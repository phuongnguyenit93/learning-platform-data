# Leader epoch, broker epoch và nhận diện trạng thái lỗi thời

Kafka là hệ thống phân tán: broker có thể khởi động lại, leader của partition có thể thay đổi, mạng có thể bị phân vùng và các thành phần có thể tiếp tục giữ metadata cũ trong một khoảng thời gian. Nếu chỉ dựa vào broker ID hoặc offset, một thành phần cũ có thể nhầm rằng nó vẫn có quyền điều phối partition hoặc một đoạn log đã lỗi thời vẫn là dữ liệu hợp lệ.

Kafka dùng các **epoch** như những số thế hệ để phân biệt trạng thái hiện tại với trạng thái trước đó. Trong kiến trúc cụm, hai loại cần hiểu rõ là:

- **Leader epoch:** thế hệ lãnh đạo của một partition. Epoch thay đổi khi partition có leader mới.
- **Broker epoch:** thế hệ đăng ký của một broker trong cụm. Epoch giúp nhận diện đúng incarnation hiện tại của broker và fencing một tiến trình cũ.

Hai epoch này có phạm vi khác nhau. Leader epoch bảo vệ lịch sử lãnh đạo và tính nhất quán của log partition; broker epoch bảo vệ vòng đời và quyền hoạt động của broker trong cụm. Chúng cùng giúp Kafka phát hiện yêu cầu, replica hoặc trạng thái metadata đã lỗi thời.

## 1. Epoch là gì và vì sao Kafka cần nó?

Trong một hệ thống phân tán, một ID xác định danh tính nhưng chưa đủ để xác định trạng thái còn mới hay không.

Ví dụ, broker có ID 2 bị mất kết nối. Hệ thống khởi động lại broker 2 trên cùng máy hoặc một tiến trình mới đăng ký lại bằng cùng broker ID. Nếu các thành phần chỉ nhìn broker ID, chúng khó phân biệt yêu cầu đến từ tiến trình cũ hay tiến trình mới. Tương tự, partition có leader cũ bị cô lập khỏi cụm nhưng vẫn nghĩ mình đang giữ vai trò leader.

Epoch bổ sung thông tin về thế hệ:

| Thông tin | Trả lời câu hỏi |
|---|---|
| Broker ID | Thành phần nào đang tham gia cụm? |
| Broker epoch | Đây là lần đăng ký/incarnation nào của broker đó? |
| Partition ID | Partition nào đang được xử lý? |
| Leader epoch | Đây là thế hệ lãnh đạo nào của partition? |
| Offset | Vị trí record trong log partition là bao nhiêu? |

Epoch hoạt động như một **fencing token**: một thành phần nhận được thế hệ mới có thể khiến yêu cầu từ thế hệ cũ bị từ chối. Nó giúp ngăn một tiến trình đã mất quyền tiếp tục thực hiện hành động như thể nó vẫn là chủ thể hiện tại.

Epoch không phải timestamp. Không thể suy ra thời gian thực từ giá trị epoch, cũng không nên so sánh epoch giữa hai partition hoặc hai broker khác nhau để kết luận thành phần nào mới hơn trên toàn cụm. Mỗi epoch có phạm vi và chủ thể quản lý riêng.

## 2. Leader epoch của partition

### 2.1 Định nghĩa và thời điểm thay đổi

Mỗi partition có một leader tại một thời điểm. Leader epoch là số thế hệ gắn với lịch sử lãnh đạo của partition đó.

Khi một partition được bầu leader mới, Kafka tăng leader epoch. Các broker tham gia replication theo dõi epoch để biết log đang thuộc thế hệ lãnh đạo nào và để nhận diện những đoạn log không còn phù hợp với lịch sử đã được chấp nhận.

Ví dụ, partition `orders-0` trải qua các trạng thái:

| Thời điểm | Leader | Leader epoch | Ý nghĩa |
|---|---:|---:|---|
| Ban đầu | Broker 1 | 4 | Broker 1 đang lãnh đạo partition ở thế hệ 4 |
| Broker 1 lỗi | Broker 2 | 5 | Broker 2 được bầu làm leader mới |
| Broker 2 lỗi sau đó | Broker 3 | 6 | Broker 3 trở thành leader ở thế hệ tiếp theo |

