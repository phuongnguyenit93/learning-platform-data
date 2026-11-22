# Ảnh hưởng của chiến lược định danh đến batch insert

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao chiến lược sinh khóa chính ảnh hưởng đến khả năng gom nhiều INSERT thành JDBC batch.
- Phân biệt IDENTITY, SEQUENCE, TABLE và khóa được cấp từ ứng dụng trong JPA/Hibernate.
- Hiểu giới hạn của GenerationType.IDENTITY khi Hibernate cần lấy khóa chính ngay sau mỗi INSERT.
- Cấu hình batch insert trong Spring Boot và phân biệt cấu hình Hibernate với khả năng rewrite của MySQL Connector/J.
- Thiết kế vòng lặp ghi dữ liệu lớn bằng flush() và clear() để kiểm soát persistence context.
- Đo hiệu quả batch insert và lựa chọn chiến lược định danh phù hợp với MySQL.

## 1. Batch insert là gì?

Batch insert là cách gửi nhiều câu lệnh INSERT đến database theo một nhóm để giảm số lần trao đổi giữa ứng dụng và MySQL. Thay vì gửi một request cho từng hàng, JDBC có thể thêm nhiều bộ tham số vào cùng một PreparedStatement rồi gọi executeBatch().

Ví dụ một luồng không gom batch:

~~~sql
INSERT INTO audit_log(message) VALUES ('created');
INSERT INTO audit_log(message) VALUES ('updated');
INSERT INTO audit_log(message) VALUES ('deleted');
~~~

Khi gom batch, driver nhận nhiều bộ tham số của cùng một câu lệnh prepared statement và gửi chúng theo cơ chế batch:

~~~java
PreparedStatement statement =
    connection.prepareStatement(
        "INSERT INTO audit_log(message) VALUES (?)");

statement.setString(1, "created");
statement.addBatch();

statement.setString(1, "updated");
statement.addBatch();

statement.setString(1, "deleted");
statement.addBatch();

statement.executeBatch();
~~~

JPA/Hibernate có thể thực hiện thao tác tương tự ở phía ORM. Khi ứng dụng gọi persist() nhiều entity, Hibernate có thể trì hoãn SQL INSERT, nhóm các lệnh cùng loại rồi gửi theo batch khi flush.

Batch insert thường giúp:

- Giảm số round trip giữa ứng dụng và MySQL.
- Giảm overhead khi chuẩn bị và gửi từng câu lệnh riêng.
- Tăng throughput cho import, ETL, ghi log và các tác vụ tạo nhiều entity.

Batch không làm mỗi hàng biến mất khỏi chi phí xử lý. MySQL vẫn phải kiểm tra constraint, cập nhật index, ghi redo/undo và ghi binary log theo transaction. Kích thước batch quá lớn có thể làm tăng bộ nhớ, thời gian giữ lock, kích thước transaction và replication lag.

## 2. JPA, Hibernate và quá trình sinh khóa chính

Trong JPA, khóa chính thường được khai báo bằng @Id. Nếu ứng dụng hoặc provider tự sinh giá trị, có thể dùng @GeneratedValue với một trong các chiến lược:

| Chiến lược | Cách lấy định danh |
|---|---|
| IDENTITY | Database sinh giá trị khi INSERT, ví dụ MySQL AUTO_INCREMENT |
| SEQUENCE | Database cấp giá trị từ sequence object |
| TABLE | Provider dùng một bảng để cấp phát giá trị định danh |
| AUTO | Provider tự chọn chiến lược dựa trên dialect, kiểu khóa và phiên bản provider |

Một chiến lược khác là **application-assigned identifier**: ứng dụng tạo ID trước khi gọi persist(), ví dụ UUID hoặc ID từ dịch vụ cấp phát riêng. Đây không phải một giá trị GenerationType trong JPA; entity chỉ khai báo @Id và ứng dụng gán giá trị.

Chiến lược định danh quyết định thời điểm Hibernate có thể biết khóa chính. Đây là điểm quan trọng đối với batch insert:

- Nếu ID đã có trước INSERT, Hibernate có thể xếp lệnh vào batch.
- Nếu ID chỉ được MySQL tạo sau INSERT, Hibernate thường phải thực thi INSERT để lấy khóa ngay.
- Nếu provider phải gọi database để cấp trước từng ID, chi phí lấy ID có thể làm giảm lợi ích của batch; cơ chế cấp phát theo block có thể giảm số lần gọi.

## 3. Vì sao IDENTITY cản trở JDBC insert batching?

MySQL thường dùng AUTO_INCREMENT cho khóa chính số nguyên. Trong JPA, mapping phổ biến là:

~~~java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Các thuộc tính khác
}
~~~

