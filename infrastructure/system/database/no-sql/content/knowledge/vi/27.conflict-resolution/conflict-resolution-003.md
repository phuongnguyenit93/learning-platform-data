# Đồng hồ máy, sai lệch thời gian và giới hạn xác định thứ tự thực tế

## 1. Tình huống mở đầu: cập nhật sau lại bị cập nhật trước ghi đè

Một hệ thống hồ sơ người dùng chạy ở hai vùng địa lý. Cả Region A và Region B đều có thể nhận thao tác sửa tên hiển thị. Để giải quyết xung đột, hệ thống chọn bản ghi có **timestamp lớn hơn** theo quy tắc Last-Write-Wins (LWW).

Giả sử mọi thời điểm thực bên dưới chỉ là ví dụ minh họa:

| Sự kiện | Thời điểm thực | Đồng hồ máy tạo timestamp | Giá trị |
| --- | --- | --- | --- |
| Write A hoàn tất | 10:00:00 | 10:00:08 (máy A chạy nhanh 8 giây) | `"An"` |
| Write B bắt đầu sau A | 10:00:02 | 09:59:57 (máy B chạy chậm 5 giây) | `"Anna"` |

Theo thứ tự thực, B xảy ra **sau** A. Nhưng nếu dùng timestamp vật lý do hai máy cấp:

```text
Timestamp A = 10:00:08
Timestamp B = 09:59:57

LWW chọn A vì timestamp A lớn hơn.
Kết quả cuối: "An" — dù B được người dùng thực hiện sau.
```

Không có gì bảo đảm hai máy đồng hồ chạy giống nhau tuyệt đối, và **giá trị timestamp lớn hơn không chứng minh thao tác đã xảy ra muộn hơn trong thực tế**.

Bài học này giải thích một giới hạn cốt lõi của cơ sở dữ liệu NoSQL phân tán: **đồng hồ vật lý đo thời gian theo độ chính xác hữu hạn; thứ tự nhân quả, thứ tự commit và thứ tự toàn cục là những khái niệm khác nhau**.

## 2. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Phân biệt **wall-clock time**, **monotonic time** và **logical clock**.
2. Giải thích **clock offset**, **clock skew**, **clock drift**, độ phân giải và khoảng bất định thời gian.
3. Phân biệt **sự kiện xảy ra trước theo thời gian thực** với **quan hệ nhân quả happened-before** và **thứ tự commit**.
4. Chỉ ra vì sao timestamp từ hai máy không đủ để xác định mọi xung đột bằng LWW.
5. Hiểu Lamport clocks, vector clocks, Hybrid Logical Clocks (HLC) và giới hạn của từng cách.
6. Hiểu vai trò của leader, consensus log, MVCC, CAS, version và fencing token.
7. Tránh lỗi do timestamp tương lai, TTL, lease, clock jump và event đến ngược thứ tự.
8. Biết cách diễn giải các tính năng liên quan trong MongoDB, Cassandra, DynamoDB, Redis và những pipeline CDC/search.
9. Thiết kế chính sách giải quyết xung đột theo bất biến nghiệp vụ thay vì luôn dùng “bản có ngày giờ mới nhất”.
10. Lập kế hoạch đo clock offset, thử nghiệm lệch giờ, theo dõi replication và đối soát.

## 3. Ba câu hỏi khác nhau về “thứ tự”

Khi một ứng dụng nói “bản cập nhật mới nhất”, phải hỏi:

1. **Thứ tự thời gian vật lý:** sự kiện nào xảy ra sớm hoặc muộn theo thời gian thực?
2. **Thứ tự nhân quả:** sự kiện nào được tạo ra sau khi đã biết kết quả sự kiện trước?
3. **Thứ tự quyết định/commit:** hệ thống đã phân xử các thao tác theo thứ tự nào?

Ba thứ tự có thể khác nhau.

Ví dụ hai người cùng sửa một tài liệu từ hai thiết bị, không ai thấy sửa đổi của người kia. Các thao tác có thể **đồng thời về mặt nhân quả** dù một máy gắn timestamp lớn hơn.

Ngược lại, nếu người dùng nhận xác nhận A hoàn tất rồi mới khởi tạo B, hai thao tác có một quan hệ **theo thời gian thực rõ ràng**, nhưng một cơ chế LWW dựa trên đồng hồ không đồng bộ vẫn có thể xếp ngược.

### 3.1. Cùng một request có nhiều mốc thời gian

```text
t0: Client tạo command
t1: API gateway nhận command
t2: Database coordinator nhận
t3: Replica primary ghi log
t4: Quorum xác nhận commit
t5: Client nhận success
t6: CDC consumer nhận event
t7: Search index làm event visible
```

Một timestamp có thể là `clientCreatedAt`, `serverReceivedAt`, `committedAt`, `indexedAt`, hoặc `displayedAt`. Chúng **không thể thay thế nhau**.

Gắn timestamp ở gateway **không chứng minh** commit xảy ra theo thứ tự gateway nhận; gắn timestamp ở search index chỉ phản ánh tiến trình indexing.

## 4. Wall-clock time: đồng hồ lịch của máy

**Wall clock** trả thời gian lịch, thường được biểu diễn bằng mốc UTC, ví dụ:

```text
2026-11-14T10:00:00.123Z
```

Nó hữu ích để:

- Ghi thời điểm nghiệp vụ, hạn thanh toán và ngày đặt hàng.
- Lập báo cáo theo giờ/ngày.
- Truy vết request giữa hệ thống.
- Xác định lịch vận hành, TTL và ngày hết hạn.
- Hiển thị thời gian cho người dùng.

Trong Java:

```java
import java.time.Instant;

Instant submittedAt = Instant.now();
```

Nhưng `Instant.now()` đọc clock do môi trường cung cấp; **không phải một global sequencer**. Giá trị có thể lệch so với máy khác hoặc nhảy khi đồng hồ được điều chỉnh.

### 4.1. Wall clock không bắt buộc tăng đơn điệu

Một chuỗi đo có thể là:

```text
12:00:00.900
12:00:01.000
11:59:59.800  <- đồng hồ bị chỉnh lùi
12:00:00.100
```

Dù code gọi `Instant.now()` sau, giá trị mới có thể nhỏ hơn giá trị trước.

Hệ điều hành/dịch vụ đồng bộ có thể **slew** (điều chỉnh tốc độ) hoặc **step** (nhảy mốc); hành vi tùy hệ thống và cấu hình. Không dựa vào giả định mọi đồng hồ máy tăng đúng một mili-giây cho mỗi mili-giây thực tế.

### 4.2. UTC và múi giờ không chữa clock skew

Lưu thời gian ở UTC giúp tránh nhầm chuyển múi giờ hoặc DST khi so sánh. Nhưng:

```text
Host A: UTC thật + 800 ms
Host B: UTC thật - 700 ms
```

đều có thể hiển thị UTC mà vẫn lệch nhau 1,5 giây.

**Cùng timezone không có nghĩa cùng thời điểm vật lý chính xác.**

## 5. Monotonic clock: đo khoảng thời gian trôi qua

**Monotonic clock** phục vụ tính thời lượng trong một tiến trình/hệ điều hành. Nó không phải thời gian lịch, và thường được thiết kế để không nhảy ngược vì một thao tác sửa wall clock.

Trong Java:

```java
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public class ClockExample {
    public static void main(String[] args) {
        Instant createdAt = Instant.now();     // Mốc lịch để ghi log

        long started = System.nanoTime();      // Mốc tương đối
        doWork();
        long elapsed = System.nanoTime() - started;

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsed);

        System.out.println("Created: " + createdAt);
        System.out.println("Elapsed ms: " + elapsedMs);
    }

    private static void doWork() {
        // Thao tác minh họa.
    }
}
```

Giá trị của `System.nanoTime()`:

- Chỉ có ý nghĩa khi **lấy hiệu các lần đọc từ cùng nguồn clock thích hợp**.
- Không có ý nghĩa như một Unix timestamp.
- Không nên so trực tiếp giá trị tuyệt đối giữa hai JVM/máy.
- Không cấp thứ tự commit toàn cầu.

### 5.1. Deadline nên dựa trên elapsed time

Ví dụ không tốt:

```java
long start = System.currentTimeMillis();
// Sau đó...
long elapsedMs = System.currentTimeMillis() - start;
```

Nếu wall clock bị chỉnh, `elapsedMs` có thể âm hoặc phình to.

Tốt hơn cho elapsed duration:

```java
long started = System.nanoTime();
// Sau đó...
long elapsedNanos = System.nanoTime() - started;
```

Dùng monotonic time để đo timeout **cục bộ**, nhưng deadline truyền qua nhiều tiến trình cần thiết kế giao thức rõ (duration budget, absolute deadline có xử lý clock skew, hoặc do từng tầng quy đổi). Không gửi một giá trị `nanoTime()` thô cho máy khác.

## 6. Offset, skew, drift, precision và uncertainty

Các thuật ngữ thường bị trộn lẫn:

| Thuật ngữ | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **Clock offset** | Chênh lệch một clock so với mốc tham chiếu tại một thời điểm | A nhanh hơn chuẩn 200 ms |
| **Clock skew** | Độ lệch giữa hai clocks, thường xét tại cùng một thời điểm | A nhanh 200 ms, B chậm 300 ms ⇒ lệch nhau 500 ms |
| **Clock drift** | Tốc độ clock lệch, khiến offset thay đổi theo thời gian | Một clock chạy nhanh vài phần triệu |
| **Precision/resolution** | Mức hạt nhỏ nhất được biểu diễn/quan sát | Timestamp chỉ đến millisecond |
| **Accuracy** | Mức gần thời gian thực | Timestamp sai 80 ms |
| **Uncertainty/error bound** | Khoảng có thể chứa thời gian thực theo giả định đo/sync | Mốc đọc ±10 ms |
| **Latency** | Thời gian request/message đi qua hệ | RPC RTT 120 ms |
| **Replication lag** | Độ trễ bản sao bắt kịp nguồn | Follower chậm 3 s |

**Network latency không đồng nhất với clock skew**, mặc dù network delay ảnh hưởng khả năng đồng bộ đồng hồ và cách timestamp được quan sát.

### 6.1. Ví dụ drift tích lũy

Giả sử một oscillator nhanh hơn chuẩn **20 ppm** (20 phần triệu), và không có cơ chế hiệu chỉnh.

Độ lệch tăng xấp xỉ:

\[
\Delta t \approx T\times20/1.000.000
\]

Sau một giờ (`T=3600 s`):

\[
\Delta t \approx 3600\times20/1.000.000=0,072s
\]

Tức khoảng **72 ms**. Sau thời gian dài không đồng bộ, sai lệch có thể lớn lên; con số ppm chỉ là ví dụ, không phải giới hạn của mọi máy.

### 6.2. Độ phân giải không phải độ chính xác

Một API xuất thời gian tới nanosecond **không chứng minh clock thật sự chính xác tới nanosecond**.

Ví dụ:

```text
2026-11-14T10:00:00.123456789Z
```

có chín chữ số phần giây, nhưng nguồn clock có thể chỉ cập nhật với độ phân giải thấp hơn hoặc lệch hàng chục millisecond.

## 7. Đồng bộ qua NTP/PTP giúp ích gì và không giúp gì?

**NTP** và **PTP** giúp các máy ước lượng thời gian chuẩn và hiệu chỉnh clock. Trong môi trường phù hợp, PTP có thể hỗ trợ yêu cầu chính xác cao hơn nhờ đồng bộ phần cứng và thiết kế mạng thích hợp.

Tuy nhiên:

- Kết quả có thể bị ảnh hưởng bởi asymmetric network delay.
- Clock source và đường mạng có thể gặp lỗi.
- VM/container kế thừa ảnh hưởng từ host/hypervisor.
- Clock có thể thay đổi sau restart, migration hoặc cấu hình sai.
- Có thể xuất hiện giai đoạn clock đang được chỉnh.
- Monitoring cần xem sync health, không chỉ dịch vụ còn chạy.

**Đồng bộ tốt làm sai lệch nhỏ hơn, không tự cung cấp thứ tự nhân quả hoặc transaction serializable.**

### 7.1. Khi nào nên cảnh báo clock sync?

Ví dụ policy nội bộ có thể định nghĩa:

```text
Clock sync state = unsynchronized
OR observed offset > operation-specific threshold
OR uncertainty bound not trustworthy
```

Ngưỡng cần phù hợp workload. Hệ giao dịch cần kiểm soát chặt hơn hệ log tham khảo; không có một ngưỡng millisecond chung cho mọi NoSQL.

### 7.2. Leap seconds và clock adjustments

Các nền tảng có thể xử lý leap second bằng step/smear hoặc chiến lược khác. Khi các máy áp dụng policy khác nhau, phép so sánh timestamp sát một sự kiện hiệu chỉnh có thể khó diễn giải.

Không giả định mọi timestamp Unix/UTC từ mọi môi trường có cùng cách xử lý leap second; nên chuẩn hóa nguồn giờ, định dạng và chính sách ở phạm vi vận hành.

## 8. Timestamp không tự cho biết thời điểm commit

Một event có thể được timestamp tại nhiều nơi:

```text
Client emits event     : 10:00:01.200
API receives request   : 10:00:01.250
Coordinator assigns ts : 10:00:01.270
Leader appends WAL     : 10:00:01.280
Quorum commits         : 10:00:01.430
CDC consumer receives  : 10:00:03.000
Index refresh visible  : 10:00:04.000
```

Đó là các **mốc khác nhau** và còn có sai số clock giữa các thành phần.

Một field `updatedAt` do client gửi có thể:

- Chậm hoặc nhanh hơn giờ thực.
- Bị cố tình sửa.
- Là timestamp **thời điểm người dùng chỉnh offline**, không phải thời điểm server chấp nhận.
- Được gửi lại ở lần retry sau.
- Đến server sau một event có timestamp lớn hơn.

Một field `serverReceivedAt` chỉ nói **một server** đã nhận vào lúc nó đọc clock; không tự là thứ tự commit trên các shards.

## 9. Quan hệ nhân quả happened-before

Trong hệ phân tán, **happened-before** (ký hiệu \(a\rightarrow b\)) mô tả một quan hệ thứ tự nhân quả:

1. Hai sự kiện trong cùng một tiến trình: sự kiện trước trong thứ tự thực thi xảy ra trước.
2. Nếu sự kiện a gửi một message được nhận ở b, thì \(a\rightarrow b\).
3. Quan hệ này có tính bắc cầu: nếu \(a\rightarrow b\) và \(b\rightarrow c\), thì \(a\rightarrow c\).

Nếu không suy được \(a\rightarrow b\) hoặc \(b\rightarrow a\) từ các quan hệ đó, hai sự kiện **concurrent về mặt nhân quả**.

### 9.1. Ví dụ có quan hệ nhân quả

```text
Service A:
  Commit OrderCreated
  Send OrderCreated event

Service B:
  Receive OrderCreated
  Generate InvoiceCreated
```

Trong luồng đó:

\[
OrderCreated\rightarrow InvoiceCreated
\]

B không thể tạo Invoice dựa trên event trước khi nhận event phù hợp, nếu hệ giữ đúng phụ thuộc.

### 9.2. Ví dụ concurrent

Hai thiết bị offline cùng sửa tên hiển thị:

```text
Device A: rename "An"
Device B: rename "Anna"
```

Không thiết bị nào nhận cập nhật của thiết bị kia. Hai thao tác có thể **concurrent**, kể cả khi wall timestamps khác nhau.

Nếu nghiệp vụ cần giữ cả hai sửa đổi hoặc hỏi người dùng, LWW có thể làm mất thông tin.

### 9.3. Chuyện gì không thể suy từ timestamp?

Nếu `timestamp(a) < timestamp(b)`, **không đủ** để kết luận \(a\rightarrow b\). Có thể đồng hồ A và B lệch, hoặc hai thao tác độc lập.

Ngược lại, nếu biết \(a\rightarrow b\) từ luồng message/session, có thể dùng quan hệ nhân quả đó để giữ thứ tự xử lý dù wall timestamps bị đảo.

## 10. Partial order, total order và serial order

Một **partial order** có thể để một số cặp sự kiện không so sánh được. Causal order là ví dụ.

Một **total order** đặt mọi sự kiện vào một thứ tự hoàn chỉnh, kể cả các sự kiện độc lập. Nhưng total order đó có thể được tạo bằng một tie-breaker tùy ý, **không phải tái hiện “sự thật thời gian vật lý”**.

Ví dụ:

```text
A=(logicalTime=5, nodeId="A")
B=(logicalTime=5, nodeId="B")
```

So theo `(logicalTime, nodeId)` cho A trước B, nhưng không chứng minh A đã xảy ra trước theo thời gian thực.

### 10.1. Bốn thuộc tính hay nhầm

| Thuộc tính | Điều được bảo đảm ở mức khái niệm |
| --- | --- |
| **Total order** | Mọi cặp sự kiện đều được xếp theo một thứ tự |
| **Causal order** | Nếu a gây ảnh hưởng tới b thì a trước b |
| **Linearizability** | Mỗi thao tác có thể xem như xảy ra tại một điểm giữa invocation và response, bảo toàn thứ tự real-time của các thao tác không chồng lấn trên đối tượng |
| **Strict serializability** | Transaction serializable đồng thời tôn trọng thứ tự real-time giữa các transaction không chồng lấn |

Một hệ có thể tạo total order theo node ID nhưng **không linearizable**. Một thứ tự transaction serializable **không nhất thiết** tôn trọng real-time nếu không có điều kiện strong/external consistency tương ứng.

## 11. Lamport logical clocks

**Lamport clock** là bộ đếm logic giúp bảo đảm: nếu \(a\rightarrow b\), thì \(L(a)<L(b)\).

Quy tắc đơn giản:

1. Trước một sự kiện cục bộ/gửi message: tăng counter.
2. Gửi kèm counter.
3. Khi nhận message với counter `m`, đặt:

\[
L_{\text{new}}=\max(L_{\text{local}},m)+1
\]

### 11.1. Ví dụ

```text
Process A:
  A1: L=1
  A2: gửi message, L=2

Process B:
  B1: L=1
  nhận A2 với L=2 -> L=3
  B2: L=4
```

Ta biết:

\[
A2\rightarrow B2 \implies 2<4
\]

Nhưng chiều ngược **không đúng nói chung**:

\[
L(a)<L(b)\not\Rightarrow a\rightarrow b
\]

Hai sự kiện concurrent vẫn có thể có số Lamport khác nhau.

### 11.2. Lamport clock giải quyết được gì?

- Giữ thứ tự không đảo quan hệ nhân quả đã quan sát.
- Là cơ sở thiết kế một số protocol ordering.
- Có thể kết hợp node ID để tạo total order xác định.

### 11.3. Lamport clock không giải quyết được gì?

- Không cho biết chính xác bao nhiêu millisecond đã trôi qua.
- Không nhận diện đầy đủ mọi cặp concurrent chỉ từ một số nguyên scalar.
- Không cung cấp commit consensus nếu không có giao thức đồng thuận.
- Không bảo vệ invariant nhiều key hay business idempotency.

## 12. Vector clocks: nhận biết cập nhật concurrent

**Vector clock** lưu một vector counter theo các actor/replica tham gia. Nó có thể so sánh quan hệ nhân quả trong mô hình tương ứng.

Giả sử hai replica A, B, vector `(counterA, counterB)`:

```text
Khởi đầu:
  A = [0,0]
  B = [0,0]

A sửa dữ liệu offline:
  vA = [1,0]

B sửa dữ liệu offline:
  vB = [0,1]
```

So sánh component-wise:

- `[1,0]` **không nhỏ hơn hoặc bằng** `[0,1]`.
- `[0,1]` cũng **không nhỏ hơn hoặc bằng** `[1,0]`.

Vì vậy hai version **concurrent** về mặt nhân quả trong mô hình actor tương ứng.

### 12.1. Khi một version phụ thuộc version trước

B nhận bản của A rồi chỉnh tiếp:

```text
A tạo vA = [1,0]
B nhận [1,0]
B chỉnh -> [1,1]
```

Ta có:

\[
[1,0] < [1,1]
\]

Bản `[1,1]` kế thừa lịch sử của `[1,0]`.

### 12.2. Quy tắc so sánh

Với hai vector `v`, `w` cùng tập actor:

\[
v\leq w\iff \forall i,\;v_i\leq w_i
\]

Và:

\[
v<w\iff v\leq w\land \exists j,\;v_j<w_j
\]

Nếu không có `v<w`, không có `w<v`, và `v != w`, hai versions concurrent.

### 12.3. Merge vector clocks

Khi hợp nhất thông tin nhân quả:

\[
merge(v,w)_i=\max(v_i,w_i)
\]

Ví dụ:

```text
vA = [2,0]
vB = [0,3]

merge = [2,3]
```

Đây là **merge metadata về quan hệ nhân quả**, không tự trả lời cách hợp nhất hai giá trị `nickname` hoặc hai mức tồn kho.

### 12.4. Hạn chế

- Vector có thể tăng theo số actor/replica.
- Membership động và client offline làm quản lý vector phức tạp.
- Có các biến thể như version vectors, dotted version vectors để giảm/điều chỉnh metadata.
- Cần xác định actor identity ổn định và quy tắc compaction.
- Cần chính sách giải quyết conflict khi hai versions concurrent.

Vector clock có thể **phát hiện xung đột**, nhưng không tự quyết định chính sách nghiệp vụ.

## 13. Last-Write-Wins (LWW): đơn giản nhưng có thể mất dữ liệu

LWW thường chọn phiên bản có timestamp lớn hơn. Nếu bằng nhau, hệ cần một tie-breaker xác định theo protocol.

Ví dụ:

