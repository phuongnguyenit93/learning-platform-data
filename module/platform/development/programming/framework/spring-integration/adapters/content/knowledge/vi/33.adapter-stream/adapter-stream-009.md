# Buffer size và hiệu năng

## 1. Bài toán: một tham số `bufferSize` không giải quyết mọi nút thắt

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration kết nối các hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Khi dữ liệu đi qua file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, chúng ta phải giữ đúng hợp đồng message, xử lý lỗi và vòng đời kết nối. Trong chương **Adapter Stream**, bài **Buffer size và hiệu năng** giải thích tác động của kích thước bộ đệm đối với **throughput, latency, memory, GC, số lời gọi I/O và backpressure**.

Một ứng dụng đọc file 10 GiB qua `InputStream`, chuyển thành `Message<byte[]>` và ghi ra một `OutputStream`. Nếu mỗi message chỉ có 1 byte, overhead tạo message/dispatch và số lần gọi I/O có thể rất lớn. Nếu mỗi message chứa 64 MiB, bộ nhớ đỉnh, thời gian chờ consumer, kích thước queue và khả năng khôi phục sau lỗi có thể trở nên khó kiểm soát.

```text
Disk / Pipe / Socket / SDK
           |
      InputStream
           |
      I/O buffering             (A) java.io / source buffer
           |
 ByteStreamReadingMessageSource
           |
      bytesPerMessage           (B) payload bytes per Spring Message
           |
       Inbound poller
           |
      MessageChannel
           |
    [QueueChannel capacity]     (C) number of pending messages
           |
       Transform/Validate
           |
     ByteStreamWritingMessageHandler
           |
      output buffering          (D) java.io / handler buffer
           |
      OutputStream
           |
      External reader
```

**Bốn thứ (A), (B), (C), (D) là những knobs khác nhau.** Không nên gọi chung là “bufferSize” rồi điều chỉnh tất cả lên 64 KiB mà chưa đo. Khi nguồn là text, còn có **charset decoder buffer**, **max line length** và **record parser**; khi đích là file/remote service, còn có **filesystem cache, TCP socket buffers, SDK batching và ACK nghiệp vụ**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `BufferedInputStream`, `BufferedOutputStream`, `BufferedReader`, `BufferedWriter` và buffer do Spring Integration adapter cấu hình.
2. Giải thích `ByteStreamReadingMessageSource.setBytesPerMessage(...)`, `setShouldTruncate(...)` và constructor `bufferSize`.
3. Cấu hình `ByteStreamWritingMessageHandler(OutputStream, int)` và character stream tương ứng.
4. Dự đoán trade-off khi buffer quá nhỏ/quá lớn: số message, allocation, latency, throughput và memory.
5. Tính ngân sách bộ nhớ từ chunk size, queue capacity, concurrency, reassembler và parser.
6. Không nhầm **buffer boundary** với **framing, line/record boundary, EOF hoặc transaction**.
7. Xây dựng Spring Boot Java DSL và XML cấu hình luồng byte với tham số có thể thử nghiệm.
8. Viết bài thử kiểm đếm bytes, partial read, UTF-8 split và đo microbenchmark đúng cách.
9. Thiết lập mục tiêu SLO/metrics, thí nghiệm nhiều mức buffer và ra quyết định dựa trên kết quả đo.
10. Chọn File/SFTP/TCP/JMS/Kafka hoặc adapter chuyên dụng khi cần tối ưu trên giao thức có ACK/session/offset riêng.

## 2. Cơ chế của Java I/O buffering

### 2.1. `InputStream` và `BufferedInputStream`

`InputStream.read()` đọc một byte, còn `InputStream.read(byte[],off,len)` yêu cầu đọc **tối đa** `len` byte (không bảo đảm đủ `len` trong một lần). `BufferedInputStream` giữ một vùng đệm ở tầng Java để giảm số lượt gọi xuống nguồn bên dưới khi ứng dụng đọc những đoạn nhỏ.

```java
import java.io.BufferedInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (InputStream input = new BufferedInputStream(
        Files.newInputStream(Path.of("data/input.bin")),
        16 * 1024)) {

    byte[] chunk = new byte[4096];
    int n;
    while ((n = input.read(chunk)) != -1) {
        // Xu ly dung n byte, KHONG phai toan bo chunk.length.
        consume(chunk, 0, n);
    }
}
```

Đoạn code là **mẫu Java I/O**: `consume(...)` là method do ứng dụng cung cấp. Không truyền nguyên `chunk` sang code bất đồng bộ rồi ghi đè nó ở vòng lặp kế tiếp; phải sao chép bytes thực cần hoặc dùng chiến lược pool/buffer có ownership rõ ràng.

**Buffering giảm overhead trong một số workload**, nhưng không biến file read thành network-free hoặc transaction. Nếu bên dưới là `ByteArrayInputStream` có bytes sẵn trong RAM, việc thêm `BufferedInputStream` chưa chắc cải thiện hiệu năng, có thể chỉ thêm copy.

### 2.2. `OutputStream` và `BufferedOutputStream`

`BufferedOutputStream` tích lũy các lần ghi nhỏ trước khi đẩy xuống sink. Trong workload nhiều message nhỏ, điều này có thể giảm overhead gọi I/O.

```java
import java.io.BufferedOutputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (OutputStream output = new BufferedOutputStream(
        Files.newOutputStream(
                Path.of("data/output.bin"),
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE),
        16 * 1024)) {

    output.write(new byte[] {0x41, 0x42, 0x43});
    output.flush();
}
```

`flush()` đẩy dữ liệu khỏi lớp buffer theo contract Java I/O; **không đồng nghĩa `fsync`, remote receiver ACK hoặc database commit**. `close()` kết thúc stream và có thể flush, nhưng cũng có thể ném `IOException`. Mở output với `TRUNCATE_EXISTING` là chủ động ghi đè dữ liệu cũ — chỉ thích hợp khi hợp đồng cho phép.

### 2.3. Double buffering: thêm một tầng chưa chắc tốt

```text
FileInputStream
    -> BufferedInputStream(8 KiB)
        -> ByteStreamReadingMessageSource(input, 16 KiB)
            -> payload byte[4 KiB]
```

Tùy implementation của adapter, bạn có thể đang dùng **hai tầng buffering** mà không giảm số thao tác nguồn thật thêm bao nhiêu, nhưng tăng bộ nhớ và copy. Tương tự, `BufferedOutputStream` bên ngoài handler có buffer riêng có thể làm chiến lược flush/close khó nhìn.

Đặt một **resource owner** cho chain, lập bản đồ những lớp buffer đang dùng, rồi đo trước/sau khi bỏ bớt lớp không cần thiết. Không suy đoán rằng “càng nhiều buffer càng nhanh”.

### 2.4. `Reader`/`Writer` xử lý ký tự, không xử lý byte trực tiếp

| API | Đơn vị xử lý | Buffer thuộc tầng |
| --- | --- | --- |
| `BufferedInputStream` | Byte | Java I/O |
| `BufferedOutputStream` | Byte | Java I/O |
| `BufferedReader` | UTF-16 code units / dòng | Character I/O |
| `BufferedWriter` | UTF-16 code units | Character I/O |
| `InputStreamReader` | Giải mã bytes → characters | Charset decoder |
| `OutputStreamWriter` | Mã hóa characters → bytes | Charset encoder |
| Spring `Message<byte[]>` | Một payload bytes | Messaging |
| Spring `Message<String>` | Một String payload | Messaging |

**Buffer size theo byte** và **buffer size theo character** không được quy đổi bằng một hệ số cố định khi dùng UTF-8: một Unicode code point có thể chiếm 1–4 bytes và 1–2 UTF-16 code units. Không dùng `String.length()` để tính length-prefix cho protocol byte-oriented.

## 3. Bốn kích thước cần phân biệt

| Ký hiệu | Tham số | Điều nó điều chỉnh | Điều nó không bảo đảm |
| --- | --- | --- | --- |
| `B_in` | Input stream buffer | Đọc gom từ nguồn | Một read = một record |
| `C_msg` | `bytesPerMessage` | Source cố đọc bao nhiêu bytes cho một Spring message | Payload luôn dài đúng `C_msg` |
| `Q` | `QueueChannel(capacity)` | Tối đa bao nhiêu **messages** đang chờ | Q × C_msg là toàn bộ heap |
| `B_out` | Output stream buffer | Gộp các lần ghi nhỏ | Khi write trả về là remote đã commit |

Ngoài ra, phải xác định:

- `F_max`: **max frame/record bytes**, giới hạn parser/reassembler.
- `N`: số message đang **in-flight** ngoài queue.
- `E`: số executor tasks đang chờ.
- `R`: số bản sao dữ liệu trong decode/transform/serialization.
- `L_target`: độ trễ đầu–cuối theo SLO.

### Ví dụ không được nhầm

```text
B_in  = 8 KiB
C_msg = 64 KiB
Q     = 32 messages
B_out = 8 KiB
```

Ở đây queue có thể giữ tới khoảng **2 MiB payload** nếu mỗi message đủ 64 KiB, **chưa tính** headers, object wrappers, message in-flight, decoder state và I/O buffers. Không phải vì `B_in=8 KiB` mà mỗi message chỉ 8 KiB, cũng không phải vì `Q=32` mà tổng backlog chỉ 32 KiB.

## 4. ByteStreamReadingMessageSource trong Spring Integration 6.5

Với Spring Integration **6.5.x**, class chính là:

```java
import java.io.InputStream;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;

InputStream input = /* InputStream do ung dung so huu */;

ByteStreamReadingMessageSource source =
        new ByteStreamReadingMessageSource(input, 8192);

source.setBytesPerMessage(4096);
source.setShouldTruncate(true);
```

API đã được xác minh với **Spring Integration Reference 6.5** và Javadoc:

- Constructor `ByteStreamReadingMessageSource(InputStream)`.
- Constructor `ByteStreamReadingMessageSource(InputStream, int bufferSize)`.
- Setter `setBytesPerMessage(int)`, **mặc định 1024 bytes**.
- Setter `setShouldTruncate(boolean)` để kiểm soát payload trong trường hợp số bytes thực đọc ít hơn vùng mảng ban đầu.

**Constructor `bufferSize` và `setBytesPerMessage` là hai cấu hình khác nhau.** Với file lớn, bạn có thể thử các cặp `(8 KiB, 4 KiB)`, `(16 KiB, 16 KiB)` hoặc `(64 KiB, 16 KiB)`; nhưng không có bảo đảm cấu hình lớn nhất sẽ thắng trong mọi môi trường.

### 4.1. Khi `read(...)` chỉ trả một phần

```text
Requested bytesPerMessage: 8192 bytes
Actual bytes read:         2751 bytes
shouldTruncate(true):      payload length should reflect 2751 bytes
```

Một `InputStream` có thể trả ít hơn số byte yêu cầu **mà không phải EOF**. Với network/pipe, short read là bình thường. `shouldTruncate(true)` quan trọng để downstream không hiểu phần dữ liệu đệm chưa thực nhận là payload hợp lệ. Không dùng `payload.length == bytesPerMessage` làm điều kiện record hoàn chỉnh.

### 4.2. Vì sao rất nhiều chunk nhỏ có thể chậm?

Giả sử file có `D` bytes và mỗi message chứa khoảng `C_msg` bytes; số message tạo ra xấp xỉ:

\[
N_{\mathrm{messages}}\approx \left\lceil D/C_{\mathrm{msg}}\right\rceil
\]

Nếu `C_msg` nhỏ, mỗi message kéo theo overhead:

- Tạo `Message<byte[]>`, headers và possibly array copy.
- Poller gọi `receive()` và dispatch qua channel.
- Header propagation/tracing/metrics.
- Transformer/handler invocation.
- Queue enqueue/dequeue nếu có channel đệm.
- Kiểm tra exception và ghi audit.

Không cần đoán số nano giây của một Spring message; hãy **đếm messages/sec, bytes/sec, allocation/GC và latency** trên chính flow. Hiệu năng không tỉ lệ tuyến tính hoàn hảo với `C_msg` vì read có thể short, handler có fixed overhead và sink có giới hạn riêng.

### 4.3. Chunk lớn không tự tạo record lớn

`bytesPerMessage=64*1024` có thể đọc **nhiều dòng NDJSON trong một chunk** hoặc chỉ **một phần JSON object**. Với text UTF-8, một ký tự nhiều byte còn có thể bị chia giữa hai chunk. Phải dùng framing/reassembler hoặc streaming decoder stateful, có **`maxFrameBytes`**, trước khi parse schema.

```text
Input UTF-8 for "Đ": C4 90

Chunk A ends: ... C4
Chunk B starts: 90 ...

decodeStrict(A) -> lỗi truncated UTF-8
decodeStrict(B) -> lỗi continuation byte

reassemble -> C4 90 -> decode -> "Đ"
```

Tăng chunk size làm giảm xác suất một ký tự bị cắt nhưng **không loại bỏ vấn đề boundary**. Framing là hợp đồng, buffer chỉ là tối ưu.

## 5. ByteStreamWritingMessageHandler: buffer cho đầu ra

Với Spring Integration 6.5:

```java
import java.io.OutputStream;
import org.springframework.integration.stream.ByteStreamWritingMessageHandler;

OutputStream destination = /* stream do ung dung cap */;

ByteStreamWritingMessageHandler handler =
        new ByteStreamWritingMessageHandler(destination, 8192);
```

Constructor nhận `OutputStream` và tùy chọn `bufferSize`; handler là một `MessageHandler` ghi payload **`byte[]`** xuống stream. Nó có thể được đăng ký qua `@ServiceActivator`, Java DSL `.handle(...)` hoặc XML outbound channel adapter.

### 5.1. Ghi nhiều message nhỏ

```text
Message #1: 100 bytes
Message #2: 200 bytes
Message #3: 300 bytes
        |
ByteStreamWritingMessageHandler
        |
OutputStream with buffering
        |
External destination receives byte stream
```

Việc gộp write ở tầng buffer **không tự thêm delimiter**. Reader sẽ nhìn một dãy bytes nối tiếp; nếu cần ba record phải thiết kế newline, length-prefix hoặc protocol serialization. `bufferSize` không phải frame size.

### 5.2. Throughput cao hơn có thể đổi lấy latency

Với một đích cần nhận dữ liệu ngay sau từng event, tăng buffer có thể làm dữ liệu ở trong Java memory lâu hơn **tùy chính sách flush**. Với một file batch chờ đóng ở cuối job, buffering có thể hữu ích hơn. Phải kiểm tra cách handler/wrapper cụ thể flush ở phiên bản runtime và đo **time-to-visible** ở reader, không chỉ throughput ở phía producer.

### 5.3. Phân biệt write / flush / close / durability

| Hành động | Có nghĩa | Không bảo đảm |
| --- | --- | --- |
| `MessageChannel.send()` | Channel chấp nhận message theo semantics của loại channel | Bên nhận đã commit |
| `OutputStream.write(...)` | Yêu cầu ghi bytes vào tầng I/O | Đã fsync vào disk |
| `BufferedOutputStream.flush()` | Đẩy bytes khỏi Java buffer xuống tầng dưới | Reader bên kia đã xử lý |
| `OutputStream.close()` | Kết thúc resource, có thể flush/giải phóng | Transaction giữa nhiều hệ thống đã hoàn tất |
| `FileChannel.force(...)` | Yêu cầu đồng bộ bytes/metadata theo contract filesystem | Tự có atomic file publication |
| Business ACK | Bên nhận phản hồi theo protocol | Mức durability tùy hợp đồng ACK |

**Không tự báo giao hàng exactly-once** chỉ vì một lời gọi `write()` hoặc `flush()` thành công.

## 6. CharacterStreamReader/Writer: buffer ký tự và dòng quá dài

`CharacterStreamReadingMessageSource` nhận `Reader` và có constructor:

```java
import java.io.Reader;
import org.springframework.integration.stream.CharacterStreamReadingMessageSource;

Reader reader = /* Reader UTF-8 da duoc ung dung tao */;
CharacterStreamReadingMessageSource source =
        new CharacterStreamReadingMessageSource(reader, 8192, true);
```

Đối số `8192` trong ví dụ là **số characters của `BufferedReader`**, không phải kích thước byte trên wire. Đối số `true` bật chế độ có thể **block để phát hiện EOF** và công bố `StreamClosedEvent`. Nếu để `false` (mặc định), `receive()` có thể trả `null` khi `Reader.ready()==false` mà **chưa xác nhận EOF**.

### 6.1. Buffer reader không phải max line size

`BufferedReader.readLine()` có thể tích lũy một dòng lớn hơn 8192 chars; nó không tự reject dòng quá dài. Nếu đối tác gửi một dòng 500 MiB không có newline, ứng dụng vẫn có nguy cơ OOM dù `bufferSize=8192`. Cần **bounded line parser** hoặc giới hạn bytes/file ở trước bước tích lũy không kiểm soát.

### 6.2. CharacterStreamWritingMessageHandler

```java
import java.io.Writer;
import org.springframework.integration.stream.CharacterStreamWritingMessageHandler;

Writer writer = /* Writer duoc ung dung cap */;

CharacterStreamWritingMessageHandler handler =
        new CharacterStreamWritingMessageHandler(writer, 8192);

handler.setShouldAppendNewLine(true);
```

Ở đây `bufferSize=8192` không tự quyết định charset: khi dùng `OutputStreamWriter`, encoding được chọn từ lúc tạo Writer. `setShouldAppendNewLine(true)` thêm newline sau message; không bật đồng thời nếu payload đã có delimiter.

**Text buffering và binary buffering là hai trường hợp khác nhau.** Khi phân tích byte throughput, cần đếm số bytes sau UTF-8 encoding, không dùng `String.length()` làm byte count.

## 7. Spring Boot Java DSL: cấu hình ba kích thước độc lập

Ứng dụng mẫu dùng **Java 17+** và Spring Boot quản lý một phiên bản Spring Integration **6.5.x** tương thích. Job đọc một file binary cố định rồi ghi sang một file khác bằng hai stream adapters. Nó dành cho việc so sánh kích thước buffer và correctness, **không phải** giải pháp đồng bộ file production với checkpoint/atomic rename.

### 7.1. Dependencies

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-stream</artifactId>
    </dependency>
</dependencies>
```

Không trộn các artifact Spring Integration nhiều phiên bản. Các classes của stream trong ví dụ dùng package `org.springframework.integration.stream` của **6.5**; kiểm tra Javadoc khi nâng lên dòng framework khác.

### 7.2. application.yml

```yaml
app:
  copy:
    input-path: ${STREAM_INPUT_PATH:./data/source.bin}
    output-path: ${STREAM_OUTPUT_PATH:./data/copied.bin}
    input-buffer-bytes: ${STREAM_INPUT_BUFFER_BYTES:8192}
    bytes-per-message: ${STREAM_BYTES_PER_MESSAGE:16384}
    output-buffer-bytes: ${STREAM_OUTPUT_BUFFER_BYTES:8192}
    poll-delay-ms: ${STREAM_POLL_DELAY_MS:25}
