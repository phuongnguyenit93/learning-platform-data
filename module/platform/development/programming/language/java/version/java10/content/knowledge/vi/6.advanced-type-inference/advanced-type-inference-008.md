# Giới hạn suy luận kiểu của `var` từ cách biến sẽ được sử dụng

Khi khai báo biến cục bộ bằng `var` trong Java 10 trở lên, **trình biên dịch xác định kiểu của biến từ biểu thức khởi tạo tại chính khai báo đó**. Nó **không đọc các câu lệnh phía sau để đoán lập trình viên muốn biến mang kiểu nào**. Cách biến sẽ được gán lại, truyền vào phương thức, gọi phương thức trên nó hoặc trả về sau đó chỉ được **kiểm tra theo kiểu đã suy luận**, chứ không được dùng để suy luận lại kiểu.

Đây là quy tắc của Java hiện đại: `var` thay cho phần kiểu tường minh trong một số khai báo biến cục bộ, không tạo biến có kiểu động và cũng không thực hiện suy luận kiểu trên toàn bộ phương thức.

## 1. Quy tắc: suy luận tại khai báo, kiểm tra các cách dùng về sau

~~~java
var number = 10;     // Kiểu tĩnh được suy luận: int
number = 20;         // Hợp lệ: vẫn là int

// number = 2.5;      // Lỗi biên dịch: double không gán được cho int
// number = "mười";   // Lỗi biên dịch: String không gán được cho int
~~~

Lần gán `number = 20` hoặc nhu cầu dùng số thực trong một đoạn mã phía sau không khiến Java tự đổi `int` thành `double`, `Number` hay `Object`.

Nếu muốn biến mang kiểu `double` ngay từ đầu, hãy chủ động đưa thông tin đó vào khai báo:

~~~java
var number = 10.0;  // double
number = 2.5;       // Hợp lệ

// Hoặc ghi kiểu tường minh:
double otherNumber = 10;
otherNumber = 2.5;
~~~

Java có thể **chuyển kiểu khi sử dụng** theo quy tắc thông thường: chẳng hạn `double d = 10;` hợp lệ do mở rộng từ `int` sang `double`. Nhưng khả năng chuyển kiểu ở một vị trí sử dụng **không thay đổi kiểu tĩnh của biến `var` ban đầu**.

### Vì sao Java thiết kế như vậy?

Suy luận kiểu chỉ từ biểu thức khởi tạo giúp kết quả ổn định và dễ kiểm tra. Nếu phải tổng hợp mọi phép gán hay lời gọi phía sau, một chỉnh sửa ở cuối phương thức có thể làm thay đổi kiểu của biến ở đầu phương thức, khiến lỗi xuất hiện ở những nơi khó hiểu. Java cố ý giới hạn phạm vi suy luận kiểu biến cục bộ.

Đặc tả Java mô tả cách xử lý biểu thức khởi tạo của `var` như **một biểu thức độc lập, không nhận kiểu đích từ chính khai báo biến**. Từ kiểu của biểu thức đó, trình biên dịch tính kiểu tĩnh của biến (có các quy tắc chi tiết về generic và *upward projection* trong trường hợp cần thiết).

## 2. Không suy luận ngược từ phép gán sau

~~~java
var text = "Java";       // String
text = "Java 10";        // Hợp lệ

// text = new StringBuilder("Java"); // Không hợp lệ: StringBuilder không phải String
~~~

Một ví dụ khác khi biểu thức khởi tạo đã có kiểu rộng:

~~~java
CharSequence original = "Java";
var value = original;     // CharSequence, vì original được khai báo như vậy

System.out.println(value.length()); // Hợp lệ: CharSequence có length()
// value.toUpperCase();                // Không hợp lệ: CharSequence không có toUpperCase()
~~~

`original` thực tế đang giữ một `String`, nhưng `var value = original` lấy **kiểu tĩnh `CharSequence`** từ biểu thức `original`. Lời gọi `toUpperCase()` sau đó không thể buộc trình biên dịch suy luận `value` thành `String`.

Nếu thật sự muốn dùng `String`, cần biểu thức có kiểu `String` một cách hợp lệ:

~~~java
String value = "Java";
// Hoặc: var value = "Java"; // String
System.out.println(value.toUpperCase());
~~~

