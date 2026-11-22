# Phân biệt hoàn tất lời gọi ghi với dữ liệu đã bền vững

Trong ứng dụng Java, một lệnh ghi trả về thành công **không nhất thiết** chứng minh dữ liệu đã an toàn trước mọi sự cố. Một phương thức repository có thể hoàn tất khi transaction vẫn chưa commit. Câu lệnh COMMIT có thể được cơ sở dữ liệu xác nhận sau khi nhật ký giao dịch đã được đồng bộ tới bộ lưu trữ, nhưng bản sao ở trung tâm dữ liệu khác chưa nhận được dữ liệu. Ngược lại, đôi khi database đã commit thành công nhưng mạng bị ngắt trước khi ứng dụng nhận phản hồi, làm kết quả từ góc nhìn ứng dụng trở nên **chưa rõ**.

Bài học thuộc chương **Độ bền dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là làm rõ những lời hứa mà tầng persistence trong Java có thể đưa ra: từ JDBC, transaction, WAL và cơ chế đồng bộ đĩa đến replica, sao lưu, failover và khôi phục. Khi hiểu chính xác các mốc này, người học có thể thiết kế việc ghi, xử lý lỗi kết nối và xác nhận thành công theo đúng yêu cầu nghiệp vụ.

> **Thông điệp chính:** “Lệnh ghi đã chạy xong”, “giao dịch đã commit”, “đã được ghi bền vững trên một máy”, “đã được sao chép an toàn” và “có thể phục hồi sau thảm họa” là các trạng thái khác nhau. Mỗi trạng thái cần cơ chế và bằng chứng riêng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt thành công của một lời gọi Java/JDBC với việc commit và độ bền vật lý của dữ liệu.
- Mô tả đường đi từ bộ đệm ứng dụng đến cơ sở dữ liệu, WAL, hệ điều hành và thiết bị lưu trữ.
- Giải thích vì sao fsync, cấu hình synchronous commit, replication và backup ảnh hưởng phạm vi bảo đảm.
- Phân tích các cửa sổ lỗi trước/sau commit, bao gồm trường hợp ACK bị mất.
- Thiết kế API ghi có idempotency key và cách xác minh khi trạng thái commit không rõ.
- Kiểm tra độ bền qua truy vấn cấu hình, bài thử crash có kiểm soát và diễn tập khôi phục.
- Đặt ranh giới giao dịch đúng trong JDBC/Spring và nói chính xác với người dùng về mức thành công của thao tác.

## 2. “Ghi thành công” có nhiều nghĩa

Xét một chức năng chuyển tiền. Java gọi một repository để ghi hai bút toán vào PostgreSQL:

~~~java
int affectedRows = jdbcTemplate.update(
    "UPDATE accounts SET balance = balance - ? WHERE id = ?",
    amount, senderId
);
~~~

Nếu affectedRows bằng 1, điều đó nói rằng lệnh UPDATE đã tác động tới một hàng **theo ngữ cảnh transaction của lời gọi**. Nó không tự chứng minh transaction đang mở đã commit, rằng phần bù tăng số dư người nhận cũng thành công, hay rằng WAL đã được flush tới storage.

Nên tách ít nhất sáu mốc:

| Mốc | Có thể nói điều gì? | Chưa thể kết luận |
|---|---|---|
| **A. Java nhận kết quả lệnh SQL** | Server đã xử lý câu lệnh và trả kết quả theo giao thức hiện tại | Nếu transaction vẫn mở, dữ liệu chưa commit; chưa biết kết quả của các câu lệnh sau |
| **B. Transaction commit được database xác nhận** | DB công nhận transaction đã commit theo cấu hình hiện hành | Chưa chắc dữ liệu đã có trên replica/backup; độ bền khi mất điện phụ thuộc cấu hình và hạ tầng |
| **C. Nhật ký commit đã được làm bền vững trên máy chính** | Với cơ chế và thiết bị hoạt động đúng, có thể khôi phục sau crash thuộc phạm vi bảo đảm | Không loại bỏ rủi ro hỏng máy/thiết bị hoặc mất cả vùng |
| **D. Replica nhận/ghi/flush/apply thay đổi** | Tùy chế độ, có bản sao đã đến một mốc cụ thể | Không phải mọi ACK sao chép đều hàm ý cùng mức độ bền hoặc đã phục vụ được truy vấn đọc |
| **E. Backup/snapshot phục hồi được** | Dữ liệu nằm trong điểm khôi phục đã được kiểm chứng | Không có nghĩa mọi giao dịch mới nhất đều có trong backup |
| **F. Nghiệp vụ hoàn tất xuyên các dịch vụ** | Các bước phụ thuộc như thanh toán, kho, sự kiện đã đạt trạng thái yêu cầu | Một COMMIT DB cục bộ không tự bảo đảm trạng thái này |

Vì thế, tên hàm save(), flush(), executeUpdate() hoặc send() chỉ nói về **API được gọi**. Muốn biết điểm bền vững, phải xét transaction manager, DBMS, cấu hình, replica và phạm vi sự cố.

### 2.1. Commit, visibility và durability là ba chiều khác nhau

- **Atomicity:** các thay đổi của một transaction được công bố cùng nhau hoặc không được công bố, trong phạm vi nguồn dữ liệu hỗ trợ transaction.
- **Visibility / isolation:** những transaction khác được phép nhìn thấy thay đổi khi nào và theo snapshot nào.
- **Durability:** sau khi database công nhận một commit, dữ liệu có còn tồn tại sau loại sự cố được hệ thống hứa bảo vệ hay không.

Ví dụ một transaction đã ghi UPDATE nhưng chưa commit. Chính transaction đó có thể đọc lại giá trị mới; transaction khác thường chưa thấy giá trị mới theo cơ chế cô lập phù hợp. Sự khác nhau về *tầm nhìn dữ liệu* này không chứng minh giá trị mới đã bền vững.

Ngược lại, một bản sao bất đồng bộ có thể chưa thấy transaction đã commit bền vững trên primary. Trạng thái chưa thấy trên replica là chuyện **độ trễ sao chép hoặc tính nhất quán đọc**, không nhất thiết là thất bại durability của primary.

## 3. Đường đi từ lệnh Java đến lưu trữ bền vững

Một mô hình giản lược cho hệ quản trị ghi nhật ký trước (write-ahead logging, WAL):

