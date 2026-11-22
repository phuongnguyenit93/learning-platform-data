# Vector clock/version vector và phát hiện cập nhật đồng thời

Một khách hàng đổi địa chỉ nhận hàng trên điện thoại khi mất mạng. Cùng lúc, nhân viên hỗ trợ sửa địa chỉ trên phiên làm việc khác. Khi hai thiết bị đồng bộ trở lại, cơ sở dữ liệu NoSQL nên làm gì? Nếu chỉ so thời gian ghi và giữ bản có timestamp mới hơn, hệ có thể xóa âm thầm thay đổi hợp lệ của một người. Nếu cứ ghi đè theo thứ tự message tới server, mạng chậm có thể khiến dữ liệu mới bị thay bằng dữ liệu cũ.

**Vector clock** và **version vector** giúp trả lời một câu hỏi quan trọng hơn: *hai phiên bản có quan hệ nhân quả, tức phiên bản này được xây dựng trên phiên bản kia, hay chúng được tạo độc lập nên có thể xung đột?* Công cụ này được dùng trong lý thuyết hệ phân tán và một số thiết kế lưu trữ nhiều bản sao/đa vùng để **phát hiện cập nhật đồng thời**. Sau khi phát hiện, hệ vẫn phải chọn chính sách xử lý: giữ nhiều phiên bản, yêu cầu người dùng hợp nhất, merge theo quy tắc nghiệp vụ hay dùng một kiểu dữ liệu có thể hội tụ tự động.

Bài học thuộc chương **Xung đột và đồng bộ** của module **Database No SQL**, gồm mô hình quan hệ nhân quả, cấu trúc vector, phép so sánh, ví dụ nhiều replica, thuật toán Java, cách tích hợp vào read/write/anti-entropy, giới hạn metadata và các tình huống thực hành.

**Lưu ý phạm vi:** *Cập nhật đồng thời* theo vector không nhất thiết có nghĩa hai thao tác diễn ra tại đúng một thời điểm trên đồng hồ. Nó nghĩa là **không có quan hệ nhân quả nào được chứng minh giữa chúng trong mô hình sự kiện đang theo dõi**. Vector clock/version vector là metadata phát hiện thứ tự, **không tự tạo transaction, không tự giải quyết xung đột và không bảo đảm mọi bất biến nghiệp vụ**.

## 1. Bài toán: hai phiên bản cùng hợp lệ ở hai nơi

Giả sử một hồ sơ có trạng thái ban đầu:

~~~json
{
  "customerId": "u42",
  "shippingAddress": "12 Đường A",
  "phone": "0900000000"
}
~~~

Replica **A** và **B** đều có phiên bản gốc. Trong lúc mất liên lạc:

- Tại A, người dùng thay `shippingAddress` thành `"18 Đường B"`.
- Tại B, nhân viên hỗ trợ thay `phone` thành `"0911111111"`.
- Mỗi phía chấp nhận ghi tại chỗ; không bên nào biết thay đổi của bên kia.

Khi kết nối hồi phục:

~~~text
Phiên bản gốc V0:
  address = "12 Đường A"
  phone   = "0900000000"

Replica A, phiên bản VA:
  address = "18 Đường B"
  phone   = "0900000000"

Replica B, phiên bản VB:
  address = "12 Đường A"
  phone   = "0911111111"
~~~

Giữ nguyên VA bằng *last-write-wins* (LWW) sẽ mất phone mới. Giữ nguyên VB sẽ mất address mới. Tệ hơn, nếu hai bên cùng sửa **một field** thì kết hợp tự động có thể không hợp lệ. Trước khi quyết định cách merge, hệ phải nhận biết **VA và VB là hai nhánh xuất phát từ V0**, không phải phiên bản này được tạo sau khi đã đọc phiên bản kia.

Đó là nhiệm vụ chính của metadata nhân quả.

## 2. Vì sao timestamp vật lý chưa đủ?

Một cách đơn giản là gắn thời gian:

~~~text
A: address updated at 10:00:05.100
B: phone   updated at 10:00:05.090
~~~

Nếu lấy timestamp lớn hơn, VA sẽ “thắng”. Nhưng timestamp vật lý không chứng minh thứ tự nhân quả:

- Đồng hồ giữa hai máy có thể lệch, dù đều dùng NTP.
- Một request đến muộn có thể là thay đổi cũ.
- Hai cập nhật có thể diễn ra đồng thời về logic dù timestamp khác nhau.
- LWW chọn một bản theo quy tắc, **không phát hiện và giữ lại cả hai thay đổi**.
- Timestamp tăng không bảo đảm writer đã nhìn thấy dữ liệu của writer khác.

Trong các hệ mà nghiệp vụ cho phép LWW (ví dụ trạng thái hiển thị tạm thời), đó vẫn có thể là **chính sách giải quyết xung đột** hợp lệ. Nhưng khi người dùng cần được cảnh báo về sửa đổi song song, hoặc cần hợp nhất các trường độc lập, LWW có thể gây **lost update**.

Vector clock tập trung vào **thứ tự nhân quả** chứ không dựa vào thời gian tường.

## 3. Quan hệ nhân quả: happens-before

Trong hệ phân tán, dùng ký hiệu `a → b` để nói sự kiện `a` **happens-before** sự kiện `b` nếu ta có bằng chứng quan hệ nhân quả từ quy tắc:

1. Hai sự kiện trên cùng một tiến trình/actor được sắp thứ tự, sự kiện trước happens-before sự kiện sau.
2. Một sự kiện gửi message happens-before sự kiện nhận message tương ứng.
3. Quan hệ có tính bắc cầu: nếu `a → b` và `b → c` thì `a → c`.

Nếu không chứng minh được `a → b` cũng không chứng minh được `b → a`, ta viết `a ∥ b`, tức **concurrent**.

### 3.1. Ví dụ một nhánh và hai nhánh

~~~mermaid
flowchart LR
    V0["V0: dữ liệu gốc"] --> A1["A1: sửa address"]
    V0 --> B1["B1: sửa phone"]
    A1 --> M["M: hợp nhất"]
    B1 --> M
    M --> C["C: cập nhật tiếp sau merge"]
~~~

- `V0 → A1` và `V0 → B1`.
- `A1 ∥ B1` nếu hai phía không trao đổi quan sát trước khi sửa.
- `A1 → M` và `B1 → M` nếu merge thực sự đã biết cả hai.
- `M → C`, nên C có lịch sử chứa cả hai nhánh.

Một bản ghi có thể đã được tạo sớm hơn theo wall-clock nhưng không phải ancestor của bản ghi khác. Vector là cách lưu dấu quan hệ này.

## 4. Vector clock là gì?

Một vector clock gắn **bộ đếm logic** với mỗi actor/process/replica tham gia:

\[
V = [v_A,v_B,v_C,\dots]
\]

Ví dụ:

~~~text
V0 = [A:1, B:0]
VA = [A:2, B:0]
VB = [A:1, B:1]
~~~

Ý nghĩa: vector mô tả **lịch sử nhân quả mà phiên bản/sự kiện đã quan sát**, trong đó bộ đếm của mỗi actor tăng khi actor tạo một sự kiện thuộc mô hình.

Trong dạng chuẩn:

1. Mỗi actor giữ vector của mình, khởi tạo các thành phần 0.
2. Khi actor thực hiện sự kiện nội bộ cần ghi nhận, tăng thành phần của chính nó.
3. Khi nhận message kèm vector, lấy **max theo từng thành phần** với vector hiện tại.
4. Nếu việc nhận message hoặc cập nhật tiếp theo được xem là một sự kiện, tăng thành phần actor theo định nghĩa protocol.

Vector clock không đòi các máy có chung đồng hồ thời gian thực. Nó đòi **định danh actor ổn định và quy tắc cấp số logic đúng**, cùng metadata phải được truyền qua các messages/versions liên quan.

### 4.1. Vector theo map thưa

Thay vì mảng có vị trí cố định, nhiều thiết kế lưu:

~~~json
{
  "A": 2,
  "B": 0,
  "C": 5
}
~~~

Hoặc bỏ các thành phần 0:

~~~json
{
  "A": 2,
  "C": 5
}
~~~

Hai biểu diễn trên tương đương nếu **key vắng mặt được hiểu là counter bằng 0**, và protocol đảm bảo actor ID không bị dùng lại tùy tiện. Đó là lý do map từ actor ID đến counter thường phù hợp khi membership động, mặc dù nó làm chi phí metadata thay đổi theo số actor.

## 5. Các phép so sánh vector

Cho hai vector `X` và `Y`, so theo **từng actor**, với các thành phần vắng mặt được xem là 0.

Định nghĩa:

\[
X \preceq Y \quad\Longleftrightarrow\quad
\forall i:\ X_i \leq Y_i.
\]

Và:

\[
X \prec Y
\quad\Longleftrightarrow\quad
X \preceq Y\ \land\ X\neq Y.
\]

Có bốn kết quả:

| Quan hệ | Điều kiện | Diễn giải theo protocol nhân quả chuẩn |
|---|---|---|
| **EQUAL** | `X_i = Y_i` với mọi actor | Cùng causal summary; chưa chắc payload giống nhau nếu protocol lỗi |
| **BEFORE** | `X ≺ Y` | X là ancestor/đã được Y bao hàm |
| **AFTER** | `Y ≺ X` | X bao hàm Y |
| **CONCURRENT** | Có thành phần X lớn hơn Y và thành phần khác nhỏ hơn Y | Hai nhánh không có quan hệ trước–sau được chứng minh |

Điểm quan trọng nhất: **so sánh vector là một quan hệ thứ tự bộ phận (partial order)**. Không phải mọi cặp đều so được theo trước–sau.

### 5.1. Ví dụ so sánh

