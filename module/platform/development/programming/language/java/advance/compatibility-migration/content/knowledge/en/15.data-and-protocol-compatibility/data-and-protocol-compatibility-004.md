# JSON, XML and the impact of upgrading a serializer

In a Java application, upgrading the JDK or upgrading a serializer library is not merely replacing a dependency. A small change in how a Java object is converted into JSON/XML can make another application unable to read the message, break digital signatures, cause data loss on rollback, or prevent the system from decoding data saved many years ago.

The dangerous part is that most of these changes **do not cause compilation errors**. The `writeValueAsString(...)` or `marshal(...)` API still runs, HTTP returns a success status, yet the payload may change field names, date-time representations, element order, `null` values, number formats, XML namespaces, or how unknown fields are handled.

This lesson focuses on data and protocol compatibility in Java when upgrading a serializer: how to distinguish contract layers, common changes in Jackson, Gson, JSON-B, and JAXB/Jakarta XML Binding; designing contract tests; parser security; and a safe deployment process across multiple application versions.

## 1. What is a serializer and why does upgrading carry risk?

**Serialization** is the process of turning an object or data structure into a representation for transmission, storage, or exchange. **Deserialization** does the reverse, reading that representation and constructing values on the receiving side.

Example of a Java object:

```java
public record Customer(
        long id,
        String displayName,
        boolean active) {
}
```

Can be represented as JSON:

```json
{
  "id": 42,
  "displayName": "Minh",
  "active": true
}
```

Or XML:

```xml
<customer>
    <id>42</id>
    <displayName>Minh</displayName>
    <active>true</active>
</customer>
```

In the example above, JSON and XML are not the same protocol. They have different rules for data types, ordering, namespaces, and validation. However, both require a clear **wire contract**: which format is accepted, which fields are required, what each value means, and which version can read which version.

A serializer typically encompasses many behaviors:

- Discovering properties from fields, getters, record components, or annotations.
- Choosing field/tag/attribute names.
- Choosing which fields are ignored and which fields always appear.
- Converting numbers, dates, enums, collections, and nested objects.
- Generating or reading type metadata for polymorphism.
- Handling `null`, missing fields, unknown fields, and default values.
- Controlling charset, XML namespaces, escaping, and byte representation.
- Configuring security when reading untrusted input.

When upgrading a library, any of the points above can be affected by the new version, integration module, or configuration.

## 2. Four compatibility layers that must be checked separately

The word "compatibility" is very easy to overuse broadly. During migration, it should be divided into four layers:

| Compatibility layer | Question | Example |
|---|---|---|
| **Syntax / format** | Is the new payload still valid JSON/XML? | JSON is still parseable, XML is still well-formed. |
| **Schema / structure** | Do names, types, requiredness, ordering, and namespaces match the contract? | `customerId` is changed to `id`, `<item>` changes namespace. |
| **Semantics** | Does the read data preserve the same business meaning? | `null` differs from "not provided"; timezone changes the payment date. |
| **Byte-level** | Are the bytes identical when the receiver requires an exact match? | HMAC signature, ETag, hash, snapshot, canonical XML/JSON. |

The fact that two payloads are both syntactically valid does not mean they are structurally or semantically compatible.

Example:

```json
{"amount": 10.00, "currency": "VND"}
```

and:

```json
{"amount": 10, "currency": "VND"}
```

may represent the same numeric value in some systems; however, if the receiving side validates the decimal format, processes numbers using `BigDecimal` with a specific scale, or signs the raw bytes verbatim, these two representations can produce different behavior.

Conversely, whitespace differences between:

```json
{"id":1}
```

and:

```json
{
  "id": 1
}
```

normally should not cause errors with a standard JSON parser. If a consumer depends on spaces or line breaks, that is usually a poorly defined contract issue, unless both parties have intentionally committed to a specific byte representation.

## 3. Distinguishing backward, forward, and full compatibility

Suppose version V1 of a system produces the old payload, while V2 produces the new payload.

**Backward compatibility:** a V2 consumer can read data created by a V1 producer.

**Forward compatibility:** a V1 consumer can read data created by a V2 producer, in cases permitted by the contract.

**Full compatibility:** both directions are supported within the defined scope.

```text
                 V1 data     -------->  Consumer V2
                       backward compatibility

                 V2 data     -------->  Consumer V1
                       forward compatibility
```

For example, V1 has:

```json
{"id": 42, "name": "Minh"}
```

V2 adds:

```json
{"id": 42, "name": "Minh", "marketingOptIn": false}
```

A V2 consumer can usually read V1 data easily if there is a policy for missing fields. However, whether a V1 consumer can read V2 data depends on the unknown fields configuration: some deserializers ignore unknown fields, while others reject them.

In a rolling deployment system, V1 and V2 producers may coexist at the same time. Therefore, the policy is not just "being able to upgrade to the new JDK", but **being able to communicate with every version still active during the deployment window**.

## 4. Serializer changes that are not easily noticeable

