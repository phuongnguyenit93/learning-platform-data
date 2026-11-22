# Sắp xếp toàn mảng hoặc một khoảng trong Java

`java.util.Arrays.sort(...)` là API chuẩn để sắp xếp phần tử **ngay trong mảng ban đầu**, có từ lâu và vẫn được hỗ trợ trong Java hiện hành. Với mảng `int[]`, `double[]`, `String[]` hay một mảng object, ta có thể yêu cầu:

- **Sắp xếp toàn bộ mảng:** `Arrays.sort(a)`.
- **Sắp xếp một khoảng liên tiếp:** `Arrays.sort(a, fromIndex, toIndex)`.
- **Định nghĩa thứ tự cho object:** `Arrays.sort(objects, comparator)` hoặc `Arrays.sort(objects, fromIndex, toIndex, comparator)`.
- **Cân nhắc xử lý song song:** `Arrays.parallelSort(...)`, cũng có overload toàn mảng hoặc theo khoảng.

Hai điều cốt lõi là: **khoảng sắp xếp dạng nửa mở `[fromIndex, toIndex)`** và **sort làm thay đổi chính mảng đã truyền vào**. Bài này giải thích rõ cú pháp, hợp đồng, độ ổn định, comparator, xử lý null, số thực đặc biệt, biên chỉ số, việc không thay đổi dữ liệu gốc và cách kiểm thử.

## 1. Lựa chọn đúng overload

Những dạng lời gọi phổ biến:

~~~java
Arrays.sort(numbers);                     // Toàn mảng primitive.
Arrays.sort(numbers, fromIndex, toIndex); // Một khoảng primitive.

Arrays.sort(words);                       // Toàn mảng object, natural order.
Arrays.sort(words, fromIndex, toIndex);   // Khoảng object, natural order.

Arrays.sort(tasks, byPriority);           // Toàn mảng object, comparator.
Arrays.sort(tasks, fromIndex, toIndex, byPriority); // Khoảng object.

Arrays.parallelSort(numbers);             // Tùy triển khai, có thể dùng song song.
Arrays.parallelSort(numbers, fromIndex, toIndex);
~~~

Đây là **mẫu cú pháp**, cần import `java.util.Arrays`, có sẵn các mảng/biến `numbers`, `words`, `tasks`, `byPriority` và chỉ số hợp lệ.

| Dữ liệu và mục tiêu | Phương thức phù hợp | Thứ tự sử dụng |
|---|---|---|
| `int[]`, `long[]`, `double[]`, v.v., toàn bộ | `Arrays.sort(a)` | Thứ tự tăng dần tự nhiên của kiểu primitive |
| `int[]` hoặc kiểu primitive khác, chỉ một đoạn | `Arrays.sort(a, from, to)` | Tăng dần trong đoạn |
| `String[]` hoặc object `Comparable` | `Arrays.sort(a)` | Thứ tự tự nhiên do `compareTo` xác định |
| `T[]` theo thứ tự nghiệp vụ | `Arrays.sort(a, comparator)` | Thứ tự từ `Comparator` |
| `T[]`, chỉ một đoạn, theo comparator | `Arrays.sort(a, from, to, comparator)` | Chỉ thay đổi đoạn đã chỉ định |
| Mảng lớn, cần đo hiệu năng thực | `Arrays.parallelSort(...)` | Có thể thực hiện một phần công việc song song |

`Arrays.sort` hỗ trợ những mảng primitive có thứ tự số như `byte[]`, `short[]`, `char[]`, `int[]`, `long[]`, `float[]`, `double[]`, và mảng object. **Không có overload `Arrays.sort(boolean[])`**, vì `boolean` không có thứ tự số học tự nhiên như các kiểu trên.

Trong phần còn lại, mọi code cần `import java.util.Arrays;` (và `java.util.Comparator` khi dùng comparator), trừ khi được ghi rõ là ví dụ độc lập.

## 2. Sắp xếp toàn bộ mảng primitive

Ví dụ đơn giản:

~~~java
int[] scores = {9, 1, 5, 3};
Arrays.sort(scores);

System.out.println(Arrays.toString(scores));
// [1, 3, 5, 9]
~~~

Mảnh code này đặt trong một phương thức. `Arrays.sort(scores)` sắp lại **chính các phần tử của `scores`**, chứ không trả về một mảng khác. Đây là phép thay đổi (*mutating*) và giá trị trả về của `sort` là `void`.

Với mảng `int[]` thông thường, kết quả là thứ tự tăng dần: phần tử nhỏ đứng trước phần tử lớn. Những giá trị bằng nhau vẫn được giữ đủ số lần xuất hiện; `sort` không khử trùng lặp và không chuyển mảng thành Set.

~~~java
int[] numbers = {4, -2, 4, 0};
Arrays.sort(numbers); // [-2, 0, 4, 4]
~~~

Lưu ý: `Arrays.toString(a)` chỉ dùng để **in trực quan một mảng một chiều**; in trực tiếp một mảng bằng `System.out.println(a)` không cho danh sách phần tử dễ đọc.

### 2.1. Primitive khác: char, long, double

