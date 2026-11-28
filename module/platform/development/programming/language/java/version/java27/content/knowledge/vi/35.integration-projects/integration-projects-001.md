# Xây dựng ứng dụng CLI xử lý tệp bằng `record` và collection trong Java 27

Trong chương **Thực hành tích hợp** của lộ trình **Java 27**, chúng ta sẽ xây dựng một chương trình dòng lệnh thực tế, sử dụng hoàn toàn **Java Standard Library**, để **đọc tệp UTF-8, kiểm tra dữ liệu, biểu diễn từng dòng bằng `record`, lọc và tổng hợp bằng các collection, rồi ghi báo cáo có thứ tự xác định**.

Dự án có tên **Expense CLI**: nhận tệp chi tiêu cá nhân theo định dạng TSV (*tab-separated values*), kiểm tra từng giao dịch và tạo báo cáo tổng tiền theo danh mục. Không cần Spring, database, network hay dependency runtime bên ngoài.

Mục tiêu không chỉ là chạy được một vòng lặp đọc file. Một CLI đáng tin cậy cần giải quyết **hợp đồng dữ liệu đầu vào**, **xử lý lỗi có số dòng**, **số tiền chính xác**, **kết quả ổn định qua nhiều lần chạy**, **đóng tài nguyên**, và đặc biệt **không ghi hỏng file đầu ra khi một bước thất bại**.

Các tính năng ngôn ngữ/API ở đây đều hiện hành với Java 27: `record` (ổn định từ Java 16), `List`, `Map`, `Set`, Stream API, `BigDecimal`, `LocalDate`, `Path`, `Files`, `StandardCharsets.UTF_8` và `try-with-resources`. Không cần dựa vào preview feature.

## 1. Yêu cầu sản phẩm và kết quả kỳ vọng

Ứng dụng hỗ trợ hai lệnh:

```text
validate <input.tsv>

report <input.tsv> <output.tsv> [--from=YYYY-MM-DD] [--to=YYYY-MM-DD]
```

- `validate`: đọc toàn bộ đầu vào, kiểm tra header, kiểu dữ liệu và ID trùng; **không tạo file mới**.
- `report`: kiểm tra đầu vào trước, lọc theo khoảng ngày nếu có, nhóm theo danh mục, cộng số tiền và ghi một tệp báo cáo.
- `--from` và `--to` là ngày **bao gồm cả hai đầu mút**.
- Báo cáo sắp xếp theo **tổng tiền giảm dần**; nếu bằng nhau thì theo tên danh mục tăng dần để kết quả ổn định.
- Khi gặp lỗi cấu trúc, chương trình báo **dòng gây lỗi** và kết thúc khác `0`.
- Chỉ khi đã đọc và tổng hợp thành công, chương trình mới thực hiện bước ghi file tạm và chuyển file vào đích.

### 1.1. Ví dụ nhanh

Tệp `expenses.tsv` được lưu bằng UTF-8, sử dụng ký tự **TAB thực sự** giữa các cột:

```text
id	date	category	amount
E-001	2026-11-25	Ăn uống	120.50
E-002	2026-11-26	Đi lại	60.00
E-003	2026-11-26	Ăn uống	30.00
E-004	2026-11-27	Sách	80.00
```

Báo cáo cho toàn bộ giao dịch:

```text
category	count	total
Ăn uống	2	150.50
Sách	1	80.00
Đi lại	1	60.00
TOTAL	4	290.50
```

Nếu chạy với `--from=2026-11-26 --to=2026-11-27`, kết quả là:

```text
category	count	total
Sách	1	80.00
Đi lại	1	60.00
Ăn uống	1	30.00
TOTAL	3	170.00
```

Các dấu tab trong khối ví dụ là **dấu phân cách trường**, không phải nhiều dấu cách được căn chỉnh theo cột.

## 2. Vì sao chọn TSV thay vì giả lập parser CSV?

CSV tổng quát có thể chứa dấu phẩy bên trong chuỗi được quote, dấu `"` được escape, và đôi khi cả **newline bên trong một field**. Vì vậy code kiểu `line.split(",")` **không phải parser CSV chuẩn**.

Dự án cố ý chọn một **hợp đồng TSV có giới hạn**:

| Quy tắc | Yêu cầu |
| --- | --- |
| Encoding | UTF-8, **không có BOM** |
| Dòng đầu | Chính xác `id<TAB>date<TAB>category<TAB>amount` |
| Dòng dữ liệu | Đúng **bốn trường**, ngăn bằng TAB |
| `id` | 1–40 ký tự ASCII: chữ, số, `_`, `-`; duy nhất |
| `date` | ISO `yyyy-MM-dd`, chẳng hạn `2026-11-27` |
| `category` | 1–40 ký tự thuộc nhóm chữ/số Unicode, khoảng trắng, `_`, `-` |
| `amount` | Số không âm: tối đa 12 chữ số phần nguyên, tối đa 2 chữ số thập phân, dùng dấu `.` |
| Dòng trống | Bị từ chối |
| Ký tự TAB trong field | Không hỗ trợ; sẽ bị coi là cột bổ sung |
| Dấu quote và newline trong field | Không hỗ trợ |
| Header/giá trị không hợp lệ | Báo lỗi, không bỏ qua im lặng |
| Số dòng dữ liệu | Giới hạn **100.000** cho bản minh họa |

Đây là **định dạng riêng của bài tập**, không được gọi là bộ đọc mọi TSV/CSV hợp lệ trên thị trường. Khi cần dữ liệu có trích dẫn, xuống dòng trong field hoặc định dạng không kiểm soát, hãy chọn thư viện parser CSV/TSV chuyên dụng với contract được xác định.

### 2.1. Không phụ thuộc default charset hoặc locale

Chương trình luôn dùng `StandardCharsets.UTF_8` khi đọc/ghi và `BigDecimal` khi xử lý tiền. Không lấy `Double.parseDouble` để lưu tiền và không để số tiền phụ thuộc dấu phẩy thập phân của locale máy người dùng.

Ví dụ **không nên dùng** cho tiền:

```java
double a = 0.1;
double b = 0.2;
System.out.println(a + b == 0.3); // false
```

`BigDecimal` được khởi tạo từ chuỗi thập phân tránh nhiều sai khác thường gặp do biểu diễn nhị phân của `double`.

## 3. Thiết kế mô hình bằng `record`

Một bản ghi chi tiêu:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

record Expense(
    String id,
    LocalDate date,
    String category,
    BigDecimal amount
) { }
```

Java tự tạo constructor, accessors (`id()`, `date()`...), `equals`, `hashCode`, `toString`; các field của record là `final`. Đây là **shallowly immutable data carrier**: record không tự biến object mutable được giữ bên trong thành immutable.

Với `Expense`, các component `String`, `LocalDate` và `BigDecimal` đều là các value objects bất biến, nên bản ghi có mô hình dữ liệu tương đối an toàn để chia sẻ.

### 3.1. Dùng compact constructor để bảo vệ invariant

```java
import java.math.RoundingMode;
import java.util.Objects;

