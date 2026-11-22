# Nhóm thao tác ném ngoại lệ khi không thực hiện được trong Deque

## 1. Vì sao Deque có một nhóm thao tác báo lỗi bằng ngoại lệ?

Khi thêm, lấy hoặc xem phần tử ở hai đầu deque, có những trạng thái làm thao tác không đạt yêu cầu:

- Muốn thêm vào một deque giới hạn dung lượng nhưng nó đã đầy.
- Muốn lấy hoặc xem phần tử đầu/cuối khi deque đang rỗng.

Deque cung cấp một nhóm phương thức báo các trạng thái đó bằng ngoại lệ. Cách dùng này phù hợp khi nơi gọi yêu cầu thao tác phải thực hiện được và việc không thực hiện được cần được xử lý rõ như một tình trạng lỗi.

Nhóm đối ứng như `offer`, `poll`, `peek` trả false/null cho một số trạng thái thông thường. Đổi nhóm không làm hai đầu deque đổi ý nghĩa; nó đổi **cách báo không đạt yêu cầu**. Xem [Deque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html).

Không hiểu “nhóm ném ngoại lệ” thành mọi phương thức sẽ luôn ném lỗi. Khi điều kiện hợp lệ, chúng thực hiện thao tác và trả về bình thường.

## 2. Sáu phương thức chính và điều kiện gây ngoại lệ

| Mục đích | Ở đầu deque | Ở cuối deque | Trạng thái cần chú ý |
| --- | --- | --- | --- |
| Thêm phần tử | `addFirst(e)` | `addLast(e)` | Hết chỗ trên triển khai có giới hạn dung lượng |
| Lấy và loại phần tử | `removeFirst()` | `removeLast()` | Deque rỗng |
| Xem nhưng không loại phần tử | `getFirst()` | `getLast()` | Deque rỗng |

Cách báo chính:

- `addFirst/addLast`: ném `IllegalStateException` nếu không thêm được vì không còn dung lượng.
- `removeFirst/removeLast`: ném `NoSuchElementException` khi không có phần tử để lấy.
- `getFirst/getLast`: cũng ném `NoSuchElementException` khi không có phần tử để xem.

Kiểu trả về cũng khác nhau:

```text
addFirst/addLast    → void
removeFirst/Last    → phần tử đã lấy
getFirst/Last       → phần tử đang ở đầu/cuối, deque không đổi
```

Không viết `if (deque.addLast(value))`, vì `addLast` không trả boolean. Nếu cần biết bằng true/false việc thêm có thực hiện được ngay không, chọn phương thức offer tương ứng và kiểm tra kết quả của nó.

## 3. Phân biệt đầy, rỗng và phần tử không hợp lệ

Ba trường hợp không nên bị gộp chung:

| Nguyên nhân | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Trạng thái dung lượng | Thêm vào deque giới hạn 2 phần tử khi đã có đủ 2 | Giải phóng chỗ, từ chối yêu cầu hoặc chọn chính sách chờ/thử khác |
| Không có phần tử | Gọi removeFirst trên deque rỗng | Kiểm tra giả định của thuật toán hoặc dùng poll nếu rỗng là trường hợp bình thường |
| Phần tử vi phạm hợp đồng | Thêm null vào ArrayDeque | Sửa/kiểm tra dữ liệu đầu vào; chờ thêm chỗ không giải quyết được |

`NoSuchElementException` biểu thị phần tử được yêu cầu không tồn tại; trong các phương thức đầu/cuối ở đây, đó là deque rỗng. Xem [NoSuchElementException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/NoSuchElementException.html).

`IllegalStateException` biểu thị trạng thái không phù hợp với thao tác; với thêm vào deque đã đầy, vấn đề là không còn chỗ tại thời điểm gọi. Nó không có nghĩa đối tượng deque đã hỏng vĩnh viễn. Xem [IllegalStateException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/IllegalStateException.html).

Ngoài các trạng thái chính, phương thức thêm có thể còn từ chối phần tử theo hợp đồng của triển khai. Vì vậy luôn đọc cả mục `Throws`, không chỉ học một loại ngoại lệ rồi bắt mọi lỗi như cùng nguyên nhân.

Không suy ra lỗi bằng thông điệp văn bản của ngoại lệ. Loại ngoại lệ và điều kiện API mới là cơ sở xử lý; thông điệp có thể khác theo triển khai hoặc bản JDK.

## 4. Chọn đúng triển khai để quan sát trường hợp đầy

