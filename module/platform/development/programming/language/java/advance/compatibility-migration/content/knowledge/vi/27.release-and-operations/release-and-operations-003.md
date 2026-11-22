# Chạy song song phiên bản cũ và mới với hợp đồng dữ liệu chung

Một đợt nâng cấp Java hoặc framework hiếm khi được triển khai đồng thời trên toàn bộ hệ thống. Trong quá trình **rolling deployment**, **canary release** hoặc **blue–green deployment**, nhiều instance của phiên bản cũ và mới có thể cùng phục vụ traffic, cùng đọc/ghi cơ sở dữ liệu, cùng trao đổi message và cùng dùng cache. Nếu phiên bản mới thay đổi định dạng dữ liệu mà phiên bản cũ không hiểu, hệ thống có thể hoạt động bình thường trong vài phút đầu rồi thất bại khi request đến một instance cũ, khi một message được retry hoặc khi cần rollback.

Để tránh tình huống đó, hai phiên bản phải có **hợp đồng dữ liệu chung** (*shared data contract*) trong **khoảng thời gian cùng tồn tại**. Hợp đồng không nhất thiết yêu cầu hai bản dùng cùng một class Java hoặc cùng một mô hình database nội bộ. Nó yêu cầu hai bản có thể **tạo, đọc và diễn giải chính xác dữ liệu mà bản kia có thể phát sinh** trong cửa sổ triển khai được cam kết, đồng thời duy trì bất biến nghiệp vụ và khả năng khôi phục.

Bài học thuộc chương **Phát hành và vận hành** của module **Java Advance Compatibility Migration**. Trọng tâm là thiết kế một đợt nâng cấp Java/JDK/framework mà **old và new có thể chạy song song an toàn**, từ hợp đồng API/message/schema, database expand–migrate–contract đến traffic routing, contract testing, monitoring và rollback.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao rolling/canary/blue–green tạo ra trạng thái **mixed-version**.
- Phân biệt tính tương thích khi **đọc dữ liệu cũ** và khi **đọc dữ liệu mới**; không đánh đồng chúng.
- Xác định một hợp đồng dữ liệu chung theo schema, kiểu, ngữ nghĩa, default, validation và protocol version.
- Thiết kế thay đổi schema tiến hóa: thêm trường tùy chọn, trì hoãn trường bắt buộc, giữ nguyên field IDs và xử lý giá trị chưa biết.
- Áp dụng chiến lược **expand → migrate → contract** cho cơ sở dữ liệu được nhiều phiên bản cùng truy cập.
- Tránh sai lầm dual-write, cache serialization, session affinity, shadow traffic gây side effect và message consumer incompatibility.
- Viết ma trận kiểm thử producer–consumer hai chiều và kiểm chứng các tổ hợp old/new.
- Thiết lập readiness, canary metrics, feature flags, rollback gate và quy trình loại bỏ tương thích tạm thời.
- Kết nối rủi ro mixed-version với thay đổi JDK, Jakarta, JSON framework, ORM, JDBC, timezone/charset và serialization.

## 2. Vì sao hệ thống xuất hiện hai phiên bản đồng thời?

### 2.1. Rolling deployment

Một cluster có bốn instance, lần lượt thay instance cũ bằng instance mới:

```text
Trước deploy:    [OLD] [OLD] [OLD] [OLD]
Bước 1:         [NEW] [OLD] [OLD] [OLD]
Bước 2:         [NEW] [NEW] [OLD] [OLD]
Bước 3:         [NEW] [NEW] [NEW] [OLD]
Sau deploy:     [NEW] [NEW] [NEW] [NEW]
```

Trong các bước 1–3, request có thể đến cả old và new. Nếu hai phiên bản còn dùng chung database, queue hoặc cache, tác động không chỉ nằm ở traffic routing mà còn nằm ở **dữ liệu được chia sẻ qua thời gian**.

### 2.2. Canary release

Một phần nhỏ traffic được chuyển sang bản mới:

```text
                  +----------------> OLD (95%)
Client -> Router -|
                  +----------------> NEW (5%)
```

Canary nhằm đo khả năng tương thích trước khi mở rộng. Nhưng nếu NEW ghi dữ liệu mà OLD không đọc được, chỉ **5% request đi qua NEW** vẫn có thể gây hỏng cho 95% instance OLD khi chúng đọc cùng dữ liệu đó.

### 2.3. Blue–green deployment

Có hai môi trường ứng dụng:

```text
Blue:  OLD instances
Green: NEW instances
```

Có thể chuyển traffic bằng router hoặc DNS. Nhưng hai môi trường vẫn có thể dùng chung database/message broker. Khi đó blue–green **không có nghĩa dữ liệu đã được cô lập**.

Nếu dùng hai database riêng, cần giải bài toán đồng bộ và reconciliation trước khi switch; đừng mặc định dual-write hai nơi là một phép triển khai an toàn.

### 2.4. Rollback cũng tạo mixed-version

Một rollout đã đạt 80% NEW rồi phát hiện lỗi và chuyển traffic về OLD. Lúc này, **NEW có thể đã ghi dữ liệu mới** vào database/queue/cache. OLD cần đọc được dữ liệu đó hoặc rollout không thực sự rollback được.

Vì vậy, câu hỏi quan trọng không chỉ là “NEW có đọc được dữ liệu cũ không?” mà còn là:

> **“Sau khi NEW ghi dữ liệu, OLD có tiếp tục hoạt động đúng nếu traffic quay về không?”**

Đó là điều kiện cốt lõi của rollback-safe migration.

## 3. Hợp đồng dữ liệu chung là gì?

Hợp đồng dữ liệu là tập quy tắc mà các producer, consumer và storage layers cùng tuân theo. Nó bao gồm nhiều hơn một file JSON Schema hoặc bảng database.

Một hợp đồng nên mô tả:

| Thành phần | Ví dụ nội dung cần thống nhất |
| --- | --- |
| Định danh | `orderId` là chuỗi ổn định, không được tái sử dụng cho đơn khác. |
| Kiểu dữ liệu | `amountMinor` là số nguyên đơn vị nhỏ nhất của tiền tệ, không phải floating point. |
| Required/optional | `currency` là optional trong giai đoạn song song; default được định nghĩa rõ. |
| Null và vắng mặt | Thiếu trường, `null` và chuỗi rỗng có cùng nghĩa hay không? |
| Enum và trạng thái | Giá trị mới có thể được consumer cũ xử lý an toàn không? |
| Thời gian | Timestamp là UTC/offset-aware, precision và timezone được quy định. |
| Charset | Text/wire format thống nhất UTF-8 khi protocol áp dụng. |
| Ràng buộc nghiệp vụ | Không charge hai lần; transition của order status hợp lệ. |
| Quy tắc schema evolution | Additive trước, không xóa/rename khi còn consumer cũ. |
| Protocol/version | Có cần version ở header/envelope/topic/endpoint không? |
| Ordering/idempotency | Event có ID ổn định; retry/replay không gây duplicate effect. |
| Error semantics | Khi gặp field/enum không biết, consumer làm gì? |
| Giới hạn tương thích | Cam kết N và N−1 hay nhiều phiên bản hơn; trong bao lâu? |

Hợp đồng phải được phản ánh trong **consumer behavior thực tế**. Có một schema “đẹp” nhưng serializer của OLD ném lỗi khi gặp trường mới thì vẫn không tương thích.

## 4. Hai hướng tương thích: backward và forward

### 4.1. Định nghĩa theo reader và writer

Trong migration, để tránh tranh luận về thuật ngữ, hãy xác định rõ **ai viết và ai đọc**:

- **NEW reader đọc OLD writer:** dữ liệu đã tồn tại hoặc tiếp tục do OLD phát sinh phải được NEW hiểu.
- **OLD reader đọc NEW writer:** dữ liệu được NEW tạo ra trong rollout/rollback phải được OLD hiểu.

Sơ đồ:

```text
                OLD writer                 NEW writer
                     |                          |
                     v                          v
                Data schema V1             Data schema V2
                     |                          |
          +----------+-----------+  +-----------+----------+
          |                      |  |                      |
          v                      v  v                      v
      OLD reader              NEW reader              OLD reader
      (baseline)           (backward read)          (forward read)
```

