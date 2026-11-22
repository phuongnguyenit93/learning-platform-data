# Giới hạn dùng `var` cho trường dữ liệu trong Java

*Ngữ cảnh Java 10 — “Vị trí dùng var”. Nội dung tập trung vào quy tắc vẫn áp dụng trong các phiên bản Java hiện đại (Java 17+ và mới hơn).*

## 1. Kết luận cần nắm

**Không thể dùng `var` làm kiểu của một trường dữ liệu (field) trong Java**, dù đó là trường đối tượng (instance field), trường `static`, trường `private`, `public` hay `final`. Quy tắc này có từ khi suy luận kiểu biến cục bộ ra đời ở Java 10 (JEP 286) và vẫn có hiệu lực.

`var` là **tên kiểu có ý nghĩa đặc biệt trong một số ngữ cảnh khai báo**, cho phép trình biên dịch suy luận kiểu **tĩnh** của biến cục bộ từ biểu thức khởi tạo. Nó không đại diện cho kiểu dữ liệu “tự thay đổi” lúc chương trình chạy, không phải kiểu mà JVM lưu trong trường dữ liệu, và cũng không phải một lối viết tắt có thể đặt ở mọi nơi thường ghi tên kiểu.

Ví dụ phân biệt:

~~~java
class Example {
    private String name = "Java"; // Hợp lệ: instance field có kiểu String
    private static final int LEVEL = 10; // Hợp lệ: static field có kiểu int

    void print() {
        var message = name + " " + LEVEL; // Hợp lệ: biến cục bộ của phương thức
        System.out.println(message);
    }
}
~~~

Trong ví dụ trên, `message` được suy luận là `String` tại thời điểm biên dịch. Hai trường `name` và `LEVEL` bắt buộc viết kiểu tường minh.

## 2. Field khác local variable ở chỗ nào?

**Field (trường dữ liệu)** là biến được khai báo trực tiếp trong thân một lớp hoặc giao diện; trường đối tượng gắn với từng instance, còn trường `static` thuộc về lớp. Khai báo field là một phần mô tả cấu trúc kiểu của lớp. Kiểu của field được ghi trong class file và tham gia hợp đồng liên kết khi code khác truy cập field.

**Local variable (biến cục bộ)** được khai báo trong khối lệnh, chẳng hạn thân phương thức, constructor hoặc khối khởi tạo `static`/instance. Biến cục bộ có phạm vi giới hạn trong đoạn mã đó và có thể để trình biên dịch xác định kiểu thông qua `var` khi cú pháp cho phép.

| Vị trí | Ví dụ | `var` làm kiểu khai báo được không? |
| --- | --- | --- |
| Field đối tượng, kể cả `private` | `private var title = "A";` | **Không** |
| Field `static` | `static var counter = 0;` | **Không** |
| Field `final` | `private final var id = 1;` | **Không** |
| Field trong interface, hằng số của interface | `var LIMIT = 3;` | **Không** |
| Thành phần khai báo của `record` | `record Person(var name) {}` | **Không** |
| Biến cục bộ trong phương thức | `var count = 3;` | **Có** |
| Biến cục bộ trong constructor | `var normalized = input.trim();` | **Có** |
| Biến cục bộ trong khối `static { ... }` hoặc `{ ... }` | `var limit = 3;` | **Có** |
| Biến điều khiển vòng lặp | `for (var i = 0; i < 3; i++)` | **Có** |
| Biến phần tử của enhanced `for` | `for (var item : items)` | **Có** |

Lưu ý về chữ “tham số”: `var` **không** được dùng để khai báo tham số của phương thức hoặc constructor. Từ Java 11, cú pháp `var` được hỗ trợ riêng cho tham số của biểu thức lambda suy luận kiểu, ví dụ `(var s) -> s.trim()`. Ngoại lệ này **không** mở rộng `var` sang field hay tham số của phương thức thông thường.

## 3. Vì sao Java không suy luận kiểu của field?

