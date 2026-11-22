# Connector, trigger và action trong Logic Apps

Một doanh nghiệp nhận đơn hàng qua API, cần kiểm tra dữ liệu, gửi yêu cầu xử lý vào hàng đợi, lưu biên nhận và thông báo cho bộ phận vận hành khi bước nào đó thất bại. Nếu tất cả được viết trong một ứng dụng tích hợp lớn, mỗi thay đổi về hệ thống đích có thể đòi hỏi sửa mã và triển khai lại nhiều thành phần. **Azure Logic Apps** giúp mô hình hóa luồng tích hợp dưới dạng các bước có **trigger** khởi động, **action** thực thi và **connector** kết nối đến dịch vụ khác.

Ví dụ đơn giản:

```text
Đối tác gửi HTTP POST
          |
          v
Trigger: When an HTTP request is received
          |
          v
Action: Parse JSON / validate
          |
          v
Action: Send message to Azure Service Bus
          |
          +-- Succeeded --> Action: Response 202 Accepted
          |
          +-- Failed ----> Action: log/alert + Response lỗi phù hợp
```

Bài này thuộc chương **API và tích hợp quy trình** của module `CLOUD_PROVIDERS_AZURE`. Module giúp khám phá Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời thực hành triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Trọng tâm ở đây là **cách Logic Apps kết nối, được kích hoạt, xử lý dữ liệu và vận hành đáng tin cậy**, không chỉ thao tác kéo-thả trên giao diện.

> Ví dụ dùng dữ liệu và tên tài nguyên giả lập. Cách đặt tên connector/action, tính năng authentication, màn hình designer, SKU và giới hạn kỹ thuật có thể thay đổi theo **Consumption/Standard**, region và phiên bản dịch vụ. Chỉ tạo workflow và kết nối đến hệ thống thật khi có quyền và chính sách tổ chức cho phép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khái niệm **Logic App**, **workflow**, **connector**, **connection**, **trigger**, **action** và **run**.
2. Phân biệt Logic Apps **Consumption** và **Standard**, hiểu tác động đến connector và vận hành.
3. Chọn giữa **built-in connector**, **managed connector**, HTTP action và các connector được hỗ trợ khác.
4. Phân biệt **polling trigger**, **webhook/event trigger**, **Request trigger** và **Recurrence trigger**.
5. Xây workflow gồm action truy cập dữ liệu, điều kiện, vòng lặp, biến và xử lý lỗi.
6. Dùng dynamic content và biểu thức **Workflow Definition Language** để ánh xạ input/output.
7. Thiết kế **runAfter**, scopes và retry policy để xử lý lỗi không gây gửi trùng.
8. Tổ chức API connections, Microsoft Entra identity/managed identity và secrets theo nguyên tắc quyền tối thiểu.
9. Kiểm thử, quan sát trigger history, run history và diagnostic logs.
10. Ước lượng chi phí từ tần suất kích hoạt, số action, connector, hosting và logging.
11. Tạo một quy trình tích hợp HTTP → validate → Service Bus → response và xử lý những failure paths thường gặp.
12. Nhận diện giới hạn của workflow đối với transaction, idempotency và dữ liệu nhạy cảm.

## 2. Logic Apps giải quyết vấn đề gì?

**Azure Logic Apps** là nền tảng xây dựng và vận hành workflow tích hợp trên Azure. Người phát triển mô tả một chuỗi hành động bằng designer hoặc workflow definition; Azure chịu trách nhiệm chạy, lên lịch, kết nối dịch vụ và cung cấp trạng thái theo mô hình hosting đã chọn.

Một workflow có thể:

- Nhận một webhook hoặc HTTP request từ đối tác.
- Định kỳ đọc tệp trong storage hoặc hệ thống SaaS.
- Chuyển đổi JSON/XML và chuẩn hóa dữ liệu.
- Gửi message tới Azure Service Bus.
- Kích hoạt API nội bộ hoặc Azure Function.
- Ghi dữ liệu vào SQL, Blob Storage hay dịch vụ khác.
- Gửi thông báo khi lỗi hoặc kết quả vượt ngưỡng.
- Thực hiện điều kiện, nhánh song song, lặp, chờ và xử lý exception.

Logic Apps hữu ích khi luồng tích hợp **ghép nhiều dịch vụ**, cần thay đổi quy trình tương đối nhanh, muốn dùng connector có sẵn và theo dõi lịch sử chạy. Nó **không tự thay thế** hệ thống giao dịch database, API gateway, broker hoặc một ứng dụng tính toán chuyên sâu. Workflow vẫn cần thiết kế đúng retry, schema, quyền, giới hạn và xử lý lỗi.

### Ví dụ nghiệp vụ

Cửa hàng có ba yêu cầu:

1. Mỗi khi có đơn hàng được đối tác gửi đến, tiếp nhận và xác thực đầu vào.
2. Đẩy thông tin hợp lệ vào queue để backend xử lý bất đồng bộ.
3. Nếu queue không khả dụng, ghi nhận sự cố và trả phản hồi không đánh lừa đối tác rằng đơn đã tiếp nhận thành công.

Luồng này phù hợp với Logic Apps vì gồm **nhiều dịch vụ có giao diện sẵn** và quy tắc tích hợp rõ ràng.

## 3. Từ vựng cốt lõi

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Logic App resource** | Tài nguyên Azure chứa khả năng chạy workflow theo loại hosting. | `la-orders-intake-prod` |
| **Workflow** | Định nghĩa một quy trình gồm trigger và actions. | `ReceiveOrder` |
| **Connector** | Thành phần cung cấp các thao tác/triggers cho dịch vụ hoặc giao thức. | Service Bus, SQL, HTTP, Blob, Office 365 |
| **Connection** | Cấu hình kết nối/xác thực đến một hệ thống cụ thể, thường có identity/credential và scope. | Kết nối tới namespace Service Bus Production |
| **Trigger** | Điều kiện/sự kiện làm khởi đầu một run. | HTTP request, lịch 5 phút, có message mới |
| **Action** | Bước thực thi sau trigger hoặc sau action khác. | Parse JSON, Condition, Send message |
| **Run** | Một lần thực thi workflow gắn với trigger và lịch sử trạng thái. | Run xử lý đơn `ORD-1042` |
| **Expression** | Biểu thức truy cập/biến đổi dữ liệu runtime. | `triggerBody()?['orderId']` |
| **Dynamic content** | Giá trị output từ trigger/action trước đó có thể chèn vào bước sau. | `orderId` từ request |
| **runAfter** | Quy tắc cho action chạy sau action khác với trạng thái cụ thể. | Chạy cảnh báo khi Send message Failed |

**Connector không đồng nghĩa connection**: Service Bus connector cung cấp chức năng gửi/nhận message, còn connection xác định **đúng namespace và quyền** để workflow gọi connector đó.

## 4. Workflow hoạt động như thế nào?

Một workflow thường có **một trigger** làm điểm vào; sau đó action graph quyết định các bước kế tiếp. Workflow có thể có nhánh điều kiện, nhánh song song, scope và vòng lặp, nhưng không phải là một chương trình chạy vô hạn mà không có giới hạn.

```text
                 Workflow definition
                         |
                         v
                    [TRIGGER]
                         |
                  Trigger fired?
                   /          \
                 No            Yes
                 |              |
             Chưa có run        v
                           Run started
                                |
                           [ACTION A]
                                |
                       +--------+---------+
                       |                  |
                    Success             Failure
                       |                  |
                   [ACTION B]         [HANDLE ERROR]
                       |                  |
                       +--------+---------+
                                |
                           Run outcome
```

Một run có thể có trạng thái **Succeeded, Failed, Cancelled, Running** hoặc trạng thái khác được runtime hỗ trợ. Trạng thái action như **Succeeded, Failed, Skipped, TimedOut** là tín hiệu quan trọng để quyết định nhánh theo `runAfter`.

### Trigger kiểm tra hoặc nhận dữ liệu không phải action

Ví dụ:

- **Recurrence trigger** chạy theo lịch.
- **Request trigger** chờ HTTP request.
- **Service Bus trigger** nhận event/message theo cơ chế connector.
- **SQL action** thực hiện câu truy vấn sau khi trigger đã kích hoạt.
- **Response action** trả kết quả cho caller trong workflow phù hợp.

Nhầm trigger với action có thể dẫn tới một thiết kế không đúng: đặt một action “đọc file” sau Recurrence không giống một trigger “khi file thay đổi” về tần suất, trạng thái, polling, quyền hoặc cách nhận dữ liệu.

## 5. Consumption và Standard: tác động đến connector/trigger/action

Azure Logic Apps có những mô hình hosting quan trọng:

| Khía cạnh | Logic Apps Consumption | Logic Apps Standard |
|---|---|---|
| Kiểu hosting | Multi-tenant theo mô hình Consumption. | Single-tenant Logic Apps runtime trên hạ tầng hosting Standard. |
| Tổ chức workflow | Thường mỗi Logic App resource có một workflow. | Một Logic App resource có thể chứa **nhiều workflows**. |
| Workflow runtime | Stateful workflow theo mô hình Consumption. | Có **stateful** và **stateless** workflows theo khả năng Standard. |
| Connectors | Built-in/control actions và managed connectors theo hỗ trợ. | In-app/built-in service-provider connectors cùng managed connectors tùy dịch vụ. |
| Kết nối | Managed API connections là thành phần quan trọng với nhiều connectors. | Có built-in connection settings và managed API connections tùy loại connector. |
| Scale/billing | Thường tính theo trigger/action execution, connector operations và các thành phần khác. | Có chi phí hosting plan/runtime/capacity cùng managed connector operations và thành phần liên quan. |
| Local development | Tùy công cụ hỗ trợ; designer trong Azure phổ biến. | Workflow project/runtime Standard phù hợp VS Code và CI/CD theo tính năng. |
| Isolation/network | Phụ thuộc SKU và cấu hình hỗ trợ. | Có nhiều lựa chọn tích hợp mạng và vận hành theo hosting; cần đối chiếu region/plan. |

**Standard không có nghĩa tất cả connectors miễn phí**, và **Consumption không có nghĩa không bao giờ mất phí khi không có request** nếu tài nguyên phụ trợ/điều kiện billing khác còn tồn tại. Phải xem đơn vị tính phí thực tế.

### Stateful và stateless (Standard)

- **Stateful:** lưu/truy vết trạng thái workflow để quản lý các bước, thời gian chạy và lịch sử theo cách runtime cung cấp; phù hợp tích hợp kéo dài, cần quan sát/khôi phục.
- **Stateless:** ưu tiên luồng ngắn, giảm overhead của việc lưu trạng thái từng bước; có giới hạn về thời gian/độ dài và cách xem history, phù hợp kịch bản latency thấp khi ứng dụng đáp ứng yêu cầu.

