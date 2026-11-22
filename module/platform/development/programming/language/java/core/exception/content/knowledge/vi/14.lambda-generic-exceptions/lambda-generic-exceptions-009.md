# Giữ hợp đồng rõ ràng khi kết hợp Stream và thao tác có thể thất bại trong Java

`Stream` giúp mô tả chuỗi xử lý dữ liệu dưới dạng các thao tác `map`, `filter`, `flatMap`, `forEach` và các phép toán kết thúc. Nhưng khi **một thao tác trên phần tử có thể thất bại**, lựa chọn cách truyền lỗi trở thành một phần quan trọng của **hợp đồng phương thức**. Nếu không xác định rõ, chương trình dễ nuốt lỗi, trả kết quả thiếu phần tử mà không giải thích, mất nguyên nhân gốc hoặc đóng tài nguyên sai thời điểm.

Vấn đề nổi bật nhất trong Java là các phương thức như `Stream.map` dùng `Function.apply`, trong khi `Function.apply` **không khai báo checked exception**. Một thao tác đọc tệp hoặc parse theo API khai báo `throws IOException` / checked exception tùy chỉnh vì thế **không thể tự động ném loại checked đó xuyên qua lambda của `map`**.

Có ba chính sách thiết kế thường dùng:

1. **Fail-fast:** dừng pipeline ở lỗi đầu tiên và lan truyền một exception có ý nghĩa; thường dùng khi chỉ cần tất cả dữ liệu đều đúng thì mới có kết quả.
2. **Kết quả trên từng phần tử:** chuyển từng phần tử thành `Success` hoặc `Failure` có cấu trúc, để xử lý hết dữ liệu và tổng hợp các lỗi mong đợi.
3. **Phục hồi có chủ đích:** bỏ qua, thay thế hay thử lại một phần tử **chỉ khi hợp đồng cho phép** và phải ghi nhận đủ ngữ cảnh để không tạo thành công giả.

Không có một kiểu xử lý đúng cho mọi pipeline. Điều cần giữ rõ ràng là: **lỗi nào được xem là thất bại của cả thao tác, lỗi nào là dữ liệu của từng phần tử, lỗi nào được phục hồi, và bên nào chịu trách nhiệm đóng tài nguyên**.

## 1. Hiểu đúng Stream trước khi bàn về ngoại lệ

Một pipeline điển hình:

```java
List<Integer> values = List.of("2", "3", "4").stream()
        .map(Integer::parseInt)
        .filter(n -> n > 2)
        .toList();
```

Đoạn này hợp lệ với Java 17+. `Integer.parseInt` có thể ném `NumberFormatException`, nhưng đó là **unchecked exception**, vì vậy việc truyền method reference vào `map` không vi phạm quy tắc checked exception.

`Stream` là mô hình xử lý dữ liệu, không phải tự thân là một cấu trúc xử lý lỗi. Cần phân biệt:

- **Nguồn**: `Collection.stream()`, `Stream.of(...)`, `Files.lines(...)`...
- **Intermediate operations**: `map`, `filter`, `peek`, `flatMap`; nói chung chỉ dựng các bước xử lý, chưa kích hoạt việc duyệt nguồn.
- **Terminal operations**: `toList`, `collect`, `count`, `forEach`, `findFirst`, `anyMatch`...; khi chạy sẽ kích hoạt các phần pipeline cần thiết để cho ra kết quả.
- **Một lần sử dụng**: một stream sau khi đã tiêu thụ không được xem là pipeline có thể tái sử dụng; muốn xử lý lần nữa phải tạo stream mới từ nguồn phù hợp.
- **Close/ownership**: phần lớn stream trên collection không cần đóng, nhưng các stream được tạo từ nguồn I/O, ví dụ `Files.lines`, có thể nắm tài nguyên cần `close()`.

**Đặc biệt:** pipeline có thể không duyệt hết mọi phần tử: `findFirst` hoặc `anyMatch` có thể kết thúc sớm, và một exception cũng có thể cắt ngang quá trình. Không nên suy luận rằng gọi một terminal operation luôn khiến mọi lambda chạy một lần trên từng phần tử.

## 2. Vì sao checked exception không đi xuyên qua `map` thông thường?

Chữ ký liên quan về ý nghĩa:

```java
<R> Stream<R> map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

Đây là **chữ ký minh họa rút gọn** của API `Stream`. Kiểu `Function<T,R>` có phương thức hàm:

```java
R apply(T value);
```

Phương thức này **không có `throws IOException`, `throws SQLException` hoặc `throws Exception`**. Vì thế:

```java
static String load(String id) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(id));
}
```

là một phương thức Java hợp lệ khi đặt trong lớp. Nhưng dùng nó thế này:

```java
// Cố ý KHÔNG BIÊN DỊCH.
List<String> texts = ids.stream()
        .map(id -> load(id))
        .toList();
```

sẽ không hợp lệ nếu `ids` là `List<String>` và `load` khai báo `throws IOException`, vì body lambda có thể ném checked exception mà `Function.apply` không cho phép.

### Thêm `throws IOException` bên ngoài chưa đủ

Ví dụ:

```java
// Cố ý KHÔNG BIÊN DỊCH.
static List<String> loadAll(List<String> ids)
        throws java.io.IOException {

    return ids.stream()
            .map(id -> load(id))
            .toList();
}
```

Dù `loadAll` có `throws IOException`, lambda vẫn phải tương thích **hợp đồng của `Function.apply`**. `throws` của phương thức bao ngoài không được “truyền” tự động vào function descriptor của `map`.

Điểm cần nhớ: **nghĩa vụ checked exception được xác định theo kiểu hàm đích tại chỗ tạo lambda**. Đây là cơ chế compile-time, không phải lỗi chỉ phát sinh khi chương trình chạy.

## 3. Chọn hợp đồng fail-fast cho dữ liệu bắt buộc chính xác

Giả sử một thao tác cần chuyển các chuỗi thành số lượng đơn hàng dương. Nếu một dòng sai, có thể quy định rằng **toàn bộ thao tác thất bại**; caller không nhận một danh sách “có vẻ thành công” nhưng âm thầm thiếu dòng.

Với parser chỉ ném unchecked exception:

```java
List<Integer> quantities = List.of("2", "oops", "5")
        .stream()
        .map(Integer::parseInt)
        .toList();
