# Chỉ mục principal, tác vụ cleanup và chi phí dữ liệu phụ trợ

Spring Session có thể lưu nhiều phiên của cùng một người dùng trong Redis hoặc JDBC. Khi cần tìm tất cả session theo người dùng, chẳng hạn để giới hạn số lần đăng nhập đồng thời, hiển thị thiết bị đang đăng nhập hoặc thu hồi mọi phiên sau khi đổi mật khẩu, ứng dụng cần một cách tra cứu từ principal tới các session ID. Chỉ mục principal giải quyết truy vấn này bằng cách lưu một ánh xạ phụ trợ bên cạnh dữ liệu session.

Chỉ mục giúp tra cứu nhanh hơn nhưng cũng tạo thêm chi phí: mỗi lần session được tạo, xác thực, đổi principal, gia hạn, xóa hoặc hết hạn có thể kéo theo cập nhật index; cleanup phải dọn cả session lẫn dữ liệu phụ trợ; index lớn làm tăng RAM, dung lượng database, I/O, replication traffic và thời gian khôi phục. Nếu index bị stale, truy vấn có thể trả session ID không còn tồn tại hoặc bỏ sót session hợp lệ.

Bài học này tập trung vào:

- Vai trò của `FindByIndexNameSessionRepository` và principal index.
- Cách Spring Session lấy principal từ session, thường thông qua Spring Security.
- Khác biệt giữa Redis indexed repository và JDBC indexed repository.
- Đồng bộ index khi tạo, cập nhật, xóa và hết hạn session.
- Thiết kế cleanup an toàn khi chạy nhiều instance.
- Đo chi phí dữ liệu phụ trợ và kiểm soát tăng trưởng index.
- Kiểm thử tính đúng đắn, race condition và hiệu năng của truy vấn theo principal.

## 1. Vì sao cần chỉ mục principal?

Session thường được tra cứu bằng session ID lấy từ cookie. Đây là đường đọc phổ biến của request HTTP. Nhưng một số nghiệp vụ bắt đầu từ principal name và cần tìm các session liên quan:

- Quản trị viên xem các phiên đang hoạt động của một tài khoản.
- Giới hạn một tài khoản chỉ có tối đa N phiên đồng thời.
- Đăng xuất mọi thiết bị sau khi đổi mật khẩu.
- Thu hồi phiên khi tài khoản bị khóa hoặc nghi ngờ bị xâm nhập.
- Phát hiện một principal có quá nhiều session.
- Hiển thị thiết bị và thời điểm truy cập gần nhất.

Nếu chỉ có tra cứu theo session ID, ứng dụng không có đường truy vấn hiệu quả từ principal tới danh sách session. Một cách ngây thơ là quét toàn bộ session store, đọc từng session rồi so sánh principal. Chi phí tăng theo tổng số session của hệ thống và có thể gây tải lớn.

Chỉ mục principal lưu mối quan hệ phụ:

~~~text
principal name -> session IDs
~~~

Ví dụ:

~~~text
alice@example.test -> [S101, S208, S309]
bob@example.test   -> [S410]
~~~

Khi cần thu hồi mọi session của Alice, ứng dụng đọc danh sách ID của Alice rồi xóa từng session tương ứng. Chỉ mục giúp tìm candidate nhanh, nhưng trạng thái session chính vẫn nằm trong repository.

## 2. FindByIndexNameSessionRepository

Spring Session định nghĩa interface `FindByIndexNameSessionRepository<S extends Session>` để repository hỗ trợ tìm session theo một index name và index value. Hằng số phổ biến:

~~~java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
~~~

Index name này biểu thị principal name. Interface cũng cung cấp phương thức tiện ích `findByPrincipalName(String principalName)` trên các implementation hỗ trợ.

Ví dụ:

~~~java
Map<String, ? extends Session> sessions =
        repository.findByPrincipalName("alice@example.test");

sessions.forEach((sessionId, session) -> {
    System.out.println(session.getLastAccessedTime());
});
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế, inject đúng kiểu repository mà cấu hình đang tạo; không phải mọi `SessionRepository` đều triển khai `FindByIndexNameSessionRepository`. Nếu repository không hỗ trợ principal lookup, phương thức này không thể tự tạo index bằng cách quét toàn bộ storage.

Có thể dùng API tổng quát:

~~~java
Map<String, ? extends Session> sessions =
        repository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                "alice@example.test");
