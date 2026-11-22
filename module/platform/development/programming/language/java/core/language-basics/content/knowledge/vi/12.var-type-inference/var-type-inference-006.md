# Không dùng `var` cho trường hoặc kiểu trả về phương thức — Java 17+

## 1. Mục tiêu và câu trả lời ngắn

Trong Java 17+, `var` hỗ trợ **suy luận kiểu biến cục bộ** (*local-variable type inference*), chứ không phải cú pháp thay thế kiểu khai báo ở mọi vị trí trong chương trình.

**Hai quy tắc trọng tâm:**

- **Không dùng `var` để khai báo field** (*trường dữ liệu*) của class, dù là field instance, `static` hay `final`.
- **Không dùng `var` làm kiểu trả về của method**, dù method có `return` một biểu thức mà compiler có thể xác định kiểu.

~~~java
public final class Counter {
    private int value = 0; // Đúng: field có kiểu int tường minh

    public int getValue() { // Đúng: kiểu trả về int tường minh
        var snapshot = value; // Đúng: var khai báo biến cục bộ trong thân method
        return snapshot;
    }
}
~~~

Các dòng sau **không phải cú pháp Java hợp lệ**:

~~~java
// private var value = 0;       // SAI: var không khai báo field
// public var getValue() {      // SAI: var không là return type
//     return 0;
// }
~~~

`var` không biến Java thành ngôn ngữ kiểu động. Compiler vẫn suy ra một **kiểu tĩnh cụ thể** cho biến cục bộ tại nơi khai báo và kiểm tra kiểu trong các câu lệnh sau.

## 2. Field, local variable và method return type khác nhau

Ba khái niệm rất dễ nhầm khi học cú pháp:

| Thành phần | Nằm ở đâu? | Kiểu khai báo |
|---|---|---|
| **Instance field** | Trong class, ngoài thân method/constructor/block cục bộ | Viết tên kiểu tường minh |
| **Static field** | Trong class, có `static` | Viết tên kiểu tường minh |
| **Local variable** | Trong method, constructor hoặc khối lệnh hợp lệ | Có thể dùng `var` nếu đủ điều kiện |
| **Method return type** | Trước tên method trong chữ ký | Viết kiểu trả về, hoặc `void` |
| **Method parameter** | Trong `(...)` của khai báo method | Viết kiểu tham số tường minh |

Ví dụ:

~~~java
final class Account {
    private final String owner;       // Field: String
    private static int nextId = 1;    // Static field: int

    Account(String owner) {            // Tham số constructor: String
        var normalized = owner.trim(); // Local variable: String
        this.owner = normalized;
    }

    String getOwner() {                // Method return: String
        var result = owner;            // Local variable: String
        return result;
    }
}
~~~

Trong ví dụ, compiler tự xác định kiểu của `normalized` và `result` từ biểu thức khởi tạo. Nhưng cú pháp của **field** và **chữ ký method** vẫn bắt buộc nêu tên kiểu cụ thể.

**Một class có thể chứa đồng thời khai báo kiểu tường minh và `var`**: mỗi thứ thuộc phạm vi hợp lệ riêng, không mâu thuẫn nhau.

## 3. Sai ở field: initializer không làm `var` hợp lệ

Kể cả field có giá trị khởi tạo hiển nhiên, cũng **không thể** viết:

~~~java
// KHÔNG ĐƯỢC CHÈN VÀO CLASS ĐỂ BIÊN DỊCH
// class Wrong {
//     private var name = "Java";
//     static var attempts = 0;
//     final var enabled = true;
// }
~~~

Không hợp lệ vì `var` không được phép đứng tại vị trí tên kiểu của field. Tính từ `private`, `static` hoặc `final` không thay đổi giới hạn này.

Cách đúng:

~~~java
final class Settings {
    private String name = "Java";
    private static int attempts = 0;
    private final boolean enabled = true;
}
~~~

**Không tự suy luận field từ giá trị khởi tạo** trong Java 17. Compiler biết `"Java"` có kiểu `String`, nhưng Java không định nghĩa cú pháp `var` cho field dựa trên thông tin ấy.

### Nếu field nhận object generic thì sao?

~~~java
import java.util.ArrayList;
import java.util.List;

final class Group {
    private final List<String> members = new ArrayList<>();
}
~~~

Ở đây Java cho phép **diamond `<>`** ở phía phải nhờ **kiểu đích tường minh** `List<String>` bên trái. Đây không phải khai báo field bằng `var`.

