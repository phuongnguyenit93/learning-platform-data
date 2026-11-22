# Enum, tên enum và tính tương thích khi đổi tên trong Spring Data JDBC

`enum` giúp Java biểu diễn tập giá trị hữu hạn như trạng thái đơn hàng, phương thức thanh toán hoặc loại tài khoản. Trong **Spring Data Relational JDBC**, enum còn có một vai trò quan trọng khác: giá trị của nó được chuyển đổi thành dữ liệu lưu trong **cột của cơ sở dữ liệu quan hệ**. Vì vậy, đổi tên một hằng enum trong Java có thể khiến chương trình mới không đọc được dữ liệu mà chương trình cũ đã ghi.

Ví dụ: ứng dụng ban đầu có `OrderStatus.PENDING`. Nếu database đang chứa chuỗi `'PENDING'` và lập trình viên đổi hằng Java thành `AWAITING_PAYMENT` mà không chuẩn bị tương thích, khi đọc hàng cũ, Spring Data JDBC có thể không chuyển được chuỗi `PENDING` thành enum mới. Vấn đề này đặc biệt dễ gặp ở hệ thống đã có dữ liệu production, triển khai nhiều phiên bản song song hoặc dùng một cột trạng thái chung với các hệ thống khác.

Bài học đi từ ánh xạ enum mặc định đến cách thiết kế **mã lưu trữ ổn định**, viết converter, lập kế hoạch đổi tên an toàn và xử lý dữ liệu lịch sử. Nội dung tập trung vào **Spring Data JDBC**, không sử dụng quy tắc ánh xạ của JPA để suy luận cho JDBC.

## 1. Enum trong Java: tên, giá trị hiển thị và mã lưu trữ

Giả sử có một quy trình xử lý đơn hàng:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Một hằng enum có nhiều cách biểu diễn:

~~~java
OrderStatus status = OrderStatus.PENDING;

System.out.println(status.name());       // PENDING
System.out.println(status.toString());   // PENDING nếu không override
System.out.println(status.ordinal());    // 0 trong khai báo hiện tại
~~~

**`name()`** trả về tên hằng đúng như trong mã nguồn Java. Đây là tên mang tính kỹ thuật; đổi `PENDING` thành `AWAITING_PAYMENT` cũng thay đổi kết quả `name()`.

**`toString()`** mặc định trả về cùng tên nhưng có thể được override để phục vụ giao diện hoặc log. Không nên coi `toString()` là một hợp đồng dữ liệu bền vững.

**`ordinal()`** là vị trí của hằng trong thứ tự khai báo, bắt đầu từ 0. Chèn hoặc sắp xếp lại hằng sẽ làm ordinal thay đổi. Không nên lưu ordinal làm trạng thái nghiệp vụ lâu dài khi có thể dùng một mã ổn định.

**Mã lưu trữ (`database code`)** là giá trị do ứng dụng tự quy định để ghi vào database, ví dụ `WAIT_PAY`. Mã này có thể giữ nguyên khi đổi tên Java, thay đổi câu chữ giao diện hoặc dịch ngôn ngữ.

| Khái niệm | Giá trị ví dụ | Có nên xem là hợp đồng ổn định? |
|---|---|---|
| `OrderStatus.PENDING` | Tên hằng trong source | Không, nếu lập trình viên có thể đổi tên |
| `status.name()` | `PENDING` | Chỉ khi đã chủ ý cam kết không đổi giá trị này |
| `status.toString()` | `Đang chờ thanh toán` nếu override | Không nên; thường phục vụ hiển thị |
| `status.ordinal()` | `0` | Không nên; phụ thuộc thứ tự khai báo |
| `status.databaseCode()` | `WAIT_PAY` | Có thể, nếu mã được quản lý như hợp đồng dữ liệu |

Điểm cốt lõi: **mã nguồn có thể refactor; dữ liệu trong database cần một kế hoạch tiến hóa có kiểm soát**. Hai vòng đời này không mặc nhiên đồng bộ.

## 2. Spring Data JDBC thường lưu enum như thế nào?

Với một thuộc tính enum thông thường được ánh xạ đến **cột chuỗi** như `VARCHAR`, Spring Data JDBC mặc định chuyển enum thành **tên hằng** khi ghi, và chuyển chuỗi cột về hằng enum tương ứng khi đọc.

~~~text
Java object                   Database row
-------------------           ----------------------------
OrderStatus.PENDING   ---->    status = 'PENDING'

OrderStatus.PENDING   <----    status = 'PENDING'
~~~

Đây là quy ước thuận tiện cho các enum nhỏ, nhưng tạo một liên kết ngầm giữa **tên hằng Java** và **dữ liệu đã lưu**.

### Phân biệt với JPA

Nếu đã từng dùng JPA, bạn có thể biết:

~~~java
// Cách viết của JPA, KHÔNG phải cấu hình enum của Spring Data JDBC:
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

`@Enumerated` và `EnumType` thuộc **Jakarta Persistence/JPA**. Trong bài học Spring Data JDBC, ta dùng mapping và cơ chế converter của **Spring Data**, chẳng hạn `@Table`, `@Id`, `@Column` và `@ReadingConverter` / `@WritingConverter`. Đừng thêm `@Enumerated` vào entity Spring Data JDBC rồi kỳ vọng nó điều khiển cách lưu enum.

