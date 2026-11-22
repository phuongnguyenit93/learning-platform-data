# INSERT, UPDATE và DELETE bằng JdbcTemplate.update()

Trong Spring Framework Data Access, phương thức `JdbcTemplate.update()` là API thường dùng để thực thi các lệnh **thay đổi dữ liệu**: `INSERT` (thêm), `UPDATE` (sửa) và `DELETE` (xóa). Điểm chung quan trọng nhất: phương thức này **trả về số hàng bị tác động** dưới dạng `int` — nó **không** trả về đối tượng entity, `ResultSet` hay ID vừa được database sinh ra.

Ví dụ cùng một repository sử dụng `JdbcTemplate`:

```java
// Thêm một sản phẩm với ID do ứng dụng cung cấp.
int inserted = jdbc.update(
    "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
    10L, "Bút", 5
);

// Sửa sản phẩm đang tồn tại.
int updated = jdbc.update(
    "UPDATE products SET stock = ? WHERE id = ?",
    7, 10L
);

// Xóa sản phẩm theo khóa chính.
int deleted = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    10L
);
```

Các câu lệnh trên là **snippet bên trong phương thức có biến `jdbc`** và bảng `products` với cột tương ứng; không phải chương trình Java độc lập. Trong trường hợp có đúng một bản ghi với `id=10`, và không có lỗi ràng buộc, mỗi lời gọi thường trả `1`. Nếu `UPDATE` hoặc `DELETE` không tìm thấy bản ghi thỏa `WHERE`, kết quả thường là `0`.

Bài học sẽ giải thích cách dùng đúng ba loại lệnh, tham số hóa, kiểm tra số hàng tác động, giao dịch, xung đột cập nhật đồng thời, xử lý lỗi và cách tách việc **sinh khóa chính** sang overload có `KeyHolder` khi cần.

## 1. Mô hình tinh thần: update() thực thi thay đổi, không truy vấn dữ liệu

`JdbcTemplate` là lớp trợ giúp Spring JDBC nhận một `DataSource` đã cấu hình. Khi thực thi `update()`, Spring lấy `Connection` phù hợp với transaction hiện hành (nếu có), chuẩn bị statement, bind các tham số, gọi JDBC `executeUpdate()`, dịch lỗi SQL sang `DataAccessException` và dọn tài nguyên đúng phạm vi.

```text
Service / Repository
        |
        | jdbc.update(sql, args...)
        v
     JdbcTemplate
        |
        +---- DataSourceUtils lấy Connection theo transaction context
        |
        +---- Tạo PreparedStatement với SQL có dấu ?
        |
        +---- Bind parameter (setString/setLong/setObject/...)
        |
        +---- PreparedStatement.executeUpdate()
        |
        +---- Trả số hàng bị tác động (int)
        |
        +---- Dọn Statement và release Connection đúng cơ chế Spring
        v
Database: INSERT / UPDATE / DELETE
```

Điều phải nhớ:

- `update()` **không** đồng nghĩa chỉ làm SQL `UPDATE`. Tên phương thức là thuật ngữ JDBC cho thao tác DML, bao gồm `INSERT` và `DELETE`.
- Dùng `query()`/`queryForObject()`/`queryForList()` khi muốn lấy dữ liệu theo dạng `ResultSet`, không dùng `update()` thay cho `SELECT`.
- `int` trả về là số hàng do **JDBC driver báo cáo** cho lệnh; không phải ID được sinh ra hay số transaction đã commit.
- Việc gọi `update()` thành công chỉ nói statement chạy không ném lỗi; business operation có thể vẫn **không thành công** nếu cần đúng một hàng nhưng kết quả bằng `0`.

### 1.1. Những overload thường gặp

| API `JdbcTemplate` | Mục đích | Ghi chú |
| --- | --- | --- |
| `update(String sql, Object... args)` | DML với `?` và danh sách giá trị | Lựa chọn đơn giản, phổ biến. |
| `update(String sql, Object[] args, int[] argTypes)` | DML với kiểu SQL rõ ràng | Hữu ích với `NULL`/driver nhạy kiểu. |
| `update(String sql, PreparedStatementSetter pss)` | Tự bind các tham số vào `PreparedStatement` | Linh hoạt với kiểu đặc thù. |
| `update(PreparedStatementCreator psc)` | Tự tạo `PreparedStatement` | Dùng khi cần tùy biến statement. |
| `update(PreparedStatementCreator psc, KeyHolder keyHolder)` | DML đồng thời lấy khóa sinh do driver trả về | Phải bật yêu cầu generated keys khi tạo statement. |
| `update(String sql)` | Chạy SQL không có tham số qua `Statement` | Chỉ nên dùng với SQL **tĩnh, đáng tin cậy**. |

Tất cả các overload ở bảng trên (khi thực thi DML thành công) trả về `int`. Khi có lỗi, Spring ném một exception họ `DataAccessException`; không trả mã lỗi âm tùy ý để báo mọi trường hợp thất bại.

Không nhầm với `batchUpdate()`: phương thức batch trả `int[]` cho nhiều lệnh/nhóm lệnh, có ngữ nghĩa báo cáo riêng của JDBC.

## 2. Cú pháp SQL và binding tham số

### INSERT: tạo bản ghi mới

