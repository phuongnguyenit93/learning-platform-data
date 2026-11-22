# Nhóm offer, poll, peek và kết quả đặc biệt

## 1. Vì sao cần một nhóm thao tác trả kết quả đặc biệt?

Khi xử lý một hàng đợi hai đầu (deque), có những tình huống không thực hiện được thao tác nhưng vẫn hoàn toàn bình thường:

- Nơi tiếp nhận việc đang đầy nên chưa thể nhận thêm.
- Nơi xử lý chưa có phần tử để lấy.
- Mã chỉ muốn xem đầu hàng đợi và chấp nhận việc hiện chưa có dữ liệu.

Thay vì phải dùng ngoại lệ cho mỗi lần gặp các trạng thái ấy, nhóm `offer`, `poll`, `peek` cung cấp kết quả để mã gọi chủ động quyết định bước tiếp theo:

- `offer...` trả `boolean`: có tiếp nhận phần tử hay không.
- `poll...` trả phần tử vừa lấy, hoặc `null` khi rỗng.
- `peek...` trả phần tử được xem, hoặc `null` khi rỗng; nó không xóa phần tử.

“Kết quả đặc biệt” ở đây là một phần của hợp đồng phương thức. Nó không có nghĩa Java đã chuyển mọi loại lỗi thành `false` hoặc `null`.

Ví dụ trong bài dùng API hiện vẫn áp dụng trên Java hiện đại và chạy được với JDK 17 trở lên. Một deque có giới hạn sức chứa được dùng để quan sát rõ trường hợp `offer` trả `false`.

## 2. Đọc tên phương thức theo hành động và đầu được chọn

Deque cho phép thao tác ở hai đầu:

```text
First / đầu trước                         Last / đầu sau
        |                                      |
        v                                      v
      [ A ] ------------ [ B ] ------------ [ C ]
```

Đọc tên phương thức bằng cách tách hai phần:

- `offer`: đề nghị thêm phần tử.
- `poll`: lấy và xóa một phần tử.
- `peek`: xem một phần tử, giữ nguyên dữ liệu.
- `First`: chọn đầu trước.
- `Last`: chọn đầu sau.

Bảng này giúp nhìn cả kết quả lẫn tác động:

| Phương thức | Khi thực hiện được | Khi không có chỗ hoặc đang rỗng | Thay đổi deque? |
| --- | --- | --- | --- |
| `offerFirst(e)` | Thêm đầu trước, trả `true` | Trả `false` nếu bị giới hạn sức chứa và không còn chỗ | Có, nếu thêm được |
| `offerLast(e)` | Thêm đầu sau, trả `true` | Trả `false` nếu bị giới hạn sức chứa và không còn chỗ | Có, nếu thêm được |
| `pollFirst()` | Trả và xóa phần tử đầu trước | `null` nếu rỗng | Có, nếu có phần tử |
| `pollLast()` | Trả và xóa phần tử đầu sau | `null` nếu rỗng | Có, nếu có phần tử |
| `peekFirst()` | Trả phần tử đầu trước | `null` nếu rỗng | Không |
| `peekLast()` | Trả phần tử đầu sau | `null` nếu rỗng | Không |

Đối với cách gọi thừa hưởng từ `Queue`, `offer(e)` tương ứng với `offerLast(e)`, còn `poll()` và `peek()` tương ứng với `pollFirst()` và `peekFirst()`. Tên không có hậu tố không có nghĩa phương thức tự chọn đầu tùy tình huống. [Hợp đồng Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)

Với dãy A, B, C trong hình:

- `peekFirst()` trả A và dãy vẫn là A, B, C.
- `pollFirst()` trả A và dãy còn B, C.
- `pollLast()` trả C và dãy còn A, B.
- `offerFirst("X")`, nếu thành công, tạo X, A, B, C.
- `offerLast("X")`, nếu thành công, tạo A, B, C, X.

