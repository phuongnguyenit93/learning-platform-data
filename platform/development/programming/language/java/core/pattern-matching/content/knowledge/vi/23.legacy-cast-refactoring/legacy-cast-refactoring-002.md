# Refactor một nhánh kiểm tra kiểu: từ `instanceof` + cast sang pattern matching

## 1. Mục tiêu của refactor

Trong Java trước khi có *pattern matching for `instanceof`*, một nhánh kiểm tra kiểu thường có hai thao tác liên tiếp:

1. Kiểm tra giá trị có thuộc kiểu cần xử lý bằng `instanceof`.
2. Nếu đúng, ép kiểu thủ công (*cast*) cùng giá trị sang kiểu đó để gọi phương thức hoặc dùng dữ liệu.

Ví dụ:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Từ **Java 16** (JEP 394), có thể gom hai việc trên thành một **type pattern**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` bên trong `instanceof` vừa xác định kiểu cần kiểm tra, vừa khai báo **pattern variable** `text`. Khi điều kiện khớp, `text` có kiểu tĩnh là `String` và tham chiếu đến chính đối tượng đã được kiểm tra. Java **không tạo đối tượng `String` mới** và cũng không biến đổi nội dung của đối tượng.

Trong bài này, phạm vi là **refactor một nhánh kiểm tra kiểu** của chương trình đang có: loại bỏ cast dư thừa, bảo toàn đường đi `if`/`else` và giá trị xử lý. Đây là kỹ thuật nhỏ nhưng thường gặp khi nâng cấp mã Java cũ. **Java 17** đã hỗ trợ type pattern trong `instanceof`; với Java 21, ta còn có thể cân nhắc record pattern khi dữ liệu đầu vào là record.

## 2. Ví dụ trước/sau: một nhánh, cùng hành vi

### Trước refactor: kiểm tra rồi ép kiểu

```java
static void handleLegacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println("text=" + text.strip().toUpperCase());
    } else {
        System.out.println("unsupported");
    }
}
```

Nhánh `if` chỉ chạy khi `value` là `String`, nên cast `(String) value` trong nhánh đó là an toàn. Tuy nhiên, việc lặp lại tên kiểu `String` và biểu thức `value` khiến mã dài hơn cần thiết.

### Sau refactor: type pattern ngay trong `instanceof`

```java
static void handleModern(Object value) {
    if (value instanceof String text) {
        System.out.println("text=" + text.strip().toUpperCase());
    } else {
        System.out.println("unsupported");
    }
}
```

Hai phương thức có cùng ý định: xử lý `String` và đưa những giá trị còn lại vào nhánh `else`. `text` chỉ được dùng ở nhánh mà compiler đã chứng minh matching thành công.

**Chương trình hoàn chỉnh:** lưu vào `SingleBranchRefactor.java`:

```java
import java.util.Locale;

public class SingleBranchRefactor {
    static void legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            System.out.println("old:" +
                    text.strip().toUpperCase(Locale.ROOT));
        } else {
            System.out.println("old:skip");
        }
    }

    static void modern(Object value) {
        if (value instanceof String text) {
            System.out.println("new:" +
                    text.strip().toUpperCase(Locale.ROOT));
        } else {
            System.out.println("new:skip");
        }
    }

    public static void main(String[] args) {
        Object[] cases = {" java ", 42, null};

        for (Object value : cases) {
            legacy(value);
            modern(value);
        }
    }
}
```

Biên dịch và chạy với JDK 21:

```bash
javac --release 21 SingleBranchRefactor.java
java SingleBranchRefactor
```

Kết quả:

```text
old:JAVA
new:JAVA
old:skip
new:skip
old:skip
new:skip
```

Tiền tố `old:` và `new:` được dùng để phân biệt kết quả của hai phương thức; nội dung được xử lý là tương đương. Với `42` và `null`, cả hai đều đi vào nhánh `else`.

## 3. Quy trình refactor an toàn cho đúng một nhánh

Một thao tác refactor nhỏ nên có các bước rõ ràng:

1. **Xác định phép kiểm tra hiện có.** Ví dụ `if (input instanceof Customer)`.
2. **Xác định cast tương ứng ngay trong nhánh thành công.** Ví dụ `Customer customer = (Customer) input;`.
3. **Chuyển tên biến vào type pattern.** Thành `if (input instanceof Customer customer)`.
4. **Xóa đúng cast và khai báo biến đã được thay thế.** Giữ lại logic xử lý, nhánh `else`, các thao tác trả kết quả và bắt ngoại lệ đang có.
5. **Biên dịch và kiểm tra các đường đi.** Ít nhất là một giá trị đúng kiểu, một giá trị không đúng kiểu và `null` nếu tham chiếu có thể là `null`.

Ví dụ chuyển đổi cơ học:

```java
// Trước
if (candidate instanceof Number) {
    Number number = (Number) candidate;
    System.out.println(number.intValue());
}