```text
Replica A:
  value = "An"
  ts = 10:00:08

Replica B:
  value = "Anna"
  ts = 09:59:57
```

LWW chọn `"An"` dù thao tác `"Anna"` hoàn tất sau trong tình huống mở đầu.

### 13.1. LWW là chính sách, không phải chân lý về “last”

Tên “Last-Write-Wins” dễ khiến người học nghĩ hệ xác định **bản viết cuối cùng theo thời gian thực**. Trên thực tế, kết quả phụ thuộc cách hệ tạo/comparison timestamp:

- Timestamp do client cấp.
- Timestamp do coordinator/server cấp.
- Timestamp logic/physical hybrid.
- Tie-breaker.
- Replica reconciliation.
- Chính sách về clock và version.

Nếu hai write concurrent và timestamps không đáng tin, LWW chọn một phiên bản **theo quy tắc đã định nghĩa**, không chắc theo ý định mới nhất của con người.

### 13.2. Timestamps tương lai có thể “đè bóng” cập nhật mới

Ví dụ một client gửi timestamp do lỗi cấu hình ở năm sau. Trong hệ LWW timestamp-based:

```text
Value A: ts = 2030-01-01, value = "old"
Value B: ts = 2026-11-14, value = "new"
```

Các cập nhật về sau dùng timestamp bình thường có thể không thắng A cho tới khi vượt timestamp tương lai hoặc dữ liệu được sửa bằng quy trình phù hợp.

Đây là **future timestamp poisoning**; cần giám sát và kiểm soát nguồn timestamp ở những hệ cho phép client cấp timestamp.

### 13.3. Khi nào LWW phù hợp?

Có thể cân nhắc nếu:

- Giá trị chỉ là sở thích UI có thể ghi đè.
- Mất một sửa đổi concurrent là chấp nhận được.
- Có thể giải thích cách chọn winner.
- Không dùng timestamp làm bằng chứng audit chính xác tuyệt đối.
- Hệ có telemetry và quy trình khôi phục.

Không dùng LWW mù quáng cho:

- Số dư tiền.
- Tồn kho hữu hạn.
- Unique username toàn hệ.
- Quyền truy cập và thu hồi quyền.
- Thanh toán, reservation và ledger.
- Các tài liệu cộng tác cần giữ cả hai thay đổi.

## 14. Cassandra: timestamps của cell và xung đột LWW

Cassandra là ví dụ hữu ích vì các write timestamps đóng vai trò quan trọng trong reconciliation của cell theo semantics engine.

Ví dụ CQL minh họa:

```sql
CREATE TABLE user_profiles (
    user_id text PRIMARY KEY,
    display_name text,
    updated_at timestamp
);
```

Một update với timestamp được chỉ định rõ:

```sql
UPDATE user_profiles
USING TIMESTAMP 1800000000000000
SET display_name = 'An'
WHERE user_id = 'U01';
```

`USING TIMESTAMP` của Cassandra sử dụng mốc microsecond theo semantics CQL. Nó **không phải** thứ tự nhân quả được chứng minh giữa hai writers.

Nếu một writer dùng timestamp quá xa tương lai, những write bình thường có timestamp thấp hơn có thể không thay được cùng cell như kỳ vọng.

### 14.1. Write timestamp khác column `updated_at`

Trong table có:

```text
display_name   <- dữ liệu nghiệp vụ
updated_at     <- một field do ứng dụng lưu
write timestamp metadata <- timestamp dùng khi reconciliation
```

Hai mốc này có thể khác nhau. Không mặc định `updated_at` là metadata mà Cassandra dùng để phân xử cell versions.

### 14.2. Giá trị timestamp bằng nhau

Nếu hai updates có cùng timestamp, engine vẫn cần quy tắc xử lý tie theo loại giá trị/tombstone và implementation. Không suy ra rằng “write tới cuối cùng sẽ thắng” chỉ vì một write thực sự đi qua network muộn hơn.

### 14.3. Delete và tombstone

Xóa trong hệ LWW/timestamp-based có thể được biểu diễn bằng **tombstone**. Một delete với timestamp thấp hơn một write tương lai có thể không có tác dụng mong muốn lên dữ liệu đó.

Nếu replica xa đã bỏ lỡ tombstone và metadata xóa được dọn trong điều kiện không an toàn, có thể xuất hiện rủi ro **dữ liệu đã xóa hồi sinh**. Cần xét repair, retention, GC policy và protocol thực tế.

### 14.4. Consistency level không chữa đồng hồ lệch một cách thần kỳ

Đọc/ghi `QUORUM` hay `LOCAL_QUORUM` liên quan số replica đáp ứng, nhưng **không thay được một quy tắc conflict resolution đã chọn winner sai** do timestamp.

Normal quorum overlap cũng không biến mọi write thành transaction serializable. Nếu cần điều kiện không bị ghi đè sai, xem **LWT/CAS**, version, single-writer ownership và data modeling thích hợp.

## 15. MongoDB: ObjectId timestamp không phải commit order

MongoDB `ObjectId` thường bao gồm thành phần thời gian tạo ở độ phân giải giây cùng các thành phần khác. Nó hữu ích như một kiểu định danh, nhưng không nên kết luận:

> “Sắp xếp `_id` giảm dần cho thứ tự commit chính xác tuyệt đối của mọi writer.”

Lý do:

- ObjectId có thể được tạo ở client trước khi insert.
- Máy tạo ID có thể lệch clock.
- Những IDs cùng giây không có thứ tự thời gian toàn cục chắc chắn giữa các clients.
- Insert có thể bị retry hoặc tới DB sau.
- Một transaction có thể commit sau thời điểm ObjectId được sinh.

Nếu cần thứ tự list theo nghiệp vụ, định nghĩa `createdAt`/sequence và tie-breaker cùng contract rõ. Nếu cần thứ tự commit authoritative, phải dùng cơ chế dữ liệu/log/transaction phù hợp, không suy từ ID.

### 15.1. `clusterTime` và `operationTime`

MongoDB dùng logical time/operation metadata trong những ngữ cảnh replication, causal consistency và sessions được hỗ trợ. Các metadata này **không nên được diễn giải như một mốc UTC chính xác tuyệt đối giữa mọi hệ thống bên ngoài**.

Một causal session có thể giúp thực hiện những guarantee theo điều kiện read/write concern, session và operation type. Nó không tự làm Elasticsearch index, Redis cache hoặc service ngoài kế thừa thứ tự.

### 15.2. Change streams và resume tokens

Khi đồng bộ projection, change stream cung cấp các tín hiệu/thứ tự trong phạm vi được sản phẩm hỗ trợ. Consumer nên giữ resume token/offset, xử lý replay và idempotency.

Không nên chỉ sort event bằng field `updatedAt` từ client rồi coi đó là thứ tự nguồn tuyệt đối, nhất là khi nhiều documents/shards và transaction tham gia.

### 15.3. Optimistic concurrency

Ví dụ update có version:

```javascript
db.profiles.updateOne(
  {
    _id: "U01",
    version: 7
  },
  {
    $set: {
      displayName: "Anna"
    },
    $inc: {
      version: 1
    }
  }
);
```

Nếu một writer khác đã đưa version từ 7 lên 8, update với `version:7` không match theo kết quả được xác nhận. Ứng dụng cần đọc lại và quyết định merge/retry, không blind overwrite.

**Version và điều kiện atomic bảo vệ tranh chấp tốt hơn một câu “client timestamp của tôi lớn hơn”.**

## 16. DynamoDB multi-region: mode và chính sách xung đột

DynamoDB cho phép các hình thức replication nhiều vùng với **bảo đảm khác nhau theo chế độ global table và khả năng dịch vụ được hỗ trợ**. Không được mô tả tất cả global tables là một cơ chế nhất quán duy nhất.

Trong một cấu hình multi-writer với replication eventually consistent, các cập nhật đồng thời tại nhiều vùng có thể cần conflict resolution. Một chính sách dựa trên timestamp hoặc winner rule không nên được hiểu là bảo đảm mọi intention hoặc bất biến đều được giữ.

### 16.1. Ví dụ counter bị lost update

```text
Region A đọc counter=10, ghi counter=11
Region B đọc counter=10, ghi counter=11

Cả hai người dùng kỳ vọng tăng một.
Kết quả hội tụ có thể chỉ là 11 trong thiết kế LWW.
```

Hai thao tác hợp lệ bị gộp như một. Với lượt xem có thể dùng mô hình counter thích hợp; với tiền cần transaction/ledger.

### 16.2. Condition trên một vùng không tự là uniqueness toàn cầu

Hai vùng có thể cùng kiểm tra `attribute_not_exists(PK)` trong mô hình eventual multi-region rồi cùng xác nhận local write trước khi replication hội tụ, tùy mode và policy.

Vì vậy nếu username hoặc operationId phải duy nhất **toàn cầu**, cần:

- Xác minh mode/service guarantee chính xác.
- Một owner/allocator authoritative.
- Transaction/conditional write trong phạm vi toàn cầu được cam kết.
- Fencing khi failover.
- Reconciliation nếu thực sự chấp nhận conflict.

Không tự áp một công thức `R+W>N` kiểu Cassandra vào managed service không công bố API đó.

### 16.3. Tách clock timestamp và version nghiệp vụ

Một item có:

```json
{
  "pk": "PROFILE#U01",
  "name": "Anna",
  "clientUpdatedAt": "2026-11-14T10:00:00Z",
  "version": 8
}
```

`clientUpdatedAt` phục vụ hiển thị/audit theo nguồn timestamp. `version` và conditional-write contract phục vụ chống lost update trong phạm vi engine hỗ trợ. Không coi timestamp là sự thay thế cho điều kiện ghi.

## 17. Redis: TTL, time và thứ tự lệnh có phạm vi

Redis xử lý nhiều lệnh theo một mô hình thực thi tuần tự trên một instance; một lệnh atomic trên server có thứ tự thực thi tương ứng trong phạm vi đó. Nhưng:

- Hai Redis instances ở hai vùng không tự chia sẻ một global command order.
- Replica có thể lag.
- Network response có thể mất sau khi lệnh hoàn tất.
- Failover và persistence có phạm vi bảo đảm riêng.
- Client-supplied timestamp trong value vẫn có thể skew.

### 17.1. `TIME` của một server không phải time oracle toàn cầu

Lệnh Redis `TIME` trả thời gian từ server tương ứng. Dùng cùng một server để lấy mốc có thể giảm sự khác biệt giữa các client clocks, nhưng không bảo đảm thứ tự commit của một database khác hoặc những server Redis khác.

### 17.2. TTL và clock adjustments

Với nhiều hệ lưu trữ, expiry được đánh giá dựa trên clock/time semantics của engine. Nếu clock dịch mạnh, kỳ vọng “record sống đúng 60 giây theo thời gian thực tuyệt đối” cần được kiểm tra theo implementation.

Ví dụ:

```redis
SET session:U01 value EX 60
```

