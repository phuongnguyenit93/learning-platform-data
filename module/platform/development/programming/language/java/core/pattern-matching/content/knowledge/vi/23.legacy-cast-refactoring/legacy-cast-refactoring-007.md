# Bảo toàn behavior khi thay cú pháp: refactor legacy cast sang Java Pattern Matching

## 1. Mục tiêu của refactor: đổi cách viết, không đổi cách chương trình hoạt động

Một đoạn Java cũ thường kiểm tra kiểu bằng `instanceof` rồi ép kiểu (*cast*) để dùng thành viên của kiểu con:

```java
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip());
}
```

Từ **Java 16 (JEP 394)**, *pattern matching for instanceof* là tính năng chính thức. Có thể viết:

```java
if (input instanceof String text) {
    System.out.println(text.strip());
}
```

Cả hai đoạn đều kiểm tra liệu `input` có phải một instance phù hợp với `String` hay không; nếu có, đoạn trong nhánh dùng biến kiểu `String`. Việc loại bỏ dòng cast dư thừa làm mã ngắn và dễ đọc hơn.

Tuy nhiên, yêu cầu của một **behavior-preserving refactor** không chỉ là “biên dịch được” hay “test với một đối tượng chuỗi cho cùng kết quả”. Ta cần duy trì những gì mã cũ đã cam kết hoặc quan sát được:

- Nhánh nào được chọn cho cùng một đầu vào, kể cả `null` và các kiểu con.
- Giá trị trả về, dữ liệu bị thay đổi và đối tượng được truyền đến các phương thức khác.
- Thứ tự, số lần gọi các hàm có side effect (truy xuất dữ liệu, tăng bộ đếm, log, ghi CSDL, phát sự kiện).
- Việc ném ngoại lệ, loại ngoại lệ và thời điểm lỗi xảy ra khi đây là một phần của hợp đồng quan sát được.
- Thứ tự đánh giá các điều kiện, cơ chế dừng sớm và phạm vi biến.
- Ngữ nghĩa do kiểu tĩnh quyết định: overload resolution, generic type và khả năng kiểm tra tại compile time.

**Nguyên tắc:** chỉ thay cú pháp kiểm tra và cast khi có đủ cơ sở chứng minh **cùng một giá trị được kiểm tra, cùng nhánh được thực thi và phần thân vẫn làm cùng việc**. Nếu muốn sửa một bug lịch sử cùng lúc, hãy tách thành thay đổi hành vi có chủ đích và kiểm thử riêng.

## 2. Phép biến đổi cơ bản và các giả định cần giữ

### Trước: kiểm tra kiểu rồi cast đúng cùng một biến

```java
static String legacy(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.strip();
    }
    return "not a string";
}
```

### Sau: type pattern ràng buộc trực tiếp biến đã kiểm tra

```java
static String modern(Object input) {
    if (input instanceof String text) {
        return text.strip();
    }
    return "not a string";
}
```

Hai phương thức trên có cùng hành vi với các giá trị đầu vào thông thường:

| Đầu vào | Trước | Sau | Vì sao |
| --- | --- | --- | --- |
| `" Java "` | `"Java"` | `"Java"` | `instanceof String` khớp, dùng cùng chuỗi |
| `""` | `""` | `""` | Cùng thao tác `strip()` |
| `Integer.valueOf(7)` | `"not a string"` | `"not a string"` | Không khớp `String` |
| `null` | `"not a string"` | `"not a string"` | `null instanceof String` là `false` |

Với cú pháp `input instanceof String text`, tên `text` chỉ được sử dụng ở nơi compiler có thể xác định pattern khớp. Điều kiện `instanceof` không ép kiểu mù rồi hi vọng phép cast thành công; nó thực hiện kiểm tra kiểu và tạo biến khi phù hợp.

Điều kiện tiên quyết của phép thay đơn giản:

1. `input` là **cùng một biểu thức/giá trị** ở bước kiểm tra và bước cast.
2. Không có thao tác nào thay thế giá trị của `input` giữa hai bước.
3. Cast loại bỏ có cùng kiểu mục tiêu với pattern, ví dụ cùng là `String`.
4. Những câu lệnh còn lại, thứ tự của chúng và cấu trúc `else` không bị đổi.
5. Không có phụ thuộc vào khai báo biến cùng tên trong một phạm vi gây xung đột hoặc đổi overload.

