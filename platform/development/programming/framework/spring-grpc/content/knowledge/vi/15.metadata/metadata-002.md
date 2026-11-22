# ASCII metadata và binary metadata

Trong gRPC, **metadata** mang thông tin phụ trợ của một lời gọi RPC dưới dạng các cặp **key–value**. Hai loại value quan trọng là **ASCII metadata** (chuỗi ký tự) và **binary metadata** (dãy byte). Cả hai đều được vận chuyển qua HTTP/2 headers hoặc trailers, nhưng khác nhau về tên key, cách mã hóa trên đường truyền và kiểu dữ liệu mà ứng dụng Java thao tác.

Trong hệ sinh thái Spring gRPC, hai loại metadata này được xử lý bằng API của `grpc-java`, đặc biệt là `io.grpc.Metadata` và các interceptor. Hiểu đúng sự khác biệt giúp truyền request ID, thông tin client và dữ liệu nhị phân nhỏ một cách nhất quán, đồng thời tránh lỗi mã hóa, rò rỉ thông tin và vượt giới hạn header.

**Mục tiêu học tập:**

- Phân biệt ASCII metadata và binary metadata bằng tên key, kiểu value, cách mã hóa và tình huống sử dụng.
- Tạo `Metadata.Key<String>` và `Metadata.Key<byte[]>` đúng với từng `Marshaller`.
- Gửi, nhận và kiểm tra dữ liệu qua `Metadata.put`, `get`, `getAll` trong Java.
- Nhận diện giới hạn về dung lượng, quyền truy cập, dữ liệu Unicode và metadata trùng key.
- Tích hợp với gRPC client/server interceptor trong ứng dụng Spring và xây dựng kiểm thử phù hợp.

## 1. Vì sao gRPC cần hai loại metadata?

Hãy xét dịch vụ `OrderService` viết bằng Spring gRPC. Khi client gọi `PlaceOrder`, message Protobuf mang `order_id` và danh sách mặt hàng. Ngoài dữ liệu nghiệp vụ, client muốn gửi:

- `x-request-id: req-2026-0042` để tìm log của cùng một yêu cầu.
- `x-client-version: 3.2.1` để phân tích phiên bản ứng dụng đang gọi.
- Một tập byte mô tả khả năng của client (`x-capabilities-bin`), ví dụ dữ liệu do hai bên thống nhất định dạng.

Hai giá trị đầu là chuỗi ngắn, biểu diễn được bằng ASCII. Giá trị thứ ba là byte tùy ý, nên sử dụng binary metadata. Nếu nhét byte tùy ý vào header ASCII, một số byte không phải ký tự in được và quá trình chuyển đổi có thể làm thay đổi nội dung.

Metadata thuộc **phạm vi lời gọi RPC**, không phải từng message. Với unary và mọi loại streaming RPC, headers được gửi khi bắt đầu lời gọi; response trailers được gửi khi kết thúc. Các giá trị thay đổi theo từng bản ghi trong stream nên thuộc message Protobuf.

## 2. So sánh ASCII metadata và binary metadata

| Tiêu chí | ASCII metadata | Binary metadata |
| --- | --- | --- |
| Tên key | Ví dụ `x-request-id` | **Bắt buộc** kết thúc bằng `-bin`, ví dụ `x-capabilities-bin` |
| Value phía Java | `String` | `byte[]` |
| Marshaller thông dụng | `Metadata.ASCII_STRING_MARSHALLER` | `Metadata.BINARY_BYTE_MARSHALLER` |
| Biểu diễn trên HTTP/2 | Chuỗi ASCII trong header value | Byte được mã hóa Base64 theo quy tắc gRPC |
| Phù hợp | ID, mã ngôn ngữ, phiên bản, flag ngắn | Dữ liệu byte ngắn, định dạng nhị phân do hai bên thỏa thuận |
| Rủi ro thường gặp | Unicode hoặc ký tự điều khiển không phù hợp; giá trị quá dài | Tự Base64 lần nữa; dùng sai hậu tố key; không thống nhất định dạng byte |
| Bảo mật | Không tự động mã hóa bí mật | Cũng không tự động mã hóa bí mật |

