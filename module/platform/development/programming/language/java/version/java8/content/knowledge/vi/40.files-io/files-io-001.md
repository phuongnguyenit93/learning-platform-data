# BufferedReader.lines() và nguồn dữ liệu lười trong Java 8+

## 1. Bài toán: xử lý tệp theo dòng mà không nạp trước toàn bộ nội dung

Một ứng dụng nhận log, file cấu hình, CSV đơn giản hoặc dữ liệu xuất từ hệ thống khác. Ta muốn lọc những dòng hợp lệ, biến đổi nội dung và tổng hợp kết quả. Nếu tệp rất lớn, cách đọc toàn bộ bằng **Files.readAllLines(...)** có thể tiêu tốn nhiều bộ nhớ vì mọi dòng được lưu vào một collection trước khi xử lý.

Từ Java 8, **BufferedReader.lines()** trả một **Stream<String>**, cho phép dựng một pipeline xử lý theo dòng:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long nonEmptyLines = reader.lines()
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .count();
    System.out.println(nonEmptyLines);
}
~~~

Đây là đoạn minh họa **bên trong một method** có biến path kiểu Path và các import java.io.*, java.nio.file.*, java.nio.charset.*, java.util.stream.*; không phải chương trình độc lập.

**Điểm mấu chốt: Stream chỉ mô tả các bước trước khi có terminal operation.** Lời gọi reader.lines() và các bước map/filter không tự đọc toàn bộ tệp. Việc lấy từng dòng diễn ra khi một terminal operation như count, collect, forEach, findFirst hoặc anyMatch tiêu thụ pipeline.

Bài tập trung vào **bản chất nguồn dữ liệu lười**, thời điểm I/O xảy ra, vòng đời BufferedReader, ngoại lệ khi đọc, việc dùng Stream đúng một lần, khác biệt với Files.lines và các lỗi thường gặp. Tất cả API cơ bản ở đây đã có từ Java 8, **vẫn còn được hỗ trợ trong Java SE hiện hành**; những tính năng Java mới hơn được đánh dấu rõ.

## 2. BufferedReader.lines() thực sự trả về gì?

Trong **java.io.BufferedReader**, chữ ký là:

~~~java
public Stream<String> lines()
~~~

Kết quả là một **Stream<String>** mà mỗi phần tử là một dòng văn bản từ BufferedReader. Phương thức có từ **Java 8 (since 1.8)**.

Dòng được hiểu theo quy tắc đọc của BufferedReader.readLine(): phần kết thúc dòng (line terminator) **không nằm trong String trả về**. Dòng trống vẫn có thể trở thành String rỗng. Dòng cuối cùng **không cần có ký tự xuống dòng** để được đọc.

Ví dụ một nguồn gồm ba dòng:

~~~text
alpha

beta
~~~

Khi được duyệt, stream có thể cung cấp tuần tự các phần tử:

~~~text
"alpha"
""
"beta"
~~~

Khi nguồn hết, readLine() trả null, và Stream kết thúc. **Điều này không có nghĩa Stream được phép chứa null như một dòng dữ liệu cuối**: null ở đây là tín hiệu kết thúc từ bộ đọc, không phải phần tử nghiệp vụ.

**Đọc theo dòng** không đồng nghĩa tách text bằng biểu thức đơn giản chỉ nhận LF. BufferedReader hiểu các dấu kết thúc dòng được API định nghĩa. Nếu cần giữ byte, giữ dấu xuống dòng gốc hoặc phân biệt LF/CRLF chính xác, xử lý theo **BufferedReader.lines()** có thể làm mất thông tin đó; phải chọn cách đọc ở mức ký tự/byte thích hợp.

## 3. Lazy source, intermediate operations và terminal operation

Một pipeline:

~~~java
Stream<String> pipeline = reader.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty());
~~~

Chỉ mới tạo ra **mô tả công việc**; chưa có terminal operation. Việc gọi **map**, **filter**, **limit**, **distinct** hoặc **sorted** để dựng pipeline không có nghĩa tất cả dữ liệu đã được đọc.

Khi gọi:

~~~java
long count = pipeline.count();
~~~

Stream bắt đầu lấy dữ liệu từ BufferedReader theo nhu cầu, chạy các bước biến đổi/lọc và trả một kết quả cuối.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Nguồn | reader.lines() | Tạo Stream<String> được nạp lười từ reader |
| Intermediate | map, filter, limit | Mô tả cách biến đổi/chọn dòng |
| Terminal | count, collect, forEach | Kích hoạt tiêu thụ nguồn và tạo kết quả/side effect |

**Lazy không có nghĩa mọi terminal operation đều đọc ít dữ liệu.** count thường cần đọc tới hết nguồn. collect(toList()) cũng tiêu thụ toàn bộ phần dữ liệu được pipeline đưa qua. Ngược lại, findFirst, anyMatch hoặc limit có thể **short-circuit**, tức là dừng sớm khi đủ dữ liệu cho kết quả.

Stream cũng có thể sử dụng bộ đệm hoặc đọc trước ở những tầng I/O thấp hơn; do đó **số lời gọi đọc dòng không phải số byte vật lý được đọc từ đĩa**. Laziness là hợp đồng về cách **các phần tử được tiêu thụ**, không phải lời hứa chính xác về từng lần truy cập hệ điều hành.

## 4. Dễ nhầm: việc tạo pipeline không tự kéo tệp vào bộ nhớ

Một ví dụ:

~~~java
Stream<String> names = reader.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase);
~~~

Nếu chỉ dừng ở đây, Stream chưa được tiêu thụ. Cũng chưa có **List** chứa mọi dòng, vì không có bước collect.

Sau đó:

~~~java
List<String> firstTwo = names.limit(2)
        .collect(Collectors.toList());
~~~

Mới xảy ra các thao tác đọc cần thiết để tìm hai dòng không rỗng đầu tiên, biến đổi thành uppercase và lưu hai giá trị vào List.

**Không được hiểu lầm rằng limit(2) luôn chỉ đọc đúng hai dòng thô.** Nếu có các dòng bị filter loại, pipeline cần đọc thêm để tìm đủ hai dòng hợp lệ. Ngoài ra BufferedReader có buffer nội bộ; nó có thể đọc sẵn nhiều ký tự từ nguồn bên dưới.