Không chọn stateless cho một quy trình chờ phê duyệt nhiều ngày nếu runtime/stateless limits không hỗ trợ. Ngược lại, không mặc định workflow nào cũng cần lưu lịch sử chi tiết từng bước khi yêu cầu throughput/latency cao.

## 6. Connector là gì?

**Connector** đóng gói những thao tác tích hợp vào một dịch vụ hoặc giao thức, cho phép designer liệt kê trigger/action mà không phải tự viết mọi HTTP request.

Ví dụ:

| Connector / nhóm | Trigger/action điển hình | Tình huống |
|---|---|---|
| **HTTP** | Gọi một REST endpoint hoặc nhận request qua Request trigger. | Gọi API nội bộ/đối tác. |
| **Azure Service Bus** | Gửi message, nhận message theo connector cung cấp. | Xếp hàng xử lý đơn hàng. |
| **Azure Blob Storage** | Đọc/ghi blob, kiểm tra blob/tệp thay đổi nếu có trigger tương ứng. | Lưu biên nhận hoặc nhận tệp. |
| **Azure SQL** | Truy vấn/thêm/cập nhật record theo action hỗ trợ. | Đối soát dữ liệu. |
| **Office 365 Outlook** | Trigger email mới, gửi email. | Thông báo hoặc xử lý mail. |
| **SharePoint** | Theo dõi hoặc tạo/cập nhật item theo connector. | Phê duyệt và cộng tác. |
| **Event Grid / Event Hubs** | Xử lý luồng hoặc event khi có connector phù hợp. | Event-driven integration/stream ingestion. |
| **Azure Functions** | Gọi Function endpoint được cấu hình. | Logic chuyên biệt ngoài khả năng data actions. |
| **Custom connector** | Cung cấp interface cho API riêng theo mô hình được hỗ trợ. | Hệ thống đối tác/nội bộ chưa có connector sẵn. |

Tên action và capability khác theo **connector, loại workflow, SKU và authentication mode**. Không suy diễn “có connector” là mọi operation của hệ thống đích đã được hỗ trợ.

### Connector giúp gì?

1. Cung cấp contract input/output trong designer.
2. Hỗ trợ cách kết nối và authentication theo dịch vụ.
3. Giúp chèn dynamic content từ kết quả action.
4. Một số connector có trigger dạng polling hoặc webhook.
5. Cung cấp lỗi/trạng thái dùng cho branching.
6. Tận dụng tài liệu và cơ chế vận hành của connector thay vì viết REST integration từ đầu.

### Connector không làm gì?

- Không tự bảo đảm dữ liệu nghiệp vụ được commit ở backend.
- Không tự giải quyết duplicate requests hay idempotency.
- Không thay thế phân quyền và network.
- Không bảo đảm mọi HTTP 5xx đều được retry mãi tới khi thành công.
- Không tạo transaction ACID trải qua SQL, Service Bus và email.
- Không miễn mọi giới hạn API, rate limit hoặc chi phí của SaaS đích.

## 7. Built-in, managed và service-provider connectors

Đây là điểm cần hiểu khi chọn Logic Apps Consumption hay Standard.

### Built-in connectors / actions

Một số thao tác như **Control, Data Operations, HTTP/Request hoặc workflow operations** được runtime hỗ trợ theo mô hình built-in. Ở Standard, còn có các **in-app service-provider connectors** như một số kết nối tới Azure Services được chạy trong runtime Standard.

Đặc điểm có thể gồm:

- Gọi qua runtime nội bộ hơn thay vì managed connector gateway cho một số thao tác.
- Cấu hình kết nối khác managed connector.
- Tối ưu performance/latency trong những trường hợp cụ thể.
- Vẫn chịu giới hạn, RBAC và chi phí hạ tầng/địch vụ đích.

### Managed connectors

Managed connector thường truy cập dịch vụ qua hạ tầng **Azure managed connector** và có cấu hình **API connection** liên quan. Ví dụ các SaaS connectors như Outlook/SharePoint, cùng các Azure connectors tùy lựa chọn.

Đặc điểm:

- Có thể yêu cầu tạo resource/configuration **API connection** và bước ủy quyền.
- Có thể có quota/rate limit của connector/API và phí connector operations.
- Credential có thể hết hạn hoặc bị thu hồi.
- Cần chú ý connection ownership, consent, tenant, secret rotation.
- Trong Standard, một số dịch vụ vừa có built-in/service-provider connector vừa có managed connector; **chúng không đồng nhất** về connector settings và hành vi.

### Bảng so sánh

| Tiêu chí | Built-in / in-app | Managed |
|---|---|---|
| Nơi thực thi tích hợp | Trong runtime/host theo connector được hỗ trợ. | Hạ tầng managed connector/API connection theo mô hình dịch vụ. |
| Connection config | Có thể là app settings/connection config riêng. | Thường gắn với API connection được quản lý. |
| Authentication | Tùy connector; có thể hỗ trợ managed identity. | Tùy connector và operation, OAuth/API key/managed identity khi hỗ trợ. |
| Availability | Phụ thuộc Consumption/Standard và service provider. | Phụ thuộc danh mục managed connectors, region, tier. |
| Giới hạn | Runtime, connector và hệ thống đích. | Connector throttling, API limits và hệ thống đích. |
| Chi phí | Hosting/operations theo SKU. | Có thể thêm phí managed connector operations. |

**Đừng chọn connector chỉ dựa trên icon trong designer**. Hãy kiểm tra loại connector, authentication, runtime behavior, retry, networking, cost và tính năng hỗ trợ trong SKU đã chọn.

## 8. Connection và API connection: xác thực đến đúng đích

Một action “Send message” cần biết **gửi đến namespace nào và với quyền gì**. Thông tin đó thường đến từ connection config, không phải từ việc đặt tên action.

```text
Logic App: orders-intake
    |
    +-- Connector: Azure Service Bus
             |
             +-- Connection: sb-orders-prod
                     |
                     +-- Endpoint: namespace cụ thể
                     +-- Authentication: managed identity / credential được hỗ trợ
                     +-- Authorization: quyền Send
```

Những điểm cần kiểm tra:

- **Resource đích:** có phải namespace/storage account/database Production đúng?
- **Principal:** managed identity, service principal hay user credential?
- **Role/scope:** chỉ Send vào queue hay cả Manage namespace?
- **Network:** endpoint, private DNS, firewall, VNet integration?
- **Vòng đời:** khi người tạo connection rời công ty, OAuth consent hết hạn hoặc secret bị rotate thì sao?
- **Ownership:** tài nguyên API connection có được tạo/triển khai cùng workflow không?
- **Secrets:** connection string/token có bị ghi vào file JSON, deployment logs hoặc parameters không?

Một API connection **thành công khi tạo** không chứng minh action thật sẽ chạy được lâu dài. Cần kiểm tra permission đối với resource đích, token refresh và thử một giao dịch an toàn.

## 9. Trigger là điều kiện bắt đầu run

**Trigger** xác định lúc nào workflow bắt đầu. Trong Logic Apps, trigger có thể kiểm tra theo lịch hoặc được kích hoạt khi có một request/event, tùy connector.

Các nhóm thường gặp:

| Loại trigger | Cách hoạt động khái quát | Ví dụ |
|---|---|---|
| **Recurrence** | Runtime kích hoạt theo lịch được cấu hình. | Mỗi 15 phút tổng hợp báo cáo. |
| **Polling** | Kiểm tra nguồn theo chu kỳ để phát hiện dữ liệu/sự kiện mới. | Kiểm tra có file hoặc record mới. |
| **Webhook / push** | Đăng ký callback; nguồn gọi khi có sự kiện. | Thông báo thay đổi khi nguồn hỗ trợ. |
| **Request** | Workflow tiếp nhận HTTP request tại endpoint trigger. | Đối tác POST đơn hàng. |
| **Event/message trigger** | Nhận message/event từ broker theo khả năng connector. | Có message mới trong Service Bus queue. |
| **Manual / external invocation** | Workflow được gọi bởi hệ thống/người dùng/logic khác theo cơ chế hỗ trợ. | Kiểm thử hoặc workflow chaining. |

Không giả định mọi action của một connector đều có trigger tương ứng. Danh sách các trigger phụ thuộc connector, workflow type và SKU.

### Trigger và action có cùng một connector?

Có thể có cả hai. Ví dụ Service Bus connector có thể cung cấp trigger nhận message và action gửi message; SQL connector có thể cung cấp trigger theo dõi thay đổi và action truy vấn dữ liệu. Nhưng cách kết nối, permission và polling behavior có thể khác nhau.

## 10. Polling trigger: độ trễ và số lần kiểm tra

Polling trigger chạy theo một chu kỳ, chẳng hạn mỗi 5 phút kiểm tra nguồn có item mới.

```text
09:00  Poll → không có dữ liệu
09:05  Poll → tìm thấy item A → workflow run
09:10  Poll → item B, C → workflow run(s) theo cơ chế trigger
09:15  Poll → không có dữ liệu
```

**Không mặc định** một lần poll tương đương đúng một workflow run hoặc luôn nhận đủ mọi item; trigger có thể hỗ trợ batching, split-on, watermark hoặc paging theo connector.

### Cần cấu hình gì?

- **Interval/frequency** của trigger.
- **Time zone** nếu phụ thuộc lịch kinh doanh.
- **Start time** và điều kiện lọc dữ liệu.
- **Concurrency** nếu nhiều run có thể chạy chồng nhau.
- **Polling window**, pagination hoặc cơ chế lưu checkpoint của connector nếu được hỗ trợ.
- **Retry/backoff** khi nguồn tạm không khả dụng.
- Khả năng API đích giới hạn **rate limit** hoặc số request.

### Độ trễ và chi phí

Với chu kỳ 5 phút, một item có thể không được phát hiện ngay lập tức. Độ trễ còn phụ thuộc backend connector, throttling, thời gian processing và lịch runtime. **Đặt poll 1 giây không bảo đảm near-real-time** nếu connector có giới hạn minimum polling interval hoặc dịch vụ đích không đáp ứng.

Một polling trigger có thể tiêu tốn operations/API quota dù không tìm thấy item mới, tùy SKU và cơ chế connector. Khi chỉ cần xử lý khi có event, xem nguồn có hỗ trợ webhook/push không.

## 11. Webhook/push trigger: đẩy sự kiện tới workflow

Webhook trigger thường thiết lập hoặc sử dụng cơ chế đăng ký callback với hệ thống nguồn; sau đó nguồn **push notification** tới endpoint để kích hoạt run.

