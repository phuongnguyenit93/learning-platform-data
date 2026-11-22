# Unclean leader election và đánh đổi mất dữ liệu

Kafka dùng replication để giữ nhiều bản sao của partition trên các broker. Khi leader của partition gặp sự cố, controller cần chọn một replica khác làm leader để producer và consumer tiếp tục hoạt động. Lựa chọn an toàn nhất là một replica đang thuộc ISR (In-Sync Replicas), vì replica này được xem là đã theo kịp leader theo tiêu chí đồng bộ của Kafka.

Nếu không còn replica thuộc ISR nào có thể trở thành leader, Kafka phải đối mặt với một quyết định: giữ partition offline để chờ replica đồng bộ quay lại, hay cho phép một replica đã tụt hậu trở thành leader để khôi phục khả năng phục vụ. Cơ chế thứ hai được gọi là **unclean leader election**. Nó có thể giúp hệ thống hoạt động trở lại nhanh hơn, nhưng có nguy cơ làm mất những record đã tồn tại trên leader cũ mà replica được chọn không có.

Đây là đánh đổi giữa availability và durability. Cấu hình phù hợp phụ thuộc mức độ quan trọng của dữ liệu, khả năng chấp nhận mất sự kiện và yêu cầu thời gian khôi phục của từng topic.

## 1. Leader, follower và ISR

Mỗi partition có một replica leader và có thể có nhiều follower replica. Producer gửi record đến leader. Follower sao chép dữ liệu từ leader để duy trì bản sao.

Ví dụ topic payments có replication factor bằng 3:

~~~text
Partition payments-0

Broker 1: Leader
Broker 2: Follower
Broker 3: Follower
~~~

Replication factor 3 nghĩa là partition có ba replica được gán trên các broker. Nó không có nghĩa cả ba replica luôn có cùng dữ liệu tại mọi thời điểm.

### 1.1. ISR là gì?

ISR là tập hợp các replica đang theo kịp leader theo tiêu chí đồng bộ của Kafka. ISR có thể thay đổi khi broker mất kết nối, follower sao chép chậm hoặc follower bắt kịp trở lại.

Ví dụ:

~~~text
Replica assignment: [Broker 1, Broker 2, Broker 3]
Current ISR:        [Broker 1, Broker 2]
Out of ISR:         [Broker 3]
~~~

Broker 3 vẫn là replica được gán cho partition, nhưng hiện không thuộc ISR. Nó có thể đang chậm hoặc đã mất kết nối đủ lâu để bị loại khỏi ISR.

ISR không phải danh sách tất cả broker đang chạy. Nó là danh sách replica đủ điều kiện được xem là đồng bộ với leader tại thời điểm đó.

### 1.2. Log End Offset và High Watermark

Hai khái niệm giúp hiểu vì sao một replica có thể bị tụt hậu:

- **Log End Offset (LEO):** vị trí offset tiếp theo mà replica có thể append. LEO cho biết log của replica đã ghi đến đâu.
- **High Watermark (HW):** mốc offset mà Kafka xem là đã được replicate đầy đủ theo trạng thái ISR; record nằm dưới HW được xem là committed trong log.

Ví dụ minh họa:

| Replica | LEO | Diễn giải |
|---|---:|---|
| Leader Broker 1 | 106 | Leader đã append đến offset 105 |
| Follower Broker 2 | 106 | Follower đã theo kịp leader |
| Follower Broker 3 | 102 | Follower mới append đến offset 101 |

Nếu Broker 1 và Broker 2 thuộc ISR, còn Broker 3 ở ngoài ISR, HW được xác định dựa trên tiến độ của các replica trong ISR. Những record leader đã append nhưng chưa được replicate đến các replica cần thiết có thể chưa được xem là committed.

Các giá trị trên chỉ để minh họa mối quan hệ giữa LEO và HW; cách tính và các mốc offset nội bộ cần được hiểu theo protocol của phiên bản Kafka đang dùng.

## 2. Clean leader election và unclean leader election

Khi leader dừng hoạt động, controller điều phối việc chọn leader mới.

### 2.1. Clean leader election

Clean leader election chọn một replica thuộc ISR làm leader mới. Replica này được xem là đã theo kịp log theo tiêu chí ISR, do đó giảm nguy cơ mất các record đã được xác nhận là committed.

Ví dụ:

~~~text
Trước sự cố:
  Broker 1: Leader,   LEO 106
  Broker 2: Follower, LEO 106, thuộc ISR
  Broker 3: Follower, LEO 102, ngoài ISR