Trong ví dụ chạy được ở phần 14, dữ liệu là **alpha**, dòng trống, **beta**, **gamma**; kết quả limit(2) là **[ALPHA, BETA]**, vì dòng trống bị loại.

## 5. Short-circuit: findFirst, anyMatch, limit

Những terminal operation hoặc intermediate operation có thể giúp dừng sớm:

- **findFirst()**: lấy dòng đầu tiên theo encounter order nếu có.
- **findAny()**: lấy một phần tử bất kỳ, không dành cho yêu cầu "dòng đầu".
- **anyMatch(predicate)**: có thể dừng khi gặp một dòng khớp.
- **allMatch(predicate)**: có thể dừng khi có dòng không khớp.
- **noneMatch(predicate)**: có thể dừng khi có dòng khớp.
- **limit(n)**: giới hạn số phần tử được đưa ra sau những bước trước nó.

Ví dụ muốn biết tệp có dòng comment hay không:

~~~java
boolean hasComment = reader.lines()
        .anyMatch(line -> line.startsWith("#"));
~~~

Khi có một dòng khớp, pipeline không cần tiếp tục duyệt toàn bộ nội dung để trả true. Tuy nhiên **không khẳng định chính xác số byte nguồn đã đọc** vì tầng BufferedReader có thể đọc trước.

Nếu cần dòng đầu tiên hợp lệ:

~~~java
Optional<String> firstNonEmpty = reader.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .findFirst();
~~~

Optional.empty() ở đây nghĩa là không có dòng phù hợp trong phần dữ liệu stream được tiêu thụ, không phải một IOException.

**Giới hạn quan trọng:** sau khi gọi một terminal operation, Stream đó đã được tiêu thụ, không được dùng lại để gọi một terminal khác.

## 6. Lazy không có nghĩa tính toán nào cũng dùng ít bộ nhớ

Nguồn BufferedReader.lines() có thể được duyệt theo từng dòng, nhưng **pipeline phía sau** có thể làm bộ nhớ tăng lớn:

~~~java
List<String> all = reader.lines()
        .collect(Collectors.toList());
~~~

Đoạn này sẽ giữ toàn bộ các dòng đã thu thập vào List; không nên quảng cáo nó là giải pháp O(1) bộ nhớ chỉ vì source là lazy.

Những thao tác **stateful** như sorted hoặc một số cấu hình distinct cũng có thể cần lưu nhiều phần tử trung gian. Ví dụ:

~~~java
Optional<String> smallest = reader.lines()
        .sorted()
        .findFirst();
~~~

Muốn biết phần tử nhỏ nhất theo sort, pipeline này cần xem dữ liệu thích hợp của toàn nguồn. Nếu chỉ cần giá trị nhỏ nhất, dùng **min(comparator)** có thể tránh việc sắp xếp toàn bộ khi cấu trúc phù hợp, nhưng vẫn phải duyệt nguồn để xác định kết quả.

**Đánh giá bộ nhớ của toàn pipeline**, không chỉ của source:

| Cách xử lý | Rủi ro bộ nhớ |
| --- | --- |
| filter → count | Không giữ toàn bộ dòng, thường nhẹ |
| filter → findFirst | Có thể dừng sớm |
| limit(10) → collect(toList) | List chỉ chứa tối đa 10 kết quả |
| collect(toList) không limit | Giữ mọi phần tử được chọn |
| sorted → collect(toList) | Có thể giữ/sắp nhiều phần tử |
| groupingBy key | Giữ trạng thái theo số nhóm và collector |
| forEach ghi sang sink | Không bắt buộc giữ tất cả dòng, nhưng sink/side effect có chi phí riêng |

**Không giả định mọi phép group hoặc reduce đều có bộ nhớ cố định.** Nếu số key duy nhất có thể tăng theo số dòng, map kết quả cũng có thể lớn tương đương dữ liệu.

## 7. BufferedReader là tài nguyên; Stream phụ thuộc vào Reader còn mở

**BufferedReader** bao bọc một Reader và có thể gián tiếp giữ file descriptor, socket hoặc tài nguyên I/O. Dòng được đọc **sau khi terminal operation bắt đầu**, vì vậy reader phải tiếp tục mở **trong toàn bộ thời gian tiêu thụ pipeline**.

Mẫu đúng:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    List<String> results = reader.lines()
            .filter(s -> !s.isEmpty())
            .limit(100)
            .collect(Collectors.toList());
    // Terminal operation kết thúc khi reader vẫn đang mở.
}
// Tới đây reader được đóng bởi try-with-resources.
~~~

**Không tạo Stream trong try rồi trả ra ngoài để tiêu thụ khi reader đã đóng:**

~~~java
Stream<String> unsafe(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines(); // Sai: reader đóng trước khi caller đọc.
    }
}
~~~

Đoạn trên là phương thức minh họa không nên dùng. Khi caller gọi count/findFirst, việc I/O xảy ra sau khi reader đóng có thể ném UncheckedIOException.

**Ownership:** code tạo và giữ BufferedReader thường chịu trách nhiệm đóng nó. Dùng try-with-resources cho **BufferedReader**, thay vì tin rằng terminal operation tự đóng tài nguyên.

## 8. stream.close() và reader.close() không phải cùng một việc

**Stream** có phương thức close(), nhưng **BufferedReader.lines() không có hợp đồng rằng đóng Stream sẽ tự đóng BufferedReader**. Trong chương trình kiểm thử ở phần 14, đóng Stream bằng try-with-resources không tự gọi close() của reader bên dưới.

Mẫu cần ưu tiên:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
            .filter(line -> !line.startsWith("#"))
            .forEach(System.out::println);
}
~~~

Nếu muốn đóng Stream riêng, vẫn phải quản lý reader:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Stream<String> lines = reader.lines()) {
    lines.forEach(System.out::println);
}
~~~

Thứ tự resource trong try-with-resources khiến **lines.close()** chạy trước, sau đó **reader.close()**. Nhưng việc giữ cả hai resource ở đây thường không cần thiết với một pipeline đơn giản từ BufferedReader.lines; điều bắt buộc là reader được đóng.

