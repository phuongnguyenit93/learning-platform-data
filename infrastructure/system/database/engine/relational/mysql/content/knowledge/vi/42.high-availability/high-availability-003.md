# Single-primary/multi-primary và giới hạn mô hình ghi

MySQL Group Replication cung cấp hai mô hình ghi chính: **single-primary**, trong đó chỉ một thành viên nhận giao dịch ghi tại một thời điểm, và **multi-primary**, trong đó nhiều thành viên có thể nhận ghi đồng thời. Hai mô hình dùng chung cơ chế replication và certification của Group Replication, nhưng khác nhau ở cách định tuyến ghi, xử lý xung đột và độ phức tạp vận hành.

Chọn mô hình phù hợp là quyết định về tính nhất quán và luồng nghiệp vụ, không chỉ là bật thêm nơi nhận lệnh ghi. Multi-primary không chia dữ liệu thành nhiều phần và cũng không tự động làm tăng thông lượng ghi tuyến tính theo số node. Mọi thành viên vẫn duy trì bản sao của cùng tập dữ liệu; các transaction cạnh tranh phải được kiểm tra để giữ trạng thái nhất quán.

Bài học thuộc chương **Sẵn sàng cao** của module `DATABASE_MYSQL`. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index, transaction, kiểm soát đồng thời, tối ưu, phân quyền, backup và vận hành cơ sở dữ liệu quan hệ. Nội dung tập trung vào MySQL Group Replication và InnoDB Cluster trên MySQL 8.0; tên lệnh và giới hạn cụ thể cần được đối chiếu với phiên bản đang triển khai.

Sau bài học, bạn có thể:

- Phân biệt single-primary và multi-primary trong Group Replication.
- Mô tả luồng ghi và cơ chế certification của transaction.
- Nhận diện xung đột ghi và giới hạn của mô hình multi-primary.
- Chọn mô hình dựa trên workload, vị trí ứng dụng và yêu cầu sẵn sàng.
- Chuyển chế độ bằng MySQL Shell AdminAPI trong điều kiện phù hợp.
- Thiết kế định tuyến, retry, giám sát và diễn tập failover.

## 1. Phạm vi: Group Replication và InnoDB Cluster

Single-primary và multi-primary là hai chế độ hoạt động của **MySQL Group Replication**. InnoDB Cluster dùng Group Replication để duy trì các thành viên dữ liệu, MySQL Shell AdminAPI để quản trị cụm và MySQL Router để định tuyến kết nối ứng dụng.

Cần phân biệt các khái niệm:

| Thành phần | Vai trò |
|---|---|
| Group Replication | Giao thức nhóm giúp các thành viên trao đổi transaction, sắp thứ tự và kiểm tra khả năng commit. |
| Single-primary | Một thành viên là primary nhận ghi; các thành viên còn lại hoạt động như secondary và thường chỉ phục vụ đọc. |
| Multi-primary | Tất cả thành viên đủ điều kiện có thể nhận ghi; transaction được chứng nhận trên toàn nhóm. |
| InnoDB Cluster | Giải pháp quản trị cụm dựa trên Group Replication, tích hợp AdminAPI và thường dùng MySQL Router. |
| MySQL Router | Điểm kết nối cho ứng dụng; có thể định tuyến tới primary hoặc các thành viên đọc theo metadata của cụm. |

Group Replication duy trì các bản sao của cùng một database trên các thành viên. Đây không phải sharding: mỗi node không chỉ giữ một phân vùng dữ liệu riêng. Nếu cần chia dữ liệu theo tenant hoặc vùng địa lý, đó là bài toán phân vùng/sharding ở một lớp kiến trúc khác.

Replication của Group Replication thường được mô tả là *virtually synchronous*: transaction được trao đổi và chứng nhận qua nhóm trước khi commit được xác nhận theo chính sách consistency, trong khi việc áp dụng thay đổi trên các thành viên khác có thể diễn ra sau đó. Không nên diễn giải điều này thành mọi node luôn đọc được cùng một trạng thái ngay tại mọi thời điểm. Hành vi đọc sau ghi còn phụ thuộc consistency setting, routing và trạng thái của thành viên.

## 2. Cơ chế chung: write set và certification

