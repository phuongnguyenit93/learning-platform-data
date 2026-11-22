# Collectors.toList(), Collectors.toSet() và giới hạn hợp đồng kết quả

> **Chủ đề:** Java 8 – Collector cơ bản. Các quy tắc về `Collectors.toList()`, `Collectors.toSet()`, `Collectors.toCollection()` trong bài vẫn có hiệu lực ở các phiên bản Java hiện hành. Ví dụ chính dùng API Java 8 và có thể chạy trên JDK hiện đại.

## 1. Collector là gì và bài toán cần giải quyết?

Khi xử lý `Stream<T>`, ta thường biến đổi và lọc phần tử rồi muốn **thu thập kết quả thành một collection**. Phương thức terminal `collect(Collector)` thực hiện phép *mutable reduction*: mỗi phần tử được đưa vào một cấu trúc tích lũy; khi pipeline hoàn tất, trả về kết quả.

Hai cách thông dụng nhất:

~~~java
List<String> names = stream.collect(Collectors.toList());
Set<String> uniqueNames = stream.collect(Collectors.toSet());
~~~

Đây là **đoạn minh họa**, giả định `stream` có kiểu `Stream<String>`. Mỗi stream chỉ tiêu thụ được một lần; cần tạo một stream mới cho lần `collect` tiếp theo.

- **`Collectors.toList()`:** gom toàn bộ các phần tử thành một `List<T>`, giữ phần tử trùng và giữ **encounter order** nếu nguồn stream có thứ tự.
- **`Collectors.toSet()`:** gom thành một `Set<T>`, chỉ giữ phần tử phân biệt theo ngữ nghĩa của `Set`; collector này mang đặc tính **`UNORDERED`**, vì vậy không được suy ra thứ tự duyệt kết quả.
- Cả hai đều là **collector dùng trong terminal operation** `collect(...)`; khi chỉ xây dựng pipeline bằng `map`/`filter`, dữ liệu chưa được duyệt.
- Kiểu generic của phần tử vẫn giữ nguyên: từ `Stream<Customer>` nhận `List<Customer>` hoặc `Set<Customer>`; collector không tự chuyển đối tượng thành một kiểu khác.

**Điều rất quan trọng:** “Kết quả là `List`/`Set`” là cam kết về **giao diện và hành vi tập hợp**, chứ **không cam kết** lớp triển khai cụ thể, có thể thêm/xóa phần tử hay không, có thể serialize hay không, hoặc an toàn để nhiều thread chỉnh sửa cùng lúc hay không.

## 2. So sánh hợp đồng của toList và toSet

| Tiêu chí | `Collectors.toList()` | `Collectors.toSet()` |
| --- | --- | --- |
| Kiểu trả về | `List<T>` | `Set<T>` |
| Phần tử trùng | **Giữ lại** các lần xuất hiện | **Loại trùng** theo quy tắc tập hợp |
| Encounter order | Giữ thứ tự nếu stream đầu vào có encounter order | **Không bảo đảm thứ tự**; đây là collector `UNORDERED` |
| Kiểu triển khai cụ thể | **Không bảo đảm** `ArrayList`/`LinkedList`/... | **Không bảo đảm** `HashSet`/`LinkedHashSet`/... |
| Có cho phép `add`/`remove`? | **Không có bảo đảm** về mutability | **Không có bảo đảm** về mutability |
| Serialization | **Không có bảo đảm** | **Không có bảo đảm** |
| Thread safety của kết quả | **Không có bảo đảm** | **Không có bảo đảm** |
| Khi cần điều khiển loại collection | `toCollection(ArrayList::new)`, `toCollection(LinkedList::new)` | `toCollection(LinkedHashSet::new)`, `toCollection(TreeSet::new)` |

Các bảo đảm và giới hạn trên được mô tả ngay trong **Javadoc `Collectors`**; chúng là những điều khoản vẫn hiện hành, kể cả khi một bản JDK cụ thể thường trả về `ArrayList` hoặc `HashSet`.

