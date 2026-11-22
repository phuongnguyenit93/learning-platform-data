# MatchException và nguyên nhân gốc trong Java Pattern Matching

## 1. MatchException là gì?

Từ **Java 21**, `java.lang.MatchException` là một `RuntimeException` dùng để biểu thị **thất bại bất thường trong quá trình pattern matching**. Đây không phải thông báo “pattern này không khớp” thông thường. Một pattern không khớp có thể dẫn đến `false` trong `instanceof` hoặc khiến `switch` thử nhãn khác; `MatchException` xuất hiện ở những tình huống mà quá trình matching **không thể kết thúc theo cách bình thường như chương trình đã dự kiến**.

Hai nhóm nguyên nhân đặc biệt quan trọng:

1. **Lỗi khi trích xuất thành phần của record:** record pattern gọi accessor để lấy component, nhưng accessor ném ngoại lệ. Java ném `MatchException` và đặt ngoại lệ ban đầu vào `getCause()`.
2. **`switch` được compiler coi là exhaustive nhưng lại không có nhánh nào khớp tại runtime:** điều này có thể xảy ra khi hierarchy/enum thay đổi giữa các lần biên dịch, hoặc khi có `null` ở **component lồng nhau** khiến các record patterns không khớp dù bộ pattern được coi là exhaustive. Trong trường hợp “không có nhãn khớp”, `getCause()` thường là `null` vì không có ngoại lệ accessor nào cần bọc.

Khai báo API trong Java 21:

```java
public final class MatchException extends RuntimeException {
    // Constructor công khai:
    public MatchException(String message, Throwable cause);
}
```

Đây là **mô tả rút gọn chữ ký**, không phải mã nguồn đầy đủ của JDK. `MatchException` nằm trong `java.lang` nên không cần `import`; lớp được giới thiệu từ Java 21. Nó là **unchecked exception**, compiler không yêu cầu khai báo `throws` hoặc bắt `catch`.

**Điểm cốt lõi của bài:** khi thấy `MatchException`, phải tìm **nguyên nhân gốc (root cause)**. Đừng mặc định mọi `MatchException` đều do thiếu `default`, cũng đừng mặc định `getCause()` luôn khác `null`.

## 2. Trình tự kiểm tra để phân biệt nguyên nhân

Sơ đồ quyết định ở mức ý tưởng:

```text
Một phép matching hoặc switch bị lỗi
  |
  +-- Có MatchException?
  |     |
  |     +-- Có getCause()?
  |     |     |
  |     |     +-- Có: xem loại exception, message, stack trace,
  |     |     |        record accessor nào ném lỗi
  |     |     |
  |     |     +-- Không: kiểm tra switch exhaustive runtime:
  |     |              nested record/null, nested sealed/null,
  |     |              enum hoặc sealed hierarchy khác lúc compile
  |     |
  |     +-- Đối chiếu source code đang chạy và version của dependency
  |
  +-- Không: phân loại đúng ngoại lệ:
        NullPointerException, IllegalArgumentException từ guard,
        exception từ thân nhánh, lỗi cast, lỗi khác...
```

Sơ đồ giúp **khoanh vùng**, không phải một quy tắc suy luận tuyệt đối chỉ dựa vào `getCause()`. Người viết có thể tự tạo `MatchException` bằng constructor, và dữ liệu logging có thể không đầy đủ. Hãy đọc stack trace cùng code và trạng thái triển khai.

Bảng phân biệt:

| Hiện tượng | Ngoại lệ/hành vi thường gặp | Cần kiểm tra |
| --- | --- | --- |
| `record` accessor ném lỗi trong khi deconstruct | `MatchException`, `getCause()` chứa ngoại lệ gốc | Accessor, component, nguồn dữ liệu, side effect |
| `switch` exhaustive gặp instance không còn được bộ case hiện tại bao phủ | `MatchException`, không nhất thiết có cause | Phiên bản class/enum/sealed hierarchy, module/JAR và cách build |
| `switch` exhaustive theo type coverage nhưng component record lồng nhau null làm mọi nhánh trượt | `MatchException`, thường không có cause | Nullable component và pattern dự phòng |
| Selector của `switch` là null nhưng không có nhãn null phù hợp | `NullPointerException` | `case null`, null contract |
| Guard `when` ném `IllegalArgumentException` | Thông thường truyền chính `IllegalArgumentException` | Phương thức/biểu thức của guard |
| Thân nhánh `->` ném exception | Exception từ thân nhánh được truyền ra | Logic xử lý sau khi chọn nhánh |
| `value instanceof SomeType` không khớp | `false` | Đây là kết quả matching bình thường |
| `switch` expression thiếu tính exhaustive ở compile time | Lỗi biên dịch | Bổ sung case/default thích hợp trước khi chạy |

