# Version number, logical clock và quan hệ trước-sau

Trong một hệ NoSQL phân tán, nhiều replica có thể nhận thay đổi tại những thời điểm khác nhau. Một sự kiện có thể đến chậm, bị phát lại sau timeout hoặc bị ghi vào log ở máy có đồng hồ lệch. Nếu chỉ nhìn vào thời gian ghi `updatedAt` hoặc một số `version` mà chưa hiểu ý nghĩa của chúng, hệ thống dễ **ghi đè dữ liệu mới, bỏ sót xung đột, áp event cũ lên trạng thái mới hoặc hợp nhất sai ý định người dùng**.

Để xử lý xung đột và đồng bộ đúng, cần phân biệt ba lớp thông tin:

- **Version number:** Phiên bản của một entity, một mutation hay một dòng log trong một phạm vi nhất định. Thường dùng để chống lost update, kiểm tra precondition hoặc phát hiện event cũ.
- **Logical clock:** Đồng hồ biểu diễn **thứ tự logic của sự kiện**, không cố gắng đo số giây thật. Lamport clock và vector clock cung cấp những mức thông tin khác nhau về quan hệ nhân quả.
- **Quan hệ trước–sau (`happens-before`):** Quan hệ nhân quả từng phần giữa các sự kiện, hình thành từ thứ tự trong process, việc gửi/nhận thông điệp và tính bắc cầu. Hai sự kiện không có quan hệ này theo cả hai chiều là **đồng thời theo nghĩa nhân quả (`concurrent`)**, dù chúng xảy ra ở hai thời điểm thực khác nhau.

**Kết luận quan trọng cần đạt:** “Version lớn hơn” không phải lúc nào cũng có nghĩa “biết về tất cả thay đổi trước đó”. “Timestamp lớn hơn” không chứng minh một sự kiện xảy ra *sau* về mặt nhân quả. Và hai replica có thể đều lưu giá trị hợp lệ nhưng **chưa có đủ thông tin để tự chọn một bản thắng đúng theo nghiệp vụ**.

Trong chương **Xung đột và đồng bộ** của Database No SQL, bài này xây dựng tư duy từ lịch sự kiện, ví dụ tính toán, mã Java, cách quản lý phiên bản entity/event, đến chính sách xử lý conflict và kiểm thử.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích **event**, **process**, **message**, **partial order**, **causality** và **concurrent events**.
2. Định nghĩa `happens-before` theo ba quy tắc cơ bản, phân biệt với thứ tự theo đồng hồ vật lý.
3. Gán và cập nhật **Lamport scalar clock** cho local event, send, receive; chứng minh vì sao `a → b ⇒ L(a) < L(b)` nhưng chiều ngược lại không đúng.
4. Dùng **vector clock** để nhận ra một phiên bản là tổ tiên của phiên bản khác hay hai phiên bản concurrent.
5. So sánh **per-record version**, **log offset**, **leader term**, **Lamport timestamp**, **vector clock** và **hybrid logical clock (HLC)**.
6. Thiết kế **optimistic concurrency control/CAS** với `expectedVersion` và hiểu hạn chế trong multi-writer/multi-region.
7. Xử lý **out-of-order event, duplicate delivery, retry sau timeout, tombstone và resynchronization** mà không làm trạng thái đi lùi.
8. Biết vì sao **last-write-wins (LWW)** có thể hội tụ nhưng mất một thay đổi đã được xác nhận.
9. Chọn giữa **reject conflict, merge theo domain, multi-value register, CRDT và single authority** theo bất biến nghiệp vụ.
10. Xây dựng timeline và bài test giúp phân biệt **thứ tự tổng**, **nhân quả**, **tính mới của bản ghi** và **consistency của API**.

## 2. Bài toán xuyên suốt: hai replica cùng cập nhật hồ sơ khách hàng

Giả sử một khách hàng lưu hồ sơ trên hai region A và B:

~~~json
{
  "tenantId": "shop-7",
  "customerId": "C42",
  "shippingAddress": "12 Nguyen Trai",
  "phone": "0900000000",
  "version": 7
}
~~~

Trước khi mạng lỗi, cả hai replica đều có **cùng dữ liệu ở version 7**.

~~~text
                   Customer C42
                        |
             +----------+----------+
             |                     |
         Replica A             Replica B
         version 7             version 7
         address=old           address=old
             |                     |
      Client trên A          Client trên B
~~~

Trong một lần phân tách mạng:

| Thứ tự quan sát cục bộ | Region A | Region B |
| --- | --- | --- |
| 1 | Đọc C42 ở version 7 | Đọc C42 ở version 7 |
| 2 | Cập nhật `shippingAddress` thành địa chỉ mới | Cập nhật `phone` thành số mới |
| 3 | A xác nhận local write | B xác nhận local write |
| 4 | Mạng khôi phục, hai phía trao đổi thay đổi | Hai thay đổi cần được giải quyết |

Cả A và B có thể tự tăng version cục bộ thành 8:

~~~text
Replica A: version=8, address=new, phone=old
Replica B: version=8, address=old, phone=new
~~~

**Cùng version 8 không có nghĩa hai bản giống nhau.** Khi không có một authority tạo version duy nhất cho từng mutation, con số scalar cục bộ **không đủ để biểu diễn nhánh xung đột**.

Ba câu hỏi cần tách:

1. **Có phải A và B được sinh ra từ cùng bản gốc?** Có, trong ví dụ cả hai bắt đầu từ v7.
2. **A có biết về update B khi A ghi không?** Không.
3. **B có biết về update A khi B ghi không?** Không.

Vì vậy hai write **concurrent theo quan hệ nhân quả**. Một timestamp nào đó lớn hơn không làm chúng tự trở thành quan hệ “A biết B”.

## 3. Thời gian vật lý, thứ tự logic và quan hệ nhân quả

### 3.1. Wall-clock timestamp đo “khi nào” theo một đồng hồ

Ví dụ:

~~~text
Node A local clock: 10:00:00.500
Node B local clock: 10:00:00.200
~~~

Không được kết luận write A xảy ra sau write B chỉ vì timestamp A lớn hơn. Node A có thể chạy **nhanh hơn thời gian thật** 400 ms và B chậm 300 ms. NTP, virtual machine pause, leap adjustment hoặc việc sửa đồng hồ đều ảnh hưởng timestamp.

Wall-clock hữu ích cho audit, TTL, retention và báo cáo nếu quản lý clock uncertainty; nó **không tự là bằng chứng của nhân quả**.

### 3.2. Quan hệ trước–sau là quan hệ từng phần

Ký hiệu:

\[
a \rightarrow b
\]

đọc là **“sự kiện a xảy ra trước b theo quan hệ nhân quả (`happens-before`)”**.

Điều này **không** yêu cầu biết bao nhiêu mili giây giữa a và b. Quan hệ được suy từ thứ tự chương trình và trao đổi thông điệp.

Hai sự kiện **concurrent** nếu:

\[
\neg(a\rightarrow b)\quad\land\quad\neg(b\rightarrow a)
\]

Concurrent ở đây **không có nghĩa xảy ra đúng cùng mili giây**. Nó có nghĩa mô hình không có chuỗi phụ thuộc nhân quả nối hai sự kiện.

### 3.3. Đồng hồ logic không nhất thiết đo thời gian thật

Lamport clock gán một số thứ tự tăng theo các sự kiện. Vector clock dùng nhiều thành phần để biểu diễn kiến thức nhân quả. Cả hai có thể hoạt động mà không cần đồng bộ wall-clock giữa các server.

### 3.4. Version number có nhiều nghĩa

“Version” trong tài liệu hệ thống có thể là:

- Số lần document đã thay đổi trong một authority.
- Một token cho **optimistic concurrency control**.
- Số `offset` trong một log partition.
- Sequence number của một shard.
- Leader `term` hoặc `epoch`.
- Timestamp logic của sự kiện.
- Một vector chứa counters theo replica.
- Một ETag opaque mà client chỉ được **so bằng/khác**.

Không được so sánh số thuộc **hai phạm vi khác nhau** rồi tuyên bố cái lớn hơn là trạng thái mới hơn của cùng dữ liệu.

## 4. Định nghĩa quan hệ happens-before

Theo mô hình sự kiện phân tán, `→` được xác định bởi các quy tắc:

1. **Program order:** Nếu a và b thuộc cùng một process và a diễn ra trước b trong thứ tự thực thi, thì `a → b`.
2. **Message order:** Nếu a là hành động **send** một thông điệp và b là hành động **receive** của chính thông điệp đó, thì `a → b`.
3. **Transitivity:** Nếu `a → b` và `b → c`, thì `a → c`.

Không tự thêm `a → b` chỉ vì timestamp vật lý của a nhỏ hơn b hoặc vì hai event cùng nằm trong một hệ thống.

### 4.1. Sơ đồ message nhân quả

~~~text
Process A                      Process B

A1: local change
    |
A2: send message M ---------> B2: receive M
    |                              |
A3: local work                    B3: update state
                                   |
                                   v
                                B4: send reply
                                   |
A4: receive reply <---------------+
~~~

Ta suy được:

~~~text
A1 -> A2
A2 -> B2
B2 -> B3 -> B4
B4 -> A4
=> A1 -> B3, A1 -> A4
~~~

Nhưng chưa chắc có quan hệ giữa **A3** và **B3**, vì hai event có thể diễn ra độc lập sau send M. Biết rằng A2 trước cả hai không cho phép suy A3 trước B3 hoặc ngược lại.

### 4.2. Đặc tính của thứ tự từng phần

| Thuộc tính | Diễn giải |
| --- | --- |
| Nhân quả | A có thể ảnh hưởng B qua chương trình/message |
| Bắc cầu | A trước B, B trước C thì A trước C |
| Không bắt buộc so được mọi cặp | Có thể có hai event concurrent |
| Không đo độ dài thời gian | Chỉ có thông tin quan hệ |
| Phụ thuộc mô hình quan sát | Truyền dữ liệu “ngoài băng” không được ghi thành message có thể khiến trace thiếu causal edge |