- `long[]` được sắp theo giá trị `long` có dấu, tăng dần.
- `char[]` được sắp theo giá trị `char` (đơn vị mã UTF-16), **không phải sắp từ tiếng Việt theo quy tắc ngôn ngữ**; nếu cần thứ tự chữ, phải chọn giải pháp so sánh chuỗi/ngôn ngữ phù hợp.
- `float[]` và `double[]` có quy tắc thứ tự tổng đặc biệt để xử lý `NaN` và hai loại zero, không chỉ dựa vào toán tử `<`.
- `boolean[]` không có lời gọi `Arrays.sort` hợp lệ.

Với mảng primitive, `Arrays.sort(a, comparator)` **không tồn tại**. Nếu muốn một thứ tự tùy biến bằng comparator, thường phải dùng mảng object, ví dụ `Integer[]`, hoặc dùng một thuật toán chuyên biệt trên `int[]`. Cần cân nhắc boxing và chi phí bộ nhớ nếu dữ liệu rất lớn.

## 3. Sắp xếp một khoảng: [fromIndex, toIndex)

Ký hiệu `[fromIndex, toIndex)` nghĩa là:

- `fromIndex` được tính **bao gồm**.
- `toIndex` được tính **loại trừ**.
- Chỉ những vị trí có `fromIndex <= i < toIndex` mới được sắp lại.
- Các vị trí **bên ngoài khoảng** được giữ nguyên.

Ví dụ:

~~~java
int[] data = {9, 7, 4, 1, 8, 2};
Arrays.sort(data, 1, 5);

System.out.println(Arrays.toString(data));
// [9, 1, 4, 7, 8, 2]
~~~

Ở đây, mảng có chỉ số 0 đến 5; chỉ sắp đoạn có chỉ số **1, 2, 3, 4**.

~~~text
Chỉ số:   0  1  2  3  4  5
Trước:    9  7  4  1  8  2
             |--------|
Sắp:         [7, 4, 1, 8]  ->  [1, 4, 7, 8]
Sau:      9  1  4  7  8  2
           ^              ^
        giữ nguyên     giữ nguyên
~~~

Dấu `[from, to)` thường dùng cho nhiều API Java khác như `Arrays.copyOfRange` hoặc `List.subList`, nhưng cần đọc hợp đồng từng API; không dựa vào việc tên phương thức “có vẻ giống nhau”.

### 3.1. Các khoảng thường gặp

Giả sử `n = array.length`:

| Khoảng | Ý nghĩa | Kết quả |
|---|---|---|
| `[0, n)` | Toàn bộ mảng | Tương đương về vùng sắp xếp với `Arrays.sort(array)` |
| `[1, n - 1)` | Bỏ phần tử đầu và phần tử cuối | Chỉ phần giữa thay đổi |
| `[k, k)` | Khoảng rỗng | Không phần tử nào thay đổi |
| `[k, k + 1)` | Một phần tử | Kết quả không đổi |
| `[0, 0)` | Khoảng rỗng tại đầu | Không thay đổi |
| `[n, n)` | Khoảng rỗng hợp lệ tại cuối | Không thay đổi |
| `[2, 1)` | from lớn hơn to | `IllegalArgumentException` |
| `[-1, 2)` | Chỉ số bắt đầu âm | `ArrayIndexOutOfBoundsException` |
| `[0, n + 1)` | Chỉ số kết thúc vượt giới hạn | `ArrayIndexOutOfBoundsException` |

Không dùng `array.length - 1` làm `toIndex` khi muốn bao gồm phần tử cuối: vì chỉ số kết thúc là **exclusive**, muốn sắp cả mảng thì `toIndex = array.length`.

### 3.2. Tính đúng số lượng phần tử của khoảng

Số phần tử trong khoảng hợp lệ là:

\[
\text{length of range} = \text{toIndex} - \text{fromIndex}
\]

Ví dụ từ chỉ số 2 đến trước chỉ số 6 có **4 phần tử**, không phải 5. Đổi từ chỉ số bắt đầu và số lượng phần tử:

~~~java
int from = 2;
int count = 3;
int to = from + count;
Arrays.sort(data, from, to);
~~~

Đây là đoạn có thể chạy khi đã có `data` với ít nhất 5 phần tử. Trước khi tính `from + count` từ dữ liệu không tin cậy, cần tránh tràn `int` và xác minh các giới hạn; quy tắc an toàn là `0 <= from <= data.length` và `0 <= count <= data.length - from`, sau đó mới tính `to`.

### 3.3. Sắp xếp khoảng có thay đổi các phần tử khác không?

Không. Nếu chỉ định khoảng hợp lệ, những vị trí ngoài `[from, to)` **không bị hoán vị hoặc ghi đè bởi phép sắp xếp khoảng**.

Điều này phù hợp khi mảng có header, sentinel, phần tử cố định hoặc nhiều phần cần giữ thứ tự riêng. Tuy nhiên, **toàn bộ mảng sau đó không nhất thiết được sắp tăng dần**; chỉ đoạn được chỉ định có thứ tự theo comparator.

Ví dụ: sau `Arrays.sort(data, 1, 5)`, giá trị `9` ở đầu vẫn lớn hơn giá trị `1` ngay sau nó. Không gọi `Arrays.binarySearch(data, target)` trên **toàn bộ** mảng rồi kỳ vọng kết quả đúng khi chỉ một đoạn được sắp. Nếu tìm kiếm trong đoạn đã sắp, dùng overload `Arrays.binarySearch(data, from, to, target)`.

## 4. Mảng object: thứ tự tự nhiên và Comparable

Mảng `String[]` có thể dùng overload không có comparator:

~~~java
String[] fruits = {"pear", "apple", "kiwi"};
Arrays.sort(fruits);

System.out.println(Arrays.toString(fruits));
// [apple, kiwi, pear]
~~~

Mảng object sắp theo thứ tự **tự nhiên** của phần tử, dựa vào `Comparable.compareTo`. Với `String`, thứ tự không tự nhiên là thứ tự từ điển tiếng Việt theo văn hóa địa phương; `String.compareTo` so theo đơn vị mã UTF-16. Nếu muốn thứ tự ngôn ngữ, phải chọn comparator thích hợp, có thể dùng `java.text.Collator` theo `Locale`.

Nếu class nghiệp vụ có thứ tự tự nhiên hợp lý, nó có thể triển khai `Comparable<T>`. Khi không có thứ tự tự nhiên phù hợp cho mọi ngữ cảnh, **đừng ép class triển khai Comparable chỉ để sắp xếp một màn hình**; dùng comparator tường minh sẽ dễ mở rộng hơn.

Ví dụ chữ ký:

~~~java
Arrays.sort(items);            // Các phần tử phải mutually comparable.
Arrays.sort(items, from, to);   // Cũng theo natural ordering.
~~~

Hai lời gọi là mẫu minh họa, không phải code độc lập.

### 4.1. Comparator chọn thứ tự nghiệp vụ

Ví dụ cần sắp task theo `priority`:

~~~java
Arrays.sort(tasks, Comparator.comparingInt(
        task -> task.priority));
~~~

Đây là mảnh mã với `tasks` là `Task[]` và class `Task` có field `priority`. `Comparator.comparingInt` tránh boxing giá trị `int` khi so sánh và dễ đọc.

Muốn giảm dần:

~~~java
Arrays.sort(tasks, Comparator.comparingInt(
        (Task task) -> task.priority).reversed());
~~~

Ở chương trình hoàn chỉnh phía dưới, `Task` có `id` và `priority`. Việc chỉ đảo comparator của priority **không tự nhiên tạo ra thứ tự phụ** giữa các task có cùng priority.

Nếu muốn thứ tự xác định giữa các phần tử có giá trị khóa giống nhau:

~~~java
Comparator<Task> byPriorityThenId =
        Comparator.comparingInt((Task t) -> t.priority)
                  .thenComparing(t -> t.id);

Arrays.sort(tasks, byPriorityThenId);
~~~

`thenComparing` dùng thêm khóa phụ khi kết quả so sánh ưu tiên bằng 0; phù hợp khi business logic cần danh sách ổn định **theo khóa phụ**, khác với việc chỉ dựa vào stability của sort.

### 4.2. Sắp xếp khoảng object với comparator

Overload:

~~~java
Arrays.sort(tasks, fromIndex, toIndex, comparator);
~~~

Ví dụ `tasks` ban đầu là `[A:2, B:1, C:2, D:1]`, sắp **[1, 4)** theo priority **giảm dần**:

~~~java
Arrays.sort(tasks, 1, 4,
        Comparator.comparingInt(
                (Task t) -> t.priority).reversed());
~~~

Kết quả là `[A:2, C:2, B:1, D:1]`. Phần tử ở index 0 vẫn là `A:2`. Trong đoạn được sắp, `C:2` đứng trước hai task priority 1. `B` và `D` có cùng priority, giữ thứ tự tương đối ban đầu do sắp object ổn định.

## 5. Stable sort và ý nghĩa với mảng object

`Arrays.sort(Object[])` và các overload dành cho object là **stable sort** theo hợp đồng Java: nếu comparator coi hai phần tử bằng nhau (`compare(a,b) == 0`), thứ tự tương đối của chúng không bị đảo chỉ do phép sort.

Ví dụ task nhập theo thứ tự:

~~~text
[A:2, B:1, C:2, D:1]
~~~

Sắp tăng dần theo priority:

~~~text
[B:1, D:1, A:2, C:2]
~~~

Nhóm priority 1 vẫn `B` trước `D`; nhóm priority 2 vẫn `A` trước `C`. Đây là lợi ích quan trọng khi dữ liệu có **khóa sort bằng nhau** nhưng vẫn muốn bảo toàn thứ tự xuất hiện.

Cần phân biệt:

- **Stable:** với các phần tử comparator xem bằng nhau, giữ đúng thứ tự tương đối ban đầu.
- **Deterministic theo khóa phụ:** định nghĩa thêm `thenComparing(...)` để áp dụng một thứ tự rõ ràng ngay cả khi đầu vào có thứ tự khác.
- **Distinct:** loại phần tử trùng. `Arrays.sort` không thực hiện điều này.
- **Không thay đổi mảng:** không. Stable sort vẫn có thể hoán đổi vị trí các phần tử khác khóa; chỉ bảo toàn thứ tự tương đối trong nhóm bằng nhau.

Với mảng primitive, **không có object identity** để quan sát hai giá trị giống nhau theo cách tương tự. Không viết logic dựa vào stability của thuật toán sắp primitive; API bảo đảm kết quả thứ tự giá trị, còn thuật toán triển khai có thể khác theo JDK.

## 6. Comparator đúng hợp đồng để tránh kết quả sai

`Comparator` phải có thứ tự nhất quán. Với một comparator chuẩn, dấu của kết quả so sánh cho biết phần tử thứ nhất nhỏ hơn, bằng hay lớn hơn phần tử thứ hai; quan hệ này phải có tính đối xứng dấu và bắc cầu phù hợp.

