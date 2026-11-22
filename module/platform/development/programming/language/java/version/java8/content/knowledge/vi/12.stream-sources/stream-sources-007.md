# BufferedReader.lines và Files: tạo Stream từ tệp văn bản trong Java

**Java Stream có thể nhận dữ liệu trực tiếp từ tệp hoặc một `BufferedReader`** thay vì trước hết tải toàn bộ nội dung vào `List`. Hai API nền tảng, được giới thiệu từ **Java 8** và vẫn dùng trong Java hiện đại, là:

- **`BufferedReader.lines()`**: trả `Stream<String>` đọc *các dòng còn lại* từ **reader đã tồn tại**. Người tạo/giữ `BufferedReader` có trách nhiệm quản lý vòng đời reader.
- **`Files.lines(Path)` / `Files.lines(Path, Charset)`**: mở tệp từ `Path` và trả `Stream<String>` đọc dòng **lazily**. Stream **giữ file đang mở**, nên chính stream cần được đóng, tốt nhất với **try-with-resources**.

Hai cách cùng đưa dữ liệu vào pipeline `filter`, `map`, `limit`, `count`, `collect`… nhưng **quyền sở hữu tài nguyên**, **nơi chọn charset**, **exception** và **khả năng chia việc song song** khác nhau. Hiểu các điểm này giúp xử lý file lớn, tránh rò rỉ file descriptor và không ngộ nhận rằng tạo stream là đã đọc xong file.

Bài thuộc chủ đề **Nguồn Stream**. Các quy tắc dưới đây còn áp dụng hiện nay; API có phiên bản bổ sung sau Java 8 được ghi rõ. Chương trình thực hành dùng **JDK 17+**, tạo và dọn tệp tạm, biên dịch/chạy thực tế với stdout xác định.

## 1. Tổng quan luồng dữ liệu

~~~text
                 TỆP VĂN BẢN
                       |
        +--------------+----------------+
        |                               |
 Files.lines(path, UTF_8)      Files.newBufferedReader(path, UTF_8)
        |                               |
 Stream<String>                BufferedReader reader
        |                               |
        |                         reader.lines()
        |                               |
        +---------------+---------------+
                        |
              Stream<String> dòng
                        |
          map / filter / limit / ...
                        |
             terminal operation
            collect / count / reduce
                        |
                  KẾT QUẢ
~~~

**Chữ “lazily”** nghĩa là đối tượng Stream thường chỉ xây dựng pipeline trước; việc lấy dữ liệu xảy ra khi terminal operation tiêu thụ phần tử. Nó **không** nghĩa là file chưa được mở: `Files.lines(...)` mở tài nguyên file khi được gọi và trả về một stream chứa tham chiếu đến file đó. Vì vậy, một stream tạo ra rồi không dùng vẫn cần được đóng.

### Bảng so sánh nhanh

| Tiêu chí | `BufferedReader.lines()` | `Files.lines(Path, Charset)` |
| --- | --- | --- |
| Có gì trước lời gọi? | Một `BufferedReader` đã được mở | Một `Path` và charset |
| Tạo ra | `Stream<String>` các dòng còn lại | `Stream<String>` các dòng trong file |
| Khi đọc dòng? | Trong terminal operation | Lazily khi stream được tiêu thụ |
| Quyền sở hữu resource | **Caller phải đóng reader** | **Caller phải đóng stream** |
| Cách chuẩn đóng | `try (BufferedReader r = ...) { r.lines()... }` | `try (Stream<String> s = Files.lines(...)) { ... }` |
| Charset | Đã được quyết định khi reader được tạo | Truyền `Charset` hoặc dùng overload UTF-8 mặc định |
| Từ Java | 8 | 8 |
| I/O exception khi đang đọc | Thường được bọc thành `UncheckedIOException` từ stream operation | Đọc sau khi mở lỗi sẽ được bọc thành `UncheckedIOException` |
| Lỗi khi mở | Phụ thuộc cách tạo reader, thường `IOException` | `Files.lines` có thể ném `IOException` |
| Khả năng chia parallel work | Spliterator thường khó chia hiệu quả | Có thể chia tốt hơn với một số charset như UTF-8 trên implementation hiện hành |
| Có thể dùng nguồn khác file? | Có, qua reader từ socket/stream/chuỗi tùy ngữ cảnh | Chỉ mở từ file `Path` |
| Cần reader để dùng `readLine` riêng? | Có thể dùng reader, nhưng **không trộn khi stream đang thực thi** | Không cấp một `BufferedReader` riêng cho người gọi |

**Ý chính:** Khi đã có một `BufferedReader` thuộc một workflow I/O khác, `reader.lines()` rất tiện. Khi chỉ có đường dẫn tệp và muốn pipeline dòng, `Files.lines(path, charset)` thường là điểm bắt đầu gọn và đúng với ý định.

## 2. `BufferedReader.lines()` hoạt động thế nào?

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long count = reader.lines()
            .filter(line -> !line.isEmpty())
            .count();
    System.out.println(count);
}
~~~

Đây là **đoạn minh họa nằm trong phương thức**, cần import `java.io.BufferedReader`, `java.nio.file.*`, `java.nio.charset.StandardCharsets` và khai báo `path` hợp lệ. `Files.newBufferedReader` mở một reader với charset chỉ định; `reader.lines()` tạo nguồn Stream từ reader ấy.

Theo API `BufferedReader.lines()`:

1. Các phần tử là **những dòng văn bản còn lại** tính từ vị trí hiện tại của reader.
2. Stream được tạo **lazily**; đọc xảy ra khi terminal operation yêu cầu.
3. Trong khi terminal operation đang thực thi, **không được thao tác reader trực tiếp**; nếu làm, kết quả không được xác định.
4. Sau terminal operation, **không có bảo đảm reader đang ở vị trí ký tự/dòng cụ thể** để tiếp tục `readLine()` một cách suy đoán.
5. Nếu I/O lỗi khi nguồn Stream đọc từ reader, ngoại lệ được bọc trong **`UncheckedIOException`** tại operation gây đọc.

