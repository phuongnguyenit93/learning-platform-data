
# Kiểm thử nhiều phiên bản dịch vụ cùng hoạt động

Nâng cấp Java trong một hệ thống phân tán thường không thể thực hiện bằng cách dừng tất cả dịch vụ, thay đồng loạt các JAR rồi khởi động lại. Trên thực tế, nhiều phiên bản của **cùng một dịch vụ** và các **dịch vụ phụ thuộc** có thể hoạt động đồng thời trong quá trình rolling deployment, canary release, blue–green deployment, rollback hoặc khi một nhóm consumer chưa kịp nâng cấp.

Ví dụ, trong lúc nâng một dịch vụ từ JDK 11 lên JDK 21, một replica chạy phiên bản cũ và replica khác chạy phiên bản mới có thể cùng phục vụ request. Một client đã được triển khai từ hôm trước tiếp tục gọi API mới. Một consumer cũ vẫn đọc các event được tạo bởi producer mới. Một ứng dụng cũ và mới cùng truy cập database trong giai đoạn chuyển schema. Một worker cũ đọc job do worker mới ghi vào hàng đợi. Nếu chỉ kiểm thử rằng **mỗi phiên bản tự chạy tốt khi đứng một mình**, những lỗi chỉ xuất hiện trong trạng thái trộn phiên bản sẽ bị bỏ sót.

Bài học thuộc *Java Advance Compatibility Migration*, chương *Kiểm thử hồi quy*, hướng dẫn cách thiết kế **mixed-version compatibility tests**: xác định contract, lập ma trận tương thích, dựng môi trường với nhiều phiên bản, kiểm tra HTTP/gRPC/event/database/state, xử lý rolling deployment và rollback, rồi sử dụng bằng chứng để quyết định phát hành an toàn.

## 1. “Nhiều phiên bản cùng hoạt động” nghĩa là gì?

Một hệ thống có thể cùng lúc có nhiều loại phiên bản:

- **Phiên bản source/artifact:** ví dụ `orders-service 2.4.0` và `2.5.0`.
- **Phiên bản JDK runtime:** ví dụ Java 17 và Java 21.
- **Phiên bản framework:** thế hệ Spring/Jakarta/ORM hoặc thư viện network khác nhau.
- **Phiên bản API contract:** `/v1/orders` và `/v2/orders`, hoặc media type/header version.
- **Phiên bản event/schema:** event cũ và event có field bổ sung.
- **Phiên bản database schema:** bảng/cột/constraint thay đổi dần.
- **Phiên bản giao thức/serialization:** JSON, Protobuf, Avro, Java native serialization, custom binary.
- **Phiên bản cấu hình/tính năng:** feature flags, consumer capabilities, deployment policies.

Không nên đồng nhất “service version 2” với “API v2”. Artifact v2 có thể vẫn cung cấp API v1; một artifact có thể hỗ trợ nhiều schema versions cùng lúc.

### 1.1. Ba tình huống có bản chất khác nhau

| Tình huống | Ví dụ | Câu hỏi kiểm thử |
|---|---|---|
| Nhiều replica của cùng service | Order v1 và Order v2 cùng sau load balancer | Request có hoạt động bất kể replica nào xử lý? |
| Producer và consumer khác version | Billing v1 đọc event Order v2 | Consumer cũ có hiểu event mới? |
| Nhiều service dùng shared state | Order v1 và v2 cùng truy cập một DB | Hai phiên bản có đọc/ghi được schema chuyển tiếp? |

Ngoài ra, một request có thể đi qua **cả chuỗi dịch vụ trộn phiên bản**, như Gateway v2 → Orders v1 → Payments v2. Vì thế, một phép thử chỉ gọi thẳng Orders v2 chưa đủ cho một hệ thống microservices.

### 1.2. Tại sao đây là kiểm thử hồi quy?

Một thay đổi có thể hoàn toàn hợp lệ khi tất cả service cùng được nâng nhưng gây lỗi trong quá trình chuyển đổi:

- Field JSON đổi tên làm consumer cũ không parse được.
- Một cột DB bị xóa khi còn instance cũ đang đọc nó.
- Event mới yêu cầu enum constant mà consumer cũ không biết.
- Token/session format mới không đọc được trên replica cũ.
- Transaction hoặc retry policy khác nhau gây ghi lặp.
- Framework mới có default HTTP serialization hoặc time zone khác.
- JDK mới thay đổi TLS/certificate/charset behavior.
- Một instance mới ghi Java-serialized object mà instance cũ không deserialize được.

Kiểm thử mixed-version nhằm chứng minh hệ thống chịu được **khoảng thời gian nhiều phiên bản cùng tồn tại**, không chỉ trạng thái cuối sau khi nâng xong.

## 2. Bốn loại tương thích cần phân biệt

### 2.1. Backward compatibility

**Bản mới** vẫn chấp nhận dữ liệu/API/hành vi do **bản cũ** tạo hoặc sử dụng.

Ví dụ: Orders v2 vẫn đọc được event `OrderCreated` do v1 gửi; endpoint của v2 vẫn đáp ứng client v1.

### 2.2. Forward compatibility

**Bản cũ** vẫn xử lý được một phần dữ liệu/hành vi do **bản mới** tạo, trong phạm vi contract đã thiết kế.

Ví dụ: consumer v1 có thể bỏ qua trường JSON `deliveryEstimate` mới của v2 mà không lỗi.

Forward compatibility **không tự động có**. Nếu v2 thay field bắt buộc hoặc thêm enum state mà v1 coi là không hợp lệ, consumer v1 có thể thất bại.

### 2.3. Binary compatibility

Một JAR hoặc plugin đã biên dịch trước vẫn liên kết được với API/library mới ở cấp bytecode. Ví dụ method descriptor không đổi.

Tương thích nhị phân **khác** tương thích giao thức mạng. Hai dịch vụ chạy trong hai JVM độc lập có thể giao tiếp bằng JSON dù bytecode của chúng hoàn toàn khác; ngược lại, cùng Java types trong source không bảo đảm JSON wire format tương thích.

### 2.4. Behavioral/semantic compatibility

Request hoặc message vẫn parse được **không có nghĩa** kết quả đúng.

Ví dụ, hai phiên bản đều chấp nhận field `amount` nhưng v1 hiểu là đơn vị tiền cơ sở còn v2 hiểu là đơn vị nhỏ nhất. Đây là lỗi nghiêm trọng dù schema hình thức không đổi.

| Mức tương thích | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Syntax/format | JSON/Protobuf có giải mã được? | Parser từ chối field mới |
| Contract | Endpoint, header, status, schema có hợp lệ? | API đổi status 200 thành 202 ngoài hợp đồng |
| Semantics | Giá trị có cùng ý nghĩa? | Tiền đồng đổi thành xu |
| Operational | Timeout, retry, auth, capacity có đáp ứng? | Retry trùng order |
| State/data | DB/job/session state có đọc được giữa phiên bản? | Schema bị drop sớm |
| Binary | Library/agent đã compile còn link? | `NoSuchMethodError` |

## 3. Tư duy theo “hợp đồng ở ranh giới”, không theo từng repository

Một dịch vụ thường có nhiều ranh giới:

~~~mermaid
flowchart LR
    A["Client v1/v2"] --> B["Gateway v1/v2"]
    B --> C["Orders service v1/v2"]
    C --> D["Payments service v1/v2"]
    C --> E["Database schema chuyển tiếp"]
    C --> F["Message broker"]
    F --> G["Billing consumer v1/v2"]
    C --> H["Shared session/cache"]
~~~

Mỗi đường nối là một **contract riêng**:

- HTTP/gRPC giữa client và service.
- Event giữa producer và consumer.
- Schema/transaction giữa service và database.
- Cache/session record giữa replicas.
- Authentication token/claims giữa auth và consumers.
- Job payload giữa scheduler/worker.
- Health/readiness protocol giữa app và deployment platform.

