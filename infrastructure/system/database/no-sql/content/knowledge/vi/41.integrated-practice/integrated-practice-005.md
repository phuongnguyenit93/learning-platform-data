# Xây dựng luồng CRUD từ Java với kiểm tra đầu vào và tài nguyên

Trong **Database No SQL**, một luồng CRUD (*Create, Read, Update, Delete*) có vẻ đơn giản:

~~~text
HTTP request -> Java service -> NoSQL database -> HTTP response
~~~

Nhưng một hệ thống thực tế phải trả lời nhiều câu hỏi hơn là “đã gọi `save()` chưa?”:

- Input có hợp lệ về kiểu, kích thước, giới hạn nghiệp vụ và quyền truy cập không?
- Khi hai clients cùng sửa bản ghi, bản nào được phép ghi đè?
- Nếu database timeout sau khi đã commit, application có biết outcome hay không?
- Connection pool, cursor, HTTP request, thread và bộ nhớ được quản lý thế nào?
- Một truy vấn đọc 10 triệu records có thể làm cạn tài nguyên của dịch vụ không?
- Những lỗi như duplicate key, validation failure, version conflict và backend unavailable được phản hồi khác nhau ra sao?
- Unit test, integration test và kiểm thử concurrency phải chứng minh điều gì?

Bài trong chương **Thực hành tổng hợp** của **Database No SQL** sẽ xây dựng một API quản lý sản phẩm bằng **Java 17, Spring Boot, Spring Data MongoDB**. Ví dụ sử dụng **MongoDB** vì document model giúp nhìn rõ validation, CRUD, atomic update và cursor. Những nguyên tắc cốt lõi cũng áp dụng cho DynamoDB, Cassandra, Redis và các hệ NoSQL khác, nhưng câu lệnh/consistency semantics phải điều chỉnh theo từng engine.

> **Mục tiêu:** hoàn thành một luồng CRUD có hợp đồng dữ liệu rõ ràng, **không tin dữ liệu đầu vào**, không ghi đè phiên bản mới bằng dữ liệu cũ, không mở tài nguyên vô hạn và có kiểm thử cho các failure modes thường gặp.

**Phạm vi:** ví dụ tạo một dịch vụ **catalog nội bộ trong môi trường học tập**. Mẫu API chưa triển khai xác thực/ủy quyền; **không mở public endpoint trong production** nếu chưa thêm authentication, authorization, tenant scoping, rate limits và data governance tương ứng. Phiên bản dependency minh họa là một baseline đã biết, **không được hiểu là phiên bản mới nhất**; khi áp dụng, chọn các phiên bản còn được hỗ trợ và kiểm tra compatibility.

---

## 1. Mục tiêu đầu ra

Sau bài học, người học có thể:

1. Thiết kế CRUD API với request/response DTO tách biệt document lưu trữ.
2. Dùng Bean Validation để kiểm kiểu, giới hạn số và chuỗi.
3. Chuẩn hóa SKU một cách nhất quán và bảo vệ tính duy nhất bằng `_id`.
4. Tạo, đọc, cập nhật, xóa document bằng `MongoTemplate`.
5. Dùng **optimistic concurrency** với `expectedVersion` và atomic condition ở database.
6. Giảm số lượng tồn kho an toàn khi hai requests cùng đặt hàng.
7. Phân trang theo indexed key thay vì trả toàn bộ collection.
8. Phân loại HTTP 400, 404, 409, 422 và 503.
9. Hiểu vòng đời `MongoClient`, pool, cursor, timeout và request budget.
10. Viết integration tests và xử lý timeout/retry/idempotency.
11. Nhận diện những phần cần bổ sung khi đưa code lên production.

## 2. Yêu cầu nghiệp vụ

Quản lý danh mục sản phẩm:

~~~text
Product
  sku          : String, 2..40 ký tự, chỉ A-Z 0-9 . _ -
  name         : String, không trống, tối đa 120 ký tự
  priceCents   : long, >= 0
  stock        : long, >= 0
  version      : long, tăng khi mutation thành công
  createdAt    : Instant (UTC)
  updatedAt    : Instant (UTC)
~~~

Quy tắc:

- Mỗi `sku` là định danh duy nhất.
- Không cho sản phẩm có giá hoặc tồn kho âm.
- Update metadata phải chỉ thành công khi `expectedVersion` trùng.
- Reserve tồn kho phải atomic và không cho `stock` xuống dưới 0.
- Delete cần đúng `expectedVersion` để chặn yêu cầu cũ.
- Read danh sách phải có giới hạn số records.
- Database exceptions không được lộ stack trace, URI có credentials hay dữ liệu nhạy cảm.

`priceCents` ở đây chỉ là **số nguyên đơn vị nhỏ** cho mục đích học tập; trong ứng dụng thật, cần định nghĩa currency và đơn vị nhỏ cho từng loại tiền. Không mặc định mọi currency có đúng hai chữ số thập phân.

## 3. Hợp đồng CRUD HTTP

| Method | Path | Ý nghĩa | Thành công | Thất bại tiêu biểu |
|---|---|---|---|---|
| POST | `/api/v1/products` | Tạo | 201 | 400, 409 |
| GET | `/api/v1/products/{sku}` | Đọc một | 200 | 400, 404 |
| GET | `/api/v1/products?limit=25&after=...` | Đọc có trang | 200 | 400, 503 |
| PUT | `/api/v1/products/{sku}` | Đổi name/price | 200 | 400, 404, 409 |
| POST | `/api/v1/products/{sku}/reservations` | Giảm stock | 200 | 400, 404, 409, 422 |
| DELETE | `/api/v1/products/{sku}?expectedVersion=3` | Xóa có điều kiện | 204 | 400, 404, 409 |

Vì bản demo dùng `expectedVersion` trong request, khi version không khớp ta trả **409 Conflict**. Nếu chuyển sang chuẩn `ETag`/`If-Match`, phản hồi khi precondition thất bại thường là **412 Precondition Failed**, cần định nghĩa riêng.

## 4. Kiến trúc request

~~~mermaid
flowchart TD
  C["HTTP client"] --> V["Controller + DTO validation"]
  V --> S["ProductService / business rules"]
  S --> T["MongoTemplate / mapping"]
  T --> DB["MongoDB products collection"]
  S --> E["Domain exception"]
  E --> H["Global exception handler"]
  H --> R["HTTP ProblemDetail"]
  DB --> T
  T --> S
  S --> V
  V --> C
~~~

Controller chỉ chuyển giao thức HTTP. Service quản lý nghiệp vụ và concurrency. `MongoTemplate` là adapter truy cập NoSQL, **không đưa raw database document ra ngoài API** khi có thể dùng DTO.

## 5. Vì sao chọn một document cho aggregate?

Mỗi Product có `stock`, `priceCents`, `version` nằm cùng một MongoDB document. MongoDB atomic update trong **phạm vi một document** cho phép:

~~~text
WHERE sku = X AND version = V AND stock >= qty
UPDATE stock -= qty, version += 1
```

Đây là lý do ví dụ không tách `stock` ra nhiều documents để rồi phải bảo vệ cross-document invariant bằng transaction. Nếu nghiệp vụ tách nhiều kho/đơn hàng, cần aggregate/transaction/ledger design riêng.

## 6. Công nghệ dùng trong bài

| Thành phần | Vai trò |
|---|---|
| Java 17+ | Records, `java.time.Instant`, `Clock` |
| Spring Boot 3.x | HTTP, configuration, lifecycle |
| Spring Web MVC | REST controllers |
| Jakarta Bean Validation | Ràng buộc input |
| Spring Data MongoDB | Mapping và `MongoTemplate` |
| MongoDB | Document storage |
| Spring Boot Actuator | Health/metrics endpoints |
| JUnit 5 / Spring Boot Test | Tests |
| Testcontainers | Integration test với MongoDB sandbox |
| Maven | Quản lý dependencies |

Ví dụ `pom.xml` dưới đây ghim một **bản Spring Boot 3.3.5 làm baseline học tập**, không khẳng định là bản mới nhất hoặc còn trong vòng hỗ trợ ở mọi môi trường. Production cần kiểm vulnerability, hỗ trợ và khả năng tương thích của bộ dependencies tại thời điểm triển khai.

## 7. Cấu trúc dự án đề xuất

~~~text
catalog-api/
  pom.xml
  src/main/java/com/example/catalog/
    CatalogApplication.java
    TimeConfig.java
    Product.java
    CreateProductRequest.java
    UpdateProductRequest.java
    ReserveStockRequest.java
    ProductResponse.java
    ProductPage.java
    ProductService.java
    ProductController.java
    ApiExceptions.java
    ApiExceptionHandler.java
  src/main/resources/
    application.yml
  src/test/java/com/example/catalog/
    ProductServiceIntegrationTest.java
    ProductControllerTest.java
~~~

Để dễ học, ví dụ đặt classes cùng package. Dự án lớn có thể chia `api`, `domain`, `application`, `infrastructure` sau khi các hợp đồng đã ổn định.

## 8. Maven dependencies

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>mongodb</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

BOM của Spring Boot quản lý phiên bản dependencies tương thích theo baseline. Nếu thay Boot version, cần kiểm lại Java, driver và Testcontainers.

## 9. Cấu hình kết nối

`src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/catalog?maxPoolSize=30&serverSelectionTimeoutMS=3000&connectTimeoutMS=2000}"
      auto-index-creation: false

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

**Lưu ý YAML:** không thể khai báo **hai key `spring:` cùng cấp** trong một YAML document một cách đáng tin. Khi thực sự tạo file, phải gộp như sau:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/catalog?maxPoolSize=30&serverSelectionTimeoutMS=3000&connectTimeoutMS=2000}"
      auto-index-creation: false
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Hãy dùng **khối thứ hai** làm `application.yml`. Hostname/URI của cluster thật phải lấy từ secrets manager/environment configuration; không hardcode username/password vào Git.

## 10. Cấu hình connection pool có ý nghĩa gì?

Ví dụ MongoDB URI:

~~~text
mongodb://localhost:27017/catalog
  ?maxPoolSize=30
  &serverSelectionTimeoutMS=3000
  &connectTimeoutMS=2000
~~~

Các options:

- `maxPoolSize`: giới hạn số connections trong pool theo server/driver semantics.
- `serverSelectionTimeoutMS`: thời gian chờ tìm một server phù hợp.
- `connectTimeoutMS`: timeout tạo network connection.
- Các timeout khác như socket/read timeout, acquire wait và operation deadline cần cấu hình theo driver version, topology và SLO.

**Pool size không phải toàn bộ concurrency limit của ứng dụng.** Nhiều HTTP threads có thể chờ pool, tạo queue và tail latency. Không tăng pool lên hàng nghìn chỉ để tránh chờ.

## 11. Bắt đầu bằng MongoDB local

Ví dụ nếu máy học tập có Docker và được phép chạy container:

~~~bash
docker run --name catalog-mongo \
  -p 127.0.0.1:27017:27017 \
  -d mongo:7.0
~~~

Đây là **một instance đơn** dành cho lab; không có cấu hình replica set đầy đủ, TLS/auth hay HA. Không đưa cấu hình này ra Internet. Trong production, phải bật authentication, TLS, network restrictions, backups và monitoring tương ứng.

Ứng dụng có thể khởi động qua Maven:

~~~bash
./mvnw spring-boot:run
~~~

Nếu dự án chưa có Maven Wrapper, dùng `mvn spring-boot:run`. Không thực thi các lệnh ở bước viết bài này; người học chạy trong môi trường lab phù hợp.

## 12. Spring Boot entrypoint

`CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật component scan theo package. Các controllers, services và configurations trong `com.example.catalog` sẽ được Spring quản lý.

## 13. Inject `Clock` để dễ test

`TimeConfig.java`:

~~~java
package com.example.catalog;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Không gọi `Instant.now()` rải rác qua hàng trăm methods nếu business cần test expiry/timestamps. Một `Clock` inject được có thể được thay bằng `Clock.fixed(...)` trong unit tests.

**Clock không phải source version.** Business version ở bài này do atomic update tăng lên; timestamps chỉ để audit/hiển thị.

## 14. Mapping MongoDB document

`Product.java`:

~~~java
package com.example.catalog;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record Product(
    @Id String sku,
    String name,
    long priceCents,
    long stock,
    long version,
    Instant createdAt,
    Instant updatedAt
) {}
~~~

Một record được map thành document tương tự:

~~~json
{
  "_id": "KB-101",
  "name": "Bàn phím cơ",
  "priceCents": 1500000,
  "stock": 5,
  "version": 1,
  "createdAt": "2026-11-14T08:00:00Z",
  "updatedAt": "2026-11-14T08:00:00Z"
}
~~~

Các `Instant` được driver mapping sang BSON date/time representation theo converter; giá trị JSON là minh họa.

## 15. `_id` và uniqueness

MongoDB bảo đảm uniqueness cho `_id` trong một collection qua index mặc định. Vì vậy:

~~~text
POST sku=KB-101 -> insert success
POST sku=KB-101 -> duplicate key conflict
~~~

Không làm:

~~~text
if (!exists(sku)) insert(product)
~~~

rồi tin đã bảo vệ uniqueness. Hai requests có thể cùng thấy `exists=false` trước khi insert. **Unique index và atomic insert** mới là nơi quyết định.

## 16. Phân biệt domain ID và display name

`sku` là định danh ổn định, `name` là thuộc tính đổi được:

~~~text
sku = "KB-101"
name = "Bàn phím cơ"
```

Nếu user đổi tên sản phẩm, `_id` không đổi. Không dùng tên hiển thị hoặc tên Unicode chưa chuẩn hóa làm khóa nếu business identity không định nghĩa như vậy.

SKU trong lab được giới hạn ASCII uppercase để API key rõ và an toàn cho URL. Production có thể cần một **immutable generated ID** tách khỏi SKU business vốn có thể đổi; khi đó unique SKU index là constraint riêng.

## 17. DTO khác document

Vì sao không nhận thẳng `Product` từ HTTP?

- Client có thể gửi `version=999`.
- Client có thể giả `createdAt`.
- Client có thể điều chỉnh `stock` âm.
- Khi thêm internal fields, chúng dễ bị mass assignment.
- Validation của API khác rules của persisted representation.
- Response không nên lộ internal fields theo mặc định.

Hãy nhận **request records** và trả **response record** do server định nghĩa.

## 18. DTO tạo sản phẩm

`CreateProductRequest.java`:

~~~java
package com.example.catalog;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 2, max = 40)
    @Pattern(regexp = "[A-Z0-9._-]+")
    String sku,

    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @PositiveOrZero
    Long priceCents,

    @NotNull
    @PositiveOrZero
    Long stock
) {}
~~~

Dùng `Long` boxed cho input numeric để `@NotNull` phát hiện **JSON thiếu trường**. Nếu dùng `long` primitive, một số đường mapping có thể mặc định `0` và đánh mất phân biệt “không gửi” với “gửi 0”.

## 19. DTO cập nhật metadata

`UpdateProductRequest.java`:

~~~java
package com.example.catalog;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

public record UpdateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @PositiveOrZero
    Long priceCents,

    @NotNull
    @Positive
    Long expectedVersion
) {}
~~~

Update **không nhận field stock** trong mẫu này. Stock được sửa qua một domain command riêng, giúp tránh overwrite một reservation hợp lệ khi user cập nhật name/price.

## 20. DTO giữ chỗ tồn kho

`ReserveStockRequest.java`:

~~~java
package com.example.catalog;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record ReserveStockRequest(
    @NotNull @Positive Long quantity,
    @NotNull @Positive Long expectedVersion
) {}
~~~

Các giá trị `quantity <= 0` bị reject từ validation. Việc đủ tồn kho được kiểm **atomically tại database**, không chỉ kiểm trong Java.

## 21. DTO response

`ProductResponse.java`:

~~~java
package com.example.catalog;

import java.time.Instant;