### 4.3. Ví dụ về hai write concurrent

~~~text
Region A                         Region B
A0: read version 7               B0: read version 7
    |                                 |
A1: write address                B1: write phone
    |                                 |
A2: ACK                          B2: ACK

          (network link disconnected)
~~~

Chưa có message nối A1 với B1, nên theo history này:

~~~text
not (A1 -> B1)
not (B1 -> A1)
=> A1 concurrent with B1
~~~

Đây là lý do không thể xử lý xung đột chỉ bằng `if incoming.version > local.version` khi version được cấp **độc lập**.

## 5. Lamport logical clock: đồng hồ scalar

Lamport clock dùng **một số nguyên tăng dần trên mỗi process**. Mỗi local event/send/receive có một timestamp logic.

Giả sử `L_i` là counter của process i, ban đầu bằng 0.

### 5.1. Quy tắc cập nhật

**Local event hoặc send:**

\[
L_i\leftarrow L_i+1
\]

Nếu send message M, gắn `timestamp = L_i` vào M.

**Receive message M có timestamp t:**

\[
L_i\leftarrow\max(L_i,t)+1
\]

Event receive được gán timestamp mới này.

### 5.2. Ví dụ cụ thể

~~~text
Process A                              Process B

A1 local: L_A=1                        B1 local: L_B=1
A2 send M: L_A=2 -------------------> B2 receive M:
                                      L_B=max(1,2)+1=3
A3 local: L_A=3                        B3 local: L_B=4
~~~

Các mối quan hệ:

~~~text
A1 -> A2 -> B2 -> B3
L(A1)=1 < L(A2)=2 < L(B2)=3 < L(B3)=4
~~~

Với A3 và B3 có thể **không có quan hệ nhân quả**, dù `L(A3)=3 < L(B3)=4`.

### 5.3. Tính chất cần nhớ

\[
a\rightarrow b\quad\Longrightarrow\quad L(a)<L(b)
\]

Nhưng chiều ngược lại:

\[
L(a)<L(b)\quad\not\Longrightarrow\quad a\rightarrow b
\]

**Lamport clock là điều kiện cần cho một quan hệ nhân quả, không phải công cụ xác định chính xác mọi cặp sự kiện có quan hệ nhân quả hay concurrent.**

### 5.4. Số bằng nhau trên hai process

Hai event độc lập có thể cùng Lamport timestamp 5. Không nên hiểu đó là cùng event hoặc cùng dữ liệu.

Để sắp xếp mọi event một cách ổn định, có thể dùng cặp:

~~~text
(lamportCounter, processId)
~~~

Ví dụ:

~~~text
(5, "A") < (5, "B")
~~~

theo thứ tự từ điển khi counter bằng nhau. Đây là **total order tùy chọn**, nhưng tie-breaker **không làm xuất hiện quan hệ nhân quả chưa từng tồn tại**.

### 5.5. Java: Lamport clock đơn giản

~~~java
public final class LamportClock {
    private long counter = 0;

    public synchronized long event() {
        return ++counter;
    }

    public synchronized long send() {
        return ++counter;
    }

    public synchronized long receive(long messageTimestamp) {
        counter = Math.max(counter, messageTimestamp) + 1;
        return counter;
    }

    public synchronized long value() {
        return counter;
    }
}
~~~

Ví dụ sử dụng khái niệm:

~~~java
LamportClock a = new LamportClock();
LamportClock b = new LamportClock();

long a1 = a.event();       // 1
long a2 = a.send();        // 2, gắn vào message M
long b1 = b.event();       // 1
long b2 = b.receive(a2);  // max(1,2)+1 = 3
~~~

**Giới hạn của demo:**

- `synchronized` chỉ bảo vệ object Java **trong cùng JVM**, không phải distributed consensus.
- Counter chỉ có nghĩa theo một **incarnation/process identity**; restart từ 0 mà không có generation bền vững có thể trùng timestamp.
- Không được dùng Lamport scalar làm bằng chứng CAS/uniqueness toàn cluster nếu không có protocol cấp quyền/commit tương ứng.
- Nếu counter sắp tràn hoặc bị reset, cần lifecycle/epoch phù hợp, không im lặng quay về 0.

## 6. Lamport total order khác causal order

Xét hai process không gửi message cho nhau:

~~~text
Process A: local update address, L=1
Process B: local update phone,   L=1
~~~

Một hệ có thể chọn:

~~~text
(1,A) < (1,B)
~~~

và xử lý B sau A theo total order. Đây là **quyết định sắp thứ tự**, không chứng minh update B được sinh ra sau khi B đã quan sát A.

### 6.1. Khi total order hữu ích

- Sắp thứ tự deterministic để các node nhận **cùng danh sách event** theo một quy tắc.
- Ghi log và debug.
- Là thành phần trong một số thuật toán mutual exclusion/ordering, cùng nhiều điều kiện bổ sung.

### 6.2. Khi total order là chưa đủ

- Phát hiện hai bản update độc lập cần merge.
- Quyết định một write đã nhìn thấy một write khác hay chưa.
- Bảo vệ uniqueness hoặc stock bằng chỉ một comparator timestamp.
- Bảo đảm event đã được commit qua quorum.

**Cần phân biệt “có thể sắp thứ tự mọi event” với “hệ đã thống nhất commit mọi event theo thứ tự ấy”.** Lamport timestamp không tự triển khai consensus.

## 7. Per-record version number và optimistic concurrency control

Version number phổ biến nhất trong nghiệp vụ là **version nguyên của một aggregate/document**, tăng khi mutation hợp lệ được commit.

Ví dụ:

~~~json
{
  "orderId": "O900",
  "status": "CREATED",
  "version": 17
}
~~~

Hai client cùng đọc v17:

~~~text
Client A reads v17  -------> update status=PAID, expectedVersion=17
Client B reads v17  -------> update status=CANCELLED, expectedVersion=17
~~~

Nếu database bảo đảm **compare-and-set nguyên tử trên cùng authoritative record**, một update thắng và tăng thành v18; update kia thất bại vì version không còn 17.

### 7.1. Quy tắc CAS

~~~text
if stored.version == expectedVersion
   and businessTransitionAllowed(stored, mutation):
    atomically apply mutation
    stored.version = expectedVersion + 1
    return SUCCESS
else:
    return CONFLICT
~~~

“Đọc version rồi kiểm tra bằng `if` ở application” **không** thay được CAS tại database: giá trị có thể đổi giữa lúc đọc và lúc ghi.

### 7.2. Ví dụ SQL-like minh họa

~~~sql
UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE order_id = 'O900'
  AND status = 'CREATED'
  AND version = 17;
~~~

Ứng dụng kiểm tra số dòng được cập nhật:

~~~text
rowsAffected=1 -> conditional mutation succeeded
rowsAffected=0 -> state/version khác kỳ vọng, phải đọc lại
~~~

Đây là mô hình khái niệm của CAS; khả năng atomicity, điều kiện, transaction và read consistency phải được kiểm tra theo **engine NoSQL và API cụ thể**.

### 7.3. Ví dụ MongoDB-style