**Phân biệt “không match” và “match thất bại bất thường”:** ví dụ `obj instanceof String s` với một `Integer` sẽ trả `false`. Đó không phải lý do để ném `MatchException`.

## 3. Nguyên nhân 1 — Record accessor ném ngoại lệ

Record pattern vừa kiểm tra kiểu vừa trích xuất các component bằng accessor. Mỗi record component có accessor tương ứng, có thể là accessor do compiler sinh hoặc do lập trình viên khai báo tường minh.

Ví dụ:

```java
record Broken(String text) {
    @Override
    public String text() {
        throw new IllegalStateException("accessor failed");
    }
}
```

Khi kiểm tra pattern:

```java
// Phần minh họa trong một phương thức nhận Object value:
return switch (value) {
    case Broken(String text) -> "text:" + text;
    case null -> "missing";
    default -> "other";
};
```

Java phải gọi `Broken.text()` để xác định component `text`. Vì accessor ném `IllegalStateException`, quá trình khớp record pattern kết thúc bất thường và Java ném `MatchException`, có **cause** là `IllegalStateException("accessor failed")`.

Đây không phải trường hợp `case Broken(...)` “không phù hợp, hãy thử `default`”. **Ngoại lệ không bị biến thành một lần match thất bại bình thường.**

Đặc tả JLS 21 `14.30.2 yêu cầu khi invocation của accessor trong record pattern kết thúc bất thường, matching ném `MatchException` có nguyên nhân gốc là lý do ngoại lệ đó. Cơ chế tương tự có thể ảnh hưởng cả record pattern trong `instanceof`; không chỉ giới hạn ở `switch`.

### Vì sao có thể xảy ra trong hệ thống thực?

- Accessor tùy biến kiểm tra một trạng thái không hợp lệ rồi ném exception.
- Accessor có logic tính toán, đọc dữ liệu ngoài hoặc sử dụng trạng thái mutable.
- Accessor record lồng nhau ném lỗi khi deconstruct ở tầng sâu.
- Một dependency thay đổi triển khai accessor hoặc dữ liệu bị lệch với invariant mà accessor giả định.

**Khuyến nghị:** accessor của record nên đơn giản, ổn định và ít side effect. Nếu cần validate invariant, cân nhắc thực hiện trong constructor của record hoặc tại biên nhận dữ liệu, thay vì chờ đến lúc deconstruct. Việc di chuyển validation có thể thay đổi **thời điểm** exception, vì vậy cần xác nhận hợp đồng trước khi refactor.

## 4. Nguyên nhân 2 — Exhaustive switch nhưng nested record chứa null

Đây là trường hợp khó thấy vì chương trình **vẫn biên dịch**.

```java
record Inner(String content) {}
record Outer(Inner inner) {}

