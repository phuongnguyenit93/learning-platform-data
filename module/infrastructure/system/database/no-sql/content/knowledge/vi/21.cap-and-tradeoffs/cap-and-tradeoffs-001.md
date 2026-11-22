# Đặt bài toán CAP trong hệ phân tán có khả năng mất liên lạc

Khi học NoSQL, ta thường nghe: **“Hệ phân tán chỉ chọn được hai trong ba: Consistency, Availability và Partition tolerance.”** Câu này dễ nhớ nhưng không đủ chính xác để thiết kế một hệ thống thực tế. Nó có thể khiến người học tưởng rằng “P” là một tính năng bật/tắt được, hoặc một database luôn mang một nhãn cố định **CA/CP/AP** bất kể cấu hình và loại truy vấn.

Vấn đề thật sự là: **khi các bản sao dữ liệu không thể trao đổi thông tin nhưng vẫn nhận yêu cầu từ người dùng, chúng sẽ trả lời thế nào?** Nếu một phía đã xác nhận ghi thành công, phía khác chưa biết đến thay đổi ấy có được trả dữ liệu cũ không? Nếu không thể chắc chắn dữ liệu mới nhất là gì, phía cô lập phải chờ hay được phép tiếp tục xử lý cục bộ?

Đây là cách **đặt bài toán CAP** đúng: xác định đối tượng dữ liệu, hợp đồng của operation, những node còn sống, liên kết mạng bị hỏng và lịch đọc/ghi cụ thể; sau đó giải thích đánh đổi xảy ra **ở đâu và với ai**.

Bài học minh họa CAP qua hệ thống đặt chỗ và các timeline có giá trị đọc/ghi, rồi mở rộng sang **quorum, leader, read replica, NoSQL, timeout, hội tụ dữ liệu, lựa chọn nghiệp vụ và kiểm thử mất liên lạc**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô hình hóa một cluster có replication và network partition.
2. Định nghĩa đúng **C, A, P** theo CAP; phân biệt chữ C trong CAP với ACID và chữ A với uptime SLA.
3. Dựng lịch gồm một write đã được xác nhận và một read bắt đầu sau đó để kiểm tra tính tuyến tính.
4. Giải thích vì sao khi partition xảy ra, không thể luôn bảo đảm cả linearizability và availability mạnh cho mọi request liên quan.
5. Hiểu cách leader/quorum ảnh hưởng sự khác biệt giữa phía đa số và phía thiểu số.
6. Biết giới hạn của công thức `R + W > N`, của LWW và của CRDT khi cần bảo vệ bất biến nghiệp vụ.
7. Phân tích các operation như giữ ghế, tồn kho, thanh toán, giỏ hàng và báo cáo theo mức nhất quán thích hợp.
8. Tránh phân loại toàn bộ MongoDB, Cassandra, DynamoDB hay Redis bằng một nhãn CAP duy nhất.
9. Thiết kế fault-injection lab, thu dữ liệu thời điểm, version, request ID và kiểm tra kết quả sau khi mạng hồi phục.

## 2. Bài toán xuyên suốt: hai region, một ghế cuối cùng

Giả sử nền tảng bán vé lưu:

~~~json
{
  "eventId": "concert-42",
  "seatId": "seat-007",
  "status": "FREE",
  "reservationId": null,
  "version": 10
}
~~~

Dữ liệu được nhân bản tại hai khu vực:

~~~text
         Region A                            Region B
    +----------------+                 +----------------+
    | Replica A      |                 | Replica B      |
    | seat-007: FREE | <-------------> | seat-007: FREE |
    | version: 10    |   Replication   | version: 10    |
    +----------------+                 +----------------+
            ^                                  ^
            |                                  |
        Client An                          Client Bình
~~~

Bất biến nghiệp vụ:

> Một ghế không được có hai reservation đã được **xác nhận thành công** cho hai request độc lập.

Lúc 10:00, liên kết mạng giữa A và B bị hỏng. A và B vẫn chạy bình thường, vẫn nhận request từ client ở vùng tương ứng:

~~~text
        Region A                            Region B
    +----------------+                  +----------------+
    | A vẫn sống     |      X X X       | B vẫn sống     |
    | seat = FREE    |  Mất liên lạc    | seat = FREE    |
    +----------------+                  +----------------+
            ^                                   ^
            |                                   |
      reserve(A-101)                       reserve(B-202)
~~~

Trong khoảng mạng đứt, hai khách cùng yêu cầu giữ `seat-007`. Mỗi replica chỉ biết bản ghi cục bộ trước partition là `FREE`, không nhận được cập nhật của phía kia.

Nếu **cả A và B cùng báo `RESERVED`**, hai khách đã được hứa cùng một ghế. Nếu một bên phải chờ đủ thông tin trước khi xác nhận, bên đó có thể không thể hoàn tất request trong lúc mạng bị chia cắt.

Đây là xung đột cốt lõi. Để lập luận chặt chẽ, cần định nghĩa từng chữ của CAP.

## 3. C — Consistency trong định lý CAP

Trong mô hình CAP, **Consistency** thường được diễn đạt là **atomic consistency / linearizability** của thao tác trên một đối tượng dữ liệu.

Trực giác:

- Một operation hoàn tất có thể hình dung như có hiệu lực tại **một điểm logic** nằm giữa lúc gọi và lúc nhận response.
- Nếu operation A đã hoàn tất **trước** khi operation B bắt đầu, thứ tự tuyến tính phải đặt A trước B.
- Với những operation **chồng lấn**, có thể có nhiều thứ tự hợp lệ; phải tìm một thứ tự thỏa đặc tả tuần tự và các ràng buộc thời gian thực.

### 3.1. Ví dụ register

Ban đầu một register có `x = 0`:

~~~text
10:00:00.010  Client A gọi write(1)
10:00:00.020  write(1) trả SUCCESS
10:00:00.030  Client B gọi read()
10:00:00.040  read() trả kết quả
~~~

Nếu không có writer khác, một **read linearizable** bắt đầu sau write đã xác nhận phải trả **1**. Trả 0 không phù hợp với đặc tả của register tuyến tính.

Điều này **không có nghĩa** mọi replica phải có byte giống nhau trong từng mili giây. Replica phụ có thể chưa nhận thay đổi, nhưng hệ thống cam kết read tuyến tính thì phải **điều hướng/đợi/xác minh** để không công bố giá trị cũ trái hợp đồng.

### 3.2. Đừng nhầm với chữ C trong ACID

