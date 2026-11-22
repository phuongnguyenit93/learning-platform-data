# Giao thức giữa dịch vụ cũ và mới trong thời gian chạy song song

Trong Java Advance Compatibility Migration, việc nâng một dịch vụ từ JDK cũ lên JDK mới hiếm khi diễn ra đồng thời trên toàn bộ hệ thống. Một số instance hoặc service vẫn chạy Java 8/11, trong khi những thành phần khác đã chuyển lên Java 17/21 hoặc một release phù hợp với lộ trình của tổ chức. Khi triển khai rolling update, canary, blue-green hoặc tách dần một monolith, **hai phiên bản có thể giao tiếp với nhau trong nhiều ngày hoặc nhiều tuần**.

Nếu giao thức giữa chúng thay đổi không có kế hoạch, ứng dụng có thể gặp lỗi dù mỗi phiên bản đều chạy đúng khi hoạt động độc lập: bên cũ không đọc được trường mới; bên mới hiểu sai giá trị mặc định; event được tiêu thụ hai lần; một mã trạng thái mới khiến client cũ thất bại; hoặc rollback binary thành công nhưng dữ liệu đã ghi trong thời gian chạy song song không còn đọc được bởi phiên bản trước.

Vì thế, **giao thức giữa dịch vụ cũ và mới trong thời gian chạy song song** là tập hợp các hợp đồng cần giữ giữa những phiên bản cùng tồn tại: HTTP/gRPC API, định dạng payload, mã lỗi, message schema, thứ tự và ngữ nghĩa event, xác thực và phân quyền, quy tắc retry, dữ liệu lưu trữ, thời gian xử lý cùng quy trình triển khai. Mục tiêu không phải bắt buộc mọi phiên bản giống hệt nhau; mục tiêu là thiết kế thay đổi để các tổ hợp phiên bản được hỗ trợ **hiểu và xử lý dữ liệu đúng hợp đồng**, đồng thời có đường nâng cấp và rollback an toàn.

## 1. Vì sao cần chạy song song và điều gì dễ bị phá vỡ?

Một hệ thống có thể chạy song song phiên bản cũ và mới bởi:
- Rolling deployment: một số instance v1 được thay dần bằng v2.
- Canary: chỉ một phần traffic được điều hướng tới v2 để đánh giá rủi ro.
- Blue-green: hai nhóm instance cùng sẵn sàng trong giai đoạn chuyển traffic.
- Tách một chức năng từ monolith sang microservice mới.
- Đổi runtime JDK, framework, serialization library hoặc message broker client theo từng service.
- Migration dữ liệu cần đồng bộ giữa schema cũ và schema mới.
- Hỗ trợ các mobile app, batch job, đối tác hoặc consumer không thể nâng đồng thời với server.

Trong các tình huống này, một request có thể đi qua chuỗi:

~~~text
                 Gateway / Load balancer
                          |
                  +-------+-------+
                  |               |
             Orders v1        Orders v2
             (JDK cũ)        (JDK mới)
                  |               |
                  +-------+-------+
                          |
                     Inventory v1
                          |
                       Broker
                          |
                 Billing v1 / Billing v2
                          |
                    Shared storage
~~~

Cần xem xét không chỉ v1 ↔ v2 của cùng một service, mà cả consumer cũ của API, producer cũ/mới của event, database đang cùng được truy cập, cache, scheduler và những thành phần xử lý retry.

### 1.1. Nhiều loại tương thích cùng tồn tại

| Loại tương thích | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| **Wire format** | Bên nhận có parse được bytes/payload không? | JSON đổi kiểu number thành object |
| **Schema** | Trường, tên, mã enum, field number có còn hợp lệ không? | Protobuf tái sử dụng field tag |
| **Semantic** | Giá trị vẫn mang cùng ý nghĩa không? | `amount` từ đồng thành xu mà không đổi contract |
| **Behavioral** | Side effect, mã lỗi, retry và trạng thái có giữ hợp đồng? | POST gửi lại tạo hai đơn hàng |
| **Temporal** | Timestamp, timezone, expiry và ordering có cùng cách hiểu? | `LocalDateTime` được coi là UTC ở bản mới |
| **Security** | Authn/authz, TLS, signature và identity còn tương thích? | Client cũ không gửi claim mới bắt buộc |
| **Data/storage** | Bản cũ có đọc được dữ liệu bản mới đã ghi không? | DB enum value mới không được code cũ xử lý |
| **Operational** | Có thể deploy, quan sát, cắt traffic và rollback không? | Rollback app nhưng DB đã xóa cột cũ |

Một API **parse được** chưa chắc có **semantics tương thích**. Đối với migration, cần mô tả rõ từng loại hợp đồng trước khi sửa code.

## 2. Khái niệm backward và forward compatibility

Xét producer (bên phát dữ liệu) và consumer (bên đọc/xử lý dữ liệu):

- **Backward compatibility**: consumer phiên bản mới có thể đọc và xử lý dữ liệu do producer phiên bản cũ tạo.
- **Forward compatibility**: consumer phiên bản cũ có thể đọc và xử lý dữ liệu do producer phiên bản mới tạo, trong phạm vi đã cam kết.
- **Full compatibility**: hai chiều trên đều được bảo đảm cho một tập thay đổi/schema cụ thể.

Các tên này đôi khi được dùng trong schema registry theo định nghĩa chi tiết khác nhau, nhất là khi nói về khả năng đọc schema cũ/mới. Trong tài liệu dự án, hãy ghi rõ **ai tạo payload, ai đọc payload, phiên bản nào** thay vì chỉ ghi “backward compatible” không kèm chiều giao tiếp.

### 2.1. Ma trận giao tiếp tối thiểu

Trong giai đoạn coexistence, một ma trận thường cần là:

| Producer | Consumer | Mục tiêu |
|---|---|---|
| v1 | v1 | Baseline vốn đang chạy |
| v1 | v2 | Bản mới vẫn hiểu dữ liệu cũ |
| v2 | v1 | Bản cũ không bị phá khi nhận dữ liệu mới |
| v2 | v2 | Chức năng mới hoạt động |

Nếu producer và consumer có nhiều service/version độc lập, hãy mở rộng ma trận dựa trên **support window**. Không cần thử mọi tổ hợp lịch sử vô hạn; phải thử những phiên bản thật sự còn chạy hoặc được hỗ trợ.

Đối với request-response, một tương tác gồm **request lẫn response**:
- Client v1 phải gửi request mà server v2 hiểu được.
- Server v2 phải trả response và lỗi mà client v1 xử lý được.
- Client v2 gửi request mới tới server v1 chỉ khi client đã có fallback hoặc cơ chế thương lượng năng lực.

Một thay đổi chỉ “server v2 chấp nhận request v1” chưa đủ chứng minh client v1 dùng được server v2.