```text
Logic App đăng ký callback
         |
         v
Nguồn phát event
         |
         +-- POST callback → Logic App trigger → run
         |
         +-- có thể retry callback theo quy tắc nguồn
```

Ưu điểm:

- Không cần liên tục polling trong những trường hợp hỗ trợ.
- Có thể giảm thời gian từ event đến run.
- Phù hợp dịch vụ có hệ thống notification subscription ổn định.

Cần chú ý:

- Cơ chế đăng ký/hủy đăng ký callback và expiry.
- Authentication/chữ ký webhook nếu nguồn cung cấp.
- Retry/duplicate callback: **một event có thể kích hoạt nhiều lần** khi nguồn gửi lại.
- Endpoint public/private reachability và firewall.
- Khi workflow bị disabled/xóa/đổi endpoint, subscription cũ có thể còn tồn tại ở phía nguồn tùy connector.
- Không tự coi webhook event là chứng cứ nghiệp vụ đã commit tại hệ thống nguồn; đôi khi cần gọi API để lấy dữ liệu chuẩn.

**Webhook trigger và Request trigger khác nhau:** Request trigger cung cấp endpoint cho caller chủ động gọi; webhook connector có thể quản lý việc đăng ký với event source và semantics riêng.

## 12. Request trigger: tạo endpoint HTTP cho workflow

**When an HTTP request is received** là trigger quen thuộc cho kịch bản webhook do bạn quản lý hoặc API intake.

Ví dụ caller gửi:

```http
POST /orders HTTP/1.1
Content-Type: application/json

{
  "orderId": "ORD-1042",
  "customerRef": "C-81",
  "amount": 250000,
  "currency": "VND"
}
```

Đoạn trên **mô phỏng HTTP request**; URL thật của Logic App không tự là `/orders` theo tên đẹp trong ví dụ. URL gọi thực tế được runtime tạo, có thể chứa **chữ ký/credential** và đường dẫn workflow riêng.

### Các bước thiết kế

1. Thêm Request trigger.
2. Định nghĩa JSON schema cho dữ liệu đầu vào.
3. Chỉ chấp nhận phương thức/kiểu yêu cầu phù hợp theo cấu hình hỗ trợ.
4. Xác thực caller theo mô hình được phê duyệt.
5. Đặt giới hạn payload, timeout, concurrency và xử lý lỗi.
6. Parse/validate dữ liệu.
7. Xử lý hành động bền vững (ví dụ gửi tới Service Bus) trước khi trả `202 Accepted`.
8. Dùng **Response** action nếu cần trả status/body rõ ràng.

### Bảo vệ callback URL

Một Request trigger URL có thể mang chữ ký truy cập (SAS hoặc token) tùy cấu hình. **Bất kỳ ai sở hữu URL có quyền gọi** theo phương thức xác thực được áp dụng; không đăng URL có chữ ký trong Git, log, ảnh chụp màn hình hoặc ticket công khai.

Các cách bảo vệ cần đánh giá theo SKU và yêu cầu:

- Microsoft Entra authentication cho workflow endpoint khi được hỗ trợ.
- API Management đứng trước endpoint, áp dụng OAuth/JWT, quota và rate limit.
- HTTPS/TLS, private networking/access restrictions phù hợp.
- WAF/Front Door hoặc gateway theo topology nếu cần.
- Rotate/thu hồi callback signature và quản lý quyền xem URL.
- Không đưa dữ liệu nhạy cảm vào query string hoặc URL nếu tránh được.

**Không đồng nhất schema validation với authorization.** JSON hợp lệ vẫn có thể do caller không có quyền gửi.

## 13. Recurrence trigger: lịch chạy và múi giờ

Recurrence phù hợp với các luồng định kỳ:

- Mỗi 15 phút đọc dữ liệu doanh số.
- Mỗi đêm tạo báo cáo.
- Mỗi ngày kiểm tra dữ liệu cần đối soát.

Ví dụ:

```text
Trigger: Recurrence
Frequency: Day
Interval: 1
Time zone: Asia/Ho_Chi_Minh (nếu designer/runtime hỗ trợ giá trị tương ứng)
At these hours: 07
At these minutes: 30
```

Đây là **cấu hình khái niệm**, không phải JSON manifest cụ thể. Trong thực tế cần kiểm tra quy tắc timezone và daylight saving của vùng chạy, thời điểm bắt đầu, xử lý missed schedule và số run trùng nhau.

### Tránh workflow chạy chồng

Nếu một run mất 20 phút mà Recurrence kích hoạt mỗi 10 phút, nhiều run có thể chạy đồng thời, truy cập cùng file/record và tạo dữ liệu trùng. Có thể giải quyết bằng:

1. Giới hạn trigger concurrency nếu hỗ trợ.
2. Dùng business lock hoặc cơ chế idempotency.
3. Thiết kế batch/window ID riêng cho mỗi kỳ.
4. Đặt lịch phù hợp thời gian chạy thực tế.
5. Khi không thể bỏ qua kỳ nào, có cơ chế queue/checkpoint/đối soát.

Không dùng delay tùy tiện để “chắc chắn run trước xong” vì thời gian chạy có thể thay đổi.

## 14. Action: một bước trong luồng xử lý

Sau trigger, mỗi action thực hiện một thao tác cụ thể như:

- **Compose** giá trị.
- **Parse JSON** theo schema.
- **Condition** rẽ nhánh.
- **For each** lặp qua tập item.
- **HTTP** gọi dịch vụ.
- **Send message** gửi tới Service Bus.
- **Create blob** lưu tài liệu.
- **Response** trả HTTP response.
- **Scope** nhóm nhiều actions.
- **Terminate** kết thúc workflow theo trạng thái được cấu hình.

Một action có:

- **Inputs:** dữ liệu, parameters và connection.
- **Outputs:** kết quả hoặc thông tin lỗi.
- **Status:** Succeeded, Failed, Skipped, TimedOut... theo runtime.
- **runAfter:** điều kiện chạy sau action khác.
- **Retry policy:** cách thử lại lỗi có thể phục hồi khi khả năng action hỗ trợ.
- **Timeout:** giới hạn thời gian action theo cấu hình và runtime.

**Action thành công về mặt HTTP/connector không chắc đồng nghĩa công việc nghiệp vụ đã xong.** Ví dụ action gửi message Service Bus trả thành công chỉ xác nhận message được broker nhận, chưa xác nhận consumer đã thanh toán đơn hàng.

## 15. Control actions: Condition, Switch, For each, Until và Scope

| Action | Ý nghĩa | Lỗi thường gặp |
|---|---|---|
| **Condition** | Chọn một trong hai nhánh theo biểu thức. | So sánh sai kiểu string/number hoặc null. |
| **Switch** | Rẽ nhánh theo nhiều giá trị. | Thiếu nhánh Default hoặc không xử lý giá trị mới. |
| **For each** | Thực thi actions cho từng phần tử. | Ghi chung biến khi chạy song song hoặc gọi API quá nhiều. |
| **Until** | Lặp cho tới khi điều kiện đạt hoặc chạm giới hạn. | Không có giới hạn an toàn, poll vô tận. |
| **Scope** | Nhóm actions để xử lý kết quả và lỗi ở cấp nhóm. | Nhầm skipped/failed ở scope và nested actions. |
| **Terminate** | Kết thúc workflow với trạng thái chủ động. | Đánh dấu Succeeded khi workflow thực tế thất bại. |
| **Delay / Delay until** | Tạm hoãn bước xử lý. | Dùng Delay thay cơ chế queue/retry dài hạn. |
| **Parallel branches** | Chạy nhánh độc lập cùng lúc. | Hai nhánh cùng sửa một resource không có đồng bộ. |

### Ví dụ Condition

Đơn hàng hợp lệ khi `amount > 0` và `orderId` có giá trị:

```text
Condition:
  amount > 0 AND orderId is not empty
    |
    +-- True:
    |     Send message to queue
    |
    +-- False:
          Respond 400 Bad Request / audit invalid data
```

Nếu `amount` được đưa vào dưới dạng string như `"250000"`, phải chuyển kiểu trước khi so sánh số. Nếu trường vắng mặt, expression có thể trả null hoặc báo lỗi tùy cách truy cập.

### Ví dụ Switch

```text
Switch eventType
  OrderPlaced    → queue orders-created
  OrderCancelled → queue orders-cancelled
  Other/Default  → quarantine/validation error
```

Đừng chỉ định Default là “thành công” nếu event schema có thể mở rộng trong tương lai; việc im lặng bỏ dữ liệu có thể rất khó phát hiện.

## 16. For each và xử lý song song: tránh race condition

Giả sử workflow nhận danh sách 100 sản phẩm và cần gọi API cập nhật kho cho mỗi sản phẩm.

```text
For each product in products:
    HTTP POST /inventory/update
```

Vấn đề:

- For each có thể chạy các vòng song song theo mặc định/cấu hình của môi trường.
- Một API đích có thể giới hạn concurrent requests và trả HTTP 429.
- Các vòng không được bảo đảm hoàn thành theo đúng thứ tự input.
- Một **variable chung** được cập nhật từ nhiều iteration có thể bị tranh chấp.
- Một vòng lỗi có thể ảnh hưởng trạng thái chung của loop theo rules của runtime.

### Cách thiết kế tốt

1. Chỉ dùng vòng lặp song song khi các item độc lập.
2. Nếu thứ tự hoặc ghi chung state quan trọng, cấu hình concurrency phù hợp, thậm chí chạy tuần tự khi cần.
3. Dùng idempotency key cho từng item.
4. Đặt retry/backoff có giới hạn khi API trả 429/503.
5. Kiểm soát pagination để không tự tin rằng chỉ 100 item khi nguồn có 10.000 item.
6. Nếu khối lượng lớn, cân nhắc đẩy từng công việc vào queue để worker scale theo capacity.

Không sửa giới hạn concurrency của cả workflow chỉ để giải một vòng lặp khi có thể tách logic thành actions/worker xử lý song song an toàn hơn.

## 17. Data Operations: Compose, Parse JSON, Select, Filter array

Các action biến đổi dữ liệu giúp chuẩn hóa payload mà không cần viết một microservice nhỏ cho mọi phép ánh xạ.

### Compose

Tạo giá trị mới từ input:

```text
Input:
  orderId = "ORD-1042"
  amount = 250000

Compose:
  {
    "orderId": "ORD-1042",
    "amount": 250000,
    "source": "partner-api"
  }
```

### Parse JSON

