# Viết type pattern thay cho cast thủ công — Thực hành tổng hợp Java

## 1. Mục tiêu của bài thực hành

Trong mã Java cũ, việc kiểm tra kiểu trước khi ép kiểu thường được viết thành hai thao tác riêng:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.strip());
}
```

Đoạn này có thể đúng, nhưng nhắc lại tên kiểu `String` ở cả `instanceof` và phép cast `(String) value`. Nếu phương thức lớn có nhiều nhánh hoặc các object lồng nhau, các cặp kiểm tra/cast lặp lại khiến code dài và dễ bị sửa lệch nhau.

**Type pattern với `instanceof`** cho phép viết:

```java
if (value instanceof String text) {
    System.out.println(text.strip());
}
```

Trong một biểu thức, Java vừa **kiểm tra kiểu runtime** vừa **ràng buộc biến pattern** có kiểu đã xác định. Nếu pattern không khớp, thân `if` không chạy; không có việc ép kiểu trực tiếp bị thất bại tại dòng đó.

Bài “**Viết type pattern thay cho cast thủ công**” thuộc nhóm **Thực hành tổng hợp**. Bạn sẽ:

1. Nhìn ra mô hình `instanceof T` → `(T) object` trong mã cũ.
2. Refactor sang `instanceof T variable` mà không thay đổi nhánh thành công hoặc nhánh không khớp.
3. Dùng **flow scoping** và guard clause để bỏ các phép cast lồng nhau.
4. Xử lý các kiểu `String`, `Integer`, `CharSequence`, `record` và `List<?>`.
5. Giữ đúng hành vi với `null`, dữ liệu không hợp lệ, kiểu runtime không khớp và thứ tự các nhánh.
6. Hiểu những chỗ **không nên** thay cast bằng pattern: khi cố ý muốn ném `ClassCastException`, khi đang chuyển đổi số hoặc khi kiểm tra generic type argument.
7. Chạy chương trình Java độc lập so sánh hai cách viết trên **25 ca kiểm thử**, sau đó tự làm bài tập refactor.

**Phiên bản:** Pattern matching cho `instanceof` được chuẩn hóa từ **Java 16** theo JEP 394. Mọi chương trình chạy đầy đủ trong bài chỉ dùng tính năng đã ổn định ở **Java 17**, không cần `--enable-preview`. Record patterns trong `switch` là phần mở rộng Java 21, được tách riêng ở cuối bài.

## 2. Quy tắc refactor cơ bản: kiểm tra kiểu và ràng buộc biến cùng lúc

### 2.1. Trước: cast thủ công sau instanceof

```java
static String oldText(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return "text:" + text.strip();
    }
    return "other";
}
```

Luồng hoạt động: `input instanceof String` trả true nếu `input` là một đối tượng `String` khác null. Sau đó phép `(String) input` sẽ thành công vì điều kiện đã xác nhận kiểu. Phép cast thứ hai có thể bỏ mà vẫn giữ ý định.

### 2.2. Sau: type pattern

```java
static String newText(Object input) {
    if (input instanceof String text) {
        return "text:" + text.strip();
    }
    return "other";
}
```

Trong `instanceof String text`:

- `String` là **kiểu pattern**.
- `text` là **biến pattern** được ràng buộc khi pattern khớp.
- Bên trong nhánh đúng, compiler biết `text` có kiểu `String` nên gọi được `strip()`.
- Khi `input` là `Integer`, `StringBuilder` hoặc `null`, pattern không khớp và chương trình trả `"other"`.

Nếu code cũ đã bảo đảm cast an toàn bằng `instanceof` trên **chính cùng giá trị**, refactor thường rất thẳng. Tuy nhiên việc giữ nguyên hành vi tổng thể còn phụ thuộc vào những biểu thức khác, thứ tự nhánh và cách xử lý null.

### 2.3. Không phải cast nào cũng có thể thay bằng type pattern

Ví dụ:

```java
String text = (String) raw;
```

Đây là phép ép kiểu **trực tiếp**. Nếu `raw` là `Integer`, Java ném `ClassCastException`. Nếu thay bằng:

```java
if (raw instanceof String text) {
    use(text);
}
```

bạn đã chuyển từ **“sai kiểu thì ném lỗi”** sang **“sai kiểu thì bỏ qua”**, chưa chắc tương đương. Nếu hợp đồng yêu cầu từ chối kiểu không hợp lệ, hãy viết nhánh lỗi tường minh:

```java
if (!(raw instanceof String text)) {
    throw new IllegalArgumentException("expected a String");
}
use(text);
```

Hai snippet có `raw`/`use` lấy từ ngữ cảnh phương thức. Chúng minh họa ba chính sách khác nhau: cast trực tiếp, bỏ qua non-match và từ chối có thông báo. Chọn chính sách theo hợp đồng, không chỉ theo độ dài cú pháp.

## 3. Hiểu match, non-match và null trước khi refactor

| Giá trị của `Object raw` | `raw instanceof String text` | Nhánh đi vào |
| --- | --- | --- |
| `"Java"` | true | Nhánh String, `text="Java"` |
| `""` | true | Nhánh String, dù chuỗi rỗng |
| `7` | false | Nhánh không khớp |
| `3.5` | false | Nhánh không khớp |
| `new StringBuilder("abc")` | false | Nhánh không khớp |
| `null` | false | Nhánh không khớp |

Hai trường hợp dễ bị nhầm:

**Chuỗi rỗng không phải non-match.** Nó vẫn thuộc kiểu `String`, vì vậy nếu nghiệp vụ yêu cầu dữ liệu có nội dung, phải thêm điều kiện kiểm tra `text.isBlank()`.

**`null` không khớp type pattern.** `null instanceof String text` cho kết quả false và không tự ném `NullPointerException`. Tuy nhiên, nếu nhánh fallback gọi `raw.getClass()` mà không xử lý null, ứng dụng có thể phát sinh NPE ở **mã fallback**, không phải do `instanceof`.

Phần mã thực hành sau này phân biệt rõ `"missing"` với các giá trị kiểu không hỗ trợ.

### 3.1. Kiểu tĩnh và kiểu runtime

Với:

```java
Object input = 7;
```

Biến `input` có kiểu tĩnh là `Object`, còn đối tượng runtime là `Integer` (do autoboxing). Vì vậy `input instanceof Integer number` khớp. Nhưng `input instanceof Long number` không khớp, dù 7 là một số nguyên theo cách nói thông thường.

Pattern dựa trên quan hệ kiểu của Java, không dựa vào tên hiển thị, hình dạng dữ liệu hay khả năng chuyển đổi số. Không coi `Integer` và `Long` là cùng type pattern; nếu cần nhận nhiều loại số, cân nhắc `Number` với quy tắc xử lý các giá trị cụ thể.

## 4. Refactor một chuỗi phân loại nhiều kiểu

Một use case thường gặp là nhận `Object` rồi phân loại. Mã cũ:

```java
static String oldLabel(Object value) {
    if (value == null) return "missing";

    if (value instanceof String) {
        String text = (String) value;
        return text.isBlank() ? "blank-text" : "text:" + text.strip();
    }
    if (value instanceof Integer) {
        Integer n = (Integer) value;
        return "integer:" + n;
    }
    if (value instanceof CharSequence) {
        CharSequence chars = (CharSequence) value;
        return "chars:" + chars.length();
    }
    return "unsupported:" + value.getClass().getSimpleName();
}
```

Bản dùng type patterns:

```java
static String newLabel(Object value) {
    if (value == null) return "missing";

    if (value instanceof String text) {
        return text.isBlank() ? "blank-text" : "text:" + text.strip();
    }
    if (value instanceof Integer n) {
        return "integer:" + n;
    }
    if (value instanceof CharSequence chars) {
        return "chars:" + chars.length();
    }
    return "unsupported:" + value.getClass().getSimpleName();
}
```

Những điểm đã cải thiện:

- Không lặp lại `String text = (String) value`, `Integer n = (Integer) value` và `CharSequence chars = (CharSequence) value`.
- Các nhánh cho thấy ngay **đầu vào khớp kiểu nào** và **biến nào dùng trong nhánh**.
- Không cần tạo một biến kiểu rộng rồi cast trước mọi lần gọi phương thức.
- Giữ nguyên thứ tự nhánh, cách xử lý null và fallback để không vô tình thay đổi hành vi.

**Vì sao để `String` trước `CharSequence`?** `String` implements `CharSequence`. Nếu đổi thứ tự và nhánh `CharSequence` trả về ngay, một String sẽ đi vào nhánh rộng trước, không còn xử lý theo quy tắc riêng của String. Việc bỏ cast không cho phép tự động đảo các nhánh.

Trong chương trình đầy đủ ở mục 8, còn có thêm case `Purchase` để minh họa type pattern với record nghiệp vụ.

## 5. Flow scoping: biến pattern sống ở nơi compiler biết đã khớp

Type pattern không đơn giản là khai báo biến cục bộ thông thường. Java sử dụng **flow scoping**: biến chỉ hợp lệ ở những đường điều khiển mà compiler xác định pattern chắc chắn đã thành công.

### 5.1. Bên trong nhánh đúng

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Ở đây `text` hợp lệ trong nhánh `if`. Sau `if`, nếu chương trình có thể đi tiếp cả khi input không là String, bạn không thể dùng `text` như thể nó luôn tồn tại.

### 5.2. Kết hợp với && để kiểm tra thêm điều kiện

```java
static String longText(Object value) {
    if (value instanceof CharSequence text && text.length() >= 3) {
        return "long:" + text.length();
    }
    return "short-or-other";
}
```

Toán tử `&&` đánh giá vế phải **chỉ khi** vế trái true. Vì vậy, khi chạy `text.length()`, compiler biết pattern `CharSequence text` đã khớp và biến `text` được ràng buộc.

Ba nhóm ca test cần thiết:

- `"Java"` → pattern khớp, điều kiện độ dài đúng → `long:4`.
- `"ab"` → pattern khớp nhưng guard false → `short-or-other`.
- `null` hoặc `123` → pattern không khớp, vế phải không được đánh giá → `short-or-other`.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH: khi vế trái false thì text chưa được ràng buộc.
if (value instanceof CharSequence text || text.length() >= 3) {
    System.out.println(text);
}
```

