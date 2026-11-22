# Biến mẫu có thể gán lại: quy tắc chính thức của Java hiện đại

## 1. Kết luận quan trọng và mốc phiên bản

Trong cú pháp **pattern matching for `instanceof`**, Java cho phép vừa kiểm tra kiểu, vừa khai báo một **biến mẫu** (*pattern variable*):

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Ví dụ này là **đoạn mã trong một phương thức** có biến `input` với kiểu phù hợp, ví dụ `Object input`. Khi phép kiểm tra thành công, `text` có **kiểu tĩnh `String`** và tham chiếu tới object được kiểm tra.

Điểm cần nhớ trong Java hiện đại: **biến mẫu mặc định không phải là `final`, nên có thể gán lại một giá trị tương thích kiểu ở những nơi biến đó đang nằm trong phạm vi**. Ví dụ sau là hợp lệ:

```java
if (input instanceof String text) {
    text = text.strip();             // Hợp lệ trên Java 16+.
    System.out.println(text);
}
```

**Lịch sử cần phân biệt:** type pattern của `instanceof` được giới thiệu **preview ở Java 14** (JEP 305), trải qua preview Java 15, và trở thành **tính năng ngôn ngữ chính thức từ Java 16** (JEP 394). **JEP 394 bỏ hạn chế biến mẫu mặc nhiên `final`** của những phiên bản preview. Hạn chế cũ **không còn là quy tắc phải áp dụng** khi viết Java 17, 21, 25 hoặc các JDK mới hơn hỗ trợ đặc tả tương ứng.

Bài này chỉ dùng **cú pháp ổn định Java 17+**, biên dịch với `javac --release 17`. Không cần `--enable-preview`; không sử dụng cách viết hoặc API preview đã lỗi thời.

Sau bài học, bạn sẽ phân biệt được:

- **Gán lại biến mẫu** với **thay đổi object được tham chiếu**.
- Tính **không mặc nhiên `final`** với việc có thể khai báo `final` tường minh.
- **Phạm vi theo luồng điều khiển (*flow scoping*)** với quyền được gán giá trị khi biến nằm trong phạm vi.
- **Tham chiếu có kiểu tĩnh** với object runtime: gán lại vẫn bị kiểm tra kiểu Java.
- **Effectively final** khi dùng pattern variable trong lambda/lớp cục bộ.
- Các ví dụ gán lại hợp lệ và các lỗi biên dịch thường gặp.

## 2. Biến mẫu là gì và nó được khởi tạo khi nào?

Mẫu cơ bản:

```java
expression instanceof ReferenceType variableName
```

Với `Object value = "Java";`, biểu thức `value instanceof String text` làm ba việc: kiểm tra object runtime có phù hợp `String` không; trả một giá trị `boolean`; và khi **match thành công**, khởi tạo biến mẫu `text` bằng tham chiếu tới object đã match.

**Giải thích từng thành phần:**

| Thành phần | Vai trò |
| --- | --- |
| `value` | Biểu thức đầu vào cần kiểm tra kiểu |
| `instanceof` | Toán tử kiểm tra runtime và pattern match |
| `String` | Kiểu tham chiếu được kiểm tra (*pattern type*) |
| `text` | Biến mẫu mới, có kiểu tĩnh `String` khi pattern match |
| `if (...) { ... }` | Cấu trúc điều khiển bảo đảm nhánh true chỉ chạy khi pattern khớp |

`null` không match type pattern tham chiếu thông thường: `value == null` thì `value instanceof String text` trả `false`; `text` không được sử dụng ở đường đi đó. Biến mẫu được **khởi tạo bởi quá trình pattern matching**, không cần viết thêm `String text = ...`. Theo JLS, nó không phải một biến chưa khởi tạo rồi được phép đọc tùy tiện.

**Trước khi dùng pattern:**

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

**Dùng pattern trong Java hiện đại:**

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Dạng thứ hai loại bỏ cast thủ công, tránh lặp lại tên biến và khiến compiler quản lý đúng kiểu. Cả hai ví dụ trong mục này là **đoạn mã tích hợp**, không phải chương trình độc lập.

