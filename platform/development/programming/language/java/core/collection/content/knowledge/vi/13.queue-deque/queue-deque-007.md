# Vì sao ArrayDeque không nhận null

## 1. Đây là hợp đồng của lớp, không phải hạn chế của mảng Java

`ArrayDeque` là một cách triển khai `Deque` bằng mảng có thể tăng dung lượng. Bạn có thể thêm và lấy phần tử ở cả hai đầu, dùng nó như hàng đợi hoặc ngăn xếp.

Nhưng có một điều kiện rõ ràng: **không được lưu null làm phần tử**. Việc gọi một phương thức chèn với null dẫn đến `NullPointerException`, kể cả khi phương thức mang tên `offer`.

Điều này không có nghĩa mảng tham chiếu trong Java không chứa được null. Mảng Object có thể chứa null. Đây là một lựa chọn của ArrayDeque, giúp giữ ý nghĩa của giá trị báo không có phần tử và phù hợp với cách lớp tổ chức các ô lưu trữ.

Có hai lớp giải thích cần phân biệt:

- Ở API, null được dùng làm kết quả báo rằng không có phần tử để xem hoặc lấy.
- Trong cách triển khai OpenJDK 17, các ô mảng không chứa thành viên của deque cũng được giữ là null.

Người dùng lớp phải tuân theo hợp đồng công khai. Chi tiết mảng giúp hiểu cơ chế, nhưng không phải lý do để chương trình truy cập trực tiếp các trường riêng bên trong.

Bài học dùng ví dụ Java 17 để kiểm chứng các đường chèn, trường hợp thêm cả lô và cách biểu diễn một thông điệp có dữ liệu bên trong vắng mặt. Bạn chỉ cần biết biến tham chiếu, phương thức và tập hợp tổng quát; các trường hợp dễ nhầm sẽ được tách rõ.

## 2. Từ “null” có thể đang chỉ những điều khác nhau

Xét các biểu thức:

| Trường hợp | Ý nghĩa |
| --- | --- |
| `Deque<String> q = null` | Chưa có đối tượng deque để gọi phương thức |
| `q.addLast(null)` | Cố thêm tham chiếu null làm một thành viên |
| `q.pollFirst() == null` | Với ArrayDeque hợp lệ, thao tác không lấy được phần tử |
| `new Message(null)` | Có đối tượng Message, nhưng một trường bên trong là null |
| `"null"` | Một đối tượng chuỗi chứa bốn ký tự n, u, l, l |
| `""` | Một đối tượng chuỗi có độ dài 0 |

ArrayDeque cấm trường hợp **phần tử chính là null**. Nó không tự cấm mọi đối tượng có trường null, không cấm chuỗi rỗng và không cấm chuỗi chứa chữ “null”.

Nếu biến q tự nó bằng null, lỗi khi gọi q.addLast khác với việc có một ArrayDeque thật từ chối một phần tử null. Cùng tên NullPointerException không đủ để kết luận lỗi nằm ở đâu; phải xem tham chiếu nào đang vắng hoặc điều kiện nào bị kiểm tra.

Kiểu `Deque<String>` trong Java 17 không tự biểu diễn ràng buộc “tham chiếu phần tử chắc chắn khác null” ở cấp trình biên dịch. Cách triển khai kiểm tra điều kiện của nó khi nhận dữ liệu. Vì vậy, một lời gọi có thể biên dịch nhưng vẫn bị từ chối lúc chạy.

## 3. Lý do ở API: giữ null làm tín hiệu không có phần tử

ArrayDeque có các phép:

~~~text
peekFirst / peekLast : xem một đầu, không xóa
pollFirst / pollLast : lấy ra và xóa một đầu
~~~

Khi rỗng, chúng trả null. Nếu không rỗng, chúng trả một phần tử thực đang được lưu ở đầu tương ứng.

Vì ArrayDeque không có thành viên null, hai tình trạng được phân biệt rõ:

~~~text
kết quả khác null → đã nhận một phần tử
kết quả bằng null → không có phần tử ở lần xem/lấy đó
~~~

Với một cấu trúc cho phép lưu null, kết quả null có thể mang hai nghĩa: “không có thành viên” hoặc “có thành viên nhưng giá trị của nó là null”. Nếu API chỉ trả một tham chiếu, người gọi không thể phân biệt chỉ bằng giá trị ấy.

Ví dụ phản chứng dùng LinkedList, lớp cho phép null:

~~~text
nội dung ban đầu: [null, next]
pollFirst()    : null
còn lại        : [next]
~~~

Null vừa được trả là dữ liệu đã lấy ra, không phải bằng chứng deque ban đầu rỗng. ArrayDeque loại bỏ sự nhập nhằng này bằng cách không chấp nhận dữ liệu null ngay từ đầu.