record Expense(
    String id,
    LocalDate date,
    String category,
    BigDecimal amount
) {
    Expense {
        id = Objects.requireNonNull(id).strip();
        date = Objects.requireNonNull(date);
        category = Objects.requireNonNull(category).strip();
        amount = Objects.requireNonNull(amount)
            .setScale(2, RoundingMode.UNNECESSARY);

        if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid expense ID");
        }
        if (!category.matches("[\\p{L}\\p{M}\\p{N} _-]{1,40}")
                || category.equalsIgnoreCase("TOTAL")) {
            throw new IllegalArgumentException("Invalid category");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }
}
```

Trong compact constructor, gán lại tên parameter như `id = id.strip()` được phép; các giá trị cuối cùng sẽ được gán vào record fields sau khi constructor body hoàn tất.

`RoundingMode.UNNECESSARY` **không làm tròn ngầm**. Với giá trị không thể biểu diễn chính xác ở hai chữ số thập phân, phép `setScale(2, ...)` ném `ArithmeticException`. Phần parser còn giới hạn cú pháp số tiền để từ chối dữ liệu không phù hợp trước khi chuyển thành `BigDecimal`.

**Lưu ý về danh mục:** ví dụ cho phép chữ/số Unicode và các ký tự an toàn đơn giản để hạn chế lỗi định dạng và rủi ro *formula injection* khi báo cáo được mở bằng bảng tính. Đây **không phải giải pháp bảo mật hoàn chỉnh cho mọi định dạng spreadsheet**.

## 4. Lựa chọn collection theo vai trò

| Collection | Nhiệm vụ trong dự án | Lý do |
| --- | --- | --- |
| `ArrayList<Expense>` | Lưu giao dịch sau parse | Có thứ tự, duyệt tuần tự hiệu quả |
| `HashSet<String>` | Phát hiện ID trùng | `add(id)` trả `false` nếu đã tồn tại |
| `HashMap<String, CategorySummary>` | Tổng hợp số liệu theo danh mục | Tra cứu và cập nhật theo khóa |
| `List<CategorySummary>` | Báo cáo đã sắp xếp | Thuận tiện hiển thị/ghi file |
| `List.copyOf(...)` | Chặn thay đổi list từ caller | Tạo unmodifiable snapshot |
| `Map.merge(...)` | Cộng dồn kết quả nhóm | Giảm logic `containsKey`/`get`/`put` thủ công |

Không nên dùng `HashMap` rồi dựa vào thứ tự duyệt của nó. Nếu output cần ổn định, phải **sort tường minh**; `HashMap` không cam kết iteration order.

### 4.1. Các record phụ trợ

```java
record CategorySummary(
    String category,
    long count,
    BigDecimal total
) { }

record Report(
    long inputRows,
    long selectedRows,
    BigDecimal grandTotal,
    java.util.List<CategorySummary> categories
) {
    Report {
        categories = java.util.List.copyOf(categories);
    }
}
```

`Report` sử dụng bản sao list **không thể sửa bằng các thao tác collection thông thường**. Nếu các phần tử là object mutable, `List.copyOf` vẫn chỉ bảo vệ cấu trúc danh sách; trường hợp này `CategorySummary` cũng là record chứa những component bất biến.

## 5. Kiến trúc CLI đơn giản, dễ kiểm thử

```text
Arguments từ terminal
          |
          v
parseOptions(args)
          |
          v
load(input.tsv) ---------------------+
 | BufferedReader UTF-8              |
 | Header + row validations          |
 | Expense record + Set duplicate ID |
 +-----------------------------------+
          |
          v
List<Expense>
          |
          +---- validate ---> In số dòng, exit 0
          |
          +---- report
                    |
                    v
             filter by DateRange
                    |
                    v
             Map.merge aggregate
                    |
                    v
             sort CategorySummary
                    |
                    v
            writeReport(...)
               |
               +-- create temp in output folder
               +-- BufferedWriter UTF-8
               +-- Files.move ATOMIC_MOVE
               +-- cleanup temp on failure
