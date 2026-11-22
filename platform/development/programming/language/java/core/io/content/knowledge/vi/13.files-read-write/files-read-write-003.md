# `Files.readAllLines()` và việc đưa toàn bộ dữ liệu vào bộ nhớ trong Java

## Mục tiêu bài học

Trong Java I/O, `Files.readAllLines(path)` rất tiện khi cần đọc một tệp văn bản thành từng dòng. Chỉ với một lời gọi, ta nhận được `List<String>` để duyệt, truy cập theo chỉ số, đếm hoặc so sánh dòng. Tuy nhiên, điểm quan trọng nhất cần nhớ là **phương thức đọc hết nội dung tệp và giữ tất cả các dòng trong bộ nhớ của tiến trình Java**.

Sau bài học, bạn sẽ:

- Hiểu chính xác kết quả và hành vi của `Files.readAllLines(Path)` và `Files.readAllLines(Path, Charset)`.
- Giải thích sự khác biệt giữa **đọc háo hức (eager)** toàn bộ dòng và **đọc theo luồng (streaming/lazy)**.
- Biết tại sao kích thước tệp trên ổ đĩa **không bằng** dung lượng heap dùng cho `List<String>`.
- Dùng `Files.lines()` hoặc `Files.newBufferedReader()` khi dữ liệu lớn hoặc không biết trước kích thước.
- Tránh nhầm các ký tự xuống dòng, charset, tài nguyên cần đóng và giới hạn của cách kiểm tra `Files.size()`.

Các ví dụ sử dụng **Java 17+**, có lệnh biên dịch/chạy và đầu ra dễ kiểm chứng.

## 1. `readAllLines` thực sự làm gì?

Các overload cần nhớ trong `java.nio.file.Files`:

```java
public static List<String> readAllLines(Path path) throws IOException;

public static List<String> readAllLines(Path path, Charset cs)
        throws IOException;
```

Đây là **chữ ký API minh họa**, không phải một chương trình độc lập.

- `path` xác định vị trí tệp trên filesystem. Nếu path tương đối, vị trí của nó phụ thuộc thư mục làm việc hoặc base được giải quyết bởi filesystem.
- `Files.readAllLines(path)` sử dụng **UTF-8** theo hợp đồng API hiện đại của Java.
- `Files.readAllLines(path, charset)` giải mã byte bằng charset do bạn chọn, ví dụ `StandardCharsets.UTF_8` hoặc `StandardCharsets.UTF_16LE`.
- Kết quả là **một danh sách chứa tất cả các dòng đã đọc**; mỗi phần tử là một `String` không chứa ký tự kết thúc dòng.
- Phương thức đọc cho đến **EOF** hoặc lỗi I/O. Nó không trả trước các dòng đã có rồi để bạn đọc phần còn lại theo nhu cầu.
- Sau khi lời gọi hoàn tất, nội dung các dòng nằm trong `List<String>` ở bộ nhớ Java và bạn không cần giữ một stream file đang mở để duyệt danh sách.
- Nếu tệp không tồn tại, không thể đọc, bị hỏng theo charset đang dùng hoặc có lỗi truy cập, lời gọi có thể ném `IOException` hoặc một lớp con thích hợp.

Ví dụ tư duy:

```text
Tệp UTF-8:
  alpha\n
  \n
  beta\r\n
  gamma\n

Files.readAllLines(...)
          |
          v
List<String> trong heap
  index 0: "alpha"
  index 1: ""
  index 2: "beta"
  index 3: "gamma"
```

Trong sơ đồ, `\n` và `\r\n` biểu thị ký hiệu kết thúc dòng, **không phải** các dấu gạch chéo được lưu trong danh sách. Một dòng rỗng **ở giữa tệp** tạo ra phần tử `""`; dấu kết thúc dòng đơn thuần ở **cuối tệp** không tạo thêm một dòng rỗng sau cùng.

Các dấu kết thúc dòng được Java nhận diện hiện nay gồm LF (`\n`), CR (`\r`) và CRLF (`\r\n`). API có thể mở rộng tập dấu kết thúc dòng được nhận diện trong các phiên bản tương lai, nên không xây định dạng lưu trữ nhị phân dựa vào giả định chỉ có đúng ba loại này mãi mãi.

## 2. Ví dụ Java 17+: đọc toàn bộ tệp thành `List<String>`