**Không nhầm với Files.lines(path)**: API này **trả Stream giữ file đang mở và quy định việc đóng Stream sẽ đóng file**. Phần sau so sánh rõ hai cách sử dụng.

## 9. Một Stream chỉ được tiêu thụ một lần

Mã sau không hợp lệ về vòng đời Stream:

~~~java
Stream<String> lines = reader.lines();
long count = lines.count();

// Không được tiêu thụ lại cùng Stream:
// Optional<String> first = lines.findFirst();
~~~

Một terminal operation kết thúc làm stream không thể được dùng lại. Việc cố dùng lại thường ném **IllegalStateException**, như ví dụ Java 8 đã kiểm thử.

**Không coi việc gọi lại reader.lines() trên cùng BufferedReader là cách "rewind tệp".** Oracle nói rõ rằng sau terminal operation của stream lấy từ BufferedReader.lines, **không có bảo đảm reader đang ở vị trí cụ thể** để đọc ký tự/dòng tiếp theo.

Nếu cần duyệt lại từ đầu một tệp, hãy **mở một BufferedReader mới**, hoặc dùng nguồn có thể tạo stream mới độc lập và hợp đồng phù hợp:

~~~java
try (BufferedReader first =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long total = first.lines().count();
}

try (BufferedReader second =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    Optional<String> head = second.lines().findFirst();
}
~~~

Đây là hai lần đọc độc lập cùng path, không phải reuse một Stream hay guarantee về vị trí của reader cũ.

## 10. Không thao tác trực tiếp trên Reader trong khi terminal operation chạy

Đây là ràng buộc **được ghi rõ trong tài liệu BufferedReader.lines()**:

Trong lúc một terminal operation đang chạy trên Stream, **không được thao tác trực tiếp trên chính BufferedReader**. Nếu làm như vậy, kết quả terminal operation là **không được định nghĩa** theo hợp đồng API.

Ví dụ nên tránh:

~~~java
try (BufferedReader reader =
             new BufferedReader(new StringReader("a\nb\nc\n"))) {
    reader.lines().forEach(line -> {
        // Sai ngữ nghĩa: can thiệp trực tiếp vào cùng reader.
        // reader.readLine();  // IOException và trạng thái stream không rõ.
    });
}
~~~

Đây là đoạn minh họa có import java.io.*; comment cố ý không thực hiện lời gọi sai.

Ràng buộc cũng áp dụng khi một thread khác muốn đọc từ cùng reader trong lúc Stream đang được tiêu thụ. **Đừng chia sẻ cùng BufferedReader để nhiều pipeline hoặc thread cùng thao tác tùy ý**.

Một Stream không tự biến BufferedReader thành một nguồn bất đồng bộ hay một hàng đợi nhiều consumer. Nếu cần fan-out, hãy đọc từng dòng ở một thành phần quản lý I/O rồi chuyển dữ liệu sang một queue hoặc một abstraction có cơ chế đồng bộ riêng.

## 11. IOException trong lúc stream đọc sẽ thành UncheckedIOException

Một điểm dễ gây bất ngờ: **BufferedReader.readLine()** là I/O API checked exception, nhưng các lambda/Stream terminal operation không có chữ ký throws IOException từ nguồn đó.

Vì vậy, theo Oracle, khi một **IOException xảy ra trong lúc BufferedReader.lines() tiếp tục đọc**, nó được **bọc trong java.io.UncheckedIOException**, ném từ thao tác Stream gây ra việc đọc.

Ví dụ xử lý:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long count = reader.lines().count();
    System.out.println(count);
} catch (UncheckedIOException ex) {
    System.err.println("Lỗi khi đọc dòng: " + ex.getCause());
} catch (IOException ex) {
    System.err.println("Lỗi khi mở hoặc đóng reader: " + ex);
}
~~~

Đây là đoạn minh họa trong method có path và import phù hợp.

**Phân biệt thời điểm và loại ngoại lệ:**

- **Files.newBufferedReader(...)** có thể ném **IOException** khi mở tệp.
- **Reader.close()** có thể ném **IOException** khi đóng.
- **BufferedReader.lines()** tạo Stream trước khi đọc thực sự; một lỗi đọc sau đó có thể xuất hiện từ **count, collect, findFirst, forEach** dưới dạng **UncheckedIOException**.
- **Exception do lambda của ứng dụng** như NumberFormatException hay IllegalArgumentException là lỗi logic/parse nghiệp vụ, **không tự biến thành UncheckedIOException** chỉ vì nằm trong pipeline.

**Tránh catch(Exception) rồi trả dữ liệu giả như đã thành công.** Nếu pipeline đang parse dữ liệu quan trọng, lỗi I/O giữa chừng phải được ghi nhận theo contract và không mặc định dùng kết quả một phần.

## 12. Tạo Stream từ Reader đã đóng cũng có thể chưa lỗi ngay

Theo javadoc, **BufferedReader.lines() có thể vẫn trả Stream kể cả khi BufferedReader đã bị đóng**. Khi một terminal operation yêu cầu đọc, nó mới gặp lỗi I/O đã được bọc trong UncheckedIOException.

Ví dụ:

~~~java
BufferedReader reader =
        new BufferedReader(new StringReader("data\n"));
Stream<String> late = reader.lines();
reader.close();

try {
    late.findFirst(); // Lúc này mới cần đọc.
} catch (UncheckedIOException ex) {
    System.out.println("Reader đã đóng trước lúc tiêu thụ");
}
~~~

Đây là đoạn minh họa trong method khai báo throws IOException hoặc xử lý checked exception close. Chương trình phần 14 kiểm thử trường hợp này.

**Đừng tin rằng lệnh reader.lines() thành công chứng tỏ reader đang mở và tệp có thể đọc được.** Lazy source trì hoãn cả **công việc I/O** lẫn **một số lỗi I/O** tới thời điểm terminal operation.

Vì vậy, nếu một method trả Stream từ một nguồn còn mở, nó phải **làm rõ ownership/lifetime**. Thiết kế đơn giản nhất là thực hiện terminal operation trong scope try-with-resources của reader.