Group Replication dùng cơ chế tối ưu theo hướng lạc quan. Transaction chạy trên thành viên nhận request; khi đến giai đoạn commit, write set của transaction được trao đổi với nhóm và kiểm tra xung đột theo thứ tự toàn cục.

Write set mô tả những hàng mà transaction đã thay đổi, dựa trên thông tin khóa của hàng. Các thành viên kiểm tra xem transaction có xung đột với transaction khác đã được chứng nhận hay không. Nếu không xung đột, transaction có thể commit và được áp dụng trên các thành viên còn lại. Nếu xung đột, transaction bị từ chối ở giai đoạn certification và client cần xử lý lỗi.

Ví dụ hai ứng dụng gửi lệnh tới hai primary khác nhau trong multi-primary:

~~~sql
-- Transaction A trên node 1
START TRANSACTION;
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
COMMIT;

-- Transaction B trên node 2, cùng thời điểm
START TRANSACTION;
UPDATE inventory
SET available = available - 2
WHERE product_id = 42;
COMMIT;
~~~

Cả hai transaction có thể chạy cục bộ trong thời gian đầu. Khi write set được chứng nhận, chúng cùng tác động đến một hàng có khóa `product_id = 42`. Nhóm chỉ có thể chấp nhận một thứ tự tương thích; transaction còn lại có thể bị rollback do certification conflict. Ứng dụng phải nhận biết lỗi, đọc lại trạng thái và quyết định có retry hay không.

Điểm quan trọng:

- Certification không biến các thao tác ghi đồng thời trên cùng hàng thành một phép cộng tự động.
- Một transaction bị rollback do conflict không được xem là đã commit một phần.
- Client phải xử lý lỗi commit và retry toàn bộ transaction khi nghiệp vụ cho phép.
- Retry cần giới hạn số lần, có backoff và bảo đảm thao tác nghiệp vụ có thể lặp lại an toàn.
- Các thành viên phải có schema và cấu hình tương thích để cùng diễn giải write set.

Primary key ổn định giúp nhận diện hàng và phát hiện xung đột hiệu quả. Nên thiết kế bảng InnoDB với primary key rõ ràng; tránh dựa vào hàng không có khóa duy nhất khi workload cần replication và xử lý xung đột đáng tin cậy.

## 3. Single-primary: một đầu mối nhận ghi

Trong chế độ single-primary, một thành viên được bầu làm primary. Ứng dụng gửi các thao tác ghi đến primary; secondary nhận và áp dụng transaction từ nhóm, thường được cấu hình chỉ đọc đối với ứng dụng.

Luồng tổng quát:

~~~text
                 Ứng dụng
                     |
               MySQL Router
                     |
              Primary hiện tại
                /    |    \
               /     |     \
        Secondary  Secondary  Secondary
           đọc       đọc        đọc
~~~

Các đặc điểm:

- Chỉ primary nhận transaction ghi thông thường.
- Secondary có thể phục vụ truy vấn đọc nếu routing và consistency policy cho phép.
- Group Replication duy trì trạng thái transaction trên các thành viên.
- Khi primary lỗi hoặc rời nhóm, các thành viên còn lại có thể bầu primary mới nếu nhóm vẫn có quorum và đủ điều kiện hoạt động.
- Ứng dụng cần kết nối lại hoặc được Router định tuyến tới primary mới sau failover.

### 3.1. Ưu điểm

Single-primary tạo một điểm điều phối ghi rõ ràng. Những transaction cùng cập nhật một hàng thường được xử lý tại một primary, nhờ đó giảm tình huống hai node đồng thời chạy transaction cạnh tranh trên cùng dữ liệu.

Mô hình này phù hợp với nhiều ứng dụng OLTP có quan hệ dữ liệu phức tạp, nhiều khóa ngoại, transaction cập nhật nhiều bảng và logic nghiệp vụ cần một luồng ghi dễ dự đoán. Các replica có thể được dùng để mở rộng một phần workload đọc, tùy consistency requirement và độ trễ apply.

Vận hành cũng dễ hiểu hơn: xác định primary hiện tại, theo dõi tải ghi ở primary, kiểm tra replica lag và để Router chuyển kết nối ghi khi vai trò primary thay đổi.

