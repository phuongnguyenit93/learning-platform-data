# Phân biệt sẵn sàng cao, phục hồi thảm họa và mở rộng tải

Bài học này thuộc module **DATABASE_MYSQL**. Khi vận hành MySQL cho ứng dụng thực tế, hệ thống cần tiếp tục phục vụ khi một thành phần gặp lỗi, có thể phục hồi sau sự cố lớn và đáp ứng tải tăng theo thời gian. Ba mục tiêu này liên quan với nhau nhưng không giống nhau: **sẵn sàng cao (High Availability - HA)** giảm gián đoạn dịch vụ, **phục hồi thảm họa (Disaster Recovery - DR)** khôi phục hệ thống sau sự cố nghiêm trọng, còn **mở rộng tải (scalability)** giúp xử lý nhiều yêu cầu hoặc dữ liệu hơn.

Một cụm nhiều máy chủ chưa chắc đã có HA tốt; một replica chưa chắc là bản backup; và thêm read replica không làm tăng trực tiếp năng lực ghi. Muốn chọn đúng kiến trúc, cần xác định loại lỗi cần chịu đựng, mức mất dữ liệu chấp nhận được, thời gian phục hồi, đặc điểm đọc/ghi và cách ứng dụng kết nối tới MySQL.

## 1. Ba mục tiêu: HA, DR và scalability

### 1.1. Sẵn sàng cao (HA)

HA là thiết kế giúp dịch vụ tiếp tục hoạt động hoặc nhanh chóng hoạt động trở lại khi một thành phần bị lỗi. Với MySQL, thành phần đó có thể là tiến trình mysqld, máy chủ vật lý/ảo, ổ đĩa, mạng, proxy hoặc một thành viên trong cụm.

HA thường dựa trên các thành phần dự phòng, cơ chế phát hiện lỗi, chuyển đổi vai trò (failover), định tuyến kết nối và quy trình phục hồi tự động hoặc bán tự động. Mục tiêu là giảm downtime trong phạm vi các lỗi đã dự kiến.

Ví dụ: source MySQL ngừng hoạt động, một replica đã đồng bộ được chọn làm primary mới. Proxy hoặc MySQL Router chuyển kết nối ghi sang primary mới để ứng dụng tiếp tục làm việc.

### 1.2. Phục hồi thảm họa (DR)

DR là khả năng khôi phục dịch vụ và dữ liệu sau sự cố có phạm vi lớn, chẳng hạn mất toàn bộ một trung tâm dữ liệu, lỗi vùng cloud, hỏng storage dùng chung, tấn công phá hoại hoặc thao tác quản trị làm mất dữ liệu trên nhiều máy chủ.

DR thường cần một địa điểm hoặc miền lỗi độc lập, bản backup tách biệt, binary log được lưu ngoài hệ thống nguồn, thông tin cấu hình và khóa mã hóa, cùng runbook khôi phục. DR có thể mất nhiều thời gian hơn HA vì phải dựng hoặc kích hoạt môi trường dự phòng, kiểm tra dữ liệu rồi chuyển ứng dụng sang đó.

Ví dụ: toàn bộ vùng cloud đang chạy primary và các replica bị mất. Đội vận hành kích hoạt cụm ở vùng khác, restore bản backup gần nhất, phát lại binary log được lưu trữ ngoài vùng lỗi và chuyển ứng dụng sang endpoint mới.

### 1.3. Mở rộng tải (Scalability)

Scalability là khả năng tăng năng lực xử lý khi số lượng người dùng, truy vấn hoặc dung lượng dữ liệu tăng. Hai hướng cơ bản:

- **Vertical scaling (scale up):** tăng CPU, RAM, IOPS hoặc dung lượng cho máy chủ MySQL hiện tại.
- **Horizontal scaling (scale out):** phân tải lên nhiều máy chủ, ví dụ read replica cho truy vấn đọc hoặc sharding để phân chia dữ liệu và tải ghi.

HA tập trung vào khả năng chịu lỗi và duy trì dịch vụ. Scalability tập trung vào năng lực xử lý. Một read replica có thể vừa là bản dự phòng cho failover vừa phục vụ truy vấn đọc, nhưng hai vai trò có thể cạnh tranh tài nguyên và cần được thiết kế rõ ràng.

### 1.4. Bảng so sánh