Giá trị id chỉ được MySQL sinh khi câu INSERT được thực thi. Hibernate cần lấy khóa đó để gán vào entity đang được quản lý và để duy trì identity map trong persistence context. Vì vậy, với chiến lược IDENTITY, Hibernate phải thực thi INSERT ngay khi persist entity trong các trường hợp thông thường thay vì trì hoãn nó để gom vào JDBC batch.

Hệ quả:

- hibernate.jdbc.batch_size có thể đã được cấu hình nhưng INSERT của entity dùng IDENTITY vẫn không được batch theo cách Hibernate thông thường.
- Gọi saveAll() với hàng nghìn entity không tự biến chúng thành một câu INSERT nhiều hàng.
- Bật rewriteBatchedStatements=true trong Connector/J cũng không tạo ra batch nếu Hibernate đã gửi từng INSERT riêng lẻ.
- MySQL vẫn sinh khóa AUTO_INCREMENT bình thường; giới hạn nằm ở cách ORM cần nhận khóa được sinh ngay sau mỗi lần INSERT.

IDENTITY có ưu điểm là đơn giản, dùng trực tiếp cơ chế MySQL và dễ tương thích với schema hiện hữu. Với CRUD thông thường, đây vẫn có thể là lựa chọn hợp lý. Nếu workload chủ yếu là insert hàng loạt và throughput là yêu cầu quan trọng, nên đo tác động của IDENTITY và cân nhắc chiến lược cấp ID trước INSERT.

Không nên kết luận rằng MySQL không hỗ trợ multi-row INSERT hoặc JDBC batch với auto-increment. MySQL và JDBC driver có thể xử lý batch INSERT, nhưng Hibernate không thể gom các INSERT theo đường thực thi IDENTITY thông thường khi cần lấy generated key ngay sau mỗi entity.

## 4. SEQUENCE và đặc điểm của MySQL

GenerationType.SEQUENCE dùng sequence object để lấy ID trước khi INSERT. Trên database có sequence native, provider có thể lấy trước một dải ID rồi ghi nhiều hàng bằng batch.

MySQL không có sequence object native giống PostgreSQL hoặc Oracle. Vì vậy, không nên giả định khai báo sau sẽ hoạt động giống nhau trên mọi phiên bản Hibernate/MySQL:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

Kết quả phụ thuộc JPA provider, dialect và phiên bản. Provider có thể báo không hỗ trợ hoặc dùng cơ chế sequence-style dựa trên bảng. Hãy kiểm tra DDL và SQL thực tế được Hibernate sinh ra.

Khi cần ID được cấp trước INSERT trên MySQL, có thể xem xét TABLE generator, UUID do ứng dụng tạo hoặc một dịch vụ cấp ID. Không chọn SEQUENCE chỉ vì nó thường được khuyên dùng cho batch insert trên database có sequence native.

## 5. TABLE generator: cấp ID trước khi INSERT

GenerationType.TABLE sử dụng một bảng quản lý giá trị định danh. Hibernate đọc và cập nhật bộ đếm trong bảng này để cấp ID cho entity.

Ví dụ:

~~~java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @TableGenerator(
        name = "order_id_generator",
        table = "id_generator",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "orders",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "order_id_generator"
    )
    private Long id;
}
~~~

Hibernate dùng bảng id_generator để cấp trước một block ID. allocationSize=50 cho biết provider có thể cấp phát theo block 50 giá trị theo cơ chế generator/optimizer mà nó hỗ trợ. Nhờ đó, provider không nhất thiết phải truy vấn bảng generator cho từng entity.

Ví dụ cấu trúc bảng generator ở mức khái niệm:

~~~sql
CREATE TABLE id_generator (
    generator_name VARCHAR(100) NOT NULL PRIMARY KEY,
    next_value BIGINT NOT NULL
) ENGINE=InnoDB;
~~~

DDL chính xác có thể do Hibernate tự sinh và khác nhau theo dialect/version. Không tự tạo bảng bằng schema trên nếu chưa đối chiếu DDL Hibernate yêu cầu.

### 5.1. Ưu điểm

- ID có trước INSERT, cho phép Hibernate trì hoãn và gom INSERT thành batch.
- Có thể dùng với MySQL mà không cần sequence object native.
- Có thể cấp phát theo block để giảm số lần truy cập bảng generator.
- Có thể giữ khóa số nguyên gọn hơn UUID trong index clustered của InnoDB.

### 5.2. Chi phí và lưu ý

- Bảng generator tạo thêm truy cập và có thể trở thành điểm tranh chấp nếu nhiều transaction cùng cấp ID.
- allocationSize lớn giảm tần suất truy cập generator nhưng có thể tạo khoảng trống ID khi ứng dụng restart hoặc block chưa dùng hết.
- Tất cả instance ứng dụng phải dùng cấu hình generator tương thích. Không để các node dùng allocation size/optimizer khác nhau một cách tùy tiện.
- Cần kiểm tra generator table, unique segment và transaction behavior khi chạy nhiều instance.
- ID không bảo đảm liên tục; không dùng số ID làm số chứng từ nghiệp vụ không có khoảng trống.

