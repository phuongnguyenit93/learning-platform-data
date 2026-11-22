# Hoàn thiện ví dụ tích hợp Java I/O và kiểm thử các nhánh thất bại

## 1. Mục tiêu và tiêu chí hoàn thành

Bài thực hành tích hợp các thành phần đã học của Java I/O/NIO.2 thành một luồng xử lý có thể chạy và kiểm tra được: **đọc byte → giải mã UTF-8 → đọc theo dòng → xác thực dữ liệu → tính toán → ghi tệp tạm → đưa kết quả vào vị trí đích**. Ngoài luồng thành công, mỗi điểm có khả năng thất bại đều phải có một kiểm thử cho thấy lỗi được phát hiện, tài nguyên được đóng và kết quả hợp lệ cũ được giữ nguyên khi chưa tới bước hoàn tất.

Sau bài này, bạn cần giải thích được sự khác biệt giữa lỗi định dạng dữ liệu và lỗi I/O, vai trò của `try-with-resources`, lý do không ghi trực tiếp đè lên báo cáo cũ, cách tạo lỗi giả lập có kiểm soát và cách kiểm thử **cả ngoại lệ lẫn trạng thái tệp sau ngoại lệ**.

**Đề bài mẫu:** Đọc tệp UTF-8 `orders.csv` có hai cột `id,quantity`, tính số bản ghi và tổng số lượng, xuất `report.txt` chứa `records=...` và `totalQuantity=...`. Bài dùng **CSV đơn giản có chính xác một dấu phẩy mỗi dòng**, không hỗ trợ trường trong dấu nháy hoặc dấu phẩy nằm trong giá trị; hệ thống CSV thực tế cần parser chuyên dụng.

Quy ước dữ liệu: dòng đầu tiên phải chính xác `id,quantity` (không BOM); mỗi dòng tiếp theo phải có ID khớp `[A-Za-z][A-Za-z0-9_-]{0,31}`, ID không trùng, `quantity` là số nguyên `long` dương. Dòng trống, số không hợp lệ, số âm/0, ID trùng, dữ liệu UTF-8 lỗi hoặc tổng bị tràn đều làm thao tác thất bại. Tệp chỉ có header là hợp lệ và tạo báo cáo 0 bản ghi, tổng 0.

Ví dụ đầu vào:

```csv
id,quantity
apple,2
banana,7
```

Kết quả nội dung `report.txt`:

```text
records=2
totalQuantity=9
```

## 2. Thiết kế luồng và ranh giới trách nhiệm

1. `generate` nhận `Path` đầu vào/đầu ra, không cho dùng cùng một tệp và điều phối hai pha.
2. `parse` sử dụng `Files.newInputStream`, `InputStreamReader` với bộ giải mã UTF-8 ở chế độ `REPORT`, rồi `BufferedReader` để xử lý tuần tự. Toàn bộ phân tích và kiểm tra diễn ra **trước khi tạo báo cáo mới**.
3. `writeSafely` viết kết quả ra tệp tạm trong **cùng thư mục** với đích, đóng writer trước khi di chuyển; dùng `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)` để yêu cầu đổi tên nguyên tử nếu hệ thống tệp hỗ trợ. Không hỗ trợ atomic move thì trả lỗi rõ ràng, không âm thầm chuyển sang thao tác kém bảo đảm hơn.
4. `finally` xóa tệp tạm nếu nó còn tồn tại. `BeforeCommit` là điểm chèn lỗi dành cho kiểm thử, giúp ép luồng lỗi ngay sau khi ghi tệp tạm mà không lệ thuộc vào quyền tệp/hệ điều hành.
5. Bộ kiểm thử dùng thư mục tạm độc lập cho mỗi ca và xóa sau khi chạy. Assertions xác minh giá trị đầu ra, **loại lỗi mong đợi** và tác động lên tệp cũ/tệp tạm.

Trong ví dụ đơn luồng này, “an toàn” có nghĩa là **không cố ý thay báo cáo cũ trước khi dữ liệu mới được đọc, kiểm tra và ghi xong**; tính nguyên tử của bước đổi tên phải được hệ thống tệp bảo đảm. Đây không phải cơ chế giao dịch nhiều tệp, chống ghi đồng thời hoặc bảo đảm dữ liệu đã được đồng bộ vật lý xuống thiết bị lưu trữ.

## 3. Mã hoàn chỉnh: Java 17 trở lên

