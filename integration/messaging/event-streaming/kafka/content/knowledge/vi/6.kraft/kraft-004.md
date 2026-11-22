# Raft, bầu leader và điều kiện đạt quorum

## Mục tiêu bài học

KRaft dùng giao thức Raft để nhiều controller của Kafka thống nhất metadata của cluster mà không cần ZooKeeper. Để hiểu khả năng chịu lỗi của KRaft, cần nắm cách Raft bầu leader, sao chép log, xác định entry đã commit và vì sao một nhóm node phải có đa số thành viên liên lạc được.

Sau bài học, bạn có thể:

- Giải thích vai trò của leader, follower, term, log replication và commit index trong Raft.
- Tính số phiếu cần thiết để một controller quorum đạt majority và số node có thể mất mà vẫn tiếp tục hoạt động.
- Mô tả quá trình bầu leader khi controller hiện tại gặp sự cố hoặc mạng bị phân vùng.
- Phân biệt controller quorum của KRaft với leader/ISR của partition dữ liệu.
- Đọc trạng thái metadata quorum và nhận diện các dấu hiệu mất quorum.
- Lựa chọn số lượng, vị trí và cấu hình controller phù hợp với yêu cầu chịu lỗi.

## 1. Vì sao KRaft cần consensus?

Một Kafka cluster có nhiều broker và nhiều partition. Các broker phải cùng hiểu một trạng thái metadata nhất quán, chẳng hạn:

- Broker nào đang tham gia cluster và broker nào đã rời cluster.
- Topic nào tồn tại, topic có bao nhiêu partition và replica được phân bổ ở đâu.
- Broker nào đang là leader của từng partition.
- Cấu hình topic, ACL và các thông tin quản trị liên quan.
- Thay đổi nào đã được chấp nhận và thứ tự các thay đổi đó.

Nếu mỗi broker tự quyết định metadata theo cách riêng, các node có thể nhìn thấy những trạng thái mâu thuẫn. Ví dụ, hai broker cùng tin mình là controller đang hoạt động hoặc một số broker áp dụng thay đổi topic trong khi các broker khác chưa biết thay đổi đó.

KRaft giải quyết bài toán này bằng một nhóm controller duy trì **metadata log**. Nhóm controller sử dụng Raft để thống nhất thứ tự các thay đổi metadata. Tại một thời điểm, một controller là leader của metadata quorum; các controller còn lại theo dõi và sao chép log.

KRaft là viết tắt của Kafka Raft. Cơ chế này thay thế vai trò điều phối metadata trước đây do ZooKeeper đảm nhiệm. Raft là thuật toán consensus chịu lỗi crash và lỗi mạng; nó không phải giao thức chịu được node cố ý gửi dữ liệu giả mạo theo mô hình Byzantine.

## 2. Các thành phần và thuật ngữ của Raft

### 2.1. Leader và follower

Một Raft group có một leader được bầu và các follower. Leader điều phối việc thêm entry vào log; follower nhận bản sao log và phản hồi tiến độ replication.

Trong KRaft:

- **Active controller** là leader của metadata quorum. Nó xử lý các thay đổi metadata và điều phối trạng thái cluster.
- **Standby controllers** là follower của metadata quorum. Chúng sao chép metadata log và có thể trở thành active controller khi leader hiện tại không còn hoạt động.
- **Broker** phục vụ producer/consumer và lưu các partition dữ liệu. Một tiến trình Kafka có thể chạy vai trò broker, controller hoặc kết hợp cả hai tùy cấu hình triển khai.

Ví dụ một quorum có ba controller:

```text
              KRaft metadata quorum

       Controller 1       Controller 2       Controller 3
          LEADER             FOLLOWER           FOLLOWER
             |                  ^                  ^
             |---- append ------|------------------|
             |                  |                  |
             +------ commit after majority -------+
```

