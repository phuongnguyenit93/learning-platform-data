# Truyền đối số kiểu và tạo đối tượng kiểu tham số hóa trong Java Generics

Khi sử dụng **Java Generics**, ta có thể viết một lớp hay interface dùng chung cho nhiều kiểu dữ liệu, sau đó **truyền đối số kiểu** (`type argument`) vào nơi sử dụng. Ví dụ `Box<String>` biểu thị một `Box` mang giá trị kiểu `String`, còn `Box<Integer>` biểu thị một `Box` mang giá trị kiểu `Integer`. Trình biên dịch dựa vào đối số kiểu để kiểm tra phép gán, lời gọi phương thức và kiểu dữ liệu được trả về.

Bài này hướng dẫn cú pháp truyền đối số kiểu, cách tạo đối tượng với hoặc không có **diamond operator** (`<>`), cách Java suy luận kiểu dựa trên ngữ cảnh và các lỗi thường gặp khi khởi tạo generic.

## 1. Phân biệt tham số kiểu và đối số kiểu

Xét khai báo lớp:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Ở đây:

- `Box` là tên lớp generic.
- `T` là **tham số kiểu** (`type parameter`), được khai báo bên trong `<T>`; nó là tên đại diện cho một kiểu tham chiếu mà nơi sử dụng sẽ chỉ định.
- `Box<String>` là một **kiểu được tham số hóa** (`parameterized type`), trong đó `String` là **đối số kiểu** (`type argument`) cụ thể truyền vào vị trí `T`.
- `Box<Integer>` là cách sử dụng khác của cùng khai báo `Box<T>`, với `T` tương ứng `Integer`.

Cú pháp tổng quát:

```java
class Container<T> { /* khai báo sử dụng T */ }

// Ví dụ đặt trong một phương thức:
Container<String> textContainer;    // Truyền đối số kiểu String
Container<Integer> numberContainer; // Truyền đối số kiểu Integer
```

Phần `<T>` xuất hiện **khi khai báo** generic; `<String>` hoặc `<Integer>` xuất hiện **khi sử dụng** generic. Đây là hai vai trò khác nhau, dù cùng dùng dấu ngoặc nhọn `<...>`.

Có thể khai báo nhiều tham số kiểu, phân biệt bằng dấu phẩy:

```java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
```

Khi dùng `Pair<String, Integer>`, tham số `K` được gắn với `String`, còn `V` với `Integer`. **Thứ tự đối số kiểu phải tương ứng thứ tự tham số kiểu** trong khai báo. Tên `T`, `K`, `V` là quy ước dễ đọc; trình biên dịch không yêu cầu dùng đúng các chữ cái này.

## 2. Cú pháp đầy đủ khi tạo đối tượng generic

Một đối tượng `Box<String>` có thể được tạo bằng cách nêu đối số kiểu trong cả khai báo biến lẫn biểu thức `new`:

```java
Box<String> title = new Box<String>("java");
```

Cách đọc:

1. `Box<String>` ở bên trái khai báo **kiểu của biến tham chiếu** `title`.
2. `new Box<String>("java")` ở bên phải gọi constructor của `Box` và chỉ định đối số kiểu `String` cho đối tượng được tạo.
3. `"java"` là giá trị constructor nhận; vì `T` được chỉ định là `String`, nó phù hợp với tham số constructor kiểu `T`.
4. `title.get()` có kiểu biểu thức `String` theo kiểm tra kiểu lúc biên dịch, nên gọi được `toUpperCase()` trực tiếp.

Đối số kiểu được truyền vào **kiểu generic**; nó không phải tham số giá trị của constructor. Ví dụ `new Box<String>("java")` có **đối số kiểu** `String` và **đối số constructor** là chuỗi `"java"`.

Nếu lớp định nghĩa constructor không nhận đối số, ta có thể dùng `new ClassName<Type>()`; nếu constructor yêu cầu tham số, phải cung cấp các đối số giá trị tương ứng. Generics không tự tạo constructor hay bỏ qua các ràng buộc constructor.

### Ví dụ Java 17 chạy đầy đủ

Lưu chương trình sau thành `TypeArgumentsDemo.java`:

```java
public class TypeArgumentsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class Pair<K, V> {
        private final K key;
        private final V value;

        Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() {
            return key;
        }

        V value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> title = new Box<String>("java");
        Box<Integer> quantity = new Box<Integer>(3);
        Pair<String, Integer> version = new Pair<String, Integer>("JDK", 17);

        System.out.println(title.get().toUpperCase());
        System.out.println(quantity.get() + 2);
        System.out.println(version.key() + " " + version.value());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TypeArgumentsDemo.java
java TypeArgumentsDemo
```

Kết quả chuẩn (`stdout`):

```text
JAVA
5
JDK 17
```

Trong `Box<Integer>`, tham số kiểu dùng `Integer` (lớp bao của `int`). Java tự đóng hộp số `3` thành `Integer` khi truyền constructor và tự mở hộp khi thực hiện phép cộng trong `quantity.get() + 2`. Kiểu `Pair<String, Integer>` giúp trình biên dịch kiểm tra lần lượt hai đối số của constructor.

## 3. Dùng diamond operator `<>` để Java tự suy luận đối số kiểu

Kể từ Java 7, khi tạo đối tượng generic, ta thường có thể thay phần đối số kiểu phía sau `new` bằng **diamond** `<>`:

```java
Box<String> title = new Box<>("java");
Box<Integer> quantity = new Box<>(3);
Pair<String, Integer> version = new Pair<>("JDK", 17);
```

Ba biểu thức trên mang cùng ý định kiểu với cách viết tường minh trong ví dụ trước. Diamond yêu cầu trình biên dịch **suy luận** đối số kiểu dựa trên thông tin có sẵn, bao gồm kiểu đích (`target type`) và kiểu đối số constructor.

So sánh:

| Viết tường minh | Dùng diamond | Kết quả cần diễn đạt |
|---|---|---|
| `new Box<String>("java")` | `new Box<>("java")` | Khởi tạo `Box<String>` trong ngữ cảnh phù hợp |
| `new Box<Integer>(3)` | `new Box<>(3)` | Khởi tạo `Box<Integer>` trong ngữ cảnh phù hợp |
| `new Pair<String, Integer>("JDK", 17)` | `new Pair<>("JDK", 17)` | Khởi tạo `Pair<String, Integer>` trong ngữ cảnh phù hợp |

**Diamond chỉ viết `<>`, không phải `<T>`.** Trong `new Box<>()`, Java có trách nhiệm suy luận đối số kiểu; trong `new Box<String>()`, lập trình viên chỉ định `String` trực tiếp.

Diamond giảm lặp thông tin và thường được ưu tiên khi kết quả suy luận đúng với hợp đồng mong muốn. Có những ngữ cảnh thiếu thông tin hoặc đối số constructor phức tạp làm kiểu suy luận rộng hơn mong đợi; khi đó khai báo kiểu rõ ràng giúp kiểm soát tốt hơn.

## 4. Kiểu biến ở bên trái có thể quyết định kiểu suy luận ở bên phải

Xem khai báo collection:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
String firstName = names.get(0);
```

Đây là **đoạn mã minh họa nằm trong thân một phương thức**; cần các import như trên. `List<String>` là kiểu được tham số hóa của **interface** `List`; `ArrayList` là lớp triển khai được khởi tạo. Trình biên dịch suy luận `String` cho `new ArrayList<>()` nhờ kiểu đích `List<String>`.

Lợi ích thực tế:

- API của biến `names` thể hiện danh sách chỉ nhận phần tử `String` qua các thao tác được kiểm tra kiểu.
- Khi gọi `names.add("An")`, giá trị hợp lệ vì là `String`.
- Khi gọi `names.get(0)`, kiểu biểu thức là `String`; không cần viết `(String)`.
- Nếu thêm `names.add(42)`, trình biên dịch sẽ báo lỗi vì `int` được đóng hộp thành `Integer`, không phù hợp tham số kiểu `String`.

Vì `List` là interface nên không thể viết `new List<String>()` trực tiếp; phải chọn một lớp triển khai, ví dụ `ArrayList`. Cú pháp tham số hóa của biến và cú pháp khởi tạo thuộc hai vị trí độc lập: biến có thể khai báo bằng interface, còn đối tượng được tạo từ lớp triển khai.

### Ví dụ với kiểu lồng nhau

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

// Đặt bên trong một phương thức:
Map<String, List<Integer>> scores = new HashMap<>();
scores.put("Java", new ArrayList<>());
scores.get("Java").add(10);
```