```

Các tham số cho phép bạn thử nghiệm **một biến mỗi lần**. Input và output **phải khác path**, file đầu vào phải tồn tại; đường dẫn do operator đáng tin cung cấp, không lấy tên file tùy ý từ request người dùng. `poll-delay-ms` cũng ảnh hưởng throughput, nên phải giữ cố định khi so sánh riêng `bytes-per-message`.

### 7.3. Java configuration

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;
import org.springframework.integration.stream.ByteStreamWritingMessageHandler;

@SpringBootApplication
@EnableIntegration
public class StreamBufferSizingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamBufferSizingApplication.class, args);
    }

    @Bean(name = "copyInput", destroyMethod = "close")
    public InputStream copyInput(
            @Value("${app.copy.input-path}") String path)
            throws IOException {

        return Files.newInputStream(
                Path.of(path).toAbsolutePath().normalize());
    }

    @Bean(name = "copyOutput", destroyMethod = "close")
    public OutputStream copyOutput(
            @Value("${app.copy.input-path}") String inputPath,
            @Value("${app.copy.output-path}") String outputPath)
            throws IOException {

        Path source = Path.of(inputPath).toAbsolutePath().normalize();
        Path target = Path.of(outputPath).toAbsolutePath().normalize();
        if (source.equals(target)) {
            throw new IllegalArgumentException(
                    "Input path and output path must differ");
        }
        if (target.getParent() != null) {
            Files.createDirectories(target.getParent());
        }
        // Demo: intentionally replace prior output contents.
        return Files.newOutputStream(
                target,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    @Bean
    public IntegrationFlow binaryCopyFlow(
            @Qualifier("copyInput") InputStream input,
            @Qualifier("copyOutput") OutputStream output,
            @Value("${app.copy.input-buffer-bytes:8192}")
                    int inputBufferBytes,
            @Value("${app.copy.bytes-per-message:16384}")
                    int bytesPerMessage,
            @Value("${app.copy.output-buffer-bytes:8192}")
                    int outputBufferBytes,
            @Value("${app.copy.poll-delay-ms:25}")
                    long pollDelayMs) {

        validateBytes("inputBufferBytes", inputBufferBytes);
        validateBytes("bytesPerMessage", bytesPerMessage);
        validateBytes("outputBufferBytes", outputBufferBytes);
        if (pollDelayMs < 1 || pollDelayMs > 60_000) {
            throw new IllegalArgumentException(
                    "Invalid poll delay");
        }

        ByteStreamReadingMessageSource source =
                new ByteStreamReadingMessageSource(
                        input, inputBufferBytes);
        source.setBytesPerMessage(bytesPerMessage);
        source.setShouldTruncate(true);

        ByteStreamWritingMessageHandler writer =
                new ByteStreamWritingMessageHandler(
                        output, outputBufferBytes);

        return IntegrationFlow.from(
                    source,
                    endpoint -> endpoint
                            .id("binaryCopyInbound")
                            .poller(Pollers.fixedDelay(
                                            Duration.ofMillis(pollDelayMs))
                                    .maxMessagesPerPoll(1)))
                .handle(writer)
                .get();
    }

    private static void validateBytes(String name, int bytes) {
        if (bytes < 1 || bytes > 1024 * 1024) {
            throw new IllegalArgumentException(
                    name + " must be in [1, 1048576]");
        }
    }
}
```

Đặt lớp trong `StreamBufferSizingApplication.java`, thêm build Spring Boot tương thích. Đây là một **flow đồng bộ** do inbound poller kích hoạt. Không có `QueueChannel` giữa nguồn và sink: khi writer chậm, nó có thể làm lượt poll chậm, tạo backpressure theo call stack.

### 7.4. Phân tích từng tầng

| Dòng code | Chức năng | Chú ý |
| --- | --- | --- |
| `new ByteStreamReadingMessageSource(input, inputBufferBytes)` | Thiết lập adapter input với kích thước đệm được cấu hình | Khác `bytesPerMessage` |
| `setBytesPerMessage(bytesPerMessage)` | Mục tiêu payload size của `Message<byte[]>` | Không tạo framing |
| `setShouldTruncate(true)` | Giữ độ dài payload tương ứng bytes đã thực đọc | Không có nghĩa record hoàn chỉnh |
| `Pollers.fixedDelay(...)` | Điều tiết tần suất polling | Không phải timeout của read/write |
| `.maxMessagesPerPoll(1)` | Giới hạn số message mỗi lượt poll | Tổng throughput còn phụ thuộc scheduler |
| `.handle(writer)` | Gửi message tới output handler | Không có ACK từ hệ thống ngoài |
| `new ByteStreamWritingMessageHandler(output, outputBufferBytes)` | Cấu hình ghi byte ra stream | Flush/durability phải kiểm chứng riêng |

### 7.5. Ownership và output correctness

`@Bean(destroyMethod="close")` chỉ định Spring hủy resource bean khi context đóng. Cần kiểm tra rõ contract cleanup của source/handler trong phiên bản runtime để **không có hai owner cùng đóng một SDK stream**. Đối với file Java trong ví dụ, việc đóng buffer/resource đúng thứ tự vẫn cần phối hợp với **lượt poll đang chạy**; đừng tự gọi `context.close()` ngay khi một chunk được đọc.

Khi so sánh file đầu vào/đầu ra, hãy đợi flow xử lý xong và đảm bảo output được flush/close. **Đừng lấy thời điểm file tồn tại trên disk làm bằng chứng copy đã hoàn tất.** Ví dụ không tự dừng application ở EOF; một batch job production phải có completion coordinator và chính sách drain.

### 7.6. Thử nhiều cấu hình

| Lần | `inputBufferBytes` | `bytesPerMessage` | `outputBufferBytes` | Mục đích |
| --- | ---: | ---: | ---: | --- |
| Baseline | 8192 | 1024 | 8192 | Đo theo mặc định chunk của SI |
| B | 8192 | 4096 | 8192 | Giảm số Spring messages |
| C | 8192 | 16384 | 8192 | Tăng chunk, giữ buffer I/O |
| D | 16384 | 16384 | 8192 | Thử input buffer riêng |
| E | 16384 | 16384 | 32768 | Thử output buffer riêng |
| F | 65536 | 65536 | 65536 | Kiểm tra có giảm throughput/latency không |

**Đây là ma trận thí nghiệm, không phải bảng benchmark đã chạy.** Cần giữ nguyên file đầu vào, máy/CPU, storage, JDK, số worker, GC, poller delay và điều kiện cache khi so sánh. Lần F không mặc định nhanh hơn lần C.

## 8. XML: cấu hình buffer của source, handler và poller

Tương đương về cấu trúc với Java DSL, XML cần một `InputStream` bean và một `OutputStream` bean do ứng dụng cấp (chẳng hạn Java `@Bean` với cleanup):

```xml
<beans:beans
    xmlns:beans="http://www.springframework.org/schema/beans"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:int="http://www.springframework.org/schema/integration"
    xsi:schemaLocation="
        http://www.springframework.org/schema/beans
        https://www.springframework.org/schema/beans/spring-beans.xsd
        http://www.springframework.org/schema/integration
        https://www.springframework.org/schema/integration/spring-integration.xsd">

    <!-- copyInput / copyOutput: bean tai nguyen do app quan ly. -->
    <beans:bean id="binarySource"
                class="org.springframework.integration.stream.ByteStreamReadingMessageSource">
        <beans:constructor-arg ref="copyInput"/>
        <beans:constructor-arg value="8192"/>
        <beans:property name="bytesPerMessage" value="16384"/>
        <beans:property name="shouldTruncate" value="true"/>
    </beans:bean>

    <int:channel id="binaryCopyChannel"/>

    <int:inbound-channel-adapter
            id="binarySourceAdapter"
            ref="binarySource"
            channel="binaryCopyChannel">
        <int:poller fixed-delay="25"
                    max-messages-per-poll="1"/>
    </int:inbound-channel-adapter>

    <beans:bean id="binarySink"
                class="org.springframework.integration.stream.ByteStreamWritingMessageHandler">
        <beans:constructor-arg ref="copyOutput"/>
        <beans:constructor-arg value="8192"/>
    </beans:bean>

    <int:outbound-channel-adapter
            id="binarySinkAdapter"
            channel="binaryCopyChannel"
            ref="binarySink"/>
</beans:beans>
```

Đây là **một mảnh XML tích hợp**, vì `copyInput` và `copyOutput` phải được cấu hình ở nơi khác. Đừng bật đồng thời XML này và Java DSL ở mục 7 cùng đọc một `InputStream`: chúng có thể tranh vị trí đọc, làm sai kết quả.

### Khi nào XML namespace stream hữu ích?

Spring Integration còn có namespace `int-stream` để cấu hình stdin/stdout/stderr. Nó thích hợp cho CLI text/binary pipeline đơn giản. Tuy nhiên tham số tối ưu trong namespace phải được tra theo **XSD của phiên bản đang dùng**, không tự giả định mọi tên attribute của Java setter cũng được chấp nhận trong XML. Với use case này, bean source/handler và generic channel-adapter cho phép thấy rõ từng buffer.

## 9. Poller và MessageChannel cũng ảnh hưởng hiệu năng

### 9.1. Poller điều khiển nhịp gọi receive

Với `SourcePollingChannelAdapter`:

```java
Pollers.fixedDelay(Duration.ofMillis(50))
       .maxMessagesPerPoll(1)
```

Nếu mỗi lượt poll sinh một message nhỏ, `fixedDelay` 50 ms có thể tạo ra **trần lý thuyết** khoảng 20 message/giây trên một poller trong điều kiện không chồng lấp. Khi chunk là 1024 bytes, throughput tối đa theo trần đơn giản chỉ khoảng 20 KiB/giây! Con số minh họa lý do **đừng benchmark buffer chỉ với poller đang giới hạn throughput**; thời gian xử lý và scheduler còn làm thấp hơn.

Nếu muốn đo ảnh hưởng chunk thực, phải biết liệu poller, nguồn disk hay sink đang là bottleneck. Điều chỉnh `maxMessagesPerPoll` và schedule có thể giúp throughput nhưng cũng tăng thời gian một lượt poll giữ thread.

### 9.2. DirectChannel vs bounded QueueChannel

