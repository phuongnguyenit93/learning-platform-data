# Kiểm tra năng lực phục hồi bằng các lần diễn tập

Một cơ sở dữ liệu có replica, backup hằng ngày và tài liệu hướng dẫn khôi phục **chưa chắc đã phục hồi được trong thời gian nghiệp vụ cho phép**. Khi sự cố thật xảy ra, đội vận hành có thể phát hiện rằng bản backup thiếu WAL, tài khoản restore không còn quyền, connection pool Java vẫn giữ endpoint cũ, hoặc worker outbox gửi lại một sự kiện đã được xử lý. Những điều này chỉ trở nên rõ khi ta **thực hiện quy trình phục hồi từ đầu đến cuối**, đo kết quả và kiểm chứng dữ liệu.

**Diễn tập phục hồi** (*recovery drill*) là hoạt động có kế hoạch nhằm giả lập một dạng sự cố, thực hiện những bước phản ứng và khôi phục đã định, rồi thu bằng chứng về khả năng đưa dịch vụ trở lại trạng thái an toàn. Nó có thể bắt đầu bằng diễn tập trên giấy (*tabletop*), tiếp đến là restore trong môi trường cô lập, thử chuyển primary–replica và, khi đã đủ năng lực kiểm soát rủi ro, những *game day* có phạm vi ảnh hưởng giới hạn.

Trong chương **Quan sát và vận hành** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài này kết nối kiến thức transaction, chỉ mục, độ bền, lỗi kết nối, schema migration, backup, bảo mật và hiệu năng với năng lực vận hành thực tế của ứng dụng Java. Đích đến không phải một bảng đánh dấu “đã diễn tập”, mà là câu trả lời có chứng cứ: **Mất những gì? Mất bao lâu để phục hồi? Dữ liệu có đúng không? Có thể tiếp tục nhận giao dịch mà không gây tác dụng phụ trùng lặp không?**

## 1. Kiểm thử tự động, quan sát và diễn tập khác nhau thế nào?

Ba hoạt động bổ sung cho nhau:

| Hoạt động | Phạm vi điển hình | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- | --- |
| **Integration/fault-injection test** | Một transaction, JVM, connection hoặc DB container test | Logic rollback, retry, SQLSTATE, idempotency cho kịch bản cụ thể | Toàn bộ runbook, thao tác vận hành, quyền restore, sự phụ thuộc giữa dịch vụ |
| **Monitoring/alerting** | Sản phẩm đang hoạt động | Có số liệu về tình trạng hiện tại, lag, lỗi và độ trễ | Đã thực sự có thể restore, dùng lại backup hoặc khôi phục nghiệp vụ chưa |
| **Recovery drill** | Người, quy trình, hạ tầng, database, API và dependency | Khả năng phát hiện, đưa ra quyết định, khôi phục, đối soát và giao tiếp | Bảo đảm tuyệt đối mọi sự cố tương lai đều giống tình huống đã thử |

Một bài test JUnit mô phỏng SQL lỗi rất hữu ích nhưng không cho biết lúc 03:00 ai có quyền truy cập kho backup. Ngược lại, việc ứng dụng trả HTTP 200 sau restart không chứng minh outbox không phát lại thanh toán. Diễn tập nối **hạ tầng, dữ liệu, ứng dụng và con người** vào một quy trình có thể lặp.

### Các kiểu diễn tập nên phân biệt

1. **Tabletop:** đội ngũ duyệt kịch bản và runbook trên giấy; kiểm tra trách nhiệm, escalation, quyền phê duyệt và phụ thuộc. Không làm hỏng hệ thống.
2. **Restore drill:** khôi phục bản backup thật vào DB cách ly, kiểm chứng schema, dữ liệu, role, khóa giải mã, WAL và ứng dụng Java.
3. **Failover drill:** chuyển quyền ghi sang nút khác trong cụm test, kiểm tra fencing, client reconnect, pool, replication lag và dữ liệu đã ACK.
4. **Dependency outage drill:** mô phỏng broker, DNS, secret manager hoặc mạng tới DB chậm/ngắt; kiểm tra backoff, timeout và nguồn sự thật.
5. **Game day:** phối hợp nhiều vai trò, thực hiện kịch bản có điều phối và đo thời gian phát hiện–khắc phục. Có thể tiến hành ở staging hoặc một phạm vi production đã được **phê duyệt riêng**.

Không cần bắt đầu từ kịch bản gây gián đoạn lớn. Diễn tập từ môi trường cô lập và tăng dần độ thực tế giúp phát hiện sai sót trước khi động vào dịch vụ quan trọng.

## 2. Chốt năng lực phục hồi muốn kiểm chứng trước khi chạy

Một mục tiêu “có backup và high availability” là chưa đủ. Cần định nghĩa **dịch vụ thiết yếu, loại sự cố, RPO, RTO, bất biến và giới hạn tác động**.

| Mục tiêu | Ý nghĩa vận hành | Cách xác minh |
| --- | --- | --- |
| **RPO** (*Recovery Point Objective*) | Mức dữ liệu đã được xác nhận có thể mất tối đa khi sự cố xảy ra | So tập operation ID/commit marker đã ACK với dữ liệu phục hồi; đối chiếu WAL/replica |
| **RTO** (*Recovery Time Objective*) | Khoảng thời gian mục tiêu đến lúc dịch vụ thiết yếu hoạt động trở lại | Đo từ mốc kích hoạt sự cố đến khi API và nghiệp vụ quan trọng đạt điều kiện chấp nhận |
| **Data integrity** | Không có transaction dở dang được hiểu như đã hoàn tất, không phá bất biến | SQL kiểm tra constraint, receipt, ledger, outbox và thao tác thử |
| **Recoverable write path** | Ứng dụng có thể ghi an toàn sau failover/restore | Gửi lệnh thử idempotent trên DB lab và kiểm tra commit |
| **Dependency recovery** | Pool, broker, secret, worker và migration phù hợp sau phục hồi | Quan sát connection mới, worker backlog, schema version |
| **Operational repeatability** | Người trực có thể thực hiện runbook được cấp quyền và có log/audit | Diễn tập với người/ca trực khác; đo thời gian ra quyết định và thao tác |

