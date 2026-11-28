# Xử lý null, exception và hợp đồng dữ liệu phát ra

`Stream.mapMulti` cho phép mapper phát không, một hoặc nhiều phần tử đầu ra cho mỗi phần tử nguồn. Khi thiết kế mapper, cần xác định rõ dữ liệu null được xử lý thế nào, lỗi nào làm pipeline thất bại và các giá trị được phát phải tuân thủ những điều kiện gì.

`mapMulti` không tự lọc null, không tự chuyển exception thành phần tử lỗi và cũng không bảo đảm một nhóm kết quả được phát theo kiểu giao dịch. Mapper phải thực hiện đúng chính sách dữ liệu của ứng dụng và phát kết quả đồng bộ qua Consumer trong lần gọi hiện tại.

## 1. Null ở phần tử nguồn

Stream tham chiếu có thể chứa phần tử null nếu nguồn cho phép. Vì vậy, mapper có thể nhận null ở tham số phần tử nguồn.

Ví dụ, `Arrays.asList` cho phép chứa null:

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", null, "Binh");
```

Trước khi gọi phương thức trên phần tử nguồn, hãy xác định chính sách null. Có ba lựa chọn thường gặp:

- Bỏ qua phần tử null nếu nó có nghĩa là dữ liệu không có và nghiệp vụ cho phép bỏ qua.
- Từ chối dữ liệu bằng exception nếu null vi phạm hợp đồng đầu vào.
- Chuyển null thành một biểu diễn miền dữ liệu rõ ràng nếu nghiệp vụ cần giữ lại trạng thái thiếu dữ liệu.

Không nên vô tình gọi phương thức trên tham chiếu null rồi để `NullPointerException` xuất hiện ở một vị trí khó xác định.

## 2. Bỏ qua phần tử nguồn null một cách tường minh

Nếu null được xem là phần tử không có dữ liệu và có thể bỏ qua, kiểm tra trước khi xử lý:

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", null, "Binh");

List<String> normalized = names.stream()
    .<String>mapMulti((name, emit) -> {
        if (name == null) {
            return;
        }

        String value = name.trim();

        if (!value.isEmpty()) {
            emit.accept(value);
        }
    })
    .toList();
```

Mapper không phát kết quả cho phần tử null hoặc chuỗi rỗng. Các tên hợp lệ được chuẩn hóa rồi phát đồng bộ.

Trong mapper dạng block lambda, `return;` chỉ kết thúc lần gọi mapper hiện tại. Nó không kết thúc toàn bộ Stream và cũng không dừng xử lý các phần tử nguồn tiếp theo.

Nếu mục tiêu chỉ là bỏ qua null rồi biến đổi một giá trị thành một giá trị, có thể dùng `filter` và `map` để diễn đạt đơn giản hơn:

```java
List<String> normalized = names.stream()
    .filter(name -> name != null)
    .map(String::trim)
    .filter(name -> !name.isEmpty())
    .toList();
```

Dùng `mapMulti` khi ngoài việc bỏ qua phần tử, một phần tử nguồn còn có thể phát nhiều giá trị.

## 3. Từ chối null bằng fail-fast

Nếu null vi phạm hợp đồng đầu vào, nên báo lỗi ngay tại ranh giới xử lý:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> names = Arrays.asList("An", null, "Binh");

List<String> normalized = names.stream()
    .<String>mapMulti((name, emit) -> {
        Objects.requireNonNull(name, "name must not be null");
        emit.accept(name.trim());
    })
    .toList();
```

`Objects.requireNonNull` trả lại tham chiếu nếu nó khác null và ném `NullPointerException` nếu tham chiếu null. Dùng thông điệp phù hợp giúp xác định trường dữ liệu vi phạm.

Các factory như `List.of` từ chối null ngay khi tạo nguồn. Với nguồn đến từ API, file hoặc dữ liệu bên ngoài có thể chứa null, kiểm tra tại ranh giới tiếp nhận giúp phát hiện vi phạm sớm.

Fail-fast phù hợp khi tiếp tục xử lý dữ liệu thiếu có thể tạo kết quả sai hoặc che giấu lỗi dữ liệu. Nếu cần báo lỗi nghiệp vụ cụ thể hơn, có thể ném một exception không kiểm tra riêng của ứng dụng.

## 4. Null được phát ra khác với không phát kết quả

Với Stream tham chiếu, `emit.accept(null)` là một lần phát phần tử có giá trị null. Nó không tương đương với việc không gọi `emit.accept`.

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", "B")
    .<String>mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(null);
    })
    .toList();
```

