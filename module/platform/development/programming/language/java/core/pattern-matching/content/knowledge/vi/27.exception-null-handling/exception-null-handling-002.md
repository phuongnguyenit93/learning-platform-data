# Pattern matching hoàn tất bất thường (Java 21)

## 1. Khái niệm: không khớp khác với hoàn tất bất thường

**Pattern matching** là quá trình kiểm tra một giá trị tại runtime với một mẫu (*pattern*), chẳng hạn type pattern `String s` hoặc record pattern `Point(int x, int y)`. Nếu khớp, các pattern variables được ràng buộc để dùng trong phạm vi hợp lệ.

Theo Java Language Specification (JLS) `14.30.2, có hai nhóm kết quả ở cấp **quá trình matching**:

- **Hoàn tất bình thường (*normal completion*):** Matching kết thúc mà không ném exception; kết quả có thể là **khớp** hoặc **không khớp**.
- **Hoàn tất bất thường (*abrupt completion*):** Trong khi xác định có khớp hay không, một phép đánh giá liên quan ném exception, làm quá trình matching dừng. Ở cấp **pattern matching**, lý do hoàn tất bất thường là **`throw`**, không phải một giá trị `false`.

Điều này đặc biệt quan trọng ở Java 21 vì **record patterns** có thể gọi accessor ngầm để đọc các component. Nếu accessor ném lỗi, Java có cơ chế `MatchException`. Guard `when` và biểu thức selector của `switch` cũng có thể ném exception, nhưng không phải lúc nào cũng bị đổi thành `MatchException`.

| Tình huống | Kết quả | Có thử nhánh tiếp theo không? |
| --- | --- | --- |
| `Object` không phải `String` khi kiểm tra `instanceof String s` | Matching hoàn tất bình thường, **không khớp** | Với `switch`, có thể xét case tiếp theo |
| Selector `null` trong `instanceof SomeRecord(...)` | Hoàn tất bình thường, **không khớp** | `instanceof` trả `false` |
| Nested record component `null` trước pattern record con | Pattern record con **không khớp** bình thường | Có thể xét case khác; vẫn có rủi ro exhaustive runtime |
| Record component accessor ném exception | **Abrupt completion**, ném `MatchException` | **Không** tiếp tục sang case dự phòng |
| Guard `when` ném exception | Quá trình chọn case **abrupt** với exception gốc | **Không** tiếp tục sang case dự phòng |
| Guard `when` trả `false` | Nhánh đó không áp dụng, không phải exception | **Có**, xét case tiếp theo |
| Selector của `switch` ném exception | `switch` kết thúc bất thường với exception gốc | Không bắt đầu matching |
| Selector `null` nhưng `switch` không có nhánh nhận null | `NullPointerException` khi chọn nhánh | `default` đơn thuần không bắt null |
| Không có pattern nào khớp trong switch vốn được xem là exhaustive | Có thể ném `MatchException` ở runtime | Không có kết quả bình thường |

**Phạm vi phiên bản:** Type patterns với `instanceof` là tính năng chuẩn từ Java 16. **Record patterns** (JEP 440) và **pattern matching cho `switch`** (JEP 441) chính thức từ **Java 21**, không cần `--enable-preview`. Bài này dùng cú pháp Java 21, nơi `java.lang.MatchException` đã có sẵn.

## 2. Ba vị trí khác nhau có thể ném exception

Để phân tích chính xác, nên chia việc xử lý pattern thành các giai đoạn:

1. **Đánh giá biểu thức đầu vào (*selector / operand*)**. Ví dụ `getValue() instanceof String s` phải gọi `getValue()` trước; `switch (getValue())` cũng phải đánh giá `getValue()` trước.
2. **Đối chiếu pattern**. Với type pattern thông thường, Java kiểm tra kiểu; với record pattern, runtime phải truy cập các record component bằng accessor rồi tiếp tục kiểm tra các component pattern, kể cả record pattern lồng nhau.
3. **Đánh giá guard `when`** của một case `switch`, nếu pattern đã khớp và case có guard.
4. **Thực thi phần thân nhánh được chọn**. Phần thân có thể tính toán, gọi method, `throw`, `return` hoặc điều khiển luồng.

Nếu exception xuất hiện ở mỗi vị trí, cách quan sát là khác nhau:

- Exception từ **biểu thức đầu vào** được truyền ra như chính exception đó; pattern chưa được so khớp.
- Exception từ **record accessor được gọi ngầm trong quá trình deconstruction** được bọc thành `MatchException` với `cause` là exception gốc, theo JLS `14.30.2.
- Exception từ **guard** được truyền ra với cùng lý do, theo các quy tắc chọn nhánh của `switch`; không tự chuyển thành `MatchException`.
- Exception do **phần thân case** tự ném là lỗi khi thực thi business logic đã được chọn, không phải sự thất bại của pattern matching. Nó được truyền ra theo luật Java thông thường.

