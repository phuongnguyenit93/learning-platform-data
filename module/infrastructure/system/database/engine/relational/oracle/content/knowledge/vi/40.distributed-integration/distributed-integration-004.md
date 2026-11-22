# XA transaction từ Java và lựa chọn quản lý giao dịch toàn cục

## 1. Vì sao ứng dụng Java cần XA transaction?

Một giao dịch thông thường thường chỉ thay đổi dữ liệu trong một database connection. Ví dụ, ứng dụng cập nhật đơn hàng và tồn kho trong cùng một Oracle Database có thể dùng một local transaction do JDBC connection quản lý:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection);
        updateInventory(connection);
        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
```

Khi một nghiệp vụ cần cập nhật nhiều resource manager độc lập, local transaction trên một connection không đủ để bảo đảm tất cả cùng commit hoặc cùng rollback. Ví dụ:

- Ghi đơn hàng vào Oracle Database và gửi message vào JMS broker.
- Cập nhật dữ liệu ở hai Oracle Database độc lập.
- Ghi dữ liệu vào Oracle và một database khác trong cùng một nghiệp vụ.

Nếu ứng dụng commit Oracle trước rồi gửi message thất bại, database và message broker không còn nhất quán. Nếu gửi message trước rồi database rollback, consumer có thể nhận một thông báo về giao dịch chưa được commit.

**XA (eXtended Architecture)** định nghĩa giao thức phối hợp giao dịch giữa một transaction manager và nhiều resource manager. Trong Java, JTA/Jakarta Transactions cung cấp API quản lý giao dịch toàn cục; JDBC XA cung cấp giao diện để database tham gia giao dịch đó.

Mục tiêu của XA là cho phép transaction manager điều phối các resource tham gia theo một quyết định commit/rollback thống nhất, thường thông qua two-phase commit (2PC).

## 2. Các thành phần trong kiến trúc XA

Một hệ thống XA có ba vai trò chính:

| Thành phần | Vai trò | Ví dụ trong Java/Oracle |
|---|---|---|
| Transaction Manager (TM) | Tạo giao dịch toàn cục, enlist resource, điều phối prepare/commit/rollback và phục hồi giao dịch dang dở | JTA implementation trong application server hoặc standalone TM |
| Resource Manager (RM) | Quản lý dữ liệu/tài nguyên và thực hiện nhánh giao dịch theo lệnh của TM | Oracle Database, JMS provider có hỗ trợ XA |
| Application | Xác định ranh giới nghiệp vụ và thực hiện thao tác trên các resource | Java service, EJB, Spring application |

Luồng tổng quát:

```text
Java application
       |
       | begin / commit / rollback
       v
Transaction Manager (JTA)
       |
       +-------------------------+
       |                         |
       v                         v
Oracle XA resource          JMS XA resource
       |                         |
       v                         v