**RPO là mục tiêu, không phải số đo thực tế.** Một lần diễn tập không thấy mất transaction không chứng minh mọi lần failover sẽ có RPO bằng 0. Trong mô hình primary–replica bất đồng bộ, giao dịch đã được primary ACK có thể chưa đến replica. Phải xác định chính sách durability/replication và giới hạn sự cố trước khi công bố mức bảo đảm.

**RTO không dừng ở lúc DB mở cổng TCP.** Nếu PostgreSQL lên sau 90 giây nhưng API Java cần 5 phút để nhận secret mới, chạy migration và trả lời giao dịch hợp lệ, RTO cho nghiệp vụ gần 5 phút (tính theo mốc đã định). Nên ghi cả **thời gian phát hiện (TTD), ra quyết định, phục hồi DB, phục hồi ứng dụng và xác minh** để tìm điểm nghẽn.

### Ví dụ về tiêu chí đạt — chỉ là số minh họa

```text
Kịch bản: primary PostgreSQL không thể phục vụ, chuyển sang standby
Phạm vi: cụm test có dữ liệu giả, không kết nối thanh toán/email thật

Điều kiện PASS:
  - leader mới duy nhất, primary cũ bị fencing
  - API GET/POST thiết yếu hoạt động trong RTO mục tiêu 5 phút
  - dữ liệu mất nếu có nằm trong RPO mục tiêu đã phê duyệt
  - không có double charge, duplicate booking, vi phạm ledger
  - connection pool tạo connection mới đến leader đúng
  - outbox có thể tiếp tục phát, consumer chống trùng
  - mọi cảnh báo và timestamp có bằng chứng từ monitoring
```

Không xem các con số ví dụ là tiêu chuẩn mặc định cho mọi hệ thống. Một dịch vụ thanh toán có yêu cầu và chi phí khác dịch vụ báo cáo. Tiêu chí phải được đặt **trước khi chạy**, không chỉnh theo kết quả chỉ để đánh dấu pass.

## 3. Xác định ranh giới và “điểm khôi phục được”

Một dịch vụ Java không chỉ có database:

```text
Client / API gateway
          |
          v
 Java service + connection pool ------> Secret/identity provider
          |
          v
  DB primary <---- replication ---- DB standby
     |                                 |
     +-- WAL/archive --> Backup store -+
     |
     +-- orders + transactional outbox
                     |
                     v
                 Publisher ---> Broker ---> Consumer / payment ledger
                                             |
                                             v
                                        External side effect
```

Với mỗi thành phần, cần trả lời:

- **Nguồn sự thật:** dữ liệu nào do DB này sở hữu, dữ liệu nào ở broker, object storage hoặc dịch vụ khác?
- **Miền lỗi:** mất một process, một host, một vùng mạng, một vùng địa lý, hay xóa logic dữ liệu?
- **Cơ chế phục hồi:** WAL/crash recovery, replica failover, backup + PITR, rebuild projection, replay event, hay bù trừ nghiệp vụ?
- **Tính nhất quán sau phục hồi:** các hệ thống có cùng mốc không; nếu không, đối soát bằng ID nào?
- **Điểm chặn an toàn:** khi nào phải dừng writer, scheduler hoặc worker để tránh sinh thêm dữ liệu sai?

**Replication không thay thế backup:** một lệnh `DELETE` sai hoặc schema migration phá dữ liệu có thể được nhân bản ngay sang standby. Ngược lại, backup ở mốc cũ không tự động có RPO tốt hơn replica. Diễn tập cần thử **cả sự cố hạ tầng và sự cố logic** khi chúng nằm trong phạm vi rủi ro.

## 4. Chuẩn bị diễn tập: bảo vệ môi trường và xác định vai trò

Trước khi tác động vào hệ thống, tạo một **exercise charter** gồm phạm vi, chủ sở hữu và ngưỡng dừng.

| Thành phần | Câu hỏi trước khi chạy |
| --- | --- |
| **Environment** | Đây là test/staging cô lập hay một phạm vi production đã được phê duyệt? |
| **Data** | Chỉ có dữ liệu giả/ẩn danh; có khả năng làm sạch và phục hồi fixture không? |
| **Access** | Ai được thực hiện failover, restore, chỉnh DNS, khóa credential và mở lại traffic? |
| **Blast radius** | Có giới hạn theo tenant, shard, vùng và số instance để không ảnh hưởng ngoài kế hoạch không? |
| **Dependency isolation** | Email, payment, broker thật và job scheduler đã tắt/chuyển sandbox theo thiết kế chưa? |
| **Stop condition** | Chạm ngưỡng lỗi, dữ liệu sai, không còn liên lạc hay thiếu disk thì ai có quyền dừng? |
| **Fallback** | Có cách khôi phục workload gốc hoặc dựng lại môi trường test từ nguồn đã biết không? |
| **Evidence** | Log, metrics, trace, mốc thời gian và tập ID thử nghiệm sẽ lưu ở đâu, ai đọc được? |

Phân vai tối thiểu: **incident commander** điều phối và quyết định dừng; **database operator** thực hiện DB/failover/restore; **application operator** xử lý pool, retry, worker và routing; **observer** ghi mốc và kiểm chứng; **business owner** xác nhận quy tắc nghiệp vụ. Trong tổ chức nhỏ, một người có thể kiêm vai, nhưng quyết định và quyền hạn vẫn phải được ghi rõ.