| Tiêu chí | HA | DR | Scalability |
|---|---|---|---|
| Mục tiêu | Giảm gián đoạn khi thành phần lỗi | Khôi phục sau sự cố lớn | Xử lý tải hoặc dữ liệu tăng |
| Phạm vi lỗi | Process, host, node hoặc một miền lỗi nhỏ | Mất site/vùng, phá hoại dữ liệu, lỗi diện rộng | Quá tải CPU, I/O, kết nối hoặc giới hạn kiến trúc |
| Cơ chế điển hình | Replica, quorum, failover, routing | Backup độc lập, binlog archive, site dự phòng | Scale up, read replica, cache, sharding |
| Chỉ số trọng tâm | Availability, failover time, RTO/RPO | RTO/RPO sau thảm họa | Throughput, latency, capacity |
| Kiểm thử | Node failure, network partition, switchover | Restore và diễn tập chuyển site | Load test, capacity test, benchmark |

Một kiến trúc sản xuất thường cần cả ba mục tiêu, nhưng không nên giả định một cơ chế duy nhất sẽ giải quyết tất cả.

## 2. Đo lường tính sẵn sàng và mục tiêu phục hồi

### 2.1. Availability và downtime

Availability thường được biểu diễn bằng tỷ lệ thời gian dịch vụ hoạt động trong một khoảng đo:

\[
Availability = \frac{Thời\ gian\ hoạt\ động}{Tổng\ thời\ gian\ quan\ sát} \times 100\%
\]

Các mức availability phổ biến tương ứng với downtime lý thuyết như sau:

| Mức availability | Downtime tối đa xấp xỉ trong 1 năm 365 ngày |
|---|---:|
| 99% | 3 ngày 15 giờ 36 phút |
| 99,9% | 8 giờ 45 phút 36 giây |
| 99,95% | 4 giờ 22 phút 48 giây |
| 99,99% | 52 phút 34 giây |
| 99,999% | 5 phút 15 giây |

Đây là phép quy đổi toán học, chưa tính cách hợp đồng SLA định nghĩa cửa sổ bảo trì, lỗi loại trừ hay cách làm tròn. Availability của database cũng không tự động bằng availability của ứng dụng: nếu ứng dụng, DNS, proxy hoặc mạng không hoạt động thì người dùng vẫn không truy cập được dữ liệu.

Nên đo bằng các kiểm tra từ góc nhìn ứng dụng, chẳng hạn kết nối được, thực hiện được giao dịch đại diện và nhận được kết quả đúng. Chỉ kiểm tra tiến trình mysqld còn sống là chưa đủ.

### 2.2. RTO và RPO

Hai chỉ số quan trọng khi thiết kế HA và DR:

- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa mà tổ chức chấp nhận trước khi dịch vụ được khôi phục.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường đo bằng khoảng thời gian từ thời điểm phục hồi đến thời điểm xảy ra lỗi.

Ví dụ, RTO 10 phút và RPO 30 giây có nghĩa là mục tiêu khôi phục dịch vụ trong 10 phút và chấp nhận mất tối đa khoảng 30 giây dữ liệu mới nhất. Đây là mục tiêu thiết kế, không phải cam kết tự động của MySQL. Phải đo bằng diễn tập và xác nhận với chủ hệ thống.

HA và DR có thể có RTO/RPO khác nhau. Một cụm HA trong cùng vùng có thể chuyển primary trong vài chục giây, trong khi DR ở vùng khác có thể cần hàng chục phút để dựng lại dữ liệu và chuyển ứng dụng. Nếu yêu cầu kinh doanh đòi hỏi cùng một RPO/RTO cho cả hai, chi phí và độ phức tạp sẽ tăng đáng kể.

## 3. Xác định miền lỗi trước khi chọn kiến trúc

Thiết kế HA/DR cần xác định những gì có thể hỏng cùng lúc. Một số miền lỗi thường gặp:

| Miền lỗi | Ví dụ | Cách giảm rủi ro |
|---|---|---|
| Tiến trình | mysqld crash, plugin lỗi | Restart có kiểm soát, giám sát, node dự phòng |
| Máy chủ | Host, VM hoặc instance mất kết nối | Replica trên host khác, failover |
| Storage | Volume lỗi, hết dung lượng, corruption | Storage redundancy, backup độc lập, kiểm tra restore |
| Rack/AZ | Mất điện, mạng hoặc hạ tầng của một khu vực | Đặt node ở các failure zone khác nhau |
| Region/site | Mất toàn bộ vùng hoặc trung tâm dữ liệu | Cụm DR ở vùng độc lập, backup ngoài site |
| Lỗi con người/phần mềm | DROP nhầm bảng, migration lỗi, bug ghi sai dữ liệu | Backup, binlog, kiểm soát thay đổi, PITR |
| Bảo mật | Ransomware, lộ thông tin xác thực, phá hoại | Tài khoản tách biệt, quyền tối thiểu, backup bất biến và tách quyền |

