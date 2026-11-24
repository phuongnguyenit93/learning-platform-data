# Unknown Fields and Schema Evolution

In Spring Batch, JSON data is typically read into Java objects and passed through a processor and writer. When an upstream system changes its JSON structure, new files may contain fields unknown to the current application version, omit old fields, or change a property's data type. Without an explicit compatibility policy, the Job can fail mid-run or silently drop data.

An **unknown field** is a property appearing in JSON that has no corresponding mapping in the Java model in use. **Schema evolution** is the process of changing a schema's structure or semantics over time, such as adding fields, removing fields, renaming, changing types, or altering required rules.

With Spring Batch, unknown-field handling is typically decided at the JSON deserialization layer, such as Jackson used by **JsonItemReader** via **JacksonJsonObjectReader**. Spring Batch controls item-by-item and chunk reading; ObjectMapper decides whether a JSON object can be mapped into the model. Choose a policy matching your data contract, audit requirements, and ability to deploy source and target systems independently.

## 1. How Does a JSON Schema Change?

Suppose the initial version of the source sends JSON:

~~~json
[
  {
    "customerId": "C-001",
    "fullName": "An Nguyen",
    "email": "an@example.test"
  },
  {
    "customerId": "C-002",
    "fullName": "Binh Tran",
    "email": "binh@example.test"
  }
]
~~~

Initial Java model:

~~~java
public class Customer {
    private String customerId;
    private String fullName;
    private String email;

    // Getters and setters
}
~~~

Later, the source system adds a loyaltyTier field:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "email": "chi@example.test",
  "loyaltyTier": "GOLD"
}
~~~

The receiving application still uses the old Customer model. loyaltyTier is an unknown field to that model.

Common schema changes:

| Change | Example | Potential issue |
|---|---|---|
| Add field | Add loyaltyTier | Old consumer may reject unknown fields |
| Remove field | email removed | Consumer may receive null or fail if required |
| Rename field | fullName to displayName | Consumer may miss the old property |
| Change type | age from number to string | Conversion error |
| Change cardinality | address from object to array | Old model cannot map the new structure |
| Change semantics | amount changed from gross to net | JSON parses, but business result is wrong |
| Add enum value | Tier adds PLATINUM | Old enum may throw an error |
| Change nullability | email from required to nullable | Downstream logic may no longer hold |

Schema evolution is not just adding or removing properties. Changes in types, units of measure, business semantics, and validation rules can also make old or new data incompatible.

## 2. Unknown Fields in Jackson

Jackson maps JSON properties to fields, setters, constructor parameters, or structures declared via annotations in the Java model. When JSON contains an unrecognized property, Jackson can:

- Throw an error and stop deserialization.
- Ignore the unknown property.
- Route the property into an extension-fields container if the model supports it.
- Use a custom deserializer to apply custom rules.

ObjectMapper's default behavior depends on configuration and how Spring Boot/Spring Batch creates the mapper. In Jackson, the **FAIL_ON_UNKNOWN_PROPERTIES** feature determines whether an error is thrown when encountering an unhandled property. Do not infer behavior merely from using JsonItemReader; inspect the actual ObjectMapper passed to JsonObjectReader.

Example JSON with an unknown field:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "loyaltyTier": "GOLD"
}
~~~

The model only has customerId and fullName. If strict unknown-property handling is enabled, Jackson may throw UnrecognizedPropertyException on loyaltyTier. If lenient handling is enabled, that property is ignored on the Customer object.

## 3. Strict Mode: Rejecting Unknown Fields

Strict mode fits when the data contract requires producer and consumer schemas to stay in sync. A new field may signal that the producer deployed an incompatible version or the consumer received the wrong file type.

You can configure ObjectMapper:

~~~java
ObjectMapper objectMapper = new ObjectMapper();
objectMapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Or configure explicitly in Spring:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

When using strict mode:

- A new field not yet supported by the model causes the item to fail during deserialization.
- The Job can fail if the exception is unhandled.
- Producer and consumer detect schema skew early.
- Even an additive producer change can halt an older consumer.

Strict mode is useful for internal data flows with synchronized release processes, files following a fixed schema version, or data where unknown fields indicate serious errors. It is less suitable when a consumer must ingest multiple independent producer versions and adding fields is considered a compatible change.

## 4. Lenient Mode: Ignoring Unknown Fields

