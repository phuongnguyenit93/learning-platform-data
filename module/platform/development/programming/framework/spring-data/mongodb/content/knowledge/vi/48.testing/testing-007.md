# Fixture, index, validator và collection kiểm thử

Trong ứng dụng **Spring Data MongoDB**, một bài kiểm thử repository có thể chạy xanh dù hệ thống thật vẫn lỗi: dữ liệu test chưa được chuẩn bị đúng kiểu BSON, chỉ mục unique chưa được tạo, collection không có schema validator, hoặc các bài test sử dụng chung dữ liệu và ảnh hưởng lẫn nhau. Ngược lại, một test chỉ kiểm tra `MongoTemplate.insert(...)` cũng chưa chứng minh được rằng MongoDB từ chối bản ghi sai cấu trúc và thực thi truy vấn theo chỉ mục mong muốn.

Bài học này xây dựng **môi trường kiểm thử có thể tái tạo** cho một collection MongoDB, gồm bốn thành phần đi cùng nhau:

1. **Fixture**: tập document đầu vào và kết quả mong đợi được kiểm soát.
2. **Collection kiểm thử**: namespace thực sự để lưu dữ liệu, với vòng đời tạo/dọn dẹp rõ ràng.
3. **Index**: các ràng buộc và đường truy cập dữ liệu như unique, compound hoặc TTL.
4. **Validator**: quy tắc phía MongoDB kiểm tra hình dạng document và kiểu BSON.

Các ví dụ sử dụng `MongoTemplate`, repository, JUnit 5 và Testcontainers. Chúng giúp kiểm thử thao tác CRUD, truy vấn, index và chuyển đổi BSON trên MongoDB thật trong môi trường cách ly, đồng thời chỉ ra cách tránh những test xanh giả hoặc test phụ thuộc vào thứ tự chạy.

## 1. Vì sao phải kiểm thử cả fixture, index và validator?

Giả sử một dịch vụ lưu sản phẩm trong collection `products`:

```javascript
{
  _id: "p-001",
  sku: "SKU-001",
  name: "Bàn phím",
  priceInCents: NumberLong("129900"),
  active: true
}
```

Quy tắc nghiệp vụ:

- Mỗi `sku` chỉ xuất hiện **một lần** trong collection.
- `sku` là chuỗi không rỗng; `priceInCents` là số nguyên 64-bit không âm; `active` là Boolean.
- Truy vấn tìm sản phẩm theo `sku` phải trả đúng document, kể cả khi dữ liệu có thêm nhiều sản phẩm khác.
- Các bài kiểm thử có thể chạy lặp lại mà không còn dữ liệu từ lượt trước.

Nếu chỉ dùng Java validation như `@NotBlank`, `@PositiveOrZero`, hệ thống có thể kiểm tra ở tầng ứng dụng khi kích hoạt Bean Validation, nhưng thao tác ghi trực tiếp qua driver, script hoặc service khác vẫn có thể bỏ qua logic đó. **MongoDB collection validator** tạo thêm một lớp kiểm tra tại database. **Unique index** mới là thành phần bảo đảm tính duy nhất khi nhiều luồng ghi đồng thời; câu lệnh `existsBySku(...)` rồi `save(...)` không ngăn được race condition.

| Thành phần | Bảo đảm điều gì? | Không thể thay thế |
| --- | --- | --- |
| Fixture | Test có dữ liệu chuẩn, trường hợp biên và kết quả dự kiến | Không tự áp đặt ràng buộc dữ liệu trên MongoDB |
| Collection kiểm thử | Có nơi chứa document và cơ chế cô lập/dọn dẹp | Không tự có index hay validator đúng yêu cầu |
| Unique index | MongoDB từ chối khóa trùng trên các document phù hợp | Không tự kiểm tra mọi kiểu BSON hoặc quy tắc nghiệp vụ |
| Schema validator | MongoDB kiểm tra cấu trúc, kiểu dữ liệu, trường bắt buộc | Không tự tạo unique index |
| Assertion | Đối chiếu hành vi thực tế với yêu cầu | Không có giá trị nếu setup dữ liệu không đại diện |

## 2. Chọn cấp độ kiểm thử

Không phải mọi test đều cần khởi động MongoDB:

| Cấp độ | Mục tiêu | Công cụ gợi ý |
| --- | --- | --- |
| Unit test | Hàm xây dựng query, xử lý giá trị, quy tắc trong service | JUnit, Mockito, không cần database |
| Spring Data slice test | Mapping entity, repository, `MongoTemplate` và truy vấn trên MongoDB | `@DataMongoTest` cùng một MongoDB test thật |
| Integration test | Unique index, validator, transaction, aggregation, concurrency, thực thi server | Testcontainers hoặc MongoDB test riêng có cấu hình sát production |
| End-to-end test | HTTP/API đến MongoDB cùng các thành phần phụ thuộc | `@SpringBootTest`, môi trường tích hợp phù hợp |

Mock `MongoRepository` có thể kiểm tra service xử lý kết quả trả về, nhưng không kiểm tra được MongoDB có tạo chỉ mục hay từ chối document sai schema. Các tính năng như `$jsonSchema`, unique index, aggregation và transaction nên có bài kiểm thử với **MongoDB thật**. Tránh suy luận rằng một database giả hoặc mock triển khai đầy đủ mọi toán tử, hành vi BSON hay giới hạn của MongoDB Server.

Với Spring Boot, `@DataMongoTest` thu hẹp application context cho các thành phần MongoDB cần thiết; annotation **không tự tạo một MongoDB server**. Ta có thể cấp kết nối từ Testcontainers. Ví dụ bên dưới là mô hình chung; dependency, API Testcontainers và cách cấu hình kết nối cần khớp phiên bản Spring Boot/Spring Data/MongoDB Java Driver thực tế.

## 3. Thiết kế fixture có thể chạy lại

Fixture là dữ liệu có chủ đích nhằm kiểm tra một hoặc nhiều hành vi. Một fixture tốt có các đặc điểm:

- **Xác định trước:** dùng `_id`, `sku`, trạng thái, số tiền và timestamp cố định. Nếu cần thời gian hiện tại, truyền `Clock` có thể điều khiển vào service thay vì gọi `Instant.now()` trực tiếp trong mọi test.
- **Đủ khác biệt:** mỗi record có một mục đích rõ ràng; ví dụ sản phẩm active/inactive, giá bằng 0, giá ở ranh giới lớn, SKU gần giống nhau.
- **Độc lập:** mỗi test bắt đầu từ cùng trạng thái hoặc có database/collection riêng; không phụ thuộc vào test khác đã insert hay xóa gì.
- **Phù hợp BSON:** khi test cần kiểu `long`, hãy dùng giá trị được lưu thực sự dưới BSON Int64 thay vì chuỗi `"129900"`.
- **Có cả ca thành công và ca thất bại:** dữ liệu sai kiểu/trùng khóa là fixture âm tính, không được đưa vào bộ fixture hợp lệ dùng chung.
- **Nhỏ nhưng có ý nghĩa:** một vài document chính xác tốt hơn hàng nghìn record ngẫu nhiên cho kiểm thử nghiệp vụ; dữ liệu lớn để kiểm thử query plan/hiệu năng là bộ fixture riêng.

Ví dụ trạng thái ban đầu:

| `_id` | `sku` | `name` | `priceInCents` | `active` | Mục đích |
| --- | --- | --- | ---: | --- | --- |
| `p-001` | `SKU-001` | Bàn phím | 129900 | `true` | Tìm theo SKU thành công |
| `p-002` | `SKU-002` | Chuột | 0 | `false` | Kiểm tra giá bằng 0 và trạng thái |
| `p-003` | `SKU-003` | Màn hình | 4999000 | `true` | Thêm giá trị khác để kiểm tra lọc |

**Không nên** tạo một chuỗi fixture khó đoán bằng `UUID.randomUUID()` hoặc ngày giờ thực tế nếu các giá trị ngẫu nhiên không phải chủ đề đang được kiểm thử. Trường hợp cần dữ liệu ngẫu nhiên hoặc property-based testing, cố định seed và lưu seed khi test thất bại để có thể tái hiện.

## 4. Entity và repository của ví dụ

Trong các phiên bản Spring Data MongoDB hiện đại có hỗ trợ Java record, có thể mô tả một document đơn giản bằng:

```java
package example.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record Product(
    @Id String id,
    @Indexed(unique = true, name = "ux_products_sku") String sku,
    String name,
    long priceInCents,
    boolean active
) {}
```

Repository:

```java
package example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
```