Có thời hạn cấu hình 60 giây theo semantics Redis, nhưng không nên lấy TTL như một lease phân tán chứng minh một worker cũ đã dừng chạy trên tài nguyên khác.

### 17.3. Redis Cluster và multi-key

Trong Redis Cluster, các lệnh/script nhiều key có quy tắc hash slot. Một script atomic trên cùng slot không tự trở thành transaction atomic giữa nhiều slots hoặc giữa Redis và database nguồn khác.

## 18. Hybrid Logical Clock (HLC): giữ logic cùng tín hiệu vật lý

**Hybrid Logical Clock** thường kết hợp:

- `physical`: thành phần gần thời gian vật lý quan sát được.
- `logical`: bộ đếm logic dùng khi cần bảo toàn thứ tự/hạn chế xung đột cùng mốc.

Một tuple khái niệm:

```text
HLC = (physicalTime, logicalCounter, nodeId)
```

`nodeId` có thể dùng tie-break khi cần total order deterministic; nó không nhất thiết là thành phần bắt buộc của mọi HLC implementation.

### 18.1. Quy tắc phát sinh sự kiện cục bộ

Gọi local state `(p,l)` và physical clock hiện tại `now`:

```text
newP = max(p, now)

if newP == p:
    newL = l + 1
else:
    newL = 0

state = (newP,newL)
```

Clock không lùi về mặt thứ tự HLC khi wall clock bị lùi nhẹ, vì có thể giữ `p` và tăng `l`.

### 18.2. Quy tắc khi nhận message

Nhận remote HLC `(pr,lr)`. Gọi local cũ `(p,l)`:

```text
newP = max(p, pr, now)

if newP == p AND newP == pr:
    newL = max(l, lr) + 1
else if newP == p:
    newL = l + 1
else if newP == pr:
    newL = lr + 1
else:
    newL = 0

state = (newP,newL)
```

Đây là pseudocode của một biến thể cơ bản, bỏ qua các giới hạn counter, restart/persistence và cơ chế kiểm tra clock drift mà engine production cần.

### 18.3. HLC giúp gì?

- Giữ một số thông tin gần thời gian vật lý.
- Bảo toàn quan hệ causal được truyền qua messages khi protocol dùng HLC đúng cách.
- Giảm việc chỉ dựa vào client wall clock để xếp versions.
- Hữu ích cho thiết kế distributed ordering/MVCC trong một số hệ.

### 18.4. HLC không giải quyết được gì?

- Không phát hiện đầy đủ mọi concurrency như vector clock trong mọi mô hình.
- Không tạo consensus hoặc global transaction chỉ bằng timestamp.
- Không tự bảo đảm linearizability hay strict serializability.
- Không biến `physical` thành thời điểm thật chính xác tuyệt đối.
- Không loại bỏ nhu cầu xử lý clock drift lớn, restart và node ID.
- Không quyết định nghiệp vụ merge giữa hai bản concurrent.

**HLC là thành phần của protocol, không phải giấy chứng nhận rằng timestamp luôn tương ứng thứ tự thực tế.**

## 19. Bounded clock uncertainty: khoảng thời gian thay vì một điểm

Nếu hệ có một mô hình đồng bộ thời gian **thực sự cung cấp bound đáng tin**, có thể biểu diễn thời gian một sự kiện được đọc theo khoảng:

\[
T_A\in[a_{\min},a_{\max}]
\]

\[
T_B\in[b_{\min},b_{\max}]
\]

### 19.1. Hai khoảng không giao nhau

Nếu:

\[
a_{\max}<b_{\min}
\]

và các bounds hợp lệ cho đúng mốc timestamp sampling, có thể kết luận mốc A xảy ra **trước** mốc B theo thời gian vật lý.

Ví dụ:

```text
A ∈ [10:00:00.000, 10:00:00.020]
B ∈ [10:00:00.200, 10:00:00.220]
```

Khoảng A kết thúc trước khi B bắt đầu.

### 19.2. Hai khoảng giao nhau

```text
A ∈ [10:00:00.000, 10:00:00.020]
B ∈ [10:00:00.010, 10:00:00.030]
```

Hai khoảng chồng lên nhau. Chỉ từ bounds này **không thể biết chính xác** mốc A hay B trước.

Không nên chọn timestamp trung tâm lớn hơn rồi tuyên bố đã chứng minh thời điểm thực.

### 19.3. Bound phải đáng tin

Nếu monitoring báo `±5 ms` nhưng một VM mất đồng bộ thực tế lệch 2 giây, mọi suy luận về khoảng thời gian trở nên sai.

Bound cần có giả định vận hành và cơ chế giám sát. Một số hệ thiết kế clock uncertainty APIs và commit-wait để đạt external consistency trong phạm vi giao thức; **chính protocol và điều kiện thời gian** tạo guarantee, không phải phép so timestamp thô.

## 20. External consistency và chi phí chờ đồng hồ

Một thiết kế như Google Spanner/TrueTime thường được dùng để minh họa cách hệ phân tán kết hợp:

- Đồng bộ thời gian với uncertainty interval.
- Consensus/transaction protocol.
- Chọn commit timestamp.
- Có thể cần **commit-wait** trước khi trả success, để bảo vệ quan hệ thời gian thực theo bảo đảm sản phẩm.

### 20.1. Vì sao có wait?

Nếu commit timestamp được chọn nhưng vẫn nằm trong khoảng bất định “có thể là tương lai” của clock, hệ có thể cần chờ qua uncertainty window để đảm bảo thứ tự external consistency mà protocol yêu cầu.

Chi phí có thể là thêm latency vào đường commit.

### 20.2. Không sao chép mô hình bằng một lệnh `sleep`

Chỉ gọi:

```java
Thread.sleep(10);
```

sau mỗi write không tạo external consistency. Phải có timestamp assignment, transaction protocol, uncertainty bound đáng tin và các điều kiện commit/read tương ứng.

### 20.3. Phân biệt các guarantee

- **Serializability:** kết quả giống một thứ tự tuần tự các transactions.
- **Strict serializability/external consistency:** thứ tự tuần tự còn tôn trọng thứ tự real-time của transactions không chồng lấn.
- **Causal consistency:** tôn trọng quan hệ nhân quả được định nghĩa.
- **Eventual consistency:** replicas cuối cùng hội tụ trong giả định phù hợp, không tự có thứ tự đọc mạnh.

Các mô hình khác nhau về phạm vi và điều kiện; không có một nút `timestamp=true` bật được tất cả.

## 21. Consensus log: thứ tự quyết định không dựa trên đồng hồ máy

Trong một replicated state machine dùng giao thức consensus (ví dụ họ Raft), các commands được áp dụng theo thứ tự **log entries** đã được thống nhất.

Ví dụ khái niệm:

```text
Term 12:
  index 100 -> Reserve R100
  index 101 -> Cancel R101
  index 102 -> Reserve R102
```

Thứ tự log index trong một consensus group có thể định nghĩa thứ tự áp dụng commands dù wall clock các replica lệch nhau.

### 21.1. Log index không phải timestamp UTC

`index=102` nói entry đứng sau entry 101 **trong cùng log group**. Nó không chứng minh command được tạo lúc UTC nào.

### 21.2. Không so log index của hai groups

```text
Shard A: logIndex=500
Shard B: logIndex=900
```

Không thể kết luận event ở B muộn hơn A chỉ vì 900 > 500. Hai indexes thuộc **hai dãy độc lập**.

Muốn có thứ tự toàn cục giữa groups có thể cần sequencer, transaction coordinator, distributed timestamp oracle hoặc giao thức phối hợp khác.

### 21.3. Follower read và commit index

Một follower đọc local có thể lag so với leader dù consensus log đã commit. Không mặc định `read from follower` linearizable nếu protocol không có read-index/lease/session mechanism phù hợp.

## 22. Total-order sequencer: giải pháp có chi phí

Một hệ cần thứ tự duy nhất cho mọi giao dịch có thể cấp sequence number tại một nguồn có thẩm quyền:

```text
Write A -> seq=1001
Write B -> seq=1002
Write C -> seq=1003
```

Nếu sequencer thực sự xử lý theo protocol bảo đảm, các sequence IDs tạo thứ tự quyết định rõ.

### 22.1. Ưu điểm

- Có order marker độc lập với clock lệch.
- Dễ replay theo số thứ tự.
- Có thể dùng để xây ledger/log.
- Giảm ambiguity khi so revision của một resource.

### 22.2. Đánh đổi

- Tăng coordination/round trips.
- Có thể là bottleneck hoặc cần partitioning.
- Failover phải giữ monotonic sequence.
- Cache/reservation số trước có thể tạo **gaps**.
- Hai sequencers độc lập không tự tạo một global order.
- Sequence ID tăng không nhất thiết tương ứng chính xác thời gian client gửi.

Nhiều hệ ưu tiên order **theo aggregate/partition** để tránh global sequencer trên mọi request.

## 23. Version và CAS: xử lý xung đột không cần đoán giờ

Một resource có revision tăng đơn điệu trong phạm vi authoritative:

```json
{
  "orderId": "O1001",
  "status": "PENDING",
  "version": 7
}
```

Client muốn chuyển trạng thái:

```text
UPDATE Order O1001
IF version = 7 AND status = PENDING
SET status = CONFIRMED, version = 8
```

Hai actors cùng đọc version 7:

```text
Actor A: CAS 7 -> 8  (succeed)
Actor B: CAS 7 -> 8  (condition fails)
```

Actor B biết phải đọc state mới và xử lý conflict theo nghiệp vụ.

**CAS giải quyết tranh chấp ở nguồn dữ liệu có phạm vi atomicity đúng**, không phụ thuộc vào việc đồng hồ của hai client chạy nhanh/chậm.

### 23.1. CAS khác idempotency

- CAS bảo vệ điều kiện state hiện hành.
- Idempotency ngăn cùng một operation ID bị áp dụng hai lần.
- Một retry sau network timeout có thể không biết CAS lần trước đã thành công chưa.

Vì vậy cần kết hợp operation ID, version, authoritative lookup và retry policy để xử lý **unknown commit**.

### 23.2. Version tăng ở đâu?

Một `version` chỉ đáng tin khi được tăng/kiểm soát tại nguồn có authority theo transaction/conditional write phù hợp.

Nếu client A và client B đều tự lấy `version=8` mà không có kiểm tra atomic, hai version giống nhau chưa chứng minh có một commit order.

### 23.3. ETag/If-Match

Một HTTP API có thể dùng optimistic concurrency:

```http
GET /orders/O1001
```

```http
HTTP/1.1 200 OK
ETag: "order-v7"

{"status":"PENDING","version":7}
```

Sau đó:

```http
PATCH /orders/O1001
If-Match: "order-v7"
Content-Type: application/json

{"status":"CONFIRMED"}
```

Server chỉ thực thi nếu nguồn vẫn ở revision 7 theo contract. Nếu không, có thể trả `412 Precondition Failed`. ETag phải được sinh/kiểm soát bởi server, không chấp nhận một timestamp giả của client làm điều kiện đủ.

