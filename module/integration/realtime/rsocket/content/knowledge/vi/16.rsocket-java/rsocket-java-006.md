# Tạo và đọc Payload bằng DefaultPayload hoặc ByteBufPayload

Trong RSocket Java, `Payload` là đối tượng mang nội dung của một thông điệp. Một payload có hai phần: **data** chứa dữ liệu chính của ứng dụng và **metadata** chứa thông tin bổ sung như route, xác thực hoặc ngữ cảnh tracing. Metadata có thể vắng mặt; nó không bắt buộc phải có trong mọi request.

RSocket Java cung cấp hai implementation thường dùng là `DefaultPayload` và `ByteBufPayload`. Cả hai đều tạo ra đối tượng có kiểu giao diện `io.rsocket.Payload`, nhưng khác nhau ở cách lưu dữ liệu và quản lý bộ nhớ. Chọn đúng implementation giúp mã dễ đọc ở luồng thông thường và kiểm soát tài nguyên tốt hơn ở luồng dùng Netty `ByteBuf`.

## 1. Cấu trúc Payload

Một payload có thể hình dung như sau:

```text
Payload
├── data      : byte[] / ByteBuffer / ByteBuf
└── metadata  : byte[] / ByteBuffer / ByteBuf (tùy chọn)
```

Hai phần được truyền dưới dạng byte. Ứng dụng quyết định cách mã hóa và diễn giải chúng. Ví dụ, data có thể là JSON UTF-8, protobuf hoặc nội dung nhị phân; metadata có thể là composite metadata chứa route và thông tin xác thực. Tên MIME type được khai báo trong bước `SETUP` để hai peer biết cách giải mã data và metadata.

Các phương thức quan trọng của `Payload`:

| Phương thức | Mục đích |
|---|---|
| `getDataUtf8()` | Đọc data thành chuỗi UTF-8 |
| `getMetadataUtf8()` | Đọc metadata thành chuỗi UTF-8 |
| `hasMetadata()` | Kiểm tra metadata có được cung cấp hay không |
| `sliceData()` | Lấy một `ByteBuf` view của data |
| `sliceMetadata()` | Lấy một `ByteBuf` view của metadata |
| `data()` / `metadata()` | Truy cập trực tiếp `ByteBuf` bên trong nếu có thể |
| `retain()` / `release()` | Quản lý vòng đời tham chiếu của payload |

`sliceData()` và `sliceMetadata()` luôn trả về một buffer, kể cả khi phần tương ứng rỗng. Dùng `hasMetadata()` để phân biệt metadata không tồn tại với metadata có tồn tại nhưng rỗng. Không nên chỉnh sửa trực tiếp buffer trả về từ `data()` hoặc `metadata()` vì có thể làm thay đổi nội dung mà payload đang quản lý.

## 2. Tạo Payload đơn giản bằng DefaultPayload

`DefaultPayload` phù hợp với mã ứng dụng cần tạo payload từ chuỗi, mảng byte hoặc `ByteBuffer` mà không phải thao tác trực tiếp với Netty. Các factory method trả về kiểu `Payload`, vì vậy phần còn lại của chương trình không cần phụ thuộc implementation cụ thể.

### Tạo data dạng chuỗi

```java
import io.rsocket.Payload;
import io.rsocket.util.DefaultPayload;

Payload payload = DefaultPayload.create("Xin chào RSocket");
```

Factory method nhận `CharSequence` mã hóa nội dung thành UTF-8. Nếu cần data và metadata dạng chuỗi:

```java
Payload payload = DefaultPayload.create(
    "Tìm đơn hàng ORD-1001",
    "route=orders.find"
);
```

Ví dụ trên chỉ minh họa hai vùng byte. Chuỗi `route=orders.find` chưa tự động trở thành routing metadata chuẩn của RSocket. Nếu muốn dùng routing extension, metadata phải được mã hóa đúng định dạng và MIME type tương ứng, chẳng hạn composite metadata.

