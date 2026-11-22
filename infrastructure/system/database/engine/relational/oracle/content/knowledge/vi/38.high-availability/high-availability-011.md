# Application Continuity, replay và những thao tác không an toàn để lặp

## 1. Vì sao cần Application Continuity?

Một ứng dụng có thể mất kết nối với Oracle Database trong lúc đang xử lý request. Nguyên nhân có thể là instance/node dừng, network bị gián đoạn, storage lỗi, service được relocate hoặc database thực hiện planned maintenance. Từ góc nhìn của ứng dụng, một lệnh SQL có thể đã được gửi nhưng response chưa quay về.

Tình huống nguy hiểm nhất là **không biết transaction đã COMMIT hay chưa**. Ví dụ:

1. Ứng dụng gửi lệnh ghi nhận thanh toán.
2. Database thực hiện COMMIT thành công.
3. Kết nối bị ngắt trước khi client nhận được response.
4. Ứng dụng chỉ thấy lỗi kết nối và không biết giao dịch đã hoàn tất.
5. Nếu ứng dụng gửi lại toàn bộ thao tác một cách mù quáng, khách hàng có thể bị ghi nhận thanh toán hai lần.

**Application Continuity (AC)** giúp che giấu nhiều lỗi có thể phục hồi bằng cách ghi nhận các database call trong một request, kết nối lại tới một database target hợp lệ và replay phần công việc cần thiết. Mục tiêu là đưa session và transaction về trạng thái tương đương để ứng dụng tiếp tục như thể request chỉ bị chậm.

Replay không phải là một cơ chế chạy lại mọi đoạn code của ứng dụng từ đầu. Oracle driver, database service và connection pool phối hợp để ghi nhận, khôi phục và kiểm tra các database call. Các logic ở middle tier, side effect bên ngoài database và những trạng thái không thể khôi phục vẫn cần được thiết kế cẩn thận.

## 2. Các khái niệm cốt lõi

### 2.1. Database request

Database request là một đơn vị công việc mà ứng dụng gửi tới Oracle trên một database connection. Một request thường tương ứng với SQL, PL/SQL và các database call phục vụ một HTTP request hoặc một thao tác nghiệp vụ.

Với connection pool, ranh giới request thường được xác định khi:

- Ứng dụng lấy connection từ pool (checkout/borrow).
- Ứng dụng thực hiện database work.
- Ứng dụng trả connection về pool (check-in/close).

Request boundary rất quan trọng vì Oracle cần biết phần call history nào thuộc một đơn vị công việc và thời điểm nào có thể giải phóng lịch sử đó.

### 2.2. Recoverable error

Recoverable error thường xuất phát từ lỗi hạ tầng hoặc kết nối độc lập với logic nghiệp vụ đang chạy, ví dụ mất kết nối, foreground/session bị lỗi, instance hoặc node dừng, network/storage outage.

Application Continuity chỉ xử lý các lỗi thuộc nhóm có thể phục hồi và khi request còn đáp ứng các điều kiện replay. Lỗi nghiệp vụ như dữ liệu đầu vào không hợp lệ, vi phạm constraint hoặc lỗi logic ứng dụng không tự động trở thành recoverable error chỉ vì driver đang bật AC.

### 2.3. Call history

Trong thời gian request được bảo vệ, replay driver ghi nhận database call và kết quả cần thiết để có thể tái lập session. Khi có recoverable error, driver dùng lịch sử này để xây dựng lại trạng thái và replay call theo thứ tự ban đầu.

Replay cần bảo đảm các kết quả mà ứng dụng đã nhìn thấy trước outage vẫn nhất quán. Nếu database trả về dữ liệu hoặc trạng thái khác với những gì ứng dụng đã sử dụng để ra quyết định, Oracle có thể từ chối replay thay vì tiếp tục với một trạng thái không an toàn.

### 2.4. Transaction Guard và commit outcome

Oracle có thể đã ghi redo của COMMIT bền vững nhưng client chưa nhận được response. Transaction Guard cung cấp transaction outcome có thể tra cứu sau outage, dùng Logical Transaction ID (LTXID) để nhận diện transaction.

Khi COMMIT_OUTCOME được bật trên service, outcome của COMMIT được lưu giữ trong khoảng thời gian retention cấu hình. Application Continuity sử dụng Transaction Guard để biết transaction cuối cùng đã commit thành công hay chưa, tránh gửi lại một transaction đã hoàn tất.

Đây là điểm khác biệt giữa replay có kiểm soát và việc ứng dụng tự retry một câu UPDATE/INSERT sau lỗi kết nối.

## 3. Application Continuity hoạt động qua những giai đoạn nào?

~~~text
Ứng dụng gửi database request
             |
             v
       NORMAL RUNTIME
       - xác định request boundary
       - ghi nhận database calls
       - theo dõi session/transaction state
             |
             v
       RECOVERABLE ERROR
       - session hoặc connection mất
             |
             v
       RECONNECTION
       - driver nhận diện lỗi có thể phục hồi
       - tìm connection tới service/target hợp lệ
       - Transaction Guard kiểm tra commit outcome
       - khôi phục session state cần thiết
             |
             v
       REPLAY
       - replay call history theo thứ tự
       - xác thực kết quả và trạng thái
       - từ chối nếu không thể khôi phục an toàn
             |
       +-----+------+
       |            |
       v            v
    SUCCESS       REJECT/FAIL
       |            |
       v            v
  Request tiếp   Ứng dụng nhận lỗi
  tục từ điểm    và xử lý fallback
  phù hợp
~~~

### 3.1. Normal runtime

Trong lúc chạy bình thường, driver nhận diện request, ghi nhận call history và theo dõi trạng thái session. Với AC, request boundary thường phải được xác định rõ. Với Transparent Application Continuity, state tracking có thể phát hiện các ranh giới request ngầm trong những điều kiện phù hợp.

### 3.2. Reconnection

Khi gặp recoverable error, driver tìm connection mới tới một target hợp lệ của service. Target phải thuộc cấu hình HA được hỗ trợ và có thể cung cấp trạng thái dữ liệu phù hợp.

Nếu transaction cuối cùng có thể đã COMMIT, Transaction Guard giúp xác định outcome trước khi replay để tránh thực thi lại một transaction đã commit.

### 3.3. Replay

