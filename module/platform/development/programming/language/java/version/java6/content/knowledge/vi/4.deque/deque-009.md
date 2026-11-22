# Chọn interface theo hành vi cần cung cấp cho nơi sử dụng

## 1. Bắt đầu từ việc nơi sử dụng cần làm

Một đối tượng `ArrayDeque` có thể phục vụ nhiều vai trò: hàng đợi, ngăn xếp, hoặc cấu trúc cho phép thêm/lấy ở cả hai đầu. Nhưng mỗi đoạn chương trình thường chỉ cần một phần những khả năng ấy. Chọn kiểu khai báo là cách nói rõ **đoạn chương trình này được viết dựa trên hợp đồng nào**.

Ví dụ, bộ xử lý công việc chỉ cần nhận phần tử ở đầu hàng đợi, còn bộ quản lý lịch sử cần thao tác đẩy/lấy ở đỉnh ngăn xếp. Nếu cả hai đều nhận `ArrayDeque`, chữ ký không cho người đọc thấy sự khác nhau đó.

Hãy đi theo thứ tự:

1. Xác định thao tác và quy tắc thứ tự mà nơi sử dụng cần.
2. Chọn interface diễn đạt được các thao tác ấy.
3. Chọn lớp triển khai đáp ứng thêm các yêu cầu về phần tử, hiệu năng, dung lượng và truy cập đồng thời.
4. Nếu interface chuẩn vẫn cho phép quá nhiều hành vi hoặc chưa diễn đạt được quy tắc nghiệp vụ, tạo một interface nhỏ của ứng dụng.

Bài này dùng các API còn áp dụng trong Java hiện đại, với ví dụ Java 17+. `Deque` và `ArrayDeque` xuất hiện từ Java 6; ta không cần quay về môi trường Java 6 hay dùng các cấu trúc cũ để học nguyên tắc này.

## 2. Ba điều khác nhau trong một dòng khai báo

```java
Queue<String> jobs = new ArrayDeque<>();
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `Queue<String>` | Kiểu tĩnh của biến: trình biên dịch kiểm tra các lời gọi qua biến theo kiểu này |
| `new ArrayDeque<>()` | Lớp thực tế được khởi tạo, thực hiện các phương thức khi chương trình chạy |
| `jobs` | Tham chiếu đến đối tượng; không phải một bản sao hay một lớp bọc mới |

Qua `jobs`, ta gọi được `offer`, `poll`, `peek` và các phương thức kế thừa hợp lệ. Ta không gọi trực tiếp được `addFirst` hay `removeLast` vì `Queue` không khai báo chúng.

```java
Queue<String> jobs = new ArrayDeque<>();
jobs.offer("compile");
String next = jobs.poll();

