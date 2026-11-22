# Giới hạn vị trí varargs và những lời gọi dễ gây nhầm trong Java

**Varargs** (*variable-length arguments*, tham số biến độ dài) cho phép một phương thức hoặc constructor nhận **số lượng đối số linh hoạt** tại **vị trí tham số cuối cùng**. Trong Java, varargs được khai báo bằng dấu ba chấm `...` sau kiểu phần tử:

```java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
```

Các cách gọi sau đều phù hợp:

```java
sum();                 // Không có số nào
sum(2);                // Một số
sum(2, 3, 5);          // Ba số
sum(new int[]{2, 3}); // Truyền trực tiếp một mảng int[]
```

Dù lời gọi có thể chứa nhiều giá trị, trong khai báo `sum(int... numbers)` chỉ có **một tham số hình thức `numbers`**. Bên trong phương thức, tham số đó có **kiểu mảng `int[]`**.

Ba điều quan trọng nhất:

1. **Varargs phải là tham số cuối cùng** trong danh sách tham số hình thức và chỉ có thể khai báo **một varargs parameter**.
2. Varargs có thể nhận **0, 1 hoặc nhiều biểu thức đối số phần tử**, hoặc nhận **một mảng tương thích**. Hai cách gọi có thể dẫn đến cách tổ chức đối số khác nhau.
3. Khi có **overloading**, lời gọi chứa `null`, một mảng, hoặc các overload kiểu gần nhau có thể tạo ra kết quả khó đoán hoặc lỗi biên dịch do mơ hồ.

Bài này phân tích cú pháp đúng/sai, cơ chế mảng, quy tắc overload, các trường hợp `null`, mảng đối tượng, generic varargs, lỗi thường gặp và cách viết API dễ sử dụng trong Java 17 trở lên.

## 1. Cú pháp varargs và giới hạn vị trí

Cú pháp khai báo:

```java
returnType methodName(Type... parameterName) {
    // parameterName được sử dụng như một mảng Type[]
}
```

Đây là **sơ đồ cú pháp**, không phải chương trình Java độc lập. Dấu `...` nằm **sau tên kiểu, trước tên tham số**, và là cú pháp khai báo đặc biệt.

Ví dụ hợp lệ:

```java
static void printAll(String... messages) {
    for (String message : messages) {
        System.out.println(message);
    }
}

static void log(String category, int level, Object... values) {
    System.out.println(category + ":" + level + ":" + values.length);
}
```

Trong `log(String category, int level, Object... values)`, hai tham số đầu `category` và `level` bắt buộc xuất hiện trước; `values` đứng cuối và có thể nhận số lượng phần tử tùy ý.

### 1.1. Những khai báo không hợp lệ

```java
// SAI: tham số thường đứng sau varargs
static void wrong1(String... messages, int count) { }

// SAI: có hai tham số varargs trong một khai báo
static void wrong2(int... numbers, String... labels) { }

// SAI: dấu ... không đặt sau kiểu dữ liệu của tham số
static void wrong3(...String messages) { }
```

Các dòng này cố ý minh họa lỗi cú pháp; **không biên dịch như chương trình chạy**.

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `void a(int... numbers)` | Hợp lệ | Varargs đứng cuối và là tham số duy nhất |
| `void b(String title, int... scores)` | Hợp lệ | Varargs đứng sau tham số bắt buộc |
| `void c(int[] values)` | Hợp lệ | Tham số mảng thông thường, không có `...` |
| `void d(int... values, String title)` | Không hợp lệ | Varargs không đứng cuối |
| `void e(int... left, int... right)` | Không hợp lệ | Không thể có hai varargs; tham số đầu cũng không đứng cuối |
| `void f(String title, Object... args)` | Hợp lệ | Một varargs ở cuối |
| `void g(Object... args, String title)` | Không hợp lệ | Vị trí varargs sai |

**Nếu cần nhiều nhóm dữ liệu có độ dài linh hoạt**, truyền các mảng hoặc collection riêng biệt thay vì cố khai báo nhiều varargs:

```java
static void combine(int[] left, int[] right) {
    System.out.println(left.length + right.length);
}
```

Với API cần thông tin bắt buộc sau nhiều giá trị, hãy **đổi thứ tự tham số** để varargs đứng cuối, hoặc thiết kế đối tượng mang tham số.

### 1.2. Varargs không áp dụng cho biến cục bộ/field

Dấu `...` trong Java 17 được sử dụng ở **tham số varargs cuối** của phương thức hoặc constructor. Không dùng `int... values;` như một khai báo mảng cục bộ thông thường:

```java
int[] values = {1, 2, 3}; // Hợp lệ
// int... values;          // SAI khi khai báo local variable
```

Bên trong thân một phương thức varargs, tham số vẫn được sử dụng như mảng; dấu `...` không phải toán tử “trải mảng” trong biểu thức lời gọi.

## 2. Cơ chế mảng: `int...` và `int[]` liên quan thế nào?

Xét:

```java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
```

