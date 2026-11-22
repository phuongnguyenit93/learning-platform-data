# Khả năng chắc chắn khớp sau return hoặc throw — phạm vi biến mẫu instanceof

## Mục tiêu học tập

Trong Java, type pattern của `instanceof` có thể vừa kiểm tra kiểu runtime, vừa ràng buộc một biến có kiểu cụ thể: `value instanceof String text`. Nhưng **khai báo được biến không đồng nghĩa biến đó được sử dụng ở mọi dòng phía sau**. Phạm vi của pattern variable tuân theo **luồng điều khiển** (*flow scoping*): chỉ tại những điểm mà compiler biết chắc pattern đã khớp (*definitely matched*), tên biến mới được phép xuất hiện.

Bài này tập trung vào một trường hợp rất hữu ích: sau câu `if` kiểm tra **điều kiện không khớp**, nếu nhánh này chắc chắn `return` hoặc `throw`, thì các lệnh phía sau `if` chỉ có thể được chạy khi pattern **đã khớp**. Bạn sẽ hiểu cơ chế, áp dụng guard clause, phân biệt nhánh thực sự không thể kết thúc bình thường với nhánh có thể đi tiếp, và nhận diện các lỗi biên dịch liên quan.

Kiến thức ở đây dựa trên cú pháp **pattern matching for `instanceof` chính thức từ Java 16**, vẫn áp dụng trong Java hiện đại. Mã thực hành dùng **JDK 17 trở lên**, không cần `--enable-preview` hoặc cơ chế preview đã cũ của Java 14.

## 1. Mẫu instanceof tạo ra bằng chứng khớp kiểu

Cách viết truyền thống trong một method:

```java
Object value = "Java";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Cách viết dùng type pattern:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Biểu thức `value instanceof String text` làm các việc:

1. Kiểm tra tham chiếu runtime có khớp kiểu `String` hay không.
2. Khi khớp, ràng buộc tên `text` với chính tham chiếu đã kiểm tra, dưới kiểu `String`.
3. Cho phép dùng `text` tại những vị trí mà phân tích luồng chắc chắn biết mẫu đã khớp, không cần thêm `(String) value`.

Nếu `value` là `null` hoặc một đối tượng không phải `String`, phép thử `instanceof String` trả `false`. Không có biến `text` hợp lệ trên đường sai. Việc pattern khớp **không tự làm sạch chuỗi, kiểm tra chuỗi rỗng, sao chép đối tượng hay chuyển đổi String thành số**; các bước đó là trách nhiệm của code nghiệp vụ.

## 2. Vì sao sau if bình thường chưa chắc dùng được biến?

Xem đoạn **cố ý sai khi biên dịch**:

```java
static int broken(Object input) {
    if (input instanceof String text) {
        System.out.println("matched");
    }
    return text.length(); // ERROR: text is not in scope here.
}
```

Có hai đường tới câu `return text.length()`:

- Input là `String`: pattern khớp, nhánh `if` chạy, nhưng sau đó chương trình tiếp tục.
- Input không phải `String`: nhánh `if` bị bỏ qua và chương trình **vẫn tiếp tục**.

Vì tồn tại đường thứ hai, compiler không thể kết luận `text` đã được ràng buộc. Việc `text` “đã được khai báo” ở phần điều kiện không đủ; **vị trí sử dụng phải được bảo đảm bởi mọi đường chạy có thể đến đó**.

Hình dung bằng luồng:

```text
input instanceof String text ?
           |
        +--+--+
      true   false
        |      |
      if-body  |
        |      |
        +---+--+
            |
      return text.length()
      (KHÔNG AN TOÀN)
