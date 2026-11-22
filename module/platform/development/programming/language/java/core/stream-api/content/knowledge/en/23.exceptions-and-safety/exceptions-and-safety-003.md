# Thiết kế kết quả thành công hoặc lỗi cho từng phần tử

> **Chương:** Ngoại lệ và tính an toàn  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện các giới hạn về trạng thái, tài nguyên và hiệu năng.

Một pipeline xử lý hàng nghìn dòng dữ liệu thường gặp cả **bản ghi hợp lệ** lẫn **bản ghi không hợp lệ**. Ví dụ, khi nhập dữ liệu đơn hàng, một dòng có thể chứa số lượng không phải số nguyên, đơn giá âm hoặc thiếu mã sản phẩm. Nếu lambda trong `map` ném ngoại lệ không được xử lý, terminal operation có thể kết thúc bằng lỗi trước khi ta có báo cáo đầy đủ. Nhưng nếu chỉ bắt ngoại lệ rồi trả `null` hoặc bỏ qua dòng hỏng, dữ liệu sai lại biến mất không có dấu vết.

Một cách thiết kế hữu ích là: **mỗi phần tử đầu vào tạo ra một kết quả có kiểu rõ ràng: thành công hoặc thất bại**. Sau khi xử lý, ta có thể thu thập cả hai nhóm, tiếp tục tổng hợp phần thành công và báo cáo lỗi theo từng dòng. Đây là mô hình *result as data*: lỗi dự kiến của dữ liệu được thể hiện bằng giá trị, trong khi lỗi lập trình hay sự cố hệ thống vẫn được xử lý bằng cơ chế ngoại lệ thích hợp.

Bài viết dùng **Java 17+**, với `sealed interface`, `record`, `Stream.map`, `filter`, `toList` và `BigDecimal`. Ví dụ độc lập có bộ kiểm tra cho dữ liệu hợp lệ, nhiều kiểu lỗi, nguồn rỗng, `null`, thứ tự và xử lý song song.

## 1. Vấn đề: một dòng hỏng có thể làm hỏng cả đợt xử lý

Giả sử file nhập có mỗi dòng theo định dạng đơn giản:

```text
SKU,quantity,unitPrice
```

Trong phạm vi ví dụ, mỗi dòng dữ liệu **không có dòng tiêu đề**, gồm đúng ba cột, không có dấu phẩy nằm bên trong một trường. Đây là định dạng nhỏ để học xử lý lỗi, **không phải parser CSV chuẩn** (CSV thật còn có dấu ngoặc kép, escape và nhiều quy tắc khác).

Nguồn mẫu:

| Dòng | Văn bản | Kết quả dự kiến |
| ---: | --- | --- |
| 1 | `PEN,2,12.50` | Thành công; thành tiền `25.00`. |
| 2 | `NOTE,0,9.99` | Lỗi: số lượng phải dương. |
| 3 | `BOOK,1,80.00` | Thành công; thành tiền `80.00`. |
| 4 | `PEN,abc,1.20` | Lỗi: số lượng không phải số nguyên. |
| 5 | `BAG,3,-10.00` | Lỗi: đơn giá âm. |
| 6 | `BAD` | Lỗi: không đủ ba cột. |
| 7 | `,5,4.00` | Lỗi: mã sản phẩm rỗng. |
| 8 | `RULER,3,2.00` | Thành công; thành tiền `6.00`. |

Kết quả nghiệp vụ cần nhận được:

```text
Tổng đầu vào:    8 dòng
Thành công:      3 dòng (1, 3, 8)
Thất bại:        5 dòng (2, 4, 5, 6, 7)
Tổng tiền đúng:  111.00
```

Tổng tiền chỉ tính trên dòng hợp lệ: `25.00 + 80.00 + 6.00 = 111.00`. Dòng không hợp lệ **không bị mất**; nó được đưa vào nhánh lỗi để sửa dữ liệu hoặc hiển thị cho người nhập.

### Ba cách làm và hệ quả

| Thiết kế | Khi gặp một dòng sai | Hạn chế |
| --- | --- | --- |
| `map(Integer::parseInt)` và để ngoại lệ thoát ra | Terminal operation thất bại nếu ngoại lệ không được xử lý. | Khó tạo báo cáo đầy đủ cho mọi dòng. |
| `try/catch` rồi trả `null` / `Optional.empty()` | Pipeline có thể tiếp tục. | Nếu chỉ giữ giá trị thành công, thường mất nguyên nhân và vị trí lỗi. |
| `map(line -> parse(line))` trả `Success` hoặc `Failure` | Mỗi dòng có kết quả tường minh; có thể tiếp tục xử lý. | Phải thiết kế kiểu dữ liệu và chính sách báo lỗi rõ ràng. |

Mô hình thứ ba phù hợp khi lỗi **đã dự đoán được ở cấp từng dòng** và yêu cầu là *thu thập lỗi, không dừng toàn bộ lô*. Nó **không có nghĩa mọi ngoại lệ trong chương trình đều nên bị biến thành dữ liệu**.

## 2. Phân biệt lỗi dữ liệu dự kiến và sự cố bất thường

Trước khi viết `Result`, hãy xác định **ranh giới trách nhiệm**.

### Lỗi dự kiến có thể trả về theo từng phần tử

