# Failure domain của ứng dụng và Kafka

Trong vận hành Spring Kafka, một lỗi hiếm khi chỉ là “Kafka bị lỗi” hoặc “ứng dụng bị lỗi”. Lỗi thường bắt đầu trong một phạm vi cụ thể, sau đó lan qua các phụ thuộc: một listener xử lý chậm làm consumer bỏ lỡ nhịp poll, consumer rời group, partition được gán lại, lag tăng; hoặc một broker mất kết nối khiến leader của một số partition phải bầu lại, producer tăng retry và ứng dụng cạn thread chờ gửi.

**Failure domain** là phạm vi thành phần có thể cùng bị ảnh hưởng bởi một lỗi hoặc một nguyên nhân chung, cùng với ranh giới mà ta có thể cô lập, khôi phục và quan sát. Xác định đúng failure domain giúp trả lời bốn câu hỏi khi thiết kế và xử lý sự cố:

1. Thành phần nhỏ nhất nào đang hỏng?
2. Những thành phần hoặc luồng dữ liệu nào cùng chịu ảnh hưởng?
3. Lỗi có thể lan sang vùng nào khác qua tài nguyên hoặc phụ thuộc dùng chung?
4. Có thể khôi phục thành phần đó độc lập đến mức nào mà không làm mất hoặc xử lý trùng dữ liệu?

Mục tiêu không phải loại bỏ mọi lỗi. Mục tiêu là giới hạn bán kính ảnh hưởng (blast radius), giữ cho phần còn khỏe tiếp tục hoạt động và khôi phục dữ liệu một cách có kiểm soát.

## 1. Phân biệt failure domain, failure mode và blast radius

Ba khái niệm liên quan nhưng không đồng nghĩa:

- **Failure domain**: vùng có chung rủi ro hoặc chung cơ chế hỏng, chẳng hạn một JVM, một node, một availability zone (AZ), một broker hay một Kafka cluster.
- **Failure mode**: cách lỗi biểu hiện, chẳng hạn process dừng, mất mạng, hết dung lượng đĩa, leader không khả dụng, listener ném exception hoặc database từ chối kết nối.
- **Blast radius**: phạm vi tác động thực tế khi failure mode xảy ra, chẳng hạn một partition bị gián đoạn, toàn bộ consumer group tăng lag, hoặc mọi service dùng chung một database đều ngừng xử lý.

Một failure domain có thể chứa nhiều failure mode. Một failure mode cũng có thể tác động qua nhiều domain nếu các thành phần dùng chung hạ tầng. Ví dụ, mất một AZ có thể đồng thời làm mất một số pod ứng dụng, một số broker và một phần dịch vụ mạng. Khi đó, triển khai nhiều pod vẫn chưa tạo được tính sẵn sàng cao nếu tất cả pod đều nằm trong cùng AZ.

Không nên xem ranh giới logic là ranh giới lỗi độc lập. Hai deployment khác tên vẫn có thể cùng phụ thuộc vào một DNS, một secret, một database connection pool, một NAT gateway hoặc một Kafka cluster.

## 2. Các failure domain ở phía ứng dụng

Ứng dụng Spring Boot sử dụng Spring Kafka có nhiều lớp failure domain. Cần phân biệt chúng vì cách phục hồi của từng lớp khác nhau.

### 2.1 Process, JVM và container

Đây là phạm vi nhỏ nhất thường gặp:

- Một JVM có thể dừng vì lỗi khởi động, OutOfMemoryError, lỗi cấu hình, lỗi thư viện hoặc bị hệ điều hành kết thúc.
- Một container có thể bị restart do health check thất bại, vượt giới hạn bộ nhớ hoặc tiến trình chính thoát.
- Một pod có thể bị reschedule khi node gặp sự cố hoặc khi triển khai phiên bản mới.
- Một consumer instance mất đi sẽ khiến Kafka group thực hiện rebalance và gán lại các partition mà instance đó đang sở hữu.

Nếu ứng dụng có nhiều replica độc lập, mất một pod thường chỉ làm giảm năng lực xử lý tạm thời. Tuy nhiên, điều này chỉ đúng khi các replica không cùng phụ thuộc vào một tài nguyên đã hỏng và số replica còn lại đủ tải.

Khi process dừng đột ngột, các bản ghi đã được đọc nhưng chưa commit offset có thể được đọc lại sau khi partition được gán cho consumer khác. Vì vậy, khả năng chịu lỗi của process phải đi cùng xử lý idempotent ở nghiệp vụ.

### 2.2 Node, rack, availability zone và region

Các pod có thể độc lập ở tầng process nhưng vẫn dùng chung máy vật lý hoặc vùng hạ tầng:

- **Node failure** ảnh hưởng đến mọi pod chạy trên node đó.
- **Rack failure** có thể ảnh hưởng đến nguồn điện, switch hoặc đường mạng dùng chung.
- **AZ failure** có thể làm mất đồng thời compute, network và storage trong một vùng.
- **Region failure** có thể làm mất toàn bộ cụm dịch vụ tại khu vực đó.

