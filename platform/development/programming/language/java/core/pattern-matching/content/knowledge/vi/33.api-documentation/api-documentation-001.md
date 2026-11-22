# Viết Javadoc cho sealed hierarchy trong Java

## 1. Vì sao sealed hierarchy cần Javadoc riêng?

`sealed` và `permits` giới hạn những kiểu trực tiếp được phép mở rộng một class/interface. Ví dụ:

```java
sealed interface Outcome permits Success, Failure, Retry {}

record Success(String requestId, String value) implements Outcome {}
record Failure(String requestId, String errorCode, String message)
        implements Outcome {}
record Retry(String requestId, int afterSeconds) implements Outcome {}
```

Đoạn này minh họa cấu trúc, chưa phải một chương trình độc lập. Compiler biết tập subtype được phép, nhưng **không biết hợp đồng nghiệp vụ**: `Success` đại diện thành công nào, `Retry.afterSeconds` có đơn vị gì, `Failure.errorCode` có thể null hay không, hay một giá trị `Outcome` null cần xử lý ra sao.

**Javadoc** cần biến một cây kiểu thành **hợp đồng API có thể sử dụng được**, giải thích những thông tin mà chỉ đọc tên class hoặc `permits` không đủ:

1. Vai trò và phạm vi của kiểu cha.
2. Ý nghĩa của từng permitted subtype và điều kiện tạo ra subtype đó.
3. Quy tắc dữ liệu của từng record component: bắt buộc, nullable, đơn vị và giới hạn.
4. Hành vi của method, constructor, factory; `@return` và `@throws`.
5. Cách caller phân nhánh, chính sách xử lý null và phiên bản API.
6. Điều gì xảy ra khi thư viện bổ sung, deprecate hoặc thay đổi một subtype.

**Mốc Java:** `record` final từ Java 16 (JEP 395), `sealed` final từ Java 17 (JEP 409); record patterns và pattern matching for `switch` final từ Java 21 (JEP 440, 441). Ví dụ chương trình cuối bài dùng **JDK 21+** do có `switch` trên record pattern, không cần `--enable-preview`. Javadoc cho sealed hierarchy không bắt buộc phải dùng pattern switch: cùng một mô hình sealed có thể được tài liệu hóa trên Java 17.

## 2. Phân chia trách nhiệm tài liệu theo tầng

| Thành phần API | Nội dung cần ghi trong Javadoc |
| --- | --- |
| **Sealed interface/abstract class** | Ý nghĩa domain, danh sách biến thể và liên kết, quan hệ giữa chúng, giới hạn mở rộng, null policy |
| **Permitted subtype** | Trạng thái cụ thể biểu thị điều gì, khi nào xảy ra, điều kiện hợp lệ của subtype |
| **Record declaration** | Mô tả từng component bằng `@param`, đơn vị, nullable, bất biến nếu liên quan |
| **Public constructor/factory** | Validation, các trường hợp ném exception, điều kiện bảo đảm khi khởi tạo thành công |
| **Public abstract/default method** | Hợp đồng chung cho caller, kết quả, side effect, quyền override nếu có |
| **Helper API dùng pattern switch** | Các nhánh được xử lý, null behavior, đầu ra, lỗi và khả năng thay đổi khi thêm subtype |

**Đừng chỉ ghi Javadoc ở kiểu cha.** Những câu như “An outcome” hoặc “A retry” không cho người dùng biết `Retry(0)` có hợp lệ không, hay `Failure.message` có thể lộ ra client ngoài hệ thống.

### 2.1. Javadoc kiểu cha nói về tổng thể

Ví dụ Javadoc cho interface:

```java
/**
 * The result of one request, with three permitted variants.
 *
 * <p>Each subtype represents a different business outcome.
 * A null reference is not one of the variants.</p>
 *
 * @apiNote Prefer an exhaustive pattern switch to arbitrary type tags.
 * @since 1.0
 * @see Success
 * @see Failure
 * @see Retry
 */
public sealed interface Outcome permits Success, Failure, Retry {
    // Public API methods...
}
```

Đây là đoạn **minh họa**, cần được đặt trong một class/package đã khai báo các subtype. Dùng `{@link Success}` hoặc `{@link Retry}` trong phần diễn giải cũng tạo liên kết inline tới kiểu liên quan.