Oracle Database             Message Broker
```

Ứng dụng yêu cầu TM bắt đầu giao dịch toàn cục. Khi ứng dụng sử dụng một XA connection, TM enlist `XAResource` tương ứng vào giao dịch. Khi commit, TM điều phối các resource đã enlist. Ứng dụng không tự quyết định commit từng database/broker một cách độc lập.

### 2.1. Transaction Manager

Transaction Manager là coordinator của giao dịch toàn cục. Nó chịu trách nhiệm:

- Tạo transaction identifier toàn cục (Xid) và quản lý trạng thái giao dịch.
- Enlist/delist các XA resource tham gia.
- Thiết lập timeout và điều phối ranh giới giao dịch.
- Thực hiện prepare rồi commit/rollback theo giao thức XA.
- Ghi log bền vững về quyết định và trạng thái giao dịch để phục hồi sau crash.
- Chạy recovery khi TM hoặc RM khởi động lại.

TM có thể nằm trong application server hoặc là một dịch vụ/thư viện độc lập. Việc chọn TM ảnh hưởng đến cách cấu hình datasource, persistence của transaction log, failover và quy trình vận hành.

### 2.2. Resource Manager

Resource Manager sở hữu tài nguyên được giao dịch bảo vệ. Oracle Database là một RM; JMS broker là RM khác nếu broker hỗ trợ XA. Mỗi RM phải có XA implementation để TM có thể bắt đầu, kết thúc, prepare và hoàn tất nhánh giao dịch.

Một JDBC `DataSource` thông thường chỉ cung cấp local JDBC connection. Để tham gia JTA/XA, ứng dụng cần một XA-capable datasource được TM quản lý, thường được cấu hình từ `XADataSource` của driver.

### 2.3. Application và transaction boundary

Ứng dụng quyết định một nghiệp vụ bắt đầu và kết thúc ở đâu. Ví dụ, tạo đơn hàng có thể bao gồm ghi order, trừ tồn kho và gửi message. Những thao tác này cần nằm trong cùng global transaction nếu yêu cầu nghiệp vụ là atomic giữa các resource.

Application gọi API JTA hoặc sử dụng declarative transaction như EJB container-managed transaction hay Spring transaction abstraction được cấu hình với JTA transaction manager. TM chịu trách nhiệm giao tiếp XA với từng resource.

## 3. XA trong Java: các API quan trọng

### 3.1. JTA / Jakarta Transactions

JTA là API Java để ứng dụng hoặc container làm việc với giao dịch toàn cục. Tùy nền tảng:

- Java EE/Jakarta EE đời cũ dùng namespace `javax.transaction`.
- Jakarta EE 9 trở lên chuyển API JTA sang namespace `jakarta.transaction`.
- Các giao diện XA của Java SE như `javax.transaction.xa.XAResource` và `javax.transaction.xa.Xid` vẫn thuộc package `javax.transaction.xa`.

Không nhầm `jakarta.transaction` với `javax.transaction.xa`: việc đổi namespace JTA không chuyển các XA interfaces thuộc Java SE sang package `jakarta.transaction.xa`.

Các API JTA thường gặp:

| API | Vai trò |
|---|---|
| `UserTransaction` | Ứng dụng bắt đầu, commit hoặc rollback giao dịch theo cách lập trình |
| `TransactionManager` | API quản trị transaction association, suspend/resume và enlist resource; thường dành cho container/framework |
| `Transaction` | Đại diện giao dịch hiện tại, hỗ trợ enlist/delist resource theo contract JTA |
| `Synchronization` | Callback trước/sau completion của transaction |
| `Status` | Các trạng thái như active, marked rollback, preparing, committed hoặc rolled back |

Trong ứng dụng container-managed, thông thường business code không cần gọi `TransactionManager` trực tiếp. Container hoặc framework quản lý transaction context và resource enlistment.

### 3.2. JDBC XA interfaces

Các giao diện XA của JDBC nằm trong Java SE:

- `javax.sql.XADataSource`: factory tạo XA connection.
- `javax.sql.XAConnection`: wrapper cung cấp connection và `XAResource`.
- `javax.transaction.xa.XAResource`: giao diện resource mà TM dùng để điều phối nhánh XA.
- `javax.transaction.xa.Xid`: định danh một nhánh giao dịch toàn cục.

Mô hình quan hệ:

```text
XADataSource
    |
    +-- XAConnection
            |
            +-- getConnection() -> JDBC Connection
            |
            +-- getXAResource() -> XAResource
```

Trong môi trường production, application server hoặc XA pool thường giữ `XAConnection` và enlist `XAResource`. Business code thường nhận một JDBC `Connection` đã được TM quản lý, chứ không tự gọi `XAResource.start()`, `prepare()` hay `commit()`.

### 3.3. Xid và transaction branch

`Xid` nhận diện nhánh giao dịch. Nó gồm:

- `formatId`: định dạng Xid.
- `globalTransactionId`: định danh giao dịch toàn cục.
- `branchQualifier`: định danh nhánh tại một resource manager.

Một global transaction có thể có nhiều branch, ví dụ một branch cho Oracle và một branch cho JMS. TM lưu ánh xạ các branch với quyết định chung của transaction. Xid là thông tin kỹ thuật để TM và RM phối hợp, không phải mã nghiệp vụ để ứng dụng tự tạo rồi commit tùy ý.

## 4. Two-phase commit (2PC)

### 4.1. Pha 1: Prepare

Khi ứng dụng yêu cầu commit global transaction, TM yêu cầu từng RM chuẩn bị commit bằng lệnh `prepare` trên XAResource.

- RM kiểm tra nhánh giao dịch có thể commit hay không.
- RM ghi trạng thái prepared đủ bền vững để có thể hoàn tất sau restart.
- RM trả vote `XA_OK` nếu sẵn sàng commit, hoặc `XA_RDONLY` nếu nhánh chỉ đọc và không cần pha commit tiếp.
- Nếu một RM báo lỗi hoặc không thể prepare, TM có thể quyết định rollback toàn giao dịch.

### 4.2. Pha 2: Commit hoặc rollback

Nếu các RM cần commit đều prepare thành công, TM ghi nhận quyết định commit bền vững rồi gửi commit đến các branch. Nếu quá trình prepare thất bại, TM ra quyết định rollback và gửi rollback tới các branch.

```text
Application requests commit
            |
            v
