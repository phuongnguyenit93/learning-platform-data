# So sánh LinkedList với ArrayList và ArrayDeque

## 1. Chọn theo thao tác cần làm, rồi mới chọn cấu trúc

Ba lớp đều có thể giữ một dãy phần tử, nhưng không cung cấp cùng hợp đồng:

- **ArrayList** là List dùng mảng động, phù hợp với truy cập theo chỉ số và nhiều kiểu xử lý danh sách thông thường.
- **LinkedList** là danh sách liên kết đôi, đồng thời triển khai List và Deque; nó hỗ trợ thao tác theo vị trí lẫn hai đầu.
- **ArrayDeque** là Deque dùng mảng có thể tăng, tổ chức để thêm/lấy ở hai đầu; nó không phải List có chỉ số.

Vì vậy, câu hỏi đầu tiên không phải “lớp nào luôn nhanh nhất”, mà là:

1. Cần chỉ số, hai đầu, hay đang giữ một iterator ở vị trí sửa?
2. Tần suất đọc, thêm, xóa và tìm kiếm như thế nào?
3. Có cho phần tử null không?
4. Cần so sánh nội dung theo hợp đồng nào?
5. Quy mô và vòng đời dữ liệu tạo áp lực bộ nhớ ra sao?

Độ phức tạp giúp loại các lựa chọn không phù hợp, còn thời gian thực tế còn phụ thuộc hằng số, cấp phát, bộ nhớ và mẫu truy cập. Không dùng một nhãn “hay chèn/xóa” thay cho mô tả vị trí và cách tìm phần tử cần sửa.

