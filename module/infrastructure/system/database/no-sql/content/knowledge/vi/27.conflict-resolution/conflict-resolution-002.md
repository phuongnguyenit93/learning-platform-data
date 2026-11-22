# Last-write-wins và vai trò timestamp trong từng thiết kế

## 1. Đặt vấn đề: “ghi sau cùng” thực sự có nghĩa gì?

Trong chương **Xung đột và đồng bộ** của Database NoSQL, một trong những chính sách giải quyết xung đột thường gặp nhất là **Last-write-wins (LWW)**: khi nhiều bản ghi hoặc mutation cạnh tranh trên cùng một dữ liệu, hệ thống dùng một quy tắc thứ tự để giữ lại bản được xem là **mới nhất**.

Nghe có vẻ đơn giản: người nào cập nhật cuối cùng thì người đó thắng. Nhưng trong hệ phân tán, câu hỏi **“cuối cùng theo đồng hồ nào và trong phạm vi nào?”** không có câu trả lời mặc định.

Giả sử hồ sơ người dùng được đồng bộ giữa hai vùng:

```text
                        User U42
                           |
              +------------+------------+
              |                         |
              v                         v
          Region A                   Region B
         profile.city               profile.city
          = "Hà Nội"                 = "Đà Nẵng"
              |                         |
              +---- mạng gián đoạn -----+
```

Hai thay đổi diễn ra trong lúc hai vùng không liên lạc được. Khi kết nối phục hồi, mỗi vùng thấy một giá trị khác nhau. Nếu hệ chọn một giá trị theo timestamp rồi đồng bộ giá trị thắng sang bên còn lại, nó đang áp dụng một biến thể của LWW.

**LWW giải quyết việc hội tụ dữ liệu, không tự chứng minh lựa chọn cuối cùng đúng với ý định của người dùng.** Một giá trị hợp lệ vẫn có thể bị mất; một thay đổi vừa được thực hiện theo thời gian thực vẫn có thể thua vì clock skew.

Bài viết sẽ làm rõ:

- LWW register, LWW theo field/cell, document và event.
- Timestamp vật lý, logical clock, Hybrid Logical Clock (HLC) và version.
- Điểm khác nhau giữa event time, processing time, ingest time và commit order.
- Quy tắc tie-break, timestamp bằng nhau và deterministic merge.
- Cassandra, DynamoDB global tables, Cosmos DB, MongoDB, Firestore, Redis cùng phạm vi bảo đảm khác nhau.
- Delete, tombstone, TTL, replay, repair và nguy cơ dữ liệu hồi sinh.
- Khi nào LWW phù hợp; khi nào phải dùng CAS, transaction, version vector, CRDT hoặc business conflict resolution.
- Thiết kế API, kiểm thử mạng phân hoạch, quan sát hệ thống và bài tập thực hành.

## 2. Mô hình tối giản của LWW

Một LWW register có thể lưu một giá trị cùng metadata thứ tự:

```json
{
  "key": "profile:U42:city",
  "value": "Hà Nội",
  "timestamp": 1700000000100,
  "writerId": "region-a"
}
```

Khi nhận mutation thứ hai:

```json
{
  "key": "profile:U42:city",
  "value": "Đà Nẵng",
  "timestamp": 1700000000200,
  "writerId": "region-b"
}
```

Theo chính sách **timestamp lớn hơn thắng**, hệ chọn giá trị của Region B.

Giả mã:

```text
merge(a, b):
    if a.timestamp > b.timestamp:
        return a
    if b.timestamp > a.timestamp:
        return b
    return deterministicTieBreak(a, b)
```

Điểm cuối rất quan trọng: khi timestamp bằng nhau, **mọi replica phải dùng cùng một luật** để không chọn hai kết quả khác nhau.

### 2.1. Bản ghi thắng không nhất thiết là mutation đến sau

Một message timestamp 200 có thể đến trước message timestamp 100. Nếu hệ chọn max timestamp, 200 vẫn thắng:

```text
Receive order:  mutation t=200 -> mutation t=100
Winner:         mutation t=200
```

### 2.2. Không có một định nghĩa LWW chung cho mọi NoSQL

Tùy sản phẩm và mô hình:

- LWW trên **toàn document**.
- LWW trên **từng field/cell**.
- LWW trên **một register** của CRDT.
- LWW trên **các thành phần của một set**.
- Chọn winner theo **commit sequence của authority** thay vì wall-clock.
- Conflict resolution theo **property** được cấu hình.
- LWW chỉ dùng trong **multi-region concurrent writes**, không phải trong regular single-primary replication.

Vì vậy, câu “database này dùng LWW” luôn cần thêm **scope, timestamp source và conflict policy**.

## 3. LWW không phải “dùng đồng hồ để biết sự thật”

Một timestamp trong database thường là một **nhãn để sắp thứ tự**. Nó không chắc là thời gian thực tế mà hành động xảy ra.

Ví dụ:

```text
Thời gian thực:

12:00:00  User X cập nhật city="Huế" tại A
12:00:05  User Y cập nhật city="Đà Nẵng" tại B
```

Nhưng đồng hồ hai máy lệch:

```text
Node A nhanh hơn thực tế 20 giây:
  X ghi timestamp 12:00:20

Node B đúng giờ:
  Y ghi timestamp 12:00:05
```

Nếu chọn timestamp lớn nhất, mutation của X **thắng**, dù Y thao tác **sau** theo thời gian thực.

**LWW theo physical clock không tự bảo đảm real-time last writer wins.**

### 3.1. “Last” có thể được định nghĩa bằng nhiều trục

| Định nghĩa “sau cùng” | Nguồn thứ tự | Điều cần lưu ý |
|---|---|---|
| Client event time | Đồng hồ thiết bị gửi | Clock skew, offline, giả mạo thời gian |
| Server receive time | Đồng hồ máy nhận | Message đến muộn, region clock skew |
| Ingest sequence | Offset/sequence ở ingestion authority | Chỉ có thứ tự trong phạm vi ingestion |
| Commit index | Log/transaction commit order | Phụ thuộc authority và transaction scope |
| Logical timestamp | Bộ đếm gắn quan hệ sự kiện | Không tự đo thời gian thực |
| Hybrid logical timestamp | Physical + logical component | Cần protocol HLC và giả định phù hợp |
| Application version | CAS/generation tăng đơn điệu | Bảo vệ thứ tự theo entity; có thể cần authority |

Một hệ chọn **event time lớn nhất** có thể muốn ưu tiên thao tác “được người dùng thực hiện sau” ngay cả khi event tới muộn. Một hệ chọn **commit order** muốn ưu tiên thao tác được authority chấp nhận sau. Hai chính sách khác nhau có thể cho winner khác nhau.

## 4. Tách event time, processing time, ingest time và commit time

Giả sử thiết bị ngoại tuyến ghi một sự kiện lúc 08:00 và gửi lên server lúc 12:00:

```text
08:00  Người dùng thực hiện thay đổi trên thiết bị
12:00  Thiết bị có mạng trở lại
12:01  Ingestion service nhận event
12:02  Database commit event
```

Có ít nhất bốn mốc:

- **Event time:** 08:00, theo nguồn phát sự kiện.
- **Processing time:** thời điểm một consumer/processor xử lý event.
- **Ingest time:** lúc hệ tiếp nhận event.
- **Commit time:** lúc mutation được xác nhận ở database authority.

Nếu một update khác đã commit lúc 10:00, dùng ingest time có thể khiến update từ 08:00 thắng chỉ vì đến sau 12:01.

### 4.1. Một ví dụ cụ thể

```text
Event E1: city="Huế"
  eventTime=08:00
  ingestTime=12:01

Event E2: city="Đà Nẵng"
  eventTime=10:00
  ingestTime=10:01
```

- LWW theo **eventTime** chọn Đà Nẵng.
- LWW theo **ingestTime** chọn Huế.

Không thể nói một kết quả “đúng” mà chưa biết hợp đồng nghiệp vụ.

### 4.2. Event time từ client có đáng tin không?

Thiết bị có thể:

- Chỉnh giờ thủ công.
- Sai múi giờ hoặc clock drift.
- Mất đồng bộ NTP.
- Lưu event với timestamp tương lai.
- Gửi lại event cũ kèm timestamp mới.
- Cố ý làm sai thời gian để ghi đè dữ liệu.

Nếu dữ liệu cần chống gian lận hoặc bảo vệ quyền, **không tin tuyệt đối timestamp tự khai của client**.

### 4.3. Commit time không tự là thứ tự toàn cầu

Hai database partitions hoặc hai independent leaders có thể có commit clocks/sequence riêng. Không được lấy offset 100 từ partition A so với offset 200 từ partition B rồi tuyên bố cái sau xảy ra muộn hơn theo toàn hệ.

## 5. Timestamp vật lý và clock skew

Physical timestamp thường được lấy từ đồng hồ hệ thống:

```java
long nowMillis = System.currentTimeMillis();
```

hoặc:

```java
java.time.Instant timestamp = java.time.Instant.now();
```

Chúng hữu ích cho audit và hiển thị thời gian, nhưng không tự bảo đảm tính tăng đơn điệu hoặc thứ tự nhân quả.

### 5.1. Clock drift

Hai máy có đồng hồ không hoàn toàn trùng nhau, kể cả khi cùng đồng bộ NTP. Độ lệch có thể thay đổi theo thời gian và môi trường.

### 5.2. Clock step

Một máy có thể điều chỉnh đồng hồ tiến/lùi. Nếu ứng dụng dùng wall-clock timestamp cho ordering, mutation mới có thể mang timestamp **nhỏ hơn** mutation trước.

### 5.3. Timestamp tương lai

Một writer có clock nhanh bất thường ghi timestamp rất lớn:

```text
T0: value=A, timestamp=2099-01-01
T1: value=B, timestamp=2026-11-14
```

Nếu LWW chọn max timestamp, B sẽ thua cho tới khi hệ có cơ chế sửa timestamp hoặc chấp nhận sự kiện thật sự mới hơn mốc tương lai đó.

