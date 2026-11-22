# Mô hình source/replica và vai trò trong mở rộng đọc hoặc khôi phục

Replication trong MySQL duy trì một hoặc nhiều máy chủ replica bằng cách chuyển các thay đổi được ghi vào binary log của máy chủ source sang các máy chủ còn lại. Mô hình này giúp phân phối truy vấn đọc, tạo máy dự phòng và hỗ trợ khôi phục dịch vụ khi source gặp sự cố. Để sử dụng đúng, cần hiểu luồng dữ liệu, độ trễ sao chép và giới hạn nhất quán của từng replica.

Trong MySQL hiện đại, tài liệu và câu lệnh mới dùng thuật ngữ **source** và **replica**. Một số phiên bản cũ vẫn hiển thị tên gọi **master** và **slave** trong câu lệnh hoặc trường trạng thái. Bài học sử dụng source/replica; khi vận hành cần đối chiếu cú pháp với phiên bản MySQL đang chạy.

## 1. Kiến trúc source/replica

Trong mô hình một source và một replica, ứng dụng gửi thao tác ghi đến source. Source thực thi transaction và ghi các thay đổi vào binary log. Replica kết nối đến source, nhận các sự kiện binary log, lưu chúng vào relay log rồi áp dụng lên dữ liệu cục bộ.

~~~mermaid
flowchart LR
    AppW["Ứng dụng ghi"] --> Source["MySQL source"]
    Source --> Binlog[("Binary log")]
    Binlog --> Receiver["Receiver thread"]
    Receiver --> Relay[("Relay log")]
    Relay --> Applier["Applier thread"]
    Applier --> Replica["MySQL replica"]
    AppR["Ứng dụng đọc"] --> Replica
    AppR2["Truy vấn đọc khác"] --> Source
~~~

Luồng cơ bản gồm các thành phần:

| Thành phần | Vai trò |
|---|---|
| Source | Nhận ghi, thực thi transaction và phát các sự kiện thay đổi qua binary log |
| Binary log (binlog) | Lưu các sự kiện cần sao chép; cũng là đầu vào quan trọng cho khôi phục theo thời điểm |
| Receiver thread (I/O thread) | Trên replica, kết nối đến source và đọc các sự kiện binlog |
| Relay log | Lưu tạm các sự kiện đã nhận để replica có thể áp dụng |
| Applier thread (SQL thread hoặc worker) | Đọc relay log và thực thi các thay đổi trên replica |
| Replica | Duy trì bản sao dữ liệu, phục vụ truy vấn đọc hoặc chờ được chọn làm source mới |

Replication thông thường của MySQL là **asynchronous replication**. Source không phải đợi replica áp dụng transaction xong mới tiếp tục xử lý ghi. Vì vậy source có thể hoạt động nhanh và độc lập, nhưng replica có thể chậm hơn source một khoảng thời gian.

Khi receiver đã nhận sự kiện, sự kiện được ghi vào relay log. Applier có thể áp dụng ngay hoặc xử lý sau nếu tải cao, transaction chạy lâu hay có lỗi. Do đó cần phân biệt dữ liệu **đã nhận** và dữ liệu **đã áp dụng**. Một replica có receiver đang hoạt động nhưng applier bị dừng vẫn có thể tích lũy relay log mà dữ liệu chưa theo kịp source.

Mỗi máy chủ trong topology phải có **server_id duy nhất**. Source cần bật binary logging; replica cần kết nối được đến source và có cấu hình replication tương ứng. Nếu replica còn phải phát lại các thay đổi của mình cho replica phía sau hoặc có thể được promote thành source trong một topology tiếp nối, cần thiết kế thêm việc ghi binary log trên replica, thường thông qua tùy chọn **log_replica_updates** ở các phiên bản hỗ trợ tên mới.

## 2. Source và replica đảm nhiệm những vai trò nào?

**Source** là điểm ghi chính trong topology một source. Nó tiếp nhận các lệnh **INSERT**, **UPDATE**, **DELETE**, thay đổi schema và transaction của ứng dụng. Các thay đổi cần sao chép được ghi vào binary log. Source cũng thường là nơi có dữ liệu mới nhất và là nơi phù hợp cho các thao tác cần đọc ngay kết quả vừa ghi.

