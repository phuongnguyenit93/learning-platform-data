# Phân biệt `when` với điều kiện trong thân `case` của Java pattern switch

**Chủ đề:** Java Core Pattern Matching → *Guard when*. Bài dùng cú pháp **Java 21** (JEP 441: *Pattern Matching for switch* đã ổn định); trọng tâm là sự khác nhau giữa **điều kiện bảo vệ một nhãn `case`** bằng `when` và **câu lệnh `if` chạy bên trong nhánh `case`**. Ví dụ chính là chương trình hoàn chỉnh có thể biên dịch bằng JDK 21 trở lên, không cần `--enable-preview`.

> **Ý chính:** `when` tham gia **quá trình quyết định nhãn `case` nào được chọn**. `if` trong thân `case` chỉ tham gia **xử lý sau khi nhãn đã được chọn**. Khi guard `when` trả về `false`, Java có thể xét nhãn `case` tiếp theo. Khi `if` trong nhánh trả về `false`, Java **không tự quay lại tìm một `case` khác**.

## 1. Bối cảnh: pattern matching for switch hoạt động ra sao?

Trước tiên, xét `switch` expression trên một giá trị kiểu `Object`:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> "text: " + s;
        case Integer n -> "number: " + n;
        default -> "other";
    };
}
```

Một nhãn như `case String s` chứa **type pattern**. Khi `input` là `String` khác null, pattern khớp và biến `s` được khởi tạo; chương trình xử lý nhánh đó. Một `switch` với các nhánh mũi tên `->` chọn một nhánh phù hợp rồi thực thi nhánh ấy, không *fall-through* sang các nhánh sau.

Đôi khi chỉ biết “đây là `String`” chưa đủ. Ta còn cần phân loại chuỗi trắng, chuỗi dài hay chuỗi ngắn; hoặc cùng là `Integer` nhưng giá trị âm hay không âm. Java 21 cho phép đặt điều kiện ngay sau pattern:

```java
case String s when s.isBlank() -> "blank";
```

`String s` là **pattern**, còn `s.isBlank()` là **guard expression**. Cả hai phải thành công để nhãn này áp dụng.

## 2. `when` là điều kiện của nhãn, không phải thân nhánh

Đọc nhãn:

```java
case String s when s.length() >= 5 -> "long string";
```

Theo trình tự logic:

1. Java đã đánh giá selector expression của `switch` để nhận một giá trị.
2. Java kiểm tra giá trị ấy có **khớp pattern `String s`** không.
3. Chỉ khi pattern khớp, Java mới đánh giá **guard `s.length() >= 5`**. Tại đây `s` đã được khởi tạo và an toàn về kiểu.
4. Nếu guard cho kết quả `true`, nhãn này **áp dụng** và Java chạy phần sau `->`.
5. Nếu guard cho kết quả `false`, nhãn này **không áp dụng**. Java tiếp tục quá trình tìm nhãn phù hợp khác trong `switch`.

Điểm ở bước 5 là khác biệt cốt lõi. Guard không “chọn nhánh rồi chạy một kiểm tra bên trong”; guard làm quyết định **chọn hay không chọn nhãn hiện tại**.

Ví dụ:

```java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long";
        case String s -> "short";
        case null -> "null";
        default -> "other";
    };
}
```

Kết quả dự đoán:

| Đầu vào | Các bước đáng chú ý | Kết quả |
| --- | --- | --- |
| `"   "` | Pattern String khớp; guard `isBlank()` đúng | `blank` |
| `"Java"` | Guard blank sai; guard độ dài ≥ 5 sai; đến String không guard | `short` |
| `"Pattern"` | Guard blank sai; guard độ dài ≥ 5 đúng | `long` |
| `42` | Không khớp String; đến `default` | `other` |
| `null` | Nhãn `case null` xử lý selector null | `null` |

Đặt các nhãn **cụ thể có guard trước**, cuối cùng mới đến nhãn `String s` tổng quát, giúp các phân loại được xét đúng thứ tự.

### Guard chỉ chạy khi pattern khớp

Với selector là `Integer`, câu `case String s when s.length() > 4` không gọi `s.length()`. Pattern đã không khớp nên guard không được đánh giá. Tránh diễn giải sai rằng Java chạy mọi điều kiện `when` cho mọi loại đối tượng.

## 3. `if` trong thân `case` chỉ chạy sau khi case được chọn

Giờ đưa điều kiện vào thân một nhánh:

```java
static String bodyCheck(Object input) {
    return switch (input) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            yield "nonblank";
        }
        case null -> "null";
        default -> "other";
    };
}
```

Ở đây, **chỉ cần** `input` khớp `String s` thì nhánh `case String s` đã được chọn. Sau đó `if (s.isBlank())` được thực thi **bên trong nhánh**.

Nếu `s.isBlank()` trả về `false`, Java chạy các lệnh tiếp theo **trong cùng nhánh**. Nó không tự đi xuống `case null` hoặc `default`, không xét lại các pattern khác.

Trong `switch` expression, dùng `yield` để trả giá trị từ nhánh có thân là block. `return` bên trong một switch expression thường không dùng để trả giá trị của riêng expression; khi muốn tạo giá trị nhánh, `yield` là cú pháp đúng.

### Sai lầm thường gặp: tưởng `if` sai sẽ thử nhãn tiếp

Giả sử cần ưu tiên chuỗi bắt đầu bằng `"A"`, còn các `CharSequence` khác được xử lý chung.

**Cách dùng guard đúng mục tiêu:**

```java
static String guardFallback(Object input) {
    return switch (input) {
        case String s when s.startsWith("A") -> "starts-with-A";
        case CharSequence chars -> "general sequence";
        case null -> "null";
        default -> "other";
    };
}
```

- `guardFallback("Alpha")` → `starts-with-A`.
- `guardFallback("Beta")` → `general sequence`: pattern `String` khớp nhưng guard sai, nên Java tiếp tục tới `CharSequence`.
- `guardFallback(new StringBuilder("Hi"))` → `general sequence`: không phải String, nhưng là CharSequence.

**Cách dùng `if` trong thân không tạo fallback sang case khác:**

```java
static String bodyDoesNotFallback(Object input) {
    return switch (input) {
        case String s -> {
            if (s.startsWith("A")) {
                yield "starts-with-A";
            }
            yield "String branch already selected";
        }
        case CharSequence chars -> "general sequence";
        case null -> "null";
        default -> "other";
    };
}
```

`bodyDoesNotFallback("Beta")` trả về **`String branch already selected`**, **không phải** `general sequence`. Nhãn String được chọn ngay khi pattern khớp, trước khi `if` bên trong bắt đầu chạy.

**Kết luận:** Khi mục tiêu là *“nếu điều kiện bổ sung sai, thử nhãn `case` kế tiếp”*, dùng `when`. Khi mục tiêu là *“đã chọn nhánh này; bên trong nhánh có nhiều bước xử lý riêng”*, dùng `if`.

## 4. So sánh bản chất và khả năng biểu đạt

| Khía cạnh | `case Pattern when condition ->` | `case Pattern -> { if (condition) ... }` |
| --- | --- | --- |
| Thời điểm kiểm tra | Trong giai đoạn xác định nhãn áp dụng | Sau khi nhãn được chọn |
| Pattern phải khớp trước không? | Có; sau đó mới kiểm tra guard | Có; thân nhánh chỉ chạy sau khi khớp |
| Condition sai thì sao? | Nhãn hiện tại không áp dụng; tìm nhãn tiếp theo | Tiếp tục thực thi thân nhánh; không tự thử nhãn khác |
| Có dùng được pattern variable không? | Có, trong phạm vi guard | Có, trong thân nhánh |
| Phân loại nhiều nhóm cùng một kiểu | Rất phù hợp với các nhãn có guard nối tiếp | Phù hợp nếu muốn gom logic dưới một nhánh kiểu |
| Muốn nhiều câu lệnh, vòng lặp, try/catch | Đưa vào thân nhánh sau `->` | Dùng trực tiếp trong block thân nhánh |
| Ảnh hưởng đến dominance/exhaustiveness | Có; compiler xét guard trong quy tắc nhãn | Không; `if` nội bộ không thay đổi độ bao phủ của case label |
| Exception trong điều kiện | Guard ném exception thì việc chọn case bị ngắt, không fallback | `if` ném exception thì việc thực thi nhánh bị ngắt |
| Dùng với literal `case null` hoặc case constant? | Không; `when` gắn với case pattern | Có thể đặt `if` trong thân nhánh constant/null |
| Tác dụng chính | **Chọn case** | **Xử lý trong case** |

Không có quy tắc “luôn ưu tiên `when`”. Chọn dựa trên **ngữ nghĩa cần biểu đạt** và khả năng bảo trì.

## 5. Khi nào hai cách cho cùng kết quả?

Nếu chỉ phân chia nội bộ một kiểu và không cần cho case khác xử lý khi điều kiện sai, bạn có thể viết cả hai cách cho kết quả tương đương.

### Dạng nhiều nhãn có guard

```java
static String byGuard(Object input) {
    return switch (input) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long:" + s;
        case String s -> "short:" + s;
        case Integer n when n < 0 -> "negative:" + n;
        case Integer n -> "nonnegative:" + n;
        default -> "other";
    };
}
```

### Dạng gộp bằng `if` trong thân nhánh

```java
static String byBody(Object input) {
    return switch (input) {
        case null -> "null";
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            if (s.length() >= 5) {
                yield "long:" + s;
            }
            yield "short:" + s;
        }
        case Integer n -> {
            if (n < 0) {
                yield "negative:" + n;
            }
            yield "nonnegative:" + n;
        }
        default -> "other";
    };
}
```

Hai hàm trả về **cùng kết quả cho các đầu vào trong chương trình minh họa của bài này**, vì nhánh `String` gộp cũng tự phân chia đủ ba nhóm, và nhánh `Integer` gộp tự chia âm/không âm. Nhưng hai cách **không giống nhau trong cách xác định nhãn**:

- `byGuard`: khi một guard sai, Java tìm nhãn kế tiếp. Các ranh giới phân loại nằm ở **switch labels**.
- `byBody`: ngay khi khớp String, Java vào block String; các ranh giới phân loại là **if statements** nội bộ.
- Với `byBody`, không thể kỳ vọng một nhánh kiểu rộng đặt sau sẽ được tự chọn nếu `if` bên trong String sai. Muốn được như vậy, phải thay đổi cách tổ chức logic hoặc sử dụng guard.

Do đó, **cùng đầu ra không có nghĩa cùng ngữ nghĩa điều khiển**. Hai biểu thức chỉ tương đương khi việc phân nhánh nội bộ được viết đầy đủ và các hành vi ngoại lệ, tác dụng phụ, thứ tự kiểm tra đều được giữ đúng.

## 6. Pattern variables: có phạm vi trong guard và thân nhánh

`String s` trong nhãn:

```java
case String s when s.length() >= 5 -> "long: " + s;
```

đồng thời khai báo biến pattern `s`. Khi guard chạy, pattern đã khớp nên `s` được definitely matched. Biến này cũng khả dụng trong thân nhánh `->` của **chính nhãn đó**.

```java
static int textLength(Object input) {
    return switch (input) {
        case String s when !s.isEmpty() -> s.length();
        case String s -> 0;
        case null -> -1;
        default -> -2;
    };
}
```

Hai tên `s` trong hai nhãn khác nhau là **hai khai báo pattern variable riêng**. Biến được giới thiệu bởi nhãn này không tự mang sang nhãn khác.

**Không được gọi `s.length()` trước khi kiểm tra kiểu** nếu `input` chưa biết là String. `when` giúp đảm bảo điều kiện chạy trong bối cảnh đã khớp pattern. Tương tự, `if` trong thân nhánh đã chọn cũng có thể sử dụng `s` an toàn.

### Pattern trên record và điều kiện guard

`when` không chỉ áp dụng cho type pattern:

```java
record Order(String code, int total) {}

