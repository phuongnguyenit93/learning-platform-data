# Metadata log, snapshot và quá trình đồng bộ metadata

Trong Kafka sử dụng **KRaft**, metadata của cluster được quản lý bằng một metadata log và một nhóm controller phối hợp theo giao thức Raft. Metadata log ghi lại các thay đổi về cấu trúc và cấu hình cluster; snapshot lưu ảnh trạng thái metadata tại một offset để node có thể khôi phục nhanh mà không phải phát lại toàn bộ lịch sử.

Hai cơ chế này giúp controller duy trì cùng một trạng thái metadata khi có thay đổi, khi controller khởi động lại hoặc khi một node bị tụt lại phía sau. Sau đó, active controller truyền metadata update đến broker để broker cập nhật metadata cache và tiếp tục phục vụ request dữ liệu.

Cần phân biệt ba luồng công việc:

1. **Replication trong controller quorum:** các controller đồng bộ metadata log bằng Raft.
2. **Khôi phục trạng thái controller:** controller nạp snapshot rồi phát lại các record metadata còn thiếu.
3. **Phân phối metadata đến broker:** active controller gửi metadata update để broker cập nhật trạng thái cục bộ.

Đây là các bước liên quan nhưng không phải cùng một cơ chế replication.

## 1. Metadata là gì và được lưu ở đâu?

Metadata mô tả cách Kafka cluster được tổ chức và vận hành. Nó không phải payload của message mà producer gửi vào topic. Metadata có thể bao gồm:

- Định danh và trạng thái đăng ký của broker.
- Topic, partition và cấu hình của chúng.
- Replica assignment, leader và các thông tin liên quan đến phân vùng.
- Cấu hình động của broker, topic và cluster.
- ACL, thông tin xác thực SCRAM và các loại cấu hình bảo mật được quản lý qua metadata.
- Feature level và các thay đổi cấu trúc cluster được hỗ trợ bởi phiên bản Kafka.

Trong kiến trúc KRaft, metadata được ghi vào một **metadata log chuyên dụng** do controller quorum quản lý. Đây là log nội bộ của control plane, không phải topic nghiệp vụ để ứng dụng tạo consumer đọc như orders hoặc payments. Metadata log có offset và lịch sử record riêng; offset của nó không liên quan đến offset của các partition dữ liệu.

Ví dụ, khi quản trị viên tạo topic orders, controller cần ghi nhận tên topic, topic ID, số partition, replication factor và replica assignment. Khi cấu hình topic thay đổi, một metadata record khác được ghi nhận. Trạng thái metadata hiện tại là kết quả áp dụng các thay đổi đã commit theo thứ tự log.

### Control plane và data plane

Có thể chia trách nhiệm của Kafka thành hai mặt:

| Thành phần | Vai trò |
|---|---|
| Controller quorum | Quản lý metadata và quyết định thay đổi cấu trúc cluster |
| Active controller | Lãnh đạo quorum, điều phối thay đổi metadata và gửi cập nhật đến broker |
| Controller follower | Replicate metadata log, theo kịp leader và duy trì trạng thái metadata |
| Broker | Lưu trữ, replicate và phục vụ record của topic dữ liệu; đồng thời giữ metadata cache để định tuyến và xử lý request |
| Producer/consumer | Gửi và đọc record theo metadata mà cluster công bố |

Broker có thể được cấu hình chỉ làm broker, chỉ làm controller hoặc đồng thời đảm nhiệm cả hai vai trò tùy kiến trúc triển khai. Trong cluster tách vai trò, các node controller chuyên trách metadata; broker nhận metadata update để biết topic và partition cần phục vụ.

## 2. Metadata log được replication bằng Raft

KRaft sử dụng một nhóm controller tạo thành **metadata quorum**. Một controller được bầu làm leader của Raft log; trong Kafka, đây là active controller. Các controller còn lại là follower hoặc observer tùy cấu hình và trạng thái tham gia quorum.

Khi có thay đổi metadata, luồng xử lý khái quát như sau:

1. Một yêu cầu quản trị hoặc thay đổi nội bộ đến active controller.
2. Active controller kiểm tra điều kiện và tạo các metadata record cần thiết.
3. Record được append vào metadata log của leader.
4. Các controller khác fetch và replicate record từ leader.
5. Khi record được xác nhận bởi đa số voter theo quy tắc Raft, record trở thành committed.
6. Các controller áp dụng record đã commit vào metadata image của mình.