```

Phân chia này quan trọng hơn việc đưa mọi thứ vào một `main()` lớn:
- **Parse/validation** không phụ thuộc output.
- **Aggregate** là hàm logic dễ unit test.
- **Write** là phần có side effect và quyền truy cập filesystem.
- **CLI** chỉ phụ trách ghép các bước và báo exit code.

### 5.1. Quy tắc exit code của dự án

| Exit code | Nghĩa |
| --- | --- |
| `0` | Hoàn tất thành công |
| `2` | Sai cú pháp hoặc dữ liệu input không hợp lệ |
| `1` | Lỗi I/O như file không đọc được, thiếu quyền, atomic move không hỗ trợ |

Đây là **quy ước của Expense CLI**, không phải quy tắc bắt buộc của JVM. Chương trình dùng `System.exit` **chỉ ở điểm vào**; các method xử lý nghiệp vụ trả kết quả hoặc ném exception để dễ unit test.

## 6. Mã nguồn đầy đủ: `ExpenseCli.java`

Chương trình dưới đây là **một file Java độc lập**, có thể biên dịch bằng JDK 27, không dùng package hoặc thư viện ngoài. Lưu file với UTF-8 dưới tên `ExpenseCli.java` và giữ nguyên toàn bộ các phần bên trong cùng một source file.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class ExpenseCli {
    private static final String HEADER = "id\tdate\tcategory\tamount";
    private static final int MAX_ROWS = 100_000;

    private ExpenseCli() { }

    enum Mode {
        VALIDATE, REPORT
    }

    record DateRange(LocalDate from, LocalDate to) {
        DateRange {
            if (from != null && to != null && from.isAfter(to)) {
                throw new IllegalArgumentException(
                    "--from must not be after --to");
            }
        }

        boolean contains(LocalDate date) {
            return (from == null || !date.isBefore(from))
                && (to == null || !date.isAfter(to));
        }
    }

    record Options(
        Mode mode,
        Path input,
        Path output,
        DateRange range
    ) { }

    record Expense(
        String id,
        LocalDate date,
        String category,
        BigDecimal amount
    ) {
        Expense {
            id = Objects.requireNonNull(id, "id").strip();
            date = Objects.requireNonNull(date, "date");
            category = Objects.requireNonNull(category, "category").strip();
            amount = Objects.requireNonNull(amount, "amount")
                .setScale(2, RoundingMode.UNNECESSARY);

            if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
                throw new IllegalArgumentException(
                    "ID must have 1-40 letters/digits/_/-");
            }
            if (!category.matches(
                    "[\\p{L}\\p{M}\\p{N} _-]{1,40}")
                    || category.equalsIgnoreCase("TOTAL")) {
                throw new IllegalArgumentException(
                    "Invalid or reserved category");
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException(
                    "Amount must be non-negative");
            }
        }
    }

    record CategorySummary(
        String category,
        long count,
        BigDecimal total
    ) { }

    record Report(
        long inputRows,
        long selectedRows,
        BigDecimal grandTotal,
        List<CategorySummary> categories
    ) {
        Report {
            categories = List.copyOf(categories);
        }
    }

    public static void main(String[] args) {
        int code = run(args);
        if (code != 0) {
            System.exit(code);
        }
    }

    static int run(String[] args) {
        try {
            Options options = parseOptions(args);
            List<Expense> rows = load(options.input());

            if (options.mode() == Mode.VALIDATE) {
                System.out.println("VALID: " + rows.size() + " rows");
                return 0;
            }

            Report report = summarize(rows, options.range());
            writeReport(options.input(), options.output(), report);
            System.out.println(
                "OK: input=" + report.inputRows()
                + ", selected=" + report.selectedRows()
                + ", total=" + money(report.grandTotal())
                + ", output=" + options.output()
            );
            return 0;
        } catch (IllegalArgumentException | DateTimeException ex) {
            System.err.println("Input error: " + ex.getMessage());
            usage();
            return 2;
        } catch (IOException ex) {
            System.err.println("I/O error: " + ex.getMessage());
            return 1;
        }
    }

    private static void usage() {
        System.err.println(
            "Usage:\n"
            + "  java ExpenseCli.java validate <input.tsv>\n"
            + "  java ExpenseCli.java report <input.tsv> <output.tsv>"
            + " [--from=YYYY-MM-DD] [--to=YYYY-MM-DD]");
    }

    static Options parseOptions(String[] args) {
        if (args.length == 2 && "validate".equals(args[0])) {
            return new Options(
                Mode.VALIDATE,
                Path.of(args[1]),
                null,
                new DateRange(null, null)
            );
        }

        if (args.length < 3 || !"report".equals(args[0])) {
            throw new IllegalArgumentException("Invalid command/arguments");
        }

        Map<String, String> flags = new HashMap<>();
        for (int i = 3; i < args.length; i++) {
            String option = args[i];
            int equalAt = option.indexOf('=');
            if (equalAt <= 2 || equalAt == option.length() - 1) {
                throw new IllegalArgumentException(
                    "Expected --from=DATE or --to=DATE");
            }

            String name = option.substring(0, equalAt);
            String value = option.substring(equalAt + 1);
            if (!name.equals("--from") && !name.equals("--to")) {
                throw new IllegalArgumentException(
                    "Unknown option: " + name);
            }
            if (flags.putIfAbsent(name, value) != null) {
                throw new IllegalArgumentException(
                    "Duplicate option: " + name);
            }
        }

        LocalDate from = flags.containsKey("--from")
            ? LocalDate.parse(flags.get("--from"))
            : null;
        LocalDate to = flags.containsKey("--to")
            ? LocalDate.parse(flags.get("--to"))
            : null;

        return new Options(
            Mode.REPORT,
            Path.of(args[1]),
            Path.of(args[2]),
            new DateRange(from, to)
        );
    }

    static BigDecimal parseAmount(String value) {
        if (!value.matches("[0-9]{1,12}(\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException(
                "Amount must use digits and optional .dd");
        }
        return new BigDecimal(value)
            .setScale(2, RoundingMode.UNNECESSARY);
    }

    static List<Expense> load(Path input) throws IOException {
        try (BufferedReader reader =
                Files.newBufferedReader(
                    input, StandardCharsets.UTF_8)) {

            String header = reader.readLine();
            if (!HEADER.equals(header)) {
                throw new IllegalArgumentException(
                    "Line 1: expected header: id<TAB>date<TAB>category<TAB>amount");
            }

            List<Expense> rows = new ArrayList<>();
            Set<String> ids = new HashSet<>();
            int lineNo = 1;

            String line;
            while ((line = reader.readLine()) != null) {
                lineNo++;
                if (rows.size() >= MAX_ROWS) {
                    throw new IllegalArgumentException(
                        "Input exceeds " + MAX_ROWS + " rows");
                }

                String[] fields = line.split("\t", -1);
                if (fields.length != 4) {
                    throw new IllegalArgumentException(
                        "Line " + lineNo + ": expected exactly 4 fields");
                }

                try {
                    Expense row = new Expense(
                        fields[0],
                        LocalDate.parse(fields[1]),
                        fields[2],
                        parseAmount(fields[3])
                    );

                    if (!ids.add(row.id())) {
                        throw new IllegalArgumentException(
                            "Duplicate ID: " + row.id());
                    }
                    rows.add(row);
                } catch (IllegalArgumentException
                        | DateTimeException
                        | ArithmeticException ex) {
                    throw new IllegalArgumentException(
                        "Line " + lineNo + ": " + ex.getMessage(), ex);
                }
            }
            return List.copyOf(rows);
        }
    }

    static Report summarize(
            List<Expense> rows, DateRange range) {
        List<Expense> selected = rows.stream()
            .filter(row -> range.contains(row.date()))
            .toList();

        Map<String, CategorySummary> totals = new HashMap<>();
        for (Expense row : selected) {
            CategorySummary current = new CategorySummary(
                row.category(), 1L, row.amount()
            );

            totals.merge(
                row.category(),
                current,
                (oldValue, newValue) -> new CategorySummary(
                    oldValue.category(),
                    Math.addExact(oldValue.count(), newValue.count()),
                    oldValue.total().add(newValue.total())
                )
            );
        }

        List<CategorySummary> sorted = totals.values().stream()
            .sorted(
                Comparator.comparing(CategorySummary::total)
                    .reversed()
                    .thenComparing(CategorySummary::category)
            )
            .toList();

        BigDecimal grandTotal = selected.stream()
            .map(Expense::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new Report(
            rows.size(), selected.size(), grandTotal, sorted
        );
    }

    static String money(BigDecimal amount) {
        return amount.setScale(2, RoundingMode.UNNECESSARY)
            .toPlainString();
    }

    static void writeReport(
            Path input, Path output, Report report)
            throws IOException {
        Path source = input.toAbsolutePath().normalize();
        Path target = output.toAbsolutePath().normalize();

        if (source.equals(target)
                || (Files.exists(target)
                    && Files.isSameFile(source, target))) {
            throw new IllegalArgumentException(
                "Output must not be the input file");
        }

        Path parent = target.getParent();
        if (parent == null || !Files.isDirectory(parent)) {
            throw new IllegalArgumentException(
                "Output directory does not exist: " + parent);
        }

        // File tạm nằm trong thư mục đích, thuận lợi cho atomic rename.
        Path temporary = Files.createTempFile(
            parent, ".expense-report-", ".tmp");

        try {
            try (BufferedWriter writer =
                    Files.newBufferedWriter(
                        temporary, StandardCharsets.UTF_8)) {
                writer.write("category\tcount\ttotal");
                writer.newLine();

                for (CategorySummary item : report.categories()) {
                    writer.write(item.category());
                    writer.write('\t');
                    writer.write(Long.toString(item.count()));
                    writer.write('\t');
                    writer.write(money(item.total()));
                    writer.newLine();
                }

                writer.write("TOTAL\t");
                writer.write(Long.toString(report.selectedRows()));
                writer.write('\t');
                writer.write(money(report.grandTotal()));
                writer.newLine();
            }

            // Fail-closed: không ghi đè bằng non-atomic move.
            try {
                Files.move(
                    temporary, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING
                );
            } catch (AtomicMoveNotSupportedException ex) {
                throw new IOException(
                    "Atomic move unsupported: output not replaced", ex);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
```

### 6.1. Những điều cần lưu ý trong code

- `record Expense` chỉ được tạo sau khi parser kiểm tra đủ bốn trường.
- `Set.add(id)` giúp phát hiện ID bị lặp trong file.
- `List.copyOf(rows)` cung cấp snapshot không cho caller tự thêm/xóa hàng.
- `DateRange.contains` thể hiện điều kiện bao gồm ngày đầu và cuối.
- `Map.merge` kết hợp hai `CategorySummary` thành một giá trị mới.
- `BigDecimal` cộng tiền chính xác, `toPlainString()` tránh ký pháp số mũ.
- `Comparator...reversed().thenComparing(...)` cố định thứ tự báo cáo.
- `try-with-resources` đóng `BufferedReader` và `BufferedWriter`.
- Không ghi trực tiếp vào output; file được tạo ở một đường dẫn tạm trong cùng thư mục.
- Nếu hệ thống file **không hỗ trợ atomic move**, chương trình từ chối hoàn tất và xóa file tạm, thay vì âm thầm chuyển sang thao tác không nguyên tử.

**Giới hạn quan trọng của `ATOMIC_MOVE`:** Java NIO không bảo đảm mọi file provider sẽ thay thế một file đích đã tồn tại khi `ATOMIC_MOVE` được yêu cầu; hành vi khi đích tồn tại có thể phụ thuộc implementation. Trường hợp move không thành công, chương trình trả lỗi, giữ output cũ nếu nó chưa bị thay thế. Với môi trường nhiều process cùng ghi hoặc kịch bản chống crash nghiêm ngặt, cần thiết kế thêm locking, durability (`fsync`) và chính sách overwrite; ví dụ này không tự nhận là một transaction filesystem tổng quát.

## 7. Tạo dữ liệu mẫu và chạy CLI

Tạo `expenses.tsv` bằng text editor lưu **UTF-8 không BOM**, chọn TAB làm dấu phân cách. Không phải mọi editor đều hiển thị TAB rõ ràng; nên kiểm tra cấu trúc cột trước khi chạy.

```text
id	date	category	amount
E-001	2026-11-25	Ăn uống	120.50
E-002	2026-11-26	Đi lại	60.00
E-003	2026-11-26	Ăn uống	30.00
E-004	2026-11-27	Sách	80.00
```

### 7.1. Chạy source-file mode

Với JDK 27, Java hỗ trợ chạy trực tiếp một source file:

```text
java ExpenseCli.java validate expenses.tsv
```

Kỳ vọng:

```text
VALID: 4 rows
```

Tạo báo cáo:

```text
java ExpenseCli.java report expenses.tsv summary.tsv
```

Kỳ vọng ở console:

```text
OK: input=4, selected=4, total=290.50, output=summary.tsv
```

