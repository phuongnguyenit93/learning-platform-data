# WellKnownMimeType và định danh kiểu metadata

Trong RSocket, payload có thể mang hai phần dữ liệu độc lập: **data** và **metadata**. Data thường chứa nội dung nghiệp vụ như một đối tượng `QuoteRequest`; metadata chứa thông tin giúp bên nhận hiểu cách định tuyến, xác thực, truy vết hoặc diễn giải payload. Cả hai phần đều được truyền dưới dạng byte, vì vậy hai phía cần thống nhất cách mã hóa.

MIME type là nhãn mô tả định dạng hoặc ý nghĩa của byte. RSocket truyền MIME type mặc định của data và metadata trong frame `SETUP`. Khi dùng Composite Metadata, mỗi mục metadata còn có MIME type riêng. `WellKnownMimeType` cung cấp các định danh ngắn cho những MIME type đã được chuẩn hóa trong phần mở rộng của RSocket, giúp biểu diễn chúng gọn hơn trong Composite Metadata.

## 1. Data MIME type và Metadata MIME type

RSocket phân biệt hai loại nội dung trong một payload:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Data | Nội dung chính của tương tác, thường là request hoặc response của nghiệp vụ. | JSON của `QuoteRequest`, bytes của ảnh hoặc dữ liệu nhị phân. |
| Metadata | Thông tin bổ sung đi kèm kết nối, request hoặc payload. | Route, thông tin xác thực, trace context, tenant hoặc phiên bản schema. |

Trong frame `SETUP`, bên khởi tạo kết nối công bố hai MIME type độc lập:

- `dataMimeType` mô tả cách diễn giải phần data, ví dụ `application/json` hoặc `application/cbor`.
- `metadataMimeType` mô tả định dạng của phần metadata. Nếu dùng Composite Metadata, giá trị thường là `message/x.rsocket.composite-metadata.v0`.

MIME type không phải nội dung và cũng không tự thực hiện serialization. Nó chỉ cho biết byte tiếp theo cần được hiểu theo định dạng nào. Nếu bên gửi mã hóa JSON nhưng bên nhận lại giải mã như CBOR, việc trao đổi vẫn có thể thành công ở tầng transport nhưng dữ liệu không thể được diễn giải đúng.

Ví dụ, một payload có thể chứa JSON ở phần data và nhiều mục metadata với định dạng khác nhau:

```text
SETUP
  dataMimeType     = application/json
  metadataMimeType = message/x.rsocket.composite-metadata.v0

PAYLOAD
  data
    { "symbol": "ACME" }
  metadata (Composite Metadata)
    message/x.rsocket.routing.v0       -> quotes.latest
    application/vnd.acme.trace+json    -> { "traceId": "trace-123" }
    message/x.rsocket.authentication.v0 -> thông tin xác thực
```

`metadataMimeType` ở đây mô tả toàn bộ vùng metadata là một danh sách mục Composite Metadata. MIME type nằm trong từng mục mới mô tả định dạng của giá trị metadata tương ứng.

## 2. Well-known MIME type là gì?

Một MIME type thông thường được truyền dưới dạng chuỗi, chẳng hạn `application/json`. Để giảm kích thước metadata, RSocket định nghĩa một bảng MIME type phổ biến có định danh số trong phạm vi từ `0` đến `127`. Đây là **well-known MIME types**.

Trong Java, thư viện RSocket cung cấp enum `io.rsocket.metadata.WellKnownMimeType` để ánh xạ giữa:

- Tên hằng enum trong mã nguồn, ví dụ `APPLICATION_JSON`.
- Chuỗi MIME type, ví dụ `application/json`.
- Định danh số được dùng trong header Composite Metadata.

Một số giá trị thường gặp:

| Hằng enum | MIME type | Công dụng thường gặp |
|---|---|---|
| `APPLICATION_JSON` | `application/json` | Nội dung JSON. |
| `APPLICATION_CBOR` | `application/cbor` | Nội dung CBOR. |
| `APPLICATION_OCTET_STREAM` | `application/octet-stream` | Dữ liệu nhị phân tổng quát. |
| `TEXT_PLAIN` | `text/plain` | Văn bản thuần. |
| `MESSAGE_RSOCKET_COMPOSITE_METADATA` | `message/x.rsocket.composite-metadata.v0` | Định dạng bao ngoài cho nhiều mục metadata. |
| `MESSAGE_RSOCKET_ROUTING` | `message/x.rsocket.routing.v0` | Metadata định tuyến. |
| `MESSAGE_RSOCKET_AUTHENTICATION` | `message/x.rsocket.authentication.v0` | Metadata xác thực. |
| `MESSAGE_RSOCKET_TRACING_ZIPKIN` | `message/x.rsocket.tracing-zipkin.v0` | Metadata truy vết theo định dạng Zipkin. |

Danh sách trên chỉ là những loại tiêu biểu. Bảng chuẩn còn có các MIME type cho nhiều định dạng dữ liệu và loại nội dung khác. Hãy tham chiếu bảng của phiên bản thư viện/giao thức đang sử dụng thay vì tự gán một số ID cho MIME type.

Well-known MIME type là quy ước của RSocket, không phải một serializer riêng. Ví dụ, `APPLICATION_JSON` giúp hai phía nhận diện chuỗi `application/json`; encoder và decoder vẫn phải chịu trách nhiệm chuyển đối tượng Java thành JSON bytes và ngược lại.

## 3. Tra cứu định danh trong Java

`WellKnownMimeType` cung cấp các phương thức để tra cứu theo MIME type string hoặc theo identifier:

```java
import io.rsocket.metadata.WellKnownMimeType;

WellKnownMimeType json =
    WellKnownMimeType.fromString("application/json");

if (json == WellKnownMimeType.UNPARSEABLE_MIME_TYPE) {
    throw new IllegalArgumentException("Unsupported MIME type");
}

String mimeType = json.getString();
byte identifier = json.getIdentifier();

WellKnownMimeType decoded =
    WellKnownMimeType.fromIdentifier(Byte.toUnsignedInt(identifier));

assert decoded == WellKnownMimeType.APPLICATION_JSON;
```

Các phương thức chính:

| Phương thức | Chức năng |
|---|---|
| `fromString(String)` | Tìm enum tương ứng với chuỗi MIME type đã biết. |
| `fromIdentifier(int)` | Tìm enum tương ứng với identifier từ `0` đến `127`. |
| `getString()` | Lấy chuỗi MIME type chuẩn mà enum đại diện. |
| `getIdentifier()` | Lấy identifier dạng `byte`; giá trị hợp lệ nằm trong khoảng không âm `0` đến `127`. |

Không dùng `ordinal()` của enum làm identifier giao thức. `ordinal()` phụ thuộc thứ tự khai báo hằng enum trong một bản thư viện; `getIdentifier()` mới là giá trị được định nghĩa cho wire format. Tương tự, `name()` trả tên hằng Java như `APPLICATION_JSON`, không trả MIME type string; hãy dùng `getString()` khi cần chuỗi MIME type.

### Hai trạng thái tra cứu cần phân biệt

`WellKnownMimeType` có hai giá trị đặc biệt đáng chú ý:

- `UNPARSEABLE_MIME_TYPE`: chuỗi không khớp với một well-known MIME type, hoặc identifier nằm ngoài phạm vi hợp lệ. Một MIME type tùy chỉnh như `application/vnd.acme.trace+json` có thể trả về giá trị này dù chuỗi đó vẫn là MIME type hợp lệ trong ứng dụng.
- `UNKNOWN_RESERVED_MIME_TYPE`: identifier nằm trong phạm vi `0` đến `127` nhưng được dành riêng hoặc chưa được phiên bản thư viện hiện tại nhận diện.

Vì vậy, kết quả `UNPARSEABLE_MIME_TYPE` từ `fromString()` không có nghĩa metadata tùy chỉnh là sai. Nó chỉ cho biết MIME type đó không nằm trong bảng well-known mà enum hiện tại biết. Trong Composite Metadata, MIME type tùy chỉnh có thể được ghi dưới dạng chuỗi tường minh.

Khi gặp identifier đã được dành riêng nhưng chưa biết, một decoder có thể giữ lại identifier và nội dung gốc để chuyển tiếp hoặc xử lý ở tầng phù hợp. Không tự diễn giải một identifier chưa biết thành một MIME type khác.

