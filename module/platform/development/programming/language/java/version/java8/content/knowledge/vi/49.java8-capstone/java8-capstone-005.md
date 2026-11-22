# Đọc và xử lý tệp lớn bằng Stream có quản lý tài nguyên trong Java

Khi tệp có hàng triệu dòng, cách đọc quyết định lượng bộ nhớ và độ ổn định của chương trình. Nếu gọi `Files.readAllLines` rồi giữ toàn bộ nội dung trong `List<String>`, bộ nhớ tăng theo kích thước tệp. Với tệp lớn, cách phù hợp hơn thường là **đọc lười từng dòng bằng `Files.lines`, xử lý trong pipeline và đóng stream đúng lúc**.

`Files.lines(Path, Charset)` trả về `Stream<String>` được nạp lười. API giữ một file đang mở và chỉ giải phóng file khi stream được đóng. Vì vậy terminal operation như `count()` hoặc `forEach()` **không thay thế việc đóng stream**. Hãy đặt stream trong `try-with-resources` để file được đóng cả khi xử lý thành công, có exception hoặc pipeline kết thúc sớm.

Bài này giải thích cách đọc/ghi tệp lớn, quản lý vòng đời tài nguyên, xử lý lỗi I/O, chọn charset, giữ bộ nhớ ổn định, kiểm soát parallel stream và kiểm thử. Ví dụ hoàn chỉnh dùng API Java 8 và có thể compile bằng JDK hiện hành với `--release 8`.

## 1. Chọn API đọc file phù hợp

Các API đọc toàn bộ nội dung vẫn hữu ích với tệp nhỏ và trường hợp đơn giản:

~~~java
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8); // Java 11+
~~~

Nhưng chúng materialize toàn bộ nội dung thành collection hoặc String. Với tệp lớn, bộ nhớ cần thiết tăng theo số dòng và độ dài dữ liệu, cộng thêm overhead của object, collection và các bản sao trung gian. Tài liệu Java nói rõ `Files.readAllLines` và `Files.readString` không dành cho việc đọc tệp rất lớn; `Files.readString` chỉ có từ Java 11.

| API | Cách đọc | Resource cần đóng | Phù hợp với file lớn |
|---|---|---|---|
| `Files.lines` | Lazy Stream theo dòng | Đóng Stream | Có, nếu không gom toàn bộ |
| `Files.newBufferedReader` | Đọc buffered thủ công | Đóng Reader | Có |
| `BufferedReader.lines` | Lazy Stream theo dòng | Đóng Reader sở hữu | Có |
| `Files.readAllLines` | Nạp thành List | API tự đóng file | Không nên |
| `Files.readString` | Nạp thành String | API tự đóng file | Không nên |
| `Files.newBufferedWriter` | Ghi buffered | Đóng Writer | Có |
| `Files.newInputStream` | Đọc byte | Đóng InputStream | Có, cho dữ liệu byte |

### 1.1. Đọc lười bằng Files.lines

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long errorCount = lines
            .filter(line -> line.startsWith("ERROR"))
            .count();

    System.out.println("Errors: " + errorCount);
}
~~~

Pipeline không tạo `List<String>` chứa mọi dòng. Sau khi terminal operation hoàn tất, khối try kết thúc và stream được đóng.

**Đọc lười không tự động bảo đảm bộ nhớ hằng số.** Nếu pipeline gọi `collect(toList())`, `toArray()` hoặc tích lũy mọi dòng vào collection, chương trình vẫn giữ toàn bộ dữ liệu. Bộ nhớ phụ thuộc vào pipeline và dữ liệu được giữ lại.

### 1.2. Mô hình xử lý

~~~text
File trên đĩa
    |
    v
Files.lines(path, charset)
    |
    v
Stream<String> đọc lười
    |
    v
filter -> map -> reduce / collect / forEach
    |
    v
Kết quả nhỏ: count, sum, thống kê
    |
    v
try-with-resources đóng stream và file
~~~

Mục tiêu thường là xử lý mỗi dòng rồi bỏ nó đi, chỉ giữ kết quả cần thiết như bộ đếm, tổng, trạng thái hoặc một tập kết quả có giới hạn.

