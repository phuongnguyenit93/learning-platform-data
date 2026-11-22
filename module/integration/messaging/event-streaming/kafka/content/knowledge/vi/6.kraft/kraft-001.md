# Vì sao Kafka cần cơ chế đồng thuận cho metadata

Một cụm Kafka có thể chứa hàng nghìn topic, partition, broker và replica. Để producer gửi record đúng nơi, consumer tìm đúng leader và broker phối hợp sao chép dữ liệu, mọi node phải có cùng một bức tranh về cấu trúc cụm. Bức tranh đó là **metadata**.

Metadata thay đổi liên tục: broker gia nhập hoặc rời cụm, topic được tạo hay xóa, partition được phân công lại, leader thay đổi, replica vào hoặc ra khỏi ISR, cấu hình topic được cập nhật. Nếu các broker nhìn thấy những phiên bản metadata khác nhau, chúng có thể định tuyến request sai hoặc thực hiện các quyết định mâu thuẫn. Kafka cần một cơ chế đồng thuận để xác định một thứ tự thay đổi metadata duy nhất và bảo đảm thay đổi quan trọng chỉ được công nhận khi đã được một nhóm controller đủ lớn chấp nhận.

Trong kiến trúc KRaft, Kafka dùng **Raft consensus** cho metadata quorum. Bài học này giải thích vấn đề mà đồng thuận giải quyết, cách metadata log được commit, điều gì xảy ra khi controller lỗi và vì sao cơ chế này khác với replication của dữ liệu event.

## 1. Metadata là bản đồ điều khiển của cụm Kafka

Metadata mô tả cách cụm Kafka được tổ chức và cách các broker phối hợp. Nó không phải nội dung event do producer gửi vào topic.

Một số thông tin quan trọng trong metadata:

| Nhóm metadata | Ví dụ | Thành phần sử dụng |
|---|---|---|
| Broker và controller | Broker ID, trạng thái đăng ký, thông tin node và controller | Các broker và controller |
| Topic và partition | Tên topic, ID topic, số partition, cấu hình topic | Admin client, broker, producer và consumer |
| Phân công replica | Broker nào giữ replica của partition nào | Controller và broker |
| Leader và ISR | Replica nào là leader, replica nào đang đồng bộ | Producer, consumer, broker và controller |
| Cấu hình và tính năng | Retention, giới hạn record, feature level, ACL và các cấu hình cluster | Broker, client và controller |

Ví dụ, khi producer muốn ghi vào `orders-3`, nó cần biết broker nào đang là leader của partition 3 thuộc topic `orders`. Consumer cũng cần metadata để gửi fetch request đến đúng leader. Nếu một broker vừa bị thay thế nhưng các node khác chưa thống nhất metadata mới, producer có thể tiếp tục gửi đến broker cũ hoặc broker không còn là leader.

Có thể nhìn Kafka thành hai mặt phối hợp với nhau:

- **Data plane:** nhận, ghi, lưu trữ, sao chép và đọc các record trong partition.
- **Control plane:** quản lý cấu trúc cụm, phân công replica, bầu controller và cập nhật metadata.

Metadata là trạng thái dùng chung của control plane. Các broker có thể cập nhật cache metadata ở những thời điểm hơi khác nhau, nhưng chúng phải dựa trên cùng một lịch sử thay đổi đã commit. Nếu không có cơ chế đồng thuận, nhiều node có thể cùng đưa ra quyết định mà không có một thứ tự thống nhất.

## 2. Điều gì có thể xảy ra nếu metadata không được đồng thuận?

Giả sử cụm có ba broker A, B và C. Partition `payments-0` đang có leader là A, replica trên B và C. Sau một sự cố mạng, một số node không nhận được thông tin mới nhất.

Nếu hai controller độc lập cùng có quyền quyết định, một controller có thể cho rằng A vẫn là leader trong khi controller khác lại chỉ định B làm leader. Khi đó:

- Producer kết nối đến A có thể ghi theo trạng thái cũ.
- Producer kết nối đến B có thể ghi theo trạng thái mới.
- Consumer ở các broker khác nhau có thể nhận metadata không đồng nhất.
- Broker có thể quảng bá leader hoặc replica assignment khác nhau.
- Việc tạo topic, xóa topic hoặc thay đổi cấu hình có thể được áp dụng theo những thứ tự khác nhau.

Hệ thống sẽ khó xác định quyết định nào là hợp lệ. Nếu hai controller cùng hoạt động như leader, nguy cơ split brain xuất hiện: mỗi bên tin rằng mình có quyền điều khiển cụm.

Đồng thuận giải quyết vấn đề bằng cách thiết lập một nguồn quyết định có thứ tự. Tại một thời điểm, metadata quorum có một leader được bầu hợp lệ; các thay đổi được ghi vào metadata log và chỉ được xem là đã commit khi đạt điều kiện đa số của quorum.

Điều đó tạo ra hai thuộc tính quan trọng:

- **Safety:** không có hai lịch sử metadata đã commit mâu thuẫn nhau. Các node không thể tự ý công nhận hai thứ tự thay đổi khác nhau.
- **Liveness:** khi quorum vẫn có đa số thành viên hoạt động và mạng đủ ổn định, hệ thống có thể bầu leader và tiếp tục commit thay đổi.

Safety ưu tiên tránh trạng thái sai. Khi mất đa số, Kafka có thể phải tạm dừng các thay đổi metadata thay vì để một nhóm thiểu số tự đưa ra quyết định xung đột.

## 3. Từ ZooKeeper đến KRaft: đưa đồng thuận metadata vào Kafka

### 3.1. Mô hình trước KRaft

Trong kiến trúc Kafka dùng ZooKeeper, Kafka dựa vào một hệ thống bên ngoài để lưu trữ và phối hợp metadata. ZooKeeper tự duy trì quorum và cung cấp cơ chế nhất quán cho dữ liệu điều phối.

Kafka có controller broker được bầu để quản lý nhiều hoạt động của cụm. Controller theo dõi trạng thái cluster, cập nhật thông tin trong ZooKeeper và truyền các thay đổi cần thiết đến broker. Broker cũng theo dõi thay đổi metadata từ hệ thống điều phối này.

Mô hình đó hoạt động, nhưng vận hành cần quản lý hai hệ thống có vai trò liên quan:

- Kafka lưu và sao chép event data.
- ZooKeeper lưu và đồng bộ trạng thái điều khiển của Kafka.

Việc triển khai, giám sát, nâng cấp và khôi phục cần hiểu cả vòng đời của Kafka lẫn ZooKeeper. Khi metadata thay đổi, Kafka còn phải phối hợp giữa trạng thái trong ZooKeeper và trạng thái mà broker đang giữ.

### 3.2. KRaft hợp nhất cơ chế đồng thuận metadata vào Kafka

KRaft là viết tắt của Kafka Raft. Thay vì phụ thuộc ZooKeeper, Kafka duy trì metadata trong một log được sao chép giữa các controller thuộc metadata quorum. Raft quyết định ai là leader, thứ tự record metadata và thời điểm các thay đổi được commit.

Kafka 4.x chỉ hỗ trợ KRaft; ZooKeeper mode đã bị loại bỏ. Vì vậy, KRaft là kiến trúc bắt buộc cho các triển khai Kafka 4.x.

Trong KRaft:

- Các node có vai trò controller tham gia metadata quorum.
- Một controller giữ vai trò leader của quorum tại một thời điểm.
- Các controller còn lại là follower hoặc voter chưa giữ vai trò leader.
- Leader nhận và sắp xếp các thay đổi metadata thành record trong metadata log.
- Các voter sao chép log và xác nhận các record.
- Metadata chỉ được áp dụng như trạng thái đã commit sau khi quorum xác nhận đủ đa số.

