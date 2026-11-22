# Giao dịch phân tán, two-phase commit và giao dịch in-doubt trong Oracle

Giao dịch phân tán (distributed transaction) là một giao dịch nghiệp vụ thực hiện thay đổi trên nhiều database hoặc nhiều resource manager nhưng cần được xem như một đơn vị nhất quán. Ví dụ một đơn hàng được ghi ở database bán hàng, đồng thời trừ tồn kho ở database kho và ghi bút toán ở database tài chính. Nếu chỉ một nơi commit trong khi nơi khác rollback, dữ liệu nghiệp vụ sẽ không còn nhất quán.

Oracle hỗ trợ giao dịch phân tán qua database links và cơ chế **two-phase commit (2PC)**. Khi một transaction thay đổi dữ liệu trên nhiều database, Oracle phối hợp các participant để cùng đi đến quyết định commit hoặc rollback. 2PC có hai giai đoạn: prepare để mỗi participant bảo đảm có thể commit, rồi commit/rollback để hoàn tất quyết định đã thống nhất.

Nếu coordinator hoặc participant mất kết nối đúng lúc quyết định commit đang được truyền, một database có thể chưa biết kết quả cuối cùng. Transaction khi đó ở trạng thái **in-doubt**. Oracle giữ thông tin transaction và có thể giữ lock liên quan cho tới khi quyết định được khôi phục. Background process RECO (Recoverer) tự động thử giải quyết các distributed transactions bị pending khi kết nối giữa các site trở lại.

In-doubt không đồng nghĩa transaction chắc chắn đã commit hoặc rollback. DBA không được tự ý FORCE COMMIT/FORCE ROLLBACK chỉ để xóa entry hoặc giải phóng lock. Phải xác định quyết định toàn cục từ coordinator/participants, transaction ID, commit record và bằng chứng nghiệp vụ trước khi can thiệp thủ công.

Bài học thuộc chủ đề **Tích hợp phân tán** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Distributed transaction và database link.
- Vai trò coordinator, participant, commit point site.
- Hai giai đoạn prepare và commit/rollback của 2PC.
- Read-only participant optimization và transaction consistency.
- Giao dịch in-doubt, lock và RECO.
- DBA_2PC_PENDING, DBA_2PC_NEIGHBORS và các view giám sát.
- COMMIT FORCE, ROLLBACK FORCE và rủi ro quyết định sai.
- Quy trình phục hồi khi network/site/database gặp sự cố.
- Bài lab nhiều database, fault scenario và checklist vận hành.

## 1. Giao dịch phân tán là gì?

Một local transaction chỉ thay đổi dữ liệu trong một database. Distributed transaction có thể thay đổi dữ liệu ở nhiều database khác nhau nhưng ứng dụng muốn chúng có một kết quả nguyên tử: tất cả commit hoặc tất cả rollback.

### Ví dụ nghiệp vụ

Một ứng dụng chuyển hàng giữa hai chi nhánh:

1. Database kho A giảm số lượng hàng.
2. Database kho B tăng số lượng hàng.
3. Database kế toán ghi nhận điều chuyển.

Nếu bước 1 và 2 commit nhưng bước 3 rollback, số liệu kế toán không khớp. Nếu database A commit còn B rollback, hàng bị mất khỏi tổng tồn kho. Giao dịch phân tán phối hợp quyết định để tránh trạng thái một phần.

### Oracle database link

Database link cho phép session tại một database truy cập object ở database khác:

~~~sql
SELECT *
FROM products@warehouse_link
WHERE product_id = 100;
~~~

Database link có thể dùng để truy vấn từ xa hoặc thực hiện DML:

~~~sql
UPDATE inventory@warehouse_link
SET quantity = quantity - 1
WHERE product_id = 100;
~~~

Khi một transaction chỉ đọc dữ liệu remote, đó là distributed query. Khi transaction thực hiện DML trên remote database và có thay đổi local/remote cần commit thống nhất, Oracle có thể dùng distributed transaction protocol.

### Ví dụ thay đổi local và remote trong cùng transaction

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

UPDATE inventory@warehouse_link
SET reserved_qty = reserved_qty + 1
WHERE product_id = 100;

COMMIT;
~~~

Ứng dụng chỉ gửi một COMMIT. Oracle điều phối các database tham gia để đạt quyết định commit toàn cục. Nếu transaction rollback trước commit, Oracle yêu cầu các thay đổi tham gia rollback.

### Distributed query không luôn là distributed transaction

SELECT qua database link có thể đọc nhiều database nhưng không nhất thiết tạo một transaction phân tán cần 2PC commit. Điểm cần chú ý là transaction có thay đổi dữ liệu ở nhiều participant và cần commit atomic. Một câu lệnh DML remote vẫn tham gia transaction của session; khi transaction có nhiều database, Oracle phải phối hợp commit.

## 2. Thành phần của distributed transaction

### Global coordinator

Coordinator điều phối distributed transaction. Trong Oracle, site khởi tạo transaction thường giữ vai trò điều phối và theo dõi trạng thái các participant. Coordinator bắt đầu prepare, thu nhận vote và quyết định commit hoặc rollback theo protocol.

### Participant

Participant là mỗi database tham gia transaction và thực hiện một phần công việc. Mỗi participant phải bảo đảm thay đổi của mình có thể commit hoặc rollback theo quyết định toàn cục.

### Commit point site

Trong Oracle 2PC, một participant được chọn làm commit point site. Site này có vai trò đặc biệt trong giai đoạn commit và có thể commit trước các participant khác sau khi tất cả đã prepare. Các site còn lại sau đó hoàn tất theo quyết định đã được ghi nhận.

Oracle lựa chọn commit point site dựa trên tham số COMMIT_POINT_STRENGTH của các database tham gia; site có strength cao nhất được chọn theo quy tắc Oracle. Nếu cần hiểu chi tiết tie/selection, kiểm tra tài liệu đúng release.

### RECO

RECO là background process Recoverer. Nó theo dõi và tự động thử giải quyết các distributed transactions còn in-doubt khi liên lạc giữa các database participant được khôi phục. RECO sử dụng thông tin transaction và trạng thái protocol đã lưu để xác định quyết định còn thiếu.

### Sơ đồ tổng quát

~~~text
                 Application Session
                         |
                         v
                Coordinator Database
                   /            \
                  /              \
          Participant A       Participant B
          Remote DB link      Remote DB link
                  \              /
                   \            /
               Global transaction
                Prepare / Commit
~~~

Một transaction có thể có nhiều participant và nhiều tầng database links. Càng nhiều site, network hop và coordinator dependency, việc điều tra lỗi càng phức tạp.

