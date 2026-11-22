# InnoDB ReplicaSet và phân biệt với InnoDB Cluster

Trong module **DATABASE_MYSQL**, tính sẵn sàng cao giúp ứng dụng tiếp tục truy cập dữ liệu khi một máy chủ MySQL gặp sự cố hoặc cần bảo trì. MySQL cung cấp hai mô hình được quản lý bằng MySQL Shell AdminAPI là **InnoDB ReplicaSet** và **InnoDB Cluster**. Cả hai đều có thể kết hợp với MySQL Router để định tuyến kết nối ứng dụng, nhưng cơ chế đồng bộ dữ liệu và cách xử lý lỗi của chúng khác nhau.

Bài học này giải thích kiến trúc, luồng vận hành và tình huống sử dụng của từng mô hình. Trọng tâm là chọn đúng topology theo yêu cầu RPO/RTO, hiểu giới hạn failover và tránh để hai máy chủ cùng nhận ghi sau một lần chuyển primary.

Trong phạm vi DATABASE_MYSQL, chủ đề này bổ sung cho việc làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời; đồng thời kết nối với đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và khái niệm

Sau bài học, bạn có thể:

- Mô tả kiến trúc InnoDB ReplicaSet và InnoDB Cluster.
- Phân biệt replication bất đồng bộ với Group Replication.
- Giải thích primary, replica, member, quorum và metadata.
- Tạo, kiểm tra và thay đổi topology bằng MySQL Shell AdminAPI.
- Thực hiện planned switchover và xử lý failover khi primary gặp sự cố.
- Đánh giá nguy cơ mất dữ liệu do replication lag và nguy cơ split-brain.
- Chọn mô hình phù hợp với yêu cầu sẵn sàng cao của ứng dụng.

Một topology có **primary** nhận ghi và một hay nhiều **replica** nhận dữ liệu từ primary. Ứng dụng thường gửi truy vấn ghi đến primary; truy vấn đọc có thể được phân phối đến replica nếu ứng dụng chấp nhận độ trễ đồng bộ. Với hệ thống có nhiều thành phần, cần xác định rõ vai trò của MySQL Server, MySQL Shell, MySQL Router và công cụ giám sát.

Hai mô hình cần phân biệt:

- **InnoDB ReplicaSet:** quản lý một primary và các replica bằng replication bất đồng bộ dựa trên GTID.
- **InnoDB Cluster:** quản lý các member bằng Group Replication; có thể chạy single-primary hoặc multi-primary. Ở chế độ single-primary, Group Replication hỗ trợ tự động bầu primary mới khi primary hiện tại gặp sự cố và nhóm vẫn còn quorum.

Với dữ liệu nghiệp vụ cần tính nhất quán giao dịch, InnoDB là lựa chọn phù hợp; Group Replication yêu cầu các bảng được sao chép phải dùng InnoDB. Việc lựa chọn không chỉ là lựa chọn công cụ; nó quyết định cách hệ thống xác nhận giao dịch, xử lý thành viên lỗi và phục hồi sau gián đoạn mạng.

## 2. InnoDB ReplicaSet

### 2.1. Kiến trúc

InnoDB ReplicaSet là topology replication bất đồng bộ được quản lý bởi MySQL Shell AdminAPI. Nó có một primary và một hoặc nhiều replica:

- Primary nhận các giao dịch ghi từ ứng dụng.
- Các replica nhận binary log từ primary và áp dụng thay đổi theo cơ chế asynchronous replication.
- Mỗi replica có thể có độ trễ so với primary.
- Replica thường được đặt ở chế độ chỉ đọc để tránh ghi độc lập làm lệch dữ liệu.
- Quản trị viên điều khiển việc chuyển primary thông qua AdminAPI.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    APP[Ứng dụng] --> ROUTER[MySQL Router]
    ROUTER -->|Ghi| P[Primary]
    ROUTER -->|Đọc tùy chính sách| R1[Replica 1]
    ROUTER -->|Đọc tùy chính sách| R2[Replica 2]
    P -->|Binary log / async replication| R1
    P -->|Binary log / async replication| R2
    SHELL[MySQL Shell AdminAPI] -. quản lý .-> P
    SHELL -. quản lý .-> R1
    SHELL -. quản lý .-> R2
~~~

ReplicaSet phù hợp khi ứng dụng cần một primary ghi và các bản sao phục vụ đọc hoặc dự phòng, đồng thời chấp nhận replication bất đồng bộ và quy trình failover do quản trị viên điều khiển.