~~~mermaid
flowchart TD
    A["Java / JDBC<br/>executeUpdate"] --> B["DB transaction đang mở"]
    B --> C["Sửa các trang dữ liệu trong bộ nhớ"]
    C --> D["Sinh WAL mô tả thay đổi"]
    D --> E["COMMIT và WAL commit record"]
    E --> F["Ghi/flush WAL theo cấu hình"]
    F --> G["DB gửi ACK commit"]
    G --> H["Java nhận kết quả"]
    F --> I["Crash recovery có thể replay WAL"]
    D -.-> J["Các data page được ghi xuống đĩa sau"]
~~~

Sơ đồ là mô hình ý tưởng, không phải lời khẳng định mọi DBMS đều có đúng cùng luồng nội bộ. Trong cơ chế WAL, dữ liệu trên trang chính có thể được ghi ra sau; bộ máy phục hồi dùng các bản ghi nhật ký cần thiết để khôi phục trạng thái đã commit.

### 3.1. Bộ đệm ứng dụng không phải storage bền vững

Một lớp trong Java có thể ghi dữ liệu vào buffer của thư viện. flush() của stream thường đẩy dữ liệu từ buffer Java sang lớp bên dưới; thao tác đó **không mặc định yêu cầu thiết bị lưu trữ xác nhận ghi bền vững**.

Ngay cả khi write() của hệ điều hành trả thành công, dữ liệu có thể còn trong page cache của OS. Nếu nguồn điện hoặc hệ điều hành gặp sự cố trước khi đồng bộ thích hợp, dữ liệu gần đây có thể bị mất.

### 3.2. Database buffer và WAL có vai trò khác nhau

Hệ quản trị cơ sở dữ liệu thường giữ những trang dữ liệu trong buffer pool để giảm chi phí I/O. Khi ghi, nó có thể làm bẩn trang trong bộ nhớ và sinh bản ghi WAL trước khi trang dữ liệu thực sự được flush xuống đĩa.

**Nguyên lý write-ahead:** nhật ký cần thiết cho việc khôi phục phải đạt mốc bền vững phù hợp trước khi các trang dữ liệu đã thay đổi được ghi theo cách có thể phá tính đúng đắn sau crash.

Ở những DBMS như PostgreSQL, WAL giúp phục hồi các transaction đã commit sau sự cố ngay cả khi trang dữ liệu chính chưa kịp được ghi ra thiết bị. Nếu bỏ qua điều kiện bảo đảm của WAL/flush, chỉ việc thấy trang dữ liệu thay đổi trong cache không đủ kết luận.

### 3.3. write(), flush(), fsync() và thiết bị lưu trữ

Có thể hình dung một chuỗi trừu tượng:

~~~text
Ứng dụng Java
    -> thư viện / user-space buffer
    -> hệ điều hành / page cache
    -> filesystem và tầng block
    -> controller / thiết bị lưu trữ bền vững
~~~

Các tên thao tác dễ gây nhầm:

| Thao tác hoặc khái niệm | Thường mang ý nghĩa gì? | Giới hạn |
|---|---|---|
| Java OutputStream.flush() | Đẩy buffer thuộc stream xuống tầng dưới | Không mặc nhiên bằng fsync |
| File write() hoàn thành | OS nhận/yêu cầu ghi số byte được báo | Có thể còn dữ liệu trong cache |
| fsync()/fdatasync() hoặc FileChannel.force() | Yêu cầu đồng bộ thay đổi tới thiết bị theo ngữ nghĩa API/hệ điều hành | Độ an toàn còn phụ thuộc filesystem, storage/controller và việc phần cứng thực hiện đúng cam kết |
| DB COMMIT | Kết thúc giao dịch theo hợp đồng của DBMS | Thời điểm ACK và độ bền phụ thuộc thiết lập log/commit |
| Replica ACK | Một mốc sao chép được xác nhận | “Nhận”, “ghi vào OS”, “flush bền vững” và “apply” có thể khác nhau |
| Backup hoàn thành | Đã tạo một bộ dữ liệu phục vụ khôi phục | Phải kiểm tra tính nhất quán, chuỗi WAL, quyền truy cập và khả năng restore |

Ngay cả khi chương trình gọi fsync thành công, cần xem thiết bị có bộ nhớ đệm được bảo vệ trước mất điện, filesystem có đáp ứng contract và có kiểm chứng phục hồi thực tế hay không. Không đồng nhất một syscall thành “bất khả mất dữ liệu trong mọi tình huống”.

## 4. Một transaction SQL hoàn tất như thế nào?

Xét ví dụ đặt hàng có hai câu ghi liên quan:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status)
VALUES ('6bff7a7e-6c2e-4d73-8ca2-93f9f527b009', 101, 'PENDING');

INSERT INTO order_audit (order_id, action)
VALUES ('6bff7a7e-6c2e-4d73-8ca2-93f9f527b009', 'CREATED');

COMMIT;
~~~

Các mốc quan trọng:

1. BEGIN tạo ngữ cảnh giao dịch.
2. INSERT đầu tiên được server xác nhận nhưng transaction còn mở.
3. INSERT thứ hai có thể thành công hoặc thất bại; chưa có kết quả commit.
4. COMMIT là điểm database chốt quyết định về transaction; nếu nhận ACK thành công, cần diễn giải theo cấu hình durability của hệ quản trị.
5. Nếu kết nối bị ngắt trong lúc COMMIT, ứng dụng có thể **không biết commit đã diễn ra hay chưa**. Cần tra cứu theo một định danh nghiệp vụ ổn định.

### 4.1. Nếu một INSERT thành công nhưng transaction sau đó ROLLBACK?

Transaction không được commit, do đó thay đổi trong transaction không xuất hiện như dữ liệu đã commit. Một lệnh INSERT “success” trước đó không đồng nghĩa người dùng có đơn hàng.

### 4.2. Nếu COMMIT thành công nhưng máy chủ DB crash?

Nếu DB đã đảm bảo flush nhật ký commit bền vững và storage thực hiện đúng hợp đồng, bộ máy khôi phục được thiết kế để giữ các transaction đã commit qua crash trong phạm vi bảo đảm. Nếu chế độ commit cho phép ACK trước khi log được làm bền vững, **một số transaction đã được ACK gần thời điểm crash có thể mất**.

### 4.3. Nếu COMMIT đã thực hiện nhưng response đến Java bị mất?

Từ phía Java, việc nhận SQLException hoặc timeout không luôn phân biệt được:

- COMMIT chưa được DB xử lý.
- COMMIT đã được xử lý nhưng DB trả lỗi trước khi chốt.
- COMMIT đã được chốt, còn ACK bị mất trên mạng.
- Connection bị ngắt khi kết quả đang được gửi.

Đó là **ambiguous commit outcome**. Không tự động gọi lại toàn bộ nghiệp vụ với một ID mới vì có thể tạo bản ghi hoặc trừ tiền hai lần.

## 5. Bảng lỗi: hành động nào đã bền vững?

Giả sử JDBC autoCommit=false, DB chính dùng cấu hình synchronous commit có đảm bảo WAL flush cục bộ, storage hoạt động đúng hợp đồng:

| Thời điểm sự cố | Có thể khẳng định điều gì? | Cách xử lý |
|---|---|---|
| Java chưa gửi SQL | DB chưa nhận lệnh này | Có thể thử lại theo logic nghiệp vụ |
| SQL đã chạy nhưng chưa COMMIT | Transaction chưa được công bố; server sẽ rollback nếu phiên giao dịch bị hủy | Không báo người dùng đã lưu xong |
| DB crash trong lúc COMMIT, chưa có kết quả rõ | Có thể đã commit hoặc chưa; client không biết | Kiểm tra lại trạng thái sau phục hồi bằng business key |
| DB xác nhận COMMIT, sau đó chỉ tiến trình Java crash | DB đã commit; crash JVM không hủy commit | Khi restart, phục hồi tiến trình dựa trên ID/trạng thái bền vững |
| COMMIT đã flush WAL bền vững, DB/OS crash sau đó | Recovery phải khôi phục commit trong phạm vi bảo đảm | Kiểm tra startup/recovery, không replay nghiệp vụ tùy tiện |
| Commit ACK trước flush do cấu hình không đồng bộ, OS crash | Có thể mất một số commit gần nhất | Chỉ chấp nhận khi yêu cầu RPO và rủi ro phù hợp |
| Primary mất vĩnh viễn, chỉ còn replica bất đồng bộ đang trễ | Một số commit ở primary có thể không có trên replica | Đánh giá replication policy, RPO và failover |
| Mất cả cụm lưu trữ, phải restore backup cũ | Chỉ phục hồi được đến mốc có trong backup/WAL còn lưu | Cần backup, lưu trữ ngoài vùng lỗi và diễn tập restore |

Bảng này không ngụ ý “mất ACK tức là rollback”. **Mất phản hồi khác với thất bại thực thi**, và phải được thiết kế như một trạng thái riêng.

## 6. PostgreSQL: synchronous_commit, fsync và WAL

PostgreSQL là ví dụ cụ thể để làm rõ các lựa chọn. Khả năng bền vững không được xác định chỉ bằng tên DBMS, mà còn bằng cấu hình vận hành và hành vi storage.

Đọc các cài đặt liên quan:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW synchronous_standby_names;
SHOW full_page_writes;
SHOW wal_level;
~~~

Đây là các lệnh đọc cấu hình. Kết quả cần được đối chiếu với phiên bản PostgreSQL, cấu hình thực tế và tài liệu vận hành của cụm.

### 6.1. fsync và full_page_writes

- **fsync = on:** PostgreSQL cố gắng bảo đảm các thay đổi cần thiết đã được đồng bộ đến thiết bị theo contract của hệ điều hành/lưu trữ. Tắt fsync có thể khiến database không phục hồi an toàn sau crash; không dùng việc tắt nó như “mẹo” tối ưu tùy tiện.
- **full_page_writes = on:** hỗ trợ phục hồi khỏi tình huống trang dữ liệu ghi dở (torn page) bằng cách ghi thông tin cần thiết trong WAL, đặc biệt sau checkpoint. Đây là thành phần quan trọng của crash safety theo cấu hình thông thường.

Việc commit bền vững dựa trên một chuỗi điều kiện: cơ chế WAL đúng, flush thích hợp, thiết bị thực sự giữ dữ liệu, và khả năng replay WAL sau crash. Không thể tách từng cấu hình khỏi hệ thống còn lại.

### 6.2. synchronous_commit thay đổi mốc ACK

Các chế độ thường gặp trong PostgreSQL:

| Giá trị | Mốc xác nhận theo ý tưởng | Điều cần nhớ |
|---|---|---|
| off | Có thể trả kết quả commit trước khi WAL commit record được flush cục bộ | Crash DB/OS có thể mất một số commit vừa ACK; không đồng nghĩa database tự mất tính nhất quán cấu trúc nếu những bảo đảm còn lại được duy trì |
| local | Chờ WAL commit record được flush cục bộ | Không chờ remote flush dù có synchronous standby |
| on | Chờ WAL flush cục bộ và, nếu cấu hình standby đồng bộ phù hợp, chờ mốc flush trên standby theo yêu cầu | Không có synchronous standby đang áp dụng thì không được tự suy ra đã có bản sao bền vững |
| remote_write | Với synchronous standby tương ứng, chờ standby ghi WAL tới hệ điều hành nhưng chưa nhất thiết flush ra storage bền vững | Có thể chống lỗi tiến trình ở standby trong những trường hợp nhất định nhưng không có cùng mức bảo vệ như remote flush khi mất điện trên standby |
| remote_apply | Với synchronous standby tương ứng, chờ standby apply commit và cho phép transaction khả kiến trên standby theo ngữ nghĩa của chế độ | Tăng độ trễ, phụ thuộc availability của synchronous standby và cấu hình |

Các chế độ liên quan remote chỉ có ý nghĩa khi cơ chế synchronous replication được cấu hình và standby thực sự tham gia. Tên tham số synchronous_commit **không tự chứng minh** có replica, replica đã bền vững hoặc dữ liệu tồn tại ở một vùng độc lập.

Ở chế độ synchronous commit mặc định phù hợp, PostgreSQL có thể xác nhận commit sau khi WAL đã flush cục bộ; trang dữ liệu trong bảng không cần được ghi vật lý ngay tại thời điểm đó, vì WAL phục vụ crash recovery.

### 6.3. Đồng bộ, hiệu năng và rủi ro

Một ứng dụng ghi nhiều giao dịch nhỏ có thể giảm độ trễ khi cho phép commit bất đồng bộ, vì không phải giao dịch nào cũng chờ cùng mốc flush. Đổi lại, nó chấp nhận một cửa sổ có thể mất commit vừa được ACK nếu DB/OS bị crash.

