# RowMapper không tự gọi ResultSet.next() — quy tắc quản lý con trỏ khi ánh xạ JDBC

## 1. Quy tắc quan trọng nhất

Trong Spring JDBC, `org.springframework.jdbc.core.RowMapper<T>` là callback có trách nhiệm **ánh xạ đúng một hàng hiện tại** của `ResultSet` thành một đối tượng Java. **Không gọi `rs.next()` trong `mapRow(ResultSet rs, int rowNum)`.** `JdbcTemplate` (thông qua bộ duyệt kết quả tương ứng) đã gọi `ResultSet.next()` và định vị con trỏ trên hàng cần đọc **trước khi** gọi mapper. **Gọi `next()` lần nữa trong mapper sẽ làm con trỏ vượt khỏi hàng hiện tại, gây bỏ hàng, mapping sai hoặc phát sinh `SQLException`.**

Một `RowMapper` đúng chỉ cần đọc cột của hàng đang đứng, tạo đối tượng, trả về. Hầu hết trường hợp có thể biểu diễn bằng lambda hai tham số:

```java
RowMapper<Student> mapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

Đây là mã **trong dự án có Spring JDBC**, với record `Student` được định nghĩa ở phần ví dụ. Không có `rs.next()` vì mapper không chịu trách nhiệm di chuyển con trỏ.

Mục tiêu sau bài học:
1. Giải thích chính xác ai điều khiển `ResultSet.next()` khi dùng `JdbcTemplate.query()`.
2. Phân biệt mapper của **một hàng** với extractor của **toàn bộ tập kết quả**.
3. Nhận diện lỗi gọi `rs.next()` sai chỗ và biết vì sao nó thường tạo **bỏ sót dữ liệu âm thầm**.
4. Dùng đúng `rowNum`, getter JDBC, nullability và vòng đời JDBC resources.
5. Tự chạy ví dụ Spring Boot/Java 17+ và kiểm thử hợp đồng mapping theo tình huống 0, 1, nhiều hàng.

Bối cảnh: Spring Framework 6.x, Spring Boot 3.x và JDBC blocking. Nguyên tắc này cũng thể hiện trong Javadoc chính thức của `RowMapper`.

## 2. ResultSet là con trỏ, không phải List đã nằm sẵn trong Java

Một `ResultSet` JDBC điển hình đại diện các hàng SQL và một **cursor** cho biết hàng nào đang được đọc. Với JDBC thuần, ban đầu cursor thường ở vị trí **trước hàng đầu tiên**; người viết JDBC cần tự gọi `rs.next()` để tiến tới hàng thứ nhất. Mỗi lần `next()` thành công, cursor tiến thêm một hàng và trả `true`; khi hết hàng, trả `false`.

### Ví dụ SQL trả bốn hàng

```text
SELECT id, name FROM students ORDER BY id

Vị trí cursor:
[before first] → [1: An] → [2: Bình] → [3: Chi] → [4: Dũng] → [after last]
        rs.next()    rs.next()   rs.next()   rs.next()   rs.next()
```

Với JDBC thuần:

```java
// Mã JDBC thuần trong method có Connection connection.
// Tài nguyên tự tạo phải được đóng.
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id, name FROM students ORDER BY id");
     ResultSet rs = statement.executeQuery()) {

    while (rs.next()) {   // ĐÚNG trong JDBC thuần
        System.out.println(rs.getString("name"));
    }
}
```

Trong JDBC thuần, vòng `while` sở hữu logic di chuyển con trỏ; vì thế nó **phải** gọi `next()`. Nếu bỏ lời gọi này, getter có thể truy cập khi cursor chưa đứng ở hàng hợp lệ và ném SQLException.

**Khác biệt căn bản:** trong `JdbcTemplate.query(sql, rowMapper)`, *Spring đã thực hiện vòng lặp tương đương*, nên `RowMapper` không được lặp lại thao tác chuyển con trỏ.

## 3. JdbcTemplate duyệt ResultSet như thế nào?

Với một overload `JdbcTemplate.query(sql, RowMapper<T>)`, đường đi logic giống đoạn mã khái niệm sau:

```java
// PSEUDOCODE: để hiểu cơ chế, không phải mã nguồn Spring nguyên văn.
List<T> result = new ArrayList<>();
int rowNum = 0;

while (rs.next()) {
    T item = rowMapper.mapRow(rs, rowNum++);
    result.add(item);
}
return result;
```

Bộ duyệt của Spring chịu trách nhiệm:
- Thực thi câu SQL và nhận `ResultSet`.
- Gọi `rs.next()` để đi tới từng hàng.
- Gọi `mapRow(rs, rowNum)` đúng lúc cursor đã ở hàng hợp lệ.
- Thu thập những object Java được mapper trả về thành danh sách cho `query(...)`.
- Đóng ResultSet/Statement và release connection do template sở hữu theo hợp đồng và transaction context.

Trong Spring, `RowMapperResultSetExtractor` là một adapter phổ biến dùng `RowMapper` để tạo một object cho mỗi hàng của ResultSet. Đây là **lớp extractor** xử lý việc duyệt, còn mapper chỉ xử lý hàng hiện tại. Không cần phụ thuộc lớp internal/adapter này trực tiếp trong repository bình thường: hãy sử dụng `JdbcTemplate.query(...)`.

### Dòng thời gian đúng

```text
Kết quả SQL: id=1,2,3,4

