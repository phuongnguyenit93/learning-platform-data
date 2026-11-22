# Kiểm tra selector type thực tế khi debug Java Pattern Matching

## 1. Vấn đề: tại sao case không chạy như mình dự đoán?

Với pattern matching trong Java, nhiều lỗi debug xuất phát từ việc nhầm **kiểu tĩnh (static type)** của biểu thức sau `switch (...)` với **kiểu thực tế lúc chạy (runtime type)** của giá trị biểu thức ấy.

Ví dụ, một tham số được khai báo là `Object selector` có thể chứa một `String`, `Integer`, `Long`, record nghiệp vụ, proxy hoặc `null`. Một nhánh `case Integer n` không khớp `Long` mặc dù cả hai đều biểu diễn số nguyên, và `case String s` không khớp `StringBuilder` dù cả hai có ký tự. Nếu chỉ nhìn chữ `Object` ở chữ ký phương thức, bạn chưa biết nhánh nào sẽ được chọn.

Kỹ năng **“Kiểm tra selector type thực tế”** là kết hợp quan sát giá trị/kiểu runtime với việc phân tích **pattern, guard, thứ tự case, null và cấu trúc record** để giải thích chính xác vì sao nhánh `switch` hoặc `instanceof` khớp/không khớp.

Sau bài này, bạn có thể:

- Phân biệt `static type` và `runtime class` của selector, biết lúc nào dùng `getClass()`, `getName()`, `getSimpleName()`.
- Đọc kết quả debug cho `Integer`, `Long`, `Double`, `String`, `CharSequence`, record, component null và selector null.
- Phân biệt **type pattern không khớp** với **type pattern đã khớp nhưng `when` false**.
- Kiểm tra đúng giá trị thật sự được đưa vào `switch`, tránh lẫn đối tượng bên ngoài với component con.
- Dùng log/breakpoint an toàn, không làm selector được đánh giá lại gây side effect.
- Viết tests kiểm tra nhánh đúng dựa trên các kiểu runtime cụ thể.

**Phiên bản:** Type pattern với `instanceof` đã được chuẩn hóa từ Java 16 (JEP 394). Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) chính thức trong **Java 21**. Chương trình chạy đầy đủ ở mục 8 tương thích **JDK 21+** và không cần `--enable-preview`.

## 2. Static type khác runtime type như thế nào?

Xem đoạn sau:

```java
Object selector = 7L;

System.out.println(selector.getClass().getName());       // java.lang.Long
System.out.println(selector.getClass().getSimpleName()); // Long
System.out.println(selector instanceof Integer);         // false
System.out.println(selector instanceof Long);            // true
System.out.println(selector instanceof Number);          // true
```

Biến `selector` được khai báo kiểu **`Object`**, nhưng biểu thức `7L` có kiểu nguyên thủy `long` và được **autobox** thành một đối tượng `Long` khi gán vào `Object`. Vì vậy, runtime class là `java.lang.Long`.

Ba cấp thông tin cần tách bạch:

| Khái niệm | Ví dụ | Vai trò khi debug |
| --- | --- | --- |
| Kiểu tĩnh của selector | `Object` | Compiler dùng để kiểm tra pattern có hợp lệ và switch có đầy đủ trường hợp hay không. |
| Kiểu runtime của giá trị | `java.lang.Long` | Giúp giải thích vì sao `case Long l` khớp và `case Integer i` không khớp. |
| Điều kiện bổ sung sau khi khớp | `when n > 0` | Quyết định nhánh có được chọn tiếp hay không; runtime class đúng chưa đủ. |

Đừng dùng kiểu tĩnh để suy ra kiểu runtime. Một tham số `Number n` có thể đang trỏ tới `Integer`, `Long`, `Double`, `BigDecimal` hoặc implementation khác của `Number`. Một tham số interface có thể trỏ tới bất kỳ implementation hợp lệ nào.

**Quan trọng:** `getClass()` chỉ phản ánh **class của đối tượng thật**. Nó không tự chứng minh đối tượng sẽ khớp nhánh nào nếu các nhánh còn có guard `when` hoặc nested record patterns.

## 3. Cách quan sát kiểu runtime mà không gây NullPointerException

### 3.1. Helper an toàn với null

```java
static String runtimeType(Object value) {
    return value == null ? "null" : value.getClass().getName();
}
```

Nếu value khác null, `value.getClass()` trả về đối tượng `Class<?>` đại diện cho class runtime. `getName()` thường hữu ích khi cần tên đầy đủ để phân biệt hai class cùng tên ngắn nhưng khác package.

Ví dụ:

```java
Object a = "java";
Object b = 12;
Object c = 12L;
Object d = null;

System.out.println(runtimeType(a)); // java.lang.String
System.out.println(runtimeType(b)); // java.lang.Integer
System.out.println(runtimeType(c)); // java.lang.Long
System.out.println(runtimeType(d)); // null
```

**Sai thường gặp** là ghi `selector.getClass().getName()` trước khi xét `null`. Nếu selector null, chính lệnh debug này ném `NullPointerException` và che mất nguyên nhân gốc. Hãy kiểm tra null hoặc dùng helper.

### 3.2. Chọn getName hay getSimpleName?

- `getClass().getSimpleName()`: tên ngắn như `Integer`, `Ready`, `StringBuilder`, dễ nhìn trong demo nhưng **không duy nhất** giữa các package và có thể rỗng với một số class vô danh.
- `getClass().getName()`: tên binary/runtime, ví dụ `java.lang.Integer` hoặc `com.acme.dto.Ready`; class lồng có thể chứa ký tự `$`.
- `getClass().getCanonicalName()`: tên canonical nếu có; có thể trả `null` cho local/anonymous class và một số dạng class khác, nên không mặc định phù hợp với mọi log.
- `getClass().getTypeName()`: tên kiểu dành cho mục đích hiển thị, hữu ích nếu bạn đã có đối tượng `Class<?>`.

Trong chương trình ở mục 8, helper dùng **`getSimpleName()`** để đầu ra ngắn, dễ đối chiếu; khi debug dự án thật, ưu tiên tên đầy đủ và thêm ngữ cảnh request/branch nếu cần.

### 3.3. Array, wrapper và kiểu nguyên thủy

Nếu gán `int x = 7; Object o = x;`, biến `o` chứa `Integer` do boxing. Không có “runtime `int` object” mà `getClass()` trả về cho trường hợp này.

Đối với array, `getName()` dùng biểu diễn binary như `[Ljava.lang.String;` (`String[]`) hoặc `[I` (`int[]`); đừng nhầm chúng với tên package thông thường. Nếu cần debug một array:

```java
static String arrayInfo(Object value) {
    if (value == null) return "null";
    Class<?> c = value.getClass();
    if (!c.isArray()) return "not-array:" + c.getName();
    return "array-component:" + c.getComponentType().getTypeName();
}
```

Đoạn này minh họa truy vấn `Class.isArray()` và `getComponentType()`; không có mục đích thay toàn bộ pattern matching bằng reflection.

## 4. Đặt log đúng vị trí: selector của switch là biểu thức nào?

Giả sử một record chứa dữ liệu khác kiểu:

```java
record Envelope(Object payload) {}

static String route(Envelope envelope) {
    Object selector = envelope.payload();
    return switch (selector) {
        case String s -> "text:" + s;
        case Integer n -> "integer:" + n;
        case null -> "missing payload";
        default -> "other payload";
    };
}
```

Nếu debug `envelope.getClass()`, bạn chỉ nhận `Envelope`, không giải thích được vì sao `case String` hay `case Integer` trong đoạn này được chọn. **Selector của switch là `envelope.payload()`**, không phải chính `envelope`.

Hãy quan sát đúng giá trị:

```java
Object selector = envelope.payload();
String actualType = selector == null
        ? "null"
        : selector.getClass().getName();

// Dùng actualType để log an toàn (không cần ghi raw payload).
return switch (selector) {
    case String s -> "text:" + s;
    case Integer n -> "integer:" + n;
    case null -> "missing payload";
    default -> "other payload";
};
```

Ngoài ra, **không nên gọi lại một getter hoặc phương thức có side effect chỉ để debug**. Ví dụ:

```java
// Không nên khi source.next() có thể lấy phần tử khác nhau ở mỗi lần gọi.
System.out.println(source.next().getClass().getName());
return switch (source.next()) {
    // Các case...
};
```

Đây chỉ là snippet phản ví dụ (`source` và các case chưa được khai báo), không phải tệp Java hoàn chỉnh. Hai lần gọi `source.next()` có thể trả hai giá trị khác nhau: kiểu được in ra không phải kiểu thật của selector đã đi vào switch.

Thay vào đó:

```java
// Minh họa khi source.next() trả Object.
Object selector = source.next();
System.out.println(selector == null ? "null" : selector.getClass().getName());
return switch (selector) {
    case String s -> "text:" + s;
    case null -> "missing";
    default -> "other";
};
```

Trong thực tế, không nhất thiết in lên stdout; có thể dùng logger hoặc debugger. Điều cốt lõi là **lấy selector một lần, dùng cùng giá trị để quan sát và phân nhánh**.

