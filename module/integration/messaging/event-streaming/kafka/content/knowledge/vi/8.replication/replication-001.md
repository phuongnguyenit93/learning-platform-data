# Replica, leader, follower và replication factor

Kafka lưu dữ liệu theo topic và partition. Để một partition vẫn có thể hoạt động khi một broker gặp sự cố, Kafka có thể giữ nhiều bản sao của partition trên các broker khác nhau. Các bản sao đó được gọi là replica. Trong mỗi partition, một replica giữ vai trò leader; các replica còn lại là follower.

Replication factor (RF) cho biết mỗi partition có bao nhiêu replica, tính cả leader. Ví dụ RF = 3 nghĩa là mỗi partition có một leader và hai follower. Hiểu đúng vai trò của replica, leader, follower và RF giúp thiết kế khả năng chịu lỗi, lựa chọn cấu hình producer và xác định hệ thống sẽ phản ứng thế nào khi broker dừng hoặc mạng bị gián đoạn.

## 1. Replica là gì?

Replica là một bản sao của partition log được lưu trên một broker. Mỗi replica có dữ liệu của cùng một partition và có vị trí log riêng. Kafka phân bố các replica của một partition trên những broker khác nhau để tránh việc một broker hỏng làm mất tất cả bản sao của partition đó.

Ví dụ topic orders có ba partition và replication factor bằng 3:

| Partition | Replica trên các broker |
|---|---|
| orders-0 | Broker 1, Broker 2, Broker 3 |
| orders-1 | Broker 2, Broker 3, Broker 1 |
| orders-2 | Broker 3, Broker 1, Broker 2 |

Mỗi partition có ba bản sao. Các bản sao của cùng một partition nằm trên ba broker khác nhau, trong khi mỗi broker có thể giữ replica của nhiều partition.

Sơ đồ một partition:

~~~mermaid
flowchart LR
    P["Producer"] --> L["Broker 1<br/>Leader replica"]
    L -->|"Follower fetch / replication"| F1["Broker 2<br/>Follower replica"]
    L -->|"Follower fetch / replication"| F2["Broker 3<br/>Follower replica"]
    C["Consumer"] -->|"Fetch records"| L
~~~

Trong ví dụ, producer gửi record đến leader của partition. Follower lấy dữ liệu từ leader và cập nhật log của bản thân. Consumer thông thường cũng đọc từ leader. Việc có nhiều replica không có nghĩa producer gửi cùng một record riêng rẽ đến từng broker; Kafka điều phối replication ở tầng broker.

Replica không phải bản backup độc lập theo nghĩa lưu trữ lâu dài. Các replica cùng thuộc một cluster và chịu ảnh hưởng của chính sách retention, lỗi vận hành, lỗi phần mềm hoặc thao tác xóa nhầm. Replication tăng khả năng sẵn sàng khi broker hỏng, nhưng không thay thế backup và quy trình phục hồi.

## 2. Leader và follower khác nhau thế nào?

### 2.1. Leader replica

Mỗi partition tại một thời điểm có một leader replica đang hoạt động. Leader chịu trách nhiệm chính cho các thao tác ghi và đọc thông thường của partition:

- Nhận Produce request từ producer.
- Append record batch vào partition log.
- Phục vụ Fetch request của consumer.
- Phối hợp với follower để replication.
- Theo dõi tiến độ replica và trạng thái ISR.
- Cung cấp dữ liệu cần thiết cho quá trình chuyển leader khi có sự cố.

Producer cần gửi record đến broker đang giữ leader của partition đích. Kafka client lấy thông tin leader từ metadata. Nếu leader thay đổi, client phải làm mới metadata và gửi lại request đến broker mới.

### 2.2. Follower replica

Follower là bản sao không giữ vai trò leader hiện tại của partition. Follower chủ động gửi yêu cầu fetch đến leader để lấy record batch mới và cập nhật log cục bộ.

Follower có các nhiệm vụ chính:

- Bắt kịp dữ liệu từ leader.
- Duy trì bản sao partition trên broker khác.
- Có thể được chọn làm leader mới nếu đủ điều kiện.
- Tham gia ISR khi đáp ứng tiêu chí đồng bộ của Kafka.

Follower có thể chậm hơn leader trong một khoảng thời gian ngắn do mạng, I/O hoặc tải broker. Điều đó không nhất thiết có nghĩa replica đã hỏng. Kafka theo dõi mức độ theo kịp để quyết định follower có còn đủ điều kiện nằm trong ISR hay không.

### 2.3. Controller quyết định leader nào đang hoạt động

Controller quản lý metadata cluster và phối hợp thay đổi trạng thái partition. Khi leader broker bị mất, controller xử lý sự kiện broker và chọn leader mới theo chính sách election, thông thường từ các replica đang nằm trong ISR.

Producer và consumer không tự chọn follower làm leader. Client nhận metadata mới từ cluster rồi kết nối đến broker đang giữ vai trò leader.

## 3. Replication factor có ý nghĩa gì?

Replication factor là số replica của mỗi partition. Nó bao gồm cả leader và follower.

| Replication factor | Cấu trúc một partition | Nhận xét |
|---:|---|---|
| 1 | 1 leader, không có follower | Không có bản sao trên broker khác |
| 2 | 1 leader, 1 follower | Có một bản sao dự phòng |
| 3 | 1 leader, 2 follower | Cấu hình phổ biến cho hệ thống cần khả năng chịu lỗi |
| 5 | 1 leader, 4 follower | Nhiều bản sao hơn, tăng chi phí lưu trữ và replication traffic |

RF = 3 không có nghĩa cluster có ba broker tổng cộng. Một cluster có thể có nhiều broker hơn; các replica của từng partition được phân phối trên các broker đó.

Một số nguyên tắc:

- RF không thể lớn hơn số broker có thể đặt replica cho partition.
- Các replica của cùng partition phải được đặt trên các broker khác nhau.
- RF càng cao thì dung lượng lưu trữ và lưu lượng replication càng tăng.
- RF cao hơn không tự động làm throughput tăng; leader vẫn phục vụ phần lớn yêu cầu đọc/ghi thông thường.
- RF cần được chọn dựa trên mục tiêu sẵn sàng, số broker, phân bố rack/availability zone và chi phí.

### 3.1. RF = 1

Với RF = 1, partition chỉ có một bản sao. Nếu broker chứa replica đó dừng, partition không có replica khác để bầu làm leader. Dữ liệu có thể vẫn còn trên disk khi broker quay lại, nhưng trong thời gian broker mất kết nối, partition không thể phục vụ bình thường.

RF = 1 thường chỉ phù hợp với lab, dữ liệu có thể tái tạo hoặc môi trường chấp nhận downtime và rủi ro mất dữ liệu cao hơn.

### 3.2. RF = 2

Với RF = 2, partition có một leader và một follower. Nếu một broker gặp sự cố, replica còn lại có thể tiếp quản nếu nó đủ điều kiện election. Tuy nhiên, khả năng tiếp tục nhận ghi còn phụ thuộc ISR, min.insync.replicas, acks và chính sách leader election.

Hai replica không cung cấp đa số 2/3 cho mọi quyết định quorum dữ liệu. Không nên suy luận rằng RF = 2 luôn bảo đảm ghi an toàn khi một bản sao đã mất liên lạc.

### 3.3. RF = 3

RF = 3 thường là lựa chọn cân bằng cho hệ thống cần chịu lỗi broker. Nếu ba replica nằm trên ba broker hoặc ba failure domain khác nhau, một broker có thể dừng mà vẫn còn hai bản sao.

Với producer dùng acks=all và min.insync.replicas=2, hệ thống có thể tiếp tục chấp nhận ghi khi còn ít nhất hai replica trong ISR. Nếu ISR giảm xuống dưới hai, Kafka từ chối ghi theo cấu hình đó để tránh chấp nhận dữ liệu khi mức replication thấp hơn yêu cầu.