## 3. Gán lại hợp lệ: thao tác trên biến, không phải trên pattern

Xét:

```java
Object obj = "  Java  ";
if (obj instanceof String text) {
    String before = text;
    text = text.strip();
    System.out.println(before);
    System.out.println(text);
}
```

Hai lệnh in lần lượt cho `"  Java  "` và `"Java"` (giả sử giữ nguyên các dấu cách trong output). Khi pattern match, compiler xác định `text` có kiểu `String`. Sau đó:

1. `String before = text;` lưu tham chiếu trước khi gán lại.
2. `text.strip()` trả một giá trị `String` đã loại bỏ khoảng trắng đầu/cuối.
3. `text = ...` gán **một tham chiếu mới** cho chính biến local `text`, theo quy tắc gán biến bình thường.
4. `before` và `obj` **không bị gán lại** bởi thao tác `text = ...`.
5. Trong phần còn lại của phạm vi hợp lệ, `text` vẫn **có kiểu tĩnh `String`**; phép gán không biến một pattern variable thành biến kiểu động.

Việc một pattern đã match **không khóa tham chiếu ban đầu**. Cũng đừng nghĩ gán lại có thể “chạy lại” điều kiện `instanceof` hoặc đổi kết quả boolean đã được dùng để chọn nhánh. Điều kiện được đánh giá tại thời điểm chương trình đi qua nó; lệnh gán sau đó chỉ thay giá trị biến.

### 3.1. Giá trị mới phải tương thích với kiểu khai báo của pattern

```java
Object obj = "hello";

if (obj instanceof CharSequence chars) {
    chars = new StringBuilder("updated");  // Hợp lệ: thực thi CharSequence.
    System.out.println(chars.length());
}
```

Dạng này có thể gán một `StringBuilder` vì kiểu tĩnh của `chars` là `CharSequence`. Nhưng với:

```java
// KHÔNG biên dịch — String không nhận Integer.
if (obj instanceof String text) {
    text = Integer.valueOf(5);
}
```

Compiler báo lỗi tương thích kiểu. **Gán lại được** không có nghĩa có thể đưa bất kỳ object nào vào biến mẫu. Những quy tắc kiểm tra kiểu của biến local vẫn áp dụng.

### 3.2. Có thể gán `null`, nhưng không có bảo đảm an toàn khi dùng tiếp

```java
Object obj = "ok";

if (obj instanceof String text) {
    text = null;                 // Hợp lệ: String là kiểu tham chiếu.
    // System.out.println(text.length()); // NPE nếu bỏ comment.
}
```

Ở đầu nhánh, match `String` bảo đảm `text` khác `null`. Sau lệnh `text = null`, **biến mới mang `null`**; lời gọi `text.length()` sẽ ném `NullPointerException` nếu được thực thi. Compiler **không tái thực hiện pattern matching** để ngăn lỗi này. Vì vậy, đừng lạm dụng gán lại vào giá trị có thể null nếu phía sau giả định luôn non-null.

### 3.3. Gán lại biến không có nghĩa sửa dữ liệu trong object

Cùng là một tên biến nhưng có hai thao tác hoàn toàn khác:

- **Thay đổi object**: `buffer.append("-x")` làm thay đổi trạng thái của `StringBuilder` hiện đang được tham chiếu.
- **Thay đổi tham chiếu**: `buffer = new StringBuilder("fresh")` khiến biến `buffer` trỏ sang object khác; object cũ không tự biến mất hay bị thay đổi vì phép gán này.

Với `String`, các thao tác như `strip()` trả một giá trị String, không sửa nội dung String hiện có. Khi học quy tắc biến mẫu, luôn phân biệt **biến local** và **object**.

## 4. Chương trình đầy đủ: gán lại biến mẫu trong nhiều ngữ cảnh

**Tệp `PatternReassignmentDemo.java` — Java 17+:**