Deque nói chung không buộc mọi cách triển khai phải cấm null, nhưng khuyến cáo mạnh việc tránh null vì vai trò báo rỗng. ArrayDeque chọn chính sách cấm cụ thể và tường minh. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 4. Lý do trong cách triển khai: ô trống và thành viên có ý nghĩa khác nhau

OpenJDK 17 dùng một mảng vòng để chứa tham chiếu. Những ô không thuộc thành viên được giữ null; đầu chỉ vị trí lấy tiếp theo, đuôi chỉ vị trí chèn tiếp theo. Khi lấy một phần tử ra, ô cũ được xóa về null. [Mã nguồn ArrayDeque, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayDeque.java).

Mô hình minh họa dưới đây dùng tám ô giả định:

~~~text
chỉ số:   0      1      2      3      4      5      6      7
ô mảng:  [C]  [null] [null] [null] [null] [null]  [A]    [B]

đầu = 6: vị trí của A
đuôi = 1: ô trống để chèn tiếp theo
thứ tự thành viên: ô 6 (A) → ô 7 (B) → ô 0 (C)
~~~

Đường đi logic trong sơ đồ quấn qua cuối mảng rồi về ô 0. Các ô null không phải phần tử được duyệt. Số tám chỉ để minh họa, không là dung lượng mặc định.

Quy tắc không lưu phần tử null giúp việc đọc một ô ở đầu phân biệt được có phần tử hay không. Nếu cho null làm dữ liệu mà giữ nguyên cách kiểm tra ấy, một giá trị hợp lệ sẽ bị lẫn với ô trống.

Một cấu trúc mảng khác có thể hỗ trợ null bằng cách quản lý sự hiện diện theo một cơ chế khác. Do đó, không nên suy “mảng vòng về lý thuyết không thể lưu null”. Điểm đang học là sự phối hợp giữa hợp đồng và biểu diễn của ArrayDeque.

## 5. poll và get có thể dùng chung ý nghĩa của ô không chứa phần tử

Trong mô hình của ArrayDeque, khi có một tham chiếu thật ở đầu, pollFirst lấy nó ra, bỏ tham chiếu khỏi ô cũ và tiến đầu. Khi không có phần tử, kết quả là null.

GetFirst là dạng yêu cầu phải có phần tử: nếu không có, nó ném `NoSuchElementException`; nếu có, nó trả phần tử mà không xóa.

Nhờ ràng buộc cấm null, kết quả rỗng không bị nhầm với một thành viên hợp lệ. Nhưng người dùng vẫn phải chọn đúng tác dụng:

| Phương thức | Khi có phần tử | Khi rỗng |
| --- | --- | --- |
| `peekFirst()` | Trả phần tử, giữ nguyên deque | null |
| `pollFirst()` | Trả phần tử và xóa nó | null |
| `getFirst()` | Trả phần tử, giữ nguyên deque | NoSuchElementException |
| `removeFirst()` | Trả phần tử và xóa nó | NoSuchElementException |

Phía Last có các cặp tương tự cho đầu cuối. Các tên Queue ngắn hơn như peek và poll làm việc ở đầu trước của deque.

Cấm null không làm mọi thao tác trở thành phép lấy ra. Peek vẫn chỉ xem; không thể dùng việc nhìn thấy phần tử như bằng chứng nó đã bị xử lý hoặc đã rời cấu trúc.

## 6. Xóa tham chiếu cũ không phải cam kết thu gom bộ nhớ tức thời

Khi một phần tử bị loại, đặt ô cũ về null còn có tác dụng bỏ tham chiếu của deque tới đối tượng ấy. Một vùng mảng đã không còn giữ thành viên không nên tiếp tục giữ đối tượng chỉ vì giá trị cũ còn nằm trong ô.

Điều đó không có nghĩa đối tượng được thu gom ngay sau poll. Nếu biến khác hoặc cấu trúc khác vẫn tham chiếu tới nó, đối tượng vẫn có thể được dùng. Thời điểm thu gom bộ nhớ cũng không do lời gọi poll tự bảo đảm.

Trong chương trình kiểm chứng, chúng ta chỉ quan sát hợp đồng thành viên và kết quả phương thức. Không gọi bộ thu gom để cố chứng minh thời điểm một đối tượng biến mất, và không dùng phản chiếu để đọc mảng riêng của lớp.

Hãy tách “deque đã bỏ tham chiếu của nó” khỏi “không còn tham chiếu nào trong toàn chương trình”. Hai kết luận này không tương đương.

## 7. Những đường chèn nào đều từ chối null?

Với ArrayDeque, chính sách áp dụng cho các cách thêm trực tiếp:

| Lời gọi | Ý nghĩa khi phần tử hợp lệ | Khi phần tử là null |
| --- | --- | --- |
| `add(e)` | Thêm phía cuối | NullPointerException |
| `offer(e)` | Thêm phía cuối | NullPointerException |
| `addFirst(e)` | Thêm phía đầu | NullPointerException |
| `addLast(e)` | Thêm phía cuối | NullPointerException |
| `offerFirst(e)` | Thêm phía đầu | NullPointerException |
| `offerLast(e)` | Thêm phía cuối | NullPointerException |
| `push(e)` | Đưa vào đầu khi dùng như ngăn xếp | NullPointerException |

Không có đường vòng “dùng push thay add” để đưa null vào. Đổi tên phương thức không đổi hợp đồng phần tử.

Offer là dạng có thể dùng giá trị false để báo không chèn được vì điều kiện dung lượng ở những cấu trúc bị giới hạn. Nó không biến một tham chiếu đầu vào bị cấm thành kết quả false.

ArrayDeque tự tăng dung lượng khi cần theo hợp đồng của lớp và không đặt một sức chứa tối đa cố định qua số khởi tạo. Null bị từ chối là vấn đề dữ liệu, không phải bằng chứng deque đang đầy. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Nếu thay kiểu biến từ ArrayDeque sang Deque hoặc Queue nhưng vẫn dùng cùng đối tượng ArrayDeque, chính sách cũng không đổi. Kiểu interface không tắt các kiểm tra của đối tượng thực tế.

## 8. Hàm khởi tạo và addAll cũng phải tuân theo chính sách

Không chỉ lời gọi thêm từng phần tử mới có thể nhận dữ liệu không hợp lệ. Một nguồn Collection có thể chứa null rồi được truyền vào hàm khởi tạo hoặc addAll.

Ví dụ nguồn hợp lệ đối với Arrays.asList nhưng không hợp lệ làm thành viên ArrayDeque:

~~~java
List<String> input = Arrays.asList("before", null, "after");
~~~

Đoạn minh họa cần nhập `java.util.List` và `java.util.Arrays`. Arrays.asList cho phép phần tử null nên có thể dùng nó để kiểm tra chính deque nhận dữ liệu.

Nếu tạo `new ArrayDeque<>(input)`, việc khởi tạo không hoàn thành bình thường và mã gọi nhận NullPointerException. Bạn không nhận được một deque đã tạo thành công với một thành viên null.

Nếu đang có một deque rồi gọi addAll, cần chú ý thêm một điểm: **ngoại lệ không có nghĩa mọi thay đổi trước đó của lời gọi đã được hoàn tác**.

Trong ví dụ OpenJDK được kiểm chứng ở chương trình:

~~~text
deque trước: [stable]
nguồn:       [before, null, after]

addAll ném NullPointerException

deque sau:   [stable, before]
~~~

Before đã được thêm; null bị từ chối; after chưa được thêm. Không có thành viên null nào vượt qua chính sách, nhưng deque đã thay đổi một phần.