## 3. Two-phase commit (2PC)

2PC là protocol điều phối commit giữa nhiều participant. Oracle dùng protocol này để bảo đảm tính nguyên tử của distributed transaction khi các database cần commit cùng nhau.

### Giai đoạn 1: PREPARE

Coordinator yêu cầu các participant chuẩn bị commit. Mỗi participant:

- Hoàn tất các thao tác cần thiết để xác nhận transaction có thể commit.
- Ghi thông tin cần thiết vào redo/transaction metadata để có thể khôi phục quyết định.
- Giữ các lock cần thiết để bảo vệ thay đổi trong lúc chờ kết quả.
- Trả vote YES nếu có thể commit hoặc NO nếu không thể.

Vote YES có nghĩa participant đã prepare và cam kết có thể hoàn tất commit khi nhận quyết định toàn cục. Nó chưa có nghĩa transaction đã commit.

### Giai đoạn 2: COMMIT hoặc ROLLBACK

Nếu tất cả participant cần thiết vote YES, coordinator quyết định COMMIT. Quyết định commit được ghi nhận bền vững và truyền tới các participant. Nếu có participant vote NO hoặc có lỗi khiến transaction không thể tiếp tục theo protocol, coordinator quyết định ROLLBACK.

Participant nhận quyết định sẽ hoàn tất commit/rollback, giải phóng lock và thông báo trạng thái. Coordinator theo dõi cho tới khi các participant hoàn tất.

### Sơ đồ hai giai đoạn

~~~text
Coordinator                    Participants
     |                               |
     |--------- PREPARE ------------>|
     |                               |
     |<--------- YES / NO ------------|
     |                               |
     |   All required votes YES?     |
     |          /       \            |
     |        YES        NO          |
     |         |          |          |
     |------ COMMIT ---- ROLLBACK -->|
     |                               |
     |<------ completion ------------|
~~~

Sơ đồ minh họa khái niệm; thông điệp, log record và trạng thái nội bộ cụ thể do Oracle quản lý.

### Vì sao phải có PREPARE?

Nếu coordinator gửi COMMIT trực tiếp tới từng site mà không có prepare, một participant có thể phát hiện constraint/space/transaction error sau khi site khác đã commit. Prepare giúp participant xác nhận trước rằng nó có thể commit, sau đó giữ trạng thái cần thiết trong khi chờ quyết định.

### Tính bền vững của quyết định

2PC dựa vào log/redo để khôi phục quyết định sau crash. Một participant đã prepare có thể phải giữ lock qua restart cho tới khi nhận được kết quả. Đây là lý do in-doubt transaction có thể làm ứng dụng bị block ngay cả khi database đã khởi động lại.

## 4. Vòng đời và trạng thái transaction

Các trạng thái khái niệm thường gặp trong distributed transaction:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Active | Transaction đang thực hiện công việc local/remote. |
| Preparing | Coordinator yêu cầu participant chuẩn bị. |
| Prepared | Participant đã vote YES và chờ quyết định cuối. |
| Committed | Participant đã hoàn tất commit. |
| Aborted/Rolled back | Transaction đã rollback. |
| In-doubt | Một hoặc nhiều site chưa xác định/hoàn tất được quyết định toàn cục do lỗi liên lạc hoặc crash. |

Trong Oracle dictionary, DBA_2PC_PENDING hiển thị các transaction đang pending/in-doubt và một số thông tin trạng thái. STATE trong view có thể dùng các giá trị như collecting, prepared, committed, forced commit, forced rollback tùy tình huống/release. Không suy diễn state từ tên khái niệm; xem giá trị thực tế và tài liệu Oracle.

### Prepared participant giữ lock

Participant đã vote YES không thể tự ý rollback chỉ vì coordinator mất liên lạc. Nó đã cam kết có thể commit nếu quyết định toàn cục là commit. Do đó, transaction có thể giữ row/table locks và làm các transaction khác chờ.

### In-doubt không nhất thiết là database hỏng

Database có thể OPEN và phục vụ các transaction khác trong khi một distributed transaction còn in-doubt. Tuy nhiên, lock trên các row liên quan có thể ảnh hưởng một phần workload. Cần điều tra transaction cụ thể thay vì restart database nhiều lần.

## 5. Commit point site và commit point strength

Commit point site là participant được chọn để commit trước theo quy tắc Oracle 2PC. Việc chọn site này giúp protocol có một điểm quyết định bền vững để các participant còn lại theo sau.

### COMMIT_POINT_STRENGTH

Tham số COMMIT_POINT_STRENGTH xác định strength của database khi Oracle lựa chọn commit point site. Giá trị cao hơn có mức ưu tiên cao hơn theo quy tắc Oracle.

Kiểm tra:

~~~sql
SHOW PARAMETER commit_point_strength;

SELECT name, value
FROM v$parameter
WHERE name = 'commit_point_strength';
~~~

### Không tùy tiện thay đổi strength

COMMIT_POINT_STRENGTH là cấu hình ảnh hưởng lựa chọn commit point trong distributed transaction. Không thay đổi chỉ để "ưu tiên" database quan trọng hơn nếu chưa hiểu tác động, phạm vi tham gia và recovery procedure. Giá trị cụ thể phải được quản trị nhất quán theo thiết kế.

### Commit point site không phải application coordinator

Site khởi tạo distributed transaction và commit point site là hai vai trò khác nhau. Coordinator điều phối protocol; commit point site là participant được chọn làm điểm commit trước. Đừng nhầm commit point site với server ứng dụng hoặc database nhận request đầu tiên.

## 6. Read-only participant optimization

Một participant chỉ đọc dữ liệu từ xa và không có thay đổi cần commit có thể được xử lý như read-only participant. Oracle có thể tối ưu protocol để participant read-only không cần tham gia đầy đủ các bước prepare/commit như participant có DML.

### Ví dụ

~~~sql
SELECT customer_name
INTO l_customer_name
FROM customers@crm_link
WHERE customer_id = p_customer_id;

UPDATE orders
SET customer_name = l_customer_name
WHERE order_id = p_order_id;
~~~

Participant CRM chỉ đọc; database local có thay đổi. Oracle có thể dùng read-only optimization tùy cấu trúc transaction. Nếu remote participant có DML, nó cần tham gia 2PC.

### Read-only optimization không phải distributed read consistency tổng quát

