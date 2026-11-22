# Phân biệt triển khai độc lập với vận hành hoàn toàn không có phụ thuộc

## 1. Bối cảnh: “deploy riêng được” không có nghĩa “tồn tại một mình”

Trong kiến trúc microservices, một trong những lý do tách hệ thống thành nhiều dịch vụ là mỗi nhóm có thể phát triển, kiểm thử và phát hành thay đổi của dịch vụ mình mà không phải đồng thời phát hành toàn bộ ứng dụng. Khả năng này thường được gọi là **independent deployability** — khả năng triển khai độc lập.

Tuy nhiên, một service có thể được triển khai độc lập mà vẫn phải gọi service khác, kết nối database, xác thực qua Identity Provider, tải secret, sử dụng message broker và phụ thuộc vào DNS, mạng, container platform hoặc ingress để phục vụ yêu cầu. Những quan hệ đó là **operational dependencies** — phụ thuộc vận hành. Hai khái niệm này thuộc hai chiều khác nhau của thiết kế.

Ví dụ:

```text
                     [Người dùng]
                           |
                        Gateway
                           |
                           v
                      Order API
                      /   |   \
                     /    |    \
            Inventory  Payment  PostgreSQL
                |        |
              Redis   Payment Provider
                           |
                (Nền chung: DNS, TLS, IdP,
                 Kubernetes, Secret Manager,
                 mạng, logging, monitoring)
```

Order API có thể được build thành Docker image riêng, deploy theo pipeline riêng và rollback độc lập. Nhưng nếu Order API bắt buộc gọi Payment đồng bộ để hoàn tất checkout, độ sẵn sàng của checkout vẫn phụ thuộc vào Payment. Nếu PostgreSQL mất kết nối, Order API có thể đang chạy và trả `/health` thành công nhưng nghiệp vụ tạo đơn thất bại.

**Ý chính:** “triển khai độc lập” nói về *khả năng thay đổi phiên bản và đưa phiên bản đó vào hoạt động mà không buộc triển khai đồng thời các thành phần khác*; “không có phụ thuộc vận hành” là một tuyên bố rất mạnh về *hành vi khi các thành phần khác không khả dụng*. Trong một hệ thống thực tế, các dịch vụ thường còn nhiều phụ thuộc cần được quản lý.

Sau bài học, bạn có thể:
- Định nghĩa ranh giới build, release, deploy, runtime và failure.
- Giải thích vì sao một service deploy độc lập vẫn cần phụ thuộc vận hành.
- Xác định phụ thuộc trực tiếp, gián tiếp, đồng bộ, bất đồng bộ, dữ liệu và hạ tầng.
- Thiết kế contract và rollout có khả năng chạy hỗn hợp phiên bản.
- Đưa ra hành vi suy giảm khi một downstream lỗi thay vì giả định “service nào cũng tự sống được”.
- Đo mức độ độc lập bằng bằng chứng triển khai, runtime và phản ứng sự cố.

## 2. Các từ khóa phải phân biệt

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Independent development** | Nhóm A có thể sửa chức năng A mà không phải sửa source B không? | Orders chỉ sửa rule phí giao hàng trong repo/module của Orders |
| **Independent build** | Có thể compile, test và package artifact A riêng không? | `orders:bootJar` hoặc image Orders build độc lập |
| **Independent release** | Có thể publish một phiên bản A riêng không? | Orders `2.7.1` được publish mà Payments vẫn `3.4.0` |
| **Independent deployment** | Có thể đưa A vào môi trường chạy mà không cần đồng thời triển khai B không? | Rollout Orders với Payments hiện hành vẫn tương thích |
| **Independent rollback** | Có thể quay A về phiên bản trước một cách an toàn không? | Orders rollback nhưng vẫn đọc được schema/event hiện tại |
| **Runtime dependency** | Khi xử lý yêu cầu, A cần B hoặc hạ tầng nào? | Orders gọi Inventory và PostgreSQL |
| **Failure isolation** | Khi B lỗi, phạm vi hỏng của A có được giới hạn không? | Order history vẫn xem được trong khi Recommendations bị lỗi |
| **Operational autonomy** | A có thể được vận hành, quan sát, mở rộng và khôi phục trong phạm vi trách nhiệm rõ không? | Team Orders có on-call, SLO, dashboard, runbook riêng |

Các thuộc tính trên **không suy ra lẫn nhau**. Một repository chứa nhiều service vẫn có thể hỗ trợ independent deployment. Nhiều repository riêng chưa chắc đem lại independent deployment nếu service dùng chung database schema và yêu cầu release đúng thứ tự.

Cũng không nên đánh đồng *có container riêng* với *có failure boundary thật*: một ứng dụng bị chia thành nhiều process nhưng tất cả đều cần cùng một database transaction hoặc một endpoint trung tâm cho mọi request có thể phát sinh điểm lỗi chung nghiêm trọng.

## 3. Định nghĩa độc lập triển khai theo hành vi có thể kiểm chứng

Một service S được xem là có khả năng triển khai tương đối độc lập nếu một thay đổi hợp lệ của S có thể đi qua chu trình:

```text
S sửa source
    |
    v
S build + test + publish artifact
    |
    v
S deploy/canary phiên bản mới
    |
    v
S đạt health/SLO và tương thích với các dependency đang chạy
    |
    v
S ổn định hoặc rollback theo hợp đồng
```

Trong chu trình đó, các service khác **không bị bắt buộc** phải rebuild/redeploy cùng một thời điểm chỉ vì S thay đổi. Tuy nhiên, những kiểm tra tương thích, cập nhật contract và thay đổi hạ tầng cần thiết vẫn có thể phải thực hiện theo kế hoạch.

Các dấu hiệu kiểm chứng:
1. S có artifact/version/immutable image digest nhận diện được.
2. Pipeline có target build/test/deploy riêng cho S.
3. S vẫn tương thích với phiên bản các service khác đang chạy, kể cả giai đoạn canary/rolling deployment.
4. Thay đổi database/event/API dùng chiến lược mở rộng trước, loại bỏ sau khi các consumer đã chuyển.
5. S có thể scale, restart hoặc rollback trong giới hạn không gây hỏng hợp đồng và trạng thái dữ liệu.
6. Việc triển khai S có trách nhiệm owner, monitor và rollback criteria riêng.

Chỉ nhìn thấy nút “Deploy Orders” trong CI chưa đủ để kết luận độc lập. Nếu nhấn nút này khiến service khác nhận dữ liệu không tương thích hoặc bắt buộc thay schema ngay, independent deployment mới tồn tại trên giao diện vận hành, chưa tồn tại trong kiến trúc.