## 5. Runtime type đúng nhưng case vẫn không chạy: kiểm tra thứ tự nhánh

Khi có nhiều type patterns liên quan kế thừa, nhánh rộng và nhánh hẹp có thể khớp cùng một object.

Ví dụ an toàn (Java 21):

```java
static String numberKind(Object selector) {
    return switch (selector) {
        case Integer n -> "integer:" + n;
        case Number n -> "number:" + n;
        case null -> "missing";
        default -> "other";
    };
}
```

Nếu runtime class là `Integer`, hai pattern `Integer` và `Number` đều có thể áp dụng về quan hệ kiểu, nhưng nhánh **`Integer` trước** được chọn. Nếu runtime class là `Long`, nhánh `Integer` không khớp, nhánh `Number` khớp.

Nếu đảo hai nhánh:

```java
// Không biên dịch: case Integer bị case Number đứng trước bao phủ.
return switch (selector) {
    case Number n -> "number:" + n;
    case Integer n -> "integer:" + n;
    default -> "other";
};
```

Compiler Java 21 phát hiện nhánh `Integer` bị **dominated** bởi nhánh `Number` rộng hơn. Đây là lỗi biên dịch, **không phải** tình huống runtime đã chạy nhầm `case`.

Với một chuỗi `if / else if`, điều kiện rộng ở trước có thể đơn giản làm nhánh cụ thể không được chọn; với pattern switch, compiler có thêm kiểm tra tĩnh giúp phát hiện nhiều trường hợp bị che khuất.

### Không nhầm String với CharSequence

Một `StringBuilder` implements `CharSequence`, nhưng không phải `String`:

```java
Object selector = new StringBuilder("abc");
System.out.println(selector instanceof String);       // false
System.out.println(selector instanceof CharSequence); // true
```

Nếu code chỉ có `case String s`, runtime class `StringBuilder` sẽ đi đến nhánh fallback hoặc nhánh `CharSequence` rộng hơn, tùy cách bạn viết `switch`.

**Mẹo debug:** Ghi lại **actual runtime class**, rồi hỏi: class đó có phải subtype/implementation của kiểu pattern đang thử không? Chỉ sau đó mới xét guard và dữ liệu con.

## 6. Case type khớp nhưng guard when false

Nhánh `when` bổ sung điều kiện **sau khi pattern khớp**. Vì vậy, runtime class không thay đổi khi guard false; Java chỉ tiếp tục xét nhánh khác phù hợp.

```java
static String classifyText(Object selector) {
    return switch (selector) {
        case String text when text.isBlank() -> "String:blank";
        case String text -> "String:text=" + text.strip();
        case null -> "null";
        default -> "other";
    };
}
```

Hai đầu vào `"  "` và `"java"` đều có runtime class `String`, nhưng vào hai nhánh khác nhau. Để giải thích nguyên nhân, cần kiểm tra **giá trị và biểu thức `text.isBlank()`**, không chỉ tên class.

Trong một phiên debug, bạn có thể ghi log an toàn kiểu và kết quả của guard:

```java
if (selector instanceof String text) {
    boolean blank = text.isBlank();
    System.out.println("runtimeType=String, blank=" + blank);
}
```

Đoạn này là snippet minh họa dùng selector đã lấy. Tránh ghi toàn bộ text thật nếu đó là thông tin nhạy cảm hoặc có dung lượng lớn; khi đó chỉ ghi `blank`, độ dài hoặc số liệu đã lọc.

**Phân biệt ba trạng thái:**

1. **Pattern không khớp:** ví dụ selector là `Integer`; guard `text.isBlank()` không được đánh giá.
2. **Pattern khớp, guard sai:** selector là `String` không trắng, nhánh có `when` bị bỏ qua.
3. **Pattern khớp, guard đúng:** selector là `String` trắng, nhánh đó được chọn.

Đặt nhánh có `when` cụ thể trước nhánh cùng type không có guard; nếu đặt nhánh không guard lên trước, nhánh cụ thể có thể bị compiler báo `dominated case label`.

## 7. Record patterns: cần xem type của selector lẫn component bên trong

Với Java 21:

```java
record Ready(String id, Object payload) {}
```

Nhánh sau:

```java
// Snippet trong switch expression với Object selector.
case Ready(var id, var payload) when payload instanceof String text
        -> "Ready:" + id + ":string=" + text;
```

có hai tầng kiểm tra:

- Selector phải là một instance record `Ready` khác null.
- Component `payload` phải là một `String` khác null để guard `payload instanceof String text` đúng.