Khai báo cấu trúc JSON để designer cung cấp những trường dynamic content có tên rõ ràng. Ví dụ schema:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string", "minLength": 1 },
    "amount": { "type": "number", "exclusiveMinimum": 0 },
    "currency": { "type": "string" }
  },
  "required": ["orderId", "amount", "currency"],
  "additionalProperties": false
}
```

Đây là schema nghiêm ngặt minh họa. Với API có schema tiến hóa, `additionalProperties: false` có thể loại bỏ những field mới từ đối tác; cần thỏa thuận contract thay vì tự áp dụng.

### Select

Chuyển đổi mỗi phần tử của mảng thành cấu trúc mới, ví dụ từ `[{sku, qty, price}]` sang `[{productId, quantity}]`.

### Filter array

Giữ những phần tử đáp ứng điều kiện, ví dụ đơn có `amount > 0`.

**Không lẫn Filter array với authorization hoặc validation dữ liệu đầu vào**: loại bỏ phần tử âm thầm có thể khiến tổng tiền đơn hàng sai. Với dữ liệu nghiệp vụ quan trọng, nên từ chối payload sai hoặc ghi nhận chính xác những item bị loại.

## 18. Dynamic content và biểu thức Workflow Definition Language

Designer hiển thị **Dynamic content** từ trigger và action trước đó. Ở nền tảng, workflow sử dụng expressions để truy cập dữ liệu runtime.

Ví dụ:

| Mục đích | Biểu thức minh họa | Ý nghĩa |
|---|---|---|
| Đọc body của trigger | `triggerBody()` | Payload trigger. |
| Đọc một field an toàn với null | `triggerBody()?['orderId']` | Field `orderId` nếu tồn tại. |
| Đọc output action | `outputs('Compose_Order')` | Giá trị output của action có tên tương ứng. |
| Đọc body action | `body('Parse_JSON')` | Body của action được chỉ định. |
| Lấy một field output | `body('Parse_JSON')?['amount']` | Giá trị `amount` sau parse. |
| Định dạng JSON | `string(...)`, `json(...)` | Chuyển kiểu theo nhu cầu. |
| Thời điểm hiện tại | `utcNow()` | Giá trị UTC runtime; không thay thế event timestamp gốc. |
| Tạo ID | `guid()` | UUID mới, phù hợp correlation khi cần. |
| Kết hợp chuỗi | `concat('order-', triggerBody()?['orderId'])` | Tạo key có tiền tố. |

**Tên action trong expression phải khớp tên nội bộ của workflow**, không phải luôn trùng chính xác label người dùng nhìn thấy. Sau khi đổi tên action, kiểm tra lại những expression tham chiếu.

### Cú pháp expression trong JSON

Một expression đầy đủ trong workflow JSON thường được biểu diễn bằng ký hiệu mở đầu `@`:

```json
{
  "orderId": "@triggerBody()?['orderId']",
  "correlationId": "@coalesce(triggerBody()?['correlationId'], guid())",
  "receivedAtUtc": "@utcNow()"
}
```

Khi cần chèn expression vào chuỗi có phần văn bản cố định, runtime có cú pháp **interpolation** dạng `@{...}`. Không đặt dấu ngoặc/nháy tùy tiện làm expression bị coi là chuỗi literal.

### Null và lỗi parse

Một field không có có thể cho kết quả null; việc dùng `int(null)` hoặc truy cập field lồng nhau thiếu bảo vệ có thể làm action Fail. Vì vậy:

1. Validation với schema đúng.
2. Dùng toán tử null-safe `?` ở nơi phù hợp.
3. Dùng `coalesce` cho giá trị thay thế có ý nghĩa.
4. Kiểm tra kiểu thật của nguồn (string vs number vs array).
5. Không tự đặt giá trị mặc định 0 cho tổng tiền nếu điều đó che giấu payload hỏng.

## 19. Workflow JSON: cấu trúc tối thiểu

Logic Apps sử dụng workflow definition dựa trên cấu trúc có `triggers` và `actions`. Ví dụ tối giản sau **chỉ minh họa cấu trúc và biểu thức**, chưa gửi dữ liệu vào queue:

```json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {},
  "triggers": {
    "When_HTTP_request_received": {
      "type": "Request",
      "kind": "Http",
      "inputs": {
        "schema": {
          "type": "object",
          "properties": {
            "orderId": { "type": "string" }
          },
          "required": ["orderId"]
        }
      }
    }
  },
  "actions": {
    "Compose_Order": {
      "type": "Compose",
      "inputs": {
        "orderId": "@triggerBody()?['orderId']",
        "receivedAtUtc": "@utcNow()"
      },
      "runAfter": {}
    },
    "Response_200": {
      "type": "Response",
      "inputs": {
        "statusCode": 200,
        "body": "@outputs('Compose_Order')"
      },
      "runAfter": {
        "Compose_Order": ["Succeeded"]
      }
    }
  },
  "outputs": {}
}
```

**Chú ý:** Response 200 trong ví dụ trên chỉ xác nhận workflow đã đọc/compose payload; **không được diễn giải là đã lưu đơn hàng hoặc enqueue bền vững**. Trong kịch bản thật, chỉ trả 202 Accepted khi action tiếp nhận bền vững đã thành công, hoặc khi hợp đồng API nói rõ trạng thái mà caller nhận được.

Trong Standard, cấu trúc project và file định nghĩa (ví dụ `workflow.json`, `connections.json` và application settings) khác gói triển khai Logic Apps Consumption, nhưng ý tưởng **trigger/actions/runAfter** vẫn giữ. Không chép một ARM workflow resource Consumption nguyên trạng vào Standard project rồi mong runtime tự hiểu hết connection references.

## 20. runAfter: điều khiển hành vi sau thành công hoặc thất bại

Mặc định action tiếp theo thường chạy sau khi action trước **Succeeded**. Khi lỗi xảy ra, các action downstream có thể bị **Skipped**. Dùng `runAfter` để định nghĩa điều kiện chạy sau trạng thái cụ thể.

Ví dụ JSON fragment:

```json
{
  "Log_failed_send": {
    "type": "Compose",
    "inputs": "Send failed or timed out; investigate",
    "runAfter": {
      "Send_message": ["Failed", "TimedOut"]
    }
  }
}
```

Đây là **đoạn trích thuộc tập actions**; nó giả định có action tên nội bộ `Send_message` ở cùng scope/level phù hợp. Tên action và statuses phải đúng runtime schema.

### Các trạng thái quan trọng

- **Succeeded:** action chạy thành công theo contract của chính nó.
- **Failed:** action không hoàn tất thành công.
- **TimedOut:** action vượt timeout được xác định.
- **Skipped:** action không chạy vì điều kiện/nhánh/trạng thái trước đó.
- Một số trường hợp có trạng thái runtime khác; kiểm tra run history thật trước khi xây logic phụ thuộc.

### Rủi ro khi dùng runAfter sai

Giả sử workflow muốn ghi log nếu bất kỳ bước nào lỗi nhưng action `Log_failed_send` chỉ chạy sau `Send_message=Failed`. Khi Send message **TimedOut**, log có thể bị Skipped và incident không được ghi nhận. Ngược lại, đặt cảnh báo chạy sau cả Succeeded có thể tạo thông báo lỗi giả.

Đừng xem một action cảnh báo **Succeeded** là bằng chứng toàn bộ workflow đã khôi phục. Cần quyết định **final run status** và nghiệp vụ đã hoàn thành hay chưa.

## 21. Scopes và mẫu Try–Catch–Finally

Trong workflow phức tạp, nhóm các bước vào **Scope** giúp tổ chức xử lý lỗi.

```text
Trigger
   |
   v
Scope: TRY
   |
   +-- Validate
   +-- Send message
   +-- Record acceptance
   |
   +---- Succeeded --------> Scope: FINALLY
   |
   +---- Failed/TimedOut --> Scope: CATCH
                                  |
                                  +-- Log sanitized error
                                  +-- Alert / compensate
                                  +-- Report failure
                                  |
                                  v
                             Scope: FINALLY
                                  |
                             Cleanup/metrics
