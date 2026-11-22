# TransactionManager và chiến lược quản lý giao dịch trong Spring

Một yêu cầu nghiệp vụ như chuyển tiền, tạo đơn hàng kèm các dòng chi tiết hoặc cập nhật tồn kho có thể thực hiện nhiều thao tác ghi. Nếu một phần thành công và phần còn lại thất bại, ứng dụng cần biết **phạm vi nào phải commit hoặc rollback**. Trong Spring, TransactionManager là thành phần điều phối việc bắt đầu, tham gia và kết thúc giao dịch trên tài nguyên thích hợp. Để áp dụng đúng, cần phân biệt **loại transaction manager**, **cách khai báo ranh giới**, **chiến lược propagation**, **isolation** và **rollback**.

Bài học này trình bày mô hình quản lý giao dịch của Spring Framework cho JDBC, JPA, JTA và ứng dụng reactive; chỉ rõ cách chọn và cấu hình TransactionManager theo từng tình huống.

## 1. TransactionManager nằm ở đâu trong mô hình Spring?

Giả sử service xử lý chuyển 50 đơn vị từ tài khoản A sang tài khoản B. Cả hai câu SQL cần cùng commit hoặc cùng rollback. Service có thể khai báo:

~~~java
// Trích đoạn minh họa trong ứng dụng Spring đã cấu hình repository và transaction.
@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, int amount) {
        accounts.decrease(fromId, amount);
        accounts.increase(toId, amount);
    }
}
~~~

Đoạn mã **không phải chương trình độc lập**: cần lớp repository, DataSource, TransactionManager và cơ chế quản lý transaction được kích hoạt. Mục đích của nó là chỉ ra ranh giới giao dịch ở tầng service. Không có bằng chứng rằng hai câu SQL cùng transaction nếu repository lại sử dụng các DataSource hoặc connection độc lập.

Một sơ đồ các vai trò:

~~~text
Caller
  |
  v
Spring-managed service (lời gọi qua transactional proxy)
  |
  v
TransactionInterceptor / TransactionAspectSupport
  |
  v
TransactionManager: mở, tham gia, commit hoặc rollback
  |
  +---- JDBC: DataSource + Connection -> JDBC driver -> DBMS
  |
  +---- JPA : EntityManager + JPA provider -> JDBC -> DBMS
  |
  +---- JTA : transaction coordinator -> các tài nguyên enlist được
  |
  +---- R2DBC: reactive Connection -> R2DBC driver -> DBMS
~~~

**Spring không tự thay database thực thi ACID.** TransactionManager ra quyết định điều phối trong phạm vi tài nguyên mà nó quản lý; DBMS thực thi các thay đổi, khóa, ràng buộc và commit/rollback thực tế. TransactionManager cũng không mặc nhiên biến một lần gửi HTTP, email hay message thành thao tác có thể rollback cùng SQL.

## 2. Họ interface: TransactionManager, PlatformTransactionManager và ReactiveTransactionManager

Trong Spring, **org.springframework.transaction.TransactionManager** là interface gốc đánh dấu abstraction. Hai nhánh chính có ngữ nghĩa khác nhau:

| Interface | Dùng cho | Cơ chế gắn transaction | Những thao tác chính |
| --- | --- | --- | --- |
| PlatformTransactionManager | Luồng imperative/blocking, ví dụ JDBC, JPA | Transaction context thường gắn với luồng hiện tại | getTransaction, commit, rollback |
| ReactiveTransactionManager | Pipeline reactive, ví dụ R2DBC | Reactor Context trong chuỗi reactive | getReactiveTransaction, commit, rollback trả về Publisher/Mono |

Với PlatformTransactionManager, hợp đồng tiêu biểu là:

~~~java
// Trích chữ ký API; không phải lớp thực thi hoàn chỉnh.
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

- **TransactionDefinition** mô tả chính sách yêu cầu: propagation, isolation, timeout, read-only và tên transaction.
- **TransactionStatus** cho biết transaction mới hay đang tham gia, có savepoint hay không, đã hoàn tất hay chưa; mã nghiệp vụ cũng có thể yêu cầu **setRollbackOnly()**.
- **PlatformTransactionManager** thực hiện lời gọi thông qua công nghệ cụ thể. Các implementation thường kế thừa **AbstractPlatformTransactionManager** để sử dụng chung quy trình kiểm soát propagation, synchronization, commit và rollback.

Với ReactiveTransactionManager, thao tác transaction gắn với luồng xử lý bất đồng bộ và subscription của Publisher, không thể giả định nó được truyền nhờ ThreadLocal giữa mọi callback. Trong cùng một ứng dụng có thể tồn tại cả hai loại manager nhưng chúng không thể tự thay thế nhau.

**Không nên chọn manager chỉ theo tên lớp hoặc chỉ vì đã có @Transactional.** Cần căn cứ vào công nghệ truy cập dữ liệu và tài nguyên thực sự mà service sử dụng.

## 3. Các implementation và cách lựa chọn