| X | Y | Kết quả X so với Y | Giải thích |
|---|---|---|---|
| `[1,0]` | `[2,0]` | BEFORE | Y đã đi tiếp trên nhánh A |
| `[1,1]` | `[2,1]` | BEFORE | Mọi thành phần X không lớn hơn Y |
| `[2,0]` | `[1,1]` | CONCURRENT | X lớn hơn ở A, nhỏ hơn ở B |
| `[2,3]` | `[2,3]` | EQUAL | Cùng bộ đếm |
| `[4,1]` | `[3,2]` | CONCURRENT | Hai hướng tăng khác nhau |
| `[0,0]` | `[0,2]` | BEFORE | Vector zero đứng trước |
| `[3,2,1]` | `[3,2,1]` | EQUAL | So đủ mọi actor |

Một lỗi rất phổ biến là cộng các thành phần rồi chọn tổng lớn hơn. Ví dụ `[3,0]` và `[1,2]` có tổng lần lượt 3 và 3; chúng vẫn **CONCURRENT**. Dù tổng khác nhau, phép cộng cũng không chứng minh ancestor.

## 6. Cập nhật đồng thời không nghĩa timestamp bằng nhau

Giả sử:

~~~text
A update ở 09:00:00; không gửi thông tin cho B.
B update ở 09:05:00; B vẫn chỉ biết bản gốc.
~~~

Dù B ghi sau A **5 phút**, B có thể tạo bản concurrent với A vì B chưa quan sát nhánh A. Ngược lại:

~~~text
A update ở 09:00:00.
A gửi version cho B và B đọc/nhận nó.
B update ở 09:00:02 dựa trên A.
~~~

Khi đó update của B có quan hệ nhân quả sau A; vector B phải bao hàm vector A. Cùng một khoảng thời gian ngắn không biến hai thao tác thành concurrent nếu có đường truyền nhân quả.

**Vector clocks trả lời “có biết/đã thấy những sự kiện nào?”**, không trả lời “ai bắt đầu trước trên đồng hồ?” hay “cập nhật nào có giá trị kinh doanh cao hơn?”.

## 7. Ví dụ đầy đủ hai replica bị phân vùng mạng

Bắt đầu khi A và B đều có bản gốc `V0={A:1,B:0}`:

~~~text
T0: A và B đã đồng bộ bản gốc:
    value = {"address":"12 A","phone":"0900"}
    vector = {A:1, B:0}

T1: A mất liên lạc với B.
T2: A sửa address:
    VA = {A:2, B:0}

T3: B sửa phone dựa trên V0:
    VB = {A:1, B:1}

T4: Kết nối phục hồi.
    A và B trao đổi VA/VB.
~~~

So sánh:

~~~text
A component: VA[A]=2 > VB[A]=1
B component: VA[B]=0 < VB[B]=1

=> VA ∥ VB: concurrent
~~~

Hệ có thể giữ cả hai **siblings** và yêu cầu merge. Nếu business merge được hai field độc lập, tạo nội dung:

~~~json
{
  "address": "18 B",
  "phone": "0911"
}
~~~

Causal context sau khi đã hiểu cả hai nhánh được tạo bằng max theo thành phần:

\[
\operatorname{join}(V_A,V_B)
=
[\max(2,1),\max(0,1)]
=
[A:2,B:1].
\]

Nếu A thực hiện sự kiện ghi **merged value mới** theo protocol một actor phát phiên bản, A tăng counter:

\[
V_{\mathrm{merged}}=[A:3,B:1].
\]

Vector mới **dominate cả VA và VB**. Khi B nhận được bản merged, nó có thể biết hai nhánh cũ đã được bao hàm và không còn phải giữ siblings cũ nếu không còn yêu cầu audit.

### 7.1. Cảnh báo: merge metadata chưa phải merge nội dung

Chỉ lấy `max(VA,VB)` rồi tùy tiện chọn payload VA không có nghĩa đã giải quyết xung đột. Nếu version mới tuyên bố bao hàm VB mà bỏ mất thay đổi phone của VB, bạn đã **làm biến mất dữ liệu một cách có chủ ý hoặc do lỗi**.

Trước khi tạo phiên bản thống trị cả hai, phải có **quy tắc giá trị**: chấp nhận một bản và ghi nhận việc loại bản kia, hợp nhất field, trình bày conflict cho người dùng, hoặc áp một CRDT đúng semantics.

## 8. Ba replica: vector phát triển qua truyền message

Ví dụ vector theo thứ tự `[A,B,C]`:

~~~text
A tạo sự kiện a1: [1,0,0]
A truyền a1 cho B.
B nhận a1:      [1,0,0]
B tạo b1:       [1,1,0]
C chưa thấy gì, tạo c1:
                  [0,0,1]
B truyền b1 cho A.
A nhận b1:      [1,1,0]
A tạo a2:       [2,1,0]
C vẫn đang cô lập.
~~~

Quan hệ:

- `a1 → b1 → a2`.
- `c1 ∥ a1`, `c1 ∥ b1` và `c1 ∥ a2` khi C chưa trao đổi.
- Nếu C nhận a2 rồi tạo c2, context C trở thành `[2,1,1]` sau merge, rồi tăng C lên `[2,1,2]`; c2 có quan hệ nhân quả sau a2 và c1.

Một bản biểu diễn graph:

~~~mermaid
flowchart LR
    A1["A: a1 [1,0,0]"] --> B1["B: b1 [1,1,0]"]
    B1 --> A2["A: a2 [2,1,0]"]
    C1["C: c1 [0,0,1]"] --> C2["C: c2 [2,1,2]"]
    A2 --> C2
~~~

Trong sơ đồ, mũi tên là quan hệ nhân quả. Không có mũi tên giữa c1 và a2 trước khi C nhận a2.

## 9. Vector clocks có thể phát hiện update concurrent ở đâu?

Các tình huống thường gặp:

- Hai replica cho phép ghi khi network partition, rồi đồng bộ trở lại.
- Ứng dụng offline-first lưu thay đổi trên nhiều thiết bị và cần phát hiện fork.
- Nhiều writers cùng cập nhật một document/key mà không có coordinator tuyến tính hóa tất cả ghi.
- Anti-entropy truyền các bản ghi từ peers và cần nhận diện phiên bản cũ, mới hoặc song song.
- Một read phải trả nhiều siblings cho client hợp nhất.
- Đồng bộ tài liệu nhiều nguồn, nơi có nhu cầu trình bày **conflict** thay vì tự ghi đè.

Vector clock không phù hợp với mọi trường hợp:

- Nếu hệ **chỉ có một writer tuần tự duy nhất**, một version number có thể đủ cho thứ tự của cùng record.
- Nếu nghiệp vụ chỉ có append-only immutable events với IDs duy nhất, có thể không cần vector per event cho bài toán “cùng document bị sửa”.
- Nếu yêu cầu transaction serializable/linearizable để trừ quota, chỉ phát hiện concurrent sau khi ghi **không cứu được invariant** đã bị vi phạm.
- Nếu dữ liệu có CRDT hỗ trợ merge đúng semantics, causal metadata có thể là một phần protocol nhưng không nhất thiết dùng vector clock truyền thống ở application.

## 10. Vector clock vs Lamport clock

**Lamport scalar clock** thường chỉ lưu một số và tăng dựa trên sự kiện/nhận message. Nó bảo vệ chiều:

\[
a\to b\ \Longrightarrow\ L(a)<L(b).
\]

Chiều ngược **không đúng nói chung**: nếu `L(a)<L(b)`, chưa chắc a happens-before b. Hai concurrent events có thể có hai số Lamport khác nhau.

Một vector clock chuẩn theo protocol đủ điều kiện cho phép:

\[
a\to b\ \Longleftrightarrow\ V(a)\prec V(b).
\]

Tính tương đương này cần giả định vector được cập nhật/truyền đầy đủ theo mô hình actor/events. Nó không đúng nếu metadata bị mất, actor ID bị tái sử dụng hoặc client không mang đủ causal context.

| Thuộc tính | Lamport scalar | Vector clock |
|---|---|---|
| Metadata | Một counter và có thể actor ID tie-breaker | Counter cho nhiều actors |
| Nhận biết a có trước b | Chỉ đủ một chiều theo luật | Có thể so quan hệ nhân quả |
| Phát hiện concurrency | Không chính xác chỉ từ scalar | Có thể phát hiện khi vectors không so được |
| Kích thước | Nhỏ | Tăng theo số actors được theo dõi |
| Dùng để | Thứ tự logic/tie-break | Causal tracking/concurrent versions |

Không dùng một số Lamport lớn hơn để khẳng định writer đã đọc mọi cập nhật có số nhỏ hơn.

## 11. Version vector khác vector clock ở trọng tâm sử dụng

Hai thuật ngữ có quan hệ gần, trong tài liệu sản phẩm đôi khi được dùng lẫn nhau; cần hỏi protocol cụ thể:

- **Vector clock** thường mô tả logical clocks của **events/processes** để suy luận happens-before.
- **Version vector** thường mô tả lịch sử/version của **một đối tượng hoặc một tập dữ liệu được sao chép**, giúp so phiên bản (ancestor, descendant, concurrent) khi đồng bộ.
- **Dotted version vector**, **version vector with exceptions** và các biến thể khác làm rõ một cập nhật riêng lẻ hoặc giảm metadata/đại diện causal context trong những protocol nhất định.

Ví dụ một version vector gắn với record:

~~~json
{
  "key": "profile:u42",
  "value": {"phone": "0911111111"},
  "version": {"A": 1, "B": 1}
}
~~~

Không phải mọi system dùng version vector đều lưu chính xác JSON này. Một record có thể lưu **context** và mỗi sibling có **dot** riêng; hoặc metadata được lưu nội bộ, không lộ ra API.

