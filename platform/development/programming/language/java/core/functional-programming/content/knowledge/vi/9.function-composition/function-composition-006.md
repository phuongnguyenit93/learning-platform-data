# `Consumer.andThen()` và ảnh hưởng khi thao tác trước ném ngoại lệ

## 1. `Consumer.andThen()` dùng để làm gì?

Trong `java.util.function`, `Consumer<T>` là functional interface diễn tả một **hành động nhận một giá trị kiểu `T` và không trả giá trị**. Phương thức trừu tượng của nó là:

```java
void accept(T value);
```

`Consumer<T>` thường xuất hiện ở callback, logging, xử lý sự kiện, ghi dữ liệu, hoặc `Iterable.forEach` và `Stream.forEach`. Để ghép hai hành động theo **thứ tự đã định**, Java cung cấp phương thức mặc định `andThen`:

```java
default Consumer<T> andThen(Consumer<? super T> after)
```

Về hành vi, `first.andThen(second)` tạo **một Consumer mới**. Khi gọi `accept(input)` trên Consumer mới, Java:

1. Gọi `first.accept(input)`.
2. Nếu bước 1 **kết thúc bình thường**, gọi tiếp `second.accept(input)`.
3. Nếu một bước **ném ngoại lệ**, ngoại lệ được truyền ra người gọi; các bước sau trong chuỗi **không chạy**.

Cả hai hành động nhận **cùng một đầu vào**, chứ không nhận kết quả từ hành động trước. `Consumer.accept` trả `void`, nên không có giá trị để truyền cho bước kế tiếp.

Ví dụ:

```java
Consumer<String> save = id -> System.out.println("Save " + id);
Consumer<String> notify = id -> System.out.println("Notify " + id);

Consumer<String> workflow = save.andThen(notify);
workflow.accept("A01");
```

Đầu ra:

```text
Save A01
Notify A01
```

Đây là ví dụ đặt trong một phương thức hoặc `jshell` (cần `import java.util.function.Consumer;`). Lệnh tạo `workflow` **chưa thực hiện** `save` hay `notify`. Hai hành động chỉ thực sự chạy khi gọi `workflow.accept("A01")`.

**Điểm quan trọng của bài:** nếu `save` ném ngoại lệ, `notify` không chạy. Nếu `save` đã ghi dữ liệu trước khi ném, dữ liệu đó vẫn có thể đã được ghi. `andThen` không tự bắt lỗi, không khôi phục dữ liệu và không thực hiện rollback.

## 2. Hợp đồng thứ tự và truyền ngoại lệ

Có thể mô tả ý nghĩa của một chuỗi `first.andThen(second)` bằng pseudocode Java:

```java
Consumer<T> combined = input -> {
    first.accept(input);
    second.accept(input);
};
```

Đây là **mã mô tả khái niệm** (giả định `T`, `first`, `second` đã được khai báo trong một phương thức generic), không phải đoạn chương trình chạy độc lập. Nó giúp thấy rằng lời gọi thứ hai phụ thuộc việc lời gọi thứ nhất trả về bình thường. Việc triển khai thật còn kiểm tra `after` khác `null` ngay khi tạo chuỗi.

| Tình huống | `first.accept(x)` | `second.accept(x)` | Kết quả của `combined.accept(x)` |
| --- | --- | --- | --- |
| Cả hai thành công | Chạy | Chạy sau `first` | Kết thúc bình thường |
| `first` ném ngoại lệ | Chạy đến điểm ném | **Không chạy** | Ném ngoại lệ từ `first` |
| `first` thành công, `second` ném | Chạy | Chạy đến điểm ném | Ném ngoại lệ từ `second` |
| `after == null` ở `andThen(null)` | **Chưa chạy** | Không có hành động hợp lệ | Ném `NullPointerException` khi ghép |
| Chỉ tạo `combined` mà chưa `accept` | **Chưa chạy** | **Chưa chạy** | Có đối tượng Consumer ghép |

