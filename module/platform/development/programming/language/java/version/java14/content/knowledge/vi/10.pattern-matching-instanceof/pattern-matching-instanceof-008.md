# Tái cấu trúc kiểm tra kiểu lặp lại bằng pattern matching cho `instanceof` (Java 16+)

## 1. Vấn đề: kiểm tra kiểu xong lại ép kiểu

Khi một biến có kiểu tổng quát như `Object`, interface hoặc lớp cha, mã Java thường phải kiểm tra kiểu thực của đối tượng rồi mới dùng những phương thức riêng của kiểu con. Cách viết truyền thống:

```java
// Đoạn minh họa đặt trong phương thức có tham số Object input.
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip());
}
```

Mã trên **vẫn hợp lệ trong Java hiện đại**, nhưng tên kiểu `String` xuất hiện hai lần và tác giả phải tự viết phép ép kiểu `(String)`. Nếu lặp cho nhiều trường hợp (`String`, `List`, `Number`, các lớp domain), mã trở nên dài, dễ sao chép nhầm tên kiểu hoặc nhầm biến và khó theo dõi đường đi của từng nhánh.

**Pattern matching cho `instanceof`** gộp **kiểm tra kiểu + khai báo biến đã kiểm tra kiểu** vào một biểu thức:

```java
// Đoạn minh họa đặt trong phương thức có tham số Object input.
if (input instanceof String text) {
    System.out.println(text.strip());
}
```

Ở đây `String text` là một **type pattern**, còn `text` là **pattern variable**. Khi `input` thực sự là `String`, điều kiện đúng và `text` dùng được với kiểu `String` tại những vị trí mà trình biên dịch biết chắc phép khớp thành công. Không cần viết ép kiểu riêng.

**Mốc phiên bản cần nhớ:** Tính năng này xuất hiện ở dạng preview trong **Java 14** (JEP 305), có lần preview thứ hai ở **Java 15** (JEP 375), và trở thành tính năng **chính thức từ Java 16** (JEP 394). Từ Java 16 trở đi, cú pháp `instanceof String text` được hỗ trợ **không cần `--enable-preview`**. Bài này sử dụng quy tắc Java hiện hành và ví dụ biên dịch bằng Java 17, không hướng dẫn cách bật preview đã qua.

## 2. Công thức refactor cho một lần kiểm tra kiểu

Quy tắc cơ bản:

| Trước refactor: kiểm tra rồi cast | Sau refactor: type pattern |
| --- | --- |
| `if (obj instanceof T) { T value = (T) obj; ... }` | `if (obj instanceof T value) { ... }` |
| `if (!(obj instanceof T)) return; T value = (T) obj; ...` | `if (!(obj instanceof T value)) return; ...` |
| `obj instanceof T && ((T) obj).check()` | `obj instanceof T value && value.check()` |

`T` ở bảng là **ký hiệu kiểu tham chiếu hợp lệ** như `String` hoặc `SomeInterface`; `value` là tên biến mới. Khi refactor thực tế, cần bảo toàn **thứ tự điều kiện, số lần đánh giá biểu thức, giá trị trả về, các tác dụng phụ và trường hợp `null`**.

### Trước và sau: một kiểu dữ liệu

**Trước:**

```java
static int trimmedLength(Object candidate) {
    if (candidate instanceof String) {
        String text = (String) candidate;
        return text.strip().length();
    }
    return 0;
}
```

**Sau:**

```java
static int trimmedLength(Object candidate) {
    if (candidate instanceof String text) {
        return text.strip().length();
    }
    return 0;
}
```

Hai phương thức trên là **hai phiên bản thay thế** có cùng tên, không đặt cùng lúc trong một class. Cả hai kiểm tra `candidate` trước khi dùng API của `String`. Phiên bản sau giảm dòng khai báo và ép kiểu, nhưng không thay đổi hành vi với chuỗi hợp lệ, đối tượng thuộc kiểu khác hay `null`.

### Khi một giá trị được dùng nhiều lần trong cùng nhánh

