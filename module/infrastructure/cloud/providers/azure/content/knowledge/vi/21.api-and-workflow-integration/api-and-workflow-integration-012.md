# Lựa chọn API Management, Logic Apps và Functions theo tình huống

Một kiến trúc tích hợp trên Microsoft Azure thường phải giải quyết ba câu hỏi khác nhau: **ai được gọi API**, **quy trình nghiệp vụ đi qua những bước nào**, và **mã chương trình nào thực hiện xử lý cụ thể**. Dùng cùng một dịch vụ để trả lời cả ba câu hỏi có thể tạo ra hệ thống khó bảo trì, tốn kém hoặc thiếu bảo mật.

Ba dịch vụ rất dễ bị nhầm lẫn:

- **Azure API Management (APIM):** tạo lớp **API gateway và quản trị API** trước các backend, giúp định tuyến, xác thực/ủy quyền ở gateway, áp chính sách, giới hạn lưu lượng, quan sát và công bố sản phẩm API.
- **Azure Logic Apps:** xây dựng **workflow tích hợp và điều phối** dựa trên trigger, actions, connectors, điều kiện, vòng lặp và trạng thái thực thi; phù hợp liên kết hệ thống SaaS, dữ liệu và quy trình có nhiều bước.
- **Azure Functions:** chạy **mã xử lý theo sự kiện hoặc HTTP** dưới mô hình serverless; phù hợp logic tùy chỉnh, tính toán, chuyển đổi dữ liệu, webhook handlers và những tác vụ có trigger.

Bài học này thuộc chương **API và tích hợp quy trình** của module **CLOUD_PROVIDERS_AZURE**, trong lộ trình khám phá subscription, resource group, Microsoft Entra ID, mạng ảo, compute, lưu trữ và dữ liệu. Mục tiêu là biết **chọn đúng dịch vụ hoặc kết hợp chúng**, rồi thiết kế triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure.

> **Quy tắc nhớ nhanh:** **APIM quản trị cửa vào**, **Logic Apps điều phối các bước**, **Functions thực thi mã**. Đây là phép so sánh vai trò, không phải giới hạn cứng: từng dịch vụ có thêm các chức năng khác, nhưng không nên biến một dịch vụ thành bản thay thế thiếu kiểm soát cho hai dịch vụ còn lại.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Giải thích thành phần của APIM: gateway, API, operation, backend, product, subscription, policy và các khía cạnh developer experience.
2. Phân biệt Logic Apps **Consumption** và **Standard**, trigger, connector, actions, stateful/stateless workflow và các lựa chọn retry.
3. Hiểu Azure Functions trigger/bindings, hosting plans, timeout, concurrency, cold start và khi nào cần **Durable Functions**.
4. Đánh giá tình huống theo API traffic, latency, mức độ tích hợp SaaS, độ phức tạp logic, trạng thái dài hạn, bảo mật, vận hành và chi phí.
5. Chọn APIM, Logic Apps, Functions, kết hợp hai/ba dịch vụ, hoặc dịch vụ thay thế như App Service, Azure Container Apps và Service Bus.
6. Thiết kế API đồng bộ so với tác vụ bất đồng bộ trả HTTP **202 Accepted**, có tracking ID và idempotency.
7. Xây dựng một Azure Function HTTP Java mẫu, một Logic Apps workflow minh họa và một APIM policy xác thực JWT/rate limiting.
8. Lập sơ đồ xác thực người dùng, managed identity giữa các dịch vụ, kết nối riêng và luồng telemetry.
9. Xử lý retry, timeout, duplicate delivery, thất bại một phần và compensation mà không hứa hẹn exactly-once sai.
10. Thiết kế CI/CD, versioning, monitoring, runbook và phân tích tổng chi phí end-to-end.

## 2. Bức tranh lớn: ba lớp trách nhiệm

~~~mermaid
flowchart LR
    CLIENT["Mobile, website, đối tác B2B"] --> APIM["Azure API Management<br/>gateway + policy"]
    APIM --> API["Azure Functions / App Service<br/>Business API"]
    API --> MSG["Service Bus / Event Grid"]
    MSG --> FLOW["Logic Apps<br/>workflow + connectors"]
    FLOW --> CRM["CRM / ERP / Microsoft 365"]
    FLOW --> FUNC["Azure Functions<br/>custom transformation"]
    API --> DB["Azure SQL / Cosmos DB"]
    FLOW --> DB
    ID["Microsoft Entra ID"] -. "Danh tính, tokens" .-> APIM
    ID -. "Managed identity" .-> API
    ID -. "Connections" .-> FLOW
    OBS["Azure Monitor / App Insights"] -. "Logs, traces, metrics" .-> APIM
    OBS -. "Telemetry" .-> API
    OBS -. "Run history" .-> FLOW
~~~

Kiến trúc này không bắt buộc phải có đủ ba sản phẩm. Nếu ứng dụng chỉ cần xử lý một file Blob khi được upload, **Function với Blob/Event Grid trigger** có thể đủ. Nếu có nhiều hệ thống SaaS và quy trình phê duyệt kéo dài, **Logic Apps** có thể chủ động điều phối mà không cần APIM. Nếu một backend Java đã tồn tại và chỉ cần quản trị API đối tác, **APIM có thể đứng trước backend hiện hữu**; không nhất thiết viết lại API sang Functions.

### 2.1. Phân biệt lớp gateway, orchestration và compute

| Khía cạnh | API Management | Logic Apps | Azure Functions |
|---|---|---|---|
| Trách nhiệm chính | Cổng API và governance | Workflow/integration orchestration | Chạy custom code |
| Điểm kích hoạt thường gặp | HTTP request đi qua gateway | HTTP, recurrence, connector event, message | HTTP, timer, queue, Blob, Event Hubs và các triggers hỗ trợ |
| Xử lý | Policies, routing, request/response transformation giới hạn | Actions, conditions, loops, connectors | Code C#, Java, JavaScript/TypeScript, Python, PowerShell... theo runtime |
| Trạng thái nghiệp vụ dài hạn | Không phải nơi giữ workflow | Stateful workflows phù hợp | Functions thường nên stateless; Durable Functions cho orchestration stateful |
| Tích hợp SaaS | Proxy API; không phải thư viện connector workflow | Thế mạnh lớn với managed/built-in connectors | Dùng SDK/HTTP client hoặc bindings hỗ trợ |
| Quản trị API bên ngoài | Thế mạnh chính | Có HTTP trigger nhưng không thay gateway đầy đủ | Có HTTP trigger nhưng không thay gateway đầy đủ |
| Logic nghiệp vụ phức tạp | Không nên đưa toàn bộ vào policy | Phù hợp orchestration; custom compute nên gọi code | Phù hợp logic code và thuật toán |
| Đơn vị scale/chi phí | Gateway/tier/requests theo mô hình | Workflow hosting, triggers/actions/connectors theo plan | Executions, compute/memory, instances theo hosting plan |
| Ví dụ | JWT validation, quota, versioning | Khi đơn hàng được duyệt, cập nhật ERP, gửi thông báo | Xử lý JSON, tính thuế, sinh file PDF |

**Chú ý:** các tính năng, hạn mức, private networking, availability, deployment slots và pricing thay đổi theo **tier/plan/region**. Bảng trên so sánh bản chất dịch vụ, không cam kết một tính năng cụ thể tồn tại ở mọi SKU.

## 3. Bắt đầu bằng nhu cầu, không bắt đầu bằng tên sản phẩm

Trước khi chọn dịch vụ, hãy trả lời:

1. **Ai gọi?** Trình duyệt, ứng dụng mobile, đối tác B2B, hệ thống nội bộ, scheduler hay event broker?
2. **Giao tiếp gì?** HTTP đồng bộ, webhook, queue, event stream, file, FTP/SFTP hay SaaS connector?
3. **Kết quả phải có ngay?** Trong vài trăm mili-giây, vài giây hay vài giờ?
4. **Quy trình có người tham gia không?** Phê duyệt, đợi phản hồi hoặc hẹn giờ?
5. **Logic dài và tùy biến đến đâu?** Mapping vài trường, hay thuật toán Java phức tạp và nhiều thư viện?
6. **Có nhiều dịch vụ cần phối hợp?** Microsoft 365, Dynamics 365, Salesforce, SAP, SQL, Service Bus?
7. **Yêu cầu API governance?** OAuth/JWT, subscriptions, productization, quotas, versioning, developer portal?
8. **Điều gì xảy ra nếu một bước thất bại?** Retry, compensation, manual intervention, dead-letter?
9. **Ranh giới mạng và dữ liệu?** Private endpoint, VNet, region, dữ liệu nhạy cảm, compliance?
10. **Tải và chi phí?** Số API calls, workflow actions, execution duration, concurrency, peak traffic và retention của logs?

Cách này ngăn tình trạng dùng **Logic Apps như một web server**, dùng **APIM policy như business application**, hoặc dùng **Function như một workflow engine không có state store**.

## 4. Cây quyết định chọn dịch vụ

~~~mermaid
flowchart TD
    A["Bài toán tích hợp mới"] --> B{"Cần gateway chung<br/>cho các HTTP APIs?"}
    B -->|Có| C["Thêm API Management"]
    B -->|Không| D["Không nhất thiết cần APIM"]
    C --> E{"Phần xử lý chính là gì?"}
    D --> E
    E -->|"Nhiều SaaS, điều phối steps, chờ/approval"| L["Logic Apps"]
    E -->|"Tính toán/biến đổi custom code, event handler"| F["Azure Functions"]
    E -->|"API dài hạn nhiều kết nối, quy mô app lớn"| APP["Đánh giá App Service / Container Apps / AKS"]
    L --> G{"Có đoạn thuật toán code phức tạp?"}
    G -->|Có| LF["Logic Apps gọi Functions"]
    G -->|Không| LONLY["Logic Apps có thể đủ"]
    F --> H{"Workflow stateful, chạy lâu, fan-out?"}
    H -->|Có| DF["Đánh giá Durable Functions / Logic Apps"]
    H -->|Không| FONLY["Function có thể đủ"]
~~~

Cây quyết định là **heuristic**, không phải luật tính năng. Ví dụ một API đơn giản vẫn có thể cần APIM nếu phải công bố cho nhiều đối tác. Một Function có thể chạy nền định kỳ, nhưng khi workflow gồm hàng trăm connector actions và human approvals thì Logic Apps thường giúp quan sát quy trình thuận tiện hơn.

### 4.1. Năm câu hỏi quyết định nhanh

| Nếu bạn hỏi... | Ưu tiên xem xét |
|---|---|
| “Làm sao xác thực/rate limit/version nhiều backend APIs dưới một cổng?” | **API Management** |
| “Làm sao khi có email/tệp/CRM event thì chạy 8 bước và phê duyệt?” | **Logic Apps** |
| “Làm sao chạy Java code để chuyển JSON, ký hash hoặc tính nghiệp vụ?” | **Azure Functions** |
| “Làm sao một orchestration nhiều ngày, có fan-out/fan-in và chờ tín hiệu?” | **Logic Apps stateful** hoặc **Durable Functions** |
| “Làm sao vừa quản lý public API vừa gọi SaaS và xử lý Java?” | **APIM + Logic Apps + Functions**, nếu mỗi lớp có giá trị thực |