### 11.1. Không suy từ tên gọi ra bảo đảm

Khi một database nói “version vector” hoặc “vector clock”, cần xem:

- Actor IDs tương ứng node, replica, client hay vnode?
- Version được cấp lúc nhận write hay lúc commit?
- Context được truyền trong read-response và write-request thế nào?
- Hai concurrent writes tạo siblings hay có LWW policy?
- Khi merge siblings có tạo causal descendant đúng không?
- Đồng hồ/vector có thể bị compact/prune theo cách nào?
- Conflict resolution xảy ra trong engine, ứng dụng hay người dùng?

Tên cấu trúc là một gợi ý, **không thay thế hợp đồng consistency**.

## 12. Vector là partial order, không phải tổng thứ tự

Xét hai phiên bản:

~~~text
X = {A:4, B:1}
Y = {A:3, B:2}
~~~

Có `X[A]>Y[A]` và `X[B]<Y[B]`. Nếu API cần hiển thị **một** bản “mới nhất”, vector không tự chọn được X hay Y. Hệ phải:

1. Trả cả X và Y.
2. Áp domain merge.
3. Áp deterministic policy (ví dụ LWW) và chấp nhận mất nhánh bị bỏ.
4. Yêu cầu người dùng chọn.
5. Dùng transaction/coordination để không tạo hai nhánh ngay từ đầu, nếu invariant yêu cầu.

**Phát hiện xung đột và giải quyết xung đột là hai vấn đề khác nhau.** Đó là trọng tâm cần giữ trong toàn bộ bài.

## 13. Thuật toán so sánh hai vector

Để so X với Y, duyệt **hợp các actor IDs**, coi thành phần vắng mặt bằng 0:

~~~text
function compare(X, Y):
    xGreater = false
    yGreater = false

    for actor in union(keys(X), keys(Y)):
        x = X.getOrDefault(actor, 0)
        y = Y.getOrDefault(actor, 0)

        if x > y: xGreater = true
        if x < y: yGreater = true

        if xGreater and yGreater:
            return CONCURRENT

    if not xGreater and not yGreater:
        return EQUAL
    if xGreater:
        return AFTER
    return BEFORE
~~~

Nếu mỗi vector có ít nhất một thành phần lớn hơn phía kia, đó là **CONCURRENT**, bất kể tổng counter hoặc wall-clock timestamp. Nếu dùng map thưa với tối đa `m` actor IDs, so sánh cần thời gian O(m); triển khai với một tập hợp keys tạm còn dùng O(m) bộ nhớ. Không cần sắp xếp các vectors theo một tổng thứ tự để quyết định causality.

## 14. Java 17: triển khai VersionVector bất biến

Dưới đây là ví dụ Java 17 minh họa các phép toán căn bản, **chưa phải protocol replication hoàn chỉnh**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public record VersionVector(Map<String, Long> counters) {
    public enum Relation {
        BEFORE, AFTER, EQUAL, CONCURRENT
    }

    public VersionVector {
        if (counters == null) {
            throw new IllegalArgumentException("counters");
        }
        for (var entry : counters.entrySet()) {
            if (entry.getKey() == null
                    || entry.getKey().isBlank()
                    || entry.getValue() == null
                    || entry.getValue() < 0) {
                throw new IllegalArgumentException(
                    "Invalid vector entry"
                );
            }
        }
        counters = Map.copyOf(counters);
    }

    public static VersionVector empty() {
        return new VersionVector(Map.of());
    }

    private long count(String actor) {
        return counters.getOrDefault(actor, 0L);
    }

    public VersionVector increment(String actor) {
        if (actor == null || actor.isBlank()) {
            throw new IllegalArgumentException("actor");
        }
        Map<String, Long> next = new HashMap<>(counters);
        next.put(actor, Math.addExact(count(actor), 1L));
        return new VersionVector(next);
    }

    public VersionVector join(VersionVector other) {
        Map<String, Long> result = new HashMap<>(counters);
        for (var entry : other.counters.entrySet()) {
            result.merge(entry.getKey(), entry.getValue(), Math::max);
        }
        return new VersionVector(result);
    }

    public Relation compareTo(VersionVector other) {
        Set<String> actors = new HashSet<>(counters.keySet());
        actors.addAll(other.counters.keySet());

        boolean greater = false;
        boolean less = false;

        for (String actor : actors) {
            long a = count(actor);
            long b = other.count(actor);

            if (a > b) greater = true;
            if (a < b) less = true;
            if (greater && less) return Relation.CONCURRENT;
        }

        if (!greater && !less) return Relation.EQUAL;
        return greater ? Relation.AFTER : Relation.BEFORE;
    }
}
~~~

Phép join là max theo thành phần, thỏa các tính chất của một join-semilattice:

\[
X\sqcup Y=Y\sqcup X,\qquad
(X\sqcup Y)\sqcup Z=X\sqcup(Y\sqcup Z),\qquad
X\sqcup X=X.
\]

Nghĩa là **giao hoán, kết hợp và lũy đẳng** cho *causal context*. Tuy nhiên, **không suy ra payload cũng tự merge đúng**. Với bản cập nhật dữ liệu, vẫn phải có chính sách hợp nhất hoặc lựa chọn nội dung.

### 14.1. Ví dụ gọi phép toán

~~~java
import java.util.Map;

public class VectorDemo {
    public static void main(String[] args) {
        VersionVector base =
            new VersionVector(Map.of("A", 1L));

        VersionVector a = base.increment("A");
        VersionVector b = base.increment("B");

        System.out.println(a.counters()); // {A=2}
        System.out.println(b.counters()); // {A=1, B=1}
        System.out.println(a.compareTo(b)); // CONCURRENT

        VersionVector context = a.join(b);  // {A=2, B=1}
        VersionVector resolved = context.increment("A");
        // {A=3, B=1}

        System.out.println(resolved.compareTo(a)); // AFTER
        System.out.println(resolved.compareTo(b)); // AFTER
    }
}
~~~

Điều kiện của ví dụ: actor A phát số tuần tự đúng protocol, không có hai writes khác nhau cùng nhận counter 3. Đoạn Java chỉ triển khai phép toán trên map, **không** giải quyết đồng bộ bộ đếm actor giữa các threads/processes.

## 15. Hai writers cùng actor không được cấp trùng counter

Phản ví dụ:

~~~text
Node A có vector {A:5}.
Writer X đọc rồi tạo {A:6} với payload "X".
Writer Y cũng đọc rồi tạo {A:6} với payload "Y".
Không có atomic assignment hoặc serialization.
~~~

Hai payload khác nhau mang cùng vector; phép so cho **EQUAL** mặc dù hai sự kiện ghi thực tế độc lập. Đây là **lỗi protocol cấp version**, không phải lỗi của hàm compare.

Muốn tránh:

- Actor có nguồn cấp counter tuần tự/atomically theo scope.
- Dùng CAS/transaction cho cấp version của cùng key.
- Dùng một dot có định danh update độc lập theo giao thức tương ứng.
- Actor ID có epoch/incarnation để tránh tái sử dụng sau restart.
- Không cho các clients tự gửi counter không kiểm soát rồi được server tin tưởng.

Một vector chỉ có giá trị khi **mọi sự kiện thuộc cùng actor được định danh duy nhất và thứ tự nhân quả được duy trì**.

## 16. Read–modify–write nên mang causal context

Một giao thức ở mức khái niệm:

~~~text
GET /profiles/u42
Response:
  value: {...}
  context: {A:4, B:2}

Client sửa và gửi:
PUT /profiles/u42
Body:
  desiredValue: {...}
  observedContext: {A:4, B:2}
  mutationId: "mut-1001"

Server:
  Validate authorization, mutationId, context.
  Assign a unique new version/dot.
  Compare against currently stored siblings.
  Preserve concurrent versions not seen by client.
  Return new context or conflict for resolution.
~~~

Nếu client **không mang context**, server khó biết nó đã nhìn thấy những cập nhật nào. Một số hệ dùng version token opaque do server cấp, số khác dùng `ETag/If-Match` với CAS.

**Không cho client tự tăng vector rồi tin tuyệt đối.** Một actor giả mạo counter rất cao có thể tuyên bố sai rằng nó đã thấy mọi thay đổi, và khiến engine bỏ một nhánh chưa được merge. Causal context cần gắn đúng tenant/key, được xác thực/kiểm soát bởi protocol.

## 17. Concurrent chưa chắc là xung đột payload

Hai cập nhật concurrent:

~~~text
A sửa profile.displayName.
B sửa profile.notificationLanguage.
~~~

Nếu hai field độc lập, có thể hợp nhất thành một document. Nhưng:

~~~text
A đặt preferredContact = EMAIL.
B đặt preferredContact = SMS.
~~~

Cùng một field bị đổi hai cách cần chính sách rõ.

Với invariant cứng:

~~~text
A giảm availableStock 1.
B giảm availableStock 1.
~~~

Chỉ biết A và B concurrent **không ngăn** hai decrements cùng vượt quota. Vector phát hiện forks sau sự kiện, còn business invariant cần conditional write, escrow hoặc coordination phù hợp.

| Quan hệ | Dạng sửa đổi | Cách xử lý |
|---|---|---|
| BEFORE/AFTER | Descendant hợp lệ | Có thể bỏ ancestor khi protocol đảm bảo |
| CONCURRENT | Hai field độc lập | Field-wise merge nếu domain cho phép |
| CONCURRENT | Cùng field hai giá trị | Conflict policy/UX |
| CONCURRENT | Hai giảm quota cứng | Protocol bảo vệ invariant |
| EQUAL | Payload khác nhau | Kiểm tra version collision/corruption |

## 18. Siblings: lưu các phiên bản không so được

