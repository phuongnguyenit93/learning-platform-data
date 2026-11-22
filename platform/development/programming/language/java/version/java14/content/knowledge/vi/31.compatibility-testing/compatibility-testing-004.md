# Đối chiếu kết quả trước và sau tái cấu trúc `switch` hoặc `instanceof`

## 1. Vấn đề: code ngắn hơn nhưng hành vi có còn đúng?

Tái cấu trúc (*refactoring*) là thay đổi **cấu trúc nội bộ** mà vẫn giữ **hành vi đã cam kết**. Trong Java hiện đại, hai kiểu tái cấu trúc phổ biến là:

1. Chuyển một `switch` statement với biến tạm, `break` và các nhóm `case` thành **`switch` expression** trả thẳng giá trị bằng `->` hoặc `yield`.
2. Chuyển cặp **`instanceof` + ép kiểu tường minh** thành **pattern matching for `instanceof`**, chẳng hạn `value instanceof String text`.

Cả hai đều có thể làm mã dễ đọc, nhưng **biên dịch thành công không chứng minh kết quả không thay đổi**. Lỗi thường nằm ở ranh giới: một nhánh `case` bị bỏ sót, một nhánh fall-through cũ bị hiểu nhầm, điều kiện `instanceof` đổi thứ tự, giá trị `null`, kiểu con, ngoại lệ, hoặc biểu thức có tác dụng phụ được đánh giá nhiều lần.

**Bài toán:** Thiết lập cách **đối chiếu kết quả trước/sau bằng bộ kiểm thử tự động**, vừa kiểm tra giá trị trả về, vừa so sánh lỗi/ngoại lệ và những tác dụng phụ có ý nghĩa.

**Special Note về kiến thức hiện hành:** `switch` expression chính thức từ **Java 14** (JEP 361); pattern matching for `instanceof` từng preview ở Java 14, nhưng **chính thức từ Java 16** (JEP 394). Các đoạn thực hành chỉ sử dụng **Java 17+**, không dùng cờ preview, không sử dụng cú pháp thử nghiệm cũ như `break value;`. Cú pháp pattern switch của Java 21+ được nêu riêng, không trộn vào ví dụ `--release 17`.

## 2. Định nghĩa chính xác “giữ nguyên kết quả”

Hai hàm `before(input)` và `after(input)` có thể được xem là tương đương trong phạm vi hợp đồng nếu những quan sát cần thiết giống nhau với mọi input thuộc miền đã cam kết.

Những gì nên so sánh:

| Nhóm quan sát | Ví dụ với `switch`/`instanceof` | Cách kiểm tra |
| --- | --- | --- |
| Giá trị trả về | `"OK"`, `"UNKNOWN"`, số, `null`, object | `Objects.equals` hoặc assertion chuyên dụng |
| Nhánh được chọn | `case 200`, `default`, `instanceof String` | Bảng test từng nhánh |
| Ngoại lệ | Kiểu exception và, nếu là hợp đồng, mã/thông điệp lỗi | Ghi lại exception hoặc `assertThrows` |
| Tác dụng phụ | Số lần gọi selector, cập nhật state, số lần gọi service | Spy/fake/counter, đối chiếu trace |
| Thứ tự | Ghi log, gửi sự kiện, gọi dependency theo thứ tự | So sánh danh sách sự kiện có thứ tự |
| `null` | `instanceof null` trả false; `switch(String null)` có thể ném NPE | Test `null` tường minh |
| Kiểu đối tượng | `String`, `Number`, subclass, object không khớp | Test nhiều runtime type |
| Biên số và nhóm case | `Integer.MIN_VALUE`, `200`, `201`, `500` | Boundary/decision-table tests |
| Dữ liệu phản hồi phức tạp | Record, list, map, JSON | So sánh theo semantic contract, tránh phụ thuộc identity vô tình |

**Không phải lúc nào cũng phải so chính xác mọi byte:** stack trace và số dòng source sẽ khác sau khi refactor; thông điệp *helpful NullPointerException* cũng có thể thay đổi theo biểu thức nguồn. Nếu API cam kết **loại exception** và **mã lỗi nghiệp vụ**, hãy so những thuộc tính đó. Nếu API thực sự cam kết thông điệp lỗi, phải đưa thông điệp vào test. Việc chuẩn hóa exception quá rộng (chỉ lấy “có ném lỗi”) có thể **che một hồi quy quan trọng**.

**Cảnh báo đối chiếu hai bản:** Nếu bản cũ vốn có lỗi, test “before bằng after” có thể giúp bảo toàn chính lỗi ấy. Cần thêm một **nguồn kỳ vọng độc lập**: yêu cầu nghiệp vụ, test fixtures, ví dụ được duyệt hoặc test “golden”. Đây là lý do phải kết hợp **differential testing** với test expected behavior.

## 3. `switch` statement sang `switch` expression: những điểm dễ thay đổi

### 3.1. Trước khi tái cấu trúc

Ví dụ mapping HTTP-like status code sang chuỗi hiển thị:

```java
static String oldStatus(int code) {
    String result;
    switch (code) {
        case 200:
        case 201:
            result = "OK";
            break;
        case 404:
            result = "MISSING";
            break;
        case 500:
            throw new IllegalStateException("REMOTE_ERROR");
        default:
            result = "UNKNOWN";
            break;
    }
    return result;
}
```

Đây là **phương thức minh họa** với logic đầy đủ; cần đặt trong class và import nếu dùng API ngoài `java.lang`. Cặp `case 200: case 201:` là **hai nhãn chung một nhóm statement**. Nó cố ý cho cả 200 và 201 cùng kết quả `"OK"`.

### 3.2. Sau khi tái cấu trúc

```java
static String newStatus(int code) {
    return switch (code) {
        case 200, 201 -> "OK";
        case 404 -> "MISSING";
        case 500 -> throw new IllegalStateException("REMOTE_ERROR");
        default -> "UNKNOWN";
    };
}
```