Hợp đồng thêm lô của Deque có nêu khả năng chỉ một phần dữ liệu được thêm trước khi lỗi xuất hiện. Đừng coi addAll là một giao dịch nguyên tử chỉ vì nó là một lời gọi phương thức. [Java 17: Deque.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#addAll(java.util.Collection)).

## 9. Kiểm tra lô trước khi sửa deque

Nếu hợp đồng của hàm là “từ chối lô có null trước khi thêm bất kỳ phần tử nào của lô”, có thể thực hiện hai giai đoạn:

1. Chụp nguồn vào một danh sách riêng và kiểm tra các tham chiếu phần tử.
2. Chỉ thêm danh sách đã kiểm tra vào đích khi toàn bộ kiểm tra thành công.

Hàm trong chương trình:

~~~java
static <E> void appendValidated(
        ArrayDeque<E> target, Collection<? extends E> input) {
    List<E> snapshot = new ArrayList<>(input);
    for (E element : snapshot) {
        Objects.requireNonNull(element, "Phan tu cua lo khong duoc null");
    }
    target.addAll(snapshot);
}
~~~

Đây là đoạn trích từ mã hoàn chỉnh. Danh sách chụp giữ cùng các tham chiếu phần tử, không nhân bản sâu từng đối tượng.

Khi lô có null, lỗi xảy ra ở giai đoạn kiểm tra trước khi hàm gọi addAll trên target. Trong ví dụ, target vẫn là `[stable]`. Khi lô sạch gồm first và second, kết quả là `[stable, first, second]`.

Phạm vi bảo đảm cần nói chính xác: hàm tránh thay đổi target do **phát hiện null trong lô ở bước kiểm tra** trong điều kiện sử dụng của ví dụ. Nó không phải một cơ chế giao dịch cho mọi lỗi tài nguyên hoặc mọi thao tác cạnh tranh.

Kiểu đích được chọn là ArrayDeque, không phải một Deque bất kỳ có thể đầy giữa lô vì giới hạn cố định. Không tự mở rộng kết luận này sang những cách triển khai có điều kiện chấp nhận phần tử khác.

Việc lọc bỏ null là một chính sách khác với từ chối. Chỉ bỏ qua khi dữ liệu cho phép điều đó; đừng tự xóa một thông điệp thiếu rồi báo rằng toàn bộ lô đã được chấp nhận nguyên vẹn.

## 10. Chương trình đầy đủ dùng Java 17

Lưu thành `ArrayDequeNullDemo.java`. Chương trình kiểm tra các đường chèn, tìm/xóa theo null, nguồn Collection có null, thêm lô, tín hiệu rỗng và hai cách bọc dữ liệu bên trong có thể thiếu.

Hàm checkNullInput chỉ phục vụ các phép thử. Tham số Runnable giữ một lời gọi, và `() -> ...` tạo thao tác để hàm chạy. Mỗi phép thử biết deque nhận lời gọi là đối tượng thật, nên lỗi đang được kiểm tra là chính sách với đầu vào null.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;

public class ArrayDequeNullDemo {
    record Message(String payload) {}

    static void checkNullInput(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=accepted");
        } catch (NullPointerException exception) {
            System.out.println(label + "=" + exception.getClass().getSimpleName());
        }
    }

    static <E> void appendValidated(
            ArrayDeque<E> target, Collection<? extends E> input) {
        List<E> snapshot = new ArrayList<>(input);
        for (E element : snapshot) {
            Objects.requireNonNull(element, "Phan tu cua lo khong duoc null");
        }
        target.addAll(snapshot);
    }

    public static void main(String[] args) {
        ArrayDeque<String> direct = new ArrayDeque<>();
        direct.addLast("stable");
        checkNullInput("add", () -> direct.add(null));
        checkNullInput("offer", () -> direct.offer(null));
        checkNullInput("addFirst", () -> direct.addFirst(null));
        checkNullInput("addLast", () -> direct.addLast(null));
        checkNullInput("offerFirst", () -> direct.offerFirst(null));
        checkNullInput("offerLast", () -> direct.offerLast(null));
        checkNullInput("push", () -> direct.push(null));
        System.out.println("after direct attempts=" + direct);
        System.out.println("contains(null)=" + direct.contains(null));
        System.out.println("remove(null)=" + direct.remove(null));
        System.out.println("after null search=" + direct);

        checkNullInput("constructor", () ->
                new ArrayDeque<>(Arrays.asList("before", null, "after")));
        checkNullInput("List.of source", () ->
                List.of("before", null, "after"));

        ArrayDeque<String> bulk = new ArrayDeque<>();
        bulk.addLast("stable");
        List<String> badBatch = Arrays.asList("before", null, "after");
        checkNullInput("addAll", () -> bulk.addAll(badBatch));
        System.out.println("after failing addAll=" + bulk);

        ArrayDeque<String> checked = new ArrayDeque<>();
        checked.addLast("stable");
        checkNullInput("validated batch", () -> appendValidated(checked, badBatch));
        System.out.println("after validation rejection=" + checked);
        appendValidated(checked, List.of("first", "second"));
        System.out.println("after valid batch=" + checked);

        Deque<String> signals = new ArrayDeque<>();
        signals.addLast("A");
        System.out.println("nonempty peek=" + signals.peekFirst());
        System.out.println("size after peek=" + signals.size());
        System.out.println("nonempty poll=" + signals.pollFirst());
        System.out.println("empty peek=" + signals.peekFirst());
        System.out.println("empty poll=" + signals.pollFirst());
        try {
            signals.getFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getFirst=" + exception.getClass().getSimpleName());
        }

        Deque<String> nullable = new LinkedList<>();
        nullable.addLast(null);
        nullable.addLast("next");
        System.out.println("linked first poll=" + nullable.pollFirst());
        System.out.println("linked empty after null=" + nullable.isEmpty());
        System.out.println("linked next poll=" + nullable.pollFirst());

        Deque<Message> messages = new ArrayDeque<>();
        messages.addLast(new Message(null));
        messages.addLast(new Message("hello"));
        Message first = messages.pollFirst();
        System.out.println("message reference present=" + (first != null));
        System.out.println("message payload absent=" + (first.payload() == null));
        System.out.println("second payload=" + messages.pollFirst().payload());
        System.out.println("no message=" + messages.pollFirst());

        Deque<Optional<String>> options = new ArrayDeque<>();
        options.addLast(Optional.empty());
        options.addLast(Optional.of("data"));
        Optional<String> wrapper = options.pollFirst();
        System.out.println("optional wrapper present=" + (wrapper != null));
        System.out.println("optional payload present=" + wrapper.isPresent());
        System.out.println("next optional=" + options.pollFirst());
        System.out.println("no optional element=" + options.pollFirst());

        Deque<String> text = new ArrayDeque<>();
        text.addLast("");
        text.addLast("null");
        System.out.println("empty string length=" + text.pollFirst().length());
        String literal = text.pollFirst();
        System.out.println("literal value='" + literal + "'");
        System.out.println("literal is null=" + (literal == null));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ArrayDequeNullDemo.java
java ArrayDequeNullDemo
~~~

Dùng JDK 17 trở lên. `--release 17` kiểm tra mã và API theo Java 17. Tên tệp phải khớp lớp public.

Kết quả chuẩn:

~~~text
add=NullPointerException
offer=NullPointerException
addFirst=NullPointerException
addLast=NullPointerException
offerFirst=NullPointerException
offerLast=NullPointerException
push=NullPointerException
after direct attempts=[stable]
contains(null)=false
remove(null)=false
after null search=[stable]
constructor=NullPointerException
List.of source=NullPointerException
addAll=NullPointerException
after failing addAll=[stable, before]
validated batch=NullPointerException
after validation rejection=[stable]
after valid batch=[stable, first, second]
nonempty peek=A
size after peek=1
nonempty poll=A
empty peek=null
empty poll=null
empty getFirst=NoSuchElementException
linked first poll=null
linked empty after null=false
linked next poll=next
message reference present=true
message payload absent=true
second payload=hello
no message=null
optional wrapper present=true
optional payload present=false
next optional=Optional[data]
no optional element=null
empty string length=0
literal value='null'
literal is null=false
~~~

## 11. Đọc kết quả theo từng ranh giới

### 11.1. Không có đường chèn null thành công

Bảy dòng đầu đều là NullPointerException. Sau chúng, `after direct attempts=[stable]` cho biết phần tử cũ vẫn được giữ và không có thành viên mới nào từ các lời gọi chèn null.

Phương thức offer cũng ném lỗi chứ không trả false. Push không tạo một ngoại lệ cho chính sách chỉ vì đang dùng deque như ngăn xếp.

### 11.2. Tìm null khác với chèn null

`contains(null)=false` và `remove(null)=false` cho thấy hai lời gọi tìm/xóa theo giá trị không tìm được thành viên null trong ArrayDeque của ví dụ. Nội dung vẫn là stable.

Đừng suy câu “ArrayDeque không nhận null làm phần tử” thành “bất kỳ phương thức nào có đối số null đều phải ném NullPointerException”. Chính sách với từng tham số vẫn phải đọc theo chữ ký phương thức. Các thao tác chèn và thao tác hỏi sự hiện diện không phải cùng một việc.

### 11.3. Thêm lô có thể đổi trạng thái trước khi báo lỗi

`after failing addAll=[stable, before]` đối chiếu rõ phần được thêm trước lỗi. Nếu mã bắt ngoại lệ rồi thử lại nguyên lô, nó có thể thêm lại một bản before nữa. ArrayDeque cho phép các phần tử bằng nhau xuất hiện nhiều lần, nên không có cơ chế loại trùng tự bù cho một chính sách thử lại sai.

`after validation rejection=[stable]` cho thấy cách kiểm tra trước đã đổi thời điểm phát hiện lỗi: target chưa nhận phần tử nào của lô.

### 11.4. Hai nguồn NullPointerException khác nhau

`constructor=NullPointerException` kiểm tra ArrayDeque nhận một nguồn cho phép null.

`List.of source=NullPointerException` kiểm tra một bước khác: List.of đã từ chối null lúc tạo nguồn. Lúc đó chưa có một lời gọi chèn dữ liệu ấy vào deque.

Vì vậy, khi viết ví dụ hoặc kiểm thử, hãy biết lỗi xảy ra ở nguồn hay ở nơi nhận. Tạo `List.of("before", null, "after")` rồi dùng nó để “chứng minh addAll từ chối null” là gán sai trách nhiệm cho phương thức chưa được chạy.

## 12. Không có phần tử và có thông điệp thiếu dữ liệu là hai trạng thái

Giả sử một thông điệp có thể tồn tại nhưng chưa có payload. Bạn không cần biến chính phần tử của deque thành null để diễn đạt điều đó.

Chương trình định nghĩa:

~~~java
record Message(String payload) {}
~~~

`new Message(null)` là một tham chiếu Message thật. Nó khác `null` và được ArrayDeque nhận. Chỉ trường payload bên trong mới không có giá trị.

Kết quả:

~~~text
message reference present=true
message payload absent=true
~~~

Hai dòng này trả lời hai câu hỏi riêng:

- Có lấy được một thông điệp ra không?
- Thông điệp ấy có payload không?

Khi không còn Message nào, pollFirst trả null ở cấp tham chiếu thông điệp. Khi đã nhận một Message, mã mới xem ý nghĩa trường bên trong theo hợp đồng của Message.

ArrayDeque không tự kiểm tra sâu mọi trường của đối tượng. Nếu nghiệp vụ yêu cầu payload bắt buộc phải có, hãy đặt điều kiện đó trong mô hình hoặc tại nơi nhận thông điệp. Việc deque chấp nhận một đối tượng không chứng minh đối tượng đáp ứng mọi quy tắc nghiệp vụ.

Mẫu wrapper giúp tách sự hiện diện của một phần tử khỏi sự hiện diện của dữ liệu chứa trong phần tử ấy. Nó không phải cách lách chính sách để lưu một thành viên null: thành viên được lưu là Message khác null.

## 13. Optional.empty cũng là một đối tượng khác null

Một lựa chọn minh họa khác là `Deque<Optional<String>>`:

~~~text
không có phần tử của deque          → poll trả null
có Optional.empty trong deque       → poll trả một Optional khác null, không có giá trị bên trong
có Optional chứa "data" trong deque → poll trả Optional[data]
~~~

Chương trình nhận:

~~~text
optional wrapper present=true
optional payload present=false
~~~

Điều đó không mâu thuẫn với chính sách cấm null. Optional.empty là một giá trị Optional hợp lệ; nó không phải tham chiếu null.

Ngược lại, `options.addLast(null)` vẫn bị từ chối, dù kiểu phần tử là Optional. Bọc kiểu tổng quát không làm tham chiếu null ở cấp ngoài trở nên hợp lệ.

Optional có API mô tả sự có hoặc không của giá trị bên trong. Khi mô hình một thông điệp thực, một kiểu miền như Message có thể diễn đạt tên trường và ý nghĩa sự vắng mặt rõ hơn. Không cần bọc mọi phần tử chỉ để tránh viết điều kiện đầu vào; chọn mô hình theo ý nghĩa dữ liệu. [Java 17: Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

Đừng dùng đồng nhất tham chiếu của các Optional.empty để suy quy tắc nghiệp vụ. Trong ví dụ, chúng ta chỉ dùng tính khác null của phần tử và isPresent của giá trị được bọc.

## 14. Chuỗi rỗng và chuỗi “null” vẫn là dữ liệu thật

Chương trình thêm lần lượt `""` và `"null"` vào ArrayDeque rồi lấy ra.

Kết quả:

~~~text
empty string length=0
literal value='null'
literal is null=false
~~~

Chuỗi rỗng có một tham chiếu thật nhưng không có ký tự. Chuỗi “null” có bốn ký tự. Cả hai đều khác null ở cấp tham chiếu nên ArrayDeque nhận được.

Đừng dùng cách hiển thị làm bằng chứng về danh tính tham chiếu. Một chuỗi in ra chữ null và một tham chiếu null có thể gây nhầm nếu chỉ nhìn dòng văn bản thiếu ngữ cảnh. Chương trình đặt dấu nháy quanh chuỗi và kiểm tra `literal == null` để phân biệt.

Tương tự, số 0 hoặc một đối tượng có tên “EMPTY” vẫn có thể là dữ liệu hợp lệ nếu mô hình cho phép. Muốn dùng một đối tượng làm tín hiệu riêng của ứng dụng, phải xác định rõ kiểu và chính sách; deque không tự biết rằng tên hoặc nội dung của nó là đặc biệt.

Nếu thay một giá trị null bị lỗi bằng chuỗi “null” chỉ để chèn được, bạn đã thay dữ liệu, không chỉ sửa cách lưu. Việc đó chỉ hợp lệ khi hợp đồng đầu vào thực sự muốn một chuỗi như vậy.

## 15. Không suy chính sách chung cho mọi Collection từ ArrayDeque

Một số cấu trúc như ArrayList hoặc LinkedList có thể nhận null. ArrayDeque thì không. Việc các lớp cùng giữ tham chiếu đối tượng không buộc chúng có cùng hợp đồng phần tử.

Khi chuyển dữ liệu từ nguồn cho phép null sang đích cấm null, cần chọn chính sách tường minh:

| Chính sách | Ý nghĩa |
| --- | --- |
| Từ chối lô | Giữ nguyên yêu cầu rằng mọi thành viên phải có tham chiếu thật |
| Bỏ qua null | Chấp nhận mất những vị trí dữ liệu đó vì miền sử dụng đã cho phép |
| Dùng kiểu thông điệp khác null có trường tùy chọn | Giữ sự hiện diện của thông điệp, biểu diễn riêng dữ liệu bên trong vắng mặt |
| Sửa dữ liệu ở nguồn | Thực hiện một phép chuyển đổi có ý nghĩa và được xác định trước |

Không chỉ thay lớp bằng một cấu trúc cho phép null để làm ngoại lệ biến mất rồi tiếp tục dùng các vòng poll đến null như cũ. Khi dữ liệu null được phép vào, cách giải thích kết quả trả về đã thay đổi.

Cũng không coi Arrays.asList cho phép null là bằng chứng mọi Collection nhận lô đó đều phải chấp nhận. Mỗi nơi nhận có quyền áp dụng hợp đồng phần tử của nó; bước chuyển là ranh giới cần kiểm tra.

Trong chương trình, LinkedList chỉ được dùng làm phản ví dụ để hiểu sự mơ hồ ở kết quả null. Các thao tác còn lại chọn ArrayDeque để giữ chính sách không có thành viên null nhất quán.

## 16. Giới hạn của suy luận từ null và chi tiết mảng

Với ArrayDeque được dùng hợp lệ, kết quả null từ một lần poll/peek biểu thị không có phần tử để trả ở lần thao tác đó. Nó không có nghĩa sẽ không có phần tử nào được thêm về sau.

Một lần peek khác null cũng không dành riêng phần tử cho bên vừa nhìn. Nếu có thao tác sửa xen vào giữa peek và poll, hai lời gọi có thể quan sát những trạng thái khác nhau.

ArrayDeque không được đồng bộ hóa sẵn để nhiều luồng tùy ý cùng sửa. Các quy tắc về ô trống trong cách triển khai không phải cơ chế phối hợp giữa các luồng. Không thể dựa vào việc “đã kiểm tra khác null” để thay thế một hợp đồng chia sẻ dữ liệu đúng.

Chi tiết mảng vòng ở phần giải thích được đối chiếu với OpenJDK 17. Các số chỉ vị trí, kích thước mảng và cách tăng dung lượng không phải API để mã ứng dụng bám vào. Các ví dụ chỉ dùng các phương thức công khai để kiểm chứng những kết quả mà người dùng lớp được phép dựa vào.

Nếu cần tìm nguyên nhân NullPointerException, xác định trước lỗi là do biến deque null, do chèn phần tử null, do lấy từ một deque rỗng rồi dùng kết quả không kiểm tra, hay do trường bên trong đối tượng. Không gom các nguyên nhân ấy thành một câu “ArrayDeque lỗi null”.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều cần hiểu đúng |
| --- | --- |
| “Mảng Java không thể có null” | Mảng tham chiếu có thể; ArrayDeque cấm null như một thành viên theo hợp đồng |
| “Offer dùng false nên offer(null) không ném lỗi” | Dữ liệu null bị cấm vẫn dẫn đến NullPointerException |
| “Dùng push có thể đưa null vào ngăn xếp” | Push vẫn phải tuân chính sách của cùng ArrayDeque |
| “Đổi biến sang Deque sẽ bỏ kiểm tra” | Đối tượng thực tế vẫn là ArrayDeque |
| “Có null trong ô mảng nghĩa là deque đang chứa null” | Ô không giữ thành viên khác với một phần tử hợp lệ |
| “Poll xóa ô thì đối tượng được thu gom ngay” | Nó bỏ một tham chiếu; còn phải xét các tham chiếu khác và cơ chế thu gom |
| “AddAll ném lỗi thì đích chắc chắn không thay đổi” | Có thể đã thêm một phần trước khi gặp null |
| “List.of có null là nguồn tốt để kiểm thử deque” | List.of có thể lỗi trước khi deque được gọi |
| “ArrayDeque sẽ kiểm tra mọi trường bên trong” | Nó kiểm tra tham chiếu phần tử, không tự áp mọi quy tắc của kiểu miền |
| “Optional.empty chính là null” | Đó là một Optional khác null, không chứa giá trị bên trong |
| “Chuỗi có chữ null là tham chiếu null” | Chuỗi là một đối tượng thật với nội dung ký tự |
| “Một số Collection nhận null thì ArrayDeque cũng phải nhận” | Chính sách của lớp nhận cần được đọc riêng |
| “Thay null bằng chuỗi rỗng không làm đổi dữ liệu” | Đó là một phép chuyển đổi ý nghĩa, cần hợp đồng rõ |

Một thói quen hữu ích là phân biệt ba cấp: đối tượng chứa, tham chiếu phần tử, và dữ liệu bên trong phần tử. Nhiều lỗi chỉ xuất hiện vì ba cấp ấy bị gọi chung bằng một từ “null”.

## 18. Thực hành có lời giải

### Bài 1: offer null khi còn rất nhiều chỗ

Một ArrayDeque vừa được tạo rỗng. OfferLast(null) có trả false vì chưa thêm được không?

**Lời giải:** Không. Null là phần tử bị cấm nên lời gọi ném NullPointerException. Trạng thái dung lượng không biến dữ liệu bị cấm thành một giá trị hợp lệ.

### Bài 2: cùng đối tượng, kiểu biến khác nhau

Bạn giữ một ArrayDeque qua biến Deque<String> rồi gọi push(null). Chính sách có thay đổi không?

**Lời giải:** Không. Đối tượng thực tế vẫn là ArrayDeque và push là một đường chèn vào nó. Null vẫn bị từ chối.

### Bài 3: ô trống trong mảng

Một sơ đồ mảng bên trong có nhiều ô null nhưng size của deque bằng 3. Có phải deque đang giữ các thành viên null không?

**Lời giải:** Không. Những ô không chứa thành viên có thể mang null để biểu diễn ô trống. Size và thứ tự thành viên không đồng nhất với toàn bộ độ dài mảng vật lý.

### Bài 4: đọc kết quả poll

ArrayDeque<String> hợp lệ đang chứa một A. PollFirst hai lần lần lượt cho gì?

**Lời giải:** Lần đầu trả A và xóa nó. Lần sau trả null vì không còn thành viên. Với lớp này, không có một phần tử null thật để gây nhập nhằng.

### Bài 5: thêm lô lỗi giữa chừng

Deque trước là `[stable]`, lô Arrays.asList gồm `before, null, after`. Có thể coi NullPointerException từ addAll là bằng chứng stable là thành viên duy nhất sau đó không?

**Lời giải:** Không. Ví dụ trong chương trình giữ `[stable, before]` sau lỗi. Phần đầu lô có thể đã được thêm, còn null không được lưu. Muốn từ chối lô trước khi sửa đích, cần kiểm tra trước theo hợp đồng phù hợp.

### Bài 6: phép kiểm thử lỗi sai nơi

Bạn tạo List.of chứa null rồi định truyền vào ArrayDeque. Ngoại lệ xuất hiện. Có thể kết luận hàm khởi tạo ArrayDeque đã chạy và từ chối nguồn không?

**Lời giải:** Không nếu lỗi xuất hiện lúc tạo List.of. Cần một nguồn thật sự cho phép null, chẳng hạn Arrays.asList, để đi tới bước kiểm tra deque nhận dữ liệu.

### Bài 7: đối tượng có trường null

Có thể thêm `new Message(null)` vào ArrayDeque<Message> không?

**Lời giải:** Có theo chính sách tham chiếu phần tử của ArrayDeque, vì đối tượng Message khác null. Nếu mô hình yêu cầu payload bắt buộc có, điều kiện đó phải được kiểm tra riêng.

### Bài 8: Optional.empty

Một ArrayDeque<Optional<String>> có thành viên Optional.empty. PollFirst trả đối tượng gì? Nó khác tình trạng deque rỗng thế nào?

**Lời giải:** Nó trả một Optional khác null nhưng không có giá trị bên trong. Khi deque rỗng, pollFirst trả null ở cấp tham chiếu phần tử.

### Bài 9: tìm null có phải chèn null không?

ArrayDeque hiện chứa stable. Contains(null) và remove(null) trong chương trình làm gì?

**Lời giải:** Chúng trả false và không thay đổi nội dung. Đây là tìm/xóa theo giá trị, không phải cố chèn một thành viên null. Không suy hành vi của mọi tham số null chỉ từ quy tắc chèn.

### Bài 10: chuỗi “null”

Bạn thêm chuỗi `"null"` rồi kiểm tra phần tử lấy ra bằng `== null`. Kết quả là gì?

**Lời giải:** False. Có một đối tượng String chứa bốn ký tự. Chuỗi rỗng cũng là tham chiếu thật và được nhận, dù độ dài bằng 0.

### Bài 11: xóa và thu gom

Sau pollFirst, deque không còn giữ thành viên X. Biến bên ngoài vẫn trỏ đến X. Có thể nói X đã được thu gom ngay không?

**Lời giải:** Không. Deque đã bỏ tham chiếu của nó, nhưng biến bên ngoài vẫn giữ đối tượng. API không cam kết thời điểm thu gom bộ nhớ.

### Bài 12: lọc hay từ chối?

Nguồn có null nhưng mỗi vị trí đều biểu diễn một công việc phải được ghi nhận. Có nên tự bỏ mọi null rồi báo nhận đủ lô không?

**Lời giải:** Không nếu điều đó làm mất ý nghĩa dữ liệu. Cần từ chối hoặc dùng mô hình thông điệp tường minh theo hợp đồng. Bỏ qua là một chính sách có thể làm thay đổi số và ý nghĩa thành viên, không phải sửa lỗi trong suốt.

## 19. Cách áp dụng trong mã thật

Ở ranh giới đưa dữ liệu vào ArrayDeque, hãy kiểm tra tham chiếu phần tử và xác định chính sách nếu nguồn có thể chứa null. Với lô dữ liệu, quyết định rõ có được thêm một phần trước lỗi hay phải kiểm tra trước.

Nếu cần biểu diễn “có một thông điệp nhưng nội dung chưa có”, giữ một đối tượng phần tử khác null và mô tả sự vắng mặt bên trong bằng kiểu dữ liệu phù hợp.

Khi đọc deque, dùng null theo đúng ý nghĩa báo không có phần tử và phân biệt phép xem với phép lấy ra. Sự rõ ràng ở hai ranh giới chèn/đọc là lợi ích trực tiếp của hợp đồng ArrayDeque không lưu null.