Với quorum có N voter, đa số cần thiết là **floor(N / 2) + 1**. Vì vậy, quorum ba voter có thể tiếp tục commit khi một voter không khả dụng; quorum năm voter có thể chịu lỗi hai voter. Nếu mất đa số, cluster không thể tiếp tục commit thay đổi metadata mới cho đến khi quorum được khôi phục.

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi metadata<br/>Create topic / Update config"] --> L["Active controller<br/>Raft leader"]
    L --> M["Append metadata record<br/>vào metadata log"]
    M --> F1["Controller follower 1<br/>replicate log"]
    M --> F2["Controller follower 2<br/>replicate log"]
    F1 --> Q["Đủ đa số voter xác nhận"]
    F2 --> Q
    M --> Q
    Q --> C["Record được commit"]
    C --> I1["Metadata image<br/>Controller 1"]
    C --> I2["Metadata image<br/>Controller 2"]
    C --> I3["Metadata image<br/>Controller 3"]
    C --> B["Active controller gửi<br/>metadata update đến broker"]
~~~

Ví dụ với ba controller voter:

~~~text
controller-1: leader
controller-2: follower
controller-3: follower

Một metadata record được append:
  controller-1: append thành công
  controller-2: replicate thành công
  controller-3: đang mất kết nối

Đã có 2/3 voter xác nhận:
  majority = 2
  record có thể được commit
~~~

Đây là ví dụ minh họa điều kiện đa số. Việc append thành công trên leader đơn lẻ chưa đủ để coi một thay đổi metadata là đã commit. Leader epoch và các quy tắc bầu chọn Raft giúp ngăn leader cũ tiếp tục quyết định trạng thái sau khi quyền lãnh đạo đã chuyển sang node khác.

### Offset và high watermark của metadata log

Metadata log có offset để xác định vị trí record. Hai mốc thường cần phân biệt:

- **Log end offset (LEO):** vị trí cuối mà một replica đã append vào log; replica khác nhau có thể có LEO khác nhau.
- **High watermark (HW):** mốc metadata đã được commit theo quorum. Controller áp dụng trạng thái committed làm trạng thái metadata có hiệu lực.

Do đó, LEO cao hơn HW không tự động có nghĩa mọi record ở phần đuôi đã được commit. Khi leader thay đổi, phần log chưa commit có thể được xử lý theo quy tắc đồng bộ và phục hồi của Raft. Không nên dùng một offset nhìn thấy trên một controller để kết luận toàn cluster đã áp dụng thay đổi.

## 3. Metadata image và snapshot khác nhau thế nào?

**Metadata image** là biểu diễn trạng thái metadata hiện tại mà controller dùng trong bộ nhớ. Nó được tạo bằng cách áp dụng các metadata record theo thứ tự. Ví dụ, sau khi áp dụng record tạo topic, thêm partition và cập nhật cấu hình, image phản ánh topic cùng cấu hình mới nhất.

**Metadata snapshot** là bản lưu bền vững của metadata image tại một vị trí xác định trong metadata log. Snapshot ghi nhận trạng thái đã được xây dựng đến một metadata offset, nhờ vậy controller có thể nạp trạng thái gần nhất thay vì phát lại log từ đầu.

| Khái niệm | Nội dung | Mục đích |
|---|---|---|
| Metadata log | Chuỗi record mô tả thay đổi metadata | Replication, commit và lưu lịch sử thay đổi |
| Metadata image | Trạng thái hiện tại sau khi áp dụng record | Phục vụ controller xử lý metadata |
| Metadata snapshot | Bản lưu image tại một offset | Rút ngắn thời gian khôi phục và đồng bộ node |

Giả sử metadata log có các thay đổi từ offset 0 đến 12.000. Snapshot được tạo tại offset 10.000. Khi khởi động lại, controller có thể nạp snapshot đó rồi phát lại các record sau snapshot để dựng image đến trạng thái mới nhất đã commit.

~~~text
Metadata log:
0 -------------------------------------------- 12.000
                         |
                         +-- Snapshot tại offset 10.000

Khôi phục:
1. Nạp snapshot đến offset 10.000
2. Replay record sau offset snapshot
3. Áp dụng đến metadata offset đã commit
4. Hoàn tất metadata image hiện tại
~~~