## 13. So sánh BufferedReader.lines, Files.lines và Files.readAllLines

| API | Tạo gì? | Tính lazy | Ai chịu trách nhiệm đóng? | Bộ nhớ điển hình |
| --- | --- | --- | --- | --- |
| **BufferedReader.lines()** | Stream<String> trên một reader có sẵn | Có | **Đóng BufferedReader** tại scope sở hữu nó | Phụ thuộc pipeline |
| **Files.lines(path, charset)** | Stream<String> gắn với file mở | Có | **Đóng chính Stream**, thường try-with-resources | Phụ thuộc pipeline |
| **Files.readAllLines(path, charset)** | List<String> | Đọc tất cả trước khi trả List | File được API quản lý trong lời gọi | Giữ tất cả dòng trong List |
| **BufferedReader.readLine()** | Một String mỗi lần gọi | Người gọi chủ động kéo từng dòng | **Đóng BufferedReader** | Có thể nhẹ nếu xử lý từng dòng |

**Cả ba API đọc theo dòng và các overload với charset tường minh vẫn được hỗ trợ.** Files.lines và BufferedReader.lines đã có từ Java 8.

Cách dùng **Files.lines**:

~~~java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isEmpty()).count();
    System.out.println(count);
}
~~~

Với **Files.lines**, stream giữ một file mở nên **Stream.close() đóng file**. Đây là một khác biệt thiết yếu với Stream mà người gọi tạo từ BufferedReader.lines().

**Lưu ý:** một số JDK hiện đại tối ưu việc chia nguồn song song cho Files.lines với charset thuận lợi, nhưng không suy ra mọi pipeline parallel luôn nhanh hơn. BufferedReader.lines gắn với một reader đơn lẻ và không thích hợp để tùy tiện yêu cầu parallel traversal.

## 14. Chương trình Java 17 độc lập: laziness, close, lỗi và tổng hợp

Chương trình sau có đầy đủ class, tên file, import và không cần thư viện ngoài. Nó tạo dữ liệu tạm, xóa tệp trong finally, không phụ thuộc file có sẵn trên máy. **record Item** là cú pháp chính thức từ Java 16; sử dụng JDK 17+ để biên dịch.