Ví dụ bảng `products`:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    stock INT NOT NULL CHECK (stock >= 0),
    version INT NOT NULL DEFAULT 0
);
```

Thao tác chèn:

```java
int rows = jdbc.update(
    "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
    id, name, initialStock
);
```

Cần ba dấu `?` tương ứng ba tham số. `JdbcTemplate` dùng `PreparedStatement` để bind, tránh ghép raw input vào SQL. Khi `id` trùng khóa chính, `name` là `NULL` dù cột `NOT NULL`, hoặc `stock < 0` vi phạm `CHECK`, DB từ chối lệnh; Spring thông thường ném một `DataAccessException` cụ thể thay vì trả `0`.

**Không đoán rằng INSERT luôn trả 1 trong mọi câu SQL:** `INSERT ... SELECT` hoặc một statement DML tác động nhiều hàng có thể trả số lượng khác. Với ví dụ `VALUES (...)` một hàng, kỳ vọng `1` là hợp lý.

### UPDATE: sửa bản ghi thỏa WHERE

```java
int rows = jdbc.update(
    "UPDATE products SET name = ?, stock = ? WHERE id = ?",
    newName, newStock, id
);
```

Thứ tự bind là `newName`, `newStock`, `id` theo thứ tự xuất hiện của từng dấu `?` trong SQL. Nên đặt điều kiện `WHERE` đủ cụ thể (thường theo khóa chính và tenant, hoặc điều kiện phiên bản) để tránh sửa nhầm nhiều bản ghi.

`UPDATE` không tìm thấy bản ghi thường trả `0` — không nhất thiết ném exception. Nếu tìm thấy hơn một bản ghi thỏa `WHERE`, có thể trả lớn hơn `1`. Việc đặt `WHERE id = ?` trên khóa chính có ràng buộc duy nhất giúp kỳ vọng tối đa một bản ghi.

### DELETE: xóa bản ghi thỏa WHERE

```java
int rows = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    id
);
```

`DELETE` xóa dữ liệu thật (hard delete) trừ khi database áp trigger/quy tắc khác. Nếu không còn bản ghi khớp, thông thường trả `0`. Hãy làm rõ nghiệp vụ muốn coi xóa bản ghi không tồn tại là **idempotent success**, `404 Not Found` hay lỗi concurrency; không coi `0` và `1` là tương đương trong mọi use case.

### 2.1. Bảng đối chiếu nhanh

| Câu lệnh | Ví dụ | Số hàng thường gặp | Cần quyết định |
| --- | --- | --- | --- |
| `INSERT ... VALUES` một hàng | `INSERT ... VALUES (?, ?)` | `1` | Thêm mới có được phép trùng ID không? |
| `UPDATE ... WHERE id = ?` | `UPDATE ... SET name=? WHERE id=?` | `0` hoặc `1` | Không tồn tại / phiên bản cũ thì xử lý sao? |
| `DELETE ... WHERE id = ?` | `DELETE FROM ... WHERE id=?` | `0` hoặc `1` | Xóa lặp có hợp lệ không? |
| `UPDATE ... WHERE status = ?` | `UPDATE ... SET status=? WHERE status=?` | `0..N` | Có đúng là cập nhật hàng loạt không? |
| `DELETE ... WHERE created_at < ?` | `DELETE FROM ... WHERE ...` | `0..N` | Cần audit, batch hoặc giới hạn thời gian không? |

**Cảnh báo:** Lệnh `UPDATE products SET stock = 0` hoặc `DELETE FROM products` **không có `WHERE`** sẽ tác động tất cả hàng của bảng theo câu lệnh đó. Chúng có thể hợp lệ trong migration có kiểm soát, nhưng phải được review đặc biệt và thường không phù hợp với API thao tác một entity.

## 3. Đọc đúng ý nghĩa của số hàng bị tác động

Ví dụ:

```java
int affected = jdbc.update(
    "UPDATE products SET name = ? WHERE id = ?",
    "Sổ tay", 10L
);

if (affected == 0) {
    // Không có hàng phù hợp, hoặc có điều kiện bảo vệ không khớp.
}
if (affected == 1) {
    // Với ràng buộc khóa chính, một hàng đã được statement xử lý.
}
if (affected > 1) {
    // Bất thường nếu tác vụ chỉ mong sửa đúng một entity.
}
```

Với câu lệnh cụ thể, hãy xác định **hậu điều kiện**:

- Chèn một hàng mới: thường kỳ vọng `affected == 1`.
- Sửa/xóa theo khóa duy nhất: `affected == 1` nghĩa là có một hàng thỏa điều kiện và driver báo cập nhật; `0` có thể là không tìm thấy hoặc điều kiện bảo vệ không khớp.
- Cập nhật hàng loạt: `affected >= 0` là bình thường, nhưng phải biết cỡ tác động kỳ vọng.
- Không được dùng `affected` như một giá trị generated ID. Ví dụ `affected=1` **không** có nghĩa record mới được sinh `id=1`.

### 3.1. Một nuance: “matched rows” và “changed rows”

Đối với `UPDATE` đặt lại đúng giá trị cũ, số hàng báo về có thể phụ thuộc **DBMS/driver/cấu hình driver**: một số môi trường báo số hàng khớp điều kiện, môi trường khác báo hàng thực sự thay đổi. Vì vậy, không suy diễn tuyệt đối:

> `affected == 0` luôn chứng minh bản ghi không tồn tại.

Với điều kiện `WHERE id = ? AND version = ?` và statement thật sự tăng `version`, `0` hữu ích hơn để phát hiện xung đột, bởi mỗi hàng khớp sẽ được thay đổi. Nếu nghiệp vụ cần phân biệt “không tồn tại” với “phiên bản lạc hậu”, có thể kiểm tra lại bằng truy vấn phù hợp hoặc dùng cơ chế khóa optimistic của domain; tránh dựa duy nhất vào ngữ nghĩa “changed rows” của một driver chưa kiểm chứng.

### 3.2. Không coi số hàng tác động là số hàng cascade

Khi xóa một parent có `ON DELETE CASCADE` hoặc trigger thay đổi bảng phụ, `update()` thường phản ánh update count do JDBC báo cho **statement được gọi**, không phải một phép đo tổng quát tất cả side effect ở mọi bảng. Nếu cần kiểm toán số lượng row phụ xóa, thiết kế audit hoặc truy vấn phù hợp thay vì suy ra từ một số `int`.

### 3.3. Check count rồi nâng thành lỗi nghiệp vụ

Nếu use case mong đúng một bản ghi, biến outcome thành điều kiện rõ:

```java
import org.springframework.dao.DataAccessException;

