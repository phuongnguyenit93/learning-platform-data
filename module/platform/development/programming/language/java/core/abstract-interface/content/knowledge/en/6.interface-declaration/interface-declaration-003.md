# Top-level interfaces: public and package-private

## 1. Declaration location and two access levels

A **top-level interface** is declared directly in a source file, outside any other class, interface, enum, or record. A top-level interface has only two access level options:

| Syntax | Access level | Who can reference the type name? |
| --- | --- | --- |
| `public interface PublicService { ... }` | public | Code in other packages can use the type if the package/module containing it is accessible. |
| `interface InternalService { ... }` | package-private | Code with access in the same package. |

Package-private is not a keyword. It is formed by omitting the access modifier. A top-level interface cannot be `private` or `protected`; `static` is also not a valid modifier for a top-level interface.

## 2. File names and package boundaries

With conventional Java source organization, if a file has a `public` top-level type, the file name must match that public type's name. A file should not declare multiple public top-level types.

For example, the file `PublicService.java`:

```java
package demo.api;

public interface PublicService {
    String greet(String name);
}
```

The file `InternalService.java` in the same package:

```java
package demo.api;

interface InternalService {
    String auditTag();
}
```

`InternalService` can be used from other files in `demo.api`, even though the files are separate. It cannot be imported directly from `demo.client`. The package `demo.api.internal` is also a different package; a name that looks like a parent package does not grant package-private access.

An implementation class can be kept package-private and provided externally via a public factory:

```java
package demo.api;

public final class Services {
    private Services() {}

    public static PublicService create() {
        return new DefaultService();
    }
}

final class DefaultService implements PublicService, InternalService {
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }

    @Override
    public String auditTag() {
        return "internal";
    }
}
```

Code outside the package only needs `PublicService service = Services.create()`. It does not need to know the implementation class name `DefaultService`.

## 3. Type access differs from member access

You should not infer that a method in a package-private interface also becomes package-private. Modifier rules for types and members are two separate matters. For example, a regular abstract method in an interface is still implicitly `public abstract`; interface fields are implicitly `public static final`.

Even though members are declared public, code outside the package still cannot name a package-private top-level type in its declarations. The type must be accessible before member access is meaningful.

An interface declared inside a class/interface is a member interface, not a top-level interface. A member interface has the access rules of member types and can use `private` or `protected` when the declaration location allows it.

## 4. Java Platform Module System (JPMS)

In a project with named modules, the `public` modifier is a necessary but insufficient condition for another module to use the type. Typically, all of the following are needed:

1. The consuming module reads the providing module, via `requires`.
2. The providing module exports the package containing the type via `exports`.
3. The top-level interface itself is declared `public`.

Example:

```java
module demo.api.module {
    exports demo.api;
}
```

Another module must also declare `requires demo.api.module;`. If the package is not exported, a public interface in that package does not automatically become a public API for other modules.

## 5. Checklist for diagnosing access errors

- Check the actual `package` line in both files; do not rely on directory names.
- Check whether the top-level type is `public` if it needs to be used from another package.
- Check that the file name matches the public top-level type.
- If `module-info.java` is present, check both `requires` and `exports`.
- If only internal classes need to collaborate, consider package-private to avoid exposing an unnecessary part of the API.

**Self-check:** If `InternalService` is in `demo.api`, can a class in `demo.api.client` access it just because that package has the same prefix? No; it is a different package.