Bên trong `sum`, `numbers` là một biến tham số có **kiểu `int[]`**:

- `numbers.length` trả về số phần tử của mảng.
- `numbers[0]` đọc phần tử đầu tiên nếu mảng có ít nhất một phần tử.
- Vòng `for-each` duyệt các phần tử của mảng.
- Mảng có thể được truyền trực tiếp vào lời gọi phù hợp.

Ở cách gọi **variable arity** như `sum(2, 3, 5)`, Java thu thập ba giá trị vào một mảng `int[]` mới để truyền cho tham số. Ở cách gọi `sum(new int[]{2, 3})`, biểu thức đối số là **một mảng `int[]` tương thích**, nên mảng đó có thể được truyền **trực tiếp**, không cần tạo thêm mảng chứa các phần tử của nó.

**Chú ý:** nói “một phương thức varargs nhận 3 tham số” khi gọi `sum(2, 3, 5)` không chính xác nếu đang đếm **tham số hình thức**. Khai báo chỉ có một tham số hình thức `numbers`; lời gọi có ba biểu thức đối số.

### 2.1. Không thể overload `int...` và `int[]` cùng tên

Hai khai báo sau **xung đột chữ ký** khi nằm trong cùng lớp:

```java
// SAI: không thể đặt cả hai trong một class
static void show(int... values) { }
static void show(int[] values) { }
```

Một tham số varargs `int...` được biểu diễn dưới dạng **mảng `int[]`** trong chữ ký phương thức. Hai khai báo trên không tạo thành hai overload khác nhau.

Nếu API cần một cách nhận mảng và một cách nhận các giá trị riêng lẻ, **chỉ một phương thức `int...` đã đủ**:

```java
static void show(int... values) {
    System.out.println(values.length);
}

// Các cách gọi hợp lệ trong một phương thức:
show(1, 2);              // Hai phần tử
show(new int[]{1, 2});   // Một đối số mảng có hai phần tử
```

### 2.2. Một mảng truyền trực tiếp có thể được sửa

Java truyền tham số **theo giá trị**: varargs method nhận bản sao giá trị tham chiếu đến mảng. Nếu phía gọi cung cấp mảng có sẵn, việc sửa phần tử mảng trong phương thức có thể ảnh hưởng tới mảng của bên gọi.

Ví dụ hoàn chỉnh trong tệp **`VarargsArrayDemo.java`**:

```java
import java.util.Arrays;

public class VarargsArrayDemo {
    static void increaseFirst(int... values) {
        if (values.length > 0) {
            values[0]++;
        }
    }

    public static void main(String[] args) {
        int[] existing = {2, 4};

        increaseFirst(existing);
        System.out.println(Arrays.toString(existing));

        increaseFirst(7, 8); // Có mảng varargs được tạo cho lời gọi này
        System.out.println(Arrays.toString(existing));

        System.out.println(existing.length);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 VarargsArrayDemo.java
java VarargsArrayDemo
```

Stdout:

```text
[3, 4]
[3, 4]
2
```

Ở lần gọi đầu, `values` và `existing` cùng tham chiếu đến mảng đó, nên `values[0]++` làm `existing[0]` đổi từ `2` thành `3`. Ở lần gọi `increaseFirst(7, 8)`, phương thức nhận mảng varargs được tạo riêng từ hai giá trị; lệnh tăng không đụng tới mảng `existing`.

**Thiết kế an toàn:** nếu một phương thức có thể thay đổi dữ liệu đầu vào, cần mô tả rõ điều đó. Để tránh tác động lên mảng của caller, có thể tạo bản sao bằng `values.clone()` trước khi sửa.

## 3. Không đối số, một đối số và nhiều đối số

Xét phương thức:

```java
static String describe(String label, int... values) {
    return label + "=" + values.length;
}
```

Các lời gọi hợp lệ:

```java
describe("none");                // values là mảng rỗng, length = 0
describe("one", 9);              // values có 1 phần tử
describe("three", 1, 2, 3);      // values có 3 phần tử
describe("array", new int[]{4, 5}); // values có 2 phần tử
```

**Tham số bắt buộc vẫn bắt buộc**. `describe()` không hợp lệ vì thiếu tham số `label`, dù `values` có thể rỗng.

Một lệnh như `describe("one", 9)` chứa **hai đối số** (nhãn và giá trị `9`), nhưng khai báo cũng có đúng **hai tham số hình thức** (`label` và `values`). Điều này không có nghĩa tham số `values` mang kiểu `int`: ở thân phương thức, nó vẫn là **`int[]` dài 1**.

Với lời gọi `describe("three", 1, 2, 3)`, có **bốn biểu thức đối số** nhưng vẫn chỉ **hai tham số hình thức**.

Cũng có thể chủ động truyền một mảng rỗng:

```java
describe("none", new int[0]);
```

Lúc này `values.length == 0` giống với lời gọi không truyền số nào, nhưng nguồn mảng từ phía gọi khác nhau. Điều này có thể quan trọng nếu phương thức thay đổi hoặc lưu lại mảng đầu vào.