Nếu tất cả replica của một consumer service bị đặt trên cùng node hoặc AZ, số replica lớn không giúp ích khi failure domain đó mất hoàn toàn. Cần dùng topology spread constraints, pod anti-affinity hoặc cơ chế phân bố tương đương để phân tán replica theo node/AZ. Phân bố phải được kiểm tra ở trạng thái thực tế; khai báo cấu hình mà scheduler không thể đáp ứng không tạo ra dự phòng.

### 2.3 Deployment, cấu hình và phiên bản

Một lỗi triển khai có thể trở thành failure domain của toàn bộ service:

- Phiên bản mới có bug khiến mọi listener ném exception.
- Cấu hình sai bootstrap server, group id, topic hoặc serializer làm tất cả instance không thể kết nối hay giải mã.
- Secret hoặc chứng thư hết hạn làm nhiều instance mất xác thực cùng lúc.
- Một feature flag hoặc schema không tương thích làm hỏng toàn bộ luồng dữ liệu.

Rolling update chỉ giảm rủi ro khi phiên bản cũ còn khỏe và có thể tiếp tục xử lý trong lúc phiên bản mới được triển khai. Nếu cùng một cấu hình lỗi được phát hành cho tất cả replica, rolling update không ngăn được lỗi lan rộng.

Nên có khả năng rollback, quản lý cấu hình theo phiên bản, kiểm tra tương thích schema và triển khai theo từng đợt nhỏ. Khi thay đổi cấu hình Kafka, cần phân biệt lỗi chỉ ảnh hưởng một consumer group với lỗi ảnh hưởng mọi producer hoặc consumer dùng chung cấu hình đó.

### 2.4 Listener container, consumer thread và consumer group

Trong Spring Kafka, một phương thức có **@KafkaListener** thường được chạy bên trong listener container. Container quản lý consumer, vòng lặp poll, việc gọi listener, xử lý lỗi và commit offset theo cấu hình.

Các phạm vi quan trọng:

- **Consumer thread**: một consumer thực hiện poll và xử lý các partition được gán cho nó. Listener xử lý chậm hoặc bị block có thể làm consumer không poll đúng hạn.
- **Listener container**: quản lý một hoặc nhiều consumer tùy cấu hình concurrency và loại container.
- **Application instance**: có thể chạy nhiều container hoặc nhiều listener khác nhau.
- **Consumer group**: các consumer cùng group chia nhau partition của topic. Group có offset và trạng thái phân phối riêng.
- **Partition**: đơn vị song song và thứ tự của Kafka. Trong một consumer group, tại một thời điểm, một partition chỉ được gán cho tối đa một consumer.

**concurrency** của **@KafkaListener** làm tăng số consumer do container quản lý trên mỗi application instance. Nếu có 4 pod, mỗi pod chạy concurrency 3, group có thể có tối đa 12 consumer hoạt động. Số consumer thực sự nhận partition vẫn bị giới hạn bởi số partition được subscribe. Nếu topic chỉ có 6 partition, 6 consumer còn lại sẽ không có partition để xử lý trong group đó.

Một consumer chết thường không làm hỏng topic hoặc Kafka cluster. Nó làm thay đổi assignment của group. Nếu nhiều consumer liên tục gia nhập và rời group, rebalance lặp lại có thể làm giảm thông lượng và khiến lag tăng.

### 2.5 Tài nguyên dùng chung bên trong ứng dụng

Các pool và executor cũng là failure domain:

- Thread pool bị chiếm hết bởi lời gọi downstream đang treo.
- Database connection pool cạn khiến listener không thể hoàn tất xử lý.
- HTTP connection pool hoặc DNS resolver gặp lỗi làm mọi record phụ thuộc vào service bên ngoài bị chậm.
- Bộ nhớ heap, direct memory hoặc producer buffer tăng đến giới hạn.
- Một lock hoặc hàng đợi không giới hạn làm nhiều listener bị block.

Một listener xử lý record chậm không chỉ ảnh hưởng record đó. Nếu nó chiếm consumer thread, các partition được gán cùng consumer có thể cùng ngừng tiến triển. Nếu tất cả listener dùng chung pool, một downstream chậm có thể làm nghẽn nhiều luồng nghiệp vụ khác nhau.

Cần giới hạn pool và queue, đặt timeout cho lời gọi phụ thuộc, tách pool cho các workload có mức độ quan trọng khác nhau và theo dõi saturation. Retry không có giới hạn có thể làm tình trạng cạn tài nguyên nghiêm trọng hơn.

## 3. Các failure domain ở phía Kafka

Kafka có nhiều lớp dữ liệu và điều khiển. Một broker không phải là toàn bộ cluster, và một partition không phải là một broker.

### 3.1 Partition, leader và replica

Topic được chia thành partition. Mỗi partition có một leader và có thể có các replica trên broker khác.

- Producer gửi record tới leader của partition.
- Consumer đọc record từ leader theo assignment và cấu hình đọc.
- Replica theo kịp leader có thể thuộc tập ISR (in-sync replicas).
- Khi leader mất khả năng phục vụ, Kafka có thể bầu một replica đủ điều kiện làm leader mới.

Một broker có thể là leader của nhiều partition và là replica của nhiều partition khác. Vì vậy, mất một broker có thể làm gián đoạn nhiều partition cùng lúc, nhưng không nhất thiết làm toàn bộ topic hoặc cluster ngừng hoạt động.

