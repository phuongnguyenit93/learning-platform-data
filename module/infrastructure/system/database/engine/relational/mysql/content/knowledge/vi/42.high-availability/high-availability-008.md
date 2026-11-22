# InnoDB Cluster, MySQL Shell AdminAPI và ranh giới với Group Replication

InnoDB Cluster là giải pháp MySQL để xây dựng cụm cơ sở dữ liệu có tính sẵn sàng cao. Nó kết hợp Group Replication để đồng bộ transaction giữa các thành viên, MySQL Shell AdminAPI để tạo và quản trị cụm, cùng MySQL Router để định tuyến kết nối ứng dụng. Group Replication là lớp giao tiếp và đồng thuận dữ liệu; AdminAPI là lớp quản trị vòng đời; Router là lớp kết nối client. Hiểu rõ ba vai trò này giúp thiết kế cụm đúng, xử lý lỗi có kiểm soát và tránh kỳ vọng sai về khả năng bảo vệ dữ liệu.

Bài học này thuộc chương **Sẵn sàng cao** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và sao lưu, InnoDB Cluster giúp duy trì dịch vụ khi một thành viên gặp sự cố. Cụm HA vẫn cần backup, PITR, giám sát và kế hoạch phục hồi thảm họa riêng.

## 1. InnoDB Cluster gồm những thành phần nào?

Một InnoDB Cluster tiêu chuẩn gồm ba thành phần:

- **Group Replication:** plugin MySQL điều phối nhóm thành viên, trao đổi transaction, kiểm tra xung đột và giữ trạng thái nhóm nhất quán.
- **MySQL Shell AdminAPI:** bộ API quản trị để kiểm tra cấu hình instance, tạo cụm, thêm hoặc loại thành viên, theo dõi topology và thay đổi primary.
- **MySQL Router:** proxy nhận kết nối ứng dụng và định tuyến tới thành viên phù hợp dựa trên metadata của cụm.

Mô hình tổng quát:

~~~text
                  Ứng dụng
                     |
                     v
               MySQL Router
                /        \
         read/write      read-only
              |              |
              v              v
         Primary node    Secondary nodes
              \              /
               \            /
                Group Replication
             (membership + certification)

        MySQL Shell AdminAPI
           |      |      |
           +------ quản trị ------+
             các thành viên cụm
~~~

Trong chế độ single-primary, một thành viên là primary nhận ghi; các thành viên còn lại là secondary và thường phục vụ đọc. Router cung cấp endpoint để ứng dụng không cần tự theo dõi tên primary sau mỗi lần failover.

AdminAPI không phải replication engine. Khi gọi `dba.createCluster()`, Shell cấu hình Group Replication và ghi metadata quản trị của InnoDB Cluster. Sau khi cụm hoạt động, các transaction vẫn được trao đổi và áp dụng bởi Group Replication. Router cũng không tham gia đồng thuận transaction; nó chỉ định tuyến kết nối.

## 2. Group Replication hoạt động ra sao?

Group Replication là cơ chế replication theo nhóm. Các thành viên trao đổi thông tin transaction qua group communication, kiểm tra xung đột và phối hợp thứ tự áp dụng. Transaction được kiểm tra bằng cơ chế certification trước khi được chấp nhận vào nhóm. Nếu hai transaction đồng thời sửa cùng dữ liệu theo cách xung đột, một transaction có thể bị từ chối và ứng dụng cần xử lý retry.

Group Replication cung cấp mô hình **virtually synchronous replication**: thành viên phối hợp qua giao thức nhóm trước khi transaction được xác nhận theo chính sách commit. Điều này giảm khả năng một thành viên tự ý chấp nhận thay đổi không được nhóm thống nhất. Tuy nhiên, không nên hiểu điều đó là mọi transaction đã được ghi bền vững trên đĩa của tất cả replica trước khi client nhận phản hồi. Độ bền còn phụ thuộc cấu hình durability, storage và trạng thái từng thành viên.

Các đặc điểm chính:

- Mỗi thành viên có một `server_id` duy nhất và cấu hình replication phù hợp.
- Transaction được ghi vào binary log; Group Replication dùng GTID để định danh transaction.
- Các thành viên duy trì membership và trao đổi trạng thái nhóm.
- Transaction xung đột có thể bị certification failure; ứng dụng phải có chiến lược retry an toàn.
- Thành viên có thể rời nhóm, mất kết nối hoặc tham gia lại thông qua distributed recovery.