RF = 3 không đảm bảo hệ thống luôn tiếp tục ghi khi hai broker cùng hỏng. Với min.insync.replicas=2, khi chỉ còn một replica trong ISR, ghi sẽ bị từ chối. Nếu bật unclean leader election để ép một replica ngoài ISR làm leader, hệ thống có thể hoạt động trở lại nhưng có nguy cơ mất các record chưa được replica đó nhận.

## 4. ISR — In-Sync Replicas

ISR (In-Sync Replicas) là tập hợp các replica được Kafka xem là đang đồng bộ đủ mức với leader. ISR bao gồm leader và các follower đáp ứng tiêu chí đồng bộ.

Ví dụ partition orders-0 có:

- Leader: Broker 1.
- Follower: Broker 2.
- Follower: Broker 3.
- ISR: Broker 1, Broker 2, Broker 3.

Nếu Broker 3 bị chậm quá ngưỡng cho phép, nó có thể bị loại khỏi ISR. Khi đó:

| Thành phần | Trạng thái |
|---|---|
| Broker 1 | Leader, trong ISR |
| Broker 2 | Follower, trong ISR |
| Broker 3 | Follower, ngoài ISR |

Follower bị loại khỏi ISR vẫn có thể còn dữ liệu trên disk và tiếp tục cố gắng bắt kịp leader. Khi đạt lại điều kiện đồng bộ, nó có thể được thêm trở lại ISR.

Kafka có cấu hình broker replica.lag.time.max.ms để xác định ngưỡng thời gian follower có thể không theo kịp leader trước khi bị xem là out-of-sync. Chi tiết cơ chế và cách diễn giải metric có thể thay đổi theo phiên bản Kafka; khi vận hành, hãy kiểm tra cấu hình và tài liệu của phiên bản đang chạy.

ISR quan trọng vì nó tham gia vào quyết định replication và acknowledgement. Khi producer dùng acks=all, leader chờ các replica hiện thuộc ISR xác nhận theo semantics Kafka. Điều đó không có nghĩa chờ mọi replica được khai báo trong RF nếu một follower đã bị loại khỏi ISR.

## 5. High watermark và dữ liệu được xem là đã commit

Mỗi replica có log end offset (LEO), là vị trí cuối log mà replica đã ghi nhận. Các replica có thể có LEO khác nhau trong lúc follower đang bắt kịp leader.

High watermark (HW) là offset ranh giới exclusive đến đó dữ liệu đã được replication xác nhận theo định nghĩa Kafka. Consumer thông thường chỉ đọc record có offset nhỏ hơn HW. HW giúp tránh để consumer nhìn thấy record mà replication chưa đạt mức Kafka coi là đã commit.

Ví dụ minh họa:

| Replica | Log end offset |
|---|---:|
| Leader Broker 1 | 150 |
| Follower Broker 2 | 150 |
| Follower Broker 3 | 147 |
| High watermark | 147 |

Trong ví dụ đơn giản này, follower Broker 3 đang chậm hơn. Các record có offset nhỏ hơn 147 đã nằm trong vùng high watermark; record từ 147 trở đi chưa thuộc vùng đã commit theo HW.

Không nên nhầm high watermark với committed offset của consumer group. HW thuộc trạng thái replication của partition; committed offset thuộc tiến độ đọc của một consumer group. Hai giá trị giải quyết hai bài toán khác nhau.

Với consumer isolation level read_committed, Kafka còn dùng last stable offset (LSO) để ngăn consumer đọc vượt qua transaction chưa kết thúc. LSO và HW liên quan nhưng không phải cùng một khái niệm.

## 6. Producer acknowledgement liên quan đến replication ra sao?

Producer cấu hình acks để quyết định cần chờ xác nhận ở mức nào trước khi xem thao tác gửi thành công.