Tối ưu participant read-only trong 2PC không có nghĩa mọi SELECT qua nhiều database có một snapshot SCN duy nhất hoặc không thể thấy dữ liệu thay đổi giữa các site. Distributed query consistency có các quy tắc riêng; nếu nghiệp vụ cần snapshot đồng nhất, cần hiểu SCN, transaction isolation và khả năng hỗ trợ của phiên bản.

## 7. Oracle ghi nhận distributed transaction

Oracle lưu thông tin cần thiết để theo dõi các transaction branch ở từng database. Khi một transaction hoàn tất bình thường, các record quản lý transaction được dọn theo cơ chế nội bộ. Khi lỗi xảy ra trong giai đoạn 2PC, metadata có thể được giữ lại để RECO tiếp tục recovery.

### Local transaction ID và global transaction ID

- LOCAL_TRAN_ID nhận diện transaction branch tại database hiện tại.
- GLOBAL_TRAN_ID liên kết các branch thuộc cùng một distributed transaction toàn cục.
- Một global transaction có thể có nhiều local transaction IDs, mỗi ID thuộc một participant.

Không dùng local transaction ID của database A để force transaction trên database B nếu ID đó không phải branch tương ứng ở B. Thu thập ID và neighbor information tại từng participant.

### DBA_2PC_PENDING

DBA_2PC_PENDING liệt kê các distributed transactions đang pending/in-doubt tại database hiện tại. Một số cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| LOCAL_TRAN_ID | ID của transaction branch tại database hiện tại. |
| GLOBAL_TRAN_ID | ID toàn cục dùng để liên kết các branch. |
| STATE | Trạng thái branch đang pending. |
| MIXED | Cho biết có khả năng xảy ra mixed outcome. |
| ADVICE | Transaction advice nếu được cung cấp. |
| TRAN_COMMENT | Comment gắn với transaction nếu có. |
| FAIL_TIME | Thời điểm phát hiện lỗi/pending. |
| FORCE_TIME | Thời điểm có thao tác force nếu đã thực hiện. |
| RETRY_TIME | Thời điểm retry gần nhất theo metadata. |
| DB_USER | Database user liên quan. |

Kiểm tra:

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       tran_comment,
       fail_time,
       force_time,
       retry_time,
       db_user
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

Tên/cấu trúc cột có thể thay đổi theo release; dùng DESC DBA_2PC_PENDING để xác nhận trước khi tạo monitoring script. View chỉ cho biết trạng thái tại database hiện tại, không tự cung cấp quyết định toàn cục nếu coordinator/participant khác đang unreachable.

### DBA_2PC_NEIGHBORS

DBA_2PC_NEIGHBORS mô tả các database neighbor tham gia branch, bao gồm hướng kết nối và thông tin site liên quan.

~~~sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface,
       dbid,
       sess#,
       branch
FROM dba_2pc_neighbors
ORDER BY local_tran_id, in_out;
~~~

IN_OUT thường phân biệt neighbor hướng vào/hướng ra theo quan hệ protocol. DATABASE và DBID giúp xác định remote database; INTERFACE mô tả cách kết nối/participant theo metadata. Kiểm tra DESC trên đúng release để xác nhận cột có sẵn.

### Xem cả pending transaction và neighbor

~~~sql
SELECT p.local_tran_id,
       p.global_tran_id,
       p.state,
       p.mixed,
       n.in_out,
       n.database,
       n.dbid
FROM dba_2pc_pending p
LEFT JOIN dba_2pc_neighbors n
  ON n.local_tran_id = p.local_tran_id
ORDER BY p.local_tran_id, n.in_out;
~~~

Đây là góc nhìn local. Để hiểu toàn bộ transaction, DBA thường phải kết nối tới từng database liên quan và đối chiếu global ID, local branch ID, state và neighbor records.

## 8. RECO tự động giải quyết in-doubt

RECO (Recoverer) là background process của Oracle chịu trách nhiệm tự động giải quyết các distributed transactions bị in-doubt. Khi database có transaction branch đang pending, RECO định kỳ thử kết nối tới các participant/coordinator cần thiết để lấy quyết định cuối cùng.

### RECO làm gì?

- Phát hiện transaction branch cần recovery.
- Thử kết nối tới database neighbor.
- Trao đổi thông tin trạng thái/decision của global transaction.
- Hoàn tất commit hoặc rollback branch theo quyết định đã được ghi nhận.
- Dọn metadata pending khi toàn bộ protocol được giải quyết.

### RECO cần gì để hoạt động?

- Database liên quan phải có thể truy cập qua Oracle Net/database link theo cấu hình.
- TNS/service resolution phải đúng.
- Listener, network, firewall và credential/remote authentication phải hoạt động.
- Database participant phải mở ở trạng thái phù hợp để xử lý recovery.
- Transaction metadata không bị xóa hoặc force sai ở một site.

### Theo dõi background process

~~~sql
SELECT pname, description, tracefile
FROM v$process
WHERE pname LIKE 'RECO%';
~~~

Tên/cách hiển thị process phụ thuộc platform/version. Có thể kiểm tra background processes qua V$BGPROCESS:

~~~sql
SELECT name, description
FROM v$bgprocess
WHERE name = 'RECO';
~~~

Nếu RECO không giải quyết được transaction, xem alert log và trace file để tìm lỗi kết nối, authentication hoặc participant state.

### Đừng cố restart RECO như một tiến trình ứng dụng

RECO là background process do Oracle quản lý. Không kill OS process RECO hoặc thao tác trực tiếp trên internal transaction tables. Khôi phục network/database connectivity và để Oracle retry. Nếu cần can thiệp, dùng các câu lệnh/documented package được Oracle hỗ trợ.

### Thời gian retry

RECO retry theo cơ chế nội bộ và tham số/cấu hình của Oracle release. Không đặt một SLA cố định kiểu "sau N giây sẽ tự giải quyết". Theo dõi RETRY_TIME, alert log, network và trạng thái remote site.

## 9. Điều tra in-doubt transaction theo thứ tự

Khi phát hiện transaction in-doubt, điều quan trọng nhất là xác định quyết định toàn cục. Không force trên một participant trước khi thu thập bằng chứng từ các site.

### Bước 1: ghi nhận transaction branch

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time,
       db_user,
       tran_comment
FROM dba_2pc_pending;
~~~

Ghi lại LOCAL_TRAN_ID, GLOBAL_TRAN_ID, STATE, MIXED, thời gian và user.

### Bước 2: xác định neighbors

~~~sql
SELECT local_tran_id,
       in_out,
       database,
       dbid,
       branch
FROM dba_2pc_neighbors
WHERE local_tran_id = :local_tran_id;
~~~