Epoch tăng theo lịch sử của partition. Broker 2 có thể là leader của partition ở epoch 5 nhưng đồng thời là follower của partition khác. Một broker không có một leader epoch chung cho tất cả partition.

Leader epoch khác với offset:

- Offset định vị record trong log của một partition.
- Leader epoch xác định thế hệ lãnh đạo gắn với một khoảng offset trong lịch sử partition.
- Offset có thể được tái sử dụng sau khi Kafka loại bỏ một đoạn log chưa được commit do phát hiện log divergence.
- Epoch giúp replica xác định ranh giới chung và tránh giữ lại phần log thuộc lịch sử lãnh đạo cũ.

### 2.2 Leader epoch gắn với ranh giới log

Replica lưu thông tin về epoch và offset bắt đầu của từng thế hệ lãnh đạo. Có thể hình dung một partition có lịch sử:

| Leader epoch | Leader trong giai đoạn đó | Offset bắt đầu |
|---:|---:|---:|
| 4 | Broker 1 | 0 |
| 5 | Broker 2 | 120 |
| 6 | Broker 3 | 185 |

Bảng này là ví dụ minh họa. Trong Kafka, replica duy trì leader epoch cache để ánh xạ epoch với offset tương ứng. Khi replica cần xác định phần log nào còn phù hợp, nó có thể trao đổi thông tin epoch với leader hiện tại.

Một follower có thể đã sao chép thêm record từ leader cũ trước khi nhận biết việc leader đã thay đổi. Nếu phần đuôi log đó không thuộc lịch sử được leader mới chấp nhận, follower phải truncate phần log lệch để đồng bộ lại.

## 3. Leader epoch giúp xử lý log divergence như thế nào?

### 3.1 Tình huống hai replica có đuôi log khác nhau

Giả sử partition `payments-0` có replication factor 3:

- Broker 1 là leader ở epoch 7.
- Broker 2 và broker 3 là follower.
- Broker 1 tạm thời mất kết nối với phần còn lại của cụm nhưng vẫn có thể nhận ghi từ một client còn kết nối được.
- Broker 2 được bầu làm leader mới ở epoch 8.
- Broker 2 chỉ có phần log đã được sao chép đến offset 102, trong khi broker 1 đã ghi thêm các offset 103–105.

Đây là tình huống có thể tạo ra hai phần đuôi log khác nhau. Các record mà broker 1 ghi thêm trong lúc bị cô lập có thể chưa được commit và không nằm trong lịch sử được leader mới chấp nhận.

~~~mermaid
sequenceDiagram
    participant B1 as Broker 1 (leader cũ)
    participant B2 as Broker 2 (leader mới)
    participant B3 as Broker 3 (follower)
    Note over B1,B3: Leader epoch 7
    B1->>B1: Append offset 103-105
    Note over B1,B3: Mạng phân vùng; B1 bị cô lập
    B2->>B2: Được bầu leader, epoch 8
    B3->>B2: Fetch theo epoch hiện tại
    B2-->>B3: Log thuộc lịch sử epoch 8
    Note over B1,B2: B1 chưa biết quyền leader đã thay đổi
    B1->>B2: Kết nối lại và đồng bộ follower
    B2-->>B1: Trao đổi leader epoch và ranh giới log
    B1->>B1: Truncate phần log lệch
    B1->>B2: Fetch lại phần log còn thiếu
~~~

Trong ví dụ này, các offset cụ thể chỉ để minh họa. Kafka không chỉ so sánh LEO rồi cắt log theo một con số cố định; nó sử dụng thông tin leader epoch để tìm điểm chung giữa lịch sử của follower và lịch sử leader hiện tại.

### 3.2 Trao đổi epoch và xác định điểm chung

Kafka có giao thức trao đổi epoch giữa replica. Về mặt khái niệm:

1. Follower giữ thông tin epoch và offset mà nó đã quan sát.
2. Follower hoặc replica manager truy vấn leader hiện tại về ranh giới offset của một epoch thông qua cơ chế OffsetsForLeaderEpoch.
3. Leader trả về offset cuối cùng thuộc epoch được hỏi, hoặc thông tin epoch phù hợp nhất mà nó có.
4. Replica so sánh lịch sử của mình với kết quả từ leader để tìm điểm bắt đầu của phần log không còn hợp lệ.
5. Follower truncate phần đuôi log lệch và fetch lại dữ liệu từ leader hiện tại.