TABLE generator là một lựa chọn có thể batch insert, nhưng cần benchmark với tải thực tế. Với hệ thống có nhiều node và throughput cao, phải đo contention trên bảng generator trước khi chọn.

## 6. UUID hoặc ID do ứng dụng cấp

Nếu ứng dụng tạo ID trước khi ghi, Hibernate không phải chờ MySQL trả generated key sau mỗi INSERT. Điều này giúp giữ khả năng gom INSERT vào JDBC batch.

Ví dụ entity dùng UUID:

~~~java
import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private UUID id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.id = UUID.randomUUID();
        this.name = name;
    }
}
~~~

ID đã có trước khi persist:

~~~java
Customer customer = new Customer("An");
entityManager.persist(customer);
~~~

Với khóa UUID, ứng dụng có thể tạo ID mà không cần round trip đến database. Điều này hữu ích cho batch insert, tạo dữ liệu offline hoặc sinh ID ở nhiều service độc lập.

### 6.1. Ảnh hưởng đến InnoDB primary key

InnoDB tổ chức dữ liệu bảng theo clustered index, thường là primary key. Mỗi secondary index cũng chứa giá trị primary key để tham chiếu hàng tương ứng. Vì vậy, kích thước và tính chất sắp xếp của khóa chính ảnh hưởng đến mọi index phụ.

UUID ngẫu nhiên có một số chi phí:

- Khóa lớn hơn BIGINT, làm tăng dung lượng clustered index và secondary index.
- Các giá trị ngẫu nhiên có thể chèn vào nhiều vị trí B-tree, gây page split và giảm locality.
- Cache hiệu quả có thể thấp hơn khi index lớn và phân tán.

UUID vẫn có lợi thế về khả năng tạo ID phân tán và không cần round trip. Nếu dùng UUID, hãy cân nhắc biểu diễn lưu trữ gọn như BINARY(16) thay vì chuỗi 36 ký tự khi mapping và tooling cho phép.

### 6.2. ID có thứ tự thời gian

UUID có thứ tự thời gian hoặc ID phân tán có tính tăng dần gần đúng có thể cải thiện locality so với UUID ngẫu nhiên. Ví dụ UUIDv7 được thiết kế có thành phần timestamp ở đầu để giá trị có xu hướng sắp xếp theo thời gian.

Tuy nhiên:

- Không phải mọi phiên bản JPA/Hibernate đều có cùng hỗ trợ UUIDv7 tích hợp.
- Phải kiểm tra cách sinh ID, mapping JDBC và kiểu cột MySQL.
- Không giả định ID thời gian là thứ tự commit chính xác hoặc thay thế timestamp nghiệp vụ.
- Nếu nhiều node sinh ID, cần bảo đảm thuật toán và độ duy nhất theo thư viện được chọn.

Không chuyển sang UUID chỉ để batch insert nếu hệ thống đang phụ thuộc mạnh vào BIGINT AUTO_INCREMENT và index hiện tại. Hãy đo kích thước index, tốc độ insert, buffer pool hit rate và chi phí join trước khi thay đổi.

### 6.3. ID Snowflake hoặc ULID

Một số hệ thống tạo ID từ timestamp, node identifier và sequence cục bộ (ví dụ Snowflake) hoặc dùng ULID. Các loại ID này có thể được sinh trước INSERT và hỗ trợ batch.

Điều kiện cần đánh giá:

- Không trùng ID giữa các instance, kể cả khi node restart hoặc đổi cấu hình.
- Đồng hồ hệ thống phải được quản lý nếu thuật toán phụ thuộc timestamp.
- Kiểu Java và kiểu cột MySQL phải đủ phạm vi.
- Thứ tự ID có thể phản ánh thời gian gần đúng, không nhất thiết thứ tự transaction.
- Cần có quy trình cấp node ID và xử lý sự cố khi nhiều instance dùng cùng node identifier.

## 7. So sánh chiến lược định danh với batch insert

| Chiến lược | ID có trước INSERT? | Khả năng Hibernate batch INSERT | Đặc điểm khi dùng MySQL |
|---|---:|---|---|
| IDENTITY / AUTO_INCREMENT | Không | Thông thường không batch được qua Hibernate identity path | Đơn giản, native, generated key lấy sau INSERT |
| SEQUENCE native | Có | Thường có thể batch | MySQL không có sequence object native; provider/dialect có thể không hỗ trợ hoặc mô phỏng |
| TABLE | Có, sau khi cấp từ generator | Có thể batch | Dùng bảng cấp ID; cần quản lý contention và allocation |
| UUID do ứng dụng sinh | Có | Có thể batch | Phân tán tốt; cần cân nhắc kích thước và locality của primary key |
| Snowflake/ULID/ID tự cấp | Có | Có thể batch | Cần quản lý tính duy nhất, node/time và mapping |

