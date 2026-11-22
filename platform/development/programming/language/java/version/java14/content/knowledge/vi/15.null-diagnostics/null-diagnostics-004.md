# Chẩn đoán null khi truy cập phần tử mảng, lấy độ dài mảng và unboxing

## 1. Mục tiêu của bài học

Khi thấy `NullPointerException` (NPE) trong Java, nhiều người chỉ tìm một biến có giá trị `null` gần dòng lỗi. Cách đó chưa đủ, đặc biệt khi trên cùng dòng có **nhiều thao tác**: truy cập một phần tử mảng, truy cập mảng con, lấy `length` hoặc chuyển `Integer` thành `int`. Một thông báo lỗi hữu ích phải trả lời **thao tác nào thất bại** và **biểu thức nào có giá trị `null`**.

Bài này tập trung vào ba nhóm thao tác:

- **Đọc/ghi phần tử mảng:** `numbers[index]` hoặc `numbers[index] = value` khi tham chiếu `numbers` là `null`.
- **Đọc độ dài mảng:** `numbers.length` khi `numbers` là `null`.
- **Unboxing:** chuyển một wrapper như `Integer`, `Long` hoặc `Boolean` sang kiểu nguyên thủy tương ứng khi chính wrapper đang là `null`; kể cả trường hợp wrapper nằm trong mảng.

Bài cũng chỉ rõ cách đọc **Helpful NullPointerExceptions** do JVM tạo theo **JEP 358**, cách phân biệt null ở mảng với null ở phần tử, và cách ngăn lỗi từ thiết kế dữ liệu.

### Phiên bản hiện hành

Tính năng **Helpful NullPointerExceptions** được giới thiệu trong **Java 14 (JEP 358)**. Ở Java 14, thông báo chi tiết cần bật bằng tùy chọn `-XX:+ShowCodeDetailsInExceptionMessages`; từ **Java 15**, HotSpot bật tính năng này mặc định trong cấu hình thông thường. Đây vẫn là cơ chế hữu ích trên các bản Java hiện đại.

Ví dụ chính dùng **Java 17+**, không cần tính năng preview, và chỉ rõ tùy chọn JVM để thông báo có chi tiết khi dùng HotSpot. **Nội dung văn bản của thông báo NPE không phải hợp đồng API bất biến**: nó có thể khác giữa JVM, bản JDK, tùy chọn debug và cách biên dịch. Học **cơ chế và mẫu chẩn đoán**, không viết nghiệp vụ dựa vào chuỗi thông báo chính xác.

## 2. Phân biệt các trạng thái trước khi chẩn đoán

Các ví dụ sau có vẻ giống nhau nhưng hành vi rất khác:

| Giá trị | Ví dụ | Khi dùng `[0]` hoặc `length` |
| --- | --- | --- |
| **Mảng null** | `int[] a = null;` | `a[0]` và `a.length` gây NPE |
| **Mảng rỗng nhưng không null** | `int[] a = new int[0];` | `a.length == 0`; `a[0]` gây `ArrayIndexOutOfBoundsException` |
| **Mảng nguyên thủy có phần tử mặc định** | `int[] a = new int[1];` | `a[0] == 0`; phần tử `int` **không thể là null** |
| **Mảng wrapper có phần tử null** | `Integer[] a = {null};` | `a.length == 1`; đọc `a[0]` dưới dạng `Integer` hợp lệ, nhưng **unbox** nó sang `int` gây NPE |
| **Mảng tham chiếu có phần tử null** | `String[] a = {null};` | `a[0]` trả `null`; chỉ khi **dùng giá trị đó như một đối tượng**, ví dụ `a[0].length()`, mới phát sinh NPE |

**Không được kết luận:** “Cứ thấy `arr[0]` và NPE là chắc chắn `arr` null”. Với mảng `Integer[]`, `arr` có thể hoàn toàn hợp lệ nhưng chính `arr[0]` là null và lỗi chỉ phát sinh trong bước unboxing.

~~~java
Integer[] boxed = {null}; // Bản thân mảng có một phần tử.
Integer ref = boxed[0];   // Hợp lệ: ref nhận null.
// int number = boxed[0]; // Nếu bỏ comment: unboxing null sẽ ném NPE.
~~~

Đoạn trên là **mã minh họa**, cần đặt bên trong một phương thức hoặc khối Java phù hợp.

## 3. Cấu trúc thông báo Helpful NPE

Với JVM HotSpot hỗ trợ và đã bật chế độ chi tiết, thông báo NPE do JVM tạo thường có cấu trúc:

~~~text
Cannot <thao tác> because "<biểu thức>" is null
~~~

Nó có hai phần:

1. **Thao tác thất bại** — ví dụ `Cannot load from int array`, `Cannot read the array length` hoặc `Cannot invoke "java.lang.Integer.intValue()"`.
2. **Nguyên nhân gần nhất** — ví dụ `because "values" is null`, `because "grid[0]" is null` hoặc `because "boxed[0]" is null`.

