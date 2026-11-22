# Phân biệt Spring Data Relational, Spring Data R2DBC và Spring R2DBC

Ba tên này có liên quan chặt chẽ nhưng nằm ở những tầng khác nhau của hệ sinh thái Spring. Điểm dễ nhầm nhất là **Spring Data R2DBC** và **Spring R2DBC** đều làm việc với R2DBC, trong khi **Spring Data Relational** cung cấp mô hình và hạ tầng ánh xạ dữ liệu quan hệ được các module Spring Data JDBC và Spring Data R2DBC dùng chung.

Có thể nhớ nhanh:

- **Spring Data Relational**: mô hình dữ liệu quan hệ và hạ tầng mapping dùng chung.
- **Spring Data R2DBC**: lớp Spring Data cung cấp repository, mapping entity và thao tác dữ liệu quan hệ theo kiểu reactive trên R2DBC.
- **Spring R2DBC**: lớp của Spring Framework tích hợp R2DBC SPI, cung cấp API truy cập SQL và quản lý kết nối/giao dịch ở mức thấp hơn.

## 1. Đặt ba thành phần vào đúng tầng

Một ứng dụng có thể truy cập cơ sở dữ liệu quan hệ qua JDBC hoặc R2DBC. Spring chia trách nhiệm thành nhiều lớp để phần mô hình dữ liệu và phần kết nối cơ sở dữ liệu không phải gắn chặt với nhau.

### Spring Data Relational

Spring Data Relational là tên được dùng ở hai phạm vi có liên quan:

1. **Dự án/nhóm giải pháp Spring Data Relational**: bao gồm các hướng truy cập dữ liệu quan hệ như Spring Data JDBC và Spring Data R2DBC.
2. **Module spring-data-relational**: phần hạ tầng dùng chung bên dưới các module đó.

Khi so sánh ba tên trong bài này, trọng tâm là module nền tảng dùng chung. Module này cung cấp mô hình metadata cho bảng và cột, quy tắc ánh xạ đối tượng sang dữ liệu quan hệ, chuyển đổi kiểu dữ liệu, naming strategy, các khái niệm truy vấn quan hệ và những cơ chế nền tảng liên quan.

Ví dụ, các annotation như **@Table**, **@Column**, **@Id** mô tả cách một lớp Java tương ứng với bảng, cột và khóa định danh. Những khái niệm mapping này có thể được sử dụng trong cả Spring Data JDBC và Spring Data R2DBC.

Spring Data Relational không phải là một giao thức kết nối cơ sở dữ liệu, không phải JDBC driver và cũng không phải R2DBC driver. Nó không tự quyết định ứng dụng sẽ dùng kết nối đồng bộ hay reactive. Việc đó thuộc về module truy cập dữ liệu cụ thể.

### Spring Data R2DBC

Spring Data R2DBC là module thuộc Spring Data, cung cấp cách làm việc với cơ sở dữ liệu quan hệ qua R2DBC theo mô hình Spring Data.

Nó bổ sung những tiện ích ở tầng dữ liệu mà ứng dụng thường cần:

- Repository abstraction, ví dụ **ReactiveCrudRepository**.
- Ánh xạ entity với bảng và cột dựa trên hạ tầng Spring Data Relational.
- Sinh truy vấn từ tên phương thức repository trong các trường hợp được hỗ trợ.
- Hỗ trợ truy vấn khai báo và truy vấn tùy chỉnh.
- **R2dbcEntityTemplate** cho thao tác entity mà không nhất thiết phải tạo repository.
- Các cơ chế callback, conversion và tích hợp transaction phù hợp với luồng reactive.

Spring Data R2DBC giúp ứng dụng làm việc với entity và repository thay vì phải tự quản lý từng chi tiết của câu SQL, **Row** và **Connection**.

Tên gọi có chữ R2DBC vì module này dùng R2DBC làm nền tảng kết nối. Nó không phải là chính R2DBC SPI và cũng không phải module **spring-r2dbc** của Spring Framework.