| Khái niệm | Câu hỏi chính |
| --- | --- |
| **CAP Consistency** | Các operation có thể được giải thích theo một thứ tự tuyến tính tôn trọng thời gian thực không? |
| **ACID Consistency** | Transaction có giữ các ràng buộc toàn vẹn và bất biến dữ liệu không? |
| **Serializability** | Các transaction có tương đương một lịch tuần tự nào đó không? |
| **Strict serializability** | Transaction vừa serializable vừa tôn trọng thứ tự thời gian thực? |
| **Eventual consistency** | Các replica có thể tạm khác nhau và hội tụ khi không còn thay đổi mới, theo giả định của hệ? |

Không dùng “schema hợp lệ” để suy CAP consistency. Cũng không suy “một document được update nguyên tử” thành “toàn workflow nhiều document có strict serializability”.

## 4. A — Availability trong định lý CAP

Trong mô hình CAP, **Availability** được hiểu mạnh: **mọi request được gửi tới một node không hỏng cuối cùng nhận được một phản hồi hợp lệ theo đặc tả**.

Có ba lưu ý:

1. **Node bị cô lập nhưng vẫn sống** vẫn là node không hỏng. Nếu nó nhận request mà phải chờ vô thời hạn vì không liên lạc được với node khác, không giữ được availability mạnh cho request đó.
2. “Cuối cùng” là điều kiện **liveness**. Nó không tự đặt p95 dưới 150 ms hay timeout dưới một giây.
3. Một response như `HTTP 503` hoặc `UNAVAILABLE` **không tự biến một operation bị từ chối thành operation được phục vụ thành công**.

### 4.1. Availability CAP không phải uptime SLA

Một hệ có thể đạt 99,95% uptime cả tháng nhưng từ chối write tại region bị cô lập. Nó vẫn vi phạm bảo đảm availability CAP **trong tình huống lỗi và loại operation đang xét**, nếu áp yêu cầu availability mạnh tới node còn sống đó.

Ngược lại, một hệ cuối cùng trả kết quả sau 30 giây có thể thỏa điều kiện liveness lý thuyết, nhưng đã vi phạm SLO latency 150 ms.

Nên tách:

~~~yaml
formalModel:
  availability: "eventual valid response at non-failing nodes"
operationalSLO:
  p95LatencyMs: 150
  requestTimeoutMs: 800
  monthlySuccessRate: "99.95%"
  maximumStalenessSeconds: 3
~~~

Các con số là **ví dụ**, không phải một phần của định lý.

### 4.2. Phản hồi nghiệp vụ hợp lệ khác từ chối do partition

Nếu ghế thật sự đã bị giữ, phản hồi `ALREADY_RESERVED` có thể hoàn toàn hợp lệ.

Nhưng nếu replica không biết ghế có bị giữ ở vùng khác hay chưa, nó không thể tùy tiện trả “hết ghế” cho mọi request rồi tuyên bố vẫn available. **Phản hồi phải phù hợp với đặc tả operation**, không chỉ là một HTTP response bất kỳ.

## 5. P — Partition tolerance

**Network partition** là tình huống một số tập node không thể trao đổi message cần thiết trong một khoảng thời gian. Các node ở mỗi nhóm vẫn có thể chạy và phục vụ client gần chúng.

Các dạng thực tế:

- Mất cả hai chiều liên lạc giữa hai region.
- Mất một chiều truyền thông.
- Packet drop hoặc delay kéo dài đến mức không phân biệt được với đứt mạng.
- Firewall, route, load balancer hoặc DNS gây phân tách kết nối.
- Client vào được node A, nhưng node A không nói chuyện được với các replica cần thiết.

### 5.1. P không phải công tắc bật/tắt

Nếu triển khai trên mạng có thể gặp lỗi, không thể **chọn “CA” để loại bỏ khả năng partition**. Ta có thể giảm xác suất, giảm tác động và thiết kế phản ứng phù hợp, nhưng không điều khiển được mọi lỗi mạng.

### 5.2. Node chết khác node bị cô lập

| Hiện tượng | Node vẫn xử lý cục bộ? | Node khác liên lạc được? |
| --- | --- | --- |
| Crash hoàn toàn | Không | Không |
| Cô lập khỏi một phần cluster | Có thể | Không với phía còn lại |
| Quá tải/GC pause | Có thể rất chậm | Có thể trễ |
| Replica lag | Có thể trả read | Có thể đã có kết nối, nhưng trạng thái cũ |
| Split-brain | Hai phía có thể tự nhận quyền ghi | Không xác minh authority được |

Điểm CAP quan tâm là **node còn sống nhưng mất khả năng trao đổi thông tin để giữ hợp đồng chung**.

## 6. Sửa câu “chọn hai trong ba”

Cách diễn đạt chính xác và hữu ích hơn:

> **Khi partition ảnh hưởng các node phải phối hợp cho cùng một operation, không thể luôn bảo đảm cả tính nhất quán tuyến tính và khả năng hoàn tất hợp lệ mọi request gửi tới các node còn sống.**

Khi mạng bình thường, một hệ có thể đồng thời **consistent và available**. Khi partition:

- Một nhóm còn đủ quorum có thể tiếp tục strong read/write.
- Nhóm thiểu số có thể phải từ chối hoặc chờ operation mạnh.
- Một số endpoint có thể trả read stale nếu hợp đồng cho phép.
- Những object không cần phối hợp với phía bị cắt vẫn có thể hoạt động.
- Một API có thể nhận một **ý định PENDING**, không hứa kết quả CONFIRMED ngay.

Do đó, **CP/AP là cách mô tả chính sách trong tình huống lỗi cụ thể**, không phải nhãn tuyệt đối của một logo database.

## 7. Lịch H1 — A xác nhận write, B đọc sau khi mất liên lạc

Giả sử A và B đều giữ register `x`, ban đầu:

~~~text
A.x = 0
B.x = 0
~~~

Lúc 10:00, đường A↔B bị cắt, nhưng mỗi node vẫn nhận request địa phương.

### 7.1. Lịch có thời điểm và dữ liệu cụ thể

| Thời điểm UTC giả định | Nơi xảy ra | Sự kiện | Trạng thái |
| --- | --- | --- | --- |
| 10:00:00.000 | Network | A↔B bị cắt | `A.x=0`, `B.x=0` |
| 10:00:00.010 | Client 1 → A | Invoke `write(1)` | — |
| 10:00:00.020 | A | Lưu cục bộ `x=1` | `A.x=1`, `B.x=0` |
| 10:00:00.030 | A → Client 1 | Trả `SUCCESS` | Write đã được xác nhận |
| 10:00:00.040 | Client 2 → B | Invoke `read()` | B vẫn có `x=0` |
| 10:00:00.050 | B | Cần trả lời | ? |