Điểm dễ nhầm là **binary metadata không có nghĩa là mã hóa bảo mật**. Base64 chỉ chuyển byte sang biểu diễn phù hợp với header HTTP/2; ai đọc được header sau khi giải mã cũng có thể lấy lại byte gốc. Vì vậy, cả hai loại đều cần kênh truyền bảo vệ phù hợp, chẳng hạn TLS khi gọi qua mạng.

### 2.1. Quy tắc chung về key

Theo định dạng gRPC, tên metadata key dùng ký tự ASCII chữ thường `a–z`, chữ số `0–9`, dấu gạch ngang `-`, gạch dưới `_` và dấu chấm `.`. HTTP/2 yêu cầu tên header chữ thường; một số API có thể chuẩn hóa tên đầu vào nhưng mã ứng dụng nên chủ động đặt chữ thường.

Các key bắt đầu bằng `grpc-` được dành cho giao thức. Ví dụ:

| Key | Đánh giá | Lý do |
| --- | --- | --- |
| `x-request-id` | Hợp lệ, loại ASCII | Không có hậu tố `-bin` |
| `x-capabilities-bin` | Hợp lệ, loại binary | Có hậu tố `-bin` |
| `authorization` | Hợp lệ, loại ASCII | Thường dùng cho thông tin xác thực theo cơ chế đã chọn |
| `grpc-custom-id` | Không dùng cho metadata ứng dụng | Tiền tố `grpc-` thuộc phạm vi dành riêng |
| `x-capabilities` cho raw bytes | Sai thiết kế | Thiếu hậu tố `-bin` nên không thể dùng như binary metadata |
| `Tên-Người-Dùng` | Không hợp lệ | Key chứa ký tự ngoài bảng chữ cái ASCII được phép |

Hậu tố `-bin` là quy tắc của **loại dữ liệu**, không chỉ là sở thích đặt tên. Với `Metadata.Key.of(...)`, marshaller ASCII đi cùng key thường, còn marshaller binary đi cùng key `-bin`.

### 2.2. Quy tắc về value

**ASCII value:** Trong giao thức gRPC, custom ASCII header value được biểu diễn bằng các ký tự ASCII in được (khoảng byte `0x20` đến `0x7E`). Tránh đưa trực tiếp tên tiếng Việt có dấu, ký tự điều khiển hoặc nội dung nhiều dòng vào ASCII metadata. Nếu cần văn bản Unicode, hãy cân nhắc trường `string` trong Protobuf; nếu một giao thức phụ bắt buộc dùng metadata, phải thống nhất cách mã hóa với bên nhận.

**Binary value:** Có thể chứa mọi giá trị byte, kể cả `0x00`, `0x80` và `0xFF`. Thư viện gRPC mã hóa/giải mã khi vận chuyển, nên trong Java ứng dụng vẫn làm việc trực tiếp với `byte[]`.

## 3. ASCII và binary được truyền trên HTTP/2 như thế nào?

Về mặt khái niệm:

```text
                 Ứng dụng Java                     HTTP/2                     Ứng dụng Java

ASCII    "req-42" --------------------------> x-request-id: req-42 -----------> "req-42"

Binary   byte[] {0x00, 0x7F, 0xFF} ---------> x-data-bin: AH// --------------> byte[] {0x00, 0x7F, 0xFF}
                           gRPC mã hóa Base64                         gRPC giải mã Base64
```

Trong ví dụ, `AH//` là Base64 của ba byte `00 7F FF`. Đây là minh họa giá trị trên đường truyền; code sử dụng `grpc-java` **không tự thêm bước Base64**.

Đối với binary metadata, giao thức có thể chấp nhận Base64 có hoặc không có ký tự đệm `=`; thư viện chịu trách nhiệm tương thích và xử lý chi tiết này. Không viết logic ứng dụng dựa trên việc header quan sát được luôn có đúng một biểu diễn Base64 cụ thể.