Javadoc cần nêu đúng bản chất “closed world”: một `sealed` interface trực tiếp chỉ cho các subtype có trong `permits` được thực thi theo các quy tắc Java. **Không có thẻ Javadoc chuẩn `@sealed`** để thay thế từ khóa `sealed`; chỉ code của ngôn ngữ mới thực thi hạn chế đó.

Lưu ý: `sealed` không đồng nghĩa mọi kiểu con ở mọi cấp đều cuối cùng. Một permitted subtype được khai báo `non-sealed` có thể mở ra chỗ mở rộng mới. Trong ví dụ này, subtype là các `record`, mặc nhiên `final`, nên tập biến thể đơn giản và đóng.

### 2.2. Javadoc subtype nói về ý nghĩa riêng

- `Success`: yêu cầu hoàn thành thành công và có kết quả.
- `Failure`: yêu cầu hoàn thành với mã lỗi ứng dụng và thông tin lỗi.
- `Retry`: yêu cầu xử lý lại sau số giây dương; không phải kết quả terminal.

Dùng các mô tả làm rõ quan hệ giữa các trạng thái, không chỉ lặp lại tên subtype. Nếu tên như `Failure` còn bao gồm lỗi cần retry, phải đổi mô hình hoặc giải thích chính xác; đừng viết docs mâu thuẫn với phương thức `terminal()`.

## 3. Các tag Javadoc nên dùng

| Tag | Chức năng | Ví dụ |
| --- | --- | --- |
| `@param` | Tham số phương thức hoặc **component của record** khi đặt trên khai báo record | `@param afterSeconds strictly positive delay in seconds` |
| `@return` | Mô tả kết quả method | `@return a nonblank correlation ID` |
| `@throws` | Mô tả ngoại lệ và tình huống ném | `@throws IllegalArgumentException if delay is not positive` |
| `@since` | Phiên bản **thư viện/API** bắt đầu có thành phần | `@since 1.0` |
| `@see` | Liên kết đến mục liên quan trong tài liệu | `@see Retry` |
| `{@link Type}` | Link inline đến type, method hoặc member | `{@link Outcome}` |
| `{@code value}` | Code literal inline, tránh HTML bị hiểu sai | `{@code null}` |
| `@apiNote` | Lưu ý cách sử dụng API cho caller | `@apiNote Handle every variant.` |
| `@implSpec` | Đặc tả hành vi của implementation mặc định/cụ thể | `@implSpec Returns false only for Retry.` |
| `@implNote` | Ghi chú implementation khi có ích cho người triển khai | `@implNote Uses a type test.` |
| `{@inheritDoc}` | Kế thừa phần documentation của một method override theo quy tắc Javadoc | `/** {@inheritDoc} */` |

**`@since 1.0` là phiên bản của thư viện ví dụ**, không phải “Java có sealed từ version 1.0”. Nếu có một subtype mới từ release 1.1, ghi `@since 1.1` ở subtype đó. Mốc tối thiểu JDK để biên dịch là một thông tin khác, nên ghi trong hướng dẫn build/compatibility.

Không cần dùng tất cả tag trên cho mọi thành viên. Ví dụ, `@implSpec` hữu ích cho `default method` thật sự có body, nhưng một record chỉ chứa component không nhất thiết cần nó.

## 4. Viết @param cho record component

Trên **Javadoc của record declaration**, `@param` mô tả từng component. Ví dụ:

```java
/**
 * A request to retry after a delay.
 *
 * @param requestId nonblank correlation identifier
 * @param afterSeconds delay in seconds, strictly greater than zero
 * @since 1.0
 */
public record Retry(String requestId, int afterSeconds) implements Outcome {
    // Validation...
}
```

`afterSeconds` là primitive `int`, nên không thể nhận `null`. Quy tắc cần giải thích là **giá trị phải lớn hơn 0**, với **đơn vị giây**. Mô tả “afterSeconds is the delay” không đủ cho người sử dụng API.

Record có các accessor (`requestId()`, `afterSeconds()`) và constructor chuẩn. Tài liệu `@param` trên khai báo record giúp Javadoc trình bày contract của các component. Nếu người viết định nghĩa **compact canonical constructor** để validate, cần mô tả các ngoại lệ tương ứng tại constructor:

```java
/**
 * Validates a retry request.
 *
 * @throws IllegalArgumentException if requestId is null/blank
 *         or afterSeconds is not positive
 */
public Retry {
    requireText(requestId, "requestId");
    if (afterSeconds <= 0) {
        throw new IllegalArgumentException("afterSeconds must be positive");
    }
}
```