Xác định coordinator và participant còn lại từ thông tin neighbor. Nếu view không đủ, dùng transaction comment, application logs, database link name, alert log và thông tin transaction ở ứng dụng.

### Bước 3: kiểm tra kết nối tới từng site

Kiểm tra TNS alias/service, listener, network route, firewall, DNS, credentials và database availability. Một transaction in-doubt thường tự được giải quyết khi các site có thể liên lạc lại.

### Bước 4: kiểm tra trạng thái trên tất cả participant

Kết nối tới từng database có liên quan và chạy truy vấn DBA_2PC_PENDING/NEIGHBORS. So sánh GLOBAL_TRAN_ID, local branch, state, commit number nếu có và log records. Không chỉ dựa vào một site.

### Bước 5: tìm quyết định coordinator

Xác định coordinator/commit point site và xem transaction đã commit hay rollback. Kiểm tra alert log, trace, application logs và trạng thái branch. Nếu coordinator đã hoàn tất commit, các participant còn pending cần được hoàn tất commit; nếu quyết định rollback, tất cả branch phải rollback.

### Bước 6: khôi phục đường kết nối

Sửa database link/TNS/service/network/authentication. Sau đó để RECO retry và kiểm tra DBA_2PC_PENDING cho tới khi transaction được giải quyết.

### Bước 7: chỉ cân nhắc FORCE khi có bằng chứng

Nếu không thể phục hồi kết nối hoặc coordinator không còn tồn tại, DBA cần một quy trình quyết định thủ công dựa trên log/bằng chứng có thẩm quyền. Chỉ khi xác định chắc chắn commit hay rollback mới dùng FORCE COMMIT/FORCE ROLLBACK cho branch tương ứng.

### Ghi nhận hồ sơ incident

- Global transaction ID và mọi local transaction IDs.
- Danh sách database participants và commit point site.
- State của mỗi branch.
- Commit/rollback decision evidence.
- Thời điểm network/database outage và khôi phục.
- Các lệnh force (nếu có), operator và phê duyệt.
- Đối chiếu dữ liệu nghiệp vụ sau khi hoàn tất.

## 10. COMMIT FORCE và ROLLBACK FORCE

Oracle cung cấp các lệnh force để DBA giải quyết một transaction branch in-doubt khi RECO không thể hoàn tất tự động và đã xác định quyết định toàn cục bằng bằng chứng đáng tin cậy.

### COMMIT FORCE

Nếu bằng chứng cho thấy global transaction đã commit và branch hiện tại chỉ còn pending, có thể buộc branch này commit:

~~~sql
COMMIT FORCE 'local_tran_id';
~~~

Ví dụ cú pháp:

~~~sql
COMMIT FORCE '12.34.567';
~~~

Chuỗi trong ví dụ chỉ minh họa định dạng local transaction ID; phải thay bằng LOCAL_TRAN_ID thật từ DBA_2PC_PENDING trên database hiện tại.

### ROLLBACK FORCE

Nếu bằng chứng cho thấy quyết định toàn cục là rollback, có thể buộc branch hiện tại rollback:

~~~sql
ROLLBACK FORCE 'local_tran_id';
~~~

Không dùng COMMIT FORCE chỉ vì muốn giải phóng lock, cũng không dùng ROLLBACK FORCE chỉ vì transaction đã pending lâu. Lệnh force có thể làm một branch đi ngược quyết định đã được ghi nhận ở site khác.

### FORCE giải quyết branch local

FORCE COMMIT/ROLLBACK áp dụng cho transaction branch có LOCAL_TRAN_ID trong database hiện tại. Một global transaction có thể có nhiều branch. DBA phải xác định và giải quyết các branch pending trên tất cả participants theo cùng một quyết định toàn cục.

### Trước khi force

Phải có:

- Global transaction ID và local branch ID đã đối chiếu.
- Bằng chứng quyết định commit/rollback từ coordinator hoặc commit point site.
- Trạng thái các participant còn lại.
- Bản ghi alert/trace/application log hỗ trợ.
- Phê duyệt incident/change của người có thẩm quyền.
- Kế hoạch đối chiếu dữ liệu sau khi force.

Nếu không thể xác định decision, không force. Khôi phục coordinator/network hoặc chuyển incident tới DBA cấp cao/Oracle Support.

### Sau khi force

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       force_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

Ghi lại lệnh, người thực hiện và thời điểm. RECO có thể cần tiếp tục giải quyết các neighbors; kiểm tra view cho tới khi transaction được dọn theo cơ chế Oracle. Không xóa trực tiếp rows trong SYS transaction tables.

## 11. Mixed outcome và rủi ro không nhất quán

MIXED='YES' trong DBA_2PC_PENDING là tín hiệu nghiêm trọng cho thấy các branch của global transaction có thể đã kết thúc theo các kết quả khác nhau, chẳng hạn có participant commit trong khi participant khác rollback/được force theo hướng ngược lại.

### Tại sao mixed outcome nguy hiểm?

Distributed transaction được thiết kế để atomic. Nếu một phần branch commit và phần khác rollback, ứng dụng có thể có dữ liệu nghiệp vụ không khớp:

- Đơn hàng được xác nhận nhưng tồn kho không bị trừ.
- Tiền đã ghi nợ ở một database nhưng không ghi có ở database kia.
- Một bản ghi điều phối tồn tại nhưng participant chưa cập nhật.

### Cách xử lý

1. Không tiếp tục force branch khác theo phỏng đoán.
2. Thu thập tất cả local/global IDs ở mọi participant.
3. Xác định branch nào đã commit, branch nào rollback.
4. Đối chiếu decision record, audit, redo/transaction state và nghiệp vụ.
5. Xây dựng kế hoạch compensation/reconciliation có phê duyệt.
6. Chỉ dùng thủ tục cleanup được Oracle hỗ trợ sau khi trạng thái dữ liệu đã được xử lý.

### Không sửa dictionary nội bộ

Không DELETE/UPDATE trực tiếp các bảng SYS liên quan transaction, pending transaction hoặc two-phase commit. Các bảng nội bộ không phải API quản trị. Sửa trực tiếp có thể làm metadata không nhất quán và khiến recovery không thể hoàn tất.

### PURGE_LOST_DB_ENTRY và PURGE_MIXED

DBMS_TRANSACTION có các thủ tục quản lý một số entry pending/mixed trong những tình huống recovery đặc biệt. Đây là thao tác cleanup có hậu quả và chỉ được dùng theo hướng dẫn Oracle sau khi transaction đã được xác định, dữ liệu được đối chiếu và các branch cần thiết đã được xử lý.

