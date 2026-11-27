# Type Hints, the `_class` Field, and Polymorphic Type Mapping

Spring Data Elasticsearch converts Java entities into JSON documents and converts retrieved documents back into Java objects. When a Java property has a concrete type, the converter can usually determine which class to instantiate from the property declaration. However, when a property is declared using an interface, abstract class, or superclass in an inheritance hierarchy, the converter needs extra information to identify the actual concrete class.

Spring Data Elasticsearch solves this with **type hints**. By default, the type hint is written into the `_class` field inside `_source`. The value is usually the fully qualified name of the Java class; it can be replaced with a stable alias using `@TypeAlias`. Type hints help the converter restore the runtime type, especially when documents contain polymorphic objects.

## 1. What Are Type Hints and `_class`?

Suppose an order can be paid by card or bank transfer. In Java, the `paymentMethod` property may be declared using the `PaymentMethod` interface, while the actual object is `CardPayment` or `BankTransfer`.

When writing a document, Spring Data needs to record a hint indicating which concrete class that object belongs to. A type hint is metadata added by Spring Data to the document. Under default configuration, this metadata looks like:

~~~json
{
  "_class": "com.example.payment.CardPayment",
  "lastFourDigits": "4242"
}
~~~

`_class` is the default type hint field name. It is a property inside JSON `_source` used by Spring Data, not a special Elasticsearch metadata field like `_id`, `_index`, or `_version`. Elasticsearch does not use `_class` to instantiate Java objects on its own; Spring Data reads this field during mapping.

Type hints typically appear on root documents and complex objects whenever the converter needs to preserve type information. The default value is usually the fully qualified class name, including package and class name.

## 2. Why Are Type Hints Needed?

For a property with a concrete type, the converter already knows the target class from the entity declaration:

~~~java
public class Product {
    private Brand brand;
}
~~~

When reading `Product`, Spring Data knows `brand` must be converted into `Brand`.

However, with an interface or abstract class, the declaration does not specify which implementation to instantiate:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class Order {
    private PaymentMethod paymentMethod;
}
~~~

`PaymentMethod` cannot be instantiated directly. If the document stores a `CardPayment`, the converter needs to know the actual class to construct the right object and assign it to `paymentMethod`. The type hint provides that information.

Type hints are also useful when a property is declared using a superclass while the document holds an instance of a subclass. Without type information, the converter might only know the declared type or be unable to restore the intended implementation.

## 3. Polymorphic Mapping Using `_class`

Example model with two payment methods:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters, and setters
}

public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters, and setters
}
~~~

An order entity containing a list of payment methods:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<PaymentMethod> paymentMethods;

    // Constructor, getters, and setters
}
~~~

When saving an `Order` containing a `CardPayment` and a `BankTransfer`, `_source` may have an illustrative structure such as:

~~~json
{
  "_class": "com.example.order.Order",
  "paymentMethods": [
    {
      "_class": "com.example.payment.CardPayment",
      "reference": "PAY-001",
      "lastFourDigits": "4242"
    },
    {
      "_class": "com.example.payment.BankTransfer",
      "reference": "PAY-002",
      "bankCode": "EXAMPLE"
    }
  ]
}
~~~

When reading the document, the converter uses each element's type hint to identify the corresponding implementation. The Java result can be a `List<PaymentMethod>` containing a `CardPayment` object and a `BankTransfer` object.

`@Field(type = FieldType.Nested)` in the example controls how Elasticsearch indexes the object array so conditions can be queried within the same element. It does not generate type hints. The two features are independent:

- `_class` helps Spring Data determine the actual Java class during data conversion.
- `FieldType.Nested` instructs Elasticsearch to preserve relationships between fields inside the same array element during indexing and querying.

If Elasticsearch's nested query semantics are not needed, an object property can use an appropriate `object` mapping. Choose `object` or `nested` based on query needs; do not choose `nested` merely because Java uses an interface or subclass.

## 4. Using `@TypeAlias` Instead of Fully Qualified Class Names

The default value of `_class` typically includes the package and class name. For example:

~~~json
{
  "_class": "com.example.payment.CardPayment"
}
~~~

This creates coupling between stored data and class names in source code. If you move the class to another package or rename the class, older documents still retain the old name and the converter may fail to locate the corresponding class.

`@TypeAlias` lets you assign a shorter, more stable name for the type hint. The annotation belongs to `org.springframework.data.annotation.TypeAlias`.

~~~java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("card-payment")
public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters, and setters
}

@TypeAlias("bank-transfer")
public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters, and setters
}
~~~

When writing a document, the type hint can use the alias:

~~~json
{
  "paymentMethods": [
    {
      "_class": "card-payment",
      "reference": "PAY-001",
      "lastFourDigits": "4242"
    },
    {
      "_class": "bank-transfer",
      "reference": "PAY-002",
      "bankCode": "EXAMPLE"
    }
  ]
}
~~~

Aliases reduce data coupling to Java package and class names. When refactoring packages or renaming implementations, you can keep the old alias so existing documents continue mapping to the new class.

### 4.1. Registering Type Aliases in the Mapping Context

`@TypeAlias` only works when Spring Data Elasticsearch knows about the annotated class. The mapping context must discover those entities to build the association between the alias and the corresponding `TypeInformation`.

Therefore, ensure polymorphic implementations are included in entity scanning or registered in the application's mapping context configuration. Simply adding the annotation to a class the application has never discovered does not guarantee the converter can resolve the alias when reading documents.

When an alias is unrecognized, data may fail to convert to the intended class. Check entity scanning/registration and ensure aliases are unique within the mapping context.

## 5. Type Hints at Root Documents and Nested Objects

Type hints can appear at multiple levels of `_source`:

~~~json
{
  "_class": "order-v1",
  "customer": {
    "_class": "individual-customer",
    "fullName": "Nguyen An"
  },
  "paymentMethods": [
    {
      "_class": "card-payment",
      "lastFourDigits": "4242"
    }
  ]
}
~~~

In this example:

- The root-level type hint identifies the stored entity type.
- The type hint in `customer` identifies the actual customer object implementation if the property is declared using a superclass/interface.
- The type hint in each `paymentMethods` element identifies the corresponding implementation for that element.

Not every field needs a type hint. Simple values such as strings, numbers, booleans, or dates already have clear types from the mapping and do not need a separate Java class identifier. Type hints matter for entities and complex objects, especially when the runtime type may differ from the declared type.

## 6. Distinguishing `_class` from Business Fields and Elasticsearch Mapping

`_class` is metadata serving Spring Data's object conversion. It should not replace a business field such as `paymentType`, `customerType`, or `documentKind`.

For instance, if the application needs to filter orders paid by card, store an explicit, meaningful business field:

~~~json
{
  "paymentType": "CARD",
  "paymentMethods": [
    {
      "_class": "card-payment",
      "lastFourDigits": "4242"
    }
  ]
}
~~~

The `paymentType` field can be declared as `keyword` and used in queries, aggregations, or reports. `_class` reflects the current Java structure and can change during code refactoring; thus, it is not a stable business data contract.

Nor is `_class` a `type` field in an Elasticsearch mapping. A mapping defines how fields are indexed, such as `keyword`, `text`, `object`, or `nested`. A type hint merely tells Spring Data how to construct Java objects from `_source`.

When Elasticsearch uses dynamic mapping, the `_class` field may be recognized as a string field. If the mapping sets `dynamic: strict`, every field written into a document must be declared beforehand; in that case, either include `_class` in the mapping or configure type hints appropriately for the Spring Data version in use. If `dynamic: false`, the field is not indexed yet can still reside in `_source` for the converter to read.

Example explicit mapping declaration for type hints and polymorphic fields:

~~~json
{
  "mappings": {
    "properties": {
      "_class": { "type": "keyword" },
      "paymentMethods": {
        "type": "nested",
        "properties": {
          "_class": { "type": "keyword" },
          "reference": { "type": "keyword" },
          "lastFourDigits": { "type": "keyword" },
          "bankCode": { "type": "keyword" }
        }
      }
    }
  }
}
~~~

Declaring `_class` as `keyword` is useful if you need to include the field in an explicit mapping or inspect type hint values. Typically, applications do not need to query by `_class` for business logic.

## 7. What Happens When a Type Hint Is Missing or Unreadable?

The outcome depends on the property's declared type and the remaining data in `_source`:

| Scenario | Possible Behavior |
| --- | --- |
| Property declared with concrete class and `_class` is absent | The converter can use the declared type to build the object. |
| Property declared with interface/abstract class and `_class` is absent | The converter does not know which implementation to instantiate; reading may fail. |
| `_class` contains an unresolvable class name or alias | The converter cannot map the type hint to a known Java type. |
| `_class` points to a deleted or relocated implementation | Old documents may become unreadable without an alias or compatibility strategy. |
| `_class` is filtered out of `_source` results | The converter loses the type information needed for polymorphic properties. |

When encountering conversion errors, inspect `_source` first, then check the property's declared type, aliases, and the list of registered entities. Do not work around errors by changing every property to `Object`, as doing so loses strong typing and forces the application to handle conversion manually.

## 8. Source Filtering and Type Hints