| Channel | Đặc điểm hiệu năng | Rủi ro |
| --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ, ít queue overhead | Producer/poller bị giữ khi handler chậm |
| `QueueChannel(capacity)` | Cho phép buffer message hữu hạn giữa hai poller | Gây memory backlog, timeout và chưa durable |
| `ExecutorChannel` | Có thể tách caller/worker | Task queue phải bounded, ordering/rejection cần test |
| `RendezvousChannel` | Zero-capacity handoff | Block sender khi chưa có receiver |

`QueueChannel(32)` giới hạn **32 messages** chứ không phải 32 KiB. Với `bytesPerMessage=64 KiB`, riêng payload queue khi đầy đã gần **2 MiB**, chưa tính object/header/in-flight. Nếu dùng unbounded executor hoặc parser, memory còn có thể tăng nhiều hơn.

### 9.3. Phân biệt batching với tăng buffer

Tăng `bytesPerMessage` làm giảm số Spring messages trong cùng lượng bytes, nhưng không tự tạo **database batch** gồm nhiều record. Một chunk 64 KiB có thể chứa nhiều bản ghi, một phần bản ghi hoặc dữ liệu nén. Nếu muốn JDBC batch, hãy tạo **records đã parse** rồi dùng batch theo transaction policy; không lấy byte chunk làm số lượng business events.

### 9.4. Backpressure và lỗi sau khi đọc

`InputStream.read()` có thể đã lấy bytes khỏi nguồn trước khi `QueueChannel.send()` bị block/timeout. **Retry bằng cách gọi source.receive() lần nữa không lấy lại bytes cũ.** Với nguồn quan trọng, cần durable staging/checkpoint theo record đã commit và idempotent consumer, không chỉ tăng queue capacity để né lỗi.

## 10. Ước lượng memory và allocation

Giả sử:

- `C`: kích thước payload `byte[]` trung bình hoặc giới hạn (byte/message).
- `Q`: tối đa messages chờ trong queue.
- `N`: tối đa messages đang xử lý đồng thời.
- `H`: overhead trung bình cho một Spring message và headers.
- `B`: tổng I/O buffers đang cấp phát.
- `P`: memory cho parser/reassembler/decoded text và objects.

Ước lượng phần memory liên quan flow:

\[
M_{\mathrm{peak}}\;\approx\; (Q+N)(C+H) + B + P
\]

Đây là một mô hình sizing **không phải memory profiler chính xác**. `C` nếu là average có thể đánh giá thấp peak; đầu vào có record size phân phối lệch, object overhead/GC cũng thay đổi theo JVM.

### Một bảng thử tính

| `C` | `Q` | Payload chỉ riêng queue khi đầy |
| ---: | ---: | ---: |
| 1 KiB | 64 | 64 KiB |
| 4 KiB | 64 | 256 KiB |
| 16 KiB | 64 | 1 MiB |
| 64 KiB | 64 | 4 MiB |
| 256 KiB | 64 | 16 MiB |

Tăng chunk 64 lần mà không đổi queue capacity có thể tăng **payload memory capacity** 64 lần. Nếu reassembler giữ một record 100 MiB và parser tạo JSON tree lớn, queue rất nhỏ vẫn có thể OOM.

### 10.1. Allocation và GC

Với file hữu hạn khoảng `D` bytes và trung bình chunk size `C`:

\[
N_{\mathrm{message}}\approx D/C
\]

Message count càng nhiều thì các allocation wrapper, `MessageHeaders` và dispatch cũng nhiều hơn. Nhưng chunk quá lớn có thể gây allocation spikes, áp lực humongous objects trên một số GC/configuration, tăng thời gian copy và tail latency. Không có một ngưỡng “humongous” cố định cho mọi JVM/GC; phải quan sát GC logs/JFR.

### 10.2. Off-heap và OS buffer

Heap metrics không phản ánh hoàn toàn kernel page cache, socket send/receive buffers, direct `ByteBuffer` hay native allocations của SDK. Nếu tiến trình có RSS cao nhưng heap ổn định, kiểm tra cả off-heap/native memory và I/O buffering bên ngoài JVM, không chỉ chỉnh heap.

### 10.3. Không biến một chunk thành nhiều bản sao vô tình

Một flow có thể đồng thời giữ:

```text
raw byte[]
   -> copied byte[] for frame
      -> new String (UTF-8 decode)
         -> business DTO / JSON tree
            -> new encoded byte[]
               -> destination buffer
```

Tránh log raw payload hoặc convert qua lại byte/String không cần thiết. Nếu business cần xử lý binary, giữ `Message<byte[]>`; nếu business cần text, decode đúng một lần **sau khi ghép record**; nếu cần lưu vào database, batch trên bản ghi đã validate.

## 11. Kích thước buffer, throughput và latency: đường cong không đơn điệu

Một cách nhìn phổ biến là “buffer càng lớn càng nhanh”. Thực tế, độ lợi thường tăng mạnh từ cấu hình cực nhỏ sang vừa phải, rồi **bão hòa hoặc suy giảm** khi tăng tiếp.

```text
Throughput
 ^
 |                 ________   vùng bão hòa (minh họa)
 |              __/        \\__
 |          ___/
 |      ___/
 |_____/________________________> bytesPerMessage / buffer size
   rất nhỏ   vừa phải        rất lớn
```

Sơ đồ **mang tính khái niệm**, không phải dữ liệu benchmark. Đường cong thực còn phụ thuộc filesystem, SSD/HDD, socket, SDK, GC, poller, CPU, compression và serialization.

### 11.1. Thế nào là buffer quá nhỏ?

- Message count tăng, fixed overhead của Spring Messaging lớn so với payload.
- Các lời gọi read/write nhỏ có thể tăng overhead kernel/SDK nếu không có lớp đệm khác.
- Poller hoặc channel dispatch tốn tỷ lệ CPU lớn.
- Metrics/tracing/logging trên mỗi message có thể trở thành bottleneck.

**Ngoại lệ:** nếu nguồn là một pipe có record rất nhỏ và SLO latency thấp, message nhỏ có thể chính là lựa chọn đúng; đừng ép tích lũy quá nhiều để tối đa hóa throughput.

### 11.2. Thế nào là buffer quá lớn?

- Payload byte arrays lớn hơn; memory/backlog tăng nếu queue tính theo message.
- Dữ liệu chưa đầy buffer có thể chờ, tùy implementation flush/read.
- Mỗi message tạo công việc lớn, giảm fairness với flow khác trên cùng thread/scheduler.
- Lỗi sau khi đã đọc một chunk lớn có thể khó replay nếu nguồn không seek.
- Copy/serialization lớn gây GC pressure hoặc tail latency spikes.
- Một oversized message có thể vượt giới hạn DB/HTTP/broker downstream dù raw stream cho phép.

### 11.3. Throughput không phải latency

| Chỉ số | Câu hỏi |
| --- | --- |
| **Throughput** | Mỗi giây xử lý xong bao nhiêu bytes/records? |
| **Latency P50/P95/P99** | Một record mất bao lâu từ source tới commit/ACK? |
| **Time to first record** | Sau khi dữ liệu đầu tiên có mặt, bao lâu consumer thấy record? |
| **Queue residence time** | Record chờ trong queue bao lâu? |
| **GC pause / CPU** | JVM có đủ tài nguyên để tiếp tục không? |
| **Memory peak/RSS** | Buffer có làm hết ngân sách memory không? |
| **Error rate** | Timeout, reject, partial write, retry có tăng không? |

Một cấu hình 64 KiB có thể tăng throughput batch nhưng tăng latency của event nhỏ. Tuning đúng phải theo **SLO của người dùng**: batch file hoàn tất dưới 2 phút khác với dòng telemetry cần xuất trong 100 ms.

### 11.4. Số lời gọi I/O không luôn là số syscall

Nếu gọi `BufferedInputStream.read(byte[])` 1.000 lần, không thể kết luận JVM đã gọi kernel `read` 1.000 lần: wrapper có thể lấy nhiều bytes từ buffer nội bộ. Ngược lại, một lời gọi Java xuống network SDK có thể gây nhiều thao tác bên trong. Đo Java method-call counts, syscall counts và latency của socket/file **bằng công cụ phù hợp**, không suy từ code thuần túy.

## 12. Thiết kế benchmark đúng

Một benchmark hiệu năng hữu ích phải kiểm soát **correctness** trước:

1. Giữ file fixture binary **bất biến**, biết trước `fileSize` và checksum.
2. Đảm bảo output không ghi chồng input; test lại bytes sau run.
3. Cố định số worker/queue policy, JDK/GC, storage, stream ownership.
4. Ghi cả **throughput, latency P95/P99, allocations, GC, CPU, memory peak** và số messages.
5. Có warm-up, nhiều lần lặp và phân biệt cold-cache với warm-cache.
6. Chỉ đổi **một tham số** trong mỗi nhóm thí nghiệm.
7. Đánh giá cả **file lớn**, **message nhỏ**, **record dài**, **consumer chậm**, **file cuối ngắn**.
8. Tránh logging từng chunk trong vòng benchmark: logger có thể là bottleneck.

### 12.1. Tách ba loại benchmark

| Loại test | Đo gì? | Không chứng minh |
| --- | --- | --- |
| **JDK-only copy** | Chi phí `InputStream`/`OutputStream` và buffering Java | Chi phí Spring Messaging |
| **Spring flow in-memory** | Source/message/channel/handler overhead | Disk/network performance |
| **End-to-end production-like** | Storage, serialization, queue, consumer, network, ACK | Tự cô lập nguyên nhân nghẽn nếu không có telemetry |

Nếu test `ByteArrayInputStream` và `ByteArrayOutputStream` rồi kết luận “buffer 64 KiB tối ưu cho SFTP” là sai: SFTP có encryption, session, network latency, server disk và connection pool riêng.

### 12.2. JDK baseline file copy để so sánh

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

public final class BufferedFileCopy {

