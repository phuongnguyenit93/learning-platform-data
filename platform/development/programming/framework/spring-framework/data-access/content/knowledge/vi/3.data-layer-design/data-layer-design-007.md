# Trả về dữ liệu độc lập với tài nguyên đã đóng

## 1. Vấn đề: đối tượng còn tồn tại nhưng dữ liệu có thể đã hết hiệu lực

Trong tầng truy cập dữ liệu của Spring Framework, một phương thức đọc database thường dùng tài nguyên có vòng đời ngắn: JDBC Connection, Statement, ResultSet; với JPA là EntityManager, persistence context và các quan hệ tải lười (lazy loading). Những tài nguyên này phải được đóng hoặc trả về pool sau khi hoàn tất công việc. Nhưng đối tượng mà service trả cho tầng gọi vẫn cần đọc được dữ liệu.

**Nguyên tắc thiết kế:** hoàn tất việc đọc, chuyển đổi và sao chép những giá trị cần thiết **khi tài nguyên còn hợp lệ**; phương thức public trả về DTO/value object đã có đủ dữ liệu cho mục đích của người gọi. Người gọi không cần ResultSet, Connection, EntityManager hoặc một phiên làm việc với database để đọc các trường được công bố.

Ví dụ: màn hình danh sách sách cần id, tiêu đề và giá. Repository phải lấy ba giá trị này trong lúc ResultSet đang mở, tạo các BookView rồi trả về List<BookView>. Sau khi JDBC đóng ResultSet và transaction hoàn tất, màn hình vẫn đọc được tiêu đề/giá. Nếu repository trả ResultSet, Stream đang truy vấn database hoặc một đối tượng đợi truy cập quan hệ lazy, tầng trên có thể gặp lỗi khi tài nguyên đã đóng.

Đây là vấn đề **ranh giới vòng đời (resource lifetime)**, không chỉ là vấn đề đóng kết nối. Các câu hỏi phải trả lời trước khi thiết kế API đọc dữ liệu:

1. Dữ liệu nào người gọi thực sự cần và cần tải đến mức nào?
2. Những giá trị nào đã được materialize thành Java object, những giá trị nào còn phải truy vấn khi được truy cập?
3. Ai sở hữu việc đóng ResultSet, Stream, Connection hay persistence context?
4. Kết quả có cần bất biến để không bị thay đổi sau khi thoát phương thức không?
5. Nếu kết quả rất lớn, nên phân trang, tải theo lô hay xử lý luồng trong transaction?

## 2. Phân biệt dữ liệu độc lập và dữ liệu còn phụ thuộc tài nguyên

| Giá trị trả về | Dùng sau khi tài nguyên dữ liệu đã đóng? | Điều kiện/lưu ý |
| --- | --- | --- |
| String, primitive, BigDecimal, LocalDate đã đọc từ ResultSet | Có | Là giá trị Java đã được lấy ra; không cần JDBC gọi lại. |
| Record/DTO chỉ chứa các giá trị đã đọc | Có | Không giữ JDBC handle, proxy lazy hoặc thành phần có cách đọc trì hoãn. |
| List<DTO> được JdbcTemplate.query ánh xạ xong | Có | Mỗi phần tử đã materialize; cần cân nhắc dung lượng nếu dữ liệu lớn. |
| ResultSet, Statement, Connection | Không | Đây là các JDBC handle gắn với tài nguyên có vòng đời hữu hạn. |
| Stream do JdbcTemplate.queryForStream cung cấp | Không nên chuyển ra ngoài phạm vi sở hữu tài nguyên | Stream còn gắn với ResultSet/Statement; phải đóng bằng try-with-resources sau khi dùng xong. |
| Stream tạo từ List<DTO> đã nạp xong | Có, nếu DTO độc lập | Dữ liệu nguồn đã có trong bộ nhớ; đây không phải JDBC stream. |
| JPA entity với trường scalar đã được nạp | Có thể đọc những giá trị đã nạp | Entity có thể detached; những quan hệ lazy chưa khởi tạo là vấn đề riêng. |
| Quan hệ lazy chưa nạp trên JPA entity đã detached | Không an toàn | Có thể phát sinh LazyInitializationException khi truy cập sau khi persistence context không còn khả dụng. |
| JDBC Blob/Clob locator hoặc InputStream đọc từ database | Không mặc nhiên | Có thể phụ thuộc connection/statement/locator; phải tiêu thụ hoặc chuyển dữ liệu trong phạm vi còn hợp lệ. |
| byte[] đã đọc toàn bộ từ cột binary | Có | Không còn phụ thuộc JDBC, nhưng byte[] là mutable và có thể tốn nhiều bộ nhớ. |

