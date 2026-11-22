# Read-only của phương thức trong khi tham gia giao dịch đọc-ghi

## Câu trả lời trọng tâm

Trong Spring Framework, một phương thức được đánh dấu `@Transactional(readOnly = true)` **không tự chuyển giao dịch đọc–ghi đang tồn tại của caller thành giao dịch chỉ đọc** khi phương thức đó tham gia với `Propagation.REQUIRED` (giá trị mặc định). Transaction manager tiếp tục dùng **physical transaction** đã được outer scope mở, bao gồm read-only flag, isolation và timeout thực tế của transaction đó. Theo cấu hình mặc định của các manager Spring quen thuộc, yêu cầu read-only của inner logical scope **được bỏ qua cho physical transaction chung**.

Ví dụ:

```java
@Service
public class ReportService {

    @Transactional(readOnly = true)
    public Report loadReport() {
        // Đọc bằng repository sử dụng cùng transaction manager.
        return repository.loadReport();
    }
}
```

Đây là **fragment minh họa**, thiếu class `Report`, `repository`, imports và bean wiring. Nếu một service `@Transactional(readOnly = false)` đã mở T1 gọi `loadReport()` qua Spring proxy, method này **tham gia T1** chứ không mở transaction T2 chỉ đọc. Spring không gọi một thao tác “nâng/tắt quyền ghi” để thay đổi read-only flag của T1 giữa chừng.

Đối với imperative JDBC manager chuẩn, khi quan sát trong inner method:

```text
OUTER T1: @Transactional(REQUIRED, readOnly=false)
    |
    +--> INNER @Transactional(REQUIRED, readOnly=true)
            |
            +-- tham gia T1
            +-- physical readOnly của T1 vẫn false
            +-- TransactionStatus.isNewTransaction() của inner = false
            +-- TransactionSynchronizationManager.isCurrentTransactionReadOnly()
                thường trả false
```

**Điểm then chốt:** annotation `readOnly=true` thể hiện **ý định của phương thức**, không phải hàng rào bảo mật chặn mọi SQL `UPDATE`; và khi **join một giao dịch đọc–ghi**, nó không phải chỉ thị đổi trạng thái của toàn bộ transaction vật lý. Ngược lại, nếu method bắt đầu **transaction vật lý mới** (caller không có transaction, hoặc dùng `REQUIRES_NEW`), transaction manager có cơ hội áp dụng read-only hint vào resource mới.

Bài này thuộc nhóm **Read-only và timeout**, trong module **Spring Framework – transaction-management**. Mục tiêu là hiểu đúng trạng thái read-only của phương thức **khi tham gia một transaction đọc–ghi**, không nhầm với hiệu lực khi tạo transaction mới hay với enforcement của database.

---

## 1. Phân biệt ý định của phương thức và đặc tính giao dịch đang chạy

Có ba cấp thông tin khác nhau:

1. **Method-level metadata:** `@Transactional(readOnly = true)` là khai báo trên một phương thức hoặc class Java. Spring đọc nó để tạo `TransactionAttribute`.
2. **Logical transaction scope:** mỗi invocation được transaction advice chặn có thể tạo một scope logic; scope này có propagation và rollback rules riêng.
3. **Physical transaction:** một JDBC transaction, JPA resource transaction hoặc transaction tương ứng do manager quản lý. Đây là đơn vị thực tế được commit/rollback.

Điểm dễ nhầm là **hai logical scopes không nhất thiết là hai physical transactions**.

```text
Caller
   |
   v
OrderService.submit()         outer logical scope
@Transactional(REQUIRED,      readOnly=false
               readOnly=false)
   |
   +-- physical T1 begins --------------------+
   |                                          |
   +--> ReportService.loadReport()            |
        @Transactional(REQUIRED,              |
                       readOnly=true)         |
        inner logical scope joins T1          |
        không thay readOnly của T1            |
   |                                          |
   +-- T1 commit/rollback --------------------+
```

Spring có thể xử lý rollback-only status ở từng scope logic nhưng chỉ có **một** transaction vật lý T1. Khi inner return, T1 vẫn đang thuộc outer và **không commit riêng**.

Điều này quan trọng nếu developer nghĩ đọc dữ liệu bên trong inner sẽ chạy ở một chế độ “tối ưu chỉ đọc” khác hẳn connection chung. Trong tình huống join, những tối ưu được áp dụng **khi transaction bắt đầu** thường đã được quyết định từ lúc outer mở T1.

## 2. `REQUIRED` là điều kiện khiến inner tham gia transaction ngoài

`@Transactional` mặc định tương đương:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false
)
```

Khi đổi `readOnly` thành true:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true
)
public void fetchRecords() {
    // ...
}
```

điều đó **không thay propagation**. `REQUIRED` nghĩa là:

- Nếu **chưa có physical transaction** với manager tương ứng: tạo transaction mới.
- Nếu **đã có physical transaction**: tham gia transaction hiện có.

Do vậy, cùng một method có thể có hai hành vi khác nhau tùy caller:

| Cách gọi | Tình trạng trước method | Physical transaction sau khi vào method | Read-only thực tế |
| --- | --- | --- | --- |
| Gọi trực tiếp qua proxy, caller không có T1 | Không có transaction | Mở T1 mới | Manager cố áp dụng `readOnly=true` |
| Outer `REQUIRED(readOnly=false)` gọi inner `REQUIRED(readOnly=true)` | Có T1 đọc–ghi | Inner join T1 | T1 tiếp tục read-write |
| Outer `REQUIRED(readOnly=true)` gọi inner `REQUIRED(readOnly=true)` | Có T1 chỉ đọc | Inner join T1 | Giữ read-only của T1 |
| Outer `REQUIRED(readOnly=true)` gọi inner `REQUIRED(readOnly=false)` | Có T1 chỉ đọc | Inner join T1 trong lenient mode | Không đổi T1 thành read-write |
| Outer đọc–ghi gọi inner `REQUIRES_NEW(readOnly=true)` | Có T1 đọc–ghi | Suspend T1, mở T2 riêng | Manager có thể áp dụng read-only lên T2 |

Đừng kết luận “readOnly=true lúc nào cũng có tác dụng” từ code annotation đơn lẻ. Cần biết **scope này có bắt đầu physical transaction hay không** và resource có hỗ trợ read-only không.

