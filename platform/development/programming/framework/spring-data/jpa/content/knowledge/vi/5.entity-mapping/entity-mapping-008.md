# Ánh xạ enum bằng STRING, ORDINAL và rủi ro thay đổi thứ tự

## Mục tiêu

Enum trong Java biểu diễn một tập giá trị hữu hạn, chẳng hạn trạng thái đơn hàng `PENDING`, `PAID`, `CANCELLED`. Khi lưu entity bằng JPA, giá trị enum phải được chuyển thành kiểu dữ liệu mà database có thể lưu. JPA hỗ trợ hai cách ánh xạ chuẩn qua `@Enumerated`: `EnumType.STRING` và `EnumType.ORDINAL`.

Chọn sai cách ánh xạ có thể khiến dữ liệu cũ bị diễn giải thành trạng thái khác sau khi thêm, xóa hoặc sắp xếp lại enum constants. Bài này giải thích dữ liệu được lưu như thế nào, vì sao `ORDINAL` đặc biệt nhạy với thứ tự, giới hạn của `STRING`, và cách dùng `AttributeConverter` khi cần mã lưu trữ ổn định.

## 1. Enum được lưu trong database ra sao?

Giả sử Java có enum:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
```

JPA không lưu object enum như một object Java. Provider chuyển giá trị thành dữ liệu cột trong database rồi khôi phục nó khi đọc entity.

| Cách ánh xạ | Giá trị Java | Giá trị thường được lưu |
| --- | --- | --- |
| `EnumType.STRING` | `PENDING` | Chuỗi `PENDING` |
| `EnumType.ORDINAL` | `PENDING` | Số `0` |

`STRING` lưu kết quả của `Enum.name()`. `ORDINAL` lưu kết quả của `Enum.ordinal()`, là vị trí bắt đầu từ 0 trong khai báo enum. Hai cách này có hành vi khác nhau khi mã nguồn thay đổi.

## 2. EnumType.STRING

Khai báo `@Enumerated(EnumType.STRING)` trên thuộc tính entity:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private OrderStatus status;
}
```

Nếu `status` là `OrderStatus.PENDING`, database lưu chuỗi `PENDING`. Khi đọc lại, JPA provider tìm enum constant có tên tương ứng và khôi phục thành `OrderStatus.PENDING`.

### Ưu điểm

- Giá trị database dễ đọc và dễ kiểm tra bằng SQL.
- Thêm một constant mới ở bất kỳ vị trí nào không làm thay đổi cách diễn giải các chuỗi đã lưu.
- Thứ tự constants trong file Java không tham gia vào dữ liệu đã lưu.
- Log, báo cáo và dữ liệu xuất ra thường dễ hiểu hơn số ordinal.

### Rủi ro còn lại

`STRING` phụ thuộc vào chính tên constant. Nếu đổi `PENDING` thành `WAITING`, các hàng đang lưu `PENDING` không tự đổi theo. Khi đọc chúng, provider không tìm thấy enum constant `PENDING` và việc hydrate entity có thể thất bại.

Xóa một constant cũng có vấn đề tương tự nếu database vẫn còn giá trị đó. Đổi cách viết hoa/thường cũng là thay đổi dữ liệu vì tên được lưu chính xác theo `name()`.

`@Enumerated(EnumType.STRING)` không gọi `toString()` để lưu. Override `toString()` chỉ thay đổi cách hiển thị object trong Java; nó không đổi chuỗi mà JPA ghi vào cột.

### Chú ý schema

Cột nên đủ dài cho tên constant dài nhất. Có thể đặt `length` rõ ràng để schema sinh ra có kích thước dự kiến:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 24)
private OrderStatus status;
```

Nếu thêm constant có tên dài hơn giới hạn cột, thao tác ghi có thể thất bại do dữ liệu quá dài. Cần cập nhật schema trước hoặc cùng lúc với phiên bản ứng dụng dùng constant mới.

## 3. EnumType.ORDINAL

Khai báo `@Enumerated(EnumType.ORDINAL)` sẽ lưu chỉ số thứ tự của enum:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.ORDINAL)
    @Column(nullable = false)
    private OrderStatus status;
}
```

Với khai báo ban đầu:

```java
public enum OrderStatus {
    PENDING,    // ordinal = 0
    PAID,       // ordinal = 1
    CANCELLED   // ordinal = 2
}
```