Chương trình dưới đây tự tạo tệp tạm để không phụ thuộc đường dẫn trên máy người học. Nó chứa một dòng rỗng ở giữa, các kiểu newline khác nhau và một dấu newline cuối tệp.

Lưu thành **`ReadAllLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadAllLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lines-demo-", ".txt");

        try {
            Files.writeString(
                    file,
                    "Java\n\nPython\r\nGo\n",
                    StandardCharsets.UTF_8
            );

            List<String> lines =
                    Files.readAllLines(file, StandardCharsets.UTF_8);

            System.out.println("number of lines = " + lines.size());
            System.out.println("first = " + lines.get(0));
            System.out.println("second is empty = " + lines.get(1).isEmpty());
            System.out.println("last = " + lines.get(lines.size() - 1));
            System.out.println("joined = " + String.join("|", lines));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ReadAllLinesDemo.java
java ReadAllLinesDemo
```

Kết quả:

```text
number of lines = 4
first = Java
second is empty = true
last = Go
joined = Java||Python|Go
```

**Giải thích:**

1. `Files.writeString` ghi đúng chuỗi được chỉ định với mã hóa UTF-8.
2. `readAllLines` đọc đến hết tệp và tạo một `List<String>` có bốn phần tử: `"Java"`, `""`, `"Python"`, `"Go"`.
3. `lines.get(1).isEmpty()` cho thấy dòng trống ở giữa vẫn được giữ lại.
4. Dấu `\n` ở cuối không làm thêm dòng thứ năm.
5. `String.join("|", lines)` chỉ thay đổi cách ta hiển thị danh sách; nó không khôi phục chính xác các dấu xuống dòng ban đầu, vì `readAllLines` đã loại bỏ chúng.
6. `finally` dọn đúng tệp tạm vừa tạo. `readAllLines` tự quản lý việc mở/đóng nguồn đọc nội bộ; không cần gọi `close()` trên `List<String>`.

**Trường hợp đặc biệt:** Tệp hoàn toàn rỗng trả về danh sách rỗng (`lines.size() == 0`). Khi xử lý input có thể rỗng, kiểm tra `isEmpty()` trước khi dùng `get(0)`.

## 3. Vì sao “đưa toàn bộ vào bộ nhớ” là vấn đề lớn?

Đây là điểm phân biệt quan trọng nhất trong đề bài.

```text
                         Files.readAllLines(path)
                                   |
               đọc toàn bộ, giải mã, tách dòng
                                   |
                                   v
Heap Java:    List<String>
             +-----------------------------------+
             | reference -> String dòng 1        |
             | reference -> String dòng 2        |
             | reference -> String dòng 3        |
             | ...                               |
             | reference -> String dòng N        |
             +-----------------------------------+
                                   |
                         toàn bộ dữ liệu còn sống
                         khi danh sách còn được giữ
```

Trong khi danh sách còn được tham chiếu, các đối tượng `String` và cấu trúc chứa chúng cũng tiếp tục chiếm bộ nhớ. Tổng bộ nhớ sử dụng có thể **khác đáng kể so với dung lượng tệp trên đĩa**, vì:

- Byte trong tệp phải được **giải mã** thành dữ liệu chuỗi Java. Số byte UTF-8 không bằng số Java `char` hay dung lượng biểu diễn chuỗi trong bộ nhớ.
- Có **overhead của từng `String`**, các tham chiếu tới phần tử và cấu trúc danh sách. Với hàng triệu dòng rất ngắn, overhead theo **số lượng dòng** có thể đáng kể.
- Có thể xuất hiện các buffer và đối tượng trung gian trong quá trình đọc/giải mã; mức sử dụng bộ nhớ cao nhất trong lúc đọc không nhất thiết bằng dung lượng chỉ của danh sách kết quả.
- Cách JVM biểu diễn chuỗi (chẳng hạn compact strings), kiến trúc runtime và phiên bản Java ảnh hưởng kích thước thực tế. **Không có công thức cố định** kiểu “file 100 MB thì danh sách luôn tốn đúng 200 MB”.
- Nếu tiếp tục gọi `stream()`, `map()`, `toArray()`, `copyOf()`, `collect()` hoặc tạo bản sao khác, chương trình có thể giữ thêm nhiều đối tượng và làm tăng peak memory.