~~~

Giá trị trả về thường là map từ session ID tới session. Hãy xem nó như tập candidate tại thời điểm truy vấn; session có thể hết hạn hoặc bị xóa ngay sau khi kết quả được trả về. Khi thực hiện thao tác nhạy cảm, cần xử lý session không còn tồn tại và race giữa query với delete.

## 3. Principal index là dữ liệu phụ trợ

Chỉ mục principal không phải nguồn xác thực độc lập. Nó là dữ liệu dẫn đường để tìm session. Authentication vẫn phải được khôi phục và kiểm tra theo session state cùng chính sách Spring Security.

Phân biệt:

| Dữ liệu | Vai trò | Có thể dùng làm bằng chứng xác thực? |
| --- | --- | --- |
| Session record | Lưu attributes, thời gian và trạng thái session | Có thể chứa SecurityContext cần được xác minh theo security chain |
| Session ID trong cookie | Định danh session để repository tra cứu | Là credential nhạy cảm; phải được bảo vệ |
| Principal index | Tìm các session có liên quan tới principal | Không; chỉ là index phụ trợ |
| Account record | Trạng thái tài khoản, khóa/mở, security version | Là nguồn nghiệp vụ theo chính sách của ứng dụng |
| Audit record | Ghi lại hành động và actor | Không thay thế quyết định authorization hiện tại |

Index có thể stale hoặc thiếu do lỗi cập nhật, cleanup, failover hay phiên bản code không tương thích. Vì vậy, kết quả index không nên tự cấp quyền truy cập dữ liệu hoặc chứng minh người dùng đang đăng nhập. Trước khi thao tác với từng session, repository phải xác minh session còn tồn tại và còn hiệu lực.

## 4. Spring Session lấy principal name từ đâu?

Trong ứng dụng Spring Security, principal thường nằm trong `Authentication` được lưu trong `SecurityContext`. Spring Session có thể dùng `PrincipalNameIndexResolver` để trích principal name từ SecurityContext được lưu trong session.

Luồng khái quát:

1. Người dùng đăng nhập.
2. Spring Security tạo Authentication và lưu SecurityContext.
3. SecurityContext được lưu vào session theo cấu hình security context repository.
4. Khi repository lưu session, index resolver đọc principal name.
5. Repository cập nhật chỉ mục principal để ánh xạ principal tới session ID.
6. Truy vấn theo principal sử dụng index thay vì quét mọi session.

Trong các ứng dụng dùng Spring Security, attribute session thường chứa SecurityContext. Tên attribute và cách trích xuất phụ thuộc integration/version; không tự giả định mọi ứng dụng lưu Authentication theo cùng một cách.

Nếu custom authentication không đặt principal trong SecurityContext theo cấu trúc mà resolver mặc định hiểu, index có thể không được tạo. Khi đó, cần cấu hình resolver phù hợp hoặc lưu một attribute index riêng có kiểm soát.

## 5. PrincipalNameIndexResolver và custom index resolver

Resolver quyết định index name/value nào được trích từ session. Với principal lookup, Spring Session có resolver tiêu chuẩn để lấy tên principal từ SecurityContext. Nếu cần index theo tenant, account ID hoặc loại principal khác, có thể xây dựng resolver riêng theo API của phiên bản đang dùng.

Một resolver tùy chỉnh cần trả về các cặp index name/value ổn định:

~~~text
principalName -> alice@example.test
tenantId      -> tenant-42
accountId     -> 78123
~~~

Không đưa dữ liệu nhạy cảm hoặc không ổn định vào index value. Tránh dùng display name vì người dùng có thể đổi tên; ưu tiên ID bất biến. Nếu principal name có thể đổi, cần cập nhật index cũ và mới nhất quán.

Các quyết định cần chốt:

- Principal name có phân biệt chữ hoa/chữ thường không?
- Có chuẩn hóa Unicode hoặc khoảng trắng không?
- Tenant có phải một phần của khóa index không?
- Principal có thể đổi tên hay được tái sử dụng sau khi tài khoản bị xóa không?
- Nhiều loại Authentication có cùng cách trích principal không?
- Session anonymous có bị index hay không?

Nếu nhiều tenant có thể dùng cùng username, chỉ index theo username sẽ trộn session giữa tenant. Nên dùng một giá trị định danh duy nhất, ví dụ tenant ID kết hợp account ID, hoặc index riêng cho từng chiều truy vấn.

