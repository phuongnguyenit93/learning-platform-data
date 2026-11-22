# Giới hạn không chứa null của ArrayDeque

## 1. Không có phần tử và phần tử null là hai ý khác nhau

`ArrayDeque<E>` lưu các tham chiếu đến phần tử ở hai đầu. Một deque đang rỗng là một đối tượng hợp lệ có số phần tử bằng 0. Ngược lại, yêu cầu thêm `null` là yêu cầu lưu một phần tử không trỏ tới đối tượng nào; `ArrayDeque` **không cho phép yêu cầu này**.

```java
Deque<String> queue = new ArrayDeque<>();
queue.addLast("task"); // Hợp lệ.
queue.addLast(null);   // Ném NullPointerException.
```

Đoạn minh họa cần import `java.util.Deque` và `java.util.ArrayDeque`, và được đặt trong một phương thức. Kiểu `String` trong `Deque<String>` không tự tạo ràng buộc khác `null` ở lúc biên dịch. Lời gọi thứ hai hợp lệ về mặt kiểu Java, nhưng vi phạm hợp đồng của lớp khi chạy.

Giới hạn này vẫn áp dụng trong Java hiện đại. Đây không phải một quy tắc chỉ dùng cho thời điểm `ArrayDeque` xuất hiện trong Java 6. Các ví dụ đầy đủ dưới đây dùng Java 17+.

Một lợi ích khi đọc chương trình là: nếu biết chắc đối tượng là `ArrayDeque`, `null` trả về từ thao tác lấy/xem dạng giá trị đặc biệt có thể biểu thị **không có phần tử**, không bị lẫn với một phần tử `null` đã được lưu. Hợp đồng lớp xác nhận không cho phép phần tử `null`; xem [ArrayDeque API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html).

## 2. Tất cả đường thêm phần tử đều phải giữ quy tắc này

| Cách sử dụng | Các phương thức điển hình | Khi đối số phần tử là null |
| --- | --- | --- |
| Thêm vào đầu | `addFirst`, `offerFirst` | `NullPointerException` |
| Thêm vào cuối | `addLast`, `offerLast` | `NullPointerException` |
| Dùng như hàng đợi | `add`, `offer` | `NullPointerException` |
| Dùng như ngăn xếp | `push` | `NullPointerException` |
| Thêm nhiều phần tử | `addAll` | Không chấp nhận nguồn có phần tử `null` |

**Đổi từ add sang offer không làm null trở thành dữ liệu hợp lệ.** Họ phương thức `offer` dùng giá trị `false` cho trường hợp không thêm được theo điều kiện dung lượng của cấu trúc phù hợp; nó không có nghĩa “mọi đầu vào sai đều trả false”. Đối với `ArrayDeque.offer(null)`, kết quả là ngoại lệ, không phải `false`.

Việc dùng một interface để khai báo biến cũng không thay đổi quy tắc của đối tượng:

```java
Queue<String> jobs = new ArrayDeque<>();
jobs.offer(null); // Vẫn ném NullPointerException.
```

Đoạn này cần thêm import `java.util.Queue`. `Queue` là kiểu tham chiếu; đối tượng được tạo vẫn là `ArrayDeque`. Không được suy rộng chính sách phần tử của một lớp thành quy tắc cho mọi lớp triển khai `Queue` hoặc `Deque`.

### Khởi tạo từ một collection cũng cần dữ liệu hợp lệ

`new ArrayDeque<>(source)` không phải cách bỏ qua quy tắc. Nếu nguồn chứa `null`, ta không có một deque hợp lệ được tạo thành để sử dụng. Nếu chính tham chiếu `source` là `null`, lời gọi cũng không hợp lệ.

Khi nạp một lô dữ liệu, cần phân biệt hai đối tượng được kiểm tra:

- Nguồn phải là một đối tượng collection tồn tại.
- Từng phần tử sẽ được đưa vào deque phải khác `null`.

Không nên dùng `List.of("A", null)` để minh họa “ArrayDeque từ chối null”: `List.of` đã từ chối `null` trước khi lời gọi tới `ArrayDeque` xảy ra. Chương trình đầy đủ phía dưới dùng `Arrays.asList` để tạo dữ liệu đầu vào có phần tử `null`, rồi thể hiện rõ nơi kiểm tra.

## 3. Giá trị null trả về không vi phạm quy tắc lưu trữ

Không chứa phần tử `null` không có nghĩa là mọi phương thức đều không bao giờ trả về `null`.