Không nên kết luận “bất kỳ entity JPA nào cũng hỏng khi transaction kết thúc”. Phần dữ liệu đã khởi tạo thường vẫn đọc được sau khi entity detached. Rủi ro nằm ở thao tác khiến ORM phải tải thêm dữ liệu hoặc thay đổi trạng thái thông qua persistence context đã không còn khả dụng. Cũng không nên kết luận “có @Transactional là mọi dữ liệu trả về đều an toàn”; annotation không tự materialize dữ liệu bị trì hoãn.

## 3. Dòng thời gian đúng trong Spring JDBC

Một truy vấn bình thường bằng JdbcTemplate có đường đi sau:

~~~text
Caller
  │
  ▼
BookCatalogService.listBooks()      ← @Transactional(readOnly = true)
  │
  ▼
BookRepository.findAll()
  │  JdbcTemplate mượn Connection từ DataSource/transaction
  │  Statement thực thi SELECT và tạo ResultSet
  │  RowMapper đọc từng hàng, tạo BookView thuần Java
  │  JdbcTemplate thu thập List<BookView>
  │  ResultSet/Statement được đóng
  ▼
List<BookView> đã đủ dữ liệu
  │
  ▼
Service trả về List.copyOf(...)
  │  Transaction kết thúc; Connection được release về DataSource/pool
  ▼
Caller đọc List<BookView>              ← không phát sinh truy vấn mới
~~~

Nếu không có transaction, JdbcTemplate vẫn tự tổ chức phần lấy và release kết nối cho một truy vấn; cơ chế đóng và ánh xạ ResultSet vẫn đúng. Nếu có transaction, Spring giữ connection gắn với transaction cho đến khi transaction kết thúc. Quan trọng là thời điểm RowMapper đọc giá trị xảy ra **trước** lúc ResultSet bị đóng.

### Phản ví dụ: trả về ResultSet đã đóng

Đoạn Java sau **chỉ minh họa lỗi**; giả sử các import JDBC/DataSource và các khai báo lớp đã tồn tại:

~~~java
ResultSet findBooksWrong(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, title, price FROM books");
         ResultSet resultSet = statement.executeQuery()) {

        return resultSet; // Sai: tài nguyên bị đóng trước khi caller dùng.
    }
}
~~~

Cú pháp có thể biên dịch, nhưng khi lệnh return hoàn tất, Java thực hiện đóng các tài nguyên trong try-with-resources. Caller nhận tham chiếu đến một ResultSet đã đóng và đọc nó có thể ném SQLException (thông báo cụ thể tùy driver).

Cách đúng là đọc dữ liệu trong khối try rồi trả về những giá trị Java:

~~~java
List<BookView> findBooksWithPlainJdbc(DataSource dataSource)
        throws SQLException {
    List<BookView> result = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "SELECT id, title, price FROM books ORDER BY id");
         ResultSet rs = statement.executeQuery()) {

        while (rs.next()) {
            result.add(new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")));
        }
    }
    return List.copyOf(result);
}
~~~

Đây cũng là **đoạn minh họa trong một lớp**, dùng BookView và cần import DataSource, SQLException, ArrayList, List cùng java.sql.*. Nó cho thấy quy tắc vòng đời; trong Spring nên dùng JdbcTemplate để giảm mã đóng tài nguyên, mapping và xử lý SQLException.

## 4. Ví dụ Spring JDBC hoàn chỉnh, chạy được bằng Java 21

Ta xây ứng dụng console đọc danh sách sách từ H2. Method service có transaction chỉ đọc; sau khi method trả về, runner chứng minh transaction không còn active nhưng vẫn đọc được DTO.

Cấu trúc tối thiểu:

