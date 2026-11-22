# Phân tích một kịch bản lỗi mạng thay vì gắn nhãn CP/AP cho toàn sản phẩm

## 1. Đặt vấn đề: một database có thể vừa từ chối ghi, vừa cho đọc dữ liệu cũ

Giả sử ứng dụng đặt vé có ba node lưu trữ một bản ghi:

```json
{
  "seatId": "SHOW-2026-11-14-A12",
  "state": "AVAILABLE",
  "version": 7
}
```

Một cuộc gọi từ khu vực miền Bắc muốn **giữ ghế A12**, trong khi một người dùng khác ở miền Nam cũng muốn giữ cùng ghế. Đúng lúc đó, kết nối mạng giữa các node bị đứt.

Người vận hành hỏi: “Hệ NoSQL này là **CP hay AP**?” Câu hỏi nghe hợp lý nhưng chưa giúp quyết định phải làm gì. Những câu hỏi có ích hơn là:

- Node nào còn liên lạc được với node nào?
- Có node nào chết thật hay chỉ mất liên lạc?
- Những request nào đang đi vào từng phía của mạng?
- Thao tác **giữ ghế** phải bảo vệ điều kiện không bán trùng đến mức nào?
- Thao tác **xem danh sách ghế** có được trả trạng thái cũ không?
- Ghi được ACK ở một bên có còn tồn tại sau failover/rejoin không?
- Nếu một phía trả timeout, người dùng có được gửi lại request không?
- Search index hoặc cache có nằm trong cùng cam kết nhất quán với nguồn không?

Một hệ thống thực tế có thể **từ chối thao tác giữ ghế** khi không thể xác nhận quyền sở hữu, nhưng **vẫn phục vụ danh mục, hình ảnh, giá tham khảo hoặc danh sách ghế có cảnh báo trễ**. Đánh đổi phải được phân tích **theo thao tác, dữ liệu và kịch bản lỗi**, không bằng một nhãn CP/AP áp cho toàn sản phẩm.

Bài học này sử dụng một kịch bản phân hoạch mạng cụ thể, sau đó mở rộng sang MongoDB, Cassandra, Redis, DynamoDB, search/read model và các lựa chọn kiến trúc trong NoSQL.

## 2. CAP thật sự phát biểu về điều gì?

CAP thường được nhắc bằng ba chữ:

- **C — Consistency**: trong phát biểu CAP chuẩn, thường được hình thức hóa dưới dạng **atomic consistency/linearizability** của thao tác trên đối tượng được chia sẻ. Không phải “C” của ACID, không phải tất cả mức isolation, và không có nghĩa mọi field tự động đúng nghiệp vụ.
- **A — Availability**: mỗi yêu cầu gửi tới một node **không lỗi** cuối cùng phải được đáp ứng theo hợp đồng của thao tác. Không chỉ là máy chủ trả HTTP bất kỳ; trả `503` hoặc từ chối ghi vì mất quorum nghĩa là thao tác ghi đó **không sẵn sàng** trong ý nghĩa đánh đổi này.
- **P — Partition tolerance**: hệ phải xét trường hợp thông điệp giữa các node bị mất hoặc trễ vô hạn, dù bản thân các node vẫn hoạt động.

Trực giác bất khả thi:

> Khi mạng bị chia cắt làm các nhóm node không thể trao đổi thông tin, một hệ phân tán không thể đồng thời bảo đảm **mọi thao tác liên quan đều linearizable** và **mọi yêu cầu ở tất cả node không lỗi đều được phục vụ thành công** trong mọi lịch sử phân hoạch.

### Cần cẩn thận với ba chữ

**C không đồng nghĩa với “database không bao giờ trả dữ liệu lỗi thời” trong mọi tình huống mà không cần biết API.** CAP xét một mô hình nhất quán xác định; ở các đường đọc khác nhau, database có thể có những cam kết khác.

**A không đồng nghĩa 99,99% uptime hoặc p95 latency dưới 100 ms.** Đó là các chỉ tiêu SLO vận hành. Availability trong phát biểu lý thuyết là một điều kiện tiến triển khi có partition, không tự quy định deadline hay xác suất hoạt động.

**P không phải một tính năng có thể tắt để chọn C và A trong mạng thực.** Nếu có nhiều node liên lạc qua mạng, partition/loss/delay có thể xảy ra. Câu hỏi là hệ sẽ hành xử thế nào **khi partition thực sự xuất hiện**.

### Không nên dùng công thức “chọn hai trong ba” một cách máy móc

Trong trạng thái mạng khỏe, nhiều hệ cung cấp cả consistency mạnh và availability cho nhiều thao tác. Sự căng thẳng xuất hiện khi **không thể liên lạc giữa những node cần phối hợp**. Khi đó hệ có thể:

- Chờ hoặc từ chối ở phía không có đủ bằng chứng để bảo vệ nhất quán.
- Chấp nhận ghi/đọc cục bộ để tiếp tục hoạt động nhưng cho phép kết quả khác nhau giữa các phía.
- Chọn chính sách **khác nhau cho các operation**.

Do đó, thay vì “database X là CP”, ta nên nói **“trong partition này, thao tác W ở nhóm thiếu quorum bị từ chối để bảo vệ linearizability; thao tác đọc local R vẫn có thể trả bản cũ theo một hợp đồng yếu hơn”**.

## 3. Thuật ngữ của một bài phân tích lỗi mạng

| Thuật ngữ | Ý nghĩa thực tế |
|---|---|
| **Node** | Một tiến trình/máy tham gia lưu hoặc xử lý dữ liệu |
| **Replica** | Bản sao dữ liệu có thể nằm trên node khác |
| **Leader/primary** | Thành phần điều phối một số thao tác ghi hoặc thứ tự log |
| **Quorum/majority** | Số thành viên tối thiểu phải tham gia theo giao thức |
| **Network partition** | Một số nhóm node không truyền thông điệp cho nhau được |
| **Client route** | Client đang được phục vụ bởi node/region nào |
| **Commit** | Thao tác được chấp nhận chính thức theo giao thức |
| **ACK** | Phản hồi client nhận; phải biết ACK cam kết đến đâu |
| **Stale read** | Read trả trạng thái cũ hơn trạng thái có thẩm quyền |
| **Failover** | Chuyển vai trò sang node khác khi một node không dùng được |
| **Split-brain** | Nhiều phía cùng hành xử như bên có quyền ghi theo cách xung đột |
| **Reconciliation** | Phát hiện/giải quyết khác biệt khi mạng hồi phục |
| **RPO/RTO** | Mục tiêu mất dữ liệu/thời gian phục hồi, khác với mô hình CAP |

**Mất kết nối khác với node chết.** Từ góc nhìn A, việc không nhận phản hồi từ B có thể do B chết, gói tin bị chặn hoặc B đang rất chậm. Trong mạng bất đồng bộ, không có deadline đơn giản nào chứng minh tuyệt đối node kia đã chết.

**Đồng hồ cũng không giải quyết ngay bài toán.** Một timestamp lớn hơn không luôn có nghĩa write đã commit đúng hơn; clock skew, retry, concurrent writes và authority của leader vẫn phải được xét.

## 4. Kịch bản xuyên suốt: ba node bị chia thành nhóm 1 và nhóm 2

Xét một key `seat:A12` được sao chép trên ba node:

```text
Trước lỗi mạng:

                +----------+
                | Node A   | Leader
                | v7       |
                +----+-----+
                   /   \
                  /     \
             +----v--+  +--v----+
             |Node B |  |Node C |
             | v7    |  | v7    |
             +-------+  +-------+

Sau lỗi mạng:

       Nhóm 1                NHÓM 2
   +------------+     X   +------------+
   | Node A     |   <===> | Node B     |
   | (1 node)   |  network| Node C     |
   +------------+ partition+------------+
```

Giả định:

1. A ban đầu là leader; B và C là follower.
2. Cả ba có trạng thái đã commit `version=7`, `seat=A12 AVAILABLE`.
3. Liên lạc giữa A và B/C bị chặn theo cả hai chiều; **B vẫn nói chuyện được với C**.
4. Client `U1` vẫn gửi request tới A; client `U2` vẫn gửi request tới B/C.
5. Các node **chưa bị crash** và có thể tiếp tục phục vụ một số API.
6. Hệ áp dụng giao thức cần **đa số 2/3** để commit những ghi theo một thứ tự duy nhất.

Đây là một **mô hình minh họa có leader và majority**, không phải mô tả chính xác thuật toán của tất cả NoSQL database.

### Đặt lịch sử sự kiện