Theo đặc tả register, **write đã hoàn tất trước khi read bắt đầu**. Nếu không có writer khác, read tuyến tính phải thấy `1`.

Nhưng B chưa nhận được message từ A và không biết A đã thay đổi `x`.

### 7.2. Nếu B trả 0

~~~text
write(1) -> SUCCESS
read()   -> 0
~~~

Hệ đã phục vụ read cục bộ, nhưng **history không linearizable** cho cùng register: write thành công trước, read bắt đầu sau lại thấy giá trị cũ.

### 7.3. Nếu B chờ hoặc từ chối read mạnh

~~~text
write(1) -> SUCCESS
read()   -> WAIT / TIMEOUT / UNAVAILABLE
~~~

Hệ tránh công bố dữ liệu không phù hợp với consistency mạnh, nhưng B vẫn sống và **không thể hoàn thành read như đặc tả** trong lúc partition kéo dài. Nó đã đánh đổi availability CAP cho request ấy.

### 7.4. Tại sao B không thể đoán đúng?

Đặt hai thế giới:

| Thế giới | A đã làm gì? | B biết gì từ sau partition? | Giá trị read đúng |
| --- | --- | --- | --- |
| W0 | Không có write mới | Không có message từ A | 0 |
| W1 | `write(1)` thành công | Không có message từ A | 1 |

Đối với B, **thông tin cục bộ trong W0 và W1 giống nhau**. Nếu B luôn trả 0, sai W1. Nếu luôn trả 1, sai W0. Không có thuật toán nào từ thông tin B đang có bảo đảm trả kết quả đúng ngay trong **mọi lịch partition**, đồng thời luôn hoàn tất operation.

Đó là trực giác của lập luận **không thể phân biệt** (*indistinguishability*).

### 7.5. Những điều không được suy ra

- Không phải mọi operation ở mọi node đều phải dừng. A có thể còn quyền phục vụ.
- Nếu thiết kế không cho A xác nhận write khi chỉ có một replica, lịch H1 có thể **không xảy ra**: đánh đổi sẽ thể hiện ở write bị chặn trước.
- Một `read()` eventual ở B có thể được phép trả 0; lúc đó **hợp đồng không phải linearizable read**.
- Cần xác định key, routing, mức read/write consistency, không chỉ nhìn hình có hai server.

## 8. Lịch H2 — Cả hai phía cùng nhận ghi

Một Order ban đầu có:

~~~json
{
  "orderId": "O900",
  "status": "CREATED",
  "version": 7
}
~~~

Trong partition:

| Thời điểm | Region A | Region B |
| --- | --- | --- |
| 10:01:00 | Client A gọi `set(CANCELLED)` | — |
| 10:01:01 | A lưu và trả SUCCESS | — |
| 10:01:02 | — | Client B gọi `set(CONFIRMED)` |
| 10:01:03 | — | B lưu và trả SUCCESS |
| 10:01:04 | Read A → `CANCELLED` | Read B → `CONFIRMED` |
| 10:03:00 | Mạng hồi phục | Cần reconcile |

Cho phép ghi ở cả hai phía có thể tăng khả năng phục vụ cục bộ, nhưng sẽ tồn tại hai trạng thái đã được **xác nhận** và chưa được đồng bộ.

### 8.1. Last-write-wins không giữ mọi ý định

Giả sử sau heal hệ chọn `CONFIRMED` vì timestamp được xem là mới hơn:

~~~text
A đã báo CANCELLED thành công.
B đã báo CONFIRMED thành công.
Trạng thái hội tụ cuối: CONFIRMED.
~~~

Hai replica nhất trí một giá trị, nhưng **ý định hủy đã được xác nhận** có thể bị mất. Nếu khách đã nhận email hủy hoặc khoản hoàn tiền đã được khởi tạo, LWW không thể đơn giản xóa mọi tác động ấy.

### 8.2. Trở lại bài toán ghế

~~~text
Region A: reserve(seat-007,A101) -> RESERVED
Region B: reserve(seat-007,B202) -> RESERVED
~~~

Khi mạng hồi phục, chọn A101 “thắng” không làm lời hứa đã gửi cho B202 chưa từng xảy ra. Muốn bảo vệ **một ghế chỉ có một booking được xác nhận**, cần authority, transaction/conditional write hoặc phân quyền sử dụng trước; không thể chỉ đợi reconcile sau.

### 8.3. Đổi API thành PENDING là đổi hợp đồng

Trong partition, API có thể trả:

~~~json
{
  "requestId": "B202",
  "status": "PENDING_CONFIRMATION"
}
~~~

Đó là cam kết **nhận ý định để xử lý sau**, không phải khẳng định ghế đã thuộc về khách. Một endpoint tiếp nhận được yêu cầu PENDING có thể khả dụng hơn, nhưng **không chứng minh** operation `reserveConfirmed` vừa linearizable vừa available.

## 9. Ví dụ ba node và majority quorum

Giả sử có ba replica `A`, `B`, `C` và giao thức cần **đa số hai node** để xác nhận write.

~~~text
N = 3
Majority = 2

Network partition:
  Group 1: A <--> B
  Group 2: C
  No connection between groups.
~~~

~~~mermaid
flowchart LR
    X["Client nhóm 1"] --> A["Node A"]
    A <--> B["Node B"]
    Y["Client nhóm 2"] --> C["Node C"]
    B -.- P["Mất liên lạc"]
    P -.- C
~~~

### 9.1. Nhóm đa số có thể tiếp tục

A và B có **2/3 node**, đủ majority. Nếu protocol replication/consensus và mode request thật sự bảo đảm được quyền ghi theo quorum, nhóm A/B có thể tiếp tục strong write/read phù hợp.

### 9.2. Node C còn sống nhưng thiếu quorum

C có thể trả healthcheck tốt, nhận request từ client và có dữ liệu cũ, nhưng **không đủ quyền xác nhận write yêu cầu majority**. Để tránh split-brain hoặc công bố trạng thái xung đột, C phải chờ/từ chối các operation mạnh ấy.

Điều này không đồng nghĩa **toàn cluster down**: nhóm đa số vẫn hoạt động. Một số hệ còn cho phép C trả local/stale read theo hợp đồng khác.

### 9.3. Tại sao cụm hai node nhạy với partition 1–1?

Nếu `N=2` và majority lớn hơn `N/2`, cần cả **hai** node. Partition 1–1 khiến không phía nào có majority. Cụm ba voter có thể tạo nhóm 2–1, nhưng một witness/arbiter tùy hệ có thể chỉ bỏ phiếu mà không chứa dữ liệu. Không được tự suy mọi read/write được đảm bảo chỉ vì số voter lẻ.