Chỉ có một leader hợp lệ cho một term của quorum. Khi leader không còn liên lạc được với đa số, nó không thể tiếp tục commit metadata entry mới. Một leader mới cần được bầu theo term mới.

### 2.2. Term và election

**Term** là số thế hệ bầu chọn tăng dần. Mỗi lần một cuộc bầu chọn mới bắt đầu, term được tăng lên. Term giúp các node nhận ra thông tin leader cũ đã lỗi thời.

Một node có thể ở các trạng thái:

- **Follower:** nhận heartbeat và log replication từ leader.
- **Candidate:** bắt đầu election, tăng term và xin phiếu từ các node khác.
- **Leader:** đã nhận đủ phiếu majority và điều phối log replication trong term hiện tại.

Nếu follower không nhận được heartbeat trong khoảng thời gian election timeout, nó có thể chuyển sang candidate và khởi động bầu chọn. Timeout không có nghĩa node chắc chắn đã chết; mạng chậm hoặc JVM pause cũng có thể khiến heartbeat đến trễ.

### 2.3. Log, commit index và state machine

Raft duy trì một log có thứ tự. Leader nhận entry mới, append vào log của mình rồi gửi entry đến follower. Khi entry đã được sao chép đủ điều kiện theo quorum, nó được xem là committed. Các node áp dụng entry đã commit vào state machine theo đúng thứ tự log.

Ba khái niệm cần phân biệt:

- **Appended:** entry đã được ghi vào log của một node, nhưng có thể chưa được quorum xác nhận.
- **Replicated:** entry đã được sao chép đến một hoặc nhiều follower.
- **Committed:** entry đã thỏa điều kiện commit của Raft; các node có thể áp dụng entry vào trạng thái metadata đã thống nhất.

Một entry chỉ xuất hiện trên leader chưa đủ để coi là bền vững theo quorum. Nếu leader lỗi trước khi entry được commit, leader mới có thể không giữ entry đó. Vì vậy, ứng dụng quản trị không nên đồng nhất việc gửi request thành công ở một điểm mạng với việc thay đổi metadata đã được commit.

Trong Raft chuẩn, commit index biểu thị vị trí cao nhất trong log đã được xác nhận commit. Raft còn có quy tắc an toàn liên quan đến term: leader không chỉ dựa vào việc một entry cũ được sao chép đến đa số để commit entry đó trực tiếp; commit entry thuộc term hiện tại theo điều kiện quorum sẽ giúp bảo đảm các entry trước đó được giữ đúng quy tắc. Kafka triển khai Raft cho metadata quorum với các chi tiết riêng của giao thức và phiên bản.

## 3. Quá trình bầu leader

### 3.1. Election khi leader không còn phản hồi

Một cuộc bầu chọn đơn giản diễn ra theo trình tự:

1. Follower không nhận heartbeat trong khoảng timeout và nghi ngờ leader không còn hoạt động.
2. Follower chuyển thành candidate, tăng term và bỏ phiếu cho chính mình.
3. Candidate gửi yêu cầu vote đến các thành viên khác.
4. Thành viên nhận vote request kiểm tra term và mức độ cập nhật của log candidate.
5. Nếu candidate nhận được phiếu từ đa số thành viên, nó trở thành leader của term đó.
6. Leader mới gửi heartbeat để các follower biết leader hiện tại và tiếp tục replication.

Điều kiện log freshness rất quan trọng. Một candidate có log quá cũ không được phép thắng chỉ vì gửi yêu cầu vote trước. Các node chỉ bỏ phiếu theo quy tắc Raft, trong đó term và trạng thái log được so sánh để bảo vệ các entry đã commit.

### 3.2. Vì sao không có hai leader hợp lệ cùng term?

Một node chỉ bỏ phiếu tối đa cho một candidate trong một term theo quy tắc bầu chọn. Hai candidate khác nhau không thể đồng thời nhận được majority trong cùng một tập thành viên nếu hai majority phải giao nhau.