Khi viết `a.andThen(b).andThen(c)`, thứ tự trên một lần `accept(x)` là `a → b → c`. Nếu `b` ném ngoại lệ thì `c` bị bỏ qua, dù `a` đã hoàn thành. Đây là **thứ tự thực thi tuần tự** của chuỗi hành động trong lời gọi đó, không phải cơ chế chạy bất đồng bộ hoặc bộ điều phối giao dịch.

### Bốn điều không nên suy diễn

- **Không có điều kiện “thất bại thì chạy bước sau”:** `andThen` không giống `finally`.
- **Không có rollback:** side effect đã xảy ra có thể còn nguyên.
- **Không tự thử lại:** nếu `first`/`second` lỗi, `andThen` không retry.
- **Không tự bắt ngoại lệ:** lỗi tiếp tục truyền ra, trừ khi **chính code của một Consumer** hoặc phía gọi `accept` xử lý.

## 3. Ví dụ Java 17 hoàn chỉnh, có thể chạy

Chương trình minh họa bốn kịch bản: toàn chuỗi thành công, bước kiểm tra đầu tiên lỗi, bước thứ hai lỗi sau khi bước đầu đã làm thay đổi trạng thái, và đối số `after` bằng `null`.

Tạo tệp **`ConsumerAndThenDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerAndThenDemo {
    public static void main(String[] args) {
        List<String> trace = new ArrayList<>();

        Consumer<String> validate = id -> {
            trace.add("validate:" + id);
            if (id.startsWith("X")) {
                throw new IllegalArgumentException("blocked " + id);
            }
        };

        Consumer<String> save =
                id -> trace.add("save:" + id);
        Consumer<String> notify =
                id -> trace.add("notify:" + id);

        Consumer<String> workflow =
                validate.andThen(save).andThen(notify);

        // Kịch bản 1: tất cả các bước thành công.
        workflow.accept("A01");

        // Kịch bản 2: validate ném ngoại lệ; save/notify không chạy.
        try {
            workflow.accept("X01");
        } catch (IllegalArgumentException ex) {
            trace.add("caught:" + ex.getMessage());
        }

        System.out.println("Trace 1: " + trace);

        // Kịch bản 3: hành động đầu đã chạy, hành động thứ hai lỗi.
        List<String> effects = new ArrayList<>();

        Consumer<String> charge =
                id -> effects.add("charged:" + id);

        Consumer<String> sendEmail = id -> {
            effects.add("email-attempt:" + id);
            throw new IllegalStateException("mail offline");
        };

        Consumer<String> finish =
                id -> effects.add("finished:" + id);

        try {
            charge.andThen(sendEmail)
                    .andThen(finish)
                    .accept("B02");
        } catch (IllegalStateException ex) {
            effects.add("caught:" + ex.getMessage());
        }

        System.out.println("Trace 2: " + effects);

        // Kịch bản 4: đối số after null bị từ chối khi ghép.
        try {
            save.andThen(null);
        } catch (NullPointerException ex) {
            System.out.println("Null after: NullPointerException");
        }

        System.out.println("Final trace: " + trace);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 ConsumerAndThenDemo.java
java ConsumerAndThenDemo
```

**Stdout xác định:**

```text
Trace 1: [validate:A01, save:A01, notify:A01, validate:X01, caught:blocked X01]
Trace 2: [charged:B02, email-attempt:B02, caught:mail offline]
Null after: NullPointerException
Final trace: [validate:A01, save:A01, notify:A01, validate:X01, caught:blocked X01]
```

### Giải thích các kết quả

**Kịch bản 1 — Thành công.** `workflow.accept("A01")` chạy `validate`, `save` và `notify` cùng với giá trị `"A01"`. Vì cả ba bước hoàn tất bình thường, danh sách `trace` có ba phần tử đầu: `validate:A01`, `save:A01`, `notify:A01`.