| Transaction manager | Tài nguyên được quản lý | Nên chọn khi | Giới hạn phải biết |
| --- | --- | --- | --- |
| **JdbcTransactionManager** | Một DataSource JDBC/Connection | Ứng dụng JDBC, JdbcTemplate, NamedParameterJdbcTemplate | Một local JDBC transaction, không tự kết nối nhiều DB thành một atomic transaction |
| **DataSourceTransactionManager** | Một DataSource JDBC/Connection | Cần transaction JDBC local, tương thích lâu dài với cách tích hợp JDBC | Không quản lý JPA persistence context hoặc giao dịch đa tài nguyên |
| **JpaTransactionManager** | EntityManagerFactory và EntityManager | Dùng JPA/Hibernate qua cùng persistence unit | Không tự điều phối nhiều EntityManagerFactory hoặc nhiều DB độc lập |
| **JtaTransactionManager** | JTA transaction coordinator | Môi trường có JTA server/coordinator và tài nguyên tham gia giao dịch toàn cục phù hợp | Cần cấu hình enlistment/XA; chi phí và rủi ro vận hành cao hơn local transaction |
| **R2dbcTransactionManager** | Một R2DBC ConnectionFactory | Luồng reactive đọc/ghi dữ liệu bằng R2DBC | Không quản lý JDBC blocking trong reactive transaction |
| **TransactionManager tự viết** | Theo hợp đồng implementation | Tích hợp tài nguyên đặc thù khi thật sự cần | Cần tự bảo đảm semantics, synchronization, exception và cleanup |

**JdbcTransactionManager** kế thừa cơ chế của DataSourceTransactionManager và bổ sung dịch các lỗi commit/rollback của JDBC thành ngoại lệ truy cập dữ liệu của Spring. Với ứng dụng thuần JDBC hiện đại, đây thường là lựa chọn tốt. Cả hai dùng một DataSource; datasource thực tế nên là connection pool trong sản xuất.

**JpaTransactionManager** quản lý vòng đời transaction JPA và persistence context qua EntityManager. Trong cấu hình phù hợp, JDBC sử dụng cùng DataSource có thể tham gia transaction JPA; điều đó đòi hỏi tích hợp đúng, không được suy đoán rằng mọi JDBC Connection hoặc EntityManager đều dùng chung transaction.

**JtaTransactionManager** phù hợp khi ứng dụng thật sự cần transaction coordinator phối hợp nhiều tài nguyên có khả năng tham gia JTA/XA. Nó không khiến REST API, email hoặc hai kết nối thông thường tự động trở thành một giao dịch phân tán. Với nhiều hệ thống, **transaction cục bộ + transactional outbox + consumer idempotent** có thể dễ vận hành hơn một giao dịch XA toàn cục.

**R2dbcTransactionManager** phù hợp khi repository dùng R2DBC và trả về Mono/Flux. Với JDBC/JPA blocking, chọn PlatformTransactionManager. Hai thế giới có mô hình propagation context khác nhau; không chạy câu lệnh JDBC trong reactive chain rồi mặc nhiên mong nó tham gia R2DBC transaction.

### Ma trận quyết định nhanh

1. **Một cơ sở dữ liệu, dùng JdbcTemplate/JDBC?** Chọn JdbcTransactionManager hoặc DataSourceTransactionManager với đúng DataSource.
2. **Một persistence unit JPA?** Chọn JpaTransactionManager cho EntityManagerFactory đó.
3. **Nhiều tài nguyên cần bảo đảm atomic commit thực sự?** Đánh giá JTA/XA và khả năng của từng tài nguyên; nếu không khả thi, thiết kế outbox/saga và eventual consistency rõ ràng.
4. **R2DBC thuần reactive?** Chọn R2dbcTransactionManager với đúng ConnectionFactory.
5. **Nhiều datasource độc lập?** Có thể khai báo nhiều manager và chỉ định đúng manager cho từng nghiệp vụ, nhưng **nhiều local managers không tạo ra distributed transaction**.

Spring Boot có thể tự cấu hình TransactionManager dựa trên DataSource, JPA hoặc R2DBC và các bean hiện có. Khi ứng dụng chứa nhiều datasource/provider, hãy kiểm tra bean thực tế được chọn thay vì dựa vào giả định về auto-configuration.

## 4. Hai chiến lược khai báo ranh giới: declarative và programmatic

### 4.1. Declarative transaction với @Transactional

Khi transaction management được kích hoạt, Spring thường sử dụng AOP proxy. Lời gọi đi qua proxy sẽ được **TransactionInterceptor** xử lý:

1. Tìm cấu hình transaction của phương thức/lớp, bao gồm tên manager nếu khai báo.
2. Chọn manager và yêu cầu transaction phù hợp với propagation.
3. Gắn tài nguyên và cho phương thức nghiệp vụ thực thi.
4. Nếu lời gọi kết thúc bình thường và transaction được phép commit, yêu cầu commit tại ranh giới sở hữu transaction.
5. Nếu ngoại lệ phù hợp rollback rule hoặc trạng thái rollback-only, yêu cầu rollback.
6. Giải phóng, khôi phục tài nguyên và transaction context.

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring AOP Proxy
    participant TM as TransactionManager
    participant DB as Transactional Resource
    Caller->>Proxy: Gọi service method
    Proxy->>TM: getTransaction(definition)
    TM->>DB: Mở/tham gia transaction
    Proxy->>DB: Chạy nghiệp vụ (JDBC/JPA)
    alt Thành công, không rollback-only
        Proxy->>TM: commit(status)
        TM->>DB: Commit hoặc chờ transaction ngoài
    else Exception phù hợp / rollback-only
        Proxy->>TM: rollback(status)
        TM->>DB: Rollback hoặc đánh dấu rollback-only
    end
    Proxy-->>Caller: Result hoặc exception