Database lưu `PENDING` thành `0`, `PAID` thành `1` và `CANCELLED` thành `2`. Khi đọc, JPA provider dùng số này làm chỉ số để lấy constant trong enum hiện tại.

### Vì sao đổi thứ tự làm sai dữ liệu?

Giả sử phiên bản sau sửa enum thành:

```java
public enum OrderStatus {
    PENDING,    // ordinal = 0
    CANCELLED,  // ordinal = 1
    PAID        // ordinal = 2
}
```

Dữ liệu cũ trong database vẫn giữ nguyên. Hàng có giá trị `1` trước đây nghĩa là `PAID`, nhưng với mã mới nó được đọc thành `CANCELLED`. Không nhất thiết có exception: nguy hiểm hơn là chương trình vẫn chạy nhưng diễn giải sai nghiệp vụ.

### Những thay đổi gây rủi ro

| Thay đổi enum | Tác động với ORDINAL |
| --- | --- |
| Chèn constant vào giữa | Các constant phía sau bị đổi ordinal; dữ liệu cũ có thể thành trạng thái khác. |
| Sắp xếp lại constants | Các ordinal đổi theo vị trí mới; dữ liệu cũ bị diễn giải sai. |
| Xóa constant ở giữa | Các constant sau dịch vị trí; dữ liệu cũ có thể thành giá trị khác. |
| Xóa constant cuối | Ordinal cũ có thể vượt quá số constant hiện tại và gây lỗi khi đọc. |
| Thêm constant cuối | Các ordinal cũ giữ nguyên, nhưng giá trị mới cần được hỗ trợ bởi mọi phiên bản ứng dụng đọc dữ liệu đó. |
| Đổi tên constant nhưng giữ nguyên vị trí | ORDINAL vẫn đọc theo vị trí, nên dữ liệu có thể được ánh xạ sang tên mới; ý nghĩa nghiệp vụ có thể đã thay đổi. |

Vì vậy, `ORDINAL` chỉ an toàn khi tập constants và thứ tự của chúng được giữ ổn định trong suốt vòng đời dữ liệu. Quy tắc “chỉ thêm ở cuối” giảm một số rủi ro nhưng vẫn đòi hỏi kiểm soát chặt chẽ việc xóa, đổi ý nghĩa và khả năng tương thích giữa các phiên bản ứng dụng.

### JPA mặc định là gì nếu bỏ @Enumerated?

Theo Jakarta Persistence, nếu thuộc tính enum không khai báo `@Enumerated` và không được áp dụng converter, kiểu ánh xạ mặc định là `ORDINAL`. Vì vậy, không nên dựa vào mặc định khi đọc code entity; hãy ghi rõ ý định:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

Việc ghi rõ annotation giúp người review nhận ra ngay định dạng lưu trữ và tránh vô tình dùng ordinal.

## 4. So sánh STRING và ORDINAL

| Tiêu chí | STRING | ORDINAL |
| --- | --- | --- |
| Dữ liệu lưu | Tên constant | Chỉ số vị trí |
| Dễ đọc trong SQL | Có | Không, phải tra thứ tự enum |
| Chèn constant vào giữa | Không làm đổi chuỗi cũ | Có thể đổi ý nghĩa các số cũ |
| Đổi tên constant | Cần migration dữ liệu hoặc tương thích tên cũ | Không đổi số nếu vị trí giữ nguyên, nhưng ý nghĩa vẫn cần đánh giá |
| Xóa constant | Cần xử lý các hàng còn tên cũ | Có thể làm sai ordinal của constants phía sau hoặc gây lỗi |
| Dung lượng | Thường lớn hơn | Thường nhỏ hơn |
| Độ ổn định khi refactor | Tốt hơn về thứ tự, phụ thuộc tên | Rất nhạy với thứ tự |

Đối với phần lớn enum nghiệp vụ được lưu lâu dài, `STRING` dễ bảo trì và ít rủi ro hơn `ORDINAL`. Nếu cần một giá trị lưu trữ ổn định ngay cả khi đổi tên constant, dùng `AttributeConverter` với mã tường minh.

## 5. Dùng AttributeConverter để lưu mã ổn định

`AttributeConverter<X, Y>` cho phép tự định nghĩa cách chuyển kiểu Java `X` sang kiểu database `Y` và ngược lại. Đây là lựa chọn phù hợp khi giá trị lưu trữ là mã nghiệp vụ ổn định như `P`, `S`, `C`, độc lập với tên hoặc thứ tự enum constants.