Ví dụ quorum có 3 voter, majority là 2:

```text
Nhóm phiếu có thể thắng:
  Candidate A: Controller 1 + Controller 2 = 2 phiếu
  Candidate B: Controller 2 + Controller 3 = 2 phiếu

Hai nhóm cùng chứa Controller 2.
Controller 2 không thể bỏ phiếu cho cả A và B trong cùng term.
```

Với một quorum ổn định, hai majority bất kỳ luôn giao nhau. Kết hợp với quy tắc một phiếu mỗi term và kiểm tra log freshness, Raft ngăn hai leader hợp lệ cùng commit các nhánh log mâu thuẫn.

### 3.3. Split brain và network partition

Network partition xảy ra khi một nhóm node không thể liên lạc với nhóm còn lại. Ví dụ ba controller bị chia thành nhóm hai node và nhóm một node.

- Nhóm hai node có thể đạt majority, bầu leader và tiếp tục commit metadata nếu các điều kiện khác đáp ứng.
- Nhóm một node không có majority, nên không thể bầu leader hợp lệ hoặc commit metadata mới.
- Nếu leader cũ nằm ở nhóm thiểu số, nó mất khả năng commit. Khi nhận biết term mới, nó phải theo leader mới.

Đây là cách Raft tránh split brain ở tầng consensus. Nhóm thiểu số có thể vẫn đang chạy process và có thể giữ một phần dữ liệu local, nhưng nó không có quyền quyết định metadata mới cho toàn cluster.

## 4. Điều kiện đạt quorum

### 4.1. Majority là gì?

Một quorum Raft thông thường cần **đa số nghiêm ngặt** của tổng số voter:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Trong đó:

- `N` là tổng số voter được cấu hình trong quorum.
- `Q` là số voter tối thiểu phải tham gia để đạt majority.

Không phải chỉ cần một nửa. Với bốn voter, ba phiếu mới là majority; hai phiếu chỉ bằng một nửa và không đủ.

### 4.2. Số node lỗi có thể chịu được

Nếu quorum có `N` voter và cần `Q` voter để hoạt động, số voter có thể mất tối đa mà vẫn còn majority là:

\[
f = N - Q = \left\lfloor \frac{N-1}{2} \right\rfloor
\]

Bảng ví dụ:

| Số voter (N) | Majority (Q) | Số voter có thể mất (f) | Khả năng còn quorum |
|---:|---:|---:|---|
| 1 | 1 | 0 | Mất node duy nhất là mất quorum |
| 2 | 2 | 0 | Cả hai phải hoạt động |
| 3 | 2 | 1 | Có thể mất một voter |
| 4 | 3 | 1 | Có thể mất một voter |
| 5 | 3 | 2 | Có thể mất hai voter |
| 6 | 4 | 2 | Có thể mất hai voter |
| 7 | 4 | 3 | Có thể mất ba voter |

Vì vậy, các quorum có số voter lẻ thường được chọn. Bốn voter không tăng khả năng chịu lỗi so với ba voter, nhưng lại cần ba phiếu thay vì hai. Tương tự, sáu voter không chịu được nhiều lỗi hơn năm voter.

### 4.3. Ví dụ quorum ba controller

Với ba controller voter, quorum cần hai node:

```text
Trạng thái bình thường:
  C1 leader + C2 follower + C3 follower
  3/3 node liên lạc được -> đạt quorum

Một controller lỗi:
  C1 leader + C2 follower + C3 down
  2/3 node liên lạc được -> vẫn đạt quorum

Hai controller lỗi:
  C1 down + C2 down + C3 còn lại
  1/3 node liên lạc được -> mất quorum
```

Khi leader C1 lỗi nhưng C2 và C3 còn liên lạc, một trong hai có thể được bầu làm leader mới. Trong khoảng thời gian election, các thao tác cần commit metadata có thể bị chậm hoặc thất bại tạm thời. Sau khi leader mới ổn định, quorum có thể tiếp tục.

