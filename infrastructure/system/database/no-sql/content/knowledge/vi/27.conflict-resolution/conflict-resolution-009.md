# Bộ đếm, tập hợp và những ngữ nghĩa xóa cần lựa chọn rõ trong NoSQL

## 1. Tình huống mở đầu: đồng bộ xong nhưng kết quả lại sai?

Một ứng dụng lưu danh sách bài viết yêu thích trên điện thoại và máy tính bảng. Hai thiết bị có thể hoạt động offline:

```text
                 favorites = {POST-A}
                         |
               NETWORK PARTITION
                   /          \
                  v            v
           Phone (R1)       Tablet (R2)
           remove A         add A
                  |            |
                  +-----+------+
                        |
                      MERGE

              Result = {} or {A} ?
```

Không thể trả lời chỉ bằng câu “hệ hỗ trợ eventual consistency”. Kết quả phụ thuộc vào **ngữ nghĩa xóa** mà sản phẩm lựa chọn:

- **Add-wins:** một lần thêm đồng thời với xóa chưa quan sát được lần thêm đó có thể khiến phần tử vẫn tồn tại.
- **Remove-wins:** xóa đồng thời được ưu tiên, nên phần tử biến mất.
- **Last-write-wins (LWW):** một thứ tự timestamp/phiên bản được dùng để chọn thao tác thắng, có thể trái với trực giác người dùng.
- **Strongly coordinated write:** hai thay đổi phải được sắp thứ tự bởi một authority có quyền quyết định.

Bài toán tương tự xảy ra với **bộ đếm**. Hai replica cùng nhìn thấy `views=100` và mỗi replica tăng một lần. Nếu cả hai ghi đè toàn bộ giá trị thành `101` rồi hệ chọn một bản cuối, kết quả là 101 thay vì 102. Nhưng nếu cứ cộng lại mọi bản sao nhận được sau mỗi lần đồng bộ, một bản tin truyền lặp có thể bị đếm nhiều lần.

Trong chương **Xung đột và đồng bộ**, bộ đếm (*counter*), tập hợp (*set*) và việc xóa là ba trường hợp giúp hiểu vì sao **merge không chỉ là chọn phiên bản mới nhất**, và vì sao một thuật toán hội tụ tốt vẫn có thể **vi phạm bất biến nghiệp vụ** như không bán vượt kho hoặc thu hồi quyền truy cập.

## 2. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt **atomic operation trên một primary** với **merge các update được chấp nhận độc lập tại nhiều replica**.
2. Hiểu G-Counter và PN-Counter, đặc biệt việc merge theo từng actor, vấn đề retry, reset và giá trị âm.
3. Phân biệt G-Set, 2P-Set, OR-Set, add-wins, remove-wins và LWW-Element-Set.
4. Hiểu **causal order**, **concurrent updates**, **dot/tag** và **causal context** khi remove một phần tử.
5. Phân biệt remove logic, tombstone, TTL, clear toàn bộ và xóa vật lý.
6. Biết khi nào cần coordination, conditional update, escrow rights, request ledger hoặc transaction thay vì chỉ dùng CRDT.
7. Đánh giá cách Redis, MongoDB, DynamoDB và Cassandra cung cấp atomic operators/counters/sets mà **không tự đồng nghĩa** CRDT.
8. Thiết kế thực nghiệm chống lost update, duplicate increment, stale delete và zombie data.

## 3. Tách ba câu hỏi trước khi chọn cấu trúc

| Trục thiết kế | Câu hỏi | Ví dụ |
|---|---|---|
| **Thao tác** | Increment, decrement, add, remove, reset hay clear? | Lượt xem, giỏ hàng, favorite |
| **Phạm vi quyền ghi** | Chỉ một leader hay nhiều replica offline cùng ghi? | Một shard chủ, multi-region active-active |
| **Bất biến** | Chỉ cần hội tụ hay phải đúng ngay? | View count có thể lệch tạm; stock không được âm |

Thêm các điều kiện vận hành: có thể **retry** không, message có thể đến **trùng/đảo thứ tự** không, client offline bao lâu, có thể **xóa metadata** không, và kết quả cần visible trên đường đọc nào.

Một database có thể hỗ trợ `INCR` và `SADD` nguyên tử trên một node nhưng không định nghĩa **phép hợp nhất cho hai primary ghi độc lập**. Đừng coi tên lệnh là bằng chứng về CRDT, multi-region convergence hay linearizability.

## 4. Concurrent khác causally after

Trong hệ phân tán, quan hệ **happens-before** thể hiện thao tác A có ảnh hưởng nhân quả đến thao tác B:

\[
A \rightarrow B
\]

Nếu hai thao tác xảy ra mà chưa bên nào nhìn thấy bên kia:

\[
A \parallel B
\]

thì chúng là **concurrent theo quan hệ nhân quả**, không nhất thiết diễn ra đúng cùng mili giây.

**Trường hợp 1 — Remove quan sát add:**

```text
R1: add(X) -> sync -> R2 sees X -> R2: remove(X)
```

Với observed-remove add-wins set, remove có thể xóa X vì nó đã biết lần add cần xóa.

**Trường hợp 2 — Remove và add đồng thời:**

```text
R1: add(X)   (offline)
R2: remove(X) (offline, does not observe R1's add)
```

Add-wins có thể giữ X; remove-wins có thể bỏ X. **Chính sách conflict phải được nêu ngay trong đặc tả sản phẩm.**

Timestamp đồng hồ máy không tự cho biết quan hệ nhân quả: một thiết bị có thể chạy nhanh vài phút so với thiết bị khác.

## 5. Counter kiểu ghi đè và lỗi lost update

Giả sử hai replica có `count=100`:

```text
             R1                      R2
           count=100               count=100
                |                      |
             +1 = 101               +1 = 101
                |                      |
                +-------- MERGE -------+
                         |
                      LWW=101
                  Expected=102
```

Đây là **lost update**: thao tác “tăng thêm 1” bị chuyển thành một lần ghi đè scalar “gán bằng 101”.

### Các cách diễn đạt khác nhau

| Kiểu lưu | Update | Điều cần chú ý |
|---|---|---|
| Scalar + LWW | `count=101` | Một increment concurrent có thể mất |
| Log event | `Increment(eventId)` | Phải dedup event và tính tổng |
| Sharded counter | Increment từng shard | Read tổng cần fan-out/aggregation |
| G-/PN-Counter | Tăng component per actor, merge bằng max | Metadata actor, retry input, reset |
| Conditional update tại authority | `count=count+1` trong một atomic write | Phụ thuộc route/consistency và timeout outcome |

Không có một giải pháp tốt nhất cho mọi trường hợp. Một bộ đếm thống kê khác về độ chính xác, latency và quyền ghi so với số dư tài khoản hoặc số chỗ trống.

## 6. G-Counter: bộ đếm chỉ tăng

G-Counter (*grow-only counter*) phân mỗi actor/replica một thành phần số không âm:

\[
G=[g_A,g_B,g_C]
\]

Giá trị:

\[
\operatorname{value}(G)=\sum_i g_i
\]

Một actor chỉ được tăng component mà nó sở hữu. Ví dụ:

```text
Initial state:
  A=[0,0,0]
  B=[0,0,0]

A increments three times -> [3,0,0]
B increments twice       -> [0,2,0]
```

Merge thực hiện bằng **max từng thành phần**:

\[
(G_1\sqcup G_2)[i]=\max(G_1[i],G_2[i])
\]

```text
[3,0,0] JOIN [0,2,0] = [3,2,0]
value = 5
```