### Spring R2DBC

Spring R2DBC là module của **Spring Framework**. Nó tích hợp chuẩn R2DBC SPI vào hệ sinh thái Spring và cung cấp các API hạ tầng để thực thi SQL, quản lý kết nối, dịch lỗi và điều phối transaction.

Một API tiêu biểu là **DatabaseClient**. Ứng dụng có thể dùng API này để gửi SQL và đọc kết quả mà không cần tự viết toàn bộ quy trình lấy kết nối, thực thi statement và giải phóng tài nguyên.

Các thành phần thường gặp gồm:

- **ConnectionFactory**: điểm tạo kết nối theo R2DBC SPI.
- **DatabaseClient**: API thực thi SQL và xử lý kết quả.
- **R2dbcTransactionManager**: transaction manager cho một **ConnectionFactory**.
- **ConnectionFactoryUtils**: tiện ích lấy và quản lý kết nối gắn với ngữ cảnh Spring.
- **TransactionalOperator**: cách điều phối transaction trong luồng reactive bằng chương trình.

Spring R2DBC cung cấp hạ tầng truy cập dữ liệu ở mức thấp hơn Spring Data R2DBC. Nếu ứng dụng chỉ cần chạy SQL tùy chỉnh và tự ánh xạ kết quả, có thể dùng **DatabaseClient** trực tiếp mà không cần tạo repository Spring Data.

## 2. Quan hệ giữa các thành phần

Sơ đồ dưới đây thể hiện cách các lớp thường kết hợp khi ứng dụng sử dụng repository reactive:

~~~mermaid
flowchart TB
    A["Ứng dụng"]
    B["Spring Data R2DBC<br/>Repository, entity mapping,<br/>R2dbcEntityTemplate"]
    C["Spring Data Relational<br/>Metadata và mapping quan hệ dùng chung"]
    D["Spring R2DBC<br/>DatabaseClient, transaction,<br/>kết nối"]
    E["R2DBC SPI"]
    F["R2DBC Driver"]
    G[("Cơ sở dữ liệu quan hệ")]

    A --> B
    B --> C
    B --> D
    D --> E
    E --> F
    F --> G
~~~

Trong sơ đồ, Spring Data R2DBC dùng các khái niệm mapping quan hệ chung và dựa vào hạ tầng Spring R2DBC để giao tiếp qua R2DBC SPI. Driver cụ thể triển khai SPI để kết nối tới hệ quản trị cơ sở dữ liệu.

Spring Data Relational và Spring R2DBC không thay thế nhau: một bên tập trung vào mô hình dữ liệu quan hệ, bên còn lại tập trung vào kết nối và thực thi SQL theo R2DBC.

Có thể đặt Spring Data JDBC cạnh kiến trúc này để thấy vai trò của phần dùng chung:

~~~mermaid
flowchart TB
    A["Ứng dụng dùng Spring Data JDBC"]
    B["Spring Data JDBC<br/>Repository và JdbcAggregateTemplate"]
    C["Spring Data Relational<br/>Mapping quan hệ dùng chung"]
    D["Spring JDBC<br/>JdbcTemplate và transaction JDBC"]
    E["JDBC API"]
    F["JDBC Driver"]
    G[("Cơ sở dữ liệu quan hệ")]

    A --> B
    B --> C
    B --> D
    D --> E
    E --> F
    F --> G
~~~

Spring Data JDBC và Spring Data R2DBC có thể dùng chung nhiều khái niệm mapping quan hệ, nhưng đường kết nối và mô hình thực thi của chúng khác nhau:

- Spring Data JDBC đi qua Spring JDBC và JDBC API; thao tác thường mang tính đồng bộ, chặn luồng gọi trong lúc chờ I/O.
- Spring Data R2DBC đi qua Spring R2DBC và R2DBC SPI; API được thiết kế cho xử lý reactive, không chặn luồng trong quá trình I/O khi driver triển khai đúng mô hình này.