Việc này giúp follower không giữ lại các record thuộc một nhánh lịch sử đã bị loại bỏ. Nó đặc biệt quan trọng sau failover, khi replica từng theo leader cũ cần hội tụ về lịch sử của leader mới.

**Log truncation** là thao tác cắt bỏ phần đuôi log không còn hợp lệ. Kafka không tùy tiện xóa mọi record sau một lần đổi leader; việc cắt dựa trên ranh giới lịch sử được xác định qua epoch và quy tắc replication/commit.

### 3.3 Ví dụ log trước và sau khi đồng bộ

Giả sử hai replica có trạng thái trước khi phát hiện divergence:

| Offset | Broker 1 (leader cũ, epoch 7) | Broker 2 (leader mới, epoch 8) |
|---:|---|---|
| 100 | `PAYMENT_CREATED` | `PAYMENT_CREATED` |
| 101 | `PAYMENT_VALIDATED` | `PAYMENT_VALIDATED` |
| 102 | `PAYMENT_AUTHORIZED` | `PAYMENT_AUTHORIZED` |
| 103 | `PAYMENT_CAPTURED` | Chưa có |
| 104 | `PAYMENT_SETTLED` | Chưa có |
| 105 | `PAYMENT_CLOSED` | Chưa có |

Nếu các record 103–105 chỉ tồn tại trên nhánh log của leader cũ và không được leader mới chấp nhận, broker 1 sẽ loại bỏ phần đuôi đó khi đồng bộ lại. Sau khi fetch xong, hai replica có cùng lịch sử hợp lệ theo leader hiện tại.

Không thể kết luận record có thể bị truncate chỉ vì nó chưa được follower sao chép tại một thời điểm bất kỳ. Quyết định còn phụ thuộc vào lịch sử epoch, trạng thái commit, ISR và kết quả bầu leader. Với producer dùng `acks=all` và cấu hình ISR phù hợp, dữ liệu đã được xác nhận có mức bảo vệ tốt hơn trước lỗi broker, nhưng cần hiểu rõ điều kiện xác nhận và cấu hình cụm.

## 4. Broker epoch và vòng đời broker

### 4.1 Broker epoch nhận diện incarnation hiện tại

Broker ID xác định một broker logic trong cụm. Broker epoch phân biệt các lần broker đăng ký hoặc incarnation của broker đó với controller.

Trong KRaft, broker đăng ký với controller hiện tại và nhận metadata đăng ký bao gồm broker epoch. Khi một broker khởi động lại và đăng ký như một incarnation mới, controller cấp epoch mới theo trạng thái đăng ký của cụm. Các yêu cầu gắn với epoch cũ có thể bị fencing.

Ví dụ:

| Sự kiện | Broker ID | Broker epoch | Trạng thái |
|---|---:|---:|---|
| Broker khởi động lần đầu | 2 | 11 | Đăng ký hợp lệ |
| Broker mất kết nối và được khởi động lại | 2 | 12 | Incarnation mới được đăng ký |
| Tiến trình cũ tiếp tục gửi yêu cầu | 2 | 11 | Bị nhận diện là thế hệ cũ và có thể bị fencing |

Các con số chỉ minh họa. Broker epoch là trạng thái đăng ký của broker trong metadata cụm, không phải số lần process đã restart mà ứng dụng tự tính.

### 4.2 Vì sao cần fencing broker cũ?

Giả sử một máy chạy broker 2 bị mất kết nối với controller nhưng process cũ chưa dừng. Người vận hành khởi động một broker 2 mới, hoặc môi trường điều phối khởi tạo một incarnation mới dùng cùng broker ID.

Nếu cả hai tiến trình đều tiếp tục gửi yêu cầu như broker 2 hợp lệ, cụm có thể gặp xung đột trạng thái. Controller cần công nhận một incarnation hiện tại và từ chối yêu cầu từ incarnation cũ.

Broker epoch cung cấp token thế hệ để nhận diện yêu cầu lỗi thời. Khi controller hoặc broker nhận yêu cầu mang epoch cũ, Kafka có thể trả lỗi fencing như `FENCED_BROKER_EPOCH`, tùy API và luồng xử lý.