### 2.1. Khi không có transaction trước đó

Nếu caller không có T1, một method `REQUIRED(readOnly=true)` mở T1 mới với read-only hint. Với JDBC, Spring có thể gọi `Connection.setReadOnly(true)` khi chuẩn bị connection. Với một số ORM integrations, read-only metadata có thể giảm flush/dirty checking. Tuy nhiên, không có bảo đảm universal rằng mọi DB sẽ từ chối `UPDATE`.

### 2.2. Khi đã có transaction đọc–ghi

Nếu outer đã mở T1 với `readOnly=false`, Spring **không tạo connection mới** chỉ vì inner khai báo `readOnly=true`; DAO của inner có thể dùng đúng connection của T1. Read-only metadata của inner không có hiệu lực thay thế physical characteristics đã được outer quyết định. Các thao tác ghi trong T1 vẫn có thể thực hiện bình thường theo quyền của DB.

### 2.3. Cùng một method, kết quả tùy ngữ cảnh gọi

Method `loadReport()` có thể khởi tạo transaction read-only khi được gọi độc lập, nhưng chỉ tham gia transaction đọc–ghi khi được gọi trong workflow ghi. Vì vậy, nếu bạn dùng `@Transactional(readOnly=true)` để biểu đạt API **không có side effect**, hãy kiểm tra cả logic code và quyền truy cập, đừng dựa hoàn toàn vào annotation.

## 3. `readOnly=true` thực chất yêu cầu Spring làm gì?

Tài liệu Spring định nghĩa read-only của `@Transactional` là **một hint gửi tới transaction subsystem**, cho phép tối ưu nếu có thể. Nó không phải một contract bắt buộc **mọi database phải ném exception khi gặp write**.

Các cơ chế cần tách biệt:

| Lớp | Ví dụ cơ chế | Ý nghĩa |
| --- | --- | --- |
| Java annotation | `@Transactional(readOnly = true)` | Khai báo method/scope có ý định chỉ đọc |
| Transaction manager | `TransactionDefinition.isReadOnly()` | Đọc metadata khi quyết định begin/join |
| Spring thread metadata | `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Trạng thái read-only của transaction hiện hành đã được manager expose |
| JDBC connection | `Connection.setReadOnly(true)` | Hint/driver setting khi chuẩn bị connection cho transaction mới |
| Database enforcement tùy chọn | SQL như `SET TRANSACTION READ ONLY` nếu manager/backend phù hợp | Có thể làm DML bị từ chối ở mức DB trong transaction thực sự chỉ đọc |
| ORM integration | Flush mode/session read-only optimization tùy provider | Có thể tối ưu việc quản lý entity; không đồng nghĩa policy DB giống JDBC |

Khi inner **join T1 đọc–ghi**, không nên mặc định rằng nó được cấp một read-only connection hoặc session riêng. Một resource vẫn thuộc T1 và giữ đặc tính của T1.

`readOnly=true` hữu ích cho performance/ý định API, nhưng **không phải cơ chế authorization**. Muốn ngăn ghi dữ liệu nhạy cảm, hãy dùng quyền DB, phân quyền ứng dụng, schema constraints và kiểm thử.

### 3.1. Read-only không tự động làm dữ liệu bất biến

Java object được đọc từ repository vẫn có thể bị sửa trong bộ nhớ. Đối với JPA, một thay đổi của managed entity có được flush xuống DB hay không phụ thuộc persistence context và flush mode thực tế. Nếu đang tham gia một **outer read-write transaction** với flush bình thường, không nên suy ra entity đổi trong inner sẽ không được ghi chỉ vì inner method khai báo read-only.

Điều này đặc biệt nguy hiểm khi một repository trả **managed entities** rồi code gọi setter; ORM dirty checking có thể flush ở cuối **outer** transaction. Annotation readOnly của inner không tạo một “vùng Java chỉ đọc” có runtime enforcement mặc định.

## 4. Cơ chế của `PlatformTransactionManager` khi join

Với transaction manager thuộc họ `AbstractPlatformTransactionManager`, luồng logic có thể hình dung như sau:

```text
Caller -> TransactionInterceptor
          |
          +-- đọc TransactionAttribute của method:
          |       propagation=REQUIRED
          |       readOnly=true
          |
          +-- manager.getTransaction(definition)
                  |
                  +-- phát hiện physical T1 đã tồn tại
                  +-- REQUIRED => participate
                  +-- không gọi begin cho transaction T2
                  +-- không chuẩn bị lại connection như new tx
                  +-- trả TransactionStatus của logical scope inner
          |
          +-- thực thi method nội bộ
          +-- kết thúc logical scope
                  |
                  +-- nếu bình thường: chưa commit T1 riêng
                  +-- nếu exception khớp rule: có thể đánh dấu rollback-only
```

Khi mới bắt đầu physical transaction, manager chuẩn bị tài nguyên và có thể expose các đặc tính transaction cho Spring synchronization. Khi **tham gia**, theo mặc định manager leniently dùng đặc tính outer; không tự gọi cơ chế chuẩn bị lại read-only cho connection.

**Không phải mọi transaction manager có implementation giống từng dòng trên.** Các đặc tính có hiệu lực phụ thuộc JDBC, JPA, JTA, reactive manager và backend cụ thể. Nhưng quy tắc tham gia transaction ngoài thay vì áp dụng lại physical read-only là semantics mà tài liệu Spring mô tả cho `PROPAGATION_REQUIRED`.

### 4.1. Transaction status của inner

`TransactionAspectSupport.currentTransactionStatus()` trả về status của invocation được advice chặn. Inner join T1 thường có:

```text
isNewTransaction() = false
hasTransaction()   = true
```

Tùy cấu hình Spring version, `TransactionStatus.hasTransaction()` có sẵn trong Spring 6.1+; ví dụ Java dùng Spring 6.2. Nó cho biết scope có gắn actual transaction, còn `isNewTransaction()` phân biệt transaction mới thuộc scope với participation.

`isNewTransaction() = false` **không** có nghĩa đang chạy ngoài transaction: nó cũng là kết quả thông thường của inner `REQUIRED` tham gia T1.

### 4.2. `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`

Trong imperative Spring, có thể dùng:

```java
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