Nội dung `summary.tsv`:

```text
category	count	total
Ăn uống	2	150.50
Sách	1	80.00
Đi lại	1	60.00
TOTAL	4	290.50
```

### 7.2. Biên dịch rồi chạy

Nếu muốn tái sử dụng class đã compile:

```text
javac -encoding UTF-8 ExpenseCli.java
java ExpenseCli validate expenses.tsv
java ExpenseCli report expenses.tsv summary.tsv
```

Đặt hai file đầu vào/đầu ra trong một thư mục người dùng được quyền đọc/ghi. Khi chạy trong một shell, chú ý đường dẫn tương đối được giải theo **working directory** của tiến trình.

### 7.3. Lọc theo ngày

```text
java ExpenseCli.java report expenses.tsv filtered.tsv --from=2026-11-26 --to=2026-11-27
```

Bản report dự kiến:

```text
category	count	total
Sách	1	80.00
Đi lại	1	60.00
Ăn uống	1	30.00
TOTAL	3	170.00
```

Nếu chỉ cần giới hạn dưới:

```text
java ExpenseCli.java report expenses.tsv newer.tsv --from=2026-11-26
```

Nếu `--from` lớn hơn `--to`, `DateRange` từ chối ngay; không ghi output.

## 8. Tách trách nhiệm: vì sao không đọc rồi ghi trong cùng một vòng lặp?

Chương trình đi theo các giai đoạn:

1. Kiểm tra cấu trúc của **toàn bộ input**.
2. Đưa giao dịch hợp lệ vào `List<Expense>`.
3. Lọc và tổng hợp trong bộ nhớ.
4. Chuẩn bị report ở file tạm.
5. Thay file đích khi report đã được ghi và đóng.

Lợi thế: nếu dòng cuối cùng sai định dạng, ứng dụng **không sửa một nửa báo cáo cũ**. Cách làm này dễ test và phù hợp file nhỏ/vừa.

Nhược điểm: giữ toàn bộ giao dịch trong `ArrayList` cần bộ nhớ **tăng theo số dòng**. Giới hạn 100.000 dòng trong demo nhằm tránh tự nhận có thể xử lý file dung lượng không giới hạn. Để xử lý dữ liệu lớn hơn, có thể **aggregate streaming** mà không giữ từng `Expense`, nhưng vẫn phải quyết định chiến lược phát hiện ID trùng.

## 9. Vì sao cần `try-with-resources`?

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Đọc nhiều dòng.
}
```

Khi rời scope, reader được đóng dù parse ném exception. Tương tự với writer.

Nếu dùng `Files.lines(path)` để lấy `Stream<String>` từ file, stream có tài nguyên liên quan và cũng cần đóng:

```java
try (var lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    System.out.println(count);
}
```

Không trả một stream từ `Files.lines` ra ngoài rồi đóng reader trước khi caller tiêu thụ. Không mặc định GC sẽ đóng file descriptor đúng thời điểm.

### 9.1. Không dùng `readAllLines()` với file không biết kích thước

```java
// Chỉ nên dùng khi đã biết file nhỏ:
List<String> lines = Files.readAllLines(
    path, StandardCharsets.UTF_8);
```

`readAllLines` materialize mọi dòng vào bộ nhớ. `newBufferedReader` cho phép đọc tuần tự. Trong demo, dù parser đọc tuần tự, nó vẫn **chủ ý giữ record** để minh họa collection và cho phép kiểm tra toàn bộ input.

## 10. Record không có nghĩa dữ liệu tự hợp lệ

Compiler tạo accessors/equality nhưng **không tự kiểm tra giá trị nghiệp vụ**. Nếu gọi:

```java
new Expense("E-5", LocalDate.now(), "Sách",
    new BigDecimal("-5"));
```

compact constructor phải từ chối số tiền âm theo chính sách của dự án.

Nếu dùng một record chứa `List` hoặc `Map`, việc field là `final` chỉ ngăn gán lại reference, **không tự ngăn sửa collection**:

```java
record Batch(List<Expense> expenses) {
    Batch {
        expenses = List.copyOf(expenses);
    }
}
```

Không nên đưa một `ArrayList` mutable trực tiếp vào record rồi tuyên bố model hoàn toàn immutable. `List.copyOf` cũng không deep-copy các phần tử bên trong, nhưng `Expense` ở ví dụ có component bất biến.

## 11. BigDecimal: chính xác và chính sách làm tròn

Một số quy tắc:

```java
BigDecimal a = new BigDecimal("10.10");
BigDecimal b = new BigDecimal("0.20");

BigDecimal sum = a.add(b);
System.out.println(sum.toPlainString()); // 10.30
```

**Không** dùng constructor `new BigDecimal(0.1)` nếu muốn giá trị tiền thập phân đúng 0.1; nó phản ánh biểu diễn binary floating-point đầu vào. Dùng string hoặc `BigDecimal.valueOf(...)` tùy nguồn.

Phân biệt:

- `equals`: so cả **value và scale** (`10.0` khác `10.00`).
- `compareTo`: so **giá trị số học** (`10.0` bằng `10.00` về mặt số).
- `setScale(2, UNNECESSARY)`: yêu cầu số có thể biểu diễn đúng ở hai chữ số thập phân, không âm thầm làm tròn.
- `toPlainString`: ghi dạng thập phân không sử dụng ký pháp khoa học.

Dự án chỉ chấp nhận số tiền có tối đa hai chữ số sau dấu chấm. Nếu nghiệp vụ có thuế, tỷ giá, crypto hoặc nhiều loại tiền tệ, cần **mô hình hóa currency và rounding policy** tường minh; không áp dụng cứng hai chữ số cho mọi đơn vị tiền.

## 12. Lựa chọn xử lý lỗi: fail-fast có số dòng
Khi một dòng sai, bản minh họa **từ chối toàn bộ file** thay vì im lặng bỏ qua dữ liệu. Ví dụ:

```text
id	date	category	amount
E-001	2026-11-25	Ăn uống	120.50
E-001	2026-11-26	Đi lại	60.00
```

Lần chạy `validate` có thể in:

```text
Input error: Line 3: Duplicate ID: E-001
Usage:
  java ExpenseCli.java validate <input.tsv>
  java ExpenseCli.java report <input.tsv> <output.tsv> [--from=YYYY-MM-DD] [--to=YYYY-MM-DD]
```

Exit code của quy ước dự án là `2`. Lỗi file không đọc được, file đích không ghi được hoặc atomic move không hỗ trợ trả `1` qua nhánh `IOException`.

### 12.1. Những trường hợp parser từ chối

| Dữ liệu | Lý do | Hành vi |
| --- | --- | --- |
| File trống | Không có header bắt buộc | Lỗi dòng 1 |
| Header sai thứ tự | Không đúng contract | Lỗi dòng 1 |
| Có UTF-8 BOM trước `id` | Header không khớp chính xác | Lỗi dòng 1 |
| Dòng trống | Không đủ bốn trường | Lỗi tương ứng |
| Thêm TAB trong danh mục | Có hơn bốn trường | Lỗi tương ứng |
| `2026-02-30` | Ngày không hợp lệ | Parse error có số dòng |
| `12,50` | Dùng dấu phẩy thập phân | Reject |
| `1e3` | Không thuộc cú pháp số tiền đã chọn | Reject |
| `12.999` | Nhiều hơn hai chữ số thập phân | Reject |
| `-10.00` | Số tiền âm ngoài phạm vi | Reject |
| Hai dòng cùng ID | Vi phạm uniqueness trong file | Reject |
| Danh mục `TOTAL` | Đụng nhãn tổng kết dành riêng | Reject |
| Hơn 100.000 dòng dữ liệu | Vượt giới hạn bản demo | Reject |

Nếu cần nhập dữ liệu đã xuất từ Excel, phải xác định rõ delimiter, BOM, quoting và locale; **đừng tự sửa bằng cách bỏ mọi dòng lỗi**. Việc bỏ dòng sai có thể làm số liệu báo cáo không còn đối soát được.

### 12.2. Vì sao dùng `split("\t", -1)`?

Với regex TAB và tham số `-1`, Java giữ lại các **trường trống ở cuối**:

```java
String[] fields = "E-1\t2026-11-27\tSách\t".split("\t", -1);
System.out.println(fields.length); // 4
System.out.println(fields[3].isEmpty()); // true
```

Nếu dùng `split("\t")` không có limit âm, cột `amount` rỗng ở cuối có thể bị loại khỏi array. Trong cả hai trường hợp có thể báo lỗi, nhưng `-1` giúp parser xác định **đúng số cột** và phân biệt thiếu cột với cột có giá trị rỗng.

`String.split` không phải CSV parser tổng quát: không hỗ trợ quy tắc quote/escape của CSV. Đây là giới hạn **có chủ đích** của dự án.

### 12.3. Bảo toàn thông tin lỗi hữu ích

Trong `load`, exception được wrap cùng số dòng:

```java
throw new IllegalArgumentException(
    "Line " + lineNo + ": " + ex.getMessage(), ex);