Không dùng PURGE_LOST_DB_ENTRY để xóa một transaction còn in-doubt đang chờ quyết định. Không dùng PURGE_MIXED để che giấu mixed outcome trước khi reconcile dữ liệu. Kiểm tra tài liệu đúng release và cân nhắc Oracle Support trước khi gọi các thủ tục này.

## 12. Distributed locks và tác động tới ứng dụng

Participant đã prepare thường giữ các lock liên quan cho tới khi nhận quyết định cuối. Các session khác có thể chờ khi truy cập cùng row/table hoặc tài nguyên bị khóa.

### Dấu hiệu lock contention

- UPDATE/DELETE bị treo dù SQL plan đơn giản.
- Session chờ transaction khác kết thúc.
- Ứng dụng báo timeout hoặc ORA-02049.
- DBA_2PC_PENDING có transaction ở trạng thái prepared/in-doubt.
- Blocking session thuộc transaction distributed.

### Tìm blocking sessions

~~~sql
SELECT sid,
       serial#,
       username,
       blocking_session,
       event,
       wait_class,
       seconds_in_wait,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Để xem locks:

~~~sql
SELECT lo.session_id AS sid,
       lo.oracle_username,
       lo.locked_mode,
       ob.owner,
       ob.object_name,
       ob.object_type
FROM v$locked_object lo
JOIN dba_objects ob
  ON ob.object_id = lo.object_id
ORDER BY lo.session_id, ob.owner, ob.object_name;
~~~

Các view này giúp tìm session/object đang bị khóa nhưng không tự chứng minh lock đến từ in-doubt transaction. Đối chiếu SID, transaction IDs, DBA_2PC_PENDING, V$TRANSACTION và alert log.

### V$TRANSACTION và transaction metadata

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.xidusn,
       t.xidslot,
       t.xidsqn,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr;
~~~

V$TRANSACTION hiển thị transaction đang hoạt động trong instance. Một branch in-doubt có thể không xuất hiện như transaction active thông thường sau restart; cần dùng DBA_2PC_PENDING để điều tra pending branch.

### DISTRIBUTED_LOCK_TIMEOUT

DISTRIBUTED_LOCK_TIMEOUT xác định khoảng thời gian chờ lock trong một số distributed transaction operations trước khi trả lỗi timeout (thường ORA-02049). Kiểm tra:

~~~sql
SHOW PARAMETER distributed_lock_timeout;
~~~

Tham số này không phải thời gian RECO retry và không quyết định transaction in-doubt tự commit hay rollback. Tăng timeout chỉ làm session chờ lâu hơn; nó không giải quyết nguyên nhân coordinator/participant mất kết nối hoặc branch giữ lock.

### Không kill blocker như giải pháp đầu tiên

Kill session không bảo đảm giải quyết branch đã prepared/in-doubt. Một số thao tác chỉ khiến cleanup/rollback cần thời gian hoặc vẫn giữ transaction metadata. Trước khi kill, xác định session/transaction, vai trò coordinator, participant state và hậu quả nghiệp vụ.

## 13. Các tình huống lỗi thường tạo in-doubt transaction

### Coordinator mất kết nối sau PREPARE

Participant đã vote YES và giữ trạng thái prepared, nhưng không nhận được quyết định cuối. Khi đó branch có thể ở trạng thái in-doubt và giữ lock. Sau khi coordinator trở lại, RECO có thể trao đổi decision và hoàn tất.

### Participant mất kết nối

Coordinator có thể đã ghi quyết định commit/rollback nhưng không thể liên lạc tới participant. Participant có thể còn pending cho tới khi network/database được phục hồi và RECO nhận được decision.

### Database restart trong giai đoạn 2PC

Sau restart, Oracle đọc transaction metadata từ redo/transaction tables và tiếp tục recovery. Branch đã prepared có thể tiếp tục in-doubt; không tự ý rollback chỉ vì instance đã khởi động lại.

### Network partition

Coordinator và participant có thể cùng chạy nhưng không liên lạc được. 2PC ưu tiên tính nguyên tử nên participant đã prepared có thể chờ quyết định thay vì tự quyết. Đây là trade-off giữa consistency và availability khi mất liên lạc.

### Commit point site lỗi

Nếu commit point site gặp sự cố đúng lúc commit decision được ghi/lan truyền, các participant có thể phải chờ cho tới khi site đó khôi phục hoặc quyết định có thể được xác minh từ log/recovery. Không đoán commit/rollback từ việc ứng dụng đã nhận timeout.

### Database link hoặc authentication thay đổi

TNS alias, service name, password, wallet, database link credential hoặc remote_listener thay đổi có thể khiến RECO không kết nối được. Sửa đúng đường kết nối và xác nhận từ database participant, không chỉ từ máy client.

## 14. Thiết kế ứng dụng để giảm rủi ro distributed transaction

2PC cung cấp atomic commit nhưng có chi phí network, logging, lock retention và phụ thuộc coordinator. Thiết kế ứng dụng nên giảm số participant và thời gian transaction.

### Giữ transaction ngắn

- Chỉ mở distributed transaction khi cần thực hiện các DML liên quan.
- Không gọi người dùng, API HTTP hoặc xử lý lâu trong khi giữ transaction.
- Tránh đọc/ghi nhiều remote database không cần thiết.
- Hoàn tất validation trước khi bắt đầu transaction nếu dữ liệu cho phép.
- Commit/rollback rõ ràng; không giữ transaction mở trong connection pool.

### Giảm số participant

Nếu một nghiệp vụ cập nhật 5 database, mỗi site thêm một điểm lỗi và network dependency. Cân nhắc gom dữ liệu cùng consistency boundary vào một database, dùng service boundary phù hợp hoặc xử lý bất đồng bộ cho những bước không cần atomic ngay.

### Dùng local transaction khi có thể

Nếu dữ liệu có thể được quản lý trong cùng database/schema, local transaction thường đơn giản và ít failure modes hơn. Database link không nên là cách mặc định để kết hợp mọi service/database.

### Outbox pattern

Khi một thay đổi local cần phát sự kiện cho hệ thống khác nhưng không cần commit đồng thời trên mọi database, có thể dùng transactional outbox:

1. Trong một local transaction, cập nhật dữ liệu nghiệp vụ và ghi event vào outbox table.
2. Commit local transaction.
3. Worker đọc outbox và gửi event tới hệ thống đích.
4. Hệ thống đích xử lý idempotently và xác nhận.
5. Worker đánh dấu event đã gửi hoặc retry.

Outbox không cung cấp atomic commit tức thời giữa các database; nó cung cấp eventual delivery có thể retry, dễ vận hành hơn trong nhiều integration scenarios.