### Ai đóng `BufferedReader`?

**Người sở hữu reader phải đóng reader.** Bản hợp đồng `BufferedReader.lines()` không nói rằng việc hoàn thành terminal operation hoặc `Stream.close()` sẽ tự đóng reader bên dưới. Vì vậy, đừng viết:

~~~java
// Không nên: không quản lý rõ vòng đời reader.
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
reader.lines().forEach(System.out::println);
// reader chưa được đóng chắc chắn.
~~~

Đây là **anti-pattern**, không phải mã đầy đủ khuyến nghị. Dùng try-with-resources cho `BufferedReader`:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
          .map(String::trim)
          .filter(line -> !line.isEmpty())
          .forEach(System.out::println);
}
~~~

`reader.close()` được gọi khi ra khỏi khối try, kể cả khi có exception. Đây là **quyền sở hữu reader**; nếu bạn tạo reader từ một stream/socket mà đối tượng khác sở hữu, cần xác định rõ ai có quyền đóng tài nguyên, tránh đóng ngoài ý muốn.

### Có thể ghép `readLine()` với `lines()` không?

Không được dùng đồng thời trong **quá trình terminal operation** của Stream:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    Stream<String> lines = reader.lines();

    // KHÔNG làm trong một callback đang chạy:
    // lines.forEach(line -> System.out.println(reader.readLine()));

    long count = lines.count();
}
~~~

Comment trên minh họa một việc **không hợp lệ về hợp đồng thao tác**: reader bị can thiệp trong lúc stream đang tiêu thụ nó. Ngoài ra, `reader.readLine()` ném checked `IOException`, khiến ví dụ lambda thẳng như vậy còn cần xử lý exception riêng.

Sau khi đã dùng stream để đọc, việc dựa vào “reader chắc chắn còn đúng n dòng” là không an toàn vì implementation có thể đọc trước. Nếu cần nhiều lượt phân tích độc lập, **mở lại reader/tạo stream mới**. Stream nói chung là **single-use**; không được thực hiện nhiều terminal operations trên cùng một stream.

## 3. `Files.lines`: dòng từ `Path` với vòng đời Stream

Mẫu nên nhớ:

~~~java
Path path = Paths.get("data.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .count();
    System.out.println("nonEmpty=" + count);
}
~~~

Đây là snippet trong một method `throws IOException` hoặc có `catch`, cần các imports tương ứng. `Files.lines` **mở file** và trả Stream đại diện các dòng. Khi khối try kết thúc, `Stream.close()` sẽ đóng nguồn file mà Stream giữ.

Hai overload:

~~~java
Files.lines(path);                         // UTF-8 mặc định
Files.lines(path, StandardCharsets.UTF_8); // Chỉ định tường minh UTF-8
~~~

`Files.lines(Path)` tương đương đọc bằng **UTF-8**, không phụ thuộc charset mặc định của hệ điều hành/JVM. Nếu file sử dụng charset khác, cần dùng overload nhận `Charset` đúng thực tế, chẳng hạn `StandardCharsets.ISO_8859_1`.

**Đừng giả định “dùng default encoding”** rồi gặp lỗi với file được tạo theo quy ước khác. Với hệ thống hiện đại, xác định encoding ngay tại điểm xuất/nhập dữ liệu là thói quen tốt. Khi cần xử lý BOM, dữ liệu bị hỏng hoặc normalizing Unicode, thiết kế riêng chính sách decode; `Files.lines` không phải thư viện parse mọi định dạng văn bản.

### Vì sao phải đóng Stream kể cả khi đã `count()`?

Một terminal operation như `count()` **không thay thế `close()`**. Stream chứa tham chiếu đến file được mở; các resource-backed streams không tự đóng đơn giản vì đã đến terminal operation. Đây là điểm khác so với stream từ `List` hoặc `Stream.of(...)`, vốn thường không nắm file handle.

Sai:

~~~java
long count = Files.lines(path).count();
// Không đảm bảo file được đóng kịp thời.
~~~

Đúng:

~~~java
long count;
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    count = lines.count();
}
~~~

**Quan trọng:** không trả một `Stream<String>` gắn với file đã đóng khỏi một method rồi để nơi khác tiêu thụ:

~~~java
// SAI VỀ LIFECYCLE:
static Stream<String> broken(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines;
    }
}
// Caller nhận stream đã đóng.
~~~

Nếu API buộc trả Stream, bạn phải xác định người gọi sở hữu và phải đóng nó, ví dụ:

~~~java
static Stream<String> openLines(Path file) throws IOException {
    return Files.lines(file, StandardCharsets.UTF_8);
}
~~~

Đây là fragment hợp lệ trong class, nhưng API nên ghi rõ **caller must close**; dùng try-with-resources ở vị trí gọi. Nếu không cần chuyển quyền sở hữu, **tốt hơn là xử lý dữ liệu bên trong scope** rồi trả kết quả đã materialize.

## 4. Phân biệt Stream đọc lazy và List đọc eager

`Files.readAllLines(path, charset)` đọc nội dung thành một `List<String>` trước khi trả kết quả:

~~~java
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_8);
int count = lines.size();
~~~

Trong khi đó:

~~~java
long count;
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    count = lines.count();
}
~~~