```

Giải pháp đơn giản là chỉ dùng `text` trong nhánh đúng, hoặc **loại trừ nhánh sai** trước khi dùng biến ở phần còn lại của method.

## 3. Guard clause với return: nhánh sai không thể đi tiếp

Đây là cú pháp **hợp lệ**, vì câu `return` trực tiếp chấm dứt lời gọi method trên đường pattern không khớp:

```java
static String trimOrDash(Object input) {
    if (!(input instanceof String text)) {
        return "-";
    }

    // Chỉ đến đây khi input instanceof String text đã đúng.
    return text.strip();
}
```

Phân tích từng bước:

1. `input instanceof String text` khớp nếu input là `String`.
2. Toán tử `!` đảo kết quả: `!(...)` **đúng** khi pattern gốc **không khớp**.
3. Nếu nhánh không khớp được chọn, `return "-"` thoát khỏi method ngay; không có đường nào từ nhánh này tới dòng `text.strip()`.
4. Nếu điều kiện phủ định sai, tức pattern gốc đúng, chương trình bỏ qua nhánh `if` và đi thẳng tới dòng cuối.
5. Vì mọi đường có thể đến `return text.strip()` đều đã khớp, compiler cho phép dùng `text` **sau câu `if`**, ngay trong phần còn lại của block chứa nó.

Ví dụ: `trimOrDash("  A  ")` trả `"A"`; `trimOrDash(7)` và `trimOrDash(null)` trả `"-"`. Với chuỗi toàn khoảng trắng, `strip()` trả chuỗi rỗng; ở đây không có quy tắc bổ sung để đổi chuỗi rỗng thành `"-"`.

### Điều kiện cốt lõi theo JLS

Trong trường hợp `if (e) S` **không có `else`**, pattern variable có thể được đưa vào phạm vi sau cả câu `if` khi:

- Biến được biểu thức điều kiện `e` giới thiệu trên **đường điều kiện sai** (ví dụ phủ định `!(input instanceof String text)`); và
- Câu lệnh/thân nhánh `S` **không thể hoàn thành bình thường** (*cannot complete normally*), chẳng hạn chỉ có `return` hợp lệ hoặc `throw` trực tiếp trên tất cả đường của nhánh.

Sự kết hợp này là chìa khóa: nếu nhánh sai có khả năng đi tiếp, compiler sẽ không công nhận `text` ở đoạn sau `if`. Nếu phủ định bị bỏ đi, `return` chỉ thoát trên đường **khớp**, và đường **không khớp** vẫn đi tiếp — biến cũng không được dùng phía sau.

## 4. Guard clause với throw: chỉ giá trị hợp lệ mới đi tiếp

`throw` trực tiếp cũng khiến nhánh kiểm tra sai không thể hoàn thành bình thường:

```java
static int requireTextLength(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("expected String");
    }
    return text.length();
}
```

Khi input là `"abc"`, pattern khớp và trả `3`. Khi input là `42` hoặc `null`, nhánh sai ném `IllegalArgumentException`; dòng `return text.length()` không được thực thi.

Khác biệt giữa hai chính sách:

| Guard | Khi không khớp | Khi khớp |
| --- | --- | --- |
| `return defaultValue;` | Method trả giá trị mặc định | Chạy tiếp với pattern variable có kiểu cụ thể |
| `throw new IllegalArgumentException(...);` | Method thất bại bằng ngoại lệ | Chạy tiếp với pattern variable có kiểu cụ thể |

Cả hai cùng bảo đảm **đường không khớp không thể chạy tiếp**. Chọn `return` khi đầu vào sai được coi là trường hợp thông thường có fallback hợp lệ; chọn `throw` khi đầu vào sai vi phạm contract.

Một ngoại lệ runtime chưa được bắt tại đây làm method kết thúc đột ngột. Nếu có `catch` ở nơi gọi method, ngoại lệ có thể được xử lý **ở nơi gọi**; điều đó không khiến dòng phía sau `throw` trong method này được thực thi.

## 5. Sơ đồ so sánh: return/throw đúng và những đường không đủ bảo đảm

### 5.1. Đường hợp lệ: phủ định + chấm dứt nhánh sai

```text
 !(input instanceof String text)
                |
            +---+---+
           true   false
            |       |
          return    pattern đã khớp
       hoặc throw     |
            X         v
                   text.strip()
                   (HỢP LỆ)