KRaft không có nghĩa mọi record nghiệp vụ trong các topic đều được ghi bằng Raft. Raft được dùng để đồng thuận metadata của cluster. Dữ liệu event của từng partition vẫn dùng cơ chế leader/follower replication của Kafka.

## 4. Raft quorum hoạt động như thế nào?

### 4.1. Quorum là nhóm thành viên cần đạt đa số

Một quorum là số thành viên tối thiểu cần xác nhận để một thay đổi được commit. Với N voter, đa số là:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Raft thường được triển khai với số voter lẻ để đạt khả năng chịu lỗi tốt với chi phí node hợp lý.

| Số controller voter | Số phiếu cần để có đa số | Số voter có thể lỗi mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Ví dụ:

- Với 3 voter, chỉ cần 2 voter xác nhận. Nếu 1 controller hỏng, 2 node còn lại vẫn có thể duy trì quorum.
- Nếu 2 trong 3 voter cùng hỏng hoặc không liên lạc được, quorum không còn đa số. Không thể commit metadata mới.
- Với 5 voter, hệ thống có thể chịu lỗi tối đa 2 voter mà vẫn có 3 phiếu.

Hai voter không phải lựa chọn HA tốt: cần cả hai cùng hoạt động mới có đa số, nên mất một node là mất quorum. Thêm nhiều voter cũng không miễn phí; quorum càng lớn càng có nhiều thành viên cần liên lạc và đồng bộ. Với phần lớn cụm production, 3 hoặc 5 controller voter thường là lựa chọn dễ vận hành.

### 4.2. Quy trình bầu leader

Raft dùng term và vote để xác định leader hợp lệ. Khi follower không nhận được heartbeat của leader trong khoảng thời gian bầu cử, nó có thể chuyển sang candidate và yêu cầu các voter bỏ phiếu.

Một node chỉ trở thành leader khi nhận đủ phiếu đa số. Các voter không thể cùng cấp quyền leader cho hai candidate trong cùng một term. Term tăng qua các lần bầu cử, giúp node nhận biết thông tin từ một leader cũ.

Các điểm chính:

1. Follower theo dõi heartbeat từ leader hiện tại.
2. Nếu heartbeat vắng mặt đủ lâu, follower bắt đầu election và tăng term.
3. Candidate gửi yêu cầu vote đến các voter.
4. Voter kiểm tra term và độ mới của log trước khi bỏ phiếu.
5. Candidate nhận đa số phiếu trở thành leader.
6. Leader mới tiếp tục đồng bộ metadata log với các follower.

Nếu hai candidate cùng tranh cử, có thể không ai nhận được đa số ở vòng đầu. Một election mới sẽ diễn ra sau đó. Hệ thống ưu tiên chỉ công nhận một leader có đủ phiếu, thay vì cho phép nhiều candidate cùng quyết định metadata.

### 4.3. Commit metadata record

Sau khi trở thành leader, controller nhận thay đổi metadata và append record vào metadata log. Leader gửi record đến follower. Khi đủ đa số voter xác nhận record theo quy tắc Raft, record đạt trạng thái committed và có thể được áp dụng vào metadata state.

~~~mermaid
sequenceDiagram
    participant A as Admin Client
    participant L as Controller Leader
    participant F1 as Controller Follower 1
    participant F2 as Controller Follower 2
    A->>L: Yêu cầu tạo topic
    L->>L: Append metadata record
    par Sao chép log
        L->>F1: Replicate record
        F1-->>L: Acknowledge
    and
        L->>F2: Replicate record
        F2-->>L: Acknowledge
    end
    Note over L,F2: Đủ đa số voter xác nhận
    L->>L: Đánh dấu record committed
    L-->>A: Trả kết quả
~~~

Với quorum 3 voter, leader cộng với ít nhất một follower tạo thành đa số. Nếu follower còn lại tạm thời không liên lạc được, thay đổi vẫn có thể commit. Khi follower quay lại, nó đồng bộ phần log còn thiếu.