Đây là một dạng **future timestamp poisoning**. Replica repair có thể tiếp tục lan truyền winner sai, vì nó tuân thủ quy tắc LWW.

### 5.4. Theo dõi NTP chưa đủ

Cần quan sát:

- Offset giữa các node/writers.
- Clock steps/drift và nguồn NTP.
- Timestamp lớn bất thường so với server receive time.
- Client timestamp không hợp lệ.
- Tỷ lệ mutation bị bỏ qua vì “older timestamp”.
- Có hay không producer cấp timestamp thủ công.

**Đồng bộ clock giảm rủi ro, không biến physical LWW thành phép nhận diện chính xác thứ tự thời gian thực trong mọi network partition.**

## 6. Precision: mili-giây, micro-giây và trùng timestamp

Timestamp có thể lưu với precision:

- Giây;
- Mili-giây;
- Micro-giây;
- Nanosecond theo mô hình cụ thể;
- Một logical counter kèm physical time.

Nếu 10.000 writes xảy ra trong cùng mili-giây trên một hot key, precision 1 ms sẽ tạo nhiều collision nếu không có thành phần logical/tie-break khác.

### 6.1. “Giá trị timestamp lớn hơn” chỉ là một phần

Với two-value LWW register, một **total order** cần định nghĩa cả khi timestamp bằng nhau:

\[
version=(timestamp,\ tieBreaker)
\]

Chọn winner theo lexicographic order:

\[
\operatorname{winner}=\max_{\text{lex}}(v_a,v_b)
\]

Ví dụ:

```text
A: (ts=1000, writer="region-a"), value="X"
B: (ts=1000, writer="region-b"), value="Y"

So writerId theo quy tắc cố định -> B thắng.
```

Đây là **một chính sách do ứng dụng thiết kế**, không phải quy tắc của mọi database.

### 6.2. Nếu cùng timestamp và cùng writerId?

Nếu cùng version nhưng payload khác, có thể có:

- Writer tái sử dụng sequence.
- Duplicate ID được gắn sai.
- Bug serialization.
- Dữ liệu bị sửa ngoài protocol.

Thay vì âm thầm chọn tùy node, hệ có thể **báo conflict/integrity error** và yêu cầu xử lý.

### 6.3. Tie-break không làm tăng tính đúng nghiệp vụ

Chọn `region-b` thắng vì tên lớn hơn chỉ giúp mọi bản sao chọn **cùng một kết quả**. Nó không chứng minh cập nhật của B xảy ra sau hoặc hợp ý người dùng hơn.

## 7. Yêu cầu hội tụ của một hàm merge

Một hàm merge LWW tốt nên ổn định khi dữ liệu đến trùng hoặc đảo thứ tự.

Ba tính chất mong muốn:

**Commutative:**

\[
merge(a,b)=merge(b,a)
\]

**Associative:**

\[
merge(merge(a,b),c)=merge(a,merge(b,c))
\]

**Idempotent:**

\[
merge(a,a)=a
\]

Nếu các candidate có version nằm trong một **total order ổn định**, việc chọn max có những tính chất này.

### 7.1. Vì sao quan trọng trong NoSQL?

Các sự kiện qua mạng có thể:

- Đến lệch thứ tự.
- Được retry.
- Được giao lại sau failover.
- Đi qua nhiều region.
- Được replay khi rebuild.

Nếu kết quả merge phụ thuộc thứ tự message đến, hai replicas có thể vẫn phân kỳ sau khi mỗi bên đều đã nhận cùng các events.

### 7.2. Những quy tắc tie-break nguy hiểm

- “Giữ cái đến sau tại node này” nhưng không lưu metadata chung.
- “Giữ theo thứ tự iteration của HashMap”.
- “Chọn bất kỳ nếu timestamp bằng nhau”.
- “Chọn theo local wall-clock lúc merge”.
- “Chọn theo tên host thay đổi khi restart”.

Tất cả có thể khiến replicas chọn winner khác nhau.

## 8. Java: LWW register có total-order version

Ví dụ Java 17 dưới đây minh họa một LWW register **do ứng dụng tự định nghĩa**, không giả vờ mô phỏng chính xác Cassandra/DynamoDB.

```java
import java.util.Objects;

public final class LwwRegisterDemo {

    record Version(
            long timestampMicros,
            String writerId
    ) implements Comparable<Version> {

        Version {
            Objects.requireNonNull(writerId);
        }

        @Override
        public int compareTo(Version other) {
            int byTime = Long.compare(
                    this.timestampMicros,
                    other.timestampMicros
            );

            if (byTime != 0) {
                return byTime;
            }

            return this.writerId.compareTo(other.writerId);
        }
    }

    record Candidate(
            String key,
            String value,
            boolean deleted,
            Version version
    ) {
        Candidate {
            Objects.requireNonNull(key);
            Objects.requireNonNull(version);
        }
    }

    static Candidate merge(Candidate a, Candidate b) {
        if (!a.key().equals(b.key())) {
            throw new IllegalArgumentException(
                    "Cannot merge different keys"
            );
        }

        int order = a.version().compareTo(b.version());

        if (order > 0) return a;
        if (order < 0) return b;

        if (Objects.equals(a.value(), b.value())
                && a.deleted() == b.deleted()) {
            return a;
        }

        throw new IllegalStateException(
                "Same version but conflicting payload"
        );
    }

    public static void main(String[] args) {
        Candidate a = new Candidate(
                "profile:U42:city",
                "Hà Nội",
                false,
                new Version(2_000_000L, "region-a")
        );

        Candidate b = new Candidate(
                "profile:U42:city",
                "Đà Nẵng",
                false,
                new Version(2_000_000L, "region-b")
        );

        Candidate winner = merge(a, b);
        System.out.println(winner.value());
        // Theo rule writerId lexicographic: Đà Nẵng.
    }
}
```

Điểm quan trọng:

1. `Version` so sánh timestamp rồi writerId theo luật cố định.
2. `merge` không phụ thuộc thứ tự giao message.
3. Cùng version nhưng payload khác được coi là lỗi protocol.
4. `deleted` là metadata về tombstone, không dùng `null` mơ hồ.
5. Không có logic cấp timestamp/đồng bộ clock trong ví dụ.

**Không dùng ví dụ này để bảo vệ payment, seat uniqueness hay inventory:** LWW register tự chọn winner nhưng không ngăn hai clients đã được ACK với hai quyết định trái nhau.

## 9. Logical clock: Lamport timestamp

Một cách không phụ thuộc trực tiếp wall-clock là dùng **Lamport logical clock**.

Mỗi process có counter `L`:

- Trước một local event, tăng `L`.
- Khi gửi message, mang theo `L`.
- Khi nhận message có `remoteL`, cập nhật `L = max(L, remoteL) + 1`.

Ví dụ:

```text
Node A:
  Event A1 -> L=1
  Send message L=1 ------>

Node B:
  Receive A1 -> L=max(0,1)+1=2
  Event B1   -> L=3
```

Nếu A1 **happens-before** B1, Lamport timestamps có thể phản ánh thứ tự:

\[
A1 \rightarrow B1 \implies L(A1)<L(B1)
\]

### 9.1. Chiều ngược lại không đúng

\[
L(A)<L(B)
\]

**không chứng minh** A causally precedes B. Hai concurrent events vẫn có thể được gắn các counters khác nhau.

### 9.2. Lamport clock cần tie-break cho total order

Dùng `(lamportCounter, writerId)` để tạo total order khi cần. Nhưng total order tùy ý của hai concurrent events **không cho biết user nào thực sự thao tác sau**.

### 9.3. Một key hay nhiều keys?

Logical sequence do một authority cấp cho một key là chuyện khác sequence cục bộ ở mỗi region. Không được so `L=100` của hai log độc lập như hai phiên bản chung nếu chưa có protocol thống nhất.

## 10. Hybrid Logical Clock (HLC)

**Hybrid Logical Clock** kết hợp thành phần physical clock với logical component để biểu diễn thứ tự phù hợp hơn khi có sự kiện cùng/đảo thời gian và truyền message.

Một dạng khái niệm:

```text
HLC = (physicalPart, logicalPart, nodeId)
```

Ví dụ:

```text
A: (2026-11-14T10:00:00.001Z, 0, A)
B: (2026-11-14T10:00:00.001Z, 1, B)
```

Một implementation HLC đúng sử dụng quy tắc cập nhật theo local event/received HLC và physical clock.

### 10.1. HLC giải quyết điều gì?

- Giảm phụ thuộc vào thứ tự wall-clock cục bộ đơn thuần.
- Có thể bảo toàn ordering tương thích với quan hệ happens-before khi protocol được dùng đúng.
- Vẫn có thành phần physical để liên hệ gần thời gian thực.
- Giảm collision timestamp nhờ logical component.

### 10.2. HLC không tự biết business intent

Hai updates concurrent, không có causal relation, vẫn cần chọn winner hoặc merge. HLC có thể tạo total order, nhưng đó **vẫn là chính sách phân xử**, không phải quyền nghiệp vụ.

### 10.3. HLC không phải tên thay cho server timestamp

Không tự gắn một counter vào `Instant.now()` rồi gọi đó là HLC đầy đủ. Cần quy tắc nhận remote clock, xử lý overflow/skew, persistence và failover.

### 10.4. Timestamp gần thời gian thực không đồng nghĩa total linearizability

HLC hỗ trợ ordering nhưng không tự tạo một consensus commit rule. Muốn external users thấy một thứ tự tuyến tính hóa toàn cục, còn phải có protocol/authority phù hợp.

## 11. Vector clock và version vector: khi muốn biết có concurrency

LWW chọn một winner, thường **mất thông tin** rằng hai values được sửa đồng thời.

**Vector clock/version vector** có thể biểu diễn quan hệ nhân quả giữa các phiên bản:

```text
Version A = {east: 2, west: 0}
Version B = {east: 1, west: 1}
```

A và B không trội nhau theo từng thành phần:

- A có `east=2 > 1`;
- B có `west=1 > 0`.

Hai phiên bản có thể là **concurrent**.