`ArrayDeque` không có giới hạn sức chứa cố định do người dùng đặt. Khi cần, nó tăng dung lượng để chứa thêm phần tử theo khả năng tài nguyên.

Do đó:

```java
Deque<String> deque = new ArrayDeque<>(2);
```

không có nghĩa chỉ thêm tối đa 2 phần tử. Đoạn này cần các import tương ứng và chỉ minh họa ý nghĩa constructor. Không dùng nó để tạo ca kiểm tra “lần thêm thứ ba phải ném IllegalStateException”.

`ArrayDeque` cũng cấm null và không tự an toàn khi nhiều luồng cùng sửa. Xem [ArrayDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html).

Để có giới hạn rõ trong bài, dùng:

```java
Deque<String> jobs = new LinkedBlockingDeque<>(2);
```

`LinkedBlockingDeque` nhận giới hạn dung lượng qua constructor. Dù tên lớp có chữ “Blocking”, `addFirst/addLast` vẫn là thao tác thử thực hiện ngay rồi báo lỗi khi đầy; chúng không tự chờ tới khi có chỗ trống. Xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Nếu cần chờ, phải chọn thao tác put hoặc offer có thời hạn trên API BlockingDeque phù hợp. Đó là chính sách khác với nhóm phương thức đang học.

## 5. Chương trình minh họa đầy đủ

Ví dụ một luồng dưới đây tạo trạng thái đầy, xem/lấy phần tử, khôi phục khả năng thêm, rồi tạo các trường hợp rỗng và null.

Hàm `expect()` là công cụ kiểm tra của bài: nó chỉ in kết quả khi loại ngoại lệ đúng mong đợi; nếu không có ngoại lệ hoặc có loại lỗi khác, bài kiểm tra thất bại. Nó không phải mẫu bắt chung RuntimeException để che lỗi trong xử lý nghiệp vụ.

Lưu thành `DequeExceptionDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;
import java.util.concurrent.LinkedBlockingDeque;

public class DequeExceptionDemo {
    static void expect(String label,
                       Class<? extends RuntimeException> expected,
                       Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected.getSimpleName());
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> jobs = new LinkedBlockingDeque<>(2);
        jobs.addLast("A");
        jobs.addFirst("B");
        System.out.println("full=" + jobs);

        expect("addFirst(full)", IllegalStateException.class,
                () -> jobs.addFirst("X"));
        expect("addLast(full)", IllegalStateException.class,
                () -> jobs.addLast("Y"));
        System.out.println("afterRejected=" + jobs);

        System.out.println("getFirst=" + jobs.getFirst());
        System.out.println("sizeAfterGet=" + jobs.size());
        System.out.println("removedLast=" + jobs.removeLast());
        jobs.addLast("C");
        System.out.println("afterRecovery=" + jobs);
        System.out.println("takeFirst=" + jobs.removeFirst());
        System.out.println("takeLast=" + jobs.removeLast());

        expect("removeFirst(empty)", NoSuchElementException.class,
                () -> { jobs.removeFirst(); });
        expect("removeLast(empty)", NoSuchElementException.class,
                () -> { jobs.removeLast(); });
        expect("getFirst(empty)", NoSuchElementException.class,
                () -> { jobs.getFirst(); });
        expect("getLast(empty)", NoSuchElementException.class,
                () -> { jobs.getLast(); });

        Deque<String> local = new ArrayDeque<>();
        expect("nullInsert", NullPointerException.class,
                () -> local.addFirst(null));
        System.out.println("removeMissingValue=" + local.remove("missing"));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 DequeExceptionDemo.java
java DequeExceptionDemo
```

Output dự kiến, đối chiếu theo các thao tác và hợp đồng API:

```text
full=[B, A]
addFirst(full)=IllegalStateException
addLast(full)=IllegalStateException
afterRejected=[B, A]
getFirst=B
sizeAfterGet=2
removedLast=A
afterRecovery=[B, C]
takeFirst=B
takeLast=C
removeFirst(empty)=NoSuchElementException
removeLast(empty)=NoSuchElementException
getFirst(empty)=NoSuchElementException
getLast(empty)=NoSuchElementException
nullInsert=NullPointerException
removeMissingValue=false
```

Không cố định thông điệp stack trace trong kiểm tra. Chương trình chỉ in tên lớp ngoại lệ cho những trường hợp được chủ động tạo ra.

## 6. Đọc thay đổi trạng thái trong ví dụ

### Thêm bị từ chối khi đầy