### Vì sao không cộng toàn bộ vector khi merge?

Nếu đã merge một snapshot rồi lại nhận snapshot giống hệt, việc cộng sẽ đếm lặp. Nhưng phép max có:

\[
G\sqcup G=G
\]

nên nhận cùng state bao nhiêu lần cũng không tăng tổng.

### Các giới hạn của G-Counter

- Không thể decrement.
- Reset component về 0 có thể bị state cũ ghi đè khi merge.
- Actor ID phải ổn định và thuộc quyền một writer hợp lệ; không hai writer độc lập cùng tăng chung một component.
- Dữ liệu component có thể phình khi thêm/bớt replicas.
- **Merge idempotent không làm một HTTP increment request idempotent.** Nếu origin xử lý cùng request hai lần, component tăng hai lần.
- Nếu kiểu số overflow, tính đơn điệu của component có thể bị phá.

## 7. PN-Counter: tăng và giảm

PN-Counter gồm hai G-Counter:

- `P` lưu số tăng.
- `N` lưu số giảm theo trị tuyệt đối.

\[
\operatorname{value}(PN)=\sum_i P_i-\sum_i N_i
\]

Ví dụ:

```text
A increases by 5:
  P=[5,0], N=[0,0]

B decreases by 2:
  P=[0,0], N=[0,2]

Merge:
  P=[5,0], N=[0,2]
  value=3
```

Với state-based PN-Counter, cả P và N đều merge bằng max từng thành phần. Các trạng thái G-Counter con **đơn điệu tăng**, dù giá trị PN hiển thị có thể giảm.

### PN-Counter không bảo vệ giới hạn không âm

Stock ban đầu có một sản phẩm:

```text
R1 offline: decrement 1
R2 offline: decrement 1
Merged stock = 1 - 2 = -1
```

CRDT đã hợp nhất đúng hai ý định bán nhưng **sản phẩm bị oversold**. Không được chọn PN-Counter làm nguồn xác nhận tồn kho cuối nếu business rule yêu cầu `stock >= 0` mà chưa thiết kế thêm authority hoặc bounded rights.

### Reset không đơn giản là gán P và N về 0

```text
Old replica: P=[100,0]
Reset replica: P=[0,0]
Merge by max: P=[100,0]
```

State cũ quay lại. Cần **epoch/generation**, namespace mới theo thời gian, protocol reset chuyên biệt hoặc coordination.

## 8. CRDT merge có tính chất gì?

Với state-based CRDT, phép join được thiết kế có các tính chất:

**Giao hoán:**

\[
a\sqcup b=b\sqcup a
\]

**Kết hợp:**

\[
(a\sqcup b)\sqcup c=a\sqcup(b\sqcup c)
\]

**Lũy đẳng:**

\[
a\sqcup a=a
\]

Nhờ vậy, duplicate snapshot, thứ tự trao đổi khác nhau và retry state sync không làm kết quả cuối thay đổi.

Nhưng ba tính chất **không tự bảo đảm**:

- Read linearizable ngay tại mọi replica.
- Không có double increment do request retry tại origin.
- Counter không bao giờ âm.
- Xóa quyền có hiệu lực tức thì ở replica offline.
- Write đã được ghi bền sau crash.
- Có transaction atomic giữa database và external provider.

**Convergence là một phần của correctness**, không phải toàn bộ correctness.

## 9. State-based, op-based và delta-state

| Loại | Dữ liệu truyền | Điều kiện và trade-off |
|---|---|---|
| **State-based** | Trạng thái CRDT, rồi join | Merge lũy đẳng; state có thể lớn |
| **Operation-based** | Các operation như `increment(eventId)` | Phải thỏa điều kiện delivery/ordering/dedup của thiết kế |
| **Delta-state** | Những phần thay đổi có thể join | Tiết kiệm bandwidth, cần causal context/checkpoint phù hợp |

Ví dụ một event:

```json
{
  "eventId": "EV-1001",
  "actorId": "R1",
  "operation": "INCREMENT",
  "quantity": 1
}
```

Nếu consumer nhận cùng event hai lần rồi cộng mù, kết quả sai. Op-based CRDT có thể cần causal delivery hoặc delivery guarantees khác theo từng định nghĩa; đừng tự suy **Kafka offset** hay **HTTP retries** đã đáp ứng chúng.

State-based G-Counter có thể nhận snapshot lặp mà không đếm trùng, nhưng nếu handler ở R1 gọi `increment()` hai lần cho cùng ý định nghiệp vụ, state đã ghi nhận hai increment hợp lệ từ góc nhìn CRDT.

## 10. Java 17: mô hình G-/PN-Counter dễ kiểm tra

Đoạn mã sau chỉ minh họa merge. Actor ID được giả định là **duy nhất, có một writer sở hữu**, không bị tái sử dụng sau restore. Production còn cần persistence, snapshots nguyên tử và giao thức membership.

```java
import java.util.HashMap;
import java.util.Map;

final class GCounter {
    private final Map<String, Long> slots = new HashMap<>();

    public synchronized void increment(String actor, long n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        long old = slots.getOrDefault(actor, 0L);
        slots.put(actor, Math.addExact(old, n));
    }

    public synchronized Map<String, Long> snapshot() {
        return Map.copyOf(slots);
    }

    public synchronized void merge(Map<String, Long> remote) {
        for (var entry : remote.entrySet()) {
            if (entry.getValue() < 0)
                throw new IllegalArgumentException("invalid state");
            slots.merge(entry.getKey(), entry.getValue(), Math::max);
        }
    }

    public synchronized long value() {
        long sum = 0;
        for (long n : slots.values()) sum = Math.addExact(sum, n);
        return sum;
    }
}

final class PNCounter {
    private final GCounter positive = new GCounter();
    private final GCounter negative = new GCounter();

    public void add(String actor, long delta) {
        if (delta >= 0) positive.increment(actor, delta);
        else negative.increment(actor, Math.negateExact(delta));
    }

    public void merge(PNCounter other) {
        positive.merge(other.positive.snapshot());
        negative.merge(other.negative.snapshot());
    }

    public long value() {
        return Math.subtractExact(positive.value(), negative.value());
    }
}

// Minh họa:
// PNCounter a = new PNCounter();
// PNCounter b = new PNCounter();
// a.add("A", 5);
// b.add("B", -2);
// a.merge(b);   // 3
// b.merge(a);   // 3
// a.merge(b);   // vẫn 3
```

**Giới hạn kỹ thuật:** `synchronized` chỉ bảo vệ bộ nhớ trong một JVM; nó không ngăn hai process độc lập dùng chung actor ID. PN state không được snapshot atomically với chỉ hai GCounter riêng như ví dụ nếu có nhiều thread đang chạy; production cần khóa/transaction cho một snapshot hợp lệ. `Math.addExact` phơi bày overflow nhưng không định nghĩa chính sách xử lý. Không có idempotency ledger hay storage durability trong demo.

## 11. Bộ đếm không âm: conditional authority hoặc escrow

Stock ban đầu 10; region A và B offline, mỗi bên bán 8:

```text
Initial stock: 10
Region A: sold 8
Region B: sold 8
PN merge: -6
```

Nếu cần giữ invariant:

\[
stock \ge 0
\]

ta phải thay đổi cách xác nhận bán:

**Cách A — Conditional write tại authority:** chỉ cho phép `decrement(quantity)` khi value hiện tại `>= quantity`, thực thi điều kiện và ghi trong cùng atomic operation/transaction phù hợp.

