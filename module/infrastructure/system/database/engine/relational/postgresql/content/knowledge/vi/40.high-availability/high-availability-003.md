# Failover, switchover và tiêu chí kích hoạt trong PostgreSQL

High availability (HA) giúp dịch vụ PostgreSQL tiếp tục phục vụ khi primary hoặc một thành phần hạ tầng gặp sự cố. Trong kiến trúc streaming replication, một hoặc nhiều standby nhận WAL từ primary và có thể được promote thành primary mới khi cần.

Hai hoạt động chuyển vai trò thường gặp là:

- **Failover**: chuyển dịch vụ sang standby vì primary bị lỗi hoặc không còn an toàn để phục vụ.
- **Switchover**: chuyển vai trò primary một cách có kế hoạch, thường để bảo trì, nâng cấp hoặc chuyển tải sang node khác.

Cả hai đều có thể kết thúc bằng việc promote một standby, nhưng tiêu chí kích hoạt, mức độ kiểm soát và quy trình phối hợp khác nhau. Một quyết định promote sai có thể làm mất dữ liệu hoặc tạo hai primary cùng nhận ghi (split-brain).

Một quy trình HA phải trả lời được bốn câu hỏi:

1. Khi nào xác định primary thực sự không còn phục vụ?
2. Standby nào đủ điều kiện trở thành primary?
3. Làm thế nào bảo đảm primary cũ không tiếp tục nhận ghi?
4. Sau khi chuyển vai trò, ứng dụng và các node còn lại kết nối tới đâu?

~~~mermaid
flowchart TD
    A["Primary đang phục vụ"] --> B{"Sự kiện xảy ra?"}
    B -->|"Bảo trì có kế hoạch"| C["Switchover"]
    B -->|"Primary lỗi / mất an toàn"| D["Failover"]
    C --> E["Drain writes và đồng bộ standby"]
    E --> F["Fence hoặc dừng primary cũ"]
    D --> G["Xác nhận lỗi và quorum"]
    G --> H["Fence primary cũ"]
    F --> I["Promote đúng một standby"]
    H --> I
    I --> J["Xác minh primary mới"]
    J --> K["Chuyển endpoint / kết nối ứng dụng"]
    K --> L["Rejoin node cũ và giám sát"]
~~~

Bài học thuộc chương **Tính sẵn sàng cao**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ phân tích tiêu chí kích hoạt, RPO/RTO, replication lag, synchronous/asynchronous replication, fencing, promotion, client routing, rejoin và kiểm thử HA.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt failover, switchover và failback.
2. Mô tả vai trò primary, standby và HA manager.
3. Xây dựng tiêu chí xác định primary failure.
4. Phân biệt lỗi database, lỗi host và lỗi đường mạng.
5. Đánh giá standby candidate dựa trên WAL/LSN và trạng thái replication.
6. Giải thích ảnh hưởng của synchronous và asynchronous replication tới RPO.
7. Hiểu mối liên hệ giữa RPO, RTO và thời gian phát hiện lỗi.
8. Giải thích split-brain và vai trò của fencing.
9. Promote standby bằng pg_ctl hoặc pg_promote.
10. Xác minh node mới đã thoát recovery và có thể nhận ghi.
11. Chuyển endpoint và xử lý connection pool của ứng dụng.
12. Đưa primary cũ trở lại topology bằng pg_rewind hoặc base backup mới.
13. Thực hiện switchover có kiểm soát và giảm thiểu mất dữ liệu.
14. Hiểu quorum, witness và vai trò của HA orchestration.
15. Theo dõi replication lag, WAL, timeline và trạng thái standby.
16. Xây dựng runbook cho các tình huống lỗi khác nhau.
17. Kiểm thử failover, switchover và failback định kỳ.
18. Đánh giá các rủi ro về dữ liệu, kết nối, bảo mật và vận hành.

## 2. Các thuật ngữ cần phân biệt

### Failover

Failover là hành động chuyển dịch vụ từ primary bị lỗi sang một standby đủ điều kiện. Failover thường được kích hoạt bởi sự cố ngoài kế hoạch như:

- PostgreSQL primary process bị dừng.
- Máy chủ hoặc storage bị hỏng.
- Primary không thể phục vụ truy vấn ghi.
- Primary bị cô lập khỏi phần còn lại của hệ thống.
- Sự cố trung tâm dữ liệu hoặc availability zone.

Failover có thể tự động hoặc do operator thực hiện. Tự động hóa rút ngắn RTO nhưng cần quorum, fencing và tiêu chí chọn candidate đủ chặt để tránh promote nhầm.

### Switchover

Switchover là chuyển primary sang một standby khi hệ thống vẫn hoạt động và có thể phối hợp các bước chuyển đổi.

Các lý do thường gặp:

- Bảo trì phần cứng hoặc hệ điều hành.
- Nâng cấp PostgreSQL hoặc thay đổi cấu hình.
- Chuyển workload sang máy chủ khác.
- Kiểm tra năng lực standby.
- Di chuyển giữa các vùng hạ tầng.

Vì primary cũ vẫn có thể phối hợp, operator có thể ngừng ghi, đợi standby replay tới WAL cuối cùng, dừng primary cũ rồi mới promote standby. Switchover được chuẩn bị tốt thường có thể đạt RPO bằng 0 đối với các giao dịch đã được đồng bộ đầy đủ.

### Failback

Failback là chuyển vai trò trở lại node hoặc site ban đầu sau khi sự cố được xử lý. Đây cũng là một lần chuyển vai trò có kế hoạch, không đơn giản là bật lại máy cũ.

Node primary cũ thường đã đi theo timeline cũ và có thể chứa các transaction khác với primary mới. Cần đưa node đó về trạng thái standby bằng pg_rewind nếu đủ điều kiện, hoặc tạo lại từ base backup, sau đó mới cân nhắc switchover trở lại.

| Thuật ngữ | Thời điểm | Mục tiêu | Mức độ phối hợp |
| --- | --- | --- | --- |
| Failover | Sau sự cố | Khôi phục dịch vụ trên standby | Thường khẩn cấp |
| Switchover | Có kế hoạch | Chuyển vai trò an toàn | Có thể drain và đồng bộ trước |
| Failback | Sau khi xử lý sự cố | Đưa node cũ trở lại topology | Cần kiểm tra và lập kế hoạch |

## 3. Kiến trúc HA với primary và standby

Một kiến trúc đơn giản:

~~~text
                 Application
                      |
              Stable DB endpoint
                      |
                 HA routing
                      |
             Current primary node
                 /          \
            WAL sender     Monitoring
                |
         Streaming replication
                |
          Standby node(s)
~~~

Primary nhận các transaction ghi và tạo WAL. Standby nhận WAL, ghi vào storage và replay để cập nhật trạng thái database.

Các thành phần vận hành thường gồm:

- PostgreSQL primary.
- Một hoặc nhiều physical standby.
- Network riêng cho replication.
- Replication slots hoặc chính sách WAL retention.
- HA manager/cluster manager.
- Distributed configuration store hoặc quorum mechanism khi kiến trúc cần.
- Fencing mechanism.
- Load balancer, virtual IP, proxy hoặc service discovery.
- Monitoring, alerting và backup/WAL archive.

### PostgreSQL streaming replication không tự cung cấp toàn bộ HA orchestration

Streaming replication vận chuyển WAL và duy trì standby. Nó không tự quyết định rằng primary đã chết, không tự fence primary cũ và không tự chuyển endpoint cho mọi ứng dụng.

Những phần đó cần được triển khai bằng HA manager, hạ tầng hoặc runbook. Các giải pháp phổ biến gồm Patroni, repmgr, pg_auto_failover, Pacemaker/Corosync và dịch vụ PostgreSQL được quản lý trên cloud. Mỗi giải pháp có cách quản lý leader, quorum, fencing và routing riêng; cần vận hành theo đúng thiết kế của công cụ.