## 4. Vì sao vẫn có phụ thuộc vận hành?

Giả sử mỗi service được triển khai độc lập:

```text
orders-image:v4   → deployment/orders
payments-image:v9 → deployment/payments
stock-image:v3    → deployment/inventory
```

Các image độc lập không loại bỏ yêu cầu nghiệp vụ:
- Orders cần tồn kho chính xác để xác nhận đơn.
- Payments cần gateway thanh toán để thu tiền.
- Users cần Identity Provider hoặc khả năng xác minh token.
- Mọi service dùng DNS/networking để tìm dependency và TLS/CA để xác thực.
- Consumer cần broker để nhận sự kiện hoặc một cơ chế khác để tiếp tục xử lý.

Đó là **quan hệ phụ thuộc theo khả năng cung cấp chức năng**. Trong thiết kế tốt, mỗi quan hệ phải có hợp đồng và trạng thái lỗi dự kiến. Một service không cần loại bỏ mọi dependency; cần biết **cái nào bắt buộc cho chức năng nào, khi nào fail fast, khi nào chờ và khi nào dùng fallback**.

Phân biệt “ứng dụng còn chạy” với “khả năng nghiệp vụ còn phục vụ”:

```text
Order process UP        ≠ Checkout available
Readiness PASS          ≠ Payment path healthy
All pods Running        ≠ User transaction succeeds
HTTP 200 from Gateway   ≠ Đơn hàng đã được xác nhận
```

Một tổ hợp service có thể chạy bình thường ở mức process nhưng thất bại tại đường nghiệp vụ quan trọng.

## 5. Bản đồ phụ thuộc theo loại và tính bắt buộc

| Loại phụ thuộc | Ví dụ | Ảnh hưởng khi lỗi |
| --- | --- | --- |
| **Đồng bộ bắt buộc** | Orders gọi Inventory để reserve ngay | Request có thể timeout/fail; ảnh hưởng trực tiếp latency |
| **Đồng bộ tùy chọn** | Orders gọi Recommendations để gợi ý thêm | Có thể bỏ phần gợi ý và tiếp tục trả kết quả |
| **Bất đồng bộ** | Orders publish `OrderPlaced` qua broker | Lưu lượng có thể tích tụ; kết quả đến chậm |
| **Dữ liệu** | PostgreSQL, Redis, object storage | Read/write có thể bị chặn hoặc suy giảm |
| **Identity và security** | IdP, token introspection, CA, secrets | Có thể không đăng nhập được, không kết nối được; policy phải rõ |
| **Control plane** | Kubernetes API, service mesh control plane | Deploy/scale/cấp cert có thể ảnh hưởng; data plane có thể vẫn chạy một thời gian |
| **Network/discovery** | DNS, ingress, load balancer, service discovery | Không tìm được endpoint hoặc route sai |
| **Shared resource** | Database cluster, node pool, message broker | Tải một tenant/service có thể làm ảnh hưởng service khác |
| **External partner** | Payment gateway, shipping provider | Nghiệp vụ có thể pending, fail hoặc chờ reconciliation |
| **Con người/quy trình** | Phê duyệt thay đổi contract, on-call, release window | Lead time hoặc khôi phục có thể bị trì hoãn |

**Bắt buộc hay tùy chọn** không phải thuộc tính cố định của cả service. Inventory có thể bắt buộc cho hành động “xác nhận mua hàng”, nhưng không bắt buộc khi người dùng chỉ xem lại hóa đơn đã tạo. Cần phân loại theo từng **operation** và mỗi cấp chất lượng dịch vụ.

Một bảng dependency nên thể hiện:

```text
Operation: POST /checkout
  -> Inventory.reserve    REQUIRED, synchronous
  -> Payment.authorize    REQUIRED, synchronous or stateful async
  -> EmailNotification    OPTIONAL, asynchronous
  -> Analytics.track      OPTIONAL, asynchronous

Operation: GET /orders/{id}
  -> Orders database      REQUIRED
  -> Recommendations     NOT REQUIRED
  -> Payment             NOT REQUIRED nếu trạng thái đã được lưu phù hợp
```

Việc đánh dấu này giúp tránh một downstream tùy chọn trở thành điểm lỗi chung cho toàn bộ service.

## 6. Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Trong hệ thống phân tán, team sở hữu Orders có thể chỉ biết Orders gọi Payments, nhưng Payments còn gọi Risk Service và một external provider:

```text
Checkout → Orders → Payments → Risk
                           |
                           +→ External Processor
```

Nếu Risk lỗi, Payment timeout; Orders timeout; Checkout báo lỗi. Đây là **transitive dependency** (phụ thuộc bắc cầu). Mức ảnh hưởng ở upstream có thể lớn hơn vẻ ngoài của một sơ đồ gọi trực tiếp.

Khi vẽ đồ thị phụ thuộc:
1. Ghi lại edge service-to-service thực tế từ traces/traffic, không chỉ đọc source và cấu hình.
2. Gắn operation và lý do mỗi edge là bắt buộc hay tùy chọn.
3. Ghi đồng bộ/bất đồng bộ, timeout, retry, deadline và circuit breaker.
4. Ghi owner, SLO, change/deprecation policy của endpoint/topic.
5. Ghi nguồn dữ liệu, quyền truy cập và shared infrastructure.
6. Chỉ ra **shared failure domain**: các service khác nhau nhưng dùng cùng cluster, availability zone, node pool, broker hoặc secret issuer.

Sơ đồ topology cần được cập nhật từ telemetry và service catalog. Một dependency đã không còn trong code chính vẫn có thể hiện diện trong scheduled job hoặc luồng xử lý lỗi.

## 7. Hệ quả lên độ sẵn sàng của đường nghiệp vụ

Giả sử một yêu cầu bắt buộc ba dịch vụ hoạt động nối tiếp và giả định xác suất sẵn sàng độc lập, mỗi dịch vụ đều có availability 99,9% trong cùng phạm vi đo. Khả năng cả ba cùng sẵn sàng tại một thời điểm là:

```text
P(success) = 0,999 × 0,999 × 0,999
           ≈ 0,997003 = 99,7003%
```

Ví dụ chỉ minh họa phép nhân **khi các sự kiện độc lập**; thực tế có thể có lỗi chung (DNS, network, identity, cloud region) khiến giả định độc lập không đúng. Ngoài ra, khả năng hoàn thành yêu cầu còn phụ thuộc latency, retry, fallback, thiết kế giao dịch và định nghĩa success.