    private BufferedFileCopy() {
    }

    public static long copy(
            Path source, Path destination,
            int ioBufferSize, int copyChunkSize)
            throws java.io.IOException {

        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        if (source.toAbsolutePath().normalize().equals(
                destination.toAbsolutePath().normalize())) {
            throw new IllegalArgumentException(
                    "Source and destination must differ");
        }
        if (ioBufferSize < 1 || copyChunkSize < 1) {
            throw new IllegalArgumentException(
                    "Buffer sizes must be positive");
        }

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(source), ioBufferSize);
             OutputStream out = new BufferedOutputStream(
                    Files.newOutputStream(
                        destination,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE),
                    ioBufferSize)) {

            byte[] buffer = new byte[copyChunkSize];
            long totalBytes = 0;
            int n;

            while ((n = in.read(buffer)) != -1) {
                if (n == 0) {
                    // Khong phat message rong; cho source co tien trien.
                    // Với một InputStream có hành vi 0-byte kéo dài, cần
                    // deadline/policy riêng để tránh busy loop.
                    continue;
                }
                out.write(buffer, 0, n);
                totalBytes += n;
            }
            out.flush();
            return totalBytes;
        }
    }
}
```

**Đây là baseline Java I/O**, không dùng Spring Integration. Nó tách tác động `ioBufferSize` và `copyChunkSize` để so với flow Spring. Dùng file độc lập và cleanup output sau khi test; không thử trên dữ liệu production có thể bị ghi đè. `Files.copy(...)` cũng là một baseline có ích, nhưng implementation có thể tối ưu khác nên phải báo rõ.

### 12.3. Đo thời gian cẩn trọng

Ví dụ một đo lường cục bộ có thể làm:

```java
long startNanos = System.nanoTime();
long copiedBytes = BufferedFileCopy.copy(
        sourcePath, outputPath, 8192, 16384);
long elapsedNanos = System.nanoTime() - startNanos;

double seconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = copiedBytes / (1024.0 * 1024.0) / seconds;
```

Đây là **snippet minh họa** với hai biến `sourcePath`/`outputPath` kiểu `Path` đã được cung cấp. Một lượt chạy không phải benchmark đáng tin cậy. Nên warm-up, lặp nhiều lần, lấy phân phối số đo, khóa chặt điều kiện cache, đo correctness và so sánh với baseline. JMH thích hợp với **microbenchmark Java code**, còn end-to-end Spring Integration cần test với workload gần thực tế và telemetry.

### 12.4. Tránh các thiên lệch benchmark

- **Page cache**: chạy lần hai có thể nhanh vì file đã ở OS cache.
- **Disk contention**: ứng dụng khác đọc/ghi cùng storage gây kết quả khác.
- **JIT warm-up**: vòng đầu có thể chậm do class loading/JIT.
- **GC**: allocation spikes và pause làm thay đổi tail latency.
- **Network variance**: SFTP/HTTP/TCP không có RTT cố định.
- **Logging**: một debug log cho mỗi message có thể che mất lợi ích buffer.
- **Poller ceiling**: `fixedDelay` cao khiến bạn benchmark scheduler, không benchmark disk.
- **Validation work**: parse JSON/CSV có thể đắt hơn copy bytes.
- **File size**: file quá nhỏ không đại diện workload streaming dài.

### 12.5. Thang cấu hình để thử

Chọn `bytesPerMessage` là `1 KiB, 4 KiB, 16 KiB, 64 KiB, 256 KiB`. Với mỗi mức, thử một vài `input/output buffer size` độc lập và giữ nguyên các biến còn lại. Không cần thử mọi tổ hợp ngay nếu tải kiểm thử lớn; thu hẹp vùng tốt nhất dựa trên throughput + P99 latency + memory.

Nếu tăng từ 16 KiB lên 64 KiB chỉ cải thiện throughput 1% nhưng tăng queue memory 4 lần và P99 xấu đi, 64 KiB có thể không đáng chọn. Con số **1%** ở đây là tình huống giả định để minh họa quyết định trade-off, không phải một phát hiện benchmark.

## 13. JUnit 5: source trả đúng bytes, kể cả chunk cuối

Test với dữ liệu trong RAM để xác minh **correctness trước khi đo hiệu năng**.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.integration.stream.ByteStreamReadingMessageSource;
import org.springframework.messaging.Message;

class StreamChunkSizingTest {

    @Test
    void readsAllBytesWithoutPaddingInLastChunk() {
        byte[] original = new byte[8193];
        for (int i = 0; i < original.length; i++) {
            original[i] = (byte) (i % 251);
        }

        ByteStreamReadingMessageSource source =
                new ByteStreamReadingMessageSource(
                        new ByteArrayInputStream(original),
                        512);
        source.setBytesPerMessage(4096);
        source.setShouldTruncate(true);

        ByteArrayOutputStream captured =
                new ByteArrayOutputStream();
        int messages = 0;
        int lastPayloadLength = -1;

        Message<byte[]> message;
        while ((message = source.receive()) != null) {
            byte[] chunk = message.getPayload();
            assertTrue(chunk.length > 0);
            assertTrue(chunk.length <= 4096);
            lastPayloadLength = chunk.length;
            captured.write(chunk, 0, chunk.length);
            messages++;
        }

        assertArrayEquals(original, captured.toByteArray());
        assertEquals(3, messages);
        assertEquals(1, lastPayloadLength);
    }
}
```

Với nguồn `ByteArrayInputStream` hữu hạn, ví dụ kỳ vọng ba chunk **4096 + 4096 + 1**. Test **chưa được thực thi trong STEP 4**; nếu triển khai trên một `InputStream` khác có short reads, có thể có nhiều hơn ba chunk mà vẫn đúng tổng bytes và order. Vì vậy assertion số chunk chính xác chỉ phù hợp với fixture có hành vi đọc xác định.

### 13.1. Test nguồn trả short read

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class SmallReadInputStream extends InputStream {

    private final ByteArrayInputStream delegate;

    public SmallReadInputStream(byte[] data) {
        this.delegate = new ByteArrayInputStream(data);
    }

    @Override
    public int read() {
        return delegate.read();
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        if (len == 0) {
            return 0;
        }
        // Co tinh gioi han moi luot doc toi da 3 bytes.
        return delegate.read(b, off, Math.min(len, 3));
    }
}
```

Lớp này giả lập nguồn dữ liệu luôn trả từng đoạn nhỏ; trong test Java I/O trực tiếp, `read(buffer)` không được hiểu là đọc đúng `buffer.length`. Khi đưa vào Spring source có lớp buffering, hãy **xác minh behavior thực tế**, không gắn mọi lần read của wrapper vào một read bên dưới.

### 13.2. Test integrity quan trọng hơn số chunk

Với mọi nguồn, assertion nên ưu tiên:

1. `sum(payload.length) == original.length` (khi nguồn hữu hạn và không lỗi).
2. Bytes sau khi ghép lại **giống hệt thứ tự** bytes gốc.
3. Không có byte `0` đệm dư ở chunk cuối.
4. Không có message rỗng bất ngờ.
5. EOF/completion được xử lý theo contract nguồn.

Đo số chunks chỉ để phân tích performance; đừng cho nghiệp vụ yêu cầu chính xác một số chunks nếu giao thức không nói như vậy.

## 14. JUnit 5: đo tác động của BufferedInputStream trên lời gọi tầng dưới

`CountingInputStream` giúp đếm số lần **đọc xuống nguồn bên dưới**, không phải số syscall kernel:

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class CountingInputStream extends FilterInputStream {

    private long singleByteReads;
    private long blockReads;

    public CountingInputStream(InputStream delegate) {
        super(delegate);
    }

    @Override
    public int read() throws IOException {
        singleByteReads++;
        return in.read();
    }

    @Override
    public int read(byte[] b, int off, int len) throws IOException {
        blockReads++;
        return in.read(b, off, len);
    }

    public long getSingleByteReads() {
        return singleByteReads;
    }

    public long getBlockReads() {
        return blockReads;
    }
}
```

Nếu bọc một `CountingInputStream` bằng `BufferedInputStream`, rồi gọi `read()` từng byte ở lớp ngoài, số lần gọi xuống delegate có thể giảm đáng kể so với đọc từng byte trực tiếp. Test có thể đo:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import org.junit.jupiter.api.Test;

class BufferReadCallTest {

    @Test
    void bufferReducesReadsToDelegateInThisFixture()
            throws Exception {

        byte[] fixture = new byte[8192];
        CountingInputStream counted =
                new CountingInputStream(
                    new ByteArrayInputStream(fixture));

        try (BufferedInputStream buffered =
                new BufferedInputStream(counted, 1024)) {

            int bytesRead = 0;
            while (buffered.read() != -1) {
                bytesRead++;
            }
            assertEquals(fixture.length, bytesRead);
        }

        assertTrue(counted.getBlockReads() > 0);
        assertTrue(counted.getBlockReads() < fixture.length);
    }
}
```

Đây là **test logic về lớp đệm**, chưa chạy trong STEP 4. Nó **không** chứng minh giảm syscall trên OS; delegate là `ByteArrayInputStream`. Khi đo file/network thật, phải dùng profiler hoặc các counters phù hợp.

## 15. Kiểm thử output buffering, flush và dữ liệu chưa hoàn tất

Đầu ra có thể có buffer ở **handler**, **Java wrapper**, **OS** và **SDK**. Để hiểu flush, nên bắt đầu bằng test JDK trong RAM:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class OutputBufferTest {

    @Test
    void flushMakesBufferedBytesVisibleToUnderlyingSink()
            throws Exception {

        ByteArrayOutputStream sink =
                new ByteArrayOutputStream();

        try (BufferedOutputStream buffered =
                new BufferedOutputStream(sink, 8192)) {

            buffered.write(
                    "Đã thanh toán".getBytes(
                        StandardCharsets.UTF_8));

            // BufferedOutputStream dang giu bytes nho hon
            // kich thuoc buffer theo behavior cua JDK.
            assertEquals(0, sink.size());

            buffered.flush();
            assertArrayEquals(
                    "Đã thanh toán".getBytes(
                            StandardCharsets.UTF_8),
                    sink.toByteArray());
        }
    }
}
```