### 11.1. Dominance

Vector `x` dominates `y` khi tất cả thành phần của `x` lớn hơn hoặc bằng `y` và ít nhất một thành phần lớn hơn.

Ví dụ:

```text
X = {east:3, west:1}
Y = {east:2, west:1}
```

X dominates Y, cho thấy X đã bao hàm causal history của Y theo protocol phù hợp.

### 11.2. Concurrent versions

Nếu hai vectors không dominates nhau, hệ có thể:

- Trả sibling versions cho ứng dụng merge;
- Dùng domain-specific resolution;
- Dùng CRDT;
- Đưa vào conflict queue cho người dùng;
- Cuối cùng vẫn áp LWW nhưng ghi nhận có conflict.

### 11.3. Trade-off

Version vectors tăng metadata và độ phức tạp merge/garbage collection, nhất là có nhiều writers. Chúng hữu ích khi **không được âm thầm bỏ mất thay đổi của người dùng**.

## 12. LWW register và LWW element set

LWW có thể áp dụng với những kiểu dữ liệu khác nhau.

### 12.1. LWW register

Một key giữ đúng một giá trị thắng theo version:

```text
Register color:
  (red, t=100)
  (blue, t=110)

merge -> blue
```

### 12.2. LWW element set

Một tập hợp lưu metadata add/remove cho mỗi element.

Ví dụ:

```text
ADD "apple" at t=100
REMOVE "apple" at t=120
ADD "apple" at t=130
```

Theo một LWW-element-set policy, apple có mặt vì latest add t=130 thắng remove t=120.

### 12.3. Khi add/remove cùng timestamp

Có nhiều policy:

- Add-wins tie.
- Remove-wins tie.
- Deterministic node/event ID tie-break.

**Không có một luật chuẩn phù hợp cho mọi ứng dụng.** Nếu dùng CRDT LWW-element-set, phải mô tả rõ variant và merge semantics.

### 12.4. LWW set khác OR-Set

**Observed-Remove Set (OR-Set)** sử dụng causal tags để xử lý add/remove và concurrency theo thiết kế CRDT. Nó khác việc đơn giản chọn timestamp lớn nhất cho mỗi element.

Ví dụ collaborative editing hoặc shopping cart thường cần cân nhắc semantics “add đồng thời với remove” theo kỳ vọng người dùng.

## 13. LWW theo field/cell khác theo document

Giả sử document:

```json
{
  "userId": "U42",
  "city": "Hà Nội",
  "phone": "0900000000"
}
```

Hai devices offline:

- A sửa `city="Huế"`.
- B sửa `phone="0911111111"`.

### 13.1. Document-level LWW

Nếu cả hai gửi full-document replacement, bản có timestamp lớn hơn có thể ghi đè **toàn bộ document**. Một thay đổi ở field không liên quan bị mất:

```text
A writes whole doc:
  city=Huế, phone=0900000000, ts=100

B writes whole doc:
  city=Hà Nội, phone=0911111111, ts=101

Document LWW chooses B:
  city=Hà Nội (sửa của A bị mất)
  phone=0911111111
```

### 13.2. Field-level LWW

Nếu mỗi field có metadata/version riêng:

```text
city:  Huế, ts=100
phone: 0911111111, ts=101
```

cả hai cập nhật có thể được giữ lại, nếu không có ràng buộc chéo.

### 13.3. Field-level không luôn đúng hơn

Nếu `startDate` và `endDate` phải thỏa `startDate <= endDate`, việc merge độc lập từng field có thể tạo một cặp không hợp lệ.

Ví dụ:

```text
State đầu:
  start=2026-11-01
  end=2026-11-30

Region A cập nhật cặp thành 2026-12-10 ... 2026-12-20
Region B cập nhật cặp thành 2026-11-05 ... 2026-11-10

Merge theo từng field độc lập có thể lấy:
  start=2026-12-10
  end=2026-11-10
```

**Ranh giới conflict resolution phải phù hợp ranh giới invariant.**

## 14. Cassandra: LWW theo cell với write timestamps

Trong Cassandra, các regular mutations thường được hòa giải theo **timestamp ở cấp cell**, với những quy tắc cụ thể cho tombstone, tie-break và loại dữ liệu.

Đây là một ứng dụng quan trọng của LWW trong NoSQL.

### 14.1. Ví dụ CQL

```sql
CREATE TABLE customer_profile (
    customer_id text PRIMARY KEY,
    city text,
    phone text
);
```

Ghi có timestamp do client chỉ định:

```sql
UPDATE customer_profile
USING TIMESTAMP 1700000000000000
SET city = 'Hà Nội'
WHERE customer_id = 'U42';
```

Timestamp CQL được biểu diễn theo **microseconds kể từ Unix epoch** trong trường hợp cú pháp `USING TIMESTAMP`. Con số trên chỉ minh họa, không gắn với thời gian hiện tại.

Sau đó một mutation có timestamp cao hơn:

```sql
UPDATE customer_profile
USING TIMESTAMP 1700000000000100
SET city = 'Đà Nẵng'
WHERE customer_id = 'U42';
```

Theo LWW resolution thông thường, `city="Đà Nẵng"` sẽ thắng đối với cell ấy.

### 14.2. Arrival order không quyết định winner

Mutation với timestamp nhỏ hơn có thể tới replica muộn vì hinted handoff, retry hoặc network lag, nhưng không được mặc nhiên ghi đè mutation timestamp lớn hơn.

```text
Replica C:
  nhận city=Đà Nẵng, ts=200
  sau đó nhận city=Huế, ts=100

Result: giá trị ts=200 có ưu tiên.
```

### 14.3. Client timestamp vs coordinator/server timestamp

Nếu ứng dụng tự gắn timestamp:

- Cần hiểu unit và precision.
- Không thể dùng `System.currentTimeMillis()` trực tiếp như microseconds mà không chuyển unit.
- Không tin clock client không được kiểm soát.
- Cần tránh nhiều concurrent writers cấp timestamps không phối hợp.

Nếu để driver/coordinator/database tự cấp timestamp, vẫn phải biết clock nào được dùng và hợp đồng phiên bản. **Không tự động coi mọi server-generated timestamp là một global consensus sequence**.

### 14.4. LWW theo cell làm field độc lập hội tụ

Một update `city` và một update `phone` có thể không xung đột như hai full-document replacements. Nhưng invariant liên field vẫn có thể bị phá nếu ứng dụng tách mutations không nguyên tử.

### 14.5. Regular write CL=QUORUM không phải LWT

Consistency level quyết định số replica ACK/đường read, không thay compare-and-set atomicity. Hai writers cùng update một cell với timestamps khác nhau vẫn phải hòa giải winner.

Nếu nghiệp vụ cần “chỉ đổi từ PENDING sang CONFIRMED khi version=7”, cần conditional mutation/LWT hoặc authority thích hợp, không chỉ nâng regular write từ ONE lên QUORUM.

## 15. Cassandra: timestamp bằng nhau và tie-break phải hiểu đúng phiên bản

Trong một số trường hợp Cassandra cần giải quyết **hai cell cùng timestamp**, cơ chế reconciliation có những luật deterministic liên quan giá trị và tombstone. Chi tiết có thể phụ thuộc loại cell và phiên bản.

Điều cần nhớ:

- Không thiết kế business rule dựa vào “giá trị chuỗi lớn hơn sẽ thắng” nếu chưa có contract chính thức cho phiên bản.
- Không tự tạo cùng write timestamp cho nhiều mutation xung đột với hy vọng arrival order quyết định.
- Tombstone/delete có semantics riêng khi cạnh tranh với live value.
- Không tự dùng server wall-clock ở thời điểm repair để thay timestamp mutation gốc.

Nếu cần một chính sách nghiệp vụ rõ ràng, dùng **version/conditional write hoặc logic domain** thay vì dựa vào chi tiết tie-break nội bộ.

## 16. Delete là một mutation có thứ tự: tombstone

Trong hệ LSM như Cassandra, DELETE không đơn giản là “xóa byte ngay”. Nó thường tạo một **tombstone** đại diện cho việc xóa.

Ví dụ:

```text
T0:
  value=ACTIVE, timestamp=100

T1:
  tombstone DELETE, timestamp=200

T2:
  late replica/hint: value=ACTIVE, timestamp=100
```

Nếu tombstone còn tồn tại và reconciliation hoạt động đúng, giá trị cũ timestamp 100 không được sống lại chỉ vì message tới sau.

### 16.1. Delete có thể thua một write timestamp mới hơn

```text
value=ACTIVE, ts=300
DELETE tombstone, ts=200
```

Một delete timestamp 200 không chắc thắng mutation live timestamp 300.

Nếu writer bị clock skew lớn, có thể xảy ra tình trạng ứng dụng gọi DELETE “sau” nhưng tombstone mang timestamp thấp hơn giá trị đã tồn tại.

### 16.2. Equal timestamps

Cassandra có những quy tắc riêng xử lý tie giữa live cell và tombstone. Không nên tùy ý suy từ lexicographic tie-break của một LWW register tự viết; phải dựa vào semantics phiên bản.

### 16.3. Xóa dữ liệu có yêu cầu compliance

Nếu nghiệp vụ yêu cầu dữ liệu phải được xóa ở mọi nơi, cần xét thêm:

- Tombstones và repair.
- Backup/snapshot retention.
- CDC và search projection.
- Replica offline lâu.
- TTL.
- Storage encryption/erasure policy.
- Quy trình đáp ứng yêu cầu xóa.

Một client nhận DELETE success theo CL không đồng nghĩa dữ liệu đã được xóa vật lý khỏi mọi bản sao, backup và hệ dẫn xuất.

## 17. Tombstone garbage collection và zombie data

Giả sử replica C offline khi A/B nhận DELETE:

```text
A: tombstone(K, ts=200)
B: tombstone(K, ts=200)
C: live K=v1, ts=100
```

Nếu C offline lâu, các tombstones ở A/B về sau bị purge sau khi đủ điều kiện compaction và grace, C có thể mang lại giá trị cũ khi rejoin:

```text
A: không còn tombstone
B: không còn tombstone
C: vẫn có K=v1
```

Trong điều kiện phù hợp, **zombie data** có thể xuất hiện.

### 17.1. Vai trò gc_grace_seconds

`gc_grace_seconds` trong Cassandra liên quan khoảng thời gian tombstone được bảo vệ trước khi có thể đủ điều kiện thu gom. Hết thời gian **không đồng nghĩa tombstone biến mất tức thì**; compaction và các quy tắc khác còn ảnh hưởng.

### 17.2. Hinted handoff không thay repair

Hints giúp chuyển những mutation mà coordinator đã lưu, nhưng không chứng minh mọi delete bị bỏ lỡ đều có hint. Anti-entropy repair định kỳ và quy trình xử lý node offline quá lâu vẫn cần thiết.

### 17.3. LWW không bảo đảm xóa vĩnh viễn nếu mất tombstone

Nếu bằng chứng xóa không còn nhưng một replica cũ vẫn giữ live value, quy tắc chọn version có thể không còn đủ thông tin để chọn đúng. Đây không phải lý do “tăng timestamp cho mọi write”, mà là vấn đề **vòng đời tombstone và repair**.

## 18. TTL: thời gian hết hạn khác write timestamp

Một record được ghi với TTL:

```sql
INSERT INTO sessions_by_id (
    session_id, user_id, state
)
VALUES ('S100', 'U42', 'ACTIVE')
USING TTL 3600;
```

Có hai khái niệm:

- **Write timestamp:** metadata hòa giải mutation.
- **Expiration time/TTL:** dữ liệu hết hạn khi nào theo semantics engine.

Chúng không phải một.

### 18.1. Replay native mutation

Nếu một replica nhận mutation gốc muộn qua hinted handoff, không nên hình dung nó như ứng dụng chạy một INSERT mới và bắt đầu lại TTL từ lúc replay. Hệ cần giữ semantics expiration của mutation gốc.

### 18.2. Replay event ở tầng ứng dụng

Ngược lại, một consumer tự chạy:

```text
T0: Event "create session TTL 3600"
T3: Consumer replay như một INSERT mới TTL 3600
```

có thể vô tình kéo dài session nếu nó tính lại thời điểm hết hạn. Cần lưu **absolute expiresAt** hoặc thời gian còn lại theo nghiệp vụ, tùy model.

### 18.3. TTL expiration cũng dẫn tới vấn đề xóa

TTL hết hạn có thể tạo/được quản lý theo semantics tombstone. Một replica cũ chưa đồng bộ và chính sách grace/repair không phù hợp có thể gây rủi ro dữ liệu hồi sinh.

## 19. DynamoDB Global Tables: cần phân biệt replication mode

Trong các cấu hình **multi-region eventual consistency** của DynamoDB global tables, đồng bộ liên vùng và xung đột concurrent writes có cơ chế hòa giải theo **last-writer-wins** trong phạm vi tính năng ấy.

Điều đó không có nghĩa:

- Mọi write của DynamoDB ở mọi table đều luôn được phân xử bằng cùng một LWW policy.
- Một `ConditionExpression` thành công ở Region A tự bảo đảm một claim duy nhất toàn cầu dưới mọi mode multi-writer eventual.
- Một read strongly consistent trong region tự thành strong read trên mọi region.
- DynamoDB và Cassandra dùng cùng timestamp source và tie-break rule.

Các cấu hình/tính năng multi-region với bảo đảm mạnh hơn có thể có hợp đồng khác; phải kiểm tra đúng **global table mode, region set và API** đang dùng.

### 19.1. Ví dụ concurrent updates

```text
Region East:
  product P100: promotion="A"

Region West:
  product P100: promotion="B"

WAN partition -> local writes accepted under eventual model
WAN recovery -> replication + conflict resolution
```

Một writer có thể bị thay thế dù đã được local region ACK. Khi business muốn “không bao giờ nhận hai mã khuyến mãi duy nhất”, cần một quyền quyết định an toàn hơn LWW sau hội tụ.

### 19.2. Tránh tự áp dụng conditional write cục bộ như global CAS

Nếu hai regions không phối hợp theo same conditional authority, hai điều kiện “giá trị chưa tồn tại” có thể cùng đúng cục bộ. Replication LWW sau đó chọn winner nhưng không đảo ngược business side effects.

### 19.3. Thiết kế tốt hơn theo dữ liệu

- Catalog hoặc preference phù hợp eventual/LWW khi chấp nhận mất một concurrent edit.
- Inventory, voucher quota hoặc claim duy nhất cần conditional authority/transaction trong phạm vi bảo đảm.
- Nếu muốn writes offline ở nhiều vùng, có thể phân bổ quota/tokens trước hoặc dùng mergeable CRDT cho những dữ liệu phù hợp.

## 20. Azure Cosmos DB: conflict resolution là một cấu hình thiết kế

Trong những mô hình Cosmos DB cho phép ghi ở nhiều vùng, conflict resolution có thể dùng chính sách **Last Write Wins** với property/timestamp xác định winner, hoặc những chính sách/khả năng xử lý xung đột khác theo API và cấu hình.

Một số điểm cần chú ý:

- Đọc rõ **conflict resolution policy** của container.
- Xác định timestamp/property dùng so sánh.
- Hiểu scope của một logical partition.
- Hiểu transaction boundary của transactional batch.
- Phân biệt session, eventual, bounded staleness và strong consistency.
- Không nhầm conflict resolution liên vùng với atomicity đa partition.

### 20.1. Custom conflict property

Nếu ứng dụng dùng property tùy chỉnh để chọn winner, phải đảm bảo mọi writers tạo property này có **thứ tự và semantics thống nhất**.

Nếu Region A ghi `priorityTimestamp` theo clock cục bộ nhưng Region B ghi theo event time từ điện thoại, hai bên đang so những đơn vị không cùng nghĩa.

### 20.2. Server timestamp cũng cần hiểu

Một timestamp được cấp bởi dịch vụ có thể tốt hơn client clock tự khai trong một số tình huống, nhưng **không nên tự khẳng định nó là global linearizable commit order** nếu policy không hứa như vậy.

### 20.3. Policy theo business type

Có thể dùng LWW cho preference, nhưng một claim quyền truy cập hoặc chuyển tiền vẫn cần transaction/authority và reconciliation theo contract phù hợp.

## 21. MongoDB: đừng coi primary oplog replication là generic multi-master LWW

MongoDB replica set thông thường có primary cho writes, secondaries nhận oplog. Các operations có thứ tự theo cơ chế của replica set, cùng write concern/read concern/failover semantics.

Điều này **khác** một mô hình multi-leader “mỗi region ghi version theo local timestamp rồi sau đó LWW chọn winner”.

### 21.1. Lost update ở tầng ứng dụng vẫn có thể xảy ra

Hai clients cùng đọc document:

```json
{
  "_id": "U42",
  "city": "Hà Nội",
  "phone": "0900000000",
  "version": 7
}
```

Client A sửa city. Client B dựa trên bản cũ rồi replace toàn bộ document, có thể làm mất update city của A dù database áp dụng từng write nguyên tử.

### 21.2. Optimistic concurrency control

Một hướng là dùng version:

```javascript
db.profiles.updateOne(
  { _id: "U42", version: 7 },
  {
    $set: { city: "Huế" },
    $inc: { version: 1 }
  }
);
```

Client kiểm tra `matchedCount`. Nếu zero, có conflict và cần reload/merge/retry có kiểm soát.

### 21.3. `$currentDate` không tự giải quyết conflict

Một field `updatedAt` do server cập nhật hữu ích cho audit/UI, nhưng **không tự biến các updates dựa trên bản cũ thành CAS**. Cần điều kiện version nếu muốn không ghi đè im lặng.

### 21.4. Transactions có scope riêng

Với các invariants nhiều documents, sử dụng transaction/constraint phù hợp thay vì chỉ chọn bản có timestamp mới nhất.

## 22. Firestore: offline edits và last-write-wins

Firestore có thể hỗ trợ client offline persistence/cached writes trong các SDK tương ứng. Khi nhiều thay đổi tới **cùng một document**, hành vi đồng bộ offline có thể dẫn đến chính sách last-write-wins theo hợp đồng tính năng.

Điều cần xem xét:

- Local pending write khác backend-committed write.
- Một thiết bị offline có thể hiển thị giá trị của mình trước khi được backend đồng bộ.
- Thiết bị khác có thể ghi trong thời gian ấy.
- Khi reconnect, conflict resolution có thể chọn một phiên bản, không nhất thiết giữ cả hai thay đổi.
- Transactions và preconditions có semantics khác với blind offline replacement.

### 22.1. Một UI cần minh bạch

```json
{
  "documentId": "profile-U42",
  "syncState": "LOCAL_PENDING",
  "city": "Huế"
}
```

Đừng hiển thị “Đã đồng bộ trên mọi thiết bị” khi mới lưu local cache.

### 22.2. Invariant không được dựa vào offline LWW

Một reservation duy nhất, quota hoặc quyền admin phải được kiểm tra ở authority thích hợp. Không lấy offline cached state để xác nhận một transaction cuối cùng.

## 23. Redis: không biến replication bất đồng bộ thành LWW tổng quát

Redis primary–replica replication thường theo một primary write path, với follower lag/failover concerns. Đây không mặc định là một multi-master LWW register theo client timestamps.

### 23.1. ACK local rồi rollback sau failover

```text
T0: Primary SET K=A
T1: ACK
T2: Primary lỗi trước khi replica nhận
T3: Replica được promote, vẫn K=old
```

Điều này là **replication durability/failover** issue, không nên giải thích như một LWW tie-break.

### 23.2. Application-managed LWW trên Redis

Nếu ứng dụng muốn lưu `(timestamp, value)` và merge bằng Lua/script/transaction, đó là **policy do ứng dụng tự triển khai**. Cần nguyên tử cùng data write, chống timestamp tương lai và xử lý duplicate events.