Mỗi phần tử nguồn phát hai phần tử: giá trị ban đầu và một tham chiếu null. Kết quả của `Stream.toList()` có thể chứa null.

Điều này có thể gây lỗi ở các bước sau nếu chúng không chấp nhận null. Ví dụ:

- `value.length()` ném `NullPointerException` khi value là null.
- `findFirst()` ném `NullPointerException` nếu phần tử được chọn là null vì `Optional` không biểu diễn một giá trị null.
- `List.of(...)` và `Collectors.toUnmodifiableList()` không chấp nhận phần tử null.

Nếu ý nghĩa của null là "không có kết quả", hãy không gọi Consumer. Nếu null là một trạng thái nghiệp vụ cần giữ, nên cân nhắc một kiểu kết quả tường minh như record chứa trạng thái hoặc `Optional` thay vì phát null không có ngữ nghĩa rõ ràng.


## 5. Dùng Optional để biểu diễn kết quả có thể không tồn tại

`Optional` giúp thể hiện rõ một phép biến đổi có thể không tạo ra giá trị. Mapper có thể phát phần tử khi Optional có giá trị và không phát gì khi Optional rỗng:

```java
import java.util.List;
import java.util.Optional;

List<String> inputs = List.of("  Java  ", "", " Stream ");

List<String> normalized = inputs.stream()
    .<String>mapMulti((input, emit) -> {
        Optional<String> result = Optional.of(input.trim())
            .filter(value -> !value.isEmpty());
        result.ifPresent(emit);
    })
    .toList();
```

Trong ví dụ, `Optional.filter` tạo `Optional.empty()` cho chuỗi rỗng và giữ giá trị cho chuỗi hợp lệ. `ifPresent(emit)` gọi Consumer đồng bộ khi có giá trị.

Nếu một phương thức trả về chính tham chiếu Optional null, đó là vi phạm hợp đồng của phương thức; cần xác thực bằng `Objects.requireNonNull` thay vì gọi `ifPresent` trên tham chiếu null.

Với quan hệ một đầu vào tạo tối đa một đầu ra, `flatMap` cùng Optional có thể diễn đạt tự nhiên hơn:

Giả sử `MyNormalizer.normalize(String)` trả về một `Optional<String>` không null:

```java
List<String> normalized = inputs.stream()
    .map(MyNormalizer::normalize)
    .flatMap(Optional::stream)
    .toList();
```

`Optional.stream()` có từ Java 9 và vẫn là API hiện hành. Dùng cách viết phù hợp với hình dạng phép biến đổi và khả năng đọc của pipeline.

## 6. Null với primitive output và unboxing

Các biến thể `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble` phát kiểu nguyên thủy thông qua `IntConsumer`, `LongConsumer` và `DoubleConsumer`. Primitive không thể chứa null.

Nếu nguồn là wrapper như `Integer` hoặc `Long`, việc truyền null vào primitive Consumer sẽ cần unboxing và gây `NullPointerException`.

Ví dụ không an toàn:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(10, null, 30);

int[] numbers = values.stream()
    .mapMultiToInt((value, emit) -> {
        emit.accept(value);
    })
    .toArray();
```

Khi mapper nhận phần tử null, Java không thể unbox nó thành `int` để gọi `accept(int)`.

Cách an toàn nếu null được phép bỏ qua:

Tiếp tục dùng danh sách `values` đã khai báo trong ví dụ ngay trên:

```java
int[] numbers = values.stream()
    .mapMultiToInt((value, emit) -> {
        if (value != null) {
            emit.accept(value);
        }
    })
    .toArray();
