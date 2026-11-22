# Không coi ánh xạ tự động là thay thế kiểm tra kiểu và dữ liệu đầu vào

## 1. Vấn đề cốt lõi: ánh xạ thành công chưa có nghĩa dữ liệu hợp lệ

Khi xây tầng data-access bằng Spring Framework, ta thường đọc dữ liệu qua `JdbcTemplate`, `BeanPropertyRowMapper`, `DataClassRowMapper` hoặc một `RowMapper` tự viết. Các công cụ này giúp đưa giá trị của cột SQL sang thuộc tính Java, chuyển một số kiểu dữ liệu và tạo object. Tuy nhiên, **chuyển thành object không đồng nghĩa giá trị trong object đã thỏa mãn quy tắc nghiệp vụ, quy tắc bảo mật hoặc hợp đồng API**.

Ví dụ, một bản ghi sản phẩm có thể được ánh xạ hoàn toàn “thành công”:

- `sku = "SKU-002"` → Java `String`.
- `price = -7.00` → `BigDecimal("-7.00")`.
- `stock = 2` → Java `Integer(2)`.
- `status = "ACTIVE"` → Java `String`.

Không có lỗi JDBC hay lỗi ánh xạ, nhưng **giá âm** có thể vi phạm hợp đồng dữ liệu của ứng dụng. Tương tự, một cột `stock` bị `NULL` có thể được ánh xạ vào `Integer` mà không phát sinh exception, nhưng service cần số lượng tồn kho bắt buộc phải có. Chuỗi `status = "UNKNOWN"` là `String` hợp lệ về mặt kiểu, nhưng không thuộc tập trạng thái được hỗ trợ.

Vì vậy cần phân biệt **ba việc riêng**:

1. **Đọc dữ liệu:** JDBC đọc cột, SQL NULL, số, chuỗi, thời gian... từ ResultSet.
2. **Ánh xạ/chuyển kiểu:** RowMapper hoặc ConversionService gán giá trị vào field, setter hay constructor Java.
3. **Kiểm tra hợp đồng và dữ liệu:** validate nullability, định dạng, miền giá trị, quan hệ giữa các trường, enum hợp lệ, tính chính xác số/thời gian, ràng buộc nghiệp vụ và ranh giới tin cậy.

Một chương trình chỉ làm xong bước 2 chưa chắc làm đúng bước 3.

## 2. Các ranh giới dữ liệu cần phân biệt

Dữ liệu đi qua hệ thống theo hai hướng; mỗi hướng có nhiệm vụ kiểm tra riêng.

~~~text
HTTP / message / batch input
    │ parse JSON, đọc dữ liệu thô
    ▼
DTO đầu vào
    │ xác thực cú pháp/kiểu, Bean Validation, quy tắc nghiệp vụ
    ▼
Service / domain
    │ bind tham số SQL; không nối chuỗi dữ liệu người dùng
    ▼
Database
    │ NOT NULL, CHECK, UNIQUE, FK, DECIMAL, transaction...
    ▼
ResultSet (dữ liệu có thể đến từ dữ liệu cũ/import/lỗi migration)
    │ RowMapper / BeanPropertyRowMapper / DataClassRowMapper
    ▼
Object Java đã ánh xạ
    │ kiểm tra nullability, kiểu thực tế, giá trị miền, quan hệ field
    ▼
DTO/domain đã kiểm chứng
    │ không rò rỉ JDBC handle, chỉ công bố dữ liệu phù hợp hợp đồng
    ▼
Service / API / người tiêu thụ
~~~

Điểm đáng nhớ:

- **Input validation** bảo vệ dữ liệu mới đi *vào* hệ thống. Nó bao gồm giới hạn độ dài, phạm vi, pattern, whitelist và quy tắc liên trường. Một JSON parser chuyển `"5"` thành số thành công không bảo đảm `5` được nghiệp vụ chấp nhận.
- **Database constraints** là tuyến phòng thủ cấp lưu trữ: NOT NULL, CHECK, FK, UNIQUE, giới hạn độ chính xác và transaction. Chúng bảo vệ dữ liệu trước nhiều đường ghi, nhưng schema cũ, import, dữ liệu đã lưu, migration, quyền bypass hoặc logic liên bảng vẫn có thể để lại trạng thái không đúng hợp đồng của API.
- **Result mapping** đưa giá trị từ ResultSet thành Java. Tầng này cần xác định có chấp nhận `NULL`, giá trị lạ, enum lạ, giá trị mất độ chính xác hoặc dữ liệu không đầy đủ hay không.
- **Post-mapping validation** là bước xác nhận object đã ánh xạ thực sự phù hợp với domain/response contract. Việc này không tự xảy ra chỉ vì dùng một mapper “tự động”.

Ở đây “dữ liệu đầu vào” gồm cả dữ liệu nhập từ request và dữ liệu đọc từ database. Database có thể chứa dữ liệu ngoại lai hoặc lịch sử; **không mặc nhiên tin rằng dữ liệu đọc ra luôn đúng**.