**Cách B — Escrow/bounded counter:** phân bổ trước quyền bán:

```text
Total stock = 10
Region A rights = 6
Region B rights = 4

A may sell at most 6 while offline.
B may sell at most 4 while offline.
```

Chuyển quyền từ B sang A cần giao thức đảm bảo **một đơn vị quyền không bị tiêu hai lần**. Nếu A hết quyền khi mất mạng nhưng toàn hệ còn stock ở B, A có thể phải từ chối/chờ — đó là đánh đổi availability để giữ bound.

**Không được coi “mỗi region có counter riêng” tự là escrow.** Cần lưu entitlement/transfer/spend một cách có thẩm quyền, có idempotency, recovery và chống rollback sau failover.

## 12. Reset, cửa sổ thời gian và actor membership

Lượt xem mỗi ngày nên thường được model bằng **key theo thời kỳ**:

```text
views:POST-1:2026-11-14
views:POST-1:2026-11-15
```

thay vì reset G-Counter về zero ở một replica. Nhưng phải định nghĩa:

- Ngày theo UTC hay timezone nghiệp vụ?
- Sự kiện đến muộn được tính cho event day hay processing day?
- Nếu đồng hồ client lệch, ai cấp timestamp hợp lệ?
- Tới lúc nào counter cũ được đóng và không nhận event nữa?

### Actor rời cụm

Nếu actor `A` từng đóng góp 1.000, xóa slot A trên một replica chưa đủ: replica khác có `A=1000` có thể đồng bộ lại. Cần một **compaction protocol/base checkpoint/epoch** có bằng chứng rằng state cũ không được áp lại sai.

### Restore snapshot cũ

Một process restore từ disk có sequence counter cũ rồi tự tái sử dụng actor ID có thể làm mất increment mới hoặc tạo nhầm đóng góp trùng. Actor generation và recovery procedure phải bảo vệ tính đơn điệu.

## 13. Tập hợp chỉ thêm: G-Set

Nếu ứng dụng chỉ cần add và không bao giờ remove, dùng G-Set:

\[
S_{merged}=S_1\cup S_2
\]

```text
R1: {A,B}
R2: {A,C}
MERGE: {A,B,C}
```

Union có tính giao hoán, kết hợp và lũy đẳng. Nó phù hợp với một số tập ID từng thấy hoặc dấu mốc chỉ tiến lên.

**Nhưng G-Set không có remove.** Nếu xóa khỏi visible state bằng cách tự `S = S - {A}` rồi merge với replica cũ, union có thể đưa A quay lại.

Không chọn G-Set cho favorites, group membership có thể rời nhóm, giỏ hàng cần xóa item hoặc ACL có thu hồi quyền.

## 14. 2P-Set: xóa một lần, không thể thêm lại

2P-Set (*two-phase set*) lưu:

- `A` — tập mọi phần tử đã add.
- `R` — tập mọi phần tử đã remove.

\[
\operatorname{value}=A\setminus R
\]

```text
add(X):     A = A union {X}
remove(X):  R = R union {X}
merge:      union A and union R
```

Nếu X đã thuộc `R`, add lại X cũng **không làm X trở lại**:

```text
ADD X    -> visible X
REMOVE X -> absent
ADD X    -> still absent
```

2P-Set thích hợp với những ID bị **thu hồi vĩnh viễn** trong phạm vi nghiệp vụ, nhưng không thích hợp cho favorites vì user cần add lại.

Nó cũng **không tự xóa mọi dấu vết vật lý**: metadata `R` có thể phải giữ để ngăn re-add. Nếu chứa dữ liệu cá nhân, phải thiết kế retention/ẩn danh phù hợp.

## 15. OR-Set: mỗi lần thêm có dot/tag riêng

OR-Set (*Observed-Remove Set*) hỗ trợ thêm, xóa và thêm lại nhờ gắn một **tag độc nhất cho từng lần add**.

Ví dụ:

```text
R1 ADD X at dot (R1,1)

adds:
  X -> {R1:1}
removed dots:
  {}

visible:
  {X}
```

Khi R2 đã quan sát `R1:1` và remove X, nó đánh dấu **những dots đã thấy**:

```text
adds X: {R1:1}
removed: {R1:1}
visible: {}
```

### Add concurrent với remove

```text
R1: ADD X with dot R1:2, offline
R2: REMOVE X, only observes R1:1

After merge:
  adds X = {R1:1, R1:2}
  removed = {R1:1}
  X visible because R1:2 survives
```

Đây là **observed-remove add-wins**: remove chỉ xóa các add mà nó đã quan sát; một add concurrent chưa thấy vẫn tồn tại.

### Remove sau khi đồng bộ

Nếu R2 sau đó nhìn thấy `R1:2` rồi remove X:

```text
removed = {R1:1, R1:2}
visible = {}
```

Vì vậy **add-wins không nghĩa remove chẳng bao giờ thắng**. Remove causally-after add có thể loại phần tử.

### Vì sao dot phải độc nhất?

Nếu tag `R1:2` được dùng lại cho một lần add khác sau crash, tombstone cũ xóa `R1:2` có thể xóa nhầm add mới. Actor ID + counter/generation cần được quản lý bền.

## 16. Add-wins, remove-wins, LWW: lựa chọn nghiệp vụ

Giả sử hai bản sao chưa nhìn thấy nhau:

```text
Device A: ADD user U2 to group
Device B: REMOVE user U2 from group
```

| Chính sách | Kết quả sau merge | Tình huống có thể phù hợp |
|---|---|---|
| **Add-wins** | U2 còn | Favorites, thao tác thêm mới được ưu tiên |
| **Remove-wins** | U2 vắng | Tác vụ block/unsubscribe cần ưu tiên xóa |
| **LWW** | Theo timestamp/tie-break | Các cài đặt chấp nhận một quyết định cuối |
| **2P-Set** | U2 vắng vĩnh viễn theo cùng ID | ID bị loại không được tái kích hoạt |
| **Strong authority** | Một thứ tự commit được quyết định | Chỗ ngồi, ACL nghiêm ngặt, quyền sở hữu |

### Remove-wins vẫn có thể cho phép add lại

Một remove-wins CRDT có causal semantics có thể cho phép **add mới sau khi đã quan sát remove** làm phần tử xuất hiện trở lại. Nó chỉ ưu tiên remove khi **concurrent**, không nhất thiết cấm vĩnh viễn như 2P-Set.

### Không hiện thực remove-wins bằng một cờ đơn giản

Một `boolean deleted` không gắn version/causal context có thể bị ghi đè bởi update cũ. Cần CRDT remove-wins có protocol phù hợp, hoặc authority/epoch để phân xử.

### Quy tắc đặc tả

Trước khi chọn thư viện, hãy điền:

> Khi một người thêm X trên replica A và người khác xóa X trên replica B **mà hai bên chưa nhìn thấy nhau**, hệ thống phải trả kết quả ______, bởi vì ______.

Nếu nhóm sản phẩm chưa thống nhất kết quả, database không thể đoán thay.

## 17. LWW-Element-Set và nguy cơ clock skew

Một LWW-Element-Set có thể lưu timestamp/version của add/remove:

```text
ADD X at timestamp 100
REMOVE X at timestamp 101
=> absent
```

Nhưng wall-clock từ hai máy có thể sai lệch:

```text
Replica A clock 2 minutes fast:
  ADD X at logical real time 12:00, timestamp 12:02

Replica B later:
  REMOVE X at real time 12:00:30, timestamp 12:00:30

LWW by timestamp -> ADD wins
```

