# Vai trò của Spring, JDBC driver và hệ quản trị cơ sở dữ liệu trong giao dịch

Khi một phương thức trong ứng dụng Spring thực hiện nhiều câu lệnh SQL, câu hỏi quan trọng là: **ai quyết định phạm vi giao dịch, ai chuyển yêu cầu xuống cơ sở dữ liệu, và ai thật sự bảo đảm commit hoặc rollback?** Câu trả lời nằm ở ba tầng phối hợp với nhau: Spring quản lý **ranh giới và chính sách giao dịch**, JDBC driver cung cấp **kết nối và giao tiếp theo giao thức của hệ quản trị**, còn hệ quản trị cơ sở dữ liệu (DBMS) thực thi SQL và duy trì **trạng thái giao dịch thực tế**.

Bài này tập trung vào giao dịch với cơ sở dữ liệu quan hệ qua JDBC/JPA trong ứng dụng Spring theo mô hình blocking. Các mô hình phản ứng (R2DBC) và giao dịch phân tán được giới thiệu ở mức phân biệt trách nhiệm.

## 1. Một giao dịch nhìn từ yêu cầu nghiệp vụ

Giả sử chuyển 200 đơn vị từ ví A sang ví B:

1. Trừ 200 khỏi số dư A.
2. Cộng 200 vào số dư B.
3. Hoặc cả hai thay đổi được chấp nhận, hoặc cả hai bị hủy nếu một bước thất bại.

Nếu chỉ có câu lệnh thứ nhất được lưu vĩnh viễn, hệ thống bị sai lệch. Vì vậy hai thao tác cần nằm trong **cùng một giao dịch cơ sở dữ liệu**. Giao dịch tạo một ranh giới cho đơn vị công việc, nhưng để đạt tính đúng đắn còn cần kiểm tra nghiệp vụ, ràng buộc dữ liệu và chiến lược xử lý đồng thời phù hợp.

**Không nên đồng nhất** khái niệm giao dịch với annotation @Transactional: annotation là cách khai báo ý định của Spring; giao dịch thật liên quan đến tài nguyên và các thao tác commit/rollback ở hệ cơ sở dữ liệu.

## 2. Bản đồ trách nhiệm: mỗi tầng làm gì?

| Thành phần | Trách nhiệm chính | Không chịu trách nhiệm thay thành phần khác |
| --- | --- | --- |
| Service/nghiệp vụ | Chọn đơn vị công việc, thứ tự thao tác, điều kiện hợp lệ, cách xử lý lỗi | Không tự tạo bảo đảm ACID chỉ bằng mã Java |
| Spring Transaction Infrastructure | Xác định ranh giới transaction, propagation, isolation, timeout, rollback rule; lấy/gắn tài nguyên, yêu cầu commit/rollback | Không trực tiếp ghi WAL, giữ khóa hay thực thi engine SQL |
| DataSource và connection pool | Cung cấp, quản lý vòng đời và tái sử dụng JDBC Connection | Pool không phải transaction coordinator; một Connection không tự tạo giao dịch xuyên nhiều DB |
| JDBC API và JDBC driver | Ánh xạ lời gọi Java như prepare/execute/commit/rollback tới kết nối/giao thức DBMS và chuyển kết quả/lỗi về Java | Driver không quyết định quy tắc rollback của @Transactional hay bảo đảm ACID thay DBMS |
| DBMS và storage engine | Thực thi SQL, kiểm tra ràng buộc, quản lý khóa/MVCC, nhật ký, isolation, commit và rollback | DBMS không tự biết ranh giới nghiệp vụ ở lớp Spring hoặc hoàn tác email/HTTP đã gửi |
| JPA provider, nếu dùng | Quản lý EntityManager/persistence context, dirty checking và chuyển thay đổi đối tượng thành SQL | flush không đồng nghĩa commit; JPA vẫn dựa vào transaction và DBMS bên dưới |

Có thể hình dung:

~~~text
HTTP/CLI/scheduler
       |
       v
Service được Spring quản lý
       |
       v
Spring proxy / TransactionInterceptor
       |
       v
