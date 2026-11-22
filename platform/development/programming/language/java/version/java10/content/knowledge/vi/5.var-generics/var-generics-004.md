# `var` với phương thức generic và phương thức tạo đối tượng (Java 10+)

## 1. Khái niệm cốt lõi: hai quá trình suy luận kiểu

Từ **Java 10**, khai báo `var` cho phép trình biên dịch suy ra **kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo. Khi biểu thức ở vế phải là **lời gọi phương thức generic** hoặc **biểu thức tạo đối tượng generic**, có thể xảy ra **hai bước suy luận kiểu liên tiếp**:

1. **Suy luận tham số kiểu của lời gọi**: Java xác định `T`, `K`, `V`… trong phương thức generic hoặc toán tử diamond `<>` của biểu thức `new`, dựa trên các đối số và ngữ cảnh kiểu khả dụng.
2. **Suy luận kiểu của biến `var`**: sau khi vế phải đã có kiểu tĩnh, `var` lấy chính kiểu của biểu thức đó làm kiểu của biến.

Ví dụ:

```java
var languages = java.util.List.of("Java", "Kotlin");
```

Phương thức `List.of` là một *generic factory method*, có thể hiểu qua chữ ký dạng `static <E> List<E> of(E... elements)`. Hai đối số chuỗi cung cấp thông tin để suy ra `E = String`; biểu thức trả về `List<String>`. Sau đó `var` nhận kiểu `List<String>`.

Ngược lại:

```java
var items = new java.util.ArrayList<>();
```

Ở đây không có đối số constructor nào giúp suy ra kiểu phần tử, và khai báo `var` không cung cấp kiểu đích tường minh ở bên trái. Với ví dụ này, Java suy ra `ArrayList<Object>`, **không** tự hiểu rằng sau đó bạn muốn thêm chuỗi.

Điểm cần nhớ: `var` **không phải generic**, không phải kiểu `Object`, không tạo kiểu động và không làm biến tự đổi kiểu khi sử dụng. Kiểu được chốt ở thời điểm biên dịch.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Tham số kiểu generic | Đại diện cho một kiểu chưa xác định trong khai báo API | `<T> T first(List<T> values)` |
| Suy luận kiểu cho lời gọi generic | Xác định `T` khi gọi phương thức, hoặc kiểu tham số cho `<>` trong `new` | `first(List.of("A", "B"))` trả về `String` |
| Suy luận biến cục bộ bằng `var` | Nhận kiểu tĩnh của **toàn biểu thức khởi tạo** | `var firstName = first(List.of("A", "B"));` có kiểu `String` |

Ngoài ra, **kiểu static của biểu thức** khác với **lớp triển khai lúc chạy**. Ví dụ, một phương thức được khai báo trả về `List<String>` có thể trả về đối tượng của một lớp nội bộ; `var` vẫn suy ra kiểu `List<String>` từ kiểu trả về đã khai báo, không dò lớp triển khai thực tế.

### `var` không cung cấp “target type” theo cách khai báo tường minh

Java có cơ chế *target typing*: trong một số biểu thức, kiểu đích mà nơi sử dụng yêu cầu có thể giúp suy luận kiểu generic.

```java
java.util.List<String> explicit = java.util.Collections.emptyList();
var inferred = java.util.Collections.emptyList();
```

- Với `explicit`, kiểu đích `List<String>` ở bên trái giúp lời gọi `Collections.emptyList()` chọn `T = String`.
- Với `inferred`, vế trái `var` **chưa có kiểu để làm target type** cho lời gọi. Phương thức không nhận đối số nên không có thông tin xác định `T`; kết quả ở đây là `List<Object>`.

**Không được suy luận ngược từ dòng sử dụng sau đó:** thêm giá trị ở bước sau hoặc gán biến cho một nơi khác không khiến `T` của lời gọi ban đầu được tính lại.

## 3. `var` với các phương thức generic

### 3.1. Suy luận từ đối số của phương thức