Transaction Manager records transaction state
            |
            v
       PREPARE phase
            |
      +-----+------+
      |            |
  All vote OK   A branch fails
      |            |
      v            v
  COMMIT decision  ROLLBACK decision
      |            |
      v            v
  Commit branches  Roll back branches
      |            |
      +-----+------+
            v
       Completion
```

### 4.3. Vì sao cần prepare trước commit?

Nếu TM gửi commit ngay cho Oracle rồi sau đó gửi commit cho JMS, lỗi mạng ở giữa có thể khiến một resource đã commit trong khi resource còn lại chưa nhận quyết định. Prepare tạo một trạng thái bền vững để RM cam kết có thể hoàn tất nhánh sau khi TM đưa ra quyết định chung.

2PC cung cấp atomicity giữa các XA resource theo giả định RM/TM thực hiện đúng protocol và recovery được vận hành đúng. Nó không làm cho mọi hệ thống bên ngoài trở thành XA resource; một HTTP API, file system hoặc email service thông thường không tự tham gia 2PC.

### 4.4. One-phase optimization

Nếu global transaction chỉ có một XA resource thực sự tham gia, TM có thể dùng one-phase commit optimization thay cho prepare rồi commit hai pha. Đây là tối ưu được XA hỗ trợ; nó không có nghĩa ứng dụng được tự ý bỏ qua TM.

Khi có nhiều resource manager, 2PC thường cần thiết để đồng bộ quyết định. Một số TM cung cấp last-resource optimization để phối hợp thêm một resource không XA, nhưng cơ chế này có giới hạn atomicity và phụ thuộc TM. Không nên coi nó tương đương một hệ thống mà mọi resource đều hỗ trợ XA.

## 5. Cấu hình Oracle JDBC XA

### 5.1. Oracle XADataSource

Oracle JDBC cung cấp XA datasource implementation, thường được dùng qua lớp `oracle.jdbc.xa.client.OracleXADataSource` trong cấu hình client-side. Ví dụ khởi tạo datasource về mặt API:

```java
import oracle.jdbc.xa.client.OracleXADataSource;

OracleXADataSource xaDataSource = new OracleXADataSource();
xaDataSource.setURL(
    "jdbc:oracle:thin:@//db-host.example.com:1521/app_service"
);
xaDataSource.setUser("APP_USER");
xaDataSource.setPassword(secretFromVault);
```

Đoạn mã chỉ minh họa cấu hình datasource. Trong ứng dụng thực tế, không nên tự quản lý vòng đời XAConnection bằng đoạn code này rồi tự commit từng resource. Hãy đăng ký XA datasource với transaction manager/XA connection pool được hỗ trợ; TM quản lý việc lấy connection, enlist resource, prepare, commit, rollback và recovery.

Tên lớp, constructor, phương thức cấu hình và driver artifact cần được đối chiếu với phiên bản Oracle JDBC đang triển khai. Dùng driver tương thích với Oracle Database, JDK và application server. Không trộn driver JAR khác phiên bản một cách tùy tiện.

### 5.2. Đăng ký XA datasource với transaction manager

Trong application server, datasource thường được khai báo là XA datasource và gắn với JNDI name. TM sử dụng XADataSource để tạo connection và enlist XAResource tự động khi ứng dụng truy cập resource trong global transaction.

Với standalone Java application, cần một TM và XA pool có khả năng tích hợp với nhau. Các thành phần cần cấu hình gồm:

- Oracle XA datasource/driver.
- Tên resource duy nhất và ổn định trong cấu hình TM.
- Connection pool quản lý XA connections.
- Transaction manager và transaction log store bền vững.
- Thông tin xác thực database được quản lý an toàn.
- Cấu hình timeout, recovery credential và khả năng truy cập Oracle sau restart.

Không tạo một `DriverManager.getConnection()` thông thường rồi kỳ vọng TM tự biến local JDBC connection đó thành XA resource. Datasource phải thực sự hỗ trợ XA và được đăng ký đúng với TM.

### 5.3. Ví dụ transaction boundary bằng UserTransaction

Trong môi trường cung cấp `UserTransaction`, code có thể bắt đầu và hoàn tất global transaction:

```java
import jakarta.transaction.UserTransaction;