## 6. Redis indexed repository

Spring Session Redis có implementation indexed để hỗ trợ truy vấn theo principal và các index session khác. Cấu hình và annotation bật repository phụ thuộc phiên bản Spring Session; thường cần chọn cấu hình Redis indexed session repository thay vì repository Redis không có indexing.

Về mặt logic, Redis indexed repository quản lý:

- Dữ liệu session chính.
- Metadata expiration và key phụ trợ cần cho lifecycle.
- Index từ principal name tới session ID.
- Các cấu trúc phụ trợ để tìm session theo index value.

Tên key và cấu trúc dữ liệu cụ thể là chi tiết implementation; không nên hard-code vào code ứng dụng nếu API repository đã cung cấp truy vấn. Khi nâng cấp phiên bản, cấu trúc nội bộ có thể thay đổi.

### 6.1. Chi phí Redis index

Mỗi principal có thể có một tập session ID. Chi phí phụ thuộc:

- Số principal có session.
- Số session trung bình và tối đa trên mỗi principal.
- Độ dài principal/index value và session ID.
- Kiểu dữ liệu Redis dùng để lưu index.
- Số lượng index khác ngoài principal.
- Replication, persistence và memory fragmentation.

Một tài khoản có hàng nghìn session có thể tạo index lớn và thao tác xóa hàng loạt tốn thời gian. Một hệ thống có hàng triệu principal dù mỗi principal chỉ có một session vẫn tạo số lượng key/member đáng kể.

Không chỉ đo số session chính. Đo cả số key index, số member, memory usage và thời gian query/delete theo principal.

### 6.2. Redis keyspace notification và expiration

Một số khả năng cleanup/index/event của Redis repository phụ thuộc keyspace notifications. Khi session hết hạn, notification có thể giúp repository hoặc listener dọn index và phát event. Tuy nhiên:

- Notification phải được bật theo cấu hình Redis mà implementation yêu cầu.
- Redis managed service có thể giới hạn CONFIG hoặc notification settings.
- Expiration event có thể đến trễ so với deadline.
- Notification có thể không được xem là durable event stream.
- Listener disconnect hoặc process restart có thể bỏ lỡ event.

Vì vậy, đừng coi keyspace notification là cơ chế duy nhất bảo đảm index không bao giờ stale. Cần hiểu cleanup fallback và khả năng đối soát theo phiên bản repository.

## 7. JDBC indexed repository

Với JDBC, session thường được lưu trong bảng session và bảng attributes. Indexed repository có thể lưu principal name trong cột riêng của bảng session để truy vấn theo principal.

Schema chuẩn Spring Session JDBC thường có các cột thời gian như creation time, last access time, max inactive interval và expiry time, cùng principal name khi dùng indexed repository. Bảng attributes lưu session attributes. Tên cột, kiểu dữ liệu và index phải theo schema script đúng phiên bản.

Truy vấn theo principal có thể dùng index database trên cột principal name. Ví dụ SQL khái quát:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, EXPIRY_TIME
FROM SPRING_SESSION
WHERE PRINCIPAL_NAME = :principalName
  AND EXPIRY_TIME > :now;
~~~

Đây là truy vấn minh họa, không thay thế SQL do repository phát hành. Repository có thể join hoặc đọc thêm bảng attributes và áp dụng logic expiration khác. Không truy cập trực tiếp schema nội bộ từ nghiệp vụ nếu API repository đã đáp ứng.

### 7.1. Chi phí JDBC index

Index database giúp query principal nhanh hơn nhưng làm tăng:

- Dung lượng index trên disk.
- Chi phí insert/update/delete.
- WAL/redo log và replication traffic.
- I/O khi cleanup xóa nhiều row.
- Lock contention khi nhiều request cùng cập nhật session.
- Thời gian backup, restore và migration.

Nếu principal name dài hoặc index nhiều cột, kích thước index tăng. Nếu truy vấn luôn theo tenant và principal, một composite index phù hợp có thể hiệu quả hơn nhiều index đơn, nhưng phải dựa trên query plan thực tế.

## 8. Đồng bộ index trong vòng đời session

Index cần nhất quán với session chính trong các chuyển đổi:

| Thao tác | Cập nhật index mong đợi |
| --- | --- |
| Tạo session chưa xác thực | Có thể chưa có principal index |
| Đăng nhập và lưu SecurityContext | Thêm session ID vào index principal |
| Cập nhật thuộc tính không đổi principal | Giữ nguyên quan hệ index |
| Principal thay đổi | Xóa quan hệ cũ và thêm quan hệ mới |
| Logout/delete | Xóa session ID khỏi index |
| Session hết hạn | Xóa hoặc làm cho index stale không còn trả session hợp lệ |
| Revoke tất cả phiên | Xóa từng session và cập nhật index tương ứng |

Không phải mọi repository cập nhật index ở cùng thời điểm hoặc bằng cùng transaction. Redis có thể dùng nhiều lệnh/structures; JDBC có thể dùng transaction trên cùng database. Hãy xác định consistency guarantee của implementation và kiểm thử các khoảng thời gian chuyển tiếp.

## 9. Session anonymous chuyển thành authenticated

Một session có thể được tạo trước khi đăng nhập. Sau khi xác thực, SecurityContext được thêm vào session và principal index có thể được tạo ở lần save phù hợp.

Test cần kiểm tra:

1. Tạo session anonymous.
2. Xác nhận session chưa xuất hiện trong principal index nếu policy không index anonymous.
3. Thực hiện login và lưu SecurityContext.
4. Đọc theo principal name.
5. Xác nhận session ID được đưa vào kết quả.
6. Đổi hoặc xóa SecurityContext theo luồng logout.
7. Xác nhận index được cập nhật theo contract.

Nếu index được trích khi repository lưu session, thay đổi SecurityContext phải được persist. Chỉ sửa object trong memory mà không save không đủ để cập nhật index.

## 10. Principal thay đổi và index cũ

Principal có thể thay đổi do account rename, liên kết identity provider, chuyển tenant hoặc custom authentication. Khi principal value đổi, repository cần loại bỏ mapping cũ và thêm mapping mới.

Nếu chỉ thêm index mới mà không xóa index cũ:

- Truy vấn principal cũ trả session đã chuyển.
- Một thao tác revoke theo principal cũ có thể xóa nhầm session hiện tại.
- Index cũ giữ member mồ côi và tăng chi phí cleanup.

Nếu xóa index cũ trước khi lưu session mới rồi thao tác ghi thất bại, session có thể không được tìm thấy theo cả hai principal. Với JDBC cùng transaction có thể cập nhật nhất quán hơn; với Redis nhiều key, cần hiểu atomicity và cách repository xử lý partial failure.

Không cho phép principal rename đồng thời mà không có quy tắc thứ tự hoặc version. Nếu cần, lưu principal immutable ID trong index chính và dùng username như một index phụ có thể tái tạo.

## 11. Cleanup session hết hạn và index phụ

Cleanup phải xử lý cả session chính lẫn dữ liệu phụ trợ. Nếu chỉ xóa session record mà không xóa principal index, truy vấn theo principal có thể tiếp tục trả session ID mồ côi.

Ngược lại, nếu xóa index trước nhưng session delete thất bại, session còn tồn tại mà không thể tìm qua index. Đây là một dạng partial update cần được xử lý bằng transaction, atomic script, retry hoặc reconciliation tùy storage.

### 11.1. JDBC cleanup

JDBC repository có thể cung cấp tác vụ cleanup định kỳ xóa session hết hạn. Cần xác minh:

- Cleanup query dùng đúng expiry column và index database.
- Row attributes được xóa qua foreign key cascade hoặc thao tác cleanup tương ứng của schema.
- Principal index được cập nhật do row xóa.
- Batch size không tạo transaction quá lớn.
- Nhiều node không tranh chấp quá mức khi cùng chạy cleanup.
- Cleanup có metric và log số lượng row bị xóa.

Không tự viết lệnh DELETE trực tiếp vào bảng session khi repository đang quản lý lifecycle, trừ khi thiết kế đã tính đến attributes, index, events và transaction. Xóa một bảng chính mà bỏ sót bảng phụ sẽ tạo dữ liệu mồ côi.

### 11.2. Redis cleanup

Redis có thể tự hết hạn key session theo TTL. Nhưng index phụ có thể có lifecycle khác key session chính. Kiểm tra:

- Index member có được loại bỏ khi session expired/deleted không?
- Cleanup phụ thuộc keyspace notifications hay tác vụ khác?
- Có shadow/phantom key để giữ metadata phục vụ event không?
- Notification bị mất có để lại index member không?
- Có cơ chế dọn stale member khi truy vấn hoặc đối soát không?

