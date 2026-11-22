# Tìm theo điều kiện bằng, so sánh, khoảng và thời gian trong Spring Data JPA

## Mục tiêu học tập

Sau bài này, bạn có thể viết phương thức truy vấn suy diễn từ tên (derived query method) trong `JpaRepository` để:
- Tìm bản ghi có thuộc tính **bằng / khác** một giá trị, hoặc bằng `null`.
- So sánh **lớn hơn, nhỏ hơn, có hoặc không có dấu bằng** trên số và các kiểu dữ liệu có thứ tự.
- Lọc giá trị **nằm trong một khoảng** bằng `Between` hoặc hai điều kiện biên.
- Lọc theo **ngày, thời điểm, trước / sau một mốc**, kể cả truy vấn trọn một ngày theo múi giờ.
- Kiểm tra biên mở / đóng, kiểu tham số và cách đọc tên phương thức để tránh kết quả sai.

Phạm vi bài: **Spring Data JPA – truy vấn theo tên phương thức**. Các ví dụ dựa trên trường của entity, không phải tên cột SQL.

## 1. Spring Data JPA suy diễn truy vấn từ tên như thế nào?

Khai báo một interface kế thừa `JpaRepository<Entity, Id>`; Spring Data JPA đọc các từ khóa sau `By` trong tên phương thức, xác định đường dẫn thuộc tính của entity rồi tạo truy vấn tương ứng. Bạn không phải tự viết câu SQL cho những điều kiện đơn giản này.

```java
public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByStatus(String status);
    List<PurchaseOrder> findByTotalGreaterThan(BigDecimal lowerBound);
}
```

Ý nghĩa gần tương đương:

```sql
SELECT * FROM purchase_orders WHERE status = ?;
SELECT * FROM purchase_orders WHERE total > ?;
```

Đây là **SQL minh họa ý nghĩa**; SQL thật do Hibernate/JPA provider tạo và có thể khác tên alias, cú pháp hoặc kiểu tham số. Dấu `?` đại diện cho tham số được bind, không phải ghép giá trị người dùng trực tiếp vào SQL.

Cách đọc `findByTotalGreaterThan`: `find...By` (hành động truy vấn) + `Total` (thuộc tính Java `total`) + `GreaterThan` (toán tử `>`). Tên thuộc tính phải khớp entity, kể cả chuỗi đường dẫn thuộc tính lồng nhau. Kiểu đối số phải tương thích với kiểu thuộc tính.

## 2. Điều kiện bằng, khác và NULL

Giả sử entity có thuộc tính `String status`:

| Phương thức | Ý nghĩa điều kiện |
| --- | --- |
| `findByStatus("PAID")` | `status = 'PAID'` |
| `findByStatusIs("PAID")` hoặc `findByStatusEquals("PAID")` | Cùng nghĩa với `findByStatus` |
| `findByStatusNot("PAID")` | `status <> 'PAID'` |
| `findByStatusIsNull()` | `status IS NULL` |
| `findByStatusIsNotNull()` | `status IS NOT NULL` |
| `findByStatusIgnoreCase("paid")` | So sánh chuỗi không phân biệt hoa/thường theo cách Spring Data JPA hỗ trợ |
| `findByStatusIn(Collection<String> statuses)` | `status IN (...)`; nhận danh sách giá trị cho phép |

Ví dụ chữ ký:

```java
List<PurchaseOrder> findByStatus(String status);
List<PurchaseOrder> findByStatusNot(String status);
List<PurchaseOrder> findByStatusIgnoreCase(String status);
List<PurchaseOrder> findByStatusIn(Collection<String> statuses);
```

**Lưu ý về `null`:** Với toán tử bằng (`Is` / `Equals` / không ghi toán tử), Spring Data JPA sinh `IS NULL` khi tham số bằng `null`; với `Not` và đối số `null`, sinh `IS NOT NULL`. Tuy nhiên, trong API nghiệp vụ nên dùng phương thức `IsNull` / `IsNotNull` khi muốn nói rõ ý định. Giá trị `null` **không đồng nghĩa** với “bỏ điều kiện lọc”. Với toán tử so sánh và `Between`, hãy kiểm tra tham số trước khi truy vấn; đừng dùng `null` để tùy ý vô hiệu hóa một biên.