static String orderCategory(Object input) {
    return switch (input) {
        case Order(String code, int total) when total >= 100 ->
                "big:" + code;
        case Order(String code, int total) ->
                "small:" + code;
        case null -> "null";
        default -> "not-order";
    };
}
```

Đầu vào `new Order("A", 120)` trả `big:A`; `new Order("B", 15)` trả `small:B`. Với tổng tiền nhỏ, record pattern đầu tiên vẫn **khớp cấu trúc**, nhưng guard sai; vì vậy Java tiếp tục tới nhãn Order không guard. Điều kiện `total >= 100` có thể dùng biến `total` được khai báo trong record pattern.

## 7. Thứ tự nhãn và dominance

Java 21 không đơn thuần lấy nhánh đầu tiên có cùng tên kiểu. Compiler còn kiểm tra **dominance** (nhãn trước đã bao phủ nhãn sau hay chưa).

### Đúng: guard cụ thể ở trước, nhánh không guard ở sau

```java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "other string";
        case null -> "null";
        default -> "non-string";
    };
}
```

Java cho phép pattern String có guard đứng trước pattern String không guard. Guard có thể sai nên nhãn sau vẫn có cơ hội áp dụng.

### Sai: pattern String tổng quát đứng trước guard String

```java
// KHÔNG BIÊN DỊCH trong Java 21:
static String invalidOrder(Object value) {
    return switch (value) {
        case String s -> "string";
        case String s when s.isBlank() -> "blank"; // Bị nhãn trước dominate
        case null -> "null";
        default -> "other";
    };
}
```

Nhãn `case String s` không guard đã xử lý mọi String khác null, do đó nhãn guard cùng kiểu phía sau bị dominate. Một `if` bên trong thân nhánh String **không** làm các nhãn đứng sau có thêm cơ hội áp dụng.

### `when true` và `when false` là trường hợp đặc biệt

Theo JLS Java SE 21:

- `case String s when true` được coi là **unguarded** cho các quy tắc liên quan vì guard là hằng biểu thức `true`. Nó có thể dominate nhãn String phía sau.
- Guard là một **constant expression có giá trị `false`** sẽ gây **lỗi biên dịch**. Không dùng `when false` để vô hiệu hóa tạm một nhánh.
- Với guard động như `s.isBlank()`, Java không giả định nó luôn đúng; do đó nhãn String không guard đứng sau là cách phổ biến để xử lý phần còn lại.

Quy tắc này liên quan trực tiếp đến cách compiler kiểm tra cấu trúc nhãn; **`if (true)` hoặc `if (false)` trong thân case không phải phép thay thế tương đương** cho dominance.

## 8. Guard và exhaustiveness: if nội bộ không quyết định độ bao phủ

Một `switch` expression phải **exhaustive**: tập nhãn phải bao phủ các giá trị mà luật kiểm tra tĩnh yêu cầu. Enhanced `switch` statement có case pattern cũng phải exhaustive theo Java 21.

Xét một selector kiểu `String`:

```java
// KHÔNG BIÊN DỊCH: switch expression không exhaustive.
static String incomplete(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s when s.length() <= 3 -> "short";
    };
}
```

Con người biết hai điều kiện có thể phủ hết mọi độ dài của String khác null. Nhưng compiler **không** chứng minh tổng quát biểu thức guard tùy ý là exhaustive. Để hoàn chỉnh, thêm nhãn **không guard**:

```java
static String complete(String value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s -> "short";
    };
}
```

Lưu ý: expression trên vẫn **ném `NullPointerException`** nếu `value` null vì thiếu `case null`, dù nó exhaustive đối với kiểu String theo quy tắc tĩnh. Khi cần xử lý null, thêm `case null -> ...`.

Với một `if` trong thân case, compiler nhìn độ bao phủ của **nhãn bên ngoài**, không dùng điều kiện `if` để mở rộng hay thu hẹp tập nhãn:

```java
static String completeUsingBody(String value) {
    return switch (value) {
        case String s -> {
            if (s.length() > 3) {
                yield "long";
            }
            yield "short";
        }
    };
}
```

Nhãn `String s` không guard là unconditional cho các giá trị String khác null, nên `switch` expression hợp lệ. Điều kiện `if` chỉ quyết định kết quả **sau khi nhãn đã được chọn**.

**Kỹ thuật thực hành:** khi muốn nhiều nhãn có `when`, hãy luôn tự hỏi có một nhãn không guard hoặc `default` đáp ứng exhaustiveness hay chưa. Đừng dựa vào việc các điều kiện `when` “có vẻ bao phủ hết”.

## 9. Ràng buộc cú pháp và kiểm tra guard Java 21

### 9.1. `when` chỉ gắn với case pattern

**Đúng:**

```java
case String s when s.startsWith("A") -> "A";
```

**Sai:**

```java
// KHÔNG BIÊN DỊCH:
// case null when condition -> "missing";
// case 1 when condition -> "one";
```

Nhãn `case null` và nhãn hằng số `case 1` không phải case pattern; Java 21 không cho đặt `when` trực tiếp sau chúng. Nếu cần xử lý thêm điều kiện, đặt `if` trong thân nhánh tương ứng, hoặc chọn mô hình selector khác.

### 9.2. Kiểu trả về phải là boolean hoặc Boolean

Guard là một **expression** có kiểu `boolean` hoặc `Boolean`:

```java
case String s when s.length() > 3 -> "long";
```

Không dùng biểu thức kiểu `int` làm guard:

```java
// KHÔNG BIÊN DỊCH:
// case String s when s.length() -> "invalid";
```

Nếu guard là `Boolean` và kết quả bằng `null`, phép unboxing khi đánh giá có thể ném `NullPointerException`. Điều này **không** làm Java tiếp tục đến nhãn `case` kế tiếp; lỗi từ guard sẽ lan ra ngoài việc chọn nhãn.

### 9.3. Biến ngoài guard phải final hoặc effectively final

JLS còn yêu cầu local variable, formal parameter và exception parameter **được dùng trong guard nhưng không khai báo tại guard** phải là `final` hoặc *effectively final*. Ví dụ:

```java
static String threshold(Object input, int minLength) {
    return switch (input) {
        case String s when s.length() >= minLength -> "long enough";
        case String s -> "too short";
        case null -> "null";
        default -> "other";
    };
}
```

`minLength` không bị gán lại nên hợp lệ. Nếu chỉnh sửa `minLength` bằng phép gán khiến nó không còn effectively final trong phương thức, guard tham chiếu tới biến ấy sẽ gây lỗi biên dịch. Với `if` trong thân nhánh, ràng buộc đặc thù này của guard không áp dụng y hệt; vẫn phải tuân theo các quy tắc scope và definite assignment thông thường.

### 9.4. Guard có thể gọi phương thức nhưng nên tránh side effects

`when` được đánh giá trong **quá trình tìm nhãn áp dụng**. Nếu phương thức trong guard thay đổi dữ liệu, gọi I/O, ghi log hoặc ném lỗi, thứ tự tìm nhãn và việc xử lý ngoại lệ có thể trở nên khó hiểu:

```java
case String s when expensiveCheck(s) -> "accepted";
```

Cú pháp trên chỉ là ví dụ nếu `expensiveCheck` được định nghĩa để trả boolean. Nó hợp lệ nhưng chi phí kiểm tra phát sinh mỗi khi pattern trước nó khớp và Java cần xét guard. **Guard trả false** khiến Java tìm nhãn tiếp theo; **guard ném exception** làm quá trình chọn nhãn kết thúc bất thường, không phải “false rồi fallback”.

Khi phép kiểm tra rất phức tạp, cần nhiều câu lệnh, cập nhật trạng thái hoặc xử lý ngoại lệ riêng, có thể chọn **`if` trong block case** hay tách ra một phương thức predicate thuần hàm có tên rõ nghĩa.

## 10. Null và việc không áp dụng pattern/guard

Với selector là `null` trong pattern switch Java 21:

- Một type pattern `String s` **không khớp `null` ở selector ngoài**.
- Guard `when` gắn với `String s` **không được chạy** cho selector null.
- `default` **đơn lẻ không bắt null**. Nếu không có `case null` thì `switch` ném `NullPointerException`.
- Có thể viết `case null -> ...`, hoặc `case null, default -> ...` khi null và giá trị còn lại được xử lý giống nhau.

Ví dụ đúng:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "string";
        default -> "other";
    };
}
```

