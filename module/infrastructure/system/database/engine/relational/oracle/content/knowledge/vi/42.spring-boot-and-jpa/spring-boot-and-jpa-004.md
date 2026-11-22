# Khởi tạo và đặt lại NLS/application context khi tái sử dụng kết nối trong Spring Boot và JPA

## 1. Vì sao phải quản lý session state khi dùng connection pool?

Trong ứng dụng Spring Boot, Hibernate/JPA thường lấy connection từ connection pool thay vì tạo một kết nối vật lý mới cho từng request. Pool giữ các connection đã mở để tái sử dụng, giúp giảm chi phí TCP handshake, xác thực Oracle session và khởi tạo driver.

Một connection được trả về pool thường vẫn gắn với cùng Oracle session. Những trạng thái được đặt ở cấp session có thể còn tồn tại khi request tiếp theo mượn lại connection đó, chẳng hạn:

- NLS settings như `NLS_DATE_FORMAT`, `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_LANGUAGE`, `NLS_SORT`.
- Application context dùng cho VPD/row-level security.
- `CLIENT_IDENTIFIER`, `MODULE`, `ACTION` phục vụ audit và tracing.
- `CURRENT_SCHEMA`, time zone, isolation-related session settings.
- Package state, global temporary table state và các thiết lập session khác.

Nếu request của tenant A đặt `TENANT_ID = 10`, sau đó trả connection về pool mà không xóa context, request của tenant B có thể nhận lại đúng Oracle session đó. Khi VPD policy đọc context cũ, B có thể nhìn thấy dữ liệu của A hoặc request bị từ chối ngoài dự kiến.

NLS state cũng có thể gây lỗi khó phát hiện. Một request đặt `NLS_DATE_FORMAT` theo định dạng riêng rồi trả connection về pool; request tiếp theo có thể chuyển chuỗi ngày hoặc số theo một quy tắc khác với quy tắc ứng dụng mong đợi.

Vì vậy, vòng đời một lần mượn connection cần có ba bước:

1. **Initialize:** áp dụng NLS baseline và thiết lập application context phù hợp với danh tính đã xác thực.
2. **Use:** thực hiện toàn bộ SQL/JPA work trên chính connection/session đó.
3. **Reset:** xóa context và đưa session về trạng thái baseline trước khi connection được tái sử dụng.

Bài học thuộc module **Database Engine Relational Oracle**, chương **Spring Boot và JPA**, tập trung vào **khởi tạo và đặt lại NLS/application context khi tái sử dụng kết nối**.

## 2. Connection, Oracle session và persistence context là ba khái niệm khác nhau

Cần phân biệt các lớp trạng thái:

| Thành phần | Phạm vi sống | Ví dụ trạng thái |
|---|---|---|
| JDBC logical connection | Lần ứng dụng mượn connection từ pool | `close()` thường trả connection về pool |
| Physical connection | Kết nối mạng do pool quản lý | Socket, driver state, Oracle session |
| Oracle database session | Session phía database được physical connection duy trì | NLS, application context, module/action, package state |
| JPA persistence context | Vòng đời `EntityManager`/transaction theo cấu hình | Managed entities, dirty checking, first-level cache |
| HTTP request | Một request ở tầng web | Principal, tenant, correlation ID |

Một HTTP request không nhất thiết tương ứng một physical connection mới. Một `EntityManager` cũng không nên được hiểu là một Oracle session luôn mới. Spring transaction manager có thể bind một connection vào transaction và các repository/JdbcTemplate cùng dùng lại connection đó.

### 2.1. `Connection.close()` trong pool không nhất thiết đóng Oracle session

Khi code gọi:

```java
connection.close();
```

với connection do pool cung cấp, thường chỉ logical connection được đóng và trả về pool. Physical connection cùng Oracle session có thể vẫn tồn tại.

Đó là lý do session state có thể rò sang lần mượn tiếp theo. Rollback transaction hoặc đóng `EntityManager` không tự động khôi phục mọi NLS parameter và application context về baseline.

### 2.2. Transaction state khác session state

`COMMIT` và `ROLLBACK` kết thúc transaction. Chúng không tự động xóa:
- Application context đã set trong session.
- `ALTER SESSION` settings.
- `CLIENT_IDENTIFIER`.
- `MODULE`/`ACTION`.
- Một số package state hoặc session setting khác.

Vì vậy, không thể dùng `finally { connection.rollback(); }` như một giải pháp reset session đầy đủ.

## 3. NLS settings ảnh hưởng đến ứng dụng như thế nào?

NLS (National Language Support) kiểm soát một số quy tắc ngôn ngữ, định dạng và so sánh trong Oracle session.

Các tham số thường gặp:

| Parameter | Ảnh hưởng |
|---|---|
| `NLS_DATE_FORMAT` | Format mặc định khi chuyển DATE sang chuỗi và ngược lại |
| `NLS_TIMESTAMP_FORMAT` | Format mặc định cho TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Format cho TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Tên tháng/ngày và một số quy tắc ngôn ngữ |
| `NLS_NUMERIC_CHARACTERS` | Dấu thập phân và dấu phân nhóm |
| `NLS_CURRENCY` | Ký hiệu tiền tệ mặc định |
| `NLS_TERRITORY` | Một số quy tắc vùng như ngày đầu tuần và định dạng mặc định |
| `NLS_SORT` | Quy tắc sắp xếp chuỗi |
| `NLS_COMP` | Cách áp dụng quy tắc so sánh theo NLS |

NLS có thể ảnh hưởng câu SQL sử dụng implicit conversion, hàm `TO_CHAR`/`TO_DATE` không có format model, sort/filter chuỗi và kết quả trả về từ một số API.

### 3.1. Ví dụ lỗi do NLS_DATE_FORMAT