**Replica** nhận và áp dụng các thay đổi từ source. Một replica có thể phục vụ báo cáo, dashboard, truy vấn tra cứu hoặc các tác vụ đọc nặng. Replica khác có thể được giữ gần như không phục vụ ứng dụng để sẵn sàng thay thế source khi có sự cố. Có thể triển khai nhiều replica với cấu hình phần cứng hoặc mục đích khác nhau.

| Vai trò của replica | Cách sử dụng | Điều cần lưu ý |
|---|---|---|
| Read replica | Chuyển truy vấn đọc phù hợp khỏi source | Kết quả có thể cũ hơn source do replication lag |
| Reporting replica | Chạy báo cáo hoặc truy vấn phân tích ít ảnh hưởng đến ứng dụng giao dịch | Truy vấn nặng vẫn tiêu thụ CPU, I/O và bộ nhớ trên replica |
| Standby replica | Chờ được promote khi source lỗi | Cần theo dõi độ trễ, dung lượng và quy trình chuyển vai trò |
| Backup replica | Hỗ trợ lấy bản sao lưu để giảm tải cho source | Cần bảo đảm snapshot nhất quán; replica không thay thế bản backup độc lập |

Một topology phổ biến có một source và nhiều replica:

~~~mermaid
flowchart TB
    App["Ứng dụng"]
    Source["Source"]
    R1["Replica đọc ứng dụng"]
    R2["Replica báo cáo"]
    R3["Replica dự phòng"]
    App -->|"Ghi"| Source
    App -->|"Đọc phù hợp"| R1
    Source --> R1
    Source --> R2
    Source --> R3
~~~

Mô hình này giúp phân phối tải đọc theo mục đích. Tuy nhiên, mọi thao tác ghi vẫn tập trung tại source. Thêm replica không tự động tăng năng lực ghi của một source và cũng không thay thế việc tối ưu schema, index, transaction hay truy vấn.

Có thể xây dựng topology nhiều tầng, trong đó một replica tiếp tục phát binlog cho replica khác, hoặc cấu hình multi-source để một replica nhận dữ liệu từ nhiều source. Những topology này có thêm ràng buộc về luồng dữ liệu, xung đột, thứ tự transaction và vận hành. Chỉ triển khai khi đã xác định rõ dữ liệu nào thuộc nguồn nào và cách xử lý xung đột; mô hình một source với nhiều replica thường dễ kiểm soát hơn.

## 3. Replication giúp mở rộng đọc như thế nào?

Khi ứng dụng có nhiều truy vấn đọc, một phần truy vấn có thể được chuyển đến read replica. Source tiếp tục xử lý transaction ghi; replica xử lý truy vấn đọc trên bản dữ liệu được sao chép. Việc định tuyến thường được thực hiện ở tầng ứng dụng, connection pool, proxy hoặc lớp truy cập dữ liệu.

Ví dụ phân loại luồng truy vấn:

| Loại thao tác | Nơi nên gửi | Lý do |
|---|---|---|
| Tạo đơn hàng, cập nhật số dư, ghi giao dịch | Source | Cần thực hiện ghi trên điểm ghi chính |
| Đọc ngay đơn hàng vừa tạo hoặc dữ liệu vừa cập nhật | Source, hoặc cơ chế chờ replica áp dụng transaction | Tránh đọc dữ liệu chưa được sao chép |
| Tra cứu danh mục, nội dung, dữ liệu ít thay đổi | Read replica | Có thể chấp nhận độ trễ nhỏ nếu nghiệp vụ cho phép |
| Báo cáo tổng hợp, dashboard, truy vấn đọc nặng | Replica chuyên báo cáo | Giảm cạnh tranh tài nguyên với workload giao dịch trên source |
| Thao tác thay đổi schema hoặc quản trị replication | Theo runbook trên source hoặc máy được chỉ định | Tránh thực hiện tùy tiện trên replica đang phục vụ đọc |

Không nên gửi mọi câu **SELECT** sang replica một cách máy móc. Một số truy vấn cần đọc chính xác trạng thái mới nhất ngay sau khi ghi. Nếu ứng dụng ghi một đơn hàng lên source rồi lập tức đọc đơn hàng đó từ replica, replica có thể chưa áp dụng transaction và trả về kết quả cũ hoặc chưa thấy bản ghi.

Đây là vấn đề **read-after-write consistency**. Có ba cách xử lý phổ biến:

1. Sau một thao tác ghi, tiếp tục đọc từ source trong một khoảng thời gian hoặc trong cùng luồng nghiệp vụ.
2. Định tuyến các truy vấn yêu cầu dữ liệu mới nhất đến source; chỉ chuyển truy vấn có thể chấp nhận dữ liệu trễ sang replica.
3. Với hệ thống dùng GTID, ứng dụng hoặc middleware có thể đợi replica áp dụng đến GTID của transaction cần đọc trước khi gửi truy vấn. Cơ chế chờ phải có timeout và phương án dự phòng khi replica không theo kịp.

Độ trễ sao chép có thể thay đổi theo tải ghi, transaction lớn, truy vấn chạy lâu trên replica, tốc độ mạng, dung lượng I/O và cách cấu hình applier. Vì vậy, cần đặt ngưỡng lag phù hợp với nghiệp vụ và có phương án khi vượt ngưỡng, chẳng hạn tạm ngừng định tuyến một số truy vấn đến replica đang chậm.

Replication chỉ phân phối tải đọc ở mức máy chủ. Nếu một truy vấn báo cáo quét quá nhiều dữ liệu hoặc thiếu index, nó vẫn có thể làm replica quá tải. Cần đo hiệu năng, đọc EXPLAIN, thiết kế index và giới hạn truy vấn nặng như trên source.

## 4. Replication lag và tính nhất quán

**Replication lag** là khoảng chậm giữa thay đổi trên source và thời điểm thay đổi đó được áp dụng trên replica. Lag có thể ngắn trong điều kiện bình thường nhưng tăng mạnh khi source ghi nhiều, có transaction lớn hoặc replica thiếu tài nguyên.

Một số tình huống dễ gây hiểu nhầm:

- Receiver hoạt động nhưng applier dừng: relay log vẫn tăng, dữ liệu trên replica không tiến lên.
- Receiver dừng hoặc mất kết nối: replica không nhận thêm sự kiện mới từ source.
- Một transaction lớn: replica có thể mất thời gian đáng kể để áp dụng transaction đó.
- Truy vấn đọc dài: có thể cạnh tranh tài nguyên với applier và làm chậm việc cập nhật dữ liệu.
- **Seconds_Behind_Source** bằng **0** không phải bằng chứng tuyệt đối rằng mọi truy vấn sẽ luôn thấy dữ liệu mới nhất; chỉ số này là một tín hiệu giám sát và cần được đọc cùng trạng thái receiver, applier và các lỗi replication.

Với workload cần độ mới cao, hãy giám sát ít nhất:

- Trạng thái receiver và applier.
- Thời gian chậm ước tính và xu hướng lag theo thời gian.
- Lỗi I/O, lỗi áp dụng transaction và dung lượng relay log.
- Tốc độ ghi binlog ở source và tốc độ áp dụng ở replica.
- Khả năng kết nối mạng, dung lượng đĩa và tài nguyên CPU/I/O của cả hai phía.

Nếu topology dùng GTID, các tập GTID đã nhận và đã thực thi giúp xác định replica đang ở đâu trong luồng transaction. **Retrieved GTID set** phản ánh transaction đã nhận; **Executed GTID set** phản ánh transaction đã được thực thi trên máy chủ. Hai tập này hữu ích khi kiểm tra lag và lựa chọn replica để promote, nhưng cần hiểu quan hệ giữa các tập GTID và kiểm tra transaction phát sinh ngoài luồng replication trước khi chuyển vai trò.

MySQL cũng có cơ chế semi-synchronous replication khi được cấu hình plugin phù hợp. Với chế độ này, source có thể chờ ít nhất một replica xác nhận đã nhận và ghi sự kiện vào relay log trước khi hoàn tất commit theo chính sách semi-sync. Xác nhận nhận sự kiện không đồng nghĩa replica đã áp dụng transaction. Semi-sync có thể thu hẹp cửa sổ mất dữ liệu khi source lỗi, nhưng không tự bảo đảm không mất dữ liệu trong mọi tình huống; cần kiểm tra timeout, trạng thái fallback và chính sách failover.

## 5. Dùng replica làm máy dự phòng và khôi phục dịch vụ

Một replica được duy trì khỏe mạnh có thể trở thành source mới khi source hiện tại gặp sự cố. Quá trình này thường gọi là **failover**. Replica dự phòng giúp giảm thời gian khôi phục dịch vụ, nhưng hiệu quả phụ thuộc vào độ trễ replication, khả năng phát hiện sự cố và quy trình chuyển vai trò.

Hai chỉ số quan trọng khi thiết kế khôi phục:

- **RPO (Recovery Point Objective):** mức dữ liệu có thể chấp nhận mất, thường được tính theo thời gian hoặc số transaction.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa chấp nhận để khôi phục dịch vụ.

Với asynchronous replication, source có thể đã xác nhận transaction cho ứng dụng nhưng transaction đó chưa đến replica khi source đột ngột hỏng. Khi promote replica, các transaction chưa được sao chép có thể mất. RPO thực tế vì vậy phụ thuộc vào lag tại thời điểm sự cố. Nếu nghiệp vụ yêu cầu RPO rất thấp, cần cân nhắc semi-sync, kiến trúc HA phù hợp và kiểm thử failover; không nên suy ra RPO bằng 0 chỉ vì có replica.

Quy trình failover thủ công cần có các bước kiểm soát:

1. **Xác nhận sự cố:** xác định source thật sự không thể phục vụ và loại trừ lỗi mạng hoặc lỗi ứng dụng tạm thời.
2. **Ngăn source cũ tiếp tục nhận ghi:** cô lập hoặc fence máy chủ cũ để tránh hai source cùng nhận ghi khi mạng được khôi phục.
3. **Đánh giá các replica:** kiểm tra receiver/applier, lỗi replication, độ trễ và tập GTID đã thực thi. Chọn replica có dữ liệu đầy đủ nhất theo trạng thái transaction đã xác minh.
4. **Promote một replica:** dừng replication theo runbook, xác nhận dữ liệu cần thiết đã áp dụng và chuyển máy được chọn sang vai trò ghi.
5. **Chuyển định tuyến:** cập nhật proxy, DNS hoặc cấu hình ứng dụng để các kết nối ghi đi đến source mới; kiểm tra luồng đọc và ghi.
6. **Cấu hình lại topology:** đưa các replica còn lại theo source mới, xử lý source cũ trước khi cho phép nó tham gia lại.
7. **Xác minh và ghi nhận:** kiểm tra dữ liệu, lỗi, lag, backup và thời điểm chuyển vai trò; lưu lại transaction hoặc khoảng dữ liệu có thể bị mất.

Trên replica được bảo vệ bằng **super_read_only**, thao tác chuyển thành source mới phải được thực hiện có chủ đích sau khi đã cô lập source cũ và hoàn tất đánh giá dữ liệu. Ví dụ, lệnh sau có thể bỏ chế độ chỉ đọc ở cấp máy chủ:

~~~sql
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;
~~~

Đây là thao tác thay đổi vai trò, không phải lệnh khắc phục lag. Chỉ thực hiện trên đúng máy đã được chọn promote theo quy trình vận hành. Nếu source cũ vẫn có thể nhận ghi, việc mở ghi trên replica mới có thể tạo hai nhánh dữ liệu độc lập và gây xung đột khó hợp nhất.

Khi source cũ được phục hồi, không nên tự động cho nó nhận ghi trở lại. Cần xác định transaction nào đã được xác nhận ở source cũ, transaction nào đã được thực thi ở source mới và cách đồng bộ lại. Tùy tình trạng, có thể cần dựng lại máy cũ từ backup hoặc từ bản sao của source mới rồi mới thêm nó trở lại topology.

## 6. Replica có thay thế được backup không?

Replica **không phải bản backup độc lập**. Replication sao chép các thay đổi hợp lệ theo luồng binlog. Nếu người dùng vô tình chạy **DELETE** hoặc **DROP TABLE** trên source, thay đổi đó cũng có thể được áp dụng lên replica. Nếu dữ liệu bị hỏng về mặt logic hoặc tài khoản bị xâm phạm, replica có thể nhận cùng thay đổi gây hại.

Replica có thể giúp giảm tải source khi tạo backup, nhưng quy trình backup vẫn phải bảo đảm tính nhất quán của dữ liệu và lưu giữ bản sao độc lập. Một chiến lược bảo vệ dữ liệu nên kết hợp:

- Backup đầy đủ hoặc backup gia tăng theo chính sách lưu trữ.
- Binary log được giữ đủ lâu để hỗ trợ point-in-time recovery.
- Bản backup được lưu ở nơi có quyền truy cập và miền lỗi tách biệt với máy chủ cơ sở dữ liệu.
- Kiểm tra tính toàn vẹn và diễn tập restore định kỳ.
- Theo dõi replication lag và trạng thái replica được dùng làm nguồn backup.