Sau hai lần thêm:

```text
addLast(A)  → [A]
addFirst(B) → [B, A]
```

Dung lượng là 2. Hai yêu cầu thêm X/Y đều không có chỗ và bị từ chối. Chúng không tự đẩy A/B ra ngoài và không tự thay thế phần tử cũ.

Vì vậy, `afterRejected=[B, A]`. Nếu ứng dụng muốn “đầy thì bỏ phần tử cũ nhất”, đó phải là một chính sách được viết riêng, không phải hành vi mặc định của add.

### Xem không làm mất phần tử

`getFirst()` trả B, nhưng số phần tử vẫn là 2. Việc đã xem không làm deque có chỗ cho lần thêm kế tiếp.

Đừng dùng getFirst khi mục tiêu là nhận một công việc ra khỏi hàng đợi. Nếu không lấy bỏ, vòng lặp có thể xử lý lặp lại cùng phần tử đầu.

### Tạo chỗ rồi thêm lại

`removeLast()` trả A và làm trạng thái thành `[B]`. Sau đó `addLast(C)` thành công, thành `[B, C]`.

Điều này chứng minh một lần IllegalStateException do đầy không làm mất khả năng sử dụng deque. Cần thay đổi điều kiện liên quan, không chỉ lặp lại ngay cùng thao tác trong một vòng bận.

### Lấy hết rồi xem/lấy tiếp

`removeFirst()` lấy B; `removeLast()` lấy C. Deque rỗng, nên bốn thao tác remove/get ở hai đầu đều không còn phần tử thích hợp và ném NoSuchElementException.

`getFirst()` và `removeFirst()` khác tác động khi thành công, nhưng cùng cần tồn tại phần tử đầu.

## 7. Tên ngắn và overload: nhìn đầy đủ chữ ký

Một số tên khác cũng thuộc cách báo bằng ngoại lệ:

| Phương thức | Tương đương | Trường hợp cần nhớ |
| --- | --- | --- |
| `add(e)` | Thêm cuối theo dạng add | Ném lỗi do đầy thay vì trả false |
| `push(e)` | `addFirst(e)` | Không có chỗ thì thất bại theo hợp đồng thêm |
| `remove()` | `removeFirst()` | Rỗng thì NoSuchElementException |
| `pop()` | `removeFirst()` | Stack rỗng thì NoSuchElementException |
| `element()` | `getFirst()` | Chỉ xem đầu, rỗng thì NoSuchElementException |

Nhưng:

```java
deque.remove("missing");
```

là overload nhận một giá trị, không phải `remove()` lấy đầu. Nó tìm loại một lần xuất hiện và trả boolean cho biết có loại được không. Giá trị không tồn tại trong ArrayDeque của ví dụ dẫn tới false, không phải NoSuchElementException.

Với `Deque<Integer>`, `remove(1)` cũng là thao tác tìm giá trị tương ứng, không phải xóa phần tử tại index 1 như một overload của List. Deque không cung cấp hợp đồng truy cập theo chỉ số giống List.

Vì vậy, không xây một quy tắc “mọi phương thức tên remove đều ném lỗi khi không tìm thấy”. Hãy kiểm tra chữ ký, kiểu trả về và tài liệu đúng overload.

## 8. Khi nào nên chọn nhóm này?

Nhóm ném ngoại lệ thể hiện ý định tốt khi thuật toán đã có một giả định đáng tin cậy:

- Một bước xử lý bắt buộc phải có phần tử.
- Một cấu trúc được quản lý sao cho việc đầy là sai lệch cần báo ra.
- Một thao tác là một phần của hợp đồng “thành công hoặc thất bại rõ ràng”, không muốn âm thầm bỏ qua kết quả false.

Tuy nhiên, nếu rỗng hoặc đầy là trạng thái bình thường thường xuyên xuất hiện, các phương thức trả giá trị đặc biệt thường giúp diễn đạt trực tiếp hơn:

```java
String next = deque.pollFirst();
if (next == null) {
    // Chua co phan tu; xu ly theo chinh sach ung dung.
} else {
    // Xu ly next.
}
```

Đây là đoạn tích hợp, cần biến deque và cơ chế bảo vệ phù hợp với môi trường. Không để phần comment thay cho chính sách cần có trong chương trình thật.

Nếu chọn add nhưng sau đó bắt IllegalStateException rồi bỏ qua hoàn toàn, ứng dụng có thể làm mất công việc mà không ai biết. Cần quyết định từ chối, lưu lại, chờ có giới hạn hoặc báo thất bại cho nơi gọi.