### 23.3. Redis lock không chứng minh writer mới nhất

Một `SET NX PX` lease có thể hết hạn trong lúc worker bị pause. Lock owner cũ vẫn có thể thực hiện external write. Cần fencing token/authority khi rủi ro cao.

## 24. Search index, cache và read models: “mới nhất” theo source version

Một source NoSQL có thể publish events tới:

```text
Authoritative DB
      |
      +-- CDC/outbox --> Search index
      |
      +-- CDC/outbox --> Cache updater
      |
      +-- CDC/outbox --> Analytics warehouse
```

Nếu event `v12` tới trước `v11`, một projector upsert theo **arrival time** có thể viết đè bản mới bằng bản cũ.

### 24.1. Version guard thay arrival-order LWW

```text
Current projection:
  orderId=O100, version=12, status=CANCELLED

Incoming event:
  version=11, status=PAID

Rule:
  if incoming.version <= stored.version:
      ignore
```

Điều kiện so sánh version và write phải nguyên tử ở sink, hoặc có một protocol ngăn concurrent consumers phá guard.

### 24.2. Event version từ đâu?

Phiên bản nên được cấp tại **authoritative aggregate** theo thứ tự mutation được quyết định, không phải tự cấp độc lập tại mỗi projector.

Nếu hai aggregates có versions riêng, không so version 12 của Order O100 với version 13 của Inventory P100 để xác định toàn hệ mới hơn.

### 24.3. Delete và projection tombstone

Một delete event v13 tới rồi upsert v11 tới sau. Nếu sink xóa record và xóa luôn last version, upsert cũ có thể tạo lại record.

Giữ tombstone/version marker hoặc generation theo policy retention để ngăn resurrection.

### 24.4. Backfill cạnh tranh live stream

Một job backfill đọc snapshot cũ có thể chạy cùng CDC stream mới. Phải giữ source version/checkpoint để không ghi đè live projection bằng bản backfill đến sau.

### 24.5. `updatedAt` không luôn đủ

Nếu events có cùng timestamp, hoặc clock thay đổi, cần aggregate version/sequence hay một total-order token trong phạm vi đúng.

## 25. Conditional writes và optimistic concurrency khác LWW

**LWW:** nhận nhiều candidates rồi chọn một winner theo ordering policy.

**Compare-and-set (CAS):** chỉ áp dụng mutation nếu điều kiện về trạng thái hiện tại còn đúng.

Ví dụ:

```text
Current:
  version=7, city="Hà Nội"

Client A:
  IF version=7:
     city="Huế", version=8

Client B:
  IF version=7:
     city="Đà Nẵng", version=8
```

Nếu cả hai đi qua cùng một authority nguyên tử, chỉ một update dựa trên version 7 được áp dụng; client còn lại phải xử lý conflict.

### 25.1. CAS không tự merge

CAS phát hiện xung đột thay vì âm thầm chọn winner. Ứng dụng vẫn phải quyết định:

- Reload và hỏi người dùng.
- Merge fields độc lập.
- Retry với business rule.
- Từ chối mutation.
- Bắt đầu một workflow mới.

### 25.2. Version phải tăng ở authority

Nếu clients cùng tự cấp version 8 rồi ghi vô điều kiện ở hai regions eventual, không có CAS thực sự. Version number chỉ có ý nghĩa bảo vệ khi có **atomic guard tại nơi quyết định**.

### 25.3. HTTP ETag / If-Match

Một REST API có thể dùng ETag:

```http
PATCH /profiles/U42
If-Match: "version-7"
Content-Type: application/json

{"city":"Huế"}
```

Server phải thực sự kiểm tra điều kiện cùng commit, trả conflict/precondition failure nếu version không khớp. Chỉ nhận header mà bỏ qua check không tạo OCC.

## 26. LWW vs domain-specific merge

Một số dữ liệu không nên chọn một writer thắng toàn bộ.

### 26.1. Giỏ hàng

Thiết bị A thêm sản phẩm P1, thiết bị B thêm P2 offline. Document-level LWW có thể làm mất một sản phẩm.

Domain merge có thể gộp operations hoặc OR-Set/CRDT trong một số mô hình. Nhưng cần định nghĩa semantics “remove đồng thời với add” và quantity conflicts.

### 26.2. Bộ đếm lượt xem

Thay vì mỗi region ghi total:

```text
East total=101
West total=101
```

rồi LWW chọn 101, có thể cần PN-Counter/G-Counter hoặc event aggregation có idempotency, tùy yêu cầu monotonicity và duplicate handling.

### 26.3. Văn bản cộng tác

Hai người sửa hai đoạn khác nhau. LWW toàn document xóa công sức của một người. Có thể dùng operation-based CRDT/OT với causal ordering và conflict representation phù hợp.

### 26.4. Hồ sơ

Cập nhật độc lập `city` và `phone` có thể merge theo field. Nhưng không nên merge độc lập `startDate/endDate` nếu chúng tạo một invariant chung.

### 26.5. Inventory

Nếu hai regions cùng bán đơn vị hàng cuối cùng, chọn owner có timestamp lớn hơn **sau khi đã thu tiền cả hai** không đáp ứng invariant. Dùng authoritative reservation, allocated quotas hoặc workflow PENDING phù hợp.

## 27. LWW trong giao dịch tiền và quyền truy cập: rủi ro lớn

### 27.1. Số dư tài khoản

Nếu hai cập nhật số dư:

```text
Balance initial = 100

Region A subtract 30 -> writes 70
Region B subtract 20 -> writes 80
```

LWW chọn 70 hoặc 80, đánh mất một debit. Kết quả đúng theo nghiệp vụ (nếu cả hai debit hợp lệ) là 50, nhưng không thể suy ra bằng LWW của tổng.

Cần **ledger, atomic increments, transactions hoặc một authority duy nhất** theo invariant, không chọn balance snapshot bằng timestamp.

### 27.2. Permission revoke

Admin thu hồi quyền lúc 12:00, replica cũ có permission `ADMIN` với timestamp lạ trong tương lai. Một LWW policy có thể giữ giá trị trái quyền.

Với hành động nhạy cảm:

- Kiểm tra authority.
- Dùng revocation epoch/generation.
- Fail closed nếu thiếu bằng chứng quyền.
- Không tin stale cache chỉ vì record có `updatedAt` lớn.

### 27.3. Unique username hoặc voucher quota

Hai regions có thể cùng cho claim rồi LWW hội tụ một winner. Nhưng mỗi client đã nhận success. Phải có **atomic claim/global authority** theo contract hoặc phân bổ quyền trước.

## 28. Vấn đề “timestamp tương lai độc hại”

Một client cấp timestamp quá cao:

```json
{
  "key": "profile:U42",
  "value": "ATTACKER_VALUE",
  "timestampMicros": 4102444800000000
}
```

Nếu hệ mù quáng chọn max timestamp, những updates hợp lệ với timestamp hiện tại có thể thua trong thời gian dài.

### 28.1. Bảo vệ tại ingest

- Giới hạn timestamp vượt xa server receive time.
- Xác thực source/writer permission.
- Không cho client tự đặt write timestamp nhạy cảm nếu không cần.
- Gắn server-authoritative sequence khi cần.
- Audit những versions bất thường.
- Dùng CAS/epoch để kiểm soát thay đổi.

### 28.2. Không tự ý sửa timestamp khi replay

Nếu replay của CDC thay timestamp gốc bằng thời gian hiện tại, một event cũ sẽ trở thành “mới nhất” và có thể ghi đè live state. Phải giữ source version và semantics.

### 28.3. Chọn ngưỡng skew có cơ sở

Một cửa sổ chấp nhận timestamp cần tính tới offline UX, sự kiện đến muộn và yêu cầu sản phẩm. Không dùng một ngưỡng tùy tiện để làm mất dữ liệu hợp lệ.

## 29. Timestamp không thay idempotency key

Hai messages cùng payload có thể được giao lại:

```text
E100: set city="Huế", timestamp=100
E100: retry same event
```

LWW với cùng version có thể idempotent nếu được merge đúng. Nhưng nếu consumer **tạo timestamp mới cho mỗi retry**, duplicate event trở thành một mutation “mới” và có thể ghi đè một cập nhật khác.

### 29.1. Idempotency theo ý định nghiệp vụ

Lưu operation ID hoặc event ID:

```json
{
  "eventId": "EVT-100",
  "aggregateId": "U42",
  "aggregateVersion": 12,
  "operation": "CHANGE_CITY",
  "value": "Huế"
}
```

Producer cần cấp version/id tại authority, consumer kiểm tra trùng theo cùng scope.

### 29.2. LWW không tự bảo vệ external side effect

Một event `PAYMENT_SUCCEEDED` được giao lại có thể khiến consumer gửi email hai lần. Chọn winner LWW trong storage không tự đảm bảo email exactly-once. Cần idempotency/outbox/inbox tương ứng.

## 30. Thứ tự xóa và tái tạo: generation quan trọng

Một key có thể bị xóa rồi tạo lại cho một thực thể mới.

```text
T0: key K belongs to account A, generation 1
T1: delete K, generation 1
T2: key K reused for account B, generation 2
T3: old update for account A arrives late
```

Nếu chỉ so timestamp, một old update có clock tương lai có thể phá dữ liệu account B.

### 30.1. Thêm generation/epoch

Một version có thể là:

\[
version=(generation,\ sequence)
\]

So generation trước, sequence sau.

```text
(gen=2, seq=1) > (gen=1, seq=999)
```

Khi generation được authority cấp an toàn, events cũ không được vượt sang lifecycle mới.

### 30.2. Định nghĩa scope

Generation cần gắn đúng resource/namespace. Không dùng một `epoch=5` toàn cục tự khai của client để tuyên bố mạnh hơn authority thật.

### 30.3. Retention của tombstone/version marker

Nếu tombstone bị purge quá sớm, hệ có thể quên generation và chấp nhận old writes. Cần retention lớn hơn expected replay/offline window hoặc cơ chế truy vấn authoritative khác.

## 31. Multi-region và quyền ghi