```

Khi pipeline được thực thi, `Integer.parseInt("oops")` ném `NumberFormatException`; `toList()` không trả một `List<Integer>` bình thường cho caller. Việc có phần tử `2` đã xử lý trong nội bộ **không bảo đảm có một danh sách kết quả hợp lệ được trả về**.

Nhược điểm: nếu không bổ sung ngữ cảnh, message/stack trace có thể không nêu rõ **ID dòng** nào gây lỗi. Lúc đó nên dùng một loại exception mang thông tin có cấu trúc.

### Một wrapper có ý nghĩa

```java
static int parseQuantity(String id, String raw) {
    try {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return value;
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "invalid quantity for item " + id,
                cause);
    }
}
```

Đây là một **phương thức minh họa có thể biên dịch khi đặt trong một lớp**. Nó giữ `NumberFormatException` làm cause và thêm ID mặt hàng. Tuy nhiên, với dữ liệu nhạy cảm, chỉ nên đưa mã định danh không bí mật hoặc mã tương quan vào message; không nên ghi raw token hay toàn bộ payload.

Nếu muốn xử lý bằng chương trình theo mã thay vì parse message, có thể dùng custom exception có `errorCode` và `itemId`. Ví dụ hoàn chỉnh phía dưới sẽ làm rõ điều đó.

## 4. Lỗi phát sinh khi terminal operation chạy: hệ quả của tính lazy

Ví dụ:

```java
var pipeline = List.of("1", "bad", "3")
        .stream()
        .map(Integer::parseInt);
```

Ngay sau khi khai báo `pipeline`, việc parse các phần tử **chưa nhất thiết xảy ra**. Lời gọi:

```java
List<Integer> result = pipeline.toList();
```

mới là phép kết thúc kích hoạt quá trình cần thiết. `NumberFormatException` được quan sát tại thời điểm terminal operation thực thi, dù stack trace cũng có frame lambda/`Integer.parseInt`.

Hệ quả thực hành:

- Đặt `try-catch` quanh nơi **pipeline được tiêu thụ**, không chỉ nơi pipeline được xây dựng.
- Nếu một phương thức chỉ trả về `Stream` còn caller mới gọi terminal operation, thời điểm lỗi có thể thuộc về caller, không còn nằm trong `try-catch` của phương thức tạo stream.
- Không nên trả `Stream` đọc lười từ tài nguyên đã đóng, vì caller mới thực thi pipeline sau khi phương thức tạo nguồn đã rời phạm vi.
- Một phép kết thúc dạng short-circuit có thể không chạm tới phần tử lỗi; **không thấy exception chưa đủ để khẳng định mọi phần tử đều hợp lệ**.

### `findFirst` không tự kiểm tra toàn bộ nguồn

```java
var first = List.of("2", "bad", "4")
        .stream()
        .map(Integer::parseInt)
        .findFirst();