```

Đây là **mẫu thiết kế**, không phải cú pháp tự động như try/catch trong Java. Trong Logic Apps, các scopes được nối bằng **Configure run after** và điều kiện trạng thái runtime.

### Cần xem trạng thái nested actions

Một Scope có thể được đánh giá theo những actions bên trong và cách chúng fail/skip. Nếu chỉ xem status của bước sau Scope, có thể bỏ lỡ nguyên nhân gốc.

Khi cần trích lỗi bên trong, Logic Apps có các function như `result('Scope_Try')` trong trường hợp hỗ trợ; cần xử lý output an toàn và **không đưa secret/payload nhạy cảm** vào log.

### Finally không phải luôn luôn chạy vô điều kiện

Nếu workflow bị dừng trước khi tạo run, bị terminate/cancel hoặc runtime không còn đủ điều kiện, không thể hứa một Finally action sẽ chạy trong mọi tình huống. Hãy xem finally theo runAfter **các trạng thái được hỗ trợ**, kèm monitoring độc lập cho workflow không kích hoạt hoặc run bị hủy.

## 22. Retry policy và timeout: lỗi tạm thời hay lỗi vĩnh viễn?

Nhiều HTTP/connector actions hỗ trợ **retry policy**, nhưng không có một quy tắc áp dụng cho mọi connector, status code hoặc error.

| Loại lỗi | Retry thường có ích? | Ghi chú |
|---|---|---|
| HTTP 429 rate limit | Có, với backoff và giới hạn. | Tôn trọng Retry-After nếu connector/runtime hỗ trợ. |
| HTTP 500/502/503/504 tạm thời | Có thể. | Cần kiểm tra side effect, timeout và idempotency. |
| Network timeout | Có thể. | Request trước đó **có thể đã được hệ thống đích xử lý**. |
| HTTP 400 schema không hợp lệ | Thường không. | Sửa payload hoặc contract; retry nguyên trạng vô ích. |
| HTTP 401 token hết hạn | Cần sửa auth/refresh. | Retry mù không thay credential sai. |
| HTTP 403 thiếu quyền | Thường không. | Cần RBAC/authorization, không tăng retry count. |
| Duplicate business operation | Không giải quyết bằng retry. | Dùng idempotency, dedupe và reconciliation. |

### Mẫu retry có kiểm soát

- Số lần thử **hữu hạn**.
- **Exponential backoff** hoặc retry policy được connector hỗ trợ.
- Delay/jitter để tránh nhiều workflow cùng retry một lúc.
- Timeout hợp lý cho action và toàn workflow.
- Idempotency key cho hệ thống đích có side effect.
- Cảnh báo khi retries vượt ngưỡng.

**Lỗi đặc biệt nguy hiểm:** action POST tạo đơn hàng bị timeout sau khi server đã ghi DB, workflow retry lần nữa tạo thêm đơn. Retry tự động không thể phân biệt “server chưa nhận” và “server nhận nhưng phản hồi thất lạc” nếu API không hỗ trợ idempotency hoặc query trạng thái.

## 23. Idempotency và tránh gửi trùng

Đối với tích hợp đơn hàng, một Request trigger có thể nhận **cùng payload nhiều lần** vì đối tác retry. Một trigger kiểu polling hoặc webhook cũng có thể xử lý lại cùng sự kiện theo semantics connector.

Thiết kế an toàn:

1. Producer gửi `eventId` hoặc `requestId` ổn định.
2. Logic App xác minh schema và lấy idempotency key.
3. Ghi marker vào hệ thống có **unique constraint/atomic conditional write** hoặc gọi API idempotent.
4. Chỉ thực hiện side effect một lần theo khóa đã thống nhất.
5. Với kết quả trùng hợp lệ, trả lại trạng thái đã tiếp nhận/xử lý thay vì gửi bản mới.
6. Ghi correlation ID để đối soát và tránh replay nhầm.

### Ví dụ

Hai HTTP requests đều chứa:

```json
{
  "requestId": "partner-x-2026-1042",
  "orderId": "ORD-1042",
  "amount": 250000
}
```

Không thể dựa vào một biến `alreadyProcessed` trong cùng run vì **hai runs độc lập có thể bắt đầu cùng lúc**. Cần nơi lưu trạng thái dùng chung với thao tác kiểm tra/ghi atomic, ví dụ SQL unique key, hệ thống API idempotency hoặc pattern inbox/outbox.

### Logic Apps không tự là distributed transaction coordinator

Nếu workflow làm ba hành động SQL → Service Bus → Email, action thứ ba Fail không khiến hai action trước tự rollback. Với yêu cầu nhất quán mạnh, cân nhắc **transactional outbox, saga/compensation và domain-specific reconciliation**, thay vì chỉ dùng runAfter để “undo”.

## 24. Xử lý dữ liệu lớn, pagination và connector throttling

Một connector “List rows” có thể trả một trang kết quả, không phải toàn bộ cơ sở dữ liệu. Các khả năng **pagination, threshold, batching** khác theo connector.

### Dấu hiệu thường gặp

- Ứng dụng biết có 50.000 records nhưng workflow chỉ thấy một phần.
- For each xử lý hàng nghìn items làm run kéo dài.
- Connector trả HTTP 429 hoặc action timeouts.
- Workflow ghi quá nhiều run history dẫn tới chi phí/log lớn.
- SaaS đích giới hạn số API calls mỗi phút.
- Payload vượt giới hạn của trigger/action hoặc connector.

### Hướng thiết kế

1. Xác minh pagination có được hỗ trợ và cấu hình đúng.
2. Đặt batch size phù hợp, không đọc toàn bộ lịch sử mỗi lần poll.
3. Dùng watermark hoặc change tracking từ nguồn khi được hỗ trợ.
4. Giới hạn loop concurrency và retry.
5. Nếu khối lượng rất lớn, tách workflow thành ingestion → queue/broker → workers.
6. Ghi dữ liệu dung lượng lớn vào Blob Storage, gửi tham chiếu an toàn thay vì nhúng body khổng lồ.
7. Tối ưu schema và chỉ chọn fields cần thiết.
8. Giám sát throttling cả **ở connector** lẫn **API đích**.

Không tăng timeout và số retries vô hạn để ép một workflow làm công việc ETL lớn; có thể cần Azure Data Factory, Functions, Batch hoặc một pipeline xử lý dữ liệu phù hợp hơn.

## 25. Security: identity, quyền và secret

Logic App có thể là một phần nhạy cảm của kiến trúc vì nó đọc/ghi dữ liệu qua nhiều hệ thống.

### Nên phân quyền theo từng kết nối

- Workflow đọc dữ liệu: chỉ cấp quyền **Read** cần thiết.
- Workflow gửi Service Bus message: **Azure Service Bus Data Sender**, không mặc định Data Owner.
- Workflow ghi Blob: quyền data plane tại account/container phù hợp.
- Workflow gọi API nội bộ: token/audience/scope được thiết kế cho API đó.
- Người sửa workflow: Azure RBAC tối thiểu và change approval.
- Người xem run history: giới hạn theo dữ liệu có thể hiển thị.

### Managed identity

Với connector/action hỗ trợ, dùng **system-assigned hoặc user-assigned managed identity** giúp giảm nhu cầu lưu client secret. Cần:

1. Enable identity trên Logic App/resource phù hợp.
2. Gán role data-plane đúng resource đích.
3. Chọn managed identity authentication trong connector nếu hỗ trợ.
4. Xác minh token audience/resource và network.
5. Kiểm thử kết nối **thật**; không coi “identity enabled” nghĩa là có quyền đọc mọi Azure service.

**Không phải mọi managed connector/action hỗ trợ managed identity theo cùng cách**. Khi một connector chỉ hỗ trợ OAuth user consent/API key, cần cơ chế credential management và rotation phù hợp.

### API connection và OAuth consent

Một connection tạo bởi tài khoản nhân viên có thể phụ thuộc quyền/consent của tài khoản đó; khi nhân viên nghỉ việc hoặc token bị revoke, workflow có thể ngừng. Với Production nên cân nhắc **service-owned identities/connections**, rõ owner và lịch kiểm tra credential/authorization.

### Secrets

- Tránh hard-code connection strings/SAS/API keys trong workflow definition hoặc deployment parameters.
- Dùng Azure Key Vault hoặc nền tảng secret management được hỗ trợ.
- Không ghi secret vào `Compose` để debug.
- Kiểm soát quyền xem trigger/action inputs/outputs.
- Rotate callback signatures và OAuth credentials theo runbook.
- Bảo vệ source repo, CI/CD variables, IaC state và ARM deployment history.
- Đánh giá data residency và retention của run history khi xử lý dữ liệu nhạy cảm.

## 26. Secure Inputs, Secure Outputs và dữ liệu trong run history

Logic Apps cung cấp cách đánh dấu **Secure Inputs** và **Secure Outputs** cho những actions/triggers được hỗ trợ, để hạn chế hiển thị dữ liệu nhạy cảm trong lịch sử thực thi.

Nhưng cần hiểu phạm vi:

- Đánh dấu một action không tự làm **mọi downstream action** trở nên bí mật.
- Nếu một bước sau dùng `Compose` để in token, dữ liệu có thể lại xuất hiện ở nơi khác.
- Connector/API đích có thể có logs riêng.
- Developer có quyền sửa workflow có thể tạo thêm bước tiết lộ secret nếu không có kiểm soát thay đổi.
- Một số tracing/diagnostic properties hoặc tracked properties cần kiểm tra để không đưa PII/secret vào telemetry.
- Che run history **không thay thế** encryption, RBAC, network security và dữ liệu tối thiểu.

### Quy trình kiểm tra

1. Xác định những fields nhạy cảm: password, tokens, thông tin khách hàng.
2. Bật secure inputs/outputs tại các điểm phù hợp.
3. Kiểm tra run history bằng dữ liệu giả lập.
4. Kiểm tra diagnostics/Application Insights/Log Analytics không chứa giá trị cấm.
5. Xem người có quyền đọc history hoặc resubmit runs.
6. Không dùng secret thật trong các bản chụp màn hình và tài liệu học tập.

**Quy tắc:** nếu một giá trị không cần để điều tra, đừng xuất nó ra logs chỉ để “dễ debug”.

## 27. API Management và Logic Apps: phân chia trách nhiệm

Logic Apps Request trigger có thể nhận HTTP request, nhưng với API công khai có nhiều đối tác, nên đánh giá **Azure API Management (APIM)** đứng trước workflow.

```text
External partner
       |
       v
API Management
  - OAuth/JWT validation
  - client quota / rate limit
  - API versioning / transformation
  - request/response policy
       |
       v
Logic Apps Request trigger
  - validate business payload
  - orchestrate connectors/actions
       |
       v
Azure Service Bus / SQL / Blob
```

APIM có thể giúp điều tiết request và áp dụng security policy; Logic Apps tập trung xử lý **workflow orchestration/integration**.

Không mặc định APIM sẽ xác thực được Logic App callback URL chỉ bằng việc biết endpoint. Cần cấu hình **backend authentication**, secret/managed identity và chính sách truy cập đúng theo sản phẩm/runtime hỗ trợ.

### Khi nên viết Azure Function thay vì action phức tạp?

Nếu logic cần thuật toán nặng, xử lý payload phức tạp, thư viện chuyên dụng, hiệu năng ổn định hoặc kiểm thử unit sâu, có thể tách sang **Azure Functions** hoặc API worker. Logic Apps gọi function như một action với contract rõ ràng. Không cần cố nhồi hàng nghìn biểu thức trong designer chỉ để tránh viết code.

## 28. Ví dụ thực tế: HTTP → Parse JSON → Service Bus → Response

**Yêu cầu nghiệp vụ:**

- Đối tác POST một order request.
- Workflow kiểm tra đủ `requestId`, `orderId` và `amount > 0`.
- Workflow gửi một command vào Service Bus queue `order-intake`.
- Chỉ sau khi broker **chấp nhận send**, trả HTTP 202 với correlation ID.
- Nếu schema sai, trả 400; nếu enqueue thất bại, trả lỗi phù hợp và gửi telemetry/cảnh báo.
- Không ghi token/PII nhạy cảm vào run history.

### Dữ liệu thử

```json
{
  "requestId": "partner-x-2026-1042",
  "orderId": "ORD-1042",
  "amount": 250000,
  "currency": "VND"
}
```

### Luồng thiết kế

```text
HTTP Request Trigger
         |
         v
Parse JSON / Validate payload
         |
         +---- Invalid --------> Response 400
         |
         v
Condition: amount > 0
         |
         +---- False ----------> Response 400
         |
         v
Compose normalized command
         |
         v
Send message: Service Bus queue order-intake
         |
         +---- Succeeded -----> Response 202
         |                         body: requestId, status=accepted
         |
         +---- Failed/Timeout -> Scope Error
                                   +-- sanitized diagnostics
                                   +-- alert (best effort)
                                   +-- Response 503/500 theo contract