| acks | Ý nghĩa | Đánh đổi |
|---|---|---|
| 0 | Producer không chờ broker xác nhận | Độ trễ thấp, nhưng không biết broker đã ghi thành công hay chưa |
| 1 | Leader xác nhận sau khi append vào log cục bộ | Có thể mất record nếu leader hỏng trước khi follower nhận dữ liệu |
| all | Leader chờ các replica hiện thuộc ISR xác nhận theo quy tắc Kafka | Độ bền tốt hơn, nhưng có thể từ chối ghi khi ISR không đủ |

Trong Kafka, acks=all thường được dùng cùng min.insync.replicas để đặt mức replica tối thiểu phải có trong ISR khi chấp nhận ghi.

Ví dụ topic có RF = 3:

~~~properties
min.insync.replicas=2
~~~

Producer:

~~~properties
acks=all
enable.idempotence=true
retries=2147483647
~~~

Khi ISR có ba replica, leader chờ các replica trong ISR xác nhận theo protocol. Khi một follower rời ISR và chỉ còn hai replica, ghi vẫn có thể thành công. Nếu chỉ còn một replica trong ISR, broker từ chối ghi với lỗi không đủ replica đồng bộ.

Đặt min.insync.replicas ở cấp topic hoặc broker tùy chính sách triển khai. Giá trị này không tự tạo thêm replica; topic vẫn phải được tạo hoặc reassigned với RF phù hợp.

### 6.1. Ví dụ các tình huống ghi

Giả sử RF = 3 và min.insync.replicas = 2:

| Trạng thái ISR | acks=all | Kết quả mong đợi |
|---|---|---|
| 3 replica trong ISR | Có đủ replica | Ghi được |
| 2 replica trong ISR | Đạt min ISR | Ghi được |
| 1 replica trong ISR | Thấp hơn min ISR | Ghi bị từ chối |
| 0 leader hoạt động | Không có leader phục vụ | Ghi không thực hiện được |

Ứng dụng cần xử lý lỗi ghi, retry có giới hạn phù hợp và quan sát trạng thái cluster. Không nên hạ min.insync.replicas ngay khi thấy lỗi để làm cho producer gửi thành công, vì việc đó thay đổi mức độ an toàn dữ liệu mà hệ thống đã đặt ra.

Idempotent producer giúp giảm duplicate do retry trong phạm vi producer session. Nó không thay thế replication factor, ISR hoặc min.insync.replicas.

## 7. Điều gì xảy ra khi leader broker gặp sự cố?

Giả sử partition orders-0 có leader Broker 1 và follower Broker 2, Broker 3. Cả ba đang thuộc ISR.

Khi Broker 1 mất kết nối:

1. Cluster phát hiện broker không còn hoạt động.
2. Controller cập nhật trạng thái broker và xử lý leader election cho các partition bị ảnh hưởng.
3. Một replica đủ điều kiện trong ISR được chọn làm leader mới, ví dụ Broker 2.
4. Broker 2 bắt đầu phục vụ produce/fetch cho partition.
5. Client nhận lỗi do metadata cũ hoặc kết nối cũ, refresh metadata và gửi request đến leader mới.
6. Broker 3 tiếp tục fetch từ leader mới và bắt kịp log.

Sơ đồ trước và sau:

~~~mermaid
flowchart TB
    subgraph Before["Trước sự cố"]
      L1["Broker 1<br/>Leader"] --> F2["Broker 2<br/>Follower"]
      L1 --> F3["Broker 3<br/>Follower"]
    end
    subgraph After["Sau khi Broker 1 mất"]
      N2["Broker 2<br/>Leader mới"] --> N3["Broker 3<br/>Follower"]
    end
    Before -. "Controller bầu leader mới từ ISR" .-> After
~~~

Trong thời gian election, partition có thể tạm thời không phục vụ. Thời gian gián đoạn phụ thuộc phát hiện lỗi, controller, trạng thái quorum, leader election và thời gian client cập nhật metadata/retry.