Với `||`, vế phải được xét khi vế trái false, chính là lúc biến pattern **chưa** có giá trị. Không đổi `&&` thành `||` mà vẫn dùng biến pattern ở vế phải.

### 5.3. Guard clause phủ định giúp giảm nesting

Mã cũ:

```java
static int oldLength(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return -1;
}
```

Mã mới:

```java
static int newLength(Object input) {
    if (!(input instanceof String text)) return -1;
    return text.length();
}
```

Tại lệnh `return text.length();`, compiler biết mọi đường đi không khớp đều đã kết thúc ở `return -1;`. Do đó `text` hợp lệ phía sau guard clause. Cách viết này giúp đặt **đường thành công ở cuối** mà không lồng thêm nhiều `if`.

Nếu bỏ `return -1;` và để nhánh phủ định tiếp tục chạy, compiler không còn đủ bằng chứng rằng `text` luôn được ràng buộc. Flow scoping là một kiểm tra tĩnh, không phải mẹo đặt tên biến.

## 6. Refactor ép kiểu lồng nhau: Envelope chứa Purchase

Khi dữ liệu được lồng trong một wrapper, mã cast thủ công có thể rất khó theo dõi. Ta dùng:

```java
record Purchase(String orderId, java.math.BigDecimal amount) {}
record Envelope(Object payload) {}
```