Nếu selector là `new Ready("R2", 42)`, **type của selector vẫn là `Ready`**, nhưng `payload` có runtime class `Integer`. Pattern `Ready(var id, var payload)` khớp; guard `payload instanceof String text` không khớp. Khi có nhánh `case Ready(var id, var payload)` không guard ở phía sau, nó sẽ được chọn.

Nếu selector là `new Ready("R3", null)`, record ngoài vẫn khớp và `var payload` có thể ràng buộc `null`; nhưng guard `payload instanceof String text` là false. Điều này **khác** với nested pattern:

```java
record Message(String text) {}
record Box(Object item) {}

// Snippet với Object selector:
case Box(Message(var text)) -> "message:" + text;
```

Ở đây `Box(Message(...))` không khớp nếu component `item` là null hoặc không phải record `Message`. Ngược lại, khi `Message` tồn tại nhưng component `text` bằng null, `Message(var text)` vẫn có thể khớp và ràng buộc biến `text` bằng null. Nên đặt breakpoints hoặc log đúng tầng:

- **Tầng selector ngoài:** `typeName(selector)`.
- **Tầng component:** `typeName(payload)` hoặc `typeName(item)`.
- **Tầng guard:** biểu thức `payload instanceof String`, `text != null`, `!text.isBlank()` và các điều kiện nghiệp vụ.

Đừng suy luận “selector là `Ready` thì payload chắc chắn là String” khi component được khai báo `Object`. Type system không bảo đảm điều đó. Nếu hợp đồng nghiệp vụ yêu cầu chặt hơn, nên dùng kiểu component cụ thể và validation thích hợp.

## 8. Chương trình Java 21 hoàn chỉnh: in actual type và nhánh được chọn

Tạo tệp **`SelectorRuntimeTypeDemo.java`**:

```java
public class SelectorRuntimeTypeDemo {
    sealed interface Signal permits Ready, Failed {}
    record Ready(String id, Object payload) implements Signal {}
    record Failed(int code) implements Signal {}
    record Box(Object item) {}

    static String typeName(Object value) {
        return value == null ? "null" : value.getClass().getSimpleName();
    }

    static String route(Object selector) {
        return switch (selector) {
            case null -> "selector:null";
            case String text when text.isBlank() -> "String:blank";
            case String text -> "String:text=" + text.strip();
            case Integer number -> "Integer:" + number;
            case Number number -> "Number:" + typeName(number) + "=" + number;
            case Ready(var id, var payload) when payload instanceof String text
                    -> "Ready:" + id + ":string=" + text;
            case Ready(var id, var payload)
                    -> "Ready:" + id + ":payload=" + typeName(payload);
            case Failed(var code) -> "Failed:" + code;
            case Box(var item) -> "Box:item=" + typeName(item);
            default -> "other:" + typeName(selector);
        };
    }

    static String inspect(Object selector) {
        return "type=" + typeName(selector) + " | branch=" + route(selector);
    }

    public static void main(String[] args) {
        Object[] samples = {
            "  java  ", "  ", 7, 7L, 3.5,
            new Ready("R1", "ok"), new Ready("R2", 42),
            new Ready("R3", null), new Failed(404),
            new Box(null), new Box(new StringBuilder("x")),
            new StringBuilder("text"), new Object(), null
        };
        for (Object sample : samples) {
            System.out.println(inspect(sample));
        }
    }
}
```

Biên dịch/chạy với JDK 21+:

```bash
javac --release 21 SelectorRuntimeTypeDemo.java
java SelectorRuntimeTypeDemo
```

**Kết quả chuẩn:**

```text
type=String | branch=String:text=java
type=String | branch=String:blank
type=Integer | branch=Integer:7
type=Long | branch=Number:Long=7
type=Double | branch=Number:Double=3.5
type=Ready | branch=Ready:R1:string=ok
type=Ready | branch=Ready:R2:payload=Integer
type=Ready | branch=Ready:R3:payload=null
type=Failed | branch=Failed:404
type=Box | branch=Box:item=null
type=Box | branch=Box:item=StringBuilder
type=StringBuilder | branch=other:StringBuilder
type=Object | branch=other:Object
type=null | branch=selector:null
```

**Giải thích theo từng nhóm:**