Điều này bảo vệ các thao tác quản lý broker và replica khỏi một tiến trình đã mất quyền. Nó cũng giúp tránh việc một broker cũ tiếp tục cập nhật trạng thái hoặc thực hiện các thao tác replication sau khi một incarnation mới đã được công nhận.

### 4.3 Broker epoch không phải leader epoch

| Đặc điểm | Leader epoch | Broker epoch |
|---|---|---|
| Phạm vi | Một partition | Một broker |
| Được gắn với | Lịch sử lãnh đạo partition | Lần đăng ký/incarnation broker |
| Thay đổi khi | Partition bầu leader mới | Broker đăng ký incarnation mới với controller |
| Mục đích chính | Nhận diện lịch sử log và fencing leader cũ | Fencing broker process/registration cũ |
| Tác động dễ thấy | Replica có thể cần tìm điểm chung và truncate log lệch | Yêu cầu từ broker cũ có thể bị từ chối |

Một broker có thể có broker epoch hiện tại là 12, đồng thời đang làm leader cho partition A ở leader epoch 5 và partition B ở leader epoch 9. Không thể dùng broker epoch để thay thế leader epoch.

## 5. Nhận diện các dạng trạng thái lỗi thời

Trong vận hành Kafka, “stale” có thể mô tả nhiều trạng thái khác nhau. Cần xác định thành phần nào đang giữ thông tin cũ trước khi xử lý.

### 5.1 Stale leader

Một broker từng là leader nhưng partition đã bầu leader mới. Broker cũ có thể chưa nhận được metadata mới hoặc chưa hoàn tất chuyển sang follower.

Dấu hiệu:

- Broker cũ gửi yêu cầu với leader epoch cũ.
- Broker mới đã được controller xác định là leader.
- Request hoặc replication operation bị từ chối do epoch không còn hợp lệ.
- Replica cũ cần đồng bộ lại log với leader hiện tại.

Cách xử lý là để broker nhận metadata mới, chuyển sang follower và thực hiện quy trình đồng bộ/truncation. Không cố ép broker cũ tiếp tục làm leader chỉ vì process của nó vẫn sống.

### 5.2 Stale broker incarnation

Một tiến trình broker cũ vẫn hoạt động sau khi một incarnation mới đã đăng ký bằng cùng broker ID.

Dấu hiệu:

- Broker đăng ký lại và nhận epoch mới.
- Yêu cầu từ tiến trình cũ mang broker epoch thấp hơn bị fencing.
- Log có thể xuất hiện lỗi `FENCED_BROKER_EPOCH` hoặc thông báo liên quan đến registration/heartbeat lỗi thời.

Cách xử lý là xác định tiến trình hoặc container nào đang sở hữu broker ID, dừng incarnation cũ và bảo đảm chỉ có tiến trình được điều phối hiện tại sử dụng broker ID đó.

### 5.3 Stale metadata ở client

Producer hoặc consumer có thể giữ metadata về leader trước đó. Sau failover, client vẫn thử gửi request đến broker cũ.

Dấu hiệu:

- Client nhận các lỗi như `NOT_LEADER_OR_FOLLOWER` hoặc lỗi metadata tương ứng với phiên bản giao thức.
- Client refresh metadata rồi chuyển request đến leader mới.
- Trong một khoảng thời gian ngắn, request có thể thất bại và được retry.

Kafka client chuẩn có cơ chế cập nhật metadata. Ứng dụng nên dùng client chính thức và thiết lập retry/backoff phù hợp, đồng thời không xem mọi lỗi do leader chuyển đổi là lỗi nghiệp vụ vĩnh viễn.

### 5.4 Stale replica log

Follower có log cục bộ chứa một phần đuôi không phù hợp với lịch sử leader hiện tại.

Dấu hiệu:

- Follower cần đồng bộ lại sau failover.
- Log end offset của follower không phản ánh đúng ranh giới chung.
- Broker log ghi nhận quá trình epoch reconciliation hoặc log truncation.
- Replica cần fetch lại dữ liệu từ leader.