Tương tự, không nên giả định enum sẽ tự lưu theo `ordinal()` chỉ vì có ba giá trị. Nếu muốn lưu mã số hoặc kiểu database đặc biệt, cần xác định rõ converter và kiểu cột tương ứng.

### Cột SQL và tên enum là hai thứ khác nhau

~~~java
@Column("order_status")
private OrderStatus status;
~~~

`@Column("order_status")` chỉ định **tên cột SQL**. Nó không đổi cách chuyển `PENDING` thành `'PENDING'`. Đổi tên cột và đổi tên **giá trị đang nằm trong cột** là hai bài toán khác nhau.

## 3. Thực hành ánh xạ enum mặc định với Spring Data JDBC

Ví dụ nhỏ dưới đây tạo một bảng `purchase_orders` chứa `id` và `status`. Chúng ta lưu `PENDING`, đọc ngược về Java, đổi sang `PAID` rồi xem chuỗi trong database. Ứng dụng dùng **Spring Boot + Spring Data JDBC + H2**.

### 3.1. Tạo dự án

Từ Spring Initializr, tạo dự án Maven với Java 17+ và chọn:

- **Spring Data JDBC**
- **H2 Database**

Trong `pom.xml` do Initializr tạo, các dependency chính có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Giữ phần parent, phiên bản Java và Maven plugin do Spring Initializr sinh ra. Starter Data JDBC cũng cung cấp hạ tầng Spring JDBC; ví dụ có thể dùng `JdbcTemplate` để đọc chuỗi SQL trực tiếp nhằm quan sát giá trị thực sự được ghi.

Cấu trúc tệp:

~~~text
enum-jdbc-demo/
└── src/main/
    ├── java/com/example/enumdemo/
    │   ├── EnumJdbcApplication.java
    │   ├── domain/OrderStatus.java
    │   ├── domain/PurchaseOrder.java
    │   └── repository/PurchaseOrderRepository.java
    └── resources/
        ├── application.yml
        └── schema.sql
~~~

### 3.2. Khai báo bảng SQL

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);
~~~

`status` là `VARCHAR`. Không dùng kiểu enum riêng của database trong ví dụ cơ bản; cách này giúp quan sát cơ chế chuyển chuỗi thông thường của Spring Data JDBC. Độ dài `32` chỉ là ví dụ; hệ thống thật phải chọn độ dài đủ cho giá trị lưu, hoặc dùng bộ mã ngắn và cố định.

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:enumdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Spring Boot chạy `schema.sql` khi khởi động. Database H2 trong bộ nhớ bị mất khi ứng dụng kết thúc; ở môi trường có dữ liệu tồn tại lâu dài, chính những hàng từ phiên bản cũ mới tạo ra vấn đề đổi tên enum.

### 3.3. Enum và aggregate root

Tạo `src/main/java/com/example/enumdemo/domain/OrderStatus.java`:

~~~java
package com.example.enumdemo.domain;

public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Tạo `src/main/java/com/example/enumdemo/domain/PurchaseOrder.java`:

~~~java
package com.example.enumdemo.domain;

import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(@Id Long id, OrderStatus status) {

    public PurchaseOrder {
        Objects.requireNonNull(status, "status không được null");
    }

    public static PurchaseOrder newOrder() {
        return new PurchaseOrder(null, OrderStatus.PENDING);
    }

    public PurchaseOrder markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Chỉ đơn PENDING mới được trả tiền");
        }
        return new PurchaseOrder(id, OrderStatus.PAID);
    }
}
~~~

`PurchaseOrder` là một **aggregate root** đơn giản có một bảng; `@Id` là annotation của `org.springframework.data.annotation`, còn `@Table` của `org.springframework.data.relational.core.mapping`. Record tạo đối tượng bất biến, vì vậy `markPaid()` trả về trạng thái mới có cùng ID.

### 3.4. Repository

Tạo `src/main/java/com/example/enumdemo/repository/PurchaseOrderRepository.java`:

~~~java
package com.example.enumdemo.repository;

import com.example.enumdemo.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Không phải viết SQL `INSERT`/`UPDATE` thủ công cho các thao tác CRUD này. Spring Data JDBC dựa vào mapping của `PurchaseOrder` để thực hiện.

### 3.5. Chạy và xem giá trị thực tế trong database

Tạo `src/main/java/com/example/enumdemo/EnumJdbcApplication.java`:

~~~java
package com.example.enumdemo;