## 4. Composite Metadata cho phép nhiều kiểu metadata

Nếu metadata của một kết nối chỉ dùng một định dạng duy nhất, MIME type metadata trong `SETUP` có thể chỉ thẳng đến định dạng đó. Nhưng trong ứng dụng thực tế, một request có thể cần đồng thời route, thông tin xác thực và trace context. Composite Metadata giải quyết việc này bằng cách đóng gói nhiều mục metadata trong cùng một vùng metadata.

MIME type của vùng đóng gói là:

```text
message/x.rsocket.composite-metadata.v0
```

Mỗi mục bên trong có MIME type và nội dung riêng. Các mục được nối liên tiếp, không cần một cấu trúc JSON chung để chứa tất cả. Nhờ đó, route có thể dùng định dạng routing của RSocket, authentication dùng định dạng xác thực, còn metadata riêng của ứng dụng có thể dùng JSON hoặc CBOR.

```text
Composite Metadata
┌─────────────────────┬─────────────────────┬─────────────────────┐
│ Entry 1             │ Entry 2             │ Entry 3             │
│ routing MIME        │ authentication MIME │ custom trace MIME   │
│ route bytes         │ auth bytes          │ trace JSON bytes    │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

Mỗi mục có thể dùng một well-known MIME type hoặc một MIME type tùy chỉnh được mã hóa tường minh. Thứ tự các mục là thứ tự xuất hiện trong vùng metadata; bên nhận cần đọc hết vùng này để tìm những loại metadata mà ứng dụng quan tâm.

## 5. Cấu trúc một mục Composite Metadata trên wire

Một mục Composite Metadata gồm phần header xác định MIME type, trường độ dài nội dung và các byte nội dung:

```text
+----------------------+--------------------------+----------------------+
| MIME header          | Metadata length          | Metadata content     |
| 1 byte, có thể thêm  | 3 bytes, unsigned,       | số byte theo length  |
| MIME string          | big-endian               |                      |
+----------------------+--------------------------+----------------------+
```

Byte đầu tiên của MIME header dùng bit cao nhất để phân biệt hai cách mã hóa:

| Bit cao nhất | 7 bit còn lại | Các byte tiếp theo |
|---|---|---|
| `1` | Well-known MIME identifier, từ `0` đến `127`. | Không có MIME string; trường độ dài nội dung 3 byte theo sau ngay. |
| `0` | Độ dài MIME string trừ đi `1`. | MIME string được mã hóa bằng US-ASCII, rồi đến trường độ dài nội dung 3 byte. |

Với MIME type tùy chỉnh, cách mã hóa độ dài trừ một cho phép biểu diễn chuỗi từ 1 đến 128 byte trong 7 bit. MIME string không có byte kết thúc NUL. Với well-known MIME type, bit cao nhất được bật và 7 bit còn lại chính là identifier đã đăng ký.

Trường độ dài metadata gồm 3 byte unsigned theo thứ tự big-endian. Giá trị này cho biết số byte của nội dung mục metadata, không bao gồm header MIME type và chính trường độ dài. Sau nội dung, mục kế tiếp bắt đầu ngay nếu còn byte trong vùng Composite Metadata.

Ví dụ minh họa cấu trúc một mục dùng well-known MIME type:

```text
+--------------------------+-------------------------+-------------------+
| 1xxxxxxx                 | length[23:16]           |                   |
| bit 7 = 1                | length[15:8]            | metadata content  |
| 7 bit = MIME identifier  | length[7:0]             |                   |
+--------------------------+-------------------------+-------------------+
```

Với MIME type tùy chỉnh, phần đầu thay bằng byte có bit cao nhất bằng `0`, theo sau là chuỗi MIME ASCII có độ dài được mã hóa trong byte đầu. Trường độ dài nội dung 3 byte vẫn có cùng ý nghĩa.

Một vùng Composite Metadata có thể chứa nhiều mục liên tiếp:

```text
┌───────────────────── Composite Metadata ─────────────────────┐
│ MIME header │ 3-byte length │ content │ MIME header │ ...     │
└───────────────────────────────────────────────────────────────┘
```

Decoder phải đọc header trước, xác định đó là identifier hay MIME string, sau đó đọc đúng 3 byte độ dài và lấy chính xác số byte nội dung. Không thể tách các mục bằng dấu phẩy, dấu xuống dòng hay ký tự phân cách tự chọn.

## 6. MIME type tùy chỉnh và khả năng tương thích

Không phải metadata nào cũng có trong bảng well-known. Ứng dụng có thể định nghĩa MIME type riêng, ví dụ:

```text
application/vnd.acme.trace-context+json
application/vnd.acme.tenant+json
application/vnd.acme.schema-version
```

MIME type tùy chỉnh cần tuân thủ một quy ước ổn định và được cấu hình giống nhau ở hai phía. Khi đưa vào Composite Metadata, sender mã hóa MIME string tường minh thay vì tự gán một well-known identifier.

Trong `rsocket-core`, `CompositeMetadataCodec` có overload nhận `String` cho MIME type tùy chỉnh và overload nhận `WellKnownMimeType` cho loại đã biết. `encodeAndAddMetadataWithCompression(...)` có thể kiểm tra chuỗi MIME type; nếu khớp bảng well-known thì dùng identifier rút gọn, nếu không thì mã hóa MIME string tường minh.

```java
// Minh họa lựa chọn kiểu MIME trước khi ghi một metadata entry.
WellKnownMimeType type = WellKnownMimeType.fromString(mimeType);