| Mục đích | Phương thức trên deque | Khi deque rỗng |
| --- | --- | --- |
| Lấy và xóa ở đầu | `pollFirst`, `poll` | Trả `null` |
| Lấy và xóa ở cuối | `pollLast` | Trả `null` |
| Chỉ xem ở đầu | `peekFirst`, `peek` | Trả `null` |
| Chỉ xem ở cuối | `peekLast` | Trả `null` |
| Lấy/xóa bằng họ báo lỗi | `removeFirst`, `removeLast`, `remove`, `pop` | Ném `NoSuchElementException` |
| Chỉ xem bằng họ báo lỗi | `getFirst`, `getLast`, `element` | Ném `NoSuchElementException` |

Hai loại lỗi cần tách bạch:

- `NullPointerException` khi thêm `null`: đầu vào vi phạm điều kiện phần tử.
- `NoSuchElementException` khi lấy/xem bằng họ báo lỗi trên deque rỗng: không có phần tử để đáp ứng thao tác.

Ví dụ suy luận trạng thái:

```text
Ban đầu:               []
addLast("A"):          [A]
offerFirst(null):      ném NullPointerException, không thêm phần tử
pollFirst():           trả "A", còn []
pollFirst() lần nữa:   trả null, vẫn []
removeFirst():         ném NoSuchElementException
```

Một lời gọi thêm đơn lẻ bị từ chối vì đối số `null` không tạo ra một phần tử mới trong deque. Đừng suy ra từ đó rằng một chuỗi nhiều lời gọi hoặc một thao tác thêm cả lô luôn có cơ chế hoàn tác tự động. Tóm tắt hai họ phương thức và trường hợp rỗng có trong [Deque API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html).

## 4. Dùng null làm tín hiệu kết thúc vòng lấy

Với một `ArrayDeque` cục bộ không có bên khác thêm dữ liệu đồng thời, có thể lấy đến khi hết:

```java
String item;
while ((item = queue.pollFirst()) != null) {
    System.out.println(item);
}
```

Đây là đoạn dùng bên trong phương thức với `queue` đã được khởi tạo. Mỗi vòng lấy và xóa một phần tử; kết quả `null` nghĩa là thao tác đó không tìm thấy phần tử.

Không cần gọi `isEmpty()` rồi mới gọi `pollFirst()` để giải quyết riêng trường hợp rỗng. Nhưng quy tắc không chứa `null` cũng không tạo cơ chế đồng bộ hóa. `ArrayDeque` không an toàn cho truy cập đồng thời nếu không có đồng bộ hóa thích hợp. Trong bài này, mọi deque thuộc về luồng đang chạy ví dụ.

Nếu cần xử lý xong và giữ nguyên dữ liệu, vòng trên không phù hợp vì nó tiêu thụ deque. Dùng duyệt phần tử khi mục tiêu là quan sát; chính sách `null` không thay đổi ý nghĩa “poll là lấy và xóa”.

## 5. Ví dụ đầy đủ: thêm sai, lấy khi rỗng và kiểm tra lô dữ liệu

Lưu thành `NullBoundaryDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;

public class NullBoundaryDemo {
    record Message(String text) {}

    static void rejectNull(String label, Runnable insertion) {
        try {
            insertion.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException ex) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        Deque<String> queue = new ArrayDeque<>();
        queue.addLast("A");

        rejectNull("addLast", () -> queue.addLast(null));
        rejectNull("offerFirst", () -> queue.offerFirst(null));
        rejectNull("push", () -> queue.push(null));

        System.out.println("afterRejected=" + queue);
        System.out.println("firstPoll=" + queue.pollFirst());
        System.out.println("emptyPeek=" + (queue.peekFirst() == null));
        System.out.println("emptyPoll=" + (queue.pollFirst() == null));

        try {
            queue.removeFirst();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyRemove=NoSuchElementException");
        }

        Deque<Integer> numbers = new ArrayDeque<>();
        Integer number = numbers.pollFirst();
        System.out.println("emptyNumber=" + (number == null));

        Deque<Message> messages = new ArrayDeque<>();
        messages.addLast(new Message(null));
        Message message = messages.removeFirst();
        System.out.println("fieldMissing=" + (message.text() == null));

        Deque<String> destination = new ArrayDeque<>();
        destination.addLast("kept");
        List<String> incoming = Arrays.asList("B", null, "C");
        try {
            List<String> checked = List.copyOf(incoming);
            destination.addAll(checked);
        } catch (NullPointerException ex) {
            System.out.println("batch=NullPointerException");
        }
        System.out.println("destination=" + destination);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```shell
