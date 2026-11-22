# Spring Boot testing — @DataMongoTest và kiểm thử document, mapping, query

## 1. Vì sao MongoDB cần một kiểu kiểm thử persistence riêng?

Spring Data MongoDB cho phép viết Java repository gần giống Spring Data JPA. Tuy nhiên, MongoDB không lưu dữ liệu theo bảng/row của SQL mà theo **BSON documents** trong collections, có nested objects, arrays, các kiểu BSON như ObjectId/Date, chỉ mục (index), query operators và transaction semantics khác relational databases.

Ví dụ một document có thể có hình dạng:

```json
{
  "_id": {"$oid": "65a000000000000000000001"},
  "item_code": "CAM-001",
  "title": "Máy ảnh",
  "category": "camera",
  "price_cents": 3500000,
  "tags": ["new", "sale"],
  "details": {
    "brand": "ACME",
    "fragile": true
  },
  "created_at": {"$date": "2026-11-08T02:30:00Z"}
}
```

Đây là **Extended JSON minh họa** để dễ nhìn; BSON wire format không phải raw JSON text. Giá trị `_id` là ví dụ, không được cố định trong test. `created_at` ở MongoDB là BSON Date biểu diễn thời điểm theo milliseconds kể từ epoch UTC; thông tin timezone gốc không được giữ nguyên theo kiểu `OffsetDateTime` nếu không lưu riêng.

Một Java class có thể dùng `itemCode`, `priceCents` và `createdAt`, trong khi document thực lưu `item_code`, `price_cents`, `created_at`. Cùng lúc, repository method `findByCategoryAndPriceCentsGreaterThanEqual(...)` phải được Spring Data MongoDB phân tích, ánh xạ Java property sang đúng BSON field và gửi query phù hợp đến server.

Một unit test chỉ gọi method trên mocked `MongoRepository` **không chứng minh** những điều trên. Bài này tập trung vào **`@DataMongoTest`** — một Spring Boot test slice cho MongoDB persistence, kiểm tra document mapping, query derivation, `@Query` và `MongoTemplate` trên MongoDB test server được cô lập.

**Điểm phải nhớ:** `@DataMongoTest` tự cấu hình MongoDB-related beans; **không có nghĩa Spring Boot 3.3 sẽ tự khởi động embedded MongoDB**. Ta cần cung cấp MongoDB instance thật ở test environment, chẳng hạn Testcontainers MongoDB hoặc một server test chuyên dụng.

## 2. Mục tiêu học tập

Sau bài học bạn có thể:

1. Giải thích phạm vi `@DataMongoTest` và so sánh với Mockito unit test, `@SpringBootTest` và `@DataJpaTest`.
2. Tạo `@Document` với `@Id`, `@Field`, nested record/document, arrays, date field và unique index.
3. Dùng `MongoRepository` để `save`, `findById`, tìm theo business key, filter/sort/paginate và delete.
4. Viết derived query đúng Java property names, hiểu BSON field names khác Java names.
5. Viết `@Query` JSON theo tham số `?0`, phân biệt repository query với `MongoTemplate` query DSL.
6. Kiểm tra document **thực sự lưu trên MongoDB** bằng `org.bson.Document`, không chỉ so object do mock trả.
7. Dùng MongoDB Testcontainers cùng `@ServiceConnection`/`@DynamicPropertySource` trên Spring Boot 3.3.
8. Biết vì sao `@Indexed` không tự đồng nghĩa index đã được tạo; thực thi duplicate-key test thật.
9. Hiểu MongoDB writes không mặc định được rollback sau mỗi `@DataMongoTest` như JPA tests.
10. Làm test độc lập, dọn dữ liệu đúng collection, nhận diện database sai và tránh kết nối production.
11. Đánh giá type conversion (`ObjectId`/`String`, `Instant`/BSON Date, null, enum, nested object) và query behavior.
12. Biết những khi nào cần mở rộng từ JPA-style repository syntax sang MongoDB-specific integration tests.

## 3. Một bảng so sánh ranh giới kiểm thử

| Cách test | Có Spring context? | Có MongoDB server? | Chứng minh được gì? |
| --- | --- | --- | --- |
| JUnit thuần + mock repository | Không cần | Không | Business logic với dữ liệu giả |
| JUnit unit test custom converter | Có thể không | Không | Chuyển đổi giá trị riêng lẻ trong phạm vi converter |
| `@DataMongoTest` + MongoDB Testcontainers | Có, **slice Mongo** | Có, MongoDB thật trong container | Mapping, repository, query, BSON, indexes thực |
| `@SpringBootTest` + MongoDB container | Có, app đầy đủ | Có | Service, repository, cross-bean interaction |
| Live HTTP + MongoDB container | Có, app + HTTP server | Có | HTTP contract và persistence cùng luồng |
| Test trực tiếp database staging | Tùy | Có | Engine thật nhưng đòi isolation/credentials rõ |

**Hai chiều là độc lập:** `@DataMongoTest` quyết định **Spring beans nào được nạp**; Testcontainers quyết định **MongoDB server nào được dùng**. Không cần `@SpringBootTest` full context chỉ để sử dụng MongoDB thật.

## 4. `@DataMongoTest` làm gì trong Spring Boot 3.3?

Trong Boot 3.3, annotation nằm ở:

```java
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
```

Theo tài liệu Spring Boot 3.3, mặc định nó:

- Giới hạn auto-configuration cho những gì liên quan MongoDB data access.
- Cấu hình một `MongoTemplate` (imperative) khi các phụ thuộc phù hợp có trên classpath.
- Quét các `@Document` classes và Spring Data MongoDB repositories.
- Cấu hình `MongoClient`/mapping/converter/repository infrastructure qua auto-configurations của slice.
- Không quét các bean `@Component` thông thường hoặc `@ConfigurationProperties` như full app. Có thể dùng `@EnableConfigurationProperties` để thêm properties bean cần thiết.
- Hỗ trợ thêm test configuration/converter thích hợp qua `@Import` và những cơ chế Spring TestContext hợp lệ.
- **Không tự bảo đảm embedded MongoDB server**.
- **Không mặc định bọc toàn bộ test method trong transaction rollback** như `@DataJpaTest`.

Mẫu gọn:

```java
@DataMongoTest
class InventoryMongoTest {
    @Autowired MongoTemplate mongoTemplate;
    @Autowired CatalogItemRepository repository;
}
```

Mẫu trên chỉ minh họa annotation. Nó vẫn cần một MongoDB server được cấu hình và các class repository/document. Nếu không có server tại URI/host được cấu hình, lần thao tác database sẽ fail khi client không kết nối được.

### 4.1. Vì sao regular service không xuất hiện?

Giả sử một `@Service InventoryService` phụ thuộc `CatalogItemRepository`, test chỉ viết:

```java
@DataMongoTest
class InventoryServiceTest {
    @Autowired InventoryService service;
}
```

Context có thể fail vì `InventoryService` không được slice quét. Đây không phải bug của MongoDB repository. Khi muốn kiểm tra service trên dữ liệu Mongo thật, có thể `@Import(InventoryService.class)` vào slice nếu dependency graph nhỏ, hoặc `@SpringBootTest` nếu cần nhiều thành phần application.

**Không chồng `@DataMongoTest` với `@SpringBootTest` trên cùng class** để “cộng phạm vi”. Chọn một bootstrap strategy theo mục tiêu.

### 4.2. Có cần MongoDB trong JUnit method không?

Một test `@DataMongoTest` có thể nạp context mà chưa thực hiện I/O lập tức; không nên xem điều đó là bằng chứng MongoDB server đã chạy. Cần một phép ghi/đọc thật hoặc lệnh `ping` gửi tới database để xác nhận kết nối.

Nếu có Mongo server nhưng credentials/database sai, việc context khởi tạo không bảo đảm query sẽ trả đúng. Bài mẫu sẽ `save`, kiểm tra raw `Document` và truy vấn lại bằng repository để tránh false positive.

## 5. Mô hình MongoDB: document, collection, _id, BSON và mapping

Trong Spring Data MongoDB:

