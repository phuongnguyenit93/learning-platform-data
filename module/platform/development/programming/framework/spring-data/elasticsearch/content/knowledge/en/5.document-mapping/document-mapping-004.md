# @Setting, @Mapping, and Loading Configuration from Resources

In Spring Data Elasticsearch, a document class describes Java data stored in Elasticsearch. Beyond data fields, an index also requires **settings** and a **mapping** to define how documents are stored, analyzed, and searched. Spring Data Elasticsearch allows declaring these two parts using the **@Setting** and **@Mapping** annotations, while loading configurations from JSON files placed in the application's resources.

This lesson uses a **products** index as an example. Product names require full-text search, SKU codes and categories require exact matching, prices require range queries, and creation dates need to be recognized as date types. We will separate index configuration from Java code so it is easier to manage and modify.

## 1. Distinguishing Settings and Mapping

Settings and mapping both belong to an index's configuration, but they solve two different problems.

**Settings** configure how Elasticsearch organizes and processes the index. Common settings include:

- Number of primary shards and replicas.
- Refresh interval, i.e., how often Elasticsearch makes new data searchable.
- Analyzers, tokenizers, and token filters used during text analysis.
- Options related to index storage and data processing.

**Mapping** defines document structure and the data type of each field. Mapping tells Elasticsearch which fields are text, exact-match values, numbers, dates/times, or other types. It can also attach analyzers to text fields.

For example, if the **name** field is **text**, Elasticsearch analyzes its content into tokens for full-text search. If the **category** field is **keyword**, Elasticsearch preserves the exact value for exact filtering or grouping results. Choosing the wrong type can cause queries to return unexpected results.

| Aspect | Settings | Mapping |
|---|---|---|
| Purpose | Configure index behavior and processing | Declare document field types and structure |
| Examples | Shard count, replicas, refresh interval, analyzer | text, keyword, long, date, scaled_float |
| Related components | Analyzer, tokenizer, filter | Properties, field type, format, analyzer |
| When applied | On index creation; some settings can be changed later per Elasticsearch rules | On mapping creation; many field type changes require a new index |

Settings and mapping must be consistent with one another. If the mapping specifies an analyzer named **product_name_analyzer**, the settings must declare that analyzer. Otherwise, Elasticsearch will report an error when creating the mapping or index.

## 2. Organizing Configuration Files in Resources

JSON files can be placed in **src/main/resources** with the following structure:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/catalog/
    │       ├── Product.java
    │       └── ProductRepository.java
    └── resources/
        └── elasticsearch/
            ├── settings/
            │   └── products-settings.json
            └── mappings/
                └── products-mapping.json
~~~

Files under **src/main/resources** are included on the classpath when the application is packaged. Thus, the application can read them both when running from an IDE and when running from a JAR, provided the path is declared accurately.

In annotations, paths typically start with **/**, relative to the classpath root. For example:

- **/elasticsearch/settings/products-settings.json**
- **/elasticsearch/mappings/products-mapping.json**

Directory and file names must match exactly, including uppercase and lowercase letters when running on case-sensitive filesystems.

## 3. Declaring Settings in a JSON File

Create the file **src/main/resources/elasticsearch/settings/products-settings.json**:

~~~json
{
  "index": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "1s",
    "analysis": {
      "analyzer": {
        "product_name_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  }
}
~~~

Configuration explanation:

- **number_of_shards** specifies the number of primary shards for the index. This is a design decision that must consider data volume and workload; do not blindly copy example values for every environment.
- **number_of_replicas** specifies the number of replica copies per primary shard. A value of `0` is often convenient for single-node development environments; operational environments must consider availability and resources.
- **refresh_interval** sets the refresh cycle. A shorter interval makes new documents appear in search sooner, though it may increase write processing overhead.
- **analysis.analyzer** declares a custom analyzer named **product_name_analyzer**.
- **tokenizer: standard** splits text into tokens according to the standard tokenizer rules.
- **lowercase** converts tokens to lowercase.
- **asciifolding** converts many accented characters into their ASCII equivalents, useful for some accent-insensitive search cases. Test your application's languages and search requirements before choosing this filter.

The analyzer is named in settings so the mapping can reference it. Multiple analyzers, tokenizers, and filters can be declared if the application needs different analysis strategies for different fields.

Shard settings and certain other settings have specific rules for modification. For example, the primary shard count cannot be arbitrarily changed directly on an existing index. Determine appropriate settings before creating the index and plan data migration if changes are needed later.

## 4. Declaring Mapping in a JSON File

Create the file **src/main/resources/elasticsearch/mappings/products-mapping.json**:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "product_name_analyzer",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "description": {
      "type": "text",
      "analyzer": "standard"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

In the file above:

- **sku** uses **keyword** because SKU codes typically require exact matching.
- **name** uses **text** and the analyzer declared in settings for full-text search.
- **name.keyword** is a multi-field, allowing the same product name content to be used for exact filtering, sorting, or grouping.
- **category** uses **keyword** to filter by category.
- **description** uses **text** to search description content.
- **price** uses **double** to store floating-point numeric values in the example.
- **createdAt** uses **date**, accepting date/time strings in the specified format or epoch milliseconds.

The mapping file here directly contains the **properties** object. This is the mapping content passed to Spring Data Elasticsearch's mapping creation operation; do not wrap it inside a **mappings** object as you would when writing a full index creation REST API request.

The mapping must describe the exact field names that the application writes into documents. For example, Java uses the **createdAt** property, so the mapping also declares **createdAt**. If the application uses field-renaming rules during data conversion, names in the mapping must match the actual names stored in Elasticsearch.

**Double** is convenient for examples, but it is not optimal for all monetary data because binary floating-point numbers can have representation inaccuracies. For values requiring decimal precision, consider storing amounts in the smallest unit as integers or using **scaled_float** mapping with an appropriate scaling factor; in that case, synchronize the Java type, annotations, and JSON mapping.

## 5. Attaching @Setting and @Mapping to the Document Class

Spring Data Elasticsearch provides the **@Setting** and **@Mapping** annotations in the **org.springframework.data.elasticsearch.annotations** package. These two annotations let you specify resources containing index configuration.

Example **Product** class:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Mapping;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = true)
@Setting(settingPath = "/elasticsearch/settings/products-settings.json")
@Mapping(mappingPath = "/elasticsearch/mappings/products-mapping.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text, analyzer = "product_name_analyzer")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    public Product() {
    }

    // Constructors, getters, and setters omitted to focus on mapping.
}
~~~

Meaning of the annotations:

- **@Document(indexName = "products")** specifies the index represented by the document class.
- **createIndex = true** allows Spring Data Elasticsearch to create the index if it does not exist yet during metadata/repository initialization according to the application configuration.
- **@Setting(settingPath = "...")** specifies the settings file to load from the classpath.
- **@Mapping(mappingPath = "...")** specifies the mapping file to load from the classpath.
- **@Id** maps the Java identifier property to Elasticsearch's **_id**.
- **@Field** declares field type metadata for Spring Data.

In the example, the JSON mapping is the detailed configuration of the index. The **@Field** annotations on the Java class express mapping intent in source code; they must remain consistent with the JSON file. If JSON specifies **name** as **text** with a custom analyzer, the annotation should also specify the same analyzer, e.g., **@Field(type = FieldType.Text, analyzer = "product_name_analyzer")**. When using an external mapping as the primary configuration source, ensure the field types in JSON are the actual types used by Elasticsearch.

Do not declare the same field in two conflicting ways. For instance, if JSON specifies **price** as **scaled_float** while Java code describes that field with a different type, the development team will struggle to determine which configuration is intentional. Agree on one primary configuration source, then keep Java metadata compatible with it.

## 6. Loading Configuration and Creating the Index

When Spring Data Elasticsearch needs to create an index for a document class, class metadata is used to retrieve index info, settings, and mapping. The two paths in **@Setting** and **@Mapping** allow Spring Data to load content from the respective resources.

When you want proactive control over when the index is created, you can use **ElasticsearchOperations** and **IndexOperations**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

**indexOps(Product.class)** obtains the index operations object based on the **Product** class metadata. **exists()** checks whether the index already exists. **createWithMapping()** creates the index with the settings and mapping declared for the document class.

You can call **initialize()** from a component executed at application startup, such as **ApplicationRunner** or **CommandLineRunner**. If the application already enables repository auto-index creation, choose a single place to manage initialization to avoid duplicate index creation operations.

Example integration with **ApplicationRunner**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ElasticsearchInitializer implements ApplicationRunner {

    private final ProductIndexInitializer productIndexInitializer;

    public ElasticsearchInitializer(
            ProductIndexInitializer productIndexInitializer) {
        this.productIndexInitializer = productIndexInitializer;
    }

    @Override
    public void run(ApplicationArguments args) {
        productIndexInitializer.initialize();
    }
}
~~~

In real applications, clearly define which component is responsible for index creation. For systems where indexes are managed by deployment tools or a separate migration process, you can set **createIndex = false** and not auto-create indexes from the application. In that case, the deployment process must create the index with the correct settings and mapping before the application writes data.

## 7. Use Mapping from Annotations or from Resource Files?

Spring Data Elasticsearch can build mappings based on document class metadata, such as **@Field**, or load explicit mappings from the resource specified by **@Mapping**.

Using mapping from annotations is usually suitable when:

- The document structure is simple.
- The mapping has few special options.
- You want to keep field type descriptions close to the Java properties.
- There is no need to manage complex analyzers or mapping configurations.

Using a separate mapping file is usually suitable when:

- The mapping has many fields and multi-fields.
- You need to declare analyzers, normalizers, or specialized Query DSL options.
- You want to separate index configuration from Java classes.
- You need to review and manage Elasticsearch configuration as a distinct resource.

Similarly, **@Setting** can point to a JSON file to declare analyzers, tokenizers, filters, and other settings. Separating files makes configurations easier to read and makes changes easier to control.

Do not declare the same field in two conflicting ways. Agree on one primary configuration source, then keep Java metadata compatible with it.

## 8. Verifying Configuration After Creating the Index

After the index is created, you can inspect settings and mappings using Elasticsearch Dev Tools or the REST API.

Read settings:

~~~http
GET /products/_settings
~~~

Read mapping:

~~~http
GET /products/_mapping
~~~

In the response, verify the following points:

- The **products** index has been created.
- **number_of_shards**, **number_of_replicas**, and **refresh_interval** have the expected values.
- The **product_name_analyzer** analyzer is declared.
- The **name** field uses that analyzer.
- The **name.keyword** field has type **keyword**.
- The **category** field is **keyword**.
- The **price** field has type **double**.
- The **createdAt** field is **date** with the declared format.

You can test a search analysis request to confirm the analyzer works:

~~~http
POST /products/_analyze
{
  "analyzer": "product_name_analyzer",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch returns the list of tokens after analysis. This is a useful way to verify that the tokenizer and filters are operating as configured.

If the mapping result is not as expected, check the resource paths, JSON content, and when the index was created. Reading the actual mapping from Elasticsearch is how you confirm the configuration has been applied, rather than just checking annotations in Java code.

## 9. Changing Settings and Mappings After the Index Already Exists

An important point is that **@Setting** and **@Mapping** are used during index creation. Once the index already exists, editing JSON files or annotations does not automatically update the running index structure.

Cases can be distinguished as follows:

- Some settings can be changed directly via Elasticsearch's update settings API.
- Some settings only take effect upon index creation or require closing the index before updating.
- Changing the data type of a mapping field usually cannot be done directly on an index that already contains data.
- Changing analyzers or text analysis rules usually requires creating a new index and reindexing data to apply consistently.

Common workflow when significant mapping changes are needed:

1. Create a new index, such as **products-v2**, with the new settings and mapping.
2. Use reindex or an appropriate synchronization process to transfer documents from the old index to the new one.
3. Verify document counts, mapping, and search results on the new index.
4. Switch aliases or application configuration to the new index.
5. Delete the old index only after confirming the transition is complete and retention requirements are met.

In systems requiring continuous deployment, consider using an alias as a stable index name for the application. Each time a major mapping change occurs, the application can switch the alias to the new versioned index after reindexing and verification are complete.

## 10. Common Errors When Loading Configuration from Resources

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Settings or mapping file not found | Wrong path, case mismatch, or file not placed inside resources | Check location under **src/main/resources** and classpath path in the annotation |
| Invalid JSON | Missing comma, brace, or wrong JSON structure | Check syntax and structure against the Elasticsearch API |
| Unrecognized analyzer | Mapping references an analyzer name not declared in settings | Ensure the analyzer exists in settings of the same index |
| Index creation reports mapping error | Invalid field type, analyzer, or format | Read the error response from Elasticsearch and compare against the JSON |
| Edited file but actual mapping did not change | Index already existed, so the creation workflow did not run again | Check current mapping; use an update workflow or create a new index when needed |
| Application works in IDE but fails when packaged | Resource files were not included in the artifact or path is wrong | Inspect JAR contents and build resources configuration |
| Mapping in JSON does not match Java documents | Field names or data types between the two parts are inconsistent | Synchronize field names, data types, and conversion rules |

When encountering errors, examine startup logs and detailed responses from Elasticsearch. Resource-reading errors typically occur before sending the index creation request; mapping or analyzer errors usually appear in the response from Elasticsearch. Distinguishing these two groups helps narrow down the issue faster.

## 11. Example Using a Repository Once the Index Is Ready

Once the **products** index has its settings and mapping, the repository can be used like standard Spring Data Elasticsearch operations:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findBySku(String sku);
}
~~~

Saving a document:

~~~java
Product product = new Product();
// Set SKU, name, category, price, and creation date.
productRepository.save(product);
~~~

Searching by category or SKU relies on the corresponding mapping. Full-text search on **name** can use a **match** query so Elasticsearch analyzes content with **product_name_analyzer**. If exact name matching is needed, use the **name.keyword** subfield in Query DSL.

Example REST full-text search query:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Example filtering by exact category and price range:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

The two examples above demonstrate that the mapping determines how Elasticsearch interprets each field in queries. **match** suits analyzed text; **term** suits exact values; **range** is used to filter numeric or time ranges.

## 12. Notes on Versions and Deployment Environments

The **@Setting** and **@Mapping** annotations are ways to declare index metadata at the Spring Data Elasticsearch layer. However, client configuration, index operation APIs, and some data types may vary across Spring Data Elasticsearch and Elasticsearch versions.

When applying to a project:

- Use the Spring Data Elasticsearch version managed by Spring Boot or explicitly defined in dependency management.
- Check the documentation of your exact version regarding annotation attributes and **IndexOperations** APIs.
- Verify that the target Elasticsearch version supports the declared analyzers, field types, and settings.
- Test index creation in a development environment before deploying new configurations.
- Manage credentials, TLS, and index creation permissions using secure environment configuration.
- Avoid letting multiple application instances run uncoordinated index migrations simultaneously.

Separating settings and mapping into JSON files makes Elasticsearch configurations readable, reviewable, and packageable with the application. **@Setting** specifies the resource configuring index behavior; **@Mapping** specifies the resource describing data fields. When both files are declared properly on a **@Document** class, Spring Data Elasticsearch can use them during index creation. Managing subsequent changes must rely on the index lifecycle and Elasticsearch's mapping rules.