```java
import java.util.Locale;
import java.util.function.Supplier;

public class PatternReassignmentDemo {
    static String normalize(Object input) {
        if (input instanceof String text) {
            String before = text;
            text = text.strip();
            System.out.println("before=[" + before + "]");
            System.out.println("after=[" + text + "]");
            text = text.toUpperCase(Locale.ROOT);
            return "result=" + text + "; length=" + text.length();
        }
        return "not a String";
    }

    static int guardedLength(Object input) {
        if (!(input instanceof String text)) {
            return -1;
        }
        text = text.strip();
        return text.length();
    }

    static String validLabel(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            text = text.strip();
            return "valid=" + text;
        }
        return "invalid";
    }

    static String withLambda(Object input) {
        if (input instanceof String text) {
            String normalized = text.strip();
            Supplier<String> task =
                    () -> normalized.toUpperCase(Locale.ROOT);
            return task.get();
        }
        return "skip";
    }

    static String finalPattern(Object input) {
        if (input instanceof final String text) {
            return "final=" + text.length();
        }
        return "none";
    }

    public static void main(String[] args) {
        Object input = "  Java  ";
        System.out.println(normalize(input));
        System.out.println("input=[" + input + "]");
        System.out.println(normalize(15));
        System.out.println("guard=" + guardedLength(" A "));
        System.out.println("guard=" + guardedLength(null));
        System.out.println(validLabel("  Core "));
        System.out.println(validLabel(" "));
        System.out.println("lambda=" + withLambda(" hi "));
        System.out.println(finalPattern("ok"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 PatternReassignmentDemo.java
java PatternReassignmentDemo
```

**Stdout chính xác:**

```text
before=[  Java  ]
after=[Java]
result=JAVA; length=4
input=[  Java  ]
not a String
guard=1
guard=-1
valid=Core
invalid
lambda=HI
final=2
```

**Phân tích:**

- `normalize("  Java  ")` cho thấy biến mẫu `text` được **gán lại hai lần**: lần đầu `strip()`, lần sau `toUpperCase(Locale.ROOT)`. Mọi phép gán đều sinh ra `String`, nên hợp lệ. Giá trị `before` và `input` bên ngoài giữ nguyên.
- `normalize(15)` không match String và trả `"not a String"`; biến `text` của nhánh true không xuất hiện ở đường đi này.
- `guardedLength(...)` dùng nhánh phủ định `!(input instanceof String text)` để loại dữ liệu không phải String. Khi đi tiếp sau `if`, compiler biết match đã xảy ra, nên `text` vừa có phạm vi vừa có thể gán lại.
- `validLabel(...)` minh họa `&&`: `text.isBlank()` chỉ được đánh giá sau khi `instanceof` thành công. Trong thân true, gán lại `text` để chuẩn hóa là hợp lệ.
- `withLambda(...)` dùng **một biến riêng `normalized`** làm đầu vào cho lambda, giúp giữ biến được capture ở trạng thái *effectively final*. Phần 7 giải thích vì sao cách này an toàn hơn việc gán lại biến được lambda capture.
- `finalPattern(...)` chứng minh rằng cú pháp `instanceof final String text` có thể dùng để **cấm gán lại** khi cần.

## 5. Ví dụ đầy đủ: gán lại tham chiếu và thay đổi object

**Tệp `PatternReferenceDemo.java` — Java 17+:**

```java
public class PatternReferenceDemo {
    static void demonstrate(Object input) {
        if (input instanceof StringBuilder buffer) {
            buffer.append("-x");
            System.out.println("first=" + buffer);

            buffer = new StringBuilder("fresh");
            buffer.append("-y");
            System.out.println("rebound=" + buffer);
        }
        System.out.println("original=" + input);
    }

    public static void main(String[] args) {
        demonstrate(new StringBuilder("seed"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PatternReferenceDemo.java
java PatternReferenceDemo
```

**Stdout chính xác:**

```text
first=seed-x
rebound=fresh-y
original=seed-x
```