~~~

Cấu hình một manager cho ứng dụng JDBC (đây là **đoạn cấu hình minh họa**, cần DataSource bean tồn tại):

~~~java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Các import tương ứng: **org.springframework.context.annotation.Bean**, **Configuration**; **org.springframework.transaction.annotation.EnableTransactionManagement**; **org.springframework.transaction.PlatformTransactionManager**; **org.springframework.jdbc.support.JdbcTransactionManager**; **javax.sql.DataSource**. Trong ứng dụng Spring Boot tự cấu hình thành công, có thể không cần tự khai báo bean này.

Dùng annotation để mô tả chính sách tại ranh giới service:

~~~java
// Trích đoạn service minh họa; các dependency nằm trong ứng dụng Spring.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = BusinessCheckedException.class,
    timeout = 15
)
public void placeOrder(Command command) throws BusinessCheckedException {
    reserveInventory(command);
    saveOrder(command);
}
~~~

Đây không phải chương trình độc lập: các type Command, BusinessCheckedException và phương thức nghiệp vụ cần được định nghĩa. Ý nghĩa là cùng một service operation, Spring cố gắng áp dụng transaction được yêu cầu lên tài nguyên thích hợp. **Isolation.READ_COMMITTED** phụ thuộc DBMS hỗ trợ; thời gian timeout không bảo đảm mọi driver/DBMS có cùng cách ngắt câu lệnh.

**Các lưu ý về proxy:** lời gọi tự thân như this.save() từ cùng object thường không đi qua proxy, nên annotation trên phương thức save() không tạo transaction mới. Các phương thức private/final hoặc lời gọi ngoài cơ chế proxy cũng cần được đánh giá theo proxy mode và phiên bản Spring; đặt ranh giới transaction ở phương thức service có thể được Spring chặn rõ ràng. Transaction context imperative không tự truyền sang luồng mới do @Async hoặc Executor tạo ra.

### 4.2. Programmatic transaction với TransactionTemplate

Trong luồng imperative, **TransactionTemplate** nhận PlatformTransactionManager, bao các callback trong transaction và tự thực hiện commit/rollback theo trạng thái hoặc ngoại lệ.

~~~java
// Trích đoạn minh họa bên trong class đã được inject JdbcTemplate và manager.
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
template.executeWithoutResult(status -> {
    jdbcTemplate.update("UPDATE account SET balance = balance - 10 WHERE id = 1");
    if (businessConditionNotMet()) {
        status.setRollbackOnly();
    }
});
~~~

Điểm mạnh là **không phụ thuộc lời gọi qua AOP proxy**, dễ điều khiển một phạm vi ngắn, timeout hoặc rollback-only động. Đổi lại, logic transaction gắn chặt vào mã nghiệp vụ và dễ bị lạm dụng nếu bọc nhiều thao tác nhỏ. Đối với service thông thường, @Transactional thường dễ đọc hơn.

Trong reactive, lựa chọn programmatic tương đương là **TransactionalOperator**; operator bao Publisher và dùng ReactiveTransactionManager. Không đưa mã JDBC blocking vào pipeline rồi coi TransactionalOperator là transaction manager cho JDBC.

### 4.3. Nên chọn cách nào?

| Tiêu chí | @Transactional | TransactionTemplate / TransactionalOperator |
| --- | --- | --- |
| Sự tách biệt nghiệp vụ và hạ tầng | Cao; policy khai báo bằng metadata | Code nghiệp vụ biết API transaction |
| Ranh giới | Phương thức được interceptor quản lý | Khối callback hoặc pipeline được bao rõ ràng |
| Cần AOP proxy ở imperative | Thường có trong proxy mode | Không |
| Thay đổi transaction policy lúc runtime | Giới hạn theo metadata/config | Linh hoạt hơn theo từng callback |
| Dễ đọc với CRUD service | Thường đơn giản hơn | Có thể nhiều boilerplate hơn |
| Kiểu ứng dụng | Imperative và reactive nếu dùng đúng manager | TransactionTemplate (imperative), TransactionalOperator (reactive) |

## 5. Propagation: chiến lược khi lời gọi lồng nhau

**Propagation** trả lời: “Khi một phương thức cần transaction nhưng đã có transaction ở tầng gọi bên ngoài, Spring sẽ làm gì?” Đây là chính sách của transaction manager, không phải một mức khóa database.

| Propagation | Đang có transaction | Chưa có transaction | Ghi chú |
| --- | --- | --- | --- |
| **REQUIRED** (mặc định) | Tham gia transaction hiện tại | Tạo mới | Thích hợp cho đa số service |
| **REQUIRES_NEW** | Tạm đình chỉ transaction ngoài, tạo transaction vật lý mới độc lập | Tạo mới | Có thể cần thêm connection; commit/rollback độc lập |
| **NESTED** | Tạo savepoint trong cùng transaction vật lý nếu manager hỗ trợ | Tạo transaction mới | Rollback một phần về savepoint; commit cuối vẫn thuộc outer |
| **SUPPORTS** | Tham gia nếu có | Chạy không có transaction chủ động | Cần hiểu hành vi đọc hoặc ghi khi không có transaction |
| **MANDATORY** | Tham gia | Báo lỗi | Yêu cầu caller đã mở transaction |
| **NOT_SUPPORTED** | Tạm đình chỉ transaction hiện tại | Chạy ngoài transaction | Hữu ích khi thao tác độc lập thật sự cần bỏ transaction |
| **NEVER** | Báo lỗi | Chạy ngoài transaction | Dùng khi nghiêm cấm chạy trong transaction |