```

Nếu null vi phạm hợp đồng, hãy import `java.util.Objects` và dùng `Objects.requireNonNull(value, "...")` trước khi unbox để báo lỗi ngay tại điểm xác thực.

Primitive Stream như `IntStream`, `LongStream` và `DoubleStream` không chứa phần tử null. Null chỉ có thể xuất hiện ở nguồn tham chiếu trước khi chuyển sang primitive Stream hoặc ở một kiểu dữ liệu tham chiếu khác trong pipeline.

## 7. Xác định hợp đồng của dữ liệu được phát

Mapper nên có hợp đồng rõ ràng về hình dạng đầu ra. Với mỗi phần tử nguồn, hãy xác định:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Số lượng | Có thể phát 0, 1 hay nhiều phần tử? Có giới hạn tối đa không? |
| Null | Đầu ra có được phép null không? |
| Kiểu dữ liệu | Mọi giá trị phát ra có cùng kiểu và ý nghĩa không? |
| Miền giá trị | Có giới hạn min/max, định dạng hoặc đơn vị không? |
| Thứ tự | Thứ tự phát trong một nhóm có ý nghĩa không? |
| Trùng lặp | Các giá trị trùng có hợp lệ không? |
| Lỗi | Dữ liệu sai bị bỏ qua, chuyển thành lỗi dữ liệu hay làm pipeline thất bại? |

Ví dụ, một dòng đơn hàng có thể phát một sự kiện cho mỗi đơn vị hàng:

```java
import java.util.Objects;
import java.util.List;

record OrderLine(String sku, int quantity) {}

List<OrderLine> lines = List.of(
    new OrderLine("BOOK-01", 2),
    new OrderLine("PEN-02", 3)
);

List<String> unitIds = lines.stream()
    .<String>mapMulti((line, emit) -> {
        String sku = Objects.requireNonNull(line.sku(), "sku must not be null");

        if (line.quantity() < 0) {
            throw new IllegalArgumentException("quantity must be non-negative");
        }

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }

        for (int index = 0; index < line.quantity(); index++) {
            emit.accept(sku + "#" + (index + 1));
        }
    })
    .toList();
```

Hợp đồng của ví dụ:

- Số lượng âm là dữ liệu không hợp lệ và làm pipeline thất bại.
- Số lượng bằng không phát không phần tử.
- Số lượng dương phát đúng số lượng mã đơn vị.
- Mỗi mã được phát theo thứ tự chỉ số tăng dần.
- SKU không được null hoặc rỗng theo quy tắc dữ liệu của ứng dụng.

Nếu SKU có thể null, cần xác thực trước khi nối chuỗi. Không nên để chuỗi `"null#1"` trở thành dữ liệu hợp lệ ngoài ý muốn.


## 8. Kiểm tra dữ liệu trước khi phát

Khi một phần tử nguồn có thể tạo nhiều đầu ra, hãy kiểm tra các điều kiện cần thiết trước khi gọi Consumer. Điều này giúp tránh phát một phần kết quả rồi mới phát hiện phần dữ liệu còn lại không hợp lệ.

Ví dụ, mỗi batch chứa danh sách chuỗi số. Chính sách là toàn bộ batch phải hợp lệ mới được phát các số:

```java
import java.util.ArrayList;
import java.util.List;

record Batch(String id, List<String> tokens) {}

List<Batch> batches = List.of(
    new Batch("B-01", List.of("10", "20", "30")),
    new Batch("B-02", List.of("5", "invalid", "15"))
);

List<Integer> values = batches.stream()
    .<Integer>mapMulti((batch, emit) -> {
        List<Integer> parsed = new ArrayList<>();

        for (String token : batch.tokens()) {
            parsed.add(Integer.parseInt(token));
        }

        for (Integer value : parsed) {
            emit.accept(value);
        }
    })
    .toList();
