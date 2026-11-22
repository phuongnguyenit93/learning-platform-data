# Truy cập dữ liệu là gì và vai trò trong ứng dụng Spring

## 1. Hiểu đúng về truy cập dữ liệu

**Truy cập dữ liệu (data access)** là phần ứng dụng thực hiện thao tác đọc, ghi, tìm kiếm, cập nhật và xóa dữ liệu thông qua một hệ thống lưu trữ: cơ sở dữ liệu quan hệ, cơ sở dữ liệu tài liệu, key-value store hoặc dịch vụ lưu trữ khác. Với cơ sở dữ liệu quan hệ, các thao tác thường liên quan đến câu lệnh SQL, kết nối, kết quả truy vấn và giao dịch (transaction).

Ví dụ, khi người dùng đặt hàng:

1. Ứng dụng đọc thông tin sản phẩm và tồn kho.
2. Kiểm tra quy tắc nghiệp vụ: sản phẩm có bán được không, số lượng còn đủ không.
3. Ghi đơn hàng, dòng hàng và cập nhật tồn kho.
4. Đảm bảo các thay đổi liên quan thành công cùng nhau hoặc được hoàn tác theo ranh giới giao dịch phù hợp.

Việc kiểm tra quy tắc kinh doanh thuộc **tầng nghiệp vụ**; việc làm việc với hệ thống lưu trữ thuộc **tầng truy cập dữ liệu**. Tách hai trách nhiệm này giúp mã dễ hiểu, dễ kiểm thử và có thể thay đổi cách lưu trữ mà ít ảnh hưởng đến nghiệp vụ.

Cần phân biệt:

- **Data access:** cách ứng dụng giao tiếp với nơi lưu trữ, chạy truy vấn và chuyển đổi kết quả.
- **Persistence:** lưu và duy trì trạng thái dữ liệu qua các lần chạy/chấp nhận yêu cầu; thường là mục đích của một phần thao tác data access.
- **Repository/DAO:** lớp hoặc giao diện gom các thao tác dữ liệu cho một nhóm đối tượng/khái niệm; đây là mẫu thiết kế, không mặc nhiên đồng nghĩa với JPA.
- **ORM:** cơ chế ánh xạ đối tượng với dữ liệu quan hệ, ví dụ JPA với Hibernate. ORM là một lựa chọn triển khai data access, không phải bản thân data access.

## 2. Vị trí của data access trong ứng dụng Spring

Một cách tổ chức thường gặp:

```text
HTTP request
    |
    v
Controller (nhận yêu cầu, xác thực/kiểm tra dữ liệu đầu vào)
    |
    v
Service (quy tắc nghiệp vụ, điều phối, ranh giới transaction)
    |
    v
Repository/DAO (truy vấn, lưu, ánh xạ dữ liệu)
    |
    v
JdbcTemplate / JPA EntityManager / Spring Data repository
    |
    v
DataSource / driver / database
```

Ví dụ, phương thức `OrderService.placeOrder()` quyết định có được tạo đơn hàng hay không; `OrderRepository.save(...)` chịu trách nhiệm ghi dữ liệu. Controller không nên chứa SQL hay điều phối nhiều cập nhật cơ sở dữ liệu. Service cũng không cần biết chi tiết `ResultSet` hoặc câu SQL nếu trách nhiệm này đã được đóng gói ở Repository.

Đây là **cách phân chia trách nhiệm phổ biến**, không phải cấu trúc thư mục bắt buộc của Spring. Ứng dụng nhỏ có thể có ít lớp hơn; ứng dụng lớn có thể bổ sung domain model, port/adapter, query service hoặc nhiều nguồn dữ liệu.

## 3. Spring giúp giải quyết những khó khăn nào?

Nếu chỉ dùng JDBC thuần, lập trình viên phải tự tổ chức vòng đời `Connection`, tạo `PreparedStatement`, ánh xạ `ResultSet`, xử lý ngoại lệ và đảm bảo giải phóng tài nguyên. Khi hệ thống lớn hơn, còn phải thống nhất cách quản lý giao dịch và cách sử dụng kết nối giữa nhiều thao tác.

