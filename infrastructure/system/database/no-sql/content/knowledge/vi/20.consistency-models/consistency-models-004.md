# Sequential consistency và thứ tự quan sát chung trong NoSQL

## 1. Vì sao nhiều client cùng đọc một hệ có thể bất đồng về thứ tự?

Giả sử ứng dụng có hai thuộc tính ban đầu bằng `0`:

```text
order.approved = 0
order.published = 0
```

Một worker luôn **phê duyệt trước rồi mới công bố**:

```text
Worker A:
    WRITE approved = 1
    WRITE published = 1
```

Client B thực hiện theo thứ tự:

```text
    READ published -> 1
    READ approved  -> 0
```

Nếu hai thao tác ghi đều thuộc cùng luồng A và hai thao tác đọc thuộc cùng luồng B, kết quả này có vấn đề: B đã thấy thay đổi **xảy ra sau** nhưng lại không thấy thay đổi **xảy ra trước** trong cùng một chuỗi thao tác của A.

Một mô hình nhất quán có thể dùng để phân tích câu hỏi đó là **sequential consistency (SC)**, hay *nhất quán tuần tự*.

Ý tưởng trực giác:

> Mọi thao tác đọc/ghi phải có thể được giải thích như thể chúng diễn ra theo **một thứ tự tuần tự chung**, và thứ tự đó giữ nguyên **thứ tự chương trình của từng client/process**.

Điểm tinh tế là SC **không bắt buộc** thứ tự chung ấy trùng với thứ tự thời gian thực giữa các client khác nhau. Vì vậy SC khác **linearizability**, dù cả hai đều dùng ý tưởng một thứ tự chung.

Trong NoSQL, điều này đặc biệt quan trọng với nhiều replica, partition, read model, session và API có các chế độ consistency khác nhau. Một lần đọc thành công hoặc một bản sao “đã nhận update” chưa tự chứng minh toàn bộ lịch sử đọc/ghi đạt sequential consistency.

## 2. Hai điều kiện chính của sequential consistency

Để mô tả chính xác, xét một **history** \(H\) gồm các thao tác đọc và ghi do nhiều process/client thực hiện trên các đối tượng được chia sẻ.

Sequential consistency yêu cầu tồn tại **một thứ tự toàn phần** \(S\) của các thao tác (một *sequential history*) sao cho:

1. **Giữ thứ tự chương trình (*program order*)**: nếu cùng process A thực hiện thao tác \(a\) trước thao tác \(b\), thì \(a\) phải đứng trước \(b\) trong \(S\).
2. **Tôn trọng đặc tả tuần tự của đối tượng**: mỗi thao tác đọc trong \(S\) phải trả giá trị có thể xảy ra nếu các lệnh được thực hiện **lần lượt theo \(S\)**. Với thanh ghi đọc/ghi đơn giản, một lần đọc trả giá trị của lần ghi gần nhất đứng trước nó trong \(S\), hoặc giá trị khởi tạo nếu chưa có lần ghi nào.

Ký hiệu:

\[
\exists S:
\quad S \text{ là thứ tự toàn phần hợp lệ}
\quad\land\quad
\forall p,\; S|_p = H|_p
\]

Trong đó \(S|_p\) là phép chiếu thứ tự chung lên các thao tác của process \(p\), và \(H|_p\) là thứ tự chương trình của process đó. Ngoài điều kiện bảo toàn thứ tự, \(S\) còn phải hợp lệ theo semantics đọc/ghi của đối tượng.

Ta có thể hình dung:

```text
Lịch sử thực tế (nhiều client chạy đồng thời)

Client A:   W(x=1) ---------- W(y=1)
Client B:       R(x)=1 ----------- R(y)=1
Client C:            R(y)=0

Một thứ tự logic có thể giải thích kết quả:

W(x=1) -> R(x)=1 -> R(y)=0 -> W(y=1) -> R(y)=1
```

Thứ tự trên giữ `W(x)` trước `W(y)` của A, giữ `R(x)` trước `R(y)` của B, và trả đúng giá trị của các lần đọc. Nó là **một chứng nhân** cho SC đối với history minh họa.

### “Thứ tự chung” không nhất thiết là một file log vật lý

Định nghĩa yêu cầu **có thể tồn tại một thứ tự logic** giải thích lịch sử. Nó không bắt buộc mọi kiến trúc phải lưu một global log có timestamp duy nhất. Hệ thống có thể dùng một sequencer/log thống nhất, cơ chế điều phối khác hoặc thậm chí chỉ có những lịch sử mà ta chứng minh được một thứ tự hợp lệ.

Quan trọng là **tính chất có thể quan sát**, không phải tên của thành phần hạ tầng.

### “Chung” không có nghĩa mọi client thấy cùng phiên bản ngay cùng giây

Các client có thể đang đọc ở những **vị trí khác nhau** trong thứ tự logic. SC không bắt buộc chúng đồng thời nhìn thấy cùng một prefix mới nhất theo đồng hồ. Tuy nhiên tất cả các kết quả đọc vẫn phải **cùng giải thích được bởi một thứ tự toàn phần duy nhất**, giữ program order của mỗi client.

## 3. Program order là gì và không phải là gì?

**Program order** là thứ tự một process/session thực hiện những thao tác mà chương trình đã xác định có quan hệ trước–sau.

Ví dụ:

```text
Client A:
    W(x=1)  ->  W(y=1)

Client B:
    R(y)    ->  R(x)
```

Trong mọi thứ tự \(S\) hợp lệ:

\[
W_A(x=1) <_S W_A(y=1)
\]

\[
R_B(y) <_S R_B(x)
\]

Nhưng **không có ràng buộc program order trực tiếp** giữa một thao tác của A và một thao tác của B chỉ vì wall-clock của A xảy ra trước B. Đó là phần mà linearizability bổ sung, không phải điều kiện chung của SC.

### Một request song song trong cùng ứng dụng

Đừng mặc định mọi lời gọi từ cùng một ứng dụng luôn có thứ tự nghiêm ngặt. Ví dụ Java tạo hai tác vụ đồng thời:

```java
CompletableFuture<Void> first = CompletableFuture.runAsync(
    () -> repository.write("x", 1)
);
CompletableFuture<Void> second = CompletableFuture.runAsync(
    () -> repository.write("y", 1)
);
CompletableFuture.allOf(first, second).join();
```

Ví dụ chỉ minh họa API bất đồng bộ (giả định `repository` do ứng dụng định nghĩa). Hai thao tác ghi không tự có quan hệ `W(x)` trước `W(y)` chỉ vì dòng code tạo `first` đứng trên dòng code tạo `second`: cả hai chạy song song. Muốn có thứ tự, chương trình phải xây một **dependency/happens-before** thực sự, chẳng hạn đợi `first` hoàn thành rồi mới bắt đầu `second`.