JdbcTemplate              RowMapper
   |
   | rs.next() → row 1
   +----------------------> mapRow(row 1, 0)
   |                         đọc id/name của row 1
   |<---------------------- trả Student(1,...)
   |
   | rs.next() → row 2
   +----------------------> mapRow(row 2, 1)
   |<---------------------- trả Student(2,...)
   |
   | rs.next() → row 3
   +----------------------> mapRow(row 3, 2)
   |<---------------------- trả Student(3,...)
   |
   | rs.next() → row 4
   +----------------------> mapRow(row 4, 3)
   |<---------------------- trả Student(4,...)
   |
   | rs.next() → false, kết thúc
   +-- cleanup rồi return List<Student> 4 phần tử
```

Điều kiện cốt lõi: **không có dòng nào trong `mapRow` gọi `next()`**. Callback được phép gọi getter `getString`, `getLong`, `getBigDecimal`, `getObject`… trên các cột đang có, nhưng không được tự chuyển cursor.

## 4. Vì sao gọi rs.next() trong RowMapper là sai?

### Mẫu sai rất dễ viết

```java
RowMapper<Student> wrongMapper = (rs, rowNum) -> {
    rs.next();   // SAI: Spring đã chuyển đến hàng hiện tại trước đó.
    return new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
};
```

Giả sử SQL trả bốn hàng `1,2,3,4`. Lúc Spring đang xử lý hàng 1, mapper tự gọi `next()` sang hàng 2 và tạo Student cho hàng 2; Spring tiếp tục `next()` sang hàng 3; mapper lại tự chuyển sang hàng 4. Kết quả trả về có thể chỉ còn các hàng `2,4`:

| Bước | Cursor do Spring định vị | Mapper sai gọi thêm `next()` | Đối tượng được tạo |
|---|---|---|---|
| 1 | hàng 1 (An) | sang hàng 2 | Bình |
| 2 | hàng 3 (Chi) | sang hàng 4 | Dũng |
| 3 | không còn hàng | không được gọi nữa | kết thúc |

**Điểm nguy hiểm:** hệ thống có thể không ném exception nào; nó chỉ **mất dữ liệu âm thầm**. Nếu số hàng lẻ, mapper sai có thể gọi `next()` tới sau hàng cuối rồi cố đọc getter và nhận SQLException, tùy driver. Với cursor không hỗ trợ di chuyển đặc biệt, các thao tác như `previous()`/`absolute()` còn có thể lỗi ngay.

### Mẫu đúng

```java
RowMapper<Student> correctMapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

**Không dùng `if (rs.next())` để “kiểm tra có hàng không” ở trong mapper.** Nếu mapper đang được gọi, Spring đã định vị một hàng cho nó. Nếu query trả 0 hàng, mapper **không được gọi**; `jdbc.query(...)` trả list rỗng. Trường hợp truy vấn một hàng bắt buộc với `queryForObject(...)` có hợp đồng ngoại lệ riêng.

Không dùng `rs.previous()` để “quay lại hàng vừa bỏ qua”: các ResultSet dạng forward-only phổ biến không cho phép quay lui và việc điều chỉnh con trỏ vẫn vi phạm hợp đồng của RowMapper. Hãy xóa thao tác di chuyển con trỏ trong mapper.

## 5. Chữ ký chính xác của RowMapper<T>

Giao diện cốt lõi:

```java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
```

Đây là **chữ ký rút gọn để minh họa**, không sao chép đầy đủ annotation/nullability/API metadata của phiên bản Spring cụ thể.

- `rs`: ResultSet **đã được định vị tại một hàng hiện tại**. Thao tác chính là đọc các cột của hàng này.
- `rowNum`: số thứ tự hàng **trong quá trình mapping**. Với adapter chuẩn `RowMapperResultSetExtractor` của Spring JDBC, nó bắt đầu từ **0** rồi tăng dần cho các hàng mapper nhận. Nó **không phải** cột `id` trong DB, không phải số thứ tự từ `ROW_NUMBER()` của SQL và không phải `ResultSet.getRow()` (theo JDBC thường bắt đầu 1 nếu có hỗ trợ).
- Giá trị trả về `T`: object đại diện hàng hiện tại. Theo API, mapper có thể trả Java `null`; tuy nhiên DTO non-null thường giảm nhầm lẫn.
- `SQLException`: có thể để Spring nhận và dịch qua `DataAccessException`. Không bắt rồi trả object giả hoặc bỏ hàng trừ khi nghiệp vụ có quy định rõ.

`RowMapper` thường nên **stateless** và có thể tái sử dụng an toàn. Ví dụ static final mapper chỉ phụ thuộc dữ liệu từ ResultSet:

```java
private static final RowMapper<Student> STUDENT_MAPPER =
    (rs, rowNum) -> new Student(
        rs.getLong("id"),
        rs.getString("name")
    );
```

Tuyệt đối không giữ `ResultSet` thành field của object rồi đọc sau khi `query()` trả về: ResultSet đã hết vòng đời và không còn hợp lệ cho kiểu truy cập đó.

## 6. Mỗi callback phù hợp với một mức quyền điều khiển con trỏ

Điểm dễ nhầm là Spring JDBC có nhiều callback nhận `ResultSet`, nhưng **quyền gọi `next()` khác nhau**:

| Callback | Mục tiêu | Có tự gọi `rs.next()` không? | Số lần framework gọi callback |
|---|---|---|---|
| `RowMapper<T>.mapRow(rs, rowNum)` | Map **một hàng** thành object | **Không** | Một lần cho mỗi hàng mapper nhận |
| `RowCallbackHandler.processRow(rs)` | Xử lý **một hàng** không cần trả object | **Không** | Một lần cho mỗi hàng |
| `ResultSetExtractor<T>.extractData(rs)` | Xử lý **toàn bộ ResultSet** thành một kết quả | **Có thể/cần**, khi muốn tự duyệt | Thông thường một lần cho cả result set |
| JDBC thuần `ResultSet` do code tự thực thi `executeQuery()` | Tự xử lý kết quả | **Có**, cần điều khiển cursor | Do code trực tiếp quyết định |
| `PreparedStatementCallback`/`ConnectionCallback` tự gọi `executeQuery()` để nhận ResultSet | Chủ động thực thi và duyệt kết quả tự mở | **Có**, trên ResultSet do callback tạo | Theo logic callback, đồng thời phải tự đóng ResultSet do mình mở |

Nói cách khác: **“không bao giờ gọi `ResultSet.next()`” là sai; quy tắc đúng là “không gọi `next()` trong `RowMapper` và `RowCallbackHandler`”.** Với `ResultSetExtractor` hoặc JDBC thuần, chính bạn cần viết vòng lặp vì callback được giao xử lý toàn tập kết quả.

### 6.1. RowMapper: trả đối tượng mới cho mỗi row

```java
List<Student> students = jdbc.query("""
        SELECT id, name FROM students ORDER BY id
        """,
    (rs, rowNum) -> new Student(
        rs.getLong("id"),
        rs.getString("name")
    )
);
```

Ví dụ này nằm trong class có `JdbcTemplate jdbc`, và record Student được định nghĩa phù hợp. `JdbcTemplate` sẽ tự duyệt mọi row, tạo `List<Student>`. Không tự mở ResultSet và không tự đóng ResultSet mà template đưa cho mapper.

### 6.2. RowCallbackHandler: xử lý row mà không tự next

```java
List<String> names = new ArrayList<>();

jdbc.query(
    "SELECT name FROM students ORDER BY id",
    (RowCallbackHandler) rs -> names.add(rs.getString("name"))
);
```

Dùng khi chỉ muốn tiêu thụ hoặc gom thông tin từng row. Spring cũng định vị cursor và gọi `processRow` với hàng hiện tại. Callback không có tham số `rowNum`, nhưng vẫn **không được gọi `rs.next()`**. Cần thận trọng nếu callback có side effect bên ngoài DB: khi mapper/SQL lỗi giữa chừng, side effect đã thực hiện có thể không được rollback cùng JDBC transaction.

### 6.3. ResultSetExtractor: chủ động duyệt toàn ResultSet

```java
List<String> names = jdbc.query("""
        SELECT name FROM students ORDER BY id
        """,
    (ResultSetExtractor<List<String>>) rs -> {
        List<String> result = new ArrayList<>();
        while (rs.next()) {  // ĐÚNG trong ResultSetExtractor.
            result.add(rs.getString("name"));
        }
        return result;
    }
);
```

Ở đây `extractData` nhận toàn tập, nên **callback phải tự duyệt** nếu muốn lấy từng hàng. Spring vẫn quản lý việc đóng ResultSet/Statement chuẩn sau khi extractor hoàn tất; callback không tự `rs.close()` trên ResultSet do template truyền vào.

Khi dùng các overload `jdbc.query(...)` với lambda, hãy dùng cast/interface tường minh trong các ví dụ dễ gây **overload ambiguity**:
- Lambda `(rs, rowNum) -> ...` nhận **hai tham số** là RowMapper.
- Lambda `rs -> { while (rs.next()) ...; return object; }` là ResultSetExtractor.
- Lambda `(RowCallbackHandler) rs -> ...` một tham số và trả `void` là RowCallbackHandler.

Sự phân biệt này là một trong những cách đọc code review nhanh để biết ai nên điều khiển cursor.

## 7. Ví dụ ứng dụng Spring Boot và Java 17 chạy được