Giả sử một session có:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
```

Câu SQL sau phụ thuộc session:

```sql
SELECT *
FROM app.orders
WHERE order_date >= '04/05/2026';
```

Chuỗi ngày có thể được hiểu theo định dạng tháng/ngày khác nhau nếu session có NLS khác. Điều này gây lỗi hoặc trả sai tập hàng.

Nên dùng bind parameter kiểu DATE/TIMESTAMP hoặc format model tường minh:

```sql
SELECT *
FROM app.orders
WHERE order_date >= DATE '2026-05-04';
```

Nếu cần parse chuỗi:

```sql
SELECT TO_DATE(
    '2026-05-04',
    'YYYY-MM-DD'
)
FROM dual;
```

Đặt NLS baseline giúp hành vi nhất quán cho legacy SQL, nhưng không thay thế typed bind variable và format model rõ ràng.

### 3.2. Ví dụ lỗi do NLS_NUMERIC_CHARACTERS

Một session có thể dùng dấu phẩy làm dấu thập phân:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

Nếu ứng dụng dựng SQL bằng chuỗi số, giá trị `1234.56` có thể được diễn giải khác tùy NLS.

Dùng JDBC bind số:

```java
preparedStatement.setBigDecimal(1, new BigDecimal("1234.56"));
```

Bind `BigDecimal` tránh chuyển số qua chuỗi SQL phụ thuộc locale.

### 3.3. Không dùng format hiển thị làm hợp đồng dữ liệu

NLS nên được xem là trạng thái session ảnh hưởng đến SQL và hiển thị, không phải định nghĩa dữ liệu nghiệp vụ. API nên truyền ngày/giờ và số bằng kiểu dữ liệu hoặc format invariant. UI mới quyết định format theo locale người dùng.

## 4. Xác định NLS baseline cho ứng dụng

Ứng dụng nên chọn một baseline thống nhất, được kiểm thử với SQL, báo cáo và dữ liệu thực tế. Ví dụ:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF';
ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET NLS_SORT = 'BINARY';
ALTER SESSION SET NLS_COMP = 'BINARY';
ALTER SESSION SET TIME_ZONE = 'UTC';
```

Các giá trị chỉ là ví dụ. Chọn time zone, language, sort và numeric characters theo hợp đồng ứng dụng. Không áp dụng `NLS_SORT=BINARY` hoặc `UTC` một cách máy móc nếu nghiệp vụ cần quy tắc khác.

### 4.1. NLS baseline phải được áp dụng nhất quán

Nếu một số connection dùng baseline A và số khác dùng baseline B, cùng một câu SQL có thể cho kết quả khác nhau tùy connection được pool cấp. Điều này đặc biệt nguy hiểm khi lỗi chỉ xuất hiện ngẫu nhiên dưới tải.

Cần một thành phần duy nhất quản lý baseline:
- Hằng số cấu hình được version control.
- Một service/helper thực hiện `ALTER SESSION`.
- Test xác nhận session state sau initialize/reset.
- Monitoring để phát hiện cấu hình không đúng.

### 4.2. Chỉ đưa giá trị tin cậy vào ALTER SESSION

Không nối trực tiếp locale, format model hoặc timezone do request gửi vào SQL:

```java
// Không an toàn nếu format đến từ input không tin cậy.
statement.execute("ALTER SESSION SET NLS_DATE_FORMAT = '" + userValue + "'");
```

`ALTER SESSION` không nhận bind variable cho mọi thành phần cấu hình. Dùng allowlist các giá trị đã định nghĩa trong application configuration và không cho client tự chọn SQL fragment.

### 4.3. Đọc NLS hiện tại

Có thể xem các tham số session:

```sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
```

So sánh với database defaults:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_LANGUAGE',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

`NLS_SESSION_PARAMETERS` cho biết trạng thái session hiện tại. Không giả định nó luôn giống `NLS_DATABASE_PARAMETERS` hoặc cấu hình client.

## 5. Application context và bảo mật theo session

Application context là tập thuộc tính gắn với Oracle session, được đọc bằng `SYS_CONTEXT`. Ứng dụng có thể dùng context để truyền thông tin bảo mật hoặc nghiệp vụ cho VPD policy, auditing và stored procedure.

Ví dụ namespace `APP_CTX`:
- `TENANT_ID`
- `APP_USER_ID`
- `REGION_ID`
- `BUSINESS_UNIT`

Đọc context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id,
       SYS_CONTEXT('APP_CTX', 'APP_USER_ID') AS app_user_id
FROM dual;
```

Nếu context được VPD policy sử dụng, giá trị sai hoặc còn sót từ request trước có thể gây rò dữ liệu giữa tenant.

### 5.1. Secure application context

Nên tạo secure application context bằng `CREATE CONTEXT ... USING package`:

```sql
CREATE CONTEXT app_ctx USING sec.app_session_context_pkg;
```

Package được chỉ định là trusted package có quyền thiết lập context qua `DBMS_SESSION.SET_CONTEXT`.

Ví dụ API package:

```sql
CREATE OR REPLACE PACKAGE sec.app_session_context_pkg
AUTHID DEFINER
AS
    PROCEDURE initialize_for_session;
    PROCEDURE clear_for_session;
END;
/
```

Phần thân package phải xác định danh tính từ nguồn tin cậy rồi mới thiết lập context. Ví dụ mô hình mỗi database principal có mapping tenant:

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_session_context_pkg
AS
    PROCEDURE initialize_for_session
    IS
        l_tenant_id NUMBER;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username =
              SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(-20001, 'No tenant mapping');
    END initialize_for_session;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END clear_for_session;
END;
/
```

Đây là ví dụ cho kiến trúc có database principal được ánh xạ rõ ràng. Tùy phiên bản và cơ chế context, DBA cần xác nhận cách clear namespace phù hợp; package trusted có thể dùng API clear context tương ứng cho toàn bộ attribute của session.

### 5.2. Không tin tenant ID do client tự gửi

Nếu mọi request dùng chung một database account, `SESSION_USER` chỉ nhận diện service account. Không thể suy ra end user hoặc tenant chỉ từ giá trị đó.