## 10. Quorum R, W và công thức R + W > N

Một mô hình quorum đọc/ghi đơn giản có:

- `N`: số replica của một data item.
- `R`: số replica tham gia read.
- `W`: số replica tham gia write/ack.

Điều kiện thường gặp:

\[
R + W > N
\]

Với tập replica **cố định**, hai tập gồm `R` và `W` node bắt buộc **giao nhau ít nhất một node**.

Ví dụ:

~~~text
N = 3
R = 2
W = 2

R + W = 4 > 3
~~~

### 10.1. Nhưng giao quorum chưa đủ để bảo đảm linearizability

Còn phải biết:

- Write nào đã commit và được ack?
- Read có chọn **phiên bản hợp lệ mới nhất** hay có read barrier/quorum read đúng không?
- Concurrent writes được sắp thứ tự/giải quyết xung đột ra sao?
- Quorum có luôn thuộc cùng tập owner không, hay dùng **sloppy quorum**?
- Có leader term, membership change, failover, hinted handoff không?
- Timestamp LWW và durability có thể làm một write từng được ack bị rollback không?

**`R + W > N` là tính chất giao tập trong một mô hình**, không tự chứng minh mọi triển khai NoSQL đều linearizable.

### 10.2. Bảng ví dụ

| N | R | W | R+W>N? | Hệ quả cơ bản |
| ---: | ---: | ---: | --- | --- |
| 3 | 2 | 2 | Có | Quorum giao nhau, cần nhiều replica cho cả đọc và ghi |
| 3 | 1 | 3 | Có | Read ít replica, write cần tất cả |
| 3 | 1 | 1 | Không | Read và write có thể không chạm cùng replica |
| 5 | 3 | 3 | Có | Majority cho cả hai |
| 5 | 2 | 2 | Không | Hai quorum có thể rời nhau |

Trong partition, nếu một phía không đủ `W`, write yêu cầu `W` có thể không được phục vụ. Đó là đánh đổi thực tế, không phải lỗi kỳ lạ của database.

## 11. Leader, bầu chọn và split-brain

Một số hệ chọn **leader** cho từng phạm vi dữ liệu:

~~~text
               Client
                 |
               Leader A
               /      \
          Replica B   Replica C
~~~

Partition tạo:

~~~text
{ A }  |  { B, C }
~~~

Nếu A vẫn cho rằng mình là leader và nhận write, còn B/C bầu leader mới cũng nhận write, có thể xuất hiện **split-brain**: hai bên tự nhận quyền ghi vào một state machine.

### 11.1. Term/epoch và quorum

Các giao thức mạnh thường quản lý:

- Election với `term`/`epoch`.
- Điều kiện majority để xác nhận quyền commit.
- Bỏ quyền writer cũ khi đã có term mới.
- Fencing token để chặn tác động từ worker/leader cũ lên tài nguyên ngoài.

Một node còn chạy hoặc có khả năng trả `PING` **không đồng nghĩa** nó còn quyền commit.

### 11.2. Fencing token

Giả sử worker A từng có token 41, worker B sau failover có token 42. Tài nguyên đích ghi nhận token lớn nhất và:

~~~text
reject write if fencingToken < maxSeenToken
~~~

Khi A quay lại và gửi write với token 41, nó bị chặn. Điều kiện then chốt: **tài nguyên đích phải thực sự kiểm tra token**; ghi token trong log ứng dụng không đủ.

### 11.3. Lease và đồng hồ

Lease có thể giới hạn thời gian một leader được phép ghi, nhưng phụ thuộc giả định về clock drift, thời hạn lease và message delay. Không được suy “A chưa thấy lease hết hạn theo đồng hồ local” thì A chắc chắn vẫn có authority trong mọi kiểu partition.

## 12. Timeout và unknown outcome

Một request không có response có thể vì:

- Node chết.
- Network bị cắt một hoặc hai chiều.
- Message tới muộn, queue lâu.
- Node bị quá tải/GC pause.
- Database đã commit nhưng **response bị mất**.

Ví dụ:

~~~text
10:10:00.000  Client gửi reserve(requestId=R42)
10:10:00.450  Database commit thành công
10:10:00.460  Response bị mất
10:10:00.800  Client thấy TIMEOUT
~~~

**TIMEOUT không chứng minh write chưa xảy ra.** Nếu client retry một phép trừ tồn kho không idempotent, cùng một ý định có thể bị áp hai lần.

### 12.1. Phân biệt operation và attempt

~~~text
logicalRequestId = R42
attempt-1 -> UNKNOWN_OUTCOME
attempt-2 -> retry cùng ý định
~~~

Một thiết kế cần ID ý định ổn định, trạng thái dedup/transaction và đường đối soát. Bảo vệ concurrent writes bằng CAS hoặc conditional update **không tự giải quyết duplicate retry**.

### 12.2. Availability và timeout

CAP nói về bảo đảm lý thuyết khi request được gửi tới node không hỏng. SLA thực tế có deadline riêng: API có thể phải trả `503` sau 800 ms để không làm người dùng chờ quá lâu. Đây là **một quyết định sản phẩm hợp lý**, nhưng không biến request chưa hoàn thành thành available theo nghĩa hình thức.

## 13. Hội tụ sau partition không tự bảo vệ nghiệp vụ

Một hệ eventual có thể:

~~~text
During partition:
  Replica A: status=CANCELLED
  Replica B: status=CONFIRMED

After healing:
  Replica A: status=CONFIRMED
  Replica B: status=CONFIRMED
~~~

Các replica đã **hội tụ**, nhưng một hành động hủy đã được A xác nhận có thể bị mất. Nếu bên ngoài đã thực hiện refund/email, cần xử lý hậu quả.

### 13.1. LWW

Last-write-wins đơn giản, có thể hội tụ nhanh, nhưng **làm mất một phiên bản**. Clock skew càng làm thứ tự theo timestamp khó đại diện đúng ý định hoặc nhân quả.

### 13.2. Merge từng thuộc tính

Merge hai bản sửa có thể hữu ích khi các field độc lập. Nhưng địa chỉ gồm street/city/postalCode là một đơn vị nghiệp vụ; trộn các field từ hai bản sửa khác nhau có thể cho kết quả sai dù không có conflict kỹ thuật.

### 13.3. Event log, idempotency và compensation

Với booking hoặc thanh toán, cần biết **operation ID, event ID, amount, trạng thái xác nhận, nguồn authority**. Một bản ghi cuối giống nhau ở các replica không thay thế việc đối soát những tác động đã được gửi ra ngoài.