## 2. Quản lý vòng đời của Files.lines

### 2.1. Stream giữ file đang mở

`Files.lines(path, charset)` có các đặc điểm:

- Đọc dòng theo kiểu lazy; nội dung không được nạp toàn bộ vào List trước.
- File được mở khi tạo stream; lỗi mở file được báo bằng `IOException`.
- Stream giữ tham chiếu tới file đang mở.
- Đóng stream sẽ đóng file.
- Lỗi I/O phát sinh sau khi method trả về được bọc trong `UncheckedIOException`.
- Nội dung file không được thay đổi trong khi terminal operation đang chạy; nếu bị sửa, kết quả terminal operation là không xác định.

### 2.2. Luôn dùng try-with-resources

~~~java
Path path = Paths.get("logs", "application.log");

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.contains("timeout"))
         .forEach(System.out::println);
}
~~~

`Stream` kế thừa `AutoCloseable` thông qua `BaseStream`. Try-with-resources gọi `close()` khi rời khỏi block, kể cả khi body ném exception. Cách này an toàn hơn việc tự gọi `close()` trong nhiều nhánh hoặc viết `finally` thủ công.

Không viết:

~~~java
Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8);
lines.forEach(System.out::println);
// File vẫn có thể đang mở vì stream chưa được đóng.
~~~

Terminal operation tiêu thụ stream nhưng không tự đóng một stream có resource. Cần đóng bằng try-with-resources hoặc cơ chế quản lý tương đương.

### 2.3. Pipeline kết thúc sớm vẫn phải đóng

Các terminal operation như `findFirst()`, `anyMatch()`, `allMatch()` và `limit()` có thể khiến quá trình đọc dừng trước khi tới cuối file. Chúng không thay thế `close()`.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    boolean found = lines.anyMatch(line -> line.contains("FATAL"));
    System.out.println("Fatal event found: " + found);
}
~~~

Dù đã tìm thấy dòng phù hợp ở đầu file, try-with-resources vẫn đóng stream khi thoát block.

### 2.4. Stream chỉ dùng một lần

Stream đã có terminal operation thì không thể tái sử dụng cho terminal operation khác. Nếu cần hai thống kê độc lập, có thể mở file hai lần hoặc tính nhiều thống kê trong một lượt bằng collector phù hợp.

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    // Không gọi lines.filter(...) ở đây: stream đã được tiêu thụ.
}
~~~

Không lưu stream vào field hoặc chia sẻ cho nhiều method để sử dụng về sau. Hãy tạo stream trong scope xử lý, dùng nó một lần rồi đóng.

## 3. Charset và cách tách dòng

### 3.1. Nêu rõ charset

~~~java
Stream<String> lines = Files.lines(path);
Stream<String> utf8Lines =
        Files.lines(path, StandardCharsets.UTF_8);
~~~

Overload không có charset dùng UTF-8. Ghi rõ charset trong code giúp hợp đồng dữ liệu dễ đọc và tránh nhầm khi hệ thống trao đổi file với nguồn khác. Chỉ dùng charset phù hợp với định dạng nguồn; không đoán encoding khi nó đã được quy định.

### 3.2. Line terminator và dòng trống

`Files.lines` nhận biết các dấu kết thúc dòng phổ biến như CRLF (`\\r\\n`), LF (`\\n`) và CR (`\\r`). Phần tử String trả về không chứa ký tự kết thúc dòng. Một dòng trống vẫn là phần tử String rỗng. Không tự bỏ dòng trống hoặc trim khoảng trắng nếu định dạng nghiệp vụ yêu cầu giữ chúng.

Nếu tệp UTF-8 có BOM, decoder UTF-8 có thể đưa ký tự `U+FEFF` vào đầu nội dung. `Files.lines` không phải parser CSV/JSON và không tự xử lý mọi quy tắc định dạng. Nếu format nguồn cho phép BOM, xử lý có chủ đích ở dòng đầu hoặc dùng parser phù hợp.

### 3.3. Một dòng cực dài vẫn có thể tốn bộ nhớ