Không có chiến lược tốt nhất cho mọi ứng dụng. Nếu cần throughput insert cao trên MySQL, các chiến lược có ID trước INSERT thường có lợi thế với Hibernate batching. Nếu ưu tiên đơn giản, IDENTITY có thể hợp lý dù không batch theo đường Hibernate thông thường.

## 8. Cấu hình JDBC batching trong Spring Boot

Hibernate không bật batch insert lớn chỉ vì ứng dụng dùng saveAll(). Cần cấu hình kích thước batch.

Với Spring Boot, có thể đặt trong application.yml:

~~~yaml
spring:
  jpa:
    properties:
      hibernate.jdbc.batch_size: 50
      hibernate.order_inserts: true
      hibernate.order_updates: true
~~~

Các thuộc tính:

- hibernate.jdbc.batch_size: số statement Hibernate cố gắng gom vào một JDBC batch. Giá trị khởi đầu thường ở mức vài chục, sau đó benchmark.
- hibernate.order_inserts: sắp xếp INSERT theo entity type và thứ tự phù hợp để tăng khả năng gom các lệnh cùng loại.
- hibernate.order_updates: sắp xếp UPDATE để cải thiện batching và trong một số trường hợp giảm deadlock.

Đây là cấu hình provider-specific của Hibernate, không phải thuộc tính chuẩn JPA. Spring Boot truyền chúng vào Hibernate thông qua spring.jpa.properties.

Nếu dùng properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

### 8.1. Batch size không phải transaction size

Hai khái niệm thường bị nhầm:

- **Batch size:** số câu lệnh được gom vào một lần JDBC executeBatch().
- **Transaction size:** số thao tác được commit hoặc rollback cùng nhau.

Ví dụ batch size 50 nhưng một transaction ghi 5.000 hàng thì Hibernate có thể gửi khoảng 100 batch trong cùng transaction. Transaction vẫn giữ các thay đổi cho đến khi commit.

Transaction quá lớn có thể làm tăng undo/redo, thời gian giữ lock, thời gian rollback và replication lag. Batch size và transaction size cần được chọn riêng theo workload.

### 8.2. Sắp xếp INSERT

order_inserts=true giúp Hibernate sắp xếp các INSERT để lệnh của cùng entity type có thể được gom lại. Nếu một transaction persist xen kẽ nhiều loại entity, việc sắp xếp có thể tăng số lệnh liên tiếp cùng prepared statement.

Tuy nhiên, sắp xếp có thể thay đổi thứ tự thực thi SQL so với thứ tự gọi persist(). Không dựa vào thứ tự INSERT để biểu diễn thứ tự nghiệp vụ; dùng khóa ngoại, transaction và quan hệ entity đúng cách.

## 9. Cấu hình MySQL Connector/J cho batch

Hibernate tạo JDBC batch thông qua addBatch() và executeBatch(). MySQL Connector/J có thuộc tính rewriteBatchedStatements để viết lại một số batch INSERT/REPLACE thành câu lệnh nhiều giá trị, giảm số lần trao đổi với server.

Ví dụ URL:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?rewriteBatchedStatements=true
~~~

Hoặc cấu hình trong Spring Boot:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.internal.example:3306/sales_app?rewriteBatchedStatements=true
~~~

Thuộc tính này chỉ tối ưu batch mà ứng dụng/ORM thực sự gửi xuống JDBC. Nó không thể biến một chuỗi INSERT riêng lẻ do Hibernate thực thi ngay lập tức thành batch ORM.

Vì vậy, nếu entity dùng GenerationType.IDENTITY, chỉ bật rewriteBatchedStatements=true thường không giải quyết được giới hạn batching do Hibernate phải lấy ID sau từng INSERT.

Một số lưu ý:

- Driver có thể viết lại batch INSERT thành multi-values INSERT khi câu lệnh và điều kiện hỗ trợ.
- Hành vi generated keys và số lượng update count cần được kiểm tra với phiên bản Connector/J.
- Batch lớn có thể tạo packet lớn; xem xét max_allowed_packet, kích thước payload và bộ nhớ.
- Benchmark cả khi bật và tắt rewrite để biết hiệu quả trên workload thực tế.

Không nhầm rewriteBatchedStatements với useServerPrepStmts. Hai thuộc tính điều khiển các khía cạnh khác nhau của cách driver gửi câu lệnh; tổ hợp có thể ảnh hưởng đến đường thực thi và phải được kiểm thử.

## 10. Ví dụ cấu hình entity với TABLE generator

Ví dụ một entity dùng ID cấp trước:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "import_item")
public class ImportItem {
    @Id
    @TableGenerator(
        name = "import_item_gen",
        table = "id_generator",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "import_item",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "import_item_gen"
    )
    private Long id;