Nếu muốn kiểm tra một điều kiện phụ **sau khi null label đã được chọn**, hãy dùng `if` trong thân nhánh `case null`, không dùng `when`:

```java
static String missing(Object input, boolean required) {
    return switch (input) {
        case null -> {
            if (required) {
                yield "error: required value";
            }
            yield "optional missing";
        }
        case String s -> s;
        default -> "other";
    };
}
```

Đây là một tình huống **`if` trong thân case là lựa chọn cần thiết theo cú pháp**.

## 11. Chương trình đầy đủ: hai cách phân loại và kết quả khác nhau khi fallback

Tạo tệp **`WhenVsCaseBodyDemo.java`** với nội dung sau:

```java
public class WhenVsCaseBodyDemo {
    record Order(String code, int total) {}

    static String byGuard(Object input) {
        return switch (input) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s when s.length() >= 5 -> "long:" + s;
            case String s -> "short:" + s;
            case Integer n when n < 0 -> "negative:" + n;
            case Integer n -> "nonnegative:" + n;
            default -> "other";
        };
    }

    static String byBody(Object input) {
        return switch (input) {
            case null -> "null";
            case String s -> {
                if (s.isBlank()) {
                    yield "blank";
                }
                if (s.length() >= 5) {
                    yield "long:" + s;
                }
                yield "short:" + s;
            }
            case Integer n -> {
                if (n < 0) {
                    yield "negative:" + n;
                }
                yield "nonnegative:" + n;
            }
            default -> "other";
        };
    }

    static String guardFallback(Object input) {
        return switch (input) {
            case String s when s.startsWith("A") -> "starts-with-A";
            case CharSequence chars -> "general sequence";
            case null -> "null";
            default -> "other";
        };
    }

    static String wrongBody(Object input) {
        return switch (input) {
            case String s -> {
                if (s.startsWith("A")) {
                    yield "starts-with-A";
                }
                yield "String branch already selected";
            }
            case CharSequence chars -> "general sequence";
            case null -> "null";
            default -> "other";
        };
    }

    static String withRecord(Object input) {
        return switch (input) {
            case Order(String code, int total) when total >= 100 ->
                    "big:" + code;
            case Order(String code, int total) -> "small:" + code;
            case null -> "null";
            default -> "not-order";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "   ", "Java", "Pattern", -3, 4, 2.5};

        for (Object input : inputs) {
            System.out.println(byGuard(input) + " | " + byBody(input));
        }

        System.out.println("guard: " + guardFallback("Beta"));
        System.out.println("body: " + wrongBody("Beta"));
        System.out.println("builder: "
                + guardFallback(new StringBuilder("Hi")));

        System.out.println(withRecord(new Order("A", 120)));
        System.out.println(withRecord(new Order("B", 15)));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 WhenVsCaseBodyDemo.java
java WhenVsCaseBodyDemo
```