### 2.2. Replication bất đồng bộ và độ trễ

Trong asynchronous replication, primary không chờ mọi replica áp dụng giao dịch rồi mới xác nhận commit cho client. Primary ghi giao dịch vào binary log; replica nhận và áp dụng các sự kiện sau đó.

Hệ quả:

- Replica có thể chưa nhìn thấy giao dịch vừa commit trên primary.
- Tải cao, mạng chậm hoặc applier bị nghẽn có thể làm replication lag tăng.
- Nếu primary hỏng đột ngột, một số giao dịch đã xác nhận trên primary có thể chưa đến replica được chọn để nâng cấp.
- Việc đọc từ replica có thể trả về dữ liệu cũ hơn primary.

GTID giúp định danh giao dịch và theo dõi tập giao dịch đã nhận hoặc đã áp dụng. GTID không biến replication bất đồng bộ thành đồng bộ và không loại bỏ nguy cơ mất giao dịch chưa được truyền đến replica.

Nếu ứng dụng cần đọc dữ liệu vừa ghi, hãy đọc từ primary hoặc triển khai cơ chế chờ replica bắt kịp theo GTID/position phù hợp. Không giả định rằng truy vấn đọc trên replica luôn thấy ngay giao dịch trước đó của cùng người dùng.

### 2.3. Tạo và quản lý ReplicaSet bằng AdminAPI

Ví dụ minh họa dùng MySQL Shell ở chế độ JavaScript. Trước khi tạo topology, kiểm tra phiên bản, kết nối mạng, danh tính máy chủ, cấu hình GTID và các yêu cầu của AdminAPI trên tất cả instance.

Kiểm tra cấu hình instance:

~~~javascript
dba.checkInstanceConfiguration('admin@db-primary:3306');
dba.checkInstanceConfiguration('admin@db-replica1:3306');
~~~

Nếu AdminAPI đề xuất cấu hình, hãy xem lại thay đổi và áp dụng theo quy trình quản trị. Trên các máy chủ mới, dba.configureInstance() có thể cấu hình các thiết lập cần thiết:

~~~javascript
dba.configureInstance('admin@db-primary:3306');
dba.configureInstance('admin@db-replica1:3306');
~~~

Một số thay đổi cấu hình có thể yêu cầu khởi động lại MySQL Server. Hãy hoàn tất bước restart theo cửa sổ bảo trì, sau đó chạy lại kiểm tra cấu hình trước khi tạo topology. Không xem việc lệnh cấu hình trả về thành công là bằng chứng duy nhất rằng instance đã sẵn sàng.

Kết nối vào instance sẽ làm primary:

~~~javascript
var rs = dba.createReplicaSet('ordersReplicaSet');
~~~

Thêm replica. Tùy kích thước dữ liệu và trạng thái ban đầu, chọn phương pháp recovery phù hợp; ví dụ clone cần đáp ứng yêu cầu của Clone Plugin và sẽ thay thế dữ liệu trên instance nhận:

~~~javascript
rs.addInstance('admin@db-replica1:3306', {
  recoveryMethod: 'clone'
});
~~~

Kiểm tra trạng thái:

~~~javascript
rs.status();
rs.status({extended: 1});
~~~

Hãy đọc trạng thái của từng instance, vai trò, kết nối replication, lỗi applier và độ trễ nếu được cung cấp. Một instance xuất hiện trong metadata không có nghĩa nó đang đồng bộ khỏe mạnh hoặc sẵn sàng nhận đọc.

Một số thao tác quản trị thường gặp:

~~~javascript
// Kiểm tra topology và trạng thái
rs.status();

// Chuyển primary có kế hoạch sang replica đã đồng bộ
rs.setPrimaryInstance('admin@db-replica1:3306');

// Cho instance đã được sửa lỗi tham gia lại topology
rs.rejoinInstance('admin@db-replica2:3306');

// Loại instance khỏi topology khi không còn sử dụng
rs.removeInstance('admin@db-replica2:3306');
~~~

Tên host, tài khoản, cổng và tên ReplicaSet trong ví dụ chỉ là giá trị minh họa. Hãy xác nhận đúng instance trước mỗi thao tác thay đổi topology. removeInstance() thay đổi metadata topology; nó không phải lệnh xóa dữ liệu nghiệp vụ khỏi tất cả nơi lưu trữ.