Biểu thức `switch` có kết quả, nên có thể `return switch(...)` trực tiếp. Dạng **`case ... ->`** không fall-through. Với nhóm `case 200, 201`, một nhánh có thể gắn **nhiều nhãn**.

Nếu một nhánh cần nhiều câu lệnh trước khi trả về giá trị, dùng:

```java
default -> {
    String message = "UNKNOWN";
    yield message;
}
```

Đây là **một nhánh minh họa** nằm bên trong switch expression. `yield` trả giá trị cho **biểu thức `switch`**, khác với `break` của switch statement và `return` của phương thức.

### 3.3. Bản refactor sai rất dễ lọt review

```java
// Sai về hành vi: quên mã 201.
return switch (code) {
    case 200 -> "OK";
    case 404 -> "MISSING";
    case 500 -> throw new IllegalStateException("REMOTE_ERROR");
    default -> "UNKNOWN";
};
```

Đây là **đoạn mã minh họa** trong một phương thức trả `String`, không độc lập. Trước refactor, mã 201 trả `"OK"`; sau bản sai nó rơi vào `default` và trả `"UNKNOWN"`. Compiler vẫn chấp nhận vì `switch` có `default`.

**Cách phát hiện:** đặt 200 **và 201** trong bộ test. Chỉ kiểm tra 200 là chưa đủ.

### 3.4. Fall-through, return, throw và exhaustiveness

Những quy tắc hiện còn áp dụng:

- `case ... ->` **không fall-through** sang nhánh kế tiếp.
- `case ... :` của switch statement **có thể fall-through** nếu không có `break`/`return`/`throw` thích hợp.
- **Không chuyển nhầm fall-through có chủ đích** thành các nhánh `->` độc lập, hoặc vô tình mất một bước xử lý.
- `throw` là kết thúc bất thường; khi đổi sang biểu thức switch phải giữ đúng loại lỗi, điều kiện và thông tin nghiệp vụ.
- Một switch expression cần **exhaustive** theo quy tắc ngôn ngữ, nhưng có `default` và biên dịch được vẫn **không chứng minh** logic đúng nghiệp vụ.
- Với enum exhaustive, có thể không cần `default` tường minh; khi enum phát triển ở phiên bản thư viện khác, cần xem chính sách tương thích và cách xử lý constant mới.

**Điều cần test:** tất cả nhánh hiện có, mọi nhóm case nhiều nhãn, nhánh default, exception path, input ở sát ranh giới và các side effects trong nhánh.

### 3.5. `switch` không chỉ khác vì giá trị

Đôi khi `switch` statement thực hiện nhiều tác vụ rồi return/thoát. Chẳng hạn:

```java
switch (level) {
    case 1:
        audit("first");
        // Cố ý fall-through.
    case 2:
        audit("second");
        break;
    default:
        audit("other");
}
```

Đây là **đoạn minh họa**, với `level` và `audit(...)` được khai báo ngoài. Nếu `level=1`, trace là `first,second`. Refactor máy móc sang `case 1 -> audit("first")` và `case 2 -> audit("second")` sẽ **đổi trace**, dù mỗi nhánh riêng nhìn có vẻ hợp lý. Với code có hiệu ứng, dùng **spy** ghi lại thứ tự lời gọi bên cạnh test kết quả.

## 4. `instanceof` + cast sang pattern matching: giữ cả điều kiện và phạm vi

### 4.1. Trước

```java
static String oldType(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "S:" + text.strip().toUpperCase(Locale.ROOT);
    }
    if (value instanceof Number) {
        Number number = (Number) value;
        return "N:" + number.longValue();
    }
    return "OTHER";
}
```

Đây là phương thức minh họa, cần `import java.util.Locale;`. Với `value=null`, cả hai điều kiện `instanceof` đều **false**; hàm trả `"OTHER"`.

### 4.2. Sau

```java
static String newType(Object value) {
    if (value instanceof String text) {
        return "S:" + text.strip().toUpperCase(Locale.ROOT);
    }
    if (value instanceof Number number) {
        return "N:" + number.longValue();
    }
    return "OTHER";
}
```

Pattern variable `text` hoặc `number` được tạo **khi phép so khớp thành công**. Không cần viết cast tường minh. `instanceof` đối với `null` vẫn trả false. **Không đổi thứ tự các nhánh chỉ để làm code gọn hơn** nếu nhiều điều kiện có thể khớp một đối tượng.

### 4.3. Các ca bắt buộc nên thử

| Input | Nhánh kỳ vọng | Kết quả minh họa |
| --- | --- | --- |
| `null` | Không khớp | `OTHER` |
| `""` | `String` | `S:` |
| `" hello "` | `String`, strip và uppercase | `S:HELLO` |
| `String` chứa khoảng trắng Unicode | `String` | Áp dụng cùng `strip()` và `Locale.ROOT` |
| `Integer.valueOf(7)` | `Number` | `N:7` |
| `Double.valueOf(2.5)` | `Number` | `N:2` nếu dùng `longValue()` |
| `Long.valueOf(8)` | `Number` | `N:8` |
| `BigDecimal("123.45")` | `Number` | `N:123` |
| `new StringBuilder("hi")` | Không phải `String` hoặc `Number` | `OTHER` |
| `Boolean.TRUE` | Không khớp | `OTHER` |

Các kết quả `Number.longValue()` là **quy tắc chuyển đổi số hiện tại**, không đồng nghĩa làm tròn theo nghiệp vụ. **Đừng đổi `longValue()` thành `Math.round(...)`** trong lúc chỉ muốn loại bỏ cast; như vậy sẽ thay đổi hành vi.

### 4.4. Flow scoping, `&&`, `||` và null

Pattern variable không phải một biến “luôn luôn tồn tại”. Với:

```java
if (value instanceof String s && !s.isBlank()) {
    System.out.println(s.length());
}
```

Java biết `s` đã được gán ở vế phải của `&&`, vì vế phải chỉ được đánh giá khi vế trái `true`. Đây là **đoạn mã minh họa** trong phương thức với `value` có kiểu thích hợp.

**Cẩn thận:** nếu bản cũ có nhánh `if (value instanceof String)` xử lý **cả chuỗi rỗng**, khi chuyển thành `instanceof String s && !s.isBlank()` bạn đã **thêm một điều kiện nghiệp vụ**. Test `""`, chuỗi toàn khoảng trắng và ký tự Unicode sẽ phát hiện hồi quy.

Với `||`, không thể mặc định dùng pattern variable trong phần được chạy bất kể nhánh nào, vì có thể điều kiện đúng mà pattern chưa match. Java dùng **flow-sensitive scope** để tránh trường hợp đọc biến chưa được gán; đổi thứ tự toán tử/biểu thức cũng có thể đổi thứ tự side effects.

**Không nhầm pattern matching với việc cho phép cast bất kỳ:** mã `value instanceof String s` chỉ khớp nếu runtime value thực sự là `String`. `StringBuilder` có thể thực thi `CharSequence`, nhưng nó **không** là `String`. Đổi pattern sang `CharSequence cs` sẽ **mở rộng tập đối tượng match**, có thể phá tương thích.

## 5. Những thay đổi ngầm cần đối chiếu khi refactor

### 5.1. `null`

- `null instanceof String` là `false`; pattern `null instanceof String s` cũng `false`.
- Với **`switch(String)` cổ điển** trong Java 17, `null` gây **`NullPointerException`** kể cả khi có `default`. Chuyển statement sang expression mà thêm `if (value == null) return "OTHER";` sẽ **thay hành vi**, không chỉ làm đẹp code.
- Từ **Java 21**, Java hỗ trợ `case null` trong switch pattern theo cơ chế đã chuẩn hóa (JEP 441). Nếu cố ý thêm `case null`, cần ghi rõ thay đổi hợp đồng và cập nhật tests; không coi nó là refactor hành vi bất biến.
- Với `Integer`, `Enum` và các selector tham chiếu có thể null, cần kiểm thử tương tự theo phiên bản Java mục tiêu.

### 5.2. Chuỗi và locale

- `switch(String)` so khớp giá trị chuỗi theo nội dung, không phải `==` đồng nhất tham chiếu. Test `new String("A")` giúp phòng lỗi nếu refactor thành `if (s == "A")`.
- `toUpperCase()` không có `Locale` tường minh có thể phụ thuộc môi trường. Trong bài thử, cả hai bản dùng `Locale.ROOT` để cố định quy tắc; đừng vô tình đổi từ cách cũ sang cách mới mà không duyệt tác động.
- `strip()` và `trim()` không đồng nghĩa với mọi loại khoảng trắng Unicode. Một thay đổi đi kèm ép kiểu có thể đổi kết quả của một vài giá trị biên.
- Kiểm tra chuỗi rỗng, dấu cách, tab, xuống dòng, ký tự Unicode, dữ liệu viết hoa/thường và encoding nếu là hợp đồng.

### 5.3. Ngoại lệ

Đối chiếu:
1. Không ném ngoại lệ khi trước đó trả giá trị.
2. Không trả giá trị khi trước đó phải ném lỗi.
3. Cùng **loại exception** cho cùng trường hợp.
4. Cùng mã lỗi hoặc message nếu đó là phần của hợp đồng.
5. Cùng side effects trước thời điểm throw, nếu chúng có ý nghĩa nghiệp vụ.

Trong một chương trình tự kiểm thử, có thể đóng gói hai kết quả thành:

```java
record Outcome(boolean failed, String detail) {}
```

Nếu code trả giá trị thì `failed=false`; nếu ném `RuntimeException` thì `failed=true` và `detail` chứa thông tin lỗi đã chuẩn hóa theo **chính sách kiểm thử**. **Không bắt `Throwable` một cách vô điều kiện** rồi coi mọi lỗi nghiêm trọng (ví dụ `OutOfMemoryError`) là đầu ra nghiệp vụ bình thường.

### 5.4. Tác dụng phụ và thứ tự thực thi

Một selector `switch` được đánh giá theo thứ tự quy định và được đánh giá một lần khi bắt đầu switch. Tuy nhiên, **refactor có thể vô tình sao chép biểu thức này** sang nhiều nhánh hoặc gọi thêm dependency.

Ví dụ:

```java
return switch (nextStatus()) {
    case 200 -> "OK";
    default -> "UNKNOWN";
};
```

Đây là đoạn minh họa khi `nextStatus()` là phương thức có side effect. Nếu logic cũ gọi `nextStatus()` đúng một lần, test cũng nên xác nhận bản mới đúng một lần. Điều này quan trọng với đọc message queue, lấy thời gian, tăng counter, truy vấn database hoặc gọi API có side effect.

**Không chỉ so return value** khi các thao tác phát sinh trước đó có ý nghĩa. Với async code hoặc concurrency, cần phân biệt contract về **thứ tự quan sát được** với chi tiết lịch trình thread không được cam kết.

## 6. Thiết kế bảng quyết định trước khi viết test

Trước khi chuyển đổi mã, nên ghi lại **mỗi nhánh đầu vào và kết quả kỳ vọng**. Ví dụ với mapping status:

| Nhóm | Input | Kết quả/ngoại lệ kỳ vọng |
| --- | --- | --- |
| Nhánh nhóm | 200 | `OK` |
| Nhánh nhóm | 201 | `OK` |
| Nhánh lỗi không tìm thấy | 404 | `MISSING` |
| Nhánh throw | 500 | `IllegalStateException("REMOTE_ERROR")` |
| Nhánh mặc định | 0, -1, 202, 409, 501 | `UNKNOWN` |
| Giá trị biên `int` | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | `UNKNOWN` |