PlatformTransactionManager ---- DataSource / pool
                                   |
                                   v
                             JDBC Connection
                                   |
                              JDBC driver
                                   |
                                   v
                         DBMS: SQL, locks, log,
                         constraints, commit/rollback
~~~

**Phân biệt hai đường đi:** điều khiển transaction (begin/commit/rollback) được Spring điều phối qua transaction manager; các câu lệnh CRUD do JdbcTemplate, JDBC thuần hoặc JPA provider thực hiện trên tài nguyên được gắn vào transaction đó. Hai đường cần dùng đúng cùng tài nguyên để cùng tham gia một giao dịch.

## 3. Spring: quản lý ranh giới, không thay thế database

### 3.1. Abstraction và transaction manager

Spring cung cấp giao diện PlatformTransactionManager cho giao dịch imperative. Ba thao tác cốt lõi là:

~~~java
// Trích chữ ký API để minh họa; đây không phải chương trình độc lập.
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

TransactionDefinition mô tả chính sách (propagation, isolation, timeout, read-only); TransactionStatus phản ánh trạng thái giao dịch. Tùy môi trường, transaction manager sẽ sử dụng cơ chế thực tế khác nhau:

- **JdbcTransactionManager / DataSourceTransactionManager:** quản lý một DataSource JDBC và JDBC Connection, phù hợp với truy cập JDBC cục bộ. JdbcTransactionManager bổ sung dịch lỗi giao dịch thành hệ ngoại lệ truy cập dữ liệu của Spring.
- **JpaTransactionManager:** tích hợp giao dịch JPA thông qua EntityManager và JPA provider; với cấu hình phù hợp có thể phối hợp JDBC sử dụng cùng DataSource.
- **JtaTransactionManager:** phối hợp với hạ tầng JTA khi cần tài nguyên giao dịch có khả năng tham gia giao dịch toàn cục; không biến mọi driver/DB hoặc API bên ngoài thành tài nguyên XA.
- **ReactiveTransactionManager:** dùng cho mô hình reactive như R2DBC với cơ chế lan truyền context khác JDBC blocking.

Transaction manager phải phù hợp công nghệ truy cập dữ liệu và tài nguyên. Đặt @Transactional trên service nhưng cấu hình sai manager, dùng một DataSource khác, hoặc lấy một Connection nằm ngoài phạm vi quản lý đều có thể tạo ra các giao dịch khác với mong đợi.

### 3.2. @Transactional hoạt động qua lời gọi được Spring chặn

Ở chế độ proxy thông dụng, khi mã khác gọi phương thức của Spring bean **qua proxy**, TransactionInterceptor đọc metadata @Transactional, nhờ transaction manager tham gia hoặc mở giao dịch theo propagation, gọi phương thức nghiệp vụ, rồi quyết định commit/rollback khi phương thức kết thúc.

~~~java
// Mã minh họa trong một Spring application đã bật transaction management.
@Service
public class TransferService {
    private final WalletRepository repository;

    public TransferService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        repository.debit(from, amount);
        repository.credit(to, amount);
    }
}
~~~

Đoạn trên minh họa **ranh giới ở service**; chưa phải chương trình độc lập vì cần repository, DataSource, transaction manager và cấu hình Spring. Annotation chỉ là metadata: cần bean được Spring quản lý và cơ chế transaction được kích hoạt (ví dụ @EnableTransactionManagement hoặc tự cấu hình tương ứng trong Spring Boot).

Các mặc định phổ biến của Spring @Transactional là PROPAGATION_REQUIRED, ISOLATION_DEFAULT và readOnly=false. Theo mặc định, RuntimeException và Error làm Spring rollback, còn checked Exception không tự làm rollback trừ khi cấu hình rollbackFor hoặc chính sách mặc định khác. Quy tắc này quyết định **Spring yêu cầu rollback khi ngoại lệ lan ra**; nó không thay thế rollback của DBMS.