## 24. Lease và fencing: clock skew có thể làm hai worker cùng nghĩ mình sở hữu tài nguyên

Một hệ dùng lease để phân phối quyền ghi:

```text
Worker A giữ lease đến 10:00:10 theo đồng hồ A
Worker B nhận lease mới khi thấy lease hết hạn
```

Nếu clock giữa A, B và nơi lưu lease lệch, hoặc A bị pause/GC rồi tiếp tục, hai worker có thể cùng tưởng mình được phép ghi.

### 24.1. Lease expiry không buộc worker cũ ngừng chạy

Ví dụ:

```text
t0: A lấy lease
t1: A pause 30 giây
t2: Lease hết hạn
t3: B lấy lease mới
t4: A tỉnh lại và ghi
```

Dù không có clock skew, worker cũ vẫn có thể gây ghi sai nếu tài nguyên đích không kiểm tra quyền.

### 24.2. Fencing token

Mỗi lần cấp ownership, tăng generation/epoch:

```text
A giữ epoch=41
B được cấp epoch=42
```

Nguồn tài nguyên authoritative từ chối write với epoch thấp hơn highest accepted epoch.

```text
Write from B epoch=42 -> accepted
Late write from A epoch=41 -> rejected
```

**Fencing phải được enforce ở nơi áp dụng side effect**, không chỉ in token trong log. Nếu external system không hỗ trợ fencing, cần thiết kế single-owner, idempotency, coordinator hoặc compensating workflow khác.

### 24.3. TTL không tương đương lock an toàn

Redis `SET NX EX`, database lease field hoặc queue visibility timeout đều cần xét:

- Clock semantics.
- Worker pause/restart.
- Renewal failure.
- Delayed messages.
- Leader election.
- Thời gian thực thi dài.
- Fencing/idempotency.

Không dùng “lease còn hạn theo đồng hồ của tôi” làm bằng chứng đủ để chuyển tiền hoặc ghi đè dữ liệu quan trọng.

## 25. TTL, expiration và dữ liệu đã xóa

TTL thường được diễn giải là dữ liệu tồn tại tối đa một khoảng thời gian. Trong hệ phân tán, phải xem rõ **đồng hồ và thời điểm nào dùng để tính hết hạn**.

### 25.1. Hai cách diễn đạt khác nhau

```text
Expire 60 giây sau khi server áp dụng write
```

và:

```text
Expire lúc 2026-11-14T10:01:00Z
```

Có khác biệt về nguồn thời gian và timestamp assignment. Client offline có thể gửi event cũ với thời gian tạo trước nhiều giờ, nhưng server chỉ vừa nhận nó.

### 25.2. TTL không phải nghiệp vụ hủy có transaction

Một reservation:

```text
status = RESERVED
expiresAt = ...
```

không nhất thiết tự giải phóng tồn kho đúng một lần chỉ vì document TTL bị xóa. TTL deletion có thể bất đồng bộ và không chạy business side effect như kỳ vọng.

Cần một state transition/expiry processor có idempotency và điều kiện:

```text
IF status=RESERVED AND expiresAt <= authoritativeNow
THEN release reservation
```

Cách lấy `authoritativeNow` và ranh giới atomic cần do hệ đảm bảo; đây là pseudocode, không phải cú pháp chung mọi NoSQL.

### 25.3. Tombstone và độ trễ truyền xóa

Một delete với timestamp thấp hơn một old write có timestamp tương lai có thể bị reconciliation xử lý không như người dùng dự đoán.

Ngoài ra, một replica/backup/read model còn giữ dữ liệu cũ có thể làm bản đã xóa xuất hiện lại khi reindex/restore nếu thiếu tombstone retention và replay policy.

Thời gian xóa logic, visibility của delete và physical garbage collection là những mốc khác nhau.

## 26. Event time, processing time và ingestion time

Trong stream/CDC:

| Loại thời gian | Mốc mô tả |
| --- | --- |
| **Event time** | Thời điểm sự kiện nghiệp vụ được phát sinh hoặc được gắn mốc |
| **Ingestion time** | Thời điểm hệ tiếp nhận event |
| **Processing time** | Thời điểm processor đang xử lý |
| **Commit time/order** | Mốc/sequence mà source quyết định lưu |
| **Index visibility time** | Khi read model có thể tìm thấy event |

Ví dụ mobile app offline:

```text
09:00  User cập nhật profile (eventTime=09:00)
09:02  User làm một cập nhật khác trên web (eventTime=09:02)
10:00  Điện thoại reconnect, gửi event 09:00
```

Sự kiện 09:00 đến server lúc 10:00, sau web update. Nếu áp dụng theo **arrival order**, offline event có thể ghi đè thông tin mới. Nếu áp dụng theo **event time** từ client không tin cậy, sai lệch clock lại có thể tạo winner sai.

Cần chọn **quy tắc merge theo domain**, ví dụ field-level changes, CAS/version, user conflict dialog hoặc CRDT phù hợp.

### 26.1. Watermark không phải bằng chứng mọi event đã tới

Watermark trong xử lý event time thường biểu diễn một nhận định về mức độ hoàn chỉnh với allowed lateness hoặc assumptions. Nó không tự chứng minh không có event cũ tới muộn.

Nếu dùng watermark để đóng bucket báo cáo, cần chính sách late events, correction/backfill và UI báo timestamp thống kê.

### 26.2. Duplicate và out-of-order

Một event có thể đến hai lần và không theo thứ tự do retry, broker redelivery, network và consumer rebalancing.

Dùng `eventId`, aggregate version/sequence và idempotent consumer. Timestamp chỉ là một trường thêm, không thay cơ chế dedup.

## 27. Causal ordering trên event stream

Một hệ có:

```text
OrderCreated -> PaymentAuthorized -> OrderConfirmed
```

Nếu `OrderConfirmed` đến projection trước `OrderCreated`, projection cần biết:

- Có thể áp dụng sự kiện mới trực tiếp từ full-state snapshot không?
- Hay phải chờ các transitions phụ thuộc?
- Có sequence gap cần replay không?
- Có event bị duplicate không?
- Aggregate version hiện tại là bao nhiêu?

### 27.1. Full-state snapshots và deltas khác nhau

**Full-state event:**

```json
{
  "orderId":"O1001",
  "revision":9,
  "status":"CANCELLED"
}
```

Nếu projection đã có revision 9 rồi nhận revision 8, có thể bỏ revision 8 theo rule snapshot/version.

**Delta event:**

```json
{
  "orderId":"O1001",
  "sequence":8,
  "deltaQuantity":-2
}
```

Không được tự bỏ delta 8 chỉ vì đã thấy sequence 9 nếu delta 8 chưa được áp dụng và tổng phụ thuộc cả hai. Cần ordered replay/gap handling, hoặc cấu trúc delta được thiết kế merge an toàn.

### 27.2. Kafka partition order không phải global order

Một broker có thể bảo toàn thứ tự trong một partition/topic log theo protocol, nhưng:

```text
Partition A offset=100
Partition B offset=400
```

không tạo thứ tự toàn cục giữa A và B.

Muốn xử lý thứ tự theo order, các events của cùng `orderId` thường cần routing/keying phù hợp hoặc per-aggregate sequence có kiểm tra.

### 27.3. CDC từ nhiều shards

Mỗi shard có thể xuất một log riêng. Dù mỗi log ordered, khi merge nhiều logs:

- Network delay khác nhau.
- Consumer processing chậm không đều.
- Transaction trải nhiều shards.
- Clock timestamps chưa chắc đồng nhất.

Không sort tất cả CDC events theo client `updatedAt` rồi tuyên bố có full commit order. Cần dựa vào guarantees của CDC protocol/source và thiết kế projection theo scope.

## 28. Xử lý xung đột dựa trên CRDT thay vì “ai có timestamp lớn nhất”

**Conflict-free Replicated Data Types (CRDTs)** là một họ cấu trúc dữ liệu có phép cập nhật/merge được thiết kế để replicas hội tụ trong điều kiện giả định phù hợp, không nhất thiết dùng LWW cho toàn bộ giá trị.

Ví dụ một số loại:

- **G-counter/PN-counter:** tăng hoặc cộng/trừ theo thiết kế replicated counter.
- **Grow-only set:** thêm phần tử, merge theo tập hợp.
- **Observed-remove set:** có metadata để phân biệt add/remove.
- **Multi-value register:** giữ nhiều giá trị concurrent thay vì bỏ một.
- **LWW register:** chọn winner theo timestamp/tie-breaker nhưng vẫn có mất cập nhật nếu policy chấp nhận.

### 28.1. Khi counter cần cộng các updates độc lập

Hai vùng đồng thời tăng view count:

```text
A: +1
B: +1
```

LWW trên một scalar có thể chỉ còn `+1` hiệu dụng. Một counter CRDT phù hợp có thể hội tụ đến tổng hai increments theo protocol.

### 28.2. CRDT không bảo vệ mọi invariant

Giả sử stock=1, hai vùng cùng cho phép reserve 1 khi offline. Một counter hội tụ chính xác tổng hai reservations có thể cho `stock=-1`.

CRDT tự hội tụ không có nghĩa giữ invariant `available >= 0` trong mọi thao tác concurrent. Có thể cần escrow quotas, global owner hoặc consensus transaction.

### 28.3. Set remove và resurrection

Nếu một replica xóa item trong lúc replica khác thêm cùng item, hành vi cuối phụ thuộc **semantics của set CRDT** (add-wins, remove-wins, observed-remove...), không thể quyết chỉ bằng tên “CRDT”.

Phải chọn đúng quy tắc nghiệp vụ.

## 29. Xác định xung đột bằng revision thay vì `updatedAt`

Một document có:

```json
{
  "profileId":"U01",
  "name":"Anna",
  "version":42,
  "updatedAt":"2026-11-14T10:00:00Z"
}
```

Có ba tác dụng khác nhau:

- `updatedAt`: phục vụ hiển thị, audit/time filters theo nguồn.
- `version`: nhận biết một state transition đã được nguồn authoritative xác nhận.
- `operationId`: nhận biết một ý định ghi để dedup khi retry.

Khi dùng cùng nhau:

```text
Client muốn sửa từ version 42:
  send operationId=R100, expectedVersion=42

Source:
  if R100 already completed -> return previous outcome
  else if version != 42 -> conflict
  else update state, version=43, record R100
```

Điều kiện `record R100` và `update state` phải atomic hoặc có workflow recovery phù hợp nếu nằm khác items/systems.

### 29.1. Sequence không nhất thiết là timestamp

Một revision 43 không có nghĩa xảy ra lúc 43 ms hay 43 giây. Nó chỉ biểu diễn thứ tự **trong phạm vi aggregate/version authority**.

### 29.2. Có thể dùng composite version

Một số hệ dùng `(epoch, counter)`:

```text
epoch=12, counter=100
epoch=12, counter=101
epoch=13, counter=1
```