Đối với `instanceof`, dùng bảng ở phần 4.3, bổ sung các subtype/implementation có thể đi qua nhiều nhánh và những object có state không hợp lệ theo nghiệp vụ.

**Quy tắc chọn ca:**
- Mỗi nhánh riêng, **mỗi nhãn trong case nhóm**.
- `default`/`else` và input **không khớp**.
- Giá trị sát biên (ví dụ 199/200/201/202).
- `null`, rỗng, whitespace và Unicode.
- Exceptions, kể cả failure path.
- Kiểu con/multiple interfaces nếu có.
- Input dùng chung với serialization/API cũ nếu code nằm trong thư viện.
- Side effects/trace và idempotence khi áp dụng.

Không tự đồng nhất **coverage cao** với tương đương hành vi. Branch coverage có thể đạt 100% nhưng một nhãn `case 201` bị bỏ sót nếu chỉ test 200 để đi qua nhánh thành công.

## 7. Ví dụ Java 17+ hoàn chỉnh: differential testing có chủ đích

Bài thực hành tạo **một chương trình Java duy nhất**, không yêu cầu JUnit hay phụ thuộc ngoài JDK. Chương trình chứa cả trước và sau refactor, kiểm tra:

- `switch` trên `int`: 13 ca được chọn và **5.000 input ngẫu nhiên có seed cố định**.
- Các trường hợp ném `IllegalStateException` có message nghiệp vụ.
- `instanceof`: 10 loại input, gồm `null`, String, Number và object không khớp.
- `switch(String)`: 5 input, gồm `null` và một `new String("A")`.
- Một selector có side effect: mỗi phiên bản chỉ đọc selector một lần.
- Một bản refactor **cố ý sai**: bỏ sót `case 201`; test phải phát hiện sai khác.

### 7.1. Toàn bộ file `RefactoringCompatibilityDemo.java`

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.IntSupplier;

public class RefactoringCompatibilityDemo {
    record Outcome(boolean failed, String detail) {}

    static String beforeStatus(IntSupplier selector) {
        String result;
        switch (selector.getAsInt()) {
            case 200:
            case 201:
                result = "OK";
                break;
            case 404:
                result = "MISSING";
                break;
            case 500:
                throw new IllegalStateException("REMOTE_ERROR");
            default:
                result = "UNKNOWN";
                break;
        }
        return result;
    }

    static String afterStatus(IntSupplier selector) {
        return switch (selector.getAsInt()) {
            case 200, 201 -> "OK";
            case 404 -> "MISSING";
            case 500 -> throw new IllegalStateException("REMOTE_ERROR");
            default -> "UNKNOWN";
        };
    }

    static String oldStatus(int status) {
        return beforeStatus(() -> status);
    }

    static String newStatus(int status) {
        return afterStatus(() -> status);
    }

    static String brokenStatus(int status) {
        return switch (status) {
            case 200 -> "OK";
            case 404 -> "MISSING";
            case 500 -> throw new IllegalStateException("REMOTE_ERROR");
            default -> "UNKNOWN";
        };
    }

    static String oldType(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "S:" + text.strip().toUpperCase(Locale.ROOT);
        }
        if (value instanceof Number) {
            Number number = (Number) value;
            return "N:" + number.longValue();
        }
        return "OTHER";
    }

    static String newType(Object value) {
        if (value instanceof String text) {
            return "S:" + text.strip().toUpperCase(Locale.ROOT);
        }
        if (value instanceof Number number) {
            return "N:" + number.longValue();
        }
        return "OTHER";
    }

    static String oldTextSwitch(String text) {
        switch (text) {
            case "A": return "ALPHA";
            case "B": return "BETA";
            default: return "OTHER";
        }
    }

    static String newTextSwitch(String text) {
        return switch (text) {
            case "A" -> "ALPHA";
            case "B" -> "BETA";
            default -> "OTHER";
        };
    }

    static Outcome observe(IntFunction<String> function, int input) {
        try {
            return new Outcome(false, function.apply(input));
        } catch (RuntimeException ex) {
            return new Outcome(true,
                    ex.getClass().getSimpleName() + ":" + ex.getMessage());
        }
    }

    static Outcome observeString(Function<String, String> function, String input) {
        try {
            return new Outcome(false, function.apply(input));
        } catch (RuntimeException ex) {
            return new Outcome(true, ex.getClass().getSimpleName());
        }
    }

    static void same(Object oldValue, Object newValue, String caseName) {
        if (!Objects.equals(oldValue, newValue)) {
            throw new AssertionError(caseName + ": before=" + oldValue
                    + ", after=" + newValue);
        }
    }

    public static void main(String[] args) {
        int[] boundaries = {
                Integer.MIN_VALUE, -1, 0, 199, 200, 201, 202,
                404, 409, 499, 500, 501, Integer.MAX_VALUE
        };
        for (int value : boundaries) {
            same(observe(RefactoringCompatibilityDemo::oldStatus, value),
                    observe(RefactoringCompatibilityDemo::newStatus, value),
                    "switch:" + value);
        }

        Random random = new Random(2026L);
        for (int i = 0; i < 5_000; i++) {
            int value = random.nextInt(2_001) - 1_000;
            same(observe(RefactoringCompatibilityDemo::oldStatus, value),
                    observe(RefactoringCompatibilityDemo::newStatus, value),
                    "random-switch:" + value);
        }

        Object[] objects = {
                null, "", " hello ", "\u2002x\u2002", Integer.valueOf(7),
                Double.valueOf(2.5), Long.valueOf(8),
                new BigDecimal("123.45"), new StringBuilder("hi"),
                Boolean.TRUE
        };
        for (int i = 0; i < objects.length; i++) {
            same(oldType(objects[i]), newType(objects[i]), "instanceof:" + i);
        }

        String[] texts = {null, "A", new String("A"), "B", "C"};
        for (String text : texts) {
            same(observeString(RefactoringCompatibilityDemo::oldTextSwitch, text),
                    observeString(RefactoringCompatibilityDemo::newTextSwitch, text),
                    "string-switch");
        }

        AtomicInteger beforeReads = new AtomicInteger();
        AtomicInteger afterReads = new AtomicInteger();
        same(beforeStatus(() -> {
                    beforeReads.incrementAndGet();
                    return 200;
                }),
                afterStatus(() -> {
                    afterReads.incrementAndGet();
                    return 200;
                }), "selector-value");
        same(1, beforeReads.get(), "old-selector-count");
        same(1, afterReads.get(), "new-selector-count");

        boolean regressionDetected = !Objects.equals(
                observe(RefactoringCompatibilityDemo::oldStatus, 201),
                observe(RefactoringCompatibilityDemo::brokenStatus, 201));
        same(true, regressionDetected, "intentional-regression");

        // Oracle độc lập từ yêu cầu nghiệp vụ, không chỉ so hai bản với nhau.
        same("OK", newStatus(200), "golden-200");
        same("OK", newStatus(201), "golden-201");
        same("MISSING", newStatus(404), "golden-404");
        same("S:HELLO", newType(" hello "), "golden-type");
        same("ALPHA", newTextSwitch(new String("A")), "golden-string");

        System.out.println("fixedSwitchCases=" + boundaries.length);
        System.out.println("randomSwitchCases=5000");
        System.out.println("exception500=" +
                observe(RefactoringCompatibilityDemo::oldStatus, 500).detail());
        System.out.println("instanceofCases=" + objects.length);
        System.out.println("instanceofNull=" + newType(null));
        System.out.println("stringSwitchCases=" + texts.length);
        System.out.println("stringNullException=" +
                observeString(RefactoringCompatibilityDemo::oldTextSwitch, null).detail());
        System.out.println("selectorEvaluations=" + beforeReads.get()
                + "," + afterReads.get());
        System.out.println("intentionalRegressionDetected=" + regressionDetected);
        System.out.println("ALL_PASS");
    }
}
```

### 7.2. Lệnh biên dịch và chạy

Dùng **JDK đầy đủ từ Java 17 trở lên**, tại thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 RefactoringCompatibilityDemo.java
java RefactoringCompatibilityDemo
```