```

Dấu `X` đánh dấu đường đã kết thúc, không tới lệnh sau `if`.

### 5.2. Sai: return nằm trên đường đã khớp

```java
// CỐ Ý SAI:
static int wrongDirection(Object input) {
    if (input instanceof String text) {
        return text.length();
    }
    return text.length(); // ERROR.
}
```

Khi input **không phải String**, `if` sai, method vẫn đi tới dòng thứ hai; `text` chưa được ràng buộc. Việc nhánh khớp `return` không giúp ích cho đường không khớp.

### 5.3. Sai: nhánh phủ định có thể hoàn thành bình thường

```java
// CỐ Ý SAI:
static int maybeContinue(Object input, boolean strict) {
    if (!(input instanceof String text)) {
        if (strict) {
            throw new IllegalArgumentException("expected String");
        }
        // strict=false: vẫn có đường đi tiếp.
    }
    return text.length(); // ERROR.
}
```

Không đủ khi *một phần* nhánh sai có `throw` hoặc `return`. Compiler phải có bằng chứng **mọi đường** mà nhánh kiểm tra sai thực hiện đều không kết thúc bình thường.

Phiên bản sửa có thể viết:

```java
static int alwaysReject(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("expected String");
    }
    return text.length();
}
```

### 5.4. Sai: gọi phương thức vốn luôn throw nhưng compiler không chứng minh được

```java
// Ví dụ CỐ Ý SAI:
static void fail() {
    throw new IllegalArgumentException("rejected");
}

static int unsafe(Object input) {
    if (!(input instanceof String text)) {
        fail(); // Chỉ là một lời gọi method có kiểu trả về void.
    }
    return text.length(); // ERROR: nhánh if có thể hoàn thành bình thường.
}
```

Con người đọc thân `fail()` biết nó luôn ném ngoại lệ. Nhưng đối với quy tắc **khả năng hoàn thành bình thường** tại vị trí này, một *method invocation statement* không được xem là không thể hoàn thành bình thường chỉ vì bạn biết hoặc kỳ vọng phương thức được gọi luôn ném. Compiler không sử dụng phân tích toàn chương trình kiểu “hàm này luôn throw” để đưa pattern variable ra ngoài `if`.

Hãy dùng `throw` trực tiếp, dùng `return` thích hợp, hoặc tái cấu trúc điều kiện để phạm vi đúng theo quy tắc ngôn ngữ. Ví dụ nếu muốn tận dụng helper tạo đối tượng ngoại lệ, có thể dùng `throw reject(input);` khi helper **trả về exception**:

```java
static IllegalArgumentException reject(Object value) {
    return new IllegalArgumentException("expected String: " + value);
}