Đây là **fragment chẩn đoán**, cần import. Với inner `REQUIRED(readOnly=true)` tham gia một T1 được outer bắt đầu `readOnly=false`, giá trị thường là **`false`**, vì Spring expose read-only metadata của **physical transaction outer**.

Đừng nhầm giữa **annotation source** của inner (đúng là `readOnly=true`) với **metadata hiện hành ở thread** (đang là `false` khi tham gia T1). Cả hai có thể cùng đúng.

Phép đo trên không tự chứng minh database có hay không có quyền ghi, và không nên được lạm dụng trong domain logic: `TransactionSynchronizationManager` chủ yếu phục vụ transaction/resource infrastructure và chẩn đoán.

## 5. Vì sao read-only không được “bật tạm” ở giữa transaction?

Có ba lý do:

1. **Cùng một physical resource.** Inner `REQUIRED` không mở T2; JDBC connection/JPA persistence context đang phục vụ T1, với đặc tính đã khởi tạo từ outer.
2. **Read-only là đặc tính của transaction/resource, không phải một modifier độc lập quanh mỗi Java method.** Thay nó ở giữa T1 có thể dẫn tới behavior mâu thuẫn giữa các SQL đã chạy và chưa chạy.
3. **Một transaction có thể gồm đọc và ghi đan xen.** Outer cần read-write để hoàn thành nghiệp vụ; nếu inner chuyển T1 thành read-only rồi không khôi phục đúng, những thao tác ghi sau đó sẽ bị ảnh hưởng bất ngờ.

Vì thế Spring mặc định **giữ transaction characteristics của outer**. Đây là một lựa chọn thiết kế về transaction semantics, không phải bug của `@Transactional`.

### 5.1. Sơ đồ trước–sau

```text
T1 do outer tạo: readOnly=false
        |
        +-- UPDATE order
        +-- gọi inner readOnly=true
        |       +-- SELECT customer
        |       +-- có thể chạy UPDATE do T1 vẫn read-write
        +-- UPDATE inventory
        |
        +-- COMMIT T1
```

Các thay đổi SQL được rollback/commit theo **T1 chung**. Nếu inner làm một lệnh ghi, annotation `readOnly=true` ở inner **không tự tạo điểm chặn write** trong T1. Dùng validation nghiệp vụ, API và DB permissions để kiểm soát phạm vi được phép ghi.

## 6. `validateExistingTransaction(true)` có từ chối trường hợp này không?

Thông thường **không, chỉ vì inner xin read-only**.

Một transaction manager thuộc họ `AbstractPlatformTransactionManager` cho phép:

```java
JdbcTransactionManager manager =
        new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

Đây là **fragment**, cần `dataSource` và imports. Flag này làm manager **kiểm tra participation** nghiêm ngặt hơn thay vì leniently bỏ qua các khai báo isolation/read-only không tương thích.

Tuy nhiên, cần hiểu **chiều mismatch** được Spring mô tả rõ:

- **Outer T1 read-only**, inner yêu cầu **read-write** (`readOnly=false`): strict validation có thể **từ chối** vì inner định làm việc có ghi trong transaction ngoài chỉ đọc.
- **Outer T1 read-write**, inner yêu cầu **read-only** (`readOnly=true`): đó **không** phải tình huống bắt buộc bị từ chối theo read-only validation của manager thông thường. Inner thường tham gia T1 và physical transaction **vẫn read-write**.

Không thể dùng `validateExistingTransaction=true` như cơ chế cưỡng bức tạo một vùng “chỉ đọc” bên trong T1 đọc–ghi. Nó cũng không biến inner `readOnly=true` thành T2 read-only.

### 6.1. Bảng kiểm tra hai chiều

| Outer T1 | Inner `REQUIRED` | Mặc định lenient | Bật strict validation |
| --- | --- | --- | --- |
| Read-write | `readOnly=true` | Join T1, giữ read-write | Thông thường vẫn join; read-only của inner không enforce |
| Read-only | `readOnly=false` | Có thể join T1, giữ read-only | Có thể bị từ chối do read-write inner tham gia read-only outer |
| Read-only | `readOnly=true` | Join T1, read-only | Join nếu không có mismatch khác |
| Read-write | `readOnly=false` | Join T1, read-write | Join nếu không có mismatch khác |
| Bất kỳ | Isolation inner khác outer | Join T1, dùng isolation outer | Có thể bị từ chối do isolation mismatch |

Nếu inner còn khai báo `isolation` riêng không tương thích, strict validation có thể từ chối **vì isolation**, dù hướng read-only hợp lệ. Bảng này giả định cùng manager, actual transaction đang có và các đặc tính khác không gây lỗi.

### 6.2. Không tự ý tắt strict validation để “chữa lỗi”

Nếu ứng dụng có strict validation và inner read-write cố join outer read-only, vấn đề thường nằm ở transaction boundary không đúng hoặc method contract mâu thuẫn. Cần xác định nơi bắt đầu T1 và business semantics trước khi sửa. Tắt validation chỉ làm mismatch bị bỏ qua; nó không tự bảo đảm dữ liệu đúng.

## 7. JDBC: một connection đọc–ghi vẫn có thể ghi trong inner `readOnly=true`

Trong Spring JDBC, `JdbcTransactionManager` hoặc `DataSourceTransactionManager` quản lý local transaction qua `DataSource`. `JdbcTemplate` dùng `DataSourceUtils` để lấy connection phù hợp với transaction đang bind trên thread.

Khi outer đọc–ghi mở T1:

```text
JdbcTransactionManager -> lấy connection C1
                         -> autoCommit=false cho T1
                         -> readOnly flag của T1=false
                         -> bind C1 vào thread
                               |
                               +--> outer JdbcTemplate UPDATE
                               +--> inner JdbcTemplate SELECT
                               +--> inner JdbcTemplate UPDATE
                               +--> outer JdbcTemplate UPDATE
                         -> commit/rollback C1