`@Document("products")` xác định collection; `@Id` ánh xạ `id` với `_id`; `@Indexed(unique = true)` mô tả chủ đích tạo unique index. Tuy nhiên, **Spring Data MongoDB không bảo đảm index được tự động tạo ở mọi cấu hình**; trong các phiên bản hiện đại, auto-index creation thường mặc định tắt. Test cần chủ động thiết lập index hoặc chạy chính cơ chế migration/index management mà production dùng. Nếu bật auto-index creation, phải bảo đảm định nghĩa và tên index từ annotation thống nhất với index được tạo thủ công để tránh xung đột cấu hình.

`long priceInCents` được lưu thành BSON Int64 theo ánh xạ Java Driver tiêu chuẩn. Dùng đơn vị nhỏ nhất của tiền tệ là một lựa chọn để tránh sai số dấu phẩy động trong ví dụ. Nếu ứng dụng lưu `BigDecimal`, cần kiểm thử mapping BSON Decimal128 hoặc custom conversion đúng với cấu hình thực tế, chứ không tự suy từ kiểu Java.

## 5. Kết nối MongoDB test bằng Testcontainers

Một cấu hình minh họa cho Spring Boot + JUnit 5:

```java
package example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataMongoTest
@Testcontainers
class ProductRepositoryTest {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            () -> mongo.getReplicaSetUrl("catalog_test")
        );
    }

    @Autowired
    MongoTemplate mongoTemplate;

    @Autowired
    ProductRepository repository;

    // Các hàm @BeforeEach và @Test sẽ được thêm ở phần sau.
}
```

Các import bổ sung cho `MongoTemplate` và JUnit:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.junit.jupiter.api.BeforeEach;
```

Chuẩn bị dependencies tương ứng trong **test scope**: Spring Boot Test, Spring Data MongoDB, JUnit 5, Testcontainers MongoDB và tích hợp Testcontainers JUnit Jupiter. Máy chạy test cần môi trường container khả dụng. Có thể dùng `@ServiceConnection` thay cho `@DynamicPropertySource` trên phiên bản Spring Boot/Testcontainers tương thích; hãy chọn **một** cách cấu hình để tránh mâu thuẫn URI.

Ví dụ dùng image `mongo:7.0` để minh họa môi trường có server thật, không có nghĩa mọi dự án phải dùng đúng tag này. Với MongoDB feature có phụ thuộc phiên bản (validator, collation, transaction, search...), hãy chọn image tương thích môi trường production và khóa phiên bản image trong pipeline CI. Không dựa vào `latest` nếu mục tiêu là phép thử lặp lại.

## 6. Tạo collection và validator có chủ đích

MongoDB có thể tự tạo collection khi insert document lần đầu, nhưng khi đó collection sẽ không tự có validator do ứng dụng kỳ vọng. Với bài test phải kiểm tra schema, hãy **tạo collection trước khi seed fixture**.

Schema dưới đây yêu cầu:

- `sku` có mặt, là String và có độ dài tối thiểu 1;
- `priceInCents` có mặt, là BSON Int64 và không âm;
- `active` có mặt, là Boolean;
- `name` nếu có phải là String.

Code Java Driver dùng cùng `MongoDatabase` mà `MongoTemplate` kết nối:

```java
import java.util.List;

import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.ValidationAction;
import com.mongodb.client.model.ValidationLevel;
import com.mongodb.client.model.ValidationOptions;
import org.bson.Document;