Snapshot là ảnh trạng thái, không phải bản sao dữ liệu của các topic nghiệp vụ. Nó không chứa payload của orders hoặc payments. Nó cũng không thay thế cơ chế Raft replication: các controller vẫn cần duy trì metadata log và quorum để thống nhất thay đổi mới.

### Vì sao cần snapshot?

Nếu cluster hoạt động lâu, metadata log có thể tích lũy nhiều record. Nếu mỗi lần controller khởi động đều phải phát lại toàn bộ log, thời gian khôi phục sẽ tăng theo lượng lịch sử cần xử lý.

Snapshot giúp:

- **Khởi động nhanh hơn:** nạp một trạng thái đã tổng hợp thay vì replay từ đầu.
- **Giảm lượng log cần replay:** chỉ cần áp dụng các record sau offset snapshot.
- **Hỗ trợ follower tụt xa:** khi follower không còn phần log cần thiết để bắt kịp, snapshot phù hợp có thể giúp follower dựng lại image rồi tiếp tục fetch phần log mới hơn.
- **Giảm áp lực lưu trữ lịch sử cũ:** snapshot cùng cơ chế retention/cleanup metadata log giúp hệ thống quản lý phần log cần thiết.

Snapshot được tạo và sử dụng theo chính sách nội bộ của Kafka. Không nên giả định mỗi lần có một record mới thì Kafka tạo ngay một snapshot, hoặc mọi controller đều có cùng snapshot file tại cùng thời điểm.

## 4. Quá trình đồng bộ metadata khi controller khởi động

Khi một controller khởi động, nó cần biết trạng thái metadata đã commit của cluster trước khi có thể tham gia đầy đủ vào công việc điều khiển. Luồng khôi phục khái quát gồm các bước:

1. **Đọc metadata storage:** controller mở metadata log và các snapshot hợp lệ trong storage directory được cấu hình.
2. **Nạp snapshot mới nhất có thể sử dụng:** snapshot cung cấp metadata image đến một offset xác định.
3. **Replay log sau snapshot:** controller đọc các record metadata tiếp theo theo thứ tự và áp dụng vào image.
4. **Bắt kịp quorum:** nếu node còn thiếu record so với leader, nó tiếp tục fetch và replicate log; nếu log cần thiết không còn sẵn, cơ chế snapshot có thể được dùng để đưa node đến một mốc phù hợp.
5. **Theo dõi commit mới:** controller tiếp tục nhận các record mới, cập nhật trạng thái và tham gia vai trò voter/observer theo cấu hình và trạng thái quorum.

~~~mermaid
flowchart TD
    S["Controller khởi động"] --> D["Mở metadata storage"]
    D --> N{"Có snapshot hợp lệ?"}
    N -->|Có| L["Nạp metadata image từ snapshot"]
    N -->|Không| E["Dựng image từ log còn khả dụng"]
    L --> R["Replay metadata record sau snapshot"]
    E --> R
    R --> C{"Đã bắt kịp committed log?"}
    C -->|Chưa| F["Fetch record hoặc snapshot từ leader"]
    F --> R
    C -->|Rồi| I["Metadata image đồng bộ"]
    I --> Q["Tiếp tục tham gia metadata quorum"]
~~~

Trong thực tế, các bước có thể được phối hợp và thực hiện theo cơ chế nội bộ của Kafka; sơ đồ thể hiện trình tự logic để người học hiểu quá trình khôi phục.

### Khi follower bị tụt lại phía sau

Giả sử controller follower ngừng hoạt động trong một thời gian. Trong lúc đó, leader tiếp tục commit metadata record và log được quản lý theo chính sách retention. Khi follower quay lại:

- Nếu phần record mà follower còn thiếu vẫn có thể fetch từ leader, follower tải record, append và áp dụng chúng.
- Nếu follower tụt quá xa và phần log cần thiết đã bị loại bỏ khỏi phạm vi log có thể fetch, leader có thể cung cấp snapshot tại một offset phù hợp.
- Follower nạp snapshot, sau đó tiếp tục đồng bộ các record sau snapshot để bắt kịp trạng thái committed hiện tại.

Không phải snapshot bất kỳ nào cũng đủ để follower bắt kịp. Snapshot cần thuộc đúng cluster, hợp lệ và có offset phù hợp với tiến trình đồng bộ. Node không được tự ý lấy snapshot từ một cluster khác hoặc trộn snapshot không tương thích với metadata log của mình.

## 5. Active controller phân phối metadata đến broker