**Giới hạn vận chuyển:** Metadata nằm trong HTTP/2 headers/trailers, chịu giới hạn dung lượng do gRPC server, client, reverse proxy hoặc load balancer áp dụng. Tài liệu giao thức gRPC đề xuất giới hạn mặc định khoảng 8 KiB cho request headers, nhưng giới hạn thực tế tùy cấu hình của từng thành phần. Binary metadata còn có chi phí biểu diễn khi truyền qua Base64. Vì vậy, chỉ gửi các giá trị nhỏ; file, JSON lớn và dữ liệu nghiệp vụ phức tạp nên nằm trong message hoặc nơi lưu phù hợp.

## 4. Khai báo metadata key và value trong Java

`io.grpc.Metadata` là tập hợp key–value có thể thay đổi. `Metadata.Key<T>` kết hợp tên key với cách chuyển đổi dữ liệu qua marshaller.

### 4.1. Ví dụ ASCII metadata

```java
import io.grpc.Metadata;

public class AsciiMetadataExample {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> CLIENT_VERSION =
        Metadata.Key.of("x-client-version", Metadata.ASCII_STRING_MARSHALLER);

    public static void main(String[] args) {
        Metadata metadata = new Metadata();

        metadata.put(REQUEST_ID, "req-2026-0042");
        metadata.put(CLIENT_VERSION, "3.2.1");

        System.out.println(metadata.get(REQUEST_ID));    // req-2026-0042
        System.out.println(metadata.get(CLIENT_VERSION)); // 3.2.1
    }
}
```

Ở ví dụ trên, kiểu Java là `String`, key không kết thúc bằng `-bin` và marshaller là `ASCII_STRING_MARSHALLER`. Khi phía nhận biết đúng tên key và quy tắc ASCII, họ có thể đọc value mà không cần giả định thêm định dạng nhị phân.

### 4.2. Ví dụ binary metadata

```java
import io.grpc.Metadata;
import java.util.Arrays;

public class BinaryMetadataExample {
    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of(
            "x-capabilities-bin",
            Metadata.BINARY_BYTE_MARSHALLER
        );

    public static void main(String[] args) {
        byte[] bytes = new byte[] {0x00, 0x7F, (byte) 0xFF};

        Metadata metadata = new Metadata();
        metadata.put(CAPABILITIES, bytes);

        byte[] received = metadata.get(CAPABILITIES);
        System.out.println(Arrays.equals(bytes, received)); // true
    }
}
```

Ép kiểu `(byte) 0xFF` cần thiết vì `byte` trong Java có dấu và chỉ nhận literal số nguyên từ `-128` đến `127` nếu không ép kiểu. Dù đọc ra `-1` khi in kiểu `byte`, mẫu bit thực vẫn là `0xFF`.

Trong ví dụ này, `byte[]` là dữ liệu có định dạng do ứng dụng tự định nghĩa. Hai phía cần thỏa thuận cấu trúc, phiên bản và ý nghĩa từng byte. Việc dùng `-bin` chỉ giải quyết phần truyền tải, **không tự định nghĩa schema** cho chuỗi byte.

### 4.3. Vì sao không tự Base64 trước khi `put`?

Giả sử byte gốc là `{0x00, 0x7F, 0xFF}`. Nếu ứng dụng tự Base64 thành chuỗi `"AH//"`, lấy byte ASCII của chuỗi này rồi đưa vào `BINARY_BYTE_MARSHALLER`, gRPC sẽ mã hóa *chính các byte ASCII đó* thêm lần nữa trên đường truyền. Bên nhận nhận lại byte của `"AH//"`, không phải ba byte ban đầu.

Làm đúng:

```java
byte[] raw = new byte[] {0x00, 0x7F, (byte) 0xFF};
metadata.put(CAPABILITIES, raw);
byte[] restored = metadata.get(CAPABILITIES);
```

Chỉ tự sử dụng Base64 khi định dạng **ứng dụng** đã được hai phía quy định rõ ràng phải là chuỗi Base64. Trường hợp ấy nên cân nhắc liệu key ASCII có phù hợp hơn; không nhầm quy tắc ứng dụng với mã hóa vận chuyển của gRPC.