Group Replication không phải cơ chế khóa bảng toàn cục. Nó dùng certification và group communication để phối hợp transaction giữa các thành viên. Vì vậy, ứng dụng vẫn phải thiết kế transaction ngắn, khóa chính rõ ràng và xử lý lỗi commit/retry đúng cách.

## 3. Single-primary và multi-primary

### Single-primary

Single-primary là chế độ mặc định và thường là lựa chọn phù hợp cho phần lớn ứng dụng. Chỉ primary nhận transaction ghi; secondary giữ bản sao và có thể phục vụ truy vấn đọc tùy chính sách routing.

Ưu điểm:

- Luồng ghi tập trung, dễ dự đoán hơn.
- Ít xung đột ghi giữa các thành viên.
- Dễ tích hợp với ứng dụng vốn giả định một database endpoint ghi.
- Khi primary lỗi, nhóm có thể bầu một primary mới nếu còn quorum.

Ví dụ tạo cụm ở chế độ mặc định:

~~~javascript
var cluster = dba.createCluster("ordersCluster");
~~~

Khi primary gặp lỗi, Group Replication lựa chọn primary mới trong nhóm theo cơ chế bầu chọn. Ứng dụng kết nối qua Router có thể tiếp tục dùng endpoint ghi sau khi Router nhận biết topology mới và các kết nối được thiết lập lại.

### Multi-primary

Multi-primary cho phép nhiều thành viên nhận ghi. Mỗi transaction vẫn phải qua certification và phối hợp nhóm. Nếu hai client ghi cùng hàng ở các thành viên khác nhau, một transaction có thể bị từ chối do xung đột.

Có thể tạo cụm multi-primary trong MySQL Shell bằng tùy chọn:

~~~javascript
var cluster = dba.createCluster("ordersCluster", {
  multiPrimary: true
});
~~~

Hoặc chuyển chế độ qua API tương ứng khi phiên bản Shell hỗ trợ:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.switchToSinglePrimaryMode();
~~~

Multi-primary không tự động làm mọi ứng dụng ghi nhanh hơn. Nó phù hợp hơn khi workload có thể phân vùng dữ liệu hoặc phần lớn transaction ghi các hàng độc lập. Cần đánh giá các giới hạn liên quan đến foreign key, khóa unique, transaction nhiều hàng, thứ tự ghi và hành vi failover. Với ứng dụng có nhiều thao tác cập nhật cùng một thực thể, single-primary thường dễ vận hành hơn.

| Tiêu chí | Single-primary | Multi-primary |
|---|---|---|
| Thành viên nhận ghi | Một primary | Nhiều thành viên |
| Xung đột ghi | Ít hơn, tập trung tại primary | Có thể phát sinh giữa các primary |
| Failover | Chọn primary mới | Nhóm duy trì nhiều điểm nhận ghi nếu còn thành viên phù hợp |
| Ứng dụng | Đơn giản hơn | Cần xử lý retry và xung đột cẩn thận |
| Trường hợp phù hợp | Workload OLTP thông thường | Workload phân vùng tốt, ghi ít xung đột |

## 4. Quorum và khả năng chịu lỗi

Group Replication cần đa số thành viên đang hoạt động để duy trì quyết định của nhóm. Với nhóm có N thành viên, quorum thông thường là `Q = floor(N / 2) + 1`.

Ví dụ:

| Số thành viên | Quorum | Số thành viên có thể mất mà nhóm vẫn còn đa số |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |

Vì vậy, cụm ba thành viên phân bố trên ba máy chủ độc lập có thể chịu được một thành viên bị lỗi mà vẫn còn đa số. Cụm hai thành viên không thể tiếp tục hoạt động bình thường khi mất một thành viên, vì thành viên còn lại không đủ quorum. Thêm một arbitrator không phải là cách mặc định của Group Replication để thay thế một MySQL member; hãy thiết kế số thành viên và failure domain phù hợp.

Quorum bảo vệ tính nhất quán membership, không thay thế thiết kế dự phòng hạ tầng. Nếu cả ba thành viên nằm trên cùng một host vật lý, lỗi host vẫn có thể làm mất toàn bộ cụm. Cần phân bố thành viên theo host, rack, zone hoặc failure domain theo mục tiêu sẵn sàng.

Khi nhóm mất đa số, các thành viên còn lại có thể chuyển sang trạng thái không có quorum và ngừng nhận ghi. Không được tự ý ép một partition hoạt động nếu chưa xác minh các thành viên còn lại đã bị cô lập. Ép quorum sai cách có thể tạo split-brain hoặc hai nhánh dữ liệu cùng nhận ghi.