**Không thực hiện thao tác phá hủy lên production chỉ vì đây là một bài học.** Lệnh terminate backend, promote standby, xóa volume, thu hồi credential hoặc ngắt mạng chỉ nên dùng trên môi trường được phê duyệt với định danh tài nguyên rõ và phương án khôi phục. Bài này minh họa **cách kiểm chứng**, không đưa một script phá hoại chạy tùy ý.

### Cơ sở dữ liệu thử nghiệm phải đủ thật

Một môi trường trống chỉ chứng minh DB khởi động. Để kiểm tra năng lực persistence, seed các tập dữ liệu có quan hệ và **operation marker ổn định**:

- Đơn ở nhiều trạng thái, hàng chi tiết, tồn kho, ledger và một số transaction cập nhật đồng thời.
- Bảng outbox có event chờ phát, event đã gửi, event cần retry; consumer có bảng inbox/deduplication.
- Dữ liệu đủ lớn để restore, replay WAL, index build và cache warmup có thời gian đáng kể.
- Một tập mã command đã nhận **commit ACK** và được lưu trong **bằng chứng độc lập** với DB bị thử, giúp đo mất dữ liệu.
- Một transaction cố ý để dở dang khi fault, để xác minh crash recovery không biến phần chưa commit thành dữ liệu hợp lệ.

Không tạo dữ liệu kiểm thử bằng cách sao chép thô thông tin khách hàng, password hoặc mã thanh toán production. Kích thước dữ liệu và phân bố phải phù hợp mục tiêu đo, nhưng vẫn giữ an toàn thông tin.

## 5. Các bài diễn tập theo cấp độ

### 5.1. Tabletop: phát hiện lỗ hổng trước khi chạm hệ thống

Điều phối viên đưa ra tình huống: “02:15, primary không phản hồi, replica trễ và backup đêm qua có cảnh báo archive WAL”. Nhóm phải lần lượt nêu:

1. Ai nhận alert đầu tiên, làm sao phân biệt DB chết với connection pool bị cạn?
2. Có chứng cứ primary không còn ghi, và cách **fencing** tránh hai primary nhận ghi không?
3. Nếu replica thiếu WAL, RPO dự kiến là bao nhiêu? Có được phép promote không?
4. Nếu cần restore, backup, encryption key, quyền truy cập và tài liệu nằm ở đâu?
5. Ứng dụng Java đổi endpoint thế nào, có phải drain/recreate pool không?
6. Khi nào bật lại outbox, scheduler và tác động ngoài DB?
7. Ai có thẩm quyền tuyên bố khôi phục nghiệp vụ và thông báo cho người dùng?

Tabletop không chứng minh hệ thống thực sự phục hồi, nhưng nó có thể phát hiện **quyền thiếu, runbook quá cũ, trách nhiệm mơ hồ, liên hệ đứt hoặc assumption sai** mà không cần tạo downtime.

### 5.2. Restore drill: lấy bản backup thật, không chỉ kiểm file

Quy trình trong **restore lab cô lập**:

1. Chọn một bản backup **đang được bảo quản thật** theo retention policy, không chỉ bản vừa xuất cho test.
2. Xác định loại logical/physical, DB version, schema version, roles, extensions, tablespaces, encryption key và WAL cần thiết.
3. Provision database đích độc lập, chặn network tới email/broker/payment production.
4. Restore bằng công cụ DB đã được phê duyệt; với PITR xác định recovery target và giữ đủ chuỗi WAL.
5. Kiểm tra manifest/checksum theo khả năng công cụ, sau đó **khởi động DB**, kiểm tra các object và query nghiệp vụ.
6. Chạy smoke check từ ứng dụng Java cùng version phù hợp; xác minh đọc và ghi thử **chỉ vào bảng dành cho probe trong lab**.
7. Đối chiếu tập ID đã commit tới mốc backup, outbox, ledger và dữ liệu ngoài DB nếu có; ghi các chênh lệch được giải thích.
8. Đo thời gian lấy backup, decrypt, restore, replay, cấu hình secret, migration và đưa API hoạt động.

**Điều được chứng minh:** bản backup có thể dùng để dựng môi trường và chạy nghiệp vụ. **Điều chưa chứng minh:** mọi backup đều tốt, hay hệ thống production sẽ hồi phục trong cùng thời gian nếu dung lượng/tải/hạ tầng khác đáng kể.

### 5.3. Failover drill: kiểm tra leader, router và client

Với cụm test primary–replica, ghi một tập giao dịch và xác nhận ACK; sau đó mô phỏng primary ngừng phục vụ bằng cơ chế phù hợp với cụm test.

```text
T0: xác minh primary hiện tại và replay position
T1: ghi marker E1...En, lưu các ACK độc lập
T2: inject primary outage trong cụm TEST
T3: phát hiện sự cố, ngăn leader cũ nhận ghi (fencing)
T4: election/promotion, cập nhật proxy/endpoint
T5: Java pool tạo kết nối mới, API chạy lại
T6: so marker ACK với dữ liệu phục hồi, đo RPO/RTO
T7: kiểm tra outbox, worker và invariant
```

Nếu hệ dùng asynchronous replication, một số marker ACK có thể chưa được sao chép. Điều này phải được ghi nhận theo **cam kết RPO đã thiết kế**, không tự động gọi là bug cho mọi tình huống. Nhưng một hệ thống tuyên bố zero data loss mà marker đã ACK bị mất thì phải báo **không đạt**.

Khi primary cũ xuất hiện trở lại, phải xác minh nó **không tự nhận ghi**. Test failover chỉ nhìn “API sống lại” mà không kiểm tra split-brain sẽ bỏ sót nguy cơ dữ liệu phân kỳ rất nghiêm trọng.