Driver phát lại các database call đã ghi nhận theo trình tự cần thiết. Oracle kiểm tra session state và các kết quả đã quan sát. Nếu replay thành công, ứng dụng có thể tiếp tục request. Nếu replay không thể tái lập kết quả mà client đã dựa vào, replay bị từ chối và ứng dụng nhận lỗi để xử lý.

### 3.4. AC không loại bỏ error handling

Ứng dụng vẫn phải xử lý:

- Lỗi không thể phục hồi, chẳng hạn dữ liệu đầu vào sai.
- Request bị từ chối replay vì kết quả hoặc session state không thể khôi phục.
- Timeout vượt quá replay initiation timeout.
- Hết thời gian chờ hoặc không có target phù hợp.
- Side effect bên ngoài đã xảy ra nhưng transaction database chưa hoàn tất.
- Lỗi từ hệ thống bên ngoài, message broker hoặc payment provider.

Không thiết kế ứng dụng với giả định rằng bật AC đồng nghĩa không bao giờ nhận lỗi.

## 4. Application Continuity và Transparent Application Continuity

Oracle 19c có hai chế độ chính cần phân biệt:

- **Application Continuity (AC):** chế độ replay được cấu hình tường minh; service thường đặt FAILOVER_TYPE = TRANSACTION.
- **Transparent Application Continuity (TAC):** chế độ dùng state tracking để tự động nhận diện và quản lý session state; service đặt FAILOVER_TYPE = AUTO.

| Tiêu chí | Application Continuity | Transparent Application Continuity |
| --- | --- | --- |
| Service attribute | TRANSACTION | AUTO |
| Cách quản lý state | Dựa trên cấu hình, callback và các trạng thái ứng dụng đã biết | Theo dõi và phân loại session/transaction state tự động |
| Request boundary | Bắt buộc cho AC | Được khuyến nghị; có thể phát hiện implicit boundary trong điều kiện hỗ trợ |
| Side effect của ứng dụng | Các call được replay theo history; side effect cần được đánh giá và có thể phải disable replay | State tracking nhận diện một số side effect ứng dụng và tắt capture/replay cho call liên quan |
| Mức hiểu biết ứng dụng | Thường cần hiểu session state và các call có side effect | Giảm nhu cầu hiểu sâu ứng dụng nhờ state tracking |
| Session state consistency | DYNAMIC hoặc STATIC theo thiết kế manual AC | AUTO là chế độ bắt buộc |
| Phù hợp | Ứng dụng đã được đánh giá, có request boundaries và replay behavior rõ | Ứng dụng muốn theo dõi state tự động và giảm thay đổi code |

TAC không có nghĩa mọi side effect ở mọi hệ thống bên ngoài đều tự động trở nên an toàn. Ứng dụng vẫn phải kiểm thử hành vi với các callout, database link, autonomous transaction và tích hợp ngoài database theo đúng phiên bản driver/service đang dùng.

### 4.1. Cấu hình service cho AC

Ví dụ minh họa với Oracle RAC:

~~~text
srvctl add service -db mydb -service app_ac
  -preferred inst1 -available inst2
  -failovertype TRANSACTION
  -failover_restore LEVEL1
  -commit_outcome TRUE
  -notification TRUE
  -drain_timeout 300
  -stopoption IMMEDIATE
~~~

### 4.2. Cấu hình service cho TAC

~~~text
srvctl add service -db mydb -service app_tac
  -preferred inst1 -available inst2
  -failovertype AUTO
  -failover_restore AUTO
  -commit_outcome TRUE
  -notification TRUE
  -drain_timeout 300
  -stopoption IMMEDIATE
~~~

Đây là ví dụ minh họa, không phải lệnh copy nguyên xi cho mọi database. Cần xác định admin-managed hay policy-managed database, PDB, role PRIMARY/STANDBY, service hiện có và cú pháp SRVCTL đúng với Grid Infrastructure đang dùng.

### 4.3. Single-instance database

Với database không dùng RAC, có thể quản lý service qua DBMS_SERVICE. Ví dụ ý tưởng cấu hình TAC:

~~~sql
DECLARE
    params DBMS_SERVICE.SVC_PARAMETER_ARRAY;
BEGIN
    params('FAILOVER_TYPE') := 'AUTO';
    params('FAILOVER_RESTORE') := 'AUTO';
    params('COMMIT_OUTCOME') := 'TRUE';
    params('AQ_HA_NOTIFICATIONS') := 'TRUE';
    params('REPLAY_INITIATION_TIMEOUT') := 600;
    params('RETENTION_TIMEOUT') := 86400;

    DBMS_SERVICE.MODIFY_SERVICE(
        service_name => 'APP_TIER_SERVICE',
        params       => params
    );
END;
/
~~~

Tên service phải tồn tại và người chạy cần quyền quản trị phù hợp. Kiểm tra tài liệu DBMS_SERVICE và service attributes cho đúng release.

### 4.4. Các thuộc tính service quan trọng

| Thuộc tính | Vai trò |
| --- | --- |
| FAILOVER_TYPE | TRANSACTION cho AC, AUTO cho TAC |
| FAILOVER_RESTORE | Khôi phục session state; LEVEL1 thường dùng với AC, AUTO với TAC |
| COMMIT_OUTCOME | Bật khả năng truy vấn commit outcome của Transaction Guard |
| RETENTION_TIMEOUT | Thời gian giữ thông tin cần cho replay/commit outcome theo cấu hình |
| REPLAY_INITIATION_TIMEOUT | Giới hạn thời gian bắt đầu replay sau lỗi |
| FAILOVER_DELAY / FAILOVER_RETRIES | Điều khiển retry/failover theo cấu hình service |
| AQ_HA_NOTIFICATIONS / notification | Hỗ trợ FAN/HA notification cho client/pool |
| DRAIN_TIMEOUT / STOP_OPTION | Điều khiển drain khi bảo trì service |

Giá trị cần chọn theo SLA, thời gian outage dự kiến, pool behavior và thời gian request. Không đặt timeout quá ngắn khiến replay bị dừng trước khi target mới sẵn sàng; cũng không kéo dài vô hạn khiến request treo quá SLA.

## 5. Request boundary: ranh giới quyết định phạm vi replay

### 5.1. Vì sao cần request boundary?

Oracle cần biết call history bắt đầu và kết thúc ở đâu. Nếu một connection được dùng cho nhiều request nhưng ranh giới không rõ, history có thể quá lớn hoặc chứa các thao tác không thuộc cùng một đơn vị công việc.