## 4. Những loại sự cố có thể kích hoạt failover

Không phải mọi lỗi kết nối đều có nghĩa primary đã hỏng. Cần phân loại sự cố trước khi promote.

| Loại sự cố | Dấu hiệu | Hướng đánh giá |
| --- | --- | --- |
| PostgreSQL process crash | Port không phản hồi, process dừng | Kiểm tra process, logs và khả năng restart |
| Host failure | Máy chủ mất điện hoặc kernel panic | Xác nhận từ hạ tầng/out-of-band monitor |
| Storage failure | I/O error, filesystem read-only, corruption | Đánh giá khả năng ghi và tính toàn vẹn |
| Network partition | Một số node không liên lạc được với primary | Xác định primary còn phục vụ client hay không; cần quorum/fencing |
| Client path failure | Ứng dụng không tới được primary nhưng standby vẫn thấy primary | Kiểm tra routing, DNS, firewall, load balancer |
| Database overload | Kết nối chậm, query timeout | Đánh giá khả năng phục hồi, không tự động đồng nhất với node chết |
| Replication lag cao | Standby chậm hơn primary | Đánh giá RPO và candidate trước khi promote |
| WAL/archive problem | Standby không thể nhận hoặc replay WAL | Xác định có đủ WAL để tiếp tục hay cần rebuild |

### Lỗi mạng và lỗi primary là hai việc khác nhau

Nếu application network không thể kết nối primary nhưng primary vẫn hoạt động và nhận ghi từ client khác, promote standby có thể tạo split-brain. Đây là một trong các lý do quan trọng nhất để dùng nhiều health checks và fencing.

Một ping thất bại hoặc một lần TCP timeout không đủ làm bằng chứng duy nhất cho failover.

## 5. Tiêu chí kích hoạt failover

Một chính sách failover tốt xác định rõ:

- Điều kiện health check nào phải thất bại.
- Bao nhiêu lần kiểm tra liên tiếp mới xem là failure.
- Những nguồn kiểm tra nào phải đồng thuận.
- Primary có bị fence được không.
- Standby nào đủ điều kiện promote.
- Mức mất dữ liệu có thể chấp nhận.
- Ai hoặc hệ thống nào có quyền ra quyết định.
- Điều kiện nào yêu cầu operator phê duyệt thủ công.

### Các nhóm tiêu chí

**1. Primary health**

- PostgreSQL process có hoạt động không?
- Có thể thực hiện một query health check không?
- Có thể commit một transaction kiểm tra phù hợp không?
- Server có bị treo do storage hoặc resource exhaustion không?

**2. Failure confirmation**

- Có nhiều probe độc lập xác nhận lỗi không?
- HA manager có quorum không?
- Lỗi có chỉ nằm ở một network path không?
- Hệ thống hạ tầng có xác nhận host down không?

**3. Standby readiness**

- Standby có đang ở recovery và nhận WAL không?
- WAL receiver có hoạt động không?
- Standby có đủ WAL để bắt kịp không?
- Có lỗi replay hoặc storage không?
- Candidate có lag nằm trong RPO cho phép không?

**4. Safety**

- Primary cũ đã bị fence hoặc chắc chắn không thể nhận ghi chưa?
- Chỉ một candidate được quyền promote chưa?
- HA manager có bảo đảm single leader không?
- Các client có thể được chuyển sang endpoint mới không?

### Tiêu chí mẫu

Bảng dưới đây chỉ là ví dụ để bắt đầu thiết kế; không phải ngưỡng mặc định cho mọi production system.

| Điều kiện | Ví dụ chính sách | Hành động |
| --- | --- | --- |
| Primary SQL health check | Thất bại liên tiếp từ nhiều probe | Tiếp tục xác minh failure |
| Host health | Hạ tầng xác nhận node down | Đánh giá standby candidate |
| Network partition | Không có quorum hoặc chưa fence được primary | Chưa tự động promote |
| Standby state | Candidate không ở recovery ổn định hoặc có lỗi WAL | Loại candidate |
| Replication lag | Vượt RPO đã định | Cảnh báo, chọn candidate khác hoặc xin quyết định |
| Fencing | Primary cũ đã bị cô lập | Cho phép promotion theo policy |
| Candidate quorum | Chỉ một candidate được chọn | Thực hiện promotion |

Không nên copy ngưỡng thời gian hoặc số lần retry từ một hệ thống khác. Hãy đo thời gian khởi động, failover detection, network latency, replication lag và application reconnect của chính môi trường.

## 6. RPO và RTO quyết định tiêu chí kích hoạt

Hai chỉ số quan trọng của HA:

- **RPO (Recovery Point Objective)**: lượng dữ liệu tối đa có thể chấp nhận mất, thường đo bằng thời gian hoặc điểm transaction/WAL.
- **RTO (Recovery Time Objective)**: thời gian tối đa để khôi phục dịch vụ sau sự cố.

Ví dụ:

- RPO 0: mục tiêu không mất các transaction đã được xác nhận commit theo chính sách đồng bộ.
- RPO 30 giây: chấp nhận có thể mất tối đa khoảng 30 giây dữ liệu trong điều kiện giả định của kế hoạch.
- RTO 2 phút: mục tiêu khôi phục khả năng phục vụ trong hai phút.

RPO/RTO phải được định nghĩa cùng business owner. Một hệ thống thanh toán có thể cần RPO nghiêm ngặt hơn một hệ thống báo cáo có thể tái tạo dữ liệu.

### Các thành phần tạo nên RTO

\[
RTO = T_{detect} + T_{decide} + T_{fence} + T_{promote} + T_{route} + T_{reconnect}
\]

Đây là mô hình phân rã để lập kế hoạch. Các bước có thể chồng lấp một phần tùy kiến trúc, nhưng từng thành phần đều cần được đo khi diễn tập.

### RPO trong asynchronous replication

Với asynchronous streaming replication, primary không chờ standby xác nhận WAL trước khi commit thành công cho client. Nếu primary hỏng đột ngột, standby có thể thiếu WAL chứa những transaction vừa được xác nhận.

Mức mất dữ liệu phụ thuộc replication lag và vị trí WAL cuối cùng standby đã nhận/flush/replay. Không có bảo đảm RPO cố định chỉ từ việc bật streaming replication bất đồng bộ.

### RPO trong synchronous replication

Với synchronous replication, commit có thể chờ standby xác nhận WAL theo mức synchronous_commit và cấu hình synchronous_standby_names.

Điều này có thể giảm hoặc loại bỏ mất dữ liệu của các transaction đã được xác nhận, nhưng cần chọn đúng standby để promote. Nếu có nhiều standby và quorum, không phải mọi standby đều đã xác nhận cùng một commit.

RPO 0 là cam kết về điều kiện cấu hình và lựa chọn candidate, không phải kết quả tự động của việc đặt một tham số đơn lẻ.

## 7. Synchronous và asynchronous replication

### Asynchronous replication

Đây là chế độ mặc định phổ biến của streaming replication. Primary không phải đợi standby flush WAL trước khi trả commit cho client.

Ưu điểm:

- Primary ít bị ảnh hưởng bởi standby latency.
- Giao dịch không phải chờ network round trip tới standby.
- Primary vẫn có thể commit khi standby tạm thời chậm hoặc mất kết nối, miễn các điều kiện khác cho phép.

Đánh đổi:

- Standby có thể chưa nhận transaction cuối cùng khi primary hỏng.
- Failover có thể mất các transaction đã được client nhận commit thành công nhưng chưa tới candidate.
- Cần đo lag và xác định RPO chấp nhận được.

### Synchronous replication