JVM phân tích vị trí bytecode nơi null được sử dụng, rồi truy ngược trong khả năng cho phép để mô tả biểu thức đã tạo ra tham chiếu null. **Thông báo không phải một công cụ chứng minh nguồn gốc dữ liệu null trong toàn hệ thống**: nó cho biết biểu thức tại điểm lỗi, không cho biết dữ liệu bị bỏ sót từ HTTP request, database hay mapper nào trước đó.

### 3.1. Bảng nhận dạng nhanh

| Hoạt động tại bytecode / biểu thức | Tiền tố thông báo thường thấy | Điều bị null |
| --- | --- | --- |
| Đọc `int[]` bằng `arr[i]` | `Cannot load from int array` | Tham chiếu tới mảng `int[]` |
| Ghi `int[]` bằng `arr[i] = n` | `Cannot store to int array` | Tham chiếu tới mảng `int[]` |
| Đọc `String[]` hoặc `Integer[]` bằng `arr[i]` | `Cannot load from object array` | Tham chiếu tới mảng kiểu tham chiếu |
| Ghi mảng kiểu tham chiếu | `Cannot store to object array` | Tham chiếu tới mảng kiểu tham chiếu |
| Truy cập `arr.length` | `Cannot read the array length` | Tham chiếu tới mảng, chưa thể đọc độ dài |
| Unboxing `Integer` | `Cannot invoke "java.lang.Integer.intValue()"` | Một đối tượng `Integer` cần chuyển sang `int` |
| Unboxing `Boolean` | `Cannot invoke "java.lang.Boolean.booleanValue()"` | Một đối tượng `Boolean` cần chuyển sang `boolean` |
| Unboxing `Long` | `Cannot invoke "java.lang.Long.longValue()"` | Một đối tượng `Long` cần chuyển sang `long` |

Đây là những **mẫu thông báo** của HotSpot khi đủ dữ liệu chẩn đoán, không phải cam kết mọi bản JVM đều trả về đúng câu chữ. Loại mảng và kiểu wrapper giúp bạn suy ra **bước nào đã xảy ra**, nhưng cần đọc tiếp phần `because ... is null` để biết vị trí cụ thể.

## 4. Truy cập phần tử mảng: đọc và ghi

### 4.1. Đọc từ tham chiếu mảng null

~~~java
static int readFirst() {
    int[] values = null;
    return values[0];
}
~~~

Với HotSpot, biên dịch có thông tin tên biến và bật thông báo chi tiết, lỗi có thể là:

~~~text
Cannot load from int array because "values" is null
~~~

Khi thực hiện `values[0]`, JVM cần một mảng `int[]` thật. Tham chiếu `values` là null nên không thể tải phần tử.

**Chú ý:** Đây là **NPE do mảng null**, không phải lỗi chỉ số. Kể cả chỉ số bằng `0`, `-1` hoặc lớn, nếu tham chiếu mảng null thì vấn đề đầu tiên cần chẩn đoán là không có mảng để truy cập. Biểu thức chỉ số vẫn có các quy tắc đánh giá riêng theo JLS; không dùng NPE để suy luận rằng mọi biểu thức con khác chắc chắn không được chạy.

### 4.2. Ghi vào tham chiếu mảng null

~~~java
static void writeFirst() {
    int[] values = null;
    values[0] = 7;
}
~~~

Thông báo dạng:

~~~text
Cannot store to int array because "values" is null
~~~

Từ khóa `store` chỉ ra đây là một **phép gán vào vị trí mảng**, khác `load` của phép đọc. Lỗi không có nghĩa số `7` không hợp lệ; **đối tượng mảng đích không tồn tại**.

Với `String[]` hoặc `Integer[]`, các thông báo về đọc/ghi mảng có thể nói `object array` vì phần tử là tham chiếu, không phải kiểu nguyên thủy.

### 4.3. Trường hợp mảng không null nhưng chỉ số không hợp lệ

~~~java
int[] values = new int[0];
System.out.println(values.length); // 0
// System.out.println(values[0]);  // ArrayIndexOutOfBoundsException.
~~~

Đây là **mã minh họa**, cần đặt trong phương thức. `values.length` hợp lệ vì mảng có thật. `values[0]` lỗi do độ dài bằng `0`. Không nên “sửa NPE” bằng cách thay mảng null thành mảng rỗng rồi bỏ qua việc kiểm tra chỉ số: đó là **hai điều kiện riêng biệt**.

Đối với mảng có `n` phần tử, các chỉ số hợp lệ là từ `0` đến `n - 1`. Khi `n == 0`, không có chỉ số hợp lệ.

## 5. `array.length`: tham chiếu null khác độ dài bằng zero

Trong Java, `length` là một trường đặc biệt để đọc độ dài mảng, **không phải lời gọi method**. Cách viết đúng:

~~~java
int[] values = {10, 20, 30};
System.out.println(values.length); // 3
// values.length(); // Sai cú pháp Java: length không phải phương thức của array.
~~~

Nếu biến mảng là null:

~~~java
int[] values = null;
// int n = values.length; // Khi bỏ comment: NullPointerException.
~~~

Thông báo dạng:

~~~text
Cannot read the array length because "values" is null
~~~

Giải thích:
- `values == null`: chưa có đối tượng mảng; JVM không có độ dài để đọc → NPE.
- `values = new int[0]`: có đối tượng mảng hợp lệ với `length == 0`.
- `values = new int[3]`: có đối tượng mảng hợp lệ với `length == 3`, các phần tử mặc định bằng `0`.

**Sai lầm cần tránh:** Thấy NPE tại dòng `for (int i = 0; i < values.length; i++)` rồi chỉ sửa biến lặp `i`. Nếu thông báo là `Cannot read the array length`, cần truy đường gán của **`values`**. Chỉ sau khi mảng hợp lệ mới cần xem giới hạn chỉ số.

### 5.1. `String.length()` và `array.length` không giống nhau

~~~java
String text = null;
// text.length();     // NPE: cannot invoke String.length().
String[] words = null;
// int n = words.length; // NPE: cannot read the array length.
~~~

Cả hai là NPE nhưng hành động bytecode khác nhau. `String` là đối tượng có phương thức `length()`, còn mảng Java có trường đặc biệt `length`. Đọc phần **Cannot invoke** hay **Cannot read the array length** sẽ giúp phân biệt.

## 6. Mảng nhiều chiều: phần tử ở tầng nào null?

Mảng nhiều chiều trong Java được biểu diễn bằng **mảng của các mảng**. Điều đó có nghĩa mảng ngoài có thể không null nhưng một mảng con trong đó lại null:

~~~java
int[][] grid = new int[1][];
// grid != null và grid.length == 1.
// grid[0] == null, vì phần tử của mảng ngoài là tham chiếu chưa gán.
// int value = grid[0][0]; // NPE ở mảng con grid[0].
~~~

Thông báo dạng:

~~~text
Cannot load from int array because "grid[0]" is null
~~~

**Biểu thức null ở đây là `grid[0]`, không phải `grid`.** Mảng ngoài đã có thật và việc lấy phần tử tại chỉ số 0 là hợp lệ; phần tử đó đang là null nên không thể truy cập `[0]` tiếp theo.

Nếu làm:

~~~java
int[][] grid = new int[1][];
// int count = grid[0].length; // NPE ở array length của grid[0].
~~~

mẫu thông báo sẽ phản ánh **đọc độ dài mảng**, vì thao tác cuối cùng là `arraylength`, không phải tải một phần tử `int`.

### 6.1. Field chứa mảng cũng có thể null

~~~java
class Inventory {
    int[] counts;
    Inventory(int[] counts) { this.counts = counts; }
}

Inventory inventory = new Inventory(null);
// int first = inventory.counts[0]; // NPE: inventory.counts null.
~~~

Đoạn cuối là minh họa trong phương thức; `Inventory` là class có thể đặt cùng tệp nếu không `public`. Helpful NPE có thể báo:

~~~text
Cannot load from int array because "inventory.counts" is null
~~~

Nó chỉ đích danh **field `counts` thuộc `inventory`**. Nếu bản thân `inventory` là null, thao tác thất bại xảy ra **sớm hơn**, ngay khi đọc field `counts`, với thông báo liên quan `Cannot read field "counts"`. Vì thế, cần đọc **toàn bộ vế trái và vế phải của thông báo**, không chỉ thấy tên `counts` rồi kết luận.

## 7. Unboxing: tại sao một `Integer` null làm phép tính `int` ném NPE?

**Unboxing** là chuyển từ một wrapper reference sang giá trị kiểu nguyên thủy tương ứng, ví dụ `Integer` → `int`. Java có thể thực hiện việc này **ngầm định** ở nhiều ngữ cảnh mà không cần lập trình viên viết `intValue()`.

~~~java
Integer count = null;
// int number = count; // NPE lúc unboxing.
~~~

Về mặt hành vi, phép chuyển có tác dụng tương tự gọi `count.intValue()`. Nếu `count` là null, không thể gọi phương thức instance đó. Với HotSpot, thông báo thường là:

~~~text
Cannot invoke "java.lang.Integer.intValue()" because "count" is null
~~~

**Bẫy quan trọng:** Không hề có `.intValue()` trong dòng source, nhưng thông báo NPE lại nêu nó vì compiler tạo thao tác chuyển kiểu thích hợp.

### 7.1. Những ngữ cảnh unboxing dễ gặp

| Ví dụ | Vì sao có unboxing? | Khi wrapper null |
| --- | --- | --- |
| `Integer boxed = null; int x = boxed;` | Gán wrapper vào `int` | NPE |
| `Integer boxed = null; int x = boxed + 1;` | Toán tử cộng số yêu cầu giá trị nguyên thủy | NPE |
| `Long boxed = null; long x = boxed;` | `Long` → `long` | NPE |
| `Boolean flag = null; if (flag) { ... }` | Điều kiện `if` yêu cầu `boolean` | NPE |
| `Integer boxed = null; Integer copy = boxed;` | Chỉ sao chép tham chiếu, không unbox | **Không** có NPE tại phép gán |