### 2.4. Planned switchover

Khi cần bảo trì primary, nên thực hiện chuyển primary có kế hoạch:

1. Kiểm tra trạng thái ReplicaSet và xác nhận replica đích đang kết nối bình thường.
2. Xác nhận replica đích đã áp dụng đầy đủ các giao dịch cần thiết từ primary.
3. Kiểm tra ứng dụng, kết nối Router và kế hoạch chuyển lưu lượng.
4. Gọi rs.setPrimaryInstance() để AdminAPI thực hiện chuyển vai trò.
5. Xác minh primary mới nhận ghi, các replica còn lại theo dõi đúng primary mới và ứng dụng hoạt động.
6. Chỉ bảo trì primary cũ sau khi đã xác nhận nó không còn nhận ghi.

Ví dụ:

~~~javascript
rs.setPrimaryInstance('admin@db-replica1:3306');
rs.status();
~~~

Đây là planned switchover: primary cũ vẫn có thể tham gia quy trình chuyển vai trò. Hãy thực hiện khi replica đích đã bắt kịp để tránh mất các giao dịch đã commit trước thời điểm chuyển.

### 2.5. Failover khi primary không còn hoạt động

Nếu primary bị mất kết nối hoặc hỏng máy, ReplicaSet không tự động nâng cấp một replica thành primary. Quản trị viên cần đánh giá các replica còn hoạt động, chọn replica có dữ liệu mới nhất và thực hiện failover có kiểm soát bằng forcePrimaryInstance().

Ví dụ minh họa:

~~~javascript
var rs = dba.getReplicaSet();
rs.status();
rs.forcePrimaryInstance('admin@db-replica1:3306');
rs.status();
~~~

forcePrimaryInstance() dành cho trường hợp primary hiện tại không thể tham gia chuyển đổi bình thường. Trước khi chạy:

- Xác nhận primary cũ đã bị fencing: tắt, cô lập mạng hoặc chặn quyền ghi để nó không thể tiếp tục nhận giao dịch.
- Xác định replica được chọn đã nhận/applied đến GTID nào; so sánh các tập GTID của những replica còn lại.
- Ước lượng giao dịch có thể bị mất vì asynchronous replication.
- Ghi nhận quyết định chọn replica và mốc dữ liệu được chấp nhận.
- Sau khi nâng cấp, chỉ mở lưu lượng ghi vào primary mới khi đã xác nhận không còn primary cũ hoạt động độc lập.

Không để primary cũ tự động quay lại nhận ghi khi ReplicaSet đã có primary mới. Cần đưa nó vào quy trình rejoin/recovery để đồng bộ lại từ nguồn đúng. Nếu hai instance cùng nhận ghi, dữ liệu có thể phân nhánh và việc hợp nhất thủ công rất rủi ro.

## 3. InnoDB Cluster

### 3.1. Kiến trúc

InnoDB Cluster là giải pháp high availability dựa trên Group Replication, được quản lý bằng MySQL Shell AdminAPI và thường kết hợp với MySQL Router.

Các thành phần:

- **Group Replication:** duy trì nhóm member, phân phối và chứng nhận giao dịch, theo dõi membership và quorum.
- **MySQL Shell AdminAPI:** tạo cluster, thêm/xóa member, kiểm tra trạng thái và thực hiện các thao tác quản trị.
- **MySQL Router:** cung cấp điểm kết nối cho ứng dụng và định tuyến đến member phù hợp theo metadata topology.

Sơ đồ single-primary:

~~~mermaid
flowchart LR
    APP[Ứng dụng] --> ROUTER[MySQL Router]
    ROUTER -->|Read / Write| P[Primary]
    ROUTER -->|Read only| S1[Secondary 1]
    ROUTER -->|Read only| S2[Secondary 2]
    P <-->|Group Replication| S1
    P <-->|Group Replication| S2
    S1 <-->|Membership / transaction| S2
    SHELL[MySQL Shell AdminAPI] -. quản lý .-> P
    SHELL -. quản lý .-> S1
    SHELL -. quản lý .-> S2
~~~

Trong single-primary mode, chỉ primary nhận giao dịch ghi thông thường; các secondary nhận và áp dụng giao dịch qua Group Replication. Khi primary lỗi, các member còn lại có thể bầu primary mới nếu nhóm còn đủ quorum.