Elasticsearch allows returning only a subset of `_source` to reduce payload size. However, if results contain polymorphic properties, filtering out `_class` can prevent Spring Data from knowing which concrete class to instantiate.

For example, the following query retrieves only data fields without the type hint:

~~~json
{
  "_source": [
    "paymentMethods.reference",
    "paymentMethods.lastFourDigits"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

If the application maps this result into `Order` and `paymentMethods` is declared with `PaymentMethod`, the converter may fail to restore the implementation. When using source filtering, retain the necessary `_class` paths, such as `paymentMethods._class`, alongside the data fields you want to read.

Do not apply source filtering mechanically to every repository. If using projections or DTOs that do not require polymorphic mapping, you can intentionally omit type hints; if mapping back to the original entity, retain the metadata the converter needs.

## 9. Class Changes and Already Stored Data

Default type hints containing full class names mean renaming packages or classes can affect older data. For example:

~~~text
Before refactoring:
com.example.payment.CardPayment

After refactoring:
com.acme.checkout.payment.CardPayment
~~~

Previously saved documents still contain the old name. When reading, the current mapping context may not find the corresponding class.

There are several ways to manage changes:

1. Use stable `@TypeAlias` values from the start for types with long data lifecycles.
2. When refactoring, preserve the old alias and map it to the new implementation.
3. If fully qualified class names were already written into data, perform a data migration/reindex or adopt a compatibility strategy to read old names.
4. Test reading old documents before deploying the new code version.

Example preserving an alias across a refactor:

~~~java
@TypeAlias("card-payment")
public class CardPaymentV2 implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters, and setters
}
~~~

Old documents with `_class: "card-payment"` can still map to the new class if the mapping context has discovered that alias and the data structure is compatible. If old class names were written directly into `_class`, adding a new alias does not automatically change values inside old documents; plan inspection and migration accordingly.

## 10. When Should Type Hints Be Kept or Disabled?

For entities with polymorphic properties, type hints are usually necessary so the converter can restore the right runtime type. If all properties have concrete types, the schema is stable, and the application does not need to store class info, you can consider minimizing or disabling type hint writing to keep `_source` leaner.

Some Spring Data Elasticsearch versions provide options to configure type hint writing at the `@Document` level or via the mapping converter/type mapper. APIs and scope of impact depend on the library version; check the documentation for the exact version you use before changing this.

Before disabling type hints, confirm that:

- There are no interface or abstract class properties needing implementation restoration.
- There are no polymorphic nested objects relying on type hints.
- Both existing and new documents can be converted using the current declared types.
- The mapping is not in `strict` mode conflicting with an emitted `_class` field.
- Active source filters, projections, and queries do not depend on type hints.

If you want to customize the type hint field name or class mapping behavior, Spring Data can be configured via a type mapper/mapping converter. This is a mapping-layer change; maintain compatibility with older documents and any other applications reading the same index.

## 11. Complete Example with `@TypeAlias`

Implementation classes using stable aliases:

~~~java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("card-payment")
public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters, and setters
}

@TypeAlias("bank-transfer")
public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters, and setters
}
~~~

Root entity:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
@TypeAlias("order-v1")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<PaymentMethod> paymentMethods;

    // Constructor, getters, and setters
}
~~~

When writing the entity, Spring Data uses `id` as Elasticsearch's `_id` metadata; type hints for the entity and polymorphic elements are written into `_source`. When reading, the converter resolves the aliases `order-v1`, `card-payment`, and `bank-transfer` into classes discovered by the mapping context.

As a result, business code can work against the `PaymentMethod` interface, while concrete objects are accurately restored when reading from Elasticsearch.

## 12. Design and Verification Workflow

When designing a mapping with polymorphic types, follow this sequence:

1. Identify which properties truly require polymorphism; only use interfaces or abstract classes when multiple valid implementations exist.
2. Decide whether storing type hints is needed to restore implementations.
3. Use stable `@TypeAlias` values for classes with long-lived data or likely package/class refactors.
4. Ensure implementations are discovered by the mapping context.
5. Choose the Elasticsearch field type `object` or `nested` based on query needs, independent of type hints.
6. Check the mapping if the index uses `dynamic: strict`, and ensure `_class` is not stripped from `_source` in flows requiring entity restoration.
7. Create documents with each implementation, read them back via repository/`ElasticsearchOperations`, and verify runtime classes.
8. Test reading old data after changing aliases, packages, or type mapper configuration.

Type hints and `_class` bridge Java object structures and JSON documents. They enable Spring Data Elasticsearch to restore concrete types when properties are declared as supertypes or interfaces. Using stable aliases, registering all entities, and retaining type metadata in `_source` when needed ensures data remains readable across code changes.