### 3.2. Giới hạn

Primary là nơi tập trung ghi nên có thể trở thành giới hạn thông lượng. Thêm secondary không tự động tăng năng lực ghi vì các transaction vẫn phải được chứng nhận và áp dụng trên nhóm.

Secondary có thể trễ so với primary ở thời điểm truy vấn. Nếu ứng dụng vừa ghi rồi đọc ngay từ một secondary, kết quả có thể chưa phản ánh transaction vừa commit, trừ khi dùng cơ chế đảm bảo read-after-write phù hợp.

Khi primary failover, có một khoảng thời gian chuyển vai trò và kết nối. Cụm cần quorum để tiếp tục; Router chỉ hỗ trợ định tuyến, không thể tự khôi phục một nhóm đã mất quorum hoặc sửa dữ liệu không nhất quán.

## 4. Multi-primary: nhiều thành viên nhận ghi

Trong chế độ multi-primary, tất cả thành viên đủ điều kiện có thể nhận transaction ghi. Mỗi node vừa có thể nhận lệnh ghi từ ứng dụng, vừa trao đổi và áp dụng transaction từ các thành viên khác.

~~~text
                 Ứng dụng
                     |
          Router / bộ định tuyến ứng dụng
               /            \
              /              \
          Node 1  <------>  Node 2
             ^    Group       ^
             |  Replication   |
             v                v
          Node 3  <------>  Node 4

      Các node có thể nhận ghi; transaction
      vẫn phải qua certification của nhóm.
~~~

Điều này có thể hữu ích khi ứng dụng phân bố ở nhiều vùng mạng và cần ghi vào node gần nơi phát sinh request. Tuy nhiên, việc ghi ở nhiều node chỉ có lợi khi workload ít xung đột và cách phân công dữ liệu đủ rõ ràng.

### 4.1. Ưu điểm

- Có nhiều điểm tiếp nhận ghi, có thể giảm đường truyền từ ứng dụng đến node nhận request.
- Có thể phân bố workload ghi theo tenant, vùng hoặc loại giao dịch nếu dữ liệu và nghiệp vụ được thiết kế phù hợp.
- Khi một thành viên gặp sự cố, các thành viên còn lại vẫn có thể nhận ghi nếu nhóm còn quorum và ứng dụng định tuyến lại thành công.
- Có thể tránh tập trung toàn bộ kết nối ghi vào một máy duy nhất trong một số topology phân tán.

### 4.2. Giới hạn

Multi-primary không phải cách đơn giản để nhân thông lượng ghi. Mỗi transaction vẫn cần trao đổi write set, đi qua certification và được áp dụng trên các thành viên. Khi nhiều node ghi vào cùng dữ liệu, xung đột và retry có thể làm giảm throughput thay vì tăng nó.

Nếu ứng dụng không kiểm soát node nhận ghi, cùng một tenant hoặc cùng một hàng có thể bị cập nhật từ nhiều nơi. Mạng WAN có độ trễ cao cũng làm tăng thời gian trao đổi và xác nhận transaction.

Các giao dịch nhiều hàng, nhiều bảng hoặc nhiều bước nghiệp vụ có thể đụng đến cùng tập khóa từ những node khác nhau. Khi đó, tỷ lệ certification conflict tăng và ứng dụng phải xử lý nhiều lần thử lại hơn.

## 5. So sánh single-primary và multi-primary

| Tiêu chí | Single-primary | Multi-primary |
|---|---|---|
| Node nhận ghi | Một primary tại một thời điểm | Nhiều thành viên |
| Điều phối ghi | Tập trung tại primary | Phân tán qua các node |
| Xung đột cùng hàng | Thường được tuần tự hóa tại primary | Có thể bị phát hiện khi certification và rollback |
| Định tuyến ứng dụng | Ghi tới primary, đọc có thể tới secondary | Ghi có thể tới nhiều node |
| Mở rộng ghi | Bị giới hạn bởi primary và chi phí replication | Không tuyến tính; phụ thuộc mức xung đột và overhead nhóm |
| Workload phù hợp | OLTP có transaction phức tạp, nhiều điểm tranh chấp | Workload ít xung đột, có thể phân công ghi theo tenant/vùng |
| Vận hành | Dễ xác định nơi nhận ghi | Phức tạp hơn về định tuyến, retry và phân tích conflict |
| Failover | Cần bầu primary mới | Cần duy trì quorum và định tuyến tới thành viên còn hoạt động |
| Rủi ro chính | Primary quá tải hoặc failover | Conflict, retry, độ trễ liên node và thiết kế ghi thiếu phân tách |