Primary chờ xác nhận từ một hoặc nhiều standby được chọn làm synchronous standbys, theo cấu hình.

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

FIRST 1 chọn standby đầu tiên đủ điều kiện trong danh sách theo cơ chế ưu tiên. Có thể dùng quorum mode:

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
~~~

ANY 1 yêu cầu ít nhất một standby trong tập hợp xác nhận theo cơ chế synchronous replication.

### synchronous_commit có các mức khác nhau

| Giá trị | Hành vi khái quát |
| --- | --- |
| off | Không đợi local WAL flush trước khi báo commit; có thể mất transaction gần nhất khi crash |
| local | Đợi local WAL flush, không đợi standby |
| remote_write | Đợi standby ghi WAL tới hệ điều hành, chưa đồng nghĩa durable flush trên storage |
| on | Đợi synchronous standby xác nhận WAL flush theo cơ chế synchronous replication |
| remote_apply | Đợi synchronous standby replay WAL để transaction có thể được nhìn thấy ở standby |

remote_apply thường tăng độ trễ commit hơn on, nhưng có thể hữu ích khi ứng dụng cần transaction đã được replay trên standby trước khi commit trả về.

### Availability trade-off

Nếu không có synchronous standby đáp ứng yêu cầu, transaction commit có thể bị chờ. Synchronous replication tăng độ an toàn dữ liệu nhưng có thể giảm khả năng ghi liên tục khi standby/network gặp sự cố.

Thiết kế cần trả lời: hệ thống ưu tiên tiếp tục ghi hay giữ cam kết durability? Không có một cấu hình đúng cho mọi workload.

## 8. Chọn standby candidate dựa trên WAL/LSN

Không nên chọn candidate chỉ vì tên node, thứ tự danh sách hoặc trạng thái đang chạy. Cần đánh giá mức WAL mà standby đã nhận, flush và replay.

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication
ORDER BY replay_lsn DESC NULLS LAST;
~~~

Các trường:

- sent_lsn: vị trí WAL đã gửi tới standby.
- write_lsn: vị trí standby đã ghi WAL.
- flush_lsn: vị trí WAL standby đã flush.
- replay_lsn: vị trí standby đã replay.
- sync_state: trạng thái synchronous/asynchronous/quorum theo cấu hình và version.

### Received, flushed và replayed không giống nhau

- WAL đã gửi chưa chắc đã tới standby.
- WAL đã nhận chưa chắc đã flush xuống storage.
- WAL đã flush chưa chắc đã replay thành dữ liệu query-visible.
- Một standby có replay lag nhỏ nhưng chưa flush phần WAL cuối cùng vẫn cần được đánh giá theo mục tiêu durability.

Với failover, vị trí WAL durable trên candidate là thông tin quan trọng. Với switchover, thường đợi replay tới target LSN cuối cùng trước khi promote để database mới có thể phục vụ query ngay với dữ liệu đã catch up.

### Trên standby

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_time;
~~~

pg_last_xact_replay_timestamp() có thể cũ khi workload ít hoặc không có transaction mới; không dùng riêng timestamp này để kết luận standby lag. So sánh LSN và trạng thái receiver phù hợp hơn.

## 9. Kiểm tra WAL receiver trên standby

Xem kết nối upstream:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port,
    slot_name
FROM pg_stat_wal_receiver;
~~~

View này có một dòng khi WAL receiver đang hoạt động. Không có dòng không nhất thiết chứng minh data directory hỏng; có thể standby chưa kết nối hoặc receiver đang dừng.

Kết hợp với:

~~~sql
SELECT pg_is_in_recovery();
~~~

Nếu kết quả là true, server vẫn đang ở recovery/standby mode. Sau khi promote thành công, kết quả phải là false.

## 10. Quorum và nhiều standby

Khi có nhiều standby, HA manager cần chọn đúng một node để promote. Quorum giúp các thành viên trong cluster thống nhất ai được quyền trở thành leader.

Các thành phần có thể gồm:

- Primary.
- Hai hoặc nhiều standby.
- Distributed configuration store (DCS).
- Witness hoặc quorum voters.
- Fencing service.
- HA manager.

### Vì sao cần quorum?

Giả sử primary mất kết nối với standby nhưng vẫn nhận ghi từ một nhóm ứng dụng. Nếu nhóm standby tự promote mà không có cơ chế xác định leader duy nhất, hệ thống có thể có hai node nhận writes.

Quorum giúp tránh hai nhóm node cùng tin rằng mình là primary. Trong nhiều thiết kế, số voter lẻ giúp có đa số rõ ràng; cách bố trí cụ thể phụ thuộc HA manager và failure domains.

### Synchronous quorum không tự động là HA quorum

synchronous_standby_names = 'ANY 1 (...)' quyết định số standby cần xác nhận commit. Đây là cơ chế durability/commit acknowledgement, không thay thế quorum của HA manager để bầu leader và ngăn split-brain.

Hai loại quorum giải quyết hai vấn đề khác nhau.

## 11. Fencing và split-brain

Split-brain xảy ra khi hai node cùng được xem là primary và cùng nhận ghi. Hai lịch sử transaction có thể phân nhánh, làm việc hợp nhất dữ liệu rất khó hoặc không thể tự động.

### Fencing là gì?

Fencing bảo đảm primary cũ không thể tiếp tục ghi hoặc phục vụ như primary sau khi một standby được promote.

Các cách fencing có thể gồm:

- Power fencing/STONITH qua hạ tầng quản lý máy chủ.
- Dừng PostgreSQL service và ngăn tự khởi động lại.
- Cô lập network của node cũ.
- Thu hồi quyền truy cập storage theo kiến trúc shared-storage phù hợp.
- Dùng cloud API để stop/deallocate instance.
- HA manager điều phối lease/leader lock cùng fencing.

Cách fencing phải bảo đảm node cũ không thể tiếp tục nhận writes từ client hoặc một network partition khác.

### Không chỉ đổi DNS

Đổi DNS hoặc load balancer endpoint không fence primary cũ. Client có thể giữ connection cũ, một nhóm ứng dụng có thể dùng IP trực tiếp hoặc một hệ thống khác vẫn kết nối primary cũ.

Fencing và client routing là hai bước riêng.

### Khi không fence được primary cũ

Nếu không thể xác nhận primary cũ đã bị cô lập, tự động promote có thể tạo split-brain. Hệ thống cần chính sách rõ ràng: chờ xác minh, yêu cầu operator can thiệp hoặc dùng một cơ chế fencing/quorum khác đã được thiết kế trước.

Không nên bỏ qua bước safety chỉ để đạt RTO ngắn hơn.

## 12. Failover: quy trình tổng quát

Một quy trình failover an toàn có thể chia thành các bước:

1. **Detect**: phát hiện primary health check thất bại.
2. **Confirm**: xác minh sự cố bằng nhiều tín hiệu độc lập.
3. **Quorum**: HA manager xác định cluster có quyền ra quyết định.
4. **Fence**: ngăn primary cũ tiếp tục nhận ghi.
5. **Select**: chọn standby có dữ liệu mới nhất trong nhóm candidate hợp lệ.
6. **Promote**: đưa đúng một standby ra khỏi recovery.
7. **Validate**: xác nhận primary mới có thể nhận truy vấn ghi.
8. **Route**: chuyển endpoint và để ứng dụng reconnect.
9. **Rejoin**: đưa node cũ trở lại như standby sau khi xử lý timeline.
10. **Observe**: kiểm tra replication, backup, WAL và ứng dụng.

~~~mermaid
sequenceDiagram
    participant M as HA Manager
    participant P as Primary cũ
    participant S as Standby được chọn
    participant A as Application
    M->>P: Health checks thất bại
    M->>M: Xác nhận quorum và chọn candidate
    M->>P: Fence primary cũ
    M->>S: Promote
    S-->>M: Xác nhận primary mới
    M->>A: Chuyển endpoint
    A->>S: Reconnect và tiếp tục workload
    M->>P: Rebuild hoặc rewind thành standby