| Mốc | Sự kiện |
|---|---|
| T0 | Ba node có bản ghi v7, ghế AVAILABLE |
| T1 | Mạng chia `{A} | {B,C}` |
| T2 | U1 gửi “giữ ghế A12” tới A |
| T3 | U2 gửi “giữ ghế A12” tới nhóm B/C |
| T4 | B/C có thể phối hợp đủ hai node theo giao thức |
| T5 | Kết nối giữa hai nhóm được khôi phục |
| T6 | Hệ đồng bộ lại trạng thái và client truy vấn kết quả |

**Quan trọng:** phải định nghĩa chính xác request U1/U2 là **lệnh giữ ghế có điều kiện**, không phải một lệnh `SET` vô điều kiện. Bất biến nghiệp vụ là:

\[
\text{AtMostOneConfirmedReservation}(\text{seat A12})
\]

Tức là tại cùng một thời điểm nghiệp vụ, không được có hai reservation được xác nhận hợp lệ cho cùng ghế.

## 5. Nhánh 1: ưu tiên tính nhất quán khi thiếu quorum

Trong một giao thức leader/quorum đúng, A không đủ 2/3 thành viên để commit ghi mới.

```text
U1 ---> Node A (bị cô lập)
          |
          +--> không liên lạc được với B/C
          |
          +--> không đủ majority để commit
          |
          v
        timeout / rejected / retry-later

U2 ---> Node B/C (2 node)
          |
          +--> bầu/nhận diện leader hợp lệ sau thời gian cần thiết
          |
          +--> commit hold seat với majority
          |
          v
        ACK thành công
```

Nếu B/C được phép bầu leader theo đúng điều kiện và bảo toàn log đã commit, U2 có thể được xác nhận. A **không được tự phát một ACK “đã giữ ghế thành công” có cùng ý nghĩa commit**, vì như vậy có thể tồn tại hai phía tuyên bố giữ cùng ghế.

### Phía thiếu quorum có “chết” không?

Không nhất thiết. A vẫn có thể:

- Trả health check của process.
- Phục vụ nội dung tĩnh hoặc dữ liệu local theo chính sách.
- Trả thông báo “tạm thời không thể xác nhận giữ chỗ”.
- Cho truy vấn đọc best-effort hoặc cache cũ **nếu API công bố rõ hợp đồng yếu hơn**.

Nhưng thao tác **giữ ghế cần xác nhận duy nhất** không còn sẵn sàng ở A.

### Một read cũ cũng có thể vi phạm linearizability

Giả sử B/C đã commit `seat=HELD(v8)` và ACK cho U2. **Sau ACK đó**, một controller bắt đầu read tại A:

```text
U2 -> B/C: reserve seat -> ACK COMMITTED(v8)

Controller nhận ACK U2
Controller -> A: GET seat
A -> Controller: AVAILABLE(v7)
```

Vì read bắt đầu sau write đã hoàn tất và không có ghi đưa ghế về AVAILABLE, read này **không linearizable** nếu GET được hứa là strong read của cùng đối tượng. A phải chờ bằng chứng mới, từ chối/timeout hoặc thay đổi API thành **local stale read** không nằm trong hợp đồng mạnh.

**Sự khác biệt chính:** một node vẫn trả HTTP 200 với dữ liệu cũ không có nghĩa nó phục vụ thành công **strong read** được hứa.

### Vì sao B/C không chắc thành công ngay?

Có thể cần thời gian phát hiện leader cũ không còn liên lạc, bầu leader mới, đồng bộ thuật toán/log và kiểm tra tính hợp lệ của leader lease. Trong khoảng đó có thể xảy ra timeout trên cả hai phía.

CAP là một ràng buộc lý thuyết, **không hứa “nhóm majority luôn sẵn sàng ngay”**. Hành vi cụ thể còn phụ thuộc giao thức, topology, lỗi đồng thời và triển khai.

## 6. Nhánh 2: ưu tiên nhận yêu cầu ở cả hai nhóm

Xét một mô hình khác: cả A lẫn nhóm B/C **được phép nhận ghi local** trong lúc không liên lạc.

```text
             PARTITION

  U1 -> A: reserve A12        U2 -> B/C: reserve A12
          |                               |
          v                               v
     local state                    local state
       HELD_BY_U1                     HELD_BY_U2
          |                               |
          v                               v
       ACK U1                         ACK U2
```

Trong cùng một thế giới nghiệp vụ, **hai phía đã xác nhận giữ đúng một ghế cho hai người**. Khi mạng hồi phục, hệ phải chọn một giá trị hoặc hòa giải.

Không có cách nào biến hai ACK “ghế đã thuộc về bạn” thành một lịch sử linearizable giữ đúng quy tắc **chỉ một người có thể giữ ghế**, nếu cả hai client được xác nhận thành công với cùng điều kiện độc quyền.

### “Last write wins” giải quyết được không?

Một hệ có thể chọn giá trị có timestamp mới nhất:

```text
Node A:   HELD_BY_U1 @ t=1001
Node B/C: HELD_BY_U2 @ t=1002

Merge theo LWW:
    HELD_BY_U2 thắng
```

Sau khi hội tụ, dữ liệu chỉ còn U2. Nhưng U1 **đã nhận ACK thành công** rồi bị mất quyền; đây là **thay đổi ý nghĩa nghiệp vụ sau ACK**, không phải bằng chứng các ACK ban đầu được linearizable.

LWW còn có vấn đề về đồng hồ lệch, ghi đồng thời và những cập nhật bị mất. Một quy tắc hội tụ có thể hữu ích cho dữ liệu ít quan trọng như “màu giao diện ưu tiên”, nhưng không tự phù hợp với giữ chỗ độc quyền hay tiền.

### CRDT có giải quyết CAP không?

Các cấu trúc CRDT có thể hỗ trợ **merge deterministic** cho những kiểu dữ liệu/phép toán phù hợp:

- Counter phân tán với semantics đã xác định.
- Tập các phần tử thêm/xóa theo một loại CRDT cụ thể.
- Metadata hoặc sở thích cá nhân có thể chấp nhận concurrent updates.

Nhưng CRDT không tự cho phép **hai người cùng chiếm một tài nguyên độc quyền** rồi vẫn giữ bất biến “chỉ một người được xác nhận”. Với quota/tồn kho, có thể dùng các giao thức **escrow/bounded counters** cấp trước quyền tiêu thụ từng phần ngân sách cho các nhóm; điều này làm thay đổi bài toán bằng cách phân phối quyền từ trước, không xóa bỏ định lý CAP.

## 7. Chứng minh trực giác: hai phía không phân biệt được thế giới nào

Xét một thanh ghi `x=0` trên hai nhóm không liên lạc.

Trong lúc partition:

1. Client A gửi `WRITE(x=1)` tới nhóm trái.
2. Nhóm trái trả **thành công** để giữ availability.
3. Sau khi A đã nhận ACK, client B ở nhóm phải gửi `READ(x)`.
4. Nhóm phải không nhận thông điệp nào từ nhóm trái.

Nhóm phải không thể phân biệt:

- **Thế giới 1:** A chưa từng ghi, `x` vẫn là 0.
- **Thế giới 2:** A đã ghi và nhận ACK, `x` phải là 1 nếu read được hứa linearizable.

Nếu nhóm phải buộc phải trả read thành công ngay mà không thể liên lạc, nó phải chọn kết quả dựa trên thông tin cục bộ giống nhau ở cả hai thế giới. Trả `0` sai trong thế giới 2; trả `1` sai trong thế giới 1.

```text
LEFT GROUP                     RIGHT GROUP

W(x=1) -> ACK               Không nhận message
       |                            |
       +--- network partition ------+
                                    |
                                R(x) -> ?
```

Đó là cốt lõi đánh đổi CAP. Nó không phụ thuộc tên database, ngôn ngữ lập trình hay “database có nhiều replica”.

### Phân biệt với concurrent operations

Để tạo phản ví dụ linearizability rõ ràng, cần **WRITE hoàn tất trước khi READ bắt đầu**, chẳng hạn controller ngoài đường mạng giữa các replica chờ ACK rồi mới phát lệnh đọc. Nếu hai thao tác chồng lấn, linearizability có thể cho phép nhiều thứ tự hơn.

## 8. Phân tích cả đường đọc và đường ghi, không chỉ một nhãn

Giả sử ứng dụng cung cấp các API:

| API | Ý nghĩa nghiệp vụ | Khi node không có quorum | Bảo đảm cần thiết |
|---|---|---|---|
| `POST /seats/A12/reserve` | Xác nhận một người giữ ghế | Từ chối/chờ/chuyển tiếp an toàn | Không xác nhận trùng |
| `GET /seats/A12/authoritative` | Trạng thái hiện hành để ra quyết định | Chờ hoặc trả unavailable nếu không đảm bảo | Linearizable/nguồn có thẩm quyền theo thiết kế |
| `GET /events/catalog` | Mô tả suất diễn | Có thể trả cache cũ có TTL | Eventual được giới hạn |
| `GET /seats/availability-preview` | Gợi ý chỗ có thể chọn | Có thể trả dữ liệu trễ kèm thông báo | Không là cam kết giữ chỗ |
| `GET /user/reservations` | Hiển thị giao dịch của chính user | Có thể cần read-your-writes/session token | Không bỏ qua reservation vừa xác nhận |
| `GET /analytics/sold-seats` | Dashboard tổng hợp | Có thể chậm nếu có watermark | Eventual + reconciliation |

**Một sản phẩm có thể có chính sách khác nhau cho từng API** và đó là lựa chọn hợp lý. Không nên ép `GET catalog` phải có cùng consistency/availability với `POST reserve`.

### Đừng nhầm xử lý lỗi với phục vụ thành công

Nếu `POST reserve` trả `503 Retry-After` đúng lúc thiếu quorum, người dùng nhận được response hữu ích ở cấp HTTP, nhưng **operation reserve vẫn không available** theo cách diễn giải CAP.

Ở cấp SLO, hệ có thể phân biệt:

- **Transport availability:** request đến server và có response.
- **Functional availability:** tính năng thật sự hoàn tất thành công.
- **Consistency correctness:** phản hồi thành công có giữ bất biến không.

Ba chỉ số này không được gộp thành một.

## 9. Một ma trận đầy đủ cho partition 1 | 2

Giả sử A ở nhóm thiểu số, B/C ở nhóm đa số, và version v7 đã commit trước partition.

| Thao tác | Nhóm A (1 node) với policy quorum mạnh | Nhóm B/C (2 node) | Nếu hệ nhận local ở cả hai |
|---|---|---|---|
| Đọc linearizable hiện tại | Có thể chờ/từ chối nếu không chứng minh trạng thái mới nhất | Có thể phục vụ khi leader/read protocol sẵn sàng | Không thể đồng thời đảm bảo strong read trên cả hai |
| Đọc snapshot v7 | Có thể trả nếu API cho phép đọc stale | Có thể trả trong phạm vi trạng thái hợp lệ | Có thể trả local |
| Giữ ghế độc quyền | Không ACK commit nếu thiếu quyền/quorum | Có thể commit sau bầu leader/quorum | Nguy cơ xác nhận trùng |
| Ghi tùy ý “last-write-wins” | Không commit dưới policy quorum | Có thể commit | Cả hai có thể ACK, cần merge |
| Đọc catalog cache | Có thể phục vụ | Có thể phục vụ | Vẫn có thể phục vụ |
| Thay đổi quyền nhạy cảm | Phải giữ nguồn có thẩm quyền, có thể từ chối | Có thể commit nếu giao thức cho phép | Rủi ro lộ dữ liệu nếu phục vụ stale |
| Khi mạng nối lại | Bắt kịp log/role mới | Khôi phục replication | Resolve conflict, có thể cần bù trừ |

Từ bảng có thể thấy không có một ô “CP/AP” mô tả mọi thao tác. Bảng mới hữu ích vì chỉ ra **request nào bị từ chối, request nào thành công, loại kết quả nào được phép cũ và cần xử lý gì sau khi mạng hồi phục**.

## 10. ACK, commit và write concern: “đã nhận” khác “đã xác nhận hợp lệ”

Một lời gọi write có thể có nhiều mốc:

```text
Client gửi WRITE
       |
       v
Server nhận request
       |
       v
Ghi local vào bộ nhớ / log
       |
       v
Đợi replica / majority (nếu policy yêu cầu)
       |
       v
Commit theo giao thức
       |
       v
ACK client
```

Thứ tự kỹ thuật chính xác phụ thuộc engine, nhưng về mặt phân tích cần biết **ACK ở mốc nào**.

Một ACK từ leader **trước khi write đạt quorum** có thể phải rollback khi leader bị thay thế. Ngược lại, một ACK commit majority từ giao thức bảo toàn lịch sử đã commit cho kết luận khác về tính bền qua failover trong phạm vi cam kết.

### Timeout không phải bằng chứng “không ghi”

```text
T0 Client gửi reserve(A12, requestId=R1)
T1 Leader commit thành công
T2 Network làm mất ACK
T3 Client timeout
```

Client **không biết** reservation đã commit hay chưa. Nếu retry với request ID mới, hệ có thể tạo **hai tác động** hoặc thông báo lỗi mơ hồ tùy cách thiết kế.

Hướng an toàn:

- Dùng `requestId/idempotencyKey` ổn định.
- Dùng conditional write/transaction để kiểm tra trạng thái.
- Cho endpoint `GET /reservations/by-request/R1` để xác minh kết quả khi có thể.
- Không tạo quyền giữ ghế mới chỉ vì request đầu timeout.
- Nếu phía nguồn chưa đủ quorum để xác minh, trả trạng thái `UNKNOWN/PENDING_RETRY` thay vì tự nói thành công hoặc thất bại chắc chắn.

CAP bàn về **khả năng đáp ứng request và nhất quán dưới partition**; idempotency giải quyết **tác động nghiệp vụ khi phản hồi bị mất**. Cần cả hai.

## 11. Failover: node cũ còn sống có thể trở thành nguồn dữ liệu sai

Trong kịch bản:

```text
T0 A là leader, v7 committed
T1 A bị cô lập
T2 B/C chọn B làm leader hợp lệ
T3 B commit v8 với C
T4 A vẫn còn chạy và giữ dữ liệu v7
T5 A được kết nối lại
```

Nếu A vẫn tự xem mình có quyền xác nhận ghi, nguy cơ **split-brain** xuất hiện. Một giao thức leader election/epoch/term và quorum đúng phải ngăn việc hai leader độc lập cùng commit lịch sử xung đột theo cùng cam kết.

### Dữ liệu ở A sau nối mạng

Có thể cần:

- Cập nhật leader term/epoch.
- Dừng nhận write dưới nhiệm kỳ cũ.
- Bắt kịp log/replication từ leader có thẩm quyền.
- Rollback hoặc loại trạng thái local **chưa commit hợp lệ**, nếu cơ chế hệ cho phép/đòi hỏi.
- Phục hồi quyền phục vụ read/write theo các điều kiện thích hợp.

Không được tự chọn “node có timestamp mới nhất” làm nguồn có thẩm quyền. Trong giao thức consensus, **commit index, term và quyền leader hợp lệ** quan trọng hơn timestamp của đồng hồ ứng dụng.

### Reconciliation khi đã cho phép ghi độc lập

Nếu hệ chủ động chấp nhận ghi ở cả hai phía, việc nối mạng lại đòi **merge/conflict resolution**.

Ví dụ:

```text
Nhóm A:  seat A12 = HELD_BY_U1
Nhóm BC: seat A12 = HELD_BY_U2
```

Phải có quyết định nghiệp vụ: ai giữ ghế, ai được thông báo, có hoàn tiền/đền bù không, và có audit hai lời xác nhận hay không. Một merge tự động không thể làm biến mất việc một người đã được hứa quyền sở hữu trái thực tế.

## 12. Network partition khác mất node hoặc quá tải

Ba tình huống có triệu chứng giống nhau từ client nhưng hàm ý khác:

### Node A thực sự chết

A không còn nhận request. B/C có thể failover. Theo định nghĩa availability trong CAP, yêu cầu gửi tới một **node đã chết** không phải cùng kịch bản yêu cầu phục vụ từ node không lỗi nhưng bị cô lập.

### Node A còn sống nhưng không thấy B/C

A có thể nhận request mà không thể đồng bộ trạng thái. Đây là kịch bản CAP điển hình: **mạng chia cắt, hai phía vẫn hoạt động**.

### A và B/C nói chuyện được nhưng chậm

Có thể do queue, GC pause, network delay hoặc quá tải. Tùy hệ, deadline khiến client timeout dù không có partition vĩnh viễn. CAP không cho một công thức tự động quyết định timeout tối ưu; cần xem **SLO latency, retry và cơ chế phát hiện lỗi**.

Trong bài thử cần ghi rõ đang mô phỏng:

- Packet drop 100% theo chiều nào?
- Delay có giới hạn hay không giới hạn?
- Packet loss ngẫu nhiên hay hoàn toàn?
- Node process có vẫn chạy?
- Client có tiếp cận cả hai phía không?
- Link giữa B và C còn hoạt động không?

Không gọi mọi request timeout là “CAP partition” nếu chưa biết nguyên nhân.

## 13. Phân hoạch mạng có thể bất đối xứng

Đời thực không phải lúc nào cũng là hai nhóm đối xứng đẹp:

```text
A -> B: gói đi được
B -> A: gói bị drop
A <-> C: có delay
B <-> C: bình thường
```