Trong kiến trúc shared account, cần một cơ chế identity tin cậy như proxy authentication hoặc assertion được xác minh ở trusted tier/package. Không dùng `CLIENT_IDENTIFIER` hoặc một tham số `tenant_id` do caller tự truyền làm bằng chứng phân quyền nếu caller có thể tự đặt giá trị đó.

Secure context giới hạn package nào được set context; nó không tự chứng minh logic bên trong package là đúng.

### 5.3. Fail closed

Nếu không xác thực được danh tính hoặc không tìm thấy tenant mapping:
- Không thiết lập context giả định.
- Xóa context cũ nếu có.
- Báo lỗi và dừng request.
- VPD policy nên trả predicate không cho phép hàng nào khi context thiếu, ví dụ `1=0`.

Không để request tiếp tục với context cũ hoặc predicate mặc định cho phép tất cả dữ liệu.

## 6. Vì sao connection pool làm session context trở nên nguy hiểm?

Giả sử pool có một physical connection:

```text
Request A (tenant 10)
    |
    v
Borrow connection C1
    |
    v
Set APP_CTX.TENANT_ID = 10
    |
    v
Query VPD-protected tables
    |
    v
Return C1 without clearing context
    |
    v
Request B (tenant 20) borrows C1
    |
    v
Context still says TENANT_ID = 10
```

Nếu B không set context trước query, VPD có thể lọc dữ liệu theo tenant 10. Nếu ứng dụng tự đặt tenant context bằng cách không an toàn, B có thể vô tình hoặc cố ý đổi sang tenant khác.

### 6.1. Hai nguyên tắc bắt buộc

- **Set lại context ở mỗi lần mượn/transaction request:** không dựa vào giá trị còn lại từ connection trước.
- **Clear/reset trước khi trả connection:** bảo đảm request sau không thừa hưởng trạng thái bảo mật trước.

Set mới mỗi lần giúp tránh context cũ trong trường hợp cleanup trước đó thất bại. Clear khi kết thúc giảm rủi ro và giúp phát hiện lỗi sớm. Nếu initialize hoặc reset không thành công, không được tiếp tục dùng connection như bình thường.

### 6.2. NLS cũng cần reset

NLS settings thường không thay đổi theo tenant nhưng có thể thay đổi theo request, báo cáo hoặc legacy code. Nếu một request tự chạy `ALTER SESSION`, phải khôi phục baseline trước khi connection được tái sử dụng.

Không dựa vào `ROLLBACK` để reset NLS. `ALTER SESSION` là thay đổi session state.

## 7. Phân biệt connectionInitSql với reset mỗi lần borrow

Một số pool cho phép chạy SQL khi physical connection mới được tạo. Với HikariCP, thuộc tính `connectionInitSql` được thực hiện khi một connection mới được tạo trước khi đưa vào pool.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  datasource:
    hikari:
      connection-init-sql: >
        ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'
```

Cấu hình này có thể đặt baseline ban đầu cho physical connection. Nhưng nó **không chạy lại mỗi lần một request mượn connection từ pool**.

Nếu request thay đổi NLS hoặc application context, request tiếp theo vẫn có thể nhận session đã bị thay đổi. Vì vậy:
- `connectionInitSql` hữu ích cho baseline ban đầu.
- Nó không thay thế checkout initialization.
- Nó không thay thế reset khi connection được trả về.
- Không nên đặt tenant-specific context ở đây vì physical connection được tái sử dụng cho nhiều tenant.

### 7.1. Pool không tự reset mọi Oracle session state

Pool thường có thể reset một số JDBC state chuẩn như auto-commit, read-only hoặc transaction isolation tùy implementation. Những thay đổi bằng `ALTER SESSION`, `DBMS_SESSION.SET_CONTEXT`, package state, `CLIENT_IDENTIFIER` hoặc `DBMS_APPLICATION_INFO` không nhất thiết được pool phát hiện và reset tự động.

Không giả định `Connection.close()` sẽ xóa application context hoặc NLS state.

### 7.2. Validation query không phải reset hook

Một validation query như:

```sql
SELECT 1 FROM dual
```

chỉ kiểm tra connection có thể thực hiện truy vấn hay không. Nó không đặt lại NLS, không clear context và không chứng minh session sạch.

## 8. Thiết kế vòng đời session state

Một request dùng Oracle nên tuân theo trình tự:

```text
Borrow connection
      |
      v
Apply NLS baseline
      |
      v
Clear stale context and client metadata
      |
      v
Authenticate/resolve trusted application identity
      |
      v
Set secure application context
      |
      v
Execute JPA/JDBC work in same transaction connection
      |
      v
Flush pending JPA changes
      |
      v
Clear application context and request metadata
      |
      v
Restore NLS baseline
      |
      v
Return healthy connection to pool
```

Nếu bất kỳ bước initialize nào thất bại, không chạy SQL nghiệp vụ. Nếu cleanup thất bại, connection có thể còn trạng thái nhạy cảm; phải đánh dấu lỗi và evict/discard connection khỏi pool.

### 8.1. Khởi tạo trước truy vấn đầu tiên

VPD policy có thể được gọi khi SQL được parse hoặc thực thi theo policy type. Context phải sẵn sàng trước khi bất kỳ repository query nào chạy.

Không khởi tạo context sau khi đã gọi repository. Không chỉ set context trong controller nếu service khác, scheduled job hoặc message consumer có thể truy cập cùng repository mà bỏ qua controller.

### 8.2. Giữ cùng physical connection

Lệnh thiết lập context và truy vấn JPA phải chạy trên cùng Oracle session. Nếu set context trên connection C1 nhưng Hibernate query trên connection C2, policy không thấy context mong muốn.

Trong Spring-managed transaction, hãy dùng connection đã được transaction manager bind cho persistence context, thay vì tự mở connection độc lập qua `DriverManager` hoặc một `DataSource` khác.

### 8.3. Reset sau khi mọi SQL nghiệp vụ hoàn tất

Với JPA, entity có thể được flush xuống database khi transaction commit. Nếu xóa context quá sớm, thao tác flush hoặc SQL phát sinh muộn có thể chạy khi context đã bị xóa.

Có thể gọi `entityManager.flush()` trước khi reset trong một wrapper đồng bộ. Với giải pháp quản lý ở transaction lifecycle, cleanup nên chạy sau khi transaction đã hoàn thành nhưng trước khi connection được trả về pool. Cần xác nhận thứ tự lifecycle thực tế của transaction manager và pool đang dùng.

## 9. Cấu hình Spring Boot và HikariCP

Spring Boot thường cấu hình `DataSource` từ `spring.datasource.*`. Nếu dùng HikariCP, có thể cấu hình pool:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-host:1521/orders_service
    username: app_runtime
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
      connection-init-sql: >
        ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'
```