Kết luận quan trọng không phải con số cụ thể mà là: **một user journey đồng bộ bắt buộc nhiều thành phần có thể có độ sẵn sàng thấp hơn từng thành phần riêng lẻ**.

Nếu Recommendations là tùy chọn và bị lỗi, trang sản phẩm vẫn có thể tải. Nhưng nếu Checkout bắt buộc có tồn kho và thanh toán, sự cố ở một trong hai có thể làm hành trình checkout thất bại hoặc chuyển vào trạng thái pending.

Do đó cần định nghĩa SLO cho **user journey** (tạo đơn thành công, hoàn tất thanh toán đúng, truy xuất trạng thái đơn) song song với SLO theo service.

## 8. Tương thích phiên bản mới là điều kiện của triển khai độc lập

Khi Orders triển khai phiên bản mới, những phiên bản khác có thể vẫn đang chạy trong hàng giờ hoặc hàng ngày:

```text
Time T0:
  Orders v1 → Inventory v1 → Payment v1

Time T1:
  Orders v2 → Inventory v1 → Payment v1

Time T2:
  Orders v2 → Inventory v2 → Payment v1

Time T3:
  Orders v2 → Inventory v2 → Payment v2
```

Nếu Orders v2 chỉ hoạt động với Inventory v2, ở thời điểm T1 người dùng sẽ gặp lỗi. Mẫu “đổi mọi service cùng một lúc” loại bỏ mục tiêu độc lập và rất khó rollback khi rollout từng phần.

Một **compatibility matrix** có thể mô tả:

| Consumer | Provider | Hành vi bắt buộc |
| --- | --- | --- |
| Orders v1 | Inventory v1 | Đang hỗ trợ |
| Orders v2 | Inventory v1 | Phải hoạt động trong migration, nếu yêu cầu deploy Orders trước |
| Orders v1 | Inventory v2 | Phải hoạt động nếu provider deploy trước |
| Orders v2 | Inventory v2 | Hành vi mục tiêu |

Không phải mọi tổ hợp version lịch sử đều phải được hỗ trợ vô hạn. Tổ chức cần chính sách **support window**: những version có thể đồng thời tồn tại, contract nào có thể bị deprecate và khi nào thực sự an toàn để remove field/endpoint.

### Ví dụ đổi response HTTP

Inventory v1 trả:

```json
{
  "sku": "SKU-42",
  "available": 10
}
```

Inventory v2 muốn thêm `reserved`:

```json
{
  "sku": "SKU-42",
  "available": 10,
  "reserved": 3
}
```

Thêm field optional thường dễ tương thích hơn đổi kiểu của `available` hoặc xóa field cũ, nhưng phải kiểm tra policy deserialization của consumer. Một consumer cấu hình từ chối unknown properties có thể hỏng ngay cả khi thêm field.

Để deploy độc lập, contract tests phải bảo vệ **những consumer version còn được hỗ trợ**, không chỉ version mới nhất trong Git.

## 9. Expand–migrate–contract khi thay API hoặc event

Quy trình thay hợp đồng an toàn:

1. **Expand:** provider thêm cách hiểu hoặc định dạng mới trong khi vẫn hỗ trợ định dạng cũ.
2. **Verify:** consumer/provider contract tests xác nhận tổ hợp phiên bản dự kiến cùng tồn tại.
3. **Migrate consumers:** deploy consumer mới, sử dụng khả năng mới nhưng xử lý được dữ liệu cũ trong khoảng chuyển tiếp.
4. **Switch producer:** bắt đầu phát định dạng/giá trị mới khi những consumer cần thiết đã sẵn sàng.
5. **Observe:** đo tỷ lệ sử dụng đường cũ, kiểm tra backlog/message còn nằm trong broker.
6. **Contract:** gỡ field/endpoint/schema cũ khi không còn consumer cần nó và đủ điều kiện dữ liệu lịch sử.

Ví dụ Payments thêm trạng thái `PENDING_REVIEW` vào event. Nếu Orders chưa biết trạng thái này, producer không nên phát nó ngay cho toàn hệ thống sau khi merge source. Có thể deploy consumer hỗ trợ trạng thái mới trước; sau đó bật phát trạng thái mới bằng feature flag với owner và thời hạn rõ.

```text
Provider supports OLD + NEW
        |
        v
Consumers updated to parse NEW
        |
        v
Producer starts emitting NEW
        |
        v
Historical messages / old deployments drained
        |
        v
Provider stops supporting OLD
```

Mỗi bước là một thay đổi riêng có điều kiện tiến tiếp và rollback phù hợp. **Một commit code duy nhất không làm các phiên bản đã triển khai đổi đồng thời.**

## 10. Phụ thuộc dữ liệu: sở hữu database không đồng nghĩa không cần dữ liệu từ nơi khác

Một đặc tính quan trọng của microservices là dịch vụ có **quyền sở hữu dữ liệu** và không để service khác tùy ý đọc/ghi schema nội bộ. Nhưng khi Orders cần trạng thái thanh toán từ Payments, Orders vẫn có phụ thuộc nghiệp vụ vào thông tin của Payments.

Các cách trao đổi:
- API đồng bộ: Orders hỏi Payment khi cần; dữ liệu mới nhưng tăng phụ thuộc availability và latency.
- Sự kiện bất đồng bộ: Payments phát `PaymentAuthorized`, Orders duy trì local projection; giảm phụ thuộc đồng bộ nhưng chấp nhận eventual consistency.
- Query model/read projection: cập nhật dữ liệu phục vụ đọc từ events hoặc change feed có hợp đồng.
- Workflow/Saga: quản lý chuỗi thao tác phân tán bằng state transitions và compensation thay vì transaction chung kéo dài qua nhiều service.

**Tránh shared database tables như API ngầm.** Khi Orders và Payments cùng truy cập trực tiếp một bảng, thay schema có thể buộc release lockstep và làm độc lập triển khai trở nên giả tạo. Chia database theo service không nhất thiết luôn cần hạ tầng DB vật lý riêng, nhưng ownership của schema và quyền đọc/ghi cần rõ ràng.

### Schema migration phải hỗ trợ phiên bản cũ

Giả sử Orders v2 muốn đổi `customer_name` thành `buyer_display_name`:

```text
Release A: thêm buyer_display_name (nullable / có default phù hợp)
Release B: ứng dụng ghi cả hai hoặc cung cấp compatibility layer
Release C: backfill và deploy reader mới
Release D: xác nhận không còn consumer đọc customer_name
Release E: bỏ cột cũ trong change riêng
```