## 5. Cùng một key có thể chứa nhiều value

`Metadata` không phải một `Map<String, String>` thông thường. Nó có thể chứa nhiều entry với cùng tên key. Phương thức `put` thêm value, `get` trả về value cuối cùng tương ứng và `getAll` trả về iterable của các value.

```java
Metadata.Key<String> TAG =
    Metadata.Key.of("x-tag", Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(TAG, "web");
headers.put(TAG, "canary");

String latestTag = headers.get(TAG);          // canary
Iterable<String> tags = headers.getAll(TAG); // web và canary
boolean exists = headers.containsKey(TAG);   // true
```

Những lưu ý khi đọc:

- Nếu key không tồn tại, `get` hoặc `getAll` trả về `null`.
- Nếu chỉ cho phép một value (ví dụ một mã phiên bản client), hãy kiểm tra số lượng value và từ chối yêu cầu mơ hồ theo chính sách API.
- Không giả định rằng những header bị gộp hoặc tách ở tầng HTTP trung gian sẽ giữ nguyên hình dạng văn bản ban đầu; ứng dụng nên làm việc với API `Metadata`.
- Metadata không được thiết kế để nhiều luồng cùng sửa trên một instance. Tạo metadata theo từng lời gọi và tránh giữ tham chiếu `byte[]` có thể bị sửa sau khi đã đưa vào metadata; sao chép mảng nếu vòng đời dữ liệu yêu cầu.

**Cùng tên khác kiểu không phải cách chuyển đổi:** `Metadata.Key.of("x-data-bin", Metadata.ASCII_STRING_MARSHALLER)` không phải một cách hợp lệ để đọc binary metadata thành chuỗi. Hai phía phải thống nhất tên key và kiểu marshaller, sau đó tự giải mã nội dung `byte[]` nếu có định dạng nội bộ.

## 6. Đưa ASCII và binary metadata vào gRPC client

Trong Spring gRPC, client thường sử dụng các stub do Protobuf/gRPC sinh ra. Interceptor của `grpc-java` có thể thêm metadata **theo từng lời gọi** trước khi client gửi request headers.

Ví dụ sau thêm request ID ASCII và một byte biểu diễn khả năng client. Định dạng mẫu của `x-capabilities-bin` là **một byte**, trong đó bit thấp nhất cho biết client hỗ trợ một chức năng tùy chọn. Đây là định dạng minh họa, do client và server chủ động thống nhất.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class ClientMetadataInterceptor implements ClientInterceptor {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of("x-capabilities-bin", Metadata.BINARY_BYTE_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                headers.put(REQUEST_ID, UUID.randomUUID().toString());
                headers.put(CAPABILITIES, new byte[] {0x01});
                super.start(responseListener, headers);
            }
        };
    }
}
```

Gắn interceptor lên stub:

```java
// channel được cấu hình bởi ứng dụng Spring gRPC hoặc grpc-java.
OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new ClientMetadataInterceptor());

// Mỗi lần stub.placeOrder(...) bắt đầu, interceptor thêm request headers.
```

Tên `OrderServiceGrpc` và `placeOrder` chỉ là ví dụ về các lớp/phương thức được sinh từ hợp đồng `.proto`; trong dự án thực tế hãy thay bằng stub tương ứng. Interceptor ở trên tạo request ID mới trong `start(...)` nên dùng lại stub không khiến các RPC dùng cùng một ID ngoài ý muốn.

Nếu hệ thống cần giữ **một correlation ID xuyên qua nhiều RPC** của cùng một yêu cầu người dùng, hãy nhận ID từ ngữ cảnh tin cậy và tái sử dụng có chủ đích thay vì luôn tạo mới. Tracing phân tán nên dùng cơ chế propagation được cấu hình, không cố thay mọi trace header bằng request ID tùy biến.

## 7. Đọc và xác thực hai loại metadata tại server

`ServerInterceptor` nhận `Metadata headers` trước khi gRPC chuyển lời gọi cho service. Có thể kiểm tra tính hợp lệ của ASCII value và byte payload tại đây.

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ServerMetadataInterceptor implements ServerInterceptor {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of("x-capabilities-bin", Metadata.BINARY_BYTE_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);
        byte[] capabilities = headers.get(CAPABILITIES);

        boolean badRequestId = requestId == null
            || requestId.isBlank()
            || requestId.length() > 64;

        // Giao thức minh họa: payload đúng 1 byte, bit 0 mô tả một capability.
        boolean badCapabilities = capabilities == null
            || capabilities.length != 1;

        if (badRequestId || badCapabilities) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "Invalid request metadata"),
                new Metadata()
            );
            return new ServerCall.Listener<ReqT>() {};
        }

        boolean supportsFeature = (capabilities[0] & 0x01) != 0;
        // Từ đây có thể gắn thông tin đã kiểm tra vào Context nếu service cần.
        // Không ghi byte nhạy cảm vào log.
        return next.startCall(call, headers);
    }
}
```