```java
if (input instanceof String text) {
    String normalized = text.strip();
    if (!normalized.isEmpty()) {
        System.out.println(normalized.toUpperCase(java.util.Locale.ROOT));
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Dùng `text` nhiều lần trong nhánh là hợp lệ vì nhánh được thực thi khi pattern khớp. Nếu muốn tách `strip()` ra một lần để tránh tính lại, vẫn làm được qua biến cục bộ `normalized`.

## 3. Ví dụ Java 17 hoàn chỉnh: kiểm tra tính tương đương trước/sau

Tệp **`InstanceofRefactorDemo.java`** dưới đây gồm hai phương thức `before` và `after` có cùng mục đích. Cả hai xử lý đầu vào thuộc `String`, `List<?>`, `Number` và trường hợp còn lại. Phương thức `main` tự so sánh kết quả cho nhiều dữ liệu để phát hiện nếu refactor làm đổi hành vi.

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class InstanceofRefactorDemo {
    static String before(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            if (text.isBlank()) {
                return "EMPTY_STRING";
            }
            return "TEXT:" + text.strip();
        }
        if (input instanceof List<?>) {
            List<?> entries = (List<?>) input;
            return "LIST:" + entries.size();
        }
        if (input instanceof Number) {
            Number number = (Number) input;
            return "NUMBER:" + number.intValue();
        }
        return "OTHER";
    }

    static String after(Object input) {
        if (input instanceof String text) {
            if (text.isBlank()) {
                return "EMPTY_STRING";
            }
            return "TEXT:" + text.strip();
        }
        if (input instanceof List<?> entries) {
            return "LIST:" + entries.size();
        }
        if (input instanceof Number number) {
            return "NUMBER:" + number.intValue();
        }
        return "OTHER";
    }

    static String normalize(Object input) {
        if (!(input instanceof String text)) {
            return "INVALID_TYPE";
        }
        if (text.isBlank()) {
            return "EMPTY";
        }
        return "OK:" + text.strip().toUpperCase(Locale.ROOT);
    }

    static boolean containsJava(Object input) {
        return input instanceof String text
                && text.toLowerCase(Locale.ROOT).contains("java");
    }

    public static void main(String[] args) {
        Object[] inputs = {
            " Java 17 ", List.of("A", "B"), Integer.valueOf(8), null, "   "
        };
        for (Object input : inputs) {
            String oldOutput = before(input);
            String newOutput = after(input);
            if (!Objects.equals(oldOutput, newOutput)) {
                throw new AssertionError(
                    "Refactor changed behavior for " + input);
            }
            System.out.println(newOutput);
        }
        System.out.println(normalize("  ready  "));
        System.out.println(normalize(42));
        System.out.println(containsJava("Pattern in JAVA"));
        Object missing = null;
        System.out.println(missing instanceof String);
    }
}
```

