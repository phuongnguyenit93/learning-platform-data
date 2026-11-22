# Reflection access to private members

Reflection allows a program to inspect classes, fields, methods, and constructors at runtime. In many scenarios, frameworks need to read or invoke non-public members to perform dependency injection, object mapping, serialization, or data binding.

Since Java 9, JPMS places modules inside clear boundaries. Therefore, whether a class has a private field is no longer something that depends solely on `setAccessible(true)`: the module owning the package must allow the module calling reflection to deeply access that package.

Two permissions must be distinguished:

- **Java access control:** `private`, package-private, `protected`, `public` determine whether ordinary Java code is allowed to access a member.
- **Module encapsulation:** `exports` and `opens` determine whether another module can access a package at the normal API level or via deep reflection.

## 1. Why does reflection need separate access permission?

Consider a class with a private field:

~~~java
package com.acme.domain.internal;

public final class Customer {
    private final String email;

    public Customer(String email) {
        this.email = email;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Code within the same class can read `email` directly. Code outside the class cannot access this field in ordinary Java:

~~~java
Customer customer = new Customer("user@example.com");
String email = customer.email; // Compile error: email is private
~~~

Reflection allows finding a field by name:

~~~java
Field field = customer.getClass().getDeclaredField("email");
~~~

However, obtaining a `Field` object does not mean permission to read the private value has been granted. By default, `Field.get` still enforces access checks. To bypass normal Java access checks, the program can request enabling access:

~~~java
field.setAccessible(true);
String email = (String) field.get(customer);
~~~

In an application not using JPMS, or when both classes reside in the same module, this operation can work under the corresponding access rules. With two different named modules, the module system also checks whether the package containing the member is **open** to the module calling reflection.

If the package is not opened, `setAccessible(true)` can throw `InaccessibleObjectException`. The `trySetAccessible()` API returns `false` when access cannot be enabled.

## 2. exports and opens solve two different needs

Suppose the domain module wants to expose an API to the application while keeping internal packages private:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

`exports` allows modules reading `com.acme.domain` to use public types in the package `com.acme.domain.api`. It does not automatically allow frameworks to access private fields in that package.

If a framework in module `com.acme.mapper` needs deep reflection into the package `com.acme.domain.internal`, the domain module can declare:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

Meaning:

- `exports com.acme.domain.api` exposes the normal API.
- `opens com.acme.domain.internal to com.acme.mapper` allows the mapper module to perform deep reflective access into the internal package.
- The internal package is still not exported for mapper's Java code to import and use types in that package directly.

This is a useful boundary: the application uses the public API, while the framework is granted reflection permission on the exact package it needs.

### Quick comparison

| Declaration | Ordinary Java API access | Reflection to public members | Deep reflection to private members |
| --- | --- | --- | --- |
| Neither exported nor opened | No | Restricted by module boundary | No |
| `exports p` | Yes, for public types in the package | Can access public members | Not automatically allowed |
| `opens p` | Does not make the package a compile-time API | Can access via reflection | Yes, to modules it is opened to |
| `exports p; opens p` | Yes | Yes | Yes |
| `exports p to m` | Yes for target module `m` | Yes for target module | Not automatically allowed |
| `opens p to m` | No | Yes via reflection for `m` | Yes for `m` |

`exports` and `opens` do not replace each other. A package can be exported without being opened, opened without being exported, or both exported and opened if the architecture genuinely needs both.

## 3. Example: opening a package for a mapper framework

Suppose there are two modules:

~~~text
src/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/
│       ├── api/
│       │   ├── CustomerView.java
│       │   └── CustomerFactory.java
│       └── internal/
│           └── Customer.java
└── com.acme.mapper/
    ├── module-info.java
    └── com/acme/mapper/
        └── CustomerInspector.java
~~~

The domain module exposes its API and opens only the internal package to mapper:

`com.acme.domain/module-info.java`:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

Public API:

~~~java
package com.acme.domain.api;

public interface CustomerView {
    String id();
}
~~~

~~~java
package com.acme.domain.api;

public final class CustomerFactory {
    private CustomerFactory() {
    }

    public static CustomerView sample() {
        return new com.acme.domain.internal.Customer(
            "C-100",
            "customer@example.com"
        );
    }
}
~~~

Internal implementation:

~~~java
package com.acme.domain.internal;

import com.acme.domain.api.CustomerView;

public final class Customer implements CustomerView {
    private final String id;
    private final String email;

    public Customer(String id, String email) {
        this.id = id;
        this.email = email;
    }

    @Override
    public String id() {
        return id;
    }
}
~~~

The package `com.acme.domain.internal` is not exported. Consumers only see `CustomerView` and `CustomerFactory`, while the actual created object has the runtime class `Customer`.

Mapper module:

~~~java
module com.acme.mapper {
    requires com.acme.domain;
}
~~~

The mapper class reads the private field via reflection:

~~~java
package com.acme.mapper;

import com.acme.domain.api.CustomerFactory;
import com.acme.domain.api.CustomerView;

import java.lang.reflect.Field;

public class CustomerInspector {
    public static void main(String[] args) throws ReflectiveOperationException {
        CustomerView customer = CustomerFactory.sample();

        Field emailField = customer.getClass().getDeclaredField("email");

        if (!emailField.trySetAccessible()) {
            throw new IllegalStateException(
                "Module domain has not opened its internal package to mapper"
            );
        }

        String email = (String) emailField.get(customer);
        System.out.println(email);
    }
}
~~~

Compile both modules:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.domain,com.acme.mapper
~~~

Run the mapper module:

~~~bash
java --module-path out \
  --module com.acme.mapper/com.acme.mapper.CustomerInspector
~~~

Output:

~~~text
customer@example.com
~~~

Mapper does not import or directly call the `Customer` class at compile time. It only receives `CustomerView` from the API and uses the runtime class to look up the field. Reading the private field succeeds because the domain module opened the package `com.acme.domain.internal` to the exact module `com.acme.mapper`.

The example only illustrates the reflection mechanism. In a real application, if mapper only needs the email, consider adding an appropriate accessor to the API. Deep reflection is usually reserved for general-purpose frameworks or libraries that must process many object types without being able to write separate accessors for each type.

## 4. Using unrestricted opens and open module

There are three common ways to open packages.

**Opening a package to all modules:**

~~~java
module com.acme.domain {
    opens com.acme.domain.internal;
}
~~~

Any module can perform deep reflection on that package, subject to the JVM's other access conditions.

**Opening a package to a specific module:**

~~~java
module com.acme.domain {
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

This is usually the clearer choice because reflection permission is granted only to the module that needs it.

**Opening the entire module:**

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

An `open module` opens all packages for deep reflection at runtime. It does not automatically export all packages for ordinary Java code. Packages intended to be a compile-time API still need `exports` declarations.

Once `open module` is used, do not declare additional `opens` directives inside the same module declaration. Choose the opening approach according to the exact scope the framework needs, avoiding granting unnecessary reflection permissions.

## 5. Opening packages via launcher options

Sometimes you cannot edit a library's descriptor, such as a legacy dependency or an application needing to test a framework. You can grant package-opening permission at runtime using `--add-opens`:

~~~bash
java \
  --add-opens com.acme.domain/com.acme.domain.internal=com.acme.mapper \
  --module-path out \
  --module com.acme.mapper/com.acme.mapper.CustomerInspector
~~~

Syntax:

~~~text
--add-opens source-module/package=target-module
~~~

Where:

- `source-module` is the module owning the package.
- `package` is the package to open.
- `target-module` is the module permitted to perform deep reflection.

For libraries running on the classpath (unnamed module), `ALL-UNNAMED` can be used as the target:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar legacy-app.jar
~~~

This is a useful compatibility approach when migrating legacy applications to newer Java versions or diagnosing reflection errors. For modules you control, declare appropriate `opens` in `module-info.java` so access configuration is managed alongside the source code.

`--add-exports` serves a different purpose: it allows accessing public APIs in an unexported package. It does not replace `--add-opens` when reading or modifying private members is needed.

## 6. Handling reflection access errors

Two commonly used APIs are `setAccessible(true)` and `trySetAccessible()`.

### setAccessible(true)

~~~java
Field field = target.getClass().getDeclaredField("secret");
field.setAccessible(true);
Object value = field.get(target);
~~~

If the module boundary does not allow enabling access, calling `setAccessible(true)` can throw `InaccessibleObjectException`. This is a runtime error related to being unable to bypass access checks.

### trySetAccessible()

~~~java
Field field = target.getClass().getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(target);
} else {
    // Choose a public API or report that the module configuration has not opened the package
}
~~~

`trySetAccessible()` helps check beforehand and receive `false` if access cannot be enabled. This approach is suitable when a library needs to report a clear error message or provide a fallback.

If access has been enabled but the code still calls `Field.get` on an incompatible object, or with an incompatible data type, other errors can still occur. Opening a package only resolves module access; it does not bypass all reflection rules.

### Checking module status

You can check whether a package is currently open to the calling module:

~~~java
Module sourceModule = target.getClass().getModule();
Module callerModule = CustomerInspector.class.getModule();

boolean opened = sourceModule.isOpen(
    "com.acme.domain.internal",
    callerModule
);
~~~

`Module.isOpen(packageName, otherModule)` answers whether the package is open to the target module. This is a useful diagnostic check when a framework reports reflection errors.

## 7. MethodHandles and privateLookupIn

Reflection is not the only API for working with non-public members. `MethodHandles` provides a mechanism to access methods, fields, and constructors through `Lookup`.

Example:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        target.getClass(),
        lookup
    );
~~~

`privateLookupIn` can create a lookup with private access to the target class if the module and lookup conditions are met. In the case where the target resides in another module, the target's package must be open to the caller's module and the caller must read the target module.

It is not a way to bypass module encapsulation. `opens` is still part of the access contract. Method handles are useful when you need strongly typed call sites, good performance in certain scenarios, or deep integration with dynamic APIs.

## 8. Principles for designing safe boundaries

When designing a module with frameworks that use reflection, apply these principles:

1. **Prefer public APIs:** if consumers need a stable value or behavior, provide a method or interface instead of requiring consumers to read private fields.
2. **Open only necessary packages:** use `opens package to framework.module` instead of opening the entire module.
3. **Keep internal packages unexported:** reflection access does not require a package to become an ordinary Java API.
4. **Do not open packages just to mask design flaws:** review dependencies and APIs before granting more permissions.
5. **Keep reflection in the adapter/framework layer:** business code should call strongly typed abstractions.
6. **Test on the actual runtime:** module path, module names, and launcher options can differ between local, test, and production environments.
7. **Do not modify private state arbitrarily:** reflection to read data for frameworks is usually less risky than mutating internal state or final fields.

A module can open a package for an ORM or serializer while keeping its public API small. The key is that reflection permission must be granted intentionally and clearly recorded in the descriptor or launch configuration.

## 9. Checklist when encountering InaccessibleObjectException

When a framework cannot access a private member, check:

- Which package contains the member, and which module owns that package?
- Is the module calling reflection a named module or the unnamed module?
- Has the package been opened to the exact calling module?
- Does `opens` in the descriptor specify the right package and target module name?
- Is the application running the latest artifact/module descriptor?
- Can reflection be replaced by a public API or an appropriate constructor/factory?

If temporary opening via the launcher is needed, verify the exact source module, package, and target module before using `--add-opens`. Avoid using `ALL-UNNAMED` if only a specific named module needs that permission.

## Conclusion

Reflection to private members in JPMS is governed by both Java access control and module encapsulation. `exports` exposes APIs for ordinary Java code; `opens` allows deep reflection. `trySetAccessible()` helps detect early when access cannot be enabled, while `--add-opens` is a runtime option when compatibility or diagnostics are needed.

A good boundary exposes only the API consumers need, keeps implementations internal, and opens the right packages to the right frameworks. Such a design both reduces coupling and avoids turning reflection into an open door to the entire module.