Nếu leader chỉ ghi record vào đĩa của mình mà chưa có đa số xác nhận, record đó chưa được xem là đã commit. Một leader khác được bầu sau đó có thể tiếp tục từ lịch sử đã commit mà không làm mất tính nhất quán của metadata.

## 5. Metadata log lưu những gì?

Metadata log là lịch sử tuần tự các thay đổi của cluster. Mỗi record biểu diễn một thay đổi hoặc một phần trạng thái metadata, ví dụ:

- Tạo hoặc xóa topic.
- Tạo partition và cập nhật replica assignment.
- Thay đổi leader hoặc trạng thái replica.
- Đăng ký broker mới hoặc cập nhật trạng thái đăng ký.
- Thay đổi cấu hình topic hoặc cấu hình cluster.
- Thay đổi feature level, ACL và các metadata bảo mật liên quan.

Metadata log không phải topic nghiệp vụ mà ứng dụng tạo để lưu đơn hàng hay thanh toán. Nó là log nội bộ dành cho trạng thái điều khiển của cluster, được lưu trong metadata directory và sao chép giữa các controller voter.

### 5.1. Tại sao cần log có thứ tự?

Giả sử quản trị viên thực hiện ba thao tác:

1. Tạo topic `orders`.
2. Tăng số partition của topic.
3. Thay đổi replica assignment.

Nếu các broker áp dụng các thao tác theo thứ tự khác nhau, chúng có thể có những nhận định không tương thích về trạng thái topic. Metadata log cung cấp thứ tự duy nhất cho các thay đổi đã commit. Các node có thể phát lại log theo thứ tự đó để xây dựng lại cùng một metadata state.

Log cũng giúp node mới hoặc node vừa khôi phục bắt kịp trạng thái của cluster. Thay vì phải đoán trạng thái từ các thông tin rời rạc, node có thể tải snapshot và tiếp tục đọc các record mới hơn.

Đồng thuận không có nghĩa mọi broker nhận metadata cùng một mili giây. Controller quorum thống nhất thứ tự và trạng thái đã commit; sau đó metadata được truyền đến broker để cập nhật cache. Trong khoảng thời gian lan truyền, một broker có thể tạm giữ metadata cũ. Broker và client cần xử lý các phản hồi như leader đã thay đổi, rồi làm mới metadata để tiếp tục gửi request đến đúng node.

### 5.2. Snapshot giúp phục hồi nhanh hơn

Nếu phải phát lại toàn bộ lịch sử metadata từ lúc cluster được tạo, thời gian khôi phục có thể tăng khi log dài. KRaft tạo snapshot của metadata state tại một offset nhất định. Khi khởi động hoặc cần khôi phục, controller có thể nạp snapshot rồi phát lại phần log mới hơn snapshot.

Snapshot là điểm khởi đầu để tái dựng trạng thái; metadata log tiếp tục là lịch sử các thay đổi. Việc tạo snapshot không thay thế quorum và cũng không có nghĩa có thể tự ý chép một snapshot cũ lên controller đang chạy.

## 6. Điều gì xảy ra khi controller hoặc mạng gặp sự cố?

### 6.1. Một follower bị lỗi

Giả sử quorum có ba voter: C1, C2 và C3. C1 là leader, C2 và C3 là follower. C3 bị tắt đột ngột.

C1 và C2 vẫn còn đa số 2/3 nên có thể tiếp tục commit metadata. Khi C3 quay lại, nó đọc trạng thái log và snapshot hiện có, sau đó đồng bộ phần còn thiếu.

### 6.2. Leader bị lỗi

Nếu C1 là leader và bị dừng, C2 và C3 có thể bầu leader mới. Candidate nhận đa số phiếu sẽ tiếp quản. Sau election, controller mới tiếp tục xử lý metadata thay đổi.

Trong khoảng thời gian phát hiện lỗi và bầu leader, các thao tác quản trị cần thay đổi metadata có thể tạm thời thất bại hoặc phải retry. Ứng dụng quản trị nên xử lý lỗi tạm thời thay vì giả định mọi request luôn thành công ngay.