Các con số là ví dụ. `connection-timeout` là thời gian chờ lấy connection từ pool, không phải Oracle network connect timeout. `connection-init-sql` là SQL khởi tạo physical connection, không phải hook mỗi lần borrow.

Không đặt password thật trong file cấu hình được commit. Dùng environment/secret provider và quản lý quyền truy cập.

### 9.1. Không đặt application context tenant trong connection-init-sql

Physical connection có thể được tạo lúc startup rồi được nhiều request/tenant dùng lại. Nếu init SQL gắn tenant 10, mọi request sử dụng session đó có nguy cơ chạy với tenant sai.

Tenant/application context phải được thiết lập theo identity của request/transaction hiện tại.

### 9.2. Đừng dùng connectionTestQuery để thay initialization

HikariCP/driver có thể dùng JDBC `Connection.isValid()` hoặc validation query. Mục tiêu là kiểm tra connection còn hoạt động, không phải làm sạch session state.

### 9.3. Một DataSource duy nhất cho transaction

`JpaTransactionManager`, `EntityManagerFactory` và `JdbcTemplate` cần tham chiếu cùng datasource nếu muốn cùng tham gia một transaction và cùng session. Nếu cấu hình nhiều datasource, phải chỉ rõ transaction manager và persistence unit tương ứng.

## 10. Thiết lập context trong Spring Boot/JPA bằng Hibernate doWork

Với Hibernate, `Session.doWork()` cho phép thực hiện JDBC work trên connection mà Hibernate đang sử dụng. Trong transaction JPA đang hoạt động, đây là cách phù hợp để gọi package Oracle trên cùng session.

Ví dụ helper:

```java
@Component
public class OracleSessionStateManager {

    @PersistenceContext
    private EntityManager entityManager;

    public void initializeForRequest() {
        Session session = entityManager.unwrap(Session.class);

        session.doWork(connection -> {
            applyNlsBaseline(connection);
            clearRequestState(connection);
            callTrustedContextInitializer(connection);
        });
    }

    public void resetAfterRequest() {
        Session session = entityManager.unwrap(Session.class);

        session.doWork(connection -> {
            clearRequestState(connection);
            applyNlsBaseline(connection);
        });
    }

    private void applyNlsBaseline(Connection connection)
            throws SQLException {

        try (Statement statement = connection.createStatement()) {
            statement.execute(
                "ALTER SESSION SET NLS_DATE_FORMAT = " +
                "'YYYY-MM-DD HH24:MI:SS'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = " +
                "'YYYY-MM-DD HH24:MI:SS.FF'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'"
            );
            statement.execute(
                "ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN'"
            );
            statement.execute(
                "ALTER SESSION SET TIME_ZONE = 'UTC'"
            );
        }
    }

    private void clearRequestState(Connection connection)
            throws SQLException {

        try (CallableStatement call = connection.prepareCall(
                "{ call SEC.APP_SESSION_CONTEXT_PKG.CLEAR_FOR_SESSION }")) {
            call.execute();
        }

        try (CallableStatement call = connection.prepareCall(
                "{ call DBMS_SESSION.CLEAR_IDENTIFIER }")) {
            call.execute();
        }

        try (CallableStatement call = connection.prepareCall(
                "{ call DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL) }")) {
            call.execute();
        }
    }

    private void callTrustedContextInitializer(Connection connection)
            throws SQLException {

        try (CallableStatement call = connection.prepareCall(
                "{ call SEC.APP_SESSION_CONTEXT_PKG.INITIALIZE_FOR_SESSION }")) {
            call.execute();
        }
    }
}
```

Đây là skeleton minh họa. Cần điều chỉnh package, quyền, NLS baseline và cách clear context theo schema/version thực tế. Package `INITIALIZE_FOR_SESSION` phải lấy identity từ nguồn tin cậy; không thêm tham số tenant tùy ý do client gửi.

### 10.1. Vì sao dùng doWork?

`doWork()` nhận connection của Hibernate session hiện tại. Nhờ đó, lệnh `ALTER SESSION` và stored procedure context chạy trên cùng Oracle session với các query JPA tiếp theo trong transaction.

Không làm như sau trong service JPA:

```java
try (Connection connection = dataSource.getConnection()) {
    // Set context ở connection này...
}
```

Nếu transaction manager/Hibernate đang dùng connection khác, context vừa set không áp dụng cho query JPA. Ngoài ra, tự lấy connection có thể làm việc quản lý transaction và lifecycle khó đoán.

### 10.2. Dùng doReturningWork khi cần kết quả

Nếu cần trả một giá trị JDBC:

```java
String tenant = session.doReturningWork(connection -> {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') FROM dual");
         ResultSet resultSet = statement.executeQuery()) {

        return resultSet.next() ? resultSet.getString(1) : null;
    }
});
```

Chỉ dùng để đọc trạng thái/chẩn đoán cần thiết. Không đưa context nhạy cảm vào log.

## 11. Bao quanh service transaction bằng initialize/reset

Ví dụ service đồng bộ:

```java
@Service
public class OrderService {

    private final OracleSessionStateManager sessionStateManager;
    private final OrderRepository orderRepository;
    private final EntityManager entityManager;

    public OrderService(
            OracleSessionStateManager sessionStateManager,
            OrderRepository orderRepository,
            EntityManager entityManager) {
        this.sessionStateManager = sessionStateManager;
        this.orderRepository = orderRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public OrderSummary findOrdersForCurrentTenant() {
        sessionStateManager.initializeForRequest();

        try {
            List<Order> orders = orderRepository.findOpenOrders();

            // Bảo đảm các thay đổi JPA cần flush được gửi trước reset.
            entityManager.flush();

            return OrderSummary.from(orders);
        } finally {
            sessionStateManager.resetAfterRequest();
        }
    }
}
```

Ví dụ cho thấy nguyên tắc initialize trước query và reset trong `finally`. Production implementation cần xử lý trường hợp reset phát sinh exception: lỗi cleanup phải được ghi nhận, transaction không được tiếp tục như thành công nếu connection có thể còn context cũ, và connection phải được evict khỏi pool theo API của pool.

Nếu method chỉ đọc dữ liệu, `flush()` thường không cần thiết; với write transaction, flush trước reset giúp tránh Hibernate trì hoãn DML đến sau khi context đã bị xóa. Cần đánh giá các query/lazy loading phát sinh sau khi method trả về; không để database access tiếp tục sau khi session context đã được reset.

### 11.1. Không để cleanup exception bị nuốt

Không viết:

```java
try {
    sessionStateManager.resetAfterRequest();
} catch (Exception ignored) {
    // Không an toàn: session có thể còn tenant context cũ.
}
```

Nếu reset thất bại, connection có thể được trả về pool trong trạng thái bảo mật không xác định. Hãy:
- Đánh dấu request/transaction thất bại.
- Ghi metric và log kỹ thuật không chứa secret.
- Đánh dấu connection cần loại bỏ.
- Dùng pool-specific eviction hoặc cơ chế wrapper để không tái sử dụng physical connection.

### 11.2. Lưu ý về Spring proxy và @Transactional

`@Transactional` thường được áp dụng qua Spring proxy. Gọi một method transactional khác bằng self-invocation trong cùng object có thể bỏ qua proxy và transaction không được mở như dự kiến.

Đặt transaction boundary ở service bean phù hợp và kiểm tra transaction đang active trước khi gọi `Session.doWork()`.

### 11.3. Lazy loading

Nếu trả entity còn lazy association và truy cập association sau khi service đã reset context hoặc transaction đã kết thúc, SQL phát sinh có thể chạy ngoài phạm vi context dự kiến.

Ưu tiên fetch dữ liệu cần thiết trong transaction và trả DTO/projection. Không dựa vào Open Session in View để kéo dài một session có tenant context không được quản lý rõ ràng.

## 12. Dùng JdbcTemplate trong cùng transaction

`JdbcTemplate` của Spring dùng cơ chế quản lý connection của Spring. Nếu nó và JPA cùng dùng datasource được `JpaTransactionManager` quản lý, các thao tác có thể tham gia cùng transaction-bound connection theo cấu hình.

Ví dụ gọi package:

```java
@Repository
public class OracleSessionContextDao {

    private final JdbcTemplate jdbcTemplate;

    public OracleSessionContextDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void initialize() {
        jdbcTemplate.execute(
            "{ call SEC.APP_SESSION_CONTEXT_PKG.INITIALIZE_FOR_SESSION }"
        );
    }

    public void clear() {
        jdbcTemplate.execute(
            "{ call SEC.APP_SESSION_CONTEXT_PKG.CLEAR_FOR_SESSION }"
        );
    }
}
```

Gọi DAO trong cùng `@Transactional` service trước khi gọi JPA repository. Kiểm tra `JdbcTemplate`, `EntityManagerFactory` và transaction manager thực sự dùng cùng datasource.

### 12.1. Không mở connection riêng bên trong DAO

Dùng `DriverManager.getConnection()` hoặc datasource khác sẽ tạo session khác và có thể không tham gia transaction hiện tại. Với thao tác cần cùng session, dùng `JdbcTemplate`, `DataSourceUtils` hoặc Hibernate `doWork()`.

### 12.2. Chọn một cơ chế truy cập nhất quán

Có thể dùng:
- Hibernate `Session.doWork()` cho lệnh session-level cần connection hiện tại.
- `JdbcTemplate` cho stored procedure và SQL cùng transaction.
- Một DataSource wrapper để reset tự động khi logical connection được trả về pool.

Tránh trộn nhiều datasource/transaction manager mà không xác định rõ connection nào đang giữ context.

## 13. Reset bằng transaction lifecycle hoặc DataSource wrapper

Ví dụ `try/finally` ở service dễ hiểu và hữu ích khi mỗi transaction có một entry point rõ ràng. Với ứng dụng lớn có nhiều service, scheduled job và message listener, reset phân tán trong từng method dễ bị bỏ sót.

Có thể tập trung hóa quản lý ở một trong hai lớp:

### 13.1. Transaction synchronization

Spring cung cấp transaction synchronization callbacks. Có thể đăng ký cleanup sau khi transaction hoàn tất, trước khi transaction manager giải phóng resource theo đúng thứ tự lifecycle của cấu hình đang dùng.

Nguyên tắc:
- Initialize trên connection đang bound với transaction.
- Cleanup phải chạy sau khi JPA flush/commit hoặc rollback hoàn tất.
- Cleanup phải chạy trước khi connection được trả về pool.
- Nếu callback không thể truy cập đúng connection hoặc cleanup lỗi, connection phải bị evict.
- Không đăng ký callback trùng lặp cho cùng transaction.

Không sao chép callback mẫu mà chưa kiểm tra thứ tự `beforeCommit`, `afterCompletion`, Hibernate connection release và Spring transaction manager version. Thứ tự cụ thể cần được kiểm thử với stack thực tế.

### 13.2. DataSource/connection wrapper

Một wrapper quanh datasource có thể:
1. Khi `getConnection()` cấp logical connection, thực hiện baseline/reset và khởi tạo request context theo cơ chế được thiết kế.
2. Khi logical `close()` được gọi, chạy cleanup/reset trước khi delegate connection về pool.
3. Nếu cleanup thất bại, evict physical connection thay vì trả nó vào pool.