- Thiếu cột hoặc sai cấu trúc của một dòng đầu vào.
- Số lượng không phải số nguyên, hoặc nhỏ hơn hoặc bằng 0.
- Giá trị đơn giá không phân tích được thành số thập phân.
- Mã sản phẩm rỗng hoặc không hợp lệ theo quy tắc nghiệp vụ.
- Một điều kiện nghiệp vụ rõ ràng không được đáp ứng.

Các tình huống này nên tạo một đối tượng lỗi có **mã lỗi, vị trí và mô tả an toàn**, để những dòng khác có thể tiếp tục được xử lý.

### Lỗi không nên bị nuốt trong một `catch (Exception)` chung

- `NullPointerException` do lập trình sai hoặc một invariant nội bộ bị vi phạm bất ngờ.
- `OutOfMemoryError`, lỗi tài nguyên nghiêm trọng hoặc lỗi hệ thống không thể khôi phục bằng việc bỏ một dòng.
- Lỗi kết nối đến dịch vụ dùng chung, hết quyền truy cập file hoặc cấu hình sai khiến **mọi dòng** đều không thể xử lý.
- Hủy tác vụ, ngắt luồng, timeout hoặc các vấn đề lifecycle khác cần được truyền tới tầng điều phối.

Với công việc có I/O, hãy phân biệt **lỗi dịch vụ cho một yêu cầu** (đôi khi có thể là `Failure` theo hợp đồng) với **sự cố hạ tầng** đòi hỏi retry, dừng lô hoặc báo lỗi cấp job. Khi bắt `InterruptedException` ở những API có thể ngắt, thông thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` và truyền trạng thái hủy theo chính sách của ứng dụng, không âm thầm chuyển thành một lỗi dữ liệu bình thường.

**Nguyên tắc:** chỉ chuyển sang `Failure` những lỗi đã được định nghĩa trong hợp đồng của thao tác đó; không dùng `catch (Throwable)` để giữ pipeline bằng mọi giá.

## 3. Mô hình hóa kết quả bằng `sealed interface` và `record`

Trong Java 17, `sealed interface` cho phép giới hạn những kiểu triển khai hợp lệ. Ta dùng hai kiểu:

```java
sealed interface RowOutcome permits Success, Failure {
    int lineNo();
}

record Success(int lineNo, Order order) implements RowOutcome {}

record Failure(
        int lineNo,
        ErrorCode code,
        String message
) implements RowOutcome {}
```

Với mỗi phần tử đầu vào, kết quả có thể là **`Success` hoặc `Failure`**, không phải một giá trị mơ hồ như `null`. `lineNo` xuất hiện ở cả hai nhánh, giúp ghép kết quả với vị trí ban đầu.

`ErrorCode` là một enum có giá trị ổn định:

```java
enum ErrorCode {
    EMPTY_RECORD,
    WRONG_COLUMN_COUNT,
    EMPTY_SKU,
    INVALID_QUANTITY,
    NON_POSITIVE_QUANTITY,
    INVALID_PRICE,
    NEGATIVE_PRICE
}
```

Tách `code` khỏi `message` giúp:

- Kiểm thử dựa trên **mã lỗi**, tránh phụ thuộc câu chữ mô tả.
- Phân loại lỗi thống kê, ví dụ bao nhiêu dòng bị sai số lượng.
- Thay đổi ngôn ngữ thông báo mà không phá logic.
- Không phải lưu nguyên văn dữ liệu nhạy cảm trong thông báo.

Mô hình kiểu này là một **domain-specific result** cho một bài toán nhập liệu. Trong thư viện tái sử dụng, có thể xây dựng kiểu tổng quát `Result<T, E>`, nhưng ở ví dụ học Stream, hai `record` cụ thể giúp trình bày rõ hơn.

### Khi nào chọn `Optional`?

`Optional<T>` diễn tả **có hoặc không có giá trị**, nhưng tự nó không nêu lý do vì sao không có. Nếu nghiệp vụ chỉ cần “có tìm thấy sản phẩm không?”, `Optional<Product>` là phù hợp. Nếu cần “dòng số 4 sai vì số lượng `abc`”, dùng kiểu lỗi có cấu trúc sẽ hữu ích hơn.

```text
Optional<Order>:
  present → có Order
  empty   → không có Order, không có mã lỗi

RowOutcome:
  Success → có Order và số dòng
  Failure → có số dòng, mã lỗi, thông báo
```

Không cần coi hai mô hình là đối thủ: một `Success` vẫn có thể chứa một trường `Optional` nếu **chính trường đó** thực sự tùy chọn theo nghiệp vụ.

## 4. Thiết kế hàm parse thuần: một đầu vào, một kết quả

Hàm `parseLine(lineNo, raw)` có trách nhiệm:

1. Kiểm tra dòng rỗng hoặc `null`.
2. Kiểm tra đúng ba cột.
3. Đọc và kiểm tra `sku`.
4. Phân tích `quantity`, trả lỗi tương ứng nếu sai hoặc không dương.
5. Phân tích `unitPrice` bằng `BigDecimal`, trả lỗi nếu sai hoặc âm.
6. Chỉ khi mọi điều kiện đều đạt mới tạo `Success`.

Sơ đồ:

```text
Input(lineNo, raw)
          │
          ▼
      parseLine
          │
          ├── thiếu/sai cột ───► Failure(lineNo, code, message)
          ├── SKU sai       ───► Failure(lineNo, code, message)
          ├── số lượng sai  ───► Failure(lineNo, code, message)
          ├── đơn giá sai   ───► Failure(lineNo, code, message)
          │
          └── hợp lệ ──────────► Success(lineNo, Order)
