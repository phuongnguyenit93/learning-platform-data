# Cú pháp `instanceof` với kiểu và biến mẫu trong Java hiện đại

## 1. Mục tiêu, phiên bản và ý nghĩa của type pattern

**Pattern matching for `instanceof`** cho phép kiểm tra một đối tượng có khớp với một kiểu hay không và, nếu khớp, **khai báo ngay biến có kiểu đó**. Cú pháp tiêu biểu:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Đây là **đoạn mã minh họa** đặt trong một phương thức có biến `value` mang kiểu tham chiếu phù hợp (ví dụ `Object value`). `String` là **kiểu mẫu (pattern type)** và `text` là **biến mẫu (pattern variable)**. Khi `value` là một `String` khác `null`, điều kiện trả `true`, đồng thời Java gán tham chiếu đã được kiểm tra kiểu cho `text`. Trong nhánh đó, có thể gọi `text.length()` mà không cần ép kiểu bằng `(String) value`.

**Mốc phiên bản:** tính năng xuất hiện ở **Java 14 dưới dạng preview** (JEP 305), được preview tiếp trong Java 15 (JEP 375), rồi **trở thành chính thức từ Java 16** (JEP 394). Đây vẫn là một kỹ thuật Java hiện đại. Mọi ví dụ chạy được ở bài này sử dụng **Java 17+ với cú pháp chuẩn**, biên dịch bằng `javac --release 17`; không cần `--enable-preview`. Các pattern mở rộng được bổ sung sau này, như record deconstruction patterns hoặc tính năng thử nghiệm cho primitive, là các chủ đề riêng và không cần để hiểu cú pháp `instanceof Type variable`.

Sau bài học, bạn sẽ biết:

1. Đọc và viết chính xác biểu thức `expression instanceof Type variable`.
2. Phân biệt biểu thức `instanceof` thông thường và dạng khai báo biến mẫu.
3. Hiểu phép kiểm tra runtime, giá trị `null`, sự hình thành biến mẫu và kiểu tĩnh của biến.
4. Xác định phạm vi của biến mẫu theo **flow scoping**, đặc biệt trong `if`, `else if`, `&&`, `||` và guard clause.
5. Dùng type patterns với class, interface, record và generic reifiable types.
6. Chẩn đoán các lỗi biên dịch thường gặp và chọn tên biến phù hợp trong mã thực tế.

## 2. Cấu trúc cú pháp và cách chạy

Hình thức ổn định, thông dụng trên Java 17+:

```java
expression instanceof ReferenceType patternVariable
```

Ví dụ:

```java
value instanceof String text
value instanceof Number number
value instanceof CharSequence chars
value instanceof java.util.List<?> items
```

Các dòng trên là **biểu thức minh họa**, không phải các statement đầy đủ để đặt độc lập tại cấp tệp Java. Chúng có ý nghĩa:

- **`expression`**: biểu thức cần kiểm tra, thường có kiểu `Object`, interface, supertype hoặc kiểu tham chiếu có thể chuyển hợp lệ sang kiểu mẫu.
- **`instanceof`**: toán tử kiểm tra mẫu. Kết quả của toàn biểu thức là `boolean`.
- **`ReferenceType`**: một kiểu tham chiếu phù hợp, chẳng hạn `String`, interface `CharSequence`, record `Product`, hoặc `List<?>`. Với target Java 17, không dùng kiểu nguyên thủy như `int` ở type pattern.
- **`patternVariable`**: tên biến mới được khai báo ngay trong pattern, có **kiểu tĩnh chính là kiểu của pattern**. Compiler chỉ cho phép sử dụng ở những vị trí đã chứng minh phép match thành công.

**Diễn tiến runtime** với `Object value = "Java";`:

1. Đánh giá `value` một lần để lấy tham chiếu.
2. Kiểm tra tham chiếu khác `null` và giá trị thực tương thích với kiểu mẫu `String`.
3. Nếu không tương thích, biểu thức `instanceof` cho `false`, không có biến mẫu được sử dụng ở đường đi đó.
4. Nếu tương thích, biểu thức cho `true`, biến `text` được khởi tạo bằng chính tham chiếu đã kiểm tra, mang kiểu tĩnh `String`.
5. Trong vùng phạm vi hợp lệ, dùng các phương thức của `String` mà không cần tự cast.