Ở đây `Map<String, List<Integer>>` có hai đối số kiểu ở lớp ngoài: khóa `String` và giá trị `List<Integer>`. `List<Integer>` lại là một kiểu được tham số hóa. Dấu `>>` cuối khai báo đóng hai cặp ngoặc góc lồng nhau; trong Java hiện đại, không cần thêm khoảng trắng để phân tách chúng.

Đừng nhầm các loại ngoặc:

- `<String, Integer>`: đối số **kiểu**.
- `("Java", 17)`: đối số **giá trị** của constructor/phương thức.
- `<>`: diamond để **suy luận** đối số kiểu khi khởi tạo.

## 5. `var` kết hợp với diamond: nhận diện kiểu suy luận

`var` để compiler suy luận **kiểu tĩnh của biến cục bộ** từ initializer. Nếu initializer là một constructor generic rỗng với diamond và không có target type cụ thể, suy luận có thể cho kiểu phần tử `Object`:

```java
List<String> a = new ArrayList<>();     // Target type cho phép suy luận String.
var b = new ArrayList<>();              // b có kiểu ArrayList<Object>.
var c = new ArrayList<String>();        // c có kiểu ArrayList<String>.
```

Khác biệt quan trọng: `ArrayList<Object>` vẫn là **parameterized type**, không phải raw `ArrayList`. `var` không khiến biến trở thành kiểu động. Khi lời gọi cần phần tử String, ưu tiên viết `List<String> names = new ArrayList<>();` hoặc `var names = new ArrayList<String>();`. Phân tích sâu về diamond/var, cảnh báo raw và ví dụ heap pollution thuộc bài chuyên về toán tử diamond.

## 6. Truyền đối số kiểu cho phương thức generic

Đối số kiểu cũng có thể được truyền khi gọi **phương thức generic**. Trong khai báo phương thức, danh sách tham số kiểu `<T>` đứng **trước kiểu trả về**:

```java
static <T> T echo(T value) {
    return value;
}
```

Khi gọi, Java thường suy luận `T` từ đối số giá trị và kiểu đích:

```java
String result = echo("Java");
```

Cũng có thể chỉ định đối số kiểu **tường minh** bằng cú pháp `ClassName.<Type>method(...)`:

```java
String result = TypeMethodDemo.<String>echo("Java");
```

Trong lời gọi phương thức generic, `<String>` xuất hiện **ngay trước tên phương thức**, không phải sau `new`. Đây là cú pháp khác diamond của biểu thức khởi tạo constructor.

Ví dụ chạy đầy đủ, lưu thành `TypeMethodDemo.java`:

```java
public class TypeMethodDemo {
    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        String inferred = echo("Java");
        String explicit = TypeMethodDemo.<String>echo("JDK");

        System.out.println(inferred);
        System.out.println(explicit);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 TypeMethodDemo.java
java TypeMethodDemo
```

`stdout`:

```text
Java
JDK
```

Thông thường nên để trình biên dịch suy luận đối số kiểu cho phương thức khi ý định đã rõ. Cú pháp chỉ định tường minh hữu ích khi muốn làm rõ một kiểu cụ thể hoặc xử lý một tình huống suy luận khó.

**Một lưu ý quan trọng:** tham số kiểu của lớp và tham số kiểu của phương thức là hai khai báo riêng biệt. Một phương thức `static` không thể trực tiếp sử dụng `T` chỉ khai báo trên `class Box<T>`; nó phải tự khai báo tham số kiểu, ví dụ `static <U> U identity(U value)`.

## 7. Những điều kiện đối số kiểu phải đáp ứng

### 7.1. Đối số kiểu phải là kiểu tham chiếu

Java Generics không chấp nhận kiểu nguyên thủy (`primitive type`) làm đối số kiểu:

```java
Box<int> counter;       // Sai: int không phải kiểu tham chiếu
Box<Integer> counter2;  // Đúng: Integer là kiểu tham chiếu
```

Các cặp thường dùng gồm `int`/`Integer`, `long`/`Long`, `double`/`Double` và `boolean`/`Boolean`. Autoboxing/unboxing cho phép mã tiện dụng, nhưng không làm `Box<int>` trở nên hợp lệ.