**Độ phức tạp khái quát:** lưu toàn bộ `N` dòng cần bộ nhớ tăng theo **tổng độ dài nội dung được giữ cộng overhead mỗi dòng**, thay vì chỉ theo kích thước của buffer đọc. `readAllLines` phù hợp với dữ liệu **nhỏ, có giới hạn rõ**; với log nhiều GB, file CSV rất lớn hoặc dữ liệu do người dùng tải lên không có giới hạn, đây thường không phải lựa chọn tốt.

Nếu hết heap, chương trình có thể gặp `OutOfMemoryError`. Đây là một `Error` nghiêm trọng, không nên coi việc bắt nó rồi cố xử lý tiếp như chiến lược vận hành bình thường. **Phòng ngừa bằng chọn thuật toán và giới hạn đầu vào phù hợp** mới là hướng chính.

### Ví dụ so sánh định lượng mang tính minh họa

Một tệp 10 triệu dòng, mỗi dòng chỉ vài ký tự, vẫn đòi hỏi tạo/giữ một lượng lớn phần tử `String` và tham chiếu danh sách. Ngay cả khi số byte văn bản trên đĩa không quá lớn, heap cần thiết có thể vượt giới hạn `-Xmx` của JVM. Đây là **nhận định về xu hướng và overhead**, không phải cam kết một mức sử dụng RAM cụ thể; muốn đo thực tế phải profiling trên JDK và dữ liệu cụ thể.

`Files.size(path)` trả về kích thước tệp theo metadata (đơn vị byte) tại một thời điểm; nó **không dự đoán chính xác dung lượng heap của `readAllLines`**, không tính overhead chuỗi, và cũng không bảo đảm tệp không thay đổi sau khi kiểm tra.

## 4. So sánh ba cách đọc dòng

| Tiêu chí | `Files.readAllLines(path, cs)` | `Files.lines(path, cs)` | `Files.newBufferedReader(path, cs)` |
| --- | --- | --- | --- |
| Kết quả | `List<String>` | `Stream<String>` | `BufferedReader` |
| Mô hình | Đọc hết trước khi trả kết quả | Stream đọc/duyệt theo nhu cầu | Vòng lặp đọc từng dòng |
| Lưu tất cả dòng? | **Có** | Không bắt buộc, tùy pipeline | Không bắt buộc, tùy code |
| Có thể chỉ lấy vài dòng đầu? | Đã đọc hết rồi | Có thể dùng `limit(n)`, nhưng có thể đọc trước một phần | Có thể dừng vòng lặp |
| Tài nguyên cần đóng | Hàm tự hoàn thành việc đọc/đóng trước khi trả | **Phải đóng Stream** bằng `try-with-resources` | **Phải đóng Reader** bằng `try-with-resources` |
| Truy cập bằng chỉ số bất kỳ sau đọc | Có: `list.get(i)` | Không trực tiếp | Không trực tiếp |
| Tình huống phù hợp | File nhỏ/có giới hạn, cần giữ các dòng | Lọc/đếm/biến đổi từng dòng | Parser theo vòng lặp, logic điều khiển chi tiết |
| Cạm bẫy | Heap tăng theo toàn tệp | `toList()`/`collect(...)` có thể lại đưa hết vào RAM | Tự tích lũy toàn bộ dòng cũng có vấn đề |

`Files.lines` và `BufferedReader` có thể đọc trước vào buffer, nhưng thường **không cần giữ toàn bộ các dòng đã xử lý**. Tuy nhiên, chúng không bảo đảm tiêu thụ một mức bộ nhớ cố định trong mọi tình huống: **một dòng quá dài** cũng có thể khiến `readLine()` tạo chuỗi rất lớn; các toán tử `sorted()`, `distinct()`, `toList()` hoặc lưu kết quả vào `List` cũng có thể phải giữ rất nhiều dữ liệu.

**Quy tắc chọn API:** Nếu cần random access hoặc duyệt nhiều lần trên một file nhỏ, `readAllLines` tiện. Nếu chỉ cần thống kê, lọc, xử lý từng dòng và bỏ qua nội dung đã dùng, `Files.lines` hoặc `BufferedReader` thường phù hợp hơn.

## 5. Dùng `Files.lines()` để xử lý theo luồng

`Files.lines(path, charset)` trả về `Stream<String>` để xử lý qua `filter`, `map`, `limit`, `count`, `forEach`. Stream có tính chất lazy: thao tác trung gian không tự chạy cho đến khi có thao tác kết thúc (*terminal operation*). Việc tiêu thụ một nguồn file thường diễn ra trong lúc thực hiện pipeline, không cần đợi đọc toàn bộ file rồi mới trả dữ liệu.