## 3. BeanPropertyRowMapper thực sự làm gì?

`BeanPropertyRowMapper<T>` của Spring JDBC tạo một Java bean bằng constructor không tham số và gán các cột có tên tương ứng vào property có setter public. Nó nhận diện các tên cột phù hợp tên thuộc tính; tên `first_name` có thể ánh xạ vào `firstName` theo quy tắc underscore → camelCase. Có thể dùng alias SQL để chủ động kiểm soát tên mapping.

Ví dụ lớp bean:

~~~java
public class PriceRow {
    private long id;
    private String sku;
    private BigDecimal price;

    public PriceRow() {}

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
~~~

Đây là **ví dụ định nghĩa Java bean**, giả định đã import `java.math.BigDecimal`. Trong repository có thể viết:

~~~java
List<PriceRow> rows = jdbc.query(
        "SELECT id, sku, price FROM inventory_rows",
        BeanPropertyRowMapper.newInstance(PriceRow.class));
~~~

Đây là **đoạn minh họa đặt trong lớp có trường `JdbcTemplate jdbc`**, cần import `BeanPropertyRowMapper` và `List`. Nếu database chứa `price = -7.00`, mapper vẫn có thể tạo `PriceRow` với giá -7.00. Không có bước kiểm tra giá dương tự động.

### 3.1. Chuyển kiểu không phải xác thực nghiệp vụ

Mapper hỗ trợ nhiều kiểu thường gặp: `String`, `BigDecimal`, số nguyên, boolean, kiểu ngày giờ... và có thể sử dụng `ConversionService` để chuyển kiểu. Nếu giá trị được chuyển thành công, **không** có nghĩa:

- Mã sản phẩm đúng pattern.
- Giá tiền dương và nằm trong giới hạn bán hàng.
- Ngày bắt đầu nhỏ hơn hoặc bằng ngày kết thúc.
- Trạng thái nằm trong danh sách mà API hỗ trợ.
- Đơn vị tiền tệ, scale, timezone hoặc precision khớp hợp đồng.
- Những property không được SELECT thực sự đã được gán.
- Object phù hợp annotation `@NotNull`, `@Positive`, `@Pattern` nếu chưa gọi validator.

Một conversion thất bại có thể tạo exception, nhưng conversion thành công chỉ xác nhận **có thể chuyển kiểu**, không chứng minh **giá trị hợp lệ**.

### 3.2. Property không được ánh xạ có thể vẫn giữ giá trị mặc định

Mặc định, `BeanPropertyRowMapper` không yêu cầu tất cả writable properties của bean phải được điền. Nếu bạn quên chọn một cột trong SELECT, trường Java tương ứng có thể giữ `null`, `0` hoặc giá trị mặc định. Cờ `setCheckFullyPopulated(true)` giúp phát hiện một số trường hợp thiếu mapping cho property, nhưng **không kiểm tra quy tắc domain** hoặc bảo đảm cột SQL có giá trị khác NULL.

Ví dụ:

~~~java
BeanPropertyRowMapper<PriceRow> mapper =
        BeanPropertyRowMapper.newInstance(PriceRow.class);
mapper.setCheckFullyPopulated(true);
~~~

Một mapper strict về **độ đầy đủ của property** vẫn chấp nhận giá -7.00 nếu property price đã nhận được giá trị đó.

### 3.3. NULL đối với primitive là trường hợp dễ bị bỏ qua

Khi cột SQL NULL được ánh xạ vào Java primitive như `int`, mapper mặc định thường ném `TypeMismatchException` vì không thể gán null cho primitive. Có tùy chọn `setPrimitivesDefaultedForNullValue(true)` để bỏ qua null đó và giữ giá trị primitive mặc định hoặc giá trị do constructor đặt. Nhưng bật tùy chọn này có nguy cơ **biến thông tin bị thiếu thành 0 hoặc false**, làm sai ý nghĩa nghiệp vụ.

Ví dụ, `stock = NULL` không có nghĩa `stock = 0`. Với dữ liệu nullable, hãy dùng `Integer`/wrapper để còn phân biệt null, rồi quyết định rõ: cho phép `null`, đặt fallback có chủ đích hay từ chối bản ghi.

### 3.4. Record cần một mapper khác, nhưng vẫn cần validation

`BeanPropertyRowMapper` dành cho JavaBean có setter; với Java `record` hoặc data class có constructor nhận giá trị, Spring cung cấp `DataClassRowMapper`. Nó có thể ánh xạ theo tham số constructor, nhưng vẫn **không mặc nhiên chạy toàn bộ quy tắc nghiệp vụ**. Record constructor có thể tự xác thực, hoặc service có thể gọi validator rõ ràng, nhưng đừng mặc định mapper đủ để kiểm tra mọi điều kiện.

## 4. Ví dụ chạy được: so sánh ánh xạ tự động và ánh xạ có kiểm tra

Ví dụ Java 21 + Spring Boot 3.3.5 + H2 sau mô phỏng dữ liệu legacy có một dòng tốt và một số dòng sai. Để quan sát vấn đề, bảng demo **cố ý không đặt CHECK/NOT NULL lên các cột dữ liệu nghiệp vụ**. Trong production, hãy tăng cường ràng buộc database sau khi sửa dữ liệu cũ; ví dụ này không khuyến khích lưu dữ liệu sai.

Quy tắc nghiệp vụ của ứng dụng:

- `sku` phải đúng mẫu `SKU-[0-9]{3}`.
- `price` là `BigDecimal` **khác null** và **lớn hơn 0**.
- `stock` phải **khác null** và **không âm**. Tồn kho 0 là hợp lệ trong mô hình này; NULL là “chưa biết” chứ không phải 0.
- `status` chỉ được `ACTIVE` hoặc `INACTIVE`, đúng chữ hoa.
- `id` phải là số nguyên dương.

Khi gặp bản ghi sai, tầng data-access không tự sửa, không chuyển giá âm thành 0 và không âm thầm dùng trạng thái mặc định: nó báo lỗi có id và trường dữ liệu vi phạm.

### 4.1. Cấu trúc dự án

~~~text
strict-mapping-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/mapping/
    │   ├── MappingApplication.java
    │   ├── InventoryRow.java
    │   ├── ProductStatus.java
    │   ├── ProductView.java
    │   ├── InvalidCatalogDataException.java
    │   └── InventoryRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'strict-mapping-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:strictmapping;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory_rows (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40),
    price DECIMAL(12, 2),
    stock INTEGER,
    status VARCHAR(32)
);
~~~