~~~

Không phải mọi bước đều có thể tự động trong mọi kiến trúc. Runbook phải xác định ai thực hiện, lệnh nào được dùng và điều kiện nào cho phép bước tiếp theo.

## 13. Promote standby bằng pg_ctl

Trên standby đã được chọn, có thể dùng:

~~~bash
pg_ctl promote -D /path/to/data_directory
~~~

Trên các phiên bản PostgreSQL hiện đại, có thể dùng SQL function:

~~~sql
SELECT pg_promote(true, 60);
~~~

Hai tham số trong ví dụ yêu cầu chờ promotion hoàn tất tối đa 60 giây và trả kết quả boolean. Kiểm tra signature của phiên bản đang dùng.

Promotion kết thúc recovery và node bắt đầu hoạt động như primary mới, tạo timeline mới. Promotion không tự fence primary cũ và cũng không tự chuyển ứng dụng sang node mới.

### Kiểm tra promotion

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả false cho biết server không còn ở recovery mode.

Có thể kiểm tra timeline và WAL position qua các hàm/view phù hợp version, đồng thời xác nhận server chấp nhận transaction ghi.

Không chạy lệnh promote trên nhiều standby cùng lúc. HA manager phải khóa lựa chọn candidate để chỉ một node được promote cho một sự kiện failover.

## 14. Kiểm tra primary mới sau promotion

Sau khi promote:

- pg_is_in_recovery() phải trả false.
- Server phải nhận được kết nối SQL.
- Có thể thực hiện một transaction ghi kiểm tra trong schema phù hợp.
- Timeline mới được tạo.
- WAL sender và replication configuration phù hợp cho các standby còn lại.
- Monitoring phải nhận diện đúng leader mới.
- Backup/WAL archiving tiếp tục hoạt động.

Kiểm tra:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_current_wal_lsn() AS current_wal_lsn;
~~~

Một transaction kiểm tra nên dùng bảng/đối tượng riêng đã được thiết kế cho health checks, hoặc một truy vấn chỉ đọc phù hợp. Tránh tạo dữ liệu rác vào bảng nghiệp vụ chỉ để xác nhận writable.

## 15. Chuyển ứng dụng sang primary mới

Sau promotion, các kết nối đang mở tới primary cũ có thể bị lỗi. Ứng dụng cần reconnect tới endpoint mới.

Các cách routing phổ biến:

- Virtual IP được chuyển sang node mới.
- Load balancer cập nhật backend.
- TCP proxy chuyển primary endpoint.
- DNS record đổi địa chỉ.
- Service discovery cập nhật leader address.
- HA-aware driver hoặc middleware tìm primary.

### Vì sao DNS đơn thuần có thể chưa đủ?

- DNS cache có thể giữ địa chỉ cũ.
- Connection pool giữ TCP sessions cũ.
- Ứng dụng có thể cache host/IP.
- Một số client retry tới endpoint cũ.
- Các service khác có thể kết nối trực tiếp bằng địa chỉ node.

Cần kiểm tra TTL, connection pool lifecycle và cơ chế retry. Stable endpoint thường giúp ứng dụng ít phụ thuộc node cụ thể.

### Retry an toàn

Sau failover, ứng dụng có thể không biết transaction cuối cùng đã commit hay chưa nếu connection đứt trong lúc commit response đang truyền về. Với thao tác không idempotent, retry mù có thể tạo giao dịch trùng.

Thiết kế ứng dụng nên dùng idempotency key, unique request identifier hoặc cơ chế xác minh transaction outcome trước khi retry các thao tác quan trọng.

## 16. Failover và transaction đang chạy

Khi primary bị crash hoặc bị fence:

- Transaction chưa commit có thể bị rollback.
- Transaction đã commit và được flush trên candidate có thể tồn tại.
- Transaction commit thành công ở primary nhưng chưa tới standby asynchronous có thể bị mất.
- Client có thể nhận timeout dù transaction thực tế đã commit.
- Connection pool có thể giữ trạng thái lỗi tới khi reset/reconnect.

Vì vậy, failover không chỉ là chuyển IP. Ứng dụng cần xử lý connection loss, transaction retry và kết quả không xác định (ambiguous commit outcome).

Đối với giao dịch tài chính hoặc thao tác tạo đơn hàng, idempotency là một phần của HA design.

## 17. Primary cũ quay trở lại

Sau failover, primary cũ có thể khởi động lại và vẫn mang timeline cũ. Không được cho nó nhận writes hoặc kết nối vào ứng dụng như primary.

Các hành động cần làm:

1. Giữ node cũ bị cô lập khỏi client writes.
2. Xác định timeline và trạng thái dữ liệu.
3. Xác định node mới là nguồn sự thật.
4. Đánh giá có thể dùng pg_rewind hay cần base backup mới.
5. Cấu hình node cũ làm standby của primary mới.
6. Bắt đầu streaming và xác minh catch-up.
7. Chỉ đưa node vào topology sau khi kiểm tra hoàn tất.

Không khởi động lại node cũ với vai trò primary chỉ vì PostgreSQL process chạy thành công. Nó có thể chứa transaction branch không còn thuộc lịch sử cluster hiện tại.

## 18. Rejoin bằng pg_rewind

pg_rewind có thể đồng bộ một data directory đã phân nhánh trở lại cùng timeline với một source cluster, bằng cách sao chép các block đã thay đổi thay vì phải copy toàn bộ cluster.

Dùng khi:

- Node cũ từng là primary và đã diverge.
- Source mới đang hoạt động và có WAL/history cần thiết.
- Hai cluster có chung lịch sử ancestor phù hợp.
- Các điều kiện kỹ thuật của pg_rewind được đáp ứng.

### Điều kiện quan trọng

Target cần có data checksums được bật khi initdb hoặc wal_log_hints=on trong giai đoạn cần thiết; full_page_writes phải được bật. Target phải được shutdown sạch trước khi chạy pg_rewind. Source và target cần cùng major version và có lịch sử WAL/timeline phù hợp.

Kiểm tra tài liệu pg_rewind đúng phiên bản trước khi dùng; nếu thiếu WAL cần thiết hoặc không đáp ứng preconditions, dùng base backup mới.

### Ví dụ

Dừng node cũ, sau đó chạy trên host của node đó:

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/data \
  --source-server="host=new-primary.example.net port=5432 user=rewind_user dbname=postgres" \
  --progress \
  --write-recovery-conf
~~~

Ví dụ giả định có user/quyền phù hợp và các file cấu hình/credential đã được chuẩn bị an toàn. --write-recovery-conf yêu cầu công cụ ghi cấu hình cần thiết để target khởi động lại như standby theo hỗ trợ của phiên bản.

Sau rewind, kiểm tra primary_conninfo, slot, TLS, standby.signal và các cấu hình standby khác trước khi khởi động. Không đưa password rõ vào command history; dùng service file hoặc credential mechanism được bảo vệ.

### Khi nào cần base backup mới?

- pg_rewind không đáp ứng điều kiện.
- WAL cần thiết đã bị xóa/recycle.
- Data directory hỏng hoặc không đáng tin cậy.
- Major version hoặc timeline không tương thích.
- Rewind thất bại và không thể chứng minh target nhất quán.

Tạo standby mới bằng pg_basebackup từ primary hiện tại thường là cách rõ ràng hơn khi có đủ thời gian và network/storage.

## 19. Switchover: quy trình có kế hoạch

Switchover có thể giảm tối đa mất dữ liệu vì primary cũ còn hoạt động để phối hợp.

### Bước 1: Chọn standby