### 3.2. Group Replication, certification và quorum

Group Replication phân phối giao dịch giữa các member và dùng cơ chế certification để phát hiện xung đột ghi dựa trên write set. Trong single-primary mode, các giao dịch ghi tập trung ở primary nên giảm xung đột ghi giữa nhiều node.

**Quorum** là đa số thành viên có quyền biểu quyết cần thiết để nhóm tiếp tục hoạt động. Nó giúp nhóm tránh hai phía của một phân vùng mạng cùng tự nhận quyền điều phối giao dịch.

Ví dụ với ba member có quyền biểu quyết:

- Cả ba hoạt động: nhóm có quorum.
- Một member mất kết nối: hai member còn lại vẫn là đa số và có thể tiếp tục.
- Chỉ còn một trong ba member: nhóm không có đa số, không thể tiếp tục như một nhóm khỏe mạnh.

Vì vậy, ba member là cấu hình thường dùng để chịu được lỗi của một member. Hai member không tự tạo ra khả năng chịu lỗi một node: nếu một node mất kết nối, node còn lại không có đa số. Cần thiết kế số member, vị trí triển khai và mạng theo miền lỗi thực tế.

Quorum không thay thế sao lưu. Nó giúp duy trì hoạt động của nhóm trong một số sự cố thành viên, nhưng không bảo vệ khỏi lệnh xóa nhầm, dữ liệu sai được commit hợp lệ hoặc sự cố làm hỏng dữ liệu trên tất cả member.

### 3.3. Single-primary và multi-primary

| Chế độ | Ghi dữ liệu | Ưu điểm | Điều cần cân nhắc |
|---|---|---|---|
| Single-primary | Một primary nhận ghi; các member khác là secondary | Mô hình ứng dụng quen thuộc, ít điểm ghi đồng thời | Có khoảng gián đoạn ngắn khi bầu primary mới |
| Multi-primary | Nhiều member có thể nhận ghi | Có thể phân phối điểm ghi theo thiết kế ứng dụng | Xung đột certification, giới hạn thao tác và độ phức tạp ứng dụng cao hơn |

Single-primary là lựa chọn phổ biến cho ứng dụng OLTP thông thường. Multi-primary chỉ nên chọn khi ứng dụng đã được thiết kế để xử lý xung đột và các giới hạn của Group Replication; không nên bật chỉ vì muốn có nhiều node nhận ghi.

### 3.4. Tạo Cluster bằng AdminAPI

Kết nối MySQL Shell đến instance đầu tiên, kiểm tra và cấu hình các instance theo yêu cầu của AdminAPI. Sau đó tạo cluster:

~~~javascript
var cluster = dba.createCluster('ordersCluster');
~~~

Thêm các member:

~~~javascript
cluster.addInstance('admin@db-node2:3306');
cluster.addInstance('admin@db-node3:3306');
~~~

Kiểm tra trạng thái:

~~~javascript
cluster.status();
cluster.status({extended: 1});
~~~

Kết quả trạng thái cần được xem xét để xác nhận member đã tham gia nhóm, trạng thái đồng bộ và vai trò hiện tại. Nếu member ở trạng thái không khỏe mạnh, hãy xử lý nguyên nhân trước khi mở lưu lượng ứng dụng.

Chuyển primary có kế hoạch trong single-primary mode:

~~~javascript
cluster.setPrimaryInstance('admin@db-node2:3306');
cluster.status();
~~~

Trong trường hợp member lỗi, Group Replication có thể tự bầu primary mới nếu nhóm còn quorum. AdminAPI giúp kiểm tra và quản lý topology sau sự kiện; việc tự động bầu primary là cơ chế của Group Replication, không phải một câu lệnh forcePrimaryInstance() như trong ReplicaSet.

### 3.5. Phục hồi member lỗi

Khi một member rời nhóm, cần xác định nguyên nhân trước khi cho nó tham gia lại:

- Máy chủ hoặc tiến trình MySQL đã dừng?
- Mạng giữa các member có mất ổn định hoặc bị chặn cổng?
- GTID của member có lệch khỏi nhóm?
- Có lỗi applier hoặc dữ liệu xung đột?
- Instance có đang dùng cấu hình hoặc phiên bản không tương thích?

Sau khi sửa nguyên nhân, dùng AdminAPI để kiểm tra và rejoin member theo quy trình được hỗ trợ. Nếu dữ liệu member không còn phù hợp, có thể cần clone hoặc incremental recovery tùy tình trạng và lựa chọn được AdminAPI hỗ trợ.