### Chương trình Java 17+: đếm dòng cảnh báo

Lưu **`StreamLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class StreamLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-lines-", ".txt");

        try {
            Files.writeString(file,
                    "INFO started\nWARN low\nWARN high\nINFO done\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long warnings = lines
                        .filter(line -> line.startsWith("WARN "))
                        .count();

                System.out.println("warnings = " + warnings);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac StreamLinesDemo.java
java StreamLinesDemo
```

Kết quả:

```text
warnings = 2
```

**Phân tích:**

- `lines.filter(...)` tạo mô tả pipeline, còn `count()` kích hoạt việc duyệt và đếm.
- Không có `List<String>` chứa cả bốn dòng. Chương trình chỉ cần giữ trạng thái đếm và phần dữ liệu đang được xử lý.
- `Stream<String>` mở từ file có tài nguyên I/O bên dưới: **phải đóng** bằng `try-with-resources`, kể cả khi dùng `limit(1)` hoặc có lỗi trong xử lý.
- Một Stream chỉ được tiêu thụ qua pipeline một lần. Nếu cần quét lại tệp, hãy mở `Files.lines(...)` mới hoặc chọn chiến lược lưu dữ liệu có giới hạn.
- Lỗi I/O phát sinh trong lúc duyệt stream có thể được bọc trong `UncheckedIOException` thay vì chỉ xuất hiện lúc gọi `Files.lines`. Đừng quên xử lý lỗi theo thiết kế ứng dụng.

**Cẩn thận:** Thay `count()` bằng `toList()` hay `collect(Collectors.toList())` sẽ tạo một collection chứa toàn bộ kết quả được thu thập. Dù đầu vào đến từ API lazy, **toàn bộ kết quả vẫn có thể nằm trên heap**.

Ví dụ anti-pattern:

```java
// Chỉ minh họa, không phải chương trình độc lập.
try (Stream<String> stream = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> all = stream.toList(); // Vẫn gom toàn bộ dòng vào RAM.
}
```

`Files.lines` không phải một “lá chắn chống OOM” nếu pipeline phía sau chủ động giữ hết dữ liệu.

## 6. Dùng `Files.newBufferedReader()` cho vòng lặp có kiểm soát

Nếu cần parser với trạng thái phức tạp, điều kiện dừng, đếm từng dòng hoặc xử lý lỗi theo vị trí, `BufferedReader` là lựa chọn dễ đọc:

```java
// Đoạn minh họa: path đã có, xử lý IOException tại nơi gọi.
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line); // Phương thức của ứng dụng, không có trong snippet này.
    }
}
```

`readLine()` trả về `null` khi EOF. Một dòng trống hợp lệ trả về `""`, **không phải `null`**. Điều kiện vòng lặp phải kiểm tra `!= null`, không kiểm tra `!line.isEmpty()` để tránh dừng nhầm khi gặp dòng rỗng.

### Chương trình Java 17+: đọc 10.000 dòng nhưng chỉ giữ bộ đếm

Lưu thành **`BufferedCounterDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedCounterDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("counter-lines-", ".txt");

        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                for (int i = 0; i < 10_000; i++) {
                    writer.write(i % 10 == 0 ? "ERROR " : "INFO ");
                    writer.write(Integer.toString(i));
                    writer.newLine();
                }
            }

            int total = 0;
            int errors = 0;

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    total++;
                    if (line.startsWith("ERROR ")) {
                        errors++;
                    }
                }
            }

            System.out.println("lines = " + total);
            System.out.println("errors = " + errors);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BufferedCounterDemo.java
java BufferedCounterDemo
```

Kết quả:

```text
lines = 10000
errors = 1000
```

Dù tệp có 10.000 dòng, chương trình không xây dựng `List<String>` chứa chúng. Vòng lặp chỉ giữ dòng đang xét và hai bộ đếm. `BufferedWriter` được đóng trước khi chương trình bắt đầu đọc, để dữ liệu đã được flush/đóng về phía tệp.

**Giới hạn:** Nếu một dòng duy nhất rất dài, `BufferedReader.readLine()` vẫn phải tạo một `String` chứa nguyên dòng đó. Đối với đầu vào không tin cậy có thể chứa dòng nhiều GB hoặc file không có dấu xuống dòng, muốn khống chế chặt bộ nhớ phải thiết kế bộ phân tích theo khối với giới hạn byte/ký tự rõ ràng, không chỉ thay `readAllLines` bằng `readLine()`.