### Tạo Payload từ dữ liệu nhị phân

```java
byte[] data = new byte[] { 0x01, 0x02, 0x03, 0x04 };
byte[] metadata = new byte[] { 0x10, 0x20 };

Payload payload = DefaultPayload.create(data, metadata);
```

`DefaultPayload.create(byte[])` và overload `ByteBuffer` giữ view của vùng dữ liệu đầu vào. Hãy xem mảng byte hoặc `ByteBuffer` đã đưa vào là bất biến trong thời gian payload được sử dụng; không sửa nội dung từ nơi khác sau khi tạo payload.

### Chỉ định charset

Nếu nội dung không dùng UTF-8, có thể chỉ định charset rõ ràng:

```java
Payload payload = DefaultPayload.create(
    "Xin chào",
    StandardCharsets.UTF_16LE,
    "ngôn-ngữ=vi",
    StandardCharsets.UTF_8
);
```

Hai phần data và metadata có thể dùng charset khác nhau. Hai peer phải thống nhất MIME type và quy ước mã hóa tương ứng; nếu không, byte vẫn truyền được nhưng bên nhận có thể giải mã sai ký tự.

## 3. Tạo Payload từ Netty ByteBuf bằng DefaultPayload

`DefaultPayload` cũng có overload nhận `ByteBuf`:

```java
ByteBuf data = Unpooled.buffer();
data.writeInt(42).writeCharSequence("RSocket", StandardCharsets.UTF_8);

Payload payload = DefaultPayload.create(data);
```

Điểm quan trọng: overload `DefaultPayload.create(ByteBuf)` sao chép phần byte có thể đọc sang vùng lưu trữ của `DefaultPayload`, rồi giải phóng `ByteBuf` đầu vào. Sau khi gọi factory, không tiếp tục dùng hoặc giải phóng `data` lần nữa. Nếu cần giữ buffer gốc để dùng ở nơi khác, hãy tạo một bản sao riêng trước khi chuyển nó vào factory.

Với metadata:

```java
ByteBuf data = Unpooled.copiedBuffer("hello", StandardCharsets.UTF_8);
ByteBuf metadata = Unpooled.copiedBuffer("trace=abc-123", StandardCharsets.UTF_8);

Payload payload = DefaultPayload.create(data, metadata);
```

Factory sẽ sao chép nội dung của cả hai buffer và giải phóng cả hai buffer đầu vào. Đây là lựa chọn đơn giản khi muốn có payload không phụ thuộc vòng đời của các `ByteBuf` ban đầu.

## 4. Tạo Payload bằng ByteBufPayload

`ByteBufPayload` lưu data và metadata dưới dạng Netty `ByteBuf`. Implementation này hữu ích khi ứng dụng đã làm việc với Netty buffer và muốn tránh bước sao chép không cần thiết. Nó dùng reference counting thực sự; khi số tham chiếu về 0, payload giải phóng các buffer bên trong.

Tạo payload từ chuỗi cũng rất ngắn:

```java
import io.rsocket.Payload;
import io.rsocket.util.ByteBufPayload;

Payload payload = ByteBufPayload.create("Xin chào RSocket");
Payload withMetadata = ByteBufPayload.create(
    "Tìm đơn hàng ORD-1001",
    "route=orders.find"
);
```

`ByteBufPayload` có các overload nhận `String`, `CharSequence` kèm charset, `byte[]`, `ByteBuffer` và `ByteBuf`. Với dữ liệu chuỗi, factory mặc định dùng UTF-8. Với `ByteBuf`, payload giữ trực tiếp buffer được truyền vào thay vì sao chép nội dung.

### Chuyển quyền sở hữu ByteBuf