Biến mẫu **không phải bản sao mới của đối tượng**, cũng không biến đối tượng thành immutable. Nó là một biến có kiểu tĩnh cụ thể để tham chiếu tới giá trị đã khớp. Phép `instanceof` thường chỉ trả về boolean; nó không tự gọi phương thức xử lý hay biến đổi đối tượng.

### 2.1. So sánh với dạng không có biến mẫu

Dạng chỉ kiểm tra kiểu vẫn hợp lệ trong Java hiện đại:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Dạng có type pattern gộp hai thao tác:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Cả hai có thể hoạt động đúng, nhưng dạng có biến mẫu loại bỏ ép kiểu thủ công lặp lại, giảm nguy cơ đọc nhầm biến hoặc cast nhầm lớp. Đây là cải tiến về cú pháp và sự an toàn kiểu; **không phải** lệnh gọi một API runtime mới cần import.

### 2.2. `null`, object runtime và kiểu tĩnh

- `null instanceof String text` cho `false`; biến `text` không được sử dụng ở nhánh false. `instanceof` không ném `NullPointerException` chỉ vì operand là `null`.
- `Object value = 42; if (value instanceof Integer number)` có thể match vì object runtime là `Integer`.
- `Object value = "hi"; if (value instanceof CharSequence chars)` có thể match vì `String` thực thi `CharSequence`.
- `Object value = "hi"; if (value instanceof Integer number)` trả `false`; không tự convert chuỗi `"hi"` thành số.
- Pattern variable giữ **kiểu tĩnh của pattern**: `CharSequence chars` cho các phương thức của `CharSequence`. Nó không tự biến thành kiểu `String` chỉ vì object runtime là String.
- Với Java 17, target là **reference type**. Ví dụ `value instanceof int n` không thuộc cú pháp type pattern ổn định của Java 17; khi cần kiểm tra wrapper, dùng `Integer number`. Một số phiên bản JDK mới có preview cho primitive patterns; đừng trộn chúng vào ví dụ Java 17 chuẩn.

## 3. Chương trình hoàn chỉnh: type pattern, `null`, guard và phạm vi biến

**Tệp `InstanceofPatternDemo.java` — Java 17+:**

```java
import java.util.List;
import java.util.Locale;

public class InstanceofPatternDemo {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            text = text.strip();
            return "text=" + text + "; length=" + text.length();
        } else if (value instanceof Number number) {
            return "number=" + number.intValue();
        } else if (value == null) {
            return "null";
        }
        return "other";
    }

    static String guarded(Object value) {
        if (!(value instanceof String text)) {
            return "not text";
        }
        return "guard=" + text.toUpperCase(Locale.ROOT);
    }

    static String label(Object value) {
        if (value instanceof String item) {
            return "S:" + item;
        } else if (value instanceof Integer item) {
            return "I:" + item;
        }
        return "unknown";
    }

    static int length(Object value) {
        return value instanceof String s ? s.length() : 0;
    }

    public static void main(String[] args) {
        Object[] inputs = {
            "  Java  ", Integer.valueOf(42), null, List.of("x"), ""
        };

        for (Object input : inputs) {
            System.out.println(describe(input));
        }

        System.out.println(guarded("hello"));
        System.out.println(guarded(10));
        System.out.println(label("Hi"));
        System.out.println(label(21));
        System.out.println(length("abcd"));
        System.out.println(length(null));
    }
}
```

Chạy tại thư mục có tệp:

```bash
javac --release 17 -encoding UTF-8 InstanceofPatternDemo.java
java InstanceofPatternDemo
```

**Stdout chính xác:**

```text
text=Java; length=4
number=42
null
other
other
guard=HELLO
not text
S:Hi
I:21
4
0
```

**Giải thích theo đường chạy:**