## 4. `null`: mảng `null` khác một phần tử `null`

Với varargs **kiểu tham chiếu**, `null` là nguồn gây nhầm lẫn thường gặp nhất.

Xét:

```java
static void inspect(String... words) {
    if (words == null) {
        System.out.println("Mảng null");
    } else {
        System.out.println("Số phần tử: " + words.length);
    }
}
```

Các lời gọi sau **không tương đương**:

| Lời gọi | Ý nghĩa | Kết quả `inspect` |
| --- | --- | --- |
| `inspect()` | Không truyền phần tử nào | `Số phần tử: 0` |
| `inspect("A")` | Một phần tử `"A"` | `Số phần tử: 1` |
| `inspect(new String[0])` | Truyền mảng rỗng | `Số phần tử: 0` |
| `inspect((String[]) null)` | Truyền **tham chiếu mảng null** | `Mảng null` |
| `inspect((String) null)` | Truyền **một phần tử String null** | `Số phần tử: 1` |
| `inspect(null)` | Mặc định khớp lời gọi **một đối số mảng `String[]` null** trong ví dụ này; `javac` có thể cảnh báo | `Mảng null` |

### 4.1. Chương trình Java 17 minh họa

Lưu thành **`NullVarargsDemo.java`**:

```java
import java.util.Arrays;

public class NullVarargsDemo {
    static void inspect(String... words) {
        if (words == null) {
            System.out.println("Mảng null");
        } else {
            System.out.println(words.length + ": " + Arrays.toString(words));
        }
    }

    public static void main(String[] args) {
        inspect();
        inspect("A", "B");
        inspect((String[]) null);
        inspect((String) null);
        inspect(new String[]{null, "C"});
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 NullVarargsDemo.java
java NullVarargsDemo
```

**Stdout:**

```text
0: []
2: [A, B]
Mảng null
1: [null]
2: [null, C]
```

Ở đây đã dùng phép ép kiểu tường minh để **không phụ thuộc vào cách người đọc tự suy đoán** về ý nghĩa của literal `null`:

- `(String[]) null` có kiểu `String[]`, nghĩa là chính mảng truyền vào bằng `null`.
- `(String) null` có kiểu `String`, nên Java xây dựng một mảng varargs chứa **một phần tử null**.
- `new String[]{null, "C"}` truyền một mảng có đúng hai phần tử, trong đó phần tử đầu `null`.

**Sai lầm gây lỗi runtime:** giả định `words` luôn khác `null` rồi truy cập `words.length`. Khi phía gọi truyền `(String[]) null`, việc đọc `length` sẽ ném `NullPointerException`. Nếu API muốn cấm mảng `null`, hãy kiểm tra sớm và ném lỗi có ý nghĩa, hoặc quy định không chấp nhận `null` trong tài liệu.

### 4.2. Tại sao `inspect(null)` dễ gây nhầm?

Với **duy nhất overload** `inspect(String... words)`, tham số hình thức ở dạng mảng `String[]`. Biểu thức `null` có thể phù hợp với `String[]` theo cách gọi có số tham số cố định, nên về mặt hiệu ứng thường là **mảng null**, không phải “một phần tử null”. `javac` có thể phát cảnh báo:

```text
non-varargs call for last parameter of varargs method
```

Thông điệp chi tiết có thể khác theo phiên bản JDK. Cách viết rõ ý định:

```java
inspect((String[]) null); // Cố ý truyền mảng null
inspect((String) null);   // Cố ý truyền một phần tử null
```

Dùng `inspect()` nếu muốn danh sách rỗng; không dùng `inspect(null)` để biểu diễn “không có đối số”.

### 4.3. Varargs primitive và `null`

Với `int... numbers`, đối số `null` có thể dùng làm **tham chiếu mảng `int[]` null**, nhưng **không có phần tử `int` mang giá trị null**:

```java
static void count(int... numbers) {
    System.out.println(numbers == null ? "null array" : numbers.length);
}

count((int[]) null);       // Hợp lệ: mảng int[] null
// count((int) null);      // SAI: không thể ép null thành primitive int
```

Một wrapper như `Integer...` cho phép phần tử `Integer` bằng `null`, nhưng nếu dùng auto-unboxing sang `int` sẽ có nguy cơ `NullPointerException`.

## 5. Overloading: varargs được xét sau các cách gọi phù hợp hơn

**Overloading** cho phép nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau. Java thực hiện việc chọn overload qua các giai đoạn, với ưu tiên chung:

1. Các phương thức có thể áp dụng mà **không cần boxing/unboxing và không dùng variable arity**.
2. Nếu chưa tìm được, các phương thức có thể áp dụng với **boxing/unboxing**, vẫn không dùng variable arity.
3. Nếu hai giai đoạn trước không tìm được phương thức áp dụng, mới xét **lời gọi variable arity (varargs mở rộng)**.