Một số thiết kế multi-writer lưu nhiều **siblings** thay vì âm thầm ghi đè:

~~~json
{
  "key": "profile:u42",
  "siblings": [
    {
      "value": {"address": "18 B", "phone": "0900"},
      "context": {"A": 2}
    },
    {
      "value": {"address": "12 A", "phone": "0911"},
      "context": {"A": 1, "B": 1}
    }
  ]
}
~~~

Khi nhận version N:

- Nếu old BEFORE N: N bao hàm old, có thể thay old nếu payload semantics đúng.
- Nếu N BEFORE old: N là bản cũ, không ghi đè old.
- Nếu CONCURRENT: giữ nhiều siblings hoặc chạy merge policy.
- Nếu EQUAL: kiểm tra dedup và payload fingerprint.

Khi client **đọc đủ cả siblings** rồi tạo một merged write, version mới bao hàm hai causal contexts. Khi đó engine có thể loại hai siblings cũ sau khi merge được commit.

Nếu nhiều writers cập nhật offline liên tục, **sibling explosion** tăng storage, bandwidth, CPU và độ phức tạp UX. Cần giới hạn theo policy an toàn, đo sibling count và có quy trình giải conflict; không bỏ ngẫu nhiên các nhánh chưa được hợp nhất.

## 19. Anti-entropy giữa hai replica

Một ví dụ:

~~~text
Replica A: VA={A:5,B:2}
Replica B: VB={A:4,B:3}

A lớn hơn ở A, B lớn hơn ở B.
=> CONCURRENT.
~~~

Khi anti-entropy, hệ có thể trao đổi cả hai siblings rồi merge. Không được gọi VA “mới hơn” chỉ vì component A lớn hơn.

Ngược lại:

~~~text
Replica A: {A:5,B:3}
Replica B: {A:4,B:3}
~~~

A dominates B. B có thể cập nhật theo descendant nếu payload/version đúng và không có nhánh khác phải giữ.

Một version vector gắn với **một key** không tự chứng minh mọi keys trong cluster đã hội tụ. Stream offset, per-partition anti-entropy progress và sibling context là những nguồn thông tin có semantics khác nhau.

## 20. Stale update và mutation dựa trên bản cũ

Giả sử:

~~~text
Server current:
  S={A:5,B:4}

Client offline gửi snapshot cũ:
  Old={A:3,B:2}
~~~

Old là ancestor và thường không được overwrite bản S. Nhưng nếu client gửi **mutation mới dựa trên Old**, phải phân biệt:

- Một snapshot cũ được replay → bỏ qua theo protocol.
- Một full-document replacement dựa trên Old → có thể conflict với S.
- Một operation idempotent dạng add-tag/append-event → xử lý theo operation ID/merge.
- Một write được server cấp vector mới nhưng payload vẫn stale → có thể **lost update** nếu không kiểm tra context.

Cấp vector cao hơn **không làm payload cũ đúng hơn**. Server chỉ được tuyên bố một phiên bản bao hàm version khác khi nó thực sự đã xử lý/giải quyết nhánh đó theo contract.

## 21. CAS, ETag và version vector không thay thế nhau

**Compare-and-set (CAS)** thường nói: “Chỉ ghi nếu giá trị/version hiện tại vẫn đúng điều tôi đã đọc.” Với một nguồn có thẩm quyền, kiểm tra nguyên tử này ngăn hai writers cùng ghi đè phiên bản cũ mà không phát hiện.

**Version vector** nói: “Hai phiên bản có cùng lịch sử được quan sát hay rẽ nhánh ở những actors khác nhau?” Nó hữu ích khi replica có thể tạm nhận ghi độc lập.

| Công cụ | Câu hỏi giải quyết | Không tự giải quyết |
|---|---|---|
| Integer version + CAS | Current version có còn như client đã đọc? | Mọi lịch sử fork ở nhiều writers |
| ETag/If-Match | Client đang update đúng representation nào? | Merge hai concurrent values |
| Vector clock/version vector | Ancestor, descendant hay concurrent? | Domain merge/invariant |
| Transaction/consensus | Những thao tác phải có thứ tự commit hợp lệ? | Mọi side effect ngoài DB |
| CRDT | Có phép merge hội tụ đúng semantics? | Mọi invariant cứng |
| LWW | Bản nào thắng theo quy tắc timestamp/order? | Giữ nguyên cả hai thay đổi |
| Idempotency ledger | Một business intent đã áp dụng chưa? | Thứ tự nhân quả của mọi event |

CAS và version vector **có thể dùng cùng nhau**. Chẳng hạn server dùng CAS để ghi nguyên tử **tập siblings mới và metadata**, còn vectors để quyết định sibling nào đã trở thành ancestor.

## 22. Cập nhật tập siblings phải nguyên tử

Một lỗi phổ biến:

~~~text
Writer X đọc siblings = [V0].
Writer Y đọc siblings = [V0].

X tạo VX, ghi siblings = [VX].
Y tạo VY, ghi siblings = [VY].

VX bị mất mặc dù Y chưa từng đọc VX.
~~~

Có vector trên mỗi version **không đủ** nếu thao tác thay thế tập siblings là read–then–write không có bảo vệ cạnh tranh.

Mô hình khái niệm:

~~~text
loop with bounded retries:
    current = load(key)  // revision + sibling set
    proposed = classifyAndMerge(current, incomingVersion)
    ok = conditionalReplace(
        key,
        expectedRevision = current.revision,
        next = proposed
    )
    if ok: break
    else: refetch and retry/reconcile
~~~

Điều kiện thay thế theo revision phải atomic trong phạm vi database. Nếu hệ multi-leader cho phép ghi ở hai nơi không liên lạc, cần thêm **replication protocol** để cả hai update tồn tại cho tới khi được so/merge; CAS nội bộ của một leader không tự xử lý cả fork xuyên regions.

## 23. Xóa dữ liệu cũng phải là một causal event

Nếu A xóa record trong lúc B giữ phiên bản offline cũ, B có thể “hồi sinh” record sau khi sync nếu xóa chỉ là **không còn row**.

Một versioned tombstone:

~~~json
{
  "key": "profile:u42",
  "deleted": true,
  "context": {"A": 7, "B": 3},
  "deletedAt": "2026-11-14T10:00:00Z"
}
~~~

Khi đồng bộ:

- Tombstone dominates bản cũ → bản xóa có thể thắng theo protocol.
- Tombstone concurrent với update → cần **delete-wins, update-wins, siblings hoặc manual merge** theo domain.
- Snapshot cũ đến trễ → không được tự resurrect record ngoài hợp đồng.

Tombstones không thể xóa tùy tiện khi một peer lâu ngày chưa sync vẫn có thể phát lại phiên bản cũ. Retention/garbage collection cần điều kiện causal stability, membership/epoch hoặc quy tắc thời gian có giới hạn được chấp nhận.

**TTL không phải cơ chế tự giải conflict.** Một bản ghi mất do TTL ở một replica chưa chứng minh mọi actor đã quan sát deletion.

## 24. Actor IDs: replica, vnode hay client?

Actor có thể đại diện cho:

| Granularity | Ưu điểm | Vấn đề |
|---|---|---|
| Replica ổn định | Vector gọn khi ít replicas | Cần tuần tự hóa cập nhật nhiều clients |
| Vnode | Gắn logical owner với replication | Reshard/rebalance và incarnation |
| Service instance | Dễ cấp ID theo instance | Churn/restarts làm context dài |
| Thiết bị offline | Theo dõi writer độc lập | Hàng nghìn thiết bị → vector lớn |
| Một per-document writer authority | Dễ cấp phiên bản tuần tự | Có thể thành coordination bottleneck |
| Client session | Hữu ích causal session | Phải xử lý session mới/hết hạn |

Không có actor mapping tốt nhất cho mọi hệ. Cần xác định **đối tượng có counter không trùng và scope đồng bộ**. Một actor mất state rồi khởi động lại với ID cũ, counter trở về 1 có thể tạo **va chạm version**; giải pháp có thể dùng stable persisted counter hoặc incarnation/epoch ID mới.

## 25. Vector cơ bản có chi phí metadata O(số actors)

Nếu một key được sửa qua ba replica, vector có thể gọn. Nếu mỗi thiết bị offline được coi là actor độc lập và có 50.000 thiết bị từng sửa key, một vector cơ bản có thể dài hàng chục nghìn components.

Tác động:

- Gói read/write mang nhiều metadata.
- So sánh/join cần duyệt thêm actor entries.
- Kích thước item, network và replication logs tăng.
- Lưu nhiều siblings nhân thêm chi phí.
- Actor churn khiến context cũ khó dọn.
- Có nguy cơ chạm giới hạn item/request của database.
- Anti-entropy và cursor tokens mang metadata đáng kể.

**Không tùy tiện bỏ actor có counter nhỏ** để tiết kiệm bộ nhớ: vector bị cắt có thể làm đổi kết quả BEFORE/AFTER/CONCURRENT. Garbage collection phải dựa trên một protocol chứng minh các nhánh cần thiết đã ổn định hoặc chấp nhận đánh đổi được mô tả.

## 26. Dotted version vectors: phân biệt “lịch sử đã thấy” và “sự kiện mới”

Một **dotted version vector (DVV)** hoặc biến thể tương tự mô tả một bản cập nhật bằng:

- **Causal context:** các sự kiện mà writer đã quan sát.
- **Dot:** định danh sự kiện mới, thường có dạng `(actor, counter)`.

Biểu diễn minh họa:

~~~json
{
  "context": {"A": 2, "B": 1},
  "dot": {"actor": "A", "counter": 3},
  "value": {"displayName": "Linh"}
}
~~~