Giả sử hai regions cùng nhận ghi vào cùng key và đồng bộ eventual:

```text
Region A: value=X, timestamp=200
Region B: value=Y, timestamp=190
```

LWW chọn X sau reconciliation.

Điều gì xảy ra nếu Region B đã trả thành công cho user Y? Người dùng có thể nhìn Y ngay sau write, rồi khi hệ hội tụ lại thấy X. Đây có thể được coi là **conflict resolution theo hợp đồng eventual**, nhưng không nên đưa cùng UX đó vào một nghiệp vụ yêu cầu quyết định cuối cùng.

### 31.1. Đường đọc local

Một local read sau local write có thể cho cảm giác read-your-writes, nhưng sau khi replication conflict resolution chọn remote winner, giá trị có thể đổi.

### 31.2. Stale writes và clock lệch giữa vùng

Nếu region A và B dùng clocks độc lập, LWW theo physical timestamp có rủi ro chọn sai real-time order. Cần đánh giá timestamp source và synchronization service.

### 31.3. Chọn one-write authority

Một số dữ liệu cần route writes tới một authority/quorum nhất định. Khi mạng chia cắt, vùng không có quyền commit phải từ chối hoặc trả PENDING chưa xác nhận.

### 31.4. Phân bổ quota trước

Để tăng availability mà giữ giới hạn tổng, có thể cấp trước quyền tiêu thụ:

```text
Total seats = 100
Region East quota = 60
Region West quota = 40
```

Mỗi region chỉ bán trong phần quota được cấp bền vững. LWW không cần quyết định hai writes cùng tiêu một đơn vị quyền toàn cục.

## 32. LWW và leader-based replication: không gắn nhãn quá rộng

Một leader-based replicated log có thể xác định thứ tự writes dựa trên log/commit sequence của leader, rồi followers replay theo thứ tự đã được quyết định. Đó là một kiểu **serialized authority**, không nhất thiết LWW bằng wall-clock.

Ví dụ:

```text
Leader log index 100: set city="Huế"
Leader log index 101: set city="Đà Nẵng"
```

Theo state machine, mutation index 101 được áp dụng sau 100.

Nếu client gửi event time của mutation 100 là 12:10 nhưng event time của 101 là 12:05, thứ tự commit vẫn là 100 rồi 101.

**“Lệnh được áp dụng cuối” theo log không đồng nghĩa “timestamp vật lý lớn nhất”.**

### 32.1. Quy tắc business cần được đặt ở đâu?

Nếu cần tranh quyền sở hữu, authority phải thực thi conditional invariant, không chỉ chấp nhận cả hai writes rồi xem log cuối cùng là owner.

### 32.2. Read replica lag

Dù leader có log thứ tự rõ, follower chưa apply có thể trả giá trị cũ. Thứ tự source và read freshness là hai bảo đảm khác nhau.

## 33. LWW không đồng nghĩa linearizability

**Linearizability** yêu cầu các operation nhìn như xảy ra nguyên tử tại một thời điểm nằm giữa invocation và response, tôn trọng real-time order của non-overlapping operations trong phạm vi đã định nghĩa.

Ví dụ:

```text
T0: Client A SET K=X hoàn thành
T1: Client B bắt đầu SET K=Y sau T0
T2: Client B hoàn thành
```

Nếu physical timestamp của A cao hơn Y vì clock skew, LWW có thể giữ X dù B bắt đầu và hoàn thành sau A. Điều đó không phù hợp một read/write register linearizable theo semantics ấy.

### 33.1. Total order là chưa đủ

Một tổng thứ tự dựa trên `(timestamp, writerId)` giúp replicas hội tụ, nhưng có thể không tôn trọng real-time order.

### 33.2. Consensus không tự khiến mọi read mới nhất

Ngay cả hệ có Raft/Paxos, follower reads không có read protocol/chờ applied index có thể stale. **Consensus commit và read visibility** là hai lớp khác nhau.

### 33.3. Causal consistency là mục tiêu khác

Nếu B nhìn thấy kết quả của A rồi tạo mutation phụ thuộc nó, causal consistency muốn giữ quan hệ đó. Một clock protocol phù hợp có thể bảo toàn causal order, nhưng LWW thuần theo physical timestamp có thể đi ngược nếu clock sai.

## 34. LWW theo toàn record có thể gây lost update âm thầm

Một profile:

```json
{
  "name": "Mai",
  "city": "Hà Nội",
  "phone": "0900000000",
  "version": 7
}
```

Hai clients dựa trên version 7:

```text
A sửa city=Huế
B sửa phone=0911111111
```

Nếu mỗi client gửi toàn document:

```json
{
  "name": "Mai",
  "city": "Huế",
  "phone": "0900000000"
}
```

và:

```json
{
  "name": "Mai",
  "city": "Hà Nội",
  "phone": "0911111111"
}
```

Document-level LWW làm mất sửa đổi của một client dù fields không liên quan.

### 34.1. Tránh replace khi chỉ update một field

Nếu database hỗ trợ partial update, gửi mutation đúng field thay vì full-object replacement khi access pattern cho phép.

### 34.2. Optimistic version check

Dùng ETag/conditional write để chặn client ghi đè version mà nó chưa đọc.

### 34.3. Merge có điều kiện

Nếu hai fields độc lập, backend có thể merge. Nếu có invariant chéo, cần validation/transaction.

## 35. Một thiết kế API với conflict-aware update

Ví dụ client đọc:

```http
GET /profiles/U42
```

Response:

```http
HTTP/1.1 200 OK
ETag: "v7"
Content-Type: application/json

{
  "userId": "U42",
  "city": "Hà Nội",
  "phone": "0900000000"
}
```

Client cập nhật:

```http
PATCH /profiles/U42
If-Match: "v7"
Content-Type: application/json

{
  "city": "Huế"
}
```

Backend phải kiểm tra ETag/version **cùng atomic mutation**. Nếu version đã đổi:

```http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{
  "code": "STALE_VERSION",
  "currentVersion": "v8"
}
```

Client có thể reload, hiển thị conflict hoặc tự merge theo rule đã định nghĩa.

### 35.1. Timestamp dùng để hiển thị, version để điều phối

Response có thể chứa cả:

```json
{
  "updatedAt": "2026-11-14T10:00:00Z",
  "version": 8
}
```

`updatedAt` phục vụ UI/audit. `version` phục vụ CAS và ordered projection theo authority. Hai thứ có vai trò khác nhau.

## 36. Quan sát hệ thống LWW

Nếu ứng dụng dùng LWW, cần có khả năng trả lời “vì sao giá trị này thắng?”

Những metadata hữu ích:

- Key, logical partition, tenant.
- Mutation ID/event ID.
- Writer/region ID.
- Physical timestamp và đơn vị thời gian.
- Logical/HLC component nếu có.
- Server receive/commit time.
- Aggregate version/generation.
- Current winning version.
- Winner/loser decision reason.
- Tỷ lệ equal-timestamp conflicts.
- Tỷ lệ out-of-order events.
- Timestamp future-skew.
- Replication lag và source–projection gap.
- Tombstone/backfill recovery status.

### 36.1. Metric nào báo rủi ro?

| Metric | Ý nghĩa |
|---|---|
| `lww_conflicts_total` | Có bao nhiêu collisions/conflicts |
| `lww_discarded_mutations_total` | Bao nhiêu updates bị bỏ vì version cũ |
| `timestamp_skew_ms` | Writer clock lệch ingest/server clock bao nhiêu |
| `future_timestamp_rejected_total` | Có bất thường/khả năng giả mạo timestamp |
| `equal_version_payload_conflict_total` | Một version bị dùng cho payload khác |
| `projection_version_lag` | Read model đang trễ nguồn |
| `tombstone_resurrection_total` | Có record cũ được tạo lại bất thường |
| `cas_conflict_total` | Những stale writes được chặn có điều kiện |

Tên metric trên chỉ là **đề xuất cho hệ tự instrument**, không phải metric mặc định của mọi database.

### 36.2. Hạn chế logging dữ liệu nhạy cảm

Không log toàn bộ giá trị số dư, quyền hoặc PII chỉ để debug LWW. Có thể ghi hashed key, version, conflict type và trace ID để điều tra an toàn.

## 37. Vận hành replay, repair và rebuild

Một hệ có thể gặp:

- Replica down dài;
- CDC events được replay;
- Search index rebuild;
- Restore snapshot cũ;
- Thay region primary;
- Event processor retry;
- Migration từ schema cũ sang schema mới.

Trong các tình huống này, LWW chỉ an toàn nếu metadata ordering còn đầy đủ và đồng nghĩa.

### 37.1. Restore snapshot cũ

Snapshot t0 chứa `version=8`; source hiện có `version=12`. Nếu restore bản cũ lên production rồi cấp timestamp mới t13, một bản cũ có thể thắng nếu flow coi restore là write mới.

Cần restore/replay theo authoritative log, version guard và runbook thay vì blind upsert.

### 37.2. Backfill phải mang source version

Backfill snapshot không được dùng `now()` làm timestamp để ghi vào read model, nếu điều đó khiến snapshot cũ ghi đè CDC event mới.

### 37.3. Replay cần idempotent

Consumer không được đổi event ID hoặc event timestamp mỗi lần retry. LWW register theo source version có thể tiếp nhận duplicate không thay đổi trạng thái.

### 37.4. Repair hội tụ không xác nhận correctness

Nếu cả hai replicas có timestamp sai trong tương lai, repair có thể khiến tất cả cùng giữ winner sai. Business audit và source-of-truth reconciliation vẫn cần khi có bất biến quan trọng.

## 38. Testing: đảo thứ tự và tái phát sự kiện

### Test 1 — Giao sự kiện đúng thứ tự

```text
Input: A(ts=100), B(ts=200)
Expected: B
```

### Test 2 — Giao sự kiện ngược

```text
Input: B(ts=200), A(ts=100)
Expected: B
```

### Test 3 — Duplicate

```text
Input: A(ts=100), A(ts=100)
Expected: A, no additional effect
```

### Test 4 — Tie deterministic