static int safe(Object input) {
    if (!(input instanceof String text)) {
        throw reject(input); // Chính statement này là throw.
    }
    return text.length();
}
```

Hai method trong đoạn sửa **chỉ là đoạn mã thuộc cùng một class**, không có `main` độc lập. Lưu ý nếu helper `reject` tự ném trước khi trả về, đường sai vẫn kết thúc đột ngột; dù thế quy tắc phạm vi được xác lập bởi câu `throw` tường minh, không phụ thuộc đoán hành vi nội bộ của helper.

## 6. Khi không có phủ định nhưng else chắc chắn throw

Cấu trúc `if/else` cũng có thể cho phép sử dụng biến sau câu điều kiện:

```java
static String lowercaseOrFail(Object input) {
    if (input instanceof String text) {
        // Đường khớp có thể hoàn thành bình thường.
    } else {
        throw new IllegalArgumentException("String required");
    }

    // Đường không khớp đã throw, nên text chắc chắn khớp.
    return text.toLowerCase(java.util.Locale.ROOT);
}
```

Nhánh `then` chạy khi pattern khớp, có thể đi tiếp; nhánh `else` không khớp nhưng **không thể đi tiếp** do `throw`. Sau `if/else`, mọi đường còn sống đều là đường có biến `text` được ràng buộc.

Đây là một lựa chọn đúng, nhưng nếu nhánh `then` không cần hành động gì thì dạng phủ định + guard clause ở mục 3–4 thường ngắn và rõ hơn.

### Nếu else có return thay vì throw?

```java
static String uppercaseOrDash(Object input) {
    if (input instanceof String text) {
        // Đường thành công đi tiếp.
    } else {
        return "-";
    }
    return text.toUpperCase(java.util.Locale.ROOT);
}
```

Cũng hợp lệ: nhánh không khớp `return` ra khỏi method. **Không có giới hạn bắt buộc** rằng phải viết phủ định `!` để có flow scoping sau một câu `if`; điều quyết định là cấu trúc **đường thành công đi tiếp, đường thất bại kết thúc**.

Lưu ý các đoạn ví dụ nhỏ chỉ độc lập ở mức phương thức: đặt chúng trong một class trước khi biên dịch. Ví dụ đầy đủ có `main` nằm ở mục 8.

## 7. Kết hợp kiểm tra kiểu với validation sau guard

Pattern matching xác nhận **kiểu**, không tự xác nhận các điều kiện nghiệp vụ như chuỗi không trắng hoặc có độ dài tối thiểu.

### 7.1. Dùng hai guard clauses

```java
static String requireCode(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("not a String");
    }
    String code = text.strip();
    if (code.isBlank()) {
        throw new IllegalArgumentException("blank code");
    }
    return code;
}
```

- Guard thứ nhất khiến `text` chắc chắn đã ràng buộc ở phần sau.
- Guard thứ hai kiểm tra nội dung *sau* khi kiểu đã được xác nhận.
- Đây là cách dễ mở rộng nếu mỗi bước validation cần thông điệp lỗi riêng.

### 7.2. Dùng && trong type pattern, rồi phủ định cả điều kiện

```java
static int lengthAtLeastThree(Object input) {
    if (!(input instanceof String text && text.length() >= 3)) {
        throw new IllegalArgumentException("length must be >= 3");
    }
    return text.length();
}
```

`&&` chỉ gọi `text.length()` khi `input instanceof String text` đúng. Nếu pattern sai hoặc độ dài nhỏ hơn 3, phủ định đúng và guard ném ngoại lệ. Khi chương trình đến dòng cuối, biểu thức `instanceof` đã khớp chắc chắn và điều kiện độ dài cũng đã thỏa.

Nếu input là `null` hoặc kiểu khác, vế phải `text.length()` không được đánh giá. Đây là lợi ích của **short-circuit evaluation** và bằng chứng khớp kiểu theo luồng.

### 7.3. Cấu trúc || có thể đúng khi biến đã được bảo đảm ở vế phải

```java
static String nonBlank(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("expected nonblank String");
    }
    return text.strip();
}
```

Điều kiện đầu tiên là `!(input instanceof String text)`. Với `||`, chỉ khi vế trái **sai**, Java mới đánh giá `text.isBlank()`. Điều đó chứng minh pattern gốc **đúng** trước khi gọi phương thức trên `text`.

Nếu cả biểu thức `||` **sai** và nhánh throw bị bỏ qua, `text` đã khớp và không trắng, nên `return text.strip()` hợp lệ.

So sánh với cách viết **cố ý sai**:

```java
// CỐ Ý SAI:
if (input instanceof String text || text.isBlank()) {
    System.out.println("ok");
}
```

Ở ví dụ sai, vế phải được đánh giá **khi pattern gốc không khớp**. Không có bằng chứng `text` tồn tại, nên compiler từ chối.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ ví dụ sau thành **`PatternGuardFlowDemo.java`**. Chương trình sử dụng `return`, `throw`, `else` và điều kiện ngắn mạch để làm rõ chính xác khi nào pattern variable có phạm vi.

```java
import java.util.Locale;

public final class PatternGuardFlowDemo {
    private PatternGuardFlowDemo() {
    }

    static String normalize(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_TEXT";
        }