## 5. Điều kiện trước khi tạo InnoDB Cluster

Trước khi dùng AdminAPI, chuẩn bị các instance MySQL có phiên bản tương thích và đáp ứng điều kiện Group Replication. Các điểm cần kiểm tra gồm:

- Mỗi instance có `server_id` duy nhất.
- GTID được bật và cấu hình nhất quán; `enforce_gtid_consistency=ON`.
- Binary log được bật với định dạng phù hợp; Group Replication yêu cầu `binlog_format=ROW` và `log_replica_updates=ON`.
- Các bảng nghiệp vụ dùng InnoDB và có khóa chính hoặc khóa unique không nullable phù hợp. Thiết kế bảng không có khóa định danh duy nhất làm tăng rủi ro và bị hạn chế trong replication.
- Tài khoản quản trị cụm có quyền cần thiết để cấu hình replication, metadata và Group Replication.
- Các máy chủ phân giải được hostname, đồng bộ thời gian và kết nối được qua các cổng SQL cùng cổng group communication cần thiết.
- Phiên bản MySQL Shell, Server và Router tương thích với nhau.
- Các instance có trạng thái dữ liệu phù hợp trước khi tham gia cụm; tránh thêm một instance chứa dữ liệu khác biệt mà chưa chọn phương pháp recovery.

Các thiết lập như `binlog_format`, `gtid_mode`, `log_replica_updates`, `server_id` và các tham số Group Replication có thể được AdminAPI kiểm tra hoặc cấu hình tùy phiên bản. Không nên sao chép một file cấu hình mẫu rồi áp dụng nguyên trạng cho mọi bản MySQL. Dùng preflight của AdminAPI để biết instance còn thiếu gì.

## 6. Tạo cụm bằng MySQL Shell AdminAPI

MySQL Shell có thể chạy ở JavaScript hoặc Python mode. Các ví dụ dưới đây dùng JavaScript mode. Trước tiên, kết nối tới instance dự kiến làm seed:

~~~text
mysqlsh --uri icadmin@db1.example.internal:3306
~~~

Trong Shell, kiểm tra instance:

~~~javascript
dba.checkInstanceConfiguration("icadmin@db1.example.internal:3306");
~~~

Nếu instance chưa đáp ứng yêu cầu, cấu hình bằng AdminAPI:

~~~javascript
dba.configureInstance("icadmin@db1.example.internal:3306");
~~~

Lệnh có thể yêu cầu xác nhận hoặc thông tin quản trị. Sau khi cấu hình, khởi động lại MySQL nếu Shell thông báo cần restart, rồi kết nối lại và xác minh trạng thái.

Tạo cụm:

~~~javascript
var cluster = dba.createCluster("ordersCluster");
~~~

Thêm các instance đã được chuẩn bị:

~~~javascript
cluster.addInstance("icadmin@db2.example.internal:3306");
cluster.addInstance("icadmin@db3.example.internal:3306");
~~~

Khi thêm instance, AdminAPI cần đưa dữ liệu của instance mới về trạng thái tương thích với cụm. Có thể chọn phương pháp distributed recovery phù hợp, ví dụ incremental recovery hoặc clone:

~~~javascript
cluster.addInstance(
  "icadmin@db2.example.internal:3306",
  { recoveryMethod: "clone" }
);
~~~

Clone có thể sao chép dữ liệu từ donor sang instance mới và thay thế dữ liệu hiện có của recipient. Hãy kiểm tra kỹ instance đích trước khi chọn; không dùng clone trên một máy chủ đang chứa dữ liệu cần giữ. Incremental recovery dùng binary log để truyền các transaction còn thiếu, do đó donor phải còn giữ đủ log cần thiết.

## 7. Kiểm tra trạng thái và quản trị topology

Sau khi tạo cụm, kiểm tra topology:

~~~javascript
cluster.status();
cluster.status({ extended: 1 });
cluster.describe();
~~~

Các thông tin cần quan sát:

- Tên cụm và chế độ single-primary/multi-primary.
- Thành viên nào là primary, thành viên nào là secondary.
- Trạng thái member, ví dụ ONLINE, RECOVERING, UNREACHABLE hoặc ERROR.
- Transaction đã nhận và đã áp dụng.
- Tình trạng quorum và cảnh báo cấu hình.
- Độ trễ hoặc backlog của distributed recovery.