**Kịch bản 2 — Bước đầu ném ngoại lệ.** Với `"X01"`, `validate` ghi `validate:X01` vào trace rồi ném `IllegalArgumentException("blocked X01")`. Vì vậy `save` và `notify` **không được gọi** cho `"X01"`. Khối `catch` ngoài lời gọi `accept` ghi thêm `caught:blocked X01`. Bốn phần tử ghi trước đó vẫn ở danh sách `trace`: việc ném ngoại lệ không tự xóa log.

**Kịch bản 3 — Bước thứ hai ném ngoại lệ.** `charge` ghi `charged:B02`. `sendEmail` ghi `email-attempt:B02` rồi ném `IllegalStateException`. `finish` **không chạy** vì chuỗi dừng tại bước lỗi. Khối `catch` tiếp tục ghi `caught:mail offline`. Dòng `charged:B02` còn nguyên trong `effects`, cho thấy `andThen` không tự hoàn tác một side effect đã hoàn thành. Trong hệ thống thực, một khoản thanh toán đã ghi nhận cũng không thể giả định được hủy chỉ vì email báo lỗi.

**Kịch bản 4 — `andThen(null)`.** `Consumer.andThen` yêu cầu đối số `after` khác `null`. Lỗi `NullPointerException` xuất hiện **ngay lúc tạo chuỗi**, trước khi `accept` có thể chạy. Vì thế `save` cũng không chạy, và `Final trace` giữ nguyên so với `Trace 1`.

> Các `List<String>` trong demo chỉ là công cụ ghi lại thứ tự sự kiện. Chúng được sử dụng tuần tự trong một thread. Không dùng `ArrayList` dùng chung để ghi đồng thời từ nhiều lời gọi `accept` nếu chưa có cơ chế bảo vệ.

## 4. Thứ tự ghép khi có ba hay nhiều Consumer

`andThen` trả về một `Consumer<T>` mới, nên có thể tiếp tục ghép:

```java
Consumer<String> a = s -> System.out.println("A " + s);
Consumer<String> b = s -> System.out.println("B " + s);
Consumer<String> c = s -> System.out.println("C " + s);

Consumer<String> pipeline = a.andThen(b).andThen(c);
pipeline.accept("X");
```

Kết quả:

```text
A X
B X
C X
```

Về thứ tự, `a.andThen(b).andThen(c)` tương đương `a.andThen(b.andThen(c))` đối với các hành động hoàn thành bình thường. Trong cả hai cách ghép, một lần `accept` đi qua `a`, `b` rồi `c`; nếu bước trước ném ngoại lệ thì những bước sau bị bỏ qua. Đây không phải lời hứa rằng side effect của các hành động có thể tùy ý đổi chỗ: ví dụ `save.andThen(notify)` và `notify.andThen(save)` có thể tạo ra hành vi nghiệp vụ khác nhau.

### Mọi bước đều nhận cùng giá trị đầu vào

```java
Consumer<String> trimButIgnore = s -> s.trim();
Consumer<String> print = System.out::println;

trimButIgnore.andThen(print).accept("  Java  ");
```

Dòng in vẫn có khoảng trắng bao quanh `Java`! `String.trim()` tạo giá trị trả về và **không sửa** `String`; vì `Consumer` trả `void`, kết quả của `trim` bị bỏ đi. `print` nhận lại chính chuỗi đầu vào `"  Java  "`.

Nếu muốn **đầu ra của bước trước là đầu vào của bước sau**, dùng `Function<T,R>` với `andThen`, không dùng `Consumer<T>`:

```java
import java.util.function.Function;

Function<String, String> trim = String::trim;
Function<String, String> upper =
        s -> s.toUpperCase(java.util.Locale.ROOT);

String normalized = trim.andThen(upper).apply("  java  ");
// normalized == "JAVA"
```

**So sánh chính xác:**