- `"  Java  "` match `String text`, qua điều kiện `!text.isBlank()`, được `strip()` thành `"Java"` và có độ dài 4.
- `Integer.valueOf(42)` không match `String`, nhưng match `Number number`. Gọi `number.intValue()` trả 42 mà không cần cast `Integer`.
- `null` không match bất cứ pattern reference type nào trong ví dụ này; nhánh `value == null` trả chuỗi `"null"`.
- `List.of("x")` không match `String` hay `Number`, vì vậy được phân loại là `"other"`. Chuỗi rỗng `""` có match `String` nhưng không qua kiểm tra `!text.isBlank()`; nó cũng rơi vào `"other"`.
- `guarded("hello")` dùng **guard clause phủ định**. Khi không đi vào nhánh `return "not text"`, compiler biết `text` đã được match nên cho phép dùng ở phía sau.
- `label(...)` dùng cùng tên `item` trong hai nhánh `if`/`else if` **không giao phạm vi**; trình biên dịch phân biệt biến mẫu ở mỗi nhánh.
- Toán tử điều kiện `?:` trong `length(...)` chỉ dùng biến `s` tại nhánh kết quả khi điều kiện match đúng; `null` trả 0.

**Vì sao `text = text.strip();` biên dịch được?** Kể từ khi cú pháp trở thành chính thức ở Java 16, pattern variable **không mặc nhiên `final`**. Có thể gán lại biến mẫu trong phạm vi hợp lệ như biến local khác. Tuy nhiên, trong mã cần dễ đọc, thường nên dùng tên mới (`String normalized = text.strip();`) khi không muốn che mất ý nghĩa của tham chiếu ban đầu. Nếu muốn biến mẫu là final, có thể viết `instanceof final String text`.

## 4. Flow scoping: tên biến mẫu chỉ có hiệu lực khi match được bảo đảm

Một pattern variable có **flow-sensitive scope**: Java không chỉ nhìn cặp dấu ngoặc `{ ... }` để quyết định khả năng sử dụng; compiler phân tích đường điều khiển (*control flow*) và các toán tử logic. Biến chỉ nằm trong phạm vi mà **mọi đường đi có thể tới đó đều chứng minh match thành công**. Đây là cơ chế quan trọng để bảo đảm nó đã có giá trị và đúng kiểu.

### 4.1. Trong nhánh `if`

```java
if (obj instanceof String text) {
    System.out.println(text.length()); // HỢP LỆ.
} else {
    // text không có phạm vi ở đây.
}
// Ở đây cũng không thể dùng text: if có thể đã không match.
```

Đoạn mã là **snippet trong phương thức có `Object obj`**. Kiểm tra `instanceof` phải thành công thì thân `if` mới chạy, nên `text` chắc chắn tồn tại ở nhánh true. Nhánh `else` và đoạn sau `if` không có bảo đảm đó.

### 4.2. Trong `&&`: truy cập biến mẫu ở vế phải là an toàn

```java
if (obj instanceof String text && text.length() >= 3) {
    System.out.println(text.toUpperCase());
}
```

Toán tử `&&` **short-circuit**: Java chỉ đánh giá vế phải nếu vế trái là `true`. Vì thế, khi xét `text.length()`, biến mẫu đã chắc chắn được khởi tạo. Compiler cho phép truy cập. Đặt thêm nhiều điều kiện sau `&&` vẫn hợp lệ nếu luồng logic bảo đảm thành công.

Một lỗi khác với flow scoping là vấn đề **giá trị domain**: `text.length() >= 3` kiểm tra chiều dài theo đơn vị UTF-16 của String. Nếu nghiệp vụ yêu cầu số code point Unicode, cần kiểm tra bằng API code point phù hợp; pattern matching không thay đổi ngữ nghĩa của `String.length()`.

### 4.3. Trong `||`: không dùng trực tiếp biến ở vế phải

```java
// SAI — KHÔNG BIÊN DỊCH.
if (obj instanceof String text || text.length() >= 3) {
    System.out.println("...");
}
```

Vế phải của `||` chạy khi vế trái **false**. Lúc đó không hề có bảo đảm `obj` là String, nên `text` không khả dụng. Với mục tiêu “đúng là String và đủ dài”, sửa thành `&&`:

```java
if (obj instanceof String text && text.length() >= 3) {
    System.out.println(text);
}
```

Nếu cần một điều kiện “**không phải String hoặc String rỗng**”, có thể viết:

```java
if (!(obj instanceof String text) || text.isBlank()) {
    System.out.println("not a nonblank String");
}
```

Ở ví dụ sau, vế phải chỉ chạy khi vế trái phủ định là false, tức **pattern match đã thành công**. Đây là minh họa phạm vi theo luồng điều khiển, không phải quy tắc “cứ có `||` là sai”. Hãy phân tích điều kiện nào bảo đảm biến được match.

