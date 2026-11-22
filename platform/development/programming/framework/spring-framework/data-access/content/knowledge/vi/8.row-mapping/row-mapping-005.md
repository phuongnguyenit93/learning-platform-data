# RowCallbackHandler: xử lý từng hàng mà không gom toàn bộ vào bộ nhớ

> **Ngữ cảnh:** Spring Framework → JDBC → **Ánh xạ kết quả**. Bài này giải thích `org.springframework.jdbc.core.RowCallbackHandler`, cách nó được `JdbcTemplate` gọi cho **từng hàng hiện tại** của `ResultSet`, và cách thiết kế một tác vụ thống kê hoặc xuất dữ liệu để **không dựng `List` chứa toàn bộ kết quả trong bộ nhớ ứng dụng**. Quan trọng: xử lý từng hàng ở tầng Java **không tự động bảo đảm driver JDBC/DBMS tải dữ liệu theo từng đợt**; phải xem thêm phần về fetch size, transaction và đặc tính driver.

## 1. Vấn đề cần giải quyết

Giả sử bảng `sale` có vài triệu giao dịch. Yêu cầu là đọc các giao dịch đã thanh toán, tính tổng doanh thu và xuất CSV. Cách viết quen thuộc:

~~~java
// Fragment minh họa: SaleMapper và jdbc đã được định nghĩa.
List<Sale> sales = jdbc.query(
    "SELECT id, customer, amount FROM sale WHERE status = ?",
    saleMapper,
    "PAID"
);

for (Sale sale : sales) {
    // Cộng tiền hoặc ghi CSV.
}
~~~

`RowMapper<Sale>` rất hữu ích khi ứng dụng **thực sự cần danh sách các object `Sale`**. Nhưng với `query(..., RowMapper<T>)` trả `List<T>`, `JdbcTemplate` gom các object được ánh xạ trước khi trả cho bên gọi. Khi số hàng tăng, danh sách, từng object và chuỗi ký tự liên quan có thể chiếm bộ nhớ đáng kể; nếu lớn hơn khả năng heap, có nguy cơ `OutOfMemoryError`.

Nếu ứng dụng chỉ cần **xử lý từng hàng rồi bỏ trạng thái chi tiết của nó**, có thể chuyển sang `RowCallbackHandler`:

~~~java
// Fragment minh họa: sum là một accumulator có phạm vi cục bộ.
jdbc.query(
    "SELECT amount FROM sale WHERE status = ?",
    (RowCallbackHandler) rs -> sum.add(rs.getBigDecimal("amount")),
    "PAID"
);
~~~

Callback được gọi cho từng hàng; nó không trả `Sale` và `JdbcTemplate` **không xây `List<Sale>` thay cho callback**. Nếu `sum` chỉ giữ một bộ cộng dồn, dung lượng trạng thái nghiệp vụ tăng rất ít theo số hàng. Nếu callback tự `list.add(...)` cho mọi hàng thì chính nó lại tạo ra một danh sách lớn và đánh mất lợi ích trên.

**Mục tiêu đúng:** Không giữ toàn bộ hàng trong **heap ứng dụng** khi chỉ cần tổng hợp, kiểm tra, xuất từng dòng hoặc gửi đến một downstream consumer có kiểm soát. **Mục tiêu cần điều kiện bổ sung:** Không giữ toàn bộ hàng trong **buffer JDBC driver**, vì việc đó phụ thuộc cách fetch của driver và transaction.

## 2. Hợp đồng chính xác của `RowCallbackHandler`

Đây là một functional interface trong Spring JDBC:

~~~java
package org.springframework.jdbc.core;

@FunctionalInterface
public interface RowCallbackHandler {
    void processRow(java.sql.ResultSet rs)
        throws java.sql.SQLException;
}
~~~

Điều này có năm hệ quả:

1. **Nhận `ResultSet`:** `JdbcTemplate` đã điều khiển con trỏ tới hàng đang xử lý.
2. **Trả `void`:** Callback xử lý side effect hoặc cập nhật accumulator do bên ngoài sở hữu; nó không trả object cho JdbcTemplate tổng hợp.
3. **Không được gọi `rs.next()`:** JdbcTemplate đã di chuyển con trỏ giữa các hàng. Tự gọi `next()` khiến bỏ qua hàng hoặc thay đổi kỳ vọng của vòng lặp.
4. **Có thể ném `SQLException`:** Khi đọc cột JDBC xảy ra lỗi, để exception truyền ra; JdbcTemplate xử lý và dịch ngoại lệ theo cơ chế Spring.
5. **Là callback đồng bộ của thao tác query:** `jdbc.query(..., handler)` gọi handler trên đường xử lý kết quả rồi chỉ kết thúc khi đã xử lý xong hoặc xảy ra lỗi. Không phải API tự chạy bất đồng bộ.

Ví dụ nhỏ nhất để đếm hàng:

~~~java
import org.springframework.jdbc.core.RowCallbackHandler;

final long[] count = {0L};
RowCallbackHandler handler = rs -> {
    count[0]++;
};

jdbc.query("SELECT id FROM sale", handler);
System.out.println("Row count = " + count[0]);
~~~

`long[]` ở đây là một **holder cục bộ** giúp lambda cập nhật bộ đếm trong Java. Nó chỉ chứa một số, không chứa dữ liệu của các hàng. Với code production, một class accumulator rõ tên hoặc `LongAdder` khi thật sự cần concurrency thường dễ hiểu hơn; bản thân callback JDBC này không được ngầm chạy song song cho từng hàng.

**Nhớ rằng:** Nếu chỉ cần đếm tổng số hàng, truy vấn SQL `SELECT COUNT(*) FROM sale` thường hiệu quả hơn vì database trả một giá trị; callback thích hợp khi việc đếm đi kèm xử lý từng hàng mà SQL aggregate không thể thay thế dễ dàng.

## 3. `JdbcTemplate` điều phối vòng lặp như thế nào?

Hình dung thuật toán tương đương ở mức ý tưởng:

~~~java
// MÃ GIẢ giải thích cơ chế, không phải mã nguồn JdbcTemplate.
ResultSet rs = statement.executeQuery();
while (rs.next()) {
    handler.processRow(rs);
}
~~~

Lập trình viên **chỉ viết nội dung `processRow`**, không viết vòng lặp `while (rs.next())` bên trong callback. `JdbcTemplate` còn phụ trách nhiều bước thực tế mà mã giả không thể hiện: lấy Connection phù hợp với Spring transaction, tạo Statement/PreparedStatement, áp dụng setting như fetch size/timeout, xử lý và dịch SQLException, đóng ResultSet/Statement, và release connection theo ngữ cảnh.