private void createValidatedProductsCollection() {
    Document properties = new Document()
        .append("sku", new Document("bsonType", "string")
            .append("minLength", 1))
        .append("name", new Document("bsonType", "string"))
        .append("priceInCents", new Document("bsonType", "long")
            .append("minimum", 0))
        .append("active", new Document("bsonType", "bool"));

    Document jsonSchema = new Document("bsonType", "object")
        .append("required", List.of("sku", "priceInCents", "active"))
        .append("properties", properties);

    ValidationOptions validation = new ValidationOptions()
        .validator(new Document("$jsonSchema", jsonSchema))
        .validationLevel(ValidationLevel.STRICT)
        .validationAction(ValidationAction.ERROR);

    CreateCollectionOptions options = new CreateCollectionOptions()
        .validationOptions(validation);

    mongoTemplate.getDb().createCollection("products", options);
}
```

`$jsonSchema` sử dụng các tên kiểu BSON như `"long"` và `"bool"`; đây không phải cú pháp `type: "integer"` của JSON Schema thông thường. BSON `int` (Int32) và `long` (Int64) là hai kiểu khác nhau. Nếu fixture dùng `new Document("priceInCents", 129900)`, giá trị đó thường là Int32 và có thể bị validator ở trên từ chối, trong khi `129900L` là Long và được BSON encoder ghi thành Int64.

Đặc biệt chú ý các lựa chọn:

| Cấu hình | Ý nghĩa khi test |
| --- | --- |
| `validationAction: "error"` | Vi phạm validator làm thao tác ghi thất bại; phù hợp test cần khẳng định ràng buộc |
| `validationAction: "warn"` | Ghi có thể vẫn thành công nhưng phát cảnh báo; không thích hợp nếu assertion kỳ vọng lỗi |
| `validationLevel: "strict"` | Áp dụng validation cho insert và update theo quy tắc MongoDB |
| `validationLevel: "moderate"` | Có khác biệt khi update document đã tồn tại và không hợp lệ; phải kiểm thử theo mục tiêu migration |
| `required` | Yêu cầu trường tồn tại; muốn từ chối `null` còn phải chọn `bsonType` không chấp nhận `null` |
| `additionalProperties: false` | Hạn chế trường ngoài schema; cẩn thận với `_id`, `_class` và các trường do framework ghi |

**Giới hạn cần nhớ:** tạo hoặc thay đổi validator không tự sửa dữ liệu cũ vốn đã sai schema. Khi dùng `collMod` để bổ sung validator vào collection có sẵn, cần quyết định xử lý document cũ và hành vi khi update. Không dùng validator thay thế unit test cho mọi quy tắc nghiệp vụ phức tạp.

## 7. Tạo index trước khi chạy truy vấn và fixture

Tạo index bằng `MongoTemplate`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

private void createProductsIndexes() {
    mongoTemplate.indexOps("products").ensureIndex(
        new Index()
            .on("sku", Sort.Direction.ASC)
            .unique()
            .named("ux_products_sku")
    );
}
```

Khóa `sku` phải duy nhất. Khi thử insert sản phẩm trùng SKU, database sẽ phát lỗi duplicate key, thường có **mã lỗi MongoDB 11000**. Spring Data có cơ chế dịch nhiều lỗi driver sang các ngoại lệ `DataAccessException`; ví dụ duplicate key được biểu diễn bằng `DuplicateKeyException` ở tầng `MongoTemplate`/repository.

Các loại index cần được kiểm thử tùy ứng dụng:

| Loại | Ví dụ | Lưu ý |
| --- | --- | --- |
| Unique | `{ sku: 1 }` | Kiểm thử insert trùng và cập nhật thành khóa trùng |
| Compound | `{ active: 1, priceInCents: -1 }` | Xem query shape gồm filter, sort, projection; thứ tự field quan trọng |
| Partial | Unique chỉ với `active: true` | Fixture phải có cả record nằm trong và ngoài điều kiện partial filter |
| Sparse | Index bỏ qua một số document thiếu trường | Hành vi với `null` và unique cần kiểm tra đúng phiên bản/quy tắc |
| TTL | Xóa document hết hạn dựa trên trường ngày giờ | Xóa bởi TTL monitor là bất đồng bộ, không nên assert bị xóa ngay tại thời điểm đến hạn |
| Text / geospatial | Tra cứu theo từ khóa hoặc tọa độ | Cần dữ liệu và assertion phù hợp toán tử/index thật |

**Unique index không tương đương unique trong một ứng dụng Java.** Nó được MongoDB thực thi ở mức collection và bảo vệ cả khi có nhiều service cùng ghi. Test tạo dữ liệu duplicate sau khi index đã tồn tại sẽ kiểm tra đúng ràng buộc này. Nếu insert các bản ghi trùng **trước** rồi mới tạo index unique, việc tạo index có thể thất bại; đó là một ca migration/index riêng cũng nên được kiểm thử.

## 8. Dựng và dọn fixture trước mỗi bài test

Với test chạy tuần tự, chia sẻ một database dành riêng cho lớp test, có thể dùng `@BeforeEach` để thiết lập lại collection. Các method bên dưới đặt **trong `ProductRepositoryTest`** đã giới thiệu:

```java
@BeforeEach
void prepareCollectionAndFixtures() {
    if (mongoTemplate.collectionExists("products")) {
        mongoTemplate.dropCollection("products");
    }

    // Phải tạo schema và index trước khi insert fixture.
    createValidatedProductsCollection();
    createProductsIndexes();

    mongoTemplate.insert(
        new Product("p-001", "SKU-001", "Bàn phím", 129900L, true)
    );
    mongoTemplate.insert(
        new Product("p-002", "SKU-002", "Chuột", 0L, false)
    );
    mongoTemplate.insert(
        new Product("p-003", "SKU-003", "Màn hình", 4999000L, true)
    );
}
```

Vì sao theo thứ tự này?

1. Nếu test trước đã thay đổi collection hoặc index, drop giúp xóa trạng thái đó.
2. Tạo lại collection **khôi phục validator**, vì `dropCollection` xóa cả collection lẫn index của nó.
3. Tạo index trước khi seed giúp phát hiện ngay fixture sai ràng buộc unique.
4. Insert các record với `_id` cố định giúp assertion rõ ràng và phát hiện dữ liệu rò rỉ qua các test.

Phương pháp drop/recreate phù hợp với database thử nghiệm **cách ly và được phép hủy dữ liệu**. Tuyệt đối không dùng setup này trỏ vào database đang phục vụ người dùng hoặc dữ liệu cần giữ. Nếu nhiều test class chạy song song cùng database và tên collection, drop của một test có thể phá test khác. Với parallel test, dùng database/collection tách biệt cho từng test class hoặc quản lý scope của fixture tương ứng.

### 8.1. Xóa document hay drop collection?

Hai cách reset có mục đích khác nhau:

```java
// Xóa document nhưng GIỮ collection, validator và index.
mongoTemplate.remove(new Query(), "products");

// Xóa cả collection, đồng thời xóa validator và index.
mongoTemplate.dropCollection("products");
```

Import của `Query`:

```java
import org.springframework.data.mongodb.core.query.Query;
```

Khi chỉ cần reset dữ liệu và muốn giữ cấu hình schema/index cố định, dùng xóa document rồi seed lại thường giảm thời gian setup. Khi test kiểm tra **chính quá trình tạo validator/index/collection**, tạo lại từ đầu đáng tin cậy hơn. Không nên vừa drop collection vừa giả định rằng unique index hoặc validator đã tồn tại từ lần test trước.

## 9. Kiểm thử đọc, unique index và schema validator

### 9.1. Đọc fixture bằng repository

Một test đơn giản phải xác nhận đúng dữ liệu ban đầu:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

@Test
void findsProductBySku() {
    Product product = repository.findBySku("SKU-001").orElseThrow();

    assertThat(product.id()).isEqualTo("p-001");
    assertThat(product.name()).isEqualTo("Bàn phím");
    assertThat(product.priceInCents()).isEqualTo(129900L);
    assertThat(product.active()).isTrue();
}
```

Nếu test này chạy xanh nhưng chưa tạo unique index, nó vẫn chỉ chứng minh *đọc đúng* trong fixture hiện tại. Nó chưa kiểm chứng ràng buộc uniqueness hoặc query plan.

### 9.2. Duplicate key phải bị từ chối

```java
import org.springframework.dao.DuplicateKeyException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsDuplicateSku() {
    assertThatThrownBy(() ->
        repository.save(
            new Product("p-new", "SKU-001", "Sản phẩm khác", 1000L, true)
        )
    ).isInstanceOf(DuplicateKeyException.class);

    // Không được ghi thêm document sau lần insert thất bại.
    assertThat(mongoTemplate.getCollection("products")
        .countDocuments()).isEqualTo(3L);
}
```

Test này xác minh constraint do **database** áp đặt. Không cần gọi `repository.existsBySku` trước khi insert; nếu làm vậy, test có thể che khuất vấn đề index chưa tồn tại.

### 9.3. Validator từ chối BSON sai kiểu

Dùng raw MongoDB Driver để chủ động tạo một document sai kiểu, không để Spring Data converter vô tình chuẩn hóa dữ liệu trước khi ghi:

```java
import com.mongodb.MongoWriteException;
import org.bson.Document;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void rejectsInvalidBsonType() {
    MongoWriteException error = assertThrows(
        MongoWriteException.class,
        () -> mongoTemplate.getCollection("products").insertOne(
            new Document("_id", "bad-001")
                .append("sku", "SKU-BAD")
                .append("name", "Không hợp lệ")
                .append("priceInCents", "129900") // String thay vì Long
                .append("active", true)
        )
    );

    assertEquals(121, error.getCode()); // DocumentValidationFailure
}
```

Mã 121 là mã lỗi MongoDB thường gặp cho document validation failure; trong test tích hợp thực tế, kiểm tra mã lỗi hữu ích hơn so sánh nguyên văn thông báo, vì thông báo có thể thay đổi theo phiên bản hoặc chứa chi tiết khác nhau.

Thêm ca thiếu trường bắt buộc:

```java
@Test
void rejectsMissingRequiredField() {
    MongoWriteException error = assertThrows(
        MongoWriteException.class,
        () -> mongoTemplate.getCollection("products").insertOne(
            new Document("_id", "bad-002")
                .append("sku", "SKU-NO-PRICE")
                .append("active", true)
        )
    );

    assertEquals(121, error.getCode());
}
```

Trường `priceInCents` vắng mặt bị validator từ chối. Giá trị `null` cũng bị từ chối trong schema hiện tại vì `bsonType: "long"` không cho phép BSON Null. Nếu nghiệp vụ cho phép null, cần khai báo kiểu phù hợp và kiểm thử riêng.

### 9.4. Xác nhận unique index thật sự tồn tại

Việc chỉ có annotation `@Indexed` trong source không phải bằng chứng rằng index đã được tạo:

```java
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