Spring cung cấp các mảnh ghép:

| Thành phần | Vai trò chính |
| --- | --- |
| `DataSource` | Cấp kết nối JDBC đến cơ sở dữ liệu; trong ứng dụng thực tế thường được triển khai bằng connection pool. |
| `JdbcTemplate` | Thực thi SQL/JDBC, xử lý vòng đời tài nguyên, ràng buộc tham số, ánh xạ kết quả và chuyển dịch phần lớn lỗi JDBC thành ngoại lệ của Spring. |
| `NamedParameterJdbcTemplate` | Sử dụng tham số có tên như `:id` thay cho nhiều dấu `?`, thuận tiện cho truy vấn phức tạp. |
| `@Repository` | Đánh dấu thành phần tầng dữ liệu để Spring nhận diện; trong những cơ chế phù hợp còn tham gia chuyển dịch ngoại lệ persistence. Bản thân annotation không tự tạo truy vấn. |
| `@Transactional` và `PlatformTransactionManager` | Khai báo và điều phối ranh giới giao dịch, commit/rollback thông qua transaction manager tương ứng. |
| Spring ORM/JPA integration | Tích hợp `EntityManager`, transaction và quản lý tài nguyên cho JPA. |
| Spring Data (dự án liên quan, không phải toàn bộ Spring Framework lõi) | Cung cấp abstraction repository cho nhiều hệ lưu trữ; Spring Data JPA xây trên JPA và cần JPA provider, thường là Hibernate. |

**Spring Framework không bắt buộc ứng dụng dùng ORM hoặc Spring Data JPA.** Có thể dùng JDBC với Spring, dùng JPA, hoặc kết hợp có chủ đích. **Spring Boot** có thể tự cấu hình `DataSource`, connection pool, `JdbcTemplate` hoặc JPA dựa trên dependency/properties; đó là tiện ích cấu hình của Boot, không thay đổi trách nhiệm của tầng data access.

### Quản lý kết nối và tài nguyên

`DataSource` biểu diễn nguồn kết nối, **không phải chính cơ sở dữ liệu**. Một pool giữ và tái sử dụng kết nối vật lý để giảm chi phí mở kết nối; vẫn cần giới hạn pool, thời gian chờ và đóng tài nguyên đúng cách. `JdbcTemplate` giúp mã ứng dụng không phải tự đóng `ResultSet`/`Statement` cho các thao tác thông thường. Khi có giao dịch Spring, các hoạt động JDBC tương thích sử dụng kết nối được gắn với giao dịch hiện tại thay vì tự tạo các giao dịch rời rạc.

### Xử lý lỗi nhất quán

JDBC truyền thống sử dụng `SQLException` (checked exception). `JdbcTemplate` dịch nhiều lỗi đó sang phân cấp `DataAccessException` (unchecked), ví dụ lỗi khóa trùng hay truy cập tài nguyên thất bại, giúp tầng trên xử lý theo loại lỗi thay vì phụ thuộc mã lỗi của từng hãng cơ sở dữ liệu. Không nên mặc định mọi lỗi database đều có thể retry: lỗi vi phạm unique constraint thường cần sửa dữ liệu, còn lỗi kết nối tạm thời có thể cần retry có kiểm soát.

## 4. Luồng chạy của một thao tác dữ liệu

Khi service gọi repository để lấy danh sách sách:

1. Service gọi phương thức truy cập dữ liệu, trực tiếp hoặc thông qua một bean Spring.
2. `JdbcTemplate` lấy kết nối từ `DataSource` (hoặc dùng kết nối đang thuộc transaction hiện tại).
3. JDBC driver gửi SQL và tham số đến database.
4. Database thực thi truy vấn, áp dụng điều kiện, khóa và quy tắc nhất quán liên quan.
5. `RowMapper` chuyển từng dòng kết quả thành đối tượng Java; `JdbcTemplate` xử lý tài nguyên.
6. Repository trả dữ liệu cho service; service quyết định kết quả cần đưa ra ngoài.