Đừng giả định Redis tự xóa member trong mọi set/zset chỉ vì key session chính hết hạn. Cần kiểm tra cách repository cụ thể quản lý index và expiration.

## 12. Cleanup chạy trên nhiều instance

Nếu mọi instance đều chạy cleanup task, cùng một session có thể được nhiều worker phát hiện. Tác vụ cleanup nên idempotent và có chiến lược phân phối công việc:

- Một worker leader dùng distributed lease.
- Chia partition theo shard hoặc key range.
- Nhiều worker dùng delete có điều kiện/atomic và chỉ worker thực sự xóa mới cập nhật số liệu tương ứng.
- JDBC dùng batch locking/skip locked nếu database hỗ trợ.

Lock `synchronized` hoặc biến static chỉ có tác dụng trong một JVM, không ngăn worker trên node khác chạy cùng lúc.

Cleanup cần tránh race với request đang gia hạn session. Nếu worker đọc expiry cũ rồi xóa sau khi request đã cập nhật expiry mới, session hợp lệ có thể bị xóa. Dùng conditional delete dựa trên expiry/version quan sát được hoặc transaction/atomic script để tránh xóa nhầm.

## 13. Chi phí dữ liệu phụ trợ

Tổng dung lượng session không chỉ gồm attributes. Có thể ước lượng:

~~~text
Total storage
  = session records
  + serialized attributes
  + principal indexes
  + expiration metadata
  + secondary indexes
  + event/outbox records
  + storage overhead
~~~

Chi phí phụ trợ tăng theo số session, số index trên mỗi session, số principal và thời gian dữ liệu stale tồn tại. Một index nhỏ về logic vẫn có thể tốn RAM hoặc disk đáng kể do overhead của key, object, allocator, page và replication.

Các thành phần chi phí:

| Thành phần | Redis | JDBC |
| --- | --- | --- |
| Principal index | Key và collection member | B-tree/index entry |
| Expiration metadata | TTL key, shadow key hoặc cấu trúc phụ | Expiry column và index |
| Session attributes | Serialized value/hash | Row attributes hoặc payload |
| Cleanup | Expire notification, delete key/member, scan/repair | Batch DELETE, cascade, vacuum/maintenance |
| Replication | Replication stream và memory trên replica | WAL/redo và replica apply |
| Backup/restore | RDB/AOF và dung lượng dataset | Backup database và index |

Không so sánh chi phí chỉ bằng số session. Hai hệ thống có cùng số session nhưng principal index cardinality, attribute size và số phiên trên mỗi principal khác nhau có thể có chi phí rất khác.

## 14. Index cardinality và phân bố principal

Cardinality là số giá trị principal khác nhau có index. Cần đo cùng lúc:

- Tổng số session.
- Số principal có ít nhất một session.
- Số session trung bình trên mỗi principal.
- P95/P99 session count trên một principal.
- Principal có nhiều session nhất.
- Số member stale trong index.

Phân bố lệch có thể tạo hot key hoặc hot row. Một tài khoản dùng chung bởi nhiều thiết bị/kiosk có thể có số session lớn hơn hẳn người dùng bình thường. Truy vấn và revoke principal đó sẽ tốn nhiều thao tác.

Nếu có tenant, nên kiểm tra phân bố theo tenant để tránh một tenant lớn chi phối index hoặc cleanup. Có thể giới hạn số session đồng thời theo account/tenant để bảo vệ storage, nhưng giới hạn phải được thực thi an toàn khi nhiều login đồng thời.

## 15. Chi phí truy vấn theo principal

Tra cứu theo principal thường gồm hai phần:

1. Tìm danh sách session ID từ index.
2. Đọc session records tương ứng và loại bỏ session đã hết hạn/không còn tồn tại.

Nếu principal có hàng nghìn session, phần lấy danh sách ID có thể nhanh nhưng tải toàn bộ session attributes về memory vẫn đắt. Chỉ lấy dữ liệu cần thiết nếu API hỗ trợ hoặc dùng truy vấn index để xác định ID rồi xử lý theo batch.

Khi revoke nhiều session:

- Giới hạn batch size.
- Không tải toàn bộ session attributes nếu chỉ cần xóa.
- Xử lý ID đã biến mất như trường hợp idempotent.
- Đặt timeout và giới hạn concurrency.
- Đo thời gian query index, load session và delete riêng.
- Tránh giữ transaction dài trong lúc gọi dịch vụ ngoài.

Không gọi `findByPrincipalName` rồi giữ toàn bộ session object trong memory khi principal có thể có số lượng session rất lớn. Có thể xử lý theo page/batch nếu repository cung cấp API phù hợp; nếu không, đặt giới hạn nghiệp vụ hoặc thiết kế tác vụ revoke theo lô.

## 16. Chi phí ghi và write amplification

Một lần save session có thể kéo theo nhiều ghi:

- Ghi hoặc cập nhật session record.
- Ghi attributes đã thay đổi.
- Cập nhật expiration TTL.
- Thêm hoặc loại bỏ index member.
- Cập nhật metadata phụ.
- Ghi outbox/event nếu có.

Đó là write amplification: một thao tác nghiệp vụ tạo nhiều thao tác storage. Khi số request tăng, chi phí index có thể trở thành nút thắt dù payload session nhỏ.

Đo:

- Số lệnh Redis/SQL trung bình trên mỗi request có session.
- Tỷ lệ save thực tế so với read.
- Số lần index add/remove.
- Thời gian ghi session và index.
- Transaction duration và lock wait.
- Redis command latency, CPU và memory.
- Database write IOPS, WAL/redo, deadlocks và index bloat.

Save mode/flush mode của Spring Session có thể ảnh hưởng số lần ghi. Đừng thay đổi chỉ để giảm write mà chưa kiểm tra semantics cập nhật session và index. Một cấu hình giảm ghi nhưng bỏ sót thay đổi principal có thể tạo lỗi bảo mật hoặc session lookup sai.

## 17. Giới hạn số session và xử lý concurrent login

Một use case phổ biến của principal index là giới hạn số session đồng thời. Luồng đơn giản:

1. Tìm session theo principal.
2. Nếu vượt giới hạn, xóa session cũ.
3. Cho phép tạo session mới.

Nhưng hai login đồng thời có thể cùng đọc một danh sách cũ rồi cùng tạo session mới, khiến giới hạn bị vượt. Index giúp tìm phiên nhưng không tự cung cấp transaction khóa toàn bộ login flow.

Nếu giới hạn là yêu cầu cứng, cần cơ chế đồng bộ:

- Atomic counter/lock theo principal.
- Database transaction với khóa hàng account.
- Compare-and-set/version.
- SessionRegistry/concurrent-session control của Spring Security được cấu hình đúng repository.

Ngay cả khi dùng lock, cần xử lý crash và lease timeout. Không giữ lock trong lúc gửi email hoặc gọi dịch vụ ngoài.

Principal index cũng không tự đảm bảo thứ tự “session cũ nhất” nếu repository chỉ trả map không có ordering guarantee. Nếu cần chọn session cũ nhất, so sánh creation/last access timestamps theo dữ liệu thực tế, và xử lý tie/race.

## 18. Bảo mật và quyền riêng tư của index

Principal index có thể để lộ username/email hoặc liên kết account với session ID nếu storage bị truy cập trái phép. Cần:

- Giới hạn Redis ACL hoặc quyền database chỉ cho ứng dụng cần thiết.
- Mã hóa kết nối và bảo vệ credentials.
- Không log raw session ID, cookie hoặc principal index key.
- Không cho API quản trị truy vấn principal index mà thiếu authorization.
- Phân vùng tenant rõ ràng.
- Cân nhắc dùng account ID hoặc HMAC/pseudonymous value cho index custom nếu phù hợp.
- Đặt retention và cleanup cho index stale.

Hash principal không tự động làm index an toàn: hash không có secret có thể bị dò từ danh sách username phổ biến. Nếu dùng HMAC, phải quản lý key rotation và khả năng tìm index cũ trong thời gian chuyển đổi.

Không coi việc một session ID xuất hiện trong principal index là bằng chứng người dùng hiện còn đăng nhập. Luôn kiểm tra session record và trạng thái tài khoản theo policy.

## 19. Đổi principal, xóa tài khoản và tenant migration

Khi account bị xóa hoặc chuyển tenant, cần xử lý:

- Session hiện tại của principal cũ.
- Index theo principal cũ.
- Index theo principal mới nếu rename.
- Session registry hoặc concurrent-session state.
- Audit record và outbox event.