## 5. API Management: quản trị API, không phải nơi mặc nhiên chạy backend

**Azure API Management** đưa một lớp gateway giữa API callers và backend services. Gateway nhận request, đánh giá policies rồi chuyển tiếp; có thể biến đổi response và phát telemetry.

### 5.1. Những thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| **API** | Bề mặt API được quản trị, có base path và operations |
| **Operation** | Một route + HTTP method và hợp đồng |
| **Backend** | Địa chỉ/định nghĩa backend service được gateway gọi |
| **Product** | Gói nhóm APIs cho người tiêu thụ theo cơ chế subscription/publishing |
| **Subscription** | Cơ chế truy cập API product/API qua key khi được bật |
| **Policy** | Quy tắc inbound/backend/outbound/on-error |
| **Gateway** | Thực thi policies và chuyển tiếp traffic |
| **Developer portal** | Discovery, documentation và trải nghiệm onboarding theo tier/tính năng |
| **Named value** | Cấu hình chia sẻ cho policies, có thể tham chiếu secret theo khả năng hỗ trợ |
| **Version/revision** | Quản trị các phiên bản hợp đồng và bản chỉnh sửa API |

### 5.2. Luồng policy

~~~mermaid
flowchart LR
    R["HTTP request"] --> I["Inbound<br/>validate token / rate limit"]
    I --> B["Backend<br/>forward-request"]
    B --> A["Functions / App Service"]
    A --> O["Outbound<br/>header/response policy"]
    O --> C["Client response"]
    I -. "Lỗi policy" .-> ERR["on-error"]
    B -. "Backend lỗi" .-> ERR
~~~

Một APIM policy được tổ chức theo các vùng **inbound**, **backend**, **outbound**, **on-error**. Các chính sách có thể áp dụng ở những scope khác nhau như global, product, API hoặc operation, theo quy tắc inheritance và thứ tự xử lý.

**Không đặt toàn bộ business logic** như tính thuế phức tạp, truy vấn dữ liệu nhiều bước hoặc orchestration với human approval vào expressions/policies. Policies tốt nhất là lớp quản trị giao tiếp và những biến đổi rõ ràng, kiểm thử được.

### 5.3. Use cases phù hợp

- Một công ty có 15 backend APIs muốn công bố dưới **api.company.example**.
- Một đối tác B2B cần **OAuth2/JWT, quotas, rate limits, IP restrictions**.
- Muốn thống nhất **OpenAPI documentation**, onboarding và versioning.
- Muốn che địa chỉ backend, áp header hoặc routing tới các backend khác nhau.
- Muốn quan sát latency ở gateway và tách lỗi backend/gateway.
- Đã có backend Java trên AKS/App Service nhưng chưa có cổng quản trị chuẩn.

### 5.4. Những kỳ vọng sai

- **APIM không tự thay backend computation.** Gateway chuyển request tới một backend hoặc dùng policy trả response trong một số tình huống; nó không là môi trường tổng quát để chạy Java service.
- **Subscription key không đồng nghĩa xác thực người dùng.** Đó là credential truy cập API subscription, cần thiết kế OAuth/JWT/mTLS và authorization nghiệp vụ riêng.
- **Rate-limit không bảo đảm quota toàn cầu tuyệt đối ở mọi gateway topology.** Một số chính sách giới hạn có tính xấp xỉ/phân tán, cần hiểu scope và behavior khi scale.
- **Cache tại gateway không phải database.** Phải đánh giá invalidation, dữ liệu nhạy cảm và consistency.
- **Không bật gateway public là đã an toàn backend.** Nếu backend vẫn được truy cập trực tiếp, caller có thể bypass APIM policy.

## 6. APIM policy minh họa: kiểm tra JWT và giới hạn gọi

Giả sử đối tác gửi OAuth 2.0 bearer access token do Microsoft Entra ID cấp. Một policy minh họa:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        failed-validation-httpcode="401"
        failed-validation-error-message="Invalid access token"
        require-expiration-time="true"
        require-scheme="Bearer">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://API_APP_ID</audience>
      </audiences>
    </validate-jwt>
    <rate-limit-by-key
        calls="60"
        renewal-period="60"
        counter-key="@(context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

Đây là **mẫu để phân tích**, không phải policy deploy nguyên trạng. Phải thay **TENANT_ID**, **API_APP_ID**, chọn issuer/audience đúng theo access token của ứng dụng, review yêu cầu claims/scopes/roles và kiểm tra bản APIM tier/policy đang hỗ trợ.

### 6.1. Vì sao thứ tự policy quan trọng?

**validate-jwt** được thực thi trước **rate-limit-by-key** trong ví dụ. Nếu token không hợp lệ, request có thể bị từ chối trước khi tiêu thụ quota theo cách policy tính.

**rate-limit-by-key** dùng IP trong demo. Nhưng IP không phải danh tính người dùng: nhiều người có thể chia sẻ NAT IP, IP có thể thay đổi, proxy có thể ảnh hưởng giá trị nhận diện. Trong production nên dùng **key đáng tin từ client application, subscription hoặc claim đã kiểm chứng**, theo chính sách và khả năng expression/APIM hỗ trợ.

### 6.2. JWT validation không thay authorization nghiệp vụ

Gateway có thể kiểm tra chữ ký, expiry, issuer và audience. Nhưng backend vẫn phải kiểm tra:

- Người dùng hoặc client có được xem **orderId=481** hay không?
- User có role/scope đủ để cập nhật đơn hàng?
- Tenant ID của token có khớp dữ liệu/tenant ownership?
- Tài nguyên đang ở trạng thái cho phép thay đổi không?

**JWT hợp lệ không có nghĩa mọi operation đều được phép**.

### 6.3. Bảo vệ backend khỏi truy cập trực tiếp

Nếu Function backend có URL công khai độc lập, kẻ tấn công có thể bypass APIM khi biết URL. Cần thiết kế một hoặc nhiều biện pháp theo tính năng của hosting plan:

- Private Endpoint hoặc network restrictions theo topology được hỗ trợ.
- Azure Functions authentication/authorization (Microsoft Entra) khi phù hợp.
- Function key được APIM quản lý dưới dạng secret/named value khi cơ chế phù hợp; **key không thay OAuth**.
- mTLS hoặc cơ chế service-to-service authentication phù hợp.
- Azure Firewall, NSG/VNet hoặc chính sách ingress khác theo hệ thống.

Không dựa vào việc URL backend “khó đoán” như một biện pháp bảo mật.

## 7. Logic Apps: workflow-first integration

Azure Logic Apps cho phép mô hình hóa luồng gồm **triggers**, **actions**, **conditions**, **loops**, **parallel branches**, **scopes** và **connections**. Từng lần chạy có thể được quan sát bằng run history khi môi trường/chế độ hỗ trợ.

### 7.1. Ví dụ workflow

~~~mermaid
flowchart TD
    E["Trigger: OrderApproved"] --> V["Validate payload"]
    V --> C["Create customer in CRM"]
    C --> F["Call Azure Function<br/>custom price mapping"]
    F --> ERP["Create sales order in ERP"]
    ERP --> N["Notify by email / Teams"]
    ERP -->|Failure| H["Compensation / alert / manual review"]
    N --> S["Record completion"]
~~~

Tại đây, điểm mạnh Logic Apps là **hình dung thứ tự và trạng thái các bước**, dùng connector phù hợp và xử lý những chỗ tích hợp đã có sẵn action/trigger.

### 7.2. Những thành phần quan trọng

| Thành phần | Tác dụng | Điều cần kiểm tra |
|---|---|---|
| **Trigger** | Bắt đầu workflow | Webhook, poll, recurrence, HTTP, Service Bus |
| **Action** | Một bước xử lý/gọi dịch vụ | Output schema, timeout, retry |
| **Connector** | Cơ chế tích hợp với ứng dụng/dịch vụ | Authentication, tier, throttling, region |
| **Condition/Switch** | Rẽ nhánh nghiệp vụ | Xử lý unexpected values |
| **For each** | Xử lý danh sách | Concurrency/race và order |
| **Scope** | Gom actions theo đoạn logic | Trạng thái Succeeded/Failed/Skipped/TimedOut |
| **runAfter** | Chỉ định bước sau chạy theo trạng thái nào | Error-handling và finally |
| **Stateful workflow** | Lưu state/run history theo mô hình hỗ trợ | Lưu trữ, privacy, retention, chi phí |
| **Stateless workflow** | Tối ưu xử lý ngắn, ít persistence hơn | Không hợp lý cho chờ lâu và run history chi tiết |
| **Managed identity** | Xác thực tới Azure resource khi connector hỗ trợ | Role data-plane và connection config |

### 7.3. Logic Apps Consumption và Standard

| Tiêu chí | Consumption | Standard |
|---|---|---|
| Resource model | Workflow theo mô hình multitenant | Single-tenant hosting, workflow apps và hosting plan tương ứng |
| Chi phí chính | Thường theo trigger/action/connector executions | Hosting compute/storage và các khoản connector/operations áp dụng |
| Workflow | Workflow được quản lý theo mô hình Consumption | Hỗ trợ stateful và stateless workflows trong môi trường phù hợp |
| Connectors | Managed connectors theo catalog | Built-in và managed connectors tùy loại |
| Network/integration | Theo khả năng Consumption/tier | Nhiều khả năng hosting/network riêng theo plan |
| Local development | Theo công cụ hỗ trợ | Workflow project/VS Code theo trải nghiệm Standard |
| Phù hợp | Workflows sự kiện/định kỳ không cần always-on custom hosting | Nhiều workflow cùng app, điều kiện chạy/latency/network cần Standard |

**Không mặc định Consumption luôn rẻ hơn hoặc Standard luôn nhanh hơn.** Workload có nhiều actions, connectors, chạy liên tục hay networking riêng có thể đổi kết luận; cần pricing calculator và benchmark.

### 7.4. Khi Logic Apps là lựa chọn mạnh

- Tích hợp nhiều **SaaS connectors** mà không muốn tự xây từng API client.
- Quy trình duyệt mua hàng/chi phí có **đợi người phê duyệt** và nhiều nhánh.
- Khi có dữ liệu từ FTP/SFTP/SharePoint/Office 365/Dynamics/SQL thì chuyển sang hệ thống khác.
- Workflow cần **run history**, truy vết từng action và điều kiện thất bại.
- Orchestration gồm bước đồng bộ và bất đồng bộ, chờ timer hoặc webhook callback.
- Yêu cầu business/operations cùng đọc được cấu trúc flow.

### 7.5. Những trường hợp không nên ép vào Logic Apps