So sánh theo quy tắc protocol, ví dụ epoch trước rồi counter, giúp giữ tính đơn điệu qua chuyển owner. Không so `counter=101` với `counter=1` nếu bỏ epoch.

## 30. Case study: giá bán ở hai vùng

Một cửa hàng có giá niêm yết `100.000 VND`.

```text
Region A: nhân viên sửa 90.000, ts=10:05:10
Region B: nhân viên sửa 95.000, ts=10:05:01
```

Máy A nhanh 15 giây. B được thực hiện sau A theo workflow duyệt giá, nhưng timestamp B nhỏ hơn.

### 30.1. LWW sai nghiệp vụ

Nếu policy là “phê duyệt cuối cùng theo workflow mới có hiệu lực”, LWW theo wall time có thể giữ 90.000 và bỏ 95.000.

### 30.2. Thiết kế phù hợp hơn

- Một owner cho bảng giá hoặc revision service.
- Mỗi đề xuất giá có `proposalId`, `expectedVersion`.
- Đường phê duyệt cập nhật `priceVersion` bằng CAS/transaction.
- Changes ghi log sequence theo sản phẩm.
- UI hiển thị thời điểm thao tác, nhưng engine quyết định thứ tự theo revision/approval rules.
- Retry dùng operation ID cũ.

Nếu cho phép nhiều vùng cùng duyệt, cần protocol xử lý **approval conflict** rõ, không chỉ chọn timestamp lớn.

## 31. Case study: giao diện cộng tác offline

Hai thiết bị cùng sửa ghi chú:

```text
Base v5: "Họp thứ hai"
Device A offline -> "Họp thứ ba"
Device B offline -> "Họp thứ tư"
```

Cả hai cùng xuất phát từ v5, không biết thao tác của nhau.

### 31.1. Causal detection

Version vector hoặc metadata tương đương có thể nhận diện hai sửa đổi concurrent.

### 31.2. Các chiến lược

- **Reject on conflict:** yêu cầu người dùng chọn một phiên bản.
- **Multi-value register:** giữ cả hai để sau đó hợp nhất.
- **Field-level merge:** hợp nhất nếu sửa các fields độc lập.
- **OT/CRDT text:** với tài liệu cộng tác, dùng thuật toán có semantics chỉnh sửa phù hợp.
- **LWW:** chỉ khi có thể chấp nhận một bản bị mất và người dùng hiểu.

Không có cách merge đúng chung cho mọi loại nội dung. Đồng hồ chỉ hỗ trợ metadata; domain quyết định ý nghĩa của các thay đổi.

## 32. Case study: quyền truy cập đã bị thu hồi

Region A nhận:

```text
Revoke access for User U01
```

Region B còn bản cache:

```text
permission=ACTIVE
```

Nếu B dựa vào `updatedAt` từ client để xem quyền nào mới hơn, đồng hồ sai có thể khiến bản active cũ thắng hoặc invalidation đến muộn.

### 32.1. Yêu cầu bảo mật

Với hành động nhạy cảm, policy có thể cần:

- Authority kiểm tra quyền.
- Revocation epoch/minimum revision.
- Fail-closed khi không xác minh được.
- Token TTL ngắn phù hợp.
- Session invalidation/lease fencing.
- Propagation lag SLO và audit.

Không đánh đổi quyền truy cập bằng LWW chỉ để giảm coordination latency khi business/security contract yêu cầu revocation có hiệu lực.

### 32.2. Time-based token expiry

Expiry của token dựa trên thời gian cần xem clock skew allowance. Cho phép một leeway nhỏ có thể phù hợp với validation, nhưng không nên tăng leeway quá lớn khiến token bị thu hồi vẫn được chấp nhận lâu hơn mong muốn.

## 33. Case study: thanh toán và ledger

Hai events:

```text
PaymentAuthorized
PaymentCaptured
```

Nếu hệ sort theo wall timestamp do hai services cấp, clock skew có thể khiến `Captured` được xếp trước `Authorized`.

### 33.1. Không dùng timestamp làm thứ tự quyết định tiền

- Mỗi payment intent có operation ID.
- State transitions được xác thực bằng conditional write/transaction hoặc provider authority.
- Ledger entries tham chiếu transaction/sequence phù hợp.
- Duplicate retries được dedup.
- Unknown commit được lookup/reconcile.
- Audit giữ cả event time và authoritative commit/reference.

Thứ tự ledger phải do protocol định nghĩa, không tạo ngẫu nhiên từ đồng hồ các mobile clients.

### 33.2. Refund cũng có outcome unknown

Một refund timeout không chứng minh refund chưa chạy. Nếu retry bằng operation ID mới, có thể refund hai lần. **Clock không giải quyết ambiguous commit**; idempotency và provider reconciliation mới là cơ chế phù hợp.

## 34. Chọn chính sách xung đột theo dữ liệu

| Loại dữ liệu | Rủi ro nếu LWW sai | Chiến lược cân nhắc |
| --- | --- | --- |
| Theme UI | Mất một sửa đổi, tác động nhỏ | LWW hoặc user preference revision |
| Hồ sơ người dùng | Mất sửa đổi offline | CAS, version vector, merge theo field |
| Danh sách tag | Add/remove concurrent | OR-set hoặc policy cụ thể |
| Lượt xem | Lost increments | Counter CRDT, atomic increment hoặc event aggregation |
| Tồn kho | Overselling/negative stock | Conditional atomic update, escrow quota hoặc single owner |
| Username unique | Trùng định danh | Unique constraint/allocator có phạm vi đúng |
| Giá bán | Sai giá được phê duyệt | Revision/approval workflow |
| Payment/ledger | Double charge, mất tiền | Transaction/ledger/idempotency |
| Phân quyền | Cho truy cập sau revoke | Authoritative check, revocation epoch, fail-closed |
| Chat history | Sai thứ tự theo conversation | Per-conversation sequence/causal order |
| Logs/telemetry | Xếp sự kiện lệch | Giữ nguồn timestamp + uncertainty + ingest time |
| Search index | Stale overwrite/resurrection | Revision guard, tombstone, replay |
| Lịch hẹn | Đè booking/hủy nhầm | CAS, ownership, transaction |
| Dashboard analytics | Sai grouping theo event time | Watermark, late correction, snapshot |

Một hệ thống có thể dùng nhiều chính sách trong cùng database. **Dữ liệu khác nhau có mức chấp nhận mất cập nhật khác nhau**.

## 35. Thiết kế schema có thông tin thứ tự đủ dùng

Ví dụ document theo aggregate:

```json
{
  "aggregateType": "ORDER",
  "aggregateId": "O1001",
  "tenantId": "T01",
  "state": "CONFIRMED",
  "revision": 43,
  "ownerEpoch": 12,
  "lastOperationId": "R100",
  "createdAt": "2026-11-14T09:00:00Z",
  "serverUpdatedAt": "2026-11-14T09:02:00Z",
  "sourceEventId": "E1001"
}
```

Ý nghĩa từng trường:

- `revision`: thứ tự thay đổi trong aggregate, do authority thực thi.
- `ownerEpoch`: phân biệt ownership cũ/mới khi chuyển leader.
- `lastOperationId`: một phần idempotency/attribution, không tự đủ cho lịch sử nhiều operations.
- `createdAt`/`serverUpdatedAt`: metadata thời gian.
- `sourceEventId`: hỗ trợ replay/dedup downstream.

### 35.1. Một field không đủ mọi guarantee

Nếu aggregate nhận nhiều operations cùng lúc, chỉ giữ `lastOperationId` không đủ để biết mọi ID đã xử lý. Cần operation log/inbox/idempotency store phù hợp và retention policy.

### 35.2. `createdAt` không nên cập nhật khi retry

Retry cùng operation không được làm mới timestamp tạo theo mỗi attempt rồi vô tình thay thứ tự hiển thị business.

Có thể giữ riêng:

```text
businessCreatedAt
firstReceivedAt
lastAttemptAt
committedAt
```

nhưng không được coi chúng là thứ tự tuyệt đối giữa mọi systems nếu thiếu mô hình nguồn giờ.

## 36. Ordering trong API và phân trang

Một endpoint:

```text
GET /orders?sort=createdAt:desc&limit=20
```

phải biết:

- `createdAt` là server/client timestamp?
- Đồng hồ các writer có đồng bộ không?
- Có thể có nhiều orders cùng timestamp không?
- Order nào thuộc cùng shard/partition?
- Có snapshot/cursor ổn định không?

### 36.1. Tie-breaker duy nhất

Nếu muốn thứ tự nhất quán cho UI:

```text
ORDER BY createdAt DESC, orderId DESC
```

Một tie-breaker giúp phép sort deterministic, nhưng **không biến thứ tự này thành thứ tự commit real-time**.

### 36.2. Keyset cursor

Cursor cần lưu mọi sort keys/tie-breaker:

```json
{
  "lastCreatedAt":"2026-11-14T09:30:00Z",
  "lastOrderId":"O1001"
}
```

Đây là cursor theo **thứ tự đã chọn**, không phải bảo đảm global commit sequence.

### 36.3. Snapshot qua nhiều shards

Ngay cả khi mỗi shard trả danh sách đúng, merge các danh sách đọc tại nhiều mốc khác nhau có thể tạo kết quả không nhất quán. Nếu report yêu cầu snapshot transaction, cần cơ chế snapshot/consistent cut của engine hoặc read model đã chốt mốc.

## 37. Đồng hồ trong TTL và deadline: hai bài toán khác nhau

Một lỗi thiết kế thường gặp là dùng chung một timestamp từ client cho:

1. Hiển thị thời điểm tạo.
2. Quyết định lease hết hạn.
3. Xác định thao tác mới nhất.
4. Xác định timeout RPC.

Bốn mục đích có yêu cầu khác nhau.

| Mục đích | Thông tin phù hợp hơn |
| --- | --- |
| Hiển thị ngày giờ | UTC instant + timezone khi hiển thị |
| Timeout trong một process | Monotonic elapsed time |
| Hạn thanh toán | Nguồn wall-clock authoritative và business policy |
| Thứ tự thay đổi trên aggregate | Atomic revision/sequence |
| Thứ tự nhân quả | Lamport/vector/HLC context theo protocol |
| Linearizable transaction order | Coordination/consensus/transaction protocol |
| Hạn lease cho writer | Lease policy + fencing + authoritative enforcement |
| Analytics event window | Event time + watermark/late-event rules |
| Replication ordering | Source log offsets/revision |

**Chọn một clock theo mục đích**, không dùng `Instant.now()` như chìa khóa chung cho mọi vấn đề phân tán.

## 38. Giám sát clock skew và hiệu ứng nghiệp vụ

Những metric nên xem tùy hạ tầng:

| Metric/quan sát | Ý nghĩa |
| --- | --- |
| `clock_offset_ms` | Sai lệch so nguồn đồng bộ |
| `clock_sync_state` | Đồng hồ có đang được đồng bộ không |
| `clock_uncertainty_ms` | Khoảng bất định nếu hệ có mô hình đo hợp lệ |
| `clock_step_events` | Số lần điều chỉnh nhảy clock |
| `time_source_reachability` | Khả năng tới nguồn thời gian |
| `replication_lag_ms` | Replica bắt kịp chậm |
| `future_timestamp_rejections` | Write timestamp quá xa tương lai bị chặn |
| `revision_conflict_total` | CAS conflicts |
| `out_of_order_events_total` | Event đến ngoài thứ tự đã định nghĩa |
| `stale_update_ignored_total` | Projection bỏ state snapshot cũ |
| `sequence_gap_detected_total` | Thiếu delta/offset |
| `lease_fencing_rejections` | Writer cũ bị từ chối |
| `unknown_write_outcomes` | Ghi/commit chưa rõ kết quả |
| `projection_reconciliation_mismatch` | Read model lệch nguồn |
| `event_time_lateness` | Event time và processing time khác nhau |

Tên trên là **metric thiết kế minh họa**, không có nghĩa một database tự xuất đúng những series đó.

### 38.1. Phân đoạn theo node và vùng

Trung bình offset toàn cluster có thể gần 0 trong khi:

```text
Node A offset = +800 ms
Node B offset = -800 ms

Average = 0 ms
Pairwise difference = 1600 ms
```

Vì vậy cần xem **max absolute offset**, phân bố theo host/region và trạng thái đồng bộ, không chỉ average có dấu.

### 38.2. Đo nguồn và đích

Khi phân tích event đến muộn, ghi riêng:

```text
eventCreatedAt
sourceCommittedAt (nếu nguồn cung cấp)
consumerReceivedAt
projectionAppliedAt
```

Không lấy `consumerReceivedAt - eventCreatedAt` làm network latency chính xác nếu hai clocks không có bound đáng tin; nó còn có queue/processing delays và clock offset.

### 38.3. Không tạo label cardinality vô hạn

Không dùng raw `userId`, `eventId` hoặc tài khoản trong metric labels. Giữ IDs trong logs/traces có phân quyền, TTL và masking; dùng aggregate metric theo service, region, event type hoặc shard.

## 39. Kiểm thử lệch đồng hồ có kiểm soát

Một bài test consistency chỉ mô phỏng network partition chưa đủ. Cần có tình huống **mạng vẫn hoạt động nhưng clocks sai**.

### 39.1. Ma trận thử nghiệm

| Tình huống | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Máy A nhanh +10 giây | LWW không được bị dùng sai cho invariant |
| Máy B chậm -10 giây | Replay/read model không ghi đè revision mới |
| Clock nhảy lùi | Local deadline vẫn dùng monotonic time |
| Clock nhảy tới tương lai | Không chấp nhận future timestamp nguy hiểm theo policy |
| Hai writes cùng millisecond | Tie-breaker determinism, không suy order thực |
| Hai cập nhật offline concurrent | Phát hiện conflict hoặc merge đúng |
| Event v9 đến trước v8 | Projection xử lý theo full-state/delta rule |
| Delete/tombstone đến trễ | Không hồi sinh bản đã xóa |
| Lease holder bị GC pause | Fencing từ chối worker cũ |
| Failover/leader epoch tăng | Writer cũ không ghi được |
| Cross-region RTT tăng | Không suy sự kiện tới trước là tạo trước |
| Transaction commit ACK mất | Retry/lookup không nhân side effect |
| Snapshot multi-shard | Báo cáo không trộn mốc nếu contract yêu cầu |
| Token/session gần expiry | Clock leeway được áp an toàn |
| Offline client reconnect | Event time khác commit/ingest time |

### 39.2. Phép thử LWW

1. Cấu hình hai writers có clock offsets khác nhau trong test isolation.
2. Cho A commit, nhận ACK.
3. Sau đó cho B khởi tạo update trên cùng key.
4. Quan sát timestamp và final value.
5. So với quy tắc nghiệp vụ đã công bố.
6. Kiểm tra logs có ghi nguồn timestamp và uncertainty không.

Nếu hệ dùng LWW và kết quả A thắng, đó có thể đúng **theo policy kỹ thuật** nhưng sai kỳ vọng nghiệp vụ. Test phải nêu loại tính đúng đắn đang xác minh.

### 39.3. Phép thử causal order

1. A tạo event E1.
2. B nhận E1.
3. B tạo E2 phụ thuộc E1.
4. Trì hoãn đường vận chuyển E1 tới projection, gửi E2 tới trước.
5. Quan sát projection có giữ dependency/gap/replay đúng không.

Một timestamp E1 lớn hơn E2 do skew không nên tự phá quan hệ nhân quả đã biết.

### 39.4. Không chỉnh giờ trên production để thử

Fault injection lệch đồng hồ có thể ảnh hưởng TLS certificates, authentication, leases, database durability, scheduled jobs và monitoring.

Chỉ thử trong **môi trường được phê duyệt, cô lập, có recovery plan**. Không thay NTP/clock của máy dùng chung hoặc production để minh họa bài học.

## 40. Một runbook khi nghi clock skew gây xung đột

### Bước 1 — Xác định hành vi sai

Ví dụ: cập nhật mới bị bản cũ ghi đè, delete hồi sinh, token bị từ chối, lease race hoặc event order đảo.

### Bước 2 — Xác định nguồn timestamp

Client, gateway, coordinator, storage engine, CDC hay index? Có những field nào chứa timestamp?

### Bước 3 — Tách quan hệ cần bảo đảm

Nghiệp vụ cần thứ tự thời gian thực, causal, per-key sequence, global transaction order hay chỉ deterministic tie-breaker?

### Bước 4 — Xem clock health

Đối chiếu offsets, sync state, VM migrations, clock steps và time source per host/region trong khoảng xảy ra lỗi.

### Bước 5 — Dựng lại timeline bằng nhiều bằng chứng

Dùng operation ID, request logs, trace, source log offsets, revision, WAL/commit metadata và replica states. Không sort riêng theo client `updatedAt`.

### Bước 6 — Kiểm tra conflict resolver

LWW? Timestamp từ client hay server? CAS? Version vectors? HLC? Last arrival? Merge policy? Thời điểm tombstone?

### Bước 7 — Xem bản ghi sai do retry/replay

Một event cũ có thể được phát lại sau failover hoặc consumer restart. Sự cố có thể do thiếu revision guard hơn là skew đơn thuần.

### Bước 8 — Bảo vệ invariant

Nếu là stock, tiền hoặc quyền, có thể cần dừng/fail-closed một đường ghi/đọc không an toàn thay vì chỉ “tăng tolerance”.

### Bước 9 — Sửa tại đúng tầng

- Clock sync/drift → hạ tầng time services.
- Lost update → CAS/transaction.
- Concurrent edits → conflict-aware merge.
- Old owner write → fencing.
- Projection replay → revision/offset guard.
- TTL expiry bug → authoritative expiry workflow.
- Global order cần thiết → sequencer/consensus.

### Bước 10 — Kiểm chứng và đối soát

Thử clock skew/network lag, so source với projections, xác minh state cuối, audit các record từng bị LWW chọn sai. **Khắc phục clock không tự sửa các cập nhật đã mất.**

## 41. Các hiểu nhầm thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Hai máy dùng UTC nên đồng hồ không lệch.” | UTC là chuẩn biểu diễn, không bảo đảm đồng bộ chính xác |
| “Timestamp có nanosecond nên chính xác nanosecond.” | Độ phân giải khác độ chính xác |
| “Số timestamp lớn hơn chứng minh xảy ra sau.” | Clock skew và source timestamp có thể đảo thứ tự |
| “NTP bảo đảm mọi sự kiện có global order.” | NTP đồng bộ clock, không tạo causal/commit order |
| “Monotonic clock dùng được làm timestamp toàn cầu.” | Chỉ đo elapsed time trong phạm vi nguồn thích hợp |
| “Instant.now luôn tăng trong một process.” | Wall clock có thể nhảy lùi |
| “Lamport clock cho biết thời gian thật.” | Nó là counter logic |
| “Lamport L(a)<L(b) chứng minh a gây b.” | Chỉ chiều happened-before ⇒ L(a)<L(b) |
| “Vector clock tự chọn một winner.” | Nó giúp phát hiện concurrency, merge policy cần riêng |
| “LWW tức người sửa cuối cùng thắng.” | Nó chọn theo timestamp/tie-breaker policy |
| “Timestamps bằng nhau sẽ tự giữ cả hai writes.” | Cần tie/resolution protocol rõ |
| “Timestamp tương lai vô hại.” | Có thể shadow nhiều updates |
| “Quorum sửa được LWW clock skew.” | Quorum ACK và conflict resolution là hai cơ chế khác |
| “ObjectId sort là commit order MongoDB.” | Có thể sinh ở client, không bảo đảm global commit |
| “HLC tự cho strict serializability.” | Cần protocol và điều kiện đồng thuận/commit |
| “Consensus log index so được giữa mọi shards.” | Thứ tự index chỉ có ý nghĩa trong log group |
| “Lease hết hạn thì worker cũ chắc chắn dừng.” | Cần fencing/enforcement |
| “TTL là timer chính xác cho business cancellation.” | Cần expiry semantics và state transition đúng |
| “Kafka offset lớn hơn nghĩa xảy ra muộn hơn ở mọi partition.” | Offset thuộc từng partition |
| “Event đến sau nghĩa event được tạo sau.” | Network, queue và replay có thể đảo arrival |
| “Read replica thấy bản mới nhất sau mỗi ACK.” | Còn read concern/replication lag |
| “CDC timestamp thể hiện full commit order giữa mọi shards.” | Cần guarantee của source/protocol |
| “CRDT bảo vệ tất cả invariants.” | Hội tụ không đồng nghĩa không oversell |
| “CAS và idempotency là một.” | Một cái kiểm tra state, một cái dedup intent |
| “Sửa clock là tự lấy lại cập nhật bị mất.” | Cần audit/reconciliation |
| “Một clock offset bình quân 0 nghĩa mọi node chuẩn.” | Các offsets trái dấu có thể triệt tiêu |
| “Thêm tie-breaker tạo thứ tự vật lý đúng.” | Tie-breaker chỉ tạo deterministic total order |

## 42. Bài tập thực hành

### Bài 1 — LWW đảo thứ tự

Write A xảy ra lúc thực 10:00:00, clock A nhanh 10 giây. Write B xảy ra 2 giây sau, clock B chậm 5 giây.

**Hỏi:** Timestamps lần lượt là gì? LWW timestamp-based có thể chọn bản nào?

**Gợi ý:** A=10:00:10, B=09:59:57. LWW chọn A dù B đến sau về real-time.

### Bài 2 — UTC và skew

Hai máy cùng xuất UTC; A lệch +250 ms, B lệch -150 ms.

**Hỏi:** Pairwise clock skew là bao nhiêu?

**Gợi ý:** Chênh 400 ms.

### Bài 3 — Drift

Clock chạy nhanh 20 ppm trong 2 giờ không điều chỉnh.