Nếu backup từ replica, cần xác định snapshot đại diện cho thời điểm nào, cách phối hợp với applier và cách ghi nhận vị trí binlog hoặc GTID tương ứng. Nếu replica đang lag hoặc applier chưa áp dụng hết các transaction cần thiết, backup có thể không đại diện cho trạng thái mới nhất mà nghiệp vụ yêu cầu. Bản backup cũng cần có thông tin để tiếp tục khôi phục theo thời điểm từ binlog.

## 7. Cấu hình nền tảng và kiểm tra trạng thái

Ví dụ cấu hình tối thiểu cho một source:

~~~ini
[mysqld]
server_id = 101
log_bin = mysql-bin
binlog_format = ROW
~~~

Ví dụ cấu hình nền tảng cho một replica:

~~~ini
[mysqld]
server_id = 201
relay_log = relay-bin
read_only = ON
super_read_only = ON
relay_log_recovery = ON
~~~

Các giá trị **server_id** phải duy nhất trong topology. Tên tệp cấu hình và cách quản lý dịch vụ phụ thuộc hệ điều hành và cách cài MySQL. Đây là ví dụ định hướng; trước khi áp dụng cần kiểm tra phiên bản, chính sách GTID, TLS, tài khoản replication, retention của binlog và yêu cầu của topology.

Trên replica, dùng lệnh sau để kiểm tra replication ở các phiên bản MySQL hiện đại:

~~~sql
SHOW REPLICA STATUS\G
~~~

Ở các phiên bản cũ, câu lệnh có thể vẫn là **SHOW SLAVE STATUS\G**. Trong kết quả, cần xem các trường tương ứng với phiên bản, đặc biệt:

| Trường trạng thái | Ý nghĩa |
|---|---|
| **Replica_IO_Running** | Receiver thread có đang nhận binlog hay không |
| **Replica_SQL_Running** | Applier có đang áp dụng relay log hay không |
| **Seconds_Behind_Source** | Ước lượng độ trễ; cần đọc cùng các chỉ số khác |
| **Last_IO_Error** | Lỗi gần nhất khi kết nối hoặc nhận binlog |
| **Last_SQL_Error** | Lỗi gần nhất khi áp dụng sự kiện |
| **Retrieved_Gtid_Set** | Các GTID replica đã nhận, khi dùng GTID |
| **Executed_Gtid_Set** | Các GTID đã được thực thi trên máy chủ |

Hai trạng thái receiver và applier thường cần ở trạng thái **Yes** trong topology hoạt động bình thường. Nếu một trạng thái là **No**, hãy đọc thông báo lỗi tương ứng và log máy chủ trước khi khởi động lại thread một cách máy móc. Một lỗi dữ liệu hoặc schema không tương thích có thể tiếp tục xảy ra sau khi restart.

Có thể kiểm tra vai trò và chế độ chỉ đọc của máy chủ bằng:

~~~sql
SELECT
  @@hostname AS hostname,
  @@server_id AS server_id,
  @@read_only AS read_only,
  @@super_read_only AS super_read_only;
~~~

Kết quả giúp xác nhận đang kết nối đến máy chủ nào và máy chủ có đang ở chế độ chỉ đọc hay không. Không dùng một truy vấn kiểm tra đơn lẻ để kết luận toàn bộ topology khỏe mạnh; cần đối chiếu trạng thái trên source và từng replica, log, lag và tình trạng mạng.

Binary log trên source phải được giữ đủ lâu để replica có thời gian phục hồi sau gián đoạn. Nếu source xóa binlog mà replica chưa nhận được, replica có thể không còn lấy được phần sự kiện bị thiếu và cần đồng bộ lại hoặc dựng lại từ backup. Biến **binlog_expire_logs_seconds** liên quan đến thời gian lưu binlog; giá trị cần dựa trên thời gian outage tối đa dự kiến, tốc độ phát sinh binlog và khoảng dự phòng vận hành.