Nếu một điều kiện không đúng, cần phân tích hành vi riêng thay vì áp dụng thay thế bằng tìm-và-thay hàng loạt.

## 3. Chương trình đầy đủ: refactor đúng và phản ví dụ thay đổi behavior

Lưu chương trình dưới đây vào **`BehaviorPreservingPatternsDemo.java`**. Toàn bộ mã dùng cú pháp **Java 17**, không cần preview; các kết quả được kiểm tra với chế độ biên dịch Java 17.

```java
import java.util.Locale;

public class BehaviorPreservingPatternsDemo {
    // Phiên bản truyền thống: instanceof + cast.
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return text.isBlank() ? "text:blank" : "text:" + text.strip();
        }
        if (input instanceof Number) {
            Number number = (Number) input;
            return "number:" + number.intValue();
        }
        return "other";
    }

    // Giữ nguyên thứ tự nhánh, thao tác và giá trị kết quả.
    static String modern(Object input) {
        if (input instanceof String text) {
            return text.isBlank() ? "text:blank" : "text:" + text.strip();
        }
        if (input instanceof Number number) {
            return "number:" + number.intValue();
        }
        return "other";
    }

    // Legacy guard: nhánh sai trả về sớm.
    static String legacyGuard(Object value) {
        if (!(value instanceof String)) return "not-string";
        String text = (String) value;
        if (text.isBlank()) return "empty";
        return "upper:" + text.toUpperCase(Locale.ROOT);
    }

    // Flow scoping: text vẫn dùng được sau nhánh return.
    static String modernGuard(Object value) {
        if (!(value instanceof String text)) return "not-string";
        if (text.isBlank()) return "empty";
        return "upper:" + text.toUpperCase(Locale.ROOT);
    }

    // Nguồn có side effect: lần đọc thứ nhất và thứ hai trả khác kiểu.
    static int reads;
    static Object changingRead() {
        reads++;
        return reads == 1 ? "ok" : Integer.valueOf(9);
    }

    // Legacy thực sự gọi changingRead() hai lần.
    static String duplicateRead() {
        if (changingRead() instanceof String) {
            String text = (String) changingRead();
            return text;
        }
        return "not-text";
    }

    // Bản đổi cú pháp gọi changingRead() chỉ một lần!
    static String singleRead() {
        if (changingRead() instanceof String text) return text;
        return "not-text";
    }

    // Cast không được kiểm tra trước khác với instanceof pattern.
    static void demonstrateCast(Object input) {
        try {
            String text = (String) input;
            System.out.println("direct-cast:" + (text == null ? "null" : text));
        } catch (ClassCastException ex) {
            System.out.println("direct-cast:ClassCastException");
        }

        if (input instanceof String text) {
            System.out.println("pattern:" + text);
        } else {
            System.out.println("pattern:non-string");
        }
    }

    public static void main(String[] args) {
        Object[] samples = { " Java ", "", 17, 3.9, null, new Object() };
        for (Object value : samples) {
            String before = legacy(value);
            String after = modern(value);
            System.out.println("same=" + before.equals(after) + " -> " + after);
        }

        System.out.println("guards=" +
                legacyGuard("ok").equals(modernGuard("ok")) +
                " -> " + modernGuard("ok"));
        System.out.println("guards=" +
                legacyGuard("").equals(modernGuard("")) +
                " -> " + modernGuard(""));
        System.out.println("guards=" +
                legacyGuard(null).equals(modernGuard(null)) +
                " -> " + modernGuard(null));

        reads = 0;
        try {
            System.out.println(duplicateRead());
        } catch (ClassCastException ex) {
            System.out.println("legacy-duplicate:ClassCastException reads=" + reads);
        }

        reads = 0;
        System.out.println("pattern-single:" + singleRead() + " reads=" + reads);

        demonstrateCast(5);
        demonstrateCast(null);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 BehaviorPreservingPatternsDemo.java
java BehaviorPreservingPatternsDemo
```