Các giao thức có thể yêu cầu **hai chiều giao tiếp** để xác nhận, bầu leader hoặc trao đổi heartbeat. Một node có thể thấy một số message mà không nhận được ACK, khiến việc chẩn đoán phức tạp hơn.

### Đừng rút kết luận từ ping thành công

ICMP ping thành công không chứng minh:

- Kết nối TCP tới cổng database hoạt động.
- TLS handshake/authorization thành công.
- RPC giữa replica truyền được theo cả hai chiều.
- Message đủ nhanh để đáp ứng deadline.
- Hệ đang có leader/quorum hợp lệ.

Quan sát cần kiểm tra **đúng đường RPC phục vụ replication và client**, không chỉ health check của host.

## 14. Quorum là một cơ chế, không phải nhãn nhất quán tự động

Với N=3, majority bằng 2. Nếu một thao tác phải được hai node xác nhận theo giao thức mạnh, nhóm một node không thể commit độc lập.

Nhưng **thấy công thức quorum chưa đủ** để suy ra linearizability.

Các điểm còn cần kiểm tra:

1. **Ghi** có gắn thứ tự/term/version và commit index hợp lệ không?
2. **Đọc** có xác định được trạng thái mới nhất hay chỉ hỏi hai replica bất kỳ?
3. Replica có thể trả **giá trị có timestamp cũ** hay không?
4. Concurrent writes được serialize theo cách nào?
5. Failover có cho phép rollback write đã ACK dưới mode yếu không?
6. Có nhiều datacenter/region với quorum local hay global?
7. Có thao tác riêng biệt trên nhiều partition cần transaction không?

### \(R+W>N\) nói điều gì?

Trong một mô hình quorum replication đơn giản:

\[
R+W>N
\]

giúp bảo đảm tập node tham gia đọc/ghi **giao nhau** khi cả hai là tập con của cùng N replica và đáp ứng những giả định đã nêu.

Nhưng nó không tự trả lời:

- Node giao nhau đã biết write nào là mới nhất?
- Concurrent write được xử lý bằng timestamp/merge hay leader log?
- Read có chờ/sửa dữ liệu ở replica không?
- Số node còn sống có đủ không?
- Giao thức có chống các lịch sử non-linearizable không?

Với Cassandra chẳng hạn, consistency level `QUORUM` là một phần của chính sách đọc/ghi, không phải phép chứng minh mọi bảng và transaction đa partition đều strict serializable.

## 15. Ví dụ MongoDB replica set: xem từng write/read concern

Một replica set MongoDB có thể có primary và secondaries. Khi mạng tách primary cũ khỏi majority, việc ai được phép tiếp tục nhận ghi phụ thuộc cơ chế election, trạng thái primary và write concern.

### Với ghi yêu cầu majority

Ví dụ trong `mongosh`:

```javascript
db.orders.insertOne(
  {
    _id: "ORD-1001",
    tenantId: "T01",
    status: "SUBMITTED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Nếu primary không thể đạt majority, write concern có thể không được thỏa mãn và client nhận timeout/error. Điều đó không có nghĩa network request không bao giờ được gửi tới database, hay thao tác chắc chắn chưa tạo một trạng thái local nào.

### Với ghi `w:1`

Một write được primary xác nhận ở `w:1` có thể không được nhân bản đầy đủ trước khi xảy ra failover. Nếu primary cũ không còn thuộc lịch sử được chọn khi trở lại, những thay đổi chưa đủ điều kiện có thể bị rollback.

**Không suy từ “primary đã ACK” thành “mọi failover không thể mất write”** khi chưa biết write concern và journaling.

### Đọc primary, secondary và concern

Các đường đọc có thể khác nhau:

- Read từ primary với read concern phù hợp.
- Read từ secondary còn trễ theo read preference.
- Read theo `majority`.
- Read với `linearizable` khi deployment/API hỗ trợ và đáp ứng các điều kiện được quy định.

**`readConcern:"majority"` không tự đồng nghĩa `linearizable`**. Một lần đọc từ secondary có thể phản ánh dữ liệu đã đạt một mốc majority nhưng vẫn không phải trạng thái mới nhất theo thời gian thực.

Trong phân tích CAP, cần nêu **đọc/ghi nào nằm trong hợp đồng mạnh**; những read local stale được cho phép không nên bị coi là bằng chứng cùng thao tác đạt linearizability.

### Không gắn nhãn toàn sản phẩm

Một ứng dụng trên MongoDB có thể dùng majority write cho đơn hàng, query search bất đồng bộ qua Elasticsearch cho trang tìm kiếm, và Redis cache cho metadata. Ba đường đọc/ghi có semantics khác nhau dù “database chính là MongoDB”.

## 16. Ví dụ Cassandra: cùng cluster, khác CL là khác lựa chọn

Cassandra có replication factor và consistency levels như `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL`, cùng các cơ chế riêng cho lightweight transactions.

Giả sử RF=3 trên một datacenter, các replica chia:

```text
Partition side A: 1 replica
Partition side BC: 2 replicas
```

### CL=ONE

Một request có thể thành công nếu coordinator còn tiếp cận được một replica phù hợp. Điều này có thể tăng khả năng phục vụ các thao tác local dưới network partition, nhưng các bản sao có thể khác phiên bản; sau đó cần replication/repair và semantics giải quyết concurrent writes.

### CL=QUORUM

Thông thường cần phản hồi từ đa số replica liên quan. Nhóm A chỉ có một replica sẽ không đáp ứng QUORUM; nhóm B/C có hai replica có thể đáp ứng theo điều kiện khác của cluster.

Tuy nhiên **không được viết “Cassandra QUORUM = linearizability”** như một định lý chung: đồng hồ, timestamp conflict resolution, các ghi cạnh tranh, topology và loại thao tác còn quan trọng.

### LWT/conditional write

Nếu ứng dụng cần kiểm tra “chỉ giữ chỗ khi trạng thái đang AVAILABLE”, có thể khảo sát các thao tác **lightweight transaction** với điều kiện `IF` và serial consistency phù hợp trong phạm vi Cassandra hỗ trợ.

Ví dụ CQL khái niệm:

```sql
UPDATE seats
SET reserved_by = 'U1', state = 'HELD'
WHERE event_id = 'SHOW-2026-11-14'
  AND seat_id = 'A12'
IF state = 'AVAILABLE';
```

Schema phải có khóa phù hợp; đây là ví dụ cú pháp để giải thích CAS, không phải bảng hoàn chỉnh. LWT có chi phí điều phối và giới hạn theo partition/transaction semantics của phiên bản. Không xem mọi write Cassandra là LWT chỉ vì hệ hỗ trợ từ khóa `IF`.

### Giới hạn của “availability local”

CL=ONE không có nghĩa mọi request luôn thành công: coordinator có thể không truy cập được replica sở hữu partition cần đọc, node có thể quá tải, hoặc policy vẫn chặn khi điều kiện dữ liệu không đáp ứng. Phải thiết lập **replica placement và client routing**, không chỉ đổi một option.

## 17. Ví dụ Redis: primary, asynchronous replica và failover

Redis thường cho thao tác key-value nhanh trên primary, còn replication có thể bất đồng bộ. Xét:

```text
Primary A nhận SET seat:A12 HELD_BY_U1 -> ACK
Replication sang B chưa hoàn tất
Link A-B đứt
Replica B được nâng vai trò trong một quá trình failover
```

Khi client đọc từ B, có thể chưa thấy ghi của A, tùy sự kiện và cấu hình. Nếu A đã ACK nhưng ghi không còn trong lịch sử sau failover, bài toán liên quan cả **consistency, durability và semantics của failover**.

### `WAIT` không phải “bật CP” cho mọi Redis

Redis có lệnh hỗ trợ chờ replica xác nhận đã xử lý các write trước đó của kết nối client:

```redis
WAIT 1 1000
```

Ứng dụng cần kiểm tra số replica thực sự xác nhận. Lệnh này không tự biến Redis thành một consensus database có global linearizability, và xác nhận replication không đồng nghĩa mọi replica đã fsync bền.

### Read path quyết định kết luận

- `GET` từ primary sau một `SET` trên cùng đường có semantics khác một `GET` từ replica còn trễ.
- Một cluster có nhiều shard không tự có transaction global trên mọi key.
- Một client dùng Redis như cache có thể thấy stale value ngay cả khi nguồn MongoDB đã nhất quán.

Không hỏi “Redis AP hay CP?” mà không nêu **một key, một primary, replica mode, ACK, failover và read route**.

## 18. DynamoDB và các dịch vụ quản lý đa region

DynamoDB là dịch vụ được quản lý, nên người dùng không điều khiển trực tiếp các node replication nội bộ như một cluster tự triển khai.

Khi đánh giá tính nhất quán và khả dụng, cần tách:

- `GetItem`/`Query`/`Scan` trên **base table** với tùy chọn consistency được API hỗ trợ.
- **Local secondary index (LSI)**.
- **Global secondary index (GSI)** vốn có read semantics riêng.
- **Global Tables** và kiểu sao chép/nhất quán liên vùng cụ thể theo phiên bản/tính năng đang dùng.
- **Conditional writes và transaction APIs** cho những bất biến nghiệp vụ.

### Một kịch bản cần phân tích

Ứng dụng ghi vào region A, sau đó người dùng chuyển sang region B vì network failure.

```text
Client -> Region A: write order v8 -> ACK