Đoạn thứ hai là **thân khai báo constructor trong record Retry**, giả sử có helper `requireText` như ở chương trình hoàn chỉnh. Compact constructor thực thi validation trước khi Java hoàn tất việc gán các component. Viết “afterSeconds strictly positive” trong Javadoc mà cho phép `new Retry("REQ-1", -2)` vẫn tạo được đối tượng là **một tài liệu sai**, không phải một invariant.

### 4.1. Ghi chính sách null rõ ràng

Phân biệt các trường hợp:

- Biến tham chiếu `Outcome outcome` vẫn có thể bằng `null`; `sealed` không cấm điều đó.
- Một đối tượng `Success` có thể chứa component null nếu constructor cho phép; record không tự cấm mọi null.
- Record pattern như `Success(var id, var value)` vẫn có thể lấy một component `value == null` bằng `var`; pattern không phải validator nghiệp vụ.
- Record pattern con dạng `NestedRecord(...)` không khớp nếu toàn bộ giá trị record ở tầng đó bằng null; khác với `var` nhận null.

Với API có ràng buộc không nhận null, nên dùng validation thực sự và ghi `@throws` khi phù hợp. Nếu một phương thức cho phép null để đại diện “không có dữ liệu”, ghi rõ ở `@param` và `@return`.

## 5. Phương thức chung: @return, @apiNote và @implSpec

Sealed interface có thể định nghĩa hợp đồng chung:

```java
public sealed interface Outcome permits Success, Failure, Retry {
    /**
     * Returns the correlation identifier.
     *
     * @return a nonblank request identifier
     */
    String requestId();

    /**
     * Reports whether processing has finished without another attempt.
     *
     * @return true for completed outcomes, false for a retry request
     * @implSpec This implementation returns false only for {@link Retry}.
     */
    default boolean terminal() {
        return !(this instanceof Retry);
    }
}
```

`requestId()` là method chung; mỗi record có component `requestId` và accessor tương ứng đáp ứng hợp đồng. Các constructor ở ví dụ cuối bài kiểm tra mã phải khác null/blank nên `@return` không nói quá về dữ liệu.

Ở `terminal()`, `@return` mô tả kết quả người gọi quan sát được; `@implSpec` diễn đạt cách thực thi của default implementation. Nếu sau này `permits` mở rộng thành loại khác, cả implementation lẫn documentation này cần được xem lại.

`@apiNote` thích hợp cho lời khuyên sử dụng, như “Prefer an exhaustive pattern switch”. `@implNote` dùng khi cần ghi chú về implementation, ví dụ lý do chọn thuật toán; không nên đưa các chi tiết triển khai dễ thay đổi thành một cam kết công khai nếu chúng không phải hợp đồng.

### 5.1. Kế thừa Javadoc với {@inheritDoc}

Một method `@Override` có thể kế thừa nội dung Javadoc của method ở superclass/interface bằng `{@inheritDoc}`, nếu cơ chế kế thừa documentation áp dụng phù hợp. Ví dụ **đặt bên trong record Retry** khi tự viết accessor:

```java
/** {@inheritDoc} */
@Override
public String requestId() {
    return requestId;
}
```

Đoạn code này **không bắt buộc**; record tự cung cấp accessor. Quan trọng hơn: `{@inheritDoc}` trên method **không tự tạo Javadoc cho cả record subtype**, không thể dùng thay mô tả của `Retry` và không làm thay đổi danh sách `permits`.

Với method override thay đổi contract hoặc thêm ràng buộc quan trọng, phải ghi tài liệu rõ ràng, thay vì dùng `{@inheritDoc}` để che sự khác biệt.

## 6. Chương trình độc lập: sealed hierarchy có Javadoc đầy đủ

Tạo file **`SealedHierarchyJavadocDemo.java`**:

```java
/**
 * Demonstrates a documented, closed outcome API.
 *
 * @since 1.0
 */
public class SealedHierarchyJavadocDemo {
    private static void requireText(String text, String name) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(name + " required");
        }
    }

    /**
     * Result of one request, with exactly three permitted variants.
     *
     * <p>Each variant has its own data contract. A null reference is
     * not an outcome variant; callers must decide how to handle null.</p>
     *
     * @apiNote Prefer an exhaustive pattern switch to arbitrary type tags.
     * @since 1.0
     * @see Success
     * @see Failure
     * @see Retry
     */
    public sealed interface Outcome permits Success, Failure, Retry {
        /**
         * Returns the correlation identifier.
         *
         * @return a nonblank request identifier
         */
        String requestId();

        /**
         * Reports whether processing has finished without another attempt.
         *
         * @return true for completed outcomes, false for a retry request
         * @implSpec This implementation returns false only for {@link Retry}.
         */
        default boolean terminal() {
            return !(this instanceof Retry);
        }
    }

    /**
     * A successfully processed request.
     *
     * @param requestId nonblank correlation identifier
     * @param value nonblank result text
     * @since 1.0
     * @see Outcome
     */
    public record Success(String requestId, String value) implements Outcome {
        /**
         * Validates the success components.
         *
         * @throws IllegalArgumentException if an argument is null or blank
         */
        public Success {
            requireText(requestId, "requestId");
            requireText(value, "value");
        }
    }

    /**
     * A completed request that failed with a documented error.
     *
     * @param requestId nonblank correlation identifier
     * @param errorCode nonblank application error code
     * @param message nonblank readable explanation
     * @since 1.0
     */
    public record Failure(String requestId, String errorCode, String message)
            implements Outcome {
        /**
         * Validates all failure components.
         *
         * @throws IllegalArgumentException if a component is null or blank
         */
        public Failure {
            requireText(requestId, "requestId");
            requireText(errorCode, "errorCode");
            requireText(message, "message");
        }
    }

    /**
     * A request for a later attempt; it is not terminal.
     *
     * @param requestId nonblank correlation identifier
     * @param afterSeconds strictly positive delay before another attempt
     * @since 1.0
     */
    public record Retry(String requestId, int afterSeconds) implements Outcome {
        /**
         * Validates the retry components.
         *
         * @throws IllegalArgumentException if requestId is null/blank
         *         or afterSeconds is not positive
         */
        public Retry {
            requireText(requestId, "requestId");
            if (afterSeconds <= 0) {
                throw new IllegalArgumentException("afterSeconds must be positive");
            }
        }
    }

    /**
     * Converts an outcome to a short diagnostic string.
     *
     * @param outcome an {@link Outcome}, or null when absent
     * @return a string for the matching variant; "missing" for null
     * @apiNote Do not expose raw error details to untrusted clients.
     */
    public static String summarize(Outcome outcome) {
        return switch (outcome) {
            case Success(var id, var value) -> "success:" + id + ":" + value;
            case Failure(var id, var errorCode, var message) ->
                    "failure:" + id + ":" + errorCode;
            case Retry(var id, var delay) -> "retry:" + id + ":" + delay;
            case null -> "missing";
        };
    }

    public static void main(String[] args) {
        Outcome success = new Success("REQ-1", "stored");
        Outcome failure = new Failure("REQ-2", "OUT_OF_STOCK", "Try later");
        Outcome retry = new Retry("REQ-3", 30);

        System.out.println(summarize(success));
        System.out.println(summarize(failure));
        System.out.println(summarize(retry));
        System.out.println(summarize(null));
        System.out.println("terminal:" + success.terminal() + ":" + retry.terminal());

        try {
            new Retry("REQ-4", 0);
            throw new AssertionError("Invalid retry accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid-retry:" + expected.getMessage());
        }
    }
}
```

**Biên dịch và chạy bằng JDK 21+:**

```bash
javac --release 21 SealedHierarchyJavadocDemo.java
java SealedHierarchyJavadocDemo
```

**Đầu ra chính xác:**

```text
success:REQ-1:stored
failure:REQ-2:OUT_OF_STOCK
retry:REQ-3:30
missing
terminal:true:false
invalid-retry:afterSeconds must be positive
```

Đã kiểm tra chương trình bằng JDK 24/JShell và nhận đúng sáu dòng trên. Những cú pháp `sealed`, `record`, record pattern và `switch` với pattern đều là tính năng chính thức từ Java 21 trở về trước. Nếu dự án phải biên dịch bằng Java 17, phần sealed hierarchy/record vẫn có thể dùng, nhưng hàm `summarize` phải viết lại theo cú pháp `instanceof` type patterns hoặc xử lý đa hình; không hạ `--release` xuống 17 mà giữ nguyên `case Success(var id, ...)`.

### 6.1. Đối chiếu tài liệu với hành vi