Thứ tự và khả năng dual-write phụ thuộc schema, transaction, lượng dữ liệu và cơ chế migration. Không xóa cột cũ trong cùng release với code mới nếu instances v1 vẫn đang chạy hoặc rollback v1 vẫn là phương án khôi phục.

Tương tự, migration làm data không tương thích ngược có thể khiến **rollback artifact độc lập** trở thành không an toàn. Vì vậy independent deployment luôn cần xét vòng đời dữ liệu.

## 11. Phụ thuộc bất đồng bộ vẫn là phụ thuộc

Chuyển HTTP đồng bộ thành Kafka/RabbitMQ không xóa sự phụ thuộc; nó thay hình thức và thời điểm ảnh hưởng.

```text
Order Service  --->  Broker  --->  Payment Consumer
      |                             |
      v                             v
  Lưu order                  Xử lý payment
      |
      v
  Trạng thái PENDING, sau đó CONFIRMED/FAILED
```

Khi Payment Consumer bị lỗi:
- Order API có thể vẫn nhận request mới và trả `PENDING` theo hợp đồng.
- Broker backlog tăng và thời gian hoàn tất nghiệp vụ kéo dài.
- Người dùng chưa thể coi đơn đã thanh toán.
- Consumer hồi phục có thể nhận lại thông điệp trùng.
- Nếu queue retention đầy/hết hạn hoặc DLQ không được xử lý, có thể mất tiến trình nghiệp vụ.

Vậy nên “asynchronous decoupling” thường mang nghĩa **giảm coupling thời gian cho request path**, chứ không phải miễn yêu cầu về kết quả nghiệp vụ.

Muốn vận hành an toàn cần:
1. Durable messaging, acknowledgment và retention đủ cho nhu cầu.
2. Transactional outbox hoặc cơ chế tương đương nếu phải đảm bảo thao tác ghi DB và phát event không bị lệch không kiểm soát.
3. Consumer idempotent, operation ID, xử lý duplicate delivery.
4. Retry có giới hạn, backoff và dead-letter handling.
5. Kiểm soát backlog, consumer lag, age của message và thời gian hoàn tất workflow.
6. Reconciliation cho trạng thái pending quá hạn.
7. Contract/versioning cho event lịch sử và consumer cũ.

Service có thể tự deploy trong khi vẫn yêu cầu broker, consumer và quy trình xử lý bất đồng bộ để hoàn tất nghĩa vụ nghiệp vụ.

## 12. Tách “hard dependency” và “soft dependency” theo operation

**Hard dependency** là thành phần bắt buộc để thực hiện một chức năng đúng hợp đồng. **Soft dependency** là thành phần có thể lỗi mà chức năng vẫn cung cấp kết quả chấp nhận được.

Ví dụ API xem đơn hàng:

```text
GET /orders/83
   |
   +-- Orders DB: REQUIRED
   |
   +-- Customer Profile service: OPTIONAL nếu có snapshot được phép
   |
   +-- Recommendations: OPTIONAL
   |
   +-- Audit: chính sách ghi log có thể là bắt buộc cho hành động nhạy cảm
```

Một hành vi suy giảm có chủ đích:
- Recommendations lỗi → bỏ gợi ý, giữ thông tin đơn.
- Profile chậm → hiển thị tên đã lưu trong order nếu contract cho phép.
- DB Orders lỗi → không thể trả order chính xác nếu không có cache hợp lệ.
- IdP không truy cập được → token JWT vẫn có thể kiểm tra cục bộ nếu thiết kế dùng public key được cache, nhưng chính sách thu hồi và thời hạn token phải được xử lý đúng.
- Payment bị timeout → không tự ý báo “thất bại, chưa trừ tiền”; có thể trả `PENDING_RECONCILIATION` rồi truy vấn kết quả.

Không dùng fallback bằng cách **đưa ra dữ liệu giả như dữ liệu thật**. Ví dụ tồn kho không xác định không thể mặc định bằng “còn hàng” nếu hệ thống sẽ chấp nhận thanh toán và bán vượt tồn.

Bảng quyết định nên gắn với SLO và nghiệp vụ, không chỉ lỗi HTTP.

## 13. Bảo vệ vòng lỗi: timeout, retry budget, circuit breaker và bulkhead

Một runtime dependency lỗi có thể tạo sự cố dây chuyền nếu các upstream chờ vô hạn hoặc retry lồng nhau.

```text
Payment chậm
    |
    v
Checkout timeout / retry
    |
    v
Payment bị gọi nhiều hơn
    |
    v
Thread/connection pool cạn
    |
    v
Orders và Gateway cũng chậm
```

Các cơ chế cốt lõi:

| Cơ chế | Bài toán giải quyết |
| --- | --- |
| Timeout từng lần gọi | Không chờ một downstream quá lâu |
| Deadline end-to-end | Không cho các tầng tự bắt đầu lại đồng hồ và giữ công việc quá thời gian còn hữu ích |
| Bounded retries + jitter | Chỉ thử lại lỗi thoáng qua với độ trễ phân tán |
| Retry budget | Giới hạn tổng lưu lượng bổ sung do retry |
| Circuit breaker | Ngừng gọi tạm thời khi phụ thuộc lỗi nặng, kiểm tra phục hồi có giới hạn |
| Bulkhead / concurrency limit | Một dependency chậm không chiếm hết thread/connection của mọi chức năng |
| Load shedding | Từ chối sớm request khi quá tải thay vì xếp hàng không giới hạn |
| Idempotency | Lặp yêu cầu không nhân đôi tác dụng phụ nghiệp vụ |
| Cache/fallback đúng hợp đồng | Duy trì một phần chức năng khi dependency không sẵn sàng |

Với luồng Gateway → Orders → Payments, nếu cả ba tầng đều tối đa ba attempts thì một request có thể tạo tới `3 × 3 × 3 = 27` lời gọi tại điểm cuối trong kịch bản mọi lần đều thất bại và có retry lồng nhau. Cần chỉ rõ chủ sở hữu retry, max attempts, budget và deadline; không bật retry mặc định vô thức ở gateway, SDK và service cùng lúc.

Khi một dependency là bắt buộc, các cơ chế bảo vệ không biến nó thành tùy chọn; chúng chỉ giữ **phạm vi lỗi và mức tiêu hao tài nguyên** trong giới hạn dự kiến.