Đặt ba máy MySQL trên cùng một host vật lý không tạo ra dự phòng trước lỗi host. Đặt các replica trên cùng storage hoặc cùng miền mạng cũng có thể khiến chúng cùng mất khả năng hoạt động. Dự phòng chỉ có ý nghĩa khi các thành phần không phụ thuộc vào cùng một điểm lỗi duy nhất.

Một hệ thống HA cũng cần loại bỏ **single point of failure (SPOF)** ở các lớp khác: proxy duy nhất, DNS không dự phòng, secret store không truy cập được, một đường mạng duy nhất hoặc quy trình failover chỉ một người biết thực hiện.

## 4. Các mô hình HA phổ biến cho MySQL

### 4.1. Một primary và một hoặc nhiều replica bất đồng bộ

Đây là mô hình source/replica phổ biến. Ứng dụng ghi vào primary; replica nhận binary log và áp dụng transaction theo sau. Khi primary lỗi, một replica đủ mới có thể được promote thành primary mới.

```text
                 +------------------+
Ứng dụng ghi --->| Primary MySQL    |
                 | Binary log       |
                 +------------------+
                    |           |
          async     |           | async
                    v           v
             +----------+  +----------+
             | Replica A|  | Replica B|
             +----------+  +----------+
                    |
              ứng dụng đọc
```

Ưu điểm:

- Dễ triển khai hơn các cụm đồng bộ/quorum.
- Có thể dùng replica để phục vụ truy vấn đọc.
- Có thể promote replica khi primary gặp lỗi.
- Hỗ trợ backup và PITR từ binary log.

Giới hạn:

- Replication bất đồng bộ có độ trễ; replica có thể chưa nhận hoặc chưa áp dụng transaction mới nhất khi primary hỏng.
- Failover cần xác định replica nào có dữ liệu đầy đủ nhất, ngăn primary cũ tiếp tục nhận ghi và chuyển endpoint.
- Nếu ứng dụng ghi trực tiếp vào replica hoặc có nhiều đường ghi, nguy cơ dữ liệu phân kỳ tăng lên.
- Một thao tác sai hoặc dữ liệu hỏng có thể được truyền sang replica.

Mô hình này phù hợp khi chấp nhận một mức RPO nhất định, có runbook failover rõ ràng và cần read scaling. Dùng GTID giúp xác định transaction đã thực thi và cấu hình lại replication sau khi chuyển vai trò thuận tiện hơn.

### 4.2. Semi-synchronous replication

Semi-synchronous replication bổ sung xác nhận từ replica vào đường commit của source. Tùy plugin và cấu hình, source chờ ít nhất một replica xác nhận đã nhận và ghi sự kiện vào relay log trước khi hoàn tất commit theo chế độ semi-sync.

Điểm cần hiểu rõ: xác nhận nhận log không đồng nghĩa replica đã áp dụng transaction vào bảng dữ liệu. Semi-sync giảm cửa sổ mất dữ liệu trong một số tình huống, nhưng không tự tạo ra bảo đảm zero data loss trong mọi sự cố. Nếu không có replica xác nhận trong thời gian cấu hình, cơ chế có thể timeout và chuyển sang hành vi bất đồng bộ theo cấu hình.

Do đó, semi-sync là một biện pháp cải thiện RPO trong mô hình source/replica; nó không tương đương với một cụm đồng thuận quorum và không thay thế backup/DR.

### 4.3. InnoDB Cluster và Group Replication

**MySQL InnoDB Cluster** kết hợp Group Replication, MySQL Shell và MySQL Router để xây dựng cụm MySQL có cơ chế quản lý thành viên và định tuyến kết nối. Group Replication sử dụng cơ chế trao đổi thông điệp và đồng thuận theo nhóm để các thành viên thống nhất thứ tự transaction được chấp nhận.

Hai chế độ vận hành chính:

- **Single-primary:** một thành viên nhận ghi; các thành viên còn lại là secondary. Khi primary lỗi và cụm còn quorum, một secondary phù hợp có thể được bầu làm primary mới.
- **Multi-primary:** nhiều thành viên có thể nhận ghi. Group Replication kiểm tra xung đột transaction; transaction xung đột có thể bị từ chối và ứng dụng cần xử lý retry. Mô hình này đòi hỏi thiết kế dữ liệu và ứng dụng cẩn thận hơn.

Single-primary thường dễ vận hành và dự đoán hơn cho nhiều ứng dụng OLTP. Multi-primary không có nghĩa mọi transaction ghi đều chạy song song không xung đột; các transaction cùng sửa một dữ liệu có thể bị certification failure hoặc rollback.