// jobs.addFirst("urgent"); // Không biên dịch: Queue không có addFirst.
```

Đoạn trên là minh họa trong một phương thức, cần import `java.util.Queue` và `java.util.ArrayDeque`. Dòng bị chú thích được giữ để giải thích lỗi biên dịch, không phải phần cần bật lên để chạy.

Đối tượng vẫn là `ArrayDeque`; khai báo interface không chuyển cấu trúc dữ liệu thành một lớp khác. Lời gọi hợp lệ được thực hiện bởi đối tượng thực tế. Khác biệt nằm ở các khả năng được bộc lộ qua kiểu tham chiếu và những giả định mà mã sử dụng được phép dựa vào. Quy tắc lựa chọn phương thức lúc biên dịch và tìm phần triển khai lúc chạy được mô tả trong [JLS §15.12](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).

## 3. Chọn interface chuẩn theo vai trò

| Nhu cầu của nơi sử dụng | Kiểu đáng cân nhắc | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Chỉ duyệt các phần tử | `Iterable<E>` | Trình duyệt có thể hỗ trợ xóa; đây không phải cam kết chỉ đọc |
| Làm việc với một tập phần tử và các thao tác tổng quát | `Collection<E>` | Có các thao tác sửa/xóa; không diễn đạt chính sách lấy đầu/cuối |
| Thêm công việc và lấy phần tử ở đầu theo chính sách hàng đợi | `Queue<E>` | Phải ghi rõ chính sách thứ tự mong muốn |
| Cần cả hai đầu, hoặc cần `push/pop` cho ngăn xếp | `Deque<E>` | Cung cấp nhiều khả năng hơn một giao diện chỉ có ngăn xếp |
| Thực sự cần truy cập theo vị trí | `List<E>` | `Deque` không cung cấp `get(index)` |
| Cần chờ phần tử/chỗ trống trong trao đổi giữa luồng | `BlockingQueue<E>` hoặc `BlockingDeque<E>` | Cần một thiết kế đồng thời và lớp triển khai phù hợp |
| Chỉ được nộp công việc hoặc lấy công việc theo quy tắc ứng dụng | Interface riêng | Cần mô tả thứ tự, trường hợp rỗng và quyền thay đổi |

Không có một interface “tốt nhất” cho mọi biến. Kiểu quá cụ thể làm nơi sử dụng phụ thuộc vào chi tiết không cần thiết; kiểu quá tổng quát lại làm mất thao tác cốt lõi hoặc che giấu quy tắc quan trọng.

Ví dụ, chuyển từ `Deque` sang `Collection` không giúp một thuật toán xử lý đầu hàng đợi trở nên tốt hơn. `Collection` không có `poll`, nên người đọc không còn thấy thao tác lấy đầu mà thuật toán cần. Nếu sau đó phải ép kiểu trở lại `Deque`, lựa chọn ban đầu đã không diễn đạt đúng nhu cầu.

### Queue không tự động có nghĩa FIFO

`Queue` là hợp đồng về các thao tác hàng đợi, không phải lời hứa chung rằng mọi lớp triển khai đều xử lý theo thứ tự vào trước ra trước. Hàng đợi ưu tiên cũng là `Queue`.

Trong `ArrayDeque`, dùng `offer` để thêm ở cuối và `poll` để lấy ở đầu cho hành vi FIFO. Nếu ứng dụng bắt buộc giữ thứ tự nộp việc, yêu cầu đó phải nằm trong hợp đồng của ứng dụng và được lớp triển khai đáp ứng. Chỉ đổi tên biến thành `fifo` hoặc đổi kiểu thành `Queue` chưa đủ. Xem [Queue API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Queue.html).

### Deque cho phép nhiều hơn thao tác ngăn xếp

`Deque` hỗ trợ cả hai đầu; `push`, `pop`, `peek` cũng dùng đầu thứ nhất. Nó phù hợp khi thuật toán thật sự cần những thao tác đó. Tuy nhiên, người nhận `Deque` còn có thể gọi `addLast`, `removeLast`, `clear` và nhiều phương thức khác.

Java Collections không có một interface chuẩn riêng chỉ gồm `push/pop/peek`. Khi muốn bộc lộ đúng ba khả năng này, có thể định nghĩa interface riêng và dùng `ArrayDeque` bên trong. Không cần thiết kế một cây kế thừa chỉ để đổi tên cấu trúc.

## 4. Kiểu tham số cũng là một phần thiết kế

Một hàm lấy lần lượt các phần tử ở đầu có thể viết:

```java
static List<String> drainHeads(Queue<String> source) {
    List<String> result = new ArrayList<>();
    String item;
    while ((item = source.poll()) != null) {
        result.add(item);
    }
    return result;
}
```

Đây là một phương thức trích từ chương trình đầy đủ phía dưới. Chữ ký thể hiện rằng hàm cần thao tác hàng đợi, không cần truy cập đầu còn lại hay chi tiết của `ArrayDeque`.

Hợp đồng cần được giải thích cùng chữ ký:

- Hàm **tiêu thụ** phần tử, làm thay đổi đối tượng được truyền vào.
- Kết quả theo thứ tự `poll` của đối tượng, không tự hứa FIFO cho mọi `Queue`.
- Mã dùng `null` làm tín hiệu dừng, nên đầu vào của ví dụ không chứa phần tử `null`.
- Ví dụ dùng dữ liệu cục bộ trong một luồng; không cam kết rằng hàm sẽ kết thúc nếu có bên khác liên tục thêm dữ liệu.

`ArrayDeque` đáp ứng điều kiện không chứa `null`. Không được suy rộng điều đó thành “mọi Queue đều cấm null”. Đổi lớp triển khai cần kiểm tra lại hợp đồng này.

Nếu hàm chỉ cần ghi log các phần tử mà không tiêu thụ, việc nhận `Queue` có thể tạo ấn tượng sai. Có thể nhận `Iterable` và chỉ duyệt, hoặc nhận một bản chụp dữ liệu. Dù vậy, `Iterable` tự nó không chứng minh đối tượng bên dưới bất biến: `Iterator.remove()` là thao tác tùy chọn và trình duyệt của một số lớp cho phép xóa.

## 5. Kiểu interface không tạo hàng rào sở hữu

Xét hai biến cùng tham chiếu một đối tượng:

```java
Deque<String> storage = new ArrayDeque<>();
Queue<String> publicView = storage;