Bài demo dưới đây chạy với Spring Boot 3.3.5 + H2 (JDBC), dùng 4 hàng dữ liệu có thứ tự rõ để tái hiện lỗi mất hàng khi gọi `next()` trong mapper. H2 dùng cho việc học; khi tích hợp vào sản phẩm, cần kiểm thử trên driver/database thực tế. Java 17, Gradle 8.x, môi trường có thể tải dependency là đủ cho dự án mẫu.

### 7.1. Cấu trúc

```text
row-mapper-cursor-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/RowMapperCursorDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'row-mapper-cursor-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:rowmapperdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    age INTEGER
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO students (id, name, age) VALUES (1, 'An', 20);
INSERT INTO students (id, name, age) VALUES (2, 'Binh', NULL);
INSERT INTO students (id, name, age) VALUES (3, 'Chi', 21);
INSERT INTO students (id, name, age) VALUES (4, 'Dung', 22);
```

`src/main/java/example/jdbc/RowMapperCursorDemoApplication.java`:

```java
package example.jdbc;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;

@SpringBootApplication
public class RowMapperCursorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RowMapperCursorDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc) {
        return args -> {
            String sql = "SELECT id, name, age FROM students ORDER BY id";

            RowMapper<Student> goodMapper = (rs, rowNum) ->
                new Student(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getObject("age", Integer.class)
                );

            List<Student> correct = jdbc.query(sql, goodMapper);
            System.out.println("correct=" +
                correct.stream().map(Student::name).toList());

            List<String> rowNumbers = jdbc.query(sql,
                (rs, rowNum) ->
                    rowNum + ":" + rs.getString("name"));
            System.out.println("rowNums=" + rowNumbers);

            // CHỐNG VÍ DỤ: cố ý vi phạm RowMapper contract.
            List<String> wrong = jdbc.query(sql,
                (rs, rowNum) -> {
                    rs.next(); // Không viết trong code production.
                    return rs.getString("name");
                });
            System.out.println("wrong=" + wrong);

            List<String> viaHandler = new ArrayList<>();
            jdbc.query(sql, (RowCallbackHandler) rs ->
                viaHandler.add(rs.getString("name")));
            System.out.println("handler=" + viaHandler);

            ResultSetExtractor<List<String>> extractor = rs -> {
                List<String> result = new ArrayList<>();
                while (rs.next()) {
                    result.add(rs.getString("name"));
                }
                return result;
            };
            System.out.println("extractor=" + jdbc.query(sql, extractor));

            List<String> ageValues = jdbc.query(sql,
                (rs, rowNum) -> {
                    Integer age = rs.getObject("age", Integer.class);
                    return age == null ? "NULL" : age.toString();
                });
            System.out.println("ages=" + ageValues);
        };
    }
}

record Student(long id, String name, Integer age) {}
```

**Chạy:** tại thư mục `row-mapper-cursor-demo`, khi đã cài Gradle bản tương thích:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, có thể chạy `./gradlew bootRun` trên Unix/macOS hoặc `gradlew.bat bootRun` trên Windows.

Sáu dòng ứng dụng in ra **theo đúng thứ tự** dưới đây (ngoài chúng còn có thể có log khởi động/build của Spring/Gradle):

```text
correct=[An, Binh, Chi, Dung]
rowNums=[0:An, 1:Binh, 2:Chi, 3:Dung]
wrong=[Binh, Dung]
handler=[An, Binh, Chi, Dung]
extractor=[An, Binh, Chi, Dung]
ages=[20, NULL, 21, 22]
```

Giải thích:
- `goodMapper` không chạm cursor, nhận đủ 4 hàng.
- `rowNums` cho thấy số thứ tự callback thông thường bắt đầu từ 0.
- `wrong` cố tình gọi thêm `next()`, nên chỉ còn hàng 2 và 4. Đây là **hành vi minh họa được kỳ vọng với ResultSet forward-only** trên demo H2 này; driver khác có thể báo lỗi khi cursor bị đẩy ra ngoài vùng hợp lệ.
- `RowCallbackHandler` cũng đọc đúng 4 hàng mà không gọi `next()`.
- `ResultSetExtractor` tự duyệt bằng `while(rs.next())` và nhận đủ 4 hàng.
- Cột `age` của Binh có SQL NULL, được đọc qua `getObject("age", Integer.class)` thành Java null, rồi trình bày bằng chuỗi "NULL".

**Đặc biệt:** demo intentionally chứa anti-pattern `wrong` để so sánh; tuyệt đối không sao chép mapper sai vào repository thật.

## 8. Cách viết RowMapper chuẩn trong repository

Trong code ứng dụng, hãy tách SQL khỏi mapping và tái sử dụng mapper stateless.

Ví dụ Spring JDBC, dùng bảng `students` từ demo:

```java
// StudentRepository.java
package example.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class StudentRepository {

    private static final RowMapper<Student> STUDENT_MAPPER =
        (rs, rowNum) -> new Student(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getObject("age", Integer.class)
        );

    private final JdbcTemplate jdbc;

    public StudentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Student> findAll() {
        return jdbc.query("""
                SELECT id, name, age
                FROM students
                ORDER BY id
                """, STUDENT_MAPPER);
    }

    public Optional<Student> findById(long id) {
        try {
            Student item = jdbc.queryForObject("""
                    SELECT id, name, age
                    FROM students
                    WHERE id = ?
                    """, STUDENT_MAPPER, id);
            return Optional.of(item);
        } catch (EmptyResultDataAccessException ex) {
            return Optional.empty();
        }
    }
}
```

Nhận xét:
- `findAll()` trả danh sách: nếu bảng trống, Spring trả `List` rỗng, mapper không chạy lần nào.
- `findById()` dùng query tối đa một bản ghi theo `PRIMARY KEY`. Nếu 0 hàng, `queryForObject()` ném `EmptyResultDataAccessException`; vì contract ở đây cho phép vắng mặt, method chuyển riêng nó thành `Optional.empty()`.
- Nếu query trả >1 hàng không đúng kỳ vọng, `IncorrectResultSizeDataAccessException` tiếp tục được truyền lên; đừng biến nó thành “không tìm thấy”.
- `Optional.of(item)` đúng với mapper minh họa luôn tạo `Student` non-null. Một mapper được phép trả `null` cần hợp đồng khác.
- Với `jdbc.query(...)`, template duyệt; cùng mapper được tái sử dụng cho `queryForObject(...)`. **Dù query chỉ một hàng, mapper vẫn không gọi `next()`.**
- SQL bind ID bằng `?`, không nối đầu vào thành câu SQL.

`queryForObject(sql, Student.class, id)` không thay thế `RowMapper<Student>` để mapping nhiều cột; overload `Class<T>` dùng cho kết quả kiểu đơn cột. Mỗi API có contract riêng, không được vì tên “object” mà hiểu thành tự động chuyển mọi row nhiều cột sang Java record.

## 9. rowNum có ý nghĩa gì và không nên dùng thế nào?

Với `JdbcTemplate.query(..., RowMapper<T>)` thông thường, `rowNum` bắt đầu từ `0` cho hàng đầu tiên mapper xử lý và tăng mỗi hàng. Nó hữu ích để log, chẩn đoán hoặc gắn vị trí trong batch đang trả về. Tuy nhiên:

- `rowNum` không phải `id`, không phải primary key.
- `rowNum` không phải thứ tự toàn cục của database hoặc mã định danh bền vững. Hai truy vấn khác nhau có thể trả thứ tự khác nhau nếu không có `ORDER BY`.
- Khi dùng phân trang, mỗi lượt query có thể bắt đầu `rowNum = 0` lại, bất kể đang ở trang số 20.
- Kết quả SQL `ROW_NUMBER() OVER (...)` thường bắt đầu từ 1, độc lập với `rowNum` trong callback.
- `rs.getRow()` theo JDBC báo thứ tự hàng của cursor (thường bắt đầu từ 1), không nên nhầm với `rowNum`.

Nếu cần thứ tự hiển thị ổn định:
1. Định nghĩa `ORDER BY` trong SQL (có khóa phụ để phá hòa khi cần).
2. Dùng một cột kết quả hoặc metadata phân trang để suy ra thứ tự, không gán nhầm rowNum làm business ID.
3. Không dựa vào thứ tự “vốn có” của bảng khi không có ORDER BY.

Ví dụ:

```java
List<String> labels = jdbc.query("""
        SELECT id, name
        FROM students
        ORDER BY id DESC
        """,
    (rs, rowNum) ->
        "index=" + rowNum + ", id=" + rs.getLong("id")
);
```

Với dữ liệu demo, chuỗi sẽ tương ứng `index=0, id=4` rồi `index=1, id=3`…, cho thấy `rowNum` phản ánh vị trí trong kết quả query, **không phải số ID**.

## 10. Getter JDBC và SQL NULL trong mapper

Sai lầm phổ biến khác là đọc kiểu nguyên thủy mà không xử lý SQL NULL:

```java
// Không phân biệt NULL với 0:
int age = rs.getInt("age");
```

JDBC `ResultSet.getInt(...)` trả `0` khi cột SQL NULL; muốn phân biệt, phải gọi `rs.wasNull()` **ngay sau getter vừa đọc**:

```java
int rawAge = rs.getInt("age");
Integer age = rs.wasNull() ? null : rawAge;
```

Nếu driver/type mapping hỗ trợ, `rs.getObject("age", Integer.class)` trả boxed `Integer` hoặc null và giảm mã lặp. Với PostgreSQL, một kiểu JSON/custom enum có thể cần mapper/driver handling khác; hãy dựa vào schema và test tích hợp thay vì kỳ vọng mọi driver chuyển kiểu giống nhau.