Khi kiểm thử SC, cần ghi **chính xác thứ tự thao tác của từng client**, không tự suy ra thứ tự từ timestamp ở hai process độc lập.

## 4. Đọc trễ sau ACK: SC có thể cho phép, linearizability thì không

Xét một thanh ghi `x=0` ban đầu:

```text
Thời gian thực:

Client A:  W(x=1) ---- ACK
                            \
Client B:                    R(x) ---> 0
```

Giả sử A đã nhận ACK **hoàn toàn trước khi** B bắt đầu đọc. Hai thao tác thuộc **hai client khác nhau**.

Với SC, có thể chọn thứ tự logic:

```text
R_B(x) -> 0    trước    W_A(x=1)
```

Thứ tự logic này không trùng thứ tự thời gian thực, nhưng vẫn giữ program order của từng client và trả kết quả hợp lệ. **Vì thế chỉ riêng trường hợp B đọc giá trị cũ sau ACK của A chưa đủ để kết luận vi phạm SC.**

Đối với **linearizability**, điều kiện bổ sung là:

> Nếu thao tác A hoàn tất trước khi thao tác B bắt đầu theo thời gian thực, A phải đứng trước B trong thứ tự tuyến tính.

Do đó trong ví dụ này, **linearizability không cho phép** B đọc `0` nếu không có một write khác đưa `x` về `0`.

### Tuy nhiên, cùng một client thì khác

```text
Client A:
    W(x=1) -> ACK -> R(x) -> 0
```

Nếu không có thao tác ghi khác có thể giải thích giá trị `0`, history này **vi phạm SC**, vì program order bắt buộc `W(x=1)` đứng trước `R(x)`, nên đọc phải thấy `1`.

**Phân biệt then chốt:**

- Sau ACK của **client khác**: SC không áp đặt thứ tự thời gian thực xuyên client.
- Đọc sau chính write của **cùng client/process**: thứ tự chương trình phải được bảo toàn.

Nếu chuyển request giữa nhiều thread/session mà chương trình cần tính chất read-your-writes, phải thiết kế để backend nhận biết quan hệ thứ tự này; đừng giả định routing ngẫu nhiên đến replica sẽ tự duy trì nó.

## 5. Ví dụ hợp lệ: các client đọc ở các thời điểm logic khác nhau

Ban đầu `x=0`, một client ghi `x=1`:

| Client | Chuỗi thao tác |
|---|---|
| A | `W(x=1)` |
| B | `R(x)=0`, sau đó `R(x)=1` |
| C | `R(x)=1` |

Một thứ tự toàn phần khả thi:

```text
R_B(x)=0
   |
   v
W_A(x=1)
   |
   v
R_B(x)=1
   |
   v
R_C(x)=1
```

Nó giữ B đọc `0` trước `1` và không có đọc nào yêu cầu một giá trị không thể có theo thứ tự.

Ở đây SC **không cho biết** B phải chuyển từ `0` sang `1` sau bao nhiêu mili giây. Nó là điều kiện về **thứ tự và tính hợp lệ của lịch sử**, không phải một SLA về độ trễ replication.

## 6. Ví dụ bất khả thi: thấy công bố rồi lại không thấy phê duyệt

Ban đầu `approved=0`, `published=0`.

```text
Process A:
    W(approved=1)     (A1)
    W(published=1)    (A2)

Process B:
    R(published)=1    (B1)
    R(approved)=0     (B2)
```

Từ program order của A:

\[
A1 <_S A2
\]

Để B đọc được `published=1`, A2 phải đứng trước B1:

\[
A2 <_S B1
\]

Từ program order của B:

\[
B1 <_S B2
\]

Để B đọc `approved=0`, khi chỉ A1 ghi `approved=1` và không có ghi khác, B2 phải đứng trước A1:

\[
B2 <_S A1
\]

Ghép lại:

\[
A1 <_S A2 <_S B1 <_S B2 <_S A1
\]

Đây là một **chu trình trước–sau**, không thể là thứ tự toàn phần hợp lệ. Vì vậy history **không sequentially consistent**.

### Điều kiện của ví dụ

Kết luận dựa trên giả định:

- Cả hai thuộc tính ban đầu bằng `0`.
- Không có write ẩn đưa `approved` về `0`.
- B đọc `published` trước rồi đọc `approved` theo program order.
- Những thao tác là đọc/ghi các thanh ghi theo semantics đã quy định.

Nếu xuất hiện một write thứ ba như `W(approved=0)`, phải đánh giá lại toàn bộ lịch sử; **không thể kết luận chỉ từ một đoạn log bỏ sót write**.

## 7. Litmus test “store buffering”: cả hai đều đọc 0 có hợp lệ không?

Một mẫu kiểm tra thường dùng:

```text
Ban đầu: x=0, y=0

Process P1                Process P2
-----------               -----------
W(x=1)                    W(y=1)
R(y) -> 0                 R(x) -> 0
```

Từ thứ tự chương trình:

\[
W_1(x) <_S R_1(y)
\]

\[
W_2(y) <_S R_2(x)
\]

Muốn `R_1(y)=0`, phép đọc phải đứng trước `W_2(y)`. Muốn `R_2(x)=0`, phép đọc phải đứng trước `W_1(x)`.

Như vậy:

```text
W1(x) -> R1(y)=0 -> W2(y) -> R2(x)=0 -> W1(x)
```

Chu trình xảy ra. **Kết quả cả hai read đều trả 0 bị cấm dưới SC** với giả định chỉ có hai write đó.

Nếu một hệ dữ liệu phân tán cho phép mỗi client ghi vào bản sao của mình rồi đọc bản sao khác quá cũ, đôi khi ta có thể quan sát kiểu lịch sử tương tự. Đây là dấu hiệu không thể giải thích bằng một thứ tự tuần tự toàn hệ.

### Một số kết quả khác có thể hợp lệ

```text
P1 đọc y=1, P2 đọc x=0
```

Chọn thứ tự:

```text
W2(y) -> W1(x) -> R1(y)=1 -> R2(x)=0 ?
```

Thứ tự vừa viết **không đúng**, vì nếu `W1(x)` đứng trước `R2(x)` thì `R2(x)` phải trả `1`. Một thứ tự đúng là:

```text
W2(y) -> R2(x)=0 -> W1(x) -> R1(y)=1
```

Nó giữ program order của P2 (`W2(y)` trước `R2(x)`) và P1 (`W1(x)` trước `R1(y)`). Kết quả một đọc `1`, một đọc `0` có thể giải thích được.

**Bài học:** không đánh giá một cặp giá trị chỉ từ cảm giác “có vẻ cũ”; hãy thử dựng **một thứ tự duy nhất** cho tất cả thao tác, hoặc chứng minh có chu trình ràng buộc.

## 8. IRIW: hai observer thấy hai write độc lập theo thứ tự khác nhau

**IRIW** (*Independent Reads of Independent Writes*) dùng hai write độc lập và hai reader:

```text
Ban đầu x=0, y=0

P1                  P2
--                  --
W(x=1)              W(y=1)

P3                  P4
--                  --
R(x) -> 1           R(y) -> 1
R(y) -> 0           R(x) -> 0
```

P3 đã nhìn thấy `x=1` nhưng chưa thấy `y=1`. P4 đã nhìn thấy `y=1` nhưng chưa thấy `x=1`.

Đặt tên:

- `Wx`: P1 ghi x=1.
- `Wy`: P2 ghi y=1.
- `P3x` rồi `P3y`: hai read theo thứ tự P3.
- `P4y` rồi `P4x`: hai read theo thứ tự P4.

Theo kết quả P3:

\[
Wx <_S P3x <_S P3y <_S Wy
\]

Theo kết quả P4:

\[
Wy <_S P4y <_S P4x <_S Wx
\]

Suy ra `Wx < Wy < Wx`, bất khả thi.

**Kết luận:** history IRIW này **không đạt SC**. Nó minh họa tại sao “mỗi key trông có thứ tự riêng” vẫn chưa đủ để các thao tác trên **nhiều key** có một thứ tự quan sát chung.

### Chú ý ranh giới với linearizability theo từng object

Không được đánh đồng **per-key sequential consistency** với **per-key linearizability**. Sequential consistency nói chung **không có tính compositional**: mỗi object riêng lẻ có thể có thứ tự tuần tự hợp lệ nhưng lịch sử kết hợp của các object lại không có thứ tự toàn cục.

Linearizability, với các object độc lập được xác định đúng và cùng mô hình lịch sử, **có tính compositional**: nếu mỗi object linearizable thì hệ kết hợp cũng linearizable. Tuy nhiên tính chất đó **không tạo một transaction nguyên tử nhiều key**; một transaction gồm nhiều thao tác riêng vẫn có thể bị thao tác khác chen vào.

Đây là hai câu hỏi khác nhau: “mỗi thao tác trên từng key có thể tuyến tính hóa không?” và “một nhóm nhiều key có được cập nhật/đọc nguyên tử như một đơn vị không?”.

## 9. Một thứ tự ghi chung chưa tự đủ nếu read quan sát sai

Một hệ có thể cam kết rằng **mọi write** được sắp vào một log:

```text
Log:
  101: W(x=1)
  102: W(y=1)
```

Nhưng giả sử các replica phục vụ read ở những trạng thái **không phải prefix hợp lệ** của log:

```text
Replica A đã áp write 101, chưa áp 102: x=1, y=0
Replica B đã áp write 102, chưa áp 101: x=0, y=1
```

Hai observer có thể tạo history IRIW nêu trên.

**Global order của write là điều kiện hữu ích, nhưng chưa đủ nếu read được phục vụ từ các bản sao có thể áp dụng thay đổi khác thứ tự.** Để bảo vệ một thứ tự quan sát chung, cơ chế đọc phải tương thích với thứ tự của write; ví dụ đọc một **prefix** đã áp theo thứ tự, đồng thời giữ session monotonicity khi di chuyển giữa replica.

Nếu đã áp một write ở vị trí 102 nhưng bỏ qua 101, bản sao **không** đại diện cho một prefix của log. Đây là một kiểu thiết kế cần tránh nếu toàn hệ được kỳ vọng có SC trên các key đó.

## 10. So sánh sequential consistency với linearizability

Hai mô hình thường bị gọi nhầm là “strong consistency”.

| Thuộc tính | Sequential consistency | Linearizability |
|---|---|---|
| Một thứ tự toàn phần giải thích lịch sử | Có | Có |
| Giữ program order của mỗi process | Có | Có, dưới đặc tả thao tác thích hợp |
| Giữ thứ tự thời gian thực giữa hai thao tác **không chồng lấn** | **Không yêu cầu** | **Bắt buộc** |
| Đọc sau ACK của client khác có thể trả giá trị cũ? | Có thể, nếu vẫn giải thích được bằng một lịch sử tuần tự | Không, nếu read bắt đầu sau write đã hoàn tất và không có write cạnh tranh khác |
| Cần chờ bao lâu để thấy write? | Không có ngưỡng thời gian trong định nghĩa | Không đặt latency bound, nhưng ràng buộc kết quả theo thời gian thực |
| Tính compositional trên các object độc lập | Nói chung không | Có |
| Tự bảo đảm multi-key transaction nguyên tử? | Không | Không, nếu chỉ từng thao tác/key độc lập |

### Cách nhớ

**Sequential consistency:** “Có một lịch sử tuần tự chung mà các client có thể cùng chấp nhận, giữ thứ tự lệnh của từng client.”

**Linearizability:** “Ngoài lịch sử chung ấy, những gì đã **hoàn tất trước khi một thao tác mới bắt đầu** phải xuất hiện trước thao tác đó.”

Một hệ linearizable đáp ứng ràng buộc mạnh hơn SC cho lịch sử read/write theo mô hình này. Chiều ngược lại không đúng.

### Sai lầm về thứ tự thời gian

```text
A: W(x=1) hoàn tất ở 10:00:01
B: R(x)=0 bắt đầu ở 10:00:02
```

Nếu khác process, SC **có thể** xếp `R_B` trước `W_A` để giải thích. Linearizability **không được** xếp như vậy.

Tuy nhiên nếu B thực hiện hai read liên tiếp `R(x)=1` rồi `R(x)=0` mà không có write đưa x về 0, **SC cũng không được phép**, vì không thể giữ hai read ấy theo program order trong một lịch sử hợp lệ.

## 11. Causal consistency và SC

**Causal consistency** bảo vệ thứ tự của những thao tác có quan hệ nhân quả; các thao tác **không liên quan nhân quả** có thể được quan sát theo những thứ tự khác nhau ở các replica/client.

Một quan hệ nhân quả có thể được hình thành bởi:

1. **Program order:** cùng một process ghi `approved=1` rồi `published=1`.
2. **Read-from:** B đọc một thay đổi của A rồi viết một kết quả phụ thuộc vào nó.
3. **Tính bắc cầu:** nếu A gây B và B gây C thì A gây C.

Ví dụ:

```text
Alice: WRITE comment="Ready"
Bob:   READ comment="Ready"
Bob:   WRITE reply="Approved"
```

Một mô hình causal không nên để người quan sát thấy `reply="Approved"` mà không có khả năng quan sát thay đổi `comment="Ready"` vốn là nguyên nhân của reply, theo ngữ nghĩa causal visibility của hệ.

### Causal consistency có một global order bắt buộc không?

**Không.** Hai write độc lập `W(x=1)` và `W(y=1)` có thể không có quan hệ causal. Những người quan sát khác nhau có thể thấy chúng theo những thứ tự khác nhau, miễn các quan hệ nhân quả cần bảo vệ không bị vi phạm.