| Lựa chọn | Bộ nhớ | Resource | Hợp đồng kết quả |
| --- | --- | --- | --- |
| `Files.readAllLines` | Giữ toàn bộ dòng trong List | File được đóng trong operation | List kết quả sẵn để đọc nhiều lần |
| `Files.lines` + terminal reduction | Có thể giữ ít dữ liệu nếu pipeline/reduction cho phép | Cần đóng Stream | Một phép xử lý lazy qua pipeline |
| `BufferedReader.lines` | Có thể xử lý dần từ reader | Cần đóng reader | Một nguồn Stream từ vị trí reader |
| `Files.lines(...).collect(toList())` | Kết quả vẫn giữ toàn bộ dòng trong List | Cần đóng Stream | Vẫn có kết quả eager sau collect |

**Laziness không có nghĩa chương trình luôn dùng ít RAM.** Nếu gọi `collect(Collectors.toList())` để lưu toàn bộ file, bạn vẫn cần bộ nhớ tỷ lệ với số dòng/kích thước dữ liệu. Ưu điểm của Stream rõ hơn với các terminal operations có thể gom thành tổng/đếm, tìm kiếm sớm, xử lý từng dòng hoặc giảm lưu dữ liệu.

Nếu file nhỏ và người dùng cần truy cập nhiều lần theo index, `Files.readAllLines` dễ đọc, phù hợp hơn. Với file lớn hoặc nguồn liên tục, `Files.lines` thường giúp giảm việc lưu toàn bộ dữ liệu — nhưng điều này còn phụ thuộc vào pipeline cụ thể. Các stage như `sorted()` có thể buffer đáng kể.

### API `Files.readString` và `String.lines` không phải Java 8

Từ **Java 11** có thêm:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);
Stream<String> lines = content.lines();
~~~

`Files.readString` đọc toàn bộ file thành một chuỗi; `String.lines()` là Stream từ dữ liệu **đã nằm trong bộ nhớ**, không trực tiếp giữ file handle. Cả hai đều là lựa chọn hợp lệ với đầu vào nhỏ khi toàn bộ chuỗi có giá trị cho nghiệp vụ. Nếu dự án target Java 8, **không sử dụng** hai method Java 11 này.

Không coi `String.lines()` và `Files.lines()` giống nhau về **ownership**: String là object trong bộ nhớ; `Files.lines` đang mở file.

## 5. Cách các dòng được tách và giữ dữ liệu

`BufferedReader.readLine()` và `Files.readAllLines` nhận diện những line terminators thông dụng:

- LF: `\n`.
- CR: `\r`.
- CRLF: `\r\n`.

Một dòng kết quả không chứa ký tự kết thúc dòng. Trong ví dụ:

~~~text
Lan,12
Binh,7

An,21
~~~

sau khi đọc, dòng trống giữa `Binh` và `An` là một chuỗi `""`. Không nên nhầm một dòng trống với `null` (giá trị báo hết file khi gọi `readLine()`).

Ví dụ pipeline loại dòng rỗng và comment:

~~~java
List<String> data;
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    data = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .filter(line -> !line.startsWith("#"))
            .collect(Collectors.toList());
}
~~~

Các bước có ý nghĩa rõ: **bỏ khoảng trắng ở hai đầu → loại dòng rỗng → loại comment → thu thập dòng hợp lệ**. Đây là lọc text, **không phải parse CSV đúng nghĩa**. Nếu file là CSV có dấu ngoặc kép, dấu phẩy trong field hoặc newline trong field trích dẫn, một line không tương đương một record và cần parser CSV thực sự.

### Thận trọng với dòng cuối

Một file kết thúc bằng newline thông thường **không nhất thiết tạo thêm một phần tử chuỗi rỗng** ở cuối chỉ vì có terminator cuối. Nhưng **một dòng rỗng thực sự** giữa hai terminators vẫn được biểu diễn. Hãy test cụ thể với format của ứng dụng nếu phân biệt dòng trống cuối là quan trọng. Nếu cần bảo tồn **chính xác từng byte và kiểu line ending** (CRLF vs LF), `lines()` không phù hợp vì nó **loại bỏ terminators**; đọc byte/character stream với parser chuyên dụng.

### `trim` và `strip` không giống nhau

Trong ví dụ Java 8, `String.trim()` được dùng để loại các khoảng trắng thông thường. Từ Java 11, `String.strip()` xử lý khoảng trắng theo `Character.isWhitespace`, thường hữu ích hơn với nhiều ký tự Unicode nhưng không hoàn toàn tương đương `trim()`. Chọn theo hợp đồng dữ liệu và JDK mục tiêu; không đổi qua lại bừa bãi trong ứng dụng có input quốc tế.

## 6. Exception: tách “mở tệp” và “đọc khi stream chạy”

Một bẫy của lazy I/O là thời điểm exception.

### Khi mở `Files.lines`

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    System.out.println(lines.count());
} catch (IOException ex) {
    System.err.println("Không mở/đóng file được: " + ex.getMessage());
}
~~~

Đây là **mẫu minh họa**. `Files.lines` khai báo `throws IOException` khi mở file; `try-with-resources` còn bảo đảm close khi rời khối. Tuy nhiên, lỗi đọc **sau khi mở** không nhất thiết xuất hiện dưới dạng checked IOException trực tiếp.

### Khi terminal operation đọc dữ liệu

Javadoc mô tả rằng lỗi I/O trong quá trình lấy dòng sau khi stream đã tạo, hoặc lỗi decode charset tương ứng, được bọc thành `UncheckedIOException` từ operation đã kích hoạt việc đọc.

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    System.err.println("Lỗi đọc/giải mã sau khi mở: " + ex.getCause());
} catch (IOException ex) {
    System.err.println("Lỗi mở file: " + ex);
}
~~~

Để chạy fragment cần import `java.io.*`, `java.nio.file.*` và `java.util.stream.*`. Trong ứng dụng thực tế, lựa chọn ghi log, trả lỗi cho người dùng hoặc retry tùy loại storage, idempotency và tính toàn vẹn của kết quả đã xử lý.