Trong những hệ schema-registry phổ biến, **backward compatibility** thường nói tới reader mới đọc dữ liệu do writer cũ tạo, còn **forward compatibility** nói tới reader cũ đọc dữ liệu do writer mới tạo. Một số hệ dùng quy tắc hoặc tên gọi khác; luôn kiểm tra definition trong schema registry/protocol đang sử dụng.

### 4.2. Bốn tổ hợp quan trọng

| Producer | Consumer | Ý nghĩa |
| --- | --- | --- |
| OLD | OLD | Baseline, phải ổn định trước khi nâng. |
| OLD | NEW | NEW đọc được dữ liệu lịch sử và producer cũ. |
| NEW | OLD | OLD còn hoạt động khi NEW bắt đầu phát dữ liệu; cực kỳ quan trọng với rollback. |
| NEW | NEW | Chức năng đích hoạt động đúng. |

Một build chỉ test NEW–NEW chưa đủ để phát hành mixed-version.

### 4.3. Khả năng đọc không đồng nghĩa diễn giải đúng

Ví dụ OLD không lỗi khi đọc một event mới:

```json
{
  "orderId": "O-123",
  "status": "PARTIALLY_REFUNDED"
}
```

Nhưng nếu OLD chỉ biết `NEW`, `PAID` và `CANCELLED`, nó có thể:

- Ném exception khi deserialize enum.
- Gán default không an toàn.
- Hiểu nhầm là đơn đã hủy.
- Bỏ qua sự kiện, làm số dư không nhất quán.

Vì vậy, **“parser không crash” chỉ là điều kiện đầu tiên**. Còn phải đảm bảo consumer hành xử đúng với những giá trị mà writer mới có thể phát sinh.

## 5. Quy tắc tiến hóa schema an toàn trong giai đoạn song song

### 5.1. Ưu tiên thay đổi cộng thêm

Hợp đồng ban đầu:

```json
{
  "orderId": "O-123",
  "status": "PAID"
}
```

Phiên bản mới muốn bổ sung tiền tệ:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

Thay đổi này **có thể tương thích** nếu:

1. NEW chấp nhận payload cũ thiếu `currency` với ngữ nghĩa fallback hợp lệ.
2. OLD chấp nhận hoặc bỏ qua trường chưa biết theo contract.
3. NEW không phát một giá trị mà OLD sẽ hiểu sai.
4. Tất cả đường encode/decode thực tế, kể cả cache/message, được kiểm thử.

Không nên khẳng định “thêm trường JSON luôn backward compatible”. Ví dụ Jackson POJO có thể ném lỗi đối với unknown properties nếu cấu hình hoặc annotation không cho phép bỏ qua.

### 5.2. Không thêm required field ngay lập tức

Nếu NEW yêu cầu:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

và validator mới đánh dấu `currency` là bắt buộc, những record do OLD tạo vẫn không có field đó. NEW reader cần chịu được dữ liệu cũ trong giai đoạn chuyển tiếp hoặc phải có bước backfill đáng tin cậy **trước** khi áp yêu cầu.

Một lộ trình an toàn hơn:

1. Thêm field ở trạng thái optional/nullable.
2. NEW reader biết đọc khi field có hoặc không có.
3. OLD reader được kiểm tra với field mới.
4. NEW writer bắt đầu ghi field mới trong contract cho phép.
5. Backfill dữ liệu lịch sử.
6. Chỉ sau khi không còn OLD writer và dữ liệu đã đầy đủ mới xét chuyển field thành required.

### 5.3. Phân biệt missing, null và empty

Ba payload có thể không cùng nghĩa:

```json
{}
```

```json
{"customerName": null}
```

```json
{"customerName": ""}
```

Một mapper có thể dùng default khi field vắng mặt nhưng giữ `null` khi field hiện diện; một validator khác có thể từ chối cả null lẫn empty. Khi thay Jackson/JSON-B/framework, cần thử từng trường hợp và thống nhất semantics.

### 5.4. Đừng đổi kiểu dữ liệu tại chỗ

Không an toàn khi một field từng là số nguyên:

```json
{"amount": 120000}
```

nay thành object:

```json
{"amount": {"value": 120000, "currency": "VND"}}
```

OLD parser có thể không đọc được. Giải pháp thường là **thêm field mới** và giữ field cũ trong cửa sổ chuyển tiếp:

```json
{
  "amount": 120000,
  "amountDetail": {
    "minorUnits": 120000,
    "currency": "VND"
  }
}
```

Hãy quy định rõ hai field có thể cùng tồn tại thì field nào là nguồn chính và cách phát hiện bất nhất. Không để hai field cùng ghi độc lập mà không có quy tắc đồng bộ.

### 5.5. Thay tên field phải đi qua giai đoạn dual-read

Đổi `customerName` thành `displayName` bằng cách xóa field cũ ngay là một breaking change.

Lộ trình có thể là:

```text
V1:  customerName
       |
       v
V2:  reader hiểu cả customerName và displayName
     writer vẫn ghi customerName (hoặc ghi cả hai khi an toàn)
       |
       v
V3:  tất cả reader đã hiểu displayName
     writer bắt đầu chọn displayName làm chuẩn
       |
       v
V4:  sau khi hết cửa sổ rollback, bỏ customerName
```

**Cảnh báo:** “dual-write” hai field trong cùng record phải đảm bảo chúng nhất quán. Nếu OLD writer chỉ cập nhật field cũ, NEW reader đọc field mới ưu tiên có thể thấy giá trị cũ bị stale. Cần có giai đoạn xác định nguồn dữ liệu authoritative rõ ràng.

### 5.6. Giá trị enum mới là breaking change tiềm ẩn

Nếu NEW thêm trạng thái `ON_HOLD`, OLD có thể không biết xử lý. Giải pháp tùy nghiệp vụ:

- Trì hoãn việc phát giá trị mới đến khi OLD consumer đã rời hệ thống.
- Reader hỗ trợ unknown values và đưa vào trạng thái quarantine.
- Dùng versioned event/endpoint riêng.
- Thiết kế một trạng thái fallback **an toàn** nếu contract cho phép.

Không tự chuyển giá trị chưa biết thành `PAID`, `SUCCESS` hoặc trạng thái nghiệp vụ có side effect chỉ để tránh exception.

## 6. JSON contract với Java: đọc version cũ và mới

### 6.1. Mô hình không phụ thuộc trực tiếp vào class nội bộ

Giả sử contract wire có:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