Khi gọi `ByteBufPayload.create(data, metadata)`, quyền sở hữu hai buffer được chuyển cho payload. Payload sẽ gọi `release()` trên chúng khi chính payload được giải phóng. Vì vậy, sau khi tạo payload, không dùng hoặc giải phóng hai buffer gốc thêm lần nữa.

```java
ByteBuf data = Unpooled.buffer();
data.writeInt(1001);

ByteBuf metadata = Unpooled.buffer();
metadata.writeCharSequence("application=orders", StandardCharsets.UTF_8);

Payload payload = ByteBufPayload.create(data, metadata);
// Từ đây payload sở hữu data và metadata.
// Không gọi data.release() hoặc metadata.release() ở đây.
```

Nếu cần giữ một tham chiếu độc lập tới buffer sau khi chuyển quyền sở hữu, hãy tăng reference count trước khi tạo payload:

```java
ByteBuf data = Unpooled.copiedBuffer("shared", StandardCharsets.UTF_8);
data.retain(); // Giữ thêm một tham chiếu cho phía gọi.

Payload payload = ByteBufPayload.create(data);

// Khi payload được release, một tham chiếu được giải phóng.
// Phía gọi vẫn phải release tham chiếu mà mình giữ sau khi dùng xong.
```

Chỉ dùng `retain()` khi thực sự có hai chủ sở hữu với vòng đời độc lập. Giữ tham chiếu không cần thiết sẽ làm bộ nhớ không được thu hồi.

## 5. So sánh DefaultPayload và ByteBufPayload

| Tiêu chí | `DefaultPayload` | `ByteBufPayload` |
|---|---|---|
| Lưu trữ nội bộ | `ByteBuffer` | Netty `ByteBuf` |
| Tạo từ chuỗi | UTF-8 mặc định | UTF-8 mặc định |
| Tạo từ `byte[]` / `ByteBuffer` | Giữ view của vùng đầu vào | Bọc dữ liệu bằng `ByteBuf` |
| Tạo từ `ByteBuf` | Sao chép byte và giải phóng buffer đầu vào | Giữ trực tiếp buffer và nhận quyền sở hữu |
| Reference counting | `retain()` / `release()` không quản lý vòng đời thực; `refCnt()` luôn là 1 | Reference count thực, `release()` giải phóng buffer khi về 0 |
| Thread safety | Không thread-safe | `ByteBuf` bên trong cũng không nên được truy cập đồng thời nếu chưa đồng bộ |
| Phù hợp | Ví dụ, payload nhỏ, thao tác đơn giản | Luồng Netty, dữ liệu nhị phân và trường hợp cần kiểm soát buffer |

Không nên chọn `ByteBufPayload` chỉ vì tên gọi có vẻ tối ưu hơn. Lợi ích về sao chép và quản lý bộ nhớ chỉ có ý nghĩa khi ứng dụng quản lý đúng quyền sở hữu và reference count. Nếu chưa có nhu cầu thao tác trực tiếp với Netty buffer, `DefaultPayload` thường giúp mã dễ đọc hơn.

## 6. Đọc data và metadata dưới dạng chuỗi

Khi data và metadata là UTF-8, các phương thức tiện ích giúp đọc trực tiếp:

```java
void printPayload(Payload payload) {
    String data = payload.getDataUtf8();

    String metadata = payload.hasMetadata()
        ? payload.getMetadataUtf8()
        : "<không có metadata>";

    System.out.println("data = " + data);
    System.out.println("metadata = " + metadata);
}
```

`hasMetadata()` phân biệt metadata không được gửi với metadata được gửi nhưng có độ dài bằng 0. Nếu metadata dùng composite metadata, không thể chuyển toàn bộ vùng byte thành một chuỗi UTF-8 rồi mong đợi nhận được route hoặc token đã tách riêng. Khi đó phải dùng decoder tương ứng với định dạng metadata.

Đọc chuỗi không làm thay đổi reader index của `ByteBuf` gốc thông qua thao tác đọc thủ công. Với dữ liệu nhị phân, hãy kiểm soát rõ vị trí đọc và kích thước trước khi giải mã.