Replication factor quyết định số bản sao được cấu hình cho partition. Nó không có nghĩa mọi bản sao luôn đồng bộ. ISR phản ánh các replica đang theo kịp theo tiêu chí của cluster. Cấu hình replication và phân bố broker phải xét đến failure domain vật lý; đặt các replica của cùng partition trong cùng một AZ không bảo vệ được khi AZ đó mất.

### 3.2 Broker

Broker là một node Kafka lưu trữ partition replica và phục vụ request. Một broker có thể gặp:

- Process dừng hoặc restart liên tục.
- Disk đầy, lỗi filesystem hoặc độ trễ I/O cao.
- Network partition, packet loss hoặc kết nối không ổn định.
- CPU, memory hoặc request handler thread bị quá tải.
- Lỗi cấu hình, chứng thư hoặc xác thực.

Khi broker hỏng, các partition có replica trên broker đó có thể mất một replica; các partition do broker đó làm leader cần chuyển leader nếu có replica đủ điều kiện. Nếu cluster còn đủ replica và quorum cần thiết, dữ liệu vẫn có thể được phục vụ. Tuy nhiên, số ISR giảm có thể khiến producer bị từ chối ghi khi cấu hình durability yêu cầu đủ replica.

### 3.3 Controller và metadata quorum

Kafka cần controller để quản lý metadata và các thay đổi trạng thái của cluster. Với Kafka chạy KRaft, controller quorum duy trì metadata log và bầu controller đang hoạt động.

Controller/quorum là failure domain của mặt phẳng điều khiển. Mất quorum có thể ngăn các thao tác cần cập nhật metadata hoặc bầu leader mới. Tác động lên luồng đọc/ghi hiện tại phụ thuộc trạng thái cluster, nhưng các thay đổi topology và phục hồi partition có thể bị đình trệ. Vì vậy, cần giám sát controller quorum riêng với tình trạng request data plane của broker.

Không nên kết luận cluster hoàn toàn khỏe chỉ vì một số producer và consumer hiện tại vẫn gửi/đọc được record. Mặt phẳng điều khiển có thể đang suy giảm và làm sự cố khó phục hồi hơn.

### 3.4 Topic, quota và cấu hình bảo mật

Một số lỗi có phạm vi topic hoặc client thay vì toàn cluster:

- Topic bị xóa, tạo thiếu partition hoặc có cấu hình retention không phù hợp.
- ACL thay đổi khiến một principal mất quyền đọc, ghi hoặc mô tả topic.
- Quota giới hạn throughput khiến client bị throttle.
- Schema hoặc serializer thay đổi không tương thích.
- Consumer group dùng sai group id hoặc subscribe sai topic.

Lỗi ACL của một service account có thể làm một ứng dụng ngừng hoạt động trong khi ứng dụng khác vẫn bình thường. Ngược lại, thay đổi ACL hoặc credential dùng chung có thể ảnh hưởng nhiều service. Cần quản lý danh tính và quyền theo service, topic và môi trường; tránh dùng một principal chung cho mọi ứng dụng.

### 3.5 Cluster, AZ và region

Kafka cluster là một failure domain lớn vì nhiều topic và consumer group cùng phụ thuộc vào nó. Nếu cluster mất hoàn toàn, producer không thể ghi và consumer không thể tiếp tục đọc từ cluster đó.

Replication trong cluster bảo vệ trước một số lỗi broker, nhưng không tự động bảo vệ trước mất toàn bộ cluster hoặc region. Muốn phục hồi ở region khác cần một chiến lược disaster recovery riêng, chẳng hạn replication liên cluster bằng MirrorMaker 2 hoặc giải pháp tương đương, quy trình chuyển hướng producer/consumer, quản lý offset và kiểm thử failover.

Replication liên cluster không tự động tạo ra một hệ thống active-active an toàn. Cần xác định rõ nơi ghi chính, cách xử lý xung đột, tính nhất quán thứ tự, khả năng chuyển group offset, RPO và RTO.

## 4. Nhìn failure domain theo toàn bộ luồng dữ liệu

Một record thường đi qua nhiều ranh giới. Sơ đồ dưới đây giúp xác định nơi record có thể bị chặn, mất hoặc được xử lý lặp.

~~~mermaid
flowchart LR
    P["Producer process"] --> C["Client: serialize, buffer, metadata"]
    C --> N["Network, DNS, TLS, ACL"]
    N --> K["Kafka broker: partition leader"]
    K --> R["Partition replicas / ISR"]
    R --> G["Consumer group assignment"]
    G --> L["Spring listener container"]
    L --> A["Application business logic"]
    A --> D["Database or downstream service"]
    L --> O["Offset commit"]
~~~

Mỗi mũi tên là một ranh giới có thể phát sinh lỗi. Ví dụ:

- Producer serialize thất bại: record chưa được gửi đến Kafka.
- Producer gửi nhưng không nhận được ACK trước timeout: kết quả có thể không rõ đối với ứng dụng; retry có thể cần thiết và phải được bảo vệ bằng idempotence.
- Broker nhận record nhưng replica không đáp ứng mức ISR tối thiểu: ghi có thể bị từ chối khi dùng durability policy phù hợp.
- Consumer đọc được record nhưng listener lỗi: record có thể được retry, chuyển sang retry topic/DLT hoặc tiếp tục chặn partition tùy error handler.
- Business logic ghi database thành công nhưng process chết trước khi commit offset: record có thể được đọc lại và ghi database lần nữa.
- Offset commit thành công trước khi business effect hoàn tất: lỗi sau đó có thể khiến record không được xử lý lại.

Do đó, phải theo dõi cả trạng thái Kafka lẫn trạng thái xử lý nghiệp vụ. Consumer lag bằng 0 không chứng minh dữ liệu đã được ghi đúng vào database; producer nhận ACK cũng không chứng minh downstream đã hoàn thành công việc.

## 5. Failure domain trên đường producer

Producer có nhiều điểm hỏng độc lập:

1. Ứng dụng không tạo được event hoặc không serialize được payload.
2. Client không lấy được metadata, không xác thực được hoặc không kết nối được broker.
3. Producer buffer đầy vì broker chậm hoặc mạng gián đoạn.
4. Broker leader không khả dụng hoặc replica không đủ điều kiện ACK.
5. Ứng dụng hết thời gian chờ và quyết định retry hoặc báo lỗi.

### 5.1 ACK và durability

Các lựa chọn ACK có ý nghĩa khác nhau:

- **acks=0**: producer không chờ broker xác nhận. Thông lượng có thể cao nhưng ứng dụng không biết broker đã nhận record hay chưa.
- **acks=1**: leader xác nhận sau khi ghi local. Nếu leader hỏng trước khi replica khác có dữ liệu, record có thể mất.
- **acks=all**: leader chờ các replica hiện thuộc ISR xác nhận theo giao thức replication. Đây là lựa chọn thường dùng cho dữ liệu quan trọng.

**acks=all** cần được kết hợp với **min.insync.replicas**. Ví dụ, topic có replication factor 3 và **min.insync.replicas=2**: khi còn ít nhất 2 ISR, producer có thể ghi theo policy này; khi ISR giảm xuống dưới 2, broker từ chối ghi thay vì âm thầm hạ mức durability. Ứng dụng phải xử lý lỗi ghi đó và có cơ chế retry có giới hạn.

**acks=all** không có nghĩa mọi replica được cấu hình đều phải ACK. Nó áp dụng cho ISR tại thời điểm ghi. Cấu hình replication factor, min ISR và phân bố replica phải được thiết kế cùng nhau.

### 5.2 Idempotent producer và retry

Bật idempotent producer giúp Kafka loại bỏ bản ghi trùng phát sinh do producer retry trong cùng producer session theo cơ chế sequence number. Đây là lớp bảo vệ quan trọng khi mạng chập chờn hoặc ACK bị trễ.

Tuy nhiên, idempotence không thay thế idempotency ở tầng nghiệp vụ. Nếu ứng dụng khởi động lại rồi chủ động gửi lại cùng một lệnh nghiệp vụ như một lần gửi mới, Kafka không thể tự biết đó là cùng một nghiệp vụ. Nên dùng event id hoặc business key ổn định để downstream có thể phát hiện và loại bỏ xử lý lặp.

Retry cần có giới hạn thời gian tổng thể. Nếu producer tiếp tục retry trong khi broker hoặc mạng đã hỏng kéo dài, request có thể chiếm buffer và làm cạn tài nguyên ứng dụng. Cần cân bằng **delivery.timeout.ms**, request timeout, retry và timeout của luồng gọi bên ngoài.

### 5.3 Transactional outbox

Nếu một nghiệp vụ vừa cập nhật database vừa phát event Kafka, hai thao tác độc lập có thể lệch nhau:

- Database commit thành công nhưng gửi Kafka thất bại.
- Kafka nhận event nhưng database rollback.

Kafka transaction không tự tạo giao dịch nguyên tử giữa Kafka và một database quan hệ. Transactional outbox giải quyết vấn đề bằng cách ghi business data và outbox row trong cùng transaction database; một publisher riêng đọc outbox và gửi event lên Kafka. Publisher có thể gửi lặp, nên consumer vẫn cần idempotent hoặc deduplication.

## 6. Failure domain trên đường consumer

Consumer có thể đọc record thành công nhưng không hoàn thành business effect. Cần tách rõ ba hành động: poll record, xử lý nghiệp vụ và commit offset.

### 6.1 Offset và thời điểm commit

Với xử lý kiểu at-least-once, ứng dụng thường hoàn thành business effect trước rồi mới commit offset. Nếu process chết giữa hai bước, record được đọc lại. Cách này ưu tiên tránh mất record nhưng đòi hỏi xử lý lặp an toàn.

Nếu commit offset trước khi business effect hoàn tất, process chết sau commit có thể khiến record bị bỏ qua ở lần đọc tiếp theo. Vì vậy, thời điểm commit phải phù hợp với yêu cầu nghiệp vụ.

Trong Spring Kafka, có thể chọn ack mode phù hợp, tắt auto commit để container quản lý commit, và chỉ dùng manual acknowledgment khi ứng dụng thật sự cần kiểm soát thời điểm xác nhận. Manual ack sai vị trí có thể tạo ra mất dữ liệu hoặc xử lý trùng khó dự đoán.