### 2.1. Giữ thứ tự khác với có thể dự đoán thứ tự

`List` có thứ tự theo vị trí (index). Với nguồn ordered như `List.stream()`, `Stream.of(...)` hoặc `Arrays.stream(...)`, collector `toList()` giữ thứ tự encounter order. Nếu bản thân nguồn unordered như một số loại `Set.stream()`, `toList()` không tự tạo ra thứ tự nghiệp vụ ổn định.

`Set` không cho phép các phần tử trùng nhau, nhưng **giao diện `Set` không mặc nhiên quy định thứ tự in ra hoặc duyệt phần tử**. `toSet()` còn được đánh dấu `UNORDERED`; đừng dựa vào chuỗi `set.toString()`, thứ tự lặp `for-each` hay vị trí phần tử khi gửi dữ liệu ra API.

> Ví dụ, kết quả của `Stream.of("b", "a", "b").collect(Collectors.toSet())` có hai phần tử `"a"` và `"b"`, nhưng không có bảo đảm rằng khi in ra sẽ là `[a, b]` hay `[b, a]`.

### 2.2. “Giới hạn hợp đồng” nghĩa là gì?

**Hợp đồng API** là những điều caller có quyền phụ thuộc khi thay đổi phiên bản Java, triển khai JDK hoặc cách chạy sequential/parallel. Một đặc điểm **quan sát được trên máy hiện tại** chưa chắc là hợp đồng.

Ví dụ sau **không phải một giả định an toàn**:

~~~java
List<String> result = Stream.of("An", "Binh")
        .collect(Collectors.toList());

// Không được thiết kế chương trình dựa trên giả định này:
ArrayList<String> arrayList = (ArrayList<String>) result;
// Cũng không được mặc định rằng result.add("Chi") luôn hợp lệ.
~~~

Đoạn này là **minh họa về sai lầm hợp đồng**: cast có thể gây `ClassCastException` nếu triển khai thay đổi; `add` có thể gây `UnsupportedOperationException` nếu collection không sửa được. Đó không phải là hành vi của mọi JDK, mà là điều hợp đồng **không bảo đảm loại trừ**.

Nếu logic cần một `ArrayList` thực sự có thể sửa, hãy **yêu cầu điều đó khi collect** bằng `toCollection(ArrayList::new)`.

## 3. Ví dụ hoàn chỉnh, kết quả có thể kiểm chứng

Lưu thành tệp **CollectorContractsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class CollectorContractsDemo {
    public static void main(String[] args) {
        List<String> source =
                Arrays.asList(" Lan ", "Minh", "Lan", "An", "Minh");

        List<String> list = source.stream()
                .map(String::trim)
                .collect(Collectors.toList());
        System.out.println("list = " + list);

        Set<String> set = list.stream()
                .collect(Collectors.toSet());
        // Chỉ in những thuộc tính được bảo đảm, không in thứ tự của set.
        System.out.println("set size = " + set.size());
        System.out.println("set contains Lan = " + set.contains("Lan"));

        List<String> uniqueInOrder = list.stream()
                .distinct()
                .collect(Collectors.toList());
        System.out.println("uniqueInOrder = " + uniqueInOrder);

        LinkedHashSet<String> insertionOrder = list.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println("insertionOrder = " + insertionOrder);

        TreeSet<String> alphabetical = list.stream()
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println("alphabetical = " + alphabetical);

        ArrayList<String> editable = list.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Binh");
        System.out.println("editable = " + editable);

        List<String> readOnly =
                Collections.unmodifiableList(new ArrayList<>(list));
        try {
            readOnly.add("Binh");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readOnly rejects add");
        }
    }
}
~~~

Biên dịch bằng JDK 17+ và yêu cầu tương thích ngôn ngữ/API Java 8:

~~~bash
javac --release 8 CollectorContractsDemo.java
java CollectorContractsDemo
~~~

**Stdout chính xác:**