Với code:

~~~java
// private final var members = new ArrayList<String>(); // SAI
~~~

vẫn sai cú pháp dù initializer đã nêu `ArrayList<String>`.

**Lợi ích thiết kế:** khai báo `List<String>` làm field cho thấy code dựa vào abstraction `List`, thay vì khóa API vào lớp triển khai `ArrayList`.

## 4. Sai ở return type: `return` không thay thế khai báo kiểu

Java yêu cầu method khai báo kiểu trả về ở chữ ký:

~~~java
static int sum(int a, int b) {
    return a + b;
}
~~~

Không thể thay `int` bằng `var`:

~~~java
// static var sum(int a, int b) {
//     return a + b;
// }
~~~

Lý do: `var` là cơ chế suy luận cho **khai báo biến cục bộ ở những vị trí ngôn ngữ cho phép**, không phải cơ chế suy luận kiểu trả về của method từ tất cả nhánh `return`.

Một method không trả giá trị dùng `void`, **không dùng `var`**:

~~~java
static void logMessage(String message) {
    System.out.println(message);
}
~~~

### Vẫn được dùng `var` bên trong method trả giá trị

~~~java
static long square(int input) {
    var result = (long) input * input; // Suy ra long
    return result;                     // Kiểu trả về long tường minh
}
~~~

Ở đây `result` là biến cục bộ kiểu `long`; method `square` vẫn có chữ ký trả `long`.

### Phân biệt return expression và method signature

~~~java
static double average(int x, int y) {
    var total = x + y;   // int
    return total / 2.0;  // double
}
~~~

Một method hoàn toàn có thể chứa nhiều biến cục bộ được suy luận kiểu. Nhưng **hợp đồng trả về** vẫn được định nghĩa bằng kiểu `double` ở đầu chữ ký.

## 5. `var` trong thân constructor, instance initializer và static initializer

Không được khai báo field bằng `var`, nhưng bạn **được khai báo biến cục bộ bằng `var` trong khối lệnh** của class, ví dụ constructor:

~~~java
final class Product {
    private final String code;

    Product(String rawCode) {
        var normalized = rawCode.strip();
        this.code = normalized;
    }
}
~~~

Và trong **khối khởi tạo instance**:

~~~java
final class Metrics {
    private int total = 0;

    {
        var initialValue = 5; // Biến cục bộ trong initializer block
        total = initialValue;
    }
}
~~~

Tương tự trong **static initializer**:

~~~java
final class Configuration {
    private static final int DEFAULT_SIZE;

    static {
        var computed = 16 * 2; // Local variable kiểu int
        DEFAULT_SIZE = computed;
    }
}
~~~

**Điểm phân biệt vị trí:**

- `private var total = 0;` → sai vì đang khai báo field.
- Trong `{ var temporary = 0; }` → đúng nếu là một khối lệnh hợp lệ và có initializer.

Khối lệnh **không biến local variable thành field**. Biến `temporary` chỉ tồn tại trong phạm vi lexical của khối, không thể truy cập từ bên ngoài.

## 6. Điều kiện để suy kiểu local không cho phép suy kiểu field

Ở **vị trí local** hợp lệ, compiler suy kiểu từ initializer; ở **vị trí field** hay **chữ ký method**, dù có thể đoán kiểu từ biểu thức thì Java 17 vẫn đòi kiểu tường minh.

~~~java
var count = 1;                   // local: int
var list = new java.util.ArrayList<String>(); // local: ArrayList<String>
String nullable = null;          // Kiểu tham chiếu tường minh
// var absent = null;            // Local không suy được kiểu
// var missing;                  // Local thiếu initializer
~~~

Đừng trộn hai câu hỏi “**biểu thức có kiểu suy ra được không?**” và “**vị trí khai báo có cho dùng var không?**”. Biểu thức hợp lệ chưa đủ nếu đang khai báo field hoặc kiểu trả về.

## 7. `var` không thay đổi hợp đồng field hoặc method return

Ví dụ một lớp có giao diện đơn giản:

~~~java
final class Invoice {
    private final long cents;

    Invoice(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        this.cents = cents;
    }

    long getCents() {
        var snapshot = cents; // long
        return snapshot;
    }

    String describe() {
        var label = "cents=";
        return label + cents;
    }
}
~~~

Những phần **ổn định trong API**:

- Field `cents` luôn khai báo `long`.
- Constructor nhận tham số `long`.
- `getCents()` khai báo trả `long`.
- `describe()` khai báo trả `String`.

Những phần có thể **rút gọn tại chỗ**:

- `snapshot`, `label` là biến cục bộ, có initializer phù hợp.

Đây là cách phối hợp `var` hợp lý: giữ kiểu rõ ở **biên class/API** và giảm lặp kiểu ở những điểm mà initializer cho thấy kiểu cụ thể.

### Tại sao kiểu trả về rõ lại quan trọng?

Caller có thể phụ thuộc vào chữ ký:

~~~java
long totalCents = invoice.getCents();
String text = invoice.describe();
~~~

Nếu tác giả method sửa biểu thức tính toán bên trong, chữ ký tường minh giúp compiler kiểm tra rằng giá trị trả về vẫn tương thích. Đây là một lớp bảo vệ hợp đồng API khi refactor.

## 8. Tham số phương thức, lambda và kiểu generic tại ranh giới API

**Tham số method** vẫn cần kiểu rõ: `static String format(int n)` hợp lệ, còn `format(var n)` không hợp lệ. Riêng tham số **lambda** từ Java 11 có thể dùng `var` khi lambda đã có target type:

~~~java
java.util.function.IntBinaryOperator add =
        (var left, var right) -> left + right;
System.out.println(add.applyAsInt(2, 3)); // 5
~~~

Một danh sách tham số lambda không được trộn `var` với tham số không ghi kiểu hoặc ghi kiểu tường minh. Ví dụ `var callback = x -> x + 1;` vẫn sai vì initializer là lambda thiếu functional target type.

Đối với generic, khai báo field/API nên thể hiện **mức abstraction mong muốn**:

~~~java
private final java.util.List<String> members =
        new java.util.ArrayList<>();
~~~

Ở đây `List<String>` là kiểu field được công bố; diamond nhận kiểu đích. Nếu trong local dùng `var bag = new java.util.ArrayList<>();`, kiểu suy ra là `ArrayList<Object>` trong tình huống này, không tự suy thành `ArrayList<String>` từ các lần `add` viết sau. Nội dung về vị trí hợp lệ và suy luận generic được nhắc ở đây để **phân biệt ranh giới API với local**, không phải thay thế chủ đề chuyên sâu của các bài khác.

## 9. Return type không tự đổi theo `var` trong method

Giả sử method khai báo trả `long` nhưng biểu thức bên trong có kiểu `int`:

~~~java
static long twice(int input) {
    var result = input * 2; // int; phép tính diễn ra ở int
    return result;          // Widening int -> long khi return
}
~~~

**Bẫy:** nếu `input` quá lớn, phép nhân `int` có thể overflow **trước khi** chuyển thành `long`. `var` không tự dự đoán ý định muốn tính kiểu rộng hơn.

~~~java
static long twiceSafe(int input) {
    var result = (long) input * 2; // long từ lúc nhân
    return result;
}
~~~

Với `input = 2_000_000_000`:

~~~java
System.out.println(twice(2_000_000_000));     // -294967296
System.out.println(twiceSafe(2_000_000_000)); // 4000000000
~~~

Cả hai method đều **trả `long` theo chữ ký**, nhưng **kiểu của phép tính trung gian** khác nhau. Đây là lý do quan trọng để hiểu kiểu mà compiler suy ra, không phải chỉ đọc chữ `var`.

### Compiler vẫn kiểm tra kiểu trả về

~~~java
static int count() {
    var text = "not an int";
    // return text; // Lỗi compile: String không chuyển thành int
    return 1;
}
~~~

`var` không cho phép “giấu” một giá trị trả về sai kiểu. Chữ ký method vẫn là hợp đồng được compiler kiểm tra.

## 10. Sửa đúng lỗi tại field và chữ ký method

| Vị trí viết sai | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| `private var name = "Java";` | `var` không khai báo field | `private String name = "Java";` |
| `static var count = 1;` | `static` không làm field được suy kiểu | `static int count = 1;` |
| `public var name() { ... }` | Chữ ký method phải khai báo return type | `public String name() { ... }` |
| `void set(var x)` | Method parameter phải có kiểu | `void set(int x)` |
| `record Pair(var a, int b)` | Record component cần kiểu | `record Pair(int a, int b)` |

Nếu code **đã ở trong thân method/constructor/block**, `var local = expression;` có thể hợp lệ; đừng sửa field hoặc chữ ký method bằng cách di chuyển dữ liệu vào local mà làm mất hợp đồng bên ngoài.