```

Inner `@Transactional(readOnly=true)` tham gia T1 thì **không tự gọi `Connection.setReadOnly(true)` trên C1**. Do đó, nếu schema/DB permissions cho phép, UPDATE ở inner có thể thành công và được commit cùng outer.

### 7.1. Read-only JDBC chỉ là hint theo hợp đồng chung

Khi **transaction mới** được khai báo read-only, Spring thường truyền hint tới `Connection.setReadOnly(true)`. JDBC driver có thể diễn giải khác nhau; một số backend không enforce cứng. Tài liệu Spring mô tả `readOnly=true` là hint, **không bảo đảm mọi write access phải fail**.

`DataSourceTransactionManager` có tùy chọn `setEnforceReadOnly(true)` cho những backend hỗ trợ cách thiết lập mạnh bằng SQL như `SET TRANSACTION READ ONLY`. Nó được thực hiện **khi chuẩn bị một transaction mới** có read-only, không phải mẹo ép inner `REQUIRED(readOnly=true)` đổi trạng thái của T1 đọc–ghi đang có.

### 7.2. Chú ý `DataSource` phải đồng nhất

Nếu manager quản lý `DataSource A` nhưng repository hoặc `JdbcTemplate` dùng `DataSource B`, code có thể mở một transaction T1 hợp lệ mà SQL của repository **không tham gia T1**. Kết quả thực tế có thể bị auto-commit hoặc điều phối bởi manager khác. Kiểm tra **manager, datasource identity và cách lấy connection** trước khi quy kết annotation readOnly hoạt động sai.

### 7.3. Connection pool và restoration

Manager JDBC thường chịu trách nhiệm khôi phục trạng thái connection cần thiết khi transaction kết thúc. Không tự gọi `setReadOnly(true/false)` trên connection đang được Spring quản lý để điều khiển từng method nội bộ nếu không hiểu pool và lifecycle: có thể làm outer query/write sai hoặc rò rỉ trạng thái về lần mượn connection tiếp theo.

## 8. JPA/Hibernate: read-only inner không bảo đảm tắt dirty checking

Trong ứng dụng JPA/Hibernate, `@Transactional(readOnly=true)` trên một **transaction mới** có thể giúp provider giảm overhead thông qua flush/session optimizations; độ chính xác tùy Spring/JPA provider và version.

Nhưng khi một inner service tham gia một **outer read-write transaction**:

- Inner thường chia sẻ transaction/persistence context đang phục vụ T1.
- Method-level readOnly của inner **không tự chuyển toàn bộ EntityManager/Session của T1 thành read-only**.
- Nếu outer dùng automatic flush/dirty checking, thay đổi của managed entity được thực hiện trong inner **có thể được flush tại cuối outer transaction**.
- Một `repository.save(...)` hay entity setter trong inner không tự bị chặn bởi annotation readOnly nếu physical transaction và backend đang read-write.

Ví dụ minh họa:

```java
@Service
public class CustomerViewService {
    private final CustomerRepository customers;

    public CustomerViewService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Customer loadAndRename(long id) {
        Customer customer = customers.findById(id).orElseThrow();
        customer.setName("Updated within outer transaction");
        return customer;
    }
}
```

Đây là **fragment**, thiếu entity `Customer`, repository và imports. Nếu caller đã mở T1 read-write, một `Customer` managed entity được đổi tên trong inner có thể được Hibernate flush khi outer commit. Không nên coi annotation readOnly của inner là contract “setter sẽ không được lưu”.

### 8.1. Read-only ở ORM và read-only ở DB khác nhau

Một Hibernate session có thể dùng flush mode để giảm số lần flush; read-only entities có thể tránh một số dirty checking. Database có thể dùng quyền hoặc read-only transaction mode. Hai lớp này có thể cùng tồn tại nhưng không đồng nhất.

Nếu đúng yêu cầu là **bảo đảm không thay đổi dữ liệu**, hãy tách read model/DTO, không trả entity mutable khi không cần, dùng quyền DB hoặc persistence-unit read-only dành riêng, và kiểm thử kết quả sau commit.

### 8.2. Dùng `@Transactional(readOnly=true)` ở tầng repository có còn lợi ích không?

Có thể có lợi khi repository method được gọi **độc lập**, vì nó có cơ hội mở transaction read-only hoặc nhận hint phù hợp. Khi repository được gọi trong outer read-write transaction, readOnly của repository method không tự đổi physical transaction. Điều này là bình thường trong Spring Data JPA: transaction boundary của use case ở service thường quan trọng hơn annotation mặc định của từng repository method.

## 9. Ví dụ Java 17 chạy độc lập: inner read-only join outer read-write

### 9.1. Mục tiêu thí nghiệm

Demo này dùng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19** và **H2 in-memory 2.3.232**. Có hai Spring beans:

- `OuterService` có `@Transactional(propagation=REQUIRED, readOnly=false)` để mở physical transaction T1 đọc–ghi.
- `InnerService` có `@Transactional(propagation=REQUIRED, readOnly=true)` để minh họa khi **gọi độc lập** và khi **join T1**.

Chương trình gồm ba phần:

1. Gọi inner trực tiếp từ caller không có T1: inner **mở transaction mới read-only**; chỉ xem metadata, không viết DB.
2. Outer mở T1 read-write rồi gọi inner `readOnly=true`, yêu cầu inner làm một `UPDATE`: thao tác có thể commit cùng T1, minh họa annotation không khóa quyền ghi khi join.
3. Outer mở T1 read-write, inner `UPDATE` xong nhưng outer ném unchecked exception: T1 rollback, cho thấy một physical transaction chung kiểm soát kết cục.

Đây là demo JDBC/H2, **không** dùng nó để suy ra mọi database cho phép ghi trong một transaction **thực sự** được tạo read-only. Chúng ta chủ động chỉ ghi trong nhánh T1 read-write.

### 9.2. Cấu trúc Maven

```text
readonly-join-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ReadOnlyJoinDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>readonly-join-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp IoC và Java transaction configuration; `spring-jdbc` kéo theo transaction infrastructure, `JdbcTemplate` và JDBC manager. H2 là database in-memory sử dụng lúc chạy. `DriverManagerDataSource` của demo không có connection pool; production nên dùng pool và cấu hình bảo mật phù hợp.

### 9.3. Toàn bộ source Java