- Tính toán CPU-intensive kéo dài, xử lý hàng triệu bản ghi trong một For each không giới hạn.
- Business algorithm Java phức tạp cần unit/integration tests nhiều và thư viện đặc thù.
- API high-throughput low-latency mà mỗi call chỉ cần một câu lệnh ngắn nhưng workflow overhead không đáng có.
- Lưu long-lived business data trong run history như database.
- Vòng lặp không giới hạn, retry vô hạn hoặc dựa vào connector mà không xem throttling.
- Mong **exactly-once effects** khi workflows có retry/resubmit; điều này phải giải bằng idempotency.

## 8. Logic Apps runAfter, retry và compensation

### 8.1. Retry ở mức action

Một connector action có thể tự retry transient errors theo retry policy của connector/runtime. Ví dụ một HTTP call tới ERP trả HTTP 429, Logic Apps có thể retry theo cấu hình.

Rủi ro: ERP đã tạo order nhưng response bị timeout. Nếu workflow retry **POST /orders** không có idempotency key, có thể tạo đơn hàng trùng.

Giải pháp:

- Truyền business key ổn định như **externalOrderId**.
- Dùng API idempotent/upsert khi đối tác hỗ trợ.
- Kiểm tra kết quả qua GET/status trước khi retry khi outcome không rõ.
- Có retry cap, timeout và alert sau khi hết số lần thử.
- Không lưu secret/payload nhạy cảm trong run history không được bảo vệ.

### 8.2. Try / Catch / Finally bằng Scopes

Một mẫu thường gặp:

~~~text
Scope Try
  - Validate
  - Call CRM
  - Call ERP
  - Write final state

Scope Catch
  runAfter Try: Failed, TimedOut
  - Capture error
  - Mark NEEDS_REVIEW
  - Notify operator
  - Compensate theo business rules

Scope Finally
  runAfter Try/Catch theo trạng thái phù hợp
  - Emit correlation/metrics
~~~

**Compensation không phải rollback database tự động**. Nếu bước 1 đã tạo khách hàng CRM, bước 2 tạo ERP bị lỗi, “xóa CRM customer” có thể không đúng nếu khách hàng đã được dùng ở hệ thống khác. Cần định nghĩa compensation theo nghiệp vụ, thường là thay đổi trạng thái hoặc tạo một giao dịch bù trừ.

### 8.3. Resubmit có thể tạo tác dụng phụ mới

Run history giúp điều tra và một số mô hình cho phép resubmit run. Resubmit **không phải rewind transaction**: các bước đã gọi API bên ngoài có thể đã commit. Phải kiểm tra workflow state, idempotency, dedup và compensation trước khi chạy lại.

### 8.4. Concurrency và ordering

Nếu **For each** chạy song song, các vòng có thể hoàn thành khác thứ tự input. Trigger concurrency cao cũng có thể tạo race khi nhiều workflow cập nhật cùng một record.

Muốn xử lý theo thứ tự, cần:

- Thiết kế partition/business key hoặc concurrency limits.
- Dùng database locking/optimistic concurrency.
- Phân biệt order-sensitive operations với xử lý độc lập.
- Không tắt mọi concurrency chỉ vì một bug ngẫu nhiên mà không phân tích throughput.

## 9. Logic Apps workflow JSON minh họa

Ví dụ workflow có trigger **Recurrence** mỗi giờ và gọi một HTTP endpoint kiểm tra trạng thái. Đây là mẫu học cấu trúc, **không chạy nguyên trạng** vì URL là placeholder, chưa có authentication và chưa có cấu hình resource/connection.

~~~json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {},
  "triggers": {
    "Every_Hour": {
      "type": "Recurrence",
      "recurrence": {
        "frequency": "Hour",
        "interval": 1
      }
    }
  },
  "actions": {
    "Check_Service": {
      "type": "Http",
      "inputs": {
        "method": "GET",
        "uri": "https://api.example.invalid/health"
      },
      "runAfter": {}
    },
    "Evaluate_Result": {
      "type": "If",
      "expression": {
        "equals": [
          "@outputs('Check_Service')?['statusCode']",
          200
        ]
      },
      "actions": {},
      "else": {
        "actions": {}
      },
      "runAfter": {
        "Check_Service": [
          "Succeeded"
        ]
      }
    }
  },
  "outputs": {}
}
~~~

Trong thực tế:

- Định nghĩa workflow thường được đóng gói trong tài nguyên Logic App và có **connections/authentication** nếu dùng connectors.
- **Recurrence** là lịch khởi động; nó không có nghĩa mọi lần chạy sẽ xong trước lần kế tiếp.
- HTTP action nên có timeout/retry policy và managed identity hoặc auth phù hợp.
- Dùng **runAfter** để phân biệt Succeeded/Failed/TimedOut/Skipped.
- **Evaluate_Result** chỉ chạy nếu HTTP action succeeded theo runAfter. Để xử lý một HTTP 500 có thể khiến action Failed, cần có nhánh Catch/runAfter phù hợp chứ không trông cậy vào condition 200.
- URL **example.invalid** là placeholder không thể truy cập; không được đưa vào production.
- Tài liệu chỉ minh họa cách chọn Logic Apps khi có workflow, không thay thế ARM/Bicep deployment đã kiểm chứng.

## 10. Azure Functions: custom code theo trigger

**Azure Functions** thực thi mã ứng dụng khi trigger chạy. Thay vì tự khởi tạo máy ảo và scheduler/container host, nền tảng cung cấp hosting và trigger plumbing theo plan.

### 10.1. Một số triggers phổ biến

| Trigger | Tình huống |
|---|---|
| **HTTP trigger** | Nhận webhook hoặc API request |
| **Timer trigger** | Chạy job định kỳ |
| **Service Bus trigger** | Nhận hàng đợi/thuộc subscription |
| **Event Hubs trigger** | Xử lý event stream theo partition/batch |
| **Event Grid trigger** | Phản ứng với sự kiện tài nguyên, ví dụ BlobCreated |
| **Blob trigger** | Xử lý thay đổi Blob theo extension và mô hình hỗ trợ |
| **Queue Storage trigger** | Chạy xử lý nền từ Azure Storage Queue |

Trigger quyết định **khi nào Function được gọi**, không định nghĩa toàn bộ business logic. Bindings giúp đọc/ghi một số dịch vụ theo extension, nhưng SDK trực tiếp vẫn thích hợp khi cần kiểm soát transaction, connection, retry hoặc domain logic cụ thể.

### 10.2. Khi Functions phù hợp

- Chạy vài chục dòng hoặc vài nghìn dòng Java/C# để xử lý dữ liệu.
- Parse/validate/transform JSON/XML, tính toán thuế, chuyển định dạng file.
- Xử lý webhook/callback cần custom verification.
- Xử lý một message Azure Service Bus, Blob hoặc Event Grid.
- Một API nhỏ, không muốn vận hành một web server liên tục.
- Một bước compute tùy chỉnh trong Logic Apps workflow.

### 10.3. Khi không nên mặc định chọn Functions

- Một ứng dụng web lớn cần host web framework/server với startup và connections đặc thù: đánh giá **App Service, Container Apps hoặc AKS**.
- Job liên tục kéo dài hơn giới hạn của plan/trigger và không có checkpoint: đánh giá **Durable Functions**, Container Apps Jobs, Batch hoặc thiết kế chia nhỏ.
- Muốn giữ business state trong memory của Function giữa executions: không phù hợp.
- API cần latency cực thấp ổn định nhưng plan có cold start hoặc scale khác SLA: chọn plan/always-ready phù hợp hoặc hosting khác.
- Workflow có hàng trăm connector actions và human approval: cân nhắc Logic Apps thay vì tự code mỗi bước.

## 11. Functions hosting plan ảnh hưởng kiến trúc

Azure Functions có các mô hình hosting như **Flex Consumption**, **Premium**, **Dedicated/App Service plan** và các lựa chọn/biến thể được hỗ trợ theo hệ điều hành/runtime/region. Mỗi plan có đặc tính khác nhau về cost, startup, scaling, timeout, networking và capacity.

| Yêu cầu | Điều phải đánh giá |
|---|---|
| Traffic không đều, nhiều lúc idle | Plan tiêu thụ theo execution/compute có thể hiệu quả |
| Latency không chịu cold start | Pre-warmed/always-ready instances hoặc plan provisioned phù hợp |
| VNet integration và private networking | Feature support của đúng hosting plan/region |
| Long-running execution | Timeout max, trigger semantics, memory, shutdown |
| High throughput event stream | Scaling constraints, batch/concurrency và downstream capacity |
| Ứng dụng Java cần JVM startup lớn | Cold start, heap, memory quota, prewarming |
| Predictable cost với tải ổn định | So sánh Premium/Dedicated hoặc app hosting khác |
| Compliance và network isolation | Feature availability, identity và network policy |

**Không dùng một bảng timeout cố định cho mọi Functions plan**: giới hạn có thể thay đổi theo runtime, trigger, HTTP connection timeout và plan. Một backend chạy vài phút có thể vẫn bị gateway/client HTTP timeout trước khi Function hoàn tất.

## 12. Ví dụ Azure Function Java: nhận yêu cầu và validate

Ví dụ minh họa một Function HTTP dùng annotation của Azure Functions Java library. Function chỉ kiểm tra payload và trả response; nó **không ghi order**, không enqueue message và không được hiểu là ứng dụng production hoàn chỉnh.

~~~java
package com.example;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import java.util.Optional;

public class ValidateOrderFunction {
    @FunctionName("ValidateOrder")
    public HttpResponseMessage run(
            @HttpTrigger(
                name = "request",
                methods = { HttpMethod.POST },
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/validate"
            )
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String body = request.getBody().orElse("");

        if (body.isBlank()) {
            return request
                .createResponseBuilder(HttpStatus.BAD_REQUEST)
                .header("Content-Type", "application/json")
                .body("{\"error\":\"body_required\"}")
                .build();
        }

        context.getLogger().info("Received order validation request");

        return request
            .createResponseBuilder(HttpStatus.OK)
            .header("Content-Type", "application/json")
            .body("{\"valid\":true,\"note\":\"demo-only\"}")
            .build();
    }
}
~~~

### 12.1. Ý nghĩa của HTTP authLevel FUNCTION

**AuthorizationLevel.FUNCTION** yêu cầu Function key hoặc cơ chế tương ứng theo runtime; nó **không kiểm tra danh tính người dùng hoặc quyền xem đơn hàng**. Để bảo vệ public API production:

1. Xác thực caller bằng Microsoft Entra ID/OAuth/JWT tại APIM hoặc identity layer phù hợp.
2. Backend phải áp dụng **authorization nghiệp vụ**.
3. Hạn chế đường direct access vào Function.
4. Bảo vệ Function key như secret, rotate theo quy trình.
5. Dùng TLS và có telemetry để phát hiện lỗi 401/403.

Nếu APIM gọi backend bằng Function key, lưu key bằng **named value/Key Vault integration** hoặc cơ chế secret được duyệt. Không ghi literal function key trong policy XML hay Git repository.