// Sau
if (candidate instanceof Number number) {
    System.out.println(number.intValue());
}
```

Không cần thay `Number` thành `Integer` chỉ vì dữ liệu ví dụ hiện tại là `Integer`. Làm như vậy **thu hẹp tập kiểu được chấp nhận**: `Number` còn có các subtype như `Long`, `Double` và `BigDecimal`. Khi mục tiêu chỉ là refactor, **giữ nguyên kiểu ở điều kiện cũ**.

Tương tự, nếu nhánh cũ có `else`, đừng xóa hoặc thay đổi `else` nếu chưa có yêu cầu thiết kế mới. Một refactor tốt có thể được review bằng cách đối chiếu thẳng từng dòng trước/sau.

## 4. Ngữ nghĩa cần được giữ nguyên

Với cùng một biểu thức ổn định `value`, cùng kiểu kiểm tra `T` và cùng thân xử lý, các đoạn mã dưới đây thực hiện cùng phép thử kiểu và sử dụng cùng đối tượng sau khi thử thành công:

```java
// Cách cũ
if (value instanceof CharSequence) {
    CharSequence seq = (CharSequence) value;
    consume(seq);
}

// Cách mới
if (value instanceof CharSequence seq) {
    consume(seq);
}
```

Ở đây, `consume(seq)` chỉ là **phương thức giả định có sẵn trong ngữ cảnh**; hai đoạn dùng để so sánh cấu trúc refactor, không phải chương trình độc lập.

Các điểm quan trọng:

| Tình huống | `instanceof` + cast trong nhánh | Type pattern |
| --- | --- | --- |
| Giá trị thuộc kiểu cần kiểm tra | Nhánh chạy, cast hợp lệ | Nhánh chạy, biến pattern được ràng buộc |
| Giá trị thuộc subtype hợp lệ | Nhánh chạy | Nhánh chạy |
| Giá trị không thuộc kiểu | Điều kiện `false`, nhánh bị bỏ qua | Điều kiện `false`, nhánh bị bỏ qua |
| Giá trị `null` | `instanceof` là `false`, không thực hiện cast trong nhánh | `instanceof` là `false`, không ràng buộc biến |
| Có nhánh `else` | `else` chạy nếu không khớp | `else` chạy nếu không khớp |
| Đối tượng sau kiểm tra | Tham chiếu đến giá trị gốc | Tham chiếu đến giá trị gốc |

**Đừng nhầm `instanceof` với cast trực tiếp không có kiểm tra trước.** Nếu viết `String s = (String) value;` ngoài nhánh bảo vệ, giá trị sai kiểu có thể ném `ClassCastException`; refactor bằng type pattern không cần hành vi ấy.

Với `null`, `value instanceof String text` trả `false` chứ không ném `NullPointerException`. Đây là hành vi tương ứng với `value instanceof String` trước refactor.

## 5. Phạm vi của pattern variable: *flow scoping*

Khác với khai báo biến cục bộ thông thường ở đầu block, pattern variable tuân theo **phạm vi phụ thuộc luồng điều khiển** (*flow scoping*): nó chỉ có mặt ở những vị trí compiler chắc chắn phép matching đã thành công.

Hợp lệ:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Không hợp lệ nếu cố dùng biến trong `else` hoặc ngay sau `if` khi nhánh thành công có thể bị bỏ qua:

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // Không thể dùng text ở đây: pattern đã không khớp.
}

// Không thể mặc định dùng text ở đây.
```

Biến `text` không được khai báo cho mọi đường đi như một biến được khởi tạo sẵn bằng `null`. Đây là cơ chế an toàn kiểu và khởi tạo của Java.

Nếu bên ngoài đã có một biến cục bộ tên `text` gây xung đột phạm vi, hãy chọn tên pattern variable khác (ví dụ `matchedText`) thay vì đổi tùy tiện những biến không liên quan.

## 6. Kết hợp điều kiện với `&&`

Một refactor thường có thêm điều kiện nghiệp vụ kiểm tra sau phép thử kiểu:

```java
// Cũ
if (value instanceof String) {
    String text = (String) value;
    if (!text.isBlank()) {
        System.out.println(text.trim());
    }
}
```