- `buffer.append("-x")` sửa **StringBuilder ban đầu**. Biến `input` và `buffer` lúc đó cùng tham chiếu một object, nên `input` về sau thấy `seed-x`.
- `buffer = new StringBuilder("fresh")` đổi giá trị của **biến mẫu** sang một object khác. Nó không tác động tới tham chiếu đang có trong `input`.
- `buffer.append("-y")` chỉ sửa object mới. Vì thế `buffer` in `fresh-y`, còn `input` vẫn in `seed-x`.

Đây là ví dụ cho thấy quy tắc “pattern variable có thể gán lại” nói về **biến**, không trực tiếp về tính bất biến của object được match. Ngay cả khi biến được khai báo `final`, trạng thái một object mutable có thể vẫn thay đổi qua phương thức; `final` chỉ cấm gán lại **tham chiếu** của biến đó.

## 6. Flow scoping: điều kiện để gán lại không chỉ là đúng kiểu

Một biến mẫu chỉ có ý nghĩa trong những vùng mà compiler chứng minh việc pattern matching **đã thành công**. Đây là **flow scoping**: phạm vi phụ thuộc vào điều kiện boolean và đường điều khiển chứ không đơn thuần là cặp dấu ngoặc `{...}`.

### 6.1. Bên trong `if` match thành công

```java
if (obj instanceof String text) {
    text = text.strip();       // Hợp lệ.
    System.out.println(text);
} else {
    // Không thể gán hay đọc text tại đây: pattern có thể không match.
}
// Không thể đọc hoặc gán text ở đây nếu if có thể đi theo nhánh false.
```

Đoạn này là **snippet** cần biến `obj` trong phương thức. `text` tồn tại ở nhánh true, nhưng không còn ở vùng sau `if` nếu chương trình có thể đi qua cả true lẫn false. Gán lại **không kéo dài phạm vi**.

### 6.2. Sau guard clause phủ định

```java
static String tidy(Object obj) {
    if (!(obj instanceof String text)) {
        return "not-text";
    }
    text = text.strip();       // Hợp lệ: đường đi này phải đã match.
    return text;
}
```

Khi đi tới dòng `text = ...`, nhánh không khớp đã `return`. Do đó biến mẫu được đưa vào scope ở phần sau. Mẫu guard này thường giúp tránh nhiều mức `if` lồng nhau.

Nếu nhánh phủ định chỉ ghi log và tiếp tục chạy, thì match **không được đảm bảo** ở phần sau; compiler không cho dùng `text` tại đó.

### 6.3. Toán tử `&&`: biến đã được match ở vế phải

```java
if (obj instanceof String text && text.length() > 0) {
    text = text.strip();       // Hợp lệ trong thân.
    System.out.println(text);
}
```

Toán tử `&&` **short-circuit**: vế phải chỉ chạy khi vế trái `true`. Vì vậy `text.length()` hợp lệ. Thậm chí về mặt cú pháp, trong Java 17+ có thể gán lại ngay trong vế phải:

```java
// HỢP LỆ, nhưng khó đọc vì có side effect trong điều kiện.
if (obj instanceof String text &&
        (text = text.strip()).length() > 0) {
    System.out.println(text);
}
```

Cách viết này đã hợp lệ ở **Java 17**, nhưng **không phải khuyến nghị mặc định**. Để dễ bảo trì, nên đặt phần chuẩn hóa thành một lệnh rõ ràng trong thân `if` hoặc dùng helper có tên. Nếu điều kiện thực sự phải kiểm tra chuỗi **sau chuẩn hóa**, hãy đặt kiểm tra ở vị trí phản ánh đúng ý nghĩa:

```java
if (obj instanceof String text) {
    String normalized = text.strip();
    if (!normalized.isEmpty()) {
        System.out.println(normalized);
    }
}
```

Tránh kết hợp quá nhiều phép gán và toán tử boolean khiến reviewer phải suy luận phức tạp về side effects.

### 6.4. Toán tử `||`: không phải lúc nào biến cũng sẵn có

```java
// KHÔNG BIÊN DỊCH.
if (obj instanceof String text || text.length() > 0) {
    System.out.println("test");
}
```