Với `BufferedReader.lines()`, một `IOException` xảy ra khi Stream đọc từ reader cũng được bọc thành `UncheckedIOException`. Chính phương thức `reader.lines()` không khai báo checked `IOException` cho phép xử lý các callback theo Stream API, nhưng không xóa bỏ khả năng lỗi I/O lúc runtime.

### Đừng “nuốt” UncheckedIOException

Không viết pipeline trả kết quả một phần nhưng âm thầm bỏ lỗi nếu ứng dụng cần hoàn chỉnh tất cả dữ liệu. Ví dụ tính tổng doanh thu từ file: nếu I/O hỏng sau nửa file, tổng tạm thời **không được** coi là tổng đầy đủ. Nếu cần partial-results semantics, hãy nêu rõ chúng và lưu checkpoint/diagnostics phù hợp.

### Malformed input / charset

Nếu file UTF-8 chứa byte không hợp lệ, việc xử lý trong `Files.lines(path, UTF_8)` có thể dẫn tới `UncheckedIOException` khi terminal operation giải mã. `Files.readAllLines` là thao tác đọc eager nên có thể báo `IOException` trong chính lời gọi. Không giả định mọi decode error đều biểu hiện giống nhau trên mọi API.

Dùng charset explicit, kiểm tra nguồn dữ liệu và nêu chính sách lỗi. **Đừng tự đổi sang charset khác** trong catch để “chữa” file mà không có bằng chứng format, vì có thể khiến dữ liệu bị biến dạng âm thầm.

## 7. Chọn `Files.newBufferedReader` + `lines` khi cần quyền điều khiển reader

`Files.newBufferedReader(path, charset)` có vai trò mở reader có bộ đệm. Sau đó ta dùng được cả `readLine()` lẫn `lines()`, nhưng **không trộn thao tác trong khi terminal operation đang thực thi**.

Một use case hợp lý là đọc riêng header **trước** rồi chỉ stream những dòng còn lại:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String header = reader.readLine();
    if (header == null) {
        throw new IllegalArgumentException("File rỗng");
    }

    long dataLines = reader.lines()
            .filter(line -> !line.trim().isEmpty())
            .count();
    System.out.println("header=" + header + ", dataLines=" + dataLines);
}
~~~

Đây là fragment trong method có `throws IOException`. `readLine()` tiêu thụ đúng **một dòng trước khi** Stream được tạo và chạy. `lines()` chỉ cung cấp những dòng **còn lại**. Sau khi Stream hoàn tất, khối try đóng reader; không cố tiếp tục dựa vào vị trí nội bộ.

Nếu cần đọc header và dữ liệu trong cùng một định dạng phức tạp, nên dùng parser chuyên dụng; mẫu trên chỉ minh họa xử lý file dòng đơn giản.

### Có thể dùng `BufferedReader.lines` với nguồn không phải file

Một `BufferedReader` được tạo từ `Reader` khác, ví dụ:

~~~java
try (BufferedReader reader =
         new BufferedReader(new StringReader("red\nblue\n"))) {
    reader.lines().forEach(System.out::println);
}
~~~

Đây là **đoạn độc lập trong method** với imports `java.io.*`. `StringReader` không nắm file handle, nhưng vẫn minh họa rằng `BufferedReader.lines` có thể đọc từ Reader bất kỳ. Khi nguồn thực là socket, HTTP response stream hoặc pipe, trách nhiệm đóng tài nguyên bên dưới cần được quy định chặt chẽ.

**Phân biệt:** `Files.lines` luôn liên quan đến đường dẫn file, không phải API đọc trực tiếp `InputStream` tùy ý. Nếu đã có `InputStream`, hãy bọc `InputStreamReader` với charset được chọn và `BufferedReader`, quản lý resource ownership đúng cách.

## 8. `Files` còn cung cấp các nguồn Stream khác

“Files” trong đề bài không chỉ có `Files.lines`. Java NIO.2 có các phương thức sinh Stream từ hệ thống tệp:

| API | Phần tử Stream | Tình huống |
| --- | --- | --- |
| `Files.lines(path)` | `String` | Các dòng của một tệp văn bản |
| `Files.list(dir)` | `Path` | Các entry trực tiếp trong thư mục |
| `Files.walk(start)` | `Path` | Duyệt cây thư mục, bao gồm điểm bắt đầu |
| `Files.walk(start, maxDepth)` | `Path` | Giới hạn độ sâu duyệt cây |
| `Files.find(start, maxDepth, matcher)` | `Path` | Duyệt cây và lọc bằng attributes |
| `Files.readAllLines(path)` | **`List<String>`, không phải Stream trực tiếp** | Tệp nhỏ cần giữ mọi dòng trong RAM |

Các phương thức `Files.list`, `walk`, `find` tạo nguồn Stream **gắn với tài nguyên thư mục** nên cũng cần **try-with-resources**, như `Files.lines`.

Ví dụ liệt kê file con trực tiếp:

~~~java
try (Stream<Path> children = Files.list(dir)) {
    List<String> names = children
            .map(path -> path.getFileName().toString())
            .sorted()
            .collect(Collectors.toList());
    System.out.println(names);
}
~~~

`Files.list` **không duyệt đệ quy**. Nếu muốn mọi cấp, `Files.walk`; nếu chỉ quan tâm độ sâu hữu hạn, `Files.walk(dir, 1)` thường tương ứng “điểm bắt đầu và các entry ở mức một cấp”, chứ không chỉ con mà bỏ root. File system provider có thể có các hạn chế/quy tắc riêng; `Files.walk` gặp I/O lỗi trong lúc duyệt có thể ném `UncheckedIOException`.