NEW có thể nhận payload từ OLD không có `currency`. Một ví dụ Java dùng Jackson `JsonNode`, không dựa vào việc deserialize trực tiếp enum:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderWireReader {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static OrderMessage read(String json) throws Exception {
        JsonNode root = MAPPER.readTree(json);

        JsonNode idNode = root.get("orderId");
        JsonNode statusNode = root.get("status");

        if (idNode == null || !idNode.isTextual()
                || statusNode == null || !statusNode.isTextual()) {
            throw new IllegalArgumentException(
                    "orderId/status missing or invalid");
        }

        String id = idNode.asText();
        String status = statusNode.asText();

        // V1 thiếu currency; giá trị fallback chỉ hợp lệ
        // nếu contract cũ đã bảo đảm toàn bộ đơn là VND.
        JsonNode currencyNode = root.get("currency");
        String currency;

        if (currencyNode == null || currencyNode.isNull()) {
            currency = "VND";
        } else if (currencyNode.isTextual()) {
            currency = currencyNode.asText();
        } else {
            throw new IllegalArgumentException("Invalid currency");
        }

        return new OrderMessage(id, status, currency);
    }

    public static final class OrderMessage {
        public final String orderId;
        public final String status;
        public final String currency;

        public OrderMessage(String orderId, String status, String currency) {
            this.orderId = orderId;
            this.status = status;
            this.currency = currency;
        }
    }
}
```

Đây là ví dụ minh họa đọc payload V1/V2 theo một contract rất cụ thể. **Default `VND` chỉ đúng nếu dữ liệu lịch sử thật sự luôn dùng VND**; nếu không, fallback này làm sai tiền tệ và phải thay bằng quy trình xác định currency theo nguồn dữ liệu khác.

### 6.2. Đừng suy luận default từ sự thuận tiện

Một số fallback có thể biến lỗi thiếu dữ liệu thành sai số nghiêm trọng:

```text
Thiếu currency -> ngầm coi VND
Thiếu tenantId -> ngầm dùng tenant mặc định
Thiếu authScope -> ngầm cấp quyền đầy đủ
Thiếu timezone -> ngầm hiểu local timezone của server
```

Chỉ dùng default khi nó là một phần **có bằng chứng** của contract V1. Với dữ liệu không thể diễn giải an toàn, cần reject hoặc quarantine kèm metric và khả năng xử lý lại.

### 6.3. Kiểm tra cấu hình serializer thực tế

Với Jackson, JSON-B, Gson hoặc serializer khác, có thể khác nhau về:

- Unknown property policy.
- Null/default và primitive conversion.
- Enum unknown handling.
- Date/time format.
- Naming strategy.
- Polymorphic typing.
- Record/class constructor.
- Validation annotations.
- Java module reflection access.

Nâng framework/JDK đôi khi thay transitive serializer version. Hãy kiểm tra **effective dependency version và ObjectMapper configuration**, không chỉ JSON fixture.

### 6.4. Tránh wire format phụ thuộc trực tiếp vào tên class Java

Ví dụ không nên dùng lâu dài:

```json
{
  "@class": "com.example.orders.internal.OrderEntity",
  "id": 123
}
```

Khi refactor package, shading, nâng framework hoặc module hóa, FQCN có thể thay đổi. Một contract wire tốt nên dùng schema identifier ổn định như `eventType`, `schemaVersion` hoặc loại DTO được quản lý, không để consumer phải nạp class tùy ý từ payload.

Cách này cũng giảm rủi ro bảo mật của polymorphic deserialization không kiểm soát.

## 7. Hợp đồng API HTTP khi old và new phục vụ song song

### 7.1. Request cũ đến new

NEW phải chấp nhận request format mà client và các service khác đang gửi, trừ khi API endpoint/version được thay đổi có chủ đích.

Ví dụ OLD cho phép:

```json
{"customerId":"C-7"}
```

NEW muốn thêm `locale`. Trong mixed-version rollout, NEW cần hỗ trợ request thiếu `locale` hoặc cung cấp endpoint mới đã versioned.

### 7.2. Response mới đến client cũ

Ngay cả khi OLD và NEW cùng nằm sau router, client cũ có thể nhận response từ NEW. Nếu client từ chối unknown fields, đổi shape hoặc enum values, canary có thể làm client lỗi.

Bảng kiểm tra:

| Thay đổi response | Rủi ro |
| --- | --- |
| Thêm optional field | Thường an toàn nếu client bỏ qua field lạ; phải test. |
| Xóa field | Client cũ có thể crash hoặc mất dữ liệu. |
| Đổi kiểu của field | Deserialize fail hoặc logic sai. |
| Đổi tên field | Tương đương xóa field cũ đối với client chưa cập nhật. |
| Thêm enum/status mới | Client cũ có thể không xử lý được. |
| Đổi HTTP status/header | Proxy/client retry, cache và error handling có thể khác. |
| Đổi pagination/order | Client có thể bỏ sót hoặc lặp item. |
| Đổi auth/session cookie | Client hoặc instance cũ có thể không xác thực được. |

### 7.3. Versioned API có thể phù hợp hơn compatibility shim

Nếu thay đổi lớn không thể giữ tương thích, có thể cung cấp song song:

```text
/api/v1/orders    -- contract cũ
/api/v2/orders    -- contract mới
```

Hoặc chọn protocol/schema version trong media type/header theo chuẩn của hệ thống. Điều quan trọng là **client có biết chọn phiên bản và router/server có giữ đúng contract không**.

Không coi việc thêm `/v2` là giải pháp tự động cho shared database/message: backend vẫn cần contract dữ liệu phù hợp.

### 7.4. Authentication và session

Trong rolling deployment, người dùng có thể đăng nhập qua OLD rồi request tiếp theo đến NEW. Cần kiểm tra:

- JWT claims được cả hai bản hiểu.
- Session token/cookie format và encryption key.
- Shared session store serializer.
- CSRF token và state.
- API gateway header behavior.
- Redirect/URL/cookie SameSite/Domain.
- Key rotation và thời gian sống token.

Nếu NEW phát token mà OLD không xác minh được, một rollback hoặc request sang OLD có thể khiến người dùng đăng xuất hàng loạt.

## 8. Message broker và event schema khi producer/consumer lệch phiên bản

### 8.1. Producer và consumer không nâng cùng lúc

Trong hệ thống dùng Kafka, RabbitMQ hoặc message bus khác:

```text
OLD Producer ----\
                  >---- Topic / Queue ----> OLD Consumer
NEW Producer ----/                  \
                                     ---> NEW Consumer
```

Có thể tồn tại **message đã phát trước deploy**, message từ NEW producer trong canary và message được retry sau rollback.

Vì vậy consumer cần biết xử lý các payload có thể tồn tại trong retention window, không chỉ payload của phiên bản vừa được deploy.

### 8.2. Event envelope ổn định

Một dạng event envelope minh họa:

```json
{
  "eventId": "e-8f21",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-10-15T09:30:00Z",
  "orderId": "O-123",
  "amountMinor": 120000,
  "currency": "VND"
}
```

Những field như `eventId` và `schemaVersion` giúp idempotency và version handling, nhưng **chỉ thêm schemaVersion mà không triển khai logic xử lý version thì chưa đủ**.

Cần quy định:

- Event ID duy nhất và ổn định qua retries.
- Event type/version.
- Semantic của field, null/default.
- Key/partition và ordering trong phạm vi được broker bảo đảm.
- Retention/replay và thời hạn tương thích.
- Cách xử lý unknown schema/field.
- Dead-letter/quarantine khi không thể xử lý an toàn.

### 8.3. Additive schema không luôn đủ

Với JSON, khả năng bỏ qua unknown field tùy decoder. Với Avro hoặc Protobuf, schema evolution có quy tắc riêng về field types, tags/field numbers, default values và reader/writer compatibility.

Không được dùng một quy tắc chung “thêm field là an toàn” cho mọi định dạng.

Ví dụ với Protobuf, **không tái sử dụng số field đã xóa**; cần dùng cơ chế `reserved` khi loại field để tránh message cũ bị diễn giải sai khi số field được dùng cho ý nghĩa mới. Với Avro, cần kiểm tra quy tắc schema resolution và giá trị default của reader/writer phù hợp.

Nếu dùng Schema Registry, chọn compatibility policy theo đúng rollout pattern: backward, forward, full và các chế độ transitive có mục đích khác nhau tùy hệ thống. Một policy cho phép producer/consumer mới cùng làm việc chưa chắc cho phép rollback về consumer cũ.

### 8.4. Trì hoãn phát event type mới

Một chiến lược an toàn:

1. Deploy consumer có thể **đọc** event type/field mới nhưng chưa dùng.
2. Kiểm chứng OLD và NEW consumer cùng chạy được.
3. Deploy producer có khả năng phát event mới nhưng giữ feature flag off.
4. Chờ tất cả consumer quan trọng được nâng.
5. Bật emission của event mới.
6. Theo dõi lỗi và chỉ xóa fallback khi hết retention/rollback window.

Đây là thứ tự **reader trước writer** cho những thay đổi schema không thể được consumer cũ xử lý an toàn.

### 8.5. Không trộn “consumer cũ” với “message cũ”

Một consumer mới phải có khả năng đọc message được sản xuất nhiều giờ/ngày trước, tùy retention. Mặt khác, nếu rollback về OLD consumer, nó có thể nhận message mới từ NEW producer.

Vì vậy test cần có cả:

- OLD payload fixture → NEW decoder.
- NEW payload fixture → OLD decoder.
- Replay với event order/retry.
- Unknown fields và enum values.
- Batch có message V1/V2 xen kẽ.

## 9. Database: expand–migrate–contract

### 9.1. Vấn đề khi OLD và NEW cùng database

Đây là tình huống dễ làm rollback nguy hiểm:

```text
          OLD instances -----+
                             |
                             v
                          Database
                             ^
                             |
          NEW instances -----+