Vế phải `||` chạy **khi vế trái false**, nên compiler không thể bảo đảm `text` đã được match. Không được đọc **hoặc gán** `text` trong đường đi không có scope.

Ví dụ ngược lại với phủ định có thể hợp lệ:

```java
if (!(obj instanceof String text) || text.isBlank()) {
    System.out.println("invalid");
}
```

Ở ví dụ này, khi chạy vế phải của `||`, vế trái phủ định phải đã false; có nghĩa `instanceof String text` đã match thành công. Tuy nhiên, viết rõ ràng bằng guard thường dễ hiểu hơn.

### 6.5. Phạm vi không bị “mở rộng” bằng một phép gán

```java
// KHÔNG BIÊN DỊCH.
if (obj instanceof String text) {
    text = text.strip();
}
return text; // Biến không có phạm vi ở đây.
```

Dù đã gán cho `text` ở nhánh true, đường đi false vẫn có thể đến `return`. Quy tắc scope của pattern variable **không phụ thuộc vào** việc bạn cố gán nó một lần hoặc nhiều lần; nó phụ thuộc vào việc pattern matching đã được chứng minh ở **mọi đường đến điểm sử dụng**.

## 7. `final` và *effectively final*: hai giới hạn khác nhau

### 7.1. Biến mẫu mặc định không `final`, nhưng có thể khai báo `final` tường minh

Cú pháp hiện đại hợp lệ:

```java
if (obj instanceof final String text) {
    System.out.println(text.strip());
    // text = "new";  // Lỗi: biến text đã được khai báo final.
}
```

Nếu có từ khóa `final` thì mọi lệnh gán lại `text` sau khi pattern đã khởi tạo đều là lỗi biên dịch, kể cả phép gán cho một `String` khác. Điều này **không mâu thuẫn** với JEP 394: JEP 394 bỏ `final` **ngầm định**, không cấm người lập trình **tự khai báo** `final`.

| Cú pháp | Gán lại trong phạm vi hợp lệ? | Vì sao |
| --- | --- | --- |
| `obj instanceof String text` | **Có** | Biến mẫu mặc định không final |
| `obj instanceof final String text` | **Không** | Đã khai báo `final` |
| `obj instanceof CharSequence text` | **Có**, với giá trị tương thích `CharSequence` | Kiểu của biến là `CharSequence` |
| `obj instanceof String text` rồi `text = Integer.valueOf(1)` | **Không** | Bất tương thích kiểu `Integer` → `String` |
| Biến mẫu được gán lại nhưng dùng bên ngoài scope | **Không** | Không còn được phép tham chiếu biến mẫu |
| Biến mẫu đã gán lại, sau đó lambda muốn capture | **Không**, nếu không *effectively final* | Quy tắc capture của local variables |

### 7.2. *Effectively final* khi capture trong lambda

Một biến local hoặc pattern variable được lambda sử dụng từ scope bao ngoài phải là **`final` hoặc *effectively final***. *Effectively final* nghĩa là dù không ghi `final`, biến không bị gán lại theo quy tắc ngôn ngữ.

**Ví dụ đúng**:

```java
if (obj instanceof String text) {
    java.util.function.Supplier<String> task =
            () -> text.toUpperCase(java.util.Locale.ROOT);
    System.out.println(task.get());
}
```

`text` không bị gán lại nên có thể capture. **Ví dụ sai**:

```java
// KHÔNG BIÊN DỊCH.
if (obj instanceof String text) {
    text = text.strip();
    java.util.function.Supplier<String> task =
            () -> text.toUpperCase();
}
```

Compiler báo tương đương `local variables referenced from a lambda expression must be final or effectively final`. Dù phép gán lại xảy ra **trước khi tạo lambda**, biến `text` đã mất tính effectively final của nó. Không có cơ chế cho rằng “lệnh gán đã chạy xong nên lambda được phép capture”.

**Cách sửa rõ ràng:**

```java
if (obj instanceof String text) {
    String normalized = text.strip();
    java.util.function.Supplier<String> task =
            () -> normalized.toUpperCase(java.util.Locale.ROOT);
    System.out.println(task.get());
}
```