## 7. Đọc data nhị phân bằng ByteBuf

`sliceData()` trả về một view của phần data có thể đọc. View có reader index và writer index riêng nhưng chia sẻ vùng nhớ với buffer gốc. Đoạn mã sau đọc một số nguyên và phần byte còn lại:

```java
void readBinaryPayload(Payload payload) {
    ByteBuf data = payload.sliceData();

    if (data.readableBytes() < Integer.BYTES) {
        throw new IllegalArgumentException("Payload thiếu trường integer");
    }

    int orderId = data.readInt();
    byte[] remaining = new byte[data.readableBytes()];
    data.readBytes(remaining);

    System.out.println("orderId = " + orderId);
    System.out.println("remaining bytes = " + remaining.length);
}
```

`sliceData()` không tự tăng reference count. Vì vậy, chỉ sử dụng view trong khi payload gốc còn hợp lệ. Nếu cần chuyển dữ liệu sang một luồng bất đồng bộ hoặc lưu lại sau khi payload đã được giải phóng, hãy tạo bản sao bằng `copy()` hoặc lấy một retained slice và chịu trách nhiệm release nó sau khi hoàn tất.

Ví dụ giữ dữ liệu độc lập bằng bản sao:

```java
byte[] copyData(Payload payload) {
    ByteBuf view = payload.sliceData();
    byte[] copy = new byte[view.readableBytes()];
    view.getBytes(view.readerIndex(), copy);
    return copy;
}
```

`getBytes(index, destination)` không thay đổi reader index của view. Nếu dùng `readBytes(...)`, reader index của view sẽ tiến lên. Dùng `copy()` khi cần một `ByteBuf` độc lập thay vì một mảng byte.

## 8. Vòng đời và reference counting

`ByteBuf` của Netty và `ByteBufPayload` dùng reference count để xác định khi nào bộ nhớ có thể được thu hồi. Khi tạo một `ByteBuf` mới, reference count thường bắt đầu ở 1. `retain()` tăng số tham chiếu; `release()` giảm số tham chiếu. Khi về 0, buffer được giải phóng hoặc trả lại allocator/pool.

```java
ByteBuf buffer = Unpooled.buffer();
buffer.writeInt(7);

assert buffer.refCnt() == 1;
buffer.retain();
assert buffer.refCnt() == 2;

buffer.release();
assert buffer.refCnt() == 1;

buffer.release();
assert buffer.refCnt() == 0;
```

Với `ByteBufPayload`, payload quản lý buffer data và metadata. `payload.release()` giảm reference count của payload; khi về 0, `ByteBufPayload` giải phóng hai buffer bên trong. Không release cùng một tham chiếu hai lần. Truy cập buffer sau khi reference count về 0 có thể gây `IllegalReferenceCountException`.

`DefaultPayload` khác ở chỗ `refCnt()` trả về 1 và `retain()`/`release()` không thay đổi vòng đời bộ nhớ. Nội dung của nó được lưu bằng `ByteBuffer` và được thu hồi theo cơ chế garbage collection. Vì vậy, việc gọi `release()` trên `DefaultPayload` không thay thế cho việc quản lý `ByteBuf` mà bạn tự tạo bên ngoài.

## 9. PayloadDecoder.DEFAULT và ZERO_COPY khi đọc Payload nhận vào

RSocket Java cho phép cấu hình cách tạo `Payload` từ frame nhận được:

| Decoder | Cách xử lý | Trách nhiệm của ứng dụng |
|---|---|---|
| `PayloadDecoder.DEFAULT` | Sao chép data và metadata khỏi buffer frame | Không cần theo dõi/release buffer frame của payload nhận vào |
| `PayloadDecoder.ZERO_COPY` | Data và metadata là các retained slice của buffer frame | Phải release payload khi xử lý xong |

