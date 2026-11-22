# Giới hạn bộ đệm, fragmentation và payload lớn trong RSocket

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt kích thước frame, kích thước payload sau khi ghép mảnh và giới hạn bộ nhớ của codec.
- Giải thích RSocket fragmentation hoạt động như thế nào và vì sao fragmentation không biến một payload lớn thành luồng dữ liệu có thể xử lý từng phần.
- Cấu hình ngưỡng fragmentation và giới hạn payload nhận trong RSocket Java thông qua Spring Framework.
- Chọn giữa một payload đơn, fragmentation ở tầng giao thức, chunking ở tầng ứng dụng và lưu trữ ngoài.
- Dùng Reactive Streams backpressure để giới hạn lượng dữ liệu đang được xử lý đồng thời.

Bài này thuộc chủ đề **Spring Framework - messaging**, trong ngữ cảnh **Vòng đời RSocket**. Trọng tâm là giới hạn bộ đệm, fragmentation và cách truyền dữ liệu lớn an toàn.

## 1. Payload, frame và buffer là ba khái niệm khác nhau

RSocket truyền thông điệp trên một kết nối dạng byte stream như TCP hoặc WebSocket. Một thông điệp RSocket có phần **data** và phần **metadata**. Metadata thường chứa route, MIME type hoặc thông tin phục vụ định tuyến và bảo mật; data chứa nội dung nghiệp vụ.

Trong Spring Framework, **RSocketRequester** cung cấp API cấp cao để gửi và nhận object. **RSocketStrategies** chọn encoder và decoder để chuyển object thành data/metadata và ngược lại. Ở phía nhận, **@MessageMapping** ánh xạ request vào handler. Phía dưới các abstraction đó, RSocket Java làm việc với **Payload** và các frame của giao thức.

Cần phân biệt:

- **Payload** là thông điệp logic mà ứng dụng gửi hoặc nhận.
- **Frame** là đơn vị dữ liệu được đóng gói để truyền trên kết nối. Một payload có thể nằm trong một frame hoặc nhiều frame.
- **Buffer** là vùng nhớ chứa byte trong quá trình nhận, ghép, giải mã, xử lý hoặc gửi dữ liệu. Buffer có thể nằm trên heap hoặc dùng bộ nhớ trực tiếp do thư viện mạng quản lý.

Vì vậy, một payload 5 MB có thể được truyền thành nhiều frame nhỏ, nhưng ứng dụng vẫn nhận một payload logic 5 MB sau khi thư viện ghép các fragment. Việc chia frame không tự động làm giảm lượng dữ liệu cần giữ để giải mã một payload đơn.

## 2. Các lớp giới hạn cần kiểm tra

Không có một tham số duy nhất kiểm soát mọi giới hạn kích thước. Hãy xác định lỗi xảy ra ở lớp nào trước khi thay đổi cấu hình.

| Lớp | Tham số hoặc khái niệm | Phạm vi kiểm soát | Câu hỏi cần trả lời |
|---|---|---|---|
| Transport | Maximum frame length | Frame mà transport có thể chấp nhận | Một frame riêng lẻ có vượt giới hạn transport không? |
| RSocket fragmentation | MTU/fragment size | Ngưỡng để chia frame khi gửi | Payload có cần chia thành frame nhỏ hơn không? |
| RSocket reassembly | Maximum inbound payload size | Tổng payload sau khi ghép các fragment nhận được | Một thông điệp logic lớn nhất được phép là bao nhiêu byte? |
| Spring codec | Maximum in-memory size | Dữ liệu codec cần buffer để decode/encode | Decoder có phải gom quá nhiều byte trước khi tạo object không? |
| Ứng dụng | Chunk size, concurrency, queue capacity | Dữ liệu và công việc ứng dụng giữ đồng thời | Có bao nhiêu payload/chunk đang được xử lý cùng lúc? |

Các giới hạn này độc lập về mục đích:

1. Giảm MTU hoặc bật fragmentation giúp một payload đi qua transport bằng nhiều frame.
2. Giới hạn inbound payload bảo vệ bước ghép các fragment thành một thông điệp logic.
3. Giới hạn codec bảo vệ bước buffer và giải mã dữ liệu thành object.
4. Giới hạn concurrency và queue bảo vệ tổng bộ nhớ khi có nhiều request cùng hoạt động.

Tăng một giới hạn không tự động tăng các giới hạn còn lại. Ví dụ, tăng kích thước payload được phép nhận không làm decoder chấp nhận một buffer vượt quá giới hạn riêng của decoder.

## 3. RSocket fragmentation và reassembly

### 3.1. Cơ chế

Khi một payload hoặc request frame lớn hơn ngưỡng fragmentation đã cấu hình, RSocket có thể chia nó thành nhiều fragment để truyền. Cờ **Follows** cho biết fragment hiện tại còn fragment tiếp theo hay không.

Với một request bị phân mảnh:

1. Frame đầu tiên vẫn mang loại request ban đầu, chẳng hạn REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL hoặc REQUEST_FNF.
2. Các frame tiếp theo dùng PAYLOAD để tiếp tục chuyển phần còn lại.
3. Các fragment trung gian bật cờ Follows. Fragment cuối cùng không bật cờ này.
4. Receiver ghép các phần lại thành payload logic trước khi chuyển cho tầng xử lý request.

Với một PAYLOAD frame bị phân mảnh, chuỗi fragment gồm các PAYLOAD frame. Theo quy tắc giao thức, metadata được truyền hoàn tất trước phần data. Việc phân mảnh không làm thay đổi số request credit: một payload logic vẫn được tính là một message đối với request(n), dù nó được truyền qua nhiều fragment.

### 3.2. Fragmentation giải quyết điều gì?

Fragmentation hữu ích khi:

- Payload đơn lớn hơn kích thước frame mà bạn muốn gửi.
- Transport hoặc hạ tầng mạng có ngưỡng frame phù hợp nhỏ hơn payload.
- Bạn muốn tránh gửi một frame rất lớn trên kết nối byte stream.

Fragmentation không giải quyết:

- Tổng dung lượng của payload logic.
- Việc decoder cần buffer dữ liệu để tạo một object hoàn chỉnh.
- Việc ứng dụng giữ nhiều payload lớn cùng lúc.
- Việc truyền một file rất lớn theo cách có thể xử lý và giải phóng từng phần ngay khi nhận.

Receiver vẫn phải ghép payload. Do đó, một payload lớn vẫn có thể tiêu thụ nhiều bộ nhớ dù từng frame riêng lẻ nhỏ.

### 3.3. Cấu hình từ Spring RSocketRequester

Spring cho phép tùy chỉnh RSocket Java connector thông qua callback **rsocketConnector** của builder. Ví dụ dưới đây đặt ngưỡng fragmentation là 64 KiB và giới hạn payload nhận sau khi ghép là 32 MiB:

```java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector
        .fragment(64 * 1024)
        .maxInboundPayloadSize(32 * 1024 * 1024))
    .tcp("localhost", 7000);
```

Đây là giá trị minh họa để giải thích API, không phải cấu hình mặc định phù hợp cho mọi hệ thống. Hãy chọn dựa trên kích thước payload thực tế, transport, số kết nối đồng thời và ngân sách bộ nhớ.

Ý nghĩa của hai phương thức:

- **fragment(mtu)** đặt ngưỡng để RSocket chia frame lớn thành fragment khi gửi.
- **maxInboundPayloadSize(bytes)** đặt giới hạn kích thước payload inbound sau khi reassembly. Giới hạn này áp dụng cho payload logic, không phải chỉ cho từng fragment.

RSocket Java yêu cầu maxInboundPayloadSize không nhỏ hơn maximum frame length của transport. Nếu không, một frame inbound riêng lẻ có thể lớn hơn giới hạn reassembly và cấu hình không hợp lệ. Hãy kiểm tra transport đang dùng và phiên bản rsocket-core trước khi chốt giá trị.

Cần cấu hình chính sách nhận ở cả hai phía của kết nối. Ví dụ, giới hạn inbound ở client bảo vệ client khi nhận response; giới hạn inbound ở server bảo vệ server khi nhận request. Cấu hình fragmentation của bên gửi cần tương thích với khả năng nhận của bên kia.