Ý định: đầu vào phải là `Envelope`, component `payload` phải là `Purchase`, giá trị `amount` phải khác null và dương. Nếu hợp lệ, trả `accepted:<orderId>`. Nếu không hợp lệ, trả mã lỗi rõ ràng.

### 6.1. Phiên bản cũ

```java
static String oldPurchase(Object input) {
    if (!(input instanceof Envelope)) return "not-envelope";
    Envelope envelope = (Envelope) input;

    if (!(envelope.payload() instanceof Purchase)) return "not-purchase";
    Purchase purchase = (Purchase) envelope.payload();

    java.math.BigDecimal amount = purchase.amount();
    if (amount == null) return "missing-amount";
    if (amount.signum() <= 0) return "nonpositive";

    return "accepted:" + purchase.orderId();
}
```

Đầu tiên kiểm tra `Envelope`, sau đó cast; tiếp tục kiểm tra `Purchase` rồi lại cast. Trong ví dụ này `Envelope` là record có accessor mặc định, nên gọi `payload()` hai lần cho cùng component không thay đổi đối tượng.

### 6.2. Phiên bản dùng type patterns

```java
static String newPurchase(Object input) {
    if (!(input instanceof Envelope envelope)) return "not-envelope";
    if (!(envelope.payload() instanceof Purchase purchase)) return "not-purchase";

    java.math.BigDecimal amount = purchase.amount();
    if (amount == null) return "missing-amount";
    if (amount.signum() <= 0) return "nonpositive";

    return "accepted:" + purchase.orderId();
}
```

Với pattern `Envelope envelope`, compiler tự ràng buộc biến sau khi kiểm tra. Khi guard không khớp, phương thức đã thoát. Tiếp theo, pattern `Purchase purchase` ràng buộc dữ liệu `payload`; không còn hai phép cast.

**Mã mới là type patterns, chưa phải record deconstruction.** Java 17 đã hỗ trợ `instanceof Envelope envelope` và `instanceof Purchase purchase`. Nếu nâng lên Java 21, có thể dùng record pattern lồng như `Envelope(Purchase(var orderId, var amount))`, nhưng đó là một kỹ thuật khác, sẽ được phân biệt ở mục 11.

### 6.3. Cẩn thận với null ở nhiều tầng

Cần kiểm thử:

| Input | `Envelope` match? | `Purchase` match? | Kết quả |
| --- | --- | --- | --- |
| `null` | Không | Không xét | `not-envelope` |
| `"other"` | Không | Không xét | `not-envelope` |
| `new Envelope(null)` | Có | Không | `not-purchase` |
| `new Envelope("other")` | Có | Không | `not-purchase` |
| `new Envelope(new Purchase("P2", null))` | Có | Có | `missing-amount` |
| `new Envelope(new Purchase("P3", BigDecimal.ZERO))` | Có | Có | `nonpositive` |
| `new Envelope(new Purchase("P1", new BigDecimal("2.00")))` | Có | Có | `accepted:P1` |

Record `Purchase` có thể có component `amount == null` vì record ở đây không có validation trong constructor. **Type pattern `Purchase purchase` chỉ chứng minh kiểu của object, không chứng minh component hợp lệ**. Vì vậy kiểm tra `amount == null` là bắt buộc nếu nghiệp vụ không chấp nhận thiếu số tiền.

### 6.4. Tránh đánh giá lại getter có side effect khi refactor

Mã cũ kiểm tra và đọc `envelope.payload()` hai lần. Với record accessor mặc định cho component `Object payload`, kết quả ổn định. Nhưng nếu mã thực tế gọi một accessor tùy biến có side effect hoặc dữ liệu bị thay đổi từ bên ngoài, hai lời gọi có thể khác nhau.