        String clean = text.strip();
        return clean.isEmpty()
                ? "BLANK"
                : "TEXT:" + clean.toUpperCase(Locale.ROOT);
    }

    static int requireLength(Object input) {
        if (!(input instanceof String text)) {
            throw new IllegalArgumentException("expected String");
        }
        return text.length();
    }

    static String requireNonBlank(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "expected nonblank String");
        }
        return text.strip();
    }

    static String lowercaseViaElse(Object input) {
        if (input instanceof String text) {
            // Success path can finish normally.
        } else {
            throw new IllegalArgumentException("String required");
        }
        return text.toLowerCase(Locale.ROOT);
    }

    static int requireMinLength(Object input) {
        if (!(input instanceof String text && text.length() >= 3)) {
            throw new IllegalArgumentException("min length 3");
        }
        return text.length();
    }

    private static void check(boolean passed, String label) {
        if (!passed) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(normalize("  Java  ").equals("TEXT:JAVA"),
                "normalize String");
        check(normalize(Integer.valueOf(7)).equals("NOT_TEXT"),
                "normalize other type");
        check(normalize(null).equals("NOT_TEXT"),
                "normalize null");
        check(normalize("  ").equals("BLANK"),
                "normalize blank");

        System.out.println("normalize text = " + normalize("  Java  "));
        System.out.println("normalize number = " + normalize(7));
        System.out.println("normalize null = " + normalize(null));
        System.out.println("normalize blank = " + normalize("  "));

        check(requireLength("abc") == 3, "length");
        System.out.println("length = " + requireLength("abc"));

        try {
            requireLength(7);
            throw new AssertionError("must reject non-String");
        } catch (IllegalArgumentException ex) {
            System.out.println("bad type = " + ex.getMessage());
        }

        check(requireNonBlank("  Hi  ").equals("Hi"),
                "nonblank String");
        System.out.println(
                "nonblank = " + requireNonBlank("  Hi  "));

        try {
            requireNonBlank("   ");
            throw new AssertionError("must reject blank String");
        } catch (IllegalArgumentException ex) {
            System.out.println("bad blank = " + ex.getMessage());
        }

        check(lowercaseViaElse("ALPHA").equals("alpha"),
                "else matching");
        System.out.println("else = " + lowercaseViaElse("ALPHA"));

        try {
            lowercaseViaElse(null);
            throw new AssertionError("must reject null");
        } catch (IllegalArgumentException ex) {
            System.out.println("bad else = " + ex.getMessage());
        }

        check(requireMinLength("Java") == 4, "min length");
        System.out.println("min length = " + requireMinLength("Java"));

        try {
            requireMinLength("Hi");
            throw new AssertionError("must reject short String");
        } catch (IllegalArgumentException ex) {
            System.out.println("bad length = " + ex.getMessage());
        }
    }
}
```

### Lệnh biên dịch và chạy

Trong thư mục chứa `PatternGuardFlowDemo.java`, dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 PatternGuardFlowDemo.java
java PatternGuardFlowDemo
```

**Stdout mong đợi chính xác theo thứ tự:**

```text
normalize text = TEXT:JAVA
normalize number = NOT_TEXT
normalize null = NOT_TEXT
normalize blank = BLANK
length = 3
bad type = expected String
nonblank = Hi
bad blank = expected nonblank String
else = alpha
bad else = String required
min length = 4
bad length = min length 3
```

### Giải thích các đường chạy quan trọng

1. `normalize` dùng **phủ định + return**. Sau guard, `text` chắc chắn là `String`. Với `Integer` hoặc `null`, method đã trả `NOT_TEXT`, không thể chạy vào `strip()`.
2. `requireLength` dùng **phủ định + throw**. Với `"abc"`, trả `3`; với `7`, ném exception trước khi có thể sử dụng biến chưa khớp.
3. `requireNonBlank` kiểm tra bằng `||` đúng hướng: vế phải `text.isBlank()` chỉ chạy khi đầu vào là `String`. Nếu bất kỳ kiểm tra nào thất bại, nhánh `throw` chấm dứt method.
4. `lowercaseViaElse` minh họa `if/else`: nhánh không khớp `throw`, nhánh khớp có thể hoàn thành bình thường; sau câu `if`, `text` được phép dùng.
5. `requireMinLength` kiểm tra `instanceof` kết hợp `&&`, phủ định toàn biểu thức, rồi `throw` nếu không đạt. Khi đến `return text.length()`, compiler có bằng chứng kiểu đã khớp và độ dài đạt yêu cầu.
6. Các lệnh `check(...)` ném `AssertionError` nếu kết quả hợp lệ sai. Các `try/catch` dùng kiểm tra rằng lỗi thực tế là `IllegalArgumentException` được mong đợi; nếu một ca sai bất ngờ không ném ngoại lệ, chương trình ném `AssertionError` thay vì âm thầm cho qua.