Xác nhận candidate:

- Đang streaming.
- Không có lỗi replay.
- Có đủ disk và WAL.
- Có cấu hình phù hợp để làm primary.
- Không có replication conflict bất thường.
- Có thể nhận writes sau promotion.

### Bước 2: Dừng hoặc drain writes

Chuyển ứng dụng sang maintenance/read-only mode theo thiết kế. Dừng producers, background workers hoặc các tác vụ ghi khác. Chờ các transaction đang chạy kết thúc.

Không chỉ dừng traffic web; cần xác định mọi writer như batch jobs, ETL, scheduler và service nội bộ.

### Bước 3: Ghi nhận WAL target trên primary cũ

Trên primary:

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

Lưu lại LSN cuối cùng sau khi writers đã dừng và transaction cần thiết đã hoàn tất.

### Bước 4: Chờ standby replay tới target

Trên standby:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

Chờ cho tới khi replay LSN bằng hoặc vượt target LSN đã ghi nhận. So sánh LSN bằng các hàm PostgreSQL hoặc công cụ orchestration, không so sánh chuỗi theo thứ tự từ điển.

### Bước 5: Dừng/fence primary cũ

Dừng PostgreSQL một cách có kiểm soát hoặc fence node cũ để nó không thể nhận writes. Trong switchover, có thể dùng shutdown fast sau khi writers đã được drain, rồi xác nhận standby đã nhận/replay WAL cuối cùng.

### Bước 6: Promote standby

~~~sql
SELECT pg_promote(true, 60);
~~~

Hoặc dùng pg_ctl promote theo môi trường.

### Bước 7: Kiểm tra và chuyển endpoint

Xác nhận pg_is_in_recovery() trả false, kiểm tra query ghi, sau đó cập nhật routing và cho ứng dụng mở lại writes.

### Bước 8: Rejoin primary cũ

Đưa node cũ về làm standby bằng pg_rewind hoặc base backup mới. Xác minh streaming và replication lag trước khi kết thúc maintenance.

## 20. Switchover có bảo đảm không mất dữ liệu không?

Có thể đạt RPO 0 cho các transaction đã commit nếu:

- Tất cả writers đã dừng và transaction cần thiết đã hoàn tất.
- LSN cuối cùng trên primary đã được ghi nhận.
- Standby đã replay tới hoặc vượt LSN đó.
- Không có writer khác tiếp tục tạo WAL sau checkpoint.
- Primary cũ được dừng/fence trước khi standby nhận writes.
- Không có lỗi storage hoặc dữ liệu ẩn ngoài replication path.

Nếu chỉ đợi replication lag hiển thị bằng 0 mà không drain writers và không khóa thời điểm cuối, primary vẫn có thể phát thêm WAL ngay sau lần kiểm tra. Vì vậy, switchover cần một barrier rõ ràng giữa lần ghi cuối cùng và promotion.

## 21. Failback sau khi sửa primary cũ

Failback là một switchover mới. Trước khi chuyển lại:

1. Xác minh node cũ đã rejoin thành standby.
2. Xác minh nó streaming và replay ổn định.
3. Đợi lag về ngưỡng yêu cầu.
4. Đánh giá capacity và health của cả hai node.
5. Drain writes.
6. Đợi standby cũ replay tới target LSN.
7. Dừng/fence primary hiện tại.
8. Promote node được chọn.
9. Chuyển endpoint.
10. Rejoin node còn lại.

Không nên failback ngay khi máy chủ cũ vừa sửa xong. Primary mới có thể đã chạy workload ổn định và node cũ có thể cần thời gian catch-up hoặc rebuild.

## 22. Vai trò của HA manager

HA manager điều phối quyết định và trạng thái node. Các khả năng thường cần:

- Health checks.
- Leader election.
- Quorum/DCS.
- Fencing integration.
- Candidate selection.
- Promotion.
- Replication configuration.
- Service endpoint updates.
- Rejoin/rebuild.
- Monitoring và event logs.

Các công cụ như Patroni, repmgr, pg_auto_failover hoặc Pacemaker có mô hình triển khai và mức tự động hóa khác nhau. Không nên chỉ cài công cụ mà bỏ qua việc kiểm thử DCS, fencing, DNS/VIP, slot management và behavior khi network partition.

### HA manager không thay backup

Replication có thể truyền nhầm lệnh DROP TABLE hoặc UPDATE sai sang standby. Standby không phải bản backup lịch sử độc lập. Cần base backups, WAL archives, retention và test restore riêng.

## 23. Network partition và quyết định promote

Network partition là tình huống nguy hiểm vì primary có thể còn hoạt động trong khi một phần cluster không nhìn thấy nó.

Ví dụ:

- Application subnet vẫn tới primary.
- Standby subnet không tới primary.
- HA manager mất kết nối tới một số voter.
- Một nhóm node tin primary đã chết, nhóm khác vẫn thấy primary.

Nếu standby promote trong khi primary vẫn nhận ghi, split-brain xảy ra.

### Chính sách an toàn

- Dùng quorum/leader lease theo HA manager.
- Dùng fencing độc lập với network path bị lỗi.
- Không dựa trên một ping hoặc một monitor duy nhất.
- Giới hạn quyền promote cho một control plane.
- Đảm bảo endpoint không thể trỏ đồng thời tới hai primary.
- Có manual override và audit cho tình huống bất thường.

Trong hệ thống không có fencing đáng tin cậy, failover tự động có thể nguy hiểm hơn việc chờ operator xác minh.

## 24. Replication slots và WAL sau failover

Standby mới trở thành primary có thể cần phục vụ các standby còn lại. Cần kiểm tra:

- max_wal_senders.
- max_replication_slots.
- Physical replication slots.
- Logical replication slots.
- WAL archive.
- wal_keep_size.
- max_slot_wal_keep_size.
- Standby primary_slot_name.
- Slot synchronization/failover support của PostgreSQL version và HA manager.

Một số cấu hình có thể đồng bộ hoặc failover slots theo version; không giả định mọi slot tự xuất hiện ở primary mới. Slot thiếu có thể khiến consumer không tiếp tục được hoặc phải tạo lại/reseed.

### WAL retention

Nếu standby mất kết nối lâu và slot giữ WAL, disk có thể đầy. Nếu không có slot hoặc WAL bị recycle trước khi standby quay lại, standby có thể cần rebuild từ base backup.

Failover runbook cần kiểm tra WAL availability cho từng consumer, không chỉ trạng thái primary.

## 25. Timeline sau promotion

Khi promote standby, PostgreSQL bắt đầu một timeline mới. Timeline giúp phân biệt các nhánh lịch sử WAL.

Sau failover:

- Primary mới ghi WAL trên timeline mới.
- Node cũ có thể đã tạo WAL trên timeline trước đó.
- Không thể đơn giản nối hai nhánh WAL như thể chúng là một lịch sử duy nhất.
- Rejoin cần rewind hoặc base backup theo timeline mới.
- Archive cần giữ timeline history files để khôi phục và phân tích.

Đảm bảo WAL archive chứa các timeline history files và quy trình restore có thể tìm đúng WAL cần thiết.

## 26. Backup và PITR sau failover

Sau khi promote:

- Xác nhận WAL archiving hoạt động trên primary mới.
- Kiểm tra backup schedule.
- Xác định backup chain nào thuộc timeline hiện tại.
- Ghi nhận mốc failover và timeline mới.
- Kiểm tra replication slots và archive destination.
- Chạy base backup mới theo policy.

Không xóa backup cũ ngay khi failover hoàn tất. Backup và WAL ở timeline cũ vẫn có thể cần cho điều tra hoặc recovery point trước sự cố.

Nếu có PITR, kiểm tra recovery target theo timeline và WAL history. Logical/physical replication không thay thế quy trình backup có thể phục hồi độc lập.