**Bẫy self-invocation:** từ một phương thức của cùng object gọi this.anotherTransactionalMethod() thường bỏ qua proxy, nên annotation trên phương thức được gọi không kích hoạt một ranh giới giao dịch mới trong proxy mode. Tách sang một Spring bean được gọi qua proxy hoặc thiết kế lại ranh giới transaction là cách giải quyết thông thường.

### 3.3. Tài nguyên được gắn với transaction như thế nào?

Với JDBC imperative, DataSourceTransactionManager/JdbcTransactionManager lấy JDBC Connection từ DataSource, cấu hình trạng thái cần thiết và gắn ConnectionHolder vào context giao dịch của luồng hiện tại. JdbcTemplate dùng DataSourceUtils để lấy đúng Connection đã gắn; vì vậy các câu lệnh trong cùng transaction có thể dùng chung connection.

Khi hoàn tất, Spring gọi commit/rollback, khôi phục trạng thái connection cần thiết, giải phóng ràng buộc với luồng, rồi trả connection về pool hoặc đóng nó theo DataSource. **Đóng logical connection của pool không đồng nghĩa đóng socket vật lý.** Driver và pool có thể làm thêm xử lý dọn dẹp tùy triển khai.

Không được tùy tiện tạo DriverManager.getConnection(...) bên trong một @Transactional rồi mong Connection mới tự tham gia transaction hiện tại. Việc gọi thẳng DataSource.getConnection() từ mã tự viết cũng có thể lấy connection riêng; khi cần JDBC thấp tầng tham gia transaction Spring, dùng DataSourceUtils hoặc API Spring đã tích hợp transaction.

## 4. JDBC driver: cầu nối giữa Java và DBMS

JDBC là hợp đồng API chuẩn của Java; driver là phần triển khai cụ thể cho PostgreSQL, MySQL, Oracle, H2, SQL Server... Driver thực hiện các công việc như:

1. Mở kết nối vật lý, xác thực và trao đổi với server qua giao thức tương ứng.
2. Truyền câu lệnh SQL và tham số PreparedStatement, nhận result set, update count hoặc lỗi.
3. Ánh xạ kiểu dữ liệu Java/JDBC với kiểu DB và chuyển lỗi máy chủ thành SQLException cùng các mã/SQLState hữu ích.
4. Chuyển các lời gọi Connection.setAutoCommit(false), commit(), rollback(), setTransactionIsolation(...) thành thao tác theo khả năng DBMS/driver.

Driver có thể thực hiện đệm, batching, lựa chọn giao thức và tối ưu khác, nhưng **không phải là bộ máy lưu trữ dữ liệu**. Driver báo thao tác commit thành công theo phản hồi đã nhận; tính bền vững, khóa và rollback thực tế do DBMS và cấu hình của nó quyết định.

**DataSource không đồng nghĩa driver:** DataSource là abstraction cung cấp JDBC Connection; trong thực tế thường kết nối tới connection pool như HikariCP, còn pool sử dụng driver. DriverManagerDataSource của Spring thích hợp demo/test vì mỗi lần yêu cầu có thể tạo kết nối vật lý mới; nó không phải connection pool sản xuất.

**Autocommit:** một JDBC Connection mới thường hoạt động với autoCommit=true theo mặc định JDBC, khi đó mỗi câu lệnh SQL riêng được commit theo quy tắc của DB. Để nhóm nhiều lệnh trong một transaction JDBC thông thường, cần điều khiển autoCommit=false hoặc để transaction manager làm việc đó. Một số DB có ngữ nghĩa transaction/DDL và hành vi autocommit đặc thù; không suy luận rằng mọi SQL đều rollback được trên mọi engine.

## 5. DBMS: nơi giao dịch thật sự được thực thi

Khi nhận SQL, DBMS xác thực cú pháp/quyền, lập kế hoạch, đọc/ghi dữ liệu và áp dụng ràng buộc. Trong transaction, engine dùng cơ chế như khóa, MVCC, undo/redo hoặc write-ahead log tùy sản phẩm để hỗ trợ:

- **Atomicity:** các thay đổi trong một transaction thành công cùng nhau hoặc được rollback theo khả năng engine.
- **Consistency:** trạng thái chuyển từ hợp lệ sang hợp lệ khi có ràng buộc và logic nghiệp vụ đúng. DBMS enforce PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK..., nhưng không biết hết mọi bất biến nghiệp vụ.
- **Isolation:** quy định mức độ các transaction đồng thời nhìn thấy hoặc tác động lẫn nhau; mức isolation và các hiện tượng bị ngăn chặn khác nhau theo DBMS.
- **Durability:** dữ liệu đã được xác nhận commit được giữ theo bảo đảm và cấu hình lưu trữ của DBMS.

Commit là điểm yêu cầu DBMS hoàn tất giao dịch. Rollback yêu cầu DBMS hủy các thay đổi chưa commit thuộc transaction đó. Spring điều phối **khi nào gọi**; DBMS quyết định **cách thực hiện**. Không nên nói rằng Spring tự khóa bảng, viết WAL, hay tự bảo đảm ACID.

Một transaction có thể phát sinh lỗi dù Java không ném lỗi nghiệp vụ: vi phạm UNIQUE/CHECK, deadlock, serialization failure, mất kết nối, timeout, thiếu tài nguyên... DBMS phát hiện và trả lỗi qua driver; Spring JDBC có thể dịch SQLException sang DataAccessException. Với lỗi xảy ra tại commit, kết quả đôi khi cần xác minh trước khi retry, nhất là khi kết nối bị mất trong lúc xác nhận.

## 6. Dòng thời gian: một request chuyển tiền

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring TX proxy
    participant TM as TransactionManager
    participant JDBC as JDBC driver/Connection
    participant DB as DBMS
    Caller->>Proxy: transfer(A, B, 200)
    Proxy->>TM: getTransaction(REQUIRED)
    TM->>JDBC: lấy Connection, cấu hình transaction
    JDBC->>DB: bắt đầu làm việc trong transaction
    Proxy->>JDBC: UPDATE ví A (qua JDBC/JPA)
    JDBC->>DB: SQL trừ tiền
    DB-->>JDBC: kết quả
    Proxy->>JDBC: UPDATE ví B (qua JDBC/JPA)
    JDBC->>DB: SQL cộng tiền
    DB-->>JDBC: kết quả
    alt Không có lỗi cần rollback
        Proxy->>TM: commit
        TM->>JDBC: Connection.commit()
        JDBC->>DB: yêu cầu COMMIT
    else Lỗi cần rollback
        Proxy->>TM: rollback
        TM->>JDBC: Connection.rollback()
        JDBC->>DB: yêu cầu ROLLBACK
    end
    TM-->>Proxy: giải phóng tài nguyên
    Proxy-->>Caller: kết quả hoặc ngoại lệ
~~~

Sơ đồ mô tả **ý nghĩa logic**, không khẳng định mọi driver đều gửi một lệnh BEGIN tường minh tại cùng thời điểm: một số DB bắt đầu transaction khi thực hiện câu SQL đầu tiên sau khi tắt autocommit. Nếu PROPAGATION_REQUIRED tham gia transaction đã tồn tại, điểm commit cuối cùng thuộc về ranh giới transaction bên ngoài, không nhất thiết là phương thức được gọi bên trong.

Ví dụ lỗi có thể xuất hiện ở lệnh UPDATE thứ hai. Nếu cả hai lệnh đi qua đúng cùng transaction và DBMS hỗ trợ rollback cho thao tác đó, việc rollback trả số dư về trạng thái ban đầu. Nếu UPDATE thứ nhất chạy qua connection autocommit độc lập, Spring không thể hủy thay đổi đã commit đó.

## 7. Thực hành chạy được: quan sát rollback và commit

Ví dụ này dùng **Java 17+, Maven, Spring JDBC 6.2.12 và H2 2.3.232** để minh họa ba tầng trên. H2 chạy trong bộ nhớ, không cần server ngoài. DriverManagerDataSource chỉ dùng để học; hệ sản xuất nên cấu hình pool DataSource phù hợp.

Cấu trúc thư mục:

~~~text
transaction-roles-demo/
├── pom.xml
└── src/main/java/demo/TransactionRolesDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-roles-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.TransactionRolesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TransactionRolesDemo.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionRolesDemo {
    private TransactionRolesDemo() {}

    private static int balance(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?",
                Integer.class, id);
        if (value == null) {
            throw new IllegalStateException("Wallet not found: " + id);
        }
        return value;
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:role_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE wallet (" +
                "id INT PRIMARY KEY, " +
                "balance INT NOT NULL CHECK (balance >= 0))");
        jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 1, 1000);
        jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 2, 500);

        TransactionTemplate tx = new TransactionTemplate(
                new JdbcTransactionManager(dataSource));

        try {
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE wallet SET balance = balance - 200 WHERE id = ?", 1);
                jdbc.update("UPDATE wallet SET balance = balance + 200 WHERE id = ?", 2);
                throw new IllegalStateException("demo rollback");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback: " + expected.getMessage());
        }

        System.out.printf("After rollback: A=%d, B=%d%n",
                balance(jdbc, 1), balance(jdbc, 2));

        tx.executeWithoutResult(status -> {
            jdbc.update("UPDATE wallet SET balance = balance - 200 WHERE id = ?", 1);
            jdbc.update("UPDATE wallet SET balance = balance + 200 WHERE id = ?", 2);
        });

        System.out.printf("After commit: A=%d, B=%d%n",
                balance(jdbc, 1), balance(jdbc, 2));
    }
}
~~~

Từ thư mục transaction-roles-demo, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout của chương trình Java** (không tính log riêng của Maven hoặc môi trường):

~~~text
Rollback: demo rollback
After rollback: A=1000, B=500
After commit: A=800, B=700
~~~

**Giải thích chính xác những gì diễn ra:**

1. JdbcTemplate tạo bảng và hai dòng dữ liệu trước khi mở transaction demo; các lệnh khởi tạo độc lập với hai transaction bên dưới.
2. TransactionTemplate nhờ JdbcTransactionManager mở transaction trên DataSource. Spring giữ connection phù hợp trong transaction context.
3. JdbcTemplate tìm lại connection đó qua cơ chế tích hợp Spring; driver H2 gửi hai UPDATE tới H2 DBMS.
4. RuntimeException trong lambda đầu làm transaction manager rollback. H2 hủy hai thay đổi chưa commit, vì vậy số dư vẫn 1000 và 500.
5. Lambda thứ hai kết thúc bình thường; transaction manager commit, H2 lưu hai thay đổi và số dư thành 800 và 700.

Nếu thay lời gọi JdbcTemplate trong lambda bằng một kết nối JDBC tự mở ngoài transaction Spring với autocommit=true, kết quả có thể khác. Thử thay đổi này chỉ trong môi trường demo để quan sát lỗi thiết kế, không áp dụng vào hệ thống thật.

Trong ứng dụng sử dụng @Transactional, interceptor thực hiện việc điều phối trước/sau phương thức thay cho TransactionTemplate; vai trò driver và DBMS vẫn cùng bản chất.

## 8. Các thuộc tính giao dịch: ai quyết định, ai thực thi?

| Thuộc tính | Spring quyết định | DBMS/driver thực hiện hoặc giới hạn |
| --- | --- | --- |
| Ranh giới transaction | Mở/tham gia/kết thúc theo propagation và lời gọi qua proxy hoặc template | Connection và DBMS thực thi transaction vật lý |
| Rollback rules | Ngoại lệ nào làm đánh dấu rollback; có thể gọi setRollbackOnly() | DBMS hủy thay đổi thuộc transaction chưa commit |
| Propagation | REQUIRED, REQUIRES_NEW, SUPPORTS, NESTED... xác định quan hệ giữa lời gọi | REQUIRES_NEW thường cần transaction/connection độc lập; NESTED phụ thuộc savepoint và manager |
| Isolation | Gửi yêu cầu mức isolation qua transaction definition | Khả năng và cách hiểu READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE... tùy DBMS |
| Timeout | Đặt timeout/chuyển vào truy vấn nếu API hỗ trợ | Driver, statement, DBMS quyết định cách cắt hoặc hủy công việc thực tế |
| readOnly | Biểu thị ý định đọc, cho phép tối ưu và có thể chuyển hint xuống JDBC | Không được xem như hàng rào bảo mật/cấm ghi chắc chắn trên mọi DBMS |
| Commit/rollback | Yêu cầu cuối cùng theo transaction status và chính sách | DBMS thực hiện, ghi log, giữ nhả khóa và xác nhận kết quả |