`DEFAULT` là mặc định của `RSocketConnector` và `RSocketServer` trong RSocket Java. `ZERO_COPY` có thể giảm sao chép và độ trễ, nhưng đổi lại ứng dụng phải kiểm soát chính xác vòng đời payload. Nếu giữ payload trong cache, đưa vào queue hoặc chuyển qua scheduler khác, cần retain/copy phù hợp và release đúng một lần.

Cấu hình decoder ở client và server:

```java
RSocketConnector connector = RSocketConnector.create()
    .payloadDecoder(PayloadDecoder.ZERO_COPY);

RSocketServer server = RSocketServer.create(acceptor)
    .payloadDecoder(PayloadDecoder.ZERO_COPY);
```

Chỉ bật `ZERO_COPY` khi tất cả đường xử lý payload nhận vào đã được rà soát ownership. Nếu một handler giữ `Payload` sau khi callback kết thúc mà không retain/copy, buffer có thể đã được giải phóng khi handler truy cập lại.

Ví dụ xử lý một response trong chế độ zero-copy:

```java
Mono<String> readResponse(RSocket socket) {
    Payload request = DefaultPayload.create("hello");

    return socket.requestResponse(request)
        .map(response -> {
            try {
                return response.getDataUtf8();
            }
            finally {
                response.release();
            }
        });
}
```

Khi dùng `PayloadDecoder.DEFAULT`, `release()` trên payload nhận vào không cần thiết cho việc thu hồi buffer của frame vì dữ liệu đã được sao chép. Đoạn mã vẫn có thể gọi `release()` an toàn với `DefaultPayload`, bởi `release()` của implementation này không làm giảm reference count. Khi dùng `ZERO_COPY`, `finally` đảm bảo payload được giải phóng cả khi đọc data phát sinh exception.

Với `Flux<Payload>`, cần giải phóng từng payload sau khi xử lý:

```java
Flux<String> messages = socket.requestStream(
        DefaultPayload.create("start"))
    .map(payload -> {
        try {
            return payload.getDataUtf8();
        }
        finally {
            payload.release();
        }
    });
```

Không giữ đối tượng `Payload` hoặc `ByteBuf` nhận vào trong biến dùng sau khi callback đã kết thúc nếu không retain/copy. Nếu chỉ cần chuỗi hoặc mảng byte, hãy chuyển đổi sang kiểu dữ liệu độc lập ngay trong thời gian payload còn hợp lệ.

## 10. Dùng Payload trong request-response

Ở mức API thấp của RSocket Java, `RSocket` nhận `Payload` và trả về `Mono<Payload>` cho request-response. Ví dụ phía client:

```java
RSocket client = /* RSocket đã kết nối */;

Mono<String> response = client
    .requestResponse(DefaultPayload.create(
        "ORD-1001",
        "operation=orders.find"
    ))
    .map(payload -> {
        try {
            return payload.getDataUtf8();
        }
        finally {
            payload.release();
        }
    });
```

Phía responder có thể đọc request và tạo response:

```java
RSocket responder = new AbstractRSocket() {
    @Override
    public Mono<Payload> requestResponse(Payload request) {
        String orderId;
        try {
            orderId = request.getDataUtf8();
        }
        finally {
            request.release();
        }

        return Mono.just(ByteBufPayload.create(
            "Đã nhận yêu cầu cho đơn " + orderId
        ));
    }
};
```

Trong ví dụ, payload đầu vào được đọc và release trong `finally`, phù hợp cả khi server bật `ZERO_COPY`. Response được tạo mới và trả cho RSocket runtime để gửi. Khi truyền payload vào API tương tác hoặc trả payload từ responder, hãy tuân theo ownership contract của RSocket API; không tiếp tục đọc hoặc release một payload đã chuyển quyền sở hữu cho runtime.

## 11. Các lỗi thường gặp khi tạo và đọc Payload