public void renameRequired(long id, String title) {
    int changed = jdbc.update(
        "UPDATE products SET name = ? WHERE id = ?",
        title, id
    );
    if (changed != 1) {
        throw new IllegalStateException(
            "Expected exactly one product to be updated");
    }
}
```

Đây là **snippet phương thức** trong repository/service đã có `JdbcTemplate jdbc`; `DataAccessException` không cần import nếu phương thức không dùng tên kiểu này trong chữ ký. Với API HTTP, nên phân loại tình huống thành lỗi 404/409 hoặc domain exception thích hợp, không tự động trả 500 cho mọi trường hợp `0`.

## 4. Code repository dùng ba thao tác

Lớp dưới là thành phần Spring (Java 17+). Nó chỉ giữ `JdbcTemplate`, không giữ `Connection` trong field:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {
    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(long id, String name, int stock) {
        return jdbc.update(
            "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
            id, name, stock
        );
    }

    public int rename(long id, String name) {
        return jdbc.update(
            "UPDATE products SET name = ? WHERE id = ?",
            name, id
        );
    }

    public int changeStockIfVersion(
            long id, int newStock, int expectedVersion) {
        return jdbc.update(
            """
            UPDATE products
               SET stock = ?, version = version + 1
             WHERE id = ? AND version = ?
            """,
            newStock, id, expectedVersion
        );
    }

    public int delete(long id) {
        return jdbc.update(
            "DELETE FROM products WHERE id = ?",
            id
        );
    }
}
```

**Giải thích:**

- `@Repository` có thể là singleton vì dependency `JdbcTemplate` thread-safe sau cấu hình; mỗi lời gọi thực thi một statement với tham số riêng.
- `JdbcTemplate.update` quản lý việc lấy/giải phóng resource bằng cơ chế tích hợp Spring transaction.
- Các giá trị `name`, `id`, `stock` được bind, không chèn vào text SQL.
- `changeStockIfVersion` cập nhật `version` nguyên tử cùng với `stock` khi phiên bản kỳ vọng còn khớp. Kết quả `0` có thể là id không tồn tại hoặc version lạc hậu.
- Các phương thức trả `int` để tầng service **quyết định** hậu điều kiện; không giấu `0` như thể thao tác chắc chắn thành công.

Cần validate `stock >= 0`, tên không trống/độ dài hợp lệ và quyền truy cập trước khi gọi. Ràng buộc `CHECK`/`NOT NULL`/`PRIMARY KEY` trong DB vẫn là lớp bảo vệ cuối; validation ứng dụng không thay thế constraint.

## 5. Dự án Spring Boot + H2 chạy được, có output xác định

Đây là ví dụ end-to-end chạy trên Java 17+ dùng Spring Boot 3.3.x, `spring-boot-starter-jdbc` và H2. Nó minh họa:

1. `INSERT` thành công trả 1.
2. `UPDATE` theo ID tồn tại trả 1.
3. `UPDATE` theo ID không tồn tại trả 0.
4. `UPDATE` với điều kiện `version` còn đúng trả 1 và tăng version.
5. `UPDATE` với expected version cũ trả 0.
6. `DELETE` lần đầu trả 1; lần sau trả 0.
7. Bảng không còn bản ghi sau khi xóa.

### 5.1. Cấu hình Gradle

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Tệp `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:jdbc_update_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` duy trì H2 in-memory database trong vòng đời JVM dù có giai đoạn connection đóng hết. Đây là cấu hình demo, không phải thiết lập bắt buộc cho production.

### 5.2. Ứng dụng Java đầy đủ

Tệp `src/main/java/example/UpdateDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class UpdateDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpdateDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, BookRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(120) NOT NULL,
                    stock INT NOT NULL CHECK (stock >= 0),
                    version INT NOT NULL DEFAULT 0
                )
                """);

            int inserted = repo.insert(10L, "Java", 5);
            int renamed = repo.rename(10L, "Spring JDBC");
            int missing = repo.rename(99L, "Not there");
            int changed = repo.updateStockIfVersion(10L, 4, 0);
            int stale = repo.updateStockIfVersion(10L, 8, 0);

            Integer version = jdbc.queryForObject(
                "SELECT version FROM books WHERE id = ?",
                Integer.class, 10L
            );

            int removed = repo.deleteById(10L);
            int removedAgain = repo.deleteById(10L);

            Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Integer.class
            );

            System.out.println("inserted=" + inserted);
            System.out.println("renamed=" + renamed);
            System.out.println("missing=" + missing);
            System.out.println("stockChanged=" + changed);
            System.out.println("staleVersion=" + stale);
            System.out.println("version=" + version);
            System.out.println("removed=" + removed);
            System.out.println("removedAgain=" + removedAgain);
            System.out.println("remaining=" + remaining);
        };
    }
}

@Repository
class BookRepository {
    private final JdbcTemplate jdbc;

    BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    int insert(long id, String title, int stock) {
        return jdbc.update(
            "INSERT INTO books(id, title, stock) VALUES (?, ?, ?)",
            id, title, stock
        );
    }

    int rename(long id, String title) {
        return jdbc.update(
            "UPDATE books SET title = ? WHERE id = ?",
            title, id
        );
    }

    int updateStockIfVersion(
            long id, int stock, int expectedVersion) {
        return jdbc.update(
            """
            UPDATE books
               SET stock = ?, version = version + 1
             WHERE id = ? AND version = ?
            """,
            stock, id, expectedVersion
        );
    }

    int deleteById(long id) {
        return jdbc.update(
            "DELETE FROM books WHERE id = ?",
            id
        );
    }
}
```