**Đầu ra chính xác:**

```text
same=true -> text:Java
same=true -> text:blank
same=true -> number:17
same=true -> number:3
same=true -> other
same=true -> other
guards=true -> upper:OK
guards=true -> empty
guards=true -> not-string
legacy-duplicate:ClassCastException reads=2
pattern-single:ok reads=1
direct-cast:ClassCastException
pattern:non-string
direct-cast:null
pattern:non-string
```

### Ý nghĩa của từng nhóm kết quả

- Sáu dòng `same=true` thể hiện hai hàm `legacy` và `modern` giữ giá trị kết quả cho chuỗi, chuỗi rỗng, số nguyên, số thực, `null` và đối tượng khác. Với `Double.valueOf(3.9)`, cả hai đều dùng `intValue()` nên ra `3`.
- Ba dòng `guards=true` cho thấy dạng `if (!(value instanceof String text)) return ...;` giữ logic của phép kiểm tra phủ định kết hợp thoát sớm.
- `legacy-duplicate:ClassCastException reads=2` nhưng `pattern-single:ok reads=1` là **phản ví dụ**: chỉ đổi cú pháp đã thay số lần gọi hàm và kết quả ngoại lệ. Không được tuyên bố hai phiên bản tương đương.
- Hai cặp dòng cuối phân biệt **direct cast** với **instanceof pattern**. Với số nguyên, cast sang `String` ném `ClassCastException`; pattern không khớp. Với `null`, cast tham chiếu sang `String` tạo giá trị `null`, còn pattern không khớp.

Ví dụ này cố ý tách rõ **phép thay đúng điều kiện** và **những trường hợp đổi semantics** thay vì biến tất cả thành một “trước/sau” được mặc định là tương đương.

## 4. Bẫy lớn nhất: số lần đánh giá biểu thức và side effects

Cẩn thận khi đối tượng được lấy qua lời gọi phương thức thay vì một biến cục bộ ổn định.

### Trước: biểu thức có thể được gọi hai lần

```java
if (repository.findNext() instanceof String) {
    String text = (String) repository.findNext();
    consume(text);
}
```

Giả sử `repository.findNext()` lấy rồi loại một phần tử khỏi hàng đợi. Lần gọi thứ nhất dùng để kiểm tra, lần gọi thứ hai lấy **một phần tử khác**. Nó có thể có kiểu khác; phần tử đầu tiên có thể đã bị tiêu thụ dù không được xử lý. Đây là hành vi mà mã cũ *thực sự thực hiện*, dù có thể là bug.

### Sau: type pattern chỉ đánh giá biểu thức kiểm tra một lần

```java
if (repository.findNext() instanceof String text) {
    consume(text);
}
```

Mã mới chỉ gọi `findNext()` một lần. Điều này có thể là **sửa lỗi tốt**, nhưng không phải refactor bảo toàn behavior: số lần lấy phần tử và kết quả ngoại lệ đã thay đổi.

### Cách xử lý đúng khi có nguồn dữ liệu biến đổi

Trước hết, xác định rõ **hợp đồng mong muốn**, sau đó tách truy xuất khỏi thao tác kiểm tra:

```java
Object candidate = repository.findNext();

if (candidate instanceof String) {
    String text = (String) candidate;
    consume(text);
}
```

Sau khi đã có căn cứ rằng việc truy xuất **một lần** là hành vi được mong muốn và phiên bản có biến `candidate` đã được chấp thuận/kiểm thử, mới áp dụng phép đổi cú pháp an toàn:

```java
Object candidate = repository.findNext();

if (candidate instanceof String text) {
    consume(text);
}
```

Hai khối sau cùng đều chỉ truy xuất `candidate` một lần và không thay đổi nó giữa kiểm tra/cast. **Đừng âm thầm coi việc chuyển từ hai lần truy xuất sang một lần là không đổi hành vi** nếu chưa xác nhận yêu cầu nghiệp vụ.

Áp dụng cùng quy tắc với `iterator.next()`, `queue.poll()`, `stream`/cursor, hàm đọc đồng hồ, random, hàm có bộ đếm, hàm lấy dữ liệu từ CSDL hoặc gọi service, và những accessor có thể thay đổi trạng thái.