~~~text
list = [Lan, Minh, Lan, An, Minh]
set size = 3
set contains Lan = true
uniqueInOrder = [Lan, Minh, An]
insertionOrder = [Lan, Minh, An]
alphabetical = [An, Lan, Minh]
editable = [Lan, Minh, Lan, An, Minh, Binh]
readOnly rejects add
~~~

Giải thích từng nhánh:

1. `toList` giữ đủ **năm lần xuất hiện** sau khi `trim`, kể cả `Lan` và `Minh` lặp.
2. `toSet` có **ba giá trị phân biệt**. Chương trình không in nguyên `set` vì hợp đồng không bảo đảm thứ tự lặp.
3. `distinct().collect(toList())` tạo `List` không trùng và, vì nguồn ordered, giữ lại **lần xuất hiện đầu** theo thứ tự gốc.
4. `toCollection(LinkedHashSet::new)` cho một `LinkedHashSet` có thứ tự **chèn lần đầu** xác định: `Lan` → `Minh` → `An`.
5. `toCollection(TreeSet::new)` cho kết quả **sắp xếp tự nhiên** của `String`: `An`, `Lan`, `Minh`.
6. `toCollection(ArrayList::new)` trả về chính kiểu `ArrayList`, nên `editable.add(...)` hoạt động theo hợp đồng của `ArrayList`.
7. `Collections.unmodifiableList(...)` là cách tương thích Java 8 để chặn các thao tác sửa cấu trúc qua danh sách trả về; nó **không biến mọi đối tượng phần tử có thể thay đổi thành bất biến**.

## 4. Chọn collection bằng toCollection(Supplier)

Phương thức `Collectors.toCollection(Supplier<C>)` có từ Java 8, nhận factory để tạo một collection **mới, rỗng**, và gom các phần tử vào đó theo encounter order của stream nếu có. Đây là cách thích hợp khi caller cần thuộc tính cụ thể mà `toList`/`toSet` không hứa.

| Yêu cầu nghiệp vụ | Cách collect | Điều được đảm bảo bởi lựa chọn |
| --- | --- | --- |
| Cần một danh sách sửa được bằng `add`/`remove` | `collect(toCollection(ArrayList::new))` | Kết quả là `ArrayList`; các thao tác sửa thông thường được hỗ trợ |
| Cần cấu trúc `LinkedList` | `collect(toCollection(LinkedList::new))` | Kết quả là `LinkedList` |
| Cần tập hợp duy nhất, giữ thứ tự xuất hiện đầu | `collect(toCollection(LinkedHashSet::new))` | Kết quả là `LinkedHashSet`, duyệt theo thứ tự chèn |
| Cần tập hợp duy nhất có thứ tự sắp xếp | `collect(toCollection(TreeSet::new))` | Kết quả là `TreeSet`, sắp xếp theo natural ordering hoặc comparator được cấp |
| Chỉ cần danh sách theo vị trí, không ràng buộc class/mutability | `collect(toList())` | Hợp đồng ngắn gọn, tránh áp đặt triển khai |
| Chỉ cần tập hợp phần tử phân biệt, không quan tâm thứ tự | `collect(toSet())` | Hợp đồng ngắn gọn, tránh áp đặt triển khai |

Các biểu thức rút gọn trong bảng giả định đã `import static java.util.stream.Collectors.*;` hoặc viết đầy đủ tiền tố `Collectors.`.

### 4.1. Ví dụ khi phải giữ thứ tự xuất hiện

Với đầu vào `["Mai", "An", "Mai", "Binh"]`:

- `collect(toSet())`: tập các giá trị `Mai`, `An`, `Binh`; **không suy ra thứ tự**.
- `distinct().collect(toList())`: `[Mai, An, Binh]` đối với ordered stream; vẫn là danh sách, có index.
- `collect(toCollection(LinkedHashSet::new))`: tập duy nhất duyệt theo thứ tự `[Mai, An, Binh]`; là `Set`, không có index.
- `collect(toCollection(TreeSet::new))`: tập sắp xếp `[An, Binh, Mai]`; thứ tự do comparator/natural order, **không phải thứ tự xuất hiện**.