## 27. Failover với synchronous replication: chọn đúng node

Khi cấu hình synchronous replication, candidate cần được đánh giá theo nhóm standby thực sự xác nhận commit.

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Trong chế độ FIRST, một standby có thể đang ở trạng thái synchronous trong khi standby khác asynchronous. Promote standby đang lag có thể làm mất transaction đã được xác nhận bởi standby đồng bộ.

Với quorum:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Mỗi commit cần hai standby trong tập hợp xác nhận. Không nhất thiết cả ba node đều có mọi transaction đã được xác nhận. Candidate selection cần xem LSN durable thực tế và quorum semantics, không chỉ thấy sync_state có giá trị tương tự.

Đối với yêu cầu RPO 0, phải chứng minh candidate được chọn chứa mọi commit mà primary đã xác nhận theo chính sách synchronous commit. Nếu không thể chứng minh, cần quyết định dựa trên RPO chấp nhận được và xin phê duyệt khi cần.

## 28. Failover với asynchronous replication: ước lượng dữ liệu có thể mất

Trên primary, có thể theo dõi:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;
~~~

Nếu primary đã mất hoàn toàn, view này không còn truy vấn được trên primary. Dùng số liệu monitoring gần nhất, standby receive/replay positions và WAL archive để ước lượng.

### Không chuyển byte lag trực tiếp thành thời gian mất dữ liệu

Một byte WAL không tương ứng với một khoảng thời gian cố định. Workload có thể phát sinh WAL rất khác nhau theo thời điểm. Muốn ước lượng RPO theo thời gian, cần đo WAL generation rate và replication lag theo lịch sử, nhưng vẫn phải ghi nhận đây là ước lượng.

Candidate có replay LSN cao nhất thường là điểm khởi đầu hợp lý, nhưng cần xem WAL đã flush chưa, có lỗi storage không và candidate có cùng timeline/ancestor không.

## 29. Chuyển endpoint và connection pool

Một kiến trúc HA tốt nên dùng endpoint ổn định:

- DNS alias.
- VIP.
- Load balancer.
- TCP proxy.
- Service discovery record.
- Connection routing layer hiểu primary role.

Ứng dụng cần:

- Reconnect khi connection bị reset.
- Loại bỏ pooled connections tới node cũ.
- Retry với backoff và jitter.
- Xử lý transaction outcome không xác định.
- Không gửi writes tới read-only standby.
- Phát hiện primary mới trước khi mở traffic.

Nếu có read replicas, tách routing đọc và ghi. Sau failover, một số standby cũ có thể chưa được reconfigure để follow primary mới; không gửi query tới chúng cho tới khi topology xác nhận.

## 30. Health checks và tiêu chí sẵn sàng

Health check có thể có nhiều cấp:

| Cấp | Kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Process | PostgreSQL process tồn tại | Server process đang chạy |
| Port | TCP connect thành công | Listener có phản hồi |
| SQL | Query health check thành công | Database xử lý được query |
| Readiness | Kiểm tra role và recovery state | Node có đúng vai trò để nhận traffic |
| Write readiness | Transaction kiểm tra có thể commit | Primary có thể phục vụ writes |
| Replication | WAL receiver/sender và lag | Standby đang theo kịp |
| Application | End-to-end request | Dịch vụ thực sự hoạt động |

Một process còn chạy không có nghĩa database khỏe. Một SQL query thành công trên standby cũng không có nghĩa nó có thể nhận writes.

### Health check phải nhận biết role

Ứng dụng ghi cần endpoint trỏ tới primary. Health check có thể kiểm tra pg_is_in_recovery() để phân biệt primary/standby, kết hợp HA manager state và endpoint routing.

Không để load balancer phân phối write traffic ngẫu nhiên tới mọi node PostgreSQL.

## 31. Monitoring cần có cho failover

Các chỉ số quan trọng:

- Primary role và standby role.
- PostgreSQL process/SQL health.
- pg_stat_replication state.
- pg_stat_wal_receiver status.
- Sent/write/flush/replay LSN.
- Replication lag bytes/time.
- WAL generation rate.
- Replication slot active/inactive.
- Disk free space và WAL directory size.
- DCS/quorum/leader lease.
- Fencing status.
- Client connection errors.
- Application transaction errors.
- Failover duration và recovery time.
- Timeline ID và archive health.

### Trên primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

### Trên standby

~~~sql
SELECT
    status,
    sender_host,
    sender_port,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

### Kiểm tra role

~~~sql
SELECT pg_is_in_recovery();
~~~

Các query cần được điều chỉnh theo version và quyền monitoring. Ghi nhận cả giá trị hiện tại lẫn xu hướng, vì một lần lấy mẫu không đủ để quyết định failover.

## 32. Runbook cho failover tự động

Một runbook tự động nên mô tả các state rõ ràng:

1. HEALTHY: primary đang phục vụ, standby streaming.
2. SUSPECT: một hoặc nhiều health checks thất bại.
3. CONFIRMED_FAILURE: đủ tín hiệu xác nhận primary không phục vụ.
4. FENCING: ngăn primary cũ nhận ghi.
5. CANDIDATE_SELECTED: một standby được chọn.
6. PROMOTING: thực hiện promote.
7. PRIMARY_VALIDATED: node mới sẵn sàng nhận ghi.
8. ROUTING_UPDATED: client endpoint chuyển thành công.
9. REJOINING: node cũ được rewind/rebuild.
10. STABLE: topology ổn định và monitoring xanh.

Mỗi state cần timeout, retry policy, log và điều kiện dừng. Nếu fencing thất bại, không tự chuyển sang promote như thể bước đó đã thành công.

## 33. Runbook cho switchover thủ công

Một checklist thực tế:

**Trước khi chuyển**

- Xác nhận maintenance window.
- Thông báo ứng dụng và dừng writer jobs.
- Kiểm tra primary/standby health.
- Kiểm tra lag và WAL archive.
- Kiểm tra backup mới nhất.
- Xác nhận routing và rollback plan.
- Xác nhận candidate có đủ tài nguyên.

**Trong khi chuyển**

- Drain writes.
- Ghi target LSN.
- Đợi standby replay target.
- Dừng/fence primary cũ.
- Promote standby.
- Xác minh pg_is_in_recovery() = false.
- Chuyển endpoint.
- Mở writes và theo dõi lỗi.

**Sau khi chuyển**

- Rejoin node cũ.
- Kiểm tra replication slots.
- Xác minh backup/WAL archiving.
- Kiểm tra application health.
- Ghi lại thời gian từng bước và RTO thực tế.

## 34. Các tình huống cụ thể và quyết định

### Primary process crash, standby healthy

- Xác nhận process/server thực sự down.
- Kiểm tra candidate và replication lag.
- Fence/restart policy bảo đảm node cũ không nhận writes.
- Promote candidate.
- Chuyển endpoint và giám sát.

### Primary mất mạng nhưng host còn chạy

- Xác định có phải network partition.
- Kiểm tra các path khác tới primary.
- Dùng quorum và fencing.
- Không promote chỉ vì một client subnet không kết nối được.

### Standby lag lớn

- So sánh các standby.
- Kiểm tra WAL receive/flush/replay.
- Đánh giá RPO thực tế.
- Nếu không candidate nào đáp ứng RPO, cần quyết định có chủ đích và ghi nhận mức mất dữ liệu tiềm tàng.

### Primary storage corruption

- Không tiếp tục ghi vào storage không đáng tin cậy.
- Fence primary.
- Chọn standby có dữ liệu tốt.
- Promote và xác minh.
- Giữ bản lỗi để điều tra theo policy, không xóa evidence trước khi cần.

### Không còn standby