```

Nếu NEW ngay lập tức rename/drop một cột mà OLD vẫn truy cập, OLD có thể lỗi SQL. Nếu NEW tăng ràng buộc `NOT NULL` nhưng OLD chưa ghi field đó, OLD có thể không insert/update được.

Database change cần được triển khai theo thứ tự **không phá các writers/readers còn sống**.

### 9.2. Expand: thay đổi schema theo hướng cộng thêm

Giả sử bảng ban đầu:

```sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL
);
```

NEW muốn dùng tên chuẩn `customer_display_name`. Thay vì rename cột ngay:

```sql
ALTER TABLE orders
    ADD COLUMN customer_display_name VARCHAR(255);
```

Trong pha expand:

- OLD tiếp tục đọc/ghi `customer_name`.
- NEW phải đọc được record chưa có field mới.
- Không ép `customer_display_name NOT NULL` ngay nếu OLD writer chưa cập nhật.
- Index/constraint mới phải được đánh giá về lock, workload và migration thời gian dài.

SQL minh họa theo hệ quan hệ tương thích; cú pháp migration và locking behavior phụ thuộc database/version cụ thể.

### 9.3. Migrate: backfill có kiểm soát

Ví dụ:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE customer_display_name IS NULL;
```

Lệnh minh họa logic backfill, **không phải khuyến nghị chạy một transaction khổng lồ trên production**. Với bảng lớn, cần batch, checkpoint, rate limit, monitoring và đánh giá lock/replication lag theo database thực tế.

Quan trọng hơn, **OLD writer vẫn có thể tiếp tục cập nhật `customer_name`**. Nếu NEW đọc `customer_display_name` ưu tiên mà cột này không được cập nhật đồng bộ, NEW có thể đọc giá trị stale.

Có vài phương án:

- Giữ `customer_name` làm nguồn dữ liệu authoritative trong pha mixed-version, NEW ưu tiên đọc nó và ghi cả hai khi phù hợp.
- Dùng migration/trigger hoặc application compatibility layer có quy tắc đồng bộ được kiểm chứng để giữ hai cột nhất quán, nếu database và hệ thống cho phép.
- Trì hoãn thay đổi nguồn authoritative đến khi tất cả OLD writers đã rút khỏi hệ thống.
- Dùng cơ chế version hoặc timestamp để phát hiện tranh chấp nếu data model yêu cầu.

Không áp dụng **dual-write ngây thơ** rồi mặc định hai bản dữ liệu luôn giống nhau.

### 9.4. Contract: xóa cột cũ cuối cùng

Chỉ sau khi:

1. Không còn OLD binary/OLD writer sử dụng cột cũ.
2. Không còn job batch, worker, report, script và tool vận hành cũ.
3. NEW đã sử dụng nguồn dữ liệu mới ổn định.
4. Backfill hoàn tất và được đối chiếu.
5. Cửa sổ rollback về OLD đã kết thúc hoặc có đường rollback khác.
6. Backup/restore và migration plan được phê duyệt.

...mới cân nhắc loại cột cũ:

```sql
ALTER TABLE orders DROP COLUMN customer_name;
```

Đây là một thay đổi **contract** có thể không đảo ngược đơn giản. Đừng thực hiện trong cùng release với bước thêm cột nếu còn khả năng rollback về ứng dụng cũ.

### 9.5. Luồng mẫu

```text
Release A (OLD đang chạy)
  |
  v
DB expand: thêm cột nullable, giữ cột cũ
  |
  v
Release B: NEW có dual-read; writer vẫn bảo toàn contract cũ
  |
  v
Backfill + theo dõi sai lệch và concurrent writes
  |
  v
Rolling/canary NEW; OLD và NEW cùng chạy
  |
  v
Tất cả OLD readers/writers rút khỏi hệ thống
  |
  v
Chuyển nguồn authoritative theo policy và kiểm chứng
  |
  v
Hết rollback/retention window
  |
  v
DB contract: bỏ cột/API cũ ở release sau
```

Trình tự cụ thể phải được điều chỉnh theo schema, dữ liệu thực và migration tool. Nguyên tắc không đổi là **không xóa ranh giới mà OLD đang dựa vào khi OLD còn có thể chạy**.

## 10. Dual-write: phân biệt những mô hình khác nhau

### 10.1. Dual-write hai cột trong một transaction

NEW ghi cả cột cũ và mới vào cùng một database transaction có thể bảo đảm chúng được commit cùng nhau, nhưng OLD writer vẫn chỉ biết cột cũ. Vì vậy, không đủ chỉ sửa NEW.

Trong mixed-version, phải xác định:

- Ai được phép ghi dữ liệu?
- Field nào là authoritative?
- OLD có thể ghi sau NEW hay không?
- Làm thế nào khi cập nhật hai chiều?
- Có thể mất cập nhật khi backfill chạy đồng thời?
- Reader chọn field theo quy tắc nào?

### 10.2. Dual-write sang hai hệ thống độc lập

Ví dụ ứng dụng ghi đồng thời database và Kafka:

```text
Application
   ├── write Database
   └── publish Event
```

Nếu database commit thành công nhưng publish thất bại, hai hệ thống không nhất quán. Nếu publish trước rồi database rollback, consumer có thể thấy event không tương ứng state thực.

Đây là bài toán **atomicity qua hai hệ thống**, không giải quyết được bằng cách gọi hai API liên tiếp rồi retry vô điều kiện.

Một giải pháp thường dùng là **transactional outbox**:

```text
Trong một DB transaction:
  - Update order
  - Insert outbox event
             |
             v
Commit
             |
             v
Outbox dispatcher/CDC publish tới broker
             |
             v
Consumer xử lý idempotent theo eventId
```

Outbox vẫn cần retry, xử lý event trùng và monitoring; nó không tự bảo đảm exactly-once end-to-end cho mọi side effect.

### 10.3. Dual-read không đồng nghĩa dual-write

Có thể cần NEW đọc được cả field cũ và mới, nhưng **chưa được phép ghi format mới** trong cửa sổ rollback. Đây thường là một trạng thái rollout an toàn hơn.

Hãy phân tách feature flags hoặc release steps:

- Can read V1?
- Can read V2?
- Can write V2?
- Can remove V1?

Phương án “reader trước, writer sau” giảm rủi ro NEW phát format mà OLD chưa chấp nhận.

## 11. Shared cache, distributed session và serialized objects

### 11.1. Cache format là một data contract

OLD và NEW có thể cùng sử dụng Redis, Memcached hoặc distributed cache. Một entry do NEW ghi có thể được OLD đọc sau đó.

Ví dụ OLD lưu:

```json
{"id":"U-7","roles":["USER"]}
```

NEW thêm:

```json
{"id":"U-7","roles":["USER"],"permissions":["orders:read"]}
```

Nếu OLD không hiểu `permissions`, có thể lỗi hoặc bỏ qua. Nhưng nguy hiểm hơn là NEW đọc cache cũ và **ngầm cấp quyền mặc định** khi field mới thiếu. Contract cache phải xử lý đủ hai hướng và đặc biệt chú ý security semantics.

### 11.2. Không dùng Java native serialization làm hợp đồng liên phiên bản nếu tránh được

`ObjectOutputStream` có thể chứa thông tin class name, `serialVersionUID` và cấu trúc object. Khi nâng class, refactor package, thay JDK/framework hoặc đổi class loader, một object serialized cũ có thể không deserialize được.

Đối với cache/session chia sẻ nhiều phiên bản, ưu tiên định dạng được quản lý bằng schema ổn định (JSON/Protobuf/Avro với policy rõ) hoặc dùng cache namespace versioned có kế hoạch chuyển tiếp.

Không coi việc giữ `serialVersionUID` giống nhau là đủ bảo đảm mọi thay đổi class đều tương thích.

### 11.3. Versioned cache keys

Có thể dùng:

```text
user-profile:v1:<id>
user-profile:v2:<id>
```