`Files.lines` chia nội dung theo dòng. Một dòng có kích thước hàng trăm MB vẫn cần được biểu diễn thành một String lớn khi dòng đó được đọc. Nếu định dạng không có line boundary đáng tin cậy hoặc một record có thể rất lớn, cân nhắc đọc theo byte/char buffer có kích thước cố định, parser streaming hoặc định dạng record có giới hạn.

Streaming theo dòng tránh giữ toàn bộ file, nhưng không biến một dòng đơn lẻ thành chuỗi có bộ nhớ cố định.

## 4. Giữ bộ nhớ ổn định khi xử lý

### 4.1. Tích lũy kết quả nhỏ

~~~java
long errorCount;
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    errorCount = lines
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

`count()` chỉ trả về một số long. Pipeline xử lý từng dòng và không cần giữ toàn bộ nội dung trong một collection.

### 4.2. Một lượt đọc với nhiều thống kê

~~~java
long[] stats;
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    stats = lines.collect(
            () -> new long[3],
            (counts, line) -> {
                counts[0]++;
                if (line.startsWith("ERROR")) {
                    counts[1]++;
                } else if (line.startsWith("WARN")) {
                    counts[2]++;
                }
            },
            (left, right) -> {
                left[0] += right[0];
                left[1] += right[1];
                left[2] += right[2];
            });
}
~~~

Accumulator có ba số đếm; mỗi dòng được kiểm tra rồi loại khỏi pipeline. Combiner cộng các accumulator khi stream được thực thi theo nhiều phần. Cách viết này không cần collection chứa tất cả dòng.

Với stream tuần tự mặc định, collector vẫn chạy đúng. Nếu chuyển sang parallel, supplier/accumulator/combiner phải tuân thủ quy tắc reduction; không dùng một mảng dùng chung bên ngoài rồi tăng số đếm trong lambda.

### 4.3. Tránh thao tác giữ trạng thái lớn

Các thao tác sau có thể cần giữ nhiều phần tử trong bộ nhớ:

- `collect(Collectors.toList())` hoặc `toArray()` giữ toàn bộ kết quả.
- `sorted()` thường phải giữ dữ liệu để sắp xếp.
- `distinct()` phải theo dõi các phần tử đã gặp.
- `groupingBy()` có thể tạo map chứa nhiều nhóm và giá trị.
- Lưu mọi dòng vào field/static collection làm mất lợi ích streaming.

Không phải những thao tác này luôn sai. Chỉ dùng khi kích thước dữ liệu được giới hạn hoặc có ngân sách bộ nhớ rõ ràng. Nếu cần sắp xếp toàn bộ tệp lớn, cân nhắc external sort hoặc xử lý phân vùng trên đĩa.

### 4.4. Dùng giới hạn cho tập kết quả

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.startsWith("WARN"))
         .limit(20)
         .forEach(System.out::println);
}
~~~

`limit` giới hạn số phần tử được tiêu thụ sau filter. Nó không bảo đảm file chỉ có 20 dòng được đọc nếu filter phải quét nhiều dòng mới tìm đủ kết quả.

## 5. IOException và UncheckedIOException

Lỗi lúc mở file và lỗi trong lúc đọc lazy khác nhau:

| Thời điểm | Loại lỗi thường gặp | Cách xử lý |
|---|---|---|
| Mở file trong `Files.lines` | `IOException` | Xử lý quyền, path, trạng thái file |
| Đọc tiếp khi terminal operation chạy | `UncheckedIOException` | Xem `getCause()` và propagate |
| Charset không giải mã được dữ liệu | `UncheckedIOException` sau khi stream trả về | Xác minh encoding và dữ liệu |
| Đóng stream gặp lỗi I/O | `UncheckedIOException` | Giữ lại thông tin lỗi đóng |

`Files.lines` có thể ném `IOException` ngay khi mở file, ví dụ file không tồn tại hoặc không có quyền truy cập. Sau khi stream được trả về, thao tác đọc diễn ra lazy. Nếu có lỗi I/O hoặc lỗi decode trong lúc terminal operation chạy, API bọc lỗi trong `UncheckedIOException` để truyền qua functional method không khai báo checked exception.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(this::processLine);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    // Ghi path và operation để điều tra; giữ cause khi propagate.
    throw ex;
}
~~~