Tệp `src/main/resources/data.sql`:

~~~sql
INSERT INTO inventory_rows(id, sku, price, stock, status) VALUES
    (1, 'SKU-001', 125.50, 3, 'ACTIVE'),
    (2, 'SKU-002', -7.00, 2, 'ACTIVE'),
    (3, 'SKU-003', 50.00, NULL, 'ACTIVE'),
    (4, 'SKU-004', 15.00, 1, 'UNKNOWN'),
    (5, 'bad-sku', 19.00, 1, 'ACTIVE');
~~~

Bản ghi 1 hợp lệ. Bản ghi 2 sai vì giá âm; 3 thiếu số tồn kho; 4 chứa status ngoài enum; 5 có SKU sai pattern. Cả năm vẫn là các hàng SQL có thể đọc và các cột có kiểu SQL tương thích. Đây là khác biệt giữa **lưu/ánh xạ được** và **đúng dữ liệu nghiệp vụ**.

### 4.2. Bean dành cho ánh xạ tự động

Tệp `src/main/java/example/mapping/InventoryRow.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;

public class InventoryRow {
    private long id;
    private String sku;
    private BigDecimal price;
    private Integer stock;
    private String status;

    public InventoryRow() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public Integer getStock() {
        return stock;
    }

    public void setStock(Integer stock) {
        this.stock = stock;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Bean có constructor rỗng và setter, tên property khớp cột SQL. `Integer stock` cho phép giữ nguyên thông tin NULL. Không có logic kiểm tra giá dương trong setter; ta cố ý quan sát việc auto mapper có thể ánh xạ dòng không hợp lệ.

### 4.3. Domain view chỉ nhận trạng thái hợp lệ

Tệp `src/main/java/example/mapping/ProductStatus.java`:

~~~java
package example.mapping;

public enum ProductStatus {
    ACTIVE,
    INACTIVE
}
~~~

Tệp `src/main/java/example/mapping/ProductView.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;

public record ProductView(
        long id,
        String sku,
        BigDecimal price,
        int stock,
        ProductStatus status) {
}
~~~

Đây là DTO chỉ chứa các kiểu đã được kiểm chứng. Record không tự kiểm tra dữ liệu chỉ nhờ là record; các điều kiện cần được thực thi ở mapper/constructor/factory hoặc một bước validation rõ ràng. Trong ví dụ ta để mapper thực hiện validation trước khi tạo ProductView.

Tệp `src/main/java/example/mapping/InvalidCatalogDataException.java`:

~~~java
package example.mapping;

public class InvalidCatalogDataException extends RuntimeException {
    public InvalidCatalogDataException(String message) {
        super(message);
    }
}
~~~

Đây là một exception nghiệp vụ/dữ liệu không hợp lệ, **khác** với lỗi JDBC. Nó giúp caller phân biệt “database không truy vấn được” với “database trả một hàng không thỏa hợp đồng của ứng dụng”.

### 4.4. Repository: auto mapper và custom mapper có kiểm tra