import com.example.enumdemo.domain.PurchaseOrder;
import com.example.enumdemo.repository.PurchaseOrderRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class EnumJdbcApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnumJdbcApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            PurchaseOrderRepository orders,
            JdbcTemplate jdbc) {
        return args -> {
            PurchaseOrder created = orders.save(PurchaseOrder.newOrder());

            String valueInDatabase = jdbc.queryForObject(
                "SELECT status FROM purchase_orders WHERE id = ?",
                String.class,
                created.id()
            );
            System.out.println("SQL value: " + valueInDatabase);

            PurchaseOrder loaded = orders.findById(created.id())
                .orElseThrow();
            System.out.println("Java enum: " + loaded.status());

            PurchaseOrder paid = orders.save(loaded.markPaid());
            String updatedSqlValue = jdbc.queryForObject(
                "SELECT status FROM purchase_orders WHERE id = ?",
                String.class,
                paid.id()
            );
            System.out.println("SQL after update: " + updatedSqlValue);
        };
    }
}
~~~

Chạy trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Hoặc trên macOS/Linux:

~~~bash
./mvnw spring-boot:run
~~~

Kết quả nghiệp vụ dự kiến:

~~~text
SQL value: PENDING
Java enum: PENDING
SQL after update: PAID
~~~

Kết quả làm rõ: **Java enum và dữ liệu cột SQL là hai biểu diễn của cùng một trạng thái**. Với mapping mặc định vào `VARCHAR`, tên enum trở thành chuỗi trong database. `JdbcTemplate` được dùng ở đây để đọc trực tiếp cột, không thay thế repository trong quy trình nghiệp vụ.

## 4. Điều gì xảy ra khi đổi tên một hằng enum?

Giả sử sau một thời gian vận hành, đội ngũ nhận thấy `PENDING` quá chung chung, muốn dùng tên rõ nghĩa hơn là `AWAITING_PAYMENT`.

### Phiên bản trước

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Database đã có dữ liệu:

~~~text
purchase_orders
id | status
---+----------
 1 | PENDING
 2 | PAID
 3 | CANCELLED
 4 | PENDING
~~~

### Phiên bản sau khi chỉ refactor Java

~~~java
public enum OrderStatus {
    AWAITING_PAYMENT, // đổi tên từ PENDING
    PAID,
    CANCELLED
}
~~~

Khi chạy ứng dụng mới và đọc hàng có `status = 'PENDING'`, cách ánh xạ mặc định cần tìm một hằng Java tên `PENDING`. Hằng này đã không còn tồn tại. Việc chuyển đổi có thể ném ngoại lệ chuyển đổi/`IllegalArgumentException` (thường được bọc trong ngoại lệ truy cập dữ liệu hoặc ánh xạ tùy đường gọi).

~~~mermaid
flowchart LR
    A[("DB: status = 'PENDING'")] --> B["Đọc cột thành String"]
    B --> C["Chuyển String thành OrderStatus"]
    C --> D{"Enum còn PENDING?"}
    D -->|Có| E["Đọc thành công"]
    D -->|Không| F["Lỗi chuyển đổi dữ liệu"]
~~~

Đổi tên enum trong IDE chỉ cập nhật **tham chiếu Java**. IDE không tự sửa giá trị đã lưu trong database; cũng không bảo đảm các hệ thống khác, dữ liệu sao lưu, message cũ hoặc job đang chạy đều hiểu tên mới.

### Trường hợp còn phức tạp hơn khi nâng cấp nhiều instance

Xét một hệ thống có hai phiên bản chạy song song trong quá trình triển khai:

| Thành phần | Chỉ hiểu `PENDING` | Chỉ hiểu `AWAITING_PAYMENT` |
|---|---|---|
| Instance ứng dụng cũ | Có | Không |
| Instance ứng dụng mới sau refactor đơn giản | Không | Có |
| Database đang chứa `PENDING` | Đọc được ở bản cũ | Có nguy cơ lỗi ở bản mới |
| Hàng được ghi bằng `AWAITING_PAYMENT` | Có nguy cơ lỗi ở bản cũ | Đọc được ở bản mới |

Vì thế, chạy một lệnh `UPDATE` đổi toàn bộ chuỗi trong database ngay lúc ứng dụng cũ vẫn phục vụ traffic có thể tạo lỗi theo chiều ngược lại: **instance cũ không đọc được giá trị mới**. Đây là vấn đề tương thích hai chiều giữa các phiên bản, không chỉ là thao tác đổi tên đơn lẻ.

## 5. Hai chiến lược chính khi đổi tên enum

### Chiến lược A — Tiếp tục lưu `name()`, đồng bộ Java và dữ liệu SQL

Phương án này chấp nhận tên hằng Java là giá trị trong database. Khi đổi tên, phải xem đây là **thay đổi schema/data contract** và chuyển dữ liệu có kiểm soát.

Ví dụ bảng `purchase_orders` trước đó lưu `PENDING`, muốn đổi thành `AWAITING_PAYMENT`:

~~~sql
UPDATE purchase_orders
SET status = 'AWAITING_PAYMENT'
WHERE status = 'PENDING';
~~~

Lệnh này chỉ xử lý dữ liệu. Để hệ thống hoạt động, phiên bản Java, converter (nếu có), các câu query viết cố định trạng thái, constraint database và các consumer của trạng thái cũng phải tương thích.

**Phù hợp khi:** hệ thống nhỏ, có cửa sổ bảo trì hoặc kiểm soát được thứ tự nâng cấp toàn bộ ứng dụng và dữ liệu, không cần giữ tương thích khi hai phiên bản chạy song song.