public record ProductResponse(
    String sku,
    String name,
    long priceCents,
    long stock,
    long version,
    Instant createdAt,
    Instant updatedAt
) {
    public static ProductResponse from(Product product) {
        return new ProductResponse(
            product.sku(),
            product.name(),
            product.priceCents(),
            product.stock(),
            product.version(),
            product.createdAt(),
            product.updatedAt()
        );
    }
}
~~~

Response không cho client ghi `version`, `createdAt` như một command. Chúng là thông tin quan sát từ server.

## 22. DTO danh sách có cursor

`ProductPage.java`:

~~~java
package com.example.catalog;

import java.util.List;

public record ProductPage(
    List<ProductResponse> items,
    String nextCursor
) {}
~~~

Ở lab, `nextCursor` chính là SKU cuối trang, vì query sắp theo `_id`. Trong production, nên dùng **cursor opaque có version, query binding và chữ ký** nếu cần chống giả mạo/đảm bảo tenant isolation.

## 23. Kiểm tra đầu vào không chỉ là annotation

Bean Validation giúp kiểm:

- `@NotBlank`.
- `@Size`.
- `@Pattern`.
- `@Positive` / `@PositiveOrZero`.
- `@NotNull`.

Nhưng nghiệp vụ còn cần:

- SKU trong URL phù hợp format.
- `priceCents` không vượt giới hạn thương mại nếu có.
- Currency hợp lệ.
- User có quyền sửa sản phẩm hay không.
- Sản phẩm có thuộc tenant không.
- `expectedVersion` thực sự khớp.
- `stock >= quantity` ngay tại điểm ghi.
- Chống spam/rate limit và payload body quá lớn.

Validation annotation **không thay quyền truy cập, unique index hay CAS**.

## 24. Ba tầng validation

~~~text
HTTP/DTO:
  shape, type, size, required fields

Application/domain:
  business rules, allowed states, authorization

Database:
  unique key, atomic compare-and-set, consistency
~~~

Một request có SKU đúng regex vẫn có thể thuộc tenant khác. Một quantity dương vẫn có thể vượt stock. Một version hợp kiểu vẫn có thể đã cũ. Mỗi tầng giải quyết một lớp lỗi khác nhau.

## 25. Chuẩn hóa dữ liệu ngay entry boundary

Đối với `name`:

~~~java
String normalizedName = request.name().trim();
~~~

Đối với SKU, bài này **yêu cầu uppercase từ đầu** thay vì tự đổi chữ thường. Điều đó tránh việc client tưởng `"kb-101"` và `"KB-101"` là hai identities khác nhau.

Nếu muốn canonicalize SKU bằng `toUpperCase(Locale.ROOT)`, phải xác định rõ collision/uniqueness semantics cho mọi code path, including imports, legacy data và index constraints.

## 26. `@NotBlank` và whitespace

`@NotBlank` loại các giá trị trống/whitespace theo định nghĩa validator. Nhưng `@Size(max=120)` đo **chuỗi đầu vào**, không tự đo name sau normalization.

Với production cần quyết định:

- Có trim không?
- Có collapse multiple spaces không?
- Có normalize Unicode không?
- Có cấm control characters không?
- Có max bytes khác max code points không?
- Có cần kiểm format theo locale không?

Không tắt validation chỉ vì người dùng có Unicode; hãy định nghĩa đúng domain.

## 27. JSON number và `priceCents`

Nếu client gửi:

~~~json
{"priceCents": 19.99}
~~~

trong khi DTO yêu cầu `Long`, HTTP deserialization có thể báo lỗi hoặc xử lý theo converter/config. **Không dựa vào phép làm tròn âm thầm**. API contract nên yêu cầu số nguyên đơn vị nhỏ.

Ví dụ:

~~~json
{
  "sku": "KB-101",
  "name": "Bàn phím cơ",
  "priceCents": 1500000,
  "stock": 5
}
~~~

Nếu sản phẩm có giá trong nhiều currency, cần `Money(currency, minorUnits)` hoặc decimal representation rõ, không gán chung giá trị cents cho mọi loại tiền.

## 28. Giới hạn kích thước input

Các lớp bảo vệ:

- Giới hạn `Content-Length`/body size tại ingress.
- Giới hạn server HTTP request size.
- DTO max field lengths.
- Jackson depth/nesting nếu cần.
- MongoDB document size limits.
- Rate/concurrency limits.
- Không ghi toàn request body vào logs.

Một `@Size(max=120)` không đủ bảo vệ nếu client gửi body 100 MiB có nested extra fields hoặc parser phải allocate trước validation.

## 29. NoSQL injection và query construction

Tránh nhận raw query từ client:

~~~text
POST /search
body: {"filter": {"$where": "..."}}
~~~

rồi đưa trực tiếp vào database command.

Với REST CRUD:

- Chỉ nhận scalar fields được phép.
- Tự dựng Mongo `Criteria`.
- Không nối user input thành JavaScript/regex server-side không kiểm soát.
- Không expose arbitrary operators/pipelines.
- Giới hạn query shape và sort fields.
- Authorize tenant/record scope.

Parameterization/type-safe builders giảm injection surface; **authorization** vẫn cần riêng.

## 30. Thời gian và version là hai trục khác nhau

`createdAt`/`updatedAt` phục vụ audit/hiển thị. `version` phục vụ concurrency.

~~~text
t=10:00 API A reads version 1
t=10:01 API B updates to version 2
t=10:02 API A tries update expectedVersion=1
```

A phải bị từ chối dù `updatedAt` có thể bằng nhau ở độ phân giải milliseconds hoặc clocks lệch. **Không dùng client timestamp như optimistic lock** nếu database không cam kết ordering tương ứng.

---

## 31. Domain exceptions

`ApiExceptions.java` có thể chứa các classes package-private:

~~~java
package com.example.catalog;

class BadRequestException extends RuntimeException {
    BadRequestException(String message) { super(message); }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String sku) {
        super("Product not found: " + sku);
    }
}

class ProductAlreadyExistsException extends RuntimeException {
    ProductAlreadyExistsException(String sku) {
        super("Product already exists: " + sku);
    }
}

class VersionConflictException extends RuntimeException {
    VersionConflictException() {
        super("Product was modified by another request");
    }
}

class InsufficientStockException extends RuntimeException {
    InsufficientStockException() {
        super("Insufficient stock");
    }
}
~~~

Trong production, hạn chế đưa raw user-supplied identifiers vào error body/log nếu đó là PII hoặc nếu tồn tại record là thông tin nhạy cảm.

## 32. Service dependency và resources

`ProductService.java` bắt đầu bằng:

~~~java
package com.example.catalog;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private static final Pattern SKU =
        Pattern.compile("[A-Z0-9._-]{2,40}");

    private final MongoTemplate mongo;
    private final Clock clock;

    public ProductService(MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    // Các methods ở những phần tiếp theo đặt trong class này.
}
~~~

Ví dụ methods sau đây **được ghép vào class `ProductService`**, không định nghĩa thêm nhiều class public cùng tên. Spring tạo/tiêm `MongoTemplate` quản lý bởi context; không tạo mới `MongoClient` trong mỗi method.

## 33. Validate SKU từ path và query

Method trong `ProductService`:

~~~java
private String requireSku(String sku) {
    if (sku == null || !SKU.matcher(sku).matches()) {
        throw new BadRequestException("Invalid SKU");
    }
    return sku;
}
~~~

Giới hạn này đồng nhất với DTO create. Không có `toUpperCase()` nên API chủ động từ chối URL chứa lowercase.

Nếu sản phẩm theo tenant, `requireSku` chỉ kiểm format, **không xác thực quyền**; câu truy vấn còn phải có `tenantId` lấy từ security context.

## 34. Create: insert thay vì check-then-insert

Method trong `ProductService`:

~~~java
public ProductResponse create(CreateProductRequest request) {
    String sku = requireSku(request.sku());
    String name = request.name().trim();

    Instant now = clock.instant();
    Product product = new Product(
        sku,
        name,
        request.priceCents(),
        request.stock(),
        1L,
        now,
        now
    );

    try {
        return ProductResponse.from(mongo.insert(product));
    } catch (DuplicateKeyException duplicate) {
        throw new ProductAlreadyExistsException(sku);
    }
}
~~~

Những giá trị từ `request` được giả định đã qua `@Valid` tại HTTP entrypoint. Nếu service còn được gọi từ batch/queue, **phải validate ở application boundary đó** hoặc dùng domain types bất biến để không phụ thuộc riêng vào controller.

## 35. Vì sao `insert` đúng hơn `save` cho create?

`save` thường mang semantics **insert hoặc replace/upsert** tùy mapping/ID. Nếu client thử tạo lại một SKU đang tồn tại, `save` không có bảo vệ unique-create như mong đợi và có thể ghi đè.

`insert` thể hiện intent: **record chưa tồn tại**. Unique `_id` bảo vệ ngay cả khi hai requests đồng thời.

Trong production, việc phân loại duplicate error cần tránh lộ thông tin nếu endpoint không được phép tiết lộ resource tồn tại.

## 36. Read một document

Method trong `ProductService`:

~~~java
public ProductResponse get(String rawSku) {
    String sku = requireSku(rawSku);

    Product product = mongo.findById(sku, Product.class);
    if (product == null) {
        throw new ProductNotFoundException(sku);
    }
    return ProductResponse.from(product);
}
~~~

Một point lookup theo `_id` thường phù hợp với index sẵn có hơn unbounded search. Nhưng đọc từ MongoDB cluster có read preference/read concern; ví dụ **không tự khẳng định global linearizable reads** dưới mọi failover configuration.

## 37. Read consistency không được đoán

Nếu writes dùng primary và read của ứng dụng dùng secondary:

~~~text
PUT returns success
GET from secondary immediately returns older version
```

điều này có thể hợp với read consistency đã chọn. Nếu nghiệp vụ yêu cầu read-your-writes/strong read, phải chọn read concern/route/session contract phù hợp và kiểm theo version/driver semantics.

Một unit test `create -> get` trên MongoDB local **không chứng minh** khả năng đọc nhất quán trên multi-region/multi-replica deployment.

## 38. Update có điều kiện theo version

Method trong `ProductService`:

~~~java
public ProductResponse update(
        String rawSku, UpdateProductRequest request) {

    String sku = requireSku(rawSku);

    Query query = Query.query(
        Criteria.where("_id").is(sku)
            .and("version").is(request.expectedVersion())
    );

    Update update = new Update()
        .set("name", request.name().trim())
        .set("priceCents", request.priceCents())
        .set("updatedAt", clock.instant())
        .inc("version", 1L);

    Product changed = mongo.findAndModify(
        query,
        update,
        FindAndModifyOptions.options().returnNew(true),
        Product.class
    );

    if (changed == null) {
        failNotFoundOrConflict(sku);
    }
    return ProductResponse.from(changed);
}
~~~

`findAndModify` kiểm query condition và mutation trong **một atomic document operation** theo MongoDB semantics. Query yêu cầu `_id` và `version` khớp, nên hai writers cùng expectedVersion không thể đồng thời tăng cùng một version nếu writes được áp đúng tại cùng authoritative document.

## 39. Giải thích thất bại của update

Helper:

~~~java
private void failNotFoundOrConflict(String sku) {
    if (mongo.findById(sku, Product.class) == null) {
        throw new ProductNotFoundException(sku);
    }
    throw new VersionConflictException();
}
~~~

**Cảnh báo race khi phân loại lỗi:** đọc lại để phân biệt `NOT_FOUND` và `VERSION_CONFLICT` là một **quan sát sau mutation thất bại**, không phải snapshot atomic cùng thời điểm. Document có thể bị xóa/tạo lại giữa hai lệnh; vì vậy HTTP classification có thể phụ thuộc trạng thái lúc reread, trong khi **safety của update** vẫn được bảo đảm bởi predicate atomically tại điểm ghi.

Nếu yêu cầu phân biệt chính xác hơn, có thể thiết kế API/transaction/read version response tương ứng.

## 40. Vì sao không làm update kiểu read → modify → save?

Sai trong môi trường có concurrent writes:

~~~java
Product old = mongo.findById(sku, Product.class);
Product changed = new Product(
    old.sku(), newName, newPrice, old.stock(),
    old.version() + 1, old.createdAt(), clock.instant()
);
mongo.save(changed);
~~~

Hai clients cùng đọc `version=5`, rồi mỗi client `save` có thể ghi đè thay đổi của nhau nếu không có condition/optimistic-locking mechanism. `@Version` của Spring Data MongoDB có thể hỗ trợ optimistic locking khi được cấu hình/sử dụng đúng, nhưng **bài này đã chọn manual CAS** bằng `findAndModify`; không trộn cơ chế tự tăng `@Version` với manual `$inc` mà không kiểm semantics.

## 41. Reserve stock phải kiểm ngay trong database

Điều kiện nghiệp vụ:

\[
quantity>0,\qquad stock_{\text{before}}\ge quantity
\]

Nếu đọc stock trong Java rồi trừ và `save`, hai khách hàng có thể cùng thấy còn một sản phẩm và cùng đặt được. Vì thế reserve dùng **một atomic conditional mutation**.

Method trong `ProductService`:

~~~java
public ProductResponse reserve(
        String rawSku, ReserveStockRequest request) {

    String sku = requireSku(rawSku);

    Query query = Query.query(
        Criteria.where("_id").is(sku)
            .and("version").is(request.expectedVersion())
            .and("stock").gte(request.quantity())
    );

    Update update = new Update()
        .inc("stock", -request.quantity())
        .inc("version", 1L)
        .set("updatedAt", clock.instant());

    Product changed = mongo.findAndModify(
        query,
        update,
        FindAndModifyOptions.options().returnNew(true),
        Product.class
    );

    if (changed == null) {
        failReservation(sku, request);
    }
    return ProductResponse.from(changed);
}
~~~

`quantity` là `Long` boxed đã được `@NotNull @Positive` ở controller; toán tử unary minus unbox thành `long`. Đảm bảo method được gọi với DTO hợp lệ từ **mọi entrypoint**; nếu consumer hoặc batch gọi trực tiếp, nên bảo vệ bằng domain validation thêm.

## 42. Phân loại reserve failure

Helper trong `ProductService`:

~~~java
private void failReservation(
        String sku, ReserveStockRequest request) {

    Product current = mongo.findById(sku, Product.class);
    if (current == null) {
        throw new ProductNotFoundException(sku);
    }
    if (current.version() != request.expectedVersion()) {
        throw new VersionConflictException();
    }
    if (current.stock() < request.quantity()) {
        throw new InsufficientStockException();
    }

    // State changed after the failed atomic condition, or
    // an unexpected observation: do not assume success.
    throw new VersionConflictException();
}
~~~

Reread để phân biệt lỗi là **best-effort diagnostic**; dữ liệu vẫn có thể đổi giữa failed condition và reread. Việc chặn oversell dựa vào `stock >= qty` được MongoDB kiểm **trong chính phép update**.

## 43. Hai requests cạnh tranh một sản phẩm cuối

Initial state:

~~~json
{"_id":"KB-101","stock":1,"version":7}
~~~

Hai clients gửi:

~~~text
A: reserve quantity=1 expectedVersion=7
B: reserve quantity=1 expectedVersion=7
~~~

Trong một source document có atomic conditional writes:

- Tối đa một request match version 7 và `stock >= 1`.
- Request thắng: `stock=0`, `version=8`.
- Request còn lại không match version 7; trả conflict.
- Stock không âm.

Không phải vì Java `synchronized` — service có thể chạy trên 20 pods — mà vì **database là điểm kiểm atomically**.

## 44. Reserve không tự có idempotency khi timeout

Một tình huống:

~~~text
Client reserve v7 -> MongoDB commits v8
HTTP response lost
Client retries reserve v7
~~~

Retry nhận 409 vì version đã thành 8. **409 không tự chứng minh lần đầu không thành công.**

Với reservation/payment thật, nên có **stable operation ID** và một ledger/inbox được cập nhật atomically với stock theo scope hỗ trợ, hoặc cơ chế reconciliation. Bài lab dùng `expectedVersion` để học CAS; không dùng nguyên xi như cơ chế chống double charge/exactly-once reservation trên production.