## 14. Phụ thuộc hạ tầng chung và shared failure domain

Các service khác nhau có thể triển khai độc lập nhưng dùng chung:
- Kubernetes cluster, node pool, availability zone hoặc region.
- DNS resolver, service discovery, ingress, API Gateway.
- Service mesh control plane, certificate authority, trust bundle.
- Identity Provider, token verifier, Secret Manager.
- Database/broker cluster, connection gateway, NAT hoặc egress proxy.
- Object storage, registry artifact hoặc cấu hình điều phối.
- Monitoring/alerting và hệ thống incident communication.

Ví dụ Payments và Orders chạy trên hai Deployment riêng nhưng cùng node pool. Khi node pool hết tài nguyên, cả hai có thể mất năng lực phục vụ. Việc deploy riêng không tạo **resource isolation** nếu CPU/memory, connection limits hoặc quota dùng chung không được phân bổ hợp lý.

Không phải control plane outage nào cũng làm data plane dừng ngay. Ví dụ một số workload vẫn phục vụ request với cấu hình đã có khi Kubernetes API tạm không truy cập được; tuy vậy deploy/scale/renew cert có thể bị gián đoạn. Hành vi thật phụ thuộc công nghệ và cấu hình, cần được thử nghiệm và ghi nhận.

Một bản đồ failure domain nên gắn:
- Service → compute cluster/node pool/region.
- Service → network/DNS/ingress.
- Service → database/broker/secret issuer.
- Critical journey → tập các dependency bắt buộc.
- On-call owner và runbook cho từng thành phần chung.

**Dịch vụ khác nhau trong sơ đồ logic không bảo đảm chúng tách failure domain về vật lý.**

## 15. Bảo mật cũng tạo ranh giới phụ thuộc vận hành

Một service có thể cần:
- Access token hợp lệ cho API của nó.
- Chứng chỉ mTLS để gọi downstream.
- IAM role để lấy secret hoặc gọi database.
- Key rotation/JWKS cập nhật từ hệ thống định danh.
- Chính sách mạng cho phép route đúng giữa service.

Nếu certificate của service hết hạn, image đang chạy có thể không còn kết nối được. Nếu IdP đổi signing key trước khi các resource server cập nhật public key, request có thể bị 401 hàng loạt. Nếu Secret Manager tạm unavailable trong lúc instance restart, ứng dụng có thể không nạp được credential dù các instance cũ vẫn đang phục vụ.

Quy tắc:
1. Service phải có identity và quyền tối thiểu của **workload** riêng.
2. Phân biệt workload identity với quyền của user cuối.
3. Mỗi resource service vẫn xác thực và phân quyền theo audience, scope, tenant/resource.
4. Có kế hoạch rotation cert/secret với thời gian overlap hoặc cutover kiểm soát.
5. Runbook nêu hành vi khi issuer, CA, secret store hoặc policy engine không sẵn sàng.
6. Không “fix” sự cố phụ thuộc bằng cách tắt TLS verification hoặc bỏ authorization.

Operational autonomy gồm khả năng quản lý và hồi phục các phụ thuộc bảo mật, không có nghĩa bỏ chúng khỏi đường yêu cầu.

## 16. Deploy độc lập nhưng cần phối hợp phát hành contract

“Không cần deploy đồng thời” khác “không cần nói chuyện với nhóm khác”.

Một thay đổi trong Orders có thể cần:
- Thống nhất version mới của Payment API.
- Provider hỗ trợ cả contract cũ/mới một thời gian.
- Client SDK được publish có version.
- Các consumer deploy theo thứ tự an toàn.
- Mỗi team biết khi nào có thể gỡ đường cũ.
- Một test liên service hoặc synthetic journey xác nhận tích hợp.

Ví dụ release phối hợp:

```text
Thay đổi: Payment thêm response field authorizationRef

1) Payment mở rộng response, giữ field cũ
2) Provider contract verification PASS
3) Orders deploy bản có khả năng đọc authorizationRef
4) Orders bắt đầu sử dụng field mới khi đã nhận đủ
5) Theo dõi error và phiên bản consumer
6) Xóa compatibility path cũ sau khi đã chuyển xong
```

Có thể triển khai từng service riêng lẻ trong từng bước, nhưng **lộ trình release** vẫn là công việc liên nhóm. Đó là sự phối hợp chủ động giúp giữ độc lập về thời điểm triển khai.

Nếu nhóm phải phát hành đồng thời mỗi tuần chỉ để sửa DTO hoặc shared database table, đó là dấu hiệu coupling cần điều tra, không phải đặc điểm hiển nhiên không thể tránh của microservices.

## 17. Phụ thuộc vào môi trường triển khai và pipeline

Dù mỗi service có CI/CD riêng, deployment vẫn có thể bị chặn bởi một phụ thuộc chung:
- Container registry mất kết nối.
- Runner hoặc signing service không hoạt động.
- Shared Helm chart hoặc GitOps controller lỗi.
- Namespace quota không cho tạo pod mới.
- Schema migration job chưa xong.
- Feature flag service hoặc config source chưa cung cấp phiên bản mong đợi.
- Admission webhook từ chối manifest vì policy thay đổi.

Các yếu tố này là **deployment-time dependencies**, khác với **request-time dependencies** nhưng đều ảnh hưởng khả năng phát hành.

Một pipeline tốt nên:
- Build artifact immutable và có provenance.
- Kiểm tra contract/migration compatibility trước deploy.
- Dùng canary/rolling rollout và readiness đúng nghiệp vụ.
- Có timeout/rollback gate khi hạ tầng không phản hồi.
- Không rebuild tất cả service khi chỉ một service thay đổi, trừ trường hợp dependency graph yêu cầu.
- Không đánh dấu “deploy thành công” chỉ vì controller đã chấp nhận manifest; cần kiểm tra rollout và tín hiệu hệ thống.
- Giữ audit về service version, image digest, config version và database schema state.

Independent deployment có nghĩa **không buộc triển khai đồng thời các service khác**; nó không miễn việc chờ infrastructure hoặc kiểm tra an toàn trước release.

## 18. Readiness, liveness và trạng thái nghiệp vụ

Một service cần phân biệt ba loại tín hiệu:

**Liveness:** tiến trình còn sống hay rơi vào trạng thái cần restart? Không nên làm liveness phụ thuộc quá sâu vào mọi downstream, vì một outage nhỏ có thể gây vòng restart đồng loạt.