Ngược lại, synchronous replication có thể tăng độ bền trước mất primary nếu standby thật sự nhận và flush commit theo cấu hình, nhưng tăng phụ thuộc mạng và availability của standby. Khi standby không sẵn sàng, giao dịch có thể phải chờ và không đạt latency mục tiêu. Đây là quyết định về **RPO, RTO, topology và hiệu năng**, không chỉ là bật một lựa chọn để “nhanh hơn”.

Không thay đổi các cài đặt durability trên production khi chưa được đánh giá, phê duyệt và đo tác động. Trong bài này, các lệnh SHOW chỉ dùng để quan sát.

## 7. JDBC: executeUpdate thành công khác commit thành công

Ví dụ SQL được gọi theo autoCommit=false:

~~~java
public UUID createOrder(DataSource dataSource, UUID orderId, long customerId)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            try (PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO orders(order_id, customer_id, status) " +
                    "VALUES (?, ?, 'PENDING')")) {
                statement.setObject(1, orderId);
                statement.setLong(2, customerId);

                int rows = statement.executeUpdate();
                if (rows != 1) {
                    throw new SQLException("Expected exactly one order row");
                }
                // Đây là thành công của statement trong transaction.
            }

            connection.commit();
            // Từ đây DB đã xác nhận commit theo cấu hình hiện hành.
            return orderId;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback(); // Cố gắng dọn transaction nếu còn mở.
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}
~~~

Những chi tiết cần chú ý:

- executeUpdate() trả về số hàng tác động của **statement**, không phải chứng nhận mọi transaction liên quan đã commit.
- commit() là thao tác khác; nó cũng có thể ném exception.
- Nếu commit() ném lỗi vì mất kết nối, rollback() thử sau đó có thể thất bại hoặc không thể đổi quyết định commit đã được server chốt. **Không khẳng định “rollback rồi, chắc chắn chưa tạo đơn”** trong trường hợp commit outcome chưa rõ.
- Nếu dùng autoCommit=true, JDBC thông thường commit mỗi statement khi hoàn tất theo hợp đồng của driver/DB. Tuy vậy độ bền còn phụ thuộc cấu hình DB, không đồng nghĩa đã sao chép hay backup.
- Những thay đổi tại database khác hoặc API ngoài không tham gia transaction này chỉ vì code nằm trong cùng method Java.

Ví dụ giả định schema có cột order_id kiểu UUID và status hợp lệ. Code minh họa trình tự xử lý; ứng dụng thực tế cần kiểm soát chính sách kết nối, transaction manager, timeout, idempotency và ranh giới nghiệp vụ.

### 7.1. Khi commit outcome chưa rõ: dùng một business key ổn định

Nếu request bị timeout sau khi DB đã có thể commit, client có thể retry. Không sinh orderId mới cho mỗi attempt của **cùng một yêu cầu nghiệp vụ**. Hãy giữ requestId do client cung cấp hoặc do server cấp ổn định và đặt UNIQUE constraint:

~~~sql
CREATE TABLE order_requests (
    request_id uuid PRIMARY KEY,
    order_id   uuid NOT NULL UNIQUE,
    status     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Luồng xử lý điển hình:

1. Client gửi requestId=R ổn định; server xác thực request và kiểm tra xem R đã có kết quả hay chưa.
2. Trong một local transaction, ghi requestId=R, order và các thay đổi cần commit nguyên tử.
3. Nếu trả về thành công, cung cấp orderId tương ứng.
4. Nếu mất kết nối ngay lúc commit, trước khi thử lại với requestId=R, đọc lại trạng thái từ nguồn dữ liệu authoritative sau khi DB sẵn sàng.
5. Nếu R đã có kết quả, trả lại kết quả hiện có; nếu chưa và không có một attempt đang xử lý, tiếp tục theo chính sách retry an toàn.

Cần xử lý **đồng thời hai attempt mang cùng requestId**, ví dụ bằng UNIQUE constraint và logic đọc lại sau xung đột. Nếu cơ chế lưu kết quả chỉ nằm trong bộ nhớ Java, restart hoặc chạy nhiều instance sẽ làm mất khả năng chống trùng.

Idempotency key giải quyết nguy cơ *lặp tác động nghiệp vụ* khi request được gửi lại; nó không tự làm dữ liệu trên primary bền hơn trước lỗi storage.

## 8. Spring @Transactional: khi nào lời gọi method thực sự đã commit?

Ví dụ tầng service dùng Spring transaction manager:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public UUID placeOrder(UUID orderId, long customerId) {
        orders.insert(orderId, customerId);
        return orderId; // Lúc return bên trong method, proxy còn phải commit.
    }
}
~~~

Với lời gọi đi qua transactional proxy và **một transaction mới do proxy tạo**, trình tự khái quát là:

~~~text
Caller
  |
  v
Spring transaction proxy: BEGIN
  |
  v
OrderService.placeOrder()
  |
  +-- Repository INSERT -> statement thành công
  |
  +-- Method trả về orderId cho proxy
  |
  v
Spring transaction proxy: COMMIT
  |
  v
Proxy trả orderId cho caller
~~~

Nếu COMMIT thất bại và transaction manager ném lỗi, caller không nhất thiết nhận return value bình thường dù phần thân method đã chạy xong.

**Hai ngoại lệ quan trọng khi suy luận về thời điểm commit:**

1. Nếu method **tham gia một transaction đã tồn tại** theo propagation mặc định, nó không tự commit khi kết thúc. Transaction bên ngoài có thể còn chạy rất lâu và sau cùng rollback.
2. Nếu lời gọi nội bộ dùng this.placeOrder() trong cùng bean theo cơ chế proxy thường gặp, annotation có thể không được áp dụng như dự định.

Cần kiểm tra transaction manager, DataSource và propagation thực tế trước khi dùng tên method hoặc log của repository để tuyên bố ghi đã bền vững.

### 8.1. Flush của ORM không phải COMMIT

JPA EntityManager.flush() khiến những thay đổi đang chờ trong persistence context được đồng bộ thành các câu SQL theo cơ chế ORM. Nó **không tương đương** một lời gọi commit transaction. Những INSERT hoặc UPDATE đã phát trong flush vẫn có thể rollback.

Ví dụ:

~~~java
@Transactional
public void createOrder(Order order) {
    entityManager.persist(order);
    entityManager.flush();     // SQL có thể đã được gửi.
    validateAdditionalRules(); // Nếu lỗi, transaction vẫn có thể rollback.
}
~~~

