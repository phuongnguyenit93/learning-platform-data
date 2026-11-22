# Consumer.andThen và thứ tự thực hiện trong Java 8

## 1. Mục tiêu

`java.util.function.Consumer<T>` là một **functional interface** có phương thức trừu tượng `void accept(T value)`: nó *nhận một giá trị và thực hiện hành động*, không tạo ra giá trị trả về. Từ Java 8, `Consumer` có phương thức mặc định `andThen` để ghép **hai hành động tuần tự** thành một Consumer mới. Đây vẫn là API tiêu chuẩn, tiếp tục được sử dụng trong Java hiện đại.

Sau bài học, bạn có thể:

- Giải thích `Consumer<T>`, `accept` và `andThen` theo đúng contract.
- Chỉ ra hành động nào chạy trước, hành động nào chạy sau trong chuỗi `a.andThen(b).andThen(c)`.
- Phân biệt **tạo Consumer ghép** với **thực sự thực thi** bằng `accept`.
- Dự đoán chính xác hành vi khi bước đầu hoặc bước sau ném exception và khi đối số `after` là `null`.
- Hiểu tác động của side effect, shared mutable state, cùng đối số được truyền qua các bước và giới hạn của thao tác tuần tự.
- Áp dụng `Consumer.andThen` trong callback và Stream mà không suy diễn sai thứ tự giữa các phần tử hoặc tính an toàn đa luồng.

## 2. Contract của `Consumer<T>` và `andThen`

Trong API chuẩn:

```java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T t);

    default Consumer<T> andThen(Consumer<? super T> after) {
        // Định nghĩa chuẩn cho biết: nhận cùng t,
        // thực hiện Consumer hiện tại rồi Consumer after.
        // Đây là mô tả hành vi, không phải mã nguồn JDK.
    }
}
```

Phần khai báo trên **chỉ là phác họa chữ ký và ý nghĩa**, không phải code được phép biên dịch nguyên văn vì method có block nhưng không trả giá trị. Chữ ký thực tế quan trọng là `Consumer<T> andThen(Consumer<? super T> after)`.

Với hai Consumer `first` và `second`:

```java
Consumer<String> composed = first.andThen(second);
composed.accept("A");
```

Đây là một đoạn minh họa, giả sử `first` và `second` đã được khai báo trong cùng phạm vi. Khi gọi `composed.accept("A")`, thứ tự được xác định là:

1. `first.accept("A")`.
2. Nếu bước 1 hoàn tất bình thường, `second.accept("A")`.
3. `composed.accept("A")` hoàn tất sau cả hai bước, hoặc ném exception tại bước thất bại.

Từ `andThen` trong tên phương thức nhấn mạnh **hành động bên trái trước, hành động `after` sau**. Đây không phải toán tử chạy song song, không tạo transaction và không tự thêm retry.

### Lưu ý quan trọng: ghép chưa phải chạy

`first.andThen(second)` chỉ tạo ra một `Consumer` ghép. Hai callback **không chạy ngay** khi gọi `andThen`. Chúng chạy khi có lời gọi `accept` trên Consumer đã ghép, hoặc khi một API khác như `forEach` gọi nó.

Đừng nhầm với lời gọi `first.accept(value)` rồi `second.accept(value)`: hai lời gọi này chạy **ngay tại vị trí viết code**. Consumer ghép đóng gói cùng thứ tự để truyền đi và thực hiện sau.

### Cùng một đối số được truyền tiếp

Cả hai hành động nhận **cùng tham chiếu đầu vào `t`**, không có bản sao tự động:

```java
Consumer<StringBuilder> addPrefix = text -> text.insert(0, "pre-");
Consumer<StringBuilder> print = text -> System.out.println(text);
Consumer<StringBuilder> both = addPrefix.andThen(print);

both.accept(new StringBuilder("value")); // In: pre-value
```