Chọn single-primary làm mặc định cho phần lớn ứng dụng giao dịch nếu chưa có bằng chứng rằng multi-primary giải quyết một vấn đề thực tế. Chỉ chuyển sang multi-primary sau khi đo workload, phân tích write conflict và thử nghiệm client routing.

## 6. Những giới hạn cần đánh giá trong multi-primary

### 6.1. Ghi đồng thời trên cùng hàng

Đây là giới hạn quan trọng nhất. Nếu hai node cập nhật cùng một hàng trong các transaction chồng lấn, certification có thể từ chối một transaction. Tỷ lệ xung đột cao dẫn đến rollback, retry và giảm throughput hữu ích.

Các bảng có hàng “nóng” như số dư tài khoản, tồn kho của sản phẩm bán chạy, bộ đếm toàn cục hoặc trạng thái đơn hàng thường dễ trở thành điểm tranh chấp. Việc gửi cùng một workload tới mọi node có thể làm tình hình xấu hơn.

### 6.2. Thiết kế khóa và phạm vi transaction

Write set dựa trên các khóa hàng. Bảng nên có primary key duy nhất, ổn định; transaction nên cập nhật phạm vi hàng cần thiết và giữ thời gian mở transaction ngắn.

Ví dụ, thay vì một transaction cập nhật hàng loạt hàng nóng từ nhiều node, có thể phân công mỗi tenant hoặc nhóm key về một node nhận ghi chính. Đây là quy ước routing ở tầng ứng dụng, không phải sharding tự động: dữ liệu vẫn được replication tới các thành viên khác.

Tránh dùng bộ đếm toàn cục làm điểm ghi chung nếu có thể tạo bộ đếm theo tenant hoặc theo phân vùng nghiệp vụ. Nếu cần số thứ tự toàn cục, phải thiết kế cơ chế cấp số phù hợp và hiểu rằng nó có thể trở thành điểm điều phối.

### 6.3. Khóa cục bộ và thao tác điều phối

Không nên giả định một khóa được giữ trên node này sẽ khóa cùng tài nguyên trên mọi node. Các cơ chế khóa cục bộ, named lock hoặc table lock không thay thế được cơ chế đồng thuận của Group Replication. Kiểm tra tài liệu phiên bản để biết các câu lệnh khóa, isolation level và tính năng nào được hỗ trợ trong multi-primary.

Với nghiệp vụ cần tuần tự hóa, ưu tiên thiết kế transaction và định tuyến để cùng một đối tượng được xử lý qua một node có trách nhiệm rõ ràng. Không dùng `GET_LOCK()` hoặc một khóa trong bộ nhớ của ứng dụng như thể nó là distributed lock toàn cụm nếu chưa có hệ thống điều phối phù hợp.

### 6.4. Foreign key và cascading action

Multi-primary có giới hạn với các bảng sử dụng foreign key có hành động cascading như `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE`. Các thao tác cascade có thể tạo thay đổi ở nhiều hàng mà không được biểu diễn theo cách phù hợp với cơ chế phát hiện xung đột của multi-primary.

Nếu schema dựa nhiều vào cascading foreign key, hãy giữ single-primary hoặc thiết kế lại thao tác nghiệp vụ để thực hiện thay đổi tường minh và kiểm thử theo tài liệu Group Replication của đúng phiên bản. Không xóa bỏ ràng buộc dữ liệu chỉ để ép hệ thống chạy multi-primary.

### 6.5. DDL và thay đổi schema

DDL là thay đổi cấu trúc, không giống transaction DML thông thường. Khi nhiều ứng dụng cùng ghi và migration chạy đồng thời, việc thay đổi schema có thể gây lỗi tương thích giữa câu lệnh ứng dụng, transaction đang chạy và trạng thái các thành viên.