if (type == WellKnownMimeType.UNPARSEABLE_MIME_TYPE) {
    // MIME type tùy chỉnh: ghi MIME string tường minh.
    CompositeMetadataCodec.encodeAndAddMetadata(
        compositeMetadata, allocator, mimeType, metadataBytes);
} else {
    // Well-known MIME type: ghi identifier rút gọn.
    CompositeMetadataCodec.encodeAndAddMetadata(
        compositeMetadata, allocator, type, metadataBytes);
}
```

Đoạn code trên minh họa lựa chọn overload của codec; trong ứng dụng thật, cần tạo và quản lý `ByteBuf` đúng vòng đời, giải phóng buffer sau khi không còn sử dụng và bảo đảm nội dung `metadataBytes` được serialize đúng theo MIME type đã khai báo.

Một số nguyên tắc khi thiết kế MIME type tùy chỉnh:

1. Dùng tên có ý nghĩa và phiên bản rõ ràng nếu cấu trúc metadata có thể thay đổi.
2. Chọn một định dạng nội dung thống nhất, ví dụ JSON hoặc CBOR, và dùng encoder/decoder tương ứng ở cả hai phía.
3. Không tái sử dụng MIME type chuẩn của RSocket cho cấu trúc dữ liệu riêng của ứng dụng.
4. Không tự cấp identifier trong dải well-known `0` đến `127`; hãy dùng MIME string tường minh cho kiểu tùy chỉnh.
5. Kiểm tra tương thích khi nâng cấp thư viện, vì một identifier được dành riêng có thể được một phiên bản mới nhận diện với ý nghĩa đã đăng ký.

## 7. Sử dụng MIME type trong Spring RSocket

Spring RSocket thường dùng Composite Metadata mặc định để một request có thể mang nhiều cặp MIME type và giá trị metadata. Trong phần lớn ứng dụng, không cần thay đổi metadata MIME type của requester. Nếu cấu hình kết nối thủ công, có thể chỉ định rõ MIME type của data và metadata:

```java
MimeType compositeMimeType = MimeType.valueOf(
    WellKnownMimeType.MESSAGE_RSOCKET_COMPOSITE_METADATA.getString());

RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(compositeMimeType)
    .tcp("localhost", 7000);
```

`dataMimeType` ở ví dụ là JSON; `metadataMimeType` là định dạng bao ngoài Composite Metadata. Bên server cần hiểu cùng định dạng metadata và có decoder cho những MIME type ứng dụng gửi.

### Gửi metadata tùy chỉnh

Giả sử ứng dụng cần gửi trace context cùng request lấy báo giá:

```java
MimeType traceMimeType = MimeType.valueOf(
    "application/vnd.acme.trace-context+json");