### 5.1. REQUIRED: các ranh giới logic chia sẻ một transaction vật lý

Giả sử method outer() và inner() đều REQUIRED. Khi outer đã tạo transaction, inner **tham gia cùng transaction vật lý**, không tự commit khi inner trả về. Mỗi method có logical scope riêng nhưng chung kết quả cuối.

Nếu inner xác định phải rollback và đánh dấu transaction rollback-only, outer dù hoàn tất bình thường cũng không thể commit. Trong tình huống outer cố commit mà không biết inner đã làm rollback-only, Spring thường ném **UnexpectedRollbackException**. Exception này bảo đảm caller không hiểu nhầm thao tác đã commit.

### 5.2. REQUIRES_NEW: giao dịch vật lý độc lập

Khi outer() đã có transaction và inner() là REQUIRES_NEW, Spring tạm suspend tài nguyên của outer, mở transaction mới cho inner, rồi phục hồi outer sau khi inner kết thúc.

~~~text
outer REQUIRED   : [ begin ----------- (suspended) ---------- resume ---- rollback ]
inner REQUIRES_NEW:                    [ begin --- commit ]
Kết quả          : thay đổi trong inner có thể được giữ dù outer rollback
~~~

Tình huống dùng hợp lý: ghi bản ghi audit độc lập mà yêu cầu sản phẩm cho phép lưu ngay cả khi thao tác chính thất bại. Tuy nhiên, việc tách audit theo cách này có thể gây sai lệch ngữ nghĩa nếu audit phải phản ánh đúng giao dịch nghiệp vụ đã commit; cần định nghĩa rõ yêu cầu.

**Chi phí kỹ thuật:** inner thường cần connection mới trong khi outer vẫn giữ connection. Nếu có N luồng đồng thời, mỗi luồng cần cả outer và inner connection, pool chỉ đủ N connection có thể khiến các luồng chờ nhau. Hãy đặt giới hạn concurrency, connection pool sizing và timeout thực tế.

### 5.3. NESTED: cùng transaction vật lý, có savepoint

NESTED dựa vào savepoint khi manager/driver hỗ trợ. Khi inner thất bại, có thể rollback về savepoint rồi outer tiếp tục; nhưng **outer rollback thì mọi thay đổi, kể cả phần nested từng thành công, vẫn mất**.

~~~text
BEGIN outer
  UPDATE A
  SAVEPOINT before_inner
    UPDATE B
  ROLLBACK TO SAVEPOINT before_inner
  UPDATE C
COMMIT outer

DB lưu A và C; B bị hủy.
~~~

Trong Spring, DataSourceTransactionManager/JdbcTransactionManager có hỗ trợ savepoint JDBC phù hợp. Không mặc định dựa vào NESTED cho mọi JPA provider, Reactive manager hoặc tài nguyên không hỗ trợ savepoint.

**REQUIRES_NEW khác NESTED:** REQUIRES_NEW có transaction vật lý mới có thể commit độc lập; NESTED chỉ tạo savepoint trong transaction vật lý đang có. Đây là khác biệt quyết định khi lựa chọn chiến lược.

### 5.4. Quy tắc chọn propagation

- Dùng **REQUIRED** cho một đơn vị nghiệp vụ cần cùng thành công/thất bại, đặt boundary ở service.
- Chỉ dùng **REQUIRES_NEW** khi hành vi cần độc lập về commit thực sự là yêu cầu; đánh giá pool và side effect.
- Dùng **NESTED** khi muốn rollback một phần trong cùng transaction và đã kiểm chứng manager/driver hỗ trợ savepoint.
- Dùng **MANDATORY** khi method không có nghĩa nếu caller chưa có transaction.
- Dùng **SUPPORTS/NOT_SUPPORTED/NEVER** cho hợp đồng có chủ đích; tránh dùng để “chữa” lỗi rollback khi chưa hiểu sự khác nhau.

## 6. Isolation, timeout và readOnly: chiến lược điều khiển tài nguyên

### 6.1. Isolation

Propagation giải quyết **quan hệ giữa lời gọi**; isolation giải quyết **quan hệ giữa các transaction đồng thời**.

| Isolation | Ý nghĩa khái quát | Rủi ro hoặc lưu ý |
| --- | --- | --- |
| DEFAULT | Dùng mức mặc định của cơ sở dữ liệu | Cần biết DBMS đang cấu hình gì |
| READ_UNCOMMITTED | Có thể cho phép đọc dữ liệu chưa commit | Một số DBMS nâng mức hoặc triển khai khác |
| READ_COMMITTED | Tránh đọc dữ liệu chưa commit | Non-repeatable read/phantom vẫn có thể xảy ra tùy DBMS |
| REPEATABLE_READ | Nhiều DBMS giữ snapshot/khóa để tránh non-repeatable read | Không mặc nhiên loại mọi write skew hoặc anomaly |
| SERIALIZABLE | Cố gắng cho kết quả tương đương chạy tuần tự | Có thể cần retry khi bị serialization failure, giảm concurrency |

