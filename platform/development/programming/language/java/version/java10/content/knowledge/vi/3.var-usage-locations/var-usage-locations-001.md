# `var` trong thân phương thức, hàm tạo và khối khởi tạo (Java 10+)

## Mục tiêu

Trong Java, `var` giúp trình biên dịch **suy luận kiểu của biến cục bộ từ biểu thức khởi tạo**. Tính năng Local-Variable Type Inference được giới thiệu ở Java 10 và vẫn được hỗ trợ trong các phiên bản Java hiện đại. Nó giúp giảm phần khai báo kiểu lặp lại, nhưng **không biến Java thành ngôn ngữ có kiểu động**.

Bài này tập trung vào ba vị trí đặt câu lệnh khai báo biến cục bộ hợp lệ:

1. **Trong thân phương thức**: phương thức thường, phương thức `static`, `main` và các khối lệnh lồng trong chúng.
2. **Trong thân hàm tạo (constructor)**: biến dùng tạm để kiểm tra, chuẩn hóa và chuyển đổi đầu vào trước khi gán vào field.
3. **Trong khối khởi tạo của lớp**: khối khởi tạo đối tượng `{ ... }` và khối khởi tạo tĩnh `static { ... }`.

Điểm chung: `var` xuất hiện **bên trong một khối lệnh thực thi**, khai báo một **biến cục bộ**. Không thể thay kiểu khai báo của field, tham số phương thức/hàm tạo hay kiểu trả về bằng `var`.

## 1. Hiểu chính xác `var` suy luận điều gì

So sánh hai câu lệnh tương đương về kiểu:

```java
String greeting = "Xin chào";
var message = "Xin chào"; // compiler suy luận String
```

`message` có kiểu **`String` cố định ngay lúc biên dịch**. Sau đó `message = "Hello";` hợp lệ, nhưng `message = 42;` là lỗi biên dịch. Trình biên dịch dựa vào **kiểu của biểu thức khởi tạo ngay tại câu khai báo**, không quan sát các phép gán ở những dòng phía sau.

Một số ví dụ:

```java
var attempts = 3;                  // int (kiểu nguyên thủy)
var ratio = 0.5;                   // double
var title = "Java";                // String
var tags = java.util.List.of("a", "b"); // List<String>
var sample = new int[] {1, 2, 3}; // int[]
final var timeoutSeconds = 30;    // final int
```

`var` **không tự đồng nghĩa với `final`** và không thay đổi khả năng sửa nội dung của đối tượng. `final var timeoutSeconds` chỉ chặn việc gán lại biến; với biến tham chiếu tới một đối tượng mutable, `final` vẫn không đóng băng trạng thái đối tượng ấy.

Điểm cần nhớ: đây là tính năng của **ngôn ngữ và compiler**; không có một kiểu runtime tên `var` được tạo ra cho biến. Khi đọc mã, có thể thay chữ `var` bằng kiểu được suy luận để hiểu các phép gán và lời gọi phương thức có hợp lệ hay không.

## 2. Trong thân phương thức: xử lý dữ liệu ngắn gọn, vẫn kiểm tra kiểu tĩnh

`var` hợp lệ với biến cục bộ có biểu thức khởi tạo trong thân phương thức instance hoặc `static`:

```java
import java.util.Locale;

public class LabelFormatter {
    public String format(String input) {
        var trimmed = input.trim();                    // String
        var normalized = trimmed.toLowerCase(Locale.ROOT); // String
        var length = normalized.length();              // int

        return normalized + " (" + length + ")";
    }
}
```

Ở đây `String` và `int` được xác định tại thời điểm biên dịch. Biến `trimmed`, `normalized` và `length` chỉ có phạm vi sử dụng trong phương thức `format`, từ câu khai báo đến hết khối phù hợp. Chúng **không phải field** và không trở thành thuộc tính của đối tượng `LabelFormatter` sau khi phương thức kết thúc.

Cũng có thể khai báo `var` trong các khối lệnh lồng bên trong phương thức:

```java
void printUppercase(java.util.List<String> words) {
    for (var word : words) { // kiểu của phần tử: String
        var upper = word.toUpperCase(java.util.Locale.ROOT);
        System.out.println(upper);
    }

    for (var index = 0; index < words.size(); index++) { // int
        System.out.println(words.get(index));
    }

    if (!words.isEmpty()) {
        var first = words.get(0); // String; chỉ trong khối if
        System.out.println("First: " + first);
    }
}
```

Đây là **đoạn phương thức minh họa để đặt trong một class**, không phải tệp Java tự chạy. `var word` trong `for-each` suy luận từ kiểu phần tử của `words`; nó không có `= initializer` riêng ở phần khai báo, vì nguồn duyệt cung cấp kiểu. `var index = 0` trong vòng `for` thường suy luận `int` từ `0`. Biến `first` không còn trong phạm vi sau dấu `}` của khối `if`.

Ngoài ra, trong phương thức, cú pháp khai báo tài nguyên `try (var resource = ...)` cũng dùng suy luận kiểu cục bộ (chẳng hạn biến reader tạo bởi `Files.newBufferedReader(...)`); tài nguyên vẫn phải đáp ứng các quy tắc của `try-with-resources`. Đây là những vị trí **bổ sung cho biến cục bộ trong thân phương thức**, không phải một khả năng khai báo field mới.

## 3. Trong thân hàm tạo: biến tạm để chuẩn hóa đầu vào

Tham số constructor có kiểu khai báo rõ ràng, nhưng biến tạo **bên trong thân constructor** có thể dùng `var`:

```java
import java.util.List;
import java.util.Locale;

public final class LessonConfig {
    private final String name;
    private final List<String> topics;

    public LessonConfig(String rawName) {
        var cleaned = rawName.trim();                  // String
        var normalized = cleaned.toLowerCase(Locale.ROOT); // String
        var selectedTopics = List.of(normalized, "java");  // List<String>

        this.name = normalized;
        this.topics = selectedTopics;
    }

    public String name() {
        return name;
    }

    public List<String> topics() {
        return topics;
    }
}
```

Đây là một class độc lập có thể biên dịch, nhưng không có `main` nên không tự chạy qua lệnh `java LessonConfig`. Phần quan trọng nằm ở sự tách biệt giữa:

- **Field** `name`, `topics`: bắt buộc khai báo kiểu rõ ràng, tồn tại như trạng thái của object.
- **Tham số** `String rawName`: phải có kiểu rõ ràng trong khai báo constructor.
- **Biến cục bộ** `cleaned`, `normalized`, `selectedTopics`: được `var` suy luận kiểu trong thân constructor và chỉ phục vụ quá trình khởi tạo.

`this.name = normalized;` là phép gán từ một biến cục bộ vào field, không biến biến `normalized` thành field. Khi constructor kết thúc, field `name` và `topics` còn thuộc về object; các biến cục bộ không còn trong phạm vi.

Thực tế, constructor thường là nơi tốt để dùng `var` cho các kết quả rõ kiểu như `trim()`, `toLowerCase(...)`, thao tác parse và việc tạo collection. Với biểu thức trả về kiểu khó đoán hoặc có ý nghĩa API quan trọng, nên cân nhắc ghi kiểu cụ thể để mã dễ đọc.

## 4. Trong khối khởi tạo: phân biệt `static { }` và `{ }`

Trong thân một class, Java có **hai loại initializer block**. Cả hai đều chứa các câu lệnh thực thi và có thể khai báo biến cục bộ bằng `var`.

### 4.1. Khối tĩnh `static { ... }`

```java
public class Limits {
    private static final int MAX_ITEMS;

    static {
        var base = 2;   // int, biến cục bộ của static block
        var extra = 1;  // int
        MAX_ITEMS = base + extra;
    }
}
```

Khối `static` chạy khi lớp được khởi tạo theo quy tắc của JVM, thường trước khi lớp được sử dụng tích cực lần đầu. Nó không chạy lại mỗi lần tạo object mới. `base` và `extra` chỉ dùng trong khối tĩnh; `MAX_ITEMS` mới là **field static** tồn tại để các phương thức khác sử dụng.

Vì đang ở ngữ cảnh `static`, mã trong khối này không thể dùng `this` hoặc trực tiếp truy cập field instance không thông qua đối tượng. `var` không thay đổi quy tắc ấy.