```

Việc giữ `cause` giúp unit test và logging nội bộ có thể biết nguyên nhân gốc. CLI chỉ xuất thông tin lỗi ngắn gọn cho người dùng; không tự in stack trace dài hoặc dump toàn bộ nội dung input ra stderr.

Nếu làm ứng dụng phục vụ tệp của người dùng không tin cậy, cần thêm giới hạn **độ dài từng dòng** trước khi materialize chuỗi, kiểm tra kích thước file và giám sát thời gian/CPU parse. `BufferedReader.readLine()` vẫn có thể cấp phát một chuỗi rất dài trước khi bước kiểm tra số dòng kịp chạy.

## 13. Tổng hợp bằng `Map.merge` và sắp xếp xác định

Tâm điểm xử lý collection:

```java
Map<String, CategorySummary> totals = new HashMap<>();

for (Expense row : selected) {
    totals.merge(
        row.category(),
        new CategorySummary(row.category(), 1, row.amount()),
        (oldValue, newValue) -> new CategorySummary(
            oldValue.category(),
            oldValue.count() + newValue.count(),
            oldValue.total().add(newValue.total())
        )
    );
}
```

`merge(key, value, remappingFunction)` hoạt động như sau:

- Nếu key chưa có giá trị tương ứng, đặt `value`.
- Nếu key đã có, kết hợp giá trị cũ và mới bằng hàm được cung cấp.
- Nếu remapping trả `null`, entry có thể bị xóa; ví dụ này **không** làm vậy.

Nhờ sử dụng record `CategorySummary`, mỗi lần cập nhật tạo một **giá trị kết quả mới** thay vì sửa trực tiếp các field của object summary.

### 13.1. Có thể tách một accumulator mutable cho hiệu năng

Với file rất lớn, tạo nhiều `CategorySummary` trong `merge` có thêm allocation. Một giải pháp khác:

```java
final class MutableTotal {
    long count;
    BigDecimal total = BigDecimal.ZERO;

    void add(BigDecimal value) {
        count++;
        total = total.add(value);
    }
}

Map<String, MutableTotal> byCategory = new HashMap<>();

for (Expense row : selected) {
    byCategory.computeIfAbsent(
        row.category(), ignored -> new MutableTotal()
    ).add(row.amount());
}
```

Dùng mutable accumulator là lựa chọn kỹ thuật hợp lý khi việc cập nhật chỉ xảy ra trong một scope rõ. Sau đó có thể **chuyển sang record bất biến** để xuất kết quả. Không có quy tắc phải tránh hoàn toàn mutable object; vấn đề chính là **không để trạng thái mutable lan ra ngoài phạm vi kiểm soát**.

### 13.2. Vì sao không giữ thứ tự của `HashMap`?

Với output:

```text
category	count	total
Ăn uống	2	150.50
Sách	1	80.00
Đi lại	1	60.00
```

thứ tự đến từ:

```java
totals.values().stream()
    .sorted(
        Comparator.comparing(CategorySummary::total)
            .reversed()
            .thenComparing(CategorySummary::category)
    )
    .toList();
```

Comparator chọn tổng tiền giảm dần, sau đó category tăng dần khi bằng nhau. Nhờ vậy cùng input và cùng rule sẽ có thứ tự output nhất quán, độc lập với hash bucket layout.

**So sánh `String` mặc định không phải sắp xếp theo từ điển tiếng Việt.** Nếu người dùng cần collation theo locale, phải dùng `Collator` hoặc quy tắc sắp xếp riêng và test bằng dữ liệu có dấu, không suy ra từ `String.compareTo`.

## 14. Lọc ngày và ý nghĩa của `LocalDate`

`LocalDate` biểu diễn **ngày theo lịch**, không mang giờ hay timezone. Đầu vào được yêu cầu theo ISO 8601 dạng `YYYY-MM-DD`; `LocalDate.parse` không cần suy đoán `dd/MM/yyyy`.

```java
record DateRange(LocalDate from, LocalDate to) {
    boolean contains(LocalDate value) {
        return (from == null || !value.isBefore(from))
            && (to == null || !value.isAfter(to));
    }
}
```

Đây là khoảng **bao gồm hai đầu**. Nếu `--from=2026-11-26 --to=2026-11-26`, chỉ các dòng đúng ngày 26-11 được chọn.

Nếu một hệ thống ghi dữ liệu bằng `Instant` hoặc timestamp UTC và cần báo cáo theo ngày của người dùng, phải **chọn `ZoneId` rõ ràng** để chuyển timestamp thành ngày. Không tự cắt mười ký tự đầu của timestamp hoặc phụ thuộc vào timezone mặc định của máy chạy CLI.

### 14.1. Vì sao lọc sau khi parse toàn bộ file?

Trong bản demo, cả `validate` và `report` yêu cầu **mọi dòng trong file hợp lệ**, kể cả dòng ngoài khoảng ngày lọc. Cách này giúp tránh một input hỏng bị che khuất chỉ vì ngày đó không xuất hiện trong báo cáo hiện tại.

Một thiết kế khác có thể cho phép **lưu riêng rejected rows** để dữ liệu tốt tiếp tục được xử lý, nhưng phải có:
- Chính sách chấp nhận lỗi.
- File lỗi/quarantine.
- Số lượng/tỷ lệ dòng bị bỏ.
- Khả năng đối soát.
- Tiêu chí khi nào job bị coi là thất bại.

Không lặng lẽ `catch` mọi exception rồi `continue`.

## 15. Ghi file an toàn hơn: temp file và atomic move

Nếu ghi trực tiếp vào `summary.tsv` bằng `Files.newBufferedWriter(output)`, mặc định tệp có thể bị **truncate ngay khi mở**. Nếu chương trình lỗi giữa chừng, output cũ biến mất và file mới bị thiếu dữ liệu.

Mẫu trong dự án:

```text
Đọc + validate toàn bộ input
            |
            v
Aggregate và sort trong bộ nhớ
            |
            v
Tạo temp trong CÙNG thư mục đích
            |
            v
Ghi báo cáo và đóng writer thành công
            |
            v
Files.move(temp, target, ATOMIC_MOVE, REPLACE_EXISTING)
            |
            +-- Thành công: target mới
            |
            +-- Không hỗ trợ/lỗi: báo lỗi, dọn temp
```

### 15.1. `ATOMIC_MOVE` cung cấp điều gì?

`StandardCopyOption.ATOMIC_MOVE` yêu cầu một thao tác di chuyển **nguyên tử ở tầng filesystem** khi provider hỗ trợ. Ý nghĩa thường mong muốn là observer không thấy file đích đang được viết dở.

Nhưng:
- Không phải mọi filesystem/provider đều hỗ trợ.
- Với `ATOMIC_MOVE`, các option khác (bao gồm `REPLACE_EXISTING`) có thể bị bỏ qua theo contract; việc đích đã tồn tại có được thay thế hay phát sinh lỗi có thể phụ thuộc implementation.
- Không bảo đảm **durability sau mất điện** chỉ vì rename được coi là atomic.
- Không ngăn một process khác đồng thời ghi đè file sau đó.
- Không loại bỏ race condition khi một đường dẫn bị thay đổi bởi process khác.

Bản demo chọn **fail-closed**: không tự fallback sang move không nguyên tử; nếu môi trường không đáp ứng, người dùng nhận lỗi thay vì nhận một cam kết bảo toàn chưa được kiểm chứng.

### 15.2. Không để report ghi đè input

Ứng dụng kiểm tra:

```java
source.equals(target)
    || (Files.exists(target)
        && Files.isSameFile(source, target))