## 3. So sánh trực tiếp

| Tiêu chí | Spring Data Relational | Spring Data R2DBC | Spring R2DBC |
|---|---|---|---|
| Vị trí | Hạ tầng/mô hình chung của Spring Data cho dữ liệu quan hệ | Module thuộc Spring Data | Module thuộc Spring Framework |
| Trách nhiệm chính | Metadata, mapping, conversion và khái niệm quan hệ dùng chung | Repository và thao tác entity theo kiểu reactive | Kết nối, thực thi SQL và transaction qua R2DBC |
| API/khái niệm tiêu biểu | **@Table**, **@Column**, **@Id**, relational mapping metadata | **ReactiveCrudRepository**, **R2dbcEntityTemplate** | **DatabaseClient**, **ConnectionFactory**, **R2dbcTransactionManager** |
| Có repository abstraction? | Không phải vai trò riêng của lớp nền tảng dùng chung | Có | Không cung cấp repository Spring Data |
| Có entity mapping? | Cung cấp nền tảng mapping quan hệ dùng chung | Dùng nền tảng đó để ánh xạ entity khi truy cập bằng R2DBC | Không phải lớp mapping entity của Spring Data |
| Cách thực thi | Không tự xác định kiểu kết nối | Reactive | Reactive |
| Driver | Không cung cấp driver | Cần R2DBC driver tương ứng | Làm việc với driver qua R2DBC SPI |

Điểm cần phân biệt là chữ “reactive” không áp dụng cho mọi thứ mang tên Spring Data Relational. Đây là nền tảng mapping quan hệ dùng chung; Spring Data JDBC vẫn là hướng imperative, còn Spring Data R2DBC là hướng reactive.

## 4. Ví dụ để nhận ra ranh giới API

Giả sử ứng dụng có bảng **customer** với hai cột **id** và **full_name**.

### 4.1. Mô tả mapping quan hệ

Một entity có thể khai báo metadata như sau:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

**@Table**, **@Column** và **@Id** mô tả quan hệ giữa kiểu Java và cấu trúc bảng. Đây là phần thuộc mô hình mapping quan hệ mà Spring Data Relational cung cấp. Các module Spring Data JDBC và Spring Data R2DBC có thể sử dụng những metadata này trong quá trình đọc/ghi dữ liệu.

Các annotation này tự chúng không mở kết nối và không gửi SQL. Muốn thực hiện thao tác, ứng dụng cần một module truy cập dữ liệu như Spring Data JDBC hoặc Spring Data R2DBC.

### 4.2. Dùng Spring Data R2DBC với repository

Repository reactive có thể khai báo như sau:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByFullName(String fullName);
}
~~~

**ReactiveCrudRepository** thuộc Spring Data R2DBC. Spring Data cung cấp cách triển khai các thao tác CRUD và xử lý phương thức truy vấn theo quy ước. Kết quả được biểu diễn bằng kiểu reactive như **Mono** hoặc **Flux**.

Ví dụ:

~~~java
customerRepository.findByFullName("An")
    .subscribe(customer -> System.out.println(customer.fullName()));
~~~

Trong ứng dụng thực tế, controller hoặc service thường trả về và kết hợp các publisher thay vì gọi **subscribe()** tùy tiện ở mọi tầng. Cách đó giúp framework điều phối luồng xử lý và xử lý lỗi nhất quán.

### 4.3. Dùng Spring R2DBC trực tiếp với DatabaseClient

Nếu cần SQL tùy chỉnh và không cần repository, có thể sử dụng **DatabaseClient**:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

DatabaseClient databaseClient =
    DatabaseClient.create(connectionFactory);

Flux<Customer> customers =
    databaseClient.sql("""
            SELECT id, full_name
            FROM customer
            WHERE full_name = :name
            """)
        .bind("name", "An")
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class)
        ))
        .all();
