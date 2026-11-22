# Module Names and Naming Rules

A module name is the identifier that the Java Platform Module System (JPMS) uses to identify a module in the module graph. This name appears in the `module` declaration of `module-info.java`, in the `requires` clauses of dependent modules, and in commands that run applications on the module path. Therefore, a module name must be syntactically valid in Java, easy to understand, and stable over time.

## 1. Where Is a Module Name Declared?

An explicit module declares its name in the `module-info.java` file located at the root directory of the module source:

```java
module com.acme.orders {
    requires java.sql;
    exports com.acme.orders.api;
}
```

In this example:

- `com.acme.orders` is the **module name**.
- `java.sql` is the name of a module on which the current module depends.
- `com.acme.orders.api` is the name of a package exposed for other modules to use.

Module names and package names are two different kinds of identifiers. The `requires` clause takes a module name; the `exports` clause takes a package name. A module can contain multiple packages, and a module name is not required to match a specific package.

## 2. Valid Syntax

A module name is one or more Java identifiers separated by dots (`.`). Each component between two dots must itself be a valid identifier.

Examples:

| Name | Valid? | Explanation |
|---|---|---|
| `com.acme.orders` | Yes | All components are valid identifiers |
| `org.example.billing.api` | Yes | Multiple components can be used to express scope |
| `com.acme2.orders` | Yes | Identifiers can contain digits after the first character |
| `com.2orders` | No | The component `2orders` starts with a digit |
| `com.acme-orders` | No | Hyphens are not part of identifier syntax |
| `com..orders` | No | There is an empty component between two dots |
| `com acme.orders` | No | Module names cannot contain whitespace |

A Java identifier usually starts with a letter, an underscore, or a `$` symbol; subsequent characters may include digits. However, Java keywords cannot be used as identifiers. Since Java 9, `_` alone is a keyword and cannot be used as a name component.

At the language level, Java allows Unicode identifiers and some uncommon characters. In ordinary projects, prefer unaccented Latin letters, digits, and dots so names are easy to read, easy to type, and less likely to vary across environments.

Module names are case-sensitive. Although `com.acme.orders` and `com.acme.Orders` are two different names, the common convention is to write them entirely in lowercase to stay consistent with Java package naming.

## 3. Recommended Naming Conventions

### Use Reverse Domain Order

A common practice is to reverse the domain name of the organization or project, then append the product or feature name:

- `com.acme.orders`
- `com.acme.orders.api`
- `com.acme.orders.persistence`
- `vn.example.inventory`
- `org.example.reporting`

Reverse domain naming helps reduce the risk of name collisions between libraries developed by different teams. This is a naming convention, not a requirement that the module must correspond to an active Internet domain.

If the project does not own its own domain name, choose a stable namespace controlled by the team, such as the namespace of the organization or open-source project. Avoid choosing overly generic names like `util`, `common`, or `core` as standalone module names because they easily collide with other modules.

### Express the Module's Responsibility

The name should tell readers which business domain or technical responsibility the module serves. For example, in a sales system:

- `com.acme.orders` manages orders.
- `com.acme.catalog` manages the product catalog.
- `com.acme.billing` handles payments and invoices.

Only split out submodules such as `com.acme.orders.api` or `com.acme.orders.persistence` when they represent meaningful dependency boundaries. There is no need to create a module for every package or every class.

### Keep Names Stable

Module names are referenced by other modules in `requires`. Renaming a module can therefore break build configurations, the module path, and dependent modules. Choose a name that can endure over the long term.

Do not include information that changes per release or environment in the module name, for example:

- Avoid `com.acme.orders.v2` just to indicate a release version.
- Avoid `com.acme.orders.dev` or `com.acme.orders.prod` just to distinguish environments.
- Avoid putting the JAR filename or build date into the module name.

Release versions, environment configurations, and artifact names should be managed through their respective mechanisms. If you need to change the API or module boundaries, do so as an intentional compatibility change.

### Avoid Platform Namespaces

Do not name application modules under the `java.*` or `jdk.*` prefixes; these are namespaces reserved for the Java Platform and JDK. Use your organization's or project's namespace to avoid confusion and conflicts.

## 4. Module Names Differ from Package Names and JAR Filenames

These three kinds of names are related but not identical:

| Component | Example | Where It Is Used |
|---|---|---|
| Module name | `com.acme.orders` | `module`, `requires`, module path |
| Package name | `com.acme.orders.api` | `package`, `exports`, `opens` |
| JAR filename | `orders-service-2.1.0.jar` | Artifact name on the filesystem or in a repository |