Quy trình an toàn nên có một luồng migration được điều phối, tương thích ngược trong thời gian triển khai và kiểm tra trạng thái cụm trước/sau khi thay đổi. Không để từng node tự chạy migration độc lập.

### 6.6. Retry phải đúng nghiệp vụ

Certification conflict có thể khiến transaction bị rollback. Ứng dụng cần nhận diện lỗi có thể retry, bắt đầu transaction mới, đọc lại trạng thái và chạy lại toàn bộ nghiệp vụ trong giới hạn cho phép.

Không retry mù quáng các thao tác không idempotent. Ví dụ, nếu một request đã gửi email hoặc gọi cổng thanh toán bên ngoài trước khi transaction bị rollback, chạy lại toàn bộ hàm có thể gửi email hoặc thu tiền hai lần. Dùng idempotency key, transactional outbox hoặc cơ chế phối hợp tương đương để kiểm soát side effect.

## 7. Workload nào phù hợp với từng mô hình?

### 7.1. Nên bắt đầu với single-primary khi

- Nhiều giao dịch cùng cập nhật một nhóm bảng hoặc một số hàng nóng.
- Transaction cập nhật nhiều bảng có foreign key.
- Nghiệp vụ cần tuần tự hóa rõ ràng, ví dụ đặt chỗ, trừ tồn kho hoặc cập nhật số dư.
- Ứng dụng có thể định tuyến ghi tới một endpoint ổn định.
- Đội vận hành muốn giảm độ phức tạp của retry và conflict.

### 7.2. Có thể đánh giá multi-primary khi

- Ứng dụng phân bố địa lý và độ trễ tới một primary trung tâm là vấn đề đáng kể.
- Workload có thể phân tách tự nhiên theo tenant hoặc nhóm khóa.
- Xung đột ghi giữa các node thấp và được đo bằng thử nghiệm thực tế.
- Client có khả năng định tuyến ghi nhất quán và retry transaction an toàn.
- Schema và các thao tác SQL tương thích với giới hạn multi-primary của phiên bản.
- Đội vận hành có khả năng theo dõi certification conflict, rollback, network latency và quorum.

Multi-primary không phù hợp chỉ vì số lượng người dùng tăng. Nếu mọi node cùng ghi vào một bảng tồn kho với các khóa nóng giống nhau, thêm node nhận ghi có thể tăng số lần tranh chấp mà không tăng lượng công việc hoàn thành.

## 8. Định tuyến ghi và đọc

Trong single-primary, ứng dụng nên dùng endpoint ghi do MySQL Router cung cấp hoặc một cơ chế service discovery tương đương. Router đọc metadata của InnoDB Cluster và chuyển kết nối tới primary hiện tại. Kết nối đọc có thể được định tuyến tới secondary nếu ứng dụng chấp nhận độ trễ và consistency policy phù hợp.

Trong multi-primary, ứng dụng có thể kết nối tới nhiều thành viên để ghi. Tuy nhiên, routing nên có chủ đích:

- Gắn tenant hoặc nhóm dữ liệu với một node ưu tiên để giảm tranh chấp.
- Duy trì affinity trong một luồng nghiệp vụ nếu cần đọc/ghi liên tiếp.
- Không để request liên quan cùng một đối tượng luân phiên ngẫu nhiên qua nhiều node.
- Khi node rời nhóm, chuyển request sang thành viên còn hoạt động và xử lý lỗi transaction đang chạy.
- Theo dõi latency giữa ứng dụng và từng node, không chỉ số kết nối.

Một chiến lược đơn giản là định tuyến theo hash của tenant ID để cùng tenant thường tới cùng node nhận ghi. Đây là chính sách routing của ứng dụng hoặc proxy; nó không thay đổi việc mỗi thành viên vẫn lưu cùng dữ liệu và vẫn phải replication transaction.

### 8.1. Read-after-write

Sau khi một request ghi thành công trên primary, request đọc tiếp theo nếu đi tới secondary có thể thấy trạng thái cũ trong một khoảng thời gian. Có thể giữ cùng session/định tuyến đọc về primary, hoặc sử dụng consistency setting phù hợp của Group Replication khi cần chờ transaction được áp dụng.