Điều này có thể trái với ý định “remove xảy ra sau”. HLC hoặc Lamport timestamps giúp mô tả ordering trong một số giao thức, nhưng **không tự mang bảo đảm linearizability hoặc ý định nghiệp vụ**. Phải định nghĩa tie-breaker và quyết định có cho phép đồng hồ client tham gia ordering không.

LWW là một quy tắc **chọn một trong các thay đổi**, không giữ cả hai ý định cộng dồn như PN-Counter.

## 18. OR-Set và removed dots: ví dụ Java 17

Đây là ví dụ **đơn luồng** để hiểu add-wins. Không dùng nguyên xi trong production: chưa có durable storage, chuẩn hóa serialization, causal GC, membership, thread safety hoặc quyền cấp dot.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

record Dot(String actor, long sequence) {}

final class AddWinsORSet {
    private final Map<String, Set<Dot>> additions = new HashMap<>();
    private final Set<Dot> removals = new HashSet<>();

    void add(String item, Dot dot) {
        additions.computeIfAbsent(item, k -> new HashSet<>()).add(dot);
    }

    // Chỉ remove các add dots đã quan sát tại replica này.
    void removeObserved(String item) {
        removals.addAll(additions.getOrDefault(item, Set.of()));
    }

    void merge(AddWinsORSet other) {
        for (var entry : other.additions.entrySet()) {
            additions.computeIfAbsent(
                entry.getKey(), k -> new HashSet<>()
            ).addAll(entry.getValue());
        }
        removals.addAll(other.removals);
    }

    boolean contains(String item) {
        for (Dot dot : additions.getOrDefault(item, Set.of())) {
            if (!removals.contains(dot)) return true;
        }
        return false;
    }

    Set<String> visible() {
        Set<String> result = new HashSet<>();
        for (String item : additions.keySet())
            if (contains(item)) result.add(item);
        return result;
    }
}