Hai Consumer nhìn cùng một `StringBuilder`. `addPrefix` thay đổi object trước khi `print` quan sát nó. Nếu API yêu cầu immutable input, không được giả định `andThen` sẽ bảo vệ dữ liệu; hãy thiết kế dữ liệu immutable hoặc tạo copy có chủ đích.

## 3. Thứ tự trong chuỗi nhiều Consumer

`andThen` có thể nối tiếp:

```java
Consumer<String> pipeline = validate.andThen(save).andThen(log);
pipeline.accept("order-17");
```

Giả sử ba callback trên đã được tạo trước đó, thứ tự khi `accept` là:

```text
validate("order-17")
save("order-17")
log("order-17")
```

Cách viết `validate.andThen(save).andThen(log)` tương đương về **thứ tự chạy các callback** với `validate`, rồi `save`, rồi `log`, khi không có exception và không có thay đổi liên quan tới contract ở các hành động.

**Điều không được suy ra:** `andThen` không tự động quản lý tính nguyên tử. Nếu `save` ghi dữ liệu thành công nhưng `log` thất bại, `save` không tự hoàn tác. Nếu `validate` sửa state rồi báo lỗi, state có thể đã bị thay đổi. Thứ tự callback và việc **commit một giao dịch** là hai khái niệm khác nhau.

| Biểu thức | Thứ tự khi gọi `accept(x)` | Ghi chú |
| --- | --- | --- |
| `a.andThen(b)` | a → b | b chỉ chạy nếu a hoàn tất bình thường. |
| `a.andThen(b).andThen(c)` | a → b → c | Mỗi bước sau phụ thuộc việc bước trước không ném lỗi. |
| `b.andThen(a)` | b → a | Đổi chiều có thể đổi kết quả khi có side effect. |
| `a.andThen(b).andThen(a)` | a → b → a | a chạy hai lần; không có cơ chế loại trùng. |
| `a.andThen(b)` (không gọi `accept`) | Chưa thực thi a/b | Chỉ tạo Consumer ghép. |

## 4. Ví dụ Java hoàn chỉnh, chạy được

Ví dụ dùng ba bước `validate`, `store`, `audit` để thấy trường hợp thành công và lỗi ở các vị trí khác nhau. Tạo tệp **`ConsumerOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerOrderDemo {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        Consumer<String> validate = value -> {
            events.add("validate:" + value);
            if (value == null || value.trim().isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
        };
        Consumer<String> store = value -> events.add("store:" + value);
        Consumer<String> audit = value -> events.add("audit:" + value);

        Consumer<String> process = validate.andThen(store).andThen(audit);
        process.accept("A-7");
        System.out.println("success=" + events);

        events.clear();
        try {
            process.accept("");
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
        System.out.println("afterFailure=" + events);

        events.clear();
        Consumer<String> failsInMiddle = validate
                .andThen(value -> {
                    events.add("storeAttempt:" + value);
                    throw new IllegalStateException("storage offline");
                })
                .andThen(audit);
        try {
            failsInMiddle.accept("B-9");
        } catch (IllegalStateException ex) {
            System.out.println("middleError=" + ex.getMessage());
        }
        System.out.println("middleTrace=" + events);

        try {
            process.andThen(null);
        } catch (NullPointerException ex) {
            System.out.println("nullAfter=rejected");
        }

        Consumer<String> show = value -> System.out.println("seen=" + value);
        Arrays.asList("x", "y").forEach(
                show.andThen(value -> System.out.println("logged=" + value))
        );
    }
}
```

Biên dịch và chạy bằng JDK 17+ (mọi API trong chương trình cũng có từ Java 8):

```bash
javac ConsumerOrderDemo.java
java ConsumerOrderDemo
```

**Stdout chính xác:**

```text
success=[validate:A-7, store:A-7, audit:A-7]
error=blank
afterFailure=[validate:]
middleError=storage offline
middleTrace=[validate:B-9, storeAttempt:B-9]
nullAfter=rejected
seen=x
logged=x
seen=y
logged=y
```

