# Ensuring Release JARs Contain No Split Packages

## 1. What Is a Split Package?

In Java, a **package** is a namespace containing classes and interfaces. A **split package** occurs when the same package name appears in multiple independent modules/JARs.

Example of two JARs:

```text
dist/
├── acme-core.jar
└── acme-plugin.jar
```

Both contain classes in the `com.acme.util` package:

```text
acme-core.jar
└── com/acme/util/StringHelper.class

acme-plugin.jar
└── com/acme/util/DateHelper.class
```

When the two JARs become two named modules on the module path, the `com.acme.util` package is split between two modules. This is a structure to avoid when releasing applications under JPMS.

A safe design rule is that **each package belongs to exactly one named module** across the set of modules released and run together. Clear package ownership keeps the module graph consistent, prevents conflicts during resolution, and preserves package-private access boundaries as designed.

## 2. Why Do Split Packages Cause Problems?

### Conflicts during module resolution

JPMS verifies the consistency of the module graph. If a module reads two different modules that both export the same package, the resolver cannot uniquely determine the source of that package and resolution can fail with `ResolutionException`.

For example:

```text
com.acme.app
   | requires
   +------> com.acme.core  -- exports com.acme.util
   |
   +------> com.acme.plugin -- exports com.acme.util
```

The application reads both modules and both export `com.acme.util`. This is a split-package conflict in the graph.

Do not rely on the fact that a duplicate package name happens not to error in a specific configuration. When the dependency graph changes, a new module may read both package sources and cause resolution to fail.

### Package-private is not shared between two modules

Two classes declaring the same `package com.acme.util` but residing in two different named modules do not become part of the same runtime package. Those classes cannot rely on package-private access to call each other as they could when residing in the same module/package.

This can break legacy assumptions of applications running on the classpath, where multiple JARs contributed classes to the same package.

### Increased risk when changing dependencies and packaging

Split packages make upgrading or replacing a JAR prone to conflicts. They also make it harder to tell which module owns a package's API, classes, or resources. With automatic modules, packages are exported broadly, so package conflicts in the graph can surface when migrating from the classpath to the module path.

## 3. Detecting Split Packages in Release JARs

Inspect the **entire set of JARs deployed together**, not just each JAR individually. A JAR that has no internal package duplicates can still conflict with another JAR.

For example, list JAR contents:

```bash
jar --list --file dist/acme-core.jar
jar --list --file dist/acme-plugin.jar
```

Look for class paths sharing the same package directory, such as:

```text
com/acme/util/StringHelper.class
com/acme/util/DateHelper.class
```

Inspect module descriptors and exposed packages:

```bash
jar --describe-module --file dist/acme-core.jar
jar --describe-module --file dist/acme-plugin.jar
```

This command helps confirm module names, module descriptors, and package information. For automatic modules, the module name is derived from the JAR name and package exports follow different rules than explicit modules; you must still check for package overlap across the entire module set.

## 4. Validating the Module Graph with the Java Launcher

You can ask Java to validate modules on the module path:

```bash
java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH
```

`ALL-MODULE-PATH` requests adding all observable modules on the module path into the validation scope. If the graph has conflicts or invalid modules, the command can report errors instead of exiting cleanly.

This is a holistic module graph check. Errors may relate to dependencies or other module configuration issues, not only split packages; read the full error message to identify the two modules and packages involved.

You can check dependencies and the descriptor of a specific module with `jdeps`:

```bash
jdeps --check com.acme.app --module-path dist
```

`jdeps --check` helps inspect the module descriptor and dependencies of the specified module. Use it together with module validation and package inventory checks for clear results.

## 5. Automatically Scanning for Duplicate Packages Across JARs

To catch errors right in the build/release pipeline, you can build a package inventory from all JARs in the release directory and find packages appearing in multiple artifacts.

The Python script below uses the standard library `zipfile` module and requires no external packages. It takes a release directory, recursively scans `.jar` files, skips `module-info.class`, and normalizes class paths in multi-release JARs before determining packages.

Save as `check_split_packages.py`:

```python
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
import sys

if len(sys.argv) != 2:
    print("Usage: python check_split_packages.py <release-directory>")
    raise SystemExit(2)

root = Path(sys.argv[1])
if not root.is_dir():
    print(f"Not a directory: {root}")
    raise SystemExit(2)

owners = defaultdict(set)
jar_count = 0

for jar_path in sorted(root.rglob("*.jar")):
    jar_count += 1
    try:
        with ZipFile(jar_path) as jar:
            for entry in jar.namelist():
                name = entry.replace("\\", "/")

                # Multi-release classes live below META-INF/versions/<N>/.
                if name.startswith("META-INF/versions/"):
                    parts = name.split("/", 3)
                    if len(parts) != 4:
                        continue
                    name = parts[3]
                elif name.startswith("META-INF/"):
                    continue

                if not name.endswith(".class"):
                    continue
                if name.rsplit("/", 1)[-1] == "module-info.class":
                    continue

                package_path = name.rpartition("/")[0]
                package_name = (
                    package_path.replace("/", ".")
                    if package_path
                    else "<default package>"
                )
                owners[package_name].add(jar_path.relative_to(root).as_posix())

    except Exception as error:
        print(f"Cannot read {jar_path}: {error}")
        raise SystemExit(2)

duplicates = {
    package: sorted(paths)
    for package, paths in owners.items()
    if len(paths) > 1
}

print(f"Scanned {jar_count} JAR file(s) under {root}")

if duplicates:
    print("Split packages found:")
    for package, paths in sorted(duplicates.items()):
        print(f"  {package}")
        for path in paths:
            print(f"    - {path}")
    raise SystemExit(1)

print("No package appears in more than one JAR.")
```

Run the script from the project directory:

```bash
python check_split_packages.py dist
```

Output when an error is found:

```text
Scanned 3 JAR file(s) under dist
Split packages found:
  com.acme.util
    - acme-core.jar
    - acme-plugin.jar
```

Output when there are no duplicate packages:

```text
Scanned 3 JAR file(s) under dist
No package appears in more than one JAR.
```

The script checks packages inferred from class file paths. It is a useful artifact guardrail, though not a substitute for validating the module graph with the JDK. If a JAR is malformed or unreadable, the script exits with a non-zero status code so the pipeline does not silently skip that artifact.

## 6. Integrating Checks into the Release Process

A straightforward workflow can add the following steps after building all JARs:

1. Create a staging directory containing only the artifacts to be released together.
2. Run a package inventory to detect packages appearing in multiple JARs.
3. Run `java --validate-modules` on the staging module path.
4. Run `jdeps --check` for critical application modules.
5. Run integration tests on the module path, not only on the classpath.
6. Only package or publish artifacts when all mandatory checks pass.

Example pipeline at the command level:

```bash
python check_split_packages.py dist

java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH

jdeps --check com.acme.app --module-path dist
```

In CI, configure these commands as mandatory steps. If the script finds duplicate packages or Java validation returns an error, the build must fail so the artifacts are not published.

Run checks on the exact final staging directory. Checking source sets or intermediate build directories can miss JARs packaged from external dependencies or artifacts copied in during the release step.

## 7. How to Resolve a Detected Split Package

When two JARs share the same package, first determine which module owns that package by design.

- **Move classes into a single owning module:** if the classes belong to the same component, consolidate them into one module and publish the package only from that module.
- **Split packages by responsibility:** if the two groups of classes serve different purposes, rename the package of one group, e.g., `com.acme.core.util` and `com.acme.plugin.util`.
- **Adjust module boundaries:** if two modules need to share tight internal implementations, consider merging them or redesigning the API between modules.
- **Check packaged dependencies:** a third-party library may bring a duplicate package into the distribution. Upgrade versions, exclude conflicting artifacts, or choose a packaging approach compatible with licensing and runtime constraints.

Do not simply change the module name in `module-info.java`: different module names do not fix two modules containing the same package. Also avoid using `--patch-module` as a default workaround for release artifacts; that is a special mechanism for supplementing a chosen module and should be used intentionally.

## 8. Edge Cases to Watch For

- **Classpath vs. module path:** legacy applications can run when multiple JARs contribute classes to the same package on the classpath. When turning those JARs into named or automatic modules, the module graph enforces different constraints.
- **Automatic modules:** the module name is derived from the JAR name if no descriptor exists. They still participate in the module graph and can create package conflicts.
- **Multi-release JARs:** classes can reside inside `META-INF/versions/<version>/`. Inspection tools must account for packages in these versioned classes as well.
- **Package-private:** having the same package name does not mean the same runtime package if the classes belong to different modules.
- **Duplicate packages not read together:** some specific graphs may not immediately trigger a resolution conflict if no module simultaneously reads the overlapping export sources. However, releasing with unclear package ownership still leaves the system fragile when the graph evolves.

## Key Takeaways

- A split package is the same package name divided across multiple modules/JARs.
- In a module graph, two modules exporting the same package to a module that reads both can cause resolution to fail.
- Apply the rule that one package has one owning module in a distribution.
- Scan all JARs released together; checking each JAR in isolation is not enough.
- Use a package inventory, `java --validate-modules`, `jdeps --check`, and integration tests on the module path.
- Fix the root cause by consolidating classes into one module or splitting packages by responsibility; renaming modules does not fix split packages.