~~~text
book-data-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/dataaccess/
    │   ├── BookCatalogApplication.java
    │   ├── BookView.java
    │   ├── BookRepository.java
    │   └── BookCatalogService.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

### 4.1. Cấu hình Gradle và H2

Tệp settings.gradle:

~~~groovy
rootProject.name = 'book-data-demo'
~~~

Tệp build.gradle:

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

Tệp src/main/resources/application.properties:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:bookdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

Tệp src/main/resources/schema.sql:

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Tệp src/main/resources/data.sql:

~~~sql
INSERT INTO books (id, title, price) VALUES
    (1, 'Spring JDBC', 129.00),
    (2, 'Transaction Basics', 89.50);
~~~

Ứng dụng console sử dụng database trong bộ nhớ. Mỗi lần khởi động ở tiến trình mới, Spring Boot khởi tạo schema rồi nạp hai dòng dữ liệu mẫu. Không cần máy chủ database riêng.

### 4.2. DTO thuần Java

Tệp src/main/java/example/dataaccess/BookView.java:

~~~java
package example.dataaccess;

import java.math.BigDecimal;

public record BookView(long id, String title, BigDecimal price) {
}
~~~

BookView không có ResultSet, EntityManager, supplier hay proxy để chạy truy vấn sau này. Các trường long, String và BigDecimal là những giá trị đã đọc và không có khả năng “tự fetch” thêm dữ liệu. Record cho ta một carrier đơn giản, nhưng record **không mặc nhiên deep-immutable** nếu trường của nó là List mutable, Date mutable, byte[] hoặc một entity/proxy.

### 4.3. Repository ánh xạ ngay khi ResultSet còn sống

Tệp src/main/java/example/dataaccess/BookRepository.java:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {
    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<BookView> findAll() {
        return jdbc.query("""
                SELECT id, title, price
                FROM books
                ORDER BY id
                """,
                (rs, rowNum) -> new BookView(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getBigDecimal("price")));
    }
}
~~~

JdbcTemplate chịu trách nhiệm tạo PreparedStatement/ResultSet phù hợp với truy vấn và đóng chúng khi query kết thúc. RowMapper chạy trong lúc ResultSet còn mở, chuyển từng dòng thành một BookView. Phương thức query trả về một List đã materialize. Không đặt ResultSet vào trường của DTO; cũng không cất RowMapper để dùng lại chính ResultSet sau đó.

### 4.4. Service chốt dữ liệu trước khi transaction kết thúc

Tệp src/main/java/example/dataaccess/BookCatalogService.java:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class BookCatalogService {
    private final BookRepository repository;

    public BookCatalogService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<BookView> listBooks() {
        System.out.println("Trong transaction: "
                + TransactionSynchronizationManager
                        .isActualTransactionActive());

        List<BookView> books = repository.findAll();
        return List.copyOf(books);
    }
}
~~~

List.copyOf tạo list không thể thay đổi cấu trúc bằng add/remove/set và tránh để caller sửa container mà service trả ra. Trong ví dụ này, các phần tử BookView cũng chỉ chứa kiểu bất biến. Với List<MutableEntity>, List.copyOf **không** khiến từng entity trở nên bất biến: phải ánh xạ và sao chép sâu những trường cần bảo vệ.

readOnly = true biểu thị ý định chỉ đọc và có thể được transaction manager/driver tối ưu; không phải cơ chế bảo đảm rằng mọi lệnh ghi bị chặn. Điều bảo đảm dữ liệu có thể đọc sau transaction là repository đã chuyển toàn bộ giá trị cần dùng thành DTO.

### 4.5. Runner đọc dữ liệu sau khi service hoàn tất

Tệp src/main/java/example/dataaccess/BookCatalogApplication.java:

~~~java
package example.dataaccess;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
public class BookCatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookCatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookCatalogService service) {
        return args -> {
            List<BookView> books = service.listBooks();

            System.out.println("Ngoài transaction: "
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println("Số sách: " + books.size());
            System.out.println("Sách đầu: " + books.get(0).title());
        };
    }
}
~~~

Chạy với JDK 21 và Gradle tương thích Java 21 (ví dụ Gradle 8.5), tại thư mục book-data-demo:

~~~bash
gradle bootRun
~~~

Bốn dòng do chương trình in:

~~~text
Trong transaction: true
Ngoài transaction: false
Số sách: 2
Sách đầu: Spring JDBC
~~~

Đây là kết quả dự kiến của runner chạy ngoài mọi transaction khác, gọi service thông qua Spring bean proxy. Nếu có transaction bên ngoài bao trùm cả caller thì trạng thái ngoài service có thể khác. Trong ví dụ độc lập này, kết quả chứng minh List<BookView> có thể sử dụng khi transaction của service đã kết thúc. **Không cần giữ connection mở để phục vụ tầng giao diện.**

## 5. Kết quả truy vấn dạng Stream: khác biệt quan trọng

Spring JdbcTemplate có phương thức queryForStream. Không giống List từ query, Stream này đang gắn với truy vấn và cần đóng khi sử dụng xong. Nếu service trả thẳng Stream cho controller rồi kết thúc transaction, người gọi có thể bắt đầu duyệt quá muộn, khi connection/ResultSet không còn hợp lệ; hoặc bỏ quên close gây giữ tài nguyên.

Một phương thức **không nên công bố** nếu người gọi dự kiến xử lý Stream bên ngoài phạm vi JDBC:

~~~java
// Minh họa cách thiết kế API dễ lỗi, không phải ví dụ cần sử dụng.
@Transactional(readOnly = true)
public Stream<BookView> listBooksAsOpenStream() {
    return jdbc.queryForStream(
            "SELECT id, title, price FROM books",
            (rs, rowNum) -> new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")));
}
~~~

Khi return, transaction proxy có thể hoàn thành transaction; không có gì bảo đảm caller duyệt Stream trước thời điểm tài nguyên bị release. Hơn nữa Stream không được đóng tại nơi tạo ra nó.

**Cách an toàn khi muốn xử lý dữ liệu theo luồng:** xử lý và đóng Stream **bên trong** phương thức đang sở hữu truy vấn và transaction. Đoạn dưới là phương thức minh họa có thể đặt trong một Spring bean có trường JdbcTemplate jdbc, với các import Stream, Transactional và BookView:

~~~java
@Transactional(readOnly = true)
public long countBooksWithinTransaction() {
    try (Stream<BookView> stream = jdbc.queryForStream(
            "SELECT id, title, price FROM books",
            (rs, rowNum) -> new BookView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getBigDecimal("price")))) {

        return stream.count();
    }
}
~~~

try-with-resources gọi Stream.close() ngay cả khi gặp exception trong lúc tiêu thụ. Hàm này trả về long đã tính xong, độc lập với Stream và JDBC. Phương thức cần được gọi qua Spring proxy để @Transactional có hiệu lực trong cấu hình proxy thường gặp. Đếm hàng thuần túy trong production thường nên dùng SELECT COUNT(*) thay cho duyệt tất cả; đoạn trên chỉ để diễn giải vòng đời Stream.

Lưu ý thêm:

- **Stream do một List<DTO> đã materialize tạo ra** thì không còn phụ thuộc database; chẳng hạn sau khi nhận List từ listBooks, caller có thể tự gọi stream() trên list.
- JDBC streaming không tự đồng nghĩa với dùng rất ít bộ nhớ: driver có thể buffer bản ghi; fetch size và hành vi cursor thay đổi theo database/driver.
- Với dữ liệu cực lớn, dùng phân trang/keyset pagination hoặc xử lý tuần tự trong một phạm vi transaction được kiểm soát. Không trả một Stream đang giữ connection cho lớp trình bày chạy không xác định thời gian.

## 6. JPA/Hibernate: entity detached và quan hệ lazy

Với JPA, một entity có thể còn tồn tại trong bộ nhớ sau khi persistence context kết thúc. Những trường scalar đã nạp của nó vẫn có giá trị, nhưng khi code gọi quan hệ lazy chưa khởi tạo, Hibernate thường phải truy vấn tiếp. Nếu không còn session có thể phục vụ truy vấn, thao tác đó có thể báo LazyInitializationException.

Ví dụ tình huống:

~~~text
Service trong transaction:
  OrderEntity order = repository.findById(id).orElseThrow()
  return order