Hai lựa chọn “không trùng và giữ thứ tự” có mục đích khác nhau: **List** cho phép thao tác theo vị trí; **LinkedHashSet** nhấn mạnh tính duy nhất khi thêm và tra cứu phần tử.

### 4.2. Lưu ý về TreeSet và tính nhất quán so sánh

`TreeSet` xác định hai phần tử tương đương khi comparator trả `0` (hoặc `compareTo` trả `0`). Nếu comparator này không nhất quán với `equals`, cách hiểu “trùng nhau” có thể khác so với `HashSet`/`LinkedHashSet`. Do đó, chỉ chọn `TreeSet` khi yêu cầu sắp xếp và quy tắc so sánh đã được thiết kế rõ.

## 5. Loại trùng: equals(), hashCode() và phần tử có thể thay đổi

### 5.1. Set không tự biết “khóa nghiệp vụ”

Với `String`, hai chuỗi cùng nội dung được xem là bằng nhau nhờ `String.equals`. Với đối tượng tự viết, nếu không định nghĩa quy tắc so sánh, nhiều object khác nhau có thể vẫn cùng mã sản phẩm nhưng **không bị Set loại trùng**.

Đoạn dưới đây **minh họa trong mã ứng dụng đã có lớp `Order` với phương thức `getOrderId()`**, không phải chương trình độc lập:

~~~java
// Nếu mục tiêu là lấy các mã đơn hàng duy nhất:
Set<String> uniqueIds = orders.stream()
        .map(Order::getOrderId)
        .collect(Collectors.toSet());
~~~

Cách này loại trùng **theo chuỗi mã đơn hàng** thay vì tùy thuộc việc lớp `Order` có ghi đè `equals`/`hashCode` hay không. Nếu vẫn muốn tập hợp đối tượng `Order` duy nhất theo id, cần định nghĩa đúng hợp đồng bằng nhau và hash code ở domain model, hoặc chọn phép rút gọn theo khóa có quy tắc giữ bản ghi trùng rõ ràng.

Với các Set dựa trên hash như `HashSet` và `LinkedHashSet`, nguyên tắc bắt buộc là: **đối tượng bằng nhau theo `equals` phải có `hashCode` bằng nhau**. Tránh thay đổi những trường dùng trong `equals`/`hashCode` khi đối tượng đã nằm trong hash-based Set, vì lookup/removal có thể trở nên sai lệch.

### 5.2. Đừng giả định phần tử “trùng” nào được giữ

Hai object khác nhau có thể bằng nhau theo `equals` nhưng mang thêm dữ liệu khác (ví dụ cùng id, khác mô tả). `Collectors.toSet()` không cam kết giữ object xuất hiện đầu tiên hay cuối cùng; nó là collector `UNORDERED`. Nếu cần “giữ bản ghi đầu”, phải xác định **nguồn ordered** và phép chọn mang bảo đảm phù hợp. Với ordered stream, `distinct()` giữ lần xuất hiện đầu; `LinkedHashSet` giữ phần tử được chèn lần đầu.

Ngoài ra, `toSet()` không đồng nghĩa với `sorted()`: muốn thứ tự sắp xếp phải chỉ định `sorted()`/`TreeSet` theo yêu cầu cụ thể, không suy ra từ việc phần tử là duy nhất.

## 6. Mutability, unmodifiable và khả năng chia sẻ kết quả

### 6.1. Vì sao không nên gọi add() trên kết quả toList() như một điều chắc chắn?

Javadoc của `Collectors.toList()`/`toSet()` **không hứa** có thể chỉnh sửa được. Trên một JDK, kết quả quan sát có thể là `ArrayList` hoặc `HashSet`, nhưng việc gọi `add` hoặc ép kiểu dựa vào chi tiết đó sẽ ràng buộc mã vào triển khai.

Thay vì:

~~~java
List<String> names = input.stream().collect(Collectors.toList());
names.add("Moi"); // Không phải bảo đảm của Collectors.toList().
~~~

Hãy viết rõ yêu cầu:

~~~java
List<String> names = input.stream()
        .collect(Collectors.toCollection(ArrayList::new));