`normalized` được khởi tạo một lần và không gán lại, nên đủ điều kiện capture. Hoặc khai báo `final String normalized = text.strip();` để thể hiện chủ đích.

Quy tắc tương tự áp dụng khi một local/anonymous class tham chiếu local variable từ scope bên ngoài. **Gán lại biến mẫu là hợp lệ tự thân**, nhưng nó có thể khiến một **cách sử dụng khác** của biến ấy không hợp lệ.

## 8. Biến mẫu nhận kiểu tĩnh cố định; đừng nhầm với object runtime

Dù pattern variable có thể nhận một tham chiếu mới, **kiểu khai báo không đổi**. Ví dụ:

```java
Object input = "abc";

if (input instanceof CharSequence chars) {
    chars = new StringBuilder("xyz");
    System.out.println(chars.length()); // Hợp lệ vì CharSequence có length().
    // chars.strip(); // KHÔNG BIÊN DỊCH: CharSequence không có strip().
}
```

`chars` luôn có kiểu tĩnh `CharSequence` dù object ban đầu là `String` và object mới là `StringBuilder`. Java kiểm tra phương thức dựa trên kiểu tĩnh; muốn gọi phương thức riêng của implementation thì cần cấu trúc kiểu phù hợp.

**Biến `input` và biến `chars` là hai biến khác nhau.** Việc đổi `chars` không thay đổi `input`, trừ khi bạn chủ động gán cho `input` hoặc dùng object có trạng thái thay đổi thông qua một tham chiếu chung như ví dụ `StringBuilder`.

Gán lại không tạo một instance có kiểu runtime mới tự động; chỉ **lưu một tham chiếu tới object đang tồn tại hoặc object bạn vừa tạo**. Trong ứng dụng, đừng lạm dụng cùng một tên cho quá nhiều trạng thái trung gian; điều đó làm mất lợi ích dễ đọc của pattern matching.

## 9. Khi nào nên gán lại, khi nào nên dùng biến mới?

**Nên cân nhắc gán lại** khi chỉ có một ý nghĩa xuyên suốt (ví dụ loại bỏ khoảng trắng của `text`), không cần giá trị gốc trong phần còn lại của nhánh và không có lambda/inner class cần capture biến mẫu:

```java
if (obj instanceof String text) {
    text = text.strip();
    return text.isEmpty() ? "(empty)" : text;
}
```

Đây là **snippet minh họa bên trong phương thức trả `String`**; `obj` được khai báo phù hợp.

**Nên tạo biến mới** khi cần so sánh trước/sau, nhiều bước transform có thể làm khó theo dõi, hoặc cần bảo toàn giá trị nguồn, bảo đảm *effectively final* cho lambda:

```java
if (obj instanceof String text) {
    String normalized = text.strip();
    String upper = normalized.toUpperCase(java.util.Locale.ROOT);
    System.out.println("before=" + text);
    System.out.println("after=" + upper);
}
```

**Nên khai báo `final` tường minh** nếu convention dự án nhấn mạnh việc không gán lại tham chiếu hoặc đoạn logic dài và bạn muốn compiler bắt mọi thao tác thay tham chiếu:

```java
if (obj instanceof final String text) {
    System.out.println(text.strip());
}
```

Dù chọn phương án nào, nhớ rằng **kiểu dữ liệu không quyết định toàn bộ bất biến nghiệp vụ**. Với `StringBuilder`, `List` hay object mutable, `final` chỉ bảo vệ **tham chiếu của biến**, không bảo vệ trạng thái của object.

## 10. Những lỗi thường gặp và cách sửa

### 10.1. Nhầm quy tắc từ giai đoạn Java 14 preview

Một số bài viết preview cũ cho rằng pattern variable **mặc nhiên `final`** nên không được gán lại. Điều này không còn đúng theo **JEP 394 / Java 16+**. Khi dự án dùng Java 17+, viết `text = text.strip()` là hợp lệ trong scope. Chỉ giới thiệu hành vi **đã chính thức**, không giữ lại giới hạn preview cũ.