Trong mỗi giai đoạn, Java còn áp dụng quy tắc lựa chọn phương thức **cụ thể nhất**; nếu vẫn không chọn được duy nhất một phương thức, lời gọi có thể mơ hồ.

Điều này có nghĩa một phương thức varargs **không luôn được chọn** chỉ vì lời gọi có đối số kiểu phù hợp: phương thức nhận số lượng cố định có thể thắng.

### 5.1. Ví dụ overload cố định và varargs

Lưu thành **`OverloadVarargsDemo.java`**:

```java
public class OverloadVarargsDemo {
    static void select(int value) {
        System.out.println("Một int: " + value);
    }

    static void select(int... values) {
        System.out.println("Varargs: " + values.length);
    }

    public static void main(String[] args) {
        select(5);
        select();
        select(1, 2);
        select(new int[]{7, 8, 9});
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OverloadVarargsDemo.java
java OverloadVarargsDemo
```

**Stdout:**

```text
Một int: 5
Varargs: 0
Varargs: 2
Varargs: 3
```

Giải thích:

- `select(5)` khớp `select(int)` theo lời gọi fixed arity, nên overload cố định được chọn.
- `select()` không thể gọi `select(int)` vì thiếu đối số; phương thức varargs chấp nhận mảng rỗng.
- `select(1, 2)` không khớp overload một `int`; overload varargs nhận hai giá trị.
- `select(new int[]{7, 8, 9})` truyền **một mảng `int[]`** vào overload `select(int...)`; bên trong `values.length == 3`.

**Điểm tinh tế:** ở lời gọi cuối, phương thức varargs được chọn **trong dạng gọi có số tham số cố định** vì một biểu thức mảng phù hợp với tham số `int[]`. Phương thức khai báo `...` có thể được gọi ở cả dạng **fixed arity** (truyền mảng) và **variable arity** (truyền các phần tử).

### 5.2. Một overload nhận wrapper có thể thắng lời gọi varargs

```java
static void choose(Integer value) {
    System.out.println("Integer");
}

static void choose(int... values) {
    System.out.println("int varargs");
}
```

Trong ngữ cảnh có hai overload trên, `choose(3)` chọn `choose(Integer)` qua **boxing trong giai đoạn fixed arity**, thay vì dùng variable arity để đóng gói `3` vào `int[]`. Đoạn khai báo này có thể được thử bên trong một lớp riêng.

Kết luận quan trọng: thứ tự lựa chọn overload không đơn giản là “kiểu nguyên thủy `int` luôn ưu tiên mọi phương thức liên quan đến `int`”. Cần phân biệt **kiểu tham số trong lời gọi fixed arity** và **kiểu phần tử khi mở rộng varargs**.

### 5.3. Overload varargs có thể mơ hồ

Xét:

```java
static void process(String... values) {
    System.out.println("String");
}

static void process(Integer... values) {
    System.out.println("Integer");
}
```

Lời gọi `process()` **mơ hồ**, vì không có đối số để phân biệt nên cả hai overload varargs có thể áp dụng và không có overload nào cụ thể hơn theo quy tắc chọn phương thức.

Lời gọi `process(null)` cũng **mơ hồ** giữa hai tham số kiểu mảng không có quan hệ subtype `String[]` và `Integer[]`.

Cách viết rõ kiểu:

```java
process(new String[0]);     // Chọn phiên bản String...
process(new Integer[0]);    // Chọn phiên bản Integer...
process((String[]) null);   // Chọn String..., mảng null
process((Integer) null);    // Chọn Integer..., một phần tử null
```

Đây là **mẫu minh họa** để đặt trong một lớp có hai khai báo `process` như trên. Không nên cố thêm các lời gọi `process()` hoặc `process(null)` vào mã cần biên dịch: chúng sẽ gây lỗi mơ hồ.

### 5.4. Tránh nhiều overload varargs gần giống nhau

Một bộ API có các overload như `send(String...)`, `send(Object...)` và `send(String, Object...)` có thể rất khó đọc ở các lời gọi rỗng, `null` hoặc tham số có kiểu chung. Khi API công khai trở nên mơ hồ:

- Đặt tên phương thức diễn tả hành vi khác nhau.
- Giữ số overload ít nhất có thể.
- Thiết kế kiểu đối số rõ ràng hoặc yêu cầu truyền collection/mảng nếu đó là dữ liệu thật của API.
- Dùng ép kiểu tường minh khi cần làm rõ một lời gọi cụ thể, không dựa vào cast rải rác để cứu một thiết kế API gây nhầm lẫn thường xuyên.

## 6. Đối số mảng có thể là *một phần tử* hoặc *toàn bộ danh sách*

Đây là trường hợp rất dễ nhầm khi varargs có kiểu phần tử rộng như `Object`.

Xét:

```java
static void inspect(Object... values) {
    System.out.println(values.length);
}
```

Với một `String[]`, Java có thể xem mảng là **mảng tương thích với `Object[]`** (vì mảng tham chiếu Java có tính hiệp biến). Vì vậy:

```java
inspect(new String[]{"A", "B"});          // Có 2 phần tử, truyền như Object[]
inspect((Object) new String[]{"A", "B"}); // Có 1 phần tử: phần tử đó là String[]
```

Trong lời gọi đầu, `String[]` có thể chuyển sang `Object[]`, nên **mảng được truyền như chính mảng varargs**, không tự đóng gói thành một phần tử `Object`. `javac` có thể cảnh báo lời gọi không sử dụng cơ chế varargs theo cách nhiều người dự đoán.

Trong lời gọi thứ hai, phép cast `(Object)` làm biểu thức có kiểu `Object`, nên Java tạo mảng `Object[]` mới chứa một phần tử là đối tượng `String[]`.

Mảng nguyên thủy như `int[]` lại khác: `int[]` là một `Object`, nhưng **không phải `Object[]`**. Vì thế:

```java
inspect(new int[]{1, 2}); // Một phần tử Object, bản thân là mảng int[]
```

### 6.1. Ví dụ chạy được để phân biệt rõ

Lưu thành **`ObjectVarargsDemo.java`**:

```java
import java.util.Arrays;

public class ObjectVarargsDemo {
    static void inspect(Object... values) {
        System.out.println(values.length + " => " + Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        inspect("A", "B");
        inspect((Object[]) new String[]{"C", "D"});
        inspect((Object) new String[]{"E", "F"});
        inspect(new int[]{1, 2});
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ObjectVarargsDemo.java
java ObjectVarargsDemo
```

**Stdout:**

```text
2 => [A, B]
2 => [C, D]
1 => [[E, F]]
1 => [[1, 2]]
```

Ở đây đã dùng cast `(Object[])` và `(Object)` để chủ ý biểu thị **một danh sách phần tử** hay **một phần tử là mảng**. `Arrays.deepToString` hiển thị nội dung mảng lồng nhau, giúp quan sát rõ sự khác biệt.

**Đừng đồng nhất một biểu thức đối số với một phần tử varargs.** Nếu biểu thức duy nhất là mảng tương thích với **toàn bộ kiểu tham số mảng**, nó có thể đóng vai trò mảng chứa tất cả phần tử; nếu biểu thức có kiểu phần tử `Object`, nó được đóng gói thành một phần tử.

## 7. Generic varargs và cảnh báo về *heap pollution*

Varargs với kiểu mảng có phần tử **không reifiable**, chẳng hạn `List<String>...`, có thể gây cảnh báo của trình biên dịch. Nguyên nhân là:

- Varargs được triển khai bằng **mảng**.
- Mảng Java có kiểm tra kiểu thành phần khi chạy và hiệp biến đối với kiểu tham chiếu.
- Generic thường bị **type erasure**, nên runtime không kiểm tra đầy đủ `List<String>` và `List<Integer>` ở cấp phần tử generic.
- Khi kết hợp sai, có thể xuất hiện **heap pollution**: một giá trị có kiểu thực tế không khớp với kiểu mà mã generic đang tin tưởng.

Ví dụ cố ý **không an toàn**, chỉ để phân tích, **không nên sử dụng**:

```java
import java.util.List;

class UnsafeExample {
    static void unsafe(List<String>... groups) {
        Object[] array = groups;
        array[0] = List.of(42);
        String first = groups[0].get(0);
        System.out.println(first);
    }
}
```

Phần khai báo có thể biên dịch kèm cảnh báo generic/varargs; nếu gọi `unsafe(List.of("A"))`, việc đặt `List<Integer>` vào mảng qua alias `Object[]` phá vỡ giả định `List<String>`, rồi đọc giá trị như `String` gây nguy cơ `ClassCastException`.

**Không tự động thêm `@SafeVarargs` để tắt cảnh báo** nếu phương thức có thể thay đổi mảng varargs không an toàn hoặc làm lộ mảng ra nơi khác.

### 7.1. Cách dùng `@SafeVarargs` khi thật sự an toàn

Annotation `@SafeVarargs` là một **cam kết của lập trình viên** rằng implementation không làm thao tác không an toàn với varargs. Trong Java 17, annotation này được phép trên những phương thức `static`, `final`, constructor, hoặc instance method `private` thích hợp, vì chúng không thể bị override theo cách làm sai cam kết.

Một ví dụ chỉ **đọc**, không chỉnh sửa hoặc tiết lộ mảng:

```java
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> int countElements(List<T>... groups) {
        int total = 0;
        for (List<T> group : groups) {
            total += group.size();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(countElements(List.of("A"), List.of("B", "C")));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SafeVarargsDemo.java
java SafeVarargsDemo
```

Stdout:

```text
3
```

Trong ví dụ, thân `countElements` chỉ đọc kích thước từng danh sách và không đưa tham chiếu mảng varargs ra ngoài. Điều này phù hợp với cam kết `@SafeVarargs`.

Một cách thiết kế khác để tránh rắc rối mảng generic là **nhận `List<List<T>>` hoặc `Collection<? extends List<T>>`** theo nhu cầu API; khi đó caller gửi một collection rõ ràng, không dùng varargs generic.