Không nên gọi chung mọi exception phát sinh quanh `switch` là “lỗi pattern”: một lỗi từ code nghiệp vụ trong case body khác với lỗi trong giai đoạn matching hoặc lựa chọn case.

## 3. Ví dụ Java 21 chạy được: mô phỏng từng trường hợp

Tạo file **`AbruptPatternDemo.java`**:

```java
public class AbruptPatternDemo {
    sealed interface Choice permits Yes, No {}

    record Yes() implements Choice {}
    record No() implements Choice {}
    record Wrapper(Choice choice) {}

    record Item(String text) {}
    record Outer(Item item) {}

    record Fragile(String text) {
        @Override
        public String text() {
            throw new IllegalStateException("accessor failed");
        }
    }

    static boolean guard(String text) {
        throw new IllegalArgumentException("guard failed");
    }

    static Object selector() {
        throw new IllegalArgumentException("selector failed");
    }

    static String guarded(Object value) {
        return switch (value) {
            case String text when guard(text) -> "guarded";
            case String text -> "plain";
            case null -> "null";
            default -> "other";
        };
    }

    static String noNullCase(Object value) {
        return switch (value) {
            case String text -> "text";
            default -> "other";
        };
    }

    static String nested(Wrapper value) {
        return switch (value) {
            case Wrapper(Yes yes) -> "yes";
            case Wrapper(No no) -> "no";
        };
    }

    static String bodyThrows(Object value) {
        return switch (value) {
            case String text ->
                throw new UnsupportedOperationException("body failed");
            case null -> "null";
            default -> "other";
        };
    }

    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": completed");
        } catch (RuntimeException ex) {
            String cause = ex.getCause() == null
                ? "none" : ex.getCause().getClass().getSimpleName();
            System.out.println(label + ": "
                + ex.getClass().getSimpleName() + ", cause=" + cause);
        }
    }

    public static void main(String[] args) {
        Object wrong = new Item("hello");
        Object missing = null;
        Object innerNull = new Item(null);
        Object nestedNull = new Outer(null);

        System.out.println("differentType="
            + (wrong instanceof Fragile(String s)));
        System.out.println("nullType="
            + (missing instanceof Item(String s)));
        System.out.println("nullComponent="
            + (innerNull instanceof Item(String s)));
        System.out.println("nullNested="
            + (nestedNull instanceof Outer(Item(String s))));

        test("accessor", () -> {
            Object value = new Fragile("demo");
            boolean matches = value instanceof Fragile(String s);
        });
        test("guard", () -> guarded("hello"));
        test("selector", () -> guarded(selector()));
        test("nullSelector", () -> noNullCase(null));
        test("nestedExhaustive", () -> nested(new Wrapper(null)));
        test("caseBody", () -> bodyThrows("hello"));

        System.out.println("normalNested="
            + nested(new Wrapper(new Yes())));
    }
}
```

Dùng **JDK 21 trở lên**:

```bash
javac --release 21 AbruptPatternDemo.java
java AbruptPatternDemo
```

**Stdout chính xác:**

```text
differentType=false
nullType=false
nullComponent=true
nullNested=false
accessor: MatchException, cause=IllegalStateException
guard: IllegalArgumentException, cause=none
selector: IllegalArgumentException, cause=none
nullSelector: NullPointerException, cause=none
nestedExhaustive: MatchException, cause=none
caseBody: UnsupportedOperationException, cause=none
normalNested=yes
```

Ví dụ cố ý ném exception ở một số trường hợp, nhưng `test` bắt chúng để chương trình vẫn chạy qua các tình huống còn lại. Code trong `main` không mở file, không truy cập mạng hay phụ thuộc thư viện bên ngoài JDK.

## 4. Không khớp bình thường: false không phải exception

Ở bốn dòng đầu:

**`differentType=false`:** `wrong` chứa một `Item`, không phải `Fragile`. `wrong instanceof Fragile(String s)` trả `false`. Không có exception và không có biến pattern `s` nào được dùng ngoài nhánh khớp.

**`nullType=false`:** `missing` là `null`. Một `instanceof Item(String s)` với selector null trả `false`; record pattern không khớp tham chiếu null.

**`nullComponent=true`:** `innerNull` là `new Item(null)`, tức record ngoài có thật nhưng component `text` bằng null. `Item(String s)` là record pattern có **type pattern `String s` tại vị trí component khai báo kiểu `String`**. Trong Java 21, type pattern unconditional đối với kiểu component tương ứng là **null-matching** ở vị trí này, nên `s` có thể được ràng buộc với null. Không suy ra từ đó rằng `null instanceof String` sẽ thành true.

**`nullNested=false`:** `nestedNull` là `new Outer(null)`. Pattern `Outer(Item(String s))` đòi component `item` khớp một record `Item` thực sự. `item == null` làm nested **record pattern** không khớp; kết quả toàn bộ `instanceof` là false, chứ không ném exception.

Điểm mấu chốt: **null ở selector**, **null ở component có type pattern unconditional**, và **null ở record pattern lồng nhau** có thể cho ba kết quả khác nhau. Phải đọc đúng vị trí của `null` trong cấu trúc.

## 5. Record accessor ném exception: MatchException với cause

Trong code, record `Fragile` ghi đè accessor `text()`:

```java
record Fragile(String text) {
    @Override
    public String text() {
        throw new IllegalStateException("accessor failed");
    }
}
```

Khi matching `value instanceof Fragile(String s)`, runtime cần đọc component `text` để kiểm tra pattern tương ứng. Việc đọc component của record pattern sử dụng **accessor method**. Accessor bị ném `IllegalStateException`, nên Java 21 cho quá trình matching kết thúc bất thường bằng một **`MatchException`** có `cause` là lỗi gốc.

Kết quả:

```text
accessor: MatchException, cause=IllegalStateException
```

Đây không phải:
- `false` do record pattern không khớp;
- `ClassCastException` của một phép cast thủ công;
- một nhánh `default` có thể bắt thay;
- một exception được ném từ phần thân case.

Có thể quan sát nguyên nhân bằng:

```java
// Đoạn minh họa khi đã có Object value:
try {
    if (value instanceof Fragile(String text)) {
        System.out.println(text);
    }
} catch (MatchException ex) {
    Throwable root = ex.getCause();
    System.err.println("Pattern matching failed: " + root);
    throw ex; // Hoặc xử lý theo contract ứng dụng.
}
```

Mã trên là **đoạn minh họa**, cần có type `Fragile` từ chương trình và biến `value`. `MatchException` là unchecked exception (`RuntimeException`), nên `catch (RuntimeException ex)` cũng bắt được, nhưng trong bài học nên nhận diện đúng kiểu lỗi trước khi quyết định xử lý.

**Lưu ý:** Record accessor mặc định thường chỉ trả về component. Việc tự ghi đè accessor để ném exception hoặc gây side effect làm matching trở nên khó dự đoán. Hạn chế dùng accessor có side effect; kiểm tra invariant tại constructor hoặc API domain thích hợp. Không bắt toàn bộ `MatchException` rồi giả vờ pattern không khớp: như vậy sẽ che một lỗi thật.

Theo Java 21, `MatchException` do accessor ném lỗi giữ nguyên ngoại lệ trong `getCause()`. Nhưng **không phải mọi `MatchException` đều có cause**, như ví dụ mất coverage ở runtime trong phần 8.

## 6. Guard when ném exception: không chuyển thành false

Một `switch` với pattern và guard:

```java
// Đoạn minh họa trong một phương thức có biến value kiểu Object:
return switch (value) {
    case String text when check(text) -> "accepted";
    case String text -> "fallback";
    case null -> "null";
    default -> "other";
};
```

Trình tự chọn case là:

1. Kiểm tra xem selector khớp `String text` hay không.
2. Chỉ khi pattern khớp mới đánh giá `check(text)`.
3. Nếu guard trả `true`, case áp dụng.
4. Nếu guard trả `false`, xét nhánh tiếp theo.
5. Nếu guard **ném exception**, cả quá trình lựa chọn nhánh kết thúc bất thường **với exception đó**; `case String text -> "fallback"` **không** được thử.