### 5.4. Dependency outage: kiểm tra hồi phục một phần

Các tình huống bổ sung có thể diễn tập trên test environment:

| Sự cố giả lập | Điều cần quan sát | Cách kết thúc an toàn |
| --- | --- | --- |
| Mất kết nối DB giữa request | Pool/driver timeouts, request retries, transaction result unknown | Reconnect; đối soát request ID trước khi tạo side effect mới |
| Broker không nhận publish | Outbox pending tăng, worker backoff, không giữ DB transaction trong lúc chờ | Broker hồi phục; retry cùng event ID, consumer dedupe |
| Replica trễ | Đọc stale, read-your-writes, lag alert | Định tuyến đọc cần dữ liệu mới sang primary khi phù hợp |
| Secret manager tạm lỗi | Startup/readiness, credential cache, new connection failures | Khôi phục nguồn secret hoặc version trước theo policy |
| WAL archive thất bại | Archive backlog, nguy cơ PITR/RPO | Phục hồi archive, kiểm tra chuỗi WAL và disk |
| Connection pool cạn | Pool pending/acquire time, API p99 và timeout | Giải phóng connection, giảm tải/điều chỉnh ranh giới transaction |
| DDL migration xung đột | Lock wait, schema readiness, rollback runbook | Dừng/correct migration, kiểm tra schema version trước mở traffic |

Một bài diễn tập nên chọn **một loại lỗi chính** trước, ghi rõ các tình huống phát sinh phụ. Nếu cùng lúc ngắt DB, broker, DNS và secret service, rất khó phân biệt nguyên nhân và chứng minh giải pháp hồi phục.

## 6. Đo RPO bằng bằng chứng giao dịch đã được ACK

Chỉ đọc `COUNT(*)` trước/sau sự cố là không đủ: có thể mất một ID và xuất hiện một ID khác mà tổng số không thay đổi. Để kiểm chứng độ bền, sử dụng một tập marker có ID duy nhất:

```sql
-- Chỉ tạo trong database diễn tập, không dùng như bảng nghiệp vụ thật.
CREATE TABLE drill_commit_markers (
    marker_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note VARCHAR(80) NOT NULL
);
```

Trước fault, bộ phát tải ghi từng marker trong transaction và chỉ đánh dấu **ACKED** trong manifest bên ngoài sau khi `commit()` trả về thành công:

```text
Run manifest (được giữ ngoài database chịu fault):
  run_id = recovery-drill-007
  marker A: COMMIT_ACKED at 10:00:00.100
  marker B: COMMIT_ACKED at 10:00:00.310
  marker C: SENT, COMMIT_RESULT_UNKNOWN
  marker D: COMMIT_ACKED at 10:00:00.820
  fault injected at 10:00:01.000
```

Sau failover/restore, truy vấn các marker còn có:

```sql
SELECT marker_id, created_at
FROM drill_commit_markers
WHERE marker_id IN (
    '00000000-0000-4000-8000-00000000000a',
    '00000000-0000-4000-8000-00000000000b',
    '00000000-0000-4000-8000-00000000000d'
);
```

Đây là các UUID **minh họa**, không phải bằng chứng đã chạy thực tế. Với tập lớn, dùng bảng manifest ở một hệ thống **tách biệt** hoặc phép so tập ID; không cần nhét hàng triệu UUID vào một mệnh đề `IN`.

Các nguyên tắc:

- Một marker chỉ được ghi vào tập **đã ACK** nếu ứng dụng đã nhận ACK hợp lệ từ commit. Marker lỗi lúc commit là **unknown**, không được tự đếm là commit chắc chắn hoặc rollback chắc chắn.
- Ghi marker và transaction nghiệp vụ không đồng nghĩa, nếu mục tiêu là đánh giá durability của transaction nghiệp vụ cần gắn **operation ID/receipt** cùng transaction đó.
- Với restore có target trước sự cố, một số ACK sau target bị mất theo **lựa chọn recovery point**; báo cáo rõ giao dịch nào nằm ngoài phạm vi khôi phục.
- Có thể đo khoảng chênh giữa thời điểm fault và mốc commit mới nhất còn phục hồi, nhưng đồng hồ lệch, lưu lượng không đều và backup target khiến kết quả theo thời gian chỉ là xấp xỉ. **Tập ID** mới là bằng chứng mạnh hơn về giao dịch cụ thể.

## 7. Xác minh từ Java/JDBC sau khi DB phục hồi

Sau khi DB báo healthy, ứng dụng Java cần chứng minh **đường persistence thật sự dùng được**: mở connection từ pool, query theo schema mong đợi, kiểm tra kết quả trong một snapshot ổn định và đóng connection đúng cách. Một health probe chỉ chạy `SELECT 1` chưa kiểm tra migration, quyền bảng, index hay dữ liệu phục hồi.