Khi nâng JDK/framework, một contract có thể bị thay đổi ngoài ý muốn bởi library, serializer hoặc default configuration, dù business source gần như không đổi.

### 3.1. Inventory contract

Một bảng kiểm kê:

| Ranh giới | Producer/owner | Consumer | Format | SLO/rủi ro | Bằng chứng |
|---|---|---|---|---|---|
| `GET /orders/{id}` | Orders | Web/mobile | JSON/HTTP | Client cũ còn nhiều | Contract test |
| `OrderCreated` | Orders | Billing, Search | JSON/Avro | Event lưu nhiều ngày | Replay test |
| `orders` table | Orders | Orders v1/v2 | SQL schema | Cả hai ghi cùng lúc | Mixed DB test |
| Checkout session | Gateway | Gateway v1/v2 | Redis/JSON | Request đổi replica | Session test |
| Access token | Auth | Gateway/Services | JWT hoặc opaque | Roll key/claims | Auth interoperability |
| Email job | Orders | Worker | Queue JSON | Retries và redelivery | Cross-version worker test |

Đừng chỉ liệt kê API công khai. Shared cache, background jobs và migration scripts cũng có thể là những contract thực.

## 4. Lập ma trận phiên bản cơ bản

Giả sử hai release liên tiếp:

- **V1:** đang chạy, dùng JDK 17.
- **V2:** chuẩn bị triển khai, dùng JDK 21.

Ta cần kiểm tra cả hai chiều.

| Client/producer | Server/consumer | Tình huống | Mục tiêu |
|---|---|---|---|
| V1 | V1 | Baseline | Không có hồi quy trước thay đổi |
| V1 | V2 | Client/producer cũ với service mới | Backward compatibility |
| V2 | V1 | Client/producer mới với service cũ | Forward compatibility theo contract |
| V2 | V2 | Trạng thái sau migration | Hệ thống mới hoạt động |
| V1 + V2 | Shared DB/cache | Mixed deployment | State không bị hỏng |
| V2 → V1 rollback | State đã được V2 ghi | Rollback | V1 có thể phục hồi |

Không phải mọi tổ hợp đều bắt buộc hỗ trợ mãi mãi. Nhưng **tổ hợp có thể xảy ra trong rollout/rollback thực tế** phải được công bố và kiểm thử.

### 4.1. Hướng producer/consumer có ý nghĩa

Đối với event:

~~~text
Producer v1 -> Consumer v2
Producer v2 -> Consumer v1
~~~

Đây là hai hướng khác nhau. Một schema mới có thể đọc event cũ tốt nhưng event mới lại làm consumer cũ lỗi.

### 4.2. Đừng chỉ kiểm tra N và N+1 riêng rẽ

Nếu producer v2 tạo ra một giá trị mới, consumer v1 có thể nhận nó trong giai đoạn trộn version. Ngay cả khi API v1 không tự tạo giá trị đó, hệ thống vẫn có thể chuyển giá trị qua database, event hoặc cache.

Một test “v1 + v1” và “v2 + v2” đều xanh vẫn có thể bỏ sót hoàn toàn lỗi này.

## 5. Mô hình rolling deployment

Rolling deployment thay dần các instance, ví dụ:

~~~text
T0: [V1, V1, V1, V1]
T1: [V1, V1, V1, V2]
T2: [V1, V1, V2, V2]
T3: [V1, V2, V2, V2]
T4: [V2, V2, V2, V2]
~~~

Trong thời gian T1–T3, load balancer có thể đưa request tới bất kỳ replica nào. Một request retry có thể được xử lý bởi **phiên bản khác** với lần thử đầu tiên.

### 5.1. Kịch bản phải thử

- Client cũ gọi V2.
- Client mới gọi V1 trong thời gian canary.
- Cùng một user gọi luân phiên V1/V2.
- Request bắt đầu tại V1 rồi retry tới V2.
- Shared session/cache được tạo bởi V2 rồi đọc bởi V1.
- V2 cập nhật DB, V1 đọc kết quả.
- Background task từ V1 và V2 cùng hoạt động.
- Scale-down/termination của V1 diễn ra trong khi request dài.
- Rollback V2 về V1 sau khi V2 đã ghi dữ liệu.

### 5.2. Readiness không đồng nghĩa compatibility

Probe `/health` trả 200 chỉ nói service đủ khỏe theo điều kiện probe. Nó không chứng minh một endpoint có thể được gọi qua nhiều phiên bản hoặc shared state còn tương thích.

Readiness vẫn cần kết hợp:

- Contract tests.
- Stateful integration tests.
- Data/serialization tests.
- End-to-end routing tests.
- Business invariants và SLO.

## 6. Blue–green và canary cũng cần mixed-version testing

**Blue–green** duy trì hai môi trường và chuyển traffic. Nếu traffic hoàn toàn tách biệt, mixed-version requests có thể ít hơn, nhưng database, queue, cache hoặc consumer vẫn có thể được chia sẻ.

**Canary** đưa một tỷ lệ nhỏ request sang V2. Nếu consumer cũ vẫn nhận event mới, tỷ lệ HTTP request nhỏ không giới hạn được phạm vi tác động của một **breaking event schema**.

### 6.1. Câu hỏi trước khi phát hành

1. Hai phiên bản có dùng chung DB không?
2. Một event mới có thể đi tới consumer cũ không?
3. Session được giữ tại client hay shared cache?
4. Retry có thể tới instance version khác không?
5. Background jobs có chạy song song không?
6. Có thể rollback mà không rollback schema/data không?
7. Có long-lived connections như WebSocket/gRPC streams không?
8. Có scheduler hoặc leader election chọn một instance bất kỳ không?

Nếu có, cần kiểm thử tương ứng dù chiến lược deployment không mang tên “rolling”.

## 7. HTTP/JSON: mở rộng contract an toàn

Ví dụ V1 trả:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

V2 muốn bổ sung thời gian giao hàng dự kiến:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED",
  "deliveryEstimate": "2026-11-15T09:00:00Z"
}
~~~

Đây là thay đổi **additive** về mặt JSON. Nhưng consumer cũ có chấp nhận không phụ thuộc cách deserializer được cấu hình.

Nếu client V1 từ chối unknown properties, nó vẫn có thể lỗi khi nhận V2 response.

### 7.1. Consumer có khả năng bỏ qua field chưa biết

Ví dụ dùng Jackson (dependency/framework cần được khai báo riêng):

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderResponseV1(
        String orderId,
        String status) {
}
~~~

Khi parse JSON V2, property `deliveryEstimate` không thuộc record V1 sẽ được bỏ qua nếu Jackson được cấu hình/annotation tương ứng được áp dụng.

Tuy nhiên, đây không phải lời khuyên “ignore toàn bộ dữ liệu không hợp lệ”. Consumer vẫn phải validate **field bắt buộc, kiểu dữ liệu, enum và semantic contract**.

### 7.2. Field mới không phải lúc nào cũng backward compatible

Nếu V2 biến `customerId` từ string thành object:

~~~json
{
  "customerId": {
    "value": "C-55",
    "region": "VN"
  }
}
~~~

trong khi V1 kỳ vọng:

~~~json
{
  "customerId": "C-55"
}
~~~

đó là thay đổi type, không phải additive field. Consumer cũ có thể parse lỗi hoặc xử lý sai.

### 7.3. “Optional” phải được định nghĩa rõ

Một field có thể:

- Vắng mặt.
- Có mặt với `null`.
- Có mặt với chuỗi rỗng.
- Có giá trị default.
- Có giá trị hợp lệ hoặc invalid.

Những tình huống này **không tự tương đương**.

Ví dụ nếu client V1 dùng `null` để biểu thị “chưa có dữ liệu”, V2 chuyển sang bỏ field hoàn toàn có thể làm thay đổi hành vi kiểm tra presence.

### 7.4. Đổi tên field an toàn theo hai pha

Nếu muốn đổi `customerName` thành `displayName`:

1. Producer V2 tạm thời phát cả hai field.
2. Consumers mới được nâng để đọc field mới, có fallback.
3. Telemetry xác nhận consumers cũ không còn phụ thuộc field cũ.
4. Chỉ sau đó mới loại field cũ trong một release có kiểm soát.

Nếu hệ thống có client không thể nâng đồng thời (mobile/offline), thời gian hỗ trợ có thể dài hơn rollout server.

## 8. REST: endpoint, status, headers và pagination cũng là contract

Không chỉ JSON body, thay đổi trong HTTP có thể phá tương thích:

- `GET /orders/{id}` đổi sang route khác.
- Status `200 OK` đổi thành `202 Accepted`.
- Error response không còn chứa field `code`.
- `Content-Type` đổi ngoài khả năng parser của client.
- `Location`, `ETag` hoặc cache headers đổi ngữ nghĩa.
- Pagination token format bị thay.
- Query parameter có default khác.
- Idempotency behavior thay đổi.
- Timeout hoặc body-size limit giảm.
- HTTP redirects bị client cũ không xử lý.

### 8.1. Ví dụ contract table

| Trường hợp | V1 behavior | V2 expectation | Test |
|---|---|---|---|
| Đơn hàng tồn tại | `200` + JSON | Giữ shape cũ, có thể thêm field | V1 client → V2 |
| Không tìm thấy | `404` + error code | Vẫn giữ machine-readable code | V1 client → V2 |
| Tạo đơn hợp lệ | `201` + ID | Không tạo lặp khi retry | V1/V2 clients |
| Idempotency key trùng | Trả kết quả trước | Cùng semantic | Retry đổi replica |
| Pagination token cũ | Đọc được bởi V1 | V2 phải xử lý hoặc có policy hết hạn | Token cũ → V2 |
| Invalid input | `4xx` ổn định | Không đổi thành `5xx` | Both directions |

### 8.2. Versioned endpoint

Một số API cần thay đổi không tương thích có thể dùng versioned routes:

~~~text
GET /api/v1/orders/O-1001
GET /api/v2/orders/O-1001
~~~

Điều này cho phép hai contract tồn tại song song, nhưng không tự xử lý:

- Shared DB schema.
- Event payloads.
- Session data.
- Authentication.
- Dữ liệu do V2 ghi mà V1 phải đọc.

Versioned URL chỉ là một lớp quản lý compatibility, không phải toàn bộ chiến lược.

## 9. Contract tests: producer và consumer cùng hiểu một hợp đồng

**Consumer-driven contract testing** cho phép consumer diễn tả kỳ vọng đối với provider. Provider verification sau đó xác nhận bản mới đáp ứng kỳ vọng đó.

Các công cụ thường gặp gồm Pact hoặc các contract-test giải pháp tương đương, tùy hệ sinh thái. Không nên xem một công cụ cụ thể là bắt buộc; điều cần đảm bảo là **mỗi consumer đang hoạt động có contract tương ứng được kiểm chứng**.

### 9.1. Ví dụ contract

Consumer yêu cầu:

~~~json
{
  "orderId": "O-1001",
  "status": "CREATED"
}
~~~

Provider V2 có thể trả thêm `deliveryEstimate` nếu hợp đồng consumer cho phép field mới. Provider verification cần kiểm tra:

- Endpoint/HTTP method.
- Status và headers quan trọng.
- Field bắt buộc và type.
- Semantics của error.
- Auth/rate-limit behavior khi liên quan.
- Version contract của consumer đang dùng.

### 9.2. Vì sao chỉ kiểm thử provider mới là chưa đủ?

Nếu chỉ chạy tests của V2, các tests có thể đã được cập nhật theo contract mới. Consumer V1 vẫn đang hoạt động lại không được đại diện.

Do đó, trong CI:

1. Lưu các contract đã công bố bởi consumers hiện còn tồn tại.
2. Cho provider candidate V2 verify các contract đó.
3. Cho consumer candidate V2 verify với provider V1 nếu rolling deployment yêu cầu.
4. Đánh giá kịch bản không tương thích có được chặn hay chưa.
5. Tránh xóa contract cũ trước khi telemetry chứng minh consumer cũ đã ngừng dùng.

## 10. Ví dụ Java: HTTP smoke test giữa hai phiên bản

`java.net.http.HttpClient` có thể dùng để kiểm tra endpoint giữa JVM/service versions mà không phụ thuộc framework web của provider.

Ví dụ một test helper đơn giản:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class OrderApiSmoke {
    private OrderApiSmoke() {
    }

    public static void main(String[] args) throws Exception {
        URI base = URI.create(args[0]);

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {
            HttpRequest request = HttpRequest.newBuilder(
                    base.resolve("/api/v1/orders/O-1001"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new AssertionError(
                        "Unexpected HTTP status: " +
                        response.statusCode());
            }

            if (!response.headers()
                    .firstValue("Content-Type")
                    .orElse("")
                    .toLowerCase(java.util.Locale.ROOT)
                    .contains("application/json")) {
                throw new AssertionError(
                        "Expected JSON response");
            }

            System.out.println(response.body());
        }
    }
}
~~~

**Lưu ý về phiên bản Java:** ví dụ dùng `HttpClient` với `try-with-resources`; hỗ trợ `AutoCloseable` của API này tùy JDK release. Nếu muốn chạy cùng source trên những JDK cũ hơn, có thể bỏ phần `try (...)` và sử dụng client theo API khả dụng của target release. Trọng tâm là cấu trúc smoke test, không phải sự tương thích của snippet với mọi JDK.

### 10.1. Smoke test không đủ chứng minh JSON contract

Đoạn code trên chỉ kiểm tra HTTP status/content type và in body. Trong bài test thực, nên parse JSON bằng thư viện được chọn và assert:

- `orderId` không rỗng, đúng ID.
- `status` thuộc tập giá trị consumer hỗ trợ.
- Optional field không làm parser lỗi.
- Error response giữ contract.
- Timestamp/currency có semantics đúng.

Không dùng `String.contains` thay cho JSON parsing trong contract tests production.

### 10.2. Chạy test với cả hai target

Giả sử hạ tầng test có:

~~~text
http://localhost:8081   -> Orders V1 (JDK 17)
http://localhost:8082   -> Orders V2 (JDK 21)
~~~

Consumer V1 và consumer V2 nên được chạy với cả hai endpoint theo compatibility matrix. Không tự suy ra kết quả từ việc hai endpoints đều trả 200 khi gọi bằng `curl`.

## 11. Thay đổi enum và state machine

Enum là nơi dễ xảy ra lỗi tương thích ngữ nghĩa.

V1:

~~~text
OrderStatus = CREATED | PAID | CANCELLED
~~~

V2 thêm:

~~~text
OrderStatus = CREATED | PAID | CANCELLED | REFUNDED
~~~

Nếu consumer v1 làm:

~~~java
OrderStatus status = OrderStatus.valueOf(
        externalStatus);
~~~

thì `REFUNDED` có thể gây `IllegalArgumentException`. Một số client còn có `switch` không có nhánh mặc định hoặc xử lý lỗi theo giả định cũ.

### 11.1. Chiến lược

- Có representation cho unknown/future state khi hợp đồng cho phép.
- Không đổi ý nghĩa của các enum values cũ.
- Không reuse mã giá trị cũ cho nghĩa mới.
- Có policy rõ về feature chỉ phát state mới sau khi consumers đã sẵn sàng.
- Kiểm thử cả valid/unknown state và behavior fallback.
- Không âm thầm map trạng thái rủi ro như `REFUNDED` thành `PAID`.

### 11.2. Feature gating cho giá trị mới

Ngay cả khi V2 được deploy, vẫn có thể tắt việc tạo state `REFUNDED` cho đến khi các consumers được nâng. Nhưng phải kiểm soát **toàn bộ producer paths**, gồm admin tools, background jobs và replay.

Feature flag giúp điều phối nhưng không thay thế contract tests.

## 12. Event-driven systems và schema evolution

Trong hệ thống dùng Kafka, RabbitMQ, Pulsar hoặc broker khác, producer và consumer thường deploy độc lập. Một message mới có thể được đọc bởi:

- Consumer v1 đang chạy.
- Consumer v2 đang canary.
- Consumer offline sau này reconnect.
- Replay job đọc event lịch sử.
- Dead-letter reprocessor dùng version khác.
- Data platform consumer không thuộc nhóm phát triển chính.

### 12.1. Ví dụ event additive

V1:

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "e-100",
  "orderId": "O-1001",
  "totalMinorUnits": 250000
}
~~~