Wrapper phải phối hợp với transaction manager để không reset quá sớm khi transaction chưa flush/commit. Nó cũng cần phân biệt connection checkout dành cho request, background job và tác vụ không có tenant.

### 13.3. Chọn nơi đặt trách nhiệm

| Phương án | Phù hợp | Rủi ro cần quản lý |
|---|---|---|
| `try/finally` ở service | Số entry point ít, transaction rõ | Dễ quên ở service/job mới |
| Transaction synchronization | Muốn cleanup gắn với transaction lifecycle | Phụ thuộc thứ tự callback và connection release |
| DataSource wrapper/proxy | Muốn tập trung hóa mọi lần mượn/trả | Phức tạp với transaction, nested connection và pool |
| Pool connectionInitSql | Chỉ đặt baseline khi tạo physical connection | Không reset mỗi lần borrow |

Không dùng `connectionInitSql` như thể nó là wrapper checkout/return.

## 14. Background jobs, scheduler và message consumers

Không chỉ HTTP request mới cần context. Các luồng khác cũng có thể tái sử dụng connection:
- `@Scheduled` jobs.
- Spring Batch.
- Kafka/RabbitMQ message listeners.
- Async executor.
- ETL worker.
- Admin/reporting tasks.

Mỗi loại workload cần xác định context:
- Job chạy với service identity riêng.
- Message tenant được xác thực từ envelope/trusted producer.
- Scheduled task có thể chạy cross-tenant với role được phê duyệt hoặc chạy lần lượt theo tenant.
- Admin job cần identity đặc quyền riêng và audit.

Không để background worker kế thừa context từ request trước chỉ vì dùng chung pool.

### 14.1. Context của message không tự đáng tin

Một message body có `tenantId` không chứng minh sender được quyền xử lý tenant đó. Xác thực producer, chữ ký hoặc mapping với danh tính queue/consumer trước khi gọi package set context.

### 14.2. Tách service account và workload khi phù hợp

Dùng account/pool riêng cho batch, reporting và OLTP có thể giảm ảnh hưởng lẫn nhau và đơn giản hóa context policy. Tuy nhiên, mỗi pool vẫn cần quy trình initialize/reset.

## 15. NLS và application context trong nhiều datasource

Một ứng dụng có thể kết nối nhiều Oracle service hoặc nhiều PDB. Không giả định mọi datasource có cùng:
- NLS baseline.
- Package/context namespace.
- Schema mapping.
- Time zone.
- VPD policy.
- Transaction manager.

Mỗi datasource cần một cấu hình session state tương ứng và manager được gắn đúng `EntityManagerFactory`/transaction manager.

Ví dụ:
- `ordersDataSource` dùng `APP_CTX` và service `ORDERS`.
- `reportingDataSource` dùng context/read-only identity và service `REPORTING`.

Không gọi session initializer của datasource A trên connection của datasource B.

## 16. Kiểm tra session state trong Oracle

### 16.1. Kiểm tra NLS

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_LANGUAGE',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

### 16.2. Kiểm tra application context

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id,
       SYS_CONTEXT('APP_CTX', 'APP_USER_ID') AS app_user_id