Khi đó nên gán giá trị cần kiểm tra **một lần**:

```java
Object payload = getPayload();
if (!(payload instanceof Purchase purchase)) {
    return "not-purchase";
}
// Sử dụng purchase ở đây.
```

`getPayload()` là một phương thức giả định của ứng dụng, không có trong tệp chạy độc lập. Mục tiêu là không vô ý đổi **số lần đánh giá** biểu thức khi refactor. Đặc biệt không cast một kết quả mới từ `getPayload()` sau khi đã kiểm tra một kết quả cũ.

## 7. Interface/subtype và generic: những chỗ type pattern cần hiểu sâu hơn

### 7.1. StringBuilder không phải String nhưng là CharSequence

`StringBuilder` và `String` đều có khả năng cung cấp ký tự, nhưng `StringBuilder` **không kế thừa** `String`. Ví dụ:

```java
Object input = new StringBuilder("abcd");

System.out.println(input instanceof String);       // false
System.out.println(input instanceof CharSequence); // true
```

Một case `input instanceof String text` không khớp. Nếu bạn muốn xử lý cả `StringBuilder`, cần pattern rộng như `CharSequence chars` hoặc những case riêng. Trong chương trình đầy đủ, `String` được xử lý trước, còn `CharSequence` đứng sau để nhận `StringBuilder`.

Đừng thay type pattern bằng `input.getClass() == CharSequence.class`: đây là so sánh **chính xác đối tượng Class**, không kiểm tra implementation/subtype, nên sẽ false với StringBuilder dù `instanceof CharSequence` là true.

### 7.2. Kiểm tra generic container bằng List<?>

Một cạm bẫy:

```java
// KHÔNG BIÊN DỊCH trong ngữ cảnh Object raw thông thường:
if (raw instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Type argument của đa số generic types không được giữ đầy đủ tại runtime do **type erasure**. Với `Object raw`, pattern `List<String>` ở trên không phải type check reifiable hợp lệ. Refactor an toàn dùng wildcard cho container, rồi kiểm tra phần tử:

```java
static int countNonblankStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) return 0;

    int count = 0;
    for (Object element : items) {
        if (element instanceof String text && !text.isBlank()) {
            count++;
        }
    }
    return count;
}
```

Ví dụ:

- `["a", 5, " ", null, "xyz"]` → hai String không blank: `"a"` và `"xyz"`.
- `"abc"` không phải List → 0.
- List chỉ chứa số nguyên vẫn khớp `List<?>`, nhưng không phần tử nào khớp `String text`.
- List rỗng vẫn khớp container pattern và trả 0.

**Lưu ý:** `List<?>` chỉ bảo đảm object thuộc một implementation của `List`. Nó không đảm bảo từng phần tử là String. Nếu logic cần toàn bộ list có kiểu thống nhất, hãy validate từng phần tử hoặc dùng dữ liệu có schema đáng tin.

### 7.3. Không nhầm type pattern với phép chuyển đổi số

Nếu input là `Long 7L`, `instanceof Integer i` false. Pattern matching không tự biến Long thành Integer. Nếu nghiệp vụ chấp nhận các kiểu số khác nhau, có thể dùng `Number number` rồi chuyển đổi theo chính sách, nhưng cần kiểm tra phạm vi, tràn số và tính chính xác.

Ví dụ, `Number.intValue()` có thể mất thông tin với số lớn hoặc số thực. Chuyển từ cast sang type pattern **không loại bỏ** những rủi ro ấy.

## 8. Chương trình Java 17 hoàn chỉnh — so sánh trước/sau bằng 25 phép kiểm thử

Tạo tệp duy nhất **`ManualCastRefactorDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

public class ManualCastRefactorDemo {
    record Purchase(String orderId, BigDecimal amount) {}
    record Envelope(Object payload) {}

    static String oldLabel(Object value) {
        if (value == null) return "missing";
        if (value instanceof String) {
            String text = (String) value;
            return text.isBlank() ? "blank-text" : "text:" + text.strip();
        }
        if (value instanceof Integer) {
            Integer n = (Integer) value;
            return "integer:" + n;
        }
        if (value instanceof Purchase) {
            Purchase purchase = (Purchase) value;
            return "purchase:" + purchase.orderId() + "/" + purchase.amount();
        }
        if (value instanceof CharSequence) {
            CharSequence chars = (CharSequence) value;
            return "chars:" + chars.length();
        }
        return "unsupported:" + value.getClass().getSimpleName();
    }

    static String newLabel(Object value) {
        if (value == null) return "missing";
        if (value instanceof String text) {
            return text.isBlank() ? "blank-text" : "text:" + text.strip();
        }
        if (value instanceof Integer n) return "integer:" + n;
        if (value instanceof Purchase purchase) {
            return "purchase:" + purchase.orderId() + "/" + purchase.amount();
        }
        if (value instanceof CharSequence chars) {
            return "chars:" + chars.length();
        }
        return "unsupported:" + value.getClass().getSimpleName();
    }