## 45. Delete theo expectedVersion

Method trong `ProductService`:

~~~java
public void delete(String rawSku, long expectedVersion) {
    String sku = requireSku(rawSku);
    if (expectedVersion <= 0) {
        throw new BadRequestException(
            "expectedVersion must be positive"
        );
    }

    Query query = Query.query(
        Criteria.where("_id").is(sku)
            .and("version").is(expectedVersion)
    );

    Product removed = mongo.findAndRemove(
        query,
        Product.class
    );

    if (removed == null) {
        failNotFoundOrConflict(sku);
    }
}
~~~

`findAndRemove` bảo vệ operation bằng version predicate. Nếu record đã bị sửa, không được xóa nhầm bản mới.

**Giới hạn:** bài này hard-delete; trong hệ có CDC, backfill hoặc yêu cầu privacy/lifecycle, delete thường cần tombstone/generation/outbox để ngăn historical event hồi sinh record.

## 46. DELETE có idempotent hay không?

HTTP `DELETE` được thiết kế có **idempotent effect** theo nghĩa gửi nhiều lần không gây thêm hiệu ứng ngoài kết quả xóa, nhưng status responses có thể khác.

Trong API lab:

~~~text
First DELETE -> 204
Second DELETE -> 404
~~~

Điều này có thể phù hợp HTTP idempotency về **final resource state**, nhưng không phải **idempotency key** cho side effects ngoài DB. Nếu xóa phát email/billing event hoặc consumer job, cần thiết kế dedupe riêng.

## 47. Lỗ hổng khi xóa và tạo lại cùng SKU

History:

~~~text
Create SKU K -> version 1
Update K -> version 2
Delete K v2
Recreate K -> version 1
Old update expectedVersion=1 arrives
~~~

Một update cũ có thể match record mới cùng SKU/version 1. Đây là **ABA/generation reuse**.

Các lựa chọn production:

- Dùng immutable entity ID mới cho lifetime mới.
- Không cho reuse SKU.
- Tạo `generation`/epoch trong predicate.
- Lưu tombstone với version tăng xuyên lifetimes.
- Dùng event identity cùng aggregate generation.

Bài lab cố tình đơn giản hóa để tập trung CRUD; khi có retries dài hạn, phải xử lý lifecycle này trước production.

## 48. List phải có giới hạn

Một controller trả:

~~~java
return mongo.findAll(Product.class);
~~~

có thể nguy hiểm nếu collection có hàng chục triệu documents:

- Memory lớn.
- GC pressure.
- HTTP response quá kích thước.
- Connection/client timeout.
- Cache eviction.
- Database scan.
- Tạo DoS surface.

API phải giới hạn số records và query shape. Bài này cho `limit` trong **1–100**.

## 49. Keyset pagination theo SKU

Method trong `ProductService`:

~~~java
public ProductPage list(String after, int limit) {
    if (limit < 1 || limit > 100) {
        throw new BadRequestException(
            "limit must be between 1 and 100"
        );
    }

    Query query = new Query();
    if (after != null) {
        query.addCriteria(
            Criteria.where("_id").gt(requireSku(after))
        );
    }

    query.with(Sort.by(Sort.Direction.ASC, "_id"));
    query.limit(limit + 1);

    List<Product> page = mongo.find(query, Product.class);
    boolean hasMore = page.size() > limit;

    List<ProductResponse> items = page.stream()
        .limit(limit)
        .map(ProductResponse::from)
        .toList();

    String nextCursor = hasMore
        ? page.get(limit - 1).sku()
        : null;

    return new ProductPage(items, nextCursor);
}
~~~

`limit+1` lấy thêm tối đa một record để biết còn trang tiếp. `_id` có index và stable sorting. Đây là **keyset pagination**, không dùng `skip` offset rất lớn.

## 50. Phân trang và dữ liệu thay đổi đồng thời

Keyset scan có semantics:

~~~text
Page 1: keys <= K100
Page 2: keys > K100
~~~

Nếu document mới được tạo với key `< K100` giữa hai trang, user **có thể không thấy** nó trong lượt duyệt hiện tại. Vì vậy:

- Bài lab không hứa consistent snapshot toàn collection.
- Để export/backfill chính xác, phải kết hợp snapshot/CDC.
- Để UI danh sách, có thể chấp nhận pagination theo contract eventual/live.
- Cursor production nên bind query filters/sort/tenant/schema version.
- Một cursor dạng raw SKU trong demo có thể bị sửa; authorization phải kiểm ở server.

## 51. Không dùng `skip` lớn tùy tiện

Ví dụ:

~~~javascript
db.products.find().sort({_id: 1}).skip(2000000).limit(20)
~~~

có thể làm engine phải xử lý rất nhiều records trước offset, đồng thời inserts/deletes làm pagination thay đổi.

Keyset bằng indexed `_id > after` thường tốt hơn cho **forward pagination**. Nhưng nếu sort theo `price` cần index có total order `(price,sku)` và cursor chứa đủ tie-break. Không chỉ thay `skip` bằng `price > lastPrice` nếu có nhiều items cùng price.

## 52. Tạo REST controller

`ProductController.java`:

~~~java
package com.example.catalog;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest body) {

        ProductResponse created = service.create(body);

        return ResponseEntity
            .created(URI.create(
                "/api/v1/products/" + created.sku()
            ))
            .body(created);
    }

    @GetMapping("/{sku}")
    public ProductResponse get(@PathVariable String sku) {
        return service.get(sku);
    }

    @GetMapping
    public ProductPage list(
            @RequestParam(required = false) String after,
            @RequestParam(defaultValue = "25") int limit) {
        return service.list(after, limit);
    }

    @PutMapping("/{sku}")
    public ProductResponse update(
            @PathVariable String sku,
            @Valid @RequestBody UpdateProductRequest body) {
        return service.update(sku, body);
    }

    @PostMapping("/{sku}/reservations")
    public ProductResponse reserve(
            @PathVariable String sku,
            @Valid @RequestBody ReserveStockRequest body) {
        return service.reserve(sku, body);
    }

    @DeleteMapping("/{sku}")
    public ResponseEntity<Void> delete(
            @PathVariable String sku,
            @RequestParam long expectedVersion) {
        service.delete(sku, expectedVersion);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller không truy cập `MongoTemplate` trực tiếp. Các routes và bodies đi qua service, nơi kiểm domain/CAS. Khi thêm authentication, tenant identity phải lấy từ **trusted principal/claim**, không mặc định tin một request body field.

## 53. Response code theo nguyên nhân

| Trường hợp | HTTP | Ý nghĩa |
|---|---|---|
| Product tạo mới | `201 Created` | Có Location |
| Product đọc/cập nhật thành công | `200 OK` | Trả DTO |
| Delete thành công | `204 No Content` | Không body |
| JSON/field/limit invalid | `400 Bad Request` | Client sửa request |
| SKU không tồn tại | `404 Not Found` | Không tìm thấy |
| SKU trùng | `409 Conflict` | Key đã tồn tại |
| Expected version cũ | `409 Conflict` | Đọc lại trước sửa |
| Quantity vượt stock | `422 Unprocessable Entity` | Business rule không thỏa |
| Backend unavailable | `503 Service Unavailable` | Hạn retry, cần reconcile ambiguous mutations |
| Lỗi ứng dụng không dự đoán | `500 Internal Server Error` | Không lộ stack trace |

HTTP status là **API contract được thiết kế**, không phải sự thật bắt buộc cho mọi API NoSQL. Ví dụ `422` có thể được chuẩn hóa thành `409` ở hệ khác; cần tài liệu và client code tương ứng.

## 54. ProblemDetail cho lỗi có cấu trúc

Spring Framework hỗ trợ `ProblemDetail` cho RFC 7807/9457-style responses tùy cấu hình/framework version.

Ví dụ:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Product was modified by another request",
  "code": "VERSION_CONFLICT"
}
~~~

Client có thể xử lý theo `code` ổn định thay vì so string tiếng Anh. Không đưa database stacktrace hoặc connection URI vào `detail`.

## 55. Global exception handler

`ApiExceptionHandler.java`:

~~~java
package com.example.catalog;

import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class ApiExceptionHandler {

    private ResponseEntity<ProblemDetail> error(
            HttpStatus status, String code, String message) {

        ProblemDetail body =
            ProblemDetail.forStatusAndDetail(status, message);
        body.setTitle(status.getReasonPhrase());
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }

    @ExceptionHandler({
        BadRequestException.class,
        MethodArgumentNotValidException.class,
        HttpMessageNotReadableException.class
    })
    public ResponseEntity<ProblemDetail> badRequest(Exception ex) {
        return error(
            HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
            "Request parameters or body are invalid"
        );
    }

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(Exception ex) {
        return error(
            HttpStatus.NOT_FOUND, "NOT_FOUND",
            "Product not found"
        );
    }

    @ExceptionHandler(ProductAlreadyExistsException.class)
    public ResponseEntity<ProblemDetail> duplicate(Exception ex) {
        return error(
            HttpStatus.CONFLICT, "DUPLICATE_PRODUCT",
            "Product already exists"
        );
    }

    @ExceptionHandler(VersionConflictException.class)
    public ResponseEntity<ProblemDetail> version(Exception ex) {
        return error(
            HttpStatus.CONFLICT, "VERSION_CONFLICT",
            "Product version is no longer current"
        );
    }

    @ExceptionHandler(InsufficientStockException.class)
    public ResponseEntity<ProblemDetail> stock(Exception ex) {
        return error(
            HttpStatus.UNPROCESSABLE_ENTITY, "INSUFFICIENT_STOCK",
            "Not enough stock for reservation"
        );
    }

    @ExceptionHandler(DataAccessResourceFailureException.class)
    public ResponseEntity<ProblemDetail> unavailable(Exception ex) {
        return error(
            HttpStatus.SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE",
            "Data store is temporarily unavailable"
        );
    }
}
~~~

Handler này xử lý **các exception được liệt kê**. Trong production bổ sung generic fallback 500, `DuplicateKeyException` từ các đường khác, resource timeout translations, request binding errors và log correlation IDs. Không bắt tất cả `RuntimeException` thành 503: bug lập trình không nhất thiết là database unavailable.

## 56. Ranh giới `@Valid`

Khi nhận request:

~~~java
public ProductResponse update(
    @PathVariable String sku,
    @Valid @RequestBody UpdateProductRequest body) {
    return service.update(sku, body);
}
~~~

Spring MVC sẽ chạy Jakarta Bean Validation cho DTO body. Nhưng:

- Không tự validate request từ Kafka/scheduled task.
- Không thay việc validate `sku` path.
- Không kiểm version thực tế.
- Không kiểm tenant authorization.
- Không chắc chắn kiểm fields ở nested DTO trừ khi cấu hình cascade đúng.
- Không giới hạn database query runtime.

Đừng nhầm `@Valid` với một “lá chắn toàn bộ input”.

## 57. Phân biệt lỗi 400 và lỗi 409

Ví dụ:

~~~text
name=""                 -> 400: syntactically/domain-invalid input
expectedVersion=-1      -> 400: invalid precondition value
expectedVersion=4 but DB v5 -> 409: valid input, stale state
SKU exists on create    -> 409: uniqueness conflict
stock=1, quantity=2     -> 422: business capacity
~~~

Nếu client nhận 409, thường cần reread current state/merge conflict hoặc báo cho user, không nên retry cùng payload vô hạn.

## 58. Demo tạo sản phẩm bằng curl

~~~bash
curl -i -X POST http://localhost:8080/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{
    "sku": "KB-101",
    "name": "Ban phim co",
    "priceCents": 1500000,
    "stock": 5
  }'
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/products/KB-101
Content-Type: application/json

{"sku":"KB-101","name":"Ban phim co","priceCents":1500000,"stock":5,"version":1,"createdAt":"...","updatedAt":"..."}
~~~

Dấu `...` ở timestamps là placeholder trong minh họa, không phải JSON timestamp hợp lệ để client parse; response thực sẽ chứa ISO time do converter serialize.

## 59. Demo đọc một sản phẩm

~~~bash
curl -i http://localhost:8080/api/v1/products/KB-101
~~~

Một response 200 có `version=1`. Client nên lấy đúng version này để cập nhật/xóa nếu API yêu cầu optimistic concurrency.

## 60. Demo phân trang

~~~bash
curl -i 'http://localhost:8080/api/v1/products?limit=2'
~~~

Response:

~~~json
{
  "items": [
    {"sku":"KB-101","name":"Ban phim co","priceCents":1500000,"stock":5,"version":1,"createdAt":"2026-11-14T08:00:00Z","updatedAt":"2026-11-14T08:00:00Z"},
    {"sku":"KB-102","name":"Chuot","priceCents":600000,"stock":10,"version":1,"createdAt":"2026-11-14T08:01:00Z","updatedAt":"2026-11-14T08:01:00Z"}
  ],
  "nextCursor": "KB-102"
}
~~~

`KB-102` là dữ liệu ví dụ cho trang có ít nhất ba sản phẩm trong collection. Nếu chỉ có hai, `nextCursor` sẽ là `null`.

## 61. Demo cập nhật metadata

Client vừa đọc version 1:

~~~bash
curl -i -X PUT http://localhost:8080/api/v1/products/KB-101 \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Ban phim co v2",
    "priceCents": 1400000,
    "expectedVersion": 1
  }'
~~~

Nếu thành công, response có version 2. Gửi lại chính request này sau đó sẽ bị 409 vì expectedVersion 1 đã cũ; **đó là hành vi bảo vệ state**, không phải MongoDB ngẫu nhiên lỗi.

## 62. Demo reserve tồn kho

Khi version hiện tại là 2 và stock vẫn 5:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/v1/products/KB-101/reservations \
  -H 'Content-Type: application/json' \
  -d '{
    "quantity": 2,
    "expectedVersion": 2
  }'
~~~

Response thành công: `stock=3`, `version=3`. Một request reserve 4 với expectedVersion 3 sẽ bị `422`, không đưa stock xuống -1.

## 63. Demo xóa có điều kiện

~~~bash
curl -i -X DELETE \
  'http://localhost:8080/api/v1/products/KB-101?expectedVersion=3'
~~~

Nếu product vẫn version 3, response là 204. Nếu một request khác đã sửa product thành version 4, response 409. GET sau khi xóa trả 404.

## 64. Demo validation failures

Các trường hợp:

~~~json
{"sku":"kb-101","name":"A","priceCents":100,"stock":5}
~~~

SKU lowercase: 400.

~~~json
{"sku":"KB-101","name":" ","priceCents":100,"stock":5}
~~~

Name trắng: 400.

~~~json
{"sku":"KB-101","name":"A","priceCents":-5,"stock":5}
~~~

Giá âm: 400.

~~~json
{"sku":"KB-101","name":"A","priceCents":100}
~~~

Thiếu `stock`: 400. DTO boxed `Long` + `@NotNull` bảo đảm case thiếu không tự thành stock 0.

---

## 65. Resource lifecycle: các loại tài nguyên cần quản lý

Một request CRUD có thể sử dụng đồng thời:

~~~text
HTTP connection
Servlet/request thread
JSON parser and in-memory objects
MongoDB driver connection pool
MongoDB server cursor or operation
Database CPU, disk I/O and page cache
Application heap/GC
Metrics/tracing/log buffers
~~~

Nếu một resource bị giữ quá lâu, hệ có thể chết vì queue/timeout dù từng thao tác riêng lẻ đúng. Một tiêu chuẩn đánh giá tốt phải quan sát **đường đi và thời gian chiếm giữ tài nguyên** từ HTTP tới database.

## 66. `MongoClient` phải được reuse

Spring Boot thường tạo MongoDB driver client dưới quyền quản lý của application context và truyền `MongoTemplate` vào service.

Không nên viết:

~~~java
public Product find(String sku) {
    MongoClient c = MongoClients.create(uri);
    // find...
    // forget close
}
~~~