### 6.2 Consumer rebalance

Rebalance xảy ra khi group thay đổi thành viên, subscription hoặc assignment. Nguyên nhân phổ biến gồm:

- Pod được triển khai hoặc restart.
- Consumer mất kết nối hoặc heartbeat.
- Listener xử lý quá lâu, vượt giới hạn poll.
- Số consumer thay đổi do autoscaling.
- Partition của topic được tăng hoặc subscription thay đổi.

Trong rebalance, partition có thể tạm thời không được xử lý. Nếu consumer chưa commit offset của record đã xử lý, record đó có thể được giao lại. Rebalance liên tục làm giảm thời gian xử lý hữu ích và tăng lag.

Đặt **max.poll.interval.ms** dựa trên thời gian xử lý thực tế của batch, số record mỗi poll và độ trễ downstream. Tăng giá trị này không chữa được listener bị treo vô hạn; cần timeout và giới hạn thời gian xử lý ở từng phụ thuộc.

### 6.3 Poison message và lỗi nghiệp vụ

Poison message là record luôn gây lỗi khi xử lý, ví dụ payload sai định dạng, thiếu trường bắt buộc hoặc dữ liệu không thể chuyển đổi. Nếu retry vô hạn tại cùng partition, một record có thể chặn các record phía sau của partition đó.

Cần phân loại lỗi:

- Lỗi tạm thời: timeout, database unavailable, rate limit hoặc lỗi mạng. Có thể retry với backoff.
- Lỗi dữ liệu hoặc nghiệp vụ không thể tự phục hồi: payload không hợp lệ, schema không tương thích hoặc vi phạm invariant. Thường nên đưa vào DLT sau số lần thử phù hợp.
- Lỗi cấu hình hoặc xác thực diện rộng: không nên retry dồn dập trên từng record; cần cảnh báo và phục hồi cấu hình hoặc credential.

DLT giúp cô lập record lỗi để partition chính tiếp tục tiến triển, nhưng DLT cũng là một thành phần vận hành: cần retention, ACL, replication, giám sát, quy trình điều tra và khả năng replay có kiểm soát. Không nên xem việc gửi vào DLT là hoàn tất nghiệp vụ.

### 6.4 Blocking retry và retry topic

Có hai cách tiếp cận thường gặp:

- **Blocking retry**: listener container thử lại record tại luồng xử lý hiện tại. Cách này giữ được thứ tự theo partition tốt hơn, nhưng một record lỗi có thể chặn partition trong thời gian retry.
- **Non-blocking retry / retry topic**: chuyển record sang topic retry có thời gian chờ rồi xử lý lại sau. Cách này giảm việc giữ consumer thread, nhưng có thể làm record đến sau được xử lý trước record đang retry. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, cần thiết kế cẩn thận.

Chọn chiến lược dựa trên yêu cầu thứ tự, thời gian phục hồi dự kiến, số lần retry và khả năng chịu lag. Tránh kết hợp retry ở nhiều tầng mà không có giới hạn; ví dụ HTTP client retry, listener retry và retry topic cùng nhân số lần gọi downstream.

## 7. Spring Kafka: ánh xạ failure domain vào cấu hình

Spring Kafka cung cấp các lớp quản lý consumer và xử lý lỗi, nhưng cấu hình của framework không tự tạo ra tính sẵn sàng cao. Cần biết mỗi cấu hình tác động ở ranh giới nào.

### 7.1 Listener concurrency và partition

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    concurrency = "3"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

Concurrency tạo nhiều consumer cho listener container. Tăng concurrency chỉ tăng song song khi có đủ partition và tài nguyên xử lý. Nếu có 4 pod, mỗi pod có concurrency 3, group có thể có tối đa 12 consumer; số consumer nhận partition vẫn bị giới hạn bởi số partition. Nếu tăng pod và concurrency vượt xa số partition, các consumer dư không giúp tăng throughput. Nếu tất cả consumer cùng gọi một database đã quá tải, tăng concurrency còn làm failure domain của database lan rộng nhanh hơn.

Cần xác định rõ:

- Số partition của topic.
- Số pod và concurrency trên mỗi pod.
- Số consumer thực tế trong group.
- Khả năng chịu tải của database và downstream.
- Yêu cầu thứ tự theo partition/key.

### 7.2 Cấu hình producer và consumer nền tảng

Ví dụ cấu hình Spring Boot minh họa cho luồng cần độ bền dữ liệu và commit do container quản lý:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
    listener:
      ack-mode: record
~~~

Đây là điểm khởi đầu, không phải bộ giá trị dùng chung cho mọi hệ thống. Cần hiệu chỉnh timeout, số record mỗi poll, ack mode và producer delivery timeout theo latency, kích thước record, thời gian xử lý và SLA. Cấu hình consumer phải tương thích với cách listener xử lý record và commit offset.

### 7.3 Xử lý exception và Dead Letter Topic