### 4.4. Quorum cần cả số lượng và khả năng liên lạc

Có đủ process đang chạy chưa chắc đã đạt quorum. Các voter phải liên lạc được với nhau qua controller listener và có thể trao đổi vote/replication request.

Ví dụ, cả ba controller đều đang chạy nhưng firewall chặn kết nối giữa C1 với C2 và C3, trong khi C2 và C3 liên lạc được. Nhóm C2+C3 có majority nên có thể tiếp tục; C1 ở phía thiểu số không thể commit. Nếu cả ba node đều bị cô lập hoàn toàn, cluster không có majority giao tiếp được.

Các yếu tố có thể làm quorum không đạt:

- Controller process bị dừng hoặc crash.
- Mạng giữa controller bị lỗi, mất route hoặc firewall chặn.
- DNS/hostname của controller listener không phân giải đúng.
- Controller quá tải CPU, disk hoặc GC khiến heartbeat và replication bị trễ.
- Disk metadata log lỗi hoặc không còn đủ dung lượng.
- Cấu hình voter, node ID hoặc listener không nhất quán.

## 5. KRaft controller quorum và partition replication là hai cơ chế khác nhau

Đây là điểm quan trọng nhất khi đọc trạng thái Kafka. Cả hai cơ chế đều có leader và follower, nhưng quản lý hai loại dữ liệu khác nhau và dùng điều kiện quyết định khác nhau.

| Khía cạnh | KRaft controller quorum | Partition replication |
|---|---|---|
| Mục đích | Thống nhất metadata của cluster | Sao chép record dữ liệu của topic partition |
| Log | Metadata log của controller quorum | Log dữ liệu riêng của từng partition |
| Leader | Active controller của quorum | Leader replica của một partition |
| Follower | Standby controller | Follower replica trong các broker |
| Cơ chế điều phối | Raft consensus và majority voter | Kafka partition replication, ISR và leader election |
| Điều kiện commit/xác nhận | Majority voter của metadata quorum | Theo ISR, `acks`, `min.insync.replicas` và cấu hình producer/broker |
| Phạm vi | Metadata cluster | Một partition cụ thể |

Controller quorum Raft không sao chép payload của mọi topic vào metadata log. Record nghiệp vụ vẫn được lưu trên partition replica ở broker. Tương tự, ISR của một partition không phải là voter của controller quorum.

### 5.1. Leader của metadata quorum

Active controller là leader của Raft quorum. Khi một broker đăng ký, topic được tạo hoặc partition assignment thay đổi, controller xử lý metadata change và ghi vào metadata log. Thay đổi chỉ được áp dụng như metadata đã commit khi thỏa điều kiện consensus của quorum.

Nếu controller quorum mất majority, cluster không thể commit metadata change mới. Các thao tác quản trị và những quyết định control plane cần controller có thể bị gián đoạn. Một số luồng dữ liệu hiện hữu vẫn có thể tiếp tục nếu partition leader và replica liên quan vẫn hoạt động; tuy nhiên, việc bầu lại partition leader hoặc áp dụng thay đổi cluster có thể bị ảnh hưởng do control plane không có quorum.

### 5.2. Leader của partition dữ liệu

Mỗi partition có một leader replica và có thể có follower replica. Producer gửi record đến leader. Follower fetch dữ liệu từ leader và Kafka theo dõi tập replica đồng bộ gọi là ISR (in-sync replicas).

Khi partition leader lỗi, controller sử dụng trạng thái replica và chính sách leader election để chọn leader mới. Đây là quyết định về một partition, không phải cuộc bầu leader Raft của controller quorum.

Với producer `acks=all`, broker xác nhận ghi theo trạng thái ISR. `min.insync.replicas` đặt ngưỡng ISR tối thiểu để chấp nhận ghi. Ví dụ RF=3 và `min.insync.replicas=2` cho phép ghi khi có ít nhất hai replica trong ISR; nếu ISR giảm xuống dưới ngưỡng, ghi có thể bị từ chối. Điều này khác với quorum controller ba voter cần hai phiếu để commit metadata.

