# Security testing

The test suite uses `ha-testcontainer`, following the UIX test shape. It boots a disposable Home Assistant version from `tests/HA_VERSION`, mounts this custom integration, and exercises real REST and WebSocket APIs. No browser or visual test dependency is required for this suite.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
pytest tests/
```

Use `pytest tests/test_runtime_security.py -k stale` for one test. The VS Code tasks provide equivalent setup, full-suite, selected-test, and persistent-HA commands.

Each new capability must add tests for its validator, exact user-facing error, authorization, successful bounded execution, denied execution, trace/audit metadata, changed-script invalidation, and every allowed template-result boundary. The suite currently uses local fake MQTT and Z-Wave JS services so the real Home Assistant script and service paths can be tested without a network broker or physical lock.

The implemented registry has validator and runtime assertions for every stored protected-action descriptor and its original-script trace metadata. Protected-action UI acknowledgement still requires tests proving that every instance is presented, and that an added, removed, changed, or unsupported action cannot retain a previous approval.