File `src/main/java/demo/ReadOnlyJoinDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Configuration
@EnableTransactionManagement
public class ReadOnlyJoinDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:readonly_join;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    InnerService innerService(JdbcTemplate jdbc) {
        return new InnerService(jdbc);
    }

    @Bean
    OuterService outerService(InnerService inner) {
        return new OuterService(inner);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ReadOnlyJoinDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE account (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO account (id, balance) VALUES (?, ?)",
                    1, 100);

            InnerService inner = context.getBean(InnerService.class);
            OuterService outer = context.getBean(OuterService.class);

            inner.check("STANDALONE", false);

            outer.commitCase();
            System.out.println("AFTER_COMMIT=" + balance(jdbc));

            try {
                outer.rollbackCase();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_ROLLBACK=" + balance(jdbc));
        }
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1",
                Integer.class);
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = true
        )
        public void check(String label, boolean write) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println(label
                    + ": new=" + status.isNewTransaction()
                    + ", actual="
                    + TransactionSynchronizationManager
                        .isActualTransactionActive()
                    + ", readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());

            if (write) {
                jdbc.update("""
                        UPDATE account
                           SET balance = balance + 10
                         WHERE id = 1
                        """);
            }
        }
    }

    public static class OuterService {
        private final InnerService inner;

        public OuterService(InnerService inner) {
            this.inner = inner;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = false
        )
        public void commitCase() {
            System.out.println("OUTER_COMMIT: readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());
            inner.check("INNER_COMMIT", true);
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = false
        )
        public void rollbackCase() {
            System.out.println("OUTER_ROLLBACK: readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());
            inner.check("INNER_ROLLBACK", true);
            throw new IllegalStateException("rollback outer");
        }
    }
}
```

Tại sao mẫu này dùng **hai Spring-managed service beans** thay vì `this.innerMethod()`? Trong proxy mode mặc định, self-invocation không đi qua transaction proxy. Vì `OuterService` được inject `InnerService` từ container và gọi public method qua proxy, Spring thực sự thấy annotation của inner và tạo logical scope `REQUIRED` tham gia T1.

`@EnableTransactionManagement` bật transaction annotation infrastructure. `JdbcTransactionManager` được cung cấp cho cùng `DataSource` với `JdbcTemplate`; câu lệnh cập nhật tham gia resource transaction nếu được gọi trong scope.

### 9.4. Chạy chương trình và đọc output

Từ thư mục `readonly-join-demo`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReadOnlyJoinDemo
```

Các dòng **do chương trình tự in** trong môi trường demo mặc định (không tính thông báo/log Maven, Spring hoặc H2):

```text
STANDALONE: new=true, actual=true, readOnly=true
OUTER_COMMIT: readOnly=false
INNER_COMMIT: new=false, actual=true, readOnly=false
AFTER_COMMIT=110
OUTER_ROLLBACK: readOnly=false
INNER_ROLLBACK: new=false, actual=true, readOnly=false
CAUGHT=rollback outer
AFTER_ROLLBACK=110
```

Diễn giải theo từng nhánh:

1. **STANDALONE:** ngoài transaction, `inner.check(..., false)` được advice chặn, bắt đầu T1 read-only mới. Metadata read-only là `true` vì manager khởi tạo transaction mới theo definition.
2. **OUTER_COMMIT:** caller bắt đầu T2 read-write. Inner `REQUIRED(readOnly=true)` tham gia T2, vì vậy `new=false`, `readOnly=false`. Câu `UPDATE balance += 10` thực hiện trong T2 và commit khi outer return bình thường; số dư tăng từ 100 lên 110.
3. **OUTER_ROLLBACK:** một transaction read-write mới T3 bắt đầu. Inner tham gia T3 và thực hiện `UPDATE`; sau đó outer ném `IllegalStateException`, khiến T3 rollback theo quy tắc mặc định. Số dư sau boundary vẫn là 110, không phải 120.

Chương trình cố tình **không ghi dữ liệu trong transaction STANDALONE read-only**. Nhờ vậy nó kiểm tra đúng câu hỏi trọng tâm: “inner readOnly=true có bị ép vào chế độ read-only khi join outer read-write không?”, chứ không phụ thuộc H2 có cho phép ghi trong một transaction mới được đánh dấu read-only hay không.

### 9.5. Các assertion tương ứng

Một integration test có thể kiểm tra:

```text
Standalone inner: isNewTransaction = true,
                  currentTransactionReadOnly = true

Inside outer read-write: inner.isNewTransaction = false,
                         currentTransactionReadOnly = false

Commit scenario:  final balance = 110
Rollback scenario: final balance remains 110
```

Các assertion trên có ý nghĩa khi test đi qua Spring proxy và sử dụng cùng datasource/manager. Nếu test method được Spring Test tự gắn `@Transactional`, nhánh bạn nghĩ “standalone” có thể thực ra join **test transaction**, làm sai kết quả. Hãy tránh test-level transaction khi kiểm tra nhánh tự mở transaction.

## 10. Biến thể: dùng `REQUIRES_NEW` để thực sự bắt đầu transaction đọc-only

Nếu một operation cần **độc lập với outer read-write transaction** và bản thân nó chỉ đọc, có thể dùng:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    readOnly = true
)
public Report loadIndependentReport() {
    return repository.queryReport();
}
```

Đây là **fragment**, thiếu class/repository/imports. Khi caller đang có T1 read-write:

```text
Outer transaction T1 (read-write)  begin ---- suspended ---- resumed ---- commit
Inner transaction T2 (read-only)             begin--read--commit
```

T2 có một physical transaction riêng, nên manager có thể áp dụng read-only hint lên T2. Tuy nhiên:

- T2 thường dùng connection riêng; nếu pool quá nhỏ, nhiều outer transactions đồng thời chờ inner connection có thể gây cạn pool.
- T2 không nhìn thấy dữ liệu chưa commit của T1 trong cách xử lý thông thường của DB isolation; đừng dùng T2 để giả định đọc được mọi thay đổi outer vừa ghi.
- T2 có thể commit/rollback độc lập. Khi outer rollback, kết quả commit của T2 không tự bị hủy.
- `readOnly=true` vẫn không phải quyền DB tuyệt đối; tùy resource backend.
- Với use case chỉ cần đọc trong cùng snapshot của outer, `REQUIRES_NEW` có thể **làm sai kỳ vọng nhất quán** hoặc tốn tài nguyên. Chỉ dùng khi có lý do nghiệp vụ rõ.