- Khôi phục primary từ backup/WAL theo recovery plan.
- Không có promotion target.
- RTO sẽ phụ thuộc thời gian restore/PITR.
- Sau phục hồi, tái tạo standby và kiểm tra HA topology.

### Synchronous standby không phản hồi

- Commit có thể bị chờ tùy synchronous_commit.
- Kiểm tra synchronous_standby_names và trạng thái node.
- Chỉ thay đổi policy durability khi có phê duyệt.
- Không hạ sync policy trong incident mà không đánh giá RPO.

## 35. Test failover và switchover

HA chưa được kiểm chứng cho tới khi diễn tập.

Các bài test nên gồm:

- Dừng PostgreSQL primary có kiểm soát.
- Kill process trong môi trường thử nghiệm.
- Mô phỏng mất network giữa primary và standby.
- Mô phỏng mất network giữa application và primary.
- Mô phỏng standby lag.
- Mô phỏng replication slot inactive.
- Mô phỏng WAL disk pressure.
- Test fencing.
- Test promotion và endpoint switch.
- Test client reconnect.
- Test transaction retry/idempotency.
- Test rejoin bằng pg_rewind.
- Test rebuild bằng pg_basebackup.
- Test switchover trở lại sau khi topology ổn định.

Không thực hiện fault injection trên production nếu chưa có change plan, phạm vi và rollback được phê duyệt.

### Đo thời gian thực tế

Ghi lại:

- Thời điểm sự cố bắt đầu.
- Thời điểm alert phát ra.
- Thời điểm failure được xác nhận.
- Thời điểm fencing hoàn tất.
- Thời điểm promotion hoàn tất.
- Thời điểm endpoint chuyển.
- Thời điểm ứng dụng phục vụ ghi bình thường.
- Dữ liệu/transaction bị mất hoặc cần reconcile.

Dùng số đo này để điều chỉnh RTO/RPO và alert thresholds.

## 36. Bảo vệ backup và kiểm soát thay đổi

Failover không phải backup. Một thao tác sai được replicate cũng có thể xuất hiện trên standby.

Cần duy trì:

- Physical base backups.
- WAL archive và PITR.
- Logical backups cho use cases chọn lọc.
- Backup cấu hình PostgreSQL và HA manager.
- Inventory certificates/secrets.
- Runbook và change history.
- Restore tests định kỳ.

Mọi thay đổi synchronous_standby_names, replication slots, HBA, TLS, routing và fencing policy đều có thể ảnh hưởng HA. Đưa chúng vào change management và kiểm thử trước production.

## 37. Những sai lầm thường gặp

1. **Promote standby chỉ vì application không kết nối được primary**, dù primary vẫn có thể nhận ghi từ nơi khác.
2. **Bỏ qua fencing**, dẫn tới primary cũ và primary mới cùng hoạt động.
3. **Chọn standby chỉ theo tên hoặc thứ tự node**, không so sánh WAL/LSN và health.
4. **Nhầm sent_lsn với replay_lsn**, đánh giá sai dữ liệu đã sẵn sàng.
5. **Coi asynchronous replication bảo đảm RPO 0**, dù primary không chờ standby xác nhận commit.
6. **Nghĩ synchronous replication tự bảo đảm mọi standby đều có transaction cuối**, trong khi cấu hình FIRST/ANY có selection/quorum semantics.
7. **Không hiểu synchronous_commit**, dẫn tới diễn giải sai remote_write, on và remote_apply.
8. **Dùng synchronous standby mà không tính availability trade-off**, khiến commit bị block khi standby/network lỗi.
9. **Đổi DNS nhưng không xử lý connection pool**, khiến ứng dụng tiếp tục dùng session tới node cũ.
10. **Không xử lý transaction outcome mơ hồ**, khiến retry tạo giao dịch trùng.
11. **Khởi động primary cũ lại như primary**, tạo timeline phân nhánh.
12. **Coi pg_rewind luôn khả dụng**, dù thiếu WAL hoặc không đáp ứng preconditions.
13. **Không kiểm tra replication slots sau promotion**, khiến standby khác không tiếp tục được.
14. **Không kiểm tra WAL archive/timeline history**, làm PITR và rejoin khó khăn.
15. **Nhầm synchronous quorum với HA leader-election quorum**, không ngăn được split-brain.
16. **Tự động failover dựa trên một probe**, dễ kích hoạt sai khi network chập chờn.
17. **Không kiểm tra endpoint write readiness**, gửi writes tới standby read-only.
18. **Không diễn tập failover**, không biết RTO thực tế và các bước thủ công bị thiếu.
19. **Xóa backup cũ ngay sau promotion**, làm mất khả năng điều tra hoặc phục hồi.
20. **Failback quá sớm**, trước khi node cũ rejoin và catch up.
21. **Dùng replication thay backup**, không có điểm khôi phục độc lập.
22. **Không theo dõi WAL disk/slot retention**, làm primary mới đầy disk sau khi chuyển vai trò.

## 38. Bài tập thực hành có đáp án

### Bài 1. Failover là gì?

**Đáp án:** Chuyển dịch vụ sang standby do primary gặp sự cố hoặc không còn an toàn để phục vụ.

### Bài 2. Switchover là gì?

**Đáp án:** Chuyển vai trò primary/standby có kế hoạch khi có thể phối hợp và đồng bộ trước.

### Bài 3. Failback là gì?

**Đáp án:** Chuyển vai trò trở lại node/site ban đầu sau khi node đó đã được rejoin và kiểm tra.

### Bài 4. RPO đo điều gì?

**Đáp án:** Mức dữ liệu có thể chấp nhận mất trong một sự cố.

### Bài 5. RTO đo điều gì?

**Đáp án:** Thời gian mục tiêu để khôi phục dịch vụ.

### Bài 6. Vì sao ping thất bại không đủ kích hoạt failover?

**Đáp án:** Có thể chỉ một network path bị lỗi trong khi primary vẫn nhận ghi từ client khác.

### Bài 7. Fencing có tác dụng gì?

**Đáp án:** Ngăn primary cũ tiếp tục nhận writes sau khi standby mới được promote.

### Bài 8. Split-brain là gì?

**Đáp án:** Hai node cùng được xem là primary và cùng nhận ghi, tạo các lịch sử dữ liệu phân nhánh.

### Bài 9. Promote standby bằng SQL function nào?

~~~sql
SELECT pg_promote(true, 60);
~~~

**Đáp án:** pg_promote yêu cầu standby rời recovery và trở thành primary; tham số yêu cầu chờ tối đa 60 giây.

### Bài 10. Kiểm tra node còn ở recovery không?

~~~sql
SELECT pg_is_in_recovery();
~~~

**Đáp án:** true là đang recovery/standby; false là không còn ở recovery.

### Bài 11. Asynchronous replication có bảo đảm không mất transaction cuối không?

**Đáp án:** Không. Primary có thể xác nhận commit trước khi standby nhận/flush WAL.

### Bài 12. synchronous_commit=on chờ điều gì?

**Đáp án:** Local WAL flush và xác nhận flush từ synchronous standby theo cơ chế cấu hình.

### Bài 13. remote_apply khác on thế nào?

**Đáp án:** remote_apply đợi standby replay transaction; on đợi standby flush WAL.

### Bài 14. ANY 1 trong synchronous_standby_names nghĩa gì?

**Đáp án:** Ít nhất một standby trong tập quorum cần xác nhận theo cấu hình.

### Bài 15. Synchronous quorum có thay HA manager quorum không?

**Đáp án:** Không. Một cơ chế xác nhận commit durability, cơ chế kia giúp quyết định leader và tránh split-brain.

### Bài 16. Trên primary, view nào xem standby LSN?

**Đáp án:** pg_stat_replication.

### Bài 17. Trên standby, view nào xem WAL receiver?

**Đáp án:** pg_stat_wal_receiver.