Không tự sao chép thư mục dữ liệu từ member khác khi chưa kiểm tra phương pháp phục hồi. Dùng cơ chế recovery của AdminAPI để bảo đảm trạng thái GTID, metadata và dữ liệu phù hợp với topology.

## 4. So sánh ReplicaSet và Cluster

| Tiêu chí | InnoDB ReplicaSet | InnoDB Cluster |
|---|---|---|
| Cơ chế sao chép | Asynchronous replication | Group Replication |
| Topology ghi | Một primary | Single-primary hoặc multi-primary |
| Failover | Quản trị viên thực hiện; không tự động promote | Single-primary có thể tự bầu primary mới khi còn quorum |
| Quorum nhóm | Không dùng quorum Group Replication | Dựa trên đa số member có quyền biểu quyết |
| Replication lag | Có thể xuất hiện rõ do bất đồng bộ | Group Replication phối hợp giao dịch trong nhóm; vẫn có thể có member chậm hoặc không khỏe |
| Nguy cơ mất dữ liệu khi primary hỏng | Có thể mất giao dịch chưa đến replica được chọn | Được giảm nhờ cơ chế Group Replication, nhưng vẫn cần đánh giá consistency, quorum và trạng thái giao dịch |
| Độ phức tạp | Thường đơn giản hơn | Cao hơn do Group Replication và yêu cầu mạng/quorum |
| Tình huống phù hợp | Một primary, replica đọc/dự phòng, chấp nhận failover thủ công | Yêu cầu HA và failover tự động trong topology có quorum |
| Quản trị | MySQL Shell AdminAPI | MySQL Shell AdminAPI |
| Định tuyến ứng dụng | Có thể kết hợp MySQL Router | Thường kết hợp MySQL Router |

Không nên diễn giải bảng so sánh thành cam kết RPO bằng 0 cho Cluster. Tính nhất quán giao dịch và hành vi khi lỗi còn phụ thuộc cấu hình Group Replication, chế độ consistency, quorum, network partition, trạng thái member và cách ứng dụng xử lý lỗi commit. Hãy thử nghiệm tình huống lỗi thực tế để xác định RPO/RTO đạt được.

## 5. MySQL Router và luồng kết nối ứng dụng

MySQL Router là lớp định tuyến kết nối giữa ứng dụng và topology. Nó giúp ứng dụng không phải cấu hình thủ công địa chỉ của từng node cho mỗi lần chuyển primary.

Với topology có Router:

- Ứng dụng cấu hình kết nối đến endpoint của Router.
- Router đọc metadata topology và chọn backend phù hợp với mục tiêu kết nối.
- Endpoint ghi được định tuyến đến primary hiện tại.
- Endpoint đọc có thể định tuyến đến member phù hợp theo cấu hình và chính sách.
- Khi topology thay đổi, Router cập nhật định tuyến theo metadata và trạng thái mà nó quan sát được.

Router không thay thế cơ chế sao chép và không tự sửa dữ liệu bị lệch. Đối với ReplicaSet, Router không tự promote replica thay cho thao tác failover của quản trị viên. Đối với Cluster, việc bầu primary thuộc Group Replication; Router cập nhật đường đi của kết nối theo topology mới.

Các kết nối hiện hữu có thể bị ngắt trong quá trình failover hoặc chuyển vai trò. Ứng dụng cần có retry có giới hạn, backoff, xử lý lỗi giao dịch không rõ kết quả và khả năng mở lại connection pool. Không tự động retry mọi giao dịch ghi mà không xét tính idempotent, vì client có thể mất kết nối sau khi server đã commit.

## 6. Chọn mô hình theo yêu cầu hệ thống

### 6.1. Khi ReplicaSet phù hợp

Chọn ReplicaSet khi:

- Ứng dụng có một primary ghi rõ ràng.
- Có thể chấp nhận replication bất đồng bộ và theo dõi lag.
- Failover thủ công theo runbook là phù hợp với RTO.
- Muốn quản lý topology primary/replica hiện có bằng MySQL Shell AdminAPI.
- Chi phí vận hành và mức độ phức tạp cần được giữ ở mức thấp hơn Group Replication.