## 7. Có thể kiểm tra `Files.size()` trước khi dùng `readAllLines` không?

Có thể kiểm tra kích thước tệp trước khi dùng phương thức đọc hết nhằm giảm rủi ro vô tình nạp file quá lớn:

```java
// Snippet minh họa; cần import java.nio.file.Files/Path,
// java.nio.charset.StandardCharsets, java.io.IOException và java.util.List.
static List<String> readSmallText(Path path) throws IOException {
    long maxBytes = 1_000_000L;

    if (Files.size(path) > maxBytes) {
        throw new IOException("file exceeds configured size limit");
    }
    return Files.readAllLines(path, StandardCharsets.UTF_8);
}
```

Mẫu này phù hợp với **file thông thường, ổn định, có giới hạn kích thước theo nghiệp vụ**, nhưng đừng xem nó là bảo vệ tài nguyên tuyệt đối:

1. `Files.size(path)` là kích thước theo filesystem tại một thời điểm; file có thể **thay đổi giữa bước kiểm tra và đọc** (TOCTOU).
2. Kích thước theo **byte** không bằng bộ nhớ cần để tạo `List<String>`. Một file nhiều dòng ngắn vẫn tạo nhiều đối tượng.
3. Một số nguồn/filesystem đặc biệt có thể báo kích thước không hữu ích hoặc thay đổi khi đọc.
4. Một filename/path không tin cậy có thể chịu ảnh hưởng bởi symbolic link hay quyền truy cập; phải xác thực đường dẫn và thao tác file theo yêu cầu bảo mật riêng.
5. Chương trình đồng thời xử lý nhiều tệp dù mỗi tệp có kích thước nhỏ vẫn có thể tiêu thụ nhiều heap.

Với nguồn lớn hoặc không tin cậy, nên dùng **xử lý tăng dần**, giới hạn tổng byte/line, tổng số dòng, chiều dài từng dòng, thời gian và các quota phù hợp. Nếu yêu cầu bắt buộc tuyệt đối, cần đặt các giới hạn trong **quá trình đọc**, không chỉ kiểm tra metadata trước.

## 8. Charset, dòng trống và ký tự xuống dòng

### Charset phải khớp dữ liệu thật

`Files.readAllLines(path)` mặc định UTF-8. Nếu tệp được lưu bằng charset khác (ví dụ Windows-1258 hay UTF-16LE), bạn cần chỉ định charset đúng:

```java
// Đoạn minh họa, giả định path đã được khai báo.
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_16LE);
```

Dùng sai charset có thể khiến đọc thất bại do dữ liệu byte không hợp lệ hoặc tạo ký tự sai dù vẫn đọc được. Với dữ liệu UTF-16 có BOM, quy tắc xử lý BOM/endian còn phụ thuộc charset được chọn; không tự suy đoán toàn bộ từ tên file.

### Giữ hay bỏ dấu kết thúc dòng?

`readAllLines` trả các chuỗi **không chứa** line separator. Ví dụ đầu vào có `\r\n` và `\n` khác nhau nhưng sau khi trả về `List<String>`, bạn không còn thông tin chính xác mỗi dòng dùng kiểu xuống dòng nào. Dùng `String.join(System.lineSeparator(), lines)` tạo **một biểu diễn mới**, không phải khôi phục nguyên byte đã có.

Nếu cần so sánh nguyên bản, tính checksum, đọc giao thức nhị phân hoặc giữ y nguyên cách xuống dòng, hãy làm việc với byte và charset theo định dạng rõ ràng; đừng dùng `readAllLines` rồi giả định kết quả vẫn chứa separator gốc.

### Dòng trống và cuối file

- File rỗng: danh sách không có phần tử.
- Hai dấu newline liên tiếp sau một dòng: có thể tạo dòng rỗng ở giữa.
- Một dấu newline kết thúc dòng cuối: không tự tạo thêm một dòng rỗng sau EOF.
- `BufferedReader.readLine()` trả `null` ở EOF; dòng rỗng trả `""`.
- `Files.lines` cũng cung cấp nội dung dòng không kèm terminator, tương thích với mô hình tách dòng của `readAllLines`.

## 9. Khi nào dùng `readAllLines` vẫn là đúng?

**Dùng `readAllLines` khi:**