| Change | Before/after example | Impact |
|---|---|---|
| Property naming | `displayName` → `display_name` | Consumer looks up the wrong field. |
| Inclusion policy | Includes `"nickname": null` → omits field | A field that is "present but null" becomes "absent". |
| Unknown property | Ignored → throws exception | Old consumers cannot read new payloads. |
| Enum format | `"PENDING"` → `"pending"` or number | Wrong mapping or rejected value. |
| Timestamp | Epoch millis → ISO-8601 | Different JSON number/string type; timezone may change. |
| Numeric coercion | `"100"` accepted as number → rejected | Historical data fails to parse. |
| Float precision | `1.0` → `1`; scientific `1E+7` | Breaks byte-signature or downstream parser. |
| Polymorphic metadata | `"@class"` → `"type"` | Subtype cannot be determined. |
| Object property order | Order changes | Snapshots or signatures on raw bytes fail. |
| XML namespace | No namespace → new URI | XPath/XSD/JAXB mappings no longer match. |
| XML empty/null | `<x/>` → omits `<x>` or `xsi:nil` | Nullable/optional semantics differ. |
| XML attribute/element | `id="42"` → `<id>42</id>` | Breaks XPath and XML schema. |
| Security defaults | Parser blocks DTD, untrusted type metadata | Legacy input may be intentionally rejected. |

Important point: *a behavioral change is not necessarily a library bug*. It may be a documented change or the consequence of a vulnerability fix. You need to cross-check the release notes and data contracts before deciding to retain old configuration.

## 5. JSON: where does the actual contract live?

JSON has basic types: object, array, string, number, boolean, and `null`. JSON itself does not map directly to Java types such as `BigDecimal`, `Instant`, `LocalDate`, or enums.

Therefore, simply saying "the API returns JSON" is not enough. You need to decide:

1. Is the field name fixed according to a specific case/naming strategy?
2. Which fields are required, allowed to be `null`, or allowed to be absent?
3. What are the range/precision limits for numbers?
4. Which timezone and string format does date/time use?
5. Are enums transmitted by name, business code, or number?
6. How are unknown fields and duplicate fields handled?
7. Is coercion allowed, for example accepting `"42"` instead of `42`?
8. Is the payload signed using raw bytes or canonical form?
9. Is there a version field or an API version path?

These rules should be concretized using JSON Schema, OpenAPI contracts, protocol documentation, or contract tests. Do not rely solely on "the current defaults of ObjectMapper" as the communication specification.

### 5.1. JSON objects do not guarantee semantic field order

In the data model, a JSON object is a collection of name/value pairs; field order should not be treated as carrying business meaning, unless there is a specific convention for byte representation. If display order needs to be preserved in some APIs, the serializer can be configured, but a compliant consumer should still look up fields by name.

For arrays, **element order is meaningful** and must be preserved accurately. Switching from `List` to `Set` and then outputting an array can cause the order to change unexpectedly.

### 5.2. Duplicate keys

A payload such as:

```json
{"role": "viewer", "role": "admin"}
```

has two keys with the same name. Different parsers have different handling policies (take first, take last, reject). If a payload passes through a gateway, service, and audit logger that use different parsers, this can become a security issue.

You should define a clear policy, prioritizing **rejecting duplicate keys in untrusted input** if the contract does not allow them. Do not assume that a new parser handles duplicate keys the same way as the old parser.

## 6. Jackson: controlling behavior instead of relying on defaults

Jackson is a popular JSON library in the Java ecosystem, consisting of `jackson-core`, `jackson-databind`, and many extension modules. A framework may configure Jackson on behalf of the application; for example, the ObjectMapper configuration provided by Spring Boot can differ from a manually instantiated ObjectMapper.

Choices to distinguish:

- Jackson version and transitive dependencies.
- `ObjectMapper` configuration and feature flags.
- Annotations on DTOs (`@JsonProperty`, `@JsonIgnore`, `@JsonInclude`...).
- Extension modules for Java time, optional types, or special data types.
- Framework-level customization, mixins, and custom serializers/deserializers.

### 6.1. Explicit DTO declarations

Example of a contract for an order:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;

@JsonInclude(JsonInclude.Include.ALWAYS)
public record OrderPayload(
        @JsonProperty("order_id") String orderId,
        @JsonProperty("total_amount") BigDecimal totalAmount,
        @JsonProperty("note") String note) {
}
```

The example using a Java record requires a JDK that supports records and a Jackson version that supports handling records. If the baseline JDK is older, you can use a POJO with correspondingly annotated constructors/getters.

`@JsonProperty` helps lock the wire name independently of the Java member name. `@JsonInclude(ALWAYS)` expresses the intent to always write properties within the scope handled by the serializer, including `null`; if the schema does not allow nullable values, they must be validated separately, and annotations must not be treated as schema validation.

### 6.2. Do not leave unknown-field configuration to chance

Example of a consumer that accepts new fields while still requiring old values to be valid:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class JsonReaders {
    public static ObjectMapper tolerantReader() {
        return new ObjectMapper()
                .configure(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                        false);
    }
}
```

This configuration is useful for forward compatibility if the API is designed on the principle that adding new fields does not break old consumers. However, accepting every unknown field can also hide typos or schema errors. For sensitive APIs or business command input data, you can choose a strict reader and explicit versioning.

**There is no single right policy for every flow.** Do not assume that the default of a Jackson version, framework, or project will stay the same forever. Record the policy in code/tests.

### 6.3. Java Time and timestamp formatting

Suppose the API requires timestamps in ISO-8601:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

With DTO:

```java
import java.time.Instant;

public record EventPayload(
        String eventId,
        Instant occurredAt) {
}
```

Example data:

```json
{
  "eventId": "evt-100",
  "occurredAt": "2025-06-01T12:30:00Z"
}
```

Do not treat all time types as equivalent: `LocalDate` has no timezone, `LocalDateTime` carries no offset, whereas `Instant` represents a point on the UTC timeline. If a converter uses the default timezone when converting data, the result may change when upgrading the JDK, JVM flags, or container environment.

### 6.4. Configuring ObjectMapper before sharing