javac --release 17 NullBoundaryDemo.java
java NullBoundaryDemo
```

Stdout suy ra từ hợp đồng API và các thao tác cục bộ trong chương trình:

```text
addLast=NullPointerException
offerFirst=NullPointerException
push=NullPointerException
afterRejected=[A]
firstPoll=A
emptyPeek=true
emptyPoll=true
emptyRemove=NoSuchElementException
emptyNumber=true
fieldMissing=true
batch=NullPointerException
destination=[kept]
```

Hàm `rejectNull` dùng trong chương trình minh họa để xác nhận ba đường thêm đều từ chối `null`. Nó bắt ngoại lệ rồi in **tên loại ngoại lệ**, không in thông báo JVM, vì nội dung thông báo có thể khác giữa các môi trường.

Chương trình cố ý giữ các lần thêm `null` trong các khối kiểm tra có bắt ngoại lệ. Trong mã ứng dụng, nên thiết kế điều kiện đầu vào rõ ràng, thay vì tạo dữ liệu sai rồi dùng ngoại lệ như đường xử lý thông thường.

### Vì sao destination vẫn chỉ có kept?

Trong khối xử lý lô, `List.copyOf(incoming)` kiểm tra dữ liệu để tạo một danh sách không cho phép phần tử `null`. Nó thất bại trước khi `destination.addAll(checked)` được thực hiện, nên deque đích chưa nhận phần tử nào của lô.

Ta đang tạo một ranh giới kiểm tra **trước khi thay đổi đích**, không dựa vào giả định rằng `ArrayDeque.addAll` sẽ tự hoàn tác khi gặp dữ liệu sai. Nếu muốn thử trực tiếp `destination.addAll(incoming)`, chỉ nên xác nhận ngoại lệ; đừng đưa ra kỳ vọng độc lập với phiên bản rằng toàn bộ trạng thái đích chắc chắn được giữ nguyên sau lỗi.

Cách kiểm tra bằng `List.copyOf` dùng thêm bộ nhớ cho danh sách được kiểm tra khi cần tạo bản sao; dữ liệu phần tử vẫn được chia sẻ theo kiểu sao chép nông. Không xem đây là một giao dịch tổng quát: nó ngăn riêng lô có `null` đi đến lệnh cập nhật trong ví dụ, không bảo đảm hoàn tác trước mọi lỗi như hết bộ nhớ. Nguồn của ví dụ cũng không bị sửa đồng thời. Xem [List.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

## 6. Null ở phần tử khác null trong trường của phần tử

`ArrayDeque` kiểm tra tham chiếu phần tử trực tiếp, không tự duyệt và kiểm tra mọi trường bên trong đối tượng.

Trong chương trình:

```java
messages.addLast(new Message(null));
```

`new Message(null)` tạo ra một đối tượng `Message` khác `null`, dù trường `text` của đối tượng ấy mang giá trị `null`. Vì thế việc thêm là hợp lệ đối với `ArrayDeque`. Dòng `fieldMissing=true` minh họa chính sự khác nhau này.

Nếu nghiệp vụ yêu cầu nội dung thông điệp luôn tồn tại, hãy đặt ràng buộc ở kiểu dữ liệu hoặc ở nơi tiếp nhận:

```java
record RequiredMessage(String text) {
    RequiredMessage {
        java.util.Objects.requireNonNull(text, "text");
    }
}
```

Đây là khai báo record minh họa, có thể đặt trong một lớp để dùng với Java 17+. Nó thêm quy tắc của ứng dụng: không cho tạo `RequiredMessage` với trường `text` là `null`. Quy tắc đó độc lập với quy tắc không chứa phần tử `null` của deque.

Tương tự, `""` là chuỗi rỗng, `"null"` là một chuỗi bốn ký tự, và cả hai là đối tượng khác `null`. `ArrayDeque` có thể lưu chúng; việc chúng có phải dữ liệu hợp lệ cho nghiệp vụ hay không cần kiểm tra riêng. Không thay dữ liệu bị thiếu bằng chuỗi `"null"` chỉ để việc thêm không ném ngoại lệ.

## 7. Null do lấy khi rỗng có thể gây lỗi mở hộp

Với kiểu bao `Integer`, phương thức `pollFirst()` vẫn có thể trả `null`:

```java
Deque<Integer> numbers = new ArrayDeque<>();
// int value = numbers.pollFirst(); // NullPointerException khi mở hộp.