static String nested(Outer value) {
    return switch (value) {
        case Outer(Inner(String content)) -> "inner:" + content;
    };
}
```

Compiler có thể coi bộ pattern là **exhaustive về kiểu**: `Outer` có một component kiểu `Inner`; record pattern lồng có thể bao phủ kiểu đó. Nhưng runtime có thể nhận:

```java
nested(new Outer(null));
```

`Outer` khác null, nhưng component `inner` là null. Record pattern lồng `Inner(...)` **không khớp null**. Không có nhánh khác, vì vậy `switch` được coi là exhaustive lúc biên dịch nhưng không tìm thấy nhãn áp dụng lúc chạy: Java ném **`MatchException`**.

So sánh ba đầu vào:

| Đầu vào | Kết quả |
| --- | --- |
| `new Outer(new Inner("hi"))` | `inner:hi` |
| `new Outer(new Inner(null))` | `inner:null` — bản thân `Inner` tồn tại; component `String` bên trong là null vẫn có thể được binding |
| `new Outer(null)` | `MatchException` — pattern record con `Inner(...)` không thể khớp null |

Dòng thứ hai đặc biệt quan trọng: **null ở record con** khác với **null ở một component bên trong record con vẫn tồn tại**. Các quy tắc *null-matching type pattern* trong Java 21 giải thích tại sao `String content` ở đây có thể được gán null, trong khi `Inner(...)` không khớp null.

### Cách sửa có chủ đích

Nếu domain cho phép `Outer.inner == null`, thêm nhánh xử lý record rộng hơn:

```java
static String nestedSafe(Outer value) {
    return switch (value) {
        case Outer(Inner(String content)) -> "inner:" + content;
        case Outer(var inner) -> "empty inner";
        case null -> "outer null";
    };
}
```

Nhánh `Outer(var inner)` nằm **sau** nhánh lồng cụ thể để xử lý trường hợp còn lại. `case null` ở đây xử lý chính selector `value == null`, chứ không xử lý component `inner == null`.

Nếu hợp đồng **cấm** `inner == null`, thay vì lặng lẽ trả fallback, cân nhắc enforce invariant ngay tại constructor:

```java
record StrictOuter(Inner inner) {
    StrictOuter {
        java.util.Objects.requireNonNull(inner, "inner");
    }
}
```

Đây là một **ví dụ thay đổi thiết kế riêng**, không phải drop-in replacement của `Outer`. Nó chuyển lỗi từ lúc matching sang lúc khởi tạo; cần quyết định dựa trên yêu cầu domain.

## 5. Nguyên nhân 3 — Nested sealed patterns và null

Một trường hợp tương tự xuất hiện khi record chứa component kiểu `sealed interface`:

```java
sealed interface Kind permits Cash, Card {}
record Cash(int cents) implements Kind {}
record Card(String last4) implements Kind {}
record Payment(Kind kind) {}

static String sealedNested(Payment payment) {
    return switch (payment) {
        case Payment(Cash cash) -> "cash:" + cash.cents();
        case Payment(Card card) -> "card:" + card.last4();
    };
}
```

`Kind` có hai subtype được cho phép, nên compiler có thể coi hai pattern là exhaustive cho `Payment`. Tuy nhiên:

```java
sealedNested(new Payment(null));
```

không khớp cả `Cash` lẫn `Card`: component `kind` là null. `switch` không có nhánh áp dụng, dẫn đến **`MatchException`**, thường **không có cause**. Đây **không** phải lỗi `NullPointerException` từ selector, bởi selector `Payment` vẫn khác null.

Nếu null là hợp lệ, có thể dùng nhánh dự phòng:

```java
static String safePayment(Payment payment) {
    return switch (payment) {
        case Payment(Cash cash) -> "cash:" + cash.cents();
        case Payment(Card card) -> "card:" + card.last4();
        case Payment(var kind) -> "missing kind";
        case null -> "missing payment";
    };
}
```

Không nên thêm default chỉ để xóa exception mà chưa biết domain muốn xử lý `Payment(null)` như thế nào. Một hệ thống thanh toán có thể cần từ chối dữ liệu thay vì thay nó bằng một giao dịch mặc định.

## 6. Nguyên nhân 4 — Separate compilation làm switch không còn exhaustive tại runtime

Tính **exhaustiveness** thường được phân tích **lúc biên dịch** dựa trên các subtype enum/sealed mà compiler nhìn thấy. Một deployment có thể chạy các class được biên dịch ở các thời điểm khác nhau.

Tình huống khái niệm:

1. Thư viện ban đầu có `sealed interface Event permits Created, Cancelled`.
2. Một module client được biên dịch với switch expression chứa `case Created` và `case Cancelled`, nên compiler công nhận exhaustive và không yêu cầu `default`.
3. Thư viện được nâng cấp, thêm subtype `Updated` và biên dịch lại **chỉ thư viện**, trong khi class chứa switch vẫn là bản cũ.
4. Runtime nhận một `Updated`. Bộ case trong bytecode client cũ không biết subtype mới; **`MatchException` có thể được ném**.

Tương tự, enum có thêm constant mới có thể khiến exhaustive switch biên dịch trước đó không khớp khi gặp constant mới.

Ví dụ mã **minh họa trạng thái cũ**, không phải chương trình độc lập:

```java
// Library v1:
sealed interface Event permits Created, Cancelled {}
record Created() implements Event {}
record Cancelled() implements Event {}