Các dòng trên là các tình huống độc lập, đều bắt đầu từ cùng dãy ban đầu.

## 3. offer: kết quả tiếp nhận không phải kết quả xử lý

### true nghĩa là đã thêm được

Nếu `offerLast(job)` trả `true`, lời gọi đã thêm phần tử vào đầu sau theo hợp đồng triển khai. Nó không khẳng định công việc đã được xử lý, đã ghi ra cơ sở dữ liệu hoặc được giữ bền vững sau khi chương trình dừng.

Có thể hình dung ba mốc khác nhau:

```text
Đề nghị tiếp nhận -> Đã vào deque -> Được lấy ra -> Xử lý nghiệp vụ
                         ^
                         |
              offer trả true xác nhận mốc này
```

Nếu phần tử là một đối tượng có thể thay đổi, việc thêm nó vào deque không tự sao chép toàn bộ đối tượng. Cần quản lý việc sửa dữ liệu nếu nhiều phần mã cùng giữ tham chiếu đến nó.

### false nghĩa là lần đề nghị này không thêm được vì không còn sức chứa

Trong một deque có giới hạn, ví dụ sức chứa 2 đang chứa A và B, `offerFirst("URGENT")` trả `false`. Phần tử URGENT không được tự động giữ ở nơi khác và deque không tự bỏ A hoặc B để nhường chỗ.

Mã gọi phải quyết định chính sách:

- Báo từ chối cho nơi gửi.
- Giữ lại ở một cơ chế khác đã được thiết kế.
- Chờ hoặc thử lại theo điều kiện rõ ràng.
- Bỏ qua nếu nghiệp vụ cho phép và có cách ghi nhận phù hợp.

Bỏ qua giá trị trả về có thể làm chương trình đánh mất một yêu cầu mà không báo gì. Cũng không nên lặp `offer` liên tục không có khoảng chờ hay giới hạn, vì dễ tạo vòng lặp chiếm tài nguyên khi bên xử lý đang chậm.

### Không phải deque nào cũng có một mức “đầy” cấu hình được

`ArrayDeque` tăng kích thước khi cần; đối số dung lượng khởi tạo không đặt sức chứa tối đa. Vì vậy, dùng `new ArrayDeque<>(2)` không tạo một hàng đợi chỉ nhận tối đa hai phần tử.