## 3. Bắt đầu từ contract, không bắt đầu từ class Java

Các class Java trong service có thể thay đổi theo JDK/framework, nhưng **wire contract** cần được xác định độc lập với implementation: tên field, kiểu dữ liệu bên ngoài, mã HTTP, header, auth claim, event name, schema version, timezone, units, nullability và hiệu ứng nghiệp vụ.

Ví dụ, một JSON response của Orders API v1:

~~~json
{
  "orderId": "ord-102",
  "status": "CREATED",
  "totalAmount": "125000",
  "currency": "VND"
}
~~~

Bản v2 muốn thêm thông tin giao hàng:

~~~json
{
  "orderId": "ord-102",
  "status": "CREATED",
  "totalAmount": "125000",
  "currency": "VND",
  "delivery": {
    "method": "STANDARD",
    "estimatedAt": "2026-11-18T09:00:00+07:00"
  }
}
~~~

Thêm field thường là một hướng mở rộng ít rủi ro hơn đổi tên/kiểu field cũ, **nhưng chỉ an toàn khi consumer cũ có thể bỏ qua field không biết** và không bị ràng buộc bởi strict schema đã công bố. Nếu client cũ cấu hình JSON deserializer từ chối unknown fields, thêm `delivery` có thể phá tương thích. Do đó không được coi “additive” tự động là compatible; phải xác nhận bằng test với binary/client cũ.

### 3.1. Contract nên ghi gì?

Một bảng contract tiêu biểu:

| Thành phần | Quyết định cần ghi |
|---|---|
| Endpoint/method | `POST /orders`; hành động tạo đơn |
| Request field | Tên, kiểu, required/optional, validation |
| Response field | Tên, kiểu, giá trị có thể null, default |
| Enum/status | Danh sách giá trị và cách xử lý giá trị chưa biết |
| Number | Đơn vị, precision, scale, rounding |
| Timestamp | UTC/offset/IANA zone, format, semantics |
| Headers | Auth, idempotency key, correlation ID, capability/version |
| Errors | HTTP status, error code, retryability, cấu trúc payload |
| Side effects | Ghi DB, publish event, gọi external service |
| Retry/timeout | Có thể gửi lại không, deadline nào được giữ |
| Version window | Client/server versions cần hỗ trợ |
| Deprecation | Khi nào ngừng field/endpoint cũ, có cách chuyển đổi nào |

Không để những điểm này chỉ tồn tại dưới dạng implementation detail của một Java DTO hoặc annotation trong một service.

## 4. Quy tắc tiến hóa JSON/HTTP ít gây gián đoạn

### 4.1. Tránh thay đổi phá vỡ field đã phát hành

Trong giai đoạn chạy song song, những thay đổi sau thường có rủi ro:

- Đổi tên một field mà client cũ đang đọc.
- Đổi `string` thành `object`, `number` thành `string`, hoặc array thành singleton.
- Thay `null` bằng missing field hoặc ngược lại khi consumer phân biệt chúng.
- Làm một trường optional thành required.
- Đổi đơn vị (millisecond ↔ second, đồng ↔ xu) mà không đổi contract/version.
- Thêm enum value trong luồng mà consumer cũ xử lý bằng exhaustive switch không có fallback.
- Thay cấu trúc mã lỗi hoặc chuyển lỗi có thể retry thành lỗi fatal.
- Đổi pagination, sorting hay timezone mà không mô tả.
- Đổi tên HTTP header hoặc auth requirement khiến client cũ không gửi được request.

Một thay đổi có thể trông “không breaking” ở source Java nhưng vẫn breaking ở wire/semantic contract.

### 4.2. Thêm optional field có default rõ ràng

Ví dụ request v1:

~~~json
{
  "customerId": "cus-1",
  "items": [
    {"sku": "A-123", "quantity": 2}
  ]
}
~~~

Request v2 thêm `deliveryPriority`:

~~~json
{
  "customerId": "cus-1",
  "items": [
    {"sku": "A-123", "quantity": 2}
  ],
  "deliveryPriority": "STANDARD"
}
~~~

Để server v2 tiếp tục nhận request v1, `deliveryPriority` nên optional khi nhận, với default tương thích về hành vi:

~~~text
missing deliveryPriority -> STANDARD
explicit deliveryPriority -> validate allowed values
~~~

Đối với server v1, request v2 chỉ được gửi nếu v1 có khả năng chấp nhận field mới hoặc client v2 có adapter để bỏ field khi gọi v1. Nếu không, có thể cần endpoint/version mới hoặc feature negotiation.

**Cần phân biệt missing và explicit null.** Chẳng hạn, nếu field `deliveryPriority` xuất hiện với `null`, server phải quyết định nó có nghĩa như missing, “không đặt ưu tiên”, hay là input không hợp lệ. Giữ quy tắc nhất quán qua các phiên bản.

### 4.3. Tolerant reader không phải bỏ qua lỗi dữ liệu

Một consumer linh hoạt có thể bỏ qua **field chưa biết** nhưng vẫn phải kiểm tra:
- Kiểu của field mà nó sử dụng.
- Giá trị enum/currency theo contract.
- Giới hạn size và depth của payload.
- Schema và chữ ký nếu payload được bảo vệ.
- Ý nghĩa của field required hoặc validation quan trọng.

Việc bỏ qua unknown fields **không** có nghĩa tự động chấp nhận mọi payload không hợp lệ hoặc bỏ qua lỗi bảo mật. Nếu field mới thay đổi ý nghĩa của field cũ mà consumer không biết, tolerant reader vẫn xử lý sai.

### 4.4. Ví dụ Java với Jackson và unknown fields

Một consumer Java cũ có thể định nghĩa DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class OrderResponseV1 {
    public String orderId;
    public String status;
    public String totalAmount;
    public String currency;
}
~~~