## 8. Constructor cũng có varargs và cùng giới hạn vị trí

Constructor có thể khai báo tham số varargs giống phương thức:

```java
class Team {
    private final String name;
    private final String[] members;

    Team(String name, String... members) {
        this.name = name;
        this.members = members.clone();
    }

    int memberCount() {
        return members.length;
    }
}
```

Lời gọi hợp lệ:

```java
new Team("Empty");
new Team("Dev", "An");
new Team("Ops", "An", "Bình");
new Team("QA", new String[]{"Lan", "Minh"});
```

Ở constructor `Team(String name, String... members)`, `members` vẫn là **tham số cuối cùng**. Lớp ví dụ sử dụng `members.clone()` để sao chép mảng khi lưu trong field, tránh giữ trực tiếp mảng mutable của caller; nếu caller chủ động truyền `(String[]) null`, đoạn constructor này sẽ ném `NullPointerException`, nên API thực tế cần quyết định và mô tả có chấp nhận `null` hay không.

Không thể đặt một tham số bắt buộc `int level` **sau** `String... members` trong khai báo constructor. Nếu thật sự cần `level`, hãy đặt trước `members` hoặc cân nhắc dùng một đối tượng cấu hình rõ ràng.

## 9. Varargs trong phương thức `main`

Java 17 cho phép dùng varargs ở tham số `main` truyền thống:

```java
public static void main(String... args) {
    System.out.println(args.length);
}
```

`String... args` tương đương tham số dạng `String[] args` về khả năng nhận mảng đối số của launcher. Đây là một **tham số hình thức duy nhất**; các từ trên command line được trình khởi chạy chuyển thành phần tử của mảng `args`.

Ví dụ tệp **`MainVarargsDemo.java`**:

```java
public class MainVarargsDemo {
    public static void main(String... args) {
        System.out.println("Count: " + args.length);
        for (String arg : args) {
            System.out.println(arg);
        }
    }
}
```

```bash
javac -encoding UTF-8 MainVarargsDemo.java
java MainVarargsDemo red blue
```

Stdout:

```text
Count: 2
red
blue
```

Không được viết cả `main(String[] args)` và `main(String... args)` với cùng tên trong một lớp nhằm tạo overload: chữ ký tham số tương đương nhau nên gây lỗi định nghĩa trùng.

## 10. Những cách gọi sai phổ biến

Dựa trên khai báo:

```java
static void report(String title, int... scores) {
    System.out.println(title + ": " + scores.length);
}
```

Phân tích các lời gọi:

| Lời gọi | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `report("A")` | Có | Varargs nhận 0 phần tử |
| `report("A", 10)` | Có | Một phần tử int |
| `report("A", 10, 20)` | Có | Hai phần tử int |
| `report("A", new int[]{10, 20})` | Có | Truyền một mảng int[] |
| `report()` | Không | Thiếu tham số bắt buộc `title` |
| `report(10, "A")` | Không | Sai thứ tự và kiểu đối số |
| `report("A", new int[]{10, 20}, 30)` | Không | Không thể trộn “một mảng `int[]`” với đối số `int` còn lại để tạo một danh sách varargs `int` |
| `report("A", (int[]) null)` | Có, nhưng nguy hiểm | `scores` là null; đọc `scores.length` gây `NullPointerException` |
| `report("A", (Integer) null)` | Không an toàn / không hợp lệ trong ví dụ | `Integer` null cần unboxing thành `int` nếu lời gọi được chấp nhận, gây `NullPointerException` lúc chạy |
| `report("A", 2.5)` | Không | Không tự thu hẹp `double` thành `int` |
| `report("A", "10")` | Không | Không tự chuyển `String` sang `int` |

**Về `report("A", (Integer) null)`:** nếu lời gọi được chọn như variable arity, Java có thể chấp nhận chuyển `Integer` thành `int` bằng unboxing, và vì giá trị là `null` nên ném `NullPointerException` trước khi vào thân phương thức. Đây là lỗi **runtime**, không phải luôn là lỗi biên dịch; điều quan trọng là không truyền wrapper null tới tham số primitive.

Để thêm giá trị `30` vào dữ liệu từ mảng sẵn có, hãy tạo mảng mới (ví dụ dùng `Arrays.copyOf` rồi gán phần tử cuối), hoặc thay đổi API để nhận collection phù hợp. Java **không hỗ trợ cú pháp spread** kiểu `report("A", ...numbers)`.

## 11. Varargs và generic API: cân nhắc ranh giới rõ ràng

Varargs hữu ích khi dữ liệu đầu vào là **một nhóm nhỏ các phần tử cùng kiểu**, chẳng hạn:

```java
static boolean containsAny(String source, String... fragments) {
    for (String fragment : fragments) {
        if (source.contains(fragment)) {
            return true;
        }
    }
    return false;
}
```

Lời gọi đọc tự nhiên:

```java
containsAny("Java Core", "Spring", "Java"); // true
containsAny("Java Core");                   // false
```

Nhưng hãy cân nhắc không dùng varargs khi:

- Số lượng mục rất lớn, mảng/collection đã tồn tại từ trước.
- Cần phân biệt rõ **không có dữ liệu** với **dữ liệu là null**.
- Phần tử là kiểu generic phức tạp và nguy cơ heap pollution gây khó duy trì.
- Có nhiều overload cạnh tranh, đặc biệt khi một lời gọi rỗng hoặc `null` khó chọn.
- Có yêu cầu bảo toàn bất biến đối tượng hoặc không lưu lại mảng tham số mutable.
- Các tham số là những dữ liệu **không cùng nghĩa**, dù cùng kiểu, ví dụ `transfer(amount, accountId, fee)`. Nên dùng tham số đặt tên rõ ràng.

Với varargs, tên `values`, `items` hoặc `scores` nên ở dạng số nhiều để phản ánh biến trong thân là mảng.

### Tránh lỗi truyền mảng null bằng kiểm tra sớm

Nếu hợp đồng không cho phép mảng `null`:

```java
static int total(int... numbers) {
    java.util.Objects.requireNonNull(numbers, "numbers");
    int sum = 0;
    for (int value : numbers) {
        sum += value;
    }
    return sum;
}
```

Khi gọi `total()`, Java tạo mảng rỗng; phương thức trả về `0`. Khi gọi `total((int[]) null)`, lời gọi có thể biên dịch nhưng `requireNonNull` ném `NullPointerException` với thông điệp rõ hơn. Nếu muốn từ chối **phần tử null** của `String...`, cần duyệt từng phần tử và kiểm tra riêng; kiểm tra mảng không đủ.

### Tránh tác dụng phụ trên mảng caller

Nếu phương thức cần sắp xếp dữ liệu nhận vào:

```java
static int[] sortedCopy(int... values) {
    java.util.Objects.requireNonNull(values, "values");
    int[] copy = values.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
```

Vì đã tạo bản sao, `sortedCopy(existingArray)` không sắp xếp lại mảng `existingArray`. Ví dụ minh họa này trả mảng đã sắp xếp để caller dùng tiếp; nó không tự thay đổi nguồn đầu vào.

## 12. Chương trình thực hành tổng hợp

Lưu toàn bộ nội dung sau vào **`VarargsPractice.java`**:

```java
import java.util.Arrays;

public class VarargsPractice {
    static void printCount(String label, String... words) {
        if (words == null) {
            System.out.println(label + ": null-array");
            return;
        }
        System.out.println(label + ": " + words.length + " " +
                Arrays.toString(words));
    }

    static void choose(int number) {
        System.out.println("fixed: " + number);
    }

    static void choose(int... numbers) {
        System.out.println("varargs: " + Arrays.toString(numbers));
    }

    static void objects(Object... values) {
        System.out.println("objects: " + values.length + " " +
                Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        printCount("empty");
        printCount("two", "A", "B");
        printCount("one-null", (String) null);
        printCount("array-null", (String[]) null);

        choose(7);
        choose(7, 8);
        choose(new int[]{1, 2, 3});

        objects((Object[]) new String[]{"X", "Y"});
        objects((Object) new String[]{"X", "Y"});
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 VarargsPractice.java
java VarargsPractice
```

**Stdout chính xác:**

```text
empty: 0 []
two: 2 [A, B]
one-null: 1 [null]
array-null: null-array
fixed: 7
varargs: [7, 8]
varargs: [1, 2, 3]
objects: 2 [X, Y]
objects: 1 [[X, Y]]
```

Đây là ví dụ gom **những cách gọi dễ gây nhầm** vào một chương trình: số lượng phần tử, mảng null, phần tử null, ưu tiên overload cố định, và sự khác nhau giữa truyền `String[]` như `Object[]` so với một phần tử `Object`. Phép cast trong ví dụ được sử dụng **có chủ đích** để buộc ý nghĩa lời gọi rõ ràng.

## 13. Bài tự luyện có đáp án

### Bài 1 — Sửa vị trí varargs

Khai báo sai:

```java
static void notifyAll(String... users, String message) {
}
```

**Vì sao sai?** Tham số varargs `users` không đứng cuối. **Một phương án sửa:**

```java
static void notifyAll(String message, String... users) {
    for (String user : users) {
        System.out.println(user + ": " + message);
    }
}
```

Lời gọi: `notifyAll("Đã cập nhật", "An", "Bình");`. `message` bắt buộc trước, còn `users` nhận hai phần tử.

### Bài 2 — Đếm tham số hình thức và đối số

```java
static void record(String category, int... values) {
}
```

Với `record("score", 1, 2, 3)`:

- Số **tham số hình thức**: **2** (`category` và `values`).
- Số **biểu thức đối số tại lời gọi**: **4**.
- Độ dài mảng `values` trong thân: **3**.