Không nên xóa thư mục log thủ công chỉ vì follower có offset khác leader. Kafka có cơ chế đồng bộ log dựa trên epoch. Xóa dữ liệu trực tiếp có thể làm mất bản sao hữu ích và kéo dài thời gian phục hồi.

## 6. Các lỗi epoch thường gặp

Tên lỗi và nơi xuất hiện phụ thuộc API, phiên bản Kafka và vai trò broker. Một số mã lỗi thường gặp:

| Lỗi | Ý nghĩa khái quát | Hướng xử lý |
|---|---|---|
| `FENCED_LEADER_EPOCH` | Request mang leader epoch đã lỗi thời hoặc không hợp lệ so với trạng thái partition hiện tại | Refresh metadata/epoch; để replica theo leader hiện tại |
| `UNKNOWN_LEADER_EPOCH` | Broker không nhận diện được epoch được request tham chiếu | Cập nhật metadata và thử lại theo trạng thái mới |
| `FENCED_BROKER_EPOCH` | Broker request thuộc incarnation cũ đã bị controller fencing | Dừng tiến trình cũ; kiểm tra broker ID và registration |
| `NOT_LEADER_OR_FOLLOWER` | Broker nhận request không giữ vai trò phù hợp cho partition | Client refresh metadata và gửi đến broker hiện tại |

Các lỗi fencing thường là tín hiệu về thay đổi thế hệ hoặc trạng thái đăng ký. Chúng không tự động có nghĩa dữ liệu đã hỏng. Hãy đọc log controller, broker và client quanh cùng thời điểm để phân biệt failover bình thường với một tiến trình cũ vẫn đang hoạt động.

Không nên xử lý mọi lỗi epoch bằng cách retry liên tục. Retry chỉ hữu ích khi client hoặc broker có thể cập nhật metadata và hội tụ về thế hệ mới. Nếu một broker cũ liên tục gửi request sau khi đã bị fencing, cần giải quyết vòng đời process hoặc cấu hình điều phối.

## 7. Quan sát và chẩn đoán trong cụm Kafka

### 7.1 Xác định leader và ISR của partition

Dùng lệnh mô tả topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả cho biết leader, danh sách replica và ISR của từng partition. Đây là điểm bắt đầu để xác định broker nào đang là leader và replica nào đã theo kịp.

Lệnh này không phải công cụ hiển thị đầy đủ leader epoch hoặc broker epoch. Không nên suy ra epoch chỉ từ broker ID hoặc ISR.

### 7.2 Kiểm tra trạng thái controller quorum trong KRaft

~~~bash
kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
~~~

Lệnh hiển thị trạng thái metadata quorum, leader controller và các thông tin liên quan đến metadata log. Nó giúp kiểm tra controller quorum đang hoạt động, nhưng không thay thế việc kiểm tra leader epoch của từng partition.

Trong KRaft, controller quản lý metadata cụm và điều phối các thay đổi như đăng ký broker, thay đổi leader và cập nhật metadata. Nếu controller quorum mất quorum hoặc liên tục thay đổi leader, các thao tác metadata có thể bị chậm hoặc không thực hiện được.

### 7.3 Đọc log broker và controller

Khi gặp lỗi fencing hoặc log truncation:

1. Ghi lại thời điểm và partition bị ảnh hưởng.
2. Xác định leader hiện tại, broker ID và ISR bằng `kafka-topics --describe`.
3. Đối chiếu log broker cũ, broker mới và controller quanh thời điểm failover.
4. Tìm các thông báo leader epoch, broker epoch, registration, fencing, replica fetch và log truncation.
5. Kiểm tra broker ID có bị chạy đồng thời ở hai tiến trình/container hay không.
6. Xác minh follower đã trở lại ISR và leader ổn định sau khi đồng bộ.
7. Đối chiếu lỗi producer/consumer để xác định client có refresh metadata và phục hồi request hay không.

Tên log message có thể thay đổi theo phiên bản. Hãy dùng timestamp, broker ID, partition và correlation/request context để liên kết sự kiện giữa các log.

### 7.4 Phân biệt thay đổi leader bình thường với trạng thái lỗi thời kéo dài