Tệp `src/main/java/example/mapping/InventoryRepository.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    private static final String SELECT = """
            SELECT id, sku, price, stock, status
            FROM inventory_rows
            WHERE id = ?
            """;

    private final JdbcTemplate jdbc;

    public InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public InventoryRow findAutomatically(long id) {
        return jdbc.queryForObject(
                SELECT,
                BeanPropertyRowMapper.newInstance(InventoryRow.class),
                id);
    }

    public ProductView findStrictly(long id) {
        return jdbc.queryForObject(SELECT, this::mapAndValidate, id);
    }

    private ProductView mapAndValidate(ResultSet rs, int rowNumber)
            throws SQLException {

        long id = rs.getLong("id");
        if (id <= 0) {
            throw invalid(id, "id phải lớn hơn 0");
        }

        String sku = rs.getString("sku");
        if (sku == null || !sku.matches("SKU-[0-9]{3}")) {
            throw invalid(id, "sku sai định dạng: " + sku);
        }

        BigDecimal price = rs.getBigDecimal("price");
        if (price == null || price.signum() <= 0) {
            throw invalid(id, "price phải lớn hơn 0");
        }

        int stock = rs.getInt("stock");
        if (rs.wasNull()) {
            throw invalid(id, "stock không được NULL");
        }
        if (stock < 0) {
            throw invalid(id, "stock không được âm");
        }

        String statusText = rs.getString("status");
        if (statusText == null) {
            throw invalid(id, "status không được NULL");
        }

        ProductStatus status = switch (statusText) {
            case "ACTIVE" -> ProductStatus.ACTIVE;
            case "INACTIVE" -> ProductStatus.INACTIVE;
            default -> throw invalid(
                    id, "status không hợp lệ: " + statusText);
        };

        return new ProductView(id, sku, price, stock, status);
    }

    private static InvalidCatalogDataException invalid(
            long id, String problem) {
        return new InvalidCatalogDataException(
                "id=" + id + ", " + problem);
    }
}
~~~

Lưu ý kỹ thuật:

- `BeanPropertyRowMapper.newInstance(InventoryRow.class)` gán các giá trị tương thích vào bean mà **không biết** price phải dương.
- `getBigDecimal("price")` giữ giá trị tiền dạng decimal, tránh đưa qua `double` làm mất chính xác nhị phân không cần thiết.
- `ResultSet.getInt("stock")` trả 0 cả khi SQL NULL; **phải gọi `rs.wasNull()` ngay sau lệnh đọc tương ứng** để phân biệt NULL và số 0. Nếu dùng `rs.getObject("stock", Integer.class)` và driver hỗ trợ đúng, có thể giữ nullable wrapper rồi validate.
- `switch` biểu diễn whitelist status rõ ràng. Nếu database thêm trạng thái mới, code không tự chấp nhận trạng thái ấy mà báo lỗi để điều chỉnh hợp đồng có chủ đích.
- `matches("SKU-[0-9]{3}")` kiểm tra định dạng đầy đủ của SKU, không chỉ việc giá trị là String.
- Mỗi exception có id và trường để debug/quarantine dữ liệu nguồn. Trong ứng dụng có dữ liệu nhạy cảm, không in toàn bộ giá trị đầu vào vào public log/HTTP response; nên tách thông tin nội bộ khỏi thông điệp trả client.
- `queryForObject` yêu cầu đúng một hàng: không có hàng có thể ném `EmptyResultDataAccessException`, nhiều hàng ném exception tương ứng. Đó là tình huống khác với một hàng tồn tại nhưng **không hợp lệ**. Demo chỉ gọi các id có sẵn và khóa chính bảo đảm nhiều nhất một hàng.

### 4.5. Chương trình quan sát hành vi

Tệp `src/main/java/example/mapping/MappingApplication.java`:

~~~java
package example.mapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(InventoryRepository repo) {
        return args -> {
            InventoryRow raw = repo.findAutomatically(2);
            System.out.println("Auto id=2: price="
                    + raw.getPrice().toPlainString());

            ProductView good = repo.findStrictly(1);
            System.out.printf(
                    "Hợp lệ: id=%d, sku=%s, price=%s, stock=%d, status=%s%n",
                    good.id(),
                    good.sku(),
                    good.price().toPlainString(),
                    good.stock(),
                    good.status());

            for (long id = 2; id <= 5; id++) {
                try {
                    repo.findStrictly(id);
                } catch (InvalidCatalogDataException ex) {
                    System.out.println(ex.getMessage());
                }
            }
        };
    }
}
~~~

Sử dụng JDK 21 và Gradle hỗ trợ Java 21 (ví dụ Gradle 8.5), chạy:

~~~bash
gradle bootRun
~~~

Các dòng **do ứng dụng in**, không tính thông báo build của Gradle:

~~~text
Auto id=2: price=-7.00
Hợp lệ: id=1, sku=SKU-001, price=125.50, stock=3, status=ACTIVE
id=2, price phải lớn hơn 0
id=3, stock không được NULL
id=4, status không hợp lệ: UNKNOWN
id=5, sku sai định dạng: bad-sku
~~~

Dòng đầu chứng minh auto mapper **không phát hiện giá âm**. Năm dòng sau chứng minh custom RowMapper có thể chặn dữ liệu sai ngay tại ranh giới đọc và đưa cho caller một ProductView với các bất biến mà ứng dụng đã kiểm tra.

Ứng dụng này được thiết kế minh họa cách làm fail-fast với bản ghi sai. Một hệ thống xử lý batch có thể muốn **quarantine** các hàng lỗi, ghi nhận mã lỗi, bỏ qua theo chính sách được phê duyệt và tiếp tục hàng khác. Đừng âm thầm sửa `-7.00` thành 0 hoặc biến `UNKNOWN` thành `ACTIVE`.

## 5. Vì sao phải kiểm tra cả kiểu và giá trị?

### 5.1. SQL NULL và Java primitive

Một cột có SQL NULL không tương đương với số 0, false hoặc chuỗi rỗng. Để đọc integer:

~~~java
int count = rs.getInt("stock");
if (rs.wasNull()) {
    throw new IllegalStateException("stock không được NULL");
}
~~~

Đây là **đoạn RowMapper minh họa**, giả sử có ResultSet `rs` còn mở. `wasNull()` chỉ phản ánh lần đọc cột gần nhất, nên gọi ngay sau `getInt`. Nếu null có ý nghĩa hợp lệ, dùng `Integer` hoặc Optional trong API thích hợp, không tự thay null bằng 0.

Tùy chọn `primitivesDefaultedForNullValue` của BeanPropertyRowMapper có thể làm null trở thành giá trị mặc định trong bean. Dùng nó cần hiểu hệ quả, không bật chỉ để “chạy cho qua”.

### 5.2. BigDecimal, độ chính xác và đơn vị

Tiền nên dùng DECIMAL/NUMERIC ở database và BigDecimal ở Java khi cần số thập phân chính xác. Tránh làm trung gian qua float/double vì có thể gây sai số. Không dùng `new BigDecimal(0.1)` để biểu diễn chính xác 0.1; khi cần tạo từ chữ số thập phân, dùng `new BigDecimal("0.1")` hoặc factory phù hợp.

Vẫn cần kiểm tra:

- `price != null` và `price.signum() > 0` nếu giá phải dương.
- Giới hạn trên và quy tắc đơn vị tiền tệ.
- Scale và rounding policy nếu chuyển qua đơn vị nhỏ nhất; không tùy ý `setScale(2)` khiến làm tròn thiếu kiểm soát.
- Cột `DECIMAL(12,2)` không tự biết chính sách “giá bán phải lớn hơn 0”.

### 5.3. Enum và trạng thái lạ

Đọc một chuỗi thành công không có nghĩa thuộc tính business đúng. Dùng danh sách trạng thái cho phép một cách tường minh hoặc phép chuyển `Enum.valueOf` có xử lý lỗi; **không** gán trạng thái mặc định một cách im lặng khi gặp giá trị mới. Nếu schema tiến hóa bổ sung status, tầng đọc cần quyết định hợp đồng tương thích, migration và rollout.

`Enum.valueOf` phân biệt chữ hoa/chữ thường. Việc tự `trim().toUpperCase()` có thể có giá trị nếu hợp đồng quy định normalize, nhưng cũng có thể che dữ liệu sai. Hãy quyết định trước.

### 5.4. Chuỗi, mã định danh và Unicode

Kiểm tra chuỗi rỗng, blank, độ dài, pattern, normalization và semantics theo domain. Không dùng một pattern chung cho mọi trường. Với dữ liệu Unicode, quy tắc độ dài theo code point, ký tự hiển thị hay giới hạn lưu trữ của database có thể khác; phải chọn đúng tiêu chí theo ứng dụng.

Một `sku` hay `email` có kiểu String hợp lệ vẫn có thể sai định dạng. Với input người dùng, validate trước khi ghi; với dữ liệu đọc từ bảng cũ hoặc hệ thống import, validate lại theo hợp đồng sử dụng.

### 5.5. Ngày, giờ và timezone

Ánh xạ `DATE` sang LocalDate thường chỉ biểu diễn ngày. `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, Instant, LocalDateTime và OffsetDateTime **không tương đương** nhau. Phải xét database, JDBC driver, timezone, offset và quy tắc chuyển đổi rõ ràng. Một chuyển đổi tự động chạy được vẫn có thể lệch múi giờ hoặc sai ý nghĩa “thời điểm sự kiện”.