// Thought experiment:
// A and B both observed ADD X tagged A:1.
// A removes observed dot A:1.
// B concurrently adds X tagged B:2.
// Merge A with B -> X remains because B:2 survives.
```

### Vì sao không merge riêng tập visible?

Hai bản sao cùng hiển thị `{X}` có thể giữ **những dots khác nhau**. Nếu bỏ metadata tags và chỉ merge phần tử đang hiển thị, hệ không biết một remove đã nhìn thấy những lần add nào. Điều này có thể gây **hồi sinh phần tử** hoặc xóa cả add mới không liên quan.

### Khi nào cần tối ưu?

Với một item được add/remove hàng triệu lần, số tag/tombstone có thể tăng. Một implementation CRDT thực tế có thể dùng **dotted version vectors, causal context, compaction** hoặc mô hình khác để giảm kích thước, nhưng chỉ dọn metadata khi protocol xác nhận an toàn.

## 19. Causal context, version vector và thứ tự quan sát

Một vector theo actor:

```text
Replica A context: {A:5, B:2}
Replica B context: {A:4, B:3}
```

Hai bên không bao trùm context của nhau: A thấy bản cập nhật A:5, B thấy B:3. Chúng có thể giữ những thay đổi **concurrent**.

Một dot `(actorId, localSequence)` định danh một operation cụ thể. Dữ liệu remove có thể tham chiếu những dots đã quan sát, hoặc biểu diễn tối ưu bằng causal context.

### Vector clock không tự giải quyết conflict

Vector giúp nói “đã thấy” hay “chưa thấy”. Nó **không chọn** add-wins, remove-wins hoặc LWW thay nghiệp vụ.

### Vấn đề membership và restore

- Actor IDs có thể tồn tại lâu hơn process/máy.
- Replica offline nhiều ngày giữ context cũ.
- Restore snapshot có thể làm sequence quay lùi nếu không có epoch.
- Metadata context có thể phình theo số actors.
- Causal stability chỉ đạt khi đủ bằng chứng các peer quan trọng đã quan sát thay đổi.

Không tự dọn dots/tombstones chỉ vì một timestamp đã đủ cũ.

## 20. “Xóa” có thể là năm hành vi khác nhau

| Cách xóa | Nghĩa | Rủi ro khi đồng bộ |
|---|---|---|
| Remove visible membership | Loại X khỏi tập đang hiển thị | Replica cũ có thể thêm X lại |
| Observed-remove | Loại những add tags đã thấy | Add concurrent có thể còn |
| Remove-wins | Xóa concurrent được ưu tiên | Add concurrent có thể bị bỏ |
| LWW tombstone | Chọn delete theo version/time | Clock/order và replay cũ |
| Strong business delete/revoke | Authority quyết định xóa và điều kiện tiếp tục ghi | Có thể phải từ chối offline writes |

Một lệnh `DELETE` không nói cho bạn biết **nó đã xóa những lần add nào, có cấm add lại không, và có bảo vệ khỏi replica offline không**.

### Remove phần tử vs xóa toàn bộ container

`remove(X)` trong OR-Set có scope một phần tử. `clearAll()` của favorites hoặc `deleteCart()` còn liên quan đến **những phần tử đang được thêm offline**. Phải thiết kế một epoch/generation hoặc chính sách clear observed phù hợp.

## 21. Clear toàn bộ: observed clear hay global reset?

Thiết bị A có:

```text
Favorites observed: {POST-1, POST-2}
```

Khi offline, A bấm “Xóa tất cả”; thiết bị B đồng thời add `POST-3`.

**Observed clear:** A chỉ xóa những tags nó đã quan sát. Sau merge, `POST-3` còn tồn tại.

**Global authoritative clear:** Business rule có thể yêu cầu mọi write thuộc thế hệ cũ bị vô hiệu hóa. Cần:

```text
favorites generation = 12
clear -> authoritative generation = 13
old offline write carrying generation 12 -> reject/fence
```

Nếu offline replica vẫn được phép ACK write vào generation 12 rồi hệ tự coi nó hợp lệ sau khi server đã tăng generation 13, invariant global clear bị phá.

**Reset không miễn phí trong hệ cho phép write offline không giới hạn**. Cần chính sách rejoin/conflict và đôi khi phải từ chối một thay đổi cũ.

## 22. Tombstone: bằng chứng xóa ngăn dữ liệu hồi sinh

Một bản sao B offline giữ record X. A và C xóa X. Nếu A/C chỉ xóa vật lý rồi merge B theo union:

```text
Before: A={X}, B={X}, C={X}
B offline
A removes X, C learns deletion
A,C erase all delete metadata
B reconnects with X
Merge may resurrect X
```

**Tombstone** là dấu hiệu rằng một phiên bản hoặc lần add đã bị xóa:

```json
{
  "_id": "POST-1",
  "sourceVersion": 18,
  "deleted": true,
  "deleteOperationId": "DEL-18"
}
```

Trong OR-Set, tombstone có thể là removed dots, không nhất thiết cờ `deleted=true` của document.

### Không đánh đồng các trạng thái

- **Không có key:** có thể chưa từng có, chưa sao chép xong hoặc đã bị xóa.
- **Giá trị null:** giá trị dữ liệu theo schema, không nhất thiết là delete.
- **Tombstone:** bằng chứng một phiên bản/lần add đã bị loại.
- **TTL/expiry:** điều kiện hết hạn, cần hiểu cơ chế apply và đồng bộ.
- **Xóa vật lý:** dọn byte khỏi storage/backup theo quy trình riêng.

### Zombie data

Nếu tombstone bị dọn trước khi replica cũ nhận biết xóa, record cũ có thể quay lại. Đây là loại rủi ro thường được gọi là **resurrection/zombie data**.

## 23. Dọn tombstone, causal stability và replica offline

Giả sử:

```text
Day 1: X deleted at version 18.
Day 2: Tombstone removed at A and C.
Day 20: Offline replica B returns with X at version 17.
```

Nếu không còn metadata chặn version 17, X có thể hồi sinh.

### Khi nào có thể dọn?

Cần bằng chứng phù hợp với protocol:

- Những replica còn được phép đồng bộ đã biết deletion.
- Replica offline quá lâu phải **full resync** hoặc rejoin bằng epoch mới, không gửi state cũ như authority.
- Snapshot/log retention được quản lý.
- Backup restore không tự nhập lại dữ liệu vào thế hệ mới.
- Không còn event cũ được nhận như update có quyền trong cùng namespace.

Đây là ý tưởng **causal stability** hoặc safe garbage collection, cụ thể phụ thuộc implementation.

### “TTL tombstone = 7 ngày” là một policy, không phải chứng minh

Nếu cho phép peer offline 30 ngày tự reconnect với data cũ nhưng chỉ giữ tombstone 7 ngày, protocol cần một cơ chế khác để ngăn resurrection. Nếu không có, lịch dọn metadata có thể sai.

Với Cassandra hoặc hệ LSM có tombstone, phải hiểu **grace period, repair, topology và replication** đúng phiên bản. Không sao chép ngưỡng giữ tombstone từ hệ khác một cách máy móc.

## 24. TTL và xóa theo thời gian

Một token có TTL 24 giờ:

```text
R1: expires token T at 10:00
R2: offline with old token T
R2 reconnects at 11:00
```

Nếu expiry chỉ là local physical erase, R2 có thể tái truyền T. Nếu expiry được biểu diễn bằng versioned delete/tombstone hoặc authority kiểm tra `expiresAt`, kết quả có thể được kiểm soát tốt hơn.

### Relative TTL khác absolute expiry

| Kiểu | Ví dụ | Đánh đổi |
|---|---|---|
| Relative TTL | Hết hạn 24 giờ sau mỗi write | Replay/copy có thể vô ý kéo dài |
| Absolute expiry | `expiresAt=2026-11-15T10:00Z` | Cần clock/skew policy |
| Server authority | Một nơi quyết định đã hết hạn | Phụ thuộc kết nối/quorum |
| Lease + fencing | Hết quyền, worker cũ bị từ chối | Cần enforce ở nơi tạo effect |

**TTL xóa dữ liệu không tự ngăn request idempotency đã hết TTL được replay**. Retention của ledger/tombstone phải phù hợp với hàng đợi, backup, replay và thời gian tối đa client offline.

### Xóa dữ liệu riêng tư

Hội tụ logic `deleted=true` không chứng minh toàn bộ byte đã bị xóa khỏi backups, logs, snapshots hoặc thiết bị offline. Cần chính sách retention/quyền truy cập/khôi phục dữ liệu riêng biệt, không giao toàn bộ nhiệm vụ privacy cho CRDT.

## 25. OR-Map và giỏ hàng: một map không đơn thuần là một set

Một cart có thể lưu:

```json
{
  "cartId": "CART-101",
  "items": {
    "SKU-A": {"quantity": 2},
    "SKU-B": {"quantity": 1}
  }
}
```

Một thiết kế eventual có thể kết hợp:

- **OR-Map** cho membership của item keys.
- **PN-Counter** cho số lượng khi cho phép tăng/giảm offline.
- **Versioned register** cho thuộc tính một item.
- **Generation/tombstone** khi xóa item hoặc cả cart.

### Race xóa item và tăng quantity

```text
Replica A: REMOVE SKU-A
Replica B: quantity(SKU-A) += 2 concurrently
```

Có các lựa chọn:

1. Add-wins: item có thể trở lại vì update/reattach concurrent.
2. Remove-wins: item bị loại, bỏ thay đổi quantity concurrent.
3. Authority: hai thao tác được sắp thứ tự theo version/transaction.

Đừng mặc định “set quantity=0” giống “xóa membership”; hai ý định có thể có semantics khác.

### Checkout vẫn cần xác minh

Giỏ hàng offline eventual có thể hữu ích cho UX; **giá, khuyến mãi, tồn kho và quyền mua** cần được xác nhận tại authority khi checkout. Một PN-Counter trên cart không bảo vệ SKU stock toàn hệ.

## 26. Xóa quyền truy cập: remove-wins eventual vẫn có thể chưa đủ

Một admin thu hồi quyền đọc hồ sơ tại region A. Region B đang offline vẫn giữ ACL cũ và nhận request:

```text
T0: U has READ.
T1: Admin revokes READ on A.
T2: B has not received revoke.
T3: U accesses private document through B.
```

Ngay cả khi CRDT chọn **remove-wins sau merge**, request tại T3 có thể bị B cho phép trước khi hội tụ.

Phải phân biệt:

- **Conflict resolution:** sau khi biết cả hai updates, chọn state nào?
- **Authorization guarantee:** một request đọc mới có phải thấy revoke đã commit hay không?

Nếu cần thu hồi quyền tức thời theo hợp đồng, có thể cần **authoritative ACL check, permission epoch, revocable session/token hoặc fail-closed khi không có nguồn xác minh**. Không lấy một eventual cache làm nơi quyết định cuối của dữ liệu nhạy cảm.

### Product policy

Đối với favorites, add-wins có thể chấp nhận. Đối với blacklist, remove-wins có thể hợp lý. Đối với phân quyền tài chính, **chỉ lựa chọn một CRDT set không đủ** nếu ràng buộc bảo mật yêu cầu mạnh hơn.

## 27. Xóa document khác xóa reference khỏi set

Giả sử favorites chứa ID tài liệu:

```text
Favorites OR-Set: {POST-1}
Documents source: POST-1 deleted at version 18
```

Một reference còn trong favorites không được phép tự tạo lại document đã xóa. Có thể cần hai lớp metadata:

1. **Membership tombstone** cho favorite add/remove tags.
2. **Document tombstone/authority version** cho nội dung POST-1.

Nếu consumer xử lý `favoriteAdded(POST-1)` đến muộn, nó không được dùng event đó để hồi sinh nội dung document.

Một thao tác **delete rồi re-create** cùng ID còn cần generation/incarnation mới để những update của đời cũ không nhập nhầm vào document mới.

```text
Document POST-1 generation 4 -> deleted
Document POST-1 generation 5 -> recreated
Delayed update generation 4 -> reject/ignore under policy
```

## 28. Retry xóa: “idempotent khi đứng một mình” chưa đủ

Một lệnh xóa có thể lặp lại cùng kết quả khi không có writer khác:

```text
DELETE X
DELETE X again
=> X absent
```

Nhưng khi có add xen vào:

```text
T0: Client A sends REMOVE X.
T1: REMOVE succeeds, response lost.
T2: Client B adds X again.
T3: Client A retries REMOVE X.
T4: X absent (B's new add erased).
```

Nếu ý định A chỉ là loại **lần add cũ**, retry ở T3 đã tác động lên một add mới. Đó là lý do OR-Set remove **tham chiếu observed dots**, còn thiết kế versioned authority có thể yêu cầu `expectedVersion`/`operationId`.

Một event delete cũ với version 5 không nên xóa object đã được tạo hợp lệ ở version 6/generation mới.

### Idempotency cho operation

Truyền cùng `requestId` trên mọi attempt và lưu kết quả/điều kiện đã áp ở authority. Nếu queue replay một event, consumer có thể dựa vào `eventId` hoặc conditional version để không tạo effect mới ngoài ý định ban đầu.

## 29. MongoDB: atomic operators không tự là OR-Set

MongoDB hỗ trợ cập nhật một document:

```javascript
db.posts.updateOne(
  { _id: "POST-1" },
  { $inc: { viewCount: 1 } }
);

db.users.updateOne(
  { _id: "U1" },
  { $addToSet: { favorites: "POST-1" } }
);

db.users.updateOne(
  { _id: "U1" },
  { $pull: { favorites: "POST-1" } }
);
```

Trên authoritative write path, các operators giúp tránh những race ghi đè nguyên document trong phạm vi atomicity của MongoDB.

Nhưng:

- `$inc` retry hai lần có thể tăng hai lần.
- `$addToSet` không tự lưu **dot/causal context** của OR-Set.
- `$pull` không tự định nghĩa add-wins hay remove-wins giữa hai primary độc lập mà ứng dụng tự tạo.
- Secondary read có thể chậm hơn source tùy read concern/session.
- Quorum/write concern cần phân biệt ACK với mọi replica đã apply.

### Tồn kho có điều kiện

```javascript
const qty = 2;
const result = db.inventory.updateOne(
  { _id: "SKU-A", available: { $gte: qty } },
  { $inc: { available: -qty } }
);

if (result.modifiedCount === 0) {
  // Không có item hoặc không đủ available theo điều kiện.
}
```

Atomic condition giúp bảo vệ stock trên một document, **nhưng nếu response mất**, retry request trừ stock phải dùng operation ledger/idempotency hoặc transaction phù hợp để không trừ lại.

## 30. Redis: `INCR` và `SADD/SREM` khác merge CRDT

Ví dụ:

```redis
INCR views:POST-1
SADD favorites:U1 POST-1
SREM favorites:U1 POST-1
SMEMBERS favorites:U1
```

Redis thực thi những lệnh đơn theo atomicity của key/server; **không vì thế chúng trở thành PN-Counter/OR-Set cho multi-writer offline merge**.

| Thao tác | Retry sau response mất |
|---|---|
| `INCR key` | Có thể tăng hai lần |
| `SADD set X` | Không thêm bản sao thứ hai của X trong cùng set nếu không xen thao tác khác |
| `SREM set X` | Có thể xóa một add mới nếu retry muộn |
| `DEL key` | Có thể xóa một giá trị vừa được re-create |

### Failover và persistence

Redis replication có thể bất đồng bộ; primary ACK trước khi replica bắt kịp. Vì vậy phải xét persistence, replication/failover semantics và idempotency; không xem “INCR nguyên tử” như bảo đảm write đã bền trên mọi node.

### Redis cache và deleted flags

Một cache xóa key chưa chắc đã xóa dữ liệu nguồn; một replica cache còn stale có thể phục vụ giá trị cũ. Khi xóa dữ liệu nhạy cảm hoặc quyền, cache invalidation và authoritative check cần chính sách riêng.

## 31. DynamoDB: atomic counter, set updates và Global Tables

DynamoDB hỗ trợ `UpdateItem` với update expressions như cộng số và cập nhật sets; ví dụ diễn giải:

```text
SET viewCount = if_not_exists(viewCount, 0) + :one
ADD tags :newStringSet
DELETE tags :removedStringSet
```

Syntax/type/condition expression phải theo SDK/API thật.

- Một conditional update trên item có thể bảo vệ trạng thái trong phạm vi API.
- Nếu response mất, retry `+1` có thể cộng lại; cần idempotency.
- GSI là chỉ mục thứ cấp có read semantics riêng, không tự là authority xác nhận một write đã/ chưa commit.
- `ADD/DELETE` đối với set attributes **không tự mang causal dots** của một OR-Set.
- Multi-region conflict behavior phụ thuộc Global Tables consistency mode và phiên bản/tính năng; không giả định mọi chế độ có cùng add-wins/remove-wins semantics.

### Request ledger

Một key `(tenantId,eventId)` được tạo có điều kiện có thể đánh dấu event đã xử lý. Nhưng nếu việc ghi ledger và tăng count là **hai thao tác không atomic**, crash giữa chúng vẫn tạo gap hoặc duplicate. Cần một transaction được API hỗ trợ, hoặc dùng event log/aggregator với replay và dedup được thiết kế đúng.

## 32. Cassandra/ScyllaDB: counter, collection set và tombstone

Cassandra có CQL counter và collections:

```sql
CREATE TABLE page_counts (
    page_id text PRIMARY KEY,
    views counter
);

UPDATE page_counts
SET views = views + 1
WHERE page_id = 'POST-1';
```

Counter trong CQL có restrictions và retry semantics đặc thù, tùy phiên bản/triển khai. Một timeout không chứng minh increment chưa tới replicas; retry có thể làm tổng không đúng theo **một logical operation**.

Ví dụ set:

```sql
CREATE TABLE profiles (
    user_id text PRIMARY KEY,
    tags set<text>
);

UPDATE profiles SET tags = tags + {'java'}
WHERE user_id = 'U1';

UPDATE profiles SET tags = tags - {'java'}
WHERE user_id = 'U1';
```

CQL set update không tự là một OR-Set add-wins theo mô hình toán học. Khi có concurrent mutations, timestamp/consistency/repair/tombstone semantics của engine là điều cần đọc thật.

### Zombie data khi dọn tombstone

Một replica offline có thể giữ dữ liệu cũ; tombstone dọn quá sớm trước khi repair và replica rejoin an toàn có thể khiến dữ liệu cũ quay lại. Khi vận hành cần xét **tombstone grace period, repair, compaction, replica downtime và phiên bản**; không lấy một TTL tùy ý thay protocol.

### Count và quota

Counter phục vụ thống kê có thể hợp lý. Nếu cần đảm bảo không bán vượt hàng, không nên chỉ đọc một counter eventual rồi quyết định mà không có conditional authority/escrow.

## 33. Multi-region: hội tụ nhưng không tự đúng mọi lúc

Để các bản sao eventually converge:

1. Update được biểu diễn bằng đúng cấu trúc hoặc operation semantics.
2. Đồng bộ cuối cùng truyền đủ dữ liệu/causal context cần thiết.
3. Snapshot, redo log và tombstone không bị bỏ sớm.
4. Actor IDs/epoch vẫn hợp lệ sau crash/membership change.
5. Merge đúng phép join/ordering contract.

**Eventual** không hứa mọi read nhìn thấy trạng thái mới trong 100 ms; nếu ứng dụng cần read-your-writes, monotonic reads hoặc bounded staleness, phải thêm routing/session/version checks thích hợp.

### Rủi ro double ACK nghiệp vụ

Nếu hai vùng offline cùng xác nhận một ghế duy nhất cho hai người, không thể dùng việc merge cuối cùng chọn một bản để làm hai lời hứa “đã giữ chỗ thành công” đều đúng. Cần một authority hoặc escrow/rights model phù hợp với invariant.

### Không chọn remove-wins chỉ vì nghe “an toàn”

Nếu user thích một bài trên thiết bị A và vô tình xóa từ thiết bị B concurrent, remove-wins có thể làm mất ý định thích mới. Ngược lại nếu admin thu hồi quyền, add-wins có thể gây rủi ro. **Định nghĩa nghiệp vụ quan trọng hơn tên thuật toán.**

## 34. Chọn chính sách theo từng trường hợp

| Tình huống | Hướng bắt đầu | Bất biến/cạm bẫy |
|---|---|---|
| Tổng lượt xem nhiều vùng | G/PN counter hoặc event ledger | Duplicate request, reset, window |
| Lượt xem unique user | Set/sketch + dedup | Không thể chỉ increment mỗi request |
| Favorites offline | OR-Set add-wins tùy UX | Concurrent remove có thể không thắng |
| Danh sách chặn | Remove-wins hoặc authority | Thu hồi quyền trước hội tụ |
| Giỏ hàng | OR-Map + quantity policy | Remove item vs concurrent increment |
| Tồn kho | Conditional update/escrow | Không được âm |
| Voucher dùng một lần | Unique claim + idempotency | Hai vùng không cùng claim |
| Quyền truy cập | Strong authoritative ACL khi cần | Stale replica có thể còn ALLOW |
| Tags tài liệu | OR-Set/LWW theo yêu cầu | Re-add sau delete |
| Xóa tài khoản | Delete workflow + tombstones + retention | Backups/offline restore |
| Số lượt sử dụng coupon | Escrow/quota authority | Dù counter hội tụ vẫn có thể vượt quota |

### Ví dụ policy document

```yaml
resource: favorites
scope: tenantId + userId
offlineWritesAllowed: true
mergePolicy: observed-remove-add-wins
removeSemantics: remove-observed-add-tags
reAddAllowed: true
deleteWholeList:
  semantics: authoritative-generation-bump
rejoin:
  staleGeneration: require-resync
readConsistency: eventual-with-session-version-when-needed
```

Đây chỉ là một **hợp đồng minh họa**, không phải cấu hình của thư viện CRDT cụ thể. Những mục bắt buộc có implementation bảo vệ được; ghi YAML không tự tạo bảo đảm.

## 35. Giám sát metadata và hội tụ

| Metric gợi ý | Cần theo dõi |
|---|---|
| `crdt_merge_backlog` | Replica còn chờ đồng bộ bao nhiêu |
| `counter_component_count` | Số component/actor |
| `counter_value_disagreement` | Chênh lệch theo phạm vi đọc |
| `increment_dedup_count` | Bao nhiêu replay được chặn |
| `orset_add_tag_count` | Metadata add còn giữ |
| `orset_removed_tag_count` | Tombstone/removed tags |
| `causal_context_bytes` | Độ lớn vector/context |
| `stale_delete_rejected_count` | Version/generation cũ bị chặn |
| `resurrected_record_detected_count` | Dữ liệu đã xóa quay lại |
| `gc_waiting_for_offline_replica` | Chưa đủ an toàn để dọn |
| `escrow_rights_exhausted_count` | Không thể đáp ứng offline vì hết quyền |
| `read_staleness_seconds` | Độ trễ đo đúng theo đường đọc |

Tên trên là ví dụ instrumentation, **không phải metric mặc định của mọi database**.

Không đưa email, userId hoặc raw keys có cardinality lớn vào labels; dùng service, region, replica group, data type, operation class và log IDs có phân quyền.

### Đừng chỉ đo “trạng thái cuối bằng nhau”

Hai replica cuối cùng bằng nhau không chứng minh hệ đã trả kết quả đúng ở mọi thời điểm. Nếu API đã trả quyền đọc nhạy cảm sai trong partition, convergence sau đó không xóa sự cố.

## 36. Fault injection trong lab

Chỉ chạy với dữ liệu giả và môi trường được phép.

### Test A — Increment offline

```text
A starts [0,0]; B starts [0,0]
A +3; B +2
Merge B -> A, A -> B, B -> A again
Expected final value: 5
```

Sau đó retry **một logical increment** tại A với cùng requestId. Nếu không có input dedup, count thành 6. Tách rõ lỗi request replay khỏi phép join đúng.

### Test B — Decrement vượt stock

Stock=1, hai replica offline cùng decrement 1. Merge PN-Counter và quan sát -1; thiết kế escrow/conditional authority để chặn oversell.

### Test C — Add-wins OR-Set

Ban đầu X có tag `A:1`. R1 remove observed `A:1`, R2 concurrent add X tag `B:2`. Merge theo cả hai thứ tự; X còn.

### Test D — Remove causally after

R1 đồng bộ và thấy `B:2`, rồi removeObserved X. Merge lại; X vắng. Giải thích vì sao không mâu thuẫn với add-wins.

### Test E — Tombstone GC

Một replica offline giữ version cũ; những replica còn lại xóa và dọn tombstone quá sớm trong lab. Kiểm tra nguy cơ resurrection, sau đó áp rejoin/full resync policy.

### Test F — Reset

Một replica có component A=100, replica khác reset về 0, rồi merge. Quan sát state cũ trở lại; thử epoch mới có fencing.

### Test G — LWW clock skew

Tạo hai thiết bị có timestamp lệch và add/remove concurrent. So kết quả LWW với add-wins và remove-wins; nêu behavior product kỳ vọng.

### Test H — Business invariant

Mô phỏng hai regions nhận giữ một ghế khi mất mạng. Cho cả hai ACK rồi merge; giải thích vì sao chọn một người thắng sau đó không làm hai ACK ban đầu hợp lệ.

## 37. Những hiểu nhầm cần tránh

| Ngộ nhận | Điều đúng |
|---|---|
| “Đồng bộ bộ đếm bằng cộng hai tổng” | Duplicate state có thể đếm lặp |
| “LWW giữ mọi increment” | Có thể làm mất update |
| “G-Counter hỗ trợ giảm” | Chỉ tăng; PN-Counter tách tăng/giảm |
| “PN-Counter luôn không âm” | Có thể giảm vượt bound khi offline |
| “Reset về zero rồi merge là được” | State cũ có thể quay lại |
| “Merge lũy đẳng nghĩa API increment lũy đẳng” | Retry ở origin vẫn tăng thêm |
| “Set chỉ cần union giá trị visible” | Xóa có thể bị hồi sinh |
| “2P-Set hỗ trợ add lại sau remove” | Không hỗ trợ cùng element ID |
| “Add-wins nghĩa remove không bao giờ thắng” | Remove đã thấy add có thể xóa |
| “Remove-wins nghĩa cấm add lại vĩnh viễn” | Add sau khi thấy remove có thể hợp lệ |
| “Timestamp mới hơn luôn là ý định mới hơn” | Clock skew và causal order |
| “DELETE ở một replica là toàn hệ đã xóa” | Peer offline có thể còn dữ liệu cũ |
| “Tombstone hết TTL chắc chắn an toàn” | Rejoin/replay có thể resurrect |
| “OR-Set là Redis SADD/SREM” | Không cùng causal metadata |
| “MongoDB $addToSet tự giải quyết conflict hai primary” | Là atomic operator, không phải OR-Set protocol |
| “DynamoDB ADD tự thành counter CRDT mọi region” | Phải xem consistency/conflict mode |
| “Cassandra counter retry không bao giờ đếm hai lần” | Timeout và retry cần idempotency |
| “Remove-wins CRDT bảo vệ revoke ngay khi offline” | Chưa đồng bộ vẫn có thể serve ALLOW |
| “Xóa logic đồng nghĩa xóa mọi bản sao vật lý” | Backup/log/cache có vòng đời riêng |
| “Merge đã hội tụ chứng minh mọi ACK đúng” | Convergence không tự bảo vệ business invariant |

## 38. Bài tập thực hành

### Bài 1 — Lost update

Count=100. A và B cùng tăng và ghi 101. LWW cho kết quả gì, và vì sao sai nếu cả hai increment là hai ý định độc lập?

### Bài 2 — G-Counter

Cho `G1=[4,0,1]` và `G2=[3,5,0]`. Tính join bằng max từng component, tổng cuối và kết quả nếu nhận lại G2 hai lần.

### Bài 3 — Idempotency

Một G-Counter merge đúng nhưng client gọi increment hai lần do timeout. Vì sao kết quả vẫn tăng hai? Đề xuất requestId/ledger.

### Bài 4 — PN-Counter

A tăng 7 và giảm 2; B tăng 4 và giảm 6 trong mạng phân hoạch. Tính giá trị sau merge. Nếu là inventory, cần invariant gì?

### Bài 5 — Reset

Replica A có component 120, replica B set zero, rồi merge. Giải thích kết quả và giải pháp generation/day namespace.

### Bài 6 — Escrow

Stock=15, A có 9 quyền, B có 6. A dùng hết 9, B mới dùng 2; A offline muốn bán thêm một. A được ACK không? Thiết kế chuyển quyền.

### Bài 7 — G-Set vs 2P-Set

X được add, remove, rồi add lại. So kết quả, và giải thích kiểu nào phù hợp cho favorites.

### Bài 8 — OR-Set concurrent

Ban đầu X có dot A:1. R1 xóa observed A:1, R2 add X với B:2 concurrent. Sau merge còn X không? Vì sao?

### Bài 9 — Causal remove

R1 đã nhìn thấy dot B:2 của bài 8, rồi removeObserved X. Kết quả sau merge thế nào?

### Bài 10 — Conflict policy

So sánh add-wins/remove-wins/strong authority cho favorites, blacklist và ACL nhạy cảm. Nêu invariant.

### Bài 11 — Clock skew

Device A add X với clock chạy nhanh 2 phút, device B remove X sau đó theo thời gian thực nhưng timestamp nhỏ hơn. LWW chọn gì?

### Bài 12 — Clear all

A clear favorites khi chỉ thấy POST-1/POST-2; B concurrent add POST-3. Observed clear có xóa POST-3 không? Nếu cần xóa mọi update thế hệ cũ, thiết kế gì?

### Bài 13 — Tombstone

B offline 30 ngày. A/C dọn tombstone sau 7 ngày rồi B rejoin với dữ liệu cũ. Điều gì xảy ra? Cần resync/causal stability ra sao?

### Bài 14 — TTL

Một token hết hạn ở A nhưng B vẫn còn khi offline. Phân biệt physical erase, versioned expiry và authoritative check.

### Bài 15 — MongoDB

So `$inc`, `$addToSet`, `$pull` với G-/PN-Counter và OR-Set. Những lệnh đó đảm bảo điều gì và không đảm bảo điều gì?

### Bài 16 — Redis

`SREM X` thành công nhưng ACK mất, sau đó user khác `SADD X`, rồi client cũ retry `SREM X`. Vì sao X biến mất? Dùng operationId/dot/version thế nào?

### Bài 17 — DynamoDB và Cassandra

Một counter update timeout. Phân tích lý do không được suy “timeout = chưa tăng”, và giải pháp request ledger/conditional transaction/aggregator.

### Bài 18 — Giỏ hàng

A remove SKU-A, B concurrent tăng quantity SKU-A +2. Nêu kết quả theo add-wins/remove-wins/strong policy; tại checkout cần xác minh gì?

### Bài 19 — Privacy

User yêu cầu xóa tài khoản hoàn toàn. Liệt kê nhiệm vụ ngoài tombstone logic: backup, cache, indexes, event replay, thiết bị offline, audit retention.

### Bài 20 — Kế hoạch kiểm thử

Thiết kế lab 3 replica, counter và OR-Set, mô phỏng partition, duplicate sync, retry request, stale delete, reset, GC và crash/rejoin. Ghi expected invariants, metric và giới hạn kết luận.

## 39. Checklist thiết kế

1. **Định nghĩa thao tác:** tăng/giảm, add/remove, clear/reset hay xóa document?
2. **Định nghĩa bất biến:** eventual count có được lệch? stock có được âm? revoke phải hiệu lực ngay không?
3. **Chọn phạm vi ghi:** một authority hay nhiều replica offline?
4. **Mô tả concurrency:** add và remove không nhìn nhau thì ai thắng?
5. **Chọn representation:** G-/PN-Counter, G-/2P-/OR-/remove-wins set, LWW hoặc transaction/escrow.
6. **Chọn retry policy:** cùng logical operation có requestId và cách dedup không?
7. **Chọn causal metadata:** actor ID, dot, vector, generation và version được tạo ra ở đâu?
8. **Định nghĩa xóa:** remove observed, remove concurrent, tombstone, TTL hay xóa vật lý?
9. **Thiết kế GC/rejoin:** replica offline bao lâu vẫn được sync incremental?
10. **Bảo vệ quyền:** có read path authoritative và policy fail-closed khi cần không?
11. **Kiểm tra engine:** lệnh atomic có thực sự cung cấp merge semantics mong muốn không?
12. **Test cạnh tranh:** đã thử partition, retry, replay, reset, tombstone GC và restore snapshot chưa?
13. **Quan sát hội tụ:** có đo lag, context/tombstone size và phát hiện resurrection không?
14. **Xác định retention:** tombstone, ledger, backups và PII có chính sách phù hợp không?

## 40. Kết luận

**Bộ đếm, tập hợp và ngữ nghĩa xóa là bài toán về ý định nghiệp vụ.** Một counter có thể hội tụ bằng merge component, một set có thể hội tụ bằng causal tags, nhưng không có kiểu dữ liệu nào tự biết “người dùng muốn xóa vĩnh viễn”, “lượt tăng chỉ được tính một lần” hay “không được bán vượt”.

Ghi nhớ:

- **G-Counter/PN-Counter** giữ các đóng góp thay vì ghi đè scalar; merge state bằng max giúp chống duplicate snapshot, không chống duplicate yêu cầu người dùng.
- **G-Set, 2P-Set, OR-Set, remove-wins và LWW** có lời hứa khác nhau khi add/remove concurrent. Không dùng thay thế tùy tiện.
- **Causal order** quyết định remove đã quan sát lần add nào. Add-wins không có nghĩa xóa không bao giờ có hiệu lực.
- **Tombstone, version và generation** ngăn event/replica cũ hồi sinh dữ liệu; xóa metadata sớm có thể gây zombie data.
- **TTL và logical delete không phải xóa vật lý hoàn chỉnh**; privacy/backup retention cần quy trình riêng.
- **Counter hội tụ không bảo vệ không âm**; inventory, quota, payment, unique claim và ACL có thể cần authority hoặc escrow.
- **Atomic operators của MongoDB, Redis, DynamoDB, Cassandra** có semantics và phạm vi khác CRDT đa writer; phải xác minh đúng hệ/phiên bản.
- **Retry và status unknown** cần request ledger/operation ID; nếu không increment có thể đếm hai lần và delete retry có thể xóa add mới.

Trước khi đưa một counter hoặc set vào hệ NoSQL phân tán, hãy hỏi:

> **“Hai thay đổi chưa quan sát nhau phải được hợp nhất thế nào; xóa có xóa cả lần thêm concurrent không; dữ liệu/metadata nào phải được giữ để chống hồi sinh; và có bất biến nào không thể chờ đến lúc các bản sao hội tụ?”**

Trả lời chính xác bốn câu hỏi đó là nền tảng để chọn kiểu dữ liệu, toán tử, chiến lược retry và chính sách đồng bộ phù hợp.