### 5.3. Hai lớp có thể ảnh hưởng lẫn nhau nhưng không thể thay thế nhau

Một cluster có thể có metadata quorum khỏe nhưng một partition mất toàn bộ replica đủ điều kiện, khiến partition đó offline. Ngược lại, các partition có thể vẫn có leader và replica hoạt động trong lúc controller quorum gặp sự cố; các luồng dữ liệu hiện hữu có thể tiếp tục trong giới hạn trạng thái đã có, nhưng cluster mất khả năng thực hiện nhiều thay đổi control plane.

Do đó, khi thấy lỗi “quorum”, hãy xác định đó là:

- Metadata controller quorum không có majority.
- ISR của một partition thấp hơn `min.insync.replicas`.
- Partition không có replica đủ điều kiện để làm leader.
- Một consumer group hoặc hệ thống khác đang dùng thuật ngữ quorum theo ngữ cảnh riêng.

Không xử lý mọi trường hợp bằng cách tăng replication factor hoặc thêm controller một cách tùy tiện.

## 6. Chọn số lượng và vị trí controller

### 6.1. Số lượng voter

Với production cần chịu lỗi, ba voter là cấu hình phổ biến để chịu được một controller failure; năm voter có thể chịu được hai controller failure nhưng tăng chi phí vận hành và yêu cầu majority lên ba.

Không phải cứ tăng số controller là cluster luôn khỏe hơn. Số voter cần được chọn theo số lỗi đồng thời cần chịu, latency giữa các failure domain và khả năng vận hành. Quorum phải duy trì majority trong các tình huống bảo trì, nâng cấp hoặc mất một vùng hạ tầng.

### 6.2. Phân tán theo failure domain

Ba controller đặt trên cùng một máy vật lý hoặc cùng một availability zone có thể cùng mất khi zone hoặc host gặp sự cố. Để tận dụng khả năng chịu lỗi của quorum, hãy phân tán voter trên các failure domain độc lập, ví dụ ba rack hoặc ba availability zone khi hạ tầng cho phép.

Đồng thời, cần đảm bảo:

- Controller listener có DNS, route và firewall ổn định giữa các voter.
- CPU và RAM đủ để controller xử lý metadata và heartbeat đúng hạn.
- Metadata log nằm trên storage bền vững, có dung lượng và I/O phù hợp.
- Đồng hồ hệ thống được đồng bộ để log và điều tra sự cố dễ hơn, dù Raft không dùng timestamp wall-clock để xác định thứ tự log.
- Quy trình nâng cấp không dừng quá nhiều voter cùng lúc làm mất majority.

### 6.3. Dedicated controller và combined broker/controller

Kafka có thể chạy node chỉ làm controller hoặc node kết hợp broker và controller, tùy cách triển khai và phiên bản.

- **Dedicated controller** tách tải control plane khỏi tải producer/consumer và disk I/O của broker. Cách này thường phù hợp cluster production lớn hoặc yêu cầu cô lập tài nguyên.
- **Combined broker/controller** tiết kiệm tài nguyên và đơn giản cho môi trường local, development hoặc cluster nhỏ. Tuy nhiên, broker quá tải có thể ảnh hưởng đến controller cùng process.

Không nên lấy cấu hình combined của lab làm mặc định cho production có tải lớn. Quyết định cần dựa trên tài nguyên, topology, failure domain và hướng dẫn triển khai của phiên bản Kafka đang sử dụng.

## 7. Cấu hình và quan sát KRaft quorum

### 7.1. Nhận diện node controller

Trong KRaft, `process.roles` xác định vai trò của tiến trình. Ví dụ một node controller chuyên dụng có thể dùng:

```properties
process.roles=controller
node.id=1
controller.listener.names=CONTROLLER
listeners=CONTROLLER://controller-1.example.internal:9093
```

Các node broker có thể dùng `process.roles=broker`; node kết hợp có thể dùng `process.roles=broker,controller` nếu mô hình triển khai cho phép.

Khai báo thành viên quorum phụ thuộc chế độ quorum và phiên bản Kafka. Với cấu hình static quorum ở các phiên bản dùng `controller.quorum.voters`, danh sách voter có dạng:

```properties
controller.quorum.voters=1@controller-1.example.internal:9093,2@controller-2.example.internal:9093,3@controller-3.example.internal:9093
```

Các phiên bản Kafka mới hỗ trợ dynamic controller quorum và dùng cơ chế bootstrap/cấu hình thành viên khác, chẳng hạn `controller.quorum.bootstrap.servers`. Không trộn cấu hình static và dynamic; hãy dùng đúng tài liệu cho phiên bản Kafka và quy trình format storage của cluster. `node.id` phải duy nhất trong cluster và listener controller phải có thể được các voter truy cập.

### 7.2. Kiểm tra trạng thái quorum

Kafka cung cấp công cụ `kafka-metadata-quorum.sh` để quan sát metadata quorum. Ví dụ:

```bash
kafka-metadata-quorum.sh \
  --bootstrap-server localhost:9092 \
  describe --status
```

Lệnh này có thể hiển thị các thông tin như:

- `LeaderId`: node đang làm leader của metadata quorum.
- `LeaderEpoch`: term/epoch của leader hiện tại.
- `HighWatermark`: vị trí metadata log đã commit theo quorum.
- Danh sách voter và trạng thái liên quan.

Để xem tiến độ replication của metadata quorum:

```bash
kafka-metadata-quorum.sh \
  --bootstrap-server localhost:9092 \
  describe --replication
```

Tên trường và cách hiển thị có thể khác theo phiên bản Kafka. Hãy đọc cả leader, epoch, high watermark và độ trễ log của follower; chỉ thấy một `LeaderId` không đủ để kết luận toàn bộ voter đang khỏe.

### 7.3. Dấu hiệu cảnh báo

Theo dõi các dấu hiệu sau:

- Không có leader của metadata quorum hoặc election lặp lại liên tục.
- Follower metadata log tụt xa high watermark.
- Controller listener có lỗi kết nối hoặc timeout.
- Controller CPU, GC pause hoặc disk latency tăng cao.
- Metadata change request timeout hoặc thất bại.
- Voter thường xuyên mất kết nối rồi gia nhập lại.

Một election đơn lẻ sau khi chủ động dừng leader có thể là hành vi bình thường. Election lặp lại không giải thích được thường cho thấy mạng, tài nguyên hoặc cấu hình quorum cần được điều tra.

## 8. Điều gì xảy ra khi mất quorum?

Khi số voter liên lạc được thấp hơn majority:

1. Không candidate nào có thể nhận đủ phiếu để trở thành leader hợp lệ.
2. Leader cũ không thể commit metadata entry mới vì không thể xác nhận majority.
3. Các thao tác quản trị cần cập nhật metadata có thể timeout hoặc thất bại.
4. Cluster không thể thực hiện đầy đủ các thay đổi control plane, ví dụ xử lý một số thay đổi broker/partition assignment hoặc bầu lại partition leader khi cần quyết định từ controller.
5. Sau khi khôi phục liên lạc với đủ voter, election có thể diễn ra và quorum tiếp tục từ metadata log đã được commit.

Không nên tự ý xóa metadata log, thay đổi voter list hoặc format lại storage để “khởi động lại quorum”. Các thao tác đó có thể làm mất trạng thái metadata đã commit hoặc tạo ra một cluster không còn cùng lịch sử. Trước tiên, xác định node nào còn dữ liệu, voter nào liên lạc được, leader epoch và high watermark; sau đó làm theo quy trình phục hồi phù hợp phiên bản và topology.