`ObjectMapper` is typically reused and safe for concurrent operations once all configuration is completed before being put into use. Avoid changing shared configuration while multiple threads are serializing/deserializing. If two endpoints require different contracts, create separately configured readers/writers or separate mappers, rather than toggling features on a shared mapper across requests.

Example:

```java
ObjectMapper mapper = buildConfiguredMapper();

var strictWriter = mapper.writerFor(OrderPayload.class);
var reader = mapper.readerFor(OrderPayload.class);
```

`buildConfiguredMapper()` is an application-defined function for configuring the mapper at initialization. There is no requirement to use a single singleton for all data types if the schemas and security needs of the flows differ.

## 7. Null, missing, and default values: semantic differences

The following three states can differ:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": ""}
```

In a partial update API (PATCH), they can mean:

- **Missing:** do not change the field.
- **Null:** clear the current value.
- **Empty string:** set the value to an empty string.

However, this is a choice of the specific contract, **not** an automatic rule of every JSON API. A serializer upgrade that changes the inclusion policy from "write null" to "omit field" can cause business logic errors even though the client still parses the payload successfully.

Another risk is that Java primitives have defaults:

```java
public class AccountFlags {
    public boolean active;
}
```

When the `active` field is missing, its value may become `false` after binding if there is no validation. That does not prove the producer sent `false`. If you need to distinguish between "absent" and "false", use `Boolean` or a representation with explicit presence state, and validate according to the contract.

For public APIs, you need to decide presence on a per-field basis and create separate tests for missing, `null`, empty string, empty list, and default values.

## 8. Numbers and precision when upgrading a JSON serializer

JSON has only one number type; Java has many different types such as `int`, `long`, `double`, `BigInteger`, `BigDecimal`.

Common errors:

1. A JavaScript consumer receives a large 64-bit integer and loses precision when converting to a JS Number.
2. A new deserializer changes how `"42"` → `42` coercion works.
3. The serializer changes the representation of `1000.00` to `1000.0`, `1000`, or an exponent.
4. Java `NaN`/`Infinity` values are not standard JSON numbers; the serializer may throw an error, write a string, or use custom behavior.
5. Monetary fields pass through `double`, introducing rounding errors during calculation.

Example of an explicit contract:

```json
{
  "amount_minor_units": 125000,
  "currency": "VND"
}
```

Or using a decimal string:

```json
{
  "amount": "125000.00",
  "currency": "VND"
}
```

Both have pros and cons. What matters is that the producer and consumer agree on the wire type and conversion rules, rather than leaving it up to the serializer to decide.

With digital signatures, two numeric representations equivalent in value can still produce different bytes. If canonical JSON signing is needed, a unified canonicalization standard must be applied (for example, JSON Canonicalization Scheme, RFC 8785, within the scope supported by standard data), rather than merely relying on enabling a property-sorting flag.

## 9. Enums, field names, and naming strategy changes

Suppose we have an enum:

```java
public enum OrderStatus {
    PENDING,
    COMPLETED,
    CANCELLED
}
```

If the API writes `"PENDING"`, the enum name has become part of the wire contract. Renaming the Java constant to `WAITING` will change the data, even though the business function may be the same.

A more durable option is decoupling the wire code from the enum name:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING("pending"),
    COMPLETED("completed"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown status: " + code);
    }
}
```

When adding a new enum value, you must decide what old consumers should do: reject it, map it to an `UNKNOWN` state, or upgrade before the producer sends the new value. You should not automatically lump every unknown value into `PENDING` if doing so alters business logic.

Similarly, changing configuration from camelCase to snake_case can be a breaking change:

```json
{"customerId": 42}
```

versus:

```json
{"customer_id": 42}
```

If a field name needs to be changed, in the initial phase you can **read both the old and new names while writing only one canonical name**, and then switch the producer after the consumers have been upgraded.

## 10. Polymorphic JSON: compatibility and security

An API containing multiple subtypes may use a type discriminator:

```json
{
  "kind": "card",
  "lastFour": "4242"
}
```

In Jackson, type names can be declared explicitly:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPayment.class,
                name = "card"),
        @JsonSubTypes.Type(
                value = BankTransfer.class,
                name = "bank")
})
public interface PaymentMethod {
}
```

The `CardPayment` and `BankTransfer` classes are application-defined subtypes. The names `"card"` and `"bank"` should be treated as stable wire identifiers.

**Security risk:** do not enable default typing mechanisms that allow untrusted JSON to specify arbitrary Java class names. Historical deserialization vulnerabilities have shown that letting input choose object types can be dangerous, especially when dangerous gadgets exist on the classpath. Prefer an allowlist of permitted subtypes or a specific schema.

When upgrading Jackson, polymorphic typing and validation policies may be tightened. If old payloads can no longer be read, determine whether they relied on an insecure configuration or a supported contract. Do not disable security controls just to restore old behavior.

## 11. Gson and JSON-B: do not assume the same defaults as Jackson

In the Java ecosystem you may encounter Gson or JSON-B (Jakarta JSON Binding). These libraries have their own ways of discovering properties and handling annotations, date/time, and nulls.

Gson example:

```java
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

Gson gson = new GsonBuilder()
        .serializeNulls()
        .create();

String json = gson.toJson(
        new CustomerNote("C-1", null));