Với API trả về kiểu rộng, việc sửa kiểu trả về (khi phù hợp hợp đồng) hoặc kiểm tra và chuyển kiểu an toàn là giải pháp thiết kế; không nên ép kiểu thiếu kiểm tra chỉ để truy cập một phương thức.

## 3. Không suy luận kiểu từ lời gọi phương thức phía sau

Hãy xem phương thức nhận danh sách các chuỗi:

~~~java
static void printNames(java.util.List<String> names) {
    for (var name : names) {
        System.out.println(name);
    }
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Nếu khai báo:

~~~java
var names = new java.util.ArrayList<>(); // ArrayList<Object>
names.add("An");                          // Hợp lệ: Object nhận String
names.add(42);                            // Cũng hợp lệ: Object nhận Integer

// printNames(names); // Lỗi biên dịch: ArrayList<Object> không tương thích List<String>
~~~

Dù chương trình sau đó chỉ gọi `printNames(names)` hoặc thêm phần tử chuỗi, `names` đã có kiểu `ArrayList<Object>` vì biểu thức `new ArrayList<>()` **không nhận kiểu phần tử mong muốn từ các lệnh phía sau**.

Cần hiểu hai điều:

- `ArrayList<Object>` có thể chứa `String`, `Integer` và nhiều kiểu tham chiếu khác; `add("An")` không làm tham số generic tự đổi thành `String`.
- `ArrayList<Object>` không phải kiểu con của `List<String>`. Các tham số kiểu generic của Java về cơ bản là **invariant**: `List<Object>` và `List<String>` không thể thay cho nhau chỉ vì `String` là kiểu con của `Object`.

### Cách sửa

Cung cấp kiểu mong muốn **ngay trong biểu thức khởi tạo**:

~~~java
var names = new java.util.ArrayList<String>(); // ArrayList<String>
names.add("An");
printNames(names);                               // Hợp lệ
~~~

Hoặc khai báo kiểu bên trái để dùng được diamond `<>` với thông tin kiểu đích:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
printNames(names); // Hợp lệ
~~~

Ví dụ thứ nhất giữ kiểu cụ thể `ArrayList<String>`; ví dụ thứ hai khai báo theo giao diện `List<String>`. Chọn cách diễn đạt đúng hợp đồng bạn muốn dùng. Đừng chờ các câu lệnh `add` hoặc `printNames` “dạy” lại kiểu cho `var`.

## 4. Phương thức generic: giới hạn của kiểu đích khi dùng `var`

Đây là điểm thường gây bất ngờ nhất. `Collections.emptyList()` có phương thức generic dạng `<T> List<T> emptyList()`. Khi khai báo kiểu tường minh, Java có **kiểu đích** để suy luận `T`:

~~~java
java.util.List<String> words = java.util.Collections.emptyList();
// words có kiểu List<String>
~~~

Với `var`:

~~~java
var words = java.util.Collections.emptyList();
// words có kiểu List<Object> trong ngữ cảnh này
~~~

Biểu thức gọi `emptyList()` không có đối số cho biết `T`, và `var` không cung cấp kiểu đích `List<String>` ở phía bên trái. Kết quả ở ví dụ này là `List<Object>`. Các lệnh sử dụng `words` sau này không tác động ngược đến kết quả suy luận.

~~~java
static void acceptStrings(java.util.List<String> values) {
    System.out.println(values.size());
}

// Đặt các lệnh dưới đây trong một phương thức:
var values = java.util.Collections.emptyList(); // List<Object>
// acceptStrings(values); // Lỗi biên dịch: List<Object> không là List<String>
~~~

Có ba cách phổ biến để chương trình mang đúng kiểu `List<String>`:

~~~java
// A. Dùng khai báo tường minh:
java.util.List<String> a = java.util.Collections.emptyList();

// B. Dùng type witness tường minh ngay tại lời gọi generic:
var b = java.util.Collections.<String>emptyList();

// C. Truyền trực tiếp vào chỗ có kiểu đích:
acceptStrings(java.util.Collections.emptyList()); // Hợp lệ
~~~

Trường hợp C hợp lệ vì **đối số của lời gọi `acceptStrings` có ngữ cảnh đích `List<String>` ngay tại nơi `emptyList()` được gọi**. Điều đó khác hẳn với việc tạo `var values` trước, rồi mới truyền biến vào phương thức.

Với phương thức generic đã có đối số cung cấp thông tin kiểu, `var` vẫn suy luận được kiểu hữu ích:

~~~java
var singleton = java.util.Collections.singletonList("Java");
// List<String>, vì đối số "Java" cung cấp thông tin về T

var numbers = java.util.List.of(1, 2, 3);
// List<Integer>, vì đối số có kiểu int được boxing thành Integer
~~~

Lưu ý: `Collections.emptyList()` và `List.of(...)` không tạo danh sách có thể sửa bằng `add`. Khả năng sửa đổi do **đối tượng/API được trả về** quyết định, không liên quan đến `var` hay kiểu generic được suy luận.

## 5. Kiểu suy luận quyết định các overload và API có thể gọi

Nếu có hai overload:

~~~java
static void show(CharSequence text) {
    System.out.println("overload=CharSequence");
}

static void show(String text) {
    System.out.println("overload=String");
}
~~~

Đoạn trên là **hai phương thức của cùng một lớp**, khác kiểu tham số nên hợp lệ.

~~~java
CharSequence base = "hello";
var text = base; // CharSequence

show(text); // Chọn show(CharSequence), không chọn show(String)
~~~

Dù `base` giữ đối tượng `String` lúc chạy, Java chọn overload dựa vào kiểu tĩnh của đối số **`CharSequence`**. Trình biên dịch không suy luận ngược “vì có overload `show(String)` nên `text` phải là `String`”.

Nếu muốn chọn overload `String`:

~~~java
var text = "hello"; // String
show(text);         // Chọn show(String)
~~~

Đây cũng là lý do phương thức trả về giao diện có thể giới hạn API sau đó. Ví dụ, nếu `getNames()` khai báo trả về `List<String>` nhưng tạo `ArrayList<String>`, `var names = getNames();` vẫn có kiểu `List<String>`; lời gọi `names.ensureCapacity(20)` không biên dịch vì `List` không có phương thức đó.

## 6. Lambda, method reference và yêu cầu kiểu đích

Lambda và method reference thường **cần một kiểu giao diện hàm làm kiểu đích**. Vì `var` không cung cấp kiểu đích cho toàn bộ biểu thức khởi tạo, các dòng sau không biên dịch:

~~~java
// KHÔNG hợp lệ:
// var printer = () -> System.out.println("Hello");
// var length = String::length;
~~~

Java không suy luận kiểu của `printer` từ việc bạn định viết `printer.run()` sau đó, cũng không đoán `length` phải là `Function<String, Integer>` vì bạn định gọi `apply()`.

Dùng kiểu tường minh:

~~~java
Runnable printer = () -> System.out.println("Hello");

java.util.function.Function<String, Integer> length =
        String::length;
~~~

Hoặc đặt kiểu đích ngay trong phép ép kiểu của initializer:

~~~java
var printer = (Runnable) () -> System.out.println("Hello");

var length = (java.util.function.Function<String, Integer>)
        String::length;

printer.run();                     // In Hello
System.out.println(length.apply("Java")); // In 4
~~~

Cả hai cách đều cung cấp kiểu đích **trước khi việc dùng biến về sau diễn ra**. Đây là khác biệt giữa suy luận kiểu hợp lệ ngay bên trong biểu thức và suy luận kiểu ngược từ ý định tương lai.

### Phân biệt với lambda bên trong biểu thức đã có kiểu đích

Không nên kết luận rằng “hễ có `var` thì lambda hoặc method reference nào bên phải cũng lỗi”. Chúng có thể xuất hiện **bên trong** một lời gọi đã cung cấp kiểu đích cho đối số:

~~~java
var sizes = java.util.List.of("a", "bb")
        .stream()
        .map(String::length); // Suy luận Stream<Integer>
System.out.println(sizes.count()); // In 2
~~~

`Stream.map` có tham số là một giao diện hàm, nên `String::length` nhận kiểu đích từ **tham số phương thức `map`**. Sau đó, toàn bộ biểu thức tạo `Stream<Integer>`, và `var sizes` lấy kiểu đó. Vậy giới hạn chính xác là: **khai báo `var` không tự cung cấp kiểu đích cho initializer**, nhưng các biểu thức lồng bên trong vẫn tuân theo quy tắc suy luận kiểu bình thường của Java.

## 7. Không thể bỏ qua initializer rồi chờ cách dùng cho biết kiểu

~~~java
// KHÔNG hợp lệ:
// var value;
// value = "Java";
~~~

Biến cục bộ viết bằng `var` cần biểu thức khởi tạo ngay trong khai báo. Không có cơ chế suy luận từ phép gán `value = "Java"` xuất hiện về sau.

Tương tự:

~~~java
// KHÔNG hợp lệ:
// var message = null;
// message = "Java";
~~~

`null` đơn lẻ không cung cấp một kiểu cụ thể để `var` suy luận. Nếu muốn cho phép giá trị `null` ban đầu, hãy khai báo kiểu tường minh:

~~~java
String message = null;
message = "Java";
~~~

Một initializer được ép kiểu tường minh cũng có thể xác định kiểu:

~~~java
var message = (String) null; // Kiểu String; giá trị hiện tại là null
~~~

Tuy vậy, chỉ nên dùng `(String) null` khi thật sự có lý do rõ ràng; kiểu tường minh `String message = null;` thường dễ đọc hơn. Cả hai vẫn cần xử lý khả năng `NullPointerException` nếu dùng giá trị `null` mà không kiểm tra.

Tương tự với mảng: `var values = {1, 2, 3};` không biên dịch vì dạng array initializer rút gọn này cần kiểu đích. Hãy viết `var values = new int[] {1, 2, 3};` hoặc `int[] values = {1, 2, 3};`.

## 8. Chương trình hoàn chỉnh và kết quả kiểm tra

Lưu thành tệp **`VarUsageInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class VarUsageInferenceDemo {

    static void show(CharSequence value) {
        System.out.println("overload=CharSequence");
    }

    static void show(String value) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) {
        var count = 10;                 // int
        count = 20;                     // Hợp lệ, vẫn là int

        var mixed = new ArrayList<>();  // ArrayList<Object>
        mixed.add("An");
        mixed.add(7);

        var typed = new ArrayList<String>(); // ArrayList<String>
        typed.add("Java");

        var empty = Collections.emptyList(); // List<Object>
        List<String> typedEmpty = Collections.emptyList();
        var singleton = Collections.singletonList("Java"); // List<String>

        CharSequence base = "hello";
        var inferred = base;           // CharSequence, dù runtime là String

        System.out.println("count=" + count);
        System.out.println("mixed=" + mixed);
        System.out.println("typed=" + typed);
        System.out.println("empty=" + empty.size());
        System.out.println("typedEmpty=" + typedEmpty.size());
        System.out.println("singleton="
                + singleton.get(0).toUpperCase(Locale.ROOT));
        System.out.println("chars=" + inferred.length());
        show(inferred);

        var action = (Runnable) () -> System.out.println("lambda=ok");
        action.run();

        var len = (Function<String, Integer>) String::length;
        System.out.println("len=" + len.apply("Java"));

        var sizes = List.of("a", "bb").stream().map(String::length);
        System.out.println("streamCount=" + sizes.count());
    }
}
~~~

Chương trình dùng tính năng tương thích **Java 10 trở lên**; có thể biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac VarUsageInferenceDemo.java
java VarUsageInferenceDemo
~~~

Kết quả `stdout`:

~~~text
count=20
mixed=[An, 7]
typed=[Java]
empty=0
typedEmpty=0
singleton=JAVA
chars=5
overload=CharSequence
lambda=ok
len=4
streamCount=2
~~~

Các điểm cần giải thích:

- `mixed` vẫn là `ArrayList<Object>` sau hai lần `add`; `typed` được định kiểu `ArrayList<String>` ngay trong initializer.
- `empty` được suy luận `List<Object>`, còn `typedEmpty` là `List<String>` nhờ kiểu đích tường minh.
- `singleton` lấy `String` từ đối số truyền trực tiếp vào phương thức generic.
- `inferred` có kiểu tĩnh `CharSequence` nên chọn overload `show(CharSequence)`.
- `action` và `len` dùng kiểu đích trong cast; `sizes` nhận `Stream<Integer>` nhờ kiểu đích của `map` và suy luận kiểu trong biểu thức.
- Chương trình không cần truy vấn kiểu runtime để thay đổi kết quả suy luận; tất cả kiểu được xác định khi biên dịch.

## 9. Cách tránh lỗi suy luận từ “ý định sử dụng”

| Tình huống muốn đạt | Cách khai báo thích hợp | Lý do |
| --- | --- | --- |
| Cần `double` cho các phép gán sau | `var total = 0.0;` hoặc `double total = 0;` | Không chờ phép gán sau làm đổi `int` |
| Cần danh sách chuỗi có thể thêm phần tử | `var names = new ArrayList<String>();` | Có `String` ngay trong initializer |
| Muốn phụ thuộc vào giao diện `List<String>` | `List<String> names = new ArrayList<>();` | Nêu rõ hợp đồng cần dùng |
| Cần danh sách rỗng generic `List<String>` | `List<String> xs = Collections.emptyList();` | Cung cấp kiểu đích cho phương thức generic |
| Muốn dùng `var` với danh sách rỗng generic | `var xs = Collections.<String>emptyList();` | Cung cấp tham số kiểu tại lời gọi |
| Cần giữ lambda để gọi về sau | `Runnable action = () -> ...;` | Lambda cần functional-interface target |
| Muốn dùng `var` với lambda | `var action = (Runnable) () -> ...;` | Cast cung cấp kiểu đích |
| Cần biến ban đầu `null` | `String name = null;` | `null` đơn lẻ không xác định được kiểu |
| Cần API của `String` | `String s = ...;` hoặc `var s = "Java";` | Bảo đảm kiểu tĩnh là `String` |

**Nguyên tắc chọn cách viết:** trước khi dùng `var`, hãy tự hỏi “biểu thức khởi tạo **ngay bây giờ** có kiểu gì?” Nếu chỉ nhìn initializer không thể thấy kiểu mong muốn, hãy làm nó rõ hơn bằng tham số generic/cast hợp lệ hoặc sử dụng kiểu tường minh ở biến. Việc đọc code sẽ dễ dàng hơn, và các lỗi không tương thích được phát hiện ở nơi khai báo.

## 10. Bài tập tự kiểm tra

Cho các đoạn độc lập:

~~~java
// A
var a = 1;
// a = 1.5;

// B
var b = new java.util.ArrayList<>();
b.add("Java");
// String text = b.get(0);

// C
var c = java.util.Collections.emptyList();
// java.util.List<String> names = c;

// D
java.util.List<String> d = java.util.Collections.emptyList();

// E
var e = (java.util.function.Function<String, Integer>) String::length;
System.out.println(e.apply("Java"));
~~~

**Hãy xác định:** A có biến đổi thành `double` nếu dùng `1.5` về sau không? B có tự thành `ArrayList<String>` sau lời gọi `add("Java")` không? C có tương thích `List<String>` không? D và E có hợp lệ không?

**Đáp án:**

1. A có kiểu `int`; gán `1.5` sẽ báo lỗi biên dịch, kiểu không đổi.
2. B có kiểu `ArrayList<Object>`; `add("Java")` được phép, nhưng `b.get(0)` có kiểu tĩnh `Object` nên không thể gán trực tiếp cho `String`.
3. C có kiểu `List<Object>`; không gán trực tiếp cho `List<String>` được.
4. D hợp lệ và có kiểu `List<String>` nhờ ngữ cảnh đích trong khai báo.
5. E hợp lệ, `e` có kiểu `Function<String, Integer>` và in `4`; cast cung cấp kiểu đích cho method reference.

## 11. Ghi nhớ

- **`var` suy luận từ initializer tại khai báo**, không từ cách sử dụng biến về sau.
- Gán lại, gọi phương thức hoặc truyền biến vào API **không làm thay đổi kiểu tĩnh đã suy luận**.
- Với generic, `var` không tự cung cấp kiểu đích cho toàn bộ initializer; `new ArrayList<>()` và `Collections.emptyList()` có thể suy luận `Object` khi thiếu thông tin.
- Lambda/method reference trực tiếp cần kiểu đích; khai báo `var` không cung cấp kiểu đó, nhưng một cast hoặc tham số phương thức bên trong biểu thức có thể cung cấp.
- Khi cần một hợp đồng kiểu cụ thể cho mã phía sau, **ghi kiểu tường minh hoặc đưa thông tin kiểu vào biểu thức khởi tạo**.

### Tài liệu tham khảo

- [Java Language Specification, `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4) — quy tắc suy luận kiểu của initializer trong `var`.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286) và [FAQ về suy luận kiểu biến cục bộ](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html) — phạm vi và giới hạn suy luận từ biểu thức khởi tạo.
- [dev.java — Generic Type Inference](https://dev.java/learn/generics/type-inference/) — kiểu đích khi gọi phương thức generic.