Điều này cô lập định dạng, nhưng có chi phí:

- Hai bản có thể bị stale khác nhau.
- Cache invalidation phải xử lý cả v1/v2.
- Hit rate và bộ nhớ có thể thay đổi.
- Rollback cần v1 cache hoặc khả năng rebuild.
- Không được dùng v2 như nguồn dữ liệu authoritative mà v1 không thấy.

Versioned keys là một lựa chọn, không thay thế cho data consistency design.

### 11.4. Session stickiness chỉ giải quyết một phần

Ghim session tới một phiên bản có thể giảm lỗi client trực tiếp, nhưng không đảm bảo:

- Background jobs dùng cùng database.
- Event consumers khác phiên bản.
- Shared Redis/session store.
- Failover sang instance khác.
- Rollback giữa phiên.
- Queue chứa message do phiên bản mới phát.

Do đó sticky routing không phải bằng chứng có shared data contract an toàn.

## 12. Java và framework migration làm contract thay đổi như thế nào?

### 12.1. JDK không tự thay wire schema, nhưng ảnh hưởng implementation

Nâng JDK có thể kéo theo khác biệt ở:

- Mặc định charset của một số Java APIs.
- Date/time, timezone database hoặc locale data.
- TLS/security providers.
- Java serialization/class loading.
- Reflection/module access.
- Library/driver được nâng để hỗ trợ JVM mới.

Một message có JSON không đổi nhưng timestamp parse khác, timezone khác hoặc encoding bị hiểu sai vẫn gây behavioral incompatibility.

### 12.2. UTF-8 và dữ liệu tiếng Việt

Từ Java 18, JEP 400 chuẩn hóa default charset UTF-8 cho nhiều API Java SE thuộc phạm vi áp dụng. Nếu OLD từng ghi file text bằng charset nền tảng khác nhưng NEW đọc bằng UTF-8, dữ liệu có thể bị biến dạng.

Trong mixed-version, dữ liệu file/export là một contract: chỉ chuyển sang UTF-8 khi các producer/consumer liên quan đã thống nhất encoding nguồn/đích, có kiểm thử byte fixture và quy trình xử lý dữ liệu legacy.

Đối với wire protocol HTTP/JSON, dùng encoding theo chuẩn giao thức và contract của consumer; không suy ra mọi bên tự động xử lý đúng chỉ vì JVM có default UTF-8.

### 12.3. Jackson, JSON-B và serializer upgrades

Khi nâng Spring Boot, Jakarta EE hoặc JSON library, các giá trị mặc định có thể khác về date/time, enum, unknown field và null handling. Vì vậy cùng một DTO source có thể tạo byte JSON khác.

Cần dùng **golden fixtures** để so contract tại byte/field/semantic level, và test reader/writer old/new. Không chỉ so `toString()` của Java object.

### 12.4. ORM và Jakarta migration

Chuyển từ thế hệ `javax.persistence` sang `jakarta.persistence` là thay đổi API/framework, nhưng shared database vẫn phải đáp ứng schema contract. Hai phiên bản ORM có thể khác:

- Type mapping và SQL dialect.
- Default schema generation behavior.
- Identifier generation.
- Enum mapping.
- Precision của timestamp/numeric.
- Lazy loading và transaction semantics.

Nếu OLD và NEW ORM cùng đọc/ghi một bảng, cần test dữ liệu thực và câu SQL quan trọng, tránh vô tình bật một cơ chế auto-update/drop schema trong production trong lúc rolling deployment.

### 12.5. Module path và serialization framework

JPMS có thể yêu cầu `opens` cho framework deep reflection. NEW chạy trên module path có thể deserialize fail trong khi OLD chạy classpath vẫn thành công.

Phải kiểm tra runtime module access của serializer/ORM. Không tự thêm `--add-opens` trên toàn bộ JDK để sửa mọi lỗi; ưu tiên library version phù hợp và mở đúng package nếu cần.

## 13. Feature flags và thứ tự bật khả năng mới

### 13.1. Tách “deploy code” khỏi “activate behavior”

Một phiên bản NEW có thể được triển khai nhưng vẫn **viết format V1**. Điều này giúp quan sát code mới trước khi phát data format mới.

Ví dụ các feature flags:

```text
read_schema_v2 = true
write_schema_v2 = false
emit_new_status = false
use_new_database_column = false
```

Sau khi đủ readers hỗ trợ format mới, mới bật `write_schema_v2` theo kế hoạch.

Flags cần có owner, default rõ, trạng thái theo môi trường và lịch loại bỏ để tránh nhánh logic tương thích tồn tại vô thời hạn.

### 13.2. Reader trước writer

Một trình tự phù hợp với nhiều thay đổi additive:

1. Deploy reader NEW biết đọc V1/V2 nhưng vẫn ghi V1.
2. Xác minh mixed readers cùng hoạt động.
3. Nâng các consumer phụ thuộc.
4. Bật writer V2 với phạm vi nhỏ khi OLD readers đã an toàn hoặc đã rút khỏi hệ thống.
5. Theo dõi lỗi và rollback có giới hạn.
6. Loại bỏ V1 sau retention/rollback window.

Không áp dụng một cách máy móc nếu contract đòi thay đổi đồng thời để bảo đảm an toàn. Nhưng đây là **một nguyên tắc sắp xếp quan trọng** giúp tránh dữ liệu mới bị consumer cũ đọc sai.

### 13.3. Flag phải nhất quán qua nhiều instance

Nếu NEW instance A bật V2 writer còn NEW instance B chưa bật, shared DB/message có thể chứa cả hai format. Các readers cần chuẩn bị cho điều đó hoặc flag cần được điều phối tập trung theo kế hoạch.

Đừng giả định đổi config trên một pod sẽ đồng thời đổi mọi pod. Ghi lại thời điểm/phiên bản flag được kích hoạt để đối chiếu với lỗi dữ liệu.

## 14. Traffic routing, canary và shadow traffic

### 14.1. Canary không chỉ đo HTTP 200

Các chỉ số nên theo dõi riêng OLD và NEW:

- 4xx/5xx và lỗi nghiệp vụ.
- p50/p95/p99 latency.
- Deserialization/validation failures.
- Database errors và schema constraint violations.
- Event processing lag, DLQ, retry counts.
- Duplicate side effects và idempotency conflicts.
- Cache/session failures.
- CPU, heap, GC, connection-pool saturation.
- Metrics bảo mật: auth failures, permission mismatch.
- Version distribution theo request/job/consumer.

Một canary 5% có HTTP success rate tốt nhưng liên tục tạo message không đọc được bởi OLD consumer vẫn phải bị chặn.

### 14.2. Shadow traffic có rủi ro side effect

*Shadow traffic* là bản sao request thực gửi tới NEW để quan sát behavior mà không đưa response NEW cho client:

```text
Client ---> OLD (phản hồi chính)
             \
              \-- copy --> NEW (shadow, response không trả client)
```

Nếu NEW shadow xử lý **ghi database, charge payment, publish event hoặc gửi email**, request có thể gây side effect hai lần. **Không được nhân bản request ghi thật một cách vô điều kiện.**

Cách xử lý tùy use case:

- Shadow chỉ các endpoint read-only phù hợp.
- Dùng sandbox/dataset cô lập.
- Disable side effects bằng cơ chế được kiểm chứng.
- Thay external gateways bằng stubs ở môi trường kiểm thử.
- Nếu cần so sánh write behavior, dùng replay có kiểm soát trên dữ liệu cô lập.

Ngay cả GET có thể gây side effect gián tiếp như update last-access, rate limit hoặc cache write. Cần kiểm tra thực tế.

### 14.3. Gắn version metadata để quan sát

Có thể thêm application version vào structured logs/traces/metrics, ví dụ:

```text
app.version=old-1.8.4
app.version=new-2.0.0
schema.read=v1
schema.write=v1
```

Đối với event, đưa version vào envelope nếu contract cho phép. Với database, dùng audit/versioning phù hợp để truy nguồn bản ghi khi có sự cố.

Tránh đưa dữ liệu cá nhân nhạy cảm vào logs chỉ để debug compatibility.