Controller/serializer sau transaction:
  order.getLines()       ← lines chưa được tải
  cần truy vấn tiếp       ← persistence context có thể đã đóng
  LazyInitializationException
~~~

Trong ứng dụng web, Open Session in View (OSIV) có thể giữ persistence context mở qua giai đoạn render/serialize và che giấu truy vấn phát sinh muộn. Không nên dựa vào OSIV để xác định hợp đồng API hoặc giải quyết N+1; request web có thể phát sinh truy vấn khó kiểm soát ngoài service transaction. Cấu hình OSIV và framework/provider quyết định vòng đời thực tế, nên lỗi không luôn xuất hiện trong mọi môi trường.

### Cách thiết kế DTO snapshot trước khi rời transaction

Mẫu dưới đây **minh họa một service JPA**, không phải chương trình độc lập: giả sử đã có entity OrderEntity với getLines(), LineEntity với getSku()/getQuantity() và Spring Data repository cho OrderEntity.

~~~java
record LineSnapshot(String sku, int quantity) {}

record OrderSnapshot(long id, List<LineSnapshot> lines) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

@Transactional(readOnly = true)
public OrderSnapshot findOrderSnapshot(long id) {
    OrderEntity order = orderRepository.findById(id).orElseThrow();

    List<LineSnapshot> lines = order.getLines().stream()
            .map(line -> new LineSnapshot(
                    line.getSku(), line.getQuantity()))
            .toList();

    return new OrderSnapshot(order.getId(), lines);
}
~~~

Tất cả thao tác truy cập quan hệ lazy cần thiết diễn ra bên trong transaction, khi entity còn gắn với persistence context. Kết quả là những scalar và LineSnapshot thuần Java; khi service trả về, caller không phải chạm vào proxy lazy. DTO còn giới hạn dữ liệu được công khai, tránh vô ý serialize toàn bộ graph entity.

Với một đơn, tải lines trong service có thể hợp lý. Với danh sách nhiều đơn, gọi getLines() trên từng entity có thể tạo N+1 SELECT. Hãy chủ động chọn fetch plan: JPQL projection trả thẳng DTO, fetch join, @EntityGraph hoặc truy vấn theo batch tùy ngữ cảnh. Quan trọng nhất là **thiết kế phần dữ liệu cần trả, materialize đúng thời điểm**, chứ không mặc định tải toàn bộ quan hệ EAGER (dễ tăng chi phí và kích thước graph).

Cũng cần phân biệt snapshot DTO với snapshot transaction của database. DTO là ảnh chụp các giá trị đã đọc; nếu database thay đổi sau đó, DTO không tự cập nhật. @Transactional(readOnly = true) không tự bảo đảm nhiều truy vấn nhìn thấy cùng phiên bản dữ liệu: điều đó còn phụ thuộc isolation, loại database và cách truy vấn.

## 7. Dữ liệu lồng nhau, dữ liệu mutable và cột dung lượng lớn

### 7.1. Danh sách con và tập dữ liệu nhiều cấp

DTO chứa List hay Map chỉ thật sự độc lập nếu từng phần tử cần dùng đã được materialize và không còn giữ proxy/lazy loader. Ví dụ một OrderSnapshot gồm List<LineSnapshot> an toàn khi LineSnapshot chỉ chứa String, int, BigDecimal. Ngược lại, List<OrderEntity> đã copy chỉ mới bảo vệ **cấu trúc danh sách**, chưa bảo vệ quan hệ lazy trong từng entity.

Với các trường nullable, hãy định nghĩa rõ ý nghĩa null, danh sách rỗng và dữ liệu không tồn tại. Tránh đặt một Supplier hoặc Function vào DTO để “tải lại khi cần”, vì việc này tái tạo phụ thuộc vào service/session về sau.

### 7.2. Mảng, đối tượng mutable và phòng vệ bản sao

Khi RowMapper lấy byte[] từ cột binary, mảng đó đã được nạp nhưng vẫn sửa được. Nếu DTO trả trực tiếp tham chiếu mảng, caller có thể thay đổi nội dung DTO. Để tránh, sao chép khi tạo và khi trả mảng ra:

~~~java
public record BinarySnapshot(byte[] content) {
    public BinarySnapshot {
        content = content == null ? null : content.clone();
    }

    @Override
    public byte[] content() {
        return content == null ? null : content.clone();
    }
}
~~~

Đoạn record trên là Java 17+ độc lập khi đặt trong BinarySnapshot.java. Nó minh họa **độc lập vòng đời** và **bất biến đối với người gọi** là hai mục tiêu khác nhau. Với bộ sưu tập nhiều cấp hoặc object mutable khác, cần quyết định rõ có sao chép sâu, ánh xạ sang kiểu bất biến hay chỉ cung cấp một view đọc.

### 7.3. BLOB/CLOB và tải dữ liệu lớn

JDBC Blob/Clob có thể là locator gắn với connection. Tương tự, InputStream đọc từ database có thể cần tài nguyên còn mở. Đừng trả raw Blob/Clob/InputStream và giả định caller có thể dùng tùy ý sau khi repository đóng JDBC. Nếu dữ liệu nhỏ và giới hạn được, đọc đủ byte[]/String trong RowMapper và trả DTO có bản sao thích hợp.

Nếu là ảnh, tệp hay báo cáo lớn, nạp toàn bộ vào byte[] có thể gây áp lực bộ nhớ. Lúc đó thiết kế API streaming có **chủ sở hữu rõ ràng của transaction, connection và close** hoặc chuyển tài liệu sang object storage và trả metadata/đường dẫn truy cập phù hợp. Không trộn vòng đời download dài với transaction truy vấn kéo dài không cần thiết.

## 8. Ranh giới transaction không đồng nghĩa với ranh giới object

Một số nhầm lẫn dễ gặp:

**Nhầm 1: “Trả một entity JPA thì entity luôn chết khi transaction đóng.”** Sai. Một entity detached vẫn là object Java; dữ liệu đã tải thường vẫn đọc được. Lỗi tiềm ẩn nằm ở lazy association, dirty checking không còn tự đồng bộ, hoặc việc gọi thao tác yêu cầu persistence context.

**Nhầm 2: “Có @Transactional trên phương thức thì trả Stream nào cũng ổn.”** Sai. Với proxy transaction, transaction bao phủ **lúc thực thi phương thức**. Khi phương thức trả Stream còn đang truy vấn, caller tiêu thụ Stream sau thời điểm transaction đã kết thúc. Duyệt trong cùng phương thức và đóng Stream, hoặc trả List/Page DTO đã tải.

**Nhầm 3: “Giữ Connection không đóng sẽ tránh lỗi.”** Đây là cách gây rò rỉ connection, làm cạn pool và giảm khả năng phục vụ. Cách sửa là chọn dữ liệu và materialize trong vòng đời tài nguyên được kiểm soát.

**Nhầm 4: “List.copyOf biến toàn bộ đồ thị object thành immutable.”** Chỉ danh sách trở thành không thể chỉnh sửa cấu trúc. Các phần tử, mảng và entity có thể vẫn mutable hoặc lazy.

**Nhầm 5: “DTO đã materialize đồng nghĩa dữ liệu luôn mới.”** DTO độc lập cho phép đọc ổn định mà không đụng database; nó không tự làm mới khi bản ghi trong database thay đổi. Nếu cần dữ liệu mới, phải thực hiện truy vấn mới hoặc dùng chiến lược cache/invalidation có chủ đích.

**Nhầm 6: “Cứ tải hết quan hệ trước khi trả là tốt nhất.”** EAGER mọi nơi làm tăng truy vấn, join lớn và memory. Hãy thiết kế DTO theo use case, chỉ tải thông tin cần, dùng phân trang khi tập dữ liệu lớn.

**Nhầm 7: “Tự gọi một phương thức @Transactional trong cùng lớp chắc chắn mở transaction mới.”** Với Spring proxy mặc định, self-invocation thường không đi qua proxy nên annotation trên phương thức được tự gọi không phát huy như mong muốn. Đặt ranh giới transaction ở một phương thức public được gọi qua bean Spring khác, hoặc dùng kiến trúc/proxy phù hợp.

## 9. Kiểm tra hành vi và lựa chọn thiết kế theo tình huống

