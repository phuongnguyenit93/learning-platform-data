# Không để SQL hoặc chi tiết trình điều khiển lan tới tầng giao diện

## 1. Mục tiêu bài học

Trong ứng dụng Spring, tầng giao diện (presentation layer) có thể là REST controller phục vụ web/mobile, server-rendered view hoặc adapter GraphQL. Tầng này cần biết **người dùng yêu cầu gì, dữ liệu nào được phép nhận và mã lỗi nghiệp vụ nào cần hiển thị**. Nó không cần biết câu SQL, tên bảng/cột, kiểu `ResultSet`, `SQLException`, JDBC URL hay driver PostgreSQL/MySQL.

Sau bài học, bạn có thể:

- Nhận biết các dạng rò rỉ chi tiết lưu trữ từ controller, response JSON, exception, log và API contract.
- Phân chia rõ trách nhiệm giữa controller, application service, repository/DAO, DB và driver; chọn đúng kiểu dữ liệu đi qua từng ranh giới.
- Viết ví dụ Spring Boot dùng `JdbcTemplate` mà SQL vẫn nằm trong adapter dữ liệu, còn controller chỉ giao tiếp với service và DTO.
- Chuyển lỗi cơ sở dữ liệu thành kết quả nghiệp vụ và phản hồi HTTP ổn định, không trả SQL, mã lỗi nhà cung cấp, stack trace hoặc cấu hình kết nối cho client.
- Kiểm thử ranh giới để sau này thay JDBC bằng JPA hay thay DBMS mà hợp đồng với giao diện không phải đổi vì chi tiết lưu trữ.

**Nguyên tắc cốt lõi:** tầng giao diện phụ thuộc vào **hợp đồng ứng dụng** (use case, DTO, mã lỗi công khai), còn câu truy vấn và driver nằm tại **hạ tầng truy cập dữ liệu**.

## 2. Vì sao cần một ranh giới rõ ràng?

Hãy hình dung UI gọi `POST /api/products` để tạo sản phẩm. Nếu controller tự thực hiện SQL rồi trả nguyên `SQLException.getMessage()`, trình duyệt có thể nhìn thấy tên bảng `products`, tên constraint, địa chỉ DB, chuỗi SQL, thông tin vận hành và cấu trúc kỹ thuật. Ngay cả khi thông tin ấy chưa chứa bí mật, UI sẽ bị ràng buộc với một cách lưu trữ cụ thể, khiến thay đổi schema dễ phá vỡ API.

Các vấn đề thường xuất hiện cùng lúc:

1. **Coupling:** controller đổi theo bảng/cột hoặc công nghệ DB; khó thay `JdbcTemplate` bằng JPA/R2DBC.
2. **Khó kiểm thử:** muốn thử một quy tắc HTTP đơn giản lại cần khởi động DB, cấu hình driver và dữ liệu mẫu.
3. **Lỗi và bảo mật:** SQL/stack trace/driver exception có thể bị serialize ra client; câu SQL ghép chuỗi dễ bị SQL injection.
4. **Thiếu quy tắc nghiệp vụ:** controller trực tiếp thao tác DB dễ bỏ qua transaction, phân quyền, chuẩn hóa dữ liệu hoặc chính sách đổi trạng thái do service quản lý.
5. **Khó duy trì hợp đồng:** đổi `ResultSet`, entity, tên cột hoặc thông điệp lỗi của driver có thể làm UI hỏng dù hành vi nghiệp vụ không đổi.

Ranh giới tốt tạo khả năng thay đổi và cô lập sự cố. Nó **không** có nghĩa phải thêm nhiều interface cho mọi lớp hay viết một framework riêng: với ứng dụng nhỏ, một repository rõ nhiệm vụ và một service có use case cụ thể thường đã đủ.

## 3. Luồng phụ thuộc và dữ liệu mong muốn

```text
Browser / Mobile / Frontend
    |
    | HTTP + JSON: CreateProductRequest, ProductResponse, mã lỗi ổn định
    v
ProductController                     [Presentation]
    |
    | Gọi createProduct(...), getProduct(...)
    v
CatalogService                        [Application / use case]
    |
    | ProductStore + kiểu dữ liệu miền ứng dụng
    v
ProductStore (interface)              [Cổng truy cập dữ liệu]
    ^
    | implements
    |
JdbcProductStore                      [Infrastructure]
    |
    | JdbcTemplate -> DataSource -> JDBC driver -> SQL
    v
PostgreSQL
```

Dữ liệu và ngoại lệ được phép đi qua từng ranh giới:

| Ranh giới | Nên đi qua | Không nên đi qua |
| --- | --- | --- |
| Frontend ↔ Controller | JSON DTO, HTTP status, mã lỗi ổn định, request ID | SQL, `SQLException`, JDBC URL, tên constraint, driver stack trace |
| Controller ↔ Service | Đầu vào use case, domain/application result, lỗi nghiệp vụ | `ResultSet`, `Connection`, `EntityManager`, câu lệnh SQL |
| Service ↔ Repository port | Phương thức như `create`, `findById`; domain object | Câu SQL động từ UI, vendor exception |
| Repository adapter ↔ DB | SQL, bind parameter, mapping rows, transaction resource | Hợp đồng hiển thị và câu chữ giao diện |