Nếu replica ngoài ISR là bản sao duy nhất còn hoạt động, Kafka mặc định ưu tiên an toàn dữ liệu và có thể để partition unavailable thay vì chọn một replica có thể thiếu record. Tùy chọn unclean.leader.election.enable cho phép bầu leader ngoài ISR trong một số tình huống, nhưng có nguy cơ mất dữ liệu đã được leader cũ xác nhận mà replica mới chưa nhận.

Không bật unclean leader election chỉ để giảm downtime nếu nghiệp vụ không chấp nhận mất record.

## 8. Rack awareness và vị trí replica

Đặt replica trên các broker khác nhau là điều kiện cơ bản, nhưng nếu các broker cùng nằm trên một máy vật lý, một rack hoặc một availability zone, sự cố ở failure domain đó vẫn có thể làm mất nhiều replica cùng lúc.

Kafka hỗ trợ rack awareness qua cấu hình broker.rack. Người vận hành gán mỗi broker vào rack hoặc failure domain tương ứng. Khi phân bổ replica, Kafka có thể cố gắng trải chúng qua các rack khác nhau để giảm rủi ro một sự cố hạ tầng ảnh hưởng đồng thời nhiều bản sao.

Ví dụ:

| Broker | broker.rack |
|---|---|
| Broker 1 | zone-a |
| Broker 2 | zone-b |
| Broker 3 | zone-c |

Với RF = 3, mục tiêu là đặt ba replica của partition trên ba zone khác nhau nếu hạ tầng và thuật toán assignment đáp ứng. Cần kiểm tra replica placement thực tế sau khi tạo topic hoặc reassignment; chỉ khai báo broker.rack không đảm bảo mọi topic cũ tự động được phân bố lại.

Rack awareness giảm rủi ro theo failure domain, nhưng không thay thế thiết kế đa vùng hoàn chỉnh. Cần xem xét độ trễ liên vùng, chi phí network, quorum, khả năng phục hồi và chính sách vận hành.

## 9. Tạo topic với replication factor

Có thể tạo topic với số partition và replication factor bằng Kafka CLI:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
~~~

Lệnh trên yêu cầu cluster có đủ broker để đặt ba replica cho mỗi partition. Nếu cluster chỉ có hai broker, tạo topic với RF = 3 sẽ thất bại vì không đủ broker.

Xem phân bố replica, leader và ISR:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Kết quả có các trường thường gặp:

- Partition: số thứ tự partition.
- Leader: broker ID đang giữ leader.
- Replicas: danh sách broker chứa replica của partition.
- Isr: danh sách replica đang nằm trong ISR.

Ví dụ output minh họa:

~~~text
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3,1
Topic: orders  Partition: 2  Leader: 3  Replicas: 3,1,2  Isr: 3,1,2
~~~

Các ID trong output là broker ID minh họa, không phải tên partition. Nếu một follower bị loại khỏi ISR, trường Isr sẽ ít phần tử hơn Replicas.

## 10. Thay đổi replication factor

Replication factor không phải thuộc tính có thể đổi bằng cách sửa một dòng cấu hình topic rồi mong các bản sao tự xuất hiện. Để thay đổi số replica của partition đang tồn tại, cần thực hiện replica reassignment.

Quy trình tổng quát:

1. Xem trạng thái leader, replicas và ISR hiện tại.
2. Kiểm tra broker đích có đủ dung lượng và network capacity.
3. Lập kế hoạch reassignment cho từng partition.
4. Chạy công cụ reassignment theo hướng dẫn phiên bản Kafka.
5. Theo dõi tiến độ copy dữ liệu và trạng thái ISR.
6. Xác minh replica assignment mới và bảo đảm các partition trở lại trạng thái ổn định.

Kafka cung cấp công cụ kafka-reassign-partitions.sh trong các bản phân phối có script này. Tùy phiên bản, cú pháp và workflow có thể khác; hãy kiểm tra trợ giúp của đúng binary. Không xóa replica cũ trước khi bản sao mới được tạo và đồng bộ thành công.