Kết quả:

```text
null | null
blank | blank
short:Java | short:Java
long:Pattern | long:Pattern
negative:-3 | negative:-3
nonnegative:4 | nonnegative:4
other | other
guard: general sequence
body: String branch already selected
builder: general sequence
big:A
small:B
```

Giải thích:

1. **Bảy dòng đầu:** `byGuard` và `byBody` cùng phân loại đúng vì hai cách đều xử lý đủ các trường hợp cần thiết trong từng loại. Nhãn null cho kết quả `null`, chuỗi blank cho `blank`, chuỗi `Java` (4 ký tự) cho `short`, `Pattern` (7 ký tự) cho `long`, số nguyên âm và không âm tách riêng, `Double` vào `default`.
2. **`guardFallback("Beta")`:** `Beta` khớp type pattern String nhưng `startsWith("A")` sai. Java tiếp tục chọn nhãn `CharSequence` nên kết quả `general sequence`.
3. **`wrongBody("Beta")`:** nhãn String đã được chọn trước khi `if` chạy; `if` sai chỉ khiến chương trình chuyển đến `yield` tiếp theo trong block String. Không chuyển xuống nhãn CharSequence.
4. **`StringBuilder("Hi")`:** không phải String nhưng là CharSequence nên nhãn `CharSequence` được chọn.
5. **Hai Order:** record pattern đều khớp đối tượng Order. Guard `total >= 100` nhận Order A; đối tượng B không qua guard đầu, đi tiếp tới nhãn Order không guard.