Mất liên lạc / route sang Region B

Client -> Region B: read order -> v7 ?
```

Không thể kết luận ngay bằng nhãn “DynamoDB strong” hoặc “DynamoDB eventual”. Phải biết **kiểu Global Tables, semantics replication, vùng/đường read, write ACK và read option**. Một đặc tính mạnh trên base table trong một phạm vi không tự mở rộng sang mọi region hay GSI.

Nếu cần giữ ghế độc quyền ở nhiều region, có thể chọn **home region/owner cho mỗi ghế**, chuyển request về nguồn quyết định có thẩm quyền, hoặc dùng cơ chế transaction/coordination phù hợp với mô hình deployment. Nếu chấp nhận multi-writer eventual, cần chính sách xử lý xung đột và không phát ACK giữ chỗ không thể đảo ngược khi chưa có thẩm quyền.

### Dữ liệu read model

Một GSI chưa cập nhật không có nghĩa base table đã mất write. Việc đó liên quan **visibility của index**, và cần đo riêng so với durability/consistency của bảng nguồn.

## 19. Search, cache và dashboard không được kéo toàn sản phẩm về một nhãn

Một hệ có thể kết hợp:

```text
                                 +------------------+
POST reserve ----> Order service | Authoritative DB |
                                 +---------+--------+
                                           |
                                  Event/CDC/Outbox
                                           |
                        +------------------+----------------+
                        |                  |                |
                        v                  v                v
                   Search index         Redis cache     Analytics
                        |                  |                |
                        v                  v                v
                    Search API          GET summary      Dashboard
```

Khi phân hoạch mạng giữa source và read model:

- Nguồn vẫn có thể commit giao dịch đặt chỗ theo policy của nó.
- Search không nhận event, hiển thị trạng thái cũ.
- Cache chưa invalidate, có thể trả v7.
- Dashboard thiếu dữ liệu mới.

Đây là bài toán **độ trễ đồng bộ/read-model convergence**. Nếu mô hình nghiệp vụ cho phép UI tìm kiếm eventual, hệ có thể tiếp tục phục vụ tìm kiếm có cảnh báo, nhưng **không dùng dữ liệu đó để xác nhận ghế còn trống**.

### Biến preview thành quyết định là sai ranh giới

```text
GET /seats/availability-preview -> AVAILABLE (có thể stale)
POST /seats/A12/reserve        -> phải kiểm tra nguồn có thẩm quyền
```

API đầu giúp trải nghiệm; API sau phải bảo vệ bất biến.

Tách **đề xuất** khỏi **cam kết** giúp tiếp tục phục vụ nhiều tính năng dưới partition mà không vi phạm lời hứa độc quyền.

## 20. PACELC: khi mạng không bị chia thì vẫn có đánh đổi

CAP tập trung vào sự căng thẳng khi có partition. Trong trạng thái mạng bình thường, hệ còn phải chọn giữa độ trễ/chi phí điều phối và những mức consistency khác nhau.

Một khung thảo luận thường gặp là **PACELC**:

```text
If Partition (P):  trade off Availability (A) vs Consistency (C)
Else (E):          trade off Latency (L) vs Consistency (C)
```

Ý nghĩa:

- Khi mạng chia cắt, một request ở phía không phối hợp được phải chọn phục vụ với semantics yếu hơn hoặc chờ/từ chối để giữ cam kết mạnh.
- Khi mạng bình thường, vẫn có thể chọn local read nhanh hơn nhưng cũ hơn, hoặc read barrier/quorum/leader read có chi phí điều phối.

**Không coi PACELC là bảng phân loại bất biến cho từng thương hiệu**. Đây là khung phân tích kiến trúc; từng API, topology và workload có thể có điểm đánh đổi khác nhau.

### Một ví dụ

Trang gợi ý sản phẩm đọc replica gần người dùng, p95 thấp, chấp nhận stale 2 giây theo SLO. Endpoint đặt vé gửi tới nguồn quyết định có quyền, chịu thêm RTT để giữ tính đúng. Cả hai lựa chọn có thể cùng nằm trong một ứng dụng.

Không có một tỷ lệ cố định “consistency cao thì chậm gấp N lần”; chỉ có đo đạc trên workload cụ thể.

## 21. Tính sẵn sàng theo CAP khác SLO thực tế

Trong vận hành, ta thường dùng:

\[
\mathrm{AvailabilitySLO} =
\frac{\text{số request hợp lệ được phục vụ thành công}}
{\text{tổng request hợp lệ}}
\]

nhưng phải định nghĩa **success** theo từng API. Nếu `POST reserve` trả HTTP 202 “đã tiếp nhận, chưa xác nhận”, điều đó **không đồng nghĩa đã giữ ghế**. Nó có thể là một API bất đồng bộ có ngữ nghĩa khác và cần cách người dùng tra cứu kết quả cuối.

### Độ trễ và “eventually responds”

Availability trong mô hình CAP chuẩn không tự đặt bound cho phản hồi là 100 ms hay 1 giây. Một operation chờ rất lâu có thể không đáp ứng SLO thương mại, dù phân tích liveness hình thức khác. Khi thiết kế sản phẩm, thêm deadline:

```text
reserveSeat:
  consistency: không xác nhận hai holder
  requestDeadline: 3s (ví dụ sản phẩm)
  onNoQuorum: 503/PENDING không được coi là committed
  retry: same requestId
```

Các số trên là **ví dụ hợp đồng sản phẩm**, không phải mặc định của bất kỳ database nào.

## 22. Cách mô tả một kịch bản lỗi mạng đúng kỹ thuật

Một báo cáo nên ghi:

```yaml
scenario: isolated_former_leader
service: seat-reservation
dataUnit: seatId
topology:
  replicas: 3
  oldLeader: A
  connectedGroups:
    - [A]
    - [B, C]
initialState:
  seatId: A12
  version: 7
  status: AVAILABLE
failure:
  type: bidirectional_message_loss
  link: A_vs_BC
clients:
  - id: U1
    route: A
    operation: reserve
  - id: U2
    route: BC
    operation: reserve
requiredInvariant:
  - no_double_confirmed_reservation
observationFields:
  - requestId
  - invokeTime
  - completeTime
  - ackResult
  - servingNode
  - returnedVersion
  - leaderTerm
  - commitIndex
  - quorumStatus
  - retryStatus
```

Đây là **schema ghi chép thí nghiệm giả định**, không phải file cấu hình của một sản phẩm cụ thể. Tên `leaderTerm` và `commitIndex` có thể không tồn tại trong API ứng dụng; nếu engine có thông tin tương đương, lấy từ telemetry phù hợp.

### Điều quan trọng cần bổ sung

1. **Phiên bản database/SDK và topology thực tế.**
2. **Read/write concern hoặc consistency level từng operation.**
3. **Bản sao nào nhận được write, ACK ở đâu và khi nào.**
4. **Partition được tạo ở tầng nào và kéo dài bao lâu.**
5. **Client có retry tự động hoặc failover routing không.**
6. **Có thao tác nền/write thứ ba không.**
7. **Điều gì xảy ra sau khi nối mạng trở lại.**

Nếu thiếu thông tin ấy, câu “hệ vẫn chạy khi partition” quá mơ hồ để kết luận C hay A.

## 23. Thí nghiệm an toàn: dựng partition trong môi trường lab

**Chỉ thử trên môi trường cô lập với dữ liệu giả và có kế hoạch khôi phục**. Không tự ngắt mạng production, không phá kết nối của hệ đang phục vụ người dùng.

Một kế hoạch:

### Bước 1 — Khởi tạo trạng thái có thể kiểm tra

```text
seatId = "LAB-A12"
status = AVAILABLE
version = 7
runId = "partition-test-001"
```

Đọc từ nguồn xác nhận rằng mọi replica/đường đọc cần thiết đã bắt kịp v7, hoặc ít nhất biết trạng thái xuất phát của mỗi node.

### Bước 2 — Ghi baseline

Trước khi gây lỗi:

- Một client reserve thành công.
- Client khác không thể reserve cùng ghế.
- Log request ID, version, ACK, latency, route.
- Đo read-after-write theo đúng đường đọc cần test.

Nếu baseline đã sai, đừng quy lỗi tiếp theo cho partition.

### Bước 3 — Tạo fault chính xác

Chặn RPC giữa A và B/C, giữ kết nối B↔C hoạt động, giữ client U1 tới A và U2 tới B/C.

```text
FAULT ON:
  drop messages A <-> B
  drop messages A <-> C
  allow B <-> C
  allow clients U1->A, U2->BC