**Propagation không phải isolation.** Propagation trả lời "transaction của lời gọi này liên hệ thế nào với transaction đang có?"; isolation trả lời "các transaction đồng thời có thể quan sát nhau đến mức nào?". Một phương thức @Transactional không mặc nhiên loại bỏ lost update, write skew hay mọi race condition; cần thiết kế câu SQL, khóa, phiên bản optimistic locking, isolation và retry phù hợp.

**Độ hạt connection:** một local JDBC transaction gắn với connection cụ thể. Hai DataSource dùng hai DB khác nhau không trở thành một transaction nguyên tử chỉ vì đặt cùng một annotation. Muốn phối hợp nhiều tài nguyên cần cơ chế tương ứng (ví dụ JTA/XA khi hỗ trợ) hoặc thiết kế nhất quán cuối cùng như outbox/saga theo yêu cầu nghiệp vụ.

## 9. Các nhầm lẫn thường gặp và cách kiểm chứng

### Nhầm 1: "Có @Transactional là database tự rollback mọi thứ"

Không đúng. Spring phải thật sự chặn lời gọi, có transaction manager, và các thao tác phải tham gia đúng tài nguyên. Bắt rồi nuốt ngoại lệ trong service mà không đánh dấu rollback-only có thể khiến Spring commit. Mặc định checked Exception cũng có thể không kích hoạt rollback tự động; hãy kiểm tra rollbackFor và chính sách đang cấu hình.

### Nhầm 2: "Driver tạo ra ACID"

Driver là cầu nối giao tiếp; giao dịch và ràng buộc thực tế nằm ở DBMS/storage engine. Hành vi isolation, khóa, DDL và durability khác nhau giữa các hệ quản trị và cấu hình.

### Nhầm 3: "Hai repository được gọi trong một phương thức sẽ cùng transaction"

Chỉ đúng khi repository dùng tài nguyên được manager hiện tại phối hợp. Nếu một repository dùng DataSource khác hoặc tự mở connection autocommit, các thay đổi có thể không cùng giao dịch. Với JPA, phải kiểm tra EntityManager/transaction manager và DataSource tương ứng.

### Nhầm 4: "JPA flush() giống commit()"

Flush đẩy các thay đổi đang chờ thành SQL để DBMS xử lý trong transaction; transaction vẫn có thể rollback. Commit mới kết thúc transaction thành công. Ngược lại, lỗi ràng buộc có thể xuất hiện lúc flush hoặc commit tùy provider và cách thực thi.

### Nhầm 5: "Rollback database sẽ hủy cả email, HTTP call, message"

Một lệnh gọi dịch vụ ngoài, gửi email hoặc publish message thông thường không tự tham gia local JDBC transaction. Nếu cần nhất quán giữa database và phát sự kiện, cân nhắc transactional outbox, consumer idempotent hoặc kiến trúc phân tán được thiết kế rõ ràng.

### Nhầm 6: "REQUIRES_NEW miễn phí, readOnly chắc chắn cấm ghi"

REQUIRES_NEW có thể cần thêm connection khi transaction ngoài vẫn đang giữ tài nguyên, ảnh hưởng pool và rủi ro chờ connection. readOnly chủ yếu là hint/optimization trừ khi stack/DBMS có cơ chế enforce riêng.

### Nhầm 7: "Nếu commit báo lỗi, chắc chắn chưa có bản ghi"

Mất mạng đúng thời điểm commit có thể làm client không biết DBMS đã commit hay chưa. Cần truy vấn trạng thái, dùng khóa nghiệp vụ/idempotency key và thiết kế retry phù hợp thay vì gửi lại thao tác không kiểm soát.

## 10. Checklist chẩn đoán theo đúng tầng