Trong multi-primary, cùng vấn đề cũng xuất hiện nếu một client ghi ở node A rồi lập tức đọc từ node B. Không giả định mọi node đã apply transaction ngay khi client nhận phản hồi commit. Kiểm thử yêu cầu read-after-write của ứng dụng với cấu hình consistency đang dùng.

## 9. Quorum, membership và failover

Group Replication cần đa số thành viên đang hoạt động để duy trì nhóm. Với ba thành viên, cần ít nhất hai thành viên có thể giao tiếp để có quorum. Nếu mất đa số, nhóm có thể ngừng nhận ghi nhằm tránh hai phân vùng mạng cùng hoạt động độc lập và tạo trạng thái không nhất quán.

Quorum là điều kiện của nhóm, không phải lựa chọn single-primary hay multi-primary. Cả hai mô hình đều cần membership và quorum phù hợp.

Các nguyên tắc vận hành:

- Dùng số thành viên phù hợp với failure domain; ba thành viên ở các host hoặc zone độc lập thường dễ chịu một lỗi đơn lẻ hơn ba instance cùng một máy.
- Bảo đảm mạng giữa các thành viên ổn định, độ trễ và packet loss nằm trong ngưỡng thiết kế.
- Theo dõi trạng thái ONLINE, RECOVERING, ERROR và các thành viên bị loại khỏi nhóm.
- Có kế hoạch khôi phục quorum khi nhiều thành viên cùng lỗi; không ép một phân vùng mạng tự hoạt động nếu chưa xác định trạng thái dữ liệu.
- Diễn tập primary failover, member restart, network partition và phục hồi sau khi node mất kết nối.

Trong single-primary, khi primary lỗi, nhóm còn lại bầu primary mới. Trong multi-primary, các thành viên còn lại có thể tiếp tục nhận ghi nếu nhóm còn quorum, nhưng ứng dụng vẫn phải định tuyến khỏi node đã lỗi và xử lý transaction chưa rõ kết quả tại thời điểm mất kết nối.

## 10. Chuyển đổi chế độ bằng MySQL Shell AdminAPI

Với InnoDB Cluster, MySQL Shell AdminAPI cung cấp phương thức chuyển đổi chế độ. Trước khi chạy, xác nhận phiên bản hỗ trợ, tất cả thành viên khỏe mạnh, cấu hình tương thích, không có transaction hoặc migration quan trọng đang diễn ra và ứng dụng đã sẵn sàng với mô hình đích.

Kết nối MySQL Shell bằng tài khoản quản trị cụm, sau đó lấy đối tượng cluster:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

Chuyển sang single-primary:

~~~javascript
cluster.switchToSinglePrimaryMode();
cluster.status({extended: 1});
~~~

Chuyển sang multi-primary:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.status({extended: 1});
~~~

Các lệnh trên là ví dụ thao tác AdminAPI, không phải lệnh SQL chạy trong mysql client. Thực hiện trong cửa sổ thay đổi có kiểm soát. Nếu chuyển sang single-primary và cần chọn một instance làm primary, dùng tham số instance theo cú pháp AdminAPI của phiên bản đang chạy.

Sau khi chuyển chế độ:

1. Xác nhận trạng thái cluster và vai trò các member.
2. Kiểm tra `read_only`/`super_read_only` theo vai trò và trạng thái node.
3. Xác nhận Router metadata và endpoint ứng dụng định tuyến đúng.
4. Chạy smoke test đọc/ghi bằng tài khoản ứng dụng.
5. Kiểm tra lỗi replication, certification conflict và latency.
6. Theo dõi tải trong giai đoạn sau chuyển đổi.

Không đổi mode chỉ để thử trên cụm production đang có tải. Hãy diễn tập trên môi trường staging với dữ liệu và phiên bản tương thích.

## 11. Quan sát và chẩn đoán

Một số bảng performance schema và lệnh quản trị giúp quan sát Group Replication:

~~~sql
-- Thành viên và trạng thái trong nhóm
SELECT *
FROM performance_schema.replication_group_members;

-- Cấu hình Group Replication cơ bản
SHOW VARIABLES LIKE 'group_replication%';

-- Trạng thái replica
SHOW REPLICA STATUS\G
~~~

Bảng `performance_schema.replication_group_members` cho biết member ID, host, port, trạng thái và role của từng thành viên theo phiên bản. Các cột có thể khác nhau theo bản MySQL.