If producers frequently add optional fields and the consumer only needs part of the data, you can disable FAIL_ON_UNKNOWN_PROPERTIES:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

JSON can then contain fields undeclared by the model and still map cleanly:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "loyaltyTier": "GOLD",
  "preferredLanguage": "vi"
}
~~~

The Customer object still receives customerId and fullName; loyaltyTier and preferredLanguage do not appear in the object unless the model has somewhere to store them.

Lenient mode is beneficial when:

- Producer and consumer deploy independently.
- New fields are optional and do not affect current consumer logic.
- The consumer only needs a stable subset of properties.
- Files must keep processing when producers attach metadata.

However, ignoring unknown fields carries risks:

- New data can be lost without warning.
- The consumer may remain unaware that the producer changed the contract.
- A critical misspelled field can be silently ignored.
- The Job can complete while output lacks necessary information.

Therefore, lenient does not mean every schema change is safe. Record schema version, unknown field counts, or source metadata if you need to track schema evolution.

## 5. Configuring JacksonJsonObjectReader for JsonItemReader

In Spring Batch, **JsonItemReader<T>** reads a JSON array and emits each object as an item. Converting each JSON object into a Java type is delegated to a **JsonObjectReader<T>**, such as JacksonJsonObjectReader.

Example configuration:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}

@Bean
JacksonJsonObjectReader<Customer> customerObjectReader(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectReader<>(
            Customer.class, batchObjectMapper);
}