Broker 1 dừng:
  Broker 2 còn hoạt động và thuộc ISR
  -> Broker 2 có thể được bầu làm leader mới
~~~

Broker 2 có dữ liệu cần thiết để tiếp tục phục vụ partition theo log đã được đồng bộ. Broker 3 có thể tiếp tục làm follower và bắt kịp leader mới sau khi kết nối trở lại.

Clean election ưu tiên tính nhất quán và durability. Nếu không có replica ISR nào khả dụng, partition có thể phải ở trạng thái offline để chờ phục hồi.

### 2.2. Unclean leader election

Unclean leader election cho phép chọn một replica ngoài ISR làm leader khi không có replica ISR nào khả dụng.

Replica ngoài ISR có thể thiếu các record mà leader cũ đã ghi. Khi nó trở thành leader, log của partition tiếp tục từ trạng thái dữ liệu mà replica đó đang có. Những record chỉ tồn tại trên các replica cũ có thể bị mất khỏi lịch sử đang hoạt động.

Ví dụ:

~~~text
Trước sự cố:
  Broker 1: Leader,   LEO 106
  Broker 2: Follower, LEO 106, thuộc ISR
  Broker 3: Follower, LEO 102, ngoài ISR

Sự cố:
  Broker 1 và Broker 2 không thể truy cập
  Broker 3 là replica duy nhất còn hoạt động

Nếu unclean leader election được bật:
  Broker 3 có thể được bầu làm leader mới
  Các record từ offset 102 trở đi không có trên Broker 3
  -> Các record đó có nguy cơ bị mất khỏi log hiện hành
~~~

Nếu Broker 1 hoặc Broker 2 sau đó quay lại, chúng phải đồng bộ theo leader mới. Phần log không khớp có thể bị truncate trong quá trình follower bắt kịp. Vì thế, không thể mặc định rằng record cũ sẽ tự xuất hiện trở lại chỉ vì broker cũ đã khởi động.

### 2.3. So sánh hai cơ chế

| Tiêu chí | Clean leader election | Unclean leader election |
|---|---|---|
| Replica được chọn | Replica thuộc ISR | Có thể chọn replica ngoài ISR |
| Điều kiện | Có replica ISR đủ điều kiện và khả dụng | Không có replica ISR khả dụng |
| Khả năng phục vụ | Có thể phải chờ replica ISR quay lại | Có thể khôi phục partition sớm hơn |
| Nguy cơ mất record đã ghi | Thấp hơn, theo bảo đảm replication và ISR | Có thể cao nếu replica mới thiếu record |
| Ưu tiên | Durability và tính nhất quán | Availability |
| Trạng thái khi không có ISR khả dụng | Partition có thể offline | Có thể dùng replica tụt hậu |

Clean election không có nghĩa mọi record mà ứng dụng từng gửi đều chắc chắn tồn tại. Nó bảo vệ dữ liệu theo trạng thái replication và xác nhận của Kafka. Producer config, ISR, min.insync.replicas và thời điểm sự cố vẫn ảnh hưởng đến mức bảo đảm.

## 3. Cấu hình unclean.leader.election.enable

Cấu hình broker **unclean.leader.election.enable** quyết định Kafka có cho phép bầu leader từ replica ngoài ISR trong trường hợp không có replica ISR khả dụng hay không.

~~~properties
# Ưu tiên durability: không bầu leader ngoài ISR
unclean.leader.election.enable=false
~~~

Khi đặt false:

- Kafka chỉ sử dụng replica thuộc ISR cho leader election thông thường.
- Nếu không có replica ISR nào khả dụng, partition có thể ở trạng thái offline.
- Partition sẽ chờ replica đồng bộ quay lại hoặc được phục hồi theo quy trình vận hành.
- Hệ thống tránh việc chủ động chọn một bản sao đã tụt hậu chỉ để khôi phục phục vụ.

Khi đặt true:

- Kafka có thể chọn replica ngoài ISR nếu không có replica ISR nào khả dụng.
- Partition có thể phục vụ trở lại sớm hơn.
- Dữ liệu đã có trên leader cũ nhưng không có trên replica được chọn có thể bị mất.
- Consumer có thể quan sát lịch sử bị rút ngắn hoặc khác với log trước sự cố.

Trong các phiên bản Kafka hiện đại, false thường là giá trị mặc định, nhưng phải kiểm tra cấu hình hiệu lực của broker và phiên bản đang vận hành. Đây là cấu hình ở cấp broker/cluster, không phải một thuộc tính message hoặc một lựa chọn riêng trong từng lần gửi record.