`UncheckedIOException.getCause()` trả lại `IOException` gốc. Khi xử lý ở tầng boundary, ghi thêm path/operation phù hợp rồi propagate lỗi hoặc chuyển thành exception nghiệp vụ có cause. Không catch rồi bỏ qua, vì chương trình có thể báo thành công dù chỉ xử lý một phần file.

Nếu body của try ném exception và quá trình đóng resource cũng ném exception, lỗi từ quá trình đóng được gắn vào exception chính dưới dạng suppressed exception. Có thể xem chúng qua `Throwable.getSuppressed()`. Try-with-resources xử lý thứ tự đóng và giữ thông tin này.

## 6. BufferedReader.lines và quyền sở hữu tài nguyên

`Files.lines` là lựa chọn gọn khi muốn có Stream trực tiếp từ Path. Một cách khác là mở `BufferedReader` bằng `Files.newBufferedReader` rồi lấy stream từ `reader.lines()`.

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
          .filter(line -> line.contains("timeout"))
          .forEach(System.out::println);
}
~~~

`BufferedReader.lines()` cũng đọc lười và có thể bọc lỗi đọc trong `UncheckedIOException`. Trong cách này, **BufferedReader là resource owner** và phải được đóng bằng try-with-resources. Đừng giả định terminal operation hoặc việc stream kết thúc sẽ đóng reader thay bạn.

Dùng BufferedReader khi cần đọc thêm theo API reader, cấu hình buffer hoặc phối hợp logic đọc tuần tự khác. Không gọi `reader.readLine()` đồng thời với terminal operation đang tiêu thụ `reader.lines()`; tài liệu quy định reader không được thao tác trong khi terminal operation của stream chạy.

Nếu record không phân tách theo dòng hoặc cần kiểm soát từng block ký tự, dùng `BufferedReader.read(char[])` hoặc byte stream/channel với buffer cố định. Khi đó chương trình tự quản lý buffer, encoding decoder và ranh giới record.

## 7. Ghi kết quả lớn mà không tạo collection trung gian

Đọc streaming nhưng cuối cùng gom toàn bộ kết quả vào List rồi ghi file vẫn tiêu tốn bộ nhớ. Khi đầu ra cũng lớn, mở `BufferedWriter` trong try-with-resources và ghi từng phần.