**Readiness:** instance có thể nhận request mới một cách an toàn không? Khi service hoàn toàn không thể đáp ứng chức năng cốt lõi, readiness có thể phản ánh điều đó. Nhưng nếu readiness buộc mọi dependency tùy chọn phải khỏe, sự cố một service phụ sẽ làm rút toàn bộ instance khỏi load balancer.

**Business/SLI health:** user journey có hoàn tất trong giới hạn thời gian và kết quả mong đợi không? Đây là nơi cần đo theo operation: checkout, xem đơn, hoàn tiền, tra cứu lịch sử.

Ví dụ:

```text
GET /actuator/health/liveness  → process sống
GET /actuator/health/readiness → instance sẵn sàng nhận lưu lượng
Synthetic checkout journey   → kiểm tra tích hợp nghiệp vụ có kiểm soát
```

Các endpoint trên là cách đặt tên quen thuộc trong hệ Spring Boot với actuator/probes khi đã cấu hình; mapping thực tế có thể khác. Không nhúng thanh toán thực hoặc hành động gây side effect lớn vào một health probe được gọi liên tục.

SLO theo nghiệp vụ phải được quan sát độc lập với `Running`/`Ready` của pod.

## 19. Một ma trận dependency cho vận hành

Ví dụ bảng trách nhiệm cho Order Service:

| Operation | Dependency | Bắt buộc? | Timeout/failure behavior | Owner |
| --- | --- | --- | --- | --- |
| `POST /orders` | Orders DB | Có | Thất bại có kiểm soát; không nhận đơn giả | Orders |
| `POST /checkout` | Inventory reserve | Có | Có deadline; thông báo không thể xác nhận nếu hết tồn/không rõ kết quả | Inventory |
| `POST /checkout` | Payment authorization | Có theo contract | Pending/reconcile khi kết quả không xác định | Payments |
| `GET /orders/{id}` | Orders DB | Có | Trả lỗi có ngữ nghĩa phù hợp | Orders |
| `GET /orders/{id}` | Recommendations | Không | Bỏ recommendation, giữ order details | Recommendations |
| `OrderPlaced` publish | Broker | Tùy workflow | Durable outbox hoặc error/pending theo thiết kế | Platform/Orders |
| Service startup | Secret Manager | Theo cơ chế cấp secret | Dừng startup, retry có giới hạn hoặc cache credential còn hợp lệ theo policy | Platform |
| Mọi request authenticated | Token validation | Có | Fail closed đúng chính sách; phân biệt JWKS cache hợp lệ với issuer outage | Identity |

Các cột bổ sung có thể gồm SLO, version contract, retry budget, circuit breaker threshold, trace/metrics, phương án rollback, criticality và escalation.

Ma trận là tài liệu sống: dữ liệu thực tế từ distributed tracing và dependency registry giúp phát hiện những call ngoài bản đồ thiết kế.

## 20. Sự cố điển hình: service deploy riêng, nhưng hoạt động vẫn gãy

### Tình huống A — Payments timeout trong checkout

Orders và Payments chạy hai pipeline riêng. Payment gateway bên ngoài chậm; Orders retry ba lần; Gateway cũng retry. Lưu lượng tăng, connection pool Orders bị giữ quá lâu.

**Bài học:** deployment autonomy không tự ngăn cascading failure. Cần end-to-end deadline, bounded retry, breaker, backpressure và trạng thái không xác định được xử lý theo nghiệp vụ. Một số chức năng Orders như xem lịch sử đơn vẫn có thể phục vụ nếu tách resource pool/operation hợp lý.

### Tình huống B — Producer đổi enum event

Inventory v2 phát event `StockStatus=RESERVED_PENDING`, Orders v1 chỉ hiểu `AVAILABLE` và `OUT_OF_STOCK`. Cả hai deploy độc lập, nhưng Orders consumer bị lỗi khi đọc event mới.

**Bài học:** event schema và semantics cần compatibility tests, chính sách unknown enum và rollout producer/consumer đúng thứ tự.

### Tình huống C — Shared DB migration

Orders v2 xóa cột `status_code`; Orders v1 còn đọc cột đó trong canary rollout. Pod cũ bị lỗi SQL.

**Bài học:** database schema cũng có vòng đời version. Expand/contract giúp hỗ trợ mixed versions, independent deployment và rollback.

### Tình huống D — Control plane gặp lỗi

Không thể deploy Payments do GitOps controller unavailable; Payments v1 vẫn phục vụ bình thường. Orders cần hotfix nhưng chart dùng chung lại phụ thuộc vào controller đó.

**Bài học:** phân biệt runtime availability của phiên bản hiện hành với khả năng deploy bản mới. Hai loại dependency phải có runbook riêng.

### Tình huống E — Shared resource saturation

Orders và Reports nằm trên cùng DB cluster. Report query lớn làm cạn connection limit, khiến Orders không tạo được đơn dù không có request trực tiếp tới Reports.

**Bài học:** phụ thuộc gián tiếp qua tài nguyên chung phải được giải quyết bằng quota, pool, workload isolation và capacity management.

### Tình huống F — IdP/JWKS rotation

Identity Provider phát token bằng key mới nhưng API chưa refresh key set. Gateway và service đồng loạt trả 401.

**Bài học:** secret/key/certificate distribution là phụ thuộc vận hành của toàn bộ chuỗi và cần rotation có overlap/kiểm thử.

## 21. Kiểm thử độc lập triển khai và kiểm thử phụ thuộc vận hành

Hai thuộc tính cần bộ bằng chứng khác nhau.

### 21.1 Kiểm thử khả năng triển khai độc lập

- Build, test, package một service và publish image digest riêng.
- Deploy Orders v2 trong khi Payments/Inventory giữ version đang chạy.
- Kiểm tra consumer/provider contracts cho phiên bản mới và cũ cùng tồn tại.
- Thử canary 10% traffic, quan sát lỗi rồi nâng dần; tỷ lệ chỉ là ví dụ.
- Rollback Orders về v1 sau khi một số dữ liệu đã được ghi bởi v2; xác minh khả năng đọc và trạng thái.
- Kiểm tra schema migration theo từng pha, không thay đổi phá vỡ ngay lúc deploy.
- Xác minh không có pipeline ẩn tự deploy hàng loạt các service không liên quan.

### 21.2 Kiểm thử phụ thuộc vận hành