Test này **minh họa một lớp `BufferedOutputStream` JDK cụ thể**, không thay thế việc kiểm tra `ByteStreamWritingMessageHandler` của phiên bản Spring Integration runtime. Có handler/wrapper chủ động flush theo message, có sink khác flush/commit theo session. **Không giả định tăng buffer thì Java bytes luôn được giữ lại đến close**; phải kiểm tra bằng test hoặc source implementation của đối tượng đang sử dụng.

### Khi nào phải flush?

| Use case | Chính sách phù hợp |
| --- | --- |
| Xuất file batch tạm | Flush/close khi ghi xong rồi publish file atomically theo contract |
| Truyền text console line-oriented | Có delimiter/newline; kiểm tra reader thấy dữ liệu đúng lúc |
| Network stream request–reply | Flush theo frame/protocol; timeout và ACK |
| SDK object upload | Theo API flush/commit/complete/abort của SDK |
| Ghi dữ liệu cần durability | Dùng storage/transaction và fsync/ACK theo yêu cầu |

**Không flush sau mỗi byte** vì có thể phá lợi ích batching; nhưng **không hoãn flush quá lâu** nếu giao thức cần reader phản hồi theo từng frame (nếu không dễ deadlock: writer chờ ACK còn reader chờ bytes chưa flush).

## 16. Case study: tối ưu luồng NDJSON tiếng Việt

Giả sử nguồn là một file NDJSON, mỗi dòng là một JSON object UTF-8, chứa tên hoặc ghi chú tiếng Việt. Adapter byte đọc theo chunks 16 KiB và downstream parse JSON.

### 16.1. Cấu hình ban đầu sai

```text
ByteStreamReadingMessageSource
    bytesPerMessage = 16384
          |
          v
new String(chunk, UTF_8)
          |
          v
parseOneJsonObject(text)
```

Nó sai vì:

1. Chunk 16 KiB có thể chứa nhiều dòng JSON.
2. Một JSON object có thể nằm ở hai hoặc nhiều chunks.
3. Một ký tự UTF-8 nhiều byte có thể bị chia giữa hai chunks.
4. `bytesPerMessage` không phải `maxLineLength` và không có EOF/commit semantics.

### 16.2. Pipeline đúng

```text
InputStream
    |
ByteStreamReadingMessageSource
    |
Message<byte[]> chunks
    |
Bounded LF / frame assembler
    |  maxLineBytes=1 MiB, pending-timeout=policy
    v
Complete UTF-8 record bytes
    |
CharsetDecoder(REPORT)
    |
Valid String per line
    |
JSON parser + schema validation
    |
Domain event with stable eventId
    |
Durable inbox / idempotent consumer
```

Khi không cần xử lý binary và hợp đồng thật sự là **mỗi dòng text**, bạn có thể cân nhắc `CharacterStreamReadingMessageSource` với `Reader` UTF-8. Nhưng `BufferedReader.readLine()` thông thường không tự giới hạn độ dài dòng, nên với dữ liệu không tin cậy vẫn cần bounded parser/size limit.

### 16.3. Nên tune cái nào?

- Nếu CPU dành nhiều cho Spring message wrappers, thử tăng `bytesPerMessage` vừa phải.
- Nếu parser phải ghép rất nhiều chunks cho mỗi record, chọn framing tốt và max record, không chỉ tăng buffer.
- Nếu downstream DB chậm, tăng input buffer không giải quyết bottleneck; cần batching/transaction/consumer throughput ở tầng DB.
- Nếu hàng đợi đầy, giảm intake hoặc tăng năng lực consumer trong budget; đừng đổi queue capacity sang vô hạn.
- Nếu P99 latency tăng vì message lớn, thử chunk nhỏ hơn hoặc xử lý records độc lập có thứ tự.
- Nếu memory peak tăng vì parser tích lũy line quá dài, giới hạn `maxLineBytes` trước khi decode/parse.

## 17. Case study: đầu ra TCP/SDK chậm

Một SDK cấp `OutputStream` đến thiết bị. Ứng dụng ghi các frame binary nhỏ liên tục. Thử `ByteStreamWritingMessageHandler(destination, 8192)` rồi tăng lên 65536:

| Quan sát | Không nên kết luận vội | Kiểm tra thêm |
| --- | --- | --- |
| Throughput producer tăng | Receiver xử lý nhanh hơn | Receiver ACK và backlog ở network |
| `write()` trả về sớm | Frame đã ra khỏi máy | Wrapper/OS send buffers, flush |
| Bytes visible muộn | Chỉ cần tăng buffer | Protocol cần flush per frame? |
| TCP timeout tăng | Buffer lớn luôn là lỗi | Server rate limit, congestion, session |
| GC giảm | Không còn memory bottleneck | Queue/in-flight/parser và RSS |
| Lỗi sau nhiều frames | Dữ liệu gửi có thể tự retry an toàn | Partial write, sequence, idempotency |

**Lưu ý:** `OutputStream` không phải một TCP transport adapter đầy đủ. Khi cần connection pooling, framing, reply correlation, reconnect và timeout, chọn **TCP outbound adapter/gateway** với `TcpConnectionFactory` và serializer/deserializer phù hợp. Tương tự, chọn SFTP/HTTP/JMS/AMQP/Kafka adapters khi yêu cầu thuộc chính protocol đó.

## 18. Error handling và sự thật về partial read/write

### 18.1. Partial read không phải lỗi

Một lời gọi `InputStream.read(buffer)` trả 200 bytes trong khi buffer dài 8192 **có thể hoàn toàn bình thường**. Đừng cứ retry hoặc bỏ bytes còn thiếu. Ghi nhận `n` và xử lý chính xác `n` bytes; với message source, dùng `shouldTruncate(true)` và framing đúng.

### 18.2. Partial write có thể là lỗi nghiêm trọng

`OutputStream.write(bytes)` không có transaction/rollback giữa nhiều Spring messages. Nếu ghi nửa frame rồi `IOException`, retry cả frame có thể tạo dữ liệu lặp hoặc phá giao thức; phải có quy tắc reconnect/reframe, stable sequence/event ID, ACK và idempotency.

```text
frame = [length][eventId][payload]
             |
       write first half
             |
         I/O failure
             |
       retry whole frame?
             |
  receiver may see corrupt/duplicate stream
```

Vì vậy, **tăng buffer để tối ưu throughput không được thay thế chiến lược recovery**.

### 18.3. Queue đầy sau khi đọc

Nếu dùng `QueueChannel` sau source:

```text
source.receive() reads chunk
       |
channel.send(chunk, timeout) fails
       |
chunk is already read from InputStream
```

Không gọi `source.receive()` tiếp rồi xem đó là retry chunk cũ. Với source có thể replay (file immutable), cần checkpoint **theo record đã commit**, không chỉ theo bytes đã đọc vào buffer. Với socket/stdin không replay, cần durable staging nếu business không cho phép mất event.

### 18.4. Exception không phải lúc nào cũng vào errorChannel

Ở `DirectChannel`, exception của downstream handler có thể đi ngược lên caller/poller. Với polling endpoint hoặc flow async, error routing phụ thuộc configuration và error handler. Không giả định mọi lỗi `IOException` lúc close của Spring bean đều trở thành `ErrorMessage` trên global `errorChannel`.

Khi benchmark, ghi **lỗi và số message failed** thay vì bỏ qua; một phiên bản “nhanh hơn” vì drop payload hoặc giấu exception là kết quả không hợp lệ.

## 19. EOF, lifecycle và shutdown khi có buffer

### 19.1. Stop poller không tự flush output

`SmartLifecycle.stop()` dừng endpoint theo contract, không phải bằng chứng dữ liệu đã hết ở mọi buffer. Với flow có queue:

```text
Stop inbound poller
      |
      v
Wait until queued + in-flight business work drain
      |
      v
Flush output buffered resources
      |
      v
Close owned output / input resources
      |
      v
Mark completed only after required ACK/commit
```

`QueueChannel.getQueueSize()==0` vẫn có thể trùng lúc **consumer đã lấy message nhưng chưa commit**. Cần theo dõi `inFlight`, transaction và pending outbox.

### 19.2. Byte source và character source có EOF khác nhau

- `ByteStreamReadingMessageSource` nhận `InputStream` và trả chunk bytes; không mặc định dùng cùng `StreamClosedEvent` như character source bật detect EOF.
- `CharacterStreamReadingMessageSource` có `blockToDetectEOF=true` và có thể phát `StreamClosedEvent`; event có thể lặp nếu poller còn hoạt động, nên dedup và stop có kiểm soát.
- `Reader.ready()==false` không chứng minh EOF.

Không đóng stream trong một listener được gọi khi downstream vẫn còn xử lý. Với file copy demo, không tự đọc lại output khi application còn ghi, vì buffer chưa được flush/close.

### 19.3. Không đóng System.in/System.out từ một module

Standard streams thường thuộc JVM hoặc runtime logging, được component khác sử dụng. Nếu tạo `BufferedOutputStream(System.out)` rồi close từ một handler, bạn có thể làm logging hoặc CLI khác mất stdout. Chỉ đóng stream mà **resource owner có quyền đóng**; có chính sách riêng cho SDK/session streams.

### 19.4. Mất điện và SIGKILL

Cleanup hooks của Spring có thể không chạy nếu process chết bất ngờ. Nếu cần durability, phải lưu event/offset vào store bền và có cơ chế phục hồi độc lập với `flush()`/`close()`. Với File outbound production, cần temporary file suffix, atomic publication, fsync theo đặc tính filesystem hoặc adapter/gateway hỗ trợ chính sách file phù hợp.