- `@Document(collection="inventory_items")` gắn Java class vào MongoDB collection.
- `@Id` ánh xạ identity Java sang BSON `_id`.
- `@Field("item_code")` ánh xạ property `itemCode` thành field `item_code`.
- `@Indexed(unique=true)` khai báo index metadata cho một property; **việc index có được tạo trên server hay không còn phụ thuộc index creation configuration**.
- Nested Java POJO/record có thể thành embedded BSON document.
- `List<String>` thường thành BSON array.
- `Instant` có thể được mapping thành BSON Date; BSON Date có **độ phân giải millisecond**, không tự bảo toàn nano precision vượt quá mức đó.

Spring Data MongoDB dùng **`MappingMongoConverter`** và mapping metadata. Đây không phải cùng một lớp serializer với Jackson dùng cho REST JSON. Vì vậy:

- `@Field("item_code")` hướng đến MongoDB BSON document.
- `@JsonProperty("item_code")` hướng đến Jackson JSON payload.
- `@JsonNaming`/`@JsonInclude` không mặc nhiên đổi tên BSON fields.
- Một REST DTO và một MongoDB document entity có thể có quy tắc đặt tên khác nhau có chủ đích.

### 5.1. `@Id String` không luôn là BSON String

MongoDB thường dùng BSON `ObjectId` cho `_id`. Spring Data MongoDB có cơ chế convert `String` ID thành `ObjectId` khi chuỗi phù hợp, và hỗ trợ `@MongoId` để kiểm soát mapping ID theo kiểu mong muốn.

Ví dụ test nên:

- Assert ID Java được sinh khác null.
- Query repository bằng `findById(saved.getId())`.
- Quan sát raw `_id` khác null.
- **Không** tự giả định raw `_id` luôn là String khi Java field `@Id String`.

Nếu API yêu cầu ID string có cấu trúc đặc biệt, xác định rõ `@MongoId(FieldType.STRING)` hoặc custom conversion phù hợp và test BSON raw type theo contract.

### 5.2. BSON Date không lưu timezone vùng

Giá trị `Instant.parse("2026-11-08T02:30:00Z")` là một thời điểm tuyệt đối. MongoDB BSON Date lưu milliseconds theo UTC timeline. Nếu frontend cần khôi phục timezone nguồn `Asia/Ho_Chi_Minh` hoặc offset người dùng khai báo, ứng dụng phải lưu thêm metadata thích hợp; BSON Date không tự ghi toàn bộ ZoneId.

Với nanosecond precision, chọn policy truncate/round hoặc dùng trường bổ sung. Test bài này dùng thời gian có giây nguyên nên round-trip chính xác ở độ phân giải milliseconds.

### 5.3. Nested document không phải quan hệ JPA

MongoDB cho phép lưu:

```json
{
  "item_code": "CAM-001",
  "details": {
    "brand": "ACME",
    "fragile": true
  }
}
```

Đây là embedded document nằm trong một document. Nó **không phải** foreign key/JPA `@ManyToOne`. Khi một domain model có references tới documents khác, cân nhắc `@DocumentReference`/`@DBRef`, nhưng lựa chọn reference vs embed cần dựa vào access patterns, update consistency và domain lifecycle.

## 6. `MongoRepository`: derived query và method names

Repository có thể trông quen thuộc:

```java
public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, String> {
    Optional<CatalogItem> findByItemCode(String itemCode);

    List<CatalogItem>
        findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                String category, long minPriceCents);
}
```

Mặc dù BSON field có thể là `item_code` và `price_cents`, **derived query method names dựa vào tên Java properties**: `itemCode`, `priceCents`. Spring Data ánh xạ tên property sang field MongoDB theo metadata.

Các ví dụ:

| Method fragment | Ý nghĩa |
| --- | --- |
| `findByItemCode` | So khớp business key |
| `findByCategory` | Filter category |
| `PriceCentsGreaterThanEqual` | Lọc giá lớn hơn hoặc bằng ngưỡng |
| `OrderByPriceCentsAsc` | Sắp tăng theo Java property priceCents |
| `findByCategory(String, Pageable)` | Trang dữ liệu và sort động |
| `countByCategory` | Đếm documents theo điều kiện |
| `existsByItemCode` | Chứng minh một document matching có tồn tại |

**Không nhầm tên phương thức với JSON field literal.** Viết `findByPrice_cents` không phải cách thông thường để diễn tả `@Field("price_cents")`. Query derivation phân tích Java property path.

## 7. `@Query` JSON query và tham số `?0`

Khi derived method quá dài hoặc cần điều kiện rõ ràng, Spring Data MongoDB hỗ trợ:

```java
@Query("{ 'category': ?0, 'price_cents': { '$lte': ?1 } }")
List<CatalogItem> findAffordableInCategory(
        String category,
        long maximumPriceCents);
```

`?0` là tham số method thứ nhất, `?1` là tham số thứ hai. Spring Data thực hiện binding tham số để tránh việc tự nối chuỗi query dễ hỏng. Cú pháp ở đây là MongoDB JSON-like query string được parser framework hỗ trợ; property names có thể được mapping theo `MongoPersistentEntity`.

Nếu gọi:

```java
repository.findAffordableInCategory("camera", 25000L);
```

query logic là category bằng “camera” **và** price_cents nhỏ hơn hoặc bằng 25000. Không cần mock repository để xem dữ liệu cố định; hãy tạo fixture documents thật và kiểm tra tập kết quả.

### 7.1. Không xây query bằng nối chuỗi input

Tránh kiểu:

```java
String queryText =
        "{ 'category': '" + userInput + "' }";
```

Đây là **mẫu anti-pattern**, không dùng để chạy production. Khi input chứa quote/operator, query có thể bị sai hoặc trở thành injection risk. Dùng repository parameters, `Query`/`Criteria` DSL hoặc named parameters framework hỗ trợ.

### 7.2. `@Query` projection là một hợp đồng khác

Có thể dùng `@Query(fields=...)` để chỉ lấy một số fields:

```java
@Query(
    value = "{ 'category': ?0 }",
    fields = "{ 'item_code': 1, 'title': 1 }")
List<CatalogItem> findPartialByCategory(String category);
```

Đây là **trích đoạn minh họa**, không được thêm vào runnable repository trong bài mẫu. Khi trả lại domain type nhưng chỉ select một số fields, những Java properties không được đưa vào projection có thể null hoặc primitive default, dễ tạo “document object” thiếu dữ liệu. Với API dùng projection, nên ưu tiên projection interface/DTO được thiết kế rõ, và test những fields nào thực sự được trả.

## 8. `MongoTemplate`: Query/Criteria, đọc raw BSON và thao tác chi tiết

`MongoRepository` phù hợp cho common CRUD/query methods. Khi cần dynamic query, projection, aggregation hoặc update operators, `MongoTemplate` thường giúp biểu đạt trực tiếp:

```java
Query query = Query.query(
        Criteria.where("category").is("camera")
                .and("priceCents").gte(10000L));

List<CatalogItem> items =
        template.find(query, CatalogItem.class);
```