SC mạnh hơn ở khía cạnh **đòi một thứ tự toàn phần giải thích được mọi thao tác**, không chỉ bảo vệ một thứ tự bộ phận của các thao tác phụ thuộc.

IRIW là ví dụ đặc biệt dễ nhớ: hai write x và y độc lập có thể được nhìn theo hai hướng ở những mô hình cho phép sự khác biệt đó, nhưng **không thể cùng giải thích bằng một thứ tự toàn phần SC**.

### Tại sao tên “causal” nghe có vẻ mạnh nhưng có thể yếu hơn SC?

“Causal” nói **điều gì phải giữ thứ tự**; “sequential” nói **cả lịch sử có thể được xếp thành một chuỗi hợp lệ không**. Một global order tất yếu tôn trọng những phụ thuộc read-from/program-order đã đưa vào lịch sử, nhưng nhiều cách quan sát các write độc lập có thể chỉ hợp lệ theo causal chứ không hợp lệ theo SC.

## 12. Eventual consistency và session guarantees

**Eventual consistency** thường nhấn mạnh rằng nếu không còn update mới và hệ thống tiếp tục hoạt động theo điều kiện giả định, các replica cuối cùng sẽ **hội tụ**. Nó không mặc nhiên yêu cầu tại mọi thời điểm các lần đọc của nhiều client có thể xếp thành một lịch sử SC.

Ví dụ:

```text
Write x=1
Replica A đã nhận
Replica B chưa nhận
Client B đọc B -> 0
Later, B nhận update -> 1
```

Hiện tượng stale read **không đủ để chứng minh vi phạm SC** khi client khác vừa ghi; nhưng eventual consistency **có thể** cho phép các lịch sử phức tạp hơn (như một số dị thường cross-key) mà SC cấm.

### Các session guarantees phổ biến

| Bảo đảm phiên | Ý nghĩa tóm tắt |
|---|---|
| **Read-your-writes** | Sau khi một client ghi, những read về sau của chính client không bỏ qua write đó theo hợp đồng |
| **Monotonic reads** | Một client không quay lại một snapshot cũ hơn những gì nó đã quan sát |
| **Monotonic writes** | Write sau của cùng client không được áp trước write trước theo hợp đồng |
| **Writes-follow-reads** | Write phụ thuộc một read được sắp phù hợp với dữ liệu đã đọc |

Các bảo đảm phiên giúp người dùng tránh nhiều trải nghiệm khó hiểu, nhưng **không tự động chứng minh có một thứ tự toàn phần chung cho nhiều client và nhiều key**.

Ví dụ mỗi client chỉ đọc phiên bản không giảm vẫn có thể chưa đủ nếu các client quan sát những phần cập nhật **không tương thích** nhau trên nhiều key.

### Safety khác liveness

SC là một **safety property** trên lịch sử các thao tác: một kết quả sai lịch sử là phản ví dụ. Eventual convergence là một **cam kết tiến triển** dưới những giả định về không còn write và hệ hoạt động.

Vì vậy không nên đơn giản dùng một thứ tự xếp hạng mọi tính chất như thể chúng cùng đo một đại lượng. Cần nêu **khía cạnh đang so**: thứ tự đọc/ghi, độ mới theo thời gian thực, hội tụ, availability hay durability.

## 13. Sequential consistency khác serializability như thế nào?

Hai thuật ngữ đều liên quan tới một thứ tự tuần tự, nhưng **đơn vị được sắp thứ tự khác nhau**.

### Sequential consistency

Thông thường dùng cho **thao tác trên đối tượng dùng chung**, ví dụ read/write của register, key hoặc thao tác trên đối tượng có đặc tả tuần tự. Các thao tác của từng process phải giữ program order trong một chuỗi logic.

### Serializability

Dùng cho **giao dịch**. Lịch sử thực thi đồng thời phải tương đương một thứ tự **các transaction** chạy lần lượt, sao cho các tác động của transaction được nhìn như một đơn vị theo đặc tả isolation.

Ví dụ một transaction chuyển tiền:

```text
T1:
    Debit Account A 100
    Credit Account B 100
```

Nếu hai thao tác bị các transaction khác chen vào và làm một giao dịch đọc thấy trạng thái không tương đương bất kỳ thứ tự transaction nào, lịch sử có thể không serializable.

### SC không tự tạo transaction đa key

```text
P1: W(a=90) ; W(b=110)
P2: R(a)=90 ; R(b)=100
```

Giả sử ban đầu a=100, b=100. Một thứ tự chung:

```text
W(a=90) -> R(a)=90 -> R(b)=100 -> W(b=110)
```

**hoàn toàn phù hợp SC**: P2 nhìn một trạng thái trung gian giữa hai write. Nếu nghiệp vụ cần hai số dư thay đổi **nguyên tử cùng nhau**, phải dùng transaction hoặc thiết kế bất biến phù hợp. Sequential consistency cho các thao tác riêng **không bảo vệ tính nguyên tử của nhóm**.

### Strict serializability

**Strict serializability** kết hợp serializability ở cấp transaction với ràng buộc thời gian thực cho các transaction không chồng lấn. Nó gần trực giác “transaction xảy ra nguyên tử theo thứ tự thực tế” hơn SC.

| Tính chất | Đơn vị chính | Thứ tự thời gian thực xuyên client |
|---|---|---|
| Sequential consistency | Thao tác/object operation | Không bắt buộc |
| Linearizability | Thao tác/object operation | Có |
| Serializability | Transaction | Không bắt buộc |
| Strict serializability | Transaction | Có |

Các khái niệm này không nên được đánh đồng với **durability**: transaction có thể được sắp đúng nhưng dữ liệu vẫn mất khi cấu hình ACK/persistence không bảo đảm loại crash tương ứng.

## 14. Total order không có nghĩa tất cả thao tác cùng lúc trên nhiều key

Trong SC, thứ tự tổng là thứ tự **các thao tác**, không tự nhóm chúng thành một transaction. Một client có thể quan sát trạng thái **giữa** hai write của client khác.

Ví dụ hợp lệ:

```text
Ban đầu x=0, y=0

P1: W(x=1) -> W(y=1)
P2: R(x)=1 -> R(y)=0
```

Thứ tự tuần tự:

```text
W(x=1) -> R(x)=1 -> R(y)=0 -> W(y=1)
```

Thứ tự này giữ program order và hoàn toàn có thể xảy ra.

So với ví dụ ở mục 6:

```text
P1: W(x=1) -> W(y=1)
P2: R(y)=1 -> R(x)=0
```

thì **không** có một thứ tự hợp lệ.

Hai trường hợp khác nhau chỉ bởi **thứ tự đọc ở P2**. Vì vậy cần phân tích history thật, không chỉ xem tập những giá trị cuối cùng xuất hiện.

## 15. Kiến trúc một global sequencer hoặc log thống nhất