| Quan sát | Thay đổi leader bình thường | Có thể là stale state kéo dài |
|---|---|---|
| Leader partition | Chuyển sang broker khác rồi ổn định | Nhiều lần đổi hoặc các broker ghi nhận khác nhau |
| Client request | Một số request retry trong lúc refresh metadata | Lỗi `NOT_LEADER_OR_FOLLOWER` kéo dài |
| Replica | Follower bắt kịp và quay lại ISR | ISR liên tục co lại, follower không hội tụ |
| Broker registration | Một incarnation đăng ký hợp lệ | Broker cũ và mới cùng tranh chấp broker ID |
| Epoch fencing | Xảy ra quanh thời điểm chuyển thế hệ | Lặp lại từ tiến trình cũ hoặc cấu hình điều phối sai |

Không nên coi một lần xuất hiện lỗi fencing là sự cố nghiêm trọng nếu nó xảy ra đúng lúc broker hoặc leader chuyển thế hệ. Điều cần quan tâm là lỗi có tiếp tục sau khi metadata đã ổn định hay không.

## 8. Epoch liên hệ với các cơ chế khác

Kafka có nhiều loại generation/epoch phục vụ các mục đích khác nhau. Không nên nhầm tất cả với leader epoch hoặc broker epoch.

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Leader epoch | Partition | Nhận diện thế hệ lãnh đạo và xử lý log divergence |
| Broker epoch | Broker registration | Fencing incarnation broker cũ |
| Controller/metadata leader epoch | Metadata quorum/controller | Nhận diện thế hệ lãnh đạo metadata log |
| Producer epoch | Producer ID | Fencing producer cũ và hỗ trợ idempotence/transaction |
| Consumer group generation | Consumer group | Nhận diện thế hệ membership sau rebalance |
| Transaction coordinator epoch | Transaction coordinator | Fencing coordinator cũ trong xử lý giao dịch |

Ví dụ, khi consumer group rebalance, generation của group thay đổi. Đây không phải leader epoch của partition. Khi producer dùng idempotence, producer epoch giúp broker phân biệt producer incarnation; nó cũng không phải broker epoch.

Việc phân biệt phạm vi giúp chẩn đoán chính xác: một lỗi `FENCED_LEADER_EPOCH` liên quan đến lịch sử leader của partition; lỗi `FENCED_BROKER_EPOCH` liên quan đến incarnation broker; lỗi producer fencing lại thuộc vòng đời producer hoặc transaction.

## 9. Ví dụ thực tế: broker khởi động lại sau failover

Giả sử cụm có ba broker và partition `orders-0`:

- Broker 1 đang là leader ở leader epoch 12.
- Broker 2 và 3 là follower trong ISR.
- Broker 1 bị mất kết nối kéo dài.
- Broker 2 được bầu leader ở leader epoch 13.
- Broker 1 khởi động lại và đăng ký với controller bằng incarnation mới, nhận broker epoch mới.

Trình tự phục hồi:

1. Controller ghi nhận leader mới của `orders-0`.
2. Broker 2 phục vụ producer/consumer theo metadata mới.
3. Broker 1 đăng ký lại và nhận broker epoch mới.
4. Broker 1 nhận metadata partition hiện tại và trở thành follower.
5. Broker 1 đối chiếu lịch sử leader epoch của log cục bộ với leader mới.
6. Nếu có phần đuôi log lệch, broker 1 truncate phần không còn hợp lệ.
7. Broker 1 fetch dữ liệu còn thiếu.
8. Khi bắt kịp và đủ điều kiện, broker 1 có thể gia nhập lại ISR.

~~~mermaid
flowchart TD
    A["Broker 1 là leader, leader epoch 12"] --> B["Broker 1 mất kết nối"]
    B --> C["Broker 2 được bầu leader, epoch 13"]
    C --> D["Broker 1 khởi động và đăng ký incarnation mới"]
    D --> E["Controller cấp broker epoch mới"]
    E --> F["Broker 1 nhận metadata và chuyển thành follower"]
    F --> G["Đối chiếu leader epoch, tìm điểm log chung"]
    G --> H["Truncate phần log lệch nếu cần"]
    H --> I["Fetch phần còn thiếu"]
    I --> J["Bắt kịp leader và có thể gia nhập ISR"]
~~~