```text
A(ts=100, writer=a)
B(ts=100, writer=b)
```

Chọn một winner giống nhau ở mọi replica theo documented tie-break.

### Test 5 — Cùng version khác payload

```text
A(ts=100, writer=a, value=X)
B(ts=100, writer=a, value=Y)
```

Nên báo integrity conflict hoặc xử lý theo rule rõ, không chọn tùy lần chạy.

### Test 6 — Clock skew

Writer A nhanh 30 giây, writer B đúng giờ; B thao tác sau A. Xác minh policy phù hợp với yêu cầu, hoặc tránh dùng physical timestamp khi cần real-time order.

### Test 7 — Future timestamp

Một writer gửi version rất lớn; kiểm tra validation/quarantine/authority.

### Test 8 — Tombstone

DELETE timestamp=200, late UPSERT timestamp=100. Nếu tombstone còn hợp lệ, late update không làm record sống lại.

### Test 9 — TTL

Replay sau khi TTL đã hết; không được khởi động lại TTL như một event mới nếu đó là replay mutation gốc.

### Test 10 — Multi-region conflict

Hai regions update cùng key khi mạng đứt. Khi reconnect, mọi replicas hội tụ, nhưng UI/API vẫn phải minh bạch về conflict outcome.

### Test 11 — Backfill vs live CDC

CDC v12 tới rồi backfill v8. Version guard phải giữ v12.

### Test 12 — CAS race

Hai clients cùng cập nhật từ version 7, một trong hai phải nhận conflict/failed condition theo contract.

### Test 13 — Cross-field invariant

Merge riêng `startDate` và `endDate` nhưng không được tạo interval sai.

### Test 14 — External payment

Hai vùng có local write success; bảo đảm không báo hai payments thành công chỉ nhờ LWW reconciliation về sau.

### Test 15 — Crash và retry

Commit xảy ra nhưng ACK mất; retry cùng operation ID không gây duplicate side effect.

## 39. Tình huống nghiệp vụ A: hồ sơ sửa ở hai thiết bị

User đổi `city` trên điện thoại offline và `phone` trên laptop online.

### 39.1. Document LWW

Bản laptop có timestamp mới hơn nên thắng toàn document. City đổi trên điện thoại bị mất.

### 39.2. Field LWW

City và phone có versions riêng; có thể giữ cả hai thay đổi.

### 39.3. OCC

Nếu backend trả ETag/version, điện thoại sau reconnect nhận conflict rồi có thể reload và cập nhật city trên bản mới.

### 39.4. Khi nào chọn cách nào?

- Document LWW: ít xung đột, chấp nhận silent overwrite.
- Field merge: fields tương đối độc lập.
- OCC/manual merge: quan trọng không làm mất chỉnh sửa.
- CRDT: cộng tác/offline liên tục có operations merge được.

Không có một policy tối ưu cho mọi hồ sơ.

## 40. Tình huống nghiệp vụ B: số lượt thích và số tồn kho

### 40.1. Lượt thích

East tăng tổng từ 100 lên 101, West cũng tăng 100 lên 101.

LWW chọn một giá trị 101, làm mất một lượt. Nếu cần đếm cả hai, dùng atomic increments tại authority, event aggregation hoặc counter CRDT phù hợp.

### 40.2. Tồn kho

Còn một sản phẩm. Hai vùng cùng giảm từ 1 về 0 rồi LWW chọn một mutation. Dù final stock=0, **hai đơn đã có thể được xác nhận**.

Cần authoritative reservation, CAS/transaction hoặc quota được cấp trước; LWW chỉ thống nhất final numeric value không đủ.

### 40.3. Không giả định cộng hai counters luôn đúng

Nếu event được giao lại, cộng hai lần cũng có thể sai. CRDT/event aggregation cần unique operations hoặc semantics chống duplicate theo thiết kế.

## 41. Tình huống nghiệp vụ C: quyền bị thu hồi

Admin thu hồi quyền U42:

```text
T0: permission=ADMIN, version=10
T1: revoke permission, version=11
T2: replica offline vẫn còn ADMIN
T3: stale read phục vụ API nhạy cảm
```

Nếu hệ sử dụng raw LWW timestamp không bảo vệ version/revocation, API có thể cấp quyền sai.

Hướng xử lý:

- Dùng authoritative permission check cho hành động quan trọng.
- Dùng monotonic revocation epoch/token version.
- Fail closed khi không xác minh được.
- Không cho cache TTL quá hợp đồng an ninh.
- Không coi client timestamp là nguồn quyền.

Dữ liệu cuối cùng hội tụ về REVOKED **không bù được một lần truy cập trái phép đã xảy ra**.

## 42. Tình huống nghiệp vụ D: search index nhận event sai thứ tự

Source:

```text
Order O100 v10 = CREATED
Order O100 v11 = PAID
Order O100 v12 = CANCELLED
```

Delivery tới search:

```text
v12 -> v10 -> v11
```

Một projector blind upsert theo arrival order sẽ kết thúc ở PAID, sai so với source CANCELLED.

Dùng source version guard:

```text
On incoming event:
  if event.version <= stored.version:
      ignore
  else:
      write state and version atomically
```

Nếu event là DELETE v12, phải giữ tombstone/version marker để v10 không tạo lại document sau khi delete.

## 43. Khi nào LWW là lựa chọn hợp lý?

LWW phù hợp hơn khi:

- Dữ liệu có một value/register độc lập.
- Concurrent updates hiếm hoặc mất một update chấp nhận được.
- Product contract công khai quy tắc winner.
- Không có invariant tiền/quota/quyền phụ thuộc cả hai mutations.
- Timestamp/version source đáng tin và có total-order tie-break.
- Dữ liệu chủ yếu là preference, trạng thái hiển thị hoặc cache.
- Có cách giải thích conflict cho người dùng khi cần.
- Có version/tombstone retention phù hợp với offline/replay window.

### 43.1. LWW không phù hợp nếu

- Phải giữ mọi increment.
- Phải merge nhiều edits đồng thời.
- Chỉ một client được phép claim một resource.
- Hai field có invariant chéo.
- Cần thứ tự theo thời gian thực và physical clocks không đáp ứng.
- Revoke/authorization không được phép trễ.
- Data loss dù một mutation là không chấp nhận được.
- Có external side effects đã thực hiện trước conflict resolution.

**Một quy tắc merge đơn giản thường tốt cho tính hội tụ, nhưng sự đơn giản ấy có thể đánh đổi bằng việc mất ý định người dùng.**

## 44. Quy trình thiết kế policy LWW

### Bước 1 — Xác định scope

LWW theo key, field, document, set element, partition hay stream? Không để policy mơ hồ.

### Bước 2 — Chọn nguồn thứ tự

Client event time, server ingest time, HLC, commit sequence, aggregate version hay thế hệ quyền ghi?

### Bước 3 — Định nghĩa total order

Bao gồm tie-break và xử lý equal version conflicting payload.

### Bước 4 — Xác định business invariants

Nếu hậu quả của lost update không được chấp nhận, chọn CAS/transaction/merge khác.

### Bước 5 — Xác định delete và TTL

Tombstone version, retention, offline window và replay cần được thiết kế cùng nhau.

### Bước 6 — Xác định conflict visibility

Có thông báo “một chỉnh sửa của bạn đã bị thay thế” không? Có conflict history để khôi phục không?

### Bước 7 — Xử lý replay và backfill

Giữ source version/event ID; không gắn timestamp mới cho dữ liệu cũ một cách vô thức.

### Bước 8 — Kiểm tra multi-region

Region nào có quyền phát version? Conditional write có phạm vi cục bộ hay toàn cục? Có nên dùng authority duy nhất hoặc quota phân bổ trước không?

### Bước 9 — Đo kiểm

Clock skew, tie collisions, data loss, convergence lag, stale reads, tombstone resurrection và business conflicts.

### Bước 10 — Runbook phục hồi

Có đường sửa wrong winner, quarantine future timestamp, rebuild projection và reconcile external effects.

## 45. Bài tập thực hành

### Bài tập 1 — Chọn winner

A ghi value=X, ts=100. B ghi value=Y, ts=120.

**Câu hỏi:** Với policy max timestamp, winner là gì?

**Gợi ý:** Y.

### Bài tập 2 — Arrival order

B(ts=120) đến trước A(ts=100).

**Câu hỏi:** A tới sau có thắng không?

**Gợi ý:** Không, nếu merge dựa trên timestamp.

### Bài tập 3 — Clock skew

X thao tác lúc 12:00:00 nhưng clock nhanh 20 giây; Y thao tác lúc 12:00:05 với clock đúng.

**Câu hỏi:** Physical LWW chọn ai?

**Gợi ý:** Có thể chọn X dù Y thao tác sau theo thời gian thực.

### Bài tập 4 — Event vs ingest

E1 eventTime=08:00 ingestTime=12:00; E2 eventTime=10:00 ingestTime=10:01.

**Câu hỏi:** Winner theo mỗi nguồn time?

**Gợi ý:** Event time chọn E2; ingest time chọn E1.

### Bài tập 5 — Tie-break

A=(ts=100, writer=a), B=(ts=100, writer=b). Policy so lexicographic writerId.

**Câu hỏi:** Ai thắng, và điều đó chứng minh điều gì?

**Gợi ý:** B thắng theo rule, không chứng minh B thao tác sau.

### Bài tập 6 — Duplicate event

E100 được replay ba lần.

**Câu hỏi:** Vì sao idempotency/version ổn định giúp bảo vệ?

**Gợi ý:** Merge lặp với cùng event/version không đổi winner và không nhân đôi side effect.

### Bài tập 7 — Same version, different payload

Hai messages cùng `(timestamp=100, writer=a)` nhưng values khác.

**Câu hỏi:** Nên làm gì?

**Gợi ý:** Integrity conflict hoặc deterministic documented policy; không tùy thứ tự arrival.

### Bài tập 8 — Lamport clock

A send message ở L=4. B đang L=7, nhận message.