Trong chương trình `AbruptPatternDemo`, `guard(text)` luôn ném `IllegalArgumentException` và output là:

```text
guard: IllegalArgumentException, cause=none
```

Không có phép tự động biến exception của `when` thành `MatchException`. Để thấy một guard thất bại bình thường và cho phép fallback, viết điều kiện trả boolean:

```java
// Đoạn minh họa trong cùng một switch expression:
case String text when text.length() > 5 -> "long";
case String text -> "short";
```

Nếu text dài 3, guard thứ nhất trả false, nhánh thứ hai được chọn bình thường. Nếu guard có biểu thức dereference của component có thể null, cần chủ động kiểm tra null trước; `NullPointerException` do guard ném sẽ lan truyền, **không** được coi là `false`.

**Phân biệt khác:** Guard có kiểu `Boolean` cũng có thể ném `NullPointerException` nếu giá trị null bị unbox để kiểm tra điều kiện. Việc compiler chấp nhận kiểu `Boolean` không bảo đảm kết quả đánh giá guard luôn an toàn.

## 7. Exception khi đánh giá selector: pattern chưa chạy

Trong dòng:

```java
test("selector", () -> guarded(selector()));
```

Method `selector()` ném `IllegalArgumentException` trước khi `guarded(...)` nhận tham số. Không có bước chọn case nào của `guarded` được thực hiện. Output:

```text
selector: IllegalArgumentException, cause=none
```

Tình huống tương tự:

```java
// Đoạn minh họa, giả sử getValue() có thể ném exception:
if (getValue() instanceof String text) {
    System.out.println(text);
}
```

Đánh giá toán hạng bên trái của `instanceof` xảy ra trước quá trình pattern matching. Nếu `getValue()` ném lỗi, biểu thức `instanceof` hoàn tất bất thường với lỗi gốc, không trả false.

**Bài học:** Khi thấy stack trace từ một câu lệnh có pattern, cần xác định lỗi xảy ra ở **selector**, **record accessor**, **guard**, hay **case body**. Vị trí trên cùng một dòng source không đủ để kết luận nguyên nhân.

## 8. Null trong switch và MatchException khi exhaustive runtime thất bại

### 8.1. Selector null khi không có case null

Method `noNullCase`:

```java
static String noNullCase(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

Với `value == null`, Java ném `NullPointerException`. `default` không tự tiếp nhận null. Output:

```text
nullSelector: NullPointerException, cause=none
```

Nếu muốn kết quả riêng, thêm:

```java
case null -> "no value";
```

Có thể dùng `case null, default -> ...` trong một số trường hợp phù hợp, nhưng `case null` riêng thường dễ hiểu hơn khi logic cho thiếu dữ liệu khác logic cho kiểu không hỗ trợ.

### 8.2. Switch được xem là exhaustive nhưng không có nhánh khớp lúc chạy

Đây là trường hợp đặc biệt quan trọng của pattern matching trên **sealed hierarchy** kết hợp record patterns:

```java
sealed interface Choice permits Yes, No {}
record Yes() implements Choice {}
record No() implements Choice {}
record Wrapper(Choice choice) {}