~~~

Ở ví dụ này, **DatabaseClient** thuộc Spring R2DBC. Ứng dụng viết SQL, bind tham số và tự chỉ định cách chuyển mỗi dòng kết quả thành **Customer**. Spring Data repository không tham gia vào thao tác này.

Nếu cần các thao tác entity có mapping của Spring Data nhưng không muốn tạo repository, có thể cân nhắc **R2dbcEntityTemplate**, thuộc Spring Data R2DBC.

### 4.4. Đặt cạnh Spring Data JDBC

Với cùng mô hình dữ liệu, repository imperative của Spring Data JDBC thường có dạng:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Repository này dùng **CrudRepository** và trả kết quả theo kiểu imperative, chẳng hạn một entity, **Iterable** hoặc **Optional** tùy phương thức. Nó đi theo đường JDBC, không phải R2DBC.

Hai repository có thể trông gần giống nhau ở mức khai báo, nhưng kiểu trả về, driver, transaction manager và cách I/O diễn ra khác nhau. Không thể biến JDBC thành non-blocking chỉ bằng cách bọc lời gọi JDBC trong **Mono** hoặc **Flux**.

## 5. Chọn thành phần nào cho ứng dụng?

Hãy bắt đầu từ cách ứng dụng cần thực hiện I/O với cơ sở dữ liệu:

| Nhu cầu | Hướng phù hợp | Lý do |
|---|---|---|
| Muốn repository CRUD và truy vấn theo phương thức, theo kiểu imperative | Spring Data JDBC | Có repository và mapping quan hệ, sử dụng JDBC |
| Muốn repository CRUD và truy vấn theo phương thức trong luồng reactive | Spring Data R2DBC | Có repository reactive và sử dụng R2DBC |
| Muốn viết SQL reactive trực tiếp, tự kiểm soát việc ánh xạ kết quả | Spring R2DBC (**DatabaseClient**) | Cung cấp API SQL ở tầng Spring Framework |
| Muốn hiểu annotation, metadata và mapping chung giữa các hướng JDBC/R2DBC | Spring Data Relational | Đây là lớp mô hình và hạ tầng quan hệ dùng chung |

Một số nguyên tắc thực tế:

1. **Chọn theo driver và mô hình I/O.** Nếu ứng dụng dùng JDBC driver thì chọn hướng JDBC. Nếu cần I/O reactive và cơ sở dữ liệu có R2DBC driver phù hợp thì chọn R2DBC.
2. **Chọn mức trừu tượng theo nhu cầu.** Dùng Spring Data R2DBC khi repository và entity mapping giúp mã ứng dụng gọn hơn. Dùng **DatabaseClient** khi cần kiểm soát SQL trực tiếp hoặc không cần repository.
3. **Không cài đặt Spring Data Relational như thể đó là driver.** Trong ứng dụng, module này thường được đưa vào gián tiếp qua Spring Data JDBC hoặc Spring Data R2DBC. Dependency cụ thể nên được quản lý theo phiên bản Spring Data/Spring Boot mà dự án đang sử dụng.
4. **Kiểm tra khả năng của R2DBC driver.** Mức hỗ trợ kiểu dữ liệu, tính năng SQL và hành vi transaction phụ thuộc driver và hệ quản trị cơ sở dữ liệu.
5. **Giữ luồng reactive không bị chặn.** Nếu đã chọn R2DBC, tránh gọi thao tác blocking như JDBC hoặc I/O blocking khác trên các luồng xử lý reactive. Bọc một lời gọi blocking trong **Mono** không làm cho chính lời gọi đó trở thành non-blocking.

## 6. Transaction và tính reactive

Spring R2DBC cung cấp **R2dbcTransactionManager** để quản lý transaction cho một **ConnectionFactory**. Spring Data R2DBC có thể phối hợp với transaction manager này để repository và các thao tác entity tham gia transaction.