Những dòng trên là **mã minh họa**, một số có biến trùng tên và không thể chép nối tiếp nguyên xi vào một phương thức. Muốn chạy từng trường hợp, đặt nó vào khối riêng.

**Không suy luận rằng mọi khi cầm một `Integer` null đều ném NPE.** NPE chỉ xuất hiện khi một thao tác cần giải tham chiếu hoặc chuyển nó sang primitive. Cất giữ, truyền đi trong ngữ cảnh reference, hoặc so sánh `boxed == null` là hợp lệ.

### 7.2. Phần tử `Integer[]` null và unboxing

~~~java
Integer[] boxed = {null};
Integer ref = boxed[0]; // Hợp lệ: trả null reference.
// int number = boxed[0]; // NPE: phần tử boxed[0] phải unbox.
~~~

Mẫu thông báo rất hữu ích:

~~~text
Cannot invoke "java.lang.Integer.intValue()" because "boxed[0]" is null
~~~

Cụm `boxed[0]` chỉ rõ **phần tử mảng** nào đang null. Bản thân mảng `boxed` không null, kích thước bằng `1`, chỉ số `0` hợp lệ, và phép **đọc reference** đã thành công. Lỗi chỉ xuất hiện khi Java cần một `int`.

### 7.3. Nếu cả mảng `Integer[]` null thì lỗi ở bước khác

~~~java
Integer[] boxed = null;
// int number = boxed[0]; // Trước unboxing đã phải đọc mảng.
~~~

Với HotSpot, thông báo dạng:

~~~text
Cannot load from object array because "boxed" is null
~~~

**Không phải** `Cannot invoke Integer.intValue()`: Java chưa lấy được phần tử `boxed[0]`, nên chưa tới bước unboxing. Đây là cách phân biệt hai nguyên nhân có cùng bề ngoài `int number = boxed[0]`.

### 7.4. Primitive array không có phần tử null

~~~java
int[] numbers = new int[1];
System.out.println(numbers[0]); // 0
~~~

`int[]` lưu trực tiếp primitive `int`; mỗi phần tử mặc định `0`. Nó không thể lưu một phần tử `null`. Nếu muốn diễn đạt giá trị chưa có, có thể cân nhắc `Integer[]` hoặc cấu trúc dữ liệu khác, nhưng khi chọn wrapper phải xử lý khả năng `null` trước khi unbox.

## 8. Chương trình Java 17+ chạy được: so sánh thông báo NPE thực tế

Chương trình sau tách từng biểu thức nguy hiểm thành một phương thức để **chỉ rõ bước làm phát sinh lỗi**. Mỗi lần gọi được bắt bằng `catch (NullPointerException)` nhằm trình bày thông báo rồi tiếp tục chạy các trường hợp khác. Đây là kỹ thuật **demo/test**, không phải đề xuất bắt và bỏ qua mọi NPE trong ứng dụng.

Lưu toàn bộ vào tệp **`HelpfulNpeArrayDemo.java`**:

~~~java
import java.util.function.Supplier;

public final class HelpfulNpeArrayDemo {
    static final class Inventory {
        int[] counts;

        Inventory(int[] counts) {
            this.counts = counts;
        }
    }

    private static void check(String label, Supplier<?> operation) {
        try {
            System.out.println(label + ": OK=" + operation.get());
        } catch (NullPointerException e) {
            System.out.println(label + ": " + e.getMessage());
        }
    }

    static int loadNullArray() {
        int[] values = null;
        return values[0];
    }

    static int storeNullArray() {
        int[] values = null;
        values[0] = 7;
        return 0;
    }

    static int lengthNullArray() {
        int[] values = null;
        return values.length;
    }

    static int loadNullRow() {
        int[][] grid = new int[1][];
        return grid[0][0];
    }

    static int loadNullField() {
        Inventory inventory = new Inventory(null);
        return inventory.counts[0];
    }

    static int unboxNullLocal() {
        Integer count = null;
        return count;
    }

    static int unboxNullSlot() {
        Integer[] boxed = {null};
        int result = boxed[0];
        return result;
    }

    static int loadNullWrapperArray() {
        Integer[] boxed = null;
        int result = boxed[0];
        return result;
    }

    public static void main(String[] args) {
        check("load", HelpfulNpeArrayDemo::loadNullArray);
        check("store", HelpfulNpeArrayDemo::storeNullArray);
        check("length", HelpfulNpeArrayDemo::lengthNullArray);
        check("nested", HelpfulNpeArrayDemo::loadNullRow);
        check("field", HelpfulNpeArrayDemo::loadNullField);
        check("unbox-local", HelpfulNpeArrayDemo::unboxNullLocal);
        check("unbox-slot", HelpfulNpeArrayDemo::unboxNullSlot);
        check("wrapper-array", HelpfulNpeArrayDemo::loadNullWrapperArray);

        check("null-slot-is-valid", () -> {
            String[] words = {null};
            return words[0] == null;
        });

        check("non-null-array-length", () -> new int[0].length);
    }
}
~~~