```

Đây là **pseudocode fault injection**, không phải lệnh firewall có thể paste. Phải dùng cơ chế được môi trường lab hỗ trợ và xác minh fault đã áp dụng đúng; packet loss một chiều có thể có kết quả khác hai chiều.

### Bước 4 — Thử từng operation

1. U1 reserve A12 ở A.
2. U2 reserve A12 ở B/C.
3. Đọc trạng thái từ A, B, C sau khi biết một write đã ACK.
4. Thử read-only catalog endpoint.
5. Thử timeout trước ACK, retry cùng request ID.
6. Quan sát leader election và trạng thái quorum.

Lưu lịch sử **invoke/complete** cho từng thao tác, không chỉ số kết quả cuối.

### Bước 5 — Khôi phục kết nối

```text
FAULT OFF
allow A <-> B
allow A <-> C
```

Chờ giao thức bắt kịp theo policy, rồi xác minh:

- Chỉ một holder được commit chính thức.
- Nếu có write local chưa commit, nó được xử lý theo đúng hợp đồng.
- Client đã nhận ACK commit mạnh không bị mất quyền vô cớ.
- Mọi replica cuối cùng hội tụ theo cơ chế đã công bố.
- Projection/cache được sửa hoặc rebuild nếu cần.
- Không có double charge do retry.

### Bước 6 — Báo cáo riêng cho read và write

Không viết “test pass CP”. Viết:

> Trong partition A|BC với majority=2, các lệnh reserve gửi tới A bị từ chối hoặc timeout; lệnh tại B/C có thể commit sau khi election ổn định; local read tại A có thể trả v7 theo chế độ stale, nhưng strong read không được trả v7 sau v8 commit.

Kết luận này **mô tả kịch bản và chính sách**, và phải được thay bằng kết quả thực tế khi đã chạy test.

## 24. Thu thập history để kiểm tra linearizability

Một record tối thiểu:

```json
{
  "operationId": "op-101",
  "clientId": "U1",
  "kind": "RESERVE",
  "seatId": "LAB-A12",
  "requestId": "R1",
  "invokedAt": "2026-11-14T09:00:00.100Z",
  "completedAt": "2026-11-14T09:00:00.450Z",
  "result": "COMMITTED",
  "holder": "U1",
  "version": 8,
  "route": "A"
}
```

Những lần read cũng phải ghi `kind=READ`, `result`, version và thời điểm bắt đầu/kết thúc.

### Kiểm tra nguyên lý

Với một register:

- Nếu write A **hoàn tất trước** read B bắt đầu, và không có write cạnh tranh hợp lệ thay đổi giá trị, B không được trả giá trị cũ dưới linearizability.
- Nếu hai thao tác chồng lấn, có thể có nhiều vị trí linearization hợp lệ.
- Nếu write timeout, cần xử lý **pending operation** cẩn thận: không mặc định chưa commit.

Với reserve có điều kiện:

- Không thể có hai operation độc lập cùng trả `COMMITTED` trên cùng seat khi invariant là một người giữ và không có release/expiry hợp lệ ở giữa.
- Một lần `REJECTED_ALREADY_HELD` hợp lệ nếu trạng thái đã bị giữ trước đó theo thứ tự có thể tuyến tính hóa.
- Nếu có `RELEASE` hoặc TTL hết hạn, phải đưa những operation đó vào history; nếu không, phản ví dụ có thể là giả.

### Không dùng timestamp từ hai máy lệch đồng hồ làm bằng chứng duy nhất

Để xác nhận non-overlap giữa hai client, một **controller** có thể chờ response của write A rồi mới phát read B. Quan hệ nhân quả đó rõ hơn việc lấy hai timestamp máy khác nhau rồi so khi chưa biết clock skew.

Một checker kiểu linearizability có thể tìm một thứ tự tuần tự giữ real-time constraints và semantics của đối tượng. Kết quả **một history không vi phạm** không chứng minh tất cả lịch sử đều đúng.

## 25. Một test harness Java dạng mô phỏng

Phần sau minh họa cách kiểm tra **bất biến một ghế chỉ có một holder**, tách backend adapter khỏi logic thu thập kết quả. Đây là **khung test**, không phải code hoàn chỉnh cho một driver NoSQL.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

interface SeatStore {
    // Trả COMMITTED, CONFLICT, UNAVAILABLE hoặc UNKNOWN.
    // Không trả COMMITTED nếu chưa đạt cam kết nghiệp vụ.
    String reserve(
        String seatId, String holderId, String requestId
    ) throws Exception;
}

record Attempt(
    String clientId,
    String seatId,
    String result,
    long startedAtNanos,
    long finishedAtNanos
) {}

public final class PartitionScenarioDemo {
    public static List<Attempt> raceForSeat(
        SeatStore sideA, SeatStore sideBC
    ) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<Attempt> a = pool.submit(() -> {
                start.await();
                long begin = System.nanoTime();
                String result;
                try {
                    result = sideA.reserve("LAB-A12", "U1", "R1");
                } catch (Exception error) {
                    result = "UNKNOWN";
                }
                return new Attempt(
                    "U1", "LAB-A12", result,
                    begin, System.nanoTime()
                );
            });

            Future<Attempt> b = pool.submit(() -> {
                start.await();
                long begin = System.nanoTime();
                String result;
                try {
                    result = sideBC.reserve("LAB-A12", "U2", "R2");
                } catch (Exception error) {
                    result = "UNKNOWN";
                }
                return new Attempt(
                    "U2", "LAB-A12", result,
                    begin, System.nanoTime()
                );
            });

            start.countDown();
            List<Attempt> attempts = new ArrayList<>();
            attempts.add(a.get());
            attempts.add(b.get());
            return attempts;
        } finally {
            pool.shutdown();
        }
    }
}
```

### Diễn giải ví dụ đúng cách

- `SeatStore` là interface minh họa; implementation phải route một client tới A, client kia tới B/C và dùng **cùng logic nghiệp vụ reserve có điều kiện**.
- Không có lệnh cắt mạng trong code. Fault injection diễn ra ở môi trường lab bên ngoài.
- `UNKNOWN` là trạng thái cần tra cứu lại bằng `requestId`; **không coi như chắc chắn thất bại**.
- `System.nanoTime()` thích hợp đo khoảng thời gian trong một JVM, không phải wall-clock để so nhiều máy.
- Test đua hai request là hữu ích, nhưng để **chứng minh vi phạm linearizability** cần ghi đầy đủ lịch sử commit, release/expiry, read và quan hệ non-overlap khi liên quan.
- Nếu cả hai trả `COMMITTED` và invariant không cho phép, phải điều tra tính đúng của adapter, policy ACK và những thay đổi ẩn; không đơn giản kết luận “CAP bị phá vỡ”.

Một test production-like còn cần log độc lập, timeout, retry policy, số vòng lặp, network diagnostics và các điều kiện lỗi.

## 26. Thiết kế bất biến cho nghiệp vụ: không phải tất cả ghế đều cần một global lock

Một số nhóm có thể thử “giải CAP” bằng cách tạo **một lock toàn cục cho mọi ghế**. Điều này có thể giảm throughput hoặc tạo điểm nghẽn không cần thiết.

### Dùng ownership theo đơn vị nghiệp vụ

Nếu mỗi ghế thuộc một suất diễn xác định, có thể:

- Gán một **home shard/owner** cho từng `(showId, seatId)`.
- Dùng conditional write/transaction tại owner để đảm bảo chỉ một reservation commit.
- Chuyển request đến owner hoặc majority tương ứng.
- Khi owner không truy cập được, **không xác nhận giữ ghế**; vẫn cho phép đọc catalog/cache.

Quy mô bất biến nằm ở **một ghế/aggregate**, không nhất thiết toàn bộ sản phẩm phải dùng một consensus group duy nhất.

### Escrow cho tài nguyên chia được

Với số lượng hàng hóa có thể chia, ví dụ 100 voucher:

```text
Tổng 100
Side A được cấp trước quota 30
Side BC được cấp trước quota 70
```

Trong partition, mỗi bên có thể cấp voucher **trong quota đã được phân bổ bền và độc quyền** mà không cần liên lạc mỗi lần. Đây là mô hình phân quyền trước (escrow), không phải trường hợp hai bên cùng lấy từ cùng một kho quota chưa phân chia.