FROM dual;
```

Khi connection vừa được reset, context cần trống hoặc ở trạng thái baseline được định nghĩa. Khi đã initialize cho request, context phải khớp identity đã xác thực.

### 16.3. Kiểm tra module/action/client identifier

Có thể xem session metadata qua dynamic performance views nếu có quyền, hoặc kiểm tra bằng package/application instrumentation. `CLIENT_IDENTIFIER` hữu ích để gắn session với request/user trong audit, nhưng không phải bằng chứng xác thực nếu caller tự set được.

### 16.4. Không log context nhạy cảm tùy tiện

Tenant ID hoặc user ID có thể là dữ liệu nhạy cảm theo policy tổ chức. Log mã request, module/action và identifier đã được phê duyệt; không log token hoặc assertion gốc.

## 17. Kiểm thử việc tái sử dụng connection

Test quan trọng nhất là chứng minh cùng physical connection được tái sử dụng mà trạng thái request trước không rò sang request sau.

### 17.1. Test tuần tự hai tenant

Với pool có một connection:
1. Request A mượn connection C1.
2. Initialize context tenant 10.
3. Query bảng có VPD; chỉ thấy tenant 10.
4. Reset context và NLS baseline.
5. Trả C1 về pool.
6. Request B mượn lại C1.
7. Initialize context tenant 20.
8. Query; chỉ thấy tenant 20.
9. Kiểm tra không còn `TENANT_ID=10`.

Nếu test không bảo đảm hai request dùng cùng physical connection, nó có thể bỏ lỡ lỗi leakage. Dùng pool size 1 trong test hoặc instrument connection/session identity trong môi trường kiểm thử.

### 17.2. Test context thiếu

Sau reset, chạy query VPD-protected trước khi initialize. Kết quả phải fail-closed hoặc không trả hàng theo policy đã thiết kế.

### 17.3. Test exception và rollback

- Request A set context rồi ném exception.
- Transaction rollback.
- Cleanup vẫn chạy.
- Request B mượn lại cùng connection.
- Context của A không còn.

### 17.4. Test cleanup thất bại

Mô phỏng package reset lỗi hoặc connection bị ngắt trong cleanup:
- Request phải được đánh dấu thất bại.
- Connection không được trả về pool như connection khỏe.
- Pool tạo physical connection thay thế.
- Request tiếp theo không nhận context cũ.

### 17.5. Test NLS

Một request cố ý đổi `NLS_DATE_FORMAT` hoặc `NLS_NUMERIC_CHARACTERS`, sau đó trả connection. Request tiếp theo kiểm tra `NLS_SESSION_PARAMETERS` và phải thấy baseline chuẩn.

### 17.6. Test concurrency

Chạy nhiều request tenant khác nhau đồng thời. Mỗi transaction phải thấy đúng context của connection đang dùng. Không chia sẻ một connection/JPA EntityManager giữa nhiều thread.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ set context khi physical connection được tạo | Tenant đầu tiên có thể bị dùng cho request sau | Set theo từng request/transaction |
| Dựa vào `connectionInitSql` để reset mọi lần borrow | Session state cũ còn nguyên | Có checkout/return lifecycle riêng |
| Nghĩ rollback xóa NLS/context | Request sau kế thừa trạng thái | Reset session rõ ràng |
| Set context trên connection riêng | JPA query dùng session khác | Dùng `Session.doWork()`/connection transaction-bound |
| Tin tenant ID từ HTTP body | Caller có thể giả mạo tenant | Resolve identity từ nguồn tin cậy |
| Dùng `CLIENT_IDENTIFIER` làm authorization | Giá trị có thể do caller set | Chỉ dùng tracing/audit trừ khi được xác thực |
| Cleanup chỉ ở đường thành công | Exception để lại context cũ | `finally` hoặc transaction cleanup callback |
| Nuốt lỗi reset | Connection nhạy cảm quay lại pool | Evict/discard connection |
| Reset trước JPA flush | DML muộn chạy thiếu context | Flush trước reset hoặc cleanup sau transaction completion |
| Chỉ test bằng nhiều connection khác nhau | Không phát hiện session leakage | Test pool size 1 và cùng physical session |
| Chỉ áp dụng cho HTTP controller | Job/message consumer bỏ qua context | Centralize ở transaction/session boundary |
| Dùng một baseline NLS tùy ý | Thay đổi semantics ứng dụng | Chốt baseline theo hợp đồng và test |
| Mở connection bằng DriverManager trong service JPA | Không cùng transaction/session | Dùng transaction-bound connection |
| Dùng Open Session in View để lazy load sau reset | Query phát sinh ngoài context dự kiến | Fetch trong transaction và trả DTO |

## 19. Checklist triển khai

### NLS
- Baseline được định nghĩa tập trung.
- Có format ngày, timestamp, số và timezone rõ ràng.
- Không nối NLS setting từ input không tin cậy.
- Không dựa vào implicit conversion trong SQL mới.
- NLS được kiểm tra sau initialize/reset.

### Application context
- Dùng secure application context.
- Trusted package xác thực identity trước khi set.
- Không tin tenant ID tùy ý từ client.
- Context được set trước query đầu tiên.
- Context được clear khi request/transaction kết thúc.
- Context thiếu dẫn đến fail-closed.

### Spring Boot/JPA
- `EntityManagerFactory`, transaction manager và `JdbcTemplate` dùng đúng datasource.
- Context được set trên connection Hibernate đang sử dụng.
- Có transaction boundary rõ ràng.
- JPA flush hoàn tất trước khi reset.
- Lazy loading không chạy sau khi context đã bị xóa.
- Scheduled jobs/message consumers có quy trình context riêng.

### Connection pool
- Hiểu `connectionInitSql` chỉ chạy khi tạo physical connection.
- Có reset ở checkout/return hoặc transaction lifecycle.
- Không giả định pool tự clear Oracle session state.
- Cleanup failure dẫn tới eviction.
- Không trả connection lỗi hoặc session state không xác định về pool.

### Kiểm thử và vận hành
- Test hai tenant trên cùng physical connection.
- Test context thiếu và exception/rollback.
- Test NLS leakage.
- Test cleanup failure và eviction.
- Có metrics cho initialize/reset failure.
- Log không chứa secret hoặc assertion nhạy cảm.
- Có runbook xử lý connection bị nhiễm session state.

## 20. Bài thực hành tổng hợp

Bài lab cần Oracle database riêng, schema thử nghiệm, Spring Boot/JPA, Oracle JDBC driver và HikariCP. Không chạy DDL hoặc thay đổi NLS/context trên pool production để thử nghiệm.

### Bước 1. Tạo bảng tenant mapping

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id NUMBER NOT NULL
);
```

Tạo dữ liệu mapping phù hợp với các database principal lab. Nếu lab dùng shared account, phải mô phỏng cơ chế identity tin cậy đã được phê duyệt; không lấy tenant tùy ý từ request.

### Bước 2. Tạo secure context và trusted package

```sql
CREATE CONTEXT app_ctx USING sec.app_session_context_pkg;
```

Tạo package có hai thủ tục:
- `INITIALIZE_FOR_SESSION`: xác thực identity và set tenant/application attributes.
- `CLEAR_FOR_SESSION`: clear toàn bộ context liên quan của session hiện tại.

Cấp `EXECUTE` cho runtime account ở mức tối thiểu.

### Bước 3. Tạo bảng nghiệp vụ và policy

Tạo bảng có `TENANT_ID` và VPD policy đọc `SYS_CONTEXT('APP_CTX','TENANT_ID')`. Khi context null, policy trả `1=0`.

### Bước 4. Cấu hình HikariCP

Đặt pool size 1 để dễ buộc hai request dùng lại cùng physical connection. Cấu hình `connectionInitSql` chỉ cho NLS baseline ban đầu, không đặt tenant context ở đó.

### Bước 5. Tạo OracleSessionStateManager

Dùng Hibernate `Session.doWork()` để:
- Áp NLS baseline.
- Clear stale context/identifier.
- Gọi trusted initializer.
- Reset context và NLS khi hoàn tất.

Nếu reset lỗi, đánh dấu connection để pool evict theo implementation đang dùng.

### Bước 6. Tạo service transactional

Trong một method `@Transactional`:
1. Initialize session.
2. Gọi repository query.
3. Xác nhận kết quả chỉ thuộc tenant hiện tại.
4. Flush nếu có DML.
5. Reset trước khi connection được trả về theo lifecycle đã chọn.

### Bước 7. Gửi hai request tenant khác nhau

Thực hiện request A rồi request B và xác nhận pool tái sử dụng cùng connection nhưng context thay đổi đúng. Kiểm tra `SYS_CONTEXT` và kết quả VPD.