Trong MySQL Shell:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

Khi điều tra multi-primary, theo dõi:

- Số transaction bị rollback do certification conflict.
- Tốc độ commit và latency theo từng node.
- Thời gian transaction mở và kích thước write set.
- Tải CPU, I/O và network giữa các thành viên.
- Trạng thái membership, quorum và recovery.
- Lỗi ở client khi retry, timeout hoặc mất kết nối.
- Chênh lệch giữa workload ghi theo tenant/node.

Khi điều tra single-primary, bổ sung:

- Tải CPU, I/O, connection và lock wait của primary.
- Replica apply lag và khả năng phục vụ đọc.
- Thời gian phát hiện lỗi, bầu primary mới và khôi phục routing.
- Tỷ lệ request ghi thất bại trong cửa sổ failover.

Đừng chỉ đo số lệnh SQL mỗi giây. Hãy đo transaction commit thành công, tỷ lệ rollback, latency p95/p99 và lượng retry; đó mới là các chỉ số phản ánh năng lực xử lý hữu ích.

## 12. Ví dụ thiết kế cho hệ thống bán hàng

Giả sử ứng dụng có các nhóm nghiệp vụ:

- Tra cứu sản phẩm và danh mục.
- Tạo đơn hàng và cập nhật trạng thái.
- Trừ tồn kho và ghi nhận thanh toán.
- Báo cáo doanh thu.

Các bảng `orders`, `order_items`, `inventory` và `payments` liên kết bằng khóa ngoại. Nhiều request có thể đồng thời mua cùng một sản phẩm, khiến hàng tồn kho trở thành điểm nóng.

Single-primary thường là lựa chọn khởi đầu hợp lý:

- Ghi đơn hàng, tồn kho và thanh toán đi qua primary.
- Secondary phục vụ truy vấn báo cáo nếu độ trễ đọc chấp nhận được.
- Transaction nghiệp vụ giữ các thay đổi liên quan trong một transaction InnoDB.
- Router định tuyến kết nối ghi tới primary hiện tại.

Nếu muốn đánh giá multi-primary, cần phân tích trước:

1. Có thể phân công tenant hoặc vùng dữ liệu để giảm ghi trùng không?
2. Sản phẩm phổ biến có trở thành hot row trên mọi node không?
3. Transaction cập nhật tồn kho và đơn hàng có chạm cùng khóa từ nhiều node không?
4. Các thao tác khóa và foreign key có tương thích với giới hạn multi-primary không?
5. Client có thể retry toàn bộ transaction mà không lặp thanh toán hoặc side effect không?
6. Độ trễ mạng giữa các vùng có làm tăng thời gian certification không?

Nếu không thể giảm xung đột hoặc xử lý retry an toàn, multi-primary sẽ tăng độ phức tạp mà không mang lại lợi ích tương xứng.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn multi-primary chỉ vì có nhiều node | Kỳ vọng sai về khả năng mở rộng ghi | Đo transaction commit, conflict và latency trước khi chọn mode. |
| Định tuyến cùng tenant tới nhiều node ngẫu nhiên | Tăng xung đột trên các hàng nóng | Dùng routing affinity theo tenant hoặc nhóm khóa. |
| Không có primary key ổn định | Khó nhận diện hàng và xử lý conflict hiệu quả | Thiết kế primary key duy nhất cho bảng nghiệp vụ. |
| Retry toàn bộ request mà không có idempotency | Side effect bên ngoài có thể xảy ra hai lần | Dùng idempotency key, outbox và retry có giới hạn. |
| Dùng khóa cục bộ như distributed lock | Node khác không bị điều phối như mong đợi | Dùng cơ chế điều phối phân tán phù hợp hoặc single-primary cho nghiệp vụ cần tuần tự hóa. |
| Giữ cascading foreign key trong workload multi-primary mà không kiểm tra | Có thể vi phạm giới hạn hỗ trợ của Group Replication | Kiểm tra schema và giới hạn phiên bản; giữ single-primary nếu cần cascade. |
| Đọc ngay từ secondary sau khi ghi | Kết quả có thể cũ | Dùng read-after-write routing hoặc consistency setting phù hợp. |
| Chỉ kiểm tra Router khi failover | Nhầm routing hoạt động với cluster khỏe mạnh | Kiểm tra cả quorum, member state, applier và dữ liệu. |
| Chuyển mode khi migration đang chạy | Tăng nguy cơ lỗi thay đổi schema và client | Điều phối migration, kiểm tra cluster và chuyển mode trong cửa sổ thay đổi. |