### 10.2. Gán sai kiểu

```java
// SAI, không biên dịch.
if (obj instanceof String text) {
    text = 123;
}
```

Biến mẫu có kiểu tĩnh `String`. Một literal `int` không thể được gán làm `String`. Sửa thành một biểu thức trả String như `Integer.toString(123)` nếu đó là mục tiêu nghiệp vụ.

### 10.3. Gán ngoài phạm vi match

```java
// SAI, không biên dịch.
if (obj instanceof String text) {
    System.out.println(text);
}
text = "after";
```

Khi điều kiện false, biến không tồn tại ở đường đi sau `if`. Sửa bằng cách giữ phép gán ở nhánh match đúng hoặc khai báo một biến mới bên ngoài và gán theo các nhánh phù hợp.

### 10.4. Nhầm `&&` với `||`

```java
// SAI, không biên dịch.
if (obj instanceof String text || text.isEmpty()) {
    System.out.println("invalid");
}
```

`||` không bảo đảm pattern match trước khi dùng biến ở vế phải. Sửa bằng logic rõ:

```java
if (obj instanceof String text && text.isEmpty()) {
    System.out.println("empty string");
}
```

Hoặc nếu muốn xử lý cả “không phải String” và “String rỗng”, dùng guard phủ định phù hợp.

### 10.5. Gán lại biến đã khai báo `final`

```java
// SAI, không biên dịch.
if (obj instanceof final String text) {
    text = text.strip();
}
```

Sửa bằng một tên khác như `String normalized = text.strip();` hoặc bỏ `final` nếu thật sự cần gán lại.

### 10.6. Gán lại rồi capture trong lambda

```java
// SAI, không biên dịch.
if (obj instanceof String text) {
    text = text.strip();
    Runnable task = () -> System.out.println(text);
}
```

Muốn lambda dùng giá trị đã chuẩn hóa, gán vào một biến riêng **không bị gán lại** rồi capture biến đó.

### 10.7. Gán `null` rồi cho rằng pattern bảo vệ mọi phép gọi sau đó

Pattern bảo đảm lúc match thành công giá trị có kiểu phù hợp và khác `null`. Sau đó bạn vẫn có thể gán `null` (nếu biến không `final`); mọi phép gọi method cần kiểm tra lại giả định non-null. Đừng xem type pattern là hệ thống theo dõi tất cả trạng thái tham chiếu về sau.

### 10.8. Cùng tên với một local variable khác đang trong phạm vi

```java
// SAI, không biên dịch.
String text = "outer";
if (obj instanceof String text) {
    System.out.println(text);
}
```

Đây là lỗi **trùng khai báo tên trong scope**, khác với việc gán lại một biến đã có. Sửa bằng tên biến mẫu khác (`matchedText`) hoặc tổ chức lại phạm vi.

### 10.9. Nhầm gán lại với thay đổi dữ liệu

`buffer.append(...)` sửa object được tham chiếu; `buffer = otherBuffer` đổi object mà biến mẫu trỏ tới. Nếu nhiều tham chiếu cùng trỏ object mutable, một lệnh gọi method có thể ảnh hưởng tất cả người quan sát. Khi code cần snapshot độc lập, hãy copy dữ liệu phù hợp; không chỉ dựa vào `final` hay pattern.

## 11. Bài tập thực hành