### `Files.find` / `Files.walk` và hiệu năng

`Files.find(start, maxDepth, matcher)` cho predicate có thể xét `Path` và `BasicFileAttributes`, hữu ích nếu muốn lọc theo loại file/size mà không mở tệp nội dung. Nhưng **đừng đọc nội dung hàng triệu file bằng stream song song vô giới hạn** nếu có ràng buộc file descriptors, disk throughput hoặc permission. Thiết kế batch/resource budget và xử lý lỗi rõ ràng.

### Khi cần “dòng của nhiều tệp”

Có thể lấy các `Path` từ `Files.list` rồi mở `Files.lines` từng file; nhưng một pipeline kiểu:

~~~java
try (Stream<Path> paths = Files.list(dir)) {
    paths.flatMap(path -> {
        try {
            return Files.lines(path);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }).forEach(System.out::println);
}
~~~

là **mẫu minh họa nâng cao**. `flatMap` trong Stream API sẽ đóng mỗi mapped stream khi nó đã được tiêu thụ/đóng theo contract, nhưng toàn bộ pipeline vẫn cần quản lý stream thư mục ngoài cùng. Trong thực tế nên **lọc file thực** (tránh thư mục, symlink không mong muốn), xác định cách xử lý lỗi từng tệp, charset, ordering, cancellation và rủi ro mở nhiều tài nguyên cùng lúc.

Một vòng lặp dễ hiểu với try-with-resources riêng cho từng file thường là lựa chọn tốt hơn khi có nhiều chính sách I/O phức tạp:

~~~java
try (Stream<Path> paths = Files.list(dir)) {
    List<Path> files = paths
            .filter(Files::isRegularFile)
            .sorted()
            .collect(Collectors.toList());

    for (Path file : files) {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            lines.forEach(System.out::println);
        }
    }
}
~~~

Đây là fragment thực dụng (cần imports, `dir` và `throws IOException`), minh họa phân cấp scope tài nguyên: Stream thư mục đóng ở khối ngoài, Stream mỗi file đóng sau một lần xử lý. Nếu file listing cực lớn, `collect(toList())` ở đây có thể tốn bộ nhớ; lựa chọn duyệt trực tiếp cần cân bằng IO/resource và xử lý checked exceptions.

## 9. Parallel Stream: không phải mọi nguồn tệp chia tốt như nhau

Từ góc nhìn người dùng:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long matches = lines.parallel()
            .filter(line -> line.contains("ERROR"))
            .count();
}
~~~

Cú pháp hợp lệ, nhưng **parallel không luôn nhanh hơn sequential**. Với I/O và decode, throughput có thể bị giới hạn bởi disk, file size, charset hoặc việc chia đoạn của `Spliterator`.

Theo Java `Files.lines(Path, Charset)` hiện hành, implementation có thể hỗ trợ chia tốt với các charset “line-optimal” như **UTF-8, US-ASCII, ISO-8859-1**. Với một số charset khác, spliterator có thể chia kém, tương tự nguồn từ `BufferedReader.lines()`.

**Tuy vậy, đây là đặc điểm implementation có tài liệu mô tả, không phải bảo đảm mọi lần chạy parallel luôn cải thiện latency**. Benchmark với file, filesystem, charset, kích thước dòng và workload thực tế. Các hàm truyền vào `map`/`filter` cũng cần không can thiệp source và không phụ thuộc mutable external state.

### Điều gì xảy ra với thứ tự?

Nếu pipeline đọc các dòng có encounter order, các operations như `collect(Collectors.toList())` có thể giữ thứ tự kết quả khi stream vẫn ordered; nhưng những callback được chạy bởi `parallel` không nhất thiết theo đúng thứ tự từng dòng. Đừng ghi audit bằng `parallel().forEach(...)` rồi kỳ vọng log có cùng thứ tự file.

Nếu thứ tự output thực sự quan trọng, dùng mô hình tuần tự hoặc `forEachOrdered` với hiểu biết về chi phí. Nếu mục tiêu chỉ là tính count, sum hoặc grouping từ những hàm stateless, nhiều phép reduction có thể parallelize theo contract; nhưng vẫn cần kiểm thử correctness và benchmark.

## 10. Rủi ro file lớn, tệp đang bị sửa và độ ổn định dữ liệu

### Stream không chụp snapshot của file

`Files.lines` và `BufferedReader.lines` cung cấp dữ liệu từ nguồn được đọc theo thời gian. Nếu file bị sửa giữa lúc terminal operation đang chạy, **không có bảo đảm một snapshot nhất quán**. Với `Files.lines`, tài liệu nói không nên sửa nội dung tệp trong khi terminal operation thực hiện; nếu sửa, kết quả có thể không xác định.

Khi cần dữ liệu cố định:
- Phối hợp với writer bằng file naming/atomic rename hoặc hợp đồng publication phù hợp.
- Đọc từ bản sao/phiên bản bất biến được chốt.
- Dùng cơ chế locking/transactional storage khi môi trường cần.
- Xử lý retry nếu phát hiện file bị sửa hay dữ liệu thiếu, nhưng không làm mất lỗi âm thầm.

**Không** giải quyết bằng việc chỉ đổi `Files.lines` thành `Files.readAllLines` nếu writer vẫn sửa file đồng thời trong lúc đọc; việc đọc eager không mặc nhiên đảm bảo snapshot atomic.

### Stream lớn vẫn có thể tạo lượng dữ liệu lớn

Ví dụ:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    List<String> all = lines.collect(Collectors.toList());
}
~~~

Kết quả sẽ lưu tất cả dòng trong List — có thể chiếm nhiều bộ nhớ như `readAllLines`. Với file lớn, nếu chỉ cần đếm những dòng hợp lệ:

~~~java
long validCount;
try (Stream<String> lines = Files.lines(path)) {
    validCount = lines.filter(line -> !line.isEmpty()).count();
}
~~~

Lúc đó không giữ toàn bộ dòng trong một List chỉ để đếm. Nhưng cũng không được khẳng định luôn O(1) memory cho mọi pipeline: `sorted`, `distinct`, `groupingBy` hoặc collectors chứa dữ liệu vẫn có state.

### Đọc file ngoài hệ thống tin cậy

Nếu `Path` đến từ đầu vào người dùng, cần có các kiểm tra truy cập và canonicalization/capability-based access phù hợp để tránh path traversal, mở đường dẫn ngoài phạm vi được phép hoặc theo symlink ngoài ý muốn. `Files.lines` **không tự kiểm tra policy truy cập nghiệp vụ**. Với log/csv lớn từ nguồn không tin cậy, nên giới hạn kích thước, số dòng, độ dài dòng, charset và ngân sách xử lý.

Một dòng cực dài vẫn có thể tốn bộ nhớ dù tổng file được stream lazily, vì một phần tử String đại diện **cả một dòng**. Nếu cần hard limit theo byte/character hoặc xử lý record nhiều gigabyte, phải dùng parser/Reader đọc theo khối thay vì nghĩ `lines()` tự giới hạn từng dòng.

## 11. Chương trình Java 17 hoàn chỉnh và đã chạy thực tế

Chương trình tự tạo một thư mục và file UTF-8 tạm, thử `Files.lines` với charset tường minh, `BufferedReader.lines`, overload UTF-8 mặc định, `Files.readAllLines`, `Files.list` và `Files.walk`; sau đó dọn tài nguyên trong `finally`. Việc chỉ in **tên file**, không in đường dẫn tạm, giúp stdout ổn định giữa máy chạy.

Lưu thành **FileLineSourcesDemo.java**:

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class FileLineSourcesDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("line-stream-demo-");
        Path file = dir.resolve("records.txt");
        try {
            Files.write(file, Arrays.asList(
                    "# inventory", " Lan,12 ", "Binh,7", "", "An,21"),
                    StandardCharsets.UTF_8);

            try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
                List<String> rows = lines.map(String::trim)
                        .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                        .collect(Collectors.toList());
                System.out.println("rows=" + rows);
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                long count = reader.lines().map(String::trim)
                        .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                        .count();
                System.out.println("bufferedRows=" + count);
            }

            try (Stream<String> lines = Files.lines(file)) {
                System.out.println("utf8Default=" + lines.count());
            }

            List<String> eager = Files.readAllLines(file, StandardCharsets.UTF_8);
            System.out.println("eagerLines=" + eager.size());

            try (Stream<Path> children = Files.list(dir)) {
                List<String> names = children
                        .map(path -> path.getFileName().toString())
                        .sorted()
                        .collect(Collectors.toList());
                System.out.println("children=" + names);
            }

            try (Stream<Path> tree = Files.walk(dir, 1)) {
                System.out.println("walkDepth1=" + tree.count());
            }

            System.out.println("checks=PASS");
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 FileLineSourcesDemo.java
java FileLineSourcesDemo
~~~

Stdout chính xác **đã xác minh bằng biên dịch và thực thi**:

~~~text
rows=[Lan,12, Binh,7, An,21]
bufferedRows=3
utf8Default=5
eagerLines=5
children=[records.txt]
walkDepth1=2
checks=PASS
~~~

### Đọc kết quả

1. **`rows`:** file có năm dòng: comment, dòng Lan, dòng Binh, một dòng trống, dòng An. `map(String::trim)` và filter bỏ comment/rỗng nên còn ba chuỗi `Lan,12`, `Binh,7`, `An,21`. `List.toString()` dùng dấu phẩy giữa các phần tử; trong mỗi phần tử mẫu cũng có dấu phẩy giữa tên và số nên output đọc thủ công có thể trông như nhiều trường hơn — số phần tử thực là ba.
2. **`bufferedRows=3`:** `BufferedReader.lines()` với cùng rule lọc trả cùng số dòng dữ liệu; reader được đóng bằng try-with-resources.
3. **`utf8Default=5`:** `Files.lines(file)` dùng UTF-8 và không loại các dòng trước khi count, nên thấy đủ năm.
4. **`eagerLines=5`:** `Files.readAllLines` đọc mọi dòng vào List; số phần tử bằng năm trong file ví dụ.
5. **`children=[records.txt]`:** `Files.list(dir)` liệt kê entry trực tiếp và trả `Path`; mapping lấy filename, không phải nội dung file.
6. **`walkDepth1=2`:** `Files.walk(dir, 1)` gồm chính thư mục gốc (depth 0) và file con (depth 1), nên đếm bằng hai.
7. **`checks=PASS`:** mọi operation chạy xong bình thường. Ví dụ không giả lập lỗi I/O hoặc charset; những nhánh lỗi cần được test riêng khi nghiệp vụ đòi độ tin cậy cao.

### Lưu ý về finally

`finally` xóa file rồi xóa directory. Trong demo bình thường, mọi nguồn I/O đã được đóng trước khi delete nên thao tác này hoàn tất. Nếu lỗi mở/đóng file hoặc môi trường không cho xóa, `Files.deleteIfExists` cũng có thể ném `IOException`. Với test production, nên dùng utility dọn tệp tạm có xử lý failures/suppressed exceptions theo quy chuẩn test framework; đừng để cleanup error che hoàn toàn nguyên nhân lỗi chính.

## 12. Khi nào chọn API nào?