1. `"  java  "` và `"  "` đều là `String`. Chuỗi thứ hai thỏa `isBlank()` nên vào nhánh `String:blank`; chuỗi thứ nhất không trắng nên nhánh tiếp theo strip khoảng trắng, trả `String:text=java`.
2. `7` được box thành `Integer`, vào `case Integer number`. `7L` được box thành `Long`, **không khớp Integer**, nhưng khớp `Number`. `3.5` là `Double`, cũng khớp `Number`.
3. `Ready("R1", "ok")`: selector là `Ready`; payload là `String` nên guard `payload instanceof String text` đúng.
4. `Ready("R2", 42)`: selector vẫn là `Ready`; payload là `Integer` nên guard thất bại và vào nhánh `Ready` không guard.
5. `Ready("R3", null)`: selector không null nhưng **component payload null**; nhánh `Ready` không guard trả `payload=null`.
6. `Failed(404)` và `Box(...)` được xử lý bằng pattern record tương ứng. `Box(null)` chứng minh record ngoài khớp dù một component `var` là null.
7. `StringBuilder` có thể dùng như `CharSequence`, nhưng không phải `String`. Vì ví dụ không có nhánh `CharSequence`, nó đi vào `default`.
8. `new Object()` không thuộc các loại được hỗ trợ nên đi vào `default`.
9. Null selector vào `case null`, và helper `typeName` tránh gọi `getClass()` trên null.

**Lưu ý:** Helper `typeName` sử dụng `getSimpleName()` để minh họa ngắn gọn và có stdout ổn định. Trong hệ thống thực tế, sử dụng `getName()` để phân biệt class trùng tên từ các package khác nhau; thêm class loader/module khi điều tra các lỗi loading phức tạp.

## 9. Quy trình debug khi nhánh switch không được chọn

Khi một case “đáng lẽ phải match” không chạy, áp dụng trình tự sau:

### Bước 1: xác định biểu thức selector thực sự

Đọc nguyên biểu thức sau `switch (...)`. Nếu selector là `message.payload()`, quan sát **kết quả của `payload()`**, không phải class của `message`. Nếu là một lời gọi có side effect, gán vào biến cục bộ trước để không vô tình đánh giá hai lần.

### Bước 2: ghi runtime class an toàn với null

```java
Object selector = obtainSelector();
String runtimeClass = selector == null
        ? "null"
        : selector.getClass().getName();
System.out.println("selector type: " + runtimeClass);
```

Đây là snippet minh họa; `obtainSelector()` tượng trưng cho phương thức của ứng dụng và không được khai báo trong tệp chạy ở mục 8. Khi debug thực tế, tránh in toàn bộ dữ liệu nhạy cảm, object lớn hoặc dữ liệu có `toString()` chứa thông tin cá nhân.

### Bước 3: so kiểu với từng case theo thứ tự

Lấy runtime class vừa thấy, xác định xem nó có phải subtype/implementation của kiểu trong case hay không. Với `Long`, case `Integer` không khớp dù cả hai đều là `Number`. Với `StringBuilder`, case `String` không khớp nhưng `CharSequence` có thể khớp.

### Bước 4: tách kiểm tra type và guard

Khi type khớp nhưng `when` false, Java tiếp tục xét case khác. Đặt breakpoint tại guard hoặc đánh giá riêng biểu thức guard đã được viết trong code. Không nhầm guard false với runtime class sai.

### Bước 5: kiểm tra các component của nested record pattern

Selector ngoài có thể là đúng record, nhưng component ở vị trí yêu cầu một record khác có thể là null/sai kiểu, làm cả pattern không khớp. Nếu component được ràng buộc bằng `var`, hãy kiểm tra riêng null và giá trị để hiểu guard.

### Bước 6: xem `case null`, `default` và throw

Nếu selector null, bạn cần xác nhận có nhánh `case null` hay chính sách tiền kiểm null phù hợp. Không giả định `default` luôn bắt null: một pattern switch thiếu xử lý null có thể ném `NullPointerException`. Với selector kiểu `Object`, `default` giúp bao phủ những kiểu không được liệt kê.

### Bước 7: thêm regression test cho kiểu runtime gây lỗi

Sau khi tìm được một input thực tế gây chọn nhánh khác dự kiến, lưu input đại diện thành test: `Long` thay vì `Integer`, `StringBuilder` thay vì `String`, record con null hoặc guard false. Test cần khẳng định **kết quả công khai** và lỗi phù hợp, không chỉ `getClass()`.

## 10. Những trường hợp đặc biệt khi debug type

### 10.1. Generics không hiện đầy đủ qua getClass()

Ví dụ `new ArrayList<String>()` và `new ArrayList<Integer>()` đều có runtime class là `java.util.ArrayList`. `getClass()` không thể cho bạn biết chính xác type argument của từng instance do **type erasure**.

Không viết:

```java
// Không biên dịch khi raw là Object: List<String> không reifiable.
if (raw instanceof java.util.List<String> strings) {
    System.out.println(strings.size());
}
```

Nếu cần kiểm tra dữ liệu runtime:

```java
if (raw instanceof java.util.List<?> values) {
    for (Object element : values) {
        if (element instanceof String text) {
            System.out.println("String element length=" + text.length());
        }
    }
}
```

Các đoạn này là snippet độc lập về ý tưởng, cần đặt trong class/method có biến `raw`. Khi debug một case `List<?>`, hãy phân biệt **kiểu container** và **kiểu phần tử**.

### 10.2. Proxy và class được framework tạo ra

Một đối tượng được truyền dưới kiểu interface hoặc base class có thể là một proxy do framework tạo. Khi đó `getClass().getName()` có thể in tên class sinh động, không phải tên interface nghiệp vụ bạn chờ đợi.

Điều này **không mặc nhiên** khiến `instanceof MyInterface` sai: nếu proxy thực sự implements interface, type pattern đối với interface vẫn có thể khớp. Hãy kiểm tra quan hệ kiểu và cấu trúc wrapper/proxy thực tế, thay vì chỉ so sánh chuỗi tên class.

Nếu cần chẩn đoán class loader hoặc vấn đề trùng tên class giữa các module, có thể xem `selector.getClass().getClassLoader()` và `selector.getClass().getModule()`, nhưng không nên tràn log hoặc tự kết luận lỗi class loader khi chưa có chứng cứ.

### 10.3. getClass() khác instanceof

Đừng thay một type pattern bằng phép so sánh class chính xác chỉ vì đang debug:

```java
Object selector = new StringBuilder("abc");

System.out.println(selector.getClass() == CharSequence.class); // false
System.out.println(selector instanceof CharSequence);          // true
```

So sánh class bằng `==` yêu cầu **đúng cùng đối tượng `Class`**, trong khi `instanceof` dùng **quan hệ gán được/implementation**. Với interface và subtype, hai phép kiểm tra có thể khác kết quả. Khi muốn giải thích case match, kết quả `instanceof` (hoặc quy tắc pattern của case) mới sát hành vi cần debug.

### 10.4. Sealed hierarchy và type tĩnh

Nếu selector có kiểu tĩnh `Signal` là sealed interface và các implementation được phép đều được bao phủ bằng case, compiler có thể chứng minh một `switch expression` là exhaustive mà không cần default. Điều đó dựa trên **hệ kiểu tĩnh và các subtype được phép**, không có nghĩa dữ liệu trong mỗi subtype đều hợp lệ.

Trong chương trình ví dụ, `route(Object selector)` nhận kiểu mở `Object` nên có `default`. Dù record `Ready/Failed` implements `Signal`, type tĩnh của selector vẫn là `Object`, và Java không thể chỉ dùng hierarchy sealed này để xem cả switch đã exhaustive.

### 10.5. ClassCastException, MatchException và lỗi nghiệp vụ

Nếu code cũ thực hiện `(SomeType) selector`, sai kiểu có thể ném `ClassCastException`. Type pattern trong `switch` thường cho phép diễn đạt nhánh không khớp thay vì cast trực tiếp, nhưng chưa chắc mọi chuyển đổi đều giữ nguyên hành vi lỗi.

Với record patterns và sealed switch, nếu không thể chọn một nhánh mà chương trình được biên dịch trước đó tin rằng phải đầy đủ, trong những kịch bản bất thường như binary không tương thích, runtime có thể ném `MatchException`. Đây không phải hành vi fallback thông thường bạn nên tự tạo trong ứng dụng.

Nếu type runtime đúng nhưng dữ liệu nghiệp vụ sai (ví dụ `Ready` chứa payload rỗng), lỗi có thể nằm ở guard/validation chứ không ở cơ chế `instanceof`. Trước khi thêm một cast hoặc một default rộng, xác định chính xác ngữ nghĩa mong muốn.

## 11. Ma trận kiểm thử để giữ lại kết quả debug

Từ các trường hợp của ví dụ runnable, có thể viết test với ma trận:

| Selector | Runtime type | Case/guard dự kiến | Kết quả nổi bật |
| --- | --- | --- | --- |
| `"  java  "` | `String` | Guard `isBlank()` false, nhánh String tiếp theo | `String:text=java` |
| `"  "` | `String` | Guard `isBlank()` true | `String:blank` |
| `7` | `Integer` | `case Integer` | `Integer:7` |
| `7L` | `Long` | `case Number` | `Number:Long=7` |
| `3.5` | `Double` | `case Number` | `Number:Double=3.5` |
| `Ready("R1", "ok")` | `Ready` | Guard payload là String true | `Ready:R1:string=ok` |
| `Ready("R2", 42)` | `Ready` | Guard false; Ready không guard | `Ready:R2:payload=Integer` |
| `Ready("R3", null)` | `Ready` | Guard false do payload null | `Ready:R3:payload=null` |
| `Failed(404)` | `Failed` | `case Failed` | `Failed:404` |
| `Box(null)` | `Box` | `case Box`, item null | `Box:item=null` |
| `StringBuilder("text")` | `StringBuilder` | Không có case tương thích trong ví dụ | `other:StringBuilder` |
| `new Object()` | `Object` | `default` | `other:Object` |
| `null` | Không có runtime class | `case null` | `selector:null` |

**Đừng chỉ kiểm tra log.** Test cần gọi hàm định tuyến thực sự rồi xác nhận kết quả có ý nghĩa. Khi điều kiện `when` được sửa, một regression test như `Ready("R2", 42)` hoặc chuỗi trắng sẽ bắt thay đổi nhánh không chủ đích.

Nếu dùng JUnit 5 (trong dự án có dependency JUnit Jupiter), có thể kiểm tra với `assertEquals`:

```java
// Snippet JUnit 5, cần class SelectorRuntimeTypeDemo và JUnit Jupiter trên test classpath.
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SelectorRuntimeTypeTest {
    @Test
    void longUsesNumberCaseNotIntegerCase() {
        assertEquals(
            "Number:Long=7",
            SelectorRuntimeTypeDemo.route(7L)
        );
    }

    @Test
    void nullRecordComponentDoesNotCrash() {
        assertEquals(
            "Ready:R3:payload=null",
            SelectorRuntimeTypeDemo.route(
                new SelectorRuntimeTypeDemo.Ready("R3", null)
            )
        );
    }

    @Test
    void wrongTypeUsesFallback() {
        assertEquals(
            "other:StringBuilder",
            SelectorRuntimeTypeDemo.route(new StringBuilder("x"))
        );
    }
}
```

Các test JUnit này là ví dụ mở rộng cần cấu hình test runner và dependency, không thuộc chương trình độc lập chỉ cần `javac/java` ở mục 8. Đặt tệp test cùng package với lớp demo vì các phương thức/record ở đây có mức truy cập package-private.

## 12. Các lỗi debug thường gặp

| Hiện tượng hoặc ngộ nhận | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| “Selector là Object nên chẳng case nào biết kiểu” | Nhầm kiểu tĩnh với kiểu runtime. | Log class runtime của đúng selector; type pattern vẫn có thể match. |
| `case Integer` không chạy với số `7L` | `7L` được box thành `Long`, không phải `Integer`. | In `getName()` và test `case Long`/`Number` theo hợp đồng. |
| `case String` không chạy với StringBuilder | StringBuilder không kế thừa String. | Kiểm tra `instanceof CharSequence` nếu muốn hỗ trợ kiểu đó. |
| Log class là Envelope nhưng case switch dựa trên payload | Đang log đối tượng ngoài thay vì selector bên trong. | Gán kết quả accessor vào biến, log đúng biến đó. |
| Selector là String nhưng nhánh có `when` không chạy | Guard false. | Kiểm tra giá trị/guard; thêm test tại biên. |
| Selector là Ready nhưng nhánh guard payload String không chạy | Component payload có kiểu khác hoặc null. | Log type của payload riêng và kiểm tra `instanceof String`. |
| Nested record pattern không khớp mặc dù record ngoài đúng kiểu | Record con có thể null hoặc sai kiểu. | Kiểm tra từng component trong cây record. |
| Log `selector.getClass()` gây NPE | Selector null; log chạy trước kiểm tra. | Dùng helper null-safe, xử lý case null. |
| `case Number` trước `case Integer` làm lỗi biên dịch | Case hẹp bị che khuất (dominated). | Đặt case Integer trước Number. |
| `getClass() == Interface.class` false dù pattern interface match | Exact-class equality khác instanceof. | Dùng quan hệ kiểu và runtime class đúng. |
| Hai List có generic khác nhau nhưng getClass giống nhau | Type erasure. | Kiểm tra các phần tử hoặc metadata/schema phù hợp. |
| Runtime type in khác giữa môi trường | Proxy/class loader/class name khác ở runtime. | Xem tên đầy đủ, interface, loader/module khi cần. |
| Thêm log làm thay đổi nhánh chạy | Selector hoặc accessor được gọi lại, có side effect. | Lấy selector một lần, quan sát cùng giá trị. |
| Ghi raw selector gây rò thông tin | Log có dữ liệu nhạy cảm hoặc toString tùy biến. | Chỉ log type, trạng thái guard và dữ liệu đã ẩn/giảm chi tiết. |