Dot là **event mới** nằm trên context đã được thấy. Protocol DVV có quy tắc so/bao hàm sự kiện đầy đủ, không thể thay bằng việc chỉ so các trường `context` như vector clock thông thường.

### 26.1. Vì sao chỉ một counter replica có thể gây nhập nhằng?

Giả sử hai clients đều đọc bản gốc context `{A:2}`. Sau đó cùng ghi đến server A:

~~~text
Client X đã thấy {A:2}, gửi value X.
Server cấp dot (A,3).

Client Y cũng chỉ thấy {A:2}, gửi value Y.
Server cấp dot (A,4).
~~~

Về **thứ tự xử lý server**, write Y đến sau write X. Nhưng về **causal context của hai giá trị client gửi**, Y **chưa thấy và chưa giải quyết** X. Nếu chỉ nhìn version vector `{A:4}` so với `{A:3}` rồi ghi đè, X có thể bị xem nhầm là ancestor của Y.

Các biến thể dotted metadata giúp phân biệt: dot `(A,4)` được tạo trên **context {A:2}**, không phải trên context đã bao gồm `(A,3)`. Vì thế có thể giữ X và Y làm siblings nếu domain yêu cầu.

Đây là động cơ quan trọng cho các giải pháp DVV trong những hệ nhận updates từ nhiều clients trên cùng replica. Không nên tự dựng DVV bằng một JSON dot rồi áp phép compare vector thường; cần thực thi **đúng luật bao hàm dots/context** của protocol được chọn.

## 27. Version vector with exceptions và vector “có lỗ”

Một số luồng nhân quả không thể giả định “đã thấy counter 10 thì đã thấy 1–9” nếu message delivery có gaps. Ví dụ:

~~~text
Đã thấy event của actor A:
  A1, A2, A4, A5

Chưa thấy:
  A3
~~~

Một high-water mark `A:5` **không đủ để nói đã thấy mọi sự kiện A1–A5** trừ khi giao thức bảo đảm prefix-closed delivery/commit. Một cấu trúc **version vector with exceptions** hoặc gap-aware log cần biểu diễn phần thiếu.

Trong một vector clock chuẩn, counter actor phản ánh thứ tự events với causal transmission, không được tùy tiện dùng counter lớn nhất của một event stream thiếu messages làm causal summary đầy đủ. Khi event delivery out-of-order, phải buffer/replay hoặc dùng cấu trúc lưu gaps.

Điểm cần hỏi là **định nghĩa của counter**: đó là đếm các sự kiện liên tục đã biết, hay chỉ là ID mới nhất đã nhìn thấy? Chỉ trường hợp thứ nhất mới hỗ trợ suy luận prefix theo protocol.

## 28. Causal stability và garbage collection

Một sự kiện được gọi là **causally stable** trong một số mô hình khi có đủ bằng chứng rằng các participants có liên quan đã tiến tới điểm mà không còn xuất hiện concurrent events cần giữ đối với nó, theo giả định membership và delivery của hệ.

Khái niệm này có thể giúp:

- Prune causal metadata hoặc tombstones an toàn hơn.
- Gộp lịch sử đã ổn định thành summary.
- Dọn siblings đã được tất cả phía cần thiết bao hàm.
- Giảm kích thước anti-entropy state.

Nhưng điều kiện ổn định phụ thuộc vào **ai được tính là participant**. Với thiết bị có thể offline nhiều tháng, việc tuyên bố mọi actor đã nhìn thấy version có thể không khả thi nếu không có membership/expiry/epoch policy.

Không nên nhầm “replication lag hiện tại bằng 0” với causal stability toàn hệ, nhất là khi có clients offline hoặc event queues chưa replay.

## 29. Concurrency detection và resolution pipeline

Một workflow nhiều bước:

~~~mermaid
flowchart TD
    A["Nhận update + observed context"] --> B["Validate auth, key, mutation ID"]
    B --> C["Lấy tập versions hiện tại"]
    C --> D["So causal versions/dots"]
    D --> E{"Quan hệ?"}
    E -->|Ancestor| F["Bỏ bản cũ/accept descendant"]
    E -->|Concurrent| G["Giữ siblings hoặc domain merge"]
    E -->|Equal| H["Dedup/kiểm tra payload"]
    G --> I["Tạo merged event nếu thật sự đã resolve"]
    F --> J["Atomic commit / replication"]
    H --> J
    I --> J
    J --> K["Trả context mới + outcome"]
~~~

Các boundary quan trọng:

1. **Validate:** một client không được ghi vào tenant khác hoặc tự tuyên bố context giả.
2. **Observe:** đọc đủ siblings/versions cần so.
3. **Assign:** cấp dot/version duy nhất.
4. **Decide:** dùng causal ordering; không chọn winner mù.
5. **Commit:** cập nhật data + metadata atomically trong phạm vi cần thiết.
6. **Replicate:** gửi các nhánh hoặc merged descendant với metadata.
7. **Reconcile:** xử lý các peers reconnect/duplicate/out-of-order.
8. **Audit:** giữ lịch sử nếu business yêu cầu truy vết lost/merged changes.

## 30. Merge policy theo ngữ nghĩa dữ liệu

Một số lựa chọn:

| Kiểu dữ liệu | Ví dụ conflict | Chính sách có thể cân nhắc |
|---|---|---|
| Profile, hai fields độc lập | A sửa tên, B sửa ngôn ngữ | Field-wise merge |
| Profile, cùng field | A đặt tên X, B đặt tên Y | UI/manual resolution hoặc deterministic priority |
| Add-only set | A thêm tag X, B thêm tag Y | Union/set CRDT phù hợp |
| Remove/add set | A xóa X, B thêm X | Xác định add-wins/remove-wins |
| Counter view | A +5, B +7 | Counter CRDT theo protocol, dedup event nếu cần |
| Shopping cart | A thêm item, B xóa item | OR-set/dot semantics, business merge rules |
| Text document | Cùng sửa cùng đoạn | OT/CRDT hoặc merge tool |
| Order status | A CANCELLED, B PAID | State machine/reconciliation, không merge tự do |
| Inventory quota | A giữ 1, B giữ 1 | Escrow/quorum/transaction bảo vệ capacity |
| Permission revoked | A thu hồi, B sửa profile | Có thể phải ưu tiên security/fail closed |

**Có thể phát hiện concurrent không đồng nghĩa có thể tự động hợp nhất.** Mô hình miền nghiệp vụ quyết định xung đột nào cần người dùng giải và xung đột nào phải bị ngăn trước khi commit.

## 31. CRDT và version vector liên hệ nhưng không đồng nhất

CRDT (*Conflict-free Replicated Data Type*) thiết kế operations/state sao cho các replicas có thể hội tụ dưới điều kiện phù hợp. Một số CRDT dùng **dots, causal context, version vectors** để phân biệt additions/removals hoặc updates.

Nhưng có các điểm khác:

- Version vector cho biết **quan hệ nhân quả**, không tự định nghĩa giá trị hợp nhất.
- CRDT định nghĩa **phép merge của state/operation** theo cấu trúc cụ thể.
- Một CRDT counter có thể hội tụ mà không cần application xử lý siblings thủ công.
- CRDT không bảo vệ mọi invariant xuyên nhiều objects, ví dụ không oversell một vé có quota duy nhất.
- LWW register là một lựa chọn theo timestamp/order; nó có thể hội tụ nhưng vẫn làm mất một cập nhật concurrent có ý nghĩa.

Cần chọn CRDT khi **business semantics chấp nhận merge đã định nghĩa**, không chỉ vì muốn “multi-region luôn ghi được”.

## 32. Causal consistency khác linearizability

**Causal consistency** yêu cầu các quá trình quan sát quan hệ nhân quả theo thứ tự phù hợp, nhưng **không ép một thứ tự toàn cục duy nhất** cho mọi sự kiện concurrent.

**Linearizability** cho phép xem thao tác giống như diễn ra tại một điểm hiệu lực giữa lúc gọi và lúc phản hồi, tuân thủ thứ tự thời gian thực cho các thao tác không chồng lấp.

Ví dụ:

~~~text
A ghi x=1 và nhận ACK.
Sau đó, B bắt đầu GET x qua hệ khác.
~~~

Nếu B không phụ thuộc causally vào A theo session/message context, một mô hình causal nhất định có thể cho B đọc phiên bản chưa thấy A, trong khi một GET linearizable trên cùng đối tượng không được phép trả trước write đã hoàn tất khi không có write mới hơn.

Vector clocks có thể giúp thực thi/suy luận causal order nhưng **không tự biến mọi read thành linearizable**. Muốn consistency mạnh hơn phải dùng protocol phù hợp (leader/quorum/consensus/transaction) với phạm vi bảo đảm rõ.

## 33. Version vector không đảm bảo durability hay exactly-once

Một system có thể gắn vector cho mọi update và phát hiện đồng thời chính xác, nhưng vẫn:

- Mất dữ liệu đã ACK do chưa replicate bền.
- Gửi message lặp hoặc bỏ sót khi outbox không atomically ghi.
- Áp cùng payment charge hai lần do retry với IDs mới.
- Để hai concurrent reservations cùng vượt quota.
- Đọc search projection stale.
- Restore backup ở mốc làm lệch version data/metadata.
- Ghi hai vector khác payload cùng ID do actor counter collision.

Cần phân biệt:

| Thuộc tính | Cơ chế trọng tâm |
|---|---|
| Causal ordering | Vector clocks/version vectors |
| Conflict handling | Domain merge, siblings, CRDT hoặc policy rõ |
| Uniqueness/idempotency | Stable business IDs, unique constraints, result ledger |
| Atomicity | Transaction/CAS phù hợp |
| Durability | Journal, replication, ACK contract, backup |
| Strong consistency | Protocol read/write/consensus theo phạm vi |
| Event delivery | Outbox/Inbox, retries và reconciliation |