| Đặc điểm | `Consumer<T>.andThen(after)` | `Function<T,R>.andThen(after)` |
| --- | --- | --- |
| Mục tiêu | Ghép các hành động | Ghép các phép biến đổi |
| Phương thức thực thi | `accept(T)` | `apply(T)` |
| Đầu ra | `void` | Giá trị `R`/kiểu mới |
| Tham số nhận ở bước thứ hai | Cùng giá trị `T` ban đầu | Kết quả do hàm đầu tạo ra |
| Nếu bước đầu ném ngoại lệ | Bước sau không được gọi | Bước sau không được gọi |
| Tự rollback các side effect | Không | Không |

## 5. Chính xác điều gì xảy ra nếu thao tác đầu ném ngoại lệ?

Xét:

```java
Consumer<String> first = value -> {
    System.out.println("before failure");
    throw new IllegalArgumentException("invalid");
};

Consumer<String> second =
        value -> System.out.println("second");

Consumer<String> composed = first.andThen(second);
composed.accept("A");
```

Đoạn này là **minh họa phương thức** và cố ý ném ngoại lệ. Khi chạy từ một phương thức không bắt exception:

1. In `before failure`.
2. Ném `IllegalArgumentException("invalid")`.
3. **Không** in `second`.
4. Lời gọi `composed.accept("A")` kết thúc bằng ngoại lệ; Java tiếp tục cơ chế truyền lỗi lên call stack.

Không nên ghi sẵn một *stack trace* chính xác cho ví dụ này: tên tệp, số dòng và môi trường chạy có thể làm stack trace khác nhau. Nội dung in trước lỗi và việc bước sau bị bỏ qua mới là tính chất cần kiểm chứng.

Nếu sau `composed.accept` còn một lệnh in mà không có `try/catch` hay `finally` phù hợp, lệnh đó không chạy trong luồng thực thi thông thường. Nếu muốn kiểm soát lỗi, caller phải bắt ngoại lệ hoặc thiết kế từng action xử lý lỗi theo hợp đồng.

### Ngoại lệ ở bước thứ hai

Nếu `first` hoàn thành, `second` bắt đầu và có thể ném. Ngoại lệ đó truyền ra ngoài; `andThen` không phân biệt “lỗi từ first” và “lỗi từ second” theo cách tự thay đổi exception. Trong chuỗi `first.andThen(second).andThen(third)`, nếu `second` ném, `third` cũng không chạy.

Với lỗi `Error` nghiêm trọng, nguyên tắc truyền kết thúc đột ngột tương tự: nếu lời gọi trước không hoàn tất bình thường thì bước sau không được chạy. Không nên bắt rộng `Throwable` chỉ để tiếp tục một quy trình nghiệp vụ; lỗi hệ thống có thể không thích hợp để phục hồi.

## 6. Tác dụng phụ đã xảy ra vẫn tồn tại

Một `Consumer` thường thực hiện side effect: thêm phần tử vào `List`, cập nhật field, ghi log, gửi message, ghi database hoặc gọi HTTP API. Khi hành động đầu **đã tạo side effect** rồi ném exception (hoặc bước sau ném), `andThen` **không có cơ chế đảo ngược**.

Ví dụ theo thời gian:

```text
accept(order)
    |
    v
[charge(order)] -- đã trừ tiền / ghi nhận sự kiện
    |
    v
[sendEmail(order)] -- lỗi
    X
[markFinished(order)] -- không chạy
```

Trạng thái cuối có thể là “đã trừ tiền nhưng chưa gửi email”. Điều đó khác với “mọi bước đều thất bại và hệ thống tự trở lại trạng thái cũ”.

Đây là lý do `andThen` **không phải** transaction manager, saga orchestrator, retry framework hay bộ xử lý lỗi. Các hành động chỉ được gọi lần lượt theo contract của `Consumer`. Việc một bước có hiệu lực lâu dài hay có thể hoàn tác phụ thuộc vào hệ thống mà nó tác động.

### Cẩn thận với retry

Nếu caller bắt ngoại lệ rồi chạy lại **toàn bộ** chuỗi, bước đã thành công ở lần trước có thể bị chạy lại:

```java
// Mã minh họa nghiệp vụ, không phải chương trình độc lập.
// try {
//     charge.andThen(sendEmail).accept(order);
// } catch (RuntimeException ex) {
//     charge.andThen(sendEmail).accept(order); // Có thể charge lần nữa!
// }
```

Không tự động retry khi hành động có side effect không **idempotent**. Với xử lý thực tế, có thể cần idempotency key, kiểm tra trạng thái, deduplication, outbox, cơ chế bù trừ hoặc giao dịch. Chọn cơ chế theo bản chất hệ thống: ví dụ thao tác database trong một transaction có thể rollback khi phù hợp, nhưng gửi email hoặc gọi dịch vụ ngoài không tự nằm trong cùng transaction database.

## 7. Xử lý lỗi: chọn vị trí bắt exception theo mục tiêu

### Cách A — Để lỗi truyền ra ngoài, caller quyết định

Phù hợp khi lỗi phải làm dừng toàn bộ chuỗi:

```java
try {
    validate.andThen(save).andThen(notify).accept("X01");
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}
```

Nếu `validate` ném thì `save` và `notify` không chạy. Caller có thể trả lỗi cho API, gắn trạng thái thất bại hoặc xử lý theo hợp đồng ứng dụng. Bắt lỗi ở ngoài **không làm bước sau chạy lại**.

### Cách B — Xử lý lỗi *bên trong* một hành động

Chỉ phù hợp nếu sau lỗi vẫn có thể tiếp tục một cách có chủ đích. Ví dụ ghi log là hành động “best effort” mà lỗi log không được phép chặn cập nhật một bộ đếm khác:

```java
Consumer<String> safeLog = value -> {
    try {
        writeLog(value); // Giả định phương thức này có sẵn.
    } catch (RuntimeException ex) {
        // Tại đây ứng dụng phải có chính sách ghi nhận lỗi phù hợp.
    }
};

Consumer<String> next = value -> updateMetric(value);
safeLog.andThen(next).accept("A01");
```

Đây là **mã minh họa**, `writeLog` và `updateMetric` đại diện các phương thức có trong ứng dụng, không phải định nghĩa sẵn của JDK. Khi `safeLog` tự bắt exception và kết thúc bình thường, `next` được gọi. Nhưng không nên dùng cách này để nuốt lỗi **validate** hoặc **charge**: việc bước sau tiếp tục có thể vi phạm quy tắc nghiệp vụ. Bắt đúng loại ngoại lệ, theo dõi lỗi đầy đủ và cân nhắc mục tiêu của từng action.

### Cách C — Luôn làm cleanup bằng `finally`

Nếu cleanup phải chạy dù một action ném lỗi, đặt nó trong `finally` hoặc dùng `try-with-resources` khi quản lý tài nguyên:

```java
try {
    first.andThen(second).accept(value);
} finally {
    cleanup.accept(value);
}
```

Ví dụ này giả định các biến `first`, `second`, `cleanup`, `value` đã được khai báo. `finally` chạy khi control rời khỏi `try` theo cách thông thường, kể cả khi action trong `try` ném exception. Nếu `cleanup` cũng ném, cần xem xét cách giữ thông tin về lỗi ban đầu; xử lý tài nguyên dùng `try-with-resources` thường hữu ích vì hỗ trợ *suppressed exceptions*.

**Không thay `finally` bằng `first.andThen(cleanup)`** nếu mục tiêu là cleanup chắc chắn được gọi: khi `first` ném, `cleanup` trong `andThen` không chạy.

### Cách D — Dùng giá trị biểu diễn kết quả cho bước xử lý tiếp theo

Khi cần phân nhánh thành công/thất bại và trả thông tin chi tiết, có thể thiết kế một `Function<Input, Result>` trả kiểu kết quả chứa trạng thái thành công/lỗi, rồi quyết định có thực hiện side effect hay không ở tầng điều phối. `Consumer<T>` chỉ có `accept(T)` trả `void`, nên không cung cấp trực tiếp một kênh trả trạng thái nghiệp vụ.