static String nested(Wrapper value) {
    return switch (value) {
        case Wrapper(Yes yes) -> "yes";
        case Wrapper(No no) -> "no";
    };
}
```

Đây là **đoạn minh họa rút từ chương trình hoàn chỉnh**. `Choice` được sealed và có đúng hai subtype `Yes`/`No`. Vì thế compiler có thể coi hai nested record patterns là exhaustive cho `Wrapper`.

Tuy nhiên, `new Wrapper(null)` vẫn có thể được tạo vì record component `choice` không tự bị cấm null. Khi chạy:

```java
nested(new Wrapper(null));
```

- Selector `Wrapper` khác null.
- `case Wrapper(Yes yes)` không khớp vì component `choice` bằng null và `Yes` type pattern không null-matching ở vị trí có kiểu khai báo `Choice`.
- `case Wrapper(No no)` cũng không khớp.
- Mặc dù compiler đã chứng minh coverage dựa trên hierarchy, không có nhánh thực tế nhận giá trị này. Runtime ném **`MatchException`**.

Output:

```text
nestedExhaustive: MatchException, cause=none
```

Khác với lỗi accessor, `MatchException` ở đây có thể **không có cause**. Đây là một trong những tình huống được mô tả trong tài liệu API chính thức của `java.lang.MatchException` ở Java 21.

Một nguyên nhân khác của `MatchException` loại “unexpected non-match” là **separate compilation**: chương trình `switch` được biên dịch dựa trên tập subtype/enum cũ, sau đó chạy với định nghĩa hierarchy đã thay đổi nhưng switch chưa được biên dịch lại. Compiler bảo đảm exhaustiveness cho mô hình mà nó nhìn thấy lúc biên dịch, không tuyệt đối loại bỏ mọi thay đổi bất tương thích ở runtime.

### 8.3. Sửa đúng: kiểm soát null ở boundary hoặc thêm fallback phù hợp

Có ít nhất hai cách thiết kế:

**Cách A — Không cho phép component null từ lúc tạo record.** Nếu `Wrapper.choice` là bắt buộc, thêm canonical/compact constructor kiểm tra:

```java
record Wrapper(Choice choice) {
    Wrapper {
        java.util.Objects.requireNonNull(choice, "choice");
    }
}
```

Đây là **lựa chọn thiết kế thay thế** cho định nghĩa record trong ví dụ, không đưa đồng thời hai khai báo `Wrapper` vào cùng file. `new Wrapper(null)` khi đó thất bại ngay tại constructor với `NullPointerException`, thay vì xuất hiện `MatchException` về sau khi matching.

**Cách B — Chấp nhận null và xử lý nó trước.** Nếu null là dữ liệu hợp lệ, đặt một case có guard bắt component null:

```java
// Đoạn minh họa của phương thức thay thế:
static String safeNested(Wrapper value) {
    return switch (value) {
        case null -> "missing wrapper";
        case Wrapper(var choice) when choice == null -> "missing choice";
        case Wrapper(Yes yes) -> "yes";
        case Wrapper(No no) -> "no";
    };
}
```

Ở vị trí component của `Wrapper`, `var choice` nhận cả null, còn guard `choice == null` lọc riêng giá trị này. Các pattern `Yes`/`No` tiếp tục xử lý biến thể còn lại. Không đặt case `Wrapper(var choice)` **không guard** trước các case cụ thể, vì nó sẽ bao phủ chúng và gây lỗi *dominance*.

**Không nên** mặc định catch `MatchException` rồi trả `"other"` cho mọi trường hợp: cách này có thể che cả accessor hỏng và một thay đổi hierarchy cần cập nhật source.

## 9. Case body ném exception: không phải lỗi matching

Method `bodyThrows` đã được chọn đúng case `String text`:

```java
static String bodyThrows(Object value) {
    return switch (value) {
        case String text ->
            throw new UnsupportedOperationException("body failed");
        case null -> "null";
        default -> "other";
    };
}
```

Output khi gọi với `"hello"`:

```text
caseBody: UnsupportedOperationException, cause=none
```

Ở đây pattern đã khớp thành công; exception chỉ xuất hiện **sau đó** do câu lệnh trong nhánh. Java không bọc mọi exception của case body thành `MatchException`. Một nhánh khác trong cùng switch không được thử như một cơ chế fallback sau khi body đã được chọn.

Điều này giúp phân tích lỗi: một `MatchException` khi đọc record component khác với `UnsupportedOperationException` do service xử lý thông điệp tự ném.

## 10. Abrupt completion của pattern khác với abrupt completion của statement

JLS dùng thuật ngữ **abrupt completion** cho cả biểu thức và câu lệnh. Ở cấp **statements**, `return`, `break`, `continue`, `yield` và `throw` có thể làm chuyển luồng điều khiển; ví dụ một `return` có thể hoàn tất bất thường phương thức đang được thực thi, theo nghĩa không tiếp tục tuần tự các statement sau.

Nhưng ở cấp **quá trình pattern matching** (JLS `14.30.2), trường hợp hoàn tất bất thường được mô tả bởi **`throw`**. Không gọi một `break` được thực thi trong case body là “pattern không khớp”. Ví dụ:

```java
// Switch statement truyền thống, các nhánh dùng case type pattern:
switch (value) {
    case String text:
        System.out.println(text);
        break;
    case null:
        System.out.println("null");
        break;
    default:
        System.out.println("other");
}
```

Khi `case String text` khớp, `break` thoát khỏi switch statement. Đây là điều khiển luồng sau matching; không có `MatchException`.