Bổ sung vector field không thay các lớp này.

## 34. Dynamo, DynamoDB và vector clocks: cần phân biệt lịch sử với sản phẩm

Trong lịch sử hệ phân tán, kiến trúc **Dynamo** được biết đến với cách mô tả nhiều versions và causal metadata để phát hiện xung đột khi các replicas cùng có thể nhận write, từ đó để ứng dụng hòa giải một số conflicts. Các hệ lấy cảm hứng từ Dynamo đã dùng những kỹ thuật liên quan vector clocks, siblings, read repair và anti-entropy.

**Không đồng nhất thiết kế trong bài báo Dynamo với mọi chế độ của dịch vụ Amazon DynamoDB ngày nay.** DynamoDB có API conditional writes, transactions, consistency modes, và những lựa chọn replication đa vùng tùy cấu hình; không nên tuyên bố một API `GetItem` hiện luôn trả vector clock/siblings giống mô hình lý thuyết.

Khi dùng một managed NoSQL service, hãy kiểm tra hợp đồng của **chính phiên bản/chế độ đang triển khai**:

1. Multi-region writes có thể xung đột trong tình huống nào?
2. Hệ dùng last-writer-wins hay một cơ chế conflict resolution khác?
3. Có lộ causal token/version vector cho ứng dụng không?
4. Conditional writes có phạm vi regional hay toàn cục như yêu cầu?
5. Một event replica đến muộn có thể ghi đè giá trị gì?
6. Ứng dụng có cần tự dùng business version/merge protocol không?

Có thể tự lưu causal context trong một item, nhưng việc đó **không tự làm database thực thi vector-based concurrency control**. Đặc biệt, nếu hai writers có thể sửa item ở hai regions mà không có atomic update chung, một map version đặt trong JSON vẫn có thể bị ghi đè.

## 35. Riak và các hệ giữ siblings: bài học thiết kế

Một số hệ như **Riak** trong các phiên bản/cấu hình lịch sử đã sử dụng vector-clock-related metadata và sau này các biến thể **dotted version vectors** để biểu diễn causal history/concurrent updates.

Điều đáng học từ mô hình đó là vòng lặp:

~~~text
Read key, lấy value(s) + causal context.
Client dựa trên dữ liệu đã đọc để cập nhật.
Write kèm context.
Hệ phân biệt descendant và concurrent versions.
Nếu concurrent, giữ siblings/áp resolver.
Sau merge, trả causal context của version mới.
~~~

Nếu client không xử lý siblings mà chỉ lấy một sibling rồi ghi lại thành một bản “giải quyết tất cả”, có thể xóa mất nhánh chưa quan sát. Nếu dùng LWW resolver ở phía server, có thể không còn siblings để ứng dụng giải.

Không lấy một ví dụ API Riak cũ và áp nguyên vào phiên bản hiện đại của một hệ khác; tên field, context token và cleanup semantics cần xem tài liệu sản phẩm cụ thể.

## 36. CouchDB revision tree khác một vector clock giản lược

**CouchDB** có cơ chế revisions và replication/conflict tracking cho documents; một document có thể có các nhánh revision trong tình huống cập nhật phân tán. Tuy nhiên một `_rev` identifier **không phải** một vector clock dạng map actor→counter.

Ví dụ khái niệm:

~~~json
{
  "_id": "profile:u42",
  "_rev": "3-someRevisionHash",
  "name": "Linh"
}
~~~

Một revision token giúp nhận diện bản cụ thể và hỗ trợ optimistic update theo API, nhưng chỉ nhìn một số generation lớn hơn không đủ suy rằng revision đó **bao hàm nhánh khác** khi có replication conflicts. Muốn phân tích quan hệ cần xem revision lineage/conflict contract của hệ.

Điểm chung với vector-based design: cần phân biệt **một dòng lịch sử tuyến tính** và **nhiều nhánh concurrent**, sau đó xử lý conflict an toàn. Điểm khác: cách biểu diễn, so sánh, xóa revision cũ và conflict exposure là riêng của engine.

## 37. Cassandra/ScyllaDB: timestamp reconciliation không phải vector compare

Trong các mô hình họ Cassandra, conflict resolution đối với cells thường dựa trên timestamps và các quy tắc reconciliation của engine, cùng consistency level/replication/repair. Đó không phải lời hứa rằng mỗi CQL row mang version vector do ứng dụng so để phát hiện mọi concurrent business write.

Ví dụ:

~~~text
Client A: set profile.phone = "0900" với timestamp TA
Client B: set profile.phone = "0911" với timestamp TB

Replication có thể chọn một value theo reconciliation rule.
Ứng dụng không nhất thiết được trả cả hai phiên bản.
~~~

Nếu yêu cầu phát hiện “hai thiết bị đã sửa cùng field mà chưa nhìn thấy nhau”, có thể cần xây application revision/causal token, conditional updates theo khả năng engine, hoặc lựa chọn data model phù hợp. **LWT/CAS** có thể giải một kiểu lost-update bằng cách tuần tự hóa điều kiện trong phạm vi hỗ trợ, nhưng không tự biến các loại writes thành phiên bản vector causal.

Chọn cách nào phụ thuộc yêu cầu: ưu tiên write availability và chấp nhận resolver, hay ưu tiên không mất update cùng key và cần coordination.

## 38. MongoDB: version field và conditional update là lựa chọn khác

Một document MongoDB có thể lưu integer version:

~~~javascript
{
  _id: "profile:u42",
  version: 7,
  displayName: "Linh"
}
~~~

Nếu client đọc version 7, chỉ cho phép ghi khi version vẫn 7:

~~~javascript
db.profiles.updateOne(
  { _id: "profile:u42", version: 7 },
  {
    $set: { displayName: "Linh Nguyễn" },
    $inc: { version: 1 }
  }
);
~~~

Nếu `matchedCount=0`, caller phải đọc lại và quyết định retry/merge, không tự gán version 8 trên bản payload cũ.

Đây là **optimistic concurrency control bằng CAS của một document**, không phải vector clock native. Khi có nhiều primary/replicas và ứng dụng muốn giữ các nhánh offline cùng lúc, một integer version ở một nguồn có thẩm quyền có thể **buộc conflict ngay tại thời điểm commit**, thay vì lưu siblings để merge sau.

Nếu tự lưu vector vào MongoDB document, phải dùng conditional write/transaction khi cập nhật vector + payload/sibling set. Cứ `findOne → compare vectors → replaceOne` không có condition có thể mất một cập nhật cạnh tranh.

## 39. Redis: atomic operations và vector metadata là hai chuyện khác

Redis cho phép atomic operations trong phạm vi server/slot phù hợp, nhưng không mặc nhiên trả version vector cho một key đã được ghi ở nhiều replicas.

Ví dụ ứng dụng lưu JSON causal context:

~~~json
{
  "value": {"displayName": "Linh"},
  "vector": {"A": 2, "B": 1}
}
~~~

Nếu một worker chỉ đọc JSON rồi sửa và SET lại trong một bước khác, hai workers có thể tạo lost update dù trường `vector` trông rất khoa học. Cần atomic CAS/script/transaction pattern phù hợp với phạm vi keys/slots, hoặc một source có thẩm quyền ngoài Redis.

Trong Redis Cluster, nếu siblings/context ở nhiều keys khác hash slots, một multi-key Lua script có thể không atomic được trên tất cả keys theo model cluster. Replication/failover của Redis cũng có durability/consistency constraints riêng; vector tracking không sửa được dữ liệu đã mất từ primary trước replication.

## 40. Điểm chung của các NoSQL engines

| Thiết kế | Cơ chế phổ biến | Có tự cung cấp vector siblings? |
|---|---|---|
| Dynamo (kiến trúc nghiên cứu lịch sử) | Causal metadata/vector clocks, reconcile concurrent versions | Là một ý tưởng cốt lõi |
| Một số Riak triển khai lịch sử | Vector/dotted version metadata và siblings | Phụ thuộc phiên bản/config |
| CouchDB | Revision trees, document conflicts | Không nên coi _rev là vector map |
| MongoDB | Per-document atomic update, CAS, transactions | Không mặc định có vector sibling API |
| DynamoDB | Conditional writes, transactions, replication modes | Không đồng nhất với giao thức Dynamo paper |
| Cassandra/ScyllaDB | Timestamp reconciliation, CL, LWT trong phạm vi | Không mặc định có version-vector sibling contract |
| Redis | Atomic commands/scripts theo phạm vi và replication | Không mặc định có causal-version tracking |

Bảng này là **định hướng về mô hình**, không phải so sánh đủ tính năng hay bảo đảm của mọi phiên bản năm hiện tại. Đừng lựa chọn sản phẩm chỉ từ việc “có vector clock” nếu bài toán thật cần transaction, durability, indexing hoặc kiểm soát quota.

## 41. Vấn đề mức độ chi tiết: vector gắn vào object hay field?

Nếu vector gắn với **toàn profile document**, hai phiên bản sửa hai fields độc lập có thể bị phát hiện là concurrent và giữ siblings. Điều đó an toàn cho bảo tồn thông tin nhưng tạo conflict mặc dù merge nội dung đơn giản.

Nếu vector gắn **từng field**, cập nhật phone và address có thể không cạnh tranh trong cùng conflict domain, nhưng metadata tăng, và các invariants **liên field** có thể bị bỏ qua nếu merge tự do.