## 14. Escrow/quota: thay đổi mô hình để giảm phối hợp

Giả sử còn 100 sản phẩm, hai region cùng phục vụ đơn đặt hàng. Nếu A/B mỗi bên giữ cùng một số `stock=100` rồi tự giảm, có thể oversell.

Một phương án là **phân bổ trước quyền bán**:

~~~text
Global available stock = 100
Allocated quota A      = 60
Allocated quota B      = 40
~~~

Trong partition:

- A có thể xác nhận tối đa 60 đơn vị theo quota được cấp.
- B có thể xác nhận tối đa 40 đơn vị.
- Nếu A dùng hết 60 nhưng B còn 20, A **không tự lấy 20 của B** khi không có giao thức chuyển quyền an toàn.

Đây là cách giảm yêu cầu phối hợp cho từng operation cục bộ. Nó **không xóa CAP**; nó đã thay đổi cách biểu diễn invariant bằng quyền phân bổ.

### 14.1. Invariant của quota

\[
\sum_{i=1}^{n}\text{quota}_i \leq \text{available inventory}
\]

Chuyển quota, thu hồi từ vùng chết và cấp thêm vẫn phải có quyền authority và cơ chế chống **cấp trùng**. Không thể chép 100 cho cả A lẫn B rồi gọi đó là escrow.

### 14.2. Đánh đổi mới

A có thể tạm “hết hàng” dù B còn quota. Doanh nghiệp chấp nhận giảm tính linh hoạt điều phối để đổi lấy khả năng phục vụ cục bộ an toàn hơn trong partition.

## 15. CRDT và khả năng hội tụ

Một số cấu trúc dữ liệu có thể được thiết kế để merge mà không làm mất những operation mang tính cộng gộp. Ví dụ **G-Counter** của hai replica.

Ban đầu logical count = 10, được biểu diễn bằng vector:

~~~text
Initial = [10, 0]
~~~

Trong partition:

~~~text
A increment 2 times -> [12, 0]
B increment 3 times -> [10, 3]
~~~

Khi heal:

~~~text
merge per-component max:
[max(12,10), max(0,3)] = [12,3]

value = 12 + 3 = 15
~~~

Cấu trúc này giữ được các increment theo mô hình đã giả định. Nếu chỉ có một scalar và chọn LWW, một số increment có thể biến mất.

### 15.1. Không đồng nhất convergence với stock không âm

Một PN-counter có thể gộp các phép tăng/giảm, nhưng điều đó **không tự bảo đảm** không có hai phía trừ quá lượng hàng còn lại trong partition. Để bảo vệ tài nguyên hữu hạn, cần **escrow/rights**, một authority/conditional write hoặc giao thức phối hợp phù hợp.

### 15.2. Không phải mọi domain object có merge tự động đúng

State machine của Order, lệnh hoàn tiền và sửa địa chỉ có thể cần conflict handling theo nghiệp vụ; chọn một merge algorithm kỹ thuật không đủ để tự hiểu **ý định người dùng**.

## 16. Khi mạng hồi phục, hệ cần làm gì?

Heal mạng không có nghĩa dữ liệu đã tức thì nhất quán:

~~~text
1. Phát hiện kết nối khôi phục.
2. Trao đổi log/versions còn thiếu.
3. Xác định committed operations và term/authority.
4. Repair hoặc merge các replica.
5. Đối soát request UNKNOWN/PENDING.
6. Cập nhật cache/search/read model.
7. Xử lý compensation cho cam kết nghiệp vụ sai.
8. Kiểm tra trạng thái cuối và dữ liệu đã được ack.
~~~

Các chỉ số cần theo dõi:

| Metric | Mục đích |
| --- | --- |
| Replication lag | Replica chậm bao lâu/bao nhiêu version |
| Conflict count | Có bao nhiêu key/operation bất đồng |
| Repair throughput | Tốc độ bắt kịp khi mạng hồi phục |
| Rollback count | Những write ack yếu có bị mất sau failover không |
| Unknown requests | Các ý định cần xác minh lại |
| Compensation pending | Các nghiệp vụ chưa bù trừ xong |
| Recovery duration | Bao lâu khôi phục được SLO |
| Invariant violation | Có oversell/double booking/data leak không |

**Convergence của state cuối không chứng minh những response đã gửi trong partition đều đúng**. Cần cả operation history.

## 17. CAP và PACELC

Khi mạng **không bị cắt**, hệ vẫn phải cân bằng latency và consistency. Một mô hình thường dùng để diễn đạt là **PACELC**:

> Nếu xảy ra **P**artition, xét **A**vailability hay **C**onsistency; **E**lse (không partition), cân bằng **L**atency với **C**onsistency.

Ví dụ giả định:

~~~text
Round trip tới local replica:   5 ms
Round trip tới region khác:    90 ms
~~~

Read từ replica gần client có thể nhanh nhưng stale. Read cần leader/quorum có thể tốn thêm phối hợp, nhưng bảo đảm mạnh hơn tùy thuật toán và cấu hình.

Không thể suy chính xác p95 của một database chỉ từ hai số RTT: còn batching, hàng đợi, số vòng message, cache, I/O và số shard liên quan.

### 17.1. Nên đo SLO nào?

- Read/write p50, p95, p99.
- Timeout/error rate.
- Staleness tuổi dữ liệu.
- Replication/conflict backlog.
- Recovery time và data loss.
- Correctness/invariant violations.

CAP là **giới hạn mô hình**, không thay thế benchmark và SLO sản phẩm.

## 18. Đánh giá theo từng hệ NoSQL

Không nên áp một nhãn cố định lên cả vendor mà không xét **operation, mode read/write, index, region và topology**.

### 18.1. MongoDB replica set

Một replica set có primary và secondary. Khi phân tích partition, hãy hỏi:

- Ai đang là primary, election/quorum ra sao?
- `writeConcern` xác nhận write ở mức nào? Có khả năng rollback write đã ack với concern yếu sau failover không?
- `readConcern` và read preference là gì?
- Read có tới secondary và thấy phiên bản cũ không?
- Session/causal context có được dùng cho read-after-write không?

**Không kết luận** “MongoDB luôn CP cho mọi read/write” hay “mọi read từ secondary đều linearizable”.

### 18.2. Cassandra và ScyllaDB

Các hệ wide-column có consistency level cho những đường read/write:

- Mức yêu cầu ít replica có thể phục vụ nhiều request hơn khi một số replica unreachable.
- Quorum có thể timeout khi không đủ replica.
- LWT/CAS dùng cơ chế phối hợp riêng để bảo vệ conditional updates.
- Hinted handoff, repair, topology datacenter và cách xử lý concurrent writes ảnh hưởng kết quả.