### 12.2. Vì sao demo trả HTTP 200 thay vì 202?

Function ở trên **chưa lưu công việc vào durable queue**; trả 202 Accepted dễ khiến caller hiểu rằng backend đã tiếp nhận xử lý bất đồng bộ. Khi triển khai API thật, chỉ trả 202 sau khi yêu cầu đã được **ghi bền vững** vào queue/outbox/workflow store và có tracking ID để tra cứu.

### 12.3. Java Function app không phải JVM web server truyền thống

Java Functions có runtime/annotations, host.json, dependencies, Java version và phương thức đóng gói/deployment riêng. Không đổi tên một executable JAR của Spring Boot rồi nghĩ rằng nó tự trở thành Function HTTP. Cần một Function project với Java worker/runtime tương thích hoặc chọn App Service/Container Apps nếu muốn giữ nguyên ứng dụng web framework.

## 13. Durable Functions: code-first workflow có trạng thái

**Durable Functions** bổ sung mô hình orchestration có persistence, cho phép fan-out/fan-in, timers, retries và external events theo mô hình hoạt động được runtime hỗ trợ.

~~~mermaid
flowchart TD
    T["HTTP start orchestration"] --> O["Durable orchestrator"]
    O --> A["Activity: validate order"]
    A --> B["Activity: reserve inventory"]
    B --> W["Wait for payment event or durable timer"]
    W --> C{"Paid?"}
    C -->|Yes| D["Activity: create shipment"]
    C -->|Timeout| E["Activity: compensate / release stock"]
    D --> F["Completed"]
    E --> F
~~~

### 13.1. Durable Functions khác Logic Apps thế nào?

| Câu hỏi | Durable Functions | Logic Apps |
|---|---|---|
| Cách mô tả flow | Code-first orchestrator và activities | Workflow definition/designer |
| Complex branching | Linh hoạt bằng code, framework constraints | Actions/conditions/scopes |
| Nhiều SaaS connectors | Thường dùng SDK/HTTP hoặc bindings | Thế mạnh connector catalog |
| Human approval | Có thể đợi external event | Có actions/connectors/workflow patterns |
| State/history | Durable orchestration state | Workflow run/state theo plan |
| Quy tắc mã | Orchestrator phải deterministic theo runtime model | Designer/workflow expression semantics |
| Quan sát | Orchestration status, function telemetry | Run history từng action |
| Khi phù hợp | Nhiều logic code, fan-out/fan-in, workflow backend | Tích hợp SaaS và điều phối có tính khai báo |

### 13.2. Cảnh báo về tính quyết định

Code orchestrator trong Durable Functions có thể được **replay** để khôi phục trạng thái; vì vậy không gọi I/O tùy ý hoặc lấy thời gian/ngẫu nhiên theo cách không deterministic ngay trong orchestrator. Đưa side effects vào **activity functions** và dùng APIs durable timer/event theo hướng dẫn đúng runtime.

Không coi “Durable Functions đảm bảo exactly-once gọi API bên ngoài” là đúng. Activity có thể retry/chạy lại khi hệ thống lỗi. Các tác dụng phụ như gửi tiền, tạo invoice hay gửi email phải **idempotent**.

### 13.3. Chọn Logic Apps hay Durable Functions cho workflow dài hạn?

Chọn **Logic Apps** khi giá trị lớn nhất nằm ở **connector integration, cấu trúc flow được nhìn thấy và điều phối tác vụ**.

Chọn **Durable Functions** khi workflow đòi hỏi **logic orchestration phong phú trong code**, có nhiều activities tính toán và đội ngũ muốn áp dụng quy trình unit testing/versioning cho mã.

Trong một số hệ thống, Logic Apps gọi Durable Functions hoặc ngược lại. Nhưng kết hợp chỉ có ích khi ranh giới rõ, tránh tạo hai orchestration engines cùng quản lý một business state.

## 14. Ma trận lựa chọn cho các tình huống thực tế

| Tình huống | Lựa chọn thường hợp lý | Tại sao | Điểm cần kiểm tra |
|---|---|---|---|
| Công bố 20 API hiện có cho đối tác, có JWT/rate limits | **APIM** trước backend hiện hữu | Centralized governance | Backend không bypass gateway |
| Khi invoice được duyệt, ghi Dynamics, SAP, gửi email, đợi approval | **Logic Apps** | Connectors và run history | Retry, human timeout, licensing |
| Xử lý Blob mới tải lên thành PDF bằng Java | **Functions** hoặc Container Apps Jobs nếu nặng | Custom compute theo event | Timeout, memory, input size |
| API cần xác thực và xử lý giá do Java code | **APIM + Functions** | Gateway tách business compute | Latency, direct backend exposure |
| Từ Salesforce chuyển đổi schema phức tạp rồi ghi ERP | **Logic Apps + Functions** | Connector orchestration + code transformation | Idempotency và correlation |
| Đối tác gửi order, xử lý trong 5 phút và tra cứu trạng thái | **APIM + Function + Service Bus** | HTTP ingress + async handling | Durable enqueue, 202/status API |
| Chờ khách chấp thuận tối đa 3 ngày | **Logic Apps stateful** hoặc **Durable Functions** | State và timers | Compensation, run retention |
| API Java Spring Boot đang chạy trên AKS | **APIM + AKS/App Service** | Không cần viết lại backend | Ingress/network/observability |
| Timer hằng đêm đọc dữ liệu và ghi report đơn giản | **Function Timer** | Trigger + code | Idempotency, limits |
| Scheduler gọi 10 SaaS APIs có sẵn connector | **Logic Apps** | Low-code integration | Connector throttling và plan cost |
| Dòng telemetry lớn hàng triệu events/giờ | **Event Hubs + consumer/Stream Analytics** | Stream processing | APIM không thay event broker |
| Tính toán GPU/CPU dài nhiều giờ | **Container Apps Jobs/Batch/AKS** | Compute model phù hợp hơn | Quota, scaling, orchestration |
| API nội bộ rất nhỏ, không có consumer ngoài | Có thể **Functions trực tiếp** | Không cần gateway phức tạp | Đánh giá nhu cầu policy thực tế |
| Doanh nghiệp cần API catalog, portal, versioning | **APIM** | API lifecycle management | Tier/support và vận hành |

Bảng là quyết định **ban đầu**. Nếu có yêu cầu về residency, mạng riêng, compliance hoặc traffic khác thường, lựa chọn phải được benchmark và review theo SKU cụ thể.

## 15. Case study A: API Orders B2B với xử lý bất đồng bộ

Một đối tác gửi 300 requests/giây lúc peak, cần nhận HTTP response nhanh. Việc kiểm tra inventory và tạo shipment có thể mất tới 3 phút.

### 15.1. Phương án không nên làm

~~~text
Partner → APIM → Function HTTP → gọi Inventory → gọi ERP → gửi email
                            └── Giữ HTTP connection 3 phút
~~~

Vấn đề:

- Timeout ở APIM/client/function hosting có thể đến trước khi xử lý hoàn tất.
- Retry HTTP POST có thể tạo order trùng.
- Lỗi downstream làm cạn connections và giảm availability.
- Không có tracking status hoặc business correlation đáng tin.
- Không có chỗ bền vững lưu yêu cầu đã được chấp nhận.

### 15.2. Phương án có hàng đợi

~~~mermaid
flowchart LR
    P["Partner B2B"] -->|"OAuth / HTTPS"| G["APIM"]
    G -->|"POST /orders"| F["HTTP Function<br/>validate + enqueue"]
    F --> Q["Service Bus orders-commands"]
    F -->|"202 + operationId"| G
    Q --> W["Worker Function / Logic Apps"]
    W --> DB["Orders DB"]
    W --> ERP["ERP / Inventory"]
    P -->|"GET /operations/{id}"| G
    G --> S["Status API"]
    S --> DB
~~~

Ranh giới trách nhiệm:

- **APIM:** xác minh token, quotas/rate limits, versioning, routing, tracing.
- **HTTP Function:** xác minh payload, cấp operationId/idempotency key, ghi bền vững vào queue/outbox.
- **Service Bus:** tách traffic HTTP khỏi xử lý dài, hỗ trợ retry/DLQ theo cấu hình.
- **Worker Function hoặc Logic Apps:** thực thi các bước nghiệp vụ.
- **Database:** lưu trạng thái PENDING/PROCESSING/SUCCEEDED/FAILED và business outcome.

### 15.3. Hợp đồng HTTP 202

Ví dụ response sau khi **durable enqueue thành công**:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /operations/op-481

{
  "operationId": "op-481",
  "status": "PENDING",
  "statusUrl": "/operations/op-481"
}
~~~

Đây là **response mẫu**, không phải code backend đã thực thi. Nếu enqueue chưa thành công, không được trả 202 rồi làm mất yêu cầu. Cần trả lỗi phù hợp hoặc dùng transactional outbox nếu API đồng thời ghi database.

### 15.4. Idempotency

Client có thể retry vì timeout ngay sau enqueue. Nếu lần thứ hai tạo operationId khác, có nguy cơ hai commands cùng xử lý.

Giải pháp:

- Nhận **Idempotency-Key** do client cung cấp hoặc tạo business key ổn định.
- Lưu unique constraint theo **partnerId + idempotencyKey**.
- Trả về cùng operationId khi yêu cầu trùng nhưng cùng nội dung.
- Không dùng một idempotency key cho hai payload khác nhau; trả lỗi conflict/validation.
- Consumer xử lý idempotent bằng message/event ID.
- Nếu broker send outcome không rõ, reconciliation/outbox thay cho retry mù quáng.

### 15.5. Khi nào Logic Apps xuất hiện trong case study?

Nếu sau khi nhận command phải:

1. Kiểm tra ERP.
2. Gửi yêu cầu duyệt tới người quản lý.
3. Chờ tối đa 2 ngày.
4. Cập nhật Dynamics.
5. Gửi Teams/email.
6. Compensation nếu bất kỳ bước nào lỗi.

Đó là dấu hiệu cần **workflow orchestration**, nơi Logic Apps stateful có thể có lợi hơn một HTTP Function dài. Nếu logic tính toán chủ yếu là Java, Logic Apps gọi Functions ở một hoặc vài bước thay vì viết lại code trong expressions.

## 16. Case study B: kết nối SaaS và quy trình phê duyệt

Tình huống: tệp hóa đơn đến SharePoint; cần xác minh, gửi ERP, yêu cầu người quản lý chấp thuận nếu giá trị vượt ngưỡng, rồi thông báo.

### 16.1. Sơ đồ

~~~mermaid
flowchart TD
    SP["SharePoint: New file"] --> LA["Logic Apps trigger"]
    LA --> META["Get metadata + file"]
    META --> FN["Function: verify invoice schema"]
    FN --> RULE{"Amount > threshold?"}
    RULE -->|Yes| APPROVAL["Approval / wait for decision"]
    RULE -->|No| ERP["Create invoice in ERP"]
    APPROVAL -->|Approved| ERP
    APPROVAL -->|Rejected/TimedOut| REVIEW["Mark rejected + notify"]
    ERP --> STATUS["Record external invoice id"]
    STATUS --> EMAIL["Notification"]
    ERP -->|Error| CATCH["Catch scope: retry/compensate/alert"]