### Saga và compensating transaction

Với workflow dài qua nhiều service/database, Saga chia nghiệp vụ thành các local transactions và định nghĩa compensating actions khi một bước sau thất bại. Ví dụ đặt hàng -> giữ tồn kho -> thu tiền; nếu thu tiền thất bại, giải phóng tồn kho bằng transaction bù.

Compensation không phải rollback vật lý của transaction đã commit. Nó là nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được. Cần thiết kế idempotency, retry, timeout, deduplication và trạng thái workflow rõ ràng.

### Khi nào vẫn nên dùng 2PC?

2PC phù hợp khi:

- Các database participant hỗ trợ distributed transaction và yêu cầu atomicity thực sự.
- Transaction ngắn, số participant hạn chế.
- Hạ tầng network/database có độ tin cậy và monitoring tốt.
- Tổ chức có khả năng vận hành RECO, in-doubt recovery và incident response.
- Việc eventual consistency/compensation không đáp ứng yêu cầu nghiệp vụ.

### Retry phải an toàn

Client timeout sau COMMIT không chứng minh transaction rollback. Trước khi retry một thao tác tài chính/đơn hàng, ứng dụng phải kiểm tra trạng thái transaction hoặc dùng business request ID/idempotency key để tránh thực hiện lặp.

## 15. Giám sát distributed transactions

Monitoring nên bao gồm pending transaction count, tuổi transaction, state, MIXED flag, retry time, neighbor reachability và lock impact.

### Đếm pending transactions

~~~sql
SELECT state,
       mixed,
       COUNT(*) AS transaction_count,
       MIN(fail_time) AS oldest_fail_time,
       MAX(fail_time) AS newest_fail_time
FROM dba_2pc_pending
GROUP BY state, mixed
ORDER BY state, mixed;
~~~

### Tìm transaction pending lâu nhất

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time,
       ROUND((SYSDATE - fail_time) * 24 * 60, 1) AS pending_minutes
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

Biểu thức thời gian minh họa cho FAIL_TIME dạng DATE; xác nhận datatype bằng DESC. Nếu FAIL_TIME là timestamp ở release cụ thể, dùng phép tính interval phù hợp.

### Xem neighbors của các transaction pending

~~~sql
SELECT p.local_tran_id,
       p.global_tran_id,
       p.state,
       n.in_out,
       n.database,
       n.dbid
FROM dba_2pc_pending p
LEFT JOIN dba_2pc_neighbors n
  ON n.local_tran_id = p.local_tran_id
ORDER BY p.fail_time, p.local_tran_id;
~~~

### Theo dõi RECO và alert log

Kiểm tra alert log để tìm thông điệp RECO retry, lỗi kết nối, participant unreachable hoặc transaction resolution. Dùng ADRCI hoặc V$DIAG_ALERT_EXT nếu được cấp quyền:

~~~sql
SELECT originating_timestamp,
       message_text
FROM v$diag_alert_ext
WHERE UPPER(message_text) LIKE '%RECO%'
   OR UPPER(message_text) LIKE '%IN-DOUBT%'
ORDER BY originating_timestamp DESC;
~~~

V$DIAG_ALERT_EXT là view diagnostic; quyền truy cập và cột có thể khác theo release.

### Alert thresholds

Đặt cảnh báo theo:

- Có bất kỳ transaction MIXED='YES'.
- Pending transaction vượt tuổi mục tiêu.
- Số lượng pending tăng liên tục.
- RECO retry không thành công.
- Neighbor/database link không kết nối được.
- Lock waits và application timeouts tăng.

Ngưỡng tuổi cần theo SLA và workload; không tự động force transaction khi quá một số phút cố định.

## 16. Lỗi thường gặp và cách xử lý

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-02050 | Distributed transaction rolled back; một số remote database có thể còn in-doubt | Kiểm tra DBA_2PC_PENDING/NEIGHBORS trên mọi participant và để RECO resolve. |
| ORA-02054 | Transaction in-doubt | Xác định global/local transaction IDs, khôi phục coordinator/network, không force theo phỏng đoán. |
| ORA-02055 | Distributed update operation failed; cần rollback transaction | Rollback theo trạng thái transaction và kiểm tra remote branch. |
| ORA-02049 | Timeout khi distributed transaction chờ lock | Xác định blocker, lock duration, transaction scope và DISTRIBUTED_LOCK_TIMEOUT. |
| ORA-02068 | Có lỗi nghiêm trọng theo sau từ remote database | Đọc lỗi tiếp theo và ORA-02063, kiểm tra remote alert log. |
| ORA-02063 | Dòng trước đó phát sinh từ database link được chỉ định | Điều tra lỗi gốc ở remote database; đây thường là thông tin bổ sung. |
| ORA-02019 | Không tìm thấy connect description cho remote database | Kiểm tra database link, TNS alias, tnsnames.ora và naming method. |
| ORA-02085 | Database link kết nối tới database name khác tên kỳ vọng | Kiểm tra GLOBAL_NAMES và tên database link/remote database. |
| ORA-12154 | Không phân giải được connect identifier | Kiểm tra TNS_ADMIN, tnsnames.ora, LDAP/EZCONNECT và service alias. |
| ORA-12514 | Listener không biết service được yêu cầu | Kiểm tra service registration, listener và connect descriptor. |
| ORA-03113/ORA-03135 | Kết nối bị ngắt/timeout | Kiểm tra network, process, alert log và remote database availability. |
| Transaction pending lâu | Coordinator/participant unreachable hoặc decision chưa được trao đổi | Kiểm tra neighbors, RECO, network và transaction state trên các site. |
| Row lock kéo dài | Participant prepared/in-doubt có thể đang giữ lock | Liên kết session/transaction với DBA_2PC_PENDING; tránh kill/force tùy tiện. |
| MIXED='YES' | Có thể có outcome không nhất quán giữa branches | Dừng force, đối chiếu tất cả site, reconciliation và Oracle Support khi cần. |

### Phân biệt lỗi ứng dụng với in-doubt

Ứng dụng nhận exception hoặc timeout không đủ để kết luận global transaction in-doubt. Cần truy vấn DBA_2PC_PENDING, xem remote alert log và xác định transaction branch. Một lỗi network có thể xảy ra trước PREPARE, trong PREPARE hoặc sau COMMIT; hậu quả khác nhau.

## 17. Quy trình vận hành khi phát hiện in-doubt

Runbook cần ưu tiên khôi phục protocol tự động. FORCE là bước ngoại lệ sau khi xác định decision, không phải bước đầu tiên.