Trạng thái ONLINE cho biết member đang hoạt động trong nhóm tại thời điểm quan sát. Nó không chứng minh backup đã có hoặc dữ liệu đã được kiểm tra nghiệp vụ. Thành viên RECOVERING đang đồng bộ dữ liệu; không nên đưa nó vào luồng đọc quan trọng cho đến khi đã ONLINE.

Lấy đối tượng cluster khi mở một phiên Shell mới:

~~~javascript
var cluster = dba.getCluster("ordersCluster");
~~~

Nếu primary cần bảo trì hoặc đang gặp sự cố nhưng cụm vẫn còn quorum, có thể chủ động chuyển primary:

~~~javascript
cluster.setPrimaryInstance("db2.example.internal:3306");
~~~

Để đưa member đã rời nhóm trở lại, kiểm tra lý do lỗi trước rồi dùng phương thức phù hợp:

~~~javascript
cluster.rejoinInstance("icadmin@db3.example.internal:3306");
~~~

Nếu member không còn cần trong topology, loại bỏ có kiểm soát:

~~~javascript
cluster.removeInstance("db3.example.internal:3306");
~~~

Chỉ dùng `cluster.dissolve()` khi chủ đích là giải thể toàn bộ InnoDB Cluster. Đây là thao tác thay đổi topology lớn; kiểm tra ứng dụng, Router và kế hoạch chuyển đổi trước khi thực hiện.

## 8. MySQL Router và định tuyến ứng dụng

MySQL Router cung cấp endpoint ổn định cho client. Trong single-primary mode, Router có thể định tuyến kết nối ghi tới primary và kết nối đọc tới secondary theo routing strategy đã cấu hình. Khi primary đổi, Router đọc metadata cập nhật và chọn đích phù hợp cho kết nối mới.

Quy trình bootstrap Router thường kết nối tới một thành viên của InnoDB Cluster bằng tài khoản có quyền quản trị Router:

~~~bash
mysqlrouter --bootstrap icadmin@db1.example.internal:3306
~~~

Lệnh có thể yêu cầu mật khẩu và tạo cấu hình Router. Bảo vệ file cấu hình vì nó chứa thông tin kết nối và có thể chứa thông tin xác thực. Trong môi trường production, chạy Router dưới tài khoản hệ điều hành riêng và đặt cơ chế quản lý secret phù hợp.

Ứng dụng nên dùng endpoint Router thay vì kết nối trực tiếp tới một member cố định. Tuy vậy, cần hiểu một số điểm:

- Router không chuyển một transaction đang chạy dở từ node cũ sang node mới.
- Khi failover, kết nối hiện tại có thể bị ngắt; connection pool cần kết nối lại và ứng dụng cần retry transaction an toàn.
- Đường đọc có thể trả dữ liệu trễ hơn primary do replication apply chưa hoàn tất.
- Router cần truy cập được metadata và các node cần thiết; bản thân Router cũng cần được triển khai dự phòng.
- Không để ứng dụng ghi trực tiếp vào secondary trong single-primary mode.

Có thể triển khai nhiều Router ở các máy ứng dụng hoặc lớp proxy riêng để tránh biến một Router đơn lẻ thành điểm lỗi duy nhất.

## 9. Distributed recovery: incremental và clone

Khi một member mới tham gia hoặc quay lại sau khi offline, nó cần đồng bộ transaction còn thiếu.

**Incremental recovery** lấy transaction từ binary log của donor và áp dụng lên recipient. Cách này thường ít tốn băng thông hơn khi recipient chỉ thiếu một lượng transaction nhỏ. Donor cần còn giữ đầy đủ binlog từ GTID mà recipient còn thiếu.

**Clone recovery** sao chép trạng thái dữ liệu từ donor sang recipient bằng MySQL Clone Plugin. Nó phù hợp khi recipient thiếu quá nhiều transaction hoặc binlog cần thiết đã bị purge. Clone thay thế dữ liệu hiện tại trên recipient, vì vậy phải xác nhận đúng máy đích và có phương án giữ dữ liệu cũ nếu cần.

AdminAPI có thể tự chọn recovery method theo mặc định hoặc cho phép chỉ định:

~~~javascript
cluster.addInstance(
  "icadmin@db3.example.internal:3306",
  { recoveryMethod: "incremental" }
);
~~~