### 6.1. Không trừ số nguyên để so sánh

Phản ví dụ:

~~~java
Comparator<Task> wrong = (a, b) ->
        a.priority - b.priority;
~~~

Đây là mảnh mã minh họa, dễ gây **tràn `int`** nếu hai giá trị rất lớn và rất nhỏ, khiến comparator trả dấu không đúng.

Ưu tiên:

~~~java
Comparator<Task> correct = Comparator.comparingInt(
        task -> task.priority);
~~~

Hoặc `Integer.compare(a.priority, b.priority)` khi viết lambda thủ công. Với `long` dùng `Long.compare` hoặc `Comparator.comparingLong`; với `double` dùng `Double.compare` hoặc `comparingDouble` để xử lý NaN/zero đúng theo API.

### 6.2. Null của object array phải có chính sách

`Arrays.sort(objects)` theo natural order thông thường **không tự chấp nhận null** như một phần tử có thứ tự. Nếu phần tử null xuất hiện mà comparator không xử lý, phép so sánh có thể ném `NullPointerException`.

Muốn đưa null lên đầu hoặc xuống cuối bằng comparator:

~~~java
Integer[] boxed = {null, 3, 1, null, 2};

Arrays.sort(boxed,
        Comparator.nullsLast(Comparator.naturalOrder()));

// [1, 2, 3, null, null]
~~~

Đây là đoạn trong một phương thức với import `java.util.*;`. `nullsFirst` và `nullsLast` là API Comparator từ Java 8, vẫn hợp lệ.

Với một mảng object có thể chứa null, nên **quyết định rõ null là giá trị hợp lệ hay lỗi**. Nếu null nghĩa dữ liệu không hoàn chỉnh, đôi khi phải reject trước khi sort thay vì âm thầm đẩy null về cuối.

### 6.3. Comparator vi phạm hợp đồng

Comparator không bắc cầu, phụ thuộc vào trạng thái đang thay đổi hoặc cho kết quả khác giữa các lần gọi có thể gây sắp xếp không ổn định, kết quả khó hiểu hoặc có thể gây `IllegalArgumentException` tùy implementation. Đừng bắt exception này rồi xem như một lỗi ngẫu nhiên của Arrays; cần sửa comparator hoặc xác định lại quy tắc nghiệp vụ.

Tránh comparator có side effect như đọc đồng hồ, tăng counter dùng làm thứ tự, gọi random hoặc mutate chính dữ liệu đang sort. Lambda comparator nên là hàm nhất quán trong một lần sort.

## 7. Giá trị float/double đặc biệt

`Arrays.sort(float[])` và `Arrays.sort(double[])` có quy tắc thứ tự tổng tương đương với `Float.compareTo`/`Double.compareTo`, thay vì chỉ dùng toán tử `<`:

- `-Infinity` đứng trước mọi giá trị hữu hạn.
- `-0.0` được coi là **nhỏ hơn `+0.0`** dù phép `==` cho true.
- `+Infinity` đứng sau mọi giá trị hữu hạn.
- `NaN` đứng **sau +Infinity**. Các NaN được coi bằng nhau cho mục đích thứ tự của phép sort.

Ví dụ:

~~~java
double[] values = {
        Double.NaN, 1.0, -0.0, +0.0,
        Double.NEGATIVE_INFINITY,
        Double.POSITIVE_INFINITY, Double.NaN
};

Arrays.sort(values);

System.out.println(Arrays.toString(values));
// [-Infinity, -0.0, 0.0, 1.0, Infinity, NaN, NaN]
~~~

Đoạn mã đặt trong phương thức. **NaN không phải null** và `Double.NaN == Double.NaN` là false, nhưng hợp đồng thứ tự của `Arrays.sort(double[])` xử lý NaN nhất quán. Không tự viết comparator dựa vào `a < b ? -1 : (a > b ? 1 : 0)` cho double, vì nó không phân biệt đúng NaN và zero có dấu.

Nếu lĩnh vực nghiệp vụ yêu cầu tất cả số phải hữu hạn, nên kiểm dữ liệu và từ chối NaN/Infinity trước khi sort; Arrays.sort không tự biết quy tắc chất lượng dữ liệu của ứng dụng.

## 8. Sort là in-place: muốn giữ dữ liệu gốc thì sao?

`Arrays.sort` sắp xếp **mảng đang truyền vào**. Nó không trả mảng mới và không yêu cầu người dùng gán lại:

~~~java
int[] source = {4, 1, 3};
Arrays.sort(source); // source giờ thành [1, 3, 4].
~~~

Nếu mã khác cũng tham chiếu cùng mảng, nó thấy dữ liệu đã đổi. Khi cần giữ nguyên:

~~~java
int[] original = {4, 1, 3};
int[] sorted = Arrays.copyOf(original, original.length);
Arrays.sort(sorted);

System.out.println(Arrays.toString(original)); // [4, 1, 3]
System.out.println(Arrays.toString(sorted));   // [1, 3, 4]
~~~

Đây là mảnh mã chạy được khi import Arrays. Có thể dùng `original.clone()` để tạo bản sao mảng một chiều.