Với AC, request boundary là yêu cầu quan trọng. Khi dùng Oracle connection pool như UCP hoặc OCI Session Pool, boundary thường được tích hợp ở thời điểm lấy và trả connection.

### 5.2. JDBC beginRequest và endRequest

Oracle JDBC cung cấp API rõ ràng:

~~~java
import java.sql.Connection;
import oracle.jdbc.OracleConnection;

Connection connection = dataSource.getConnection();
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

oracleConnection.beginRequest();

try {
    // Các JDBC calls thuộc cùng một database request.
    // Thực hiện transaction và xử lý lỗi theo ứng dụng.
} finally {
    // Trước endRequest, phải kết thúc transaction:
    // COMMIT hoặc ROLLBACK theo kết quả nghiệp vụ.
    oracleConnection.endRequest();
    connection.close();
}
~~~

Đoạn code là khung minh họa. Trong ứng dụng thực tế, không đặt COMMIT vô điều kiện trong finally. Quyết định COMMIT/ROLLBACK phải dựa trên trạng thái nghiệp vụ và kết quả Transaction Guard khi cần.

Oracle JDBC báo lỗi nếu beginRequest hoặc endRequest được gọi khi local transaction vẫn đang mở. Không gọi endRequest để che giấu một transaction chưa được xử lý.

### 5.3. Connection pool

Với UCP/WebLogic pool, request thường bắt đầu khi lấy connection và kết thúc khi trả connection. Vì vậy:

- Lấy connection ở đầu đơn vị công việc.
- Không giữ connection qua nhiều request độc lập nếu không có lý do rõ ràng.
- Đóng/return connection đúng thời điểm.
- Không dùng connection đã lỗi hoặc đã bị pool loại bỏ.
- Để pool thực hiện reset/cleanup session theo cấu hình.

### 5.4. Implicit request boundary trong TAC

TAC có thể phát hiện ranh giới ngầm khi session ở trạng thái an toàn, chẳng hạn:

- Không còn object/cursor đang mở ngoài các điều kiện hỗ trợ.
- Cursor đã được trả về statement cache.
- Không có transaction đang mở.
- Session state đã được xác định là có thể khôi phục.

Implicit boundary giảm nhu cầu sửa ứng dụng, nhưng không thay thế việc quản lý connection và session state đúng cách.

## 6. Những thao tác không an toàn để replay

Điểm quan trọng của replay là database call có thể được thực thi lại sau lỗi. Một thao tác an toàn phải giữ được semantics khi được replay, hoặc phải được phát hiện và không replay.

### 6.1. Gọi hệ thống bên ngoài: email, HTTP, TCP, file

Các ví dụ thường gặp:

- UTL_SMTP, UTL_MAIL: gửi email.
- UTL_HTTP, UTL_URL: gọi endpoint hoặc truy cập website.
- UTL_FILE: ghi file.
- UTL_FILE_TRANSFER: chuyển file.
- UTL_TCP: gửi dữ liệu qua TCP.
- DBMS_PIPE, DBMS_ALERT: giao tiếp/notification.
- DBMS_FILE_TRANSFER: copy file.
- Java callout, Process.exec hoặc gọi shell script.
- Ghi external table hoặc gọi dịch vụ bên ngoài.

Các hành động này có thể tạo side effect bền vững bên ngoài transaction database. Ví dụ:

1. Procedure gửi email thành công.
2. Transaction database chưa COMMIT.
3. Session mất do outage.
4. Oracle replay procedure.
5. Email được gửi lần thứ hai.

ROLLBACK database không thể thu hồi email đã gửi hoặc file đã chuyển. Vì vậy, side effect bên ngoài là nhóm rủi ro lớn nhất khi replay.

### 6.2. Autonomous transaction

Procedure có PRAGMA AUTONOMOUS_TRANSACTION có transaction độc lập với transaction gọi nó. Nếu autonomous transaction COMMIT log/audit rồi transaction chính gặp lỗi và được replay, phần audit độc lập có thể được ghi lần nữa.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit(p_message VARCHAR2) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Nếu procedure này được gọi trong request replay, audit row có thể được tạo nhiều lần tùy chế độ replay và cách xử lý side effect. Đừng mặc định autonomous transaction được rollback cùng transaction chính.

### 6.3. Ghi file hoặc gửi message ngoài database

Một file đã được ghi ra filesystem hoặc một message đã được gửi vào hệ thống ngoài có thể vẫn tồn tại khi transaction Oracle rollback.

Nếu cần xử lý một side effect:

- Gắn một business event ID duy nhất.
- Dùng idempotency key nếu API bên ngoài hỗ trợ.
- Kiểm tra trạng thái trước khi gửi lại.
- Lưu yêu cầu gửi trong transactional outbox.
- Cho worker riêng gửi message sau commit.
- Ghi nhận kết quả gửi và retry theo chính sách của hệ thống nhận.

Không dựa vào việc replay driver sẽ tự làm cho email, HTTP request hoặc file write trở thành exactly-once.

### 6.4. Đồng bộ nhiều session bằng lock hoặc tài nguyên volatile

Ứng dụng có thể dùng database lock, DBMS_LOCK, pipe, queue trong bộ nhớ, semaphore, socket hoặc một tài nguyên volatile để đồng bộ nhiều session/data source.

Nếu session A giữ lock để bảo đảm session B không sửa dữ liệu, nhưng A bị failover và lock bị mất, replay của A không tự biết rằng session B đã dựa vào lock cũ. Tình huống này có thể phá vỡ giả định độc quyền của ứng dụng.

Không bật replay cho ứng dụng nếu tính đúng đắn phụ thuộc vào nhiều session độc lập giữ tài nguyên volatile xuyên suốt outage mà không có cơ chế tái đồng bộ.

### 6.5. Dựa vào đồng hồ của middle tier

Driver replay database call history, không chạy lại logic thời gian của middle tier.

Ví dụ không an toàn:

~~~java
if (Instant.now().isBefore(deadline)) {
    updateOrder();
}
~~~

Giả sử request bắt đầu trước deadline, outage kéo dài qua deadline, database call được replay sau deadline. Phần logic Instant.now() không được driver tự chạy lại, trong khi database call vẫn có thể được replay. Kết quả có thể khác giả định của ứng dụng.

Giải pháp:

- Đưa điều kiện thời gian vào transaction/database call khi phù hợp.
- Ghi nhận thời điểm quyết định như một input cố định của request.
- Truyền timestamp/deadline rõ ràng làm bind value.
- Không dựa vào việc đồng hồ ở application server và database luôn đồng bộ tuyệt đối.