Nếu incremental recovery thất bại vì thiếu binlog, không xóa trạng thái hoặc reset replication một cách mù quáng. Kiểm tra GTID set, binlog retention, donor và dữ liệu recipient; sau đó quyết định clone hoặc dựng lại instance từ một bản backup phù hợp.

## 10. Xử lý sự cố và giới hạn phục hồi

### Mất một thành viên

Nếu cụm ba thành viên mất một member, hai member còn lại thường vẫn có quorum. Kiểm tra `cluster.status({extended: 1})`, log MySQL và kết nối mạng. Sửa nguyên nhân rồi gọi `rejoinInstance()` nếu member đủ điều kiện quay lại.

### Mất quorum

Nếu phần còn lại không có đa số, cụm có thể ngừng nhận transaction. Trước khi phục hồi quorum, xác định partition nào có dữ liệu mới nhất và cô lập các partition khác. AdminAPI có phương thức ép quorum từ một partition, nhưng chỉ sử dụng sau khi xác minh chắc chắn các thành viên bên ngoài partition đã bị dừng hoặc cô lập. Thao tác này có thể làm mất thay đổi ở partition bị bỏ lại và tạo split-brain nếu dùng sai.

Ví dụ API dành cho tình huống phục hồi có kiểm soát:

~~~javascript
cluster.forceQuorumUsingPartitionOf("db1.example.internal:3306");
~~~

Chỉ chạy lệnh sau khi đã xác minh member được chọn thuộc partition duy nhất được phép tiếp tục và các partition khác không thể tiếp tục nhận ghi. Ghi lại trạng thái trước thao tác và kiểm tra lại toàn bộ topology ngay sau khi quorum được thiết lập.

### Primary lỗi

Trong single-primary mode, nếu còn quorum, nhóm có thể bầu primary mới. Router cập nhật tuyến cho kết nối mới; ứng dụng phải xử lý connection reset và retry. Kiểm tra transaction có thể đã commit trên server nhưng client mất phản hồi; retry cần dùng idempotency key hoặc cơ chế chống ghi trùng.

### Certification failure

Nếu transaction bị từ chối do xung đột, đọc thông báo lỗi, xác định khóa/hàng xung đột và retry ở tầng ứng dụng khi phù hợp. Không lặp vô hạn một transaction chắc chắn sẽ xung đột. Thiết kế transaction ngắn, cập nhật tập hàng rõ ràng và tránh ghi đồng thời vào cùng thực thể sẽ giúp giảm lỗi.

## 11. Ranh giới giữa Group Replication và InnoDB Cluster

Group Replication là plugin có thể được cấu hình và vận hành trực tiếp mà không cần InnoDB Cluster. InnoDB Cluster dùng Group Replication làm nền và bổ sung metadata, AdminAPI cùng quy trình quản trị được chuẩn hóa.

| Thành phần/khả năng | Group Replication độc lập | InnoDB Cluster |
|---|---|---|
| Đồng bộ nhóm transaction | Có | Có, dùng Group Replication |
| Membership và certification | Có | Có |
| Quản trị bằng AdminAPI | Không phải điều kiện bắt buộc | Là cách quản trị chính |
| Metadata topology của InnoDB Cluster | Không tự có đầy đủ | Có |
| Tích hợp MySQL Router | Có thể tự cấu hình thủ công | Được hỗ trợ qua metadata và bootstrap |
| Quản lý vòng đời cụm | Người vận hành tự quản trị nhiều bước | AdminAPI cung cấp API chuẩn hóa |

Group Replication độc lập phù hợp khi tổ chức cần tự kiểm soát cấu hình và quy trình tích hợp. InnoDB Cluster phù hợp khi muốn dùng AdminAPI để giảm thao tác thủ công và kết hợp Router theo mô hình MySQL được hỗ trợ.

Cần phân biệt InnoDB Cluster với **InnoDB ClusterSet**. ClusterSet kết nối nhiều InnoDB Cluster để xây dựng mô hình disaster recovery giữa các cụm, thường có một cluster chính và các cluster dự phòng. Replication giữa các cluster là bất đồng bộ, vì vậy khi chuyển sang cluster dự phòng có thể mất những transaction chưa được truyền tới đó. Một InnoDB Cluster đơn lẻ không tự cung cấp khả năng phục hồi thảm họa xuyên vùng địa lý. Cũng không nên đặt các member của cùng một Group Replication group qua WAN có độ trễ cao nếu chưa đánh giá yêu cầu mạng và giới hạn topology.

## 12. HA không thay thế backup và kiểm soát dữ liệu