Khi đọc payload v2 có thêm `delivery`, một phiên bản Jackson phù hợp có thể bỏ qua field chưa biết:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class ReadNewOrderPayload {
    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "orderId": "ord-102",
                  "status": "CREATED",
                  "totalAmount": "125000",
                  "currency": "VND",
                  "delivery": {"method": "STANDARD"}
                }
                """;

        OrderResponseV1 result =
                new ObjectMapper().readValue(json, OrderResponseV1.class);

        System.out.println(result.orderId);
    }
}
~~~

Java text block đòi hỏi Java 15+; **nếu consumer đang chạy Java 8 hoặc 11**, dùng chuỗi Java thông thường hoặc nạp fixture từ resource. Đây là minh họa cơ chế deserialization, không phải yêu cầu nâng source level của consumer cũ. Ngoài ra, annotation `@JsonIgnoreProperties` phải có trong binary consumer cũ trước khi nâng server; không thể sửa class cũ và tuyên bố đó là bằng chứng consumer đã phát hành tương thích.

Khi dùng thư viện khác như Gson, JSON-B, Kotlinx Serialization hoặc custom mapper, quy tắc unknown fields và nullability có thể khác. Hãy test **chính artifact consumer cũ**, không giả định behavior tương tự Jackson.

## 5. Số tiền, ngày giờ và status: tương thích ngữ nghĩa

### 5.1. Số tiền

Không đổi `totalAmount` từ đồng sang xu mà vẫn giữ cùng tên/contract. Ví dụ:

~~~text
v1: "125000"  -> 125.000 VND
v2: "125000"  -> 125.000 xu?  (breaking nếu diễn giải lại)
~~~

Nên công bố `currency`, đơn vị tiền tệ, precision, rounding, giá trị âm có cho phép và cách serialize decimal. Với Java, `BigDecimal` thường phù hợp cho phép tính tiền; không sử dụng `double` để mô tả số tiền cần chính xác tuyệt đối.

Nếu cần thay representation, bổ sung field mới có tên/semantics tách biệt, cung cấp adapter và lộ trình bỏ field cũ. Đồng thời test các giới hạn: số lớn, số lẻ, zero, null, currency không hỗ trợ và rounding.

### 5.2. Timestamp

Payload kiểu:

~~~json
{"createdAt":"2026-11-12T09:30:00Z"}
~~~

mô tả một instant UTC rõ ràng. Payload:

~~~json
{"createdAt":"2026-11-12 16:30:00"}
~~~

không có offset/zone nên bị phụ thuộc vào cách consumer tự diễn giải. Sau Java migration, default timezone hoặc tzdb của JVM có thể thay đổi; hai phiên bản dịch vụ có thể tính hai instant khác nhau từ cùng chuỗi.

Đối với event đã xảy ra, ưu tiên biểu diễn timestamp có offset/UTC và mô tả precision. Đối với lịch tương lai gắn giờ địa phương, gửi local date-time cùng IANA ZoneId và policy xử lý DST gap/overlap.

### 5.3. Enum và trạng thái nghiệp vụ

Giả sử v1 chỉ biết:

~~~text
CREATED, PAID, CANCELLED
~~~

v2 bổ sung:

~~~text
AWAITING_REVIEW
~~~

Nếu v2 phát event `AWAITING_REVIEW` tới consumer v1, việc parse chuỗi thành enum Java có thể thất bại hoặc một switch không có fallback có thể xử lý sai. Các lựa chọn:
- Tạm **không phát** giá trị mới cho consumer v1.
- Mapping sang trạng thái v1 có semantics đủ tương đương, được nghiệp vụ phê duyệt.
- Cấp endpoint/topic/event type mới cho những consumer hỗ trợ trạng thái mới.
- Nâng consumer và kiểm tra khả năng xử lý unknown trước khi producer phát giá trị mới.

Không tự mapping mọi trạng thái mới thành `CREATED` nếu điều đó có thể dẫn tới thu tiền, giao hàng hoặc xử lý nghiệp vụ sai.

## 6. Protobuf/gRPC và tiến hóa schema

Trong hệ thống gRPC hoặc message nhị phân dùng Protocol Buffers, khả năng tương thích cần xét theo **field number và wire type**, không chỉ tên field Java sinh ra.

Ví dụ v1:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;
  int64 total_minor_units = 3;
}
~~~

Một v2 theo hướng thêm field:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;
  int64 total_minor_units = 3;
  string delivery_method = 4;
}
~~~

Điểm quan trọng:
- Không thay field number `1` hoặc `2` sang ý nghĩa khác.
- Không tái sử dụng tag của field đã xóa; dùng `reserved` cho number/name khi loại bỏ.
- Không cho rằng đổi tên field là luôn vô hại, vì JSON mapping, source code và tooling có thể phụ thuộc tên.
- Proto3 có các quy tắc về default value và presence; cần phân biệt giá trị mặc định với field vắng mặt, nhất là khi đổi contract.
- Đổi scalar type có thể thay wire type hoặc semantics; ngay cả một thay đổi còn parse được ở cấp wire cũng có thể làm sai giá trị.
- Thêm enum value có thể khiến consumer cũ không hiểu giá trị mới; cần test generated code và fallback behavior.
- gRPC **service method**, request/response message, metadata, status code và deadline cũng là phần của contract.

### 6.1. Xóa field theo cách kiểm soát

Khi một field không còn dùng, thay vì tái sử dụng tag cho ý nghĩa khác:

~~~proto
syntax = "proto3";
package orders.v1;

message Order {
  string order_id = 1;
  string status = 2;

  reserved 3;
  reserved "total_minor_units";

  string delivery_method = 4;
}
~~~

Đây là ví dụ về việc dự trữ tag đã loại bỏ trong schema mới; tuy nhiên, **xóa field 3 vẫn có thể làm hỏng consumer v1 cần thông tin tiền** dù parser bỏ qua tag đúng cách. Wire compatibility và semantic compatibility phải được xét riêng.

### 6.2. Khi chuyển proto/gRPC library trong Java

Nâng JDK có thể kéo theo nâng gRPC/Netty/Protobuf version. Cần kiểm tra:
- Generated stub và runtime library có tương thích không.
- HTTP/2, TLS, ALPN và proxy/load balancer có xử lý tương đương không.
- Deadline propagation, retry, cancellation và stream backpressure.
- Max message size, compression, metadata header.
- Unknown field, enum và JSON transcoding.
- Server reflection/schema discovery nếu client/tooling phụ thuộc.

Chỉ vì proto file giữ nguyên không có nghĩa mọi behavior transport hoặc generated Java API vẫn giữ nguyên.

## 7. Event/message trong giai đoạn producer và consumer chạy song song

Với Kafka, RabbitMQ, JMS hoặc hệ thống queue tương tự, thứ tự deploy thường khác HTTP request-response. Producer mới có thể phát event mà consumer cũ đọc sau nhiều phút hoặc nhiều ngày, kể cả khi producer mới đã rollback.

Một event v1:

~~~json
{
  "eventId": "evt-51",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T09:30:00Z",
  "payload": {
    "orderId": "ord-102",
    "totalAmount": "125000",
    "currency": "VND"
  }
}
~~~

Một event mới có thể thêm field vào `payload` hoặc phát `schemaVersion` khác. Để tương thích, phải định nghĩa:
- Consumer nào biết event type và schema version nào.
- Có được bỏ qua field không biết không.
- Unknown event type nên fail, skip, quarantine hay đưa vào dead-letter queue.
- Event được replay hoặc retry bao nhiêu lần.
- Có ordering guarantee theo key/partition hay không.
- Event có thể được phát trùng, đến muộn hoặc out-of-order không.
- Định danh event và cách xử lý idempotency.

### 7.1. Envelope và payload là hai tầng contract

Nên tách trường **envelope** ổn định để routing/observability khỏi **payload** nghiệp vụ:

| Tầng | Ví dụ field | Ý nghĩa |
|---|---|---|
| Envelope | eventId | Nhận diện event và phát hiện trùng lặp |
| Envelope | eventType | Chọn handler |
| Envelope | schemaVersion | Diễn giải payload theo version |
| Envelope | occurredAt | Thời điểm sự kiện phát sinh |
| Envelope | correlationId/traceId | Theo dõi chuỗi nghiệp vụ |
| Payload | orderId, amount, status | Dữ liệu nghiệp vụ của event |

Không coi `schemaVersion` là giải pháp tự động. Nó chỉ giúp consumer biết phải dùng parser/adapter nào; vẫn cần quy định hỗ trợ version và đường nâng cấp schema.

### 7.2. Event không phải command

Một event như `OrderPaid` mô tả một sự kiện đã xảy ra. Một command như `ChargePayment` yêu cầu một thao tác có side effect. Khi migration, gửi lại command có thể dẫn tới thanh toán hai lần nếu không có idempotency; replay event thường phải cập nhật materialized view hoặc trạng thái theo một policy idempotent.

Không dùng cùng logic retry cho hai loại message chỉ vì cả hai nằm trên broker.

### 7.3. Schema registry và chính sách tương thích

Nếu dùng Avro, Protobuf hoặc JSON Schema qua registry, nên cấu hình compatibility mode phù hợp với support window. Kiểm tra:
- Registry kiểm tra schema evolution ở chiều nào.
- Consumer có tự dùng writer schema/reader schema không.
- Schema ID được đưa vào message theo cơ chế nào.
- Có yêu cầu hỗ trợ nhiều phiên bản lịch sử hay chỉ version trước không.
- Producer nào được phép publish schema mới và quy trình review.

Registry validation hữu ích nhưng không phát hiện mọi semantic break như đổi đơn vị tiền hoặc ý nghĩa trạng thái.

## 8. Idempotency, retry và delivery semantics

Khi chuyển traffic qua v1/v2, timeout dễ bị hiểu là “request chưa thực hiện”. Một client có thể retry tới instance khác sau khi instance cũ đã commit giao dịch. Nếu server không có idempotency, một lệnh nghiệp vụ có thể được xử lý hai lần.

Ví dụ:

~~~text
Client ---- POST /payments ----> Payment v1
                  |
           v1 ghi giao dịch thành công
                  |
           Response bị timeout/mất
                  |
Client ---- retry POST -------> Payment v2
                  |
           v2 tạo giao dịch lần hai  (sai)
~~~

### 8.1. Định nghĩa idempotency key ở cấp nghiệp vụ

Với operation có side effect, client gửi một key ổn định cho **cùng một ý định nghiệp vụ**:

~~~http
POST /payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: pay-request-7f4a

{"orderId":"ord-102","amount":"125000","currency":"VND"}
~~~

Cả v1 và v2 cần dùng **cùng cơ chế kiểm tra key**, không phải mỗi phiên bản lưu cache in-memory riêng. Một hợp đồng idempotency nên định nghĩa:
- Phạm vi key: theo principal/tenant và operation nào.
- Thời hạn lưu key và policy retry sau thời hạn.
- Payload fingerprint: cùng key nhưng payload khác phải làm gì.
- Kết quả nào được trả lại khi request được gửi lại.
- Khi nào key được đánh dấu committed.
- Transaction boundary với side effect thực tế.
- Cách xử lý hai request cùng key đến đồng thời.

Một cache map đơn giản trong từng instance không bảo đảm chính xác khi có rolling deployment, nhiều replica hoặc process crash.

### 8.2. Ví dụ transaction ở database

Một bảng idempotency minh họa:

~~~sql
CREATE TABLE request_dedup (
    tenant_id        VARCHAR(64) NOT NULL,
    operation_name   VARCHAR(64) NOT NULL,
    idempotency_key  VARCHAR(128) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    response_payload TEXT,
    state            VARCHAR(16) NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Hệ thống cần transaction hoặc cơ chế concurrency control thích hợp để đảm bảo một key chỉ tạo side effect một lần theo contract. **Chỉ tạo bảng không tự bảo đảm exactly-once**: race condition, commit giữa nhiều hệ thống và external payment gateway có thể vẫn gây duplicate. Khi gọi downstream có side effect, truyền idempotency key phù hợp hoặc thiết kế saga/compensation được kiểm chứng.

### 8.3. Event delivery và consumer deduplication

Trong broker có cơ chế at-least-once, một message có thể được delivery lại. Consumer có thể lưu `eventId` đã xử lý trong cùng transaction với cập nhật trạng thái, hoặc dùng operation idempotent theo business key.

Ví dụ khái niệm:

~~~text
Begin transaction
  if eventId already processed:
      no-op
  else:
      apply business change
      record eventId
Commit
Acknowledge message after successful commit
~~~

Đây là mô hình tư duy, cần điều chỉnh theo transaction semantics của DB và broker. Nếu ack xảy ra trước DB commit, message có thể mất; nếu DB commit xong nhưng ack thất bại, message có thể được gửi lại và phải được deduplicate.

## 9. Ordering, consistency và state machine

Một hệ thống có thể nhận:
 
~~~text
OrderCreated
OrderPaid
OrderCancelled
~~~

theo thứ tự khác nhau ở các consumer nếu dùng nhiều topic, partition, service, retry hoặc replication. Khi v1 và v2 dùng schema/state logic khác, sự sai lệch càng khó phát hiện.

### 9.1. Thứ tự theo entity thay vì toàn cục

Nếu broker bảo đảm ordering theo partition, dùng một key ổn định như `orderId` để các event của cùng order đi vào vùng ordering thích hợp. Cần hiểu chính xác guarantee của broker đang dùng và cách producer chọn partition.

Đừng suy luận “broker có queue nên mọi event trong hệ thống đến theo thứ tự toàn cục”. Cross-partition và cross-topic thường không có thứ tự toàn cục.

### 9.2. Version của aggregate/state

Khi consumer xử lý state update, có thể kèm `aggregateVersion` hoặc sequence được phát từ một nguồn có quyền quyết định:

~~~json
{
  "eventId": "evt-53",
  "orderId": "ord-102",
  "aggregateVersion": 4,
  "eventType": "OrderPaid"
}
~~~

Consumer kiểm tra version để phát hiện event cũ hoặc thiếu bước. Không tự giả định số version tăng đều nếu hệ thống có nhiều writer không điều phối; phải định nghĩa nơi cấp version và cách xử lý gaps.

### 9.3. Không cho v2 tạo trạng thái mà v1 không hiểu

Trong giai đoạn chạy song song, producer v2 có thể tạo giá trị state mới. Nếu một số instance v1 hoặc consumer v1 còn được điều hướng tới entity đó, chúng có thể từ chối hoặc xử lý sai.

Các cách kiểm soát:
- Tạm tắt chức năng tạo state mới bằng feature flag.
- Có state mapping sang representation v1 với semantics được phê duyệt.
- Đảm bảo entity dùng tính năng mới chỉ được xử lý bởi v2 khi routing có affinity.
- Tách topic/endpoint mới và chỉ kết nối consumer có capability phù hợp.
- Chờ giai đoạn v1 được loại khỏi mọi tuyến xử lý mới bật state mới.

Đây là một ví dụ mà **schema hợp lệ vẫn không đủ**. Migration cần phối hợp dữ liệu/state machine và deployment.

## 10. Dữ liệu dùng chung: expand–migrate–contract

Một rủi ro lớn của chạy song song là v1 và v2 cùng truy cập database. Một schema change không tương thích có thể làm v1 lỗi ngay khi v2 được deploy.

### 10.1. Expand

Đầu tiên thêm cấu trúc mới theo cách v1 vẫn hoạt động:
- Thêm cột nullable hoặc có default thực sự tương thích.
- Thêm bảng mới mà không xóa bảng cũ.
- Thêm index cần thiết trước khi mở chức năng.
- Viết code v2 có thể đọc representation cũ.

Ví dụ:

~~~sql
ALTER TABLE orders ADD COLUMN delivery_priority VARCHAR(24);
~~~

Chưa đặt ngay NOT NULL nếu v1 vẫn tạo row không có field đó. Nếu dữ liệu mới mang ý nghĩa bắt buộc, ứng dụng v2 có thể áp dụng default khi đọc trong giai đoạn chuyển tiếp.

### 10.2. Migrate/backfill

Backfill dữ liệu cũ sang representation mới theo batch có kiểm soát. Kiểm tra transaction size, lock, write amplification, replication lag, retry và khả năng resume. Nếu cả v1/v2 vẫn ghi, phải xác định quy tắc đồng bộ để dữ liệu không drift.

Các lựa chọn gồm:
- Đọc cột mới, fallback cột cũ.
- Cập nhật cả hai representation trong cùng transaction khi cùng database.
- Dùng CDC hoặc luồng đồng bộ có owner rõ.
- Tách thay đổi sang một service duy nhất được phép ghi.

**Dual-write qua hai database hoặc hai service** không có transaction chung rất dễ tạo trạng thái một bên thành công/một bên thất bại. Chỉ triển khai nếu có cơ chế reconciliation, retry/idempotency và xử lý lỗi được thiết kế rõ.

### 10.3. Contract

Sau khi không còn consumer v1 và đã xác nhận dữ liệu/truy cập tương thích, mới cân nhắc:
- Đặt NOT NULL hoặc ràng buộc mới.
- Loại cột/table cũ.
- Ngừng đọc fallback.
- Ngừng xuất field/endpoint/event v1.

Giai đoạn contract là **thời điểm có thể làm rollback về v1 không còn an toàn**. Phải có quyết định release rõ ràng, backup/restore plan và bằng chứng không còn consumer cũ.

### 10.4. Timeline minh họa

~~~text
T0  DB schema v1, App v1
 |
T1  Expand schema, App v1 vẫn chạy
 |
T2  Deploy App v2 (đọc old/new), App v1 + v2 song song
 |
T3  Backfill và reconcile; phát event compatible
 |
T4  Tắt writes theo đường cũ; xác nhận không còn v1
 |
T5  Contract schema và ngừng adapter/field cũ
 |
T6  Kết thúc compatibility window
~~~

Khoảng T2–T4 là giai đoạn dễ phát sinh dữ liệu bất nhất và rollback phức tạp; cần quan sát đặc biệt.

## 11. Version API và capability negotiation

### 11.1. Thay đổi additive có thể không cần URL version mới

Nếu v2 chỉ thêm optional field mà các client đã được chứng minh có thể bỏ qua, có thể giữ endpoint `/orders` trong support window. Nhưng khi semantics thay đổi căn bản, tách version rõ ràng thường giúp bảo vệ consumer cũ.

Các chiến lược thường gặp:
- Path version: `/v1/orders`, `/v2/orders`.
- Media type/version header.
- Protocol schema/service package version.
- Event type hoặc topic version riêng.
- Capability negotiation qua header/handshake khi có nhu cầu.

Không có một cách versioning đúng cho mọi hệ thống. Điểm quan trọng là **version đại diện cho contract được hỗ trợ**, không chỉ là version deploy của JVM.

### 11.2. Capability thay vì đoán từ Java version

Client có thể gửi một danh sách năng lực cụ thể:

~~~http
GET /orders/ord-102 HTTP/1.1
Accept: application/json
X-Client-Capabilities: delivery-status-v2
~~~

Server chỉ gửi representation mới khi contract cho phép. Đây là **ví dụ thiết kế riêng của ứng dụng**, không phải một header HTTP tiêu chuẩn được mọi framework tự hiểu. Nếu dùng phải đặc tả cách parse, validation, bảo mật và fallback.

Đừng sử dụng User-Agent hoặc JDK version của client làm bằng chứng chắc chắn về schema mà client hiểu. Hai ứng dụng cùng Java 17 có thể hỗ trợ hai phiên bản contract khác nhau.

### 11.3. Anti-corruption layer/adapter

Khi v1 và v2 có mô hình nghiệp vụ khác, có thể đặt adapter ở ranh giới:

~~~text
Client v1  ->  V1 API adapter  ->  Domain model v2
Client v2  ->  V2 API adapter  ->  Domain model v2
~~~

Adapter có nhiệm vụ chuyển:
- Tên field và value representation.
- Status/error code.
- Đơn vị tiền và timestamp.
- Request validation semantics.
- Kết quả trả về tương thích với client cũ.

Không biến adapter thành nơi âm thầm sửa mọi lỗi hoặc dịch trạng thái không có tương đương. Với những case không thể map an toàn, cần version mới, reject có thông báo rõ hoặc quy trình migrate consumer.

## 12. HTTP, TLS, authentication và lỗi giao thức

Khi nâng JDK, stack networking có thể thay cùng lúc: HTTP client, TLS defaults, certificate trust, HTTP/2, cipher suites hoặc thư viện serialization. Một API không thay JSON schema vẫn có thể không kết nối được.

### 12.1. Hợp đồng lỗi và retry

Ví dụ error response ổn định:

~~~json
{
  "errorCode": "ORDER_NOT_FOUND",
  "message": "Order does not exist",
  "retryable": false,
  "requestId": "req-7a1"
}
~~~

Nếu v2 đổi mã lỗi `ORDER_NOT_FOUND` thành `NOT_FOUND` và client v1 kiểm tra bằng string, client cũ có thể diễn giải sai. Nếu v2 đổi 409 thành 500, client có thể retry một request không nên retry.

Nên định nghĩa:
- HTTP status + machine-readable error code.
- Có thể retry không, sau bao lâu, retry cùng idempotency key không.
- 429/503 có `Retry-After` hay contract rate limit tương đương.
- Deadline/timeout và cancellation semantics.
- Error payload an toàn, không lộ stack trace/secret.

### 12.2. TLS và identity

Trước khi canary, kiểm tra:
- TLS versions/cipher suites được cả hai bên hỗ trợ theo chính sách bảo mật.
- Certificate chain, hostname validation, truststore và certificate rotation.
- mTLS identity nếu sử dụng.
- Token format, claim/role/audience và thời hạn token.
- Client cũ không phải bỏ qua certificate validation để kết nối.
- Service mới không tự bỏ kiểm tra phân quyền để giữ tương thích.

Đặc biệt, **không hạ bảo mật** để hỗ trợ client cũ không còn đáp ứng yêu cầu tối thiểu. Trong trường hợp không thể giao tiếp an toàn, dùng endpoint tách biệt, gateway có policy hoặc một lộ trình ngừng hỗ trợ công bố rõ.

### 12.3. Java Object Serialization không phù hợp làm wire contract mặc định

Dùng `ObjectOutputStream`/`ObjectInputStream` trực tiếp giữa các service tạo coupling mạnh giữa class name, `serialVersionUID`, class loader và object graph. Điều này làm migration JDK/library khó kiểm soát và gây rủi ro deserialization khi nhận dữ liệu không tin cậy.

Nếu hệ thống đang dùng Java native serialization trong cache/RMI/message:
- Kiểm kê nơi còn dùng và trust boundary.
- Không nhận untrusted serialized objects mà không có cơ chế bảo vệ phù hợp.
- Đánh giá object input filtering khi còn phải hỗ trợ.
- Lập kế hoạch chuyển sang schema contract rõ như JSON/Protobuf/Avro theo use case.
- Chuyển cả dữ liệu tồn kho/replay và kiểm tra compatibility trước khi tắt format cũ.

## 13. Routing traffic khi v1/v2 cùng chạy

### 13.1. Canary và weighted routing

Một cách phổ biến là điều hướng 1%, 5%, 25% rồi 100% traffic tới v2. Nhưng **chỉ đếm request thành công là chưa đủ**. Nếu request có side effect và state machine mới, một entity có thể bị xử lý luân phiên bởi v1 và v2.

Các kỹ thuật:
- Route theo stable hash của tenant/account/order ID.
- Session/entity affinity khi cần.
- Chỉ bật feature v2 cho nhóm tenant tương ứng.
- Canary ở read-only endpoint trước khi mở write.
- Tách hàng đợi/consumer group để tránh xử lý cùng command hai lần.

### 13.2. Shadow traffic và hạn chế

Shadow traffic sao chép request tới v2 để quan sát output mà chưa phục vụ response thật. **Không được gửi shadow write vào resource production có side effect** nếu không có sandbox hoặc dry-run mechanism đã được thiết kế.

Đối với endpoint đọc:
- Có thể so sánh response v1/v2 sau khi chuẩn hóa field không quyết định.
- Cần giới hạn dữ liệu nhạy cảm và masking.
- Phải kiểm tra việc shadow request có làm tăng tải DB hoặc gây side effect gián tiếp không.

Đối với write:
- Có thể dùng dữ liệu tổng hợp hoặc môi trường isolate để tái hiện.
- Nếu dùng hệ thống dual-run có side effect, phải có thiết kế idempotency, ownership và compensation rõ, không coi “shadow” tự động an toàn.

### 13.3. Blue-green và consumer tồn tại ngoài load balancer

Chuyển traffic ở gateway không bảo đảm toàn bộ consumer v1 đã biến mất. Có thể còn:
- Batch job gọi API trực tiếp.
- Mobile client chưa nâng cấp.
- Partner integration.
- Scheduled retry cũ.
- Event trong broker với thời gian lưu dài.
- Dead-letter queue có khả năng replay.
- Cache giữ payload/schema cũ.

Đừng xóa v1 contract ngay sau khi dashboard gateway hiển thị 100% traffic qua v2. Cần kiểm tra toàn bộ các đường giao tiếp.

## 14. Kiểm thử hợp đồng chéo phiên bản

Mục tiêu là chứng minh từng tổ hợp được hỗ trợ bằng **artifact và cấu hình thực tế**, không chỉ mock theo giả định.

### 14.1. Consumer-driven contract test

Consumer có thể phát hành contract test mô tả những request/response nó thực sự cần. Provider v2 chạy test đó để xác minh vẫn phục vụ được consumer v1. Với event, cũng cần producer/consumer contract và schema registry validation theo đúng chiều dữ liệu.

Lưu ý: contract test thường kiểm tra một phần observable behavior, không tự chứng minh transaction semantics, ordering, retry hoặc bảo mật. Cần thêm integration/end-to-end test.

### 14.2. Dùng consumer binary cũ

Trong Java migration, không biên dịch lại consumer cũ với dependency mới nếu mục tiêu là chứng minh binary consumer đã phát hành vẫn hoạt động. Với API HTTP/message, giữ nguyên:
- Client binary và config hoặc release image thực tế.
- Serializer/deserializer library version của client.
- Request fixture và expected behavior của client.
- JDK của client trong phạm vi hỗ trợ.

Sau đó cho client cũ giao tiếp với server v2. Nếu cần sửa code client để pass, đó là một migration client riêng, không còn là bằng chứng server v2 tương thích với client cũ.

### 14.3. Ma trận thực hành

| Client/producer | Server/consumer | Kịch bản |
|---|---|---|
| Client v1 | Service v1 | Baseline tạo/lấy đơn |
| Client v1 | Service v2 | Request cũ + response mới |
| Client v2 | Service v1 | Feature fallback hoặc version negotiation |
| Client v2 | Service v2 | Chức năng mới |
| Event producer v1 | Consumer v2 | Parse/process event cũ |
| Event producer v2 | Consumer v1 | Unknown field/status/schema behavior |
| Data writer v2 | Reader v1 | Rollback-read test trên schema expanded |
| Retry tới v1/v2 | Shared idempotency store | Không tạo side effect hai lần |

### 14.4. Kịch bản lỗi cần thử

- Unknown fields và missing optional fields.
- Null/empty, number boundary và precision.
- Enum/status mới.
- Timestamps có offset khác nhau và ngày giờ DST.
- Message duplication, delayed delivery, out-of-order events.
- Timeout sau khi server đã commit.
- Mã lỗi và retry policy.
- Token cũ/hết hạn/thiếu claim và mTLS rotation.
- Consumer không nhận được schema registry/broker.
- Rollback code khi database đã có row từ v2.
- Khởi động với version JDK, JSON/proto library, HTTP/TLS stack dự kiến.

Đừng sửa expected fixture chỉ để test pass khi output v2 khác. Phải phân loại khác biệt nào là thay đổi hợp đồng được chấp nhận và khác biệt nào gây breaking.

## 15. Observability khi chạy song song

Một canary v2 có thể không tạo exception nhưng vẫn gây sai nghiệp vụ: tổng tiền không khớp, thời gian giao hàng lệch, số event nhiều hơn, hoặc số lần retry tăng.

### 15.1. Gắn version và correlation

Tối thiểu, mỗi request/event/trace nên có:
- Service name và deployment version.
- Protocol/schema version hoặc capability khi có.
- Correlation/request ID và trace ID.
- Operation name và outcome.
- Retry count, queue lag, deduplication outcome.
- Runtime/JDK version khi cần điều tra sự khác biệt sau migration.

Không đưa raw token, secret, full PII hay payload tài chính vào label metric/log. Số lượng label theo user/order ID rất lớn còn có thể gây cardinality explosion trong monitoring.

### 15.2. Metrics quan trọng

| Metric | Điều cần theo dõi |
|---|---|
| Request success/error rate theo version | v2 có nhiều lỗi hơn v1 không |
| Latency p50/p95/p99 theo operation/version | Có regression do JDK/framework/serialization không |
| 4xx/5xx và error code | Mismatch contract hay auth/rate-limit |
| Serialization/deserialization failure | Unknown field, enum, schema, malformed payload |
| Consumer lag/DLQ size | Consumer mới có bị nghẽn hoặc từ chối event |
| Retry/duplicate/idempotency hit | Dấu hiệu side effect hoặc timeout |
| Data reconciliation mismatch | v1/v2 có ghi/đọc kết quả khác nhau |
| Auth/TLS failure | Client cũ không còn kết nối an toàn |
| Business invariants | Đơn hàng được trả tiền một lần, tổng tiền đúng, không chuyển trạng thái sai |

Khi so sánh version, cần điều chỉnh cohort/traffic mix. Canary chỉ phục vụ nhóm ít rủi ro có thể cho metrics đẹp hơn mà không phản ánh toàn bộ production traffic.

### 15.3. Có tiêu chí dừng rollout

Định nghĩa trước:
- Tỷ lệ lỗi hoặc độ trễ vượt baseline bao nhiêu thì dừng.
- Số reconciliation mismatch được chấp nhận.
- Có hay không sự cố duplicate payment/order.
- Consumer lag tăng tối đa trong khoảng nào.
- Khi nào chuyển traffic về v1.
- Khi nào cần dừng writes và sửa dữ liệu trước rollback.

Một canary không có ngưỡng quyết định rõ ràng chỉ là chuyển traffic theo phần trăm, chưa phải chiến lược giảm rủi ro.

## 16. Rollback không chỉ là quay lại JAR cũ

Rollback ứng dụng là một thao tác deployment. Rollback **hành vi và dữ liệu** đòi hỏi nhiều điều kiện hơn.

Giả sử v2 đã ghi status `AWAITING_REVIEW` mà v1 không hiểu, hoặc đã drop một cột mà v1 yêu cầu. Cho dù load balancer chuyển toàn bộ traffic về v1, hệ thống có thể vẫn lỗi.

Cần xác định:
- V1 còn đọc được mọi row mà v2 có thể ghi trong coexistence window không?
- Broker còn chứa event v2 mà consumer v1 không xử lý không?
- Cache có chứa representation v2 không?
- Có feature flag ngăn v2 tạo state/data mới khi vẫn cần rollback không?
- Có thể disable writes hoặc backfill/reconcile ngược không?
- Sau khi schema contract đã bị xóa, rollback có còn nằm trong phạm vi hỗ trợ không?

### 16.1. Rollback window và điểm không quay lại

Trước khi rollout, công bố mốc:
1. **Rollback-safe:** schema expand và v2 chưa tạo dữ liệu không tương thích.
2. **Guarded rollback:** v2 đã ghi dữ liệu mới nhưng có adapter/reconciliation để v1 đọc.
3. **Forward-only:** đã bỏ cột/endpoint/schema cũ hoặc dữ liệu đã có semantics không thể chuyển ngược an toàn.

Đừng để điểm forward-only xuất hiện âm thầm trong một migration script. Cần quyết định release/operational approval rõ ràng, backup và recovery plan phù hợp.

## 17. Quy trình triển khai gợi ý

### Giai đoạn A: Chuẩn bị contract

1. Inventory request/response, event, DB, cache và giao thức với đối tác.
2. Chốt support window: những client/service version còn chạy.
3. Xác định change nào additive, change nào phá hợp đồng.
4. Ghi schema, error, retry, idempotency, timestamp và security semantics.
5. Viết contract test và fixture dùng binary v1 đã phát hành.

### Giai đoạn B: Expand và tương thích hai chiều

1. Thêm field/DB schema tương thích v1.
2. Triển khai consumer mới đọc được dữ liệu cũ.
3. Đảm bảo producer mới chưa phát field/state không thể xử lý ở v1, hoặc đã có adapter/version route.
4. Cấu hình shared idempotency, event deduplication và monitoring.
5. Xác nhận cả ma trận v1/v1, v1/v2, v2/v1 và v2/v2 theo support policy.

### Giai đoạn C: Canary/parallel run

1. Deploy một phần v2 bằng routing ổn định theo cohort.
2. Dùng read-only shadow nếu phù hợp; không shadow write bừa bãi.
3. Quan sát contract failure, DB consistency, latency và business metrics.
4. Thử timeout/retry, duplicate và rollback-read scenario trên môi trường kiểm soát.
5. Dừng hoặc rollback theo ngưỡng đã phê duyệt.

### Giai đoạn D: Chuyển hoàn toàn

1. Mở traffic v2 theo giai đoạn.
2. Xác minh không còn producer/consumer v1 trong các đường cần ngừng hỗ trợ.
3. Đợi hết thời gian lưu event/retry/DLQ liên quan hoặc có cơ chế adapter xử lý.
4. Backfill/reconcile và xác nhận các invariant.
5. Chỉ sau đó mới xóa field/schema/endpoint cũ và đặt constraint mới.

### Giai đoạn E: Kết thúc migration

1. Xóa adapter/feature flag hết vòng đời khi an toàn.
2. Cập nhật versioning, tài liệu API và client SDK.
3. Pin JDK/runtime/image và dependency đã được xác minh.
4. Lưu bằng chứng contract test, deployment history, reconciliation và rollback decision.
5. Duy trì CI để ngăn breaking change trong support window tiếp theo.

## 18. Bài tập thiết kế: chuyển Orders v1 sang v2

**Bối cảnh:** Orders v1 chạy JDK 11, client đối tác v1 vẫn gửi `POST /orders` và đọc status `CREATED/PAID/CANCELLED`. Orders v2 chuyển lên JDK 21, bổ sung delivery priority và trạng thái `AWAITING_REVIEW`. Hệ thống dùng HTTP/JSON, Kafka và một database chung.

**Yêu cầu:** Hai phiên bản chạy song song ít nhất một chu kỳ release, và cần rollback về v1 khi canary gặp lỗi.

### 18.1. Thiết kế không an toàn

- Deploy v2, lập tức yêu cầu request có `deliveryPriority`.
- v2 phát `AWAITING_REVIEW` trong event hiện tại.
- v2 đổi `totalAmount` sang đơn vị nhỏ hơn mà không đổi field name.
- v2 chuyển cột `status` sang enum DB chỉ có code v2 hiểu.
- Có retry nhưng idempotency key chỉ lưu in-memory.
- Sau một ngày, xóa endpoint v1 và cột cũ.

Các bước này làm hỏng cả HTTP, event, semantic, DB và rollback contract.

### 18.2. Thiết kế chuyển tiếp có kiểm soát

1. Giữ request cũ hợp lệ, default `deliveryPriority=STANDARD` ở v2.
2. Trì hoãn phát `AWAITING_REVIEW` cho đến khi các consumer còn trong support window xử lý được, hoặc phát trên contract/event version riêng.
3. Giữ `totalAmount` và `currency` theo semantics cũ; nếu cần format mới, thêm field được version hóa.
4. Expand DB trước; không bắt buộc cột mới khi v1 còn tạo đơn.
5. Cả v1/v2 dùng cùng kho idempotency và event dedup policy.
6. Bật feature mới theo cohort có routing affinity nếu v1 không biết state mới.
7. Chạy ma trận client/service/event và rollback-read test.
8. Chỉ contract DB/API sau khi consumer v1 đã ngừng hoặc có adapter đáng tin cậy.

### 18.3. Tiêu chí nghiệm thu minh họa

- Client v1 binary gọi được Orders v2.
- Orders v2 xử lý request v1 và tạo response đúng contract v1.
- Event do v2 phát trong giai đoạn canary được consumer v1 đang hỗ trợ xử lý an toàn.
- Retry từ v1 sang v2 không tạo duplicate order/payment.
- Dữ liệu do v2 ghi trong rollback window vẫn được v1 đọc hoặc có quy trình phục hồi đã kiểm chứng.
- Không có regressions về TLS/auth, timestamp hoặc business invariant.
- Có log/metric phân tách version và ngưỡng quyết định rollback rõ.

## 19. Những lỗi thường gặp trong giai đoạn chạy song song

- **Chỉ test v2 với v2:** bỏ qua client cũ và event replay.
- **Tin rằng thêm field luôn compatible:** consumer strict có thể từ chối unknown property.
- **Đổi semantics nhưng giữ cùng field name:** parser thành công nhưng tiền/giờ/trạng thái sai.
- **Thêm enum value quá sớm:** v1 parse lỗi hoặc xử lý sai.
- **Không dùng idempotency chung:** retry qua instance v1/v2 tạo side effect trùng.
- **Nhầm at-least-once thành exactly-once:** message có thể được xử lý lại.
- **Dual-write mà không reconciliation:** data drift trong thời gian dài.
- **Chỉ chuyển traffic ở gateway:** batch, partner, mobile app và event consumer vẫn dùng contract cũ.
- **Bật v2 feature ngay khi deploy v2:** dữ liệu mới có thể phá rollback.
- **Tưởng shadow traffic luôn vô hại:** shadow write có thể gây side effect.
- **Không phân biệt UTC và local time:** JDK/tzdb hoặc default zone mới làm timestamp khác.
- **Không test TLS/auth qua JDK mới:** payload giống nhưng kết nối thất bại.
- **Rollback code sau khi drop schema:** v1 không còn đọc được dữ liệu.
- **Chỉ đo lỗi HTTP:** bỏ sót business invariant, message lag và duplicate transaction.
- **Bỏ endpoint cũ theo release server:** consumer bên ngoài có thể không được nâng cùng thời điểm.
- **Versioning chỉ bằng JDK version:** JVM release không phải contract version.

## 20. Checklist trước khi kết thúc coexistence window

- [ ] Đã liệt kê tất cả client/producer/consumer còn trong support window.
- [ ] Đã có contract rõ cho request, response, event, error, retry và security.
- [ ] Đã kiểm tra các hướng v1→v1, v1→v2, v2→v1, v2→v2 cần hỗ trợ.
- [ ] Đã bảo toàn semantics của các field cũ: unit, precision, null, timezone, status.
- [ ] Unknown field/enum/schema version có policy và test tương ứng.
- [ ] Đã kiểm tra JDK/runtime/client library version thực tế, không chỉ source mới.
- [ ] Idempotency và deduplication hoạt động qua mọi instance/version.
- [ ] Event ordering, replay, retry và DLQ đã được kiểm chứng.
- [ ] Nếu dùng database chung, schema expand cho phép v1 và v2 cùng hoạt động.
- [ ] Backfill/dual-write có cách reconcile và xử lý partial failure.
- [ ] Routing/canary/feature flag không tạo state mà phiên bản còn lại không hiểu.
- [ ] Shadow traffic không gây side effect production ngoài dự kiến.
- [ ] TLS, authn/authz, mTLS/token và dữ liệu nhạy cảm còn được bảo vệ.
- [ ] Có metric/log/trace theo deployment/schema version, không ghi secret/PII bừa bãi.
- [ ] Có ngưỡng dừng canary và runbook rollback với điều kiện dữ liệu cụ thể.
- [ ] Đã xác nhận không còn consumer v1 hoặc đã có adapter trước khi contract schema/API.
- [ ] Đã xử lý event tồn, retry và replay trước khi bỏ schema cũ.
- [ ] Có bằng chứng contract test, integration test và business invariant trên JDK đích.

## 21. Kết luận

Chạy song song dịch vụ cũ và mới trong Java migration không chỉ là bài toán triển khai hai JAR hoặc hai container. Đó là bài toán **duy trì hợp đồng trên đường truyền và ở ranh giới dữ liệu** giữa các phiên bản độc lập. Muốn migration an toàn, cần kiểm soát cả khả năng đọc schema, ý nghĩa field, mã lỗi, authorization, idempotency, event delivery, database evolution và quyền rollback.

Một lộ trình thực tế là **contract-first → expand → tương thích hai chiều → canary/parallel run → reconcile → contract**. Trong suốt support window, hãy test chính consumer/producer cũ với dịch vụ mới, tránh phát dữ liệu không thể hiểu hoặc không thể rollback, theo dõi business invariant và chỉ loại bỏ contract cũ khi đã có bằng chứng mọi consumer liên quan đã chuyển đổi. Nhờ đó, nâng JDK hoặc framework có thể diễn ra từng bước mà không làm gián đoạn giao tiếp giữa những thành phần vẫn đang hoạt động.
