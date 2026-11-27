# Proto Imports and Package Namespaces

## Learning Objectives

After this lesson, you will be able to:

- Organize multiple **.proto** files and import data types from other files.
- Distinguish import paths, Protobuf **package**, and Java **java_package**.
- Reference messages/enums by short name in the same package or by fully qualified name.
- Understand the impact of **java_multiple_files** and **java_outer_classname** on generated Java code.
- Configure include paths so **protoc** resolves dependencies correctly.
- Evaluate risks when renaming packages, moving files, or changing service names in a Spring gRPC system.

## 1. Why Are Imports and Namespaces Needed?

As **SPRING_GRPC** contracts grow, a message may be reused across multiple requests, responses, or services. Putting every type into one **.proto** file quickly makes it hard to read and prevents teams from reusing types cleanly.

Protocol Buffers supports splitting schemas into multiple files. One file can **import** another to use its declared messages, enums, or services. The **package** keyword creates a namespace for Protobuf symbols, preventing name collisions across different parts of a contract.

Three concepts to distinguish:

| Concept | What does it determine? | Example |
| --- | --- | --- |
| Import path | Which .proto file **protoc** locates | **common/address.proto** |
| **package** | Fully qualified Protobuf symbol name | **acme.common.v1.Address** |
| **java_package** | Java package of generated classes | **com.acme.common.v1** |

These three values can follow a shared convention, yet they are distinct concepts and do not automatically substitute for one another.

## 2. Organizing Schemas Across Multiple Files

Suppose several services share an address structure. You can place that type in its own file:

~~~proto
// common/address.proto
syntax = "proto3";

package acme.common.v1;

option java_package = "com.acme.common.v1";
option java_multiple_files = true;

message Address {
  string street = 1;
  string city = 2;
  string country_code = 3;
}
~~~

The file defining Customer imports and uses Address:

~~~proto
// customer/customer.proto
syntax = "proto3";

package acme.customer.v1;

option java_package = "com.acme.customer.v1";
option java_multiple_files = true;

import "common/address.proto";

message GetCustomerRequest {
  string customer_id = 1;
}

message Customer {
  string customer_id = 1;
  string display_name = 2;
  acme.common.v1.Address address = 3;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (Customer);
}
~~~

**customer/customer.proto** can use **Address** because it imported the file defining that type. The import uses the **logical path of the .proto file**, while **acme.common.v1.Address** is the symbol name in the Protobuf namespace.

A common directory convention:

~~~text
src/main/proto/
  common/
    address.proto
  customer/
    customer.proto
  order/
    order.proto
~~~

Directory names and packages can be aligned for discoverability, yet the compiler does not infer packages from directory paths. The **package** declaration itself determines the symbol namespace.

## 3. Import Paths and protoc Include Paths

In the statement:

~~~proto
import "common/address.proto";
~~~

the path is resolved relative to one of the **proto include roots** passed to the compiler. For example, if the file sits at **src/main/proto/common/address.proto**, the include root can be **src/main/proto**.

Illustrative command:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/sources/proto/main/java \
  customer/customer.proto
~~~

Run the command from the project root. The compiler resolves input paths and imports relative to the include root to locate **customer/customer.proto** and **common/address.proto**. If the include root is wrong, files will not be found even though they exist on disk.

Notes:

- Import paths use **/**, not Java package dots.
- Imports must not use absolute paths tied to a single developer machine.
- Match exact filename casing; Linux environments are typically case-sensitive.
- All required include roots, including directories containing WKTs such as **google/protobuf/timestamp.proto**, must be configured in the build.
- Import paths act as file identifiers during compilation; moving a file can break imports even if message contents did not change.

With Gradle or Maven, Protobuf plugins normally manage include paths and proto dependency artifacts. What matters is that the build configuration supplies the exact same schema tree and dependencies across all build environments.

## 4. Protobuf Package Namespaces

The declaration:

~~~proto
package acme.customer.v1;
~~~

creates a namespace for symbols declared at file level. The full name of message **Customer** is:

~~~text
acme.customer.v1.Customer
~~~

This full name is also called the **fully qualified name**. When referencing a type from another package, use the fully qualified name:

~~~proto
package acme.order.v1;

import "customer/customer.proto";

message Order {
  string order_id = 1;
  acme.customer.v1.Customer buyer = 2;
}
~~~

You can add a leading dot to specify resolution starting from the root namespace:

~~~proto
message Order {
  .acme.customer.v1.Customer buyer = 1;
}
~~~

The leading-dot form helps when a relative name might be shadowed by an identically named nested message or inner package. In large schemas, using fully qualified names at package boundaries lets readers spot cross-package dependencies right at the field.

Omitting **package** places symbols in the root namespace. That may work in tiny schemas, yet easily causes name collisions when multiple files define **Address**, **Status**, or **Request**. For shared APIs, declare a clear convention—typically including a logical domain and version such as **acme.customer.v1**.

## 5. Protobuf package vs. java_package

Example:

~~~proto
package acme.customer.v1;

option java_package = "com.acme.api.customer";
~~~

The two namespaces serve two different purposes:

- **package** belongs to Protobuf descriptors and defines the fully qualified names of messages, enums, and services.
- **java_package** specifies where generated Java classes are placed.

With the configuration above:

| Component | Name |
| --- | --- |
| Protobuf full name | **acme.customer.v1.Customer** |
| Java package | **com.acme.api.customer** |
| Java class with **java_multiple_files = true** | **com.acme.api.customer.Customer** |

A message can keep the same Protobuf package while changing its Java package to match source organization. That changes Java imports and the Java binary API, without changing Protobuf symbol names or wire format.

Conversely, changing the Protobuf **package** can impact descriptors, fully qualified type names, and gRPC service names. Do not treat changing the Protobuf package as a Java folder reorganization.

## 6. java_multiple_files and java_outer_classname

The Java generator has options controlling how generated classes are organized:

~~~proto
option java_package = "com.acme.customer.v1";
option java_multiple_files = true;
option java_outer_classname = "CustomerSchema";
~~~

### java_multiple_files

- When **false** (default), top-level types are placed inside an outer wrapper class derived from the .proto filename.
- When **true**, top-level messages and enums are generated as separate Java classes in **java_package**.
- Nested messages/enums are still accessed through their enclosing message class, e.g., **Customer.Address**.

With **java_multiple_files = true**, Java code can import directly:

~~~java
import com.acme.common.v1.Address;
import com.acme.customer.v1.Customer;
~~~

Without enabling this option, top-level types are usually referenced through the outer wrapper class, such as **CustomerSchema.Customer**, depending on the outer class name chosen by the generator.

### java_outer_classname

The **java_outer_classname** option explicitly names the file's outer wrapper class. It helps when the default name derived from the filename is awkward or conflicts with a message/enum of the same name.

Setting a stable wrapper name prevents file renames from accidentally changing generated Java class names. When modifying this option, review all Java sources importing the wrapper.

Java options never alter the Protobuf **package**. Do not expect **java_outer_classname** to alter a message's fully qualified name in descriptors.

## 7. Direct Dependency Imports and public import

A file should directly import every file defining types it uses. Do not rely on a dependency happening to be imported transitively by another file.

Example:

~~~proto
// customer/customer.proto
import "common/address.proto";

message Customer {
  acme.common.v1.Address address = 1;
}
~~~

If **order.proto** uses **Address**, **order.proto** should also import **common/address.proto** directly:

~~~proto
// order/order.proto
import "common/address.proto";

message OrderDestination {
  acme.common.v1.Address address = 1;
}
~~~

### import public

**import public** lets a file re-export a dependency so files importing it can see the re-exported symbols. This mechanism is mainly useful during schema migrations:

~~~proto
// common/location.proto
import public "common/address.proto";

message Location {
  string code = 1;
}
~~~

An older file importing only **common/location.proto** can still access symbols from **address.proto** during the transition. Document this usage and plan to remove it if the final goal is direct dependency imports.

Do not use public imports to create obscure dependency chains or hide true dependencies. When a file uses a type, direct imports make contracts easier to read and maintain.

## 8. Importing WKTs and Shared Schema Libraries

Well-known types are also imported using standard paths:

~~~proto
syntax = "proto3";

package acme.audit.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/field_mask.proto";

message AuditRecord {
  string record_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}

message UpdateAuditRequest {
  string record_id = 1;
  AuditRecord record = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

WKT files must be present on the compiler's include path. When building with Gradle/Maven, Protobuf dependencies normally supply these files; verify that the code-generation plugin sees a compatible version.

For schemas shared across multiple modules, maintain a single canonical source of definitions for types like **Address**, **Money**, or **ErrorDetail**. Avoid copying the same message into multiple packages: even if fields look identical, they are two different Protobuf types with distinct fully qualified names and may be incompatible across Any, reflection, or Java APIs.

## 9. How Do Packages and Service Names Affect gRPC?

Package names do more than avoid message collisions. For a service:

~~~proto
package acme.customer.v1;

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (Customer);
}
~~~

The service's full name is **acme.customer.v1.CustomerService**. The gRPC method path over HTTP/2 takes the form:

~~~text
/acme.customer.v1.CustomerService/GetCustomer
~~~

Therefore, changing the Protobuf package changes the **full service name** and the method path clients invoke. Old servers and new clients may fail to match the same endpoint if package/service names change without a compatibility plan.

The Java package configured by **java_package** does not replace the service name on the wire. Changing **java_package** primarily affects Java classes and source code; changing the Protobuf **package** affects descriptor namespaces and gRPC service names.

When versioning APIs, using packages like **acme.customer.v1** and later releasing **acme.customer.v2** creates clear boundaries. Both versions can coexist while clients migrate; decide upfront how shared messages are reused and how data converts between versions.

## 10. Safely Evolving Packages and Imports

Once a schema has been released:

- Do not rename a Protobuf package merely to rename a directory.
- Do not change import paths without updating all consumers and include root configurations.
- Do not move a message to a new package assuming descriptors, Any type URLs, or service routes remain unchanged.
- Do not copy a shared message into another package and treat both types as the same symbol.
- Keep field numbers and wire types stable when evolving message structures; packages do not override field compatibility rules.

Changing a message's Protobuf package usually does not change the field bytes inside a simple message if field structure stays identical. However, the type's fully qualified name changes; data packed in **google.protobuf.Any**, descriptors, reflection, and systems keyed by type name can be impacted.

For services, changing the package changes the full method name as shown in section 9. Thus, changing the package of a live service is an API contract break that requires parallel deployment or an explicit migration.

## 11. Java Example Across Two Proto Files

With **common/address.proto** and **customer/customer.proto** from section 2, when **java_multiple_files = true**, Java code can use the classes directly:

~~~java
import com.acme.common.v1.Address;
import com.acme.customer.v1.Customer;

Address address = Address.newBuilder()
    .setStreet("12 Nguyen Hue")
    .setCity("Ho Chi Minh City")
    .setCountryCode("VN")
    .build();

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("An")
    .setAddress(address)
    .build();
~~~

If a service accepts **Customer**, the gRPC stub generated by the gRPC Java plugin uses the corresponding Java class in the configured package. Ensure both the Java message generator and gRPC plugin use the same schema set, include paths, and compatible Protobuf versions.

When the IDE reports it cannot find **com.acme.common.v1.Address**, check in order:

1. Does the import statement have the right path and filename?
2. Does the compiler include root contain **common/address.proto**?
3. Does **address.proto** declare **java_package** as expected?
4. Has code generation run and is the output directory included in the source set?
5. Is **java_multiple_files** enabled, or does the type live inside an outer wrapper class?

These checks resolve issues far more reliably than guessing package names.

## 12. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using **java_package** inside an import statement | Compiler cannot locate the proto file | Import using the path relative to the include root. |
| Assuming directory structure determines the package | Fully qualified name differs from expected | Declare **package** explicitly in each file. |
| Confusing Protobuf package with Java package | Wrong type reference or accidental namespace change | Check **package** and **java_package** separately. |
| Not importing a used type directly | Build relies on fragile transitive imports | Import the file defining the type directly. |
| Renaming a file without checking outer class | Generated Java wrapper class may change name | Set a stable **java_outer_classname** if needed. |
| Changing the Protobuf package of a live service | Clients call the wrong full method name | Version/migrate the service with a plan. |
| Duplicating shared messages into another package | Two types with different fully qualified names | Import and reuse one canonical definition. |
| Different include paths between local and CI | Build fails only in one environment | Standardize proto path configuration in the build. |

## 13. Practice Exercise

Create three files:

~~~text
src/main/proto/
  common/address.proto
  customer/customer.proto
  order/order.proto
~~~

Requirements:

1. Declare **Address** in package **acme.common.v1**, Java package **com.acme.common.v1**.
2. Declare **Customer** in package **acme.customer.v1**, import **common/address.proto**, and use field **acme.common.v1.Address**.
3. Declare **Order** in package **acme.order.v1**, directly importing both **common/address.proto** and **customer/customer.proto**.
4. Enable **java_multiple_files = true**; identify the generated Java class names and imports.
5. Try changing **java_package** while keeping the Protobuf **package** unchanged; describe what changes in Java and what stays unchanged in Protobuf descriptors.
6. Try changing the Protobuf package of **CustomerService**; identify the gRPC full method name before and after the change.
7. Run **protoc** with include root **src/main/proto**, then intentionally alter the include root to observe the import-not-found error.

**Completion criteria:** accurately distinguish import path, Protobuf package, and Java package; reference shared types; explain the impact of namespaces on Java APIs, descriptors, and gRPC service routes.

## 14. Key Takeaways

- **Import path** locates a .proto file; it is resolved relative to compiler include roots.
- **package** defines the Protobuf namespace and fully qualified names of messages, enums, and services.
- **java_package** specifies the generated Java package; it does not change the Protobuf package.
- **java_multiple_files** and **java_outer_classname** control Java code organization without altering the wire schema.
- Directly import dependencies used by a file; use **import public** only for deliberate re-exports.
- Changing the Protobuf package can affect descriptors, Any type URLs, and gRPC full method names; changing the Java package affects Java source/APIs.

Organizing proto imports and package namespaces cleanly makes Protocol Buffers contracts reusable across services, keeps generated Java code consistent, and reduces risk as Spring gRPC evolves over multiple versions.
