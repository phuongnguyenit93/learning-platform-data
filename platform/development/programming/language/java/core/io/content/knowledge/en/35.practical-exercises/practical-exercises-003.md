# Đọc file lớn theo dòng và thống kê dữ liệu trong Java

Khi xử lý log, dữ liệu giao dịch, kết quả đo hoặc một file CSV có dung lượng hàng trăm MB đến nhiều GB, cách làm `Files.readAllLines(path)` rồi duyệt danh sách có thể tạo áp lực heap rất lớn: mỗi dòng là một chuỗi, còn có danh sách tham chiếu, đối tượng trung gian và chi phí giải mã. Đa số bài toán thống kê **không cần giữ toàn bộ dòng trong bộ nhớ**. Chúng chỉ cần đọc từng dòng, kiểm tra bản ghi rồi cập nhật vài bộ đếm, tổng, giá trị nhỏ nhất/lớn nhất hoặc thống kê theo nhóm.

Bài thực hành này hướng dẫn đọc một file lớn theo dòng bằng `BufferedReader` và `Files.lines()`, thiết kế phép thống kê theo kiểu **streaming / one-pass**, xử lý dòng lỗi, encoding, tràn số, tài nguyên và hiệu năng. Một chương trình Java 17 hoàn chỉnh sẽ đọc dữ liệu định dạng `level,durationMs`, đếm các bản ghi hợp lệ/không hợp lệ, số lượng theo mức log, tổng, min, max, average mà không tạo danh sách tất cả dòng.

**Mục tiêu:** Chi phí bộ nhớ chủ yếu phụ thuộc kích thước **dòng lớn nhất** và lượng trạng thái thống kê đang giữ, không tỷ lệ tuyến tính với tổng số dòng nếu chỉ lưu các bộ đếm và nhóm cố định.

## 1. Phân biệt đọc toàn bộ file với đọc từng dòng

| Cách đọc | Hành vi | Phù hợp |
| --- | --- | --- |
| `Files.readString(path)` | Đọc nội dung file thành một `String` | File nhỏ, cần nội dung nguyên vẹn trong RAM |
| `Files.readAllLines(path, charset)` | Đọc tất cả dòng và tạo `List<String>` | File nhỏ/vừa, muốn truy cập lại mọi dòng |
| `Files.newBufferedReader(path, charset)` | Đọc tuần tự bằng `BufferedReader.readLine()` | File lớn, xử lý từng dòng, kiểm soát luồng và lỗi |
| `Files.lines(path, charset)` | Trả về `Stream<String>` lười, đọc khi terminal operation chạy | Xử lý pipeline filter/map, vẫn phải đóng stream |
| `FileChannel.read(ByteBuffer)` | Đọc các khối byte, **không tự tách dòng hoặc giải mã charset** | Giao thức nhị phân, parser tùy biến hoặc cần kiểm soát byte buffer |

Đối với file văn bản lớn, `BufferedReader` là điểm khởi đầu tốt: dễ quản lý dòng, xử lý ngoại lệ checked `IOException`, kiểm soát vòng đời. `Files.lines()` hợp lý khi pipeline rõ ràng và không vô tình gom mọi dòng vào bộ nhớ bằng `collect(toList())`.

Độ lớn file **không đồng nghĩa** với việc phải dùng `MappedByteBuffer` hoặc tự viết bộ giải mã byte: streaming text qua `BufferedReader` thường đủ đúng, dễ bảo trì và dễ benchmark.

## 2. Bộ dữ liệu đầu vào và yêu cầu thống kê

Giả sử mỗi dòng dữ liệu là một bản ghi có hai cột, phân cách bởi dấu phẩy:

```text
level,durationMs
INFO,120
WARN,300
ERROR,450
INFO,80
WARN,200
broken
INFO,-1
ERROR,150
```

Quy tắc nghiệp vụ của bài thực hành:

1. Dòng đầu tiên **phải đúng** `level,durationMs`, là header và không tính vào thống kê.
2. Mỗi dòng tiếp theo phải có đúng một dấu phẩy, hai trường không rỗng.
3. `level` thuộc ba giá trị `INFO`, `WARN`, `ERROR`; so khớp phân biệt chữ hoa/thường sau khi bỏ khoảng trắng đầu/cuối mỗi trường.
4. `durationMs` phải là số nguyên kiểu `long` **không âm**.
5. Dòng không hợp lệ được **đếm vào `invalid`** và bỏ qua khi tính tổng/min/max/trung bình. Không bỏ cả file vì một dòng bẩn.
6. Các chỉ số cần in: tổng số dòng dữ liệu, valid, invalid, số dòng của từng level, tổng thời lượng, min, max, average.
7. File có thể rất lớn; chương trình không lưu `List<String>`, không giữ toàn bộ bản ghi hợp lệ và không cần tạo file trung gian.