## 5. Null, cast và exception: không thể thay thế tùy ý

### 5.1. `instanceof` và `instanceof pattern` đều không khớp `null`

```java
Object input = null;

System.out.println(input instanceof String); // false
```

Với `input == null`, cả:

```java
if (input instanceof String) { /* ... */ }
```

và:

```java
if (input instanceof String text) { /* ... */ }
```

đều không vào nhánh. Đây là điểm tương đương quan trọng khi thay đúng **cấu trúc guard + cast**.

### 5.2. Direct cast sang kiểu tham chiếu có hành vi khác

```java
Object input = null;
String text = (String) input; // Hợp lệ, text == null.
```

Nếu viết lại thành `if (input instanceof String text)`, khối sẽ **không chạy** với `null`. Còn:

```java
Object input = Integer.valueOf(9);
String text = (String) input; // ClassCastException.
```

thì ném ngoại lệ thay vì rẽ nhánh `else`. Vì vậy, refactor từ **cast trực tiếp** sang **kiểm tra kiểu + pattern** thay đổi hợp đồng xử lý dữ liệu sai kiểu; cần quyết định riêng, không xem là phép đổi cú pháp tương đương.

### 5.3. Ngoại lệ có thể nằm trong hợp đồng quan sát được

Với một API quy định đầu vào sai kiểu phải ném `ClassCastException`, thay bằng `return null` hoặc `"other"` sẽ làm caller nhận kết quả khác và có thể vô hiệu hóa cơ chế bắt lỗi hiện có. Ngược lại, có những nơi kiểm tra kiểu trước cast nhằm **tránh** ngoại lệ; khi đó pattern là lựa chọn tự nhiên.

Khi refactor, liệt kê cụ thể:
- Với giá trị không khớp kiểu, hàm ném lỗi, trả về giá trị dự phòng hay không làm gì?
- Với `null`, là đầu vào hợp lệ hay lỗi?
- Ngoại lệ xuất hiện **trước hay sau** log, gọi service hoặc cập nhật trạng thái?
- Có `catch` hoặc `finally` nào phụ thuộc kiểu ngoại lệ hay thứ tự side effect không?

## 6. Giữ nguyên thứ tự nhánh khi các kiểu có quan hệ kế thừa

`instanceof` kiểm tra quan hệ kiểu, không chỉ so khớp chính xác tên lớp. Vì `Integer` là `Number`, việc đổi thứ tự có thể khiến nhánh hẹp không bao giờ được chọn.

**Trước: nhánh `Integer` được ưu tiên.**

```java
static String classify(Object value) {
    if (value instanceof Integer) {
        Integer n = (Integer) value;
        return "integer:" + n;
    }
    if (value instanceof Number) {
        Number n = (Number) value;
        return "number:" + n;
    }
    return "other";
}
```

**Sau đúng: chỉ thay cast, giữ thứ tự.**

```java
static String classify(Object value) {
    if (value instanceof Integer n) {
        return "integer:" + n;
    }
    if (value instanceof Number n) {
        return "number:" + n;
    }
    return "other";
}
```

**Sau sai: chuyển `Number` lên trước `Integer`.**

```java
static String classify(Object value) {
    if (value instanceof Number n) {
        return "number:" + n; // Integer cũng đến đây.
    }
    if (value instanceof Integer n) {
        return "integer:" + n; // Không được chọn với Integer.
    }
    return "other";
}
```

Với đối tượng `Integer.valueOf(5)`, phiên bản đúng trả `integer:5`, phiên bản sai trả `number:5`. Cả hai có thể biên dịch, nhưng nghĩa đã đổi.

Nếu chuyển chuỗi `if` thành `switch` với type patterns (Java 21), còn phải xét quy tắc **dominated case**: nhánh rộng đặt trước nhánh hẹp có thể bị compiler báo lỗi. Đổi từ `if` sang `switch` là một bước thiết kế rộng hơn “xóa cast dư thừa” và nên được kiểm thử riêng.

## 7. Flow scoping: phạm vi biến pattern phải đi theo đường thực thi