### 7.2. Đối số kiểu phải phù hợp với giới hạn (`bound`) nếu có

Giả sử một lớp khai báo:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T extends Number` yêu cầu đối số kiểu là `Number` hoặc kiểu con của `Number`. Bởi vậy:

```java
NumberBox<Integer> integers = new NumberBox<>(5); // Đúng
NumberBox<Double> decimals = new NumberBox<>(1.5); // Đúng
// NumberBox<String> text = new NumberBox<>("x"); // Sai: String không extends Number
```

Đây là **đoạn mã minh họa**, cần đặt trong thân phương thức cùng khai báo `NumberBox` ở trên. Kiểu được suy luận qua diamond vẫn phải đáp ứng giới hạn đã khai báo.

### 7.3. Generic mặc định bất biến (`invariant`)

Ngay cả khi `Integer` là kiểu con của `Number`, hai kiểu tham số hóa sau **không** có quan hệ kiểu con theo cùng chiều:

```java
// List<Number> numbers = new ArrayList<Integer>(); // Sai: không tương thích
```

Nếu lập trình viên cần làm việc với một nhóm kiểu có quan hệ cha–con, wildcard như `? extends Number` hoặc `? super Integer` có thể phù hợp, nhưng có quy tắc đọc/ghi riêng. Không nên thay `<Integer>` bằng `<Number>` hay giả định có thể gán tùy ý chỉ vì hai kiểu đối số liên quan kế thừa.

### 7.4. Không thể suy luận đúng một kiểu từ mọi ngữ cảnh

Diamond dùng dữ kiện của chương trình, không biết ý định nghiệp vụ. Nếu các dữ kiện chỉ cho phép suy luận `Object`, chương trình có thể hợp lệ nhưng mất ràng buộc mong muốn. Tốt nhất là viết kiểu đích đủ rõ ở ranh giới API và kiểm tra cảnh báo trình biên dịch.

## 8. Phân biệt kiểu tham số hóa với raw type khi tạo object

`Box<String> value = new Box<>("Java")` dùng generic type argument `String` và diamond suy luận kiểu; còn `Box raw = new Box("Java")` cố ý bỏ type argument để tương thích mã cũ. Raw type có thể khiến compiler phát `rawtypes` hoặc `unchecked` warnings và mất kiểm tra phần tử ở những thao tác tiếp theo. Đừng đánh đồng **raw type** với `Box<?>`: wildcard vẫn là cách biểu diễn an toàn kiểu rằng type argument chưa biết.

```java
Box<String> safe = new Box<>("Java");
Box<?> unknown = safe;
// Box<?> không cho phép tự đặt một giá trị String tùy ý
// nếu phương thức Box có setter nhận chính type parameter T.
```

Dù khai báo `Box<String>`, JVM thông thường không tạo riêng một runtime class `Box<String>`; đây là hiệu ứng **type erasure**, không phải lý do để dùng raw types. Chi tiết diamond vs raw, cảnh báo và cách chuyển dữ liệu legacy được học sâu ở bài chuyên tiếp theo.

## 9. Các lỗi cú pháp và thiết kế phổ biến

| Viết sai hoặc dễ gây hiểu nhầm | Vấn đề | Cách sửa |
|---|---|---|
| `new Box<T>("x")` trong mã không hề khai báo `T` | `T` không tự động đại diện cho bất kỳ kiểu nào trong mọi phạm vi. | Dùng `new Box<String>("x")` hoặc `new Box<>("x")` khi ngữ cảnh đủ rõ. |
| `Box<int> b` | Kiểu primitive không được làm đối số generic. | `Box<Integer> b`. |
| `Box<String> b = new Box<>(123)` | Đối số constructor không tương thích với kiểu đích `String`. | Truyền một `String` hoặc đổi hợp đồng thành kiểu thực sự cần. |
| `Box<String> b = new Box<Integer>(123)` | Hai kiểu tham số hóa không tương thích. | Dùng đối số kiểu thống nhất ở hai phía. |
| `List<String> x = new List<>()` | `List` là interface, không thể tạo trực tiếp. | `List<String> x = new ArrayList<>();`. |
| `var x = new ArrayList<>()` nhưng mong chỉ chứa chuỗi | Kiểu suy luận là `ArrayList<Object>`, cho phép nhiều loại phần tử. | Viết `var x = new ArrayList<String>()` hoặc `List<String> x = new ArrayList<>();`. |
| `Box b = new Box("x")` | Raw type bỏ kiểm tra tham số kiểu; có thể xuất hiện cảnh báo. | `Box<String> b = new Box<>("x");`. |
| Cố dùng `Box<String>` làm kiểu con của `Box<Object>` | Generic bất biến. | Thiết kế API đúng kiểu; cân nhắc wildcard nếu cần. |

Các dòng minh họa lỗi biên dịch trong bảng dùng để **nhận diện và sửa lỗi**, không phải mã nguồn để chạy nguyên trạng.

## 10. Quy trình áp dụng trong code thực tế

Khi cần tạo một đối tượng generic, hãy kiểm tra lần lượt:

1. **Xác định hợp đồng kiểu:** dữ liệu phải là `String`, `Integer`, một kiểu domain như `Order`, hay một cặp `K, V`?
2. **Đọc khai báo generic:** lớp/interface có bao nhiêu tham số kiểu, theo thứ tự nào và có giới hạn `extends` gì không?
3. **Đặt kiểu đích dễ đọc:** ví dụ `List<Order> orders` hoặc `Box<String> label`. Ưu tiên interface làm kiểu biến khi thiết kế API phù hợp.
4. **Khởi tạo bằng constructor đúng:** `new ArrayList<>()`, `new Box<>("Java")` hay `new Pair<>("key", 10)`. Diamond nên được chọn khi trình biên dịch có thể suy luận kiểu mong muốn.
5. **Tránh raw type và ép kiểu không được kiểm tra:** xem cảnh báo `-Xlint:rawtypes,unchecked` khi tích hợp mã cũ; đừng dùng raw type để né lỗi generic.
6. **Xem lại suy luận khi dùng `var`:** với constructor rỗng và diamond, viết rõ đối số kiểu phía sau `new` nếu cần kiểu hẹp hơn `Object`.

Một mẫu dễ đọc, thường gặp trong dự án Java:

```java
// Trong một phương thức, đã import List và ArrayList:
List<String> tags = new ArrayList<>();
tags.add("generics");