Các ví dụ trong bài dùng API có trong Java 17. Với Java 21, List có thêm một số thao tác đầu/cuối qua SequencedCollection; ArrayList vẫn không trở thành Deque và ArrayDeque vẫn không có API List theo chỉ số. Tên phương thức có thể mở rộng theo phiên bản, còn cấu trúc lưu trữ và cách phân tích thao tác vẫn cần được xem riêng. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [List Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

## 2. So sánh hợp đồng trước khi so sánh tốc độ

| Thuộc tính | ArrayList | LinkedList | ArrayDeque |
|---|---|---|---|
| Triển khai List | Có | Có | Không |
| Triển khai Deque và Queue | Không | Có | Có |
| Truy cập/chèn theo chỉ số List | Có | Có | Không cung cấp |
| Nhóm thao tác hai đầu của Deque | Không thuộc hợp đồng Deque của lớp | Có | Có |
| ListIterator hai chiều có add/set theo vị trí | Có | Có | Không có ListIterator |
| Duyệt iterator thông thường | Theo thứ tự danh sách | Từ đầu tới cuối | Từ đầu trước tới đầu sau |
| Cho phần tử trùng nhau | Có | Có | Có |
| Cho phần tử null | Có | Có | Không |
| Có marker RandomAccess | Có | Không | Không |
| Tự đồng bộ cho nhiều luồng sửa | Không | Không | Không |

RandomAccess là dấu hiệu của một List hỗ trợ truy cập ngẫu nhiên nhanh. Việc ArrayDeque không có marker này không có nghĩa nó là LinkedList; nó không phải List ngay từ đầu.

Cả ba không tự sắp xếp và không khử phần tử trùng. Thứ tự quan sát được đến từ các thao tác đã thực hiện: thêm cuối, thêm đầu, chèn giữa hoặc thay đổi dãy.

Các kiểu biến minh họa trong phương thức:

```java
List<String> names = new ArrayList<>();
List<String> editableSequence = new LinkedList<>();

Deque<String> pending = new ArrayDeque<>();
Deque<String> bothEnds = new LinkedList<>();
```

Các import cần tương ứng từ `java.util`. Chọn kiểu biến List khi cần hợp đồng danh sách; chọn Deque khi cần hai đầu. Việc hai lớp cùng triển khai một giao diện cho phép dùng chung một phần mã, nhưng không bảo đảm chi phí hoặc mọi đặc tính phụ giống nhau.

## 3. Cấu trúc bên dưới giải thích các khác biệt

### 3.1. ArrayList: một mảng tham chiếu và số phần tử đang dùng

ArrayList dùng mảng nền để giữ tham chiếu phần tử. Phần tử ở chỉ số i có vị trí tương ứng trong mảng; đọc hoặc thay phần tử đó không cần lần theo các nút từ đầu.

Khi còn chỗ dự phòng, thêm cuối chỉ cần dùng vị trí cuối đang trống. Khi thiếu chỗ, danh sách cấp mảng lớn hơn và sao chép các tham chiếu sang đó.

Chèn/xóa ở đầu hoặc giữa thường phải dịch các tham chiếu phía sau để giữ dãy liên tiếp. Đó là chi phí chính của những thao tác này, ngay cả khi capacity đã đủ.

### 3.2. LinkedList: nút riêng có liên kết trước/sau

Mỗi nút giữ phần tử cùng liên kết đến nút trước và nút sau. Cấu trúc giữ hai đầu để thao tác trực tiếp ở đầu/cuối.

Muốn đến chỉ số giữa, nó phải đi theo liên kết từ phía gần hơn. Khi đã có đúng nút hoặc ListIterator giữ vị trí cần sửa, nối/tháo cục bộ không cần dịch một dãy tham chiếu như ArrayList.

Tuy nhiên, ứng dụng không được bỏ qua chi phí tìm đến vị trí. `remove(index)` không giống “đã giữ ListIterator ngay ở nút cần xóa”.

### 3.3. ArrayDeque: mảng vòng cho hai đầu

Trong triển khai OpenJDK, ArrayDeque dùng mảng với thông tin vị trí đầu/cuối theo cách vòng. Đầu logic của deque không nhất thiết nằm ở ô số 0 của mảng.

Khi lấy đầu, cấu trúc có thể tiến vị trí đầu thay vì dồn toàn bộ phần tử còn lại về ô số 0. Khi thêm ở đầu hoặc cuối, nó sử dụng vị trí vòng thích hợp; nếu cần thêm chỗ, có thể tăng mảng.

Vì vậy, không suy rằng “dùng mảng thì lấy đầu phải dịch như ArrayList”. Cách tổ chức dữ liệu trong mảng khác nhau.

Ngược lại, có mảng nền không tự cấp API `get(index)`. ArrayDeque được thiết kế và công bố như Deque; người gọi không được xem nó là ArrayList chỉ vì cả hai đều dùng mảng. [Mã nguồn ArrayDeque của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayDeque.java).

## 4. Bảng chi phí phải gắn với thao tác cụ thể

Bảng dưới xét chi phí cấu trúc thường dùng cho một cấu trúc có n phần tử. “Khấu hao” nói về tổng chi phí một chuỗi thao tác; một lần tăng mảng riêng lẻ vẫn có thể cần sao chép nhiều phần tử.

| Thao tác | ArrayList | LinkedList | ArrayDeque |
|---|---|---|---|
| Đọc/thay ở chỉ số i | `O(1)` | `O(n)` trường hợp xấu | Không có API chỉ số |
| Thêm cuối | `O(1)` khấu hao | `O(1)` | `O(1)` khấu hao |
| Xóa cuối | `O(1)` qua chỉ số cuối | `O(1)` | `O(1)` |
| Thêm đầu | `O(n)` do dịch phần tử | `O(1)` | `O(1)` khấu hao |
| Xóa đầu | `O(n)` do dịch phần tử | `O(1)` | `O(1)` |
| Chèn/xóa ở một chỉ số giữa | `O(n)` trường hợp xấu | `O(n)` gồm tìm nút | Không có API chỉ số |
| Contains hoặc tìm/xóa theo giá trị | `O(n)` trường hợp xấu | `O(n)` trường hợp xấu | `O(n)` trường hợp xấu |
| Duyệt toàn bộ bằng iterator | `O(n)` | `O(n)` | `O(n)` |
| Add bằng ListIterator đã ở vị trí giữa | `O(n)` do dịch | `O(1)` nối nút | Không có ListIterator |
| Remove hợp lệ bằng iterator đã ở vị trí giữa | `O(n)` trường hợp xấu | `O(1)` tháo nút | `O(n)` trường hợp xấu |

Các phép đọc đầu/cuối trên cấu trúc không rỗng cũng nhanh, nhưng API và hành vi khi rỗng có thể khác. Ví dụ Java 17: `arrayList.get(0)` dùng chỉ số và gây lỗi chỉ số nếu rỗng, còn `deque.peekFirst()` trả null khi rỗng.

Với ArrayDeque, ngoại lệ quan trọng đối với nhóm thao tác khấu hao hằng số là tìm/xóa theo giá trị và `iterator.remove()`, có thể tuyến tính. Không áp dụng chi phí của `pollFirst` cho mọi phương thức mang tên remove. [Chi phí ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [chi phí và ngoại lệ thao tác ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### 4.1. “LinkedList chèn/xóa O(1)” cần điều kiện

Nếu cần xóa ở chỉ số 50.000, LinkedList còn phải tìm nút đó. Sau khi tìm thấy, tháo liên kết nhanh không xóa đi chi phí đã tìm.

Nếu đang duyệt bằng ListIterator rồi quyết định chèn/xóa ngay tại vị trí đó, iterator đã giữ vị trí quanh nút. Đây là tình huống thể hiện đúng lợi ích sửa cục bộ của danh sách liên kết.

Tạo lại `listIterator(index)` cho mỗi lần sửa ở giữa vẫn có thể phải tìm lại nhiều lần. Phân tích cả quy trình, không chỉ một dòng `iterator.remove()` tách rời.

### 4.2. “Tất cả đều O(n)” không có nghĩa thời gian giống nhau

Duyệt tuyến tính cả ba đều có ký hiệu O(n), nhưng đường đi của CPU và bộ nhớ khác nhau:

- Mảng giữ các ô tham chiếu theo một cấu trúc tập trung hơn.
- Danh sách liên kết cần đọc liên kết để đến nút kế tiếp.
- LinkedList có thêm các đối tượng nút và hoạt động cấp phát khi thêm.
- Mảng có chỗ dự phòng và có những lần tăng phải sao chép.

Các yếu tố này ảnh hưởng hằng số và tính cục bộ truy cập bộ nhớ. Không cần hoặc không nên gán một tỉ lệ nhanh hơn cố định cho mọi JVM và mọi khối lượng dữ liệu.

## 5. Chọn theo các mẫu sử dụng thường gặp

### 5.1. Danh sách thường xuyên đọc bằng chỉ số

Nếu cần `get(i)`, `set(i, value)`, giữ kết quả để truy cập nhiều lần hoặc chủ yếu thêm cuối rồi đọc, ArrayList thường là điểm bắt đầu phù hợp.

Một vòng lặp theo chỉ số trên LinkedList có thể gây vấn đề:

```java
for (int i = 0; i < values.size(); i++) {
    process(values.get(i));
}
```

Đây là đoạn minh họa, với `values` và `process` đã được định nghĩa. Nếu values là LinkedList, mỗi get có thể lại đi qua nhiều nút, làm tổng chi phí có thể thành O(n²). Nếu chỉ cần duyệt tuần tự, for-each hoặc iterator tránh việc tìm lại từng chỉ số.

Điều đó không có nghĩa phải thay cấu trúc ngay trong mọi trường hợp; đôi khi sửa cách duyệt đã giải quyết nguyên nhân chính.

### 5.2. Hàng đợi FIFO hoặc ngăn xếp LIFO

Nếu chỉ cần thêm/lấy ở các đầu và không cần phần tử null, ArrayDeque thường là lựa chọn khởi đầu phù hợp:

```java
Deque<String> queue = new ArrayDeque<>();
queue.offerLast("A");
queue.offerLast("B");
String first = queue.pollFirst(); // A

Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
String lastPushed = stack.pop(); // B
```

Đây là đoạn minh họa trong phương thức, cần import các kiểu tương ứng. LinkedList cũng thực hiện đúng các hợp đồng Deque này, nhưng có cấu trúc cấp nút và chi phí bộ nhớ khác.

Tài liệu ArrayDeque nhận định nó có khả năng nhanh hơn LinkedList khi dùng như queue. Đó là định hướng thực tế từ API, không phải bảo đảm thắng mọi phép đo. Nếu hiệu năng quyết định lựa chọn, đo đúng mẫu queue/stack của chương trình. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Tránh dùng `ArrayList.remove(0)` lặp đi lặp lại để lấy đầu của một hàng đợi lớn; việc dồn phần tử sau mỗi lần lấy có thể tích lũy chi phí đáng kể.

### 5.3. Chỉnh sửa gần vị trí iterator đang giữ

Nếu thuật toán đi tuần tự rồi liên tục chèn/xóa ngay ở chỗ đã đến, LinkedList với ListIterator có thể phù hợp:

```java
ListIterator<String> iterator = values.listIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("obsolete".equals(value)) {
        iterator.remove();
    }
}
```

Đây là đoạn minh họa, values được giả định là LinkedList. Nó không tìm lại nút theo chỉ số cho từng lần xóa.

Nếu bài toán chỉ là lọc hàng loạt theo một điều kiện, cần xem cả API xử lý theo lô và thuật toán thực tế. Không suy từ chi phí một lần `ArrayList.iterator().remove()` rằng mọi cách lọc ArrayList đều phải có cùng cách dịch phần tử lặp lại.

### 5.4. Cần cả List và Deque trên cùng một cấu trúc

LinkedList có thể phục vụ khi một đoạn mã thực sự cần phối hợp thao tác theo vị trí và thao tác hai đầu trên cùng dãy dữ liệu.

Đoạn minh họa:

```java
LinkedList<String> storage = new LinkedList<>();
List<String> indexed = storage;
Deque<String> ended = storage;
```

Hai biến không tạo hai bản sao. Thao tác qua một biến thay đổi dữ liệu mà biến kia quan sát.

Đây là một khả năng API đáng biết, nhưng không tự chứng minh LinkedList là lựa chọn tốt nhất nếu truy cập chỉ số chiếm phần lớn thời gian. Cần mô tả tần suất của từng nhóm thao tác.

## 6. Chương trình đầy đủ: cùng hợp đồng cho kết quả tương ứng

Lưu thành `CollectionWorkloadDemo.java`. Chương trình dùng API có trong Java 17:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class CollectionWorkloadDemo {
    private static void editList(String name, List<String> values) {
        values.addAll(List.of("A", "B", "C"));
        System.out.println(name + " get(1): " + values.get(1));

        ListIterator<String> iterator = values.listIterator(1);
        iterator.add("X");
        String selected = iterator.next();
        iterator.remove();
        System.out.println(name + " selected: " + selected);
        System.out.println(name + " edited: " + values);
    }

    private static void useDeque(String name, Deque<String> values) {
        values.offerLast("A");
        values.offerLast("B");
        values.offerFirst("URGENT");
        System.out.println(name + " first: " + values.pollFirst());

        values.push("TOP");
        System.out.println(name + " stack: " + values.pop());
        System.out.println(name + " last: " + values.pollLast());
        System.out.println(name + " remaining: " + values);
    }

    public static void main(String[] args) {
        editList("ArrayList", new ArrayList<>());
        editList("LinkedList", new LinkedList<>());

        useDeque("ArrayDeque", new ArrayDeque<>());
        useDeque("LinkedList deque", new LinkedList<>());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionWorkloadDemo.java
java CollectionWorkloadDemo
```

Kết quả chuẩn:

```text
ArrayList get(1): B
ArrayList selected: B
ArrayList edited: [A, X, C]
LinkedList get(1): B
LinkedList selected: B
LinkedList edited: [A, X, C]
ArrayDeque first: URGENT
ArrayDeque stack: TOP
ArrayDeque last: B
ArrayDeque remaining: [A]
LinkedList deque first: URGENT
LinkedList deque stack: TOP
LinkedList deque last: B
LinkedList deque remaining: [A]
```

Hai triển khai List đều trả B tại chỉ số 1. Sau khi chèn X tại con trỏ rồi next chọn B và remove, cả hai đều còn `[A, X, C]`.

Hai triển khai Deque đều xử lý đúng cùng quy ước đầu/cuối:

- Thêm URGENT ở đầu, nên pollFirst lấy URGENT.
- Push TOP rồi pop lấy TOP.
- PollLast lấy B ở cuối, còn A.

Ví dụ chứng minh hành vi qua giao diện, không phải benchmark. Kết quả in giống nhau không nói chi phí nội bộ giống nhau; việc in còn thêm chi phí duyệt và nhập/xuất.

Chương trình cũng cho thấy ArrayDeque không được truyền cho hàm `editList` nhận List, còn ArrayList không được truyền cho hàm `useDeque` nhận Deque. Đó là khác biệt hợp đồng, không phải một lựa chọn tối ưu hóa có thể bỏ qua bằng ép kiểu tùy ý.

## 7. Null là khác biệt cần kiểm tra trước khi đổi lớp

ArrayList và LinkedList cho null làm phần tử. ArrayDeque từ chối null, kể cả qua `offer`; offer không có nghĩa mọi dữ liệu sai đều được chuyển thành kết quả false.

Nếu đổi một LinkedList đang có phần tử null sang `new ArrayDeque<>(source)`, quá trình tạo kết quả có thể thất bại bằng `NullPointerException`. Cần xác định ý nghĩa null trong dữ liệu và chính sách chuyển đổi, không âm thầm bỏ phần tử chỉ để constructor thành công.

Khi dùng LinkedList qua Deque, null còn có thể gây nhập nhằng:

```java
Deque<String> values = new LinkedList<>();
values.addLast(null);
values.addLast("A");

String first = values.pollFirst(); // null, nhưng đã xóa một phần tử.
// values vẫn còn [A].
```

Đây là đoạn minh họa. Kết quả null của poll có thể là một phần tử null hoặc dấu hiệu rỗng. Vì vậy, ngay cả khi cấu trúc cho phép null, một mô hình hàng đợi dừng khi poll trả null vẫn nên có chính sách không dùng null làm dữ liệu.

ArrayDeque cấm null nên tránh được sự trùng nghĩa đó. Cần phân biệt ràng buộc phần tử với hành vi khi deque rỗng: poll/peek trả null, còn removeFirst/getFirst báo `NoSuchElementException` trên cả hai triển khai Deque.

## 8. equals của List khác equals của ArrayDeque

ArrayList và LinkedList tuân theo so sánh nội dung của List: cùng số phần tử và các phần tử tương ứng bằng nhau theo thứ tự.

Vì vậy:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = new LinkedList<>(List.of("A", "B"));

boolean equal = a.equals(b); // true
```

Đoạn minh họa này không nói hai danh sách là cùng đối tượng; `a == b` vẫn là false.

ArrayDeque kế thừa cách so sánh danh tính đối tượng của Object, không cung cấp phép equals theo dãy phần tử như List. Hai ArrayDeque riêng cùng chứa `[A, B]` có thể in giống nhau nhưng equals là false.

Nếu mục tiêu là so sánh hai dãy phần tử theo thứ tự duyệt, có thể chuyển sang một biểu diễn List để so sánh trong phạm vi có kiểm soát:

```java
boolean sameSequence =
        new ArrayList<>(leftDeque).equals(new ArrayList<>(rightDeque));
```

Đây là biểu thức minh họa với hai deque đã khai báo. Nó tạo cấu trúc chứa mới để dùng hợp đồng List; không phải một phép đo miễn phí và không làm phần tử được sao chép sâu.

Một LinkedList giữ trong biến Deque vẫn có cách equals của chính LinkedList. Chọn kiểu biến Deque không biến đối tượng thành ArrayDeque hoặc thay cách triển khai equals.

Đây là một khác biệt về tính đúng đắn khi thay lớp, không chỉ về tốc độ. Nếu chương trình dựa vào equals/hashCode của container, phải kiểm tra hợp đồng thay vì chỉ so tên phương thức. [Deque và equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), [ArrayDeque kế thừa equals từ Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

## 9. Chương trình đầy đủ: giao diện, null và equals

Lưu thành `CollectionContractDifferencesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.RandomAccess;

public class CollectionContractDifferencesDemo {
    private static void capabilities(String name, Object value) {
        System.out.println(name + ": List=" + (value instanceof List<?>)
                + ", Deque=" + (value instanceof Deque<?>)
                + ", RandomAccess=" + (value instanceof RandomAccess));
    }

    public static void main(String[] args) {
        capabilities("ArrayList", new ArrayList<>());
        capabilities("LinkedList", new LinkedList<>());
        capabilities("ArrayDeque", new ArrayDeque<>());

        List<String> arrayList =
                new ArrayList<>(Arrays.asList("A", null, "A"));
        List<String> linkedList = new LinkedList<>(arrayList);
        System.out.println("ArrayList with null: " + arrayList);
        System.out.println("LinkedList with null: " + linkedList);

        Deque<String> arrayDeque = new ArrayDeque<>();
        try {
            arrayDeque.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("ArrayDeque null: NullPointerException");
        }
        System.out.println("ArrayDeque size after rejected null: "
                + arrayDeque.size());

        List<String> leftList = new ArrayList<>(List.of("A", "B"));
        List<String> rightList = new LinkedList<>(List.of("A", "B"));
        System.out.println("ArrayList equals LinkedList: "
                + leftList.equals(rightList));

        Deque<String> firstDeque =
                new ArrayDeque<>(List.of("A", "B"));
        Deque<String> secondDeque =
                new ArrayDeque<>(List.of("A", "B"));
        System.out.println("two ArrayDeque instances equal: "
                + firstDeque.equals(secondDeque));
        System.out.println("compare encounter order as lists: "
                + new ArrayList<>(firstDeque)
                        .equals(new ArrayList<>(secondDeque)));

        Deque<String> linkedAsDeque =
                new LinkedList<>(List.of("A", "B"));
        System.out.println("LinkedList held as Deque equals List: "
                + linkedAsDeque.equals(leftList));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionContractDifferencesDemo.java
java CollectionContractDifferencesDemo
```

Kết quả chuẩn:

```text
ArrayList: List=true, Deque=false, RandomAccess=true
LinkedList: List=true, Deque=true, RandomAccess=false
ArrayDeque: List=false, Deque=true, RandomAccess=false
ArrayList with null: [A, null, A]
LinkedList with null: [A, null, A]
ArrayDeque null: NullPointerException
ArrayDeque size after rejected null: 0
ArrayList equals LinkedList: true
two ArrayDeque instances equal: false
compare encounter order as lists: true
LinkedList held as Deque equals List: true
```

Các quan sát chính:

1. ArrayList là List có RandomAccess; LinkedList là cả List lẫn Deque; ArrayDeque chỉ thuộc nhóm Deque/Queue trong hai vai trò đang xét.
2. Null và giá trị trùng A được giữ trong hai danh sách.
3. ArrayDeque từ chối null, không thêm một mục dữ liệu mới.
4. ArrayList và LinkedList cùng dãy có equals true.
5. Hai ArrayDeque riêng cùng dãy không có equals theo nội dung.
6. Chuyển các thứ tự duyệt sang ArrayList cho phép so sánh dãy bằng hợp đồng List.
7. Biến Deque đang trỏ LinkedList vẫn gọi cách equals của LinkedList.

## 10. Bộ nhớ và cấp phát: không chỉ có Big O

### 10.1. Hai cấu trúc mảng có chỗ dự phòng

ArrayList và ArrayDeque giữ mảng tham chiếu có thể lớn hơn số phần tử logic. Chỗ dự phòng giúp giảm số lần tăng mảng, nhưng vẫn chiếm bộ nhớ.

Khi mảng cần lớn hơn, có chi phí cấp mảng mới và chuyển dữ liệu. Trong lúc thay mảng, mảng cũ và mới có thể cùng tồn tại tạm thời. “Thêm cuối O(1) khấu hao” không hứa rằng không bao giờ có lần cấp phát hoặc sao chép lớn.

ArrayList cung cấp `ensureCapacity` và `trimToSize`. ArrayDeque không cung cấp cùng cặp phương thức công khai đó. Không dùng một API capacity của ArrayList như thể nó là một phần của mọi cấu trúc dùng mảng.

Các constructor nhận số lượng ban đầu của hai lớp mảng chuẩn bị chỗ chứa; chúng không tạo sẵn số phần tử đó và không đặt giới hạn nghiệp vụ cứng.

### 10.2. LinkedList có chi phí nút

LinkedList không giữ một mảng chỗ dự phòng cho toàn dãy theo cách hai lớp kia làm, nhưng mỗi phần tử cần một nút có các liên kết và phần quản lý đối tượng.

Với nhiều phần tử nhỏ, chi phí các nút và cấp phát có thể đáng kể. Khi đi qua danh sách, cần theo các tham chiếu nút; đây là kiểu truy cập khác với đi qua các ô trong một mảng.

Không suy “không có capacity dư” thành “luôn dùng ít bộ nhớ hơn”. Hai cách tổ chức đánh đổi khác nhau.

### 10.3. Không gán số byte cố định cho mọi JVM

Tổng bộ nhớ phụ thuộc kích thước tham chiếu, bố cục đối tượng, căn chỉnh, cấu hình JVM, mức dự phòng và chính các đối tượng phần tử.

Cả ba cấu trúc đều giữ tham chiếu đến phần tử, không tự sao chép toàn bộ đối tượng phần tử vào container. Chuyển container bằng constructor cũng không mặc nhiên tạo một bản sao sâu của dữ liệu.

Khi bộ nhớ là yêu cầu quan trọng, đo cấu hình và tải thực. Những mô tả như “LinkedList thêm hai liên kết mỗi nút” giúp giải thích cơ chế, nhưng không thay thế phép đo tổng bộ nhớ với một số byte có tính phổ quát.

## 11. Đổi triển khai cần kiểm tra cả ý nghĩa lời gọi

Có hai loại thay đổi khác nhau:

- Đổi `new ArrayList<>()` thành `new LinkedList<>()` trong một biến List: hợp đồng List vẫn dùng được, nhưng chi phí thay đổi.
- Đổi một thiết kế từ List sang Deque: tập phương thức và có thể cả lựa chọn overload ở chỗ gọi thay đổi.

Ví dụ, qua `List<Integer>`, `remove(1)` chọn xóa tại chỉ số 1. Qua `Deque<Integer>`, không có `remove(int)`; đối số 1 được boxing để tìm theo `remove(Object)`.

Sự khác nhau đó do kiểu biến và tập overload nhìn thấy, không phải vì ArrayDeque hoặc LinkedList đoán ý định từ giá trị chứa bên trong.

Trước khi đổi lớp, kiểm tra ít nhất các điểm sau:

| Điểm cần xem | Lý do |
|---|---|
| Có gọi get/set/add theo chỉ số không? | ArrayDeque không cung cấp API đó |
| Có null trong dữ liệu không? | ArrayDeque từ chối |
| Có dựa vào equals theo nội dung container không? | ArrayDeque không dùng hợp đồng List.equals |
| Có ListIterator hoặc subList không? | Hai API này thuộc vai trò List |
| Thao tác remove đang nhận int, Object hay không có đối số? | Ý nghĩa có thể khác |
| Có truy cập dữ liệu theo chỉ số trong vòng lặp không? | Có thể làm LinkedList tốn chi phí tìm lặp lại |
| Nguồn có bị sửa qua nhiều tham chiếu hoặc nhiều luồng không? | Đổi lớp không tự xử lý quyền sửa dữ liệu |

## 12. Duyệt và đồng thời: cả ba đều cần quy tắc rõ

Iterator của ba lớp có cơ chế phát hiện một số sửa đổi ngoài lượt duyệt, nhưng không dùng nó làm cơ chế an toàn luồng hoặc bằng chứng chắc chắn về tính đúng đắn.

Nếu đang duyệt và cần sửa, dùng đúng thao tác được iterator hỗ trợ theo hợp đồng. LinkedList có ListIterator cho phép chèn/xóa tại con trỏ; ArrayDeque không có ListIterator để chèn tùy ý tại vị trí duyệt.

Một iterator không phải bản sao dữ liệu. Sửa qua biến khác cùng trỏ container vẫn là sửa cùng cấu trúc; tên biến hoặc kiểu giao diện không tạo ra chủ sở hữu độc lập.

Cả ArrayList, LinkedList và ArrayDeque đều không tự đồng bộ cho truy cập sửa đổi từ nhiều luồng. Chọn một trong ba vì chi phí thao tác không giải quyết thay yêu cầu đồng thời hoặc hàng đợi chặn. Các yêu cầu đó cần được xác định riêng trước khi chọn cấu trúc phù hợp.

## 13. Cách đánh giá một lựa chọn trên dữ liệu thực

Một phép đánh giá có ích nên giữ cùng mục tiêu xử lý và xem:

1. Tỉ lệ đọc chỉ số, duyệt toàn bộ, thao tác đầu/cuối và sửa giữa.
2. Kích thước thường gặp và các đợt tăng đột biến.
3. Chi phí tìm vị trí trước khi chèn/xóa.
4. Số đối tượng được cấp và lượng bộ nhớ giữ lâu.
5. Thời gian tăng mảng, tái sử dụng và vòng đời phần tử.
6. Các yêu cầu hợp đồng như null, thứ tự, equals và quyền sửa.

Không in từng phần tử trong vùng đo rồi kết luận đó là tốc độ container. Không so một thuật toán dùng iterator với một thuật toán tìm lại chỉ số mỗi lần mà gọi đó là so sánh thuần cấu trúc.

Nếu có thể diễn đạt cùng mục tiêu bằng một thuật toán xử lý theo lô phù hợp hơn, cần xét cả lựa chọn thuật toán. Đổi container không phải đòn bẩy duy nhất.

## 14. Bài tập chọn và giải thích

| Tình huống | Lựa chọn khởi đầu hợp lý | Lý do chính |
|---|---|---|
| Nạp dữ liệu rồi đọc nhiều lần bằng get(i) | ArrayList | Truy cập chỉ số hằng số |
| Duy trì FIFO, chỉ thêm cuối và lấy đầu, không có null | ArrayDeque qua Deque/Queue | Hợp đồng trực tiếp và thao tác hai đầu hiệu quả |
| Ngăn xếp một luồng, không có null | ArrayDeque qua Deque | Push/pop theo quy ước Deque |
| Đang duyệt và sửa cục bộ nhiều tại ListIterator đã giữ | Cân nhắc LinkedList | Tận dụng vị trí nút đã có, vẫn tính chi phí duyệt |
| Cần cùng đối tượng cung cấp List và Deque | Cân nhắc LinkedList | Có cả hai vai trò API |
| Thường xuyên tìm phần tử theo giá trị trong một dãy lớn | Chưa thể quyết định chỉ từ ba tên lớp | Cả ba đều có tìm tuyến tính; phải xem toàn bộ yêu cầu |

Câu hỏi tự kiểm tra:

1. Vì sao thêm/xóa nhiều chưa đủ để kết luận dùng LinkedList?
2. Vì sao ArrayDeque dùng mảng nhưng lấy đầu không cần dồn toàn bộ dãy như ArrayList?
3. Hai ArrayDeque in cùng nội dung có nhất thiết equals true không?
4. Đổi LinkedList có null sang ArrayDeque có phải thay đổi chỉ về hiệu năng không?
5. Nếu một vòng lặp LinkedList dùng get(i) cho mọi i, có thể sửa gì trước khi thay lớp?
6. Chèn qua ListIterator của ArrayList và LinkedList có cùng ý nghĩa nhưng cùng chi phí không?

Đáp án:

1. Cần biết vị trí, cách tìm và có giữ iterator hay không; chi phí tìm nút có thể chiếm phần lớn.
2. Mảng vòng quản lý đầu/cuối logic bằng các vị trí thích hợp, không buộc đầu luôn ở ô số 0.
3. Không; ArrayDeque dùng equals theo danh tính đối tượng.
4. Không; khác biệt null có thể làm thao tác thất bại.
5. Nếu chỉ cần duyệt tuần tự, đổi sang for-each hoặc iterator để tránh tìm lại từng chỉ số.
6. Ý nghĩa hợp đồng tương ứng giống nhau, nhưng ArrayList có thể cần dịch phần tử còn LinkedList sửa liên kết tại nút đã đến.

Hãy chọn từ hợp đồng và mẫu thao tác: ArrayList cho nhu cầu List thiên về truy cập chỉ số, ArrayDeque cho nhu cầu hai đầu thông thường không có null, và LinkedList cho các trường hợp có lý do cụ thể về vị trí nút hoặc sự kết hợp List/Deque. Sau đó kiểm tra chi phí và đặc tính dữ liệu trên quy trình thực tế của chương trình.