```

`Integer.parseInt` ném `NumberFormatException` nếu token không phải số nguyên hợp lệ. Với batch lỗi, vòng lặp phân tích thất bại trước khi mapper phát bất kỳ giá trị nào của batch đó.

Cách này tạo một danh sách tạm cho từng batch. Đổi lại, nó tách rõ hai giai đoạn: xác thực toàn bộ dữ liệu của một phần tử nguồn, rồi mới phát kết quả. Những batch trước đó có thể đã được xử lý; Stream không cung cấp giao dịch rollback cho toàn bộ pipeline.

Nếu batch rất lớn, cân nhắc xác thực ở ranh giới nhập dữ liệu hoặc dùng một mô hình kết quả riêng để tránh giữ thêm toàn bộ danh sách tạm trong bộ nhớ.

## 9. Exception không kiểm tra được truyền ra khỏi mapper

Mapper của `mapMulti` có kiểu functional interface không khai báo checked exception. Những exception không kiểm tra như `IllegalArgumentException`, `NumberFormatException` hoặc `NullPointerException` có thể được ném trực tiếp.

Ví dụ, nếu một token không hợp lệ thì chọn chính sách fail-fast:

```java
import java.util.List;

List<String> tokens = List.of("10", "20", "not-a-number", "40");

int[] numbers = tokens.stream()
    .mapMultiToInt((token, emit) -> {
        int value = Integer.parseInt(token);
        emit.accept(value);
    })
    .toArray();
```

`Integer.parseInt` ném `NumberFormatException` khi gặp token sai. Terminal operation `toArray()` không hoàn tất bình thường và exception được truyền ra nơi gọi terminal operation.

Do Stream là lazy, mapper thường chỉ được thực thi khi terminal operation bắt đầu tiêu thụ pipeline. Vì vậy, lỗi dữ liệu có thể xuất hiện ở `toArray()`, `sum()` hoặc terminal operation khác chứ không nhất thiết ở dòng tạo Stream.

Không nên bắt mọi `RuntimeException` rồi bỏ qua. Việc đó có thể che giấu cả lỗi lập trình như null ngoài dự kiến, chỉ số sai hoặc vi phạm invariant.

## 10. Bỏ qua dữ liệu lỗi khi nghiệp vụ cho phép

Có những luồng nhập liệu mà một bản ghi sai không nên làm hỏng toàn bộ batch. Khi chính sách nghiệp vụ cho phép bỏ qua bản ghi sai định dạng, hãy bắt đúng loại exception tại phạm vi nhỏ:

```java
import java.util.List;

List<String> tokens = List.of("10", "20", "not-a-number", "40");

int[] validNumbers = tokens.stream()
    .mapMultiToInt((token, emit) -> {
        int parsed;
        try {
            parsed = Integer.parseInt(token);
        } catch (NumberFormatException ignored) {
            // Chính sách của ví dụ: bỏ qua token không phải số nguyên.
            return;
        }

        emit.accept(parsed);
    })
    .toArray();
```

Kết quả là `[10, 20, 40]`. Exception chỉ bị bắt cho lỗi chuyển chuỗi thành số nguyên. Những lỗi khác vẫn được truyền ra ngoài.

Không dùng cách bỏ qua này nếu dữ liệu lỗi phải được báo cho người gửi hoặc cần kiểm toán. Khi cần lưu cả thành công và thất bại, hãy phát một kiểu kết quả thể hiện rõ hai trạng thái thay vì âm thầm loại bỏ lỗi.

## 11. Giữ lại thông tin lỗi bằng kiểu kết quả rõ ràng

Nếu ứng dụng cần tiếp tục xử lý các bản ghi hợp lệ đồng thời giữ thông tin về bản ghi lỗi, hãy biểu diễn kết quả bằng một kiểu dữ liệu riêng:

```java
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;

record ParseResult(
    String input,
    OptionalInt value,
    Optional<String> error
) {}

List<String> tokens = List.of("10", "bad", "30");

List<ParseResult> results = tokens.stream()
    .mapMulti((token, emit) -> {
        ParseResult result;
        try {
            int value = Integer.parseInt(token);

            result = new ParseResult(
                token,
                OptionalInt.of(value),
                Optional.empty()
            );
        } catch (NumberFormatException exception) {
            result = new ParseResult(
                token,
                OptionalInt.empty(),
                Optional.of(exception.toString())
            );
        }

        emit.accept(result);
    })
    .toList();