### 4.2. Khối khởi tạo đối tượng `{ ... }`

```java
public class DisplaySettings {
    private String prefix;

    {
        var fallback = "Course"; // String, biến cục bộ
        prefix = fallback;       // gán vào instance field
    }

    public DisplaySettings() {
        // Khối khởi tạo instance chạy trước thân constructor này.
    }

    public String prefix() {
        return prefix;
    }
}
```

Khối không có chữ `static` là **instance initializer**. Nó được thực hiện khi mỗi đối tượng được tạo, trong giai đoạn khởi tạo instance trước phần thân constructor tương ứng. Nó thường dùng để chia sẻ một phần logic khởi tạo giữa nhiều constructor, nhưng với trường hợp đơn giản, gán ngay tại khai báo field hoặc khởi tạo trong constructor thường dễ hiểu hơn.

Các điểm quan trọng về thứ tự:

1. Việc khởi tạo class (bao gồm các field/khối `static` tương ứng) xảy ra theo quy tắc class initialization; không phụ thuộc vào mỗi lần gọi constructor.
2. Khi tạo instance, quá trình khởi tạo của superclass được xử lý trước các field initializer và instance initializer của chính class này.
3. Các field initializer và instance initializer của class được thực hiện theo **thứ tự xuất hiện trong mã nguồn**, trước phần thân constructor của class.
4. Biến `var fallback` chỉ có phạm vi trong instance initializer; field `prefix` mới còn tồn tại sau khi khối kết thúc.

Không được nhầm:

```java
class Example {
    // var count = 1;    // SAI: khai báo field bằng var
    int count = 1;       // ĐÚNG: kiểu field tường minh

    static {
        var local = 1;   // ĐÚNG: biến cục bộ trong static block
    }

    {
        var local = 2;   // ĐÚNG: biến cục bộ trong instance block
    }
}
```

## 5. Ví dụ hoàn chỉnh: cả ba vị trí trong cùng một chương trình

Tạo tệp tên **`VarScopeDemo.java`** với nội dung sau; mã dùng API và cú pháp phù hợp từ Java 10, đồng thời chạy được trên Java 17+:

```java
import java.util.List;
import java.util.Locale;

public final class VarScopeDemo {
    private static final int MAX_ITEMS;

    // Khối khởi tạo tĩnh: local var, chạy khi class khởi tạo.
    static {
        var base = 2;
        var extra = 1;
        MAX_ITEMS = base + extra;
    }

    private String prefix;
    private final List<String> tags;

    // Khối khởi tạo instance: local var, chạy khi tạo từng object.
    {
        var defaultPrefix = "Course";
        prefix = defaultPrefix;
    }

    // Thân constructor: local var để chuẩn hóa dữ liệu đầu vào.
    public VarScopeDemo(String raw) {
        var normalized = raw.trim().toLowerCase(Locale.ROOT);
        tags = List.of(normalized, "java");
    }

    // Thân phương thức: local var lưu kết quả trung gian.
    public String describe() {
        var joined = String.join(", ", tags);
        var description = prefix + ": " + joined + " | max=" + MAX_ITEMS;
        return description;
    }

    public static void main(String[] args) {
        var example = new VarScopeDemo("  VAR  ");
        System.out.println(example.describe());

        var count = 2;
        count++;
        System.out.println("count=" + count);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 10 VarScopeDemo.java
java VarScopeDemo
```

Đầu ra chính xác:

```text
Course: var, java | max=3
count=3
```

Giải thích theo tiến trình:

- Khi khởi tạo class `VarScopeDemo`, khối `static` dùng hai biến cục bộ kiểu `int` để tính `MAX_ITEMS = 3`. Field `MAX_ITEMS` có kiểu tường minh `int`.
- Khi `new VarScopeDemo("  VAR  ")` tạo instance, instance initializer gán `prefix = "Course"`. Sau đó constructor chuẩn hóa đối số thành `"var"` và gán field `tags` thành `["var", "java"]`.
- Trong `describe()`, `joined` và `description` được suy luận là `String`, rồi trả về thông điệp.
- Trong `main()`, `example` được suy luận là `VarScopeDemo`, `count` là `int`. Dòng `count++` hợp lệ vì `var` không mặc định làm biến `final`.