Đoạn này nằm trong một test có `MongoTemplate template`; imports:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
```

Trong query mapped cho `CatalogItem.class`, `priceCents` có thể được convert sang stored field `price_cents`. Đây là lợi ích của mapping metadata; khác với raw driver query trực tiếp phải dùng đúng BSON field key.

**Phân biệt hai tầng test:**

- `MongoTemplate.find(Query, CatalogItem.class)` → document được mapping sang Java type.
- `template.getCollection("inventory_items").find(new Document(...))` → driver thao tác trực tiếp với **raw BSON Document**.

Khi muốn kiểm tra `@Field` mapping thực sự, raw BSON assertion có sức nặng hơn chỉ compare hai Java objects qua cùng mapper.

### 8.1. Có thể test trực tiếp MongoDB commands?

`template.getDb().runCommand(new Document("ping", 1))` gửi command đến database. Nó xác nhận MongoDB trả lời, nhưng **chưa** chứng minh mapping hoặc repository logic. Test có `save`/`find` + raw BSON checks cung cấp nhiều bằng chứng hơn.

## 9. Unique index và lý do test phải kiểm tra server thật

Khai báo:

```java
@Indexed(unique = true)
@Field("item_code")
private String itemCode;
```

là metadata cho Spring Data MongoDB. Nhưng **từ Spring Data MongoDB 3.0**, tự tạo index **được tắt theo mặc định**. Do đó một test duplicate key sẽ có thể **không fail** nếu index chưa được tạo.

Với bài học dùng một test container trống, ta bật index creation tường minh:

```java
@DataMongoTest(properties = {
    "spring.data.mongodb.auto-index-creation=true"
})
class CatalogItemMongoTest { }
```

Khi Mongo mapping context biết `@Document` và property `@Indexed`, cơ chế auto index creation có thể tạo index trên collection. Đối với ứng dụng thực tế, index management cần được kiểm soát trong deployment/migrations; không bật auto index creation toàn bộ production chỉ để có test xanh mà không review performance và quyền tạo index.

**Test đúng là ghi hai documents khác ID nhưng cùng business key**, yêu cầu MongoDB trả duplicate key error. Chỉ kiểm tra Java annotation tồn tại không chứng minh index đang được áp dụng ở database.

### 9.1. Lỗi duplicate key ≠ validation lỗi ở Java

Khi index thật được tạo, MongoDB phát duplicate key error (thường server code 11000). Spring Mongo exception translation có thể chuyển thành `org.springframework.dao.DuplicateKeyException`. Đây là lỗi ở database layer, khác với việc constructor hoặc Bean Validation từ chối một giá trị.

Đừng assert chính xác server error message vì nó có thể chứa collection/index naming khác theo version. Assert exception type thích hợp và không tiếp tục dùng một transaction đã thất bại theo cách không hợp lệ.

### 9.2. Index là một phần của contract vận hành

Nếu application query theo `item_code` hàng triệu documents, việc thiếu index có thể làm test correctness xanh nhưng performance tệ. Ngoài duplicate-key test, với các truy vấn quan trọng hãy kiểm tra index definitions trên MongoDB test server, và cân nhắc explain plan/performance tests ở môi trường phản ánh dữ liệu, không chỉ mấy bản ghi fixture.

## 10. Dự án ví dụ runnable: Java 17, Spring Boot 3.3.0, MongoDB Testcontainers

Dự án dưới đây dùng MongoDB container để kiểm tra document mapping và queries. Tất cả thao tác ghi/đọc thực sự gửi đến MongoDB trong Docker. Vì điều kiện máy học khác nhau, class MongoDB test chỉ được bật khi `RUN_MONGO_TESTS=true`; khi biến này không tồn tại, **JUnit skip Mongo tests chứ không giả vờ đã kiểm tra MongoDB**.

Đây là release Spring Boot **3.3.0** để ví dụ import/Gradle nhất quán; production nên dùng bản đã được tổ chức hỗ trợ và cập nhật security patches.

### 10.1. Cấu trúc thư mục

```text
mongo-slice-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/mongo/
    │   ├── MongoLabApplication.java
    │   ├── ItemDetails.java
    │   ├── CatalogItem.java
    │   └── CatalogItemRepository.java
    └── test/java/example/mongo/
        └── CatalogItemMongoTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'mongo-slice-lab'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-mongodb` cung cấp imperative Spring Data MongoDB, MongoDB Java driver và mapping/repository infrastructure. `spring-boot-testcontainers` bổ sung `@ServiceConnection` support của Spring Boot 3.3. Hai `org.testcontainers` modules cung cấp MongoDBContainer và JUnit 5 lifecycle.

**Điều kiện thực thi:** JDK 17, Gradle Wrapper tương thích (ví dụ Gradle 8.5), Docker/compatible Testcontainers runtime khi bật tests, quyền tải image `mongo:7.0`. Ví dụ không đưa Mongo credentials production vào source. Với project sử dụng cloud MongoDB/Atlas, phải thay bằng URI và test database cô lập trong test profile; không tự trỏ test đến cluster production.

### 10.4. `MongoLabApplication.java`

**`src/main/java/example/mongo/MongoLabApplication.java`:**

```java
package example.mongo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MongoLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MongoLabApplication.class, args);
    }
}
```

Class này là primary Boot configuration ở cùng package `example.mongo` với document/repository/tests. `@DataMongoTest` dùng slice filters, nên không tự nạp mọi ordinary service dù application class có `@SpringBootApplication`.

### 10.5. Nested value object `ItemDetails.java`

**`src/main/java/example/mongo/ItemDetails.java`:**

```java
package example.mongo;

public record ItemDetails(String brand, boolean fragile) {}
```

Java 17 record là một immutable value object. Spring Data MongoDB có thể mapping nó thành nested BSON object. Trong demo, hai fields được lưu ở document `details`, không có collection riêng cho `ItemDetails`.

### 10.6. Document `CatalogItem.java`

**`src/main/java/example/mongo/CatalogItem.java`:**

```java
package example.mongo;

import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "inventory_items")
public class CatalogItem {
    @Id
    private String id;

    @Indexed(unique = true)
    @Field("item_code")
    private String itemCode;

    private String title;
    private String category;

    @Field("price_cents")
    private long priceCents;

    private List<String> tags;

    @Field("created_at")
    private Instant createdAt;

    private ItemDetails details;

    protected CatalogItem() {
        // Spring Data mapping constructor.
    }

    public CatalogItem(
            String itemCode,
            String title,
            String category,
            long priceCents,
            List<String> tags,
            Instant createdAt,
            ItemDetails details) {
        this.itemCode = itemCode;
        this.title = title;
        this.category = category;
        this.priceCents = priceCents;
        this.tags = List.copyOf(tags);
        this.createdAt = createdAt;
        this.details = details;
    }

    public String getId() {
        return id;
    }

    public String getItemCode() {
        return itemCode;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public List<String> getTags() {
        return tags;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public ItemDetails getDetails() {
        return details;
    }
}
```

Giải thích:

- `@Document(collection="inventory_items")` cố định tên collection.
- `@Id String id` dùng Spring Data MongoDB ID mapping, có thể được convert sang BSON ObjectId.
- `@Field("item_code")` và `@Field("price_cents")`/`@Field("created_at")` đặt BSON keys khác tên Java.
- `@Indexed(unique=true)` yêu cầu index metadata, nhưng phải bảo đảm index được tạo thực sự trong test.
- `tags` thành array, `details` thành nested BSON document, `Instant` thành BSON Date với millisecond precision.
- No-arg constructor `protected` dùng cho materialization nếu cần; getter giúp test quan sát state.
- `List.copyOf(tags)` tạo immutable snapshot, không đồng nghĩa MongoDB array là immutable sau khi đã lưu.

Nếu domain cho phép tags null, constructor mẫu sẽ ném NPE; trong demo fixture luôn cung cấp list khác null. Đây là giới hạn của test model, không phải một quy tắc MongoDB tự áp đặt.

### 10.7. Repository `CatalogItemRepository.java`

**`src/main/java/example/mongo/CatalogItemRepository.java`:**

```java
package example.mongo;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, String> {

    Optional<CatalogItem> findByItemCode(String itemCode);

    List<CatalogItem>
        findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                String category, long minimumPriceCents);

    @Query("{ 'category': ?0, 'price_cents': { '$lte': ?1 } }")
    List<CatalogItem> findAffordableInCategory(
            String category, long maximumPriceCents);

    Page<CatalogItem> findByCategory(
            String category, Pageable pageable);
}
```

`MongoRepository<CatalogItem,String>` tạo CRUD repository. `findByItemCode` dùng property `itemCode` được mapping sang BSON `item_code`. Derived price query dùng `priceCents` và sort ascending. `@Query` viết Mongo filter theo category và `$lte`. `findByCategory` với `Pageable` kiểm tra paging/sort.

## 11. Tệp test chạy được: @DataMongoTest + MongoDBContainer

**`src/test/java/example/mongo/CatalogItemMongoTest.java`:**

```java
package example.mongo;

import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@EnabledIfEnvironmentVariable(
        named = "RUN_MONGO_TESTS",
        matches = "true"
)
@Testcontainers
@DataMongoTest(properties = {
        "spring.data.mongodb.auto-index-creation=true"
})
class CatalogItemMongoTest {
    @Container
    @ServiceConnection
    static MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @Autowired
    CatalogItemRepository repository;

    @Autowired
    MongoTemplate template;

    private static final Instant FIXED_TIME =
            Instant.parse("2026-11-08T02:30:00Z");