names.add("Moi"); // Hợp đồng ArrayList bảo đảm thao tác này.
~~~

Hai đoạn trên là **ví dụ rút gọn**, giả định `input` là `Collection<String>` và có đầy đủ import. Các lỗi tiềm tàng ở đoạn đầu là do **phụ thuộc điều không nằm trong hợp đồng**, không có nghĩa nó luôn lỗi trên mọi JDK.

### 6.2. Nếu cần kết quả không cho phép sửa

Trong Java 8, có thể tạo bản sao về **cấu trúc collection** rồi bọc:

~~~java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(input.stream()
                .collect(Collectors.toList())));
~~~

Đây là **đoạn minh họa** với `input` kiểu `Collection<String>`. Phép bọc cấm `add`/`remove`/`set` thông qua `snapshot`. Vì đã tạo `ArrayList` mới, những lần thêm/xóa sau này ở collection nguồn không tự sửa danh sách đó. Tuy vậy, các phần tử được copy bằng **tham chiếu**: nếu phần tử là object mutable thì trạng thái bên trong chúng vẫn có thể đổi.

Đối với Set, cách tương đương trên Java 8 là xây dựng `LinkedHashSet` hoặc `HashSet` đúng nhu cầu rồi bọc `Collections.unmodifiableSet(...)`. Không nhầm **unmodifiable collection** với **deep immutable object graph**.

### 6.3. Phân biệt API hiện hành ở các phiên bản Java mới hơn

Các API sau vẫn hữu ích trong codebase hiện đại, nhưng **không thuộc Java 8**:

| API | Có từ | Điểm khác biệt cần nhớ |
| --- | --- | --- |
| `Collectors.toList()` | Java 8 | Không bảo đảm mutability hay class cụ thể |
| `Collectors.toSet()` | Java 8 | Không bảo đảm mutability/class/thứ tự; collector `UNORDERED` |
| `Collectors.toUnmodifiableList()` | Java 10 | Cam kết List không sửa được, giữ encounter order; **không chấp nhận phần tử `null`** |
| `Collectors.toUnmodifiableSet()` | Java 10 | Cam kết Set không sửa được; **không chấp nhận `null`**; không cam kết giữ đối tượng nào trong nhóm trùng |
| `Stream.toList()` | Java 16 | Là **terminal method khác** `collect(Collectors.toList())`; List trả về **không sửa được**, vẫn giữ encounter order nếu có |

Ví dụ về **sự khác biệt trong API hiện đại** (chỉ chạy trên **Java 16+**):

~~~java
List<String> result = Stream.of("An", "Binh").toList();
result.add("Chi"); // Ném UnsupportedOperationException.
~~~

Bài học về hợp đồng vẫn như cũ: **cùng trả `List<T>` không có nghĩa cùng bảo đảm chỉnh sửa được**. Chọn API dựa trên contract, thay vì đoán theo tên `toList`.

### 6.4. Serializability và thread safety

`Collectors.toList()`/`toSet()` không bảo đảm kết quả hỗ trợ serialization hay truy cập sửa đồng thời một cách an toàn. Việc implementation thường gặp có hỗ trợ `Serializable` cũng không tự biến điều đó thành bảo đảm của collector; bản thân phần tử cũng phải đáp ứng yêu cầu của quá trình serialize.

**`parallelStream().collect(Collectors.toList())` vẫn là cách collect hợp lệ.** Framework có thể dùng các bộ tích lũy trung gian riêng rồi kết hợp; không có nghĩa danh sách **sau khi trả về** an toàn khi nhiều thread cùng gọi `add`/`remove`. Nếu chương trình cần chia sẻ kết quả giữa nhiều thread, hãy thiết kế ranh giới bất biến, đồng bộ hoặc cấu trúc concurrent phù hợp theo trường hợp sử dụng.

## 7. Các tình huống dễ viết sai

### Lỗi 1: Biến Set thành danh sách rồi kỳ vọng thứ tự gốc