```

Mỗi token tạo đúng một `ParseResult`. Kết quả hợp lệ có `OptionalInt.of(value)`; kết quả lỗi có giá trị rỗng và thông tin lỗi. Không dùng null để phân biệt hai trường hợp.

Nếu một token có thể không tạo ra bất kỳ kết quả nào theo nghiệp vụ, mapper có thể không phát. Nhưng khi cần báo lỗi, hãy giữ lỗi trong dữ liệu hoặc gửi tới cơ chế ghi nhận lỗi được thiết kế riêng, không trộn lỗi với việc bỏ qua.

## 12. Checked exception cần được chuyển đổi rõ ràng

Các functional interface mà Stream sử dụng như `BiConsumer` không khai báo checked exception. Vì vậy, mapper không thể trực tiếp ném một checked exception như `IOException` ra ngoài mà không xử lý.

Nếu một phương thức được gọi trong mapper có thể ném checked exception, có thể bắt và bọc nó trong unchecked exception phù hợp:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

record RawRecord(String content) {}

List<RawRecord> records = List.of(
    new RawRecord("record-1"),
    new RawRecord("record-2")
);

List<ParsedRecord> parsed = records.stream()
    .<ParsedRecord>mapMulti((record, emit) -> {
        try {
            emit.accept(parseRecord(record));
        } catch (IOException exception) {
            throw new UncheckedIOException(
                "Cannot parse record: " + record.content(),
                exception
            );
        }
    })
    .toList();
```

Trong ví dụ, `parseRecord` là phương thức ứng dụng có chữ ký ném `IOException` và `ParsedRecord` là kiểu kết quả đã định nghĩa. `UncheckedIOException` giữ exception gốc làm cause để tầng gọi có thể kiểm tra nguyên nhân.

Nếu công việc thực chất là đọc file hoặc gọi mạng, thường nên thực hiện I/O ở một tầng riêng có chính sách retry, timeout và xử lý lỗi rõ ràng. Không biến mapper của Stream thành nơi điều phối I/O bất đồng bộ hoặc side effect phức tạp.


## 13. Nếu mapper phát một phần rồi ném exception

`mapMulti` không cung cấp cơ chế transaction cho các lần gọi `accept`. Nếu mapper phát một hoặc nhiều giá trị rồi sau đó ném exception, pipeline có thể đã chuyển các giá trị trước đó tới những bước downstream.

Ví dụ:

```java
import java.util.List;

List<String> values = List.of("first", "second");

List<String> result = values.stream()
    .<String>mapMulti((value, emit) -> {
        emit.accept(value);

        if (value.equals("second")) {
            throw new IllegalStateException("invalid second value");
        }

        emit.accept(value.toUpperCase());
    })
    .toList();
```

Terminal operation thất bại và không trả về danh sách kết quả bình thường. Không có bảo đảm rollback cho những tác động phụ downstream đã xảy ra trước lúc exception được ném.

Điều này đặc biệt quan trọng nếu downstream có `forEach` ghi file, gửi message hoặc cập nhật hệ thống bên ngoài. Một phần tác động phụ có thể đã xảy ra trước khi lỗi làm pipeline thất bại.

Nếu cần bảo đảm tất cả giá trị của một phần tử nguồn hợp lệ trước khi phát, hãy xác thực và chuẩn bị kết quả trong biến cục bộ trước, rồi mới gọi Consumer. Nếu cần tính nguyên tử cho toàn bộ batch hoặc toàn bộ quy trình, hãy dùng transaction hoặc cơ chế commit phù hợp ở tầng nghiệp vụ; Stream không tự cung cấp transaction.

## 14. Không nuốt exception phát sinh từ downstream

Lời gọi `emit.accept(value)` chuyển giá trị vào phần còn lại của pipeline. Một thao tác downstream có thể ném exception khi xử lý giá trị đó.

Không nên bao toàn bộ mapper bằng một khối catch rộng rồi bỏ qua mọi lỗi:

Giả sử `stream`, `transform` và các kiểu liên quan đã được khai báo trong lớp ứng dụng:

```java
stream.mapMulti((input, emit) -> {
    try {
        emit.accept(transform(input));
    } catch (RuntimeException ignored) {
        // Không nên nuốt mọi lỗi ở đây.
    }
});
```

Khối catch có thể vô tình bắt cả exception do thao tác downstream ném ra thông qua lời gọi Consumer. Điều này che giấu lỗi ở giai đoạn sau và làm pipeline tiếp tục trong trạng thái khó dự đoán.