Không chỉ đổi username trong account database rồi mong session index tự thay đổi. Session attributes và index có thể vẫn chứa principal cũ cho tới khi session được save hoặc hết hạn.

Một chiến lược an toàn:

1. Khóa hoặc tăng security version của account để chặn session cũ.
2. Tìm session bằng index cũ.
3. Xóa/revoke theo batch.
4. Dọn index phụ và metadata.
5. Cập nhật principal/tenant mapping.
6. Xác minh không còn session hợp lệ theo principal cũ.
7. Ghi audit và metric số session đã thu hồi.

Nếu việc xóa nhiều session kéo dài, giữ account ở trạng thái không thể đăng nhập trong thời gian revoke đang xử lý, theo chính sách nghiệp vụ.

## 20. Đo lường và cảnh báo

Theo dõi cả correctness lẫn cost:

| Metric | Ý nghĩa |
| --- | --- |
| sessions.active | Số session được repository coi là còn hiệu lực |
| sessions.principals.indexed | Số principal có index |
| sessions.index.members | Tổng số session ID trong principal index |
| sessions.index.stale_members | Member trỏ tới session không còn tồn tại |
| sessions.lookup.by_principal.latency | Độ trễ truy vấn principal |
| sessions.lookup.by_principal.result_size | Số session trả về mỗi principal |
| sessions.cleanup.deleted | Số session được cleanup |
| sessions.cleanup.index_members_removed | Số index member được dọn |
| sessions.cleanup.lag | Độ trễ từ expiration tới physical cleanup |
| sessions.index.update.errors | Lỗi cập nhật principal index |
| sessions.storage.bytes | Dung lượng session và dữ liệu phụ trợ |
| sessions.write.operations | Số thao tác storage trên mỗi lần save |

Không dùng principal name hoặc session ID làm metric label vì cardinality rất cao và có thể lộ dữ liệu. Dùng repository type, operation, node, tenant tier hoặc bucket đã giới hạn.

Cảnh báo nên bao gồm:

- Index members tăng nhanh hơn active sessions.
- Stale member ratio vượt ngưỡng.
- Principal lookup p95/p99 tăng.
- Cleanup lag kéo dài.
- Số session trên một principal vượt giới hạn.
- Redis memory hoặc database index size tiến gần capacity.
- Index update error tăng sau deploy.

## 21. Kiểm thử principal index

Bộ test nên xác nhận index theo lifecycle:

1. Tạo session anonymous và xác nhận chưa có principal index nếu policy không index anonymous.
2. Thêm SecurityContext/authentication và save session.
3. Tìm theo principal và xác nhận đúng session ID.
4. Tạo nhiều session cho cùng principal và xác nhận tất cả được trả.
5. Tạo session cho principal khác và xác nhận không lẫn.
6. Đổi principal hoặc tenant theo custom resolver và xác nhận index cũ được loại bỏ.
7. Xóa session và xác nhận index không còn trả ID đó.
8. Để session hết hạn và xác nhận truy vấn không trả session hợp lệ đã hết hạn.
9. Chạy cleanup và xác nhận stale metadata được dọn theo guarantee.
10. Mô phỏng lỗi giữa cập nhật session và index; xác nhận retry/reconciliation.

Test phải dùng repository implementation thật khi xác minh Redis/JDBC indexing. Mock có thể dùng cho logic service nhưng không chứng minh cấu trúc index, cleanup hay transaction.

## 22. Kiểm thử race condition và tải

Các tình huống quan trọng:

- Hai request cùng save session và cập nhật principal index.
- Request gia hạn session chạy đồng thời cleanup.
- Logout/delete chạy đồng thời principal lookup.
- Hai login cùng principal chạy đồng thời khi có giới hạn session.
- Principal rename trong khi request cũ đang save.
- Node A xóa session nhưng node B vẫn có cache/index cũ.
- Notification expiration bị trễ hoặc listener tạm ngắt.

Dùng barrier/latch để điều khiển thứ tự test, không phụ thuộc sleep ngẫu nhiên. Sau mỗi race, xác minh invariant:

- Không có index trỏ tới session không hợp lệ sau khi cleanup hoàn tất.
- Không xóa nhầm session mới được gia hạn.
- Một session chỉ thuộc principal index đúng theo snapshot được lưu.
- Session đã revoke không được coi là xác thực chỉ vì index còn member.
- Consumer cleanup chịu được event trùng.