Mono<Quote> quote = requester
    .route("quotes.latest")
    .metadata(new TraceContext("trace-123"), traceMimeType)
    .data(new QuoteRequest("ACME"))
    .retrieveMono(Quote.class);
```

`route(...)` tạo routing metadata theo cơ chế của Spring RSocket. Lời gọi `metadata(...)` thêm một mục metadata khác với MIME type tùy chỉnh. Để serialize `TraceContext`, requester phải có encoder phù hợp với MIME type đó.

### Đọc metadata ở phía server

`DefaultMetadataExtractor` cho phép đăng ký MIME type và kiểu Java tương ứng. Ví dụ:

```java
DefaultMetadataExtractor extractor =
    new DefaultMetadataExtractor(metadataDecoders);

extractor.metadataToExtract(
    traceMimeType,
    TraceContext.class,
    "traceContext");
```

Sau khi extractor được gắn vào cấu hình `RSocketStrategies` của responder, ứng dụng có thể đọc giá trị đã giải mã bằng tên `traceContext` trong handler, chẳng hạn thông qua `@Header("traceContext")`. Decoder phải tương thích với encoder ở requester. Spring có hỗ trợ sẵn cho `message/x.rsocket.routing.v0` và ánh xạ route vào key `route`; những MIME type khác cần được đăng ký theo nhu cầu.

Không nên giả định việc gửi metadata object tự động khiến server biết kiểu Java tương ứng. Hai phía cần thống nhất MIME type, cấu trúc byte và decoder.

## 8. Phân biệt MIME type của metadata với MIME type của từng mục

Một nhầm lẫn phổ biến là dùng `application/json` làm `metadataMimeType` của kết nối rồi lại gửi Composite Metadata chứa nhiều mục. Hai cách cấu hình này mô tả hai định dạng khác nhau:

| Cấu hình | Ý nghĩa |
|---|---|
| `metadataMimeType = application/json` | Toàn bộ vùng metadata được diễn giải như một tài liệu JSON theo cấu hình đơn giản. |
| `metadataMimeType = message/x.rsocket.composite-metadata.v0` | Vùng metadata là một chuỗi các mục; mỗi mục tự khai báo MIME type. |
| Một entry có MIME type `application/json` bên trong Composite Metadata | Chỉ nội dung của entry đó được diễn giải theo JSON. |

Nếu peer mong đợi Composite Metadata nhưng nhận metadata được mã hóa như một tài liệu JSON đơn, decoder sẽ đọc sai cấu trúc ngay từ byte đầu. Ngược lại, nếu peer mong đợi một MIME type đơn nhưng nhận một chuỗi Composite Metadata, peer không thể tự suy ra cách tách từng mục.

Hãy đồng bộ `metadataMimeType` ở thời điểm thiết lập kết nối và cách serialize metadata của từng request. `dataMimeType` vẫn độc lập với cả hai lựa chọn này.

## 9. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Dùng `ordinal()` làm MIME identifier. | Thứ tự enum Java không phải định danh trên wire. | Dùng `getIdentifier()` và `fromIdentifier()`. |
| Dùng `name()` khi cần MIME string. | `name()` trả tên enum như `APPLICATION_JSON`. | Dùng `getString()` để lấy `application/json`. |
| Coi `UNPARSEABLE_MIME_TYPE` là MIME type tùy chỉnh không hợp lệ. | Enum chỉ tra cứu bảng well-known, không bao gồm mọi MIME type của ứng dụng. | Mã hóa MIME type tùy chỉnh dưới dạng chuỗi tường minh. |
| Tự gán identifier cho MIME type riêng. | Dải ID well-known thuộc bảng chuẩn của RSocket. | Chọn MIME string riêng và đăng ký encoder/decoder. |
| Chỉ cấu hình decoder cho data nhưng quên metadata. | Data và metadata có MIME type, encoder/decoder độc lập. | Cấu hình metadata encoder ở requester và metadata extractor/decoder ở responder. |
| Dùng sai `metadataMimeType` trong `SETUP`. | Hai peer không thống nhất metadata đơn hay Composite Metadata. | Đồng bộ cấu hình kết nối; dùng `message/x.rsocket.composite-metadata.v0` nếu gửi nhiều mục. |
| Đọc sai độ dài entry. | Trường độ dài nội dung là 3 byte unsigned big-endian, còn MIME header có hai cách mã hóa. | Để codec RSocket xử lý; nếu tự viết parser, kiểm tra từng ranh giới trước khi đọc buffer. |
| Không xử lý identifier chưa biết. | Peer có thể nhận một identifier đã dành riêng nhưng thư viện chưa hỗ trợ. | Giữ nguyên thông tin thô nếu cần chuyển tiếp; không tự diễn giải thành loại khác. |
| Gửi token hoặc dữ liệu nhạy cảm rồi ghi log toàn bộ metadata. | Metadata có thể chứa thông tin xác thực hoặc định danh nhạy cảm. | Che giá trị nhạy cảm trong log và dùng transport bảo mật; MIME type không mã hóa hay xác thực nội dung. |

## 10. Kiểm thử và chẩn đoán

Khi kiểm tra metadata, nên xác minh cả tên MIME type, identifier và nội dung sau khi decode.

**Kiểm tra ánh xạ well-known:**

```java
WellKnownMimeType type =
    WellKnownMimeType.fromString("message/x.rsocket.routing.v0");