Những nguyên tắc kiểm tra mapping:
- Dùng **tên cột/alias** thực sự có trong SQL, ví dụ `SELECT display_name AS name` rồi `rs.getString("name")`.
- Không viết `rs.getString("old_name")` sau khi SQL đã đổi alias; đây là lỗi mapping, không phải lỗi cursor.
- Chọn kiểu `BigDecimal` cho SQL DECIMAL/NUMERIC cần chính xác; chú ý precision/scale.
- Với cột timestamp, xác định rõ timezone và kiểu Java (`LocalDateTime`, `OffsetDateTime`, `Instant`…) theo semantics DB/driver.
- Khi một cột phải NOT NULL, tốt hơn nên dùng constraint tại DB và kiểm tra dữ liệu; đừng tự mặc định null thành 0/chuỗi rỗng nếu không có business rule.
- Mapper chỉ tạo Java DTO/entity mapping đơn giản; tránh gọi API mạng/DB lần nữa trên mỗi row, dễ tạo N+1 query và tăng độ trễ.

**Đọc getter nhiều lần** trên cùng hàng đôi khi khả thi, nhưng hãy tránh lặp lại converter đắt tiền; lưu giá trị cục bộ. Không dùng `rs.next()` để “đọc cột tiếp theo”: các **cột** được truy cập bằng tên hoặc chỉ số cột; `next()` di chuyển sang **hàng khác**.

## 11. Quyền sở hữu tài nguyên JDBC trong RowMapper

`JdbcTemplate` thường lấy connection theo Spring transaction context, tạo statement/resultset, thực thi, duyệt và cleanup các tài nguyên do nó sở hữu. `RowMapper` chỉ được cấp một `ResultSet` tại hàng hiện tại, **không được đóng**:

```java
RowMapper<Student> wrong = (rs, rowNum) -> {
    Student current = new Student(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getObject("age", Integer.class)
    );
    rs.close(); // SAI: đóng ResultSet do JdbcTemplate quản lý.
    return current;
};
```

Cũng không làm việc như:

```java
// SAI: trả ResultSet cho lớp khác để đọc sau khi query kết thúc.
RowMapper<ResultSet> bad = (rs, rowNum) -> rs;
```

Hai ví dụ là **anti-pattern**, không nên chạy trong ứng dụng thật. Khi `JdbcTemplate.query(...)` kết thúc, ResultSet thường được đóng. Một lớp service/HTTP không được giữ tham chiếu đến cursor để gọi getter sau này.

Một mapper tốt trả **dữ liệu tách khỏi cursor** như record/DTO; template chịu trách nhiệm giải phóng tài nguyên. Nếu cần đọc data rất lớn, đừng giữ ResultSet qua nhiều tầng; chọn phân trang, cursor streaming với vòng đời rõ hoặc `queryForStream` và **caller phải đóng `Stream`** bằng try-with-resources:

```java
// Trong class có JdbcTemplate jdbc, RowMapper<Student> STUDENT_MAPPER.
try (java.util.stream.Stream<Student> stream = jdbc.queryForStream("""
        SELECT id, name, age FROM students ORDER BY id
        """, STUDENT_MAPPER)) {
    stream.forEach(student -> process(student));
}
```

`process(student)` là xử lý của ứng dụng đã định nghĩa. Dù được gọi qua `queryForStream`, RowMapper vẫn chỉ map **một hàng đang được driver/template định vị**; nó không có quyền tự `next()`. `queryForStream` sử dụng JDBC blocking, và hiệu quả fetch/streaming phụ thuộc driver và transaction.

## 12. Khi mapper ném SQLException hoặc RuntimeException

`mapRow(...)` được phép khai báo `throws SQLException`. Nếu getter JDBC gặp lỗi, bạn thường không cần bọc `try/catch(SQLException)` trong mọi mapper; `JdbcTemplate` có cơ chế dịch SQLException thành `DataAccessException`.

```java
RowMapper<Student> mapper = (rs, rowNum) ->
    new Student(
        rs.getLong("id"),
        rs.getString("missing_column"), // SQL không chọn cột này.
        rs.getObject("age", Integer.class)
    );
```

Khi query thực thi trên schema demo, đọc `missing_column` có thể gây SQLException; lớp template dịch thành lỗi truy cập dữ liệu thích hợp. **Không** trả Student giả hoặc im lặng bỏ hàng khi mapping thất bại.

Với lỗi từ code Java của ứng dụng, ví dụ:

```java
RowMapper<Student> mapper = (rs, rowNum) -> {
    if (rowNum > 1000) {
        throw new IllegalStateException("Unexpected result size");
    }
    return new Student(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getObject("age", Integer.class));
};
```

Đây là chính sách minh họa, **không nên giới hạn result set ở mapper** vì DB đã thực thi truy vấn và có thể đã tải dữ liệu lớn. Hãy đặt `LIMIT`/pagination/query semantics ở SQL. RuntimeException từ mapper có thể propagate; template vẫn cleanup theo vòng đời. Không catch mọi lỗi rồi trả empty list: điều đó làm che lỗi dữ liệu và khó debug.

### Không tự “fix” việc đọc hàng lỡ bằng try/catch

Mã sau sai về cả cursor lẫn xử lý lỗi:

```java
RowMapper<Student> wrong = (rs, rowNum) -> {
    try {
        if (rs.next()) { // SAI: vượt qua hàng hiện tại.
            return new Student(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getObject("age", Integer.class)
            );
        }
    } catch (SQLException ignored) {
        // SAI: bỏ qua lỗi thật.
    }
    return null;
};
```

Nếu gặp lỗi, cần sửa **mấu chốt** là bỏ `rs.next()`, giữ mapper thuần túy và để lỗi thích hợp được truyền lên. Không biến lỗi cursor thành row null, vì sẽ tạo list có phần tử null khó phát hiện.

## 13. Test contract: xác minh mapper chỉ đọc hàng hiện tại

Một integration test dùng Spring Boot + H2 hoặc DB thật có thể so sánh output với seed cố định. Khi SQL trả 4 hàng, mapper đúng phải trả **đủ 4 record với đúng thứ tự**. Với bài toán cursor, chỉ kiểm tra “list không rỗng” là chưa đủ: mapper sai có thể vẫn trả hai phần tử dù mất hai hàng.

Ví dụ JUnit 5/AssertJ trong project đã có test starter, schema fixture:

```java
// StudentRepositoryTest.java - đoạn class test trong project Spring Boot.
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class StudentRepositoryTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsAllRowsExactlyOnce() {
        List<String> names = jdbc.query("""
                SELECT name FROM students ORDER BY id
                """,
            (rs, rowNum) -> rs.getString("name")
        );

        assertThat(names).containsExactly("An", "Binh", "Chi", "Dung");
    }

    @Test
    void callbackReceivesZeroBasedRowNum() {
        List<Integer> nums = jdbc.query("""
                SELECT id FROM students ORDER BY id
                """,
            (rs, rowNum) -> rowNum
        );

        assertThat(nums).containsExactly(0, 1, 2, 3);
    }
}
```

Test cần `spring-boot-starter-test` trong dependency **testImplementation** và datasource/schema/data fixture được khởi tạo trong test context; trên `@JdbcTest`, Spring Boot thường cấu hình embedded DB nếu có trên classpath và test sẽ quản lý rollback. Không chạy được chỉ với `javac` thuần.

Với test thuần đơn vị của chính mapper, có thể mock `ResultSet` và xác minh mapper **không gọi `next()`**; ví dụ với Mockito:

```java
@Test
void mapperNeverMovesCursor() throws SQLException {
    ResultSet rs = mock(ResultSet.class);
    when(rs.getLong("id")).thenReturn(7L);
    when(rs.getString("name")).thenReturn("An");
    when(rs.getObject("age", Integer.class)).thenReturn(20);

    Student item = STUDENT_MAPPER.mapRow(rs, 0);

    assertEquals("An", item.name());
    verify(rs, never()).next();
}
```

Đoạn này minh họa **body method test** có static Mockito/JUnit imports và mapper đã định nghĩa; không phải file hoàn chỉnh. Tuy nhiên, test logic mapper không thay thế integration test: vẫn cần kiểm tra câu SQL và mapping thực tế trên database.

### Ma trận cần bao phủ

| Dữ liệu SQL | Hành vi mong đợi của RowMapper |
|---|---|
| 0 row | Không được gọi; `query(...)` trả list rỗng |
| 1 row | Được gọi một lần; không gọi next |
| 4 row | Được gọi bốn lần, đủ bốn DTO theo ORDER BY |
| 1 row có nullable column | Map đúng null bằng boxed type/JDBC helper |
| SQL có alias khác tên property | Mapper dùng đúng alias hoặc báo lỗi |
| SQL/cột không hợp lệ | Lỗi được truyền lên; không sinh DTO giả |
| Có duplicate rows theo nghiệp vụ | Query có thể trả nhiều DTO; contract/business xử lý uniqueness, mapper không tự “skip duplicate” |
| Dataset rất lớn | Query được giới hạn/phân trang/stream lifecycle đúng; không dùng mapper để điều khiển số row |

Kiểm thử một bản ghi riêng lẻ **không đủ** để bắt lỗi `next()`; với một row, mapper sai có thể chỉ ném lỗi, còn với nhiều row nó có thể âm thầm bỏ hàng. Vì vậy phải có integration test với **ít nhất 3–4 row**, so sánh đầy đủ ID và thứ tự.

## 14. Những hiểu nhầm thường gặp

**Hiểu nhầm 1: “JDBC phải gọi next() nên RowMapper cũng phải gọi.”**

JDBC thuần đúng là phải tự duyệt, nhưng `JdbcTemplate` đã duyệt và truyền hàng hiện tại cho mapper. Viết `next()` trong RowMapper làm con trỏ tiến hai lần.

**Hiểu nhầm 2: “Nếu không gọi next(), rs.getString sẽ luôn đọc hàng đầu.”**

Không. Spring di chuyển tới từng hàng trước khi mapper được gọi. Cùng một mapper đọc hàng 1, rồi hàng 2, rồi hàng N ở những lần gọi khác nhau.

**Hiểu nhầm 3: “rowNum là số hàng của ResultSet JDBC.”**