Một cách hiện thực **một thứ tự chung** là đặt thao tác qua một sequencer:

```text
                Client A      Client B       Client C
                   \             |             /
                    \            |            /
                     v           v           v
                        Global Sequencer
                                |
                                v
                      Ordered Operation Log
                       [101] W(x=1)
                       [102] W(y=1)
                       [103] R(x)
                                |
                   +------------+------------+
                   |                         |
                   v                         v
             Replica A                  Replica B
          apply 101,102,103          apply ordered prefix
```

Một sequential log có thể giúp:

- Cấp thứ tự ổn định cho các write.
- Phân phát thay đổi tới replica theo cùng sequence.
- Làm căn cứ kiểm tra bản sao đã áp tới **log position** nào.
- Dùng version/read token để tránh client quay về vị trí cũ hơn.

Nhưng cần quan tâm cả **read**: nếu chúng tự đọc những snapshot không phải prefix hợp lệ hoặc một client bị route tới replica lùi về version trước đó, hệ có thể mất bảo đảm SC.

### Nếu sequencer linearizable?

Một leader/consensus log kết hợp read barrier theo thời gian thực có thể cung cấp **linearizability**, mạnh hơn SC. Đây là một lựa chọn kiến trúc; SC **không bắt buộc** mọi lần đọc phải chờ một global linearizable read barrier nếu chỉ cần bảo vệ program order và thứ tự tuần tự chung.

### Chi phí

- Một đường điều phối chung có thể trở thành bottleneck.
- Độ trễ tăng do network hop, batching hoặc chờ log position.
- Failover cần bảo vệ thứ tự đã cam kết, tránh fork lịch sử.
- Replication lag phải đi kèm cơ chế đọc đúng phiên bản.
- Nếu nhiều vùng địa lý, mỗi quyết định đòi coordination có thể tăng latency.

Không phải mọi bài toán NoSQL cần SC toàn hệ; nhiều workload chỉ cần consistency mạnh trong **một aggregate** và eventual consistency ở projection.

## 16. Hạn chế của log theo partition

Một hệ thống có thể chia dữ liệu:

```text
Partition 0 log:  x=1, x=2, ...
Partition 1 log:  y=1, y=2, ...
```

Mỗi partition có thứ tự sự kiện riêng. Điều đó **không tự tạo một thứ tự toàn phần trên cả hai partition**, đặc biệt khi nhiều reader truy cập hai partition theo thứ tự khác nhau.

### Kafka là ví dụ về phạm vi thứ tự

Trong broker phân vùng như Kafka, các record có thứ tự **trong một partition** theo offset. Không có một offset duy nhất xếp thứ tự tất cả record thuộc mọi partition của topic hoặc các topic khác.

Gửi event cùng aggregate theo **cùng partition key** giúp giữ order cho aggregate theo các điều kiện producer/consumer tương ứng. Nó **không biến mọi thao tác đọc/ghi của MongoDB, Redis, search và broker thành một lịch sử SC toàn cục**.

Nếu cần invariant liên quan nhiều partition, thường phải dùng:

- Một nguồn/transaction coordinator có phạm vi phù hợp.
- State machine của aggregate chứa dữ liệu cần quyết định.
- Protocol chuyển quyền/đặt chỗ có điều kiện.
- Hoặc chấp nhận eventual consistency và thiết kế compensation/reconciliation.

Một thứ tự log dùng để phát event cũng không tự đảm bảo **atomic multi-key transaction** ở target.

## 17. Replication, replica lag và session-aware reads

Giả sử một write đã được commit ở primary nhưng secondary còn chậm:

```text
Primary:   logPosition = 105
Replica A: logPosition = 105
Replica B: logPosition = 103
```

Client A đã ghi/đọc tại position 105. Nếu request tiếp theo của A được đưa tới B và đọc snapshot 103, client có thể bị **monotonic-read/read-your-writes violation**.

Một hướng thiết kế là mang theo **session position token**:

```text
Client gửi request với minPosition = 105
          |
          v
Router chọn replica đã apply >= 105
          |
       hoặc chờ / fallback primary
          |
          v
Trả dữ liệu thỏa vị trí yêu cầu
```

Token này không tự là API tiêu chuẩn của mọi NoSQL; nó minh họa cách sử dụng **read barrier hoặc version watermark**. Nếu có nhiều shard/log độc lập, một số nguyên toàn cục có thể không tồn tại; phải dùng vector/metadata phù hợp hoặc cơ chế mạnh hơn.

**Cảnh báo:** việc chỉ giữ read-your-writes và monotonic reads cho từng session chưa đủ chứng minh có một global sequential order cho toàn hệ. Cần xem cách mọi key và replica cùng tổ chức thứ tự.

### Sticky session là giải pháp đủ chưa?

Gắn một client với một replica có thể tránh một số read regression, nhưng:

- Replica có thể áp write khác thứ tự so với replica khác.
- Failover đổi replica.
- Dữ liệu nằm ở nhiều shard.
- Một service khác có thể đọc từ cache/search với consistency riêng.

Do đó sticky routing là **một công cụ**, không phải chứng nhận SC.

## 18. Cách đánh giá SC khi dùng một số hệ NoSQL

Không nên gán nhãn cả sản phẩm là “SC” hoặc “không SC” chỉ từ tên. Phải xác định **API, đối tượng, topology, read/write settings và kiểu thao tác**.

### MongoDB

MongoDB có các chế độ `readConcern`, `writeConcern` và session semantics. Một document update nguyên tử không đồng nghĩa mọi read qua mọi secondary đều đồng thời thấy cập nhật. Causal-consistent session là một hợp đồng khác với yêu cầu mọi client và mọi key chia sẻ một global SC history.

Khi hệ cần đảm bảo mạnh tại một quyết định, cần xác định read/write concern và topology; không suy ra SC đa document hoặc linearizability toàn hệ từ một lệnh `findOne` thông thường.

### DynamoDB

DynamoDB có read path với lựa chọn strongly consistent ở **những nơi được hỗ trợ**, trong khi GSI và replication liên vùng có đặc điểm eventual riêng. Tính đúng của một item lookup không tự xác lập điều kiện quan sát chung của nhiều API, nhiều index, nhiều region và workflow.

Nếu cần cập nhật/kiểm tra bất biến nhiều item, hãy xem transaction/conditional write API phù hợp, thay vì chỉ dựa vào filter và các truy vấn GSI.

### Cassandra

Cassandra dùng replication factor và consistency level như `ONE`, `QUORUM`, `LOCAL_QUORUM`; các lựa chọn ấy nói về số/phạm vi replica tham gia thao tác. Chúng không tự tạo một thứ tự tổng cho tất cả thao tác trên mọi partition.

Từ công thức quorum kiểu \(R+W>RF\) trong một số giả định cũng **không thể tự suy ra** toàn hệ có SC hoặc linearizability xuyên partition khi còn có concurrency, timestamps, reconciliation, topology và các kiểu lỗi thực tế.

