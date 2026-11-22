# Reader.transferTo: Đặc tính chặn và xử lý nguồn chưa kết thúc (Java 10+)

## 1. Mục tiêu và vấn đề thực tế

Từ **Java 10**, lớp `java.io.Reader` có phương thức `long transferTo(Writer out) throws IOException`. Nó đọc **toàn bộ các ký tự còn lại** từ Reader hiện tại và ghi lần lượt vào Writer đích. Đây là cách gọn để chuyển nội dung văn bản khi **nguồn có thể đi đến cuối luồng (EOF)**.

Tuy nhiên, chữ “chuyển hết” cũng là rủi ro quan trọng. `Reader.transferTo` **có thể chặn vô thời hạn** trong lúc chờ dữ liệu từ Reader, hoặc khi ghi vào Writer. Nếu nguồn luôn mở và chưa phát tín hiệu EOF — chẳng hạn kết nối mạng, pipe giữa hai thread, đầu vào tương tác, hoặc một nguồn đang stream liên tục — lệnh có thể **không bao giờ trả về**, ngay cả khi đã nhận và ghi một phần nội dung.

Bài này hướng dẫn:

1. Hiểu chính xác điều kiện để `transferTo` kết thúc bình thường.
2. Phân biệt **chưa có dữ liệu tạm thời** với **EOF thật sự**.
3. Nhận diện khả năng chặn ở **đầu đọc** lẫn **đầu ghi**.
4. Chọn chiến lược thích hợp khi nguồn chưa kết thúc: kết thúc nguồn đúng giao thức, đọc có giới hạn, xử lý tăng dần, timeout/cancellation tại tầng I/O hoặc xử lý từng thông điệp.
5. Quản lý sở hữu Reader/Writer, `IOException`, trạng thái chuyển một phần, timeout và tài nguyên.
6. Phân biệt số **ký tự Java/UTF-16 code unit** do phương thức trả về với số byte hoặc số Unicode code point.
7. Kiểm thử các tình huống chặn, EOF, exception và nguồn vô hạn mà không tạo một bài test bị treo.

Các quy tắc cốt lõi dưới đây là **hợp đồng API còn hiệu lực trong Java hiện đại**, không dựa vào kỹ thuật lỗi thời hay API legacy. Ví dụ hoàn chỉnh cuối bài được biên dịch và chạy với `javac --release 10`.

## 2. Hợp đồng của `Reader.transferTo`

Chữ ký:

```java
public long transferTo(java.io.Writer out) throws java.io.IOException
```

Ý nghĩa theo Javadoc:

- Đọc tất cả **ký tự còn lại** từ Reader nguồn, theo thứ tự.
- Ghi các ký tự đó vào Writer đích theo đúng thứ tự đã đọc.
- Khi phương thức **trả về bình thường**, Reader đã ở cuối luồng.
- Trả một giá trị `long` là **số ký tự đã chuyển**; nếu tổng vượt `Long.MAX_VALUE` thì kết quả được giới hạn ở `Long.MAX_VALUE`.
- **Không tự đóng** Reader hoặc Writer.
- Có thể **chặn vô thời hạn** khi đọc hoặc khi ghi.
- Ném `IOException` nếu thao tác đọc/ghi có lỗi; `out == null` gây `NullPointerException`.
- Nếu bị ngắt giữa chừng bởi `IOException`, Reader/Writer có thể đã xử lý **một phần dữ liệu** và nằm trong trạng thái không nhất quán. Javadoc khuyến nghị nhanh chóng đóng cả hai luồng khi gặp I/O error.
- Nếu Reader/Writer bị đóng không đồng bộ hoặc thread bị interrupt khi đang chuyển, hành vi phụ thuộc implementation cụ thể và **không được API bảo đảm chung**.

`Reader.transferTo` **không** phải một phép truyền “n phần tử đang sẵn có”. Nó là yêu cầu **đọc đến EOF**. Với Reader còn mở và đang chờ phía khác gửi thêm, không thể kết luận rằng “đã đọc hết dữ liệu hiện có” đồng nghĩa “đã đọc đến cuối luồng”.

### Cách dùng phù hợp: nguồn hữu hạn

```java
try (var source = new java.io.StringReader("Java 10\nTransfer");
     var target = new java.io.StringWriter()) {

    long copied = source.transferTo(target);
    System.out.println(copied);             // 16
    System.out.println(target.toString());   // Hai dòng nội dung.
}
```

Đây là đoạn minh họa hoàn chỉnh để đặt trong thân phương thức có xử lý ngoại lệ phù hợp. `StringReader` từ chuỗi hữu hạn có điểm EOF rõ ràng, nên `transferTo` có thể kết thúc bình thường.

Không áp dụng lập luận này cho một `Reader` lấy dữ liệu từ socket hoặc pipe còn mở nếu chưa xác định rõ điều kiện kết thúc.

## 3. Cơ chế: tại sao Reader có dữ liệu vẫn có thể chặn?

Nhìn vào mô hình đọc cơ bản của `Reader`:

```java
// Minh họa logic khái niệm; không phải nguồn triển khai của JDK.
char[] buffer = new char[4096];
int n;

while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
    writer.write(buffer, 0, n);
}
```

Một lời gọi `read(char[], int, int)` có thể chờ cho đến khi **có dữ liệu**, **gặp EOF**, hoặc **phát sinh lỗi**. Khi `read` trả một số dương, thuật toán có thể ghi phần đó ra Writer rồi tiếp tục gọi `read`. Nếu bên gửi chưa đóng hoặc chưa gửi tín hiệu kết thúc, vòng lặp **tiếp tục chờ** dù đã ghi nhiều phần thành công.

Đây là **mô hình khái niệm** để hiểu API, không phải cam kết kích thước buffer, số lần `read`, số lần `write` hay thuật toán chính xác mà implementation JDK phải dùng. `Reader.transferTo` có thể được override trong subclass, và code sản phẩm không nên dựa vào chi tiết nội bộ.