**Hạn chế:** mỗi lần đổi tên hằng có thể kéo theo migration; tên Java vô tình trở thành hợp đồng giữa nhiều hệ thống. Với dữ liệu lớn hoặc môi trường triển khai liên tục, việc phối hợp phức tạp hơn.

### Chiến lược B — Tách tên Java khỏi mã lưu trong database

Phương án này định nghĩa một **mã lưu trữ cố định** cho từng trạng thái. Tên Java có thể thay đổi, nhưng chuỗi trong database vẫn giữ nguyên.

~~~text
Tên Java (có thể refactor)     Mã lưu trong database (ổn định)
--------------------------    --------------------------------
AWAITING_PAYMENT              WAIT_PAY
PAID                          PAID
CANCELLED                     CANCELLED
~~~

Nếu sau này đổi `AWAITING_PAYMENT` thành `WAITING_FOR_PAYMENT` mà vẫn giữ `WAIT_PAY`, dữ liệu lịch sử không cần cập nhật chỉ vì refactor tên hằng Java. Ta cần cung cấp converter để Spring Data JDBC sử dụng `WAIT_PAY` thay cho tên `AWAITING_PAYMENT`.

**Phù hợp khi:** database được dùng lâu dài, ứng dụng nhiều phiên bản cùng truy cập, trạng thái còn đi qua báo cáo hoặc integration, và đội ngũ muốn kiểm soát hợp đồng dữ liệu rõ ràng.

**Hạn chế:** phải viết, đăng ký và duy trì converter; mã lưu trữ phải được quy định cẩn thận vì nó trở thành hợp đồng bền vững.

## 6. Ánh xạ enum bằng mã database ổn định

Phần này tiếp tục với `PurchaseOrder` và repository đã xây dựng. Ta thay **cách biểu diễn của enum**, còn property `OrderStatus status` trong aggregate root giữ nguyên. Các đoạn mã dưới đây thuộc **một phương án thay thế** mapping mặc định; không chạy song song hai bộ enum/converter trái nhau trong cùng project.

### 6.1. Định nghĩa enum có mã cố định

Thay nội dung `OrderStatus.java` bằng:

~~~java
package com.example.enumdemo.domain;

import java.util.Arrays;

public enum OrderStatus {
    AWAITING_PAYMENT("WAIT_PAY"),
    PAID("PAID"),
    CANCELLED("CANCELLED");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return Arrays.stream(values())
            .filter(value -> value.databaseCode.equals(code))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Mã trạng thái không được hỗ trợ: " + code
            ));
    }
}
~~~

Trong ví dụ này:

- `AWAITING_PAYMENT` là tên hằng dùng trong mã Java.
- `WAIT_PAY` là mã được lưu ở database.
- `fromDatabaseCode` chuyển chuỗi database về enum; mã không nhận diện được sẽ báo lỗi rõ ràng.

**Không tự động biến mã lạ thành trạng thái mặc định**, đặc biệt với thanh toán hoặc quy trình duyệt. Nếu dữ liệu chứa mã không hợp lệ, trả sai trạng thái có thể nguy hiểm hơn việc báo lỗi và xử lý dữ liệu.

Khi chuyển từ enum cũ sang enum này, sửa các tham chiếu Java trong aggregate: `PENDING` thành `AWAITING_PAYMENT`. Ví dụ:

~~~java
public static PurchaseOrder newOrder() {
    return new PurchaseOrder(null, OrderStatus.AWAITING_PAYMENT);
}

public PurchaseOrder markPaid() {
    if (status != OrderStatus.AWAITING_PAYMENT) {
        throw new IllegalStateException(
            "Chỉ đơn chờ thanh toán mới được trả tiền");
    }
    return new PurchaseOrder(id, OrderStatus.PAID);
}
~~~

### 6.2. Converter để ghi enum thành chuỗi

Tạo `src/main/java/com/example/enumdemo/config/OrderStatusWritingConverter.java`:

~~~java
package com.example.enumdemo.config;

import com.example.enumdemo.domain.OrderStatus;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.databaseCode();
    }
}
~~~

Khi lưu `OrderStatus.AWAITING_PAYMENT`, converter trả `"WAIT_PAY"`. Annotation `@WritingConverter` nói rõ mục đích chuyển đổi của converter.

### 6.3. Converter để đọc chuỗi thành enum

Tạo `src/main/java/com/example/enumdemo/config/OrderStatusReadingConverter.java`:

~~~java
package com.example.enumdemo.config;

import com.example.enumdemo.domain.OrderStatus;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromDatabaseCode(source);
    }
}
~~~

Khi đọc cột chuỗi `WAIT_PAY`, converter trả `OrderStatus.AWAITING_PAYMENT`. Hướng chuyển đổi **đọc** và **ghi** khác nhau, nên cần khai báo cả hai nếu muốn quản lý mã lưu trữ riêng.

### 6.4. Đăng ký converter với Spring Data JDBC

Tạo `src/main/java/com/example/enumdemo/config/JdbcConversionConfig.java`:

~~~java
package com.example.enumdemo.config;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConversionConfig extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new OrderStatusWritingConverter(),
            new OrderStatusReadingConverter()
        );
    }
}
~~~

`AbstractJdbcConfiguration` cung cấp điểm mở rộng để khai báo custom converters của Spring Data JDBC. Cấu hình nằm trong package con của `com.example.enumdemo` để Spring Boot có thể phát hiện. Đây là cách đăng ký minh họa cho các phiên bản Spring Data JDBC cung cấp `userConverters()`; khi áp dụng vào dự án đang dùng phiên bản khác, cần đối chiếu API cấu hình converter của chính phiên bản đó.

**Cần lưu ý phạm vi:** cặp converter trên áp dụng cho kiểu `OrderStatus` trong các mapping phù hợp, không chỉ một property có tên `status`. Nếu nhiều bảng dùng cùng kiểu enum nhưng đòi hỏi mã khác nhau, đó có thể là dấu hiệu nên phân biệt kiểu domain hoặc dùng phương án chuyển đổi có phạm vi phù hợp hơn.

### 6.5. Dữ liệu sau khi dùng converter

Với enum mới và converter đã đăng ký:

~~~java
PurchaseOrder created = orders.save(PurchaseOrder.newOrder());
System.out.println(created.status()); // AWAITING_PAYMENT
~~~

SQL lưu dạng:

~~~text
purchase_orders
id | status
---+---------
 1 | WAIT_PAY
~~~

Khi đọc lại, Java nhận `OrderStatus.AWAITING_PAYMENT`. Đổi tên hằng Java một lần nữa sẽ không làm database thay đổi nếu vẫn giữ mã `WAIT_PAY` và logic converter.

**Chuyển sang converter không tự chuyển dữ liệu cũ.** Nếu database hiện đang có `'PENDING'` từ bản mapping mặc định, converter mới vừa viết chỉ hiểu `WAIT_PAY`, `PAID` và `CANCELLED`. Cần một giai đoạn đọc tương thích hoặc migration dữ liệu như phần tiếp theo.

## 7. Di chuyển dữ liệu cũ sang mã ổn định

Giả sử database production đang lưu:

~~~text
id | status
---+----------
 1 | PENDING
 2 | PAID
 3 | CANCELLED
~~~

Ta muốn chuyển giá trị cũ `PENDING` thành mã ổn định `WAIT_PAY`. Với môi trường có thể tạm dừng toàn bộ writer và reader, cách làm đơn giản là nâng cấp ứng dụng và chuyển dữ liệu trong một cửa sổ triển khai được kiểm soát:

~~~sql
UPDATE purchase_orders
SET status = 'WAIT_PAY'
WHERE status = 'PENDING';
~~~

Nếu database có `CHECK` constraint chỉ cho phép `PENDING`, phải cập nhật constraint trước khi ghi `WAIT_PAY`. Nếu có view, trigger, report SQL, stored procedure hoặc service khác kiểm tra chuỗi `PENDING`, các thành phần đó cũng cần được kiểm tra về hợp đồng dữ liệu.

Ở hệ thống **rolling deployment** không dừng tất cả instance, thay đổi từng bước để old/new version cùng đọc được dữ liệu trong thời gian giao nhau.

### 7.1. Giai đoạn chuyển tiếp đọc được cả hai mã

Tạm thời định nghĩa mapper chấp nhận cả `PENDING` và `WAIT_PAY` nhưng luôn biểu diễn trong Java là `AWAITING_PAYMENT`:

~~~java
public static OrderStatus fromDatabaseCode(String code) {
    return switch (code) {
        case "PENDING", "WAIT_PAY" -> AWAITING_PAYMENT;
        case "PAID" -> PAID;
        case "CANCELLED" -> CANCELLED;
        default -> throw new IllegalArgumentException(
            "Mã trạng thái không được hỗ trợ: " + code);
    };
}
~~~

Đây là **biến thể chuyển tiếp** của `fromDatabaseCode` trong `OrderStatus`, thay cho logic `Arrays.stream(...)` trước đó. Đừng đặt hai phương thức cùng chữ ký trong một class.

Chỉ thêm khả năng đọc hai mã ở instance mới **chưa đủ** để an toàn với các instance cũ. Nếu instance cũ chỉ hiểu `PENDING`, nó sẽ lỗi khi gặp `WAIT_PAY`. Vì vậy, trong giai đoạn còn instance cũ, phiên bản mới cần **tiếp tục ghi mã cũ**:

~~~java
// Chỉ dùng tạm trong giai đoạn triển khai còn instance cũ:
public String databaseCode() {
    return this == AWAITING_PAYMENT ? "PENDING" : databaseCode;
}
~~~

Đoạn trên là ý tưởng cấu hình ghi tạm để minh họa thứ tự triển khai. Trong hệ thống thật, quản lý chế độ ghi chuyển tiếp bằng cấu hình hoặc một converter versioned rõ ràng sẽ dễ vận hành hơn việc chèn logic tạm vào domain enum.

### 7.2. Trình tự expand → migrate → contract