### Redis

Một Redis primary có thể xử lý các command theo thứ tự của server và cung cấp thao tác nguyên tử cho nhiều command đơn. Nhưng replication thường bất đồng bộ; đọc từ replica và failover có thể thay đổi những gì client thấy. **Một thứ tự lệnh trên primary** không tự đảm bảo toàn bộ topology/cache read paths có SC.

Nếu một nghiệp vụ cần nguyên tử nhiều thay đổi ở Redis, cần chọn `MULTI/EXEC`, Lua/script hoặc những cơ chế phù hợp và hiểu phạm vi của chúng. Nguyên tử trong Redis không phải transaction chung với MongoDB hay broker.

### Graph và search

Graph database có thể có transaction và consistency semantics theo topology, nhưng một traversal qua nhiều node/edge không nhất thiết là một snapshot mạnh chỉ vì có cú pháp `MATCH`. Search index được cập nhật bất đồng bộ thường là **read model**; refresh lag không được dùng làm bảo đảm SC của nguồn.

### Bảng câu hỏi trước khi cam kết

| Cần xác định | Ví dụ câu hỏi |
|---|---|
| Đối tượng bảo đảm | Một key, một partition, một collection, hay nhiều key? |
| Read path | Primary, secondary, GSI, cache, search, local replica? |
| Write path | ACK ở đâu, quorum nào, commit nào? |
| Thứ tự client | Có session token, monotonic reads, program-order routing? |
| Thứ tự nhiều key | Dùng chung một log/coordinator hay từng shard riêng? |
| Failover | Có rollback/reorder những write đã ACK không? |
| Read–write overlap | Đọc bị chồng lấn với write được phép trả gì? |
| Transaction | Nhiều operation có được nhóm thành một đơn vị atomic? |

**Không sử dụng tài liệu của một read API riêng để tuyên bố mô hình nhất quán cho mọi thành phần của hệ thống.**

## 19. Sequential consistency không giải quyết hết chuyện durability

SC kiểm tra **lịch sử giá trị và thứ tự quan sát**, không tự quy định:

- Write đã được fsync bền trên disk chưa.
- Có replica ở AZ/region khác không.
- Restore từ backup sẽ mất bao nhiêu thay đổi.
- Sau crash ACK nào còn hiệu lực.
- Một cache có giữ dữ liệu quá TTL hay không.

Ví dụ hệ có thể phục vụ mọi read từ một leader nhất quán nhưng trả ACK trước khi log được đồng bộ bền; sau crash, một số write đã ACK mất. **Durability** và **consistency** là những trục đánh giá khác nhau.

Mặt khác, một backup rất bền không làm các read từ những replica lag tự nhiên trở nên sequentially consistent.

Khi đánh giá sau failover, phải định nghĩa history nào được xét, các write nào đã hoàn tất và hệ thống cam kết gì cho chúng. Một write đã ACK nhưng bị rollback có thể gây vi phạm hợp đồng consistency/durability tùy mô hình và API; không thể chỉ nói “đây là eventual nên bình thường” khi ứng dụng cần bảo đảm mạnh.

## 20. Thứ tự quan sát và quyền truy cập: đừng lấy SC thay authorization

Giả sử tài liệu được thu hồi quyền ở nguồn, nhưng search index/cache chưa cập nhật. Cho dù các thao tác đọc/ghi có một giải thích theo SC ở phạm vi nào đó, API vẫn có thể **lộ dữ liệu** nếu nó không kiểm tra quyền hiện hành.

Đối với bất biến nhạy cảm:

- Lấy tenant ID từ identity đã xác thực.
- Kiểm tra quyền tại điểm trả dữ liệu bằng nguồn có thẩm quyền hoặc cơ chế fail-closed tương đương.
- Đặt version/epoch cho chính sách truy cập nếu cần.
- Không coi “projection rồi sẽ nhận sự kiện revoke” là biện pháp bảo mật đủ mạnh.

**Mô hình nhất quán và chính sách authorization giải quyết hai câu hỏi khác nhau.** Một hệ có global order vẫn có thể trả đúng thứ tự **dữ liệu mà người dùng không được phép đọc** nếu kiểm tra quyền sai.

## 21. Kiểm thử sequential consistency bằng history, không chỉ timestamp

Một bài kiểm thử có thể ghi:

```text
operationId
clientId / processId
programSequence
operationType (READ/WRITE)
key
writeValue
readReturnedValue
startTime, endTime (để kiểm tra linearizability nếu cần)
readReplica / requestRoute (phục vụ điều tra)
```

Đối với SC, bộ kiểm tra cố tìm **một thứ tự toàn phần** thỏa:

1. Từng process giữ đúng `programSequence`.
2. Mỗi read trả giá trị phù hợp khi chạy các thao tác theo thứ tự ấy.

Timestamp có thể được ghi để chẩn đoán, nhưng **không được buộc mọi thao tác của client A trước client B chỉ vì endTime nhỏ hơn startTime** nếu mục tiêu đang kiểm tra **SC thuần túy**. Đó là ràng buộc của linearizability.

### 21.1. Bộ kiểm tra mini cho lịch sử nhỏ

Ví dụ Python sau dùng brute force cho **các thanh ghi đơn giản khởi tạo 0**, chỉ thích hợp history ít thao tác và không có transaction:

```python
from itertools import permutations

# Mỗi phần tử: (client, kind, key, write_value, read_result)
# Thứ tự xuất hiện của những operation cùng client là program order.
history = [
    ("P1", "W", "x", 1, None),
    ("P1", "R", "y", None, 0),
    ("P2", "W", "y", 1, None),
    ("P2", "R", "x", None, 0),
]

def is_sequentially_consistent(operations, initial=None):
    initial = dict(initial or {"x": 0, "y": 0})
    count = len(operations)

    for order in permutations(range(count)):
        position = {op_index: rank for rank, op_index in enumerate(order)}

        # Bảo toàn program order của từng client.
        if any(
            operations[i][0] == operations[j][0]
            and position[i] > position[j]
            for i in range(count)
            for j in range(i + 1, count)
        ):
            continue

        state = dict(initial)
        valid = True

        for index in order:
            _, kind, key, value, result = operations[index]
            if kind == "W":
                state[key] = value
            elif kind == "R":
                if state.get(key) != result:
                    valid = False
                    break
            else:
                raise ValueError("Unknown operation")

        if valid:
            return True, order

    return False, None

print(is_sequentially_consistent(history))
# (False, None) - store buffering, cả hai read đều trả 0.
```

Với \(n\) thao tác, duyệt \(n!\) hoán vị sẽ nhanh chóng quá lớn. Bộ kiểm tra thực tế cần tìm kiếm có ràng buộc, phát hiện chu trình, xử lý operation chưa hoàn thành, concurrency và đặc tả đối tượng phức tạp. Ví dụ trên chỉ giúp người học thấy rõ ý nghĩa **“tồn tại một thứ tự”**.