**Sao chép mảng object là shallow copy:** `Task[] copied = tasks.clone()` tạo một mảng chứa các tham chiếu mới về mặt mảng, nhưng **không clone từng object Task**. Sort trên `copied` không thay vị trí trong `tasks`, nhưng sửa nội dung của một Task dùng chung vẫn ảnh hưởng cả hai mảng. Cần deep copy nếu nghiệp vụ yêu cầu object độc lập.

### 8.1. Muốn chỉ lấy đoạn đã sắp thành mảng mới

~~~java
int[] original = {9, 7, 4, 1, 8, 2};
int[] section = Arrays.copyOfRange(original, 1, 5);
Arrays.sort(section);

// original: [9, 7, 4, 1, 8, 2]
// section:  [1, 4, 7, 8]
~~~

`Arrays.copyOfRange` có khoảng `[from, to)`, nhưng **khác `sort` ở xử lý cận vượt cuối**: với `to` lớn hơn chiều dài mảng, `copyOfRange` có thể tạo đoạn dài hơn và **điền giá trị mặc định** cho phần vượt (tùy loại mảng), còn `Arrays.sort(a, from, to)` từ chối `toIndex > a.length`. Đừng coi hai API này là có cùng hợp đồng kiểm tra cận.

## 9. Khi nào dùng Arrays.parallelSort?

`Arrays.parallelSort(...)` có từ Java 8 và vẫn được hỗ trợ. Có cả các overload toàn mảng, một khoảng và object Comparator tương ứng. Nó dùng thuật toán song song thích hợp với phần tử primitive/object và có thể tận dụng các tác vụ trên `ForkJoinPool.commonPool()` tùy kích thước dữ liệu và môi trường.

Ví dụ:

~~~java
int[] data = {6, 3, 5, 1, 4, 2};
Arrays.parallelSort(data, 1, 5);

System.out.println(Arrays.toString(data));
// [6, 1, 3, 4, 5, 2]
~~~

Đây là đoạn trong một phương thức. Vẫn là **khoảng nửa mở**, vẫn sửa **mảng ban đầu**, vẫn chỉ sắp vùng [1,5).

Khi chọn `sort` hoặc `parallelSort`:

- Với mảng nhỏ, `Arrays.sort` thường đủ đơn giản và overhead thấp. Không giả định parallel luôn nhanh.
- Với mảng lớn, workload và CPU phù hợp, `parallelSort` có thể có lợi, nhưng cần benchmark bằng công cụ như JMH, không dùng một lần chạy thủ công.
- Cả hai đều cho kết quả đúng theo hợp đồng thứ tự. Các overload sort cho **mảng object** có bảo đảm **stable**; không phụ thuộc vào việc cùng một thuật toán nội bộ được dùng qua mọi JDK.
- `parallelSort` có thể dùng bộ nhớ đệm và các task bên ngoài; nên cân nhắc áp lực bộ nhớ và sự cạnh tranh với công việc khác trong common pool.
- Đừng để thread khác mutate mảng đang sort rồi mong có kết quả đáng tin; sort song song **không tạo đồng bộ nghiệp vụ** cho một mảng mutable được nhiều luồng chia sẻ.

Đối với một mảng object có Comparator không nhất quán hoặc có side effect, chạy parallel có thể làm vấn đề càng khó chẩn đoán. Comparator nên thuần và có thứ tự ổn định.

## 10. Sắp xếp rồi tìm kiếm hoặc xử lý tiếp

Một use case phổ biến là sort để chuẩn bị cho `Arrays.binarySearch`:

~~~java
int[] sorted = {9, 1, 5, 3};
Arrays.sort(sorted);
int index = Arrays.binarySearch(sorted, 5); // 2
~~~

Chỉ nên gọi overload `binarySearch(array, key)` trên **toàn bộ mảng đã được sắp** theo đúng thứ tự và comparator phù hợp. Nếu chỉ sắp một đoạn:

~~~java
int[] partial = {9, 7, 4, 1, 8, 2};
Arrays.sort(partial, 1, 5);            // [9, 1, 4, 7, 8, 2]
int index = Arrays.binarySearch(partial, 1, 5, 4); // 2
~~~

Đoạn `binarySearch` cũng dùng khoảng `[from, to)`. Không tìm trên toàn mảng `partial` đã sắp một đoạn mà đòi kết quả đúng, vì phần tử ngoài đoạn có thể phá thứ tự toàn cục.

Với object comparator, hãy dùng đúng comparator cho cả sort và search:

~~~java
Comparator<Task> comparator =
        Comparator.comparingInt(task -> task.priority);

Arrays.sort(tasks, comparator);
// Arrays.binarySearch(tasks, desiredTask, comparator);
~~~

Mảnh mã minh họa: `desiredTask` là đối tượng có khóa tương thích, và kết quả nếu có **nhiều phần tử so sánh bằng nhau** có thể là một vị trí trong nhóm bằng nhau, không phải nhất thiết phần tử đầu tiên. Nếu cần đầu tiên/cuối cùng của nhóm, áp dụng thuật toán tìm biên theo comparator.

### 10.1. Arrays.sort và Stream.sorted khác thế nào?

~~~java
int[] source = {3, 1, 2};

int[] copiedSorted = Arrays.stream(source)
        .sorted()
        .toArray();
// source chưa đổi; copiedSorted là [1, 2, 3].
~~~