| Vấn đề | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Bên nhận đọc ra ký tự sai | Hai phía không thống nhất charset hoặc MIME type | Dùng UTF-8 nhất quán hoặc khai báo charset rõ ràng |
| Không đọc được route từ metadata | Metadata chỉ là chuỗi tùy ý, chưa mã hóa theo routing/composite metadata | Dùng encoder và MIME type metadata tương ứng |
| `IllegalReferenceCountException` | Dùng `ByteBuf`/payload sau khi đã release | Kiểm tra ownership, không dùng buffer sau khi release |
| Memory leak khi dùng ZERO_COPY | Quên release payload nhận vào | Release trong `finally` hoặc operator phù hợp |
| Buffer bị giải phóng quá sớm | Chuyển slice không retain sang xử lý bất đồng bộ | Dùng `retainedSlice()`/`retain()` hoặc copy độc lập |
| Double release | Cả bên tạo và bên nhận đều nghĩ mình sở hữu cùng một tham chiếu | Quy định rõ nơi chuyển quyền sở hữu và nơi release |
| Payload thay đổi ngoài ý muốn | Chia sẻ mảng byte hoặc buffer rồi sửa từ nơi khác | Coi vùng dữ liệu đầu vào là immutable hoặc tạo bản sao |

Một lưu ý riêng: `DefaultPayload.create(ByteBuf)` copy dữ liệu rồi release buffer đầu vào; `ByteBufPayload.create(ByteBuf)` giữ trực tiếp buffer và chuyển quyền sở hữu cho payload. Nhầm hai hành vi này dễ dẫn đến double release hoặc truy cập buffer đã bị giải phóng.

## 12. Checklist trước khi dùng Payload trong production

- [ ] Data và metadata có schema, charset và MIME type thống nhất giữa hai peer.
- [ ] Dùng `hasMetadata()` để phân biệt metadata vắng mặt và metadata rỗng.
- [ ] Dùng `getDataUtf8()`/`getMetadataUtf8()` cho nội dung UTF-8; dùng `ByteBuf` cho dữ liệu nhị phân.
- [ ] Không sửa trực tiếp vùng byte do payload sở hữu nếu không có chủ đích.
- [ ] Biết factory method đang copy, wrap hay nhận quyền sở hữu buffer.
- [ ] Với `ByteBufPayload`, mỗi `retain()` phải có một lần `release()` tương ứng.
- [ ] Không chuyển `sliceData()` hoặc `sliceMetadata()` sang xử lý bất đồng bộ khi chưa retain/copy.
- [ ] Với `PayloadDecoder.ZERO_COPY`, release payload nhận vào sau khi xử lý xong.
- [ ] Không release payload sau khi đã chuyển quyền sở hữu cho RSocket runtime.
- [ ] Kiểm tra bằng test dữ liệu rỗng, metadata không có, metadata rỗng, payload lớn và lỗi giải mã.

`DefaultPayload` giúp tạo payload nhanh từ các kiểu dữ liệu Java phổ biến. `ByteBufPayload` phù hợp khi làm việc trực tiếp với Netty và cần kiểm soát bộ nhớ ở mức thấp hơn. Dù chọn implementation nào, điều quan trọng là đọc đúng hai vùng data/metadata, thống nhất cách mã hóa và xác định rõ ai đang sở hữu từng buffer tại mỗi thời điểm.

## Tài liệu tham khảo

- [RSocket Java 1.1.5 — DefaultPayload API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/DefaultPayload.html)
- [RSocket Java 1.1.5 — ByteBufPayload API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/ByteBufPayload.html)
- [RSocket Java — DefaultPayload source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/util/DefaultPayload.java)
- [RSocket Java — ByteBufPayload source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/util/ByteBufPayload.java)
- [RSocket Java — PayloadDecoder và RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [Netty — Reference-counted objects](https://netty.io/wiki/reference-counted-objects.html)