Nếu log ghi SQL INSERT đã chạy trước khi validateAdditionalRules() ném exception, điều đó không chứng minh dữ liệu đã commit. Cần quan sát kết quả transaction do framework điều phối.

### 8.2. Đừng dùng callback sau commit như nhật ký bền vững

Một callback Spring chạy sau commit có thể phù hợp để thực hiện việc không quá quan trọng, nhưng nó thường nằm trong cùng tiến trình Java:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendNotification(OrderCreated event) {
    emailClient.send(event);
}
~~~

Nếu DB đã commit rồi JVM chết trước khi callback được thực thi, email có thể không được gửi. Nếu email đã được gửi nhưng phản hồi mất, việc thử lại có thể gây trùng. **Commit DB không tự làm một callback in-memory trở nên durable.**

Khi tác vụ phụ thuộc bắt buộc phải được thực hiện sau commit, mô hình transactional outbox có thể ghi bản ghi cần phát vào cùng transaction với dữ liệu nghiệp vụ; một worker đọc outbox và gửi với retry/idempotency. Tuy nhiên outbox giải quyết phối hợp **ý định phát**, không thay thế cơ chế WAL/fsync và sao lưu để đảm bảo sự tồn tại của database.

## 9. File I/O: write() và flush() chưa đủ cho dữ liệu quan trọng

Không phải mọi persistence đều dùng RDBMS. Nếu ứng dụng Java tự ghi file cấu hình hoặc checkpoint, nó cũng cần phân biệt nhận dữ liệu vào bộ đệm với đã bền vững.

Ví dụ tối giản:

~~~java
Path target = Path.of("checkpoint.dat");
byte[] content = checkpointBytes();