Trong cụm ba thành viên, đa số là hai thành viên. Nếu một thành viên lỗi, hai thành viên còn lại vẫn có thể duy trì quorum. Nếu mạng bị chia cắt thành hai phía một thành viên và hai thành viên, phía có đa số có thể tiếp tục, phía thiểu số không được tự ý tiếp tục nhận ghi. Với cụm năm thành viên, cần ba phiếu để đạt đa số.

Quorum là điều kiện quan trọng để tránh hai phía của một network partition cùng hoạt động như primary độc lập. Vì vậy, không nên thiết kế cụm với số thành viên hoặc vị trí triển khai khiến một sự cố mạng phổ biến làm mất đa số.

### 4.4. Vai trò của MySQL Router

MySQL Router cung cấp endpoint để ứng dụng kết nối theo vai trò của cụm. Thay vì cấu hình ứng dụng trỏ cố định vào một IP primary, Router có thể định tuyến kết nối tới primary hoặc secondary theo metadata và cấu hình routing.

Router không lưu dữ liệu và không tự thay thế cơ chế đồng thuận của Group Replication. Nó cần được triển khai dự phòng, giám sát và đặt gần ứng dụng phù hợp với topology. Ứng dụng vẫn cần xử lý lỗi kết nối, kết nối lại và transaction có kết quả chưa xác định khi primary chuyển đổi.

### 4.5. Sơ đồ InnoDB Cluster single-primary

```text
                    +------------------+
Ứng dụng ---------->| MySQL Router     |
                    | endpoint ghi/đọc |
                    +------------------+
                             |
                 +-----------+-----------+
                 |           |           |
                 v           v           v
            +---------+ +---------+ +---------+
            | Node 1  | | Node 2  | | Node 3  |
            | Primary | |Secondary| |Secondary|
            +---------+ +---------+ +---------+
                 Group Replication / quorum
```

Đây là sơ đồ logic. Trong triển khai thực tế, Router nên có nhiều instance và các node nên được phân bố theo failure domain phù hợp. Đặt ba node ở ba AZ có thể tăng khả năng chịu lỗi AZ, nhưng cần xem xét latency mạng và yêu cầu quorum.

## 5. Failover và switchover

Hai thao tác thường bị nhầm lẫn:

- **Failover:** chuyển sang máy chủ khác ngoài kế hoạch vì primary hiện tại đã lỗi hoặc không còn an toàn để phục vụ.
- **Switchover:** chuyển vai trò có kế hoạch, ví dụ bảo trì primary, nâng cấp hoặc chuyển vùng hoạt động.

### 5.1. Quy trình failover với source/replica

Một runbook failover nên có các bước:

1. **Phát hiện và xác nhận lỗi:** kiểm tra health check từ ứng dụng, trạng thái mysqld, mạng, storage và khả năng truy cập primary.
2. **Fence primary cũ:** ngăn máy chủ cũ tiếp tục nhận ghi. Có thể cần cô lập mạng, dừng dịch vụ hoặc dùng cơ chế fencing của hạ tầng. Chỉ bỏ endpoint khỏi load balancer chưa chắc đã ngăn các client khác ghi trực tiếp.
3. **Chọn replica:** so sánh GTID đã nhận/đã thực thi hoặc tọa độ binlog, xác định replica có dữ liệu mới nhất và phù hợp với mục tiêu RPO.
4. **Hoàn tất áp dụng log:** nếu primary cũ còn truy cập được, có thể thu thập transaction cuối cùng theo runbook. Không giả định mọi transaction đã commit đều có mặt trên replica bất đồng bộ.
5. **Promote:** cấu hình replica được chọn thành primary mới, bật quyền ghi theo chính sách và xác minh dữ liệu.
6. **Chuyển kết nối:** cập nhật Router, proxy, service discovery hoặc endpoint ứng dụng.
7. **Tái cấu hình replica còn lại:** cho các replica khác theo primary mới, thường thuận tiện hơn khi dùng GTID.
8. **Theo dõi sau chuyển đổi:** kiểm tra lỗi ứng dụng, transaction retry, replication lag, dữ liệu và dung lượng.

Không nên promote một replica trước khi đã ngăn primary cũ tiếp tục nhận ghi. Nếu cả hai cùng nhận ghi, hệ thống có thể rơi vào **split-brain**: hai nhánh dữ liệu độc lập cùng được xem là authoritative. Hợp nhất dữ liệu sau đó có thể rất khó hoặc không thể tự động.

### 5.2. Switchover có kế hoạch

Một switchover an toàn thường gồm:

1. Chọn thời điểm ít tải và thông báo cửa sổ chuyển đổi.
2. Dừng hoặc khóa ghi mới vào primary cũ theo quy trình ứng dụng.
3. Chờ replica mục tiêu nhận và áp dụng hết transaction cần thiết.
4. Xác minh dữ liệu, GTID hoặc tọa độ replication đã đồng bộ.
5. Chuyển vai trò primary/replica và endpoint kết nối.
6. Mở lại ghi, kiểm tra luồng replication mới và theo dõi ứng dụng.

Switchover có thể đạt RPO bằng 0 cho các transaction đã được xác nhận đồng bộ và được kiểm soát đúng quy trình, nhưng cần kiểm tra điều kiện cụ thể của topology. Không dùng từ “zero data loss” nếu chưa chứng minh được hành vi commit, fencing và trạng thái replica trong tình huống lỗi.

## 6. DR: thiết kế môi trường phục hồi độc lập

HA thường xử lý lỗi thành phần trong một cụm hoặc một vùng. DR cần chuẩn bị cho trường hợp toàn bộ vùng hoạt động không thể dùng hoặc dữ liệu chính bị phá hoại.

### 6.1. Các thành phần của một giải pháp DR

- **Site/vùng dự phòng:** MySQL instance hoặc cụm ở miền lỗi độc lập, có tài nguyên đủ để khôi phục tải quan trọng.
- **Backup độc lập:** full và incremental backup được lưu ngoài site chính, có retention và cơ chế chống xóa.
- **Binary log archive:** chuyển binlog liên tục sang storage độc lập để phục hồi đến thời điểm cần thiết.
- **Cấu hình và secret:** lưu an toàn cấu hình MySQL, TLS certificate, keyring, khóa mã hóa, tài khoản dịch vụ và thông tin định tuyến.
- **Runbook:** hướng dẫn restore, phát lại binlog, xác minh dữ liệu, chuyển endpoint và quay lại site chính.
- **Diễn tập:** định kỳ khôi phục trên môi trường DR và đo RTO/RPO thực tế.

Một replica ở vùng khác có thể giảm thời gian khôi phục khi site chính lỗi, nhưng nếu chỉ dựa vào replica thì thao tác xóa nhầm hoặc dữ liệu hỏng vẫn có thể được sao chép. Backup bất biến và binlog archive độc lập vẫn cần thiết.

### 6.2. Active-passive và active-active ở cấp site

| Mô hình | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Active-passive | Một site nhận ghi; site DR đồng bộ dữ liệu và chờ kích hoạt | Luồng ghi đơn giản, dễ kiểm soát xung đột | Cần chuyển ứng dụng và tài nguyên khi DR; replica có thể trễ |
| Active-active | Nhiều site cùng phục vụ traffic | Có thể phân phối tải và giảm thời gian chuyển dịch vụ ở một số kiến trúc | Xử lý xung đột ghi, định tuyến, nhất quán và vận hành phức tạp |

Replication đa site không tự tạo ra active-active an toàn. Nếu hai site cùng nhận ghi vào cùng dữ liệu, cần một thiết kế phân vùng dữ liệu hoặc cơ chế xử lý xung đột rõ ràng. Với nhiều hệ thống MySQL, active-passive thường dễ kiểm soát hơn cho database giao dịch.

### 6.3. Trình tự DR khi mất site chính

1. Xác nhận phạm vi thảm họa và quyết định kích hoạt DR theo quyền phê duyệt đã định trước.
2. Cô lập site cũ nếu có nguy cơ nó hoạt động trở lại và nhận ghi song song.
3. Xác định backup tốt gần nhất và tập binlog archive liên tục.
4. Khởi tạo hoặc kiểm tra cụm ở site DR; restore backup và phát lại log đến điểm phục hồi được chọn.
5. Xác minh database, đối tượng, quyền, keyring, dữ liệu nghiệp vụ và ứng dụng.
6. Chuyển DNS, Router, proxy hoặc cấu hình service discovery sang site DR.
7. Theo dõi traffic, độ trễ, lỗi kết nối và tính nhất quán sau khi mở dịch vụ.
8. Lập kế hoạch failback về site chính sau khi site đó được sửa chữa và đồng bộ lại an toàn.

Failback là một lần chuyển đổi khác, không đơn giản là bật lại máy chủ cũ. Cần xác định site nào đang authoritative, đồng bộ dữ liệu theo một chiều được kiểm soát, xác minh điểm đồng bộ rồi mới chuyển vai trò.

## 7. Mở rộng tải MySQL

### 7.1. Scale up

Tăng CPU, RAM, dung lượng hoặc IOPS có thể cải thiện hiệu năng khi máy chủ còn nút thắt tài nguyên. Đây thường là cách đơn giản nhất để tăng năng lực của một primary, nhưng có giới hạn phần cứng, chi phí và cửa sổ thay đổi. Scale up không tạo thêm bản sao dữ liệu và không giải quyết lỗi của máy chủ duy nhất.