### Bài 18. Vì sao không chọn candidate chỉ theo replay lag timestamp?

**Đáp án:** Timestamp có thể cũ khi workload idle; cần xem LSN, flush state, timeline và health.

### Bài 19. Sau promotion, primary cũ có thể khởi động lại như primary không?

**Đáp án:** Không. Phải fence và rejoin theo timeline mới bằng pg_rewind hoặc base backup.

### Bài 20. pg_rewind dùng để làm gì?

**Đáp án:** Đồng bộ target đã diverge với source bằng cách sao chép các block thay đổi, khi đủ điều kiện.

### Bài 21. Khi nào cần base backup mới thay pg_rewind?

**Đáp án:** Khi thiếu WAL, không đáp ứng preconditions, timeline/version không phù hợp hoặc data directory không đáng tin cậy.

### Bài 22. Switchover cần drain writes để làm gì?

**Đáp án:** Tạo một barrier cuối cùng, tránh primary phát thêm WAL sau khi đã kiểm tra standby catch-up.

### Bài 23. Vì sao đổi DNS chưa đủ?

**Đáp án:** DNS cache và connection pools có thể giữ địa chỉ/session cũ; cần routing và reconnect behavior rõ ràng.

### Bài 24. Client timeout khi COMMIT có nghĩa transaction rollback không?

**Đáp án:** Không nhất thiết. Commit có thể đã thành công nhưng response bị mất; ứng dụng cần idempotency hoặc xác minh outcome.

### Bài 25. Logical replication slot có tự động theo primary mới không?

**Đáp án:** Không được giả định. Cần kiểm tra hỗ trợ slot failover/synchronization của version và HA manager.

### Bài 26. Một standby duy nhất có đủ HA không?

**Đáp án:** Có thể cung cấp một candidate nhưng còn phụ thuộc failure domain, quorum, fencing và khả năng node đó sẵn sàng; không có redundancy nếu standby cũng hỏng.

### Bài 27. Vì sao failover phải kiểm tra WAL archive?

**Đáp án:** Để bảo đảm khả năng tiếp tục standby/recovery và PITR trên timeline phù hợp.

### Bài 28. Khi nào nên trì hoãn tự động promotion?

**Đáp án:** Khi failure chưa được xác nhận, không có quorum, không fence được primary cũ hoặc không có candidate đáp ứng policy an toàn.

### Bài 29. Một switchover an toàn cần xác minh điều gì trước promote?

**Đáp án:** Writers đã drain, target LSN đã được ghi nhận, standby replay tới target và primary cũ đã dừng/fence.

### Bài 30. Khi nào được coi failover hoàn tất?

**Đáp án:** Primary mới đã được xác minh writable, endpoint và ứng dụng đã reconnect, monitoring/backup/replication được khôi phục và node cũ có kế hoạch rejoin.

## 39. Checklist quyết định failover

- [ ] Primary failure được xác nhận bằng nhiều health checks.
- [ ] Phân biệt lỗi primary với lỗi client network path.
- [ ] HA manager có quorum hoặc cơ chế quyết định leader rõ ràng.
- [ ] Primary cũ đã được fence.
- [ ] Có đúng một standby candidate được chọn.
- [ ] Candidate ở trạng thái healthy và có đủ WAL.
- [ ] Đã xem received/write/flush/replay LSN.
- [ ] Đánh giá RPO theo sync mode và candidate thực tế.
- [ ] Có quyết định rõ nếu RPO mục tiêu không đạt.
- [ ] Promote đúng một standby.
- [ ] Xác nhận pg_is_in_recovery() = false.
- [ ] Kiểm tra primary mới nhận được write.
- [ ] Chuyển endpoint và reset connection pools.
- [ ] Ứng dụng xử lý retry/idempotency.
- [ ] Kiểm tra WAL archiving và replication slots.
- [ ] Lập kế hoạch rejoin node cũ.
- [ ] Kiểm tra monitoring và alert sau chuyển đổi.
- [ ] Ghi nhận timeline, thời gian và dữ liệu có thể mất.

## 40. Checklist switchover

- [ ] Có maintenance window và rollback plan.
- [ ] Chọn standby khỏe, đủ capacity.
- [ ] Kiểm tra replication lag và WAL availability.
- [ ] Dừng/drain mọi writers và background jobs.
- [ ] Chờ các transaction cần thiết kết thúc.
- [ ] Ghi nhận primary flush LSN cuối cùng.
- [ ] Chờ standby replay tới target LSN.
- [ ] Dừng hoặc fence primary cũ.
- [ ] Promote standby.
- [ ] Xác minh role và write readiness.
- [ ] Chuyển endpoint.
- [ ] Mở lại writers và theo dõi ứng dụng.
- [ ] Rejoin primary cũ bằng rewind/rebuild.
- [ ] Xác minh backup, slots, WAL và replication.
- [ ] Ghi RTO thực tế và kết quả diễn tập.

## 41. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical standby, streaming và promotion.
- [Failover](https://www.postgresql.org/docs/current/warm-standby-failover.html) — promote standby và các vấn đề khi failover.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous_standby_names và commit behavior.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html) — promote, stop và quản lý server.
- [pg_promote](https://www.postgresql.org/docs/current/functions-admin.html) — SQL function điều khiển promotion.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html) — đưa node đã diverge trở lại cùng timeline.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo standby từ physical base backup.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL senders, slots và synchronous replication settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication và pg_stat_wal_receiver.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL archives và timeline recovery.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — WAL retention và slot lifecycle.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Promotion, pg_rewind, synchronous replication, slot failover và monitoring details có thể thay đổi theo major version; xác nhận tài liệu đúng phiên bản server/client và HA manager trước khi áp dụng.

## 42. Tổng kết

**Failover phục hồi dịch vụ sau sự cố; switchover chuyển vai trò có kế hoạch; failback đưa node cũ trở lại topology sau khi được rejoin an toàn.** Cả ba cần kiểm soát dữ liệu, leader identity và client routing.

1. **Không kích hoạt failover chỉ từ một dấu hiệu mất kết nối.** Xác minh primary failure bằng nhiều tín hiệu và quorum.
2. **Fencing là điều kiện an toàn quan trọng.** Không để primary cũ tiếp tục nhận ghi sau promotion.
3. **Chọn candidate theo WAL/LSN và health**, không chỉ theo tên node hoặc timestamp lag.
4. **Asynchronous replication có thể mất các transaction chưa tới standby.** RPO phụ thuộc lag tại thời điểm sự cố.
5. **Synchronous replication giảm rủi ro mất commit đã xác nhận**, nhưng cần chọn đúng synchronous/quorum candidate và chấp nhận trade-off availability.
6. **pg_promote hoặc pg_ctl promote chuyển standby thành primary**, nhưng không tự chuyển endpoint hoặc fence node cũ.
7. **Ứng dụng cần reconnect và xử lý transaction outcome mơ hồ**, đặc biệt với thao tác không idempotent.
8. **Primary cũ phải rejoin theo timeline mới** bằng pg_rewind nếu đủ điều kiện hoặc base backup mới.
9. **Switchover cần drain writes và đợi standby replay target LSN** trước khi promote.
10. **HA manager, quorum, fencing và routing bổ sung cho streaming replication**, tạo thành hệ thống HA hoàn chỉnh.
11. **Backup/PITR vẫn cần thiết.** Standby không thay thế bản backup độc lập.
12. **Diễn tập và đo RPO/RTO thực tế** để runbook có thể thực hiện được trong sự cố.

Một hệ thống HA chỉ đáng tin khi đội vận hành biết chính xác lúc nào được phép promote, làm sao ngăn primary cũ tiếp tục ghi và cách đưa toàn bộ ứng dụng trở lại trạng thái phục vụ ổn định.