### 4.4. Phủ định `!` và guard clause

```java
static int safeLength(Object obj) {
    if (!(obj instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Đây là **phương thức minh họa độc lập về cú pháp**, đặt trong lớp. Khi đến `return text.length();`, nhánh `if` đã không xảy ra (hoặc đã kết thúc bằng `return -1`). Vì vậy compiler có thể chứng minh `obj instanceof String text` đúng và cho phép dùng `text` sau `if`.

Nếu thân phủ định **không chắc chắn kết thúc** (chỉ log rồi đi tiếp), compiler không thể đưa `text` ra phạm vi phía sau. Cùng ý tưởng áp dụng khi phủ định đi với đường thoát hợp lệ như `throw` hoặc các cấu trúc điều khiển được JLS quy định.

### 4.5. Trong toán tử điều kiện `?:`

```java
int count = obj instanceof String s ? s.length() : 0;
```

Nhánh sau dấu `?` chỉ chạy nếu điều kiện true, nên `s` khả dụng ở nhánh đó. Đổi chỗ `s.length()` vào phần sau dấu `:` sẽ không hợp lệ vì đó là nhánh khi match false.

**Ghi nhớ:** biến mẫu nằm trong phạm vi **nơi được chứng minh match**, không ở “mọi dòng sau câu lệnh có `instanceof`”. Khi refactor `if` và logic Boolean, phải xem lại đường dẫn bảo đảm match.

## 5. Pattern matching với class, interface và record

`instanceof Type variable` kiểm tra **quan hệ kiểu runtime**, không chỉ tên lớp chính xác. Kiểu mẫu có thể là lớp, interface hoặc record (vì record là class).

**Tệp `ShapePatternDemo.java` — Java 17+:**

```java
interface Shape {}

record Rectangle(double width, double height) implements Shape {}
record Circle(double radius) implements Shape {}

public class ShapePatternDemo {
    static String describe(Shape shape) {
        if (shape instanceof Rectangle rectangle) {
            return "rectangle area=" +
                   rectangle.width() * rectangle.height();
        }
        if (shape instanceof Circle circle) {
            return "circle radius=" + circle.radius();
        }
        return "unknown";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Rectangle(3, 4)));
        System.out.println(describe(new Circle(2)));
        System.out.println(describe(null));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ShapePatternDemo.java