### Trạng thái “chưa có dữ liệu” không phải EOF

| Trạng thái nguồn | Lần đọc có thể làm gì? | Hệ quả với `transferTo` |
| --- | --- | --- |
| Có ký tự sẵn | Trả một số ký tự | Ghi ra Writer, rồi tiếp tục đọc |
| Tạm hết ký tự nhưng nguồn còn mở | Chờ thêm dữ liệu | Có thể chặn, chưa được trả về |
| Người dùng chưa nhập dòng/thông điệp hoàn chỉnh | Chờ theo cơ chế nguồn | Có thể chặn |
| Socket/pipe đang mở, peer chưa kết thúc | Chờ thêm ký tự hoặc tín hiệu kết thúc | Có thể chặn rất lâu |
| Nguồn đã báo EOF | `read` trả `-1` | Chuyển hoàn tất, trả số ký tự |
| Đọc thất bại | Ném `IOException` | Chuyển thất bại, có thể đã ghi một phần |
| Ghi đích bị nghẽn/chặn | `Writer.write` chờ hoặc lỗi | Chuyển cũng chặn/thất bại dù nguồn có dữ liệu |

**Không có quy tắc:** “`transferTo` trả về khi Writer đã nhận vài ký tự”, “khi người gửi gọi `flush()`” hay “khi `ready()` trả `false`”. Điều kiện bình thường là **EOF** của Reader.

## 4. Những nguồn thường có khả năng chưa kết thúc

### 4.1. `PipedReader` từ thread khác

Một `PipedReader` được nối với `PipedWriter` dùng để truyền ký tự giữa các thread. Nếu phía ghi đã gửi `"hello"` nhưng **vẫn mở**, phía đọc không biết liệu sẽ còn `"world"` hay không.

```java
var pipeIn = new java.io.PipedReader();
var pipeOut = new java.io.PipedWriter(pipeIn);

// Thread ghi có thể gửi một phần rồi chờ:
pipeOut.write("hello");
pipeOut.flush();

// Nếu Reader.transferTo(...) đang chạy ở thread khác,
// thao tác đó có thể vẫn chờ vì pipeOut còn mở.
```

Đoạn này chỉ để minh họa và **không chạy `transferTo` ngay trong cùng thread**: làm vậy có thể chặn mà không còn thread nào để đóng pipe. Mục 12 có demo đầy đủ dùng producer thread, future timeout và `close()` đúng thứ tự.

Với pipe, `PipedWriter.close()` ở phía gửi là một cách hợp lệ để **báo kết thúc luồng ghi** cho phía đọc. `flush()` chỉ chuyển dữ liệu đang có, **không phải thông báo EOF**.

### 4.2. `InputStreamReader` bọc socket còn mở

```java
// Minh họa: socket đã được kết nối theo quy trình riêng.
java.io.Reader reader = new java.io.InputStreamReader(
        socket.getInputStream(), java.nio.charset.StandardCharsets.UTF_8);
```

Một TCP connection có thể gửi vài thông điệp rồi tiếp tục mở để tái sử dụng. Nếu gọi `reader.transferTo(writer)`, reader có thể chờ **đến khi peer kết thúc chiều gửi (EOF)** hoặc thao tác đọc bị lỗi. Việc hoàn tất **một thông điệp ứng dụng** không tự động đồng nghĩa **kết thúc byte stream**.

Nếu protocol là HTTP, WebSocket hay giao thức tự định nghĩa, hãy dùng **định dạng và ranh giới thông điệp của protocol đó**. Không coi “không có byte mới trong một khoảng ngắn” là kết thúc dữ liệu.

### 4.3. Đầu vào tương tác hoặc luồng log/live stream

Nếu nguồn là stdin/console, dữ liệu có thể đến theo từng dòng. Một newline chỉ kết thúc **dòng**, không nhất thiết kết thúc **Reader**. Một nguồn log liên tục có thể không bao giờ có EOF khi ứng dụng đang chạy. Với những nguồn ấy, `transferTo` không phù hợp nếu ứng dụng cần phản hồi sau một số dòng hoặc sau một khoảng thời gian nhất định.

### 4.4. Nguồn file thông thường

File hữu hạn thường là trường hợp dùng `transferTo` dễ nhất: sau khi đọc hết file, Reader nhận EOF và phương thức trả về. Nhưng ngay cả với file, Writer đích vẫn có thể chặn do hệ thống lưu trữ, mạng mount, thiết bị chậm hoặc resource contention. Không nên tuyên bố mọi lần chuyển file đều không chặn.

## 5. Có hai phía có thể chặn: Reader và Writer

Nhiều người chỉ nghĩ `transferTo` đang “đợi đọc”. Theo Javadoc, nó có thể chặn **khi đọc hoặc khi ghi**:

<escape>**Đầu vào:**</escape> nguồn chưa có dữ liệu, peer chưa kết thúc, decoder đang chờ bytes cho một chuỗi ký tự hoàn chỉnh, file/network read chậm hoặc một Reader có cơ chế đồng bộ nội bộ.

<escape>**Đầu ra:**</escape> Writer bọc kênh mạng, file/mount chậm, bộ đệm/queue đầy và consumer chưa xử lý kịp, hoặc một Writer có lock đang bị giữ.

Kể cả khi Reader đã ở gần EOF, một lần `Writer.write(...)` vẫn có thể mất thời gian hoặc chặn. Nếu writer thực sự bị lỗi, `IOException` có thể xảy ra sau khi một số ký tự trước đó đã được ghi.

Do đó, việc chỉ đặt read timeout cho nguồn **không bảo đảm toàn bộ thời gian chuyển luôn có giới hạn**. Cần xem cả chiều ghi, chính sách tải, giới hạn dữ liệu và lifecycle kết nối.