    private CatalogItem item(
            String code, String category, long price) {
        return new CatalogItem(
                code,
                "Mặt hàng " + code,
                category,
                price,
                List.of("new"),
                FIXED_TIME,
                new ItemDetails("ACME", false));
    }

    @BeforeEach
    void cleanBefore() {
        repository.deleteAll();
    }

    @AfterEach
    void cleanAfter() {
        repository.deleteAll();
    }

    @Test
    void savesAndReloadsMappedDocument() {
        CatalogItem original = new CatalogItem(
                "CAM-001",
                "Máy ảnh",
                "camera",
                3500000L,
                List.of("new", "sale"),
                FIXED_TIME,
                new ItemDetails("ACME", true));

        CatalogItem saved = repository.save(original);

        assertNotNull(saved.getId());

        Document raw = template
                .getCollection("inventory_items")
                .find(new Document("item_code", "CAM-001"))
                .first();

        assertNotNull(raw);
        assertNotNull(raw.get("_id"));
        assertEquals("CAM-001", raw.getString("item_code"));
        assertEquals("Máy ảnh", raw.getString("title"));
        assertEquals("camera", raw.getString("category"));
        assertEquals(3500000L,
                ((Number) raw.get("price_cents")).longValue());
        assertEquals(
                List.of("new", "sale"),
                raw.getList("tags", String.class));
        assertFalse(raw.containsKey("itemCode"));
        assertFalse(raw.containsKey("priceCents"));

        Document nested =
                raw.get("details", Document.class);
        assertNotNull(nested);
        assertEquals("ACME", nested.getString("brand"));
        assertTrue(nested.getBoolean("fragile"));

        CatalogItem reloaded = repository
                .findByItemCode("CAM-001")
                .orElseThrow();

        assertEquals(saved.getId(), reloaded.getId());
        assertEquals(3500000L, reloaded.getPriceCents());
        assertEquals(FIXED_TIME, reloaded.getCreatedAt());
        assertEquals("ACME", reloaded.getDetails().brand());
        assertTrue(reloaded.getDetails().fragile());
    }

    @Test
    void derivedQueryUsesJavaPropertiesAndSortsPrice() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 5000L)));

        List<CatalogItem> result = repository
                .findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                        "camera", 20000L);

        assertEquals(
                List.of("CAM-MID", "CAM-HIGH"),
                result.stream().map(CatalogItem::getItemCode)
                        .toList());
    }

    @Test
    void annotatedMongoQueryBindsParameters() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 5000L)));

        List<CatalogItem> affordable = repository
                .findAffordableInCategory(
                        "camera", 25000L);

        assertEquals(
                java.util.Set.of("CAM-LOW", "CAM-MID"),
                affordable.stream()
                        .map(CatalogItem::getItemCode)
                        .collect(java.util.stream.Collectors.toSet()));
    }

    @Test
    void mongoTemplateCriteriaMapsPropertyNames() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 120000L)));

        Query query = Query.query(
                Criteria.where("category").is("camera")
                        .and("priceCents").gte(50000L));

        List<CatalogItem> result =
                template.find(query, CatalogItem.class);

        assertEquals(1, result.size());
        assertEquals("CAM-HIGH",
                result.get(0).getItemCode());
    }

    @Test
    void pageableQuerySortsWithoutDependingOnNaturalOrder() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L)));

        Page<CatalogItem> firstPage = repository.findByCategory(
                "camera",
                PageRequest.of(0, 2,
                        Sort.by(Sort.Direction.DESC, "priceCents")));

        assertEquals(3, firstPage.getTotalElements());
        assertEquals(2, firstPage.getContent().size());
        assertEquals(
                List.of("CAM-HIGH", "CAM-MID"),
                firstPage.getContent().stream()
                        .map(CatalogItem::getItemCode)
                        .toList());
    }

    @Test
    void uniqueIndexRejectsDuplicateBusinessKey() {
        repository.save(
                item("UNIQUE-ITEM", "camera", 10000L));

        assertThrows(DuplicateKeyException.class,
                () -> repository.save(
                        item("UNIQUE-ITEM", "accessory", 20000L)));
    }

    @Test
    void deletingOneDocumentDoesNotDeleteOthers() {
        CatalogItem first = repository.save(
                item("DEL-ONE", "camera", 10000L));

        CatalogItem second = repository.save(
                item("DEL-TWO", "camera", 20000L));

        repository.deleteById(first.getId());

        assertFalse(repository.findById(first.getId())
                .isPresent());
        assertTrue(repository.findById(second.getId())
                .isPresent());
    }

    @Test
    void mongoServerReallyAnswersCommands() {
        Document result = template.getDb()
                .runCommand(new Document("ping", 1));

        assertEquals(
                1.0d,
                ((Number) result.get("ok")).doubleValue());
    }
}
```

**Tổng cộng 8 test methods** trong class này. Khi biến `RUN_MONGO_TESTS=true` và Docker/runtime sẵn sàng, kỳ vọng cả 8 pass với MongoDB server do Testcontainers khởi động. Khi không bật biến, JUnit **skip** class: không có bằng chứng query chạy trên MongoDB trong lần đó.

### 11.1. Lý do dùng một test class và container static

`@Container` static thường được Testcontainers JUnit extension quản lý cho lifecycle class. TestContext của Spring có thể cache application contexts lâu hơn lifecycle container; nếu chia sẻ một context cùng connection tới container static đã dừng ở test class trước, test class khác có thể bị connection refused.

Trong lab này, chỉ một `@DataMongoTest` class khai báo Mongo container nên lifecycle dễ hiểu. Trong dự án lớn, cân nhắc shared container bean do Spring Boot quản lý hoặc singleton container lifecycle nhất quán với context cache và test isolation.

### 11.2. Điều gì làm test “raw BSON” mạnh hơn mock test?

`savesAndReloadsMappedDocument` kiểm tra đồng thời:

1. Repository thực sự ghi một document có `_id` khác null.
2. Collection có tên `inventory_items`.
3. BSON keys là `item_code` và `price_cents`, không phải Java property names `itemCode`/`priceCents`.
4. `tags` trở thành BSON array, `details` trở thành nested document.
5. MongoDB raw document lưu đúng giá trị và repository load được về Java object.
6. `Instant` được round-trip cho một fixed timestamp phù hợp BSON millisecond precision.

Nếu chỉ dùng `when(repository.findByItemCode(...)).thenReturn(Optional.of(...))`, không có bằng chứng nào trong sáu điều này.

### 11.3. Vì sao assert kết quả có thứ tự ở query A nhưng không ở query B?

Derived query method khai báo `OrderByPriceCentsAsc` nên có thứ tự dự kiến rõ. `@Query` annotated ở test `findAffordableInCategory` **không chỉ định sort**, vì vậy test so sánh `Set` of codes, **không** giả định MongoDB trả documents theo thứ tự insert.

**Không bao giờ** dựa vào “natural order” của MongoDB như một API contract. Nếu cần thứ tự, khai báo `Sort` hoặc sort trong query; với paging phải có sort ổn định (và có thể tie-breaker) để tránh trùng/bỏ sót khi dữ liệu thay đổi.

### 11.4. Vì sao bật auto-index-creation trong test?

Bộ test duplicate key cần một MongoDB unique index thật trên `item_code`. `@Indexed(unique=true)` cung cấp metadata; cấu hình `spring.data.mongodb.auto-index-creation=true` cho phép Spring Data tạo index từ metadata trong context test. Không có index, hai documents khác `_id` nhưng trùng `item_code` có thể được lưu mà không lỗi.

Trong production, index nên được quản lý bằng migration/deployment phù hợp, review tên index và rolling changes. Test có thể dùng `template.indexOps(CatalogItem.class).getIndexInfo()` để quan sát indexes được tạo.

## 12. Chạy test và hiểu rõ trạng thái SKIP

### 12.1. Không có Docker

Linux/macOS:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu không đặt `RUN_MONGO_TESTS`, class `CatalogItemMongoTest` bị **disabled** bởi `@EnabledIfEnvironmentVariable`. Gradle có thể báo build thành công nhưng **không có MongoDB integration test nào được thực thi**. Đây là thiết kế an toàn để ví dụ không ngẫu nhiên kết nối local/prod server khi máy thiếu Docker.

### 12.2. Có Docker, chủ động bật Mongo tests

Linux/macOS:

```bash
RUN_MONGO_TESTS=true ./gradlew test \
    --tests example.mongo.CatalogItemMongoTest