| Tình huống | Cách làm phù hợp | Vì sao |
| --- | --- | --- |
| API cần trả 20 cuốn sách | JdbcTemplate.query → List<BookView> | Toàn bộ 20 DTO được ánh xạ trước khi tài nguyên đóng. |
| Trang danh sách cần 10.000 sách | Truy vấn phân trang + List<DTO> mỗi trang | Kết quả độc lập nhưng không giữ 10.000 object trong một response. |
| Xử lý tuần tự hàng triệu dòng | Stream/cursor được duyệt và đóng trong phạm vi sở hữu tài nguyên, hoặc batch | Không xuất bản handle còn sống; kiểm soát connection, transaction và bộ nhớ. |
| Trả JPA Order cùng các dòng hàng | DTO projection hoặc materialize OrderSnapshot trong service | Caller không kích hoạt lazy query sau transaction. |
| Trả tệp nhị phân dung lượng nhỏ | Đọc đầy đủ byte[] rồi copy khi cần | Không giữ Blob locator và không để thay đổi dữ liệu ngoài ý muốn. |
| Tệp rất lớn | Streaming có lifecycle rõ hoặc lưu tệp ngoài database | Tránh load toàn bộ vào RAM và tránh transaction dài. |

Để tự kiểm tra ví dụ hoàn chỉnh ở mục 4:

1. Chạy ứng dụng và kiểm tra dòng “Trong transaction: true”, rồi “Ngoài transaction: false”.
2. Kiểm tra List<BookView> vẫn có hai sách, và tiêu đề đầu là Spring JDBC, dù transaction service đã hoàn tất.
3. Thử thay đổi List bằng add hoặc clear: List.copyOf khiến thao tác sửa cấu trúc ném UnsupportedOperationException.
4. Thử tạo một API trả ResultSet trong try-with-resources như phản ví dụ: giải thích tại sao return không giữ tài nguyên mở.
5. Giả lập entity có quan hệ LAZY, trả entity khi persistence context không còn hoạt động, rồi thiết kế lại API thành DTO chỉ chứa trường màn hình cần.
6. Với tập dữ liệu hàng triệu hàng, giải thích vì sao việc materialize đúng vòng đời vẫn cần giới hạn dung lượng hoặc phân trang.

## 10. Checklist cho một phương thức đọc dữ liệu

Trước khi công bố API đọc dữ liệu từ repository/service, tự xác nhận:

- **Hợp đồng kết quả:** DTO/value object chứa đủ trường cần thiết, không mang JDBC handle hoặc quan hệ lazy ngoài dự kiến.
- **Thời điểm materialize:** mọi giá trị được đọc khi ResultSet, persistence context hoặc stream cần thiết vẫn hợp lệ.
- **Sở hữu tài nguyên:** JdbcTemplate hoặc try-with-resources đóng Statement/ResultSet/Stream; không chuyển trách nhiệm đóng mơ hồ cho caller.
- **Transaction:** đặt ở service theo use case; proxy thực sự được áp dụng; readOnly không bị dùng như thay thế cho cách materialize.
- **Kích thước:** phân trang, batch hoặc streaming có kiểm soát khi danh sách lớn; không tạo bản sao sâu vô hạn chỉ để né lỗi lazy.
- **Độ ổn định:** copy những bộ sưu tập/mảng mutable khi hợp đồng yêu cầu; phân biệt dữ liệu đã materialize với dữ liệu luôn mới.
- **Kiểm chứng:** chạy một test đọc DTO **sau khi method transactional trả về**, tắt OSIV khi kiểm tra rủi ro lazy trong web app, và giám sát connection pool để phát hiện rò rỉ.

**Kết luận học tập:** một tầng dữ liệu có thiết kế tốt trả về **giá trị đủ dùng**, còn vòng đời Connection, ResultSet, Stream và EntityManager được xử lý bên trong ranh giới sở hữu rõ ràng. Spring giúp quản lý tài nguyên; lập trình viên vẫn phải xác định dữ liệu nào được materialize, khi nào cần transaction, và cái gì được phép đi qua ranh giới service.

### Tài liệu tham khảo

- Spring Framework — Data Access với JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — Working with SQL Databases: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Framework API — JdbcTemplate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