Xét phương thức generic tự định nghĩa:

```java
static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
```

Trong một lớp có phương thức trên:

```java
var name = first(java.util.List.of("An", "Binh")); // String
var number = first(java.util.List.of(10, 20));      // Integer
```

Đây là **đoạn minh họa đặt bên trong cùng lớp với phương thức `first`**, không phải chương trình độc lập. Ở lời gọi thứ nhất, `List.of("An", "Binh")` có kiểu `List<String>` nên `T` của `first` là `String`. Ở lời gọi thứ hai, `T` là `Integer`, vì literal `int` được boxing khi dùng trong generic `List<Integer>`. `var` nhận kiểu trả về tương ứng.

Một số factory method chuẩn hiện hành:

| Khởi tạo | Kiểu tĩnh của biến `var` | Vì sao? |
| --- | --- | --- |
| `var names = List.of("An", "Binh");` | `List<String>` | Đối số đều là `String` |
| `var ids = List.of(10, 20);` | `List<Integer>` | Số `int` được boxing thành `Integer` khi làm phần tử |
| `var single = Optional.of("Java");` | `Optional<String>` | `T` lấy từ đối số chuỗi |
| `var byName = Map.of("An", 21);` | `Map<String, Integer>` | Suy ra kiểu khóa và giá trị |
| `var copy = new ArrayList<>(List.of("A", "B"));` | `ArrayList<String>` | Constructor nhận collection có phần tử `String` |

Các dòng bảng được xét **độc lập**; muốn biên dịch phải import các lớp tương ứng trong `java.util`.

Các factory method `List.of`, `Map.of` tạo collection **không cho phép thay đổi cấu trúc**: gọi `add` hoặc `put` sẽ thất bại lúc chạy. `var` không thay đổi tính chất đó. Ngược lại, `new ArrayList<>(...)` tạo danh sách có thể thêm/xóa phần tử.

### 3.2. Phương thức generic không có đối số xác định kiểu

```java
var empty = java.util.Collections.emptyList();         // List<Object>
var typedEmpty = java.util.Collections.<String>emptyList(); // List<String>
```

Trong lời gọi thứ hai, `<String>` là **type witness**: cung cấp đối số kiểu một cách tường minh cho phương thức generic. Đây là cách hữu ích khi lập trình viên cần chính xác `List<String>` nhưng trình biên dịch không có đủ ngữ cảnh để tự suy ra.

Một cách khác là **khai báo kiểu tường minh ở bên trái**:

```java
java.util.List<String> empty = java.util.Collections.emptyList();
```

Khi đó `List<String>` cung cấp target type cho lời gọi generic. Hãy chọn cách thể hiện ý định rõ nhất; không có yêu cầu phải dùng `var` cho mọi khai báo.

Tương tự, lời gọi `List.of()` không có phần tử được suy ra thành `List<Object>` khi đứng trong `var empty = List.of();`. Nếu cần kiểu `String`, dùng `List.<String>of()` hoặc `List<String> empty = List.of();`.

**Lưu ý quan trọng về kiểu:** `List<Object>` và `List<String>` **không tương đương**. Generic Java mặc định là *invariant*: dù `String` là kiểu con của `Object`, `List<String>` không phải kiểu con của `List<Object>` và ngược lại.

### 3.3. Lời gọi generic có đối số nhưng kiểu suy ra có thể khác dự tính

```java
var words = java.util.List.of("a", "b");  // List<String>
// words = java.util.List.of(1, 2);       // Không hợp lệ: List<Integer> không gán cho List<String>
```

Đối với tham số kiểu hỗn hợp, thuật toán suy luận có thể tìm một kiểu chung phức tạp hơn `Object`. Đừng đoán đơn giản rằng “có nhiều loại là luôn thành `List<Object>`”; khi kiểu phần tử quan trọng, hãy sử dụng type witness hoặc khai báo kiểu tường minh, chẳng hạn `List<Number> numbers = List.of(1, 2.5);`.