### 6.3. Mất đa số quorum

Nếu C1 và C2 cùng lỗi trong quorum 3 voter, chỉ C3 còn hoạt động. C3 không thể tự quyết định metadata mới vì không có đa số.

Điều này có nghĩa:

- Không thể bầu một leader mới nếu không có đa số phiếu.
- Không thể commit thay đổi metadata mới.
- Các thao tác quản trị như tạo topic hoặc thay đổi assignment có thể bị gián đoạn.
- Broker có thể tiếp tục một số hoạt động data plane dựa trên metadata đã commit và cache hiện có, nhưng các thay đổi cần controller hoặc việc xử lý failover có thể bị ảnh hưởng.

Khi C1 hoặc C2 khôi phục và quorum có lại đa số, quá trình election và đồng bộ có thể tiếp tục. Không nên cố khởi tạo một quorum mới chỉ từ node thiểu số khi các node cũ vẫn có thể quay lại, vì thao tác sai có thể tạo ra một lịch sử metadata khác.

### 6.4. Network partition và split brain

Giả sử mạng chia cụm controller 3 voter thành hai nhóm: nhóm A có 2 voter, nhóm B có 1 voter. Nhóm A vẫn có đa số nên có thể duy trì leader và commit metadata. Nhóm B không thể tự commit metadata.

Nếu mạng phục hồi, node ở nhóm thiểu số phải đồng bộ với lịch sử đã được quorum commit. Cơ chế term, vote và quy tắc log của Raft giúp ngăn nhóm thiểu số tự công nhận một lịch sử metadata xung đột.

~~~mermaid
flowchart TD
    A["Quorum có 3 voter"] --> B{"Phân vùng mạng"}
    B --> C["Nhóm A: 2 voter"]
    B --> D["Nhóm B: 1 voter"]
    C --> E["Có đa số: tiếp tục commit metadata"]
    D --> F["Thiểu số: không thể commit"]
    E --> G["Mạng phục hồi"]
    F --> G
    G --> H["Node bị tụt đồng bộ theo log đã commit"]
~~~

## 7. Đồng thuận metadata khác với replication của dữ liệu event

Đây là điểm rất dễ nhầm khi học KRaft.

| Đặc điểm | Metadata quorum (Raft) | Partition replication |
|---|---|---|
| Mục đích | Đồng thuận trạng thái điều khiển của cluster | Sao chép record event của topic |
| Thành viên | Controller voter | Broker giữ replica của partition |
| Dữ liệu | Topic, partition assignment, broker registration, cấu hình và metadata khác | Record key/value, timestamp, headers và record batch |
| Leader | Controller leader của metadata quorum | Leader riêng của từng partition |
| Cơ chế | Raft election, log replication và majority commit | Kafka leader/follower replication, ISR và replica fetch |
| Điều kiện ghi | Metadata record được commit theo quorum | Producer acknowledgment theo `acks`, ISR và cấu hình liên quan |
| Khi mất đa số | Không thể commit metadata mới | Khả năng ghi partition phụ thuộc leader, ISR, `acks` và `min.insync.replicas` |

Ví dụ, topic `orders` có partition 0 với leader là broker B1 và follower là B2, B3. Dữ liệu event được B1 ghi và sao chép sang follower theo cơ chế replication của partition. Trong khi đó, controller quorum dùng Raft để thống nhất metadata rằng partition 0 có replica trên B1, B2, B3 và B1 hiện là leader.

Raft không yêu cầu mỗi event của `orders-0` phải được controller quorum bỏ phiếu. Ngược lại, ISR replication cũng không thay thế được đồng thuận metadata: cluster vẫn cần controller thống nhất broker nào là leader, replica nào được phân công và cấu trúc topic ra sao.