```

### Tại sao 202?

HTTP 202 **Accepted** có thể nghĩa là yêu cầu đã được nhận để xử lý bất đồng bộ, chưa hoàn thành nghiệp vụ. Vì vậy:

- Không trả `paid=true` hay `orderCompleted=true` ngay sau Service Bus send.
- Cần endpoint/status store hoặc correlation ID để đối tác theo dõi kết quả.
- Nên lưu idempotency key để caller retry không tạo hai công việc cùng nghiệp vụ.
- Nếu action Send message timeout, broker **có thể đã nhận message**; không thể trả lỗi rồi mặc định chắc chắn chưa enqueue.

### Khi Response không chạy?

Request/Response trong Logic Apps chịu các giới hạn về thời gian phản hồi và runtime. Nếu workflow làm một tác vụ dài hoặc Response không được thực thi, caller có thể timeout/nhận phản hồi không như dự định. Do đó nên **trả phản hồi sau một bước tiếp nhận nhanh, bền vững**, còn xử lý dài hạn chạy qua queue/backend.

## 29. Thực hành qua Azure Portal: tạo workflow Consumption

Các bước khái quát cho một workflow Consumption trong subscription/lab đã được phê duyệt:

1. Mở [Azure Portal](https://portal.azure.com/) và xác minh tenant/subscription.
2. Tạo **Logic App (Consumption)** ở resource group lab, region phù hợp.
3. Mở **Logic App Designer**, chọn **When an HTTP request is received**.
4. Thêm sample JSON payload hoặc nhập JSON schema thủ công cho request.
5. Thêm **Parse JSON** nếu cần dynamic content và validation rõ ràng.
6. Thêm **Condition** kiểm tra `amount > 0`; nhánh False trả HTTP 400.
7. Nhánh True dùng **Compose** tạo command payload, thêm correlation/requestId.
8. Thêm **Service Bus Send message action**. Chọn đúng queue, tạo/chọn API connection với quyền Sender tối thiểu.
9. Sau khi send Succeeded, thêm **Response** trả HTTP 202 và body không nhạy cảm.
10. Tạo một nhánh xử lý lỗi sau send với **Configure run after** cho Failed/TimedOut.
11. Lưu workflow và xem callback URL theo cách bảo mật; không ghi URL có signature vào repo.
12. Gửi request giả lập qua công cụ thử được cấp phép.
13. Xem **Runs history**, kiểm tra từng trigger/action và các outputs đã được làm sạch.
14. Đối chiếu Service Bus queue/broker metrics hoặc receiver thử nghiệm để xác minh đã enqueue.
15. Bật monitoring và alerts; tắt/dọn tài nguyên lab khi không cần.

**Lưu ý:** tên action trong Designer và khả năng chọn managed identity cho Service Bus có thể khác theo connector/region/SKU. Nếu không thấy kiểu xác thực mong muốn, xem đặc tính connector đang chọn thay vì chuyển sang paste connection string vào workflow code.

### Test schema lỗi

Gửi:

```json
{
  "requestId": "partner-x-2026-1043",
  "orderId": "",
  "amount": -1,
  "currency": "VND"
}
```

Mong đợi workflow **không enqueue** dữ liệu này và trả phản hồi client error phù hợp, thay vì âm thầm gửi message lỗi cho worker.

### Test enqueue lỗi

Dùng **lab queue** và thay đổi có kiểm soát theo phê duyệt để mô phỏng Service Bus không khả dụng/thiếu quyền. Kiểm tra nhánh lỗi, không để action trả `202` khi chưa xác nhận send.

## 30. Standard workflow: tổ chức nhiều workflow trong một app

Một Logic App Standard resource có thể chứa nhiều workflows, ví dụ:

```text
Logic App Standard: la-integration-platform
  |
  +-- Workflow: ReceiveOrder     (stateful)
  |     Request → Validate → Service Bus
  |
  +-- Workflow: DailyReconcile   (stateful)
  |     Recurrence → SQL → Blob
  |
  +-- Workflow: QuickLookup      (stateless, nếu phù hợp)
        Request → HTTP → Response
```

Ở Standard, cấu hình có thể nằm trong project gồm:

- `workflow.json` cho định nghĩa mỗi workflow.
- `connections.json` cho connection references/config theo loại connector.
- App settings và những file cấu hình runtime được hỗ trợ.
- Deployment pipeline/IaC cho Logic App Standard hosting và các tài nguyên kết nối.

### Chọn stateful hay stateless

| Tiêu chí | Stateful | Stateless |
|---|---|---|
| Cần theo dõi từng bước dài hạn | Thường phù hợp hơn. | Giới hạn khác; cần kiểm tra observability. |
| Workflow xử lý nhanh, ít chờ | Có thể dùng, nhưng có overhead lưu trạng thái. | Có thể phù hợp nếu giới hạn runtime đáp ứng. |
| Long-running orchestration | Phù hợp khi hỗ trợ. | Thường không phù hợp với run dài. |
| Replay và debugging | Có thêm bề mặt history/diagnostics. | Cần thiết kế logging/monitoring khác. |
| Chi phí/performance | Theo hosting/operations. | Theo hosting/operations, không tự miễn phí. |

Trong Standard, **managed connectors và built-in service-provider connectors có thể có cách tham chiếu connections khác nhau**. Không sửa `connections.json` bằng tay trong Production khi chưa biết schema và secrets management; ưu tiên dùng designer/CI pipeline được kiểm thử.

## 31. Azure CLI: đọc tài nguyên Logic App (read-only)

Trong Logic Apps Consumption, Azure CLI hỗ trợ thao tác quản lý workflow theo resource tương ứng. Các lệnh dưới đây chủ yếu là **read-only**:

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az logic workflow list \
  --resource-group "<RESOURCE_GROUP>" \
  --output table

az logic workflow show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<CONSUMPTION_LOGIC_APP_NAME>" \
  --query "{Name:name,State:state,Location:location}" \
  --output json
```

Cần kiểm tra phiên bản Azure CLI/extension và quyền ARM của tài khoản. Trường output có thể khác theo API version. **Đừng in toàn bộ workflow definition/parameters vào terminal được thu log** nếu nó có chứa credential hoặc URLs có signature.

### Logic Apps Standard

Standard Logic App là tài nguyên hosting dựa trên mô hình App Service/Functions workflow app. Không mặc định lệnh `az logic workflow show` của Consumption sẽ liệt kê từng Standard workflow.

Có thể dùng ARM resource query ở cấp hosting app:

```bash
az resource show \
  --resource-group "<RESOURCE_GROUP>" \
  --resource-type "Microsoft.Web/sites" \
  --name "<STANDARD_LOGIC_APP_NAME>" \
  --query "{Name:name,Kind:kind,Location:location}" \
  --output json
```

Lệnh trên giúp kiểm tra **host resource**, không chứng minh từng Standard workflow đã chạy đúng hoặc API connections khỏe. Để kiểm tra workflow runtime, dùng Portal, công cụ Standard phù hợp và diagnostic logs.

## 32. Run history, trigger history và action details

Khi workflow không hoạt động như kỳ vọng, không chỉ xem trạng thái cuối.

### Trigger history

- Trigger có chạy/được kiểm tra không?
- Có phát hiện event/request không?
- Trigger conditions hoặc filter có loại bỏ payload không?
- Polling có trả kết quả 0 items hay lỗi auth?
- Có concurrency/rate limit/connector throttling không?
- Endpoint callback có bị block bởi mạng hoặc caller không gửi?

### Run history

- Run bắt đầu lúc nào, với correlation ID nào?
- Action nào đầu tiên Fail/TimedOut?
- Những action nào bị Skipped vì runAfter?
- Input/output đã được Secure Inputs/Outputs chưa?
- Có retry hoặc action nào thực sự đã tạo side effect trước khi lỗi?
- Branch khác có hoàn thành không?
- Có một step lâu bất thường, ví dụ API connector chậm?

### Những giới hạn cần biết

- Khi workflow bị disable hoặc trigger chưa bao giờ nhận request, có thể **không có run** để xem.
- Stateful và stateless có cách lưu/truy vấn history khác nhau.
- Retention của run history/diagnostics có giới hạn theo SKU/cấu hình.
- Run details có thể chứa payload nhạy cảm nếu không được bảo vệ.
- Resubmit một run có thể **gửi lại action đã từng thành công**, dẫn đến duplicate business side effects nếu thiếu idempotency.

**Resubmit là một thao tác nghiệp vụ có rủi ro**, không phải nút “sửa lỗi” vô hại cho bất kỳ run thất bại nào.

## 33. Azure Monitor, Log Analytics và Application Insights

Logic Apps có thể kết hợp Azure Monitor metrics, diagnostic settings, Log Analytics và Application Insights theo loại hosting/cấu hình được hỗ trợ.

| Nguồn | Dùng để |
|---|---|
| Portal trigger/run history | Điều tra một lần kích hoạt/chạy cụ thể. |
| Azure Monitor metrics | Số runs/trigger successes/failures, thời gian chạy hoặc tín hiệu tương tự theo SKU. |
| Diagnostic settings → Log Analytics | Lưu và truy vấn workflow runtime/resource logs theo retention. |
| Application Insights | Tìm telemetry, exceptions, dependencies và correlation khi workflow Standard/integration hỗ trợ. |
| Azure Activity Log | Theo dõi thay đổi resource/control plane, ví dụ chỉnh workflow, policy, role assignment. |
| Connector/API destination logs | Xác minh API đích có nhận request/message, phục vụ đối soát. |

**Không mặc định Azure Activity Log chứa đầy đủ payload và từng action execution**. Cần cấu hình nguồn diagnostics/runtime logs phù hợp.

### KQL khởi đầu

Trong workspace có dữ liệu diagnostic logs của Logic Apps, một truy vấn tham khảo:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(2h)
| where ResourceProvider =~ "MICROSOFT.LOGIC"
| project TimeGenerated, Resource, Category, OperationName
| order by TimeGenerated desc
```

Tên bảng/cột có thể khác theo cấu hình **resource-specific tables**, Logic Apps Standard hosting hoặc phiên bản diagnostics. Nếu truy vấn rỗng, phải kiểm tra **destination, table schema, ingestion và retention** trước khi kết luận không có run.

### Thiết kế correlation

Gán `requestId`/`correlationId` vào payload sạch:

```text
Partner requestId = partner-x-2026-1042
        |
Logic App run ID + correlationId
        |
Service Bus message ID = partner-x-2026-1042
        |