Đây là ví dụ thực hành cho thấy **“có thể trả về kết quả giống nhau”** và **“có thể chọn các nhãn khác nhau”** là hai câu hỏi riêng.

## 12. Lỗi thường gặp khi chọn giữa when và if

**Lỗi 1 — biến `when` thành `if` bên trong nhánh rồi chờ case kế tiếp chạy.** Nhãn đã được chọn thì `if` không thể tự làm `switch` bắt đầu lại việc chọn label. Muốn fallback giữa các case, chuyển điều kiện vào `when`.

**Lỗi 2 — đặt case kiểu tổng quát trước case có guard cùng kiểu.** Nhánh không guard có thể dominate nhánh guard, gây lỗi compile. Đặt nhãn đặc biệt lên trước và nhãn tổng quát sau.

**Lỗi 3 — không cung cấp nhánh bao phủ dữ liệu còn lại.** Tập guard tùy ý không tự được coi là exhaustive. Dùng unguarded pattern thích hợp hoặc `default`; đồng thời xử lý `null` theo chính sách API.

**Lỗi 4 — đặt `when` sau `case null` hoặc hằng số.** `when` gắn với case pattern trong Java 21; đặt kiểm tra có điều kiện bên trong thân case null/constant thay vì gắn guard sai cú pháp.