1. **Gán lại hợp lệ:** viết `Object value = "  Hello  ";`, dùng `if (value instanceof String text)` rồi `text = text.strip();`. In cả `text` và `value`. Giải thích vì sao hai biến hiển thị khác nhau.
2. **Thử với `final`:** đổi pattern thành `instanceof final String text`, giữ dòng gán lại; dự đoán thông báo lỗi compiler. Sửa bằng `String normalized = text.strip();`.
3. **Sai kiểu:** trong pattern `String text`, thử gán `Integer.valueOf(12)`. Chọn một API chuyển đổi hợp lệ nếu thật sự cần chuỗi.
4. **Flow scoping:** viết nhánh `if (obj instanceof String text)`, gán lại bên trong; thử dùng `text` sau `if`. Giải thích vì sao gán lại không kéo dài scope.
5. **Guard clause:** viết phương thức trả độ dài của String đã trim, trả `-1` cho kiểu khác, dùng `if (!(obj instanceof String text)) return -1;` rồi `text = text.strip();`.
6. **Short circuit:** thử `obj instanceof String text && text.length() > 2` và `obj instanceof String text || text.length() > 2`. Giải thích chỉ một biểu thức hợp lệ.
7. **Lambda:** tạo `Supplier<String>` từ biến mẫu không gán lại, sau đó thêm một phép `text = ...` và quan sát lỗi *effectively final*. Sửa bằng biến `normalized`.
8. **Tham chiếu và object:** dùng pattern `StringBuilder buffer`, gọi `append()`, rồi gán `buffer = new StringBuilder("new")`. Dự đoán đầu ra của biến `Object input` ban đầu.
9. **Kiểu tĩnh:** match `CharSequence chars` từ `String`, sau đó gán cho nó `new StringBuilder("x")`. Giải thích vì sao `chars.length()` hợp lệ nhưng `chars.strip()` không.
10. **Cập nhật code cũ:** tìm một đoạn mã cho rằng mọi pattern variables đều `final`. Trình bày quy tắc đúng từ Java 16 và tiêu chí để chọn gán lại, biến mới hoặc `final` tường minh.

**Đáp án gợi ý:** (1) `text` được gán lại, còn `value` không; (2) `final` cấm gán lại; (3) phải tương thích với `String`; (4) scope theo luồng match không đổi do assignment; (5) phủ định thoát sớm chứng minh match cho phần còn lại; (6) `&&` dùng biến khi match true; (7) lambda cần biến `final` hoặc *effectively final*; (8) đổi tham chiếu khác với mutate object; (9) kiểu tĩnh `CharSequence` quyết định API gọi được; (10) JEP 394 bỏ implicit-final nhưng không bỏ các kiểm tra kiểu, scope và capture.

## 12. Tài liệu chính thức

- **OpenJDK JEP 394 — Pattern Matching for `instanceof` (Java 16):** quy tắc chính thức, bỏ trạng thái *implicitly final* cho pattern variable: https://openjdk.org/jeps/394
- **Oracle Java 16 Language Changes:** xác nhận pattern matching for `instanceof` trở thành tính năng vĩnh viễn từ Java 16 và biến mẫu không còn implicitly final: https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html
- **Oracle Java 17 — Pattern Matching for `instanceof`:** hướng dẫn type patterns, phạm vi biến mẫu trong `if`, `&&`, `||` và guard: https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html
- **JLS Java SE 25, `14.30 — Patterns:** pattern variables là biến local được khởi tạo khi match thành công: https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.30
- **JLS Java SE 25, `6.3 — Scope of Pattern Variable Declarations:** quy tắc phạm vi phụ thuộc luồng điều khiển: https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3
- **JLS Java SE 25, `4.12.4 — `final` Variables:** khác biệt giữa final và effectively final, ý nghĩa gán lại tham chiếu: https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4
- **JLS Java SE 25, `15.27.2 — Lambda Body:** yêu cầu về local variable được lambda capture: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.2
- **OpenJDK JEP 305:** bối cảnh tính năng từng là preview ở Java 14; chỉ dùng để phân biệt lịch sử, không áp dụng giới hạn preview vào code hiện đại: https://openjdk.org/jeps/305

**Ghi nhớ:** pattern matching **khởi tạo** biến mẫu khi điều kiện match thành công. Sau đó, trên Java 16+ biến ấy **được phép gán lại** như một biến local thông thường, **nếu** vẫn nằm trong scope, phép gán tương thích kiểu, không bị khai báo `final` và không vi phạm yêu cầu *effectively final* khi capture. Quy tắc này giúp code linh hoạt, nhưng việc dùng tên biến riêng cho giá trị đã chuẩn hóa thường dễ đọc hơn khi logic lớn dần.