### Phân tích kết quả

- Với `"A-7"`, cả ba bước hoàn tất; `events` ghi đúng thứ tự **validate → store → audit**.
- Với chuỗi rỗng, `validate` ghi một sự kiện rồi ném `IllegalArgumentException`; `store` và `audit` không được gọi. Bởi vậy danh sách chỉ còn `[validate:]`.
- Với `"B-9"`, bước `validate` thành công; bước `storeAttempt` ghi một sự kiện rồi ném `IllegalStateException`; `audit` không chạy. Việc đã ghi `storeAttempt` **không bị tự động hoàn tác**.
- `process.andThen(null)` ném `NullPointerException` tại thời điểm xây dựng composition, trước khi có lời gọi `accept` mới. Đó là contract của `andThen` khi `after == null`.
- `Arrays.asList("x", "y").forEach(...)` truyền mỗi phần tử vào **cùng một Consumer ghép**. Với danh sách này và `List.forEach` tuần tự, `seen=x` đứng ngay trước `logged=x`, rồi mới đến cặp dành cho `y`.

Ví dụ sử dụng `events` trong một luồng và có các bước chỉ ghi log để thấy rõ thứ tự. Trong ứng dụng thật, `store` có thể viết database hoặc gửi message; lúc đó cần chính sách transaction, retry/idempotency và xử lý lỗi riêng, không được quy trách nhiệm đó cho `andThen`.

## 5. Exception: quy tắc thực thi và lan truyền

Tài liệu API của `Consumer.andThen` nêu rõ: nếu **một trong hai hành động ném exception**, exception đó được chuyển ra ngoài Consumer ghép; nếu **hành động đầu** ném, hành động `after` không được thực thi.

Xét `a.andThen(b).andThen(c)`:

| Trường hợp | Đã thực thi | Không được thực thi | Kết quả |
| --- | --- | --- | --- |
| Không có lỗi | a, b, c | Không có | `accept` hoàn tất. |
| a ném lỗi | a (có thể đã tạo side effect) | b, c | Exception từ a lan ra. |
| b ném lỗi | a, b (b có thể đã tạo side effect) | c | Exception từ b lan ra. |
| c ném lỗi | a, b, c | Không có callback sau c | Exception từ c lan ra. |
| `after == null` khi ghép | Chưa chạy callback | Không áp dụng | `andThen(null)` ném NPE ngay khi ghép. |

**Không được coi việc b hoặc c không chạy là rollback.** Các side effect ở bước đã thực thi vẫn có thể tồn tại.

### Cẩn thận khi đưa `try/catch` vào từng callback

Khi callback tự bắt rồi **nuốt exception**, đối với composition nó đã "hoàn tất bình thường", nên Consumer phía sau **vẫn chạy**. Ví dụ minh họa:

```java
Consumer<String> safeLog = value -> {
    try {
        sendOptionalLog(value); // Một method do ứng dụng tự định nghĩa.
    } catch (RuntimeException ex) {
        recordMetric(ex);       // Một method do ứng dụng tự định nghĩa.
    }
};
```

Đoạn này **chỉ minh họa**: `sendOptionalLog` và `recordMetric` không thuộc JDK và không được khai báo ở đây. Nếu cần chạy, bạn phải tự cài đặt chúng. Ý nghĩa: callback có thể quyết định lỗi nào được xử lý nội bộ; `andThen` chỉ quan sát việc `accept` hoàn tất hoặc ném lỗi.

Khi lỗi thể hiện thất bại bắt buộc của nghiệp vụ (ví dụ validation hoặc ghi giao dịch), đừng âm thầm nuốt lỗi rồi cho bước sau chạy như thành công. Xác định rõ chính sách thất bại, retry và bù trừ ở tầng nghiệp vụ.

## 6. Side effect và lý do thứ tự quan trọng