Ngược lại, `new LinkedBlockingDeque<>(2)` tạo deque có sức chứa cố định là 2. Bài chọn lớp này để minh họa kết quả từ chối do đầy. Đây là đặc điểm của triển khai, không phải điều suy ra từ mọi biến kiểu `Deque`. [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html), [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

Khả năng tăng kích thước không đồng nghĩa bộ nhớ vô hạn. Nếu nghiệp vụ cần kiểm soát tồn đọng, phải có thiết kế sức chứa và tiếp nhận rõ ràng, thay vì dựa vào việc chưa nhìn thấy `false` khi thử vài phần tử.

## 4. poll: lấy dữ liệu và diễn đạt trạng thái rỗng

`pollFirst()` có hai kết quả nghiệp vụ khác nhau:

```text
Có phần tử: trả phần tử, đồng thời xóa nó
Đang rỗng: trả null, không có phần tử để xóa
```

Ví dụ minh họa trong một phương thức, với `pending` là `Deque<String>` không chứa `null`:

```java
String job = pending.pollFirst();
if (job == null) {
    System.out.println("Chua co viec");
} else {
    System.out.println("Xu ly " + job);
}
```

Điều quan trọng là dùng chính giá trị đã lấy ra. Nếu gọi `pollFirst()` một lần trong điều kiện rồi gọi lần nữa để xử lý, hai lời gọi có thể lấy hai phần tử khác nhau:

```java
// Minh họa sai: phần tử lấy trong điều kiện bị bỏ đi.
if (pending.pollFirst() != null) {
    String job = pending.pollFirst();
    System.out.println(job);
}
```

Nếu ban đầu chỉ có một việc A, điều kiện lấy mất A, rồi lời gọi trong thân trả `null`. Nếu có A và B, mã bỏ A rồi xử lý B. Lỗi này có thể xảy ra ngay cả khi chỉ có một luồng.

### null chỉ nói về lần quan sát hoặc lấy hiện tại

Kết quả `null` từ `poll` không phải lời tuyên bố rằng nguồn dữ liệu đã kết thúc vĩnh viễn. Một deque đang rỗng có thể được thêm phần tử sau đó.

Với một tập dữ liệu cục bộ đã nạp xong và không còn bên thêm mới, có thể dùng vòng lặp lấy đến khi rỗng. Nhưng với bên sản xuất việc hoạt động đồng thời, muốn xác định “đã hoàn thành toàn bộ” phải có thêm giao thức kết thúc hoặc trạng thái của hệ thống.

### Lấy khỏi deque chưa phải hoàn thành công việc

Sau khi `poll` trả A, A đã bị xóa khỏi deque. Nếu bước xử lý A gặp lỗi, deque không tự đặt A trở lại.

Do đó, yêu cầu thử lại, lưu kết quả, chống xử lý trùng hoặc phục hồi sau sự cố cần có chính sách riêng. Không thể dùng kết quả khác `null` của `poll` làm bằng chứng rằng tác vụ ngoài hệ thống đã thành công.

## 5. peek: quan sát nhưng không giữ chỗ

`peekFirst()` và `peekLast()` không xóa phần tử. Chúng phù hợp khi chỉ muốn xem phần tử sắp được xử lý ở một đầu.

Ví dụ, với A và B:

```text
peekFirst() -> A, deque vẫn [ A, B ]
peekFirst() -> A, deque vẫn [ A, B ]
pollFirst() -> A, deque còn [ B ]
peekFirst() -> B, deque vẫn [ B ]
```

Nếu đặt `peek` vào vòng lặp mà không có bước thay đổi dữ liệu hoặc điều kiện dừng, chương trình có thể in mãi cùng một phần tử.

Cũng không nên dùng `peek` như một thao tác giữ chỗ. Trong môi trường có nhiều bên truy cập, phần tử vừa được nhìn thấy có thể bị bên khác lấy trước lời gọi tiếp theo của mình.

Một trình tự như sau có hai bước riêng:

```text
Bước 1: xem đầu bằng peek
Bước 2: lấy đầu bằng poll
```

Không có bảo đảm chung rằng bước 2 sẽ lấy đúng đối tượng bước 1 đã thấy nếu deque có thể bị thay đổi xen giữa. Nếu mục đích là nhận một phần tử để xử lý, nên lấy trực tiếp bằng thao tác phù hợp và dùng kết quả của lần lấy đó.

Sự khác biệt “quan sát” và “tiêu thụ” quan trọng hơn việc hai phương thức đều trả cùng một kiểu `E`.

## 6. false, null và ngoại lệ là ba loại thông tin khác nhau

Không nên gom chúng thành một khái niệm “lỗi” duy nhất:

| Kết quả hoặc hiện tượng | Ý nghĩa trong các tình huống của bài | Hướng xử lý |
| --- | --- | --- |
| `offer...` trả `false` | Deque có giới hạn hiện không còn chỗ cho lần thêm | Áp dụng chính sách tiếp nhận |
| `poll...` trả `null` | Không lấy được phần tử vì đang rỗng | Xử lý trạng thái chưa có việc |
| `peek...` trả `null` | Không có phần tử để xem | Hiển thị hoặc tiếp tục theo trạng thái rỗng |
| `NullPointerException` khi thêm `null` | Đầu vào vi phạm quy tắc của triển khai cấm `null` | Sửa dữ liệu hoặc cách biểu diễn |
| Lỗi từ bước xử lý sau `poll` | Công việc đã được lấy nhưng xử lý thất bại | Áp dụng chính sách lỗi của nghiệp vụ |

### Vì sao không nên lưu null?

`null` là dấu hiệu rỗng trong hợp đồng `poll` và `peek`. Nếu một triển khai cho phép lưu `null`, giá trị trả về đó gây khó phân biệt giữa “không có phần tử” và “phần tử là null”.

Không nên khẳng định mọi triển khai `Deque` đều cấm `null`; hãy đọc hợp đồng lớp cụ thể. Hai lớp được nhắc trong bài là `ArrayDeque` và `LinkedBlockingDeque` đều cấm nó. Đối với ví dụ và các mẫu xử lý này, giả định rõ rằng deque không chứa `null`.

Nếu nghiệp vụ cần một giá trị đặc biệt, hãy dùng một đối tượng hoặc kiểu trạng thái có ý nghĩa. “Tín hiệu kết thúc” và “hiện chưa có việc” nên được biểu diễn khác nhau.

### Nhóm trả kết quả đặc biệt không miễn việc tuân thủ điều kiện đầu vào

`offer` chỉ diễn đạt một số tình huống thất bại bằng `false`, không thay thế toàn bộ hợp đồng phương thức. Không nên viết một khối bắt mọi ngoại lệ rồi đổi thành `false`, vì cách đó che khuất sự khác nhau giữa đầy, đầu vào sai và lỗi lập trình. [Quy tắc thêm và trạng thái rỗng của Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html)

## 7. Chương trình hoàn chỉnh: quan sát đủ true, false và null

Ví dụ dùng `LinkedBlockingDeque` với sức chứa 2. Dù lớp này hỗ trợ thêm các thao tác chặn chờ, chương trình chỉ dùng các phương thức cơ bản không chờ điều kiện đầy hoặc rỗng thay đổi. Nó chạy trong một luồng để stdout xác định.

Lưu tệp `OfferPollPeekDemo.java`:

```java
import java.util.Deque;
import java.util.concurrent.LinkedBlockingDeque;

public class OfferPollPeekDemo {
    public static void main(String[] args) {
        Deque<String> pending = new LinkedBlockingDeque<>(2);

        System.out.println("offerA=" + pending.offerLast("A"));
        System.out.println("offerB=" + pending.offerLast("B"));
        System.out.println("offerUrgent=" + pending.offerFirst("URGENT"));
        System.out.println("afterRejectedOffer=" + pending.size());

        System.out.println("peekFirst=" + pending.peekFirst());
        System.out.println("peekLast=" + pending.peekLast());
        System.out.println("afterPeek=" + pending.size());

        System.out.println("pollFirst=" + pending.pollFirst());
        System.out.println("pollLast=" + pending.pollLast());
        System.out.println("peekEmpty=" + pending.peekFirst());
        System.out.println("pollEmpty=" + pending.pollLast());

        System.out.println("offerC=" + pending.offerFirst("C"));
        System.out.println("peekC=" + pending.peekFirst());
        System.out.println("pollC=" + pending.pollFirst());

        try {
            pending.offerLast(null);
        } catch (NullPointerException e) {
            System.out.println("offerNull=" + e.getClass().getSimpleName());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 OfferPollPeekDemo.java
java OfferPollPeekDemo
```

Stdout:

```text
offerA=true
offerB=true
offerUrgent=false
afterRejectedOffer=2
peekFirst=A
peekLast=B
afterPeek=2
pollFirst=A
pollLast=B
peekEmpty=null
pollEmpty=null
offerC=true
peekC=C
pollC=C
offerNull=NullPointerException
```

### Theo dõi trạng thái để hiểu kết quả

| Sau bước | Nội dung từ First đến Last |
| --- | --- |
| Tạo deque | Rỗng |
| `offerLast("A")` | A |
| `offerLast("B")` | A, B |
| `offerFirst("URGENT")` trả `false` | A, B |
| Hai lần `peek` | A, B |
| `pollFirst()` | B |
| `pollLast()` | Rỗng |
| Hai lời gọi trên deque rỗng | Rỗng |
| `offerFirst("C")` | C |
| `peekFirst()` | C |
| `pollFirst()` | Rỗng |
| Thử thêm `null` gây ngoại lệ | Rỗng |

Ba điểm cần kiểm tra bằng cách đọc cả stdout lẫn trạng thái:

1. URGENT không được tiếp nhận; việc gọi `offerFirst` không có quyền vượt sức chứa.
2. Hai lần `peek` không làm giảm kích thước.
3. Ngoại lệ khi thêm `null` khác hoàn toàn với `false` do đầy.

Việc bắt `NullPointerException` trong ví dụ chỉ nhằm quan sát quy tắc. Trong mã ứng dụng, nên ngăn giá trị không hợp lệ trước khi gọi thay vì dùng ngoại lệ này làm nhánh xử lý bình thường.

## 8. Phân biệt với các phương thức báo bằng ngoại lệ

Các tên tương ứng giúp diễn đạt kỳ vọng của thuật toán:

| Nhu cầu | Dạng kết quả đặc biệt | Dạng báo bằng ngoại lệ |
| --- | --- | --- |
| Thêm đầu trước khi có thể đầy | `offerFirst(e)` | `addFirst(e)` |
| Thêm đầu sau khi có thể đầy | `offerLast(e)` | `addLast(e)` |
| Lấy đầu trước khi có thể rỗng | `pollFirst()` | `removeFirst()` |
| Lấy đầu sau khi có thể rỗng | `pollLast()` | `removeLast()` |
| Xem đầu trước khi có thể rỗng | `peekFirst()` | `getFirst()` |
| Xem đầu sau khi có thể rỗng | `peekLast()` | `getLast()` |

Khi rỗng, các dạng `remove...` và `get...` trong bảng ném `NoSuchElementException`. Với `LinkedBlockingDeque` đã đầy, `addFirst` hoặc `addLast` ném `IllegalStateException` thay vì trả `false`.

Chọn `poll` khi rỗng là trạng thái cần xử lý như bình thường. Chọn `remove` nếu điều kiện của thuật toán yêu cầu phải có phần tử và muốn nhận báo lỗi khi điều kiện ấy bị vi phạm.

Cả hai cách vẫn cần xử lý đúng ngữ nghĩa. Dùng `poll` rồi truy cập ngay phương thức của kết quả mà không kiểm tra `null` chỉ đẩy lỗi sang dòng tiếp theo; nó không làm thuật toán trở nên an toàn hơn.

Tương tự, bỏ qua `false` của `offer` có thể nguy hiểm hơn một ngoại lệ rõ ràng, bởi nơi gửi tưởng công việc đã được nhận.

## 9. Không nhầm phương thức cơ bản với phương thức chặn chờ

Một lớp thuộc nhóm `BlockingDeque` có thể cung cấp nhiều dạng thao tác:

- Các dạng cơ bản như `offerFirst(e)`, `pollFirst()` báo kết quả mà không chờ điều kiện có chỗ hoặc có phần tử xuất hiện.
- Các dạng như `putFirst` và `takeFirst` có thể chờ điều kiện.
- Các dạng nhận thời hạn có thể chờ tối đa trong giới hạn được cung cấp.

Đây là các hợp đồng riêng. Từ “Blocking” trong tên lớp không làm mọi lời gọi `poll` hoặc `offer` tự động chờ. “Không chờ điều kiện” cũng không phải một cam kết rằng mã hoàn toàn không dùng khóa hoặc có thời gian chạy cố định. [Các nhóm thao tác BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Bài không dùng thao tác chặn chờ vì mục đích là nhìn rõ giá trị đặc biệt. Nếu một hệ thống cần đợi việc mới, thời hạn, hủy hoặc dừng luồng, phải thiết kế thêm giao thức ấy thay vì liên tục gọi `poll` trong một vòng lặp trống.

## 10. Các mẫu sử dụng và giới hạn cần nhớ

### Lấy một lần rồi kiểm tra chính kết quả đó

Mẫu này tránh làm mất phần tử do gọi hai lần:

```java
// Minh họa: pending không chứa null.
String job = pending.pollFirst();
if (job != null) {
    process(job);
}
```

`process` ở đây đại diện cho bước xử lý của ứng dụng, không phải một phương thức chuẩn của Java. Đoạn mã là mẫu sử dụng, không phải chương trình độc lập.

### Tiêu thụ dữ liệu đã nạp xong trong một luồng

```java
// Minh họa: không có bên thêm mới; pending không chứa null.
String job;
while ((job = pending.pollFirst()) != null) {
    process(job);
}
```

Điều kiện “không có bên thêm mới” làm cho rỗng trở thành dấu hiệu kết thúc đợt dữ liệu này. Không tự áp dụng cách suy luận đó cho một nguồn liên tục có công việc mới.

### Dùng kết quả offer thay vì kiểm tra kích thước rồi thêm

Nếu có nhiều bên cùng thêm, một phép kiểm tra “còn chỗ” có thể không còn đúng khi đến bước thêm. Hãy dùng kết quả của chính thao tác tiếp nhận trên triển khai đồng thời phù hợp.

Việc mỗi lời gọi là an toàn khi dùng một triển khai đồng thời không biến mọi chuỗi thao tác thành một giao dịch. `peek` rồi `poll`, hay kiểm tra kích thước rồi `offer`, vẫn là những bước riêng.

Đối với `ArrayDeque`, trước hết còn phải giải quyết việc chia sẻ giữa các luồng; không thể chỉ thay vòng lặp rồi coi đối tượng đã an toàn.

## 11. Tự kiểm tra bằng các tình huống biên

### Tình huống 1: đầy rồi thêm đầu

Deque sức chứa 1 đang chứa A. Gọi `offerFirst("B")`.

Kết quả là `false`, nội dung vẫn là A. Không có thao tác tự loại bỏ phần tử cuối để nhận B.

### Tình huống 2: xem hai lần rồi lấy

Deque chứa A, B. Gọi lần lượt `peekLast()`, `peekLast()`, `pollLast()`.

Cả ba lần trả B, nhưng chỉ lần cuối thay đổi deque. Sau đó deque còn A.

### Tình huống 3: rỗng rồi được bổ sung

Deque rỗng nên `pollFirst()` trả `null`. Sau đó một bước khác thêm C thành công.

Lần `pollFirst()` tiếp theo có thể trả C. Kết quả `null` trước đó chỉ phản ánh trạng thái ở lần gọi trước, không khóa deque ở trạng thái rỗng.

### Tình huống 4: bỏ qua kết quả tiếp nhận

Một hàm báo “đã nhận yêu cầu” ngay sau `pending.offerLast(request)` mà không đọc giá trị trả về.

Hãy sửa thiết kế để chỉ báo đã nhận khi lời gọi trả `true`; với `false`, phải thực hiện nhánh từ chối hoặc chính sách đã định. Đồng thời phân biệt việc đã nhận vào bộ nhớ với việc đã xử lý xong.

### Tình huống 5: làm mất công việc sau khi lấy

`pollFirst()` trả A, rồi `process(A)` thất bại.

A không còn trong deque. Cần quyết định cách ghi nhận thất bại và thử lại, thay vì giả định một giá trị khác `null` đã bảo đảm thành công.

Khi đọc hoặc viết mã, hãy luôn xác định ba điều: **thao tác có thay đổi deque không, giá trị đặc biệt có ý nghĩa gì, và bước tiếp theo phải làm gì với kết quả ấy**. Đó là cơ sở để dùng `offer`, `poll`, `peek` đúng cả trong trường hợp có dữ liệu lẫn ở các trạng thái biên.