## 8. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Receiver không chạy | Mất mạng, sai hostname/port, tài khoản replication sai hoặc source không còn giữ binlog cần thiết | Kiểm tra **Last_IO_Error**, kết nối TCP, quyền tài khoản và binlog trên source |
| Applier không chạy | Sự kiện không áp dụng được, lỗi dữ liệu/schema hoặc xung đột | Kiểm tra **Last_SQL_Error**, transaction lỗi và sự khác biệt schema |
| Lag tăng liên tục | Tốc độ ghi source cao hơn tốc độ áp dụng, transaction lớn hoặc replica thiếu tài nguyên | Đo tải, I/O, CPU, transaction và số worker applier |
| Replica nhận được nhưng dữ liệu chưa cập nhật | Receiver hoạt động nhưng applier chậm hoặc dừng | Đối chiếu relay log, trạng thái applier và GTID đã thực thi |
| Ứng dụng đọc thấy dữ liệu cũ | Đọc từ replica trước khi transaction được áp dụng | Định tuyến read-after-write về source hoặc dùng cơ chế chờ GTID có timeout |
| Không thể dùng replica để phục hồi | Replica lag lớn, thiếu binlog hoặc bản sao dữ liệu không nhất quán | Kiểm tra GTID, binlog retention, backup và kế hoạch dựng lại |
| Sau failover có hai nơi nhận ghi | Source cũ chưa được fence hoặc định tuyến còn trỏ đến máy cũ | Cô lập source cũ, kiểm tra mọi endpoint ghi và chỉ duy trì một source hợp lệ |

Không nên bỏ qua transaction lỗi chỉ để làm cho replication tiếp tục chạy. Bỏ qua một sự kiện có thể khiến dữ liệu replica khác source mà không được nhận biết. Nếu buộc phải xử lý transaction lỗi, cần đánh giá ảnh hưởng dữ liệu, ghi nhận quyết định và xác minh lại tính nhất quán sau xử lý.

## 9. Tình huống thiết kế

Một hệ thống bán hàng có một MySQL source và hai replica:

- Source nhận đơn hàng, cập nhật thanh toán và quản lý tồn kho.
- Replica A phục vụ tra cứu đơn hàng và thông tin sản phẩm cho ứng dụng.
- Replica B phục vụ báo cáo cuối ngày và được giữ sẵn sàng để phục hồi khi source gặp sự cố.

Hãy thiết kế cách sử dụng topology này:

1. Chỉ định các thao tác tạo đơn, thanh toán và cập nhật tồn kho đến source.
2. Chỉ định truy vấn tra cứu có thể chấp nhận độ trễ đến replica A; sau khi khách vừa đặt hàng, đọc trạng thái mới từ source hoặc đợi replica áp dụng transaction cần thiết.
3. Giới hạn truy vấn báo cáo nặng ở replica B và theo dõi để báo cáo không làm replication lag tăng vượt ngưỡng.
4. Đặt cảnh báo khi receiver/applier dừng, lag tăng hoặc binlog sắp hết thời gian lưu.
5. Xây dựng runbook failover: cô lập source cũ, đánh giá GTID và lag, promote một replica, cập nhật định tuyến và kiểm tra dữ liệu.
6. Duy trì backup độc lập và thử restore; không xem hai replica là hai bản backup.

Khi đánh giá thiết kế, hãy trả lời được các câu hỏi: truy vấn nào cần dữ liệu mới nhất, lag tối đa chấp nhận được là bao nhiêu, nếu source mất ngay sau một transaction thì transaction đó đã đến replica chưa, ai có quyền promote và làm sao ngăn source cũ tiếp tục nhận ghi?

## 10. Câu hỏi tự kiểm tra

1. Binary log và relay log có vai trò khác nhau như thế nào trong replication?
2. Vì sao receiver thread chạy nhưng applier thread dừng vẫn khiến replica bị stale?
3. Read replica giúp mở rộng phần tải nào của hệ thống? Nó không giải quyết được giới hạn nào?
4. Vì sao truy vấn đọc ngay sau khi ghi có thể trả về dữ liệu cũ khi đọc từ replica?
5. Asynchronous replication ảnh hưởng đến RPO trong trường hợp source gặp sự cố như thế nào?
6. Vì sao cần fence source cũ trước khi promote replica?
7. Replica có thể thay thế backup không? Hãy nêu một tình huống khiến dữ liệu xấu được sao chép sang tất cả replica.
8. Khi kiểm tra replica, vì sao phải xem cả trạng thái receiver, applier, lỗi và GTID đã thực thi?

Một topology source/replica tốt phải có mục đích rõ cho từng replica, quy tắc định tuyến đọc/ghi, ngưỡng replication lag, chính sách lưu binlog và quy trình failover đã được diễn tập. Khi kết hợp các yếu tố này với backup độc lập và kiểm soát quyền, replication mới hỗ trợ được cả mở rộng đọc lẫn khôi phục vận hành.
