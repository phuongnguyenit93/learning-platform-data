# Suy luận kiểu với đối số generic được ghi tường minh khi dùng `var` (Java 10+)

## 1. Ý tưởng cốt lõi

Trong Java 10 trở lên, `var` cho phép khai báo **biến cục bộ** mà không cần viết kiểu ở phía trái dấu `=`. Trình biên dịch suy ra kiểu tĩnh của biến từ **kiểu của toàn bộ biểu thức khởi tạo**. Khi biểu thức là một lời gọi tạo đối tượng hoặc phương thức generic, các **đối số kiểu (type arguments)** được ghi tường minh bên trong biểu thức có thể quyết định chính xác kiểu mà `var` nhận.

```java
var names = new ArrayList<String>();          // ArrayList<String>
var ids = new HashMap<String, Integer>();     // HashMap<String, Integer>
var emptyNames = Collections.<String>emptyList(); // List<String>
```

Các dòng này cần các import thích hợp từ `java.util`. Sau khi suy luận xong, `names`, `ids` và `emptyNames` là các biến **có kiểu tĩnh cố định**. `var` không biến Java thành ngôn ngữ kiểu động, cũng không làm mất kiểm tra kiểu của generic.

Trong bài này, cần phân biệt:

- **Type parameter** (tham số kiểu): tên hình thức như `T`, `E`, `K` và `V` do lớp hoặc phương thức generic khai báo, chẳng hạn `class Box<T>`.
- **Explicit type argument** (đối số kiểu tường minh): kiểu thực tế truyền vào như `String`, `Integer` trong `new ArrayList<String>()` hoặc `Collections.<String>emptyList()`.
- **Type inference** (suy luận kiểu): quá trình trình biên dịch tìm ra kiểu còn thiếu, trong đó có kiểu của biến `var` và các type argument bị lược bỏ.

Đối số kiểu tường minh giúp trình biên dịch có thông tin chính xác ngay trong biểu thức, đặc biệt khi biểu thức generic không có giá trị đầu vào đủ cụ thể để tự suy luận.

## 2. Ghi rõ đối số kiểu của **lớp generic** khi tạo đối tượng

Với biểu thức `new Class<TypeArgument>(...)`, dấu `<...>` sau tên lớp chỉ rõ kiểu cho **generic class**:

```java
var names = new ArrayList<String>();             // ArrayList<String>
var ages = new HashMap<String, Integer>();       // HashMap<String, Integer>
var groups = new ArrayList<List<String>>();      // ArrayList<List<String>>
```

Giả sử có `import java.util.*;`. Những khai báo dùng `var` tương đương về kiểu tĩnh với:

```java
ArrayList<String> names = new ArrayList<String>();
HashMap<String, Integer> ages = new HashMap<String, Integer>();
ArrayList<List<String>> groups = new ArrayList<List<String>>();
```

Lợi ích: phần bên trái không phải lặp lại kiểu generic dài, còn type argument của biểu thức vẫn rõ ràng. Trình biên dịch vẫn kiểm tra:

```java
var names = new ArrayList<String>();
names.add("An");      // hợp lệ
// names.add(42);     // lỗi biên dịch: Integer không phù hợp String
String first = names.get(0); // không cần cast
```

Hãy chú ý **kiểu chính xác** của biến: `var names = new ArrayList<String>()` tạo biến kiểu `ArrayList<String>`, chứ không tự nâng kiểu lên interface `List<String>`. Khi cần dùng hợp đồng interface để dễ thay đổi implementation, khai báo tường minh thường rõ ý hơn:

```java
List<String> names = new ArrayList<>();
names = new LinkedList<>(); // hợp lệ vì cả hai đều là List<String>
```

Ngược lại, với `var names = new ArrayList<String>()`, việc gán trực tiếp một `LinkedList<String>` cho `names` sẽ sai kiểu vì biến được suy luận là `ArrayList<String>`.

## 3. So sánh đối số kiểu tường minh với toán tử diamond `<>`

Diamond `<>` yêu cầu trình biên dịch suy ra type argument thay vì ghi nó ra. Sự khác biệt thể hiện rõ khi khai báo bên trái bằng `var`:

| Khai báo | Kiểu tĩnh của biến | Giải thích |
| --- | --- | --- |
| `var a = new ArrayList<String>();` | `ArrayList<String>` | `String` được ghi tường minh. |
| `var b = new ArrayList<>();` | `ArrayList<Object>` | Không có ràng buộc nào khác cho `E`, suy ra `Object`. |
| `var c = new ArrayList<>(List.of("A", "B"));` | `ArrayList<String>` | Đối số constructor là `Collection<String>`, cung cấp thông tin suy luận. |
| `List<String> d = new ArrayList<>();` | `List<String>` | Kiểu đích bên trái hỗ trợ suy luận diamond; biến được khai báo là `List<String>`. |
| `var e = new HashMap<String, Integer>();` | `HashMap<String, Integer>` | `K` và `V` được ghi rõ. |
| `var f = new HashMap<>();` | `HashMap<Object, Object>` | Không có thông tin để chọn `K`, `V` cụ thể. |

Ví dụ dễ nhầm:

```java
var values = new ArrayList<>(); // ArrayList<Object>
values.add("hello");
values.add(10);                 // vẫn hợp lệ vì E là Object
```

Lệnh `add("hello")` **không khiến kiểu đã suy luận trước đó chuyển từ `Object` sang `String`**. Kiểu được xác định một lần khi khai báo, không suy luận lại theo các phép gán hoặc lời gọi sau đó.

Hai cách giúp có `ArrayList<String>`:

```java
var values1 = new ArrayList<String>();           // chỉ rõ type argument
var values2 = new ArrayList<>(List.of("hello")); // constructor có đối số đủ thông tin
```

**Đừng khái quát rằng cứ có `var` và diamond là nhận `Object`**: constructor có thể cung cấp ràng buộc kiểu từ đối số; chỉ khi thiếu thông tin suy luận thì kết quả mới thường là `Object` hoặc một kiểu giới hạn khác theo khai báo generic.

## 4. Ghi rõ đối số kiểu của **phương thức generic** (type witness)

Ngoài lớp generic, phương thức generic cũng khai báo tham số kiểu của riêng nó. Khi cần ghi tường minh đối số kiểu tại vị trí gọi phương thức, đặt `<Kiểu>` **ngay trước tên phương thức**, sau tên lớp/đối tượng và dấu chấm.

```java
var emptyStrings = Collections.<String>emptyList(); // List<String>
var emptyNumbers = List.<Integer>of();              // List<Integer>
var noValue = Optional.<Long>empty();                // Optional<Long>
var noStrings = Set.<String>of();                    // Set<String>
```

Cú pháp quan trọng là `Collections.<String>emptyList()`, không phải `Collections.emptyList<String>()`. Trong Java, type witness cho một **method invocation** được viết trước tên phương thức.

Ví dụ một phương thức generic đơn giản:

```java
static <T> List<T> one(T value) {
    return List.of(value);
}

// Trong phương thức khác:
var a = one("Java");         // List<String>, suy ra T từ đối số String
var b = MyClass.<Number>one(7); // List<Number>, type witness chọn T = Number
```

Ở ví dụ này, `MyClass` là tên lớp chứa phương thức `static one`; đoạn mã mang tính minh họa và chưa phải một chương trình độc lập. Giá trị `7` được boxing thành `Integer` và phù hợp với tham số `Number`.

Với những phương thức **không có đối số truyền vào để suy ra `T`**, việc ghi type witness rất có ích:

```java
var a = Collections.emptyList();            // List<Object>
var b = Collections.<String>emptyList();    // List<String>

var c = List.of();                          // List<Object>
var d = List.<String>of();                  // List<String>

var e = Optional.empty();                   // Optional<Object>
var f = Optional.<Integer>empty();          // Optional<Integer>
```

Hai danh sách rỗng `a` và `b` có cùng số phần tử (0), nhưng **khác kiểu tĩnh**. Khi biên dịch, `b` là `List<String>` còn `a` là `List<Object>`; `var` không dự đoán rằng về sau bạn sẽ muốn chứa chuỗi.