Khi dùng Spring Boot, builder và RSocketStrategies có thể được auto-configure. Bạn vẫn có thể tùy chỉnh connector qua callback hoặc cơ chế customizer mà phiên bản Spring Boot đang dùng cung cấp. Không giả định một property của HTTP/WebFlux tự động thay thế các giới hạn ở RSocket transport.

## 4. Giới hạn bộ nhớ của Spring codec

RSocket fragmentation thuộc tầng giao thức. Spring codec thuộc tầng chuyển đổi byte thành object. Hai tầng có thể tạo ra hai loại lỗi khác nhau.

Spring Core cung cấp **DataBuffer**, **DataBufferFactory**, **DataBufferUtils**, **Encoder** và **Decoder**. RSocketStrategies tập hợp encoder/decoder dùng cho data và metadata. Các codec có thể cần gom một lượng byte nhất định trước khi giải mã, ví dụ khi tạo một object JSON duy nhất.

Nếu codec phải buffer nhiều byte hơn giới hạn cho phép, ứng dụng có thể gặp:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Lỗi này cho biết thao tác buffer của codec vượt giới hạn. Nó không đồng nghĩa với việc một frame RSocket vượt maximum frame length, và cũng không tự chứng minh rằng fragmentation chưa được bật.

Ví dụ cấu hình một Jackson JSON decoder với giới hạn 4 MiB rồi đăng ký decoder đó vào RSocketStrategies:

```java
Jackson2JsonDecoder jsonDecoder = new Jackson2JsonDecoder();
jsonDecoder.setMaxInMemorySize(4 * 1024 * 1024);

RSocketStrategies strategies = RSocketStrategies.builder()
    .decoders(decoders -> decoders.add(jsonDecoder))
    .build();
```

Đây là đoạn cấu hình codec; hãy bảo đảm decoder được đăng ký đúng thứ tự và được chọn cho MIME type của kết nối. Nếu ứng dụng dùng Spring Boot auto-configuration, có thể tùy chỉnh RSocketStrategies thông qua cơ chế **RSocketStrategiesCustomizer** phù hợp với phiên bản đang dùng.

Không nên tăng giới hạn codec một cách máy móc. Trước hết hãy xác định:

- Codec nào đang decode payload.
- Codec đang buffer toàn bộ message hay có thể decode theo từng phần.
- Payload lớn đến từ data hay metadata.
- Có thể đổi định dạng hoặc chuyển sang streaming/chunking hay không.
- Mỗi request và số request đồng thời có thể tiêu thụ bao nhiêu bộ nhớ.

Một codec có giới hạn cao hơn chỉ cho phép một lần decode giữ nhiều byte hơn. Nó không làm payload nhỏ đi và cũng không kiểm soát số request cùng lúc.

## 5. Chọn cách truyền dữ liệu lớn

### 5.1. Dùng một payload đơn

Dùng một payload đơn khi dữ liệu có kích thước hữu hạn, được giới hạn rõ ràng và cần xử lý như một object hoàn chỉnh, chẳng hạn một lệnh cập nhật hoặc một bản ghi có kích thước vừa phải.

Ưu điểm là mô hình đơn giản: encode một lần, gửi một request, decode một lần. Nhược điểm là receiver cần nhận và xử lý toàn bộ payload logic. Không dùng cách này cho file rất lớn hoặc dữ liệu có thể phát sinh không giới hạn.

### 5.2. Dùng protocol fragmentation

Dùng fragmentation khi vẫn muốn giữ một message logic duy nhất nhưng cần truyền nó qua các frame nhỏ hơn. Ứng dụng tiếp tục làm việc với một payload sau reassembly.

Đây là giải pháp cho giới hạn frame/transport, không phải giải pháp streaming từng phần ở tầng nghiệp vụ.

### 5.3. Dùng application-level chunking

Với file hoặc dữ liệu lớn, hãy chia dữ liệu thành các chunk có kích thước giới hạn ở tầng ứng dụng. Mỗi chunk là một phần dữ liệu độc lập mà receiver có thể kiểm tra, ghi xuống storage rồi giải phóng trước khi nhận phần tiếp theo.