**Lưu ý phiên bản:** `--release 17` áp dụng cú pháp và API Java 17 khi biên dịch bằng JDK hỗ trợ cờ đó. Để xác minh runtime tại dự án, chạy bằng `java` từ runtime mục tiêu, không chỉ nhìn vào lệnh biên dịch.

## 9. Bảng kiểm “có chắc chắn khớp sau if?”

| Cấu trúc | Dùng biến sau if? | Vì sao |
| --- | --- | --- |
| `if (o instanceof String s) { ... }` | **Không được mặc định** | Nhánh điều kiện sai có thể đi tiếp |
| `if (!(o instanceof String s)) return "-";` | **Có** | Đường không khớp chấm dứt bằng `return` |
| `if (!(o instanceof String s)) throw new IllegalArgumentException();` | **Có** | Đường không khớp chấm dứt bằng `throw` |
| `if (!(o instanceof String s)) { if (strict) throw ...; }` | **Không** | Có đường `strict == false` đi tiếp |
| `if (!(o instanceof String s)) reject();` | **Không mặc định** | Lời gọi `void` có thể hoàn thành bình thường theo phân tích compiler |
| `if (o instanceof String s) return s;` | **Không** | Đường không khớp mới là đường đi tiếp |
| `if (o instanceof String s) { } else { throw ...; }` | **Có** | Nhánh khớp đi tiếp, nhánh sai chấm dứt |
| `if (!(o instanceof String s) || s.isBlank()) throw ...;` | **Có** | RHS chỉ được xét khi pattern khớp; thất bại sẽ throw |
| `if (!(o instanceof String s && s.length() >= 3)) throw ...;` | **Có** | Nếu đi tiếp, toàn điều kiện gốc đúng |

Trong bảng, dấu `...` là chỗ rút gọn minh họa. Khi kiểm tra một chương trình thật, cần xét toàn bộ nội dung nhánh; một nhánh có thêm điều kiện hoặc đường đi tiếp có thể thay đổi kết quả phân tích. Ví dụ `return` trong một `if` con mà các đường còn lại rơi ra cuối block **không đủ** để bảo đảm.

## 10. Lưu ý tinh tế về “không thể hoàn thành bình thường”

### 10.1. Compiler chứng minh theo cấu trúc cú pháp và quy tắc JLS

Một lời gọi hàm mà bạn *biết trong thực tế* luôn ném ngoại lệ vẫn không đồng nghĩa với một câu `throw` tường minh khi kiểm tra phạm vi pattern variable. Compiler không phân tích mọi implementation của các method được gọi để suy ra chúng không bao giờ trả về.

Tương tự, lời gọi `System.exit(...)` không phải cách thay thế đáng tin cho `return`/`throw` nhằm mở rộng phạm vi pattern variable. Nó là lời gọi method; đừng dùng cả trong logic kiểm chứng này vì nó dừng quá trình Java và gây khó test.

### 10.2. Catch bên trong nhánh có thể khiến đường sai đi tiếp

```java
// MÃ CỐ Ý SAI:
static int caughtInside(Object input) {
    if (!(input instanceof String text)) {
        try {
            throw new IllegalArgumentException("invalid");
        } catch (IllegalArgumentException ex) {
            System.out.println("ignored");
        }
    }
    return text.length(); // ERROR: nhánh sai có thể kết thúc bình thường.
}
```

Mặc dù có `throw`, ngoại lệ đã bị bắt **trong chính nhánh đó** và code đi tới cuối block; vì vậy compiler không có bằng chứng rằng đường không khớp đã kết thúc.