~~~mermaid
flowchart TD
    A["Service/Repository gọi JdbcTemplate.query"] --> B["JdbcTemplate lấy Connection"]
    B --> C["Tạo và thực thi PreparedStatement"]
    C --> D["ResultSet được mở"]
    D --> E{"ResultSet còn hàng?"}
    E -- "Có" --> F["JdbcTemplate di chuyển tới hàng hiện tại"]
    F --> G["RowCallbackHandler.processRow(rs)"]
    G --> H["Chỉ giữ accumulator/output cần thiết"]
    H --> E
    E -- "Hết / lỗi" --> I["Đóng ResultSet/Statement, release Connection"]
    I --> J["query trả void hoặc ném exception"]
~~~

Giữa các lời gọi handler, dữ liệu hàng trước **không được tự động giữ trong một `List` do RowCallbackHandler tạo**. Nhưng nếu callback dùng một `ArrayList`, `Map` theo từng id, `StringBuilder` chứa toàn bộ CSV hoặc cache mọi hàng, heap vẫn tăng tuyến tính. **API cho phép cách xử lý tiết kiệm bộ nhớ; hành vi thực tế phụ thuộc code trong callback.**

### Tránh nhầm quyền sở hữu tài nguyên

Trong callback, không thực hiện `rs.close()`, `rs.next()`, `connection.commit()`, `dataSource.close()` hay thay đổi `ResultSet` theo cách phá vòng lặp. Nên lấy giá trị cột hiện tại, kiểm tra dữ liệu cần thiết, cập nhật một trạng thái nhỏ hoặc gửi kết quả đến output an toàn. JdbcTemplate dọn JDBC resource khi query kết thúc.

## 4. So sánh với RowMapper, ResultSetExtractor và Stream

| Cách làm | Callback chính | Ai điều khiển con trỏ? | Hình dạng kết quả phổ biến | Điểm mạnh | Lưu ý bộ nhớ |
| --- | --- | --- | --- | --- | --- |
| `query(..., RowMapper<T>)` | `T mapRow(ResultSet, int)` | JdbcTemplate | `List<T>` | Lấy danh sách domain/DTO gọn | `List` giữ object từng hàng |
| `query(..., RowCallbackHandler)` | `void processRow(ResultSet)` | JdbcTemplate | `void`; trạng thái do callback tự giữ | Thống kê, kiểm tra, xuất từng hàng | Có thể chỉ giữ O(1) hoặc O(batch), nếu callback không thu gom tất cả |
| `query(..., ResultSetExtractor<T>)` | `T extractData(ResultSet)` | Chính extractor | Tùy kiểu `T` | Toàn quyền xử lý một ResultSet, xây cấu trúc phức tạp | Phụ thuộc thuật toán extractor |
| `queryForStream(..., RowMapper<T>)` | Mapping trong Java Stream | Framework / Stream | `Stream<T>` | Xử lý lazy; tích hợp Stream API | Stream phải được đóng; driver có thể buffer |
| `SELECT COUNT/SUM/GROUP BY` | Không cần per-row callback | DBMS | Một/vài dòng tổng hợp | Đẩy phép tổng hợp sang database | Thường tiết kiệm dữ liệu truyền về hơn |

Nếu mỗi hàng cần trở thành một object độc lập để trả về API, `RowMapper` là lựa chọn thường thấy. Nếu chỉ cần đếm, tính tổng, kiểm tra điều kiện hoặc ghi output, `RowCallbackHandler` phù hợp. Nếu cần tự điều khiển vòng lặp, gom theo cấu trúc phân cấp hoặc xử lý đa ResultSet, cân nhắc `ResultSetExtractor`.

**Hai loại “xử lý từng hàng” khác nhau:** `RowMapper` cũng **được gọi mỗi hàng**, nhưng overload `query` trả List giữ kết quả của mọi hàng. `RowCallbackHandler` không tạo List ở lớp framework, và công việc của nó có thể giải phóng dữ liệu mỗi hàng ngay sau khi xử lý.

## 5. Những overload `JdbcTemplate.query` thường dùng

### 5.1. SQL tĩnh không có tham số

~~~java
RowCallbackHandler handler = rs -> {
    System.out.println(rs.getLong("id"));
};
jdbc.query("SELECT id FROM sale ORDER BY id", handler);
~~~

Đây là overload `void query(String sql, RowCallbackHandler rch)`. `System.out.println` chỉ nên dùng cho dữ liệu mẫu nhỏ; ghi hàng triệu dòng vào console có thể rất chậm.

### 5.2. SQL có tham số `?`

~~~java
RowCallbackHandler handler = rs -> {
    // Chỉ đọc hàng đã được định vị.
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));
};

jdbc.query(
    "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
    handler,
    "PAID"
);
~~~

Đây là overload `void query(String sql, RowCallbackHandler rch, Object... args)`. Các tham số được bind vào PreparedStatement; không nối trực tiếp status vào SQL. Hàm `consume(...)` là helper minh họa và phải được định nghĩa ở nơi dùng fragment.

### 5.3. Có `PreparedStatementSetter` để đặt fetch size

~~~java
PreparedStatementSetter setter = ps -> {
    ps.setString(1, "PAID");
    ps.setFetchSize(200);
};

RowCallbackHandler handler = rs ->
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));

jdbc.query(
    "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
    setter,
    handler
);
~~~

Đây là overload `void query(String sql, PreparedStatementSetter pss, RowCallbackHandler rch)`. `setFetchSize(200)` là một **hint/request đối với driver**, không phải cam kết nó chỉ giữ 200 hàng. Phải kiểm tra driver và transaction thực tế.

### 5.4. Cần custom cách tạo statement

Có `void query(PreparedStatementCreator psc, RowCallbackHandler rch)`:

~~~java
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "SELECT id, amount FROM sale WHERE status = ? ORDER BY id",
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY
    );
    ps.setString(1, "PAID");
    ps.setFetchSize(200);
    return ps;
};
RowCallbackHandler handler = rs ->
    consume(rs.getLong("id"), rs.getBigDecimal("amount"));

jdbc.query(creator, handler);
~~~

Creator được truyền Connection do Spring chọn; không tự lấy một connection mới để phá transaction hiện hành. Nếu SQL và tham số bình thường, ưu tiên overload đơn giản hơn.

**Đừng dùng overload trả `List<T>` rồi bỏ List** với kỳ vọng tiết kiệm heap: danh sách đã được tạo và lấp đầy trước khi lời gọi kết thúc.

## 6. Mức sử dụng bộ nhớ: phần nào được tiết kiệm?

Giả sử SELECT trả N hàng, mỗi object đã map chiếm trung bình M byte (chưa kể bộ nhớ của List, chuỗi, references, mảng nội bộ và JDBC buffer).