Có thể cấu hình **DefaultErrorHandler** với **DeadLetterPublishingRecoverer** để retry có giới hạn rồi chuyển record không phục hồi được sang DLT. Ví dụ minh họa:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Ví dụ giả định DLT đã được tạo và có đủ partition tương ứng với partition nguồn. Nếu DLT không có partition đích hợp lệ, việc publish DLT có thể thất bại. Trong hệ thống thực tế, cần cấu hình error handler trên listener container factory phù hợp, phân loại exception theo nghiệp vụ và kiểm tra kết quả publish DLT.

Một số lưu ý:

- Không đưa mọi exception vào nhóm non-retryable; lỗi database tạm thời có thể phục hồi.
- Không retry vô hạn lỗi dữ liệu không thể sửa.
- Bảo đảm DLT có replication, retention, ACL và cảnh báo.
- Lưu metadata lỗi, topic/partition/offset gốc và correlation/event id để điều tra.
- Replay DLT phải có kiểm soát, tránh gửi lại hàng loạt record gây quá tải downstream.

### 7.4 Retry topic

Spring Kafka hỗ trợ non-blocking retry topic qua **@RetryableTopic**. Mô hình này phù hợp khi muốn tách thời gian chờ retry khỏi consumer thread chính. Cần tạo và quản lý retry topic/DLT, xác định số lần thử, backoff, partitioning và retention. Kiểm tra tác động đến thứ tự: record retry có thể được xử lý sau record mới hơn trên partition nguồn.

### 7.5 Kafka transaction và giới hạn exactly-once

Kafka transaction có thể kết hợp việc consume record, produce record khác và commit offset trong cùng transaction Kafka. Điều này hữu ích cho luồng consume-transform-produce và hỗ trợ semantics exactly-once trong phạm vi Kafka khi được cấu hình đúng.

Tuy nhiên, nếu listener cập nhật database hoặc gọi API bên ngoài, Kafka transaction không làm các side effect đó trở thành một phần của transaction nguyên tử. Dùng idempotency key, inbox/outbox hoặc cơ chế phối hợp phù hợp cho side effect ngoài Kafka.

## 8. Ma trận sự cố và phạm vi ảnh hưởng

| Sự cố | Failure domain trực tiếp | Dấu hiệu thường thấy | Hướng xử lý |
|---|---|---|---|
| Một pod consumer dừng | Pod / consumer member | Một member rời group, rebalance, lag tăng tạm thời | Khôi phục pod; kiểm tra restart reason; xác nhận partition đã được gán lại |
| Listener xử lý quá lâu | Consumer thread / group | Poll gap, rebalance, lag tăng, timeout downstream | Tìm lời gọi chậm; đặt timeout; giảm batch/concurrency nếu cần |
| Một record luôn lỗi | Record / partition | Retry lặp, partition không tiến triển hoặc DLT tăng | Phân loại lỗi; đưa record lỗi sang DLT; sửa dữ liệu/logic rồi replay |
| Database cạn connection | Pool hoặc database dùng chung | Listener timeout hàng loạt, pool pending tăng | Khôi phục database/pool; giới hạn concurrency; áp dụng backpressure |
| Một broker dừng | Broker và các partition replica trên đó | Leader election, ISR giảm, request lỗi hoặc latency tăng | Kiểm tra broker, disk, network; phục hồi broker; theo dõi ISR và partition |
| ISR thấp hơn min ISR | Partition durability boundary | Producer nhận lỗi không đủ replica | Khôi phục replica/broker; không hạ durability vội khi chưa đánh giá rủi ro |
| Controller quorum mất | Kafka control plane | Metadata/leader changes bị đình trệ | Kiểm tra quorum và node controller; khôi phục quorum theo runbook |
| Credential/ACL sai | Principal hoặc nhóm client | Authentication/authorization error | Khôi phục secret/ACL đúng scope; tránh retry dồn dập |
| Topic hoặc schema không tương thích | Topic / contract giữa service | Serialization/deserialization error, consumer không xử lý được | Khôi phục contract tương thích; kiểm soát rollout và replay |
| Toàn bộ AZ mất | AZ | Nhiều pod/broker/network dependency cùng mất | Chuyển sang capacity ở AZ còn lại; xác minh replica và khả năng chịu tải |
| Kafka cluster mất | Cluster | Producer không ghi, consumer không đọc | Kích hoạt DR/failover; kiểm tra RPO/RTO và quy trình chuyển hướng |

Bảng trên mô tả dấu hiệu điển hình. Một dấu hiệu đơn lẻ không đủ kết luận nguyên nhân. Ví dụ, consumer lag tăng có thể do consumer dừng, downstream chậm, partition tăng tải, rebalance liên tục hoặc producer đột ngột tăng throughput.

## 9. Thiết kế để giới hạn blast radius

### 9.1 Phân tán và dự phòng

- Chạy nhiều application replica trên các node/AZ khác nhau.
- Phân bố Kafka broker và replica của partition qua các rack/AZ theo topology thực tế.
- Duy trì replication factor và min ISR phù hợp với mức mất dữ liệu chấp nhận được.
- Tránh đặt mọi service account, secret hoặc gateway phụ thuộc vào một điểm quản trị duy nhất.
- Kiểm tra năng lực còn lại khi mất một node hoặc AZ; dự phòng chỉ có ý nghĩa nếu phần còn lại đủ capacity.