## 6. `Reader.ready()` không phải bộ phát hiện EOF

Một anti-pattern:

```java
// SAI nếu mục tiêu là xác định toàn bộ dữ liệu đã kết thúc:
if (!reader.ready()) {
    // Không được kết luận đã EOF.
}
```

`Reader.ready()` trả `true` khi **lần `read()` tiếp theo được bảo đảm không chặn vì chờ đầu vào**; trả `false` **không có nghĩa** lần đọc tiếp theo chắc chắn sẽ chặn, càng không có nghĩa đã EOF.

Hãy phân biệt:

- **Không sẵn sàng ngay lúc này:** trạng thái tạm thời, còn có thể có dữ liệu.
- **EOF:** được biểu đạt thông qua kết quả `read(...) == -1` hoặc tín hiệu kết thúc đặc thù của nguồn.
- **Đóng Reader:** hành động quản lý tài nguyên, không phải cách phổ quát để chủ động lấy “phần còn lại” có sẵn.

Trên socket, `available()` của byte stream cũng không phải tổng số bytes còn lại hay tín hiệu EOF; không dùng phép đo số byte đang có ngay tức thời để thay thế protocol framing hoặc điều kiện kết thúc luồng ký tự.

## 7. Chọn chiến lược khi nguồn chưa kết thúc

### Phương án A — nếu toàn bộ nguồn **có điểm kết thúc rõ**, hãy dùng `transferTo`

Phù hợp với file, chuỗi hữu hạn, stream tài liệu được mở rồi đóng theo protocol, hoặc một pipe mà producer **chắc chắn** gửi EOF.

```java
try (var in = new java.io.StringReader("A\nB\n");
     var out = new java.io.StringWriter()) {
    long count = in.transferTo(out);
    System.out.println(count); // 4 ký tự
}
```

Nếu một nguồn thực sự sẽ có EOF, việc chuyển toàn bộ có thể rất gọn. Nhưng vẫn cần chính sách lỗi và đảm bảo thời gian thực thi khi I/O từ hệ thống bên ngoài không đáng tin.

### Phương án B — nếu ứng dụng chỉ cần **một thông điệp**, đọc theo framing của protocol

Với giao thức **mỗi thông điệp một dòng**, phương thức như `BufferedReader.readLine()` có thể phù hợp hơn:

```java
// Minh họa khi đã có một BufferedReader tên buffered.
String message = buffered.readLine();
if (message == null) {
    // Reader đã đến EOF.
} else {
    // Đã đọc một dòng, không nhất thiết đã đến EOF của toàn bộ Reader.
}
```

Tuy nhiên, `readLine()` **cũng có thể chặn** cho đến khi gặp line terminator hoặc EOF. Nếu peer không gửi newline, hoặc một dòng quá dài vượt chính sách tài nguyên, vẫn có rủi ro. Cần giới hạn kích thước thông điệp và timeout ở tầng nguồn khi thực tế có thể gặp đầu vào không đáng tin.

Nếu protocol dùng **length prefix**, đọc đúng lượng ký tự/byte được khai báo, rồi dừng theo ranh giới đó. Nếu protocol là nhị phân, xử lý framing trên byte stream trước khi decode text; không tự giả định “n ký tự” = “n byte”.

### Phương án C — nếu chỉ được chuyển tối đa N ký tự, dùng **vòng đọc có giới hạn**

`transferTo` không có tham số `maxChars`. Nếu giới hạn là yêu cầu nghiệp vụ hoặc an toàn tài nguyên, hãy tự áp dụng vòng đọc–ghi có giới hạn:

```java
static long copyAtMost(
        java.io.Reader source, java.io.Writer destination, long maxChars)
        throws java.io.IOException {
    if (maxChars < 0) {
        throw new IllegalArgumentException("maxChars must be non-negative");
    }

    char[] buffer = new char[4096];
    long total = 0;

    while (total < maxChars) {
        int requested = (int) Math.min(buffer.length, maxChars - total);
        int read = source.read(buffer, 0, requested);
        if (read == -1) {
            break; // Nguồn đã EOF trước maxChars.
        }
        if (read == 0) {
            throw new java.io.IOException("No progress from Reader");
        }
        destination.write(buffer, 0, read);
        total += read;
    }
    return total;
}
```

Đây là phương thức độc lập có thể đặt trong class; nó **không tự đóng** hai stream và không tự flush. Chính sách “no progress” chủ động báo lỗi nếu một Reader không tuân thủ kỳ vọng khi yêu cầu đọc dương. Có thể tùy chỉnh cách xử lý theo contract của Reader cụ thể.

**Giới hạn số ký tự không phải timeout.** Nếu cần `100` ký tự nhưng nguồn mới gửi `10` rồi giữ mở, lời gọi `read` tiếp theo có thể chặn. Vòng lặp này chỉ bảo đảm **không chủ động đọc quá N ký tự khi kết thúc**, không bảo đảm hoàn tất trong T mili-giây.

Nếu nhận dữ liệu từ đối tác ngoài, cũng cần cân nhắc giới hạn bytes đầu vào, decoder và ranh giới message để chống các nguồn gửi dữ liệu vô hạn. Với surrogate pair, giới hạn UTF-16 code unit có thể cắt đôi cặp ký tự; nếu mục tiêu là hiển thị Unicode đúng, phải thiết kế quy tắc giới hạn ở cấp phù hợp.

### Phương án D — nếu là luồng liên tục, xử lý tăng dần thay vì chờ EOF

Với live stream, ứng dụng thường cần xử lý một chunk, một event, một dòng, hoặc một message rồi lập tức phản hồi. Dùng vòng xử lý theo giao thức, bảo đảm:

- Có quy tắc kết thúc cho mỗi đơn vị dữ liệu.
- Có khả năng dừng theo lệnh của hệ thống.
- Có giới hạn kích thước/buffer và backpressure.
- Có chính sách timeout ở tầng I/O khi nguồn không hợp tác.
- Có phương án đóng tài nguyên khi consumer không còn cần dữ liệu.