~~~

### 16.2. Vì sao Logic Apps dẫn dắt?

- Các connectors SharePoint/ERP/Teams/email có sẵn khi catalog và quyền cho phép.
- Workflow có nhiều branches, waits và business approvals.
- Run history có ích khi operator cần biết **bước nào lỗi**.
- Function chỉ giữ phần code như validate XML/signature hoặc tính toán khó diễn đạt bằng expression.

### 16.3. Những rủi ro phải kiểm soát

- Connector đăng nhập bằng user cá nhân có thể hết quyền hoặc hết hạn. Ưu tiên service connection/managed identity theo khả năng connector.
- File có thể bị cập nhật trước khi workflow đọc; dùng version/ETag.
- Với For each, giới hạn concurrency để không tạo hai invoice từ cùng file.
- ERP POST đã thành công nhưng response timeout; retry cần idempotency.
- Run history có thể lưu nội dung hóa đơn/PII; cấu hình **secure inputs/outputs**, retention và quyền xem logs.
- Human approval có deadline, escalation và người thay thế.
- Business state cần được lưu rõ; chỉ dựa vào email đã gửi không đủ chứng minh đã được phê duyệt.

## 17. Case study C: webhook bên ngoài với API governance

Đối tác gửi webhook đến doanh nghiệp:

~~~text
External SaaS → Public HTTPS → APIM → Function handler
                                   |
                                   +→ durable message / DB
~~~

### 17.1. APIM có cần thiết không?

Nếu chỉ có một webhook nội bộ ít traffic, Function HTTP có authentication phù hợp có thể đủ.

APIM trở nên có ích khi:

- Nhiều webhook providers và cần chung routing/policy.
- Cần versioning và quotas theo đối tác.
- Muốn tập trung TLS/certificates, tracing, transformation, IP filtering.
- Cần API catalog hoặc áp những chính sách bảo vệ backend khác nhau.

### 17.2. Webhook signature

Không phải webhook nào cũng dùng Entra JWT. Một số provider gửi **HMAC signature** trên body hoặc custom token.

Lưu ý:

- Xác minh chữ ký trên **raw request body** theo cách provider quy định.
- Kiểm tra timestamp/tolerance và chống replay.
- Không log payload/secret nhạy cảm.
- Hạn chế retry side effects bằng eventId.
- Nếu cần custom crypto logic phức tạp, **Function** phù hợp hơn policy script dài trong APIM.
- Trả ACK chỉ sau khi sự kiện đã được durable enqueue/record theo hợp đồng provider.

## 18. Case study D: xử lý dữ liệu theo sự kiện

Yêu cầu: khi tệp CSV lên Blob Storage, kiểm tra schema, chuyển sang JSON và cập nhật metadata.

### 18.1. Chọn Function

~~~mermaid
flowchart LR
    B["Blob Storage: new CSV"] --> EG["Event Grid / Blob trigger"]
    EG --> F["Azure Function<br/>validate + transform"]
    F --> OUT["Blob Storage: JSON"]
    F --> DB["Metadata DB"]
    F -. "Errors/telemetry" .-> MON["Application Insights"]
~~~

Function phù hợp khi:

- Logic chuyển đổi là code có thể test.
- Không cần tích hợp nhiều hệ thống SaaS.
- Event trigger và scaling theo tải đáp ứng SLA.
- Dữ liệu đủ nhỏ/thời lượng đủ phù hợp với hosting plan.

### 18.2. Khi nên thêm Logic Apps?

Khi mỗi file còn phải:

- Lấy metadata từ SharePoint.
- Gửi email cho bộ phận duyệt.
- Gọi CRM theo connector.
- Đợi người phụ trách xác nhận.
- Tạo ticket khi thất bại.

Lúc đó dùng Logic Apps cho orchestration và giữ Function làm bước transform.

### 18.3. Khi nên dùng Container Apps Jobs/Batch thay Functions?

Nếu mỗi file có kích thước rất lớn, xử lý hàng giờ, cần GPU/specialized binaries hoặc yêu cầu tài nguyên vượt giới hạn Function plan, hãy đánh giá **Azure Container Apps Jobs, Azure Batch hoặc AKS Jobs**; Logic Apps không nên loop qua hàng triệu dòng CSV trong memory.

## 19. Case study E: API đã có backend Java

Một doanh nghiệp đã triển khai Spring Boot trên App Service hoặc AKS với:

- Authentication/authorization nghiệp vụ.
- Database transactions.
- Connection pools.
- Nhiều endpoints REST.
- Pipeline CI/CD đã trưởng thành.

Nếu bài toán mới chỉ là công bố API ra đối tác, **không có lý do phải chuyển toàn bộ Spring Boot sang Functions hoặc Logic Apps**.

Kiến trúc:

~~~mermaid
flowchart LR
    PARTNER["Partners"] --> APIM["APIM<br/>OAuth + quotas + versioning"]
    APIM --> JAVA["Spring Boot API<br/>App Service / AKS"]
    JAVA --> DB["Azure SQL"]
    JAVA --> SB["Azure Service Bus"]
    SB --> FLOW["Logic Apps<br/>downstream SaaS orchestration"]
~~~

Dùng đúng dịch vụ theo ranh giới:

- **APIM** bổ sung API lifecycle governance.
- **Spring Boot** giữ business API dài hạn và database transactions.
- **Logic Apps** chỉ dùng cho những workflow connector nếu có.
- **Functions** có thể có cho tác vụ nhỏ theo event, không bắt buộc.

## 20. HTTP request đồng bộ, bất đồng bộ và timeout

### 20.1. Chọn theo trải nghiệm người dùng

| Yêu cầu | Kiểu | Dịch vụ thường phù hợp |
|---|---|---|
| GET trạng thái đơn hàng trong 150 ms | Sync HTTP | APIM → backend API |
| POST tạo một bản ghi với DB commit ngắn | Sync HTTP | APIM → Function/App Service |
| POST xử lý 3 phút | Async 202 + status | APIM → Function enqueue → worker |
| Gửi yêu cầu approval 48 giờ | Stateful orchestration | Logic Apps/Durable Functions |
| Nhận hàng nghìn events/s | Broker-triggered processing | Event Hubs/Functions/ASA/consumer |
| Nightly import batch | Scheduled job | Functions Timer / Logic Apps / Container Apps Jobs tùy logic |

### 20.2. Timeout nhiều lớp

Một request qua APIM tới Functions có nhiều điểm timeout:

- Client/browser/proxy HTTP timeout.
- APIM gateway/backend forwarding timeout theo policy/tier.
- Function hosting/HTTP trigger behavior.
- Downstream database/API timeout.
- Network/DNS/TLS timeouts.

**Không tăng mọi timeout lên hàng giờ để né kiến trúc bất đồng bộ.** HTTP connection có giới hạn thực tế; tác vụ dài cần durable queue/workflow state và endpoint tra cứu.

### 20.3. Cancellation không đồng nghĩa rollback

Client ngắt HTTP connection không bảo đảm backend Function hoặc Logic Apps đã ngừng side effects. Nếu cần hủy đơn hàng, thiết kế một **cancellation command** có trạng thái và compensation. Phải xét race giữa cancel và worker hoàn thành.

## 21. Reliability: retry, idempotency, compensation

### 21.1. At-least-once là giả định an toàn

Event-driven Functions, Logic Apps connector triggers và broker messages có thể retry/re-deliver theo cơ chế từng trigger. Hãy thiết kế theo khả năng cùng một business event được xử lý nhiều lần.

~~~mermaid
flowchart TD
    IN["Incoming event / HTTP command"] --> ID["Read stable eventId/idempotencyKey"]
    ID --> CHECK{"Already processed?"}
    CHECK -->|Yes| ACK["Return previous outcome / acknowledge"]
    CHECK -->|No| WORK["Apply durable state transition"]
    WORK --> LOG["Record processed ID + outbox"]
    LOG --> ACK
~~~

Không đặt khóa idempotency chỉ trong memory của Function, vì instance có thể recycle hoặc scale-out.

### 21.2. Retry transient vs permanent

| Lỗi | Phản ứng |
|---|---|
| HTTP 429 từ SaaS | Backoff, tôn trọng Retry-After khi có, giới hạn concurrency |
| Network timeout | Reconcile outcome/idempotent retry |
| Payload sai schema | Reject/quarantine; không retry vô hạn |
| 401/403 | Kiểm tra token/role/secret; retry vô hạn không sửa authorization |
| Database deadlock | Retry có giới hạn và transaction handling |
| API provider đã tạo record nhưng response timeout | Query theo external key hoặc xử lý idempotency |
| Logic Apps action thất bại sau side effect | Compensation hoặc manual review, không resubmit mù |
| Broker lock lost | Consumer có thể nhận lại; dedup business state |

### 21.3. Transactional outbox

Nếu Function/API vừa ghi SQL vừa phát event, không có transaction tự động bao trùm SQL và Service Bus:

~~~mermaid
flowchart LR
    API["Function / backend API"] --> DBTX["Single database transaction"]
    DBTX --> ORDER["Orders table"]
    DBTX --> OUT["Outbox table"]
    OUT --> PUB["Outbox publisher"]
    PUB --> BUS["Service Bus / Event Hubs"]
    BUS --> CON["Consumer idempotent"]
~~~

Publisher có thể gửi trùng sau crash giữa send và mark-sent. Stable message/event ID và consumer idempotency giải quyết duplicate effects.

### 21.4. Compensation và Saga

Nếu một workflow tạo invoice, trừ inventory và đặt lịch vận chuyển, rollback tất cả bằng transaction ACID xuyên SaaS gần như không khả thi.

Hãy mô hình hóa:

1. **Pending**.
2. **InventoryReserved**.
3. **InvoiceCreated**.
4. **ShipmentBooked**.
5. **Completed** hoặc **Compensating/NeedsReview**.

Mỗi bước có idempotency key, timeout, retry và hoạt động bù phù hợp. Logic Apps/Durable Functions là nơi orchestration hữu ích, còn dữ liệu nghiệp vụ phải được lưu ở hệ thống đáng tin.

## 22. So sánh bảo mật ở ba dịch vụ

| Lớp | API Management | Logic Apps | Azure Functions |
|---|---|---|---|
| Caller authentication | JWT/OAuth validation, client certificates, subscription keys theo cấu hình | HTTP trigger auth/connector connections | HTTP auth level, App Service auth/Entra theo hosting |
| Backend identity | Managed identity to backend/Key Vault theo tính năng | Managed identity/connection auth theo connector | System/user-assigned managed identity |
| Authorization nghiệp vụ | Có thể kiểm tra claims/policies; không thay mọi backend checks | Workflow conditions; phải kiểm tra business rights | Code/API layer kiểm soát resource permissions |
| Secrets | Named values/Key Vault integration | Secure connections/parameters/Key Vault | App settings/Key Vault references, managed identity |
| Network | Gateway endpoint, VNet/private networking theo tier | Consumption/Standard network khác nhau | Hosting plan/private endpoint/VNet integration |
| Logging | API gateway requests/policies/diagnostics | Run history/action outputs | App Insights/application logs |
| Rủi ro nổi bật | Backend bypass, public gateway, policy sai | Connector credentials/PII trong history, resubmit | Function key lộ, secret trong env/log, code CVEs |