@Bean
JsonItemReader<Customer> customerJsonReader(
        Resource inputResource,
        JacksonJsonObjectReader<Customer> customerObjectReader) {

    return new JsonItemReaderBuilder<Customer>()
            .name("customerJsonReader")
            .resource(inputResource)
            .jsonObjectReader(customerObjectReader)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

There are two distinct kinds of strictness here:

- ObjectMapper strictness concerns JSON properties absent from the Java model.
- JsonItemReaderBuilder strictness concerns checking the input resource, such as whether the resource exists per reader behavior.

Do not confuse these two settings. Disabling FAIL_ON_UNKNOWN_PROPERTIES does not mean the reader accepts missing files or invalid JSON syntax. Conversely, strict resource checking does not determine how Jackson handles unknown properties.

Constructor and builder APIs may vary across Spring Batch/Jackson versions. Use the right overload in your application's dependencies and pass the same configured ObjectMapper; do not create another mapper that accidentally keeps strict defaults.

## 6. Which JSON Structure Does JsonItemReader Expect?

JsonItemReader typically reads an array of objects:

~~~json
[
  {
    "customerId": "C-001",
    "fullName": "An Nguyen"
  },
  {
    "customerId": "C-002",
    "fullName": "Binh Tran"
  }
]
~~~

Each object in the array is an item passed through JsonObjectReader.

If the source sends an envelope:

~~~json
{
  "schemaVersion": 2,
  "generatedAt": "2026-11-15T10:00:00Z",
  "data": [
    {
      "customerId": "C-001",
      "fullName": "An Nguyen"
    }
  ]
}
~~~

This is not the same structure as a top-level array. Do not assume JsonItemReader automatically locates the data property to read objects inside. You can use a preprocessing step, a custom JsonObjectReader/ItemReader, or a dedicated reader to handle the envelope. When choosing a solution, preserve the file's schemaVersion and metadata rather than discarding them accidentally.

## 7. Ignoring Unknown Fields Is Not Ignoring All JSON Errors

FAIL_ON_UNKNOWN_PROPERTIES only handles properties unrecognized by the model. It does not make Jackson ignore all deserialization errors.

Errors that can still occur:

- Syntactically invalid JSON, such as missing brackets or commas.
- Incompatible data types, such as an object receiving an array.
- Unparseable date strings.
- Missing required values when constructors or validation require them.
- Enums containing unsupported values.
- Custom deserializers throwing exceptions.
- JSON tokens whose structure does not fit the Java model.

Example:

~~~json
{
  "customerId": "C-003",
  "age": "not-a-number"
}
~~~

If age is an Integer, disabling FAIL_ON_UNKNOWN_PROPERTIES will not convert the string not-a-number into a number. That is a type conversion error.

Clear exception classification helps decide which errors can be skipped and which must stop the Job. Do not broadly configure skip for all JacksonException or Exception just to keep the Job running, because broken JSON syntax or mismatched types can render output data untrustworthy.

## 8. Retaining Unknown Fields Instead of Dropping Them

In some systems, consumers need to accept new fields even before understanding their semantics. Ignoring fields lets parsing succeed, yet loses data if objects are serialized or forwarded to another system.

You can use @JsonAnySetter to collect undeclared properties into a Map:

~~~java
public class Customer {

    private String customerId;
    private String fullName;
    private Map<String, JsonNode> additionalProperties = new HashMap<>();

    // Getters and setters for known fields

    @JsonAnySetter
    public void addAdditionalProperty(String name, JsonNode value) {
        additionalProperties.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getAdditionalProperties() {
        return additionalProperties;
    }
}
~~~

With @JsonAnySetter, Jackson passes unmapped properties into the method accepting key and value. Using JsonNode keeps value structure flexible when unknown fields can be strings, numbers, objects, or arrays.

You can persist extension fields into a JSON column, raw payload, or audit record for later processing. Enforce size limits and validate key names; never allow extension fields to overwrite business properties or drive SQL column names.

Another option is reading each item as a JsonNode first, extracting known fields, and preserving the remainder. This increases flexibility, but puts more responsibility on the application for type checking and validation.

## 9. Adding New Fields: Backward Compatibility

An additive change is usually backward-compatible if the new field is optional and older consumers can ignore it.

Version 1 example:

~~~json
{
  "customerId": "C-001",
  "fullName": "An Nguyen"
}
~~~

Version 2 adds an optional field:

~~~json
{
  "customerId": "C-001",
  "fullName": "An Nguyen",
  "preferredLanguage": "vi"
}
~~~

Older consumers can keep reading if unknown fields are ignored. Newer consumers can read both old and new files if preferredLanguage is treated as optional or has an appropriate default.

To preserve backward compatibility:

- Add new fields as optional whenever possible.
- Define meaningful defaults when fields are absent.
- Do not change the meaning of existing fields.
- Do not change existing data types without a migration plan.
- Check whether older consumers have strict unknown-property handling enabled.

Adding a field is not automatically always compatible. If the new field is required to compute accurate results, an older consumer ignoring it can produce wrong data even though parsing succeeds.

## 10. Removing Fields and Changing Nullability

If a producer stops sending a field, the consumer may receive null or a default value depending on property type and binding.

Old JSON example with email:

~~~json
{
  "customerId": "C-001",
  "email": "an@example.test"
}
~~~

New JSON drops email:

~~~json
{
  "customerId": "C-001"
}
~~~

If the model uses String email, the value is typically null when the property is absent, unless a constructor, initializer, or custom deserializer applies different logic. If the model uses primitive int, a missing property can keep Java's default 0; that 0 may be mistaken for real data.

For fields that may be missing:

- Use wrapper types like Integer instead of int if you need to distinguish missing/null from zero.
- Validate before the processor uses the value.
- Set explicit defaults if the default accurately reflects business rules.
- Distinguish a property absent from JSON from a property present with null if business logic requires it.

If a previously required field becomes optional, update validation and downstream logic. Do not merely change the Java type and assume every flow is compatible.

## 11. Renaming Fields with JsonAlias

Renaming properties is a change prone to breaking compatibility. For example, the producer renames fullName to displayName.

You can support both old and new names with @JsonAlias:

~~~java
public class Customer {

    private String customerId;

    @JsonAlias({"fullName", "displayName"})
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Under matching configuration, Jackson can accept fullName or displayName to populate the name property. When serializing, the output property name still follows JsonProperty/the primary property, rather than outputting all aliases.

When both names appear in the same object, define the desired behavior and test it. Do not allow producers to send both fullName and displayName with conflicting values without a precedence rule.

A safe strategy:

1. Consumer supports both old and new names simultaneously.
2. Producer starts sending the new name, optionally keeping the old name during transition if the contract requires.
3. Monitor usage of the old name.
4. Remove the old alias only after all producers have migrated and legacy data no longer needs support.

## 12. Changing Data Types

Changing a field's type is generally harder to keep compatible than adding a field. For instance, amount was previously a JSON number:

~~~json
{
  "amount": 125000.50
}
~~~

Later the producer sends amount as a string:

~~~json
{
  "amount": "125000.50"
}
~~~

Jackson may support some coercion depending on configuration, yet you should not rely on implicit conversion when the contract requires explicit types. Values like "unknown", empty strings, or comma-formatted numbers can cause failures or unexpected results.

Options:

- Keep JSON types stable in the contract.
- Use a custom deserializer if both formats must be supported.
- Read into an intermediate JsonNode/String and parse by defined rules.
- Version the schema when changes cannot be safely supported in the same model.

For example, a custom deserializer must explicitly handle null, number tokens, and string tokens; reject invalid values instead of defaulting to 0. For currency, use BigDecimal and control scale/rounding.

## 13. New Enums and Unknown Values

Suppose the old model has:

~~~java
public enum LoyaltyTier {
    STANDARD,
    SILVER,
    GOLD
}
~~~

The producer adds PLATINUM. When Jackson encounters PLATINUM, deserialization can fail because the current Java enum lacks a matching constant.

You can add a default enum value:

~~~java
public enum LoyaltyTier {
    STANDARD,
    SILVER,
    GOLD,
    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

And configure:

~~~java
objectMapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

When encountering an unknown enum value, Jackson can use the constant marked JsonEnumDefaultValue. Another option is READ_UNKNOWN_ENUM_VALUES_AS_NULL, though using null requires clear downstream validation.

Do not map every unknown enum to a valid business state such as STANDARD. That can alter business meaning. UNKNOWN is only suitable if the consumer can hold an unknown state and process it safely, such as recording it and awaiting an update.

## 14. Schema Version in Payload

For systems with multiple producers or breaking changes, include a schema version in the envelope:

~~~json
{
  "schemaVersion": 2,
  "generatedAt": "2026-11-15T10:00:00Z",
  "data": [
    {
      "customerId": "C-001",
      "displayName": "An Nguyen"
    }
  ]
}
~~~

schemaVersion helps the consumer identify the payload structure and select the matching mapping. It does not replace validation, but avoids guessing versions from whichever fields happen to appear.

You can define versioned models:

~~~java
public record CustomerV1(
        String customerId,
        String fullName) {
}

public record CustomerV2(
        String customerId,
        String displayName,
        String preferredLanguage) {
}
~~~

After reading the envelope, an adapter can convert CustomerV1 or CustomerV2 into a stable internal model:

~~~java
public record CustomerRecord(
        String customerId,
        String name,
        String preferredLanguage) {
}
~~~

The version conversion point is where defaults, renames, type conversions, and validation are applied. Downstream processors can work strictly with CustomerRecord without knowing every external schema version.

## 15. Handling Multiple Schema Versions in Spring Batch

Standard JsonItemReader reads an array using one JsonObjectReader with a fixed target type. If each file has only one schema version, you can select the matching reader/model based on JobParameters or file metadata.

Example reader configuration for a known version:

~~~java
@Bean
@StepScope
JsonItemReader<CustomerV2> customerV2Reader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        JacksonJsonObjectReader<CustomerV2> objectReader) {

    return new JsonItemReaderBuilder<CustomerV2>()
            .name("customerV2Reader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(objectReader)
            .saveState(true)
            .build();
}
~~~

If files can belong to multiple versions, use a preparation Step to read schemaVersion, validate it, and choose the appropriate flow/Step. Another approach is a custom reader reading the envelope and dispatching each object by version.

Do not use a single lenient ObjectMapper across all versions when versions have incompatible semantic or type changes. Ignoring unknown fields only addresses extra properties; it does not properly convert a different schema into the internal model.

## 16. Normalizing to a Canonical Model

A useful strategy is keeping the internal model stable and building adapters for each external schema:

~~~text
JSON schema v1 ----> V1 DTO ----\
                                \
JSON schema v2 ----> V2 DTO -----> Version adapter
                                  |
JSON schema v3 ----> V3 DTO ----/
                                  |
                                  v
                           Canonical model
                                  |
                                  v
                        ItemProcessor / Writer
~~~

The canonical model represents the business concepts needed by the Job, not necessarily matching the producer's JSON verbatim.

Benefits:

- External changes do not ripple across processors and writers.
- Multiple schema versions can be supported concurrently.
- Mappings and defaults are tested independently.
- Easy to record source version for auditing.
- Old aliases can be retired on schedule.

Do not turn the canonical model into a DTO containing every field from every producer. Keep only the data needed for business logic, and store extension payloads separately if out-of-contract data must be preserved.

## 17. Distinguishing Missing, Null, and Default

These three states can carry different meanings:

~~~json
{}
~~~

Property is absent.

~~~json
{"email": null}
~~~

Property is present with null value.

~~~json
{"email": ""}
~~~

Property is present with empty string.

In many simple Java models, the first two can both become null, while empty string remains "". If business logic must distinguish missing from explicit null, use an intermediate structure like JsonNode, a custom deserializer, or a wrapper representing presence.

Do not apply defaults mechanically. For instance, a missing quantity does not necessarily mean quantity equals 0; a missing status does not necessarily mean ACTIVE. Defaults must be defined in the contract or version adapter.

## 18. Unknown Fields and Business Validation

Successful deserialization only proves JSON can be converted into a Java object. It does not prove the object is valid under business rules.

For example, an object parses cleanly yet:

- customerId is empty.
- amount is negative.
- currency is unsupported.
- effective date is out of range.
- old and new fields contradict each other.

Separate the layers:

1. **JSON syntax:** is the payload valid JSON syntax?
2. **Deserialization:** can tokens map to the Java model?
3. **Schema validation:** do properties, types, and structure match the version?
4. **Business validation:** does the data satisfy business rules?
5. **Persistence validation:** does the data satisfy target system constraints?

An unknown field may be ignored at deserialization yet still require a warning at contract monitoring. Conversely, a known property may parse cleanly yet still be invalid in business terms.

## 19. Combining Unknown Fields with Skip Policy

If strict mode is enabled, an unknown field can cause an error when reading an item. You can configure skip for a specific exception if business rules permit dropping that item. However, evaluate whether a file full of unknown fields actually indicates the wrong schema version.

Example:

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerJsonReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(UnrecognizedPropertyException.class)
        .skipLimit(10)
        .build();
~~~

This illustrates exception classification; the actual exception may be wrapped by Spring Batch or JsonObjectReader depending on version and call path. Verify the root cause in tests before declaring skip rules.

Skipping an item with an unknown property drops the entire object from the pipeline, not merely that single field. If remaining fields are valid and processing should continue, lenient mapping or extension-field capture may be more suitable.

Do not skip unknown-field errors broadly if new fields may carry vital data or indicate the producer sent the wrong schema. Keep skip limits low and record failing files/versions/fields if taking this approach.

## 20. Monitoring Schema Drift

When consumers enable lenient mode, Jobs can keep running even as producers add properties. This helps availability, yet makes schema changes easy to miss. Have observability into how actual payloads evolve.

You can record:

- schemaVersion from the envelope.
- Producer name or source system.
- File ID, batch ID, and creation timestamp.
- Record counts per version.
- Unknown field names and occurrence frequencies.
- Failed deserialization item counts by exception type.
- Items missing critical fields.
- Unrecognized enum values count.

Logging raw payloads is unnecessary. Field names, versions, and counts are usually enough to detect drift; raw data should be stored in a protected area if investigation is needed.

Configure alerts when:

- A new schemaVersion appears.
- An unknown field appears for the first time.
- A required field suddenly goes missing.
- Deserialization failure rate spikes unusually.
- An unknown enum value appears.

Lenient mode should go hand in hand with schema monitoring when data has business or audit significance.

## 21. Testing Schema Evolution

Do not test only with the current version's JSON. Maintain representative fixtures for all versions the consumer commits to supporting.

Suggested test matrix:

| Case | Expected behavior |
|---|---|
| Old-version JSON, all fields present | Parse and mapping succeed |
| JSON with extra optional unknown field | Strict fails or lenient succeeds per policy |
| JSON with unknown field to preserve | Extension map retains exact key and value |
| JSON missing optional field | Default/null per contract |
| JSON missing required field | Validation/deserialization fails |
| Renamed field | Alias or version adapter maps accurately |
| Changed field type | Explicit conversion or clear failure |
| New enum | UNKNOWN/default or fail per contract |
| Explicit null | Handled differently from missing if business requires |
| Invalid JSON syntax | Item/Step fails per policy |
| Unsupported version | Stops early with clear message |

Example unit test for lenient unknown fields:

~~~java
@Test
void ignoresUnknownPropertyWhenLenientModeIsConfigured()
        throws Exception {

    ObjectMapper mapper = JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    Customer customer = mapper.readValue("""
            {
              "customerId": "C-003",
              "fullName": "Chi Le",
              "loyaltyTier": "GOLD"
            }
            """, Customer.class);

    assertEquals("C-003", customer.getCustomerId());
    assertEquals("Chi Le", customer.getFullName());
}
~~~

Strict mode test:

~~~java
@Test
void rejectsUnknownPropertyWhenStrictModeIsConfigured() {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    assertThrows(UnrecognizedPropertyException.class, () ->
            mapper.readValue("""
                    {
                      "customerId": "C-003",
                      "loyaltyTier": "GOLD"
                    }
                    """, Customer.class));
}
~~~

The test examples above assume the Customer model lacks loyaltyTier, has no @JsonAnySetter, and the mapper registers no other handler for unknown properties. With Spring Boot, test the exact ObjectMapper bean used by the application, as auto-configuration or modules may alter behavior.

## 22. Integration Testing with Spring Batch

ObjectMapper unit tests verify mapping, yet do not test JsonItemReader, chunks, skip policy, metadata, or restarts. Add Step integration tests with fixture resources.

Skeleton example:

~~~java
@SpringBatchTest
@SpringJUnitConfig(JsonImportTestConfiguration.class)
class JsonSchemaEvolutionStepTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void importsOldAndExtendedPayload() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "src/test/resources/customers-v1-plus-field.json", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(2, customerRepository.count());
    }
}
~~~

Fixtures must contain a valid array of objects belonging to schemas supported by the consumer. Beyond Job status, verify persisted values to ensure existing fields were neither dropped nor misassigned.

For restarts, keep the same identifying JobParameters and JobRepository across two launches. Confirm file/schema version stays stable, checkpoints restore, and writers create no duplicates.

## 23. Managing Versions and Producer/Consumer Rollout

A safe schema change usually requires a rollout plan:

1. Determine whether the change is additive or breaking.
2. Update consumers to read both old and new structures.
3. Deploy the compatible consumer first if producers release independently.
4. Update producers to the new contract.
5. Monitor versions, unknown fields, and mapping errors.
6. Remove old aliases or models after the compatibility window ends.

For breaking changes, consider explicit versioning instead of forcing one model to handle every shape. Store schemaVersion in JobParameters or JobExecution metadata for auditing; if version dictates data structure, it must remain fixed across restarts.

Do not alter mapping between a run and its restart in a way that causes the same checkpoint to be interpreted under a different schema. If reprocessing under a new schema is required, consider creating a new JobInstance and reconciling committed data.

## 24. Common Pitfalls

**Disabling FAIL_ON_UNKNOWN_PROPERTIES without monitoring drift:** Jobs may complete while new fields are silently dropped. Record schema versions and unknown fields when needed.

**Confusing unknown fields with wrong data types:** ignoring unknown properties does not handle known properties carrying wrong token types.

**Assuming JsonItemReader strictness means strict unknown fields:** resource strictness and Jackson unknown-property handling are two separate configurations.

**Ignoring business-critical fields:** successful parsing does not prove output correctness. Define which fields are optional and which are required.

**Using primitives for fields that may be missing:** default values 0/false can be mistaken for real data. Use wrappers and validation when needed.

**Renaming properties without aliases or version adapters:** legacy data may fail to map.

**Mapping new enums to a valid state with the wrong meaning:** use UNKNOWN or fail explicitly rather than defaulting to a state with different business semantics.

**Enabling lenient mode across all schema versions:** incompatible type or structural changes can still cause errors or corrupt data.

**Skipping all Jackson exceptions:** can bypass malformed JSON syntax or vital data errors. Classify exceptions and set limits.

**Not retaining old-version fixtures:** producer changes can silently break the consumer's ability to read archived files.

**Not pinning schema version on restart:** the same JobInstance may reread data under a different mapping from the first run.

## Conclusion

Unknown fields appear when JSON contains properties not yet mapped by the current Java model. With Spring Batch, JsonItemReader reads objects one by one while JacksonJsonObjectReader and ObjectMapper determine how those properties deserialize. Enable FAIL_ON_UNKNOWN_PROPERTIES to strictly detect schema drift; disable it when new fields are optional and consumers can safely ignore them; use @JsonAnySetter or JsonNode if extension fields must be preserved. Schema evolution also encompasses missing fields, renames, type changes, new enums, nullability, and business semantic shifts. Version breaking changes, normalize multiple versions to a canonical model, monitor schema drift, and test old/new fixtures at both mapper and Step integration levels. Parsing success is only the first step; data after processor and writer handling must still satisfy the business contract.
