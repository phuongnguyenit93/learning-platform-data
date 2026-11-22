# Sắp xếp theo nhiều khóa và xử lý khóa null trong Java Stream

Khi dữ liệu có nhiều tiêu chí sắp xếp, một khóa thường không đủ. Ví dụ, danh sách nhân viên có thể cần **phòng ban tăng dần → tuổi tăng dần → tên tăng dần**; danh sách điểm có thể cần **điểm giảm dần → nhóm tăng dần → mã định danh tăng dần**. Trong thực tế, một vài trường là `null`. Nếu viết bộ so sánh mà không xác định cách đặt `null`, pipeline `Stream.sorted()` có thể ném `NullPointerException` hoặc trả kết quả không đúng nghiệp vụ.

Java giải quyết vấn đề bằng cách **ghép các `Comparator` theo thứ tự ưu tiên** và đặt `Comparator.nullsFirst()`/`nullsLast()` ở **đúng cấp**:

- `Comparator.comparing(...)`, `comparingInt(...)`, `comparingLong(...)`, `comparingDouble(...)`: định nghĩa tiêu chí đầu tiên.
- `thenComparing(...)`, `thenComparingInt(...)`, ...: bổ sung tiêu chí tiếp theo, chỉ dùng khi các tiêu chí trước trả kết quả bằng nhau.
- `Comparator.nullsFirst(c)` hoặc `nullsLast(c)`: xử lý **đối tượng được so sánh trực tiếp bởi `c`**. Có thể là *giá trị khóa* hoặc *cả phần tử* tùy nơi đặt.
- `Comparator.reverseOrder()` và `reversed()`: đảo thứ tự; phải đặt đúng cấp để giữ chính sách `null` mong muốn.

Bài này sử dụng Java 17+ và nhấn mạnh cách đọc một bộ so sánh theo thứ tự **khóa chính → khóa phụ → chính sách null → chiều sắp xếp**.

## 1. Cách `thenComparing` quyết định thứ tự

Một `Comparator<T>` so sánh hai phần tử và trả về:

- Giá trị âm nếu phần tử thứ nhất đứng trước phần tử thứ hai;
- `0` nếu hai phần tử bằng nhau **theo tiêu chí của comparator**, dù bản thân chúng không nhất thiết `equals()`;
- Giá trị dương nếu phần tử thứ nhất đứng sau phần tử thứ hai.

Với `comparatorA.thenComparing(comparatorB)`:

1. Thử khóa A.
2. Nếu A cho kết quả khác `0`, giữ nguyên kết quả, **không gọi** comparator B.
3. Chỉ khi A trả `0`, mới so tiếp khóa B.
4. Có thể nối nhiều lần để tạo khóa thứ ba, thứ tư, v.v.

Ví dụ:

~~~java
Comparator<Employee> order =
        Comparator.comparing(Employee::department)
                  .thenComparingInt(Employee::age)
                  .thenComparing(Employee::name);
~~~

Đây là **đoạn minh họa**, giả định `Employee.department()` và `Employee.name()` trả `String` khác `null`, còn `Employee.age()` trả `int`. `department` là khóa chính, `age` là khóa phụ, `name` là khóa thứ ba. Vì khóa sau chỉ được xét khi khóa trước bằng nhau, **thứ tự gọi `thenComparing` chính là độ ưu tiên của các khóa**.

`Comparator.comparingInt` nhận `ToIntFunction<T>` và dùng so sánh `int` phù hợp, tránh boxing chỉ để biểu diễn khóa nguyên thủy. Với trường `Integer` có thể null, **không dùng trực tiếp `comparingInt`** nếu muốn giữ null như một trạng thái riêng, bởi bước unboxing sang `int` có thể gây lỗi.

## 2. Phân biệt ba loại null cần xử lý

Khi sắp xếp một `List<Employee>`, có thể gặp các cấp sau:

| Vị trí null | Ví dụ | Vấn đề | Cách xử lý |
| --- | --- | --- | --- |
| **Phần tử** trong danh sách | `null` thay vì `Employee` | Method reference `Employee::department` không thể gọi trên phần tử null | Bọc **comparator toàn phần tử** bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`. |
| **Khóa chính** trong đối tượng | `employee.department() == null` | Comparator tự nhiên của `String` không so được null | Dùng `comparing(Employee::department, nullsLast(naturalOrder()))`. |
| **Khóa phụ** trong đối tượng | `employee.age() == null` (kiểu `Integer`) | `comparingInt` phải unbox `Integer null` | Dùng `thenComparing(Employee::age, nullsLast(naturalOrder()))`. |

Thêm nữa, trường tên dùng để phá hòa có thể null, và cần chính sách riêng. **Một lớp `nullsLast` không tự bảo vệ mọi cấp.** Chẳng hạn:

~~~java
// Chỉ xử lý null của đối tượng Employee, KHÔNG xử lý khóa department null:
Comparator<Employee> incomplete = Comparator.nullsLast(
        Comparator.comparing(Employee::department));
~~~

Nếu `Employee` hiện diện nhưng `department` null, comparator bên trong vẫn có thể ném `NullPointerException`.

Ngược lại:

~~~java
// Xử lý department null, KHÔNG xử lý phần tử Employee null:
Comparator<Employee> alsoIncomplete = Comparator.comparing(
        Employee::department,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Nếu một phần tử danh sách là null, biểu thức `Employee::department` vẫn không thể chạy. Giải pháp khi **cả hai cấp đều nullable** là bọc comparator ngoài cùng sau khi đã xây dựng các khóa bên trong.

## 3. Ví dụ đầy đủ: phòng ban, tuổi, tên và null ở nhiều cấp

Định nghĩa quy tắc nghiệp vụ:

1. Phòng ban **tăng dần**, phòng ban null **sau** các phòng ban có giá trị;
2. Trong cùng phòng ban, tuổi `Integer` **tăng dần**, tuổi null **sau** tuổi có giá trị;
3. Nếu phòng ban và tuổi cùng bằng nhau, tên **tăng dần**;
4. Nếu cả phần tử `Employee` là null thì xếp **cuối cùng**.

Tạo file `MultiKeyNullSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class MultiKeyNullSortDemo {
    record Employee(String name, String department, Integer age) {}

    public static void main(String[] args) {
        List<Employee> employees = new ArrayList<>(Arrays.asList(
                new Employee("An", "Sales", 28),
                new Employee("Bình", null, 22),
                new Employee("Chi", "HR", null),
                new Employee("Dũng", "HR", 22),
                new Employee("Em", "Sales", null),
                new Employee("Gia", null, null),
                null
        ));

        Comparator<Employee> nonNullEmployees =
                Comparator.comparing(
                        Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(
                        Employee::age,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(
                        Employee::name,
                        Comparator.nullsLast(Comparator.naturalOrder()));

        Comparator<Employee> order =
                Comparator.nullsLast(nonNullEmployees);

        List<Employee> sorted = employees.stream()
                .sorted(order)
                .toList();

        for (Employee employee : sorted) {
            if (employee == null) {
                System.out.println("<null employee>");
            } else {
                System.out.println(
                        employee.department() + " | "
                        + employee.age() + " | "
                        + employee.name());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 MultiKeyNullSortDemo.java
java MultiKeyNullSortDemo
~~~

Kết quả:

~~~text
HR | 22 | Dũng
HR | null | Chi
Sales | 28 | An
Sales | null | Em
null | 22 | Bình
null | null | Gia
<null employee>
~~~

Đọc comparator từ trong ra ngoài:

- `Comparator.comparing(Employee::department, ...)`: tạo khóa phòng ban `String`. Comparator của **khóa** được bọc bằng `nullsLast`.
- `.thenComparing(Employee::age, ...)`: chỉ so tuổi khi hai phòng ban bằng nhau; khóa `Integer` null được đưa cuối.
- `.thenComparing(Employee::name, ...)`: tên là khóa thứ ba, bảo vệ null của tên cho dữ liệu mở rộng.
- `Comparator.nullsLast(nonNullEmployees)`: bao phủ **cả phần tử null**. Chỉ khi hai `Employee` đều không null mới cần gọi getter.

`employees.stream().sorted(order)` **không sắp xếp tại chỗ** danh sách gốc; `toList()` trả danh sách kết quả không hỗ trợ thao tác sửa. Nếu cần sắp xếp danh sách có thể chỉnh sửa tại chỗ, gọi `employees.sort(order)` trên `ArrayList`.

Điểm dễ sai: `List.of(...)` không cho chứa phần tử null. Ví dụ chủ ý dùng `Arrays.asList(...)` rồi bọc `ArrayList`; cách đó cho phép dữ liệu đầu vào có null.

## 4. Thiết kế nhiều khóa tăng/giảm độc lập

Yêu cầu thường là **điểm cao nhất trước**, sau đó **nhóm theo chữ cái**, rồi **mã định danh tăng dần**. Đồng thời, điểm và nhóm có thể null, phải ở cuối nhóm tương ứng.

Không nên đảo nguyên comparator đã có chính sách null; hãy đặt chiều so sánh ngay **bên trong comparator của từng khóa**.

Tạo file `MixedDirectionSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class MixedDirectionSortDemo {
    record Entry(String label, Integer score, String team, int id) {}

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>(Arrays.asList(
                new Entry("A", 90, "red", 2),
                new Entry("B", 90, null, 1),
                new Entry("C", null, "blue", 3),
                new Entry("D", 100, "blue", 4),
                null,
                new Entry("E", 90, "red", 1)
        ));

        Comparator<Entry> nonNullEntries =
                Comparator.comparing(
                        Entry::score,
                        Comparator.nullsLast(Comparator.reverseOrder()))
                .thenComparing(
                        Entry::team,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparingInt(Entry::id);

        Comparator<Entry> order =
                Comparator.nullsLast(nonNullEntries);

        entries.stream()
                .sorted(order)
                .forEach(entry -> System.out.println(
                        entry == null ? "<null>" : entry.label()));
    }
}
~~~

~~~bash
javac --release 17 MixedDirectionSortDemo.java
java MixedDirectionSortDemo
~~~

Kết quả:

~~~text
D
E
A
B
C
<null>
~~~

Giải thích kết quả:

- `D` có điểm 100, trước các điểm 90.
- `E` và `A` đều điểm 90, nhóm `red`; mã 1 của E trước mã 2 của A.
- `B` cũng điểm 90 nhưng nhóm null nên đứng sau nhóm `red` cùng điểm.
- `C` có điểm null và vì vậy đứng sau các mục có điểm.
- Phần tử `null` đứng cuối cùng nhờ comparator bọc ngoài cùng.

Việc dùng `Comparator.reverseOrder()` **bên trong** `nullsLast(...)` chỉ đảo các điểm khác null; null vẫn ở cuối. Đây là thứ tự triển khai đúng khi đặc tả là “giảm dần, thiếu điểm cuối”.

## 5. Bẫy `reversed()`: đảo cả chính sách null

Xét các biểu thức:

~~~java
// Giả sử Entry::score trả Integer, Entry không null.
Comparator<Entry> descNullLast = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.reverseOrder()));

Comparator<Entry> descButNullFirst = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.naturalOrder()))
        .reversed();
~~~

Biểu thức đầu là **điểm giảm dần nhưng null cuối**. Biểu thức sau xây dựng “điểm tăng dần, null cuối” trước, sau đó gọi `reversed()` trên **toàn bộ comparator**, nên cho ra “điểm giảm dần, null đầu”.

Nếu đang có:

~~~java
Comparator<Entry> order = Comparator.nullsLast(
        Comparator.comparingInt(Entry::id));
~~~

thì `order.reversed()` không chỉ đổi mã tăng thành giảm, mà **cũng đưa phần tử Entry null lên đầu**. Để giữ null cuối trong khi đảo mã, hãy đảo comparator bên trong trước:

~~~java
Comparator<Entry> descIdNullLast = Comparator.nullsLast(
        Comparator.comparingInt(Entry::id).reversed());
~~~

Các đoạn ở mục này là **minh họa trong phạm vi phương thức** với lớp `Entry` đã tồn tại. Nguyên tắc chung: **đảo tiêu chí cần đảo trước, áp dụng chính sách null ở tầng cần giữ sau**.

## 6. Đặt `nullsLast` ở cuối chuỗi nhiều khóa

Sai lầm khó thấy là thêm `thenComparing` **sau khi** đã bọc toàn bộ phần tử bằng `nullsLast`:

~~~java
// Nguy hiểm nếu đầu vào có hai phần tử null:
Comparator<Employee> unsafe =
        Comparator.nullsLast(
                Comparator.comparing(Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder())))
                  .thenComparing(Employee::name);
~~~

Khi **cả hai Employee đều null**, `nullsLast` xem chúng ngang nhau và trả `0`. `thenComparing(Employee::name)` bên ngoài tiếp tục gọi getter qua null, gây `NullPointerException`.

Cấu trúc an toàn hơn:

~~~java
Comparator<Employee> safe = Comparator.nullsLast(
        Comparator.comparing(
                        Employee::department,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                  .thenComparing(
                        Employee::name,
                        Comparator.nullsLast(Comparator.naturalOrder())));
~~~

Bây giờ lớp null của **đối tượng Employee** ở bên ngoài toàn bộ chuỗi, xử lý các phần tử null trước khi gọi bất kỳ getter nào. Nếu tên không nullable và dữ liệu bảo đảm không null, comparator khóa phụ có thể viết `thenComparing(Employee::name)` cho gọn.

## 7. `comparingInt`, `comparingLong` và khóa nullable

Khi khóa thực sự là primitive `int`, dùng:

~~~java
Comparator<Entry> byId = Comparator.comparingInt(Entry::id);
~~~

Khi khóa là `Integer` có thể null, cách sau **không an toàn**:

~~~java
// Minh họa nguy cơ, không chạy mã này với score == null.
Comparator<Entry> unsafeScore =
        Comparator.comparingInt(e -> e.score());
// e.score() trả Integer; Java tự unbox thành int và có thể ném NPE.
~~~

Thay bằng:

~~~java
Comparator<Entry> safeScore = Comparator.comparing(
        Entry::score,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

`Comparator.comparingLong` và `comparingDouble` cũng dùng các extractor primitive tương ứng; nếu getter trả `Long`/`Double` nullable thì cần chính sách null qua `comparing` cho kiểu wrapper hoặc quy tắc thay thế rõ ràng.

Có thể chuyển null thành một số sentinel để tiếp tục dùng `comparingInt`, nhưng chỉ khi nghiệp vụ **thật sự quy định null tương đương giá trị đó**:

~~~java
Comparator<Entry> fallback = Comparator.comparingInt(
        e -> e.score() == null ? -1 : e.score());
~~~

Nếu điểm thật có thể là -1, hai trường hợp “thiếu điểm” và “điểm -1” trở thành cùng khóa. Dùng `nullsLast` cho `Integer` khi cần phân biệt chúng rõ ràng.

Không viết comparator số dạng `(a, b) -> a.id() - b.id()`: phép trừ có thể tràn `int`, phá hợp đồng comparator. `comparingInt` sử dụng phép so sánh số nguyên đúng thay vì dựa vào phép trừ.

## 8. Kiểu dữ liệu ở từng bước trong Stream pipeline

Với `Stream<Employee>`, thao tác `sorted(comparator)` **không thay đổi kiểu phần tử**:

~~~text
List<Employee>
  .stream()                             → Stream<Employee>
  .filter(Objects::nonNull)              → Stream<Employee>
  .sorted(Comparator<Employee>)          → Stream<Employee>
  .map(Employee::name)                   → Stream<String>
  .toList()                              → List<String>
~~~

Sắp xếp nên thực hiện trên kiểu chứa **mọi khóa cần thiết**. Ví dụ, nếu chuyển `Employee` sang tên `String` trước khi sort, `Stream<String>` không còn truy cập được phòng ban và tuổi để so theo nhiều khóa.

Nếu yêu cầu loại bỏ phần tử null thay vì xếp chúng đầu/cuối, có thể chủ động lọc:

~~~java
// Giả sử employees: List<Employee> và comparator cho Employee không null.
List<Employee> valid = employees.stream()
        .filter(java.util.Objects::nonNull)
        .sorted(nonNullEmployees)
        .toList();
~~~

Đây là **thay đổi tập kết quả** (loại bỏ null), khác với sắp xếp để giữ tất cả phần tử. Không dùng `filter(Objects::nonNull)` chỉ nhằm che việc thiếu chính sách nghiệp vụ.

## 9. Tính ổn định và các khóa bằng nhau

`List.sort` là phép sắp xếp **ổn định**: nếu comparator trả `0`, thứ tự tương đối ban đầu của các phần tử đó được giữ. `Stream.sorted` cũng bảo đảm ổn định với **ordered stream**; đối với unordered stream thì không có bảo đảm tương tự.

Ví dụ, hai `Employee` có cùng department và age sẽ được so bằng tên nếu có `thenComparing(Employee::name)`. Nếu tên cũng bằng, comparator trả `0`; với ordered stream, chúng giữ thứ tự gặp ban đầu.

Điều này có hai ý nghĩa thực tế:

1. Nếu muốn phân trang hoặc xuất báo cáo có thứ tự **hoàn toàn xác định** ngay cả khi các khóa nghiệp vụ trùng, thêm khóa phá hòa ổn định (ví dụ `id` duy nhất) ở cuối chuỗi.
2. `Comparator.compare(a, b) == 0` không đồng nghĩa `a.equals(b)`. Trong `TreeSet`/`TreeMap`, phần tử/khóa được xem là trùng theo comparator nếu trả `0`, vì vậy thiếu khóa phân biệt có thể khiến dữ liệu bị gộp trong cấu trúc đó.

Với stream từ `HashSet` hoặc nguồn không có encounter order xác định, không dựa vào tính ổn định để suy ra thứ tự giữa các phần tử bằng khóa. Hãy cung cấp khóa phá hòa đầy đủ nếu cần đầu ra tái lập.

## 10. Chi phí và hành vi thực thi của `sorted`

`Stream.sorted()` là thao tác trung gian **stateful**. Để sắp xếp toàn bộ tập hữu hạn theo nhiều khóa, hệ thống thường cần nắm dữ liệu đủ để xác định thứ tự; không nên giả định nó có thể phát ra từng kết quả ngay từ phần tử đầu như một `filter` thuần. Việc tạo comparator là rẻ, nhưng sắp xếp thường có chi phí tăng theo kích thước đầu vào (thông thường cỡ `O(n log n)` số phép so sánh, tùy thuật toán và dữ liệu).

**Hàm trích xuất khóa có thể được gọi nhiều lần**, nên cần tránh:

- truy vấn database/mạng trong `Comparator.comparing(x -> expensiveLookup(x))`;
- sửa trạng thái trong getter hoặc `thenComparing`;
- phụ thuộc vào đồng hồ/thông tin biến thiên liên tục khi comparator được gọi;
- thực hiện logic có side effect như ghi file, gửi thông báo hoặc thay đổi đối tượng đang sắp xếp.

Nếu khóa đắt tiền hoặc dễ thay đổi, tính **snapshot key** trước khi sắp xếp, rồi so trên giá trị ổn định. Với dữ liệu lớn, đo chi phí thực tế; tránh tái tính cùng khóa nhiều lần trong quá trình so sánh. Phép tối ưu cần giữ đầy đủ các quy tắc null và thứ tự khóa.

Stream pipeline như:

~~~java
// Minh họa cấu trúc xử lý, source là Stream<Employee>.
source.sorted(order).limit(10).toList();
~~~

thường vẫn phải xét phạm vi dữ liệu đủ lớn để biết **10 phần tử nhỏ nhất** theo comparator; việc đặt `limit(10)` sau `sorted` không có nghĩa chỉ sắp xếp 10 phần tử đầu của nguồn. Không nên dùng `sorted` trên nguồn vô hạn rồi mong `limit` sẽ luôn cho kết quả hữu hạn.

## 11. Chuỗi khóa và thứ tự theo locale

`Comparator.naturalOrder()` cho `String` dùng thứ tự tự nhiên dựa trên `String.compareTo`. Đây là thứ tự theo giá trị ký tự UTF-16, **không mặc nhiên là thứ tự từ điển tiếng Việt** hoặc thứ tự tự nhiên phù hợp người đọc.

Nếu ứng dụng cần thứ tự theo ngôn ngữ, dùng chiến lược so sánh địa phương hóa, chẳng hạn `Collator` từ `java.text` với locale thích hợp. Vì `Collator` có cấu hình mutable, nên thiết lập và quản lý instance cẩn thận, đặc biệt với sắp xếp song song. Nếu cần xử lý khóa `String` null, bọc comparator ngôn ngữ đó bằng `nullsFirst`/`nullsLast` giống như comparator tự nhiên.

Ví dụ chỉ minh họa cấu trúc:

~~~java
// Trong phương thức có type Employee và import các kiểu liên quan.
java.text.Collator collator =
        java.text.Collator.getInstance(java.util.Locale.forLanguageTag("vi-VN"));

Comparator<Employee> byVietnameseName = Comparator.comparing(
        Employee::name,
        Comparator.nullsLast(collator));
~~~

Các ví dụ có `naturalOrder()` trong bài chỉ xác định **thứ tự tự nhiên Java**, không khẳng định quy tắc sắp xếp tên theo văn hóa/locale.

## 12. Xác định đầu ra và kiểm thử comparator

Một bộ so sánh nhiều khóa nên được thử với ít nhất các trường hợp sau:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Hai khóa chính khác nhau | Khóa chính có ưu tiên đúng, khóa phụ không lấn át. |
| Khóa chính giống nhau, khóa phụ khác nhau | `thenComparing` xử lý đúng chiều. |
| Nhiều khóa bằng nhau | Khóa cuối cùng phá hòa, hoặc ổn định khi comparator trả `0`. |
| Khóa chính null / không null | Null nằm đầu hay cuối như đặc tả. |
| Khóa phụ null / không null | Null trong trường phụ không gây unboxing hoặc NPE. |
| Phần tử null / không null | Bọc comparator ngoài cùng đúng. |
| Hai phần tử cùng null | Không bị gọi getter khóa phụ trên null. |
| Điểm âm, 0, số cực trị | Không dùng phép trừ tràn số; xử lý sentinel hợp lệ. |
| `reversed()` và nhiều chiều sắp xếp | Chỉ tiêu chí cần đảo thay đổi; null giữ đúng vị trí. |
| Dữ liệu cùng khóa từ nguồn unordered | Có khóa phá hòa nếu thứ tự cần xác định. |

Comparator cần có thứ tự nhất quán: tính phản đối xứng, bắc cầu, và kết quả so sánh phải dựa trên dữ liệu ổn định. Một comparator “tùy hứng” trả kết quả khác nhau cho cùng hai đối tượng có thể khiến `sort` thất bại, thậm chí ném `IllegalArgumentException` với thông báo comparator vi phạm hợp đồng. Đừng xử lý lỗi bằng cách bắt ngoại lệ và trả `0` vô điều kiện: cần sửa quan hệ thứ tự.

Một cách kiểm tra thủ công là viết chuỗi khóa mong đợi cạnh tập mẫu, ví dụ:

~~~text
Yêu cầu: department ASC NULLS LAST
        → age ASC NULLS LAST
        → name ASC NULLS LAST
        → Employee NULLS LAST

HR / 22 / Dũng
HR / null / Chi
Sales / 28 / An
Sales / null / Em
null / 22 / Bình
null / null / Gia
<null employee>
~~~

Đây là lý do khóa trống của phòng ban nằm **sau** Sales dù tuổi của Bình là 22. Khóa phụ không được phép vượt quyền ưu tiên của khóa chính.

## 13. Những lỗi thường gặp

1. **Dùng `comparingInt` với trường `Integer` nullable:** auto-unboxing có thể ném NPE; dùng `comparing` với comparator null-safe của khóa.
2. **Bọc `nullsLast` ngoài cùng rồi nghĩ mọi getter null đều an toàn:** lớp ngoài chỉ xử lý phần tử null, không tự xử lý các khóa nullable.
3. **Đặt `thenComparing` sau lớp bọc phần tử null:** khi hai phần tử đều null, getter khóa phụ vẫn có thể được gọi.
4. **Gọi `reversed()` lên comparator đã bọc null:** chính sách đầu/cuối của null bị đảo ngoài ý muốn.
5. **Đổi thứ tự `thenComparing` tùy tiện:** khóa đứng trước luôn có quyền ưu tiên cao hơn khóa đứng sau.
6. **Sắp xếp sau `map` làm mất các khóa:** một `Stream<String>` không còn đủ dữ liệu để so theo tuổi, phòng ban của đối tượng ban đầu.
7. **Bỏ khóa phá hòa khi cần kết quả ổn định giữa nhiều nguồn:** nguồn unordered và dữ liệu nhiều khóa trùng có thể gây thứ tự không xác định.
8. **Nhầm `Stream.sorted` với sắp xếp tại chỗ:** nó trả một stream mới trong pipeline; `List.sort` trên list mutable mới thay đổi danh sách.
9. **Coi thứ tự `String.compareTo` là thứ tự tiếng Việt:** nếu yêu cầu địa phương hóa, cần comparator tương ứng.
10. **Dùng key extractor có side effect hoặc dữ liệu thường xuyên đổi:** có thể vi phạm hợp đồng comparator và tạo lỗi khó tái hiện.

## 14. Quy tắc thực hành

Để viết comparator cho nhiều khóa có null, nên đi theo thứ tự:

1. Viết rõ **thứ tự khóa** theo đặc tả (khóa chính trước, rồi khóa phụ).
2. Với **từng khóa**, xác định kiểu primitive hay reference và khả năng null.
3. Quy định riêng **chiều ASC/DESC** và **NULLS FIRST/LAST** của mỗi khóa.
4. Dùng `comparing` cho khóa reference nullable và `comparingInt/Long/Double` cho khóa primitive phù hợp.
5. Ghép toàn bộ các khóa bằng `thenComparing`, kèm khóa phá hòa nếu cần.
6. Nếu **cả phần tử** có thể null, bọc comparator hoàn chỉnh bằng `nullsFirst`/`nullsLast` sau cùng.
7. Chạy thử với dữ liệu có khóa bằng nhau, null ở các tầng, và giá trị biên; kiểm tra thứ tự in ra có đúng yêu cầu.

**Ghi nhớ:** với nhiều khóa, `thenComparing` quyết định **mức ưu tiên**; comparator trong `comparing(..., keyComparator)` quyết định **thứ tự và chính sách null của từng khóa**; lớp `nullsFirst/nullsLast` bao quanh toàn bộ comparator quyết định **vị trí của phần tử null**. Đặt đúng từng tầng giúp `Stream.sorted()` rõ nghĩa, an toàn và dễ kiểm thử.