Lưu toàn bộ chương trình bên dưới trong **`IntegratedIoDemo.java`** (một tệp, không dùng thư viện bên thứ ba). `Summary` dùng `record`, các hàm kiểm thử nằm cùng lớp để chạy trực tiếp bằng JDK.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class IntegratedIoDemo {
    record Summary(int records, long totalQuantity) {}

    static final class DataFormatException extends IOException {
        DataFormatException(String message) { super(message); }
        DataFormatException(String message, Throwable cause) { super(message, cause); }
    }

    @FunctionalInterface
    interface BeforeCommit {
        void run(Path temporaryFile) throws IOException;
    }

    static void generate(Path input, Path output) throws IOException {
        generate(input, output, temporaryFile -> {});
    }

    static void generate(Path input, Path output, BeforeCommit beforeCommit)
            throws IOException {
        Path target = output.toAbsolutePath().normalize();
        if (Files.exists(input) && Files.exists(target)
                && Files.isSameFile(input, target)) {
            throw new IOException("Input and output must be different files");
        }
        Summary summary = parse(input);
        writeSafely(target, summary, beforeCommit);
    }

    private static Summary parse(Path input) throws IOException {
        Set<String> seenIds = new HashSet<>();
        int records = 0;
        long total = 0;

        // Stream bytes -> strict UTF-8 decoding -> buffered text lines.
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                Files.newInputStream(input),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)))) {
            if (!"id,quantity".equals(reader.readLine())) {
                throw new DataFormatException("Line 1: expected id,quantity header");
            }
            String line;
            int lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                String[] fields = line.split(",", -1);
                if (fields.length != 2
                        || !fields[0].matches("[A-Za-z][A-Za-z0-9_-]{0,31}")) {
                    throw new DataFormatException("Line " + lineNumber + ": invalid CSV row");
                }
                long quantity;
                try {
                    quantity = Long.parseLong(fields[1]);
                } catch (NumberFormatException error) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": quantity is not a long", error);
                }
                if (quantity <= 0) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": quantity must be positive");
                }
                if (!seenIds.add(fields[0])) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": duplicate id " + fields[0]);
                }
                try {
                    total = Math.addExact(total, quantity);
                    records = Math.incrementExact(records);
                } catch (ArithmeticException error) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": aggregate overflow", error);
                }
            }
        }
        return new Summary(records, total);
    }

    private static void writeSafely(Path output, Summary result,
                                    BeforeCommit beforeCommit) throws IOException {
        Path parent = output.getParent();
        if (!Files.isDirectory(parent)) {
            throw new IOException("Output parent directory does not exist: " + parent);
        }
        if (Files.isDirectory(output)) {
            throw new IOException("Output is a directory: " + output);
        }

        // A temp file in the same directory enables an atomic rename where supported.
        Path temporary = Files.createTempFile(parent, ".report-", ".tmp");
        try {
            try (BufferedWriter writer = Files.newBufferedWriter(temporary,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING)) {
                writer.write("records=" + result.records());
                writer.newLine();
                writer.write("totalQuantity=" + result.totalQuantity());
                writer.newLine();
            }
            beforeCommit.run(temporary); // Inject a failure here in a test.
            try {
                Files.move(temporary, output,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                throw new IOException("Atomic move unsupported; output not replaced", error);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    @FunctionalInterface
    interface TestCase { void run(Path directory) throws Exception; }

    @FunctionalInterface
    interface ThrowingAction { void run() throws Exception; }

    static <T extends Throwable> T expect(Class<T> expected, ThrowingAction action)
            throws Exception {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) return expected.cast(actual);
            throw new AssertionError("Expected " + expected.getSimpleName()
                    + ", got " + actual, actual);
        }
        throw new AssertionError("Expected " + expected.getSimpleName());
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void test(String name, TestCase body) throws Exception {
        Path directory = Files.createTempDirectory("io-lab-");
        try {
            body.run(directory);
            System.out.println("PASS " + name);
        } finally {
            try (Stream<Path> paths = Files.walk(directory)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    static Path input(Path directory, String contents) throws IOException {
        Path path = directory.resolve("orders.csv");
        Files.writeString(path, contents, StandardCharsets.UTF_8);
        return path;
    }

    static void runTests() throws Exception {
        test("success", dir -> {
            Path source = input(dir, "id,quantity\napple,2\nbanana,7\n");
            Path result = dir.resolve("report.txt");
            generate(source, result);
            check(Files.readAllLines(result, StandardCharsets.UTF_8)
                    .equals(List.of("records=2", "totalQuantity=9")), "wrong report");
        });
        test("missing-input", dir -> {
            expect(NoSuchFileException.class,
                    () -> generate(dir.resolve("missing.csv"), dir.resolve("out.txt")));
        });
        test("bad-header", dir -> {
            Path source = input(dir, "wrong,header\na,1\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("bad-row", dir -> {
            Path source = input(dir, "id,quantity\na,nope\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("duplicate-id", dir -> {
            Path source = input(dir, "id,quantity\na,1\na,2\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("sum-overflow", dir -> {
            Path source = input(dir,
                    "id,quantity\na,9223372036854775807\nb,1\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("malformed-utf8", dir -> {
            Path source = dir.resolve("orders.csv");
            Files.write(source, new byte[] {(byte) 0xC3, (byte) 0x28});
            expect(MalformedInputException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("output-is-directory", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            Path result = Files.createDirectory(dir.resolve("out.txt"));
            expect(IOException.class, () -> generate(source, result));
            check(Files.isDirectory(result), "directory changed");
        });
        test("old-report-survives-bad-input", dir -> {
            Path source = input(dir, "id,quantity\na,0\n");
            Path result = dir.resolve("out.txt");
            Files.writeString(result, "KEEP", StandardCharsets.UTF_8);
            expect(DataFormatException.class, () -> generate(source, result));
            check("KEEP".equals(Files.readString(result)), "old output changed");
        });
        test("failure-before-commit", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            Path result = dir.resolve("out.txt");
            Files.writeString(result, "KEEP", StandardCharsets.UTF_8);
            expect(IOException.class, () -> generate(source, result,
                    temporary -> { throw new IOException("injected failure"); }));
            check("KEEP".equals(Files.readString(result)), "old output changed");
            try (Stream<Path> files = Files.list(dir)) {
                check(files.noneMatch(p -> p.getFileName().toString()
                        .startsWith(".report-")), "temporary file leaked");
            }
        });
        test("same-input-and-output", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            expect(IOException.class, () -> generate(source, source));
            check(Files.readString(source).contains("a,1"), "input changed");
        });
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            runTests();
        } else if (args.length == 2) {
            generate(Path.of(args[0]), Path.of(args[1]));
            System.out.println("Created report: " + args[1]);
        } else {
            throw new IllegalArgumentException(
                    "Usage: java IntegratedIoDemo [input.csv output.txt]");
        }
    }
}
```

## 4. Biên dịch, chạy và quan sát kết quả

Trong thư mục chứa tệp Java, thực hiện:

```bash
javac -encoding UTF-8 IntegratedIoDemo.java
java IntegratedIoDemo
```

Với hệ thống tệp hỗ trợ atomic rename, chương trình in đúng 11 dòng sau (đã chạy kiểm tra trên JDK 21 với mã Java 17 tương thích):

```text
PASS success
PASS missing-input
PASS bad-header
PASS bad-row
PASS duplicate-id
PASS sum-overflow
PASS malformed-utf8
PASS output-is-directory
PASS old-report-survives-bad-input
PASS failure-before-commit
PASS same-input-and-output
```

Muốn chạy như công cụ thật, tạo tệp `orders.csv` từ ví dụ ở mục 1, rồi chạy:

```bash
java IntegratedIoDemo orders.csv report.txt
```

Lệnh này báo `Created report: report.txt` khi thành công. Nội dung tệp báo cáo giống ví dụ; ký tự xuống dòng của tệp phụ thuộc nền tảng nhưng `Files.readAllLines` kiểm tra nội dung theo dòng, tránh gắn kiểm thử với CRLF/LF.

## 5. Ma trận kiểm thử nhánh thành công và thất bại

| Ca kiểm thử | Kích hoạt | Kết quả cần chứng minh |
|---|---|---|
| `success` | Dữ liệu đúng, hai bản ghi | Có báo cáo `records=2`, `totalQuantity=9` |
| `missing-input` | Đường dẫn nguồn không có tệp | `NoSuchFileException`; không tạo kết quả |
| `bad-header` | Header không chính xác | `DataFormatException` với vị trí dòng đầu |
| `bad-row` | Số lượng `nope` | `DataFormatException` thay vì bỏ qua dòng |
| `duplicate-id` | ID `a` xuất hiện hai lần | Phát hiện ID lặp và dừng |
| `sum-overflow` | Tổng vượt `Long.MAX_VALUE` | `Math.addExact` phát hiện tràn, không cho báo cáo sai |
| `malformed-utf8` | Byte `C3 28` không tạo chuỗi UTF-8 hợp lệ | `MalformedInputException` từ decoder ở chế độ `REPORT` |
| `output-is-directory` | Đường dẫn đích là thư mục | Trả `IOException`; thư mục còn nguyên |
| `old-report-survives-bad-input` | Báo cáo cũ là `KEEP`, dữ liệu mới sai | Báo cáo cũ vẫn đúng từng ký tự |
| `failure-before-commit` | Hook ném `IOException` sau khi đã đóng writer | Báo cáo cũ vẫn là `KEEP`; không còn tệp `.report-*.tmp` |
| `same-input-and-output` | Trỏ nguồn và đích tới một tệp | Từ chối xử lý; nguồn không bị ghi đè |

**Vì sao cần xác minh trạng thái sau lỗi?** Chỉ kiểm tra `expect(IOException.class, ...)` là chưa đủ: một chương trình vẫn có thể ném ngoại lệ *sau khi đã làm hỏng output*. Hai ca `old-report-survives-bad-input` và `failure-before-commit` kiểm tra trực tiếp tính bất biến của dữ liệu cũ; ca sau kiểm tra thêm cleanup. Việc tạo thư mục tạm cho mỗi test khiến kết quả ít phụ thuộc trạng thái còn sót từ lần chạy khác.

## 6. Cơ chế xử lý lỗi và vòng đời tài nguyên

**Đường đọc:** `Files.newInputStream` có thể ném `NoSuchFileException`, `AccessDeniedException` hoặc các `IOException` khác. `InputStreamReader` đổi byte thành ký tự bằng decoder chỉ định; chế độ `REPORT` bảo đảm byte UTF-8 sai bị báo thay vì thay thầm bằng ký tự `�`. `BufferedReader.readLine()` tiện cho dữ liệu theo dòng nhưng không thích hợp khi cần giữ nguyên ký tự xuống dòng hoặc xử lý bản ghi nhiều dòng. Đóng `BufferedReader` trong `try-with-resources` đóng luôn reader bên trong và input stream, kể cả khi parser ném lỗi.

**Đường kiểm tra:** `DataFormatException extends IOException` biểu diễn nội dung đầu vào không đáp ứng hợp đồng, với số dòng có thể dùng để chẩn đoán. `Long.parseLong` xử lý lỗi văn bản/số vượt phạm vi; `Math.addExact` và `Math.incrementExact` ngăn tràn khi cộng dồn. `Set` phát hiện ID trùng. Bài chọn chính sách **fail fast**: chỉ một dòng sai đã làm cả lượt xử lý thất bại; không tạo báo cáo một phần. Nếu nghiệp vụ muốn gom nhiều lỗi để trả về cùng lúc, phải thiết kế kết quả validation riêng.

**Đường ghi:** Ghi vào `output` trực tiếp bằng `TRUNCATE_EXISTING` có thể xóa nội dung cũ trước khi lỗi xảy ra. Tệp tạm cùng thư mục giảm nguy cơ đổi tên xuyên hệ thống tệp. Writer được đóng trước `move`; nếu hook ném lỗi, `finally` dọn tệp tạm. Nếu rename nguyên tử không được hỗ trợ, phương thức phát sinh `IOException` bọc `AtomicMoveNotSupportedException`. Với `ATOMIC_MOVE`, cách xử lý đích đã tồn tại có khác biệt theo provider; cần kiểm chứng trên hệ thống tệp triển khai, và lỗi truy cập/quyền ghi không nên được nuốt rồi coi như thành công.

**Lưu ý giới hạn thực tế:** Ví dụ không theo dõi dung lượng đĩa/quota, không gọi `FileChannel.force` để tăng bảo đảm bền vững sau mất điện, không giải quyết nhiều tiến trình cùng cập nhật báo cáo và không bảo vệ khỏi thay đổi đường dẫn/symlink giữa lúc kiểm tra và ghi. Ở dịch vụ thật, bổ sung giới hạn kích thước file, chính sách path/permission, log có ngữ cảnh và cơ chế khóa/phối hợp khi cần. Không dùng `catch (Exception) { }`, không làm mất nguyên nhân lỗi trong lúc chuyển thành `DataFormatException`.

## 7. Tự đánh giá kết quả và mở rộng có kiểm soát

Một bài hoàn chỉnh cần đạt đồng thời: chạy xanh ca hợp lệ; mỗi nhánh sai thất bại theo đúng loại/nhóm ngoại lệ; nội dung hợp lệ cũ còn nguyên khi validation hoặc hook lỗi; không rò rỉ temp; input/output khác nhau; file handle được đóng; output không được công bố trước bước commit.

Để kiểm tra hiểu sâu, hãy chủ động đổi một ca test thành lượng `0` hoặc `-1`, một dòng thiếu dấu phẩy, thêm dấu phẩy thứ hai, một header rỗng, một ID không hợp lệ và một output parent chưa tồn tại: xác định lỗi do pha parse hay pha write, và vì sao. Thử đổi decoder sang chính sách `REPLACE` để thấy lý do cần chế độ strict khi chất lượng dữ liệu có ý nghĩa. Khi đưa sang CI, có thể chuyển các kiểm thử thành JUnit 5 với `@TempDir`, `assertThrows` và `assertEquals`; giữ nguyên các assertion về dữ liệu và cleanup.

Phần quan trọng của thực hành là **chứng minh hành vi khi thất bại**, không chỉ chứng minh một đường chạy thành công.