    @Column(nullable = false)
    private String payload;

    protected ImportItem() {
    }

    public ImportItem(String payload) {
        this.payload = payload;
    }
}
~~~

Sau khi cấu hình Hibernate batching, các INSERT của ImportItem có thể được trì hoãn và gom thành batch. Việc cấp ID theo block giảm số lần truy cập generator table so với cấp từng ID riêng lẻ.

Để biết Hibernate có thực sự batch, hãy xem SQL log hoặc thống kê JDBC/Hibernate trong môi trường kiểm thử. Việc entity có ID trước INSERT là điều kiện quan trọng, nhưng không phải điều kiện duy nhất: batch size phải lớn hơn 0, các INSERT cần tương thích để gom, transaction phải được flush đúng lúc và không có cơ chế khác buộc thực thi ngay.

## 11. Persist hàng loạt và quản lý persistence context

Một ví dụ đơn giản:

~~~java
@Transactional
public void importItems(List<String> payloads) {
    for (String payload : payloads) {
        entityManager.persist(new ImportItem(payload));
    }
}
~~~

Với số lượng nhỏ, cách này có thể đủ. Với hàng trăm nghìn entity, persistence context sẽ giữ tham chiếu đến các entity đã persist cho đến khi chúng được detach hoặc transaction kết thúc. Bộ nhớ có thể tăng mạnh.

Có thể flush và clear theo từng lô:

~~~java
@Transactional
public void importItems(List<String> payloads) {
    int batchSize = 50;
    int count = 0;

    for (String payload : payloads) {
        entityManager.persist(new ImportItem(payload));
        count++;

        if (count % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

- flush() đồng bộ các thay đổi đang chờ trong persistence context xuống database. Đây là thời điểm Hibernate có thể gửi JDBC batch.
- clear() detach tất cả entity khỏi persistence context, giúp giải phóng bộ nhớ mà persistence context đang giữ.
- clear() không commit transaction. Các INSERT đã flush vẫn nằm trong transaction hiện tại cho đến khi commit.

Đoạn code trên vẫn dùng một transaction cho toàn bộ danh sách. Với dữ liệu rất lớn, có thể cần chia thành nhiều transaction độc lập để giới hạn thời gian transaction và khả năng rollback. Khi chia transaction, mỗi chunk cần có ranh giới commit rõ ràng và chiến lược retry/idempotency.

Không gọi clear() trước flush() nếu các thay đổi chưa được đồng bộ, vì các entity đang được quản lý có thể bị detach trước khi Hibernate phát SQL theo ý định.

### 11.1. Transaction theo chunk

Một cách tổ chức là dùng service điều phối và một bean khác xử lý từng chunk với transaction riêng:

~~~java
@Service
public class ImportCoordinator {
    private final ImportChunkWriter chunkWriter;

    public ImportCoordinator(ImportChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void importAll(List<String> values) {
        int chunkSize = 1000;

        for (int start = 0; start < values.size(); start += chunkSize) {
            int end = Math.min(start + chunkSize, values.size());
            chunkWriter.writeChunk(values.subList(start, end));
        }
    }
}

@Service
public class ImportChunkWriter {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void writeChunk(List<String> values) {
        int batchSize = 50;
        int count = 0;

        for (String value : values) {
            entityManager.persist(new ImportItem(value));
            count++;

            if (count % batchSize == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Hai bean tách riêng để lời gọi qua Spring proxy có thể áp dụng @Transactional cho mỗi chunk. Nếu gọi một method @Transactional khác trong cùng object bằng self-invocation, transaction proxy mặc định của Spring có thể không được kích hoạt như mong muốn.

Chunk size 1.000 và batch size 50 chỉ là giá trị minh họa. Chọn theo thời gian commit, dung lượng transaction, replication lag, giới hạn packet và khả năng retry.

## 12. saveAll() có bảo đảm batch insert không?

Spring Data JPA cung cấp saveAll() để lưu một iterable entity. Tuy nhiên, saveAll() không phải cam kết rằng tất cả INSERT sẽ được gửi bằng một JDBC batch.

Kết quả phụ thuộc:

- Entity được xem là mới hay đã tồn tại.
- Chiến lược định danh của entity.
- Hibernate batch size.
- Cách transaction và flush được quản lý.
- Các callback, cascade, relationship và SQL khác phát sinh.
- Driver có hỗ trợ tối ưu batch hay không.

Nếu dùng IDENTITY, Hibernate thường phải INSERT ngay để lấy ID nên saveAll() vẫn có thể tạo một INSERT round trip cho từng entity.

### 12.1. Lưu ý khi dùng ID tự cấp với Spring Data JPA

Spring Data JPA cần xác định entity mới hay đã tồn tại để chọn persist() hoặc merge(). Với entity dùng UUID đã được gán trước khi gọi save(), trường id không còn null. Theo cơ chế phát hiện mặc định dựa trên ID, entity có thể bị xem là đã tồn tại và đi theo nhánh merge().

Có thể dùng thuộc tính @Version nullable để Spring Data nhận diện entity mới theo version, hoặc implement Persistable<ID> và cung cấp isNew() phù hợp. Ví dụ:

~~~java
import jakarta.persistence.*;
import org.springframework.data.domain.Persistable;
import java.util.UUID;

@Entity
public class ExternalEvent implements Persistable<UUID> {
    @Id
    private UUID id;

    @Version
    private Long version;

    @Transient
    private boolean newEntity = true;

    protected ExternalEvent() {
    }

    public ExternalEvent(UUID id) {
        this.id = id;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    void markNotNewAfterPersist() {
        newEntity = false;
    }

    @PostLoad
    void markNotNewAfterLoad() {
        newEntity = false;
    }
}
~~~

Đây là mẫu minh họa; cần bảo đảm lifecycle callback và cách deserialize entity phù hợp ứng dụng. Một cách khác là gọi EntityManager.persist() trực tiếp khi đã biết entity mới. Không dùng merge() cho mọi entity mới chỉ vì ID đã được gán.

## 13. Quan hệ entity và thứ tự INSERT

Khi một entity tham chiếu entity khác bằng foreign key, Hibernate phải bảo đảm thứ tự SQL phù hợp với constraint. Ví dụ tạo Order và các OrderItem:

~~~java
Order order = new Order();
order.addItem(new OrderItem("Keyboard"));
order.addItem(new OrderItem("Mouse"));

entityManager.persist(order);
~~~

Hibernate có thể phải INSERT parent trước child tùy mapping và cách cascade. order_inserts=true có thể sắp xếp INSERT theo entity type, nhưng không xóa bỏ dependency của foreign key.

Một transaction tạo nhiều loại entity có thể hình thành nhiều nhóm batch. Batch size 50 không có nghĩa mọi 50 entity liên tiếp trong vòng lặp luôn nằm trong một batch duy nhất.

Các yếu tố ảnh hưởng:

- Entity type và SQL INSERT tương ứng.
- Generated identifier và thời điểm ID sẵn sàng.
- Quan hệ cascade và thứ tự dependency.
- Flush mode và các truy vấn buộc Hibernate flush.
- Callback hoặc listener có thực hiện truy vấn/ghi bổ sung.

Thiết kế quan hệ rõ ràng và đo SQL thực tế thay vì suy luận số batch chỉ từ số entity trong collection.

## 14. Batch insert với entity có @Version

Optimistic locking dùng @Version để phát hiện cập nhật đồng thời:

~~~java
@Entity
public class InventoryItem {
    @Id
    private Long id;

    @Version
    private Long version;

    private Integer quantity;
}
~~~

Hibernate có thể batch các UPDATE versioned entity nếu driver/provider hỗ trợ update count phù hợp. Thuộc tính Hibernate hibernate.jdbc.batch_versioned_data điều khiển việc batching các DML có version trong một số cấu hình/version. Cần kiểm tra mặc định và hành vi của Hibernate đang dùng trước khi đặt rõ giá trị.

@Version không thay thế transaction hoặc constraint. Với insert mới, version thường được khởi tạo bởi provider; nó không phải chiến lược sinh primary key. Khi batch update, Hibernate cần biết số hàng bị tác động để phát hiện optimistic lock failure.

## 15. Chọn batch size và transaction size

Không có batch size tối ưu cho mọi hệ thống. Một số yếu tố:

- Latency giữa ứng dụng và MySQL.
- Kích thước mỗi row và số cột.
- Số index, foreign key và trigger trên bảng.
- max_allowed_packet và kích thước batch sau khi driver rewrite.
- Bộ nhớ JVM và thời gian giữ persistence context.
- Undo/redo, binary log và replication topology.
- Mức độ tranh chấp khóa với workload giao dịch khác.

Có thể bắt đầu benchmark với các batch size 20, 50 và 100, rồi đo:

| Chỉ số | Điều cần quan sát |
|---|---|
| Rows/second | Throughput thực tế |
| Batch execution time | Thời gian gửi và thực thi một batch |
| Commit latency | Thời gian commit transaction |
| JVM heap | Mức tăng bộ nhớ theo số entity |
| DB CPU và I/O | Tải MySQL trong lúc import |
| Lock wait/deadlock | Mức cạnh tranh với workload khác |
| Replication lag | Độ trễ áp dụng binary log ở replica |
| Packet/statement size | Có vượt giới hạn driver/server không |

Tăng batch size không phải lúc nào cũng tăng throughput. Khi batch quá lớn, thời gian thực thi và commit có thể tăng, đồng thời việc retry một transaction thất bại trở nên tốn kém.

## 16. Kiểm tra Hibernate có thực sự batch hay không

### 16.1. Bật thống kê Hibernate trong môi trường kiểm thử

Có thể bật:

~~~yaml
spring:
  jpa:
    properties:
      hibernate.generate_statistics: true
~~~

Hibernate Statistics có thể cung cấp thông tin về entity insert, flush, prepared statement và batch theo phiên bản. Không bật logging SQL chi tiết liên tục ở production nếu nó tạo lượng log lớn hoặc làm lộ dữ liệu.

### 16.2. Xem SQL và JDBC execution

Trong môi trường lab, bật log phù hợp để quan sát:

- SQL INSERT có được trì hoãn đến flush không.
- Hibernate có log batch execution hay không.
- Mỗi batch có bao nhiêu statement.
- Generated key được lấy sau từng INSERT hay đã có trước.
- Driver có rewrite batch thành multi-values INSERT hay không.

Chỉ nhìn thấy nhiều câu INSERT trong log chưa đủ để kết luận batching không hoạt động: driver có thể gửi batch theo giao thức khác nhau. Kết hợp Hibernate statistics, log driver, MySQL general log trong lab hoặc tracing phù hợp để xác định.

### 16.3. So sánh hai mapping

Tạo hai entity tương đương:

- IdentityItem dùng GenerationType.IDENTITY.
- TableGeneratedItem dùng GenerationType.TABLE với allocation block.

Chạy cùng một khối lượng dữ liệu, cùng batch size và cùng transaction size. Ghi nhận thời gian, số lần execute, số lần lấy ID và tài nguyên MySQL. Không dùng hai schema hoặc hai cấu hình khác nhau ngoài chiến lược ID vì sẽ làm kết quả benchmark thiếu công bằng.

## 17. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Thực tế | Cách xử lý |
|---|---|---|
| Có saveAll() là tự batch | saveAll() không bảo đảm JDBC batch | Cấu hình Hibernate và kiểm tra ID strategy/SQL |
| Chỉ cần đặt batch_size | IDENTITY vẫn có thể buộc Hibernate INSERT ngay | Chọn ID có trước INSERT nếu batching là yêu cầu |
| rewriteBatchedStatements=true sửa được mọi trường hợp | Driver chỉ rewrite JDBC batch đã được gửi xuống | Bảo đảm Hibernate thực sự tạo batch trước |
| SEQUENCE luôn tốt nhất | MySQL không có native sequence object | Kiểm tra dialect/provider; cân nhắc TABLE hoặc ID cấp từ ứng dụng |
| UUID luôn nhanh hơn AUTO_INCREMENT | UUID ngẫu nhiên làm index lớn và phân tán | Đo index, locality và throughput |
| flush() là commit | Flush chỉ gửi SQL xuống database trong transaction | Gọi commit theo ranh giới transaction |
| clear() rollback dữ liệu | Clear detach entity khỏi persistence context | Chỉ clear sau flush nếu cần giữ thay đổi |
| Batch size bằng transaction size | Đây là hai giới hạn khác nhau | Cấu hình và đo độc lập |
| ID phải liên tục | Rollback, preallocation và concurrency có thể tạo khoảng trống | Không dùng primary key làm số thứ tự nghiệp vụ |
| Tăng batch vô hạn sẽ tăng tốc | Packet, memory, lock và transaction có thể trở thành bottleneck | Benchmark từng mức và theo dõi server |

## 18. Quy trình lựa chọn cho MySQL

Một cách ra quyết định thực tế:

1. Nếu hệ thống CRUD thông thường, ưu tiên đơn giản và không có yêu cầu import tốc độ cao, IDENTITY với AUTO_INCREMENT có thể phù hợp.
2. Nếu insert hàng loạt là workload trọng yếu, đánh giá ID cấp trước để Hibernate có thể batch.
3. Nếu cần khóa số nguyên, thử TABLE generator có allocation block và đo contention của generator table.
4. Nếu cần sinh ID phân tán, cân nhắc UUID hoặc ID dạng time-ordered/Snowflake; đo chi phí index InnoDB.
5. Cấu hình Hibernate jdbc.batch_size, order_inserts và Connector/J rewriteBatchedStatements theo benchmark.
6. Tách batch size khỏi transaction size; dùng flush/clear để kiểm soát persistence context.
7. Chạy thử với schema, index, trigger, constraint và replication gần production.
8. Kiểm tra khả năng retry và idempotency trước khi chạy import có thể bị ngắt giữa chừng.

## 19. Checklist trước khi triển khai batch insert

### Chiến lược ID

- [ ] Xác định entity dùng IDENTITY, TABLE, UUID hay ID do ứng dụng cấp.
- [ ] Kiểm tra ID có sẵn trước INSERT hay phải lấy từ MySQL sau INSERT.
- [ ] Với MySQL, không giả định có native SEQUENCE.
- [ ] Nếu dùng UUID, đánh giá kiểu cột, kích thước index và locality.
- [ ] Nếu dùng TABLE generator, kiểm tra allocationSize và contention giữa các instance.
- [ ] Nếu dùng Spring Data JPA với ID tự cấp, kiểm tra cơ chế phát hiện entity mới.

### Hibernate và JDBC

- [ ] Cấu hình hibernate.jdbc.batch_size.
- [ ] Đánh giá hibernate.order_inserts và hibernate.order_updates.
- [ ] Kiểm tra rewriteBatchedStatements của Connector/J nếu phù hợp.
- [ ] Kiểm tra generated key có buộc thực thi INSERT ngay không.
- [ ] Đo batch thực tế bằng statistics/log trong môi trường kiểm thử.

### Bộ nhớ và transaction

- [ ] Dùng flush() và clear() theo batch khi persistence context lớn.
- [ ] Chọn transaction size riêng với JDBC batch size.
- [ ] Theo dõi heap, undo/redo, lock wait và replication lag.
- [ ] Có checkpoint và idempotency cho import có thể chạy lại.
- [ ] Không giữ transaction hoặc connection trong thời gian không cần thiết.

## 20. Bài tập thực hành

Một ứng dụng Spring Boot nhập 500.000 dòng đơn hàng vào MySQL. Entity hiện tại dùng GenerationType.IDENTITY, saveAll() nhận toàn bộ danh sách và transaction kéo dài đến khi import xong. Sau khi tăng dữ liệu, thời gian import tăng mạnh và JVM heap thường xuyên cao.

Hãy thử nghiệm trong môi trường lab:

1. Bật Hibernate statistics và ghi nhận thời gian import hiện tại, số INSERT và heap.
2. Xác nhận mapping IDENTITY khiến Hibernate thực thi INSERT để lấy generated key.
3. Tạo một biến thể entity dùng TABLE generator với allocationSize 50; kiểm tra generator table và ID được cấp trước.
4. Tạo một biến thể khác dùng UUID do ứng dụng sinh trước persist.
5. Cấu hình hibernate.jdbc.batch_size=50 và hibernate.order_inserts=true.
6. Thử Connector/J với rewriteBatchedStatements=true, so sánh với cấu hình tắt.
7. Thực hiện import bằng flush()/clear() sau mỗi batch, rồi thử transaction theo chunk 1.000 hàng.
8. So sánh rows/second, heap, DB CPU, thời gian commit, dung lượng index và replication lag.
9. Dừng tiến trình giữa import, chạy lại từ checkpoint và kiểm tra không tạo dữ liệu trùng.
10. Viết kết luận chọn IDENTITY, TABLE hay UUID cho workload này và nêu rõ trade-off.

**Câu hỏi tự kiểm tra:**

1. Vì sao Hibernate thường không batch INSERT cho entity dùng IDENTITY?
2. Vì sao rewriteBatchedStatements=true không khắc phục được việc Hibernate gửi INSERT riêng lẻ?
3. MySQL khác PostgreSQL về native sequence object như thế nào?
4. TABLE generator cấp ID trước INSERT bằng cách nào?
5. UUID ngẫu nhiên ảnh hưởng đến clustered index và secondary index của InnoDB ra sao?
6. hibernate.jdbc.batch_size khác transaction size như thế nào?
7. flush() và clear() có vai trò gì trong vòng lặp import lớn?
8. Vì sao Spring Data JPA có thể coi entity UUID đã gán ID là entity cũ?
9. Khi nào cần dùng Persistable.isNew() hoặc nullable @Version?
10. Những metric nào cần đo trước khi kết luận batch size 100 tốt hơn 50?

## Kết luận

Chiến lược định danh quyết định thời điểm Hibernate biết primary key và vì thế ảnh hưởng trực tiếp đến khả năng trì hoãn, gom INSERT thành JDBC batch. Với MySQL, IDENTITY/AUTO_INCREMENT đơn giản nhưng thường ngăn Hibernate batch INSERT do generated key chỉ có sau khi thực thi. TABLE generator, UUID hoặc ID do ứng dụng cấp có thể cung cấp ID trước INSERT và hỗ trợ batching, đổi lại là chi phí generator hoặc kích thước/locality của index. Muốn đạt throughput tốt, cần kết hợp chiến lược ID phù hợp, cấu hình Hibernate và Connector/J, quản lý persistence context, chọn transaction size hợp lý và đo trên workload gần production.

## Tài liệu tham khảo

- [Hibernate ORM User Guide — Identifiers](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#identifiers)
- [Hibernate ORM User Guide — JDBC Batching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#batch)
- [Spring Data JPA Reference — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [MySQL Connector/J Developer Guide — Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL 8.4 Reference Manual — InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