Không nên bật unclean election chỉ để loại bỏ cảnh báo partition offline. Trước khi thay đổi, cần xác định rõ dữ liệu nào có thể mất và ai chấp nhận rủi ro nghiệp vụ đó.

## 4. Mối quan hệ giữa acks, min.insync.replicas và unclean election

Ba cấu hình này thường được nhắc cùng nhau, nhưng chúng giải quyết các vấn đề khác nhau:

- **acks:** producer yêu cầu mức xác nhận nào khi ghi record.
- **min.insync.replicas:** broker yêu cầu tối thiểu bao nhiêu replica trong ISR cho một lần ghi với acks=all.
- **unclean.leader.election.enable:** quyết định có được bầu leader từ replica ngoài ISR khi không còn replica ISR khả dụng hay không.

### 4.1. acks=all không có nghĩa mọi replica được gán đều phải xác nhận

Với acks=all, producer chờ các replica trong ISR đáp ứng điều kiện xác nhận của Kafka. Nó không chờ mọi replica từng được gán cho partition, kể cả replica đã nằm ngoài ISR.

Ví dụ replication factor là 3 nhưng ISR chỉ còn Broker 1 và Broker 2. Với acks=all, việc xác nhận ghi dựa trên tập ISR hiện tại, không phải bắt buộc Broker 3 ngoài ISR phải xác nhận.

### 4.2. min.insync.replicas đặt ngưỡng an toàn cho ghi

Giả sử:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
~~~

Khi ISR còn hai replica, broker có thể chấp nhận ghi với acks=all. Nếu ISR giảm còn một replica, broker từ chối ghi vì không đạt min.insync.replicas.

Điều này giúp tránh tiếp tục xác nhận các lần ghi mới khi số bản sao đồng bộ đã xuống dưới ngưỡng được chọn.

Tuy nhiên, min.insync.replicas không phải cơ chế ngăn unclean leader election. Nó kiểm soát điều kiện ghi, còn unclean election kiểm soát lựa chọn leader khi không còn replica ISR khả dụng.

### 4.3. Các cấu hình phối hợp với nhau

| Producer acks | min.insync.replicas | Unclean election | Ý nghĩa vận hành |
|---|---:|---|---|
| all | 2 | false | Ưu tiên durability; từ chối ghi khi ISR dưới 2 và giữ partition offline nếu không còn ISR khả dụng |
| all | 2 | true | Ghi vẫn yêu cầu ít nhất 2 ISR, nhưng khi mọi ISR không khả dụng, replica ngoài ISR có thể được bầu và dữ liệu có thể mất |
| 1 | 1 | false | Producer chỉ chờ leader; vẫn tránh bầu replica ngoài ISR nhưng record có thể chưa được follower replicate khi leader lỗi |
| 1 | 1 | true | Ưu tiên availability cao hơn; cả xác nhận ghi và leader election đều có thể chấp nhận mức bảo vệ dữ liệu thấp hơn |

Với topic quan trọng, một cấu hình thường được cân nhắc là replication factor 3, acks=all, min.insync.replicas=2 và unclean leader election tắt. Đây là một cấu hình nền tảng, không thay thế việc phân bố replica trên các broker và failure domain độc lập.

Ngay cả khi dùng acks=all và min.insync.replicas=2, nếu mọi replica từng xác nhận record đều bị mất hoặc không thể khôi phục, dữ liệu vẫn có thể mất. Không có cấu hình replication nào thay thế được backup, kế hoạch phục hồi và quy trình bảo vệ dữ liệu.

## 5. Kịch bản mất dữ liệu chi tiết

Xét partition orders-0 có ba replica:

| Broker | Vai trò trước sự cố | Trạng thái log |
|---|---|---|
| Broker 1 | Leader | Có các record đến offset 105 |
| Broker 2 | Follower, thuộc ISR | Đã replicate đến offset 105 |
| Broker 3 | Follower, ngoài ISR | Chỉ có record đến offset 101 |

Giả sử producer gửi record đến offset 105 với acks=all khi Broker 1 và Broker 2 đang thuộc ISR. Record được xác nhận sau khi các replica trong ISR đáp ứng điều kiện ghi.

Sau đó:

1. Broker 1 gặp sự cố phần cứng.
2. Broker 2 cũng mất kết nối hoặc không thể phục hồi.
3. Broker 3 là replica duy nhất còn hoạt động nhưng đang ngoài ISR.
4. Nếu unclean election tắt, partition ở trạng thái offline và chờ replica ISR phục hồi.
5. Nếu unclean election bật, Broker 3 có thể được bầu làm leader.
6. Log mới của partition chỉ có dữ liệu đến offset 101; các record 102-105 không có trên leader mới.

~~~mermaid
flowchart TD
    A["Trước sự cố<br/>B1 và B2 thuộc ISR<br/>B3 bị tụt hậu"] --> B["B1 và B2 mất khả năng phục vụ"]
    B --> C{"Unclean leader election?"}
    C -->|false| D["Không bầu B3<br/>Partition offline<br/>Chờ ISR phục hồi"]
    C -->|true| E["Bầu B3 ngoài ISR"]
    E --> F["Partition hoạt động trở lại"]
    F --> G["Các record B3 chưa có<br/>có thể mất khỏi log hiện hành"]
~~~

Đây là ví dụ minh họa cho một lần mất đồng thời các replica đã đồng bộ. Trong vận hành thực tế, cần kiểm tra log end offset, high watermark, replica state và lịch sử acknowledgement để xác định chính xác phạm vi dữ liệu bị ảnh hưởng.

### 5.1. Record đã được producer xác nhận có thể vẫn mất không?

Có. acks=all chỉ chờ các replica thuộc ISR tại thời điểm ghi. Nếu toàn bộ các replica đã xác nhận record sau đó đều không khả dụng, và một replica ngoài ISR được chọn làm leader, record có thể không còn trong log hiện hành.

Đó là lý do cần phân biệt:

- **Producer acknowledgement:** producer nhận xác nhận rằng điều kiện ghi đã được đáp ứng.
- **Replication factor:** số replica được gán cho partition.
- **ISR:** các replica hiện được xem là đồng bộ.
- **Unclean election:** cho phép chọn một replica ngoài ISR khi không còn lựa chọn ISR khả dụng.

Không nên diễn giải acks=all là bảo đảm tuyệt đối chống mất dữ liệu trong mọi tổ hợp sự cố.

### 5.2. Consumer có thể nhìn thấy điều gì?

Sau unclean election, consumer có thể gặp một số tình huống:

- Những record từng có trong log leader cũ không còn được đọc từ leader mới.
- Log end offset mới có thể thấp hơn log end offset của leader cũ.
- Committed offset của consumer group có thể vượt quá log end offset mới và dẫn đến OffsetOutOfRangeException.
- Nếu offset vẫn nằm trong phạm vi log mới, consumer có thể tiếp tục mà không tự biết rằng một số record ở giữa lịch sử đã mất.
- Ứng dụng downstream có thể giữ trạng thái được tạo từ record cũ trong khi lần replay sau không còn những record đó.

Cần đối chiếu event ID, sequence number, database state và log ứng dụng để xác định tác động nghiệp vụ. Không nên tự động reset offset về earliest hoặc latest trước khi hiểu dữ liệu bị ảnh hưởng.

## 6. Khi nào nên bật hoặc tắt unclean election?

Quyết định phụ thuộc mục tiêu của topic và khả năng chấp nhận mất dữ liệu.

| Loại dữ liệu | Ưu tiên thường gặp | Chính sách thường phù hợp |
|---|---|---|
| Thanh toán, sổ cái, đơn hàng đã xác nhận | Durability và tính nhất quán | Tắt unclean election |
| Trạng thái tài khoản, tồn kho | Durability, tránh trạng thái lùi | Tắt unclean election |
| Audit log hoặc sự kiện pháp lý | Giữ lịch sử | Tắt unclean election |
| Telemetry có thể tái tạo từ nguồn khác | Availability có thể quan trọng hơn | Có thể cân nhắc bật nếu business chấp nhận mất một phần dữ liệu |
| Metrics tần suất cao, dữ liệu không quan trọng | Phục vụ liên tục và chi phí khôi phục thấp | Đánh giá theo RPO/RTO thực tế |
| Event stream có thể replay từ hệ thống nguồn | Có thể phục hồi từ upstream | Chỉ cân nhắc bật khi đã kiểm chứng quy trình replay |

Không có một lựa chọn phù hợp cho mọi hệ thống. Hãy định nghĩa rõ:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận hệ thống không phục vụ.
- **Durability:** mức độ dữ liệu đã xác nhận được bảo vệ trước sự cố.
- **Availability:** khả năng tiếp tục phục vụ khi thành phần gặp lỗi.