Nếu cột được khai báo `nullable = false` như ví dụ chạy ở cuối bài, truy vấn `IsNull` vẫn hợp lệ về cú pháp nhưng thông thường không tìm thấy bản ghi.

## 3. So sánh lớn hơn, nhỏ hơn: hiểu chính xác biên

Đối với `BigDecimal total`, các từ khóa quan trọng là:

| Phương thức | Điều kiện tương đương | Có lấy giá trị tại biên? |
| --- | --- | --- |
| `findByTotalGreaterThan(x)` | `total > x` | Không |
| `findByTotalGreaterThanEqual(x)` | `total >= x` | Có |
| `findByTotalLessThan(x)` | `total < x` | Không |
| `findByTotalLessThanEqual(x)` | `total <= x` | Có |
| `findByTotalBetween(a, b)` | `total BETWEEN a AND b` | Có cả `a` và `b` |

Ví dụ tổng tiền là `80, 90, 120, 200`:
- `GreaterThan(120)` trả về `200`; `GreaterThanEqual(120)` trả về `120, 200`.
- `LessThan(90)` trả về `80`; `LessThanEqual(90)` trả về `80, 90`.
- `Between(80, 120)` trả về `80, 90, 120`. Trong SQL/JPQL, `BETWEEN` bao gồm **cả hai đầu**.
- `Between(120, 80)` không tự đảo hai đầu. Nên xác nhận `a <= b` trước khi gọi.

Dùng `BigDecimal` cho tiền hoặc số thập phân cần chính xác; tránh so sánh tiền bằng `double` nếu nghiệp vụ yêu cầu độ chính xác thập phân. Với dữ liệu số thực, kiểu dữ liệu, scale và phép làm tròn của database cũng có thể ảnh hưởng kết quả.

## 4. Lọc khoảng: đóng, mở và nửa mở

Có ba dạng phổ biến:

- **[a, b] – đóng cả hai đầu:** `findByTotalBetween(a, b)`.
- **(a, b) – mở cả hai đầu:** `findByTotalGreaterThanAndTotalLessThan(a, b)`.
- **[a, b) – gồm đầu, loại cuối:** `findByTotalGreaterThanEqualAndTotalLessThan(a, b)`.

```java
List<PurchaseOrder> findByTotalGreaterThanAndTotalLessThan(
        BigDecimal lowerExclusive, BigDecimal upperExclusive);

List<PurchaseOrder> findByTotalGreaterThanEqualAndTotalLessThan(
        BigDecimal lowerInclusive, BigDecimal upperExclusive);
```

Phần `And` nối hai điều kiện bằng logic AND. Mỗi điều kiện trên cùng một thuộc tính `total` có một tham số riêng, theo **đúng thứ tự xuất hiện** trong tên phương thức. Không có từ khóa ngắn `Gte` hoặc `Lte` tương đương trong cú pháp truy vấn suy diễn thông dụng; dùng `GreaterThanEqual` và `LessThanEqual`.

Khi tìm theo khoảng, hãy thống nhất quy tắc đầu vào: `min <= max`; quyết định liệu biên trên có lấy hay không; kiểm tra các giá trị âm, số 0 và các trường hợp ranh giới bằng nhau. Một khoảng nửa mở `[start, end)` đặc biệt hữu ích để chia dữ liệu theo các khoảng liên tiếp mà không đếm trùng thời điểm ở biên.

## 5. Điều kiện ngày và thời gian

JPA hỗ trợ ánh xạ các kiểu `java.time` phổ biến:
- `LocalDate`: **ngày theo lịch**, không có giờ và không chứa múi giờ; phù hợp ngày giao dịch, ngày sinh.
- `LocalDateTime`: ngày và giờ **không có thông tin múi giờ/offset**; cần quy ước rõ múi giờ khi gắn với một thời điểm thực.
- `Instant`: **thời điểm trên trục thời gian UTC**; phù hợp thời điểm tạo/sửa bản ghi khi hệ thống làm việc ở nhiều múi giờ.
- `OffsetDateTime`: có offset; cách lưu và so sánh cụ thể cần kiểm tra provider và kiểu cột database.