### 8.1. Biên dịch và chạy

Sử dụng **JDK 17 trở lên**, bản HotSpot có tùy chọn chi tiết:

~~~bash
javac -g -encoding UTF-8 --release 17 HelpfulNpeArrayDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeArrayDemo
~~~

Tùy chọn `-g` yêu cầu `javac` phát thêm thông tin debug, giúp JVM có cơ hội hiển thị tên biến cục bộ như `values`, `count` thay vì ký hiệu `<local1>`. `-XX:+ShowCodeDetailsInExceptionMessages` bật cơ chế Helpful NPE của HotSpot để các lần chạy dễ tái hiện kết quả.

**Stdout kiểm chứng với JDK hỗ trợ Helpful NPE và thông tin biến đầy đủ:**

~~~text
load: Cannot load from int array because "values" is null
store: Cannot store to int array because "values" is null
length: Cannot read the array length because "values" is null
nested: Cannot load from int array because "grid[0]" is null
field: Cannot load from int array because "inventory.counts" is null
unbox-local: Cannot invoke "java.lang.Integer.intValue()" because "count" is null
unbox-slot: Cannot invoke "java.lang.Integer.intValue()" because "boxed[0]" is null
wrapper-array: Cannot load from object array because "boxed" is null
null-slot-is-valid: OK=true
non-null-array-length: OK=0
~~~

**Lưu ý tái hiện:** Đó là stdout từ chương trình đã được biên dịch và chạy thực tế. Ở một JVM hoặc cách build khác, thông tin chi tiết trong `e.getMessage()` có thể thay đổi. Nếu không có `-g`, thay vì tên `values` bạn có thể thấy ký hiệu vị trí local; nếu tính năng bị tắt hoặc thiếu metadata, `getMessage()` thậm chí có thể trả `null`. Điều này **không làm thay đổi loại lỗi hay cơ chế ngôn ngữ**.

### 8.2. Giải thích 10 dòng output

1. **`load`:** `int[] values` null; JVM không thể đọc một `int` từ mảng.
2. **`store`:** `int[] values` null; JVM không thể gán giá trị `7` vào phần tử.
3. **`length`:** không có mảng để lấy độ dài.
4. **`nested`:** `grid` tồn tại, nhưng `grid[0]` là null; truy cập cấp thứ hai thất bại.
5. **`field`:** `inventory` tồn tại; field `inventory.counts` là null. Thông báo nêu đúng đường truy cập field.
6. **`unbox-local`:** `Integer count` null; compiler cần chuyển thành `int`, thao tác như `intValue()` thất bại.
7. **`unbox-slot`:** `boxed` tồn tại, nhưng phần tử `boxed[0]` null; lỗi xảy ra tại unboxing.
8. **`wrapper-array`:** chính `boxed` là mảng null; phép tải phần tử thất bại trước khi Java có thể unbox.
9. **`null-slot-is-valid`:** đọc phần tử `String[]` đang null **không tự gây NPE** nếu chỉ đem so sánh `== null`.
10. **`non-null-array-length`:** mảng rỗng vẫn tồn tại và `length == 0`.

Ba thông báo **`load`**, **`length`** và **`unbox-slot`** có mục đích chẩn đoán khác nhau. Hãy xác định chúng trước khi sửa code, vì cách khắc phục sẽ khác.

## 9. Đọc stack trace cùng thông báo, không chỉ đọc thông báo

Một lỗi không bắt (uncaught) có thể được JVM in theo dạng:

~~~text
Exception in thread "main" java.lang.NullPointerException:
    Cannot load from int array because "values" is null
    at HelpfulNpeArrayDemo.loadNullArray(HelpfulNpeArrayDemo.java:<line>)
    at HelpfulNpeArrayDemo.main(HelpfulNpeArrayDemo.java:<line>)
~~~

Đoạn trên là **sơ đồ minh họa**, không phải stdout của chương trình trong phần 8 (phần đó chủ động bắt NPE). `<line>` biểu thị số dòng thực tế trong file; vị trí phụ thuộc cách lưu và biên dịch mã.

Đọc theo thứ tự:
1. `NullPointerException`: loại exception.
2. `Cannot load from int array`: thao tác thất bại.
3. `because "values" is null`: biểu thức được xác định là null.
4. Dòng `at Class.method(File.java:line)` gần đầu stack trace: vị trí thực hiện thao tác; cần mở mã ở đó.
5. Các frame phía dưới: đường gọi dẫn tới đoạn code, hữu ích để truy về nơi dữ liệu bị đưa vào dưới dạng null.

Nếu thông báo trỏ tới `inventory.counts`, kiểm tra **nơi khởi tạo/cập nhật `counts`**. Nếu trỏ tới `grid[0]`, kiểm tra **nơi tạo và lấp đầy hàng 0**. Nếu trỏ tới `boxed[0]` tại `intValue()`, kiểm tra **chính phần tử 0** và yêu cầu nghiệp vụ về null.