| Phạm vi causal version | Lợi ích | Rủi ro |
|---|---|---|
| Toàn document | Dễ biểu diễn một version cho object | Phát hiện nhiều concurrent edits không thực sự cùng field |
| Theo field | Fine-grained merge | Metadata lớn và rules liên field khó |
| Theo aggregate nghiệp vụ | Phù hợp invariant boundary | Aggregate quá lớn thành hot key |
| Theo operation/event | Dễ ghi lại ý định | Cần reducer/state machine và causal ordering |
| Theo replica stream | Thuận anti-entropy | Chưa đủ nói quan hệ hai phiên bản của một key |

Chọn conflict domain theo semantics. Một trường `shippingAddress` có thể gồm street, postalCode, country; tách từng field merge tùy tiện có thể tạo địa chỉ không tồn tại. Khi đó coi address là một aggregate nhỏ hợp lý hơn.

## 42. Chỉnh sửa offline và synchronization token

Một ứng dụng offline-first thường lưu:

~~~json
{
  "documentId": "note-1001",
  "baseContext": {"deviceA": 4, "deviceB": 2},
  "mutationId": "m-1001",
  "changes": [
    {"op": "replace", "path": "/title", "value": "Ghi chú mới"}
  ]
}
~~~

Khi reconnect:

1. Xác minh user/session và quyền sửa.
2. Đọc current server state cùng causal metadata.
3. Phân biệt mutation trùng theo `mutationId`.
4. So `baseContext` với current version(s).
5. Nếu server descendant đã thay cùng field, áp policy conflict.
6. Nếu changes độc lập, có thể merge và tạo version mới.
7. Lưu outcome/context để client retry an toàn.
8. Trả version/sibling state cho client tiếp tục.

Không nhận một `baseContext` không có dấu xác thực/kiểm soát từ client như bằng chứng tuyệt đối. Với ứng dụng nhiều thiết bị, còn phải xét **device reinstall/actor incarnation** và điều gì xảy ra nếu thiết bị offline lâu hơn retention của tombstones/causal history.

## 43. Vector metadata trong message broker: dùng đúng mục đích

Một event:

~~~json
{
  "eventId": "evt-1001",
  "aggregateId": "profile:u42",
  "sourceActor": "A",
  "causalContext": {"A": 5, "B": 2},
  "operation": "PROFILE_UPDATED"
}
~~~

Causal context có thể giúp consumer xác định một event phụ thuộc những cập nhật đã có. Nhưng:

- Broker có thể **at-least-once** → phải dedup event ID.
- Event có thể đến out-of-order → cần buffer/gap handling khi ordering quan trọng.
- Vector cho profile không phải vector cho toàn database.
- Một consumer biết eventId và context không có nghĩa transaction source đã commit hợp lệ nếu outbox không atomic.
- Event payload có thể thiếu dữ liệu để merge; phải giữ operation semantics.
- Cần quyền truy cập/tenant scope: không trust context ngoài authority.

Ví dụ projection nhận event vector `{A:5,B:2}` trong khi chỉ có `{A:3,B:2}`. Nếu protocol bảo đảm event có đầy đủ snapshot state, có thể ứng dụng áp descendant trực tiếp theo quy tắc. Nếu event chỉ là delta cần mọi bước, **bỏ qua A4** có thể khiến projection sai dù vector cao hơn. Vậy causal metadata **không thay thế event replay và loại event**.

## 44. Thực nghiệm 1: so vector theo bộ trường hợp cố định

Dùng lớp Java đã xây hoặc tự viết `compare(X,Y)`:

| X | Y | Expected |
|---|---|---|
| `{}` | `{}` | EQUAL |
| `{}` | `{A:1}` | BEFORE |
| `{A:1}` | `{A:1}` | EQUAL |
| `{A:1}` | `{A:2}` | BEFORE |
| `{A:3}` | `{A:2}` | AFTER |
| `{A:2,B:0}` | `{A:1,B:1}` | CONCURRENT |
| `{A:2,B:2}` | `{A:3,B:2}` | BEFORE |
| `{A:3,B:1}` | `{A:2,B:2}` | CONCURRENT |
| `{A:2,C:3}` | `{A:2,B:1,C:3}` | BEFORE |
| `{A:4,B:4,C:1}` | `{A:4,B:4,C:1}` | EQUAL |

`{A:2,B:0}` và `{A:2}` là cùng causal vector nếu missing=0. Một bug phổ biến là chỉ duyệt keys của X mà bỏ actor chỉ có trong Y.

### 44.1. Kiểm tra tính chất bằng property-based tests

~~~text
compare(X,X) = EQUAL

Nếu X BEFORE Y:
    compare(Y,X) = AFTER

Nếu X CONCURRENT Y:
    compare(Y,X) = CONCURRENT

join(X,Y) = join(Y,X)

join(X,join(Y,Z)) = join(join(X,Y),Z)

join(X,X) = X

compare(X,join(X,Y)) thuộc {BEFORE,EQUAL}
compare(Y,join(X,Y)) thuộc {BEFORE,EQUAL}
~~~

Đây là tests về **toán học dữ liệu**. Chúng chưa kiểm tra protocol cấp actor counters/dots, lưu siblings, crash/retry hoặc correctness của merge payload.

## 45. Thực nghiệm 2: hai writers offline

Mô hình:

~~~text
Initial:
  document = {"title":"T0","body":"B0"}
  vector = {A:1}

Disconnect A và B.

Writer A:
  document = {"title":"T1","body":"B0"}
  vector = {A:2}

Writer B:
  document = {"title":"T0","body":"B1"}
  vector = {A:1,B:1}

Reconnect và anti-entropy.
~~~

Kỳ vọng:

1. Hai versions có quan hệ CONCURRENT.
2. Không tự chọn một version chỉ vì timestamp lớn hơn.
3. Nếu giữ siblings, cả hai payloads còn truy xuất được.
4. Nếu merge fields, document mới có title T1 và body B1.
5. Merged causal context bao hàm cả hai nhánh.
6. Một update sau merge phải dominate A/B.
7. Replay cùng messages không tạo siblings vô hạn.
8. Một client chưa thấy B không được tuyên bố đã giải quyết B.
9. Snapshot cũ tới muộn không ghi đè merged descendant.
10. Thứ tự messages A/B đến khác nhau không được làm mất nhánh.

Lặp lại test với A và B **cùng sửa title**. Khi đó phải có policy manual conflict/deterministic priority. Nếu policy LWW, ghi rõ nhánh nào bị mất và lý do; đừng gọi đó là “vector clock đã tự tìm phiên bản đúng”.

## 46. Thực nghiệm 3: race khi cấp version

Bắt đầu với record `{A:5}`. Hai writers cùng chạy:

~~~text
read current
increment actor counter
write payload + vector
~~~

Nếu không có cấp counter nguyên tử, cả hai có thể tạo `{A:6}` với hai payload khác nhau.

Thử các biến thể: per-actor serialized issuance, CAS/unique dots, revision-based atomic sibling-set update, idempotent mutation ID. Sau khi tất cả workers hoàn tất, kiểm tra **không có hai versions khác payload bị nhận diện EQUAL do va chạm counter**. Đây là phép thử version issuance, không chỉ payload conflict.

## 47. Thực nghiệm 4: partition rồi phục hồi

Chỉ chạy trong môi trường lab được phép gây lỗi:

~~~text
T0: A, B, C có bản gốc.
T1: C mất liên lạc với A/B.
T2: A/B nhận update X.
T3: C nhận update Y nếu topology cho phép.
T4: Phục hồi kết nối.
T5: Anti-entropy trao đổi phiên bản.
T6: Detect concurrent histories.
T7: Merge hoặc giữ siblings theo policy.
T8: Đọc lại từ mọi replicas ở consistency mode phù hợp.
~~~

Ghi rõ actor IDs, counter/dot issuance, context mà mỗi client đã thấy, trạng thái ACK, replica placement, siblings sau reconnect, kết quả sau duplicate/out-of-order delivery, metadata size và lag. Không kết luận “vector clock sửa được phân vùng mạng”; nó giúp **phát hiện lịch sử fork** và là một phần của giải pháp.

## 48. Observability của causal versions

| Metric | Câu hỏi |
|---|---|
| Concurrent version rate | Bao nhiêu updates fork? |
| Siblings per key | Key nào có nhiều unresolved versions? |
| Conflict resolution latency | Merge mất bao lâu? |
| Manual conflicts pending | Có bao nhiêu trường hợp chờ người dùng? |
| Vector component count | Metadata có tăng quá lớn? |
| Actor churn/epochs | Có nhiều IDs do restart/rebalance? |
| Equal vector, different payload | Có counter collision hoặc corruption? |
| Context validation failures | Client có gửi context sai không? |
| Anti-entropy lag | Replica thiếu updates trong bao lâu? |
| Tombstone resurrection | Data đã xóa có xuất hiện lại không? |
| Mutation dedup hits | Retries có bị xử lý trùng? |
| Resolution payload loss | Có bỏ nhánh trái business policy? |
| Read p95/p99 | Nhiều siblings có làm chậm GET? |
| Network/storage overhead | Vector/context chiếm bao nhiêu? |

Bộ metric write-success đơn thuần không phản ánh người dùng phải giải quyết hàng trăm conflicts. Cần đo cả **safety, lộ xung đột, độ trễ hội tụ và kinh nghiệm hợp nhất**.