Biến pattern không giống một biến đã được khai báo ở mọi nơi; Java chỉ cho sử dụng nó ở những vị trí mà compiler chứng minh phép kiểm tra kiểu đã thành công.

### 7.1. Bên trong nhánh `if`

```java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ.
}
// Không tùy ý dùng text ở đây nếu pattern có thể đã không khớp.
```

### 7.2. Dùng `&&` để kiểm tra sâu hơn

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

Vế phải của `&&` chỉ chạy nếu pattern ở vế trái đã thành công; do đó có thể dùng `text`.

**Không đổi máy móc thành `||`:**

```java
// SAI: text không chắc đã được ràng buộc ở vế phải.
if (value instanceof String text || text.isBlank()) {
    System.out.println("check");
}
```

Đây là ví dụ **cố ý không biên dịch**. Nếu mục tiêu là chấp nhận dữ liệu khác chuỗi **hoặc** chuỗi rỗng, cần diễn đạt lại điều kiện theo đúng logic:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("not a non-blank string");
}
```

Ở đây vế phải của `||` chỉ được đánh giá khi vế trái là `false`, tức `value instanceof String text` là `true`; lúc đó `text` nằm trong phạm vi hợp lệ.

### 7.3. Guard clause phủ định và `return` sớm

Legacy:

```java
if (!(value instanceof String)) {
    return "not-string";
}
String text = (String) value;
return text.strip();
```

Refactor:

```java
if (!(value instanceof String text)) {
    return "not-string";
}
return text.strip();
```

Mã mới hợp lệ: khi đã đi qua một nhánh có `return` trong điều kiện phủ định, compiler biết pattern đã khớp ở đường chạy còn lại. Ngược lại, nếu nhánh phủ định **không chắc kết thúc**, biến `text` sẽ không được bảo đảm có hiệu lực ngoài `if`.

### 7.4. Tránh trùng tên và đổi scope không chủ đích

Nếu đã có biến `text` trong phạm vi cục bộ, không thể tùy tiện khai báo pattern variable trùng tên ở vùng bị xung đột. Ngoài ra, khi thay một biến khai báo trong block bằng biến ràng buộc trong điều kiện, phạm vi nhìn thấy có thể khác so với bản cũ. Hãy sửa tên theo ý nghĩa, biên dịch lại và giữ nguyên các nhánh cần dùng biến đó thay vì mở rộng phạm vi bằng cast thêm.

## 8. Sự khác biệt giữa kiểu runtime và kiểu tĩnh

### 8.1. Overload resolution dựa vào kiểu ở vị trí lời gọi

Giả sử có hai overload:

```java
static void render(Object value) {
    System.out.println("generic");
}

static void render(String value) {
    System.out.println("text");
}
```

Trong legacy:

```java
if (input instanceof String) {
    String text = (String) input;
    render(text);  // Chọn render(String).
}
```

Sau refactor:

```java
if (input instanceof String text) {
    render(text);  // Vẫn chọn render(String).
}
```

Nhưng nếu lỡ viết `render(input)`, trong khi `input` có kiểu tĩnh `Object` thì có thể chọn `render(Object)`, dù đối tượng thực tế là chuỗi. Đây là thay đổi behavior **do truyền biến khác**, không phải do pattern matching; trình biên dịch vẫn cho phép.

### 8.2. Generic type erasure không tự biến mất

Legacy có thể dùng raw cast hoặc unchecked cast:

```java
// Minh họa cú pháp có cảnh báo unchecked.
java.util.List<String> names =
        (java.util.List<String>) unknown;