```

Windows PowerShell:

```powershell
$env:RUN_MONGO_TESTS = 'true'
.\gradlew.bat test --tests example.mongo.CatalogItemMongoTest
Remove-Item Env:RUN_MONGO_TESTS
```

Dự kiến **8 tests pass** nếu môi trường có Docker/Testcontainers runtime tương thích, image `mongo:7.0` tải được và các dependencies Maven Central có thể truy cập.

**Kết quả là expected behavior, không phải kết quả thực thi được đo trong bài viết.** Không bịa một MongoDB port/container ID, log thực tế hay execution time.

### 12.3. Muốn CI luôn bắt buộc chạy Mongo tests?

Không sử dụng conditional skip nếu policy CI là *database integration bắt buộc*. Khi đó bỏ `@EnabledIfEnvironmentVariable` và chạy trên CI agent luôn có Docker; nếu MongoDB không khởi động, test **phải fail** thay vì bị skip. Có thể tách Gradle task/source set cho fast unit tests và integration tests, nhưng phải báo rõ số executed/skipped.

## 13. `@ServiceConnection` so với `@DynamicPropertySource`

`@ServiceConnection` thuộc Spring Boot 3.3 testcontainers integration. Trên typed `MongoDBContainer`, nó cung cấp `MongoConnectionDetails` để auto-configured Mongo client trỏ tới đúng container. Connection details được ưu tiên trước một số connection properties thông thường.

Cấu hình trong lab:

```java
@Container
@ServiceConnection
static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");
```

Bạn không phải tự gọi `mongo.getReplicaSetUrl()` để set `spring.data.mongodb.uri` khi sử dụng cách này.

Nếu không dùng `@ServiceConnection`, có thể thay bằng Spring TestContext `@DynamicPropertySource`:

```java
@Container
static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

@DynamicPropertySource
static void mongodbProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
}
```

Đoạn trên là **phương án thay thế** trong class `@Testcontainers` (cần imports `DynamicPropertySource`/`DynamicPropertyRegistry`). **Không áp dụng đồng thời** hai cách vào cùng một container nếu không có yêu cầu và hiểu rõ precedence.

### 13.1. MongoDBContainer và replica set

Testcontainers `MongoDBContainer` thường cung cấp MongoDB instance và connection URL phù hợp với test, có hỗ trợ cấu hình replica set trong container module. Việc sử dụng replica set có ý nghĩa nếu sau này muốn kiểm tra MongoDB transactions hoặc change streams. Nhưng một `@DataMongoTest` thường dùng CRUD/query ở trên **không tự mở Mongo transaction** chỉ vì replica set tồn tại.

### 13.2. Đừng kết nối nhầm local 27017

Nếu một test bỏ connection details và có MongoDB driver, Spring Boot có thể dùng connection setting/default như localhost `27017` (tùy version/config). Nếu đúng lúc máy có MongoDB process ở đó, test có thể **pass trên sai database** hoặc xóa dữ liệu test khác.

Với Testcontainers, hãy đưa URI từ container qua service connection/dynamic properties và kiểm soát môi trường test. Không dựa vào việc localhost 27017 luôn trống hay an toàn.

## 14. Vì sao MongoDB test không tự rollback như @DataJpaTest?

Với `@DataJpaTest` và relational transaction manager, Spring Boot test slice thường bắt đầu một test-managed transaction rồi **rollback sau test method**. Với MongoDB, `@DataMongoTest` **không mặc định cấp cùng cơ chế rollback**.

MongoDB transactions có yêu cầu riêng:

- MongoDB deployment cần topology hỗ trợ transactions (ví dụ replica set hoặc sharded cluster phù hợp).
- Spring Data MongoDB thường cần `MongoTransactionManager`/reactive transaction manager và session/transaction participation đúng cấu hình.
- Một test method có `@Transactional` mà không có transaction manager phù hợp **không** biến các writes thành rollback tự động.
- Dữ liệu được ghi ngoài transaction phù hợp sẽ tồn tại đến khi bị xóa/collection bị drop/database bị destroy.

Trong lab:

```java
@BeforeEach
void cleanBefore() {
    repository.deleteAll();
}

@AfterEach
void cleanAfter() {
    repository.deleteAll();
}
```

Hai callbacks bảo đảm collection của container test chỉ chứa fixture của method hiện tại, với giả định **không có writer đồng thời khác vào cùng database**.

**Không dùng `repository.deleteAll()` trên MongoDB staging/production.** Dữ liệu ở lab thuộc một container test cô lập. Với shared DB, hãy dùng database-per-test/schema-like logical database riêng, unique keys và cleanup đúng documents do test tạo; MongoDB không có SQL schema theo cách JPA.

### 14.1. Có nên dùng `template.dropCollection(CatalogItem.class)`?

Nếu drop collection, bạn cũng có thể xóa **indexes**. Sau đó duplicate key test có thể mất unique index nếu auto index creation chỉ chạy lúc mapping context khởi tạo.

Trong bài mẫu dùng `deleteAll()` để **xóa documents nhưng giữ collection và indexes**. Nếu test cần drop collection, hãy quản lý việc tạo index lại có chủ đích (ví dụ `ensureIndex`) hoặc tạo database/container mới.

### 14.2. Cleanup hai phía không tạo transaction isolation tự động

Trong các test chạy song song dùng chung Mongo container/database, hai methods có thể xóa dữ liệu lẫn nhau. `@BeforeEach`/`@AfterEach` giúp test tuần tự độc lập, **không phải giải pháp concurrency**.

Với parallel tests, dùng database/collection riêng theo test hoặc Testcontainers isolation strategy hợp lý. Đừng bật JUnit parallel trên shared Mongo state rồi cố chữa bằng `Thread.sleep`.

## 15. `@Indexed`, collection lifecycle và persistence index tests

### 15.1. Auto-index-creation tắt theo mặc định

Tài liệu Spring Data MongoDB cho biết auto index creation cần bật tường minh từ version 3.0. Điều này tránh thay đổi collection/index một cách bất ngờ khi ứng dụng khởi động.

Bởi vậy, test `uniqueIndexRejectsDuplicateBusinessKey` sẽ chỉ đúng nếu index thật tồn tại. Nó là **integration test quan trọng** vì annotation đơn lẻ không phải cam kết MongoDB server đã tạo index.

### 15.2. Tạo index bằng MongoTemplate khi cần

Ở một test/sandbox nâng cao:

```java
template.indexOps(CatalogItem.class)
        .ensureIndex(
                new Index()
                        .on("itemCode", Sort.Direction.ASC)
                        .unique());
```

Đoạn **minh họa** cần imports `org.springframework.data.mongodb.core.index.Index` và `org.springframework.data.domain.Sort`, được chạy trong context có `template`. Index operations có thể map property `itemCode` sang field `item_code`; xác minh thực tế từ `getIndexInfo()` nếu đang chuẩn hóa index conventions.

Không chạy lệnh này bừa bãi trên production/shared DB trong mỗi test. Khi collection có duplicate documents sẵn, tạo unique index có thể fail — đây là một trạng thái dữ liệu cần migration/cleanup, không phải chỉ đổi annotation là xong.

### 15.3. Index uniqueness trên null/missing

MongoDB unique indexes có quy tắc riêng đối với missing/null, compound indexes, partial filters và sparse indexes. Nếu `item_code` optional, một unique index thông thường có thể từ chối nhiều documents thiếu field theo cách không giống unique constraint SQL. Cần thiết kế `partialFilterExpression` hoặc sparse index đúng business contract nếu cần nhiều documents không có key.

Bài mẫu luôn cung cấp non-null `itemCode`, nên không suy luận toàn bộ semantics cho optional unique key từ duplicate test đó.

## 16. Null, missing, arrays và query semantics trong MongoDB

Trong document database:

```json
{"details": null}
```

khác về mặt lưu trữ với:

```json
{}
```

Với một số MongoDB queries, predicate `{field: null}` có thể match cả explicit null lẫn missing field. Muốn phân biệt, sử dụng `$exists` và các điều kiện thích hợp, kiểm tra trên server thật.

Trong Java:

- `null` ở một property có thể bị omit khỏi BSON document theo mapping behavior/config.
- Primitive như `long priceCents` có default 0, không biểu diễn thiếu dữ liệu rõ.
- `List<String>` và arrays có thể map thành BSON arrays.
- Query equality trên array field có semantics đặc biệt: điều kiện bằng một scalar có thể match một array chứa scalar đó.
- `$elemMatch` cần thiết khi muốn nhiều điều kiện áp dụng lên **cùng một phần tử** của array embedded documents.
- `$in`, `$nin`, `$exists`, `$type` và `$regex` cần được test với edge cases nếu chúng thuộc public query contract.

**Không áp đặt semantics của SQL NULL lên MongoDB**. Những trường hợp null vs absent nên dùng raw document tests và MongoDB predicates riêng.

### 16.1. Thí nghiệm với `exists`

Trích đoạn sử dụng MongoTemplate:

```java
Query missingDetails = Query.query(
        Criteria.where("details").exists(false));