`rowNum` là tham số callback do Spring cung cấp; trong extractor chuẩn bắt đầu từ 0. JDBC `ResultSet.getRow()` thường là thứ tự bắt đầu từ 1, còn primary key không phụ thuộc số hàng. Đừng trộn ba giá trị.

**Hiểu nhầm 4: “RowCallbackHandler có thể next() vì không trả object.”**

`RowCallbackHandler.processRow(rs)` cũng chỉ nhận **hàng đã định vị** và không gọi next. Muốn điều khiển toàn tập kết quả, chọn `ResultSetExtractor`.

**Hiểu nhầm 5: “ResultSetExtractor cũng không được next().”**

Ngược lại: `ResultSetExtractor` nhận toàn ResultSet để xử lý, thường dùng `while(rs.next())`. Khác biệt là **đơn vị được giao xử lý**: một hàng so với toàn tập.

**Hiểu nhầm 6: “Nếu mapper sai có exception, luôn biết ngay.”**

Không. Với số hàng chẵn, việc gọi thêm next() có thể làm mất một nửa dữ liệu mà vẫn trả List bình thường. Phải kiểm tra kích thước, ID và thứ tự trong test.

**Hiểu nhầm 7: “Có thể trả ResultSet từ RowMapper để xử lý lazy ở service.”**

ResultSet thuộc JDBC resource scope; template có thể đóng khi query trả về. Mapper phải materialize dữ liệu cần thiết thành DTO, không giữ cursor.

**Hiểu nhầm 8: “@Transactional thay đổi quyền gọi next() trong mapper.”**

Transaction điều phối connection, commit/rollback; nó **không chuyển quyền quản lý ResultSet.next()** sang RowMapper. Luật cursor không thay đổi.

**Hiểu nhầm 9: “Mapper dùng rowNum=0 nên JDBC tự bắt đầu từ row 0.”**

JDBC ResultSet được định vị theo cursor, còn rowNum là chỉ số callback bắt đầu 0 do extractor chuẩn cung cấp. Đây là hai khái niệm khác nhau.

**Hiểu nhầm 10: “Muốn bỏ row không đạt điều kiện thì gọi next() trong mapper.”**

Không. Nếu cần filter, ưu tiên `WHERE` trong SQL. Nếu cần filter logic Java sau truy vấn, map tất cả các row rồi filter List/Stream, cân nhắc chi phí và kích thước tập kết quả. RowMapper không phải iterator cho phép bỏ qua row tùy ý.

## 15. Checklist code review

- [ ] `RowMapper.mapRow(...)` chỉ đọc giá trị của **current row**.
- [ ] Không có `rs.next()`, `rs.previous()`, `rs.absolute()`, `rs.beforeFirst()` hoặc `rs.last()` trong mapper.
- [ ] Không đóng `ResultSet`/`Statement`/`Connection` do `JdbcTemplate` cấp từ mapper.
- [ ] Trả DTO/record tách khỏi ResultSet và đúng kiểu/alias cột.
- [ ] Nullability đã được xử lý: `getObject(..., Integer.class)` hoặc `wasNull()` khi dùng primitive getter.
- [ ] Không dùng `rowNum` làm business ID; SQL có `ORDER BY` nếu thứ tự quan trọng.
- [ ] Không gọi DB/API/network trên mỗi row nếu có thể dùng JOIN/batch/projection.
- [ ] Nếu cần duyệt toàn tập bằng tay, dùng `ResultSetExtractor`/JDBC thấp tầng đúng ownership.
- [ ] Nếu dùng `RowCallbackHandler`, cũng không gọi `next()`.
- [ ] Có test tối thiểu 0, 1 và nhiều hàng, kiểm tra đủ ID/thứ tự, không chỉ kiểm tra non-empty.
- [ ] Có giới hạn/pagination với kết quả lớn; stream phải được close khi API trả Stream.
- [ ] Mapper không nuốt lỗi SQL và không trả dữ liệu giả khi cột/driver thất bại.

## 16. Ghi nhớ và tài liệu tham khảo

**`RowMapper` là “một hàng vào, một object ra”, còn `JdbcTemplate` là bên đi qua các hàng.** Một lời gọi `mapRow(rs, rowNum)` đã nhận `rs` tại hàng cần map, vì vậy **tuyệt đối không gọi `ResultSet.next()` trong RowMapper**. Nếu muốn tự viết vòng `while(rs.next())`, hãy đặt nó ở `ResultSetExtractor` hoặc đoạn JDBC tự điều khiển cursor, không phải ở mapper.

Tài liệu Spring chính thức:
- Spring Framework `RowMapper` Javadoc, mô tả contract “không gọi next()”: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- `RowCallbackHandler` Javadoc, contract của processRow: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- `ResultSetExtractor` Javadoc, xử lý toàn ResultSet: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- `RowMapperResultSetExtractor` Javadoc, adapter mapper cho nhiều hàng: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/RowMapperResultSetExtractor.html
- Spring Framework JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