Với **switch expression**, `yield` trong một block case được dùng để tạo kết quả:

```java
// value có kiểu Object:
String result = switch (value) {
    case String text -> {
        String cleaned = text.trim();
        yield cleaned;
    }
    case null -> "null";
    default -> "other";
};
```

`yield` cũng không đại diện cho pattern failure. Nó chuyển giá trị của nhánh ra switch expression.

**Tóm lại:** “Pattern matching hoàn tất bất thường” nên được hiểu trước hết là **exception trong khi thử pattern**. Các cơ chế điều khiển luồng của statement/expression là chủ đề liên quan nhưng khác về thời điểm và ý nghĩa.

## 11. Cách xử lý exception an toàn trong ứng dụng

Một chiến lược ổn định gồm các bước sau:

1. **Xác định contract null:** Selector có thể null hay không? Record component nào bắt buộc? Bảo vệ invariant ở constructor nếu điều đó đúng về domain.
2. **Giữ accessor đơn giản:** Record accessor nên trả dữ liệu dự đoán được, tránh I/O, thay đổi trạng thái hay chủ động ném exception khi deconstruction.
3. **Giữ guard thuần và an toàn null:** Guard `when` nên là kiểm tra boolean ít side effect. Xử lý nhánh null/giá trị không hợp lệ một cách tường minh.
4. **Dùng case fallback cho dữ liệu hợp lệ nhưng không khớp:** Fallback xử lý *non-match*, không thay cho catch exception.
5. **Dùng `try/catch` ở boundary phù hợp:** Phân biệt `MatchException`, `IllegalArgumentException`, `NullPointerException` và lỗi nghiệp vụ. Giữ `getCause()` và stack trace khi cần chẩn đoán.
6. **Biên dịch lại cùng hierarchy sau thay đổi:** Sealed/enum exhaustive switch có thể gặp khác biệt khi các module được build và deploy không đồng bộ.
7. **Kiểm thử cả success, false và throw:** Không chỉ kiểm tra case được chọn; cần cả nullable components, guard ném lỗi, accessor bất thường và subtype không mong đợi.

**Ví dụ xử lý một nhánh mà không che lỗi:**

```java
// Minh họa: không biến MatchException thành "no match" một cách tùy tiện.
try {
    String answer = nested(input);
    System.out.println(answer);
} catch (MatchException ex) {
    System.err.println("Unexpected pattern failure");
    if (ex.getCause() != null) {
        System.err.println("Root cause: " + ex.getCause());
    }
    throw ex; // Hoặc chuyển thành lỗi ở application boundary theo contract.
}
```

Trong đoạn này `input` phải là một biến kiểu `Wrapper` và `nested` là phương thức đã định nghĩa ở chương trình. Đây là ví dụ về **chính sách báo lỗi**, không phải yêu cầu bắt mọi `MatchException` trong tất cả các đoạn code.

### Những lỗi thường gặp

| Hiểu nhầm | Hệ quả | Cách hiểu/sửa đúng |
| --- | --- | --- |
| “Pattern không khớp thì ném exception” | Bắt exception cho một kết quả bình thường | Non-match thường chỉ trả false hoặc xét case khác |
| “Record accessor ném gì thì pattern ném y nguyên” | Bắt nhầm `IllegalStateException` bên ngoài record pattern | Java 21 bọc lỗi accessor thành `MatchException` với cause gốc |
| “Guard ném exception thì thử case kế tiếp” | Che lỗi hoặc mong đợi fallback không xảy ra | Guard ném lỗi làm chọn case kết thúc bất thường; chỉ guard trả false mới xét tiếp |
| “`default` bắt cả null” | Gặp `NullPointerException` trên selector null | Có `case null` hoặc xử lý null trước switch |
| “Sealed exhaustive nghĩa là không bao giờ MatchException” | Bỏ qua nested null và separate compilation | Kiểm tra null/invariant, đồng bộ build; test runtime |
| “Trong `instanceof` không thể có exception” | Không tính đến operand/accessor có thể ném lỗi | Phân biệt bước đánh giá operand và record accessor |
| “Exception trong case body là lỗi pattern” | Chẩn đoán sai tầng lỗi | Case body chạy sau khi matching đã thành công |
| “Bắt `MatchException` là đủ cho mọi lỗi” | Bỏ sót guard, selector, case body exceptions | Phân loại theo giai đoạn và contract |
| “`MatchException.getCause()` luôn khác null” | Có thể gây NPE khi báo lỗi | Kiểm tra cause trước khi sử dụng |