assert type == WellKnownMimeType.MESSAGE_RSOCKET_ROUTING;
assert WellKnownMimeType.fromIdentifier(
    Byte.toUnsignedInt(type.getIdentifier())) == type;
```

**Kiểm tra MIME type tùy chỉnh:**

```java
String customMime = "application/vnd.acme.trace-context+json";

assert WellKnownMimeType.fromString(customMime)
    == WellKnownMimeType.UNPARSEABLE_MIME_TYPE;
```

Assertion thứ hai là kết quả mong đợi: MIME type tùy chỉnh không nằm trong bảng well-known, nhưng vẫn có thể dùng trong Composite Metadata nếu cả hai phía hiểu nó.

Khi đọc packet capture hoặc log:

1. Xác định `metadataMimeType` đã được công bố trong `SETUP`.
2. Nếu là Composite Metadata, đọc bit cao nhất của MIME header để biết entry dùng identifier hay MIME string.
3. Với well-known entry, tra identifier bằng bảng chuẩn hoặc `WellKnownMimeType.fromIdentifier()`.
4. Với custom entry, đọc đúng độ dài MIME string và giải mã US-ASCII.
5. Đọc 3 byte độ dài nội dung theo big-endian, rồi lấy đúng số byte metadata.
6. Kiểm tra encoder và decoder của MIME type đó ở hai phía có cùng quy ước hay không.

Không nên log toàn bộ buffer metadata ở môi trường production nếu nó có thể chứa token xác thực, dữ liệu cá nhân hoặc trace baggage nhạy cảm. Hãy log tên MIME type, kích thước, route và correlation ID đã được phép ghi nhận; che hoặc loại bỏ giá trị bí mật.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/) — cấu trúc frame, `SETUP`, data và metadata.
- [Spring Framework: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — `RSocketRequester`, Composite Metadata và `MetadataExtractor`.
- [RSocket Core 1.1.5: WellKnownMimeType](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/metadata/WellKnownMimeType.html) — enum, tra cứu MIME type và identifier.
- [RSocket Core 1.1.0: CompositeMetadataCodec](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.0/io/rsocket/metadata/CompositeMetadataCodec.html) — encode/decode các mục Composite Metadata.

## Kết luận

MIME type cho biết cách diễn giải byte của data hoặc metadata. `WellKnownMimeType` ánh xạ các MIME type chuẩn của RSocket sang identifier nhỏ gọn từ `0` đến `127`, còn Composite Metadata cho phép nhiều mục với định dạng độc lập cùng tồn tại trong một payload. Khi triển khai, hãy đồng bộ MIME type ở `SETUP`, dùng `getIdentifier()` thay cho `ordinal()`, mã hóa MIME type tùy chỉnh dưới dạng chuỗi tường minh và đăng ký decoder tương ứng ở phía nhận. Những quy tắc này giúp các peer Java/Spring Boot và các implementation RSocket khác nhau trao đổi metadata nhất quán qua TCP hoặc WebSocket.