**Không cần REQUIRES_NEW chỉ để “tối ưu” một truy vấn** đang nằm trong outer transaction read-write; lợi ích có thể không đáng so với chi phí và sự thay đổi semantics.

## 11. `NESTED`, `SUPPORTS` và các propagation khác

Câu hỏi chính tập trung vào inner `REQUIRED` join outer read-write, nhưng các propagation liên quan giúp tránh suy diễn sai:

| Propagation của inner | Khi caller đã có T1 read-write | Read-only của inner |
| --- | --- | --- |
| `REQUIRED` | Join T1 | Không đổi physical read-only của T1 |
| `SUPPORTS` | Join T1 | Không đổi physical read-only của T1 |
| `MANDATORY` | Join T1, nếu thiếu T1 thì lỗi | Không đổi physical read-only của T1 |
| `REQUIRES_NEW` | Suspend T1, mở T2 độc lập | Có thể áp dụng read-only lên T2 mới |
| `NESTED` | Thường tạo savepoint trong cùng T1 khi manager hỗ trợ | Không có physical T2 mới để đổi read-only |
| `NOT_SUPPORTED` | Suspend T1, chạy không có physical transaction | Không có physical read-only transaction mới do inner mở |
| `NEVER` | Nếu T1 có sẵn thì từ chối | Không đến bước mở một transaction read-only |

`NESTED` không tương đương `REQUIRES_NEW`: savepoint vẫn nằm trong **cùng physical T1**. Không giả định một nested method `readOnly=true` có JDBC connection riêng.

Nếu inner `SUPPORTS(readOnly=true)` được gọi **ngoài** transaction, nó không bắt đầu physical transaction. Spring có thể kích hoạt transaction synchronization và truyền read-only metadata cho resource management trong một số cấu hình, nhưng đó không phải bằng chứng rằng DB có một transaction read-only mới.

## 12. Rollback rules vẫn có tác dụng khi join

Một inner method `@Transactional(readOnly=true)` tham gia outer read-write vẫn có thể làm **toàn bộ T1 rollback**, nếu exception thoát khỏi transactional advice và khớp rollback rule.

Mặc định:

- `RuntimeException` và `Error` làm rollback.
- Checked `Exception` thường không làm rollback nếu không thêm rule.
- Spring 6.2 có cấu hình global để thay default, ví dụ `@EnableTransactionManagement(rollbackOn=ALL_EXCEPTIONS)`; hãy kiểm tra cấu hình thực tế.

Ví dụ:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true,
    rollbackFor = java.io.IOException.class
)
public void loadAndValidate() throws java.io.IOException {
    // Nếu IOException thoát khỏi advice, rollback rule được xét
}
```

Đây là **fragment minh họa**. Nếu method tham gia T1 đọc–ghi và IOException khớp rule, transaction manager có thể đánh dấu T1 **rollback-only**. Outer bắt exception rồi return bình thường vẫn có thể gặp `UnexpectedRollbackException` khi cố commit.

Đây là lý do không được kết luận “mọi thuộc tính inner đều bị bỏ qua khi join”. Read-only/isolation/timeout thuộc **physical characteristics**, thường của outer; rollback rules thuộc **logical scope completion** và vẫn có thể ảnh hưởng T1.

### 12.1. Exception bị catch bên trong

Nếu inner tự catch lỗi rồi return bình thường, transaction advice có thể không thấy exception. Khi cần buộc rollback, có thể dùng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` trong invocation hợp lệ. Lưu ý cờ này làm transaction chung không thể commit như ban đầu; cần thông báo kết quả nghiệp vụ đúng cho caller.

### 12.2. Không biến read-only flag thành một rollback rule

`readOnly=true` không đồng nghĩa “nếu có SQL UPDATE thì tự rollback”. Đó không phải rollback condition. Cần cơ chế DB/provider, rule exception và validation nghiệp vụ nếu hệ thống bắt buộc chặn ghi.

## 13. Thiết kế service boundary để tránh hiểu nhầm

Một pattern thông dụng:

```text
Controller / Handler
       |
       v
OrderApplicationService.checkout()   @Transactional(readOnly=false)
       |
       +--> PricingService.lookup()   @Transactional(readOnly=true)
       |                               joins outer T1
       |
       +--> InventoryService.reserve() (tham gia T1)
       |
       +--> OrderRepository.save()    (tham gia T1)
       |
       v
COMMIT T1
```

Pricing service có thể được gọi độc lập, khi đó read-only hint của nó được áp dụng cho transaction mới. Trong checkout, nó tham gia T1 read-write. Điều này có thể là **thiết kế đúng**, vì toàn use case cần một transaction nhất quán; read-only annotation trên pricing chỉ thể hiện use-case expectation khi chạy độc lập.

### 13.1. Nếu muốn bảo đảm một helper không sửa dữ liệu

Đừng chỉ dựa vào annotation inner readOnly. Các lựa chọn mạnh hơn:

- Chỉ expose phương thức đọc (`get...`, `find...`) bằng API contract, tránh dùng repository write methods trong helper.
- Trả về immutable DTO hoặc projection, không trả managed entity mutable cho logic chỉ đọc.
- Sử dụng quyền database read-only theo user/role hoặc datasource riêng khi business yêu cầu enforcement.
- Đặt rule static analysis/lint và integration tests để phát hiện write trong read helper.
- Tách transaction/scope đọc thực sự riêng khi cần, nhưng hiểu rõ `REQUIRES_NEW` có semantics và chi phí khác.
- Theo dõi SQL phát sinh ở môi trường test; xác nhận không có `UPDATE`/`INSERT` bất ngờ trong read workflow.

### 13.2. Nếu method là một bước của workflow có ghi

Đặt outer transaction boundary ở **application service**, nơi yêu cầu atomicity của toàn operation được xác định. Inner read helper có thể khai readOnly để dùng độc lập; không nên kỳ vọng hint đó sửa physical transaction đang xử lý cả read và write.

### 13.3. Không gọi method annotated bằng `this.method()`