Giảm RF cũng cần reassignment và làm giảm khả năng chịu lỗi. Không thực hiện trong lúc cluster đang thiếu ISR hoặc đang phục hồi sau sự cố nếu chưa đánh giá tác động.

## 11. Những hiểu lầm thường gặp

### RF = 3 nghĩa là luôn chịu được hai broker hỏng và vẫn ghi được

Không chính xác. Ba replica có thể giữ dữ liệu trên ba broker, nhưng khả năng tiếp tục ghi phụ thuộc số replica trong ISR, min.insync.replicas, acks và leader election. Với min ISR bằng 2, khi chỉ còn một replica trong ISR, ghi bị từ chối.

### Follower luôn có dữ liệu giống leader ngay lập tức

Follower replication là bất đồng bộ theo quá trình fetch và ghi log. Follower có thể trễ. ISR là cách Kafka theo dõi các replica đủ đồng bộ, không có nghĩa mọi follower luôn có LEO bằng leader tại mọi thời điểm.

### acks=all nghĩa là chờ mọi replica được khai báo trong RF

Không hẳn. acks=all chờ các replica hiện thuộc ISR theo semantics Kafka. Nếu follower bị loại khỏi ISR, nó không nằm trong tập xác nhận hiện tại. min.insync.replicas đặt ngưỡng tối thiểu để leader chấp nhận ghi.

### Consumer đọc trực tiếp từ mọi follower

Mặc định, consumer fetch từ partition leader. Một số phiên bản và cấu hình hỗ trợ replica-aware/rack-aware fetching, nhưng đó là tính năng cần cấu hình và xác minh riêng. Không nên mặc định mọi consumer đều đọc follower.

### Replication thay thế backup

Không. Replication sao chép dữ liệu trong cùng cluster. Xóa topic, lỗi logic ứng dụng, retention hoặc thao tác phá hủy có thể ảnh hưởng đến mọi replica. Backup, archive và quy trình restore vẫn cần được thiết kế riêng.

### Tăng RF làm tăng số consumer có thể xử lý song song

Không. Số consumer song song trong một group bị giới hạn chủ yếu bởi số partition được assign. RF tăng số bản sao và khả năng chịu lỗi, không tạo thêm partition.

## 12. Checklist thiết kế replication

Trước khi đưa topic vào môi trường dùng chung, hãy xác nhận:

- [ ] Đã chọn RF theo mục tiêu sẵn sàng và số broker/failure domain.
- [ ] Replica của cùng partition được đặt trên các broker khác nhau.
- [ ] Rack awareness được cấu hình và replica placement thực tế đã được kiểm tra.
- [ ] Producer acks phù hợp với yêu cầu độ bền dữ liệu.
- [ ] min.insync.replicas được đặt phù hợp với RF và chính sách ghi.
- [ ] Đã hiểu hành vi khi ISR giảm xuống dưới ngưỡng.
- [ ] Unclean leader election được cân nhắc theo trade-off giữa availability và data loss.
- [ ] Theo dõi leader, replicas, ISR, under-replicated partitions và offline partitions.
- [ ] Có quy trình reassignment khi thêm/bớt broker hoặc thay đổi RF.
- [ ] Có backup/restore độc lập với replication.
- [ ] Đã thử nghiệm broker failure và xác minh client phục hồi sau leader election.

Replica, leader, follower và replication factor tạo thành cơ chế chịu lỗi cốt lõi của Kafka. Leader nhận và phục vụ dữ liệu của partition; follower sao chép log để sẵn sàng tiếp quản; RF xác định số bản sao; ISR và acknowledgement quyết định mức độ replication được yêu cầu trước khi ghi được xác nhận. Thiết kế tốt cần cân bằng độ bền, khả năng sẵn sàng, thông lượng và chi phí lưu trữ.