Lưu ý: ví dụ cố ý dùng đủ ba vị trí để minh họa. Trong ứng dụng thực tế, khối `static` hoặc instance initializer chỉ nên tồn tại khi có lý do thiết kế rõ ràng; `var` tự nó **không tạo ra nhu cầu dùng initializer block**.

## 6. Ranh giới cú pháp: cái gì hợp lệ, cái gì bị compiler từ chối?

| Vị trí khai báo | Dùng `var`? | Lý do |
| --- | --- | --- |
| Biến trong phương thức thường/`static`/`main` | Có | Biến cục bộ, có dữ liệu để suy luận kiểu. |
| Biến trong constructor | Có | Biến cục bộ nằm trong thân constructor. |
| Biến trong `static { ... }` | Có | Biến cục bộ của static initializer. |
| Biến trong `{ ... }` của instance | Có | Biến cục bộ của instance initializer. |
| Biến đếm trong `for`, phần tử trong `for-each` | Có | Cả hai là biến cục bộ với ngữ cảnh suy luận kiểu phù hợp. |
| Biến tài nguyên khai báo trong `try-with-resources` | Có | Kiểu được suy luận từ biểu thức tạo tài nguyên. |
| Instance field hoặc `static` field | Không | Field là thành viên class, cần kiểu khai báo. |
| Tham số phương thức và tham số constructor | Không | Chữ ký phương thức/constructor cần kiểu rõ ràng. |
| Kiểu trả về của phương thức | Không | Không được suy luận return type của phương thức bằng `var`. |

Đoạn sau **cố ý minh họa cú pháp không hợp lệ, không phải tệp để biên dịch**:

```java
class InvalidLocations {
    // var name = "Java";                   // SAI: var không dành cho field
    // InvalidLocations(var input) {}        // SAI: tham số constructor
    // void setName(var input) {}            // SAI: tham số phương thức
    // var getName() { return "Java"; }      // SAI: kiểu trả về

    InvalidLocations(String input) {
        var name = input.trim();            // ĐÚNG: biến trong constructor
    }

    void run() {
        var count = 1;                      // ĐÚNG: biến trong method
    }
}
```

**Ngoại lệ khác phiên bản:** từ Java 11, `var` còn được phép trong cú pháp **tham số lambda kiểu suy luận** theo JEP 323, ví dụ `(var left, var right) -> left + right` khi có target functional interface phù hợp. Điều này **không** làm `var` hợp lệ trong danh sách tham số khai báo của phương thức hoặc constructor, và không thuộc tính năng nguyên bản của Java 10. Phần cốt lõi của bài này vẫn là biến cục bộ trong các khối thực thi.

## 7. Quy tắc khởi tạo và các lỗi cú pháp dễ mắc

Trong một câu khai báo biến cục bộ thông thường, `var` cần biểu thức khởi tạo đủ để compiler xác định kiểu **ngay tại chỗ**:

```java
var score = 10;                     // ĐÚNG: int
var words = new String[] {"a", "b"}; // ĐÚNG: String[]
var label = (String) null;          // HỢP LỆ về kiểu, nhưng ít khi cần thiết

// Các dòng dưới đều SAI nếu bỏ dấu //:
// var pending;                      // Không có initializer để suy luận kiểu.
// var unknown = null;               // null thuần túy không xác định được kiểu.
// var values = {"a", "b"};           // Array initializer cần target type.
// var a = 1, b = 2;                 // var không dùng để khai báo nhiều biến một câu.
// var transform = x -> x + 1;       // Lambda chưa có target functional interface.
// var ref = String::valueOf;        // Method reference cũng cần target type.
```

Nếu cần lambda/method reference, hãy khai báo functional interface rõ kiểu:

```java
java.util.function.Function<String, Integer> length = String::length;
```

Nếu dữ liệu có thể `null`, hãy quyết định kiểu một cách tường minh và xử lý null theo hợp đồng của API. `var label = (String) null` có thể biên dịch nhưng không phải chiến lược khởi tạo tốt cho biến tạm; khi cần biến chưa có giá trị, khai báo kiểu tường minh giúp ý định rõ hơn.