```

With the illustrative DTO:

```java
public record CustomerNote(String customerId, String note) {
}
```

`serializeNulls()` is an intentional choice; omitting it can produce a different payload. Support for records and other Java types depends on the actual library version.

With JSON-B, annotations such as `@JsonbProperty` or `JsonbConfig` configuration can be used to express the corresponding wire name and policy. Do not directly carry Jackson's `@JsonProperty` over to JSON-B and assume it will be processed the same way.

When switching to a serializer **from a different family** (Jackson → Gson or JSON-B), the migration scope is usually larger than a minor/patch upgrade within the same family. Treat this as a serialization contract change with its own tests, not a simple dependency swap.

## 12. XML has different rules from JSON

XML carries not only data structure, but also namespaces, attributes, element order, text content, entities, and schema validation mechanisms. Two XML documents can both be well-formed yet still be incompatible with an XSD or with an XPath used by a partner.

Example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<invoice xmlns="urn:example:invoice:v1" id="INV-1">
    <amount currency="VND">125000.00</amount>
    <paid>false</paid>
</invoice>
```

Elements that may belong to the contract:

- The root element is `invoice`, not `Invoice`.
- The namespace URI is `urn:example:invoice:v1`.
- `id` is an attribute, not a child element.
- `amount` carries the `currency` attribute.
- `paid` has lexical content permitted by the XSD.
- Element order may be constrained by `xs:sequence`.

If the new serializer replaces `<amount currency="VND">` with `<amount><currency>VND</currency>...`, the data may no longer be valid even though it is still well-formed XML.

### 12.1. Namespace prefix differs from namespace URI

Two documents:

```xml
<inv:invoice xmlns:inv="urn:example:invoice:v1"/>
```

and:

```xml
<x:invoice xmlns:x="urn:example:invoice:v1"/>
```

differ only in prefix while sharing the same namespace URI and element local name. A standards-compliant XML-aware consumer should normally distinguish elements by expanded name (namespace URI + local name), without depending on the prefix text.

However, if a system signs **raw bytes** or uses XPath without properly declaring namespaces, changing the prefix can still cause the system to fail. Therefore, XML semantic testing must be separated from byte-level testing.

### 12.2. Element order can be part of the contract

In a JSON object, field order should generally not be constrained. In XML, the order of child elements can be declared in XSD using `xs:sequence`:

```xml
<xs:sequence>
    <xs:element name="id" type="xs:string"/>
    <xs:element name="amount" type="xs:decimal"/>
</xs:sequence>
```

If JAXB marshalling changes element order, messages may be rejected by an XSD validator. Define `@XmlType(propOrder = {...})` or an appropriate schema binding, rather than relying on the reflection order of fields.

## 13. JAXB and migrating from `javax.xml.bind` to `jakarta.xml.bind`

JAXB used to be part of the Java EE modules bundled with some older JDKs. Starting in JDK 11, JEP 320 removed the JAXB modules from the JDK. When upgrading from JDK 8 to JDK 11+, an application using:

```java
import javax.xml.bind.JAXBContext;
```

needs to declare compatible JAXB API and runtime dependencies separately. In newer generations of Jakarta XML Binding, the Java package namespace moves to `jakarta.xml.bind`.

**Do not conflate the following two steps:**

1. Remove dependency on the *JDK-bundled* JAXB and switch to standalone JAXB dependencies while still using the appropriate `javax.xml.bind` API namespace.
2. Upgrade to the Jakarta XML Binding generation using `jakarta.xml.bind` and update imports, annotations, and runtime.

Step (2) can be a source/binary compatibility change for Java code, in addition to changes directly related to the XML wire format.

### 13.1. Explicit XML binding example

The following example illustrates the Jakarta XML Binding API:

```java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlAttribute;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
        name = "invoice",
        namespace = "urn:example:invoice:v1")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"amount", "paid"})
public class InvoiceXml {
    @XmlAttribute(name = "id")
    public String id;

    @XmlElement(
            name = "amount",
            namespace = "urn:example:invoice:v1")
    public java.math.BigDecimal amount;

    @XmlElement(
            name = "paid",
            namespace = "urn:example:invoice:v1")
    public boolean paid;

    public InvoiceXml() {
    }
}
```

This example shows how to fix the root, namespace, attributes, and element order. To satisfy the entire earlier schema, additional package-level namespace configuration, attributes on `amount`, validation, or adapters may be required. The illustrative DTO should not be assumed to be completely equivalent to every earlier XML example.

### 13.2. Marshalling and unmarshalling

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import java.io.StringWriter;

public final class XmlCodec {
    private final JAXBContext context;

    public XmlCodec() throws Exception {
        this.context = JAXBContext.newInstance(InvoiceXml.class);
    }

    public String write(InvoiceXml invoice) throws Exception {
        Marshaller marshaller = context.createMarshaller();
        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
        StringWriter out = new StringWriter();
        marshaller.marshal(invoice, out);
        return out.toString();
    }

    public InvoiceXml read(String xml) throws Exception {
        Unmarshaller unmarshaller = context.createUnmarshaller();
        return (InvoiceXml) unmarshaller.unmarshal(
                new StringReader(xml));
    }
}
```

`JAXBContext` is typically relatively expensive to initialize and can be reused according to implementation guidelines; `Marshaller` and `Unmarshaller` should not by default be shared concurrently across multiple threads. The example creates a new marshaller/unmarshaller per operation to avoid state contention.

If receiving untrusted XML, you must control the XML parser/source and external entities as described in the security section below; do not assume using JAXB automatically prevents XXE in all cases.

### 13.3. JPMS and reflection

On the module path, JAXB may need access to members for binding. A module defining DTOs may need to declare `opens` to the specific JAXB runtime:

```java
module com.example.invoice.xml {
    requires jakarta.xml.bind;