publicView.offer("A");
storage.addFirst("B");
```

Lúc này đầu hàng đợi là `B`. `publicView` không chứa một bản sao riêng; thay đổi qua `storage` cũng xuất hiện khi quan sát qua `publicView`.

Có ba hệ quả:

1. Trả về `Queue` thay vì `Deque` giảm những lời gọi trực tiếp mà mã bên nhận thường dùng, nhưng không ngăn chủ sở hữu giữ một tham chiếu khác và sửa cả hai đầu.
2. Nếu lớp thực tế hỗ trợ `Deque`, bên nhận có thể cố ép kiểu xuống `Deque`. Đây là sự phụ thuộc vào lớp/kiểu thực tế, làm giảm giá trị của hợp đồng trừu tượng.
3. Nếu trả thẳng cấu trúc nội bộ, các phương thức kế thừa như `clear` vẫn có thể xóa dữ liệu mà đối tượng chủ sở hữu cần bảo vệ.

Vì vậy, “khai báo theo interface” là một kỹ thuật thiết kế phụ thuộc, không phải cơ chế phân quyền bảo mật. Muốn kiểm soát các thao tác hợp lệ trong API ứng dụng, hãy bao gói cấu trúc và cung cấp đúng thao tác nghiệp vụ.

## 6. Ví dụ hoàn chỉnh: ba vai trò từ cùng loại cấu trúc

Lưu thành `InterfaceChoiceDemo.java`. Chương trình có:

- Một biến `Queue` sử dụng `ArrayDeque` để lấy theo FIFO.
- Một biến `Deque` sử dụng thao tác ngăn xếp.
- Hai tham chiếu cùng trỏ một đối tượng, minh họa tác động của việc chia sẻ.
- Một interface `JobInbox` của ứng dụng, không trả ra cấu trúc bên trong.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Queue;

public class InterfaceChoiceDemo {
    static List<String> drainHeads(Queue<String> source) {
        List<String> result = new ArrayList<>();
        String item;
        while ((item = source.poll()) != null) {
            result.add(item);
        }
        return result;
    }

    interface JobInbox {
        void submit(String job);
        Optional<String> takeNext();
    }

    private static final class FifoJobInbox implements JobInbox {
        private final Deque<String> jobs = new ArrayDeque<>();

        @Override
        public void submit(String job) {
            jobs.addLast(Objects.requireNonNull(job));
        }

        @Override
        public Optional<String> takeNext() {
            return Optional.ofNullable(jobs.pollFirst());
        }
    }

    static JobInbox newInbox() {
        return new FifoJobInbox();
    }

    public static void main(String[] args) {
        Queue<String> fifo = new ArrayDeque<>();
        fifo.offer("A");
        fifo.offer("B");
        System.out.println("queue=" + drainHeads(fifo));

        Deque<String> history = new ArrayDeque<>();
        history.push("open");
        history.push("edit");
        System.out.println("undo=" + history.pop());

        Deque<String> shared = new ArrayDeque<>();
        Queue<String> limitedView = shared;
        limitedView.offer("A");
        shared.addFirst("B");
        System.out.println("shared=" + drainHeads(limitedView));

        JobInbox inbox = newInbox();
        inbox.submit("X");
        inbox.submit("Y");
        System.out.println("inboxFirst=" + inbox.takeNext().orElse("<empty>"));
        System.out.println("inboxSecond=" + inbox.takeNext().orElse("<empty>"));
        System.out.println("inboxEmpty=" + inbox.takeNext().orElse("<empty>"));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```shell