### 21.2. History SC nhưng không linearizable

Thay `history` bằng:

```python
history = [
    ("A", "W", "x", 1, None),
    ("B", "R", "x", None, 0)
]
```

Hàm `is_sequentially_consistent` trả `True` vì có thể sắp B đọc trước A ghi. Nếu biết **A write đã kết thúc trước khi B read bắt đầu**, thì cùng history **không linearizable**. Bộ kiểm tra SC ở trên cố ý không dùng timestamp.

### 21.3. Không tự chứng nhận production bằng một lịch sử nhỏ

Một history không tìm thấy vi phạm SC **không chứng minh cả hệ luôn SC**. Cần tạo nhiều kiểu cạnh tranh, failover, đổi replica, cross-key, lag và kiểm tra trên các đường API đúng như sản phẩm. Một test chỉ gọi một key từ một client gần như không thể phát hiện những vấn đề global ordering phức tạp.

## 22. Hướng tạo workload và litmus test cho NoSQL

### Nhóm A — Program order

```text
Client 1: W(x=1); R(x)
Expected under SC if no competing write x=0: R(x)=1
```

Nhóm này giúp kiểm tra read-your-writes trong cùng session/đường truy cập.

### Nhóm B — Message passing

```text
Client 1: W(payload=1); W(flag=1)
Client 2: R(flag)=1; R(payload)=0
```

Với hai write có thứ tự và không có write ẩn, kết quả này **vi phạm SC**. Đây là test có thể phát hiện việc replica cho reader thấy flag mới nhưng payload cũ một cách không thể xếp tuần tự.

### Nhóm C — Store buffering

```text
Client 1: W(x=1); R(y)=0
Client 2: W(y=1); R(x)=0
```

Kết quả hai read đều 0 **không có SC witness**.

### Nhóm D — Independent writes, independent readers

```text
Client 1: W(x=1)
Client 2: W(y=1)
Client 3: R(x)=1; R(y)=0
Client 4: R(y)=1; R(x)=0
```

Đây là IRIW; kiểm tra yêu cầu thứ tự chung trên **nhiều key**.

### Nhóm E — Failover và session migration

```text
Client A: W(x=1) -> ACK
Failover/reroute
Client A: R(x) -> ?
```

Nếu không có write đưa x về 0 và API cam kết program order cho một client, việc đọc lại 0 có thể vi phạm SC đối với history này. Cần phân biệt:

- Write có thực sự được xác nhận/commit theo hợp đồng?
- Đọc có thuộc cùng client/session logic không?
- Có request khác ghi lại `0` không?
- Replica/failover có làm mất update đã ACK không?

### Nhóm F — Multi-key transaction

```text
Transaction T: W(a=90), W(b=110)
Reader: R(a)=90, R(b)=100
```

Hai read như vậy **có thể được giải thích dưới SC ở cấp thao tác rời**. Nếu yêu cầu hai field chuyển cùng lúc, kiểm thử phải dùng **transaction-level serializability/atomic visibility** theo đúng hợp đồng, không chỉ SC.

### Khi gây lỗi

Thử trên môi trường cô lập với dữ liệu giả, không gây mất node hay tắt nguồn hệ production. Ghi lịch sử độc lập với datastore đang thử; nếu log kiểm thử cũng mất trong crash, kết luận sẽ thiếu dữ kiện.

## 23. Quy trình phân tích một history nghi ngờ vi phạm SC

Một cách làm thủ công:

**Bước 1 — Xác định mô hình đối tượng.** Ban đầu mỗi key có giá trị gì? Có read/write/transaction nào chưa ghi vào history không?

**Bước 2 — Giữ thứ tự chương trình.** Vẽ mũi tên giữa thao tác liên tiếp của mỗi client.

**Bước 3 — Dùng giá trị read tạo quan hệ.** Nếu `R(x)=1` và chỉ `W(x=1)` tạo giá trị đó, write phải ở trước read trong thứ tự chung. Nếu `R(x)=0` và chưa có write đưa về 0, read phải đứng trước write đầu tiên đổi x từ 0.

**Bước 4 — Tìm một thứ tự toàn phần.** Có thể thử đan xen các chuỗi thao tác của từng client trong khi kiểm tra kết quả read.

**Bước 5 — Nếu ràng buộc tạo chu trình, kết luận không có witness.** Ví dụ message passing hoặc store buffering.

**Bước 6 — Nếu tìm được witness, history đó chưa chứng minh vi phạm SC.** Có thể vẫn không linearizable hoặc sai nghiệp vụ.

**Bước 7 — Tách vấn đề consistency khỏi permission/durability.** Một read cũ của client khác sau ACK có thể hợp lệ theo SC nhưng không được phép theo SLA của sản phẩm; một giao dịch không atomic cần transaction, không phải chỉ global ordering.

**Bước 8 — Xác minh cấu hình API thật.** Reader có đang lấy từ secondary/GSI/cache? Có read concern hay session token? Có bao nhiêu shard và replica? Khác biệt này quyết định hệ đang thực tế cam kết điều gì.

## 24. Những hiểu nhầm dễ gặp

| Nhận định sai | Điều cần hiểu đúng |
|---|---|
| “Sequential = mọi thao tác theo đúng đồng hồ” | SC giữ program order và một lịch sử chung, **không bắt buộc real-time order xuyên client** |
| “Có một global write log thì chắc chắn SC” | Các read cũng phải tương thích một thứ tự tuần tự hợp lệ |
| “Hai replica đọc hai phiên bản khác nhau tức là vi phạm SC” | Có thể hợp lệ nếu các read xếp được vào cùng lịch sử |
| “Đọc cũ sau ACK của client khác chắc chắn vi phạm SC” | Đây là ranh giới phân biệt với linearizability |
| “Read-your-writes là đủ cho SC” | Session guarantee đơn lẻ không tạo total order xuyên client/key |
| “Mỗi key có thứ tự riêng thì toàn hệ SC” | Sequential consistency **không compositional** |
| “Per-key linearizability không thể ghép thành linearizable system” | Với các object độc lập, **linearizability có tính compositional**; nhưng vẫn không tạo atomic multi-key transaction |
| “SC bảo đảm cặp field đổi cùng lúc” | Các thao tác rời vẫn có thể xen kẽ; cần transaction/atomic grouping |
| “SC và serializability giống nhau” | Đơn vị là operation vs transaction |
| “Quorum luôn có nghĩa SC đa key” | CL/write concern không thay thế chứng minh global history |
| “Kafka có thứ tự offset nên toàn hệ SC” | Offset theo partition, không tạo order cho mọi DB/API |
| “Sticky session đủ bảo đảm SC” | Chỉ giúp một số session guarantees, không tự điều phối mọi replica |
| “Mọi datastore NoSQL luôn eventual consistency” | Bảo đảm phụ thuộc API, cấu hình, phạm vi và topology |
| “SC nghĩa là dữ liệu không bao giờ mất” | Durability là khía cạnh khác |
| “Thứ tự quan sát chung nghĩa là mọi UI thấy ngay cập nhật” | Không có latency bound trong định nghĩa SC |
| “Một lần test không thấy lỗi chứng minh SC” | Cần stress lịch sử nhiều client, cross-key, failover, routing |