Ngược lại, `try/catch` ở **nơi gọi method** không khiến nhánh `throw` bên trong method `requireLength` quay lại lệnh sau guard. Các lời gọi và phạm vi điều khiển phải được xét đúng chỗ.

### 10.3. Phạm vi không vượt qua block bao quanh

```java
static void insideBlock(Object input) {
    {
        if (!(input instanceof String text)) {
            return;
        }
        System.out.println(text.length()); // Hợp lệ.
    }
    // text không còn trong scope ở đây.
}
```

Dù có `return` từ đường không khớp, pattern variable không biến thành biến toàn cục. Sau khi kết thúc block chứa câu `if`, tên `text` không thể tiếp tục được dùng bên ngoài phạm vi mà quy tắc `6.3` cấp cho nó.

### 10.4. Return hoặc throw không tự làm đầu vào hợp lệ

`input instanceof String text` chỉ xác nhận đối tượng runtime là một `String` khác null. Chuỗi `""` và `"   "` **vẫn khớp** với pattern, nên nếu contract yêu cầu không rỗng/trắng, cần thêm validation. Với generic container, một `List<?>` khớp không chứng minh các phần tử đều là `String`.

Không biến flow scoping thành lý do bỏ qua validation, dữ liệu biên, hoặc xử lý ngoại lệ đúng theo API.

### 10.5. Khác biệt với definite assignment của biến thường

`definitely matched` áp dụng cho **biến được khai báo qua pattern**; nó có liên hệ về ý tưởng nhưng không đồng nhất hoàn toàn với **definite assignment** của biến cục bộ thông thường. Ví dụ compiler có thể cho phép pattern variable xuất hiện *sau* một câu `if` dù văn bản khai báo ban đầu nằm trong biểu thức điều kiện, bởi vì các quy tắc flow scoping cung cấp bằng chứng trên tất cả đường đến vị trí sử dụng.

## 11. Lỗi thường gặp và hướng sửa

### Lỗi: return trên đường khớp, vẫn muốn dùng biến ở đường sai

```java
// CỐ Ý SAI:
if (input instanceof String s) {
    return s;
}
System.out.println(s);
```

Khi `input` không phải `String`, method vẫn tiếp tục mà chưa có `s`. Hãy dùng `if (!(input instanceof String s)) return ...;` nếu bạn muốn xử lý `s` trong phần còn lại.

### Lỗi: không xử lý toàn bộ đường thất bại

```java
// CỐ Ý SAI:
if (!(input instanceof String s)) {
    if (flag) {
        return "-";
    }
}
return s.strip();
```

Nếu `flag` sai, đường không khớp vẫn tới dòng cuối. Phải bảo đảm **mọi nhánh** của điều kiện thất bại kết thúc hoặc xử lý được loại đầu vào không khớp.

### Lỗi: dùng return bên trong lambda và nghĩ đã thoát method ngoài

```java
// CỐ Ý SAI:
if (!(input instanceof String s)) {
    Runnable task = () -> {
        return; // Chỉ trở về từ Runnable.run() của lambda.
    };
    task.run(); // Method ngoài vẫn có thể chạy tiếp.
}
return s.strip();
```

Lệnh `return` trong lambda chỉ kết thúc **lambda**, không phải method đang chứa lambda. Code ở nhánh sai vẫn có thể hoàn thành bình thường, nên không được dùng `s` ở dòng sau `if`.

### Lỗi: gọi helper throw mà không có câu throw tại đây

```java
// CỐ Ý SAI theo flow scoping:
if (!(input instanceof String s)) {
    alwaysThrows(); // Compiler không suy ra call này không bao giờ trả về.
}
return s.strip();
```

Dùng câu `throw` tường minh trong nhánh, hoặc chuyển kết quả helper thành giá trị thích hợp rồi `return`. Đừng dựa trên suy đoán về implementation của helper để làm thay đổi quy tắc phạm vi biến.

### Lỗi: lẫn lộn guard với phép phủ định

```java
if (!(input instanceof String s)) {
    return "INVALID";
}
return s.strip(); // Hợp lệ.
```

