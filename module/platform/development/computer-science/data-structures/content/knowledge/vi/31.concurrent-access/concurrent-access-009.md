# Phân biệt blocking, lock-free và wait-free

Khi nhiều luồng cùng sử dụng một cấu trúc dữ liệu, có hai câu hỏi cần tách biệt: **kết quả có đúng không?** và **mỗi thao tác có cơ hội hoàn thành như thế nào khi các luồng tranh chấp hoặc bị tạm dừng?** Một hàng đợi có thể trả phần tử theo đúng thứ tự FIFO nhưng vẫn khiến luồng đọc chờ vô hạn nếu luồng giữ khóa bị treo. Ngược lại, dùng lệnh nguyên tử `compare-and-set` (CAS) không tự động bảo đảm mọi luồng đều hoàn tất.

Trong chương **Truy cập đồng thời** của môn cấu trúc dữ liệu, ba thuật ngữ **blocking**, **lock-free** và **wait-free** mô tả các **bảo đảm về tiến triển** (*progress guarantees*) của thuật toán đồng thời. Chúng giúp lựa chọn cách cài đặt stack, queue, bộ đếm, bảng băm, cây và các cấu trúc chia sẻ giữa nhiều luồng, bên cạnh các tiêu chí bất biến và độ phức tạp thời gian, bộ nhớ.

## 1. Tính đúng đắn và khả năng tiến triển là hai vấn đề khác nhau

Một cấu trúc dữ liệu đồng thời cần xác định rõ:

- **Tính an toàn (safety):** điều gì không được phép xảy ra, chẳng hạn mất phần tử, đọc trạng thái chưa hoàn tất hoặc làm sai bất biến của cây.
- **Tính nhất quán của thao tác:** mỗi `push`, `pop` hoặc `enqueue` có thể được xem là xảy ra tại một thời điểm đơn lẻ hay không. Tính chất phổ biến là **linearizability** (tuyến tính hóa), trong đó thao tác dường như có hiệu lực nguyên tử tại một điểm từ lúc gọi đến lúc trả kết quả.
- **Tính sống/tiến triển (liveness/progress):** dưới điều kiện chạy cụ thể, thuật toán có bảo đảm một thao tác hay ít nhất một thao tác nào đó hoàn thành không?

**Linearizability không kéo theo lock-free hoặc wait-free.** Ví dụ, một stack có `synchronized` bảo vệ toàn bộ `push`/`pop` có thể tuyến tính hóa chính xác nhưng vẫn chặn các luồng khác trong lúc chủ khóa chưa được chạy tiếp.

Ngược lại, một đoạn mã dùng CAS vẫn có thể sai tính an toàn nếu liên tục sửa con trỏ sai, làm mất cập nhật, hoặc thu hồi nút mà luồng khác đang dùng. Bởi vậy, khi đọc tài liệu về cấu trúc đồng thời, cần xem **bảo đảm tiến triển** và **bằng chứng đúng đắn** là hai yêu cầu riêng biệt.

## 2. Blocking: tiến triển có thể phụ thuộc vào luồng khác

**Blocking** nghĩa là có thao tác có thể phải chờ một luồng khác thực hiện một hành động cần thiết: nhả mutex, phát tín hiệu điều kiện, giải phóng semaphore hoặc hoàn thành một vùng tới hạn.