Một lựa chọn khác là kiểm tra trước khi tạo chuỗi hành động, ví dụ parse/validate thành giá trị đã được xác thực rồi mới thực hiện ghi. Điều này giảm khả năng side effect xảy ra trước khi phát hiện dữ liệu sai, nhưng **không loại bỏ mọi lỗi** về mạng, I/O hoặc đồng thời.

## 8. `andThen(null)` và null của giá trị đầu vào khác nhau

Lời gọi:

```java
Consumer<String> print = System.out::println;
// print.andThen(null); // Ném NullPointerException ngay khi ghép.
```

Khác với:

```java
Consumer<String> print = System.out::println;
print.accept(null); // PrintStream.println(String) in "null".
```

`after == null` được `Consumer.andThen` từ chối theo contract. Nhưng `value == null` khi gọi `accept` có được chấp nhận hay không **phụ thuộc từng Consumer**: `System.out.println` có cách xử lý null của riêng nó, trong khi `value -> value.length()` sẽ ném `NullPointerException`. Do đó cần quy định đầu vào null tại ranh giới API thay vì coi tất cả Consumer đều có cùng chính sách.

## 9. Checked exception và unchecked exception

Phương thức trừu tượng của `Consumer<T>` là `void accept(T t)` **không khai báo `throws` checked exception**. Vì vậy lambda/method reference đưa vào `Consumer<T>` không thể tự do ném một checked exception chưa được bắt, ví dụ `IOException`.

Ví dụ sai về biên dịch:

```java
// SAI nếu writeToFile khai báo throws IOException:
// Consumer<String> write = value -> writeToFile(value);
```

Có thể xử lý ngay trong hành động:

```java
Consumer<String> write = value -> {
    try {
        writeToFile(value); // Phương thức trong ứng dụng.
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
```

Đây là **đoạn minh họa** với phương thức `writeToFile` giả định tồn tại. `UncheckedIOException` là một unchecked exception, nên khi nó được ném qua chuỗi `andThen`, bước sau vẫn bị bỏ qua theo cùng quy tắc. Việc chuyển đổi exception nên có lý do rõ ràng; không phải mọi lỗi đều nên được gói thành unchecked exception.

Ngược lại, `IllegalArgumentException` hoặc `IllegalStateException` là unchecked exceptions, có thể được ném trực tiếp từ Consumer, như trong chương trình hoàn chỉnh.

## 10. `andThen` không tự đảm bảo an toàn luồng

`first.andThen(second)` thực hiện hai lời gọi theo thứ tự trong **mỗi lần `accept`**, nhưng nếu nhiều thread đồng thời gọi `accept` trên cùng một Consumer ghép, các lần gọi **có thể xen kẽ** với nhau:

```text
Thread A: first(A) -------- second(A)
Thread B:      first(B) -------- second(B)
```

Vì vậy thứ tự toàn cục không nhất thiết là `first(A), second(A), first(B), second(B)`. Nếu các action chạm vào `ArrayList`, counter thông thường hoặc tài nguyên chung, phải xem xét đồng bộ, thiết kế owner của trạng thái hoặc chuyển dữ liệu qua queue/actor/transaction phù hợp.

Trong Java Stream, dùng `parallelStream().forEach(composedConsumer)` có thể gọi cùng Consumer trên nhiều phần tử cùng lúc. `forEach` trên parallel stream cũng không bảo đảm thứ tự encounter order của side effect. Nếu yêu cầu chỉ là biến đổi/thu thập dữ liệu, ưu tiên `map`, `reduce`, `collect` hoặc `toList`; `andThen` thích hợp hơn với **một chuỗi hành động có side effect đã được xác định**.

Ngay cả khi các action thread-safe riêng lẻ, “thực hiện first rồi second” trên một đầu vào **không mặc nhiên là một transaction nguyên tử** khi xen kẽ với những lời gọi khác.

## 11. Phân biệt `Consumer.andThen` và các API liên quan