**Lỗi 5 — dùng một biểu thức không phải boolean làm guard.** `when s.length()` sai về kiểu; phải là biểu thức boolean, ví dụ `when s.length() > 3`.

**Lỗi 6 — cho rằng guard ném exception tương đương false.** Khi guard ném exception, `switch` cũng bị ngắt, không thử nhãn tiếp; cần tự xử lý exception nếu muốn chính sách khác.

**Lỗi 7 — viết quá nhiều logic phức tạp trong guard.** Predicate nên dễ đọc, ít tác dụng phụ, thường thuần hàm; logic nhiều bước, logging, I/O hoặc try/catch phù hợp hơn trong phương thức riêng hoặc thân case.

**Lỗi 8 — nhầm cú pháp các phiên bản Java.** `when` trong pattern switch là cú pháp ổn định Java 21. Tài liệu preview cũ có thể dùng dạng guard khác; hãy biên dịch bằng `--release 21` và không sao chép máy móc cú pháp preview trước đó.

## 13. Bài tập tự kiểm tra

**Bài tập A.** Dự đoán kết quả với đầu vào `"Apple"` và `"Berry"`:

```java
static String f(Object obj) {
    return switch (obj) {
        case String s when s.startsWith("A") -> "A";
        case String s -> "other-string";
        case null -> "null";
        default -> "not-string";
    };
}
```