Các tên truy vấn tương ứng:

```java
List<PurchaseOrder> findByOrderDate(LocalDate day);
List<PurchaseOrder> findByOrderDateBefore(LocalDate day);
List<PurchaseOrder> findByOrderDateAfter(LocalDate day);
List<PurchaseOrder> findByOrderDateBetween(LocalDate first, LocalDate last);
List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        Instant startInclusive, Instant endExclusive);
```

`Before(x)` có nghĩa **nhỏ hơn** `x`, tương đương `<`; `After(x)` có nghĩa **lớn hơn** `x`, tương đương `>`. Cả hai đều **không lấy đúng mốc**. Nếu cần lấy mốc, dùng `LessThanEqual` hoặc `GreaterThanEqual`. Với `LocalDate`, `Between(2026-01-01, 2026-01-31)` bao gồm cả ngày 1 và ngày 31; tham số phải là `LocalDate`, không phải chuỗi định dạng tùy ý.

### Truy vấn *toàn bộ một ngày* khi cột lưu Instant

Một ngày tại Việt Nam không trùng với một ngày UTC. Muốn tìm tất cả bản ghi được tạo trong ngày `2026-01-02` theo giờ Việt Nam, hãy đổi hai **đầu ngày địa phương** thành `Instant` rồi truy vấn `[start, nextStart)`:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 1, 2);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

List<PurchaseOrder> result =
        repository.findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(start, end);
```

Nhập tương ứng `java.time.ZoneId`, `LocalDate` và `Instant`. Hai biên trên lần lượt là `2026-01-01T17:00:00Z` (bao gồm) và `2026-01-02T17:00:00Z` (không bao gồm). Dùng `day.plusDays(1).atStartOfDay(zone)` xử lý tốt cả những múi giờ có ngày dài/ngắn khác 24 giờ do đổi giờ mùa hè. Không nên dựng ngày cuối bằng `23:59:59` hoặc `23:59:59.999`: dữ liệu có thể có độ chính xác microsecond/nanosecond và bị bỏ sót. Cũng không nên dùng `Between(start, end)` để biểu diễn ngày nửa mở vì `Between` sẽ nhận cả `end`.

Nếu business muốn **ngày UTC** thay vì ngày Việt Nam, dùng mốc `2026-01-02T00:00:00Z` tới `2026-01-03T00:00:00Z`; đây là hai truy vấn có tập kết quả khác nhau. Múi giờ phải được xác định theo yêu cầu sản phẩm trước khi chuyển đổi.

## 6. Ví dụ Java 17 chạy được với Spring Boot, JPA và H2

Ví dụ là ứng dụng Maven độc lập; dùng Spring Boot `3.5.16`, Java 17, Spring Data JPA và database H2 trong bộ nhớ. Cấu trúc:

```text
derived-query-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── PurchaseOrder.java
    │   ├── PurchaseOrderRepository.java
    │   └── DemoApplication.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>derived-query-demo</artifactId>
    <version>1.0.0</version>
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

