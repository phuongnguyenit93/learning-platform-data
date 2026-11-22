# Comparator.nullsFirst() và Comparator.nullsLast() trong Java

Khi sắp xếp, dữ liệu thực tế có thể chứa `null`: một phần tử `null` trong `List`, một trường chưa được điền hoặc một khóa trích xuất từ object có giá trị `null`. Nếu chuyển thẳng các giá trị đó cho một comparator không hỗ trợ `null`, ứng dụng có thể gặp `NullPointerException`. Java cung cấp hai phương thức tĩnh **`Comparator.nullsFirst()`** và **`Comparator.nullsLast()`** để quy định vị trí của `null` một cách tường minh.

Mục tiêu của bài: hiểu hợp đồng của hai phương thức, phân biệt **phần tử null** với **thuộc tính null**, kết hợp với `comparing`/`thenComparing`/`reversed`, và tránh lỗi khi dùng `List.sort`, stream hoặc `TreeSet`.

## 1. Ý nghĩa và chữ ký API

Trong `java.util.Comparator`, hai phương thức có dạng:

~~~java
public static <T> Comparator<T> nullsFirst(
        Comparator<? super T> comparator);

public static <T> Comparator<T> nullsLast(
        Comparator<? super T> comparator);
~~~

Đây là **chữ ký API để tham khảo**, không phải đoạn khai báo cần dán vào lớp của bạn. Chúng tạo ra **comparator mới** từ comparator được cung cấp:

| Tình huống | `nullsFirst(c)` | `nullsLast(c)` |
|---|---|---|
| Cả hai đều `null` | Bằng nhau: kết quả `0` | Bằng nhau: kết quả `0` |
| Vế trái `null`, phải khác `null` | Số âm | Số dương |
| Vế trái khác `null`, phải `null` | Số dương | Số âm |
| Cả hai khác `null` | Giao cho `c.compare(a,b)` | Giao cho `c.compare(a,b)` |

Chỉ **dấu** của kết quả so sánh là phần hợp đồng: đừng viết chương trình phụ thuộc bắt buộc nhận đúng `-1` hoặc `1`. Hai phương thức không sửa danh sách và không loại phần tử; chúng chỉ tạo **quy tắc thứ tự** để truyền vào nơi cần `Comparator<T>`.

Cách đọc:

- `Comparator.nullsFirst(Comparator.naturalOrder())`: các giá trị `null` đứng **trước**, các giá trị khác `null` tăng dần theo thứ tự tự nhiên.
- `Comparator.nullsLast(Comparator.naturalOrder())`: các giá trị `null` đứng **sau**, các giá trị khác `null` tăng dần.
- Phần tử không null vẫn được so bởi comparator bên trong. Hai giá trị không null có được xem ngang hàng hay không do **comparator bên trong** quyết định.

`Comparator.naturalOrder()` đòi hỏi kiểu có thứ tự tự nhiên phù hợp (thường là triển khai `Comparable`). `nullsFirst`/`nullsLast` không tự cung cấp khả năng so sánh cho những object không có thứ tự.

## 2. Ví dụ cơ bản: sắp danh sách có phần tử null

Giả sử có các số nguyên đóng hộp `Integer`:

~~~java
List<Integer> numbers =
        new ArrayList<>(Arrays.asList(3, null, 1, null, 2));

numbers.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
System.out.println(numbers); // [null, null, 1, 2, 3]

numbers.sort(Comparator.nullsLast(Comparator.naturalOrder()));
System.out.println(numbers); // [1, 2, 3, null, null]
~~~

Đây là đoạn minh họa đặt trong `main`, cần import `List`, `ArrayList`, `Arrays`, `Comparator` trong `java.util`. `ArrayList` cho phép `null`; danh sách được tạo qua `Arrays.asList` rồi sao chép thành `ArrayList` để dễ thao tác.

Nếu gọi `numbers.sort(Comparator.naturalOrder())` trực tiếp trên danh sách có `null`, phép so sánh theo thứ tự tự nhiên không xử lý được phần tử `null` và thường ném `NullPointerException`. Cách khắc phục là **bao comparator** bằng `nullsFirst` hoặc `nullsLast`, theo yêu cầu dữ liệu.