List<CatalogItem> result =
        template.find(missingDetails, CatalogItem.class);
```

Đoạn minh họa cần documents không có field details; lab mặc định luôn tạo details nên không có fixture cho case này. Bổ sung fixture raw BSON và expected rõ trước khi assert.

### 16.2. Date query và timezone

BSON Date lưu instant theo milliseconds. Nếu bạn lọc sự kiện từ đầu ngày “2026-11-08” ở `Asia/Ho_Chi_Minh`, cần chuyển local day boundary thành UTC instants bằng `ZoneId` rồi query `createdAt` theo range.

Không dùng `LocalDateTime` local rồi suy luận nó là UTC. Với daylight-saving zones, boundary có thể có 23/25 giờ; chọn `ZonedDateTime`/`ZoneId` theo nghiệp vụ và test ngày chuyển DST.

## 17. Mapping test, JSON REST test và converter test không giống nhau

Ví dụ entity:

```java
@Field("item_code")
private String itemCode;
```

Khi lưu MongoDB, key là `item_code`. Nhưng nếu controller trả trực tiếp `CatalogItem` qua Jackson và không cấu hình Jackson naming, JSON response có thể là `itemCode`, vì Jackson dùng bean property names.

Điều này không nhất thiết là bug nếu contract REST và storage schema khác nhau. Cách kiểm tra:

- **`@DataMongoTest`:** assert raw BSON field `item_code` và Spring Data mapping.
- **`@JsonTest`:** assert Jackson JSON property name/enum/date format của REST DTO.
- **`@WebMvcTest`/`@WebFluxTest`:** assert inbound/outbound HTTP JSON mapping.
- **`@SpringBootTest`:** kiểm tra service phối hợp database + controller nếu đó là mục tiêu.

Không dùng `ObjectMapper.writeValueAsString(entity)` để kết luận BSON document có những keys ấy; Jackson và MappingMongoConverter là hai cơ chế riêng.

### 17.1. Custom conversions

Nếu lưu `Money` value object hoặc một kiểu `UUID`/`Instant` theo định dạng riêng, Spring Data MongoDB có `MongoCustomConversions` và `@ReadingConverter`/`@WritingConverter`. Khi test `@DataMongoTest`, hãy chắc custom converters **thực sự có trong slice context** qua configuration phù hợp (có thể `@Import`). Nếu converter là regular `@Component` ngoài slice scan, test có thể dùng default conversion và cho kết quả khác full app.

Test converter nên có cả hai chiều:

1. Java value → raw BSON type/value.
2. Raw BSON → Java value.
3. Negative cases: unsupported format hoặc precision overflow.
4. Kiểm tra query mapping nếu converter ảnh hưởng query criteria.

## 18. `@Version` và optimistic locking trong MongoDB

Spring Data MongoDB hỗ trợ `@Version` cho optimistic locking: khi update document có version, update query có thể kiểm tra version hiện tại và reject stale update.

Mẫu entity thêm:

```java
@Version
private Long version;
```

Đây là **trích đoạn**, không thuộc class runnable ở mục 10. Cần import `org.springframework.data.annotation.Version`, getter và lưu version theo mapping conventions. Với optimistic locking test:

1. Lưu document lần đầu, lấy version.
2. Đọc ra hai bản snapshot độc lập.
3. Cập nhật và save snapshot A.
4. Cố save snapshot B cũ, kỳ vọng optimistic locking failure.
5. Xác minh persisted document không bị ghi đè bởi stale version.

Một số điều kiện đi kèm:

- Write concern phải đủ để nhận biết update không match/version conflict.
- Transaction/driver behavior có thể ảnh hưởng cách lỗi xuất hiện.
- Đừng chỉ assert field version trên object trong memory; cần đọc lại server state.

Bài mẫu tập trung mapping/query, nên không tự thêm optimistic locking vào entity để tránh trộn behavior ngoài phạm vi chính.

## 19. Sorting, paging, projections và dữ liệu đang thay đổi

`Page<CatalogItem>` từ MongoRepository có thể chạy query lấy page và query count. Trong lab, paging được assert bằng:

```java
PageRequest.of(
        0,
        2,
        Sort.by(Sort.Direction.DESC, "priceCents"))
```

Thứ tự dựa vào Java property `priceCents`, Spring Data ánh xạ tới stored field. Khi có hai documents cùng giá, thứ tự tương đối có thể không ổn định; trong API thực tế, thêm tie-breaker (ví dụ itemCode hoặc _id) nếu paging yêu cầu ổn định:

```java
PageRequest.of(
        0, 20,
        Sort.by(Sort.Direction.DESC, "priceCents")
            .and(Sort.by("itemCode")))