For example, the JAR file may be named `orders-service-2.1.0.jar` while the module inside is named `com.acme.orders`. For a JAR with `module-info.class`, the module name is determined by the module descriptor; it does not need to be inferred from the filename.

When designing multiple modules, place packages under the project's namespace and avoid having multiple named modules contain the same package. Sharing a package across multiple named modules in the same configuration can cause a split package error when the module graph is resolved.

## 5. Automatic Module Names

A library JAR without `module-info.class` can still be placed on the module path. When that happens, JPMS can treat it as an **automatic module**.

The automatic module name is determined in the following order:

1. If the JAR has the `Automatic-Module-Name` manifest attribute, the value of that attribute is used as the module name.
2. If that attribute is absent, the name is derived from the JAR filename: strip the `.jar` extension, remove recognized version suffixes, replace sequences of non-alphanumeric characters with dots, collapse consecutive dots, and trim leading/trailing dots.

For example, `commons-lang3-3.12.0.jar` can be derived into the name `commons.lang3`. This derivation depends on the filename, so renaming the artifact can change the module name that other modules `requires`.

For libraries that want to support JPMS users without yet shipping a module descriptor, declare a stable name in the manifest:

```text
Automatic-Module-Name: org.example.reporting
```

When the library is upgraded to an explicit module via `module-info.java`, the name in the module descriptor will establish the module's identity. The published name should be kept compatible so dependent applications do not have to change `requires` solely because the library moved from an automatic module to an explicit module.

You can check the name recognized by the JDK with the command:

```bash
jar --describe-module --file libs/commons-lang3-3.12.0.jar
```

This command is useful when encountering module-not-found errors or when you need to confirm what name a legacy library is recognized under.

## 6. Example Source Structure and Module Descriptor

A project with two modules can organize its sources as follows:

```text
src/
├── com.acme.orders/
│   ├── module-info.java
│   └── com/acme/orders/api/OrderService.java
└── com.acme.billing/
    ├── module-info.java
    └── com/acme/billing/api/InvoiceService.java
```

`src/com.acme.orders/module-info.java`:

```java
module com.acme.orders {
    requires java.sql;
    exports com.acme.orders.api;
}
```

`src/com.acme.billing/module-info.java`:

```java
module com.acme.billing {
    requires com.acme.orders;
    exports com.acme.billing.api;
}
```

Here, `com.acme.billing` depends on the `com.acme.orders` module using the exact declared module name. Exported packages are still written out in full in the `exports` clause. The source directory names in the example mirror the module names to make organizing the project easier, but it is the content of the module descriptor itself that declares the name of an explicit module.

## 7. Common Mistakes

- **Using hyphens in a module name:** `com.acme.order-service` is not a valid module name according to identifier syntax. Use `com.acme.order.service` or another name with valid components.
- **Using a package name in `requires`:** `requires` expects a module name, not the name of an exported package.
- **Getting capitalization wrong:** module names are case-sensitive, so `com.acme.orders` differs from `com.acme.Orders`.
- **Renaming an automatic module's JAR without checking:** the filename-derived name may change and break `requires` declarations. Use `Automatic-Module-Name` to pin the name for a library without a descriptor.
- **Using overly generic names:** names like `common` are hard to distinguish and easily collide with other libraries. Add your organization's namespace and a specific responsibility.
- **Confusing module names with package names:** `exports com.acme.orders.api;` exports a package; it does not create or rename a module.

When encountering a `module not found` error, check three things: whether the name in `requires` matches the declared module name exactly, whether the module is actually on the module path, and whether an automatic module name was derived differently than expected from the JAR filename.

## 8. Naming Checklist

Before finalizing a module name, check:

- [ ] Each dot-separated component is a valid Java identifier.
- [ ] The name uses lowercase and is easy to read.
- [ ] The namespace is likely to be unique, preferring reverse domain order or an organization-controlled namespace.
- [ ] The name expresses the module's responsibility and is not overly generic.
- [ ] The name does not contain release versions, environments, or build information.
- [ ] The name does not use the platform-reserved `java.*` or `jdk.*` namespaces.
- [ ] Names in `requires` match the module names provided on the module path exactly.
- [ ] For automatic module libraries, a stable name is published via `Automatic-Module-Name` if possible.

A good module name is usually concise, has a clear namespace, accurately describes its responsibility boundary, and does not need to change across release versions.