`Consumer` thường được dùng cho **side effect**: ghi log, cập nhật một đối tượng, gửi thông báo, ghi metric, hoặc thao tác với kết quả. Vì các bước chạy cùng tham chiếu đầu vào theo thứ tự nối, đổi `a.andThen(b)` thành `b.andThen(a)` có thể làm đổi hành vi.

Ví dụ:

```java
Consumer<StringBuilder> trim = value -> {
    String normalized = value.toString().trim();
    value.setLength(0);
    value.append(normalized);
};
Consumer<StringBuilder> report = System.out::println;

StringBuilder input = new StringBuilder("  hello  ");
trim.andThen(report).accept(input); // In "hello".
```

Đây là đoạn ví dụ dùng được khi đặt trong method và có `import java.util.function.Consumer;`. Consumer `report` nhìn trạng thái **sau khi** `trim` sửa object. Nếu đảo `report.andThen(trim)`, nội dung được in trước khi chuẩn hóa; phép đổi thứ tự không bảo toàn contract.

Để tránh lỗi, cân nhắc:

1. **Tách validation khỏi hành động gây side effect** và bảo đảm validation chạy trước.
2. **Hạn chế mutation đầu vào** nếu những callback khác cũng nhận cùng object; dùng immutable value khi có thể.
3. **Giữ callback ngắn và ý nghĩa rõ**. Khi pipeline cần xử lý lỗi, transaction hoặc kết quả giữa các bước, một service method có cấu trúc rõ ràng có thể phù hợp hơn `andThen` thuần túy.
4. **Thiết kế idempotency** khi callback có thể được gọi lại do retry ở tầng khác; `andThen` tự nó không bảo đảm "chỉ thực hiện một lần" trong cả hệ thống.
5. **Không dựa vào side effect bên trong hoạt động Stream để điều khiển logic bên ngoài** nếu có thể dùng phép biến đổi dữ liệu thuần (`map`, `filter`, `collect`) rõ ràng hơn.

## 7. Kết hợp `Consumer.andThen` với `forEach` và Stream

Trong Java hiện đại, có thể dùng Consumer ghép để xử lý từng phần tử:

```java
List<String> items = java.util.Arrays.asList("A", "B");
Consumer<String> first = x -> System.out.println("first:" + x);
Consumer<String> second = x -> System.out.println("second:" + x);

items.forEach(first.andThen(second));
```

Đây là đoạn code minh họa **bên trong method** có `import java.util.List;` và `import java.util.function.Consumer;`. Với `List.forEach` thông thường của `Arrays.asList` và không có thay đổi đồng thời, output là:

```text
first:A
second:A
first:B
second:B
```

`forEach` gọi Consumer ghép cho từng phần tử. Với **mỗi lần** `accept(x)`, `andThen` bảo toàn thứ tự **first(x) trước second(x)**.

### Ranh giới của bảo đảm thứ tự

`Consumer.andThen` chỉ quy định **thứ tự hai hành động đối với cùng một lần `accept`**. Nó **không tự quy định** phần tử nào được xử lý trước trong collection hoặc stream.

- `List.forEach` trên danh sách có iteration order như ví dụ xử lý theo iteration order khi không có lỗi/chỉnh sửa đồng thời.
- `Stream.forEach` với stream chạy song song có thể thực thi phần tử ở các thread khác nhau và không cam kết encounter order. Các cặp hành động cho nhiều phần tử có thể đan xen.
- Nếu cần bảo toàn encounter order với ordered stream, `forEachOrdered` có contract về thứ tự phần tử. Nó không thay thế yêu cầu bảo vệ shared mutable state ngoài contract của Stream.
- `andThen` không tạo locking hoặc thiết lập transaction. Nếu nhiều thread đồng thời gọi cùng một Consumer ghép, callback phải được thiết kế để an toàn trong bối cảnh đó.
- Khi một callback ném lỗi trong `forEach`, việc lan truyền lỗi có thể chấm dứt phép duyệt; trong parallel stream, các phần tử khác có thể đã được xử lý hoặc đang chạy. Đừng dựa vào số lượng side effect đã xảy ra để suy ra rollback.