```

Đây là đoạn minh họa; phải kiểm tra index/order và schema theo lượng data thực tế. Trong hệ thống dữ liệu cập nhật liên tục, offset pagination có thể trùng/bỏ sót giữa requests nếu documents được insert/update; cursor/keyset pagination phù hợp hơn cho một số luồng.

### 19.1. Projection không phải luôn trả entity đầy đủ

Projection query chỉ lấy `item_code`/`title` sẽ làm các trường không được chọn thành null/zero nếu bạn materialize vào một entity type đầy đủ. Dùng interface/DTO projection có contract rõ; test exactly fields returned, không dùng partial entity như một entity hoàn chỉnh để update ngược database.

### 19.2. Aggregation pipeline khi query logic vượt derived methods

MongoDB có aggregation stages `$match`, `$group`, `$unwind`, `$project` và `$sort`. Spring Data cung cấp `Aggregation` DSL và `@Aggregation` repositories. Với aggregation phức tạp:

- Test pipeline trên server MongoDB thật với fixture đủ edge cases.
- Kiểm tra output shape và numeric types (`int`/`long`/`Decimal128`).
- Xác minh indexes/query plans khi performance là yêu cầu.
- Không coi một mock `List` kết quả là bằng chứng aggregation expression đúng.

## 20. MongoDB transactions: khi nào cần và khi nào không?

MongoDB hỗ trợ multi-document transactions trên deployment phù hợp như replica set/sharded cluster, nhưng chúng có chi phí và các giới hạn riêng. `@DataMongoTest` mặc định không tự cấp transaction manager theo cách `@DataJpaTest` thường làm cho SQL.

Nếu business use case cần atomic multi-document update:

- Cấu hình `MongoTransactionManager` hoặc reactive transaction manager theo stack đang dùng.
- Sử dụng Mongo deployment hỗ trợ transactions.
- Viết test verify commit/rollback bằng đọc lại data từ server sau transaction.
- Tạo lỗi có chủ đích giữa hai writes và assert partial updates không còn khi rollback.
- Tránh dùng test cleanup bằng `deleteAll()` như bằng chứng transactions đã rollback: cleanup và transaction logic là hai chuyện khác nhau.

**Không dùng `@Transactional` trên một test Mongo rồi mặc định mọi writes rollback**. Test phải xác minh thực tế transaction manager, session participation và server behavior.

### 20.1. Atomicity một document

Ngay cả không dùng multi-document transaction, MongoDB có **atomicity ở mức một document** cho các single-document write operations. Khi use case thường chỉ update fields trong một document, có thể sử dụng atomic update operators hoặc find-and-modify phù hợp thay vì mở multi-document transaction.

Test cần xác nhận kết quả thực tế của `$inc`, `$set`, concurrency và versioning nếu business rule yêu cầu; repository `save` toàn document không luôn là tương đương một atomic conditional update.

## 21. Reactive MongoDB: đừng trộn hai stack trong một test mẫu

MongoDB cũng có reactive driver, `ReactiveMongoTemplate` và `ReactiveMongoRepository`, cùng Reactor `Mono`/`Flux`. `@DataMongoTest` có thể liên quan cả MongoDB data auto-configurations tùy classpath/test slice; nhưng bài runnable này **chỉ dùng imperative `MongoRepository` và `MongoTemplate`** từ `spring-boot-starter-data-mongodb`.

Nếu project dùng reactive repositories:

- Thêm `spring-boot-starter-data-mongodb-reactive` theo Boot version.
- Sử dụng `ReactiveMongoRepository`/`ReactiveMongoTemplate`.
- Dùng `StepVerifier` để assert Publisher signals, không gọi `block()` trong production event loop.
- Thống nhất driver/configurations và Testcontainers MongoDB URI.
- Thiết kế transaction/context propagation theo reactive semantics, không suy luận từ imperative thread-local transaction.

**Không copy `MongoRepository` method trả `List` sang reactive code rồi coi tương đương `Flux` trong nonblocking stack.**

## 22. Tại sao một server thật vẫn có thể cho false confidence?

Một `@DataMongoTest` với MongoDB container có bằng chứng mạnh hơn mock, nhưng vẫn chưa tự chứng minh mọi điều:

- MongoDB container version có thể khác MongoDB Atlas/production cluster.
- Sharding, replica set topology, transaction settings hoặc user roles có thể khác.
- Test database ít documents nên không bộc lộ slow queries/index scans.
- Container test không đại diện cho TLS, auth, proxies hay latency network production.
- `@DataMongoTest` không nạp service/controller nghiệp vụ ngoài slice.
- Custom converters/index migrations hoặc application listeners có thể không được slice nạp.
- Failover/replication consistency, eventual consistency và timeouts cần test riêng.
- Atlas Search, change streams, vector indexes và provider-specific features cần môi trường đúng khả năng server.
- Bài mẫu chưa kiểm tra migrations/index rollout, chỉ bật auto-index-creation cho test.

Test xanh chỉ được hiểu trong **ranh giới được cấu hình và quan sát**.

## 23. Kết nối server MongoDB test khác Testcontainers

Nếu CI không có Docker, có thể dùng một MongoDB instance test chuyên dụng. Nhưng phải cấu hình rõ URI qua test profile/environment, không dùng production credentials và không cho phép test tự connect localhost 27017 ngoài ý muốn.

Ví dụ **chỉ minh họa, URL không dùng được**:

```properties
spring.data.mongodb.uri=mongodb://test-db.example.invalid:27017/inventory_test
```

Nếu sử dụng authentication/TLS thực, nên dùng environment variables/secret manager thay vì ghi password vào source. Để bảo vệ test:

- Database riêng cho test run hoặc namespace/collection prefix.
- User chỉ có quyền test database.
- Cleanup đúng documents/collection thuộc test.
- Kiểm tra cluster identity, database name hoặc thông số connection an toàn.
- Không chạy `dropDatabase`/`deleteAll` trên shared production database.
- Có timeout và quy trình fail fast nếu MongoDB không sẵn sàng.

Testcontainers thường thuận tiện hơn vì tạo MongoDB cô lập, nhưng không có gì buộc phải dùng Docker nếu tổ chức đã có một test DB an toàn.

## 24. Troubleshooting: test fail ở lớp nào?

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` service | `@DataMongoTest` không scan ordinary service | `@Import` có chủ đích hoặc `@SpringBootTest` |
| `MongoTimeoutException`/server selection timeout | MongoDB server không chạy, URI sai, network blocked | Kiểm tra Testcontainers/URI/credentials |
| `Could not find a valid Docker environment` | Docker không có hoặc runtime không được phép | Bật Mongo tests ở CI node có Docker |
| Test bị skip nhưng Gradle xanh | `RUN_MONGO_TESTS` chưa bật | Phân biệt SKIPPED với PASSED |
| Raw BSON field không phải `item_code` | `@Field`/converter không đúng | Xem Mongo mapping metadata, raw Document |
| Repository query không match `price_cents` | Derived property path hoặc `@Query` field key sai | Kiểm tra Java property vs BSON key |
| `DuplicateKeyException` không xảy ra | Unique index chưa được tạo | Bật index creation trong test hoặc ensureIndex |
| Duplicate key fail ngay khi tạo index | DB đã có dữ liệu trùng | Cleanup trước index migration, dùng DB riêng |
| Test xanh riêng, suite đỏ | Shared collection, context cache, container lifecycle | Isolation theo class/run, cleanup có chủ đích |
| Mongo writes còn lại sau test | Không có test-managed rollback mặc định | Delete/DB riêng, không giả định giống JPA |
| Java String ID khác raw ObjectId | Mongo ID conversion | Dùng `findById` và `@MongoId` nếu cần kiểu cụ thể |
| BSON Date lệch nanoseconds | Millisecond precision của BSON Date | Chuẩn hóa precision trong contract |
| `getIndexInfo` không có index vừa annotation | Auto-index-creation tắt hoặc collection recreated | Cấu hình explicit index management |
| Custom converter không áp dụng | Converter bean không được scan trong slice | `@Import` test config có conversion |
| Nâng Boot 4 bị lỗi package `DataMongoTest` | Test modules/packages tái cấu trúc | Dùng đúng BOM/starter/import theo Boot 4 |
| MongoDB authentication fail | Credentials/auth database sai | Dùng test account, URI/config riêng |
| JSON REST fields khác BSON fields | Jackson vs Mongo converter khác nhau | Test `@JsonTest` riêng và raw Mongo mapping |

### 24.1. Lỗi kết nối không giống lỗi query

Nếu MongoDB không reachable, driver có thể chờ server selection rồi ném timeout; điều này **không** chứng minh repository method signature sai. Trước khi sửa `@Query`:

1. Xem MongoDB server/container có chạy không.
2. Kiểm tra URI/port, database và authentication.
3. Chạy một `ping` thật.
4. Kiểm tra collection có fixture data.
5. Sau đó mới kiểm tra raw BSON field names/query conditions.

### 24.2. Truy vấn trả rỗng không nhất thiết là query syntax error

MongoDB thường trả empty cursor nếu không có matches. Truy vấn sai field có thể không ném exception mà chỉ trả list rỗng. Vì vậy hãy tạo **positive fixture và negative fixture** trong test rồi assert tập kết quả chính xác, không chỉ `assertNotNull(result)`.

### 24.3. Phân tích index trước khi thay query

Nếu query đúng nhưng chậm, có thể thiếu index, selectivity thấp hoặc sort không covered. Không sửa query business rule chỉ để micro-benchmark H2-like data. Xem MongoDB explain plan với dataset và indexes gần tình huống thật.

## 25. Best practices cho fixture và data isolation

1. Dùng business keys duy nhất trong mỗi test (ví dụ `CAM-001`, `CAM-HIGH`) hoặc thêm prefix run ID khi parallel.
2. Dùng fixed `Instant` thay vì `Instant.now()` để tránh flaky time comparisons.
3. Chỉ insert đúng documents cần kiểm tra; không tạo fixture dài không có mục đích.
4. Test query phải có cả matching và nonmatching documents.
5. Khi sort quan trọng, có sort rõ, không dựa vào insertion/natural order.
6. Đối chiếu raw BSON cho mapping quan trọng, đặc biệt `@Field` và nested types.
7. Đừng giữ mutable shared Mongo documents giữa tests nếu chúng có thể bị update.
8. Dọn dữ liệu trong test database riêng; không xóa collection/index không thuộc test.
9. Với Testcontainers, pin MongoDB major image hợp với production và ghi rõ môi trường Docker.
10. Không tiết lộ Mongo credentials/JDBC-like URI với secrets trong logs.
11. Nếu dùng MongoDB index migrations, test migration thật thay vì chỉ annotation.
12. Khi có transactions, assert commit/rollback bằng trạng thái server sau transaction.
13. Đếm executed/disabled tests; không báo “tất cả Mongo tests pass” nếu class bị skip.
14. Không dùng `@DirtiesContext` để coi như xóa MongoDB data: nó loại Spring context cache, không nhất thiết xóa MongoDB server state.