    opens com.example.invoice.xml.model
        to jakarta.xml.bind;
}
```

This is an illustrative pattern; the runtime module name and package read/open requirements depend on the actual JAXB implementation and classpath/module-path. If you encounter `InaccessibleObjectException`, identify the exact package, the module performing reflection, and the packaging structure before broadening access permissions.

## 14. XML: `null`, missing elements, and `xsi:nil`

Three XML fragments can carry different meanings:

```xml
<invoice/>
```

```xml
<invoice>
    <note/>
</invoice>
```

```xml
<invoice xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <note xsi:nil="true"/>
</invoice>
```

In XML Schema, whether an element can be omitted depends on `minOccurs`; whether `xsi:nil="true"` can be used depends on `nillable`. An empty element is not by default equivalent to `null`.

When upgrading JAXB or replacing an XML serializer, you should check:

- `@XmlElement(nillable = true)` and corresponding bindings.
- Default field values during unmarshalling.
- Compatibility of classes generated from XSD.
- `@XmlElementWrapper` for collections.
- How empty elements, whitespace text, and absence are distinguished.
- Namespace rules for nil and root elements.

If a partner provides an XSD, validate both old and new payloads; merely being able to parse the XML is not enough to confirm the contract.

## 15. XML: escaping, CDATA, and encoding

An XML serializer can represent the same character content in multiple ways:

```xml
<message>Tom &amp; Jerry</message>
```

or using CDATA:

```xml
<message><![CDATA[Tom & Jerry]]></message>
```

The two forms may be equivalent in text content after parsing, but they do not have identical raw bytes. An upgraded serializer may change escaping, line breaks, indentation, or whether CDATA is chosen.

To handle this properly:

- **XML semantic comparison:** parse into DOM/StAX or a model and compare the required nodes/attributes.
- **Schema comparison:** validate against the XSD.
- **Byte-level comparison:** use only when the protocol requires an exact match or involves digital signatures; in that case use appropriate XML Canonicalization rather than manual string concatenation.
- **Encoding:** read and write using the agreed-upon encoding; note that the XML declaration and the actual byte stream must match.

If XML data passes through multiple systems, be careful with line endings, BOM, whitespace in mixed content, entity expansion, and XML namespace prefixes. "Pretty-print" is not a neutral operation for every XML document, especially when whitespace is meaningful data.

## 16. Security: XXE and XML parser hardening

XML has DTDs, entities, and external references. With untrusted input, an insecurely configured parser can lead to **XML External Entity (XXE)** attacks, file access, SSRF, or resource exhaustion.

An example of a JAXP DOM parser with a cautious policy:

```java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import java.io.StringReader;

public final class SafeXmlReader {
    public static Document read(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);

        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }
}
```

The example uses common JAXP features; a specific parser provider might not support every feature/attribute. In a real application, if the required policy cannot be configured, it should **fail closed** rather than silently ignoring it. Also check schema validation, XSLT, XPath, StAX, or JAXB pipelines because other layers may also be able to access external resources.

Do not re-enable DTD/external entities just because a few legacy XML payloads cannot be read after upgrading a library. First verify whether the contract genuinely requires DTDs and look for safe alternatives. If support is strictly required, restrict the resolver or resource sources explicitly and have it security-reviewed.

## 17. JSON deserialization and security

JSON parsers do not have XXE in the same way XML does, yet still carry other risks:

| Risk | Example | Mitigation |
|---|---|---|
| Polymorphic type injection | Input specifies an arbitrary Java class. | Allow only listed subtypes or validate type IDs. |
| Excessive nesting | JSON with thousands of nested array/object levels. | Limit depth, payload size, and parser resources. |
| Huge strings/arrays/numbers | Very large input causes memory/CPU exhaustion. | Limit request size and parsing constraints. |
| Duplicate keys | `"role"` appears twice. | Define a policy to reject or handle explicitly. |
| Mass assignment | Deserializing requests directly into domain entities with sensitive fields. | Use dedicated input DTOs and allowlist updatable fields. |
| Lenient coercion | `"true"`, `1`, or empty string coerced into unexpected types. | Choose strictness per contract; validate data. |

A serializer update may change security defaults to mitigate these risks. When old data can no longer be read, determine whether the data violates the contract or the new security policy. Do not broadly remove guards without proving the need and assessing the risk.

## 18. Impact of the JDK, reflection, and the module system

Upgrading a serializer often happens alongside upgrading the JDK. Distinguish library issues from platform issues:

- **JDK 11:** JAXB is no longer bundled with the JDK per JEP 320; a separate dependency is required.
- **JDK 16/17 and JPMS:** strong encapsulation affects reflection libraries accessing unopened fields. Update the library or add appropriate module `opens`.
- **Java records:** older serializers may not yet support record components/constructors; a compatible library or another DTO is needed.
- **Date-time and locale:** the JDK and libraries may differ in default timezone/formatters. Use explicit formatting.
- **Default charset:** starting in JDK 18, JEP 400 standardizes UTF-8 for most APIs relying on the default charset; avoid relying on implicit encoding when reading/writing payloads.
- **Class loader/module path:** XML binding providers, Jackson modules, or SPIs may not be discovered as on the old classpath.

Example error:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module ... does not "opens ..."
```

Do not conclude that a serializer "does not support the new JDK" from this stack trace alone. The DTO may reside in a named module that does not open the required package, or a very old library may be attempting deep reflection into JDK internals. A durable fix is usually using a supported serializer version, placing appropriate annotations/accessors, and declaring module access accurately.