`Arrays.stream(source).sorted().toArray()` tạo một mảng kết quả cho Stream pipeline mà không sort `source` tại chỗ. Nhưng nó có overhead khác với `Arrays.sort` và tùy bài toán cần truyền thêm dữ liệu. Không nên chọn Stream chỉ vì nghĩ rằng `Arrays.sort` đã lỗi thời; cả hai là API hiện hành, phục vụ mục tiêu khác nhau.

## 11. Chương trình Java độc lập, có stdout kiểm chứng

Tạo file **`ArraySortDemo.java`** dưới đây. Chương trình minh họa:

1. Sắp toàn mảng primitive.
2. Sắp một khoảng và khoảng rỗng.
3. Sắp mảng `String[]`.
4. Stability khi sort object cùng priority.
5. Comparator giảm dần trên **một khoảng object**.
6. Null của mảng `Integer[]`.
7. NaN, hai zero có dấu và infinity của `double[]`.
8. Sort bản sao, giữ nguyên mảng nguồn.
9. `parallelSort` trên một khoảng.
10. `binarySearch` và hai kiểu lỗi chỉ số.

Chương trình sử dụng cú pháp và API chạy được trên **JDK 17+**, không cần thư viện ngoài JDK; riêng các phương thức `Arrays.sort`, `parallelSort`, `Comparator` được dùng cũng phù hợp với những hệ thống Java hiện hành.

~~~java
import java.util.Arrays;
import java.util.Comparator;

public class ArraySortDemo {
    static final class Task {
        final String id;
        final int priority;

        Task(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }

        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    static Task[] tasks() {
        return new Task[]{
                new Task("A", 2), new Task("B", 1),
                new Task("C", 2), new Task("D", 1)
        };
    }