`R+W>N` chỉ là điều kiện overlap theo mô hình nhất định; muốn nói về linearizability phải hiểu **protocol và loại mutation** thực tế.

### 18.3. DynamoDB

DynamoDB có:

- Các chế độ read consistency theo từng API và loại index.
- Conditional writes và `TransactWriteItems` theo phạm vi hỗ trợ.
- GSI thường có ngữ nghĩa read/replication khác một số đường đọc mạnh từ bảng nguồn.
- Global tables ở nhiều region có cập nhật và xử lý xung đột theo cơ chế riêng.

Cần hỏi **vùng nào, table/index nào, mode nào, điều kiện xác nhận nào** trước khi kết luận.

### 18.4. Redis

Redis cung cấp lệnh nguyên tử trên key trong mô hình server của nó, nhưng:

- Primary–replica replication có thể bất đồng bộ.
- Read từ replica có thể stale.
- Failover/persistence ảnh hưởng durability của write đã ack.
- Redis Cluster định tuyến theo slot, có chính sách phục vụ khi cluster mất liên lạc.
- `WAIT` có ngữ nghĩa chờ replica acknowledgement, **không tự trở thành consensus transaction cho mọi workflow**.

Không gọi Redis “CA” hay “AP” cố định ngoài bối cảnh cụ thể.

### 18.5. Search và read models

~~~text
Authoritative DB -> CDC / events -> Search index
~~~

Một query search có thể hoạt động trong khi nguồn tạm unavailable nhưng trả dữ liệu stale. Phù hợp cho tìm kiếm/gợi ý theo freshness SLO; không nên dùng trạng thái search chưa kiểm tra để quyết định **thu hồi quyền, thanh toán hay giữ ghế cuối cùng**.

### 18.6. Bảng câu hỏi thay cho nhãn vendor

| Câu hỏi | Điều cần nêu rõ |
| --- | --- |
| Write authority | Leader/quorum/region owner hay nhiều writer |
| Read path | Primary, secondary, quorum, cache hay GSI |
| Consistency mode | Strong/causal/eventual theo API |
| Ack semantics | Commit/durability mức nào |
| Partition behavior | Majority/minority có tiếp tục không |
| Conflict handling | CAS, LWW, version, CRDT, merge |
| Recovery | Replay, repair, rollback, compensation |

## 19. Mô phỏng một partition bằng Python

Đây là **mô phỏng giáo dục**, không phải algorithm consensus, replication an toàn hay một database thật.

~~~python
from dataclasses import dataclass


@dataclass
class Replica:
    name: str
    value: int = 0


a = Replica("A")
b = Replica("B")
link_up = True


def replicate(source: Replica, target: Replica):
    if not link_up:
        return False
    target.value = source.value
    return True


def local_write(node: Replica, value: int):
    node.value = value
    return "SUCCESS"


def local_read(node: Replica):
    return node.value


assert a.value == b.value == 0

# A và B tiếp tục phục vụ client cục bộ, nhưng không liên lạc.
link_up = False

print("A write:", local_write(a, 1))
# B đọc SAU khi write ở A đã báo SUCCESS.
print("B read:", local_read(b))
print("A:", a.value, "B:", b.value)

# Heal và sao chép một chiều chỉ để minh họa hội tụ.
link_up = True
replicate(a, b)
print("After heal:", a.value, b.value)
~~~

Kết quả minh họa:

~~~text
A write: SUCCESS
B read: 0
A: 1 B: 0
After heal: 1 1
~~~

Giá trị `B read: 0` trái với một hợp đồng read linearizable của cùng register nếu write A đã được xác nhận trước read. Sau heal, hai bản sao giống nhau **không sửa lại response stale đã từng trả**.

Script không có real network, quorum, failover, concurrent threads, durability hay idempotency. Nó chỉ minh họa **sự thiếu thông tin cục bộ của B**.

## 20. Kiểm thử partition trong môi trường lab

Chỉ tạo lỗi mạng trên **cluster thử nghiệm riêng có dữ liệu giả**. Không tự ý chặn traffic production.

### 20.1. Mẫu cấu hình thí nghiệm

~~~yaml
experimentId: cap-lab-01
databaseAndVersion: "ghi sản phẩm/phiên bản"
topology: "three nodes, replication factor three"
data:
  key: "cap-lab/register-1"
  initialValue: 0
fault:
  kind: "bidirectional partition"
  groups: ["A,B", "C"]
operations:
  - "write(1)"
  - "read()"
capture:
  - "operationId, requestId, attemptId"
  - "invokeAt and responseAt"
  - "read/write consistency"
  - "node, leader, term, version"
  - "ack, conflict, timeout"
  - "authoritative post-heal verification"
~~~

Đây chỉ là **mẫu thông tin cần lưu**, không phải cú pháp của một fault-injection tool cụ thể.

### 20.2. Quy trình

1. Chốt contract: read linearizable hay eventual; một key hay transaction nhiều key?
2. Khởi tạo dữ liệu và version; kiểm tra baseline mạng tốt.
3. Tạo partition có thể đảo ngược giữa các nhóm test.
4. Gửi write/read vào cả hai phía theo timeline định trước.
5. Thu **response, error, timeout, consistency mode, version**, không chỉ health status.
6. Ghi outcome `UNKNOWN` nếu client timeout nhưng chưa có chứng cứ write không commit.
7. Khôi phục mạng; theo dõi replication, merge, rollback và repair.
8. Đọc lại nguồn có thẩm quyền với consistency phù hợp.
9. Đánh giá operation history và invariant nghiệp vụ.
10. Lặp lại với partition một chiều, failover và mức đồng thời khác nếu môi trường hỗ trợ.

### 20.3. Bảng log quan sát

| Thời điểm | Client/Node | Operation | Kết quả | Ghi chú |
| --- | --- | --- | --- | --- |
| t0 | All | Khởi tạo `x=0` | OK | version 10 |
| t1 | Network | Partition `{A,B}|{C}` | Fault active | Ghi đường mạng |
| t2 | Client A | `write(1)` | ACK/timeout thực tế | Ghi mode |
| t3 | Client C | `read()` | 0/1/error thực tế | Ghi mode |
| t4 | Network | Heal | Restore | Theo dõi catch-up |
| t5 | Source | Read verify | Giá trị/version | Nguồn authority |

Không chấm “pass” chỉ vì các process quay về trạng thái `healthy`. **Tính đúng dữ liệu và response** mới là nội dung cần kiểm chứng.

## 21. Dựng lịch linearizability từ dữ liệu

Ví dụ:

~~~text
W:
  invoke  = 10:00:00.010
  response= 10:00:00.030
  write(1) -> SUCCESS

R:
  invoke  = 10:00:00.040
  response= 10:00:00.050
  read() -> 0
~~~

Vì `response(W)` **trước** `invoke(R)`, mọi thứ tự tuyến tính phù hợp bắt buộc W đứng trước R. Với register ban đầu 0 và không có writer khác, R phải trả 1. Đây là một **history không linearizable** theo những giả định đã đặt.

### 21.1. Operation overlap có thể đổi thứ tự

~~~text
W1 write(1): invoke=0,  response=30
W2 write(2): invoke=10, response=20
R  read():   invoke=40, response=50, result=1
~~~

W1 và W2 chồng lấn; ta có thể xếp W2 rồi W1, sau đó R thấy 1. Không được suy thứ tự hiệu lực chỉ từ **thứ tự bắt đầu hoặc kết thúc** của operation overlap.

### 21.2. Clock skew

Nếu A nhanh 200 ms còn B chậm 150 ms, sort log giữa hai node theo wall-clock có thể đảo cả quan hệ gửi/nhận message. Khi phân tích:

- Dùng monotonic clock cho duration trong từng process.
- Dùng correlation ID, message ID, term và source version để dựng causal order.
- Ghi clock uncertainty nếu so timestamp giữa node.
- Không so `System.nanoTime()` của hai JVM như một đồng hồ toàn cục.

### 21.3. Operation pending

Write timeout có thể đã commit. Nếu không biết outcome, history phải ghi `UNKNOWN`. Một checker nghiêm túc phải xử lý incomplete operation chứ không tự bỏ qua mọi write chưa có response.

## 22. Chọn chính sách theo yêu cầu nghiệp vụ

| Bài toán | Nguy cơ nếu hai phía cùng ghi | Hướng suy nghĩ |
| --- | --- | --- |
| Ghế duy nhất | Double booking | Authority/conditional transaction hoặc PENDING |
| Tồn kho giới hạn | Oversell | Atomic conditional decrement hoặc escrow |
| Payment capture | Double charge | Ledger, idempotency, nguồn giao dịch có thẩm quyền |
| Giỏ hàng offline | Hai thiết bị thay đổi độc lập | Merge, version, quy tắc conflict |
| Like/view count | Counter có thể tạm lệch | Aggregation/CRDT khi semantics phù hợp |
| Search catalogue | Dữ liệu stale | Freshness SLO, nguồn chuẩn khi quyết định quan trọng |
| Dashboard | Thống kê trễ | Read model eventual, reconciliation |
| Thu hồi quyền truy cập | Replica stale tiếp tục cho phép | Mức consistency/authority mạnh cho kiểm tra quyền nhạy cảm |

### 22.1. Một ứng dụng có thể có nhiều contract

~~~text
Reservation writes: conditional / authoritative.
Catalogue reads: cached / eventual.
Cart offline writes: mergeable by domain rules.
Payment events: idempotent authoritative ledger.
Analytics: delayed materialized summary.
~~~

Đó là **nhiều workload với yêu cầu khác nhau**, không phải thủ thuật một database “vừa CP vừa AP” trong cùng operation bị partition.

## 23. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Chọn C + A, bỏ P.” | Mạng vẫn có thể đứt | Thiết kế chính sách khi partition |
| “Mọi lúc phải bỏ một chữ.” | Khi không partition có thể C và A | Đánh đổi nổi bật ở lỗi mạng |
| “Availability = 99,99% uptime.” | Khác định nghĩa hình thức | Đo SLO riêng |
| “HTTP 503 nhanh nghĩa available.” | Operation không được thực hiện | Xét response hợp lệ theo spec |
| “C nghĩa mọi replica lúc nào cũng giống nhau.” | Không phải linearizability | Xét read/write API |
| “C trong CAP = C trong ACID.” | Hai nghĩa khác | Phân biệt tuyến tính và invariant |
| “P là có ba replica.” | P là partition mạng | Xem link và topology |
| “Node còn alive là được ghi.” | Có thể mất quorum | Xác minh authority |
| “R+W>N tự bảo đảm linearizability.” | Chỉ bảo đảm overlap trong giả định | Xem protocol, version, membership |
| “Mọi database có nhãn CP/AP cố định.” | Thay đổi theo config/API | Phân tích từng operation |
| “LWW giữ mọi write đã được ack.” | Có thể làm mất một intent | Conflict resolution theo nghiệp vụ |
| “CRDT counter ngăn oversell.” | Convergence không tự giữ stock hữu hạn | Escrow/conditional write |
| “Timeout chắc chắn chưa commit.” | Response có thể mất | Unknown outcome, idempotency |
| “Heal xong mọi thứ đã đúng.” | Còn repair/compensation | Đối soát history và invariant |
| “Đọc final state là đủ.” | Có thể bỏ qua cam kết sai trước đó | Ghi invocation/response |
| “Thử partition trên production.” | Có thể gây downtime/mất dữ liệu | Dùng lab an toàn |

## 24. Bài tập vận dụng

### Bài 1 — Xác minh một lịch đọc/ghi

Ban đầu A/B có `x=0`. Sau partition, A trả SUCCESS cho `write(1)`. B nhận `read()` sau đó và trả 0.

1. Với hợp đồng read linearizable, lịch hợp lệ không?
2. Nếu B chờ để không trả stale, điều gì bị đánh đổi?
3. Tại sao B không thể biết A đã write hay chưa trong mọi history?
4. Nếu B chỉ hứa eventual read, kết luận khác gì?

### Bài 2 — Phân biệt CAP và SLA

Giải thích vì sao 99,95% uptime không phải chữ A của CAP, vì sao `503` nhanh không chứng minh availability theo đặc tả và vì sao p95 latency vẫn phải được đo độc lập.

### Bài 3 — Quorum ba node

Partition tách `{A,B}` và `{C}`, cần majority hai node.

1. Phía nào đạt majority?
2. Client gửi strong write tới C có thể thấy gì?
3. C có thể trả local stale read theo hợp đồng nào?
4. Sau heal C cần bắt kịp như thế nào?

### Bài 4 — Quorum năm node

Cho `N=5`, xét `(R,W)=(3,3)`, `(1,5)`, `(2,2)`.

1. Cặp nào có `R+W>N`?
2. Điều kiện này bảo đảm điều gì và chưa bảo đảm điều gì?
3. Với partition 3–2, những operation nào có thể bị ảnh hưởng?

### Bài 5 — Hai region giữ một ghế

Hai request độc lập cùng được báo `RESERVED` cho một ghế khi partition.