Có thể giữ nguyên cấu trúc hai tầng, hoặc gộp điều kiện khi chủ đích là chỉ xử lý chuỗi không trắng:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

Vế phải của `&&` chỉ được đánh giá khi pattern ở vế trái đã khớp; vì vậy `text.isBlank()` an toàn về kiểu và không gây lỗi do `value == null`.

Chương trình hoàn chỉnh `CompoundConditionDemo.java`:

```java
public class CompoundConditionDemo {
    static void print(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("content=" + text.trim());
        } else {
            System.out.println("empty-or-other");
        }
    }

    public static void main(String[] args) {
        print(" hello ");
        print(" ");
        print(1);
        print(null);
    }
}
```

```bash
javac --release 21 CompoundConditionDemo.java
java CompoundConditionDemo
```

Kết quả:

```text
content=hello
empty-or-other
empty-or-other
empty-or-other
```

**Cẩn thận khi gộp nhánh:** nếu bản cũ có một `else` gắn với `if` kiểm tra kiểu, chuyển điều kiện nghiệp vụ vào `&&` có thể làm `else` chạy thêm khi đúng kiểu nhưng không đạt điều kiện nghiệp vụ. Việc gộp trên chỉ đúng khi bạn đã xác định được hành vi mong muốn của mọi nhánh.

**`||` không có bảo đảm tương tự.** Biểu thức `value instanceof String text || anotherCondition` có thể đúng vì `anotherCondition` dù pattern thất bại. Do đó, không được dùng `text` trong nhánh `if` như thể nó luôn được ràng buộc. Đừng đảo toán tử `&&` thành `||` chỉ để mã ngắn hơn.

## 7. Guard clause: giảm lồng nhau nhưng vẫn giữ kiểm tra kiểu

Trong một phương thức kết thúc sớm khi dữ liệu sai kiểu, có thể biến nhánh kiểm tra thành *guard clause*. Trước:

```java
static void handle(Object candidate) {
    if (candidate instanceof CharSequence) {
        CharSequence text = (CharSequence) candidate;
        System.out.println(text.length());
    } else {
        System.out.println("unsupported");
        return;
    }
}
```

Sau:

```java
static void handle(Object candidate) {
    if (!(candidate instanceof CharSequence text)) {
        System.out.println("unsupported");
        return;
    }

    System.out.println(text.length());
}
```

Mã mới đảo điều kiện nhưng **nhánh không khớp kết thúc bằng `return`**. Bởi vậy, ở dòng sau guard, compiler chứng minh `candidate instanceof CharSequence text` phải đã thành công. Nếu nhánh sai kiểu không kết thúc (vẫn có đường chạy tiếp), compiler không cho dùng `text` như vậy.

Chương trình độc lập `GuardClauseDemo.java`:

```java
public class GuardClauseDemo {
    static void handle(Object candidate) {
        if (!(candidate instanceof CharSequence text)) {
            System.out.println("unsupported");
            return;
        }

        System.out.println("length=" + text.length());
    }

    public static void main(String[] args) {
        handle("abc");
        handle(new StringBuilder("xy"));
        handle(null);
    }
}
```

```bash
javac --release 21 GuardClauseDemo.java
java GuardClauseDemo
```

Kết quả:

```text
length=3
length=2
unsupported
```

`CharSequence` là interface: cả `String` và `StringBuilder` đều phù hợp. Refactor giữ kiểu `CharSequence` nên không vô tình loại trừ `StringBuilder`.

**Chỉ thực hiện bước đảo điều kiện khi đã kiểm tra đầy đủ luồng điều khiển.** Trong refactor nhỏ của một nhánh, thay trực tiếp `instanceof` + cast thường ít rủi ro nhất; guard clause là cải tiến thêm nếu nó giữ nguyên đường đi và các tác dụng phụ.

## 8. Một nhánh có `else`: kiểm tra khả năng thay đổi thứ tự tác dụng phụ

Với một biến thông thường `value`, phép kiểm tra và cast của mẫu cũ đã thao tác trên cùng giá trị. Nhưng có mã cũ viết lặp lại **biểu thức có tác dụng phụ**:

```java
// Ví dụ có vấn đề: getNext() bị gọi ở hai thời điểm.
if (source.getNext() instanceof String) {
    String text = (String) source.getNext();
    use(text);
}
```

`source.getNext()` có thể trả **hai giá trị khác nhau** sau hai lần gọi, hoặc cập nhật vị trí con trỏ, ghi log, đọc I/O. Thay thành:

```java
if (source.getNext() instanceof String text) {
    use(text);
}
```

làm cho `getNext()` chỉ chạy **một lần**. Cách mới có thể đúng hơn về logic, nhưng **không phải refactor giữ nguyên hành vi tuyệt đối** khi việc gọi lặp có tác dụng phụ. Phải đánh giá cách hoạt động của `getNext()` trước khi tuyên bố tương đương.

Trong trường hợp code cũ đã lưu giá trị một lần, cách an toàn là giữ biến trung gian:

```java
Object candidate = source.getNext();

if (candidate instanceof String text) {
    use(text);
}
```

Cả hai ví dụ `source.getNext()`/`use(text)` trong mục này đều **là mã minh họa trong một lớp đã khai báo các thành phần đó**, không phải chương trình độc lập.

Ngoài ra, chuyển mã giữa các nhánh có thể thay đổi thời điểm gọi phương thức, trạng thái đối tượng, logging hoặc ngoại lệ. **Refactor một nhánh** nên hạn chế di chuyển logic nghiệp vụ nếu không có mục tiêu riêng.

## 9. Giới hạn của generic type pattern

Không phải cast nào cũng chuyển thẳng thành một phép `instanceof` với tham số kiểu bất kỳ. Java generic có **type erasure**: ở runtime, không thể kiểm tra trực tiếp nhiều kiểu tham số hóa như `List<String>`.

Ví dụ sau **không biên dịch** khi `input` có kiểu `Object`:

```java
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Lý do là `List<String>` không phải kiểu có thể được kiểm tra đầy đủ bởi `instanceof` ở ngữ cảnh đó. Thay vào đó, có thể kiểm tra `List<?>` và xử lý phần tử theo nhu cầu:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
```

Ví dụ hoàn chỉnh `GenericCheckDemo.java`:

```java
import java.util.List;

public class GenericCheckDemo {
    static void handle(Object input) {
        if (input instanceof List<?> values) {
            System.out.println("size=" + values.size());
        } else {
            System.out.println("not-list");
        }
    }

    public static void main(String[] args) {
        handle(List.of("a", "b"));
        handle("other");
    }
}
```

```bash
javac --release 21 GenericCheckDemo.java
java GenericCheckDemo
```

Kết quả:

```text
size=2
not-list
```

Điều kiện `List<?>` **không xác nhận từng phần tử là `String`**. Nếu logic cần `String`, tiếp tục kiểm tra từng phần tử hoặc thiết kế API với generic type chính xác. Không thêm unchecked cast sang `List<String>` chỉ để đổi được cú pháp.

## 10. Khi nào dùng record pattern thay vì type pattern?

Nếu nhánh kiểm tra kiểu một record nhưng sau đó lại gọi nhiều accessor để lấy component, Java 21 cho phép cân nhắc **record pattern**. Đây là bước refactor **rộng hơn** so với chỉ bỏ cast: nó thay đổi hình thức truy cập component và cần xem kỹ cách record/`null`/accessor hoạt động.

Ví dụ:

```java
record Point(int x, int y) {}

static void print(Object input) {
    if (input instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

`Point(var x, var y)` vừa matching kiểu record `Point`, vừa giải cấu trúc hai component bằng accessor của record. `x` và `y` được suy luận thành `int`. Với input `null` hoặc sai kiểu, `instanceof` trả `false`.

Lưu ý: **type pattern cho `instanceof` chính thức từ Java 16**, còn **record patterns chính thức từ Java 21** (JEP 440). Nếu mục tiêu tương thích Java 17, dùng `input instanceof Point point` và gọi `point.x()`, `point.y()`; đừng đặt record pattern vào source cần biên dịch `--release 17`.

Accessor do record tự định nghĩa có thể có tác dụng phụ hoặc ném ngoại lệ; record pattern không đơn thuần là thay một cast bằng tên biến mới. Muốn bảo toàn tuyệt đối hành vi một nhánh cũ, hãy ưu tiên bước **type pattern** trực tiếp trước khi cân nhắc giải cấu trúc.

## 11. Những trường hợp không nên refactor máy móc

1. **Thay đổi kiểu kiểm tra.** `instanceof Number` chuyển thành `instanceof Integer` sẽ thay đổi trường hợp được chấp nhận.
2. **Dời lời gọi phương thức.** Nếu biểu thức nguồn hoặc code trong nhánh có tác dụng phụ, thay vị trí có thể thay đổi kết quả.
3. **Xóa đường đi `else`.** Phần xử lý khi kiểu không khớp vẫn thuộc hợp đồng của phương thức.
4. **Dùng pattern variable ngoài phạm vi.** Pattern variable chỉ có mặt nơi phép matching chắc chắn thành công.
5. **Gộp `&&` vào một `if` có `else` mà không xem lại điều kiện.** Điều kiện nghiệp vụ thất bại có thể làm nhánh `else` chạy theo cách khác bản cũ.
6. **Cố dùng `List<String>` với `instanceof` trên `Object`.** Type erasure ngăn việc kiểm tra generic type arguments theo cách đó.
7. **Tạo tên biến trùng với biến địa phương đang tồn tại.** Chọn tên mới rõ nghĩa và không gây va chạm phạm vi.
8. **Giả định pattern tạo bản sao dữ liệu.** Pattern variable tham chiếu đến đối tượng đã khớp; đối tượng mutable vẫn là chính nó.
9. **Coi refactor cú pháp là lý do thay đổi xử lý `null` hoặc ngoại lệ.** Hãy bảo toàn trước, cải tiến hành vi bằng một thay đổi riêng nếu cần.
10. **Chuyển toàn bộ chuỗi `if/else if` thành `switch` không có nhu cầu.** Với một nhánh kiểm tra kiểu, `instanceof T t` thường là thay đổi nhỏ và dễ review.

## 12. Kiểm thử cần thiết sau refactor

Một refactor chỉ một nhánh thường không cần test phức tạp nếu có thể chứng minh cấu trúc tương đương và chạy kiểm tra hiện có. Tuy nhiên, với mã nghiệp vụ quan trọng, nên có các tình huống rõ ràng:

| Input | Nhánh mong đợi | Ý nghĩa |
| --- | --- | --- |
| Đối tượng đúng kiểu `T` | Nhánh `if` | Pattern variable có giá trị đúng |
| Đối tượng thuộc subtype của `T` | Nhánh `if` | Không thu hẹp điều kiện |
| Đối tượng sai kiểu | Nhánh `else` hoặc bỏ qua `if` | Không cast nhầm |
| `null` | Nhánh không khớp | `instanceof` không khớp `null` |
| Giá trị đặc biệt hợp lệ, ví dụ chuỗi rỗng | Nhánh theo kiểu, rồi điều kiện nghiệp vụ | Không đổi nghĩa điều kiện thứ cấp |
| Biểu thức nguồn có tác dụng phụ | So sánh số lần gọi trước/sau | Phát hiện thay đổi không chủ đích |

Trong code review, một phép đối chiếu cụ thể thường đủ để hiểu thay đổi:

```diff
-if (value instanceof Account) {
-    Account account = (Account) value;
+if (value instanceof Account account) {
     send(account);
 }
```

`Account` và `send(...)` ở đây là **tên minh họa** cho class và phương thức của dự án thực tế. Với trường hợp này, nếu `value` là cùng một biểu thức không có tác dụng phụ và nhánh còn lại giữ nguyên, logic xử lý đối tượng `Account` không thay đổi.

## 13. Checklist áp dụng

Trước khi hoàn thành refactor, kiểm tra lần lượt:

- Kiểu sau `instanceof` có **giống hệt** kiểu kiểm tra trước đó không?
- Biến cast có được thay bằng một pattern variable rõ nghĩa, đúng phạm vi không?
- Logic xử lý trong nhánh, `else` và các `return`/`throw` có được giữ nguyên không?
- `null`, subtype và dữ liệu sai kiểu có đi đúng đường như trước không?
- Có expression nào bị gọi **ít/nhiều lần khác trước** không?
- Nếu có `&&`, `||` hoặc phép phủ định, compiler có chứng minh biến đã match ở vị trí sử dụng không?
- Nếu code chạy trên Java 17, có tránh dùng record pattern chỉ có từ Java 21 không?

**Ghi nhớ:** với một nhánh kiểm tra kiểu cổ điển, phép chuyển cốt lõi là **`if (x instanceof T) { T t = (T) x; ... }` → `if (x instanceof T t) { ... }`**. Sức mạnh của pattern matching nằm ở việc để compiler ràng buộc biến theo kết quả kiểm tra kiểu, còn sự an toàn của refactor phụ thuộc vào việc giữ nguyên đường đi điều khiển và hành vi của biểu thức nguồn.

## Tham khảo

- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof-operator.html)
- [Java Language Specification 21 — §15.20.2 Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Java Language Specification 21 — §6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