Ví dụ với stack dùng khóa:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class BlockingStack<T> {
    private final Deque<T> data = new ArrayDeque<>();

    public synchronized void push(T value) {
        data.push(value);
    }

    public synchronized T pop() {
        return data.pop();
    }
}
```

Giả sử luồng A vừa vào `push` và đang giữ monitor của đối tượng. Nếu A bị hệ điều hành tạm dừng ngay lúc đó, luồng B gọi `pop` có thể phải chờ cho đến khi A tiếp tục và rời vùng `synchronized`. B không tự hoàn thành được bằng cách chạy thêm các bước của chính mình.

Đặc điểm thực tế của thuật toán blocking:

- Khóa giúp tạo vùng tới hạn rõ ràng, thường dễ cài đặt các thay đổi nhiều bước và duy trì bất biến.
- Có thể gặp **deadlock** nếu các luồng giữ nhiều khóa và chờ nhau theo vòng; có thể gặp **starvation** nếu một luồng liên tục không giành được khóa.
- **Blocking không đồng nghĩa chậm.** Khóa có thể rất hiệu quả nếu tranh chấp thấp và vùng tới hạn ngắn. Ngược lại, lệnh nguyên tử liên tục thử lại có thể tiêu tốn CPU đáng kể.
- **Blocking cũng không đồng nghĩa luôn deadlock.** Một cách dùng khóa đúng vẫn có thể chạy tốt trong thực tế; khác biệt nằm ở bảo đảm tiến triển trong tình huống xấu.

## 3. Lock-free: toàn hệ thống vẫn có tiến triển

Một thuật toán **lock-free** bảo đảm rằng khi có các luồng tiếp tục thực thi các bước của thuật toán, **hệ thống không thể liên tục thực hiện các bước mà không có thao tác nào hoàn thành**. Nói cách khác, trong quá trình thực thi đang có hoạt động, luôn có tiến triển của **ít nhất một** thao tác; một luồng cụ thể vẫn có thể phải thử lại vô hạn.

Điều kiện trọng tâm của lock-free là **tiến triển của hệ thống**, không phải tiến triển của mọi luồng. Khi một luồng bị dừng giữa chừng, các luồng khác vẫn có thể hoàn thành thao tác độc lập, với điều kiện thuật toán và các primitive nền không bắt chúng phải chờ luồng đó.

Một mẫu phổ biến là vòng lặp CAS:

```text
repeat:
    old = atomic_load(shared)
    new = transform(old)            // xử lý trên dữ liệu riêng
until compare_and_set(shared, old, new) succeeds
return
```

Nếu CAS thất bại vì tham chiếu `shared` đã đổi từ `old` sang giá trị khác, trong thiết kế thích hợp điều này thường cho thấy **một thao tác cập nhật khác đã thành công**. Luồng thất bại có thể làm lại công việc, nhưng toàn hệ thống vừa tiến thêm một bước hữu ích.

Cần phân biệt hai trường hợp:

1. **Một luồng liên tục thất bại, luồng khác liên tục thành công:** thuật toán có thể vẫn lock-free vì hệ thống tiến triển.
2. **Không luồng nào thành công vì cùng phải đợi một luồng đang dừng:** thuật toán này không thỏa bảo đảm lock-free chỉ nhờ có chứa CAS.

Vì vậy, việc **không khai báo mutex**, **không có `synchronized`** hoặc **có dùng CAS** chưa đủ để chứng minh thuật toán lock-free. Phải xét cả giao thức phối hợp và những điểm có thể chờ.

## 4. Wait-free: mỗi thao tác có bảo đảm tiến triển

Một thuật toán **wait-free** bảo đảm **mỗi lần gọi thao tác** hoàn thành sau **một số hữu hạn bước do chính luồng đó thực hiện**, bất kể tốc độ và cách xen kẽ bước chạy của những luồng khác. Giới hạn số bước có thể phụ thuộc vào số luồng tham gia, kích thước đầu vào hoặc tham số cấu trúc, nhưng không được tăng vô hạn chỉ vì các luồng khác liên tục chen vào.

Ví dụ đơn giản ở mô hình thanh ghi nguyên tử là một ô giá trị có **một luồng ghi, nhiều luồng đọc**. Mỗi lượt đọc chỉ cần một phép tải nguyên tử và mỗi lượt ghi chỉ cần một phép lưu nguyên tử:

```java
// Minh họa một thanh ghi đơn, không phải bộ đếm read-modify-write.
public final class SingleWriterRegister {
    private volatile int value;

    // Chỉ một luồng được quyền gọi write.
    public void write(int next) {
        value = next;
    }