Một phương thức có đối số có thể tự suy ra kiểu mà không cần type witness:

```java
var words = List.of("A", "B");         // List<String>
var number = Optional.of(10);         // Optional<Integer>
var scores = Map.of("An", 9);         // Map<String, Integer>
```

Viết tường minh `List.<String>of("A", "B")` vẫn hợp lệ nhưng thường dư thừa nếu các đối số đã nói rõ kiểu. Type witness hữu ích nhất khi bạn cần một kiểu khác với suy luận mặc định, hoặc muốn thể hiện ràng buộc một cách chủ động.

## 5. Vì sao `var` khác khai báo có kiểu đích ở bên trái?

So sánh hai khai báo sau:

```java
List<String> assigned = Collections.emptyList(); // List<String>
var inferred = Collections.emptyList();          // List<Object>
```

Với `assigned`, kiểu đích `List<String>` bên trái là một phần ngữ cảnh có thể ảnh hưởng quá trình suy luận lời gọi phương thức generic. Với `inferred`, biểu thức khởi tạo được xác định kiểu **không có target type đến từ một kiểu biến tường minh ở bên trái**. Không có đầu vào cụ thể cho `T`, trình biên dịch chọn `Object`.

Thay vì phải viết cả kiểu biến, có thể đặt thông tin ở biểu thức khởi tạo:

```java
var inferred = Collections.<String>emptyList(); // List<String>
```

Tương tự với diamond:

```java
List<String> declared = new ArrayList<>(); // List<String>
var noContext = new ArrayList<>();         // ArrayList<Object>
var explicit = new ArrayList<String>();    // ArrayList<String>
```

Nhưng không phải **mọi** generic method đều phải ghi type witness khi dùng `var`. Nếu phương thức nhận đối số cung cấp thông tin kiểu, trình biên dịch vẫn suy luận tốt:

```java
var copy = new ArrayList<>(List.of("A", "B")); // ArrayList<String>
var list = List.of("A", "B");                  // List<String>
```

**Quy trình đọc mã chính xác:** trước hết xác định kiểu của lời gọi `new`/generic method ở bên phải (dựa vào type argument tường minh và các ràng buộc suy luận); sau đó `var` nhận kiểu tĩnh đó. Không suy kiểu của biến từ dự định sử dụng nó ở những dòng tiếp theo.

## 6. Type witness có thể chủ động chọn kiểu rộng hơn

Generic method có thể nhận type argument rộng hơn kiểu lớp cụ thể của giá trị truyền vào, miễn thỏa ràng buộc của phương thức:

```java
var oneInteger = Collections.singletonList(7);         // List<Integer>
var oneNumber = Collections.<Number>singletonList(7); // List<Number>
```

Ở dòng thứ hai, `T` được chỉ rõ là `Number`; giá trị `7` được boxing thành `Integer` và có thể truyền cho tham số kiểu `Number`. Biến `oneNumber` vì thế có kiểu `List<Number>`. Không có chuyện Java đổi lớp runtime của đối tượng `Integer` thành một lớp `Number`; đây là **quan hệ kiểu tĩnh** của danh sách.

Tuy nhiên, explicit type argument phải **phù hợp với bounds và tham số** của API:

```java
// var bad1 = Collections.<String>singletonList(7);
// sai: 7 (Integer sau boxing) không thể dùng như String

// var bad2 = new ArrayList<int>();
// sai: type argument của generic phải là reference type, không dùng primitive int

var correct1 = Collections.<Integer>singletonList(7);
var correct2 = new ArrayList<Integer>();
```

Sử dụng `Integer` thay vì `int` khi cần kiểu phần tử generic. Khi phương thức khai báo bound, ví dụ `<T extends Number>`, một type witness `String` sẽ bị từ chối vì không thỏa bound.

## 7. Những điều đối số generic tường minh **không** thay đổi

### Không tự chuyển kiểu generic khác nhau

Generic trong Java có tính **invariance**: `List<String>` không phải subtype của `List<Object>`.

```java
var strings = List.<String>of("A", "B"); // List<String>
// List<Object> objects = strings;     // lỗi biên dịch
List<?> readable = strings;            // hợp lệ khi cần đọc không phụ thuộc kiểu phần tử
```