javac --release 17 InterfaceChoiceDemo.java
java InterfaceChoiceDemo
```

Stdout suy ra từ trình tự thao tác và hợp đồng API:

```text
queue=[A, B]
undo=edit
shared=[B, A]
inboxFirst=X
inboxSecond=Y
inboxEmpty=<empty>
```

Giải thích từng phần:

| Kết quả | Vì sao |
| --- | --- |
| `queue=[A, B]` | `ArrayDeque.offer` thêm cuối, `poll` lấy đầu; hàm lấy hết hai phần tử |
| `undo=edit` | Hai lần `push` đặt `edit` lên đầu; `pop` lấy phần tử ấy |
| `shared=[B, A]` | `limitedView` và `shared` cùng trỏ một deque; thêm đầu qua `shared` làm đổi thứ tự |
| Hai kết quả `X`, `Y` | Lớp hộp thư tự quản lý thêm cuối/lấy đầu |
| `<empty>` | Hộp thư đã hết phần tử; `takeNext` trả `Optional.empty()`, còn `orElse` cung cấp chuỗi để in |

`Optional` ở đây mô tả “có hoặc không có công việc” trong giá trị trả về. Nó không biến thao tác thành bất đồng bộ, không khóa luồng và không làm cấu trúc an toàn khi truy cập đồng thời. Xem [Optional API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html).

### Hợp đồng của JobInbox phải rõ hơn tên phương thức

Trong ví dụ, `JobInbox` được thiết kế với các quy tắc:

- `submit` nhận một chuỗi khác `null`; `null` dẫn đến `NullPointerException`.
- Các công việc chưa lấy được trả theo thứ tự nộp, FIFO.
- `takeNext` trả ngay; không có công việc thì trả `Optional.empty()`.
- Đối tượng được dùng trong một luồng hoặc dưới cơ chế đồng bộ hóa do thiết kế bên ngoài quy định.
- Không cung cấp thao tác xóa tùy ý, duyệt trình sửa đổi hoặc chọn đầu còn lại.

Những quy tắc này cần được viết trong tài liệu API thực tế và giữ ở mọi lớp triển khai. Bản thân Java chỉ kiểm tra chữ ký interface; nó không tự kiểm tra “mọi triển khai đều FIFO”. Tên `FifoJobInbox` mô tả lớp minh họa, còn yêu cầu thứ tự thuộc về hợp đồng của `JobInbox`.

Lớp `FifoJobInbox` tạo `jobs` bên trong, giữ trường `private`, và không trả tham chiếu này ra ngoài. `final` ngăn thay giá trị tham chiếu của trường sau khởi tạo; dữ liệu trong deque vẫn thay đổi qua `addLast`/`pollFirst`. Đây là bao gói trạng thái có thể thay đổi, không phải một deque bất biến.

## 7. Chọn kiểu ở ba ranh giới khác nhau

### Biến cục bộ

Nếu toàn bộ thuật toán cần thao tác hai đầu, viết `Deque<E>` là tự nhiên. Nếu chỉ xử lý hàng đợi và muốn tránh vô tình gọi nhầm thao tác đầu còn lại, `Queue<E>` giúp thể hiện mục đích.

`var jobs = new ArrayDeque<String>();` suy luận kiểu là `ArrayDeque<String>`, không phải `Queue<String>`. `var` không tự chọn interface phù hợp với vai trò; xem [JLS §14.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4).

### Tham số phương thức

Dùng kiểu biểu đạt đúng khả năng mà thuật toán cần. Nhận `Queue<E>` khi chỉ cần lấy đầu giúp phương thức không phụ thuộc vào thao tác hai đầu. Nhưng nếu cần bảo đảm FIFO, khả năng sửa dữ liệu hoặc không chứa `null`, phải ghi thêm điều kiện tương ứng.

Không nhận một `Collection` rồi ép kiểu xuống `Deque` ở trong hàm như cách “tổng quát hóa”. Cách ấy dời lỗi từ lúc biên dịch sang lúc chạy và làm chữ ký thiếu trung thực.

### Giá trị trả về

Trả cấu trúc sống nghĩa là người nhận có thể ảnh hưởng trạng thái chung trong phạm vi các thao tác mà đối tượng hỗ trợ. Nếu chỉ cần báo cáo danh sách công việc, có thể trả một bản chụp bằng `List.copyOf` trên dữ liệu phù hợp. Bản chụp ấy không phản ánh thay đổi cấu trúc về sau và không cho sửa qua các thao tác `List`; nó vẫn là sao chép nông, nên không tự làm các đối tượng phần tử bất biến. Xem hợp đồng [List.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Nếu cần API cho nộp/lấy việc có quy tắc, trả một đối tượng `JobInbox` như ví dụ thường diễn đạt ý nghĩa rõ hơn trả thẳng `Deque`. Không cần sao chép toàn bộ cấu trúc sau mỗi lần gọi.

## 8. Đổi lớp triển khai: kiểm tra ý nghĩa, không chỉ kiểm tra biên dịch

Thay `new ArrayDeque<>()` bằng một lớp khác có cùng interface có thể vẫn biên dịch nhưng đổi hành vi ứng dụng:

| Yêu cầu cần giữ | Câu hỏi khi thay lớp |
| --- | --- |
| Thứ tự xử lý | Có giữ FIFO hay chuyển sang ưu tiên? |
| Hết dữ liệu | `poll` trả `null`, hay API ứng dụng chuyển sang cách biểu diễn khác? |
| Phần tử hợp lệ | Có cho phép `null`, có yêu cầu khả năng so sánh không? |
| Dung lượng | Có giới hạn không, thêm khi đầy trả `false` hay ném ngoại lệ qua phương thức đã chọn? |
| Đồng thời | Có hỗ trợ chia sẻ giữa luồng không, chuỗi nhiều thao tác có cần đồng bộ thêm không? |
| Chi phí | Thao tác thuật toán dùng có đặc tính hiệu năng phù hợp không? |

`ArrayDeque` tăng dung lượng khi cần, cấm `null` và không tự bảo đảm an toàn cho truy cập đồng thời. Đổi kiểu khai báo sang `Queue`/`Deque` không thay đổi những đặc điểm đó. Mức dung lượng khởi tạo cũng không phải giới hạn số công việc tối đa. Xem [ArrayDeque API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html).

Nếu yêu cầu là “chờ đến khi có công việc” thì `Queue.poll` trả ngay không diễn đạt yêu cầu đó. Cần xem xét `BlockingQueue.take` và cơ chế ngắt/chờ trong một thiết kế riêng. Không thêm vòng lặp liên tục gọi `poll` chỉ vì biến đã mang kiểu interface.

## 9. Những lỗi thiết kế thường gặp

| Lựa chọn | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Mọi tham số đều dùng `ArrayDeque` | Nơi sử dụng phụ thuộc vào một lớp dù chỉ cần thao tác hàng đợi | Dùng `Queue` hoặc `Deque` theo thuật toán |
| Coi mọi `Queue` là FIFO | Có thể nhận lớp triển khai theo chính sách thứ tự khác | Mô tả và kiểm tra hợp đồng thứ tự |
| Coi `Queue` là chỉ được thêm/lấy | Còn `clear`, `remove(Object)` và các thao tác của `Collection` | Dùng interface nghiệp vụ nếu cần giới hạn thực sự |
| Coi `Iterable` là bất biến | Trình duyệt có thể hỗ trợ xóa; đối tượng còn có tham chiếu khác | Phân biệt khả năng duyệt, quyền sửa và bản chụp |
| Dùng `Deque` nhưng thuật toán gọi `get(0)` | `Deque` không có truy cập theo chỉ số | Chọn cấu trúc theo mô hình thao tác thực tế |
| Dùng `var` với mong muốn che lớp cụ thể | Kiểu suy luận vẫn là lớp của biểu thức khởi tạo | Khai báo interface tường minh khi đó là mục đích |
| Luôn ép kiểu xuống trước khi dùng | Hợp đồng tham số không cung cấp điều thuật toán thật sự cần | Sửa chữ ký hoặc tách hành vi vào một lớp thích hợp |
| Trả thẳng deque nội bộ rồi chỉ đổi kiểu trả về | Dữ liệu vẫn được chia sẻ và có thể bị sửa | Bao gói, dùng giao diện nghiệp vụ hoặc bản chụp phù hợp |

## 10. Tự kiểm tra lựa chọn của mình

Trước khi chốt chữ ký, hãy trả lời:

1. Nơi sử dụng cần thêm/lấy một đầu, hai đầu hay chỉ duyệt?
2. Thứ tự có là một yêu cầu của ứng dụng không? Ai bảo đảm nó?
3. Phương thức có được phép tiêu thụ hoặc xóa dữ liệu của bên gọi không?
4. Khi rỗng/đầy, bên gọi muốn giá trị đặc biệt, ngoại lệ hay chờ?
5. Có lộ tham chiếu đến cấu trúc nội bộ hoặc phần tử có thể thay đổi không?
6. Có yêu cầu về đồng thời mà interface đã chọn chưa thể hiện không?
7. Việc đổi lớp triển khai có giữ toàn bộ những điều trên không?

Bài tập thực hành:

- Trong chương trình mẫu, thử gọi `limitedView.addFirst("C")` và giải thích vì sao trình biên dịch từ chối, dù đối tượng thật là `ArrayDeque`.
- Giữ `drainHeads` nhận `Queue`, nhưng dùng một hàng đợi ưu tiên chứa `"B"` và `"A"`. Dự đoán thứ tự lấy theo chính sách ưu tiên tự nhiên của `String`; giải thích vì sao không thể coi hàm là “giữ thứ tự thêm”.
- Thiết kế interface chỉ cho phép nộp công việc, không cho lấy công việc. Nêu lớp nào sở hữu thao tác lấy và làm sao tránh trả ra deque nội bộ.
- Viết một interface ngăn xếp có `push`, `pop`, `peek`; quy định rõ trường hợp rỗng, sau đó dùng `ArrayDeque` để triển khai bằng một đầu nhất quán.

Điểm cần đạt là đọc được một chữ ký phương thức và nhận ra vai trò, quyền thay đổi và các điều kiện còn phải bảo đảm; không chỉ thay tên một lớp bằng tên interface. Hợp đồng chi tiết về hai đầu và cách các phương thức ngăn xếp ánh xạ sang deque có trong [Deque API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html).