`List.of(3, null, 1)` không dùng được để tạo fixture tương tự, vì factory `List.of` từ chối `null` ngay khi tạo. Đây là chính sách của **factory collection**, độc lập với comparator.

## 3. Hai đối tượng null và hai khóa sắp xếp null là chuyện khác nhau

Xem một bản ghi:

~~~java
record Employee(String name, Integer priority) {}
~~~

Một `List<Employee>` có hai kiểu `null`:

1. **Phần tử null**: chính biến tham chiếu `Employee` trong list là `null`.
2. **Khóa null**: phần tử là `Employee` hợp lệ nhưng `employee.priority()` là `null`.

Hai cách đặt `nullsLast` cho kết quả khác nhau:

~~~java
// Xử lý phần tử Employee null, còn Employee hợp lệ được so theo priority.
Comparator<Employee> objectNullLast =
        Comparator.nullsLast(
                Comparator.comparing(Employee::priority));

// Xử lý giá trị priority null nhưng vẫn đòi hỏi Employee khác null.
Comparator<Employee> keyNullLast =
        Comparator.comparing(
                Employee::priority,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Hai đoạn là snippet minh họa và cần một record `Employee` như trên. `objectNullLast` **không an toàn khi thuộc tính `priority` bị null**, vì `Comparator.comparing(Employee::priority)` mặc định so khóa theo natural ordering. `keyNullLast` xử lý được thuộc tính `priority == null`, nhưng **không an toàn nếu toàn bộ phần tử Employee là null**, vì extractor `Employee::priority` không thể gọi trên `null`.

Muốn xử lý **cả hai**, đặt `nullsLast` ở hai tầng:

~~~java
Comparator<Employee> byPriority =
        Comparator.nullsLast(
                Comparator.comparing(
                        Employee::priority,
                        Comparator.nullsLast(
                                Comparator.naturalOrder())));
~~~

Comparator phía **trong** quyết định vị trí của *khóa* `priority == null` trong số các Employee không null. Comparator phía **ngoài** quyết định vị trí của *object* `Employee == null`. Đây là mô hình quan trọng nhất khi dữ liệu lồng các tham chiếu nullable.

Tương tự, `Comparator.comparing(Employee::name, Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER))` cho phép **tên null**, nhưng chưa cho phép **Employee null**. Nếu cần cả hai, tiếp tục bao toàn bộ comparator bằng `Comparator.nullsFirst` hoặc `nullsLast`.

## 4. Kết hợp với thenComparing để phá hòa

Một ứng dụng thường sắp nhân viên theo `priority` tăng dần, nhưng những người cùng mức ưu tiên nên được sắp tiếp theo tên. Quy tắc cần định nghĩa:

- `Employee` null đứng cuối.
- `priority` null đứng sau các ưu tiên có số.
- Trong cùng priority (kể cả hai khóa null), so tên tăng dần.
- Nếu tên có thể null, phải thêm chính sách null riêng cho tên.

Ví dụ với tên luôn không null:

~~~java
Comparator<Employee> order =
        Comparator.nullsLast(
                Comparator.comparing(
                        Employee::priority,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(Employee::name));
~~~

Đây là đoạn minh họa trong chương trình có record `Employee`. `thenComparing` chạy khi phần so sánh trước trả `0` giữa hai Employee **khác null**. Nếu cả hai priority đều null, comparator khóa trả `0`; khi ấy thứ tự theo tên mới quyết định ai đứng trước.

Nếu tên cũng nullable, thay phần tên bằng:

~~~java
.thenComparing(
        Employee::name,
        Comparator.nullsLast(Comparator.naturalOrder()))
~~~

Đây chỉ là đoạn **nối tiếp phương thức** của comparator ở trên, không phải một biểu thức Java độc lập. `thenComparing` giúp thứ tự ổn định về logic của khóa; nó **không tự xóa các bản ghi trùng**. Với `List.sort` và `Stream.sorted`, những phần tử ngang hàng theo comparator vẫn nằm trong kết quả.

## 5. reversed() có thể đảo cả vị trí null

Một nhầm lẫn thường gặp là nghĩ `reversed()` chỉ đảo tăng/giảm của giá trị không null. Trên thực tế, nó đảo **toàn bộ quan hệ thứ tự**, gồm vị trí của `null`.

~~~java
Comparator<Integer> firstAscending =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<Integer> reversedWhole = firstAscending.reversed();
// reversedWhole: số giảm dần, null chuyển xuống cuối.

Comparator<Integer> firstDescending =
        Comparator.nullsFirst(Comparator.reverseOrder());
// firstDescending: null vẫn đứng đầu, số giảm dần.
~~~

Vì vậy:

| Yêu cầu | Cách tạo comparator |
|---|---|
| Null đầu, số tăng | `nullsFirst(naturalOrder())` |
| Null cuối, số tăng | `nullsLast(naturalOrder())` |
| Null đầu, số giảm | `nullsFirst(reverseOrder())` |
| Null cuối, số giảm | `nullsLast(reverseOrder())` |
| Đảo hẳn một quy tắc đang có | `existingComparator.reversed()` |

Nếu đang có comparator nhiều tầng, gọi `reversed()` cuối cùng sẽ đảo **toàn bộ thứ tự** của nó. Để giữ vị trí null nhưng chỉ đảo một trường, hãy đảo **comparator của trường đó trước**, sau đó đưa vào `nullsFirst`/`nullsLast` tại tầng tương ứng.

## 6. Chương trình Java 17 chạy được

Lưu file **`ComparatorNullsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorNullsDemo {
    record Employee(String name, Integer priority) {}

    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(Arrays.asList(3, null, 1, null, 2));

        numbers.sort(Comparator.nullsFirst(
                Comparator.naturalOrder()));
        System.out.println("numbers first: " + numbers);

        numbers.sort(Comparator.nullsLast(
                Comparator.naturalOrder()));
        System.out.println("numbers last: " + numbers);

        List<Employee> employees = new ArrayList<>(
                Arrays.asList(
                        new Employee("Lan", null),
                        new Employee("An", 2),
                        new Employee("Binh", null),
                        new Employee("Cuong", 1),
                        null,
                        new Employee("Dung", 2)));

        Comparator<Employee> employeeOrder =
                Comparator.nullsLast(
                        Comparator.comparing(
                                Employee::priority,
                                Comparator.nullsLast(
                                        Comparator.naturalOrder()))
                                .thenComparing(Employee::name));

        employees.sort(employeeOrder);
        List<String> labels = employees.stream()
                .map(e -> e == null
                        ? "<null-employee>"
                        : e.name() + ":" + e.priority())
                .toList();
        System.out.println("employees: " + labels);

        List<Integer> reverseExample =
                new ArrayList<>(Arrays.asList(null, 1, 3));
        Comparator<Integer> firstAscending =
                Comparator.nullsFirst(Comparator.naturalOrder());

        reverseExample.sort(firstAscending.reversed());
        System.out.println("reversed whole: " + reverseExample);

        reverseExample.sort(Comparator.nullsFirst(
                Comparator.reverseOrder()));
        System.out.println("null first descending: " + reverseExample);

        Comparator<String> onlyNullPolicy =
                Comparator.nullsFirst(null);
        System.out.println("null-only rule, a vs z equal: "
                + (onlyNullPolicy.compare("a", "z") == 0));
        System.out.println("null-only rule, null before a: "
                + (onlyNullPolicy.compare(null, "a") < 0));

        TreeSet<String> names = new TreeSet<>(
                Comparator.nullsFirst(
                        String.CASE_INSENSITIVE_ORDER));
        names.add(null);
        names.add("An");
        names.add("AN");
        System.out.println("tree set size: " + names.size());
        System.out.println("tree set contains null: "
                + names.contains(null));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac ComparatorNullsDemo.java
java ComparatorNullsDemo
~~~

Đầu ra dự kiến:

~~~text
numbers first: [null, null, 1, 2, 3]
numbers last: [1, 2, 3, null, null]
employees: [Cuong:1, An:2, Dung:2, Binh:null, Lan:null, <null-employee>]
reversed whole: [3, 1, null]
null first descending: [null, 3, 1]
null-only rule, a vs z equal: true
null-only rule, null before a: true
tree set size: 2
tree set contains null: true
~~~

**Đọc kết quả:**

1. Hai comparator đầu chỉ thay vị trí của `null`, các số không null vẫn tăng dần.
2. Comparator nhân viên có **hai lớp bảo vệ null**: trường `priority` null xếp sau số, còn phần tử `Employee` null xếp cuối danh sách. `thenComparing(Employee::name)` sắp `An` trước `Dung` (cùng priority 2) và `Binh` trước `Lan` (cùng priority null).
3. `firstAscending.reversed()` chuyển null từ đầu xuống cuối, đồng thời đảo số sang giảm dần. Nếu muốn null vẫn đầu, hãy đặt `reverseOrder()` **bên trong** `nullsFirst`.
4. Khi comparator truyền vào `nullsFirst` là `null`, mọi giá trị **khác null** được coi là ngang hàng (kết quả so sánh `0`), nhưng chúng đều đứng sau null.
5. `TreeSet` được truyền comparator hỗ trợ null nên có thể chứa một null. Hai chuỗi `"An"` và `"AN"` bị coi cùng khóa vì `CASE_INSENSITIVE_ORDER.compare` trả `0`, mặc dù `String.equals` phân biệt chữ hoa/thường.

Chú ý: kết quả `TreeSet` trong ví dụ chỉ in số phần tử và phép `contains`; không nên suy rằng mọi `TreeSet` mặc định đều cho phép null. Điều đó **phụ thuộc comparator đang dùng**.

## 7. Trường hợp comparator đầu vào là null

Java cho phép:

~~~java
Comparator<String> c = Comparator.nullsLast(null);
~~~

Đây là cú pháp hợp lệ. Khi comparator đối số là **`null`**, wrapper chỉ phân biệt **null** với **khác null**; mọi giá trị khác null được xem là ngang hàng vì không có comparator nền để sắp chúng.

Hệ quả:

- `c.compare("a","z") == 0` dù hai chuỗi không bằng nhau theo `String.equals`.
- Một `TreeSet<String>` dùng `c` có thể gộp mọi chuỗi không null thành **một khóa**.
- Các phần tử không null không có quan hệ từ điển; lựa chọn này **không thay thế** `Comparator.naturalOrder()`.

Trong phần lớn chương trình muốn sắp xếp có ý nghĩa, hãy cung cấp một comparator **không null** như `naturalOrder()`, `reverseOrder()` hoặc `comparing(...)`.

## 8. Stream, List.sort và collection có thứ tự

Cùng một comparator có thể được dùng trong nhiều API:

~~~java
List<Integer> sorted = values.stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .toList();
~~~

Ở đây `values` là một `List<Integer>` đã được khai báo. `Stream.sorted` tạo stream theo thứ tự phù hợp; `toList()` nhận kết quả thành list và không yêu cầu sửa list nguồn. `List.sort(c)` sắp **trực tiếp** trên list có thể thay đổi; `Collections.sort(list, c)` dùng comparator được truyền vào.

Nếu dùng `TreeSet` hoặc `TreeMap`, `compare == 0` có ý nghĩa **trùng khóa**. Một comparator chỉ nhìn một thuộc tính hoặc comparator nền `null` có thể khiến nhiều object khác nhau theo `equals` bị gộp thành một. Việc xử lý `null` an toàn **không bảo đảm** comparator nhất quán với `equals`; cần kiểm tra hợp đồng và mục đích của collection.

## 9. Các lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| `naturalOrder()` gặp null | Không có chính sách cho null | Bao bằng `nullsFirst`/`nullsLast` |
| Bao comparator ngoài nhưng khóa vẫn null | `nullsLast(comparing(...))` chỉ xử lý **object null** | Bao comparator **của khóa** bằng nullsFirst/Last |
| Bảo vệ khóa nhưng object có thể null | Method reference trích khóa được gọi trên null | Bao toàn bộ comparator sau cùng |
| `comparingInt(Employee::priority)` với `Integer priority` null | Unboxing `null` gây `NullPointerException` | Dùng `comparing` với comparator xử lý khóa null hoặc chọn giá trị mặc định |
| `reversed()` làm null đổi vị trí | Đảo toàn bộ thứ tự | Đảo comparator nền **trước** khi bao null policy |
| `nullsFirst(null)` dùng để sắp chuỗi theo chữ | Mọi giá trị không null ngang nhau | Truyền `Comparator.naturalOrder()` hoặc comparator thực sự |
| `TreeSet` mất các object khác nhau | Comparator trả `0` cho nhiều giá trị | Thêm tie-breaker phân biệt khóa hoặc chọn collection khác |
| Tưởng `nullsLast` lọc hết null | Wrapper chỉ quy định thứ tự | Dùng `filter(Objects::nonNull)` nếu bài toán thật sự cần loại null |
| Tên/khóa phụ cũng null | `thenComparing` không được bảo vệ | Định nghĩa null policy cho từng khóa có thể null |

## 10. Chọn phương án theo yêu cầu

- **Null đầu, giá trị tăng dần:** `Comparator.nullsFirst(Comparator.naturalOrder())`.
- **Null cuối, giá trị tăng dần:** `Comparator.nullsLast(Comparator.naturalOrder())`.
- **Null cuối, giá trị giảm dần:** `Comparator.nullsLast(Comparator.reverseOrder())`.
- **Object không null nhưng khóa nullable:** `Comparator.comparing(Foo::key, Comparator.nullsLast(Comparator.naturalOrder()))`.
- **Cả object và khóa có thể null:** bao comparator khóa như trên, rồi `Comparator.nullsLast(...)` cho object.
- **Nhiều khóa:** dùng `thenComparing`; đặt null policy **ở từng khóa** cần xử lý null.

Khi kiểm thử, cần thử tối thiểu các cặp: `null/null`, `null/value`, `value/null`, hai value khác nhau, hai object không null có khóa null, hai object có cùng khóa nhưng thuộc tính phụ khác nhau, và cả đảo thứ tự với `reversed()`.

## 11. Tự kiểm tra

**Câu 1.** `Comparator.nullsFirst(Comparator.naturalOrder())` so `null` với số 5 cho kết quả gì?  
**Đáp án:** Một số âm; null đứng trước 5. Không phụ thuộc giá trị số âm cụ thể.

**Câu 2.** Tại sao `Comparator.nullsLast(Comparator.comparing(Employee::priority))` vẫn có thể ném exception?  
**Đáp án:** Nó chỉ cho phép **Employee object** null. Một Employee khác null có `priority == null` vẫn gây lỗi khi so khóa theo natural ordering.

**Câu 3.** Muốn sắp priority giảm dần nhưng priority null vẫn ở cuối thì dùng gì?  
**Đáp án:** `Comparator.comparing(Employee::priority, Comparator.nullsLast(Comparator.reverseOrder()))` cho các Employee khác null; bao thêm ngoài nếu Employee có thể null.

**Câu 4.** Nếu có `Comparator<Integer> c = Comparator.nullsFirst(Comparator.naturalOrder())`, dùng `c.reversed()` còn giữ null đầu không?  
**Đáp án:** Không. Nó đảo toàn bộ thứ tự nên null xuống cuối và các số giảm dần.

**Câu 5.** `Comparator.nullsLast(null)` có so được hai String theo chữ cái không?  
**Đáp án:** Không. Nó xem tất cả hai String khác null là ngang hàng, trả `0`.

**Ghi nhớ:** `nullsFirst`/`nullsLast` **bọc một comparator**, đưa null lên đầu hoặc xuống cuối nhưng không tự so nội dung non-null. Với object có thuộc tính nullable, hãy đặt chính sách null **đúng tầng**, và cân nhắc hiệu ứng của `reversed`, `thenComparing` cùng collection đang sử dụng.