**Đáp án:** `f("Apple")` trả `A`; `f("Berry")` trả `other-string`. Guard chỉ quyết định nhãn đầu có áp dụng hay không.

**Bài tập B.** Thay nhãn đầu bằng:

```java
// Ví dụ chỉ là phần nhánh cho một switch expression:
case String s -> {
    if (s.startsWith("A")) {
        yield "A";
    }
    yield "not-A";
}
```

Điều gì xảy ra nếu vẫn để một `case String s -> ...` đứng sau?

**Đáp án:** nhãn String phía sau bị dominate, gây lỗi biên dịch. Khi dùng một nhánh String không guard, mọi phân loại chuỗi nên nằm trong block của nhánh ấy hoặc phải tổ chức lại các nhãn với guard phía trước.

**Bài tập C.** Hai guard `case String s when s.length() > 3` và `case String s when s.length() <= 3` đã “phủ hết” các chuỗi theo toán học. Vì sao `switch` expression chỉ có hai nhãn này vẫn không hợp lệ?

**Đáp án:** kiểm tra exhaustiveness trong JLS không dùng chứng minh logic tùy ý cho các điều kiện động. Cần một nhãn không guard hoặc nhánh dự phòng phù hợp; đồng thời xử lý null riêng nếu cần.

**Bài tập D.** Có thể viết `case null when required -> ...` không?