@Test
void createsUniqueSkuIndex() {
    List<Document> indexes = mongoTemplate.getCollection("products")
        .listIndexes()
        .into(new ArrayList<>());

    Document skuIndex = indexes.stream()
        .filter(index -> "ux_products_sku".equals(index.getString("name")))
        .findFirst()
        .orElseThrow();

    assertThat(skuIndex.get("key", Document.class))
        .containsEntry("sku", 1);
    assertThat(skuIndex.getBoolean("unique")).isTrue();
}
```

Kiểm thử sự **tồn tại và cấu hình** của index khác kiểm thử **MongoDB thực sự chọn index để truy vấn**. Với collection chỉ có ba document, planner có thể chọn collection scan vì rẻ hơn, nên không nên viết assertion cứng `explain` phải có `IXSCAN`. Để khảo sát query plan, tạo dataset phù hợp, đọc `explain("executionStats")` và giải thích kết quả theo quy mô/độ chọn lọc của truy vấn.

## 10. Kiểm thử index phức hợp và truy vấn sắp xếp

Khi ứng dụng thường lấy các sản phẩm đang bán theo thứ tự giá giảm dần, có thể có một index ứng viên:

```javascript
db.products.createIndex({ active: 1, priceInCents: -1 });
```

Tạo cùng index bằng Spring Data:

```java
mongoTemplate.indexOps("products").ensureIndex(
    new Index()
        .on("active", Sort.Direction.ASC)
        .on("priceInCents", Sort.Direction.DESC)
        .named("ix_products_active_price_desc")
);
```

Truy vấn:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(Criteria.where("active").is(true))
    .with(Sort.by(Sort.Direction.DESC, "priceInCents"))
    .limit(10);

List<Product> products = mongoTemplate.find(query, Product.class);
```

Để xác minh kết quả, fixture phải có nhiều sản phẩm `active = true` với giá khác nhau; assert thứ tự trả về và số lượng. Nếu muốn kiểm tra lợi ích của index, dùng dataset lớn hơn, thống kê `totalDocsExamined`, `totalKeysExamined`, các stage `IXSCAN`/`SORT` và số document được trả về. Việc tạo index trong bài test nhỏ chỉ khẳng định API tạo index hoạt động, không bảo đảm kế hoạch tối ưu trong production.

## 11. Trường hợp cần transaction, reference và nhiều collection

Khi một hành vi nghiệp vụ thao tác nhiều collection, chẳng hạn `orders` và `orderItems`, fixture cần mô tả **các quan hệ giữa document**:

- Seed parent trước child nếu code cần lấy khóa parent; kiểm tra ID được dùng nhất quán.
- Dọn cả hai collection và index/validator của từng collection. Thứ tự dọn nên bảo đảm không còn luồng đang đọc dữ liệu cũ.
- Nếu dùng `@DBRef` hay `@DocumentReference`, kiểm thử khả năng resolve tham chiếu thực tế; MongoDB không tự áp đặt foreign key constraint như relational database.
- Transaction trong MongoDB yêu cầu topology và cấu hình phù hợp, chẳng hạn replica set hoặc môi trường hỗ trợ transaction; nếu test bằng standalone không có transaction, lỗi không phản ánh đúng năng lực chương trình khi chạy trên replica set.
- Với concurrency test và unique constraint, nên khởi tạo fixture chung trước khi chạy các tác vụ cạnh tranh, chờ tất cả tác vụ kết thúc rồi xác nhận số document thực sự được lưu. Tránh assert dựa vào thứ tự thread hoàn thành nếu không có hợp đồng rõ ràng.