Ví dụ enum có mã riêng:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "P" -> PENDING;
            case "S" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown OrderStatus code: " + code);
        };
    }
}
```

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

Entity dùng converter:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
```

Database lưu `P`, `S` hoặc `C`. Việc đổi tên `PENDING` thành `WAITING` không làm thay đổi dữ liệu miễn là mã `P` tiếp tục được giữ nguyên và converter vẫn ánh xạ `P` về constant mới.

Không kết hợp `@Enumerated` và `@Convert` trên cùng một thuộc tính. Converter là cơ chế chịu trách nhiệm chuyển đổi thuộc tính đó.

### Vì sao mã ổn định hữu ích?

- Tên constant có thể thay đổi để code dễ hiểu hơn mà không cần đổi dữ liệu.
- Thứ tự khai báo enum không ảnh hưởng đến mã đã lưu.
- Mã ngắn gọn có thể giữ tương thích với hệ thống tích hợp hoặc hợp đồng dữ liệu.
- Có thể chủ động kiểm soát mã cũ, mã ngừng dùng và quy tắc chuyển đổi.

### Quy tắc thiết kế converter

1. Mỗi mã phải duy nhất và ổn định; không tái sử dụng mã đã ngừng dùng cho một ý nghĩa mới.
2. Xử lý `null` rõ ràng ở cả hai chiều.
3. Khi gặp mã không biết, quyết định chính sách có chủ đích. Ném exception giúp phát hiện dữ liệu sai; không tự động gán một trạng thái mặc định có thể che giấu lỗi.
4. Giữ độ dài cột phù hợp và thêm constraint nếu schema cần giới hạn tập mã.
5. Không đổi mã đã phát hành chỉ vì muốn đổi tên enum constant.
6. Chỉ dùng `@Converter(autoApply = true)` khi mọi thuộc tính của kiểu Java đó phải có cùng cách lưu. Với enum có nhiều cách biểu diễn, nên gắn `@Convert` tường minh trên từng field.

## 6. Chiến lược chọn cách ánh xạ

Chọn theo vòng đời dữ liệu và yêu cầu tương thích:

- **Enum nội bộ, dữ liệu tồn tại lâu dài:** ưu tiên `@Enumerated(EnumType.STRING)`.
- **Enum có mã nghiệp vụ ổn định hoặc tích hợp với hệ thống khác:** dùng `AttributeConverter`.
- **Enum kỹ thuật có thứ tự bất biến, chỉ dùng trong dữ liệu tạm hoặc vòng đời được kiểm soát:** có thể cân nhắc `ORDINAL`, nhưng phải ghi rõ annotation và có kiểm thử bảo vệ thứ tự.

Không chọn `ORDINAL` chỉ vì cột nhỏ hơn hoặc vì nghĩ enum sẽ không thay đổi. Enum thường thay đổi khi nghiệp vụ phát triển; dữ liệu database có thể sống lâu hơn nhiều phiên bản source code.

## 7. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ này lưu `OrderStatus` bằng mã ổn định qua `AttributeConverter`, rồi đọc lại qua Spring Data JPA. Dự án dùng Spring Boot 3.4.5, Java 17 và H2 in-memory database.

### Cấu trúc dự án

```text
enum-mapping/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/enummapping/
        │   ├── EnumMappingApplication.java
        │   ├── OrderStatus.java
        │   ├── OrderStatusConverter.java
        │   ├── PurchaseOrder.java
        │   └── PurchaseOrderRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>enum-mapping</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:enumdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` chỉ phù hợp với database thử nghiệm trong bộ nhớ. Production nên quản lý schema bằng Flyway hoặc Liquibase.

### `OrderStatus.java`

```java
package com.example.enummapping;

public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "P" -> PENDING;
            case "S" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown OrderStatus code: " + code);
        };
    }
}
```

### `OrderStatusConverter.java`

```java
package com.example.enummapping;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

### `PurchaseOrder.java`

```java
package com.example.enummapping;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderStatusConverter.class)
    @Column(name = "status_code", nullable = false, length = 1)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderStatus status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

### `PurchaseOrderRepository.java`