Ví dụ: một hệ thống báo cáo nội bộ có primary nhận ghi, một replica đọc báo cáo và một replica dự phòng. Nếu primary lỗi, đội vận hành có thể xác định replica đã bắt kịp và chuyển primary theo quy trình được phê duyệt.

### 6.2. Khi Cluster phù hợp

Chọn InnoDB Cluster khi:

- Dịch vụ cần failover tự động trong giới hạn quorum.
- Có thể triển khai đủ member và mạng ổn định giữa các node.
- Ứng dụng chấp nhận việc kết nối có thể bị gián đoạn ngắn trong lúc bầu primary.
- Đội vận hành có khả năng theo dõi Group Replication, quorum và trạng thái member.
- Cần một topology HA được quản lý bằng AdminAPI và định tuyến qua Router.

Ví dụ: hệ thống giao dịch trực tuyến cần chuyển primary nhanh khi một node gặp lỗi, có ba member ở các miền lỗi phù hợp và quy trình kiểm tra sức khỏe topology liên tục.

### 6.3. Ma trận quyết định

| Câu hỏi | Nếu câu trả lời là Có | Hướng xem xét |
|---|---|---|
| Chấp nhận replica có thể trễ và failover do người vận hành thực hiện? | Có | ReplicaSet |
| Cần tự động bầu primary khi một member lỗi và còn quorum? | Có | InnoDB Cluster single-primary |
| Ứng dụng cần nhiều node cùng nhận ghi? | Có | Đánh giá multi-primary rất kỹ; kiểm tra xung đột và giới hạn |
| Không thể bảo đảm kết nối mạng ổn định giữa các member? | Có | Xem lại thiết kế Cluster và miền lỗi trước khi triển khai |
| RPO/RTO rất nghiêm ngặt? | Có | Thử nghiệm cả hai mô hình, đo lag/failover/restore; không chọn theo tên sản phẩm |

Cần xác định rõ mục tiêu:

- **RPO:** mức dữ liệu tối đa có thể mất. Với ReplicaSet bất đồng bộ, phải tính đến giao dịch chưa được replica nhận. Với Cluster, cần đo hành vi thực tế của cấu hình và tình huống lỗi.
- **RTO:** thời gian dịch vụ được khôi phục. ReplicaSet cần thời gian phát hiện, quyết định và promote thủ công; Cluster có thể tự bầu primary khi đủ quorum nhưng ứng dụng vẫn cần phục hồi kết nối.

## 7. Chuẩn bị và kiểm soát trước khi triển khai

Trước khi tạo ReplicaSet hoặc Cluster, cần chuẩn bị:

1. Phiên bản MySQL Server và MySQL Shell tương thích với nhau.
2. Hostname phân giải ổn định giữa các node; không dựa vào địa chỉ thay đổi bất ngờ.
3. server_id duy nhất cho mỗi instance và cấu hình binary logging phù hợp.
4. GTID được bật và cấu hình nhất quán theo yêu cầu AdminAPI.
5. InnoDB cho các bảng nghiệp vụ cần replication.
6. Tài khoản quản trị topology có quyền phù hợp, mật khẩu được lưu an toàn.
7. Firewall cho phép các cổng client, replication và Group Replication cần thiết.
8. Đồng bộ thời gian và giám sát độ trễ, lỗi mạng, dung lượng, CPU, I/O.
9. Backup độc lập trước khi thêm, clone hoặc thay đổi vai trò instance.
10. Runbook cho planned switchover, unplanned failover, rejoin và rollback.

Với Group Replication, các yêu cầu thường bao gồm binary logging, GTID, row-based logging, tính nhất quán GTID và cấu hình replication cần thiết. Mỗi instance phải có server_id duy nhất; các node cần phân giải hostname ổn định và giao tiếp được qua các cổng Group Replication. Hãy để AdminAPI kiểm tra và đề xuất cấu hình theo phiên bản đang chạy thay vì tự áp một bộ tham số cũ.

Không tự sao chép một danh sách cấu hình từ môi trường khác mà chưa chạy kiểm tra AdminAPI. Phiên bản MySQL, hệ điều hành, network stack và cấu hình bảo mật có thể làm thay đổi các yêu cầu cụ thể.

Các lệnh kiểm tra cấu hình và trạng thái thường dùng:

~~~sql
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW REPLICA STATUS;
~~~