### 22.1. Zero trust và danh tính

Một đường gọi giữa dịch vụ nên có những quyết định độc lập:

1. **Client → APIM**: JWT/mTLS/subscription policy phù hợp.
2. **APIM → Function/backend**: service-to-service authentication, private network hoặc backend restriction.
3. **Function → Service Bus/Storage/SQL**: managed identity và data-plane RBAC thấp nhất.
4. **Logic Apps → SaaS/ERP**: connection identity/service account với quyền tối thiểu.
5. **Operator → Azure resources**: Azure RBAC cấp quyền quản lý tách biệt khỏi quyền business data.

**Một Managed Identity được bật chưa tự có quyền** gọi Key Vault, Service Bus hay database. Cần gán role và kiểm tra permission scope.

### 22.2. Dữ liệu nhạy cảm trong workflow

Logic Apps có thể lưu trigger/action inputs và outputs trong run history theo cấu hình. Không ghi mật khẩu, token, số thẻ thanh toán hay PII không cần thiết vào:

- Workflow parameters plaintext.
- Connector outputs được log công khai.
- APIM trace/diagnostics.
- Function stdout.
- Application Insights custom events.
- Git, IaC templates hoặc deployment logs.

Dùng **secure inputs/outputs** khi cần, retention phù hợp và kiểm soát người xem run history. Không bật tracing payload chi tiết trên production chỉ để debug lâu dài.

## 23. Network topology và private connectivity

Một API được xác thực đúng vẫn có thể gặp vấn đề nếu đường mạng private không được thiết kế rõ.

### 23.1. Inbound và outbound là hai chiều khác nhau

- **APIM inbound:** caller đến gateway qua public hoặc private ingress theo tier/topology.
- **APIM outbound:** gateway gọi backend, cần DNS/route/auth tới Function/App Service/AKS.
- **Functions VNet Integration:** thường phục vụ **outbound từ Function app** vào VNet/dịch vụ private theo hosting plan.
- **Private Endpoint của Function:** phục vụ **private inbound** theo tính năng và cấu hình.
- **Logic Apps Standard networking:** có tùy chọn hosting/network khác Consumption.
- **Logic Apps connectors:** managed connector traffic có mô hình mạng riêng; không được suy rằng tất cả connectors đều tự chạy trong VNet của workflow.

### 23.2. Mẫu private integration

~~~mermaid
flowchart LR
    C["B2B client"] --> G["APIM gateway"]
    G -->|"Private backend route"| PE["Function private endpoint"]
    PE --> F["Azure Function API"]
    F -->|"VNet outbound / private DNS"| SQL["Azure SQL Private Endpoint"]
    F -->|"Managed identity"| KV["Key Vault"]
    F --> SB["Service Bus Private Endpoint"]
    SB --> LA["Logic Apps Standard<br/>workflow theo network design"]
    LA --> ERP["Internal ERP / SaaS"]
~~~

Đây là sơ đồ **mục tiêu**; tính khả thi thực tế phụ thuộc tier, SKU, region, subnet, Private DNS, gateway deployment, built-in/managed connectors và route/NAT requirements.

### 23.3. Những sai lầm phổ biến

- Chỉ bật VNet Integration rồi nghĩ Function không còn public inbound.
- Bật Private Endpoint mà quên private DNS zone/link.
- Chọn APIM tier không hỗ trợ đúng loại internal/external gateway cần dùng.
- Giả định Consumption Logic Apps có cùng khả năng VNet với Standard.
- Dùng managed connector tới hệ thống nội bộ mà không cấu hình on-premises gateway/hybrid connectivity khi cần.
- Cấp public firewall 0.0.0.0/0 để tạm vượt lỗi DNS.
- Không tính network egress/NAT/Firewall khi tính chi phí.

## 24. Monitoring, tracing và correlation

### 24.1. Vì sao cần correlation?

Một order đi qua:

~~~text
Partner POST
  → APIM request
  → HTTP Function
  → Service Bus command
  → Logic Apps workflow
  → Function transform
  → ERP
~~~

Nếu không có **operationId/traceId** xuyên suốt, operator phải đoán những logs rời rạc có liên quan không.

### 24.2. Đề xuất định danh

- **traceparent** hoặc W3C trace context cho request tracing theo SDK/transport hỗ trợ.
- **operationId** ổn định cho tác vụ bất đồng bộ.
- **eventId/messageId** ổn định cho idempotency.
- **workflowRunId** để liên kết Logic Apps run history.
- **externalOrderId** cho ERP/business reconciliation.

Không dùng cùng một ID cho mọi mục đích mà không hiểu semantics; một request có thể tạo nhiều messages và workflow runs.

### 24.3. Ba lớp telemetry

| Lớp | Tín hiệu |
|---|---|
| APIM | Total requests, p50/p95/p99 latency, 4xx/5xx, gateway/backend errors, throttling/quota |
| Logic Apps | Trigger runs, action success/failure/timeout, run duration, retries, connector throttling |
| Functions | Invocation count/duration, errors, dependencies, cold start indicators, memory/concurrency |
| Toàn kiến trúc | End-to-end completion SLO, backlog age, failed operations, DLQ, replay count, cost per completed workflow |

Azure Monitor, Application Insights và Log Analytics cần được cấu hình theo nhu cầu/plan; không mặc định chúng đã có đủ mọi metric, trace hay payload.

### 24.4. SLO theo business outcome

Một hệ thống API có **99.9% HTTP 202** chưa chắc tốt nếu 10% operations mắc kẹt ở ERP. Ví dụ SLO:

- 99% partner requests xác thực được xử lý ACK trong 2 giây.
- 99% accepted orders hoàn tất trong 5 phút.
- Không có order PENDING quá 15 phút mà không alert.
- 100% failed workflow có error reason/correlation đủ để triage.
- Chênh lệch số processed orders và source records trong biên độ kiểm soát.

Các con số trên là **mục tiêu minh họa**, không phải Azure service SLA.

## 25. So sánh chi phí có cấu trúc

### 25.1. Mô hình chi phí

| Thành phần | Đơn vị chi phí thường cần xem | Chi phí ẩn cần tính |
|---|---|---|
| **APIM** | Gateway tier/units/requests theo plan và cấu hình | Gateway capacity, diagnostics, private networking |
| **Logic Apps Consumption** | Triggers/actions/connector executions theo mô hình | Polling, retries, loops, managed connector calls |
| **Logic Apps Standard** | Hosting plan compute/storage, connectors/operations áp dụng | Always-on capacity, state storage, diagnostics |
| **Azure Functions** | Executions, duration/compute/memory, provisioned instances theo plan | Cold start mitigation, storage, logs, VNet/NAT |
| **Durable Functions** | Function executions, state/storage operations và hosting | History growth, retries, timers, telemetry |
| **Service Bus/Event Grid** | Messaging operations/events và tier | DLQ, retention, processing retries |
| **Azure Monitor** | Ingestion, retention, alerts | Verbose action logs, PII masking |
| **Network** | Private Endpoints, NAT, bandwidth/egress theo dịch vụ | Cross-region transfers, firewall |

**Không coi APIM là miễn phí chỉ vì API không có request**. Một số gateway tiers có phí provisioning/capacity. Cũng không coi Consumption Logic Apps luôn là một execution miễn phí khi flow có nhiều actions/retries.

### 25.2. Ví dụ tính số actions

Một Logic Apps workflow chạy **100.000 lần/tháng**, mỗi lần thành công thực thi:

- 1 trigger.
- 2 connector actions.
- 1 HTTP action.
- 1 condition.
- 1 notification action.

Số lần thực thi action lý tưởng là:

~~~text
100.000 workflow runs × 5 actions/run
= 500.000 action executions
~~~

Đây chỉ là **đếm hành động giả định**, chưa tính trigger pricing, connector categories, retry, polling, skipped actions, concurrency, Standard hosting và pricing meter của từng action. Condition/trigger cũng có thể được tính khác nhau tùy loại runtime/plan.

Nếu 20% các lần gọi ERP retry thêm hai lần, tổng số invocations thực tế vượt đáng kể dự toán đơn giản.

### 25.3. So sánh cost per completed operation

Một mô hình tốt hơn “phí mỗi request”:

~~~text
TCO / completed order
 = (APIM + Function + Logic Apps + messaging
    + database + storage + networking
    + logging + operations)
   / số orders thực sự hoàn tất
~~~

Hệ thống có nhiều retries, manual recovery và dead-letter có thể tăng phí dù traffic đầu vào không đổi. Theo dõi **cost per successful business transaction** và SLO, không tối ưu rời rạc từng service.

### 25.4. Khi không nên dùng cả ba

Nếu chỉ cần một Function Timer chạy hàng đêm, thêm APIM và Logic Apps có thể tăng vận hành, latency và cost mà không tạo giá trị.

Nếu chỉ dùng APIM để forward đến một Spring Boot backend hiện có, không cần chèn một Function vô ích vào giữa để “đúng serverless architecture”.

Nếu Logic Apps đã có connector/action đủ dùng và không có thuật toán đặc biệt, không cần Function “wrapper” cho mọi bước.

## 26. Reliability và hạn mức từng dịch vụ

### 26.1. APIM

- Capacity/throughput gateway theo tier; latency policies tăng theo cấu hình.
- Backend timeouts và connection failures.
- Retry policy với POST cần idempotency.
- Caching cần invalidation và tách dữ liệu nhạy cảm.
- Rate-limit/quota behavior cần xác minh ở gateway topology thật.
- HA/availability của gateway theo tier và deployment mode.

### 26.2. Logic Apps

- Workflow state, action count, run duration và trigger frequency theo plan.
- Connector-specific throttling/limits và authentication refresh.
- Polling triggers có latency/cost riêng.
- For each/concurrency có thể đẩy quá tải ERP.
- Retry/resubmit tạo duplicate effects nếu business logic không idempotent.
- Run history retention và dữ liệu nhạy cảm.
- Connection reference/built-in connector differences khi chuyển Consumption ↔ Standard.

### 26.3. Functions

- Hosting plan scaling/cold start và request timeout.
- Trigger/binding version compatibility.
- Queue lock/visibility timeout, poison queue/DLQ behavior theo từng broker.
- Application startup, JVM heap/thread pools.
- Stateless execution: instance có thể recycle.
- Durable Functions cần deterministic orchestrator, durable state, safe activity retries.
- Concurrency tối ưu theo downstream quotas, không phải số core đơn thuần.