Nếu cần danh sách của `Object`, hãy thiết kế ngay từ kiểu biểu thức, ví dụ `var objects = new ArrayList<Object>();`; đừng ép nhận nhầm rằng `List<String>` là `List<Object>`.

### Không biến collection bất biến thành collection có thể sửa

`Collections.<String>emptyList()`, `List.<String>of()` và `List.of("A")` vẫn trả về danh sách không thể thay đổi cấu trúc theo hợp đồng API, dù kiểu generic được ghi rõ. Ví dụ:

```java
var empty = Collections.<String>emptyList();
// empty.add("An"); // biên dịch được về kiểu, nhưng ném UnsupportedOperationException khi chạy
```

Nếu muốn thêm phần tử, dùng `var mutable = new ArrayList<String>();`. **Kiểm tra kiểu** và **khả năng thay đổi dữ liệu** là hai khía cạnh khác nhau.

### Không cung cấp thông tin runtime đã bị type erasure

Đối số kiểu generic chủ yếu được kiểm tra tại thời điểm biên dịch. Ví dụ `ArrayList<String>` và `ArrayList<Integer>` dùng cùng một lớp `ArrayList` ở runtime do *type erasure*. `var` không làm xuất hiện thông tin phần tử generic ở `getClass()`, và type witness không biến generic thành cơ chế kiểm tra kiểu bằng phản chiếu.

### Không làm kiểu biến thay đổi về sau

`var typed = new ArrayList<String>();` có kiểu `ArrayList<String>` suốt phạm vi của biến. Dù collection rỗng, thêm hay xóa phần tử, hay gán một `ArrayList<String>` mới, kiểu đó không đổi.

## 8. Ví dụ hoàn chỉnh (Java 17+)

Lưu vào tệp `GenericWitnessDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public class GenericWitnessDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        var names = new ArrayList<String>(); // ArrayList<String>
        names.add("An");
        names.add("Binh");

        var noHint = new ArrayList<>(); // ArrayList<Object>
        noHint.add("An");
        noHint.add(10);

        var typedEmpty = Collections.<String>emptyList(); // List<String>
        var unconstrained = Collections.emptyList();      // List<Object>
        var optionalNumber = Optional.<Long>empty();      // Optional<Long>
        var typedSet = Set.<String>of();                   // Set<String>
        var singleNumber = Collections.<Number>singletonList(7); // List<Number>

        var map = new HashMap<String, List<Integer>>();
        map.put("ids", List.of(1, 2));
        var box = new Box<String>("hello"); // Box<String>
        var words = List.of("red", "blue");  // List<String>

        List<String> targetTyped = new ArrayList<>();
        targetTyped.add("ok");

        System.out.println("names=" + names);
        System.out.println("noHint=" + noHint);
        System.out.println("typedEmpty=" + typedEmpty.size()
                + ", unconstrained=" + unconstrained.size());
        System.out.println("optionalNumber=" + optionalNumber.isPresent()
                + ", typedSet=" + typedSet.size());
        System.out.println("singleNumber=" + singleNumber);
        System.out.println("map=" + map);
        System.out.println("box=" + box.get());
        System.out.println("words=" + words + ", targetTyped=" + targetTyped);
    }
}
```

Biên dịch và chạy:

```bash
javac GenericWitnessDemo.java
java GenericWitnessDemo
```

Đầu ra:

```text
names=[An, Binh]
noHint=[An, 10]
typedEmpty=0, unconstrained=0
optionalNumber=false, typedSet=0
singleNumber=[7]
map={ids=[1, 2]}
box=hello
words=[red, blue], targetTyped=[ok]
```

Giải thích:

- `names` có kiểu `ArrayList<String>` do type argument `String` ghi rõ ở `new`.
- `noHint` có kiểu `ArrayList<Object>` vì diamond không có dữ kiện cụ thể; thêm `String` hoặc `Integer` không thay đổi kiểu.
- `typedEmpty` được xác định là `List<String>` nhờ type witness `<String>`, trong khi `unconstrained` là `List<Object>`.
- `singleNumber` là `List<Number>` dù phần tử runtime là một `Integer`.
- `map` là `HashMap<String, List<Integer>>`; `box` là `Box<String>`, do đối số kiểu của lớp được ghi rõ.
- `targetTyped` nhận kiểu khai báo `List<String>` bên trái, qua đó giúp suy luận diamond khi gọi constructor.

