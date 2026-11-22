# So sánh ArrayDeque, LinkedList và Stack

## 1. So sánh theo vai trò cần dùng

Cùng một dãy A, B, C có thể được quản lý như hàng đợi vào trước ra trước hoặc ngăn xếp vào sau ra trước. ArrayDeque, LinkedList và Stack đều có thể xuất hiện trong mã xử lý các dãy ấy, nhưng chúng không phải ba lớp thay thế hoàn toàn cho nhau.

Trong mã một luồng cần thao tác hàng đợi hoặc ngăn xếp không null, `Deque<E>` với `ArrayDeque<E>` thường là điểm bắt đầu phù hợp. LinkedList còn có vai trò List và khả năng cập nhật qua một con trỏ duyệt đã xác định vị trí. Stack là lớp cũ kế thừa Vector, thường gặp ở mã cần tương thích.

Quyết định nên dựa trên thao tác và hợp đồng:

| Khía cạnh | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| Cấu trúc chính | Mảng vòng có thể tăng | Danh sách liên kết đôi | Mảng có thể tăng của Vector |
| Giao diện vai trò nổi bật | Deque, Queue | List, Deque, Queue | List qua Vector; API Stack riêng |
| Dùng FIFO | Có | Có | Không triển khai Queue/Deque |
| Dùng LIFO | Có qua push/pop | Có qua push/pop | Có qua API Stack |
| Truy cập theo chỉ số | Không có API get(index) | Có, cần đi qua nút | Có qua Vector |
| Phần tử null | Không chấp nhận | Chấp nhận | Chấp nhận |
| Đồng bộ sẵn | Không | Không | Các thao tác nền tảng dùng đồng bộ của Vector/Stack |
| Đặc điểm cần chú ý | Tăng mảng có chi phí từng đợt | Mỗi phần tử có nút và liên kết | API cũ, có cả các thao tác List/Vector |