### 26.4. Sự cố liên vùng

Nếu toàn region xảy ra sự cố, không một sản phẩm nào tự động bảo đảm kiến trúc đa region chỉ vì dùng PaaS. Cần thiết kế:

- APIM gateway instance/region routing phù hợp.
- Function apps hoặc backend được triển khai dự phòng.
- Logic Apps workflow deployment và state recovery strategy.
- Replication/restore cho database, messaging/storage.
- DNS/Front Door/Traffic Manager theo mô hình hỗ trợ.
- Secret/identity và private networking tại region phụ.
- Runbook failover, RPO/RTO và diễn tập thực tế.

## 27. Các mẫu anti-pattern cần tránh

| Anti-pattern | Vấn đề | Cách sửa |
|---|---|---|
| APIM chứa logic tính thuế và truy cập database nhiều bước | Policy khó test/maintain, gateway thành bottleneck | Đưa domain logic về Function/backend |
| Logic Apps For each hàng triệu records | Run phình to, throttling/memory/chi phí | Batch/stream engine hoặc Functions/Batch |
| Một Function HTTP giữ kết nối 30 phút | Timeout, resource pressure | 202 + durable queue + status |
| Dùng Function global static state làm workflow | Scale/restart làm mất state | Durable Functions/Logic Apps/DB |
| Logic Apps dùng user personal OAuth connection trên production | User rời công ty/expire token khiến flow dừng | Managed/service identity theo connector |
| APIM key là lớp bảo mật duy nhất | Key có thể bị chia sẻ/lộ, không có quyền user | OAuth/JWT/authorization nghiệp vụ |
| Function backend public không chặn direct access | APIM policy bị bypass | Private/restricted backend + service auth |
| Retry POST ERP không có idempotency | Giao dịch trùng | External business key, reconciliation |
| Workflow resubmit khi outcome chưa rõ | Chạy lại tác dụng phụ | Kiểm tra trạng thái, compensation |
| Monitor chỉ HTTP 200/202 | Không biết operation có hoàn tất không | End-to-end status, correlation và alert |
| Dùng cả ba service cho flow một bước | Thêm overhead/cost | Chọn dịch vụ đơn giản nhất đáp ứng yêu cầu |
| Hard-code API keys/connection strings vào IaC | Credential leakage | Key Vault, managed identity, secret references |
| Không version APIs/workflow contracts | Client và backend lỗi khi thay đổi | OpenAPI, schema version, backward compatibility |
| Không định nghĩa data ownership | Workflow gọi chéo và ghi đè database | Ownership rõ, event-driven integration |

## 28. Quy trình lựa chọn và review kiến trúc

### 28.1. Bước 1: mô tả business event/command

Ví dụ:

~~~text
Trigger: Partner sends new order HTTP POST
Identity: Partner application with Entra token
Response SLO: 2 seconds
Business completion SLO: 5 minutes
Downstream: ERP, payment provider, email
Approval: Sometimes, for high value orders
Peak: 300 requests/s
Data classification: Confidential
Network: Prefer private backend and managed identities
Failure handling: Idempotent retry, compensation, manual review
~~~

### 28.2. Bước 2: phân tách trách nhiệm

- API ingress/gateway governance → **APIM**.
- Ngắn hạn validate/enqueue → **Function** hoặc backend đã có.
- Async commands/events → **Service Bus/Event Grid** khi cần.
- SaaS connectors và approval → **Logic Apps**.
- Complex computation → **Function/Durable Functions hoặc app backend**.
- Durable business state → **database/workflow state**, không chỉ telemetry logs.

### 28.3. Bước 3: kiểm tra phi chức năng

- Availability/SLA, latency p95/p99.
- RTO/RPO, region/data residency.
- OAuth/mTLS/managed identity, private networking.
- Peak throughput, scale limits, runtime and connectors.
- Run history/log retention, data privacy.
- CI/CD, staging, rollback, DR.
- Budget theo một tháng và cost per completed operation.

### 28.4. Bước 4: thử failure modes

Ít nhất:

1. APIM gateway nhận token sai.
2. Backend Function bị timeout sau khi đã enqueue.
3. Service Bus redelivers cùng message.
4. ERP trả 429 trong 10 phút.
5. Logic Apps action thành công nhưng response bị mất.
6. Người phê duyệt không phản hồi trước deadline.
7. Function/Logic Apps scale-out xử lý cùng business key.
8. Private DNS lỗi khiến backend không truy cập SQL.
9. Workflow bị resubmit sau khi dữ liệu đã commit.
10. Một region/connector mất khả dụng.
11. Secrets hết hạn hoặc role assignment bị thu hồi.
12. Telemetry quá nhiều làm tăng chi phí và có nguy cơ lộ dữ liệu.

### 28.5. Bước 5: ra quyết định có điều kiện

Ví dụ kết luận:

> “Dùng APIM Premium hoặc tier đáp ứng private networking cho cổng B2B; Orders API hiện hữu trên App Service xử lý validate và queueing; Service Bus tách xử lý dài; Logic Apps Standard nếu workflow cần private connectors và approvals; một Azure Function Java thực hiện thuật toán đặc thù. Cần benchmark theo SKU, xác minh connector/region compatibility, áp OAuth/managed identity, thử idempotency và lập cost estimate trước production.”

Đây là **một mẫu lập luận**, không phải khuyến nghị bắt buộc về tier. Khi triển khai, phải chọn SKU cụ thể theo tính năng hỗ trợ và giá hiện hành.

## 29. Hướng dẫn thực hành Azure Portal có kiểm soát

Các bước sau dành cho môi trường lab được phê duyệt, không phải thao tác đã được thực hiện trong bài học.

### 29.1. Chuẩn bị

- Subscription và resource group riêng cho lab.
- Quyền Azure quản lý/tạo từng dịch vụ.
- Danh tính có quyền deploy nhưng không nhất thiết là subscription Owner.
- Budget/alert; biết các tier APIM có thể phát sinh phí gateway ngay khi không có request.
- Một Function App hoặc backend endpoint demo không chứa dữ liệu nhạy cảm.
- Một Logic App workflow test gửi đến endpoint/connector được duyệt.
- Application Insights/Azure Monitor theo chính sách.
- Kế hoạch xóa đúng resources lab.

### 29.2. Tạo Function trước

Trong Portal:

1. **Create → Function App**; chọn runtime hỗ trợ Java và hosting plan/region.
2. Xem cost/network/instance limits.
3. Deploy Function project từ CI/CD/IDE hoặc artifact được build.
4. Cấu hình App settings qua secret reference hoặc managed identity.
5. Test Function HTTP ở môi trường lab với body hợp lệ/không hợp lệ.
6. Ghi lại base URL, route, auth mechanism và deployment version.
7. Không gửi production credentials vào test payload.

### 29.3. Tạo API trong APIM

1. Tạo APIM instance/tier đáp ứng nhu cầu lab, đọc pricing cẩn thận.
2. Tạo **API** qua OpenAPI/HTTP hoặc thêm operation thủ công.
3. Khai báo backend Function URL.
4. Thêm policy validation/rate limiting thử nghiệm.
5. Kiểm tra auth, routing, status codes, backend errors.
6. Bảo vệ direct Function endpoint bằng phương án hỗ trợ.
7. Thử API từ caller không được cấp quyền và caller hợp lệ.
8. Quan sát request logs cùng correlation ID.

### 29.4. Tạo Logic App workflow

1. Tạo Logic App Consumption hoặc Standard theo kiến trúc lab.
2. Chọn trigger **Recurrence** hoặc HTTP/request khi phù hợp.
3. Thêm một HTTP action gọi Function/APIM endpoint.
4. Thêm condition và một nhánh Catch qua Scope/runAfter.
5. Cấu hình identity/connection/secrets.
6. Bật secure inputs/outputs cho nội dung nhạy cảm.
7. Chạy bằng dữ liệu mẫu, xem run history và lỗi.
8. Thử một action thất bại để xác nhận xử lý retry/alert.
9. Xác nhận không tạo side effect trùng khi resubmit.

### 29.5. Dọn lab

- Xác định APIM instance có phục vụ APIs khác không.
- Xác định Function App có chứa code/config cần giữ không.
- Logic Apps workflow có chạy recurrence và tạo phí tiếp không.
- Có Service Bus/Storage/App Insights/Key Vault phụ trợ không.
- Có private endpoint, NAT Gateway, custom DNS, Log Analytics hoặc connections dùng chung không.
- Chỉ xóa những tài nguyên dành riêng cho lab theo owner approval.

Không xóa nguyên resource group khi chưa kiểm tra bên trong có tài nguyên dùng chung.

## 30. Chẩn đoán sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| APIM trả 401 dù Function chạy trực tiếp | JWT issuer/audience/expiry sai | APIM validate-jwt policy, Entra app registration |
| APIM 403 | Policy/backend authorization, IP restriction, product subscription | APIM diagnostics, claims, backend access |
| APIM 429 | Rate-limit/quota | Counter key, limits và partner traffic |
| APIM 502/504 | Backend timeout/network/DNS/TLS | Gateway/backend logs và route |
| Function trực tiếp truy cập được, qua APIM không được | Backend network/auth hoặc policy | APIM trace, Function access restrictions |
| Function 401 do key | Function auth level/key sai | Key rotation, APIM named value |
| Function cold start chậm | Plan/instance startup/JVM initialization | Invocation latency, hosting plan, prewarming |
| Logic Apps trigger không chạy | Trigger config/poll interval/connection | Trigger history, connector auth |
| Logic Apps action 429 | SaaS throttling | Retry policy, concurrency, provider limits |
| Logic Apps Failed nhưng ERP đã tạo dữ liệu | Response lost/partial failure | Query external business key, idempotency |
| Function Service Bus trigger chạy lặp | Lock expires, redelivery/retry | Queue DLQ/delivery count, consumer idempotency |
| Logic Apps run history lộ payload | Secure outputs chưa bật, quyền rộng | Access control, retention, secure IO |
| Azure Function không gọi SQL private | VNet Integration/DNS/firewall | Effective route, private endpoint, identity |
| APIM private gateway không truy cập từ client | Route/DNS/tier/topology | Gateway network config và DNS |
| Logic Apps Standard network khác Consumption | Không tương thích connector/hosting | Kiểm tra plan và connection model |
| Chi phí tăng đột ngột | APIM tier, workflow retries, Functions scaling, logs | Cost Management theo resource/meter |

### 30.1. Debug APIM trước

1. Xác minh hostname, API path, HTTP method.
2. Xác định 401/403/429/5xx do gateway policy hay backend.
3. Kiểm tra token issuer/audience/scope/role hoặc subscription config.
4. Kiểm tra named values và key references.
5. Xác minh backend URL, DNS, private route và TLS.
6. So sánh direct backend trong đường mạng được phép với request qua APIM.
7. Xem diagnostics/tracing ở mức an toàn, không bật log payload bí mật.
8. Theo dõi latency gateway/backend.
9. Nếu backend đã commit nhưng gateway timeout, dùng idempotency/reconciliation.
10. Không tắt toàn bộ JWT validation như cách xử lý tạm không được phê duyệt.