Với dữ liệu có khoảng thời gian, kiểm tra `start <= end`, không tương lai nếu hợp đồng yêu cầu, và DST/timezone nếu liên quan.

### 5.6. Kiểu SQL và miền giá trị

Một SQL INTEGER có thể chuyển sang Java int, nhưng business có thể chỉ cho phép 0–100; một VARCHAR có thể lưu bất kỳ chuỗi nào, trong khi API chỉ cho whitelist. Kiểu dữ liệu là điều kiện **cần**, không phải điều kiện **đủ**.

Hãy đặt các bất biến vào DTO constructor/factory, explicit mapper hoặc validation layer — nơi có thông tin nghiệp vụ — và bổ sung CHECK/NOT NULL/UNIQUE ở database khi phù hợp.

## 6. Kiểm tra đầu vào trước khi ghi cũng không được bỏ qua

Ngược hướng đọc, request/input DTO có thể được parse thành Java object và truyền vào repository. JSON binding của Spring MVC, setter binding, ConversionService hoặc đọc CSV giúp đổi hình dạng dữ liệu; chúng **không thay thế validation**.

Một request có thể chứa `price = -7.00` đã parse thành BigDecimal thành công. Nếu endpoint dùng Jakarta Bean Validation, có thể khai báo:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateProductRequest(
        @NotBlank
        @Pattern(regexp = "SKU-[0-9]{3}")
        String sku,

        @NotNull
        @Positive
        BigDecimal price,

        @NotNull
        @PositiveOrZero
        Integer stock) {
}
~~~