## 19. Libraries and dependency graph: upgrading one artifact may not be enough

An application may use:

- Jackson via a web framework.
- Gson in a secondary HTTP client.
- JAXB in SOAP integration.
- JSON-B in a Jakarta EE module.
- A separate serializer in cache, message broker, or persistence.

If you only upgrade `jackson-databind` while keeping `jackson-core` or the Java Time module on a different version, the dependency graph can become inconsistent. A framework may manage versions via a BOM; explicit application dependencies can override the BOM.

Before migration, inventory the **actually resolved** artifacts:

```bash
mvn dependency:tree
```

Or Gradle:

```bash
./gradlew dependencies
```

For a specific dependency module, you can inspect the version selection reason in Gradle using `dependencyInsight`. Do not infer from `pom.xml` or `build.gradle` that the runtime contains only the directly listed artifacts.

When changing a serializer major version, read the migration notes for the source and target versions, removed APIs, changes to security defaults, JDK baseline requirements, and module IDs. In particular, ensure that serializer/deserializer plugins and framework integrations are compatible with the core library.

## 20. Long-lived stored data is more dangerous than short-lived HTTP responses

An HTTP request can be tested immediately in staging. However, JSON/XML stored in databases, object storage, file archives, caches, or message queues can persist long after the source serializer has been upgraded.

Scenarios:

**Reading old with new:** V2 must be able to read all V1 data remaining on disk.

**Reading new with old during rollback:** after V2 writes data, can V1 still understand it? If not, rolling back code may leave the system unable to start or read data.

**Delayed consumers:** queues hold messages from old producers; new consumers cannot assume every message is already in the new schema.

**Cache:** serializer changes can make old cache entries unreadable. Cache key versioning, TTL, or an invalidation plan may be needed.

**Backup/restore:** data from years ago may contain fields, enums, or formats that have disappeared from current code.

Therefore, before upgrading, inventory where **payloads are persisted**, their maximum retention lifetime, and rollback constraints. Do not test only data newly written by the new serializer.

## 21. Schema evolution strategy: expand → migrate → contract

When a payload needs to change, a low-risk rollout approach uses three phases.

### Phase 1 — Expand

New consumers accept both old and new schemas; producers still emit the old schema. For example, the consumer reads both `customerName` and `displayName` but returns one canonical internal field.

With Jackson, alias-reading annotations can be used where appropriate:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerMessage(
        String id,
        @JsonProperty("displayName")
        @JsonAlias("customerName")
        String displayName) {
}
```

The example allows reading two names, while the serializer normally writes the canonical name `displayName`. Test against the Jackson version supporting records and annotations.

### Phase 2 — Migrate

Producers gradually switch to the new schema. Monitor consumers still using the old schema; convert stored data or set up controlled dual-read/dual-write when necessary.

### Phase 3 — Contract

Once no consumers or data stores require the old schema, remove aliases or legacy fields according to the versioning policy. Removal should have a deadline, owner, and metrics proving that the old path is no longer in use.

Do not simultaneously rename a field on the producer and remove the ability to read the old field in the same rolling deployment; the mixed window can break.

## 22. Golden fixtures: locking the contract at the real-data level

A suite of golden fixtures consists of representative payloads with expected results. It should include data **actually emitted by the old serializer**, not just handwritten payloads.

Suggested structure:

```text
fixtures/
├── json/
│   ├── order-v1-normal.json
│   ├── order-v1-null.json
│   ├── order-v1-unknown-field.json
│   ├── order-v1-large-number.json
│   └── order-v2-normal.json
├── xml/
│   ├── invoice-v1.xml
│   ├── invoice-v1-nil.xml
│   ├── invoice-v1-namespaced.xml
│   └── invoice-v2.xml
└── expected/
    ├── order-semantic.json
    └── invoice-semantic.json
```

For each fixture, record:

| Field | Purpose |
|---|---|
| Producer version | Know which serializer/configuration produced the data. |
| Schema version | Know which data contract the fixture follows. |
| Encoding | Avoid guessing from the environment. |
| Representative edge case | Null, large number, timezone, namespace, collection... |
| Expected semantics | Business values after parsing. |
| Expected rejection | Which cases must be rejected, along with the appropriate error type. |

Include **both valid fixtures and intentionally invalid fixtures**, especially for duplicate keys, unknown enums, XML external entities, deeply nested payloads, and missing required fields. These cases help verify that upgrading the library does not accidentally weaken security or alter validation policy.

## 23. Testing JSON structurally instead of verbatim string comparison

JUnit 5 example with Jackson:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class JsonWireContractTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void equivalentObjectsIgnoreWhitespaceAndFieldOrder()
            throws Exception {
        String left = "{\"id\":42,\"active\":true}";
        String right = """
                {
                  "active": true,
                  "id": 42
                }
                """;

        JsonNode expected = mapper.readTree(left);
        JsonNode actual = mapper.readTree(right);

        assertEquals(expected, actual);
    }
}
```

The example uses Java 15+ text blocks. On an older JDK baseline, replace text blocks with regular strings. This test is suitable when the contract cares about **JSON structure**, not raw bytes.

If the application signs payloads or the receiver requires exact bytes, a separate byte-level test is needed after agreeing on canonicalization. Comparing `JsonNode` is not sufficient to confirm that the signature on the original string remains valid.