### 6.6. Giả định ROWID không thay đổi

Ứng dụng không nên lưu ROWID lâu dài rồi dùng lại như business key. ROWID có thể thay đổi khi table được reorganize, partition, migrate, rebuild, export/import, flashback hoặc restore.

Replay có thể bị từ chối nếu kết quả ROWID khác với giá trị ứng dụng đã nhìn thấy trước outage.

Dùng primary key hoặc business key ổn định thay cho việc lưu ROWID để định danh lâu dài.

### 6.7. Giả định instance, SID hoặc host không thay đổi

Sau failover, session có thể chạy trên instance/node khác. Các giá trị vật lý như:

- SYS_CONTEXT('USERENV','INSTANCE')
- SYS_CONTEXT('USERENV','SID')
- SYS_CONTEXT('USERENV','SESSIONID')
- HOST, IP_ADDRESS, TERMINAL

có thể khác. Nếu business logic phụ thuộc những giá trị này, replay có thể bị từ chối hoặc tạo kết quả không mong muốn.

Các giá trị định danh logic như CLIENT_IDENTIFIER, MODULE, ACTION và NLS settings thường phù hợp hơn cho phân loại request. Dùng physical locator để chẩn đoán ngoài request hoặc trong callback, không dùng làm business key.

### 6.8. Mutable functions: thời gian, GUID và sequence

Một số hàm có thể trả giá trị khác mỗi lần gọi:

- SYSDATE, SYSTIMESTAMP.
- CURRENT_TIMESTAMP, LOCALTIMESTAMP.
- SYS_GUID.
- sequence.NEXTVAL.

Nếu replay trả về giá trị mới thay vì giá trị ứng dụng đã dùng trước outage, khóa chính, foreign key bind hoặc logic client có thể không còn nhất quán.

Oracle 19c hỗ trợ giữ lại giá trị ban đầu cho các mutable function trong các trường hợp được hỗ trợ. Cần cấu hình KEEP phù hợp, đặc biệt với PL/SQL:

~~~sql
GRANT KEEP DATE TIME TO app_user;
GRANT KEEP SYSGUID TO app_user;
GRANT KEEP SEQUENCE ON sales.order_seq TO app_user;
~~~

Owner của sequence có thể dùng:

~~~sql
CREATE SEQUENCE order_seq KEEP;
~~~

Hoặc:

~~~sql
ALTER SEQUENCE order_seq KEEP;
~~~

Lưu ý:

- Oracle 19c không yêu cầu grant KEEP cho sequence mutables ở SQL level theo cơ chế được tài liệu hóa.
- PL/SQL có quy tắc KEEP riêng; cần cấp đúng privilege hoặc cấu hình sequence.
- KEEP SEQUENCE là object privilege trên sequence cụ thể.
- KEEP DATE TIME và KEEP SYSGUID là system privilege.
- GRANT ALL ON object không tự bao gồm các KEEP privilege.
- Chỉ cấp KEEP cho application user cần thiết.
- SYS_GUID giữ giá trị có giới hạn, ví dụ chỉ hỗ trợ serial processing plan trong điều kiện được tài liệu hóa.

Không bật KEEP một cách rộng rãi mà không xác định ứng dụng cần giữ giá trị nào.

### 6.9. DDL và lệnh quản trị

Một số statement bị hạn chế hoặc làm replay bị disable, ví dụ ALTER SYSTEM và ALTER DATABASE. Một số ALTER SESSION cũng bị giới hạn khi chúng làm session state không thể tái lập an toàn.

Không đưa DDL hoặc lệnh quản trị vào cùng request nghiệp vụ kỳ vọng replay. Tách migration/deployment/administrative action khỏi OLTP request.

### 6.10. XA two-phase commit và isolation level

Oracle 19c có các giới hạn theo driver và transaction mode:

- Replay có thể hỗ trợ local transaction qua XA data source trong các điều kiện được hỗ trợ.
- Khi thực sự dùng XA two-phase commit, replay có thể bị disable.
- SERIALIZABLE isolation không được hỗ trợ cho replay theo các giới hạn được tài liệu hóa.
- Phải xác nhận chính xác driver, transaction manager và kiểu XA trước khi bật AC.

Không giả định một ứng dụng đang chạy XA sẽ tự động replay được chỉ vì service đặt FAILOVER_TYPE.

## 7. Side effect khác nhau giữa AC và TAC

Với AC manual (FAILOVER_TYPE = TRANSACTION), các call được ghi nhận có thể được replay theo history. Nếu request có UTL_SMTP hoặc callout không muốn lặp, ứng dụng phải chủ động disable replay cho request hoặc dùng service không bật AC.

TAC (FAILOVER_TYPE = AUTO) dùng state tracking để nhận diện một số side effect ứng dụng và tắt capture/replay cho call liên quan. Điều này giúp giảm nhu cầu lập trình thủ công, nhưng vẫn cần kiểm thử các đường tích hợp bên ngoài và các side effect tùy biến.

### 7.1. Disable replay trong Java

Với JDBC replay connection:

~~~java
if (connection instanceof oracle.jdbc.replay.ReplayableConnection) {
    ((oracle.jdbc.replay.ReplayableConnection) connection).disableReplay();
}
~~~

API disableReplay áp dụng cho request hiện tại. Khi replay đã bị disable, cả recording và replay bị tắt cho tới khi request kết thúc. Không có API bật lại giữa request vì driver không thể đảm bảo có đủ call history liên tục.

### 7.2. Disable replay trong OCI

OCI có API tương ứng OCIRequestDisableReplay cho request cần tránh replay. Kiểm tra OCI Developer's Guide và client version đang dùng để xác định cách gọi.

### 7.3. Dùng service riêng

Một ứng dụng có thể tách service:

- Service AC/TAC cho request OLTP có thể replay an toàn.
- Service không bật replay cho request có side effect không thể kiểm soát.

Service tách riêng cần có routing, monitoring, pool và SLA phù hợp. Không đổi service tùy tiện trong lúc transaction đang mở.

## 8. Mẫu thiết kế để side effect không bị nhân đôi

### 8.1. Transactional outbox

Nếu transaction database cần phát sự kiện ra message broker hoặc gọi API ngoài, không gửi trực tiếp trong cùng luồng trước khi commit. Thay vào đó, ghi một outbox record trong cùng transaction.

~~~text
HTTP request
    |
    v