Đây là **định nghĩa request minh họa**, không phải phần của ứng dụng console ở mục 4; để chạy Bean Validation cần dependency `spring-boot-starter-validation` (hoặc provider phù hợp), và phải **kích hoạt validation** tại entrypoint, chẳng hạn dùng `@Valid` trên tham số request được Spring MVC hỗ trợ hoặc gọi `jakarta.validation.Validator.validate(...)` rõ ràng. Chỉ đặt annotation lên record mà không chạy validator thì chưa có bước kiểm tra.

Trong service tiếp tục kiểm tra quy tắc liên quan database, quyền truy cập và điều kiện nghiệp vụ, vì constraint đơn giản trên từng field chưa bao phủ hết.

### Parameter binding giải quyết một nguy cơ khác

Không ghép chuỗi từ user thành SQL:

~~~java
// Sai: user input làm thay đổi cấu trúc SQL.
String sql = "SELECT * FROM inventory_rows WHERE sku = '" + inputSku + "'";
~~~

Dùng bind parameter:

~~~java
List<InventoryRow> rows = jdbc.query(
        "SELECT id, sku, price, stock, status "
        + "FROM inventory_rows WHERE sku = ?",
        BeanPropertyRowMapper.newInstance(InventoryRow.class),
        inputSku);
~~~

Hai đoạn là **minh họa trong repository có JdbcTemplate jdbc, biến inputSku**, không phải source độc lập. Bind parameter ngăn dữ liệu trở thành cú pháp SQL ở vị trí giá trị; nó **không** xác minh SKU đúng pattern hoặc được quyền truy cập. Đồng thời, placeholder không dùng trực tiếp thay tên bảng/cột; dynamic identifier phải có whitelist riêng.

### Defense in depth ở database

Sau khi dọn dữ liệu lỗi trong môi trường thật, có thể bổ sung:

~~~sql
ALTER TABLE inventory_rows
    ALTER COLUMN price SET NOT NULL;

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_price_positive CHECK (price > 0);

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_stock_nonnegative
    CHECK (stock IS NOT NULL AND stock >= 0);

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_status_allowed
    CHECK (status IN ('ACTIVE', 'INACTIVE'));
~~~

Đây là **đề xuất migration cho schema đã sạch**, không chạy trên bộ dữ liệu cố ý lỗi ở mục 4 vì những dòng vi phạm sẽ khiến thao tác migration thất bại. Cú pháp ALTER TABLE/CHECK có thể khác theo hệ quản trị; cân nhắc kiểm thử trên database đích. CHECK cũng phải xét SQL NULL semantics — ví dụ `CHECK (stock >= 0)` riêng có thể cho qua NULL tùy SQL three-valued logic; hãy dùng NOT NULL hoặc điều kiện rõ.

Ràng buộc database và validation phía ứng dụng **bổ sung cho nhau**, không thay thế lẫn nhau.

## 7. Ba chiến lược xử lý dữ liệu đã ánh xạ

### 7.1. Fail fast

Với kết quả dùng để tính tiền, ra quyết định quan trọng, cập nhật trạng thái đơn hàng, tốt nhất là từ chối object vi phạm invariant ngay tại ranh giới đọc. Throw exception có id/trường cụ thể, để service xác định response/log phù hợp. Đây là chiến lược custom RowMapper trong demo.

### 7.2. Validation sau khi tự động ánh xạ

Nếu muốn tận dụng BeanPropertyRowMapper, có thể map thành bean trung gian rồi kiểm tra **ngay sau đó**:

~~~java
InventoryRow raw = jdbc.queryForObject(
        "SELECT id, sku, price, stock, status "
        + "FROM inventory_rows WHERE id = ?",
        BeanPropertyRowMapper.newInstance(InventoryRow.class),
        id);

// Phải có bước kiểm tra tường minh trước khi tạo DTO an toàn.
ProductView checked = validatorOrFactory.validateAndConvert(raw);
~~~