Ví dụ Java 17+ dưới đây dùng `DataSource` kết nối tới **database lab đã restore**. Giả sử lab có hai bảng `drill_commit_markers` và `outbox_events(event_id, order_id, status)`, cùng bảng `orders(order_id, status)`. Chúng phải được tạo từ schema migration tương ứng trước khi chạy smoke check.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class RecoverySmokeCheck {
    public record Report(
            boolean ackedMarkerFound,
            long orphanOutboxRows,
            long pendingOutboxRows) {
        public boolean dataChecksPass() {
            return ackedMarkerFound && orphanOutboxRows == 0;
        }
    }

    private final DataSource dataSource;

    public RecoverySmokeCheck(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Report verify(UUID ackedMarkerId) throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            c.setReadOnly(true);
            c.setTransactionIsolation(
                    Connection.TRANSACTION_REPEATABLE_READ);
            c.setAutoCommit(false);
            try {
                boolean found = hasMarker(c, ackedMarkerId);
                long orphanRows = count(c, """
                    SELECT COUNT(*)
                    FROM outbox_events e
                    LEFT JOIN orders o ON o.order_id = e.order_id
                    WHERE o.order_id IS NULL
                    """);
                long pendingRows = count(c, """
                    SELECT COUNT(*)
                    FROM outbox_events
                    WHERE status IN ('PENDING', 'IN_PROGRESS')
                    """);
                c.commit();
                return new Report(found, orphanRows, pendingRows);
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private static boolean hasMarker(Connection c, UUID marker)
            throws SQLException {
        String sql = """
            SELECT EXISTS(
                SELECT 1 FROM drill_commit_markers WHERE marker_id = ?)
            """;
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setObject(1, marker);
            ps.setQueryTimeout(5);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new SQLException("Thiếu result");
                return rs.getBoolean(1);
            }
        }
    }

    private static long count(Connection c, String sql)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setQueryTimeout(5);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new SQLException("Thiếu result");
                return rs.getLong(1);
            }
        }
    }
}
```

Đoạn code **không tự chạy restore, không tạo DB và không có tác dụng ghi**. `dataChecksPass()` minh họa một tập điều kiện nhỏ, **không phải** chứng nhận backup hoàn toàn an toàn: chỉ kiểm tra một marker đã ACK, một loại tính toàn vẹn tham chiếu và thống kê outbox. Trong bài diễn tập thật, phải so **toàn bộ tập ACKed markers** và các invariant nghiệp vụ cần thiết.

Các lưu ý:

1. Dùng **một connection/transaction `REPEATABLE READ`** để các truy vấn kiểm chứng không trộn trạng thái ở hai thời điểm khi worker vẫn tiếp tục ghi. Thực tế nên giữ publisher/worker dừng trong giai đoạn đối soát nếu kịch bản yêu cầu một mốc cố định.
2. Cấu hình `setReadOnly(true)` và `setQueryTimeout(5)` không thay thế quyền DB, pool acquisition timeout hoặc deadline tổng của diễn tập. Phải cấu hình cả network/driver/pool và chính sách retry.
3. Kết quả `pendingOutboxRows` lớn **không nhất thiết là lỗi** ngay sau recovery; cần so tuổi event, backlog và thời gian worker bắt kịp sau khi bật.
4. Connection pool phải đặt lại trạng thái read-only/isolation/auto-commit khi connection được trả về. Đừng tạo pool mới cho mỗi request để thực hiện health probe.
5. Với nghiệp vụ còn cần kiểm tra **khả năng ghi**, làm thêm một giao dịch idempotent trên bảng probe riêng trong lab; không dùng thử bằng lệnh thanh toán hoặc booking thật.

### Chứng minh đường ghi phục hồi bằng probe chỉ dùng ở lab

```sql
-- Dùng trên DB LAB sau restore/failover, không chạy trong production.
INSERT INTO drill_commit_markers(marker_id, note)
VALUES ('00000000-0000-4000-8000-000000000099',
        'post-recovery-write-check')
ON CONFLICT (marker_id) DO NOTHING;

SELECT COUNT(*) AS marker_count
FROM drill_commit_markers
WHERE marker_id = '00000000-0000-4000-8000-000000000099';
```

Chỉ tạo probe sau khi bảo đảm kết nối tới **lab**, và ghi rõ sự khác nhau giữa marker “ACKed trước fault” và marker “được ghi sau recovery”. Không trộn cả hai khi tính RPO. Một kiểm tra write path cũng cần xét DB có còn là standby read-only hay đã được promote đúng cách.

## 8. Quan sát PostgreSQL và Java trong diễn tập

Chứng cứ vận hành phải có cùng **mốc thời gian, định danh run và phạm vi topology**. Một số câu SQL hữu ích khi có quyền xem thống kê tương ứng:

```sql
-- Node hiện tại có đang ở chế độ recovery/standby không?
SELECT pg_is_in_recovery();

-- Trên primary: tình trạng replica kết nối và vị trí WAL đã báo cáo.
SELECT application_name, state, sync_state,
       sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;

-- Trên standby: mốc WAL replay và thời điểm transaction replay gần nhất.
SELECT pg_last_wal_replay_lsn(),
       pg_last_xact_replay_timestamp();

-- Trạng thái archive WAL cục bộ (nếu cơ chế archiving đang dùng).
SELECT archived_count, failed_count,
       last_archived_time, last_failed_time