**Quy tắc thực tế:** hãy phân biệt **order trong một phần tử** (andThen) và **order giữa các phần tử** (collection/stream execution policy).

## 8. `Consumer.andThen` so với `Function.andThen`

Hai API đều có `andThen` nhưng mục đích khác nhau:

| Tiêu chí | `Consumer<T>.andThen` | `Function<T,R>.andThen` |
| --- | --- | --- |
| Dữ liệu vào | T | T |
| Kết quả public | `void` | Một giá trị `V` |
| Callback sau nhận gì? | **Cùng đối số T** như callback trước. | **Kết quả R** của hàm trước. |
| Mục tiêu | Chuỗi các hành động/side effect. | Chuỗi các phép biến đổi dữ liệu. |
| Xử lý lỗi | Exception lan ra, sau không chạy nếu trước ném. | Exception từ phép biến đổi lan ra theo logic gọi hàm. |

Ví dụ khác biệt về ý tưởng:

```java
Consumer<String> a = x -> System.out.println("A:" + x);
Consumer<String> b = x -> System.out.println("B:" + x);
// a.andThen(b).accept("x"): A:x rồi B:x; b vẫn nhận "x".

java.util.function.Function<String, Integer> length = String::length;
java.util.function.Function<Integer, String> explain = n -> "len=" + n;
// length.andThen(explain).apply("abcd") trả "len=4".
```

Đây là minh họa trong cùng một method đã import `Consumer`. Không dùng `Consumer.andThen` nếu bước thứ hai cần nhận **giá trị được tạo từ bước đầu**; khi đó `Function` hoặc một method phối hợp xử lý rõ ràng phù hợp hơn.

## 9. `Consumer<? super T>` và phương thức `BiConsumer.andThen`

Chữ ký thực tế `Consumer<T> andThen(Consumer<? super T> after)` dùng wildcard `? super T` vì `after` là **nơi tiêu thụ T**. Ví dụ một Consumer nhận `Object` vẫn dùng được sau Consumer nhận `String`:

```java
Consumer<String> printText = text -> System.out.println(text);
Consumer<Object> auditAny = value -> System.out.println(value);
Consumer<String> combined = printText.andThen(auditAny);
```

`auditAny` có thể nhận một `String` vì `String` là `Object`. Đây là một ứng dụng của **Consumer Super** trong quy tắc PECS (Producer Extends, Consumer Super). Không được hiểu wildcard như một phép ép kiểu; compiler chứng minh rằng `accept(T)` hợp lệ.

Ngoài `Consumer<T>`, `BiConsumer<T,U>` cũng có `andThen(BiConsumer<? super T, ? super U> after)`; cả hai hành động nhận **cùng một cặp đối số** và chạy tuần tự. Nếu hành động đầu ném exception, hành động sau không chạy. Chọn `BiConsumer` khi hợp đồng callback thực sự cần hai đầu vào.

Các hàm chuẩn trên vẫn hiện diện trong Java hiện đại; không cần sử dụng callback API tự chế hoặc thư viện lỗi thời để có cơ chế này.

## 10. Sai lầm phổ biến và cách tránh