Đây là **mã minh họa**, `validatorOrFactory` chỉ ký hiệu cho một thành phần xác thực do ứng dụng tự xây dựng, không phải API có sẵn của Spring; không chạy độc lập. Nếu dùng Jakarta Validator thì phải gọi validator hoặc tích hợp ở ranh giới phù hợp. Ưu điểm: bớt mã mapping. Nhược điểm: có thể tạo object trung gian tạm thời không hợp lệ, nên tuyệt đối không để object đó lọt qua service trước khi kiểm tra.

### 7.3. Kết quả lỗi có cấu trúc cho batch/import

Khi đồng bộ hàng nghìn dòng, fail-fast ở dòng đầu có thể chưa phù hợp. Tạo `ValidationResult`/error DTO tách rõ hàng hợp lệ và lỗi: mã hàng, trường, nguyên nhân, thời gian, nguồn. Cho phép quarantine, thống kê và sửa dữ liệu có kiểm soát. Tuy nhiên, không “đoán” giá trị hợp lệ chỉ để chương trình tiếp tục. Đặt hạn mức lỗi, quan sát và chính sách rollback rõ ràng cho job.

## 8. Kiểm chứng schema drift, alias và mapping completeness

Một mapper tự động chỉ biết những cột đã SELECT và những setter có thể gán. Khi schema/API thay đổi, cần cảnh giác:

- **Tên cột khác tên property:** ví dụ `product_code` vs `sku` sẽ không tự hiểu là một. Dùng alias `AS sku` hoặc mapper explicit.
- **Bỏ quên SELECT field:** object có property mặc định; `setCheckFullyPopulated(true)` giúp phát hiện thiếu map các writable property nhưng không bảo đảm giá trị non-null.
- **Cột dư:** mapper có thể bỏ qua cột không có property; lựa chọn này thuận tiện nhưng có thể che thay đổi contract nếu test không bao phủ.
- **Cột trùng tên/alias:** hai cột có tên giống nhau tạo mapping mơ hồ; viết SELECT cột rõ ràng và alias duy nhất.
- **Dùng `SELECT *`:** thay đổi schema làm output và cost khó đoán; chọn danh sách cột cần thiết và test mapping.
- **Kiểu dữ liệu migration:** chuyển INT sang BIGINT có thể vượt Java int; DECIMAL sang DOUBLE có thể mất chính xác; timestamp đổi timezone có thể đổi semantics. Cần test ở ranh giới.
- **Các cột nullable mới:** dùng wrapper/Optional theo contract, không tự coi 0/null/empty là tương đương.

Khi nâng cấp schema hoặc thay đổi mapper, nên có integration tests thực sự chạy với database mục tiêu (hoặc loại tương thích đủ gần), không chỉ mock ResultSet vì driver có thể khác nhau về conversion, generated keys và timezone.

## 9. Test nào chứng minh việc kiểm tra là thật?

Một bộ test đủ tốt nên bao phủ **happy path và dữ liệu lỗi**:

| Dữ liệu đầu vào/đọc | Phản ứng mong đợi | Lỗi sẽ xuất hiện nếu chỉ tin auto-mapping |
| --- | --- | --- |
| Giá 125.50, stock 3, status ACTIVE | Trả DTO hợp lệ | Không có. |
| Giá -7.00 | Từ chối vì price không dương | Mapper nhận BigDecimal âm và trả object bình thường. |
| Giá NULL | Từ chối hoặc xử lý thiếu dữ liệu theo hợp đồng | Bean price=null có thể lọt sang tầng tính giá. |
| Stock NULL | Từ chối hoặc giữ trạng thái unknown có chủ đích | Có thể bị hiểu nhầm thành stock=0. |
| Stock = -1 | Từ chối vì âm | Chuyển Integer thành công nhưng vi phạm domain. |
| Status UNKNOWN | Báo trạng thái không hỗ trợ | String hợp lệ nhưng không có ý nghĩa. |
| SKU sai pattern | Báo lỗi định dạng | String không được mapper kiểm tra pattern. |
| Không có hàng | Đưa ra not-found phù hợp | `queryForObject` có thể ném EmptyResultDataAccessException. |
| Bỏ thiếu cột SELECT | Phát hiện mapping incomplete | Bean chứa null/default mà không ai để ý. |
| Sai kiểu không chuyển được | Lỗi conversion được xử lý/quan sát | Không nên bắt exception rồi dùng giá trị mặc định. |
| Input chứa ký tự SQL | Bind parameter xử lý như dữ liệu | Nối chuỗi SQL có nguy cơ injection. |

Gợi ý kiểm thử riêng:

1. **Unit test** factory/validator với các trường hợp null, âm, sai pattern, ngoài enum, giá trị biên. Không cần database cho logic thuần.
2. **Integration test** trên JDBC/H2 hoặc database thật với schema và dữ liệu có chủ đích. Kiểm tra mapper strict trả đúng trường hợp hợp lệ và từ chối từng trường hợp lỗi.
3. **Transaction test** xác nhận exception đi qua service có rollback như thiết kế; validation thất bại không để lại ghi dữ liệu không nhất quán.
4. **Contract test** khi thay schema/alias: DTO field nào được chọn, nullability nào được chấp nhận và version schema nào được hỗ trợ.
5. **Observability**: theo dõi số hàng lỗi theo trường/nguồn, log có id, trace phù hợp nhưng không lộ dữ liệu nhạy cảm, và cảnh báo trước khi dữ liệu xấu lan ra API.

## 10. Các nhầm lẫn cần tránh

**“Mapping không ném exception thì dữ liệu đúng.”** Sai: giá -7.00 trong ví dụ được chuyển BigDecimal thành công.

**“BeanPropertyRowMapper đã chạy @NotNull/@Positive.”** Sai: mapper chỉ ánh xạ; Bean Validation cần được kích hoạt hoặc gọi rõ ràng.

**“checkFullyPopulated kiểm tra toàn bộ dữ liệu nghiệp vụ.”** Sai: cờ này kiểm tra độ phủ property, không kiểm tra giá, pattern, quan hệ giữa field hay non-null.

**“Bật primitivesDefaultedForNullValue là cách sửa null an toàn.”** Không luôn đúng: nó có thể biến thông tin không xác định thành giá trị primitive mặc định, làm sai kết quả.

**“Database có kiểu DECIMAL nên mọi giá đều hợp lệ.”** Sai: kiểu lưu trữ cho phép giá âm trừ khi constraint/nghiệp vụ cấm.

**“Tất cả enum lạ nên đổi thành UNKNOWN hoặc ACTIVE.”** Chỉ hợp lý nếu hợp đồng định nghĩa fallback; không được tự suy diễn.

**“Dữ liệu đã ở database thì có thể tin.”** Dữ liệu lịch sử, import, migration và producer khác có thể không tuân thủ các quy tắc mới.

**“Bắt mọi exception để trả dữ liệu mặc định sẽ tăng ổn định.”** Thường gây che lỗi, mất dữ liệu và làm quyết định nghiệp vụ sai; phải phân loại lỗi và chính sách fallback được định nghĩa rõ.

**“Validation chỉ thuộc controller.”** Controller kiểm tra dữ liệu đầu vào, nhưng repository/service cũng cần bảo vệ hợp đồng khi tiêu thụ dữ liệu từ nguồn khác.

**“SQL bind parameter đủ để bảo đảm mọi input hợp lệ.”** Binding ngăn SQL injection tại vị trí giá trị; nó không kiểm tra dữ liệu đúng domain hoặc quyền truy cập.

## 11. Checklist thiết kế tầng ánh xạ an toàn

- [ ] SELECT nêu rõ cột và alias, không dựa vào `SELECT *` một cách thiếu kiểm soát.
- [ ] Kiểu Java tương ứng kiểu SQL và độ lớn cần hỗ trợ; không tùy ý mất precision/scale/timezone.
- [ ] NULL được xử lý như trạng thái riêng; primitive chỉ dùng khi cột thực sự non-null theo hợp đồng.
- [ ] Dùng BigDecimal cho dữ liệu thập phân chính xác, đặc biệt tiền; quy tắc rounding rõ ràng.
- [ ] Kiểm tra miền giá trị: dương/không âm, pattern, enum whitelist, giới hạn và quy tắc liên trường.
- [ ] BeanPropertyRowMapper, DataClassRowMapper, ConversionService hoặc JSON binding không được coi là validator.
- [ ] Chạy Bean Validation hoặc explicit domain validation ở ranh giới thích hợp.
- [ ] Có DB constraint khi phù hợp, nhưng vẫn kiểm tra hợp đồng đọc với dữ liệu có nguồn không hoàn toàn đáng tin.
- [ ] Input đi vào câu SQL bằng bind parameter; dynamic identifier nếu có phải whitelist.
- [ ] Object lỗi không được âm thầm đi sang service/API; chính sách fail-fast/quarantine/fallback phải rõ.
- [ ] Kiểm thử dữ liệu hợp lệ, sai miền, NULL, sai kiểu, schema drift và input đối kháng.
- [ ] Kết quả trả ra là DTO/value object đã materialize, không lộ JDBC handle hoặc dữ liệu chưa được kiểm tra.

**Kết luận:** ánh xạ tự động giải quyết việc **đưa giá trị từ ResultSet vào object Java**. Kiểm tra kiểu, NULL, tính chính xác và quy tắc nghiệp vụ giải quyết một việc khác: **xác nhận object ấy có đáng tin để sử dụng hay không**. Hệ thống vững chắc cần cả hai, kết hợp với validation ở đầu vào và constraint ở database.

### Tài liệu tham khảo

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — BeanPropertyRowMapper API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — DataClassRowMapper API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