Tệp `UpdateDemoApplication.java` chứa một public class và một package-private class trong cùng package `example`; Java cho phép cấu trúc này. Khi có dependencies đúng, chương trình có thể khởi chạy Spring context, tạo bảng và gọi repository.

### 5.3. Chạy và stdout

Từ thư mục project có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các dòng do **`System.out` của chương trình** tạo ra trong môi trường H2 hoạt động như trên:

```text
inserted=1
renamed=1
missing=0
stockChanged=1
staleVersion=0
version=1
removed=1
removedAgain=0
remaining=0
```

Spring Boot/Hikari có thể in thêm log. Kết quả là xác định vì mỗi thao tác chạy tuần tự trong một `CommandLineRunner` và bảng vừa được tạo mới. `version` bắt đầu bằng `0` nhờ default của database; cập nhật thành công tăng nó lên `1`. Lời gọi thứ hai với `expectedVersion=0` không còn khớp nên trả `0`. Hai lệnh xóa minh họa khác biệt giữa bản ghi còn tồn tại và đã bị xóa.

**Quan trọng:** Ví dụ dùng **ID do code cấp** (`10L`), không phải ID do database sinh. Trả về `inserted=1` là **row count**, không phải `id=1`.

## 6. Làm gì khi update() trả 0 hoặc nhiều hơn 1?

Tránh kiểu code:

```java
jdbc.update("UPDATE orders SET status = ? WHERE id = ?", status, id);
// Không kiểm tra kết quả, nhưng vẫn trả HTTP 200 như thể đã sửa được.
```

Nếu khách hàng sửa một đơn không tồn tại hoặc cập nhật phiên bản lạc hậu, kết quả có thể bằng `0` và không có exception. Cách làm tốt hơn là xác định business contract.

| Use case | `affected=0` | `affected=1` | `affected>1` |
| --- | --- | --- | --- |
| Đổi tên entity theo primary key | Not found hoặc conflict (cần phân biệt). | Thành công theo driver. | Bất thường; xem lại WHERE/constraint. |
| Xóa entity theo primary key | Có thể coi là idempotent success, hoặc 404, tùy API. | Đã xóa một hàng. | Bất thường nếu ID unique. |
| Chuyển trạng thái có điều kiện | State không khớp, cần thông báo conflict. | State transition đã được xử lý. | Chỉ hợp lệ nếu thiết kế multi-row. |
| Batch cleanup theo thời gian | Không có hàng cần dọn; thường bình thường. | Một hàng bị tác động. | Có thể hợp lệ; cần metrics/audit. |

Ví dụ chuyển trạng thái nguyên tử:

```java
int claimed = jdbc.update(
    """
    UPDATE jobs
       SET status = 'RUNNING'
     WHERE id = ? AND status = 'READY'
    """,
    jobId
);
if (claimed != 1) {
    // Job không còn READY hoặc không tồn tại; không tự xử lý lần thứ hai.
}
```

Đây là **snippet trong phương thức có jdbc và jobId**; bảng `jobs`/các trạng thái là điều kiện tiên quyết. Kết hợp trạng thái cũ trong `WHERE` là một dạng compare-and-set ở database, tránh việc đọc state rồi cập nhật mù. Hãy phân biệt quyền nhận job và semantics retry khi nhiều worker cạnh tranh.

## 7. UPDATE an toàn khi nhiều request cập nhật đồng thời

### 7.1. Lost update khi read–modify–write không có bảo vệ

Hình dung hai request đọc `stock=5`, mỗi request muốn bán một sản phẩm và đều tính `newStock=4` trên client. Nếu cả hai lần lượt thực hiện:

```sql
UPDATE products SET stock = 4 WHERE id = 10;
```

Hai request đều có thể trả `1`, nhưng stock cuối vẫn là `4` thay vì `3`. **Một row count bằng 1 không chứng minh không có race logic**.

### 7.2. Cập nhật số học trong SQL kèm điều kiện

Thay vì tính số tồn kho mới dựa trên snapshot cũ ở Java:

```java
int affected = jdbc.update(
    """
    UPDATE products
       SET stock = stock - ?
     WHERE id = ? AND stock >= ?
    """,
    quantity, productId, quantity
);
```

Với `quantity > 0` và DBMS hỗ trợ atomic update/locking thông thường, mỗi statement trừ trực tiếp từ giá trị hiện tại theo điều kiện `stock >= quantity`. Nếu không đủ tồn, `affected=0`. Điều này thường tốt hơn pattern `SELECT stock` → tính trong Java → `UPDATE stock = ?` không có kiểm soát.

Vẫn cần xử lý isolation, lock contention, transaction retry và các invariant nghiệp vụ khác. Nếu có concurrency cao hoặc nhiều bảng liên quan, một statement đơn lẻ không giải quyết toàn bộ transaction workflow.

### 7.3. Optimistic locking bằng version column

Lệnh sau chỉ cập nhật khi phiên bản trong DB còn khớp với phiên bản ứng dụng đã đọc:

```sql
UPDATE products
SET name = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Nếu hai request cùng đọc `version=0`, request thắng tăng lên `1`, request còn lại nhận `affected=0` và cần xử lý conflict. Không tự retry cùng dữ liệu cũ vô hạn; một số use case cần đọc lại, merge hoặc yêu cầu người dùng xác nhận.

Với Spring Data/JPA, có cơ chế `@Version` riêng; trong `JdbcTemplate`, **bạn tự viết** điều kiện version và kiểm tra count. Đừng nghĩ annotation của JPA tự hoạt động với mọi câu `jdbc.update` viết tay.

## 8. Nhiều câu lệnh: dùng transaction thay vì trông đợi update() tự bao trọn

Mỗi `update()` thực thi một statement. Khi không có transaction Spring đang hoạt động và connection ở chế độ auto-commit, mỗi statement thành công thường được commit riêng. Nếu nghiệp vụ cần **cả hai thay đổi cùng thành công hoặc cùng rollback**, hãy dùng transaction.

Ví dụ chuyển hàng giữa hai kho:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class StockTransferService {
    private final JdbcTemplate jdbc;

    public StockTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromWarehouseId,
                         long toWarehouseId,
                         long productId,
                         int quantity) {
        if (quantity <= 0 || fromWarehouseId == toWarehouseId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            """
            UPDATE inventory
               SET quantity = quantity - ?
             WHERE warehouse_id = ?
               AND product_id = ?
               AND quantity >= ?
            """,
            quantity, fromWarehouseId, productId, quantity
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source inventory unavailable");
        }

        int credited = jdbc.update(
            """
            UPDATE inventory
               SET quantity = quantity + ?
             WHERE warehouse_id = ? AND product_id = ?
            """,
            quantity, toWarehouseId, productId
        );
        if (credited != 1) {
            throw new IllegalStateException(
                "Destination inventory missing");
        }
    }
}
```

Đây là class Spring hợp lệ nhưng cần bảng `inventory` có unique key theo `(warehouse_id, product_id)`, transaction manager và `JdbcTemplate` cùng DataSource. Gọi service **qua Spring proxy** để `@Transactional` được áp trong chế độ proxy (self-invocation của cùng bean thường không kích hoạt interception). Khi lệnh thứ hai không sửa được hàng, `IllegalStateException` thoát khỏi phương thức khiến Spring theo mặc định rollback transaction đối với unchecked exception.

Điểm then chốt:

- `JdbcTemplate` kết hợp với `DataSourceUtils` để dùng connection gắn với transaction.
- Bản thân `update()` **không tự tạo** một transaction bao trùm nhiều lời gọi trong Java.
- Một transaction cần ranh giới rõ; không gọi HTTP API hay xử lý chậm không liên quan DB trong lúc giữ lock/connection.
- Với checked exception, Spring rollback rule mặc định khác unchecked; dùng `rollbackFor`/quy tắc phù hợp nếu nghiệp vụ yêu cầu.
- Nếu code bắt exception rồi **nuốt lỗi và trả về bình thường**, transaction manager có thể commit những thay đổi đã thành công; phải quyết định rethrow/rollback rõ ràng.
- Không giữ `Connection` trong field singleton hoặc truyền sang thread khác để “giữ transaction”.

### 8.1. Không lẫn transaction timeout với số hàng trả về

`update()` trả số hàng do driver báo, không trả trạng thái commit toàn cục. Lỗi timeout/connection có thể xuất hiện khi statement chạy hoặc lúc commit. Với những thao tác có thể bị retry (nhất là khi kết nối gián đoạn sau khi gửi SQL), phải đánh giá **idempotency** và outcome của transaction; không khẳng định bất kỳ exception nào cũng bảo đảm database chưa thực hiện thay đổi.

## 9. Generated keys: update() trả số hàng, KeyHolder mới lấy ID

Vì ngữ cảnh chương học có “khóa sinh”, cần phân biệt hai nhu cầu:

1. **Xác định chèn thành công:** dùng `int affected = jdbc.update(...)`.
2. **Lấy giá trị primary key do database sinh** (`IDENTITY`, auto-increment, v.v.): dùng overload hỗ trợ `KeyHolder`, hoặc phương án tương đương phù hợp DB/driver.

Giả sử bảng có cột `id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY`. Trong một Spring repository có `JdbcTemplate jdbc`:

```java
import java.sql.PreparedStatement;
import java.sql.Statement;

import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

public long insertAndGetId(String name) {
    KeyHolder holder = new GeneratedKeyHolder();

    int rows = jdbc.update(
        connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO customers(name) VALUES (?)",
                new String[] {"id"}
            );
            ps.setString(1, name);
            return ps;
        },
        holder
    );

    if (rows != 1) {
        throw new IllegalStateException(
            "Expected one inserted customer");
    }

    Number generated = holder.getKey();
    if (generated == null) {
        throw new IllegalStateException(
            "Driver did not return a generated ID");
    }
    return generated.longValue();
}
```

**Phạm vi của snippet:** Thân phương thức trong repository đã có `JdbcTemplate jdbc` và bảng `customers(id identity, name)`; import `Statement` ở đây không cần cho phương thức vì dùng mảng tên cột. Nếu muốn dùng `Statement.RETURN_GENERATED_KEYS`, có thể thay tham số thứ hai của `prepareStatement` bằng hằng này. Driver phải hỗ trợ generated keys. `KeyHolder.getKey()` phù hợp khi driver trả **một khóa số duy nhất**; nếu trả nhiều cột/khóa, cần kiểm tra `getKeys()` hoặc `getKeyList()` tùy bài toán.