Oracle transaction
    |
    +---- UPDATE business tables
    |
    +---- INSERT OUTBOX(event_id, payload, status)
    |
    v
  COMMIT
    |
    v
Outbox worker
    |
    +---- send to external system using event_id
    |
    +---- mark delivered / retry
~~~

Ví dụ:

~~~sql
CREATE TABLE event_outbox (
    event_id       VARCHAR2(64) PRIMARY KEY,
    event_type     VARCHAR2(50) NOT NULL,
    payload        CLOB NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    delivered_at   TIMESTAMP,
    status         VARCHAR2(20) DEFAULT 'PENDING' NOT NULL
);
~~~

Trong transaction nghiệp vụ:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;

INSERT INTO event_outbox(event_id, event_type, payload)
VALUES (:event_id, 'ORDER_PAID', :payload);

COMMIT;
~~~

Worker đọc outbox sau commit và gửi sự kiện. Nếu worker gửi thành công nhưng chết trước khi đánh dấu DELIVERED, nó có thể gửi lại. Vì vậy, hệ thống nhận vẫn nên hỗ trợ idempotency key/event_id.

Outbox không tạo exactly-once delivery thần kỳ; nó tạo một điểm ghi nhận bền vững để retry có kiểm soát và deduplicate.

### 8.2. Idempotency key cho payment/API

Khi gọi payment provider hoặc REST API, tạo một business operation ID ổn định và truyền làm idempotency key. Nếu cùng operation được gửi lại, phía nhận trả lại kết quả của lần xử lý trước thay vì thực hiện thanh toán lần hai.

Không tạo idempotency key mới mỗi lần retry; key phải đại diện cho cùng một thao tác nghiệp vụ.

### 8.3. Tách audit transaction

Nếu audit phải tồn tại độc lập với transaction chính, cần có quy tắc deduplication. Có thể dùng event ID duy nhất và unique constraint để một event chỉ được ghi nhận một lần.

Không giả định autonomous transaction luôn được replay đúng một lần.

## 9. Session state consistency và COMMIT

Replay không chỉ khôi phục dữ liệu transaction. Nó còn cần khôi phục non-transactional session state như NLS, optimizer settings, PL/SQL package state, temporary table contents, application context và các trạng thái khác.

### 9.1. DYNAMIC

DYNAMIC phù hợp với phần lớn ứng dụng, đặc biệt khi session state có thể thay đổi trong lúc request chạy.

Với manual AC, khi session state consistency là DYNAMIC (mặc định), replay bị disable sau COMMIT cho đến khi request tiếp theo bắt đầu. Lý do là trạng thái non-transactional có thể đã thay đổi trong transaction và không thể tái lập an toàn sau khi session mất.

### 9.2. STATIC

STATIC chỉ phù hợp khi session state được thiết lập trong giai đoạn initialization và có thể khôi phục qua FAILOVER_RESTORE hoặc callback. Không chọn STATIC nếu ứng dụng thay đổi package state, NLS, context hoặc temporary state giữa các transaction trong request.

### 9.3. AUTO

AUTO là session_state_consistency bắt buộc của TAC. State tracking ghi nhận và xác minh các session state mà TAC hỗ trợ, giúp khôi phục session mà không cần ứng dụng tự khai báo mọi thay đổi.

### 9.4. Bảng so sánh

| Chế độ | Dùng với | Hành vi |
| --- | --- | --- |
| DYNAMIC | Manual AC | State có thể thay đổi trong request; replay bị disable sau COMMIT cho đến request tiếp theo |
| STATIC | Manual AC | Chỉ an toàn khi state đã được thiết lập ban đầu và có thể khôi phục |
| AUTO | TAC | Oracle theo dõi state; là chế độ bắt buộc cho TAC |

Nếu không hiểu đầy đủ session state, không tự đặt STATIC. Oracle khuyến nghị AUTO khi dùng TAC; với manual AC, DYNAMIC là lựa chọn phù hợp cho phần lớn ứng dụng.

## 10. Planned maintenance và unplanned outage

### 10.1. Unplanned outage

Ví dụ:

- Instance crash.
- Node failure.
- Network interruption.
- Storage failure.
- Foreground process failure.
- Service/database outage.

FAN có thể thông báo nhanh cho connection pool về UP/DOWN events. Driver/pool loại bỏ connection hỏng, tạo connection mới và phối hợp AC/TAC để phục hồi request đủ điều kiện.

### 10.2. Planned maintenance

Khi patch, relocate service hoặc dừng instance, ưu tiên drain request đang chạy:

1. Thông báo service sẽ bảo trì.
2. Pool ngừng cấp connection mới vào instance sắp dừng.
3. Request đang chạy được cho thời gian hoàn tất.
4. Request không drain được nhưng đủ điều kiện có thể failover/replay.
5. Dừng instance/service theo quy trình.
6. Hoàn tất maintenance và mở lại service.
7. Xác nhận pool nhận FAN UP event và traffic trở lại bình thường.

### 10.3. Không phải mọi session đều cần replay

Nếu DBA chủ động kill/disconnect session và không muốn replay, Oracle hỗ trợ NOREPLAY trong một số lệnh quản trị:

~~~sql
ALTER SYSTEM KILL SESSION 'sid, serial#, @inst' NOREPLAY;
~~~

Hoặc:

~~~sql
ALTER SYSTEM DISCONNECT SESSION 'sid, serial#, @inst' NOREPLAY;
~~~

Chỉ dùng khi đã xác định session không nên được khôi phục. Với service maintenance, SRVCTL/DBMS_SERVICE có các tùy chọn tương ứng tùy môi trường.

## 11. Driver và môi trường hỗ trợ

Application Continuity phụ thuộc cả database service và client stack. Không thể chỉ bật một parameter ở database rồi mặc định mọi driver đều replay được.

Một số điểm cần kiểm tra trên Oracle 19c:

- Java sử dụng JDBC Thin Replay Driver/data source phù hợp.
- UCP và WebLogic có tích hợp hỗ trợ Application Continuity theo cấu hình.
- OCI/ODP.NET Unmanaged cần xác nhận đúng version và API.
- JDBC OCI driver (type 2), ODP.NET Managed, OLE DB, ODBC, OCCI và một số precompiler không nằm trong phạm vi AC theo ma trận hỗ trợ được tài liệu hóa cho 19c.
- TAC có ma trận hỗ trợ riêng; OCI/ODP.NET Unmanaged và SQL*Plus 19.3+ là các ví dụ có hỗ trợ.
- Không dùng SID/instance_name trong kết nối replay; kết nối tới database service để driver định tuyến tới target hợp lệ.
- Với RAC/Data Guard, cấu hình FAN/ONS và service placement phù hợp.