~~~java
// Sai khi logic đòi thứ tự gốc ổn định:
List<String> result = new ArrayList<>(
        input.stream().collect(Collectors.toSet()));
~~~

Đoạn minh họa trên tạo `List` nhưng thứ tự đã phụ thuộc vào lần duyệt một `Set` không có bảo đảm thứ tự. Nếu cần danh sách duy nhất theo encounter order của nguồn ordered:

~~~java
List<String> result = input.stream()
        .distinct()
        .collect(Collectors.toList());
~~~

### Lỗi 2: Nghĩ toSet() tự chuyển dữ liệu sang thứ tự alphabet

`toSet` bảo đảm tính duy nhất, **không bảo đảm sắp xếp**. Nếu cần một Set sắp xếp, dùng `toCollection(TreeSet::new)`. Nếu cần List đã sắp xếp, dùng `sorted().collect(toList())` (đối với phần tử có thứ tự so sánh phù hợp).

### Lỗi 3: Dùng toSet() để xóa trùng đối tượng theo một trường chưa được định nghĩa là equality

Set không biết ngầm trường `userId`, `email` hay `orderId` của object. Phải xác định rõ khóa, chuẩn hóa dữ liệu (ví dụ trim/case) nếu nghiệp vụ yêu cầu, rồi map sang khóa hoặc định nghĩa equality đúng cách.

### Lỗi 4: Giả định kết quả mặc định là ArrayList/HashSet

Không ép kiểu hay kiểm tra `getClass().getSimpleName()` để làm rẽ nhánh nghiệp vụ. Dùng `toCollection` khi cần class cụ thể.

### Lỗi 5: Cho rằng unmodifiable đồng nghĩa với thread-safe tuyệt đối

Collection không sửa cấu trúc được vẫn có thể giữ các object mutable. Việc chia sẻ object mutable giữa nhiều thread cần quy tắc đồng bộ/ownership phù hợp; wrapper không cung cấp deep immutability.

### Lỗi 6: Collect vô hạn hoặc lượng dữ liệu quá lớn mà không xét bộ nhớ

`toList()` và `toSet()` gom các phần tử đầu ra vào bộ nhớ. Một stream vô hạn không được giới hạn phù hợp sẽ không hoàn thành phép collect toàn bộ; một stream hữu hạn rất lớn vẫn có thể vượt tài nguyên. Hãy giới hạn dữ liệu theo yêu cầu nghiệp vụ, thiết kế phân trang hoặc xử lý tăng dần khi cần; đừng coi collect là cách streaming ra đĩa hoặc tự giới hạn RAM.

### Lỗi 7: Tin rằng kết quả Set sẽ giữ “bản ghi đầu” khi các object bằng nhau

`toSet` có đặc tính unordered. Nếu business rule bắt buộc giữ bản ghi xuất hiện đầu, hãy dùng nguồn ordered và quy tắc xử lý ổn định (chẳng hạn `distinct` cho danh sách, hoặc `LinkedHashSet` phù hợp), đừng suy ra từ kết quả ngẫu nhiên của một lần chạy.

### Lỗi 8: Chia sẻ biến mutable bên ngoài với forEach()/peek() để tự tích lũy

Dùng:

~~~java
List<String> result = input.parallelStream()
        .map(String::trim)
        .collect(Collectors.toList());
~~~

thay vì nhiều thread cùng sửa một `ArrayList` bên ngoài bằng `forEach`. `collect` diễn đạt đúng phép reduction và để Stream framework quản lý việc tích lũy/kết hợp. Ví dụ chỉ minh họa, giả định `input` là collection chuỗi không chứa null.

## 8. Cách chọn nhanh theo yêu cầu