~~~javascript
db.orders.updateOne(
  {
    tenantId: "tenant-a",
    orderId: "O900",
    version: 17,
    status: "CREATED"
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
~~~

Với document/điều kiện phù hợp và hợp đồng atomic update của engine, một client thứ hai vẫn dùng `version:17` không nên thắng sau khi v18 đã được commit.

### 7.4. Vì sao retry sau conflict không giống retry sau timeout?

**Conflict:** Predicate đã không đạt; cần đọc lại entity và cân nhắc ý định mới.

**Timeout:** Mutation có thể đã áp nhưng response bị mất; retry không điều kiện có thể áp lần hai. Để an toàn cần **logicalOperationId và kết quả idempotent**, hoặc tra version/operation outcome theo nguồn có thẩm quyền.

### 7.5. Version tăng cục bộ khác version toàn cục

Một authority duy nhất có thể cấp v17→18→19 cho **một entity**; khi đó version cho biết thứ tự mutation được authority chấp nhận.

Nhưng nếu **hai replica không phối hợp** cùng cấp v18 cho hai write khác nhau, v18 **không phân biệt được xung đột**. Thêm một cơ chế cấp version có authority hoặc metadata nhân quả phong phú hơn là cần thiết nếu ứng dụng nhận multi-writer concurrent writes.

### 7.6. Version per entity không tự cho thứ tự giữa entities

~~~text
Order O900 version=42
Customer C42 version=13
~~~

Không được kết luận mutation của Order xảy ra sau mutation của Customer chỉ vì `42 > 13`. Hai counters thuộc **hai phạm vi khác nhau**.

### 7.7. ABA và vòng đời bản ghi

Trong CAS kiểu so giá trị, trạng thái có thể đổi:

~~~text
A -> B -> A
~~~

Client chỉ so `state=A` có thể không biết đã có hai mutation. Một version tăng đơn điệu giúp phát hiện:

~~~text
(A, v7) -> (B, v8) -> (A, v9)
~~~

Client giữ `expectedVersion=7` sẽ không nhầm trạng thái A ở v9 với A cũ. Tuy nhiên khi delete rồi recreate, nếu version **reset** mà key giữ nguyên, vấn đề ABA có thể quay lại; cần generation/epoch/tombstone hoặc ID mới theo domain.

## 8. Per-record version không phải thứ tự causal giữa các replica

Một scalar version duy nhất hữu ích nhất khi **mọi write cạnh tranh cùng một điểm kiểm tra atomic/authority**.

Trong hệ multi-writer:

~~~text
Base: C42 version 7

Region A accepts update A, says version 8.
Region B accepts update B, says version 8.
~~~

Nếu ứng dụng chỉ giữ `version=8`, nó không biết:

- Hai bản có cùng nội dung không?
- B có dựa trên A hay không?
- A có dựa trên B hay không?
- Đây có phải hai nhánh con của v7 không?

**Vector clocks/version vectors** được dùng để cung cấp thêm thông tin về quan hệ nhân quả giữa các phiên bản.

## 9. Vector clock: một bộ đếm theo mỗi actor hoặc replica

Một **vector clock** biểu diễn một tập counter logic theo các process/replica có định danh ổn định.

Với hai replica A và B:

\[
V=[v_A,v_B]
\]

Chẳng hạn, trong một mô hình truyền causal context đầy đủ:

~~~text
[3,1] = context đã biết 3 events của A
        và 1 event của B
~~~

Các thành phần không phải timestamp vật lý và cũng không phải số lượng document mỗi node lưu.

### 9.1. Quy tắc tăng và nhận message

Với tập process cố định, vector clock cổ điển:

1. Khởi tạo tất cả component bằng 0.
2. Trước local event hoặc send ở process i: tăng thành phần i một đơn vị.
3. Khi send: gắn snapshot vector vào message.
4. Khi receive có vector M: lấy max theo từng thành phần giữa vector cục bộ và M, rồi tăng thành phần của process nhận để ghi nhận receive event.

Với **object version vectors**, quy tắc có thể là “gộp context của các phiên bản đã đọc rồi increment một lần khi tạo phiên bản mới”, thay vì tăng cho từng local/send/receive event. Hai biến thể này liên quan nhưng không đồng nhất.

### 9.2. Ví dụ hai write concurrent

Ban đầu:

~~~text
A sees [0,0]
B sees [0,0]
~~~

Trong network partition:

~~~text
Replica A writes address -> [1,0]
Replica B writes phone   -> [0,1]
~~~

Hai vector:

\[
V_A=[1,0], \qquad V_B=[0,1]
\]

Không thể nói \(V_A\le V_B\), vì component A của V_A lớn hơn. Cũng không thể nói \(V_B\le V_A\), vì component B của V_B lớn hơn.

Kết luận: **hai write concurrent theo causal order đã được ghi nhận**.

### 9.3. Khi một phiên bản biết cả hai nhánh

Giả sử A nhận được bản B và tạo phiên bản mới dựa trên cả hai:

\[
\max([1,0],[0,1])=[1,1]
\]

Nếu A tạo một mutation tiếp theo:

\[
[1,1]\xrightarrow{\text{write tại A}}[2,1]
\]

Phiên bản [2,1] là **hậu duệ causal** của hai phiên bản [1,0] và [0,1] theo mô hình này.

| Phiên bản | Vector | Quan hệ |
| --- | --- | --- |
| Base | `[0,0]` | Tổ tiên |
| Write A | `[1,0]` | Concurrent với B |
| Write B | `[0,1]` | Concurrent với A |
| Context đã merge | `[1,1]` | Biết cả A và B |
| Write tiếp tại A | `[2,1]` | Descendant của cả A và B |

**Vector metadata có thể gộp bằng max từng counter, nhưng nội dung nghiệp vụ không tự gộp đúng bằng phép max đó.**

## 10. So sánh vector: before, after, equal, concurrent

Cho hai vector cùng tập actor:

\[
V=(v_1,\ldots,v_n), \quad W=(w_1,\ldots,w_n)
\]

Định nghĩa:

\[
V\preceq W\iff \forall i,\;v_i\le w_i
\]

V trước W nghiêm ngặt nếu:

\[
V\prec W\iff V\preceq W\ \land\ V\ne W
\]

Và chúng concurrent nếu:

\[
\neg(V\preceq W)\ \land\ \neg(W\preceq V)
\]

### 10.1. Bảng ví dụ

| V | W | Kết luận |
| --- | --- | --- |
| `[1,0]` | `[2,0]` | V before W |
| `[1,1]` | `[2,1]` | V before W |
| `[2,1]` | `[1,2]` | Concurrent |
| `[3,4]` | `[3,4]` | Equal |
| `[2,3]` | `[4,5]` | V before W |
| `[3,1]` | `[1,3]` | Concurrent |

### 10.2. Không so tổng counter

~~~text
A = [3,1]  sum=4
B = [1,3]  sum=4
~~~

Tổng bằng nhau nhưng A và B **concurrent**.

~~~text
A = [9,0]  sum=9
B = [0,4]  sum=4
~~~

Tổng A lớn hơn không chứng minh B là tổ tiên của A. **Phải so từng component.**

### 10.3. Actor thiếu trong map

Hệ thực có thể biểu diễn vector dạng:

~~~json
{
  "replica-a": 3,
  "replica-b": 1
}
~~~

Nếu protocol định nghĩa component vắng mặt là 0, ta có thể so các map có tập khóa khác nhau. Nhưng phải hiểu **actor incarnation/generation** để một node restart không tự nhận lại ID cũ với counter 0.

### 10.4. Vector chỉ phản ánh context đã được truyền

Nếu client đọc write A rồi gửi write B, nhưng client/replica B **không gửi kèm causal context của A**, vector tạo ở B có thể bỏ mất dependency. Một vector chỉ chính xác về causality khi quy tắc **cập nhật, truyền và nhận context** được tuân thủ.

## 11. Java: version vector và phép so sánh

Ví dụ Java biểu diễn vector bằng map; actor không có trong map được hiểu là 0. Mục đích là minh họa comparison semantics, không phải thư viện replication hoàn chỉnh.

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class VersionVector {
    public enum Relation {
        BEFORE, AFTER, EQUAL, CONCURRENT
    }

    private final Map<String, Long> counters;

    public VersionVector() {
        this.counters = new HashMap<>();
    }

    private VersionVector(Map<String, Long> data) {
        this.counters = new HashMap<>(data);
    }

    public VersionVector increment(String actorId) {
        Map<String, Long> next = new HashMap<>(counters);
        long oldValue = next.getOrDefault(actorId, 0L);
        next.put(actorId, Math.addExact(oldValue, 1));
        return new VersionVector(next);
    }

    public VersionVector join(VersionVector other) {
        Map<String, Long> next = new HashMap<>(counters);
        for (Map.Entry<String, Long> entry : other.counters.entrySet()) {
            next.merge(entry.getKey(), entry.getValue(), Math::max);
        }
        return new VersionVector(next);
    }

    public Relation compare(VersionVector other) {
        Set<String> actors = new HashSet<>(counters.keySet());
        actors.addAll(other.counters.keySet());

        boolean less = false;
        boolean greater = false;
        for (String actor : actors) {
            long left = counters.getOrDefault(actor, 0L);
            long right = other.counters.getOrDefault(actor, 0L);
            less |= left < right;
            greater |= left > right;
        }

        if (less && greater) return Relation.CONCURRENT;
        if (less) return Relation.BEFORE;
        if (greater) return Relation.AFTER;
        return Relation.EQUAL;
    }

    @Override
    public String toString() {
        return counters.toString();
    }
}
~~~

Ví dụ sử dụng:

~~~java
VersionVector base = new VersionVector();
VersionVector a1 = base.increment("A");  // {A=1}
VersionVector b1 = base.increment("B");  // {B=1}

System.out.println(a1.compare(b1));      // CONCURRENT

VersionVector context = a1.join(b1);    // {A=1, B=1}
VersionVector a2 = context.increment("A");

System.out.println(a1.compare(a2));      // BEFORE
System.out.println(b1.compare(a2));      // BEFORE
~~~

Giới hạn: mã không quản lý actor incarnation, persistence, event transport, duplicate delivery, causal context qua client hoặc dữ liệu siblings. `join` chỉ hợp nhất **metadata counters**, không phải business values.

## 12. Vector clock và metadata growth

Nếu mỗi client được cấp một component, một object từng được sửa bởi 10.000 client có thể có 10.000 entries. Đó là chi phí đáng kể về storage, network và merge.

Các giải pháp trong những giao thức cụ thể có thể gồm:

- **Replica-scoped version vectors:** Một component theo stable replica actor, không theo mọi người dùng.
- **Dotted version vectors:** Tách causal context khỏi dot/event identity mới.
- **Actor incarnation/epoch:** Node restart hoặc join/leave không làm trùng counter history.
- **Pruning/truncation có quy tắc:** Chỉ xóa metadata khi protocol cho phép mà không làm sai conflict detection.
- **Causal metadata theo log/partition scope** thay vì mỗi object có full vector.

### 12.1. Pruning tùy ý có thể làm sai lịch sử

~~~text
Original context: {A:5, B:8, C:3}
Pruned context:   {A:5, B:8}
~~~

Nếu C mang một phiên bản cũ quay lại, hệ có thể **nhầm sự kiện bị bỏ quên thành concurrent hoặc cho hồi sinh dữ liệu đã xóa**. Không tự cắt component “lâu không dùng” khi chưa hiểu semantics.

### 12.2. Actor identity cần bền vững

~~~text
Old actor A counter = 100.
New process reused ID A, counter = 0.
~~~

Điều này vi phạm giả định counter tăng đơn điệu trong cùng actor. Cần persist state hoặc tạo generation/actor ID mới theo protocol.

## 13. Causal context, sibling versions và merge theo domain

Giả sử hai phiên bản của Customer C42 sau partition:

~~~text
Version A:
  value  = {address:"new", phone:"000"}
  vector = {A:1}

Version B:
  value  = {address:"old", phone:"999"}
  vector = {B:1}
~~~

Khi nhận hai phiên bản concurrent, hệ dùng **multi-value register/siblings** có thể giữ cả hai:

~~~json
{
  "key": "C42",
  "siblings": [
    {
      "value": {"address": "new", "phone": "000"},
      "vector": {"A": 1}
    },
    {
      "value": {"address": "old", "phone": "999"},
      "vector": {"B": 1}
    }
  ]
}
~~~

### 13.1. Merge field độc lập

Nếu business cho phép tách địa chỉ và số điện thoại:

~~~json
{
  "address": "new",
  "phone": "999"
}
~~~

Phiên bản kết quả cần giữ causal context đã thấy **cả A/B**, sau đó tạo version/event mới. Nếu bỏ context, lần sync sau có thể lại coi các bản cũ là xung đột mới.

### 13.2. Không merge mọi field theo cách máy móc

Địa chỉ gồm street/city/postalCode có thể là **một đơn vị nghiệp vụ**. Trộn trường của hai bản update có thể tạo địa chỉ không ai từng xác nhận.

Chọn merge theo **domain invariants**, không vì có hai vector concurrent mà mặc nhiên chọn từng field có timestamp mới hơn.

### 13.3. Chi phí sibling

Giữ cả hai version tránh silently losing an update nhưng tăng storage, complexity của read API, reconciliation và UX. Nếu xung đột lặp nhiều lần, sibling set có thể lớn; cần merge/compaction policy rõ.

## 14. Dotted version vectors và dot của mutation

Dotted version vectors phân biệt:

~~~text
Causal context: {A:5, B:2}
New event dot:  (B,3)
~~~

Context biểu diễn lịch sử sự kiện đã thấy; dot là event identity của **mutation mới**. Tách hai phần có thể hữu ích khi diễn đạt concurrent writes ở một object.

### 14.1. Dot phải được cấp không trùng

Hai client có thể đọc cùng context rồi cùng gửi write qua một replica B. Nếu cả hai tự cộng counter trên client từ cùng snapshot, chúng có thể tạo trùng `(B,3)`.

Một protocol đúng phải **đảm bảo dot uniqueness theo actor/incarnation** và truyền causal context. Đây không phải bài toán có thể giải bằng cách increment JSON tùy ý.

### 14.2. Không tự triển khai version vectors đầy đủ từ demo

Để vận hành production cần xét actor membership, dot allocation, anti-entropy, deletion semantics, compaction, sibling resolution, crash recovery và retry; dùng khả năng đã được hỗ trợ/kiểm chứng bởi sản phẩm phù hợp.

## 15. Hybrid Logical Clock (HLC): vừa gần thời gian thật, vừa theo thứ tự logic

Lamport clock không đo thời gian vật lý. Vector clock cho biết causal ancestry nhưng metadata có thể lớn. **Hybrid Logical Clock (HLC)** kết hợp:

~~~text
HLC = (physicalComponent, logicalComponent)
~~~

Ý tưởng:

- Phần **physical** gần wall-clock nếu clock vật lý vận hành đúng trong giới hạn skew.
- Phần **logical** tăng để phân biệt sự kiện khi physical component không tăng hoặc khi nhận message từ một node có physical timestamp lớn hơn.
- Nếu a **happens-before** b và protocol cập nhật đúng, HLC của a phải nhỏ hơn HLC của b theo phép so lexicographic.

### 15.1. Local event

Giả sử đồng hồ đang giữ `(p,l)`, còn thời gian vật lý hiện hành là `now`:

~~~text
newP = max(now, p)

if newP == p:
    newL = l + 1
else:
    newL = 0
~~~

Gán timestamp `(newP,newL)` cho local event.

### 15.2. Khi nhận một message

Node nhận message có HLC `(p_m,l_m)`, đồng hồ cục bộ là `(p,l)`:

~~~text
nextP = max(now, p, p_m)

if nextP == p AND nextP == p_m:
    nextL = max(l, l_m) + 1
else if nextP == p:
    nextL = l + 1
else if nextP == p_m:
    nextL = l_m + 1
else:
    nextL = 0
~~~

Đây là **mô hình thuật toán HLC** cho local/receive event. Một implementation production còn cần đồng bộ truy cập, persistence/restart, giới hạn clock drift, overflow và encoding/tie-breaking.

### 15.3. Ví dụ clock vật lý lệch

~~~text
Node A wall clock = 1000
Node B wall clock =  995

A event: HLC (1000,0).
A sends message with (1000,0).

B receives:
  nextP = max(995,0,1000) = 1000
  nextL = 0 + 1 = 1
  B receive event HLC = (1000,1).
~~~

Vì `(1000,0) < (1000,1)`, receive event của B được gán sau send event của A **dù clock B chậm hơn clock A**.

### 15.4. HLC không xác định đầy đủ concurrency

Hai event độc lập có thể có:

~~~text
A: HLC (1000,0)
B: HLC (1001,0)
~~~

HLC(A) nhỏ hơn HLC(B), nhưng **không chứng minh A → B**. Có thể hai event concurrent và physical clocks đơn giản có giá trị khác.

HLC tạo một timestamp có thể sắp thứ tự tốt và tương thích causal order, **không thay vector clock khi cần nhận biết chính xác cặp event concurrent**.

### 15.5. Không tự suy HLC cấp linearizability

HLC timestamp không thay leader/quorum, transaction protocol hoặc read consistency. Có thể gán HLC hợp lý cho mutations nhưng vẫn trả dữ liệu stale từ replica.

Khi một node nhận timestamp physical component **rất xa trong tương lai**, HLC có thể tiếp tục giữ phần physical đó một thời gian. Cần đọc clock-skew assumptions của engine nếu dùng HLC để phối hợp dữ liệu hoặc phân tích TTL.

## 16. So sánh các loại clock/version

| Cơ chế | Thông tin lưu | Nhận ra concurrent writes? | Gần wall-clock? | Điểm dùng phù hợp |
| --- | --- | --- | --- | --- |
| `updatedAt` | Timestamp vật lý trên node | Không đáng tin chỉ từ timestamp | Có, với skew | Audit, TTL, reporting |
| Per-record `version` | Counter/generation trong một authority | CAS conflict trong phạm vi record | Không | Optimistic concurrency |
| Log offset | Vị trí trong một log partition | Không mặc nhiên giữa partitions | Không | Ordered replay trong partition |
| Lamport clock | Scalar counter | Không, chỉ một chiều suy ra | Không | Causal-compatible ordering |
| Vector clock | Counter theo actors | Có, nếu context được truyền đầy đủ | Không | Conflict detection |
| Dotted version vector | Context và event dot | Có, theo protocol | Không | Multi-writer versions |
| HLC | Physical + logical component | Không đầy đủ như vector | Gần wall-clock có điều kiện | Distributed timestamping |
| Leader term/epoch | Thế hệ quyền ghi/leadership | Không thay vector clock | Không | Fencing và consensus |
| ETag opaque | Token đại diện resource state | Chủ yếu equality/precondition | Không nhất thiết | HTTP conditional requests |

### 16.1. Chọn công cụ từ câu hỏi

- “Order có bị ai sửa từ khi tôi đọc không?” → `version`/CAS.
- “Event nào ở sau event nào trong một log?” → partition offset/sequence với đúng log scope.
- “A có thể ảnh hưởng B qua messages không?” → Lamport/vector reasoning.
- “Hai writes thực sự độc lập cần giữ cả hai không?” → vector clock/version vector hoặc metadata nhân quả tương đương.
- “Cần timestamp gần thời gian thật để sắp log?” → HLC/physical timestamp có policy clock-skew.
- “Worker cũ có còn quyền ghi không?” → term/epoch/fencing tại destination.
- “Write đã được đồng thuận commit chưa?” → consensus/transaction/commit protocol, **không chỉ một timestamp**.

## 17. Last-write-wins: hội tụ nhưng có thể mất ý định

Một chính sách phổ biến là **LWW**: hai replica chọn giá trị có timestamp được xem là mới hơn; khi timestamp bằng nhau, có thể dùng tie-breaker.

Ví dụ:

~~~text
Region A:
  status=CANCELLED
  timestamp=1002
  ack=SUCCESS

Region B:
  status=CONFIRMED
  timestamp=1003
  ack=SUCCESS

Reconcile with LWW -> CONFIRMED.
~~~

Hai replica có thể hội tụ về `CONFIRMED`, nhưng user A **đã được báo hủy thành công**. Kết quả cuối không tự bảo đảm các cam kết nghiệp vụ trước đó đúng.

### 17.1. “Last” là theo timestamp nào?

Cần xác minh:

- Client timestamp hay server timestamp?
- Wall-clock, Lamport, HLC, log sequence hay một phiên bản khác?
- Khi hai timestamps bằng nhau, tie-breaker là gì?
- Khi clocks skew, write nào có thể thắng?
- Có trường hợp một write đến muộn nhưng causal descendant bị mất không?

### 17.2. Lamport timestamp cũng không tự giải quyết merge

Nếu A và B concurrent, hệ có thể chọn deterministic winner theo `(lamport,actorId)`. Điều này **cho một total order**, nhưng không suy được “đây là lựa chọn đúng” cho một invoice, thanh toán hay địa chỉ.

### 17.3. Khi nào LWW có thể chấp nhận?

- Cache/read model có thể rebuild từ nguồn có thẩm quyền.
- Preference không quan trọng và ứng dụng chấp nhận mất concurrent update.
- State được định nghĩa rõ ràng theo chính sách winner có thứ tự.
- UI/workflow ghi nhận việc một update có thể bị thay thế.

Khi **không được mất bất cứ intent nào**, chọn LWW mù thường không phù hợp.

### 17.4. Timestamp cao bất thường có thể ảnh hưởng lâu dài

Nếu một writer có clock chạy nhanh nhiều phút, LWW theo wall-clock có thể khiến những write hợp lệ sau đó trên node khác **liên tục thua**, dù thực tế chúng xảy ra sau. Đây là một lý do cần clock-skew handling, authority hoặc merge policy khác.

## 18. CRDT: hội tụ do đại số, nhưng vẫn có giới hạn

**Conflict-free Replicated Data Types (CRDTs)** được thiết kế để những cập nhật phù hợp có thể merge và hội tụ theo quy tắc toán học. Một số CRDT không cần full vector clock trên mỗi mutation; chi tiết metadata tùy loại.

### 18.1. Ví dụ G-Counter

Giả sử một counter có hai replica:

~~~text
Initial state: [0,0]

A increments twice -> [2,0]
B increments three times -> [0,3]
~~~

Merge theo max của từng component:

\[
\operatorname{merge}([2,0],[0,3])=[2,3]
\]

Giá trị logical:

\[
\operatorname{value}([2,3])=2+3=5
\]

Đây là **state-based G-Counter** và cách merge trạng thái của CRDT này. Những số trong vector ở đây lưu phần đóng góp theo replica, không tự đồng nhất với version vector của object.

### 18.2. CRDT không tự bảo vệ stock không âm

Một PN-Counter gộp increments/decrements có thể hội tụ. Nhưng trong partition, hai region cùng nghĩ “stock còn 1” rồi mỗi nơi decrement 1 có thể tạo oversell. Hội tụ counter **không tự bảo đảm invariant toàn cục stock ≥ 0**.

Để giữ số lượng giới hạn có thể cần:

- Một authority/conditional transaction.
- **Escrow/bounded counter** với quyền trừ được phân bổ.
- Thay mô hình kinh doanh để cho phép backorder/compensation.

### 18.3. Set semantics và remove

Một set replicated cần định nghĩa “remove” có thắng “add” concurrent không. OR-Set, add-wins/remove-wins set có semantics khác nhau; không dùng một danh sách JSON rồi cộng union/timestamp là đã có CRDT chuẩn.

### 18.4. CRDT và vector clocks không phải từ đồng nghĩa

Vector clock là **causal metadata**; CRDT là **data type với merge/update semantics**. Có thể phối hợp, nhưng một vector clock không tự giúp merge invoice đúng, và một CRDT có thể dùng metadata khác tùy thuật toán.

## 19. Event delivery không giữ causal order mặc định

Giả sử nguồn Order phát:

~~~text
E1: Order O900 status=PAID    sourceVersion=17
E2: Order O900 status=SHIPPED sourceVersion=18
~~~

Do event bus có retry, consumer có thể thấy:

~~~text
Receive E2 first.
Receive E1 later.
~~~

Nếu consumer mù quáng áp event theo thứ tự **nhận được**, read model có thể đi lùi từ `SHIPPED` về `PAID`.

### 19.1. Guard bằng source version

Một read model có thể lưu:

~~~json
{
  "orderId": "O900",
  "status": "SHIPPED",
  "lastAppliedSourceVersion": 18
}
~~~

Với **một authority cấp version tăng đơn điệu trên mỗi Order**, logic:

~~~text
if incoming.sourceVersion > lastAppliedSourceVersion:
    apply incoming full state
    lastAppliedSourceVersion = incoming.sourceVersion
else:
    ignore as duplicate/older
~~~

phù hợp **nếu event mang snapshot đầy đủ hoặc update có semantics cho phép bỏ version trung gian**.

### 19.2. Chú ý với delta events

Nếu:

~~~text
E1: +5 points, version 17
E2: -2 points, version 18
~~~

áp E2 trước E1 rồi bỏ E1 vì version thấp **không giữ đúng tổng**. Delta events cần xử lý theo sequence liên tục, buffering, replay từ checkpoint hoặc một operation-based protocol có tính chất hội tụ phù hợp.

**Dùng `incoming.version > current.version` không phải thuật toán đúng cho mọi loại event.**

### 19.3. Source version cần scoped

Một source version per Order không được so với version per Shop hay global event offset:

~~~text
Order O900 version 18
Shop S12 version 30
~~~

Không có nghĩa event của Shop sau event Order về mặt nhân quả. Muốn đảm bảo ordering nhiều aggregates, cần event context/transaction log semantics khác.

### 19.4. Duplicate và retry

Một event có thể được delivered nhiều lần:

~~~text
E2 attempt1 -> applied
E2 attempt2 -> duplicate
~~~

Nếu consumer gọi external side effect, **trả kết quả cũ theo idempotency key** quan trọng hơn chỉ không cập nhật read model hai lần.

## 20. Transactional outbox và thứ tự nhân quả

Một ứng dụng thường ghi Order và phát event:

~~~text
Update order in DB
Publish "OrderPaid" to broker
~~~

Nếu crash ở giữa, DB đã commit nhưng event chưa được publish.

**Transactional outbox** ghi business change và outbox record trong cùng transaction/atomic scope được hỗ trợ:

~~~text
Transaction:
  Order O900 version=18
  Outbox event E18 carrying sourceVersion=18
Commit.

CDC/worker later publishes E18.
~~~

### 20.1. Outbox không tự bảo đảm exactly-once qua mọi hệ

Publisher có thể publish event rồi crash trước khi đánh dấu đã gửi, nên event có thể phát lại. Consumer vẫn phải **idempotent**.

### 20.2. Một outbox có thể chứa nhiều streams

Nếu outbox của nhiều shards/partitions cùng publish, global order giữa mọi event có thể không được bảo đảm. Để giữ order cho cùng aggregate, dùng **partition key/sequence/transactional source order** tương thích protocol.

### 20.3. Quan hệ causal có thể bắc qua services

~~~text
OrderPaid E18
    -> InventoryReserved E5
         -> ShipmentCreated E2
~~~

Nếu các service có causal context/request correlation, ta có thể biết chuỗi dependency. Tuy nhiên **version number của từng aggregate không so trực tiếp được**; `Order.version=18` và `Shipment.version=2` thuộc các scope khác nhau.

## 21. Delete, tombstone và nguy cơ resurrection

Xóa trong hệ đồng bộ bất đồng bộ có một tình huống nguy hiểm:

~~~text
Replica A: deleted user U42 at version 15.
Replica B: offline, still stores U42 at version 14.
Network heals.
~~~

Nếu A chỉ **xóa vật lý** và không còn metadata cho biết đã xóa, B có thể gửi bản cũ v14 như một record “mới” và hệ **hồi sinh** người dùng đã bị xóa.

### 21.1. Tombstone gắn version/causal context

Một tombstone logic:

~~~json
{
  "id": "U42",
  "deleted": true,
  "sourceVersion": 15,
  "deletedAt": "2026-11-14T10:00:00Z"
}
~~~

Nếu một source authority phát version tăng đơn điệu, tombstone v15 có thể thắng bản v14. Trong multi-writer với concurrent delete/update, phải có **chính sách remove-wins/add-wins hoặc conflict resolution theo domain**.

### 21.2. Bao lâu giữ tombstone?

Không nên xóa tombstone chỉ vì “đã quá 5 phút” nếu replica offline lâu hơn và còn có thể phát lại giá trị cũ. Cần xét:

- Thời gian tối đa replica có thể offline.
- Anti-entropy/repair guarantees.
- Retention của stream/log.
- Bootstrap/snapshot/reconciliation.
- Policy xóa vĩnh viễn và tuân thủ quyền riêng tư.

Khi tombstone bị compact/GC, giao thức phải có một cách khác để bảo đảm bản quá cũ không được chấp nhận.

### 21.3. Retry deletion

Xóa cùng logical request nhiều lần có thể idempotent về kết quả “record absent”, nhưng audit/event/counter/side effects vẫn có thể bị áp trùng nếu xử lý không đúng.

## 22. Kết quả timeout không chứng minh sự kiện không xảy ra

Ví dụ:

~~~text
T0: Client sends UPDATE version 17 -> 18.
T1: DB commits version 18.
T2: Response gets lost.
T3: Client observes TIMEOUT.
~~~

Client không thể tự kết luận mutation chưa xảy ra. Nếu retry cùng ý định nhưng lấy version mới rồi áp lại delta, có thể **double decrement/double charge**.

### 22.1. Logical operation ID

~~~json
{
  "logicalOperationId": "reserve-R42",
  "expectedVersion": 17,
  "operation": "RESERVE",
  "quantity": 1
}
~~~

Giữ cùng ID khi retry. Một idempotency ledger có thể trả lại outcome đã commit thay vì apply lần hai.

### 22.2. Expected version và operation ID giải quyết hai rủi ro khác nhau

| Mechanism | Chống được | Không tự chống được |
| --- | --- | --- |
| §expectedVersion§ CAS | Concurrent lost update đối với một record | Double external effect, retry không có ledger |
| Logical operation ID | Duplicate attempt cùng ý định | Hai ý định khác ID tranh resource |
| Vector clock | Nhận biết causal ancestry/concurrency | Business invariant về stock/uniqueness |
| Leader term/fencing | Stale owner, khi destination kiểm tra | Duplicate logical operation cùng owner |
| Event sequence | Replay/ordering trong stream scope | Global order giữa independent streams |

### 22.3. Error classification

**CONFLICT**: Conditional predicate không đạt; phải quyết định lại theo state mới.

**UNKNOWN**: Không có kết quả đáng tin; tra operation status/ledger hoặc đánh dấu PENDING.

**SUCCESS**: Operation đã commit theo ack contract cụ thể, nhưng độ bền và read visibility vẫn phụ thuộc cấu hình.

## 23. Causal consistency không đồng nghĩa linearizability

Khi có version hoặc logical clock, một câu hỏi lớn là **API đang cam kết mức nhất quán nào?**

### 23.1. Causal consistency

Trong một mô hình causal consistency, nếu một operation **phụ thuộc nhân quả** vào operation khác, hệ phải trình bày chúng theo thứ tự tương thích khi người dùng quan sát. Các operation **concurrent** có thể được quan sát theo những thứ tự khác nhau mà không nhất thiết vi phạm causal consistency.

Những bảo đảm thường được thảo luận trong ngữ cảnh này:

- **Read-your-writes:** Client đã hoàn tất write rồi tiếp tục đọc trong session được hứa thì phải thấy write ấy hoặc trạng thái mới hơn phù hợp.
- **Monotonic reads:** Client không đọc một phiên bản cũ hơn sau khi đã quan sát phiên bản mới trong session.
- **Monotonic writes:** Những write theo thứ tự từ cùng client phải được áp theo thứ tự cần thiết.
- **Writes-follow-reads:** Write sau một read phải được đặt sau những update mà read đã quan sát về mặt causal dependency.

Các bảo đảm chính xác phụ thuộc **session/context propagation và contract của sản phẩm**. Không tự suy một hệ “eventually consistent” đã cung cấp đầy đủ chúng.

### 23.2. Ví dụ writes-follow-reads

~~~text
Region A:
  W1: Order marked PAID.

Client reads W1 at A,
then moves to Region B and writes:
  W2: Create shipment for the paid order.
~~~

W2 phụ thuộc vào W1 vì client tạo shipment sau khi đã nhìn thấy Order PAID.

Nếu B nhận W2 nhưng chưa có W1, một hệ yêu cầu causal consistency phải xử lý dependency (chờ, mang causal context, hoặc đảm bảo ordering theo giao thức), không đơn giản áp W2 rồi phục vụ read như chưa có W1.

### 23.3. Linearizability là yêu cầu khác

**Linearizability** thêm yêu cầu tôn trọng **thứ tự thời gian thực của các operation không chồng lấn**, kể cả khi hai clients độc lập không truyền causal context qua nhau.

Ví dụ:

~~~text
Client A: write(x=1) returns SUCCESS.
                         |
                         v
Client B: read(x) begins after that success.
~~~

Với register linearizable và không có write khác, read B phải trả 1, dù B không nhận message causal context trực tiếp từ A.

Hệ causal có thể không bảo đảm ràng buộc real-time giữa hai session độc lập như thế.

### 23.4. Không suy causal consistency từ việc có vector clock

Vector metadata giúp nhận diện dependency, nhưng hệ cần một **read/write protocol** thực thi causal visibility, session migration, wait-for-dependency hoặc version routing. Chỉ lưu vector vào JSON rồi phục vụ replica bất kỳ không tự tạo consistency guarantee.

## 24. Thứ tự sự kiện: nhiều khái niệm dễ nhầm

| Khái niệm | Thứ tự được bảo đảm trong phạm vi nào? |
| --- | --- |
| Program order | Events theo thứ tự của một process |
| Happens-before | Causal edges giữa events |
| Lamport total order | Comparator deterministic, không tự thể hiện causal dependency đầy đủ |
| Per-key version | Mutations của cùng key dưới authority/version protocol |
| Partition log offset | Records trong cùng một log partition |
| Global transaction order | Nếu engine/protocol thực sự định nghĩa |
| Wall-clock timestamp order | Giá trị đồng hồ, có thể sai thứ tự thật do skew |
| Leader term | Thứ tự thế hệ quyền ghi, không phải thứ tự mọi event |
| Vector partial order | So sánh ancestry/concurrency theo causal context |

### 24.1. Offset log không cho global order miễn phí

~~~text
Kafka-like partition 0:
  offset 100 -> Order O900 PAID

Partition 1:
  offset 99 -> Customer C42 ADDRESS_CHANGED
~~~

Không được kết luận Order event sau Customer event vì 100 > 99. **Offsets có scope theo partition**, trừ khi một hệ cụ thể cung cấp một order chung.

### 24.2. Cùng timestamp không có nghĩa cùng event

Hai messages có thể có cùng Lamport scalar hoặc cùng HLC tuple trước khi tie-breaker; cần event ID riêng để deduplicate.

### 24.3. Event ID và version ID khác nhau

Một event ID có thể định danh lần publish/delivery; một source version đánh số trạng thái; một transaction ID liên kết nhiều mutations. Khi retry, event ID được sử dụng thế nào phải rõ để không biến cùng thay đổi thành hai ý định khác nhau.

## 25. HTTP ETag và If-Match như một kiểu optimistic concurrency

Một REST API có thể trả:

~~~http
HTTP/1.1 200 OK
ETag: "order-O900-v17"
Content-Type: application/json

{"orderId":"O900","status":"CREATED"}
~~~

Client gửi cập nhật điều kiện:

~~~http
PATCH /orders/O900 HTTP/1.1
If-Match: "order-O900-v17"
Content-Type: application/json

{"status":"PAID"}
~~~

Nếu resource đã đổi và ETag không còn match theo HTTP precondition semantics được dùng, server có thể trả:

~~~http
HTTP/1.1 412 Precondition Failed
~~~

### 25.1. ETag là opaque token

Client không nên parse `"order-O900-v17"` để suy độ mới hay độ lớn. ETag có thể là hash, revision hoặc opaque identifier do server tạo. Ứng dụng nên dùng **so khớp precondition đúng HTTP/API contract**.

### 25.2. Không giải quyết cross-service transaction

Một PATCH với §If-Match§ bảo vệ resource theo semantics API; nó không tự làm việc gọi email hay charge payment atomic với cập nhật resource.

### 25.3. Cẩn trọng với weak ETag

HTTP có strong và weak entity tags với mục đích so khớp khác nhau. Khi dùng §If-Match§ để chống lost update, cần theo đúng **strong comparison requirements** của HTTP và implementation, không tự coi mọi token có cú pháp ETag đều tương đương một OCC version mạnh.

## 26. Ba chiến lược xử lý conflict

Khi nhận hai concurrent writes, có ba hướng lớn:

### 26.1. Chặn xung đột tại nguồn

Một authority cùng CAS/transaction có thể không cho hai writer cùng commit một transition không tương thích.

Ví dụ:

~~~text
Order status CREATED
  -> PAID
  -> SHIPPED
~~~

Một request §CANCELLED§ cạnh tranh với §SHIPPED§ nên được xử lý theo state machine/invariant, không mặc nhiên merge.

Ưu điểm: dễ bảo vệ business invariant. Nhược điểm: cần coordination, latency hoặc giảm availability khi partition.

### 26.2. Giữ siblings rồi resolve

Hai bản đồng thời được lưu, API hoặc background merge quyết định:

~~~text
Conflict Set:
  version A: address=new
  version B: phone=new
~~~

Ưu điểm: không âm thầm bỏ write. Nhược điểm: ứng dụng phải có conflict semantics, xử lý nhiều branches và metadata.

### 26.3. Dùng data type mergeable

Counter tăng, set phù hợp hoặc CRDT hỗ trợ merge theo đại số.

Ưu điểm: hội tụ tự động với loại operation phù hợp. Nhược điểm: không giữ được mọi invariant như unique booking hay nonnegative inventory nếu không thêm escrow/authority.

### 26.4. Bảng quyết định nghiệp vụ

| Dữ liệu | Tính chất | Hướng suy nghĩ |
| --- | --- | --- |
| Số lượt like/view | Có thể cộng gộp | Aggregation/CRDT nếu semantics phù hợp |
| Giỏ hàng offline | Concurrent additions/removals | OR-Set/merge theo domain |
| User preferences | Có thể mất một chỉnh sửa? | LWW nếu policy cho phép; otherwise conflict UI |
| Địa chỉ đầy đủ | Các field phụ thuộc nhau | Atomic aggregate/explicit conflict |
| Order state machine | Transition có ràng buộc | Conditional update/authority |
| Ghế cuối cùng | Không được double booking | Conditional reserve/authoritative inventory |
| Thanh toán | Không được double charge | Ledger, provider idempotency, reconciliation |
| Search index | Read model có thể stale | Source version và replay |
| Access revocation | Không được cho phép bằng state cũ | Stronger authority/read policy |

## 27. Case study: đồng bộ Customer giữa A và B

Ta quay lại Customer C42 với hai thay đổi concurrent.

### 27.1. Lịch có version/context

| Bước | Region A | Region B |
| --- | --- | --- |
| 1 | Base v7/context `[0,0]` | Base v7/context `[0,0]` |
| 2 | Edit address, vector `[1,0]` | Edit phone, vector `[0,1]` |
| 3 | Local ACK | Local ACK |
| 4 | Nhận version B | Nhận version A |
| 5 | Vector compare: CONCURRENT | Vector compare: CONCURRENT |
| 6 | Resolve domain merge | Nhận resolved version/context |

Trong trường hợp field độc lập, hai replica có thể đồng ý:

~~~json
{
  "address": "new",
  "phone": "999",
  "resolvedFrom": [
    {"A": 1},
    {"B": 1}
  ],
  "context": {"A": 2, "B": 1}
}
~~~

Context trên minh họa merge `[1,1]` rồi tạo event mới tại A thành `[2,1]`. Trường §resolvedFrom§ chỉ là metadata giải thích, không phải schema của một DB cụ thể.

### 27.2. Khi nào không thể merge?

Nếu cả A và B sửa §shippingAddress§ thành **hai địa chỉ khác nhau**, domain có thể yêu cầu:

- Hiển thị conflict cho người dùng.
- Chọn source có quyền cao hơn (chẳng hạn cập nhật đã được xác thực theo quy trình).
- Dùng một authoritative write theo business key.
- Lưu lịch sử/intent và yêu cầu xác nhận.

Không chọn “timestamp lớn hơn” chỉ vì việc đó giúp database hội tụ về một giá trị.

### 27.3. Read ở region khác ngay sau local ACK

Nếu A báo ACK nhưng replication sang B chưa hoàn tất, một client sang B có thể đọc bản cũ. Vector context có thể giúp client **yêu cầu ít nhất causal version đã thấy**, nhưng sản phẩm phải hỗ trợ session/causal read semantics. Không suy mọi read trên B luôn thấy kết quả A.

### 27.4. Khi một region offline quá lâu

Một region offline nhiều ngày có thể gửi lại:

- Updates cũ.
- Deletes cũ.
- Duplicated events.
- Changes được tạo dựa trên những causal contexts đã lỗi thời.

Anti-entropy, tombstones, log retention và conflict policy phải chịu được tình huống này; không chỉ thiết kế cho partition 1–2 giây.

## 28. Test matrix cho đồng hồ logic và version

| Kịch bản | Mục tiêu | Điều cần quan sát |
| --- | --- | --- |
| Concurrent local writes | Phát hiện siblings | Vectors incomparable |
| Message send/receive | Causal clock progression | Receiver timestamp lớn hơn sender |
| Clock skew | Không dựa mù vào updatedAt | Thứ tự logic giữ đúng |
| Client retry after timeout | Không áp business effect hai lần | ID và dedup |
| Out-of-order snapshots | Không đi lùi source state | Version guard |
| Out-of-order deltas | Không bỏ mất phép cộng/trừ | Replay/buffering |
| Replica offline lâu | Không resurrect delete cũ | Tombstone/version retention |
| Actor restart | Không trùng actor counter | Generation/incarnation |
| Multi-region concurrent updates | Không coi same scalar version là equal state | Conflict detection |
| Clock far in future | HLC/LWW không sai âm thầm | Skew handling |
| Log partitions khác nhau | Không so offset trực tiếp | Scoped ordering |
| New replica joins | Causal context/repair đúng | Bootstrap/catch-up |

### 28.1. Dùng timeline có causal edges

Mỗi test nên ghi:

~~~json
{
  "logicalOperationId": "op-C42-address",
  "attemptId": "attempt-1",
  "entityId": "C42",
  "region": "A",
  "actorId": "A#generation-3",
  "priorVersion": 7,
  "newVersion": 8,
  "vector": {"A#generation-3": 1},
  "lamportTime": 12,
  "eventType": "UPDATE_ADDRESS",
  "result": "LOCAL_ACK"
}
~~~

Với read/write ở nhiều nodes, ghi thêm **invoke/response times, message send/receive IDs, source log positions và consistency mode**. Không dùng một timestamp duy nhất làm bằng chứng cho mọi thứ tự.

### 28.2. Không đồng nhất ACK với độ bền toàn hệ

Khi test, phải biết §LOCAL_ACK§ nghĩa gì: ghi vào RAM, ổ đĩa cục bộ, majority commit hay quorum cụ thể? Một local write có thể được ACK nhưng về sau bị rollback theo hợp đồng cấu hình. Metadata causal của nó không tự làm write đó durable.

### 28.3. Tách test định hướng correctness khỏi benchmark

Benchmark throughput với key hash đều không chứng minh conflict resolution chính xác khi replicas tách mạng. Test correctness cần lịch có concurrent writes, retry, network split, process restart và checkpoint; benchmark lại đo p95/p99, storage/index overhead và metadata size.

## 29. Quan sát trong môi trường production

| Metric / log dimension | Dùng để phát hiện |
| --- | --- |
| §version_conflict_total§ | CAS conflicts do concurrent writers |
| §vector_concurrent_versions_total§ | Số sibling pairs được phát hiện |
| §sibling_count_per_key§ | Keys có quá nhiều branches |
| §merge_duration_ms§ | Chi phí giải conflict |
| §replication_lag_ms§ | Replica cập nhật trễ |
| §out_of_order_event_total§ | Events đến không theo source sequence |
| §duplicate_event_total§ | At-least-once redelivery |
| §skipped_source_version_total§ | Phát hiện gaps trong delta stream |
| §tombstone_retention_age§ | Nguy cơ xóa tombstone quá sớm |
| §clock_skew_estimate_ms§ | Chênh lệch vật lý giữa các nodes |
| §future_timestamp_rejections§ | Clock quá xa tương lai bị giới hạn |
| §actor_generation_mismatch_total§ | Event dùng incarnation cũ |
| §unknown_write_outcome_total§ | Timeout chưa rõ commit |
| §reconciliation_backlog§ | Các intents/conflicts chưa xử lý |
| §business_invariant_violations§ | Oversell, double booking, duplicate charges |

### 29.1. Cẩn thận metric cardinality

Không đưa raw entity ID, user ID hoặc event ID vào nhãn metric time-series nếu có hàng triệu giá trị. Dùng aggregate theo shard, region, actor group, conflict reason; chi tiết request ID nên nằm trong **tracing/log có kiểm soát quyền truy cập**.

### 29.2. Không chỉ đo độ trễ đồng bộ

Hai replica hội tụ sau 3 giây chưa chắc đã giữ bất biến nghiệp vụ: cả hai có thể đã xác nhận bán cùng một sản phẩm cuối. Do đó cần đo **correctness/invariant** bên cạnh lag và recovery.

## 30. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Timestamp lớn hơn luôn là event đến sau.” | Clock skew, concurrency | So causal context/protocol |
| “Hai bản version 8 là cùng một bản.” | Có thể hai writers tự cấp v8 | Authority hoặc vector conflict |
| “Version của Order 20 mới hơn version User 15.” | Scope khác nhau | Chỉ so trong scope được định nghĩa |
| “Lamport timestamp thấp hơn chứng minh happens-before.” | Converse không đúng | A→B mới suy L(A)<L(B) |
| “Hai event cùng Lamport counter là cùng event.” | Independent processes có thể trùng | Event ID và actor tie-break |
| “Total ordering nghĩa causal dependency.” | Tie-breaker tự áp thứ tự | Phân biệt deterministic order và causal order |
| “Vector lớn theo tổng thì mới hơn.” | Vector phải so từng component | Partial order |
| “Vector equal nghĩa payload chắc chắn bằng.” | Metadata hỏng/sai protocol hoặc two payloads cùng dot | Cần event identity và integrity |
| “Concurrent nghĩa cùng microsecond.” | Concurrent là không có causal edge | Happens-before model |
| “Merge vector bằng max cũng merge data.” | Counter metadata khác business value | Domain-aware merge/CRDT |
| “HLC chứng minh mọi timestamp nhỏ hơn là causal ancestor.” | Chỉ một chiều đảm bảo | HLC không thay vector |
| “Có logical clock là linearizable.” | Thiếu commit/read protocol | Cần authority/quorum/transaction |
| “LWW luôn giữ write cuối theo thời gian thật.” | Clock skew, timestamp source | Hợp đồng winner cụ thể |
| “CRDT luôn ngăn oversell.” | Convergence khác invariant | Escrow/conditional authority |
| “Event sourceVersion cao hơn thì bỏ mọi event thấp hơn.” | Delta events có thể bị mất | Gap detection/buffering |
| “Delete xong bỏ metadata là đủ.” | Replica cũ có thể hồi sinh dữ liệu | Tombstone/causal deletion |
| “Có ETag là có global consensus.” | ETag chủ yếu là precondition token | Xem API scope |
| “Timeout nghĩa chưa commit.” | Response có thể mất | Idempotency/outcome lookup |
| “Log offset 100 của partition A sau offset 99 của B.” | Offsets scope theo partition | Chỉ so cùng log context |
| “Replicas hội tụ thì mọi lời hứa nghiệp vụ đều đúng.” | Có thể lost intent hoặc double-ack | Kiểm tra history/invariants |

## 31. Bài tập thực hành

### Bài 1 — Dựng quan hệ happens-before

Cho các events:

~~~text
Process A: A1 -> A2(send M) -> A3
Process B: B1 -> B2(receive M) -> B3
~~~

1. Liệt kê các causal edges chắc chắn.
2. Có thể khẳng định A3 trước B3 không?
3. Có thể khẳng định B1 trước A1 không?
4. Những cặp nào có thể concurrent?

### Bài 2 — Tính Lamport timestamps

Ban đầu A/B đều có Lamport counter=0:

~~~text
A: local event -> send M -> local event
B: local event -> receive M -> send N
A: receive N
~~~

Hãy tính từng timestamp, với quy tắc event/send +1 và receive max(local, received)+1. Giải thích vì sao message receive luôn có timestamp lớn hơn send.

### Bài 3 — Phản ví dụ của chiều ngược Lamport

Hai process độc lập:

~~~text
A event with Lamport 4
B event with Lamport 9
No message connection in the modeled history.
~~~

1. Có suy A→B không?
2. Có thể sắp chúng bằng `(Lamport,processId)` không?
3. Total order đó có chứng minh B đã nhìn thấy A không?

### Bài 4 — Vector comparison

Với vector theo `[A,B,C]`, phân loại:

~~~text
V1=[2,1,0], V2=[3,1,0]
V3=[1,4,0], V4=[2,3,0]
V5=[1,1,1], V6=[1,1,1]
V7=[2,2,0], V8=[1,3,0]
~~~

Cho mỗi cặp: BEFORE, AFTER, EQUAL hay CONCURRENT? Không dùng tổng counter.

### Bài 5 — Merge vector context

Trước partition hai replicas có `[4,2]`. Trong partition:

~~~text
A: creates [5,2]
B: creates [4,3]
~~~

1. Hai versions concurrent không?
2. Merge context bằng max cho kết quả nào?
3. Nếu A tạo version mới dựa trên cả hai, vector tiếp theo là gì?
4. Vì sao metadata merge không tự quyết định dữ liệu business?

### Bài 6 — Version number cạnh tranh

Order O900 ở version 17. Client A và B đều đọc 17:

~~~text
A: status=PAID, expectedVersion=17
B: status=CANCELLED, expectedVersion=17
~~~

1. Nếu CAS atomic tại authority, kết quả nào có thể xảy ra?
2. Client thua nên xử lý sao?
3. Nếu hai regions tự cấp version 18, vấn đề gì xảy ra?
4. Expected version có thay thế idempotency ledger cho retry không?

### Bài 7 — ABA

Một record đi qua:

~~~text
state=A, version=5
state=B, version=6
state=A, version=7
~~~

1. Client chỉ so `state=A` có thể nhầm gì?
2. Thêm `expectedVersion=5` giúp gì?
3. Nếu delete/recreate mà version reset, cần thêm generation nào?

### Bài 8 — Siblings và resolve

Base Customer có address/phone. A đổi address, B đổi phone trong partition.

- Phân loại quan hệ version vectors tương ứng.
- Nếu domain cho phép, tạo merged payload.
- Tạo causal context mới cho merged version.
- Khi nào không được merge từng field?

### Bài 9 — HLC

Node A có HLC `(200,4)` và physical `now=198`; Node B có HLC `(199,2)` và physical `now=199`.

1. A tạo local event thì HLC thành gì?
2. A gửi message với HLC mới.
3. B nhận message, tính HLC theo quy tắc receive.
4. Vì sao phần logical cần tăng ngay cả khi wall-clock của B không tăng?

### Bài 10 — LWW và clock skew

Node A chạy nhanh đồng hồ 120 giây; node B đồng hồ đúng. Trong một partition, B tạo update sau A theo thời gian thật nhưng không biết update A.

1. Timestamp wall-clock có thể khiến A thắng vì sao?
2. Hai events có chắc có happens-before không?
3. Vector clock có phát hiện gì nếu context được truyền đúng?
4. Nên dùng policy nào nếu cả hai update đều quan trọng?

### Bài 11 — Snapshot event và delta event

Consumer nhận theo thứ tự:

~~~text
E18: FULL_STATE status=SHIPPED, version=18
E17: FULL_STATE status=PAID, version=17
~~~

Rồi trong bài khác:

~~~text
E18: DELTA -2 points, version=18
E17: DELTA +5 points, version=17
~~~

1. Version guard có thể bỏ E17 trong bài FULL_STATE không, theo điều kiện nào?
2. Vì sao bỏ E17 trong bài DELTA có thể sai?
3. Buffer/replay/checkpoint cần xử lý thế nào?

### Bài 12 — Delete resurrection

Replica A có tombstone User v15, B offline còn User v14.

1. Nếu A xóa vật lý tombstone trước khi B quay lại, lỗi nào có thể xảy ra?
2. Những điều kiện nào quyết định tombstone retention?
3. Nếu B tạo một concurrent update với delete, ứng dụng cần policy gì?

### Bài 13 — Causal read và linearizable read

Client A write `x=1` và nhận ACK. Client B khác session bắt đầu read sau ACK.

- Trong hợp đồng linearizable, read B phải thấy gì nếu không có writer khác?
- Causal consistency có tự cung cấp cùng bảo đảm real-time giữa hai session không?
- Session context/read-your-writes giúp client A theo dõi cập nhật thế nào?

### Bài 14 — Outbox

Order chuyển sang PAID và cần gửi event:

~~~text
DB update succeeded
Publisher crashed before acknowledging event publish
~~~

1. Outbox giúp tránh mất event thế nào?
2. Vì sao consumer có thể nhận duplicate?
3. Source version/operation ID được dùng thế nào?
4. Nếu broker có nhiều partitions, có global order giữa chúng không?

### Bài 15 — Version của các resource khác nhau

API nhận:

~~~json
{
  "orderVersion": 25,
  "customerVersion": 40,
  "shipmentVersion": 3
}
~~~

1. Có thể sắp các mutations toàn hệ theo ba số này không?
2. Muốn giữ dependency OrderPaid→ShipmentCreated cần loại metadata nào?
3. Khi nào một distributed transaction log có thể cung cấp ordering khác?

### Bài 16 — Chọn conflict resolution cho nghiệp vụ

Chọn chính sách cho từng loại dữ liệu:

~~~text
User avatar preference
Collaborative shopping cart
Inventory stock left=1
Unique event seat
Daily view counter
Payment capture
Order status state machine
Search read model
~~~

Với từng mục, nêu: bất biến, có chấp nhận LWW không, cần vector/siblings hay CRDT không, cần authority/CAS không, retry và consistency contract.

### Bài 17 — Phân tích operation history

Cho:

~~~text
W1: invoke=0, response=10, write x=1
W2: invoke=5, response=8,  write x=2
R:  invoke=11,response=13, read x=1
~~~

1. W1 và W2 có overlap không?
2. Có thể có một linearization order nào cho read x=1 không?
3. Nếu thay W2 bắt đầu=12, kết luận khác gì?
4. Vì sao sort theo thời điểm response không đủ?

### Bài 18 — Thiết kế multi-region profile

Hệ có 3 regions, mỗi nơi phục vụ offline mobile edits:

~~~text
Profile contains:
  displayName
  shippingAddress
  phone
  marketingPreferences
~~~

Thiết kế một chiến lược:

1. Chọn unit/aggregate nào có thể merge độc lập.
2. Dùng causal context/version vectors ra sao?
3. Khi hai updates cùng sửa shippingAddress, UI xử lý thế nào?
4. Actor IDs và metadata growth được kiểm soát ra sao?
5. Khi replica offline 30 ngày, tombstone/repair cần gì?
6. Những thao tác nào cần single authority?

## 32. Gợi ý giải một số bài tính

Đây là các phép tính minh họa để người học tự đối chiếu phương pháp, không thay thế việc giải hết mọi bài.

### 32.1. Bài 4: so từng component

~~~text
V1=[2,1,0] vs V2=[3,1,0]  -> BEFORE
V3=[1,4,0] vs V4=[2,3,0]  -> CONCURRENT
V5=[1,1,1] vs V6=[1,1,1]  -> EQUAL
V7=[2,2,0] vs V8=[1,3,0]  -> CONCURRENT
~~~

### 32.2. Bài 5: merge causal context

~~~text
[5,2] concurrent [4,3].
join([5,2],[4,3]) = [5,3].
A tạo event mới sau khi đã biết cả hai -> [6,3].
~~~

Điều quan trọng là **write mới phải dựa trên merged context**, không tạo version chỉ từ một sibling đã nhận.

### 32.3. Bài 9: HLC

~~~text
A old HLC=(200,4), now=198.
A local event -> (200,5).

B old HLC=(199,2), now=199.
Message HLC=(200,5).
nextP=max(199,199,200)=200.
nextP equals message p only.
B receive -> (200,6).
~~~

HLC của receive event lớn hơn send event dù physical clock của B là 199.

### 32.4. Bài 17: overlapping writes

W1 và W2 overlap nên có thể tuyến tính hóa W2 trước W1; read bắt đầu sau cả hai và trả 1 là khả thi theo register model. Nếu W2 chỉ bắt đầu ở t=12 và W1 đã hoàn tất ở t=10, read R bắt đầu ở t=11 và overlap W2; việc R thấy 1 vẫn có thể hợp lệ vì R có thể tuyến tính hóa trước W2. Muốn chứng minh vi phạm phải có một real-time precedence rõ ràng bắt buộc một giá trị khác.

## 33. Checklist cho thiết kế version và đồng bộ

1. **Version thuộc scope nào?** Một entity, một shard, một stream hay toàn hệ?
2. **Ai cấp version?** Authority duy nhất, leader, nhiều writers hay clients tự tăng?
3. **Version có tăng đơn điệu không?** Sau failover, restart, recreate, reshard?
4. **Điều kiện CAS có được kiểm tra nguyên tử tại nguồn dữ liệu không?**
5. **Có cần phân biệt concurrent writes không?** Nếu có, scalar version đủ không?
6. **Vector metadata có truyền causal context qua clients/services không?**
7. **Actor identity có incarnation/epoch?** Có bao nhiêu actor components?
8. **Có chiến lược metadata pruning an toàn không?**
9. **LWW có thể làm mất một intent đã được ACK không?** Domain có chấp nhận không?
10. **Merge policy có giữ invariant của aggregate không?**
11. **CRDT có đúng loại data/operation không?** Bounded constraints được bảo vệ thế nào?
12. **Event là full state hay delta?** Có thể bỏ bản version thấp hơn không?
13. **Event sequence có scope rõ không?** Theo entity, partition hay toàn cluster?
14. **Consumer có xử lý duplicate, gaps và reordering không?**
15. **Delete có tombstone/version/context?** Repair retention có đủ lâu không?
16. **Clock skew/HLC physical component có policy giới hạn không?**
17. **Read consistency có thực thi causal context hoặc read-your-writes không?**
18. **Timeout có được coi UNKNOWN cho đến khi đối soát không?**
19. **Idempotency record có commit an toàn với business effect không?**
20. **Có kiểm thử network partition, restart, concurrent mutations và read lag không?**
21. **Có đo conflict frequency, sibling growth và business invariant violation không?**
22. **Đã đọc contract chính thức của DB/SDK cho version/CAS/replication chưa?**

## Kết luận

Trong hệ NoSQL đa replica, “mới hơn” là khái niệm cần được định nghĩa cẩn thận. **Version number**, **logical clock** và **quan hệ happens-before** giải quyết những câu hỏi khác nhau:

- **Per-record version** hữu ích để nhận biết một entity đã thay đổi, triển khai CAS và chống lost update **khi có authority/atomicity trong phạm vi phù hợp**.
- **Lamport clock** bảo toàn hướng causal order: nếu a→b thì L(a)<L(b), nhưng L(a)<L(b) **không chứng minh** a→b.
- **Vector clock** dùng quan hệ so sánh theo từng component để phân biệt **ancestor/descendant và concurrent versions**, với điều kiện context được truyền đúng protocol.
- **HLC** kết hợp physical và logical components để tạo timestamp gần wall-clock và tương thích causal ordering, **không thay vector conflict detection hoặc consensus**.
- **LWW** có thể khiến replicas hội tụ nhưng **làm mất một cập nhật concurrent đã được xác nhận**; chỉ chọn khi domain chấp nhận.
- **CRDT** hỗ trợ hội tụ cho những data types phù hợp, nhưng không tự bảo vệ stock không âm, unique reservation hoặc workflow thanh toán.
- **Event version và log offset có scope**. Không được so hai counters thuộc hai resource/partition khác nhau; out-of-order delta events cần replay/buffering thay vì bỏ qua tùy tiện.
- **Tombstone và causal deletion** giúp ngăn dữ liệu cũ hồi sinh khi replica offline quay lại.
- **Consistency của API là hợp đồng khác metadata timestamp**. Có causal context không đồng nghĩa mọi read linearizable.
- **Timeout sau write có thể là unknown outcome**. Kết hợp version/CAS với idempotency, dedup ledger và reconciliation khi nghiệp vụ có side effects.

Khi thiết kế đồng bộ dữ liệu, hãy luôn hỏi: **“Phiên bản này do ai cấp, có thứ tự trong phạm vi nào, hai thay đổi có thực sự biết về nhau không, và nếu chúng độc lập thì bất biến nghiệp vụ yêu cầu giữ cả hai, gộp chúng hay chỉ cho một kết quả được commit?”**