- `@return` ở `requestId()` hứa một ID nonblank; ba compact constructors dùng `requireText` để bảo đảm điều này.
- `@param value` ở `Success` nói nonblank; `new Success("REQ-1", null)` sẽ bị constructor từ chối.
- `@param afterSeconds` ghi thời gian chờ dương; `new Retry("REQ-4", 0)` ném `IllegalArgumentException`.
- `terminal()` có implementation tương ứng với `@implSpec`: `Success` và `Failure` terminal, `Retry` không terminal.
- `summarize(null)` trả `"missing"` như `@return`; biểu thức có `case null`.
- `Failure.message` là text chẩn đoán, còn hàm `summarize` chỉ xuất mã `errorCode`; `@apiNote` cảnh báo không lộ raw error details ra ngoài.

Chương trình cố ý dùng các bản ghi nhỏ với `String`/primitive để minh họa contract; nó chưa thể thay thế cơ chế logging, error localization, retry scheduling hay serializer cho hệ thống thật.

## 7. Sinh HTML Javadoc, đọc tài liệu đã phát hành

Sau khi tạo file, dùng JDK 21+:

```bash
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs SealedHierarchyJavadocDemo.java
```

Thư mục `api-docs` và HTML được tạo khi **người học chạy lệnh này** trên môi trường của mình. Mở `api-docs/index.html`, đi tới trang class `SealedHierarchyJavadocDemo` rồi các nested types `Outcome`, `Success`, `Failure`, `Retry`.

Để kiểm tra nghiêm ngặt hơn các vấn đề có thể phát hiện bằng Javadoc doclint:

```bash
javadoc -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d api-docs SealedHierarchyJavadocDemo.java
```

**Phân biệt kiểm thử:** phần runtime đã được kiểm chứng bằng JDK 24; lệnh `javadoc` là thao tác tạo tài liệu riêng để người học/dự án thực thi. Kết quả chạy chương trình **không chứng minh** HTML link hay doclint đã sạch; phải tạo và kiểm tra Javadoc thật khi phát hành.

**Checklist đọc trang tài liệu:**

1. Ở `Outcome`, có giải thích rõ các subtype, null policy và cách sử dụng không?
2. Các `@see`, `{@link Outcome}`, `{@link Retry}` trỏ đến đúng kiểu?
3. Các record component có nội dung `@param` về ý nghĩa, đơn vị và invariant?
4. Các constructor có mô tả điều kiện `IllegalArgumentException` khớp với code?
5. `terminal()` có `@return` và `@implSpec` diễn đạt rõ?
6. `summarize` nói rõ nhận null và trả gì?
7. Có warning doclint, lỗi HTML hoặc liên kết không phân giải cần sửa?
8. Tài liệu được sinh bằng đúng JDK, encoding, classpath/module path và version của thư viện sẽ phát hành?

Với dự án Maven/Gradle, nên tích hợp Javadoc task/plugin của hệ thống build để classpath và toolchain nhất quán. Javadoc có thể chạy qua CI, tùy chính sách của dự án yêu cầu warning hay error.

## 8. `permits` là quy tắc ngôn ngữ, không phải một câu trong comment

Nếu class trực tiếp triển khai sealed interface nhưng không có trong `permits`:

```java
// CỐ TÌNH SAI: Extra không được Outcome cho phép.
class Extra implements Outcome {
    @Override
    public String requestId() {
        return "REQ-5";
    }
}
```

Compiler từ chối việc triển khai đó. Kiểm thử tình huống này trên JDK 24 cho lỗi class không nằm trong danh sách `permits`. Đoạn code cố tình sai **không đặt trong chương trình chạy ở mục 6**.

Javadoc “You may extend this interface freely” sẽ là câu hứa sai nếu code là `sealed` chỉ cho phép vài subtype. Thêm `@see` không cho phép mở rộng. Cần thay code `permits`/modifier hoặc thiết kế một điểm mở rộng riêng có chủ đích.

### 8.1. Khi thêm subtype mới

Giả sử API phiên bản 1.1 bổ sung `Canceled`. Ngoài thay đổi source, phải cập nhật:

- Javadoc kiểu cha và các link `@see`.
- Tài liệu của `Canceled`, bao gồm component và `@since 1.1`.
- `@implSpec` của method mặc định như `terminal()` nếu trạng thái mới thay đổi logic.
- `switch` exhaustive xử lý Outcome; thêm case phù hợp.
- Unit tests, negative tests, public API/changelog và chính sách tương thích.