1. Invariant nào bị vi phạm?
2. LWW sau heal có giải quyết lời hứa với khách thua không?
3. Thiết kế `PENDING_CONFIRMATION` hoặc một authority cho ghế.
4. Cần request ID và event log gì để bù trừ?

### Bài 6 — Escrow stock

Stock=100, quota A=60, B=40.

1. Trong partition, A có thể bán tối đa bao nhiêu khi chưa có sale?
2. A dùng hết 60, B còn 20: vì sao A không tự sử dụng 20 đó?
3. Chuyển quota cần bảo vệ điều kiện nào?
4. Vì sao cùng chép `stock=100` vào A/B không phải escrow?

### Bài 7 — CRDT counter

Initial vector `[10,0]`. A tăng hai, B tăng ba.

1. Hai vector trong partition là gì?
2. Merge max theo component ra bao nhiêu?
3. LWW scalar có thể làm mất gì?
4. Vì sao counter hội tụ chưa đủ cho stock không âm?

### Bài 8 — Timeout sau commit

Database commit một reservation, response mất, client timeout và retry.

- Tại sao không kết luận attempt đầu chưa thực thi?
- Logical request ID khác attempt ID thế nào?
- Idempotency ledger cần ghi những gì?
- Crash giữa cập nhật stock và dedup record có thể gây lỗi gì?

### Bài 9 — Lịch với clock skew

A nhanh UTC thật 200 ms, B chậm 150 ms. A gửi message ở 10:00:00.100, B nhận ở 10:00:00.150 thời gian thật.

1. Timestamp log mỗi node là gì?
2. Sort timestamp có thể đảo thứ tự ra sao?
3. Message ID/source version giúp gì?
4. Monotonic clock trong hai JVM có thể so trực tiếp không?

### Bài 10 — Chọn consistency theo API

Đề xuất policy khi partition cho:

~~~text
POST /tickets/reserve-confirmed
POST /cart/items (offline)
GET  /products/search
POST /payments/capture
GET  /analytics/daily-summary
~~~

Với mỗi API, nêu source authority, mức stale chấp nhận, response PENDING/UNAVAILABLE, idempotency và reconciliation.

### Bài 11 — Phản biện nhãn vendor

Một người nói: “MongoDB luôn CP, DynamoDB luôn AP, Redis luôn CA.” Hãy lập câu hỏi phản biện về read/write concern, leader/quorum, table/index, region, consistency mode, failover, ack, stale read và conflict resolution.

### Bài 12 — Thiết kế fault-injection test

Thiết kế lab ba replica, partition 2–1: khởi tạo dữ liệu/version, chốt contract, tạo lỗi mạng an toàn, gửi operation vào hai phía, thu response và timestamp, heal, đối soát từ nguồn và đánh giá history.

## 25. Quy trình ra quyết định kiến trúc

~~~mermaid
flowchart TD
    A["Operation phân tán"] --> B["Xác định invariant và authority"]
    B --> C["Chốt contract consistency/freshness"]
    C --> D["Xét partition cụ thể"]
    D --> E{"Cần linearizability?"}
    E -->|Có| F["Leader/quorum/conditional write"]
    F --> G{"Đủ authority?"}
    G -->|Có| H["Serve với contract đã hứa"]
    G -->|Không| I["WAIT / UNAVAILABLE / PENDING"]
    E -->|Không| J["Local operation theo policy"]
    J --> K["Version + conflict merge + reconciliation"]
    H --> L["Fault injection và telemetry"]
    I --> L
    K --> L
    L --> M["Kiểm chứng history, invariant, SLO"]
~~~

Checklist trước khi quyết định:

1. **Operation nào?** Get, write, CAS, transaction hay nhận ý định bất đồng bộ?
2. **Bất biến là gì?** Không double-book, không oversell, không double-spend?
3. **Nguồn authority ở đâu?** Leader, quorum, region owner hay ledger?
4. **Partition giả định kiểu nào?** Một chiều, hai chiều, đa số/thiểu số, liên AZ/region?
5. **Operation cần mức consistency nào?** Strong, causal, bounded staleness hay eventual?
6. **Phía thiếu quorum làm gì?** Wait, timeout, reject hay pending?
7. **Nếu local write được chấp nhận, quy tắc conflict là gì?**
8. **Timeout xử lý thế nào để không áp trùng?**
9. **Sau heal phục hồi/đối soát như thế nào?**
10. **SLO latency, availability, freshness và invariant được đo ra sao?**

## Kết luận

**CAP không bảo rằng mỗi database phải chọn cố định hai tính năng trong ba.** Nó mô tả một giới hạn khi **các node cần phối hợp cho cùng dữ liệu có thể mất liên lạc**: hệ không thể luôn vừa cung cấp kết quả đọc/ghi tuyến tính theo thời gian thực, vừa bảo đảm mọi operation gửi tới node còn sống đều được hoàn tất hợp lệ trong mọi lịch network partition.

Các nguyên tắc cần nhớ:

- **C** trong CAP gắn với linearizability, không phải C trong ACID.
- **A** trong CAP là liveness của operation trên node không hỏng, khác uptime SLA.
- **P** là tình huống mạng có thể đứt, không phải một checkbox để tắt.
- **Khi mạng tốt**, hệ có thể vừa consistent vừa available; **khi partition**, một số operation cần phối hợp mới bộc lộ đánh đổi.
- **Leader/quorum** có thể giữ consistency bằng cách không cho phía thiếu authority xác nhận write; đổi lại phía ấy mất khả năng phục vụ operation mạnh.
- **Local write ở nhiều phía** có thể tăng availability nhưng tạo divergence, stale reads và rủi ro mất intent khi merge.
- **Convergence không tự bảo vệ bất biến nghiệp vụ**: LWW/CRDT không thay thế mọi điều kiện giữ ghế, stock và thanh toán.
- **Thay đổi mô hình có thể giảm phối hợp** bằng quota/escrow, quyền sở hữu theo key, nhận yêu cầu PENDING hoặc read model có freshness SLO.
- **Không gắn nhãn CP/AP tuyệt đối cho vendor**; phải xét operation, topology, consistency và cách ack.
- **Kiểm chứng bằng history cụ thể**, không chỉ bằng ping/healthcheck hoặc trạng thái cuối sau heal.

Câu hỏi quan trọng nhất khi đặt bài toán CAP là: **“Nếu các replica không thể trao đổi thông tin, những yêu cầu nào vẫn được phép xác nhận thành công, những yêu cầu nào phải chờ, và cam kết dữ liệu/nghiệp vụ nào tuyệt đối không được phép bị phá vỡ?”**