| API | Điều gì được ghép? | Hành vi khi bước đầu ném ngoại lệ |
| --- | --- | --- |
| `Consumer<T>.andThen(Consumer<? super T>)` | Hai hành động nhận cùng `T` | Bước sau không chạy |
| `BiConsumer<T,U>.andThen(BiConsumer<? super T,? super U>)` | Hai hành động nhận cùng cặp `T,U` | Bước sau không chạy |
| `Function<T,R>.andThen(Function<? super R,? extends V>)` | Hai phép biến đổi, đầu ra bước đầu sang bước sau | Bước sau không chạy |
| `Function<T,R>.compose(Function<? super V,? extends T>)` | Hàm `before` rồi hàm hiện tại | Hàm hiện tại không chạy nếu `before` lỗi |
| `Predicate<T>.and(Predicate<? super T>)` | Hai điều kiện logic | Có thể short-circuit khi điều kiện đầu `false`; nếu ném lỗi, lỗi truyền ra |

Đừng nhầm **thứ tự chạy** của `Consumer.andThen` với `Predicate.and`: `Predicate.and` là phép logic, nên khi điều kiện đầu trả `false`, điều kiện sau có thể không được đánh giá theo short-circuit, dù không có ngoại lệ. Đối với `Consumer.andThen`, nếu hành động đầu kết thúc bình thường thì hành động sau được gọi, bất kể nó đã in gì hoặc thay đổi state ra sao, bởi `Consumer` không trả boolean hay trạng thái.

## 12. Những lỗi thường gặp

**Lỗi 1 — Nghĩ `andThen` luôn chạy đủ hai bước.** Nếu bước đầu ném, bước sau không chạy. Viết test cho cả đường đi thành công và đường đi lỗi.

**Lỗi 2 — Nghĩ exception làm rollback.** Side effect xảy ra trước lúc ném vẫn có thể tồn tại. Đừng gọi lại quy trình ghi tiền/đơn hàng mà không có chiến lược idempotency.

**Lỗi 3 — Dùng `andThen(cleanup)` thay cho `finally`.** Cleanup bị bỏ qua khi action đầu ném; dùng `try/finally` hoặc `try-with-resources` theo loại tài nguyên.

**Lỗi 4 — Bắt mọi exception rồi bỏ qua để bước sau chạy.** Có thể che giấu thất bại kiểm tra dữ liệu hoặc thanh toán. Chỉ phục hồi khi quy tắc nghiệp vụ thực sự cho phép.

**Lỗi 5 — Kỳ vọng output action trước trở thành input action sau.** Cả hai Consumer nhận cùng `T`; cần `Function.andThen` nếu muốn ghép giá trị đầu ra/đầu vào.

**Lỗi 6 — Cho rằng chỉ cần tạo chuỗi là đã chạy.** `first.andThen(second)` trả một Consumer; hành động xảy ra khi `accept` được gọi.

**Lỗi 7 — Nghĩ `andThen` chạy song song.** Hợp đồng của nó mô tả thứ tự tuần tự trên mỗi invocation; đồng thời chỉ xuất hiện nếu chính caller gọi từ nhiều thread hoặc action tự tạo công việc bất đồng bộ.

**Lỗi 8 — Nhầm exception ở bước một và bước hai.** Khi cần chẩn đoán, đặt tên action rõ ràng, log ngữ cảnh phù hợp và để exception gốc được nhận diện. Không dựa vào `andThen` để phân loại lỗi.

**Lỗi 9 — Truyền `null` cho `after`.** `andThen(null)` ném `NullPointerException` khi ghép. Phân biệt với giá trị đầu vào null của `accept`.

**Lỗi 10 — Dùng Consumer cho một phép biến đổi cần trả dữ liệu.** `Consumer` bỏ kết quả; nếu bước sau cần giá trị đã xử lý, dùng `Function` hoặc dựng dữ liệu trung gian rõ ràng.

## 13. Bài tập thực hành