```

Điều này chặn trường hợp hai đường dẫn tuyệt đối chuẩn hóa bằng nhau hoặc hai đường dẫn đang chỉ tới **cùng file hiện hữu** qua alias/hard link.

Đây là **kiểm tra an toàn cho tiện ích CLI tin cậy, không phải hàng rào bảo mật chống TOCTOU**: attacker có quyền thay filesystem đồng thời có thể đổi link/path giữa kiểm tra và move. Nếu xử lý đường dẫn của người dùng không tin cậy trên hệ thống đặc quyền, cần cơ chế sandbox, quyền tối thiểu và thiết kế truy cập tệp chống race chuyên dụng.

### 15.3. Xử lý lỗi khi cleanup

Mã mẫu dùng `finally { Files.deleteIfExists(temporary); }`. Trên một số filesystem, nếu write/move thất bại và cleanup lại thất bại, exception cleanup có thể che lỗi gốc. Khi cần vận hành nghiêm ngặt, hãy bổ sung logic giữ primary exception, gắn suppressed exceptions hoặc ghi nhận cả hai lỗi mà không làm lộ đường dẫn nhạy cảm.

**Không coi thao tác ghi file là transaction database.** Nếu quy trình phải đảm bảo crash consistency, cần thêm chính sách fsync file/directory khi phù hợp, journaling/commit markers hoặc một storage service có atomicity/durability contract đủ mạnh.

## 16. Chạy CLI đúng trên các hệ điều hành

Ví dụ lệnh:

```text
java ExpenseCli.java validate expenses.tsv
java ExpenseCli.java report expenses.tsv output.tsv --from=2026-11-26
```

Nếu đường dẫn chứa khoảng trắng, đặt trong dấu quote:

```text
java ExpenseCli.java report "My Data/expenses.tsv" "My Data/summary.tsv"
```

Điều này áp dụng cho command shell như PowerShell hoặc Bash; ký tự quote giúp shell truyền **một argument** tương ứng với đường dẫn.

### 16.1. Không tự tách `args` bằng dấu cách

Java `main(String[] args)` đã nhận các token từ shell/runtime. Không nối mọi argument rồi dùng `split(" ")`, vì đường dẫn chứa khoảng trắng sẽ bị vỡ.

### 16.2. Lệnh `validate` không ghi bất kỳ báo cáo nào

```text
java ExpenseCli.java validate expenses.tsv
```

Chế độ này hữu ích trước khi đưa dữ liệu vào batch pipeline. Một job scheduler có thể coi exit code `0` là hợp lệ; các mã khác cần được ghi nhận và xử lý theo runbook.

### 16.3. Exit code khác biệt với HTTP status

CLI không có HTTP server. Exit code `1`/`2` thuộc **hợp đồng của chương trình**, không phải mã HTTP. Đừng trả `200` hay `404` từ main như thể đó là response code của một API web.

## 17. Kiểm thử thuần logic bằng JUnit Jupiter

Để test mà không phải chạy subprocess cho mọi trường hợp, các method `load`, `summarize`, `writeReport` và nested records trong ví dụ được để **package-private**. Test đặt cùng package (ở đây là unnamed package khi demo một file).

JUnit Jupiter test minh họa:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ExpenseCliTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void aggregatesByCategory() {
        List<ExpenseCli.Expense> input = List.of(
            new ExpenseCli.Expense(
                "E-1", LocalDate.parse("2026-11-25"),
                "Sách", new BigDecimal("20.00")
            ),
            new ExpenseCli.Expense(
                "E-2", LocalDate.parse("2026-11-26"),
                "Sách", new BigDecimal("5.50")
            ),
            new ExpenseCli.Expense(
                "E-3", LocalDate.parse("2026-11-26"),
                "Đi lại", new BigDecimal("10.00")
            )
        );

        ExpenseCli.Report report = ExpenseCli.summarize(
            input, new ExpenseCli.DateRange(null, null)
        );

        assertEquals(3L, report.selectedRows());
        assertEquals("35.50",
            ExpenseCli.money(report.grandTotal()));
        assertEquals("Sách",
            report.categories().getFirst().category());
        assertEquals("25.50",
            ExpenseCli.money(
                report.categories().getFirst().total()));
    }

    @Test
    void rejectsDuplicateExpenseIds() throws Exception {
        Path input = temporaryDirectory.resolve("duplicate.tsv");
        Files.writeString(input,
            "id\tdate\tcategory\tamount\n"
            + "E-1\t2026-11-25\tSách\t10.00\n"
            + "E-1\t2026-11-26\tSách\t20.00\n",
            StandardCharsets.UTF_8
        );

        IllegalArgumentException ex = assertThrows(
            IllegalArgumentException.class,
            () -> ExpenseCli.load(input)
        );
        assertTrue(ex.getMessage().contains("Line 3"));
    }

    @Test
    void filterIncludesBothBoundaryDates() {
        var range = new ExpenseCli.DateRange(
            LocalDate.parse("2026-11-25"),
            LocalDate.parse("2026-11-26")
        );

        assertTrue(range.contains(
            LocalDate.parse("2026-11-25")));
        assertTrue(range.contains(
            LocalDate.parse("2026-11-26")));
        assertFalse(range.contains(
            LocalDate.parse("2026-11-27")));
    }

    @Test
    void refusesToReplaceInputFile() throws Exception {
        Path input = temporaryDirectory.resolve("input.tsv");
        String original = "id\tdate\tcategory\tamount\n";
        Files.writeString(input, original, StandardCharsets.UTF_8);

        var emptyReport = new ExpenseCli.Report(
            0, 0, BigDecimal.ZERO, List.of()
        );

        assertThrows(IllegalArgumentException.class,
            () -> ExpenseCli.writeReport(
                input, input, emptyReport));

        assertEquals(original,
            Files.readString(input, StandardCharsets.UTF_8));
    }
}
```

### 17.1. Những điểm kiểm thử cần hiểu

- `@TempDir` cho test một directory riêng, giảm nguy cơ đụng file dùng chung.
- `assertThrows` xác nhận **đúng loại lỗi**, không dựa vào stack trace.
- Một test kiểm tra `grandTotal` và thứ tự category theo comparator.
- Test không ghi đè input kiểm tra cả exception lẫn **nội dung file gốc được giữ nguyên**.
- `List.getFirst()` là API chính thức từ Java 21, hợp lệ trên Java 27.
- `ExpenseCliTest` dùng JUnit Jupiter; **JUnit không nằm sẵn trong JDK**, phải cấu hình test dependencies trong build của dự án.

### 17.2. Không giả định mọi filesystem hỗ trợ atomic move

Một integration test ghi output thành công chỉ nên chạy khi môi trường test hỗ trợ contract filesystem được yêu cầu, hoặc test phải xử lý trường hợp `AtomicMoveNotSupportedException` đúng kỳ vọng. **Không coi `ATOMIC_MOVE` là bảo đảm portable** giữa mọi OS/provider.

### 17.3. Test ma trận input lỗi

Ít nhất nên có test cho:
- Header sai, file rỗng, BOM, blank lines.
- Ít/nhiều hơn bốn trường.
- ID rỗng, ID trùng, ID ký tự không hợp lệ.
- Ngày sai hoặc `from > to`.
- Danh mục trống, `"TOTAL"` và ký tự nguy hiểm.
- `amount` âm, 3 chữ số thập phân, exponent, dấu phẩy.
- Input chỉ có header và report rỗng.
- Nhiều dòng cùng category, thứ tự bằng tổng tiền.
- Output trùng input qua alias/hard link nếu môi trường hỗ trợ.
- Directory không tồn tại, thiếu quyền, atomic move không hỗ trợ.