Thêm subtype vào một sealed hierarchy có thể khiến code client có `switch expression` exhaustive trước đó không còn bao phủ mọi trường hợp. Đừng coi việc thêm một record mới luôn là thay đổi tương thích vô hại.

### 8.2. Nếu cần subtype mở rộng bằng plugin

Một `sealed interface` đóng với chỉ các final records không thích hợp nếu yêu cầu mọi plugin bên ngoài được tự thêm subtype trực tiếp. Cần thiết kế interface mở, SPI/registry, hoặc một nhánh `non-sealed` thích hợp; đồng thời cập nhật docs để nói rõ điểm nào được extension và điểm nào không.

## 9. Những trường hợp cần Javadoc cẩn thận

**Về exception:** `@throws` nên mô tả các lỗi thật sự có thể xảy ra theo contract, không sao chép bất kỳ exception nào compiler chấp nhận. Ví dụ constructor của `Retry` ném `IllegalArgumentException` nếu mã request null/blank hoặc delay không dương; trường hợp đó đã có test.

**Về record:** các component là final, nhưng component tham chiếu object mutable có thể bị thay đổi thông qua object đó. Đừng ghi “deeply immutable” khi model chứa `List` hay một object mutable mà không defensive copy.

**Về `@since`:** ghi version của thư viện/API, không tự nhầm với Java language version. Java 21 dùng cho chương trình kiểm thử vì có pattern switch, nhưng `Outcome` sealed và record có thể tồn tại trong Java 17.

**Về kế thừa tài liệu:** method implementation có thể dùng `{@inheritDoc}` khi contract của method cha phù hợp; nhưng record declarations vẫn cần Javadoc riêng để giải thích subtype/record components. Với method override thay đổi semantic, viết docs cụ thể.

**Về deprecation:** annotation `@Deprecated` đánh dấu API trong code/compiler; Javadoc `@deprecated` giải thích lý do ngừng dùng và lựa chọn thay thế. Một subtype deprecated vẫn cần được xem xét trong `permits` và xử lý pattern theo chính sách migration, không tự xóa khỏi hierarchy.

**Về bảo mật:** `Failure.message` có thể chứa chi tiết nhạy cảm; Javadoc nên nêu giới hạn khi ghi log/hiển thị. Không hứa “safe for public output” nếu chưa có quy tắc lọc và test.

## 10. Những lỗi phổ biến khi viết Javadoc

| Lỗi | Hậu quả và cách sửa |
| --- | --- |
| Chỉ Javadoc kiểu cha, bỏ trống subtype | API có trạng thái nhưng không có semantic rõ; tài liệu hóa từng subtype |
| Dùng `@param` chỉ lặp tên component | Không biết đơn vị/ràng buộc; ghi rõ ý nghĩa và giới hạn dữ liệu |
| Viết `@since 21` để ngụ ý JDK 21 | Dễ gây nhầm phiên bản thư viện; ghi version library và yêu cầu JDK riêng |
| Coi `@sealed` là lệnh quy định subtype | Không có tag chuẩn thay thế `sealed`/`permits` trong Java |
| Ghi component non-null nhưng constructor cho null | Docs sai; thực thi invariant và thêm negative tests |
| Dùng `{@inheritDoc}` để khỏi viết docs record | Chỉ giúp kế thừa tài liệu method ở tình huống phù hợp, không thay docs subtype |
| Không mô tả lỗi constructor | Caller không biết điều kiện input hợp lệ; dùng `@throws` đúng và test |
| Tự động thêm `default` khi xử lý sealed hierarchy | Có thể che việc thiếu case khi thêm permitted subtype; cân nhắc exhaustive `switch` |
| Quên `case null` hoặc chính sách null | `null` không phải subtype; định nghĩa rõ có chấp nhận hay từ chối |
| Quên cập nhật Javadoc sau khi thêm subtype | API docs liệt kê thiếu biến thể; cập nhật liên kết, contract, tests và release notes |
| Coi stdout chạy đúng là Javadoc hợp lệ | Cần sinh HTML và kiểm doclint/link/encoding riêng |
| Copy pattern switch Java 21 vào source Java 17 | Lỗi source compatibility; dùng `instanceof` hoặc nâng toolchain |

## 11. Quy trình review theo từng loại API