## 20. Observability khi tuning buffer

### 20.1. Bộ chỉ số đề xuất

| Metric gợi ý | Đơn vị | Giải thích |
| --- | --- | --- |
| `stream_bytes_read_total` | bytes | Số bytes source đã đọc |
| `stream_chunks_emitted_total` | messages | Số `Message<byte[]>` sinh ra |
| `stream_chunk_payload_bytes` | histogram | Phân phối kích thước payload thực |
| `stream_bytes_written_total` | bytes | Bytes đã đưa cho writer; chưa phải ACK |
| `stream_messages_per_second` | messages/s | Overhead dispatch/poller |
| `stream_throughput_mib_per_second` | MiB/s | Throughput payload |
| `stream_end_to_end_latency_seconds` | seconds | Từ nhận record tới commit/ACK |
| `stream_queue_depth` | messages | Backlog đang chờ, không tính in-flight |
| `stream_inflight_count` | messages | Consumer đang xử lý |
| `stream_buffer_allocated_bytes` | bytes | Các buffer do ứng dụng theo dõi |
| `stream_gc_pause_seconds` | seconds | GC impact |
| `stream_copy_errors_total` | events | Lỗi source/decoder/sink |
| `stream_send_block_seconds` | seconds | Thời gian chờ channel khi queue đầy |
| `stream_partial_frames_total` | frames | Bản ghi chưa hoàn chỉnh theo protocol |

Đây là **metrics đề xuất**, không phải danh sách tất cả meters built-in của Spring Integration. Spring Integration và Micrometer có hỗ trợ management/observation; xác định metrics đã có trước khi tự instrument. Không dùng raw payload, event ID, tên khách hàng hoặc full file path làm metric label có cardinality cao.

### 20.2. Đánh giá theo SLO

Không chọn cấu hình thắng chỉ theo throughput. Một bảng quyết định nên có:

| Test config | Throughput | P99 latency | Max heap/RSS | Error/timeout | Pass SLO? |
| --- | --- | --- | --- | --- | --- |
| 1 KiB | *Đo* | *Đo* | *Đo* | *Đo* | *Xác định* |
| 4 KiB | *Đo* | *Đo* | *Đo* | *Đo* | *Xác định* |
| 16 KiB | *Đo* | *Đo* | *Đo* | *Đo* | *Xác định* |
| 64 KiB | *Đo* | *Đo* | *Đo* | *Đo* | *Xác định* |
| 256 KiB | *Đo* | *Đo* | *Đo* | *Đo* | *Xác định* |

**Không điền số giả** vào bảng benchmark nếu chưa chạy; giá trị tốt nhất phụ thuộc workload. Chỉ kết luận sau nhiều lần đo có độ tin cậy và so sánh dựa trên cùng điều kiện.

## 21. Troubleshooting: buffer size và hiệu năng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Tăng buffer nhưng throughput không thay đổi | Poller `fixedDelay` hoặc downstream DB đang là bottleneck | Đo poll rate, business commits/sec |
| Tăng `bytesPerMessage` làm heap tăng mạnh | Queue tính theo số messages, mỗi payload lớn hơn | Đo queue depth × payload size, memory peak |
| Chunk cuối có nhiều byte 0 dư | Payload không được truncate theo bytes thực đọc | Dùng `setShouldTruncate(true)` |
| Vài message có length nhỏ hơn `bytesPerMessage` | `InputStream.read(...)` trả short read | Xử lý đúng `payload.length`, không coi là EOF |
| JSON parse lỗi ngẫu nhiên | Đưa byte chunk thẳng vào JSON parser | Reassemble/frame trước khi decode/parse |
| Tiếng Việt biến thành `�` | UTF-8 bị cắt giữa hai chunks hoặc charset sai | Strict decoder, giữ state giữa chunks |
| File output thiếu bytes lúc đang chạy | Còn trong output buffer hoặc flow chưa xong | Xác minh flush/close/lifecycle |
| `write()` nhanh nhưng receiver nhận trễ | OS/SDK buffer, network congestion, thiếu flush frame | Đo time-to-visible và ACK |
| Gọi flush sau mỗi byte thấy CPU cao | Mất lợi ích batching | Flush theo frame/protocol/SLO |
| `readLine()` dùng buffer 8 KiB nhưng OOM | Một dòng có thể dài hơn buffer | Bounded line length và input quota |
| Queue chỉ 16 messages nhưng vẫn OOM | Decoder/JSON parser/executor unbounded | Bổ sung max frame, max task queue |
| `DirectChannel` chậm khi sink chậm | Dispatch đồng bộ | Cân nhắc bounded queue/worker, giữ ordering |
| `ExecutorChannel` tăng throughput nhưng đảo thứ tự | Worker parallel không giữ total order | Partition/sequence/single-owner |
| `QueueChannel` bị đầy kéo dài | Consumer chạy chậm/không chạy | Kiểm tra consumer poller, latency, exceptions |
| `send(timeout)` thất bại làm thiếu bytes | Source đã đọc chunk trước lúc enqueue | Durable staging/checkpoint, dừng intake |
| Test RAM nhanh nhưng production chậm | Disk/SSD/network/SDK/crypto khác với RAM | Benchmark production-like |
| Lần chạy thứ hai nhanh bất thường | OS page cache hoặc JIT warm-up | Báo rõ warm/cold cache, lặp nhiều lần |
| Tăng chunk tạo nhiều GC spikes | Large arrays, copies, JSON trees | JFR/GC logs, giảm allocations |
| `String.length()` làm length-prefix bị sai | Đếm UTF-16 units thay vì bytes | Encode UTF-8 trước rồi lấy `byte[].length` |
| Writer báo lỗi sau flush | Disk full, broken pipe, session đóng | Phân loại lỗi và trạng thái uncertain |
| Message rỗng hoặc ngắn hơn kỳ vọng | EOF, short read hoặc bug parser | Đo bytes thực và fixture validation |
| File bị xóa nội dung khi restart | Output mở bằng `TRUNCATE_EXISTING` | Thay bằng policy publication/recovery đúng |
| EOF nhưng ứng dụng không thoát | Byte source/poller không có completion coordinator | Stop intake, drain, flush/close |
| Buffer tối ưu trên Linux nhưng không tốt trên Windows | File system/driver/cache/charset khác | Benchmark trên môi trường triển khai |
| JVM RSS cao nhưng heap bình thường | Direct buffers, OS page cache/native SDK | Native memory/OS metrics |

### Trình tự chẩn đoán ngắn gọn

1. **Xác định tính đúng dữ liệu:** input bytes và output bytes có khớp không?
2. **Đọc mapping các buffers:** những lớp Java/Spring/SDK nào đang đệm?
3. **Đo bottleneck:** CPU, disk, network, queue, GC hay DB handler?
4. **Kiểm tra poller:** `fixedDelay`/`maxMessagesPerPoll` có giới hạn message rate không?
5. **So sánh C_msg với B_in/B_out:** có đang thay đổi sai knob?
6. **Kiểm tra downstream frame:** một chunk có chứa nhiều hoặc nửa record không?
7. **Kiểm tra memory peak:** queue, in-flight, parser, executor và native buffers.
8. **Kiểm tra latency/flush:** receiver đã thấy bytes khi nào?
9. **Kiểm tra error/recovery:** dữ liệu đã read nhưng chưa handoff được xử lý ra sao?
10. **Benchmark có kiểm soát:** lặp nhiều lần, đo SLO, không giả định max size luôn tối ưu.

## 22. Chọn adapter nào khi performance nằm ở tầng khác?

| Nhu cầu | Phương án phù hợp | Vì sao không chỉ tăng buffer Stream? |
| --- | --- | --- |
| Đọc một `InputStream` Java được SDK cung cấp | `ByteStreamReadingMessageSource` | Có thể kiểm soát chunk/poller; SDK vẫn có semantics riêng |
| Đọc file mới liên tục trong thư mục | **File inbound adapter** | Scanner/filter, file completion, locking |
| Ghi mỗi message ra file riêng | **File outbound adapter** | Filename, mode và temporary file suffix |
| SFTP/FTP/SMB remote file | Remote file adapters | Session, retry, remote transfer semantics |
| HTTP request–reply hoặc streaming | HTTP/WebFlux theo use case | Status, timeout, network/backpressure protocol |
| TCP framing/reconnect | TCP inbound/outbound adapter/gateway | Connection factory, serializer, deserializer |
| JMS/AMQP queue | JMS/AMQP adapters | Prefetch, ACK/redelivery, listener concurrency |
| Kafka topic | Kafka adapters | Consumer poll/offset, partition/producer batching |
| Database operations | JDBC adapter/gateway | Transaction, JDBC batch size, connection pool |
| Metrics/logs | Logging framework/appender | Rotation, async buffer và retention |

Ví dụ: nếu Kafka producer đang bị block do broker ACK, tăng buffer của một `ByteStreamWritingMessageHandler` (vốn không phải Kafka producer adapter) **không liên quan tới Kafka `batch.size` hoặc `linger.ms`**. Tương tự, SFTP throughput phụ thuộc session, encryption và remote server, không chỉ Java `BufferedInputStream`.

## 23. Checklist chọn buffer size trong thực tế

Trước khi đưa một cấu hình mới lên production, kiểm tra:

- [ ] Đã biết payload là **binary** hay **text UTF-8** và hợp đồng framing.
- [ ] Đã phân biệt `B_in`, `bytesPerMessage`, `Q`, `B_out` và max record size.
- [ ] Đã tính **memory peak** theo queue capacity, concurrency và parser.
- [ ] Đã đo **throughput** và **P95/P99 latency**, không chỉ số message/s.
- [ ] Đã benchmark cả **small records** và **large records**, không chỉ một fixture.
- [ ] Đã test **short read**, last chunk và EOF.
- [ ] Đã test **UTF-8 split across chunks** hoặc protocol framing tương đương.
- [ ] Đã test **slow consumer**, bounded queue saturation và send timeout.
- [ ] Đã test **flush** và time-to-visible ở sink thực.
- [ ] Đã test **partial write/IOException** và recovery policy.
- [ ] Đã xác định một **resource owner** quản lý close.
- [ ] Đã thiết kế shutdown **stop intake → drain → flush → close**.
- [ ] Đã có event ID/idempotency/checkpoint khi không được phép mất/trùng.
- [ ] Đã có metrics/alerts về queue depth, GC, latency và errors.
- [ ] Đã thử trên môi trường gần production và ghi lại baseline/rollback plan.

## 24. Bài tập thực hành

1. Giải thích sự khác nhau giữa `BufferedInputStream(8192)` và `bytesPerMessage(8192)`.
2. Giải thích `QueueChannel(64)` giới hạn message count, không trực tiếp giới hạn bytes.
3. Dùng `InputStream.read(byte[])` và chỉ xử lý `n` bytes thật, không dùng cả buffer nếu `n` nhỏ.
4. Tạo `ByteStreamReadingMessageSource` với constructor `bufferSize=4096` và `bytesPerMessage=16384`.
5. Bật `setShouldTruncate(true)`, kiểm tra chunk cuối của file không có bytes đệm dư.
6. Dùng fixture 8193 bytes, `bytesPerMessage=4096` và đối chiếu tổng bytes đã đọc.
7. Thay `ByteArrayInputStream` bằng `SmallReadInputStream`, giải thích vì sao số chunks có thể đổi.
8. Bọc một nguồn bằng `CountingInputStream` rồi `BufferedInputStream` để đếm số read xuống delegate.
9. Dùng `BufferedFileCopy.copy(...)` làm baseline JDK I/O.
10. So sánh một flow Spring Integration in-memory với JDK-only copy cùng payload.
11. Thử `bytesPerMessage` 1/4/16/64 KiB và ghi **throughput, CPU, GC, heap peak**.
12. Giữ `bytesPerMessage` cố định, thay riêng input buffer và output buffer.
13. Dùng Spring Boot flow ở mục 7, đổi `poll-delay-ms` rồi quan sát ceiling message rate.
14. Cấu hình XML source/handler tương đương Java DSL.
15. Thêm `QueueChannel(16)` giữa inbound và consumer, tính memory budget khi payload 64 KiB.
16. Tạo một consumer chậm 200 ms, xem DirectChannel và QueueChannel ảnh hưởng poller khác nhau thế nào.
17. Giải thích vì sao một chunk 64 KiB vẫn có thể chứa nửa JSON record.
18. Ghép bytes UTF-8 của một ký tự nhiều byte bị cắt giữa hai chunks.
19. Viết bounded assembler với `maxFrameBytes` và timeout thiếu delimiter.
20. Tạo input line rất dài, kiểm chứng `BufferedReader` 8 KiB không chặn OOM nếu không giới hạn line.
21. So sánh `new String(bytes, UTF_8)` với strict `CharsetDecoder` khi bytes malformed.
22. Kiểm thử output buffer: trước và sau `flush()` với `ByteArrayOutputStream`.
23. So sánh `flush()`, `FileChannel.force(...)`, atomic rename và ACK nghiệp vụ.
24. Giả lập write một phần rồi IOException, mô tả rủi ro retry và framing.
25. Đếm business records đã commit, không chỉ raw chunks đã đọc.
26. Giả lập queue đầy sau khi source đã đọc, đề xuất durable handoff để không mất dữ liệu.
27. Đo **P99 latency** trong lúc throughput tăng với buffer size lớn.
28. So sánh kết quả benchmark warm-cache và cold-cache.
29. Dùng JFR/GC logs tìm allocation hotspots khi tăng message size.
30. Tìm trường hợp tăng input buffer không giúp khi DB là bottleneck.
31. Thiết kế graceful shutdown còn backlog, verify queue empty + in-flight zero.
32. Chọn File/SFTP/TCP/JMS/AMQP/Kafka adapter khi cần session, ACK hoặc offset.

### Câu hỏi tự kiểm tra

**Q1. `bytesPerMessage` mặc định của `ByteStreamReadingMessageSource` là bao nhiêu?**  
1024 bytes theo Spring Integration Stream Reference 6.5.

**Q2. Constructor `ByteStreamReadingMessageSource(InputStream, int)` và `setBytesPerMessage(int)` có cùng ý nghĩa không?**  
Không. Constructor tham số thứ hai cấu hình buffer của source; setter đặt lượng bytes source cố đọc cho mỗi `Message<byte[]>`.

**Q3. `setShouldTruncate(true)` giúp gì?**  
Giúp payload phản ánh đúng số byte đã đọc trong trường hợp read trả ngắn hơn vùng buffer yêu cầu.

**Q4. Một chunk 16 KiB có phải một record JSON không?**  
Không. Record boundary do framing/schema quyết định, không do chunk size.

**Q5. `QueueChannel(32)` chứa tối đa 32 byte hay 32 messages?**  
32 Spring messages đang chờ, với payload kích thước khác nhau.

**Q6. Tại sao buffer nhỏ quá có thể chậm?**  
Tăng số read/write nhỏ, số Spring messages, dispatch/headers/allocation overhead.

**Q7. Tại sao buffer lớn quá có thể gây vấn đề?**  
Tăng peak memory, time-to-first-result, queue bytes, GC và ảnh hưởng latency/fairness.

**Q8. `BufferedReader` 8 KiB có cấm dòng dài 100 MiB không?**  
Không. Cần max line/record length độc lập.

**Q9. `flush()` có đồng nghĩa fsync hoặc remote ACK không?**  
Không. Đó là những mức xác nhận khác nhau.

**Q10. Khi tối ưu nên theo throughput hay latency?**  
Theo **SLO của hệ thống**, thường cân bằng throughput, P95/P99 latency, memory, lỗi và durability.

**Q11. Có cần poller khi một `ByteStreamReadingMessageSource` nối `DirectChannel` không?**  
Có. Source pollable cần endpoint/poller; downstream handler trên DirectChannel không cần poller riêng.

**Q12. Tăng `bytesPerMessage` có tự làm DB batch lớn hơn không?**  
Không. Byte chunk và business records là hai đơn vị khác nhau.

**Q13. Có thể retry `source.receive()` để lấy chunk vừa bị queue từ chối không?**  
Không mặc định. InputStream đã tiến lên; cần nguồn replay/staging/checkpoint.

**Q14. Vì sao phải test với file/network thật?**  
Test RAM không mô phỏng OS I/O, network, SDK, encryption, latency hoặc cache đúng workload.

**Q15. EOF có đủ để tuyên bố job completed khi còn queue không?**  
Không. Phải drain in-flight, flush/close và xác nhận commit theo contract.

**Q16. Thế nào là cách đánh giá tối ưu thiếu tin cậy?**  
Chạy một lần, không kiểm tra bytes output, chỉ đo throughput nhưng bỏ qua GC/latency/error hoặc thay nhiều tham số cùng lúc.

## 25. Ghi nhớ

**Buffer size và hiệu năng** trong Spring Integration là một bài toán **nhiều tầng**, không phải tìm một con số 8192 hay 65536 “chuẩn cho mọi hệ thống”. `ByteStreamReadingMessageSource` có constructor cấu hình buffer và setter `setBytesPerMessage(...)` (mặc định **1024 bytes/message**); `ByteStreamWritingMessageHandler` có constructor `(OutputStream, bufferSize)`. Với character stream, `BufferedReader`/`BufferedWriter` điều khiển buffer ký tự, còn UTF-8 charset và độ dài bản ghi là hợp đồng riêng.

**Những nguyên tắc cốt lõi**:

1. Tách **I/O buffer**, **message chunk**, **queue capacity**, **record/frame size** và **output buffer**; không nhầm một tham số với tham số khác.
2. **Đừng giả định một read là một record**: dùng `shouldTruncate(true)` cho bytes thực đọc, framing và decoder đúng khi text/JSON bị chia qua chunks.
3. **Đo trước khi tối ưu**: throughput, P99 latency, message rate, GC, peak RSS, memory backlog và lỗi trên cùng workload.
4. **Giữ đúng backpressure và reliability**: queue bounded, checkpoint/durable staging nếu nguồn có thể mất, event ID/idempotency khi retry.
5. **Kết thúc có kiểm soát**: stop intake → drain → flush → close, và phân biệt flush với fsync hoặc ACK nghiệp vụ.

Nếu nút thắt nằm ở JDBC, TCP, SFTP, HTTP, JMS, AMQP hoặc Kafka, tối ưu đúng tầng giao thức/adapter tương ứng sẽ hữu ích hơn việc tăng mọi Java buffer. Lựa chọn cuối cùng phải dựa vào **SLO và phép đo** của ứng dụng cụ thể.

### Tài liệu tham khảo

- [Spring Integration 6.5 Reference — Stream Support](https://docs.spring.io/spring-integration/reference/6.5/stream.html)
- [Spring Integration 6.5 API — ByteStreamReadingMessageSource](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/ByteStreamReadingMessageSource.html)
- [Spring Integration 6.5 API — ByteStreamWritingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/ByteStreamWritingMessageHandler.html)
- [Spring Integration 6.5 API — CharacterStreamReadingMessageSource](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/CharacterStreamReadingMessageSource.html)
- [Spring Integration 6.5 API — CharacterStreamWritingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/stream/CharacterStreamWritingMessageHandler.html)
- [Spring Integration 6.5 Reference — Message Channels](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)
- [Spring Integration 6.5 Reference — Pollers](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html)
- [Java SE 17 — BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [Java SE 17 — BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html)
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [Java SE 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [Java SE 17 — FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean))
- [Oracle Java 17 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html)