Đối với JDBC, Oracle 19c dùng replay data source như oracle.jdbc.replay.OracleDataSourceImpl hoặc OracleConnectionPoolDataSourceImpl theo tài liệu và cấu hình pool. Luôn kiểm tra đúng driver version, connection pool, service và database release.

## 12. Những giới hạn cần biết

Một số tình huống được Oracle 19c tài liệu hóa là bị loại trừ hoặc hạn chế:

- Statement ALTER SYSTEM hoặc ALTER DATABASE làm replay bị disable.
- Một số ALTER SESSION không an toàn cho việc tái lập session sẽ disable replay.
- XA two-phase commit có giới hạn; replay có thể bị disable khi đang thực hiện global transaction.
- SERIALIZABLE isolation không được hỗ trợ cho replay.
- Một số JDBC deprecated concrete classes không được hỗ trợ.
- JDBC statement cache ở application server cần được tắt khi replay; dùng JDBC driver statement cache được hỗ trợ.
- Một số stream arguments/physical stream address chỉ được replay best-effort; một số JDBC stream setter có thể disable replay.
- Replay target phải thuộc database cluster/configuration được hỗ trợ; không replay sang một database khác tùy ý.
- Nếu target database bị data loss hoặc được mở ở một thời điểm cũ hơn (ví dụ flashback/incomplete recovery), replay bị từ chối để bảo vệ tính toàn vẹn transaction.
- Một số lỗi statement-level của parallel query không kích hoạt replay.
- DRCP cho Java không được hỗ trợ theo giới hạn được tài liệu hóa.
- Một số cấu hình Active Data Guard với read/write database link về primary bị giới hạn.

Danh sách này không thay thế compatibility matrix của đúng driver và release update. Kiểm tra tài liệu Oracle trước khi đưa workload vào production.

## 13. Theo dõi và chẩn đoán replay

### 13.1. Application Continuity statistics

Oracle ghi nhận số request và protected calls. Có thể xem một số system statistics:

~~~sql
SELECT n.name,
       s.value
FROM v$sysstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE LOWER(n.name) LIKE '%request%'
   OR LOWER(n.name) LIKE '%replay%'
ORDER BY n.name;
~~~

Các statistic hữu ích tùy phiên bản có thể gồm:

- cumulative begin requests.
- cumulative end requests.
- cumulative user calls in requests.
- cumulative user calls protected by Application Continuity.
- successful replays by Application Continuity.
- failed replays.

Tên và sự hiện diện của statistic cần được kiểm tra trên database thực tế.

### 13.2. Session statistics

Để xem theo session, kết hợp V$SESSTAT và V$STATNAME:

~~~sql
SELECT s.sid,
       n.name,
       ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname n
  ON n.statistic# = ss.statistic#
WHERE s.username = 'APP_USER'
  AND (
      LOWER(n.name) LIKE '%request%'
      OR LOWER(n.name) LIKE '%replay%'
  )
ORDER BY s.sid, n.name;
~~~

### 13.3. JDBC ReplayStatistics

Oracle JDBC replay driver cung cấp ReplayStatistics, có thể lấy từ ReplayableConnection hoặc OracleDataSource. Các số liệu thường gồm:

- TotalRequests.
- TotalCompletedRequests.
- TotalCalls.
- TotalProtectedCalls.
- TotalCallsAffectedByOutages.
- TotalCallsTriggeringReplay.
- SuccessfulReplayCount.
- FailedReplayCount.
- ReplayDisablingCount.
- TotalReplayAttempts.

Đặt việc đọc statistics ở điểm phù hợp trong ứng dụng, ví dụ sau khi hoàn tất workload hoặc qua một connection quản trị. Các thống kê có thể được clear; số liệu sau đó phản ánh khoảng thời gian kể từ lần clear gần nhất.

### 13.4. AWR và ACCHK

Application Continuity statistics được ghi trong AWR và có thể xem trong AWR report. Dùng ACCHK utility của Oracle Autonomous Health Framework/ORAchk theo release phù hợp để phát hiện các yếu tố làm giảm protection hoặc cản trở replay.

Khi protected calls giảm, cần kiểm tra:

1. Service có FAILOVER_TYPE đúng không?
2. Driver có phải replay-capable không?
3. Request boundary có được đánh dấu không?
4. Có restricted call hoặc disableReplay không?
5. Session state có khôi phục được không?
6. Có concrete classes, stream API hoặc transaction mode không được hỗ trợ không?
7. Replay initiation timeout có đủ dài không?

## 14. Quy trình đánh giá một thao tác có an toàn để replay không

Với từng thao tác trong request, hỏi:

1. Thao tác có chỉ thay đổi dữ liệu trong transaction Oracle không?
2. Có gọi hệ thống bên ngoài hoặc tạo side effect không thể rollback không?
3. Nếu chạy hai lần, kết quả nghiệp vụ có giống một lần không?
4. Có idempotency key hoặc unique constraint bảo vệ không?
5. Có autonomous transaction hoặc COMMIT ẩn không?
6. Có phụ thuộc thời gian ở middle tier không?
7. Có phụ thuộc SID, INSTANCE, HOST, ROWID hoặc tài nguyên volatile không?
8. Có thay đổi session state sau COMMIT không?
9. Driver và service có hỗ trợ thao tác đó không?
10. Nếu replay bị từ chối, ứng dụng xử lý thế nào?

### 14.1. Ma trận đánh giá