```

Với thiết kế này, hàm parse **không in log, không sửa danh sách nguồn, không cộng vào biến bên ngoài**. Tất cả thông tin cần thiết nằm trong tham số và giá trị trả về. Vì vậy, việc gọi nó từ một `map` ở Stream tuần tự hoặc song song không phụ thuộc vào trạng thái mutable dùng chung.

### Vì sao không để `NumberFormatException` lan ra?

`Integer.parseInt("abc")` và `new BigDecimal("x")` có thể ném `NumberFormatException`. Trong bài toán nhập liệu, đây là **lỗi dữ liệu dự kiến**. Ta bắt chính ngoại lệ này ở nơi chuyển đổi cụ thể và trả mã `INVALID_QUANTITY` hoặc `INVALID_PRICE`.

```java
try {
    int quantity = Integer.parseInt(rawQuantity);
    // Dùng quantity sau khi parse thành công.
} catch (NumberFormatException invalid) {
    return new Failure(
            lineNo,
            ErrorCode.INVALID_QUANTITY,
            "Số lượng phải là số nguyên");
}
```

Không cần `catch (RuntimeException)` quanh **toàn bộ pipeline**: cách làm đó dễ che giấu lỗi lập trình, và một `catch` rộng không đủ để xác định dòng nào gây ra vấn đề nếu không bảo toàn metadata đầu vào.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu chương trình sau vào `PerElementOutcomeDemo.java`. Nó gồm model bất biến, parser theo từng dòng, báo cáo chứa cả thành công lẫn lỗi, và các ca kiểm thử tự chạy trong `main`.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class PerElementOutcomeDemo {

    enum ErrorCode {
        EMPTY_RECORD,
        WRONG_COLUMN_COUNT,
        EMPTY_SKU,
        INVALID_QUANTITY,
        NON_POSITIVE_QUANTITY,
        INVALID_PRICE,
        NEGATIVE_PRICE
    }

    record Order(String sku, int quantity, BigDecimal unitPrice) {
        Order {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "Số lượng và đơn giá phải hợp lệ");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    sealed interface RowOutcome permits Success, Failure {
        int lineNo();
    }

    record Success(int lineNo, Order order) implements RowOutcome {
        Success {
            if (lineNo <= 0) {
                throw new IllegalArgumentException("Số dòng phải dương");
            }
            Objects.requireNonNull(order, "order");
        }
    }

    record Failure(
            int lineNo,
            ErrorCode code,
            String message
    ) implements RowOutcome {
        Failure {
            if (lineNo <= 0) {
                throw new IllegalArgumentException("Số dòng phải dương");
            }
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
        }
    }

    record BatchReport(
            List<RowOutcome> outcomes,
            List<Success> successes,
            List<Failure> failures,
            BigDecimal revenue
    ) {
        BatchReport {
            // Công bố bản sao không sửa được; không giữ List mutable
            // do phía gọi có thể thay đổi sau khi xây báo cáo.
            outcomes = List.copyOf(outcomes);
            successes = List.copyOf(successes);
            failures = List.copyOf(failures);
            Objects.requireNonNull(revenue, "revenue");
        }
    }

    static RowOutcome parseLine(int lineNo, String raw) {
        if (lineNo <= 0) {
            throw new IllegalArgumentException("lineNo phải dương");
        }
        if (raw == null || raw.isBlank()) {
            return new Failure(
                    lineNo,
                    ErrorCode.EMPTY_RECORD,
                    "Dòng nhập rỗng");
        }

        // -1 giữ cột rỗng ở cuối, giúp phân biệt thiếu dữ liệu.
        String[] fields = raw.split(",", -1);
        if (fields.length != 3) {
            return new Failure(
                    lineNo,
                    ErrorCode.WRONG_COLUMN_COUNT,
                    "Mỗi dòng cần đúng 3 cột");
        }

        String sku = fields[0].strip();
        if (sku.isEmpty()) {
            return new Failure(
                    lineNo,
                    ErrorCode.EMPTY_SKU,
                    "Mã sản phẩm không được rỗng");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(fields[1].strip());
        } catch (NumberFormatException invalid) {
            return new Failure(
                    lineNo,
                    ErrorCode.INVALID_QUANTITY,
                    "Số lượng phải là số nguyên");
        }
        if (quantity <= 0) {
            return new Failure(
                    lineNo,
                    ErrorCode.NON_POSITIVE_QUANTITY,
                    "Số lượng phải lớn hơn 0");
        }

        final BigDecimal unitPrice;
        try {
            unitPrice = new BigDecimal(fields[2].strip());
        } catch (NumberFormatException invalid) {
            return new Failure(
                    lineNo,
                    ErrorCode.INVALID_PRICE,
                    "Đơn giá phải là số thập phân hợp lệ");
        }
        if (unitPrice.signum() < 0) {
            return new Failure(
                    lineNo,
                    ErrorCode.NEGATIVE_PRICE,
                    "Đơn giá không được âm");
        }

        return new Success(
                lineNo,
                new Order(sku, quantity, unitPrice));
    }

    static BatchReport analyze(List<String> source, boolean parallel) {
        Objects.requireNonNull(source, "source");

        // Chỉ số i xác định lineNo, không phụ thuộc thread.
        IntStream indices = IntStream.range(0, source.size());
        if (parallel) {
            indices = indices.parallel();
        }

        List<RowOutcome> outcomes = indices
                .mapToObj(i -> parseLine(i + 1, source.get(i)))
                .toList();

        // toList() giữ encounter order của IntStream.range.
        // Từ List đã vật hóa, mỗi lần stream() là một Stream mới.
        List<Success> successes = outcomes.stream()
                .filter(Success.class::isInstance)
                .map(Success.class::cast)
                .toList();

        List<Failure> failures = outcomes.stream()
                .filter(Failure.class::isInstance)
                .map(Failure.class::cast)
                .toList();

        BigDecimal revenue = successes.stream()
                .map(item -> item.order().amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new BatchReport(
                outcomes, successes, failures, revenue);
    }

    static List<String> sample() {
        return List.of(
                "PEN,2,12.50",
                "NOTE,0,9.99",
                "BOOK,1,80.00",
                "PEN,abc,1.20",
                "BAG,3,-10.00",
                "BAD",
                ",5,4.00",
                "RULER,3,2.00"
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkMoney(
            BigDecimal actual, String expected, String message) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                message + ": actual=" + actual
                        + ", expected=" + expected);
    }

    static void selfTest() {
        List<String> source = sample();
        BatchReport sequential = analyze(source, false);

        check(sequential.outcomes().size() == source.size(),
                "Mất một số dòng đầu vào");
        check(sequential.successes().size() == 3, "Số dòng thành công");
        check(sequential.failures().size() == 5, "Số dòng thất bại");
        check(sequential.successes().size()
                + sequential.failures().size() == source.size(),
                "Một dòng không có đúng một kết quả");
        checkMoney(sequential.revenue(), "111.00", "Tổng doanh thu");

        check(sequential.successes().stream()
                .map(Success::lineNo)
                .toList().equals(List.of(1, 3, 8)),
                "Vị trí các dòng thành công");
        check(sequential.failures().stream()
                .map(Failure::lineNo)
                .toList().equals(List.of(2, 4, 5, 6, 7)),
                "Vị trí các dòng thất bại");
        check(sequential.failures().stream()
                .map(Failure::code)
                .toList().equals(List.of(
                        ErrorCode.NON_POSITIVE_QUANTITY,
                        ErrorCode.INVALID_QUANTITY,
                        ErrorCode.NEGATIVE_PRICE,
                        ErrorCode.WRONG_COLUMN_COUNT,
                        ErrorCode.EMPTY_SKU)),
                "Phân loại mã lỗi");

        // Cùng dữ liệu, kết quả phải tương đương ở hai chế độ.
        BatchReport parallel = analyze(source, true);
        check(sequential.equals(parallel),
                "Kết quả song song khác tuần tự");

        // Nguồn rỗng không phát Success/Failure, tiền bằng 0.
        BatchReport empty = analyze(List.of(), true);
        check(empty.outcomes().isEmpty(), "Kết quả nguồn rỗng");
        check(empty.successes().isEmpty(), "Success nguồn rỗng");
        check(empty.failures().isEmpty(), "Failure nguồn rỗng");
        checkMoney(empty.revenue(), "0", "Tiền nguồn rỗng");

        // Một dòng sai vẫn tạo Failure thay vì mất dữ liệu.
        BatchReport invalidOnly =
                analyze(List.of("A,0,1.00"), false);
        check(invalidOnly.successes().isEmpty(), "Dòng sai đã lọt");
        check(invalidOnly.failures().size() == 1, "Thiếu lỗi dòng sai");
        checkMoney(invalidOnly.revenue(), "0", "Tiền khi toàn lỗi");

        // Số thập phân phải cộng chính xác bằng BigDecimal.
        BatchReport decimals = analyze(
                List.of("A,1,0.10", "B,1,0.20"), false);
        checkMoney(decimals.revenue(), "0.30", "Cộng thập phân");

        // null tại một dòng là lỗi dữ liệu nếu hợp đồng cho phép.
        RowOutcome missing = parseLine(42, null);
        check(missing instanceof Failure, "Không bắt null");
        check(((Failure) missing).code() == ErrorCode.EMPTY_RECORD,
                "Sai mã lỗi dòng null");
        check(missing.lineNo() == 42, "Mất vị trí dòng null");

        // Tạo lại bằng vòng lặp để đối chiếu thứ tự mapToObj.
        List<RowOutcome> expectedOrder = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            expectedOrder.add(parseLine(i + 1, source.get(i)));
        }
        check(sequential.outcomes().equals(expectedOrder),
                "Sai thứ tự kết quả so với đầu vào");

        // Danh sách được công bố từ report không thể sửa.
        boolean rejectedMutation = false;
        try {
            sequential.failures().clear();
        } catch (UnsupportedOperationException expected) {
            rejectedMutation = true;
        }
        check(rejectedMutation, "Danh sách lỗi phải bất biến");
    }

    public static void main(String[] args) {
        BatchReport report = analyze(sample(), false);
        System.out.println("Input: " + report.outcomes().size());
        System.out.println("Success: " + report.successes().size());
        System.out.println("Failure: " + report.failures().size());
        System.out.println("Revenue: " + report.revenue());

        report.failures().forEach(error ->
                System.out.println("line=" + error.lineNo()
                        + ", code=" + error.code()));

        selfTest();
        System.out.println("ALL ROW OUTCOME TESTS PASS");
    }
}
```