**Không nhầm:** Với `INSERT` một hàng sinh ID 745, `update()` vẫn có thể trả `1`; ID 745 đến từ generated keys, **không đến từ row count**. Các DBMS còn có lựa chọn `RETURNING`/`OUTPUT` với semantics khác; nếu statement trả result set, dùng API phù hợp, không mặc định `update()` sẽ trả các hàng đó.

## 10. Kiểu SQL, NULL và binding

Varargs `update(sql, Object... args)` thường đủ cho các kiểu phổ biến (`String`, `long`, `int`, `BigDecimal`, `Timestamp`). Tuy nhiên `NULL` hoặc kiểu DB đặc biệt đôi khi cần chỉ rõ kiểu JDBC để driver không suy luận sai.

Ví dụ khi muốn cập nhật `notes` dạng `VARCHAR` có thể NULL:

```java
import java.sql.Types;

int rows = jdbc.update(
    "UPDATE products SET notes = ? WHERE id = ?",
    new Object[] { null, productId },
    new int[] { Types.VARCHAR, Types.BIGINT }
);
```

Đây là đoạn đặt trong method đã có `JdbcTemplate jdbc` và biến `productId`. Các mảng `args` và `argTypes` phải cùng thứ tự/kích thước. Một lựa chọn khác là dùng `SqlParameterValue` để gắn `Types.VARCHAR` cho tham số cụ thể.

**Lưu ý về SQL NULL:** `WHERE field = NULL` không bao giờ là phép so sánh đúng theo logic SQL ba giá trị; dùng `IS NULL` hoặc điều kiện nullable rõ ràng. Nếu cần điều kiện tùy input null, thiết kế SQL có chủ đích, không ghép text từ input không đáng tin.

Cũng cần thận trọng với kiểu ngày/giờ, `BigDecimal` cho tiền, JSON/array/enum của từng DBMS và cách JDBC driver ánh xạ. **Binding an toàn** và **chọn kiểu dữ liệu đúng** là hai trách nhiệm khác nhau.

## 11. Không dùng raw SQL động để thay tên bảng/cột

Dấu `?` chỉ đại diện **data values**, không thay tên bảng, cột hay keyword. Không làm:

```java
// SAI: data from HTTP có thể điều khiển SQL structure.
String sql = "DELETE FROM " + requestTable + " WHERE id = ?";
jdbc.update(sql, id);
```

Tương tự, `ORDER BY ?` với bind chuỗi tên cột không thay thế được identifier theo ý muốn. Nếu nghiệp vụ cho chọn một vài bảng hoặc cột, ánh xạ choice qua enum/allow-list **cố định trong source code**, rồi mới tạo SQL; tất cả giá trị trong `WHERE` tiếp tục dùng `?`.

### 11.1. Multi-tenant và quyền cập nhật

Đối với hệ thống nhiều tenant, **khóa chính trong bảng chưa đủ làm kiểm soát quyền truy cập**. SQL thường cần điều kiện tenant/owner lấy từ authentication context đáng tin:

```java
int affected = jdbc.update(
    """
    UPDATE documents
       SET title = ?
     WHERE id = ? AND tenant_id = ?
    """,
    newTitle, documentId, authenticatedTenantId
);
```

`authenticatedTenantId` không nên đơn giản là giá trị URL do client tự khai. `affected=0` lúc này có thể nghĩa là bản ghi không tồn tại, không thuộc tenant, hoặc không thỏa điều kiện khác; tránh tiết lộ sự tồn tại bản ghi của tenant khác qua lỗi chi tiết.

## 12. DELETE thật hay soft delete?

**Hard delete:**

```java
int affected = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    id
);
```

Hàng bị xóa khỏi bảng (trừ cơ chế DB đặc biệt), các foreign key có thể chặn hoặc kích hoạt cascade. Nếu nghiệp vụ yêu cầu audit, lịch sử đơn hàng hoặc phục hồi, hard delete có thể không phù hợp.

**Soft delete:**

```java
int affected = jdbc.update(
    """
    UPDATE products
       SET deleted = TRUE
     WHERE id = ? AND deleted = FALSE
    """,
    id
);
```

Đây là `UPDATE` chứ không phải `DELETE` và cần cột `deleted` trong schema. Kết quả `0` có thể là không tồn tại **hoặc đã được xóa mềm trước đó**. Tất cả truy vấn đọc phải thống nhất có/không lọc `deleted=FALSE`; thêm quy tắc unique/index phù hợp nếu cần tránh xung đột tên của bản ghi đã ẩn.

Không coi soft delete là an toàn hơn tuyệt đối: nó làm phát sinh trách nhiệm kiểm soát truy vấn, vòng đời retention, privacy và quy tắc xóa thật.

## 13. batchUpdate() và nhiều thao tác: chọn API đúng

Nếu cần cập nhật 10.000 bản ghi theo cùng cấu trúc, gọi `jdbc.update(...)` 10.000 lần trong vòng lặp có thể tốn nhiều lượt trao đổi. `batchUpdate()` là lựa chọn tối ưu khi driver hỗ trợ batch; nó **không cùng kiểu kết quả** với `update()`.

Ví dụ:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;