## 12. Kiểm thử và bài tập

### Bộ ca kiểm thử nên có

- Đầu vào đúng kiểu và đủ component: pattern khớp bình thường.
- Đầu vào khác kiểu: `instanceof` trả false, không ném exception.
- Selector null: `instanceof` false; `switch` có `case null` xử lý, thiếu `case null` có thể ném `NullPointerException`.
- Type pattern unconditional trong record component kiểu tham chiếu: kiểm tra khả năng ràng buộc null.
- Nested record component null: nested pattern không khớp; kiểm tra case fallback hoặc invariant.
- Record accessor custom ném `IllegalStateException`: quan sát `MatchException.getCause()`.
- Guard trả false: case sau được xét; guard ném exception: case sau không chạy.
- Switch exhaustive dựa trên sealed nested patterns nhưng component null: kiểm tra `MatchException`.
- Phần thân case ném lỗi: lỗi gốc truyền ra, không mặc định bọc thành `MatchException`.
- Thay đổi subtype sealed giữa các module: xây dựng và kiểm thử lại các consumer có exhaustive switch.

### Bài tập 1 — Phân biệt false và throw

Tạo `record User(String name) {}`. Với biến `Object value`, hãy chạy:
- `value = "hello"` và thử `value instanceof User(String name)`;
- `value = null` và thử pattern tương tự;
- `value = new User(null)` và thử pattern tương tự.

Dự đoán true/false trước khi chạy, giải thích tại sao component null không nhất thiết làm record pattern thất bại.

### Bài tập 2 — Sửa guard có thể ném NPE

Tạo `record Text(String value) {}`, rồi viết case `Text(String s) when s.isBlank()`. Truyền `new Text(null)` để quan sát exception. Sửa bằng cách đặt `case Text(String s) when s == null` trước, hoặc dùng điều kiện guard an toàn null; test lại các chuỗi null, rỗng, không rỗng.

### Bài tập 3 — MatchException và cause

Tạo record có accessor tùy chỉnh ném `IllegalStateException`, rồi match bằng `instanceof` với record pattern. Catch `MatchException`, in `ex.getCause().getClass().getSimpleName()`. Giải thích vì sao catch exception gốc bên ngoài pattern có thể không bắt được trực tiếp.

### Bài tập 4 — Exhaustiveness và nested null

Từ chương trình `AbruptPatternDemo`, sửa `nested` để nhận cả `new Wrapper(null)`. Thử hai hướng:
- Kiểm tra `choice` khác null trong constructor của `Wrapper`.
- Thêm case `Wrapper(var choice) when choice == null` trước các case `Yes`/`No`, đồng thời thêm `case null` nếu cho phép chính `Wrapper` null.

Giải thích lý do case fallback dành cho null component không giống case null của selector.

### Bài tập 5 — Lỗi ở bốn giai đoạn

Lần lượt khiến lỗi xảy ra ở selector, record accessor, guard và case body. Với mỗi lần, ghi lại class của exception bắt được, giá trị `getCause()` và nhánh có/không được thực thi. Đối chiếu kết quả với bảng ở phần 1.

## 13. Tổng kết

Một pattern **không khớp** là kết quả bình thường của matching; nó **không tương đương** với “hoàn tất bất thường”. Trong Java 21, quá trình matching có thể kết thúc bất thường khi record accessor ném exception, và khi đó Java dùng **`MatchException`** giữ exception gốc ở `cause`. Trong `switch`, exception từ **selector**, **guard** và **case body** được xử lý theo các quy tắc riêng, thường lan truyền như exception ban đầu.

Ngay cả một `switch` đã được compiler đánh giá là exhaustive cũng có thể gặp `MatchException` ở runtime, điển hình khi **nested record pattern không khớp component null** hoặc do **khác biệt giữa các module biên dịch riêng**. Thiết kế đúng cần chủ động xác định invariant/null policy, giữ accessor và guard dễ dự đoán, kiểm thử đầy đủ và không đánh đồng exception với case fallback.

## Tài liệu tham khảo

- Java Language Specification SE 21 — `14.30.2 Pattern Matching`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2
- Java Language Specification SE 21 — `14.11.3 Execution of a switch Statement`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Java SE 21 API — `java.lang.MatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