### 9.1. Tên biến trong message có thể khác

Helpful NPE dựa trên bytecode và metadata có sẵn. Các lựa chọn build như `-g`/`-g:none`, biến đổi bytecode, compiler khác, JVM khác hay vị trí biểu thức phức tạp có thể ảnh hưởng **tên hiển thị**. Nếu không biết tên local, thông báo có thể dùng ký hiệu như `<local1>` hoặc `<parameter1>`.

**Không parse nội dung `getMessage()` để quyết định luồng nghiệp vụ.** Nó phục vụ con người và công cụ chẩn đoán, không phải một giao thức ổn định. Với logic ứng dụng, hãy kiểm tra dữ liệu và dùng loại exception/hợp đồng API rõ ràng.

### 9.2. NPE do JVM tạo và NPE do code ném khác nhau

~~~java
int[] data = null;
// int x = data.length; // NPE do JVM tạo khi thực hiện arraylength.

throw new NullPointerException("data must not be null");
~~~

Hai dòng trên là **minh họa độc lập**; phần truy cập array đã comment và dòng `throw` chỉ chạy khi được đặt trong method. Với `throw new NullPointerException("data must not be null")`, thông báo được lập trình viên chỉ định là `data must not be null`. Không nên mong JVM bổ sung `Cannot read the array length` cho một exception được ném tường minh theo cách này.

`Objects.requireNonNull(data, "data")` cũng ném NPE với lời nhắn được truyền vào. Đây là cơ chế **báo vi phạm hợp đồng đầu vào** chứ không phải cùng loại chẩn đoán bytecode của dereference.

## 10. Cách phòng tránh lỗi theo từng nguyên nhân

### 10.1. Nếu mảng không được phép null: từ chối ở ranh giới

~~~java
import java.util.Objects;

static int first(int[] values) {
    Objects.requireNonNull(values, "values");
    if (values.length == 0) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values[0];
}
~~~

Đây là **method minh họa** cần đặt trong một class. Nó tách rõ hai điều kiện:
- `values == null`: không thỏa hợp đồng; `Objects.requireNonNull` báo sớm với lời nhắn `values`.
- `values.length == 0`: mảng tồn tại nhưng không có phần tử 0; báo lỗi nghiệp vụ rõ ràng thay vì để `ArrayIndexOutOfBoundsException` phát sinh sau đó.

Điều này cải thiện chẩn đoán vì lỗi xảy ra **gần ranh giới nhận dữ liệu**, thay vì sau nhiều phép tính.

### 10.2. Nếu null là trạng thái hợp lệ: quy định rõ mặc định

~~~java
static int sizeOrZero(int[] values) {
    return values == null ? 0 : values.length;
}
~~~

Đây chỉ là thiết kế **khi null thực sự có nghĩa là “không có phần tử”**. Nếu null nghĩa là “lỗi dữ liệu chưa tải” thì trả `0` sẽ **che giấu lỗi**; nên báo lỗi sớm hoặc dùng một kiểu biểu diễn trạng thái rõ ràng hơn.

Một mảng rỗng `new int[0]` thường có thể dùng để biểu diễn “không có phần tử” mà không cần null. Tuy nhiên, không tự chuyển mọi null thành mảng rỗng khi hợp đồng ứng dụng còn phân biệt hai trạng thái.

### 10.3. Với mảng nhiều chiều: khởi tạo từng hàng hoặc kiểm tra hàng null

~~~java
int[][] grid = new int[2][];
grid[0] = new int[]{1, 2};
grid[1] = new int[0];
System.out.println(grid[0][0]);   // 1
System.out.println(grid[1].length); // 0
~~~

Mảng ngoài không đủ; mỗi hàng cần được khởi tạo nếu code sẽ truy cập hàng như một mảng. Với dữ liệu có hàng tùy chọn, hãy kiểm tra `grid[row] != null` trước khi dùng `grid[row][col]` hoặc `grid[row].length`.

### 10.4. Với wrapper và unboxing: xác định chính sách null

~~~java
Integer count = null;
int safeCount = count == null ? 0 : count.intValue();
~~~

Cách này chỉ đúng khi `0` là **giá trị mặc định được chấp nhận**. Có thể viết `Objects.requireNonNullElse(count, 0)` để chọn wrapper mặc định, rồi unbox, nhưng vẫn cần xem `0` có hợp ngữ nghĩa dữ liệu hay không.

Nếu null là lỗi, nên phát hiện tại nguồn:

~~~java
Integer count = null;
// int exact = Objects.requireNonNull(count, "count"); // NPE có ngữ cảnh rõ.
~~~

Các đoạn này là **mã minh họa**, cần import `java.util.Objects` cho ví dụ thứ hai.

### 10.5. Với `Integer[]`: kiểm tra cả mảng lẫn phần tử

~~~java
import java.util.Objects;