### 14.4. Health, readiness và draining

Khi rolling deployment:

- NEW chỉ nhận traffic khi đã qua readiness checks quan trọng.
- OLD cần dừng nhận request mới trước khi shutdown.
- In-flight requests và background jobs phải có chính sách drain/cancel.
- Consumer group rebalancing và message acknowledgments được xử lý đúng.
- Scheduler không tạo duplicate job khi cả OLD và NEW cùng active.

Một service HTTP đã hết traffic chưa chắc **mọi worker nền** của phiên bản cũ đã dừng.

## 15. Tác vụ nền, scheduler và idempotency

### 15.1. Khi cả old và new cùng chạy job định kỳ

Nếu cả hai phiên bản cùng chứa scheduled job:

```text
OLD job scheduler ----> phát hóa đơn 00:00
NEW job scheduler ----> phát hóa đơn 00:00
```

Hai job có thể cùng chạy và phát hóa đơn hai lần. Đó là lỗi **coordination**, không đơn thuần là lỗi schema.

Cần một trong những cơ chế phù hợp:

- Leader election.
- Distributed lock/lease có timeout và fencing nếu cần.
- Một scheduler tập trung.
- Job assignment/cutover rõ ràng.
- Idempotency key hoặc unique constraint ở nơi ghi side effect.
- Tách deployment role: HTTP workers, consumers, schedulers.

Distributed lock một mình không luôn đủ bảo đảm exactly-once side effect, nhất là khi lease hết hạn nhưng worker cũ vẫn thực hiện thao tác. Cần kiểm tra fencing/transaction/idempotency theo bài toán.

### 15.2. Event replay và duplicate processing

Trong mixed-version, consumer có thể rebalance hoặc retry một message. Nếu code OLD và NEW có logic xử lý khác nhau, cần bảo đảm kết quả cuối cùng đúng.

Ví dụ bảng deduplication:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Một consumer có thể dùng unique key và transaction phù hợp để quản lý xử lý trùng. Tuy nhiên, cần thiết kế **phạm vi consumer_name và side effect** đúng: nếu OLD và NEW dùng hai tên consumer khác nhau nhưng cùng thực hiện một nghiệp vụ, hai record dedup khác nhau có thể không ngăn duplicate business effect.

### 15.3. Idempotency key phải có cùng ngữ nghĩa

Nếu OLD dùng request ID làm idempotency key còn NEW dùng order ID, hai phiên bản có thể coi cùng một thao tác là hai thao tác khác nhau.

Khi chia sẻ dữ liệu, thống nhất key format, TTL, business meaning và race behavior. Đặc biệt với payment hoặc inventory, bảo vệ invariant ở storage/transaction layer khi phù hợp.

## 16. Kiểm thử hợp đồng theo ma trận phiên bản

### 16.1. Producer–consumer matrix

Đối với API, message, cache và file format, có thể tổ chức:

| Ca | Input/producer | Consumer/reader | Kết quả mong đợi |
| --- | --- | --- | --- |
| T1 | V1 JSON | OLD | Baseline pass. |
| T2 | V1 JSON | NEW | NEW hiểu lịch sử. |
| T3 | V2 JSON | NEW | Chức năng đích pass. |
| T4 | V2 JSON | OLD | Pass hoặc **V2 emission bị chặn** trong khi OLD còn chạy. |
| T5 | V1 thiếu optional field | NEW | Default được kiểm chứng, không bịa dữ liệu. |
| T6 | V2 có unknown enum | OLD/NEW | Safe handling theo contract hoặc quarantine. |
| T7 | Trộn V1/V2 với retry/replay | OLD/NEW | Không duplicate side effect, không mất event. |
| T8 | V2 đã ghi, rollback sang OLD | OLD | Rollback path được xác nhận. |

Một trường hợp T4 không thể pass về mặt semantics thì đó là bằng chứng rằng **writer V2 chưa được phép bật**, không phải lý do để bỏ test.

### 16.2. Contract fixtures nên chứa trường hợp biên

Không chỉ test payload đầy đủ:

- Required field bị thiếu.
- Optional field thiếu, null hoặc empty.
- Unknown field.
- Unknown enum/status.
- Number lớn, decimal precision và overflow.
- Unicode tiếng Việt và ký tự đặc biệt.
- Timestamp có offset, timezone và precision khác.
- Nested object/array rỗng.
- Duplicate/out-of-order events.
- Payload do serializer OLD **thực sự** tạo, không chỉ JSON tự viết tay.
- Dữ liệu lịch sử đã tồn tại trong storage.

### 16.3. Consumer-driven contract tests

Nếu nhiều service tiêu thụ một API, consumer có thể mô tả những field/status mà chúng dựa vào. Producer candidate được kiểm tra với các contract này trước khi deploy.

Cần quản lý phiên bản contract theo consumer đã thực sự deploy. Một contract test chỉ chạy với consumer source mới nhất trong repository có thể bỏ sót một bản consumer cũ còn hoạt động ở production.

### 16.4. Test với schema registry

Nếu dùng Avro/Protobuf/JSON Schema trong registry:

- Kiểm tra policy compatibility phù hợp với rollout plan.
- Đăng ký schema candidate bằng cơ chế kiểm tra của registry.
- Test decode fixture writer V1/V2 trên reader tương ứng.
- Kiểm tra field numbers, defaults và migration aliases khi format hỗ trợ.
- Kiểm tra retention/replay window chứ không chỉ latest schema.

Policy registry là một quality gate có giá trị, nhưng **không chứng minh semantic compatibility** của enum/tiền tệ/quy tắc nghiệp vụ.

## 17. Test tích hợp khi hai binary cùng chạy

### 17.1. Không chỉ chạy integration tests trên NEW

Một môi trường staging có thể chạy đồng thời:

```text
API Router
  |
  +---- OLD app instance
  |
  +---- NEW app instance
             |
             v
       Shared test database
             |
             v
       Shared test broker/cache
```

Dùng dữ liệu thử đại diện, không kết nối vào database production để thử migration.

Các ca thử:

1. OLD tạo bản ghi → NEW đọc/cập nhật → OLD đọc lại.
2. NEW tạo bản ghi → OLD đọc/cập nhật → NEW đọc lại.
3. OLD phát event → NEW consumer xử lý.
4. NEW phát event → OLD consumer xử lý hoặc emission bị chặn theo rule.
5. Hai bản cập nhật cùng một record → invariant không sai.
6. NEW chạy một phần rồi rollback sang OLD → dữ liệu tiếp tục hợp lệ.
7. Session tạo bởi OLD được NEW phục vụ nếu topology cho phép.
8. Rebalance/restart consumer không mất hoặc duplicate business effect.

### 17.2. Kiểm tra writers cùng tồn tại

Một hệ thống có thể thỏa test “OLD đọc được NEW” nhưng thất bại khi **hai phiên bản cùng update**. Ví dụ NEW ghi field mới, OLD update entity toàn phần và vô tình xóa hoặc overwrite field không biết.

Test nên kiểm tra:

- Partial update vs full-object replace.
- ORM dirty checking và optimistic locking.
- `version` column hoặc compare-and-swap policy.
- Lost update khi backfill và live writes.
- Null overwrite của fields chỉ NEW biết.
- Migrations chạy song song với user traffic.

Đây là vấn đề data consistency, không chỉ schema parsing.

### 17.3. Kiểm tra concurrent schema migration

Migration tool như Flyway hoặc Liquibase thường được dùng để quản lý schema versions. Khi nhiều pod cùng startup, cần cơ chế locking/chạy migration phù hợp; không để mọi pod tự chạy destructive migration độc lập.

Phân biệt **schema migration rollout** và **application rollout** trong release plan, đặc biệt khi thay đổi không tương thích backward.

### 17.4. Ma trận deployment tối thiểu

| Trạng thái | OLD | NEW | Schema/data | Kiểm thử |
| --- | --- | --- | --- | --- |
| Baseline | 100% | 0% | V1 | Regression OLD. |
| Expand ready | 100% | 0% | Expanded, vẫn V1 writes | OLD vẫn hoạt động. |
| Mixed | 80% | 20% | Shared contract | Cross-version + canary. |
| Near-complete | 10% | 90% | Shared contract | Background workers, retries. |
| New steady | 0% | 100% | Còn rollback-safe | Full regression/observability. |
| Contract cleanup | 0% | 100% | Schema V2 only | Chỉ sau khi rollback window kết thúc. |