```

Không thể đổi thành:

```java
// SAI: không thể kiểm tra List<String> bằng instanceof khi kiểu là non-reifiable.
if (unknown instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Type arguments như `String` trong `List<String>` không được kiểm tra đầy đủ ở runtime do **type erasure**. Có thể dùng `List<?>` nếu mục tiêu là xác nhận đối tượng thuộc loại list:

```java
if (unknown instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

Tuy nhiên, `List<?>` **không chứng minh** mỗi phần tử là `String`. Nếu nghiệp vụ cần đảm bảo điều này, phải kiểm tra nội dung hoặc sử dụng API có hợp đồng kiểu đủ mạnh; không được mặc nhiên coi hai đoạn tương đương.

### 8.3. Kiểm tra `getClass()` và `instanceof` không phải cùng một phép thử

`obj.getClass() == Base.class` chỉ nhận **đúng lớp** `Base` (và gọi `getClass()` trên `null` sẽ ném NPE). `obj instanceof Base` còn nhận **các lớp con** của `Base`, và với `null` trả `false`. Không nên đổi một phép so sánh lớp chính xác thành pattern `instanceof Base base` rồi tuyên bố không đổi hành vi.

### 8.4. Lưu ý nhỏ về phiên bản Java 17

Ví dụ:

```java
String text = "hello";
if (text instanceof String match) {
    System.out.println(match);
}
```

Với **`--release 17`**, pattern `instanceof String match` trên biểu thức có kiểu tĩnh sẵn là `String` có thể bị từ chối vì đó là **unconditional pattern** chưa được Java 17 cho phép trong `instanceof`. Trong **Java 21**, trường hợp này được hỗ trợ. Đây là một khác biệt giữa các phiên bản ngôn ngữ, không phải sự thay đổi runtime khi pattern khớp.

Trong mã dành cho Java 17, nếu bạn đã có biến `String text`, thường không cần kiểm tra lại kiểu `String` bằng pattern. Hãy kiểm tra `null` theo hợp đồng và dùng trực tiếp `text` nếu phù hợp. Mọi ví dụ chạy đầy đủ ở mục 3 đều tương thích Java 17.

## 9. Khi chuyển từ legacy `if` sang `switch`/record pattern: nâng mức kiểm chứng

Refactor `instanceof + cast` sang `instanceof pattern` thường là thay đổi khá cục bộ. Nhưng biến chuỗi `if` thành **pattern matching for switch** (Java 21) hoặc phân rã record có thể thay đổi thêm:

- **Null handling:** `if (x instanceof T)` chỉ bỏ qua `null`, còn `switch (x)` với selector tham chiếu thường ném `NullPointerException` khi không có `case null` phù hợp.
- **Exhaustiveness:** switch expression và enhanced switch statement phải bao phủ các đầu vào thuộc kiểu selector; việc thêm `default`/mẫu tổng quát có thể thay đổi cách trường hợp bất ngờ được xử lý.
- **Thứ tự và dominance:** một mẫu tổng quát có thể che phủ mẫu cụ thể ở dưới; compiler có thể báo dominated case.
- **Guard:** `case T t when predicate(t)` không tương đương với `case T t` không điều kiện. Có thể bỏ sót những giá trị `T` có predicate sai.
- **Record deconstruction:** `case Record(var a, var b)` có thể ràng buộc các thành phần, còn mẫu record lồng nhau có thể không khớp nếu record con bằng `null`.

Ví dụ ý tưởng:

```java
// Java 21; giả sử input có kiểu Object.
String label = switch (input) {
    case null -> "missing";
    case String text -> "text:" + text;
    case Number number -> "number:" + number;
    default -> "other";
};
```

Đây là ví dụ minh họa, không phải chương trình đầy đủ. Để đánh giá có bảo toàn hành vi hay không, phải so với **thứ tự và chính sách null/unknown** của chuỗi `if/else` ban đầu; không thể chỉ căn cứ việc switch mới biên dịch thành công.

Nếu mục tiêu là loại bỏ cast dư thừa trong một hệ thống có độ rủi ro cao, nên **hoàn tất refactor cục bộ trước** rồi mới cân nhắc tái cấu trúc sang `switch`/record patterns như một thay đổi độc lập.

## 10. Quy trình refactor an toàn theo từng bước

### Bước 1: Chụp hành vi hiện tại

Với đúng phương thức chuẩn bị sửa, ghi lại các input đại diện, output hoặc exception tương ứng, và những side effects quan trọng. Nếu có log/audit, ghi rõ thứ tự. Với các lời gọi đọc dữ liệu, chú ý số lần thực thi và tình trạng dữ liệu có thể biến đổi.

### Bước 2: Xác định mẫu chỉ thay cú pháp

Tìm cấu trúc:

```java
if (candidate instanceof Target) {
    Target typed = (Target) candidate;
    process(typed);
}
```

Chỉ khi `candidate` ổn định từ điểm kiểm tra đến cast và `Target` là cùng kiểu mới thay thành:

```java
if (candidate instanceof Target typed) {
    process(typed);
}
```

Hai đoạn là **minh họa**: `Target` và `process` đại diện cho kiểu/phương thức thực trong ứng dụng. Không tự tạo thêm `else`, `default` hoặc giá trị fallback.

### Bước 3: Đổi một điểm rồi chạy biên dịch

Giữ nguyên:
- Thứ tự các `if/else if`, điều kiện `&&`, `||` và phép phủ định.
- Các lời gọi hàm cùng tham số, loại biến được truyền vào overload.
- Nội dung nhánh `else`, `return`/`throw`, log, catch/finally.
- Số lần đánh giá biểu thức có side effect và trạng thái shared mutable liên quan.

Compiler giúp phát hiện lỗi scope, xung đột tên biến, kiểu không phù hợp; nó **không** tự chứng minh mọi behavior nghiệp vụ còn nguyên.

### Bước 4: Kiểm thử trước/sau với cùng tập đầu vào

Một ma trận tối thiểu:

| Nhóm dữ liệu | Điều cần so sánh |
| --- | --- |
| Đúng kiểu | Nhánh, giá trị, side effect |
| Sai kiểu | Fallback hay exception |
| `null` | Nhánh có chạy không, exception có đổi không |
| Kiểu con | Có chọn đúng nhánh hẹp theo thứ tự không |
| Chuỗi rỗng / dữ liệu biên | Có giữ điều kiện guard và xử lý không |
| Nguồn biến đổi qua mỗi lần đọc | Số lần đánh giá, giá trị được dùng |
| Generic/raw type | Tính tương thích compile/runtime, cảnh báo |
| Overload | Có gọi cùng signature không |
| Lỗi tại service | Exception, log và cleanup có cùng thứ tự không |

Đừng chỉ kiểm tra rằng test pass; hãy kiểm tra **assertion thật sự bao phủ** kết quả và các side effects, đặc biệt khi refactor từ hai lần gọi hàm còn một lần.

### Bước 5: Tách thay đổi có chủ đích

Nếu trong quá trình đổi cú pháp phát hiện mã gốc thực hiện hai lần đọc hàng đợi, cast lỗi bất ngờ, hoặc thứ tự nhánh sai, có thể sửa. Nhưng hãy gắn đó là **behavior change** có chủ đích: chỉnh hợp đồng/kiểm thử, ghi rõ tác động, và không trộn nó vào lời cam kết “chỉ đổi cú pháp”.

## 11. Các anti-pattern cần tránh

1. **Thay mọi `(Type) methodCall()` bằng pattern trên `methodCall()` mà không đếm số lần gọi.** Có thể làm thay đổi side effects và dữ liệu được đọc.
2. **Bỏ điều kiện bảo vệ sau khi có pattern variable.** Pattern chứng minh kiểu, không chứng minh chuỗi không rỗng, danh sách không trống hoặc dữ liệu thỏa nghiệp vụ.
3. **Đảo thứ tự nhánh giữa kiểu cha và kiểu con.** Các trường hợp có quan hệ kế thừa sẽ chọn nhánh khác.
4. **Chuyển direct cast thành một `if` có fallback tùy ý.** Thay `ClassCastException`/`null` bằng hành vi khác.
5. **Dùng `input` thay cho biến pattern có kiểu hẹp.** Dễ làm đổi overload được chọn hoặc mất API của kiểu con.
6. **Dùng pattern variable ở sai phạm vi hoặc trùng tên biến.** Compiler báo lỗi; cần thiết kế lại luồng và tên.
7. **Xem `List<?>` là `List<String>`.** Generic type arguments không được kiểm tra như vậy ở runtime.
8. **Gộp sửa nghiệp vụ vào refactor cú pháp.** Làm khó xác nhận quan hệ trước/sau; nên tách commit hoặc phần thay đổi có kiểm thử riêng.
9. **Dựa vào môi trường biên dịch mới hơn để xác nhận mã Java 17.** Dùng `javac --release 17` nếu cần hỗ trợ Java 17; cú pháp chấp nhận ở Java 21 có thể không được chấp nhận ở Java 17.
10. **Giữ nguyên output nhưng quên exception và side effect.** Hai phiên bản có thể trả cùng chuỗi nhưng gọi API khác số lần, ghi audit khác thứ tự hoặc ném lỗi ở thời điểm khác.

## 12. Bài tập thực hành và đáp án

**Bài 1 — Phép thay đúng.** Có `Object input`:

```java
if (input instanceof Number) {
    Number n = (Number) input;
    return n.intValue();
}
return -1;
```

Hãy viết lại không có cast. **Đáp án:**

```java
if (input instanceof Number n) {
    return n.intValue();
}
return -1;
```

Hai đoạn tương đương khi dùng cùng biến `input` và không sửa biểu thức/nhánh khác.

**Bài 2 — Nguồn có tác dụng phụ.** `readNext()` trả các phần tử liên tiếp trong một queue. Tại sao `if (readNext() instanceof String) { String s = (String) readNext(); ... }` không tương đương với `if (readNext() instanceof String s) { ... }`? **Đáp án:** mã cũ đọc tối đa hai phần tử; mã mới đọc một phần tử. Có thể đổi giá trị được dùng, trạng thái queue và exception.

**Bài 3 — Null.** So sánh `String s = (String) null;` và `if (value instanceof String s)` khi `value == null`. **Đáp án:** cast hợp lệ và `s == null`; pattern không khớp. Không được thay trực tiếp nếu hợp đồng cần giữ khác biệt này.

**Bài 4 — Thứ tự ưu tiên.** Có `if (value instanceof Integer) ... else if (value instanceof Number) ...`. Khi đổi sang pattern, có nên đưa `Number` lên đầu không? **Đáp án:** không, vì `Integer` cũng là `Number`; nhánh được chọn sẽ khác.

**Bài 5 — Flow scoping.** `if (obj instanceof String text || text.isBlank())` có hợp lệ không? **Đáp án:** không; trong vế phải của `||`, `text` chưa chắc đã được gán. Nếu mục tiêu là nhận giá trị không phải chuỗi **hoặc** chuỗi rỗng, dùng `if (!(obj instanceof String text) || text.isBlank())`.

**Bài 6 — Generic.** Có thể thay cast `(List<String>) value` bằng `value instanceof List<String> strings` không? **Đáp án:** không, vì `List<String>` là kiểu generic không thể kiểm tra đầy đủ ở runtime. `List<?>` chỉ kiểm tra cấu trúc list, không đảm bảo phần tử là chuỗi.

**Bài 7 — Bảo toàn xử lý lỗi.** Nếu mã cũ chủ động ném `ClassCastException` cho sai kiểu, cách nào là an toàn hơn: tự ý trả `"unsupported"` hay xác nhận hợp đồng lỗi rồi refactor? **Đáp án:** xác nhận và giữ hợp đồng lỗi; thay fallback là hành vi mới, cần quyết định và kiểm thử riêng.

## 13. Ghi nhớ

**Refactor legacy cast an toàn** là chuyển `if (x instanceof T) { T t = (T) x; ... }` thành `if (x instanceof T t) { ... }` **khi cùng giá trị được kiểm tra và sử dụng, không có side effects/đột biến xen vào, và các nhánh xử lý còn nguyên**. Pattern matching giúp trình biên dịch liên kết kiểm tra kiểu với biến có kiểu đúng, nhưng **không tự bảo toàn** số lần gọi phương thức, thứ tự nhánh, chính sách xử lý `null`, ngoại lệ, overload hay hợp đồng generic.

Hãy xác nhận bằng **diff nhỏ + biên dịch đúng `--release` + regression tests** cho cả output lẫn side effects, và tách riêng mọi thay đổi hành vi có chủ đích.

**Tài liệu chính thức:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Java Language Specification 17 — Type Comparison Operator instanceof (`15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2), [Java Language Specification 17 — Patterns (`14.30)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30), [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441).