**Đầu ra mong đợi trên JDK Java 17+ với chương trình trên:**

```text
fixedSwitchCases=13
randomSwitchCases=5000
exception500=IllegalStateException:REMOTE_ERROR
instanceofCases=10
instanceofNull=OTHER
stringSwitchCases=5
stringNullException=NullPointerException
selectorEvaluations=1,1
intentionalRegressionDetected=true
ALL_PASS
```

**Đầu ra đã kiểm chứng:** bản chương trình tương đương về các phương thức và kiểm tra so sánh đã được **biên dịch bằng `javac --release 17` và chạy trên JDK hiện đại** với chính mười dòng trên. Các assertion "golden" bổ sung trong listing đều đối chiếu với những giá trị đã được xác minh; chúng không tạo thêm stdout khi thành công.

Nếu có bất kỳ sai khác nào, phương thức `same(...)` ném `AssertionError` với tên ca và hai giá trị đối chiếu. Khi lỗi xảy ra, **không có dòng `ALL_PASS`**; tiến trình `java` thoát không thành công.

### 7.3. Vì sao cấu trúc test dùng `Outcome`?

`switch` status 500 **phải ném** `IllegalStateException("REMOTE_ERROR")`. Nếu một bản thay vì throw lại trả `"UNKNOWN"`, chỉ so chuỗi đầu ra của các ca khác sẽ bỏ sót hồi quy.

`observe(...)` biến:
- Một lời gọi thành công thành `Outcome(false, value)`.
- Một `RuntimeException` thành `Outcome(true, "ClassName:message")`.

Vì `Outcome` là `record` (tính năng chính thức từ Java 16), `Objects.equals` so sánh cấu trúc hai trường một cách trực tiếp. Trong phần test `switch(String)` với `null`, `observeString(...)` cố ý chuẩn hóa **tên lớp exception** (NPE) nhưng không so **message NPE phụ thuộc ngữ cảnh nguồn**.

**Lưu ý:** Bắt `RuntimeException` chỉ thích hợp để **ghi nhận một kết quả mong đợi trong test**, không phải thiết kế chính sách exception chung cho mọi production API. Không bắt `Throwable` rộng rồi che lỗi hệ thống nghiêm trọng.

### 7.4. Vì sao vừa có ca cố định, vừa có random?

- **13 ca cố định:** bảo đảm các nhánh quan trọng như 200, 201, 404, 500 được gọi, kèm min/max của `int` và các giá trị gần biên.
- **5.000 ca pseudo-random:** mở rộng miền kiểm tra với `new Random(2026L)`; seed cố định để test có thể lặp lại và debug.
- **Golden assertions:** một số kết quả được xác nhận với **yêu cầu độc lập**, không chỉ "hai phiên bản cùng trả một thứ".
- **Mutation/negative check:** `brokenStatus` bỏ sót 201; `intentionalRegressionDetected=true` chứng minh bộ kiểm thử thật sự nhạy với một lỗi điển hình.
- **Side-effect counters:** cả hai bản đánh giá selector đúng **một lần** theo kỳ vọng.

**Không nên chỉ dùng random:** phân phối `nextInt(...)` có thể không bao giờ chạm một nhánh hiếm, nên random **không thay thế** bảng nhánh/biên. Ngược lại, chỉ 13 ca cố định cũng không thay thế các ca dữ liệu thực hoặc thuộc tính ở miền lớn.