Benchmark nên đo theo các phân bố khác nhau: nhiều principal với ít session, ít principal với nhiều session, principal nóng, attributes nhỏ/lớn, index đơn/nhiều index. Đo p50/p95/p99, throughput, CPU, memory, disk, Redis command count và database query plan.

## 23. Các lỗi thiết kế thường gặp

- **Cho rằng mọi repository đều hỗ trợ principal lookup:** cần implementation có FindByIndexNameSessionRepository.
- **Dùng principal index làm nguồn authorization:** index là dữ liệu phụ trợ, có thể stale.
- **Chỉ index username không kèm tenant:** có thể trộn session giữa tenant.
- **Không cập nhật index khi SecurityContext được lưu:** login thành công nhưng truy vấn principal không thấy session.
- **Đổi principal mà không xóa mapping cũ:** index cũ giữ session ID sai.
- **Chỉ xóa session record:** index member hoặc attributes có thể còn tồn tại.
- **Giả định Redis tự dọn mọi member phụ:** TTL của key chính không bảo đảm cấu trúc index khác tự sạch.
- **Cleanup nhiều node không có atomicity:** có thể phát event lặp hoặc xóa session vừa được gia hạn.
- **Tải toàn bộ session của principal lớn vào memory:** tăng heap và latency.
- **Không giới hạn số session:** một principal nóng có thể tạo index và revoke workload rất lớn.
- **Không đo write amplification:** index update làm tăng chi phí mỗi request mà dashboard chỉ nhìn session payload.
- **Log principal/session ID:** làm lộ dữ liệu và tạo cardinality cao.

## 24. Checklist vận hành

- [ ] Repository thực tế hỗ trợ principal lookup và đã được cấu hình đúng.
- [ ] Index resolver trích principal từ đúng Authentication/SecurityContext.
- [ ] Principal key ổn định, chuẩn hóa và có tenant scope khi cần.
- [ ] Session anonymous/authenticated được index theo policy rõ ràng.
- [ ] Session create/save/delete/expire cập nhật index nhất quán theo guarantee.
- [ ] Cleanup xử lý session chính, attributes, principal index và metadata phụ.
- [ ] Cleanup an toàn khi nhiều node cùng chạy.
- [ ] Request gia hạn không bị cleanup xóa theo expiry cũ.
- [ ] Có cơ chế retry/reconciliation khi cập nhật index thất bại.
- [ ] Truy vấn principal có giới hạn/batch cho account có nhiều session.
- [ ] Có chính sách giới hạn session đồng thời nếu cần.
- [ ] Đã đo cardinality, stale member, cleanup lag và write amplification.
- [ ] Có cảnh báo cho lookup latency, index growth và cleanup failure.
- [ ] Redis ACL/database permissions giới hạn truy cập index.
- [ ] Không log session ID, cookie hoặc principal index key.

## 25. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- `FindByIndexNameSessionRepository` bổ sung khả năng gì so với `SessionRepository`?
- `PRINCIPAL_NAME_INDEX_NAME` được dùng trong truy vấn nào?
- `PrincipalNameIndexResolver` lấy principal từ đâu trong ứng dụng Spring Security?
- Vì sao principal index là dữ liệu phụ trợ chứ không phải nguồn xác thực?
- Redis indexed repository và JDBC indexed repository có chi phí index khác nhau thế nào?
- Vì sao cleanup phải xử lý cả session, attributes và index?
- Race nào có thể xảy ra giữa request gia hạn và cleanup?
- Vì sao username cần tenant scope hoặc ID bất biến trong hệ thống multi-tenant?
- Write amplification ảnh hưởng latency và dung lượng ra sao?
- Những metric nào giúp phát hiện stale index và tăng trưởng dữ liệu phụ trợ?

Principal index giúp tìm session theo người dùng mà không quét toàn bộ kho, nhưng mỗi index tạo thêm chi phí lưu trữ, ghi và cleanup. Hãy xem index là dữ liệu phụ trợ có thể stale, giữ principal key ổn định và có tenant scope, đồng bộ index với lifecycle session, và thiết kế cleanup an toàn trước race giữa refresh/delete. Đo cả số session lẫn cardinality, stale members, lookup latency, cleanup lag và write amplification để biết chi phí thật của dữ liệu phụ trợ khi hệ thống tăng trưởng.