Một mô hình chunk thực tế nên có:

- transferId để nhận diện lần truyền.
- sequence để xác định thứ tự chunk.
- bytes chứa dữ liệu của chunk.
- Kích thước chunk tối đa.
- Thông tin kết thúc hoặc tổng số chunk/tổng kích thước nếu giao thức ứng dụng cần.
- Checksum để phát hiện dữ liệu bị sai hoặc thiếu.
- Chính sách xử lý chunk trùng, chunk đến sai thứ tự, timeout và retry.

Ví dụ về hình dạng handler Spring RSocket nhận luồng chunk:

```java
@Controller
class FileUploadController {

    @MessageMapping("files.upload")
    Mono<UploadResult> upload(Flux<FileChunk> chunks) {
        return chunks
            .concatMap(chunk -> storage.append(chunk))
            .then(storage.complete());
    }
}
```

Đây là skeleton minh họa; **FileChunk**, **UploadResult** và **storage** là kiểu dữ liệu/dịch vụ do ứng dụng định nghĩa. Với đầu vào Flux, handler nhận một luồng message theo mô hình Request-Channel. **concatMap** xử lý tuần tự từng chunk và giữ thứ tự. API lưu trữ phải hoàn tất việc ghi chunk trước khi yêu cầu xử lý tiếp tục; không gom toàn bộ Flux vào một List.

Nếu cần xử lý song song, hãy đặt concurrency hữu hạn và bảo đảm thứ tự/độ an toàn khi ghi. Không thay concatMap bằng flatMap không giới hạn chỉ để tăng throughput.

### 5.4. Ví dụ Java 17: chia và ghép byte array

Ví dụ độc lập sau minh họa ranh giới chunk ở tầng ứng dụng. Nó dùng một byte array nhỏ để kiểm tra thuật toán; với file lớn trong production, hãy đọc dữ liệu theo luồng từ file hoặc storage thay vì nạp toàn bộ file vào một byte array trước.

Lưu thành **PayloadChunkingDemo.java**:

```java
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PayloadChunkingDemo {

    static List<byte[]> split(byte[] source, int chunkSize) {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        List<byte[]> chunks = new ArrayList<>();
        for (int offset = 0; offset < source.length; offset += chunkSize) {
            int end = Math.min(offset + chunkSize, source.length);
            chunks.add(Arrays.copyOfRange(source, offset, end));
        }
        return chunks;
    }

    static byte[] join(List<byte[]> chunks) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        for (byte[] chunk : chunks) {
            output.write(chunk, 0, chunk.length);
        }
        return output.toByteArray();
    }

    public static void main(String[] args) {
        byte[] source = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};

        List<byte[]> chunks = split(source, 4);
        byte[] restored = join(chunks);

        System.out.println("chunks=" + chunks.size());
        System.out.println("restored=" + Arrays.equals(source, restored));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac PayloadChunkingDemo.java
java PayloadChunkingDemo
```

Output chính xác:

```text
chunks=3
restored=true
```

Dữ liệu 10 byte được chia thành ba chunk có kích thước lần lượt 4, 4 và 2 byte. Khi ghép đúng thứ tự, byte array thu được giống dữ liệu ban đầu. Trong ứng dụng truyền file, cần bổ sung transferId, sequence, checksum và xử lý lỗi; ví dụ trên chỉ kiểm tra phép chia/ghép cơ bản.

### 5.5. Lưu file ngoài và truyền tham chiếu

Nếu payload là file rất lớn, có thể truyền file qua object storage hoặc một dịch vụ lưu trữ chuyên dụng, rồi gửi qua RSocket một thông điệp nhỏ chứa:

- ID hoặc URI tham chiếu.
- Kích thước và checksum.
- Loại nội dung.
- Quyền truy cập hoặc token có thời hạn.

Cách này giảm áp lực lên kết nối RSocket và bộ nhớ của service. Cần bảo đảm quyền truy cập, thời hạn của URL, tính toàn vẹn dữ liệu và quy trình xóa file tạm.