Trước khi tăng cấu hình, hãy đo CPU, memory pressure, buffer pool hit ratio, disk latency, IOPS, số kết nối, lock wait, transaction duration và query latency. Nếu nút thắt là truy vấn thiếu index hoặc transaction giữ lock lâu, thêm CPU/RAM có thể chỉ cải thiện một phần.

### 7.2. Scale đọc bằng replica

Read replica có thể phục vụ truy vấn đọc để giảm tải cho primary. Ứng dụng hoặc lớp proxy phân loại truy vấn và gửi truy vấn đọc phù hợp tới replica.

Các lưu ý quan trọng:

- Replica bất đồng bộ có thể trễ, vì vậy đọc ngay sau khi ghi có thể chưa thấy dữ liệu vừa commit.
- Các nghiệp vụ read-after-write cần đọc từ primary hoặc dùng cơ chế chờ replica bắt kịp theo GTID/position phù hợp.
- Truy vấn nặng trên replica có thể làm chậm applier và tăng replication lag.
- Không nên phân tải đọc một cách mù quáng nếu replica đang cần làm failover candidate; tải đọc quá lớn có thể khiến replica không bắt kịp.
- Cần giới hạn kết nối và cân bằng tải; mỗi replica có chi phí CPU, RAM, storage và vận hành riêng.

Read scaling giúp tăng năng lực đọc. Nó không phân tán trực tiếp các transaction ghi; primary vẫn có thể là điểm nghẽn cho workload write-heavy.

### 7.3. Scale ghi bằng sharding

Khi một primary không đáp ứng được tải ghi, có thể phân chia dữ liệu thành nhiều shard. Mỗi shard là một tập dữ liệu được quản lý bởi một máy chủ hoặc cụm riêng; ứng dụng định tuyến thao tác đến shard chứa dữ liệu tương ứng.

Ví dụ, dữ liệu khách hàng có thể phân vùng theo `customer_id`:

```text
customer_id 0..999999       -> Shard A
customer_id 1000000..1999999 -> Shard B
customer_id 2000000..2999999 -> Shard C
```

Đây chỉ là ví dụ về cách chia phạm vi. Chọn shard key cần cân nhắc phân bố dữ liệu, tăng trưởng, truy vấn phổ biến và khả năng di chuyển shard. Nếu phần lớn truy vấn cần join dữ liệu ở nhiều shard, độ phức tạp và chi phí mạng tăng lên.

Sharding đem lại khả năng phân phối tải ghi và dung lượng, nhưng kéo theo:

- Định tuyến truy vấn và quản lý metadata shard.
- Khó thực hiện transaction xuyên shard và đảm bảo tính nhất quán.
- Khó join, sort, aggregate và tạo báo cáo toàn cục.
- Cần kế hoạch rebalance, split/merge shard và xử lý shard mất cân bằng.
- Mỗi shard vẫn cần HA, backup, PITR và DR riêng.

Không nên sharding trước khi đo và tối ưu schema, index, truy vấn, connection pool, transaction và cấu hình máy chủ. Partitioning trong một bảng MySQL cũng không tương đương sharding: partitioning tổ chức dữ liệu bên trong một bảng/instance, không tự tạo thêm máy chủ hay failure domain độc lập.

### 7.4. Cache và connection pooling

Cache có thể giảm số truy vấn lặp lại tới MySQL, đặc biệt với dữ liệu đọc nhiều và ít thay đổi. Cần thiết kế TTL, invalidation và hành vi khi cache lỗi để tránh dữ liệu cũ kéo dài hoặc cache trở thành điểm lỗi mới.

Connection pool giúp tái sử dụng kết nối, giới hạn số connection và giảm chi phí tạo kết nối liên tục. Khi failover, pool cần loại bỏ kết nối cũ, thử kết nối lại theo backoff và tránh tạo một đợt reconnect đồng loạt gây quá tải primary mới.

## 8. Chọn kiến trúc theo yêu cầu

| Nhu cầu | Mô hình có thể cân nhắc | Điều cần kiểm chứng |
|---|---|---|
| Hệ thống nhỏ, chấp nhận downtime dài hơn | Một MySQL + backup/PITR | Thời gian restore, RPO/RTO thực tế |
| Cần failover cơ bản và scale đọc | Primary + async replicas | Lag, promotion, fencing, routing |
| Muốn giảm cửa sổ mất dữ liệu trên source/replica | Semi-sync replication | Timeout, số replica xác nhận, hành vi khi mất kết nối |
| Cần quản lý quorum và tự động bầu primary trong cụm | InnoDB Cluster / Group Replication | Số thành viên, quorum, latency, Router và runbook |
| Cần chịu lỗi toàn vùng | Cụm hoặc replica DR ở region khác + backup/binlog archive | Độ trễ liên vùng, RPO/RTO, failover/failback |
| Cần tăng năng lực đọc | Read replicas, cache | Read-after-write, lag, tải applier |
| Cần phân phối tải ghi vượt giới hạn một primary | Sharding hoặc kiến trúc phân vùng dữ liệu | Shard key, transaction xuyên shard, rebalance |