Tỷ lệ chỉ là minh họa. Một pipeline thật có thể chọn bước 1% → 5% → 25% → 100% theo traffic và mức rủi ro.

## 18. Xác định rollback window và “điểm không thể quay lại”

### 18.1. Rollback code khác rollback data

Quay lại container OLD rất nhanh chưa có nghĩa OLD đọc được dữ liệu mà NEW vừa ghi.

Có những dạng thay đổi khó đảo ngược:

- Xóa/rename cột đã được OLD sử dụng.
- Thay payload format không có backward reader.
- Tạo enum/status mà OLD không biết.
- Thay cơ chế hash/encryption/session serialization.
- Chuyển currency unit/timezone làm dữ liệu không cùng semantics.
- Di chuyển data sang storage khác và bỏ nguồn cũ.
- Thay external side effect (payment, email, event) không có undo.

Cần phân biệt:

- **Reversible rollout:** quay về OLD mà dữ liệu/cấu hình vẫn hợp lệ.
- **Forward-only migration:** sau một bước contract/activation nhất định phải tiến lên bằng bản sửa mới, không thể đơn giản deploy OLD.

### 18.2. Định nghĩa compatibility horizon

Một tổ chức có thể cam kết hỗ trợ tối đa hai application versions đồng thời, ví dụ `N` và `N−1`, trong một khoảng thời gian cụ thể.

Nhưng với message retention 14 ngày và job batch chạy mỗi tuần, dữ liệu do V1 tạo có thể còn lâu hơn vòng rolling deployment vài phút. Compatibility horizon phải bao gồm:

- Thời gian old/new cùng chạy.
- Cửa sổ rollback.
- Message retention/replay.
- Cache TTL/session lifetime.
- Database records lâu dài.
- Batch/import/export schedules.
- Những client mobile/desktop không cập nhật đồng thời.

Không quyết định xóa compatibility shim chỉ vì số pod OLD bằng 0 trong vài phút.

### 18.3. Đặt điều kiện để đóng rollback window

Trước khi thay schema sang V2 only:

- Không còn pod/process/consumer/job OLD.
- Không còn external consumer bắt buộc phải hiểu V1/V2 theo policy.
- Không còn message V1 cần xử lý hoặc NEW vẫn đọc V1 dài hạn.
- Dữ liệu backfill hoàn tất và không còn writer V1.
- Không còn session/cache entry V1 gây lỗi hoặc đã có đường đọc.
- New version đã ổn định theo SLO trong thời gian được định nghĩa.
- Có quyết định/phê duyệt change management thích hợp.
- Đã có backup, runbook và phương án recovery cho tình huống nghiêm trọng.

## 19. Truy vết sự cố khi mixed-version hoạt động không đúng

| Triệu chứng | Nguyên nhân có thể | Bước điều tra |
| --- | --- | --- |
| Một số request fail ngẫu nhiên theo pod | OLD không hiểu response/request format mới hoặc state mới. | Gắn app.version vào logs, so payload theo instance. |
| Rollback xong OLD không khởi động | Database đã drop/rename cột cũ, version migration không tương thích. | Kiểm tra schema history và thay đổi contract. |
| OLD consumer tăng DLQ sau canary | NEW producer phát enum/field/event type không được OLD hỗ trợ. | Xem event fixture, schemaVersion và reader errors. |
| NEW đọc sai dữ liệu cũ | Thiếu default hợp lệ, sai charset/timezone/ORM type mapping. | So raw stored data, serializer và contract lịch sử. |
| NEW thấy field mới stale | OLD writer vẫn chỉ ghi cột cũ; backfill/dual-write không nhất quán. | Truy writers, authoritative field và transaction timeline. |
| Dữ liệu trùng đơn/charge | Scheduler hoặc consumer OLD+NEW chạy song song không idempotent. | Event IDs, locks, uniqueness và side-effect logs. |
| Cache deserialize thất bại | Cache entry mới có class/format khác bản cũ. | Inspect cache schema/versioned key/TTL. |
| Người dùng bị đăng xuất khi đổi pod | Session format/encryption hoặc cookie policy khác. | Kiểm tra session store và token compatibility. |
| Latency tăng dù không lỗi HTTP | Queue, DB pool, backfill, indexes hoặc dual-write overhead. | p99, DB locks, connection metrics và queue lag. |
| Shadow request gây email/payment thật | Shadow path không cô lập side effects. | Audit sinks và dừng shadow write traffic. |
| Test OLD–NEW pass nhưng production lỗi | Profile, schema, dependency hoặc data volume khác staging. | So artifact checksums, effective config và sampled real data. |

Nguyên tắc chẩn đoán: lưu **version của writer, version của reader, schema version và đường dữ liệu**. Nếu chỉ có stack trace mà không biết payload được tạo bởi phiên bản nào, việc xác định root cause chậm hơn nhiều.

## 20. Quy trình phát hành mixed-version theo từng pha

### Pha 0: chốt baseline và contract

1. Chụp phiên bản OLD, JDK, framework/BOM, schema, serializer config, DB/queue/cache.
2. Liệt kê các producer/consumer của dữ liệu chung.
3. Định nghĩa compatibility matrix và rollback window.
4. Lưu payload fixtures thật, test reports và business invariants.
5. Chốt owner cho schema/API/event/database migrations.

### Pha 1: chuẩn bị reader và database expand

1. Thêm schema changes chỉ theo hướng không phá OLD.
2. Nâng NEW readers để hiểu V1/V2.
3. Giữ writers ở contract V1 nếu OLD chưa an toàn với V2.
4. Triển khai compatibility layer cần thiết.
5. Chạy contract tests và mixed-version integration tests.

### Pha 2: phát hành canary code mới

1. Bật NEW với tỷ lệ nhỏ.
2. Chỉ bật traffic và tính năng đã được chứng minh không phá OLD.
3. Theo dõi decode errors, data divergence, side effects, SLOs và DB load.
4. Có kill switch/rollback procedure đã thực hành.
5. Dừng mở rộng nếu dữ liệu chung bị sai, kể cả HTTP success rate còn tốt.

### Pha 3: migrate writers/consumers theo phụ thuộc

1. Nâng các consumers còn phụ thuộc format cũ.
2. Bật new writer theo flag sau khi old readers đã được bảo vệ hoặc không còn.
3. Backfill dữ liệu theo batch có checkpoint.
4. Đối chiếu old/new fields và xử lý sai lệch.
5. Theo dõi queue replay, session cache và background jobs.

### Pha 4: đạt trạng thái NEW steady

1. Xác nhận toàn bộ ứng dụng/worker quan trọng đã lên NEW.
2. Vẫn giữ khả năng đọc V1 trong thời gian dữ liệu cũ có thể tồn tại.
3. Đo SLO và kiểm tra dữ liệu sau canary/full traffic.
4. Chốt thời gian kết thúc rollback nếu có thay đổi contract không đảo ngược.

### Pha 5: contract cleanup ở release riêng

1. Xác nhận không còn OLD writers/readers theo phạm vi đã cam kết.
2. Gỡ field/cột/endpoint/cache format cũ khi đủ điều kiện.
3. Xóa feature flags và adapter tạm thời.
4. Chạy lại test với dữ liệu lịch sử và schema mới.
5. Cập nhật tài liệu contract, runbook, schema registry và migration logs.

## 21. Mẫu hợp đồng và checklist triển khai

### 21.1. Mẫu contract worksheet

```text
Data contract:
  Name:
  Owner:
  Producers (version + deployment):
  Consumers (version + deployment):
  Storage/transport:
  Wire format / schema ID:
  Charset / timestamp / numeric semantics:
  Required / optional / nullable fields:
  Unknown field and enum policy:
  Compatibility promise:
  Minimum reader versions:
  Earliest allowed new writer:
  Retention/rollback window:
  Idempotency/ordering rules:
  Failure handling / DLQ:
  Verification fixtures:
  Schema/backfill/cleanup plan:
  Rollback plan:
```