Mẫu này khác hoàn toàn với:

```java
// CỐ Ý SAI:
if (input instanceof String s) {
    return "VALID";
}
return s.strip();
```

Đảo dấu phủ định nhưng giữ vị trí `return` sẽ đảo luôn đường nào có thể tiếp tục; đây là lỗi rất dễ mắc khi refactor code.

## 12. Bài thực hành có thể tự kiểm chứng

Tự viết `static String normalizeCode(Object input)` theo yêu cầu:

1. Nếu không phải `String` (kể cả `null`), trả `"INVALID_TYPE"` bằng **guard clause với `return`**.
2. Nếu đúng kiểu, dùng pattern variable phía **sau** guard, gọi `strip()`; nếu rỗng, ném `IllegalArgumentException("blank code")`.
3. Nếu chuỗi sau `strip()` ngắn hơn 3 ký tự, ném `IllegalArgumentException("code too short")`.
4. Nếu hợp lệ, trả chữ hoa bằng `toUpperCase(Locale.ROOT)`.
5. Không dùng cast `(String)`; để compiler chứng minh phạm vi pattern variable.

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `"  java  "` | `"JAVA"` |
| `"ab"` | `IllegalArgumentException("code too short")` |
| `""`, `"  "` | `IllegalArgumentException("blank code")` |
| `Integer.valueOf(7)`, `new Object()` | `"INVALID_TYPE"` |
| `null` | `"INVALID_TYPE"` |

Tiếp theo, viết `static int lengthRequired(Object input)` theo **guard clause với `throw`**, dùng `if (!(input instanceof String s)) throw new IllegalArgumentException("expected String");` rồi `return s.length();`.

Cuối cùng, thử các thay đổi có chủ ý:

- Bỏ `!` nhưng vẫn `throw`/`return` ở nhánh khớp rồi dùng `s` sau `if`: dự đoán lỗi scope.
- Đưa `throw` vào nhánh `if (flag)` con, để nhánh khác rơi ra cuối block: compiler có thể chứng minh pattern chắc chắn khớp nữa không?
- Thay `throw new IllegalArgumentException(...)` bằng lời gọi `fail()` mà thân `fail` luôn throw: lý giải vì sao cách này không thay thế quy tắc *cannot complete normally* của statement.
- Dùng `if (!(input instanceof String s) || s.isBlank()) throw ...;`: giải thích vì sao vế phải `||` và dòng sau `if` dùng được `s`.
- Đặt một block `{ ... }` bao quanh guard, rồi thử dùng `s` ở ngoài block đó: kiểm tra giới hạn phạm vi theo block.

Một bài giải đạt yêu cầu phải chứng minh được **đường chạy nào đến vị trí dùng biến, đường không khớp đã kết thúc bằng gì, có nhánh nào vẫn có thể hoàn thành bình thường không**, thay vì chỉ học thuộc cú pháp `return`/`throw`.

## Tham khảo

- [Java Language Specification (Java SE 26), `6.3 và `6.3.2.2 — Scope of a Declaration, if Statements](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-6.html#jls-6.3.2.2): điều kiện flow scoping, đặc biệt quy tắc nhánh không thể hoàn thành bình thường.
- [Java Language Specification (Java SE 26), `14.1 và `14.22 — Normal/Abrupt Completion, Unreachable Statements](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html): cơ chế return/throw và khả năng hoàn thành bình thường.
- [Oracle Java SE 17 — Pattern Matching for the instanceof Operator](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof-operator.html): ví dụ type pattern và guard clause ổn định trên Java 17.

**Ghi nhớ:** Không phải chỉ vì bạn viết `return` hoặc `throw` đâu đó trong code mà pattern variable tự được mở rộng phạm vi. Chỉ khi **mọi đường không khớp đều không thể đi tiếp đến vị trí sử dụng**, compiler mới biết chắc biến đã được ràng buộc. Phủ định `instanceof` + guard `return`/`throw` là cách đơn giản, rõ ràng và vẫn đúng trong Java hiện đại.