Replication của metadata log giữa các controller không đồng nghĩa broker cũng tham gia replicate Raft log. Broker nhận metadata update từ active controller và cập nhật metadata cache cục bộ.

Ví dụ, khi topic orders được tạo và metadata thay đổi đã commit:

1. Active controller cập nhật metadata image.
2. Controller gửi metadata update đến các broker liên quan.
3. Broker áp dụng các thay đổi vào metadata cache.
4. Broker biết topic có những partition nào, replica nào được giao, partition leader là ai và cấu hình liên quan ra sao.
5. Producer và consumer nhận thông tin metadata qua giao thức Kafka để gửi request đến đúng broker.

Metadata update có thể được truyền dưới dạng thay đổi gia tăng (delta) hoặc trạng thái cần thiết theo giao thức và phiên bản Kafka. Broker có thể cần đồng bộ lại khi khởi động hoặc khi phát hiện mình không theo kịp các thay đổi.

~~~mermaid
flowchart LR
    Q["Controller quorum<br/>metadata log + snapshot"] --> A["Active controller<br/>metadata image"]
    A --> U1["Metadata update"]
    A --> U2["Metadata update"]
    U1 --> B1["Broker 1<br/>metadata cache"]
    U1 --> B2["Broker 2<br/>metadata cache"]
    U2 --> B3["Broker 3<br/>metadata cache"]
    B1 --> P["Producer / Consumer"]
    B2 --> P
    B3 --> P
~~~

Metadata cache giúp broker xử lý request mà không phải truy vấn controller cho mọi message. Tuy nhiên, metadata có thể cần thời gian ngắn để lan truyền sau khi thay đổi đã commit. Ứng dụng nên xử lý các lỗi tạm thời như leader chưa sẵn sàng hoặc metadata chưa được cập nhật, theo cơ chế retry phù hợp của Kafka client.

## 6. Điều gì xảy ra khi active controller gặp sự cố?

Khi active controller mất kết nối hoặc dừng hoạt động, các voter còn lại tiến hành bầu leader mới theo Raft. Controller leader mới tiếp tục với metadata log đã được đồng bộ và các record đã commit.

Một số hệ quả vận hành:

- Nếu quorum còn đa số voter và bầu được leader, cluster có thể tiếp tục commit thay đổi metadata.
- Nếu quorum mất đa số, không thể commit thay đổi metadata mới. Các thao tác quản trị như tạo topic, thay đổi cấu hình hoặc thay đổi assignment có thể bị gián đoạn.
- Broker có thể tiếp tục phục vụ một phần hoạt động dữ liệu dựa trên metadata và leadership hiện có, nhưng các hoạt động cần controller hoặc cần metadata mới có thể bị ảnh hưởng.
- Khi controller quay lại, nó cần đồng bộ metadata log và image theo trạng thái quorum hiện tại trước khi đảm nhiệm lại vai trò cần thiết.

Không nên xử lý lỗi controller bằng cách xóa metadata storage hoặc tự sao chép file snapshot giữa các node. Những hành động này có thể phá hủy dữ liệu Raft hoặc làm node không còn thuộc đúng lịch sử cluster. Hãy khôi phục node theo hướng dẫn vận hành của phiên bản Kafka đang chạy và xác minh cluster ID, node ID, voter configuration cùng metadata directory.

## 7. Quan sát trạng thái metadata quorum

Kafka cung cấp công cụ dòng lệnh để quan sát metadata quorum. Tùy phiên bản Kafka, cách gọi và các trường hiển thị có thể khác nhau. Với các phiên bản hỗ trợ lệnh tương ứng, có thể kiểm tra trạng thái qua:

~~~bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-server broker-1:9092 \
  describe --status
~~~

Lệnh trên cung cấp thông tin tổng quan như leader hiện tại, leader epoch, high watermark và danh sách voter/observer. Để quan sát tình trạng replication của các node, có thể dùng:

~~~bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-server broker-1:9092 \
  describe --replication
~~~

Khi đọc kết quả, chú ý các dấu hiệu:

| Thông tin | Ý nghĩa khi kiểm tra |
|---|---|
| LeaderId | Node đang lãnh đạo metadata quorum |
| LeaderEpoch | Thế hệ lãnh đạo hiện tại; thay đổi khi có lần bầu leader mới |
| HighWatermark | Mốc metadata log đã commit |
| LogEndOffset | Mốc log mà một node đã append |
| Lag | Khoảng cách đồng bộ của replica so với leader |
| Voter / Observer | Vai trò của node trong metadata quorum |
| LastCaughtUpTimestamp | Thời điểm node được ghi nhận là đã bắt kịp leader, nếu công cụ phiên bản đó hiển thị |