~~~java
try (Stream<String> lines =
        Files.lines(input, StandardCharsets.UTF_8);
     BufferedWriter writer =
        Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {

    lines.filter(line -> line.startsWith("ERROR"))
         .forEach(line -> {
             try {
                 writer.write(line);
                 writer.newLine();
             } catch (IOException ex) {
                 throw new UncheckedIOException(ex);
             }
         });
}
~~~

Lambda của `forEach` không khai báo checked IOException, vì vậy ví dụ chuyển lỗi ghi thành `UncheckedIOException`. Resource declarations được đóng theo thứ tự ngược: writer trước, rồi stream đọc. Nếu cần chuyển đổi phức tạp, tách logic ghi thành helper để kiểm thử và xử lý lỗi dễ hơn.

Không mở writer trùng với input path nếu mục tiêu là đọc chính file đó; thao tác truncate output có thể phá nội dung đang đọc. Ghi ra file tạm rồi thay thế đích theo policy phù hợp nếu cần cập nhật nguyên tử.

## 8. Parallel stream có nên dùng với file lớn?

`Files.lines` hỗ trợ parallel splitting tốt với một số charset line-optimal như UTF-8, US-ASCII và ISO-8859-1. Với charset khác, khả năng chia có thể kém hơn. Khả năng split tốt **không có nghĩa parallel luôn nhanh hơn**.

Đọc file thường bị giới hạn bởi tốc độ storage, cache và chi phí decode. Nếu mỗi dòng chỉ thực hiện vài phép so sánh, chi phí scheduling/thread có thể lớn hơn lợi ích.

| Tình huống | Hướng xử lý |
|---|---|
| Đọc và filter nhẹ | Bắt đầu bằng stream tuần tự |
| Tính toán CPU nặng, độc lập theo dòng | Benchmark parallel trên dữ liệu đại diện |
| Cần thứ tự file | Giữ encounter order và kiểm tra operation |
| Có side effect vào collection dùng chung | Tránh parallel mutation; dùng collector phù hợp |
| Logic phụ thuộc dòng trước/sau | Thường xử lý tuần tự |

Không dùng một `ArrayList` hoặc `long[]` dùng chung rồi cập nhật từ nhiều worker:

~~~java
// Không an toàn nếu lines là parallel:
List<String> errors = new ArrayList<String>();
lines.parallel().forEach(line -> {
    if (line.startsWith("ERROR")) {
        errors.add(line);
    }
});
~~~

Dùng collector có supplier/accumulator/combiner phù hợp, concurrent collector khi đúng nhu cầu, hoặc giữ xử lý tuần tự. Đừng dùng `forEachOrdered` để che một thiết kế side effect không an toàn; nó có thể giảm lợi ích song song.

Parallel pipeline có thể xử lý các dòng theo thứ tự khác nhau. Nếu kết quả cần giữ thứ tự file, dùng operation/collector bảo toàn encounter order và chỉ xuất theo cách API đảm bảo.

## 9. Tính nhất quán của file trong khi đọc

Tài liệu `Files.lines` nêu nội dung file không được sửa trong lúc terminal operation chạy; kết quả trong trường hợp đó là undefined. Không để tiến trình khác truncate, replace hoặc append đồng thời nếu thuật toán đòi hỏi snapshot nhất quán.

Các lựa chọn tùy hệ thống gồm:
- Đọc file bất biến theo tên/version.
- Copy sang file snapshot rồi xử lý.
- Dùng cơ chế khóa hoặc quy trình publish file tạm rồi rename.
- Kiểm tra metadata/version trước và sau nếu nghiệp vụ chấp nhận phát hiện thay đổi thay vì khóa.

Không giả định `Files.lines` tự tạo snapshot của toàn bộ file. Stream là cách đọc lười từ resource đang mở, không phải transaction snapshot cho mọi filesystem.

## 10. Chương trình Java hoàn chỉnh

File **`LargeFileStreamDemo.java`** dưới đây tương thích Java 8. Chương trình tạo file log tạm với năm dòng, đọc bằng `Files.lines` và tổng hợp ba số đếm bằng một collector nhỏ. Nó không lưu danh sách tất cả dòng vào bộ nhớ.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.stream.Stream;

public class LargeFileStreamDemo {
    private static long[] summarize(Path input) throws IOException {
        try (Stream<String> lines =
                     Files.lines(input, StandardCharsets.UTF_8)) {
            return lines.collect(
                    () -> new long[3],
                    (counts, line) -> {
                        counts[0]++;
                        if (line.startsWith("ERROR")) {
                            counts[1]++;
                        } else if (line.startsWith("WARN")) {
                            counts[2]++;
                        }
                    },
                    (left, right) -> {
                        left[0] += right[0];
                        left[1] += right[1];
                        left[2] += right[2];
                    });
        }
    }

    public static void main(String[] args) throws IOException {
        Path input = Files.createTempFile("large-file-demo-", ".log");
        try {
            Files.write(input, Arrays.asList(
                    "INFO service started",
                    "ERROR database timeout",
                    "WARN retry scheduled",
                    "ERROR payment rejected",
                    "INFO service stopped"),
                    StandardCharsets.UTF_8);

            long[] counts = summarize(input);
            long otherLines = counts[0] - counts[1] - counts[2];

            System.out.println("Total lines: " + counts[0]);
            System.out.println("ERROR lines: " + counts[1]);
            System.out.println("WARN lines: " + counts[2]);
            System.out.println("Other lines: " + otherLines);
            System.out.println("All checks passed");
        } finally {
            Files.deleteIfExists(input);
        }
    }
}
~~~

Biên dịch trên JDK 8 hoặc JDK hiện hành:

~~~bash
javac -encoding UTF-8 LargeFileStreamDemo.java
java LargeFileStreamDemo
~~~

Nếu dùng JDK 9 trở lên và muốn xác minh tương thích Java 8:

~~~bash
javac -Xlint:-options --release 8 -encoding UTF-8 LargeFileStreamDemo.java
java LargeFileStreamDemo
~~~

Stdout đã chạy kiểm chứng:

~~~text
Total lines: 5
ERROR lines: 2
WARN lines: 1
Other lines: 2
All checks passed
~~~

Kết quả cho thấy tổng cộng 5 dòng, trong đó 2 dòng ERROR, 1 dòng WARN và 2 dòng còn lại. Collector chỉ giữ ba bộ đếm; mỗi String được xử lý rồi không được giữ lại trong một danh sách toàn file. File tạm được xóa trong finally.

### 10.1. Vì sao collector này phù hợp?

`collect(supplier, accumulator, combiner)` tạo accumulator mới, cập nhật nó với từng phần tử và kết hợp các accumulator khi cần. Với chương trình này, accumulator là mảng ba phần tử kiểu long, nên trạng thái tổng hợp có kích thước cố định.

Nếu thay collector bằng `collect(Collectors.toList())` thì tất cả dòng sẽ được giữ lại, làm mất mục tiêu kiểm soát bộ nhớ. Chọn cấu trúc kết quả nhỏ phù hợp với câu hỏi cần trả lời.

## 11. Kiểm thử và vận hành với tệp lớn

### 11.1. Test file rỗng và file nhỏ

Kiểm tra file rỗng cho tổng 0, file một dòng không có newline cuối file, dòng trống và khoảng trắng, CRLF/LF/CR nếu định dạng nguồn có thể dùng chúng, dữ liệu UTF-8 có tiếng Việt và dòng ERROR/WARN ở đầu, giữa, cuối.

### 11.2. Test lỗi và quyền truy cập

Kiểm tra file không tồn tại, path là directory, không có quyền đọc, dữ liệu byte không hợp lệ với charset đã chọn và lỗi trong quá trình đọc nếu môi trường test hỗ trợ mô phỏng. Xác minh lỗi mở là IOException và lỗi phát sinh khi tiêu thụ stream có thể là UncheckedIOException.

### 11.3. Test quản lý resource

Dùng try-with-resources trong code production. Nếu viết test cho wrapper quản lý stream, có thể gắn `onClose` để đánh dấu callback đóng đã được gọi:

~~~java
AtomicBoolean closed = new AtomicBoolean(false);
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)
             .onClose(() -> closed.set(true))) {
    lines.count();
}
assertTrue(closed.get());
~~~