**Chiều phụ thuộc quan trọng:** controller gọi service; service dùng một interface mô tả khả năng lưu/truy xuất theo nhu cầu ứng dụng; adapter JDBC triển khai interface đó. Service không cần import `org.postgresql.*`, `java.sql.ResultSet`, `JdbcTemplate` hay `SQLException`. Spring có thể tiêm adapter phù hợp bằng dependency injection.

Một DTO chỉ tình cờ trùng tên field với cột DB vẫn là **DTO công khai có chủ đích** nếu ta kiểm soát nó. Ngược lại, trả thẳng `Map<String, Object>` từ `queryForList` khiến tên cột, kiểu JDBC và schema trở thành hợp đồng ngầm với client.

## 4. Dấu hiệu sai: SQL và lỗi driver ở controller

Đoạn sau là **anti-pattern để phân tích, không dùng trong ứng dụng thực tế**:

```java
// Đoạn minh họa sai: KHÔNG đưa vào hệ thống thật.
@GetMapping("/api/products")
public Object products(@RequestParam String sku) {
    try {
        String sql =
            "SELECT * FROM products WHERE sku = '" + sku + "'";
        return jdbcTemplate.queryForList(sql);
    } catch (Exception ex) {
        return ex.getMessage();
    }
}
```

Có ít nhất năm lỗi:

- Controller tự viết SQL và phụ thuộc `JdbcTemplate`, vi phạm ranh giới trách nhiệm.
- Ghép `sku` trực tiếp vào SQL gây SQL injection; dấu nháy trong dữ liệu cũng có thể phá cú pháp.
- `SELECT *` cộng `Map` trả trực tiếp có thể lộ cột nội bộ như `cost_price`, `deleted_at` hoặc trường vừa được thêm vào schema.
- Trả `ex.getMessage()` biến thông điệp nhà cung cấp DB thành dữ liệu công khai, có thể chứa SQL, tên bảng/cột, constraint hoặc chi tiết kết nối.
- Trả chuỗi lỗi như response bình thường thường làm hỏng HTTP semantics: client có thể nhận `200 OK` dù truy vấn thất bại.

Việc chuyển SQL sang một phương thức private trong chính controller **chưa** giải quyết ranh giới: controller vẫn biết cú pháp truy vấn, ràng buộc DB và cách xử lý lỗi dữ liệu. Tương tự, chỉ đổi `JdbcTemplate` sang gọi trực tiếp `JpaRepository` từ controller vẫn khiến giao diện gắn với persistence API và có thể bỏ qua use case.

## 5. Thiết kế hợp đồng ứng dụng trước khi chọn SQL

Ví dụ API quản lý sản phẩm:

- `POST /api/products` nhận `sku`, `name`, `price`; trả `201 Created` với DTO sản phẩm khi thành công.
- `GET /api/products/{id}` trả sản phẩm hoặc `404 Not Found` nếu không có.
- `sku` là duy nhất theo quy tắc nghiệp vụ; tạo trùng trả `409 Conflict` cùng `code = SKU_ALREADY_USED`.
- Dữ liệu request không hợp lệ trả `400 Bad Request` cùng `code = INVALID_INPUT`.
- Sự cố truy cập DB không dự đoán trước trả `500` với thông điệp trung tính; chi tiết chỉ được ghi trong hệ thống quan sát nội bộ.

UI có thể dựa vào những trạng thái và mã lỗi này, **không** phụ thuộc `SQLSTATE 23505`, `PSQLException`, `DuplicateKeyException` hoặc tên `uq_products_sku`.

Ví dụ JSON thành công (ID là ví dụ, không nên hard-code trong ứng dụng):

```json
{
  "id": 17,
  "sku": "BK-001",
  "name": "Sách Spring",
  "price": 129000.00
}
```

Ví dụ phản hồi trùng SKU theo dạng `ProblemDetail` (RFC 9457; server có thể bổ sung `instance`):

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Mã sản phẩm đã được sử dụng.",
  "code": "SKU_ALREADY_USED"
}
```

Một thông báo dùng được cho UI phải ổn định và phù hợp nghiệp vụ. Không phải mọi `DataIntegrityViolationException` đều có nghĩa “SKU đã tồn tại”: có thể đó là FK, NOT NULL, CHECK hoặc sai schema. Chỉ dịch một vi phạm sang lỗi cụ thể khi đã nhận diện được đúng bất biến.

## 6. Ví dụ triển khai Spring Boot 3.x + Java 17+ + PostgreSQL

Đây là ví dụ ứng dụng nhỏ nhưng đủ các ranh giới chính. Các tệp Java bên dưới cùng package `demo.catalog`; dự án cần Spring Boot 3.x, Spring Web MVC, Spring JDBC, Bean Validation, PostgreSQL driver và `DataSource` cấu hình. Ví dụ SQL sử dụng `INSERT ... ON CONFLICT ... RETURNING` **riêng của PostgreSQL**; vì cú pháp này chỉ nằm trong `JdbcProductStore`, việc đổi DBMS không bắt frontend đổi contract.

### 6.1. Phụ thuộc build và lược đồ

Bổ sung các phụ thuộc trong `dependencies { ... }` của một dự án Gradle Spring Boot đã được cấu hình plugin và Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Tạo `src/main/resources/db/migration/V1__create_products.sql`:

```sql
CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price CHECK (price >= 0)
);
```

`UNIQUE (sku)` ở database là điểm quyết định duy nhất ngay cả khi hai request tạo cùng SKU đồng thời. Validation ở HTTP làm thông báo dễ hiểu hơn, nhưng không thể đảm bảo uniqueness khi có race condition. Để giữ ví dụ tập trung, chính sách chuẩn hóa SKU (hoa/thường, khoảng trắng, Unicode) cần được quyết định nhất quán ở use case và DB nếu nghiệp vụ yêu cầu.

Cấu hình kết nối thuộc môi trường server, chẳng hạn biến `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME` và `SPRING_DATASOURCE_PASSWORD` được cấp cho ứng dụng. Không đưa mật khẩu, JDBC URL nội bộ hay tên driver vào JavaScript chạy trên trình duyệt hoặc JSON của API. Flyway thực thi migration khi ứng dụng khởi động nếu đã được cấu hình phù hợp.

### 6.2. Domain object không phụ thuộc JDBC/JPA

`src/main/java/demo/catalog/Product.java`:

```java
package demo.catalog;