Trong Spring proxy mode, lời gọi self-invocation bỏ qua proxy; annotation của inner method không được đọc cho một invocation advice mới. Nếu muốn thực sự test semantics join, dùng hai Spring beans hoặc gọi qua proxy hợp lệ.

Với AspectJ weaving, self-invocation có thể được intercept nếu cấu hình weaving thật; chỉ bật một flag mà không weave class không đủ. Ví dụ runnable đã tránh vấn đề bằng cách dùng `InnerService` và `OuterService` tách biệt.

## 14. Lỗi thường gặp và chẩn đoán

| Triệu chứng / kỳ vọng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Inner `readOnly=true` nhưng `isCurrentTransactionReadOnly()` báo `false` | Inner đang join outer read-write T1 | Xem `isNewTransaction()` của inner và annotation của outer |
| Inner `readOnly=true` vẫn ghi SQL thành công | Physical T1 là read-write; hint inner không đổi T1 | Xác nhận datasource/manager và đọc DB sau commit |
| Đặt `validateExistingTransaction=true` nhưng inner read-only vẫn join | Read-only validation không bắt buộc từ chối chiều outer RW → inner RO | Hiểu đúng chiều mismatch; đừng xem đó là lỗi |
| Inner read-write bị từ chối khi outer read-only | Strict validation chặn mismatch | Điều chỉnh transaction boundary hoặc propagation phù hợp |
| Inner gọi độc lập báo readOnly=true nhưng khi gọi trong service báo false | Một đường mở T1 mới, đường còn lại join T1 cũ | Kiểm tra caller và propagation |
| JPA entity bị thay đổi dù method readOnly | Inner join shared read-write persistence context | Xem ORM dirty checking/flush ở outer commit |
| Read-only JDBC transaction mới vẫn cho UPDATE | Backend/driver chỉ xem read-only như hint | Kiểm tra DB enforcement và config `setEnforceReadOnly` khi phù hợp |
| Chỉ thấy `readOnly=false` trong test | Test framework đã mở transaction read-write bên ngoài | Tránh test-level transaction khi kiểm tra nhánh standalone |
| Annotation inner không có tác dụng | Self-invocation hoặc bean tạo bằng `new` | Gọi qua Spring-managed proxy |
| Ghi dữ liệu không rollback dù outer có transaction | DAO dùng datasource khác hoặc connection không bind vào T1 | Kiểm tra datasource của `JdbcTemplate` và transaction manager |
| `UnexpectedRollbackException` khi outer commit | Inner scope đã đánh dấu T1 rollback-only | Kiểm tra exception path và rollback rules |
| Đổi inner sang `REQUIRES_NEW` rồi không đọc được dữ liệu outer vừa ghi | T2 là transaction độc lập, không thấy uncommitted T1 | Rà soát yêu cầu nhất quán và có cần T2 hay không |

### 14.1. Cần log gì?

Ở môi trường development hoặc integration test, bật log Spring transaction để quan sát begin, join và commit/rollback; log JDBC hoặc SQL nếu cần phân tích thao tác ghi. Không bật SQL parameter/log nhạy cảm bừa bãi ở production.

Ví dụ property cho ứng dụng có logging backend tương ứng:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Đây là **fragment logging config** thường gặp trong Spring Boot; không bắt buộc cho demo `AnnotationConfigApplicationContext` ở phần 9.

### 14.2. Đọc status đúng phạm vi

Trong invocation có transaction advice:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
System.out.println(status.isNewTransaction());
System.out.println(
        TransactionSynchronizationManager.isCurrentTransactionReadOnly());