Metadata quorum khỏe mạnh không tự bảo đảm mọi record đã được replicate an toàn. Muốn bảo đảm dữ liệu event, producer và topic vẫn cần cấu hình `acks`, `min.insync.replicas`, replication factor và chính sách xử lý lỗi phù hợp.

## 8. Thiết kế controller quorum khi triển khai

### 8.1. Chọn số voter và failure domain

Với cụm production, thường bắt đầu bằng 3 hoặc 5 controller voter:

- Đặt controller ở các máy hoặc failure domain độc lập để một sự cố máy, rack hoặc vùng không làm mất đa số.
- Tránh đặt tất cả voter trong cùng một máy vật lý hoặc cùng một failure domain.
- Chọn số lượng dựa trên khả năng chịu lỗi, độ trễ mạng và chi phí vận hành.
- Không thêm voter chỉ để tăng số node; mỗi voter phải được triển khai, giám sát và nâng cấp đúng quy trình.

Nếu dùng ba voter, hãy bố trí sao cho một lỗi đơn lẻ không làm mất hai voter cùng lúc. Nếu dùng năm voter, cần tính đến cách phân bố giữa các rack hoặc zone và latency liên vùng.

### 8.2. Dedicated controller và combined mode

KRaft cho phép tách vai trò controller và broker hoặc kết hợp chúng trong cùng một tiến trình.

- **Dedicated controller:** node chỉ đảm nhiệm controller role. Cách này giúp tách tải control plane khỏi tải produce/consume và thường phù hợp với cụm production lớn.
- **Combined broker/controller:** cùng một node vừa làm broker vừa tham gia quorum. Cách này đơn giản cho lab, môi trường nhỏ hoặc triển khai cần ít máy hơn, nhưng tài nguyên broker có thể ảnh hưởng đến khả năng phản hồi của controller.

Khi chọn mô hình, hãy cân nhắc kích thước cluster, số lượng metadata thay đổi, tải event, khả năng cách ly tài nguyên và cách tổ chức failure domain. Không nên coi combined mode là mặc định cho mọi cluster lớn.

### 8.3. Mạng và lưu trữ của controller

Controller cần trao đổi heartbeat, vote và metadata log với nhau. Vì vậy:

- Mạng giữa controller phải ổn định, latency thấp và không bị chặn bởi firewall hoặc DNS sai.
- Metadata directory cần dung lượng, độ bền và hiệu năng ghi phù hợp.
- Tránh để CPU, disk I/O hoặc GC của broker làm controller không kịp heartbeat.
- Đồng bộ thời gian hệ thống để log và chẩn đoán sự cố dễ hơn; Raft không dùng đồng hồ hệ thống để quyết định thứ tự commit, nhưng timestamp và log vận hành vẫn cần đáng tin cậy.

### 8.4. Giám sát quorum

Các dấu hiệu cần theo dõi:

- Controller leader hiện tại và trạng thái election.
- Số voter đang hoạt động, số voter mất kết nối và khả năng đạt đa số.
- Metadata log lag giữa leader và follower.
- Thời gian commit metadata và số lần election bất thường.
- Disk capacity, disk latency, CPU, network và lỗi ghi metadata log.
- Broker đăng ký hoặc rời cụm bất thường, partition offline và leader thay đổi liên tục.

Nếu controller election xảy ra liên tục, hãy kiểm tra network latency, packet loss, CPU starvation, disk I/O và thời gian pause của JVM. Tăng timeout một cách tùy tiện có thể làm lỗi được phát hiện chậm hơn mà không giải quyết nguyên nhân gốc.

## 9. Ví dụ: tạo topic và metadata được đồng thuận

Giả sử AdminClient yêu cầu tạo topic `orders` với 6 partition và replication factor 3.

Luồng khái quát:

1. AdminClient gửi yêu cầu đến một broker trong cluster.
2. Broker chuyển yêu cầu đến controller đang giữ vai trò leader.
3. Controller kiểm tra yêu cầu, tạo các metadata record mô tả topic, partition và replica assignment.
4. Controller leader append record vào metadata log.
5. Các controller follower nhận record và phản hồi xác nhận.
6. Khi metadata record đạt điều kiện commit của quorum, controller áp dụng thay đổi.
7. Broker nhận metadata đã commit và tạo các partition replica được phân công.
8. AdminClient nhận kết quả tạo topic; producer và consumer có thể lấy metadata mới để làm việc.

Nếu controller leader lỗi ở bước trước khi metadata commit, request có thể cần được gửi lại hoặc trả lỗi tạm thời. Nếu lỗi xảy ra sau khi commit nhưng trước khi client nhận response, client có thể không biết chắc thao tác đã hoàn thành. Với các thao tác quản trị, nên kiểm tra trạng thái topic trước khi retry một cách mù quáng.

Đồng thuận metadata bảo đảm các controller không cùng commit hai cấu trúc topic khác nhau. Nó không thay thế kiểm tra kết quả ở phía client khi timeout.

## 10. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| KRaft dùng Raft để ghi mọi event | Raft dùng cho metadata quorum; event data vẫn được sao chép theo cơ chế partition replication |
| Chỉ cần một controller là đủ cho production | Một voter không chịu được lỗi node; cần quorum có đa số để duy trì HA |
| Có ba controller thì mất hai node vẫn hoạt động | Với 3 voter, cần 2 phiếu; mất 2 voter là mất quorum |
| Controller leader là leader của mọi partition | Controller leader điều khiển metadata; mỗi partition có leader riêng |
| Mất quorum nghĩa mọi producer và consumer dừng ngay | Các hoạt động dựa trên metadata đã commit có thể còn tiếp tục; thay đổi metadata và một số failover bị ảnh hưởng |
| Metadata log là topic nghiệp vụ | Metadata log là log nội bộ của KRaft, không dùng để lưu event của ứng dụng |
| Raft thay thế `acks=all` và ISR | Raft bảo vệ metadata; `acks`, ISR và `min.insync.replicas` liên quan đến độ bền của record data |
| Thêm càng nhiều controller càng tốt | Cần cân bằng khả năng chịu lỗi, latency, số kết nối và chi phí vận hành |

## 11. Checklist kiểm tra hiểu biết và vận hành

- [ ] Phân biệt được metadata và event data.
- [ ] Giải thích được vì sao nhiều controller cần thống nhất một thứ tự thay đổi metadata.
- [ ] Hiểu vai trò controller leader, follower và voter.
- [ ] Tính được số phiếu đa số và số node có thể lỗi.
- [ ] Mô tả được election, metadata log replication và commit.
- [ ] Phân biệt được Raft metadata quorum với partition leader/follower replication.
- [ ] Hiểu điều gì xảy ra khi mất leader, mất follower hoặc mất đa số quorum.
- [ ] Biết vì sao node thiểu số không được tự commit metadata.
- [ ] Chọn được mô hình dedicated controller hoặc combined mode theo quy mô.
- [ ] Có kế hoạch phân bố voter theo failure domain và giám sát quorum.

## 12. Tài liệu tham khảo

- [Apache Kafka 4.4 – KRaft](https://kafka.apache.org/44/operations/kraft/)
- [Apache Kafka 4.4 – Design](https://kafka.apache.org/44/design/design/)
- [Apache Kafka 4.4 – Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka – KIP-500: Replace ZooKeeper with a Self-Managed Metadata Quorum](https://cwiki.apache.org/confluence/display/KAFKA/KIP-500%3A+Replace+ZooKeeper+with+a+Self-Managed+Metadata+Quorum)

Đồng thuận metadata giúp các broker cùng tuân theo một lịch sử điều khiển của cluster. KRaft dùng Raft quorum để bầu controller leader và commit metadata log; còn replication của từng partition tiếp tục bảo vệ các record event. Hiểu rõ hai cơ chế này giúp thiết kế cluster chịu lỗi đúng cách và chẩn đoán sự cố control plane mà không nhầm với lỗi data plane.