**Ở sealed parent:**

- Kiểu cha mô tả domain và tập biến thể có chủ đích.
- Các `@see` hoặc `{@link}` liên kết đúng subtype và các hành vi liên quan.
- Tài liệu nói rõ null policy và extension policy.
- Việc thêm subtype có quy trình versioning và compatibility.

**Ở record subtype:**

- Tên trạng thái dễ hiểu.
- Mọi component quan trọng có `@param` nói rõ đơn vị/nullable/invariant.
- Constructor/factory bảo đảm các điều kiện hứa trong tài liệu.
- `@throws` mô tả ngoại lệ thực tế, đặc biệt với dữ liệu từ bên ngoài.

**Ở public methods:**

- `@param`/`@return`/`@throws` giải thích đầy đủ hợp đồng.
- `@apiNote` là lời khuyên sử dụng, `@implSpec` là thông tin implementation khi hữu ích.
- Override chỉ dùng `{@inheritDoc}` khi thật sự có tài liệu method được kế thừa phù hợp.
- Switch trên sealed type xử lý đủ variants, có null policy và test.

**Ở CI/documentation:**

- Build code đúng `--release` và runtime target.
- Chạy tests cho trạng thái hợp lệ, null và invariant invalid.
- Sinh HTML Javadoc, kiểm link/tag và cảnh báo doclint.
- Khi thay subtype/API, cập nhật docs và tests cùng lúc.

## 12. Bài tập: tự viết Javadoc cho một sealed API khác

Bài toán: API kết quả đặt vé gồm ba biến thể:

- `Confirmed(String bookingId, String confirmationCode)`: đã xác nhận; cả hai trường nonblank.
- `Rejected(String bookingId, String reason)`: bị từ chối; reason bắt buộc.
- `Waitlisted(String bookingId, int position)`: đang ở hàng chờ; `position` là số thứ tự dương, bắt đầu từ 1.

Yêu cầu:

1. Định nghĩa `sealed interface BookingResult permits Confirmed, Rejected, Waitlisted` và ba record triển khai.
2. Viết Javadoc cho parent giải thích tập biến thể, chính sách null và cách caller phân nhánh.
3. Viết `@param` cho từng record component, nhất là đơn vị của `position` và ý nghĩa `confirmationCode`.
4. Thêm compact constructors kiểm tra invariant; ghi `@throws IllegalArgumentException`.
5. Viết `describe(BookingResult value)` với record patterns và `case null`; test từng nhánh, dữ liệu sai và null.
6. Thử một subtype ngoài `permits` để quan sát compiler từ chối; sửa Javadoc khi mở rộng hierarchy.
7. Sinh HTML `javadoc -Xdoclint:all` rồi review links, tag và nội dung contract.

Gợi ý cách chú thích (đoạn khai báo rút gọn, chưa có validation):

```java
/**
 * A booking accepted and assigned a confirmation code.
 *
 * @param bookingId nonblank identifier
 * @param confirmationCode nonblank code for the booking
 * @since 1.0
 */
record Confirmed(String bookingId, String confirmationCode)
        implements BookingResult {}
```

Gợi ý xử lý các biến thể (đặt trong class/phương thức có model đã khai báo):

```java
static String describe(BookingResult value) {
    return switch (value) {
        case Confirmed(var id, var code) -> "confirmed:" + id + ":" + code;
        case Rejected(var id, var reason) -> "rejected:" + id + ":" + reason;
        case Waitlisted(var id, var position) ->
                "waitlisted:" + id + ":" + position;
        case null -> "missing";
    };
}
```

Một người đọc HTML Javadoc phải trả lời được: `position = 0` có hợp lệ không; `describe(null)` trả gì; lớp bên ngoài có được implement `BookingResult` không; khi nào dùng `Rejected` thay `Waitlisted`. Nếu docs không trả lời được, nên cải thiện contract trước khi phát hành.

## 13. Kết luận và nguồn chính thức

Một **sealed hierarchy có thể hiểu và dùng đúng** khi kết hợp: (1) `sealed`/`permits` để compiler giới hạn quan hệ subtype; (2) record/constructor để bảo vệ dữ liệu; (3) Javadoc để người đọc nắm ý nghĩa và contract; (4) tests và HTML/doclint để xác minh hành vi và tài liệu.

Tài liệu tham khảo:

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Javadoc Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Oracle Java 21 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