SHOW REPLICA STATUS dùng để kiểm tra trạng thái replication bất đồng bộ trên các phiên bản MySQL hiện hành; ở phiên bản cũ có thể gặp tên lệnh SHOW SLAVE STATUS. Với InnoDB Cluster, ngoài các biến máy chủ, hãy dùng cluster.status() để xem trạng thái Group Replication và member.

## 8. Vận hành và giám sát

Một topology HA chỉ có ích nếu có thể phát hiện sớm lỗi và thực hiện đúng runbook. Theo dõi ít nhất:

- Trạng thái primary và replica/member.
- Replication lag, số giao dịch đang chờ áp dụng và lỗi applier.
- Kết nối mạng giữa các node và trạng thái quorum của Cluster.
- CPU, memory, disk I/O, dung lượng relay log và binary log.
- Số lượng kết nối, connection error và thời gian truy vấn.
- Trạng thái MySQL Router, metadata cache và endpoint ứng dụng.
- Sự kiện failover, switchover, rejoin, clone và thay đổi cấu hình.

Với ReplicaSet, đặt cảnh báo khi replica lag vượt ngưỡng nghiệp vụ hoặc replica không áp dụng được log. Không nâng cấp một replica đang tụt xa thành primary chỉ vì primary hiện tại đã lỗi; trước hết hãy đánh giá mức mất dữ liệu có thể chấp nhận.

Với Cluster, cảnh báo khi member rời nhóm, nhóm mất quorum, member chuyển sang trạng thái không khỏe mạnh hoặc primary election kéo dài. Không cố ép một nhóm mất quorum hoạt động bằng cách khởi động lại tùy tiện từng node; cần theo runbook Group Replication để tránh tạo hai nhóm độc lập.

## 9. Diễn tập sự cố

Hãy diễn tập trên môi trường không phục vụ dữ liệu sản xuất. Một kế hoạch tối thiểu nên có:

| Tình huống | ReplicaSet | InnoDB Cluster |
|---|---|---|
| Primary dừng có kế hoạch | Dùng setPrimaryInstance() sau khi replica bắt kịp | Dùng cluster.setPrimaryInstance() trong single-primary |
| Primary hỏng đột ngột | Fencing primary cũ, đánh giá GTID, rồi force promote replica | Kiểm tra quorum và để Group Replication bầu primary mới |
| Replica/member mất mạng | Kiểm tra lag, sửa mạng, rejoin | Kiểm tra membership, quorum và rejoin |
| Node quay lại sau failover | Không cho node cũ nhận ghi; rejoin/recover từ primary mới | Kiểm tra trạng thái member và recovery trước khi phục vụ |
| Mất nhiều node | Chọn replica có dữ liệu tốt nhất, đánh giá khả năng mất giao dịch | Xác định nhóm còn quorum hay không; phục hồi nhóm theo runbook |

Ghi lại thời điểm sự cố, thời điểm phát hiện, thời điểm promote/election, thời điểm Router chuyển endpoint, thời điểm ứng dụng phục vụ lại và GTID cuối cùng được xác nhận. Từ đó tính RPO/RTO thực tế.

Diễn tập phải bao gồm trường hợp client mất kết nối ngay sau khi gửi COMMIT. Ứng dụng có thể không biết giao dịch đã commit hay chưa. Cần thiết kế khóa idempotency hoặc cơ chế tra cứu trạng thái giao dịch để tránh ghi trùng khi retry.

## 10. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| ReplicaSet replica không theo kịp | Mạng chậm, tải ghi cao, applier bị nghẽn | Kiểm tra trạng thái replication, lag, relay log, CPU và I/O |
| Không thể chuyển primary | Replica đích chưa đồng bộ hoặc topology có lỗi | Xem rs.status(), xác định GTID còn thiếu và sửa lỗi trước |
| Force promote có nguy cơ mất dữ liệu | Replica đích chưa nhận hết giao dịch của primary cũ | So sánh GTID, chọn instance có tập giao dịch phù hợp và ghi nhận RPO |
| Primary cũ quay lại sau failover | Chưa fencing hoặc chưa rejoin đúng quy trình | Chặn ghi trên node cũ, kiểm tra dữ liệu rồi rejoin/recover |
| Cluster mất quorum | Quá nhiều member lỗi hoặc network partition | Kiểm tra trạng thái từng member và kết nối; phục hồi quorum theo runbook |
| Member không vào được Cluster | Cấu hình, GTID, plugin, phiên bản hoặc network chưa phù hợp | Chạy kiểm tra AdminAPI, đọc error log và xử lý recovery |
| Router vẫn định tuyến sai hoặc kết nối lỗi | Metadata chưa cập nhật, Router không truy cập được member hoặc connection cũ | Kiểm tra Router log, metadata cache, endpoint và trạng thái topology |
| Ứng dụng ghi trùng sau failover | Retry giao dịch không idempotent khi kết quả COMMIT chưa rõ | Dùng request ID/idempotency key và kiểm tra trạng thái trước khi gửi lại |