public final class OrderService {
    private final UserTransaction userTransaction;
    private final DataSource oracleXaDataSource;
    private final ConnectionFactory xaJmsConnectionFactory;

    public void placeOrder(Order order) throws Exception {
        userTransaction.begin();
        try {
            try (Connection connection = oracleXaDataSource.getConnection()) {
                insertOrder(connection, order);
                reserveInventory(connection, order);
            }

            try (JMSContext context = xaJmsConnectionFactory.createContext()) {
                context.createProducer().send(
                    context.createQueue("orders.created"),
                    toMessage(order)
                );
            }

            userTransaction.commit();
        } catch (Exception ex) {
            try {
                userTransaction.rollback();
            } catch (Exception rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}
```

Đây là ví dụ kiến trúc, không phải một lớp có thể copy chạy độc lập: `DataSource` và `ConnectionFactory` phải là resource được TM quản lý và hỗ trợ XA; các helper, JNDI lookup/injection và exception mapping tùy runtime. Trong một số Jakarta Messaging API, cần dùng connection factory XA do container cấu hình; `JMSContext` và cách quản lý resource phải tuân theo contract của application server/provider. Không tự `commit()` local session/connection nằm trong global transaction.

Trong container, có thể dùng declarative transaction để tránh gọi `begin/commit` thủ công:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);
    inventoryRepository.reserve(order);
    orderEventPublisher.publish(order);
}
```

Annotation chỉ tạo global transaction nếu ứng dụng được cấu hình với JTA transaction manager và tất cả datasource/message resources cần phối hợp đều XA-enlisted. Nếu Spring đang dùng `DataSourceTransactionManager` hoặc `JpaTransactionManager` local cho một datasource, annotation không tự biến nhiều resource thành một XA transaction.

### 5.4. Không tự gọi XAResource protocol trong business code

Các phương thức `XAResource.start`, `end`, `prepare`, `commit`, `rollback`, `recover` và `forget` thuộc protocol mà TM điều khiển. Business code không nên tự gọi chúng trên connection lấy từ pool. Làm vậy có thể phá transaction association, khiến TM không biết trạng thái branch hoặc làm hỏng recovery.

Business code chỉ xác định transaction boundary qua JTA/container API; resource enlistment và XA branch lifecycle do TM quản lý.

## 6. Transaction management trong Spring và Jakarta EE

### 6.1. Spring với JTA transaction manager

Spring hỗ trợ giao dịch toàn cục thông qua `JtaTransactionManager` khi có JTA provider và XA datasources được cấu hình. Khi dùng:

```java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    inventoryRepository.reserve(order);
    messagePublisher.publishCreated(order);
}
```

Spring điều phối ranh giới transaction qua JTA. Việc Oracle datasource và JMS connection factory có tham gia global transaction hay không phụ thuộc cấu hình XA và integration với TM. Chỉ có `@Transactional` không đủ để bảo đảm 2PC.

Trong Spring Boot, cần xác định transaction manager thực tế được inject/auto-configure. Nếu ứng dụng có nhiều transaction manager, cần chỉ định manager phù hợp hoặc cấu hình rõ ràng; tránh để service vô tình chạy bằng local manager trong khi developer nghĩ đang dùng JTA.

### 6.2. Jakarta EE container-managed transaction

Trong Jakarta EE, EJB hoặc các thành phần được container quản lý có thể dùng container-managed transactions. Container bắt đầu/commit/rollback giao dịch theo transaction attribute và tự enlist XA datasource/JMS resource khi được truy cập.

Ví dụ EJB:

```java
@Stateless
public class OrderBean {
    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void placeOrder(Order order) {
        // Access XA-managed database and messaging resources.
    }
}
```

`REQUIRED` tham gia transaction hiện tại nếu có; nếu chưa có, container tạo transaction mới. Các attribute khác như `REQUIRES_NEW`, `MANDATORY`, `SUPPORTS`, `NOT_SUPPORTED` và `NEVER` thay đổi cách method tham gia transaction. Chúng là quy tắc propagation của container, không phải các thuật toán commit khác nhau.

### 6.3. Transaction propagation và nhiều transaction manager

Khi một method gọi method khác, cần hiểu propagation:

- `REQUIRED`: dùng transaction hiện tại hoặc tạo transaction mới.
- `REQUIRES_NEW`: suspend transaction hiện tại và chạy transaction độc lập mới.
- `MANDATORY`: yêu cầu caller đã có transaction.
- `SUPPORTS`: tham gia nếu có transaction, nếu không thì chạy không có transaction.
- `NOT_SUPPORTED`: suspend transaction hiện tại trong lúc chạy method.
- `NEVER`: lỗi nếu caller đang có transaction.

Nếu hai repository dùng hai transaction manager độc lập, `@Transactional` mặc định không tự phối hợp chúng thành một global transaction. Phải có một JTA TM chung và resource XA được enlist vào cùng transaction.

### 6.4. Transaction context qua thread và async

JTA transaction association thường gắn với thread/context do TM quản lý. Không được giả định transaction tự truyền sang `new Thread`, executor, `CompletableFuture`, scheduler hoặc reactive pipeline. Nếu công việc được chạy bất đồng bộ, cần cơ chế context propagation được runtime hỗ trợ hoặc thiết kế thành một transaction riêng với thông điệp/command bền vững.

Không giữ một global transaction mở trong thời gian chờ network hoặc công việc async kéo dài. Điều đó có thể giữ lock, connection và prepared branch quá lâu.

## 7. Recovery và in-doubt transaction

### 7.1. Vì sao XA cần recovery log?

2PC có khoảng thời gian mà RM đã prepare nhưng chưa biết quyết định cuối cùng của TM. Nếu TM crash sau khi một RM prepare, RM có thể giữ transaction ở trạng thái in-doubt. Nó chưa thể tự commit hoặc rollback vì chưa biết global decision.

TM cần ghi log bền vững trước/đúng thời điểm quyết định commit để sau restart có thể khôi phục trạng thái giao dịch và gửi quyết định đến các RM. RM cũng phải giữ trạng thái prepared cho đến khi nhận được quyết định hoặc được xử lý theo recovery protocol.

Do đó, transaction log của TM là thành phần dữ liệu quan trọng. Nếu đặt log ở filesystem tạm hoặc xóa log khi restart, TM có thể mất khả năng xác định giao dịch nào phải commit/rollback.

### 7.2. XA recovery scan

Khi khởi động hoặc chạy recovery, TM gọi `XAResource.recover()` để hỏi RM về các Xid đang ở trạng thái prepared/in-doubt. TM đối chiếu Xid đó với transaction log bền vững và gửi commit/rollback phù hợp.

Việc recovery phụ thuộc:

- Transaction log của TM còn nguyên vẹn và có thể đọc.
- XA resource có cùng định danh/configuration để TM tìm lại đúng RM.
- Oracle Database và network sẵn sàng.
- Recovery credential còn hợp lệ và có đủ quyền.
- Driver/provider hỗ trợ XA recovery đúng cách.

Không đổi tên resource, resource identity hoặc xóa transaction log tùy tiện khi còn giao dịch chưa hoàn tất.

### 7.3. Oracle in-doubt transaction

Oracle cung cấp view để DBA kiểm tra giao dịch phân tán đang chờ quyết định:

```sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       fail_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
```

Có thể xem thông tin các node liên quan:

```sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface
FROM dba_2pc_neighbors
ORDER BY local_tran_id;
```

Các view này hỗ trợ DBA điều tra giao dịch distributed/in-doubt. Không phải mọi giao dịch XA đều xuất hiện theo cùng một hình thức trong mọi tình huống; cần đối chiếu trạng thái TM và RM.

### 7.4. Không tự ý FORCE COMMIT hoặc FORCE ROLLBACK

Oracle có cú pháp `COMMIT FORCE` và `ROLLBACK FORCE` để xử lý một số giao dịch phân tán in-doubt sau khi DBA xác định quyết định đúng. Đây là thao tác quản trị có thể gây mất atomicity nếu quyết định của Oracle không khớp với quyết định TM đã ghi.

Không chạy force commit/rollback chỉ để xóa dòng khỏi `DBA_2PC_PENDING`. Trước hết phải:

1. Xác định global transaction ID và transaction coordinator.
2. Kiểm tra transaction log/recovery log của TM.
3. Xác định TM đã quyết định commit hay rollback.
4. Kiểm tra các RM khác đã hoàn tất branch nào.
5. Phối hợp DBA và chủ hệ thống để xử lý theo hướng dẫn Oracle/TM.

Force resolution chỉ là bước cuối trong quy trình được kiểm soát, không phải phương pháp recovery mặc định.

## 8. Timeout, locking và hiệu năng

### 8.1. Global transaction timeout

TM thường có timeout cho giao dịch toàn cục. Nếu transaction vượt thời gian cho phép, TM có thể đánh dấu rollback-only hoặc yêu cầu rollback theo implementation. Timeout cần phối hợp với:

- Transaction timeout của JTA/TM.
- Query timeout của JDBC.
- Network/socket timeout.
- Timeout của JMS provider.
- Lock wait và thời gian xử lý database.
- Timeout mượn connection từ pool.

Các timeout này có mục đích khác nhau. Pool borrow timeout không phải transaction timeout; query timeout cũng không tự động chứng minh mọi RM đã rollback xong.

### 8.2. Lock và thời gian giữ transaction

Trong 2PC, các RM có thể giữ lock/transaction state cho tới khi nhận quyết định cuối cùng. Nếu một participant chậm hoặc không liên lạc được, thời gian hoàn tất có thể kéo dài và ảnh hưởng transaction khác.

Giữ XA transaction ngắn, tránh thực hiện HTTP call, thao tác file, chờ người dùng hoặc tính toán dài trong transaction. Chỉ enlist resource thực sự cần thiết cho tính atomic.

### 8.3. Chi phí 2PC

So với local transaction, XA thêm round trip prepare/commit, transaction logging, recovery state và coordination overhead. Khi tất cả resource nằm trong cùng một Oracle Database, một local transaction trên một connection thường đơn giản và hiệu quả hơn XA. Chỉ dùng XA khi thực sự cần atomicity giữa các RM độc lập.

Không dùng XA chỉ vì một nghiệp vụ gọi nhiều repository nếu tất cả repository dùng cùng một database và cùng transaction manager local.

## 9. Những giới hạn và lưu ý với Oracle

### 9.1. DDL và implicit commit

Oracle DDL có hành vi implicit commit trước và sau câu lệnh theo quy tắc Oracle. Không đưa DDL như `CREATE TABLE`, `ALTER TABLE` hoặc `DROP TABLE` vào giữa một nghiệp vụ XA với kỳ vọng nó được rollback như DML. Tách migration/schema changes khỏi giao dịch nghiệp vụ.

### 9.2. Sequence không rollback

Giá trị lấy từ Oracle sequence không được trả lại khi transaction rollback. Vì vậy, sequence gap là bình thường và không phải dấu hiệu XA commit không atomic.

### 9.3. External side effects

Gọi HTTP API, gửi email, ghi file hoặc thao tác với hệ thống không hỗ trợ XA không tự được bảo vệ bởi 2PC. Nếu gọi external service trong lúc transaction đang mở, có thể xảy ra side effect đã hoàn tất nhưng database rollback.

Với những hệ thống này, cân nhắc transactional outbox, inbox/idempotency, retry có kiểm soát hoặc Saga thay vì giả định XA bao phủ mọi thứ.

### 9.4. XA không loại bỏ nhu cầu idempotency

Sau timeout hoặc lỗi mạng, client có thể không biết transaction đã commit hay chưa. Việc retry nghiệp vụ có thể tạo dữ liệu trùng nếu API không có idempotency key hoặc cơ chế phát hiện request đã xử lý. XA đảm bảo coordination trong phạm vi RM/TM; nó không tự biến request retry của ứng dụng thành thao tác idempotent.

## 10. Lựa chọn quản lý giao dịch toàn cục

### 10.1. Transaction manager trong application server

Application server như Oracle WebLogic hoặc các Jakarta EE server cung cấp JTA transaction manager tích hợp với datasource, JMS provider, naming, security và recovery service.

Ưu điểm:

- Tích hợp XA datasource/JMS theo cấu hình container.
- Quản lý transaction log, recovery và timeout ở cấp server/domain.
- Có công cụ quản trị transaction và theo dõi in-doubt state.
- Phù hợp với ứng dụng triển khai theo mô hình application server.

Điểm cần cân nhắc:

- Phụ thuộc runtime và cách triển khai của application server.
- Cần vận hành transaction log store bền vững và cấu hình failover đúng.
- Cấu hình datasource/JMS và resource identity phải nhất quán giữa node.

### 10.2. Standalone JTA transaction manager

Ứng dụng Java không chạy trong Jakarta EE application server có thể dùng một JTA implementation độc lập, ví dụ Narayana hoặc Atomikos, kết hợp XA datasource/pool tương thích.

Standalone TM phù hợp với service Spring/Java SE cần global transaction nhưng không muốn phụ thuộc một full application server. Tuy nhiên, đội vận hành phải tự bảo đảm:

- TM được khởi tạo và shutdown đúng lifecycle.
- Transaction log được lưu bền vững trên storage phù hợp.
- Recovery chạy khi restart và có thể truy cập mọi RM.
- Resource identity không thay đổi ngoài kế hoạch.
- Monitoring, alerting và xử lý in-doubt transaction có runbook.
- Phiên bản TM, JDBC driver và application framework tương thích.

Không chỉ thêm một dependency JTA vào build là có XA. Phải cấu hình TM, datasource XA, pool và recovery cùng nhau.

### 10.3. So sánh lựa chọn

| Tiêu chí | Application server TM | Standalone TM |
|---|---|---|
| Nơi quản lý | Trong Jakarta EE/application server | Trong tiến trình Java/service hoặc runtime tích hợp |
| Cấu hình resource | Thường qua admin console/config server/JNDI | Qua framework/TM-specific configuration |
| Recovery log | Do server quản lý, cần storage bền vững | Ứng dụng/đội vận hành cấu hình storage bền vững |
| Tích hợp JMS/Oracle | Theo adapter và cấu hình container | Phụ thuộc XA provider/pool hỗ trợ |
| Phù hợp | Ứng dụng triển khai trên app server | Spring/Java SE hoặc service độc lập |
| Rủi ro vận hành | Cấu hình domain, cluster và log store | Quản lý lifecycle, recovery và resource identity trong ứng dụng |

Không có một lựa chọn đúng cho mọi hệ thống. Hãy chọn theo runtime đang sử dụng, năng lực vận hành, số RM, yêu cầu RTO và khả năng hỗ trợ XA của driver/provider.

## 11. Khi nào không nên dùng XA?

XA không phải lựa chọn mặc định cho mọi distributed workflow. Một số phương án thay thế:

### 11.1. Local transaction

Nếu mọi thay đổi nằm trong một Oracle Database, dùng một local transaction qua một connection. Đây là giải pháp đơn giản, ít overhead và dễ vận hành nhất trong phạm vi một RM.

### 11.2. Transactional outbox

Nếu cần cập nhật Oracle và phát event, có thể ghi dữ liệu nghiệp vụ và một outbox row trong cùng local transaction. Một publisher đọc outbox rồi gửi message; consumer xử lý idempotent.

```text
Local Oracle transaction
      |
      +-- update business tables
      +-- insert OUTBOX event
      |
      v
     COMMIT
      |
      v
Outbox publisher sends message
      |
      v
Consumer processes idempotently
```

Outbox không cung cấp atomic commit đồng thời giữa Oracle và broker; nó bảo đảm event được lưu bền vững cùng dữ liệu và được phát lại cho đến khi xử lý. Thiết kế cần xử lý duplicate delivery, retry và ordering.

### 11.3. Saga

Saga chia nghiệp vụ dài thành các local transaction. Mỗi bước commit độc lập; nếu bước sau thất bại, hệ thống chạy compensating action để bù trừ hiệu ứng trước đó.

Saga phù hợp với workflow kéo dài, microservices và các hệ thống mà resource không hỗ trợ XA. Compensation là nghiệp vụ mới chứ không phải rollback vật lý; cần thiết kế rõ hành vi khi compensation cũng thất bại.

### 11.4. Event-driven eventual consistency

Nếu nghiệp vụ chấp nhận độ trễ nhất quán, event-driven architecture có thể giảm coupling giữa các service. Cần có retry, dead-letter handling, idempotency, observability và quy trình reconciliation.

## 12. Quy trình triển khai và kiểm thử XA

1. Xác định tất cả resource manager cần tham gia và chứng minh yêu cầu atomicity xuyên resource.
2. Kiểm tra Oracle JDBC driver, Oracle Database release, JMS provider và TM có hỗ trợ XA tương thích.
3. Chọn một JTA transaction manager phù hợp runtime; không cấu hình nhiều TM độc lập cho một global transaction.
4. Đăng ký Oracle `XADataSource` và các XA resource khác với TM; cấu hình pool, resource name, credential và recovery.
5. Thiết lập transaction boundary ngắn, timeout phù hợp và quy tắc rollback khi exception.
6. Bảo đảm TM transaction log nằm trên storage bền vững và được backup/giám sát.
7. Kiểm thử commit thành công với tất cả RM.
8. Kiểm thử exception trước prepare, lỗi trong prepare, lỗi giữa các commit và restart TM/RM ở các thời điểm khác nhau.
9. Kiểm tra recovery scan, in-doubt transaction và quy trình DBA xử lý khi coordinator không sẵn sàng.
10. Kiểm thử connection pool, transaction timeout, failover, duplicate request và idempotency.
11. Đo throughput, latency, lock duration, connection usage và transaction log growth khi có tải thực tế.
12. Viết runbook cho restart, recovery, force resolution escalation và phương án rollback cấu hình.

## 13. Checklist lựa chọn XA hay cơ chế khác

| Câu hỏi | Nếu có | Hướng cân nhắc |
|---|---|---|
| Một transaction chỉ cập nhật một Oracle database? | Có | Local JDBC/JTA transaction thường đủ |
| Cần atomic commit giữa Oracle và JMS/XA database? | Có | XA/JTA là ứng viên phù hợp |
| Mọi resource có XA implementation được hỗ trợ? | Không | Xem outbox, saga hoặc eventual consistency |
| Workflow kéo dài qua nhiều service? | Có | Saga/outbox thường phù hợp hơn giữ XA transaction dài |
| Có thể chấp nhận eventual consistency? | Có | Event-driven/outbox giảm coupling |
| Có TM log store và recovery operator? | Không | Chưa sẵn sàng vận hành XA production |
| Ứng dụng cần retry sau timeout? | Có | Thiết kế idempotency và xác định trạng thái transaction |
| Có thể giữ transaction ngắn và ít resource? | Có | XA có thể quản lý được; vẫn phải đo overhead |

## 14. Nguyên tắc cần ghi nhớ

- XA là protocol phối hợp transaction giữa TM và nhiều RM; JTA là API Java để quản lý global transaction.
- Oracle JDBC cần XA-capable datasource; một JDBC connection thông thường không tự trở thành XA resource.
- TM tạo Xid, enlist XAResource, điều phối 2PC và quản lý recovery; business code không tự gọi XAResource protocol.
- 2PC gồm prepare và commit/rollback; TM phải lưu transaction decision bền vững.
- SQL annotation `@Transactional` chỉ dùng XA khi transaction manager thực tế là JTA và các resource được cấu hình/enlist đúng.
- Recovery log của TM và khả năng `XAResource.recover()` là phần bắt buộc của vận hành production.
- Oracle `DBA_2PC_PENDING` giúp điều tra in-doubt transaction; không tự ý FORCE COMMIT/ROLLBACK.
- XA tăng coordination overhead và lock duration; chỉ dùng khi cần atomicity xuyên resource.
- DDL, sequence, HTTP, file và email có semantics riêng; không giả định chúng được rollback bởi XA.
- Outbox, Saga và eventual consistency là lựa chọn phù hợp khi resource không hỗ trợ XA hoặc workflow kéo dài.

## Tài liệu tham khảo

- [Oracle Database 19c JDBC Developer's Guide — Distributed Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/distributed-transactions.html)
- [Oracle Database 19c JDBC Developer's Guide — JDBC and XA](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c Administrator's Guide — Managing Distributed Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-distributed-transactions.html)
- [Oracle Database 19c Reference — DBA_2PC_PENDING](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_2PC_PENDING.html)
- [Oracle Database 19c Reference — DBA_2PC_NEIGHBORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_2PC_NEIGHBORS.html)
- [Jakarta Transactions Specification](https://jakarta.ee/specifications/transactions/)
- [Java SE API — XAResource](https://docs.oracle.com/en/java/javase/21/docs/api/java.transaction.xa/javax/transaction/xa/XAResource.html)