| Giai đoạn | Phiên bản chạy | Đọc được gì? | Ghi gì? |
|---|---|---|---|
| 1. Ban đầu | Bản cũ | `PENDING` | `PENDING` |
| 2. Expand | Bản mới tương thích, triển khai dần | `PENDING` và `WAIT_PAY` | Vẫn `PENDING` |
| 3. Chuyển chế độ ghi | Chỉ còn bản đọc được cả hai | `PENDING` và `WAIT_PAY` | Bắt đầu `WAIT_PAY` |
| 4. Migrate dữ liệu | Các instance tương thích | `PENDING` và `WAIT_PAY` | `WAIT_PAY`; cập nhật hàng còn `PENDING` |
| 5. Contract | Chỉ còn phiên bản mới | `WAIT_PAY` | `WAIT_PAY` |

Chi tiết thực hiện:

1. **Expand:** triển khai khả năng đọc cả mã cũ lẫn mã mới, nhưng tiếp tục ghi mã cũ. Đảm bảo toàn bộ instance đang phục vụ đã nâng cấp trước khi thay đổi mã được ghi.
2. **Chuyển ghi:** cấu hình ứng dụng ghi `WAIT_PAY`. Từ thời điểm này, không còn instance chỉ đọc được `PENDING`.
3. **Migrate:** chuyển các hàng `PENDING` lịch sử sang `WAIT_PAY`. Kiểm tra cả batch job, retry queue và các nguồn có thể ghi mã cũ.
4. **Contract:** khi không còn mã cũ được sinh ra và mọi dữ liệu tồn tại đã chuyển xong, bỏ nhánh alias `PENDING`; thu hẹp constraint nếu cần.

Với database có nhiều bản ghi, migration có thể cần chia đợt theo khóa chính, transaction và thời điểm ít tải. Thứ tự tương thích quan trọng hơn số câu SQL. Một lần rollback ứng dụng cũng phải được thiết kế trước: nếu rollback về phiên bản chỉ hiểu `PENDING` sau khi đã ghi `WAIT_PAY`, lỗi đọc sẽ xuất hiện trở lại.

### 7.3. SQL quan sát dữ liệu trước và sau migration

Trước khi chuyển:

~~~sql
SELECT status, COUNT(*) AS total
FROM purchase_orders
GROUP BY status
ORDER BY status;
~~~

Sau khi tất cả writer đã chuyển sang mã mới và migration chạy:

~~~sql
UPDATE purchase_orders
SET status = 'WAIT_PAY'
WHERE status = 'PENDING';
~~~

Sau đó dùng lại truy vấn `GROUP BY` để xem còn mã cũ không. Việc có dữ liệu mới xuất hiện với `PENDING` sau migration cho thấy một writer hoặc job vẫn đang dùng hợp đồng cũ.

Nếu có constraint giới hạn enum ở database, thứ tự chung là: **cho phép cả hai giá trị trong giai đoạn chuyển tiếp, rồi mới loại giá trị cũ sau khi migration hoàn tất**. Cú pháp thay đổi constraint khác nhau theo H2, PostgreSQL, MySQL và các hệ quản trị khác; không áp dụng máy móc một câu `ALTER TABLE` cho mọi database.

## 8. Chọn cách lưu enum theo yêu cầu tương thích

| Cách lưu | Ví dụ cột SQL | Ưu điểm | Rủi ro khi thay đổi |
|---|---|---|---|
| Tên enum mặc định | `PENDING` | Đơn giản, dễ đọc, ít cấu hình | Đổi tên Java làm thay đổi hợp đồng dữ liệu |
| Mã chuỗi ổn định với converter | `WAIT_PAY` | Refactor Java độc lập với dữ liệu; dễ truy vấn | Cần converter, quản lý mã và migration từ dữ liệu cũ |
| Mã số nghiệp vụ cố định | `10`, `20` | Dung lượng nhỏ, mã ổn định nếu quản lý tốt | SQL/report khó hiểu; vẫn cần converter và tài liệu mapping |
| Ordinal Java | `0`, `1` | Có vẻ gọn lúc đầu | Rất dễ sai nghĩa khi sắp xếp/thêm enum |
| Kiểu enum riêng của DB | Giá trị tùy DB | Có thể ràng buộc tập giá trị ở schema | DDL migration và JDBC driver/dialect có yêu cầu riêng |

**Giá trị mã số cố định khác ordinal.** Nếu doanh nghiệp chọn `10 = WAIT_PAY`, `20 = PAID` và không thay đổi ý nghĩa các mã đó, đây là một hợp đồng được chủ ý thiết kế. `ordinal()` lại phụ thuộc thứ tự hằng trong source, nên dễ thay đổi ngoài ý muốn.

### Lưu kiểu enum riêng của PostgreSQL có giống VARCHAR?

Không nhất thiết. Ví dụ PostgreSQL hỗ trợ cột enum do người dùng định nghĩa; JDBC driver có thể biểu diễn kiểu này theo cách khác chuỗi `VARCHAR` thông thường. Khi đó có thể cần converter và cách binding tham số phù hợp với PostgreSQL, hoặc cast SQL có kiểm soát. Các ví dụ `Converter<OrderStatus, String>` ở trên dành cho **cột ký tự thông thường**. Không nên chuyển sang native enum DB chỉ vì nó có cùng từ “enum” với Java.