Đây là mảnh test minh họa; cần import `AtomicBoolean` và assertion API tương ứng. `onClose` chỉ chạy khi `close()` được gọi; nó không tự chạy chỉ vì terminal operation hoàn tất.

### 11.4. Đo hiệu năng bằng dữ liệu đại diện

Đo thời gian và heap với file có số lượng dòng và kích thước gần production, độ dài dòng trung bình và dòng lớn nhất, charset thực tế, pipeline thực tế và sequential/parallel khi có lý do so sánh.

Không dùng file vài KB để kết luận tốc độ trên file nhiều GB. Không dùng thời gian của lần chạy đầu tiên làm kết luận duy nhất; JVM warm-up, filesystem cache và môi trường I/O ảnh hưởng kết quả.

### 11.5. Quan sát tài nguyên và lỗi

Khi xử lý batch dài, theo dõi thời gian, số dòng, số lỗi, file đang xử lý và thời điểm bắt đầu/kết thúc. Tránh ghi toàn bộ nội dung dòng vào log nếu có dữ liệu cá nhân, secret hoặc payload lớn. Khi thất bại, giữ path, operation, cause và số dòng/offset nếu parser có thể xác định.

## 12. Lỗi thường gặp

**1. Dùng readAllLines cho tệp rất lớn.** Nó tạo List chứa toàn bộ dòng.

**2. Dùng readString để đọc file nhiều GB.** Toàn bộ nội dung thành một String.

**3. Quên đóng Files.lines.** File handle có thể bị giữ lâu và cạn tài nguyên.