JEP 286 thiết kế suy luận kiểu để giúp mã nguồn cục bộ ngắn hơn mà vẫn giữ hệ kiểu tĩnh. Loại bỏ kiểu viết tường minh khỏi field sẽ ảnh hưởng tới **hợp đồng của lớp**, không chỉ một dòng triển khai:

1. **Mô tả class file:** field có tên và kiểu cụ thể được ghi vào class file. Bytecode truy cập field liên kết dựa trên các mô tả kiểu đó.
2. **Tính ổn định của hợp đồng:** nếu kiểu field tự suy ra từ biểu thức khởi tạo, sửa một chi tiết bên phải có thể vô tình thay đổi kiểu field, làm ảnh hưởng mã gọi hoặc khả năng tương thích nhị phân.
3. **Dễ đọc và bảo trì:** khi đọc định nghĩa một lớp, kiểu của trạng thái được biểu thị rõ ràng mà không cần lần theo biểu thức khởi tạo. Điều này đặc biệt hữu ích với field `public`/`protected` hoặc cấu trúc dữ liệu dùng lâu dài.
4. **Quy tắc thống nhất:** ngay cả field `private` cũng phải viết kiểu tường minh; Java không đặt hai bộ quy tắc riêng cho field công khai và field riêng tư.

Ví dụ thiết kế API:

~~~java
class Store {
    // Kiểu công khai của trạng thái là List<String>;
    // người cài đặt có thể thay ArrayList bằng lớp khác phù hợp.
    private final java.util.List<String> items = new java.util.ArrayList<>();
}
~~~

Đổi `new ArrayList<>()` thành một triển khai phù hợp khác vẫn giữ được kiểu khai báo `List<String>`. Nếu cho phép suy luận kiểu field từ biểu thức khởi tạo thì sự ổn định đó không còn rõ ràng tại nơi khai báo. Vì vậy, với field, hãy chủ động chọn kiểu biểu đạt hợp đồng mong muốn.

## 4. Ví dụ hoàn chỉnh: field viết rõ kiểu, local variable dùng `var`

Chương trình sau là Java hợp lệ từ Java 10 và chạy được trên Java 17+. Có đủ field đối tượng, field `static final`, biến cục bộ trong `static` initializer, constructor, method và `main`.

~~~java
// File: VarFieldDemo.java
import java.util.ArrayList;
import java.util.List;

public class VarFieldDemo {
    private static final int MAX_NOTES;
    private final List<String> notes = new ArrayList<>();
    private final String owner;

    static {
        var configuredLimit = 3;  // Local variable trong static initializer: hợp lệ
        MAX_NOTES = configuredLimit; // Gán giá trị cho static field kiểu int
    }

    public VarFieldDemo(String owner) {
        this.owner = owner; // Gán cho field đã khai báo kiểu String
        var initialNotes = List.of("Java", "SE"); // Local variable: hợp lệ
        notes.addAll(initialNotes);
    }

    public void addNote(String note) {
        var cleaned = note.trim(); // Local variable kiểu String
        if (notes.size() < MAX_NOTES) {
            notes.add(cleaned);
        }
    }

    public String summary() {
        var count = notes.size(); // Local variable kiểu int
        return owner + " (" + count + "): " + notes;
    }