### 23.1. Testing reading V1 data with V2

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CustomerBackwardCompatibilityTest {
    record CustomerV2(
            String id,
            String displayName,
            boolean marketingOptIn) {
    }

    @Test
    void canReadOldPayload() throws Exception {
        String v1 = """
                {"id":"C-1","displayName":"Minh"}
                """;

        CustomerV2 actual =
                new ObjectMapper().readValue(v1, CustomerV2.class);

        assertEquals("C-1", actual.id());
        assertEquals(false, actual.marketingOptIn());
    }
}
```

The test expresses a **contract assumption**: a missing boolean field is treated as `false`. If business logic requires distinguishing "not provided" from "false", the DTO needs the `Boolean` type or explicit validation, and the expected result must differ.

### 23.2. Byte-level testing when required

For contracts that sign raw payloads, store byte fixtures or verify hashes. Avoid using string snapshots to lock down incidental whitespace unless that is literally the signed contract. If using canonical JSON/XML, test both the canonicalizer and the serializer independently.

## 24. Testing XML with schemas and namespaces

For XML, a test should have at least two layers:

1. **Schema validation:** does the data conform to the partner's XSD?
2. **Semantic assertions:** after parsing, do elements/attributes have the right values, namespaces, and meaning?

Example of initializing an XSD validator using the JAXP API:

```java
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import java.nio.file.Path;

public final class XmlSchemaValidation {
    public static void validate(Path xsd, Path xml)
            throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Schema schema = factory.newSchema(xsd.toFile());
        Validator validator = schema.newValidator();
        validator.setProperty(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.validate(new StreamSource(xml.toFile()));
    }
}
```

The example restricts access to external DTDs/schemas. If the XSD has `xs:include` or `xs:import` outside the controlled file set, design an explicit resource resolver/valid source instead of allowing arbitrary network access. A parser provider might not support every property; fail closed when security policies cannot be applied.

When testing XML payloads, do not just compare `toString()`. If the serializer changes the namespace prefix or indentation while preserving semantics and XSD validity, that may be a permitted difference. Conversely, child element order in `xs:sequence` or `xsi:nil` can render the schema invalid even if the text looks nearly identical.

## 25. Compatibility between deployed components of different versions

A serializer change may fail only when the producer and consumer run different versions:

```text
     Producer V1  -------->  Queue  --------> Consumer V2
     Producer V2  -------->  Queue  --------> Consumer V1

     Database holds V1 and V2 records
                    |
               V2 application
                    |
           Roll back to V1?
```

Therefore, create a matrix:

| Producer / Stored data | Consumer V1 | Consumer V2 |
|---|---|---|
| V1 payload | Baseline | **Backward compatibility** needs to be tested. |
| V2 payload | **Forward/rollback compatibility** if required. | Normal operation. |

If a cell is not supported, it must be clearly documented in the deployment plan, and the deployment order must ensure no communication path requires that cell. For example, if a V1 consumer cannot read a V2 payload, all consumers must be upgraded before enabling the V2 producer.

### 25.1. Feature flags and schema versions

An explicit version can be added:

```json
{
  "schemaVersion": 2,
  "orderId": "ORD-100",
  "amount": "125000.00"
}
```

A version field helps route decoders when there genuinely are multiple schemas. However, not every minor change requires bumping the major version; if compatible expansion is possible via additive fields and readers already permit them, a single contract can support multiple versions without needing an entirely new path.

A version field also does not guarantee compatibility on its own: schema contracts, converters, and tests are still needed for existing data versions.

## 26. Process for upgrading a serializer in a Java application

### Step 1 — Inventory codecs and data

List every endpoint, queue topic, file, cache, and database column using JSON/XML. Identify which serializer handles each flow, annotation/custom module configurations, and actual dependency versions.

### Step 2 — Identify the contracts to preserve

For each payload, document field names, types, null/presence, enums, decimals, timestamps, namespaces, XML schemas, encoding, and signature rules. Distinguish public contracts from uncommitted formatting details.

### Step 3 — Record a baseline from the old version

Using representative data, generate golden fixtures from the running serializer. Save semantic expectations and raw bytes when a protocol requires exact bytes.

### Step 4 — Isolate the dependency change

Upgrade the serializer in a separate branch or environment, avoiding simultaneous upgrades of the framework, JDK, and schema whenever possible. If upgrading multiple things at once is unavoidable, document changes layer by layer and check the dependency graph.

### Step 5 — Run bidirectional test suites

Read V1 with V2, write V2 and read with V1 if rollback/rolling deployment requires it; verify JSON structure, XML XSD, semantic equivalence, and historical data.

### Step 6 — Test with untrusted input

Test duplicate keys, polymorphic type IDs, deeply nested payloads, XML DTDs, XXE, oversized numbers, overly long strings, and schema errors. Do not "fix" security tests by unconditionally enabling a lenient parser.

### Step 7 — Deploy in a compatible order

Usually consumers should be upgraded first, followed by switching producers. For stored data, apply expand/migrate/contract and schedule the removal of old schema support based on TTL/retention.

### Step 8 — Observe production

Monitor deserialization failures, validation errors, unknown fields, enum values, dead-letter messages, unreadable record counts, and payload sizes. Do not log sensitive information verbatim from messages.

### Step 9 — Controlled rollback

Before enabling the V2 producer, confirm whether V1 can read the newly written V2 data. If not, rolling back code alone is insufficient; a dual-read mechanism, converter, or corresponding data plan is needed.

### Step 10 — Remove temporary configuration

Once old data/consumers no longer exist, remove aliases, temporary compatibility parser flags, and unnecessary custom deserializers. Keep contract tests to detect unintended changes in the next library upgrade.

## 27. A sample serializer change record

```yaml
changeId: SER-MIG-014
component: "Order API JSON serializer"
oldRuntime: "Source JDK + serializer/framework version"
newRuntime: "Target JDK + serializer/framework version"
wireContract: "order-message-v2"
format: "application/json"
encoding: "UTF-8"
criticalFields:
  - orderId
  - amount
  - occurredAt