- Tắt hoặc làm chậm dependency tùy chọn: response còn đủ dữ liệu cốt lõi không?
- Tắt downstream bắt buộc: response có deadline, status và retry budget đúng không?
- Mất DNS hoặc network tạm thời: client có xử lý lỗi, không tạo bão reconnect không?
- Tạm ngưng broker: outbox/backlog, pending và reconciliation hoạt động thế nào?
- Làm mất kết nối DB trong môi trường kiểm soát: pool/circuit breaker/saturation ra sao?
- Renew certificate, xoay secret, thay JWKS trong khi pod cũ/mới cùng chạy.
- Làm lỗi một availability zone/node pool để kiểm chứng shared failure domain khi điều kiện thử nghiệm cho phép.
- Tăng tải ở một service dùng tài nguyên chung để đánh giá mức cách ly thực tế.

Test dưới điều kiện lỗi phải chạy trong môi trường được phép và có giới hạn rõ. Để tránh flaky, các assert bất đồng bộ cần chờ trạng thái có deadline, không tin vào khoảng ngủ cố định.

**Một bài test “Orders deploy thành công” không chứng minh “Orders vẫn phục vụ checkout khi Payment chết”.** Cần ghi mục tiêu của mỗi test trước khi chạy.

## 22. Thiết kế observability theo user journey và dependency

Các chỉ số đáng theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `service_deployment_version` hoặc image digest | Biết phiên bản đang chạy từng service |
| `deployment_success_rate` | Khả năng rollout riêng thành công |
| `request_success_rate` theo operation | Xác minh chức năng cốt lõi |
| `request_duration_seconds` (p95/p99) | Đo độ trễ người dùng và dependency |
| `downstream_error_rate` theo dependency | Xác định lỗi đến từ đâu |
| `retry_attempts_total` | Phát hiện khuếch đại tải |
| `circuit_breaker_state` | Biết dependency đang bị tạm ngắt |
| `connection_pool_pending` | Phát hiện nghẽn tài nguyên |
| `queue_lag` và `oldest_message_age` | Đánh giá backlog bất đồng bộ |
| `business_workflow_pending_age` | Phát hiện giao dịch quá lâu chưa kết thúc |
| `deployment_rollback_count` | Ghi nhận khả năng hồi phục sau release |
| `contract_compatibility_failures` | Phát hiện vỡ hợp đồng trước/sau deploy |

Đừng chỉ đếm service uptime rồi suy ra business availability. Với checkout, cần SLI đo số lần hoàn tất hoặc đi vào trạng thái được hợp đồng công nhận, theo cửa sổ thời gian rõ ràng. Trạng thái pending kéo dài không nên bị tính là thành công cuối cùng nếu người dùng cần thanh toán hoàn tất.

Trace phân tán nên liên kết Gateway → Orders → Payments → provider, kèm outcome/deadline và correlation ID. Ghi log đủ để truy vết lỗi, nhưng không đưa bearer token, payment credential hoặc dữ liệu cá nhân không cần thiết vào span.

### Hai câu hỏi riêng khi xem dashboard

1. **Release question:** phiên bản Orders mới có thể rollout/rollback mà không làm các service khác phải triển khai đồng thời không?
2. **Runtime question:** khi Payment hoặc một shared dependency suy giảm, những chức năng Orders nào vẫn được cung cấp, ở mức chất lượng nào và trong bao lâu?

Hai câu hỏi đòi các phép đo khác nhau, nhưng cần được xem chung trong đánh giá độ tin cậy.

## 23. Trách nhiệm vận hành và on-call

Một service có owner riêng không đồng nghĩa owner đó có thể khắc phục mọi sự cố mà không cần người khác. Khi checkout lỗi, có thể cần:
- Orders team xác minh request/timeout/idempotency.
- Payments team kiểm tra consumer, provider và giao dịch chưa rõ kết quả.
- Platform team xử lý DNS, broker, ingress, TLS hoặc cluster.
- Security/Identity owner xác minh credential, policy và token.
- SRE/Incident commander điều phối khi lỗi lan nhiều service.

Nên xác định **service ownership** và **incident coordination** song song:

```text
Order Service owner:
  API contract, business logic, DB, deploy, dashboards, runbook

Payment Service owner:
  payment contract, external provider integration, reconciliation

Platform owner:
  shared network, broker, cert infrastructure, CI/CD, observability

Incident response:
  lead + affected service owners + shared dependency owner
```

Một dependency quan trọng thiếu owner/on-call là rủi ro đáng kể dù các service khác đều deploy độc lập. Runbook nên ghi:
- Cách phân biệt lỗi của service mình với lỗi dependency.
- Cách tạm giảm traffic, breaker, retry hoặc feature.
- Cách thực hiện rollback an toàn khi data/event đã thay đổi.
- Cách xác minh hồi phục và xử lý backlog/pending.
- Tên team/đường escalation của dependency.

## 24. Anti-patterns cần nhận diện

**“Mỗi service có repo và pipeline riêng nên không còn coupling.”** Coupling có thể tồn tại trong API, schema, shared DB, synchronous calls và vận hành.

**“Mọi service đều trả health 200 nên checkout khỏe.”** Health của process không thay thế user journey test.

**“Dùng event bus thì không còn phụ thuộc.”** Broker, schema, consumer lẫn backlog trở thành phụ thuộc cần kiểm soát.

**“Để đảm bảo ổn định, release mọi service cùng một phiên bản.”** Cách này có thể đơn giản trong giai đoạn đầu, nhưng nếu trở thành yêu cầu cố định thì khó có independent deployability. Với thay đổi cần phối hợp, nên chuyển thành contract/versioned rollout.

**“Chỉ cần retry là downstream sẽ khỏe.”** Retry không giới hạn có thể khuếch đại sự cố và làm quá tải thành lỗi dây chuyền.

**“Có circuit breaker thì có thể bỏ Payment.”** Breaker giúp fail fast, không thay thế điều kiện nghiệp vụ thanh toán thành công.

**“Rollback image chắc chắn đảo ngược migration.”** Data schema, event và giao dịch đã commit thường không tự quay theo image.

**“Một service không phụ thuộc service khác vì nó chỉ đọc chung database.”** Shared DB chính là phụ thuộc rất mạnh, thường khó version độc lập hơn API rõ ràng.

**“Không phụ thuộc gì” là mục tiêu tối ưu.** Trong hệ thống thực, mục tiêu tốt hơn là **phụ thuộc có hợp đồng, có đo lường, có cách ly và có đường hồi phục rõ**.

## 25. Mô hình quyết định kiến trúc cho từng dependency

Khi thêm một lời gọi từ service A tới B, hãy trả lời theo thứ tự:

1. **Có cần gọi B trong request path không?** Nếu không, cân nhắc event/queue hoặc local projection.
2. **B cung cấp dữ liệu duy nhất hay chỉ trang trí?** Xác định hard/soft dependency theo operation.
3. **Có thể dùng cache/snapshot không?** Đánh giá độ mới chấp nhận được, quyền truy cập và tính đúng đắn.
4. **Nếu B timeout, kết quả nghiệp vụ là gì?** Fail, pending, compensation hay fallback có giới hạn?
5. **Deadline và retry budget?** Tránh retry lồng nhau, đặt giới hạn theo toàn luồng.
6. **B có thể thay contract độc lập không?** Thỏa thuận version và contract tests.
7. **Dữ liệu nào thuộc về ai?** Không tạo shared DB hoặc distributed transaction ngầm.
8. **Ai chịu trách nhiệm incident và SLO?** Đặt owner và runbook.
9. **Có shared infrastructure nào làm cả A và B cùng ngừng?** Xác định failure domain.
10. **Thay đổi A có thể deploy và rollback riêng?** Kiểm tra cả runtime mixed versions.

Nếu chưa trả lời được câu 4 hoặc 6, việc tách A và B thành hai deployment chưa tạo ra lợi ích độ tin cậy và độc lập phát hành như kỳ vọng.

## 26. Bài tập thực hành

### Bài 1 — Phân loại ranh giới

Một ứng dụng có Orders, Payments và Inventory ở ba container, nhưng cả ba đọc/ghi cùng bảng `orders`. Mỗi container được deploy riêng qua CI. Hãy phân loại independent build, deployment, rollback, runtime/data dependency và nêu lý do việc đổi schema có thể buộc rollout đồng thời.

### Bài 2 — Bản đồ hard/soft dependency

Vẽ request path `GET /orders/{id}` và `POST /checkout`. Ghi dependency nào bắt buộc, nào có thể fallback; đề xuất response khi Recommendations, Inventory hoặc Payment bị lỗi.

### Bài 3 — Mixed-version rollout

Inventory v2 thêm trạng thái `RESERVED_PENDING`. Orders v1 chưa hiểu. Lập thứ tự thay consumer, provider, contract test, feature flag và rollback để Inventory v2 có thể deploy riêng mà vẫn phục vụ Orders v1.

### Bài 4 — Tính availability minh họa

Ba downstream bắt buộc có availability lần lượt là 99,95%, 99,9% và 99,8%. Giả định độc lập chỉ trong bài toán, tính availability lý thuyết của đường gọi đồng bộ cần cả ba. Giải thích vì sao lỗi chung hoặc caching khiến công thức đó không mô tả đủ hành vi thực tế.

### Bài 5 — Chọn cơ chế xử lý sự cố

Payment provider timeout sau khi đã ghi nhận giao dịch; Orders chưa nhận response. Thiết kế operation ID, trạng thái pending/reconciliation, idempotency và deadline. Nêu lý do không thể mặc định “thất bại rồi thanh toán lại bằng request mới”.

### Bài 6 — Triển khai riêng nhưng phụ thuộc platform

Cluster không thể tạo pod mới vì admission webhook hỏng, trong khi các pod đang chạy vẫn phục vụ. Phân biệt deployment-time và runtime dependency; đề xuất monitoring, runbook và điều kiện xác nhận khôi phục.

### Bài 7 — Kiểm thử khả năng chịu lỗi

Sử dụng môi trường thử nghiệm để mô phỏng broker unavailable 10 phút. Xác định backlog, outbox, consumer idempotency, retention, tuổi message và điều kiện nghiệp vụ nào vẫn được xem là thành công; phân biệt với test deploy image mới.

### Bài 8 — Thiết kế dashboard

Liệt kê tối thiểu bốn SLI cho Order Service và ba SLI cho hành trình checkout. Gắn mỗi SLI với nguồn telemetry, owner và một hành động khi vi phạm threshold.

## 27. Ghi nhớ

- **Independent deployment là khả năng nâng phiên bản một service mà không bắt các service khác deploy cùng thời điểm.**
- **Operational dependency là quan hệ về chức năng, dữ liệu, hạ tầng và con người khi service đang chạy; nó không biến mất vì mỗi service có image/repo/pipeline riêng.**
- **Độc lập triển khai cần compatibility theo thời gian**, vì trong rolling/canary deployment luôn có nguy cơ cùng lúc tồn tại phiên bản cũ và mới.
- **Không có “zero dependencies” trong phần lớn hệ thống thực.** Hãy biết dependency nào bắt buộc cho operation nào và fail behavior đã được chấp nhận.
- **Event-driven giảm coupling thời gian**, nhưng vẫn có broker, backlog, schema và consumer dependency.
- **Shared database, chung tài nguyên và hạ tầng nền** có thể tạo điểm lỗi chung dù service được đóng gói riêng.
- **Timeout, retry budget, breaker, bulkhead, idempotency và recovery** giúp giảm khuếch đại lỗi, không thay thế logic nghiệp vụ.
- **Đo deploy autonomy và runtime resilience bằng hai bộ kiểm tra khác nhau**, đồng thời đánh giá SLO của hành trình người dùng.
- **Ownership và phối hợp incident** phải rõ: độc lập phát hành không có nghĩa mỗi team tự sửa được mọi dependency khi sự cố lan rộng.

Một thiết kế microservices tốt **trao quyền cho mỗi service thay đổi theo nhịp phù hợp**, đồng thời **thừa nhận và quản lý các phụ thuộc đang tồn tại** bằng hợp đồng, khả năng tương thích, cách ly lỗi, quan sát và quy trình vận hành.

### Đọc thêm

- Martin Fowler — Microservices: https://martinfowler.com/articles/microservices.html
- Martin Fowler — Microservice Prerequisites: https://martinfowler.com/bliki/MicroservicePrerequisites.html
- Google SRE Book — Addressing Cascading Failures: https://sre.google/sre-book/addressing-cascading-failures/
- Google SRE Workbook — Implementing SLOs: https://sre.google/workbook/implementing-slos/
- Microsoft Azure Architecture Center — Microservices Architecture Style: https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/microservices
- Kubernetes — Deployments: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- OpenTelemetry — Distributed Traces: https://opentelemetry.io/docs/concepts/signals/traces/

Các công thức, giá trị availability, phiên bản dịch vụ và quy trình rollout trong bài là ví dụ minh họa. Hành vi thực tế phải được kiểm chứng với hợp đồng, hạ tầng và SLO của hệ thống đang vận hành.