java ShapePatternDemo
```

**Stdout chính xác:**

```text
rectangle area=12.0
circle radius=2.0
unknown
```

`rectangle` có kiểu tĩnh `Rectangle`, nên dùng được accessor `width()` và `height()` mà không cần cast. Tương tự, `circle` có kiểu `Circle`. Cả hai record implement `Shape`, cho phép phương thức nhận đầu vào chung `Shape` rồi xử lý theo kiểu runtime.

**Phân biệt với record pattern:** `shape instanceof Rectangle rectangle` chỉ **test kiểu và bind toàn bộ đối tượng**. Nó **không** tách trực tiếp từng component bằng cú pháp `Rectangle(var w, var h)`. Record deconstruction patterns thuộc khả năng pattern matching được chuẩn hóa ở các phiên bản sau (Java 21) và là phạm vi khác. Bài này chỉ cần type pattern đã ổn định từ Java 16.

### 5.1. Kiểu interface làm pattern

```java
if (obj instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

Với `obj` là `String` hoặc `StringBuilder`, biểu thức có thể match vì cả hai implement `CharSequence`. Biến `chars` có kiểu tĩnh **`CharSequence`**. Do đó chỉ những thao tác của `CharSequence` (hoặc object methods chung) được phép trực tiếp; không thể gọi `chars.strip()` vì `strip()` không thuộc interface này.

Pattern kiểu interface giúp tránh sự phụ thuộc không cần thiết vào một implementation cụ thể. Chỉ chọn kiểu `String` nếu thực sự cần API của String.

## 6. Generic types: phân biệt `List<?>` và `List<String>`

Java generics sử dụng **type erasure** ở runtime. Do đó, một phép `instanceof` không được phép giả định rằng chỉ cần thấy object là `List` thì có thể chứng minh mọi phần tử trong đó đều là `String`.

**Tệp `ListPatternDemo.java` — Java 17+:**

```java
import java.util.List;

public class ListPatternDemo {
    public static void main(String[] args) {
        Object input = List.of("alpha", "beta");

        if (input instanceof List<?> items) {
            System.out.println("size=" + items.size());

            Object first = items.get(0);
            if (first instanceof String text) {
                System.out.println("first=" + text);
            }
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ListPatternDemo.java
java ListPatternDemo
```

**Stdout chính xác:**

```text
size=2
first=alpha
```

Ở đây `List<?>` là một **reifiable** dạng parameterized type dùng wildcard không giới hạn, nên có thể kiểm tra object runtime có phải List hay không. Kiểu `items` là `List<?>`; từng phần tử đọc ra là `Object`, nên tiếp tục kiểm tra bằng `instanceof String text` khi cần xử lý String.

**Ví dụ cố ý sai:**

```java
// KHÔNG BIÊN DỊCH với Object input trên Java 17.
if (input instanceof List<String> strings) {
    System.out.println(strings.size());
}
```

Do erasure, thông tin tham số `String` không được kiểm tra an toàn như phép cast cần thiết ở đây; compiler từ chối. Không nên thay bằng unchecked cast để làm cho mã có vẻ đã được xác minh. Nếu cần một `List<String>`, phải kiểm tra từng phần tử hoặc thiết kế API nhận kiểu tham số hóa ngay từ đầu.

Một số pattern khác có thể dùng với parameterized type khi chuyển kiểu là **an toàn và kiểm tra được** theo quy tắc JLS tương ứng; điều cần hiểu là **không phải mọi tổ hợp generic đều hợp lệ trong `instanceof`**.

## 7. Kiểu mẫu, biến mẫu và những quy tắc đặt tên

### 7.1. Tên biến mẫu có thể tái sử dụng ở phạm vi không giao nhau

Trong `InstanceofPatternDemo.label(...)`:

```java
if (value instanceof String item) {
    return "S:" + item;
} else if (value instanceof Integer item) {
    return "I:" + item;
}
```

Hai biến `item` chỉ nằm trong những nhánh tương ứng. Java cho phép dùng cùng tên ở đây vì phạm vi của chúng không chồng lấp. Tuy nhiên, nếu hai nhánh dài hoặc có kiểu dữ liệu dễ gây nhầm, tên rõ nghĩa như `text` và `number` sẽ dễ review hơn.

### 7.2. Không dùng tên đã có trong phạm vi

```java
// KHÔNG BIÊN DỊCH.
String text = "outer";
if (obj instanceof String text) {
    System.out.println(text);
}
```

Biến mẫu thứ hai đụng tên local variable `text` đã ở trong phạm vi, compiler báo biến được định nghĩa trùng. Điều này không liên quan tới object runtime; lỗi xảy ra khi biên dịch.

**Sửa:** đổi tên biến mẫu (ví dụ `matchedText`) hoặc tổ chức phạm vi sao cho không có hai khai báo xung đột. Không nên dùng tên mơ hồ như `s` nếu có nhiều pattern gần nhau.

### 7.3. Pattern variable không mặc nhiên `final`

```java
if (obj instanceof String text) {
    text = text.strip(); // Java 16+ hợp lệ.
    System.out.println(text);
}
```

Trái lại, có thể khai báo tường minh:

```java
if (obj instanceof final String text) {
    // text = text.strip(); // Lỗi: đã final.
    System.out.println(text.strip());
}
```

Hai ví dụ chỉ là **snippet trong phương thức có `obj`**. Việc cho phép gán lại biến mẫu là hành vi **chính thức hiện tại** (JEP 394), khác với một số tài liệu preview ban đầu. Quyết định có dùng `final` tùy convention mã nguồn và nhu cầu bảo toàn tên biến; đừng hiểu `final` là biến tham chiếu tới một object đã bất biến sâu.

### 7.4. Type pattern cần một kiểu tương thích để kiểm tra

Compiler phải chứng minh rằng việc kiểm tra/cast từ kiểu tĩnh của operand sang kiểu mẫu là hợp lệ. Ví dụ kiểm tra một `String` sang một class không có quan hệ kiểu phù hợp sẽ gây lỗi biên dịch. Đừng nghĩ `instanceof` có thể thử chuyển đổi tùy ý giữa mọi kiểu Java, như tự parse String thành Number.

**Lưu ý tương thích phiên bản:** một số quy tắc liên quan *unconditional patterns* (pattern mà kiểu tĩnh của operand đã tương thích hoàn toàn với kiểu đích) đã thay đổi sau Java 17; ví dụ `String s = ...; s instanceof String t` không biên dịch với `--release 17` nhưng hợp lệ ở một số JDK mới hơn như JDK 24. Để các ví dụ trong bài tương thích ổn định với Java 17+, chúng dùng `Object`, `Shape` hoặc kiểu cha/interface khi thử type pattern. Đừng học lỗi compiler ở một release cũ như quy tắc không đổi của mọi Java hiện đại.

## 8. Khi nào nên áp dụng type pattern trong code thực tế?

### 8.1. Xử lý đầu vào có kiểu tổng quát

Khi một API thực sự nhận `Object` hoặc giá trị từ nguồn đa hình, type pattern gọn để phân loại an toàn:

```java
static String summarize(Object input) {
    if (input instanceof String text) {
        return text.strip();
    }
    if (input instanceof Number number) {
        return "number=" + number;
    }
    return "unsupported";
}
```

Đoạn trên là **phương thức minh họa cần đặt trong lớp**. Với dữ liệu nullable, việc không match được xử lý ở nhánh cuối. Nếu cần phân biệt `null` với kiểu không hỗ trợ, kiểm tra `input == null` rõ ràng trước hoặc sau các pattern.

### 8.2. Xử lý theo interface hoặc mô hình đa hình

Nếu có hệ lớp ổn định, thường nên ưu tiên các phương thức đa hình hoặc API chung hơn là chuỗi `if (obj instanceof A a) ... else if (...)` ngày càng dài. Dùng type pattern khi phải thực sự phân nhánh theo cấu trúc runtime, ở ranh giới tích hợp hoặc khi luồng phân loại ngắn và rõ.

### 8.3. Điều kiện kết hợp với validation

```java
if (input instanceof String email && email.contains("@")) {
    process(email);
}
```

Đây là snippet minh họa trong phạm vi có phương thức `process(String)`. `instanceof` chỉ chứng minh input là String; `contains("@")` là một kiểm tra sơ bộ, **không đủ để xác thực email**. Phân biệt kiểm tra kiểu khỏi validation nghiệp vụ tránh việc gán cho pattern matching nhiều trách nhiệm mà nó không có.

### 8.4. Guard clause cho phương thức ngắn

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Kiểu này loại đầu vào sai sớm và giữ nhánh chính ít lồng nhau. Phạm vi của `text` sau `if` là kết quả của compiler phân tích đường điều khiển; không cần cast thứ hai.

## 9. Bảng lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `cannot find symbol: text` ở nhánh `else` | Pattern chưa chắc match trong nhánh đó | Dùng biến chỉ ở luồng match true |
| `cannot find symbol` sau một `if` thông thường | Luồng sau `if` có thể đến từ cả true và false | Giữ logic trong nhánh true hoặc dùng guard `return/throw` |
| Biến mẫu ở vế phải của `||` bị lỗi | Vế phải chạy khi phép match phía trước false | Dùng `&&`, hoặc bố trí phủ định để bảo đảm match |
| `Object cannot be safely cast to List<String>` | Generic parameter không được kiểm tra an toàn sau erasure | Dùng `List<?>`, rồi kiểm tra từng phần tử |
| `variable ... is already defined` | Pattern variable bị trùng tên local variable trong scope | Đổi tên hoặc tách scope hợp lệ |
| `incompatible types` với kiểu mẫu | Compiler biết kiểu nguồn không thể kiểm tra/chuyển hợp lệ sang kiểu đích | Chọn pattern phù hợp với quan hệ kiểu thực |
| Thấy `false` dù object runtime không rỗng | Kiểu runtime không đúng pattern | Kiểm tra kiểu đúng hoặc dùng interface chung |
| Nhầm `null` với object không đúng kiểu | `null` không match type pattern thông thường | Xử lý `null` riêng nếu nghiệp vụ cần |
| Vẫn viết ép kiểu sau pattern | Trùng thao tác, khó đọc | Dùng trực tiếp biến mẫu có kiểu đã được compiler xác nhận |
| Dùng Java 14 preview flags trong dự án JDK 17+ | Nhầm mốc tính năng preview với mốc chuẩn hóa | Dùng cú pháp chuẩn Java 16+, bỏ cờ preview |

Đối với các snippet được đánh dấu **KHÔNG BIÊN DỊCH** ở trên, mục đích là quan sát chẩn đoán compiler; không đưa chúng cùng lúc vào các chương trình chính đã có stdout cố định.

## 10. Thực hành với câu hỏi và đáp án định hướng

1. **Cơ bản:** viết một phương thức nhận `Object`; khi là `String`, trả về độ dài; nếu không, trả `-1`. Dùng `instanceof String text`, không ép kiểu thủ công.
2. **Null:** với `Object value = null`, giải thích giá trị của `value instanceof String s` và vì sao không có `NullPointerException`.
3. **Điều kiện kết hợp:** viết `if (obj instanceof String s && s.length() > 5)`. Giải thích vì sao `s` hợp lệ ở cả vế phải và nhánh true.
4. **Sửa lỗi:** tìm lỗi của `obj instanceof String s || s.length() > 5`. Đề xuất ít nhất một biểu thức hợp lệ đáp ứng mục tiêu “là String và dài”.
5. **Guard clause:** dùng `if (!(obj instanceof String s)) return;` rồi sử dụng `s` trong lệnh phía sau. Giải thích sự bảo đảm từ đường điều khiển.
6. **Nhánh độc lập:** viết `if (obj instanceof String x) ... else if (obj instanceof Integer x) ...`, phân tích tại sao có thể dùng cùng tên khi scopes không trùng nhau.
7. **Generics:** viết kiểm tra `obj instanceof List<?> items`, đọc phần tử và dùng pattern `String text` để kiểm tra phần tử trước khi gọi API String.
8. **Record:** khai báo `record Person(String name)` và phương thức nhận `Object`; dùng `obj instanceof Person person` rồi gọi `person.name()`.
9. **Không gán nhầm tên:** đặt sẵn biến local `String s` rồi cố khai báo `instanceof String s`; dùng lỗi compiler để tìm xung đột scope và sửa.
10. **Phiên bản:** giải thích vì sao dự án biên dịch `--release 17` không cần `--enable-preview`, mặc dù tính năng từng được giới thiệu ở Java 14.

**Gợi ý đáp án:** (1) nhánh true trả `text.length()`; (2) pattern reference type không match `null`; (3) `&&` short-circuit, vế phải chỉ chạy khi match; (4) thay `||` thành `&&`; (5) nhánh phủ định thoát sớm thì dòng sau chỉ có thể đến từ match thành công; (6) phạm vi theo luồng tách biệt; (7) kiểm tra từng phần tử vì erasure; (8) record là class nên có thể dùng type pattern; (9) pattern variable không được shadow local cùng phạm vi; (10) chuẩn hóa ở Java 16.

## 11. Nguồn chính thức và ghi nhớ

- **OpenJDK JEP 305 — Pattern Matching for `instanceof` (Preview):** lần preview ở Java 14: https://openjdk.org/jeps/305
- **OpenJDK JEP 394 — Pattern Matching for `instanceof`:** cú pháp và ngữ nghĩa chính thức từ Java 16, bao gồm thay đổi về pattern variables: https://openjdk.org/jeps/394
- **Oracle Java 17, Pattern Matching for `instanceof`:** giải thích ví dụ, `&&`, `||`, guard và flow scoping: https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html
- **Oracle Java 16, Language Changes:** xác nhận mốc chính thức Java 16 sau preview Java 14: https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html
- **Java Language Specification SE 25, `15.20.2:** cú pháp và phép kiểm tra `instanceof`: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2
- **JLS SE 25, `6.3.1 và `6.3.2:** phạm vi biến mẫu phụ thuộc điều kiện và đường điều khiển: https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3.1
- **JLS SE 25, `14.30:** định nghĩa type patterns và pattern variables: https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.30

**Ghi nhớ:** `value instanceof Type variable` vừa kiểm tra kiểu runtime, vừa **bind một biến đã có kiểu tĩnh `Type`** khi match thành công. Biến mẫu chỉ dùng được ở nơi compiler chứng minh phép match đã đúng. Với Java 17+, hãy dùng type patterns chính thức để bớt ép kiểu lặp lại, nhưng vẫn kiểm tra giá trị `null`, generic type safety và điều kiện nghiệp vụ một cách riêng biệt.