Tắt unclean election thường làm RTO dài hơn khi không còn ISR khả dụng, nhưng giữ được nguyên tắc không tự chọn bản sao tụt hậu. Bật unclean election có thể giảm thời gian partition offline, nhưng RPO có thể lớn hơn 0.

## 7. Kiểm tra cấu hình và trạng thái replica

### 7.1. Xem leader, replicas và ISR

Dùng kafka-topics để kiểm tra partition:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --topic orders
~~~

Quan sát các trường:

- Leader: broker đang phục vụ partition.
- Replicas: danh sách replica được gán.
- Isr: danh sách replica đang đồng bộ.
- Partition nào không có leader hoặc ISR bị thu hẹp.

Nếu ISR liên tục co lại, cần tìm nguyên nhân follower không bắt kịp như disk chậm, network nghẽn hoặc broker quá tải.

### 7.2. Kiểm tra cấu hình broker

Cấu hình unclean election là cấu hình broker/cluster. Có thể kiểm tra file cấu hình broker hoặc cấu hình hiệu lực qua công cụ quản trị tương ứng với phiên bản Kafka.

Ví dụ trong server.properties:

~~~properties
unclean.leader.election.enable=false
~~~

Nếu môi trường hỗ trợ dynamic broker configuration, cách xem hoặc cập nhật cấu hình có thể dùng kafka-configs.sh và phụ thuộc phiên bản, phạm vi cấu hình. Cần xác nhận cấu hình hiệu lực trên toàn bộ broker liên quan; không giả định sửa một file cấu hình đã có hiệu lực ngay khi broker đang chạy.

### 7.3. Kiểm tra min.insync.replicas

Có thể xem cấu hình topic:

~~~bash
kafka-configs.sh \
  --bootstrap-server broker-1:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Kiểm tra min.insync.replicas, cleanup policy và các cấu hình liên quan. Đồng thời kiểm tra producer có thực sự dùng acks=all hay không; cấu hình topic không thể thay thế producer config.

### 7.4. Theo dõi các metric replication

Các chỉ số nên giám sát:

| Metric hoặc dấu hiệu | Ý nghĩa |
|---|---|
| UnderReplicatedPartitions | Partition có replica chưa theo kịp |
| OfflinePartitionsCount | Partition không có leader khả dụng |
| IsrShrinksPerSec | Tốc độ replica bị loại khỏi ISR |
| IsrExpandsPerSec | Tốc độ replica gia nhập lại ISR |
| LeaderElectionRateAndTimeMs | Hoạt động và thời gian leader election |
| Replica fetch lag | Khoảng cách tiến độ giữa follower và leader |
| Produce request latency | Độ trễ request ghi, có thể tăng khi replication chậm |

Cần đặt cảnh báo cho offline partition và ISR shrink bất thường. Theo dõi xu hướng theo broker và topic để nhận biết một broker thường xuyên làm replica tụt hậu.

## 8. Quy trình xử lý khi partition không có ISR khả dụng

Khi partition offline do không có replica ISR nào có thể làm leader, hãy xử lý theo thứ tự.

### Bước 1: Xác định partition và replica

- Dùng kafka-topics --describe để kiểm tra leader, replicas và ISR.
- Xác định broker nào đang dừng, mất kết nối hoặc có log directory lỗi.
- Xem log broker và controller quanh thời điểm partition mất leader.
- Ghi lại log end offset, high watermark và trạng thái replica nếu công cụ giám sát cung cấp.

### Bước 2: Tìm cách phục hồi replica ISR

Ưu tiên khôi phục broker hoặc storage từng thuộc ISR:

- Khôi phục mạng giữa broker và cluster.
- Khắc phục disk đầy, filesystem lỗi hoặc log directory không khả dụng.
- Khởi động lại broker theo quy trình vận hành.
- Cho follower có thời gian fetch và bắt kịp leader/replica phù hợp.
- Xác nhận replica trở lại ISR trước khi tiếp tục.

Nếu replica ISR có thể phục hồi, clean election giúp tiếp tục với bản sao đã đồng bộ.

### Bước 3: Đánh giá dữ liệu và quyết định RPO

Nếu không thể phục hồi bất kỳ replica ISR nào, cần đánh giá:

- Dữ liệu này có thể tái tạo từ database, outbox hoặc upstream không?
- Có bản sao lưu hoặc snapshot đáng tin cậy không?
- Sự kiện nào đã được producer xác nhận?
- Mức mất dữ liệu tối đa mà chủ sở hữu nghiệp vụ chấp nhận?
- Có cần giữ partition offline để bảo toàn cơ hội phục hồi dữ liệu không?