## 49. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Giải pháp |
|---|---|---|
| Concurrent phải cùng timestamp | Vector xét causality | So từng component |
| Vector có tổng lớn hơn là mới hơn | Partial order | Có thể CONCURRENT |
| Cứ chọn counter của actor A cao hơn | Actor B có thể cao hơn ở vector kia | So tất cả components |
| EQUAL nghĩa payload chắc chắn bằng nhau | Version collision/corruption | Fingerprint và unique issuance |
| Client được tự gán vector rất cao | Có thể xóa nhánh chưa quan sát | Authority/context validation |
| Join hai vectors là merge nội dung | Max context không biết business value | Domain merge |
| Có vector thì không cần CAS | Sibling set vẫn bị lost update | Atomic write/transaction |
| CAS tại một leader mô tả mọi offline forks | CAS chỉ bảo vệ local current version | Causal sync protocol |
| LWW luôn giữ mọi thay đổi | Chọn winner và bỏ loser | Expose siblings nếu cần |
| Vector ngăn oversell | Chỉ phát hiện fork sau ghi | Quorum/escrow/conditional quota |
| Tombstone có thể xóa ngay | Peer offline có thể resurrect | Retention/causal stability |
| Dot chỉ là một vector khác | Dot là event, context là lịch sử | Đúng DVV protocol |
| Actor counter reset sau restart | Va chạm version | Persist counter/epoch |
| Mọi NoSQL dùng vector clock native | Sản phẩm khác nhau | Đọc engine contract |
| MongoDB integer version là version vector | Scalar CAS khác causal vectors | Phân biệt công cụ |
| DynamoDB giống hệt Dynamo paper | Managed API có semantics riêng | Xem chế độ cụ thể |
| _rev CouchDB là map actor→counter | Revision lineage khác vector map | Dùng revision contract |
| Event vector thay Inbox/Outbox | Retry và atomicity vẫn là bài toán riêng | Dedup/event workflow |
| Có replication thì vector bảo vệ durability | Durability phụ thuộc ACK/log | Tách thuộc tính |

## 50. Bài tập A — Phân loại vector

Cho các phiên bản:

~~~text
P = {A:2,B:0,C:0}
Q = {A:1,B:1,C:0}
R = {A:2,B:1,C:0}
S = {A:2,B:1,C:1}
T = {A:3,B:0,C:1}
~~~

Hãy:

1. So P với Q.
2. So P với R.
3. So Q với R.
4. So R với S.
5. So S với T.
6. Tính join(P,Q).
7. Tính join(S,T).
8. Liệt kê mọi cặp concurrent trong tập.
9. Giải thích vì sao lấy tổng counter của S/T để chọn winner là sai.
10. Nếu một merged write dựa trên S và T được tạo bởi B, tính vector sau join rồi tăng B.

**Gợi ý cách làm:** lập bảng giá trị từng actor; đánh dấu component nào lớn hơn và component nào nhỏ hơn; chỉ kết luận BEFORE/AFTER khi **tất cả** components có cùng hướng.

## 51. Bài tập B — Ghi chú offline-first

Một ứng dụng ghi chú có:

- Thiết bị A và B của cùng user.
- Offline edits dài tới 7 ngày.
- Note chứa title, body, tags.
- User có thể sửa đồng thời trên hai thiết bị.
- Không muốn âm thầm mất text edits.
- Server có thể lưu siblings và gửi conflict UI.

Thiết kế:

1. Actor IDs là device IDs hay server replicas? Nêu trade-off.
2. Context response gửi client theo token nào?
3. Mutation ID nào ngăn retry tạo hai edits?
4. Khi A thay title, B thêm tag, merge như thế nào?
5. Khi A/B cùng sửa body một đoạn, cần UI/OT/CRDT hay policy gì?
6. Nếu A reconnect trước B, server lưu version nào?
7. Khi B reconnect sau 7 ngày, phát hiện concurrent ra sao?
8. Nếu B đang dựa trên context trước khi A đã merge nhánh khác, xử lý gì?
9. Thiết bị reinstall làm actor incarnation thay đổi thế nào?
10. Xóa note offline phải giữ tombstone theo policy nào?
11. Sibling count rất lớn ảnh hưởng UX và storage thế nào?
12. Retry sau commit-success-response-lost phải dùng mutation ID ra sao?
13. Sau user merge, vector mới bao hàm siblings được giải như thế nào?
14. Metric nào chứng minh dữ liệu không bị mất âm thầm?

Phác thảo state machine `CLEAN → CONCURRENT_SIBLINGS → RESOLVING → RESOLVED`. Với mỗi trạng thái hãy ghi rõ data, causal context và quyền thao tác của client.

## 52. Bài tập C — Vector và tồn kho: bài toán khác nhau

Một event chỉ còn **1 vé**, A và B cùng chấp nhận giữ vé khi partition:

~~~text
Initial capacity:
  available=1, vector={A:1,B:0}

A: reserve(R1) -> available=0, vector={A:2,B:0}
B: reserve(R2) -> available=0, vector={A:1,B:1}
~~~

Hãy:

1. Chứng minh hai vectors concurrent.
2. Khi mạng nối lại, chỉ join vectors rồi ghi `available=0` có giải oversell không?
3. Hai reservations cùng thành công cho một vé có vi phạm bất biến không?
4. Nếu LWW bỏ một nhánh, lời hứa đối với khách còn lại được xử lý ra sao?
5. Đề xuất một nguồn giữ chỗ có conditional commit.
6. Đề xuất escrow rights phân trước để hai vùng giữ các phần quota không trùng.
7. Nếu B hết quyền cấp cục bộ nhưng A còn, B phải xử lý thế nào khi partition?
8. Idempotency key của R1/R2 ngăn retry trùng, nhưng có ngăn hai intents khác nhau tranh quota không?
9. Nếu payment đã capture, cần void/refund/reconciliation như thế nào?
10. Vì sao version vector là công cụ **phát hiện lịch sử**, không thay transaction/escrow?

## 53. Câu hỏi tự kiểm tra

1. Happens-before được xác định từ những quan hệ nào?
2. Cập nhật cách nhau năm phút có thể concurrent không?
3. Vector clock khác timestamp vật lý ở trọng tâm nào?
4. `X ≺ Y` có nghĩa gì?
5. Khi nào hai vectors không thể so theo before/after?
6. Vì sao `[2,0]` và `[1,1]` concurrent?
7. Component vắng mặt được diễn giải thế nào?
8. Lamport scalar có thể phát hiện concurrency chính xác chỉ từ số không?
9. Version vector gắn với record mô tả điều gì?
10. Phép join=max có các thuộc tính toán học nào?
11. Join causal context có tự merge payload không?
12. Vì sao hai writers cùng actor có thể cấp trùng counter?
13. Actor epoch/incarnation cần khi nào?
14. Tại sao client cần gửi observed causal context?
15. Context giả có thể khiến hệ bỏ nhánh hợp lệ như thế nào?
16. Siblings là gì và khi nào nên giữ?
17. Một ancestor có thể được bỏ khi nào?
18. Mutation dựa trên snapshot cũ khác replay snapshot cũ ở đâu?
19. Tombstone xóa có cần causal metadata không?
20. Causal stability giúp dọn metadata khi nào?
21. Dotted version vector khác version vector thường ở đâu?
22. Hai updates tới cùng replica nhưng cùng context cũ có thể bị xử lý nhầm thế nào?
23. Version vector with exceptions giúp mô tả gaps nào?
24. CAS và vector clock có thể bổ trợ nhau ra sao?
25. CRDT giải quyết thêm vấn đề gì?
26. Causal consistency khác linearizability ở điểm nào?
27. Vì sao version vector không bảo đảm durable ACK?
28. Dynamo paper và DynamoDB có nên coi là cùng API/conflict policy không?
29. CouchDB `_rev` có phải map actor→counter không?
30. MongoDB integer version CAS có mô tả mọi fork của multi-master không?
31. Hai field có thể merge độc lập trong mọi schema không?
32. Vì sao consumer vẫn cần dedup event ID?
33. Metric nào phát hiện sibling explosion?
34. Kiểm thử nào tìm ra actor-counter collision?
35. Nếu data cần không bao giờ oversell, vector đủ chưa?

## 54. Tổng kết: phát hiện quan hệ trước, giải quyết giá trị sau

**Vector clock/version vector** biểu diễn một phần **lịch sử nhân quả** trong hệ phân tán. So từng actor component cho phép nhận diện:

~~~text
X BEFORE Y:
  Y đã bao hàm lịch sử của X.

X AFTER Y:
  X đã bao hàm lịch sử của Y.

X EQUAL Y:
  Cùng causal summary theo protocol.

X CONCURRENT Y:
  Không bên nào chứng minh bao hàm lịch sử của bên kia.
~~~

Từ kết quả đó, hệ quyết định **giữ siblings, hợp nhất theo miền nghiệp vụ, trả conflict cho người dùng hoặc áp coordination để ngăn fork ngay từ đầu**. Khi merge thành version mới, phải thực sự giải quyết nội dung của các nhánh trước khi tuyên bố new vector đã bao hàm chúng.

Quy trình tư duy:

~~~text
1. Xác định key/aggregate, actors và scope.
2. Quy định causal context được tạo/truyền/xác thực thế nào.
3. Bảo đảm actor counters/dots không trùng.
4. So vector theo component-wise partial order.
5. Phân biệt ancestor, descendant, equal và concurrent.
6. Áp policy merge đúng business semantics khi concurrent.
7. Ghi atomically payload và version/sibling metadata.
8. Anti-entropy phải chịu duplicate, reorder, gaps và retry.
9. Xử lý tombstones, actor churn và metadata compaction.
10. Đo conflicts, siblings, convergence và lost updates.
11. Giữ riêng các bài toán idempotency, transaction và durability.
~~~

Bài học quan trọng nhất: **phát hiện cập nhật đồng thời không đồng nghĩa biết bản nào “đúng” hoặc “mới nhất”**. Vector cho biết hệ thống đã quan sát những lịch sử nào; còn giá trị hợp nhất và bất biến phải đến từ **hợp đồng nghiệp vụ cùng giao thức lưu trữ đúng**. Nắm rõ ranh giới này giúp hệ NoSQL đồng bộ nhiều bản sao mà không âm thầm đánh rơi các cập nhật có ý nghĩa.