`Reader.transferTo` vẫn có thể phù hợp cho một đoạn hữu hạn đã được tách riêng thành Reader có EOF rõ ràng; **không phù hợp làm hàm “đọc dữ liệu hiện có rồi trả về ngay” của một stream chưa kết thúc**.

## 8. Timeout và cancellation: không nhầm timeout của Future với timeout I/O

Một mẫu dễ thấy:

```java
var future = executor.submit(() -> reader.transferTo(writer));
future.get(5, java.util.concurrent.TimeUnit.SECONDS);
```

Nếu `future.get(...)` hết hạn, thread gọi `get` sẽ nhận `TimeoutException`, nhưng **tác vụ `transferTo` có thể vẫn đang chạy và vẫn chặn I/O ở thread khác**. `get(timeout)` chỉ đặt giới hạn **thời gian chờ của caller**, không tự dừng operation.

Có thể phối hợp `future.cancel(true)`, nhưng:

- `cancel(true)` chỉ **yêu cầu ngắt thread**; không phải mọi Reader/Writer đều phản ứng giống nhau với interrupt.
- Javadoc của `Reader.transferTo` **không bảo đảm** cách ứng xử khi bị interrupt hoặc bị đóng Reader/Writer không đồng bộ.
- Nếu nguồn là network socket, cần cấu hình timeout thích hợp ở **tầng socket/I/O** và có cơ chế đóng kết nối an toàn; chỉ một `Future.get(timeout)` không giải quyết toàn bộ lifetime.
- Writer cũng cần giới hạn hoặc cơ chế hủy thích hợp nếu có nguy cơ bị nghẽn khi ghi.

Ví dụ với TCP socket, `Socket.setSoTimeout(...)` có thể giới hạn **một số thao tác đọc blocking trên socket InputStream** và khi hết hạn dẫn đến `SocketTimeoutException`. Nó không tạo một giới hạn tổng tuyệt đối cho toàn bộ `transferTo` và **không thay thế write timeout**; một số lần đọc liên tiếp vẫn có thể kéo dài tổng thời gian. Đối với TLS/network frameworks, dùng đúng timeout, deadline và cơ chế cancellation mà tầng kết nối hỗ trợ.

**Kết luận:** timeout của caller, timeout đọc, deadline tổng và cancellation của worker là **các ràng buộc khác nhau**. Cần thiết kế và test riêng, không gộp chúng thành lời hứa “`transferTo` sẽ tự kết thúc sau 5 giây”.

## 9. Bên gửi phải kết thúc đúng cách: `flush` không phải `close`

Với một Writer có buffering:

```java
writer.write("hello");
writer.flush();
```

`flush()` yêu cầu đẩy nội dung đang đệm đến lớp bên dưới; nó **không có nghĩa** bên gửi đã hoàn tất vĩnh viễn và không tự báo EOF cho mọi Reader nhận dữ liệu.

Tùy loại nguồn:

- **Pipe:** phía gửi đóng `PipedWriter` khi đã gửi xong; `PipedReader` có thể nhận EOF sau khi tiêu thụ hết dữ liệu.
- **Socket:** protocol hoặc việc đóng/half-close chiều gửi cần được quản lý thích hợp; việc chỉ gửi newline, flush hoặc tạm ngừng gửi **không nhất thiết đóng stream**.
- **File:** Reader gặp EOF sau khi hết nội dung nguồn tại thời điểm đọc theo quy tắc I/O cụ thể.
- **Interactive input:** tín hiệu kết thúc do môi trường/ứng dụng định nghĩa, không nên mặc định một dấu xuống dòng là EOF.

Nếu server cần duy trì kết nối lâu dài để trao đổi nhiều thông điệp, **không được đóng kết nối sau mỗi message chỉ để ép `transferTo` hoàn thành**. Hãy chọn cách đọc theo ranh giới message và giữ vòng đời kết nối theo protocol.

## 10. Sở hữu tài nguyên: `transferTo` không tự `close` hay cam kết `flush`

Javadoc khẳng định `transferTo` **không đóng Reader hoặc Writer**. Với nguồn và đích do cùng phương thức tạo/nhận quyền sở hữu, dùng `try-with-resources`:

```java
static long transferText(
        java.nio.file.Path input, java.nio.file.Path output)
        throws java.io.IOException {

    try (var reader = java.nio.file.Files.newBufferedReader(
                 input, java.nio.charset.StandardCharsets.UTF_8);
         var writer = java.nio.file.Files.newBufferedWriter(
                 output, java.nio.charset.StandardCharsets.UTF_8)) {
        return reader.transferTo(writer);
    }
}
```

Đây là phương thức thuộc một class; cần đảm bảo đường dẫn tồn tại/phù hợp và cách ghi đích đúng mong muốn. `try-with-resources` bảo đảm tự động **đóng** các resource nó sở hữu khi thoát scope, kể cả khi có exception; việc close Writer thường giúp thực hiện các bước hoàn tất ghi cần thiết.

Nếu API nhận Reader/Writer **do caller sở hữu**, không tự đóng chúng mà không có thỏa thuận:

```java
static long copyWithoutOwningStreams(
        java.io.Reader source, java.io.Writer destination)
        throws java.io.IOException {
    return source.transferTo(destination);
}
```

Trong trường hợp writer có bộ đệm, chủ sở hữu có thể cần gọi `flush()` theo hợp đồng sử dụng Writer. `transferTo` **không cam kết flush tự động**; không dùng việc phương thức trả về làm bằng chứng mọi byte đã được ghi bền vững ra ổ đĩa hoặc được peer tiếp nhận.

### Không coi `StringWriter` là nơi chứa mọi luồng vô hạn