Chạy trên JDK 17 trở lên:

```text
javac PerElementOutcomeDemo.java
java PerElementOutcomeDemo
```

Đầu ra kỳ vọng:

```text
Input: 8
Success: 3
Failure: 5
Revenue: 111.00
line=2, code=NON_POSITIVE_QUANTITY
line=4, code=INVALID_QUANTITY
line=5, code=NEGATIVE_PRICE
line=6, code=WRONG_COLUMN_COUNT
line=7, code=EMPTY_SKU
ALL ROW OUTCOME TESTS PASS
```

Các phép `check(...)` ném `AssertionError` khi không đạt, không phụ thuộc tùy chọn `-ea`. Ví dụ được cung cấp để người học biên dịch và chạy; trong bước biên soạn Markdown này, mã chưa được thực thi.

## 6. Vì sao phải giữ cả `Success` và `Failure`?

Nếu chỉ viết:

```java
List<Order> accepted = input.stream()
        .map(PerElementOutcomeDemo::parseWithoutLineNumber)
        .flatMap(Optional::stream)
        .toList();
```

đoạn này chỉ là **mã phác thảo**: `parseWithoutLineNumber` không được định nghĩa trong chương trình hoàn chỉnh. Nó minh họa một thiết kế thường gặp là chuyển bản ghi thành `Optional<Order>` rồi dùng `flatMap(Optional::stream)` để bỏ những bản ghi không có kết quả.