Integer value = numbers.pollFirst();
if (value == null) {
    System.out.println("No number");
} else {
    int actual = value;
    System.out.println(actual);
}
```

Đây là đoạn minh họa trong một phương thức với các import cần thiết. Dòng bị chú thích là lỗi cần tránh. `ArrayDeque` không hề chứa số nguyên `null`; chính kết quả “không có phần tử” được trả về, rồi phép mở hộp (unboxing) cố chuyển nó thành `int` và gây lỗi.

Do đó, “deque không chứa null” không chứng minh rằng mọi biểu thức dùng kết quả của nó đều an toàn với `null`. Phải xử lý trạng thái rỗng trước khi mở hộp hoặc gọi phương thức trên kết quả. Quy tắc mở hộp tham chiếu `null` được nêu trong [JLS §5.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8).

## 8. Kiểm tra ngay tại ranh giới tiếp nhận

Nếu một API của ứng dụng luôn yêu cầu công việc khác `null`, có thể kiểm tra ngay lúc nhận để lỗi gắn với đối số cụ thể:

```java
static void enqueue(Deque<String> destination, String job) {
    java.util.Objects.requireNonNull(destination, "destination");
    destination.addLast(java.util.Objects.requireNonNull(job, "job"));
}
```

Phương thức này cũng xác định rõ deque đích phải tồn tại. `Objects.requireNonNull` trả lại chính đối tượng đầu vào khi hợp lệ và ném `NullPointerException` khi đầu vào là `null`; nó không sửa, sao chép hay tự thay dữ liệu bằng mặc định. Xem [Objects.requireNonNull](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).

Có ba chính sách ứng dụng thường cần cân nhắc:

| Dữ liệu null có nghĩa gì? | Chính sách phù hợp |
| --- | --- |
| Lỗi lập trình hoặc vi phạm hợp đồng | Từ chối sớm, nêu rõ đối số nào không hợp lệ |
| Bản ghi đầu vào không có công việc để nộp | Quyết định bỏ qua hoặc báo dữ liệu thiếu trước bước đưa vào deque |
| Một giá trị nghiệp vụ riêng, ví dụ “không có nội dung” | Biểu diễn bằng kiểu dữ liệu rõ ràng, với đối tượng phần tử khác `null` |

Đừng lọc bỏ `null` âm thầm nếu làm mất dữ liệu đầu vào là một lỗi nghiệp vụ. Cũng đừng dùng `null` làm dấu báo kết thúc việc trong `ArrayDeque`: nó sẽ bị từ chối. Nếu cần thông điệp điều khiển, mô hình hóa nó thành một giá trị/kiểu thông điệp riêng và thiết kế quy tắc nhận diện cụ thể.

## 9. Các lỗi cần nhận ra

| Hiểu nhầm | Điều thực sự xảy ra |
| --- | --- |
| `offer(null)` trả false nên có thể kiểm tra bằng if | Với `ArrayDeque`, lời gọi ném `NullPointerException` |
| Không chứa null nên poll luôn có kết quả khác null | `poll` trả `null` khi không có phần tử |
| Ngoại lệ khi remove khỏi deque rỗng cũng là lỗi null | Họ `remove/get/pop` phù hợp ném `NoSuchElementException` khi rỗng |
| Đổi kiểu biến từ ArrayDeque sang Queue sẽ cho phép null | Hành vi đối tượng không đổi |
| Một Message có text=null cũng là phần tử null | Đối tượng Message vẫn có thể khác `null`; cần ràng buộc trường riêng |
| `List.of("A", null)` kiểm tra được lỗi constructor ArrayDeque | Ngoại lệ phát sinh khi tạo danh sách trước |
| Bắt lỗi addAll chứng minh chưa có phần tử nào được thêm | Không nên giả định thao tác cả lô có tính hoàn tác |
| Không có phần tử null thì có thể mở hộp trực tiếp kết quả poll | Kết quả rỗng vẫn là `null`, mở hộp sẽ lỗi |
| Gán biến deque=null giống một deque rỗng | Biến đó không trỏ đến deque nào; gọi phương thức sẽ lỗi ở bước truy cập đối tượng |

## 10. Thực hành theo tình huống

1. Thay ba lời gọi thêm `null` trong chương trình mẫu bằng các phương thức thêm còn lại. Dự đoán loại ngoại lệ và xác nhận deque không nhận thêm phần tử sau từng lời gọi đơn.
2. Dùng deque rỗng, đối chiếu `peekFirst` với `getFirst`, rồi `pollLast` với `removeLast`. Ghi rõ thao tác nào chỉ xem, thao tác nào xóa, thao tác nào trả `null`.
3. Sửa dữ liệu `incoming` thành `Arrays.asList("B", "C")`. Khi đó việc kiểm tra hoàn tất và deque đích chứa `[kept, B, C]`.
4. Tạo một `RequiredMessage` với nội dung `null`. Xác định lỗi xảy ra khi tạo thông điệp hay khi đưa thông điệp vào deque.
5. Thiết kế quy tắc tiếp nhận bản ghi thiếu mã công việc: từ chối, bỏ qua có ghi nhận, hay biểu diễn một trạng thái riêng. Giải thích vì sao lựa chọn đó thuộc hợp đồng ứng dụng, không do `ArrayDeque` tự quyết định.

Điều cần nhớ khi đọc mã là ranh giới giữa ba trạng thái: **deque rỗng**, **tham chiếu deque không tồn tại**, và **yêu cầu thêm một phần tử null**. Nhận ra đúng trạng thái giúp chọn cách xử lý rỗng, kiểm tra đầu vào và vị trí báo lỗi phù hợp.