    public static void main(String[] args) {
        var demo = new VarFieldDemo("team"); // Local variable kiểu VarFieldDemo
        demo.addNote("  var  ");
        System.out.println(demo.summary());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `VarFieldDemo.java`:

~~~bash
javac VarFieldDemo.java
java VarFieldDemo
~~~

Đầu ra chuẩn xác:

~~~text
team (3): [Java, SE, var]
~~~

Điểm cần quan sát:

- `MAX_NOTES` là **field** có kiểu khai báo `int`; `configuredLimit` chỉ là **biến cục bộ** trong khối `static`, dù cả hai nằm gần nhau.
- `notes` là **field** có kiểu `List<String>`. Biểu thức `new ArrayList<>()` được gán hợp lệ nhờ kiểu đích tường minh; không có `var` ở khai báo field.
- `owner` là **field** kiểu `String`, còn `owner` trong chữ ký constructor là **tham số** kiểu `String`. Không vị trí nào được thay kiểu bằng `var`.
- `initialNotes`, `cleaned`, `count` và `demo` là các **biến cục bộ** hợp lệ với `var`. Trình biên dịch suy ra kiểu của từng biến từ biểu thức khởi tạo.
- Dù khai báo `var demo` nằm trong phương thức `static main`, biến `demo` **không trở thành field static**. Vị trí khai báo trong khối lệnh mới quyết định tính “cục bộ”.

## 5. Các khai báo sai và cách sửa

Ví dụ **cố ý không biên dịch**, chỉ dùng để nhận diện lỗi:

~~~java
// Các dòng khai báo sau đều KHÔNG hợp lệ.
class InvalidFields {
    var title = "Java";              // Sai: instance field
    private var owner = "team";       // Sai: private field
    static var release = 10;         // Sai: static field
    private final var enabled = true; // Sai: final instance field
}
~~~

Cách sửa là viết **tên kiểu cụ thể**, không cần thay đổi ý nghĩa của field:

~~~java
class ValidFields {
    String title = "Java";
    private String owner = "team";
    static int release = 10;
    private final boolean enabled = true;
}
~~~

Chạy `javac` với `InvalidFields` sẽ báo lỗi biên dịch vì `var` không được dùng trong khai báo field. Không nên phụ thuộc vào nguyên văn thông báo lỗi; câu chữ và vị trí chỉ lỗi có thể khác giữa các phiên bản trình biên dịch.

**Sai lầm cần tránh:** thấy khai báo có giá trị khởi tạo `= ...` rồi kết luận `var` luôn hợp lệ. Điều kiện có initializer chỉ là **một điều kiện cần của một số khai báo local variable**; nó không làm cho field có thể dùng `var`.

## 6. Những ngữ cảnh dễ nhầm lẫn

### 6.1. Field được gán từ biến cục bộ dùng `var`

Hoàn toàn được phép:

~~~java
class Configuration {
    private final String key;

    Configuration(String raw) {
        var normalized = raw.trim().toLowerCase();
        this.key = normalized;
    }
}
~~~

`normalized` dùng `var` vì nó là biến cục bộ trong constructor; `key` vẫn khai báo kiểu `String`. Cú pháp `this.key = normalized;` là **phép gán vào field đã có**, không phải khai báo field mới.

### 6.2. Khối `static` và instance initializer không biến biến cục bộ thành field

~~~java
class Defaults {
    private static final int MAX;
    private final String label;

    static {
        var base = 2; // Local variable, tồn tại trong khối static
        MAX = base + 1;
    }

    {
        var prefix = "Java"; // Local variable, tồn tại trong instance initializer
        label = prefix + " SE";
    }
}
~~~

Biến `base` và `prefix` được phép dùng `var`. Trường `MAX` và `label` phải có kiểu tường minh. Chỉ vì mã nằm trong thân lớp hoặc khối khởi tạo field mà biến đó không tự động thành field.

### 6.3. `final var` vẫn chỉ hợp lệ với biến cục bộ

~~~java
void demo() {
    final var message = "Java"; // Hợp lệ: local variable suy luận String
    // message = "Other";      // Sai nếu bỏ chú thích: không thể gán lại final
}
~~~

`final` hạn chế việc **gán lại biến**; nó không thay đổi vị trí mà `var` được phép xuất hiện. Vì vậy `private final var message = "Java";` ở cấp field vẫn sai. Đồng thời, `final` trên biến tham chiếu không tự động làm đối tượng mà nó trỏ tới trở thành bất biến.

### 6.4. Biến cục bộ nhận giá trị của field vẫn có kiểu tĩnh

~~~java
class Service {
    private final java.util.List<String> data = new java.util.ArrayList<>();

    void inspect() {
        var alias = this.data; // Suy luận List<String>, theo kiểu khai báo field
        System.out.println(alias.size());
    }
}
~~~

`alias` lấy kiểu tĩnh `List<String>` của biểu thức `this.data`. Nó không tự động trở thành `ArrayList<String>` chỉ vì đối tượng thực tế được tạo bằng `new ArrayList<>()`. Lựa chọn kiểu khai báo field ảnh hưởng tới kiểu mà mã gọi nhìn thấy.

Nếu dùng `var local = new ArrayList<String>();`, kiểu cục bộ sẽ được suy luận thành `ArrayList<String>`. Đó là hành vi suy luận kiểu tĩnh của local variable, **không phải** suy luận kiểu cho field.

### 6.5. Tên biến `var` và từ `var` làm kiểu là hai chuyện khác nhau

`var` là *restricted type identifier* trong ngữ cảnh cú pháp liên quan; Java không cấm dùng chữ `var` làm tên một biến thông thường:

~~~java
class Naming {
    private String var = "field name"; // Hợp lệ nhưng dễ gây hiểu nhầm

    void print() {
        var text = var; // var đầu chỉ kiểu suy luận của local; var sau là tên field
        System.out.println(text);
    }
}
~~~

Tuy hợp lệ, nên đặt tên có ý nghĩa hơn `var` để tránh nhầm với cú pháp suy luận kiểu. Quy tắc này không mở đường cho việc dùng `var` như một **kiểu field**.

## 7. Nên thiết kế field như thế nào?

Khi thấy muốn viết `private var field = expression;`, hãy xác định kiểu dữ liệu thể hiện rõ ý nghĩa và ràng buộc của field. Sau đó giữ `var` ở những biến cục bộ mà kiểu đã hiển nhiên:

~~~java
import java.util.ArrayList;
import java.util.List;

class TaskBoard {
    // Field: công bố kiểu trừu tượng List<String> trong nội bộ lớp.
    private final List<String> tasks = new ArrayList<>();

    void add(String raw) {
        var normalized = raw.strip(); // Local: kiểu String rất rõ
        tasks.add(normalized);
    }

    List<String> snapshot() {
        return List.copyOf(tasks);
    }
}
~~~

Mã trên biên dịch được trên Java 17+. `tasks` được khai báo qua interface `List<String>`, giảm phụ thuộc vào chi tiết `ArrayList`. `normalized` dùng `var` vì kiểu `String` dễ suy ra từ `strip()`; `snapshot()` công khai kiểu trả về tường minh. `List.copyOf` trả về danh sách không thể sửa chứa các phần tử ở thời điểm gọi (các phần tử bên trong vẫn có thể tự thay đổi nếu thuộc kiểu mutable).

**Khi chọn kiểu field, cân nhắc:**

- Ưu tiên kiểu tường minh diễn tả hợp đồng: `List<String>`, `Map<String, Integer>`, `Duration`, `String`, `long`, v.v.
- Nếu cần khả năng gọi API riêng của một lớp cụ thể, có thể chọn kiểu lớp cụ thể có chủ đích; `var` không phải công cụ quyết định thay bạn.
- Dùng `final` khi tham chiếu hoặc giá trị field không cần được gán lại sau khởi tạo; đừng hiểu `final` là sự bất biến sâu của đối tượng.
- Không dùng `Object` hoặc một kiểu quá rộng chỉ để mô phỏng ý tưởng “field linh hoạt” của `var`; Java vẫn kiểm tra kiểu tĩnh, và cách đó thường làm mất an toàn kiểu.
- Với field cần thay đổi trong môi trường đa luồng, `var` không liên quan đến visibility hay synchronization. Chọn đúng cơ chế Java Memory Model, `volatile`, khóa hoặc cấu trúc thread-safe theo yêu cầu thực tế.

## 8. Lỗi thường gặp khi học `var`

| Ngộ nhận | Thực tế |
| --- | --- |
| “Đã có initializer thì field dùng `var` được.” | **Sai:** field luôn cần kiểu tường minh. |
| “`private` field không xuất hiện trong API public nên dùng `var` được.” | **Sai:** quy tắc cấm áp dụng cả cho field `private`. |
| “`static` initializer nằm trong lớp nên mọi biến trong đó là field.” | **Sai:** khai báo `var` bên trong khối lệnh `static { ... }` vẫn là local variable. |
| “`final var` là cách khai báo hằng số field.” | **Sai:** `final var` chỉ hợp lệ ở ngữ cảnh `var` được phép, ví dụ local variable. |
| “`var` là dynamic typing nên kiểu đổi theo phép gán sau.” | **Sai:** trình biên dịch xác định một kiểu tĩnh từ initializer. |
| “Java 11 cho phép `var` ở lambda, vậy method parameter hoặc field cũng được.” | **Sai:** đây là quy tắc riêng của tham số lambda; phạm vi field không thay đổi. |
| “`var` là thay thế chung cho mọi tên kiểu.” | **Sai:** nó chỉ được nhận ở những vị trí cú pháp đã quy định. |
| “Tất cả khai báo dùng `var` đều phải có initializer dạng `= ...`.” | Đối với local declaration thông thường, cần biểu thức suy luận kiểu; riêng enhanced `for`/lambda có cú pháp và nguồn suy luận riêng. |

## 9. Bài tự kiểm tra

**Câu 1.** Đoạn nào khai báo field hợp lệ?

~~~java
class A {
    private var id = 1;       // (a)
    private final long id = 1; // (b)
}
~~~

**Đáp án:** (b) là khai báo field hợp lệ; (a) sai. Đây là hai phương án cần xem **riêng rẽ**, không đặt chung vào một lớp khi biên dịch vì trùng tên field `id`.

**Câu 2.** Trong đoạn sau, biến nào được phép dùng `var`?

~~~java
class B {
    private int total;

    B(int initial) {
        var copied = initial;
        total = copied;
    }
}
~~~

**Đáp án:** `copied` được phép vì là local variable trong constructor. `total` là field và `initial` là tham số constructor, cả hai đều khai báo kiểu tường minh.

**Câu 3.** Chuyển `private final List<String> values = new ArrayList<>();` thành `private final var values = new ArrayList<String>();` có hợp lệ không?

**Đáp án:** Không. Việc thay `<>` bằng `<String>` không giải quyết hạn chế vị trí: `values` vẫn là field.

**Câu 4.** Trong `static { var x = 5; }`, `x` có phải field `static` không?

**Đáp án:** Không. `x` là local variable sống trong khối `static`; một field `static` phải được khai báo ở cấp thành viên lớp với kiểu tường minh.

**Câu 5.** Tại sao nên dùng `List<String>` thay vì `ArrayList<String>` cho một field?

**Đáp án:** Khi chỉ cần hợp đồng `List`, kiểu interface giúp mô tả mức trừu tượng phù hợp và cho phép thay đổi lớp triển khai mà không đổi kiểu khai báo. Đây là lựa chọn thiết kế có chủ ý; không phải yêu cầu bắt buộc trong mọi tình huống.

## 10. Tài liệu đối chiếu

- [dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/): xác nhận chỉ sử dụng `var` cho local variable ở các vị trí cho phép, **không dùng cho field**.
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi tính năng được đưa vào Java 10 và lý do giới hạn ở biến cục bộ.
- [OpenJDK — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md): giải thích trường dữ liệu và method return type là một phần hợp đồng kiểu; phân biệt suy luận kiểu tĩnh với dynamic typing.
- [Java Language Specification — Field Declarations (`8.3)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.3): cú pháp và ý nghĩa của field.
- [Java Language Specification — Local Variable Declarations (`14.4)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): cú pháp và giới hạn của local variable với `var`.

**Ghi nhớ:** “Ở cấp thành viên lớp → khai báo field bằng **kiểu tường minh**. Ở trong khối lệnh → có thể cân nhắc `var` cho **local variable** khi trình biên dịch suy luận được kiểu và mã vẫn dễ đọc.”