try (FileChannel channel = FileChannel.open(
        target,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer buffer = ByteBuffer.wrap(content);
    while (buffer.hasRemaining()) {
        channel.write(buffer);
    }
    channel.force(true);
}
~~~

Đoạn code yêu cầu force() sau khi ghi. Nhưng cách **TRUNCATE_EXISTING rồi ghi** chưa an toàn về mặt thay thế file: nếu tiến trình hoặc máy crash giữa chừng, file cũ có thể đã bị cắt, trong khi file mới chưa hoàn chỉnh.

Đối với checkpoint đòi hỏi nguyên tử khi thay thế, một chiến lược thường dùng là:

1. Ghi toàn bộ nội dung vào một file tạm **cùng filesystem**.
2. Đồng bộ file tạm theo contract hệ điều hành.
3. Đổi tên/move file tạm thành tên chính bằng thao tác atomic move **nếu filesystem hỗ trợ**.
4. Đồng bộ metadata của thư mục cha khi môi trường đòi hỏi điều đó để bảo đảm bản ghi tên file sau crash; việc này có chi tiết phụ thuộc hệ điều hành/filesystem.
5. Kiểm thử crash recovery; giữ phiên bản/checksum để phát hiện file hỏng.

Không khẳng định Files.move(..., ATOMIC_MOVE) tự cung cấp mọi bảo đảm durability trên mọi hệ điều hành. Atomicity của rename và durability của directory entry là hai câu hỏi khác nhau.

Đối với dữ liệu có giao dịch phức tạp, thường nên giao phần này cho database đã được thiết kế và vận hành đúng, thay vì tự xây hệ thống lưu trữ dựa trên các lần ghi file rời rạc.

## 10. Đã commit trên primary khác với đã có bản sao an toàn

Một PostgreSQL primary có thể flush WAL, trả ACK commit rồi mất toàn bộ máy chủ. Nếu chỉ có replica **bất đồng bộ**, standby có thể chưa nhận transaction cuối cùng. Khi chuyển lưu lượng sang standby, một giao dịch được client xác nhận trước đó có thể không tồn tại trên primary mới.

~~~mermaid
sequenceDiagram
    participant J as Java API
    participant P as Primary DB
    participant S as Async standby
    J->>P: COMMIT T42
    P->>P: Flush WAL local
    P-->>J: COMMIT OK
    Note over P,S: WAL T42 chưa đến standby
    P-xP: Primary mất hoàn toàn
    Note over S: Promote standby
    J->>S: SELECT T42
    S-->>J: Không tìm thấy T42
~~~

Điều này **không phủ nhận** rằng T42 đã bền vững trên primary trước khi máy mất. Nó cho thấy bảo đảm local durability và **bảo đảm sau failover** có phạm vi lỗi khác nhau.

### 10.1. Các mốc sao chép

Đối với một replica dùng WAL/transaction log, nên phân biệt:

- **Received:** replica đã nhận dữ liệu truyền qua mạng.
- **Written:** đã ghi vào bộ đệm hệ điều hành trên replica.
- **Flushed:** đã đồng bộ vào phương tiện lưu trữ theo contract của replica.
- **Applied/Replayed:** thay đổi đã được áp dụng cho trạng thái mà truy vấn trên replica có thể quan sát theo cơ chế tương ứng.

Không dùng một câu “replica đã ACK” nếu không chỉ rõ ACK ở mốc nào.

### 10.2. Synchronous replication giải quyết một phần rủi ro

Khi chính sách commit chờ ít nhất một replica phù hợp flush dữ liệu, hệ thống có thể giảm nguy cơ mất transaction đã ACK nếu primary hỏng. Nhưng vẫn cần xét:

- Số replica và miền lỗi độc lập thực tế: cùng một nguồn điện hay cùng một vùng lưu trữ có thể làm cùng mất dữ liệu.
- Quy tắc failover và lựa chọn primary mới: phải chọn replica đạt yêu cầu và tránh hai primary hoạt động đồng thời.
- Trường hợp replica bị lỗi hoặc mạng phân vùng: synchronous commit có thể tăng thời gian chờ hoặc tạm ngừng chấp nhận ghi.
- Hạ tầng storage: “đã flush” chỉ đáng tin nếu storage đáp ứng đúng contract.
- Dữ liệu nằm ở backup nào và khả năng restore nếu cả primary lẫn replica cùng mất.

**Replicated không đồng nghĩa backed up.** Lệnh DELETE nhầm, corruption ở tầng ứng dụng hoặc ransomware có thể được sao chép tới nhiều replica. Backup có lịch sử/điểm khôi phục là lớp bảo vệ khác.

## 11. Durability trước crash khác với phục hồi sau thảm họa

Để đánh giá yêu cầu thực tế, phân loại sự cố thay vì chỉ nói “hệ thống có độ bền cao”:

| Loại sự cố | Câu hỏi về dữ liệu | Cơ chế cần đánh giá |
|---|---|---|
| JVM crash | DB đã commit có giữ dữ liệu không? | Transaction DB, trạng thái commit, idempotency |
| DB process crash | Commit được xác nhận có phục hồi sau restart không? | WAL, recovery, cấu hình commit |
| OS crash hoặc mất điện | Log đã được đồng bộ ra storage thích hợp chưa? | fsync, storage controller, nguồn điện |
| Hỏng disk/controller | Có bản sao bền vững độc lập hay redundancy? | RAID, replicated storage, replica, kiểm thử lỗi |
| Mất server/availability zone | Replica nào chứa transaction đã ACK? | Synchronous replication, miền lỗi, failover |
| Mất cả cụm hoặc region | Có bản sao/backup ở miền lỗi khác không? | Offsite backups, disaster recovery |
| Xóa nhầm hoặc ghi sai logic | Có thể quay về một thời điểm trước lỗi không? | Backup lịch sử, PITR, audit/reconciliation |
| Mất khóa mã hóa | Có giải mã/restore dữ liệu đã lưu được không? | Quản lý khóa, bản sao khóa, diễn tập recovery |

### 11.1. RPO và RTO

- **RPO (Recovery Point Objective):** mức mất dữ liệu theo thời gian có thể chấp nhận sau sự cố. Ví dụ RPO 5 phút nghĩa là mục tiêu phục hồi cho phép mất tối đa khoảng 5 phút thay đổi dữ liệu, không phải cam kết tự động đạt được.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ trở lại trạng thái hoạt động chấp nhận được.

Các mục tiêu này cần khớp với yêu cầu nghiệp vụ và thiết kế thực tế. **Một replica luôn sẵn sàng** có thể giúp RTO nhưng nếu đang trễ, RPO có thể chưa đạt. **Một backup đúng lịch** có thể giúp khôi phục dữ liệu lịch sử nhưng mất nhiều thời gian restore.

### 11.2. Backup thành công chỉ có giá trị khi restore được

Một hệ thống có thể báo “backup completed” nhưng vẫn không khôi phục được vì thiếu base backup, thiếu WAL lưu trữ, bản sao bị hỏng, khóa mã hóa không còn hoặc runbook sai.

Một quy trình kiểm chứng nên:

1. Chọn bộ backup và dữ liệu WAL cần thiết theo điểm khôi phục mong muốn.
2. Phục hồi vào môi trường độc lập, không ghi đè production.
3. Kiểm tra database khởi động được, schema nhất quán và dữ liệu mẫu có mặt.
4. Kiểm tra ứng dụng Java kết nối, truy vấn, xác minh các bất biến trọng yếu.
5. Đo thời gian phục hồi, điểm dữ liệu cuối khôi phục và xác định có đạt RPO/RTO không.

Việc có hàng triệu bản ghi được copy sang một ổ khác không đủ chứng minh backup có thể phục hồi thành một DB hợp lệ.

## 12. Lời gọi HTTP và message broker cũng có nhiều mức ACK

Khi ứng dụng Java gọi dịch vụ ngoài, cùng một vấn đề xảy ra: lời gọi trả 200/201/202 hoặc message producer nhận ACK chỉ có ý nghĩa trong **hợp đồng của dịch vụ đó**.

### 12.1. HTTP 200, 201 và 202

- HTTP 200/201 cho biết API phía nhận trả trạng thái thành công theo contract của endpoint. Nó **không tự chứng minh** kết quả đã nằm trên storage bền vững nếu contract không nói vậy.
- HTTP 202 Accepted thường có nghĩa yêu cầu đã được nhận để xử lý, có thể chưa hoàn tất tác vụ nền.
- HTTP timeout không chứng minh hệ đích không thực thi yêu cầu. Một request thanh toán có thể đã được ghi nhận ở phía nhà cung cấp dù client không nhận phản hồi.

Vì vậy, API chuyển tiền hoặc tạo đơn cần định nghĩa rõ “đã nhận yêu cầu”, “đã ghi trạng thái PENDING”, “đã xử lý thanh toán”, “đã hoàn tất nghiệp vụ” thay vì dùng một chữ success cho tất cả.

### 12.2. Broker ACK và độ bền thông điệp

Một producer gửi message và nhận ACK từ broker; ACK này phải được giải thích theo thiết lập persistence, số bản sao, quorum hoặc chế độ transaction của broker. Một số cấu hình có thể xác nhận khi message ở bộ nhớ hoặc khi đã được broker chấp nhận mà chưa đạt mức phục hồi mong muốn trước mọi sự cố.

Ngay cả khi broker đã lưu message bền vững, **consumer có thể xử lý rồi chết trước khi ACK**, khiến message được giao lại. Do đó cần consumer chịu được duplicate và đảm bảo tính đúng đắn khi xử lý.

Với thay đổi DB và thông điệp, hai commit độc lập tạo **dual-write problem**:

~~~text
DB COMMIT thành công ---- process chết ---- publish broker chưa xảy ra
broker publish thành công ---- DB ROLLBACK ---- event nói về dữ liệu không tồn tại
~~~

Transactional outbox lưu ý định phát message trong cùng DB transaction; worker sau đó phát với retry. Nó thường tạo semantics at-least-once cho bước publish khi vận hành đúng, nên consumer vẫn cần idempotency.

### 12.3. Object storage: PUT đã được nhận và bản sao ở đâu?

Dịch vụ object storage có thể có bảo đảm durability mạnh trong phạm vi sản phẩm, nhưng cần đọc contract về request ACK, versioning, replication giữa vùng, chính sách xóa và khả năng restore. Một PUT thành công không đồng nghĩa metadata của object trong một DB riêng đã commit nguyên tử.

Mẫu an toàn cho upload tài liệu thường dùng trạng thái PENDING/UPLOADING/READY, object key ổn định và job reconcile metadata với object. Nếu cần ngăn mất file do xóa nhầm, versioning và backup có vai trò khác với replication thông thường.

## 13. Kiểm chứng durability bằng thử nghiệm và quan sát

Độ bền là bảo đảm phải được kiểm tra **theo phạm vi lỗi cụ thể**, không thể kết luận chỉ bằng thời gian thực thi một câu INSERT. Một quy trình thử nghiệm có thể thực hiện trên môi trường staging được quản lý:

### 13.1. Thử nghiệm A: statement thành công, transaction chưa commit

1. Mở transaction trên một connection JDBC có autoCommit=false.
2. INSERT một bản ghi với requestId cố định.
3. Xác nhận executeUpdate() trả về thành công.
4. Từ connection khác, đọc theo requestId với mức cô lập thích hợp và kiểm tra bản ghi chưa khả kiến.
5. ROLLBACK transaction đầu tiên.
6. Đọc lại, xác nhận bản ghi không tồn tại ở trạng thái đã commit.

**Kết luận cần kiểm chứng:** statement thành công không bằng transaction commit. Không cần mô phỏng mất điện để minh họa điểm này.

### 13.2. Thử nghiệm B: commit đã xác nhận, DB process restart

1. Xác nhận cấu hình durability của DB và filesystem/storage staging.
2. COMMIT một bản ghi có ID đã biết, chỉ ghi log sau khi commit trả về bình thường.
3. Dừng/restart tiến trình DB theo kịch bản kiểm thử crash có chủ đích ở môi trường riêng, không phải tắt service bình thường.
4. Sau recovery, đọc lại bản ghi và các invariant liên quan.

**Lưu ý:** mô phỏng chết tiến trình DB chưa giống mất điện, vì page cache của hệ điều hành có thể vẫn còn. Muốn kiểm chứng power-loss recovery cần môi trường/hạ tầng thử nghiệm thích hợp và quy trình riêng. Một thử nghiệm thành công cũng không chứng minh mọi loại failure sau này đều được bảo vệ.

### 13.3. Thử nghiệm C: ACK commit bị mất

Dùng fault injection tại tầng mạng/proxy ở một môi trường riêng, tạo tình huống DB có thể đã thực hiện COMMIT nhưng client bị timeout hoặc mất kết nối trước khi nhận kết quả.

Ứng dụng cần:

- Ghi nhận trạng thái **UNKNOWN / cần xác minh** thay vì tự khẳng định rollback.
- Đọc lại theo requestId từ database authoritative sau khi kết nối phục hồi.
- Nếu ID đã tồn tại và trạng thái hợp lệ, trả lại kết quả tương ứng.
- Nếu chưa có kết quả, thực hiện retry theo chính sách đã bảo vệ bằng UNIQUE/idempotency.
- Đảm bảo một nghiệp vụ không tạo hai đơn, hai lệnh trừ tiền hay hai sự kiện thiếu kiểm soát.

Đây là bài kiểm thử khả năng phục hồi **kết quả chưa rõ**, không phải chỉ kiểm tra độ bền của log.

### 13.4. Thử nghiệm D: mất primary, failover sang replica

Tạo transaction có ID xác định, commit rồi mô phỏng primary không dùng được tại một mốc được kiểm soát. Kiểm tra primary mới chứa transaction đó hay không, so sánh với chính sách synchronous/asynchronous replication và khoảng lag thực tế.

Kết quả cần đánh giá theo **RPO sau failover**. Không dùng việc “primary từng trả COMMIT OK” để suy ra mọi replica đều đã có transaction.

### 13.5. Thử nghiệm E: restore backup

Lấy backup có mốc đã biết và phục hồi tới một điểm thời gian được chọn. Xác nhận dữ liệu, chỉ mục, constraint, khả năng kết nối ứng dụng và thời gian phục hồi.

Đây là cách kiểm tra khả năng **khôi phục**; việc nhìn thấy file backup hiện hữu trên storage chưa đủ.

## 14. Thiết kế một hợp đồng API ghi rõ ràng

Một API tạo đơn hàng cần định nghĩa lúc nào được trả kết quả “đã tạo” và lúc nào chỉ mới “đã nhận yêu cầu”. Ví dụ hợp đồng xử lý bất đồng bộ:

~~~text
POST /orders
Idempotency-Key: 7b285b32-0c66-4c96-8614-20b90307d72e

Bước 1: ghi order(status=PENDING) + outbox(event=OrderCreated)
        trong một local transaction.
Bước 2: COMMIT được DB xác nhận theo cấu hình durability.
Bước 3: HTTP 202 Accepted, trả orderId và trạng thái PENDING.
Bước 4: Worker phát event từ outbox; inventory/payment xử lý.
Bước 5: Order chuyển CONFIRMED hoặc CANCELLED.
Bước 6: GET /orders/{id} hoặc webhook có thể trả trạng thái cuối.
~~~

HTTP 202 chỉ hợp lý nếu hợp đồng endpoint thực sự là **xử lý bất đồng bộ**. Một API ghi đơn thuần có thể trả 201 sau DB commit thành công. Không chọn status code chỉ vì đang dùng message broker; hãy mô tả đúng mốc nghiệp vụ.

Nếu connection mất trong bước 2, handler không thể biết chắc đã commit hay chưa. Client sử dụng lại cùng Idempotency-Key giúp server tra cứu và trả cùng kết quả khi có thể. Nếu bản ghi đã tồn tại nhưng event chưa phát, outbox bền vững cho phép dispatcher tiếp tục sau restart.

**Giới hạn của lời hứa:** response thành công sau DB commit chỉ bảo đảm mức của DB theo cấu hình và storage, không mặc nhiên đồng nghĩa inventory đã giữ được hàng, payment đã hoàn tất hay backup ở vùng khác đã sẵn sàng.

### 14.1. Những từ ngữ nên dùng trong log, metric và giao diện

| Trạng thái | Cách hiểu rõ ràng |
|---|---|
| RECEIVED | Server đã nhận request; có thể chưa có ghi bền vững |
| VALIDATED | Đầu vào đã qua kiểm tra; chưa nhất thiết commit |
| DB_COMMITTED | Transaction cục bộ đã được DB xác nhận |
| PUBLISH_PENDING | Intent phát sự kiện đã được ghi; broker chưa chắc nhận |
| EVENT_ACKNOWLEDGED | Broker đã trả ACK theo chính sách của broker |
| REPLICATED | Cần ghi rõ bản sao, vị trí và mốc nhận/flush/apply |
| COMPLETED | Đã đạt trạng thái nghiệp vụ cuối cùng theo hợp đồng |
| UNKNOWN | Không xác định kết quả thực thi; cần reconciliation |

Không log mật khẩu, token hoặc dữ liệu thẻ nhạy cảm để theo dõi độ bền. Nên dùng transaction ID, requestId, orderId hoặc correlation ID phù hợp để lần theo công việc.

## 15. Checklist thiết kế và vận hành

- [ ] Biết lời gọi ghi đang nằm trong autoCommit hay một transaction do framework quản lý.
- [ ] Phân biệt executeUpdate/flush thành công với transaction COMMIT thành công.
- [ ] Biết DBMS, cấu hình WAL/fsync/synchronous commit và hợp đồng của thiết bị lưu trữ.
- [ ] Xác định phạm vi sự cố cần bảo vệ: process, OS, disk, server, vùng hoặc cả region.
- [ ] Không suy local durable thành replica durable hoặc đã có backup khôi phục được.
- [ ] Khi cần failover có RPO chặt, đã xác minh chính sách replication và cách promote replica.
- [ ] Có idempotency key/UNIQUE constraint cho request có thể bị gửi lại sau timeout.
- [ ] Có trạng thái xử lý kết quả COMMIT chưa rõ và cách đọc lại từ nguồn authoritative.
- [ ] Không gọi API ngoài trong DB transaction rồi coi API đó cũng được commit/rollback.
- [ ] Với dual-write bắt buộc, cân nhắc outbox, retry và consumer idempotent.
- [ ] Có backup độc lập, chính sách lưu giữ, bảo vệ khóa và diễn tập restore.
- [ ] Theo dõi latency commit, lỗi fsync/storage, replica lag, backlog WAL, độ trễ backup và thời gian phục hồi.
- [ ] Đã kiểm thử lỗi có kiểm soát trong staging; không dựa vào tên API hay một lần chạy đơn lẻ.

## 16. Bài tập tự kiểm tra

### Bài A — JDBC trả 1 hàng

Một method gọi executeUpdate(), nhận kết quả 1 và log “Đơn đã được ghi bền vững”. Sau đó một câu SQL khác trong cùng transaction ném exception, transaction bị rollback.

**Câu hỏi:** Câu log sai ở đâu, nên ghi gì?

**Gợi ý:** Một statement đã tác động 1 hàng trong transaction, nhưng chưa commit. Log lúc đó chỉ nên ghi sự kiện statement thành công hoặc đang chuẩn bị commit. Chỉ công bố thành công giao dịch sau ranh giới commit thực tế, và vẫn cần hiểu giới hạn durability configuration.

### Bài B — Flush rồi crash

Java gọi entityManager.persist(), entityManager.flush() thành công rồi JVM chết trước commit.

**Câu hỏi:** Có thể khẳng định entity đã tồn tại bền vững không?

**Gợi ý:** Không. flush có thể đã gửi INSERT tới DB nhưng transaction chưa commit; DB có cơ chế rollback khi kết nối/transaction kết thúc bất thường. Kiểm tra trạng thái DB sau phục hồi, đừng đánh đồng SQL được gửi với dữ liệu đã commit.

### Bài C — COMMIT OK nhưng replica thiếu bản ghi

PostgreSQL primary dùng replication bất đồng bộ, trả COMMIT OK cho transaction T. Ngay sau đó primary mất vĩnh viễn. Replica được promote nhưng không thấy T.

**Câu hỏi:** Có phải COMMIT chưa từng thành công? Điều này nói gì về durability?

**Gợi ý:** T có thể đã commit và bền vững trên primary cũ; replica chưa kịp nhận WAL nên không có T. Phân biệt local crash durability với durability sau failover. Muốn giảm rủi ro cần chính sách replication đồng bộ phù hợp và đánh giá miền lỗi, RPO/RTO.

### Bài D — Đổi synchronous_commit thành off

Một nhóm đo thấy độ trễ COMMIT giảm khi đặt synchronous_commit=off. Họ kết luận “SQL vẫn trả thành công nên dữ liệu không thể mất”.

**Câu hỏi:** Lỗ hổng trong lập luận là gì?

**Gợi ý:** ACK có thể xảy ra trước khi WAL commit record được flush cục bộ. Khi DB/OS crash, một số commit gần đây đã ACK có thể mất. Đây là đánh đổi latency và cửa sổ mất dữ liệu; cần so với RPO, không thể suy an toàn từ một lần benchmark.

### Bài E — Timeout khi tạo đơn

Client gửi request tạo đơn có idempotency key R. DB có thể đã commit order nhưng mất ACK đến Java. Client retry bằng idempotency key mới R2.

**Câu hỏi:** Rủi ro và cách thiết kế lại?

**Gợi ý:** Có thể tạo hai đơn. Client phải giữ cùng key R cho một ý định nghiệp vụ; server lưu key bền vững với UNIQUE constraint và trả kết quả đã có khi retry. Khi commit outcome chưa rõ, xác minh qua nguồn dữ liệu authoritative.

### Bài F — Có backup nhưng không restore được

Một hệ thống tạo backup hằng ngày và lưu trong cùng tài khoản lưu trữ. Khi cần phục hồi, đội vận hành phát hiện thiếu WAL để phục hồi theo thời điểm và khóa giải mã không còn.

**Câu hỏi:** Vì sao báo cáo “backup success” chưa chứng minh độ bền đủ cho nghiệp vụ?

**Gợi ý:** Khả năng phục hồi đòi hỏi dữ liệu cùng metadata/khóa/nhật ký cần thiết và một quy trình restore đã kiểm thử. Cần diễn tập, đo RPO/RTO, giữ bản sao ở miền lỗi phù hợp và đảm bảo quản lý khóa.

## 17. Tổng kết kiến thức

Một lời gọi ghi được hoàn tất có thể chỉ chứng minh rằng **một lớp của hệ thống đã nhận hoặc xử lý yêu cầu**. Độ bền dữ liệu là kết quả của một chuỗi cam kết từ transaction, WAL, flush tới storage, replica và backup — mỗi lớp chống một tập sự cố nhất định.

Khi xây dựng persistence cho Java:

1. Hãy xác định **mốc commit thực sự** thay vì tin vào tên save, flush hay executeUpdate.
2. Hãy xác định **phạm vi lỗi** mà DB được cấu hình để chịu đựng, phân biệt primary và replica.
3. Hãy chuẩn bị cho **kết quả commit chưa rõ** khi ACK mất, sử dụng business key ổn định và idempotency.
4. Hãy kiểm chứng bằng **crash recovery, failover và restore**, không chỉ benchmark tốc độ ghi.

Một API chỉ nên hứa “dữ liệu đã bền vững” khi người thiết kế biết chính xác **bền vững trước loại sự cố nào, ở tài nguyên nào và đến điểm khôi phục nào**.