**`src/main/java/com/example/demo/PurchaseOrder.java`**

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal total;

    @Column(nullable = false)
    private LocalDate orderDate;

    @Column(nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
        // JPA yêu cầu constructor không đối số, ít nhất là protected.
    }

    public PurchaseOrder(String status, BigDecimal total,
                         LocalDate orderDate, Instant createdAt) {
        this.status = status;
        this.total = total;
        this.orderDate = orderDate;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
    public LocalDate getOrderDate() { return orderDate; }
    public Instant getCreatedAt() { return createdAt; }
}
```

**`src/main/java/com/example/demo/PurchaseOrderRepository.java`**

```java
package com.example.demo;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(String status);

    List<PurchaseOrder> findByTotalGreaterThan(BigDecimal value);

    List<PurchaseOrder> findByTotalBetween(BigDecimal min, BigDecimal max);

    List<PurchaseOrder> findByOrderDateBetween(LocalDate from, LocalDate to);

    List<PurchaseOrder> findByCreatedAtAfter(Instant instant);

    List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            Instant fromInclusive, Instant toExclusive);

    List<PurchaseOrder> findByStatusAndTotalGreaterThanEqual(
            String status, BigDecimal min);
}
```

**`src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PurchaseOrderRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                order("PAID", "120.00", "2026-01-01", "2026-01-01T00:00:00Z"),
                order("PAID", "200.00", "2026-01-02", "2026-01-02T12:00:00Z"),
                order("NEW",  "80.00", "2026-01-02", "2026-01-02T23:59:59Z"),
                order("PAID",  "90.00", "2026-01-03", "2026-01-03T00:00:00Z")
            ));

            Instant start = Instant.parse("2026-01-02T00:00:00Z");
            Instant end = Instant.parse("2026-01-03T00:00:00Z");

            System.out.println("PAID=" +
                    repository.findByStatus("PAID").size());
            System.out.println("TOTAL_GT_100=" +
                    repository.findByTotalGreaterThan(new BigDecimal("100")).size());
            System.out.println("TOTAL_80_TO_120=" +
                    repository.findByTotalBetween(
                            new BigDecimal("80"), new BigDecimal("120")).size());
            System.out.println("ORDER_DATE_JAN_2=" +
                    repository.findByOrderDateBetween(
                            LocalDate.of(2026, 1, 2),
                            LocalDate.of(2026, 1, 2)).size());
            System.out.println("UTC_DAY_JAN_2=" +
                    repository.findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                            start, end).size());
            System.out.println("AFTER_UTC_START=" +
                    repository.findByCreatedAtAfter(start).size());
            System.out.println("PAID_MIN_100=" +
                    repository.findByStatusAndTotalGreaterThanEqual(
                            "PAID", new BigDecimal("100")).size());
        };
    }

    private static PurchaseOrder order(
            String status, String total, String day, String timestamp) {
        return new PurchaseOrder(
                status,
                new BigDecimal(total),
                LocalDate.parse(day),
                Instant.parse(timestamp));
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:derived-demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
spring.jpa.show-sql=false
```

Chạy ở thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn spring-boot:run
```

Ngoài log khởi động của Spring Boot/Hibernate, ứng dụng in **đúng bảy dòng** dưới đây; thứ tự là thứ tự các lệnh `println`:

```text
PAID=3
TOTAL_GT_100=2
TOTAL_80_TO_120=3
ORDER_DATE_JAN_2=2
UTC_DAY_JAN_2=2
AFTER_UTC_START=3
PAID_MIN_100=2
```

Giải thích: tổng tiền là `120, 200, 80, 90`; khoảng `[80,120]` có 3 đơn; ngày `2026-01-02` có 2 đơn; khoảng UTC `[2026-01-02T00:00:00Z, 2026-01-03T00:00:00Z)` có 2 đơn. `After(start)` loại đúng mốc đầu nên trả 3 đơn, trong đó có đơn tại đúng `2026-01-03T00:00:00Z`. Dữ liệu chỉ lưu trong H2 memory để học và bị xóa khi ứng dụng kết thúc.

## 7. Kết hợp điều kiện, sắp xếp và phân trang

Bạn có thể ghép các điều kiện rõ ràng:

```java
List<PurchaseOrder> findByStatusAndTotalGreaterThanEqual(
        String status, BigDecimal min);

List<PurchaseOrder> findByStatusOrTotalLessThan(
        String status, BigDecimal limit);

List<PurchaseOrder> findByOrderDateBetweenOrderByTotalDesc(
        LocalDate start, LocalDate end);
```

`And`, `Or` tương ứng AND/OR; khi trộn nhiều loại, hãy kiểm tra logic ưu tiên và dùng `@Query` hoặc `Specification` nếu cần nhóm ngoặc phức tạp để người đọc không hiểu nhầm. `OrderByTotalDesc` cố định thứ tự giảm dần theo `total`.

Đối với kết quả lớn, dùng phân trang và sắp xếp theo nhu cầu:

```java
Page<PurchaseOrder> findByStatusAndOrderDateBetween(
        String status, LocalDate start, LocalDate end, Pageable pageable);
```

Ví dụ gọi (nhập thêm `org.springframework.data.domain.Page`, `PageRequest`, `Pageable`):

```java
Pageable firstPage = PageRequest.of(0, 20);
Page<PurchaseOrder> page = repository.findByStatusAndOrderDateBetween(
        "PAID", LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 1, 31), firstPage);
```

`PageRequest.of(0, 20)` lấy trang **đầu tiên** với tối đa 20 phần tử; chỉ số trang bắt đầu từ 0. Khi cần sắp xếp ổn định giữa các trang, thêm `Sort` có cột phân biệt (ví dụ `id`) hoặc phương án phân trang thích hợp.

## 8. Lỗi thường gặp và cách kiểm tra

1. **Nhầm tên cột với tên thuộc tính:** Nếu entity có `orderDate` thì dùng `findByOrderDateBetween`, không dùng tên SQL `order_date` trong tên phương thức. Tên không khớp thường làm Spring Data báo lỗi tạo query khi khởi tạo repository.
2. **Nhầm `>` với `>=` hoặc `Before` với `<=`:** Hãy thử dữ liệu nằm *đúng trên biên*, không chỉ ở giữa khoảng.
3. **Dùng `Between` cho trọn ngày của `Instant`:** `Between` nhận cả mốc cuối; ưu tiên `GreaterThanEqualAndLessThan` với đầu ngày kế tiếp.
4. **Sai múi giờ:** Ngày ở Việt Nam và ngày UTC khác nhau. Chuyển đổi bằng `ZoneId` đúng với yêu cầu nghiệp vụ trước khi so sánh thời điểm.
5. **Đưa chuỗi vào tham số ngày:** Phương thức nhận `LocalDate` / `Instant` nên chuyển đổi bằng `LocalDate.parse(...)` hoặc `Instant.parse(...)` và xử lý input không hợp lệ tại lớp biên (controller/service).
6. **Đảo đầu và cuối khoảng:** Kiểm tra `start <= end` trước khi gọi repository; không mong `Between` tự sửa khoảng.
7. **Tưởng `null` nghĩa là không lọc:** Xác định rõ có yêu cầu `IS NULL` hay cần xây truy vấn động. Với nhiều bộ lọc tùy chọn, cân nhắc `JpaSpecificationExecutor`, Criteria API hoặc `@Query` rõ ràng.
8. **Truy vấn ra quá nhiều dòng:** Dùng `Pageable` hoặc giới hạn kết quả phù hợp, chỉ lấy các trường cần thiết và tạo index cho những điều kiện/lối sắp xếp thường dùng sau khi đo truy vấn thật. Index có thể tăng chi phí ghi nên cần cân nhắc.

## 9. Tự luyện tập

Với 4 đơn hàng trong ví dụ, hãy dự đoán kết quả trước khi chạy:
- Tìm đơn `PAID` có `total <= 100`: tên phương thức nào? Có bao nhiêu đơn?
- Tìm đơn có `orderDate < 2026-01-03`: được mấy đơn?
- Lọc các bản ghi tạo trong **ngày 2026-01-02 theo giờ Việt Nam**: có trùng tập kết quả của `UTC_DAY_JAN_2` không?

Đáp án:
- `findByStatusAndTotalLessThanEqual("PAID", new BigDecimal("100"))` → **1** đơn (`90`).
- `findByOrderDateBefore(LocalDate.of(2026, 1, 3))` → **3** đơn (ngày 1/1 và hai đơn ngày 2/1).
- Khoảng giờ Việt Nam quy về UTC: `[2026-01-01T17:00:00Z, 2026-01-02T17:00:00Z)` → **1** đơn (`2026-01-02T12:00:00Z`); trong khi ngày UTC có **2** đơn.

**Ghi nhớ:** Bằng/khác dùng `Is`, `Equals`, `Not`; bất đẳng thức dùng `GreaterThan` / `LessThan` và biến thể `Equal`; `Between` là khoảng đóng; `Before` / `After` loại mốc; đối với một ngày chứa các thời điểm, thường chọn khoảng nửa mở sau khi quy đổi múi giờ.

### Tài liệu tham khảo chính thức

- Spring Data JPA – Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data – Repository query keywords: https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html
- Spring Boot 3.5 – System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