**Chú ý phân biệt với `for-each`:** `for (var element : elements)` là cú pháp hợp lệ dù không có dấu `=`, vì iterable/array ở vế phải dấu `:` cung cấp kiểu phần tử. Nó không phải một `var element;` đứng độc lập.

## 8. Suy luận kiểu từ initializer: các bẫy có ảnh hưởng đến thiết kế mã

### 8.1. Kiểu của biến không biến đổi theo lần gán sau

```java
var total = 1; // int
total = 2;     // ĐÚNG

// total = 2.5;  // SAI: double không gán trực tiếp vào int.
// total = "2";  // SAI: String không phải int.
```

Compiler suy luận `int` ngay khi thấy literal `1`. Nếu bài toán thật sự cần `double`, viết `var total = 1.0;` hoặc `double total = 1;`. Đừng trông chờ compiler đổi kiểu vì phép gán về sau.

### 8.2. `var` có thể suy luận implementation cụ thể thay cho interface

```java
var names = new java.util.ArrayList<String>(); // ArrayList<String>
java.util.List<String> otherNames = new java.util.ArrayList<>();
```

Trong câu thứ nhất, kiểu khai báo là `ArrayList<String>`, **không tự được nâng thành `List<String>`**. Khi cần biểu thị rõ hợp đồng interface trong mã, khai báo `List<String>` hoặc `Collection<String>` đôi khi tốt hơn, kể cả khi dài hơn.

### 8.3. `var` kết hợp với diamond `<>` có thể làm mất kiểu phần tử mong muốn

```java
var mixed = new java.util.ArrayList<>(); // ArrayList<Object>
mixed.add("java");
mixed.add(42);                            // Hợp lệ: Object

var names = new java.util.ArrayList<String>(); // ArrayList<String>
names.add("java");
// names.add(42);                         // SAI: không phải String
```

Với `new ArrayList<>()` không có kiểu đích cụ thể ở bên trái, compiler có thể suy luận tham số kiểu là `Object`. Nếu cần `List<String>`, nên ghi kiểu phần tử ở constructor như ví dụ, hoặc giữ kiểu tường minh bên trái:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

Đây là một trong những trường hợp **ghi thêm kiểu làm API nội bộ an toàn và dễ hiểu hơn**. Không xem `var` là lựa chọn bắt buộc cho mọi local variable.

### 8.4. Dữ liệu đầu vào và sự rõ ràng quan trọng hơn tiết kiệm ký tự

```java
var result = service.fetch(id); // Nếu không biết fetch trả về gì, khó đọc.
UserProfile profile = service.fetch(id); // Nêu hợp đồng rõ hơn.
```

Hai dòng trên chỉ minh họa cách trình bày trong một ứng dụng **giả định đã định nghĩa `service`, `id` và `UserProfile`**; không phải chương trình Java độc lập. Có thể dùng `var` khi biểu thức khởi tạo tự thể hiện kiểu, ví dụ `var user = new UserProfile(...);`; khi cần biết kiểu mà phải lục tìm API khác, khai báo tường minh thường giúp người bảo trì hơn.

## 9. Phạm vi (scope), vòng đời và luồng khởi tạo

Cùng một chữ `var` nhưng vòng đời của biến vẫn tuân theo **vị trí khai báo**:

- **Trong method:** biến tồn tại về mặt phạm vi trong khối tương ứng và chỉ dùng khi phương thức đang thực thi. Sau khi return, không thể truy cập biến đó từ nơi gọi.
- **Trong constructor:** biến được dùng trong quá trình tạo object; các giá trị cần giữ lại phải được gán vào field hoặc đưa vào một đối tượng được lưu trữ.
- **Trong `static initializer`:** biến chỉ có phạm vi trong khối `static { }`. Khối được thực hiện khi class được khởi tạo; field static được gán trong khối mới có thể được dùng ở nơi khác.
- **Trong instance initializer:** biến chỉ có phạm vi trong khối `{ }`. Khối chạy cho từng instance trước thân constructor; field instance được cập nhật trong khối là trạng thái của đối tượng.
- **Trong `if`/`for`/`try` lồng nhau:** các biến cục bộ tuân theo phạm vi block, vòng lặp và try-resource tương ứng; không thể dùng ngoài phạm vi ấy.