## 25. Bài tập thực hành

### Bài 1 — SC hay không?

Ban đầu `x=0`. A thực hiện `W(x=1)`. B thực hiện `R(x)=0`, sau đó `R(x)=1`. Không có thao tác nào khác. Có thể xây một thứ tự tuần tự hợp lệ không? Viết thứ tự ấy.

*Gợi ý:* B đọc 0, A ghi 1, B đọc 1.

### Bài 2 — SC nhưng không linearizable?

A ghi `x=1` và nhận ACK lúc 10:00:01. B bắt đầu đọc lúc 10:00:02 và trả `0`. Không có write khác. Tại sao chỉ tình huống này chưa đủ bác bỏ SC nhưng lại bác bỏ linearizability?

### Bài 3 — Program order

Cùng client A ghi `x=1`, nhận ACK rồi đọc `x=0`; không có write khác. History có SC không? Nếu hai thao tác được gửi đồng thời từ hai thread khác nhau, bạn còn có thể tự áp quan hệ thứ tự chương trình như trước không?

### Bài 4 — Message passing

Writer ghi `payload=1` rồi `flag=1`. Reader đọc `flag=1` rồi `payload=0`. Hãy vẽ bốn thao tác, tạo các ràng buộc và chứng minh chu trình.

### Bài 5 — Store buffering

P1 ghi x=1, đọc y=0. P2 ghi y=1, đọc x=0. Ban đầu x=y=0. Kết quả này có thể giải thích bằng SC không? Thử tạo một thứ tự và chỉ ra chỗ mâu thuẫn.

### Bài 6 — IRIW và compositionality

P1 ghi x=1, P2 ghi y=1. P3 đọc x=1 rồi y=0. P4 đọc y=1 rồi x=0. Vì sao mỗi key riêng có thể trông hợp lệ dưới một thứ tự riêng nhưng tổng history lại không SC? So sánh với tính compositional của linearizability.

### Bài 7 — Atomic transaction

P1 ghi `balanceA=90` rồi `balanceB=110` bằng hai update riêng. P2 đọc `90` và `100`. Có mâu thuẫn với SC không? Nếu nghiệp vụ yêu cầu tổng tài sản nhất quán như một lần chuyển tiền, cần thêm gì?

### Bài 8 — Read barrier

Client đã thấy log position 105 nhưng được chuyển tới replica chỉ apply tới 103. Nêu hai cách giảm khả năng read regression và giải thích vì sao sticky session hoặc token chỉ cho từng session chưa tự chứng minh global SC.

### Bài 9 — Kafka partitions

Event `OrderSubmitted` nằm trong partition 0, `PaymentConfirmed` trong partition 1. Có thể dựa trên offset để khẳng định một total order giữa hai event không? Khi nào nên đồng tuyến theo aggregate hoặc dùng workflow coordinator?

### Bài 10 — Thiết kế phép đo

Hãy thiết kế một test NoSQL với bốn client, hai key, recorder ghi `clientId`/`programSequence`, giá trị read, timestamp và replica được truy cập. Cần dùng trường nào để kiểm tra SC, trường nào thêm vào để kiểm tra linearizability?

### Bài 11 — Chọn consistency theo nghiệp vụ

Phân tích ba API: xem catalog search, xác nhận đơn hàng, thu hồi quyền đọc. API nào được chấp nhận stale read theo SLA? API nào phải dùng authoritative check? Có nên yêu cầu global SC cho toàn hệ hay chỉ cho những aggregate cần giữ bất biến?

### Bài 12 — Đọc lịch sử dưới nhiều mô hình

Một hệ thỏa SC nhưng cho B đọc giá trị cũ sau ACK của A. Hệ có thể vẫn đạt causal consistency không? Có linearizable không? Nếu các replica cuối cùng hội tụ, sự hội tụ ấy có làm hai mô hình SC/linearizability trở nên giống nhau không? Hãy giải thích theo thứ tự, thời gian thực và tiến triển.

## 26. Tổng kết

**Sequential consistency** là yêu cầu tồn tại một **thứ tự tuần tự chung của các thao tác**, giữ nguyên **program order của từng process/client**, sao cho mọi kết quả đọc hợp lệ theo thứ tự đó. Đây là một định nghĩa về **những lịch sử được phép quan sát**.

Những điểm quan trọng nhất:

1. **Một global order, không nhất thiết cùng wall-clock order.** SC khác linearizability ở việc không bắt buộc giữ thời gian thực giữa các thao tác của những client khác nhau.
2. **Kết quả đọc cũng tham gia thứ tự chung.** Chỉ sắp tất cả write vào một log không tự đủ nếu replica phục vụ read từ những trạng thái không tương thích.
3. **Program order là ranh giới cứng.** Cùng client viết rồi đọc không thể tùy tiện quay về trạng thái trước write nếu không có thao tác khác hợp lệ giải thích.
4. **Các litmus test chứng minh bằng chu trình.** Message passing, store buffering và IRIW phơi bày những lịch sử không thể có sequential order.
5. **Phạm vi bảo đảm phải được xác định.** Một key, một partition, session hay toàn bộ hệ gồm nhiều key là những phạm vi khác nhau; SC không nói rằng nhóm nhiều key có transaction atomic.
6. **Không đồng nhất các mô hình nhất quán.** Causal bảo vệ quan hệ nhân quả, eventual nói về hội tụ, serializability nói về transaction, linearizability thêm real-time ordering.
7. **NoSQL cần xét đúng API/topology.** Primary/replica, GSI, cache, search, quorum, CDC và cross-partition routing có thể mang những consistency semantics khác nhau.

Khi thiết kế hoặc kiểm thử hệ NoSQL, thay vì chỉ hỏi **“replica nào đang có dữ liệu mới nhất?”**, hãy hỏi:

> “Có thể sắp tất cả thao tác đã quan sát thành **một lịch sử tuần tự hợp lệ**, giữ thứ tự chương trình của từng client không? Nếu sản phẩm còn cần đọc sau ACK của client khác phải thấy dữ liệu mới, ta có đang yêu cầu **linearizability** thay vì chỉ SC không?”

Trả lời được hai câu hỏi này giúp xác định chính xác mức nhất quán cần thiết, chọn đúng đường đọc/ghi và tránh dùng một nhãn “strong consistency” mơ hồ cho cả hệ phân tán.