## 13. Bài tập tự kiểm tra

### Bài A — Dự đoán case từ runtime class

Cho đoạn Java 21:

```java
static String choose(Object selector) {
    return switch (selector) {
        case null -> "missing";
        case Integer n -> "int:" + n;
        case Number n -> "number:" + n.getClass().getSimpleName();
        case CharSequence s -> "chars:" + s.length();
        default -> "other";
    };
}
```

Dự đoán kết quả:

1. `choose(2)` → `int:2` (boxing thành Integer).
2. `choose(2L)` → `number:Long`.
3. `choose(2.5)` → `number:Double`.
4. `choose("abc")` → `chars:3`.
5. `choose(new StringBuilder("hi"))` → `chars:2`.
6. `choose(null)` → `missing`.
7. `choose(new Object())` → `other`.

Giải thích: `Number` bao phủ các wrapper số ở đây nhưng không bao phủ `String`; `CharSequence` chấp nhận cả String và StringBuilder. Nếu đổi `case Number` lên trước `case Integer`, compiler có thể từ chối vì domination.

### Bài B — Debug sai selector

Một service làm:

```java
record Request(Object body) {}

// Snippet trong phương thức nhận Request request:
switch (request.body()) {
    case String text -> System.out.println("text");
    default -> System.out.println("other");
}
```

Developer ghi `request.getClass().getName()` và nhận `Request`, sau đó kết luận nhánh String không bao giờ chạy. Kết luận sai ở đâu?

**Đáp án:** Selector là **`request.body()`**, không phải request. Phải quan sát type runtime của body. Nếu body là String thì case String vẫn có thể khớp; nếu body null thì với switch này, cần bổ sung xử lý null theo hợp đồng, chẳng hạn `case null`. Khi debug, lấy `Object selector = request.body();` trước để log và switch cùng một giá trị.

### Bài C — Runtime class giống nhau nhưng khác nhánh

Với `classifyText` ở mục 6, hãy giải thích tại sao selector `" "` và `"Java"` có chung `java.lang.String` nhưng nhận kết quả khác nhau.

**Đáp án:** Pattern `String` khớp cả hai. Sau đó guard `text.isBlank()` đúng với chuỗi trắng và sai với `"Java"`. Khi guard sai, nhánh String không guard xử lý. Do đó **runtime type chỉ là một phần lời giải**, không thay thế việc kiểm tra dữ liệu và guard.

## 14. Checklist khi điều tra lỗi pattern matching

1. **Đúng selector?** Phân biệt `switch (value)` với `switch (value.component())`.
2. **Giá trị đã được đánh giá một lần?** Không log bằng cách gọi lại getter có thể đổi state.
3. **Selector null?** Dùng log null-safe, kiểm tra `case null` hoặc hợp đồng NPE.
4. **Kiểu runtime cụ thể là gì?** Dùng `getName()` để có tên đầy đủ; tránh chỉ nhìn kiểu tĩnh.
5. **Có boxing/subtype/interface/proxy?** So quan hệ kiểu, không so tên class bằng chuỗi.
6. **Pattern rộng hay hẹp đứng trước?** Kiểm tra domination và thứ tự nhánh.
7. **Guard `when` có false?** Ghi nhận điều kiện thực và test ở cả hai phía ngưỡng.
8. **Record pattern có tầng con null/sai kiểu?** Kiểm tra runtime type của component ở đúng vị trí.
9. **Có type erasure hoặc array?** `getClass()` chỉ cho class runtime, không đảm bảo generic arguments.
10. **Có test tái hiện?** Lưu input gây lỗi và expected result để tránh tái phát.
11. **Log an toàn?** Không in raw token, payload nhạy cảm, thông tin cá nhân hay `toString()` chưa được kiểm soát.

**Ghi nhớ:** Khi một nhánh pattern switch không chạy như mong đợi, hãy bắt đầu từ **giá trị selector thực sự** và **runtime type**, rồi lần lượt xem **quan hệ kiểu, guard, nested record components, thứ tự case và xử lý null**. Type runtime là dữ kiện chẩn đoán quan trọng, nhưng không phải quyết định cuối cùng của toàn bộ pattern matching.

**Tài liệu tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Java SE 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Java SE 21 JLS — switch expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [Class API (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).