Trong kịch bản này, broker epoch mới không làm leader epoch của partition tăng thêm. Leader epoch đã tăng khi broker 2 được bầu leader. Broker epoch mới chỉ nhận diện incarnation mới của broker 1.

## 10. Nguyên tắc vận hành để tránh stale state

- Duy trì broker ID duy nhất và chỉ một incarnation được điều phối cho mỗi broker ID.
- Dùng cơ chế quản lý process/container rõ ràng để tránh broker cũ vẫn chạy sau khi thay thế.
- Theo dõi leader election, ISR shrink/expand và offline partition để phát hiện thay đổi trạng thái bất thường.
- Đảm bảo mạng giữa broker, controller và các replica ổn định.
- Dùng client Kafka chuẩn để tận dụng cơ chế refresh metadata và xử lý lỗi leader chuyển đổi.
- Thiết lập retry/backoff có giới hạn; không retry vô hạn một request đã bị fencing.
- Khi follower phục hồi, để Kafka thực hiện epoch reconciliation và log truncation theo cơ chế replication.
- Không xóa log directory hoặc chỉnh sửa checkpoint/metadata bằng tay trong lúc broker đang chạy.
- Giữ broker/controller log đủ lâu để liên kết các sự kiện quanh thời điểm failover.
- Kiểm thử broker restart và leader failover trong môi trường staging để xác minh replica hội tụ và client phục hồi.

## 11. Checklist chẩn đoán

Khi gặp lỗi liên quan đến epoch hoặc nghi ngờ trạng thái lỗi thời, hãy trả lời lần lượt:

- [ ] Lỗi xảy ra ở partition nào, broker nào và thời điểm nào?
- [ ] Leader hiện tại của partition là broker nào?
- [ ] Leader epoch có thay đổi do leader election hay không?
- [ ] Broker có đăng ký incarnation mới và nhận broker epoch mới hay không?
- [ ] Có hai process/container cùng sử dụng một broker ID không?
- [ ] Replica có đang giữ phần đuôi log khác với leader hiện tại không?
- [ ] Broker đã hoàn thành đồng bộ và trở lại ISR chưa?
- [ ] Producer/consumer có refresh metadata sau lỗi leader không?
- [ ] Lỗi fencing chỉ xuất hiện trong lúc chuyển thế hệ hay tiếp tục kéo dài?
- [ ] Log broker và controller có đủ thông tin để liên kết sự kiện không?

Leader epoch và broker epoch là hai lớp bảo vệ khác nhau trong kiến trúc Kafka. Leader epoch giúp các replica thống nhất lịch sử log sau khi partition đổi leader; broker epoch giúp controller nhận diện incarnation broker hiện tại và từ chối thao tác từ tiến trình cũ. Kết hợp hai cơ chế này với metadata refresh, replication, ISR và log chẩn đoán giúp cụm Kafka phục hồi nhất quán sau failover và tránh để trạng thái lỗi thời tiếp tục tác động đến luồng sự kiện.

## Tài liệu tham khảo

- [Apache Kafka protocol documentation](https://kafka.apache.org/protocol.html) — mô tả request/response, epoch và các mã lỗi giao thức.
- [Apache Kafka design documentation](https://kafka.apache.org/documentation/#design) — replication, leader election và tính nhất quán của log.
- [Apache Kafka KRaft documentation](https://kafka.apache.org/documentation/#kraft) — controller quorum và quản lý metadata trong KRaft.
- [KIP-101: Alter Replication Protocol to use Leader Epoch rather than High Watermark for Truncation](https://cwiki.apache.org/confluence/display/KAFKA/KIP-101%3A+Alter+Replication+Protocol+to+use+Leader+Epoch+rather+than+High+Watermark+for+Truncation) — cơ chế leader epoch dùng để xác định ranh giới log khi replica đồng bộ lại.
- [KIP-631: The Quorum-based Kafka Controller](https://cwiki.apache.org/confluence/display/KAFKA/KIP-631%3A+The+Quorum-based+Kafka+Controller) — kiến trúc controller dựa trên quorum và metadata KRaft.

Các tên lỗi, chi tiết giao thức và công cụ quan sát có thể thay đổi theo phiên bản Kafka. Khi xử lý sự cố thực tế, hãy đối chiếu tài liệu protocol và log của đúng phiên bản đang triển khai.