Thiết kế đó có thể phù hợp cho yêu cầu **bỏ qua phần tử không đủ điều kiện**. Nhưng với import dữ liệu cần báo cáo lỗi, nó làm mất thông tin: có bao nhiêu dòng bị bỏ, chúng ở đâu, sai vì lý do gì?

Với `RowOutcome`, giữ được hai nhánh:

```text
                   List<RowOutcome>
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    List<Success>                 List<Failure>
          │                             │
     Order / amount               lineNo / code
          │                             │
          ▼                             ▼
    Doanh thu hợp lệ             Báo cáo nhập liệu
```

Một chỉ số quan trọng để kiểm thử là:

```text
successCount + failureCount == inputCount
```

Điều này đúng trong ví dụ vì **mỗi dòng được xử lý một lần và tạo đúng một `RowOutcome`**. Nếu nghiệp vụ cho phép *bỏ qua chủ đích* một số dòng (như dòng header hoặc comment), hãy mô hình hóa một trạng thái `Skipped` hoặc lọc chúng trước khi đếm, thay vì làm kiểm thử che khuất phần tử đã mất.

### Còn `Collectors.partitioningBy` thì sao?

Ta có thể phân vùng `RowOutcome` theo kiểu:

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;

Map<Boolean, List<RowOutcome>> groups = report.outcomes().stream()
        .collect(Collectors.partitioningBy(
                item -> item instanceof Success));

List<RowOutcome> successBranch = groups.get(true);
List<RowOutcome> failureBranch = groups.get(false);
```

Đây là một cách phân nhóm thuận tiện khi chỉ có hai loại kết quả; `report` là biến `BatchReport` từ chương trình ở mục 5. Giá trị trong hai nhánh vẫn có kiểu khai báo chung `RowOutcome`, nên cần kiểm tra hoặc cast nếu muốn truy cập các trường chỉ tồn tại trên `Success` hay `Failure`. Trong ví dụ hoàn chỉnh, `filter(Success.class::isInstance)` kết hợp `map(Success.class::cast)` giúp tạo ngay các danh sách có kiểu cụ thể.

## 7. Thứ tự và dòng lỗi: tuyệt đối không lấy thứ tự thread làm số dòng

Một câu hỏi thực tế: nếu dùng `parallelStream()` thì `lineNo` có còn đúng không?

Trong ví dụ, `lineNo` được gắn từ **chỉ số của danh sách nguồn**:

```java
IntStream indices = IntStream.range(0, source.size());
if (parallel) {
    indices = indices.parallel();
}
List<RowOutcome> outcomes = indices
        .mapToObj(i -> parseLine(i + 1, source.get(i)))
        .toList();