### 30.2. Debug Logic Apps

1. Trigger đã thực sự được kích hoạt?
2. Connection/authentication có hợp lệ?
3. Run history dừng ở action nào?
4. Action Failed/TimedOut/Skipped và runAfter có đúng?
5. Retry count và thời điểm retry?
6. External API đã tạo side effect chưa?
7. Có concurrency race hoặc connector throttling?
8. Payload schema/size/encoding có thay đổi?
9. Secure inputs/outputs có chặn quan sát dữ liệu cần thiết (đúng kỳ vọng bảo mật)?
10. Cần repair/compensate hay resubmit idempotent?

### 30.3. Debug Functions

1. Trigger đã nhận request/event?
2. App/runtime/JDK version/dependencies phù hợp?
3. Invocation logs/exception/correlation ID?
4. Memory/CPU/cold start/concurrency?
5. Auth level/App Service auth/managed identity?
6. App settings và Key Vault references?
7. HTTP request timeout hay queue lock expiry?
8. Service Bus/Event Hubs/Storage role và network?
9. Kết quả nghiệp vụ đã durable commit chưa?
10. Có retry/duplicate effect hoặc poison message cần xử lý?

## 31. Checklist production

- [ ] Đã xác định API gateway, workflow orchestration và custom compute là ba trách nhiệm khác nhau.
- [ ] Không triển khai APIM/Logic Apps/Functions chỉ để làm kiến trúc phức tạp hơn.
- [ ] Đã chọn hosting plan/SKU phù hợp region, network, latency và tải thực tế.
- [ ] APIs có hợp đồng OpenAPI/versioning và owner.
- [ ] APIM xác thực JWT/OAuth hoặc cơ chế phù hợp; subscription key không thay authorization.
- [ ] Backend không bị bypass qua public endpoint không kiểm soát.
- [ ] Các Function/Logic Apps connections dùng identity/secret management phù hợp.
- [ ] Có thiết kế inbound/outbound VNet, private DNS và connector networking rõ ràng.
- [ ] Logic Apps stateful/stateless được chọn theo workflow duration/history needs.
- [ ] Có retry cap, dead-letter/manual review, compensation và trạng thái nghiệp vụ.
- [ ] HTTP long-running dùng 202 + durable enqueue + status API theo nhu cầu.
- [ ] Idempotency key được thiết kế cho HTTP POST, queue message và workflow actions.
- [ ] Không coi resubmit/retry là exactly-once business effect.
- [ ] Durable Functions orchestrator tuân thủ quy tắc deterministic/replay.
- [ ] Có correlation ID giữa APIM, Functions, Service Bus và Logic Apps.
- [ ] Monitoring đo business completion, không chỉ HTTP 200/202.
- [ ] Logs/run history không rò secrets hoặc dữ liệu nhạy cảm; retention được đặt.
- [ ] CI/CD và IaC quản lý runtime, policies, workflow definitions, connections.
- [ ] Có staging, tests cho lỗi mạng/timeout/429 và rollback.
- [ ] Có RTO/RPO và phương án DR của cả quy trình.
- [ ] Đã dự toán APIM tier, Logic Apps actions/hosting, Functions compute, messaging, logs và network.
- [ ] Đã thử incident runbook và thu hồi permissions/keys theo quy trình.

## 32. Bài tập thực hành

### Bài tập 1: Phân loại nhiệm vụ

Hãy chọn APIM, Logic Apps, Functions hoặc kết hợp trong sáu yêu cầu:

1. Public API cho 25 đối tác, cần JWT, quotas và developer portal.
2. Khi có email đính kèm, trích metadata, cập nhật CRM, thông báo Teams.
3. API tính toán cước vận chuyển bằng thuật toán Java 500 dòng.
4. Đợi lãnh đạo phê duyệt khoản mua hàng tối đa 72 giờ.
5. Một Java REST API đã chạy ổn trên AKS, chỉ cần public versioned endpoint.
6. Khi BlobCreated, kiểm tra schema rồi chuyển file sang JSON.

Giải thích vì sao không chọn các dịch vụ còn lại nếu không cần thiết.

### Bài tập 2: APIM và backend Function

1. Tạo Function HTTP lab trả JSON validation.
2. Thêm API/operation trong APIM.
3. Thiết kế JWT validation và rate limit.
4. Kiểm tra 401, 429 và request thành công.
5. Nêu cách chặn gọi trực tiếp backend.
6. Trình bày cách quản lý function key nếu dùng.
7. Ghi correlation ID qua APIM/Function.

### Bài tập 3: Logic Apps workflow

Thiết kế workflow khi invoice được upload:

- Trigger SharePoint/Blob.
- Validate schema.
- Gọi Function xử lý JSON/XML.
- Tạo invoice ở ERP.
- Nếu invoice quá ngưỡng, chờ approval.
- Gửi email/Teams.
- Khi ERP trả 429, retry có backoff và idempotency.
- Khi thất bại, Catch/alert/compensation.

Vẽ flow, chỉ ra action concurrency và nơi lưu business state.

### Bài tập 4: Async Orders API

Với **POST /orders** xử lý 3 phút:

1. Thiết kế APIM + HTTP Function + Service Bus + worker.
2. Định nghĩa HTTP 202, Location và operationId.
3. Bảo đảm enqueue durable trước ACK.
4. Dùng Idempotency-Key để tránh tạo trùng.
5. Viết state machine PENDING/PROCESSING/SUCCEEDED/FAILED.
6. Thiết kế retry khi worker crash sau DB commit.
7. Nêu cách giám sát SLO end-to-end.

### Bài tập 5: Logic Apps hay Durable Functions?

Một quy trình gồm 30 bước tính toán, fan-out tới 500 công việc song song, đợi external event tối đa 2 ngày và có 2 SaaS connectors.

Hãy đề xuất:

- Một thiết kế code-first Durable Functions.
- Một thiết kế Logic Apps + Functions.
- Cách chọn dựa trên team skill, state, observability, connectors, limits, testability và chi phí.
- Vì sao side effect của activity vẫn cần idempotency.

### Bài tập 6: Network và identity

Một công ty muốn APIM public nhưng backend Function/SQL/Service Bus private, Logic Apps cần gọi ERP qua đường riêng.

Hãy mô tả:

- Gateway inbound và backend outbound.
- Function private endpoint và VNet integration.
- Private DNS / NSG / firewall.
- Managed identity & RBAC của từng service.
- Khác biệt Logic Apps Standard/Consumption về networking.
- Cách kiểm thử không mở public access vô điều kiện.

### Bài tập 7: FinOps

Hệ thống có 200.000 API calls/tháng, 30.000 workflows, trung bình 8 actions/run, 10% actions gọi ERP retry một lần, Functions xử lý 100.000 executions.

Hãy lập bảng:

1. APIM plan và request workload.
2. Logic Apps actions/connector executions, cộng retries.
3. Functions executions/compute theo plan.
4. Service Bus, database, logs và networking.
5. Tổng chi phí trên **completed business operation**.
6. Khi nào bỏ APIM hoặc không cần Logic Apps để giảm complexity?

### Bài tập 8: Incident response

Một API trả HTTP 504, nhưng ERP đã tạo order. Client retry POST; Logic Apps cũng resubmit một run.

Hãy xác định:

- Các điểm có thể xảy ra duplicate side effects.
- Vai trò APIM, Function, Logic Apps và ERP trong điều tra.
- Idempotency/unique key ở đâu?
- Có thể resubmit tự động không?
- Cần kiểm tra trạng thái trước compensation thế nào?
- Các traces và logs nào là tối thiểu?

### Câu hỏi tự kiểm tra

1. APIM có phải môi trường tổng quát để chạy Java business code không?
2. APIM subscription key có thay OAuth/authorization của người dùng không?
3. Vì sao gateway phải bảo vệ backend khỏi direct access?
4. Khi nào cần API versioning và developer portal?
5. Logic Apps mạnh nhất trong loại quy trình nào?
6. Trigger khác action thế nào?
7. Sự khác nhau cơ bản giữa Logic Apps Consumption và Standard?
8. Stateful workflow khác stateless ở điểm nào?
9. Retry một HTTP POST tạo invoice có thể gây lỗi gì?
10. Logic Apps runAfter dùng để làm gì?
11. Resubmit một workflow có rollback những hệ thống ngoài không?
12. Khi nào Function HTTP là đủ, không cần APIM?
13. Function key có xác định quyền xem orderId không?
14. Azure Functions cold start phụ thuộc điều gì?
15. Khi nào nên dùng Durable Functions thay cho một HTTP Function đơn lẻ?
16. Vì sao orchestrator Durable Functions cần deterministic code?
17. API chạy hơn 3 phút nên có hợp đồng HTTP như thế nào?
18. Trả 202 trước khi message được lưu bền vững có rủi ro gì?
19. Vì sao callback hoặc event-driven trigger cần idempotency?
20. Managed identity có tự cấp quyền Service Bus hoặc Key Vault không?
21. VNet Integration có tự khóa public inbound Function không?
22. Vì sao managed SaaS connector không luôn có cùng network path với Logic Apps runtime?
23. SLO nào phù hợp để đo kết quả workflow hơn HTTP 200/202?
24. Chi phí APIM có thể tồn tại dù API không có traffic không?
25. Vì sao phải tính cost per completed operation, không chỉ cost per request?

## 33. Tài liệu tham khảo

- [Azure API Management overview — Microsoft Learn](https://learn.microsoft.com/azure/api-management/api-management-key-concepts)
- [Azure API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies)
- [APIM validate-jwt policy](https://learn.microsoft.com/azure/api-management/validate-jwt-policy)
- [APIM rate-limit-by-key policy](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy)
- [APIM authentication and authorization](https://learn.microsoft.com/azure/api-management/authentication-authorization-overview)
- [Azure Logic Apps overview](https://learn.microsoft.com/azure/logic-apps/logic-apps-overview)
- [Single-tenant versus multitenant Logic Apps](https://learn.microsoft.com/azure/logic-apps/single-tenant-overview-compare)
- [Managed and built-in connectors for Logic Apps](https://learn.microsoft.com/azure/connectors/apis-list)
- [Logic Apps run history and troubleshooting](https://learn.microsoft.com/azure/logic-apps/monitor-logic-apps)
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview)
- [Azure Functions hosting options](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java)
- [Azure Functions triggers and bindings](https://learn.microsoft.com/azure/azure-functions/functions-triggers-bindings)
- [Durable Functions overview](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview)
- [Durable Functions code constraints](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-code-constraints)
- [Azure Service Bus overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Microsoft Entra managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Azure API Management pricing](https://azure.microsoft.com/pricing/details/api-management/)
- [Azure Logic Apps pricing](https://azure.microsoft.com/pricing/details/logic-apps/)
- [Azure Functions pricing](https://azure.microsoft.com/pricing/details/functions/)