Các con số cần được xem theo thời gian và tương quan giữa các node. Một follower có lag nhỏ trong thời gian ngắn có thể là bình thường; lag tăng liên tục, voter không bắt kịp hoặc leader thay đổi liên tục là dấu hiệu cần điều tra network, disk I/O, CPU hoặc tình trạng node.

## 8. Nguyên tắc vận hành và các nhầm lẫn thường gặp

**Không đồng nhất metadata log với topic dữ liệu.** Metadata log lưu trạng thái điều khiển của cluster; topic dữ liệu lưu record nghiệp vụ. Chúng có mục đích, offset và cơ chế quản lý khác nhau.

**Không đồng nhất snapshot với backup đầy đủ của Kafka.** Snapshot metadata không chứa toàn bộ segment dữ liệu của các topic. Muốn bảo vệ dữ liệu nghiệp vụ, vẫn cần replication và chiến lược backup/restore phù hợp cho data log.

**Không coi LEO là committed offset.** Log end offset có thể vượt high watermark. Chỉ metadata đã commit mới được xem là trạng thái có hiệu lực của quorum.

**Không giả định broker replicate Raft metadata log.** Controller quorum replicate metadata log; broker nhận metadata update và duy trì cache để phục vụ hoạt động dữ liệu.

**Không xóa metadata directory để ép đồng bộ.** Metadata storage chứa lịch sử và trạng thái cần thiết cho Raft. Hãy điều tra quorum, log, snapshot và cấu hình node trước khi thực hiện bất kỳ thao tác khôi phục nào.

**Giữ quorum đủ khả năng chịu lỗi.** Với cluster production, thường dùng số voter lẻ như ba hoặc năm để có đa số rõ ràng và khả năng chịu lỗi dự kiến. Đặt controller trên các failure domain phù hợp để một sự cố máy chủ hoặc vùng mạng không làm mất đa số cùng lúc.

**Theo dõi lag và khả năng lưu trữ.** Controller cần đủ dung lượng và I/O để append, replicate metadata log và tạo snapshot. Khi lag tăng hoặc snapshot không được tạo như kỳ vọng, thời gian khởi động lại và phục hồi follower có thể tăng.

Các cấu hình điều khiển snapshot và retention metadata có thể khác nhau theo phiên bản Kafka. Trước khi thay đổi ngưỡng tạo snapshot, thời gian giữ metadata hoặc giới hạn lưu trữ, hãy đối chiếu tài liệu đúng phiên bản và đo tác động đến khả năng bắt kịp của controller.

## 9. Tự kiểm tra cách hiểu

1. Metadata log lưu loại dữ liệu nào? — Các thay đổi về cấu trúc và cấu hình cluster, không phải payload của topic nghiệp vụ.
2. Ai replicate metadata log trong KRaft? — Các controller tham gia metadata quorum theo giao thức Raft.
3. Khi nào một metadata record được xem là committed? — Khi đạt điều kiện xác nhận của đa số voter theo Raft.
4. Metadata snapshot dùng để làm gì? — Lưu metadata image tại một offset để giảm lượng log cần replay khi khởi động hoặc đồng bộ.
5. Khi controller khởi động, nó thường làm gì với snapshot và log? — Nạp snapshot phù hợp, replay các record sau snapshot và bắt kịp committed log.
6. Broker có trực tiếp replicate Raft metadata log không? — Không; broker nhận metadata update từ active controller và cập nhật metadata cache.
7. Nếu quorum mất đa số, điều gì bị ảnh hưởng trước tiên? — Quorum không thể commit thay đổi metadata mới cho đến khi khôi phục được đa số.
8. Snapshot metadata có thay thế backup dữ liệu topic không? — Không; snapshot chỉ lưu trạng thái metadata.

Metadata log, snapshot và quá trình đồng bộ tạo thành nền tảng để KRaft giữ control plane nhất quán qua khởi động lại, follower lag và sự cố controller. Khi vận hành cluster, hãy quan sát leader, high watermark, replication lag và trạng thái snapshot; đồng thời luôn phân biệt đồng bộ giữa controller với phân phối metadata đến broker.