### 7.5. Kiểm thử `instanceof` thực tế

Mảng `objects` có:

- `null`, chuỗi rỗng, chuỗi có whitespace, chuỗi có Unicode space.
- Các lớp con cụ thể của `Number`: `Integer`, `Double`, `Long`, `BigDecimal`.
- `StringBuilder`, một object có thể bị nhầm là `String` nếu thay pattern bằng `CharSequence`.
- `Boolean` không thuộc nhánh nào.

Khi cả hai bản trả một giá trị giống nhau, kiểm thử differential **PASS**. Nếu một refactor vô tình đổi thứ tự nhánh hoặc đổi `Number.longValue()` thành một conversion khác, một số ca sẽ bắt được. Với production, phải bổ sung các kiểu class/interface thật của hệ thống.

### 7.6. Kiểm thử `switch(String)`

`texts` gồm:
- `null` để kiểm tra `NullPointerException` ở hai bản Java 17.
- `"A"` và `new String("A")` để xác nhận so khớp **giá trị chuỗi**, không phải identity.
- `"B"` và `"C"` để kiểm tra case còn lại và default.

Nếu migrate sang Java 21+ và muốn `case null`, hãy **tách thành thay đổi hành vi có mục đích**, đưa một golden test mới vào contract và cập nhật yêu cầu trước khi đổi code.

## 8. Từ demo sang kiểm thử JUnit/CI trong dự án thực

Chương trình trên dùng `AssertionError` để **không phụ thuộc thư viện ngoài**. Trong dự án Java hiện đại đã có bộ test tự động, có thể áp dụng cùng chiến lược qua **JUnit Jupiter 5** hoặc runner kiểm thử được đội ngũ sử dụng.

### 8.1. Thiết kế test parameterized

Cách suy nghĩ:

```text
given input
  |
  +--> before(input) --> Outcome trước
  |
  +--> after(input)  --> Outcome sau
                              |
                              v
                    assertEquivalent(...)
                              |
                              v
                 assertExpectedFromContract(...)
```

Khi lập test:
1. Bảo toàn **phiên bản trước** trong một nhánh/commit hoặc dùng một implementation đối chứng không bị sửa cùng lúc.
2. Tạo **test fixtures có tên**, ví dụ `status_200_success`, `status_201_success`, `status_500_throws`.
3. Dùng parameterized test (`@MethodSource`, `@CsvSource` hoặc framework phù hợp) để mỗi input có report riêng.
4. Với exception, kiểm tra `assertThrows` và thuộc tính nghiệp vụ đã định, không phụ thuộc cả stack trace nếu không phải contract.
5. Với stateful code, chạy từng trường hợp trên đối tượng/fixture **độc lập và cùng trạng thái ban đầu**.
6. Với side effects, dùng fake/spy ghi trace và so **thứ tự**.
7. Với random/property-based testing, lưu **seed và input gây lỗi**, để tái lập nhanh.
8. Với public API, kiểm tra cả tương thích nguồn và nhị phân khi refactor chạm chữ ký/module; hành vi tương đương **không tự chứng minh API compatibility**.

**Không nhất thiết sao chép nguyên mã cũ lâu dài trong production:** có thể dùng một **golden corpus** từ release trước, lưu input→outcome và state trong test fixtures. Tuy nhiên, fixture phải được cập nhật **khi có thay đổi nghiệp vụ được duyệt**, không đơn giản ghi đè kết quả mong đợi cho test xanh.

### 8.2. Vì sao 100% branch coverage vẫn chưa đủ?

Một bộ test chỉ có `status=200` đã chạy nhánh “OK” của bản cũ. Sau khi quên mất `case 201`, branch “OK” của bản mới cũng vẫn được test. Coverage có thể cao mà **ca 201** vẫn sai.

Bổ sung:
- **Decision-table coverage** cho từng nhãn và mọi nhóm nhãn.
- **Boundary-value testing** cho giá trị sát miền.
- **Mutation testing** để xem bộ test có bắt được việc xóa một case không.
- **Differential testing** cũ/mới với số lượng input lớn.
- **Property tests** cho bất biến logic (ví dụ cùng nhóm status có cùng kết quả, null xử lý như hợp đồng).
- **Snapshot/approval tests** khi output có cấu trúc; tránh snapshot những chi tiết ngẫu nhiên/không được cam kết.

### 8.3. Kiểm thử loại trừ lỗi của chính bộ test

Một test chỉ so `before(input)` với `after(input)` **mà không bao giờ assert một giá trị đúng cụ thể** có thể PASS dù cả hai cùng bị sai. Vì vậy phần demo có thêm:

```java
same("OK", newStatus(200), "golden-200");
same("OK", newStatus(201), "golden-201");
same("MISSING", newStatus(404), "golden-404");
same("S:HELLO", newType(" hello "), "golden-type");
```

Đây là **đoạn minh họa lấy từ phương thức `main`**. Các giá trị bên trái phải bắt nguồn từ **yêu cầu nghiệp vụ**, không được sinh tự động từ bản `after` cần kiểm thử.

### 8.4. Test với state và I/O

Với code có ghi log, file, database hoặc gửi event, **kết quả trả về giống nhau có thể chưa đủ**. Đối với cùng input, hãy:

- Cấu hình hai fixture giống nhau và cách ly dữ liệu trước/sau.
- Capture danh sách sự kiện đã gửi hoặc lệnh ghi, so theo thứ tự/ý nghĩa hợp đồng.
- Kiểm tra state cuối, số lần gọi và dữ liệu quan trọng.
- Dùng đồng hồ giả, random seed và dependency giả để tránh nondeterminism.
- Không so nguyên vẹn các giá trị không được cam kết như thời điểm thực, UUID ngẫu nhiên hoặc thread scheduling.
- Với race/concurrency, cần thêm test riêng hoặc stress tests; không để refactoring thay đổi khóa/đồng bộ nếu không có lý do.