Khi báo "transaction không rollback", đặt câu hỏi theo trình tự:

1. **Spring boundary:** phương thức có được gọi qua proxy/TransactionTemplate không? Transaction management đã bật chưa? Loại ngoại lệ có khớp rollback rule không? Có đoạn mã catch rồi trả về bình thường không?
2. **Transaction manager và tài nguyên:** có đúng manager và DataSource không? JdbcTemplate/JPA provider có lấy tài nguyên tham gia transaction không? Có connection tự mở hoặc @Async/luồng mới làm mất context không?
3. **JDBC/driver:** connection có autocommit gì? SQL đã gửi chưa? Có lỗi SQLState, timeout, socket hay vấn đề pool không? Driver có hỗ trợ đặc tính isolation/savepoint được yêu cầu không?
4. **DBMS:** câu lệnh có thuộc bảng/engine transactional không? Có DDL implicit commit, trigger, constraint, deadlock hoặc cấu hình isolation đặc thù không? DB đã thực sự commit hay rollback?
5. **Phạm vi hệ thống:** ngoài DB còn gọi message broker, HTTP, file hoặc nhiều DB không? Nếu có, xác định rõ cơ chế phối hợp hoặc bù trừ.

Để xác minh trong test integration, hãy tạo dữ liệu ban đầu, thực hiện hai thao tác trong một transaction, cố ý gây lỗi ở thao tác sau, rồi **đọc lại từ connection/transaction độc lập sau khi phương thức kết thúc** để kiểm tra cả hai thay đổi được rollback. Sau đó chạy trường hợp thành công và kiểm tra kết quả commit. Cách này chứng minh hành vi ở DBMS tốt hơn việc chỉ kiểm tra rằng một ngoại lệ đã được ném.

## 11. Tự kiểm tra kiến thức

**Tình huống A.** Một service @Transactional gọi repository A dùng JdbcTemplate và repository B tự gọi DriverManager.getConnection(...) để UPDATE cùng database. Repository B sẽ chắc chắn rollback cùng A chứ?  
**Đáp án:** Không. Connection tự tạo của B có thể nằm ngoài transaction do Spring quản lý, dù trỏ tới cùng DB và dùng cùng driver.

**Tình huống B.** UPDATE thứ hai vi phạm CHECK và driver báo SQLException. Ai phát hiện lỗi, ai quyết định rollback, ai hủy dữ liệu?  
**Đáp án:** DBMS phát hiện vi phạm; driver chuyển lỗi về Java; Spring (tùy transaction manager và rollback rule) yêu cầu rollback; DBMS thực thi rollback của transaction.

**Tình huống C.** Trong transaction JPA, gọi flush() thành công rồi service ném RuntimeException. Có chắc dữ liệu đã được commit không?  
**Đáp án:** Không. flush có thể đã gửi SQL, nhưng transaction vẫn có thể bị rollback khi ngoại lệ thoát ra theo chính sách mặc định.

**Tình huống D.** Có hai DB độc lập và một @Transactional trên service. Spring có mặc nhiên bảo đảm commit nguyên tử ở cả hai?  
**Đáp án:** Không. Local transaction manager không tự phối hợp hai tài nguyên. Cần kiến trúc/transaction coordinator phù hợp.

## 12. Ghi nhớ bản chất

- **Spring = người điều phối:** xác định transaction boundary, chính sách, gắn tài nguyên và yêu cầu commit/rollback.
- **JDBC driver = cầu nối kỹ thuật:** thực thi hợp đồng JDBC qua giao thức DBMS, gửi SQL và thao tác trên Connection, trả kết quả/lỗi.
- **DBMS = nơi thi hành giao dịch:** lưu/đọc dữ liệu, áp dụng ràng buộc và isolation, thực hiện commit/rollback.
- **Đúng một ranh giới nghiệp vụ chưa đủ:** mọi SQL cần tham gia tài nguyên phù hợp; concurrency, dữ liệu ngoài DB và xử lý lỗi vẫn phải được thiết kế.

## Tài liệu tham khảo

- [Spring Framework: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring: Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Java SE 17: java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