### Giai đoạn A: bảo toàn và phân loại

1. Ghi nhận thời điểm, ứng dụng, request ID và lỗi client.
2. Xác định database coordinator, participants và commit point site nếu có.
3. Truy vấn DBA_2PC_PENDING và DBA_2PC_NEIGHBORS trên database phát hiện sự cố.
4. Ghi lại LOCAL_TRAN_ID, GLOBAL_TRAN_ID, STATE, MIXED và FAIL_TIME.
5. Kiểm tra alert log/trace ở các database liên quan.
6. Không xóa database link, user hoặc transaction metadata trong lúc điều tra.

### Giai đoạn B: khôi phục connectivity

1. Xác nhận các database instance đang hoạt động.
2. Kiểm tra listener và service name.
3. Kiểm tra database link và remote authentication.
4. Kiểm tra network route, firewall, DNS và TLS/wallet nếu có.
5. Thử kết nối từ đúng database host/context.
6. Khôi phục đường liên lạc mà không thay đổi transaction decision.

### Giai đoạn C: để RECO hoàn tất

1. Theo dõi alert log/RECO retry.
2. Truy vấn DBA_2PC_PENDING theo chu kỳ hợp lý.
3. Xác nhận pending rows được giải quyết và lock được giải phóng.
4. Kiểm tra trạng thái trên các participant.
5. Đối chiếu kết quả nghiệp vụ với global transaction ID/request ID.

### Giai đoạn D: quyết định thủ công nếu không thể tự recovery

1. Xác định chắc chắn coordinator/commit point site hoặc bằng chứng decision.
2. Xác nhận branch local đang pending trên từng participant.
3. Nếu decision COMMIT, force commit branch cần thiết theo từng local transaction ID.
4. Nếu decision ROLLBACK, force rollback branch cần thiết theo từng local transaction ID.
5. Ghi nhận mọi lệnh force và phê duyệt.
6. Theo dõi RECO và kiểm tra MIXED flag.
7. Nếu MIXED='YES' hoặc decision không rõ, dừng và escalates tới Oracle Support/DBA chuyên trách; xây dựng reconciliation plan.

### Giai đoạn E: xác nhận dữ liệu và đóng incident

- Kiểm tra row counts, status, balances và business invariants trên mọi database.
- Đối chiếu application request với transaction global ID.
- Xác nhận không còn pending branch liên quan.
- Kiểm tra blocking sessions và locks.
- Ghi root cause, thời gian khôi phục và hành động phòng ngừa.

## 18. Bài thực hành: distributed transaction qua database link

Bài lab cần hai Oracle databases độc lập (LOCALDB và REMOTEDB), hai schema lab và database link riêng. Chỉ thực hiện trong môi trường học tập. Không tạo link public hoặc dùng credential production.

### Bước 1: tạo bảng ở database remote

Kết nối trực tiếp tới REMOTEDB bằng schema lab:

~~~sql
CREATE TABLE lab_inventory (
    product_id NUMBER PRIMARY KEY,
    quantity NUMBER NOT NULL,
    CONSTRAINT ck_lab_inventory_qty CHECK (quantity >= 0)
);

INSERT INTO lab_inventory(product_id, quantity)
VALUES (100, 20);

COMMIT;
~~~

### Bước 2: tạo bảng ở database local

Kết nối LOCALDB bằng schema lab:

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    product_id NUMBER NOT NULL,
    order_qty NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL
);

INSERT INTO lab_orders(order_id, product_id, order_qty, status)
VALUES (9001, 100, 1, 'NEW');

COMMIT;
~~~

### Bước 3: tạo private database link

Trong schema local:

~~~sql
CREATE DATABASE LINK remote_lab_link
CONNECT TO remote_lab IDENTIFIED BY "<lab-secret>"
USING 'REMOTEDB_SERVICE';
~~~

Thay remote user, secret và connect identifier bằng cấu hình lab. Không lưu mật khẩu thật trong source control hoặc file bài học. Remote user cần quyền truy cập object cụ thể; không cấp DBA/SYSDBA cho database link account.

Kiểm tra:

~~~sql
SELECT * FROM dual@remote_lab_link;

SELECT product_id, quantity
FROM lab_inventory@remote_lab_link
WHERE product_id = 100;
~~~

### Bước 4: thực hiện distributed DML

~~~sql
UPDATE lab_orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

UPDATE lab_inventory@remote_lab_link
SET quantity = quantity - 1
WHERE product_id = 100
  AND quantity >= 1;

COMMIT;
~~~

Trong ứng dụng thực tế, kiểm tra SQL%ROWCOUNT của remote DML để bảo đảm có đúng một hàng được cập nhật; nếu không đạt điều kiện, rollback transaction. Bài lab trên tập trung minh họa một COMMIT bao gồm thay đổi local và remote.

### Bước 5: xác minh cả hai database

LOCALDB:

~~~sql
SELECT order_id, status
FROM lab_orders
WHERE order_id = 9001;
~~~

REMOTEDB (truy vấn trực tiếp hoặc qua link):

~~~sql
SELECT product_id, quantity
FROM lab_inventory
WHERE product_id = 100;
~~~

Kết quả cần thể hiện order CONFIRMED và quantity giảm đúng một đơn vị.

### Bước 6: thử rollback

Trong LOCALDB:

~~~sql
UPDATE lab_orders
SET status = 'CANCELLED'
WHERE order_id = 9001;

UPDATE lab_inventory@remote_lab_link
SET quantity = quantity + 1
WHERE product_id = 100;

ROLLBACK;
~~~

Xác minh cả hai database vẫn giữ trạng thái trước transaction rollback. Đây là kiểm tra rollback bình thường, chưa phải mô phỏng in-doubt.

### Bước 7: quan sát metadata khi transaction bình thường

Trong lúc transaction đang chạy, có thể dùng session thứ hai có quyền DBA để quan sát transaction/locks. DBA_2PC_PENDING chủ yếu hiển thị branch pending/in-doubt, vì vậy một transaction hoàn tất bình thường có thể không để lại row ở view sau commit.

~~~sql
SELECT local_tran_id, global_tran_id, state, mixed
FROM dba_2pc_pending;
~~~

Nếu không có hàng sau khi commit bình thường, đó là kết quả mong đợi.

### Bước 8: diễn tập in-doubt trên môi trường cô lập

Tạo một clone/lab riêng và phối hợp DBA quản trị cả hai databases:

1. Bật logging/monitoring và ghi lại DBID, service, database link, alert log locations.
2. Chuẩn bị một cách cô lập network giữa LOCALDB và REMOTEDB có thể bật/tắt nhanh, chỉ áp dụng cho lab.
3. Thực hiện distributed DML và phối hợp fault injection tại thời điểm 2PC PREPARE/decision đang diễn ra.
4. Ghi lại lỗi client và kiểm tra DBA_2PC_PENDING/NEIGHBORS trên cả hai site.
5. Khôi phục network path.
6. Quan sát RECO retry và transaction tự giải quyết.
7. Xác nhận dữ liệu ở hai site nhất quán.

Thời điểm tạo in-doubt không thể bảo đảm bằng một câu SQL thông thường; cần fault injection có kiểm soát hoặc kịch bản do DBA/Oracle Support hướng dẫn. Không kill process/network trên database dùng chung để cố tạo trạng thái này.

### Bước 9: dọn lab

LOCALDB:

~~~sql
DROP DATABASE LINK remote_lab_link;
DROP TABLE lab_orders PURGE;
~~~

REMOTEDB:

~~~sql
DROP TABLE lab_inventory PURGE;
~~~

Chỉ xóa các object do bài lab tạo. Nếu có pending transaction, giải quyết trước khi drop link/user hoặc dọn schema.

## 19. Checklist thiết kế và vận hành

### Trước khi dùng distributed transaction

- Xác định nghiệp vụ có thật sự cần atomic commit xuyên database không.
- Giảm số participant và thời gian transaction.
- Kiểm tra database links, network, service và authentication.
- Xác nhận các database hỗ trợ distributed transaction protocol phù hợp.
- Xác định coordinator/participant/commit point site.
- Kiểm tra backup, redo, alert log và monitoring.
- Định nghĩa idempotency và retry behavior ở ứng dụng.

### Khi vận hành

- Giám sát DBA_2PC_PENDING và DBA_2PC_NEIGHBORS.
- Cảnh báo pending age và MIXED='YES'.
- Theo dõi RECO retry và network health.
- Theo dõi blocking sessions/locks.
- Bảo đảm TNS/service/password rotation không làm mất đường recovery.
- Không kill session hoặc force transaction khi chưa có decision evidence.

### Khi incident

- Thu thập global/local IDs và mọi participant states.
- Khôi phục connectivity trước.
- Để RECO giải quyết tự động.
- Force chỉ theo decision đã xác minh.
- Reconcile business data nếu mixed outcome.
- Ghi lại incident và diễn tập lại kịch bản.

## 20. Câu hỏi tự kiểm tra

1. **Distributed transaction là gì?** Một transaction thay đổi nhiều database/resource managers nhưng cần một kết quả nguyên tử.
2. **Database link dùng để làm gì?** Cho phép session truy cập object ở database từ xa.
3. **2PC có hai giai đoạn nào?** PREPARE và COMMIT/ROLLBACK.
4. **Participant vote YES có nghĩa gì?** Branch đã prepared và có thể commit khi nhận quyết định; chưa phải đã commit.
5. **Coordinator làm gì?** Điều phối prepare, thu votes và truyền quyết định toàn cục.
6. **Commit point site là gì?** Participant được chọn commit trước theo quy tắc Oracle 2PC.
7. **COMMIT_POINT_STRENGTH dùng để làm gì?** Hỗ trợ lựa chọn commit point site.
8. **RECO là gì?** Background process tự động recovery distributed transactions in-doubt.
9. **In-doubt transaction có thể giữ lock không?** Có, participant prepared có thể giữ lock cho tới khi quyết định cuối được nhận.
10. **DBA_2PC_PENDING hiển thị gì?** Các distributed transaction branches pending/in-doubt tại database hiện tại.
11. **DBA_2PC_NEIGHBORS cho biết gì?** Thông tin database participants/neighbors liên quan branch.
12. **LOCAL_TRAN_ID và GLOBAL_TRAN_ID khác nhau thế nào?** Local ID nhận diện branch tại một database; global ID liên kết transaction trên nhiều site.
13. **MIXED='YES' báo hiệu gì?** Có thể có kết quả commit/rollback khác nhau giữa các branches; cần reconciliation khẩn cấp.
14. **Khi nào dùng COMMIT FORCE?** Khi đã xác minh global decision là commit nhưng branch local còn in-doubt.
15. **Khi nào dùng ROLLBACK FORCE?** Khi đã xác minh global decision là rollback và branch local cần được force rollback.
16. **Có thể force chỉ dựa vào transaction pending lâu không?** Không.
17. **DISTRIBUTED_LOCK_TIMEOUT điều khiển gì?** Thời gian chờ lock trong một số distributed operations, không phải RECO retry interval.
18. **Vì sao không xóa trực tiếp SYS transaction tables?** Có thể phá metadata protocol và làm recovery không nhất quán.
19. **Read-only participant optimization là gì?** Tối ưu cho participant chỉ đọc, không có thay đổi cần commit.
20. **2PC có thể gây block khi network partition không?** Có; participant prepared có thể chờ decision để giữ atomicity.
21. **Outbox pattern khác 2PC thế nào?** Outbox commit local rồi phát sự kiện bất đồng bộ, hỗ trợ eventual consistency thay vì atomic commit xuyên database.
22. **Saga dùng gì khi một bước thất bại?** Compensating transactions để đưa workflow về trạng thái nghiệp vụ chấp nhận được.
23. **Client timeout sau COMMIT có chứng minh rollback không?** Không; transaction có thể đã commit nhưng response bị mất.
24. **Vì sao retry cần idempotency key?** Để tránh thực hiện nghiệp vụ lặp khi kết quả lần trước chưa rõ.
25. **Bước đầu tiên khi in-doubt xuất hiện là gì?** Thu thập IDs/states/neighbors và khôi phục connectivity, không force ngay.

Distributed transaction qua database links dùng two-phase commit để phối hợp các database participants. Participant prepared giữ trạng thái và lock cho tới khi nhận quyết định commit/rollback; nếu coordinator hoặc network gặp sự cố, branch có thể trở thành in-doubt. DBA_2PC_PENDING và DBA_2PC_NEIGHBORS cung cấp thông tin điều tra, còn RECO tự động thử giải quyết khi connectivity trở lại. COMMIT FORCE/ROLLBACK FORCE chỉ dùng sau khi xác minh decision toàn cục; MIXED outcome cần reconciliation và hỗ trợ chuyên trách. Với workflow dài hoặc nhiều service, cân nhắc outbox/Saga để giảm phụ thuộc 2PC. Thiết kế tốt cần transaction ngắn, ít participant, retry idempotent, monitoring pending/locks và diễn tập fault recovery định kỳ.