static int sum(Integer[] values) {
    Objects.requireNonNull(values, "values");
    int total = 0;
    for (int i = 0; i < values.length; i++) {
        Integer element = Objects.requireNonNull(
                values[i], "values[" + i + "]"
        );
        total = Math.addExact(total, element);
    }
    return total;
}
~~~

Đây là **method minh họa** trong một class. Nó phân biệt:
1. Bản thân `values` null: `Objects.requireNonNull(values, "values")` báo ngay.
2. Một `values[i]` null: thông báo chỉ chính xác chỉ số, ví dụ `values[3]`.
3. Mọi phần tử hợp lệ: `Math.addExact` cộng các giá trị và báo `ArithmeticException` nếu tràn `int`, tránh kết quả sai âm thầm.

Với mảng `int[]`, phần tử không thể là null nên không cần bước kiểm tra `Integer` riêng.

### 10.6. Không bắt NPE rồi tiếp tục với dữ liệu chưa xác minh

~~~java
// Không phải cách sửa tốt:
try {
    useData();
} catch (NullPointerException ignored) {
    // Im lặng bỏ qua lỗi, dữ liệu vẫn chưa hợp lệ.
}
~~~

Đây là **mã minh họa** và `useData()` giả định là phương thức ứng dụng. Việc bỏ qua NPE có thể che mất bug hoặc làm luồng xử lý tiếp tục trong trạng thái không nhất quán. Cách đúng thông thường là **xác định contract của dữ liệu null**, kiểm tra đúng ranh giới và sửa nơi tạo/gán dữ liệu. Demo ở phần 8 bắt NPE chỉ để so sánh thông báo cho mục đích học tập.

## 11. So sánh các loại lỗi gần nhau

| Biểu thức và trạng thái | Loại lỗi / kết quả | Chẩn đoán đúng |
| --- | --- | --- |
| `int[] a = null; a[0]` | NPE | Mảng null, không thể đọc phần tử |
| `int[] a = null; a[0] = 1` | NPE | Mảng null, không thể ghi phần tử |
| `int[] a = null; a.length` | NPE | Mảng null, không thể đọc độ dài |
| `int[] a = new int[0]; a.length` | `0` | Mảng rỗng nhưng hợp lệ |
| `int[] a = new int[0]; a[0]` | `ArrayIndexOutOfBoundsException` | Chỉ số vượt phạm vi |
| `int[] a = new int[1]; a[0]` | `0` | Phần tử nguyên thủy có giá trị mặc định |
| `Integer[] a = {null}; Integer x = a[0]` | `x == null` | Chưa unbox, chỉ truyền tham chiếu |
| `Integer[] a = {null}; int x = a[0]` | NPE lúc unboxing | Mảng tồn tại nhưng phần tử null |
| `Integer[] a = null; int x = a[0]` | NPE lúc đọc mảng | Mảng null, chưa thể unbox |
| `int[][] a = new int[1][]; a[0][0]` | NPE | Mảng con ở phần tử 0 null |

Cần phân biệt ba thao tác dù chúng đứng trên **một dòng source**. Ví dụ `int x = boxed[i]` có ít nhất hai bước: **đọc phần tử mảng** rồi **unbox phần tử**. Helpful NPE chỉ ra bước đã thất bại.

## 12. Bài tập tự kiểm tra

### Bài 1 — Đọc phần tử mảng

~~~java
int[] values = null;
// int x = values[2];
~~~

**Hỏi:** Bỏ comment dòng truy cập sẽ gây lỗi gì? Có phải lỗi `ArrayIndexOutOfBoundsException` không?

**Đáp án:** `NullPointerException` vì tham chiếu mảng `values` null; JVM không thể đọc phần tử. Khi có Helpful NPE, phần hành động có thể là `Cannot load from int array`. Chỉ số 2 không khắc phục vấn đề mảng null.

### Bài 2 — Độ dài mảng

~~~java
int[] a = new int[0];
int[] b = null;
System.out.println(a.length);
// System.out.println(b.length);
~~~

**Hỏi:** Dòng nào hoạt động và dòng nào lỗi khi bỏ comment?

**Đáp án:** `a.length` trả `0`; `b.length` gây NPE với hành động `Cannot read the array length`. Mảng rỗng và mảng null khác nhau.

### Bài 3 — Null trong mảng nhiều chiều

~~~java
int[][] matrix = new int[2][];
matrix[0] = new int[]{3};
// int x = matrix[1][0];
~~~

**Hỏi:** Biểu thức nào null khi bỏ comment? Phải sửa gì nếu mong muốn một hàng rỗng hợp lệ?

**Đáp án:** `matrix[1]` null, không phải `matrix`. Có thể gán `matrix[1] = new int[0]` để hàng tồn tại nhưng rỗng; sau đó **không được đọc `[0]`** nếu chưa kiểm tra `length > 0`.

### Bài 4 — Unboxing phần tử

~~~java
Integer[] scores = {8, null};
// int score = scores[1];
~~~

**Hỏi:** Mảng null hay phần tử null? Thông báo sẽ nói gì?