```

Đây là snippet minh họa. Nếu chạy ngoài advice, `currentTransactionStatus()` có thể ném `NoTransactionException`; nếu có nhiều managers/threads, trạng thái được giải thích theo execution context tương ứng.

Đừng thay xác minh behavior DB bằng một boolean: cần đọc hậu điều kiện **sau transaction boundary** để chứng minh kết quả commit/rollback.

## 15. Kiểm thử đúng cả hai đường gọi

Một bộ integration tests tối thiểu nên có:

1. **Standalone read-only:** gọi inner qua proxy từ caller không có transaction; xác nhận `isNewTransaction()==true` và Spring metadata readOnly=true (với manager hỗ trợ).
2. **Join outer read-write:** outer bắt đầu T1 read-write; inner `REQUIRED(readOnly=true)` qua proxy thấy `isNewTransaction()==false`, readOnly metadata=false.
3. **Commit:** trong T1 read-write, thực hiện một update từ inner; xác nhận thay đổi được commit khi outer return.
4. **Rollback:** outer ném unchecked exception sau inner update; xác nhận toàn bộ T1 rollback.
5. **Strict validation cùng chiều:** bật `setValidateExistingTransaction(true)` và kiểm tra inner read-only vẫn có thể join outer read-write khi không có mismatch khác.
6. **Strict validation chiều ngược:** outer read-only, inner read-write; kiểm tra manager từ chối participation theo semantics.
7. **REQUIRES_NEW:** inner read-only có transaction vật lý mới, metadata riêng; kiểm tra resource independence và connection pool.
8. **ORM behavior:** trong JPA/Hibernate thực, chỉnh managed entity trong inner join và kiểm tra flush behavior tại outer commit.
9. **Proxy interception:** tránh self-invocation và xác nhận method thực sự qua Spring proxy.
10. **Resource ownership:** đúng transaction manager/datasource; một datasource khác có thể không tham gia rollback của T1.

### 15.1. Spring Test có thể vô tình tạo outer transaction

Một JUnit test method gắn `@Transactional` có thể được Spring Test framework tự bao quanh bởi T1. Nếu bạn gọi inner `readOnly=true` từ đó, bạn đang test **nhánh join** chứ không phải **nhánh tự tạo transaction mới**. Khi cần kiểm tra cả hai, tách cấu hình test hoặc gọi từ ngữ cảnh không có transaction, rồi xác minh kết quả sau commit.

### 15.2. Đừng khẳng định connection-level enforcement chỉ từ H2

Ví dụ H2 có giá trị vì kết quả và transaction metadata xác định, không vì nó đại diện cho mọi database. Với PostgreSQL, MySQL, Oracle và SQL Server, read-only JDBC/SQL transaction enforcement có thể khác nhau. Hãy bổ sung integration tests trên đúng database/driver nếu ứng dụng dựa vào read-only enforcement.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Outer `@Transactional(readOnly=false)` mở T1. Inner `@Transactional(readOnly=true)` mặc định propagation là gì?

**Đáp án:** `REQUIRED`. Khi outer đã có T1 cùng manager, inner tham gia T1; nó không mở transaction read-only riêng.

**Câu 2.** `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` trả gì trong inner đang join T1 read-write?

**Đáp án:** Theo imperative manager chuẩn, thường là `false` vì flag hiện hành phản ánh transaction ngoài T1, không phải metadata riêng của annotation inner.

**Câu 3.** Inner có thể chạy `UPDATE` thành công dù annotation là readOnly=true không?

**Đáp án:** Có thể. Vì physical T1 vẫn read-write, annotation inner không mặc định chặn ghi. Hãy kiểm tra DB permissions và resource behavior thực tế.

**Câu 4.** `validateExistingTransaction=true` có nhất thiết ném lỗi với outer read-write, inner read-only?

**Đáp án:** Không. Strict read-only validation chủ yếu từ chối trường hợp **outer read-only, inner read-write**; chiều ngược lại thông thường được join.

**Câu 5.** Nếu inner được gọi độc lập khi chưa có T1, readOnly=true có ý nghĩa gì?

**Đáp án:** Method `REQUIRED` mở T1 mới, manager có thể truyền read-only hint cho JDBC/ORM resource khi bắt đầu transaction. Không bảo đảm mọi DB tự chặn DML.

**Câu 6.** Có nên dùng `REQUIRES_NEW(readOnly=true)` để luôn tách inner khỏi outer?

**Đáp án:** Chỉ khi nghiệp vụ thật sự cần transaction độc lập. T2 có snapshot/resource riêng, có thể không thấy dữ liệu uncommitted của T1 và tiêu tốn thêm JDBC connection.

**Câu 7.** Outer ghi entity, inner read-only sửa managed entity, outer commit. Có chắc thay đổi inner không được flush không?

**Đáp án:** Không. Inner join shared read-write persistence context; flush/dirty checking vẫn có thể ghi entity. Annotation readOnly của inner không phải bảo đảm bất biến.

**Câu 8.** Exception ở inner read-only có thể rollback T1 read-write không?

**Đáp án:** Có. Rollback rules được đánh giá trên logical scope tham gia T1, nên lỗi phù hợp có thể đánh dấu T1 rollback-only.

**Câu 9.** `readOnly=true` có đồng nghĩa query sẽ nhanh hơn trong mọi trường hợp không?

**Đáp án:** Không. Đây là hint; nếu inner join T1 read-write, read-only optimizations của transaction mới có thể không áp dụng. Hiệu năng phụ thuộc provider/DB/query plan.

**Câu 10.** Inner `SUPPORTS(readOnly=true)` được gọi ngoài transaction có mở physical transaction chỉ đọc không?

**Đáp án:** Không. `SUPPORTS` không tự mở physical transaction khi chưa có, dù resource synchronization có thể sử dụng read-only metadata trong một số cấu hình.

**Câu 11.** `NESTED(readOnly=true)` trong T1 read-write có một connection mới tự áp dụng read-only không?

**Đáp án:** Không theo semantics savepoint thông thường; nested scope dùng cùng physical T1 nếu manager hỗ trợ.

**Câu 12.** Làm thế nào xác minh chính xác một inner method đang join chứ không mở T2?

**Đáp án:** Gọi qua proxy, đọc `TransactionStatus.isNewTransaction()`, Spring metadata và kiểm tra behavior commit/rollback ở DB sau outer boundary.

## 17. Checklist dùng trong ứng dụng thực tế

Trước khi phụ thuộc vào `readOnly=true` ở một method:

- Xác định **method đó có được Spring transaction advice chặn** không, hay self-invocation/`new` đã bỏ qua proxy.
- Xác định **caller đã có physical transaction** với cùng manager/resource chưa.
- Nếu caller có T1 đọc–ghi và inner dùng `REQUIRED`, mặc định hiểu inner **join T1**, read-only flag hiện hành vẫn của T1.
- Kiểm tra `TransactionStatus.isNewTransaction()` và Spring read-only metadata ở vị trí phù hợp, không suy luận chỉ từ annotation.
- Nếu transaction mới, manager/driver/ORM có hỗ trợ read-only hint hoặc DB enforcement mong muốn không?
- Nếu cần **bắt buộc không ghi**, hãy dùng API/DTO/DB permissions và test, không xem annotation là authorization.
- Nếu dùng `validateExistingTransaction(true)`, hiểu mismatch **outer RO + inner RW** được Spring chú ý; **outer RW + inner RO** không nhất thiết bị từ chối.
- Đặt transaction boundary ở application service nếu toàn use case cần atomicity, hạn chế transaction lồng không có lý do.
- Cân nhắc `REQUIRES_NEW` chỉ khi muốn transaction độc lập; chú ý snapshot visibility, connection pool và kết quả commit riêng.
- Với ORM, quan sát entity dirty checking/flush khi inner join outer read-write.
- Kiểm tra exception/rollback rules: read-only flag không hủy cơ chế rollback-only của participating scope.
- Test cả **standalone**, **join**, **commit**, **rollback**, **strict validation** và persistence provider thực.

**Ghi nhớ:** `@Transactional(readOnly=true)` của method inner là **khai báo mong muốn**, còn physical transaction đang chạy có đặc tính do **outer boundary** quyết định. Khi `REQUIRED` tham gia T1 đọc–ghi, Spring **không tự biến T1 thành chỉ đọc**. Nếu thật sự cần một physical read-only transaction độc lập, phải mở transaction khác theo propagation/kiến trúc phù hợp; dù vậy read-only vẫn không thay thế kiểm soát quyền ghi.

## Tài liệu chính thức

- [Spring Framework — Transaction Propagation: participating REQUIRED và outer characteristics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Using @Transactional và readOnly](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 API — @Transactional.readOnly](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2 API — AbstractPlatformTransactionManager.validateExistingTransaction](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework 6.2 API — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework 6.2 API — DataSourceTransactionManager.setEnforceReadOnly](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JDBC connections and Spring-managed resources](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Understanding declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)