Không dùng ngoại lệ như một vòng lặp thăm dò tốc độ cao vô hạn khi không có thay đổi điều kiện.

## 9. Ngoại lệ không thay thế đồng bộ giữa các luồng

Đoạn sau không bảo đảm remove thành công khi một consumer khác có thể chạy xen vào:

```java
if (!deque.isEmpty()) {
    String job = deque.removeFirst();
}
```

Tình huống:

```text
Luồng 1 thấy deque không rỗng
Luồng 2 lấy phần tử cuối cùng
Luồng 1 gọi removeFirst → không còn phần tử
```

Ngay cả với triển khai đồng thời, hai lời gọi riêng `isEmpty()` và `removeFirst()` không tự trở thành một thao tác kiểm tra–lấy nguyên tử.

Khi việc “không còn phần tử lúc thử lấy” là bình thường, một lần poll có thể diễn đạt đúng hơn. Khi cần chờ, dùng thao tác chờ phù hợp. Nếu cần bảo vệ một chuỗi thay đổi lớn hơn, phải có cơ chế bao trùm toàn chuỗi.

Với ArrayDeque không được bảo vệ, không chỉ có nguy cơ ngoại lệ: toàn bộ cách truy cập đồng thời có thể vi phạm hợp đồng của triển khai. Bắt NoSuchElementException không làm cấu trúc trở nên an toàn nhiều luồng.

## 10. Các ca kiểm tra và lỗi phổ biến

| Ca kiểm tra | Điều cần xác minh |
| --- | --- |
| addFirst vào deque còn chỗ | Phần tử mới ở đầu |
| addLast vào deque còn chỗ | Phần tử mới ở cuối |
| Thêm vào deque bounded đã đầy | Đúng loại lỗi do dung lượng, không tự loại phần tử cũ |
| getFirst/getLast khi có dữ liệu | Trả đúng phần tử, kích thước không đổi |
| removeFirst/removeLast khi có dữ liệu | Trả và loại đúng phần tử |
| Bốn thao tác get/remove trên deque rỗng | NoSuchElementException |
| Thêm null vào ArrayDeque | NullPointerException, không diễn giải là đầy |
| Lấy một phần tử rồi thêm lại | Có thể tiếp tục khi đã tạo chỗ |
| remove(value) với giá trị không có | Kết quả theo overload, không nhầm với remove() |
| Nhiều consumer cùng lấy | Không dựa vào kiểm tra isEmpty ở thời điểm trước |

Những lỗi cần tránh:

- Bắt `Exception` rồi báo “hàng đợi đầy” cho cả lỗi null hoặc lỗi lập trình.
- Dùng `ArrayDeque(n)` làm deque giới hạn n.
- Nghĩ phương thức add sẽ đợi như put chỉ vì đối tượng là LinkedBlockingDeque.
- Gọi get trong vòng lặp xử lý mà không bao giờ loại phần tử.
- Cố định chính xác chuỗi message của ngoại lệ làm hợp đồng của mọi JDK.
- Thấy một lần thêm bị lỗi rồi tự xóa dữ liệu cũ mà chưa có chính sách.
- Cho rằng nhiều lời gọi add tạo một giao dịch tất cả hoặc không gì; chuỗi thao tác của ứng dụng cần hợp đồng riêng.

Bài tập:

1. Trong chương trình, sau khi đầy hãy đổi `addLast(Y)` sang `offerLast(Y)`. Cần đổi cách kiểm tra kết quả thế nào?
2. Đổi `getFirst()` thành `removeFirst()` trước lần kiểm tra size. Những trạng thái nào phía sau sẽ thay đổi?
3. Nếu một lần từ chối phải báo cho người gửi, hãy thiết kế kết quả nghiệp vụ rõ ràng thay vì chỉ in log rồi bỏ công việc.
4. Viết một lịch xen kẽ hai consumer làm `isEmpty()` đúng nhưng removeFirst vẫn thất bại.
5. Vì sao lỗi null không được xử lý bằng cách “chờ queue có chỗ rồi thử lại”?

Nhóm thao tác này giúp biểu đạt một yêu cầu mạnh: cần thêm, lấy hoặc xem được phần tử, nếu không thì báo thất bại bằng ngoại lệ. Hiểu đúng nguyên nhân và đúng overload mới giúp ứng dụng xử lý lỗi mà không che mất sai lệch trạng thái hoặc dữ liệu.