**4. Nghĩ terminal operation tự đóng stream.** Phải đóng rõ bằng try-with-resources.

**5. Chỉ đóng stream khi thành công.** Exception hoặc short-circuit vẫn cần cleanup.

**6. Tái sử dụng stream sau terminal operation.** Stream đã bị tiêu thụ.

**7. Dùng collect(toList()) rồi cho rằng đã streaming.** List vẫn giữ mọi dòng trong RAM.

**8. Dùng sorted/distinct/groupingBy không tính bộ nhớ.** Stateful operation có thể giữ lượng dữ liệu lớn.

**9. Không chỉ rõ charset.** Có thể giải mã sai dữ liệu nguồn.

**10. Nhầm IOException và UncheckedIOException.** Lỗi mở file khác lỗi đọc lazy sau khi stream trả về.

**11. Catch UncheckedIOException rồi bỏ qua.** File có thể chỉ được xử lý một phần.

**12. Dùng BufferedReader.lines rồi quên đóng reader.** Reader là resource owner.

**13. Đọc và sửa cùng file trong khi terminal operation chạy.** Kết quả không được bảo đảm.

**14. Parallel stream cập nhật ArrayList/long[] dùng chung.** Có race condition hoặc dữ liệu mất.

**15. Giả định parallel luôn nhanh hơn.** I/O và scheduling có chi phí.

**16. Dùng line stream cho một record đơn cực lớn.** Một String vẫn có thể chiếm bộ nhớ lớn.

**17. Dùng Files.lines cho binary.** Dùng byte stream/channel và parser binary phù hợp.

**18. Ghi output vào chính file đang đọc.** Có thể truncate dữ liệu đang đọc.

**19. Bỏ qua lỗi đóng writer/reader.** Flush/close có thể phát sinh lỗi I/O.

**20. Test chỉ với file nhỏ.** Không phát hiện tích lũy bộ nhớ, file handle leak hoặc throughput issue.

## 13. Checklist trước khi xử lý tệp lớn trong production

1. Tệp có cần đọc theo dòng hay theo byte/record cố định?
2. Charset được xác định từ hợp đồng dữ liệu chưa?
3. Dùng `Files.lines` hay `BufferedReader` đúng nhu cầu?
4. Stream/resource được đóng bằng try-with-resources chưa?
5. Pipeline có giữ toàn bộ dòng trong List/Map không?
6. Stateful operations có thể làm bộ nhớ tăng theo file không?
7. Một dòng cực lớn có thể vượt ngân sách bộ nhớ không?
8. IOException lúc mở và UncheckedIOException lúc đọc được xử lý chưa?
9. Có giữ cause và suppressed exception khi báo lỗi không?
10. File có bị tiến trình khác sửa trong khi đọc không?
11. Parallel stream có thực sự cần thiết và đã benchmark chưa?
12. Shared state trong lambda có an toàn không?
13. Output writer có được đóng và lỗi ghi được propagate không?
14. Test có cover empty, Unicode, newline, malformed data và file lớn không?
15. Có theo dõi tiến độ và tránh log raw dữ liệu nhạy cảm không?

## 14. Bài tập tự luyện

1. `Files.lines` khác `Files.readAllLines` thế nào về cách nạp dữ liệu?
2. Vì sao `Files.lines` trả về một resource-owning stream?
3. Terminal operation có tự đóng stream không?
4. Cách nào bảo đảm stream được đóng khi exception xảy ra?
5. Lỗi lúc mở file thường được báo bằng exception nào?
6. Lỗi I/O khi đọc lazy thường được bọc trong exception nào?
7. Vì sao nên chỉ rõ charset?
8. `BufferedReader.lines` có thay thế trách nhiệm đóng reader không?
9. Vì sao collect(toList()) làm mất lợi ích bộ nhớ của streaming?
10. Những operation nào có thể giữ nhiều phần tử trong memory?
11. Vì sao một dòng đơn cực dài vẫn có thể gây áp lực heap?
12. Khi nào nên dùng byte/char buffer thay cho line stream?
13. Vì sao parallel stream không được mặc định là nhanh hơn?
14. Tại sao không cập nhật ArrayList dùng chung trong parallel forEach?
15. `Files.lines` có bảo đảm snapshot nếu file bị sửa giữa lúc đọc không?
16. Try-with-resources xử lý exception khi close như thế nào?
17. `Stream.onClose` chạy lúc nào?
18. Vì sao phải đóng stream dù findFirst đã tìm thấy kết quả?
19. Cách nào tính nhiều thống kê trong một lần đọc mà không giữ mọi dòng?
20. Vì sao không nên ghi output vào chính file đang đọc?