Đây là ví dụ **chính sách ứng dụng**: server quyết định bắt buộc phải có cả hai key và binary payload dài đúng một byte. Giao thức gRPC không bắt buộc các key tùy biến này. Một service khác có thể xem capability vắng mặt là giá trị mặc định và chỉ kiểm tra khi client cung cấp.

Ở hệ thống Spring gRPC, đăng ký `ClientInterceptor` và `ServerInterceptor` theo cơ chế của phiên bản Spring gRPC/starter đang dùng, và kiểm tra chúng áp dụng cho đúng channel, stub hoặc service. Cần bảo đảm quá trình đăng ký interceptor được kiểm thử thực tế; chỉ khai báo một lớp Java không làm interceptor tự chạy.

## 8. Dùng metadata ở response headers và trailers

Hai loại metadata không chỉ xuất hiện trong request. Server cũng có thể gửi chúng:

| Vị trí | Ví dụ | Thời điểm client đọc |
| --- | --- | --- |
| Request headers | `x-request-id`, `x-capabilities-bin` | Server nhận khi RPC bắt đầu |
| Initial response headers | `x-server-version`, `x-negotiated-bin` | Client nhận khi server bắt đầu phản hồi |
| Response trailers | `x-error-id`, `x-diagnostic-bin` | Client nhận khi RPC kết thúc |

Ở API `ServerCall` của `grpc-java`, có thể gửi metadata ban đầu bằng `sendHeaders(...)` và trả trailers khi `close(status, trailers)`:

```java
// Đoạn minh họa bên trong lớp quản lý ServerCall.
Metadata responseHeaders = new Metadata();
responseHeaders.put(
    Metadata.Key.of(
        "x-server-version",
        Metadata.ASCII_STRING_MARSHALLER),
    "1.4.0"
);
call.sendHeaders(responseHeaders);

Metadata trailers = new Metadata();
trailers.put(
    Metadata.Key.of(
        "x-error-id",
        Metadata.ASCII_STRING_MARSHALLER),
    "err-42"
);
// Khi hoàn tất RPC, call.close(status, trailers) gửi status và trailers.
```

Trong lời gọi thực tế, `sendHeaders` phải tuân thủ thứ tự vòng đời của `ServerCall` và không được gọi lặp sai trạng thái. `grpc-status` và `grpc-message` do gRPC quản lý thông qua `Status`; không tự thêm chúng như custom key. Lời gọi lỗi có thể trả **trailers-only** nên client không nên giả định luôn có initial response headers.

Trong client interceptor, có thể quan sát response headers qua `ClientCall.Listener.onHeaders(Metadata)` và trailers qua `ClientCall.Listener.onClose(Status, Metadata)`. Với RPC thất bại, phần thông tin kết thúc thường quan trọng hơn một message trả về vì message có thể không tồn tại.

## 9. Quyết định chọn ASCII, binary hay trường Protobuf

Hãy chọn kiểu theo **ý nghĩa dữ liệu**, trước cả việc chọn công cụ mã hóa:

| Nhu cầu | Nơi lưu đề xuất | Giải thích |
| --- | --- | --- |
| Request ID ngắn | ASCII metadata | Giá trị là ngữ cảnh của toàn RPC |
| Client version `3.2.1` | ASCII metadata | Chuỗi ngắn, dễ đọc và dùng cho quan sát |
| Dữ liệu cờ nhị phân nhỏ đã thống nhất schema | Binary metadata `-bin` | Giữ nguyên byte, không cần Base64 thủ công |
| Tên người dùng có dấu | Protobuf `string` nếu là dữ liệu nghiệp vụ | Hỗ trợ Unicode rõ ràng và có hợp đồng kiểu |
| Danh sách sản phẩm và số lượng | Message Protobuf | Là payload nghiệp vụ, cần schema và kiểm thử tương thích |
| Ảnh hoặc tệp lớn | Message/stream thích hợp | Metadata bị giới hạn dung lượng header |
| Token truy cập | Credentials và kênh truyền bảo vệ | Đòi hỏi xác minh danh tính và chính sách bảo mật, không chỉ chọn loại metadata |
| Deadline | API deadline của gRPC | Thư viện tạo `grpc-timeout`; ứng dụng không tự ghi key hệ thống |
| Trạng thái RPC | `io.grpc.Status` | gRPC tạo mã trạng thái kết thúc trong trailers |

Nếu định dạng binary phức tạp hoặc cần tiến hóa nhiều trường, một message Protobuf có trường `bytes` hay schema riêng thường dễ quản lý hơn. Binary metadata không mang thông tin schema hoặc khả năng tương thích tự động giống Protobuf.

## 10. Những lỗi dễ xảy ra và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `Metadata.Key.of(...)` không tạo được key | Dùng binary marshaller với tên không có `-bin`, hoặc ngược lại | Đặt đúng hậu tố và marshaller |
| Server nhận byte khác mong đợi | Client đã Base64 trước khi ghi binary metadata | Đưa byte gốc trực tiếp vào `put` |
| Chuỗi ASCII có dấu hoặc ký tự xuống dòng bị sai | Value không thuộc dạng ASCII hợp lệ | Dùng Protobuf `string` hoặc một quy ước mã hóa rõ ràng |
| `get(key)` trả về `null` | Key vắng mặt, tên key sai, interceptor không được gắn | Kiểm tra tên/loại key, phía gửi và cấu hình interceptor |
| Chỉ đọc được một trong nhiều value | Dùng `get` khi key được phép lặp | Dùng `getAll`, áp dụng chính sách số lượng value |
| Tác vụ chạy ở môi trường thử nhưng lỗi qua proxy | Proxy thay đổi/loại bỏ header hoặc giới hạn kích thước | Kiểm thử qua đúng đường đi triển khai, giảm metadata |
| Secret xuất hiện trong log | Log toàn bộ headers/trailers | Dùng allowlist key được log, che token và byte nhạy cảm |
| Giá trị bất ngờ thay đổi trong quá trình xử lý | Dùng lại mutable `byte[]` hoặc `Metadata` giữa các call | Sao chép byte cần giữ ổn định; tạo metadata theo từng call |

Thêm hai nguyên tắc an toàn:

1. **Không tin dữ liệu chỉ vì nó nằm trong metadata.** Client có thể tự đặt custom key; server vẫn cần kiểm tra định dạng, kích thước, quyền và tính xác thực khi thích hợp.
2. **Không nhầm Base64 với TLS hoặc mã hóa đầu cuối.** Binary metadata có thể bị đọc nếu vận chuyển không được bảo vệ. Tránh đặt bí mật trong thông điệp lỗi, log hoặc trace.

## 11. Kiểm thử ASCII và binary metadata

Có thể kiểm tra logic `Metadata` bằng unit test thuần Java, sau đó kiểm thử interceptor bằng in-process gRPC server/channel hoặc môi trường tích hợp Spring gRPC. Những kiểm thử liên quan TLS, proxy và giới hạn header cần thực hiện trên đường kết nối tương ứng vì in-process transport không mô phỏng toàn bộ hành vi HTTP/2.