cho mỗi HTTP request. Mỗi client có thể quản lý pools/connections/threads của riêng nó, tạo overhead và leaks.

Nguyên tắc:

- Reuse **singleton Spring-managed MongoClient/MongoTemplate**.
- Không tự close bean dùng chung sau mỗi request.
- Khi standalone CLI **sở hữu** client, close đúng lúc kết thúc scope.
- Khi ứng dụng shutdown, để lifecycle manager đóng pools.

## 67. Pool size không phải tổng concurrency limit

Một URI:

~~~text
mongodb://localhost:27017/catalog?maxPoolSize=30
~~~

đặt giới hạn pool theo semantics của driver, nhưng số HTTP requests có thể lớn hơn 30 và chờ connections.

Nếu có 20 application pods × pool 30 per server, tổng candidate connections trên một server có thể tới khoảng 600, chưa tính monitoring/other pools/topologies. Đây là phép nhân đơn giản cho planning, **không phải cam kết số connections luôn đúng 600**.

Theo dõi cả **server connections, client pool checkout wait, app queue, thread count và p99**, không chỉ `maxPoolSize`.

## 68. Timeouts khác nhau về ý nghĩa

| Timeout | Khi nào | Lỗi cần xem |
|---|---|---|
| Connect | Mở TCP/TLS connection | Endpoint/network |
| Server selection | Chọn server đáp ứng operation | Topology/replica failure |
| Pool checkout | Chờ một connection có sẵn | Saturation/pool exhaustion |
| Socket/read | Đợi network response | Server latency hoặc network |
| Command max time | Engine server execution budget | Query/scan/lock |
| HTTP client | Client đợi API | Có thể mất ACK |
| Request deadline | Tổng thời gian service có thể dùng | Retry/cancellation budget |

**HTTP timeout không chứng minh mutation chưa commit.** Khi client không biết outcome, phải reconcile dựa vào business operation ID/version hoặc các cơ chế tương đương.

## 69. Deadline budget

Một request budget **giả định** 2.000 ms có thể phân bổ:

~~~text
HTTP/network:                   250 ms
Validation + mapping:            50 ms
DB pool wait + operation:      1,400 ms
Serialize/log/response:         100 ms
Contingency:                    200 ms
~~~

Các số không phải “chuẩn” cho mọi ứng dụng. Điểm quan trọng là **tổng budget**: không thể để SDK retry ba lần, mỗi lần tới 2 giây, trong một API có deadline 2 giây rồi mong outcome được ghi nhận rõ.

## 70. Pool exhaustion

Một sự cố:

~~~text
1000 servlet threads
30 pooled DB connections
slow query holds connections
-> hundreds of threads wait
-> API p99 grows
-> clients retry
-> even more waiting
~~~

Các biện pháp:

- Index/query tối ưu.
- Pool sizing theo DB capacity và pod count.
- Acquisition wait timeout.
- Bounded concurrent DB operations.
- Queue capacity limit.
- Admission control/load shedding.
- Rate limiting theo route/tenant.
- Tách background scans khỏi latency-critical workload.
- Circuit breaker với chính sách retry idempotent.

**Tăng pool lên vô hạn không giúp database xử lý nhanh hơn** nếu CPU/IO đã bão hòa.

## 71. Standalone `MongoCursor` với try-with-resources

Một export CLI không dùng Spring-managed client:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExportProducts {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("catalog");

            try (MongoCursor<Document> cursor = db
                    .getCollection("products")
                    .find()
                    .batchSize(200)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document item = cursor.next();
                    // Handle one item; do not collect all to a list.
                }
            }
        }
    }
}
~~~

`MongoClient` chỉ đóng ở cuối **CLI process ownership**; `MongoCursor` được đóng ngay khi hết scope, kể cả có exception. Không copy `MongoClients.create()` vào mỗi controller method.

## 72. Đừng tải toàn collection vào heap

Tránh:

~~~java
List<Document> all =
    collection.find().into(new ArrayList<>());
~~~

khi collection có hàng triệu documents. Rủi ro:

- OOM.
- Nhiều GC pauses.
- HTTP responses không giới hạn.
- Disk I/O/cache pressure.
- MongoDB cursor mở quá lâu.
- Request timeout và retry storm.

Cho API dùng bounded list page. Cho export/backfill dùng cursor hoặc key-range scan với batch size, durable checkpoint và rate limit.

## 73. Page size không phải giới hạn bytes

Một response 100 documents × 1 MiB có thể rất lớn dù `limit=100`. Cần thêm:

- Maximum document/field length.
- Query projection chỉ lấy fields cần.
- Maximum response bytes khi hợp lý.
- Bounded event/array nesting.
- Compression/CPU budget.
- Streaming cho large export.
- Rate limiting.
- Memory monitoring.

Trong demo Product có ít fields, nhưng lessons về quản lý tài nguyên vẫn áp dụng khi model lớn dần.

## 74. Các kiểu leak khác nhau

| Resource | Rủi ro |
|---|---|
| MongoDB connection/client | Tạo client per request, pool tăng |
| Mongo cursor | Không close khi dừng quét sớm |
| Client session | Không end khi lỗi/abort |
| Stream subscription | Không cancel khi shutdown |
| Executor | Threads/tasks không dừng |
| HTTP response stream | Không close/cancel |
| In-memory queue | Chờ vô hạn, giữ payload lớn |
| File export | Không close output stream/cleanup |

Sở hữu resource tới đâu, đóng ở đó theo `try-with-resources` hoặc framework lifecycle tương ứng.

## 75. Multi-document transaction và `ClientSession`

Khi cần thay đổi nhiều documents atomically trong phạm vi MongoDB hỗ trợ, transaction/session có thể cần thiết. Nhưng phải cân nhắc:

- Replica set/sharded cluster support.
- Transaction timeouts.
- Driver retry/commit ambiguity.
- Cross-document read/write concern.
- Session lifecycle.
- Locks/concurrency conflicts.
- Network round-trips.
- Không bao gồm external email/payment trong cùng atomic boundary.

**Product CRUD một document không cần mở transaction multi-document**. Chỉ thêm transaction khi business invariant vượt scope một document.

## 76. Reactive API không thay thế giới hạn tài nguyên

Chuyển sang WebFlux và reactive MongoDB có thể giảm blocked threads và hỗ trợ backpressure, nhưng:

- Không làm DB có thêm CPU/IO.
- Không sửa query full scan.
- Không tự có strong consistency.
- Cần cancel subscriptions.
- Vẫn phải giới hạn in-flight writes.
- Timeout/unknown commit vẫn xảy ra.

Đừng đổi programming paradigm thay vì giải thích bottleneck thật.

## 77. HTTP CRUD không được là arbitrary query engine

Không mở một endpoint cho user tự gửi:

~~~json
{
  "collection": "products",
  "filter": {"$where": "..."},
  "sort": {"someUserField": -1},
  "limit": 999999
}
~~~

rồi pass sang driver. Nó tạo security và resource risks.

Bài này cố định:

- Target collection.
- Query predicate theo SKU.
- Sort `_id`.
- Maximum page size.
- Projection/response schema.
- Atomic condition cho update/delete.

Khi bổ sung filters, nên allowlist fields/operators và index-aware limits.

## 78. Graceful shutdown

Khi deploy hoặc scale down:

1. Ngừng nhận requests mới.
2. Hoàn tất/cancel in-flight operations theo deadline.
3. Không retry blind những writes outcome unknown.
4. Dừng background consumers bằng checkpoint.
5. Flush metrics/logs có kiểm soát.
6. Đóng driver pools tại application shutdown.
7. Giữ readiness/health logic đúng lifecycle.

`server.shutdown: graceful` là một phần nhỏ; nó **không tự tạo exactly-once behavior** khi process chết đúng lúc MongoDB đã commit.

## 79. Autoscaling có thể nhân áp lực DB

Nếu 5 pods lên 30 pods nhưng mỗi pod có `maxPoolSize=30`, trần candidate connections tăng mạnh.

Theo dõi:

\[
C_{\text{possible}}\approx pods\times poolPerPod
\]

Ngoài connection count, cần quản lý:

- Rate/concurrency vào DB.
- Hot partitions.
- Replica lag.
- Query p99.
- Storage CPU/IO.
- Cost.
- SDK retries.
- Application GC.

Không chỉ autoscale API dựa trên CPU thấp rồi vô tình đánh quá tải MongoDB.

## 80. Phân cấp workload

Một policy:

~~~text
Critical: authorization and stock reservation
Normal: point reads and metadata updates
Bounded: catalog list queries
Background: indexing, reports and bulk exports
~~~

Thực hiện bằng resource budgets, priority queues, concurrency limits và monitoring. **Background jobs phải có kill switch/pause** để traffic quan trọng vẫn đạt SLO.

---

## 81. Logging đủ để truy vết, không làm lộ dữ liệu

Có thể log:

~~~text
requestId
operation=product.update
skuHash / maskedSku
result=VERSION_CONFLICT
durationMs
attemptCount
dbErrorClass
```

Không log:

- MongoDB URI chứa credentials.
- Token/JWT.
- Full request body có PII.
- Raw stack trace ra HTTP client.
- Unbounded error payload.
- Plaintext secrets.
- Query chứa nhạy cảm trong metrics labels.

Trong demo SKU không phải dữ liệu cá nhân, nhưng khi mở rộng nhiều tenants/PII cần thiết kế log classification.

## 82. Correlation ID và tracing

Một request đi qua:

~~~text
Ingress -> Controller -> Service -> Mongo Driver -> Database
~~~

Nên giữ cùng `traceId/requestId` và đo:

- End-to-end HTTP time.
- Database command duration.
- Retry count.
- Pool checkout time.
- Server selection failures.
- Query type.
- Conflict rate.

Nếu dùng OpenTelemetry/Micrometer tracing, không đưa body/secret vào attributes; giới hạn high-cardinality labels.

## 83. Actuator health cần quyền truy cập

Ví dụ `management.endpoints.web.exposure.include: "health,info"` cung cấp các endpoints theo cấu hình và dependencies.

Production cần:

- Restrict management endpoints qua network/security policy.
- Không phơi health details chứa topology/credentials.
- Readiness khác liveness.
- Tránh health probes quá nặng gây DB overload.
- Không dùng health status duy nhất để chứng minh correctness nghiệp vụ.

Một liveness probe fail tùy tiện có thể restart toàn bộ pods trong lúc database chậm, tạo reconnection storm.

## 84. Readiness và liveness

**Liveness:** process có bị kẹt cần restart không?

**Readiness:** process có nên nhận requests mới không?

Khi MongoDB temporarily unavailable:

- Readiness có thể chuyển NOT_READY theo policy để giảm traffic.
- Liveness không nhất thiết FAIL ngay, vì restart không sửa được DB outage.
- Application cần backoff để tránh thundering herd.
- Incident/alerts cần thông tin cụ thể, không chỉ “unhealthy”.

Tùy kiến trúc, có thể tránh phụ thuộc check DB liên tục ở liveness path.

## 85. Những metrics nên có

| Metric | Vì sao |
|---|---|
| HTTP p95/p99 theo route | SLO người dùng |
| Create/update/delete success rates | Bức tranh business |
| Validation errors | Client misuse/threat indicators |
| Version conflict rate | Contention/stale clients |
| Insufficient stock rate | Business behavior |
| MongoDB command latency | Database bottleneck |
| Pool checkout wait/timeouts | Pool exhaustion |
| Open connections per pod/server | Resource capacity |
| Read/write ops/s | Capacity/cost |
| Cursor/list page size/bytes | Resource abuse |
| GC pauses/heap | Memory pressure |
| DB replication lag | Read freshness/failover |
| Retry attempts/unknown writes | Ambiguous outcomes |
| Rate-limit rejections | Admission control |
| Error code counts | Stable incident classification |

Không dùng raw SKU/customerId làm metrics label nếu cardinality lớn. Lưu breakdown ở structured logs có retention/PII rules tương ứng.

## 86. Đo p99 đúng cách

Không lấy trung bình p99 của mỗi pod rồi coi là p99 toàn dịch vụ. Với histogram metrics, aggregate bucket counts và tính quantile theo cùng thời gian/route.

Đo:

- p50/p95/p99.
- Success throughput.
- Error/timeout rate.
- Database pool wait.
- Traffic mix.
- Window dưới peak.
- Deployment version.

Một throughput tăng nhưng error rate tăng 20% không phải cải thiện hệ thống.

## 87. Circuit breaker và retries

Một circuit breaker có thể giảm liên tục gửi traffic vào MongoDB đang lỗi. Nhưng:

- Không làm mất accepted writes chưa rõ outcome.
- Không retry mutation non-idempotent vô hạn.
- Có retry budget và exponential backoff/jitter.
- Distinguish duplicate key/version conflict khỏi transient error.
- Không fallback từ authoritative write sang cache stale.
- Không tự báo success vì circuit open.

Đặc biệt với stock reservation/payment, **retry phải đi kèm operation ID và reconciliation** nếu muốn bảo đảm effect chỉ một lần.

## 88. Idempotency extension: operation ID

Một API production có thể nhận:

~~~http
Idempotency-Key: reserve-tenantA-KB101-order42
~~~

Server cần **ràng buộc key với tenant, operation type, resource, payload fingerprint và retention**. Một ledger có thể ghi outcome cho các retries cùng intent.

Nếu ledger nằm ngoài Product document, đảm bảo **atomicity giữa stock decrement và operation record** bằng transaction hoặc thay data model để chúng ở cùng atomic boundary. Hai writes rời nhau không tự đủ: crash giữa chúng có thể gây double reserve khi retry.

## 89. Thiết kế lưu reservation trong một aggregate

Một hướng khác:

~~~json
{
  "_id": "KB-101",
  "stock": 10,
  "version": 8,
  "recentOperations": {
    "reserve-42": {"qty": 2, "result": "APPLIED"}
  }
}
~~~

Có thể thực hiện atomically trên một document để ngăn duplicate business effect trong horizon nhất định. Nhưng lưu operation IDs vô hạn trong document sẽ làm tăng kích thước, contention và giới hạn BSON document; cần retention/archival và replay horizon rõ. **Đây là lựa chọn thiết kế cần đánh giá**, không phải yêu cầu “thêm một Map” là xong.

## 90. Product metadata vs inventory ledger

Trong demo, stock là một scalar trong Product. Ở thương mại thật, có thể cần:

- Inventory per warehouse.
- Reservation expiry.
- Commit/cancel reservation.
- Returns.
- Audit/history.
- Inventory adjustments.
- No oversell across stores.
- Cross-region consistency.
- Order/payment coordination.

Khi nghiệp vụ phức tạp, nên thiết kế **Inventory aggregate/ledger** riêng và giữ product catalog metadata độc lập, thay vì cố nhồi mọi lệnh vào CRUD cơ bản.

## 91. Tránh dùng `save` cho mọi mutation

Spring Data repository `save` rất tiện cho CRUD cơ bản, nhưng phải hiểu:

- Create vs upsert semantics.
- Versioning annotation nếu dùng.
- Full document overwrite vs partial update.
- Conditional writes.
- Race between reads and writes.
- Side effects của mapping events/callbacks.

Trong bài này, dùng `insert` cho create và `findAndModify`/`findAndRemove` có predicate cho mutations để **trình bày rõ safety boundary**. Không phải `save` luôn sai; nó chỉ cần được dùng với concurrency semantics hiểu đúng.

## 92. Delete mềm (soft delete) và tombstone

Một production alternative:

~~~json
{
  "_id": "KB-101",
  "deleted": true,
  "version": 12,
  "deletedAt": "2026-11-14T08:00:00Z"
}
~~~

Ưu điểm:

- Chặn stale historical mutation.
- Có audit/time marker.
- Hỗ trợ CDC/replay.
- Dễ phân biệt deleted vs never existed.

Nhưng còn phải:

- Lọc `deleted=false` ở mọi queries.
- Xử lý unique SKU/recreate policy.
- Quản lý retention và privacy deletion.
- Không để stale cache/search hiển thị record.
- Tránh nhầm soft delete với erasure đầy đủ.

## 93. TTL không tự là delete theo business contract

Nếu chuyển Product sang mô hình Session có `expiresAt`, MongoDB TTL index có thể xóa bất đồng bộ. API authorization phải kiểm `expiresAt` ở read path theo trusted clock.

Không dùng “document còn tồn tại” đồng nghĩa “session còn hạn”. Đồng thời khi copy/backfill, không reset lifetime bằng thời gian import trừ khi business contract yêu cầu.

## 94. Multi-tenant API cần tenant ID đáng tin

Một bước mở rộng production:

~~~text
Authenticated JWT/principal
  -> trusted tenantId
  -> query (_id, tenantId, version)
  -> update/delete only matching tenant
~~~

Không lấy tenantId trong request body hoặc `X-Tenant-Id` do client tự đặt mà coi đã xác thực. Khi hai tenants được phép dùng cùng SKU, phải dùng:

- Composite unique index `(tenantId, sku)`, hoặc
- Stable `_id` encode không collision, hoặc
- Generated immutable entity ID cộng unique scope.

Mọi read/update/delete/list/cursor/query phải cùng tenant scope. **Chỉ kiểm quyền ở controller rồi query `_id` toàn cục là thiếu phòng vệ sâu** khi architecture mở rộng.

## 95. Cross-tenant cursor tampering

Giả sử client tenant A nhận cursor có SKU `"KB-101"`, rồi dùng cursor đó với tenant B. Nếu endpoint không filter tenant B từ trusted context, có thể gây data exposure.

Production cursor nên chứa hoặc bind:

~~~text
schemaVersion
tenantId
filters
sortKey and tie-breaker
expiry
integrity signature
~~~

Dù cursor đã ký, **authorization vẫn phải được kiểm lại** cho mỗi request.

## 96. Deletion và dữ liệu cá nhân

Một `DELETE` trên source document không tự xóa:

- Search/read model projection.
- Cache.
- CDC queue.
- Backup.
- Audit/analytics.
- External exports.

Với user data deletion, cần workflow/lifecycle contract riêng, có retention exceptions và xác nhận hoàn thành đúng điều kiện. Bài Product CRUD **không phải implementation đầy đủ của privacy erasure**.

## 97. Thay database engine: điều gì giữ nguyên?

| Concern | MongoDB | DynamoDB | Cassandra | Redis |
|---|---|---|---|---|
| Create uniqueness | `_id`/unique index | ConditionExpression | LWT/partition-specific design | `SET NX`/Lua per key |
| Read | Find by indexed key | GetItem/Query | By partition/clustering key | GET/HGET |
| CAS update | `findAndModify` query version | Conditional UpdateItem | LWT IF predicate | Lua/transaction pattern |
| Delete | Guarded findAndRemove | Conditional DeleteItem | Conditional LWT when required | Lua compare-and-delete |
| Pagination | Indexed keyset/cursor | LastEvaluatedKey | Driver paging/partition range | SCAN not snapshot |
| TTL | TTL indexes async | TTL async | TTL/tombstones | Server key expiration |
| Pool/resources | Driver pool/cursor | SDK HTTP clients/capacity | Session/paging | Client pools/SCAN |

Đây là khái quát conceptual, **không hứa cùng một consistency level** giữa các APIs. Mỗi adapter cần chứng minh invariant theo scope, latency và failure semantics của engine thật.

## 98. DynamoDB implementation idea

Nếu Product nằm trong DynamoDB:

~~~text
pk = PRODUCT#KB-101
attributes: name, priceCents, stock, version
~~~

Create với `attribute_not_exists(pk)`, update có `ConditionExpression version = :expected`, reserve có cả `stock >= :qty` và version match; DeleteItem có condition đúng phiên bản. Query list thường cần **access pattern/index riêng**, không mong full table Scan là tương đương MongoDB sorted list.

SDK Java v2 có async/sync clients và HTTP pools; close client đúng lifecycle. On-demand/provisioned capacity, throttling và per-partition limits tạo resource budget riêng.

## 99. Cassandra implementation idea

Một bảng Product theo partition key SKU:

~~~text
PRIMARY KEY (sku)
~~~

Point read/update theo partition là phù hợp. Nhưng ordinary writes có timestamp conflict semantics, không tự thực thi Java expectedVersion CAS. Khi cần atomic conditional update, xem **Lightweight Transactions (LWT)** theo API và consistency configuration phù hợp.

Cassandra có tombstones/TTL/repair/compaction behavior; bulk table listing và secondary filters cần data model khác, không dịch trực tiếp MongoDB query thành CQL `ALLOW FILTERING` trên bảng lớn.

## 100. Redis implementation idea

Với Product cached hoặc nhỏ, có thể dùng Hash và Lua script cho atomic check:

~~~text
read current version and stock
if version matches and stock >= quantity:
    decrement stock
    increment version
else:
    return conflict
~~~

Script cần atomic execution trong scope của Redis deployment; Redis replication/persistence/failover có durability và consistency khác database primary có quorum. Nếu Redis chỉ là cache, source-of-truth vẫn ở DB khác: **đừng lấy cache lock/stock làm authoritative ledger** trừ khi kiến trúc có bảo đảm đầy đủ.

---

## 101. Kiểm thử phải xuất phát từ hợp đồng, không chỉ status 200

Một bộ test CRUD tối thiểu:

| Operation | Test bình thường | Test lỗi/cạnh tranh |
|---|---|---|
| Create | 201, persisted state | Duplicate SKU, missing fields, invalid type |
| Get | 200, correct SKU | Missing, invalid path, tenant mismatch |
| List | Sorted page, nextCursor | Negative/large limit, cursor invalid |
| Update | Version tăng, fields đúng | Stale version, concurrent writers |
| Reserve | Stock giảm, version tăng | Quantity > stock, two clients reserve last item |
| Delete | 204, cannot get | Stale version, second delete, recreate |
| Resource | Client reused, cursor closed | Pool saturation, timeout, cancellation |
| Failure | Recover gracefully | ACK lost, unknown commit, DB unavailable |

Đánh giá **database state sau thao tác**, không chỉ so response. Một API có thể trả `200` nhưng state sai hoặc update bị ghi đè sau đó.

## 102. Tách unit, integration và concurrency tests

- **Unit tests:** validation/normalization, business decisions, Clock, error mapping; không cần DB thật.
- **Integration tests:** MongoDB driver, serialization, atomic conditions, indexes, CRUD và error semantics.
- **Concurrency tests:** nhiều clients cùng mutate một SKU, invocation/completion outcomes.
- **Fault tests:** timeout, primary step-down, reconnect, ACK loss, process restart trong sandbox có topology phù hợp.
- **Performance/resource tests:** p99, pool wait, memory, cursor và page sizes dưới representative load.

Một embedded mock/fake không tự mô phỏng MongoDB failover hay transactional guarantees.

## 103. Testcontainers: tạo MongoDB thật cho integration

`ProductServiceIntegrationTest.java`:

~~~java
package com.example.catalog;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class ProductServiceIntegrationTest {

    @Container
    static MongoDBContainer db =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            db::getReplicaSetUrl
        );
    }

    @Autowired ProductService service;
    @Autowired MongoTemplate mongo;

    @BeforeEach
    void clean() {
        mongo.dropCollection(Product.class);
    }

    @Test
    void createAndRead() {
        ProductResponse created = service.create(
            new CreateProductRequest(
                "KB-101", "Ban phim", 1000L, 5L)
        );

        assertEquals("KB-101", created.sku());
        assertEquals(1L, created.version());
        assertEquals(5L, service.get("KB-101").stock());
    }
}
~~~

Test dùng Docker/container sandbox và dynamic Mongo URI. `mongo:7.0` và Boot 3.3.5 chỉ là **ví dụ baseline**; chọn images/driver versions đã được phê duyệt. `@BeforeEach` drop collection **chỉ an toàn vì DB là fixture test cô lập**; tuyệt đối không trỏ test này vào production DB.

## 104. Test duplicate SKU

Trong cùng integration test class:

~~~java
@Test
void duplicateSkuIsRejected() {
    service.create(new CreateProductRequest(
        "KB-101", "One", 1000L, 1L
    ));

    assertThrows(
        ProductAlreadyExistsException.class,
        () -> service.create(new CreateProductRequest(
            "KB-101", "Other", 2000L, 2L
        ))
    );

    assertEquals("One", service.get("KB-101").name());
}
~~~

Điều cần chứng minh: duplicate create không overwrite data. `insert` + unique `_id` bảo đảm điều này; application `exists` check riêng không phải tuyến phòng vệ cuối.

## 105. Test update đúng và update stale

~~~java
@Test
void updateUsesExpectedVersion() {
    service.create(new CreateProductRequest(
        "KB-101", "Original", 1000L, 5L
    ));

    ProductResponse v2 = service.update(
        "KB-101",
        new UpdateProductRequest("New", 2000L, 1L)
    );

    assertEquals(2L, v2.version());
    assertEquals("New", v2.name());

    assertThrows(
        VersionConflictException.class,
        () -> service.update(
            "KB-101",
            new UpdateProductRequest("Old overwrite", 100L, 1L)
        )
    );

    ProductResponse current = service.get("KB-101");
    assertEquals(2L, current.version());
    assertEquals("New", current.name());
}
~~~

Nếu bỏ predicate `version == expectedVersion` trong service, test này phải phát hiện stale overwrite.

## 106. Test reserve không cho tồn kho âm

~~~java
@Test
void reserveCannotOversell() {
    service.create(new CreateProductRequest(
        "KB-101", "One", 1000L, 1L
    ));

    ProductResponse reserved = service.reserve(
        "KB-101",
        new ReserveStockRequest(1L, 1L)
    );

    assertEquals(0L, reserved.stock());
    assertEquals(2L, reserved.version());

    assertThrows(
        InsufficientStockException.class,
        () -> service.reserve(
            "KB-101",
            new ReserveStockRequest(1L, 2L)
        )
    );

    assertEquals(0L, service.get("KB-101").stock());
}
~~~

Lỗi lượng không đủ chỉ nên xảy ra khi version hiện tại khớp; nếu version cũ, theo policy của helper, version conflict được ưu tiên.

## 107. Test xóa theo version

~~~java
@Test
void deleteRequiresFreshVersion() {
    service.create(new CreateProductRequest(
        "KB-101", "One", 1000L, 1L
    ));

    service.update(
        "KB-101",
        new UpdateProductRequest("Two", 1000L, 1L)
    );

    assertThrows(
        VersionConflictException.class,
        () -> service.delete("KB-101", 1L)
    );

    service.delete("KB-101", 2L);

    assertThrows(
        ProductNotFoundException.class,
        () -> service.get("KB-101")
    );
}
~~~

Test này chưa kiểm tombstone/generation, vì demo xóa vật lý; cần mở rộng khi API có hard delete, CDC hoặc re-create.

## 108. Test phân trang không duplicate trong dataset bất biến

~~~java
@Test
void paginationIsBoundedAndOrdered() {
    service.create(new CreateProductRequest(
        "KB-101", "A", 10L, 1L
    ));
    service.create(new CreateProductRequest(
        "KB-102", "B", 10L, 1L
    ));
    service.create(new CreateProductRequest(
        "KB-103", "C", 10L, 1L
    ));

    ProductPage first = service.list(null, 2);
    assertEquals(2, first.items().size());
    assertEquals("KB-102", first.nextCursor());

    ProductPage second = service.list(first.nextCursor(), 2);
    assertEquals(1, second.items().size());
    assertEquals("KB-103", second.items().get(0).sku());
    assertNull(second.nextCursor());
}
~~~

Property “đọc đầy đủ không duplicate” ở đây dùng dataset **bất biến giữa các pages**. Với production concurrent inserts/deletes, keyset API không tự cung cấp snapshot.

## 109. Test giới hạn page size

~~~java
@Test
void paginationLimitIsValidated() {
    assertThrows(
        BadRequestException.class,
        () -> service.list(null, 0)
    );

    assertThrows(
        BadRequestException.class,
        () -> service.list(null, 101)
    );

    assertThrows(
        BadRequestException.class,
        () -> service.list("bad sku", 10)
    );
}
~~~

Đối với actual HTTP endpoint, thêm tests cho `limit=abc`, `after=` và payload lớn. Khi test chỉ gọi service trực tiếp, không có Spring MVC deserialization.

## 110. MockMvc kiểm HTTP validation

`ProductControllerTest.java` có thể viết:

~~~java
package com.example.catalog;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired MockMvc mvc;

    @MockBean ProductService service;

    @Test
    void invalidSkuReturns400() throws Exception {
        mvc.perform(post("/api/v1/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": "kb-101",
                      "name": "Keyboard",
                      "priceCents": 100,
                      "stock": 5
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

`@MockBean` được minh họa theo baseline Spring Boot 3.3; các phiên bản mới có thể khuyến nghị annotation khác. `@WebMvcTest` kiểm web validation/binding nhưng **không kiểm atomic DB condition**; vì vậy vẫn cần MongoDB integration test.

## 111. Test concurrency với `CountDownLatch`

Một test nhiều threads cùng reserve SKU chỉ còn stock=1:

~~~java
@Test
void concurrentReservationsHaveSingleWinner()
        throws Exception {

    service.create(new CreateProductRequest(
        "RACE-1", "Only one", 100L, 1L
    ));

    java.util.concurrent.CountDownLatch ready =
        new java.util.concurrent.CountDownLatch(2);
    java.util.concurrent.CountDownLatch go =
        new java.util.concurrent.CountDownLatch(1);

    var pool = java.util.concurrent.Executors
        .newFixedThreadPool(2);

    try {
        java.util.concurrent.Callable<Boolean> reserve = () -> {
            ready.countDown();
            go.await();
            try {
                service.reserve(
                    "RACE-1",
                    new ReserveStockRequest(1L, 1L)
                );
                return true;
            } catch (VersionConflictException ex) {
                return false;
            }
        };

        var a = pool.submit(reserve);
        var b = pool.submit(reserve);

        assertTrue(ready.await(
            5, java.util.concurrent.TimeUnit.SECONDS
        ));
        go.countDown();

        int success = (a.get() ? 1 : 0)
                    + (b.get() ? 1 : 0);

        assertEquals(1, success);
        assertEquals(0L, service.get("RACE-1").stock());
        assertEquals(2L, service.get("RACE-1").version());
    } finally {
        go.countDown();
        pool.shutdownNow();
    }
}
~~~

Giả định ở test này: không có external writes, không timeout/unknown result và source MongoDB khỏe. Trong fault tests có ambiguous outcomes, **không được coi timeout đồng nghĩa “thất bại và không đổi state”**.

## 112. Test concurrency không phải proof toàn hệ

Một test hai threads pass cho thấy behavior đúng trong **lịch được thử**, nhưng chưa chứng minh:

- Mọi interleavings.
- Primary step-down.
- Cross-region conflict.
- Network partition.
- Acknowledged write durability.
- Sessions/read concerns khác.
- Multi-document inventory.
- External payment side effects.

Muốn đánh giá strong consistency dưới faults, cần **history recorder + consistency checker** phù hợp với API và failure model.

## 113. Mô hình test với command sequence

Có thể định nghĩa reference model:

~~~text
State: stock, price, name, version, deleted

Create(sku, attrs):
  if absent -> version 1

Update(expectedVersion, attrs):
  if currentVersion matches -> advance

Reserve(expectedVersion, qty):
  if version matches AND stock>=qty -> decrement and advance

Delete(expectedVersion):
  if version matches -> deleted

Get:
  returns current visible state
~~~

Sinh sequences random `Create→Update→Reserve→Delete→Retry` rồi so với SUT bằng test containers. Nhớ phân biệt **hard-delete/re-create lifetime** và **unknown commits**; một model không được giả định điều engine không hứa.

## 114. Property-based test input boundaries

Sinh:

- SKU quá ngắn/dài.
- Lowercase và ký tự phân cách.
- Unicode trong name.
- Blank/whitespace.
- Price 0, lớn, âm.
- Stock 0, lớn, âm.
- Null/missing numeric fields.
- ExpectedVersion cũ/mới.
- Reserve quantity bằng stock hoặc vượt stock.
- Cùng SKU trong concurrent creates.
- Delete→recreate.
- Cursor ở ranh giới.

Một vài `@Test` cố định thường không bao phủ đủ edge cases; các framework như jqwik giúp sinh và shrink phản ví dụ.

## 115. Test lỗi backend unavailable

Không có DB hoặc kết nối hỏng:

- Application không nên treo request vô hạn.
- Client nhận 503/5xx phù hợp, không phải stacktrace.
- Pool checkout/server selection có bound.
- Metrics/alert đủ để điều tra.
- Không spam retries không giới hạn.
- Readiness/load shedding theo policy.
- Unknown write outcome được xử lý khi connectivity phục hồi.

Một test dùng `mongo:7.0` một container **không mô phỏng multi-node failover**, nên phải tách test cluster riêng cho tình huống đó.

## 116. Test lost acknowledgment

Kịch bản cần một fault injector/proxy trong sandbox:

~~~text
Client sends update(expectedVersion=7).
Database applies version=8.
Response packet is dropped.
Client sees timeout.
Client retries.
~~~

Test các outcome:

- Version CAS chặn stale overwrite.
- Client không báo chắc request lần đầu failed.
- Operation ID nếu có giúp trả previous outcome/reconcile.
- Không gửi email/payment trùng.
- Retry budget không gây storm.

Không chỉnh network production để thử fault injection nếu không có change controls.

## 117. Test pool saturation

Dùng load generator có bounded RPS và nhiều concurrent requests. Quan sát:

- Pool checkout wait.
- MongoDB connections.
- HTTP p99.
- Error/timeout rates.
- Heap/GC.
- Database CPU/IO.
- Client retries.
- Resource cleanup after load stops.

Một test tạo 100.000 threads trong một JVM để “stress” có thể chỉ stress thread scheduler/heap, không đo đúng bottleneck database. Dùng controllable concurrency và representative query mix.

## 118. Test cursor resource cleanup

Một script export:

1. Mở cursor.
2. Đọc 100 records.
3. Inject exception hoặc cancel job.
4. Confirm `try-with-resources` đóng cursor.
5. Confirm client/application vẫn có khả năng phục vụ.
6. Check server cursor/resource metrics nếu có.

Không gọi `close()` trên singleton Spring client mỗi khi một cursor kết thúc.

## 119. Test graceful shutdown

Kịch bản:

~~~text
1. Start API and send slow operations.
2. Signal graceful shutdown in test deployment.
3. Stop admitting new requests.
4. Observe in-flight completion/cancellation within budget.
5. Check DB pool is closed when process exits.
6. Reconcile ambiguous mutations.
~~~

Không chỉ assert process exit code 0: cần kiểm những mutations đã được ACK có bền theo contract và không double effect nếu clients retry.

## 120. Test validation trước database call

Một lỗi input rõ ràng nên bị reject **trước khi có DB work** khi rule không phụ thuộc DB:

~~~text
name blank -> 400, 0 DB mutations
stock negative -> 400, 0 DB mutations
expectedVersion negative -> 400, 0 DB mutations
limit=1_000_000 -> 400, no unbounded scan
~~~

Nhưng `SKU exists`, `stock sufficient`, `version current` cần database authority để tránh race. Không kiểm chúng bằng HTTP validation rồi tin đủ.

## 121. Test unauthorized tenant access

Khi mở rộng production với Spring Security:

~~~text
Principal tenant=A
Request target SKU owned by tenant=B
```