Group Replication giúp duy trì dịch vụ khi thành viên gặp sự cố, nhưng thay đổi hợp lệ về mặt replication vẫn được truyền tới mọi thành viên. Nếu người dùng chạy `DELETE` nhầm, ứng dụng ghi dữ liệu sai hoặc ransomware dùng tài khoản hợp lệ để sửa dữ liệu, cụm có thể sao chép chính thay đổi đó rất nhanh.

Vì vậy, một thiết kế vận hành cần có:

- Full backup và incremental backup theo RPO/RTO.
- Binary log được lưu giữ để PITR.
- Thử restore định kỳ trên môi trường cô lập.
- Giám sát quorum, trạng thái member, replication apply và Router.
- Tài khoản riêng, quyền tối thiểu và quản lý secret.
- Kiểm thử failover, phục hồi member và thay đổi primary.
- Kế hoạch DR ngoài cụm nếu cần chịu lỗi vùng hoặc site.

Không coi số lượng member ONLINE là bằng chứng duy nhất cho khả năng phục hồi. Định kỳ diễn tập mất node, mất mạng, hết dung lượng, lỗi donor và lỗi Router để biết hệ thống thực sự phản ứng ra sao.

## 13. Quy trình triển khai và kiểm tra

Một quy trình triển khai thực tế có thể đi theo thứ tự:

1. Xác định RTO/RPO, số member, failure domain và single-primary hay multi-primary.
2. Chuẩn bị các instance cùng phiên bản tương thích, server_id duy nhất, GTID và binary log.
3. Kiểm tra bảng InnoDB, khóa chính, quyền quản trị, hostname và firewall.
4. Cài MySQL Shell, chạy `dba.checkInstanceConfiguration()` và `dba.configureInstance()` cho từng instance.
5. Tạo cluster trên seed bằng `dba.createCluster()`.
6. Thêm các instance còn lại bằng `cluster.addInstance()`, chọn incremental hoặc clone theo trạng thái dữ liệu.
7. Kiểm tra `cluster.status({extended: 1})` cho đến khi tất cả member dự kiến đều ONLINE.
8. Bootstrap ít nhất hai MySQL Router ở các failure domain phù hợp và cấu hình ứng dụng dùng endpoint Router.
9. Thử chuyển primary, mất một member, phục hồi member và kiểm tra kết nối ứng dụng.
10. Thiết lập backup/PITR, giám sát và lịch diễn tập sự cố.

Kết quả kiểm thử phải xác nhận không chỉ việc cụm tự bầu primary mà còn cả việc ứng dụng kết nối lại, transaction được retry an toàn, secondary bắt kịp và Router định tuyến đúng.

## 14. Ghi nhớ

- InnoDB Cluster kết hợp Group Replication, MySQL Shell AdminAPI và MySQL Router.
- Group Replication đồng bộ transaction và xử lý membership/certification; AdminAPI quản trị vòng đời; Router định tuyến client.
- Single-primary thường dễ vận hành hơn; multi-primary cần workload ít xung đột và logic retry phù hợp.
- Quorum cần đa số thành viên; ba member có thể chịu một member lỗi nếu còn kết nối và tài nguyên.
- AdminAPI giúp kiểm tra instance, tạo cluster, thêm/xóa member, chuyển primary và xem trạng thái.
- Incremental recovery cần binlog còn đầy đủ; clone recovery thay thế dữ liệu recipient.
- Router không giữ kết nối đang chạy qua failover; ứng dụng cần reconnect và retry an toàn.
- Group Replication không thay thế backup, PITR hay DR.
- Không ép quorum khi chưa cô lập các partition còn lại.

Thiết kế HA tốt bắt đầu từ việc phân biệt rõ replication, quản trị topology và định tuyến ứng dụng. Khi quorum, recovery, Router, backup và quy trình failover đều được kiểm thử, InnoDB Cluster mới trở thành nền tảng sẵn sàng cao có thể vận hành tin cậy.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: InnoDB Cluster](https://dev.mysql.com/doc/mysql-shell/8.0/en/mysql-innodb-cluster.html)
- [MySQL Shell 8.0: AdminAPI](https://dev.mysql.com/doc/mysql-shell/8.0/en/admin-api.html)
- [MySQL 8.0 Reference Manual: Group Replication](https://dev.mysql.com/doc/refman/8.0/en/group-replication.html)
- [MySQL Router 8.0 Reference Manual](https://dev.mysql.com/doc/mysql-router/8.0/en/)