Một test service có `@Transactional` chỉ chứng minh transaction khi môi trường cấu hình `MongoTransactionManager` phù hợp và thao tác đi qua transaction thực. Không lấy việc annotation tồn tại làm bằng chứng MongoDB thực sự rollback.

## 12. Collection validator và cập nhật dữ liệu cũ

Với collection đã có dữ liệu, đôi khi cần bổ sung schema validator bằng lệnh `collMod`. Ví dụ minh họa trong `mongosh`:

```javascript
db.runCommand({
  collMod: "products",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "priceInCents", "active"],
      properties: {
        sku: { bsonType: "string", minLength: 1 },
        priceInCents: { bsonType: "long", minimum: 0 },
        active: { bsonType: "bool" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Những bài test nên kiểm tra:

1. Document hợp lệ trước migration vẫn đọc/ghi được.
2. Document không hợp lệ đã tồn tại **không tự được sửa** khi thêm validator.
3. Insert/update mới vi phạm schema bị từ chối khi dùng `strict/error`.
4. Nếu chọn `moderate` hoặc `warn` để chuyển tiếp dữ liệu cũ, kiểm thử đúng hành vi chấp nhận/từ chối tương ứng.
5. Khi chuyển đổi BSON từ String sang Long hoặc Decimal128, xác nhận dữ liệu sau migration phù hợp validator mới trước khi bật chế độ chặn lỗi nghiêm ngặt.

Một số client đặc quyền có thể dùng tùy chọn `bypassDocumentValidation` trong những hoàn cảnh được cấp phép. Vì vậy một test negative nên đi theo đường ghi thực tế của ứng dụng, không vô tình bật chế độ bỏ qua kiểm tra.

Đặc biệt, validator là **quy tắc của MongoDB**; nó khác với validation bằng annotation Jakarta Bean Validation trên entity. Hai lớp có thể cùng tồn tại nhưng phải được kiểm thử riêng nếu ứng dụng dùng cả hai.

## 13. Cách tránh test thiếu ổn định

| Dấu hiệu | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Test chạy riêng xanh, chạy cả suite đỏ | Các test dùng chung database và để lại dữ liệu | Tạo fixture độc lập, dọn đúng collection hoặc tách database |
| Duplicate SKU vẫn insert được | Unique index chưa tồn tại hoặc đang index sai field/điều kiện | Kiểm tra `listIndexes()`, tạo index trước khi seed |
| Test validator không báo lỗi | Collection được tạo tự động không có validator; `warn`; test dùng sai collection | Tạo collection bằng options rõ ràng và kiểm tra cấu hình |
| Test kỳ vọng BSON Long nhưng server nhận Int32 | Fixture dùng literal Java `int`/`Document` sai kiểu | Dùng `129900L` và đọc lại BSON khi cần |
| Test dữ liệu ngày tháng thỉnh thoảng thất bại | Dùng thời gian thực hoặc phụ thuộc múi giờ | Dùng `Instant`/`Clock` cố định, định nghĩa timezone rõ ràng |
| Test TTL bị chậm/flaky | TTL monitor không xóa ngay khi hết hạn | Không dùng thời điểm xóa tức thời làm assertion đồng bộ |
| Test query plan luôn đòi `IXSCAN` | Dataset quá nhỏ hoặc planner có nhiều kế hoạch hợp lệ | Test kết quả riêng; đánh giá kế hoạch bằng workload phù hợp |
| Không chạy được test trong CI | Thiếu Docker/container runtime, pull image lỗi hoặc sai version | Khai báo phụ thuộc môi trường, cố định image và chuẩn bị CI |
| Test transaction không hoạt động | Server không hỗ trợ topology/transaction cần thiết | Dùng replica set/Testcontainers phù hợp và cấu hình transaction |
| Tests song song mất collection bất ngờ | Một test drop collection đang được test khác sử dụng | Cô lập namespace theo class/test và điều phối song song |

### Tách trách nhiệm setup và assertion

Một thiết kế thực dụng:

- **Fixture factory** tạo entity/document với dữ liệu cố định, giúp mỗi test thể hiện rõ giá trị nào đang thay đổi.
- **Collection initializer** tạo validator và index theo cùng phiên bản schema mà production dùng; test không viết một schema khác với deploy thật.
- **Test setup** quyết định reset dữ liệu trước mỗi test, tránh biến business test thành một chuỗi thao tác migration dài.
- **Test assertion** kiểm tra cả kết quả thành công và lỗi từ database; không chỉ khẳng định một phương thức được gọi.

Tuy nhiên, không nên trừu tượng hóa mọi fixture thành một framework riêng phức tạp. Khi dữ liệu chỉ có ba document, builder đơn giản hoặc helper ngắn thường dễ đọc hơn hệ thống factory nhiều lớp.

## 14. Bài tập thực hành

**Bài toán:** xây dựng bài kiểm thử repository cho collection `products` với hai yêu cầu: tìm sản phẩm theo SKU, và database phải từ chối SKU trùng cũng như document thiếu hoặc sai kiểu `priceInCents`.

Tiến hành:

1. Tạo `Product`, `ProductRepository` và test slice `@DataMongoTest` sử dụng MongoDB từ Testcontainers.
2. Tạo collection `products` với `$jsonSchema` ở chế độ `strict/error` và index unique trên `sku`; đọc lại metadata để xác nhận.
3. Seed ba document xác định trước với `_id` cố định và `priceInCents` kiểu Long.
4. Viết test đọc theo SKU, test insert trùng SKU, test thiếu trường bắt buộc và test lưu String vào trường BSON Long.
5. Chạy các test độc lập rồi chạy toàn bộ suite nhiều lượt; nếu bật chạy song song, cô lập database hoặc collection để tránh xung đột.
6. Tạo thêm index compound `{ active: 1, priceInCents: -1 }` và truy vấn sắp xếp; kiểm thử thứ tự kết quả trên fixture đủ phong phú.
7. Thử một tình huống fixture được insert trước khi tạo unique index, quan sát lỗi tạo index khi dữ liệu trùng và giải thích cách tránh trong quy trình migration.

Mẫu kết quả mong đợi:

| Test | Kỳ vọng |
| --- | --- |
| `findBySku("SKU-001")` | Trả sản phẩm `p-001` đúng giá và trạng thái |
| Insert `SKU-001` lần thứ hai | Duplicate key, không có document mới |
| Insert `priceInCents: "129900"` | MongoDB từ chối vì BSON String |
| Insert thiếu `priceInCents` | MongoDB từ chối theo `required` |
| `listIndexes()` | Có index `ux_products_sku` với thuộc tính `unique: true` |
| Chạy suite lần hai | Kết quả không phụ thuộc vào dữ liệu của lần chạy trước |

**Tiêu chí hoàn thành:** test thực sự sử dụng MongoDB với cấu hình index và validator đã xác minh; fixture được tạo lại có kiểm soát; cả thao tác hợp lệ lẫn bất hợp lệ đều có assertion; không phụ thuộc vào thứ tự test hoặc hành vi bất đồng bộ như xóa TTL tức thời.

## 15. Những điểm cần ghi nhớ

- **Fixture có thể tái lập là nền tảng của integration test.** Dùng ID, thời gian và kiểu BSON ổn định, cô lập dữ liệu giữa các test.
- **Index và validator là cấu hình của collection**, không tự xuất hiện chỉ vì entity có annotation hay test insert thành công.
- **Tạo collection, validator và index trước khi seed** nếu mục tiêu là kiểm thử các ràng buộc của MongoDB ngay từ đầu.
- **Unique index** và **`$jsonSchema`** bảo vệ hai nhóm quy tắc khác nhau: tính duy nhất và cấu trúc/kiểu dữ liệu.
- **`@DataMongoTest` + MongoDB test thật** phù hợp để kiểm chứng repository/`MongoTemplate`; mock chỉ thích hợp cho các thành phần không cần hành vi server.
- **Drop collection cũng xóa index và validator**. Chọn reset document hay recreate collection tùy mục tiêu và kiểm soát các test song song.
- **Kiểm thử giá trị và cấu hình riêng**: đọc đúng dữ liệu không đồng nghĩa index đã được tạo; có index không đồng nghĩa planner luôn chọn nó với mọi dataset.