    public int read() {
        return value;
    }
}
```

Ở **mức thuật toán trừu tượng**, một thao tác `read`/`write` của thanh ghi có số bước xác định, không có vòng lặp phụ thuộc vào tranh chấp và không cần đợi một luồng khác rời vùng tới hạn; đó là ví dụ trực quan về wait-free. Phần triển khai thực tế trên JVM còn chịu tác động của cơ chế runtime và lịch CPU; `volatile` không biến mọi phép tính trên giá trị này thành wait-free.

Đặc biệt, lệnh `value++` gồm đọc, tính toán và ghi, **không phải** phép tăng nguyên tử an toàn khi nhiều luồng cùng cập nhật. Từ một thanh ghi wait-free không thể suy ra một phép tăng dùng chung cũng tự động wait-free.

**Wait-free mạnh hơn lock-free:** nếu mỗi thao tác hoạt động đều hoàn thành sau hữu hạn bước riêng của nó, thì toàn hệ thống cũng có tiến triển. Chiều ngược lại không đúng.

### “Wait-free” không có nghĩa là không bao giờ bị hệ điều hành tạm dừng

Bảo đảm wait-free được phát biểu theo **số bước của thuật toán**, dưới giả định luồng có cơ hội tiếp tục thực hiện bước. Nếu hệ điều hành không cấp CPU cho một luồng, lời gọi của luồng ấy có thể chưa trả kết quả dù thuật toán là wait-free. Tính wait-free cũng không tự hứa hẹn giới hạn thời gian thực (ví dụ luôn dưới 10 µs): thời gian còn phụ thuộc lịch CPU, thời gian truy cập bộ nhớ, garbage collection, độ dài đầu vào và nền tảng.

Trong thực hành, đôi khi cần nói chính xác hơn **bounded wait-free** khi chỉ ra một cận số bước tường minh. Một thuật toán không thể được chứng minh wait-free chỉ bằng đo benchmark thấy không có lần chờ lâu.

## 5. Bảng so sánh các mức bảo đảm

| Tiêu chí | Blocking | Lock-free | Wait-free |
| --- | --- | --- | --- |
| Thao tác có thể phụ thuộc vào việc luồng khác tiếp tục chạy? | **Có** | Không phải chờ luồng khác giải phóng khóa, theo bảo đảm của thuật toán | Không cần luồng khác chạy để hoàn tất số bước riêng hữu hạn |
| Ai được bảo đảm tiến triển khi có tranh chấp? | Không có bảo đảm chung nếu chủ khóa dừng | **Ít nhất một thao tác** của hệ thống | **Mọi thao tác** đang thực thi |
| Một luồng cụ thể có thể thử lại vô hạn? | Có thể chờ vô hạn | **Có** | **Không**, nếu được cấp các bước thực thi cần thiết |
| Dùng khóa mutex? | Thường có, nhưng không bắt buộc | Không dựa vào khóa chặn để tiến triển | Không dựa vào khóa chặn để tiến triển |
| Ví dụ điển hình | Stack với `synchronized`, queue có mutex | Stack Treiber dùng CAS, theo giả định primitive phù hợp | Đọc/ghi một thanh ghi nguyên tử đơn giản |
| Trọng tâm khi phân tích | Tranh chấp, deadlock, thời gian giữ khóa | Tiến triển toàn hệ thống, tranh chấp CAS, retry | Cận số bước cho từng thao tác, chi phí để bảo đảm cận |

Bảng trên bàn về **bảo đảm của thuật toán**, không phải thứ hạng tốc độ. Một thao tác wait-free có thể có chi phí lớn hơn một thao tác dùng khóa trong điều kiện ít tranh chấp; một cấu trúc lock-free cũng có thể tạo nhiều phép thử lại và truy cập bộ nhớ.

### Mức trung gian: obstruction-free

Thuật toán **obstruction-free** chỉ cần bảo đảm một thao tác hoàn thành **nếu luồng thực hiện thao tác đó cuối cùng được chạy một mình đủ lâu**, không bị luồng khác can thiệp vào trạng thái liên quan. Khi các luồng tranh chấp không ngừng, tất cả có thể liên tục làm hỏng tiến độ của nhau, nên obstruction-free **không nhất thiết lock-free**.

Theo thứ tự bảo đảm (với các giả định mô hình đồng nhất):

```text
wait-free  =>  lock-free  =>  obstruction-free
     (chiều ngược lại không được bảo đảm)
```

Không nên nhầm **deadlock-free** hoặc **starvation-free** trong một mô hình khóa với các mức trên. Một thuật toán sử dụng khóa có thể tránh deadlock nhờ quy tắc thứ tự khóa, nhưng nếu chủ khóa ngừng chạy, luồng khác vẫn bị chặn. Tương tự, sự công bằng của bộ cấp phát khóa dưới giả định lịch chạy công bằng khác với bảo đảm wait-free dựa trên số bước.

## 6. Ví dụ trên một cấu trúc dữ liệu: stack Treiber lock-free

Stack Treiber lưu một tham chiếu nguyên tử `head` trỏ tới nút đầu danh sách liên kết đơn. Mỗi thao tác chuẩn bị thay đổi rồi dùng CAS để cập nhật `head`. Nếu có tranh chấp, thao tác đọc lại `head` và thử lại.

```java
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

public final class TreiberStack<T> {
    private static final class Node<T> {
        final T value;
        final Node<T> next;

        Node(T value, Node<T> next) {
            this.value = value;
            this.next = next;
        }
    }