Một số trường hợp như quyền file/atomic move phụ thuộc hệ điều hành, cần integration test được thiết kế riêng, không ép thành unit test thuần.

## 18. Kiểm thử chức năng cuối-cuối và kiểm tra output thực

Unit test của `summarize` **không chứng minh** report thực sự được ghi bằng UTF-8 và đúng TAB. Cần một test end-to-end trên file tạm:

```text
Given:
  expenses.tsv hợp lệ có ba giao dịch thuộc hai category

When:
  chạy report đến summary.tsv

Then:
  exit code = 0
  summary.tsv được tạo
  header đúng thứ tự
  mỗi dòng có ba trường
  tổng tiền bằng tổng của những record đã chọn
  input.tsv không bị thay đổi
```

Các tiêu chí bổ sung:
1. Gọi lại cùng command với cùng input tạo output có **cùng nội dung byte** nếu không có tác nhân ngoài thay đổi.
2. File đầu ra cũ không bị ghi nửa chừng khi input có lỗi ở dòng cuối.
3. Khi error, không còn file tạm bị bỏ lại nếu cleanup thành công.
4. Không có file descriptor hoặc process do test tạo còn sống sau khi kết thúc.
5. Encoding tiếng Việt có dấu được giữ đúng.

Một số kiểm thử chạm filesystem cần cleanup rõ ràng và không nên chạy song song trên cùng path.

## 19. Phức tạp thuật toán và giới hạn bộ nhớ

Gọi:
- `n` là số giao dịch hợp lệ trong input.
- `k` là số category khác nhau.

Với bản demo:

| Giai đoạn | Thời gian ước lượng | Bộ nhớ bổ sung |
| --- | --- | --- |
| Parse `n` dòng + phát hiện ID trùng | Trung bình gần O(n) với hash structures | O(n) records và IDs |
| Lọc theo ngày | O(n) | Tối đa O(n) list kết quả |
| Tổng hợp `Map` | Trung bình O(n) | O(k) |
| Sort category | O(k log k) | O(k) cho list |
| Ghi report | O(k) | Buffer ghi theo dòng |

Đây là **ước lượng cấu trúc thuật toán**, không bảo đảm độ trễ thực: I/O, GC, hash collisions, encoding, độ dài chuỗi và filesystem có thể làm runtime khác đi.

### 19.1. Phương án streaming aggregate cho file lớn

Nếu không cần giữ mỗi `Expense`, có thể cộng dồn khi đọc:

```java
Map<String, BigDecimal> sums = new HashMap<>();

// Trong vòng lặp đã parse và validate từng Expense:
sums.merge(row.category(), row.amount(), BigDecimal::add);
```

Việc này giảm phần nhớ dành cho `List<Expense>` xuống gần O(k) **nếu** không cần lưu mọi record khác. Tuy nhiên, muốn phát hiện **ID trùng chính xác trên toàn file**, vẫn cần một tập ID (O(n)) hoặc một cơ chế khác như:
- Database/index ngoài bộ nhớ.
- External sort theo ID rồi so các phần tử kề nhau.
- Partitioning/hash-on-disk có kiểm soát.
- Một hợp đồng đầu vào đã bảo đảm uniqueness và được kiểm chứng ở tầng khác.

**Không thay exact duplicate detection bằng `HashSet` bỏ đi rồi vẫn tuyên bố uniqueness được bảo đảm.**

### 19.2. Dùng streaming không tự bảo vệ khỏi file độc hại

`BufferedReader.readLine()` có thể phải cấp phát một chuỗi lớn nếu có dòng hàng gigabyte không có newline. Để xử lý file không tin cậy quy mô lớn, cần kích thước file tối đa, parser có **giới hạn độ dài từng record**, và quota CPU/RAM/disk. Chỉ giới hạn số dòng chưa đủ.

## 20. An toàn dữ liệu và filesystem

Một CLI đọc/ghi file có thể được chạy dưới quyền cao hơn dữ liệu người dùng, hoặc đầu vào được tải từ nguồn khác. Khi đó:

- **Không cho phép đường dẫn ra ngoài phạm vi workspace** nếu CLI được nhúng trong một dịch vụ nhiều người dùng.
- Dùng quyền hệ điều hành tối thiểu, không chạy batch xử lý file người dùng với quyền admin/root không cần thiết.
- Không ghi đè input hoặc các file quan trọng; output directory phải nằm trong vùng cho phép.
- Tránh log toàn bộ dữ liệu tài chính, thông tin cá nhân hoặc đường dẫn nhạy cảm.
- Kiểm tra file size, line length, số record và thời gian xử lý.
- Cân nhắc symbolic links, hard links, race conditions và file provider khác nhau.
- Nếu output được mở trong Excel/LibreOffice, tiếp tục kiểm soát formula injection, encoding và định dạng theo hợp đồng.
- Khi dữ liệu đầu vào có nhiều loại currency, không cộng các amount khác currency thành một tổng duy nhất.

### 20.1. Giới hạn dự án: không phải bảng tính

Một TSV file có thể được mở trong chương trình spreadsheet, nhưng nó chỉ là **dữ liệu văn bản**. Nó không có kiểu cột, formula model, validation rule hay transaction guarantee như workbook. Bản demo cố ý hạn chế category, ID và amount để giảm mơ hồ; không tuyên bố phòng mọi rủi ro khi file bị mở bằng phần mềm khác.

### 20.2. Không tin rằng `record` tự vô hiệu hóa input độc hại

`record` là cấu trúc mô hình hóa dữ liệu trong Java, không phải tường lửa. Input vẫn cần parsing, validation, quyền truy cập file, giới hạn tài nguyên và chính sách xử lý lỗi.

## 21. Đóng gói để phân phối

Sau khi code đã được kiểm thử trong dự án, có thể đóng gói thành executable JAR:

```text
mkdir out
javac -encoding UTF-8 -d out ExpenseCli.java
jar --create --file expense-cli.jar --main-class ExpenseCli -C out .
```

Chạy:

```text
java -jar expense-cli.jar validate expenses.tsv
java -jar expense-cli.jar report expenses.tsv summary.tsv
```

Lệnh `jar` lấy **toàn bộ các `.class`** trong thư mục `out`, bao gồm class do compiler tạo cho những nested `record` và `enum`. Vì vậy không chỉ đưa riêng `ExpenseCli.class` vào JAR.

Một số môi trường cần file manifest, module descriptor hoặc quyền truy cập file theo policy riêng. Với project được module hóa, có thể dùng module JAR, `jlink` hoặc `jpackage` khi thực sự cần custom runtime hoặc native installer, nhưng **không cần** cho bài tập CLI một file này.

### 21.1. Đừng nhầm `java ExpenseCli.java` với `java -jar`

- `java ExpenseCli.java ...`: JDK chạy **source-file mode**.
- `javac` rồi `java ExpenseCli ...`: chạy class đã compile.
- `java -jar expense-cli.jar ...`: chạy executable JAR có main class được khai báo.

Trong production deployment nên ghi lại JDK version, checksum artifact và contract CLI; không phải lúc nào cũng chạy source file trực tiếp.

## 22. Mở rộng bài tập theo từng cấp

### Cấp 1 — Thêm tùy chọn lọc category

Ví dụ:

```text
report expenses.tsv summary.tsv --category="Ăn uống"
```

Thiết kế:
1. Cập nhật parse options.
2. Thêm field vào `Options`.
3. Mở rộng predicate lọc.
4. Viết test rỗng và case-sensitive/insensitive rõ.
5. Không phá hợp đồng `--from`, `--to`.

### Cấp 2 — In `top N` category

Thêm `--top=5` với validation số dương. Cần xác định tổng dòng `TOTAL` là:
- Tổng **tất cả** categories được lọc, hay
- Chỉ tổng **top N** categories được xuất?