### Bước 8. Kiểm tra exception path

Cho request A phát sinh exception sau khi initialize. Xác nhận rollback, cleanup và request B không nhận context A.

### Bước 9. Kiểm tra NLS

Trong request A, đổi một NLS parameter có kiểm soát. Sau cleanup, request B đọc `NLS_SESSION_PARAMETERS` và xác nhận baseline.

### Bước 10. Kiểm tra cleanup failure

Mô phỏng lỗi package reset trong môi trường lab. Xác nhận connection bị evict và pool tạo connection mới.

### Bước 11. Ghi kết quả

Ghi:
- Physical connection/session identity dùng trong từng request.
- NLS trước và sau reset.
- Context trước và sau initialize/clear.
- Transaction status.
- Cleanup result.
- Số connection bị evict.
- Kết quả truy vấn VPD.

### Bước 12. Dọn lab

Chỉ xóa các object do bài lab tạo và khi không còn cần. Không drop package/context hoặc policy được dùng chung bởi ứng dụng khác.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao application context có thể rò giữa hai request?

**Trả lời:** Vì context gắn với Oracle session, còn connection pool có thể tái sử dụng cùng physical connection/session cho request tiếp theo.

**Câu 2.** `Connection.close()` có luôn đóng Oracle session không?

**Trả lời:** Không. Với pool, nó thường trả logical connection về pool và physical session vẫn tồn tại.

**Câu 3.** Rollback có reset NLS không?

**Trả lời:** Không. NLS là session state và cần được reset riêng.

**Câu 4.** `connectionInitSql` của HikariCP chạy khi nào?

**Trả lời:** Khi physical connection mới được tạo trước khi đưa vào pool; nó không chạy lại mỗi lần borrow.

**Câu 5.** Vì sao không set tenant context trong `connectionInitSql`?

**Trả lời:** Physical connection có thể được tái sử dụng cho nhiều tenant; context phải theo identity của request/transaction hiện tại.

**Câu 6.** Secure application context được tạo thế nào?

**Trả lời:** Dùng `CREATE CONTEXT namespace USING trusted_package`; package tin cậy thiết lập context qua `DBMS_SESSION.SET_CONTEXT`.

**Câu 7.** Vì sao không tin tenant ID từ HTTP body?

**Trả lời:** Client có thể sửa giá trị để giả mạo tenant và vượt ranh giới dữ liệu.

**Câu 8.** `CLIENT_IDENTIFIER` có thay thế authentication không?

**Trả lời:** Không. Nó hữu ích cho audit/tracing nhưng không tự chứng minh danh tính nếu caller có thể tự set.

**Câu 9.** Vì sao dùng Hibernate `Session.doWork()`?

**Trả lời:** Nó thực hiện JDBC work trên connection của Hibernate session hiện tại, giúp context và JPA query dùng cùng Oracle session.

**Câu 10.** Vì sao cần reset trong finally hoặc transaction cleanup?

**Trả lời:** Để cleanup vẫn chạy khi request thành công, ném exception hoặc rollback.

**Câu 11.** Vì sao phải flush JPA trước khi reset trong một số thiết kế?

**Trả lời:** Hibernate có thể trì hoãn DML đến flush/commit; reset context sớm có thể làm SQL muộn chạy ngoài context dự kiến.

**Câu 12.** Khi cleanup thất bại thì sao?

**Trả lời:** Connection có thể còn trạng thái nhạy cảm; phải đánh dấu lỗi và evict/discard, không trả về pool như connection sạch.

**Câu 13.** Validation query có reset context không?

**Trả lời:** Không. Nó chỉ kiểm tra khả năng thực hiện truy vấn trên connection.

**Câu 14.** Background job có cần context không?

**Trả lời:** Có nếu truy cập dữ liệu được bảo vệ; job cần workload identity và quy trình initialize/reset riêng.

**Câu 15.** Vì sao cần test pool size 1?

**Trả lời:** Để buộc request kế tiếp dùng lại cùng physical connection và phát hiện session-state leakage.

**Câu 16.** Có thể dùng một baseline NLS cho mọi datasource không?

**Trả lời:** Chỉ khi mọi database/service có cùng hợp đồng nghiệp vụ; nếu khác, mỗi datasource cần cấu hình session state riêng.

## 22. Kết luận

Connection pool tái sử dụng physical connection và Oracle session để giảm chi phí kết nối. Điều đó đồng nghĩa session state có thể tồn tại qua nhiều request. NLS settings, application context, `CLIENT_IDENTIFIER`, module/action và các thiết lập session khác cần được quản lý như một phần của vòng đời connection.

Hãy định nghĩa NLS baseline rõ ràng, dùng typed bind và format model tường minh, đồng thời áp dụng baseline khi connection được sử dụng. Secure application context phải được thiết lập từ danh tính đã xác thực bởi trusted package; không tin tenant ID hoặc `CLIENT_IDENTIFIER` do client tự gửi. Context cần được set trước query đầu tiên và clear sau khi toàn bộ SQL nghiệp vụ hoàn tất.

Trong Spring Boot/JPA, lệnh thiết lập context phải chạy trên đúng connection mà Hibernate dùng. `Session.doWork()` hoặc `JdbcTemplate` tham gia cùng transaction là những cách phù hợp khi datasource và transaction manager được cấu hình thống nhất. `connectionInitSql` chỉ chạy khi physical connection được tạo, không thay thế reset mỗi lần borrow. Nếu cleanup thất bại, connection phải bị loại khỏi pool vì trạng thái bảo mật không còn xác định.

Kiểm thử bằng cách buộc hai request tenant khác nhau tái sử dụng cùng physical connection, kiểm tra NLS/context trước và sau reset, mô phỏng exception/rollback và cleanup failure. Chỉ khi request sau không thể kế thừa session state của request trước thì việc tái sử dụng connection mới an toàn cho ứng dụng Spring Boot và JPA.