## 4. `var` với biểu thức `new` và toán tử diamond `<>`

### 4.1. Ghi rõ tham số kiểu khi tạo đối tượng

```java
var names = new java.util.ArrayList<String>();
```

Kiểu tĩnh của biểu thức `new ArrayList<String>()` là `ArrayList<String>`; `var` nhận đúng kiểu đó. Vì vậy:

```java
names.add("Lan"); // Hợp lệ
// names.add(10); // Lỗi biên dịch: Integer không phải String
```

`var` **không xóa thông tin generic**. Phần kiểm tra kiểu phần tử vẫn thực hiện lúc biên dịch như với `ArrayList<String> names = new ArrayList<>();`.

### 4.2. Diamond `<>` có và không có ngữ cảnh

Toán tử diamond được viết thành `<>` trong biểu thức tạo đối tượng, cho phép trình biên dịch suy ra đối số kiểu generic:

```java
java.util.List<String> a = new java.util.ArrayList<>();
var b = new java.util.ArrayList<>();
var c = new java.util.ArrayList<String>();
```

- `a`: khai báo tường minh `List<String>` cung cấp **target type**; đối số kiểu trong `new ArrayList<>()` được suy ra là `String`. Kiểu biến `a` là `List<String>`.
- `b`: dùng `var` và constructor không đối số; không có thông tin cần thiết về phần tử nên kết quả là `ArrayList<Object>`.
- `c`: biểu thức `new ArrayList<String>()` chỉ rõ `String`, nên `var` suy ra `ArrayList<String>`.

Không nên hiểu `var b = new ArrayList<>();` là “Java để kiểu trống và sẽ suy ra từ các lệnh `add` sau đó”. Kiểu `ArrayList<Object>` đã cố định từ dòng khai báo:

```java
var objects = new java.util.ArrayList<>();
objects.add("Java");
objects.add(42);           // Đều hợp lệ: loại phần tử của objects là Object
```

Nếu danh sách phải chỉ chứa chuỗi, hãy viết `var strings = new ArrayList<String>();` hoặc `List<String> strings = new ArrayList<>();`.

### 4.3. Diamond vẫn có thể suy luận từ **đối số constructor**

Không phải mọi `new SomeType<>()` dùng cùng `var` đều dẫn đến `Object`. Constructor có thể nhận đối số đủ cụ thể để suy luận kiểu generic:

```java
var copied = new java.util.ArrayList<>(
        java.util.List.of("Java", "Kotlin")
); // ArrayList<String>
```

Constructor `ArrayList(Collection<? extends E>)` nhận collection có phần tử `String`, nên `E` được suy ra `String`. `copied` là `ArrayList<String>`, có thể thêm chuỗi:

```java
copied.add("Scala");
```

Ví dụ này đối lập với constructor không đối số: chính **thông tin kiểu trong đối số constructor** làm kết quả suy luận khác nhau.

### 4.4. Kiểu suy ra có thể là lớp triển khai, không phải giao diện

```java
var a = new java.util.ArrayList<String>();                 // ArrayList<String>
java.util.List<String> b = new java.util.ArrayList<>();   // List<String>
```

Cả hai đều tạo một `ArrayList`, nhưng **kiểu tĩnh của `a` là lớp cụ thể `ArrayList<String>`**, còn `b` là giao diện `List<String>`. Khi kiến trúc yêu cầu phụ thuộc vào `List`, dòng khai báo tường minh `List<String>` giúp biểu đạt hợp đồng thiết kế rõ hơn.

## 5. Trường hợp nâng cao: generic class và generic constructor không giống nhau

Một lớp generic có tham số kiểu riêng, ví dụ `Box<T>`. Constructor thông thường của nó có thể dùng `T` trong tham số:

```java
static final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Khi khai báo **bên trong lớp bao ngoài**:

```java
var box = new Box<>("hello"); // Box<String>
var text = box.get();         // String
```

Đối số `"hello"` có kiểu `String` và constructor nhận `T`, nên diamond suy ra `T = String`. Đây là suy luận **tham số kiểu của lớp** thông qua đối số constructor.

Nhưng một constructor cũng có thể **tự khai báo tham số kiểu generic của riêng nó**, độc lập với tham số kiểu của lớp. Ví dụ minh họa:

```java
static final class Token<T> {
    <U> Token(U sample) {
        // U là tham số kiểu riêng của constructor.
    }
}

var token = new Token<>("Java"); // Token<Object>, không phải Token<String>
```

Trong tình huống `Token<T>` trên, đối số chuỗi giúp constructor suy ra `U = String`; **nó không ràng buộc tham số kiểu `T` của lớp**, nên `T` không có thông tin cụ thể và được suy ra là `Object`. Nếu cần `Token<String>`, dùng `new Token<String>("Java")` hoặc khai báo `Token<String> token = new Token<>("Java");`. Đây là **đoạn mã minh họa** đặt trong một phương thức của lớp bao ngoài có định nghĩa `Token`, không phải chương trình độc lập.

Quy tắc này giúp tránh nhầm lẫn: generic của **phương thức hoặc constructor** và generic của **lớp** có thể là các tham số khác nhau; `var` chỉ nhận kiểu của biểu thức `new` cuối cùng.

## 6. Các lỗi và cách sửa thường gặp

### Lỗi 1: Mong `var` đoán kiểu phần tử từ thao tác `add` ở phía sau

```java
var list = new java.util.ArrayList<>(); // ArrayList<Object>
list.add("A"); // Không chuyển list thành ArrayList<String>
```

**Sửa:** cung cấp kiểu ngay trong biểu thức khởi tạo, ví dụ `new ArrayList<String>()`, hoặc khai báo `List<String> list = new ArrayList<>();`.

### Lỗi 2: Nhầm phương thức generic không đối số với phương thức có kết quả `String`

```java
var items = java.util.Collections.emptyList(); // List<Object>
// java.util.List<String> strings = items;      // Lỗi: List<Object> không gán cho List<String>
```

**Sửa:** `var items = Collections.<String>emptyList();` hoặc `List<String> items = Collections.emptyList();`. Hai cách giúp Java nhận đúng ý định phần tử chuỗi.

### Lỗi 3: Quên rằng kiểu `var` là kiểu của **biểu thức**, không phải kiểu mong muốn

```java
java.util.List<String> source = new java.util.ArrayList<>();
var result = source; // List<String>, không phải ArrayList<String>
```

**Giải thích:** biến `source` có kiểu khai báo `List<String>`, nên biểu thức `source` cũng có kiểu tĩnh `List<String>`. Mặc dù đối tượng được tạo từ `ArrayList`, `var` không tự đổi kết quả thành kiểu lớp triển khai.

### Lỗi 4: Dùng kiểu nguyên thủy ở nơi generic chỉ chấp nhận kiểu tham chiếu

```java
// var invalid = new java.util.ArrayList<int>(); // Sai: generic không dùng int làm đối số kiểu
var valid = new java.util.ArrayList<Integer>();
valid.add(1); // Autoboxing int -> Integer
```

`List.of(1, 2)` có kiểu phần tử `Integer`, không phải `int`, bởi type arguments trong generic phải là kiểu tham chiếu.

### Lỗi 5: Nhầm diamond `<>` với raw type

```java
var safeGeneric = new java.util.ArrayList<String>();
var inferredGeneric = new java.util.ArrayList<>(); // ArrayList<Object>, vẫn là parameterized type
// var raw = new java.util.ArrayList();             // Raw type, nên tránh
```

`ArrayList<Object>` là một kiểu generic có đối số kiểu cụ thể; raw `ArrayList` bỏ thông tin kiểu và có thể gây cảnh báo unchecked. Khi cần generic, hãy sử dụng kiểu parameterized phù hợp thay vì raw.

### Lỗi 6: Gán trực tiếp lambda hoặc method reference vào `var`

```java
// var mapper = s -> s.trim();   // Sai: lambda không có target type
// var parse = Integer::parseInt; // Sai: method reference không có target type
```

**Sửa bằng một giao diện chức năng tường minh:**

```java
java.util.function.Function<String, String> mapper = String::trim;
java.util.function.Function<String, Integer> parse = Integer::parseInt;
```

Lambda/method reference cần ngữ cảnh kiểu giao diện chức năng; không được nhầm cơ chế này với generic method như `List.of("A")` có thể tự suy luận được kiểu kết quả.

## 7. Chương trình đầy đủ, chạy được trên Java 17+

Lưu mã dưới đây vào **`VarGenericsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class VarGenericsDemo {

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    public static void main(String[] args) {
        // Generic factory method có đối số: suy ra String.
        var languages = List.of("Java", "Kotlin"); // List<String>
        var firstLanguage = first(languages);     // String
        var number = first(List.of(10, 20));      // Integer

        // Diamond suy luận tham số generic từ đối số constructor.
        var box = new Box<>("hello");             // Box<String>
        var mutable = new ArrayList<>(languages); // ArrayList<String>
        mutable.add("Scala");

        // Không có thông tin loại phần tử trong constructor không đối số.
        var objects = new ArrayList<>();          // ArrayList<Object>
        objects.add("Java");
        objects.add(42);

        // Generic factory method không đối số: khác nhau bởi type witness.
        var inferredEmpty = Collections.emptyList();         // List<Object>
        var typedEmpty = Collections.<String>emptyList();     // List<String>

        var entries = Map.of("one", 1);          // Map<String, Integer>

        System.out.println("firstLanguage=" + firstLanguage);
        System.out.println("firstNumber=" + number);
        System.out.println("box=" + box.get());
        System.out.println("mutable=" + mutable);
        System.out.println("objects=" + objects);
        System.out.println("empty=" + inferredEmpty.size());
        System.out.println("typedEmpty=" + typedEmpty.size());
        System.out.println("mapOne=" + entries.get("one"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 VarGenericsDemo.java
java VarGenericsDemo
```

Kết quả chính xác:

```text
firstLanguage=Java
firstNumber=10
box=hello
mutable=[Java, Kotlin, Scala]
objects=[Java, 42]
empty=0
typedEmpty=0
mapOne=1
```

**Diễn giải kết quả:**

1. `first(languages)` trả về `String` vì `languages` là `List<String>`; tương tự `first(List.of(10,20))` trả về `Integer`.
2. `new Box<>("hello")` suy ra `Box<String>`; `box.get()` trả về chuỗi. `new ArrayList<>(languages)` suy ra `ArrayList<String>` nhờ đối số collection.
3. `new ArrayList<>()` không có thông tin về phần tử nên suy ra `ArrayList<Object>`. Danh sách này có thể chứa cả chuỗi và `Integer`; việc đó **không chứng tỏ `var` là kiểu động**.
4. Hai lời gọi `Collections.emptyList()` không có phần tử nên cùng có kích thước 0, nhưng kiểu tĩnh khác nhau: `List<Object>` và `List<String>` nhờ type witness.
5. `Map.of("one", 1)` suy ra `Map<String, Integer>`; truy cập khóa `"one"` cho giá trị `1`.

Ví dụ chỉ dùng các tính năng/API còn hỗ trợ trong Java 17 trở lên; không cần bật preview.

## 8. Chọn giữa `var` và kiểu tường minh trong mã thực tế

**Dùng `var` khi biểu thức thể hiện rõ kiểu và ý đồ:**

```java
var names = List.of("An", "Binh"); // List<String>
var queue = new ArrayList<String>(); // ArrayList<String>
var copy = new ArrayList<>(names);  // ArrayList<String>
```

Trong một khối có import `java.util.List` và `java.util.ArrayList`, các dòng này là các khai báo hợp lệ và đọc khá tự nhiên.

**Chọn kiểu tường minh khi cần truyền đạt hợp đồng giao diện hoặc tránh suy luận `Object` không chủ ý:**

```java
List<String> names = new ArrayList<>();
List<String> empty = Collections.emptyList();
```

Nếu muốn vừa giữ `var` vừa chỉ rõ type argument, dùng `new ArrayList<String>()` hoặc type witness như `Collections.<String>emptyList()`.

Tự rà soát bằng ba câu hỏi:

1. **Kiểu tĩnh của toàn biểu thức khởi tạo là gì?** Kiểu trả về khai báo của phương thức có thể khác lớp thực tế được tạo.
2. **Generic argument đã có đủ thông tin để suy luận chưa?** Constructor rỗng và factory generic không đối số có thể cho `Object`.
3. **Kiểu được suy ra có diễn đạt đúng API/hợp đồng thiết kế không?** Nếu cần giao diện `List<String>`, khai báo tường minh có thể rõ hơn kiểu lớp cụ thể `ArrayList<String>`.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** `var a = List.of("A", "B");` cho kiểu gì? `var b = List.of();` cho kiểu gì khi đứng độc lập?

**Đáp án:** `a` là `List<String>`; `b` là `List<Object>` vì không có đối số lẫn target type cụ thể.

**Câu 2.** Hai khai báo `var a = new ArrayList<>();` và `var b = new ArrayList<>(List.of("x"));` khác nhau thế nào?

**Đáp án:** `a` là `ArrayList<Object>`; `b` là `ArrayList<String>` vì constructor nhận collection có phần tử `String`.

**Câu 3.** `var empty = Collections.emptyList();` có thể dùng trực tiếp ở nơi bắt buộc `List<String>` không?

**Đáp án:** Không, vì `empty` được suy ra là `List<Object>`; Java generic invariant. Cần khai báo `List<String> empty = Collections.emptyList();` hoặc `var empty = Collections.<String>emptyList();`.

**Câu 4.** Vì sao `var box = new Box<>("hello");` có thể là `Box<String>`?

**Đáp án:** Khi `Box<T>` có constructor `Box(T value)`, đối số `"hello"` cung cấp thông tin xác định `T = String`.

**Câu 5.** Dùng `var mapper = String::trim;` có hợp lệ không?

**Đáp án:** Không. Method reference cần target type là functional interface. Hãy khai báo `Function<String, String> mapper = String::trim;`.

## 10. Ghi nhớ

- **Suy luận kiểu cho generic method/constructor xảy ra khi định kiểu biểu thức bên phải**; sau đó `var` nhận kiểu biểu thức đó.
- `var` **không cung cấp target type tường minh** như `List<String> x = ...`; với factory không đối số hoặc diamond không đủ ngữ cảnh, generic parameter có thể được suy ra là `Object`.
- Generic method có đối số thường suy ra tham số kiểu từ đối số (`List.of("A")` → `List<String>`); type witness như `Collections.<String>emptyList()` giúp ghi rõ ý định khi thiếu thông tin.
- `new ArrayList<String>()` đi với `var` cho `ArrayList<String>`. `new ArrayList<>()` không đối số cho `ArrayList<Object>`, trong khi `new ArrayList<>(List.of("A"))` có thể cho `ArrayList<String>`.
- Tránh raw types và ghi kiểu tường minh khi cần hợp đồng giao diện; `var` không loại bỏ kiểm tra generic lúc biên dịch.

## Tài liệu tham khảo chính thức

- OpenJDK JEP 286 — Local-Variable Type Inference (Java 10): https://openjdk.org/jeps/286
- OpenJDK Project Amber — Local Variable Type Inference FAQ: https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md
- Dev.java — Type Inference with Generics: https://dev.java/learn/generics/type-inference/
- Dev.java — Using the Var Type Identifier: https://dev.java/learn/language-basics/using-var/
- Java Language Specification (Java SE 25), `15.9 — Class Instance Creation Expressions; `15.12 — Method Invocation Expressions; `18 — Type Inference: https://docs.oracle.com/javase/specs/jls/se25/html/index.html
