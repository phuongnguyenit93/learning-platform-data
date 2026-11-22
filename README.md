# learning-platform-data

This repository contains the learning modules used by
[`java-learning`](https://github.com/phuongnguyenit93/java-learning).

Content is organized under `infrastructure/`, `integration/`, and `platform/`.
The `java-learning` repository includes this repository as the `module/` Git
submodule, preserving existing script paths such as `java-learning/module/...`.

Clone the parent project together with this content:

```bash
git clone --recurse-submodules https://github.com/phuongnguyenit93/java-learning.git
```

When updating content directly here, commit and push it to this repository.
Then commit the updated `module` submodule pointer in `java-learning` when
the parent project should use the new content version.