Quy trình lựa chọn nên bắt đầu bằng yêu cầu kinh doanh: dịch vụ quan trọng đến mức nào, downtime bao lâu là chấp nhận được, có thể mất bao nhiêu dữ liệu, workload đọc/ghi ra sao và ngân sách vận hành thế nào. Sau đó mới chọn topology và công cụ.

## 9. Ứng dụng phải được thiết kế để chịu chuyển đổi

Database có thể failover thành công nhưng ứng dụng vẫn lỗi nếu không xử lý connection và transaction đúng cách.

### 9.1. Kết nối lại có kiểm soát

- Dùng endpoint ổn định qua Router, proxy hoặc service discovery thay vì gắn cứng IP primary.
- Thiết lập timeout kết nối và retry với exponential backoff cùng jitter.
- Khi failover, đóng và tạo lại connection pool để loại bỏ kết nối tới primary cũ.
- Giới hạn số lần retry và tổng thời gian retry để tránh tạo tải lớn khi database chưa sẵn sàng.

### 9.2. Transaction có kết quả chưa xác định

Nếu kết nối bị ngắt trong lúc `COMMIT`, ứng dụng có thể không biết transaction đã commit ở server hay chưa. Retry nguyên transaction có thể tạo thao tác trùng lặp nếu nghiệp vụ không idempotent.

Với các thao tác quan trọng như thanh toán hoặc tạo đơn hàng, nên thiết kế idempotency key, unique constraint hoặc cơ chế đối soát để một yêu cầu được xử lý đúng một lần về mặt nghiệp vụ. Không giả định lỗi kết nối đồng nghĩa transaction đã rollback.

### 9.3. Nhất quán khi đọc từ replica

Nếu người dùng vừa cập nhật dữ liệu rồi đọc ngay, ứng dụng cần bảo đảm read-after-write. Cách đơn giản là đọc từ primary trong một khoảng thời gian sau khi ghi. Với yêu cầu cụ thể hơn, có thể chờ replica áp dụng đến một GTID hoặc vị trí đã biết nếu phiên bản và topology hỗ trợ cơ chế tương ứng.

Không gửi mọi truy vấn đọc sang replica mà không xét ngữ nghĩa. Báo cáo có thể chấp nhận dữ liệu trễ vài giây; trang xác nhận thanh toán thường cần thấy trạng thái mới ngay.

## 10. Giám sát và diễn tập

Một hệ thống HA/DR cần giám sát trạng thái và khả năng phục hồi, không chỉ giám sát CPU và RAM.

### 10.1. Các chỉ số nên theo dõi

- **Availability:** kết nối và giao dịch tổng hợp từ góc nhìn ứng dụng.
- **Replication:** receiver/applier state, replication lag, GTID retrieved/executed, relay log growth và lỗi replication.
- **Group Replication:** trạng thái thành viên, primary hiện tại, quorum, member state và lỗi kết nối nhóm.
- **Database:** connection saturation, query latency, lock wait, deadlock, transaction dài, CPU, memory, disk latency và dung lượng.
- **Backup/DR:** thời điểm backup thành công gần nhất, tuổi binlog archive, checksum, dung lượng, kết quả restore drill và RTO/RPO đo được.
- **Routing:** trạng thái Router/proxy, endpoint primary, lỗi DNS và thời gian cập nhật định tuyến.

Đặt cảnh báo theo ngưỡng gắn với mục tiêu kinh doanh. Ví dụ, replication lag cần cảnh báo trước khi vượt RPO hoặc trước khi replica không còn khả năng bắt kịp do binlog sắp hết retention.

### 10.2. Diễn tập có kiểm soát

Ít nhất cần diễn tập các tình huống:

1. Dừng tiến trình MySQL trên primary và đo thời gian phát hiện, failover, ứng dụng kết nối lại.
2. Mất kết nối mạng giữa các thành viên để kiểm tra hành vi quorum và tránh split-brain.
3. Replica lag cao hoặc applier dừng để xác minh cảnh báo và runbook.
4. Mất toàn bộ một AZ/site để thực hiện quy trình DR.
5. Xóa nhầm dữ liệu trong môi trường thử nghiệm để kiểm tra backup và PITR.
6. Failback sau khi site chính phục hồi để xác minh dữ liệu và vai trò được chuyển an toàn.