Worker log + DB orderId = ORD-1042
```

Không dùng một `guid()` mới ở mỗi action làm mất khả năng liên hệ các bước của **cùng** yêu cầu. Nên chọn correlation ID sớm và truyền xuyên suốt theo contract.

## 34. Cảnh báo và SLO cho workflow tích hợp

Một workflow có thể chạy **Succeeded** nhưng nghiệp vụ vẫn sai nếu mapping thiếu trường hoặc message được gửi sai queue. Vì vậy cảnh báo phải kết hợp kỹ thuật và nghiệp vụ.

| Tín hiệu | Mục tiêu | Hướng xử lý |
|---|---|---|
| Trigger không kích hoạt trong giờ kỳ vọng | Phát hiện webhook/polling/connection chết. | Xem trigger history, upstream và auth. |
| Run failure rate tăng | Phát hiện lỗi workflow/connector. | Xem action đầu tiên Fail/TimedOut. |
| Run duration vượt ngưỡng | Phát hiện latency hoặc dependency nghẽn. | Phân tích HTTP/DB/queue steps và retries. |
| HTTP 429 từ connector/API | Nhận biết throttling. | Giảm concurrency, backoff, capacity. |
| Response timeout | Caller không nhận kết quả đúng hạn. | Tách xử lý dài qua queue. |
| Service Bus enqueue success nhưng consumer backlog tăng | Downstream chưa xử lý kịp. | Xem queue metrics/worker, không đổ lỗi chỉ cho Logic App. |
| Payload validation errors tăng | Đối tác thay schema hoặc gửi dữ liệu lỗi. | Contract tests, cảnh báo theo client. |
| Managed connection unauthenticated | OAuth/managed identity/secret lỗi. | Kiểm tra connection health, role/consent. |
| Chi phí action tăng bất thường | Polling/loops/retries hoặc traffic tăng. | Phân tích executions, trigger frequency, diagnostics. |

### SLO ví dụ

- 99,9% requests hợp lệ được **tiếp nhận bền vững** trong khoảng thời gian đã thống nhất.
- 99,9% commands được worker xử lý thành công trước deadline riêng.
- Tỷ lệ payload sai được trả 4xx rõ ràng, không mất dấu vết.
- Khi Service Bus không sẵn sàng, workflow không báo `accepted` sai.
- Tất cả incident quan trọng có correlation ID để đối soát.

Hai SLO đầu **khác nhau**: một cho Logic App intake, một cho backend xử lý bất đồng bộ.

## 35. Chi phí: action executions, connectors và hosting

Tổng chi phí Logic Apps có thể gồm:

- Logic App hosting/execution model.
- Trigger/action executions, bao gồm một số polling, vòng lặp và retries theo billing policy tương ứng.
- Managed connector calls, nếu có.
- Standard hosting plan/capacity/runtime.
- Azure Service Bus, SQL, Storage, Functions và các hệ thống đích.
- API Management, VNet/private endpoints, NAT/firewall.
- Azure Monitor Log Analytics/Application Insights ingestion/retention.
- Tài nguyên test/staging và công sức vận hành.

### Ví dụ ước lượng hoạt động

Giả sử mỗi ngày có 10.000 requests hợp lệ:

- Mỗi run dùng 1 Request trigger.
- 1 Parse JSON action.
- 1 Condition.
- 1 Compose.
- 1 Service Bus Send action.
- 1 Response.
- 5% requests cần retry một action thêm một lần.

Tổng số lần action thực thi **chỉ để lập capacity/cost model** sẽ khác với `10.000 × 5` nếu các nhánh không cùng chạy, loops, retries và billing metering thay đổi. Không biến phép đếm lý thuyết thành giá tiền mà chưa kiểm tra **pricing meter của SKU và connector** đang dùng.

### Tối ưu có cơ sở

1. Chọn trigger phù hợp: webhook thay polling khi tốt hơn về latency/quota.
2. Dùng batch cho dữ liệu lớn khi connector hỗ trợ.
3. Tránh For each gọi từng item nếu API có bulk endpoint.
4. Giới hạn retries, timeout và concurrency.
5. Loại bỏ log debug chứa payload dài không cần thiết.
6. Đánh giá built-in vs managed connector theo performance, security và phí thực tế.
7. Chọn Consumption hoặc Standard theo tần suất, thời gian chạy, network, isolation và hosting utilization.
8. Giám sát costs theo tags, budget và cost attribution.
9. Thử tải thật trước khi quyết định scale.
10. Không hy sinh an toàn nghiệp vụ chỉ để giảm số actions.

## 36. Troubleshooting: trigger/action/connector không chạy

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
|---|---|---|
| Không có run | Trigger chưa fire, workflow disabled, trigger conditions không khớp. | Workflow state, trigger history, callback/polling config. |
| Trigger polling không thấy record | Interval, watermark, filter, pagination hoặc nguồn API chưa trả dữ liệu. | Trigger configuration và nguồn dữ liệu. |
| Webhook không đến | Subscription/callback expired, signature/auth, network. | Source event logs, registration và endpoint reachability. |
| Request trả 401/403 | Caller không được phép hoặc callback URL/signature sai. | Auth policy, APIM/Entra/SAS và permissions. |
| Parse JSON Failed | Sai schema, field vắng, mismatch kiểu hoặc payload malformed. | Input đã làm sạch và JSON schema. |
| Action bị Skipped | runAfter không khớp hoặc Condition nhánh khác. | Trạng thái action trước đó và runAfter. |
| Service Bus Send 403 | Connection principal thiếu Data Sender hoặc scope sai. | Identity, role, namespace/queue. |
| Service Bus Send timeout | Network, broker, connector throttling hoặc outage. | DNS/route, Azure Monitor, SDK/connector error. |
| OAuth connection invalid | Token expired/revoked, user consent, tenant mismatch. | API connection health, owner và consent. |
| Loop chỉ xử lý một số item | Pagination, filter, branch, timeout, iteration limits. | Inputs counts, connector paging, loop status. |
| Run Succeeded nhưng dữ liệu không xuất hiện | Nhầm hệ thống đích, async backend pending, mapping sai. | Destination ID, correlation và backend logs. |
| Trả HTTP 202 dù Send thất bại | Response nối sai runAfter/nhánh lỗi. | Run graph, action statuses, response path. |
| Duplicate orders sau resubmit | Retry/non-idempotent API, replay nhiều lần. | RequestId, outbox/inbox và DB constraints. |
| Standard workflow không có history mong đợi | Stateless/stateful khác nhau hoặc diagnostics chưa cấu hình. | Workflow type, monitoring settings. |
| Chạy chậm hoặc quá phí | Excess retries, polls, loops, high concurrency. | Billing, metrics, run durations và logs. |

### Cây quyết định

```text
Không có dữ liệu downstream?
        |
        +-- Có trigger history?
        |      |
        |      +-- Không → cấu hình trigger / source event / polling
        |      |
        |      +-- Có
        |          |
        |          +-- Có workflow run?
        |          |      |
        |          |      +-- Không → điều kiện trigger, schedule, throttle
        |          |      |
        |          |      +-- Có
        |          |          |
        |          |          +-- Validate/Parse failed → schema/contract
        |          |          |
        |          |          +-- Connector failed → auth/network/quota
        |          |          |
        |          |          +-- Send succeeded → kiểm tra queue/worker
        |          |
        |          +-- Khả năng source callback chưa tới?
        |
        +-- Có duplicate data?
               |
               +-- Retry/resubmit/parallel runs
               +-- Thiếu idempotency/dedupe