Với dữ liệu mẫu: có **8 dòng dữ liệu**, 6 dòng hợp lệ, 2 dòng không hợp lệ (`broken` và `INFO,-1`). Mỗi level có 2 dòng hợp lệ; tổng thời lượng là **1300 ms**, min **80 ms**, max **450 ms**, trung bình **1300 / 6 = 216,67 ms**.

Đây là **CSV đơn giản do bài thực hành quy định**, **không phải parser CSV tổng quát theo RFC 4180**: nó không hỗ trợ dấu phẩy nằm trong field được quote, newline bên trong field hoặc quy tắc escape. Khi xử lý CSV thực tế có quoted fields, dùng một parser CSV chuyên dụng hoặc triển khai state machine có giới hạn tài nguyên, không sử dụng `split(",")` một cách mù quáng.

## 3. BufferedReader.readLine(): đọc dòng mà không gom cả file

Mẫu cơ bản:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("events.csv");

try (BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý ngay từng line, cập nhật các accumulator.
    }
}
```

Đây là **đoạn minh họa**: file đầu vào cần tồn tại và ứng dụng phải xử lý `IOException`; code chưa có phương thức `main`. Điểm chính:

- `readLine()` trả về một chuỗi chứa nội dung dòng, **không gồm ký tự kết thúc dòng**; hoặc `null` khi kết thúc file.
- Các dạng xuống dòng thông dụng như LF (`\n`), CRLF (`\r\n`) và CR được nhận diện làm dấu kết thúc dòng theo hợp đồng `BufferedReader`.
- **Dòng rỗng là `""`, không phải `null`.** Nếu dữ liệu có dòng rỗng, cần quyết định bỏ qua, đếm lỗi hay coi là bản ghi trống.
- `readLine()` có thể ném `IOException`, ví dụ lỗi thiết bị hoặc decode input không hợp lệ.
- `try-with-resources` đóng reader ngay cả khi vòng xử lý dừng vì lỗi. Nó cũng đóng stream bên dưới do `Files.newBufferedReader()` tạo.

**Cần phân biệt “không nạp cả file” với “giới hạn tuyệt đối RAM”.** `readLine()` phải tạo chuỗi cho **toàn bộ một dòng**. Nếu file có **một dòng dài hàng GB** mà không có newline, chương trình vẫn có nguy cơ thiếu bộ nhớ. Đọc theo dòng an toàn về bộ nhớ **khi độ dài từng dòng được kiểm soát**; với đầu vào không tin cậy phải có parser có giới hạn số ký tự/byte trước khi dựng chuỗi quá dài.

### Mã hóa ký tự và charset

Dùng charset rõ ràng:

```java
Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

Không dựa vào default charset khi file là dữ liệu chia sẻ giữa máy. Một file thực tế có thể dùng UTF-8, UTF-16 hoặc encoding khác; **chỉ định đúng encoding của nguồn**. `UTF-8 BOM` ở đầu file có thể xuất hiện trong nội dung đọc như ký tự `\uFEFF`, khiến kiểm tra header bằng `equals()` thất bại. Nếu quy ước chấp nhận BOM, xử lý rõ ràng đúng **đầu file**, không tự xóa ký tự đầu của mọi dòng.

## 4. One-pass aggregation: giữ trạng thái nhỏ và cập nhật tăng dần

Thay vì:

```java
List<String> lines = Files.readAllLines(path);
long valid = lines.stream().filter(...).count();
```

(đoạn này chỉ minh họa anti-pattern, `...` không phải Java code chạy được), hãy duy trì accumulator:

```text
rows           = 0      // Tổng số dòng sau header
valid          = 0      // Số dòng được chấp nhận
invalid        = 0      // Số dòng bị loại
sumDurationMs  = 0      // Tổng thời lượng hợp lệ
minDurationMs  = +∞     // Min của các dòng hợp lệ
maxDurationMs  = -∞     // Max của các dòng hợp lệ
count[INFO]    = 0
count[WARN]    = 0
count[ERROR]   = 0
```

Với mỗi dòng:

1. Tăng `rows`.
2. Kiểm tra số cột, level và duration.
3. Nếu sai: tăng `invalid`, xử lý dòng kế tiếp.
4. Nếu đúng: tăng `valid`, tăng bộ đếm level, cộng duration vào tổng, cập nhật min/max.
5. Khi tới EOF: tính average nếu `valid > 0`; nếu không có dòng hợp lệ, dùng `n/a` để tránh chia cho 0.