- **`List<Sale>`:** Phần dữ liệu giữ lại bởi Java application thường tăng xấp xỉ O(N × M).
- **`RowCallbackHandler` cộng dồn:** Nếu chỉ giữ `long count` và `BigDecimal total`, trạng thái logic của tầng ứng dụng là xấp xỉ O(1) theo N (bỏ qua kích thước số học tăng rất nhỏ khi tổng lớn).
- **`RowCallbackHandler` ghi CSV từng hàng:** Giữ một bộ đệm I/O hữu hạn và dữ liệu hàng hiện tại, thay vì dựng toàn bộ file vào một `StringBuilder`.
- **Driver JDBC:** Có thể fetch toàn bộ ResultSet vào heap trước khi Spring gọi handler; nếu vậy **bộ nhớ end-to-end vẫn có thể gần O(N)** dù callback rất gọn.
- **DBMS:** Truy vấn có `ORDER BY` hoặc join/aggregate có thể dùng bộ nhớ hoặc đĩa tạm ở phía server. `RowCallbackHandler` không tự giảm chi phí đó.

Vì thế, cách mô tả chính xác là:

> **`RowCallbackHandler` tránh việc `JdbcTemplate` tạo List chứa mọi object kết quả và cho phép xử lý ngay từng hàng. Để bảo đảm dòng dữ liệu vào JVM không bị driver buffer hết, phải cấu hình JDBC/driver thích hợp.**

Trong phép đo thật, cần nhìn **heap used, số hàng, driver fetch size, thời gian giữ connection, DB session/transaction, số byte qua mạng**, chứ không chỉ nhìn xem code có sử dụng `List` hay không.

## 7. Ví dụ chạy được: Spring Boot, H2, thống kê và xuất CSV từng hàng

Để thấy rõ lời gọi callback và tác động bộ nhớ ở tầng ứng dụng, ví dụ sau tạo 10.000 giao dịch thử nghiệm, lọc 5.000 giao dịch `PAID`, cộng doanh thu và ghi file CSV trực tiếp trong callback.

**Môi trường:** Java 21, Gradle, Spring Boot 3.3.5, Spring JDBC/HikariCP, H2. Project là ứng dụng console, không cần web server. Ví dụ H2 chứng minh **không tạo List sale ở tầng Java**, nhưng không phải chứng cứ rằng driver H2 dùng cursor streaming giống PostgreSQL/MySQL.

### 7.1. Cấu trúc file

~~~text
row-callback-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/rowcallback/
    │   ├── RowCallbackDemoApplication.java
    │   └── SaleRepository.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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

Spring Boot starter JDBC cung cấp `JdbcTemplate` được cấu hình sẵn từ DataSource. H2 được sử dụng để chạy độc lập mà không cần cài database server.

### 7.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:row_callback;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Database H2 được tạo mới khi ứng dụng khởi động trong một JVM mới. `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại dù mọi kết nối bị trả về pool tạm thời, không làm thay đổi hợp đồng của `RowCallbackHandler`.

### 7.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE sale (
    id BIGINT PRIMARY KEY,
    customer VARCHAR(60) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(16) NOT NULL
);
~~~

Bảng được tạo trống; ứng dụng Java chèn dữ liệu một lần khi chạy. Không cần thêm file `data.sql`.

### 7.5. Repository: `SaleRepository.java`

~~~java
package com.example.rowcallback;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Repository;

@Repository
public class SaleRepository {
    private final JdbcTemplate jdbc;

    public SaleRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Summary(long rows, BigDecimal total) {}

    public Summary summarize(String status) {
        Accumulator accumulator = new Accumulator();

        PreparedStatementSetter params = ps -> {
            ps.setString(1, status);
            ps.setFetchSize(200);
        };

        RowCallbackHandler handler =
            rs -> accumulator.accept(rs.getBigDecimal("amount"));

        jdbc.query(
            "SELECT amount FROM sale WHERE status = ? ORDER BY id",
            params,
            handler
        );

        return accumulator.snapshot();
    }