V2:

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "e-100",
  "orderId": "O-1001",
  "totalMinorUnits": 250000,
  "currency": "VND"
}
~~~

Trường `currency` có vẻ additive, nhưng nếu consumer v1 tính toán tiền theo một currency mặc định, việc v2 bắt đầu phát nhiều loại tiền có thể phá semantics dù JSON vẫn parse được.

### 12.2. Producer–consumer matrix

| Producer | Consumer | Điều cần xác nhận |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | Consumer mới đọc event cũ |
| V2 | V1 | Consumer cũ xử lý event mới trong rollout |
| V2 | V2 | Trạng thái đích |
| Event lịch sử | V2 | Replay/backfill |
| V2 retry/redelivery | V1/V2 | Idempotency, không ghi lặp |

### 12.3. Schema Registry và compatibility mode

Với Avro, Protobuf, JSON Schema hoặc schema registry, các chế độ tương thích có thể khác nhau, thường có khái niệm như backward, forward hoặc full compatibility.

**Tên mode không thay thế việc hiểu vai trò reader/writer.** Ví dụ Avro writer schema và reader schema có quy tắc resolution riêng, defaults phải hợp lệ, còn Protobuf có quy tắc bảo toàn field numbers khác JSON.

Khi áp dụng:

1. Ghi rõ schema format và registry config.
2. Ghi writer version, reader version.
3. Kiểm tra cả hướng V1→V2 và V2→V1.
4. Kiểm tra schema evolution rules của công nghệ thực tế.
5. Test message serialization/deserialization thật.
6. Test behavior khi field vắng mặt, unknown hoặc có default.

### 12.4. Không reuse Protobuf field numbers

Với Protocol Buffers, field number là một phần quan trọng của wire contract. Khi xóa field, cần quản lý field number/name theo quy tắc của Protobuf, thường sử dụng `reserved` khi phù hợp, thay vì tái sử dụng số cho ý nghĩa khác.

Đổi field number/type có thể làm các phiên bản giải mã sai hoặc mất dữ liệu. Đây không phải vấn đề chỉ cần đổi tên property Java.

## 13. Idempotency, retries và duplicate delivery

Một event hoặc request có thể được thực hiện lại khi:

- Client timeout rồi retry.
- Load balancer chuyển request sang replica version khác.
- Consumer rebalance.
- Worker crash sau khi side effect thành công nhưng trước khi ack.
- Broker redeliver message.
- Rollback khiến worker cũ tiếp tục xử lý backlog.

Trong các trường hợp này, V1 và V2 phải nhất quán về **idempotency key** và side effect.

### 13.1. Ví dụ API tạo đơn

Request:

~~~http
POST /api/v1/orders
Idempotency-Key: request-123
Content-Type: application/json

{"customerId":"C-9","totalMinorUnits":250000}
~~~

Một lần gọi có thể tới V1, retry tới V2. Nếu hai version dùng hai kho idempotency khác nhau hoặc tạo key theo thuật toán không tương thích, hệ thống có thể tạo **hai đơn hàng**.

### 13.2. Test tình huống cụ thể

1. Gửi request đầu tiên tới V1.
2. Giả lập client không nhận response dù server đã commit.
3. Retry cùng key tới V2.
4. Assert chỉ có một business order/side effect.
5. Đổi hướng: V2 trước, V1 sau.
6. Test concurrent retries.
7. Kiểm tra retention/TTL của key.
8. Xác minh response mapping và error consistency.

Nếu idempotency behavior thay đổi giữa release, migration phải có kế hoạch state sharing hoặc feature gating.

## 14. Database schema: expand–migrate–contract

Đây là lớp dễ làm rollback thất bại nhất. Trong quá trình rolling deployment, V1 và V2 có thể cùng đọc/ghi **một schema**.

Giả sử V1 dùng:

~~~sql
CREATE TABLE orders (
    id VARCHAR(40) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

V2 muốn tách tên thành `first_name` và `last_name`. Nếu trực tiếp xóa `customer_name` trong migration đầu tiên, V1 còn đang chạy có thể thất bại.

### 14.1. Quy trình ba pha

**Expand:** bổ sung cấu trúc mới, giữ nguyên cấu trúc V1 đang phụ thuộc.

~~~sql
ALTER TABLE orders
    ADD COLUMN first_name VARCHAR(100);

ALTER TABLE orders
    ADD COLUMN last_name VARCHAR(100);
~~~

**Migrate:** backfill dữ liệu cũ và triển khai code V2 biết đọc/ghi an toàn trong giai đoạn chuyển tiếp.

**Contract:** chỉ sau khi không còn consumer nào dùng `customer_name`, mới loại cột cũ theo kế hoạch.

~~~mermaid
flowchart TD
    A["Schema S1: V1 dùng customer_name"] --> B["Expand S2: thêm first_name/last_name"]
    B --> C["V1 và V2 cùng chạy trên S2"]
    C --> D["Backfill + dual-read/write hoặc adapter"]
    D --> E["Xác nhận V1 đã rút hết"]
    E --> F["Contract S3: bỏ cột cũ"]
~~~

### 14.2. Expand phải thực sự tương thích

Không phải mọi `ALTER TABLE ADD COLUMN` đều an toàn. Ví dụ thêm cột `NOT NULL` không default có thể khiến những lệnh `INSERT` của V1 thất bại.

Tương tự:

- Thêm unique constraint có thể chặn data đang tồn tại.
- Đổi type có thể làm driver/ORM cũ xử lý khác.
- Đổi default ảnh hưởng writes của V1.
- Đổi trigger có thể ảnh hưởng cả hai version.
- Index creation hoặc backfill lớn có thể gây lock/load.

Cần test **V1 writes** trên schema sau expand, không chỉ V2 đọc dữ liệu.

### 14.3. Dual-write có rủi ro

Nếu V2 ghi cả cột cũ và mới, phải xác định:

- Ai là source of truth?
- Có thể ghi không đồng bộ không?
- Nếu ghi một bên thành công, bên kia thất bại thì sao?
- V1 update cột cũ, V2 có thấy thay đổi ở cột mới không?
- Có thể backfill khi vẫn đang có writes không?
- Khi nào ngừng dual-write?

Một số migration cần trigger, change-data-capture hoặc dữ liệu được derive tại runtime. Không nên áp dụng “dual-write tất cả” mà không có consistency strategy.

### 14.4. Rollback sau schema migration

Rollback V2 về V1 **không đồng nghĩa rollback database schema**. Nếu V2 đã ghi dữ liệu theo dạng mới mà V1 không hiểu, việc đổi lại container image có thể gây lỗi hoặc mất thông tin.

Một quy tắc thực dụng là duy trì **rollback-compatible schema window** cho đến khi quyết định không còn cần rollback về V1.

## 15. Migrations phải tương thích với nhiều code versions

Flyway, Liquibase hoặc cơ chế migration SQL riêng có thể chạy khi app khởi động. Nếu V1 và V2 cùng khởi động, cần tránh:

- Hai instance chạy migration cạnh tranh.
- V2 contract/drop schema quá sớm.
- V1 ORM tự động sửa schema về trạng thái cũ.
- Version migration không được V1 hiểu.
- DB lock làm readiness/rollout timeout.
- Trigger/default mới thay đổi semantics cho V1.

### 15.1. Phân tách migration execution

Trong một số hệ thống, migration nên được chạy thành **một deployment step có kiểm soát** trước khi đưa V2 traffic. Các hệ thống khác dùng migration framework có locking và orchestration phù hợp.

Dù chọn mô hình nào, phải có kịch bản:

~~~text
Schema expanded
-> V1 vẫn hoạt động
-> V2 được deploy
-> V1/V2 cùng hoạt động
-> Rollback V2 vẫn an toàn
-> Chỉ contract schema khi V1 đã hết
~~~

### 15.2. Kiểm thử transaction boundaries

Nếu V2 thay ORM/JPA version hoặc transaction isolation, hai version có thể ghi cùng entity theo cách khác. Test nên bao gồm:

- Optimistic locking/version column.
- Concurrent update conflict.
- Retry sau deadlock.
- Transaction rollback.
- Duplicate insert prevention.
- Soft-delete semantics.
- Time zone và timestamp precision.
- Null/default values.
- Database driver behavior khi đổi JDK/framework.

Không được xem hai version cùng `SELECT` thành công là bằng chứng transaction semantics tương thích.

## 16. Cache, session và state chia sẻ

Một shared cache như Redis có thể chứa:

- Session data.
- Serialized DTO.
- Pagination/continuation tokens.
- Feature/permission snapshots.
- Rate-limit counters.
- Idempotency records.
- Locks và lease state.

Nếu V2 thay format record nhưng V1 còn đọc, lỗi có thể chỉ xuất hiện khi một request đi từ V2 sang V1.

### 16.1. Session-format matrix

| Session được ghi bởi | Session được đọc bởi | Điều cần kiểm tra |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | New app vẫn nhận session cũ |
| V2 | V1 | Rollback/traffic mix an toàn |
| V2 | V2 | New behavior |
| Session hết hạn | V1/V2 | TTL, logout và invalidation |

### 16.2. Tránh Java native serialization ở shared state nếu không quản lý contract

`Serializable`/`ObjectInputStream` gắn với class binary names, `serialVersionUID` và object graph của Java. Một object do V2 serialize có thể không deserialize được trên V1 nếu class shape hoặc dependency đổi.

Ngoài compatibility, native Java serialization còn có rủi ro bảo mật nếu deserialize dữ liệu không đáng tin. Đối với cache/session liên dịch vụ, thường nên cân nhắc một **format có schema và versioning rõ**.

Nếu hệ thống legacy buộc phải dùng Java serialization, cần explicit tests cho từng cặp runtime/artifact và kiểm soát input bằng chính sách phù hợp.

### 16.3. Cache key cũng là contract

Nếu V1 ghi:

~~~text
order:O-1001
~~~

nhưng V2 đọc:

~~~text
orders:v2:O-1001
~~~

có thể xảy ra cache miss hoặc state inconsistency. Tách namespace cache có thể là chiến lược hợp lý, nhưng cần hiểu tác động tới session, rate limit và idempotency. Không phải mọi cache miss đều vô hại.

## 17. Authentication, token và security protocol giữa phiên bản

Trong rollout, Auth v2 có thể phát token mà Gateway v1 hoặc downstream v1 chưa hiểu.

Những thay đổi cần test:

- JWT signing algorithm/key rotation.
- `kid` và key discovery.
- Audience/issuer changes.
- Claims mới hoặc claims bị đổi type.
- Token expiry và clock skew.
- Certificate truststore/TLS defaults sau JDK upgrade.
- Cookie name, domain, SameSite/Secure.
- CSRF token/session format.
- Permission/role semantics.
- HTTP header normalization qua framework mới.

### 17.1. Key rotation theo cửa sổ tương thích

Một chiến lược thường gặp:

1. Consumers hỗ trợ verify cả key cũ và key mới.
2. Auth producer bắt đầu ký bằng key mới.
3. Chờ token cũ hết hạn và quan sát compatibility.
4. Chỉ sau đó mới loại key cũ.

Không áp dụng thứ tự ngược nếu gateway cũ còn hoạt động.

### 17.2. Security compatibility không có nghĩa giữ lỗ hổng

Một hệ thống cũ có thể chỉ hỗ trợ TLS/cipher suite đã bị loại khỏi chính sách bảo mật mới. Không nên “đảm bảo mixed-version” bằng cách hạ yêu cầu security vô thời hạn.

Cần kế hoạch nâng dependencies/clients trước, có cửa sổ chuyển đổi được kiểm soát và chặn các client thực sự không còn được hỗ trợ.

## 18. gRPC và Protobuf

Với gRPC, các ranh giới tương thích gồm:

- Service/method names.
- Protobuf messages và field numbers.
- Enum values.
- Streaming semantics.
- Status codes/metadata.
- Deadlines/retries.
- Compression/interceptors.
- TLS và certificate config.

### 18.1. Ví dụ schema tiến hóa

V1:

~~~proto
syntax = "proto3";

message OrderReply {
  string order_id = 1;
  string status = 2;
}
~~~

V2 additive:

~~~proto
syntax = "proto3";

message OrderReply {
  string order_id = 1;
  string status = 2;
  string currency = 3;
}
~~~

Trong Protobuf, field numbers là phần quan trọng của wire contract. Không đổi ý nghĩa hoặc reuse một field number đã được phát hành.

### 18.2. Kiểm thử streaming

Một gRPC stream có thể được mở bởi client V1 tới server V1, sau đó deployment bắt đầu. Cần kiểm tra:

- Stream đang mở có được drain hoặc kết thúc hợp lệ?
- Client có reconnect tới V2 không?
- Resume cursor/token có tương thích không?
- Backpressure và deadline có đổi không?
- Event ordering có giữ nguyên khi reconnect không?
- Server mới có chấp nhận metadata của client cũ không?

Unary RPC test thành công không bảo đảm streaming upgrade an toàn.

## 19. Long-lived connections: WebSocket, SSE và subscriptions

Một HTTP request ngắn thường sống qua một replica duy nhất. Nhưng WebSocket, Server-Sent Events, gRPC streams hoặc long polling có thể kéo dài qua nhiều pha rollout.

### 19.1. Rủi ro

- Deployment tắt V1 khi connection còn mở.
- Client reconnect sang V2 với resume token do V1 cấp.
- Message schema thay giữa stream.
- Stateful subscription cursor không được chia sẻ.
- Event bị lặp hoặc mất khi reconnect.
- Một client cũ không hiểu command mới.
- Sticky session giữ user ở V1 lâu hơn dự kiến.

### 19.2. Bài test

1. Mở connection với V1.
2. Gửi/nhận message baseline.
3. Triển khai V2 đồng thời.
4. Giả lập termination/drain của V1.
5. Client reconnect vào V2.
6. Assert resume position, ordering và no-loss/no-duplicate policy.
7. Thử client V2 kết nối vào V1 nếu có thể.
8. Thử rollback và repeated reconnect.

Cần định nghĩa contract rõ ràng về **at-least-once, at-most-once hoặc exactly-once effect** nếu hệ thống tuyên bố điều đó; “không lặp” không tự có khi kết nối lại.

## 20. Java/JDK upgrade ảnh hưởng mixed-version như thế nào?

Hai dịch vụ có thể giao tiếp qua HTTP/JSON nên không cần chạy cùng Java major version. Tuy nhiên, khi nâng JDK có các thay đổi gián tiếp:

- Default charset và cách đọc file/headers trong code legacy.
- Locale/CLDR formatting của số, tiền, thời gian.
- TLS/security providers và certificate validation.
- HTTP client implementation/version.
- XML/JSON serialization dependencies.
- Time zone database.
- JDBC driver/ORM behavior.
- Concurrency/threading và timeout.
- JVM GC/latency gây retry/timeouts.
- Libraries bị loại khỏi JDK hoặc module access thay đổi.
- Jakarta EE namespace generation khi nâng framework cùng lúc.

### 20.1. Không truyền Java object identity qua network

Client Java 17 và server Java 21 không cần có cùng `Class<?>` object để trao đổi JSON. Wire contract mới là trọng tâm. Nhưng nếu dùng Java native serialized objects hoặc RMI/remote Java-type protocol, binary/class compatibility trở thành vấn đề quan trọng.

### 20.2. javax và jakarta có thể cùng tồn tại qua network nhưng không cùng classpath

Một service cũ dùng `javax.persistence` và service mới dùng `jakarta.persistence` vẫn có thể giao tiếp qua JSON nếu HTTP contract tương thích. Nhưng khi trộn hai framework generation **trong cùng JVM/host classpath**, vấn đề binary names và container APIs khác đi.

Không nhầm **tương thích giữa tiến trình qua giao thức** với **khả năng dùng chung classloader hoặc một framework API**.

### 20.3. Các test JDK cần riêng

Ngoài mixed-version business tests, cần:

- TLS handshake với peer/version thực.
- Charset/locale/timezone roundtrip.
- DB driver connectivity.
- Service startup và module availability.
- Serialized payload fixtures cũ/mới.
- Performance p95/p99 và timeout behavior.
- Graceful shutdown/draining.
- Java agent/observability compatibility.

Một phiên bản có cùng API behavior nhưng latency chậm hơn có thể gây bùng nổ retry và phá invariant khi chạy chung.

## 21. Thiết kế fixture nhiều phiên bản

Một môi trường test có thể có:

~~~text
Client V1 / Client V2
          |
    Gateway / router
      /        \
 Orders V1   Orders V2
     \          /
       Shared DB
          |
      Message broker
      /          \
 Consumer V1   Consumer V2
~~~

Điều quan trọng là test runner có thể **chọn rõ endpoint/consumer** để ép các tổ hợp phiên bản.

### 21.1. Không chỉ test qua load balancer ngẫu nhiên

Nếu gọi 100 request tới một URL chung, có thể hầu hết request vào cùng một replica. Khi đó không thể chứng minh cả V1→V2 và V2→V1 đã được thử.

Nên có:

- Endpoint trực tiếp tới từng deployment trong test environment.
- Version header/debug metadata chỉ dùng nội bộ test.
- Router rules ép request tới version cụ thể.
- Trace/log xác nhận request đã qua phiên bản dự kiến.

Không nên lộ endpoint nội bộ hoặc header debugging chứa thông tin nhạy cảm cho public clients.

### 21.2. Dữ liệu fixture phải đại diện

Test data cần:

- Record tạo bởi V1.
- Record tạo bởi V2.
- Record được cập nhật xen kẽ.
- Null/empty/unknown fields.
- Unicode và locale khác nhau.
- Timestamp cạnh DST/time-zone boundaries khi liên quan.
- Tiền tệ và số thập phân chính xác.
- Pagination tokens cũ.
- Session/token cũ.
- Event retries và duplicates.
- Dữ liệu lớn hoặc nhiều nested fields.

Nếu chỉ tạo dữ liệu mới bằng V2, có thể không phát hiện được vấn đề đọc lịch sử.

## 22. Dùng containers để dựng môi trường mixed-version

Docker Compose, Kubernetes namespaces hoặc Testcontainers đều có thể hỗ trợ tạo nhiều phiên bản cùng lúc. Điều cần quản trị là **immutable image tags và version chính xác**.

Ví dụ Compose ở mức cấu trúc:

~~~yaml
services:
  orders-v1:
    image: registry.example/orders:1.9.0
    environment:
      DATABASE_URL: "jdbc:postgresql://db:5432/app"
      SERVICE_INSTANCE_VERSION: "v1"
    depends_on:
      - db

  orders-v2:
    image: registry.example/orders:2.0.0
    environment:
      DATABASE_URL: "jdbc:postgresql://db:5432/app"
      SERVICE_INSTANCE_VERSION: "v2"
    depends_on:
      - db

  db:
    image: postgres:PINNED_VERSION
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test-only-password
~~~

Đây là **mẫu minh họa**, chưa phải file production/test chạy được ngay: cần thay image tags hợp lệ, cấu hình network/ports/health checks, secrets và database readiness. Không dùng credential test trong production.

### 22.1. Không dùng latest trong compatibility tests

Nếu dùng image tag `latest`, một test hôm nay và ngày mai có thể chạy hai artifact khác nhau. Cần pin:

- Image digest hoặc immutable tag.
- JDK distribution/build.
- DB version.
- Broker version.
- Schema migration revision.
- Framework/service versions.
- Configuration/feature flags.

### 22.2. Readiness trước khi bắt đầu test

`depends_on` kiểu đơn giản không nhất thiết đảm bảo DB đã sẵn sàng cho kết nối trên mọi setup. Test harness cần đợi health/readiness tương ứng, tránh flakiness do startup race.

### 22.3. Tách test fixtures khỏi dữ liệu production

Mixed-version tests có thể làm schema migration hoặc ghi dữ liệu không tương thích. Chạy trên database/queue/cache cô lập, resettable và không dùng tài nguyên production thật trừ khi có kế hoạch thử nghiệm an toàn riêng.

## 23. Ví dụ test matrix có điều khiển

Một bộ test logic:

~~~text
tests/
  contract/
    client_v1_to_orders_v2
    client_v2_to_orders_v1
  events/
    producer_v1_consumer_v2
    producer_v2_consumer_v1
    replay_old_events_consumer_v2
  state/
    write_v1_read_v2
    write_v2_read_v1
    concurrent_write_v1_v2
  deployment/
    mixed_replica_routing
    retry_switches_replica
    rollback_after_v2_write
    graceful_shutdown
~~~

### 23.1. Ghi rõ expected outcome

Không phải mọi hướng phải là PASS theo nghĩa “tính năng mới đầy đủ”. Ví dụ client V2 gọi server V1 có thể nhận **một lỗi capability-not-supported có hợp đồng rõ**, thay vì server tự hiểu tính năng chưa được phát hành.

Một expected outcome hợp lệ có thể là:

- Tính năng cũ hoạt động như trước.
- Tính năng mới bị vô hiệu khi gọi bản cũ.
- Client được server báo version/capability không hỗ trợ theo contract.
- Không ghi dữ liệu sai.
- Không crash hoặc retry vô hạn.
- Không leak thông tin.

**Fail có kiểm soát** có thể chấp nhận; silent data corruption thì không.

### 23.2. Gate theo tổ hợp thực tế

Khi V1 đã được rút hoàn toàn và không còn rollback về V1, có thể bỏ một số compatibility tests trong pipeline thường xuyên. Nhưng cần bằng chứng về fleet/consumers chứ không chỉ dựa vào ngày phát hành.

## 24. Consumer-driven tests và integration tests bổ sung cho nhau

Contract tests nhanh và phù hợp chạy mỗi PR, nhưng không bao phủ:

- Database schema coexistence.
- Retry/idempotency across replicas.
- Real broker behavior.
- Authentication/TLS.
- Transactions.
- Timeouts/resource limits.
- Service mesh/load balancer routing.
- Graceful shutdown.
- Data migration/replay.

Vì vậy, kiến trúc kiểm thử hợp lý gồm:

| Tầng | Mục tiêu | Tần suất gợi ý |
|---|---|---|
| Unit tests | Logic và serialization functions | Mỗi commit |
| Contract tests | API/schema giữa consumer/provider | Mỗi PR hoặc build |
| Component tests | Service với DB/broker giả hoặc container | CI thường xuyên |
| Mixed-version integration | Hai phiên bản cùng state/broker | Trước release, nightly khi có nhiều tổ hợp |
| Deployment rehearsal | Rolling/canary/rollback | Release pipeline |
| Production canary observation | SLO và lỗi thực tế | Khi rollout |

Tần suất thực tế tùy tốc độ phát hành và chi phí môi trường; không phải một tiêu chuẩn cố định.

## 25. Feature flags và thay đổi có hai pha

Một bản V2 có thể chứa code hỗ trợ field/state mới nhưng chưa phát ra vì consumer V1 chưa sẵn sàng.

Ví dụ:

~~~text
Deploy V2 with new field reader
  -> Upgrade consumers to accept new field
  -> Enable new field writer in producers
  -> Observe
  -> Retire old format only after all consumers migrate
~~~

### 25.1. Reader trước, writer sau

Một nguyên tắc phổ biến khi schema evolution là làm consumers **đọc được định dạng mới trước khi producers bắt đầu phát định dạng đó**.

Nhưng cần xét rollback:

- Nếu V2 producer đã ghi data mới rồi rollback V1 reader, V1 có đọc được không?
- Nếu không, cần giữ feature write tắt đến khi mất nhu cầu rollback hoặc bổ sung backward support.

### 25.2. Feature flags có thể lệch giữa replicas

Khi V1 và V2 cùng chạy, một flag bật ở V2 nhưng V1 không biết có thể khiến shared data không nhất quán. Flag rollout phải có owner, scope và capability contract rõ.

### 25.3. Không gắn compatibility với deployment order thủ công

Một kế hoạch “phải deploy A trước B” có thể hợp lý, nhưng CI/release automation nên kiểm chứng điều kiện thay vì phụ thuộc việc con người nhớ thứ tự.

## 26. Rollback là một chiều tương thích độc lập

Rollback thường bị kiểm thử ít hơn rollout.

Kịch bản:

1. V1 đang chạy.
2. Expand schema.
3. Deploy V2.
4. V2 ghi data/event/session mới.
5. Phát hiện lỗi performance.
6. Rollback toàn bộ instances về V1.
7. V1 phải đọc/xử lý state mà V2 đã tạo.

Nếu bước 7 thất bại, rollback application image có thể làm hệ thống tệ hơn.

### 26.1. Test rollback về mặt dữ liệu

- V1 đọc row được V2 tạo.
- V1 đọc event V2 đã phát.
- V1 phục hồi/retry job V2 đã enqueue.
- V1 đọc session do V2 cập nhật.
- V1 xử lý token do Auth V2 cấp.
- V1 không xóa mất field mới khi update.
- V1 không chạy schema migration ngược gây mất dữ liệu.

### 26.2. Khi không thể rollback trực tiếp

Có những migration breaking mà V1 không thể đọc state mới. Khi đó cần thiết kế một trong các phương án:

- Roll-forward only với điều kiện rất chặt.
- Giữ compat writer lâu hơn.
- Dùng adapter/downgrade transform được kiểm chứng.
- Tách data stores hoặc versioned data.
- Có backup/restore và downtime plan.
- Thực hiện migration lớn trong cửa sổ bảo trì được duyệt.

Điều quan trọng là **công bố giới hạn**, không giả định rollback luôn có thể.

## 27. Test concurrency và những business invariants

Mixed-version systems dễ gây lỗi khi logic concurrency khác nhau.

Ví dụ invariant:

~~~text
Một idempotency key chỉ tạo tối đa một order.
Số dư không được âm ngoài policy.
Một payment chỉ được capture một lần.
Một inventory reservation không được phát hành hai lần.
Một event outbox chỉ được xử lý với exactly-once business effect.
~~~

Nếu V1 và V2 sử dụng lock key khác hoặc một version đã đổi transaction boundary, test tuần tự có thể vẫn PASS.

### 27.1. Kịch bản đồng thời

- V1/V2 cùng cập nhật một order.
- V1 retry khi V2 đang commit.
- Cả hai instances cùng xử lý một scheduled job.
- Consumer rebalance khi chuyển version.
- Lock lease hết hạn giữa hai version.
- Optimistic-locking exception và retry.
- Outbox publisher v1/v2 cùng nhìn một record.

### 27.2. Assert ở dữ liệu cuối cùng

Không chỉ assert HTTP `200`. Sau workload, kiểm tra database/event sink để chứng minh invariant như số order, số payments và trạng thái cuối.

## 28. Background jobs và scheduler

Nhiều dịch vụ vừa phục vụ HTTP vừa chạy background jobs. Khi hai version hoạt động, job system có thể bị bỏ sót trong ma trận.

Những rủi ro:

- V1 không hiểu job type do V2 tạo.
- V2 thay JSON fields trong queue payload.
- Cả hai version cùng chạy singleton scheduled job.
- Job retry vượt qua phiên bản khác.
- Distributed lock key thay đổi.
- Job result được ghi dạng V2 mà V1 không đọc được.
- Dead-letter replay sau rollback.

### 28.1. Tách scheduler và worker nếu cần

Một chiến lược kiến trúc là quản lý scheduler singleton độc lập với worker fleet, hoặc có leader election/lock được hỗ trợ. Khi nâng version, test quyền sở hữu job và khả năng reclaim của lock.

Không chỉ đặt scheduler ở một instance “do may mắn” trong môi trường test.

## 29. Quan sát hệ thống trong mixed-version rollout

Để biết lỗi có liên quan phiên bản nào, cần telemetry gắn đúng context:

- Service name và artifact version.
- JDK vendor/version.
- Framework/config version nếu liên quan.
- Deployment environment, cluster/region.
- Instance/pod identity.
- Trace ID/correlation ID.
- API/schema version.
- Event type và producer version.
- Retry attempt/idempotency key nếu được phép và đã loại thông tin nhạy cảm.
- DB migration revision.
- Feature flag state.

### 29.1. Tránh labels có cardinality quá cao

Không đưa arbitrary user IDs, raw URLs có dữ liệu cá nhân hoặc idempotency key duy nhất cho từng request thành metric labels vì sẽ tăng cardinality và rủi ro dữ liệu.

Version/service/deployment labels có thể hữu ích; trace IDs và request-specific details phù hợp hơn ở tracing/logs có bảo vệ.

### 29.2. So sánh theo phiên bản

Một dashboard nên cho phép thấy:

~~~text
HTTP error rate V1 vs V2
Request latency p99 V1 vs V2
DB failures by version
JSON/Protobuf deserialization errors by version
Queue retry/DLQ by consumer version
Authentication failures by version
GC/CPU/memory by JDK version
~~~

Không chỉ xem tổng error rate; canary 5% traffic bị lỗi 30% có thể bị che bởi tổng traffic.

### 29.3. Event schema failures cần alert

Nếu V1 consumer không parse được một event V2, có thể xuất hiện retry vô hạn hoặc dead-letter queue tăng mà HTTP dashboards vẫn xanh. Cần monitoring độc lập cho queue lag, deserialization errors và DLQ volume.

## 30. CI pipeline: các mức kiểm thử

Một pipeline gợi ý:

~~~mermaid
flowchart TD
    A["Candidate V2 commit"] --> B["Unit + serialization tests"]
    B --> C["Consumer/provider contract verification"]
    C --> D["Build immutable V2 artifact"]
    D --> E["Start V1 + V2 + DB/broker"]
    E --> F["Run version matrix + state tests"]
    F --> G["Simulate rolling + rollback"]
    G --> H{"Contracts, invariants, SLO đạt?"}
    H -->|Có| I["Canary và theo dõi production"]
    H -->|Không| J["Chặn release, phân loại lỗi"]
~~~

### 30.1. Bộ test nhanh trên mỗi PR

- Serializer compatibility fixtures.
- API contract verification.
- Schema migration expand checks.
- Unit tests cho version fallback.
- Một số consumer/provider combinations quan trọng.

### 30.2. Bộ test trước release

- V1/V2 containers cùng DB/queue.
- Rolling deployment rehearsal.
- Concurrent writes.
- Event replay và retries.
- Token/session continuity.
- Long-running jobs/streams.
- Rollback sau khi V2 đã tạo state.
- Performance và SLO comparison trên JDK đích.

### 30.3. Kết quả phải gắn artifact

Không nên nói “V2 tests xanh” nếu V2 image được rebuild ngầm với dependency khác trước khi release. Ghi image digest, JDK update, DB/broker version và test report.

## 31. Một mẫu cấu hình test matrix

Ví dụ tài liệu ma trận:

~~~yaml
release_candidate:
  service: orders
  artifact: "orders:2.0.0"
  runtime: "JDK 21 approved update"

baseline:
  artifact: "orders:1.9.0"
  runtime: "JDK 17 approved update"

compatibility_window:
  allow_rolling_mix: true
  rollback_to_baseline: true

tests:
  - id: old-client-new-server
    client: v1
    server: v2
    expected: "Existing API contract preserved"

  - id: new-client-old-server
    client: v2
    server: v1
    expected: "Legacy capabilities work; new ones gated"

  - id: new-producer-old-consumer
    producer: v2
    consumer: v1
    expected: "Schema accepted or feature remains disabled"

  - id: new-write-old-read
    writer: v2
    reader: v1
    expected: "Rollback-compatible state"

  - id: mixed-replica-retry
    first_attempt: v1
    retry: v2
    expected: "At most one business order created"
~~~

Đây là **mẫu tài liệu**, không phải cấu hình được một test runner cụ thể hiểu sẵn. Trong dự án thực, các test IDs nên map tới scripts/integration tests có evidence kiểm chứng.

## 32. Những sai lầm thường gặp

### 32.1. “V1 và V2 đều xanh unit tests nghĩa là tương thích”

Không đúng. Lỗi có thể chỉ xuất hiện khi phiên bản cũ đọc dữ liệu/response do phiên bản mới tạo.

### 32.2. “API thêm field là luôn backward compatible”

Không chắc. Deserializer strict, trường mặc định và semantics có thể làm client cũ lỗi.

### 32.3. “Chỉ test client cũ với server mới”

Thiếu hướng **client mới với server cũ**, nhất là trong canary, retry hoặc khi các service deploy độc lập.

### 32.4. “Rolling deployment chỉ cần readiness probe”

Readiness không chứng minh payload/database/session compatibility.

### 32.5. “Schema migration có thể drop cột sau khi deploy V2 thành công”

Nếu V1 vẫn còn chạy hoặc rollback về V1 còn được phép, drop sớm có thể phá ứng dụng.

### 32.6. “Rollback chỉ cần đổi lại container image”

Không đúng nếu V2 đã ghi state mà V1 không đọc được.

### 32.7. “Event additive không thể gây hại”

Một field hoặc enum mới có thể đổi business semantics dù parser cũ bỏ qua field.

### 32.8. “Idempotency được xử lý trong từng instance là đủ”

Nếu retry chuyển replica/version, idempotency cần hợp đồng và state coordination phù hợp.

### 32.9. “Có versioned API URL thì mọi thứ tương thích”

Database, event, session, token, background jobs vẫn có thể bị phá.

### 32.10. “Java 17 và Java 21 không thể chạy cùng trong hệ thống”

Các JVM độc lập có thể giao tiếp qua protocol ổn định. Cần kiểm thử contract, JDK/security/serialization differences, không buộc mọi service dùng cùng Java version chỉ vì giao tiếp HTTP.

### 32.11. “Giữ binary compatibility tức giữ wire compatibility”

Không tương đương. Bytecode class/method signatures và JSON/gRPC/event contracts là những lớp khác nhau.

### 32.12. “Canary 1% không gây ảnh hưởng dữ liệu chung”

Một canary nhỏ vẫn có thể phát event mới vào shared topic hoặc migrate shared DB, ảnh hưởng 100% consumers.

### 32.13. “Một parser không lỗi là đủ”

Có thể parse đúng cú pháp nhưng hiểu sai tiền tệ, đơn vị, timestamp, enum hoặc quyền truy cập.

### 32.14. “Dùng latest cho test environment cho tiện”

Làm kết quả khó tái hiện, vì baseline có thể thay đổi mà test name không đổi.

### 32.15. “Có feature flag thì không cần compatibility tests”

Flag sai scope hoặc được bật bởi một producer phụ có thể vẫn phát dữ liệu không tương thích.

### 32.16. “Chỉ kiểm thử HTTP mà không kiểm thử queue/job”

Background tasks và event consumers có thể nhận dữ liệu của các version khác dù traffic HTTP bình thường.

## 33. Checklist triển khai mixed-version regression tests

### Xác định phạm vi

- [ ] Đã ghi rõ artifact versions và JDK runtime versions.
- [ ] Đã xác định rolling/canary/blue–green và rollback topology.
- [ ] Đã liệt kê tất cả consumers, producers và shared state.
- [ ] Đã xác định cửa sổ V1/V2 cùng chạy dài bao lâu.
- [ ] Đã công bố tổ hợp được hỗ trợ và tổ hợp chỉ “fail có kiểm soát”.
- [ ] Đã pin image digest, config, DB/broker versions.

### API và protocol

- [ ] V1 client gọi V2 provider thành công với contract cũ.
- [ ] V2 client gọi V1 provider theo contract/capability policy.
- [ ] HTTP status, headers, error codes và pagination ổn định.
- [ ] JSON unknown/missing/null/enum cases được kiểm tra.
- [ ] gRPC/Protobuf schema, field numbers và metadata được kiểm chứng nếu dùng.
- [ ] Long-lived streams/reconnect được test.
- [ ] TLS/auth/token/key rotation hoạt động trong cửa sổ trộn phiên bản.

### Event, job và state

- [ ] V1 producer → V2 consumer.
- [ ] V2 producer → V1 consumer hoặc new write vẫn được gate.
- [ ] Replay event lịch sử vào V2.
- [ ] Duplicate/redelivery/retry không tạo side effect sai.
- [ ] V1 và V2 cùng đọc/ghi DB schema chuyển tiếp.
- [ ] Migrations là expand-first, contract-last khi phù hợp.
- [ ] Schema có thể rollback về V1 trong cửa sổ đã công bố.
- [ ] Session/cache/token do V2 tạo được V1 xử lý theo yêu cầu.
- [ ] Scheduler/worker không chạy trùng hoặc mất job.
- [ ] Concurrent writes bảo toàn business invariants.

### Deployment và vận hành

- [ ] Test runner ép được request tới từng version.
- [ ] Traces/logs chứng minh tổ hợp thực sự đã chạy.
- [ ] Graceful shutdown/draining được kiểm tra.
- [ ] Canary monitoring phân biệt V1/V2.
- [ ] DLQ/queue lag/deserialization alerts có mặt.
- [ ] Latency p95/p99, errors và CPU/GC được so sánh.
- [ ] Rollback test thực hiện sau khi V2 đã ghi state.
- [ ] Artifact và test evidence được lưu cùng release candidate.

### Sau migration

- [ ] V1 đã rút hết trước khi bỏ field/endpoint cũ.
- [ ] Consumer telemetry xác nhận không còn dùng contract cũ.
- [ ] Đã tắt/loại code tương thích tạm thời theo kế hoạch.
- [ ] Đã contract DB schema ở release phù hợp.
- [ ] Đã lưu migration/rollback decisions.
- [ ] Đã cập nhật contract inventory và version support policy.

## Kết luận

**Kiểm thử nhiều phiên bản dịch vụ cùng hoạt động** không phải chỉ chạy hai image song song rồi gửi vài HTTP requests. Bài toán thật nằm ở các **ranh giới tương thích**: client/server API, producer/consumer event, database schema, session/cache, token, retry/idempotency, background jobs và lifecycle của deployment.

Trong quá trình *Java Advance Compatibility Migration*, đặc biệt khi một số service chạy JDK/framework mới và số khác vẫn ở thế hệ cũ, hãy **lập ma trận V1↔V2 rõ ràng, thử cả hai hướng giao tiếp, tạo shared-state fixtures, kiểm tra rollout và rollback, rồi xác nhận business invariants cùng SLO trên artifact thực tế**. Một hệ thống được xem là sẵn sàng khi không chỉ V2 hoạt động tốt ở trạng thái cuối, mà cả **giai đoạn chuyển tiếp và con đường trở về an toàn** cũng đã được chứng minh bằng kiểm thử hồi quy có thể tái hiện.