## 9. Lỗi thường gặp và cách tránh

| Tình huống | Nguyên nhân | Cách viết nên dùng |
| --- | --- | --- |
| `var xs = new ArrayList<>();` rồi nghĩ rằng `xs` là `ArrayList<String>` | Không có type argument hoặc ràng buộc từ constructor. | `var xs = new ArrayList<String>();` |
| `var xs = Collections.emptyList();` rồi gán cho `List<String>` | `xs` đã có kiểu `List<Object>`. | `var xs = Collections.<String>emptyList();` |
| `Collections.emptyList<String>()` | Type witness đặt sai vị trí. | `Collections.<String>emptyList()` |
| `var xs = new ArrayList<int>();` | Kiểu primitive không dùng được làm type argument. | `var xs = new ArrayList<Integer>();` |
| `var xs = Collections.<String>singletonList(7);` | Type witness mâu thuẫn kiểu đối số truyền vào. | `Collections.<Integer>singletonList(7)` hoặc chọn kiểu hợp lệ khác. |
| `var a = List.<String>of(); a.add("x");` | `List.of` tạo danh sách không thể sửa, không phải lỗi suy luận kiểu. | Dùng `new ArrayList<String>()` khi cần chỉnh sửa. |
| Nghĩ `var` suy luận lại sau `add(...)` hoặc `put(...)` | Kiểu biến được chốt ở khai báo. | Cung cấp thông tin kiểu từ biểu thức khởi tạo. |

Không cần ghi type witness ở mọi lời gọi: khi `List.of("a", "b")` hay `Optional.of(1)` đã có đối số đủ thông tin, để trình biên dịch tự suy luận sẽ ngắn gọn và rõ ràng hơn. Ngược lại, với factory rỗng, cần ép kiểu generic chính xác hoặc muốn chủ động chọn kiểu rộng hơn, type witness thường đáng dùng.

## 10. Tự kiểm tra

Xác định kiểu tĩnh của từng biến:

```java
var a = new ArrayList<String>();
var b = new ArrayList<>();
var c = new ArrayList<>(List.of("x", "y"));
var d = Collections.<Integer>emptyList();
var e = Optional.empty();
var f = Optional.<Double>empty();
var g = List.<Number>of(1, 2.5);
```

**Đáp án:**

1. `a`: `ArrayList<String>` do class type argument được ghi tường minh.
2. `b`: `ArrayList<Object>` vì diamond chưa được ràng buộc bởi thông tin cụ thể.
3. `c`: `ArrayList<String>` do constructor nhận một `List<String>`.
4. `d`: `List<Integer>` nhờ method type witness.
5. `e`: `Optional<Object>` vì lời gọi factory không có đối số hay target type từ khai báo tường minh.
6. `f`: `Optional<Double>` nhờ type witness.
7. `g`: `List<Number>` nhờ type witness `Number`; `1` và `2.5` được boxing thành các lớp con phù hợp của `Number`.

Các ví dụ kiểm tra dùng `java.util.ArrayList`, `List`, `Collections` và `Optional`.

**Ghi nhớ:** `var` nhận kiểu từ **biểu thức khởi tạo đã được xác định kiểu**. Type argument ghi tường minh trong `new Class<String>()` hoặc `SomeClass.<String>genericMethod()` giúp biểu thức mang kiểu generic mong muốn. Khi không ghi tường minh, kết quả phụ thuộc vào các dữ kiện suy luận thực sự có trong lời gọi, chứ không phụ thuộc việc bạn định sử dụng biến như thế nào về sau.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [Java Language Specification, `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1).
- [Java Language Specification, `15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9).
- [Java Language Specification, `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).
- [Dev.java — Type Inference](https://dev.java/learn/language/fp/generics/type-inference/).