## 9. Những khác biệt do phiên bản Java cần chú ý

### Java 14: `switch` expression chính thức

Java 14 chuẩn hóa `switch` expression và `yield` theo JEP 361. Hướng dẫn hiện tại nên dùng:

```java
int result = switch (code) {
    case 1 -> 10;
    default -> {
        yield 0;
    }
};
```

Đây là **đoạn minh họa trong phương thức** với `code` có kiểu phù hợp; không dùng cú pháp `break 10;` của các phiên bản preview trước đó.

### Java 16: pattern matching `instanceof` chính thức

Cú pháp:

```java
if (value instanceof String s) {
    System.out.println(s.length());
}
```

là tính năng **chính thức từ Java 16**, tiếp tục dùng trong Java 17+. Nó không cần `--enable-preview`; ví dụ chính biên dịch bằng `--release 17`.

### Java 21+: pattern matching for `switch`

Java 21 chuẩn hóa pattern matching for `switch` (JEP 441), cho phép các nhãn mới và `case null`. Ví dụ Java 21+ minh họa:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        default -> "OTHER";
    };
}
```

Đoạn này **không thuộc mã `--release 17` của phần 7**. Khi chuyển từ chuỗi `if-else instanceof` sang pattern switch Java 21+, phải kiểm tra **thứ tự và khả năng bao phủ pattern, dominance, guard, null, type/case grouping**, cùng side effects. Đây **không còn là chuyển đổi cú pháp 1:1 đơn giản**, nên các ca trong ma trận phần 6 càng quan trọng.

## 10. Các lỗi refactor phổ biến và cách phát hiện

| Sai lầm | Hành vi có thể thay đổi | Test cần thêm |
| --- | --- | --- |
| Bỏ sót `case 201` khi gộp các nhãn | 201 rơi vào default | Test từng giá trị trong nhóm |
| Đổi `case :` sang `case ->` mà quên fall-through có chủ đích | Mất hành động ở nhánh tiếp | So trace và kết quả |
| Thay `break` bằng `yield` không đúng nơi | Code không compile hoặc trả sai giá trị | Compile + kiểm thử output nhánh |
| Tự thêm `default` trả một giá trị mới | Che missing-case hoặc đổi fallback | Golden tests, enum evolution |
| Đổi exception thành giá trị dự phòng | Người gọi không còn thấy lỗi như trước | `assertThrows`/Outcome test |
| Đổi kiểu hoặc thông điệp exception nghiệp vụ | Phá hợp đồng quan sát được | So class, code, message được cam kết |
| Đọc selector thêm lần khi refactor | Tăng side effects và chi phí | Spy/counter gọi selector |
| Chuyển `if (value instanceof String)` thành `if (value instanceof String s && !s.isBlank())` | Chuỗi rỗng bị đổi nhánh | Test rỗng và blank |
| Đổi `String` thành `CharSequence` | Bắt thêm `StringBuilder` | Test kiểu implement interface |
| Đổi thứ tự các nhánh `instanceof` có quan hệ subtype | Nhánh được chọn khác | Test đối tượng kiểu con |
| Thay `longValue()` thành `intValue()`/`round()` | Số lớn/số thập phân ra kết quả khác | Test biên số |
| Thay `strip()` bằng `trim()` | Unicode whitespace khác | Test whitespace Unicode |
| Quên `null` ở `instanceof` | Tưởng null khớp pattern | Test `null` |
| Thêm xử lý null ở `switch(String)` không có trong bản cũ | NPE thành giá trị mới | Test null + exception type |
| Dùng `==` thay cho so khớp chuỗi của `switch` | `new String("A")` không khớp | Test hai object cùng nội dung |
| Biến `switch` expression thành nested ternary khác precedence | Đổi thứ tự đánh giá hoặc kiểu kết quả | Test side effects và type boundaries |
| Chỉ test happy path | Không có bằng chứng cho default/error | Nhánh lỗi, boundary, null |
| Chỉ test random không seed | Lỗi khó tái lập | Seed cố định, in input khi fail |
| Chỉ dựa vào coverage | Case cụ thể bị mất dù nhánh đã được chạy | Decision-table + mutation |
| Chỉ so trước/sau | Có thể bảo toàn lỗi cũ | Golden/business tests độc lập |
| So toàn stack trace sau refactor | Failing false positive do số dòng khác | Chuẩn hóa theo contract |
| Dùng preview code Java 14 trong build hiện đại | Mã lỗi thời hoặc không compile | Dùng tính năng chính thức Java 17+ |

## 11. Bài tập có đáp án

**Câu 1.** Tại sao biên dịch thành công sau khi chuyển `switch` statement thành expression chưa đủ?  
**Đáp án:** Compiler không biết mọi quy tắc nghiệp vụ cũ; có thể bỏ sót nhãn case, đổi default, exception hoặc side effects mà cú pháp vẫn hợp lệ.

**Câu 2.** `case 200: case 201:` chuyển thành rule nào khi cả hai cùng trả `OK`?  
**Đáp án:** `case 200, 201 -> "OK";`, với kiểm thử cả 200 và 201.

**Câu 3.** Trong switch expression, vì sao `yield` khác `break`?  
**Đáp án:** `yield` cung cấp giá trị của biểu thức switch, còn `break` thoát khỏi switch statement/loop theo ngữ nghĩa hiện hành.

**Câu 4.** Có thể kết luận `case 0 -> ...` là switch expression không?  
**Đáp án:** Không. Switch **statement** cũng hỗ trợ arrow rule; cần xét switch có đang được sử dụng như expression trả giá trị không.

**Câu 5.** `value instanceof String s` với `value=null` trả gì?  
**Đáp án:** `false`, pattern variable không được gán/đưa vào scope nhánh đúng.

**Câu 6.** Mã cũ chấp nhận mọi String, mã mới thêm `&& !s.isBlank()` có tương đương không?  
**Đáp án:** Không, các String rỗng/toàn khoảng trắng đổi nhánh. Đây là thay đổi hành vi cần duyệt riêng.

**Câu 7.** Có `default` trong `switch(String)` Java 17 thì `null` có đi vào default không?  
**Đáp án:** Không. Selector null gây `NullPointerException` trong switch cổ điển; test phải ghi nhận ngoại lệ.

**Câu 8.** Vì sao test `new String("A")` hữu ích?  
**Đáp án:** Nó phát hiện refactor sai từ so khớp theo **nội dung chuỗi** sang so sánh tham chiếu `==`.

**Câu 9.** Test refactor phải so sánh những gì ngoài return value?  
**Đáp án:** Ngoại lệ, side effects, thứ tự tác vụ, state thay đổi, số lần đánh giá biểu thức và lỗi nghiệp vụ nếu chúng thuộc contract.

**Câu 10.** Một random test có seed cố định có thay thế boundary tests không?  
**Đáp án:** Không. Random có thể bỏ sót case hiếm; cần các giá trị biên và bảng quyết định tường minh.

**Câu 11.** Tại sao cần golden expected results ngoài việc so before/after?  
**Đáp án:** Cả hai có thể cùng sai. Golden tests xác nhận yêu cầu nghiệp vụ độc lập.

**Câu 12.** Ý nghĩa của `intentionalRegressionDetected=true` trong demo là gì?  
**Đáp án:** Bộ test so sánh nhận ra bản sai `brokenStatus` đã bỏ case 201, nên không chỉ xác nhận hai bản code luôn trùng khớp.

**Câu 13.** Nếu refactor đổi thứ tự các điều kiện `instanceof`, cần thử gì?  
**Đáp án:** Object có subtype/implements nhiều interface, null và các giá trị tương ứng nhánh để phát hiện đổi thứ tự lựa chọn.

**Câu 14.** Pattern matching `instanceof` là tính năng chính thức từ Java nào?  
**Đáp án:** Java 16; trong Java 17+ không cần preview flags.

**Câu 15.** Khi dùng Java 21 pattern switch có `case null`, có phải luôn là refactor hành vi bất biến từ switch String Java 17?  
**Đáp án:** Không. Nếu bản cũ ném NPE cho null còn bản mới trả giá trị, đó là thay đổi hợp đồng; cần test và duyệt riêng.

## 12. Quy trình thực tế trước khi merge PR

Một quy trình gọn, có thể audit:

1. **Đóng băng hợp đồng**: ghi lại behavior cần giữ (đầu ra, lỗi, side effects, null).
2. **Lấy dữ liệu đầu vào thực tế được phép dùng** hoặc fixture đã được làm sạch, không đem thông tin riêng tư vào repo/test logs.
3. **Xây bảng quyết định** gồm từng case/nhánh, default, lỗi, null và biên.
4. **Chạy test trước refactor**; nếu test hiện đỏ, làm rõ lỗi cũ để không nhầm thành hồi quy mới.
5. **Refactor từng bước nhỏ**: switch statement → expression hoặc instanceof + cast → pattern. Không trộn thay đổi nghiệp vụ khác.
6. **Chạy test sau refactor**, so differential và golden expectations; kiểm tra side effects và exception types.
7. **Thêm random/property-based và mutation tests** theo mức độ rủi ro; giữ seed và minimal failing input.
8. **Kiểm tra build theo target JDK**, ví dụ `javac --release 17`, không vô tình dùng preview features của JDK mới.
9. **Chạy CI/linter/static analysis** và code review; giữ thay đổi có thể đọc và không mở rộng quyền/module không cần thiết.
10. **Merge khi có bằng chứng**: list cases, kết quả tests, JDK versions, rủi ro còn lại và lý do đổi hành vi nếu có.

Tối thiểu, một thay đổi cấu trúc nên trả lời được: “**Đã chứng minh cùng kết quả bằng những input nào, đã kiểm tra những ngoại lệ và tác dụng phụ nào, và những trường hợp nào vẫn chưa được bao phủ?**”

## 13. Tổng kết và tài liệu chính thức

**Nguyên tắc:** Để chứng minh một lần tái cấu trúc `switch` hoặc `instanceof` không làm đổi hành vi, đừng chỉ nhìn code ngắn hơn. Hãy kết hợp **bảng quyết định + phép đối chiếu cũ/mới + kỳ vọng nghiệp vụ độc lập + kiểm tra lỗi/side effects + ca biên và ngẫu nhiên có seed**. Các đoạn Java 17+ trong bài dùng **cú pháp đã chính thức**, không phụ thuộc preview hay legacy API.

**Tài liệu chính thức, còn áp dụng:**

- [Oracle Java SE 14 — Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html): `switch` expression, `case ... ->`, `yield` được chuẩn hóa từ Java 14.
- [Oracle Java SE 16 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/16/language/pattern-matching-instanceof-operator.html): cú pháp pattern type test, cast và flow scoping chính thức từ Java 16.
- [Oracle Java SE 17 — JLS `14.11 switch statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statement, case labels, fall-through và quy tắc ngôn ngữ.
- [Oracle Java SE 17 — JLS `15.28 switch expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): biểu thức `switch`, giá trị và quy tắc đánh giá.
- [Oracle Java SE 17 — JLS `15.20.2 instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): điều kiện match, null và type patterns.
- [Oracle Java SE 17 — JLS `6.3 Pattern Variable Scope](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): flow scoping của pattern variables.
- [Oracle Java SE 21 — JLS Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): cú pháp `case null` và pattern switch.
- [Oracle Java SE 23 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/23/language/switch-expressions-and-statements.html): hướng dẫn chính thức về exhaustiveness và các kiểu nhánh Java hiện đại.