- Tệp text **nhỏ và có giới hạn tin cậy**, chẳng hạn danh sách mã cấu hình vài KB, dữ liệu fixture trong bài kiểm thử hoặc văn bản ngắn cần tra cứu.
- Cần truy cập dòng theo chỉ số nhiều lần hoặc so sánh các dòng bất kỳ.
- Cần kiểm tra hay thao tác trên **toàn bộ danh sách** mà việc đọc hết ngay từ đầu là hành vi có chủ ý và chi phí có thể dự đoán.
- Muốn mã đơn giản và không cần giữ tài nguyên đọc trong khi xử lý kết quả.

**Ưu tiên `Files.lines` hoặc `newBufferedReader` khi:**

- Tệp log lớn, CSV nhiều dòng, dữ liệu không biết trước kích thước hoặc file có thể tăng liên tục.
- Mục tiêu chỉ là đếm, lọc, thống kê hoặc ghi chuyển tiếp từng dòng.
- Chỉ cần một số dòng đầu, có thể dừng sớm hoặc xử lý theo điều kiện.
- Cần chủ động xử lý từng dòng rồi bỏ đi, tránh tích lũy kết quả trong RAM.

**Chọn API khác khi:**

- Cần **toàn bộ văn bản trong một `String`**: `Files.readString(path, charset)` cũng là phương thức đọc hết, có rủi ro bộ nhớ tương tự; chỉ khác kiểu kết quả.
- Cần **mọi byte nguyên trạng**: `Files.readAllBytes(path)` đưa toàn bộ byte vào bộ nhớ, cũng không phù hợp cho file quá lớn.
- Cần đọc nhị phân, tệp cực lớn hoặc cần giới hạn bộ nhớ nghiêm ngặt: xử lý bằng `InputStream` theo từng khối, parser có giới hạn hoặc API I/O phù hợp với định dạng.
- Cần tail log hoặc theo dõi file đang được bổ sung: không sử dụng `readAllLines` như một cơ chế quan sát thay đổi liên tục; hãy thiết kế một quy trình đọc cập nhật/giám sát riêng.

## 10. Các lỗi thường gặp

1. **Đọc log vài GB bằng `readAllLines` rồi mới lọc.** Chương trình có thể hết heap trước khi lọc. Dùng `Files.lines` để lọc khi duyệt.
2. **Nghĩ `Files.lines(path).toList()` tiết kiệm heap.** Nó lại thu toàn bộ dòng thành list; lazy ở nguồn không bảo đảm ít bộ nhớ khi đích gom hết.
3. **Quên đóng `Files.lines`.** Stream nắm tài nguyên tệp cho đến khi đóng; dùng `try-with-resources`, không trông chờ GC.
4. **Nghĩ `BufferedReader.readLine()` xử lý mọi dữ liệu với memory cố định.** Một dòng quá dài vẫn có thể chiếm nhiều bộ nhớ.
5. **Dùng `readAllLines` để giữ newline gốc.** Phương thức bỏ các ký tự kết thúc dòng; không phù hợp cho roundtrip nguyên byte.
6. **Lấy `String.length()` làm kích thước file.** Độ dài chuỗi UTF-16 của Java khác kích thước byte UTF-8 và overhead trên heap.
7. **Nhầm dòng rỗng với EOF.** Dòng rỗng là `""`, EOF của `BufferedReader.readLine()` là `null`.
8. **Dựa vào `Files.size()` như một phép bảo đảm tuyệt đối.** File có thể thay đổi và heap overhead khác byte-size; áp giới hạn lúc xử lý.
9. **Giải mã bằng charset không đúng.** Khai báo `UTF-8`/charset đúng theo metadata hoặc hợp đồng dữ liệu; đừng suy từ phần mở rộng tên file.
10. **Cho rằng kiểm tra `-Xmx` lớn là thay thế thiết kế streaming.** Tăng heap chỉ nâng ngưỡng thất bại và làm tài nguyên tốn kém hơn; cần chọn thuật toán đúng.
11. **Giữ kết quả các phép `map`, `groupingBy`, `sorted` trên Stream không giới hạn.** Những thao tác đó có thể tích lũy nhiều dữ liệu; xem chi phí của toàn pipeline, không chỉ nguồn stream.
12. **Bắt `OutOfMemoryError` để coi như đọc xong.** Lỗi này không cho phép coi danh sách đã hoàn chỉnh và có thể khiến tiến trình ở trạng thái tài nguyên bất ổn.
13. **Tưởng `readAllLines` phù hợp cho file liên tục tăng.** Nó đọc đến thời điểm EOF theo cách nguồn cung cấp, không phải kênh theo dõi tail; cần chiến lược riêng khi log đang được append.