Chọn `VARCHAR` kèm `CHECK` constraint hoặc bảng mã tham chiếu là phương án phổ biến khi ưu tiên tính rõ ràng, khả năng migration và tính độc lập giữa Java với database. Chọn native enum cần cân nhắc migration và hỗ trợ của driver.

## 9. Những rủi ro thường bị bỏ qua

### 9.1. Đổi enum name không giống đổi nhãn hiển thị

Ứng dụng có thể cần hiện “Chờ thanh toán” bằng tiếng Việt và “Awaiting payment” bằng tiếng Anh. Không nên đặt hai chuỗi này vào `name()`. Giao diện nên map trạng thái sang nhãn hiển thị qua message resource/i18n hoặc lớp trình bày.

~~~java
String label(OrderStatus status) {
    return switch (status) {
        case AWAITING_PAYMENT -> "Chờ thanh toán";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Hàm trên chỉ để minh họa cách hiển thị; nó không phải converter để ghi database. Nhãn có thể đổi tùy sản phẩm hoặc ngôn ngữ mà không ảnh hưởng giá trị cột.

### 9.2. JSON, API và message cũng có thể phụ thuộc tên enum

Với các thư viện JSON thông dụng, giá trị enum thường được serialize thành tên hằng nếu không có cấu hình khác. Ví dụ client gửi `"PENDING"` có thể không còn tương thích khi API chỉ nhận `"AWAITING_PAYMENT"`.

**Converter Spring Data JDBC chỉ áp dụng cho lưu/đọc dữ liệu qua Spring Data JDBC.** Nó không tự thay đổi cách Jackson serialize enum, message queue mã hóa trạng thái hay các câu SQL thủ công của dịch vụ khác.

Nếu enum xuất hiện trên API công khai hoặc sự kiện, cần một hợp đồng riêng cho API/message, ví dụ mã công khai ổn định và cơ chế chuyển đổi phù hợp với serializer đang dùng. Không mặc định rằng sửa DB converter là đã sửa mọi luồng dữ liệu.

### 9.3. SQL viết tay có thể phụ thuộc giá trị cũ

~~~sql
SELECT *
FROM purchase_orders
WHERE status = 'PENDING';
~~~

Ngay cả khi repository đã dùng converter `WAIT_PAY`, câu SQL trên vẫn so sánh literal `PENDING`. Nếu lập trình viên dùng `JdbcTemplate`, view, stored procedure hoặc dashboard SQL, các vị trí ấy cần đọc từ hợp đồng dữ liệu thống nhất. Giữ một bảng thống kê mã được dùng trong hệ thống sẽ giúp tránh những khác biệt khó phát hiện.

### 9.4. Null và mã không hợp lệ phải có chiến lược

Ví dụ khai báo `status VARCHAR(32) NOT NULL` và domain yêu cầu trạng thái không được null. Điều này bảo vệ một phần tính đúng đắn. Tuy nhiên, dữ liệu có thể chứa một chuỗi không nằm trong enum, chẳng hạn `WAITING` do import lỗi.

Với converter, nên báo lỗi rõ ràng thay vì âm thầm gán `CANCELLED` hay `PENDING`. Chỉ thiết kế trạng thái `UNKNOWN` nếu sản phẩm thực sự có yêu cầu nghiệp vụ cho trạng thái đó và đã xác định cách xử lý.

Nếu cột SQL cho phép `NULL`, hãy hiểu rằng Spring Data có thể không gọi converter cho giá trị null; quy tắc xử lý null phải được xác định ở schema và domain, không nên chỉ kiểm tra trong `fromDatabaseCode`.

### 9.5. Cột có constraint và dữ liệu mới

Nếu database dùng:

~~~sql
CONSTRAINT chk_order_status
    CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
~~~

thì converter cố ghi `WAIT_PAY` sẽ bị database từ chối dù Java code biên dịch đúng. Khi mở rộng tập enum hoặc đổi mã, phải điều chỉnh constraint **theo thứ tự triển khai tương thích**. Với database native enum hoặc bảng mã tham chiếu, thao tác thay đổi sẽ khác.

### 9.6. Đổi tên và đổi ý nghĩa là hai quyết định khác nhau

Đổi `PENDING` thành `AWAITING_PAYMENT` mà ngữ nghĩa không đổi có thể dùng một mã lưu ổn định. Nhưng nếu trạng thái mới chỉ bao phủ một phần hành vi cũ (ví dụ tách `PENDING` thành `WAITING_PAYMENT` và `WAITING_APPROVAL`), **không thể chỉ đổi tên**.

Khi tách hoặc gộp trạng thái, cần xác định cách phân loại các bản ghi cũ, dữ liệu bổ trợ để suy ra trạng thái mới, cách xử lý ngoại lệ và tương thích với mã nghiệp vụ từng phiên bản. Một câu `UPDATE ... SET status = ...` chưa chắc đủ.

## 10. Checklist kỹ thuật khi sửa tên enum đã lưu vào database

| Hạng mục | Câu hỏi cần giải quyết |
|---|---|
| Kiểu cột | Là `VARCHAR`, `CHAR`, mã số hay native enum DB? |
| Ánh xạ hiện tại | Spring Data JDBC dùng tên mặc định hay converter tùy chỉnh? |
| Dữ liệu hiện có | Có những mã nào? Có giá trị lạ hoặc null không? |
| Hợp đồng ngữ nghĩa | Chỉ đổi tên hay thay đổi ý nghĩa trạng thái? |
| Phiên bản chạy song song | Bản cũ đọc được mã do bản mới ghi không? |
| Repository và DAO | Có truy vấn SQL literal, projection hoặc converter riêng không? |
| Ràng buộc database | Có `CHECK`, foreign key, trigger, index đặc thù không? |
| API / event | JSON và message có serialize enum theo tên Java không? |
| Job phụ trợ | Import/export, batch, báo cáo, scheduler có ghi mã cũ không? |
| Rollback | Nếu quay về phiên bản cũ, phiên bản đó có đọc dữ liệu mới không? |

Danh sách này phục vụ **thiết kế kế hoạch thay đổi trong một dự án thực tế**; ví dụ trong bài là để hiểu lý do của từng câu hỏi. Với hệ thống dùng nhiều ứng dụng hoặc triển khai liên tục, phần tương thích khi chạy đồng thời thường là yêu cầu quyết định thứ tự migration.

## 11. Bài tập thực hành

### Bài 1 — Quan sát mapping mặc định

1. Chạy ví dụ `OrderStatus.PENDING` với cột `VARCHAR`.
2. Dùng `JdbcTemplate` đọc trực tiếp `status` để xem `PENDING` được lưu trong database.
3. Thử đổi `PENDING` thành `AWAITING_PAYMENT` trong mã Java nhưng giữ một database có dữ liệu cũ. Quan sát điều gì xảy ra khi đọc.
4. Giải thích vì sao thay đổi này không được coi đơn thuần là refactor tên.

**Gợi ý:** H2 trong bộ nhớ mất dữ liệu khi restart. Để làm bài về dữ liệu cũ, có thể dùng H2 file database hoặc nạp sẵn một hàng `'PENDING'` bằng SQL khi chạy ứng dụng mới; tránh giả định database in-memory còn dữ liệu sau khi JVM tắt.

### Bài 2 — Ánh xạ mã ổn định

1. Thay enum bằng `AWAITING_PAYMENT("WAIT_PAY")`, `PAID("PAID")` và `CANCELLED("CANCELLED")`.
2. Tạo `@WritingConverter`, `@ReadingConverter` và đăng ký với Spring Data JDBC.
3. Lưu aggregate có trạng thái `AWAITING_PAYMENT` và xác nhận cột SQL chứa `WAIT_PAY`.
4. Đổi tên Java thành `WAITING_FOR_PAYMENT`, giữ nguyên mã `WAIT_PAY`; giải thích vì sao dữ liệu lịch sử vẫn đọc được.

### Bài 3 — Lập kế hoạch nâng cấp không dừng dịch vụ

Giả sử có ba instance ứng dụng phiên bản cũ và ba instance mới chạy luân phiên. Database chứa `PENDING`, mục tiêu là lưu `WAIT_PAY`.

Hãy mô tả thứ tự: triển khai reader hiểu cả hai mã, duy trì writer mã cũ, loại instance cũ, chuyển writer mới, migrate dữ liệu, loại alias cũ. Với mỗi giai đoạn, ghi rõ ứng dụng **đọc được gì** và **ghi gì**.

### Bài 4 — Phân biệt thay đổi ngữ nghĩa

Giả sử `PENDING` cũ bao gồm cả “chờ khách trả tiền” và “chờ nhân viên duyệt”. Phiên bản mới tách thành hai trạng thái. Hãy xác định những thông tin bổ sung cần có để phân loại hàng cũ; giải thích vì sao phép thay thế `PENDING → WAIT_PAY` cho mọi hàng có thể sai nghiệp vụ.

## 12. Tổng kết

Trong **Spring Data JDBC**, enum thường được lưu vào cột ký tự bằng **tên hằng Java** nếu dùng mapping mặc định. Điều này thuận tiện nhưng khiến việc đổi tên enum ảnh hưởng trực tiếp đến dữ liệu đã lưu: bản mới có thể không đọc được chuỗi cũ, và bản cũ có thể không đọc được chuỗi mới trong quá trình triển khai.

Khi tên enum là một phần của hợp đồng dữ liệu, phải nâng cấp Java và database theo kế hoạch tương thích. Đối với hệ thống cần tiến hóa lâu dài, **mã database ổn định kết hợp `@ReadingConverter` / `@WritingConverter`** giúp tách tên Java khỏi định dạng lưu trữ. Dù chọn cách nào, hãy coi việc thay đổi giá trị enum là **thay đổi hợp đồng dữ liệu và nghiệp vụ**: cần xét dữ liệu lịch sử, ràng buộc SQL, nhiều phiên bản chạy song song và các thành phần tích hợp khác trước khi loại bỏ giá trị cũ.