`Reader.transferTo` tự nó không nhất thiết cần lưu toàn bộ nguồn trong RAM, nhưng nếu Writer đích là `StringWriter`, bộ đệm của Writer sẽ tăng theo nội dung. Với nguồn rất lớn hoặc không giới hạn, việc tích lũy toàn bộ vào `StringWriter` có thể gây thiếu bộ nhớ. Cần hạn chế kích thước, dùng Writer hướng file/stream phù hợp hoặc xử lý tăng dần.

## 11. Nếu `IOException` xảy ra giữa chừng: đích có thể đã bị thay đổi

Một lỗi rất nguy hiểm là giả định:

```java
source.transferTo(destination);
```

là một phép biến đổi **nguyên tử**: hoặc chuyển hết, hoặc không chuyển gì. Thực tế không phải vậy.

Giả sử Reader trả `"abc"`, Writer đã nhận đoạn này, rồi lần đọc tiếp theo ném `IOException`. Khi phương thức ném lỗi:

- `destination` **có thể đã chứa `"abc"`**.
- `source` có thể đã đi qua một số ký tự, nhưng **chưa đến EOF**.
- Cả hai luồng có thể rơi vào trạng thái không thích hợp để tiếp tục một cách an toàn.
- Không có `long` kết quả được trả về bình thường trong lần gọi thất bại đó.

Javadoc khuyến nghị **đóng kịp thời cả Reader và Writer** sau I/O error. Nếu exception đến từ nguồn ngoài, cần log context và đánh dấu operation thất bại; đừng âm thầm coi phần đã chép là bản hoàn chỉnh.

### Không retry vô điều kiện lên cùng đích

Nếu tự động gọi `transferTo` lần hai với cùng Reader/Writer sau lỗi:

- Có thể thiếu phần đã đọc khỏi source.
- Có thể nhân đôi dữ liệu ở destination.
- Có thể Writer chỉ còn một phần dữ liệu.
- Có thể nguồn không cho đọc lại (network/pipe).
- Có thể có vấn đề về encoding hoặc kết thúc file.

Muốn retry, thiết kế **idempotency** hoặc khởi động lại từ một nguồn có thể replay và một đích mới. Với việc xuất bản file, một chiến lược thường dùng là ghi vào **file tạm**, kiểm tra kết quả đầy đủ rồi mới chuyển/replace file đích theo cơ chế file system được hỗ trợ. Không tuyên bố mọi thao tác move là atomic trên mọi filesystem; nếu cần atomic commit, phải xác minh hỗ trợ và dùng tùy chọn phù hợp.

## 12. Ví dụ Java 10+ hoàn chỉnh: chặn đến EOF, đóng luồng và lỗi một phần

Tạo tệp **`ReaderTransferToBlockingDemo.java`**:

```java
import java.io.IOException;
import java.io.PipedReader;
import java.io.PipedWriter;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class ReaderTransferToBlockingDemo {
    static final class CloseTrackedReader extends StringReader {
        boolean closed;
        CloseTrackedReader(String text) { super(text); }
        @Override public void close() { closed = true; super.close(); }
    }

    static final class CloseTrackedWriter extends StringWriter {
        boolean closed;
        @Override public void close() { closed = true; }
    }

    static Reader failingReader() {
        return new Reader() {
            private boolean first = true;
            @Override public int read(char[] target, int offset, int length)
                    throws IOException {
                if (first) {
                    first = false;
                    "abc".getChars(0, 3, target, offset);
                    return 3;
                }
                throw new IOException("simulated read failure");
            }
            @Override public void close() {}
        };
    }

    public static void main(String[] args) throws Exception {
        String text = "Hi \uD83D\uDE00";
        var source = new CloseTrackedReader(text);
        var destination = new CloseTrackedWriter();
        long count = source.transferTo(destination);
        System.out.println("chars=" + count + ", utf8Bytes=" +
                text.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("text=" + destination);
        System.out.println("autoClosedReader=" + source.closed +
                ", autoClosedWriter=" + destination.closed);

        try (var reader = new StringReader("abcdef");
             var writer = new StringWriter()) {
            reader.read();
            System.out.println("remaining=" + reader.transferTo(writer) +
                    ", data=" + writer);
            System.out.println("atEOF=" + reader.transferTo(new StringWriter()));
        }

        try {
            new StringReader("abc").transferTo(null);
        } catch (NullPointerException expected) {
            System.out.println("nullWriter=NullPointerException");
        }

        var partialDestination = new StringWriter();
        try (var broken = failingReader()) {
            broken.transferTo(partialDestination);
        } catch (IOException expected) {
            System.out.println("partialWritten=" + partialDestination +
                    ", error=" + expected.getMessage());
        }

        var pipeReader = new PipedReader();
        var pipeWriter = new PipedWriter(pipeReader);
        var publishedFirst = new CountDownLatch(1);
        var finishProducer = new CountDownLatch(1);
        var producer = new Thread(() -> {
            try (var writer = pipeWriter) {
                writer.write("alpha");
                writer.flush();
                publishedFirst.countDown();
                finishProducer.await();
                writer.write("-omega");
            } catch (IOException | InterruptedException ex) {
                throw new RuntimeException(ex);
            }
        }, "demo-pipe-producer");
        var pool = Executors.newSingleThreadExecutor();
        producer.start();
        try {
            var pipeDestination = new StringWriter();
            Future<Long> transferred = pool.submit(() ->
                    pipeReader.transferTo(pipeDestination));
            publishedFirst.await();
            boolean waitingForEOF = false;
            try {
                transferred.get(150, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                waitingForEOF = true;
            }
            System.out.println("waitingForEOF=" + waitingForEOF);
            finishProducer.countDown();
            long copied = transferred.get(3, TimeUnit.SECONDS);
            System.out.println("pipeChars=" + copied +
                    ", pipeText=" + pipeDestination);
            producer.join(3000);
            System.out.println("producerFinished=" + !producer.isAlive());
        } finally {
            finishProducer.countDown();
            pipeWriter.close();
            pipeReader.close();
            pool.shutdownNow();
            producer.join(1000);
        }
    }
}
```