## 11. Ví dụ Java 17 đầy đủ, độc lập

Lưu file đúng tên **`VarMemberReturnDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;

public final class VarMemberReturnDemo {
    private static final int DEFAULT_LIMIT = 5; // Field: kiểu tường minh
    private static int created = 0;             // Static field: kiểu tường minh

    private final String label;                 // Instance field
    private final List<String> history = new ArrayList<>();

    static {
        var marker = "class initialized";      // Local trong static block
        if (marker.isEmpty()) {
            throw new IllegalStateException("empty marker");
        }
    }

    {
        var entry = "instance initialized";     // Local trong instance block
        history.add(entry);
    }

    VarMemberReturnDemo(String rawLabel) {
        var normalized = Objects.requireNonNull(rawLabel).strip();
        label = normalized;
        created++;
    }

    public String labelText() {                 // Return type tường minh
        var prefix = "Label:";
        return prefix + label;
    }

    public int sum(int left, int right) {        // Parameters/return rõ kiểu
        var result = left + right;
        return result;
    }

    public List<String> history() {              // Return interface List<String>
        return List.copyOf(history);
    }

    static long twice(int input) {               // Return long, tính int
        var result = input * 2;
        return result;
    }

    static long twiceSafe(int input) {           // Return long, tính long
        var result = (long) input * 2;
        return result;
    }

    public static void main(String[] args) throws Exception {
        var demo = new VarMemberReturnDemo("  Core  ");
        System.out.println("label=" + demo.labelText());
        System.out.println("history=" + demo.history());
        System.out.println("sum=" + demo.sum(2, 3));

        var count = DEFAULT_LIMIT; // int
        count += 2;
        System.out.println("local int=" + count);

        var title = "Java"; // String
        System.out.println("text length=" + title.length());

        var names = new ArrayList<String>();
        names.add("Lan");
        System.out.println("typed list=" + names);

        List<String> contract = new ArrayList<>();
        contract.add("An");
        System.out.println("interface list=" + contract);

        var inferredReturn = demo.history(); // List<String>
        System.out.println("return item=" + inferredReturn.get(0));

        var nullable = (String) null;
        System.out.println("typed null=" + (nullable == null));

        IntBinaryOperator add = (var a, var b) -> a + b;
        System.out.println("lambda vars=" + add.applyAsInt(3, 4));

        var increment = (IntUnaryOperator) (x -> x + 1);
        System.out.println("lambda target=" + increment.applyAsInt(5));

        for (var i = 0; i < 2; i++) {
            System.out.println("for=" + i);
        }

        try (var reader = new StringReader("Z")) {
            System.out.println("reader=" + (char) reader.read());
        }

        System.out.println("twice int first=" + twice(2_000_000_000));
        System.out.println("twice long first=" + twiceSafe(2_000_000_000));

        var alias = demo;
        System.out.println("same instance=" + (alias == demo));
        System.out.println("objects created=" + created);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal đứng trong thư mục có file `VarMemberReturnDemo.java`. Không cần Maven, Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 VarMemberReturnDemo.java
java -cp . VarMemberReturnDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarMemberReturnDemo.java
java -cp . VarMemberReturnDemo
~~~

**Exact expected output:**

~~~text
label=Label:Core
history=[instance initialized]
sum=5
local int=7
text length=4
typed list=[Lan]
interface list=[An]
return item=instance initialized
typed null=true
lambda vars=7
lambda target=6
for=0
for=1
reader=Z
twice int first=-294967296
twice long first=4000000000
same instance=true
objects created=1
~~~

### Tại sao code này đúng phạm vi `var`?

1. Các field `DEFAULT_LIMIT`, `created`, `label`, `history` đều ghi **kiểu tường minh**.
2. Method `labelText`, `sum`, `history`, `twice`, `twiceSafe`, `main` đều có **return type tường minh**, gồm cả `void`.
3. Các biến `marker`, `entry`, `normalized`, `prefix`, `result` là **local** trong những khối lệnh hợp lệ.
4. `IntBinaryOperator add = (var a, var b) -> ...` hợp lệ vì lambda có target type.
5. `var nullable = (String) null` có kiểu `String` vì cast cung cấp kiểu cho initializer.
6. `var inferredReturn = demo.history()` suy ra `List<String>` theo **kiểu trả về đã khai báo của method**, không phải do compiler nhìn vào runtime object.
7. `twice` và `twiceSafe` cùng trả `long`, nhưng kiểu phép nhân trung gian khác nên kết quả khác — static typing vẫn kiểm soát.
8. `same instance=true` vì gán biến `alias` sao chép tham chiếu, không tạo object mới.

## 12. Bài tập có đáp án

### Bài A — sửa khai báo field

Đoạn sai:

~~~java
// final class Item {
//     private var id = 7;
// }
~~~

**Đáp án:**

~~~java
final class Item {
    private int id = 7;
}
~~~

### Bài B — sửa kiểu trả về method

Đoạn sai:

~~~java
// static var greeting() {
//     return "Hello";
// }
~~~

**Đáp án:**

~~~java
static String greeting() {
    return "Hello";
}
~~~

Có thể dùng local `var` trong thân method:

~~~java
static String greeting() {
    var text = "Hello";
    return text;
}
~~~

### Bài C — `var` trong constructor

~~~java
final class User {
    private final String name;

    User(String input) {
        var trimmed = input.trim();
        name = trimmed;
    }
}
~~~

**Đáp án:** hợp lệ. `trimmed` là biến cục bộ kiểu `String`; `name` là field khai báo tường minh. Nếu `input` có thể null, cần thêm validation theo hợp đồng.

### Bài D — `var` có làm method trả về kiểu mới không?

~~~java
static long compute(int x) {
    var doubled = x * 2;
    return doubled;
}
~~~

**Đáp án:** kiểu trả về method vẫn **`long`**; `doubled` có kiểu **`int`**. Phép nhân diễn ra trong `int`, sau đó kết quả mới chuyển rộng sang long. Với đầu vào lớn, có nguy cơ int overflow trước khi trả. Cách sửa nếu cần phép nhân long: `var doubled = (long) x * 2;`.

### Bài E — vị trí hợp lệ hay không?

Đánh giá:

~~~java
// private final var names = new ArrayList<String>();
// public var names() { return List.of("An"); }

static List<String> names() {
    var result = List.of("An");
    return result;
}
~~~

**Đáp án:** hai dòng comment là **không hợp lệ** do field và return type. Method `names()` hợp lệ, khai báo trả `List<String>` rõ ràng; `result` là local variable suy ra kiểu từ `List.of("An")`.

### Bài F — generic với field

Muốn field duy trì API `List<String>` nhưng tạo bằng `ArrayList`:

~~~java
private final java.util.List<String> names =
        new java.util.ArrayList<>();
~~~

**Đáp án:** hợp lệ và thể hiện abstraction. Không đổi thành `private final var names = ...` vì `var` không được khai báo field.

## 13. Checklist và kết luận

- [ ] Biết `var` chỉ là cú pháp suy luận kiểu ở **những khai báo cục bộ hợp lệ**.
- [ ] Không dùng `var` cho instance field, static field hoặc final field.
- [ ] Không dùng `var` ở vị trí return type của method.
- [ ] Không dùng `var` cho tham số method thông thường hay record component.
- [ ] Dùng kiểu tường minh để biểu diễn hợp đồng class/API.
- [ ] Biết local `var` hợp lệ trong method, constructor, instance/static initializer block.
- [ ] Biết `var` cần initializer có kiểu suy ra được; null literal trần không đủ.
- [ ] Biết `var` trong for, enhanced for, try-with-resources và lambda parameter có điều kiện.
- [ ] Hiểu cú pháp `var` không đổi kiểu khi gán lại.
- [ ] Nhớ generic, overload, toán tử và access tới member vẫn được **kiểm tra tĩnh**.
- [ ] Biết kiểu của initializer có thể gây overflow trước khi kết quả được return sang kiểu rộng.
- [ ] Chọn khai báo kiểu tường minh khi mức abstraction hoặc hợp đồng dữ liệu quan trọng.
- [ ] Biên dịch và chạy `VarMemberReturnDemo.java` bằng `javac`/`java`; so từng dòng expected output.

**Kết luận:** Trong Java 17+, `var` là tiện ích giảm lặp tên kiểu cho **biến cục bộ có initializer hợp lệ**. Nó **không phải kiểu dữ liệu**, nên không được dùng làm **kiểu field** hoặc **kiểu trả về method**. Hãy khai báo rõ kiểu ở biên class/API và dùng `var` trong thân khối lệnh khi initializer làm cho kiểu tĩnh dễ hiểu, dễ kiểm tra.