1. **Mong `andThen` chạy ngay.** Chỉ gọi `accept` hoặc một API gọi `accept` mới khiến hành động thực thi.
2. **Cho rằng mỗi Consumer nhận đầu ra của Consumer trước.** `Consumer.accept` trả `void`; các bước nhận **cùng T**. Dùng `Function` khi cần pipeline chuyển đổi kết quả.
3. **Đảo thứ tự tùy ý.** `a.andThen(b)` và `b.andThen(a)` thường khác nhau nếu có side effect hoặc exception.
4. **Tưởng bước sau luôn chạy.** Nếu bước trước ném exception, phần sau bị bỏ qua. Nếu bước trước bắt và nuốt lỗi thì phần sau có thể vẫn chạy.
5. **Tưởng ghép Consumer là transaction.** Không có rollback tự động; side effect trước exception vẫn tồn tại.
6. **Cho rằng `andThen(null)` chỉ lỗi khi `accept`.** Thực tế `NullPointerException` được ném ngay khi gọi `andThen` với `after == null`.
7. **Mong parallel Stream giữ thứ tự các phần tử.** `andThen` giữ thứ tự trong mỗi cặp hành động, không đảm bảo thứ tự giữa các phần tử.
8. **Dùng `ArrayList` hay biến đếm mutable dùng chung từ nhiều callback chạy song song.** Có nguy cơ race/data corruption; cân nhắc collection concurrent, synchronization hoặc thiết kế không chia sẻ state.
9. **Trộn logging tùy chọn với nghiệp vụ bắt buộc mà không xác định lỗi.** Nếu `audit` là bắt buộc, lỗi của nó cần được phản ánh; nếu logging chỉ hỗ trợ, phải có quy tắc xử lý riêng và không làm sai kết quả nghiệp vụ.
10. **Dùng `andThen` thay cho kiểm soát luồng phức tạp.** Khi cần rẽ nhánh, retry, compensation, kết quả trung gian hoặc quản lý giao dịch, hãy dùng method/service có luồng điều khiển minh bạch.

## 11. Kiểm thử hành vi `andThen`

Không chỉ kiểm tra số lần gọi; hãy kiểm tra **đúng thứ tự** và **phần đã chạy trước khi lỗi**. Ví dụ một test đơn giản có thể dùng danh sách ghi vết:

```java
List<String> steps = new java.util.ArrayList<>();
Consumer<String> one = value -> steps.add("one:" + value);
Consumer<String> two = value -> steps.add("two:" + value);

one.andThen(two).accept("ok");
if (!steps.equals(java.util.Arrays.asList("one:ok", "two:ok"))) {
    throw new AssertionError("Unexpected order: " + steps);
}
```

Đoạn test này chạy trong method có import `List` và `Consumer`. Trong một dự án thực tế, dùng JUnit 5 hoặc test framework phù hợp để có các test riêng cho: tất cả bước thành công, bước đầu ném exception, bước sau ném exception, `after == null`, cùng tham chiếu mutable và nhiều phần tử có thứ tự. Với công việc đa luồng, test phải xét contract ordering của API gọi Consumer và cơ chế đồng bộ đang dùng.

Kết quả `andThen` có thể gọi nhiều lần. Hãy kiểm tra callback có **idempotent** hay không khi được gọi lại, nhất là ghi DB, gửi email/message hoặc tăng số đếm. `andThen` không deduplicate các side effect.

## 12. Ghi nhớ

`Consumer<T>.andThen(after)` tạo một Consumer mới mà khi `accept(t)` được gọi sẽ **thực hiện Consumer hiện tại trước, rồi `after` với cùng đối số t**. Nếu bước đầu ném exception, bước sau không chạy; nếu `after` là `null`, `andThen` ném `NullPointerException` ngay khi ghép. Tính tuần tự trong một lời gọi không đồng nghĩa có rollback, không đảm bảo thứ tự giữa các phần tử của parallel stream và không tự làm side effect trở nên thread-safe.

Để thiết kế callback an toàn, hãy đặt hành động theo thứ tự có ý nghĩa, biết bước nào là bắt buộc, kiểm thử trace/exception, quản lý mutation và chọn `Function` khi cần chuyền kết quả. Những nguyên tắc này áp dụng nguyên vẹn cho Java hiện đại.

**Tài liệu tham khảo chính thức:** [Java SE Consumer — `andThen`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Consumer.html#andThen(java.util.function.Consumer)), [`BiConsumer.andThen`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiConsumer.html#andThen(java.util.function.BiConsumer)), [Stream API — `forEach` và `forEachOrdered`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html), [`Function.andThen`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html#andThen(java.util.function.Function)).