```

Không sửa ba thứ cùng lúc (schema, connection, retry) khi chưa khoanh vùng; một thay đổi nhỏ theo run history thường giúp xác định nguyên nhân rõ hơn.

## 37. Tình huống A: HTTP trigger chạy nhưng queue không có message

**Hiện tượng:** đối tác POST đơn hàng, Logic App có run, HTTP response 202 nhưng worker không thấy message.

**Điều tra:**

1. Xác định requestId và thời điểm từ client.
2. Xem run history, tìm action Service Bus Send.
3. Kiểm tra nó Succeeded, Failed hay Skipped.
4. Nếu Succeeded, kiểm tra **đúng namespace/queue** và Service Bus metrics; message có thể đã được worker nhận/complete nhanh.
5. Nếu Failed với 403, kiểm tra Data Sender và connection identity.
6. Nếu TimedOut, xác nhận có khả năng broker đã nhận, rồi đối soát bằng requestId trước khi retry.
7. Nếu Skipped, kiểm tra Condition/runAfter.
8. Nếu queue có message nhưng worker không xử lý, chuyển điều tra downstream.

**Nguyên nhân thường gặp:** Response được cấu hình chạy sau Validate thay vì **sau Send Succeeded**. Logic App báo accepted quá sớm.

**Khắc phục:** đưa Response vào nhánh đúng, bổ sung failure response/alert và idempotency. Kiểm thử cả đường gửi thành công lẫn mô phỏng lỗi.

## 38. Tình huống B: Polling lấy trùng hoặc bỏ sót dữ liệu

**Hiện tượng:** workflow Recurrence mỗi 10 phút đọc bảng `Orders` và gửi email. Sau một lần timeout, cùng đơn được gửi hai email; đồng thời vài đơn khác không có trong output.

**Điều tra:**

1. Kiểm tra workflow có các run chạy chồng nhau không.
2. Xem filter theo thời gian và time zone; có dùng `updatedAt > lastRunTime` thiếu watermark bền vững không?
3. Kiểm tra pagination/Top count của connector.
4. Xem action email đã thành công trước khi workflow retry/resubmit?
5. Xem có idempotency key theo orderId + loại thông báo không.
6. So nguồn dữ liệu với output để biết chính xác item nào thiếu.

**Khắc phục:** dùng watermark bền vững, query có thứ tự/cửa sổ chồng hợp lý, pagination đúng, dedupe key và concurrency policy an toàn. Email không nên được gửi chỉ theo một biến `lastRunTime` nằm trong run memory.

## 39. Tình huống C: OAuth connection hết hiệu lực

**Hiện tượng:** sau khi đổi nhân sự phụ trách, workflow gửi email qua một managed connector liên tục Failed với lỗi unauthorized.

**Điều tra:**

1. Xem API connection reference và loại authentication.
2. Xác định connection có phụ thuộc OAuth consent/token của tài khoản nhân viên cũ không.
3. Kiểm tra tenant, policy, licensing và quyền service mailbox.
4. Đối chiếu thời điểm lỗi bắt đầu với thay đổi user/credential/policy.
5. Không paste access token hay refresh token vào ticket để nhờ hỗ trợ.

**Khắc phục:** tạo/ủy quyền lại connection dưới ownership được tổ chức quản lý; dùng managed identity/service-owned integration khi connector cho phép; cập nhật monitoring credential expiry/revocation và test workflow.

**Bài học:** “tạo connection xong” chưa phải hết việc. Connection có vòng đời, owner và rủi ro phụ thuộc con người.

## 40. Bài thực hành: triển khai Logic App nhận yêu cầu đơn hàng

**Bối cảnh lab:** một đối tác giả lập gửi yêu cầu đơn hàng; Logic App cần validate và gửi tới Service Bus queue. Không kết nối vào hệ thống Production hoặc gửi email thật.

| Thành phần | Giá trị minh họa |
|---|---|
| Resource group | `rg-integration-lab` |
| Logic App | `la-orders-intake-lab` |
| Workflow | `ReceiveOrder` |
| Trigger | `When an HTTP request is received` |
| Queue | `order-intake` |
| Namespace | `sb-orders-lab-unique` |
| Connection | Service Bus connection với quyền Sender |
| Payload | `requestId`, `orderId`, `amount`, `currency` |
| Success response | HTTP 202 và correlation ID |
| Invalid response | HTTP 400 |
| Enqueue failure | HTTP lỗi theo API contract + alert |
| Observability | Runs history, sanitized logs, queue metrics |

### Nhiệm vụ

1. Vẽ sơ đồ trigger → Parse JSON → Condition → Compose → Send message → Response.
2. Nêu khác nhau giữa connector và connection.
3. Chọn Consumption hoặc Standard cho lab và giải thích lý do.
4. Tạo resource trong môi trường lab được phê duyệt.
5. Khai báo Request JSON schema có trường bắt buộc.
6. Dùng expressions lấy `orderId`/`requestId`.
7. Dùng Condition chặn `amount <= 0`.
8. Tạo Service Bus connection với managed identity nếu connector/hosting hỗ trợ; nếu không, mô tả phương án auth an toàn được phê duyệt.
9. Thiết kế Response 202 **chỉ sau Send Succeeded**.
10. Thêm error branch với Configure run after Failed/TimedOut.
11. Bật Secure Inputs/Outputs nếu có dữ liệu nhạy cảm.
12. Gửi request lab hợp lệ và xem output queue.
13. Gửi request sai schema và chứng minh **không enqueue**.
14. Mô phỏng Service Bus không khả dụng và xem response/alert.
15. Dùng requestId để thử gửi lại cùng request; nêu cách ngăn side effect trùng.
16. Kiểm tra run history/diagnostic logs và permission của người xem.
17. Dự toán tác động khi volume tăng từ 100 lên 10.000 requests/ngày.
18. Dọn lab theo quy trình, không xóa queue/connection dùng chung.

### Dữ liệu test

**Yêu cầu hợp lệ:**

```json
{
  "requestId": "partner-x-lab-1042",
  "orderId": "ORD-LAB-1042",
  "amount": 250000,
  "currency": "VND"
}
```

**Yêu cầu sai:**

```json
{
  "requestId": "partner-x-lab-1043",
  "orderId": "",
  "amount": -100,
  "currency": "VND"
}
```

### Lời giải định hướng

- **Trigger:** HTTP Request.
- **Connector:** Service Bus để gửi command; authentication connection tách biệt.
- **Action mapping:** Parse JSON + Condition bảo đảm schema/amount, Compose chuẩn hóa event ID.
- **Success path:** Send Succeeded → Response 202. HTTP response không nói “đã thanh toán”.
- **Failure path:** Invalid → 400; Send Failed/TimedOut → error response theo API contract, sanitized alert và reconciliation.
- **Idempotency:** hệ thống lưu requestId/business operation key bền vững; không chỉ dùng biến trong một run.
- **Monitoring:** trace requestId xuyên qua Logic App → Service Bus → worker.
- **Security:** không lưu callback URL signature hoặc connection string trong Git/logs.
- **Validation:** mỗi thử nghiệm có expected result, run history và queue evidence.

**Tiêu chí nghiệm thu:** workflow không chấp nhận payload sai, không báo accepted trước khi enqueue xác nhận, người xem không thể lấy secret qua logs, có hướng xử lý khi retry/resubmit gây duplicate và có dấu vết correlation giữa hai hệ thống.

## 41. Tự kiểm tra kiến thức

**Câu 1.** Logic Apps connector khác connection như thế nào?

**Đáp án:** Connector cung cấp chức năng trigger/action cho dịch vụ; connection xác định cách kết nối và xác thực tới resource cụ thể.

**Câu 2.** Trigger khác action ở đâu?

**Đáp án:** Trigger khởi đầu workflow run khi điều kiện/sự kiện phù hợp; action là bước được thực thi sau trigger hoặc theo các bước trước.

**Câu 3.** Polling trigger và webhook trigger có cùng cách nhận event không?

**Đáp án:** Không. Polling kiểm tra nguồn theo chu kỳ; webhook/push dùng callback từ nguồn khi có sự kiện theo cơ chế connector.

**Câu 4.** Một HTTP Request trigger có schema JSON hợp lệ thì caller tự được phép gọi không?

**Đáp án:** Không. Schema kiểm tra cấu trúc dữ liệu, còn authorization cần chính sách riêng như Entra/APIM/callback signature khi được hỗ trợ.

**Câu 5.** Logic Apps Standard có thể chứa nhiều workflows trong một resource không?

**Đáp án:** Có. Standard hỗ trợ nhiều workflows và có các mô hình stateful/stateless theo khả năng runtime; Consumption thường có một workflow trên một Logic App resource.

**Câu 6.** Managed connector và built-in service-provider connector có luôn dùng cùng connection format không?

**Đáp án:** Không. Chúng có runtime, connection config, giới hạn và phí có thể khác, đặc biệt trong Standard.

**Câu 7.** `Compose` thường dùng để làm gì?

**Đáp án:** Tạo/biến đổi một giá trị hoặc payload từ trigger/action outputs để dùng ở bước sau.

**Câu 8.** Vì sao Parse JSON có thể Failed dù HTTP body là JSON hợp lệ?

**Đáp án:** Dữ liệu có thể không phù hợp JSON schema, thiếu required fields, sai kiểu hoặc bị giới hạn bởi contract.

**Câu 9.** `triggerBody()?['orderId']` khác `triggerBody()['orderId']` về ý nghĩa gì?

**Đáp án:** Toán tử null-safe `?` giúp truy cập linh hoạt khi thuộc tính thiếu/null theo cách runtime hỗ trợ; vẫn cần validation chặt cho trường bắt buộc.

**Câu 10.** Vì sao action tiếp theo có thể Skipped sau khi action trước Failed?

**Đáp án:** runAfter mặc định thường chỉ cho chạy sau Succeeded; action cần cấu hình runAfter cho những trạng thái muốn xử lý.

**Câu 11.** Nếu cần cảnh báo khi action Failed **hoặc TimedOut**, có nên chỉ chọn Failed trong Configure run after không?

**Đáp án:** Không. Chọn cả Failed và TimedOut khi logic cần xử lý cả hai tình huống.

**Câu 12.** HTTP 429 nên được xử lý thế nào?

**Đáp án:** Retry/backoff có giới hạn, tôn trọng rate limit/Retry-After nếu được hỗ trợ, giảm concurrency hoặc điều chỉnh capacity; không spam retries vô hạn.

**Câu 13.** Tại sao retry một HTTP POST bị timeout có nguy cơ tạo đơn trùng?

**Đáp án:** Server có thể đã commit trước khi client timeout; retry lần nữa tạo side effect nếu API thiếu idempotency.

**Câu 14.** Có thể dùng một variable trong Logic App run để ngăn hai requests giống nhau chạy đồng thời không?

**Đáp án:** Không đủ. Hai runs có trạng thái riêng; cần idempotency key và lưu trạng thái bền vững/atomic ở hệ thống dùng chung.

**Câu 15.** Service Bus Send message Succeeded có chứng minh worker đã xử lý đơn không?

**Đáp án:** Không. Nó chỉ xác nhận send tới broker thành công theo connector; kết quả downstream phải theo dõi riêng.

**Câu 16.** Response 202 nên đặt ở đâu trong luồng nhận đơn hàng?

**Đáp án:** Sau khi bước tiếp nhận bền vững (ví dụ Service Bus Send) thành công, kèm correlation ID và hợp đồng trạng thái accepted rõ ràng.

**Câu 17.** Managed identity được bật cho Logic App có tự cho phép đọc SQL/Service Bus/Blob không?

**Đáp án:** Không. Identity phải được gán quyền data-plane phù hợp, connector hỗ trợ cách auth đó và network phải thông.

**Câu 18.** Secure Inputs/Outputs trên một action có bảo đảm mọi downstream action không lộ secret không?

**Đáp án:** Không. Cần bảo vệ cả các bước tiếp theo, diagnostics, tracked properties và quyền đọc run history.

**Câu 19.** Tại sao không nên tăng For each concurrency vô hạn?

**Đáp án:** Dễ gây race conditions, API throttling, retry storms, sai thứ tự xử lý và tăng chi phí.

**Câu 20.** Một Logic App run đã Failed, nhấn Resubmit có an toàn với mọi workflow không?

**Đáp án:** Không. Một số actions có thể đã tạo side effect trước khi run thất bại; resubmit có nguy cơ ghi/gửi trùng nếu thiếu idempotency.

**Câu 21.** Azure Activity Log có thay thế workflow run history không?

**Đáp án:** Không. Activity Log chủ yếu phản ánh thay đổi control plane; run history và runtime diagnostics cần cho trigger/actions.

**Câu 22.** Vì sao một workflow có run history Succeeded nhưng nghiệp vụ vẫn sai?

**Đáp án:** Action có thể thực thi đúng kỹ thuật nhưng mapping sai, gửi nhầm queue, workflow chỉ enqueue chứ không theo dõi kết quả hoặc payload bị lọc không đúng.

**Câu 23.** Stateless Standard workflow có phù hợp với quy trình chờ phê duyệt nhiều tuần không?

**Đáp án:** Thường không; cần xét thời hạn chạy, khả năng lưu trạng thái và lựa chọn stateful phù hợp.

**Câu 24.** Vì sao lỗi “không có run” phải kiểm tra trigger history/source trước khi xem run details?

**Đáp án:** Khi trigger chưa fire hoặc workflow không tạo run, không có action history để xem; nguồn lỗi ở tầng kích hoạt.

**Câu 25.** Khi nào nên dùng Azure Function thay vì nhồi thêm hàng chục biểu thức trong workflow?

**Đáp án:** Khi logic cần thư viện/thuật toán phức tạp, hiệu năng và unit tests sâu; Logic Apps có thể điều phối Function qua contract rõ ràng.

**Tóm lại:** Trong Azure Logic Apps, **trigger** quyết định *khi nào workflow bắt đầu*, **connector** quyết định *có thể nói chuyện với dịch vụ nào và bằng cơ chế nào*, còn **action** quyết định *từng bước làm gì và xử lý kết quả ra sao*. Một workflow Production đáng tin cậy phải có **connection/identity đúng quyền, validation, runAfter, retry giới hạn, idempotency, quan sát đầy đủ, bảo vệ dữ liệu nhạy cảm và kiểm soát chi phí**. Đừng chỉ hỏi “workflow đã chạy thành công chưa”; hãy hỏi thêm **“dữ liệu đã đến đúng hệ thống, nghiệp vụ đã hoàn tất và có thể khôi phục an toàn khi lỗi chưa?”**.