// Client v1, biên dịch dựa trên Library v1:
static String describe(Event e) {
    return switch (e) {
        case Created c -> "created";
        case Cancelled c -> "cancelled";
    };
}
```

Nếu Library v2 thêm `record Updated() implements Event` và chạy cùng bytecode Client v1, tính exhaustive **lúc biên dịch Client v1** không còn phản ánh tập subtype mới. Không được suy rằng compile-time safety của bản cũ là hợp đồng bao phủ mọi phiên bản thư viện về sau.

**Chẩn đoán:** so sánh phiên bản JAR, module path/classpath, build artifact, container image, lớp thật đang được load và thứ tự deploy. Cần **recompile các module chứa switch** với hierarchy/enum đã cập nhật và chạy test tích hợp trên đúng bộ artifact sẽ triển khai. Việc thêm `default` để nuốt subtype mới có thể che lỗi hợp đồng; chỉ dùng fallback nếu domain thực sự muốn cho phép các trường hợp chưa được nhận diện.

**Lưu ý:** không phải mọi thay đổi nhị phân đều chỉ tạo `MatchException`. Những thay đổi hierarchy không tương thích có thể gây lỗi linkage khác, chẳng hạn `IncompatibleClassChangeError`. Phải đọc loại lỗi cụ thể thay vì mặc định mọi lỗi deployment đều là mismatch của switch.

## 7. Chương trình Java 21 hoàn chỉnh để phân biệt các nguyên nhân

Đoạn mã sau minh họa được **accessor failure**, **nested null**, **nested sealed null**, và các ngoại lệ dễ bị nhầm là `MatchException`. Để giữ bài độc lập, tình huống separate compilation ở mục 6 chỉ trình bày khái niệm; nó cần hai phiên bản thư viện/bytecode nên không tái hiện bằng một file duy nhất.

Lưu thành **`MatchExceptionCausesDemo.java`**:

```java
public class MatchExceptionCausesDemo {
    record Broken(String text) {
        @Override
        public String text() {
            throw new IllegalStateException("accessor failed");
        }
    }

    record Inner(String content) {}
    record Outer(Inner inner) {}

    sealed interface Kind permits Cash, Card {}
    record Cash(int cents) implements Kind {}
    record Card(String last4) implements Kind {}
    record Payment(Kind kind) {}

    static String broken(Object value) {
        return switch (value) {
            case Broken(String text) -> "text:" + text;
            case null -> "missing";
            default -> "other";
        };
    }

    static String nested(Outer value) {
        return switch (value) {
            case Outer(Inner(String content)) -> "inner:" + content;
        };
    }

    static String nestedSafe(Outer value) {
        return switch (value) {
            case Outer(Inner(String content)) -> "inner:" + content;
            case Outer(var inner) -> "empty inner";
            case null -> "outer null";
        };
    }

    static String sealedNested(Payment payment) {
        return switch (payment) {
            case Payment(Cash cash) -> "cash:" + cash.cents();
            case Payment(Card card) -> "card:" + card.last4();
        };
    }

    static boolean guard(int value) {
        throw new IllegalArgumentException("guard failed");
    }

    static String guarded(Object value) {
        return switch (value) {
            case Integer x when guard(x) -> "ok";
            case Integer x -> "other integer";
            case null -> "missing";
            default -> "not integer";
        };
    }

    static String noNull(Object value) {
        return switch (value) {
            case String s -> s;
            default -> "other";
        };
    }

    static void show(
            String label, java.util.function.Supplier<String> operation) {
        try {
            System.out.println(label + " => " + operation.get());
        } catch (RuntimeException ex) {
            Throwable cause = ex.getCause();
            String description = cause == null
                    ? "none"
                    : cause.getClass().getSimpleName()
                            + ":" + cause.getMessage();

            System.out.println(
                    label + " => " + ex.getClass().getSimpleName()
                            + " | cause=" + description);
        }
    }