Biên dịch với Java 10:

```bash
javac --release 10 ReaderTransferToBlockingDemo.java
java ReaderTransferToBlockingDemo
```

Stdout của **lần chạy đã được kiểm chứng**:

```text
chars=5, utf8Bytes=7
text=Hi 😀
autoClosedReader=false, autoClosedWriter=false
remaining=5, data=bcdef
atEOF=0
nullWriter=NullPointerException
partialWritten=abc, error=simulated read failure
waitingForEOF=true
pipeChars=11, pipeText=alpha-omega
producerFinished=true
```

### Giải thích theo nhóm

**1. Số ký tự không bằng số byte.** Chuỗi `"Hi 😀"` có **5 đơn vị `char` Java/UTF-16**: `H`, `i`, dấu cách và một cặp surrogate cho biểu tượng cảm xúc. Nội dung đó có **7 byte UTF-8**, nhưng `Reader.transferTo` trả **5**, không phải 7.

**2. Reader/Writer vẫn mở sau lời gọi.** Hai cờ `closed` là `false` ngay sau `transferTo`, xác nhận không có `close()` tự động. Chủ sở hữu tài nguyên phải đóng ở thời điểm thích hợp; class kiểm tra trong demo là nguồn/đích in-memory nên không tiêu thụ tài nguyên hệ điều hành đáng kể.

**3. Chỉ chuyển phần còn lại.** Đã gọi `reader.read()` trước nên một ký tự `a` đã được tiêu thụ; `transferTo` tiếp tục từ `b` đến `f`, trả `5`. Gọi lần nữa tại EOF trả `0`.

**4. Null đích gây lỗi.** `transferTo(null)` ném `NullPointerException`. Đó là lỗi lập trình, không phải tín hiệu nguồn đã hết dữ liệu.

**5. Lỗi giữa chừng có thể ghi một phần.** Reader tự định nghĩa trả `"abc"` ở lần đọc đầu tiên rồi ném `IOException`; Writer đã chứa `"abc"` khi lỗi xuất hiện. Điều này chứng minh không có “all-or-nothing transaction”.

**6. Pipe chưa EOF vẫn chặn.** Producer thread ghi `"alpha"` và `flush()`, rồi cố ý chờ một latch trước khi ghi `"-omega"` và đóng Writer. Future thực hiện `pipeReader.transferTo(pipeDestination)`. Trong lúc producer còn mở Writer và chưa phát EOF, `Future.get(150 ms)` hết hạn; do đó dòng `waitingForEOF=true` xuất hiện. Khi main cho producer gửi phần còn lại và đóng Writer, `transferTo` hoàn tất với 11 ký tự và chuỗi `"alpha-omega"`.

**7. Demo có cleanup có kiểm soát.** Latch và tài nguyên pipe được giải phóng trong `finally`; future có giới hạn thời gian chờ khi chốt kết quả. Đây là mẫu **thử nghiệm hành vi**, không phải tuyên bố rằng bọc mọi `transferTo` trong một Future là đủ để tạo timeout I/O production.

### Không tự phát triển một bài test chặn vĩnh viễn

Không nên demo bằng cách gọi `transferTo` trên pipe còn mở trong cùng thread rồi hy vọng code chạy đến dòng `close()` nằm **sau lệnh chặn**. Dòng close có thể không bao giờ được thực thi. Dùng thread riêng, điều khiển thời điểm EOF và có cleanup rõ ràng như ví dụ.

## 13. Sự khác biệt giữa ký tự, code point và byte

`Reader`/`Writer` làm việc với **dòng ký tự Java**. Trong xử lý `Reader.transferTo`, số lượng chuyển về mặt hợp đồng là số ký tự được đọc và ghi theo abstraction Java, không phải số byte sau encoding.

Ví dụ:

```java
String value = "Hi 😀";

System.out.println(value.length()); // 5 (UTF-16 code units)
System.out.println(value.codePointCount(0, value.length())); // 4
System.out.println(
        value.getBytes(java.nio.charset.StandardCharsets.UTF_8).length
); // 7
```

Đối với chuỗi này:

- **5** là số `char` Java/UTF-16 code units; cũng là kết quả khi toàn bộ chuỗi được `StringReader.transferTo(new StringWriter())`.
- **4** là số Unicode code points.
- **7** là số byte khi mã hóa UTF-8.

Các số này khác nhau không có nghĩa `transferTo` làm mất dữ liệu. Nó đang làm việc ở **tầng ký tự**, còn việc mã hóa thành byte do `InputStreamReader`/`OutputStreamWriter` và charset quy định.

Nếu ứng dụng muốn chuyển dữ liệu **nhị phân** và đếm byte, hãy dùng abstraction byte stream phù hợp như `InputStream.transferTo(OutputStream)` (có từ Java 9), không ép dữ liệu nhị phân đi qua `Reader` và `Writer` một cách tùy tiện.

## 14. Bảng lựa chọn kỹ thuật

| Nhu cầu thật sự | Cách phù hợp | Cảnh báo |
| --- | --- | --- |
| Chép toàn bộ file văn bản hữu hạn | `Reader.transferTo(Writer)` + `try-with-resources` | Vẫn có thể chặn khi I/O chậm/lỗi |
| Chép phần còn lại của `StringReader` | `transferTo` | Trả về tại EOF, không chép lại phần đã đọc |
| Pipe producer gửi xong và đóng | `transferTo` trong consumer phù hợp | Phải có producer khác phát EOF |
| Một message trên socket persistent | Đọc theo framing của giao thức | Không đợi EOF của toàn socket |
| Một dòng văn bản theo protocol | `BufferedReader.readLine()` với chính sách độ dài/timeout | `readLine()` cũng có thể chặn |
| Giới hạn N ký tự | Vòng `read/write` với `remaining` | Giới hạn số lượng, **không** phải giới hạn thời gian |
| Live stream vô hạn | Xử lý tăng dần từng chunk/event | `transferTo` có thể không trả về |
| Nguồn không tin cậy | Timeout thực ở tầng I/O + giới hạn + cancel/cleanup | `Future.get(timeout)` không tự dừng I/O |
| Chuyển dữ liệu nhị phân | `InputStream.transferTo(OutputStream)` | Đếm byte, không giống Reader |
| Muốn kết quả bền vững ở đĩa | Thiết kế flush/close/commit tương ứng | `transferTo` không bảo đảm “đã fsync” |