## 14. Bài tập thực hành

### Bài 1: Chọn mô hình cho workload

Một ứng dụng có 80% thao tác đọc, 20% thao tác ghi. Các thao tác ghi tập trung vào 20 sản phẩm bán chạy và cập nhật cùng bảng tồn kho. Hãy chọn single-primary hoặc multi-primary, giải thích rủi ro và xác định node nào nên nhận ghi.

### Bài 2: Phân tích certification conflict

Dùng hai session kết nối tới hai member trong môi trường multi-primary thử nghiệm. Cùng cập nhật một hàng bằng hai transaction chồng lấn. Quan sát transaction nào commit, transaction nào bị rollback và thông báo lỗi client. Lặp lại với hai hàng độc lập để so sánh.

### Bài 3: Thiết kế routing theo tenant

Giả sử có 12 tenant và 3 member nhận ghi. Đề xuất một quy tắc định tuyến để mỗi tenant thường tới cùng member. Nêu cách chuyển tenant sang member khác khi node lỗi và cách xử lý transaction đang chạy lúc chuyển.

### Bài 4: Diễn tập chuyển mode

Trên InnoDB Cluster thử nghiệm:

1. Kiểm tra trạng thái và phiên bản các member.
2. Chuyển từ single-primary sang multi-primary bằng AdminAPI.
3. Kiểm tra vai trò và trạng thái cluster.
4. Chạy transaction ghi trên hai member và quan sát kết quả.
5. Chuyển lại single-primary.
6. Kiểm tra Router và ứng dụng sau mỗi lần chuyển.

Ghi lại thời gian chuyển đổi, lỗi client và các chỉ số transaction commit/rollback.

### Bài 5: Đánh giá retry an toàn

Một transaction vừa cập nhật đơn hàng vừa gọi dịch vụ thanh toán bên ngoài. Nếu commit bị từ chối do conflict, giải thích vì sao retry cả hàm có thể gây thu tiền hai lần. Đề xuất idempotency key hoặc transactional outbox để tách side effect khỏi lần thử transaction.

## 15. Checklist trước khi đưa mô hình ghi vào production

- [ ] Đã xác định rõ Group Replication single-primary hay multi-primary.
- [ ] Đã đo tỷ lệ đọc/ghi, hot row, kích thước transaction và latency.
- [ ] Các bảng nghiệp vụ có primary key ổn định.
- [ ] Đã kiểm tra foreign key, cascading action và các thao tác khóa theo giới hạn phiên bản.
- [ ] Ứng dụng nhận biết lỗi certification và retry toàn bộ transaction có giới hạn.
- [ ] Side effect ngoài database có idempotency hoặc cơ chế outbox phù hợp.
- [ ] Routing ghi/đọc phù hợp với mode và yêu cầu read-after-write.
- [ ] Router metadata và endpoint ứng dụng đã được kiểm thử.
- [ ] Quorum và failure domain đã được thiết kế, giám sát.
- [ ] Đã diễn tập member failure, primary failover, network partition và recovery.
- [ ] Có dashboard cho commit latency, conflict, rollback, retry và replication health.
- [ ] Có quy trình migration DDL và chuyển mode được điều phối.
- [ ] Có runbook xử lý khi cluster mất quorum hoặc một member không thể gia nhập lại.

Single-primary tạo một luồng ghi dễ kiểm soát và thường phù hợp với ứng dụng OLTP có nhiều điểm tranh chấp. Multi-primary mở thêm điểm tiếp nhận ghi, nhưng mọi transaction vẫn phải qua certification và replication; lợi ích chỉ xuất hiện khi workload có thể phân tán mà ít xung đột. Hãy chọn mode dựa trên dữ liệu đo được, thiết kế routing và retry ngay từ đầu, rồi xác minh bằng diễn tập failover trong môi trường tương thích.