Với **một chiếc ghế độc nhất**, không thể chia quyền giữ thành hai phần cùng hợp lệ. Chọn mô hình phù hợp với **phép toán và invariant**.

## 27. Đối chiếu C/A với read-your-writes và trải nghiệm người dùng

Client A vừa nộp đơn và nhận ACK, sau đó vào trang lịch sử đơn ở một region khác:

```text
POST /orders -> COMMITTED v8 ở source
GET /orders -> read model v7
```

Nếu trang lịch sử dùng read model eventual, đây có thể là behavior theo thiết kế. Nhưng trải nghiệm người dùng vẫn khó hiểu.

Một số biện pháp:

- Trả `orderId` và `version` trong ACK.
- Đọc source có thẩm quyền ngay sau thao tác ghi, hoặc dùng session token/watermark để chờ read model bắt kịp.
- Hiển thị trạng thái “đang đồng bộ” thay vì nói “đơn không tồn tại”.
- Dùng polling với giới hạn thời gian, sau đó fallback nguồn.
- Chặn quyết định tài chính/giữ ghế dựa trên projection trễ.

### Không coi “eventual” là giấy phép hiển thị sai vô hạn

Ứng dụng vẫn cần **SLO hội tụ** và quan sát backlog:

```text
projectionLagSeconds
outboxOldestPendingAge
replicaAppliedVersion
reconciliationMismatchCount
timeoutRate
```

Không có một bound tự động từ chữ eventual; thời gian có thể tăng do connector lỗi, network partition kéo dài hoặc event bị mất.

## 28. Quan sát gì để kết luận đúng kịch bản?

| Nhóm telemetry | Tín hiệu | Câu hỏi |
|---|---|---|
| **Topology** | Leader/primary, term/epoch, replica membership | Bên nào có thẩm quyền? |
| **Network** | Partition direction, packet loss, RPC timeout, RTT | Ai liên lạc được với ai? |
| **Quorum** | Thành viên phản hồi, commit index, CL success/failure | Write có đạt điều kiện commit không? |
| **Client** | Invoke/complete, ACK type, requestId, retry | User được hứa điều gì? |
| **Read path** | Serving node, region, primary/replica/cache | Read đang quan sát nguồn nào? |
| **Version** | Aggregate version, log position, timestamp có nguồn gốc | Đang thấy bản cũ hay bản đã commit mới? |
| **Failover** | Election, rollback, rejoin, replica lag | Có mất/đảo trạng thái đã ACK không? |
| **Consistency** | Histories và counterexample | Có tuyến tính hóa được không? |
| **Availability** | Successful operations / valid requests theo API | Tính năng nào còn phục vụ được? |
| **Durability** | Journal, sync, rollback, restore result | Write ACK có sống qua crash không? |
| **Recovery** | Reconciliation, conflicts, compensation | Sau nối mạng cần sửa gì? |

Không đưa raw token, dữ liệu thanh toán nhạy cảm hoặc định danh cá nhân vào log thử nghiệm. Dùng ID giả và quyền truy cập phù hợp. Một metric “requests_successful” không tự định nghĩa thế nào là **thành công nghiệp vụ**.

## 29. Khi không còn partition, điều gì vẫn phải kiểm tra?

Sau khi network hồi phục, cần xác minh **cả hệ thống nguồn và các projection**:

1. **Leader/authority**: chỉ còn nhóm được phép ghi theo giao thức; không có leader cũ tiếp tục ACK xung đột.
2. **Committed history**: các write đã được xác nhận theo mức mạnh vẫn còn theo hợp đồng.
3. **Tentative writes**: local writes chưa commit bị loại/hòa giải đúng quy tắc.
4. **Read behavior**: read strong không trả trạng thái cũ sau commit hợp lệ đã hoàn tất.
5. **Replica convergence**: follower bắt kịp đúng version hoặc log position.
6. **Client retries**: requestId không sinh reservation/charge trùng.
7. **Search/cache**: read model được đồng bộ, version không ghi lùi.
8. **Audit và compensation**: nếu một phía đã cấp ACK yếu gây xung đột, có quy trình xử lý người dùng.
9. **SLO**: thời gian failover, error rate, độ trễ recovery và data loss được đo.

**Recovery không chỉ là “ba node đều xanh”.** Các bất biến nghiệp vụ và những lời hứa đã trả cho client mới quyết định hệ đã thực sự khôi phục đúng.

## 30. Quy trình đưa ra quyết định dựa trên kịch bản

Một quy trình có thể áp dụng cho hệ mới:

### Bước 1 — Nêu bất biến nghiệp vụ

Ví dụ: một ghế chỉ có một holder đã xác nhận, không double charge, hoặc comment có thể hiển thị trễ.

### Bước 2 — Chọn đơn vị dữ liệu

Một item, một document, một partition, một transaction nhiều record hay một workflow xuyên hệ? Đừng tự ngoại suy từ single-key sang multi-key.

### Bước 3 — Vẽ topology và đường request

Primary, replicas, datacenter/AZ/region, client route, search, cache, broker. Nêu failure domains và quyền phục vụ read/write.

### Bước 4 — Mô tả partition cụ thể

Nhóm A một node, nhóm B hai node? Đứt hai chiều hay một chiều? Client ở đâu? Những request nào chồng lấn?

### Bước 5 — Chốt hợp đồng API

Ví dụ `reserve` yêu cầu strong decision; `preview` cho phép stale với TTL; `history` yêu cầu read-your-writes.

### Bước 6 — Xác định cách hệ phản hồi

Trả committed, conflict, unavailable, pending hay stale? Mỗi response có nghĩa gì? ACK dựa trên majority hay local?

### Bước 7 — Thiết kế retry và hòa giải

Idempotency, expectedVersion, lease fencing, conflict policy, compensation và source of truth.

### Bước 8 — Thử nghiệm và đo

History có invoke/complete, fault injection, tracer, client route, metrics; đánh giá cùng với docs đúng phiên bản.

### Bước 9 — Xác minh sau nối mạng

Quorum/leader, dữ liệu đã ACK, reconciliation, cache/index và hoạt động business.

### Bước 10 — Viết kết luận có điều kiện

Không viết “chúng tôi đã chứng minh hệ này CP”. Hãy viết rõ **cấu hình, partition, operation và kết quả quan sát**.

## 31. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Cách phân tích đúng |
|---|---|---|
| “Mọi database phải chọn 2 trong 3” | Đánh đổi CAP trọng tâm là khi mạng bị chia | Mô tả partition và operation |
| “CP có nghĩa toàn hệ luôn offline khi mất một node” | Majority còn có thể phục vụ | Xét nhóm nào đủ quorum |
| “AP có nghĩa luôn bảo toàn mọi write được ACK” | Có thể cần merge/rollback/compensation | Xem ACK, replication, conflict |
| “A nghĩa server trả HTTP 503 cũng được” | Thao tác không hoàn tất thành công | Phân biệt transport và functional availability |
| “C là ACID consistency” | CAP C thường là linearizability | Nêu mô hình formal |
| “Một node chết giống partition 1|2” | Node chết không nhận request, partition có thể cả hai nhóm sống | Ghi đúng fault model |
| “Majority có nghĩa linearizable cho mọi API” | Reads, concurrent writes và topology vẫn quan trọng | Kiểm tra protocol/read path |
| “Cassandra QUORUM chắc chắn global serializable” | CL/quorum không tạo transaction toàn hệ | Xác minh LWT/partition/transaction |
| “Redis primary ACK chắc chắn sống qua failover” | Async replication có cửa sổ mất write | Kiểm tra persistence và failover |
| “GSI trễ nghĩa nguồn không nhất quán” | Index là đường đọc có semantics riêng | Tách source và projection |
| “Cache cũ cũng là bằng chứng database eventual” | Cache có TTL/invalidation độc lập | Trace end-to-end |
| “Last-write-wins bảo vệ độc quyền giữ ghế” | Có thể đã xác nhận hai người | Chọn authoritative CAS/escrow |
| “CRDT giải quyết mọi business invariant” | Merge có ranh giới theo phép toán | Phân tích invariant và escrow |
| “Network partition chỉ cần thử ping” | RPC có thể một chiều, delay hoặc bị ACL chặn | Fault injection đúng đường |
| “Timeout nghĩa write không commit” | ACK có thể mất sau commit | Idempotency và xác minh |
| “Mạng hồi phục là dữ liệu tự động đúng nghiệp vụ” | Có thể còn conflict/đơn trùng | Reconcile và audit |
| “Chỉ cần đọc docs CP/AP là đủ” | Mỗi option/API có semantics khác | Test theo phiên bản/topology |
| “Không quan sát lỗi trong 100 lần = chứng minh CAP” | Test không bao phủ mọi lịch sử | Kết luận đúng phạm vi thử |