    public static void main(String[] args) {
        int[] whole = {9, 1, 5, 3};
        Arrays.sort(whole);
        System.out.println("Whole: " + Arrays.toString(whole));

        int[] range = {9, 7, 4, 1, 8, 2};
        Arrays.sort(range, 1, 5);
        System.out.println("Range [1,5): " + Arrays.toString(range));
        Arrays.sort(range, 3, 3);
        System.out.println("Empty range: " + Arrays.toString(range));

        String[] words = {"pear", "apple", "kiwi"};
        Arrays.sort(words);
        System.out.println("Words: " + Arrays.toString(words));

        Task[] stable = tasks();
        Arrays.sort(stable,
                Comparator.comparingInt(t -> t.priority));
        System.out.println("Stable: " + Arrays.toString(stable));

        Task[] partialObjects = tasks();
        Arrays.sort(partialObjects, 1, 4,
                Comparator.comparingInt(
                        (Task t) -> t.priority).reversed());
        System.out.println("Objects range: "
                + Arrays.toString(partialObjects));

        Integer[] nullable = {null, 3, 1, null, 2};
        Arrays.sort(nullable,
                Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("Nulls last: "
                + Arrays.toString(nullable));

        double[] floats = {
                Double.NaN, 1.0, -0.0, +0.0,
                Double.NEGATIVE_INFINITY,
                Double.POSITIVE_INFINITY, Double.NaN
        };
        Arrays.sort(floats);
        System.out.println("Double: "
                + Arrays.toString(floats));

        int[] original = {4, 1, 3};
        int[] copy = Arrays.copyOf(original, original.length);
        Arrays.sort(copy);
        System.out.println("Original: "
                + Arrays.toString(original));
        System.out.println("Sorted copy: "
                + Arrays.toString(copy));

        int[] parallel = {6, 3, 5, 1, 4, 2};
        Arrays.parallelSort(parallel, 1, 5);
        System.out.println("Parallel range: "
                + Arrays.toString(parallel));

        System.out.println("Search 5 in whole: "
                + Arrays.binarySearch(whole, 5));
        try {
            Arrays.sort(whole, 3, 2);
        } catch (IllegalArgumentException expected) {
            System.out.println("Reversed range rejected");
        }
        try {
            Arrays.sort(whole, -1, 2);
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println("Negative index rejected");
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ArraySortDemo.java
java ArraySortDemo
~~~

Stdout đã xác minh:

~~~text
Whole: [1, 3, 5, 9]
Range [1,5): [9, 1, 4, 7, 8, 2]
Empty range: [9, 1, 4, 7, 8, 2]
Words: [apple, kiwi, pear]
Stable: [B:1, D:1, A:2, C:2]
Objects range: [A:2, C:2, B:1, D:1]
Nulls last: [1, 2, 3, null, null]
Double: [-Infinity, -0.0, 0.0, 1.0, Infinity, NaN, NaN]
Original: [4, 1, 3]
Sorted copy: [1, 3, 4]
Parallel range: [6, 1, 3, 4, 5, 2]
Search 5 in whole: 2
Reversed range rejected
Negative index rejected
~~~

Kết quả `Range [1,5)` giữ `9` và `2` ở hai đầu; kết quả `Objects range` giữ `A:2` tại index 0 và sắp đoạn còn lại theo priority giảm dần. Dòng `Stable` thể hiện `B` đứng trước `D` trong nhóm priority 1 và `A` trước `C` trong nhóm priority 2. Dòng `Nulls last` là kết quả của **Comparator rõ ràng**, không phải do Arrays.sort tự biết nên đặt null cuối.

Khi chạy code, hai lời gọi cuối cố tình truyền chỉ số sai và bắt đúng loại exception để giải thích hợp đồng. Không dùng việc bắt mọi `RuntimeException` để che lỗi range từ người dùng; thông thường cần validate chỉ số trước khi gọi.

## 12. Kiểm tra tính đúng và các tình huống biên

Một bộ kiểm thử hữu ích cần kiểm cả **nội dung sau sắp** lẫn **dữ liệu nằm ngoài khoảng**:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Mảng rỗng | Sort thành công, vẫn rỗng |
| Mảng một phần tử | Không thay đổi |
| Mảng đã có thứ tự | Kết quả giữ thứ tự |
| Mảng ngược thứ tự | Thành thứ tự tăng/giảm đúng theo comparator |
| Có giá trị trùng | Giữ đúng số lần xuất hiện |
| Có số âm hoặc min/max primitive | Không dùng comparator trừ có thể tràn |
| Sort khoảng `[from,to)` | Bên ngoài đoạn không đổi, trong đoạn có thứ tự |
| `from == to` | Khoảng rỗng hợp lệ, mảng không đổi |
| `from > to` | `IllegalArgumentException` |
| `from < 0` hoặc `to > length` | `ArrayIndexOutOfBoundsException` |
| Object có nhiều phần tử cùng khóa | Giữ thứ tự tương đối khi dùng stable sort |
| Object có phần tử null | Xử lý qua `nullsFirst`/`nullsLast` hoặc từ chối theo hợp đồng |
| Double gồm NaN, zero có dấu, infinity | Thứ tự tổng của `Arrays.sort(double[])` đúng |
| Sắp bản sao | Mảng ban đầu không đổi |
| Chỉ một đoạn được sắp rồi binarySearch | Tìm trong **đúng đoạn đã sắp** |
| Dùng parallelSort thay sort | Kết quả thứ tự đúng; không phụ thuộc tốc độ hoặc scheduling |

### 12.1. Bất biến để kiểm thử tự động

Với `int[]` sau sắp tăng dần, có thể kiểm mọi cặp liền kề:

~~~java
for (int i = 1; i < numbers.length; i++) {
    if (numbers[i - 1] > numbers[i]) {
        throw new AssertionError("Not sorted at " + i);
    }
}
~~~

Đây là đoạn mã giả sử có `numbers` kiểu `int[]`. Với một đoạn `[from, to)`, bắt đầu vòng lặp ở `from + 1` và dừng trước `to`. Ngoài ra phải kiểm **tập đa giá trị** (multiset) phần tử không thay đổi: sort được quyền hoán vị nhưng không được tự đánh mất hoặc tạo phần tử.

Với object, kiểm dấu của comparator:

~~~java
for (int i = from + 1; i < to; i++) {
    if (comparator.compare(items[i - 1], items[i]) > 0) {
        throw new AssertionError("Object range not sorted");
    }
}
~~~

Đoạn này cần `items` là `T[]`, `comparator` hợp lệ và `from/to` là cận đúng. Nếu test stability, ngoài việc kiểm có thứ tự phải gắn một ID/thứ tự ban đầu cho các phần tử có khóa bằng nhau và xác minh không bị đảo thứ tự tương đối.

### 12.2. Các phép kiểm nên tránh

- So sánh array trực tiếp bằng `arrayA == arrayB` để kiểm nội dung. Với mảng, `==` kiểm **tham chiếu**, không kiểm từng phần tử. Dùng `Arrays.equals(a,b)` cho mảng một chiều hoặc `Arrays.deepEquals` cho mảng object lồng nhau khi phù hợp.
- Test rằng sort primitive luôn dùng đúng một thuật toán nội bộ cụ thể. Chi tiết thực thi có thể thay đổi; API chỉ cần đáp ứng hợp đồng.
- Test rằng `parallelSort` chắc chắn nhanh hơn. Hiệu năng phải đo trên dữ liệu và môi trường thật.
- Test rằng mọi object sau sort đều có ID tăng nếu comparator **chỉ so priority**. Comparator không biết ID nếu bạn không chỉ định `thenComparing`.
- Test thứ tự văn bản theo chuẩn tiếng Việt bằng `String.compareTo` nếu yêu cầu thực tế là collation theo locale.

## 13. Lỗi phổ biến và cách sửa

**Lỗi 1 — Hiểu toIndex là inclusive.** `Arrays.sort(a, 2, 5)` chỉ sắp các vị trí 2,3,4. Muốn bao gồm vị trí 5 phải dùng `toIndex=6` nếu mảng đủ dài.

**Lỗi 2 — Dùng `array.length - 1` làm cận cuối để sort toàn mảng.** Phần tử cuối sẽ nằm ngoài khoảng. Dùng `array.length`.

**Lỗi 3 — Nhầm sort trả mảng mới.** `Arrays.sort(a)` trả `void` và sửa `a`. Khi cần dữ liệu gốc, sao chép trước.

**Lỗi 4 — Sắp cả mảng trong khi chỉ được sửa một đoạn.** Dùng overload nhận `fromIndex/toIndex` và kiểm phần tử ở ngoài khoảng.

**Lỗi 5 — Gọi `Arrays.sort(intArray, comparator)`.** Overload Comparator dành cho object array, không dành cho mảng primitive.

**Lỗi 6 — Cho rằng object sort không stable.** Các overload `Arrays.sort(Object[])` cam kết stable; phần tử comparator xem bằng nhau giữ thứ tự tương đối ban đầu. Nhưng không nhầm ổn định với khái niệm một khóa phụ có thứ tự.

**Lỗi 7 — Dùng `(a,b) -> a - b` trên các số nguyên lớn.** Có thể overflow, làm dấu so sánh sai. Dùng `Integer.compare`, `Long.compare` hoặc `Comparator.comparingInt`.

**Lỗi 8 — Không xử lý null trong object array.** Natural ordering/comparator không xử lý null có thể ném lỗi. Chọn `Comparator.nullsFirst/Last` hoặc reject đầu vào.

**Lỗi 9 — Giả định `Double.NaN` tuân theo toán tử so sánh thông thường.** Sort double có total order đặc biệt; test cả NaN/Infinity và zero có dấu.

**Lỗi 10 — Chỉ sắp một đoạn nhưng binarySearch trên toàn mảng.** Yêu cầu tiền điều kiện đã sắp của binarySearch bị vi phạm. Dùng overload tìm theo khoảng.

**Lỗi 11 — Cho rằng `parallelSort` luôn có lợi.** Parallel có overhead và dùng chung tài nguyên; cần benchmark bằng workload phù hợp.

**Lỗi 12 — Viết code mutate mảng trong thread khác khi đang sort.** Không có hợp đồng bảo đảm kết quả khi có can thiệp bất hợp lệ; cần chủ động đồng bộ, snapshot hoặc giao quyền sở hữu mảng rõ ràng.

## 14. Bài tập tự luyện

1. Cho `int[] a = {8, 5, 3, 9, 2, 1}`. Hãy dự đoán kết quả của `Arrays.sort(a, 1, 5)`. Những vị trí nào chắc chắn không đổi?
2. Với mảng dài 6, `Arrays.sort(a, 0, 6)` và `Arrays.sort(a, 0, 5)` khác nhau thế nào?
3. Cho `String[] names = {"Mai", "An", "Binh"}`. Viết hai cách sắp toàn mảng: thứ tự tự nhiên và theo độ dài chuỗi (nếu bằng độ dài thì theo chuỗi). 
4. Cho task có priority bằng nhau nhưng ID khác nhau. Tại sao sort stable không tự khiến ID tăng dần? Khi nào dùng `thenComparing`?
5. Viết một phép kiểm rằng sau `Arrays.sort(a, from, to)`, các vị trí ngoài khoảng giữ nguyên và phần bên trong không giảm.
6. Với `Integer[] values = {null, 5, 1}`, cách nào đặt null ở cuối một cách có chủ đích?
7. Cho `double[] d = {Double.NaN, -0.0, +0.0, 1.0}`, thứ tự sau sort là gì?
8. Khi cần trả cho caller một bản đã sắp nhưng không thay đổi `original`, dùng API nào và có giới hạn gì khi phần tử là object mutable?

**Gợi ý đáp án:**

1. Đoạn chỉ số 1 đến 4 là `[5,3,9,2]`, thành `[2,3,5,9]`; kết quả `[8,2,3,5,9,1]`, index 0 và 5 không đổi.
2. Khoảng `[0,6)` bao gồm toàn mảng; `[0,5)` bỏ index 5.
3. `Arrays.sort(names)` và `Arrays.sort(names, Comparator.comparingInt(String::length).thenComparing(Comparator.naturalOrder()))`.
4. Stability chỉ giữ thứ tự gốc của các phần tử có cùng priority; muốn theo ID cần quy tắc thứ tự phụ rõ ràng.
5. Sao chép bản trước, so sánh từng index ngoài khoảng và duyệt cặp liền kề trong khoảng.
6. `Arrays.sort(values, Comparator.nullsLast(Comparator.naturalOrder()))`.
7. `[-0.0, 0.0, 1.0, NaN]`.
8. Dùng `clone()`/`Arrays.copyOf` rồi sort bản mới; với mảng object, bản sao là shallow copy, các object bên trong vẫn được dùng chung.

## Ghi nhớ

- **Toàn mảng:** `Arrays.sort(a)`.
- **Một khoảng:** `Arrays.sort(a, fromIndex, toIndex)` sắp **`fromIndex` inclusive đến `toIndex` exclusive** và giữ các phần tử ngoài khoảng.
- **Object tùy thứ tự:** `Arrays.sort(a, comparator)` và overload có cận; các phép sort object **stable**.
- **Thay đổi tại chỗ:** `sort` trả `void`, mảng gốc được hoán vị; sao chép nếu cần giữ nguyên.
- **Đúng comparator:** dùng `comparingInt`/`Integer.compare`, xử lý null có chủ đích, không viết comparator trừ có thể tràn.
- **Kiểm biên và dữ liệu:** từ lớn hơn đến, chỉ số âm, vượt chiều dài, NaN, zero có dấu và mảng trống đều cần test.
- **Parallel không phải luôn nhanh:** `Arrays.parallelSort` vẫn có toàn mảng/khoảng nhưng phải đo hiệu năng trước khi chọn.

### Nguồn tham khảo chính thức, API hiện hành

- [Oracle Java SE 26 — Arrays.sort, Arrays.parallelSort, Arrays.binarySearch và Arrays.copyOfRange](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [Oracle Java SE 26 — Comparator, nullsFirst/nullsLast, comparingInt, thenComparing](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 26 — Comparable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Comparable.html)
- [Oracle Java SE 26 — String.compareTo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
- [Oracle Java SE 26 — Collator (so sánh văn bản theo Locale)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html)