**Không cần biết trước tổng số dòng hoặc dung lượng file** để tính các thống kê này. Với ba level cố định, số bộ đếm cũng cố định. Chi phí thời gian gần tương ứng tổng số ký tự/byte được đọc cộng chi phí parse, còn bộ nhớ không phải một `List` phình to cùng kích thước file.

### Tràn số và độ chính xác

Không nên dùng `int` cho tổng duration khi file có thể chứa hàng triệu bản ghi. Dùng `long` và nếu tổng có thể vượt `Long.MAX_VALUE`, kiểm tra bằng `Math.addExact()` (ném `ArithmeticException` khi overflow) hoặc dùng `BigInteger` nếu nghiệp vụ thực sự cần dải số lớn hơn.

Với trung bình:

```java
double average = valid == 0 ? Double.NaN
        : (double) sumDurationMs / valid;
```

Đây là công thức minh họa, biến phải khai báo ở context ứng dụng. `double` phù hợp cho báo cáo trung bình; nếu là tiền hoặc nghiệp vụ cần decimal precision tuyệt đối, dùng `BigDecimal` với chính sách làm tròn. Không cộng giá trị `long` vào `int` rồi mong phép chia cuối sửa được overflow đã xảy ra.

## 5. Chương trình Java 17 hoàn chỉnh: thống kê file lớn bằng một lượt đọc