## 9. Ví dụ tính quorum và tình huống lỗi

Giả sử cluster có năm controller voter: C1, C2, C3, C4, C5.

Majority cần:

\[
Q = \left\lfloor \frac{5}{2} \right\rfloor + 1 = 3
\]

Cluster có thể mất tối đa hai voter mà vẫn còn quorum.

| Tình huống | Voter còn liên lạc | Có quorum? | Kết quả |
|---|---:|---|---|
| Bình thường | 5/5 | Có | Leader commit metadata bình thường |
| C5 dừng | 4/5 | Có | Quorum vẫn hoạt động |
| C4 và C5 dừng | 3/5 | Có | Vẫn đạt majority; ít dư địa cho lỗi tiếp theo |
| C3, C4 và C5 dừng | 2/5 | Không | Không thể bầu leader hoặc commit metadata mới |
| Mạng chia 3 node và 2 node | Nhóm 3/5 | Nhóm 3 có quorum | Nhóm 2 không thể commit metadata |

Nếu leader hiện tại ở nhóm hai node, nhóm ba node có thể bầu leader mới sau timeout. Nếu nhóm ba node bị cô lập và leader cũ nằm trong đó, nhóm có majority vẫn có thể tiếp tục khi thỏa điều kiện bầu chọn và log freshness.

## 10. Checklist vận hành controller quorum

Trước khi triển khai hoặc thay đổi KRaft quorum, hãy kiểm tra:

- Số voter được chọn theo số controller failure cần chịu.
- Các voter được phân tán trên failure domain độc lập.
- Mỗi node có `node.id` duy nhất và đúng `process.roles`.
- Controller listener phân giải DNS và kết nối được giữa các voter.
- Cấu hình static/dynamic quorum nhất quán với phiên bản Kafka.
- Metadata log storage bền vững và có dung lượng phù hợp.
- Không nâng cấp hoặc bảo trì quá số voter có thể mất mà vẫn giữ majority.
- Có dashboard/alert cho leader epoch, high watermark, replication lag và election.
- Có quy trình phục hồi khi mất majority; không tự ý format lại metadata storage.
- Phân biệt cảnh báo controller quorum với ISR/under-replicated partition.

## 11. Câu hỏi tự kiểm tra

1. KRaft dùng Raft để thống nhất loại dữ liệu nào trong Kafka cluster?
2. Sự khác nhau giữa follower, candidate và leader trong Raft là gì?
3. Term có vai trò gì khi leader cũ quay lại sau một network partition?
4. Vì sao một entry mới chỉ được append trên leader chưa chắc đã committed?
5. Công thức tính majority quorum với `N` voter là gì?
6. Ba controller voter có thể chịu được bao nhiêu controller lỗi? Vì sao hai controller không thể chịu được một lỗi?
7. Vì sao bốn voter không tăng khả năng chịu lỗi so với ba voter?
8. Điều kiện bầu active controller của KRaft khác gì điều kiện bầu partition leader?
9. `min.insync.replicas` và controller quorum majority có cùng ý nghĩa không?
10. Khi mất controller quorum, vì sao một số luồng dữ liệu hiện hữu có thể vẫn hoạt động trong khi thay đổi metadata bị gián đoạn?

## Kết luận

Raft giúp KRaft duy trì một metadata log có thứ tự bằng cách bầu một leader và chỉ commit thay đổi khi đạt majority voter. Với `N` voter, quorum cần `floor(N/2)+1`; vì vậy ba voter chịu được một lỗi và năm voter chịu được hai lỗi nếu các node còn lại liên lạc được. Controller quorum quản lý metadata cluster, còn leader/ISR của partition quản lý bản sao record dữ liệu. Phân biệt hai cơ chế này là nền tảng để thiết kế topology controller, đọc cảnh báo và phục hồi Kafka cluster an toàn.