```

`IntStream.range` có encounter order. `toList()` giữ thứ tự tương ứng khi nguồn và pipeline giữ thứ tự, ngay cả khi phép `mapToObj` được thực hiện bởi các worker khác nhau. Do `lineNo` lấy từ `i + 1`, mã dòng cũng không phụ thuộc vào thứ tự lập lịch.

**Không làm như sau:**

```java
// Không nên: biến count mutable dùng chung khi chạy song song.
// int[] counter = {0};
// source.parallelStream()
//       .map(raw -> parseLine(++counter[0], raw))
//       .toList();
```

Mã trên có race condition và có thể gán số dòng sai. Ngay cả nếu dùng `AtomicInteger` để tránh race, số thứ tự được cấp theo **thời điểm callback chạy**, không nhất thiết là **vị trí dòng trong nguồn**. Một biến đếm thread-safe không tự biến lịch thực thi song song thành encounter order.

### Nếu nguồn là file đọc tuần tự?

Với nguồn file được đọc có thứ tự, có thể gắn `lineNo` trong quá trình đọc, rồi chuyển thành các đối tượng `InputLine(lineNo, raw)` bất biến trước khi xử lý song song. Đừng tạo chỉ số sau khi `unordered()` hoặc sau khi biến đổi khiến không còn mối liên hệ ổn định với vị trí ban đầu.

Ví dụ chương trình dùng `List<String>` để tránh I/O trong bài tập. Trong ứng dụng thật, hãy sử dụng `try-with-resources` khi đọc file và quản lý chính sách lỗi đọc file **khác** với lỗi phân tích một dòng.

## 8. Lỗi từng phần tử và dừng cả pipeline: lựa chọn có chủ đích

Không phải lúc nào cũng cần thu thập toàn bộ lỗi. Có ít nhất ba chiến lược:

| Chiến lược | Cách xử lý | Phù hợp khi |
| --- | --- | --- |
| **Fail-fast** | Ném ngoại lệ và dừng terminal operation nếu một lỗi không được xử lý. | Mọi phần tử đều phải hợp lệ trước khi tiếp tục, hoặc lỗi phản ánh vi phạm nghiêm trọng. |
| **Collect all errors** | Mỗi phần tử trả `Success`/`Failure`, vẫn tiếp tục xử lý những dòng khác. | Import hàng loạt, form validation, kiểm toán, xử lý dữ liệu lỗi cần được tổng hợp. |
| **Skip with metrics** | Bỏ một số phần tử theo chính sách nhưng vẫn ghi nhận số lượng/lý do. | Luồng dữ liệu có các bản ghi được phép bỏ, nhưng cần quan sát tỷ lệ và nguyên nhân bỏ. |

Với **fail-fast**, nếu một lambda ném ngoại lệ trong parallel stream, các tác vụ khác có thể đã bắt đầu hoặc đang chạy. Không được giả định rằng khi terminal operation ném ngoại lệ, mọi side effect ngoài hệ thống đều đã được rollback. Điều này là một lý do quan trọng để giữ các bước trong pipeline **thuần và không can thiệp nguồn**.

Với **collect-all**, một `Failure` ghi nhận sai dữ liệu **không đồng nghĩa** báo cáo phải được phép đưa vào sản xuất. Ứng dụng có thể xử lý hai pha:

1. Parse và thu thập toàn bộ lỗi để hiển thị.
2. Chỉ commit dữ liệu hoặc phát lệnh bên ngoài khi tỷ lệ lỗi đáp ứng chính sách hoặc toàn bộ lô đã được xác nhận.

Như vậy, mô hình kết quả từng phần tử là một **công cụ thu thập thông tin**, còn quyết định chấp nhận cả lô nằm ở tầng nghiệp vụ.

## 9. Tránh biến lỗi thành `null` và tránh ngoại lệ mất ngữ cảnh

Một anti-pattern thường gặp:

```java
List<Order> orders = rawLines.stream()
        .map(raw -> {
            try {
                return parseOrderOrThrow(raw);
            } catch (Exception ignored) {
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

Đây là **mã phác thảo mô tả thiết kế cần tránh**; `parseOrderOrThrow` không thuộc chương trình mẫu. Có ba vấn đề:

1. `catch (Exception)` quá rộng, có thể biến cả lỗi lập trình hoặc sự cố hệ thống thành bản ghi bị bỏ.
2. `null` không mang mã lỗi, vị trí hoặc thông tin sửa dữ liệu.
3. Sau `filter(Objects::nonNull)`, không biết có bao nhiêu dòng lỗi và lỗi gì.

Nếu thật sự muốn bỏ dữ liệu không hợp lệ theo hợp đồng, vẫn nên **ghi nhận lý do** trước khi loại bỏ hoặc tạo một báo cáo đếm lỗi. Không sử dụng một biến `ArrayList<Failure> errors` rồi `errors.add(...) ` bên trong `parallelStream().map(...)` nếu chưa thiết kế đồng bộ và thứ tự: trạng thái mutable dùng chung có thể gây race và khiến kết quả không tái lập.

Một cách rõ hơn là **để `map` tạo giá trị, sau đó `collect` các giá trị** như ví dụ `BatchReport`. Việc tạo `List<RowOutcome>` còn giúp có một nguồn ổn định để tính nhiều chỉ số mà không dùng lại chính đối tượng Stream đã qua terminal operation.

## 10. Kết quả lỗi có cấu trúc cần lưu thông tin gì?

Đối với hệ thống có yêu cầu kiểm toán, các trường thường hữu ích gồm:

| Trường | Vai trò | Lưu ý an toàn |
| --- | --- | --- |
| `lineNo` / `recordId` | Xác định vị trí bản ghi. | Gắn tại nguồn, không dựa vào thứ tự callback song song. |
| `code` | Mã lỗi ổn định cho máy xử lý. | Không dùng toàn bộ text của ngoại lệ làm mã. |
| `message` | Thông báo giúp người dùng sửa. | Không cần kèm nguyên văn dữ liệu bí mật hoặc stack trace. |
| `field` (mở rộng) | Xác định trường lỗi như `quantity`. | Chuẩn hóa tên trường để thống kê. |
| `severity` (mở rộng) | Phân biệt cảnh báo và lỗi chặn. | Quy tắc chấp nhận lô phải định nghĩa rõ. |
| `sourceId` (mở rộng) | Phân biệt file, batch hoặc nguồn nhập. | Không đưa token, mật khẩu hoặc thông tin truy cập vào ID. |

Trong ứng dụng thực tế, có thể cần báo **nhiều lỗi trên cùng một dòng**, không chỉ lỗi đầu tiên. Khi đó một `Failure` có thể chứa `List<ValidationIssue>` bất biến. Parser phải xác định rõ: **trả lỗi đầu tiên** hay **thu thập tất cả lỗi có thể xác minh độc lập**.

Ví dụ chương trình ở mục 5 cố ý trả **lỗi đầu tiên** theo thứ tự kiểm tra, để đầu ra dễ dự đoán. Điều đó không có nghĩa chỉ có một lỗi tồn tại trên một dòng.

### Bảo vệ dữ liệu nhạy cảm

Không mặc định gắn toàn bộ `raw` vào mọi `Failure` hay log. Một dòng nhập có thể chứa tên khách hàng, email, định danh, địa chỉ hoặc token. Nên cân nhắc che bớt giá trị, giữ mã lỗi có cấu trúc, và quy định vòng đời lưu trữ dữ liệu lỗi.

Khi báo cáo lỗi đến hệ thống giám sát, tránh đưa thông báo chi tiết có chứa dữ liệu người dùng vào **nhãn metrics** có tính phân biệt cao. Có thể dùng mã lỗi ổn định làm nhóm thống kê và lưu ngữ cảnh chi tiết ở kênh bảo mật phù hợp.

## 11. Trường hợp biên cần kiểm thử

| Ca kiểm thử | Dữ liệu | Kết quả cần xác nhận |
| --- | --- | --- |
| Dòng hợp lệ | `PEN,2,12.50` | `Success`, thành tiền `25.00`. |
| Số lượng bằng 0 | `NOTE,0,9.99` | `NON_POSITIVE_QUANTITY`. |
| Số lượng không phải số | `PEN,abc,1.20` | `INVALID_QUANTITY`. |
| Đơn giá âm | `BAG,3,-10.00` | `NEGATIVE_PRICE`. |
| Đơn giá không phải số | `PEN,1,x` | `INVALID_PRICE`. |
| Thiếu cột | `BAD` | `WRONG_COLUMN_COUNT`. |
| SKU rỗng | `,5,4.00` | `EMPTY_SKU`. |
| Dòng `null` hoặc toàn khoảng trắng | `null`, `"  "` | `EMPTY_RECORD`. |
| Nguồn rỗng | `List.of()` | Không có `Success` hay `Failure`; tiền là 0. |
| Toàn bộ dòng hỏng | `["A,0,1.00"]` | `0` thành công, `1` thất bại, tiền `0`. |
| Tiền thập phân | `0.10` và `0.20` | Tổng `0.30` theo giá trị số. |
| Nguồn có cùng SKU nhiều lần | Hai dòng `PEN` hợp lệ | Hai `Success`; không tự `distinct()` nếu nghiệp vụ tính theo dòng. |
| Song song | Cùng nguồn, `parallel=true` | Cùng các kết quả, lineNo và tổng như tuần tự. |
| Thứ tự | Nguồn `List` có encounter order | `outcomes` và mỗi nhánh giữ thứ tự dòng trong nguồn. |
| Thử thay đổi báo cáo | `report.failures().clear()` | Ném `UnsupportedOperationException`. |

**Mỗi dòng có đúng một kết quả** là một invariant mạnh của mô hình này. Kiểm thử nên so sánh danh sách kết quả theo đúng thứ tự, không chỉ đếm số lượng. Đặc biệt, phải có những trường hợp lỗi **thực sự kích hoạt nhánh lỗi**; nếu dữ liệu mẫu toàn hợp lệ, một parser bắt sai ngoại lệ vẫn có thể qua test.

## 12. Chi phí bộ nhớ, hiệu năng và xử lý lượng dữ liệu lớn

Ví dụ giữ ba danh sách: `outcomes`, `successes`, `failures`. Chúng chứa những tham chiếu đến các kết quả đã tạo và giúp truy cập, kiểm thử rõ ràng; đổi lại, bộ nhớ tăng theo số dòng đầu vào.

Với dữ liệu rất lớn có thể:

- Dùng một **collector tùy chỉnh** giữ hai nhóm và các tổng một cách nhất quán; chú ý `supplier`, `accumulator`, `combiner` và tính kết hợp khi song song.
- Xử lý dữ liệu theo **lô có kích thước giới hạn**, ghi kết quả vào storage và báo lỗi theo từng lô.
- Thu thập thống kê lỗi bằng **mã lỗi**, thay vì giữ hàng triệu chuỗi thông báo nếu yêu cầu chỉ cần tổng số.
- Dừng hoặc tạm ngừng đọc nguồn khi vượt ngưỡng lỗi được quy định, nhưng phải định nghĩa rõ chính sách và tránh báo rằng đã kiểm tra toàn bộ file nếu thực tế chưa đọc hết.

Khi đọc dữ liệu từ file, cursor CSDL hoặc mạng, `Stream` có thể gắn với tài nguyên cần đóng. Hãy đóng nguồn theo hợp đồng API, thường qua `try-with-resources`; mô hình `Result` không tự giải quyết việc giải phóng tài nguyên.

### Xử lý song song không tự tốt hơn

Nếu mỗi phần tử chỉ cần `split`, `Integer.parseInt` và tạo `BigDecimal` nhỏ, phí lập lịch của `parallelStream()` có thể lớn hơn lợi ích. Nếu parser gọi HTTP hoặc database chặn, nên dùng cơ chế điều phối I/O có giới hạn, thay vì mặc định tận dụng common pool.

`BatchReport` trong ví dụ được tạo từ các giá trị bất biến, không có `ArrayList` mutable dùng chung được cập nhật trong lambda song song. Đây là **điều kiện thuận lợi cho tính đúng**, nhưng không phải lời hứa về tốc độ. Đo bằng dữ liệu đại diện và công cụ phù hợp trước khi tối ưu.

## 13. Bài tập mở rộng

**Bài 1 — Thêm mã lỗi đơn giá không phải số.** Cho dòng `"PEN,2,abc"`, gọi `parseLine(9, ...)`. Xác minh kết quả là `Failure` có `lineNo = 9` và `code == INVALID_PRICE`, không ném `NumberFormatException` ra ngoài.

**Bài 2 — Thống kê lỗi theo mã.** Từ `report.failures()`, lập `Map<ErrorCode, Long>` đếm số lần xuất hiện mỗi mã lỗi:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<ErrorCode, Long> errorCounts = report.failures().stream()
        .collect(Collectors.groupingBy(
                Failure::code,
                Collectors.counting()));
```

Đoạn trên sử dụng kiểu và biến từ chương trình chính; kết quả chỉ có các mã lỗi **đã xuất hiện**, không tự tạo các mục đếm bằng 0.

**Bài 3 — Trả nhiều vấn đề trên một dòng.** Đổi `Failure(code, message)` thành `Failure(List<ValidationIssue>)` để có thể báo cùng lúc SKU rỗng và đơn giá âm. Phân tích những kiểm tra nào độc lập, những kiểm tra nào phải có giá trị parse thành công mới thực hiện được.

**Bài 4 — Chính sách fail-fast của lô.** Sau khi có `BatchReport`, chỉ cho phép thực hiện bước lưu dữ liệu khi `failures.isEmpty()`. Nếu có lỗi, trả toàn bộ báo cáo nhưng **không thực hiện side effect ghi dữ liệu**.

**Bài 5 — Giữ thứ tự sau khi xử lý song song.** Đảo dữ liệu mẫu, chạy `analyze(reversed, true)`. Xác minh các vị trí `lineNo` mới tương ứng với vị trí **trong nguồn đã đảo**, không phải chỉ số ban đầu của file trước khi đảo. Nếu muốn giữ số dòng từ file gốc khi đổi thứ tự, mô hình `InputLine(originalLineNo, raw)` cần được tạo **trước khi hoán vị**.

**Bài 6 — Phân biệt lỗi hệ thống với lỗi dữ liệu.** Giả sử parser cần tra danh mục sản phẩm từ dịch vụ ngoài. Phân loại `SKU_NOT_FOUND`, `HTTP_TIMEOUT`, `AUTH_FAILED`, `SERVICE_UNAVAILABLE`: lỗi nào có thể coi là lỗi của một bản ghi, lỗi nào cần retry hoặc dừng cả lô? Giải thích tại sao `catch (Exception)` rồi gắn cùng một mã `INVALID_RECORD` có thể gây mất thông tin.

**Bài 7 — Tiền tệ.** Bổ sung quy tắc đơn giá có tối đa hai chữ số thập phân, hoặc phải có đơn vị tiền. Phân biệt **sai cú pháp** với **sai ràng buộc nghiệp vụ** và bổ sung mã lỗi riêng. Đừng làm tròn âm thầm một giá trị `1.999` thành `2.00` nếu yêu cầu là từ chối dữ liệu vượt độ chính xác cho phép.

**Bài 8 — Property-based test.** Sinh nhiều dòng hợp lệ và không hợp lệ, kiểm tra bất biến `outcomes.size() == input.size()`, `successes.size() + failures.size() == input.size()` và kết quả `analyze(source, false).equals(analyze(source, true))` khi không có can thiệp nguồn. Không dùng dữ liệu ngẫu nhiên **không có seed** nếu test phải tái lập được.

## 14. Ghi nhớ

- Khi một dòng dữ liệu có thể sai nhưng cả lô vẫn cần được xử lý, hãy mô hình hóa **mỗi phần tử thành `Success` hoặc `Failure`** thay vì bỏ qua lỗi bằng `null` hay bắt rộng mọi ngoại lệ.
- `sealed interface` và `record` trong Java 17 cho phép biểu diễn kết quả có kiểu rõ; giữ **số dòng, mã lỗi và thông báo an toàn** để kiểm thử và sửa dữ liệu.
- Chỉ chuyển **lỗi dữ liệu dự kiến** thành kết quả `Failure`. Lỗi lập trình, hủy luồng và sự cố hạ tầng cần chính sách riêng; không dùng `catch (Throwable)` để ép pipeline tiếp tục.
- Dùng `map` thuần để tạo `RowOutcome`, sau đó tách thành công/lỗi bằng `filter` và `map`; tính tổng tiền hợp lệ bằng `BigDecimal`. Tránh cập nhật danh sách dùng chung bên trong lambda song song.
- Kiểm thử invariant **một đầu vào → một kết quả**, nguồn rỗng, toàn lỗi, mã lỗi, dữ liệu thập phân, thứ tự và kết quả tuần tự/song song. **Việc thu thập lỗi không đồng nghĩa tự động chấp nhận lô dữ liệu**.