    static String oldPurchase(Object input) {
        if (!(input instanceof Envelope)) return "not-envelope";
        Envelope envelope = (Envelope) input;
        if (!(envelope.payload() instanceof Purchase)) return "not-purchase";
        Purchase purchase = (Purchase) envelope.payload();
        BigDecimal amount = purchase.amount();
        if (amount == null) return "missing-amount";
        if (amount.signum() <= 0) return "nonpositive";
        return "accepted:" + purchase.orderId();
    }

    static String newPurchase(Object input) {
        if (!(input instanceof Envelope envelope)) return "not-envelope";
        if (!(envelope.payload() instanceof Purchase purchase)) return "not-purchase";
        BigDecimal amount = purchase.amount();
        if (amount == null) return "missing-amount";
        if (amount.signum() <= 0) return "nonpositive";
        return "accepted:" + purchase.orderId();
    }

    static String oldLength(Object value) {
        if (value instanceof CharSequence) {
            CharSequence text = (CharSequence) value;
            if (text.length() >= 3) return "long:" + text.length();
        }
        return "short-or-other";
    }

    static String newLength(Object value) {
        if (value instanceof CharSequence text && text.length() >= 3) {
            return "long:" + text.length();
        }
        return "short-or-other";
    }

    static int countNonblankStrings(Object value) {
        if (!(value instanceof List<?> items)) return 0;
        int count = 0;
        for (Object element : items) {
            if (element instanceof String text && !text.isBlank()) {
                count++;
            }
        }
        return count;
    }

    static String unsafeCast(Object value) {
        Purchase purchase = (Purchase) value;
        return purchase.orderId();
    }

    static int passed;