| Yêu cầu thực tế | Gợi ý | Lý do |
| --- | --- | --- |
| Có `Path` tới tệp text lớn, muốn lọc/count/sum | `try (Stream<String> s = Files.lines(path, cs))` | Nguồn lazy; đóng file bằng stream |
| Đã sở hữu `BufferedReader` từ nơi khác | `reader.lines()` trong scope reader | Tận dụng reader, quản lý lifecycle tại nơi sở hữu |
| Cần đọc header rồi stream phần còn lại | `reader.readLine()` trước, sau đó `reader.lines()` | Reader giữ vị trí từ phần đã đọc |
| Tệp nhỏ, cần đọc nhiều lần/index | `Files.readAllLines(path, cs)` | List eager, file đóng trong lời gọi |
| Tệp nhỏ, cần toàn bộ text nguyên gốc | `Files.readString(path, cs)` (Java 11+) | Trả chuỗi; không phải stream line-based |
| Chuỗi đã có trong bộ nhớ, muốn từng dòng | `String.lines()` (Java 11+) | Không mở thêm file |
| Liệt kê file trực tiếp trong thư mục | `Files.list(dir)` | Stream<Path>, không đệ quy |
| Duyệt directory tree | `Files.walk(start[,depth])` | Stream<Path>, có resource; cần đóng |
| Duyệt và xét attributes | `Files.find(...)` | Có matcher và BasicFileAttributes |
| Muốn giữ nguyên CRLF/LF và từng byte | `InputStream`/`Reader` custom parser | `lines` bỏ line terminators |
| Cần xử lý CSV có quoted newline | CSV parser có hỗ trợ record multiline | Một line không luôn bằng một record |
| Gặp malformed charset | Đọc với charset đúng và policy lỗi rõ | Không âm thầm đổi charset |
| Nhiều file phải đọc tuần tự | `Files.list` + từng `Files.lines` trong try riêng | Resource scope dễ hiểu |

**Không phải** vì dùng Stream nên tự động nên chạy parallel. Với xử lý I/O tuần tự, đơn giản và có side effects bắt buộc, code với BufferedReader và vòng lặp `readLine` vẫn có thể đúng, dễ debug hơn một pipeline phức tạp. Chọn công cụ phù hợp với semantics chứ không chạy theo độ ngắn của cú pháp.

## 13. Những lỗi phổ biến cần tránh

| Hiểu nhầm hoặc anti-pattern | Rủi ro | Cách đúng |
| --- | --- | --- |
| `Files.lines(path).count()` không đóng stream | File descriptor giữ lâu | Try-with-resources cho `Stream` |
| `reader.lines()` xong thì reader tự đóng | Không có bảo đảm như vậy | Try-with-resources cho `BufferedReader` |
| `Files.lines` “chỉ mở file tại terminal” | File được mở khi gọi Files.lines | Đóng stream ngay cả khi chưa consume |
| Dùng `-parameters` hoặc flag compiler để giải quyết lỗi file I/O | Không liên quan | Kiểm tra Path, charset, permission, resource scope |
| Trộn `readLine` với stream terminal | Can thiệp trạng thái nguồn | Đọc header trước khi tạo pipeline; không thao tác đồng thời |
| Coi Stream dùng được nhiều lần | `IllegalStateException` trong nhiều trường hợp | Tạo stream mới cho mỗi lượt |
| Đọc `Files.lines` mà mặc định system encoding | Overload mặc định **UTF-8** | Ghi charset rõ hoặc xác nhận UTF-8 |
| `readAllLines` luôn tiết kiệm RAM | Đọc toàn file vào List | Stream + reduction khi không cần lưu |
| `Files.lines(...).collect(toList())` luôn ít RAM | Vẫn tích lũy tất cả | Chọn terminal operation theo nhu cầu |
| Coi từng dòng là CSV record hoàn chỉnh | Quoted newline/commas có thể xuất hiện | Dùng CSV parser |
| Coi `readLine` giữ ký tự `\n`/`\r` | Terminators bị loại | Dùng parser byte/char nếu cần nguyên bản |
| Bỏ qua `UncheckedIOException` | Lỗi đọc xảy ra sau khi mở | Bắt/xử lý đọc và giải mã đúng |
| Dùng `peek` để ghi audit bắt buộc | Stage có thể bị tối ưu bỏ | Tách side effect nghiệp vụ |
| Dùng `parallelStream` để đọc file bất kỳ | Có thể chậm hơn hoặc sai ordering | Benchmark, hiểu splitting & thread safety |
| Không đóng `Files.walk`/`Files.list` | Tài nguyên thư mục bị giữ | Try-with-resources cho stream Path |
| Truy cập file ngoài vùng được phép | Path traversal/symlinks | Ràng buộc đường dẫn theo security policy |
| Đọc file đang bị ghi và mong snapshot | Có thể ra dữ liệu không nhất quán | Chốt bản phát hành/snapshot và phối hợp writer |
| Trả Stream sau khi đóng trong method | Caller nhận stream không dùng được | Chuyển ownership rõ, hoặc materialize result trước |
| Dùng `String.lines()` rồi bảo đó là Java 8 | API bổ sung Java 11 | Ghi version hoặc dùng Java 8 API |
| Dựa vào thứ tự `Files.list` | Order không được cam kết | `sorted()` khi cần thứ tự tên |
| Dùng `count()` rồi suy ra các side effects trong `map` luôn chạy | Stream có quyền tối ưu stage không ảnh hưởng count | Không dùng intermediate side effects để đảm bảo nghiệp vụ |

## 14. Checklist cho code review