    private final AtomicReference<Node<T>> head =
            new AtomicReference<>();

    public void push(T value) {
        Objects.requireNonNull(value);

        while (true) {
            Node<T> oldHead = head.get();
            Node<T> newHead = new Node<>(value, oldHead);

            if (head.compareAndSet(oldHead, newHead)) {
                return;
            }
            // Đầu stack đã đổi: tạo lại nút với next mới.
        }
    }

    public Optional<T> pop() {
        while (true) {
            Node<T> oldHead = head.get();

            if (oldHead == null) {
                return Optional.empty();
            }

            Node<T> next = oldHead.next;
            if (head.compareAndSet(oldHead, next)) {
                return Optional.of(oldHead.value);
            }
        }
    }
}
```

**Bất biến của stack:** từ `head` đi theo `next` tới `null` tạo một chuỗi nút hợp lệ; nút được khởi tạo đầy đủ trước khi tham chiếu tới nó được công bố. Các nút là bất biến sau khi tạo, nên luồng khác không thấy trường `next` bị sửa trong lúc duyệt.

**Điểm tuyến tính hóa:** `push` có hiệu lực khi CAS thành công và thay `head` bằng nút mới; `pop` có phần tử khi CAS thành công và bỏ nút đầu khỏi chuỗi. `pop` trả rỗng tuyến tính hóa tại lần quan sát `head == null`. Từ đó có thể đối chiếu với hành vi stack tuần tự LIFO.

**Bảo đảm tiến triển:** giả sử mỗi thao tác đọc/CAS nguyên tử trên `head` hoàn tất mà không phải chờ luồng khác, và các bước phụ trợ như cấp phát nút không chặn vô hạn. Mỗi CAS thành công làm một thao tác hoàn tất. CAS thất bại vì có cập nhật `head` cạnh tranh; khi tiếp tục có thất bại do tranh chấp, có thao tác khác thành công. Đó là cơ sở để coi **thuật toán Treiber lock-free** trong mô hình chuẩn. Nó **không wait-free**, vì một luồng có thể thất bại CAS liên tục.

Trong hệ thống thực, bảo đảm còn phụ thuộc primitive CAS và runtime; garbage collection, page fault hay cấp phát bộ nhớ có thể gây tạm dừng ngoài mô hình tiến triển trừu tượng. Không nên kết luận mọi dòng mã Java chạy không bao giờ chờ chỉ từ tên thuật toán.

### Hai luồng tranh chấp trên cùng stack

Giả sử ban đầu stack là `A -> B`. W1 muốn `pop` và W2 muốn `push(X)`:

| Bước | W1 | W2 |
| --- | --- | --- |
| 1 | Đọc `head = A`, chuẩn bị CAS `A -> B` | Đọc `head = A` |
| 2 | Tạm dừng trước CAS | Tạo `X -> A`, CAS `A -> X` thành công |
| 3 | CAS `A -> B` thất bại vì `head` đang là `X` | Hoàn tất `push(X)` |
| 4 | Đọc lại `head = X`, chuẩn bị `X -> A` | Có thể bắt đầu thao tác khác |
| 5 | CAS thành công nếu không có cập nhật mới | — |

Nếu W2 và các luồng khác liên tục công bố đầu stack mới ngay trước mỗi CAS của W1, W1 có thể thất bại không giới hạn số lần. Dù vậy, các thao tác khác hoàn tất, nên bảo đảm lock-free của toàn hệ thống vẫn được giữ.

### Lưu ý về ABA và thu hồi bộ nhớ

Một lỗi kinh điển trong thuật toán dùng con trỏ là **ABA**: luồng T1 nhìn thấy đầu `A`, tạm dừng; luồng khác thay `A -> B -> A` (tham chiếu trở về đúng `A`), khiến CAS của T1 có thể thành công dù trạng thái logic đã thay đổi. Điều này đặc biệt nguy hiểm khi **tái sử dụng cùng một nút** hoặc thu hồi bộ nhớ thủ công.

Trong mã minh họa, mỗi lần `push` tạo **nút mới**, không đưa lại các đối tượng `Node` đã bị `pop` loại ra; Java GC giúp giữ đối tượng còn đang được tham chiếu. Nhờ các điều kiện đó, trường hợp ABA do **tái sử dụng cùng đối tượng nút** không xuất hiện trong API hiện tại. Nếu thêm tính năng đẩy lại nút cũ hoặc dùng bộ quản lý vùng nhớ thủ công, phải phân tích lại ABA và thu hồi an toàn; giải pháp thường gặp là **tag/version** đi kèm con trỏ, **hazard pointers**, hoặc cơ chế **epoch-based reclamation** phù hợp.

## 7. Khi nào một vòng lặp CAS vẫn không lock-free?

Xét đoạn mã sau:

```text
while shared == BUSY:
    continue