import java.math.BigDecimal;

public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price
) {}
```

Đây là một kiểu Java đơn giản, không có `@Entity`, `ResultSet` hay `Connection`. Nó đại diện thông tin ứng dụng cần dùng trong use case. Trong hệ thống lớn hơn, domain model có thể chứa nhiều bất biến/hành vi hơn một `record`; chọn kiểu phù hợp với độ phức tạp thật.

### 6.3. Port định nghĩa năng lực lưu trữ

`src/main/java/demo/catalog/ProductStore.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.Optional;

public interface ProductStore {
    Product insert(String sku, String name, BigDecimal price);

    Optional<Product> findById(long id);
}
```

Service chỉ yêu cầu “tạo sản phẩm” và “tìm sản phẩm”. Interface không yêu cầu bên gọi biết cách tạo kết nối, cách map row hay dialect của câu truy vấn. Một adapter khác có thể dùng JPA hoặc một hệ thống lưu trữ thay thế miễn đáp ứng cùng ngữ nghĩa.

### 6.4. Ngoại lệ nghiệp vụ độc lập DB

`src/main/java/demo/catalog/CatalogErrors.java`:

```java
package demo.catalog;

public final class CatalogErrors {
    private CatalogErrors() {}

    public static final class SkuAlreadyUsed extends RuntimeException {}

    public static final class ProductMissing extends RuntimeException {}
}
```

Hai loại lỗi này diễn tả **điều ứng dụng muốn công bố**, không mang theo `SQLException` hoặc mã vendor. Tên class có thể đổi theo chuẩn dự án; phần client nhìn thấy là HTTP status và trường `code` do tầng web định nghĩa.

### 6.5. JDBC adapter sở hữu toàn bộ SQL

`src/main/java/demo/catalog/JdbcProductStore.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcProductStore implements ProductStore {

    private static final RowMapper<Product> PRODUCT_MAPPER =
            (rs, rowNumber) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("name"),
                    rs.getBigDecimal("price")
            );

    private final JdbcTemplate jdbc;

    public JdbcProductStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Product insert(String sku, String name, BigDecimal price) {
        List<Product> inserted = jdbc.query(
                """
                INSERT INTO products (sku, name, price)
                VALUES (?, ?, ?)
                ON CONFLICT (sku) DO NOTHING
                RETURNING id, sku, name, price
                """,
                PRODUCT_MAPPER,
                sku,
                name,
                price
        );

        return inserted.stream()
                .findFirst()
                .orElseThrow(CatalogErrors.SkuAlreadyUsed::new);
    }

    @Override
    public Optional<Product> findById(long id) {
        List<Product> products = jdbc.query(
                """
                SELECT id, sku, name, price
                FROM products
                WHERE id = ?
                """,
                PRODUCT_MAPPER,
                id
        );
        return products.stream().findFirst();
    }
}
```

**Cơ chế quan trọng:**

1. `JdbcTemplate` và `RowMapper` chỉ xuất hiện trong adapter. JDBC driver thực thi SQL và giao tiếp với PostgreSQL, nhưng controller và service không thấy các kiểu JDBC.
2. `?` kèm bind parameters bảo vệ dữ liệu đầu vào khỏi việc bị ghép như cú pháp SQL. Không nối `sku` trực tiếp vào `WHERE` hay `INSERT`.
3. `ON CONFLICT (sku) DO NOTHING` chỉ xử lý xung đột trên khóa duy nhất `sku`. `RETURNING` trả hàng vừa tạo; nếu xung đột SKU, kết quả rỗng và adapter ném `SkuAlreadyUsed`. Đây là quyết định nghiệp vụ có căn cứ, tránh gọi mọi lỗi UNIQUE thành trùng SKU.
4. Nếu có lỗi DB khác (hết kết nối, schema sai, lỗi CHECK chưa được validate...), `JdbcTemplate` chuyển lỗi JDBC sang hệ `DataAccessException` của Spring theo khả năng của translator. Những lỗi hạ tầng bất ngờ không bị gán sai thành `SkuAlreadyUsed`.
5. Khi chuyển PostgreSQL sang DBMS khác, thay câu SQL và cách nhận generated key **tại adapter**. Không đổi `ProductStore`, use case hoặc hợp đồng JSON nếu nghiệp vụ giữ nguyên.

`@Repository` làm bean được Spring quản lý và hỗ trợ hệ cơ chế exception translation cho DAO thích hợp; riêng `JdbcTemplate` đã tích hợp dịch `SQLException` sang `DataAccessException`. Không cần tự `catch (SQLException)` rồi trả chuỗi lỗi.

### 6.6. Service giữ use case và transaction

`src/main/java/demo/catalog/CatalogService.java`:

```java
package demo.catalog;