Nếu phương thức được thực thi trong một transaction hợp lệ, transaction manager quyết định commit khi hoàn tất hoặc rollback khi có lỗi phù hợp. **Một lệnh SQL chạy thành công chưa đủ đảm bảo toàn bộ quy trình nghiệp vụ đã thành công**, nhất là khi còn thao tác trên hệ thống bên ngoài như gửi email hoặc gọi API.

## 5. Chọn cách truy cập dữ liệu phù hợp

| Lựa chọn | Phù hợp khi | Điều cần chú ý |
| --- | --- | --- |
| JDBC/`JdbcTemplate` | Muốn kiểm soát SQL và ánh xạ rõ ràng, truy vấn báo cáo, truy cập dữ liệu trực tiếp. | Tự viết SQL và mapping; cần quản lý số lượng truy vấn và schema. |
| JPA với Hibernate (hoặc provider khác) | Mô hình domain có entity, quan hệ và vòng đời đối tượng cần quản lý. | Cần hiểu persistence context, flush, lazy loading, N+1 và SQL thực tế ORM phát ra. |
| Spring Data JPA | Đã chọn JPA và muốn giảm mã repository lặp, hỗ trợ query method, pagination/specification. | Không loại bỏ nhu cầu hiểu JPA, transaction, truy vấn và index. |
| Spring Data cho store khác | Dữ liệu nằm trong MongoDB, Redis hoặc kho dữ liệu được module Spring Data tương ứng hỗ trợ. | Mô hình nhất quán và transaction phụ thuộc từng store. |
| R2DBC với Spring reactive | Cần luồng I/O database không chặn trong kiến trúc reactive end-to-end. | API, driver và quản lý transaction khác JDBC; bọc JDBC blocking bằng kiểu reactive không biến nó thành non-blocking. |

Không có công nghệ tốt nhất cho mọi hệ thống. Điểm xuất phát hợp lý là yêu cầu dữ liệu, độ phức tạp truy vấn, quy mô hệ thống, tính nhất quán và năng lực vận hành. Với những thao tác đọc/ghi SQL rõ ràng, `JdbcTemplate` là cách học tốt vì giúp thấy trực tiếp tương tác giữa Spring và JDBC.

## 6. Ví dụ chạy được: Spring Framework + JdbcTemplate + H2

Ví dụ dùng **Java 17+**, Spring Framework 6.2.x, Gradle và H2 trong bộ nhớ để minh họa một vòng đọc/ghi hoàn chỉnh. Không cần Spring Boot, server HTTP hay database cài sẵn.

Cấu trúc thư mục:

```text
spring-data-access-demo/
├── build.gradle
└── src/main/java/example/DataAccessDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.DataAccessDemo'
}
```

Nội dung `src/main/java/example/DataAccessDemo.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class DataAccessDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:knowledge;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DataAccessDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(200) NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)",
                    1L, "Spring JDBC");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)",
                    2L, "Spring Transactions");

            List<Book> books = jdbc.query(
                    "SELECT id, title FROM books ORDER BY id",
                    (rs, rowNum) -> new Book(
                            rs.getLong("id"),
                            rs.getString("title"))
            );

            System.out.println(books);
        }
    }

    record Book(long id, String title) {}
}
```

Chạy trong thư mục dự án bằng `gradle run` (hoặc `./gradlew run` nếu dự án có Gradle Wrapper). Với dependency đã được tải về, dòng **stdout do chương trình in ra** là:

```text
[Book[id=1, title=Spring JDBC], Book[id=2, title=Spring Transactions]]
```

Giải thích từng mảnh:

- `@Configuration` và `@Bean` đưa `DataSource`, `JdbcTemplate` vào Spring container; `JdbcTemplate` nhận dependency qua method parameter.
- `DriverManagerDataSource` mở kết nối mới theo yêu cầu, phù hợp **demo đơn giản**, không phải connection pool nên không nên dùng kiểu cấu hình này cho tải sản xuất.
- `jdbc.execute(...)` tạo bảng; `jdbc.update(...)` thực thi SQL ghi dữ liệu và trả số dòng bị tác động nếu cần dùng.
- Các dấu `?` được JDBC bind giá trị, giúp tách dữ liệu đầu vào khỏi cú pháp SQL.
- `jdbc.query(...)` sử dụng lambda `RowMapper<Book>` để chuyển mỗi dòng `ResultSet` thành một record bất biến.
- `DB_CLOSE_DELAY=-1` giữ database H2 in-memory tồn tại giữa các lần đóng kết nối trong cùng JVM; dữ liệu **không tồn tại sau khi tiến trình kết thúc**.