Ghi lại thời điểm bắt đầu, thời điểm phát hiện, thời điểm database sẵn sàng, thời điểm ứng dụng phục vụ thành công, lượng dữ liệu mất và các thao tác thủ công. Các con số đó mới chứng minh được RTO/RPO thực tế.

## 11. Những hiểu lầm cần tránh

1. **Có replica nghĩa là có backup:** sai. Replica có thể nhận cả thao tác xóa nhầm hoặc dữ liệu hỏng. Cần backup độc lập và PITR.
2. **Có ba node nghĩa là không thể downtime:** sai. Mất quorum, mạng, storage, Router hoặc ứng dụng vẫn có thể làm dịch vụ gián đoạn.
3. **Failover luôn không mất dữ liệu:** sai với replication bất đồng bộ; replica có thể thiếu transaction mới nhất.
4. **Thêm read replica làm tăng tốc ghi:** sai. Nó chủ yếu phân tải đọc; primary vẫn xử lý luồng ghi.
5. **Semi-sync tương đương đồng bộ quorum:** sai. Điều kiện xác nhận và hành vi timeout khác với Group Replication.
6. **Tự động failover luôn an toàn hơn thủ công:** không hẳn. Nếu phát hiện lỗi sai hoặc không fencing primary cũ, tự động hóa có thể tạo split-brain.
7. **DR chỉ cần một replica ở vùng khác:** sai. Cần backup độc lập, binlog, cấu hình, khóa, endpoint và diễn tập phục hồi.
8. **Partitioning là sharding:** sai. Partitioning không tự phân phối workload sang các instance độc lập.

## 12. Checklist thiết kế HA/DR và mở rộng tải

- [ ] Đã xác định workload đọc/ghi, mục tiêu availability, RTO và RPO.
- [ ] Đã liệt kê failure domain và SPOF ở database, network, routing, storage và ứng dụng.
- [ ] Replica hoặc thành viên cụm được phân bố theo miền lỗi phù hợp.
- [ ] Đã xác định cơ chế đồng bộ: async, semi-sync hay Group Replication và hiểu giới hạn dữ liệu.
- [ ] Đã có cơ chế fencing để primary cũ không thể tiếp tục nhận ghi sau failover.
- [ ] Đã chọn endpoint ổn định và kiểm thử connection pool khi chuyển primary.
- [ ] Đã thiết kế backup độc lập, binlog archive, retention, mã hóa và bảo vệ khóa.
- [ ] Đã có quy trình restore, PITR, failover, switchover, DR và failback.
- [ ] Đã đo replication lag, quorum, transaction latency, connection và dung lượng.
- [ ] Đã thử tải đọc trên replica và xác định chính sách read-after-write.
- [ ] Đã đánh giá shard key nếu workload ghi vượt khả năng của một primary.
- [ ] Đã diễn tập và ghi lại RTO/RPO thực tế.

## 13. Tự kiểm tra

1. HA khác DR ở phạm vi sự cố và mục tiêu phục hồi như thế nào?
2. Vì sao một replica bất đồng bộ có thể không chứa transaction cuối cùng khi primary gặp sự cố?
3. Semi-synchronous replication xác nhận điều gì, và vì sao điều đó chưa có nghĩa transaction đã được áp dụng trên replica?
4. Quorum có vai trò gì trong Group Replication khi xảy ra network partition?
5. Vì sao phải fencing primary cũ trước khi promote replica?
6. MySQL Router giải quyết phần nào trong kiến trúc InnoDB Cluster, và nó không thay thế thành phần nào?
7. Vì sao read replica giúp scale đọc nhưng không tự giải quyết nút thắt ghi?
8. Sharding đem lại lợi ích gì và tạo ra những khó khăn nào cho transaction, join và vận hành?
9. Vì sao transaction bị ngắt kết nối tại thời điểm COMMIT cần được xử lý bằng idempotency hoặc đối soát?
10. Hãy đề xuất kiến trúc cho một ứng dụng cần RTO 10 phút, RPO 1 phút, có site DR và tải đọc cao; nêu cách kiểm thử để chứng minh mục tiêu.

Khi thiết kế MySQL cho production, hãy nối yêu cầu kinh doanh với failure domain, cơ chế đồng bộ, endpoint ứng dụng, backup và runbook. Một kiến trúc chỉ đáng tin khi đã được thử trong các tình huống lỗi đại diện và kết quả đo thực tế đáp ứng mục tiêu đã thống nhất.