public int[] markProcessed(List<Long> ids, JdbcTemplate jdbc) {
    return jdbc.batchUpdate(
        "UPDATE jobs SET processed = TRUE WHERE id = ?",
        ids,
        200,
        (ps, id) -> ps.setLong(1, id)
    ).stream()
     .flatMapToInt(java.util.Arrays::stream)
     .toArray();
}
```

Snippet trên là **phương thức trong một class**, dùng overload `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` trả về `int[][]`, được làm phẳng để dễ quan sát số hàng từ mỗi batch. Tùy JDBC driver, các giá trị có thể gồm `Statement.SUCCESS_NO_INFO` (`-2`), không phải luôn là số không âm chính xác. Không áp invariant “mỗi kết quả phải bằng 1” với batch khi driver có quyền trả mã đặc biệt; phải xem hợp đồng JDBC.

**Trọng tâm bài:** Khi chỉ thực thi một `INSERT`/`UPDATE`/`DELETE`, dùng `update()` và kiểm tra `int`. Khi chạy nhiều statement cùng loại, cân nhắc `batchUpdate()`, transaction, giới hạn batch size và driver support.

## 14. Xử lý lỗi: exception khác với 0 hàng

`JdbcTemplate` chuyển JDBC `SQLException` thành exception thuộc họ `org.springframework.dao.DataAccessException` (unchecked). Một số tình huống:

| Tình huống | Kết quả có thể |
| --- | --- |
| `UPDATE ... WHERE id=?` không khớp hàng | `affected=0`, không phải luôn exception. |
| `DELETE` theo id đã bị xóa | `affected=0` nếu không còn match. |
| `INSERT` trùng primary key | `DataIntegrityViolationException`/`DuplicateKeyException` tùy translator/DB. |
| `INSERT` vi phạm `NOT NULL` hoặc `CHECK` | Một `DataAccessException` liên quan ràng buộc dữ liệu. |
| SQL sai cú pháp/bảng không tồn tại | Một `DataAccessException` (có thể `BadSqlGrammarException`). |
| DB/network/timeout lỗi | Một `DataAccessException` phù hợp, tùy driver và translator. |
| Transaction commit thất bại | Có thể phát sinh exception ngoài thời điểm gọi `update()`. |

Không nên:

```java
try {
    jdbc.update(sql, args);
} catch (Exception ex) {
    return 0; // SAI: đánh đồng DB hỏng/constraint violation với không khớp bản ghi
}
```

Nếu thực sự cần chuyển exception thành lỗi nghiệp vụ, phân loại theo nguyên nhân, log thông tin vừa đủ (không lộ credentials/dữ liệu nhạy cảm) và bảo toàn rollback/retry semantics. Với `@Transactional`, tránh bắt rồi nuốt unchecked exception vì transaction có thể commit những statement đã chạy thành công.

### 14.1. Về retry

Retry sau deadlock hoặc transient connection failure có thể hợp lý **nếu có kiểm soát**. Nhưng retry bừa `INSERT` sau timeout mạng là nguy hiểm: DB có thể đã chèn thành công dù client chưa nhận phản hồi. Xây idempotency key/unique constraint, transaction boundaries, và kiểm tra outcome trước khi quyết định retry.

## 15. Performance và quan sát

`JdbcTemplate.update()` chỉ giảm boilerplate JDBC, không làm mọi SQL nhanh. Với thao tác thay đổi dữ liệu, các điểm vận hành cần chú ý:

- **Index trên điều kiện WHERE:** `UPDATE/DELETE WHERE id=?` thường được lợi từ primary-key index. Điều kiện thiếu index có thể scan nhiều hàng.
- **Lock duration:** Transaction dài giữ row locks lâu, tăng chờ và deadlock.
- **Số hàng bị tác động:** Log/metrics hữu ích để phát hiện thao tác bất thường, nhưng tránh lộ ID/ngữ cảnh nhạy cảm.
- **Transaction boundaries:** Gộp các statement phụ thuộc nhau vào một transaction; không giữ transaction qua network I/O chậm.
- **Batch:** Dùng `batchUpdate` cho lượng thay đổi lớn khi có lợi, tránh một SQL update hàng triệu bản ghi không giới hạn mà không có kế hoạch.
- **Connection pool:** Mỗi request cần connection đúng phạm vi; không giữ `Connection` singleton. Pool cạn có thể làm thao tác chờ trước khi JDBC statement chạy.
- **Query/statement timeout:** Cân nhắc thời gian giao dịch và DB lock timeout; timeout không tự chứng minh rollback an toàn trong mọi tình huống ngoài transaction.

Một migration hoặc cleanup có tác động lớn cần backup, maintenance window, plan, audit và dry-run thích hợp; không dựa đơn thuần vào `affected` để khẳng định dữ liệu đã đúng sau thay đổi.

## 16. Những lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| Nghĩ `update()` chỉ chạy SQL UPDATE | Dùng nhầm API cho INSERT/DELETE. | Nhớ nó thực thi DML và trả row count. |
| Nghĩ return `1` là ID được sinh | Nhầm row count với generated key. | Dùng `KeyHolder` khi thật sự cần ID. |
| Không kiểm tra `affected` | Không phát hiện thao tác 0 hàng. | Đặt hậu điều kiện theo business operation. |
| Bỏ `WHERE` trong UPDATE/DELETE | Có thể sửa/xóa toàn bảng. | Review SQL và điều kiện khóa/tenant. |
| Ghép input thành SQL string | SQL injection và lỗi quoting. | Bind data values qua `?`, cấu trúc dùng allow-list. |
| Tính giá trị mới trong Java rồi UPDATE mù | Lost update khi concurrency. | SQL atomic/optimistic locking/transaction. |
| Bắt DB exception rồi trả 0 | Che mất lỗi infrastructure và có thể commit một phần. | Phân biệt exception với no-match; rollback rõ. |
| Tưởng nhiều update() cùng transaction tự động | Có thể chỉ commit từng statement. | `@Transactional`/`TransactionTemplate` đúng phạm vi. |
| Dùng `update()` để lấy danh sách bản ghi | Method trả int, không RowMapper result. | Dùng query APIs cho SELECT. |
| Dùng `DELETE` khi cần lưu lịch sử | Mất dữ liệu hoặc vi phạm FK. | Cân nhắc soft delete, retention và audit. |
| Nhầm row count với số hàng cascade | Audit không chính xác. | Theo dõi side effect riêng. |
| Coi SQL type của `NULL` luôn tự suy ra | Driver có thể bind sai. | Cung cấp `Types`/`SqlParameterValue` khi cần. |
| Dùng `batchUpdate()` và mong `int` đơn | Batch trả mảng counts và có mã đặc biệt. | Đọc đúng API batch/JDBC contract. |

## 17. Câu hỏi tự kiểm tra

**1.** `JdbcTemplate.update()` dùng cho những SQL nào và trả kiểu gì?

**Đáp án:** Chủ yếu `INSERT`, `UPDATE`, `DELETE` và DML tương ứng; trả `int` là số hàng do JDBC báo tác động.

**2.** `INSERT` một hàng thành công trả `1` có nghĩa primary key được sinh là 1 không?

**Đáp án:** Không. `1` là row count. Generated ID cần lấy qua `KeyHolder` hoặc cơ chế tương ứng.

**3.** `UPDATE products SET name=? WHERE id=?` trả `0` có luôn là exception không?

**Đáp án:** Không. Thường có nghĩa không có hàng thỏa điều kiện (hoặc khác biệt matched/changed rows tùy driver), và caller phải quyết định tình huống nghiệp vụ.

**4.** Nếu hai request đọc stock=5 rồi cùng ghi stock=4 bằng `UPDATE`, mỗi request đều trả `1`, dữ liệu đã đúng chưa?

**Đáp án:** Chưa chắc. Có thể xảy ra lost update. Dùng câu SQL trừ nguyên tử hoặc điều kiện version và kiểm tra số hàng.

**5.** Vì sao `WHERE id=? AND version=?` cùng `version=version+1` hữu ích?

**Đáp án:** Nó biến cập nhật thành compare-and-set theo version. Một request có version cũ sẽ không match và thường nhận `0` thay vì ghi đè người khác.

**6.** Có hai `update()` trong một service cần cùng commit/rollback thì làm gì?

**Đáp án:** Thiết lập Spring transaction phù hợp (`@Transactional` hoặc `TransactionTemplate`), bảo đảm cùng DataSource và proxy/transaction manager đang hoạt động; ném exception nếu hậu điều kiện không đạt.

**7.** `DELETE FROM products WHERE id=?` trả `0` sau lần xóa thứ hai có phải luôn là lỗi?

**Đáp án:** Không. Tùy hợp đồng API, xóa lặp có thể là idempotent success hoặc phải trả not-found. Row count cung cấp tín hiệu để quyết định.

**8.** `update(sql, args, argTypes)` giải quyết vấn đề gì?

**Đáp án:** Cho phép xác định kiểu SQL rõ ràng khi bind tham số, đặc biệt hữu ích với `NULL` hay kiểu driver khó suy đoán.

**9.** Khi cần lấy khóa được database sinh, overload nào liên quan?

**Đáp án:** `update(PreparedStatementCreator, KeyHolder)`, với statement yêu cầu generated keys; cần driver hỗ trợ.

## 18. Checklist trước khi đưa vào production

- [ ] Chọn `update()` cho một thao tác DML; chọn `query()` cho kết quả hàng, `batchUpdate()` cho batch.
- [ ] Tham số SQL đều bind bằng `?`; không nối raw input thành SQL structure.
- [ ] `WHERE` bảo đảm đúng khóa, điều kiện trạng thái/version và tenant authorization.
- [ ] Với tác vụ một entity, đã xác định rõ cách xử lý `affected=0`, `1` hoặc giá trị bất thường.
- [ ] Không nhầm `affected` với khóa ID do DB sinh; dùng `KeyHolder` khi cần.
- [ ] Có constraints DB phù hợp (`PK`, `FK`, `NOT NULL`, `CHECK`, unique).
- [ ] Có transaction cho các statement phải cùng commit/rollback.
- [ ] Các phương thức `@Transactional` được gọi qua proxy theo chế độ cấu hình; không nuốt lỗi mà làm commit một phần.
- [ ] Khi concurrency, kiểm tra atomic update/optimistic locking và tránh lost update.
- [ ] Có quyết định rõ về hard delete, soft delete, cascade và audit.
- [ ] Kiểu JDBC của `NULL`, ngày giờ và decimal được kiểm thử trên driver thực.
- [ ] Có test insert thành công/duplicate, update 0/1 hàng, delete lặp, version stale và rollback.
- [ ] Đã kiểm tra logs/metrics, query plan, index và timeout cho thao tác lớn.

## 19. Tài liệu tham khảo

- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): các overload `update`, `batchUpdate`, `KeyHolder` và giá trị trả về.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): mẫu dùng `JdbcTemplate`, binding và error translation.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries, `@Transactional` và rollback rules.
- [Java SE — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): `executeUpdate()` và binding tham số.
- [Java SE — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): update count, `SUCCESS_NO_INFO` và generated keys.

**Ghi nhớ:** `JdbcTemplate.update()` thực thi `INSERT`, `UPDATE` và `DELETE`, rồi trả về **số hàng bị tác động**. Hãy bind tham số, kiểm tra hậu điều kiện bằng row count, đặt `WHERE` có kiểm soát, dùng transaction khi nhiều thay đổi phải nguyên tử và dùng `KeyHolder` khi thực sự cần **ID được sinh**, không suy ra ID từ giá trị `int`.