**Lệnh biên dịch và chạy** với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 InstanceofRefactorDemo.java
java InstanceofRefactorDemo
```

Mã chỉ sử dụng các tính năng **chính thức của Java 17 hoặc trước đó**. Không cần preview flag.

**Kết quả đầu ra chính xác:**

```text
TEXT:Java 17
LIST:2
NUMBER:8
OTHER
EMPTY_STRING
OK:READY
INVALID_TYPE
true
false
```

### Vì sao test này có giá trị?

1. Vòng lặp chạy cả `before(input)` và `after(input)` với **cùng dữ liệu**, so sánh chuỗi đầu ra bằng `Objects.equals`; nếu có sự khác biệt, chương trình ném `AssertionError` thay vì âm thầm in kết quả.
2. `" Java 17 "` khớp `String text`, không rỗng, sau `strip()` thành `Java 17`.
3. `List.of("A", "B")` khớp `List<?> entries`, nên trả `LIST:2`. Đây là một kiểm tra kiểu collection có thể sử dụng ở runtime mà **không giả định kiểu của phần tử**.
4. `Integer.valueOf(8)` đồng thời là `Number`, nên nhánh `Number number` trả `NUMBER:8`.
5. `null` không khớp một type pattern `instanceof`, nên trả `OTHER`; dòng cuối `missing instanceof String` cho `false`.
6. Chuỗi chỉ gồm khoảng trắng vẫn là `String` nhưng `text.isBlank()` đúng, nên trả `EMPTY_STRING`.
7. `normalize` dùng **guard clause**: nếu không phải `String` thì return ngay; từ dòng tiếp theo, `text` có kiểu `String` và có thể dùng mà không cast.
8. `containsJava` minh họa **`&&` short-circuit**: lời gọi `text.toLowerCase(...)` chỉ chạy khi `instanceof String text` thành công. Giá trị chứa `JAVA` được chuyển sang chữ thường, nên hàm trả `true`.

**Giới hạn kiểm thử:** Với ví dụ chỉ gồm các phép kiểm tra không có tác dụng phụ, so sánh đầu ra là một phép kiểm tra hồi quy trực tiếp. Trong code production, còn cần kiểm tra ngoại lệ, các lệnh ghi log, thay đổi state, gọi mạng/database và thứ tự đánh giá trước/sau. Không được kết luận mọi refactor đều an toàn chỉ vì một số test điển hình đạt.

## 4. Phạm vi (*flow scoping*) của pattern variable

Biến mẫu **không** hoạt động giống một biến được khai báo ở đầu phương thức. Trình biên dịch chỉ cho dùng tên khi đường điều khiển đi đến đó chứng minh pattern đã khớp (*definitely matched*).

### 4.1. Bên trong nhánh khớp kiểu

```java
// Minh họa, trong phương thức có Object input.
if (input instanceof String text) {
    System.out.println(text.length()); // Đúng.
} else {
    // text không nằm trong scope ở đây.
}
// text cũng không mặc nhiên nằm trong scope ở đây.
```

Ở nhánh `else`, điều kiện `instanceof` là sai nên không có cơ sở để dùng `text`. Việc đặt biến mẫu trong một nhánh không có nghĩa là tên đó tồn tại ở tất cả các nhánh khác.

### 4.2. Ghép với `&&` là an toàn khi giữ thứ tự

```java
static boolean hasEnoughChars(Object value) {
    return value instanceof String text && text.strip().length() >= 5;
}
```

Đây là phương thức độc lập về cú pháp để đặt trong class. `&&` đánh giá vế phải **chỉ khi** vế trái là `true`. Vì vậy, tại vế phải `text` đã khớp kiểu `String` và có thể được truy cập.

So sánh:

```java
// KHÔNG BIÊN DỊCH: text chưa chắc được khởi tạo trên vế phải.
// if (value instanceof String text || text.isBlank()) { ... }
```

Với `||`, vế phải có thể chạy **khi vế trái sai**: lúc ấy `value` có thể không phải `String`, nên `text` không ở trong scope. Không đổi máy móc `&&` thành `||` khi biến mẫu xuất hiện ở vế phải.

**Trường hợp phủ định cần phân biệt:** biểu thức `!(value instanceof String text) || text.isBlank()` là một cấu trúc hợp lệ trong điều kiện phù hợp, vì vế phải của `||` chỉ được chạy khi phủ định là sai, tức là `instanceof` đã khớp. Tuy nhiên, cấu trúc này dễ khó đọc; guard clause thường diễn đạt ý định rõ hơn.

### 4.3. Guard clause và phủ định

```java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.strip(); // Hợp lệ sau nhánh return.
}
```

Nhờ nhánh `if` đã `return` ở trường hợp không khớp, mọi đường đi đến `return text.strip()` đều bảo đảm giá trị là `String`. Pattern variable được dùng **sau** câu lệnh `if`, dù nó không nằm trong block `if`.

Nếu nhánh không khớp vẫn có thể **đi tiếp bình thường** (không `return`/`throw`), thì không được giả định biến mẫu sẽ ở scope sau `if`.

### 4.4. Tên biến mẫu ở những nhánh loại trừ nhau

```java
// Đoạn minh họa trong một phương thức nhận Object value.
if (value instanceof String item) {
    System.out.println(item.length());
} else if (value instanceof Number item) {
    System.out.println(item.intValue());
}
```

Tên `item` có thể được sử dụng lại vì các biến mẫu nằm trong những vùng flow scope riêng và không xung đột. Dù được phép, trong code nghiệp vụ nên chọn tên mô tả như `text` và `number` khi điều đó giúp người đọc không nhầm kiểu.

## 5. Tái cấu trúc chuỗi `if / else if` với nhiều loại dữ liệu

Một dạng lặp thường gặp là:

```java
// Minh họa trước refactor.
if (event instanceof Payment) {
    Payment payment = (Payment) event;
    handlePayment(payment);
} else if (event instanceof Refund) {
    Refund refund = (Refund) event;
    handleRefund(refund);
} else {
    handleUnknown(event);
}
```

Dạng pattern tương ứng:

```java
// Minh họa sau refactor, giữ nguyên thứ tự nhánh.
if (event instanceof Payment payment) {
    handlePayment(payment);
} else if (event instanceof Refund refund) {
    handleRefund(refund);
} else {
    handleUnknown(event);
}
```

`Payment`, `Refund` và các phương thức `handle...` ở đây đại diện cho kiểu/hàm của ứng dụng, **không phải tệp Java độc lập**. Ý tưởng là thay thế **đúng những cặp kiểm tra + cast** bằng một type pattern, không tự ý đổi logic nghiệp vụ.

### Thứ tự nhánh có thể làm thay đổi hành vi

Nếu các kiểu có quan hệ kế thừa, một object có thể khớp nhiều kiểm tra. Ví dụ `Integer` cũng là `Number`:

```java
// Object input chứa Integer(8).
if (input instanceof Number number) {
    System.out.println("number");
} else if (input instanceof Integer integer) {
    System.out.println("integer");
}
```

Nhánh đầu tiên đã khớp `Integer`, nên nhánh sau không chạy. Nếu **đổi thứ tự** để `Integer` đứng trước `Number`, hành vi thay đổi: input đó sẽ vào nhánh chuyên biệt. Việc refactor loại bỏ cast **không tự quyết định lại thứ tự**; chỉ thay thứ tự khi đã có yêu cầu nghiệp vụ và test tương ứng.

Với nhiều kiểu có thể tương quan, nếu mô hình cho phép, cân nhắc **polymorphism** (gọi phương thức interface thay vì liên tục hỏi kiểu). Nhưng việc chuyển sang polymorphism là thay đổi thiết kế lớn hơn, không đồng nhất với phép rút gọn cú pháp `instanceof`.

## 6. Rủi ro refactor biểu thức được đánh giá nhiều lần

Không chỉ nhìn xem `instanceof` có đúng kiểu hay không, mà còn cần xem **đối tượng được kiểm tra đến từ đâu**.

Ví dụ:

```java
// Minh họa: không nên tự ý gọi hàm sinh dữ liệu nhiều lần.
if (readNext() instanceof String) {
    String result = (String) readNext();
    consume(result);
}
```

Nếu `readNext()` đọc một phần tử từ queue, hai lần gọi có thể trả **hai đối tượng khác nhau** hoặc gây tác dụng phụ. Mã này đã tiềm ẩn lỗi vì kiểm tra một giá trị nhưng ép kiểu **giá trị khác**. Có thể viết lại thành:

```java
// Minh họa: readNext() được gọi đúng một lần.
Object candidate = readNext();
if (candidate instanceof String result) {
    consume(result);
}
```

Đây là một **thay đổi có chủ ý về số lần gọi**. Không được tuyên bố hai đoạn luôn tương đương nếu `readNext()` có side effect; cần kiểm thử hành vi mong muốn trước và sau, nhất là khi xử lý stream, I/O, generator hay queue.

Tương tự, khi biểu thức phức tạp chứa `getter()`, phép tính tốn kém hoặc truy cập trạng thái có thể thay đổi, hãy quyết định rõ nên đánh giá một lần rồi lưu vào biến. **Pattern matching không tự bảo đảm giá trị nguồn ổn định giữa các lần gọi một method khác nhau.**

## 7. Những ràng buộc cú pháp quan trọng

### 7.1. `instanceof` pattern cần kiểu tham chiếu kiểm tra hợp lệ

`instanceof String text` áp dụng kiểm tra kiểu tham chiếu; không có cú pháp `instanceof int n` để kiểm tra primitive `int`. Nếu giá trị được boxing dưới dạng `Object`, có thể khớp wrapper như `Integer`:

```java
Object candidate = Integer.valueOf(10);
if (candidate instanceof Integer number) {
    System.out.println(number.intValue()); // 10
}
```

### 7.2. Không dùng type pattern vốn đã chắc chắn đúng theo kiểu khai báo

Java 16+ không cho một phép kiểm tra type pattern `instanceof` khi kiểu tĩnh của biểu thức đã là subtype của kiểu pattern, ví dụ:

```java
String message = "hello";
// KHÔNG BIÊN DỊCH trên Java 16+:
// if (message instanceof String text) { ... }
```

`message` vốn đã có kiểu `String` nên không cần kiểm tra để làm hẹp kiểu. Hãy dùng trực tiếp `message`, hoặc giữ kiểu tĩnh rộng hơn (`Object`/interface) khi tình huống thực sự cần rẽ nhánh theo kiểu runtime. Đừng thêm `instanceof` chỉ để tạo tên biến thứ hai.

### 7.3. Generic type phải kiểm tra được tại runtime

```java
// Hợp lệ với Object candidate:
if (candidate instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
```

`List<?>` là dạng có thể dùng cho kiểm tra runtime ở đây. Nhưng kiểm tra `candidate instanceof List<String> elements` **không hợp lệ** vì JVM không phân biệt các đối số generic như `String` sau type erasure cho kiểu `Object` này.

Nếu cần xác nhận mọi phần tử là `String`, thực hiện kiểm tra riêng sau khi đã có `List<?>`:

```java
// Đoạn minh họa đặt trong nhánh có List<?> elements.
boolean allStrings = elements.stream()
        .allMatch(value -> value instanceof String);
```

Dòng này trả `true` cho danh sách rỗng vì không có phần tử phản ví dụ, và trả `false` nếu có phần tử `null`. Nó chỉ xác minh điều kiện các phần tử tại thời điểm kiểm tra, không tự đổi kiểu tĩnh của danh sách thành `List<String>` hay bảo đảm collection mutable không đổi sau đó.

### 7.4. Khác với ép kiểu không điều kiện

`(String) candidate` có thể ném `ClassCastException` nếu candidate không phải String (và cho phép cast `null`). Ngược lại, `candidate instanceof String text` **trả `false` nếu candidate không khớp hoặc là `null`**, và không thực thi phần code chỉ dành cho String.

Vì vậy, **không thay mọi phép ép kiểu bằng một pattern chỉ vì muốn loại cast**. Nếu code cũ *chủ đích* ném exception khi kiểu sai thì thêm nhánh fallback để giữ hợp đồng:

```java
static String requireString(Object value) {
    if (value instanceof String text) {
        return text;
    }
    throw new IllegalArgumentException("Expected String");
}
```

Đoạn này chủ đích ném `IllegalArgumentException`, **khác loại ngoại lệ** với cast thất bại bằng `ClassCastException`. Nếu hợp đồng API cũ yêu cầu đúng loại ngoại lệ/thông điệp, phải cân nhắc và kiểm thử chứ không mặc nhiên coi chúng tương đương.

### 7.5. Pattern `instanceof` không đồng nghĩa pattern của `switch`

Bài này dùng `instanceof T variable` với `if` hoặc biểu thức Boolean. Pattern matching cho `switch` là tính năng riêng đã được chính thức hóa ở **Java 21**; nó có cú pháp, quy tắc dominance/exhaustiveness và handling `null` khác, không tự thay thế mọi chuỗi `if`. Khi chỉ muốn bỏ phép cast lặp, sử dụng `instanceof` vẫn là lựa chọn đơn giản và hiện hành.

## 8. Checklist refactor theo từng bước

1. **Tìm cặp trùng lặp:** `if (expr instanceof T)` rồi `T value = (T) expr`, hoặc nhiều chỗ cast `(T) expr` trong cùng nhánh.
2. **Kiểm tra tính ổn định của `expr`:** nên là biến đang giữ object; nếu có method call/side effect, cân nhắc lưu `Object candidate = expr` một lần rồi refactor.
3. **Chọn type pattern:** đổi thành `if (candidate instanceof T value)`, giữ tên biến rõ nghĩa và không trùng local đang nằm trong scope.
4. **Bỏ cast thừa:** thay các lần dùng `(T) candidate` bằng `value` trong vùng flow scope hợp lệ.
5. **Giữ thứ tự nhánh:** đặc biệt khi các lớp có quan hệ cha/con như `Integer` và `Number`.
6. **Kiểm tra Boolean và return:** với `&&`, biến mẫu có thể dùng ở vế phải; với `||` thông thường không được sử dụng kiểu `x instanceof T t || t...`. Nếu dùng guard phủ định, nhánh lỗi phải kết thúc đường đi khi muốn dùng tên sau `if`.
7. **Kiểm tra generic:** dùng kiểm tra runtime hợp lệ như `List<?>`, không thêm type argument không kiểm chứng như `List<String>` vào pattern.
8. **Bảo toàn hợp đồng lỗi:** đầu vào `null`, kiểu sai, exception, thông điệp lỗi, tác dụng phụ và thứ tự gọi các method.
9. **Kiểm thử trước/sau:** unit test với type đúng, type con, type khác, `null`, giá trị rỗng, nhiều nhánh có thể khớp và điều kiện phụ; đối chiếu kết quả và side effects.
10. **Đánh giá độ dễ đọc:** nếu rút gọn khiến logic nhánh phức tạp hơn, tách phương thức hoặc chọn mô hình đa hình phù hợp thay vì ép một câu điều kiện thật dài.

### Bảng lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Viết `instanceof String text` nhưng vẫn cast `(String) input` trong cùng nhánh | Dư thừa, chưa đạt mục tiêu refactor | Dùng `text` |
| Dùng biến mẫu trong `else` nơi không khớp kiểu | Lỗi scope/biên dịch | Chỉ dùng nơi chắc chắn match |
| Viết `obj instanceof String text || text.isBlank()` | Lỗi biên dịch | Dùng `&&` khi vế phải chỉ được chạy sau match, hoặc đổi logic phủ định/guard |
| Chuyển `if` sang pattern và đổi thứ tự nhánh subtype/supertype | Kết quả xử lý có thể đổi | Bảo toàn thứ tự hoặc thay đổi có test |
| Kiểm tra `List<String>` từ `Object` trong pattern | Generic type không kiểm tra được ở runtime | Dùng `List<?>` và validate phần tử riêng |
| Thêm pattern trên biến đã có kiểu `String` | Pattern check vô điều kiện đúng, lỗi compile từ Java 16 | Dùng biến trực tiếp |
| Cho rằng `null` sẽ đi vào nhánh pattern | `null instanceof T` là false | Thêm nhánh xử lý `null` khi cần |
| Giả định pattern check luôn tương đương cast đơn thuần | Cast sai kiểu ném lỗi; pattern không match | Giữ hợp đồng lỗi và test |
| Kiểm tra một lời gọi method rồi cast kết quả của lời gọi khác | Khác instance/side effect | Lưu kết quả một lần và chủ đích xử lý thay đổi |
| Chỉ test happy path | Sai behavior với kiểu lạ/null/blank | Test thêm các nhánh và hồi quy |

## 9. Bài tập tự kiểm tra

**Bài 1.** Rút gọn hai dòng:

```java
if (source instanceof java.util.Map<?, ?>) {
    java.util.Map<?, ?> map = (java.util.Map<?, ?>) source;
    System.out.println(map.size());
}
```

**Đáp án:**

```java
if (source instanceof java.util.Map<?, ?> map) {
    System.out.println(map.size());
}
```

**Bài 2.** Vì sao `input instanceof String s && s.length() > 4` hợp lệ, nhưng `input instanceof String s || s.length() > 4` không hợp lệ?

Đáp án: `&&` chỉ cho vế phải chạy khi pattern đã match; `||` có thể cho vế phải chạy sau khi pattern thất bại, nên biến `s` chưa chắc tồn tại trong flow scope.

**Bài 3.** Chuyển đoạn sau thành guard clause để không phải cast:

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String)) {
        return 0;
    }
    String value = (String) input;
    return value.length();
}
```

**Đáp án:**

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String value)) {
        return 0;
    }
    return value.length();
}
```

**Bài 4.** Mã cũ gọi `fetch()` hai lần (một lần khi kiểm tra `instanceof`, một lần khi cast), mã mới gọi một lần. Có chắc refactor không thay đổi hành vi?

Đáp án: **Không.** Nếu `fetch()` đọc queue, tạo giá trị khác mỗi lần hoặc có side effect, số lần gọi thay đổi là thay đổi hành vi. Cần xác định yêu cầu, kiểm thử và ghi nhận đây là bản sửa chủ đích.

**Bài 5.** Pattern có “ép” `null` thành `String` không?

Đáp án: **Không.** `null` không khớp `instanceof String s`; nhánh đó không chạy. Nếu cần xử lý `null` riêng, kiểm tra trước hoặc dành một nhánh fallback phù hợp.

## 10. Tài liệu chính thức

- [OpenJDK — JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394): cơ chế type pattern, flow scoping, tính năng được chính thức hóa từ Java 16.
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): ví dụ before/after, `&&`, `||`, phủ định và phạm vi biến mẫu.
- [Oracle — Java Language Changes (Java 16)](https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html): xác nhận tính năng `instanceof` pattern là chính thức từ Java 16.
- [Java Language Specification — `instanceof`, `15.20.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2): định nghĩa ngôn ngữ đang áp dụng của toán tử `instanceof`.

**Ghi nhớ:** Khi một đoạn mã *kiểm tra kiểu rồi lặp lại phép cast cùng giá trị*, `instanceof T variable` giúp diễn đạt trực tiếp ý định và giảm rủi ro sao chép sai. Refactor tốt phải bảo toàn đường điều khiển, phạm vi biến, thứ tự kiểm tra, hành vi với `null`, exception và side effects — không chỉ là xóa bớt vài dòng mã.