**Đáp án:** Không. Guard `when` chỉ gắn với case pattern. Dùng `case null -> { if (required) ... }`.

**Bài tập E.** Trong `case String s when s.length() > 3`, Java có gọi `length()` khi selector là `Integer` không? Nếu `s.length()` được thay bằng một phương thức ném exception thì sao?

**Đáp án:** Không gọi khi selector là Integer vì pattern String thất bại. Khi selector là String nhưng guard ném exception, việc chọn nhãn bị ngắt bởi exception, không phải guard trả false.

**Bài tập F.** Hãy viết một `switch` expression cho `Object` có các nhóm: Integer âm, Integer không âm, String rỗng/blank, String khác, null, và mọi kiểu khác. Sau đó viết lại bằng đúng một nhãn Integer và một nhãn String, với các `if` bên trong block. Hai phiên bản cần có cùng kết quả; giải thích chúng khác nhau ở bước chọn nhãn nào.

## 14. Checklist chọn cấu trúc

Trước khi dùng `when`, hãy trả lời:

1. Điều kiện này là **điều kiện để một nhãn case được áp dụng**, hay chỉ là **quyết định xử lý trong case đã được chọn**?
2. Nếu điều kiện sai, bạn có thật sự muốn **thử case khác** không? Nếu muốn, ưu tiên guard.
3. Nếu có nhiều guard cùng kiểu, đã xếp **guard đặc thù trước pattern không guard** để tránh dominance chưa?
4. Có nhãn không guard/`default` đáp ứng exhaustiveness chưa? Null selector có chính sách riêng chưa?
5. Guard có sử dụng pattern variable sau khi khớp và có kiểu boolean/Boolean không? Các biến ngoài guard có final/effectively final không?
6. Điều kiện có tác dụng phụ, lỗi tiềm ẩn hay chi phí cao không? Nếu có, cần tổ chức lại xử lý cho dễ kiểm thử và dễ đọc.
7. Nếu dùng `switch` expression và thân case dạng block, đã dùng `yield` để trả giá trị đầy đủ trên mọi đường đi bình thường cần thiết chưa?

**Quy tắc ghi nhớ:** `when` = *điều kiện tham gia chọn nhãn*; `if` trong thân `case` = *điều kiện tham gia thực hiện công việc sau khi chọn nhãn*.

## Tài liệu đối chiếu

- [JLS Java SE 21 `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): dạng nhãn `case Pattern when Guard`, ràng buộc guard, dominance và compatibility.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): kiểm tra độ bao phủ.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): trình tự thử pattern, guard và nhãn tiếp theo.
- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi của pattern variable.
- [JLS Java SE 21 `15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): trả giá trị và `yield`.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng ổn định từ Java 21 và rationale của guarded patterns.