**Câu hỏi:** B cập nhật thành bao nhiêu theo quy tắc cơ bản?

**Gợi ý:** `max(7,4)+1=8`.

### Bài tập 9 — Vector version

A={east:2, west:0}, B={east:1, west:1}.

**Câu hỏi:** Phiên bản nào dominates?

**Gợi ý:** Không có; chúng có thể concurrent.

### Bài tập 10 — HLC

Hai events có physical time bằng nhau nhưng logical components khác.

**Câu hỏi:** Thành phần logical giúp gì?

**Gợi ý:** Phân biệt thứ tự trong clock protocol, giảm collisions.

### Bài tập 11 — Cassandra USING TIMESTAMP

Ứng dụng truyền epoch milliseconds vào tham số được hiểu là microseconds.

**Câu hỏi:** Lỗi gì có thể xảy ra?

**Gợi ý:** Timestamp bị sai đơn vị, khiến ordering/TTL/audit hỏng.

### Bài tập 12 — Cassandra per-cell

A sửa `city`, B sửa `phone`.

**Câu hỏi:** Vì sao có thể giữ cả hai fields?

**Gợi ý:** Conflict resolution theo cell có thể độc lập, tùy mutation/schema.

### Bài tập 13 — Quorum không làm CAS

Hai clients đọc `seat.owner=null`, rồi regular writes CL=QUORUM.

**Câu hỏi:** Có chắc chỉ một client được CONFIRMED không?

**Gợi ý:** Không, cần conditional mutation/authority.

### Bài tập 14 — Tombstone

DELETE ts=200, old INSERT ts=100 đến muộn.

**Câu hỏi:** Khi tombstone còn tồn tại, old value có được phục hồi không?

**Gợi ý:** Không theo reconciliation phù hợp.

### Bài tập 15 — Clock tương lai

Client ghi timestamp năm 2099 lên record năm 2026.

**Câu hỏi:** Vì sao updates tiếp theo bị kẹt?

**Gợi ý:** Max timestamp policy cho bản tương lai thắng; cần validation/authority.

### Bài tập 16 — TTL replay

Session TTL 1 giờ được replay sau 3 giờ.

**Câu hỏi:** Có nên khởi động lại TTL một giờ từ thời điểm replay?

**Gợi ý:** Không nếu đó là mutation gốc; phải giữ expiration semantics.

### Bài tập 17 — Document lost update

A sửa city, B sửa phone từ cùng snapshot, B full replace sau.

**Câu hỏi:** Điều gì mất?

**Gợi ý:** A có thể mất city edit; partial update/OCC/field merge có thể phù hợp hơn.

### Bài tập 18 — LWW element set

ADD X ts=10, REMOVE X ts=20, ADD X ts=30.

**Câu hỏi:** Với max timestamp, X có còn trong set không?

**Gợi ý:** Có.

### Bài tập 19 — Add/remove tie

ADD và REMOVE cùng timestamp.

**Câu hỏi:** Có thể để mỗi replica tự chọn không?

**Gợi ý:** Không; phải định nghĩa deterministic add-wins/remove-wins/tie-break.

### Bài tập 20 — View counter

East và West đều tăng từ 100 lên 101 rồi LWW hội tụ 101.

**Câu hỏi:** Mất gì?

**Gợi ý:** Một increment; cần counter CRDT/atomic increment/event aggregation.

### Bài tập 21 — Inventory

Còn một vé, hai region cùng bán và LWW chọn một order.

**Câu hỏi:** Final state một owner có làm nghiệp vụ đúng không?

**Gợi ý:** Không, vì hai khách có thể đã được xác nhận.

### Bài tập 22 — MongoDB version

Hai clients cùng update với filter `{version:7}`.

**Câu hỏi:** Lợi ích của filter?

**Gợi ý:** Chỉ request hợp lệ với version hiện tại được áp dụng; client stale nhận conflict.

### Bài tập 23 — DynamoDB MREC

Hai regions cùng nhận conditional claim cục bộ trong mô hình eventual replication.

**Câu hỏi:** Có tự giữ global uniqueness không?

**Gợi ý:** Không thể suy; phải xem contract multi-region và authority.

### Bài tập 24 — Projection out-of-order

Search nhận order v12 rồi v10.

**Câu hỏi:** Dùng rule nào?

**Gợi ý:** Atomic source-version guard, giữ v12.

### Bài tập 25 — Delete resurrected

Projection xóa v12 và xóa luôn metadata version, sau đó UPSERT v11 đến.

**Câu hỏi:** Vì sao record quay lại?

**Gợi ý:** Sink quên tombstone/version marker; giữ guard theo retention policy.

### Bài tập 26 — Business field invariant

`startDate` và `endDate` được merge từng field làm `startDate>endDate`.

**Câu hỏi:** Giải pháp?

**Gợi ý:** Merge theo aggregate/transaction và validate invariant.

### Bài tập 27 — Multisource version

Order v12, Inventory v14.

**Câu hỏi:** Có thể so 14>12 để kết luận inventory mới hơn order theo toàn hệ không?

**Gợi ý:** Không, versions ở hai aggregates không cùng scope.

### Bài tập 28 — Fencing generation

Worker A generation=41 hết lease, B được cấp 42. A thức dậy gửi write.

**Câu hỏi:** Ai chặn A?

**Gợi ý:** Sink kiểm tra generation nguyên tử, từ chối stale token.

### Bài tập 29 — Monitoring

Có nhiều mutations bị discard nhưng dữ liệu vẫn hội tụ.

**Câu hỏi:** Có nên coi hệ hoàn toàn khỏe?

**Gợi ý:** Chưa; cần điều tra timestamp skew, lost user edits và correctness.

### Bài tập 30 — Thiết kế cuối

Một ứng dụng có hồ sơ, giỏ hàng, inventory, payment, search và analytics.

**Yêu cầu:** Chọn phần có thể dùng LWW, phần nên dùng merge/CAS/ledger, và cách xử lý khi mạng bị chia cắt.

**Gợi ý:** Preferences có thể LWW; cart có thể merge theo operations; inventory cần authoritative reservation; payment cần idempotency/ledger; search/analytics có thể dùng version-aware asynchronous projections.

## 46. Checklist áp dụng vào production

- [ ] Đã nêu LWW áp dụng cho field, document, element hay event.
- [ ] Đã xác định timestamp source, time unit và precision.
- [ ] Đã phân biệt event time, ingest time và commit order.
- [ ] Không tin client clock cho dữ liệu cần security/financial correctness.
- [ ] Đã kiểm soát clock skew và future timestamps.
- [ ] Có deterministic total-order tie-break.
- [ ] Có chính sách khi cùng version nhưng payload khác.
- [ ] Merge idempotent và không phụ thuộc arrival order.
- [ ] Có source version/event ID khi replay.
- [ ] Đã đánh giá lost updates trong full-document replacement.
- [ ] Đã chọn CAS/transaction khi không được âm thầm bỏ mutation.
- [ ] Không dùng regular QUORUM/LWW thay atomic uniqueness claim.
- [ ] Đã hiểu delete/tombstone/TTL và retention window.
- [ ] Có repair/backfill/runbook cho offline replica dài ngày.
- [ ] Có version/tombstone guard ở search/cache projections.
- [ ] Có kiểm tra multi-region consistency mode đúng dịch vụ.
- [ ] Đã xác định quyền ghi và generation/epoch khi cần fencing.
- [ ] Có idempotency cho external side effects.
- [ ] Có UX thông báo local pending/conflict khi cần.
- [ ] Có metrics conflict, clock skew, discards, convergence lag.
- [ ] Đã kiểm thử đảo thứ tự, duplicate, tie, future timestamp.
- [ ] Đã kiểm thử multi-region partition và restore snapshot cũ.
- [ ] Business invariants quan trọng được bảo vệ tại authority.
- [ ] Không coi dữ liệu hội tụ là bằng chứng đã xử lý đúng mọi giao dịch.

## 47. Tổng kết

**Last-write-wins** là chính sách giải quyết xung đột bằng cách chọn một bản ghi/mutation có thứ tự lớn nhất. Nó đơn giản, có thể hội tụ độc lập với thứ tự giao message nếu có **total-order version và tie-break deterministic**.

Nhưng “last” không có nghĩa phổ quát:

- **Physical timestamp** dễ bị clock skew, future timestamps và collisions.
- **Client event time** phản ánh một dạng ý định của người dùng nhưng có thể không đáng tin.
- **Ingest/processing time** phụ thuộc mạng và thời điểm event tới.
- **Commit sequence** tạo thứ tự trong phạm vi một authority, không tự là global sequence.
- **Lamport/HLC** giúp diễn đạt thứ tự logic/nhân quả hơn nhưng không tự đảm bảo real-time linearizability.
- **Version vectors** có thể phát hiện concurrent updates thay vì âm thầm chọn một winner.
- **CAS/transactions** bảo vệ điều kiện khi ghi, còn **domain merge/CRDT** giữ hoặc kết hợp dữ liệu theo semantics khác.

Các hệ NoSQL áp dụng các cơ chế ở **những phạm vi khác nhau**: Cassandra có per-cell timestamp reconciliation, DynamoDB global tables eventual có conflict resolution theo LWW trong mode liên quan, Cosmos DB có conflict policies, Firestore có semantics offline conflicts, còn MongoDB/Redis single-primary replication không nên bị gọi nhầm thành multi-master LWW thuần túy.

Đặc biệt, LWW không thay được authority khi **không được bán trùng, trừ tiền sai, mất increment hoặc cho quyền truy cập đã bị thu hồi**. Một hệ hội tụ dữ liệu về sau chưa chắc đã đúng với những thành công từng công bố trước đó.

**Nguyên tắc cuối cùng:** *Hãy chọn nguồn timestamp và quy tắc winner theo ý nghĩa dữ liệu, không theo sự tiện lợi của một cột updatedAt. Khi một update không được phép biến mất, hãy phát hiện hoặc ngăn xung đột bằng version/CAS/transaction/merge phù hợp thay vì mặc nhiên để Last-write-wins âm thầm quyết định.*