Các đặc điểm nền được đối chiếu với tài liệu Java 17 của [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [Stack](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html) và [Vector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html).

Bài này giải thích vì sao các khác biệt đó quan trọng, thay vì chỉ chọn một lớp bằng khẩu hiệu “mảng nhanh” hoặc “danh sách liên kết thêm/xóa O(1)”.

## 2. Cấu trúc lưu trữ tạo ra những đánh đổi nào?

### 2.1. ArrayDeque: các tham chiếu trong một mảng vòng

Mô hình:

```text
mảng nền:
[ C | D | . | . | A | B ]
                  ^
                 đầu logic

dãy logic: A, B, C, D
```

Vị trí đầu và cuối được đưa vòng qua biên mảng. Thêm/lấy ở đầu không cần dồn toàn bộ các phần tử còn lại về ô 0.

Nếu thiếu chỗ, cấu trúc tăng mảng và tổ chức lại tham chiếu. Vì vậy, có những lần thêm tốn nhiều công hơn các lần thông thường.

Các ô tham chiếu nằm trong mảng không có nghĩa toàn bộ đối tượng phần tử cũng được đặt liên tiếp trong bộ nhớ. Đối tượng có thể tồn tại độc lập; mảng giữ tham chiếu tới chúng.

### 2.2. LinkedList: mỗi phần tử ở một nút liên kết đôi

Mô hình:

```text
first
  |
  v
[prev | A | next] <-> [prev | B | next] <-> [prev | C | next]
                                                   ^
                                                   |
                                                  last
```

Nhờ giữ hai đầu, thêm hoặc gỡ first/last không phải tìm từ đầu qua toàn bộ danh sách. Nhưng để lấy phần tử ở một chỉ số bất kỳ, cần lần theo liên kết từ đầu gần hơn.

Mỗi phần tử còn có một nút chứa thông tin liên kết. Điều đó tạo chi phí cấp phát và bộ nhớ ngoài tham chiếu tới dữ liệu. Không nên nêu một số byte cố định cho mọi JVM nếu chưa xác định cấu hình và cách đo.

### 2.3. Stack: hành vi LIFO trên nền Vector

Stack kế thừa Vector. Đỉnh stack được đặt ở cuối dãy của Vector:

```text
index:       0    1    2
dữ liệu:     A    B    C
             ^         ^
            đáy       đỉnh
```

Push thêm vào cuối, pop gỡ ở cuối. Iterator thông thường đi theo thứ tự chỉ số từ 0 trở lên, nên đi từ đáy tới đỉnh.

Do kế thừa, Stack còn có các phương thức List/Vector như get theo chỉ số hoặc thêm vào giữa. Những khả năng ấy không cần thiết cho một giao diện ngăn xếp thuần và có thể làm ý định sử dụng kém rõ.

[Tài liệu Stack Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html) khuyến nghị dùng Deque và các triển khai của nó để có tập thao tác LIFO phù hợp hơn trong mã mới.

## 3. Độ phức tạp phải gắn với đúng thao tác

Gọi n là số phần tử hiện có. Bảng sau mô tả các thao tác thông dụng với giả định phép so sánh giá trị có chi phí hằng số:

| Thao tác | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| Thêm/lấy để làm LIFO | Thêm O(1) khấu hao; lấy đầu O(1) | O(1) ở đầu, có cấp/gỡ nút | Push O(1) khấu hao; pop cuối O(1), kèm cơ chế đồng bộ |
| Thêm cuối, lấy đầu để làm FIFO | O(1) khấu hao cho thao tác đầu/cuối | O(1) cho liên kết ở hai đầu | Không có API Queue; mô phỏng bằng remove(0) phải dịch dãy |
| Xem đầu hoặc đỉnh | O(1) | O(1) | O(1), theo API Stack |
| get(i) | Không hỗ trợ theo chỉ số | O(n) trong trường hợp tổng quát | O(1) qua Vector |
| Tìm hoặc xóa theo giá trị | O(n) trong trường hợp tổng quát | O(n) để tìm vị trí | O(n) trong trường hợp tổng quát |
| Chèn giữa khi chỉ có chỉ số | Không có API chèn theo chỉ số | Phải tìm vị trí, tổng quát O(n) | Dịch các phần tử phía sau, O(n) |
| Cập nhật tại ListIterator đã ở vị trí | Không có ListIterator | Thay đổi liên kết cục bộ có thể O(1) | Không phải lợi thế tương tự vì nền mảng |
| Duyệt toàn bộ | O(n) | O(n) | O(n) |

Các con số không có nghĩa ba cấu trúc có cùng thời gian thực tế khi cùng ghi O(1). Cấp phát nút, sao chép mảng, đi theo tham chiếu và đồng bộ đều có chi phí khác nhau.

### 3.1. Khấu hao khác với từng lần gọi

Với mảng có thể tăng, đa số lần thêm chỉ ghi vào vùng có sẵn. Thỉnh thoảng phải cấp phát và chuyển nhiều tham chiếu.

O(1) khấu hao nghĩa tổng chi phí có thể được phân bổ trên một chuỗi thao tác; một lần thêm đúng lúc tăng mảng vẫn có thể tốn O(n).

Nếu yêu cầu có giới hạn độ trễ chặt, chỉ nhìn cận khấu hao chưa đủ. Cần đánh giá quy mô, lịch sử sử dụng và cơ chế cấp phát trong môi trường thật.

### 3.2. LinkedList không có “xóa giữa miễn phí”

Nếu đã có một ListIterator đang đứng ở vị trí cần cập nhật, thay đổi các liên kết lân cận có thể rẻ.

Nhưng nếu đầu vào chỉ là chỉ số 5000 hoặc một giá trị cần tìm, LinkedList phải đi tới vị trí ấy trước. Chi phí tìm không biến mất chỉ vì bước nối/gỡ nút là O(1).

Đặc biệt, lặp theo chỉ số:

```java
// Trích đoạn dễ tốn nhiều lần đi lại trên LinkedList.
for (int i = 0; i < list.size(); i++) {
    use(list.get(i));
}
```

có thể tạo tổng công việc bậc hai trên LinkedList. Một vòng duyệt iterator hoặc for-each phù hợp với cách lưu trữ liên kết hơn. Đây là trích đoạn minh họa, không phải chương trình độc lập.

### 3.3. Bộ nhớ và tính cục bộ

ArrayDeque và Vector giữ các tham chiếu trong mảng, còn LinkedList phải đi qua các nút. Điều này ảnh hưởng tính cục bộ khi đọc và lượng cấp phát.

Ngược lại, mảng có thể có sức chứa dư sau một đỉnh tải và phải xử lý tăng dung lượng. LinkedList có chi phí nút trên từng phần tử.

Không thể suy ra một tỷ lệ nhanh hơn cố định từ bảng độ phức tạp. Nếu hiệu năng là yêu cầu thực tế, đo bằng kịch bản đại diện, kiểm tra cả lượng cấp phát và độ trễ, không chỉ một vòng chạy nhỏ.

## 4. Chương trình 1: cùng vai trò có thể cho cùng đầu ra

Lưu tệp `ThreeCollectionsRolesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.Queue;
import java.util.Stack;

public class ThreeCollectionsRolesDemo {
    static List<String> drainQueue(Queue<String> queue) {
        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.remove());
        }
        return result;
    }

    static List<String> drainDequeStack(Deque<String> stack) {
        List<String> result = new ArrayList<>();
        while (!stack.isEmpty()) {
            result.add(stack.pop());
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C");

        Queue<String> arrayQueue = new ArrayDeque<>(input);
        Queue<String> linkedQueue = new LinkedList<>(input);
        System.out.println("ArrayDeque FIFO = " + drainQueue(arrayQueue));
        System.out.println("LinkedList FIFO = " + drainQueue(linkedQueue));

        Deque<String> arrayStack = new ArrayDeque<>();
        Deque<String> linkedStack = new LinkedList<>();
        Stack<String> legacyStack = new Stack<>();
        for (String item : input) {
            arrayStack.push(item);
            linkedStack.push(item);
            legacyStack.push(item);
        }

        System.out.println("ArrayDeque iteration = " + arrayStack);
        System.out.println("LinkedList iteration = " + linkedStack);
        System.out.println("Stack iteration = " + legacyStack);
        System.out.println("ArrayDeque LIFO = " + drainDequeStack(arrayStack));
        System.out.println("LinkedList LIFO = " + drainDequeStack(linkedStack));

        List<String> legacyOutput = new ArrayList<>();
        while (!legacyStack.empty()) {
            legacyOutput.add(legacyStack.pop());
        }
        System.out.println("Stack LIFO = " + legacyOutput);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ThreeCollectionsRolesDemo.java
java ThreeCollectionsRolesDemo
```

Kết quả của lần chạy kiểm chứng:

```text
ArrayDeque FIFO = [A, B, C]
LinkedList FIFO = [A, B, C]
ArrayDeque iteration = [C, B, A]
LinkedList iteration = [C, B, A]
Stack iteration = [A, B, C]
ArrayDeque LIFO = [C, B, A]
LinkedList LIFO = [C, B, A]
Stack LIFO = [C, B, A]
```

Các chương trình trong bài dùng ngôn ngữ và API có ở Java 17 trở lên, được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

### 4.1. ArrayDeque và LinkedList đều làm FIFO qua Queue

Hai đối tượng được tạo từ cùng dãy A, B, C. Khi xử lý bằng Queue.remove, cả hai cho A, B, C.

Điều đó cho thấy có thể chọn một giao diện để biểu đạt vai trò. Nó không có nghĩa null, bộ nhớ hoặc chi phí ở các thao tác khác đều giống nhau.

Các vòng trong chương trình là mã một luồng, nên kiểm tra rỗng rồi remove không có cập nhật chen vào. Không tự chuyển giả định đó sang nhiều luồng.

### 4.2. Cả ba có thể cho cùng thứ tự pop

Sau push A, B, C, cả ba lấy ra C, B, A khi dùng đúng API LIFO.

Nhưng thứ tự duyệt ban đầu khác:

```text
ArrayDeque dùng push: [C, B, A]  -> đỉnh ở first
LinkedList dùng push: [C, B, A]  -> đỉnh ở first
Stack:                [A, B, C]  -> đỉnh ở cuối Vector
```

Cùng thứ tự pop không đồng nghĩa cùng thứ tự iterator. Đây là khác biệt quan trọng khi hiển thị lịch sử, serialize dãy hoặc sao chép sang collection khác.

### 4.3. Chương trình này không phải benchmark

Các dòng in chỉ kiểm tra hợp đồng thứ tự. Không đo thời gian nên không dùng output để kết luận lớp nào nhanh hơn.

Ngay cả khi thêm một đồng hồ vào ví dụ nhỏ, kết quả còn chịu khởi động JVM, tối ưu hóa, cấp phát và công việc in ra. Muốn đánh giá hiệu năng phải thiết kế phép đo riêng.

## 5. API rỗng và null: cùng tên chưa chắc cùng hành vi

### 5.1. Peek trên Deque khác peek trên Stack cũ

| Lời gọi khi rỗng | ArrayDeque | LinkedList | Stack |
|---|---|---|---|
| `peek()` | null | null | EmptyStackException |
| `pop()` | NoSuchElementException | NoSuchElementException | EmptyStackException |
| Xem và muốn ngoại lệ kiểu Deque | `getFirst()` | `getFirst()` | API Stack.peek riêng |
| Lấy và muốn null kiểu Queue/Deque | `poll()` hoặc `pollFirst()` | `poll()` hoặc `pollFirst()` | Không có phương thức poll của Queue |

Vì vậy, đổi khai báo từ Stack sang Deque rồi giữ nguyên tên peek/pop vẫn có thể làm thay đổi nhánh xử lý rỗng hoặc loại ngoại lệ được bắt.

Nếu ngoại lệ là một phần hợp đồng của hàm công khai, cần quyết định có giữ tương thích bằng lớp bao quanh hay cập nhật hợp đồng một cách rõ ràng.

### 5.2. Null làm mất nghĩa đơn giản của poll/peek

ArrayDeque cấm phần tử null. Khi poll trả null, không có sự mơ hồ với một thành viên null thật.

LinkedList nhận null. Nếu phần tử đầu là null, poll có thể trả null trong khi vừa gỡ một phần tử thật và danh sách vẫn còn dữ liệu khác.

Stack cũng có thể giữ null. Peek trả null khi đỉnh là thành viên null thật, nhưng peek trên Stack rỗng ném ngoại lệ. Không dùng “peek khác null” để kiểm tra Stack có phần tử.

Nhận null ở collection không có nghĩa null là một mô hình dữ liệu tốt cho mọi hàng đợi. Nếu muốn các mẫu xử lý bằng poll đến null, nên xác lập dữ liệu thành viên không null.

### 5.3. Push có kiểu trả về khác nhau

- `Stack.push(e)` trả lại e.
- `Deque.push(e)` trả void.

Mã cũ dùng biểu thức như gán kết quả push hoặc truyền nó làm đối số sẽ không thể đổi lớp bằng cách thay tên kiểu đơn thuần.

Nếu cần giữ giá trị vừa đẩy, hãy giữ biến phần tử rồi push, thay vì dựa vào một giá trị trả về không có trong Deque.

## 6. Chương trình 2: đối chiếu rỗng và null

Lưu tệp `EmptyAndNullComparisonDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedList;
import java.util.Stack;

public class EmptyAndNullComparisonDemo {
    static void reportFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected a runtime exception");
        } catch (RuntimeException ex) {
            System.out.println(label + " = " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> array = new ArrayDeque<>();
        LinkedList<String> linked = new LinkedList<>();
        Stack<String> legacy = new Stack<>();

        System.out.println("empty ArrayDeque peek = " + array.peek());
        System.out.println("empty LinkedList peek = " + linked.peek());
        reportFailure("empty Stack peek", legacy::peek);
        reportFailure("empty ArrayDeque pop", array::pop);
        reportFailure("empty LinkedList pop", linked::pop);
        reportFailure("empty Stack pop", legacy::pop);
        reportFailure("ArrayDeque offer null", () -> array.offerLast(null));

        linked.offerLast(null);
        linked.offerLast("X");
        System.out.println("LinkedList size with null = " + linked.size());
        System.out.println("LinkedList empty with null = " + linked.isEmpty());
        System.out.println("LinkedList peek null member = " + linked.peek());
        System.out.println("LinkedList poll null member = " + linked.poll());
        System.out.println("LinkedList remaining = " + linked);

        System.out.println("Stack push null result = " + legacy.push(null));
        System.out.println("Stack empty with null = " + legacy.empty());
        System.out.println("Stack peek null member = " + legacy.peek());
        System.out.println("Stack pop null member = " + legacy.pop());
        System.out.println("Stack empty after pop = " + legacy.empty());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 EmptyAndNullComparisonDemo.java
java EmptyAndNullComparisonDemo
```

Kết quả của lần chạy kiểm chứng:

```text
empty ArrayDeque peek = null
empty LinkedList peek = null
empty Stack peek = EmptyStackException
empty ArrayDeque pop = NoSuchElementException
empty LinkedList pop = NoSuchElementException
empty Stack pop = EmptyStackException
ArrayDeque offer null = NullPointerException
LinkedList size with null = 2
LinkedList empty with null = false
LinkedList peek null member = null
LinkedList poll null member = null
LinkedList remaining = [X]
Stack push null result = null
Stack empty with null = false
Stack peek null member = null
Stack pop null member = null
Stack empty after pop = true
```

Hàm reportFailure làm ví dụ dừng bằng AssertionError nếu một thao tác không ném ngoại lệ như dự kiến. Các tên lớp ngoại lệ trong output là kết quả thực tế đã được chạy, không phải nhãn dự đoán.

### 6.1. ArrayDeque vẫn có thể ném lỗi ở offer

Offer có thể dùng boolean cho một số thất bại như thiếu chỗ ở một triển khai giới hạn dung lượng, nhưng không biến mọi đầu vào sai thành false.

ArrayDeque.offerLast(null) ném NullPointerException. Do đó, chính sách dữ liệu cần được kiểm tra riêng với chính sách rỗng hoặc đầy.

### 6.2. LinkedList còn X sau khi poll trả null

Danh sách có hai phần tử: null rồi X. Lời gọi poll gỡ thành viên đầu null và trả null; danh sách còn X.

Mẫu:

```java
// Không tổng quát nếu queue có thể chứa thành viên null.
String next;
while ((next = queue.poll()) != null) {
    process(next);
}
```

có thể dừng trước khi lấy hết dữ liệu nếu dùng một LinkedList chứa null. Trích đoạn này minh họa lỗi giả định, không phải chương trình độc lập.

Với mã một luồng cho phép null, có thể tách điều kiện rỗng khỏi giá trị lấy được và xử lý null có chủ đích. Với nhiều luồng, chuỗi kiểm tra rồi lấy còn có yêu cầu phối hợp riêng.

### 6.3. Stack giữ null mà không rỗng

Sau push null, empty trả false; peek và pop trả null là dữ liệu thật. Sau pop, empty mới trả true.

Điều này nhắc rằng thay Stack hoặc LinkedList có null bằng ArrayDeque cần một quyết định về dữ liệu, không chỉ sửa import và constructor.

Không âm thầm lọc null nếu mỗi lần xuất hiện có ý nghĩa nghiệp vụ. Có thể phải từ chối đầu vào, đổi kiểu biểu diễn hoặc chọn cấu trúc phù hợp.

## 7. Khi nào khả năng List của LinkedList có giá trị?

ArrayDeque chủ yếu phục vụ các thao tác hai đầu. LinkedList còn có List và ListIterator, cho phép một con trỏ duyệt đi qua dãy và cập nhật tại vị trí đang biết.

Ví dụ, một quy trình đang quét tuần tự các điểm trong hành trình, thỉnh thoảng chèn một điểm ngay trước vị trí tiếp theo hoặc gỡ điểm vừa đọc. Nếu con trỏ đã ở đó, sửa liên kết cục bộ không cần tìm lại vị trí theo chỉ số.

Cần giữ hai bước tách biệt:

```text
đi đến vị trí cần cập nhật
    +
cập nhật ở vị trí đã biết
```

Bước thứ hai có thể O(1) với nút liên kết; bước thứ nhất vẫn có chi phí di chuyển.

Không chọn LinkedList chỉ vì nghe câu “chèn giữa O(1)” nếu mỗi thao tác của ứng dụng lại bắt đầu bằng một chỉ số ngẫu nhiên và phải đi tìm từ đầu hoặc cuối.

### 7.1. Không phải thay thế List bằng Deque chỉ để đổi triển khai

Nếu một hàm dùng `List.get(i)`, `ListIterator.add` hoặc thao tác theo chỉ số, ArrayDeque không đáp ứng cùng giao diện.

Khi ấy, quyết định thiết kế không chỉ là thay `new LinkedList<>()` bằng `new ArrayDeque<>()`. Cần xem thuật toán có thật sự cần khả năng List hay có thể được diễn đạt lại bằng thao tác hai đầu.

Ngược lại, nếu mã chỉ dùng offer/poll hoặc push/pop, khai báo bằng Queue/Deque giúp biểu đạt vai trò rõ và cho phép chọn triển khai phù hợp hơn.

### 7.2. Cấp phát nút và vị trí đã biết

LinkedList phải cấp phát nút khi thêm. O(1) của số liên kết cần thay không có nghĩa công việc cấp phát, thu gom rác hoặc truy cập bộ nhớ là miễn phí.

Do đó, lợi ích của ListIterator cần được đánh giá trong thuật toán cụ thể: mức độ cập nhật cục bộ, cách duyệt và dữ liệu thực tế, thay vì chỉ nhìn một thao tác cô lập.

## 8. Chương trình 3: vị trí con trỏ và cập nhật cục bộ

Lưu tệp `LinkedListCursorComparisonDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorComparisonDemo {
    public static void main(String[] args) {
        LinkedList<String> route = new LinkedList<>(List.of("A", "C", "D"));
        ListIterator<String> cursor = route.listIterator(1);

        System.out.println("initial route = " + route);
        cursor.add("B");
        System.out.println("after cursor add B = " + route);
        System.out.println("cursor next = " + cursor.next());
        cursor.remove();
        System.out.println("after cursor remove = " + route);
        System.out.println("cursor previous = " + cursor.previous());
        cursor.set("B2");
        System.out.println("after cursor set = " + route);
        System.out.println("indexed get 1 = " + route.get(1));

        route.addFirst("START");
        route.addLast("END");
        System.out.println("with both ends = " + route);
        System.out.println("remove first = " + route.removeFirst());
        System.out.println("remove last = " + route.removeLast());
        System.out.println("final route = " + route);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 LinkedListCursorComparisonDemo.java
java LinkedListCursorComparisonDemo
```

Kết quả của lần chạy kiểm chứng:

```text
initial route = [A, C, D]
after cursor add B = [A, B, C, D]
cursor next = C
after cursor remove = [A, B, D]
cursor previous = B
after cursor set = [A, B2, D]
indexed get 1 = B2
with both ends = [START, A, B2, D, END]
remove first = START
remove last = END
final route = [A, B2, D]
```

### 8.1. Chi phí tìm nằm ở lúc tạo hoặc di chuyển con trỏ

`listIterator(1)` xác định vị trí trước phần tử C. Với dữ liệu nhỏ, chi phí này không nổi bật; với dữ liệu lớn ở giữa dãy, cần nhớ rằng việc tìm vị trí vẫn tồn tại.

Sau đó, cursor.add chèn B tại vị trí con trỏ. Cursor.next đọc C; cursor.remove gỡ đúng phần tử vừa đọc. Không có một lời gọi tìm C lại theo giá trị.

Chương trình không đo thời gian và không tự chứng minh một tỷ lệ hiệu năng. Nó giúp chỉ ra điều kiện “đã có vị trí” nghĩa là gì trong API.

### 8.2. Iterator có quy tắc trạng thái

Remove của ListIterator liên quan tới phần tử vừa được next hoặc previous trả về. Nó không phải “xóa một phần tử bất kỳ” mà không cần biết trạng thái duyệt.

Set thay giá trị phần tử vừa đọc; add chèn tại vị trí con trỏ. Khi xây thuật toán cập nhật, cần giữ đúng hợp đồng các thao tác ấy.

Sau khi chương trình thay đổi hai đầu trực tiếp qua route, nó không dùng lại cursor cũ. Không nên tiếp tục dùng một iterator sau các thay đổi cấu trúc qua đường khác rồi mặc định trạng thái vẫn hợp lệ.

### 8.3. Cùng một LinkedList có hai vai trò API

Route còn có addFirst/addLast/removeFirst/removeLast, nên cũng dùng được như Deque ở hai đầu.

Điều này thể hiện sự linh hoạt, nhưng không có nghĩa ứng dụng nên trộn tùy tiện truy cập giữa dãy với một ngăn xếp cần bất biến chỉ thay đổi ở đỉnh. Chọn giao diện và quyền sở hữu phù hợp vẫn quan trọng.

## 9. Đồng bộ của Stack bảo vệ tới đâu?

Stack kế thừa Vector, một lớp có cơ chế đồng bộ cho các thao tác nền tảng. Điều đó khác với ArrayDeque và LinkedList không tự đồng bộ.

Nhưng cần phân biệt một thao tác và một chuỗi thao tác.

Giả sử stack đang có đúng một phần tử:

```text
Luồng 1: gọi empty() -> false
Luồng 2: gọi pop()   -> lấy phần tử cuối
Luồng 1: gọi pop()   -> EmptyStackException
```

Từng lời gọi vẫn có thể thực hiện đúng cơ chế đồng bộ của lớp. Lỗi giả định nằm ở khoảng giữa hai lời gọi của luồng 1: trạng thái đã thay đổi.

### 9.1. “Có synchronized” không phải mọi quy trình đều nguyên tử

Những chuỗi như kiểm tra-rồi-lấy, duyệt-rồi-cập nhật hoặc sao chép nhiều bước cần một ranh giới phối hợp phù hợp cho cả yêu cầu.

Trong mã cũ bắt buộc giữ Stack, có thể cần đồng bộ toàn bộ chuỗi liên quan theo cùng cơ chế mà mọi bên tham gia tuân thủ. Trong thiết kế mới, nên xem lại mô hình xử lý và API đồng thời cần thiết.

Không dùng Stack chỉ vì nó có đồng bộ rồi coi các yêu cầu về chờ dữ liệu, giới hạn số lượng, xử lý thất bại hoặc phối hợp nhiều bên đã được đáp ứng.

### 9.2. Iterator không phải bản chụp an toàn đồng thời

Các iterator của các lớp trong bài không tự cung cấp một ảnh chụp ổn định cho mọi thay đổi đồng thời. Fail-fast có thể giúp phát hiện sửa đổi, nhưng không bảo đảm một thuật toán dùng chung dữ liệu đã đúng.

Đừng dùng việc “không thấy ConcurrentModificationException trong vài lần chạy” làm bằng chứng an toàn nhiều luồng.

Tương tự, một Stack có những phương thức đồng bộ không đồng nghĩa vòng for-each trên nó tự giữ một khóa bao trùm toàn bộ vòng lặp.

### 9.3. Chọn vai trò đồng thời trước khi chọn lớp

Nếu dữ liệu chỉ thuộc một luồng, không nên chọn Stack chỉ để có một cơ chế đồng bộ mà thuật toán không cần.

Nếu dữ liệu được chia sẻ, hãy xác định các thao tác cần nguyên tử, có cần chờ khi rỗng/đầy không và chính sách giới hạn. Khi đó, so sánh ba lớp này mới là một phần của quyết định; chưa phải toàn bộ thiết kế.

Không bỏ đồng bộ khỏi một hệ thống chỉ vì ArrayDeque thường phù hợp với FIFO/LIFO đơn luồng. Điều kiện sử dụng là một phần của lựa chọn.

## 10. Chuyển mã Stack sang Deque cần kiểm tra những gì?

Một khai báo LIFO mới thường là:

```java
// Trích đoạn; cần import java.util.Deque và ArrayDeque.
Deque<String> history = new ArrayDeque<>();
```

Push thêm ở first; pop lấy first. Tuy nhiên, mã Stack cũ có thể phụ thuộc nhiều hơn hai thao tác đó.

| Điều mã cũ có thể phụ thuộc | Điều cần xem lại |
|---|---|
| Pop trên rỗng ném EmptyStackException | Deque.pop ném NoSuchElementException |
| Peek trên rỗng ném ngoại lệ | Deque.peek trả null; getFirst có ngoại lệ kiểu Deque |
| Stack.push trả lại phần tử | Deque.push trả void |
| Stack.empty | Deque dùng isEmpty |
| Stack.search trả độ sâu từ đỉnh | Deque không có API search tương đương trực tiếp |
| Iterator đi từ đáy lên đỉnh | Deque dùng push đi từ đỉnh xuống |
| Phần tử null hợp lệ | ArrayDeque từ chối null |
| Các thao tác Vector/List kế thừa | ArrayDeque không có truy cập/chèn theo chỉ số |
| Hành vi đồng bộ | ArrayDeque không tự giữ cơ chế ấy |
| Equals theo List | ArrayDeque không so sánh nội dung dãy bằng equals như List |

Không nên chuyển một kiểu công khai mà nhiều bên đang dùng bằng một phép thay văn bản đơn thuần. Trước hết cần xác định những hành vi nào thuộc hợp đồng thực sự.

### 10.1. Sao chép đúng dãy iterator chưa chắc đúng đỉnh stack

Stack push A, B, C sẽ duyệt ra A, B, C. Constructor ArrayDeque nhận collection giữ thứ tự iterator của nguồn, nên dãy mới là A, B, C từ first tới last.

Nếu sau đó dùng Deque.pop, giá trị lấy đầu là A, trong khi legacy Stack.pop phải lấy C.

Vì vậy:

```java
// Trích đoạn: không giữ cùng đỉnh nếu sau đó dùng Deque.push/pop.
Deque<String> copy = new ArrayDeque<>(legacyStack);
```

có thể sao chép đúng thứ tự duyệt nhưng sai ngữ nghĩa stack mong muốn.

### 10.2. Giữ quy ước đỉnh ở first

Với nguồn một luồng, không null và không bị thay đổi trong lúc sao chép, có thể duyệt từ đáy lên đỉnh rồi push từng phần tử vào Deque mới.

Mỗi phần tử mới trở thành first, nên đỉnh cuối cùng đúng là phần tử ở đỉnh Stack cũ.

Nếu nguồn có null, phải quyết định cách xử lý trước; đừng để một bản chuyển đổi dở dang được coi là thành công. Nếu nguồn được chia sẻ giữa nhiều luồng, cần lấy dữ liệu theo một ranh giới nhất quán phù hợp.

### 10.3. Một lựa chọn khác là đỉnh ở last

Có thể giữ thứ tự iterator A, B, C trong Deque mới nhưng dùng addLast/removeLast/getLast làm thao tác stack.

Cách đó cũng hợp lệ nếu toàn bộ mã dùng nhất quán cùng đầu. Nhưng không được vừa sao chép theo quy ước đỉnh last rồi lại dùng các tên push/pop vốn đặt đỉnh ở first.

Lựa chọn cần được thể hiện trong giao diện bao quanh hoặc quy tắc sử dụng, tránh để mỗi phần mã tự đoán.

## 11. Chương trình 4: giữ đúng phần tử sẽ được pop tiếp theo

Lưu tệp `StackToDequeMigrationDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Stack;

public class StackToDequeMigrationDemo {
    public static void main(String[] args) {
        Stack<String> legacy = new Stack<>();
        legacy.push("A");
        legacy.push("B");
        legacy.push("C");

        Deque<String> iteratorOrderCopy = new ArrayDeque<>(legacy);
        Deque<String> topPreservingCopy = new ArrayDeque<>();
        for (String item : legacy) {
            topPreservingCopy.push(item);
        }

        System.out.println("legacy bottom to top = " + legacy);
        System.out.println("legacy top = " + legacy.peek());
        System.out.println("legacy search B = " + legacy.search("B"));
        System.out.println("constructor copy first = "
                + iteratorOrderCopy.peekFirst());
        System.out.println("top-preserving copy = " + topPreservingCopy);
        System.out.println("top-preserving peek = " + topPreservingCopy.peek());

        List<String> output = new ArrayList<>();
        while (!topPreservingCopy.isEmpty()) {
            output.add(topPreservingCopy.pop());
        }
        System.out.println("migrated pop order = " + output);
        System.out.println("legacy remains = " + legacy);
        System.out.println("legacy top remains = " + legacy.peek());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 StackToDequeMigrationDemo.java
java StackToDequeMigrationDemo
```

Kết quả của lần chạy kiểm chứng:

```text
legacy bottom to top = [A, B, C]
legacy top = C
legacy search B = 2
constructor copy first = A
top-preserving copy = [C, B, A]
top-preserving peek = C
migrated pop order = [C, B, A]
legacy remains = [A, B, C]
legacy top remains = C
```

### 11.1. Constructor copy và top-preserving copy khác nhau

Constructor copy có first là A vì nó đi theo iterator của Stack. Bản top-preserving dùng push trong lúc duyệt, nên first là C.

Kết quả migrated pop order là C, B, A, đúng ngữ nghĩa LIFO cần giữ.

Stack gốc vẫn là A, B, C và đỉnh vẫn là C. Chương trình đã tạo container riêng chứ không tiêu thụ Stack cũ.

### 11.2. Search không phải contains

Stack.search(B) trả 2, nghĩa B ở vị trí thứ hai tính từ đỉnh theo quy ước 1-based của Stack. Deque.contains(B) chỉ trả một boolean, không thay thế ý nghĩa độ sâu đó.

Nếu ứng dụng thật sự cần vị trí từ đỉnh, phải xác định lại cách biểu đạt và chi phí tìm. Không thay search bằng contains chỉ để mã biên dịch được.

### 11.3. Sao chép container không sao chép sâu dữ liệu

Ví dụ dùng String bất biến, nên dễ quan sát sự tách riêng của container. Với đối tượng khả biến, cả hai container vẫn có thể giữ tham chiếu tới cùng đối tượng.

Việc chuyển lớp lưu trữ không tự giải quyết quyền sở hữu và vòng đời của từng phần tử.

## 12. Chọn lớp theo một yêu cầu cụ thể

### 12.1. Chỉ cần FIFO hoặc LIFO trong một luồng

Có thể bắt đầu bằng:

```java
// Trích đoạn biểu đạt vai trò.
Queue<Job> queue = new ArrayDeque<>();
Deque<Change> history = new ArrayDeque<>();
```

Job và Change là các kiểu nghiệp vụ trong chương trình bao quanh. ArrayDeque phù hợp khi dữ liệu không null và thao tác chính ở hai đầu.

Không cần chọn LinkedList chỉ vì tên “queue thường dùng linked list” nếu mã không tận dụng khả năng List hoặc con trỏ cập nhật.

### 12.2. Cần List cùng với thay đổi tại con trỏ đã có

LinkedList có thể có giá trị khi thuật toán đã duyệt tuần tự bằng ListIterator và cần chèn/gỡ cục bộ quanh vị trí ấy.

Nhưng phải tính cả chi phí cấp phát nút, đi qua liên kết và cách tiếp cận vị trí. Nếu chủ yếu truy cập ngẫu nhiên theo chỉ số, LinkedList thường không có lợi thế từ cấu trúc của nó.

Việc cần List không tự buộc chọn LinkedList; đó là dấu hiệu bài toán cần một so sánh theo thao tác List rộng hơn, thay vì chỉ so sánh hàng đợi/ngăn xếp.

### 12.3. Đang tích hợp với mã yêu cầu Stack

Nếu một API cũ yêu cầu đúng Stack hoặc dựa vào các phương thức kế thừa/ngoại lệ/đồng bộ của nó, giữ tương thích có thể là một ràng buộc thực tế.

Nên cô lập ràng buộc ấy ở ranh giới rõ và kiểm tra ngữ nghĩa trước khi chuyển. Khuyến nghị Deque cho mã LIFO mới không có nghĩa mọi mã Stack cũ đều phải đổi ngay trong một lần sửa không liên quan.

### 12.4. Cần hỗ trợ null

Trước hết hỏi null biểu đạt điều gì và có cần giữ như một phần tử thật không.

LinkedList hoặc Stack có thể nhận null, nhưng điều đó thay đổi cách đọc peek/poll và mẫu kết thúc vòng lặp. Nếu có thể biểu đạt trạng thái thiếu dữ liệu bằng một kiểu rõ hơn và giữ phần tử không null, việc dùng Queue/Deque thường dễ hiểu hơn.

Không chọn một collection chỉ để tránh một NullPointerException mà chưa quyết định ngữ nghĩa dữ liệu.

## 13. Bộ nhớ, độ trễ và các số đo cần đọc cẩn thận

Ba lớp có đánh đổi khác nhau, không phải một thứ hạng tuyệt đối cho mọi tải.

- ArrayDeque có mảng dự phòng và các lần tăng mảng; không có một nút liên kết riêng cho mỗi phần tử.
- LinkedList có nút và liên kết theo từng phần tử; thao tác hai đầu không phải tăng một mảng chung.
- Stack dựa trên Vector, có sức chứa dự phòng và chi phí đồng bộ liên quan đến cách dùng.

Sau một đỉnh tải, mảng có thể vẫn giữ sức chứa lớn dù số phần tử giảm. Điều đó cần được tách khỏi việc các tham chiếu phần tử đã được gỡ.

Một kết luận về bộ nhớ nên nói rõ đo số ô dự phòng, số đối tượng nút, lượng cấp phát hay tổng dữ liệu nghiệp vụ. Không chỉ nhìn size rồi mặc định các lớp dùng cùng bộ nhớ.

### 13.1. Cùng O(1) không nghĩa cùng độ trễ

Cấp phát, thu gom rác, đi theo tham chiếu, vùng nhớ sẵn có và khóa đồng bộ có thể tạo khác biệt thực tế.

Mặt khác, JVM có thể tối ưu một số trường hợp sử dụng khác nhau. Không dự đoán một tỷ lệ tốc độ cố định từ số từ khóa synchronized hoặc từ một sơ đồ mảng.

Nếu cần đo, dùng tập thao tác đúng với ứng dụng: thêm/lấy xen kẽ, độ sâu hoặc độ dài chờ đại diện, tải cấp phát và mức chia sẻ giữa các luồng.

### 13.2. Đừng đo những thao tác không cùng nghĩa

So sánh ArrayDeque.removeFirst với LinkedList.remove(Object) là so sánh hai yêu cầu khác nhau: một bên lấy đầu, một bên còn phải tìm giá trị.

Tương tự, so sánh Stack.pop với Deque.peek không cho biết chi phí hai cách triển khai stack, vì peek không gỡ dữ liệu.

Một phép đo chỉ hữu ích khi hợp đồng, dữ liệu và lượng công việc thực hiện tương ứng với nhau.

## 14. Những lỗi so sánh và chuyển đổi thường gặp

| Nhận định hoặc cách làm | Điều bị bỏ sót | Cách sửa |
|---|---|---|
| LinkedList luôn tốt hơn vì thêm/xóa O(1) | Có thể phải tìm vị trí và cấp phát nút | Tính toàn bộ đường đi tới cập nhật |
| ArrayDeque luôn nhanh nhất trong mọi tình huống | Không có bảo đảm tuyệt đối cho mọi tải | Chọn theo hợp đồng rồi đo khi cần |
| Dùng Stack cho FIFO vì có add/remove | API kế thừa không phải Queue; lấy đầu mảng có thể dịch dãy | Dùng vai trò Queue phù hợp |
| Stack có đồng bộ nên mọi chuỗi thao tác đều an toàn | Kiểm tra và cập nhật riêng có thể bị chen vào | Xác lập ranh giới nguyên tử cần thiết |
| LinkedList nhận null nên poll đến null luôn lấy hết | Null có thể là thành viên đầu thật | Cấm null hoặc xử lý tồn tại riêng |
| Chỉ thay Stack thành Deque rồi giữ catch EmptyStackException | Ngoại lệ rỗng đã đổi | Xem lại hợp đồng và nhánh xử lý |
| Copy Stack bằng constructor rồi pop ở first | Iterator Stack đi từ đáy lên | Giữ đúng quy ước đỉnh |
| Dùng kết quả push của Deque như Stack | Deque.push trả void | Giữ biến giá trị trước khi push |
| Thay LinkedList bằng ArrayDeque nhưng vẫn cần get(i) | ArrayDeque không là List | Xem lại giao diện và thuật toán |
| Dùng equals để đối chiếu hai ArrayDeque như List | ArrayDeque không có equals theo dãy | So dãy quan sát được bằng cách phù hợp |
| Chỉ so size sau chạy | Bỏ qua thứ tự và số lần xuất hiện cụ thể | Đối chiếu toàn bộ đầu ra |
| Bắt đầu từ một bài đo vài mili giây rồi chọn lớp | Kịch bản và khởi động JVM có thể chi phối | Dùng phép đo đại diện có phương pháp |

Khi đọc một lời khuyên chọn collection, hãy tìm điều kiện đi cùng: một luồng hay nhiều luồng, dữ liệu có null hay không, cần chỉ số hay chỉ cần hai đầu, và chi phí tìm vị trí đã được tính chưa.

## 15. Kiểm tra trước khi thay một lớp trong mã có sẵn

Một danh sách kiểm tra ngắn nhưng có tính quyết định:

1. Ghi rõ thứ tự lấy ra mong muốn: FIFO hay LIFO.
2. Kiểm tra ít nhất ba phần tử khác nhau và các bước thêm/lấy xen kẽ.
3. Kiểm tra rỗng với đúng loại phương thức và ngoại lệ.
4. Kiểm tra dữ liệu null theo hợp đồng hiện có.
5. Kiểm tra thứ tự iterator nếu dùng để hiển thị hoặc sao chép.
6. Kiểm tra các phương thức List/Vector/Stack đặc thù mà mã gọi đang dùng.
7. Kiểm tra chia sẻ tham chiếu, đồng bộ và toàn bộ chuỗi cập nhật.
8. Kiểm tra hành vi equals nếu lớp mới có ngữ nghĩa khác.

Các bài kiểm tra nên bảo vệ yêu cầu của ứng dụng, không chỉ xác nhận tên lớp mới hoặc một đoạn triển khai.

Nếu cần so thứ tự dữ liệu, thu các phần tử được lấy ra vào List như các chương trình trong bài. Hai lớp có cùng tập phần tử nhưng khác thứ tự vẫn có thể tạo ra hành vi nghiệp vụ khác.

Không dùng một Set để xác nhận thay thế stack/queue: Set có thể che mất thứ tự và số lần xuất hiện.

## 16. Bài tập áp dụng

### Bài 1: hàng đợi công việc đơn luồng

Chỉ cần thêm cuối, lấy đầu, không nhận null và không truy cập chỉ số. Trong ba lớp, nên cân nhắc lớp nào đầu tiên?

**Gợi ý trả lời:** ArrayDeque qua giao diện Queue hoặc Deque là lựa chọn phù hợp để bắt đầu. Vẫn cần xem quy mô, giới hạn và yêu cầu thực tế.

### Bài 2: xóa giữa LinkedList

Một hàm nhận chỉ số i và gọi remove(i). Có thể kết luận O(1) chỉ vì LinkedList dùng liên kết không?

**Gợi ý trả lời:** không. Phải đi tới vị trí i; chi phí tổng quát vẫn O(n). Cập nhật cục bộ tại con trỏ đã có là trường hợp khác.

### Bài 3: cùng pop, khác iterator

Push A, B, C vào Stack và vào ArrayDeque. Cả hai pop ra C trước. Iterator có cùng thứ tự không?

**Gợi ý trả lời:** không. Stack duyệt A, B, C theo thứ tự Vector; ArrayDeque dùng push duyệt C, B, A từ first tới last.

### Bài 4: đổi peek

Mã cũ bắt EmptyStackException quanh Stack.peek. Nếu đổi sang Deque.peek, trường hợp rỗng diễn ra thế nào?

**Gợi ý trả lời:** Deque.peek trả null. Cần xem lại nhánh xử lý hoặc chọn phương thức/adapter giữ hợp đồng mong muốn.

### Bài 5: Stack có một phần tử

Hai luồng cùng chạy kiểm tra không rỗng rồi pop. Đồng bộ từng phương thức có bảo đảm cả hai pop đều thành công không?

**Gợi ý trả lời:** không. Một luồng có thể lấy phần tử giữa hai lời gọi của luồng kia. Chuỗi kiểm tra-rồi-lấy cần cơ chế phù hợp cho toàn yêu cầu.

### Bài 6: chuyển dữ liệu có null

Một LinkedList đang giữ null như một phần tử thật. Có thể thay bằng ArrayDeque mà không quyết định lại dữ liệu không?

**Gợi ý trả lời:** không. ArrayDeque cấm null; phải xác định từ chối, biểu diễn lại hoặc giữ cấu trúc có hợp đồng phù hợp.

### Bài 7: constructor copy của Stack

Stack đang có A ở đáy và C ở đỉnh. Tạo ArrayDeque bằng constructor nhận Stack rồi gọi pop.

Giá trị nào có thể được lấy và vì sao?

**Gợi ý trả lời:** A, vì constructor giữ thứ tự iterator A, B, C và Deque.pop lấy first. Muốn giữ đỉnh C cần chuyển theo quy ước đỉnh rõ ràng.

### Bài 8: chọn vì có get(i)

Stack có get(i) O(1), nên có phải lựa chọn mặc định cho mọi danh sách truy cập ngẫu nhiên không?

**Gợi ý trả lời:** không. Khả năng kế thừa không thay mục đích của cấu trúc. Khi nhu cầu là List, cần so sánh các triển khai List theo thao tác thật, không chọn Stack vì có sẵn một phương thức.

Một lựa chọn đúng cần giữ được cả ý nghĩa thứ tự, dữ liệu hợp lệ và ranh giới phối hợp. ArrayDeque, LinkedList và Stack chỉ nên được so sánh sau khi các yêu cầu ấy đã được nêu rõ.