**Hỏi:** Offset có thể tích lũy khoảng bao nhiêu?

**Gợi ý:** `7200 × 20 / 1.000.000 = 0,144 s`, tức 144 ms trong mô hình.

### Bài 4 — Độ phân giải

Một log có timestamp tới nanosecond nhưng clock offset 500 ms.

**Hỏi:** Có thể phân biệt chắc hai events cách nhau 20 ms ở hai máy chỉ từ timestamp không?

**Gợi ý:** Không, độ chính xác/offset quá kém; cần assumptions khác.

### Bài 5 — Monotonic deadline

Service dùng `currentTimeMillis()` để đo timeout; NTP chỉnh clock lùi 2 giây.

**Hỏi:** Tác động và phương án tốt hơn?

**Gợi ý:** Elapsed time có thể âm; dùng monotonic clock local như `nanoTime()`.

### Bài 6 — Lamport update

Local Lamport=4, nhận message mang Lamport=9.

**Hỏi:** Counter mới theo quy tắc thường dùng là bao nhiêu?

**Gợi ý:** `max(4,9)+1=10`.

### Bài 7 — Converse của Lamport

Hai events concurrent có `L(A)=3`, `L(B)=8`.

**Hỏi:** Có thể kết luận A gây ảnh hưởng B không?

**Gợi ý:** Không. L nhỏ hơn không chứng minh happened-before.

### Bài 8 — Vector concurrency

A=`[2,0]`, B=`[0,2]`.

**Hỏi:** Chúng có quan hệ `<` component-wise không?

**Gợi ý:** Không theo cả hai chiều; concurrent.

### Bài 9 — Vector descendant

A=`[2,1]`, B=`[2,3]`.

**Hỏi:** Quan hệ causal nào được biểu diễn?

**Gợi ý:** A<B component-wise.

### Bài 10 — Merge vector

A=`[2,0,1]`, B=`[1,4,0]`.

**Hỏi:** Merge metadata bằng component-wise max cho kết quả nào?

**Gợi ý:** `[2,4,1]`.

### Bài 11 — HLC local

HLC hiện tại `(physical=100,logical=3)`, wall clock hiện tại=98.

**Hỏi:** Một local event mới có HLC khái niệm bao nhiêu?

**Gợi ý:** `(100,4)` theo pseudocode.

### Bài 12 — HLC receive

Local `(100,2)` nhận remote `(100,5)`, wall clock=99.

**Hỏi:** HLC mới theo pseudocode là gì?

**Gợi ý:** `(100,6)`.

### Bài 13 — Khoảng bất định

A trong `[100,120]` ms, B trong `[130,150]` ms, giả định bounds đúng.

**Hỏi:** Có suy A trước B không?

**Gợi ý:** Có, vì `max A < min B`.

### Bài 14 — Khoảng giao nhau

A trong `[100,140]`, B trong `[120,160]`.

**Hỏi:** Có kết luận mốc thực nào trước không?

**Gợi ý:** Không chỉ từ hai bounds này.

### Bài 15 — ObjectId

Hai ObjectIds do hai clients tạo cùng giây, một insert commit trễ hơn.

**Hỏi:** Có dùng `_id DESC` làm thứ tự commit chắc chắn không?

**Gợi ý:** Không.

### Bài 16 — Cassandra future timestamp

Một update cell dùng timestamp năm 2030 do client lỗi, những updates bình thường dùng năm 2026.

**Hỏi:** Rủi ro và hướng điều tra?

**Gợi ý:** Bản tương lai có thể shadow updates, cần xem write timestamp metadata và reconciliation; không chỉ sửa field `updated_at`.

### Bài 17 — CAS

Hai writers cùng đọc version 7 rồi update với `IF version=7`.

**Hỏi:** Có thể cả hai cùng đổi version sang 8 trên một authoritative item với CAS đúng không?

**Gợi ý:** Không; một update có thể thắng, bên còn lại cần xử lý conflict.

### Bài 18 — Retry timeout

CAS write timeout nhưng thật ra đã commit version 8.

**Hỏi:** Nếu retry với expectedVersion=7 và nhận condition failed, có được kết luận request ban đầu thất bại không?

**Gợi ý:** Không. Cần operation ID/outcome lookup để biết ai đã tạo version 8.

### Bài 19 — Lease và pause

Worker A có lease, bị GC pause. Worker B lấy lease mới, A tỉnh lại.

**Hỏi:** Cần gì để ngăn A ghi muộn?

**Gợi ý:** Fencing token được nguồn authoritative enforce.

### Bài 20 — Log index hai shards

Shard 1 index 200, shard 2 index 900.

**Hỏi:** Event shard 2 có chắc xảy ra sau shard 1 không?

**Gợi ý:** Không. Index không cùng dãy.

### Bài 21 — Event-time versus arrival-time

Mobile event tạo lúc 09:00, gửi đến server 10:00; web update được commit 09:30.

**Hỏi:** Có thể chọn winner bằng cách nào và phải công bố điều gì?

**Gợi ý:** Cần domain merge policy, version/CAS hoặc conflict detection; arrival/event time đều có giới hạn.

### Bài 22 — Delta event

Projection đã thấy `delta seq=9` nhưng chưa thấy `seq=8`.

**Hỏi:** Có được bỏ seq8 khi tới muộn như snapshot cũ không?

**Gợi ý:** Không nếu delta cần áp dụng; cần gap/replay/order policy.

### Bài 23 — CRDT counter

Hai vùng offline cùng tăng viewCount 1.

**Hỏi:** Vì sao LWW scalar có thể mất một increment? Loại cấu trúc nào có thể hữu ích?

**Gợi ý:** Chỉ giữ một scalar winner; counter CRDT/atomic increments phù hợp.

### Bài 24 — Stock

Stock=1, A/B đồng thời reserve 1.

**Hỏi:** Counter CRDT tự hội tụ có bảo đảm không oversell không?

**Gợi ý:** Không. Cần quotas/consensus/owner hoặc conditional transaction.

### Bài 25 — Revocation

Quyền user bị thu hồi tại A, B có cache active cũ kèm timestamp lớn hơn.

**Hỏi:** Có nên cho truy cập chỉ vì B có timestamp lớn hơn không?

**Gợi ý:** Không. Dùng authoritative authz/minimum revocation version/fail-closed.

### Bài 26 — Global ordering

Hệ dùng per-shard log order và cần một báo cáo transaction toàn cụm.

**Hỏi:** Vì sao không chỉ merge theo index? Cần thêm cơ chế gì?

**Gợi ý:** Index độc lập; cần snapshot/transaction protocol hoặc global ordering/watermark được công bố.

### Bài 27 — TTL business

Một reservation có TTL=60 s. Sau 60 s bản ghi bị xóa ở store, nhưng stock chưa được trả lại.

**Hỏi:** TTL có thực hiện nghiệp vụ hoàn tác không?

**Gợi ý:** Không tự động; cần state transition và release idempotent.

### Bài 28 — Test skew

Bài kiểm thử chỉ chạy mọi node cùng clock chuẩn và không có event đến muộn.

**Hỏi:** Những tình huống nào nên thêm?

**Gợi ý:** ±clock skew, clock step, concurrent writes, replay out-of-order, lease pause, future ts, replica lag.

### Bài 29 — Monitoring

A offset +700 ms, B offset -700 ms.

**Hỏi:** Vì sao avg offset có thể bằng 0 nhưng vẫn nguy hiểm?

**Gợi ý:** Pairwise skew 1.400 ms; cần max absolute offset và phân bố.

### Bài 30 — Thiết kế xung đột

Một API quản lý giá sản phẩm cho phép chỉnh từ hai vùng.

**Hỏi:** Hãy thiết kế schema, CAS/revision, operationId, owner/failover, audit timestamps và behavior khi hai updates concurrent.

**Gợi ý:** Authority quyết định revision; expectedVersion+atomic write; giữ operation ID để retry; fencing khi đổi owner; log wall times chỉ để quan sát; trả conflict hoặc merge theo workflow.

## 43. Checklist triển khai

Trước khi dùng thời gian để phân xử xung đột trong NoSQL, hãy xác nhận:

- **Timestamp được cấp bởi client, server hay transaction coordinator?**
- **Đang so sánh thời điểm tạo, nhận, commit hay visible?**
- **Clock offset/drift có được đo và giới hạn đáng tin không?**
- **Timestamp có thể nhảy lùi hoặc trùng độ phân giải không?**
- **Nếu timestamp bằng nhau, tie-breaker là gì?**
- **Thứ tự yêu cầu là causal, real-time, per-key hay global?**
- **LWW có làm mất cập nhật mà business không chấp nhận không?**
- **Có CAS/revision hoặc multi-version conflict detection không?**
- **Một operation ID có được dùng lại khi retry không?**
- **Read replica/index/cache có làm state trông cũ hơn không?**
- **HLC/vector metadata có phạm vi và replay policy rõ không?**
- **Log index của các shards có bị so sánh sai không?**
- **Lease expiry có đi kèm fencing ở nguồn không?**
- **TTL có bị hiểu nhầm thành business cancellation atomic không?**
- **Delete/tombstone có bị overshadow hoặc hồi sinh không?**
- **CDC, broker, search có xử lý duplicate và out-of-order không?**
- **Monitoring dùng max offset và sync health thay vì chỉ average không?**
- **Có test lệch đồng hồ, future timestamp, pause, failover không?**
- **Có quy trình audit/khôi phục các updates đã bị chọn sai winner không?**

## 44. Kết luận

**Đồng hồ của máy tính không phải một nguồn sự thật tuyệt đối về thứ tự sự kiện trong hệ NoSQL phân tán.** Các clocks có offset, drift, độ phân giải hữu hạn và có thể bị điều chỉnh; timestamps từ client, coordinator, replica, CDC và index mô tả những mốc khác nhau. Một bản ghi có timestamp lớn hơn **không nhất thiết** được người dùng thực hiện sau hoặc được database commit sau.

Lamport clocks giúp giữ quan hệ nhân quả đã biết; vector clocks có thể phát hiện một số sửa đổi concurrent; HLC kết hợp logic và tín hiệu thời gian vật lý. Nhưng không cơ chế timestamp đơn lẻ nào tự tạo **linearizability, global transaction order hoặc business correctness**. Với những bất biến như tồn kho, tiền và quyền, cần **CAS/transaction, authoritative owner, fencing, idempotency, consensus hoặc conflict-aware merge** theo đúng phạm vi.

Thiết kế đáng tin là **định nghĩa rõ “mới nhất” có nghĩa gì, chọn loại thứ tự phù hợp, phân biệt thời gian hiển thị với thứ tự quyết định, theo dõi clock health, kiểm thử sai lệch và bảo vệ dữ liệu bằng protocol có thể kiểm chứng**. Khi hai cập nhật đồng thời, hệ cần một chính sách giải quyết xung đột được nghiệp vụ chấp nhận, chứ không nên giả định chiếc đồng hồ lớn hơn luôn nói đúng sự thật.