1. **Nguồn là Path hay BufferedReader?** Ai có trách nhiệm close?
2. **Try-with-resources bao đúng resource sở hữu?** `Files.lines` -> Stream; `reader.lines` -> Reader.
3. **Charset được xác định?** Overload `Files.lines(path)` là UTF-8.
4. **Dữ liệu có khả năng lớn?** Có lưu toàn bộ vào List hoặc String không?
5. **Các terminal operations có làm I/O thực sự?** Exception có thể đến muộn.
6. **Có bắt/xử lý `UncheckedIOException` nếu cần?** Không bỏ qua dữ liệu thiếu.
7. **Có trộn `readLine` trong lúc đang chạy stream không?** Nếu có, cần sửa.
8. **Có dùng stream lại?** Mỗi pipeline tiêu thụ một lần.
9. **Có dựa vào thứ tự `Files.list` hay parallel callbacks?** Xác định ordering contract.
10. **Có cần bảo toàn dòng trống, line terminator hoặc byte content không?** `lines` có giới hạn.
11. **Có parse CSV/JSON/XML thật không?** Mỗi dòng chưa chắc là một record.
12. **Tệp đang bị thread/process khác ghi?** Cần nguồn nhất quán.
13. **Có ràng buộc Path theo quyền truy cập?** Xử lý symlink/path traversal.
14. **Có đóng `Files.list`, `walk`, `find`?** Chúng cũng nắm resource.
15. **Có unit test cho file rỗng, một dòng, nhiều dòng, CRLF, UTF-8, malformed bytes và I/O failure?** Test những trường hợp thực tế.
16. **Các API có tương thích target JDK?** `Files.lines`/`BufferedReader.lines` Java 8; `Files.readString`/`String.lines` Java 11.
17. **Có benchmark trước khi parallelize file I/O?** Performance không đoán bằng cú pháp.
18. **Test có xác minh resource được đóng kể cả khi throw?** Dùng test file temp/Reader theo yêu cầu.

## 15. Bài tập thực hành

1. Viết hàm `long countNonBlank(Path file)` bằng `Files.lines(file, UTF_8)`; đóng Stream đúng và xử lý `IOException`.
2. Viết hàm tương tự từ `BufferedReader` do caller sở hữu. Theo hợp đồng, method nào được phép đóng reader?
3. Tạo file gồm `"a\nb\n"`, đếm dòng. Vì sao ký tự newline cuối không nhất thiết tạo thêm phần tử trống?
4. Tạo file có dòng trống giữa hai dòng dữ liệu, dùng `filter(String::isEmpty)` và đếm. Nếu muốn bỏ dòng chỉ chứa khoảng trắng, cần thêm bước gì?
5. Dùng `Files.readAllLines` và `Files.lines` so sánh memory/lifecycle, rồi giải thích vì sao `Files.lines(...).collect(toList())` vẫn giữ toàn bộ kết quả.
6. Đọc header bằng `BufferedReader.readLine()` trước khi gọi `reader.lines()`; xác minh stream chỉ chứa các dòng còn lại.
7. Thử dùng `reader.readLine()` trong callback Stream và giải thích vi phạm hợp đồng; không đưa anti-pattern vào code production.
8. Tạo file Latin-1 có ký tự đặc biệt; đọc bằng `Files.lines(path, ISO_8859_1)`. Điều gì xảy ra nếu decode sai bằng UTF-8?
9. Thử mở file không tồn tại và xác minh `Files.lines` có thể ném checked `IOException`.
10. Viết custom Reader gây `IOException` sau một số dòng; quan sát cách `BufferedReader.lines()` bọc thành `UncheckedIOException` khi terminal operation chạy.
11. Dùng `Files.list` liệt kê các file trực tiếp trong directory, sort theo tên; phân biệt với `Files.walk(dir,1)`.
12. Với file tree có subfolder, dùng `Files.walk(dir)` và lọc `Files::isRegularFile`, rồi đóng stream.
13. So sánh `Files.lines(path).parallel().count()` và phiên bản sequential trên dữ liệu đủ lớn, benchmark thay vì mặc định parallel nhanh.
14. Dùng `try (Stream<String> s = Files.lines(path))` rồi cố gọi terminal operation sau khi khối try đóng, giải thích vì sao sai.
15. Viết một hàm trả List các dòng hợp lệ thay vì trả Stream gắn với reader đã đóng. Đánh đổi bộ nhớ/ownership như thế nào?
16. Dùng log file có `ERROR` và `INFO`, đếm `ERROR` bằng `filter`, không lưu mọi dòng.
17. Xây một test cho file đang bị writer sửa trong khi đọc: vì sao không nên dựa vào output ổn định? Cách nào tạo snapshot an toàn?
18. Nếu đọc CSV có trường chứa newline trong dấu ngoặc kép, vì sao `Files.lines` không thể tự tái dựng record? Dùng loại parser nào phù hợp?

## 16. Tài liệu chính thức, áp dụng cho Java hiện nay

- [Oracle Java SE 26 — BufferedReader.lines()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html#lines())
- [Oracle Java SE 26 — Files.lines(Path, Charset)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset))
- [Oracle Java SE 26 — Files.lines(Path)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path))
- [Oracle Java SE 17 — Files and NIO.2](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Oracle Java SE 17 — Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Oracle Java SE 17 — UncheckedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html)
- [Oracle Java SE 17 — AutoCloseable và try-with-resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)

**Kết luận:** `BufferedReader.lines()` và `Files.lines(...)` đều cung cấp **nguồn Stream<String> lazy** để xử lý các dòng văn bản trong Java. **Khác biệt quyết định** là ownership: với `BufferedReader.lines()` hãy đóng **reader**; với `Files.lines()` hãy đóng **stream**. Chọn charset phù hợp, hiểu `UncheckedIOException` có thể xuất hiện muộn, không lạm dụng parallel và không coi `lines()` là parser định dạng phức tạp hay snapshot bất biến. Khi được dùng đúng scope và theo hợp đồng, hai API vẫn là công cụ thiết thực trong Java hiện đại.