**Đáp án:** Mảng `scores` không null, nhưng `scores[1]` null. Dòng gán sang `int` yêu cầu unboxing, nên NPE có thể nói `Cannot invoke "java.lang.Integer.intValue()" because "scores[1]" is null`.

### Bài 5 — Phân biệt trước và sau unboxing

~~~java
Integer[] values = null;
// int x = values[0];
~~~

**Hỏi:** Vì sao thông báo không cần nhắc `Integer.intValue()`?

**Đáp án:** JVM phải đọc phần tử từ mảng tham chiếu **trước khi** unbox. Mảng `values` đã null, nên lỗi xảy ra ở thao tác `Cannot load from object array`. Chưa có phần tử nào để chuyển kiểu.

### Bài 6 — Thiết kế một hàm đọc an toàn

**Yêu cầu:** Viết method `int firstOrDefault(Integer[] input, int defaultValue)` theo chính sách:
- Nếu mảng null hoặc rỗng: trả `defaultValue`.
- Nếu phần tử đầu tiên null: cũng trả `defaultValue`.
- Nếu có giá trị: trả giá trị đó.

**Đáp án tham khảo:**

~~~java
static int firstOrDefault(Integer[] input, int defaultValue) {
    if (input == null || input.length == 0) {
        return defaultValue;
    }
    Integer first = input[0];
    return first == null ? defaultValue : first.intValue();
}
~~~

Ở đây `||` có tính **short-circuit**: nếu `input == null`, Java không truy cập `input.length` ở vế phải. Sau khi chắc chắn mảng tồn tại và không rỗng mới đọc `input[0]`, rồi kiểm tra null trước unboxing. Chỉ sử dụng chính sách mặc định này khi nó thực sự đúng với nghiệp vụ.

## 13. Quy trình chẩn đoán nhanh trong thực tế

Khi gặp NPE liên quan mảng hoặc wrapper, thực hiện theo thứ tự:

1. **Đọc loại thao tác trong message**: `load/store from ... array`, `read the array length` hay `invoke ... intValue()`.
2. **Đọc biểu thức sau chữ `because`**. Phân biệt `arr`, `arr[0]`, `grid[0]`, `object.field`.
3. **Mở dòng mã trong stack trace**; nếu có nhiều phép toán trên một dòng, tách ra các biến trung gian để dễ xác định bước gây lỗi.
4. **Xác định trạng thái dữ liệu**: mảng null, mảng rỗng, mảng con null hay wrapper null? Đừng dùng cùng một cách sửa cho mọi trường hợp.
5. **Truy ngược điểm tạo hoặc gán dữ liệu**: constructor, kết quả database, request mapper, deserialize, API trả về hoặc luồng cập nhật.
6. **Quyết định hợp đồng null**: từ chối bằng validation, thay bằng giá trị mặc định có chủ đích, hoặc biểu diễn trạng thái thiếu bằng kiểu phù hợp.
7. **Viết test hồi quy** cho null array, empty array, invalid index, null wrapper element, array nhiều chiều và trường hợp hợp lệ.
8. **Không phụ thuộc vào chuỗi NPE để xử lý nghiệp vụ**; thông báo chỉ phục vụ chẩn đoán, và có thể thay đổi theo JVM.

## 14. Tổng kết

- `arr[i]` khi **`arr == null`** → NPE với thông báo thường bắt đầu `Cannot load/store from ... array`.
- `arr.length` khi **`arr == null`** → NPE với `Cannot read the array length`. Mảng rỗng có `length == 0`, hoàn toàn khác null.
- `Integer`/`Boolean`/`Long` null khi **unboxing** → NPE với thông báo gọi phương thức chuyển kiểu như `Integer.intValue()`.
- `Integer[]` có thể tồn tại nhưng **phần tử trong mảng null**; việc lấy tham chiếu vẫn hợp lệ, lỗi chỉ xuất hiện khi unbox hoặc dereference.
- `int[][]` có thể có **hàng null** dù mảng ngoài tồn tại; message như `grid[0]` giúp xác định đúng cấp.
- Helpful NPE có từ **Java 14**, được bật mặc định trong HotSpot từ **Java 15**; thông báo có thể thay đổi theo JVM và metadata. Ví dụ kiểm chứng dùng Java 17.
- Giải pháp lâu dài là **hợp đồng dữ liệu rõ ràng, validate sớm, kiểm tra null đúng cấp và test**, không phải bắt NPE rồi bỏ qua.

**Tài liệu chính thức:**
- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): nguyên tắc tạo thông báo theo thao tác bytecode và biểu thức null.
- [Java SE 17 — `NullPointerException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): trường hợp ném NPE và tính không bảo đảm của `getMessage()`.
- [Java SE 17 JLS — `5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): unboxing một null reference gây NPE.
- [Java SE 17 JLS — `15.10.4 Run-Time Evaluation of Array Access Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.4): đánh giá truy cập phần tử mảng, kiểm tra null và chỉ số.
- [Java SE 17 JLS — `10.7 Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7): trường `length` của mảng và đặc tính của mảng Java.