Box<String> label = new Box<>("Java");
String text = label.get();
```

Trong ví dụ cuối, `tags` dùng kiểu interface `List<String>` nhưng đối tượng là `ArrayList<String>`; `label` và đối tượng `Box` có cùng đối số kiểu `String`. Các kiểu được kiểm tra ngay khi biên dịch, giúp phát hiện sớm việc truyền sai dữ liệu.

## 11. Tự kiểm tra

**Câu 1.** Trong `Pair<String, Integer> pair = new Pair<>("A", 1);`, đâu là tham số kiểu, đâu là đối số kiểu, đâu là đối số constructor?

**Câu 2.** Tại sao `List<String> words = new ArrayList<>();` đúng nhưng `List<String> words = new List<>();` sai?

**Câu 3.** Hai biến dưới đây có cùng kiểu không?

```java
var a = new ArrayList<>();
var b = new ArrayList<String>();
```

**Câu 4.** Cách khai báo nào hợp lệ cho số nguyên: `Box<int>` hay `Box<Integer>`? Tại sao?

**Gợi ý đáp án:** (1) `K` và `V` là tham số kiểu ở khai báo `Pair<K,V>`; `String` và `Integer` là đối số kiểu; `"A"` và `1` là đối số constructor. (2) `List` là interface, `ArrayList` là lớp có thể khởi tạo. (3) Không; `a` thường là `ArrayList<Object>` còn `b` là `ArrayList<String>`. (4) `Box<Integer>` vì generic nhận kiểu tham chiếu, không nhận primitive `int`.

**Điểm cần nhớ:** Hãy khai báo đối số kiểu để diễn đạt rõ hợp đồng dữ liệu; dùng `new GenericClass<Type>(...)` khi muốn chỉ định tường minh và `new GenericClass<>(...)` khi suy luận kiểu đủ rõ. Khi dùng `var`, constructor rỗng, raw type hoặc generic có giới hạn, cần kiểm tra kỹ kiểu mà trình biên dịch thực sự xác định.