FROM pg_stat_archiver;
```

**Không dùng một giá trị thống kê đơn lẻ để tuyên bố khả dụng:**

- `pg_is_in_recovery() = false` nghĩa node không đang ở chế độ recovery; nó **không tự chứng minh** fencing đã thành công và không có primary khác.
- `pg_stat_replication` trên primary phản ánh standby đang kết nối theo góc nhìn của primary; danh sách rỗng không tự cho biết phải failover ngay.
- `pg_last_xact_replay_timestamp()` có thể cách hiện tại rất lâu khi standby **không có transaction mới để replay**; độ chênh timestamp khi nhàn rỗi không nhất thiết đồng nghĩa replication lag lớn. Nên kết hợp LSN, nguồn có WAL mới và trạng thái receiver.
- Bộ đếm `pg_stat_archiver` phản ánh trạng thái archiver của instance; không thay thế kiểm chứng có **đủ chuỗi WAL** trong kho lưu trữ để restore tới target.

### Quan sát từ application Java

| Tín hiệu | Vì sao quan trọng khi phục hồi |
| --- | --- |
| **Pool active/idle/pending, acquire time** | Endpoint cũ/DB mới chưa sẵn sàng có thể làm hàng đợi mượn connection tăng |
| **JDBC connection failures, SQLSTATE** | Phân biệt auth/TLS, network, deadlock, serialization và timeout |
| **API success/error, p95/p99 latency** | DB đã lên nhưng dịch vụ vẫn có thể timeout hoặc trả lỗi nghiệp vụ |
| **Transaction commit success/unknown, retry count** | Không suy từ exception rằng commit chắc chắn rollback |
| **Outbox pending/age, retries, dedupe rate** | Xem backlog hồi phục và có phát lại gây tác dụng trùng không |
| **Schema version và migration status** | DB restore ở version cũ có thể không tương thích code mới |
| **CPU, IOPS, disk free, WAL/archive backlog** | Restore/replay có thể nghẽn tài nguyên ngay cả khi network ổn |

Nên dùng **trace/correlation ID không bí mật** xuyên request–transaction–event; không đẩy password, token, dữ liệu thanh toán hoặc SQL bind chứa PII vào log. Một dashboard có thể hiển thị biểu đồ đẹp nhưng nếu không gắn mốc `fault_injected`, `leader_promoted`, `api_verified`, khó tính RTO chính xác.

## 9. Đối soát sau khôi phục: phải kiểm tra nghiệp vụ

Đây là điểm khác biệt giữa “hạ tầng hoạt động” và “hệ thống đã an toàn để mở traffic”. Đối soát cần dùng **khóa nhận diện bền vững và thời điểm quan sát có kiểm soát**.

Giả sử một giao dịch xác nhận đơn ghi **đơn hàng và outbox event cùng transaction**. Sau khi restore:

```sql
-- Ví dụ hợp đồng: mỗi event nguồn phải tham chiếu một order hợp lệ.
SELECT e.event_id, e.order_id
FROM outbox_events e
LEFT JOIN orders o ON o.order_id = e.order_id
WHERE o.order_id IS NULL;

-- Quan sát backlog, không dùng COUNT này làm kết luận đã giao thành công.
SELECT status, COUNT(*) AS events
FROM outbox_events
GROUP BY status
ORDER BY status;
```

Nếu ra event mồ côi, cần xác định schema và transaction boundary có đúng không, backup có cùng snapshot không, hay dữ liệu đã sai trước backup. Không tự động xóa record để làm dashboard chuyển xanh.

Khi đối soát nhiều dịch vụ:

1. Tập **request/operation ID** được source database ghi nhận tới recovery watermark.
2. Tập event ID đã phát tới broker, có khả năng broker giao lại.
3. Tập ID phía consumer đã lưu *inbox marker* cùng transaction với thay đổi local.
4. Tập payment/ledger operation ID tại provider ngoài, gồm trạng thái và số tiền.
5. Các chênh lệch được phân loại: `missing`, `duplicate`, `out-of-order`, `still-in-flight` hoặc `expected-loss-within-RPO`.

**Cùng số lượng record không có nghĩa cùng dữ liệu**. Hai bên có thể mất những ID khác nhau mà `COUNT(*)` vẫn bằng. Cần so ID, version, watermark và bất biến như “mỗi thanh toán được ghi sổ đúng một lần”.

### Outbox và phục hồi không mang lại exactly-once tuyệt đối

Nếu DB được restore về trước lúc outbox được đánh dấu `SENT`, worker có thể phát lại event đã gửi thành công. Đây là hành vi dự kiến của mô hình **at-least-once**. Consumer cần idempotency theo `event_id` và transaction marker; tác động ngoài DB như thu tiền cần idempotency ở provider hoặc đối soát riêng. Nếu DB consumer cũng bị restore về mốc cũ làm mất inbox marker, bản thân marker không còn đủ để ngăn mọi side effect đã diễn ra ở ngoài.

**Không mở worker, cron job và kết nối payment thật ngay sau khi lab restore.** Trước hết phải kiểm tra environment, isolation, callback endpoint, permission và danh sách event pending; sau đó mở lại theo kế hoạch có điều kiện dừng.

## 10. Runbook diễn tập theo pha, có ngưỡng dừng

| Pha | Chủ trì | Hoạt động và dấu hiệu qua pha |
| --- | --- | --- |
| **0. Phê duyệt** | Incident commander/business owner | Chốt mục tiêu, RPO/RTO, môi trường, thông báo, blast radius, thời điểm và rollback |
| **1. Ghi baseline** | Observer/DB operator | Lưu topology, backup ID, WAL/LSN, ACKed IDs, p95/p99, schema version và trạng thái worker |
| **2. Chuẩn bị hàng rào** | Application/DB operator | Cách ly external side effects, xác minh credential, quyền, storage, xác nhận người dừng |
| **3. Inject fault** | Người được chỉ định | Tạo đúng lỗi đã chọn; lưu timestamp và bằng chứng lỗi thực sự xảy ra |
| **4. Phát hiện/đánh giá** | On-call/incident commander | Alert đúng tín hiệu, phân loại lỗi, quyết định failover hay restore theo runbook |
| **5. Recovery** | DB/app operators | Phục hồi node hoặc restore; fencing, endpoint, pool, secret, schema và WAL được xử lý |
| **6. Xác minh** | Observer/app owner | Smoke check đọc/ghi lab, tập marker, constraints, outbox/ledger, API thiết yếu |
| **7. Mở lại có kiểm soát** | Incident commander | Worker/traffic trở lại, backlog hạ, không có hiệu ứng trùng ngoài kế hoạch |
| **8. Báo cáo/khắc phục** | Tất cả chủ sở hữu | Ghi RPO/RTO đo thật, lỗi phát hiện, action items, owner và lịch kiểm chứng lại |

**Điều kiện dừng khẩn cấp** có thể gồm: test bất ngờ tác động sản phẩm thật, đường ra hướng vào payment production, hai node nhận ghi, dữ liệu không thể đối soát, disk/WAL sắp cạn, hoặc mất khả năng giám sát. Khi gặp điều kiện dừng, kết thúc fault injection, cô lập tác động và chuyển sang **quy trình xử lý sự cố**; không tiếp tục cho đủ checklist.

Không cố “rollback” bằng cách bật lại primary cũ nếu nó đã bị loại khỏi quorum/chưa được đồng bộ và fencing. **Failback** là một thao tác quản trị riêng, cần kiểm tra dữ liệu và quyền leader, không mặc định là bước đảo ngược tức thời của failover.

### Kịch bản thời gian minh họa

```text
14:00:00  Baseline OK, manifest lưu ngoài DB lab
14:03:00  Inject failover fault (T_fault)
14:03:10  Alert phát hiện, on-call xác nhận
14:03:35  Quyết định chuyển leader
14:04:20  New leader có quyền ghi, fencing xác minh
14:04:45  Java pool tạo connection mới
14:05:15  API đọc/ghi quan trọng PASS (T_service_recovered)
14:06:30  Reconciliation & outbox backlog kiểm tra xong