Trong ứng dụng reactive, có thể dùng **@Transactional** trên phương thức trả về publisher hoặc dùng **TransactionalOperator** để điều phối transaction bằng chương trình. Transaction reactive được gắn với ngữ cảnh reactive; vì vậy cần duy trì chuỗi publisher và cấu hình đúng transaction manager.

JDBC có mô hình transaction riêng, thường dùng **DataSourceTransactionManager** hoặc cơ chế transaction JDBC tương ứng. Transaction JDBC và R2DBC sử dụng các loại kết nối khác nhau. Không nên giả định một transaction JDBC sẽ tự bao trùm các thao tác R2DBC, hoặc ngược lại.

## 7. Những nhầm lẫn thường gặp

**“Spring Data R2DBC và Spring R2DBC là một.”**  
Không phải. Spring Data R2DBC cung cấp repository và entity-oriented data access. Spring R2DBC cung cấp hạ tầng kết nối và thực thi SQL dựa trên R2DBC SPI. Spring Data R2DBC sử dụng hạ tầng Spring R2DBC.

**“Spring Data Relational là một cách kết nối cơ sở dữ liệu khác.”**  
Không phải. Module **spring-data-relational** cung cấp các khái niệm và hạ tầng mapping quan hệ dùng chung. Đường kết nối cụ thể do Spring Data JDBC hoặc Spring Data R2DBC đảm nhiệm.

**“Dùng Spring Data Relational thì ứng dụng tự động reactive.”**  
Không phải. Mapping quan hệ dùng chung không quyết định I/O là blocking hay non-blocking. Spring Data JDBC dùng JDBC theo kiểu imperative; Spring Data R2DBC dùng R2DBC theo kiểu reactive.

**“Có Spring R2DBC là đã có repository.”**  
Không phải. Có thể dùng **DatabaseClient** để thực thi SQL trực tiếp. Muốn dùng repository abstraction thì cần Spring Data R2DBC.

**“R2DBC chỉ là JDBC với kiểu trả về Mono/Flux.”**  
Không phải. R2DBC là một SPI riêng được thiết kế cho truy cập cơ sở dữ liệu reactive. Nó cần driver triển khai R2DBC SPI. JDBC driver không trở thành R2DBC driver khi được gọi từ mã reactive.

**“Reactive luôn nhanh hơn JDBC.”**  
Không thể kết luận như vậy cho mọi ứng dụng. Reactive có thể giúp phục vụ nhiều tác vụ I/O đồng thời với số lượng luồng hạn chế, nhưng hiệu quả thực tế phụ thuộc workload, driver, connection pool, thiết kế ứng dụng và năng lực cơ sở dữ liệu. Nếu ứng dụng chủ yếu là imperative hoặc tải không đòi hỏi mô hình reactive, JDBC có thể đơn giản và phù hợp hơn.

## 8. Ghi nhớ bằng một câu cho mỗi tên

- **Spring Data Relational** trả lời: dữ liệu quan hệ được mô tả và ánh xạ vào mô hình đối tượng Spring Data như thế nào?
- **Spring Data R2DBC** trả lời: làm thế nào để dùng repository và entity mapping của Spring Data với cơ sở dữ liệu quan hệ qua R2DBC?
- **Spring R2DBC** trả lời: làm thế nào để Spring thực thi SQL, quản lý kết nối và transaction qua R2DBC SPI?

Khi đọc dependency, package hoặc code của một dự án, hãy nhìn vào API đang được sử dụng: **@Table** và **@Column** cho thấy phần mapping quan hệ; **ReactiveCrudRepository** hoặc **R2dbcEntityTemplate** cho thấy tầng Spring Data R2DBC; **DatabaseClient** hoặc **R2dbcTransactionManager** cho thấy hạ tầng Spring R2DBC. Nhìn đúng API sẽ giúp xác định mỗi thành phần đang chịu trách nhiệm ở tầng nào.