```

Đây là Java hợp lệ. Với sequential ordered stream này, `findFirst()` có thể trả `Optional.of(2)` mà không parse `"bad"`. Nó chỉ cần phần tử đầu để hoàn tất. Không có ngoại lệ **không có nghĩa** toàn bộ danh sách đã vượt qua validation.

Nếu cần xác thực tất cả phần tử, hãy chọn terminal operation và chính sách validation thực sự cần xử lý tất cả, hoặc mô hình hóa từng kết quả để ghi nhận lỗi từng dòng.

## 5. Ví dụ Java 17+ hoàn chỉnh: fail-fast, lazy và giữ nguyên nhân

Ví dụ dùng một custom **checked exception** trong hàm parser, sau đó chuyển nó thành unchecked wrapper khi buộc phải truyền vào `Stream.map`.

Lưu tệp **`StreamFailFastDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class StreamFailFastDemo {

    record Item(String id, String raw) {}

    static final class InvalidItemException extends Exception {
        private static final long serialVersionUID = 1L;

        private final String itemId;

        InvalidItemException(
                String itemId,
                String message,
                Throwable cause) {
            super(message, cause);
            this.itemId = itemId;
        }

        String getItemId() {
            return itemId;
        }
    }

    static final class ItemProcessingException
            extends RuntimeException {
        private static final long serialVersionUID = 1L;

        ItemProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    @FunctionalInterface
    interface CheckedFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static int parse(Item item) throws InvalidItemException {
        System.out.println("parse " + item.id());

        final int parsed;
        try {
            parsed = Integer.parseInt(item.raw());
        } catch (NumberFormatException cause) {
            throw new InvalidItemException(
                    item.id(), "not an integer", cause);
        }

        if (parsed <= 0) {
            throw new InvalidItemException(
                    item.id(), "must be positive", null);
        }

        return parsed;
    }

    static <T, R, E extends Exception> Function<T, R> failFast(
            CheckedFunction<T, R, E> action) {

        return value -> {
            try {
                return action.apply(value);
            } catch (RuntimeException ex) {
                throw ex;
            } catch (Exception cause) {
                throw new ItemProcessingException(
                        "stream conversion failed", cause);
            }
        };
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", "3"),
                new Item("B", "bad"),
                new Item("C", "5"));

        System.out.println("created pipeline");

        Stream<Integer> pipeline = items.stream()
                .map(failFast(StreamFailFastDemo::parse));

        System.out.println("before terminal");

        try {
            List<Integer> values = pipeline.toList();
            System.out.println("values=" + values);
        } catch (ItemProcessingException ex) {
            InvalidItemException cause =
                    (InvalidItemException) ex.getCause();

            System.out.println("failure=" + ex.getMessage());
            System.out.println("failing id=" + cause.getItemId());
            System.out.println("detail=" + cause.getMessage());
            System.out.println(
                    "root=" + cause.getCause()
                            .getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 StreamFailFastDemo.java
java StreamFailFastDemo
```

**Stdout dự kiến chính xác:**

```text
created pipeline
before terminal
parse A
parse B
failure=stream conversion failed
failing id=B
detail=not an integer
root=NumberFormatException
```

### Vì sao không có `parse C`?

Pipeline tuần tự này bắt đầu xử lý phần tử A, tiếp tục B, rồi parser B ném `InvalidItemException`. Adapter `failFast` bọc thành `ItemProcessingException` và ngoại lệ thoát khỏi `toList()`. Vì terminal operation thất bại, chương trình không tiếp tục tới phần tử C, cũng không in `values=[...]`.

Đây là **hợp đồng fail-fast**: dừng ở lỗi đầu tiên, không làm như đã chuyển thành công tất cả dữ liệu.

### Những thông tin lỗi được giữ lại

- Exception ngoài: `ItemProcessingException("stream conversion failed")` — diễn đạt thất bại ở tầng stream.
- Cause trực tiếp: `InvalidItemException` — thuộc tầng validation và có `itemId="B"`.
- Cause sâu: `NumberFormatException` — lỗi parse kỹ thuật ban đầu.
- Caller có thể đọc `getItemId()` thay vì phân tích message `"not an integer"`.

Trong ứng dụng thật, không cần lúc nào cũng tạo cả ba lớp lỗi. Mức bọc phụ thuộc ranh giới trừu tượng và trách nhiệm của caller. Ví dụ cố tình có nhiều tầng để thấy cơ chế bảo toàn cause và ngữ cảnh.

### Tại sao adapter bắt `RuntimeException` riêng?

`RuntimeException` kế thừa `Exception`. Nếu adapter chỉ bắt mọi `Exception` rồi bọc lại, nó sẽ bọc cả lỗi unchecked không liên quan, có thể che lớp lỗi có ý nghĩa hoặc làm stack trace khó đọc. Ví dụ giữ nguyên unchecked lỗi gốc, và chỉ bọc checked exception cần chuyển hợp đồng.

Không nên dùng adapter “sneaky throw” để lách kiểm tra checked exception mà không công bố gì với caller. Kể cả khi runtime có thể ném lỗi, kiểu `Function` ở compile time không thể hiện trách nhiệm xử lý checked exception đó.

## 6. Khi nào không nên dùng fail-fast?

Giả sử một tệp nhập liệu có 10.000 bản ghi, người dùng muốn sửa **toàn bộ bản ghi không hợp lệ trong một lượt**. Dừng ở lỗi đầu tiên buộc họ sửa một dòng, chạy lại, rồi tiếp tục thấy lỗi dòng khác. Trường hợp này **thu thập kết quả theo từng phần tử** có thể phù hợp hơn.

Một hợp đồng rõ ràng:

```text
Input item
   |
   v
parse/validate
   |
   +----> Success(itemId, parsedValue)
   |
   +----> Failure(itemId, errorCode, safeMessage, cause?)
```

Trong mô hình này, lỗi dự kiến như dữ liệu không phải số hoặc số lượng ngoài phạm vi **không nhất thiết được ném xuyên khỏi pipeline**. Chúng được biểu diễn bằng **giá trị kết quả**.

Lợi ích:

- Có thể tiếp tục xử lý phần tử tiếp theo sau một lỗi validation của phần tử trước.
- Caller nhận danh sách lỗi kèm ID và mã lỗi ổn định.
- Không cần dùng chuỗi `getMessage()` để phân loại.
- Có thể đếm tổng số thành công/thất bại, hiển thị lỗi theo từng dòng.
- Phân biệt lỗi **dự kiến của dữ liệu** với lỗi **bất thường của hạ tầng**.

Tuy nhiên, mô hình này **không tự động bảo đảm tính nguyên tử hoặc tính giao dịch**. Nếu pipeline đã ghi dữ liệu bên ngoài theo từng phần tử, việc tạo `Failure` sau đó không rollback các tác động trước đó.

## 7. Dùng `sealed interface` và `record` cho kết quả có cấu trúc

Java 17 hỗ trợ `record` và `sealed interface`. Chúng giúp định nghĩa một hợp đồng kết quả rõ ràng:

```java
sealed interface ParseOutcome permits Success, Failure {}

record Success(String itemId, int value)
        implements ParseOutcome {}

record Failure(String itemId, String code, String message)
        implements ParseOutcome {}
```

Đây là các kiểu minh họa. Một hàm `parse` có thể trả `ParseOutcome` mà không ném ngoại lệ checked cho các lỗi validation dự kiến.

Dùng kiểu trả về này trong `Stream.map`:

```java
List<ParseOutcome> outcomes = items.stream()
        .map(MyParser::parse)
        .toList();
```

Lời gọi là **minh họa**, giả định `MyParser.parse` và `items` có chữ ký phù hợp.

### Có nên nhét `Throwable` vào mọi `Failure`?

Không bắt buộc. Với dữ liệu nhập sai do người dùng, một `Failure(code, field, safeMessage)` có thể đủ để trả về giao diện. Nếu cần chẩn đoán kỹ thuật, có thể lưu cause nội bộ trong kết quả hoặc log có cấu trúc tại đúng ranh giới. Nhưng **không tự đưa nguyên Throwable vào DTO API công khai**.

Cũng tránh giữ input bí mật trong record kết quả; mọi record có `toString()` tự sinh có thể khiến các field bị in vào log.

## 8. Ví dụ Java 17+ hoàn chỉnh: thu thập mọi lỗi hợp lệ về nghiệp vụ

Lưu tệp **`StreamResultsDemo.java`**:

```java
import java.util.List;

public class StreamResultsDemo {

    record Item(String id, String raw) {}

    enum ErrorCode {
        INVALID_INTEGER,
        NOT_POSITIVE
    }

    sealed interface Outcome permits Success, Failure {}

    record Success(String itemId, int value)
            implements Outcome {}

    record Failure(
            String itemId,
            ErrorCode code,
            String message,
            Throwable cause)
            implements Outcome {}

    static Outcome parse(Item item) {
        final int number;

        try {
            number = Integer.parseInt(item.raw());
        } catch (NumberFormatException cause) {
            return new Failure(
                    item.id(),
                    ErrorCode.INVALID_INTEGER,
                    "quantity must be an integer",
                    cause);
        }

        if (number <= 0) {
            return new Failure(
                    item.id(),
                    ErrorCode.NOT_POSITIVE,
                    "quantity must be positive",
                    null);
        }

        return new Success(item.id(), number);
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", "2"),
                new Item("B", "bad"),
                new Item("C", "0"),
                new Item("D", "4"));

        List<Outcome> results = items.stream()
                .map(StreamResultsDemo::parse)
                .toList();

        for (Outcome result : results) {
            if (result instanceof Success ok) {
                System.out.println(
                        "OK " + ok.itemId() + "=" + ok.value());
            } else if (result instanceof Failure bad) {
                String root = bad.cause() == null
                        ? "none"
                        : bad.cause().getClass().getSimpleName();

                System.out.println(
                        "ERR " + bad.itemId() + " "
                        + bad.code() + " cause=" + root);
            }
        }

        long successCount = results.stream()
                .filter(result -> result instanceof Success)
                .count();

        long failureCount = results.stream()
                .filter(result -> result instanceof Failure)
                .count();

        System.out.println("successes=" + successCount);
        System.out.println("failures=" + failureCount);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StreamResultsDemo.java
java StreamResultsDemo
```

**Stdout chính xác:**

```text
OK A=2
ERR B INVALID_INTEGER cause=NumberFormatException
ERR C NOT_POSITIVE cause=none
OK D=4
successes=2
failures=2
```

### Phân tích

- A và D parse thành số dương nên được biểu diễn bằng `Success`.
- B có chuỗi `"bad"`. `NumberFormatException` được bắt trong parser và **chuyển thành dữ liệu `Failure`** với mã `INVALID_INTEGER`.
- C parse thành `0` nhưng vi phạm quy tắc dương; trả `Failure` mã `NOT_POSITIVE`. Đây là lỗi validation trực tiếp nên cause có thể để `null`.
- Parser xử lý đủ bốn phần tử: không có unchecked exception thoát ra để ngắt stream ở B hoặc C.
- `successCount` và `failureCount` được tính bằng **hai stream mới từ danh sách `results`**, không cố tái sử dụng một stream đã tiêu thụ.
- `ErrorCode` là dữ liệu có cấu trúc. Có thể thay câu message hoặc bản dịch mà nhánh xử lý không cần phân tích chuỗi.

Một chính sách quan trọng: **khi parser bắt `NumberFormatException`, đó là một lỗi dữ liệu dự kiến**. Chương trình không nên tiếp tục bắt tất cả `Throwable` để biến cả lỗi hệ thống như `OutOfMemoryError` thành một dòng `Failure` bình thường.

## 9. Tổng hợp kết quả ở ranh giới, không trả dữ liệu thiếu mà im lặng

Trong mô hình thu thập kết quả, sau khi có `List<Outcome>`, caller cần quyết định:

- Nếu **mọi phần tử thành công**, trả danh sách giá trị theo thứ tự cần thiết.
- Nếu có **bất kỳ Failure nào**, trả danh sách lỗi và không commit dữ liệu, nếu tác vụ yêu cầu tất-cả-hoặc-không-gì.
- Nếu hợp đồng chấp nhận **partial success**, trả cả các thành công và thất bại kèm trạng thái rõ ràng.
- Nếu một lỗi thuộc về **hạ tầng** hoặc lỗi không thể khôi phục, có thể vẫn cần fail-fast thay vì cố tiếp tục.

Ví dụ nguy hiểm:

```java
List<Integer> values = inputs.stream()
        .map(Parser::tryParse)
        .filter(java.util.Objects::nonNull)
        .toList();
```

Đây là đoạn minh họa, với `Parser.tryParse` giả định trả `null` khi parse thất bại. Nếu API không công bố quy tắc bỏ qua dữ liệu lỗi, kết quả có ít phần tử hơn nhưng caller **không biết những phần tử nào thất bại và vì sao**.

Thay vào đó, nếu bỏ qua dòng lỗi là chủ đích, ít nhất cần giữ log/đếm/diagnostic đúng chính sách và thể hiện điều đó trong tên API hoặc loại kết quả. Với yêu cầu audit, một tập `Success/Failure` thường rõ ràng hơn.

### `Optional` không thay cho tất cả thông tin lỗi

`Optional<T>` có thể biểu diễn “có hoặc không có giá trị”, nhưng **không mang loại lỗi, vị trí lỗi hoặc nguyên nhân**. Nếu caller cần phân biệt thiếu dữ liệu hợp lệ với dữ liệu không hợp lệ hay I/O thất bại, chỉ trả `Optional.empty()` có thể quá ít thông tin.

Sử dụng `Optional` khi việc không có giá trị là một kết quả bình thường đúng hợp đồng; dùng `Failure` có cấu trúc khi **nguyên nhân thất bại có ý nghĩa**.

## 10. Lỗi phần tử và lỗi pipeline không phải một loại

Một pipeline có thể chịu nhiều nguồn lỗi:

| Nguồn lỗi | Ví dụ | Hợp đồng nên cân nhắc |
| --- | --- | --- |
| Lỗi validation từng phần tử | `"abc"` không phải số | `Failure(itemId, INVALID_INTEGER)` hoặc fail-fast |
| Không tìm thấy một bản ghi được phép thiếu | Kết quả tra cứu không có | `Optional` hoặc kết quả “not found” có cấu trúc |
| I/O không đọc được nguồn | `Files.lines` không mở được file | Checked `IOException` ở ranh giới tạo nguồn |
| I/O trong quá trình duyệt | Lỗi khi đọc dòng sau lúc mở | Có thể xuất hiện unchecked `UncheckedIOException` trong pipeline |
| Lỗi parse logic | Parser ném `IllegalStateException` do bug | Không biến mặc định thành lỗi nhập liệu |
| Lỗi trong `close()` | Reader đóng thất bại | Xem ngoại lệ lúc đóng và suppressed |
| Lỗi side effect | API ghi dữ liệu giữa `forEach` | Cân nhắc giao dịch, idempotency và hậu quả một phần |

Một API chung `processAll` không nên che tất cả các trường hợp thành `List.empty()` hoặc `null`. Phải cho caller biết **điều kiện trả kết quả thành công là gì**.

## 11. Stream và nguồn tài nguyên: `Files.lines` cần đóng đúng phạm vi

Khác với `List.stream()`, một số stream có nguồn I/O cần được đóng. Ví dụ:

```java
static List<String> readNonBlankLines(
        java.nio.file.Path path)
        throws java.io.IOException {

    try (java.util.stream.Stream<String> lines =
                 java.nio.file.Files.lines(path)) {

        return lines.filter(line -> !line.isBlank())
                .toList();
    }
}
```

Đây là **phương thức Java minh họa hợp lệ khi đặt trong lớp**. `Files.lines(path)` tạo stream có tài nguyên file cần đóng; `try-with-resources` bảo đảm đóng khi rời phạm vi, kể cả khi `toList()` ném ngoại lệ.

Các điểm cần phân biệt:

1. **Mở nguồn**: lời gọi `Files.lines(path)` có thể ném checked `IOException` ngay khi mở.
2. **Đọc trong lúc duyệt**: lỗi I/O xảy ra sau khi mở có thể được bọc vào `UncheckedIOException` khi stream thực hiện terminal operation, tùy hợp đồng của API.
3. **Đóng**: `Stream.close()` chạy do `try-with-resources`; `close` có thể có hành vi lỗi riêng theo nguồn.
4. **Kết quả sau khi đóng**: `List<String>` do `toList()` tạo ra là dữ liệu đã được vật hóa, không còn phụ thuộc vào việc tiếp tục đọc stream.
5. **Không trả stream sống ra ngoài phạm vi vừa đóng**: caller không thể kỳ vọng duyệt nguồn I/O đã hết vòng đời.

### Anti-pattern: trả một stream đã đóng

```java
// Cố ý là thiết kế SAI, dù có thể biên dịch.
static java.util.stream.Stream<String> broken(
        java.nio.file.Path path)
        throws java.io.IOException {

    try (var lines = java.nio.file.Files.lines(path)) {
        return lines;
    }
}
```

Khi phương thức `broken` trả về, `try-with-resources` đã gọi `close()` trên stream. Caller nhận một đối tượng stream **đã đóng**; duyệt hoặc liên kết thêm thao tác có thể thất bại, không thể dùng để đọc file như kỳ vọng.

Hai lựa chọn đúng:

- **Vật hóa kết quả bên trong vùng sở hữu tài nguyên**, như `readNonBlankLines` trả `List<String>`.
- **Chuyển giao ownership một cách tường minh** bằng API trả `Stream<String>` và yêu cầu caller đóng bằng `try-with-resources`, đồng thời tài liệu hóa rõ trách nhiệm và thời điểm lỗi.

Nếu API được thiết kế để trả stream sống, bản thân phương thức trả stream **không được tự đóng** trước khi caller sử dụng.

## 12. Mối liên hệ giữa checked exception và `try-with-resources` trong stream

Ngay cả khi xử lý phần tử không ném checked exception, quá trình mở/đóng nguồn có thể có lỗi.

Ví dụ:

```java
static long count(java.nio.file.Path path)
        throws java.io.IOException {

    try (var lines = java.nio.file.Files.lines(path)) {
        return lines.count();
    }
}
```

Phương thức khai báo `throws IOException` cho lỗi mở nguồn. Trong quá trình duyệt, các lỗi từ nguồn có thể xuất hiện dưới dạng `UncheckedIOException`. Nếu gặp cả lỗi xử lý chính và lỗi lúc đóng, cơ chế `try-with-resources` có thể ghi lỗi đóng dưới dạng suppressed exception của lỗi chính theo luật tương ứng.

Không nên tuyên bố rằng mọi lỗi I/O khi dùng `Files.lines` sẽ tự biến thành checked `IOException` có thể bắt ngoài pipeline. Hãy đọc hợp đồng từng API: checked ở biên mở nguồn, unchecked khi stream xử lý dữ liệu, và lỗi đóng là những chặng cần phân biệt.

### Stream bình thường có cần `try-with-resources` không?

`List.of("a","b").stream()` thường không nắm tài nguyên phải đóng, vì nguồn dữ liệu nằm trong bộ nhớ. Không cần bọc mọi stream bằng `try-with-resources` cho đúng “phong cách”.

Với `Files.lines`, `BufferedReader.lines` hoặc API tạo stream từ kết nối/nguồn bên ngoài, phải đọc rõ **ai sở hữu nguồn, có cần đóng hay không, và đóng stream có đóng luôn nguồn không**. Ví dụ `BufferedReader.lines()` không thay thế trách nhiệm đóng chính `BufferedReader`: có thể viết `try (BufferedReader reader = ...)` rồi dùng `reader.lines()` trong vùng đó.

## 13. Một chương trình nhỏ quan sát `Stream.close()` khi pipeline lỗi

Mã sau minh họa tác dụng của `try-with-resources` với close handler ngay cả khi terminal operation ném unchecked exception. Đây **không phải ví dụ I/O file thật**; chỉ dùng `onClose` để thấy thứ tự.

Lưu tệp **`StreamCloseDemo.java`**:

```java
import java.util.stream.Stream;

public class StreamCloseDemo {

    public static void main(String[] args) {
        try (Stream<String> values =
                     Stream.of("1", "bad", "3")
                             .onClose(
                                     () -> System.out.println("stream closed"))) {

            values.map(Integer::parseInt)
                    .forEach(number ->
                            System.out.println("value=" + number));

        } catch (NumberFormatException ex) {
            System.out.println(
                    "caught=" + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StreamCloseDemo.java
java StreamCloseDemo
```

**Stdout chính xác:**

```text
value=1
stream closed
caught=NumberFormatException
```

**Giải thích:** `forEach` gặp `"1"`, in `value=1`; tới `"bad"`, `Integer.parseInt` ném `NumberFormatException`. Trong quá trình rời `try-with-resources`, `values.close()` được gọi và handler `onClose` in `stream closed`. Sau đó `catch` bắt lỗi parse.

Không nên kết luận từ ví dụ rằng mọi stream tự đóng ngay sau khi terminal operation chạy. **`Stream` không tự động gọi `close()` chỉ vì đã gọi `toList()` hoặc `forEach()`**. Việc đóng xảy ra vì cấu trúc `try-with-resources`.

## 14. Lỗi khi đóng nguồn và suppressed exceptions

Nếu một pipeline bị lỗi và `close()` của nguồn cũng ném exception, cần phân biệt hai sự kiện:

- **Ngoại lệ chính**: xuất hiện khi xử lý phần tử hoặc đọc nguồn.
- **Ngoại lệ dọn dẹp**: xuất hiện khi đóng nguồn/stream.

Với `try-with-resources`, nếu phần thân đã có ngoại lệ chính và `close()` ném thêm lỗi, Java thông thường **giữ lỗi chính** và ghi lỗi đóng vào `getSuppressed()`. Nếu phần thân chuẩn bị `return` mà `close()` ném lỗi, lời gọi có thể **ném lỗi đóng thay vì trả kết quả**.

Ví dụ dạng khung:

```java
try (SomeAutoCloseable resource = openResource()) {
    return process(resource);
}
```

Đây là **mã minh họa**, cần các kiểu/hàm được định nghĩa phù hợp. Không giả định `process` thành công chỉ vì đã tính ra một giá trị trước khi đóng.

Khi điều tra thất bại của pipeline I/O, hãy xem **cause chain và suppressed ở mọi tầng** thay vì chỉ in `getMessage()` của wrapper ngoài.

## 15. Exception và thứ tự trên sequential/parallel stream

Với **sequential stream** trên một `List` có thứ tự gặp (*encounter order*), các ví dụ phía trên cho kết quả theo đường duyệt dễ quan sát.

Với **parallel stream**:

```java
items.parallelStream()
        .map(this::convert)
        .toList();
```

đây là mã minh họa, `items` và `convert` phải được định nghĩa trong ngữ cảnh phù hợp.

Các nguy cơ bổ sung:

- Nhiều phần tử có thể được xử lý **đồng thời trên các thread khác nhau**.
- Nếu nhiều lambda cùng thất bại, **không nên mặc định lỗi “đầu tiên trong danh sách” sẽ là exception được báo đầu tiên**.
- Một số công việc đã bắt đầu có thể vẫn tạo side effect trước khi pipeline hoàn tất bất thường.
- Thứ tự side effect/log từ `forEach` có thể không phản ánh encounter order.
- Những biến trạng thái dùng chung không đồng bộ gây race condition.
- **“Fail-fast” trong nghĩa dừng tạo kết quả khi gặp lỗi không phải bảo đảm dừng ngay mọi tác vụ đang chạy đồng thời.**

Nếu chính sách cần nhận diện chắc chắn **mọi lỗi của tất cả phần tử**, không nên chỉ dựa vào một exception thoát khỏi `parallelStream().map(...).toList()`. Một dạng kết quả trên từng phần tử, không có side effect ngoài cần thiết, có thể phù hợp hơn.

### `forEachOrdered` có giải quyết mọi thứ không?

`forEachOrdered` yêu cầu tôn trọng encounter order cho tác dụng của chính terminal operation trên ordered stream, nhưng không biến toàn bộ pipeline parallel thành xử lý tuần tự không side effect. Không nên dùng nó như cách giải quyết hoàn chỉnh cho rủi ro shared mutable state hoặc nhiều lỗi đồng thời.

Muốn audit đáng tin, hãy ưu tiên **dữ liệu kết quả có cấu trúc**, quy tắc tổng hợp rõ ràng và xử lý transaction ở tầng nghiệp vụ.

## 16. Side effects và giao dịch: không nhầm stream với transaction

Stream rất phù hợp để **biến đổi dữ liệu thuần** (*pure transformation*). Nhưng nhiều pipeline thực tế có thao tác ghi:

```java
orders.stream()
        .map(this::chargeCustomer)
        .toList();
```

Đây là **mã minh họa**, `chargeCustomer` giả định có side effect thanh toán. Nếu đơn thứ ba thất bại, hai đơn đầu **có thể đã bị charge**. Việc `toList()` ném ngoại lệ không tự hoàn tác tác động bên ngoài.

Đây là vấn đề về **transaction và idempotency**, không chỉ là cú pháp Stream.

Những nguyên tắc hữu ích:

1. **Validate trước khi tạo side effect** nếu có thể.
2. **Phân biệt hai giai đoạn**: parse/validate dữ liệu, sau đó thực hiện nghiệp vụ với chính sách transaction rõ ràng.
3. Nếu phải ghi từng phần tử, xác định **partial success có được phép không** và ghi nhận kết quả.
4. Nếu cần all-or-nothing, sử dụng transaction hoặc chiến lược bù trừ phù hợp với hệ thống đích.
5. Không giả định một checked exception đã được bọc thành unchecked có thể tự rollback hệ thống bên ngoài.
6. Tránh đưa I/O blocking hoặc thao tác dài vào `parallelStream` một cách tùy tiện khi chưa đánh giá concurrency/throughput.

Một API stream trả `List` không tự thay thế thiết kế tính nhất quán của domain.

## 17. Các kiểu fallback: loại nào phù hợp?

Một chiến lược:

```java
.map(raw -> {
    try {
        return riskyTransform(raw);
    } catch (SomeCheckedException ex) {
        return defaultValue;
    }
})
```

Đây là khung minh họa, chỉ hợp lệ nếu `riskyTransform`, `SomeCheckedException` và `defaultValue` được định nghĩa phù hợp. Nó có thể tốt nếu **fallback là một kết quả được cho phép**, nhưng có thể cực kỳ nguy hiểm nếu:

- `defaultValue` trùng một giá trị hợp lệ nên caller không phân biệt được lỗi.
- Lỗi thực tế là hạ tầng đang xuống cấp.
- Cần retry hoặc báo cảnh báo nhưng exception đã bị bỏ.
- Trách nhiệm xử lý lỗi thuộc tầng ngoài, không thuộc mapper.
- Việc tiếp tục tạo side effect trên các phần tử còn lại làm trạng thái khó khôi phục.

Do đó, hãy mô tả hợp đồng rõ:

| Chính sách | Khi hợp lý | Điều caller cần biết |
| --- | --- | --- |
| **Fail-fast** | Tác vụ chỉ hợp lệ khi mọi phần tử đều đúng; lỗi là ngoại lệ của toàn pipeline | Exception loại gì, có mã/ID/cause nào |
| **Collect failures** | Import hàng loạt, validation muốn thông báo nhiều lỗi | Kiểu `Outcome`, mã lỗi, danh sách kết quả |
| **Skip invalid** | Bài toán chấp nhận loại bỏ một số dữ liệu | Tiêu chí skip, số lượng bị loại, khả năng audit |
| **Fallback** | Có giá trị mặc định nghiệp vụ rõ ràng | Điều kiện dùng fallback và tính phân biệt |
| **Retry** | Lỗi tạm thời, thao tác idempotent/được kiểm soát | Số lần, delay, phân loại lỗi retryable |
| **Abort before side effect** | Muốn nhất quán tác vụ | Giai đoạn validate và commit tách rời |

Không nên để mapper tự quyết định một chính sách mơ hồ bằng `catch (Exception) { return null; }`.

## 18. Bảo toàn thông tin lỗi thay vì chỉ có message

Một nguyên tắc quen thuộc trong Java exceptions: **message dành cho người đọc; dữ liệu có cấu trúc dành cho chương trình**.

Với lỗi trên phần tử, một exception hoặc result có thể mang:

- `itemId` hoặc số dòng an toàn.
- Mã lỗi ổn định như `INVALID_INTEGER` hoặc `MISSING_FIELD`.
- Ngữ cảnh nghiệp vụ cần thiết, chẳng hạn tên trường.
- `cause` là đối tượng lỗi gốc khi có nguyên nhân kỹ thuật.
- Thông điệp chẩn đoán không chứa secret.
- Với lỗi cleanup, `getSuppressed()` trên Throwable thích hợp.

Đừng viết logic:

```java
if (ex.getMessage().contains("bad integer")) {
    // Phân nhánh nghiệp vụ.
}
```

Bởi message có thể thay đổi do dịch thuật, version hoặc làm rõ nội dung. Trong ví dụ fail-fast, caller dùng `InvalidItemException.getItemId()` và loại exception. Trong ví dụ collect, caller dùng `ErrorCode` của `Failure`.

### Đừng mất cause khi bọc ngoại lệ

Mã:

```java
throw new IllegalStateException(
        "conversion failed", original);
```

giữ nguyên `original` qua constructor nhận cause, nếu biến đó tồn tại và đúng kiểu.

Mã:

```java
throw new IllegalStateException(
        "conversion failed: " + original.getMessage());
```

không tự giữ cause; stack trace và suppressed thuộc ngoại lệ cũ sẽ không được nối vào lỗi mới chỉ vì message bị copy. Hãy bọc có nguyên nhân khi thật sự chuyển hợp đồng.

## 19. Không dùng unchecked exception để che lỗi thiết kế

Một adapter như:

```java
catch (Exception ex) {
    throw new RuntimeException(ex);
}
```

có thể giúp code vượt compiler, nhưng nếu không hiểu ngữ nghĩa thì nó chỉ làm ẩn một checked contract. Các câu hỏi cần trả lời:

- Caller của stream có biết **khi nào pipeline thất bại**?
- Loại wrapper có đủ ý nghĩa hay chỉ là `RuntimeException` chung chung?
- Cause còn nguyên không?
- Có cần xử lý lỗi tại từng phần tử thay vì ném?
- Mapper có chạy lặp hoặc chạy trên thread khác không?
- Có một ranh giới API nào phù hợp hơn để dùng vòng lặp `for` truyền checked exception trực tiếp?

Đôi khi giải pháp tốt nhất đơn giản là **không dùng stream**:

```java
static List<String> loadAll(List<String> ids)
        throws java.io.IOException {

    List<String> values = new java.util.ArrayList<>();

    for (String id : ids) {
        values.add(load(id));
    }

    return values;
}
```

Đây là **phương thức minh họa**, `load(String) throws IOException` được định nghĩa trong cùng phạm vi. Với vòng lặp, `throws IOException` của `loadAll` trực tiếp mô tả lỗi checked, không cần adapter unchecked. Nếu mục tiêu là giữ đúng loại checked exception tới caller, một vòng lặp rõ ràng đôi khi đơn giản hơn cố ép vào `Function`.

**Không có yêu cầu phải dùng Stream bằng mọi giá.** Chọn công cụ diễn đạt rõ nhất hợp đồng kết quả, lỗi và tác động phụ.

## 20. Kiểm thử ba tầng: compile time, hành vi pipeline, hợp đồng kết quả

Một bộ kiểm thử tốt không chỉ xác minh danh sách cuối cùng.

### A. Quy tắc compile-time

Kiểm thử biên dịch hoặc ví dụ nhỏ để xác nhận:

- Lambda ném checked exception trực tiếp **không** gán được vào `Function` không khai báo `throws`.
- Functional interface custom có `throws E` cho phép checked exception tương thích.
- Adapter chuyển sang `Function` có chính sách rõ và có thể được dùng với `Stream.map`.

### B. Fail-fast và cause

Kiểm tra:

- Dữ liệu hợp lệ tạo ra `List` đúng.
- Dữ liệu lỗi khiến terminal operation không trả danh sách thành công giả.
- Exception ngoài có loại/ID/mã lỗi đúng hợp đồng.
- `getCause()` giữ đối tượng nguyên nhân phù hợp.
- Khi xử lý sequential ordered stream theo logic fail-fast, phần tử sau điểm lỗi không bị xử lý tiếp như trường hợp minh họa.

Không nên kiểm thử bằng chuỗi đầy đủ của `printStackTrace()` vì tên file, số dòng và frames có thể thay đổi.

### C. Collect-all

Kiểm tra:

- Một `Failure` **không ngắt pipeline** nếu parser chuyển lỗi validation thành dữ liệu.
- Tổng số `Success + Failure` bằng tổng số đầu vào khi chính sách là một kết quả cho mỗi phần tử.
- Các mã lỗi và ID có cấu trúc được bảo toàn.
- Một lỗi hạ tầng chưa được xử lý vẫn thất bại đúng nghĩa, không lặng lẽ hóa thành `Failure` validation.
- Có tiêu chí rõ để quyết định commit hay rollback dựa trên danh sách kết quả.

### D. Resource và terminal operation

Với `Files.lines` hoặc nguồn có `close`:

- Resource được đóng trên đường thành công.
- Resource cũng được đóng khi terminal operation ném ngoại lệ.
- Caller không dùng stream sau khi chủ sở hữu đã đóng.
- Nếu close ném, lỗi phụ/primary được giữ và xử lý đúng.

## 21. Lỗi thường gặp khi kết hợp Stream và thao tác thất bại

| Lỗi hoặc hiểu lầm | Hậu quả | Cách đúng hơn |
| --- | --- | --- |
| Gọi hàm `throws IOException` trực tiếp trong `map` | Không biên dịch nếu checked exception thoát khỏi `Function.apply` | Catch/wrap, custom interface + adapter hoặc dùng vòng lặp |
| Thêm `throws IOException` ở method ngoài rồi tưởng lambda hợp lệ | Không thay đổi hợp đồng `Function` | Xử lý ngay ở descriptor boundary |
| Bắt mọi `Exception` rồi trả `null` | Mất lý do lỗi, dễ thiếu dữ liệu | Kết quả có cấu trúc hoặc fail-fast |
| `filter(Objects::nonNull)` sau parse lỗi trả null | Im lặng bỏ phần tử | Chỉ skip nếu hợp đồng cho phép và có audit |
| Chỉ log `ex.getMessage()` | Mất stack, cause và suppressed | Giữ Throwable và log đúng ranh giới |
| Nghĩ xây pipeline là đã xử lý xong | Lỗi xuất hiện lúc terminal operation | Đặt handler ở nơi thực thi |
| Dùng `findFirst` để kết luận toàn bộ nguồn hợp lệ | Short-circuit không duyệt tất cả | Chọn validation duyệt toàn bộ dữ liệu |
| Nghĩ `toList()` tự đóng nguồn file | Stream terminal không tự gọi close | Dùng try-with-resources cho nguồn cần đóng |
| Trả `Stream` từ `try-with-resources` đã đóng | Caller nhận stream không còn dùng được | Vật hóa trong scope hoặc chuyển giao ownership |
| Dùng lại một stream đã tiêu thụ | `IllegalStateException` hoặc hành vi không hợp lệ | Tạo stream mới từ nguồn phù hợp |
| Dùng `parallelStream` rồi mong lỗi đầu tiên theo thứ tự | Nondeterminism và tác vụ có thể đã chạy | Thiết kế lỗi và side effect rõ ràng |
| Dùng `forEach` để ghi database rồi tưởng lỗi sẽ rollback | Stream không phải transaction | Transaction/idempotency/bù trừ |
| Bắt `Throwable` và đổi thành `Failure` | Có thể che `Error` nghiêm trọng | Chỉ bắt lỗi đã được chính sách cho phép |
| Trộn lỗi hạ tầng và lỗi validation cùng một mã | Caller retry/hiển thị sai | Phân loại theo domain và source |
| Chỉ có `Optional.empty()` cho mọi lý do lỗi | Mất mã lỗi và ngữ cảnh | Dùng Outcome/Result khi cần |
| So chuỗi `getMessage()` để quyết định | Dễ hỏng khi đổi ngôn ngữ/câu chữ | Dùng type, code và field |

## 22. Bài tập tự kiểm tra

**Bài A — Vì sao không biên dịch?**

```java
// load(String) throws IOException.
List<String> loaded = ids.stream()
        .map(id -> load(id))
        .toList();
```

**Đáp án:** `map` nhận `Function.apply` không khai báo checked `IOException`. Cần bắt/chuyển lỗi trong lambda, adapter có hợp đồng, hoặc phương án xử lý khác.

**Bài B — Thêm `throws` ngoài có giải quyết không?**

Phương thức chứa `map` thêm `throws IOException`. Có đủ không?

**Không.** Lambda vẫn phải tuân thủ function descriptor của `Function`. Hợp đồng của phương thức bao ngoài không thay đổi descriptor này.

**Bài C — Pipeline lỗi ở đâu?**

`var p = Stream.of("1","x").map(Integer::parseInt);`. Lúc tạo `p` có nhất thiết ném `NumberFormatException` không?

**Không.** `map` là intermediate operation. Lỗi thường xuất hiện khi terminal operation yêu cầu phần tử `"x"` được parse.

**Bài D — `findFirst` có xác thực mọi phần tử không?**

`Stream.of("1","bad").map(Integer::parseInt).findFirst()` có thể trả `1` mà không gặp lỗi không?

**Có.** `findFirst` short-circuit trên stream tuần tự có thứ tự gặp, không yêu cầu duyệt mọi phần tử.

**Bài E — Bỏ phần tử sai**

Parser trả `null` khi lỗi và pipeline `filter(Objects::nonNull)`. Caller có biết chắc phần tử nào bị bỏ không?

**Không**, nếu không có cơ chế báo cáo riêng. Điều đó chỉ đúng khi hợp đồng công khai cho phép bỏ và có cách quan sát đủ.

**Bài F — Mọi lỗi đều phải throw?**

Nếu import nhiều dòng và giao diện cần hiển thị tất cả lỗi validation, có thể trả `Failure` cho từng dòng thay vì ném fail-fast không?

**Có.** `Success/Failure` có cấu trúc là lựa chọn phù hợp; cần quyết định việc commit dữ liệu ở tầng ngoài.

**Bài G — Resource của `Files.lines`**

`Files.lines(path)` có cần quan tâm `close()` không?

**Có.** Stream này có thể giữ file mở. Khi phạm vi hiện tại sở hữu nó, dùng `try-with-resources` hoặc chuyển giao trách nhiệm đóng tường minh.

**Bài H — Thực thi song song**

Một `parallelStream` có ba mapper đồng thời lỗi. Có bảo đảm nhận lỗi của phần tử đầu danh sách trước không?

**Không.** Không nên dựa vào thứ tự xuất hiện lỗi hoặc giả định mọi tác vụ khác đã dừng ngay.

**Bài I — `Stream` tự rollback?**

Mapper đã ghi hai bản ghi vào DB rồi bản ghi thứ ba lỗi. `toList()` ném exception có tự rollback hai bản ghi đầu không?

**Không.** Stream không cung cấp transaction. Cần chính sách transaction, idempotency hoặc bù trừ thích hợp.

**Bài J — Bọc checked sang unchecked**

Một adapter ném `new RuntimeException(cause.getMessage())`. Hậu quả?

**Không giữ `cause`** nếu chỉ truyền message. Nên dùng constructor nhận đối tượng `cause`, kèm ngữ cảnh có ý nghĩa.

**Bài K — Đếm mọi lỗi**

Trong chương trình `StreamResultsDemo`, vì sao có thể đếm `successes=2` và `failures=2` dù hai dòng dữ liệu sai?

Vì parser chuyển hai lỗi validation dự kiến thành **đối tượng `Failure`**, không ném exception làm ngắt pipeline, nên `toList()` hoàn tất với bốn kết quả.

**Bài L — Một stream dùng hai lần**

Sau `List<Outcome> r = s.toList()`, có nên gọi `s.count()` trên cùng biến `s` không?

**Không.** Stream đã được tiêu thụ. Có thể duyệt danh sách `r` bằng stream mới, hoặc tạo pipeline mới từ nguồn còn hợp lệ.

## 23. Checklist ra quyết định trước khi dùng Stream với thao tác có thể thất bại

Trước khi viết pipeline, hãy trả lời:

1. **Hàm mapper có checked `throws` không?** Nếu có, `Function` của `map` không cho loại đó tự thoát.
2. **Chính sách của cả tác vụ là gì?** Fail-fast, collect-all, skip hay fallback?
3. **Caller cần nhìn thấy lỗi dưới dạng gì?** Exception có kiểu/code/cause, hoặc `Outcome` cho từng phần tử?
4. **Thông tin phần tử lỗi có giữ được không?** ID, số dòng, tên trường hoặc mã lỗi, không parse message.
5. **Có đang bỏ mất cause không?** Wrapper phải giữ đối tượng lỗi gốc khi hợp lý.
6. **Pipeline chạy khi nào?** Lỗi trong intermediate operation có thể xuất hiện khi terminal được gọi, thậm chí ở tầng khác.
7. **Có short-circuit không?** `findFirst`, `anyMatch` không chứng minh mọi phần tử đã được kiểm tra.
8. **Nguồn có tài nguyên cần đóng không?** Với `Files.lines`, xác định quyền sở hữu và vị trí `try-with-resources`.
9. **Có trả stream lười ra ngoài API không?** Nếu có, ai tiêu thụ và ai đóng, và khi nào lỗi được báo?
10. **Có side effect không?** Ghi file, DB, network hoặc thanh toán cần chính sách tính nhất quán tách khỏi Stream.
11. **Có parallelism không?** Không giả định thứ tự lỗi, thứ tự side effect hoặc việc dừng mọi công việc ngay.
12. **Có thể phân loại lỗi kỳ vọng và lỗi hạ tầng không?** Tránh biến mọi exception thành `Failure` validation.
13. **Có kiểm thử đường lỗi và đóng nguồn không?** Kiểm tra cause, suppressed, output và khả năng quan sát thất bại.
14. **Một vòng lặp `for` có rõ ràng hơn không?** Nếu mục tiêu chính là truyền checked exception tới caller, đừng ép pipeline chỉ vì cú pháp ngắn.

## Kết luận

Kết hợp `Stream` với thao tác có thể thất bại đòi hỏi **hợp đồng xử lý lỗi tường minh**: `map`/`filter` dùng functional interfaces không khai báo checked exception, pipeline có tính lazy và terminal operation mới là nơi lỗi thường được quan sát. Khi một lỗi phải làm thất bại toàn tác vụ, có thể dùng **fail-fast** với exception đúng ngữ nghĩa và giữ `cause`. Khi cần xử lý mọi dòng rồi báo cáo, dùng **`Success/Failure` có cấu trúc**. Khi muốn bỏ qua hoặc fallback, phải chứng minh đó là hành vi được phép, không phải cách giấu lỗi.

Cuối cùng, **Stream không phải transaction và cũng không tự đóng mọi nguồn dữ liệu**. Hãy thiết kế ownership cho nguồn I/O, tránh side effect ngoài kiểm soát và không dựa vào thứ tự lỗi của pipeline song song. Hợp đồng rõ ràng giúp caller biết **thất bại xảy ra ở đâu, có tiếp tục được không, kết quả có đầy đủ không và phải xử lý tài nguyên ra sao**.