Service RTO quan sát: 2 phút 15 giây
Business reconciliation complete: 3 phút 30 giây
RPO quan sát: tính riêng từ tập marker ACKed/mốc WAL
```

Tất cả thời điểm và con số là **ví dụ**, không phải kết quả diễn tập thực tế. Cần quy định rõ “service recovered” nghĩa là chỉ đọc được, hay đã ghi đúng và xử lý nghiệp vụ thiết yếu; điều này quyết định mốc RTO hợp lệ.

## 11. Chấm kết quả: PASS, FAIL hay INCONCLUSIVE?

Một cuộc diễn tập không nên tự động pass chỉ vì người vận hành đã thực hiện đủ bước. Cần **đối chiếu mỗi tiêu chí ban đầu với bằng chứng**:

| Tiêu chí | Bằng chứng tối thiểu | Kết quả ví dụ |
| --- | --- | --- |
| Nhận biết đúng sự cố | Alert/trace, thời điểm phát hiện, phân loại nguyên nhân | PASS/FAIL |
| Phục hồi trong RTO | Timestamp fault và API nghiệp vụ verified | PASS/FAIL |
| Mất dữ liệu trong RPO | Danh sách ACKed operation ID, tập đã phục hồi, log/LSN | PASS/FAIL |
| Không có hai writer | Topology/fencing logs và kết quả thử ghi có kiểm soát | PASS/FAIL |
| Không vi phạm invariant | SQL checks, ledger reconcile, unique/idempotency tests | PASS/FAIL |
| Worker an toàn khi phát lại | Event ID, inbox markers, thử redelivery trên sandbox | PASS/FAIL |
| Runbook đủ dùng | Bằng chứng thao tác của người trực và quyền truy cập | PASS/FAIL |

Khi không chắc fault đã được inject **đúng cửa sổ**, không có log thời gian, hoặc tập marker không được ghi đầy đủ, đánh dấu **INCONCLUSIVE** (chưa đủ bằng chứng), **không** tự báo PASS. Ví dụ proxy ngắt kết nối trước khi COMMIT được gửi không thể chứng minh ứng dụng xử lý *commit-result-unknown*; nó chỉ thử lỗi trước commit.

Phân loại phát hiện trong báo cáo:

- **Data correctness defect:** đã commit sai invariant, phát trùng tác động hoặc sai mốc restore.
- **Availability/recovery defect:** không đạt RTO, loop retry làm cạn pool, failover thiếu fencing.
- **Operational gap:** thiếu quyền, thiếu runbook, không rõ người quyết định.
- **Observability gap:** thiếu metric/tracing, không xác minh được RPO/RTO.
- **Test design gap:** fault chưa trúng, dữ liệu không đại diện, môi trường không cô lập.

Một lỗi thật được phát hiện trong lab là **kết quả có giá trị** của diễn tập. Ghi hành động khắc phục, người sở hữu, hạn kiểm chứng và **diễn tập lại chính kịch bản đó** sau khi sửa.

## 12. Lập lịch lặp lại và tăng độ khó có kiểm soát

Khả năng phục hồi thay đổi theo thời gian: schema, DB version, vùng mạng, secrets, image Java, công cụ backup, số lượng replica, số tenant và cấu trúc team đều có thể đổi. Vì vậy, một lần diễn tập thành công không phải chứng nhận vĩnh viễn.

Một chương trình có thể được thiết kế theo chu kỳ minh họa:

| Cấp độ | Khi nào thực hiện | Mục đích |
| --- | --- | --- |
| **Tự động hằng lần build** | CI với DB test/container | Rollback, idempotency, SQL invariants và retry logic |
| **Restore drill theo lịch** | Chu kỳ phù hợp rủi ro/retention | Xác nhận backup thật dùng được, role/schema/WAL không thiếu |
| **Tabletop sau thay đổi lớn** | Thay cluster, cloud, on-call hoặc kiến trúc | Xác minh vai trò, quyền và các giả định |
| **Failover/game day định kỳ** | Staging hoặc phạm vi được phê duyệt | Đo RTO, pool reconnection, replication và luồng vận hành |
| **Diễn tập lại sau sự cố/khắc phục** | Sau khi đóng action item | Chứng minh lỗi cũ không tái hiện |

Tần suất cụ thể phụ thuộc nghĩa vụ tuân thủ, RPO/RTO, mức độ thay đổi và tổn thất tiềm tàng. Không chọn lịch máy móc làm các đội không còn đủ khả năng phân tích kết quả. Tăng độ khó từng bước: từ single-node restart đến WAL restore, rồi failover và đối soát đa dịch vụ, luôn có **điều kiện dừng và quyền phê duyệt**.

Khi chạy nhiều lần, so sánh **cùng phạm vi và dữ liệu đại diện**. Một restore 1 GB thành công trong 30 giây không chứng minh bản database 4 TB hồi phục trong vài phút. Cần ghi khối lượng dữ liệu, WAL backlog, tài nguyên lab và chênh lệch so với production trong report.

## 13. Bài tập thực hành

### Bài tập 1: DB healthy nhưng API vẫn lỗi

Sau failover, PostgreSQL nhận kết nối nhưng 70% request Java báo timeout vì connection pool chưa cập nhật endpoint. Đội vận hành đo RTO từ lúc DB bắt đầu nhận TCP và tuyên bố đạt mục tiêu. Cách đo có hợp lệ không?

**Đáp án:** không, nếu RTO được định nghĩa cho dịch vụ nghiệp vụ. Phải đo tới khi API thiết yếu đọc/ghi thành công và pool kết nối đúng leader. Lưu riêng thời điểm DB healthy và application recovered để biết phần trễ nằm ở đâu.

### Bài tập 2: RPO và replica bất đồng bộ

Primary đã ACK 100 operation ID; sau khi nó hỏng, replica được promote chỉ còn 98 ID. Có thể kết luận cơ chế replication bị lỗi không?

**Đáp án:** chưa thể kết luận chỉ từ con số ấy. Với async replication, có thể có khoảng mất dữ liệu khi primary chết; cần so với RPO đã cam kết, xác định hai ID bị mất, mốc WAL và cách đối soát nghiệp vụ. Nếu cam kết zero data loss, kết quả không đạt.

### Bài tập 3: restore có đủ file nhưng thiếu role

File backup và checksum đều hợp lệ, DB restore mở được, nhưng Java app không chạy do thiếu quyền role và migration. Diễn tập có thành công không?

**Đáp án:** chưa đạt năng lực phục hồi end-to-end. Runbook phải bao gồm global objects/role, schema version, extension, secret/TLS và smoke check ứng dụng. Chỉ verify file không chứng minh phục hồi nghiệp vụ.

### Bài tập 4: outbox bị gửi lại

Sau restore, bản ghi event E trở về `PENDING` dù broker đã giao E trước sự cố. Worker phát lại E. Có nên đánh dấu cuộc diễn tập thất bại ngay vì có hai lần publish?

**Đáp án:** không nhất thiết. Transactional outbox thường cung cấp at-least-once; phát lại có thể hợp lệ. Điều phải kiểm chứng là **tác dụng nghiệp vụ** tại consumer/nhà cung cấp ngoài không bị nhân đôi, nhờ ID ổn định, dedupe và đối soát.

### Bài tập 5: tabletop phát hiện thiếu quyền

Trong tabletop, nhóm nhận ra không ai trong ca trực có quyền truy cập backup encryption key. Chưa hề chạy restore. Đây có phải kết quả hữu ích không?

**Đáp án:** có. Diễn tập đã phát hiện một **operational gap** có thể làm RTO không đạt khi sự cố thật xảy ra. Cần sửa quyền theo nguyên tắc tối thiểu, thiết kế cơ chế cấp quyền khẩn cấp có audit và diễn tập restore thật sau đó.

### Bài tập 6: đánh giá kết quả thiếu chứng cứ

Một lần thử failover báo “không mất dữ liệu”, nhưng bộ phát tải không lưu operation ID đã ACK ở ngoài DB; chỉ so số hàng trước và sau. Nên chấm PASS hay INCONCLUSIVE?

**Đáp án:** **INCONCLUSIVE** đối với tiêu chí RPO/tính đầy đủ giao dịch. Tổng số hàng không chứng minh đúng tập commit. Cần lưu danh sách ID/commit marker độc lập và so sánh sau phục hồi.

### Checklist trước khi kết thúc một lần diễn tập

- Có xác định **loại sự cố, ranh giới hệ thống, RPO/RTO, invariant và phạm vi tác động** trước khi chạy chưa?
- Môi trường test được cách ly với production, nhất là broker/payment/email và secret thật, chưa?
- Có baseline gồm topology, schema, backup/WAL và **operation ID đã ACK** được lưu ngoài thành phần chịu fault chưa?
- Fault đã thực sự tác động đúng nơi/đúng thời điểm, có bằng chứng và điều kiện dừng khẩn cấp chưa?
- Có kiểm tra fencing/leader, khả năng tạo connection mới, pool, quyền DB và đường đọc/ghi Java sau recovery chưa?
- Có đối soát dữ liệu bằng ID/version/ledger/outbox, không chỉ nhìn health hoặc số hàng, chưa?
- Có đo RTO tới **dịch vụ thiết yếu hoạt động**, RPO tới **mốc commit thực sự**, và lưu từng timestamp chưa?
- Worker/inbox/outbox có xử lý lại an toàn; không tự động tác động lên hệ thống ngoài chưa?
- Báo cáo có phân biệt PASS/FAIL/INCONCLUSIVE, nguyên nhân, owner và lịch thử lại sau sửa không?
- Runbook, quyền và tài liệu giám sát có được cập nhật theo những phát hiện trong diễn tập chưa?

**Kết luận:** Năng lực phục hồi không thể được chứng minh chỉ bằng việc có backup, replica hoặc dashboard. Nó phải được **diễn tập có kiểm soát**, từ phát hiện lỗi, quyết định hành động, khôi phục database và Java service tới kiểm chứng dữ liệu và đối soát các tác động bên ngoài. Một diễn tập tốt có mục tiêu RPO/RTO rõ ràng, môi trường an toàn, bằng chứng transaction/operation ID, runbook thực hành được và hành động cải tiến có người chịu trách nhiệm. Khi lặp lại những phép thử này sau các thay đổi quan trọng, tổ chức mới có cơ sở thực tế để tin rằng hệ thống persistence có thể phục hồi **đúng dữ liệu, đúng quy trình và trong thời gian cần thiết**.