Khi xử lý sự cố, thu thập trạng thái topology, log MySQL Server, log MySQL Shell/Router, GTID, replication lag và thời điểm sự kiện. Tránh thao tác cưỡng bức trên nhiều node cùng lúc nếu chưa xác định rõ node nào đang có quyền ghi.

## 11. Tự kiểm tra

**Tình huống 1:** Một hệ thống dùng ReplicaSet có primary và hai replica. Primary bị hỏng; một replica đã áp dụng đến GTID mới hơn replica còn lại. Cần làm gì trước khi promote?

**Gợi ý:** Xác nhận primary cũ đã bị fencing, so sánh tập GTID và chọn replica có dữ liệu đầy đủ nhất. Đánh giá giao dịch có thể mất rồi mới dùng forcePrimaryInstance().

**Tình huống 2:** Một Cluster có ba member và một member bị mất mạng. Hai member còn lại có thể tiếp tục không?

**Gợi ý:** Hai trong ba là đa số nên nhóm vẫn có quorum, với điều kiện hai member còn lại hoạt động và giao tiếp được với nhau.

**Tình huống 3:** Một Cluster chỉ có hai member. Một member dừng, member còn lại không thể tiếp tục như nhóm khỏe mạnh. Vì sao?

**Gợi ý:** Một trong hai không phải đa số. Quorum bảo vệ nhóm khỏi hai phía của một phân vùng mạng cùng nhận quyền điều phối.

**Tình huống 4:** Ứng dụng kết nối qua MySQL Router. Router có tự promote replica của ReplicaSet khi primary bị hỏng không?

**Gợi ý:** Không. Failover của ReplicaSet cần quản trị viên điều khiển bằng AdminAPI. Router định tuyến theo metadata topology sau khi vai trò được cập nhật.

**Tình huống 5:** Hệ thống yêu cầu failover tự động và có ba node ở các miền lỗi độc lập. Nên đánh giá mô hình nào?

**Gợi ý:** InnoDB Cluster single-primary phù hợp để đánh giá vì Group Replication có thể bầu primary mới khi còn quorum. Cần diễn tập để đo RTO và kiểm tra hành vi ứng dụng.

## 12. Điểm cần ghi nhớ

- InnoDB ReplicaSet dùng asynchronous replication, một primary và các replica; failover cần quản trị viên thực hiện.
- InnoDB Cluster dùng Group Replication; single-primary có thể tự bầu primary mới khi nhóm còn quorum.
- GTID giúp theo dõi giao dịch nhưng không biến ReplicaSet thành replication đồng bộ.
- Khi force promote ReplicaSet, phải fencing primary cũ và đánh giá giao dịch có thể bị mất.
- Quorum là đa số member; ba member thường chịu được lỗi một node, còn hai member không chịu được mất một node mà vẫn giữ đa số.
- MySQL Router định tuyến kết nối theo topology; nó không thay thế replication hoặc quyết định promote của ReplicaSet.
- Ứng dụng cần xử lý kết nối bị ngắt, retry có giới hạn và giao dịch có kết quả COMMIT chưa rõ.
- Chọn topology dựa trên RPO/RTO, miền lỗi, khả năng vận hành và kết quả diễn tập thực tế.

## Tài liệu tham khảo

- [MySQL Shell 8.4 Reference: InnoDB ReplicaSet](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-innodb-replicaset.html) — kiến trúc, tạo và quản lý ReplicaSet.
- [MySQL Shell 8.4 Reference: InnoDB Cluster](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-innodb-cluster.html) — kiến trúc Cluster và các thao tác AdminAPI.
- [MySQL 8.4 Reference: Group Replication](https://dev.mysql.com/doc/refman/8.4/en/group-replication.html) — member, quorum, single-primary và multi-primary.
- [MySQL Router 8.4 Reference](https://dev.mysql.com/doc/mysql-router/8.4/en/) — bootstrap, metadata cache và định tuyến kết nối.