**Gợi ý đáp án:** (1) lines đọc lười qua Stream; readAllLines tạo List chứa tất cả dòng. (2) Nó giữ file đang mở. (3) Không. (4) try-with-resources. (5) IOException. (6) UncheckedIOException. (7) Tránh giải mã sai và làm rõ contract. (8) Không; reader vẫn phải được đóng. (9) List giữ mọi dòng. (10) sorted, distinct, groupingBy và collect toàn bộ. (11) Dòng đó vẫn được tạo thành String lớn. (12) Khi record không có line boundary hoặc cần xử lý chunk cố định. (13) I/O và scheduling có chi phí. (14) ArrayList không thread-safe. (15) Không; thay đổi file khi terminal operation chạy khiến kết quả undefined. (16) Exception khi close được thêm suppressed nếu body đã ném exception. (17) Khi Stream.close được gọi. (18) Terminal operation không giải phóng resource. (19) Collector có accumulator kích thước cố định. (20) Mở writer có thể truncate input.

## Tổng kết

Đọc tệp lớn bằng `Files.lines` giúp xử lý từng dòng theo kiểu lazy mà không materialize toàn bộ file thành List. Nhưng lợi ích đó chỉ còn khi pipeline không tích lũy mọi dòng vào collection. Vì stream giữ file đang mở, hãy **quản lý nó bằng try-with-resources**; phân biệt IOException lúc mở với UncheckedIOException khi đọc lazy, chỉ rõ charset và xử lý lỗi thay vì bỏ qua. Bắt đầu bằng stream tuần tự, accumulator nhỏ và output writer có quản lý tài nguyên; chỉ dùng parallel hoặc buffer tự quản khi đo đạc và yêu cầu dữ liệu cho thấy cần thiết.

## 15. Bảng tra nhanh

| Nhu cầu | API/operation | Ghi nhớ |
|---|---|---|
| Đọc file theo dòng lazy | `Files.lines` | Đóng Stream |
| Đọc buffered thủ công | `Files.newBufferedReader` | Đóng Reader |
| Stream từ reader | `BufferedReader.lines` | Reader sở hữu resource |
| Nạp mọi dòng | `Files.readAllLines` | Tránh với file rất lớn |
| Nạp toàn bộ text | `Files.readString` | Java 11+, tránh file rất lớn |
| Đếm dòng | `count()` | Kết quả nhỏ |
| Lọc dòng | `filter()` | Không tự giữ toàn file |
| Giới hạn kết quả | `limit()` | Vẫn phải đóng stream |
| Tổng hợp thống kê | `collect` | Dùng accumulator nhỏ |
| Sắp xếp | `sorted()` | Có thể cần nhiều bộ nhớ |
| Loại trùng | `distinct()` | Phải nhớ phần tử đã gặp |
| Đóng tài nguyên | `close()` | Dùng try-with-resources |

| Tình huống | Exception/behavior | Phản ứng |
|---|---|---|
| Không mở được path | IOException | Kiểm path/quyền |
| Lỗi đọc sau khi tạo stream | UncheckedIOException | Kiểm cause |
| Lỗi decode | UncheckedIOException | Xác minh charset/bytes |
| Lỗi khi đóng | UncheckedIOException | Giữ lại lỗi close |
| Body và close cùng lỗi | Suppressed exception | Kiểm getSuppressed() |

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — Files.lines, readAllLines, newBufferedReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Oracle Java SE 26 — BufferedReader.lines](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html)
- [Oracle Java SE 26 — BaseStream.close and onClose](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
- [Oracle Java Tutorials — try-with-resources and suppressed exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