## 6. Backpressure và ngân sách bộ nhớ

RSocket hỗ trợ Reactive Streams semantics cho Request-Stream và Request-Channel. Receiver phát tín hiệu demand bằng request(n); sender nên chỉ phát số message mà downstream đã yêu cầu. Backpressure giúp giới hạn tốc độ giữa producer và consumer.

Backpressure không thay thế giới hạn payload đơn. Một message có thể rất lớn dù demand chỉ bằng một. Tương tự, nếu ứng dụng gọi collectList(), cache(), block() hoặc tự đưa tất cả chunk vào một queue không giới hạn, lợi ích của streaming sẽ bị mất.

Hãy quản lý đồng thời hai yếu tố:

1. Kích thước tối đa của mỗi payload hoặc chunk.
2. Số payload/chunk và số request đang được xử lý đồng thời.

Một ước lượng ngân sách bộ nhớ để bắt đầu thiết kế:

```text
Memory pressure
≈ concurrent requests
  × (reassembled payload
     + decoded object
     + temporary copies
     + queued work)
```

Đây là mô hình ước lượng, không phải công thức đo chính xác. Object sau decode có thể lớn hơn nhiều so với byte JSON ban đầu; encoder/decoder hoặc thao tác copy cũng có thể tạo thêm vùng nhớ tạm. Nếu dùng buffer pooling hoặc direct memory, không chỉ nhìn heap usage để kết luận ứng dụng không bị áp lực bộ nhớ.

Các thực hành hữu ích:

- Đặt giới hạn inbound payload rõ ràng ở mỗi endpoint.
- Đặt chunk size theo throughput, độ trễ và ngân sách bộ nhớ.
- Giới hạn concurrency, prefetch và queue capacity.
- Dùng pipeline reactive để xử lý rồi giải phóng chunk sớm.
- Tránh giữ reference đến chunk sau khi xử lý xong.
- Đo cả heap, direct memory, garbage collection và số request đồng thời.
- Chỉ dùng zero-copy khi hiểu rõ vòng đời buffer. Với PayloadDecoder.ZERO_COPY trong RSocket Java, data và metadata có thể là retained slice của buffer gốc; code xử lý ở tầng thấp phải release payload đúng lúc để tránh rò rỉ bộ nhớ.

## 7. Chẩn đoán lỗi theo đúng tầng

| Triệu chứng | Lớp có khả năng liên quan | Cách kiểm tra |
|---|---|---|
| Frame bị từ chối vì quá lớn | Transport/frame length | Kiểm tra maximum frame length và kích thước frame gửi đi. |
| Lỗi khi ghép fragment hoặc payload vượt giới hạn | RSocket reassembly | Kiểm tra maxInboundPayloadSize ở receiver và kích thước payload logic. |
| DataBufferLimitException | Spring codec | Xác định decoder/encoder và giới hạn buffer của codec đang được chọn. |
| Heap/direct memory tăng mạnh khi tải cao | Ứng dụng, codec hoặc buffer | Kiểm tra concurrency, queue, object sau decode, thao tác copy và vòng đời buffer. |
| Luồng chậm hoặc dừng giữa chừng | Backpressure hoặc downstream | Kiểm tra demand, tốc độ ghi storage, timeout, cancellation và lỗi trong subscriber. |
| Dữ liệu ghép sai hoặc thiếu | Application-level chunking | Kiểm tra transferId, sequence, checksum, chunk cuối và retry trùng. |

Khi điều tra, ghi nhận kích thước data và metadata theo byte, kích thước payload sau reassembly, số fragment, thời gian xử lý và số request đồng thời. Không ghi toàn bộ nội dung payload vào log nếu dữ liệu có thể chứa thông tin nhạy cảm.

## 8. Quy trình chọn và điều chỉnh giới hạn