Tạo file **`LargeFileStatsDemo.java`**. Nếu chạy **không có đối số**, chương trình tạo dữ liệu mẫu trong file tạm, phân tích và xóa file mẫu. Nếu truyền **một đường dẫn**, chương trình đọc file đó và **không sửa/xóa file do người dùng chỉ định**.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class LargeFileStatsDemo {
    private LargeFileStatsDemo() {}

    private enum Level { INFO, WARN, ERROR }

    private static final class Stats {
        long rows;
        long valid;
        long invalid;
        long sumMs;
        long minMs = Long.MAX_VALUE;
        long maxMs = Long.MIN_VALUE;
        final long[] byLevel = new long[Level.values().length];

        void accept(Level level, long durationMs, long lineNumber)
                throws IOException {
            try {
                sumMs = Math.addExact(sumMs, durationMs);
                valid = Math.incrementExact(valid);
                byLevel[level.ordinal()] =
                        Math.incrementExact(byLevel[level.ordinal()]);
            } catch (ArithmeticException overflow) {
                throw new IOException(
                        "Statistics overflow at line " + lineNumber,
                        overflow);
            }
            minMs = Math.min(minMs, durationMs);
            maxMs = Math.max(maxMs, durationMs);
        }

        void print() {
            System.out.println("rows=" + rows);
            System.out.println("valid=" + valid);
            System.out.println("invalid=" + invalid);
            for (Level level : Level.values()) {
                System.out.println(level + "=" + byLevel[level.ordinal()]);
            }
            System.out.println("totalMs=" + sumMs);
            if (valid == 0) {
                System.out.println("minMs=n/a");
                System.out.println("maxMs=n/a");
                System.out.println("avgMs=n/a");
            } else {
                System.out.println("minMs=" + minMs);
                System.out.println("maxMs=" + maxMs);
                System.out.printf(Locale.ROOT, "avgMs=%.2f%n",
                        (double) sumMs / valid);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 1) {
            System.err.println("Usage: java LargeFileStatsDemo [file.csv]");
            return;
        }

        if (args.length == 1) {
            analyze(Path.of(args[0])).print();
            return;
        }

        Path example = Files.createTempFile("large-file-stats-", ".csv");
        try {
            String sample = String.join("\n",
                    "level,durationMs",
                    "INFO,120",
                    "WARN,300",
                    "ERROR,450",
                    "INFO,80",
                    "WARN,200",
                    "broken",
                    "INFO,-1",
                    "ERROR,150") + "\n";

            // Chỉ ghi đè file tạm vừa được chính chương trình tạo.
            Files.writeString(example, sample, StandardCharsets.UTF_8);
            analyze(example).print();
        } finally {
            Files.deleteIfExists(example);
        }
    }

    private static Stats analyze(Path file) throws IOException {
        Stats stats = new Stats();

        try (BufferedReader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String header = reader.readLine();
            if (!"level,durationMs".equals(header)) {
                throw new IOException("Missing or invalid CSV header");
            }

            String line;
            long lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                stats.rows++;

                int comma = line.indexOf(',');
                if (comma <= 0
                        || comma == line.length() - 1
                        || line.indexOf(',', comma + 1) >= 0) {
                    stats.invalid++;
                    continue;
                }

                Level level;
                long duration;
                try {
                    level = Level.valueOf(
                            line.substring(0, comma).trim());
                    duration = Long.parseLong(
                            line.substring(comma + 1).trim());
                } catch (IllegalArgumentException invalidRow) {
                    stats.invalid++;
                    continue;
                }

                if (duration < 0) {
                    stats.invalid++;
                    continue;
                }

                stats.accept(level, duration, lineNumber);
            }
        }

        return stats;
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac LargeFileStatsDemo.java
java LargeFileStatsDemo
```

**Stdout chính xác cho dữ liệu mẫu tích hợp:**

```text
rows=8
valid=6
invalid=2
INFO=2
WARN=2
ERROR=2
totalMs=1300
minMs=80
maxMs=450
avgMs=216.67
```

Để đọc file của bạn:

```bash
java LargeFileStatsDemo /path/to/events.csv
```

Đây chỉ là ví dụ cú pháp đường dẫn trên hệ Unix; hãy thay bằng đường dẫn thật phù hợp hệ điều hành của bạn. File phải tuân thủ định dạng `level,durationMs` nêu trên; output sẽ phản ánh dữ liệu của file được truyền vào.

### Phân tích cách ví dụ hoạt động

- `Files.newBufferedReader()` chỉ giữ một buffer đọc và chuỗi của dòng hiện tại, thay vì danh sách mọi dòng.
- Header được kiểm tra trước để tránh nhầm cột hoặc thống kê một file hoàn toàn sai định dạng.
- `line.indexOf(',')` xác định dấu phẩy duy nhất và kiểm tra không có dấu phẩy thứ hai; phù hợp **định dạng hai cột đơn giản**, không có quoted CSV.
- `Level.valueOf()` kiểm tra level hợp lệ; `Long.parseLong()` kiểm tra duration; cả hai có thể ném `IllegalArgumentException` (bao gồm `NumberFormatException` là lớp con) và được ghi nhận như dòng không hợp lệ.
- `stats.accept()` chỉ chạy với bản ghi hợp lệ; `Math.addExact()` ngăn số tổng im lặng tràn `long`.
- `minMs/maxMs` khởi tạo bằng các sentinel nhưng **không in sentinel nếu valid=0**.
- `Locale.ROOT` giữ dấu thập phân `.` trong kết quả mẫu, tránh phụ thuộc thiết lập vùng địa lý trên máy.
- Nhánh chạy với tham số chỉ **đọc** file người dùng, còn nhánh không tham số chỉ tạo và xóa **file tạm do chương trình sở hữu**.

Bài tập cố ý đếm dòng sai nhưng không in toàn bộ nội dung dòng vì file lớn có thể làm log lỗi phình to hoặc lộ dữ liệu. Với dịch vụ thật, có thể xuất **một số lượng chẩn đoán có giới hạn**, ví dụ tối đa 10 lỗi đầu, kèm số dòng, nguyên nhân và không lộ field nhạy cảm.

## 6. Files.lines(): cùng mục tiêu nhưng dùng Stream API

`Files.lines(path, StandardCharsets.UTF_8)` trả `Stream<String>` đọc lười. Một ví dụ đơn giản đếm những dòng chứa từ khóa:

```java
// Minh họa trong phương thức cho phép ném IOException.
try (java.util.stream.Stream<String> lines =
        Files.lines(file, StandardCharsets.UTF_8)) {
    long errors = lines.filter(s -> s.startsWith("ERROR,")).count();
    System.out.println(errors);
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: `file` phải là `Path` hợp lệ, có import `Files` và xử lý ngoại lệ. `Files.lines()` không có nhu cầu tạo danh sách trước khi `count()`. Nó đọc và kiểm tra các dòng khi terminal operation chạy.

**Đóng stream là bắt buộc.** Stream trả về từ `Files.lines()` gắn với tài nguyên file đang mở; không trả nó ra khỏi khối `try-with-resources` rồi để caller sử dụng sau khi file đã bị đóng.

Trong quá trình stream vận hành, lỗi I/O phát sinh sau khi stream được tạo có thể được đóng gói thành `UncheckedIOException` bởi pipeline. Điều này khác cách `BufferedReader.readLine()` khai báo checked `IOException`. Hãy lựa chọn cách xử lý lỗi phù hợp và không nuốt exception trong terminal operation.

### Không biến streaming thành eager collection

Một anti-pattern:

```java
try (var lines = Files.lines(path)) {
    var all = lines.toList();
    // all bây giờ chứa mọi dòng trong RAM!
}
```

Đoạn này là **minh họa**, cần biến `path` kiểu `Path` và xử lý `IOException`. `Files.lines()` chỉ có tính chất lazy **cho đến khi** bạn dùng terminal operation. `toList()`, `collect(toList())` hoặc `groupingBy(..., toList())` có thể tích lũy lượng dữ liệu lớn, đánh mất lợi ích bộ nhớ.

Có thể dùng collector để đếm nhóm:

```java
// Đoạn minh họa: chỉ phù hợp sau khi đã xác thực dữ liệu dòng.
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    var counts = lines
            .filter(s -> !s.isBlank())
            .collect(java.util.stream.Collectors.groupingBy(
                    s -> s.substring(0, s.indexOf(',')),
                    java.util.stream.Collectors.counting()));
}
```

Nhưng **mã này không an toàn với input thiếu dấu phẩy**, và header sẽ bị đếm nếu không bỏ qua. Nó chỉ minh họa collector, **không thay thế code hoàn chỉnh đã kiểm tra dữ liệu**. Hơn nữa, bộ nhớ của `groupingBy()` tăng theo số nhóm khác nhau. Nếu mỗi dòng có một khóa duy nhất, map có thể tăng gần bằng tổng số dòng; khi đó cần giới hạn cardinality hoặc external aggregation.

## 7. Thiết kế thống kê theo nhóm trong file lớn

Bộ đếm ba level cố định của bài thực hành giữ bộ nhớ O(1) theo số dòng. Với dữ liệu thực tế thường cần thống kê theo ngày, khu vực hoặc mã trạng thái:

| Bài toán | State tối thiểu | Bộ nhớ |
| --- | --- | --- |
| Đếm toàn bộ dòng và dòng sai | Một vài bộ đếm `long` | Gần O(1) |
| Tổng, min, max, average | `sum, count, min, max` | Gần O(1) |
| Đếm theo level có 3 giá trị | Mảng ba phần tử / `EnumMap` | Gần O(1) |
| Đếm theo mã trạng thái HTTP có miền hữu hạn | Mảng hoặc map giới hạn số mã | Tỷ lệ số mã có thể xuất hiện |
| Đếm theo user ID không giới hạn | `Map<userId, count>` | Tỷ lệ số user ID khác nhau, có thể rất lớn |
| Tính số giá trị phân biệt chính xác | `HashSet` | Tỷ lệ số giá trị khác nhau |
| Top-K với độ lớn K cố định | Min-heap và bộ đếm thích hợp | Thường O(K) cho lựa chọn top-K khi đã có tần suất, nhưng tính chính xác tần suất mọi khóa còn cần state khác |
| Median/p95 chính xác | Thường cần dữ liệu hoặc cấu trúc chỉ mục/thuật toán thích hợp | Không phải luôn O(1) |
| Median/p95 gần đúng | Sketch/histogram phù hợp | Có thể giới hạn bộ nhớ nhưng có sai số |

Không nên tuyên bố “đọc từng dòng ⇒ mọi thống kê đều O(1) memory”. Điều đúng là **cơ chế đọc không tự lưu toàn bộ file**; phần aggregation vẫn có thể giữ nhiều dữ liệu tùy yêu cầu. Nếu cardinality cao, cân nhắc chia bucket theo khóa, external sort, cơ sở dữ liệu hoặc công cụ xử lý dữ liệu theo khối.

### Giữ đủ thông tin để tính trung bình đúng

Muốn tổng hợp trung bình giữa nhiều file, không lưu và cộng trung bình mỗi file một cách trực tiếp, vì file có số dòng hợp lệ khác nhau. Hãy lưu **`sum` và `count`**, sau đó gộp:

```text
File A: sum=100, count=1      --> avg=100
File B: sum=300, count=3      --> avg=100
Combined: (100+300)/(1+3)    --> avg=100
```

Trường hợp khác sẽ cho thấy rõ lỗi “average of averages”:

```text
File A: sum=100, count=1       --> avg=100
File B: sum=0, count=9         --> avg=0
Incorrect: (100+0)/2          --> 50
Correct:   (100+0)/(1+9)      --> 10
```

Nếu gộp trên nhiều máy, phải định nghĩa overflow, thứ tự kết hợp và chính sách xử lý dòng không hợp lệ trước khi tổng hợp.

## 8. Tối ưu I/O: buffer, số lần cấp phát và charset decoder

`Files.newBufferedReader()` dùng buffered character reader phù hợp nhiều trường hợp. Nếu cần kích thước buffer cụ thể, có thể kết hợp:

```java
// Minh họa, file là Path hợp lệ; IOException được xử lý ở caller.
try (BufferedReader reader = new BufferedReader(
        new java.io.InputStreamReader(
                Files.newInputStream(file), StandardCharsets.UTF_8),
        64 * 1024)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Thống kê trực tiếp.
    }
}
```

Không nên kết luận tăng buffer từ 8 KiB lên 64 KiB luôn nhanh hơn. Kết quả phụ thuộc chiều dài dòng, ổ đĩa, page cache, giải mã charset, số lượng file và chi phí parse.

Một số lựa chọn tối ưu cần benchmark có kiểm soát:

1. **Hạn chế tạo đối tượng không cần thiết.** `String.split(regex)` tạo mảng và nhiều chuỗi; nếu định dạng chỉ có một dấu phân cách, `indexOf()` và `substring()` có thể đơn giản hơn. Tuy nhiên đừng đánh đổi tính đúng của CSV phức tạp để lấy tốc độ.
2. **Đếm bằng `long` thay vì `int`** cho file rất lớn.
3. **Tách I/O và parsing trong benchmark.** Đo đọc đơn thuần khác đo đọc + kiểm tra logic + tạo bản ghi + tổng hợp.
4. **Làm nóng JVM/JIT và file cache công bằng.** Lượt thứ hai có thể nhanh hơn do OS page cache dù API không đổi; không so một lượt cold với một lượt warm rồi kết luận thuật toán tốt hơn.
5. **Không tạo `StringBuilder` khổng lồ cho tất cả dòng** chỉ để thống kê vài chỉ số.
6. **Không parallelize bừa `Files.lines()`**: splitting dòng và thứ tự, tài nguyên chung và mutable accumulator có thể làm code phức tạp mà không tăng tốc.
7. **Tránh ghi log trên mỗi dòng** khi xử lý file hàng trăm triệu dòng; bản thân stdout/log có thể chậm hơn I/O đọc.
8. **Chọn charset đúng** và xử lý encoding error; tốc độ không quan trọng nếu dữ liệu bị parse sai.

Có thể benchmark với JMH cho những bước thuần CPU/parse, nhưng **JMH không tự kiểm soát cache hệ điều hành**. Nếu muốn đánh giá throughput end-to-end, còn cần đo thời gian mở file, đọc, decode, parse, GC và đóng tài nguyên theo phạm vi thật của ứng dụng.

## 9. Xử lý dữ liệu lỗi và giới hạn an toàn

File lớn thường không hoàn toàn sạch. Chính sách **skip, fail-fast, quarantine** cần được thống nhất trước khi chạy:

| Tình huống | Gợi ý xử lý |
| --- | --- |
| Header sai hoặc file trống | Fail-fast, vì có thể đọc nhầm loại dữ liệu |
| Dòng sai số cột | Đếm invalid, ghi một số diagnostic được giới hạn |
| Level lạ | Đếm invalid hoặc map sang nhóm OTHER nếu nghiệp vụ cho phép |
| Duration không phải số nguyên | Đếm invalid hoặc fail-fast tùy yêu cầu |
| Duration âm | Từ chối nếu miền hợp lệ bắt buộc không âm |
| Giá trị duration gây tràn tổng | Dừng với lỗi rõ ràng hoặc dùng `BigInteger` |
| File có charset sai | Báo lỗi decode; không tự chuyển encoding và tiếp tục mà không có quy tắc |
| Một dòng cực dài | Áp dụng giới hạn ký tự/byte trong parser trước khi cấp phát quá nhiều bộ nhớ |
| File thay đổi trong lúc đang đọc | Kết quả có thể không phản ánh snapshot nhất quán |
| Ổ đĩa/network filesystem lỗi | `IOException`; không báo hoàn thành với thống kê một phần nếu không có checkpoint |

Nếu thống kê phục vụ nghiệp vụ nhạy cảm (tài chính, kiểm toán), cần lưu cả policy parse, schema version, checksum của file đầu vào và cách xử lý lỗi để kết quả có thể truy vết. Không nên tự động bỏ dòng lỗi rồi công bố thống kê như thể toàn bộ dữ liệu đã được xử lý.

### Không chấp nhận một dòng vô hạn chỉ vì đã streaming

`BufferedReader.readLine()` không cung cấp tham số “maximum line length”. Nếu đầu vào do bên thứ ba không tin cậy tạo, bộ giới hạn phải chạy **trong lúc tiêu thụ ký tự/byte**, không chỉ:

```java
String line = reader.readLine();
if (line.length() > 10000) { ... }
```

vì tại thời điểm kiểm tra, `readLine()` **đã tạo chuỗi rất dài**. Một parser giới hạn an toàn hơn có thể đọc từng chunk/chữ cái, dừng/đánh dấu khi vượt ngưỡng và tiếp tục bỏ phần còn lại tới newline mà không tích lũy. Nếu cần dữ liệu CSV đúng chuẩn, nên chọn thư viện parser có khả năng giới hạn chiều dài record/field.

## 10. Xử lý file có nhiều GB, nhiều ngày hoặc nhiều nguồn

Đối với **một file lớn**, streaming one-pass thường đủ. Với **nhiều file**, có thể chạy vòng lặp từng file, đóng `BufferedReader` sau mỗi file, cộng thống kê vào accumulator tổng bằng phép cộng có kiểm tra overflow. Không cần mở hàng nghìn file descriptor đồng thời.

Với file được cập nhật liên tục như log đang chạy, một lượt đọc có thể gặp EOF trước khi log writer ghi tiếp. **Đọc file tới EOF khác với theo dõi file (tail -f).** Nếu ứng dụng cần nhận dữ liệu mới theo thời gian thực, phải có cơ chế polling, rotation handling hoặc watcher theo thiết kế, không để `readLine()` quay trong vòng lặp busy-wait vô hạn.

Khi file đang bị ghi cùng lúc, không mặc nhiên có ảnh chụp (snapshot) nhất quán. Có thể lựa chọn:

- Chỉ xử lý file được producer **đóng hoàn toàn** rồi publish bằng đổi tên phù hợp.
- Tạo bản snapshot/immutable input với checksum hoặc version rõ ràng.
- Nếu phải đọc file live, quy định khi nào một dòng dở chưa kết thúc newline được coi là hoàn chỉnh, xử lý log rotation và retry.
- Nếu muốn đọc song song nhiều phần của cùng file, phải tìm **ranh giới dòng thật** tại các điểm chia; chia chỉ theo byte offset rồi mỗi worker đọc tùy ý dễ đếm thiếu hoặc trùng dòng.

**Lưu ý:** Java `BufferedReader.readLine()` có thể trả về dòng cuối ngay cả khi file không kết thúc bằng newline. Với file bất biến, đây là dòng hợp lệ theo quy tắc đọc văn bản; với log đang ghi, nó có thể là **bản ghi dở**. Nên định nghĩa giao thức publish/snapshot thay vì suy đoán.

## 11. Kiểm thử thống kê trước khi dùng trên dữ liệu thật

Các ca cần có:

1. **File chỉ có header:** `rows=0`, `valid=0`, `invalid=0`, min/max/average là `n/a`.
2. **File rỗng:** Báo lỗi header, không chấp nhận thành tập dữ liệu hợp lệ.
3. **Dòng malformed:** Thiếu dấu phẩy, thừa dấu phẩy, chỉ có một cột, level lạ, duration không phải số.
4. **Dòng trống:** Với chính sách ví dụ, dòng trống là `invalid`.
5. **Duration âm:** Bị loại, không ảnh hưởng `sum` hay average.
6. **Duration bằng 0:** Là hợp lệ, ảnh hưởng `count` và có thể ảnh hưởng `minMs`.
7. **Duration lớn:** Kiểm tra parsing `long`, xử lý tổng vượt `Long.MAX_VALUE`.
8. **UTF-8/BOM:** Kiểm tra encoding và chính sách BOM của file thực tế.
9. **CRLF/LF:** Đảm bảo cách đếm dòng không phụ thuộc kiểu newline.
10. **Không có newline cuối file:** Dòng cuối vẫn được đọc.
11. **File rất lớn:** Theo dõi heap/GC, tránh tăng memory theo số dòng.
12. **File bị thay đổi giữa lượt:** Đảm bảo có chính sách snapshot/retry hoặc ghi rõ kết quả không phải snapshot.
13. **Lỗi giữa quá trình đọc:** Không xuất một báo cáo “thành công” khi `IOException` xảy ra.
14. **File do người dùng chỉ định:** Chương trình không xóa hoặc sửa nội dung đầu vào.

Với bài mẫu ở mục 5, sáu bản ghi hợp lệ có duration `120, 300, 450, 80, 200, 150`. Kiểm tra thủ công: tổng bằng `1300`, min `80`, max `450`, average `216.666...` nên in `216.67`. Mỗi level xuất hiện đúng hai lần, còn tổng số dòng sau header là tám.

## 12. Bài tập mở rộng

Sau khi chạy được chương trình, có thể tự mở rộng theo các hướng sau:

**Bài 1 — Thống kê theo ngày.** Thêm cột `date` theo ISO `yyyy-MM-dd`, đếm theo ngày và level. Dùng `LocalDate.parse()` để xác minh ngày, rồi cân nhắc `Map<LocalDate, Stats>`. Phân tích bộ nhớ nếu file có hàng triệu giá trị ngày/khóa khác nhau.

**Bài 2 — Đọc nhiều file.** Truyền danh sách đường dẫn từ CLI, xử lý từng file qua cùng một phương thức `analyze()` rồi tổng hợp. Có chính sách đối với một file thất bại: dừng tất cả hay báo trạng thái từng file; đừng im lặng bỏ file lỗi.

**Bài 3 — Báo tỷ lệ lỗi.** Tính `invalid / rows × 100%` nếu `rows > 0`, in bằng `Locale.ROOT`. Đặt ngưỡng (ví dụ tỷ lệ lỗi vượt 1%) để cảnh báo hoặc làm job thất bại.

**Bài 4 — Phân biệt thống kê exact và approximate.** Với hàng tỷ duration, thử thiết kế histogram cố định các bucket `0–99`, `100–499`, `500+`. Bộ đếm các bucket có bộ nhớ gần O(1), nhưng percentile từ bucket là **ước lượng**, không phải giá trị chính xác.

**Bài 5 — So sánh hai phương án.** Viết thêm bản dùng `Files.lines()`, đảm bảo đóng stream, parse giống hệt và so sánh tổng byte/dòng, checksum, số dòng lỗi; benchmark nhiều lượt với trạng thái page cache công bằng. Đừng chỉ đo một lần rồi kết luận API nào nhanh hơn.

## 13. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| `Files.readAllLines()` với file nhiều GB | Heap tăng mạnh, GC/OutOfMemoryError | Dùng `BufferedReader.readLine()` |
| `Files.lines().toList()` | Gom toàn bộ dòng vào RAM | Dùng terminal operation không materialize mọi dòng |
| Quên đóng `Stream` từ `Files.lines()` | Rò rỉ file descriptor/tài nguyên | `try-with-resources` |
| So sánh `line == null` với dòng rỗng | Nhầm EOF và bản ghi trống | `null` chỉ ở EOF |
| Mặc định một file lớn chỉ có dòng ngắn | Một dòng cực dài vẫn làm tăng RAM | Parser có giới hạn record length |
| Không chỉ định charset | Đọc sai tiếng Việt/cột header | Dùng charset phù hợp, thường UTF-8 |
| `split(",")` cho CSV có quoted commas | Tách sai bản ghi | Dùng CSV parser đúng chuẩn |
| Cộng duration trong `int` | Tràn số im lặng | `long` + kiểm tra overflow |
| Tính average khi `count=0` | Chia 0 hoặc output không đúng | Quy ước `n/a` |
| Dùng `groupingBy()` với khóa duy nhất cho mỗi dòng | Map tăng gần số dòng | Giới hạn cardinality hoặc external aggregation |
| In log mỗi bản ghi | I/O ghi log lấn át công việc thống kê | Aggregate lỗi và giới hạn diagnostics |
| Dùng `parallel()` với accumulator dùng chung không đồng bộ | Race, tổng đếm sai | Aggregator thread-safe hoặc thiết kế partition/merge |
| Không kiểm tra header và số cột | Đọc nhầm schema nhưng vẫn có “kết quả” | Validate cấu trúc đầu vào |
| Đọc file đang thay đổi mà coi như snapshot bất biến | Số liệu thiếu/không nhất quán | Publish immutable file hoặc snapshot |
| Cho rằng một `readLine()` luôn đọc nguyên vẹn bản ghi nghiệp vụ | CSV quoted multiline có thể trải nhiều dòng vật lý | Parser CSV có state đúng chuẩn |

**Ghi nhớ:** Với file văn bản lớn, hãy **đọc từng dòng bằng `BufferedReader` hoặc `Files.lines()`**, kiểm tra schema và dữ liệu ngay, cập nhật accumulator thay vì tích lũy mọi bản ghi. Bộ nhớ có thể giữ gần cố định khi chỉ tính count/sum/min/max và số nhóm được giới hạn, nhưng vẫn phải kiểm soát **độ dài dòng, cardinality của nhóm, charset, lỗi I/O, overflow và vòng đời stream**. Đó là nền tảng của một job thống kê Java vừa có khả năng mở rộng vừa kiểm chứng được kết quả.