do_work()
```

Nó không gọi `lock()`, nhưng nếu `shared` chỉ có thể đổi khỏi `BUSY` nhờ một luồng khác đang bị dừng, luồng hiện tại vẫn **phụ thuộc vào tiến triển của luồng đó**. Đây về bản chất là **spin lock**, không có bảo đảm lock-free.

Tương tự, giả sử một thuật toán có CAS thành công để đặt cờ `OWNED`, sau đó một luồng phải hoàn tất sửa dữ liệu và gỡ cờ. Các luồng khác chỉ thử đọc cờ cho tới khi nó được xóa. CAS ở đây chỉ dùng để **giành khóa**; nếu chủ cờ bị dừng, hệ thống có thể ngừng tiến triển.

Để đánh giá một thuật toán thật sự lock-free, nên hỏi:

1. Nếu một luồng bị dừng ở bất kỳ điểm nào, các luồng còn lại có thể tiếp tục hoàn tất thao tác không?
2. Nếu một luồng thất bại CAS liên tục, các thất bại đó có gắn với tiến triển thực sự của thao tác khác không?
3. Có chỗ nào phải chờ cờ trạng thái, cấp quyền sở hữu độc quyền hoặc đợi một luồng khác “dọn dẹp” trước khi có thể kết thúc không?
4. Primitive nguyên tử và quản lý bộ nhớ được giả định có những bảo đảm tiến triển gì?

Đôi khi thuật toán lock-free sử dụng kỹ thuật **helping**: một luồng thấy thao tác dang dở của luồng khác có thể giúp hoàn thành nó, để toàn hệ thống không phụ thuộc việc chủ thao tác được chạy tiếp. Việc giúp hoàn thành tác vụ không tự làm thuật toán wait-free; cần chứng minh cận số bước riêng cho từng thao tác.

## 8. Độ phức tạp, độ trễ và bộ nhớ

Độ phức tạp tuần tự như `O(1)` hay `O(log n)` vẫn cần, nhưng chưa đủ khi nhiều luồng tranh chấp. Phải bổ sung số lần retry, chi phí truy cập bộ nhớ dùng chung và cách cấp phát.

| Cấu trúc/thao tác | Không tranh chấp | Khi tranh chấp | Lưu ý |
| --- | --- | --- | --- |
| Stack có khóa, `push/pop` | Thường `O(1)` thời gian thao tác bên trong khóa | Thời gian chờ khóa có thể không bị chặn trên | Khóa bao quanh toàn bộ cập nhật |
| Treiber stack, `push/pop` | Một lần CAS thành công, phần việc chính `O(1)` | Một luồng có thể retry không giới hạn | Lock-free ở mức hệ thống; có chi phí cấp phát nút |
| Đọc/ghi một thanh ghi nguyên tử | Một primitive, `O(1)` | Không có vòng lặp retry do thuật toán | Wait-free ở mô hình thanh ghi |
| Cây cân bằng có khóa chung | Tìm kiếm khoảng `O(log n)` sau khi có khóa | Có thể phải chờ khóa vô hạn | Đơn giản hóa các cập nhật nhiều nút |
| Cây đồng thời lock-free | Tùy thuật toán, thường tìm kiếm theo chiều cao cây | Có thể cần retry hoặc helping | Tiến triển và thu hồi nút khó chứng minh hơn |

**Lock-free không tự có cận độ trễ cho từng lời gọi**: số lần lặp của một luồng có thể vô hạn khi tranh chấp. **Wait-free có cận về số bước** nhưng chi phí mỗi bước trên bộ nhớ và lịch chạy vẫn ảnh hưởng thời gian thực. Với giới hạn thời gian nghiêm ngặt, cần xem xét cả cận thực thi, hệ điều hành, cấp phát, dừng GC và tài nguyên phần cứng.

Ngoài tốc độ, bộ nhớ cũng quan trọng: stack dùng CAS trên danh sách liên kết thường tạo nút riêng cho mỗi `push`; một thuật toán phức tạp hơn có thể cần bộ nhớ trợ giúp cho con trỏ phiên bản hoặc mô tả thao tác. Trong ngôn ngữ không có GC, việc thu hồi nút an toàn khi còn luồng đọc giữ con trỏ có thể quyết định cả thiết kế và bảo đảm tiến triển.

## 9. Cách chọn cho từng bài toán

**Chọn blocking** khi độ đơn giản, khả năng bảo trì và cập nhật nhiều trường là ưu tiên; tranh chấp thấp và thời gian giữ khóa có thể kiểm soát. Ví dụ: bảng băm có ít cập nhật, chỉ một vài luồng chia sẻ trong ứng dụng nghiệp vụ.

**Cân nhắc lock-free** khi việc một luồng chậm hoặc tạm dừng không được làm tắc toàn bộ cấu trúc, và ứng dụng chấp nhận một số luồng phải thử lại. Ví dụ: stack phục vụ nhiều worker, queue truyền việc có thông lượng cao, hoặc bộ đếm/tập hợp thao tác nguyên tử được tổ chức phù hợp.

**Cần wait-free** khi yêu cầu bắt buộc mỗi thao tác phải có giới hạn số bước riêng, chẳng hạn một số đường đi xử lý sự kiện hoặc giao tiếp trên hệ thống thời gian thực. Một cách đạt yêu cầu có thể là thu hẹp chức năng: thanh ghi một writer nhiều reader dễ có bảo đảm mạnh hơn một hàng đợi nhiều producer nhiều consumer. Việc xây dựng queue hay map wait-free tổng quát phức tạp hơn đáng kể.

Ba bước lựa chọn thực dụng:

1. Xác định yêu cầu **an toàn** của cấu trúc (FIFO/LIFO, nhất quán nhiều trường, linearizability nếu cần).
2. Xác định **bảo đảm tiến triển** thực sự cần: chờ khóa có chấp nhận được không, toàn hệ thống phải luôn tiến triển hay từng thao tác phải có cận bước?
3. Đo thử trên tải thực tế và kiểm tra chi phí cấp phát, retry, bộ nhớ, khả năng thu hồi nút cùng các giả định về primitive nguyên tử.

## 10. Câu hỏi tự kiểm tra

**Tình huống A.** Một luồng lấy mutex của queue rồi bị tạm dừng vô hạn. Các luồng còn lại gọi `enqueue` không thể vào vùng tới hạn. Queue thuộc loại nào về bảo đảm tiến triển?

*Đáp án:* Đây là cách cài đặt **blocking**. Dù bất biến FIFO vẫn được bảo vệ, khả năng hoàn thành của các luồng còn lại phụ thuộc chủ khóa tiếp tục và nhả khóa.

**Tình huống B.** Mỗi lần CAS của T1 thất bại vì T2 vừa hoàn tất một lần cập nhật. T1 có thể mãi chưa trả về, còn T2 vẫn tiếp tục hoàn tất. Điều đó có mâu thuẫn với lock-free không?

*Đáp án:* **Không.** Tiến triển toàn hệ thống vẫn có. Nhưng nếu T1 không có cận hữu hạn số bước riêng để hoàn tất, không thể gọi thao tác đó là wait-free.

**Tình huống C.** Một API cho đọc và ghi một số nguyên bằng thao tác nguyên tử đơn lẻ, nhưng nhiều luồng cùng thực hiện `read -> cộng 1 -> write`. Có thể vừa khẳng định wait-free vừa khẳng định tăng chính xác không?

*Đáp án:* Đọc và ghi riêng lẻ có thể wait-free ở mô hình thanh ghi, nhưng chuỗi đọc–sửa–ghi không nguyên tử, nên hai luồng có thể cùng đọc giá trị cũ và làm mất một lần tăng. Bảo đảm tiến triển **không thay thế** tính đúng đắn.

**Tình huống D.** Một stack không dùng mutex, nhưng mỗi luồng phải spin tới khi cờ `owner == 0`; luồng giữ cờ bị tạm dừng. Stack có lock-free không?

*Đáp án:* **Không.** Các luồng còn lại phụ thuộc luồng giữ cờ giải phóng quyền sở hữu. Tên biến hay việc không gọi mutex không quyết định tính lock-free.

**Điểm cần ghi nhớ:** **blocking** có thể yêu cầu đợi luồng khác; **lock-free** bảo đảm hệ thống vẫn có thao tác hoàn tất; **wait-free** bảo đảm từng thao tác hoàn tất sau hữu hạn bước riêng khi được thực thi. Bảo đảm tiến triển cần được chứng minh riêng với bất biến dữ liệu, khả năng tuyến tính hóa và độ phức tạp của cấu trúc.