1. Đo kích thước payload thực tế ở cả phía gửi và nhận; tách data với metadata nếu có thể.
2. Xác định giới hạn frame của transport đang dùng.
3. Chọn ngưỡng fragmentation phù hợp với transport và môi trường mạng.
4. Đặt maxInboundPayloadSize đủ cho payload hợp lệ lớn nhất, đồng thời không nhỏ hơn maximum frame length của transport.
5. Kiểm tra codec được chọn trong RSocketStrategies và giới hạn buffer của codec đó.
6. Tính ngân sách theo số request đồng thời, object sau decode và vùng nhớ tạm.
7. Nếu payload vẫn quá lớn để giữ như một object, chuyển sang application-level chunking hoặc lưu trữ ngoài.
8. Kiểm thử với payload ở sát giới hạn, payload vượt giới hạn, nhiều request đồng thời, cancellation và kết nối bị ngắt giữa chừng.
9. Quan sát heap, direct memory, độ trễ, throughput và lỗi decode trong tải thực tế.

Không nên đặt mọi giới hạn thành một giá trị rất lớn hoặc bỏ giới hạn hoàn toàn. Giới hạn là một phần của hợp đồng giữa producer và consumer, đồng thời là hàng rào bảo vệ tài nguyên.

## 9. Những nhầm lẫn thường gặp

- **Bật fragmentation là đủ để gửi file bất kỳ kích thước nào.** Không đúng: receiver vẫn reassemble payload và cần đủ bộ nhớ cho message logic.
- **MTU và maxInboundPayloadSize là cùng một giá trị.** Không đúng: MTU quyết định ngưỡng chia frame; maxInboundPayloadSize giới hạn payload sau reassembly.
- **Tăng maxInboundPayloadSize sẽ khắc phục DataBufferLimitException.** Không nhất thiết: đây là giới hạn ở codec và phải kiểm tra riêng.
- **Một request(n) credit tương ứng với một fragment.** Không đúng: fragmentation không làm tăng số message credit; một payload logic vẫn là một message.
- **Dùng Flux nghĩa là dữ liệu luôn được xử lý streaming.** Không đúng nếu code gom Flux vào bộ nhớ, tạo queue không giới hạn hoặc giữ lại mọi chunk.
- **Zero-copy luôn an toàn và luôn nhanh hơn.** Không đúng nếu code không quản lý vòng đời/release buffer đúng cách.
- **Tăng concurrency luôn tăng throughput.** Không đúng khi storage, CPU hoặc bộ nhớ đã bão hòa; concurrency cao có thể làm tăng latency và memory pressure.

## 10. Checklist trước khi đưa vào production

- [ ] Đã phân biệt giới hạn frame, fragmentation, reassembly và codec.
- [ ] Đã đặt giới hạn payload inbound ở cả client và server theo vai trò nhận dữ liệu.
- [ ] maxInboundPayloadSize không nhỏ hơn maximum frame length của transport.
- [ ] MTU/fragment size được kiểm thử với transport thực tế.
- [ ] Codec trong RSocketStrategies có giới hạn phù hợp với payload hợp lệ.
- [ ] Payload lớn đã được cân nhắc chuyển sang chunking hoặc object storage.
- [ ] Chunk có transferId, sequence và cơ chế xác minh tính toàn vẹn.
- [ ] Backpressure, concurrency và queue đều có giới hạn.
- [ ] Có kiểm thử payload sát ngưỡng, vượt ngưỡng, nhiều request đồng thời và cancellation.
- [ ] Có quan sát heap, direct memory, latency, throughput và lỗi buffer.
- [ ] Không log nội dung payload nhạy cảm.

## Kết luận

Fragmentation giải quyết giới hạn kích thước frame bằng cách chia một message logic thành nhiều frame. Reassembly vẫn tạo lại payload hoàn chỉnh, nên giới hạn payload nhận và giới hạn buffer của codec tiếp tục có ý nghĩa riêng. Với dữ liệu rất lớn, application-level chunking kết hợp backpressure thường cho phép xử lý và giải phóng dữ liệu từng phần; với file, lưu trữ ngoài và gửi tham chiếu có thể phù hợp hơn.

## Tài liệu tham khảo

- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [RSocket Protocol - Fragmentation and Reassembly](https://rsocket.io/about/protocol/)
- [Spring Boot Reference - RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Java - RSocketConnector API source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java)