Quy tắc chọn ngắn gọn: **dùng `transferTo` khi muốn chuyển mọi ký tự còn lại đến EOF; dùng API đọc có giới hạn hoặc theo thông điệp nếu ranh giới công việc không trùng với EOF.**

## 15. Những hiểu lầm và lỗi thường gặp

1. **“Có dữ liệu trong pipe rồi thì `transferTo` phải trả về.”** Không. Nó tiếp tục đọc đến EOF; nguồn còn mở có thể giữ lệnh chặn.
2. **“Producer `flush()` nghĩa là transfer đã kết thúc.”** Sai. Flush không phải tín hiệu EOF.
3. **“`ready() == false` nghĩa là nguồn hết.”** Sai. Đó chỉ là thông tin khả năng read không chặn tại thời điểm kiểm tra, không phải EOF.
4. **“Một newline làm `Reader.transferTo` dừng.”** Sai. Newline chỉ là ký tự; muốn dừng theo dòng, dùng logic framing phù hợp.
5. **“`Future.get(5, SECONDS)` bảo đảm thread I/O kết thúc sau 5 giây.”** Sai. Nó chỉ giới hạn thời gian chờ kết quả của caller; worker có thể vẫn chạy.
6. **“`cancel(true)` chắc chắn giải phóng mọi Reader.”** Sai. Interrupt/async-close phụ thuộc loại stream/Writer và không được `transferTo` bảo đảm chung.
7. **“Chỉ read mới chặn, write không.”** Sai. Writer cũng có thể chặn vô thời hạn.
8. **“`transferTo` sẽ đóng và flush hai luồng hộ mình.”** Sai về close; về flush không có cam kết tổng quát. Dùng lifecycle quản lý sở hữu.
9. **“Nếu lỗi, đích vẫn sạch.”** Sai. Có thể đã ghi một phần. Không retry vô điều kiện trên cùng đích.
10. **“Trả `long` chính là số byte.”** Sai với Reader; đếm ký tự Java, không phải bytes hay Unicode codepoints.
11. **“Lấy `StringWriter` hứng live stream vô hạn không tốn bộ nhớ.”** Sai. Writer in-memory có thể tích lũy dữ liệu không giới hạn.
12. **“Tôi chỉ cần 100 ký tự, vậy dùng `transferTo` rồi `substring(0,100)`.”** Có thể chặn mãi trước khi tạo được chuỗi; nếu cần 100 ký tự, giới hạn ngay khi đọc.
13. **“Đọc đến EOF là đồng nghĩa một thông điệp HTTP đã xong.”** Không đúng nói chung. Ranh giới thông điệp phải được xác định theo protocol; kết nối có thể tiếp tục mở.
14. **“Gọi `transferTo` lần nữa sau IOException sẽ tự resume an toàn.”** Không có bảo đảm. Có thể đã đọc/ghi một phần và trạng thái đã thay đổi.
15. **“Kích thước buffer luôn cố định theo JDK đang dùng.”** Không dựa vào chi tiết implementation. Hợp đồng chỉ là chuỗi ký tự được chuyển đúng thứ tự đến EOF.

## 16. Checklist code review cho Reader.transferTo

- [ ] **Nguồn có EOF hữu hạn dự kiến không?** Ai phát tín hiệu hoàn tất, và khi nào?
- [ ] **Ranh giới nghiệp vụ có phải toàn bộ stream không?** Nếu chỉ một message, đã có framing chưa?
- [ ] **Có nguy cơ Writer bị chặn không?** Đã kiểm tra backpressure và đích I/O chưa?
- [ ] **Có giới hạn thời gian thực sự ở tầng I/O không?** Hay chỉ có `Future.get(timeout)`?
- [ ] **Thread interruption/async-close có được implementation hỗ trợ như kỳ vọng không?** Đã test đúng loại Reader/Writer chưa?
- [ ] **Sở hữu nguồn/đích thuộc về ai?** Dùng `try-with-resources` ở đúng scope, không vô ý đóng stream caller.
- [ ] **Có Writer buffered cần flush/close/commit theo hợp đồng không?**
- [ ] **Chính sách IOException có đánh dấu kết quả một phần là thất bại không?** Đã có cơ chế rollback/temp file/idempotency nếu cần chưa?
- [ ] **Đầu vào có thể quá lớn hoặc vô hạn không?** Writer in-memory, giới hạn bytes/chars và RAM có phù hợp không?
- [ ] **Có phân biệt chars/bytes/code points trong kết quả, log và quota không?**
- [ ] **Đã test read thành công, EOF, chờ chưa EOF, writer lỗi, reader lỗi và cancellation chưa?**
- [ ] **Không dùng `ready()` làm EOF detector hoặc `flush()` làm tín hiệu kết thúc?**

## 17. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `Reader.transferTo(writer)` có trả về ngay sau khi đọc được ký tự đầu tiên không?

**Đáp án:** Không. Nó đọc toàn bộ các ký tự còn lại đến EOF, hoặc ném lỗi nếu I/O thất bại. Khi nguồn còn mở và chưa EOF, nó có thể tiếp tục chặn.

**Câu 2.** Vì sao một `PipedReader` đã nhận `"abc"` vẫn có thể khiến `transferTo` chặn?