Không nên cố biến `var` thành field để chia sẻ một biến local giữa các phương thức. Nếu cần giữ trạng thái, thiết kế field có kiểu tường minh; nếu chỉ cần giá trị tính toán ngắn hạn, dùng local variable đúng vị trí.

## 10. Chọn `var` hay kiểu tường minh?

Một quy tắc thực dụng:

1. Dùng `var` khi **initializer cho biết rõ kiểu**: `var list = new ArrayList<String>();`, `var count = 0;`, `var normalized = text.trim();`.
2. Giữ **kiểu khai báo tường minh ở API và field** vì Java bắt buộc và vì đó là hợp đồng giữa các phần của chương trình.
3. Trong method hoặc constructor, giữ kiểu tường minh khi kiểu có ý nghĩa nghiệp vụ, kiểu trả về của lời gọi chưa rõ, hoặc cần mở rộng từ implementation sang interface.
4. Với `static`/instance initializer, ưu tiên mã khởi tạo ngắn, dễ kiểm tra; dùng initializer block khi có lợi ích thật sự, không lập block chỉ để viết `var`.
5. Để tăng khả năng đọc, đặt tên biến thể hiện nội dung như `normalizedName`, `totalCount`, `customerIds`. `var` lược bỏ chữ tên kiểu, nên tên biến và biểu thức khởi tạo càng quan trọng.

Trong mã production hiện nay, `var` không phải tính năng lỗi thời hay đã bị thay thế. Nó vẫn là một công cụ phổ biến cho **local variable type inference**; giá trị của nó nằm ở việc giúp mã gọn mà vẫn giữ được khả năng hiểu kiểu và kiểm tra biên dịch.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong `public Order(String code) { var normalized = code.trim(); }`, `var` hợp lệ không? `normalized` có tồn tại như field sau khi constructor hoàn tất không?

**Đáp án:** Hợp lệ vì là biến cục bộ trong thân constructor; compiler suy luận `String`. Nó không phải field. Nếu muốn lưu giá trị, phải gán vào một field hoặc lưu trong object khác.

**Câu 2.** `static { var threshold = 10; }` chạy mỗi khi tạo một object mới hay khi class được khởi tạo?

**Đáp án:** Khi class được khởi tạo theo quy tắc JVM, không phải mỗi lần tạo instance. Biến `threshold` chỉ có phạm vi trong khối tĩnh.

**Câu 3.** `{ var fallback = "N/A"; }` nằm trực tiếp trong class có hợp lệ không? `fallback` có thể được gọi từ phương thức khác không?

**Đáp án:** Hợp lệ: đây là biến cục bộ của **instance initializer**. Không thể truy cập `fallback` từ phương thức khác; chỉ có field được gán trong khối mới lưu lại trạng thái.

**Câu 4.** Vì sao `var labels = new ArrayList<>();` có nguy cơ suy luận `ArrayList<Object>`?

**Đáp án:** Không có thông tin kiểu phần tử rõ ràng ở constructor hoặc kiểu đích phía trái. Dùng `new ArrayList<String>()` hoặc khai báo `List<String> labels = new ArrayList<>();` để bảo đảm danh sách chỉ nhận `String`.

**Câu 5.** `var answer = 1; answer = "one";` có hợp lệ không?

**Đáp án:** Không. `answer` được suy luận kiểu `int` từ `1`, và việc gán `String` sẽ bị compiler từ chối.

## Tham khảo chính thức, vẫn có hiệu lực

- [Dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/): phạm vi sử dụng, suy luận kiểu và các giới hạn của `var`.
- [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): đặc tả tính năng được đưa vào từ Java 10.
- [OpenJDK — Local Variable Type Inference: Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): các nguyên tắc giữ khả năng đọc mã khi dùng `var`.
- [Oracle — Java Language Changes](https://docs.oracle.com/en/java/javase/11/language/java-language-changes-release.html): phân biệt tính năng local inference Java 10 với cú pháp tham số lambda từ Java 11.