## 11. Bảng quyết định nhanh

| Tình huống | Khuyến nghị |
| --- | --- |
| File cấu hình nhỏ, cần nhiều lần `get(i)` | `Files.readAllLines(path, cs)` |
| Đếm số dòng thỏa điều kiện trong file lớn | `try (Stream<String> s = Files.lines(path, cs)) { ... }` |
| Parser cần vị trí dòng và trạng thái cụ thể | `try (BufferedReader r = Files.newBufferedReader(path, cs)) { ... }` |
| Muốn lấy 10 dòng đầu từ file lớn | `Files.lines(...).limit(10)` và đóng stream |
| File nhiều GB, chỉ cần tính tổng | Streaming, chỉ giữ biến tổng và state tối thiểu |
| Dữ liệu có thể chứa một dòng rất lớn | Parser theo khối và ràng buộc chiều dài dòng |
| Cần giữ nguyên byte và newline | `InputStream` hoặc API byte theo định dạng |
| Cần một `String` chứa hết file nhỏ | `Files.readString(path, cs)`, vẫn toàn bộ trong RAM |
| Dữ liệu từ người dùng không đáng tin | Giới hạn byte/dòng/tổng xử lý và xác thực đầu vào |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Files.readAllLines(path)` có trả từng dòng dần dần giống một iterator từ file đang mở không?

**Trả lời:** Không. Nó đọc toàn bộ nội dung và trả về một `List<String>` chứa tất cả các dòng đã đọc.

**Câu 2.** Một tệp 80 MB trên đĩa có chắc chắn chỉ tiêu tốn 80 MB heap khi dùng `readAllLines` không?

**Trả lời:** Không. Bộ nhớ còn gồm chuỗi đã giải mã, các đối tượng `String`, tham chiếu và danh sách, cộng bộ đệm trung gian; mức tiêu thụ phụ thuộc dữ liệu và JVM.

**Câu 3.** Tại sao `Files.lines(path).toList()` chưa giải quyết vấn đề bộ nhớ?

**Trả lời:** Vì dù việc đọc từ file là lazy, `toList()` thu toàn bộ dòng vào bộ nhớ để trả danh sách.

**Câu 4.** Với `BufferedReader`, khi nào `readLine()` trả `null` và khi nào trả `""`?

**Trả lời:** `null` nghĩa là EOF; `""` nghĩa là đọc được một dòng rỗng hợp lệ.

**Câu 5.** Có cần đóng `List<String>` do `readAllLines` trả về không?

**Trả lời:** Không. Nó chỉ là danh sách trong bộ nhớ; phương thức đã hoàn thành việc đọc. Ngược lại, `Stream<String>` từ `Files.lines` và `BufferedReader` cần được đóng.

**Câu 6.** Nếu tệp có newline cuối cùng, `readAllLines` có luôn thêm một phần tử `""` vào cuối list không?

**Trả lời:** Không. Dấu xuống dòng kết thúc dòng cuối không tự tạo một dòng rỗng mới sau EOF.

**Câu 7.** Khi xử lý dữ liệu ngoài hệ thống và yêu cầu giới hạn tài nguyên nghiêm ngặt, chỉ kiểm tra `Files.size(path)` trước `readAllLines` đã đủ chưa?

**Trả lời:** Chưa. Tệp có thể thay đổi, overhead bộ nhớ không bằng byte-size, và một số nguồn có metadata không phản ánh đầy đủ dữ liệu. Cần giới hạn trong lúc đọc và xử lý.

## 13. Tài liệu tham khảo

- [Java 17 — `Files.readAllLines(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAllLines(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `Files.lines(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `Files.newBufferedReader(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `BufferedReader.readLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())

**Ghi nhớ:** `Files.readAllLines()` là API **eager** và giữ toàn bộ dòng trong `List<String>` ở heap. Nó thuận tiện cho tệp nhỏ, giới hạn rõ. Khi chỉ cần duyệt/lọc/đếm các dòng của tệp lớn, chọn `Files.lines()` hoặc `Files.newBufferedReader()`, đóng tài nguyên đúng lúc và tránh gom kết quả trở lại thành một danh sách khổng lồ.