**Đáp án:** Bên ghi chưa đóng và có thể còn gửi dữ liệu. `transferTo` chưa thấy EOF, nên tiếp tục đọc/chờ. `flush()` chỉ đẩy phần dữ liệu hiện có, không kết thúc nguồn.

**Câu 3.** `Reader.ready() == false` có chứng minh reader đã ở EOF không?

**Đáp án:** Không. Có thể chỉ là chưa có dữ liệu sẵn lúc kiểm tra. EOF được xác định theo kết quả đọc `-1`/contract nguồn.

**Câu 4.** Nếu `Future.get(1, SECONDS)` hết hạn khi thread đang gọi `transferTo`, thread đó có tự dừng không?

**Đáp án:** Không. Caller nhận `TimeoutException` nhưng tác vụ I/O có thể tiếp tục. Cần cơ chế timeout/cancellation và đóng tài nguyên phù hợp với stream.

**Câu 5.** `transferTo` có tự đóng Reader/Writer khi chạy xong thành công không?

**Đáp án:** Không. Nó không đóng hai luồng. Chủ sở hữu phải quản lý close bằng `try-with-resources` hoặc lifecycle được định nghĩa.

**Câu 6.** Nếu Writer đã nhận 1.000 ký tự rồi Reader ném `IOException`, có được coi toàn bộ việc chuyển đã thất bại không?

**Đáp án:** Có. Có thể có dữ liệu một phần ở đích, nhưng không có kết quả đầy đủ. Nên đóng luồng và dùng chiến lược phục hồi/rollback có chủ đích.

**Câu 7.** `long count = new StringReader("Hi 😀").transferTo(writer);` thường bằng bao nhiêu?

**Đáp án:** `5` Java `char`/UTF-16 code units, không phải 4 Unicode codepoints hoặc 7 UTF-8 bytes.

**Câu 8.** Có thể dùng `Reader.transferTo` cho một giao thức gửi nhiều message trên cùng socket persistent không?

**Đáp án:** Không phù hợp nếu cần kết thúc sau từng message trong khi socket vẫn mở. Cần đọc theo framing/length/delimiter của giao thức.

**Câu 9.** Đọc tối đa N ký tự bằng vòng `read/write` có tự bảo đảm hoàn thành trong thời gian T không?

**Đáp án:** Không. Lần đọc tiếp theo vẫn có thể chặn khi nguồn mới gửi ít hơn N ký tự. Độ dài và thời gian là hai giới hạn khác nhau.

**Câu 10.** Nếu `transferTo` đọc từ file hữu hạn nhưng ghi đến Writer đang bị nghẽn, có thể chặn không?

**Đáp án:** Có. Javadoc cho phép chặn vô thời hạn ở cả đọc lẫn ghi; nguồn hữu hạn không loại bỏ nguy cơ chặn ở đầu ra.

**Câu 11.** Vì sao không gọi `transferTo` trong cùng thread rồi đặt `pipeWriter.close()` phía sau?

**Đáp án:** Nếu Reader đang chờ EOF do Writer vẫn mở, thread không thể tiến tới câu `close()`, gây deadlock/treo. Producer hoặc lifecycle khác phải phát tín hiệu kết thúc.

**Câu 12.** Một ứng dụng nhận stream text liên tục và cần cập nhật UI theo từng dòng nên thiết kế ra sao?

**Đáp án:** Dùng đọc/parse tăng dần theo delimiter/protocol, có giới hạn độ dài, timeout, cancellation và backpressure. Không chờ toàn bộ stream kết thúc mới chuyển nội dung cho UI.

**Câu 13.** Khi nào có thể retry an toàn sau `IOException`?

**Đáp án:** Chỉ khi có chiến lược thiết kế rõ ràng: nguồn có thể phát lại từ đầu hoặc một checkpoint đáng tin, đích có thể reset/rollback hoặc ghi vào file tạm mới, và việc lặp không gây nhân đôi dữ liệu. `transferTo` không tự cung cấp các bảo đảm đó.

**Câu 14.** `StringWriter` có phù hợp làm đích cho nguồn không giới hạn không?

**Đáp án:** Không nếu không có hạn mức. Nội dung tích lũy trong bộ nhớ có thể tăng không giới hạn. Dùng cách xử lý tăng dần hoặc một Writer phù hợp với lưu trữ có kiểm soát.

## 18. Tài liệu chính thức vẫn còn áp dụng

- [Java SE — Reader.transferTo(Writer)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): hợp đồng chuyển đến EOF, khả năng chặn vô thời hạn, xử lý lỗi một phần, không tự close, tính phụ thuộc implementation của interruption.
- [Java SE — Reader.read và Reader.ready](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html): khác biệt giữa EOF, đọc có thể chặn và tín hiệu “ready”.
- [Java SE — PipedReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PipedReader.html): pipe ký tự liên thread, blocking read và EOF.
- [Java SE — PipedWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PipedWriter.html): ghi và đóng đầu gửi của pipe.
- [Java SE — Writer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Writer.html): `write`, `flush`, `close` và quản lý đích.
- [Java SE — Future.get(timeout)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): timeout đợi kết quả và cancellation.
- [Java SE — Socket.setSoTimeout](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/Socket.html#setSoTimeout(int)): timeout blocking read của socket input stream khi được hỗ trợ.

**Kết luận:** `Reader.transferTo` rất phù hợp khi **cần lấy mọi ký tự còn lại cho đến EOF**, nhưng không phải API “đọc phần có sẵn rồi trả về”. Với nguồn chưa kết thúc, phải thiết kế **ranh giới dữ liệu, thời điểm EOF, timeout/cancellation và chiến lược xử lý tăng dần**; với Writer, phải xử lý **khả năng bị chặn và kết quả ghi một phần**. Đó là cách dùng Java 10+ an toàn và dễ dự đoán.