compatibility:
  readV1WithV2: required
  readV2WithV1: required-during-rollout
goldenFixtures:
  - order-v1-normal.json
  - order-v1-null.json
  - order-v1-large-number.json
expectedChanges:
  - "Add optional field sourceSystem"
securityChecks:
  - "Reject unsafe polymorphic type IDs"
  - "Bound payload size"
deployment:
  consumerFirst: true
  producerFlag: "orderSchemaV2"
  rollbackDataPlan: "Dual reader during transition"
owner: "Order service team"
```

The template above is an illustrative structure, not built-in metadata in Jackson/JAXB. Fill in accurate real-world information and link to the corresponding tests/contracts. Each change request should clearly state **permitted changes** and **prohibited changes**, avoiding vague statements like "serializer upgraded successfully".

## 28. Common misconceptions

**"If JSON parses, it is compatible."** Field names, data types, precision, or semantics may still be wrong.

**"Ignoring unknown fields is always good."** A tolerant policy fits additive schema evolution, but can mask input errors or weaken validation.

**"Changing an XML prefix is a breaking change."** It may only differ in text representation; check the namespace URI, XPath, and byte signatures.

**"Keeping the output byte-for-byte identical to the old one is always safest."** Without a byte-level requirement, locking down spacing and property order can block a completely valid upgrade.

**"Upgrading to JDK 11 automatically makes JAXB vanish from the data."** JEP 320 removes JAXB from JDK packaging; XML can still be read if appropriate API/runtime dependencies are added and contracts are verified.

**"Since HTTP uses UTF-8, stored files must also be UTF-8."** Files/archives may have been generated by an older system using a different charset; rely on metadata and actual bytes.

**"Rolling back the application will automatically roll back the data."** The new producer may have written a format that the old code cannot read; a separate data rollback plan is required.

**"Loosening reflection/parser permissions will fix it."** It might get past the first error while simultaneously opening vulnerabilities or depending on unsupported APIs.

**"Using @JsonProperty is enough for API compatibility."** You also have to check null handling, date/time, numeric coercion, enums, unknown-field policy, and other consumers.

## 29. Pre-release upgrade checklist

- [ ] Identified the exact serializer, version, transitive dependencies, and framework configuration.
- [ ] Inventoried all JSON/XML payloads, including long-lived stored data and queues.
- [ ] Published field names, types, null/presence, enums, and date/time formats.
- [ ] Verified that decimals/large integers do not lose precision.
- [ ] Checked JSON unknown fields, duplicate keys, coercion, and polymorphism.
- [ ] Checked XML namespace URIs, attribute/element mappings, and element order.
- [ ] Confirmed XML XSD validation and external entities/DTD policy.
- [ ] Specified explicit encoding for flows requiring stability.
- [ ] Checked the `javax.xml.bind`/`jakarta.xml.bind` transition if applicable.
- [ ] Handled reflection/`opens` permissions in JPMS where needed.
- [ ] Obtained golden fixtures actually generated by the old serializer.
- [ ] Tested reading old data with the new runtime.
- [ ] Tested the reverse direction if required by rolling deployment/rollback.
- [ ] Distinguished semantic comparison from byte-level comparison.
- [ ] Set up mechanisms to detect failed messages, dead letters, and parse errors in production.
- [ ] Planned the consumer/producer deployment order and data rollback plan.
- [ ] Clearly documented temporary compatibility configurations to be removed after migration.

## References

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON format and general rules.
- [RFC 8785 — JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785): canonical JSON when deterministic byte representation is needed.
- [W3C XML 1.0 Specification](https://www.w3.org/TR/xml/): XML structure, entities, and well-formedness.
- [W3C XML Namespaces](https://www.w3.org/TR/xml-names/): how to use namespace URIs and prefixes.
- [W3C XML Schema](https://www.w3.org/XML/Schema): structure definition and validation.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): impact of JDK 11 on JAXB and related modules.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change starting in JDK 18.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): controlling reflection access when upgrading the JDK.
- [Jackson Documentation](https://github.com/FasterXML/jackson-docs): annotations, data binding, and release compatibility.
- [Jackson Databind Project](https://github.com/FasterXML/jackson-databind): library versions and migration notes.
- [Gson Project](https://github.com/google/gson): Gson configuration and changes by release.
- [Jakarta XML Binding Specification](https://jakarta.ee/specifications/xml-binding/): XML binding standard and Jakarta namespace.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): parser configuration guide to prevent XXE.

## Conclusion

Upgrading a serializer can change JSON/XML protocols even when Java code still compiles and payloads still parse. Compatibility must be evaluated across all four layers: syntax, schema, semantics, and byte-level when signatures or canonicalization are required. For JSON, control null/presence, naming, enums, numbers, date/time, unknown fields, and polymorphic typing; for XML, pay attention to namespaces, attributes/elements, ordering, XSD, encoding, and XXE. In Java, migration also involves JDK 11 removing bundled JAXB, the Jakarta namespace, Java records, and JPMS reflection. A reliable process is to define the contract, maintain golden fixtures from real data, test both backward and forward compatibility, deploy consumers before producers when appropriate, and prepare data rollback before enabling a new schema.