Ví dụ tập trung vào cơ chế nên viết câu SQL trong `main`. Với mã ứng dụng thực tế, hãy đưa SQL vào một `BookRepository`, gọi repository từ `BookService`; đặt quy tắc nghiệp vụ và ranh giới giao dịch tại service khi phù hợp.

## 7. Transaction bảo vệ tính nhất quán như thế nào?

Giả sử chuyển tiền giữa hai tài khoản. Hai câu UPDATE độc lập có thể dẫn đến trạng thái sai nếu câu đầu thành công nhưng câu sau thất bại. Một transaction cùng database cần bao trùm cả hai thao tác.

Đoạn sau **chỉ minh họa phương thức tầng service**, không phải chương trình độc lập (giả định đã có `AccountRepository`, và các bean/transaction manager được cấu hình):

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    accountRepository.subtractBalance(fromId, amount);
    accountRepository.addBalance(toId, amount);
}
```

Với JDBC, một cấu hình có thể dùng `DataSourceTransactionManager` cùng `DataSource` và bật `@EnableTransactionManagement`. Khi một phương thức bean được gọi qua Spring transaction proxy, transaction manager bắt đầu/gắn kết transaction, sau đó commit hoặc rollback theo quy tắc đã cấu hình.

Những điểm phải hiểu:

- Mặc định `@Transactional` rollback với `RuntimeException` và `Error`; checked exception thông thường **không** mặc định kích hoạt rollback. Có thể chỉ định `rollbackFor` khi cần.
- Gọi từ một phương thức sang phương thức `@Transactional` khác **trong cùng đối tượng** (self-invocation) thường bỏ qua proxy, nên annotation ở phương thức được gọi không tự mở transaction mới trong cơ chế proxy mặc định.
- `@Transactional(readOnly = true)` chủ yếu là gợi ý tối ưu hóa cho framework/driver/provider; không được coi là cơ chế kiểm soát quyền ghi phổ quát.
- Một local database transaction không mặc nhiên rollback được HTTP call, email hoặc thay đổi ở cơ sở dữ liệu khác. Những luồng đa hệ thống có thể cần outbox, saga hoặc thiết kế bù trừ.
- Transaction và locking không thay thế kiểm tra cạnh tranh, unique constraint hay thiết kế isolation phù hợp.

## 8. Các nguyên tắc thiết kế và vận hành

**Đóng gói trách nhiệm.** Repository chỉ nên cung cấp thao tác dữ liệu có ý nghĩa (`findById`, `save`, `findAvailableStock`). Service điều phối use case. Tránh để controller lắp ghép truy vấn SQL và tự xử lý commit.

**Tách truy vấn và quy tắc nghiệp vụ.** Một điều kiện lọc thuộc truy vấn nên thực thi tại database để tránh tải quá nhiều dữ liệu. Những quy tắc nghiệp vụ có thể cần dữ liệu từ nhiều repository nên nằm ở service/domain. Không biến repository thành nơi chứa mọi quyết định nghiệp vụ.

**Bảo mật truy vấn.** Dùng parameter binding cho **giá trị** (`WHERE id = ?`), không ghép chuỗi từ đầu vào người dùng. Placeholder không thể thay thế tùy ý tên bảng/tên cột; nếu cần sort theo cột động, hãy dùng allowlist cho định danh SQL. Cấu hình tài khoản database có quyền tối thiểu và quản lý secret ngoài source code.

**Chú ý hiệu năng.** Tránh query trong vòng lặp khi có thể dùng batch hoặc truy vấn tập hợp. Với ORM, kiểm tra N+1, lazy loading và SQL phát sinh. Sử dụng pagination cho tập kết quả lớn; tạo index dựa trên truy vấn thực tế và kiểm tra execution plan khi cần.

**Quản lý pool và transaction.** Pool quá nhỏ có thể gây nghẽn, quá lớn có thể làm database quá tải. Transaction giữ kết nối lâu làm giảm thông lượng; tránh thực hiện network call chậm trong transaction nếu không cần. Theo dõi timeout, số kết nối đang dùng, thời gian truy vấn và lỗi.

**Dữ liệu và lỗi.** Ràng buộc schema (primary key, foreign key, NOT NULL, unique) là một tuyến phòng thủ quan trọng. Phân biệt lỗi dữ liệu không hợp lệ, xung đột đồng thời và lỗi hạ tầng tạm thời. Retry phải có giới hạn và xét tính idempotent của thao tác.

**Kiểm thử.** Unit test service có thể thay repository bằng fake/mock để kiểm tra nhánh nghiệp vụ. Integration test repository nên chạy với database thật hoặc tương thích gần môi trường vận hành; H2 tiện cho demo nhưng khác PostgreSQL/MySQL về kiểu dữ liệu, dialect, khóa và transaction. Kiểm tra cả trường hợp thành công, lỗi ràng buộc và rollback, không chỉ đọc/ghi happy path.

## 9. Sai lầm phổ biến và cách sửa

| Hiểu nhầm/sai lầm | Cách hiểu đúng |
| --- | --- |
| “Dùng Spring tức là dùng Hibernate.” | Spring hỗ trợ JDBC, JPA và nhiều cơ chế khác; Hibernate chỉ là một JPA provider phổ biến. |
| “Có `@Repository` thì Spring tự sinh SQL.” | Annotation đánh dấu vai trò; sinh/triển khai truy vấn tùy Spring Data, ORM hoặc mã repository cụ thể. |
| “Mỗi `JdbcTemplate.update` là một transaction nghiệp vụ hoàn chỉnh.” | Cần xác định ranh giới transaction của toàn bộ use case; nhiều câu lệnh có thể phải commit/rollback cùng nhau. |
| “Đặt `@Transactional` ở đâu cũng có tác dụng.” | Phụ thuộc cấu hình transaction, loại bean, proxy và đường gọi; self-invocation là bẫy thường gặp. |
| “Dùng ORM sẽ không cần xem SQL.” | ORM vẫn gửi SQL và có thể tạo N+1, join không phù hợp hoặc cập nhật ngoài dự kiến. |
| “In-memory H2 giống hệt database production.” | Đây là công cụ học/test có giới hạn; cần kiểm thử thêm trên hệ quản trị đích. |
| “Dấu `?` cho phép truyền mọi mảnh SQL.” | Prepared-statement parameter chỉ bind giá trị, không thay tên bảng/cột hay cú pháp SQL động. |

## 10. Câu hỏi tự kiểm tra

1. Trong luồng Controller → Service → Repository, tầng nào quyết định quy tắc tạo đơn hàng, tầng nào truy vấn dữ liệu?
2. `DataSource`, `JdbcTemplate` và `RowMapper` chịu trách nhiệm gì khác nhau?
3. Nếu một use case cần ghi ba bảng, điều gì xảy ra khi thao tác thứ hai thất bại mà không có transaction chung?
4. Vì sao `JdbcTemplate` và Spring Data JPA đều là lựa chọn data access nhưng có mức abstraction khác nhau?
5. Khi nào nên kiểm tra SQL, index, N+1 hoặc kích thước connection pool thay vì chỉ chỉnh mã Java?

**Ghi nhớ:** Trong ứng dụng Spring, truy cập dữ liệu là ranh giới kết nối logic nghiệp vụ với hệ thống lưu trữ. Spring làm nhẹ việc quản lý tài nguyên, truy vấn, ánh xạ, ngoại lệ và transaction; lập trình viên vẫn phải quyết định mô hình dữ liệu, ranh giới nhất quán, tính đúng đắn, bảo mật và hiệu năng.