Isolation do DBMS thực thi. Transaction manager thường yêu cầu setting trên connection hoặc cơ chế tương ứng. **Không có giá trị isolation duy nhất tối ưu cho mọi thao tác.** Đọc số dư rồi cập nhật có thể cần câu UPDATE nguyên tử, khóa hàng, optimistic locking hoặc isolation cao hơn tùy bất biến.

Khi một method REQUIRED chỉ **tham gia** transaction đã có, khai báo isolation riêng của method bên trong thường không thay đổi isolation của transaction vật lý hiện tại. Có thể bật validateExistingTransaction=true ở AbstractPlatformTransactionManager để Spring từ chối tham gia khi có mismatch đáng kể; đừng giả định annotation inner luôn thắng.

### 6.2. Timeout

Timeout mô tả giới hạn thời gian transaction, nhưng cách enforcement tùy manager, driver và DBMS. Timeout có thể được chuyển thành deadline cho transaction hoặc timeout của statement qua integration phù hợp. Không nên coi đây là “tự động kill mọi luồng Java và hủy mọi HTTP call” chính xác sau số giây khai báo.

Nếu transaction gọi dịch vụ mạng lâu, giữ connection và lock trong suốt khoảng chờ có thể làm giảm throughput. Thường nên tách các thao tác mạng khỏi ranh giới DB transaction hoặc chọn kiến trúc bất đồng bộ phù hợp.

### 6.3. readOnly

readOnly=true là **gợi ý** dành cho manager, JDBC connection, JPA provider và/hoặc DBMS để tối ưu thao tác đọc khi hỗ trợ. Nó không phải một cơ chế phân quyền hoặc bảo đảm bất biến tuyệt đối trong mọi cấu hình.

Một đoạn @Transactional(readOnly=true) vẫn có thể gây lệnh ghi hoặc ngoại lệ tùy stack; hãy dùng tài khoản DB chỉ đọc và cơ chế permission/constraint nếu yêu cầu là không cho phép ghi.

## 7. Rollback: chiến lược xử lý lỗi và rollback-only

Theo mặc định của @Transactional trong cấu hình thông thường:

- **RuntimeException** hoặc **Error** thoát ra khỏi ranh giới transactional làm Spring yêu cầu rollback.
- **Checked exception** không tự kích hoạt rollback trừ khi có rollbackFor/chính sách tương ứng.
- Nếu đã catch exception rồi return bình thường, interceptor có thể coi lời gọi thành công và commit.
- Có thể chủ động yêu cầu rollback bằng TransactionStatus.setRollbackOnly() trong callback programmatic hoặc thông qua API transaction status phù hợp.

Ví dụ kiểm soát lỗi checked (snippet minh họa trong Spring service):

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void checkout(Order order) throws PaymentRejectedException {
    reserveStock(order);
    chargeWithinTransactionBoundary(order);
}
~~~

Đoạn trên không phải chương trình độc lập và không hàm ý thao tác charge tới cổng thanh toán bên ngoài có thể rollback cùng database. Nếu chargeWithinTransactionBoundary gọi API ngoài, cần thiết kế nhất quán và bù trừ riêng.

**rollbackFor** chỉ điều khiển quyết định của Spring, không biến các side effect ngoài transaction thành thao tác ACID. **noRollbackFor** có thể yêu cầu commit dù một loại ngoại lệ được ném; cần dùng rất thận trọng để không tạo trạng thái dở dang.

Hai mức rollback cần phân biệt:

1. **Rollback của logical transaction scope**: một phương thức tham gia REQUIRED đánh dấu rollback-only; manager có thể đánh dấu transaction vật lý hiện có phải rollback về sau.
2. **Rollback của physical transaction**: transaction owner hoặc coordinator thực thi rollback tại ranh giới cuối; DBMS hủy các thay đổi chưa commit thuộc transaction đó.

Trong trường hợp JPA, cần nhớ EntityManager có thể flush SQL trước commit. **Flush không đồng nghĩa commit**, và transaction vẫn có thể rollback. Một số lỗi DB/JPA làm transaction rơi vào trạng thái rollback-only; không nên nuốt lỗi rồi cố tiếp tục như transaction vẫn khỏe mạnh.

## 8. Chọn nhiều TransactionManager trong cùng ứng dụng

Ứng dụng có thể truy cập hai DB:

~~~text
billingService  -> billingDataSource -> billingTxManager
reportingService -> reportingDataSource -> reportingTxManager
~~~

Khai báo bean manager với tên rõ ràng rồi chỉ định bằng annotation:

~~~java
// Trích đoạn cấu hình minh họa; hai DataSource đã được khai báo riêng.
@Bean("billingTxManager")
public PlatformTransactionManager billingTxManager(
        @Qualifier("billingDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean("reportingTxManager")
public PlatformTransactionManager reportingTxManager(
        @Qualifier("reportingDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

~~~java
// Trích đoạn minh họa; giả sử đây là Spring-managed service method.
@Transactional(transactionManager = "billingTxManager")
public void collectPayment(Bill bill) {
    billingRepository.update(bill);
}
~~~

Phải import đúng **@Qualifier** từ Spring và các type Java/Spring tương ứng; đây là các snippet, không phải file Java có thể chạy độc lập. Khi có nhiều manager, bean mặc định hoặc qualifier cần được xác định tường minh. Dùng nhầm manager có thể khiến một repository chạy ngoài transaction mong muốn hoặc tạo transaction trên tài nguyên khác.

**Lưu ý cốt lõi:** gọi lần lượt billingTxManager và reportingTxManager không bảo đảm atomicity xuyên hai DB. Nếu commit DB A thành công nhưng DB B lỗi, local transaction manager không thể rollback A đã commit. Trường hợp cần atomic multi-resource, cần transaction coordinator thích hợp với tài nguyên enlist được hoặc dùng phương án consistency nghiệp vụ như outbox/saga.

## 9. Thực hành Java 17+: thấy rõ REQUIRED và REQUIRES_NEW

Ví dụ chạy độc lập dưới đây dùng **Spring JDBC + H2 in-memory** và TransactionTemplate. Nó kiểm chứng các trường hợp:

1. Transaction ngoài rollback, REQUIRES_NEW bên trong commit độc lập.
2. REQUIRED bên trong đánh dấu rollback-only, transaction ngoài cố commit nên nhận UnexpectedRollbackException.
3. Một transaction REQUIRED đơn lẻ commit thành công.

Cấu trúc:

~~~text
tx-manager-strategies/
├── pom.xml
└── src/main/java/demo/TxManagerStrategiesDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-manager-strategies</artifactId>
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
                    <mainClass>demo.TxManagerStrategiesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TxManagerStrategiesDemo.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionTemplate;

public final class TxManagerStrategiesDemo {
    private TxManagerStrategiesDemo() {}

    private static void show(JdbcTemplate jdbc, String phase) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s: A=%d, B=%d%n", phase, a, b);
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE account (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (2, 200)");

        JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);

        TransactionTemplate required = new TransactionTemplate(manager);
        TransactionTemplate requiresNew = new TransactionTemplate(manager);
        requiresNew.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        show(jdbc, "Initial");

        // A thay đổi trong outer nhưng bị rollback; inner độc lập đã commit B.
        required.executeWithoutResult(outer -> {
            jdbc.update(
                    "UPDATE account SET balance = balance - 20 WHERE id = 1");
            requiresNew.executeWithoutResult(inner ->
                    jdbc.update(
                            "UPDATE account SET balance = balance + 5 WHERE id = 2"));
            outer.setRollbackOnly();
        });
        show(jdbc, "REQUIRES_NEW + outer rollback");

        // inner REQUIRED tham gia transaction outer và yêu cầu rollback-only.
        try {
            required.executeWithoutResult(outer -> {
                jdbc.update(
                        "UPDATE account SET balance = balance - 10 WHERE id = 1");
                required.executeWithoutResult(inner -> {
                    jdbc.update(
                            "UPDATE account SET balance = balance + 10 WHERE id = 2");
                    inner.setRollbackOnly();
                });
            });
        } catch (UnexpectedRollbackException expected) {
            System.out.println("REQUIRED inner: UnexpectedRollbackException");
        }
        show(jdbc, "After REQUIRED rollback");

        // Hai câu SQL trong một transaction thành công.
        required.executeWithoutResult(status -> {
            jdbc.update(
                    "UPDATE account SET balance = balance - 30 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 30 WHERE id = 2");
        });
        show(jdbc, "Committed REQUIRED");
    }
}
~~~

Yêu cầu máy có **JDK 17+** và **Maven**. Trong thư mục tx-manager-strategies, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến từ chương trình Java** (không tính các log/warning riêng của Maven):

~~~text
Initial: A=100, B=200
REQUIRES_NEW + outer rollback: A=100, B=205
REQUIRED inner: UnexpectedRollbackException
After REQUIRED rollback: A=100, B=205
Committed REQUIRED: A=70, B=235
~~~

**Giải thích trạng thái từng bước:**

- **Initial:** H2 có tài khoản A=100 và B=200. Các lệnh tạo/seed data đã hoàn tất trước khi ví dụ mở transaction.
- **REQUIRES_NEW:** outer trên một connection trừ A 20 chưa commit; inner tạm suspend outer và trên connection giao dịch khác cộng B 5 rồi commit. Sau đó outer setRollbackOnly, chỉ thay đổi A bị hủy. Vì vậy A=100, B=205.
- **REQUIRED lồng nhau:** inner dùng cùng transaction vật lý với outer, tăng B 10 rồi đánh dấu rollback-only. Outer cố commit và nhận UnexpectedRollbackException. Cả trừ A 10 và cộng B 10 đều rollback; số dư vẫn A=100, B=205.
- **REQUIRED commit:** trừ A 30 và cộng B 30 trong một transaction thành công, cho kết quả A=70, B=235.

DriverManagerDataSource tạo connection mới khi cần, phục vụ quan sát sự tách biệt giữa hai giao dịch vật lý. Trong sản xuất, nên dùng connection pool phù hợp. Ví dụ này minh họa propagation trong **cùng một DataSource**; nếu đổi sang hai datasource, cần đánh giá atomicity riêng.

### Bài tập mở rộng có kiểm soát

Thay inner REQUIRES_NEW bằng REQUIRED trong ví dụ đầu, giữ outer rollback-only: điều gì xảy ra với B? Vì inner tham gia transaction outer, B cũng rollback và giữ nguyên 200. Đổi lại REQUIRES_NEW rồi xóa outer.setRollbackOnly(): A thành 80 và B thành 205. Hãy tự kiểm tra bằng cách đọc dữ liệu sau khi transaction đã kết thúc.

## 10. Reactive transaction: cùng ý tưởng, khác cơ chế truyền context

Trong ứng dụng reactive với R2DBC:

- ReactiveTransactionManager quản lý reactive transaction qua publisher, không dựa vào một ThreadLocal cố định.
- TransactionalOperator có thể bao Mono/Flux để mọi thao tác reactive trong cùng context tham gia transaction.
- Khi một publisher chưa được subscribe, đoạn mã trong pipeline chưa chạy và transaction chưa được thực thi theo cách thông thường.
- Các thao tác muốn tham gia phải cùng reactive transaction context và đúng ConnectionFactory/manager.
- @Transactional với return type reactive dùng reactive transaction manager; với method trả về kiểu thông thường, dùng PlatformTransactionManager phù hợp.

Ví dụ ý tưởng (snippet minh họa, cần ReactiveTransactionManager và DatabaseClient đã cấu hình):

~~~java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Void> updateBoth =
        databaseClient.sql("UPDATE account SET balance = balance - 5 WHERE id = 1")
                .fetch().rowsUpdated()
                .then(databaseClient.sql(
                        "UPDATE account SET balance = balance + 5 WHERE id = 2")
                        .fetch().rowsUpdated())
                .then();

return operator.transactional(updateBoth);
~~~

Đây không phải lớp độc lập và kết quả phụ thuộc R2DBC driver/DBMS. Không trộn JDBC blocking trong pipeline trên rồi tưởng JdbcTemplate sẽ dùng connection của R2dbcTransactionManager. Nếu cần kết hợp hai cơ chế, hãy thiết kế ranh giới và consistency riêng.

## 11. Hướng dẫn chọn chiến lược theo tình huống thực tế

### Trường hợp A: một lần đặt hàng ghi vào ba bảng cùng DB

**Khuyến nghị:** một service boundary dùng REQUIRED; với JDBC chọn JdbcTransactionManager, với JPA chọn JpaTransactionManager. Các repository phải tham gia đúng transaction. Tạo đơn hàng, chi tiết, đặt tồn kho cần cùng kết thúc; trường hợp bị vi phạm ràng buộc rollback toàn bộ.

**Không cần** REQUIRES_NEW cho từng repository. Tách mỗi dòng SQL thành transaction riêng sẽ phá vỡ atomicity của đơn hàng.

### Trường hợp B: lưu dấu vết kỹ thuật dù nghiệp vụ thất bại

**Có thể cân nhắc:** tách một service thực sự qua Spring proxy và dùng REQUIRES_NEW cho bản ghi kỹ thuật. Cần quyết định audit này mang nghĩa “đã thử” hay “đã hoàn tất”. Nếu cần phản ánh đúng trạng thái đã commit của nghiệp vụ, after-commit hook hoặc transactional outbox có thể phù hợp hơn.

### Trường hợp C: thử một nhánh phụ, thất bại thì tiếp tục nhánh chính

**Có thể cân nhắc:** NESTED với savepoint JDBC khi hỗ trợ; nhánh phụ rollback về savepoint, outer có thể tiếp tục. Nếu dùng JPA hay tài nguyên không hỗ trợ, không âm thầm giả định NESTED luôn thành công.

### Trường hợp D: hai DB và một message broker

**Phân tích trước:** tài nguyên nào có thể enlist vào JTA/XA và yêu cầu atomicity thật sự ra sao. Nếu yêu cầu giao dịch toàn cục không khả thi, dùng transaction local để ghi business state + outbox trong cùng DB; một publisher phát sự kiện sau đó và consumer xử lý idempotent. Cần chấp nhận consistency cuối cùng và khả năng retry/duplicate.

### Trường hợp E: đọc báo cáo nặng

**Khuyến nghị:** xác định isolation, snapshot consistency, timeout và readOnly đúng DBMS. Tránh giữ transaction quá lâu khi xuất báo cáo hoặc gọi dịch vụ ngoài; chỉ dùng NOT_SUPPORTED khi việc chạy ngoài transaction thật sự đáp ứng consistency mong muốn.

## 12. Các lỗi cấu hình và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| @Transactional không rollback | Self-invocation, ngoại lệ bị catch, checked exception không nằm trong rollback rule | Theo dấu proxy, ranh giới method, rollbackFor và ngoại lệ thoát ra |
| Một repository ghi rồi vẫn commit sau rollback | Dùng sai manager, DataSource khác hoặc JDBC Connection ngoài transaction | Đối chiếu bean manager, DataSource, SQL log và connection identity |
| UnexpectedRollbackException ở outer | Inner REQUIRED đã đánh dấu rollback-only | Xem stack trace và logic inner; đừng bắt exception rồi tưởng commit thành công |
| REQUIRES_NEW treo chờ | Pool cạn connection hoặc lock conflict | Kiểm tra active/waiting connections, thread dump, lock và pool sizing |
| NESTED báo unsupported | Driver/manager không hỗ trợ savepoint hay cấu hình không phù hợp | Kiểm chứng transaction manager và JDBC savepoint capability |
| Isolation annotation inner không có tác dụng | Inner chỉ tham gia transaction đã tồn tại | Xác định ranh giới mở transaction vật lý và validateExistingTransaction |
| DB không đúng trạng thái sau commit | Logic SQL sai, concurrency anomaly, transaction khác hoặc commit outcome không rõ | Test integration với DB thật, SQL log, transaction id và query từ connection mới |
| Reactive @Transactional không tác dụng | Publisher không được subscribe, mất Reactor Context, sai manager | Kiểm tra reactive chain, context, return type và ConnectionFactory |

**Quy trình debug theo thứ tự:**

1. Xác định chính xác method entrypoint và transaction boundary (proxy hay TransactionTemplate/TransactionalOperator).
2. Xác định PlatformTransactionManager hay ReactiveTransactionManager đã chọn, bean name và datasource/provider tương ứng.
3. Kiểm tra propagation đang tạo transaction mới hay chỉ tham gia; có rollback-only, suspend hoặc savepoint không.
4. Kiểm tra isolation, readOnly, timeout thực tế và SQL/exception do driver hoặc DBMS trả về.
5. Sau khi method kết thúc, xác minh trạng thái dữ liệu bằng connection/transaction độc lập, thay vì chỉ nhìn kết quả object trong persistence context.
6. Nếu giao dịch liên quan nhiều tài nguyên, kiểm tra cơ chế consistency, idempotency và khả năng retry của toàn hệ thống.

### Logging và test

Trong môi trường test, có thể bật TRACE/DEBUG có chọn lọc cho **org.springframework.transaction** và **org.springframework.jdbc.datasource** để xem lúc tạo/tham gia, suspend/resume, commit/rollback. Tránh bật SQL và parameter nhạy cảm ngoài môi trường được kiểm soát.

Một integration test hữu ích thực hiện phương thức nghiệp vụ **qua Spring bean proxy**, cố ý gây lỗi ở thao tác thứ hai, rồi đọc lại hai hàng từ transaction khác để khẳng định rollback. Sau đó kiểm tra thành công và các trường hợp REQUIRED/REQUIRES_NEW. Nếu kiểm tra behavior thật của database, dùng DBMS tương ứng môi trường ứng dụng; H2 chỉ là demo tiện lợi, không mô phỏng hoàn toàn locking và isolation của mọi DB.

## 13. Câu hỏi tự kiểm tra

**1. TransactionManager có phải là JDBC driver hoặc DBMS không?**  
Không. Nó là abstraction điều phối transaction. Driver giao tiếp với DBMS; DBMS thực thi commit/rollback và isolation thực tế.

**2. Vì sao inner REQUIRED đánh dấu rollback-only lại có thể làm outer nhận UnexpectedRollbackException?**  
Vì hai logical scope dùng chung một physical transaction. Outer tưởng có thể commit, nhưng transaction đã bị đánh dấu buộc rollback; Spring báo sự kiện commit không xảy ra.

**3. REQUIRES_NEW có thể commit rồi sau đó outer rollback không?**  
Có. Inner dùng một physical transaction độc lập. Đây là hành vi có chủ đích, không phải nested savepoint.

**4. NESTED khác REQUIRES_NEW ở đâu?**  
NESTED thường dùng savepoint trên cùng transaction vật lý; outer rollback sẽ hủy tất cả. REQUIRES_NEW mở transaction vật lý độc lập và có thể commit riêng.

**5. Khi nào dùng JpaTransactionManager thay vì JdbcTransactionManager?**  
Khi nghiệp vụ dùng JPA EntityManager/persistence unit để quản lý thay đổi đối tượng và flush, chọn manager tích hợp JPA phù hợp; JDBC dùng manager JDBC trên DataSource.

**6. Có hai DataSource, dùng @Transactional với một manager thì được bảo đảm atomicity ở cả hai không?**  
Không. Một local manager không tự phối hợp atomic commit xuyên hai tài nguyên độc lập. Cần JTA/XA phù hợp hoặc chiến lược consistency ứng dụng.

**7. readOnly=true và timeout=10 có phải bảo đảm cấm mọi ghi và hủy mọi tác vụ đúng 10 giây?**  
Không. Việc áp dụng phụ thuộc manager, provider, driver, DBMS và API truy cập dữ liệu; chúng không thay thế quyền DB và timeout của các hệ thống bên ngoài.

**8. Tại sao TransactionalOperator không tự gom các lệnh JdbcTemplate vào R2DBC transaction?**  
Vì reactive transaction được truyền bằng Reactor Context qua ReactiveTransactionManager, còn JDBC blocking thường dùng thread-bound Connection do PlatformTransactionManager quản lý.

## 14. Kết luận và nguyên tắc thực hành

- **Chọn đúng manager trước:** JDBC → JdbcTransactionManager/DataSourceTransactionManager; JPA → JpaTransactionManager; JTA/XA → JtaTransactionManager; R2DBC → R2dbcTransactionManager.
- **Đặt ranh giới ở đơn vị nghiệp vụ:** @Transactional cho service qua proxy hoặc template/operator cho luồng có yêu cầu programmatic.
- **Propagation quyết định quan hệ giao dịch:** REQUIRED dùng chung physical transaction, REQUIRES_NEW tách độc lập, NESTED dùng savepoint khi được hỗ trợ.
- **Isolation và rollback là chính sách:** Spring yêu cầu, DBMS thực thi; rollback rule phải xét ngoại lệ thực sự thoát ra hoặc rollback-only.
- **Một annotation không giải quyết phân tán:** nhiều DB, API, message cần coordinator phù hợp hoặc kiến trúc eventual consistency.
- **Kiểm chứng bằng trạng thái DB sau khi transaction kết thúc**, đồng thời quan sát đúng manager, connection, propagation và commit/rollback trong log.

## Tài liệu tham khảo

- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring – Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring – Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