```java
package com.example.enummapping;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Spring Data JPA chuyển tham số enum của `findByStatus` qua mapping của thuộc tính. Với converter ở trên, giá trị bind xuống database là mã tương ứng.

### `EnumMappingApplication.java`

```java
package com.example.enummapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EnumMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnumMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PurchaseOrderRepository repository) {
        return args -> {
            PurchaseOrder saved = repository.saveAndFlush(
                    new PurchaseOrder(OrderStatus.PENDING));

            PurchaseOrder loaded = repository.findById(saved.getId())
                    .orElseThrow();

            System.out.println("Database code for PENDING: "
                    + loaded.getStatus().code());
            System.out.println("Loaded status: " + loaded.getStatus());
            System.out.println("PENDING orders: "
                    + repository.findByStatus(OrderStatus.PENDING).size());
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Database code for PENDING: P
Loaded status: PENDING
PENDING orders: 1
```

Trong database, cột `status_code` lưu `P`. Khi đọc entity, converter đổi `P` về `OrderStatus.PENDING`. Nếu đổi tên constant trong Java nhưng vẫn giữ mã `P`, dữ liệu đã lưu vẫn được đọc đúng.

## 8. Migration khi đổi cách ánh xạ

Đổi một field từ ORDINAL sang STRING hoặc converter là thay đổi định dạng dữ liệu, không chỉ là sửa annotation. Nếu database đã có dữ liệu, phải chuyển đổi dữ liệu có kiểm soát.

### Từ ORDINAL sang STRING

Giả sử thứ tự enum hiện tại là `PENDING(0)`, `PAID(1)`, `CANCELLED(2)` và cột cũ là số. Có thể dùng quy trình expand-and-contract:

1. Kiểm kê enum constants và xác nhận ý nghĩa của từng ordinal đang tồn tại trong dữ liệu.
2. Thêm cột chuỗi mới, ví dụ `status_text`, cho phép null tạm thời.
3. Backfill bằng mapping tường minh từ ordinal sang tên hoặc mã. Không dùng thứ tự enum của phiên bản mới nếu thứ tự đã từng thay đổi.
4. Kiểm tra số lượng bản ghi, giá trị null, giá trị không nhận diện và đối chiếu các trạng thái.
5. Triển khai ứng dụng đọc/ghi định dạng mới. Nếu có rolling deployment, thiết kế giai đoạn tương thích để phiên bản cũ và mới không ghi hai định dạng không hiểu lẫn nhau.
6. Sau khi mọi instance đã chuyển đổi và dữ liệu được xác minh, chuyển ứng dụng sang cột mới, rồi mới xóa cột cũ trong một migration riêng.

Ví dụ backfill minh họa khi đã xác nhận mapping cũ chính xác:

```sql
update purchase_orders
set status_text = case status
    when 0 then 'PENDING'
    when 1 then 'PAID'
    when 2 then 'CANCELLED'
    else null
end;
```

Không chạy nguyên câu SQL này nếu ordinal trong dữ liệu thực tế có mapping khác. Trước khi bỏ cột cũ, phải xác minh không còn hàng chưa được chuyển đổi và không có ứng dụng phiên bản cũ tiếp tục ghi vào cột cũ.

### Từ STRING sang mã converter

Quy trình tương tự: thêm cột mã, backfill tên cũ sang mã ổn định, kiểm tra dữ liệu, triển khai converter đọc/ghi cột mã, rồi mới loại bỏ cột cũ. Nếu đổi tên constant cùng lúc, cần giữ bảng ánh xạ giữa tên cũ và mã mới trong migration.

### Tương thích khi triển khai nhiều phiên bản

Trong hệ thống có nhiều instance hoặc worker, một instance mới có thể ghi giá trị mà instance cũ không hiểu. Ví dụ, phiên bản mới ghi `REFUNDED`, nhưng phiên bản cũ không có constant này. Trước khi cho phép ghi trạng thái mới, cần bảo đảm mọi consumer có thể đọc nó hoặc có chiến lược rollout tương thích.

## 9. Constraint và kiểm tra dữ liệu

Enum ở Java không tự đảm bảo database chỉ chứa giá trị hợp lệ. Dữ liệu có thể được ghi từ script, ETL, ứng dụng khác hoặc phiên bản code cũ. Nên xem xét:

- `NOT NULL` nếu trạng thái bắt buộc phải có.
- `CHECK` constraint để giới hạn tập giá trị khi schema và hệ quản trị database hỗ trợ phù hợp.
- Độ dài cột đủ chứa mọi tên hoặc mã.
- Index nếu thường xuyên lọc theo trạng thái và kế hoạch truy vấn cho thấy có lợi.
- Migration cập nhật constraint khi thêm trạng thái mới.

Ví dụ constraint cho mã ổn định:

```sql
alter table purchase_orders
add constraint chk_purchase_order_status
check (status_code in ('P', 'S', 'C'));
```

Constraint phải được cập nhật đồng bộ khi bổ sung mã mới. Nếu ứng dụng cần đọc dữ liệu từ phiên bản mới trong rollout, constraint và mọi consumer liên quan phải được triển khai theo đúng thứ tự.

## 10. Những lỗi thường gặp

1. **Để mặc định ORDINAL:** field không có `@Enumerated` hoặc converter có thể được ánh xạ theo ordinal. Hãy khai báo rõ cách lưu.
2. **Chèn enum constant vào giữa:** làm dịch ordinal phía sau và có thể biến `PAID` thành `CANCELLED` khi đọc dữ liệu cũ.
3. **Đổi tên constant khi dùng STRING:** dữ liệu cũ vẫn chứa tên cũ và không tự được đổi theo mã nguồn.
4. **Nghĩ rằng toString() quyết định dữ liệu STRING:** JPA dùng `name()`, không dùng `toString()`.
5. **Đặt độ dài cột quá ngắn:** tên enum mới có thể vượt giới hạn cột và làm INSERT/UPDATE thất bại.
6. **Kết hợp @Enumerated với @Convert trên cùng field:** hai cơ chế cùng muốn điều khiển mapping; hãy chọn một.
7. **Converter không xử lý mã lạ:** khi gặp dữ liệu cũ hoặc mã mới, việc đọc có thể thất bại. Cần định nghĩa rõ chiến lược tương thích và giám sát dữ liệu không hợp lệ.
8. **Đổi annotation mà không migration:** dữ liệu số không tự biến thành tên hoặc mã đúng; cần chuyển đổi dữ liệu trước khi code mới đọc.
9. **Tái sử dụng mã đã ngừng dùng:** bản ghi lịch sử có thể bị hiểu thành một trạng thái mới với ý nghĩa khác.

## 11. Kiểm thử mapping enum

Kiểm thử nên xác nhận cả chiều ghi và chiều đọc. Với `STRING`, xác minh database chứa đúng tên constant. Với `ORDINAL`, xác minh con số đúng với mapping đã cam kết và có kiểm thử bảo vệ thứ tự. Với converter, xác minh mỗi mã được chuyển đổi hai chiều, mã không biết bị xử lý theo chính sách đã chọn, và giá trị null được xử lý đúng.

Ví dụ kiểm thử converter bằng JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderStatusConverterTest {
    private final OrderStatusConverter converter = new OrderStatusConverter();

    @Test
    void convertsStatusToStableCode() {
        assertEquals("P", converter.convertToDatabaseColumn(OrderStatus.PENDING));
    }

    @Test
    void convertsStableCodeToStatus() {
        assertEquals(OrderStatus.PAID, converter.convertToEntityAttribute("S"));
    }

    @Test
    void rejectsUnknownCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convertToEntityAttribute("X"));
    }
}
```

Đây là unit test cho converter. Nên bổ sung integration test với database để xác nhận Hibernate thực sự ghi và đọc đúng giá trị cột, đặc biệt sau khi thay đổi mapping hoặc migration.

## 12. Quy tắc thực hành

- Ưu tiên `@Enumerated(EnumType.STRING)` cho enum nghiệp vụ thông thường cần lưu bền vững.
- Dùng `AttributeConverter` khi cần mã lưu trữ độc lập với tên constant và thứ tự khai báo.
- Tránh `ORDINAL` cho dữ liệu lâu dài hoặc có nhiều phiên bản ứng dụng cùng đọc/ghi.
- Nếu buộc dùng ordinal, giữ thứ tự bất biến, không xóa hoặc chèn giữa; kiểm thử và ghi rõ quy tắc trong code review.
- Coi đổi tên constant, đổi mã, xóa trạng thái và đổi annotation là thay đổi dữ liệu cần migration.
- Không tái sử dụng tên hoặc mã cũ cho một ý nghĩa nghiệp vụ khác.
- Triển khai thay đổi theo hướng tương thích ngược khi có nhiều instance hoặc consumer.

Điểm cốt lõi: **ORDINAL lưu vị trí nên rất nhạy với thay đổi thứ tự; STRING lưu tên nên an toàn hơn khi sắp xếp lại nhưng vẫn phụ thuộc tên constant; AttributeConverter lưu mã do ứng dụng định nghĩa nên phù hợp khi cần định danh bền vững qua nhiều lần refactor.**