### 21.2. Checklist trước khi chạy song song

- [ ] Đã có phiên bản OLD/NEW và topology đang chạy song song.
- [ ] Đã xác định dữ liệu dùng chung: API, DB, event, cache, session, file.
- [ ] Đã có hợp đồng dữ liệu rõ về schema, null/default, enum và semantics.
- [ ] Đã thử OLD writer → NEW reader với dữ liệu thực.
- [ ] Đã thử NEW writer → OLD reader hoặc chặn NEW emission khi OLD chưa sẵn sàng.
- [ ] Đã xác định compatibility horizon: rollout, rollback, retention, batch và external clients.
- [ ] Đã kiểm tra thay đổi JSON/ORM/JDK ảnh hưởng đến serialization, charset và timezone.
- [ ] Đã thiết kế DB expand trước khi deploy app cần field mới.
- [ ] Đã bảo vệ OLD readers/writers trong suốt migration.
- [ ] Đã có quy tắc authoritative data khi dual-read/dual-write và kế hoạch backfill.
- [ ] Đã kiểm tra concurrent writes, optimistic locking và idempotency.
- [ ] Đã kiểm tra message replay/retry, unknown event và DLQ.
- [ ] Đã xử lý session, cache keys, token và distributed scheduler.
- [ ] Đã chứng minh shadow traffic không nhân đôi side effects thật.
- [ ] Đã có version tags trong logs/metrics/traces và các ngưỡng canary.
- [ ] Đã thử rollback sau khi NEW đã ghi dữ liệu.
- [ ] Đã định nghĩa điểm forward-only nếu rollout có thay đổi không đảo ngược.
- [ ] Đã trì hoãn destructive schema changes đến release contract cleanup riêng.
- [ ] Đã cập nhật runbook, owner, schema registry và tiêu chí đóng rollback window.

## 22. Bài thực hành: chuyển Order API từ V1 sang V2 an toàn

### 22.1. Bối cảnh

Một dịch vụ Java 11 đang triển khai V1, muốn chuyển sang Java 21 và framework mới. V2 bổ sung:

- Field `currency`.
- Field `amountMinor` thay dần cho `amount`.
- Trạng thái mới `ON_HOLD`.
- Cột database mới `customer_display_name`.
- Event payload có `schemaVersion=2`.

Hệ thống dùng rolling deployment với OLD và NEW cùng DB, broker và Redis. Cửa sổ rollback là 24 giờ, nhưng message có thể được replay lâu hơn.

### 22.2. Phân loại thay đổi

| Thay đổi | Có an toàn ngay cho mixed-version? | Hành động |
| --- | --- | --- |
| Thêm `currency` optional | Chỉ khi OLD bỏ qua field lạ và default đúng | Test hai chiều; chưa required. |
| Đổi `amount` thành `amountMinor` | Không nếu xóa field cũ | Thêm field mới, giữ field cũ, thống nhất đơn vị/authoritative. |
| Phát `ON_HOLD` | Không nếu OLD xử lý sai unknown enum | Giữ emission off đến khi consumer cũ đã an toàn hoặc rút khỏi hệ thống. |
| Thêm cột nullable | Thường là expand an toàn nếu kiểm tra DB migration | Chạy migration trước NEW; không drop cột cũ. |
| Event schema V2 | Chỉ nếu readers và schema policy chấp nhận | Reader trước writer; fixture và replay test. |
| JVM 21 / framework mới | Không trực tiếp đổi data contract nhưng có thể thay serialization behavior | Golden fixtures và mixed-version integration tests. |

### 22.3. Thứ tự đề xuất

```text
(1) Chụp payload/db/event/cache baseline V1
       |
       v
(2) Expand schema: thêm cột/field tùy chọn
       |
       v
(3) Deploy NEW code đọc V1/V2, ghi theo contract V1
       |
       v
(4) Mixed-version tests và canary
       |
       v
(5) Nâng tất cả readers cần hiểu field/event V2
       |
       v
(6) Bật writer V2 theo flag + kiểm tra idempotency
       |
       v
(7) Backfill, reconciliation, quan sát replay/rollback
       |
       v
(8) Xác nhận hết OLD + rollback window
       |
       v
(9) Contract cleanup trong release sau
```

Nếu riêng trạng thái `ON_HOLD` là một thay đổi không được OLD hiểu, không phát nó ở bước 3. Nếu việc thay amount có đổi đơn vị hoặc semantics, phải có migration logic và contract test riêng trước khi chấp nhận.

### 22.4. Điều kiện thành công

Kết quả không chỉ là `BUILD SUCCESS` hoặc hai ứng dụng cùng trả HTTP 200. Cần chứng minh:

- Dữ liệu V1 vẫn đọc được trên V2.
- Dữ liệu mà V2 có thể phát trong mixed window không làm V1 sai.
- Không có duplicate charge/invoice/event processing.
- Backfill và live writes không tạo dữ liệu stale hoặc mất cập nhật.
- Session/cache/event replay vẫn hoạt động.
- Rollback OLD sau canary đã được thực hành với dữ liệu V2 có thật.
- Schema contract không bị xóa sớm.
- SLO/error rates đạt ngưỡng đã định nghĩa.

## 23. Những hiểu lầm thường gặp

**“Có hai version sau router nghĩa là có thể chạy song song.”** Sai. Router không bảo vệ shared DB, broker, cache và background jobs.

**“NEW đọc được dữ liệu cũ nghĩa là rollback an toàn.”** Sai. Rollback đòi OLD có thể xử lý dữ liệu mới đã được ghi hoặc NEW writer bị hạn chế.

**“Chỉ thêm một JSON field thì luôn tương thích.”** Sai. OLD deserializer có thể từ chối unknown field hoặc hiểu sai semantics.

**“Hai cột dual-write thì không bao giờ lệch.”** Sai. OLD writer vẫn có thể chỉ cập nhật cột cũ, backfill cũng có thể race với live updates.

**“Blue–green giúp tránh schema migration.”** Sai nếu hai môi trường chia sẻ một database hoặc message bus.

**“Shadow traffic không ảnh hưởng production.”** Sai nếu shadow path còn thực hiện side effects.

**“Ghim session vào OLD/NEW là đủ.”** Sai. Data sharing, failover, queue và background workers vẫn là ranh giới khác.

**“Exactly-once của broker đồng nghĩa payment không thể bị charge hai lần.”** Không thể suy ra. End-to-end side effects cần idempotency và transaction/reconciliation phù hợp.

**“Xóa field cũ ngay khi 100% pod đã lên NEW.”** Chưa chắc. Queue retention, batch jobs, external clients và rollback window có thể yêu cầu giữ V1 lâu hơn.

**“Nâng JDK không đổi API JSON nên không cần contract test.”** Sai. Nâng transitive serializer, ORM, charset/timezone hoặc framework có thể làm behavior đổi dù DTO nhìn giống nhau.

## 24. Kết luận

Chạy song song phiên bản cũ và mới là **một bài toán tương thích dữ liệu và vận hành**, không chỉ là kỹ thuật chia traffic. Trong cửa sổ mixed-version, OLD và NEW phải thống nhất hợp đồng ở cả hai chiều đọc–ghi, duy trì ý nghĩa nghiệp vụ của dữ liệu chung và không phá bất biến khi các tác vụ chạy đồng thời.

Một quy trình migration Java đáng tin cậy cần **reader trước writer**, **database expand–migrate–contract**, **feature flags tách deploy khỏi activation**, **ma trận kiểm thử OLD–NEW**, **idempotency**, **quan sát theo phiên bản** và **rollback có thử nghiệm trên dữ liệu do NEW tạo**. Hợp đồng cũ chỉ được loại bỏ sau khi không còn consumer/writer cần nó và cửa sổ rollback/retention đã được xử lý. Như vậy, nâng JDK và framework mới có thể diễn ra từng bước mà không buộc toàn bộ hệ thống phải dừng hoặc chấp nhận rủi ro dữ liệu không thể phục hồi.