import java.math.BigDecimal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {

    private final ProductStore store;

    public CatalogService(ProductStore store) {
        this.store = store;
    }

    @Transactional
    public Product create(String sku, String name, BigDecimal price) {
        return store.insert(sku, name, price);
    }

    @Transactional(readOnly = true)
    public Product get(long id) {
        return store.findById(id)
                .orElseThrow(CatalogErrors.ProductMissing::new);
    }
}
```

Service phụ thuộc `ProductStore`, không chứa SQL. Nó là chỗ thích hợp để điều phối nhiều thao tác repository, phân quyền, chính sách nghiệp vụ và transaction. Khi exception unchecked thoát khỏi một phương thức `@Transactional` được gọi qua proxy Spring theo cấu hình thông thường, transaction mặc định rollback. Tránh giả định tự gọi `this.create(...)` trong chính bean luôn đi qua proxy. Chỉ thêm transaction khi có ý nghĩa nhất quán; trong ví dụ này nó minh họa vị trí đặt transaction khi use case sau này bổ sung nhiều thao tác.

Nếu service cần tạo sản phẩm và bản ghi audit trong một transaction, cả hai được commit/rollback cùng nhau. Controller chỉ nhận kết quả cuối cùng và không phải biết commit, connection hoặc isolation level.

### 6.7. Controller làm việc với DTO và HTTP

`src/main/java/demo/catalog/CatalogController.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    public record CreateProductRequest(
            @NotBlank @Size(max = 64) String sku,
            @NotBlank @Size(max = 200) String name,
            @NotNull @DecimalMin("0.00")
                @Digits(integer = 10, fraction = 2) BigDecimal price
    ) {}

    public record ProductResponse(
            long id, String sku, String name, BigDecimal price
    ) {
        public static ProductResponse from(Product product) {
            return new ProductResponse(
                    product.id(),
                    product.sku(),
                    product.name(),
                    product.price()
            );
        }
    }

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request
    ) {
        Product product = service.create(
                request.sku(),
                request.name(),
                request.price()
        );
        URI location = URI.create("/api/products/" + product.id());
        return ResponseEntity.created(location)
                .body(ProductResponse.from(product));
    }

    @GetMapping("/{id}")
    public ProductResponse get(@PathVariable long id) {
        return ProductResponse.from(service.get(id));
    }
}
```

Controller import các kiểu HTTP/validation và service; **không import JDBC, JPA, driver, `DataSource` hay `java.sql`**. `CreateProductRequest` có constraint để trả lỗi sớm; DB vẫn có `NOT NULL`, `UNIQUE` và `CHECK` để bảo vệ nhất quán từ mọi nguồn ghi. `ProductResponse` được tạo chủ động, nên thêm một cột nhạy cảm vào bảng sẽ không tự làm cột đó xuất hiện trong JSON.

Tránh trả trực tiếp JPA `@Entity` từ controller: entity có thể chứa trường nội bộ, liên kết lazy, proxy, vòng lặp quan hệ hoặc thông tin không nằm trong API contract. Dùng DTO/projection phù hợp để kiểm soát dữ liệu công khai.

### 6.8. Chuyển lỗi thành ProblemDetail an toàn

`src/main/java/demo/catalog/ApiErrorHandler.java`:

```java
package demo.catalog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiErrorHandler.class);

    @ExceptionHandler(CatalogErrors.SkuAlreadyUsed.class)
    public ResponseEntity<ProblemDetail> duplicateSku() {
        return issue(
                HttpStatus.CONFLICT,
                "SKU_ALREADY_USED",
                "Mã sản phẩm đã được sử dụng."
        );
    }

    @ExceptionHandler(CatalogErrors.ProductMissing.class)
    public ResponseEntity<ProblemDetail> missingProduct() {
        return issue(
                HttpStatus.NOT_FOUND,
                "PRODUCT_NOT_FOUND",
                "Không tìm thấy sản phẩm."
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidInput() {
        return issue(
                HttpStatus.BAD_REQUEST,
                "INVALID_INPUT",
                "Dữ liệu yêu cầu không hợp lệ."
        );
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<ProblemDetail> unexpectedStorage(
            DataAccessException failure
    ) {
        log.error("Unexpected persistence failure", failure);
        return issue(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "UNEXPECTED_STORAGE_ERROR",
                "Không thể xử lý yêu cầu lúc này."
        );
    }

    private static ResponseEntity<ProblemDetail> issue(
            HttpStatus status, String code, String message
    ) {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(status, message);
        problem.setTitle(status.getReasonPhrase());
        problem.setProperty("code", code);
        return ResponseEntity.status(status).body(problem);
    }
}
```

Tầng HTTP biết lỗi `SkuAlreadyUsed`, `ProductMissing` và validation; nó không cần truy ngược `PSQLException`, `SQLState` hay chuỗi lỗi driver để chọn status. Handler cho `DataAccessException` chỉ là lưới an toàn với thông điệp trung tính. Log chi tiết ở server cần kiểm soát quyền truy cập, che dữ liệu nhạy cảm và gắn correlation/request ID trong hệ quan sát; đừng tự động đưa stack trace hoặc SQL thô lên client telemetry.

**Lưu ý phạm vi ví dụ:** handler xử lý các lỗi đã liệt kê; hệ thống thật cũng cần quy tắc chung an toàn cho những lỗi không mong đợi khác và cách xử lý lỗi chuẩn của Spring MVC, theo chính sách API của dự án. Không nên `catch (Exception)` rồi luôn trả `200` hoặc biến mọi lỗi thành `409`.

### 6.9. Entry point Spring Boot

`src/main/java/demo/catalog/CatalogApplication.java`:

```java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Đây là mã Spring Boot cần các thư viện và DB tương ứng; không chạy độc lập chỉ bằng `javac CatalogApplication.java`. Trong dự án Gradle đã cấu hình plugin Spring Boot, cung cấp PostgreSQL và các biến `SPRING_DATASOURCE_*` cho tiến trình ứng dụng rồi chạy:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Nếu chạy lần đầu trên database trống và Flyway hoạt động, migration tạo bảng trước khi controller nhận request. Các endpoint có thể được gọi bằng HTTP client hoặc `curl`, ví dụ:

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BK-001","name":"Sách Spring","price":129000.00}'

curl -i http://localhost:8080/api/products/1
```

Câu GET với ID `1` chỉ trả thành công nếu bản ghi đó thực sự tồn tại; không suy đoán ID từ ví dụ. POST thành công nhận `201`, `Location` trỏ đến URI sản phẩm và body là `ProductResponse`. Gửi lại cùng SKU sẽ nhận `409` và mã `SKU_ALREADY_USED`, không có SQL trong body.

## 7. Phân biệt lỗi kỹ thuật và lỗi nghiệp vụ

| Sự kiện | Xử lý trong hạ tầng/service | Phản hồi giao diện |
| --- | --- | --- |
| SKU đã tồn tại | PostgreSQL `ON CONFLICT (sku)` hoặc nhận diện đúng unique constraint; chuyển sang `SkuAlreadyUsed` | `409`, `SKU_ALREADY_USED` |
| Không có ID được hỏi | Repository trả `Optional.empty()`; service chuyển `ProductMissing` | `404`, `PRODUCT_NOT_FOUND` |
| Input thiếu/price âm | DTO validation và constraint DB | `400`, `INVALID_INPUT` |
| Mất kết nối DB, SQL sai, lỗi resource | `DataAccessException`; ghi log/metric nội bộ | `500` hoặc `503` tùy chính sách; mã lỗi tổng quát |
| Deadlock/serialization conflict | Chính sách retry có giới hạn và idempotency tại đúng tầng | Lỗi có ý nghĩa ổn định, không lộ SQLSTATE |
| Lỗi nghiệp vụ khác, chẳng hạn chưa được phép thao tác | Service/policy xác định; không bắt nguồn từ tên bảng | `403`/`409` tùy hợp đồng API |

`DataAccessException` là họ ngoại lệ Spring giúp ứng dụng bớt lệ thuộc vendor. Nó **vẫn** là khái niệm tầng dữ liệu; tránh để controller phân tích sâu `SQLException` hoặc dựa vào `getMessage()`. Nếu dự án lớn muốn presentation hoàn toàn không phụ thuộc cả `DataAccessException`, có thể chuyển lỗi hạ tầng không mong đợi thành một exception ứng dụng tổng quát tại adapter/service và xử lý tập trung ở web. Làm sao cũng phải giữ lại nguyên nhân trong log và bảo đảm transaction rollback.

**Không che giấu mọi lỗi bằng một thông điệp duy nhất trong log:** client thấy thông điệp trung tính, còn người vận hành vẫn cần biết lỗi DB nào xảy ra, request nào liên quan, thời điểm, exception chain, tên constraint và đường truy vấn an toàn để xử lý sự cố. Không ghi mật khẩu hoặc bind parameters chứa dữ liệu nhạy cảm vào log không kiểm soát.

## 8. Transaction không phải trách nhiệm của giao diện

Controller không nên:

- Tự gọi `connection.setAutoCommit(false)`, `commit()` hoặc `rollback()`.
- Mở một `Connection` rồi truyền qua DTO/service hoặc giữ connection trong phiên trình duyệt.
- Tự “thử lại” một câu SQL có side effect chỉ vì nhận thông báo lỗi từ driver.
- Bắt ngoại lệ persistence rồi chuyển thành chuỗi trả về, khiến lỗi bị coi là thành công.

Một use case ghi nhiều bảng phải đặt transaction ở service hoặc một ranh giới ứng dụng tương đương. Khi service dùng repository JDBC qua `JdbcTemplate` và transaction manager cấu hình đúng, các thao tác có thể tham gia cùng transaction. Exception unchecked thoát khỏi proxy `@Transactional` thường kích hoạt rollback theo mặc định. Nếu service bắt lỗi rồi tự trả thành công, cần xem lại rollback: có thể dữ liệu dở dang được commit hoặc transaction PostgreSQL đã ở trạng thái failed.

Với thao tác retry, quyết định dựa trên ý nghĩa nghiệp vụ (idempotency key, optimistic lock, retryable conflict, số lần thử tối đa) tại service/infrastructure, không để frontend tự suy đoán từ lỗi `SQLSTATE 40001` hoặc mã vendor. Frontend có thể thử lại request **theo hợp đồng công khai** khi server tuyên bố retry an toàn.

## 9. Nếu dùng Spring Data JPA thì nguyên tắc có đổi không?

Không. Thay `JdbcProductStore` bằng một adapter JPA:

```text
CatalogController -> CatalogService -> ProductStore
                                         ^
                                         |
                                   JpaProductStore
                                         |
                              EntityManager/JpaRepository
                                         |
                                      Database
```

`@Entity`, `EntityManager`, `JpaRepository`, JPQL, Criteria API, `Pageable` thuộc cách cài đặt truy cập dữ liệu và có thể xuất hiện trong adapter. Service không nên buộc controller dùng `EntityManager` hoặc trả `Page<Entity>` như hợp đồng API mặc định chỉ vì repository tiện trả như vậy. Tạo DTO trang có các trường công khai ổn định (`items`, `page`, `size`, `total` khi thật sự cần) và kiểm soát sort/filter mà client được phép yêu cầu.

Spring có cơ chế dịch nhiều lỗi JDBC/JPA sang các loại `DataAccessException`; tính chính xác phụ thuộc đường gọi, provider và cấu hình. Với JPA, câu SQL có thể chỉ thực thi lúc `flush` hoặc `commit`; đừng giả định lỗi UNIQUE luôn ném ngay tại `save`. Thiết kế ranh giới xử lý lỗi và transaction phù hợp thời điểm thực tế, kiểm thử bằng DBMS dùng ở production.

Dùng Spring Data projection chỉ gồm trường được phép hiển thị có thể rất hiệu quả. Tuy nhiên projection/entity hạ tầng không nên âm thầm thay thế hợp đồng public DTO nếu sự thay đổi persistence có khả năng phá API.

## 10. Filtering, sorting và phân trang mà không cho UI gửi SQL

Một dạng rò rỉ tinh vi hơn là endpoint nhận tham số `sql`, `where`, `tableName`, `orderByClause` rồi ghép vào câu SQL. Đây vừa là coupling vừa có nguy cơ injection, vì placeholder `?` chỉ bind **giá trị dữ liệu**, không bind tên bảng, cột hay từ khóa SQL.

Thay vì nhận `sort=price DESC; DROP TABLE products`, định nghĩa tập giá trị công khai cố định:

```text
GET /api/products?sort=price_asc&page=0&size=20
GET /api/products?sort=name_asc&page=1&size=20
```

Controller validate `sort` thuộc `price_asc` hoặc `name_asc`, kiểm soát `size` tối đa; service chuyển thành lựa chọn nghiệp vụ; repository map sang SQL cột thực:

```java
// Minh họa phần logic đặt trong repository, không phải class hoàn chỉnh.
String orderBy = switch (publicSort) {
    case "price_asc" -> "price ASC, id ASC";
    case "name_asc"  -> "name ASC, id ASC";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String sql =
        "SELECT id, sku, name, price FROM products ORDER BY "
        + orderBy + " LIMIT ? OFFSET ?";
```

Trong đoạn này, `orderBy` đến từ **whitelist cố định do server định nghĩa**, không phải nối trực tiếp chuỗi raw từ client. `LIMIT` và `OFFSET` vẫn bind qua `?` (và nên giới hạn để tránh overflow/scan quá lớn). Mẫu SQL cụ thể được giữ trong repository; dùng sort tie-breaker `id` giúp thứ tự phân trang ổn định trong một snapshot, dù phân trang offset vẫn có thể thay đổi khi dữ liệu ghi đồng thời.

Với lỗi SQL, trả về `400` cho giá trị `sort` không được hỗ trợ theo hợp đồng HTTP; không phản hồi “column price does not exist” hoặc cấu trúc `ORDER BY` của DB.

## 11. Ranh giới dữ liệu nhạy cảm

Việc không lộ SQL là một phần của thiết kế API an toàn. Kiểm soát thêm:

- **Response DTO whitelist:** chỉ trả trường mà người gọi được phép xem. Một entity có `password_hash`, `internal_note` hoặc `purchase_cost` không nên được serialize trực tiếp.
- **Phân quyền ở use case/query:** controller/service xác thực quyền của người gọi; repository truy xuất theo phạm vi tenant/owner hợp lệ. Chỉ giấu cột khỏi JSON không ngăn rò dữ liệu qua endpoint khác.
- **Connection settings:** JDBC URL, username/password, hostname nội bộ và thông tin pool ở cấu hình phía server/secrets manager, không đưa vào frontend bundle hay response.
- **Exception và tracing:** thông điệp public không chứa SQL, bảng, driver, stack trace, địa chỉ DB; log/tracing nội bộ vẫn cần hạn chế PII và quyền đọc.
- **Caching và telemetry:** không ghi toàn bộ dữ liệu lỗi chứa SQL/bind parameters vào công cụ phân tích chạy trong browser.
- **Migrations:** API không đổi chỉ vì bảng chuyển từ `products` thành hai bảng hoặc SQL được tối ưu bằng index/materialized view.

Kể cả API chỉ chạy trong mạng nội bộ, browser/mobile vẫn là client ở ngoài ranh giới bảo vệ dữ liệu của server.

## 12. Kiểm thử kiến trúc và hợp đồng thay vì soi SQL từ UI

Có hai loại kiểm thử bổ trợ cho nhau.

**Test hợp đồng web, không cần DB:** tạo mock/fake `CatalogService`, gửi request qua Spring MVC `MockMvc`, kiểm tra status, DTO và body lỗi. Ví dụ sau dùng `@MockBean` của Spring Boot 3.3.x (phiên bản mới hơn có thể dùng `@MockitoBean`):

`src/test/java/demo/catalog/CatalogContractTest.java`:

```java
package demo.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
@Import(ApiErrorHandler.class)
class CatalogContractTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CatalogService service;

    @Test
    void unexpectedDatabaseFailureDoesNotLeakDriverDetails()
            throws Exception {
        when(service.get(99L)).thenThrow(
                new DataAccessResourceFailureException(
                        "jdbc:postgresql://internal-host/secret"
                )
        );

        mvc.perform(get("/api/products/99"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_STORAGE_ERROR"))
                .andExpect(content().string(
                        not(containsString("jdbc:postgresql"))
                ))
                .andExpect(content().string(
                        not(containsString("internal-host"))
                ));
    }
}
```

Với dependency test và lớp ví dụ ở trên, chạy:

```bash
./gradlew test
```

Bài test kiểm tra một tính chất **có giá trị cho client**: lỗi hạ tầng được che khỏi response. Nó không xác nhận PostgreSQL thật đang chạy hoặc `ON CONFLICT` đúng; đó là trách nhiệm của integration test.

**Integration test tầng dữ liệu:** dùng PostgreSQL thực/test container và kiểm tra:

1. `ProductStore.insert` tạo hàng, map `BigDecimal` và generated ID đúng.
2. Insert cùng SKU hai lần, kể cả đồng thời, chỉ một bản ghi được tạo và adapter trả `SkuAlreadyUsed` cho trường hợp xung đột.
3. `findById` trả `Optional.empty()` khi không có hàng, không ném loại exception của driver lên service.
4. Lỗi DB ngoài dự kiến vẫn là failure, không bị mô tả nhầm là `SKU_ALREADY_USED`.
5. Khi use case có nhiều lệnh ghi, transaction rollback toàn bộ nếu bước sau thất bại.

Đổi adapter thành JPA hoặc thay SQL tối ưu không nên làm hỏng test hợp đồng web; điều phải kiểm tra lại là integration test theo persistence implementation mới.

**Static architecture check/code review:** tìm import `java.sql.*`, `org.postgresql.*`, `JdbcTemplate`, `EntityManager` hoặc query string chứa `SELECT/INSERT/UPDATE/DELETE` trong package web/presentation. Không phải mọi từ “SELECT” trong chú thích đều là lỗi; hãy đánh giá ranh giới thực và caller. Ngoài ra kiểm tra response serializer, `@ExceptionHandler`, logging và schema/error snapshots để phát hiện rò rỉ.

## 13. Những nhầm lẫn phổ biến

| Cách làm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Controller tự gọi `JdbcTemplate` | UI gắn với SQL và transaction | Đưa SQL vào repository/DAO; controller gọi service |
| Trả `List<Map<String,Object>>` lấy trực tiếp từ DB | Response tự thay đổi theo tên cột/schema | Map sang DTO được kiểm soát |
| Controller bắt `SQLException` | Ràng buộc với driver và SQLSTATE | Dịch ở adapter; service/web xử lý ý nghĩa ứng dụng |
| Trả `ex.getMessage()` cho client | Lộ SQL/constraint/stack trace, error contract bất ổn | Trả status + error code + thông điệp an toàn |
| Mọi `DataIntegrityViolationException` đều thành `409` | Lẫn unique, FK, NOT NULL, CHECK | Phân loại đúng bất biến hoặc trả lỗi tổng quát |
| Chỉ kiểm tra trùng bằng `SELECT` trước `INSERT` | Race condition dưới tải đồng thời | Đặt UNIQUE ở DB, xử lý đúng conflict |
| Ghép filter/sort từ request vào SQL | SQL injection, gắn API với tên cột | Bind values và whitelist các cấu trúc SQL |
| Trả JPA entity trực tiếp | Lộ field nội bộ, lazy/cycle, thay đổi schema làm đổi JSON | Dùng API DTO/projection chủ động |
| Service mang `ResultSet` hoặc `Connection` | Logic ứng dụng phụ thuộc chi tiết DB | Chuyển sang domain/application types trong adapter |
| Tầng UI tự commit/rollback | Phá transaction boundary và chính sách use case | Để service/application quản lý transaction |
| Che mọi thông tin lỗi kể cả trong log | Không thể chẩn đoán sự cố | Response tối giản, log nội bộ có kiểm soát |
| Tạo interface cho mọi phép gán đơn giản | Tăng độ phức tạp không đem lại ranh giới mới | Chỉ trừu tượng hóa ở chỗ giúp đổi implementation/test use case |

## 14. Tình huống thiết kế: thay driver mà UI không đổi

Một nhóm đang dùng PostgreSQL/JDBC để lưu sản phẩm. Sau này họ muốn đổi adapter sang JPA hoặc tách phần đọc sang hệ thống tìm kiếm. Nếu public API vô tình trả tên cột snake_case và `PSQLException`, frontend phải sửa theo từng quyết định lưu trữ.

Với thiết kế ở mục 6, nhóm có thể tạo `JpaProductStore implements ProductStore` hoặc `SearchProductReader` cho read use case; service vẫn nhận/trả `Product` hoặc kết quả ứng dụng đã định nghĩa, controller vẫn sinh cùng `ProductResponse` và mã lỗi. Chỉ khi **yêu cầu nghiệp vụ** thay đổi (ví dụ giá có thêm currency, SKU khác quy tắc duy nhất) mới cần chủ động đổi public contract và version/migration theo quy trình của sản phẩm.

Đây là lợi ích thực tế của boundary: phát triển từng tầng độc lập, kiểm thử từng trách nhiệm và giảm phạm vi ảnh hưởng khi sửa lỗi database.

## 15. Bài tập tự kiểm tra

**Bài tập 1 — phát hiện coupling:** trong một controller có tham số `String whereClause` rồi gọi `jdbc.queryForList("SELECT * FROM orders WHERE " + whereClause)`. Hãy nêu rủi ro về coupling, injection, dữ liệu công khai và đề xuất request/DTO/service/repository thay thế.

**Bài tập 2 — xử lý lỗi:** một API trả body `"ERROR: duplicate key value violates unique constraint uq_products_sku"` cho client. Hãy thiết kế response `ProblemDetail` phù hợp và chỉ rõ chi tiết nào chỉ nên nằm ở server log.

**Bài tập 3 — đổi DBMS:** adapter hiện dùng `ON CONFLICT ... RETURNING`; nhóm muốn chuyển sang hệ hỗ trợ generated keys theo cú pháp khác. Liệt kê những lớp sẽ phải thay và những lớp/cấu trúc API nên giữ nguyên.

**Bài tập 4 — kiểm thử:** dùng `MockMvc` giả lập `DataAccessResourceFailureException` như mục 12; bổ sung assertions rằng response không chứa `SQLException`, `SELECT` hay hostname, có HTTP status và public `code`; đồng thời viết integration test cho trùng SKU ở PostgreSQL.

**Gợi ý:** (1) expose các filter nghiệp vụ có whitelist, không nhận SQL; (2) `409` + `SKU_ALREADY_USED` + thông điệp ngắn, log nội bộ chứa chi tiết đã kiểm soát; (3) chủ yếu thay adapter và migration/cấu hình, giữ use case và DTO nếu semantics không đổi; (4) chia test HTTP contract và test DB, vì chúng bảo vệ hai ranh giới khác nhau.

## 16. Checklist cho code review

- Controller có import `JdbcTemplate`, `java.sql`, `EntityManager` hoặc driver class không?
- Có tham số request nào chứa SQL thô, tên bảng/cột, `WHERE`/`ORDER BY` nguyên văn không?
- Web trả DTO ổn định hay lộ `ResultSet`/`Map`/JPA entity hoặc trường DB ngoài chủ đích?
- Service gọi cổng truy cập dữ liệu có ngữ nghĩa rõ thay vì tự biết SQL hay driver chưa?
- SQL, bind parameters, row mapping và xử lý SQL dialect có nằm trong repository adapter không?
- Các bất biến concurrency có constraint DB phù hợp, thay vì chỉ check trước bằng `SELECT` không?
- Client có nhận mã lỗi nghiệp vụ/HTTP phù hợp mà không nhận exception message/SQLSTATE/stack trace không?
- Transaction được đặt tại ranh giới use case; rollback và retry đã được kiểm tra với exception thực chưa?
- Log/tracing nội bộ có đủ để debug mà không lộ bí mật/PII ra client telemetry không?
- Đổi cách lưu trữ có thể thực hiện bằng việc thay adapter và integration test mà không đổi API contract chứ?

**Kết luận:** SQL, query plan, connection pool, JDBC driver và tên constraint là chi tiết thực thi thuộc tầng dữ liệu. Controller nên chỉ chuyển tải HTTP, validation và DTO; service quản lý use case/transaction; repository chịu trách nhiệm truy vấn, ánh xạ và dịch sự cố thành tín hiệu ứng dụng phù hợp. API công khai phản ánh **ngữ nghĩa nghiệp vụ**, nhờ đó vừa an toàn hơn, vừa dễ thay đổi công nghệ lưu trữ.

## Tài liệu tham khảo

- Spring Framework — DAO Support và `DataAccessException`: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- Spring Framework — JDBC Core, `JdbcTemplate` và `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — REST Error Responses và `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- PostgreSQL — `INSERT` / `ON CONFLICT` / `RETURNING`: https://www.postgresql.org/docs/current/sql-insert.html
- OWASP — SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