| Thao tác | Rủi ro replay | Hướng xử lý |
| --- | --- | --- |
| SELECT dữ liệu nghiệp vụ | Thường thấp nếu kết quả được kiểm tra nhất quán | Dùng driver/service hỗ trợ và kiểm thử kết quả |
| INSERT/UPDATE trong transaction Oracle | Có thể replay khi request và session state hợp lệ | Dùng transaction boundary rõ ràng, khóa nghiệp vụ/unique constraint |
| COMMIT bị mất response | Có thể không biết client đã nhận outcome chưa | Dùng Transaction Guard/COMMIT_OUTCOME; không retry mù |
| Gửi email | Cao, email có thể gửi hai lần | TAC/disable replay, outbox, idempotency |
| Gọi payment API | Rất cao, có thể tính tiền hai lần | Idempotency key ở payment provider và outbox |
| Ghi file ngoài database | Cao, file có thể bị ghi lặp | Ghi qua worker/outbox hoặc thao tác idempotent |
| Autonomous transaction | Có thể tạo side effect độc lập lặp lại | Review replay rules, deduplicate bằng event ID |
| Dùng thời gian middle tier | Cao nếu thời gian đổi trong lúc outage | Đóng băng input timestamp hoặc đưa điều kiện vào DB |
| Dùng SID/INSTANCE làm logic | Không ổn định sau failover | Dùng logical identity |
| Lưu ROWID lâu dài | ROWID có thể thay đổi | Dùng primary/business key |
| DDL ALTER SYSTEM/ALTER DATABASE | Bị hạn chế/disable replay | Tách khỏi request nghiệp vụ |
| Session state thay đổi rồi COMMIT | Có thể không khôi phục được ở DYNAMIC | Dùng AUTO/TAC hoặc thiết kế lại state |
| XA two-phase commit | Có giới hạn hỗ trợ | Xác minh driver/transaction mode; không giả định replay |

## 15. Lab: mô phỏng request và replay behavior

Lab này tập trung vào thiết kế và quan sát, không yêu cầu gây outage trên production. Chạy trong môi trường RAC/HA thử nghiệm có service và driver hỗ trợ.

### 15.1. Chuẩn bị service

DBA tạo service AC hoặc TAC riêng theo topology. Ví dụ TAC:

~~~text
FAILOVER_TYPE = AUTO
FAILOVER_RESTORE = AUTO
COMMIT_OUTCOME = TRUE
AQ_HA_NOTIFICATIONS = TRUE
~~~

Với manual AC, dùng FAILOVER_TYPE = TRANSACTION và cấu hình FAILOVER_RESTORE/SESSION_STATE_CONSISTENCY theo thiết kế.

### 15.2. Tạo bảng giao dịch thử

~~~sql
CREATE TABLE ac_lab_orders (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20) NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    updated_at TIMESTAMP
);

INSERT INTO ac_lab_orders(order_id, status, amount, updated_at)
VALUES (1001, 'NEW', 250, SYSTIMESTAMP);

COMMIT;
~~~

### 15.3. Tạo outbox