## 26. Bài tập thực hành

### Bài 1 — Chứng minh lưu đúng field names

Chạy `savesAndReloadsMappedDocument`, đổi `@Field("item_code")` thành `@Field("itemCode")` ở một nhánh học tập. Raw BSON assertion `raw.getString("item_code")` và `raw.containsKey("itemCode")` sẽ thể hiện contract bị đổi. Khôi phục annotation.

**Bài học:** Java property name không đồng nhất MongoDB stored field name.

### Bài 2 — Derived query với ngưỡng biên

Trong test `derivedQueryUsesJavaPropertiesAndSortsPrice`, đổi minimum từ 20000 lên 25000. `CAM-MID` có giá đúng 25000 phải còn trong kết quả vì predicate là greater-than-or-equal. Nếu đổi thành `GreaterThan`, expected thay đổi thế nào?

### Bài 3 — `@Query` với input động

Thêm một category chứa ký tự đặc biệt (ví dụ dấu nháy đơn) vào fixture và gọi `findAffordableInCategory`. Kiểm tra Spring Data binding `?0` giữ đúng scalar value và không bị parser injection do tự nối string.

### Bài 4 — Bỏ sort rồi quan sát test

Bỏ `OrderByPriceCentsAsc` trong repository method, giữ assertion list order. Test có thể pass ngẫu nhiên ở môi trường nhỏ nhưng không còn hợp đồng thứ tự. Khôi phục sort và giải thích vì sao natural order không an toàn.

### Bài 5 — Tắt auto index creation

Tạm bỏ property `spring.data.mongodb.auto-index-creation=true`. Chạy trên **MongoDB test database mới, trống**, rồi quan sát duplicate-key test. Vì sao annotation `@Indexed(unique=true)` chưa đủ? Khôi phục property.

### Bài 6 — Null vs missing

Tạo một raw `Document` có `details=null` và một document không có field `details`. Dùng MongoTemplate query với `Criteria.where("details").exists(false)` và phép kiểm tra `$eq: null` thích hợp. Ghi nhận khác biệt MongoDB query semantics.

### Bài 7 — Bật Testcontainers trong CI

Đặt `RUN_MONGO_TESTS=true`, chạy tests trên agent có Docker. Ghi nhận số methods pass thật (8) và phân biệt với build chỉ có disabled tests khi biến môi trường không được bật.

### Bài 8 — Thêm `@Version`

Thêm version field vào entity, viết test tạo hai snapshots, save snapshot A rồi cố save snapshot B cũ. Assert optimistic locking failure và persisted data. Lưu ý write concern/context support.

### Bài 9 — Nested document query

Thêm query tìm theo `details.brand` (ví dụ `Criteria.where("details.brand").is("ACME")`), tạo một item ACME và một item khác. Assert đúng tập kết quả; không cần một collection `ItemDetails` riêng.

### Bài 10 — Service integration

Tạo `InventoryService` dùng repository. Viết một JUnit unit test mock repository cho business decision và một `@DataMongoTest` có `@Import(InventoryService.class)` để kiểm tra đường persistence. Giải thích service bean không được slice tự quét.

### Bài 11 — Reactive query

Tạo một nhánh dùng `spring-boot-starter-data-mongodb-reactive`, `ReactiveMongoRepository` và `StepVerifier`. So sánh `Mono`/`Flux` vs synchronous `Optional`/`List`, không dùng `block()` trong application event loop.

### Bài 12 — Từ test đúng đến migration đúng

Tạo một index migration tường minh cho `item_code`, tắt auto index creation trong test migration và chạy against fresh MongoDB container. Assert index thật được tạo, duplicate key bị từ chối và collection không bị drop ngoài ý đồ.

## 27. Checklist trước khi đánh dấu QA PASS

- [ ] Tôi biết test đang chạy MongoDB server nào và database nào.
- [ ] `@DataMongoTest` chỉ nạp Mongo persistence slice, không bị hiểu nhầm là full application test.
- [ ] Test có MongoDB instance thật hoặc được đánh dấu skip rõ khi thiếu môi trường.
- [ ] Tôi không nói Spring Boot 3.3 tự khởi động embedded MongoDB.
- [ ] Entity `@Document` có đúng collection và `@Id` mapping.
- [ ] Test kiểm tra ít nhất một raw BSON document nếu mapping field là mục tiêu.
- [ ] `@Field` mapping đúng tên đã công bố của storage schema.
- [ ] Derived queries dùng Java property names và đã assert positive/negative fixtures.
- [ ] `@Query` tham số được bind, không tự nối chuỗi input.
- [ ] Query không có sort được test không phụ thuộc thứ tự.
- [ ] Có explicit sort khi paging/ordering là contract.
- [ ] Nested document/array/date mapping được kiểm tra ở cả BSON và Java khi có ý nghĩa.
- [ ] Tôi hiểu `@Indexed` không tự tạo unique index nếu index creation bị tắt.
- [ ] Duplicate-key test thực sự ném lỗi từ MongoDB server.
- [ ] Mongo tests có cleanup/collection isolation, không dựa vào JPA rollback mặc định.
- [ ] Không drop collections/indexes ngẫu nhiên giữa test methods.
- [ ] MongoDB Testcontainers connection details không bị ghi đè bằng localhost/production URI.
- [ ] Testcontainers lifecycle và Spring context cache phù hợp với cách share container.
- [ ] Nếu dùng custom converters, test scope chứa đúng conversion config.
- [ ] Nếu dùng transactions, có transaction manager/topology phù hợp và assertion sau rollback.
- [ ] Test reports nêu chính xác số chạy/skip, không coi skip là pass.
- [ ] Khi nâng Spring Boot major, tôi kiểm tra đúng imports/test modules và MongoDB driver compatibility.

## 28. Quy tắc lựa chọn cuối cùng

```text
Cần chứng minh điều gì?
    |
    +--> Business logic với repository giả?
    |      -> JUnit + Mockito; không cần MongoDB.
    |
    +--> Document mapping, @Field, MongoRepository,
    |    derived query, @Query, MongoTemplate, index?
    |      -> @DataMongoTest + MongoDB test server.
    |
    +--> Service phối hợp nhiều repositories/beans?
    |      -> @DataMongoTest + @Import service khi nhỏ,
    |         hoặc @SpringBootTest với Mongo test server.
    |
    +--> HTTP/JSON + MongoDB end to end?
    |      -> @SpringBootTest(RANDOM_PORT) và client thật,
    |         cùng MongoDB Testcontainers.
    |
    +--> MongoDB transaction/sharding/failover/prod index plan?
           -> Môi trường đúng topology/engine/version,
              test đặc thù có isolation và dữ liệu phù hợp.
```

**Thông điệp cốt lõi:** `@DataMongoTest` là một **Spring context slice** cho MongoDB; nó không tự biến mock repository thành database thật và không tự khởi động một server embedded. Khi kết hợp MongoDB Testcontainers và các assertions trên raw BSON, repository query, index và cleanup, bạn có thể kiểm tra chính xác mapping/query behavior với chi phí thấp hơn full application test — đồng thời tránh nhầm rollback của JPA và không chạm vào database ngoài phạm vi test.

## 29. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, `@DataMongoTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Test Slices auto-configuration: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Boot 3.3 — Testcontainers và `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — MongoDB configuration: https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html
- Spring Data MongoDB — MongoDB object mapping: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html
- Spring Data MongoDB — Index creation: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html
- Spring Data MongoDB — Query methods và `@Query`: https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html
- Spring Data MongoDB — MongoTemplate query DSL: https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html
- Spring Data MongoDB — MongoDB transactions: https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html
- MongoDB — BSON Date and Extended JSON: https://www.mongodb.com/docs/manual/reference/bson-types/
- MongoDB — Unique indexes: https://www.mongodb.com/docs/manual/core/index-unique/
- Testcontainers Java — MongoDB module: https://java.testcontainers.org/modules/databases/mongodb/
- JUnit Jupiter — Conditional test execution: https://docs.junit.org/current/user-guide/