    public long exportCsv(String status, Path path) throws IOException {
        try (BufferedWriter writer =
                 Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {

            writer.write("id,customer,amount,status");
            writer.newLine();

            final long[] exported = {0L};

            PreparedStatementSetter params = ps -> {
                ps.setString(1, status);
                ps.setFetchSize(200);
            };

            RowCallbackHandler handler = rs -> {
                try {
                    writer.write(Long.toString(rs.getLong("id")));
                    writer.write(",");
                    writer.write(csv(rs.getString("customer")));
                    writer.write(",");
                    writer.write(
                        rs.getBigDecimal("amount").toPlainString()
                    );
                    writer.write(",");
                    writer.write(csv(rs.getString("status")));
                    writer.newLine();
                    exported[0]++;
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            };

            jdbc.query(
                "SELECT id, customer, amount, status " +
                "FROM sale WHERE status = ? ORDER BY id",
                params,
                handler
            );

            return exported[0];
        }
    }

    private static final class Accumulator {
        private long rows = 0L;
        private BigDecimal total = BigDecimal.ZERO;

        void accept(BigDecimal amount) {
            if (amount == null) {
                throw new IllegalStateException("Amount must not be NULL");
            }
            rows++;
            total = total.add(amount);
        }

        Summary snapshot() {
            return new Summary(rows, total);
        }
    }

    private static String csv(String value) {
        if (value.indexOf(',') < 0
                && value.indexOf('"') < 0
                && value.indexOf('\r') < 0
                && value.indexOf('\n') < 0) {
            return value;
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
~~~

**Phân tích mã:**

- `Accumulator` giữ đúng hai trường `rows` và `total`, không giữ danh sách hóa đơn. Phương thức `snapshot()` chỉ chạy sau khi `JdbcTemplate.query` hoàn tất.
- `PreparedStatementSetter` bind status và đặt fetch size. Mỗi query tạo một setter và handler cục bộ, không chia sẻ accumulator giữa các request.
- `RowCallbackHandler` chỉ đọc các cột **của hàng hiện tại**. Không có `rs.next()`, `List<Sale>`, `readAllBytes()` hay `StringBuilder` chứa toàn bộ CSV.
- `BufferedWriter` ghi từng hàng ra file. Writer có buffer nhỏ hữu hạn, được đóng bởi `try-with-resources` sau khi query kết thúc.
- `IOException` là checked exception không nằm trong chữ ký `processRow`; vì vậy callback chuyển lỗi ghi file thành `UncheckedIOException` để dừng query và truyền thất bại ra caller. `SQLException` khi đọc ResultSet vẫn được phép ném trực tiếp.
- Hàm `csv` escape dấu phẩy, dấu ngoặc kép và xuống dòng theo cú pháp CSV thông dụng. Với dữ liệu thực, nên cân nhắc thư viện CSV đã kiểm thử và chính sách chống CSV formula injection khi file dành cho spreadsheet, cùng encoding/chính sách quoting.
- `Path` được caller cung cấp; việc bảo đảm thư mục tồn tại, phân quyền và file tạm/an toàn khi ghi thất bại là chính sách của ứng dụng.

### 7.6. Ứng dụng chạy: `RowCallbackDemoApplication.java`

~~~java
package com.example.rowcallback;

import java.io.BufferedReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RowCallbackDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RowCallbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(JdbcTemplate jdbc, SaleRepository sales) {
        return args -> {
            seed(jdbc);

            SaleRepository.Summary summary = sales.summarize("PAID");
            System.out.println("Paid rows = " + summary.rows());
            System.out.println("Paid total = " + summary.total());

            Path csvFile = Path.of("sales-export.csv");
            long exported = sales.exportCsv("PAID", csvFile);
            System.out.println("Exported rows = " + exported);

            try (BufferedReader reader = Files.newBufferedReader(
                    csvFile, StandardCharsets.UTF_8)) {
                reader.readLine(); // Bỏ dòng tiêu đề.
                System.out.println(
                    "First exported row = " + reader.readLine()
                );
            }
        };
    }

    private static void seed(JdbcTemplate jdbc) {
        jdbc.batchUpdate(
            "INSERT INTO sale (id, customer, amount, status) " +
            "VALUES (?, ?, ?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int index)
                        throws SQLException {
                    int id = index + 1;
                    ps.setLong(1, id);
                    ps.setString(2, "C-" + id);
                    ps.setBigDecimal(3, BigDecimal.valueOf(id, 2));
                    ps.setString(
                        4, id % 2 == 0 ? "PAID" : "PENDING"
                    );
                }

                @Override
                public int getBatchSize() {
                    return 10_000;
                }
            }
        );
    }
}
~~~

**Tại sao seed dùng `batchUpdate`?** Đây là **pha tạo dữ liệu demo**, không phải phần xử lý kết quả. Nó tránh viết 10.000 câu INSERT bằng tay. Pha đọc dữ liệu sau đó không tạo danh sách Java chứa 5.000 hàng đã thanh toán. Trong hệ thống thực, việc nạp dữ liệu, index, batch size và transaction nên được thiết kế phù hợp tải.

### 7.7. Chạy và kết quả dự kiến

Tại thư mục có `build.gradle`, dùng Gradle Wrapper nếu đã có:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell: `.\gradlew.bat bootRun`; nếu không có wrapper nhưng đã cài Gradle tương thích: `gradle bootRun`. Cần Java 21 (hoặc Gradle toolchain được cấp Java 21). Khi ứng dụng chạy, bỏ qua log khởi động Spring, HikariCP và Gradle, các dòng **do code demo chủ động in** là:

~~~text
Paid rows = 5000
Paid total = 250050.00
Exported rows = 5000
First exported row = 2,C-2,0.02,PAID
~~~

Giải thích phép tính độc lập với runtime:

- Có 10.000 bản ghi `id = 1..10000`.
- Mọi id chẵn được gắn `status = 'PAID'` ⇒ 5.000 hàng.
- `amount` của id `i` là `i / 100` với hai chữ số thập phân.
- Tổng của id chẵn `2 + 4 + ... + 10000 = 5000 × 5001 = 25,005,000`; chia 100 được `250050.00`.
- Hàng PAID đầu tiên khi sắp xếp `ORDER BY id` là id 2, customer `C-2`, amount `0.02`.
- File `sales-export.csv` gồm một dòng header và 5.000 dòng dữ liệu. Không có bước giữ tất cả 5.000 dòng trong một list hoặc chuỗi lớn trước khi ghi.

**Giới hạn kiểm chứng:** Code cho thấy callback xử lý từng hàng ở tầng Java; **không chứng minh** H2 hoặc mọi JDBC driver chỉ buffer 200 hàng. `setFetchSize(200)` có thể được driver áp dụng, thay đổi hoặc bỏ qua. Để đánh giá end-to-end streaming, cần chạy trên database/driver thật với số hàng lớn và đo heap, network, thời gian transaction.

## 8. Khi nào thực sự đọc theo từng đợt qua JDBC?

Đây là khác biệt quan trọng nhất của chủ đề. `RowCallbackHandler` giải quyết **cách ứng dụng tiêu thụ ResultSet**. Việc driver **truyền kết quả theo đợt** là vấn đề khác. Nhiều JDBC driver mặc định lấy toàn bộ kết quả về trước. Chỉ chuyển `List` sang callback chưa đủ để bảo đảm không xuất hiện OOM tại driver khi dữ liệu rất lớn.

### 8.1. Fetch size là gợi ý, không phải giới hạn cứng

Một cách cấu hình:

~~~java
jdbcTemplate.setFetchSize(500);
~~~

Cách này áp dụng cấu hình trên `JdbcTemplate` dùng chung, do đó có thể ảnh hưởng nhiều truy vấn. Có thể cấu hình cho **statement riêng** qua `PreparedStatementSetter`:

~~~java
PreparedStatementSetter pss = ps -> {
    ps.setString(1, "PAID");
    ps.setFetchSize(500);
};
RowCallbackHandler handler = rs -> {
    processOneRow(rs); // Helper do ứng dụng định nghĩa.
};
jdbcTemplate.query(
    "SELECT id, amount FROM sale WHERE status = ?",
    pss,
    handler
);
~~~

`Statement.setFetchSize(int)` là hướng dẫn JDBC về kích thước fetch. Một số driver chỉ hỗ trợ ở chế độ cursor, một số chuyển toàn bộ dữ liệu trước khi callback chạy. Không mô tả `setFetchSize(500)` như bằng chứng chắc chắn heap dùng tối đa 500 hàng; còn có metadata, network buffers, ResultSet objects và dữ liệu đang xử lý.

### 8.2. PostgreSQL (pgJDBC): transaction + forward-only + fetchSize

Theo hướng dẫn pgJDBC, driver có thể dùng cursor-backed ResultSet khi thỏa điều kiện:

- `Connection` **không ở autocommit mode**; backend cần cursor tồn tại trong một transaction.
- Statement có loại ResultSet forward-only (`TYPE_FORWARD_ONLY`, thường là mặc định).
- Câu truy vấn phù hợp chế độ cursor theo quy định của driver, thường là **một SQL statement**.
- Fetch size dương, ví dụ `setFetchSize(500)`.

Ở Spring Boot/Spring JDBC, thường đặt transaction read-only ở **public Service method** được gọi qua Spring proxy, sử dụng cùng DataSource/transaction manager với JdbcTemplate:

~~~java
// Fragment kiến trúc — service/repository phải là Spring beans thật.
@Service
public class ReportService {
    private final SaleRepository sales;

    public ReportService(SaleRepository sales) {
        this.sales = sales;
    }

    @Transactional(readOnly = true)
    public void generateReport(Path destination) throws IOException {
        sales.exportCsv("PAID", destination);
    }
}
~~~

Cần import `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `java.nio.file.Path`, `java.io.IOException`. Đây là **fragment minh họa PostgreSQL**, không thay đổi chương trình chạy với H2 ở phần 7. `readOnly=true` là một chỉ dẫn/hint tối ưu và chính sách giao dịch; cơ chế transaction khi method chạy qua proxy mới là yếu tố giúp connection không autocommit theo transaction manager cấu hình phù hợp.

**Cảnh báo transaction kéo dài:** Nếu xuất hàng triệu dòng ra một file chậm trên cùng thread, query và transaction mở cho đến khi callback xong; connection bị chiếm lâu, có thể ảnh hưởng MVCC snapshot, timeout, vacuum/locking tùy DB. Khi đó, **keyset pagination có giới hạn kích thước mỗi trang** có thể đáng tin cậy hơn về tài nguyên và khả năng khôi phục.

### 8.3. MySQL Connector/J: đặc tính streaming theo driver

MySQL Connector/J có các chế độ riêng. Tài liệu driver mô tả chế độ forward-only, read-only với `setFetchSize(Integer.MIN_VALUE)` để yêu cầu streaming row-by-row, hoặc chế độ cursor-based fetch khi cấu hình `useCursorFetch=true` và đặt fetch size dương. Các lựa chọn này **không nên bê nguyên sang PostgreSQL/H2**. Khi đang stream kết quả, việc thực thi truy vấn khác trên **cùng Connection** có thể bị hạn chế cho tới khi đã đọc hết hoặc đóng ResultSet.

Vì vậy, lựa chọn driver/database quyết định cấu hình chi tiết. Hãy đọc tài liệu bản driver đang chạy và thử tải thật; không thiết kế một “fetch size thần kỳ” duy nhất cho tất cả.

### 8.4. H2 và các database nhúng

H2 thuận tiện cho bài học vì không cần container DB ngoài, nhưng thử nghiệm thành công với 10.000 hàng **không đủ** để kết luận cách pgJDBC/MySQL đưa các hàng về mạng. H2 chạy nhúng và không tái hiện hoàn toàn độ trễ mạng, cursor, pool contention, MVCC và đặc tính transaction của production database.

## 9. Biến callback thành bộ xử lý trạng thái nhỏ

`RowCallbackHandler` theo tài liệu Spring **thường có trạng thái** (stateful), vì nó có thể giữ kết quả tổng hợp để đọc sau khi query hoàn tất. Nhưng **stateful không đồng nghĩa tích lũy cả dữ liệu**.

### 9.1. Đếm và tính tổng

~~~java
final class RevenueCounter implements RowCallbackHandler {
    private long rows;
    private BigDecimal revenue = BigDecimal.ZERO;

    @Override
    public void processRow(ResultSet rs) throws SQLException {
        rows++;
        revenue = revenue.add(rs.getBigDecimal("amount"));
    }

    public long rows() {
        return rows;
    }

    public BigDecimal revenue() {
        return revenue;
    }
}

// Sử dụng:
RevenueCounter counter = new RevenueCounter();
jdbc.query("SELECT amount FROM sale", counter);
// Đọc counter.rows()/counter.revenue() khi query hoàn tất.
~~~

Đây là **fragment cần import** `ResultSet`, `SQLException`, `BigDecimal`, `RowCallbackHandler` và khai báo biến `jdbc`. Nên tạo **một instance counter cho mỗi query**, không đăng ký một `@Component singleton` mutable rồi dùng chung cho mọi request, vì kết quả có thể trộn giữa các lượt gọi và gây race condition.

### 9.2. Xử lý mỗi hàng và không giữ lịch sử

~~~java
RowCallbackHandler handler = rs -> {
    long id = rs.getLong("id");
    BigDecimal amount = rs.getBigDecimal("amount");
    verify(id, amount); // Kiểm tra một hàng, không cache toàn bộ.
};
jdbc.query("SELECT id, amount FROM sale", handler);
~~~

`verify(...)` có thể ghi log bất thường, tăng một bộ đếm, hoặc ném exception khi thấy dữ liệu sai. Nếu callback gọi một external API/network quá chậm cho **mỗi hàng**, connection JDBC sẽ bị giữ mở lâu; tránh đưa hoạt động I/O chậm hoặc gọi cùng lúc đến nhiều service vào callback mà chưa có thiết kế timeout/backpressure.

### 9.3. Ghi file theo dòng

Với file output:

- Mở `BufferedWriter` **bên ngoài** callback.
- Trong callback chỉ ghi dữ liệu hàng hiện tại.
- Dùng `try-with-resources` để đóng Writer.
- Bọc `IOException` thành `UncheckedIOException` hoặc truyền qua cơ chế lỗi phù hợp.
- Nếu file phải được coi là “thành công hoặc không xuất hiện”, ghi vào file tạm, chỉ rename/move tới tên cuối khi query hoàn thành. Cần quyết định cách dọn file tạm khi lỗi và chính sách atomic move do filesystem hỗ trợ.

**Không dùng `StringWriter`, `ByteArrayOutputStream` hay `StringBuilder` để gom cả CSV rồi mới viết file** khi yêu cầu là tiết kiệm bộ nhớ.

## 10. Phân biệt `RowCallbackHandler` với `ResultSetExtractor`

Một `ResultSetExtractor<T>` có method:

~~~java
T extractData(ResultSet rs) throws SQLException;
~~~

Nó nhận **cả ResultSet** và tự điều khiển vòng lặp. Ví dụ:

~~~java
Long totalRows = jdbc.query(
    "SELECT id FROM sale",
    (ResultSetExtractor<Long>) rs -> {
        long rows = 0L;
        while (rs.next()) {
            rows++;
        }
        return rows;
    }
);
~~~

Extractor có quyền trả một kết quả bất kỳ `T`, bao gồm summary. Với RowCallbackHandler, `JdbcTemplate` phụ trách `rs.next()` và method `query` trả `void`, còn kết quả được lưu trong accumulator bên ngoài hoặc output side effect.

**Khi cần dừng sớm:** RowCallbackHandler không có `return false` để yêu cầu JDBC dừng vòng lặp. Nếu chỉ cần N hàng, tốt hơn dùng SQL `LIMIT`/`FETCH FIRST` hoặc phân trang đúng dialect; nếu cần điều khiển đọc phức tạp, `ResultSetExtractor` cho phép tự dùng `while(rs.next())` và `break` theo quy tắc của mình. Ném exception chỉ để dừng sau N hàng thường khiến mã khó hiểu và có thể bị xử lý như lỗi giao dịch.

## 11. Tránh nhầm với `RowMapper` và `RowCountCallbackHandler`

### `RowMapper`: ánh xạ một hàng thành một đối tượng

~~~java
RowMapper<Sale> mapper = (rs, rowNum) -> new Sale(
    rs.getLong("id"),
    rs.getBigDecimal("amount")
);

List<Sale> sales = jdbc.query(
    "SELECT id, amount FROM sale ORDER BY id",
    mapper
);
~~~

`RowMapper.mapRow` cũng không được gọi `rs.next()`, và đối số `rowNum` được framework cung cấp. Điểm khác là `mapRow` trả một object; `JdbcTemplate.query(..., RowMapper)` thu gom các object vào List. Đây vẫn là API đúng khi result set nhỏ hoặc caller thật sự cần mọi object.

### `RowCountCallbackHandler`: class có sẵn

Spring có `RowCountCallbackHandler`, một implementation `RowCallbackHandler` giúp đếm hàng và xem metadata về cột. Ví dụ:

~~~java
RowCountCallbackHandler count = new RowCountCallbackHandler();
jdbc.query("SELECT id, amount FROM sale", count);
System.out.println(count.getRowCount());
~~~

Tài liệu Spring mô tả instance của `RowCountCallbackHandler` **dùng cho một lần query**; không tái sử dụng instance cũ như bean singleton cho nhiều query. Trong ứng dụng thật, `SELECT COUNT(*)` thường tốt hơn nếu chỉ cần số lượng, vì database tự tính mà không cần truyền từng hàng.

### `queryForStream` có phải thay thế hoàn toàn không?

`JdbcTemplate.queryForStream(...)` cung cấp Stream có thể xử lý theo từng phần tử, nhưng **cần đóng stream**:

~~~java
try (Stream<Sale> stream = jdbc.queryForStream(
        "SELECT id, amount FROM sale",
        (rs, rowNum) -> new Sale(
            rs.getLong("id"),
            rs.getBigDecimal("amount")
        )
)) {
    stream.forEach(sale -> process(sale));
}
~~~

Fragment này cần import `Stream` và định nghĩa `Sale/process`. `Stream` là lazy ở API Java, nhưng driver vẫn có thể buffer và connection vẫn cần sống tới khi đọc xong. `RowCallbackHandler` dễ dùng khi tất cả xử lý nằm ngay trong lời gọi `query`; `queryForStream` hữu ích khi cần tổ hợp thao tác Stream nhưng yêu cầu lifecycle chặt chẽ.

## 12. Giao dịch, timeout và nhất quán dữ liệu

Duyệt ResultSet lớn có thể giữ một Connection trong thời gian dài. Nếu gọi callback trong transaction Spring, query sử dụng Connection gắn với transaction hiện tại. Một số lựa chọn cần xác định:

1. **Phạm vi transaction:** SQL truy vấn trên PostgreSQL cursor-based fetch cần transaction phù hợp. Chọn `@Transactional(readOnly=true)` cho một public Service method nếu phù hợp, nhưng cần xác nhận method được gọi qua Spring proxy và transaction manager đúng DataSource.
2. **Timeout:** Đặt timeout cho query/transaction và tổng thời gian xuất báo cáo; nếu Writer chậm, query không tự được giải phóng sớm.
3. **Isolation:** Dữ liệu có thể thay đổi trong khi truy vấn dài đang chạy; mức isolation và snapshot semantics ảnh hưởng “báo cáo nhất quán” theo DBMS.
4. **Connection pool:** Nếu chạy 100 job xuất CSV song song trên pool size 10, có thể cạn kết nối cho request giao dịch quan trọng. Giới hạn concurrency của export jobs.
5. **Lỗi giữa chừng:** Nếu callback thất bại ở hàng thứ 4.000, JDBC resources được đóng/release; tuy nhiên file đã ghi 3.999 hàng **không tự rollback** theo transaction database.
6. **Retry:** Nếu chạy lại job, chọn file mới/tạm, idempotency key, checkpoint hoặc cách ghi nhận job progress; không tự động append lặp vào file thành công cũ.

**Không mở một query JDBC mới dùng cùng Connection từ bên trong callback** nếu driver đang streaming và chưa tiêu thụ hết ResultSet hiện tại. Trên một số driver, nested query có thể lỗi, buộc buffer hoặc ảnh hưởng cursor. Thiết kế tốt hơn là chỉ xử lý thông tin đã SELECT được, hoặc chia thành các bước rõ ràng.

## 13. Nếu callback xuất dữ liệu ra hệ thống ngoài: backpressure

Ghi file cục bộ bằng `BufferedWriter` thường có buffer hữu hạn, nhưng network output, Kafka, REST API hoặc object storage có thể chậm hơn tốc độ đọc DB. Nếu callback cứ đưa mỗi hàng vào một **unbounded queue**, queue sẽ giữ toàn bộ dữ liệu trong heap và mất lợi ích không gom kết quả.

Các phương án thiết kế tùy yêu cầu:

- **Đồng bộ trong callback:** Đọc một hàng → ghi một hàng. Đơn giản, ít bộ nhớ, nhưng giữ JDBC Connection trong lúc ghi và có nguy cơ timeout.
- **Bounded queue:** Producer JDBC chỉ được đưa vào queue với sức chứa hữu hạn; consumer xử lý output. Cần backpressure, cancellation, phối hợp exception và lifecycle thread; không có tự động hỗ trợ chỉ vì dùng RowCallbackHandler.
- **Micro-batch với giới hạn rõ:** Gom tối đa B hàng rồi ghi một batch, sau đó `clear()`. Heap xấp xỉ O(B × M), không phải O(N × M).
- **Keyset pagination:** Mỗi lượt SELECT lấy tối đa B hàng, đóng ResultSet/Connection rồi xử lý output. Tăng overhead query nhưng có checkpoint, giảm thời gian giữ connection và hỗ trợ retry/resume tốt hơn.

**Ví dụ micro-batch dạng fragment:**

~~~java
List<SummaryLine> batch = new ArrayList<>(500);

RowCallbackHandler handler = rs -> {
    batch.add(new SummaryLine(
        rs.getLong("id"),
        rs.getBigDecimal("amount")
    ));
    if (batch.size() >= 500) {
        flushBatch(batch); // Phải xử lý xong dữ liệu trong batch.
        batch.clear();     // Không giữ lại tham chiếu đến mọi hàng.
    }
};

jdbc.query("SELECT id, amount FROM sale ORDER BY id", handler);
if (!batch.isEmpty()) {
    flushBatch(batch);
    batch.clear();
}
~~~

Đây là fragment cần class `SummaryLine`, hàm `flushBatch` và import được định nghĩa. Trạng thái chỉ bounded nếu `flushBatch` không âm thầm giữ tất cả các batch ở nơi khác. Đặc biệt, không coi `batch.clear()` là an toàn nếu consumer bất đồng bộ vẫn tham chiếu chính danh sách đó: cần ownership rõ hoặc sao chép batch với giới hạn bộ nhớ có kiểm soát.

## 14. Lựa chọn SQL tốt trước khi xử lý trong Java

Có những yêu cầu không cần đọc từng hàng vào ứng dụng:

| Nhu cầu | Ưu tiên | Tại sao |
| --- | --- | --- |
| Đếm hàng theo trạng thái | `SELECT COUNT(*) ... WHERE ...` | DB trả một số thay vì N hàng |
| Tổng doanh thu | `SELECT SUM(amount) ...` | DB tổng hợp trước khi truyền |
| Tổng theo tháng/khách hàng | `GROUP BY` phù hợp | Giảm lượng dữ liệu qua mạng |
| Xuất tất cả dòng sang CSV với định dạng phức tạp | `RowCallbackHandler` + Writer | Cần đi qua từng dòng và tránh `List` lớn |
| Phát hiện hàng sai theo chính sách Java | `RowCallbackHandler` | Logic Java có thể xử lý/ghi nhận ngay |
| Màn hình phân trang | `LIMIT/OFFSET` hoặc keyset pagination | Không nên fetch mọi hàng rồi mới `subList` |
| Tính toán phân tích rất lớn | SQL analytics/DB ETL phù hợp | Tránh tải toàn bộ dữ liệu sang JVM nếu database có thể xử lý |

Khi cần `ORDER BY id` để xuất theo thứ tự xác định, query phải có một thứ tự ổn định, đồng thời nên có index hỗ trợ filter/order. `RowCallbackHandler` không thay thế SQL tốt; query vẫn phải dùng các cột cần thiết, điều kiện WHERE phù hợp, tránh `SELECT *` khi không cần.

### Offset pagination không phải lúc nào là lựa chọn tốt

Với dữ liệu lớn hoặc dữ liệu biến động, `OFFSET` rất xa có thể tốn chi phí và gặp rủi ro trùng/bỏ hàng nếu các bản ghi liên tục thay đổi. Keyset pagination dạng `WHERE id > :lastId ORDER BY id LIMIT :limit` thường có lợi cho thứ tự theo khóa duy nhất đã index. Nhưng yêu cầu snapshot nhất quán giữa các trang cần thiết kế isolation hoặc mốc dữ liệu phù hợp; keyset không tự bảo đảm một snapshot duy nhất.

## 15. Xử lý exception và file xuất chưa hoàn tất

Bên trong `processRow(ResultSet)`:

- `SQLException` từ `rs.getXxx()`: cứ để ném ra; `JdbcTemplate` chịu trách nhiệm xử lý/dịch lỗi SQL và cleanup.
- `IOException` từ Writer: chuyển sang unchecked error rõ ngữ nghĩa, ví dụ `UncheckedIOException`, rồi để query kết thúc thất bại.
- `RuntimeException` do vi phạm dữ liệu hoặc lỗi nghiệp vụ: không nuốt rồi ghi tiếp nếu làm output không còn đáng tin.
- Cần kiểm soát side effect đã xảy ra: DB transaction rollback **không thể đảo ngược file, email hoặc network message**.

Ví dụ chiến lược file tạm (fragment kiến trúc):

~~~java
Path temp = Files.createTempFile("sale-export-", ".part");
boolean published = false;
try {
    repository.exportCsv("PAID", temp);
    // Kiểm tra nội dung/metadata nếu cần.
    Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
    published = true;
} finally {
    if (!published) {
        Files.deleteIfExists(temp);
    }
}
~~~

Đây không phải atomic-publish tuyệt đối; nếu cần atomic rename có thể dùng `StandardCopyOption.ATOMIC_MOVE` khi filesystem hỗ trợ, cần fallback và hiểu giới hạn của move xuyên filesystem. Tạo temp **cùng filesystem/thư mục đích** thường giúp tăng khả năng move an toàn. Nên phân biệt lỗi DB, lỗi I/O, bị hủy và lỗi nghiệp vụ khi báo trạng thái export.

## 16. Kiểm tra bằng integration test và đo heap

Một unit test của handler có thể sử dụng mock `ResultSet` cho một vài hàng, nhưng **không chứng minh** cách `JdbcTemplate` lấy Connection, fetch size hay rollback. Những điều đó cần integration test.

**Gợi ý bộ test thiết yếu:**

1. **Kết quả đúng:** Với 10 hàng known data, accumulator cho đúng count và total; CSV đúng header, số hàng và thứ tự.
2. **ResultSet rỗng:** Query không có hàng vẫn trả accumulator count 0, sum theo chính sách (ví dụ BigDecimal.ZERO); file chỉ có header.
3. **Null và kiểu dữ liệu:** Nếu schema cho phép NULL, xác định chính sách `rs.getBigDecimal` trả null, `rs.getLong` có thể trả 0 cho SQL NULL và phải dùng `rs.wasNull()` nếu cần phân biệt.
4. **SQLException:** Cột sai/SQL sai phải được báo đúng; không để connection leak.
5. **IOException:** Ghi file thất bại giữa chừng; JDBC được dọn và không publish file tạm.
6. **Concurrency:** Hai job cùng dùng repository không chia sẻ một accumulator mutable bean singleton.
7. **Driver streaming thật:** Chạy nhiều hàng trên pgJDBC/MySQL với cấu hình driver đúng; đo heap trong lúc query, không chỉ sau khi query trả.
8. **Transaction/timeout:** Xuất report dài trong transaction có chính sách timeout phù hợp, không giữ connection quá lâu ngoài ý muốn.

### Đo lường có ý nghĩa

Để kiểm tra bài toán “không gom toàn bộ vào bộ nhớ”, hãy đo peak heap khi số hàng tăng (ví dụ 10k → 100k → 1M) trên cùng kiểu dữ liệu. Nếu JDBC buffering đã được cấu hình đúng, callback giữ trạng thái giới hạn sẽ có profile ứng dụng khác với `List<Sale>`. Nếu peak heap vẫn tăng mạnh, kiểm tra: driver có tải toàn bộ ResultSet không, trong callback có queue/list/map tăng theo N không, Writer có dùng `StringWriter` không, logging có giữ message không, và có cache ở ORM/persistence context không.

**Không lấy mỗi phép đo thành công ở H2 làm bằng chứng production streaming.** Dùng DB engine và JDBC driver thực tế, kèm transaction, fetch size và các cấu hình mạng/pool tương ứng.

## 17. Lỗi thường gặp và cách sửa

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Gọi `rs.next()` trong `processRow` | Bỏ qua hàng hoặc phá vòng lặp do JdbcTemplate quản lý | Chỉ đọc hàng hiện tại; để JdbcTemplate dịch chuyển |
| Gọi `jdbc.query(..., RowMapper)` rồi bỏ `List` | List vẫn đã được tạo trong heap | Dùng RowCallbackHandler khi không cần kết quả tổng hợp kiểu List |
| Trong handler gọi `allRows.add(...)` vô hạn | Heap tăng O(N) như trước | Dùng accumulator, Writer hoặc batch giới hạn |
| Nghĩ `RowCallbackHandler` tự bảo đảm network streaming | Driver có thể buffer toàn bộ kết quả | Xác minh fetch size, transaction, driver |
| Chỉ đặt `setFetchSize` dương cho pgJDBC nhưng autocommit vẫn bật | Cursor mode không hoạt động theo điều kiện driver | Dùng transaction phù hợp, forward-only và một SQL statement |
| Áp dụng `Integer.MIN_VALUE` fetch size cho mọi DB | Driver không có cùng quy ước | Chỉ dùng config đặc thù khi driver hỗ trợ |
| Đưa `BufferedWriter` vào try-with-resources bên trong từng `processRow` | Mở/đóng file cho mỗi hàng, có thể ghi đè dữ liệu | Mở Writer một lần trước query, đóng sau query |
| Trong handler thực thi network request chậm cho mỗi hàng | Giữ Connection lâu, tăng timeout/pool contention | Cân nhắc bounded queue, batch, pagination và timeout |
| Dùng handler singleton có trường mutable count/list | Race condition và kết quả lẫn giữa request | Tạo handler/accumulator per invocation |
| Không xử lý lỗi ghi CSV giữa chừng | File dở dang bị coi như thành công | Temp file, publish sau khi query hoàn tất và cleanup |
| Dùng `rs.getLong` rồi tưởng SQL NULL bằng 0 | Mất phân biệt NULL với số 0 | Gọi `rs.wasNull()` hoặc dùng `getObject(..., Long.class)` nếu driver hỗ trợ |
| Ném exception để dừng sau 100 hàng | Query bị coi là lỗi, khó kiểm soát transaction | Đặt LIMIT/FETCH trong SQL, hoặc extractor/pagination |
| Đóng Connection/ResultSet trong callback | Phá lifecycle do JdbcTemplate sở hữu | Chỉ xử lý dữ liệu; framework cleanup JDBC resource |
| Hiểu `@Transactional(readOnly=true)` là phép biến mọi driver thành streaming | Autocommit/driver và fetch size còn nhiều điều kiện | Kiểm thử trực tiếp cùng driver, DataSource, transaction manager |
| Chuyển từ List sang RowCallback nhưng SELECT vẫn quá nhiều cột | Vẫn tốn network/driver buffer/CPU | Chỉ SELECT cột cần thiết, tối ưu SQL/index |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Có nên gọi `rs.next()` trong `processRow` không?  
**Đáp:** Không. JdbcTemplate đã định vị ResultSet tới hàng hiện tại.

**Câu 2.** Vì sao `RowMapper` cũng xử lý từng hàng nhưng vẫn có thể gây tốn heap?  
**Đáp:** Overload `JdbcTemplate.query(..., RowMapper)` trả List, giữ một object sau mỗi lần map cho đến khi hoàn tất.

**Câu 3.** Callback sau có đạt mục tiêu không gom toàn bộ không: `rs -> list.add(map(rs))`?  
**Đáp:** Không. Danh sách do chính callback tạo vẫn tăng theo số hàng.

**Câu 4.** Nếu chỉ cần tổng tiền toàn bảng, SQL `SELECT SUM(amount)` hay `RowCallbackHandler` thường phù hợp hơn?  
**Đáp:** Thường dùng `SUM` trong database vì không cần tải mọi hàng về JVM.

**Câu 5.** Đặt `ps.setFetchSize(500)` có chắc JVM không nhận nhiều hơn 500 hàng một lúc không?  
**Đáp:** Không. Đó là hint/cơ chế phụ thuộc JDBC driver, transaction và database.

**Câu 6.** Với PostgreSQL cursor-based fetch, autocommit có vai trò gì?  
**Đáp:** pgJDBC yêu cầu Connection không autocommit cho cursor ResultSet hoạt động theo cách được mô tả trong tài liệu; fetch size dương và forward-only cũng quan trọng.

**Câu 7.** Hàm `RowCallbackHandler` trả về kiểu gì? Lấy tổng ở đâu?  
**Đáp:** `void`; tổng nằm trong accumulator do bên gọi sở hữu, hoặc dữ liệu được ghi trực tiếp vào output.

**Câu 8.** `JdbcTemplate.queryForStream` khác RowCallbackHandler thế nào?  
**Đáp:** Trả Stream để bên gọi xử lý lazy; phải đóng stream đúng cách và giữ connection còn hiệu lực. RowCallbackHandler chạy đồng bộ trong method query rồi trả void.

**Câu 9.** Nếu xuất 1 triệu hàng CSV mà Writer lỗi tại hàng 100 nghìn, database rollback có xóa file dở dang không?  
**Đáp:** Không. File là side effect ngoài transaction DB; nên ghi file tạm và chỉ publish khi query/Writer hoàn tất thành công.

**Bài tập thực hành:** Thêm trạng thái `REFUNDED` vào dữ liệu mẫu và viết `Summary summarizeByStatus(String status)` (bài demo đã có hàm theo status), xác minh `PAID` và `PENDING` đều có 5.000 bản ghi với tổng khác nhau. Sau đó sửa export để chỉ lấy các dòng có `amount >= ?`, thêm parameter binding trong `PreparedStatementSetter`. Kiểm tra CSV theo thứ tự ID, so sánh file trước/sau, và thử ghi ra path không có quyền để quan sát đường exception và cleanup. Đối với PostgreSQL thật, chạy phiên bản có transaction read-only và fetchSize thích hợp; đo peak heap khi số hàng tăng.

## 19. Tài liệu kỹ thuật chính thức

- [Spring Framework — RowCallbackHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html): `processRow(ResultSet)`, không được gọi `next()`.
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `query` với RowCallbackHandler, setter, creator và setting fetch size.
- [Spring Framework — JDBC core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): trách nhiệm quản lý ResultSet, Connection và các callback truy cập dữ liệu.
- [pgJDBC — Using a cursor to fetch ResultSet](https://jdbc.postgresql.org/documentation/query/): điều kiện autocommit, forward-only và fetch size để đọc theo đợt.
- [MySQL Connector/J — JDBC implementation notes](https://dev.mysql.com/doc/connectors/en/connector-j-reference-implementation-notes.html): buffering mặc định và các chế độ streaming/cursor fetch đặc thù.

## 20. Ghi nhớ cốt lõi

1. `RowCallbackHandler.processRow(rs)` xử lý **hàng hiện tại**, không tự `rs.next()`.
2. Overload `JdbcTemplate.query(..., RowCallbackHandler)` **không tạo List chứa toàn bộ kết quả** cho người gọi; dùng accumulator hoặc Writer có trạng thái giới hạn.
3. Chỉ xử lý từng hàng ở Java **chưa đủ chứng minh** JDBC driver/DBMS không buffer toàn bộ dữ liệu.
4. `setFetchSize`, chế độ transaction và cơ chế cursor **phụ thuộc driver**; kiểm thử với database thật.
5. Truy vấn hàng triệu dòng giữ connection lâu; tối ưu SQL, backpressure, timeout, concurrency và kiểm soát output dở dang.
6. Nếu database có thể tự `COUNT/SUM/GROUP BY`, hãy đẩy phép tính xuống SQL thay vì kéo mọi hàng lên Java.

**Kết luận:** `RowCallbackHandler` là công cụ phù hợp khi mục tiêu là **“đọc một hàng, xử lý một hàng, không giữ tất cả kết quả trong một `List`”**. Để hoàn thiện bài toán **tiết kiệm bộ nhớ end-to-end**, còn phải thiết kế fetch, transaction, driver, output và giới hạn tài nguyên của toàn hệ thống.