1. Tạo ba Consumer `a`, `b`, `c`, mỗi Consumer ghi tên bước vào một `List<String>`. Gọi `a.andThen(b).andThen(c).accept("A")`. Dự đoán chính xác `List` sau lời gọi.
2. Thay `b` thành Consumer ném `IllegalStateException("B failed")` **trước khi ghi dấu vết**. Sau khi bắt exception ngoài `accept`, `List` còn những phần tử nào? Vì sao `c` không chạy?
3. Cho `a` ghi `a:A` rồi ném. Khi gọi `a.andThen(b).accept("A")`, có còn `a:A` trong danh sách không? Phân biệt “side effect đã xảy ra” và “action hoàn tất bình thường”.
4. Trong `ConsumerAndThenDemo`, thay `workflow.accept("X01")` bằng `workflow.accept("A02")`. Dự đoán thêm ba mục vào `Trace 1` tương ứng `validate`, `save`, `notify`, không còn `caught:blocked X01`.
5. Thử `Consumer<String> c = System.out::println; c.andThen(null);`. Xác định thời điểm `NullPointerException` xảy ra và liệu `println` có chạy không.
6. Viết một ví dụ `first.andThen(cleanup)` mà `first` ném exception; sau đó sửa thành `try { first.accept(x); } finally { cleanup.accept(x); }`. So sánh trace trước và sau.
7. Giả sử `charge` có thể trừ tiền thật, `sendEmail` có thể thất bại. Phân tích vì sao retry toàn bộ `charge.andThen(sendEmail)` có nguy cơ trừ tiền hai lần; đề xuất idempotency key hoặc một cơ chế xử lý thất bại phù hợp.
8. Viết `Function<String,String>` cắt khoảng trắng rồi nối với hàm viết hoa bằng `andThen`. So sánh với `Consumer<String>` cắt khoảng trắng nhưng bỏ kết quả: bước in sau nhận chuỗi nào?
9. Phân tích một ứng dụng có nhiều thread gọi cùng một `Consumer`. Vì sao thứ tự `first(x)` trước `second(x)` không bảo đảm mọi lần gọi được thực hiện như một transaction?
10. Tạo `Consumer<String> validate` ném exception với chuỗi rỗng; thiết kế test kiểm tra `save` **không được gọi** khi `validate` lỗi và **được gọi đúng một lần** khi dữ liệu hợp lệ.

## 14. Checklist khi áp dụng `Consumer.andThen`

- Xác định **hành động nào phải chạy trước** và hành động nào chỉ được chạy khi bước trước thành công.
- Xác định **loại exception** mỗi bước có thể ném, caller nào sẽ xử lý và bước sau có nên tiếp tục hay không.
- Xác định **side effect đã có** nếu một bước lỗi giữa chừng; đừng giả định rollback.
- Với tác vụ cần retry, kiểm tra **idempotency**, transaction hoặc cơ chế bù trừ.
- Nếu cần cleanup dù lỗi, dùng `finally`/`try-with-resources` chứ không chỉ ghép `andThen`.
- Nếu cần truyền giá trị đã chuyển đổi sang bước kế, dùng `Function.andThen` hoặc xây mô hình dữ liệu trung gian.
- Nếu callback có thể chạy đồng thời, kiểm tra thread safety và quy tắc thứ tự giữa các invocation.
- Test ít nhất ba đường đi: **thành công**, **bước đầu lỗi**, **bước sau lỗi**; đối chiếu cả exception và những side effect còn lại.

**Kết luận kỹ thuật:** `Consumer.andThen` là phép **ghép các hành động `void` theo thứ tự**. Khi hành động trước ném ngoại lệ, hành động sau không chạy và ngoại lệ được chuyển ra ngoài; những thay đổi đã xảy ra trước thời điểm ném vẫn có thể tồn tại. Hiểu đúng hợp đồng nhỏ này giúp tránh các lỗi lớn về xử lý sự kiện, cập nhật dữ liệu, retry và nghiệp vụ có side effect.