Assert:

- Không trả product B.
- Không update/delete/reserve B.
- Không lộ B qua count/search/cursor.
- Không leak data trong errors/logs.
- Queries include trusted tenant predicate.
- Same SKU across tenants vẫn unique đúng scope.

Một test endpoint trả 404 chưa đủ nếu DB mutation vẫn xảy ra sau đó.

## 122. CI pipeline đề xuất

~~~text
Commit:
  compile
  unit tests for DTO/service rules
  MockMvc validation tests

Pull request:
  integration tests with MongoDB sandbox
  duplicate/CAS/delete/pagination
  concurrency test

Nightly:
  more randomized sequences
  load/resource tests
  failure injection on dedicated cluster

Pre-release:
  failover/restore tests
  security tests
  schema migration compatibility
  operational review
~~~

Đây là đề xuất xây **test strategy** cho người học. Bước viết Markdown của worker này **không thực thi Maven, Gradle, CI hay QA**; việc chạy test thuộc môi trường thực hành riêng.

## 123. Test evidence

Khi một test thất bại, ghi:

~~~text
testId, requestId, operationId
seed / generated input
SKU (masked where appropriate)
expectedVersion and observedVersion
HTTP status and error code
MongoDB/driver/Boot versions
consistency/read/write concern
topology/fault timeline
client attempt count
elapsed time/p99
```

Không ghi passwords, tokens hoặc user PII vào logs công khai. Với concurrency, seed không đủ; cần **operation invocation/completion history** để tái hiện interleaving.

## 124. Đọc MongoDB query plan

Trong lab, có thể kiểm truy vấn đúng `_id` index bằng `explain()` trong MongoDB shell cho query tương đương:

~~~javascript
db.products.find({
  _id: { $gt: "KB-100" }
}).sort({ _id: 1 }).limit(25).explain("executionStats")
~~~

Quan sát:

- Keys/docs examined.
- Index scan vs collection scan.
- Sort cost.
- Execution stats.
- Performance khi data lớn.

Không suy từ một explain trên 10 documents rằng query sẽ đạt p99 khi có hàng triệu records và data không fit cache.

## 125. Kiểm storage/index constraints

Trong MongoDB, `_id` unique index được tạo tự động. Nếu production thêm query như:

~~~text
GET products?category=X&sort=price
~~~

cần thiết kế compound index/denormalized model phù hợp và chi phí write/index. Không đơn giản cho client sort tùy ý bằng field không có index; có thể gây full scan/in-memory sort hoặc resource saturation.

## 126. Deployment environment variables

Nên tách:

~~~text
MONGODB_URI
HTTP_PORT
LOG_LEVEL
REQUEST_TIMEOUT
MAX_PAGE_SIZE
RATE_LIMIT_POLICY
AUTH_CONFIG
```

Mongo URI có thể chứa secrets, nên:

- Quản lý bằng secrets manager.
- Không in ra logs/stacktrace.
- Không commit vào Git.
- Rotate credentials.
- Dùng least privilege DB user.
- Không dùng admin credentials cho CRUD API.

Chỉ override `MONGODB_URI` trong lab để trỏ test cluster; tránh dùng cùng URI production trong CI.

## 127. DB user nên có quyền tối thiểu

Một catalog CRUD user không cần:

- Manage users/roles.
- Admin entire cluster.
- Drop arbitrary databases.
- Execute server scripts tùy ý.
- Read unrelated tenant collections.
- Access backup credentials.
- Create indexes trong production một cách tự phát.

Khi `auto-index-creation: false`, indexes/schema được quản lý bởi migration/admin pipeline đã phê duyệt, tách khỏi runtime service credentials.

## 128. Database schema migrations

MongoDB schema linh hoạt không nghĩa schema không tồn tại. Khi thêm `category`:

- Define DTO API.
- Add defaults/nullable policy.
- Make readers backward-compatible.
- Backfill existing records nếu cần.
- Create index an toàn.
- Deploy theo expand–migrate–contract.
- Maintain optimistic version semantics.
- Test mixed old/new documents.

Không deploy field required vào reader mới khi dữ liệu lịch sử còn thiếu mà không có fallback/migration plan.

## 129. Update schema và optimistic lock

Nếu backfill thay đổi Product document và không tăng/business version đúng policy, API có thể overwrite fields mới bằng stale data.

Thiết kế:

- Source version per aggregate.
- Migration version/generation riêng.
- Atomic conditional updates.
- Tránh full-document overwrite nếu thay partial fields.
- Audit/reconciliation.
- Không reset `version` khi re-import.

Phân biệt `schemaVersion` với `sourceVersion`: schemaVersion không thay thế ordering của business mutations.

## 130. Resource-aware bulk operations

Khi cần nhập 1 triệu Products, không gọi HTTP POST 1 triệu lần không giới hạn concurrency rồi giữ mọi kết quả trong RAM.

Xây một import job riêng:

- Bounded scan/page.
- Batch size và bytes limits.
- Idempotent/conditional writes.
- Retry budget/backoff/jitter.
- Durable checkpoint.
- DLQ/quarantine.
- Rate limit theo DB headroom.
- Pause/kill switch.
- Production SLO guardrail.
- Reconcile result count/key sets.
- Cleanup temporary resources.

Bulk import/backfill là bài toán **pipeline correctness + workload isolation**, không thể giải chỉ bằng `@Async`.

## 131. Resource leaks trong event consumers

Nếu service còn tiêu thụ CDC/Kafka events để cập nhật MongoDB:

- Consumer client giữ lifecycle dài.
- Đóng/cancel khi shutdown.
- Commit offsets sau durable sink outcome.
- Handle duplicates/idempotency.
- Không commit vượt failed event.
- Bounded in-flight.
- Dead-letter poison records.
- Monitor lag and retention.

Đừng đặt consumer trong HTTP request thread hoặc quên lifecycle khi app scale down.

## 132. Triển khai đa node và version consistency

Khi chạy nhiều Java pods:

~~~text
Pod A -> MongoDB
Pod B -> MongoDB
Pod C -> MongoDB
~~~

Các pods không chia sẻ Java `synchronized` hay in-memory Maps. Vì vậy **uniqueness/CAS/stock guard** phải nằm trong MongoDB authoritative operation hoặc một transactional protocol khác.

Nếu thêm cache, đọc stale từ cache chỉ nên dùng cho những access patterns mà consistency policy cho phép; không dùng cache version cũ để quyết định reserve mà không có source-side guard.

## 133. API design: đặt giới hạn trước tính năng

Khi thêm features:

~~~text
Search product
Filter by category
Sort by price
Bulk import
Export all
Delete by criteria
```

hãy xác định:

- Authorization scope.
- Index/query access pattern.
- Maximum page size/bytes.
- Rate/time budget.
- Memory and cursor lifecycle.
- Conditional mutation semantics.
- Retry/idempotency contract.
- Audit and monitoring.
- Production load impact.

Một API feature “đơn giản” có thể tạo một full scan rất đắt nếu không có guardrail.

---

## 134. Lộ trình thực hành từ đầu đến cuối

Có thể chia lab thành các chặng nhỏ:

**Chặng 1 — Tạo project**

- Cài Java 17+, Maven và Docker (hoặc MongoDB sandbox).
- Tạo `pom.xml`, application entrypoint, `application.yml`.
- Cấu hình local `MONGODB_URI`.
- Chạy ứng dụng và kiểm health endpoint theo security policy.
- Đảm bảo không dùng URI chứa credentials trong source code.

**Chặng 2 — CRUD**

- Tạo Product document, DTOs và controller/service.
- Gửi POST, GET, PUT, GET list, DELETE.
- Đọc trạng thái MongoDB bằng công cụ sandbox.
- Quan sát `version`, `createdAt`, `updatedAt`.

**Chặng 3 — Validation**

- Thử body thiếu field, negative stock, SKU lowercase.
- Thử name trắng, SKU quá dài, `limit=100000`.
- Kiểm mọi invalid request trả 400 và không mutate DB.
- Bổ sung giới hạn bytes/rate ở ingress khi cần.

**Chặng 4 — Concurrency**

- Đọc version từ GET.
- Gửi hai PUT cùng `expectedVersion`.
- Gửi hai reservations trên last item.
- Xác nhận chỉ một CAS success, stock không âm.
- Thử stale DELETE.

**Chặng 5 — Resources/failures**

- Chạy list với page limit.
- Quan sát pool/connections khi tăng RPS.
- Thử dừng MongoDB sandbox và xem timeout/503 behavior.
- Thử cursor export với `try-with-resources`.
- Khôi phục DB, kiểm trạng thái cuối.

**Chặng 6 — Tích hợp CI**

- Unit tests.
- MockMvc validation.
- Testcontainers integration.
- Concurrency tests.
- Runbook/resource dashboards.
- Test cleanup và secrets policy.

## 135. Một state timeline có thể tự đối chiếu

| Bước | Request | Kết quả | MongoDB state |
|---|---|---|---|
| 1 | POST `KB-101` stock 5 | 201 | stock 5, version 1 |
| 2 | GET `KB-101` | 200 | Không đổi |
| 3 | PUT expected 1 | 200 | price/name đổi, version 2 |
| 4 | Reserve qty 2 expected 2 | 200 | stock 3, version 3 |
| 5 | Reserve qty 4 expected 3 | 422 | stock 3, version 3 |
| 6 | PUT expected 1 | 409 | Không đổi |
| 7 | DELETE expected 2 | 409 | Không đổi |
| 8 | DELETE expected 3 | 204 | Document bị xóa |
| 9 | GET `KB-101` | 404 | Không đổi |

State được trình bày trong một môi trường **không có requests khác**. Khi có concurrent requests, trạng thái có thể tiến lên version khác; tests phải xét lịch sử thật.

## 136. Kiểm tình trạng collection bằng MongoDB shell

Trong môi trường sandbox:

~~~javascript
use catalog;

db.products.findOne({ _id: "KB-101" });

db.products.find(
  { _id: { $gt: "KB-100" } },
  { _id: 1, name: 1, priceCents: 1, stock: 1, version: 1 }
).sort({ _id: 1 }).limit(25);
~~~

Đây là commands đọc trong lab. Khi production, truy cập database phải dùng readonly roles/approved tooling và tránh in PII.

## 137. Những lỗi thường gặp lúc khởi động

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
|---|---|---|
| Cannot connect | MongoDB chưa chạy, sai URI, firewall | Endpoint, DNS, container |
| Server selection timeout | Không có server đúng topology/read preference | URI, replica set, nodes |
| Connection refused | Port/bind chưa mở | Listener, Docker mapping |
| Authentication failed | Credentials/roles sai | Secret, auth database |
| TLS handshake failed | Certificate/CA/hostname | Truststore, TLS config |
| Duplicate key | `_id` đã tồn tại | GET current record, 409 |
| Validation 400 | DTO fields không hợp lệ | Body/schema |
| Version conflict 409 | Client dùng version cũ | Refresh current version |
| Pool timeout | Quá tải hoặc giữ connection lâu | Pool wait, p99, DB load |
| Cursor timeout | Scan quá lâu, cursor không tiêu thụ | Batch, lifecycle, deadline |
| Query slow | Thiếu index/scatter/large payload | Explain, data size |

Không “sửa” lỗi kết nối bằng cách tắt authentication/TLS trên môi trường được truy cập công khai.

## 138. Troubleshooting duplicate key

Khi create cùng SKU nhiều lần:

~~~text
POST A -> insert KB-101
POST B -> insert KB-101
```

Kết quả mong đợi:

- Một insert thành công.
- Insert còn lại bị unique `_id` từ chối.
- Record đầu không bị replace.
- API trả 409 thay vì 500 raw stacktrace.

Không bắt `DuplicateKeyException` rồi tự `save` ghi đè record như biện pháp fallback.

## 139. Troubleshooting stale version

Nếu API cập nhật trả 409:

1. Xác định current resource version.
2. Kiểm client có retry cùng command cũ không.
3. Đọc lại state qua đúng read consistency path.
4. Quyết định merge/reapply theo nghiệp vụ.
5. Gửi request mới với expectedVersion hiện tại nếu user/business cho phép.
6. Không tự lặp 409 vô hạn.

Một 409 trong optimistic concurrency đôi khi là **hành vi đúng dưới contention**, không phải production incident.

## 140. Troubleshooting stock conflict

Nếu Product stock 3 nhưng client reserve 4:

- Request là domain-rejected.
- Không thay stock/version.
- 422 cho client biết quantity vượt available.
- Không tự đổi quantity từ 4 xuống 3 nếu user không đồng ý.
- Không gửi external side effect.
- Ghi business metric `insufficient_stock` nếu phù hợp.

Nếu có concurrent update giữa failed condition và error classification, response có thể là 409 thay vì 422; **atomic guard vẫn bảo vệ stock**.

## 141. Troubleshooting request timeout

Một request PUT timeout có thể đã commit:

~~~text
Client v5 -> PUT
DB updates v6
response lost
client timeout
~~~

Không thể suy “DB không đổi” chỉ từ timeout. Có thể:

- GET current version.
- So payload/state với intended mutation nếu đủ nhận diện.
- Dùng operation ID/idempotency ledger cho commands cần exactly-once business effect.
- Tách retries cho idempotent queries khỏi writes ambiguous.
- Xem tracing/DB logs được phép.

`GET` read back cũng phải dùng đúng consistency path; một stale secondary read có thể khiến reconciliation sai nếu không hiểu semantics.

## 142. Troubleshooting memory tăng

Một API `/products` bị sửa thành `.findAll()`:

~~~text
RPS modest
heap usage rises
long GC pause
p99 spikes
OOM kill
~~~

Cách xử lý:

- Restore bounded pagination.
- Confirm no unbounded `.into(new ArrayList<>())`.
- Add projections.
- Measure response bytes/GC/cursor.
- Apply max page size and load limits.
- Keep exact query plan in regression test.

Không chỉ tăng heap từ 1 GiB lên 16 GiB rồi tiếp tục full scans.

## 143. Troubleshooting pool wait

Nếu MongoDB command latency thấp nhưng pool checkout wait cao:

- Quá nhiều application requests.
- Pool size quá nhỏ so với latency/concurrency.
- Connections bị giữ bởi slow cursor/transaction.
- Quá nhiều pods và downstream server limit.
- Workload scheduling thiếu admission control.

Điều tra connection checkout duration, server capacity và slow operations. Tăng pool vừa phải có thể giúp khi server còn headroom, nhưng không giải một database CPU đang 100%.

## 144. Troubleshooting index và pagination

Nếu GET list p99 tăng:

- Đọc query plan cho `_id > after`.
- Xem đã có index/field sort đúng chưa.
- Xem page limit có bị bypass không.
- Xem data size và network response.
- Xem cursor/driver batch size.
- Xem cache misses và disk I/O.
- Xem query có filter mới không đi với index.
- Xem sort tie-break và query shape.

**Index thực** phải phục vụ access pattern, không chỉ “đã có một index trên một field nào đó”.

## 145. Troubleshooting input Unicode và SKU

Nếu SKU có chữ thường hoặc ký tự Unicode:

~~~text
POST sku="bàn-phím-01"
```

API lab từ chối vì regex chỉ cho ASCII uppercase. Đây là **quy ước của bài thực hành**, không phải khẳng định MongoDB không lưu được Unicode.

Trong sản phẩm thật, nên phân biệt:

- Immutable internal ID.
- Display name (Unicode).
- Merchant/vendor SKU.
- Search key normalized.
- URL-encoded resource reference.
- Unique scope theo tenant.

Không tự `trim`/uppercase tất cả IDs mà không tính collision/legacy data.

---

## 146. Bài tập A — Missing field

**Đề:** Client tạo product không gửi `stock`. **Hỏi:** giá trị `0` có được ngầm hiểu không?

**Hướng giải:** DTO dùng `Long stock` và `@NotNull` nên HTTP entrypoint trả 400. Nếu contract muốn default 0, phải định nghĩa rõ server default thay vì phụ thuộc Java primitive.

## 147. Bài tập B — Giá âm

**Đề:** `priceCents=-1`. **Hỏi:** lỗi nên bắt ở đâu?

**Hướng giải:** Bean Validation từ request và domain validation cho các entrypoints khác; không gửi tới DB như một Product hợp lệ.

## 148. Bài tập C — SKU lowercase

**Đề:** gửi `"kb-101"` dù API chấp nhận `[A-Z0-9._-]`. **Hỏi:** kết quả?

**Hướng giải:** 400. Không tự chuyển thành `"KB-101"` trừ khi contract canonicalization cho phép và uniqueness/legacy mapping được xử lý.

## 149. Bài tập D — Duplicate key race

**Đề:** hai clients cùng `POST SKU=KB-101` khi chưa tồn tại. **Hỏi:** kiểm `exists()` trong Java đủ chưa?

**Hướng giải:** chưa. Cần atomic insert/unique index, một request thắng và request khác 409; record không bị ghi đè.

## 150. Bài tập E — Update stale

**Đề:** target version=8, client PUT expectedVersion=7. **Hỏi:** có nên ghi đè?

**Hướng giải:** không. Atomic predicate không match; trả 409, giữ state v8.

## 151. Bài tập F — Two writers

**Đề:** cả A và B cùng expectedVersion=3. **Hỏi:** nếu mỗi request dùng atomic CAS trên một document, có thể cả hai cùng thành công?

**Hướng giải:** không trong phạm vi contract; tối đa một chuyển v3→v4, trừ khi có lifecycle/generation đổi cần mô hình riêng.

## 152. Bài tập G — Stock cuối

**Đề:** còn một sản phẩm, hai clients cùng reserve 1. **Hỏi:** bảo đảm gì?

**Hướng giải:** atomic condition `stock >= qty` cùng version guard ngăn oversell, chỉ một success trong kịch bản không có external restock.

## 153. Bài tập H — Insufficient stock

**Đề:** `stock=3`, reserve `quantity=4` với version đúng. **Hỏi:** outcome?

**Hướng giải:** 422 theo API bài này, state không đổi. Không được trừ stock xuống -1.

## 154. Bài tập I — Negative quantity

**Đề:** reserve `quantity=-10`. **Hỏi:** nếu dùng `$inc stock -qty` không validate có chuyện gì?

**Hướng giải:** phép trừ số âm có thể tăng stock trái nghiệp vụ; DTO @Positive và domain guard phải chặn trước DB.

## 155. Bài tập J — Lỗi xóa phiên bản cũ

**Đề:** product v5, request DELETE expectedVersion=4. **Hỏi:** làm gì?

**Hướng giải:** không xóa record; trả 409 sau conditional miss/reread theo policy.

## 156. Bài tập K — Xóa lần hai

**Đề:** DELETE v5 thành công, DELETE lần hai. **Hỏi:** 404 có vi phạm idempotent HTTP method không?

**Hướng giải:** không nhất thiết; effect cuối là resource absent, còn status responses có thể khác. External side effects vẫn cần dedupe nếu có.

## 157. Bài tập L — ABA

**Đề:** product SKU K version1 bị xóa và tạo lại version1; old update expectedVersion1 tới. **Hỏi:** rủi ro?

**Hướng giải:** stale update có thể match lifetime mới. Dùng immutable ID/generation/tombstone hoặc không reuse key.

## 158. Bài tập M — Cursor giới hạn

**Đề:** `/products?limit=1000000`. **Hỏi:** có nên trả 1 triệu items?

**Hướng giải:** không trong API này; reject 400, hoặc clamp nếu contract định nghĩa, và kiểm response bytes/resource budget.

## 159. Bài tập N — `skip` lớn

**Đề:** MongoDB list page 2 triệu bằng `skip(2000000)`. **Hỏi:** vấn đề?

**Hướng giải:** chi phí offset tăng và concurrency visibility không ổn. Keyset trên indexed stable key thường phù hợp forward pagination.

## 160. Bài tập O — New key trước cursor

**Đề:** sau page1 cursor=K100, một key K050 mới được tạo. **Hỏi:** page2 `_id>K100` thấy K050 không?

**Hướng giải:** không. API live pagination không phải snapshot; export/backfill cần snapshot/CDC hoặc contract khác.

## 161. Bài tập P — SKU làm cursor

**Đề:** client sửa `nextCursor` sang SKU khác. **Hỏi:** đó đã là authorization bypass chưa?

**Hướng giải:** chưa chắc ở demo single-tenant, nhưng production cursor có query/tenant binding và mọi request phải authorize. Cursor không được làm token tin cậy tự cấp quyền.

## 162. Bài tập Q — Input limit vs byte limit

**Đề:** list limit=100 nhưng mỗi Product lớn 1 MiB. **Hỏi:** còn rủi ro?

**Hướng giải:** response ~100 MiB, memory/network/timeout lớn. Cần size constraints, projection và max response bytes.

## 163. Bài tập R — Pool size

**Đề:** 20 pods × maxPoolSize 30 connections per server. **Hỏi:** candidate cap đơn giản?

**Hướng giải:** khoảng 600 connections per server theo mô hình, chưa tính monitoring/driver/topology variations.

## 164. Bài tập S — Tạo client mỗi request

**Đề:** controller gọi `MongoClients.create()` cho mỗi GET. **Hỏi:** vấn đề?

**Hướng giải:** tạo pools/connections/threads nhiều lần và dễ leak; inject singleton Spring-managed `MongoTemplate`/MongoClient.

## 165. Bài tập T — Cursor exception

**Đề:** export đọc 1.000 docs rồi throw exception trước khi close cursor. **Hỏi:** pattern an toàn?

**Hướng giải:** `try-with-resources` cho cursor thuộc scope sở hữu, driver client cũng close ở cuối CLI process, không close singleton ở HTTP request.

## 166. Bài tập U — Timeout sau commit

**Đề:** PUT commit v8, response mất, client timeout. **Hỏi:** có thể báo chắc update failed?

**Hướng giải:** không. Cần state/operation reconciliation, tránh retry non-idempotent effects mù quáng.

## 167. Bài tập V — Wrong status

**Đề:** unique-key conflict bị handler trả 503. **Hỏi:** vì sao sai?

**Hướng giải:** duplicate business key không phải backend unavailable; nên trả 409 theo contract để client không retry vô hạn.

## 168. Bài tập W — Retry conflict mãi

**Đề:** client nhận 409 rồi tự retry cùng `expectedVersion` 100 lần.

**Hỏi:** có giúp thành công?

**Hướng giải:** không, nếu current version đã tiến lên. Cần reread/merge hoặc báo conflict, không đốt request budget và capacity.

## 169. Bài tập X — Database unavailable

**Đề:** MongoDB outage khiến server selection timeout. **Hỏi:** API nên trả gì?

**Hướng giải:** 503/5xx hợp contract, có metrics và bounded deadline; không lộ credentials/stack trace, không giả success. Mutation outcome có thể ambiguous nếu request đã tới server trước khi response mất.

## 170. Bài tập Y — Liveness probe khi DB chậm

**Đề:** liveness probe cứ timeout DB một lần là kill pod. **Hỏi:** rủi ro?

**Hướng giải:** restart storm, reconnection surge, không sửa DB outage. Tách readiness/liveness, bounded checks và policies phù hợp.

## 171. Bài tập Z — Rate limit và concurrency

**Đề:** chỉ giới hạn 100 requests/s nhưng mỗi request giữ DB connection 20 giây. **Hỏi:** có thể cạn pool không?

**Hướng giải:** có. Rate limit không thay max in-flight/concurrency, timeout và bounded queue.

## 172. Bài tập AA — Input chuẩn nhưng thiếu quyền

**Đề:** SKU đúng regex nhưng thuộc tenant khác. **Hỏi:** validation đã đủ chưa?

**Hướng giải:** không. Phải lấy trusted tenant identity từ authentication context, query/update/delete có tenant predicate và authorize operation.

## 173. Bài tập AB — Dynamic sort

**Đề:** `/products?sortBy=<arbitrary field>` đưa trực tiếp vào Mongo query. **Hỏi:** vấn đề?

**Hướng giải:** unindexed sort, resource exhaustion và surface cho query misuse. Allowlist sort fields, tạo indexes và max page/bytes.

## 174. Bài tập AC — Failover không có test

**Đề:** integration test với một container MongoDB pass. **Hỏi:** đã chứng minh primary election an toàn?

**Hướng giải:** chưa. Single-node test chủ yếu kiểm API/mapping/atomic operations trong topology đơn. Cần dedicated multi-node fault tests, read/write concern và history recording.

## 175. Bài tập AD — Change Stream consumer

**Đề:** consumer ACK event trước khi write target, rồi process crash. **Hỏi:** hậu quả?

**Hướng giải:** event có thể bị mất khỏi work queue nhưng chưa có target effect. Checkpoint sau durable sink outcome; replay phải idempotent.

## 176. Bài tập AE — Reserve duplicate sau lost ACK

**Đề:** stock=5, reserve 2 đã commit nhưng response mất; client gửi lại với expectedVersion mới từ một GET. **Hỏi:** có thể trừ thêm 2?

**Hướng giải:** có. Version CAS không thay stable business operation ID; nếu client resend với new version, operation mới có thể thành công. Cần idempotency ledger/reconciliation.

## 177. Bài tập AF — Recreate SKU

**Đề:** xóa SKU S version 4, tạo lại S version 1, stale command từ đời cũ expectedVersion 1 tới. **Hỏi:** giải pháp?

**Hướng giải:** immutable entity identity/generation hoặc tombstone version horizon để chặn ABA, không chỉ compare số version trong đời hiện tại.

## 178. Bài tập AG — Lỗi Log secrets

**Đề:** handler trả HTTP 503 kèm nguyên chuỗi MongoDB URI có username/password. **Hỏi:** lỗi?

**Hướng giải:** rò secret. Dùng sanitized ProblemDetail, structured error codes và privileged logs được redact.

## 179. Bài tập AH — TTL authorization

**Đề:** session expiresAt đã qua nhưng MongoDB TTL monitor chưa xóa. **Hỏi:** user có được authorize vì document còn?

**Hướng giải:** không theo expiry policy; validate trusted time ở read/access path. TTL cleanup vật lý có thể bất đồng bộ.

## 180. Bài tập AI — Snapshot vs list

**Đề:** một script dùng GET list với cursor để export toàn bộ collection đang ghi liên tục. **Hỏi:** đã là consistent backup?

**Hướng giải:** chưa. Keyset scan có thể miss/new keys; cần snapshot/CDC boundary, backup API hoặc reconciliation.

## 181. Bài tập AJ — Rủi ro `save`

**Đề:** endpoint Create gọi `mongo.save()` với client-supplied `_id`. **Hỏi:** điều gì có thể xảy ra?

**Hướng giải:** có thể replace/upsert existing document theo semantics, khác expected create-only. Dùng atomic insert và unique constraint hoặc conditional create.

## 182. Bài tập AK — `@Valid` ở HTTP đủ chưa?

**Đề:** Kafka consumer gọi trực tiếp `ProductService.create()` với stock=-1, bypass controller. **Hỏi:** kết luận?

**Hướng giải:** validation ở `@RequestBody` không chạy cho đường này. Dùng validated application boundary/domain types cho mọi entrypoint.

## 183. Bài tập AL — `@Version` và manual version inc

**Đề:** code vừa đặt `@Version` để framework tự quản lý, vừa `$inc("version",1)` tự viết. **Hỏi:** có chắc đúng?

**Hướng giải:** không mặc định. Chọn một optimistic-locking strategy và test mapping/update semantics; không trộn các cơ chế không có hợp đồng rõ.

## 184. Bài tập AM — Product price và currency

**Đề:** `priceCents=100` cho hai currency khác nhau. **Hỏi:** có chắc cùng giá trị kinh tế?

**Hướng giải:** không. Cần currency code và minor-unit/decimal semantics theo đồng tiền, không giả định mọi currency hai chữ số thập phân.

## 185. Bài tập AN — Xóa product nhưng Search vẫn còn

**Đề:** source MongoDB đã hard-delete, read model Search vẫn trả Product. **Hỏi:** CRUD source đã bảo đảm deletion toàn hệ?

**Hướng giải:** chưa. Cần CDC/delete events, tombstone/replay, cache/search invalidation và reconciliation theo data lifecycle.

## 186. Bài tập AO — Update mà `name` trắng

**Đề:** `PUT expectedVersion=2`, `name="   "`. **Hỏi:** error đến từ đâu và version có tăng?

**Hướng giải:** Bean Validation từ chối trước DB, trả 400 và version không thay đổi. Nên có test khẳng định zero DB mutations.

## 187. Bài tập AP — Slow query khiến pool exhaustion

**Đề:** mỗi query mất 10 giây, pool 30 connections, 400 requests đến liên tục. **Hỏi:** tăng pool lên 400 là biện pháp chắc chắn đúng?

**Hướng giải:** không; có thể khiến DB tệ hơn. Tìm query/index bottleneck, request cap, queue/backpressure và sizing theo measured headroom.

## 188. Bài tập AQ — Response JSON quá lớn

**Đề:** 100 records/page, mỗi record 5 MiB, network chậm. **Hỏi:** page limit có đủ?

**Hướng giải:** chưa. Cần byte limits, projection, document sizing, streaming/export riêng và HTTP deadlines.

## 189. Bài tập AR — Đọc từ secondary stale

**Đề:** client update version7→8, GET từ secondary trả v7. **Hỏi:** MongoDB mất update?

**Hướng giải:** không tự kết luận; kiểm read preference/read concern và replication lag. Test must match chosen consistency contract.

## 190. Bài tập AS — Source of truth khi Redis cache lệch

**Đề:** Redis cache stock=5, MongoDB source stock=0; controller cho reserve dựa trên cache. **Hỏi:** an toàn?

**Hướng giải:** không. Atomic authoritative guard phải ở nguồn/transactional protocol, cache stale không được tự quyết business commit.

## 191. Bài tập AT — Debugging bằng `findAll`

**Đề:** developer thêm `/debug/all` trả toàn bộ products, không auth. **Hỏi:** nguy cơ?

**Hướng giải:** full scan/OOM/resource DoS và data leak. Dùng authorized diagnostics, scoped filters, hard limits, audit và dedicated export pipeline.

## 192. Bài tập AU — Dừng process giữa update và HTTP response

**Đề:** MongoDB đã commit nhưng process bị kill trước khi gửi response. **Hỏi:** khi restart server có tự biết response đã mất?

**Hướng giải:** không. Cần idempotency/operation ledger hoặc client reconciliation theo business key để tránh repeated side effects.

## 193. Bài tập AV — Thử lỗi trên production

**Đề:** muốn cắt mạng MongoDB production để kiểm timeout. **Hỏi:** có cần làm ngay?

**Hướng giải:** không nếu không có approval/change control. Bắt đầu ở sandbox/topology đại diện, có kill switch, quan sát và rollback plan; chỉ chaos production theo quy trình được phê duyệt.

---

## 194. Checklist hoàn thành bài thực hành

**Thiết kế contract và dữ liệu**

1. Có mô tả rõ Product fields, business invariants và status codes không?
2. SKU có unique scope và canonical format không?
3. Có tách request DTO, stored document và response DTO không?
4. Có tránh cho client set `version`/audit metadata khi create không?
5. Có dùng `Long` boxed để nhận biết numeric field bị thiếu không?
6. Có xác định price unit/currency không?
7. Có định nghĩa behavior của blank/null/missing fields không?
8. Có giới hạn string/body/document sizes không?
9. Có phân biệt immutable ID với display name không?
10. Có xác định delete/recreate identity lifetime không?

**Validation và bảo mật**

11. `@Valid` được áp tại HTTP input đúng không?
12. Service có bảo vệ các entrypoints khác controller không?
13. Có validate SKU từ path/query không?
14. Có reject quantity/price/stock âm trước DB không?
15. Có giới hạn page limit và sort fields không?
16. Có dùng query builder thay raw user operators không?
17. Có authentication cho production không?
18. Tenant identity có từ trusted principal không?
19. Tất cả queries/mutations có tenant scope khi cần không?
20. Có tránh mass assignment và raw document exposure không?
21. Có dùng least privilege DB account không?
22. Có bảo vệ connection URI/credentials/TLS không?
23. Có tránh logs/metrics chứa secrets hoặc PII không?
24. Có authorization test cho cross-tenant cursor/cache không?

**CRUD và concurrency**

25. Create có atomic unique insert không?
26. Duplicate SKU trả stable 409 contract không?
27. GET dựa trên indexed key không?
28. Update có atomic expectedVersion condition không?
29. Reserve có guard `stock >= quantity` tại DB không?
30. Failed conditional writes không làm state biến đổi không?
31. Hai concurrent reserves không oversell không?
32. Delete có expectedVersion guard không?
33. Stale delete/update có bị reject không?
34. Không dùng read-modify-save vô điều kiện cho critical mutation không?
35. Có phân biệt `@Version` tự động và manual CAS không?
36. Có xử lý `delete→recreate` ABA/generation không?
37. Có xác định HTTP idempotency khác business idempotency không?
38. Có stable operation ID cho side effects critical không?
39. Có reconciled unknown commits khi timeout không?
40. Có plan tombstone/CDC nếu downstream projections cần không?

**Tài nguyên và tải**

41. MongoClient/MongoTemplate có được reuse đúng lifecycle không?
42. Cursor/session tự mở có được close không?
43. Không tạo client per HTTP request không?
44. Có monitor pool checkout/server connections không?
45. Có request deadlines phù hợp client/DB timeout không?
46. Có bounded in-flight concurrency không?
47. Có queue/rate limit phù hợp traffic và tenant không?
48. Có bounded pagination/cursor/export không?
49. Có tránh `findAll`/unbounded collection scans không?
50. Có limit response bytes/document size không?
51. Có dùng index/projection cho query shape không?
52. Có giới hạn retries/backoff/jitter không?
53. Có tránh autoscale làm quá tải DB không?
54. Có separate priority cho background scans không?
55. Có graceful shutdown/readiness/liveness policy không?
56. Có observe p95/p99, CPU/IO, GC, pool wait không?
57. Có instrument conflict/timeout/unknown outcome không?
58. Có runbook ứng phó saturation/cost spike không?

**Kiểm thử và triển khai**

59. Có unit tests cho validation/business rules không?
60. Có MockMvc validation tests không?
61. Có integration tests với MongoDB thực hoặc sandbox tương đương không?
62. Test DB tách biệt production và dữ liệu thật không?
63. Có test duplicate inserts không?
64. Có test stale CAS và cạnh tranh stock cuối không?
65. Có test hard delete và 404 sau delete không?
66. Có test pagination boundaries/deterministic order không?
67. Có test invalid path/JSON body và missing fields không?
68. Có test timeout/lost ACK với outcome ambiguity không?
69. Có test DB unavailable và resource cleanup không?
70. Có test pool saturation/load ở SLO target không?
71. Có test multi-node failover nếu business đòi không?
72. Có test migration backward compatibility không?
73. Có migration plan cho indexes thay vì auto-create tùy tiện không?
74. Có log correlation IDs và sanitized ProblemDetail không?
75. Có CI split fast/integration/fault tests không?
76. Có record driver/engine versions khi failure không?
77. Có monitor deployed resource and version drift không?
78. Có backup/restore drills theo RPO/RTO không?
79. Có review auth/tenant privacy requirements trước production không?
80. Có chỉ triển khai khi correctness/SLO/security gates đạt không?

Đây là checklist **kỹ thuật ứng dụng** để người học tự triển khai, không phải một lượt Content QA cho file Markdown. Việc chạy và đánh giá test suite, nếu có, được thực hiện trong dự án thực hành riêng.

## 195. Mẫu hợp đồng API và resources

~~~yaml
project:
  name: catalog-crud-lab
  language: Java17
  framework: SpringBoot3
  database: MongoDB
  environment: isolatedLab
  productionReady: false

product:
  id:
    field: sku
    pattern: uppercaseAsciiAndDigitsDotsUnderscoreHyphen
    minLength: 2
    maxLength: 40
    uniqueScope: collection
  name:
    required: true
    maxLength: 120
  priceCents:
    type: integer64
    minimum: 0
    currencySemantics: explicitInRealApplication
  stock:
    type: integer64
    minimum: 0
  version:
    initial: 1
    updateRule: atomicIncrement
  timestamps:
    source: serverClockUTC
    notUsedAsConcurrencyVersion: true

api:
  create:
    method: POST
    path: /api/v1/products
    success: 201
    uniqueConstraint: mongodbId
  get:
    method: GET
    path: /api/v1/products/{sku}
    success: 200
  list:
    method: GET
    path: /api/v1/products
    maxPageSize: 100
    sort: skuAscending
    cursor: lastSkuForLab
    snapshotConsistency: notGuaranteed
  update:
    method: PUT
    path: /api/v1/products/{sku}
    fields:
      - name
      - priceCents
    conditional: expectedVersionMustMatch
    conflictStatus: 409
  reserve:
    method: POST
    path: /api/v1/products/{sku}/reservations
    conditions:
      - expectedVersionMustMatch
      - stockAtLeastQuantity
    invariant: stockNeverNegative
    idempotencyLedger: requiredBeforeProduction
  delete:
    method: DELETE
    path: /api/v1/products/{sku}
    conditional: expectedVersionMustMatch
    behavior: hardDeleteForLab
    tombstoneAndGeneration: requiredForReplaySensitiveSystems

validation:
  rejectMissingRequiredFields: true
  rejectNegativePriceAndStock: true
  rejectNegativeOrZeroReserveQuantity: true
  pathSkuValidated: true
  limitBounded: true
  allowArbitraryDatabaseOperators: false
  authenticationAndAuthorization: addBeforeProduction

resources:
  mongoClient:
    lifecycle: springManagedSingleton
    neverCreatePerRequest: true
  cursor:
    ownedByCallerMustBeClosed: true
    useBoundedBatches: true
  connectionPool:
    maxPoolSize: tunedPerPodAndTopology
    poolCheckoutWait: monitored
  deadlines:
    clientAndDatabaseTimeouts: coordinated
    unknownWriteOutcome: reconciled
  concurrency:
    inflightLimit: requiredBeforeHighTraffic
    boundedQueue: requiredBeforeBulkOperations
  backgroundWork:
    rateLimited: true
    separateFromCriticalRequests: recommended
    pauseSwitch: requiredForLongBackfill

errors:
  invalidInput: 400
  notFound: 404
  duplicateKey: 409
  versionConflict: 409
  insufficientStock: 422
  backendUnavailable: 503
  unexpectedError: 500
  response:
    format: ProblemDetail
    code: stable
    credentialsAndInternalStackTrace: prohibited

tests:
  - beanValidation
  - duplicateInsert
  - getAfterCreate
  - staleUpdateRejected
  - twoWritersSameExpectedVersion
  - stockNeverNegative
  - deleteWithFreshVersion
  - keysetPagination
  - invalidPageLimit
  - cursorClosedOnException
  - poolSaturation
  - lostAckAfterCommit
  - databaseUnavailable
  - tenantIsolationAfterSecurityAdded
  - recoveryAndRestore

deploymentGate:
  functionalCrudCorrectness: required
  concurrentSafety: required
  securityAndTenantAuthorization: required
  boundedResources: required
  latencyAndErrorSlo: required
  backupAndRestore: required
~~~

Mẫu YAML trên là **tài liệu mô tả hợp đồng**, không phải file cấu hình chạy trực tiếp cho Spring Boot, MongoDB, Docker hoặc Maven. Người học phải triển khai và kiểm thử từng yêu cầu trong môi trường cụ thể.

## 196. Runbook khi API CRUD gây quá tải database

~~~text
TRIGGER
  HTTP p99 rises, Mongo pool waits grow,
  command timeout or DB CPU/IO saturation increases.

CONTAIN
  1. Restrict noncritical scans, exports and bulk jobs.
  2. Enforce bounded page sizes and query allowlists.
  3. Throttle retries and clients within business policy.
  4. Preserve critical writes, data integrity and logs.

DIAGNOSE
  5. Check connection pool checkout and active operations.
  6. Identify slow query shapes and missing indexes.
  7. Measure database CPU/IO/cache/replication lag.
  8. Check recent deploy and traffic changes.
  9. Inspect request size, concurrency and GC pauses.

RECOVER
 10. Fix query/index/config or reduce load safely.
 11. Reconcile writes with unknown outcomes.
 12. Confirm no stale overwrite, oversell or data loss.
 13. Observe p95/p99, successful throughput and retries.
 14. Restore background traffic progressively.

PREVENT
 15. Add regression tests and capacity guardrails.
 16. Document the maximum supported load, failover behavior
     and next review threshold.
~~~

Không coi việc tăng connection pool từ 30 lên 3.000 là mặc định đúng: khi database bị bão hòa, nhiều requests song song hơn có thể làm tình hình tệ hơn.

## 197. Runbook khi dữ liệu CRUD bị sai

~~~text
TRIGGER
  Duplicate identity, stale overwrite, negative stock,
  cross-tenant exposure or missing record after mutation.

CONTAIN
  Pause affected write path or cutover; preserve logs.
  Protect business operations from new side effects.
  Do not silently rewrite authoritative records.

INVESTIGATE
  Identify source of truth, key, generation and version.
  Compare request ID/expectedVersion with committed state.
  Check conditional mutation and unique constraints.
  Check timeout/retry/idempotency ledger and driver behavior.
  Check query tenant predicates and authorization.
  Check CDC/search/cache if projections are involved.

REPAIR
  Reconcile from authoritative history/ledger.
  Apply version-aware, approved corrections.
  Rebuild projections and validate deleted records.
  Confirm invariants and privacy constraints.

PREVENT
  Reproduce minimal failing history.
  Add deterministic regression and concurrent/fault tests.
  Review schema, index, query and resource settings.
~~~

Khi là sự cố dữ liệu thật, giữ evidence và theo incident response policy; không tự thử repair bằng random `updateMany` trên production.

## 198. Kết luận

Một luồng CRUD Java–NoSQL không chỉ là **bốn HTTP methods và vài lệnh database**. Nó là hợp đồng xuyên suốt từ input cho tới dữ liệu bền vững và tài nguyên vận hành.

Các ý chính:

- **DTO + Bean Validation** bảo vệ shape/type/range của input, nhưng không thay business validation hay authorization.
- **Unique `_id` và atomic insert** bảo vệ create dưới concurrent requests.
- **ExpectedVersion + atomic conditional update** chặn stale overwrites giữa nhiều Java pods.
- **Atomic `stock >= quantity`** bảo vệ tồn kho thay vì kiểm trong Java rồi save.
- **Delete có version guard** tránh xóa nhầm trạng thái đã đổi, nhưng production có thể cần tombstone/generation.
- **Keyset pagination có limit** bảo vệ API khỏi unbounded collection reads; nó không tự là consistent snapshot.
- **MongoClient pooling và cursor/session lifecycle** quan trọng không kém query correctness để tránh cạn resources.
- **Timeout không chứng minh mutation chưa commit**; business operations cần idempotency/reconciliation khi có side effects.
- **ProblemDetail/sanitized errors** giúp clients hiểu kết quả mà không lộ nội bộ.
- **Integration + concurrency + resource/fault tests** bổ sung cho unit tests và giúp kiểm các invariant quan trọng.
- **Auth/tenant isolation, RPO/RTO, observability và rollout gates** là phần bắt buộc trước khi đem mẫu học tập lên production.

> **CRUD đúng là CRUD có ràng buộc:** đầu vào được kiểm, business invariant được bảo vệ tại điểm ghi, tài nguyên được giới hạn và dọn dẹp, thất bại được biểu diễn trung thực, và mọi lời hứa về consistency đều có phạm vi cụ thể.

Khi hoàn thành lab, người học nên thử tự giải thích một request `reserve(KB-101, quantity=1, expectedVersion=7)` từ khi đi qua HTTP cho tới MongoDB atomic update, rồi trả lời: **ai xác thực request, trường nào được validate, điều kiện nào chặn oversell, lỗi nào trả về khi version thay đổi, pool connection được quản lý ở đâu, và client làm gì nếu response bị mất sau commit?** Nếu giải thích được toàn bộ hành trình đó bằng code và test, nền tảng xây dựng luồng CRUD NoSQL từ Java đã vững chắc.