Với `record("score")`, vẫn có **2 tham số hình thức**, nhưng lời gọi chỉ có **1 đối số**, còn `values.length == 0`.

### Bài 3 — Mảng hay một phần tử?

```java
static int size(Object... values) {
    return values == null ? -1 : values.length;
}
```

Dự đoán:

- `size(new String[]{"A", "B"})`: **2** vì `String[]` có thể truyền như mảng `Object[]`.
- `size((Object) new String[]{"A", "B"})`: **1** vì mảng `String[]` đã được xem như một phần tử `Object`.
- `size(new int[]{1, 2})`: **1** vì `int[]` không là `Object[]`.
- `size((Object[]) null)`: **-1** vì chính mảng varargs là `null`.
- `size((Object) null)`: **1** vì mảng varargs chứa một phần tử `null`.

### Bài 4 — Phương thức nào được chọn?

```java
static String kind(int value) {
    return "fixed";
}

static String kind(int... values) {
    return "varargs";
}
```

- `kind(1)` → **`"fixed"`**.
- `kind()` → **`"varargs"`**.
- `kind(1, 2)` → **`"varargs"`**.
- `kind(new int[]{1})` → **`"varargs"`** vì overload nhận mảng phù hợp.

### Bài 5 — Lời gọi mơ hồ

```java
static void send(String... parts) { }
static void send(Integer... parts) { }
```

`send()` và `send(null)` có vấn đề gì? **Mơ hồ tại thời điểm biên dịch** vì cả hai overload áp dụng mà không có lựa chọn cụ thể hơn. Để chọn một cách rõ ràng, dùng `send(new String[0])` hoặc `send(new Integer[0])` cho lời gọi rỗng, và cast mảng phù hợp nếu cố ý truyền mảng `null`.

### Bài 6 — Có cần tạo bản sao?

```java
static void replaceFirst(String... values) {
    values[0] = "changed";
}
```

Nếu caller truyền `String[] data = {"old"}; replaceFirst(data);` thì `data[0]` trở thành **`"changed"`**. Nếu không muốn sửa dữ liệu của caller, hãy tạo bản sao mảng trong phương thức trước khi ghi.

## 14. Checklist trước khi viết hoặc gọi phương thức varargs

1. **Đọc phần khai báo:** chỉ có **một** `Type... name` và nó có đứng cuối danh sách tham số không?
2. **Phân biệt mảng với phần tử:** caller truyền `new Type[]{...}` hay truyền nhiều biểu thức riêng lẻ?
3. **Đếm đối số đúng:** tham số bắt buộc trước varargs vẫn phải có đủ.
4. **Kiểm tra kiểu:** phần tử trong lời gọi mở rộng phải có khả năng chuyển đổi sang `Type`; mảng truyền trực tiếp phải tương thích với `Type[]`.
5. **Cẩn thận với `null`:** mảng null khác một phần tử null; dùng cast rõ kiểu khi thật sự cần.
6. **Kiểm tra overload:** fixed-arity candidates được xét trước variable arity; lời gọi `()` hay `(null)` có thể mơ hồ với nhiều overload.
7. **Kiểm tra mảng có sẵn của caller:** phương thức có sửa phần tử mảng hoặc giữ lại tham chiếu mảng không?
8. **Kiểm tra generic varargs:** cân nhắc heap pollution và chỉ dùng `@SafeVarargs` khi implementation thật sự an toàn.
9. **Tránh cú pháp không thuộc Java:** không có toán tử `...array` để spread mảng trong lời gọi, và không thể đặt varargs trước tham số thường.
10. **Ưu tiên lời gọi rõ ràng:** khi muốn không có phần tử, gọi không truyền các đối số varargs; khi muốn truyền một phần tử null hay một mảng null, viết biểu thức có kiểu tường minh.

## Ghi nhớ

- Varargs được khai báo dưới dạng **`Type... name` ở vị trí cuối cùng**; một danh sách tham số chỉ có thể có một varargs.
- Trong thân phương thức, tham số varargs là **mảng `Type[]`**. Lời gọi có thể sử dụng **0 hoặc nhiều phần tử**, hoặc **một mảng tương thích**.
- **`f()`**, **`f((String) null)`** và **`f((String[]) null)`** có thể biểu thị ba tình huống hoàn toàn khác nhau: mảng rỗng, một phần tử null, và mảng null.
- Khi overload, Java ưu tiên tìm phương thức có thể gọi theo số tham số cố định trước khi xét việc mở rộng varargs; nhiều overload varargs có thể khiến lời gọi mơ hồ.
- **Mảng tham chiếu** như `String[]` có thể được truyền như `Object[]`, còn `int[]` thì không. Dùng cast đúng khi cần phân biệt “một mảng làm cả danh sách” và “một mảng làm một phần tử”.
- Varargs dựa trên mảng thật; nó có thể chia sẻ mảng với caller và có nguy cơ **heap pollution** khi kết hợp với generic không reifiable. Viết API rõ hợp đồng và sao chép dữ liệu khi cần.