Đây là quyết định nghiệp vụ và vận hành. Không nên tự động bật unclean election khi chưa xác định phạm vi mất dữ liệu.

### Bước 4: Nếu chấp nhận unclean election

Chỉ thực hiện theo quy trình thay đổi đã được phê duyệt:

1. Ghi nhận trạng thái replica và metadata trước khi thay đổi.
2. Bảo toàn log hoặc snapshot của các broker cũ nếu còn khả năng truy cập và cần điều tra.
3. Xác nhận replica nào sẽ được dùng làm leader mới và mức dữ liệu nó đang có.
4. Thay đổi cấu hình theo cách phù hợp với phiên bản Kafka và chính sách cluster.
5. Theo dõi leader election, log end offset và trạng thái partition.
6. Kiểm tra consumer offset, event ID và trạng thái nghiệp vụ sau khi partition hoạt động.
7. Ghi nhận rõ khoảng dữ liệu có thể mất và lập kế hoạch tái tạo từ nguồn khác nếu có.

Sau khi khôi phục, đánh giá lại cấu hình. Không nên để một thay đổi tạm thời làm chính sách mặc định lâu dài mà không có quyết định rõ ràng về RPO.

### Bước 5: Đồng bộ và xác minh replica quay lại

Khi broker cũ trở lại:

- Kiểm tra broker có gia nhập đúng cluster và nhận đúng metadata không.
- Theo dõi follower fetch và ISR expansion.
- Xác nhận replica bắt kịp leader mới.
- Kiểm tra consumer lag, offset và trạng thái dữ liệu downstream.
- Không xóa hoặc format lại log directory để ép replica tham gia nếu chưa hiểu trạng thái dữ liệu.

Replica cũ có thể cần truncate phần log không khớp với leader mới trước khi đồng bộ tiếp. Đây là một phần của quá trình phục hồi sau leader change.

## 9. Những lỗi thiết kế thường gặp

- **Bật unclean election để mọi partition luôn online.** Partition có thể phục vụ trở lại nhưng dữ liệu đã ghi trên replica cũ có thể mất.
- **Cho rằng acks=all đồng nghĩa mọi replica được gán đều đã xác nhận.** acks=all dựa trên ISR hiện tại.
- **Cho rằng min.insync.replicas ngăn mọi trường hợp mất dữ liệu.** Nó đặt ngưỡng cho ghi mới, không thay thế bảo vệ trước việc toàn bộ bản sao đã xác nhận bị mất.
- **Nhầm unclean election với preferred leader election.** Preferred leader election cố gắng đưa leadership về replica ưu tiên, thường thuộc ISR; unclean election có thể chọn replica ngoài ISR.
- **Cho rằng controller quorum là bản sao dữ liệu partition.** KRaft quorum lưu metadata và điều phối cụm; dữ liệu record được replication giữa các broker.
- **Reset consumer offset ngay khi gặp OffsetOutOfRange.** Cần xác định log start/end offset và tác động của việc mất dữ liệu trước khi chọn earliest hoặc latest.
- **Khôi phục broker bằng cách xóa log directory.** Hành động này có thể loại bỏ bản sao cuối cùng còn giữ dữ liệu cần phục hồi.
- **Không kiểm tra phân bố failure domain.** Replication factor 3 trên ba broker cùng một máy hoặc cùng một miền lỗi không đem lại khả năng chịu lỗi tương ứng.

## 10. Kết luận

Unclean leader election là cơ chế cho phép Kafka chọn replica ngoài ISR làm leader khi không còn replica ISR nào khả dụng. Cơ chế này có thể khôi phục khả năng phục vụ partition nhanh hơn, nhưng replica được chọn có thể thiếu record đã được leader cũ xác nhận. Khi đó, log hiện hành có thể bị rút ngắn và consumer hoặc hệ thống downstream có thể chịu ảnh hưởng.

Với dữ liệu quan trọng, thường nên tắt unclean leader election, kết hợp replication factor phù hợp, acks=all và min.insync.replicas được lựa chọn theo yêu cầu durability. Khi không còn ISR khả dụng, ưu tiên phục hồi replica đồng bộ và đánh giá dữ liệu trước khi chấp nhận unclean election. Nếu phải đánh đổi availability để tránh partition offline, hãy xác định rõ RPO, bảo toàn bản sao có thể phục hồi và kiểm tra lại trạng thái nghiệp vụ sau khi leader mới hoạt động.