Tạo tệp **BufferedReaderLazyDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BufferedReaderLazyDemo {
    static final class CountingReader extends BufferedReader {
        int readLineCalls;
        CountingReader(String content) {
            super(new StringReader(content));
        }
        @Override
        public String readLine() throws IOException {
            readLineCalls++;
            return super.readLine();
        }
    }

    static final class TrackingReader extends BufferedReader {
        boolean closed;
        TrackingReader(String content) {
            super(new StringReader(content));
        }
        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class FailingReader extends BufferedReader {
        FailingReader() {
            super(new StringReader("unused"));
        }
        @Override
        public String readLine() throws IOException {
            throw new IOException("forced-read-error");
        }
    }

    record Item(String name, int amount) { }

    static Item parse(String line) {
        String[] parts = line.split(",", -1);
        if (parts.length != 2 || parts[0].isEmpty()) {
            throw new IllegalArgumentException("bad row: " + line);
        }
        return new Item(parts[0], Integer.parseInt(parts[1]));
    }

    public static void main(String[] args) throws Exception {
        try (CountingReader reader =
                     new CountingReader("alpha\n\nbeta\ngamma\n")) {
            Stream<String> pipeline = reader.lines()
                    .filter(s -> !s.isEmpty())
                    .map(String::toUpperCase);
            System.out.println("readLine calls before terminal: "
                    + reader.readLineCalls);
            List<String> firstTwo = pipeline.limit(2)
                    .collect(Collectors.toList());
            System.out.println("first two: " + firstTwo);
            System.out.println("readLine calls after terminal: "
                    + reader.readLineCalls);
        }

        try (FailingReader reader = new FailingReader()) {
            Stream<String> pipeline = reader.lines();
            System.out.println("I/O error deferred: stream created");
            try {
                pipeline.findFirst();
            } catch (UncheckedIOException ex) {
                System.out.println("wrapped cause: "
                        + ex.getCause().getMessage());
            }
        }

        TrackingReader tracking = new TrackingReader("hello\n");
        try (Stream<String> lines = tracking.lines()) {
            System.out.println("tracked line: "
                    + lines.findFirst().orElse("missing"));
        }
        System.out.println("stream close closed reader: "
                + tracking.closed);
        tracking.close();
        System.out.println("explicit reader close: " + tracking.closed);

        BufferedReader earlyClosed =
                new BufferedReader(new StringReader("data\n"));
        Stream<String> delayed = earlyClosed.lines();
        earlyClosed.close();
        try {
            delayed.findFirst();
        } catch (UncheckedIOException ex) {
            System.out.println("consume after close fails: true");
        }

        Path file = Files.createTempFile("reader-lines-", ".txt");
        try {
            Files.writeString(file,
                    "#demo\nred,2\nblue,5\nred,3\ngreen,4\n\n",
                    StandardCharsets.UTF_8);
            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                Map<String, Integer> totals = reader.lines()
                        .map(String::trim)
                        .filter(s -> !s.isEmpty() && !s.startsWith("#"))
                        .map(BufferedReaderLazyDemo::parse)
                        .collect(Collectors.toMap(
                                Item::name,
                                Item::amount,
                                Integer::sum,
                                TreeMap::new));
                System.out.println("aggregated: " + totals);
            }
            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("Files.lines count: " + lines.count());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BufferedReaderLazyDemo.java
java BufferedReaderLazyDemo
~~~

**Stdout thực tế đã kiểm chứng khi chạy trên JDK kiểm thử:**

~~~text
readLine calls before terminal: 0
first two: [ALPHA, BETA]
readLine calls after terminal: 3
I/O error deferred: stream created
wrapped cause: forced-read-error
tracked line: hello
stream close closed reader: false
explicit reader close: true
consume after close fails: true
aggregated: {blue=5, green=4, red=5}
Files.lines count: 6
~~~

**Đọc kết quả đúng cách:**

- **before terminal: 0** minh họa reader.lines + intermediate operations chưa kích hoạt đọc.
- **first two** chỉ chọn hai dòng không rỗng đầu tiên.
- **readLine calls after terminal: 3** là số đã thấy trong lần chạy demo. Không lấy số 3 làm cam kết API về mọi implementation, mọi cách tối ưu, hay số lần đọc byte vật lý. Điều chắc chắn là **terminal operation kích hoạt việc đọc dữ liệu**.
- **wrapped cause** đến từ FailingReader ném IOException; lỗi xuất hiện khi findFirst tiêu thụ, dưới dạng UncheckedIOException.
- **stream close closed reader: false** chứng minh trong demo không có cơ chế tự đóng BufferedReader chỉ vì Stream.close.
- **consume after close fails** minh họa đã đóng reader trước khi terminal operation.
- **aggregated** là kết quả đọc dòng, trim, loại comment/dòng trống, parse dữ liệu và cộng theo key; TreeMap bảo đảm thứ tự tên ở output.
- **Files.lines count: 6** bao gồm comment, các dòng dữ liệu và một dòng trống. Dấu newline cuối file không tự tạo thêm một dòng trống nữa.
- Tệp tạm được xóa trong finally, còn BufferedReader và Stream Files.lines được đóng bằng try-with-resources.

**Giới hạn ví dụ:** dữ liệu "red,2" là định dạng hai cột đơn giản. **String.split(",") không phải CSV parser đầy đủ** cho field được quote, dấu phẩy trong field, multiline field hoặc escaping. Dữ liệu CSV thật cần parser hoặc contract chặt chẽ riêng.

## 15. Chương trình Java 8 độc lập: pipeline lười và Stream dùng một lần

Tạo tệp **BufferedReaderLinesJava8Demo.java**. Mã này sử dụng hoàn toàn API Java 8 và đã được biên dịch với **javac --release 8**, không dùng record, Files.writeString hay String.isBlank của phiên bản sau.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BufferedReaderLinesJava8Demo {
    static final class CounterReader extends BufferedReader {
        int calls;
        CounterReader(String text) {
            super(new StringReader(text));
        }
        @Override
        public String readLine() throws IOException {
            calls++;
            return super.readLine();
        }
    }

    public static void main(String[] args) throws Exception {
        String data = " Java \n\n python \n JAVA \n unused\n";
        try (CounterReader reader = new CounterReader(data)) {
            Stream<String> stream = reader.lines()
                    .map(String::trim)
                    .filter(s -> !s.isEmpty())
                    .map(s -> s.toLowerCase(Locale.ROOT));
            System.out.println("before terminal: " + reader.calls);
            List<String> found = stream.limit(3)
                    .collect(Collectors.toList());
            System.out.println("selected: " + found);
            System.out.println("read calls: " + reader.calls);
            Map<String, Long> counts = found.stream()
                    .collect(Collectors.groupingBy(
                            s -> s,
                            TreeMap::new,
                            Collectors.counting()));
            System.out.println("counts: " + counts);
        }

        try (BufferedReader reader =
                     new BufferedReader(new StringReader("a\nb\n"))) {
            Stream<String> lines = reader.lines();
            System.out.println("line count: " + lines.count());
            boolean reused = false;
            try {
                lines.findFirst();
            } catch (IllegalStateException expected) {
                reused = true;
            }
            System.out.println("second terminal rejected: " + reused);
        }

        try (BufferedReader reader =
                     new BufferedReader(new StringReader("one\ntwo\n"))) {
            System.out.println("first line: " +
                    reader.lines().findFirst().orElse("missing"));
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac BufferedReaderLinesJava8Demo.java
java BufferedReaderLinesJava8Demo
~~~

**Stdout đã kiểm chứng:**

~~~text
before terminal: 0
selected: [java, python, java]
read calls: 4
counts: {java=2, python=1}
line count: 2
second terminal rejected: true
first line: one
~~~

**Giải thích:**

- Chuỗi gốc có một dòng trống và có khoảng trắng. map(trim) rồi filter loại dòng trống, limit(3) chọn ba dòng hợp lệ đầu tiên.
- **read calls: 4** là số lượt gọi readLine quan sát được trong demo Java 8 này; đó là minh họa chi tiết thực thi, không phải bảo đảm của API cho mọi Stream/JDK.
- Map kết quả được sắp theo key bằng TreeMap, không phụ thuộc thứ tự các nhóm trong quá trình đọc.
- Stream **lines** sau count đã bị tiêu thụ, nên gọi findFirst lần nữa bị từ chối.
- Phần cuối dùng một BufferedReader mới cho tác vụ findFirst; không cố rewind một reader đã tiêu thụ.

## 16. Định dạng dòng: newline, khoảng trắng, dòng trống

**BufferedReader.lines()** cắt dòng theo quy tắc đọc của BufferedReader và **không giữ ký tự kết thúc dòng** trong phần tử String.

Một số điểm cần kiểm thử:

| Nội dung nguồn | Dòng mà stream có thể cung cấp |
| --- | --- |
| "a\nb" | "a", "b" |
| "a\nb\n" | "a", "b" |
| "a\n\nb" | "a", "", "b" |
| "\n" | Một dòng rỗng |
| Chuỗi rỗng | Không có dòng |

**Đừng mặc định gọi trim() cho mọi nguồn.** Nếu khoảng trắng đầu/cuối là dữ liệu có nghĩa (file cấu hình, fixed-width record), việc trim có thể thay đổi payload. Nếu quyết định chuẩn hóa, hãy ghi rõ contract.

**Dòng trống** cũng có thể mang ý nghĩa phân đoạn; filter(!isEmpty) chỉ nên dùng khi tài liệu nguồn cho phép loại bỏ. Đối với logs, bỏ dòng trống có thể làm mất thông tin format.

**Không dùng số dòng đã đọc từ pipeline có filter như số dòng thực trong file.** Nếu cần line number gốc, nên thiết kế counter gắn với thao tác đọc dòng hoặc một vòng lặp rõ ràng; thứ tự filter/map quyết định dữ liệu nào còn đi qua pipeline.

## 17. Charset và tiếng Việt: chỉ định UTF-8 rõ ràng

Một file là **dãy byte**, BufferedReader đọc **ký tự** qua một decoder. Nếu chọn sai charset, nội dung tiếng Việt và ký tự quốc tế có thể bị đọc sai hoặc xuất hiện lỗi decode.

Cách mở được khuyến nghị:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEach(System.out::println);
}
~~~

**Files.newBufferedReader(path, StandardCharsets.UTF_8)** biểu diễn rõ encoding của file. Không phụ thuộc vào platform default charset nếu format trao đổi của ứng dụng đã quy định UTF-8.

**Files.lines(path, StandardCharsets.UTF_8)** cũng cho phép charset tường minh; overload Files.lines(path) dùng UTF-8 theo tài liệu hiện hành.

**Lưu ý Unicode:** so sánh ignore case, trim, normalize có thể có các quy tắc locale/Unicode khác nhau. String.trim của Java 8 loại một số khoảng trắng cơ bản, không phải một bộ chuẩn hóa Unicode toàn diện. Nếu contract yêu cầu xét khoảng trắng Unicode rộng hơn, chọn logic phù hợp phiên bản và kiểm thử đầy đủ.

**BOM:** không mặc định trông đợi mọi nguồn Reader tự loại mọi dấu BOM theo format. Nếu hệ thống nhận file có BOM, cần đặc tả cách xử lý rõ và kiểm thử đầu dòng đầu tiên.

## 18. Xử lý parse và lỗi dữ liệu: đừng nhầm với lỗi I/O

Giả sử mỗi dòng phải có định dạng **key,integer**. Pipeline có thể:

~~~java
Map<String, Integer> totals = reader.lines()
        .map(String::trim)
        .filter(s -> !s.isEmpty() && !s.startsWith("#"))
        .map(MyParser::parseLine)
        .collect(Collectors.toMap(
                Item::key,
                Item::count,
                Integer::sum));
~~~

**Đây là code minh họa**, không chạy độc lập: cần class MyParser, Item với các method tương ứng và quy tắc xử lý dữ liệu lỗi. Chương trình phần 14 cung cấp ví dụ runnable đơn giản có parse.

**Phân biệt lỗi:**

- **IOException/UncheckedIOException:** lỗi đọc nguồn, mất file, lỗi decoder hoặc I/O khác.
- **IllegalArgumentException/NumberFormatException:** dữ liệu một dòng không đúng contract của parser.
- **NullPointerException:** lỗi logic xử lý dữ liệu, ví dụ callback không hỗ trợ null mà lại gặp null từ một thành phần khác.
- **Exception khi xuất kết quả:** có thể đến từ sink, database, network, không phải nhất thiết lỗi ở BufferedReader.

**Mặc định nên thất bại rõ** nếu gặp dòng malformed trong một pipeline cần tính toàn vẹn. Nếu yêu cầu bỏ dòng lỗi, cần mã hóa chính sách đó: ghi nhận số lỗi, vị trí lỗi và kiểm thử không nuốt thông tin ngoài ý muốn.

**Đừng dùng catch(Exception) cho cả pipeline rồi trả Map kết quả một phần như kết quả hoàn chỉnh**, trừ khi API có định nghĩa trạng thái partial result và cách xử lý riêng.

## 19. Reader.lines() không biến I/O blocking thành bất đồng bộ

Các phần tử được lấy **lười**, nhưng việc gọi BufferedReader.readLine trên file/socket vẫn là I/O đồng bộ theo contract của Reader.

- Nếu dữ liệu chưa có hoặc thiết bị chậm, terminal operation có thể **chặn thread đang gọi nó**.
- Dùng Stream không tự tạo worker thread hay event-loop nonblocking.
- Đưa pipeline vào **CompletableFuture.supplyAsync** chỉ dời công việc blocking sang executor, không đổi bản chất lệnh đọc thành nonblocking.
- Nếu nhiều yêu cầu đồng thời, cần cân nhắc executor, giới hạn công việc, timeout, cancellation và đóng tài nguyên.

**Không tùy tiện gọi parallel() cho BufferedReader.lines().** Nguồn dựa trên một reader và không được thao tác đồng thời tùy tiện. Parallel stream có thể gây overhead splitting, thứ tự xử lý ngoài mong muốn hoặc khó giữ hành vi I/O/side effect đúng; không có bảo đảm nhanh hơn.

**Files.lines** với một số charset có thể có spliterator chia nguồn tốt hơn ở JDK hiện đại, nhưng điều đó không phải khuyến nghị mặc định dùng parallel cho mọi file. Performance phải được đo và phải giữ đúng hợp đồng xử lý.

## 20. Thứ tự, forEach và side effect

Một tệp có thứ tự dòng. Khi xử lý tuần tự, pipeline reader.lines().map(...).forEach(...) thông thường phản ánh thứ tự duyệt của nguồn, nhưng khi chuyển sang xử lý song song, **forEach không hứa thứ tự gọi side effect**.

Nếu output cần đúng thứ tự gặp dòng trong Stream có encounter order, **forEachOrdered** là API rõ ý hơn:

~~~java
reader.lines().forEachOrdered(System.out::println);
~~~

Dù vậy, **forEachOrdered không thay thế quản lý tài nguyên**. Reader vẫn cần mở trong thời gian terminal operation đang chạy và phải đóng khi hoàn tất.

**Không gắn side effect quan trọng vào peek** để làm logic bắt buộc: Stream được phép tối ưu một số pipeline, và peek chủ yếu là công cụ quan sát/debug. Các phép biến đổi/terminal operation nên biểu diễn nghiệp vụ rõ ràng.

**Nếu cần transaction:** ví dụ mỗi dòng tạo một bản ghi ở database, việc cập nhật database trong forEach có thể để lại một phần dữ liệu nếu dòng thứ N lỗi. Cần có batch/transaction/idempotency và chính sách rollback riêng. Stream không tự mang tính giao dịch.

## 21. Thiết kế API khi cần trả kết quả từ file

Một method dịch vụ có thể **đọc và xử lý đầy đủ trong phạm vi sở hữu reader**, rồi trả một kết quả đã hoàn chỉnh:

~~~java
List<String> firstMatches(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> line.startsWith("INFO"))
                .limit(50)
                .collect(Collectors.toList());
    }
}
~~~

Đây là method minh họa cần import các kiểu liên quan. List chỉ giữ tối đa 50 dòng phù hợp; bản thân file không được nạp toàn bộ vào List.

Nếu một API thật sự cần **trả Stream để caller tiêu thụ**, nó cần một hợp đồng ownership rõ: **caller phải đóng Stream/file đúng lúc**, và bộ đọc phải sống cho tới khi terminal operation kết thúc. Với trường hợp đọc file theo đường dẫn, **Files.lines(path, charset)** thường thuận tiện hơn vì Stream sở hữu file theo hợp đồng close:

~~~java
Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}
~~~

Caller phải dùng:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.forEach(System.out::println);
}
~~~

Hai đoạn này là phương thức/call-site minh họa trong cùng phạm vi có import và exception handling phù hợp.

**Không để caller đoán ai đóng reader.** Tránh method mở BufferedReader trong try rồi trả reader.lines() khi reader đã đóng.

## 22. Các lỗi thường gặp khi dùng nguồn dữ liệu lười

1. **Trả Stream của BufferedReader ra ngoài try-with-resources:** reader đã đóng trước khi caller tiêu thụ.
2. **Tưởng reader.lines() đã đọc tất cả:** I/O chỉ xảy ra khi terminal operation yêu cầu.
3. **Tưởng file lớn chắc chắn dùng ít bộ nhớ:** collect(toList), sorted hoặc groupingBy vẫn có thể giữ nhiều dữ liệu.
4. **Quên đóng BufferedReader:** có thể làm rò tài nguyên file/socket.
5. **Nghĩ Stream.close luôn đóng BufferedReader:** với BufferedReader.lines, phải quản lý Reader riêng; đừng nhầm với Files.lines.
6. **Đọc trực tiếp reader.readLine trong lúc terminal Stream đang chạy:** kết quả không được định nghĩa theo API.
7. **Coi reader nằm ở một vị trí xác định sau terminal:** Oracle không cam kết vị trí.
8. **Dùng lại cùng Stream cho terminal thứ hai:** Stream single-use, thường ném IllegalStateException.
9. **Đóng reader trước terminal:** lỗi đọc có thể chỉ xuất hiện khi Stream bị tiêu thụ.
10. **Chỉ catch IOException từ Files.newBufferedReader:** I/O lúc duyệt có thể ném UncheckedIOException.
11. **Nuốt NumberFormatException như IOException:** đó là các loại lỗi khác nhau, cần chính sách riêng.
12. **Bỏ filter line trống mà không xét dữ liệu nguồn:** dòng trống có thể có nghĩa.
13. **Dùng trim vô điều kiện:** có thể xóa khoảng trắng hợp lệ.
14. **Không chỉ định charset cho file trao đổi:** dễ sai tiếng Việt hoặc dữ liệu quốc tế.
15. **Coi limit(n) luôn đọc đúng n dòng vật lý:** filter và buffering có thể cần nhiều hơn.
16. **Dùng parallel() tùy tiện:** không bảo đảm nhanh hơn hoặc an toàn side effect.
17. **Ghi side effect từng dòng nhưng không có transaction:** lỗi ở giữa có thể để lại kết quả một phần.
18. **Coi phần cuối có newline là một dòng trống mới:** dấu kết thúc dòng cuối cùng không tự thêm phần tử rỗng dư.
19. **Dùng split(",") như CSV parser tổng quát:** không hỗ trợ đủ quoting/escaping/multiline.
20. **Chỉ kiểm tra kết quả trên file nhỏ đúng dữ liệu:** thiếu test lỗi I/O, file trống, dòng malformed và lifecycle.

## 23. Checklist kiểm thử và vận hành

| Nhóm test | Điều cần chứng minh |
| --- | --- |
| Laziness | Không đọc dữ liệu trong lúc chỉ dựng pipeline; terminal kích hoạt đọc |
| Short-circuit | limit/findFirst dừng khi đủ kết quả theo semantics; không dựa vào byte count |
| Dòng trống | Dòng trống có thể là phần tử ""; filter chỉ khi hợp đồng cho phép |
| File rỗng | Stream có 0 dòng |
| Dòng cuối không newline | Vẫn đọc được dòng cuối |
| Unicode | UTF-8, tiếng Việt, ký tự đặc biệt đúng |
| Đóng reader | Reader đóng sau terminal, không đóng trước |
| Đóng Stream | Không nhầm ownership BufferedReader.lines với Files.lines |
| Đọc sau close | Lỗi được phát hiện lúc terminal operation yêu cầu đọc |
| I/O thất bại | UncheckedIOException có IOException gốc từ việc đọc |
| Parser thất bại | NumberFormatException/IllegalArgumentException khác lỗi I/O |
| Single-use | Không dùng lại Stream sau terminal |
| Reader interference | Không đọc thêm trực tiếp từ cùng reader khi đang tiêu thụ |
| Bộ nhớ | Pipeline không có collect/sorted vô hạn nếu workload lớn |
| Concurrency | Không dùng parallel hoặc chia sẻ Reader tùy ý |
| Cleanup | Try-with-resources và finally giải phóng file tạm/executor nếu có |

**Viết test deterministic:** dùng StringReader hoặc file tạm có nội dung cố định. Với lỗi I/O, dùng BufferedReader subclass cố ý ném IOException tại readLine. Không dựa vào Thread.sleep để đoán lúc dữ liệu được đọc.

**Đừng chỉ đo thời gian:** một pipeline chậm có thể là do I/O, parse, charset, output sink, GC, buffering hoặc số lượng object được giữ. Đo đúng bottleneck và memory profile mới quyết định tối ưu.

## 24. Bài tập kèm đáp án

**Bài 1.** Sau reader.lines().map(String::trim).filter(...), file đã được đọc chưa?

**Đáp án:** Chưa có terminal operation; stream đang mô tả pipeline lười, I/O chưa phải hoàn thành. Việc đọc xảy ra khi terminal operation tiêu thụ.

**Bài 2.** Một file có "a", dòng rỗng, "b". filter(!isEmpty).limit(2) có thể lấy bao nhiêu dòng thô?

**Đáp án:** Có thể phải lấy ba dòng logic để tìm hai dòng không rỗng. Không kết luận chỉ đọc đúng hai dòng vật lý.

**Bài 3.** Dùng return reader.lines() bên trong try-with-resources có an toàn?

**Đáp án:** Không. Reader đóng khi rời try, còn Stream chưa được tiêu thụ. Caller có thể gặp UncheckedIOException.

**Bài 4.** Đóng Stream của BufferedReader.lines có bảo đảm đóng reader?

**Đáp án:** Không có hợp đồng đó; code sở hữu reader phải đóng BufferedReader. Files.lines khác: đóng Stream sẽ đóng file.

**Bài 5.** Gọi count() rồi findFirst() trên cùng Stream?

**Đáp án:** Không. Stream đã bị tiêu thụ. Muốn đọc lại file từ đầu, mở reader/stream mới theo hợp đồng phù hợp.

**Bài 6.** Nếu một readLine bị lỗi I/O trong lúc collect, loại exception nào có thể phát sinh?

**Đáp án:** UncheckedIOException bọc IOException. Đừng nhầm với IOException mở/đóng reader hoặc lỗi parse trong lambda.

**Bài 7.** Reader đã đóng, nhưng reader.lines() không ném lỗi ngay có phải dữ liệu đọc được không?

**Đáp án:** Không. Lazy Stream có thể chỉ ném UncheckedIOException khi terminal operation yêu cầu đọc.

**Bài 8.** Files.readAllLines và Files.lines khác gì quan trọng?

**Đáp án:** readAllLines trả List đã chứa toàn bộ dòng. Files.lines cung cấp Stream nạp lười và phải đóng Stream để đóng file.

**Bài 9.** Dùng lines().collect(toList()) cho file khổng lồ có chắc memory nhỏ?

**Đáp án:** Không, List sẽ giữ mọi dòng thu thập; sự lười của source không khử memory của terminal collector.

**Bài 10.** Có được gọi reader.readLine trong callback forEach của reader.lines() không?

**Đáp án:** Không. Oracle nói thao tác trên reader trong lúc terminal operation đang thực thi khiến kết quả không được định nghĩa.

**Bài 11.** Có thể mặc định gọi parallel() để đọc tệp nhanh gấp đôi?

**Đáp án:** Không. BufferedReader.lines gắn với một reader, việc chia nguồn và side effect có chi phí/semantics riêng; cần đo hiệu năng và giữ đúng contract.

**Bài 12.** Dòng trống và file rỗng có giống nhau?

**Đáp án:** Không. Một file rỗng có 0 dòng; file chứa một newline có thể sinh một dòng String rỗng.

**Bài 13.** Dòng "red,2" đọc bởi Stream đã là một Item chưa?

**Đáp án:** Chưa. BufferedReader.lines trả String; parser riêng phải diễn giải schema, validate và chuyển thành Item. Nếu schema thật là CSV có quote/escape, split đơn giản không đủ.

**Bài 14.** Vì sao code cần StandardCharsets.UTF_8?

**Đáp án:** Để xác định cách decoder đổi byte thành ký tự, giữ đúng tiếng Việt và format tệp; không dựa vào charset mặc định của môi trường.

## 25. Tổng kết và tài liệu chính thức Java hiện hành

**Những nguyên tắc quan trọng nhất:**

1. **BufferedReader.lines() trả Stream<String> lazy**, từng dòng được đọc khi terminal operation cần.
2. **map/filter chỉ dựng pipeline**; count/collect/forEach/findFirst kích hoạt tiêu thụ.
3. **limit/findFirst có thể dừng sớm**, nhưng lọc và buffering làm số dòng/byte thực tế khác nhau.
4. **Lazy source không bảo đảm memory nhỏ cho toàn pipeline**: collect(toList), sorted, grouping có thể giữ dữ liệu lớn.
5. **Giữ BufferedReader mở khi Stream đang tiêu thụ** và đóng nó bằng try-with-resources.
6. **Không nhầm stream.close với reader.close** của BufferedReader.lines; với **Files.lines**, đóng Stream đóng file.
7. **Không thao tác trực tiếp trên cùng reader trong terminal operation** và không giả định reader còn ở vị trí cụ thể sau khi terminal kết thúc.
8. **Stream single-use**; không có chuyện terminal thứ hai trên cùng Stream.
9. **I/O lỗi khi duyệt** có thể xuất hiện dưới dạng **UncheckedIOException**, khác checked IOException khi mở/đóng và khác lỗi parse.
10. **Chỉ định charset**, xử lý dòng trống/whitespace theo contract, không dùng split đơn giản thay CSV parser phức tạp.
11. **Đây là I/O đồng bộ**; không tự hóa thành nonblocking hoặc song song chỉ bằng Stream.
12. **Kiểm thử lỗi tài nguyên và short-circuit** quan trọng không kém kiểm tra nội dung đúng.

**Nguồn Oracle Java SE 25 đang được hỗ trợ:**

- **BufferedReader.lines()** — laziness, reader interference, trạng thái sau terminal và UncheckedIOException: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html
- **Files.lines/Files.newBufferedReader/Files.readAllLines** — ownership, lazy đọc file và charset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
- **Stream** — terminal/intermediate operations, single-use, onClose, encounter order: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **UncheckedIOException** — wrapper cho checked IOException trong Stream: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html
- **StandardCharsets** — UTF-8: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html
- **Collectors** — toList, toMap, groupingBy: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html

**Phiên bản:** BufferedReader.lines, Stream, Files.lines và Collectors đã có từ Java 8 và tiếp tục được hỗ trợ. Chương trình thứ nhất cần Java 17+ vì record và Files.writeString (Java 11+); chương trình thứ hai đã biên dịch thành công với target Java 8. Không sử dụng API legacy làm giải pháp chính.

**Kết luận thực hành:** nguồn dữ liệu lười giúp bắt đầu xử lý mà không nạp trước toàn bộ file, nhưng buộc ta **quản lý thời điểm đọc và vòng đời Reader**. Chỉ tiêu thụ Stream trong khi Reader còn mở, chấp nhận rằng lỗi I/O có thể xuất hiện muộn, và thiết kế pipeline theo nhu cầu bộ nhớ/thứ tự/độ tin cậy thực sự.