    static void compare(String label, String expected, String oldResult, String newResult) {
        if (!expected.equals(oldResult) || !expected.equals(newResult)) {
            throw new AssertionError(
                label + ": expected " + expected
                + ", old=" + oldResult + ", new=" + newResult
            );
        }
        passed++;
        System.out.println("PASS " + label + " => " + newResult);
    }

    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + ": expected " + expected + ", got " + actual
            );
        }
        passed++;
        System.out.println("PASS " + label + " => " + actual);
    }

    static void expectBadCast() {
        try {
            unsafeCast("not-a-purchase");
            throw new AssertionError("unsafe-cast: expected ClassCastException");
        } catch (ClassCastException ex) {
            passed++;
            System.out.println("PASS unsafe-cast => ClassCastException");
        }
    }

    static void labelCase(String name, String expected, Object value) {
        compare(name, expected, oldLabel(value), newLabel(value));
    }

    static void purchaseCase(String name, String expected, Object value) {
        compare(name, expected, oldPurchase(value), newPurchase(value));
    }

    static void lengthCase(String name, String expected, Object value) {
        compare(name, expected, oldLength(value), newLength(value));
    }

    public static void main(String[] args) {
        labelCase("text", "text:java", " java ");
        labelCase("blank", "blank-text", "   ");
        labelCase("integer", "integer:7", 7);
        labelCase("negative", "integer:-3", -3);
        labelCase("purchase", "purchase:P1/12.50",
                new Purchase("P1", new BigDecimal("12.50")));
        labelCase("builder", "chars:4", new StringBuilder("abcd"));
        labelCase("double", "unsupported:Double", 3.5);
        labelCase("boolean", "unsupported:Boolean", true);
        labelCase("object", "unsupported:Object", new Object());
        labelCase("null", "missing", null);

        purchaseCase("nested-valid", "accepted:P1",
                new Envelope(new Purchase("P1", new BigDecimal("2.00"))));
        purchaseCase("nested-null-amount", "missing-amount",
                new Envelope(new Purchase("P2", null)));
        purchaseCase("nested-zero", "nonpositive",
                new Envelope(new Purchase("P3", BigDecimal.ZERO)));
        purchaseCase("nested-negative", "nonpositive",
                new Envelope(new Purchase("P4", new BigDecimal("-1"))));
        purchaseCase("nested-other", "not-purchase", new Envelope("other"));
        purchaseCase("nested-null-payload", "not-purchase", new Envelope(null));
        purchaseCase("nested-null", "not-envelope", null);
        purchaseCase("nested-wrong-type", "not-envelope", "other");

        lengthCase("length-string", "long:4", "Java");
        lengthCase("length-short", "short-or-other", "ab");
        lengthCase("length-builder", "long:3", new StringBuilder("abc"));
        lengthCase("length-null", "short-or-other", null);

        expect("mixed-list", "2",
                Integer.toString(countNonblankStrings(
                        Arrays.asList("a", 5, " ", null, "xyz"))));
        expect("not-list", "0",
                Integer.toString(countNonblankStrings("abc")));
        expectBadCast();

        System.out.println("checks=" + passed);
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 ManualCastRefactorDemo.java
java ManualCastRefactorDemo
```

**Kết quả stdout chính xác:**

```text
PASS text => text:java
PASS blank => blank-text
PASS integer => integer:7
PASS negative => integer:-3
PASS purchase => purchase:P1/12.50
PASS builder => chars:4
PASS double => unsupported:Double
PASS boolean => unsupported:Boolean
PASS object => unsupported:Object
PASS null => missing
PASS nested-valid => accepted:P1
PASS nested-null-amount => missing-amount
PASS nested-zero => nonpositive
PASS nested-negative => nonpositive
PASS nested-other => not-purchase
PASS nested-null-payload => not-purchase
PASS nested-null => not-envelope
PASS nested-wrong-type => not-envelope
PASS length-string => long:4
PASS length-short => short-or-other
PASS length-builder => long:3
PASS length-null => short-or-other
PASS mixed-list => 2
PASS not-list => 0
PASS unsafe-cast => ClassCastException
checks=25
```

**Giải thích kết quả kiểm thử:**

- Mười ca `labelCase` gọi **cả phiên bản cũ và mới**, sau đó so với expected. Chúng kiểm tra `String`, `Integer`, record `Purchase`, `CharSequence`, kiểu không hỗ trợ và null.
- Tám ca `purchaseCase` xác nhận refactor ép kiểu lồng nhau không thay đổi các mã lỗi khi thiếu `Envelope`, sai kiểu payload, thiếu amount hoặc amount không dương.
- Bốn ca `lengthCase` kiểm tra `&&` khi pattern match + guard true, match + guard false, subtype interface và null.
- Hai ca `countNonblankStrings` kiểm tra container/element pattern khi dữ liệu là list trộn nhiều kiểu hoặc không phải list.
- Một ca `expectBadCast` xác nhận cast trực tiếp sai kiểu ném **ClassCastException**, nhấn mạnh sự khác nhau giữa “cast không có guard” và “pattern không khớp”.

Helper `compare` ném `AssertionError` nếu **oldResult hoặc newResult** khác expected. Điều này mạnh hơn việc chỉ so sánh old với new: nếu cả hai đều sai theo cùng một cách, kiểm tra old==new không đủ. Helper `expect` cũng so sánh với expected trước khi in PASS.

Dòng `checks=25` cho biết **25 kiểm tra cụ thể đã thành công**, không có nghĩa chương trình bao phủ mọi input hoặc chứng minh refactor luôn đúng trong hệ thống thực tế.

### Tại sao dùng BigDecimal cho amount?

Trong bài, `Purchase.amount` là `BigDecimal` để minh họa dữ liệu tiền tệ và kiểm tra số dương bằng `amount.signum()`. Điều này tránh dùng so sánh `double` không cần thiết cho tiền. Ta không chuyển tiền tệ, không tính thuế hoặc làm tròn ở đây; mục tiêu là kiểm tra **kiểu và điều kiện**.

`BigDecimal.ZERO` có `signum()==0`; `new BigDecimal("-1")` có `signum()==-1`. Cả hai đều bị từ chối theo `signum() <= 0`. Cần kiểm tra null trước khi gọi `signum()`, nếu không có thể phát sinh NPE.

## 9. Bài tập thực hành: tự refactor rồi so kết quả

### Bài A — Một kiểu và một nhánh lỗi

Mã cũ:

```java
static String greet(Object person) {
    if (person instanceof String) {
        String name = (String) person;
        return "Hello, " + name.strip();
    }
    return "Unknown";
}
```

**Yêu cầu:** Bỏ cast nhưng giữ kết quả với `" Lan "`, `7`, `null`.

**Đáp án:**

```java
static String greet(Object person) {
    if (person instanceof String name) {
        return "Hello, " + name.strip();
    }
    return "Unknown";
}
```

Kết quả:

- `greet(" Lan ")` → `Hello, Lan`.
- `greet(7)` → `Unknown`.
- `greet(null)` → `Unknown`.

Không tự đổi nhánh null thành ngoại lệ hoặc bỏ fallback khi đề bài chỉ yêu cầu refactor cast.

### Bài B — Nhiều kiểu có quan hệ subtype/interface

Mã cũ:

```java
static String format(Object input) {
    if (input instanceof CharSequence) {
        CharSequence value = (CharSequence) input;
        return "chars:" + value.length();
    }
    if (input instanceof Number) {
        Number value = (Number) input;
        return "number:" + value;
    }
    return "unknown";
}
```

**Đáp án:**

```java
static String format(Object input) {
    if (input instanceof CharSequence value) {
        return "chars:" + value.length();
    }
    if (input instanceof Number number) {
        return "number:" + number;
    }
    return "unknown";
}
```

Các ca test:

- `new StringBuilder("abc")` → `chars:3`.
- `"hello"` → `chars:5`.
- `7L` → `number:7`.
- `3.5` → `number:3.5`.
- `null` → `unknown`.

Một lỗi refactor thường gặp là đổi `CharSequence` thành `String` vì thấy code thao tác văn bản. Như vậy StringBuilder không còn match và hành vi thay đổi.

### Bài C — Cast lồng qua wrapper

Mã cũ:

```java
record Container(Object item) {}
record Customer(String name) {}

static String customerName(Object input) {
    if (!(input instanceof Container)) return "bad-container";
    Container container = (Container) input;
    if (!(container.item() instanceof Customer)) return "bad-customer";
    Customer customer = (Customer) container.item();
    return customer.name();
}
```

**Đáp án tương thích Java 17:**

```java
static String customerName(Object input) {
    if (!(input instanceof Container container)) return "bad-container";
    if (!(container.item() instanceof Customer customer)) return "bad-customer";
    return customer.name();
}
```

Test cần gồm Container hợp lệ, Container(null), Container(String), input null. Nếu Customer có component `name == null`, phương thức vẫn trả null; nếu nghiệp vụ không chấp nhận điều đó, cần thêm validation riêng, **không tự cho rằng type pattern đã kiểm tra tên**.

### Bài D — Guard với điều kiện ngưỡng

Cho `Object value`, yêu cầu chỉ trả mã xử lý khi value là String dài ít nhất 4 ký tự, còn lại trả `"skip"`. Viết bằng một `if` với `&&`:

```java
static String process(Object value) {
    if (value instanceof String text && text.length() >= 4) {
        return "use:" + text;
    }
    return "skip";
}
```

Test tối thiểu:

- `"abcd"` → `use:abcd` (bằng ngưỡng).
- `"abc"` → `skip` (dưới ngưỡng).
- `1234` → `skip` (sai kiểu).
- `null` → `skip` (pattern false).

Không bỏ ca sai kiểu: nó chứng minh vế phải dùng `text.length()` không bị đánh giá khi pattern không khớp.

## 10. Những lỗi refactor type pattern thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Bỏ `instanceof` và giữ cast trực tiếp | Input sai kiểu có thể ném `ClassCastException`. | Chỉ cast trực tiếp khi hợp đồng cần fail fast; nếu có non-match path, dùng type pattern và xử lý rõ. |
| Refactor nhưng đổi thứ tự case | Kiểu hẹp có thể bị kiểu rộng xử lý trước. | Giữ thứ tự cũ hoặc thay có chủ đích kèm tests. |
| Thay `CharSequence` bằng `String` | StringBuilder không còn khớp. | Bảo toàn loại pattern; test implementation khác nhau của interface. |
| Không test null | Nhánh fallback có thể dereference null. | Giữ null handling đúng hợp đồng và test riêng. |
| Dùng biến pattern ngoài flow scope | Compiler không bảo đảm biến đã được ràng buộc. | Dùng trong nhánh đúng hoặc sau guard clause phủ định có early return. |
| Dùng `||` khi vế phải cần biến pattern | Biến không chắc được ràng buộc khi vế trái false. | Dùng `&&` hoặc tách điều kiện đúng logic. |
| Nghĩ `instanceof Purchase p` kiểm tra amount > 0 | Type pattern chỉ kiểm tra kiểu object. | Kiểm tra null/component/invariant riêng. |
| Đổi nhánh non-match thành throw mà không cân nhắc | Có thể thay đổi API từ fallback sang exception. | So sánh hành vi trước/sau bằng expected assertions. |
| Cast lại giá trị do getter được gọi lần hai | Getter có thể thay đổi hoặc có side effect. | Lấy giá trị một lần và match chính giá trị đó. |
| Dùng `List<String>` cho Object runtime | Generic type argument bị erasure; pattern không phù hợp trong trường hợp thông thường. | Dùng `List<?>`, rồi kiểm tra các phần tử. |
| Cố gắng dùng `String s instanceof String text` | Java có thể từ chối kiểu pattern không có ý nghĩa khi static type đã là subtype. | Chỉ dùng pattern khi cần kiểm tra runtime; dùng `String` trực tiếp nếu kiểu đã chắc chắn. |
| Nhầm type pattern với record pattern | `instanceof Purchase(var id,var amount)` chưa chuẩn ở Java 17. | Java 17 dùng `Purchase p` + accessor; Java 21 mới có record deconstruction. |
| Chỉ kiểm tra `old.equals(new)` | Cả old và new có thể cùng sai. | So với expected độc lập và thêm ca lỗi/biên. |
| Dồn hết vào một `if` phức tạp | Code khó đọc dù ít cast. | Dùng guard clauses, phương thức nhỏ và tên biến có ý nghĩa. |

## 11. Java 21: khi nào chuyển tiếp từ type pattern sang record pattern hoặc switch?

Bài chính dùng **Java 17** vì mục tiêu là bỏ cast thủ công, không bắt buộc phải dùng cú pháp Java 21. Tuy nhiên, nếu dự án đã nâng lên Java 21, bạn có thêm lựa chọn.

### 11.1. Type pattern và record pattern không giống nhau

Với `record Purchase(String orderId, BigDecimal amount)`:

```java
// Type pattern: ổn định từ Java 16.
if (raw instanceof Purchase purchase) {
    return purchase.orderId();
}
```

```java
// Record pattern: chính thức từ Java 21.
if (raw instanceof Purchase(var orderId, var amount)) {
    return orderId;
}
```

Type pattern ràng buộc **cả object**; record pattern ràng buộc **các component**. Chọn record pattern khi cần deconstruct cấu trúc một cách rõ ràng, đặc biệt khi lồng record; không đổi sang pattern mới chỉ để giảm một lần gọi accessor nếu khiến code khó đọc hơn.

### 11.2. Switch expression khi có nhiều nhánh cùng selector

Từ Java 21:

```java
// Snippet Java 21; đặt trong method nhận Object value.
return switch (value) {
    case null -> "missing";
    case String text when text.isBlank() -> "blank-text";
    case String text -> "text:" + text.strip();
    case Integer number -> "integer:" + number;
    default -> "unsupported";
};
```

`switch` có thể rõ hơn chuỗi `if` khi nhiều case cùng phân loại **một selector**, nhưng không phải lúc nào cũng tốt hơn. Với một phép kiểm tra sớm và tiếp tục xử lý nghiệp vụ, `if (value instanceof T t)` hoặc guard clause thường đơn giản hơn.

**Lưu ý:** `case String text when text.isBlank()` phải đứng trước `case String text` không guard, nếu không case đặc thù bị nhánh rộng che (*domination*). `case null` thể hiện chính sách null chủ động; không coi `default` là tự động xử lý null.

### 11.3. Giữ tương thích source level

Nếu dự án đặt `javac --release 17`, không thể dùng record patterns hoặc pattern matching for switch chính thức của Java 21 trong source Java 17. Mã type pattern `instanceof T variable` của bài vẫn hợp lệ và giúp cải thiện readability mà không buộc nâng phiên bản.

## 12. Quy trình refactor trên dự án thật

Một quy trình làm việc đáng tin:

1. **Tìm cặp kiểm tra/cast**: `if (x instanceof T) { T t = (T)x; ... }` và các biến thể phủ định.
2. **Xác định cùng một biểu thức**: nếu code cũ kiểm tra một lời gọi getter rồi cast kết quả của lần gọi khác, xem việc đánh giá lặp có ý nghĩa gì. Có thể cần lưu vào biến trước khi thay.
3. **Ghi nhận hợp đồng hiện tại**: nhánh match xử lý gì? Non-match trả giá trị, chuyển sang nhánh khác hay ném ngoại lệ? Null xử lý thế nào?
4. **Thay bằng type pattern**: `x instanceof T t`, xóa cast dư, dùng biến `t` trong scope hợp lệ.
5. **Giữ thứ tự và mức rộng của type**: `String` trước `CharSequence` nếu muốn nhánh riêng; `Integer` không tự thay được `Number`.
6. **Đưa validation khác vào vị trí rõ ràng**: kiểm tra component null, rỗng, số âm, trạng thái hoặc quyền không phải việc của type pattern.
7. **Giữ thông điệp lỗi và exception theo hợp đồng**: tránh âm thầm đổi `ClassCastException` thành bỏ qua, hoặc đổi fallback thành throw.
8. **Chạy unit tests trước/sau** với expected độc lập cho match, non-match, null, subtype, giá trị biên và các trường hợp lồng nhau.
9. **Biên dịch đúng phiên bản**: type patterns cho `instanceof` chính thức từ Java 16; kiểm tra JDK và `--release` trong IDE/CI.
10. **Review tính dễ đọc**: nếu nhiều type pattern tạo một phương thức khổng lồ, tách phương thức xử lý thay vì coi việc bỏ cast là đủ.

### Khi nào không cần type pattern?

Nếu biến đã có kiểu chính xác tại compile time, cứ dùng nó trực tiếp:

```java
static int size(String value) {
    return value.length();
}
```

Không cần hỏi lại `value instanceof String text`. Nếu đối tượng có thể null, xử lý null theo hợp đồng: type pattern không phải là cách bắt buộc để null-check. Với kiểu Java không cần cast hoặc pattern, đừng thêm cấu trúc chỉ để “hiện đại hóa”.

## 13. Tổng kết

**Type pattern cho `instanceof` thay thế hiệu quả mô hình “kiểm tra kiểu rồi ép kiểu thủ công”.** Cú pháp `if (value instanceof T variable)` kết hợp hai thao tác, giúp giảm lặp kiểu, bỏ cast dư và làm rõ phạm vi sử dụng biến đã được kiểm tra.

Giá trị thực tế đến từ **giữ nguyên hành vi** khi chuyển đổi:

- `null` và các kiểu không khớp vẫn phải đi đúng nhánh.
- Các subtype/interface và thứ tự kiểm tra phải được bảo toàn.
- Điều kiện nghiệp vụ sau khi khớp kiểu vẫn cần kiểm tra riêng.
- Flow scoping với `&&` và guard clause phải được compiler chứng minh hợp lệ.
- Cast trực tiếp có thể cố ý ném lỗi; pattern chỉ giúp kiểm tra kiểu, không tự thay hợp đồng ngoại lệ.
- Mã Java 17 có thể dùng type patterns mà chưa cần record deconstruction hoặc pattern switch Java 21.

Hãy coi chương trình 25 checks trong mục 8 là **bài thực hành hồi quy**: chạy để thấy cả hai cách viết cho cùng expected ở các ca đã chọn, rồi áp dụng kỹ thuật tương tự cho mã thật và mở rộng ma trận test theo nghiệp vụ.

**Tài liệu tham khảo:**

- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [Java SE 17 Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