1. **Muốn giữ mọi phần tử và thứ tự của ordered source?** Dùng `Collectors.toList()`; không phụ thuộc class hay mutability.
2. **Muốn các giá trị phân biệt mà không cần thứ tự?** Dùng `Collectors.toSet()`.
3. **Muốn loại trùng và vẫn giữ thứ tự gốc trong List?** Dùng `distinct().collect(Collectors.toList())` với ordered stream.
4. **Muốn Set duy nhất nhưng duyệt theo thứ tự chèn?** Dùng `Collectors.toCollection(LinkedHashSet::new)`.
5. **Muốn Set có thứ tự sắp xếp?** Dùng `Collectors.toCollection(TreeSet::new)` và bảo đảm comparator phù hợp.
6. **Muốn kết quả chắc chắn sửa được?** Dùng `Collectors.toCollection(ArrayList::new)` hoặc một collection cụ thể phù hợp.
7. **Muốn kết quả chắc chắn không sửa được?** Trên Java 8, tạo bản sao rồi bọc `Collections.unmodifiableList/Set`; trên Java 10+ có các collector `toUnmodifiable...` với quy tắc `null` riêng.
8. **Muốn xử lý song song?** `collect` dùng được với parallel stream, nhưng thread safety của collection trả về vẫn phải xét riêng.

Trước khi chọn, hỏi thêm: nguồn có thứ tự hay không, định nghĩa “trùng” là gì, kết quả có thể chứa `null` không, caller sẽ sửa hay chia sẻ kết quả không, và có cần thứ tự đầu ra ổn định để hiển thị/serialize không.

## 9. Tự kiểm tra

**Câu 1.** Với `Stream.of("A", "B", "A")`, `toList()` trả bao nhiêu phần tử và `toSet()` trả bao nhiêu phần tử?

**Đáp án:** `toList` có 3 phần tử theo thứ tự `[A, B, A]`; `toSet` có 2 phần tử phân biệt. Không suy diễn thứ tự hiển thị của `toSet`.

**Câu 2.** Vì sao không nên viết `(ArrayList<String>) stream.collect(Collectors.toList())`?

**Đáp án:** Collector hứa `List<String>`, không hứa `ArrayList<String>`. Nếu cần `ArrayList`, dùng `collect(Collectors.toCollection(ArrayList::new))`.

**Câu 3.** Đầu vào ordered `["x", "y", "x", "z"]`; làm sao thu được List duy nhất với thứ tự `[x, y, z]`?

**Đáp án:** `stream.distinct().collect(Collectors.toList())`. `distinct` ổn định với ordered stream, và `toList` giữ encounter order.

**Câu 4.** Có thể gọi `parallelStream().collect(Collectors.toSet())` không? Sau đó có thể cho nhiều thread cùng sửa Set kết quả mà không đồng bộ không?

**Đáp án:** Có thể collect parallel. Nhưng collector **không bảo đảm Set trả về thread-safe**; việc sửa đồng thời phải được thiết kế riêng.

**Câu 5.** `Stream.toList()` và `collect(Collectors.toList())` có cùng hợp đồng chỉnh sửa không?

**Đáp án:** Không. `Stream.toList()` có từ Java 16 và trả List không sửa được; `Collectors.toList()` có từ Java 8 nhưng không bảo đảm mutability.

## 10. Những điều cần nhớ

- `toList`: **List có trùng, giữ encounter order nếu nguồn ordered**, nhưng không hứa implementation class/mutability/serialization/thread safety.
- `toSet`: **Set loại trùng, collector UNORDERED**, cũng không hứa implementation class/mutability/serialization/thread safety.
- `toCollection(supplier)`: yêu cầu kiểu collection cụ thể khi cần hợp đồng mạnh hơn về sửa đổi, cách lặp hoặc sắp xếp.
- **Giữ thứ tự, loại trùng, sắp xếp, không thể sửa và thread-safe là các yêu cầu khác nhau**; không có một collector mặc định nào tự bảo đảm tất cả.
- Khi làm việc với JDK hiện đại, phân biệt rõ **`Collectors.toList()`** và **`Stream.toList()`**.

### Tài liệu chính thức (đối chiếu hợp đồng còn hiệu lực)

- [Oracle Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Stream, bao gồm Stream.toList và distinct](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 8 — LinkedHashSet](https://docs.oracle.com/javase/8/docs/api/java/util/LinkedHashSet.html)