Ví dụ một bài kiểm thử JUnit 5 cho thao tác dữ liệu cơ bản:

```java
import static org.junit.jupiter.api.Assertions.*;
import io.grpc.Metadata;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class MetadataTypesTest {
    @Test
    void asciiAndBinaryRoundTrip() {
        Metadata.Key<String> idKey =
            Metadata.Key.of(
                "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
        Metadata.Key<byte[]> dataKey =
            Metadata.Key.of(
                "x-data-bin", Metadata.BINARY_BYTE_MARSHALLER);

        byte[] original = {0x00, 0x7F, (byte) 0xFF};
        Metadata headers = new Metadata();
        headers.put(idKey, "req-42");
        headers.put(dataKey, original);

        assertEquals("req-42", headers.get(idKey));
        assertArrayEquals(original, headers.get(dataKey));
        assertTrue(headers.containsKey(dataKey));
    }
}
```

Khi kiểm thử tích hợp, nên có các trường hợp:

1. **ASCII hợp lệ:** client gửi `x-request-id`, server đọc đúng giá trị.
2. **Binary có byte đặc biệt:** gửi mảng chứa `0x00`, `0x7F`, `0xFF` và kiểm tra byte nhận về.
3. **Thiếu key:** server thực hiện đúng chính sách: dùng giá trị mặc định hoặc trả `INVALID_ARGUMENT`.
4. **Đa giá trị:** gửi key lặp, kiểm tra `get` và `getAll` không bị hiểu nhầm.
5. **Interceptor theo RPC:** hai lần gọi dùng chung stub vẫn thêm đúng metadata riêng từng lần.
6. **Kết thúc bằng lỗi:** client thu được status và, khi có, error metadata trong trailers.
7. **Qua proxy/TLS:** metadata vẫn được giữ đúng và không rò rỉ dữ liệu nhạy cảm trong log.
8. **Streaming:** headers không bị hiểu thành thông tin thay đổi theo từng message.

## 12. Bài tập vận dụng

Bạn xây dựng `RecommendationService` bằng Spring gRPC. Client cần gửi:

- Mã yêu cầu `"req-875"`.
- Phiên bản ứng dụng `"4.0.1"`.
- Bốn byte `{0x00, 0x10, 0x7F, 0xFF}` mô tả tính năng mà client hỗ trợ.
- Danh sách hàng trăm sản phẩm dùng làm đầu vào cho thuật toán.

**Yêu cầu thực hành:**

1. Chọn tên key ASCII cho mã yêu cầu và phiên bản client.
2. Chọn key có hậu tố `-bin` cho bốn byte, khai báo `Metadata.Key<byte[]>` và `BINARY_BYTE_MARSHALLER` tương ứng.
3. Viết đoạn tạo `Metadata`, gọi `put` và chứng minh `get` lấy lại đúng byte, kể cả `0xFF`.
4. Giải thích vì sao danh sách sản phẩm thuộc request message Protobuf, thay vì request headers.
5. Mô tả cách kiểm tra metadata khi server nhận yêu cầu và cách kiểm thử qua môi trường thực có proxy.

**Câu hỏi tự kiểm tra:**

- Hậu tố `-bin` quyết định điều gì?
- Vì sao `"AH//"` không nên được đưa vào binary metadata như byte ASCII nếu payload gốc là `00 7F FF`?
- `Metadata.get(...)` sẽ làm gì nếu key vắng mặt hoặc xuất hiện nhiều lần?
- Binary metadata có thể mang token nhạy cảm mà không cần TLS không?
- Khi streaming, dữ liệu thay đổi theo từng message nên đặt ở đâu?

**Ghi nhớ:** ASCII metadata phục vụ giá trị chuỗi ngắn; binary metadata giữ nguyên byte với key `-bin`. Cả hai cùng là metadata của *lời gọi RPC*, do `grpc-java` chuyển qua HTTP/2. Việc chọn đúng marshaller, giữ payload nhỏ, kiểm tra dữ liệu ở server và dùng TLS/credentials khi cần là nền tảng để triển khai metadata đáng tin cậy trong Spring gRPC.