~~~sql
CREATE TABLE ac_lab_outbox (
    event_id VARCHAR2(64) PRIMARY KEY,
    order_id NUMBER NOT NULL,
    event_type VARCHAR2(30) NOT NULL,
    status VARCHAR2(20) DEFAULT 'PENDING' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

### 15.4. Thực hiện nghiệp vụ trong một transaction

~~~sql
UPDATE ac_lab_orders
SET status = 'PAID',
    updated_at = SYSTIMESTAMP
WHERE order_id = 1001;

INSERT INTO ac_lab_outbox(event_id, order_id, event_type)
VALUES ('ORDER-1001-PAID', 1001, 'ORDER_PAID');

COMMIT;
~~~

Business update và outbox event cùng commit hoặc cùng rollback. Worker gửi event sau đó với ORDER-1001-PAID làm idempotency key.

### 15.5. Kiểm tra kết quả

~~~sql
SELECT *
FROM ac_lab_orders
WHERE order_id = 1001;

SELECT *
FROM ac_lab_outbox
WHERE event_id = 'ORDER-1001-PAID';
~~~

Chạy lại thao tác tạo outbox với cùng EVENT_ID sẽ gặp unique constraint thay vì tạo thêm event. Ứng dụng cần diễn giải duplicate key theo business operation đã tồn tại.

### 15.6. Thử side effect không idempotent trong môi trường riêng

Trong một lab độc lập, gọi một endpoint test hoặc ghi file tạm trong request có AC manual. Mô phỏng lỗi sau side effect nhưng trước khi request hoàn tất. Quan sát side effect có được lặp hay không.

Không dùng endpoint thanh toán, email thật, file production hoặc hệ thống bên ngoài có dữ liệu thật trong bài thử này.

### 15.7. Thử disableReplay

Trong Java replay connection, gọi disableReplay trước khi thực hiện module có side effect không muốn lặp. So sánh thống kê protected calls và replay count với request bình thường.

### 15.8. Thử Transaction Guard

Trong môi trường HA thử nghiệm:

1. Bật COMMIT_OUTCOME trên service.
2. Thực hiện transaction có mã nghiệp vụ duy nhất.
3. Mô phỏng mất kết nối quanh thời điểm COMMIT theo kịch bản kiểm thử được phê duyệt.
4. Kiểm tra transaction outcome bằng API/driver phù hợp.
5. Xác nhận ứng dụng không gửi lại transaction đã commit.

Không dùng việc kill instance tùy tiện trên môi trường production để tạo lỗi thử nghiệm.

## 16. Checklist triển khai Application Continuity

1. **Service đúng chưa?** Ứng dụng kết nối bằng service, không dùng SID/instance cố định.
2. **FAILOVER_TYPE đúng chưa?** TRANSACTION cho AC, AUTO cho TAC.
3. **Transaction Guard đã bật chưa?** COMMIT_OUTCOME = TRUE và retention phù hợp.
4. **FAILOVER_RESTORE đã phù hợp chưa?** LEVEL1 cho AC hoặc AUTO cho TAC theo thiết kế.
5. **Driver có hỗ trợ không?** Kiểm tra phiên bản JDBC/OCI/ODP.NET và connection pool.
6. **FAN/notification đã cấu hình chưa?** Kiểm tra ONS, pool và service.
7. **Request boundaries có đúng không?** Checkout/check-in hoặc beginRequest/endRequest.
8. **Session state có khôi phục được không?** NLS, package state, context, temporary tables, optimizer settings.
9. **Side effect đã được rà soát chưa?** Email, HTTP, file, autonomous transaction, Java callout.
10. **Mutable functions đã được xử lý chưa?** Sequence, SYSDATE, SYSTIMESTAMP, SYS_GUID và KEEP.
11. **Có dùng ROWID hoặc physical locator không?** Thay bằng logical key nếu có thể.
12. **Có đồng bộ nhiều session bằng lock volatile không?** Thiết kế lại hoặc không bật replay cho workload đó.
13. **Có XA/Serializable/stream API bị hạn chế không?** Xác minh compatibility matrix.
14. **Disable replay có được dùng đúng request không?** Không để replay bị disable kéo dài ngoài ý muốn.
15. **Timeout có phù hợp SLA không?** Replay initiation, retry, retention và pool timeout.
16. **Đã kiểm thử unplanned outage chưa?** Kiểm tra replay thành công và replay bị từ chối.
17. **Đã kiểm thử planned maintenance chưa?** Drain, FAN, service relocate và request đang chạy.
18. **Đã theo dõi statistics chưa?** Protected calls, successful/failed replay, disabling count.
19. **Đã thử commit outcome chưa?** Không retry mù sau mất response COMMIT.
20. **Ứng dụng có fallback không?** Xử lý nonrecoverable errors và replay rejection.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Application Continuity giải quyết vấn đề gì khi database session mất?

**Câu 2.** Database request là gì?

**Câu 3.** Recoverable error khác nonrecoverable error thế nào?

**Câu 4.** Vì sao client có thể không biết COMMIT đã thành công hay chưa?

**Câu 5.** Transaction Guard và LTXID giúp giải quyết vấn đề gì?

**Câu 6.** FAILOVER_TYPE = TRANSACTION và AUTO khác nhau thế nào?

**Câu 7.** Vì sao AC cần request boundary?

**Câu 8.** beginRequest và endRequest được dùng khi nào?

**Câu 9.** Vì sao không nên gọi endRequest khi transaction còn mở?

**Câu 10.** TAC dùng state tracking để làm gì?

**Câu 11.** Vì sao UTL_SMTP hoặc UTL_HTTP có thể tạo side effect lặp?

**Câu 12.** Autonomous transaction khác transaction gọi nó ở điểm nào?

**Câu 13.** Vì sao lock giữa hai session có thể mất ý nghĩa sau replay?

**Câu 14.** Vì sao không nên dùng đồng hồ middle tier làm điều kiện quyết định replay?

**Câu 15.** Vì sao ROWID không phù hợp làm business key lâu dài?

**Câu 16.** Những SYS_CONTEXT location values nào có thể thay đổi sau failover?

**Câu 17.** KEEP DATE TIME, KEEP SYSGUID và KEEP SEQUENCE dùng để làm gì?

**Câu 18.** Vì sao DDL như ALTER SYSTEM không nên nằm trong request replay?

**Câu 19.** Transactional outbox giúp giảm rủi ro side effect như thế nào?

**Câu 20.** Vì sao idempotency key vẫn cần thiết dù đã bật AC/TAC?

<details>
<summary>Gợi ý đáp án</summary>

1. Phục hồi session và in-flight work sau recoverable outage để request có thể tiếp tục an toàn.
2. Một đơn vị database work trên một connection, thường gắn với một request ở ứng dụng.
3. Recoverable error do lỗi hạ tầng/kết nối; nonrecoverable error là lỗi không thể giải quyết bằng reconnect/replay như dữ liệu đầu vào sai.
4. COMMIT có thể đã được ghi bền vững nhưng response chưa tới client.
5. Xác định transaction cuối đã commit hay chưa để tránh gửi lại transaction đã hoàn tất.
6. TRANSACTION là manual AC; AUTO bật TAC với state tracking.
7. Để driver biết call history thuộc request nào và khi nào kết thúc.
8. Đánh dấu bắt đầu/kết thúc request trên JDBC connection khi pool/framework không tự tạo boundary.
9. Oracle yêu cầu local transaction đã kết thúc trước khi đóng request boundary.
10. Theo dõi và xác minh session/transaction state, nhận diện request boundary và một số side effect.
11. Email/HTTP là hành động bên ngoài transaction database; replay có thể gửi lại sau lỗi.
12. Autonomous transaction có commit/rollback độc lập và side effect có thể tồn tại dù transaction chính rollback.
13. Failover có thể làm mất lock/tài nguyên volatile mà session khác đang dựa vào.
14. Driver replay database calls nhưng không chạy lại logic thời gian ở middle tier.
15. ROWID có thể đổi sau reorganize, partition, migrate, restore hoặc flashback; dùng primary/business key.
16. INSTANCE, SID, SESSIONID, HOST, IP_ADDRESS và TERMINAL.
17. Giữ giá trị mutable ban đầu của thời gian, GUID và sequence trong các trường hợp replay được hỗ trợ.
18. Các lệnh quản trị bị hạn chế và làm replay bị disable; tách khỏi request nghiệp vụ.
19. Ghi event trong cùng transaction với dữ liệu, gửi sau commit bằng worker và retry có kiểm soát.
20. AC/TAC không biến external system thành exactly-once; idempotency key giúp phía nhận deduplicate thao tác được gửi lại.

</details>

## 18. Tài liệu Oracle chính thức

1. [Oracle Database 19c Real Application Clusters Administration and Deployment Guide — Ensuring Application Continuity](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html): AC, TAC, replay, side effects, restrictions, service configuration và Transaction Guard.
2. [Oracle Database 19c JDBC Developer's Guide — Application Continuity for Java](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/application-continuity.html): JDBC Replay Driver, request boundaries, TAC, disableReplay và ReplayStatistics.
3. [Oracle Database 19c High Availability Overview — Configuring Level 3](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/configuring-level-3-mask-unplanned-failovers-applications.html): cấu hình service cho AC/TAC, commit outcome và side effect.
4. [Oracle Database 19c Concepts — Transactions and Application Continuity](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): request, reconnection, replay và Transaction Guard.
5. [Oracle Database 19c Reference — DBMS_SERVICE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SERVICE.html): quản lý service và thuộc tính service.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APP_CONT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APP_CONT.html): API và quy tắc replay liên quan PL/SQL khi được hỗ trợ.
7. [Oracle Database 19c Real Application Clusters Administration and Deployment Guide — Fast Application Notification](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html): FAN events và phối hợp với connection pool.

**Nguyên tắc cần nhớ:** Application Continuity ghi nhận database request, kết nối lại và replay database calls sau recoverable outage. Transaction Guard giúp xác định commit outcome để tránh gửi lại transaction đã hoàn tất. Replay chỉ an toàn khi session state và kết quả mà ứng dụng đã nhìn thấy có thể được khôi phục. Email, HTTP, file transfer, autonomous transaction, đồng bộ nhiều session bằng lock volatile, thời gian middle tier, ROWID và physical locator là các vùng cần đánh giá đặc biệt. Dùng TAC/state tracking, disableReplay, transactional outbox và idempotency key đúng chỗ; không giả định bật AC/TAC sẽ biến mọi thao tác thành exactly-once.