### 9.2 Bulkhead và giới hạn tài nguyên

Tách tài nguyên theo workload hoặc dependency để một nhóm request chậm không chiếm toàn bộ thread, connection và queue. Dùng queue có giới hạn, thread pool có giới hạn, timeout rõ ràng và backpressure. Theo dõi cả mức sử dụng lẫn thời gian chờ pool.

Đối với listener, cân bằng concurrency với partition count và khả năng của downstream. Nếu database chỉ chịu được một mức concurrency nhất định, số consumer đồng thời phải nằm trong giới hạn đó hoặc phải có cơ chế điều tiết.

### 9.3 Retry có kiểm soát

Retry chỉ hữu ích khi lỗi có khả năng phục hồi. Thiết kế retry nên có:

- Số lần thử hữu hạn.
- Backoff, thường có jitter khi nhiều client có thể retry đồng thời.
- Timeout tổng thể cho cả chuỗi xử lý.
- Phân loại lỗi tạm thời và lỗi không thể phục hồi.
- Cơ chế dừng hoặc giảm retry khi dependency đang quá tải.
- Theo dõi số lần retry và tỷ lệ record đi vào DLT.

Retry không giới hạn có thể tạo retry storm: khi database vừa phục hồi, hàng loạt consumer cùng retry làm database quá tải trở lại.

### 9.4 Tương thích schema và triển khai an toàn

Schema evolution phải có quy tắc tương thích giữa producer và consumer đang chạy đồng thời. Triển khai producer trước hay consumer trước phụ thuộc loại thay đổi; cần bảo đảm phiên bản cũ và mới có thể cùng đọc/ghi trong giai đoạn rollout. Thay đổi không tương thích nên được triển khai theo nhiều bước, có kiểm thử và kế hoạch rollback.

Không nên đổi topic, partitioning key hoặc serialization format mà không đánh giá tác động tới thứ tự, phân bố tải, consumer assignment và khả năng replay.

### 9.5 Disaster recovery liên cluster

Với yêu cầu phục hồi sau mất cluster hoặc region, cần định nghĩa trước:

- **RPO**: lượng dữ liệu tối đa có thể mất theo thời gian.
- **RTO**: thời gian mục tiêu để khôi phục dịch vụ.
- Cluster nào là nguồn ghi chính.
- Cách replicate topic và metadata cần thiết.
- Cách chuyển producer bootstrap servers và consumer group.
- Cách xử lý offset, record trùng và record đến trễ.
- Ai có quyền kích hoạt failover và điều kiện failback.

Replication liên cluster không tự động tạo ra một hệ thống active-active an toàn. Cần xác định rõ nơi ghi chính, cách xử lý xung đột, tính nhất quán thứ tự, khả năng chuyển group offset, RPO và RTO. Diễn tập failover định kỳ. Một cấu hình replication liên cluster chưa được kiểm thử không chứng minh rằng ứng dụng có thể chuyển vùng khi sự cố xảy ra.

## 10. Quan sát failure domain bằng metrics và logs

Nên nhóm tín hiệu theo ranh giới để khoanh vùng nhanh.

| Lớp | Tín hiệu cần theo dõi |
|---|---|
| Application process | Restart count, exit reason, heap, GC pause, CPU, memory, thread count |
| Listener/container | Listener error rate, processing duration, poll interval, số consumer active, rebalance count |
| Consumer group | Lag theo group/topic/partition, commit failures, partition assignment, thời gian không có progress |
| Producer | Send error, retry count, request latency, record error rate, buffer availability, timeout |
| Kafka broker | Broker availability, request handler saturation, network processor idle, request latency, disk usage và I/O |
| Partition/replication | Under-replicated partitions, under-min-ISR partitions, offline partitions, ISR shrink/expand, leader election |
| Controller | Controller/quorum health, metadata operation latency, trạng thái bầu controller |
| Downstream | Database connection pool, query latency, timeout, error rate, queue depth và saturation |
| Retry/DLT | Retry topic lag, DLT publish failures, DLT record rate, tuổi record lâu nhất |

Các nguyên tắc quan sát:

- Đo lag theo từng partition, không chỉ tổng group; một partition bị kẹt có thể bị che bởi các partition khác đang chạy tốt.
- Đối chiếu consumer lag với tốc độ produce và tốc độ xử lý. Lag tăng vì producer tăng tải khác với lag tăng vì consumer mất năng lực.
- Dùng correlation id hoặc event id xuyên suốt producer, Kafka headers, listener và downstream logs.
- Ghi lại topic, partition, offset, group id, exception class và số lần retry khi xử lý lỗi.
- Đặt cảnh báo theo thời gian không có tiến triển và độ tuổi record, bên cạnh cảnh báo theo số lượng lag.
- Tránh chỉ cảnh báo khi process chết; một process vẫn sống nhưng listener không xử lý record cũng là sự cố.

## 11. Quy trình khoanh vùng khi có sự cố

Khi có alert, đi theo thứ tự từ triệu chứng đến ranh giới lỗi:

1. **Xác định luồng bị ảnh hưởng**: producer nào, topic nào, consumer group nào, nghiệp vụ nào và thời điểm bắt đầu.
2. **Xác định phạm vi**: một record, một partition, một consumer member, một pod, một service, một broker, một AZ hay toàn cluster.
3. **Tìm điểm tiến triển cuối cùng**: producer send/ACK, offset cuối được commit, record cuối được xử lý thành công và side effect cuối trong database.
4. **Đối chiếu hai phía**: producer rate, broker health, ISR/leader, consumer assignment/lag, listener error và downstream latency.
5. **Kiểm tra nguyên nhân dùng chung**: deployment mới, cấu hình, credential, DNS, network, quota, database hoặc schema.
6. **Giảm tác động**: dừng rollout lỗi, giảm concurrency nếu downstream quá tải, cô lập dependency hoặc chuyển record lỗi sang DLT theo runbook.
7. **Khôi phục và xác minh**: kiểm tra partition có leader, ISR đã hồi phục, consumer có progress, lag giảm và business effect được ghi đúng.
8. **Đóng sự cố bằng bằng chứng**: xác định nguyên nhân gốc, failure domain thực tế, phạm vi dữ liệu bị ảnh hưởng và hành động ngăn tái diễn.

Không nên tăng số consumer ngay khi thấy lag. Nếu bottleneck là database, tăng concurrency sẽ làm database chịu tải lớn hơn. Cũng không nên hạ **min.insync.replicas** hoặc đổi ACK policy chỉ để producer hết lỗi mà chưa đánh giá nguy cơ mất dữ liệu.

## 12. Kiểm thử khả năng cô lập lỗi

Một hệ thống chỉ chứng minh được failure domain khi đã thử làm hỏng từng ranh giới có kiểm soát. Các bài diễn tập có thể gồm:

- Dừng một consumer pod và xác nhận partition được gán lại, record chưa commit được đọc lại và business effect không bị nhân đôi.
- Làm chậm database hoặc downstream để kiểm tra timeout, bulkhead, backpressure và giới hạn concurrency.
- Gửi một record không hợp lệ để xác nhận retry hữu hạn, DLT nhận đúng record và partition tiếp tục tiến triển.
- Dừng một broker trong môi trường kiểm thử để quan sát leader election, ISR và lỗi producer.
- Tạo tình huống ISR giảm để xác nhận **min.insync.replicas** bảo vệ durability như dự kiến.
- Kiểm tra credential hết hạn hoặc ACL sai trong môi trường thử nghiệm để xác nhận cảnh báo và quy trình phục hồi.
- Diễn tập mất một AZ hoặc chuyển cluster DR nếu SLA yêu cầu khả năng đó.

Mỗi bài diễn tập cần có giả thuyết, phạm vi, điều kiện dừng, dữ liệu thử nghiệm và tiêu chí thành công. Ví dụ: “Khi mất một consumer pod, các partition của pod đó được gán lại trong thời gian mục tiêu; không mất record đã ACK; record chưa commit có thể được xử lý lại nhưng không tạo side effect trùng.”

Không chạy fault injection trên production nếu chưa có phê duyệt, giới hạn phạm vi và cơ chế dừng rõ ràng. Kết quả diễn tập cần cập nhật runbook, dashboard và ngưỡng cảnh báo.

## 13. Checklist thiết kế và vận hành

**Ứng dụng**

- [ ] Replica được phân bố qua node/AZ theo khả năng hạ tầng.
- [ ] Có readiness/liveness phù hợp và biết rõ lý do restart.
- [ ] Listener concurrency phù hợp với partition count và năng lực downstream.
- [ ] Pool, thread và queue có giới hạn; dependency có timeout.
- [ ] Commit offset phù hợp với thời điểm hoàn tất business effect.
- [ ] Business operation có idempotency key hoặc cơ chế deduplication.
- [ ] Retry hữu hạn, phân loại exception và có DLT/replay runbook.

**Kafka**

- [ ] Replication factor, min ISR và ACK policy phù hợp với yêu cầu durability.
- [ ] Replica của cùng partition được phân tán qua failure domain vật lý.
- [ ] Broker, disk, network, partition và controller/quorum có dashboard riêng.
- [ ] ACL, credential và quota được quản lý theo service/topic.
- [ ] Topic có partition count, retention và schema compatibility được quản trị.
- [ ] DLT và retry topic có replication, retention, quyền truy cập và cảnh báo.

**Toàn hệ thống**

- [ ] Có bản đồ producer → topic/partition → consumer group → downstream.
- [ ] Có thể xác định record cuối cùng được tạo, đọc, xử lý và commit.
- [ ] Có cảnh báo cho lag, record age, rebalance, retry và DLT.
- [ ] Có runbook cho broker loss, pod loss, downstream outage và credential failure.
- [ ] RPO/RTO và quy trình DR được xác định, diễn tập nếu SLA yêu cầu.
- [ ] Các bài diễn tập chứng minh được khả năng cô lập và phục hồi theo tiêu chí cụ thể.

Failure domain là công cụ để thiết kế và vận hành độ tin cậy. Khi mỗi ranh giới có phạm vi ảnh hưởng, tín hiệu quan sát, cách cô lập và quy trình phục hồi rõ ràng, một lỗi cục bộ sẽ ít có cơ hội biến thành sự cố diện rộng của toàn bộ hệ thống Spring Kafka.