    public static void main(String[] args) {
        show("normal", () -> broken("hello"));
        show("accessor", () -> broken(new Broken("data")));

        show("nested-ok",
                () -> nested(new Outer(new Inner("hi"))));
        show("nested-inner-value-null",
                () -> nested(new Outer(new Inner(null))));
        show("nested-null",
                () -> nested(new Outer(null)));
        show("nested-safe",
                () -> nestedSafe(new Outer(null)));

        show("sealed-ok",
                () -> sealedNested(new Payment(new Cash(10))));
        show("sealed-null",
                () -> sealedNested(new Payment(null)));

        show("guard", () -> guarded(1));
        show("selector-null", () -> noNull(null));
        show("explicit-null", () -> broken(null));
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 MatchExceptionCausesDemo.java
java MatchExceptionCausesDemo
```

**Stdout:**

```text
normal => other
accessor => MatchException | cause=IllegalStateException:accessor failed
nested-ok => inner:hi
nested-inner-value-null => inner:null
nested-null => MatchException | cause=none
nested-safe => empty inner
sealed-ok => cash:10
sealed-null => MatchException | cause=none
guard => IllegalArgumentException | cause=none
selector-null => NullPointerException | cause=none
explicit-null => missing
```

### Từ output đến nguyên nhân gốc

- **`accessor`:** `Broken.text()` ném `IllegalStateException`. Record pattern biến nó thành `MatchException`; `getCause()` chỉ về lỗi gốc.
- **`nested-null`:** selector `new Outer(null)` tồn tại, nhưng `Inner(...)` không khớp. Vì switch không có case khác và được compiler xem là exhaustive, `MatchException` xuất hiện **không kèm cause**.
- **`nested-inner-value-null`:** `Inner` tồn tại và accessor trả `content == null`; type pattern ở component có thể binding null, nên kết quả là `inner:null`, không có exception.
- **`nested-safe`:** nhánh `Outer(var inner)` dự phòng xử lý trường hợp component record con null.
- **`sealed-null`:** `Payment(null)` không khớp hai mẫu `Payment(Cash ...)`/`Payment(Card ...)`, dẫn đến `MatchException` không cause.
- **`guard`:** `when guard(x)` gọi một phương thức ném `IllegalArgumentException`; exception truyền ra như nó vốn có, không được bọc thành `MatchException`.
- **`selector-null`:** thiếu `case null` khiến selector null phát sinh `NullPointerException`, không phải `MatchException`.
- **`explicit-null`:** `case null` được khai báo, nên method trả `missing` bình thường.

Hàm `show` bắt `RuntimeException` để **trình diễn** và in kết quả ngắn gọn. Đây không phải một chiến lược khuyến nghị cho production: nó cố tình nuốt exception để chương trình tiếp tục từng ca kiểm thử. Trong ứng dụng thật phải xử lý hoặc truyền lỗi theo hợp đồng, đồng thời giữ stack trace.

## 8. Phân biệt MatchException với những lỗi gần giống

### 8.1. `NullPointerException` từ selector null

Một selector của pattern switch không tự khớp `default` khi nó là null. Ví dụ:

```java
Object value = null;

// Có thể ném NullPointerException:
String result = switch (value) {
    case String s -> "text";
    default -> "other";
};
```

Sửa theo domain:

```java
String result = switch (value) {
    case String s -> "text";
    case null -> "missing";
    default -> "other";
};
```

**Đừng nhầm:** `case null` ở tầng selector **không sửa** tình huống `new Outer(null)` nếu selector là một `Outer` khác null.

### 8.2. Exception từ guard, selector expression và thân nhánh

Giả sử:

```java
case Integer x when validate(x) -> "approved";
```

Nếu `validate(x)` ném exception, chính exception đó thường truyền ra thay vì bị hiểu thành guard trả `false`. Nếu selector là một phương thức `source()` và `source()` ném lỗi, quá trình đánh giá selector đã thất bại **trước khi** kiểm tra các case. Nếu nhánh `->` được chọn rồi gọi `process(...)` ném lỗi, lỗi nằm trong **xử lý của nhánh**, không tự động được bọc thành `MatchException`.

Do đó, khi đọc stack trace hãy xác định **lỗi phát sinh trước matching, trong accessor record, trong guard hay trong thân nhánh**.

### 8.3. `ClassCastException` và lỗi kiểu ở compile time

`(SomeType) value` có thể ném `ClassCastException` nếu kiểu runtime không chuyển được sang `SomeType`. Nhưng `instanceof SomeType s` khi không khớp thường trả `false`.

Còn nếu một nhãn pattern không áp dụng được với kiểu tĩnh của selector, compiler sẽ từ chối code; lỗi này **không tồn tại ở runtime để tạo `MatchException`**. Ví dụ selector có kiểu `String` nhưng nhãn `case Integer i` là một kiểu không tương thích.

### 8.4. `IncompatibleClassChangeError`

Đây là một `Error` liên quan tính nhất quán nhị phân/linkage, khác `MatchException`. Khi nâng cấp class hierarchy có thể gặp các dạng lỗi khác nhau tùy loại thay đổi. Không bắt tất cả lỗi “binary drift” rồi quy vào `MatchException`, cũng không cố sửa `IncompatibleClassChangeError` bằng cách thêm một `case` ngẫu nhiên.

## 9. Cách truy tìm root cause trong một ứng dụng thực tế

### Bước 1 — Giữ lại exception và stack trace

Trong một điểm xử lý lỗi tập trung, có thể dùng:

```java
try {
    return dispatch(value);
} catch (MatchException ex) {
    Throwable root = ex.getCause();
    if (root != null) {
        // Ghi loại và stack trace của nguyên nhân accessor.
        logger.error("Pattern matching failed in accessor", ex);
    } else {
        // Điều tra giá trị/shape và khả năng exhaustive-runtime mismatch.
        logger.error("No matching pattern at runtime", ex);
    }
    throw ex;
}
```

Đây là **mã minh họa**, không phải đoạn độc lập: `dispatch` và `logger` là những thành phần giả định của ứng dụng. Không in dữ liệu nhạy cảm vào log khi kiểm tra selector/record.

Không sử dụng chỉ `ex.getMessage()` rồi bỏ `ex.getCause()`. Ngoại lệ gốc có thể cho biết accessor nào ném lỗi, vị trí gọi và đối tượng bị vi phạm invariant. Đồng thời, **cause null là một dữ kiện hợp lệ**, không phải bằng chứng chắc chắn rằng message bị mất.

### Bước 2 — Phân loại loại pattern đang hoạt động

- Có **record pattern** (kể cả nested) đang gọi accessor tùy biến không?
- Có **sealed switch** hoặc exhaustive enum switch thiếu `default` vì compiler suy ra bao phủ không?
- Có **nested record** hoặc **nested sealed component** cho phép null không?
- Có `when` gọi method không thuần túy, hoặc thân nhánh chứa phép biến đổi có thể ném lỗi không?

Đặt breakpoint ở record accessor, trước/đầu guard, và tại nhánh được chọn để xác định giai đoạn thất bại.

### Bước 3 — Kiểm tra runtime class thực sự

Với lỗi nghi do separate compilation, so khớp:

- Source và class được compile của module chứa `switch`.
- Version của enum/sealed library ở compile time và runtime.
- Thứ tự JAR/classpath/module path, dependency tree, shaded artifact hoặc image container.
- Lịch sử bổ sung enum constants hoặc permitted subtypes.
- Test với đúng bộ artifact sẽ triển khai, không chỉ test unit bằng classpath của IDE.

Nếu `getCause()` chỉ rõ một accessor throw, điều tra accessor trước. Nếu cause null và case liên quan record lồng, kiểm tra component null trước khi đi tìm lỗi build.

### Bước 4 — Khắc phục theo nguyên nhân, không chữa triệu chứng

| Nguyên nhân thực | Hướng xử lý |
| --- | --- |
| Accessor ném lỗi | Sửa invariant/dữ liệu hoặc logic accessor; giữ trace của cause; tránh side effect không cần thiết |
| Nested record component null được cho phép | Thêm nhánh dự phòng chính xác hoặc đổi pattern cho phù hợp schema |
| Nested component null bị cấm | Validate rõ ràng ở biên/constructor; test input bất hợp lệ |
| Sealed/enum mở rộng nhưng switch được build từ phiên bản cũ | Recompile và phát hành lại các module phụ thuộc theo cùng version, bổ sung nhánh mới |
| Lỗi từ `when` hoặc thân nhánh | Sửa điều kiện/logic nghiệp vụ nơi thật sự ném exception |
| Selector null chưa được tính đến | Quy định contract null và dùng `case null`/kiểm tra đầu vào phù hợp |

**Không nên mặc định thêm `default -> "other"` cho mọi exhaustive switch.** Với sealed hierarchy, một switch không có `default` có thể là cơ chế tốt để compiler nhắc cập nhật xử lý khi thêm subtype. Với component null được cho phép, một pattern cụ thể hơn ở đúng tầng có thể bảo toàn khả năng kiểm tra subtype tốt hơn một fallback quá rộng.

## 10. Các lỗi thường gặp khi debug MatchException

1. **“MatchException nghĩa là `instanceof` trả false.”** Sai; không khớp kiểu thông thường chỉ là kết quả false hoặc chuyển case.
2. **“Mọi MatchException đều có nguyên nhân trong `getCause()`.”** Sai; mismatch của exhaustive switch có thể không kèm cause.
3. **“Chỉ cần thêm `case null` là sửa được nested null.”** Sai; selector null và component null thuộc hai tầng khác nhau.
4. **“`default` luôn xử lý selector null.”** Sai trong pattern switch Java 21; thiếu nhãn null phù hợp có thể ném NPE.
5. **“Bổ sung subtype vào sealed hierarchy luôn được client cũ tự động nhận.”** Sai; phần switch đã compile có thể không exhaustive ở runtime.
6. **“Accessor ném lỗi thì switch thử case khác.”** Sai; lỗi accessor trong record pattern được bọc vào MatchException thay vì chuyển sang case kế tiếp.
7. **“Guard ném lỗi thì bị bọc thành MatchException.”** Không đúng theo ngữ nghĩa thông thường của guard; exception từ guard được truyền ra.
8. **“Mọi vấn đề phân loại kiểu runtime đều gây MatchException.”** Sai; cast sai, lỗi linkage, selector null và lỗi biên dịch có bản chất khác.
9. **“Trả giá trị mặc định là cách sửa an toàn.”** Không nếu domain cần từ chối giao dịch hoặc cần phát hiện subtype chưa được xử lý.
10. **“Chỉ cần test một record không null.”** Không; phải test cả selector null, component null, nested null, accessor throw và dependency evolution khi phù hợp.
11. **“Đọc mỗi dòng message là đủ.”** Không; phải xem cause, stack trace và deployment metadata.
12. **“Bắt RuntimeException rồi tiếp tục là ổn.”** Không; demo làm vậy để minh họa, còn production phải theo hợp đồng lỗi, logging và rollback.

## 11. Checklist phòng ngừa

Trước khi merge code pattern matching Java 21+, tự hỏi:

- [ ] Với mọi record pattern, accessor có thể ném exception hay có side effect bất ngờ không?
- [ ] Null được phép ở **selector**, **record con**, và **component bên trong record con** đến mức nào?
- [ ] Exhaustive switch dựa trên sealed hierarchy/enum có được build và deploy đồng bộ với definition hiện tại không?
- [ ] Nếu thêm subtype/enum constant, có quy trình rebuild module phụ thuộc và test tích hợp không?
- [ ] Có testcase cho `new Outer(null)`, `new Outer(new Inner(null))` và selector null khi domain cho phép không?
- [ ] Khi debug `MatchException` có đọc `getCause()`, stack trace và xác định giai đoạn lỗi không?
- [ ] Guard và thân nhánh có ném exception riêng cần xử lý ở tầng nghiệp vụ không?
- [ ] Fallback/default có đúng hợp đồng hay chỉ được thêm để che lỗi không?
- [ ] Có giám sát loại lỗi với context vừa đủ mà không làm rò rỉ dữ liệu nhạy cảm không?

**Ghi nhớ:** `MatchException` là dấu hiệu **matching thất bại bất thường**, chứ không phải một lần kiểm tra pattern trả false. Hai nguyên nhân quan trọng nhất là **record accessor ném lỗi (có cause)** và **exhaustive switch không match ở runtime (có thể không có cause)**. Xác định đúng tầng `null`, kiểm tra tính tương thích nhị phân của sealed/enum, và xử lý theo hợp đồng domain thay vì “bắt rồi bỏ qua”.

### Tài liệu tham khảo

- Oracle Java 21 API — `java.lang.MatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
- Java Language Specification SE 21 — `14.30.2 Pattern Matching` và `14.11.3 Execution of switch:` https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