Nếu không định nghĩa, report có thể gây hiểu lầm.

### Cấp 3 — Hỗ trợ nhiều loại tiền

Thêm component `Currency` hoặc `currencyCode` vào record. Không cộng USD và VND vào một `BigDecimal` duy nhất; nhóm riêng theo currency hoặc quy đổi theo tỷ giá có nguồn thời gian rõ.

### Cấp 4 — Dữ liệu lỗi được cách ly

Cho phép `--rejects=rejected.tsv`, nhưng phải:
- Ghi số dòng lỗi và lý do.
- Định nghĩa số lỗi tối đa được phép.
- Tránh xuất raw dữ liệu nhạy cảm tùy tiện.
- Quy định atomicity giữa report và rejects file.
- Có test khi một trong hai output ghi thất bại.

### Cấp 5 — Parser CSV thật

Thay parser TSV đơn giản bằng một thư viện parser hỗ trợ quoting, escaped delimiters và newline trong field. **Không tự thay `split("\t", -1)` thành `split(",")` rồi gọi đó là CSV chuẩn.**

### Cấp 6 — Xử lý nhiều file

Có thể đọc directory bằng `Files.list`/`Files.walk`, nhưng nhớ:
- Đóng stream trả về trong `try-with-resources`.
- Quy định thứ tự file (sort nếu cần deterministic).
- Loại bỏ file đầu ra của chính job khỏi tập input.
- Kiểm soát symbolic links và directory traversal.
- Xác định uniqueness của ID **trên từng file hay toàn batch**.

## 23. Các lỗi thường gặp khi thực hành

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `double` để lưu tiền | Sai số thập phân | `BigDecimal` từ string |
| Gọi `split(",")` cho CSV thật | Hỏng trường quoted | Parser CSV có contract |
| Tin default charset luôn tương thích file | Lỗi dấu tiếng Việt | Chỉ định UTF-8 và input contract |
| Không dùng `-1` trong `split` | Mất trường rỗng cuối | `split("\t", -1)` |
| Bỏ qua dòng lỗi | Báo cáo thiếu dữ liệu âm thầm | Fail-fast hoặc rejects policy |
| Dùng `HashMap` làm thứ tự output | Kết quả không ổn định | Sort bằng comparator |
| Dùng mutable collection trong record mà không copy | Bị sửa state từ bên ngoài | `List.copyOf` hoặc ownership rõ |
| Dùng `BigDecimal.equals` để so value | `1.0` khác `1.00` do scale | `compareTo` khi so giá trị số |
| Ghi trực tiếp vào output cũ | Có thể truncate trước khi job hoàn tất | Temp file + rename có kiểm tra |
| Mặc định `ATOMIC_MOVE` hỗ trợ mọi FS | Lỗi trên provider khác | Fail-closed hoặc policy fallback rõ |
| Không kiểm output trùng input | Làm hỏng nguồn | Normalize path và `isSameFile` |
| Đọc hết file nhiều GB vào `List` | OOM | Streaming aggregate, giới hạn tài nguyên |
| Không giới hạn dòng quá dài | Memory exhaustion | Bounded parser và file-size quota |
| Bỏ `try-with-resources` | Rò rỉ file handle | Đóng reader/writer/stream |
| Để báo cáo mở ra chạy formula ngoài ý muốn | Rủi ro spreadsheet injection | Giới hạn/escape dữ liệu theo output format |
| Lọc ngày bằng substring | Sai ISO/timezone khi input khác | `LocalDate` và `DateTimeFormatter` hợp đồng |
| Dùng `LocalDate.now()` trong kết quả | Non-deterministic | Truyền ngày/Clock rõ khi cần |
| Test dùng chung file path | Flaky khi chạy song song | `@TempDir` và fixture riêng |
| Đưa mỗi `ExpenseCli.class` vào JAR | Thiếu nested record/enum classes | Đóng gói tất cả compiled classes |

## 24. Checklist trước khi coi ứng dụng hoàn thành

1. [ ] Dữ liệu đầu vào có **format và encoding rõ ràng**?
2. [ ] Header, số cột, ngày, category, ID, amount đều được validate?
3. [ ] Không có duplicate ID bị bỏ qua?
4. [ ] Dùng `record` cho những thực thể dữ liệu phù hợp?
5. [ ] Hiểu `record` chỉ bảo đảm shallow immutability?
6. [ ] Chọn `List`, `Set`, `Map` đúng mục đích?
7. [ ] Có quy định stable sorting cho report?
8. [ ] Dùng `BigDecimal` và chính sách scale/currency rõ?
9. [ ] Lọc `from`/`to` nhất quán, inclusive nếu đã công bố?
10. [ ] Trả exit code khác `0` khi input/I/O lỗi?
11. [ ] Lỗi parser có chỉ ra số dòng và lý do?
12. [ ] Có kiểm report không ghi đè input?
13. [ ] Không ghi output dở dang nếu input sai?
14. [ ] Có chủ đích khi FS không hỗ trợ atomic move?
15. [ ] Reader, writer và stream được đóng đúng scope?
16. [ ] Có giới hạn kích thước/file/record phù hợp nguồn dữ liệu?
17. [ ] Có test Unicode, BOM, dòng trống, tiền âm và ID trùng?
18. [ ] Unit tests và integration tests được phân chia rõ?
19. [ ] Tệp đầu ra giữ đúng TAB, UTF-8 và tổng tiền?
20. [ ] Có hướng dẫn biên dịch, chạy và đóng gói JAR?
21. [ ] Không lẫn code từ JDK preview hoặc hướng dẫn đã lỗi thời?
22. [ ] Có quy trình chạy dưới quyền file tối thiểu và bảo vệ dữ liệu nhạy cảm?

**Kết luận:** một ứng dụng CLI xử lý tệp bằng Java 27 tốt là một đường đi rõ ràng từ **byte dữ liệu → giá trị đã được kiểm tra → `record` → collection/aggregation → output an toàn**. `record` làm mô hình dữ liệu ngắn gọn, `Set` giúp kiểm tra uniqueness, `Map` hỗ trợ tổng hợp, `List` và comparator cho output ổn định, còn `Files` cùng `try-with-resources` quản lý ranh giới I/O. Khi kích thước dữ liệu và mức độ tin cậy nguồn tăng, bước tiếp theo là bổ sung parser/streaming/bounded resource policies chứ không chỉ tăng heap.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — `Record`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html): record là data carrier shallowly immutable, các thành phần do compiler sinh.
- [Java SE 27 API — `Files`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): buffered reading/writing, `lines`, `move`, `ATOMIC_MOVE`, lỗi encoding và I/O.
- [Java SE 27 API — `Path`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): path semantics, normalize và absolute path.
- [Java SE 27 API — `StandardCopyOption`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/StandardCopyOption.html): `ATOMIC_MOVE`, `REPLACE_EXISTING`.
- [Java SE 27 API — `BigDecimal`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html): toán học số thập phân và scale.
- [Java SE 27 API — `RoundingMode`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/RoundingMode.html): chính sách làm tròn/từ chối làm tròn.
- [Java SE 27 API — `LocalDate`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html): ngày ISO, parse và so sánh.
- [Java SE 27 API — `List`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): collections, `copyOf`, unmodifiable list và sequenced operations.
- [Java SE 27 API — `Map`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): grouping, `merge`, `computeIfAbsent`.
- [Java SE 27 API — `Set`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): unique IDs.
- [Java SE 27 API — `Comparator`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): stable order của report.
- [Java SE 27 API — `Stream`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): filter, sort, `toList`, terminal operations.
- [Java SE 27 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và các charset tiêu chuẩn.
- [Java SE 27 — `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): source-file mode và CLI execution.
- [Java SE 27 — `javac` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): biên dịch Java source.
- [Java SE 27 — `jar` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html): đóng gói executable JAR.
- [JUnit User Guide — JUnit Jupiter](https://docs.junit.org/current/user-guide/): `@Test`, assertions và `@TempDir` cho kiểm thử.