## 32. Bài tập thực hành

### Bài 1 — Phân tích partition 1|2

Có ba node A, B, C; A là leader, B/C là follower. Mạng tách A khỏi B/C. Hệ cần majority 2/3 để xác nhận ghi. Client U1 gửi write tới A, U2 gửi write tới B/C. Hãy liệt kê những phản hồi hợp lệ nếu hệ bảo vệ một thứ tự commit mạnh.

### Bài 2 — Phát hiện stale strong read

Nhóm B/C commit `x=8` và ACK. Sau đó một read bắt đầu tại A và nhận `x=7`. Nếu read này có hợp đồng linearizable, đây có phải vi phạm không? Nếu API chỉ hứa “local cached read”, kết luận thay đổi thế nào?

### Bài 3 — Vi phạm độc quyền khi nhận ghi local

Hai nhóm đang partition cùng xác nhận giữ ghế A12 cho hai user khác nhau. Khi kết nối phục hồi, last-write-wins giữ lại một người. Có thể gọi hai ACK trước đó là linearizable không? Điều gì phải xử lý với người bị mất quyền?

### Bài 4 — Availability nghĩa là gì?

Một API reserve trả HTTP 503 khi thiếu quorum nhưng health check vẫn HTTP 200. Hệ còn sẵn sàng theo nghĩa nào? Vì sao không được dùng `healthCheckUp=true` để kết luận reserve đã đạt availability theo CAP?

### Bài 5 — ACK mơ hồ

U1 gửi reserve với `requestId=R1`. Database commit nhưng response mất. U1 timeout và retry bằng `R2`. Có thể xảy ra lỗi gì? Thiết kế cách retry an toàn và endpoint xác minh kết quả.

### Bài 6 — Quorum không là phép màu

RF=3, read consistency QUORUM và write consistency QUORUM. Giải thích ý nghĩa của \(R+W>N\) và nêu ít nhất ba lý do phép bất đẳng thức này chưa chứng minh global linearizability/serializability.

### Bài 7 — Cassandra hai chế độ

Trong partition 1|2, so sánh hướng hành vi khi CL=ONE và CL=QUORUM. Nếu API giữ ghế cần tránh xác nhận trùng, có đủ khi dùng `ONE` không? Khi nào cần LWT/conditional write?

### Bài 8 — MongoDB majority và rollback

Primary A ACK write ở `w:1` rồi mất liên lạc trước replication; B/C bầu leader mới. Dữ liệu A có thể bị xử lý thế nào khi rejoin? Nếu client yêu cầu majority write và strong read, phải kiểm tra cấu hình nào?

### Bài 9 — Redis và replica

Redis primary ACK SET, replica chưa nhận và được nâng vai trò sau failover. Điều gì có thể xảy ra với GET trên replica mới? Vì sao `WAIT` không tự chứng minh mọi write đều đã fsync bền trên nhiều node?

### Bài 10 — Source vs search

Order source có v8, search index có v7 vì mạng giữa CDC và search đang partition. Có nên coi đây là bằng chứng source vi phạm CAP C không? Hãy thiết kế API hiển thị trạng thái “đang cập nhật” và đường xác nhận đơn dựa vào nguồn.

### Bài 11 — PACELC và SLO

Một ứng dụng đọc replica gần người dùng để hiển thị catalog nhanh nhưng gửi lệnh giữ vé về region có thẩm quyền. Hãy phân tích đánh đổi khi có partition và khi mạng bình thường. Nêu các SLO cần đo mà CAP không tự quy định.

### Bài 12 — Thiết kế fault injection

Thiết kế một kịch bản lab:

- Ba replica A/B/C.
- Partition A|BC trong 30 giây.
- Hai client có thể tiếp cận mỗi phía.
- Ghi history invoke/complete, result, route, version.
- Khôi phục mạng và đối soát.

Hãy nêu các bước cần làm, những tín hiệu cần lưu và cách tránh ảnh hưởng hệ production.

### Bài 13 — Reconciliation

Một hệ multi-writer đã ACK hai thay đổi `seat=HELD_BY_U1` và `seat=HELD_BY_U2`. Sau merge giữ U2. Hãy đề xuất chính sách bù trừ, audit, thông báo, refund và cách thay đổi quy trình để không tái diễn double confirmation.

### Bài 14 — Khi nào dùng escrow?

So sánh bài toán giữ **một ghế duy nhất** với cấp **100 voucher có thể phân bổ quota**. Bài toán nào có thể cấp quyền trước theo từng vùng để tiếp tục hoạt động khi partition? Những điều kiện cần giữ để không vượt 100?

### Bài 15 — Viết báo cáo có phạm vi

Hãy viết một kết luận trong 5–7 câu cho trường hợp:

```text
Topology: 3 replicas, majority=2
Fault: A isolated from B/C
Operation 1: reserve(A12) on A -> UNAVAILABLE
Operation 2: reserve(A12) on B/C -> COMMITTED
Operation 3: catalog read on A -> cached 10s-old data
Recovery: replicas converge after rejoin
```

Không dùng nhãn “toàn sản phẩm là CP” hay “toàn sản phẩm là AP”; nêu rõ cách hệ bảo vệ bất biến và phần nào chấp nhận stale.

## 33. Checklist dùng trong thiết kế và review sự cố

1. **Đã xác định business invariant chưa?** Giữ độc quyền, đếm có giới hạn hay dữ liệu có thể merge?
2. **Đã chọn đơn vị bảo đảm chưa?** Key, document, partition, transaction hay workflow?
3. **Topology đã vẽ đủ chưa?** Node, replica, leader, AZ/region và client route?
4. **Fault đã mô tả chính xác chưa?** Một chiều/hai chiều, packet loss, delay, node còn sống?
5. **Read/write mode và ACK có được ghi rõ chưa?** Majority, local, journal, conditional write?
6. **Đã tách từng API chưa?** Reserve, strong read, preview, cache, analytics?
7. **Đã xác định phản hồi khi thiếu quorum chưa?** Unavailable, timeout, pending hay stale có chú thích?
8. **Đã bảo vệ request timeout/duplicate chưa?** Request ID ổn định và idempotency?
9. **Có test history không?** Invoke/complete, concurrent operations, non-overlap, version?
10. **Có thử failover và leader cũ không?** Không ACK xung đột sau re-election?
11. **Có biết post-partition reconciliation không?** Conflict, tombstone, outbox, cache và index?
12. **Có tách consistency khỏi durability và availability SLO không?**
13. **Có đo latency và khả năng phục vụ theo thao tác không?**
14. **Có trích đúng tài liệu theo phiên bản/API/topology không?**
15. **Kết luận có giới hạn đúng phạm vi đã thử không?**

## 34. Tổng kết

Để hiểu CAP trong NoSQL, **một sơ đồ phân hoạch mạng và lịch sử request cụ thể** thường hữu ích hơn mọi bảng gắn nhãn “CP database” hoặc “AP database”.

Với ba node A/B/C bị chia `A | BC`:

- Một thao tác **giữ ghế độc quyền** cần quyền commit đáng tin có thể bị từ chối ở A khi thiếu quorum, còn nhóm B/C có thể tiếp tục sau khi đạt điều kiện election/commit.
- Một thao tác **đọc local** ở A có thể vẫn trả dữ liệu cũ nếu hợp đồng cho phép, nhưng không được giả làm strong read sau một write mới đã commit ở B/C.
- Nếu cả hai phía **cùng xác nhận write độc lập** trong partition, hệ có thể tăng khả năng tiếp nhận request nhưng phải giải quyết xung đột; merge cuối cùng không tự sửa những lời hứa nghiệp vụ đã trả sai.
- **Read path, write concern, consistency level, session, failover và topology** quyết định hành vi của từng thao tác, không phải nhãn tên sản phẩm.
- **CAP không thay thế** phân tích durability, transaction isolation, PACELC, latency SLO, idempotency hay recovery.

Thay vì hỏi “database này CP hay AP?”, hãy hỏi:

> “Trong partition cụ thể này, **client nào gọi thao tác nào tới nhóm node nào**, thao tác được phép trả **ACK gì**, kết quả đọc được phép **cũ đến đâu**, và **bất biến nghiệp vụ nào vẫn phải đúng** sau khi mạng nối lại?”

Khi trả lời được những câu hỏi đó và kiểm chứng bằng **history, fault injection và tài liệu của đúng API**, ta mới có căn cứ để thiết kế hệ NoSQL vừa **đúng nghiệp vụ**, vừa **đủ khả dụng** trong các lỗi mạng thực tế.