Hãy đặt try/catch quanh đúng thao tác có thể lỗi và có chính sách xử lý cụ thể:

Ví dụ sau cũng giả sử `stream`, `parse`, `Result` và `InvalidInputException` đã được khai báo:

```java
stream.mapMulti((input, emit) -> {
    Result result;

    try {
        result = parse(input);
    } catch (InvalidInputException exception) {
        return;
    }

    emit.accept(result);
});
```

Ở đây chỉ lỗi phân tích đầu vào được xử lý. Nếu downstream ném exception trong lúc `emit.accept` chạy, lỗi đó không bị khối catch bắt nhầm.

## 15. Exception trong parallel Stream

Với parallel Stream, nhiều mapper invocation có thể đang chạy khi một mapper ném exception. Terminal operation sẽ không hoàn tất bình thường, nhưng không nên giả định mọi tác vụ đang chạy lập tức bị hủy hoặc không có tác động phụ nào đã xảy ra.

Không dựa vào một thứ tự cố định để xác định mapper nào được chạy trước, exception nào xuất hiện trước hoặc bao nhiêu phần tử đã được xử lý. Những chi tiết đó có thể phụ thuộc cách pipeline được phân chia và thực thi.

Vì vậy, mapper chạy song song nên:

- Xác thực dữ liệu độc lập theo từng phần tử.
- Tránh cập nhật trạng thái mutable dùng chung.
- Không thực hiện side effect bên ngoài mà không có cơ chế idempotency hoặc transaction phù hợp.
- Không nuốt exception ngoài chính sách nghiệp vụ đã xác định.
- Không dựa vào việc tất cả phần tử sẽ được xử lý sau khi một lỗi xảy ra.

Nếu cần tổng hợp nhiều lỗi từ nhiều bản ghi, có thể chuyển từng bản ghi thành một kết quả thành công/thất bại rồi thu thập, sau đó xử lý danh sách lỗi ở một bước riêng.

## 16. Hợp đồng thứ tự, số lượng và trùng lặp

Mỗi lần gọi `emit.accept` phát một phần tử theo đúng thứ tự lệnh được thực thi trong mapper. Với nguồn có encounter order và pipeline giữ thứ tự, các phần tử đầu ra được kết hợp theo thứ tự nguồn và thứ tự phát trong từng mapper.

Tuy nhiên, mapper của parallel Stream không nhất thiết được gọi theo thứ tự nguồn. Nếu thứ tự nghiệp vụ quan trọng, hãy dựa vào encounter order của pipeline và terminal operation bảo toàn thứ tự, không dựa vào thời điểm mapper bắt đầu hoặc kết thúc.

Ngoài thứ tự, hãy xác định:

- Số lần phát tối đa từ một phần tử nguồn.
- Có cho phép phát giá trị trùng lặp hay không.
- Giá trị đầu ra có cần duy nhất theo khóa hay không.
- Các giá trị có cùng đơn vị, miền giá trị và quy tắc chuẩn hóa hay không.

`mapMulti` không tự loại bỏ giá trị trùng. Nếu cần duy nhất, dùng `distinct()` khi định nghĩa equality của kiểu đầu ra phù hợp, hoặc áp dụng quy tắc duy nhất theo khóa bằng collector hay logic miền dữ liệu.

## 17. Checklist xử lý null và exception

Trước khi hoàn tất mapper, hãy kiểm tra:

1. **Nguồn có thể null không?** Nếu có, quyết định bỏ qua, từ chối hay chuyển thành trạng thái dữ liệu rõ ràng.
2. **Đầu ra có được phép null không?** Nếu không, xác thực trước khi gọi Consumer.
3. **Đầu ra primitive có thể nhận wrapper null không?** Kiểm tra null trước khi unbox sang int, long hoặc double.
4. **Mapper có thể phát 0..n giá trị không?** Ghi rõ ý nghĩa của trường hợp không phát và giới hạn fan-out.
5. **Exception nào có thể xuất hiện?** Phân biệt lỗi dữ liệu dự kiến với lỗi lập trình và lỗi hệ thống.
6. **Chính sách khi một phần tử sai là gì?** Fail-fast, bỏ qua có chủ đích hay phát một kết quả lỗi tường minh.
7. **Có phát trước khi xác thực xong không?** Nếu cần tránh kết quả một phần cho từng đầu vào, hãy chuẩn bị và xác thực cục bộ trước khi phát.
8. **Có side effect downstream không?** Không giả định pipeline rollback khi exception xảy ra.
9. **Có chạy parallel không?** Không dựa vào thứ tự lỗi hoặc số mapper đã chạy.
10. **Có bắt exception quá rộng không?** Chỉ bắt loại lỗi mà ứng dụng thực sự có thể xử lý.

## 18. Lỗi thường gặp

**Gọi phương thức trên phần tử nguồn mà không kiểm tra null.** Mapper có thể nhận null nếu nguồn cho phép. Hãy xác định chính sách null trước khi xử lý.

**Nghĩ rằng không phát kết quả và phát null là như nhau.** Không gọi Consumer tạo ra zero output; gọi `accept(null)` tạo một phần tử null trong reference Stream.

**Đưa wrapper null vào primitive Consumer.** Unboxing null gây `NullPointerException`. Kiểm tra trước khi gọi `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer`.

**Bắt mọi RuntimeException rồi bỏ qua.** Điều này có thể che giấu lỗi lập trình và exception từ downstream. Chỉ bắt loại lỗi dữ liệu có chính sách xử lý cụ thể.

**Để checked exception thoát trực tiếp khỏi mapper.** Functional interface không khai báo checked exception. Hãy xử lý hoặc bọc bằng unchecked exception phù hợp như `UncheckedIOException`.

**Phát kết quả rồi mới kiểm tra phần dữ liệu còn lại.** Mapper có thể đã gửi một phần đầu ra trước khi gặp lỗi. Nếu cần xác thực toàn bộ nhóm, hãy chuẩn bị kết quả cục bộ trước khi phát.

**Giả định exception làm rollback pipeline.** Stream không cung cấp transaction. Side effect đã xảy ra trước lỗi không tự được hoàn tác.

**Âm thầm bỏ qua bản ghi lỗi khi nghiệp vụ cần kiểm toán.** Hãy phát một kiểu kết quả thể hiện thành công/thất bại hoặc ghi nhận lỗi qua cơ chế phù hợp.

**Giả định parallel Stream xử lý lỗi theo thứ tự nguồn.** Mapper có thể chạy đồng thời; không dựa vào thứ tự exception hoặc số phần tử đã xử lý.

## 19. Ghi nhớ

- Xác định rõ chính sách null ở cả đầu vào và đầu ra.
- Không phát kết quả khác với phát một phần tử null.
- Kiểm tra wrapper null trước khi unbox sang primitive Consumer.
- Dùng `Optional` hoặc kiểu kết quả rõ ràng khi cần biểu diễn dữ liệu có thể vắng mặt.
- Mapper có thể ném unchecked exception; lỗi thường xuất hiện khi terminal operation thực thi pipeline.
- Checked exception cần được xử lý hoặc chuyển thành unchecked exception có giữ nguyên cause.
- Chỉ bắt exception cụ thể mà ứng dụng có thể xử lý; tránh nuốt exception từ downstream.
- `mapMulti` không cung cấp rollback hoặc transaction cho các giá trị đã phát.
- Nếu cần xác thực toàn bộ nhóm trước khi phát, chuẩn bị kết quả cục bộ rồi mới gọi Consumer.
- Xác định rõ cardinality, nullability, miền giá trị, thứ tự và quy tắc trùng lặp của đầu ra.
- Với parallel Stream, không dựa vào thứ tự mapper hoặc thứ tự exception.

Một mapper `mapMulti` đáng tin cậy có chính sách null và exception rõ ràng, xác thực dữ liệu trước khi phát khi cần, đồng thời tuân thủ hợp đồng về số lượng, kiểu, thứ tự và miền giá trị đầu ra. Điều đó giúp pipeline dễ kiểm tra, tránh null ngoài ý muốn và xử lý lỗi theo đúng quy tắc nghiệp vụ.

