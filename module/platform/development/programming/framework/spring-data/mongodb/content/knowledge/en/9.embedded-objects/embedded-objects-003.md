# Constructor Parameter Names, -parameters, and Data Mismatch Errors

## 1. The Practical Problem: Document Has Data, Yet Java Fails to Create the Object

In MongoDB, a document can contain multiple nested objects. Spring Data MongoDB reads those objects into Java classes through mapping. When a Java class uses a parameterized constructor, the framework must know **which BSON value corresponds to each parameter**.

Suppose the customers collection contains the following document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  displayName: "Lan",
  address: {
    city: "Da Nang",
    postal_code: "550000"
  }
}
~~~

If the Address class uses a constructor taking two parameters city and postalCode, Spring Data needs to determine:

- The **city** parameter corresponds to the Java property **city**, read from the BSON field **address.city**.
- The **postalCode** parameter corresponds to the Java property **postalCode**, read from the BSON field **address.postal_code** if an alias is declared with @Field.

If **constructor parameter name** information is missing from bytecode or a parameter name cannot map back to the class's persistent properties, object creation can fail even when the document is completely valid BSON.

This is the topic of **Constructor Parameter Names, -parameters, and Data Mismatch Errors**, part of the **Objects and Embedding** chapter. Within the **SPRING_DATA_MONGODB** module, understanding constructor binding is fundamental for mapping documents, working with MongoTemplate or repositories, and writing data tests. Mapping choices also affect queries, aggregations, indexes, transactions, reactive access, and data troubleshooting.

After this lesson, you will be able to:

1. Explain how Spring Data MongoDB reads embedded documents and binds values to Java constructors.
2. Use **javac -parameters** to preserve parameter names in bytecode when needed.
3. Select a mapping constructor with **@PersistenceCreator** and understand record/no-args constructor cases.
4. Distinguish **Java parameter names**, **Java property names**, and **BSON field names**.
5. Analyze errors caused by missing fields, wrong types, renamed fields, or structural changes in embedded objects.
6. Test round-trip mapping and legacy data without relying on a single sample document.

## 2. Nested Document Mapping Flow

Spring Data MongoDB typically uses **MappingMongoConverter** to convert between BSON documents and Java objects. For a root document with embedded objects, the framework reads the root level and then instantiates the Java types of nested properties.

~~~mermaid
flowchart TD
    A["BSON customers document"] --> B["MappingMongoConverter"]
    B --> C["Customer"]
    C --> D["address property"]
    D --> E["Embedded BSON document"]
    E --> F["Select Address constructor"]
    F --> G["Read values by property mapping"]
    G --> H["Invoke Address constructor"]
    H --> I["Customer containing constructed Address"]
~~~

**Reading an embedded object is not like querying another collection.** An Address class that is part of Customer is normally stored as a subdocument directly inside the customers collection; there is no need for a separate address collection or @Document annotation on Address.

Spring Data relies on two sources of information:

- **Java type metadata:** which constructor will be invoked, parameter names and types, persistent properties, and mapping annotations.
- **The BSON document:** which fields exist, their values, BSON types, and nested structure.

Mismatches between these two sources are a common cause of mapping errors.

## 3. Correct Example: Constructor Binding for Embedded Address

The Customer class is the root document:

~~~java
package com.example.customers;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {

    @Id
    private final ObjectId id;

    private final String displayName;

    private final Address address;

    public Customer(ObjectId id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public ObjectId getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

The Address class does not need @Document because it is an embedded object:

~~~java
package com.example.customers;

import org.springframework.data.mongodb.core.mapping.Field;

public class Address {

    private final String city;

    @Field("postal_code")
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

The parameters **id**, **displayName**, **address**, **city**, and **postalCode** match the names of their corresponding Java properties. This is a key condition for Spring Data to resolve constructor values. The BSON field name **postal_code** is mapped to the Java property **postalCode** via @Field.

When compiled with proper parameter name metadata, it can be read as follows:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public class CustomerService {
    private final MongoTemplate mongoTemplate;

    public CustomerService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public String customerCity(String id) {
        ObjectId objectId = new ObjectId(id);
        Customer customer = mongoTemplate.findById(objectId, Customer.class);
        if (customer == null || customer.getAddress() == null) {
            return null;
        }
        return customer.getAddress().getCity();
    }
}
~~~

For the example document, this method returns **Da Nang**. On a successful read, Spring Data selected the Customer constructor and then instantiated Address using the values from the subdocument.

## 4. Why Do Constructor Parameter Names Matter?

In Java source code, we see:

~~~java
public Address(String city, String postalCode) {
    this.city = city;
    this.postalCode = postalCode;
}
~~~

At runtime, however, Spring Data works with **compiled classes**, not Java source files. If parameter names are not preserved, Java reflection may only see synthetic names like **arg0**, **arg1** instead of **city**, **postalCode**.

When a constructor is used to instantiate an object, Spring Data must match each parameter to a **persistent property** of the entity. This matching typically relies on parameter names, or on other metadata supported by the framework such as record component metadata. Missing parameter names can therefore cause an error when a parameter cannot be mapped to any property.

### 4.1. Parameter Names Are Java Property Names, Not BSON Field Names

Example:

~~~java
public class Address {
    @Field("postal_code")
    private final String postalCode;

    public Address(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

**postalCode** is the Java property name and constructor parameter name; **postal_code** is the BSON field name. Spring Data uses @Field metadata to bridge the two.

A common mistake is renaming the parameter to postal_code upon seeing the postal_code field in MongoDB:

~~~java
// INCORRECT example for standard constructor binding:
public Address(String postal_code) {
    this.postalCode = postal_code;
}
~~~

The parameter name **postal_code** does not match the Java property **postalCode**. Even though the constructor body assigns the variable to the right field, the mapper does not analyze Java method bodies; it must locate the matching property from metadata.

### 4.2. Parameter Names Must Match Exactly

Spring Data does not automatically assume:

| Parameter Name | Java Property Name | Treated as Equivalent Automatically? |
| --- | --- | --- |
| city | city | Yes, when metadata and type match. |
| postalCode | postalCode | Yes, when metadata and type match. |
| zipCode | postalCode | No. |
| postal_code | postalCode | No, not from the BSON field string alone. |
| name | displayName | No. |
| customerAddress | address | No. |

Renaming a constructor parameter without renaming the corresponding Java property can break constructor binding on reads, even though the code compiles cleanly.

## 5. What Is -parameters?

**-parameters** is a **javac** compiler option that instructs the compiler to store method and constructor parameter names in bytecode so reflection-based tools can read them.

Manual compilation example:

~~~bash
javac -parameters Address.java
~~~

A regular Java class compiled without -parameters may expose **arg0**, **arg1** through reflection. With -parameters, bytecode retains metadata exposing **city**, **postalCode**.

This flag does not rename BSON fields, create a MongoDB schema, or fix documents with bad data. It simply allows metadata-driven tools to see the **parameter names written in source code**.

### 5.1. Maven Configuration

Example compiler plugin configuration:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

If the project inherits compiler settings from Spring Boot or a parent POM, -parameters may already be enabled. **Check the effective build configuration** instead of blindly adding the plugin again.

### 5.2. Gradle Configuration

With Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

This is an illustrative configuration snippet and does not require modifying module build files while studying this lesson. For Gradle Kotlin DSL, the configuration syntax differs from Groovy DSL.

### 5.3. How to Verify Parameter Metadata

Java reflection can show whether parameter names were compiled into the class:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

Constructor<Address> constructor =
    Address.class.getDeclaredConstructor(String.class, String.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(
        parameter.getName() + ": " + parameter.isNamePresent()
    );
}
~~~

For a regular class compiled with **-parameters**, the output looks like:

~~~text
city: true
postalCode: true
~~~

If metadata is absent, the output is typically:

~~~text
arg0: false
arg1: false
~~~

You can inspect bytecode with the JDK tool:

~~~bash
javap -v -p com.example.customers.Address
~~~

In the output, look for the **MethodParameters** attribute on the constructor. In multi-module builds, inspect the **exact running class**: enabling -parameters in one module does not guarantee other modules or dependencies were compiled the same way.

### 5.4. -parameters Is Not the Only Mechanism

Some class kinds have other metadata sources; for example, a **Java record** stores component metadata in the record definition. The framework can infer canonical constructor parameter names from record metadata. Kotlin provides its own metadata when used with the corresponding Kotlin/Spring Data support.

However, for **regular Java classes with parameterized constructors**, -parameters is the explicit and reliable choice for constructor binding. Do not rely on debug symbols or compiler/version-specific behavior as a long-term contract.

## 6. Which Constructor Does Spring Data Choose?

A class may have a no-args constructor, a full-argument constructor, business constructors, or static factories. Spring Data must decide the **instantiation path** when reading BSON.

Key points of Spring Data's creator selection mechanism:

1. A constructor or static factory annotated with **@PersistenceCreator** can be used to designate the instantiation path.
2. When only one suitable constructor exists, Spring Data can choose that constructor.
3. For a **Java record**, the canonical constructor is the natural instantiation path.
4. When multiple constructors exist without an explicit declaration, creator selection depends on Spring Data rules and entity kind; avoid leaving the framework to guess your intent.
5. When a no-argument constructor is chosen, Spring Data can instantiate the object first and populate persistent properties afterward instead of binding all fields through the constructor.

Exact precedence among multiple constructors and static factories can vary across Spring Data versions; the practical rule is to **explicitly mark the data-reading constructor** with @PersistenceCreator whenever a class has multiple initialization paths.

### 6.1. @PersistenceCreator

Example of an embedded Address with multiple constructors:

~~~java
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Field;

public class Address {
    private final String city;

    @Field("postal_code")
    private final String postalCode;

    @PersistenceCreator
    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }

    public Address(String city) {
        this(city, null);
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

The annotation tells Spring Data to choose the two-argument constructor when reading data, while the one-argument constructor serves application code creating objects. When calling the selected constructor, Spring Data still must resolve the names city and postalCode to properties.

**@PersistenceCreator cannot fix wrong parameter names on its own.** If the annotation selects a constructor taking a parameter named name while the entity only has a displayName property, binding can still fail.

### 6.2. Distinguishing @PersistenceCreator and @Document

- **@Document** describes a root document type and its collection.
- **@PersistenceCreator** describes the constructor/factory used to instantiate an object from stored data.
- **@Field** describes the BSON field name corresponding to a Java property.
- **@Id** describes the property mapped to BSON _id.

An embedded Address class usually **does not need @Document**, though it may need @PersistenceCreator if it has multiple constructors or needs an explicit mapping path.

## 7. Constructor Parameter Name Mismatch with Property

Consider the following class:

~~~java
public class CustomerName {
    private final String displayName;

    public CustomerName(String name) {
        this.displayName = name;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Even though the constructor assigns the value to displayName properly, the parameter name **name** does not match the property name **displayName**. When Spring Data uses this constructor to materialize CustomerName, it cannot infer from the assignment statement inside the constructor body that name belongs to displayName.

A clear fix:

~~~java
public class CustomerName {
    private final String displayName;

    public CustomerName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

If a different parameter name is required due to an API or library constraint, consider changing the constructor design, using a custom converter, or choosing another suitable instantiation approach. Do not expect @Field on the property to make two different Java parameter names synonymous.

## 8. Other Mismatches Between Java Properties and BSON Fields

Java code can maintain clean naming even when BSON fields use snake_case:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public class Address {
    private final String city;

    @Field("postal_code")
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }
}
~~~

Matching document:

~~~javascript
{
  address: {
    city: "Ha Noi",
    postal_code: "100000"
  }
}
~~~

If MongoDB actually stores **postalCode** while Java maps **postal_code**, the property may be read as null or fail in the constructor if null is rejected:

~~~javascript
{
  address: {
    city: "Ha Noi",
    postalCode: "100000"
  }
}
~~~

This is a **data and field-name contract error**, not missing parameter name metadata in bytecode. Enabling -parameters will not transform legacy documents from postalCode to postal_code. Options include:

- Migrating old data to the agreed BSON field name.
- Using a compatibility reader layer that accepts multiple schemas and normalizes them before building the domain model.
- Using a custom converter when legacy structures are complex and need uniform reading in many places.
- Avoiding full-document updates before understanding which legacy fields could be dropped.

## 9. Missing Fields, Nulls, and Default Values

MongoDB distinguishes between a **non-existent field** and a **field present with a null value**:

~~~javascript
// Missing postal_code.
{ address: { city: "Hue" } }

// postal_code present with null value.
{ address: { city: "Hue", postal_code: null } }

// Expected format.
{ address: { city: "Hue", postal_code: "530000" } }
~~~

For a **String** constructor parameter, an absent value can result in null being passed to the constructor, depending on mapping and data. If the constructor requires non-null values, it should express that explicitly:

~~~java
import java.util.Objects;

public Address(String city, String postalCode) {
    this.city = Objects.requireNonNull(city, "city is required");
    this.postalCode = Objects.requireNonNull(
        postalCode,
        "postalCode is required"
    );
}
~~~

When a legacy document lacks postal_code, the constructor may throw an exception during Spring Data reads. This is not necessarily a -parameters issue; it may be data violating an invariant enforced by Java.

### 9.1. Primitives and Boxed Types

Example of an embedded LineItem:

~~~java
public record LineItem(String sku, int quantity) {}
~~~

If quantity is missing or null in BSON, the Java primitive **int** cannot hold null. Materializing the record may fail because there is no valid value for the primitive parameter. Using **Integer** allows representing null, though only when missing data is valid for the business domain. If quantity is mandatory, validate inputs and use explicit validation/migration.

Never silently assume "missing means 0" when 0 has a distinct business meaning from "unknown." Default assignment should be part of the data contract.

### 9.2. Null for an Entire Embedded Object

These states also differ:

~~~javascript
{ displayName: "Lan" }                     // Missing address.
{ displayName: "Lan", address: null }      // address = null.
{ displayName: "Lan", address: {} }        // Empty address.
{ displayName: "Lan", address: { city: "Hue" } }
~~~

In Java, the first two cases can both map to **address == null** if the model does not track field presence. The **address: {}** case requires constructing an Address object from an empty subdocument; constructors with required parameters may fail. If the business needs to distinguish missing from null, use a data model or read path that preserves the distinction.

## 10. BSON Type Mismatches and Schema Evolution

Constructor binding also depends on **data types**. The following two documents look similar but have different schemas:

~~~javascript
// V1: address is a string.
{
  displayName: "Lan",
  address: "Da Nang"
}

// V2: address is an embedded object.
{
  displayName: "Lan",
  address: { city: "Da Nang", postal_code: "550000" }
}
~~~

If Java declares **Address address**, the v1 document containing a BSON String may not be converted into Address as intended by the default converter. The error here is a **schema mismatch**, not missing parameter name metadata.

During a schema upgrade, decide:

1. How many documents currently use each shape?
2. Must the new application read both shapes during a transition period?
3. Can a String be converted to Address without losing information?
4. When will the new reader be deployed, and when will new writers emit the new structure?
5. Should a schemaVersion field be added to identify the stored format explicitly?

Data conversion can be done via batch migration or a version-aware adapter layer. **Simply changing a field type from String to Address in code does not convert existing BSON documents.**

## 11. Constructor Binding with Java Records

Java records are a convenient choice for representing immutable value objects:

~~~java
public record AddressView(String city, String postalCode) {}
~~~

A record has a **canonical constructor** and component metadata. In Spring Data MongoDB versions supporting Java records, the framework can use record metadata to map components without relying entirely on regular-class parameter name inspection.

For snake_case BSON names, you can decouple the domain record from the storage shape using a converter, or define a persistence model with explicit @Field annotations. Example of a record whose BSON field names match its components:

~~~java
public record AddressView(String city, String postalCode) {}
~~~

Matching document:

~~~javascript
{
  address: {
    city: "Da Nang",
    postalCode: "550000"
  }
}
~~~

This **does not mean records automatically translate arbitrary field names**: if MongoDB stores postal_code, you still need matching mapping or migration. Also ensure the canonical constructor has components of compatible types; missing/null issues still apply to records.

### 11.1. Constructors with Computation or Validation

A record with a compact constructor:

~~~java
public record AddressView(String city, String postalCode) {
    public AddressView {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city must not be blank");
        }
    }
}
~~~

If an old document lacks city, the constructor throws an exception. This is **validation running on read**, not only when the application creates new objects. Decide whether to accept or convert legacy schemas before enforcing strict invariants on records.

## 12. Mapping Arrays of Embedded Objects

A document can contain a list of addresses:

~~~javascript
{
  displayName: "Lan",
  addresses: [
    { city: "Ha Noi", postal_code: "100000" },
    { city: "Da Nang", postal_code: "550000" }
  ]
}
~~~

The Java class can declare:

~~~java
import java.util.List;

public class CustomerAddresses {
    private final String displayName;
    private final List<Address> addresses;

    public CustomerAddresses(
            String displayName,
            List<Address> addresses) {
        this.displayName = displayName;
        this.addresses = addresses;
    }

    public String getDisplayName() {
        return displayName;
    }

    public List<Address> getAddresses() {
        return addresses;
    }
}
~~~

When reading, Spring Data must instantiate **every Address element** in the array. If a single element uses the wrong field name, wrong type, or misses a required field, reading the entire CustomerAddresses can fail.

Example of a malformed element:

~~~javascript
{
  addresses: [
    { city: "Ha Noi", postal_code: "100000" },
    { city: { name: "Hue" }, postal_code: "530000" }
  ]
}
~~~

The city property expects a String, yet one element stores an object. When diagnosing, check the **array element index** along with the field path, not only the root document.

MongoDB can store mixed-type arrays, but with **List<Address>** in Java, design each element to have a consistent structure for reliable mapping and testing.

## 13. Common Mapping Errors and How to Distinguish Them

Errors can occur at several points: creator discovery, parameter binding, value conversion, constructor invocation, remaining field population, or callback execution. Exact exception names and messages depend on the Spring Data version, driver, and root cause.

| Symptom | Common Cause | Where to Check |
| --- | --- | --- |
| Unable to map constructor parameter to property | Parameter name missing or misspelled | Check -parameters, reflection isNamePresent, and Java property names. |
| Spring Data picks an unexpected constructor | Class has multiple constructors or factories | Check selection rules, @PersistenceCreator, and creator metadata. |
| Constructor parameter receives null despite BSON data | BSON field name does not match @Field or data lives at another path | Compare actual BSON with property mapping; check nested paths. |
| Constructor throws IllegalArgumentException/NullPointerException | Missing data, null, or business invariant violation | Inspect field values and root cause stack trace. |
| Cannot convert String to Address | Legacy schema stored a string while Java expects an object | Identify versions and plan schema migration or an adapter. |
| One document reads fine, another fails | Collection contains inconsistent data | Profile BSON types and inspect the failing record. |
| Error happens only on the second array element | One embedded item has a mismatched field type | Inspect individual elements of the array. |
| Writes succeed but reads fail | Write and read mappings are incompatible | Write round-trip tests; inspect constructors, @Field, and converters. |
| Works locally but fails when deployed | Another build/module lacks metadata or dependency versions differ | Inspect actual bytecode, deployed artifact, and -parameters. |

**Do not fix every object-reading error by adding a no-args constructor.** That can cause the framework to pick a different instantiation path, hide bad data, or weaken invariant enforcement in immutable classes. First determine whether the error comes from metadata, field names, BSON types, or business data.

### 13.1. Layer-by-Layer Error Classification

A helpful diagnostic flow:

~~~mermaid
flowchart TD
    A["Cannot read embedded object"] --> B{"Correct constructor selected?"}
    B -->|No| C["Check creator and @PersistenceCreator"]
    B -->|Yes| D{"Parameter names present and match properties?"}
    D -->|No| E["Check -parameters, record, Java names"]
    D -->|Yes| F{"BSON fields/types match?"}
    F -->|No| G["Check @Field, schema, migration"]
    F -->|Yes| H{"Did constructor throw?"}
    H -->|Yes| I["Check nulls, business invariants"]
    H -->|No| J["Check converters/callbacks and remaining mappings"]
~~~

## 14. Diagnosing with MongoDB Data

Before modifying classes, inspect the **actual document**:

~~~javascript
db.customers.findOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { _id: 1, displayName: 1, address: 1 }
);
~~~

### 14.1. Inspecting BSON Types

The aggregation **$type** operator returns the BSON type name of an expression:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      displayName: 1,
      addressType: { $type: "$address" },
      cityType: { $type: "$address.city" },
      postalCodeType: { $type: "$address.postal_code" }
    }
  }
]);
~~~

For standard documents, addressType is **object**, and cityType and postalCodeType are **string**. For legacy or corrupted records, results can be **missing**, **null**, **object**, or **string** in unexpected places.

Find documents storing address as a String:

~~~javascript
db.customers.find({
  address: { $type: "string" }
});
~~~

Find documents where address is an object but postal_code is absent:

~~~javascript
db.customers.find({
  address: { $type: "object" },
  "address.postal_code": { $exists: false }
});
~~~

Distinguish **missing** from **null** based on business rules. A `{ field: null }` filter in MongoDB matches both null fields and missing fields; use $type or $exists when you need to separate the two cases.

### 14.2. Checking Legacy Data That Deviates from the Current Schema

If you migrated from postalCode to postal_code, count documents still using the old name:

~~~javascript
db.customers.countDocuments({
  "address.postalCode": { $exists: true }
});
~~~

This gives you the basis to plan a migration or compatibility reader. **Do not adjust annotations just to match one record** without knowing how widespread each schema is.

## 15. Diagnosing Bytecode and Constructor Selection

When a stack trace reports that a parameter or property could not be found, inspect the class actually loaded at runtime:

1. Check which constructor Spring Data can select and whether @PersistenceCreator is present.
2. For regular Java classes, verify javac -parameters on the module producing that class.
3. Use reflection or javap to confirm parameter names in bytecode.
4. Compare each parameter name against the Java persistent property, not only the BSON field name.
5. Compare the parameter type against the type to be converted.
6. Inspect real BSON data, especially embedded objects/arrays and legacy records.

Reflection snippet to inspect Customer:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

for (Constructor<?> constructor : Customer.class.getDeclaredConstructors()) {
    System.out.println("Constructor: " + constructor);
    for (Parameter parameter : constructor.getParameters()) {
        System.out.println(
            "  " + parameter.getName()
            + ", present=" + parameter.isNamePresent()
            + ", type=" + parameter.getType().getName()
        );
    }
}
~~~

The goal is to catch constructors whose parameters are named arg0, arg1 or unexpectedly renamed. Avoid printing sensitive data values to logs when you only need metadata and type diagnostics.

### 15.1. Why Fixing -parameters Alone Might Not Be Enough

Even if reflection reports city and postalCode accurately, the program will still fail if:

- BSON stores **postalCode** while the mapping expects **postal_code**.
- BSON stores **address** as a String while Java expects Address.
- The constructor rejects null for a missing field.
- A registered converter alters reading logic.
- The class has multiple constructors and Spring Data picks the wrong creator.
- The application is running an older artifact that lacks the updated compilation.

Verify the **entire chain from BSON to Java object**, rather than relying on a single build flag.

## 16. Integration Testing for Embedded Objects

A unit test instantiating Address directly via new Address(...) only proves the Java constructor works. It **does not test** whether Spring Data reads the BSON field name, resolves parameter names, or invokes the right creator.

Good tests should:

1. Write real documents into a test collection.
2. Read them back using Spring Data MongoTemplate or a repository.
3. Assert on the embedded object and its properties.
4. Include cases with missing fields, wrong names, wrong types, or legacy data.
5. Run only against a dedicated test database and clean up afterward.

JUnit 5 example with MongoTemplate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class CustomerMappingTest {

    @Autowired
    private MongoTemplate mongoTemplate;

    @Test
    void readsEmbeddedAddressUsingConstructorParameters() {
        ObjectId id = new ObjectId();

        Document raw = new Document("_id", id)
            .append("displayName", "Lan")
            .append("address", new Document("city", "Da Nang")
                .append("postal_code", "550000"));

        mongoTemplate.getCollection("customers").insertOne(raw);
        try {
            Customer loaded = mongoTemplate.findById(
                id, Customer.class
            );
            assertThat(loaded).isNotNull();
            assertThat(loaded.getAddress()).isNotNull();
            assertThat(loaded.getAddress().getCity())
                .isEqualTo("Da Nang");
            assertThat(loaded.getAddress().getPostalCode())
                .isEqualTo("550000");
        } finally {
            mongoTemplate.getCollection("customers")
                .deleteOne(new Document("_id", id));
        }
    }
}
~~~

This test deliberately **writes raw BSON through the driver** and reads it via Spring Data mapping. That verifies reading from field **postal_code** into property **postalCode**, rather than letting the same converter write and read and mask errors when legacy data has a different shape.

### 16.1. Test Malformed Data Too to Lock Down the Contract

Include fixtures such as:

| BSON Fixture | Team-Defined Expectation |
| --- | --- |
| Valid address, postal_code is String | Reads cleanly with exact values. |
| address completely missing | Allows null or throws per business rule. |
| address = null | Handled explicitly, not treated as a populated object. |
| address = {} | Preserves constructor invariants. |
| address.postalCode instead of postal_code | Handled via migration/adapter or flagged as bad data. |
| address.city is an Object instead of String | Throws conversion error or follows explicit fallback policy. |
| addresses contains one element of wrong type | Detected and pinpoints the failing document/element. |

If **data integrity** must be enforced, you can use collection validation with $jsonSchema to validate BSON types of embedded fields. Validators do not convert existing data on their own; combine them with profiling and migrations.

## 17. Impact on Queries, Indexes, and Performance

Actual stored field names also govern how MongoDB searches and indexes documents:

~~~javascript
db.customers.createIndex({ "address.postal_code": 1 });
db.customers.find({ "address.postal_code": "550000" });
~~~

In a Spring Data MongoDB application, when writing a **Query** with an entity class, mapping translates Java property paths into BSON field names according to @Field. But when writing queries directly with the **MongoDB Java Driver**, you must use the actually stored field names, such as **address.postal_code**.

If data mixes **address.postal_code** and **address.postalCode**, an index on one path does not automatically cover the other. Queries and aggregations may miss documents. Before blaming constructors for slow reads, check the **query plan, indexes, scanned document count, BSON schema, and filter criteria**.

Constructor binding happens mainly when converting query results into objects. Type mismatch errors can surface at the end of the query pipeline, after MongoDB has located the documents; do not confuse them with "the query returned no results."

In **ReactiveMongoTemplate** and reactive repositories, embedded object mapping still handles the same properties and constructors. The primary difference is that errors are emitted through the reactive publisher when reading and mapping occur, not that data mapping errors disappear.

## 18. Design Practices to Prevent Errors

When designing new embedded objects or refactoring old classes:

- **Keep constructor parameter names aligned with Java properties**. Use @Field for differences between Java and BSON; never rename parameters to match BSON names.
- **Compile with -parameters** for regular Java classes relying on constructor binding; verify metadata in the actual runtime artifact.
- **Choose creators explicitly** when a class has multiple constructors or factories.
- **Prefer intentional business invariants**. If old data might omit fields, decide on conversion rules before adding strict validation to constructors.
- **Plan migrations for legacy schemas**. When fields are renamed or change types, upgrade readers and data in coordination.
- **Test reading real BSON**. Fixtures should include both valid and invalid cases.
- **Keep logs informative**. Log record identifiers, field paths, BSON types, and root causes; avoid logging sensitive values.
- **Do not rely on adding a no-args constructor as a quick fix** when the root cause is schema or field-name mismatch.

### 18.1. When Should You Use a Custom Converter?

A custom converter fits when historical data has **multiple structures that cannot be mapped directly**. For example, address used to be a String, then a document, and later a list of addresses. A converter can normalize each shape before building the domain model.

Converters also carry costs:

1. Legacy data edge cases require thorough testing.
2. Read and write paths must align so fields are not accidentally dropped.
3. Silently turning invalid values into defaults can mask schema corruption.
4. Impact on query mapping and projections must be evaluated when using specialized mechanisms.

For classes with standard mapping, **matching property/parameter names and @Field** is usually simpler than a custom converter.

## 19. Hands-on Exercises

### Exercise 1: Missing -parameters

Given a regular Java class:

~~~java
public class Address {
    private final String city;
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }
}
~~~

**Question:** Java reflection prints arg0, arg1. What should you check before modifying MongoDB data?

**Suggested answer:** check whether the class was compiled with javac -parameters; inspect reflection isNamePresent or javap MethodParameters on the actual runtime artifact; verify Spring Data selects the right constructor. If metadata is missing, configure the compiler properly and rebuild the relevant classes.

### Exercise 2: Parameter Name Mismatch

~~~java
public class Location {
    private final String countryCode;

    public Location(String code) {
        this.countryCode = code;
    }
}
~~~

**Question:** why might enabling -parameters still not solve the error?

**Suggested answer:** -parameters only preserves the name **code**, it does not turn it into **countryCode**. Constructor binding needs to locate a matching persistent property. Rename the parameter to countryCode or use another explicit mapping strategy.

### Exercise 3: Java camelCase and BSON snake_case

MongoDB stores:

~~~javascript
{ address: { city: "Hue", postal_code: "530000" } }
~~~

In Java, the property is postalCode. Choose the appropriate parameter name and annotation.

**Suggested answer:** annotate property postalCode with **@Field("postal_code")**, and have the constructor accept parameter **postalCode**. The parameter name does not need to be changed to postal_code.

### Exercise 4: Legacy Data with Different Types

A collection has 40% of documents with a String address and 60% with an Object address. The new application only uses the Address class. What will you do?

**Suggested answer:** profile the data, design a reader supporting both shapes or a controlled migration, test against fixtures for both groups, and only then drop support for the old format. Do not assume changing the Java field type converts BSON automatically.

### Exercise 5: Null Embedded Object

The Address constructor calls Objects.requireNonNull(city), yet a document has address = {}. When reading, where can the failure occur?

**Suggested answer:** during Address construction via its constructor; city has no value and validation throws. Check real data and the requirement for city, rather than just adding -parameters.

### Exercise 6: Two-Way Testing

Write a test verifying that an Address with city and postalCode is written as fields city and postal_code, then read back. Why is an additional test reading a manually constructed BSON document necessary?

**Suggested answer:** a round-trip test verifies both directions under the current configuration; a raw BSON test ensures historical data and external producer contracts are also compatible. Using the same converter to both write and read can allow both sides to share the wrong field name while the test still passes.

## 20. Key Takeaways When Working with Constructors and Embedded Objects

1. **Constructor binding links parameter names to Java persistent properties**, after which Spring Data uses mapping metadata to read the corresponding BSON fields.
2. **-parameters preserves parameter names in bytecode** for regular Java classes; it neither creates nor alters MongoDB fields.
3. **@Field changes the BSON field name**, while standard constructor parameter names must match Java property names.
4. **@PersistenceCreator explicitly selects a constructor** in classes with multiple instantiation paths; it does not fix mismatched parameter names.
5. **Java records support immutable mapping via component/canonical constructors**, but do not exempt you from checking BSON schemas and nulls.
6. **Wrong field names, missing fields, nulls, and wrong types are distinct problems**. Do not try to solve all of them with a single compiler flag.
7. **Embedded objects and embedded arrays also go through the mapping pipeline**, so one bad element can fail reading the entire document.
8. **Testing with real MongoDB and legacy data** catches bugs that constructor unit tests or self-generated data cannot reveal.

Mastering constructor parameter names, the **-parameters** flag, and BSON data verification makes **SPRING_DATA_MONGODB** applications safer to read, write, and maintain embedded documents across MongoTemplate, repositories, and advanced data-access flows.
