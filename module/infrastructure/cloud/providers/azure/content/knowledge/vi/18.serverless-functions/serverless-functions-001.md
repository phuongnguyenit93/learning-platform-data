# Function App và mô hình thực thi Azure Functions

> **Chương:** Serverless với Azure Functions  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **Azure Functions**, **Function App**, **function**, **Functions host**, **language worker**, **trigger** và **binding**.
2. Trình bày vòng đời một invocation từ event source đến thực thi code, kết quả, logging và retry.
3. So sánh hosting plans **Flex Consumption, Consumption, Premium, Dedicated/App Service Plan** theo yêu cầu thực tế.
4. Giải thích **scale-out, concurrency, scale-to-zero, cold start, timeout**, tác động chi phí và hiệu năng.
5. Viết dự án **Python v2 programming model** gồm HTTP, Queue Storage và Timer triggers, chạy local và triển khai theo quy trình.
6. Phân biệt `host.json`, `local.settings.json`, application settings, Key Vault và managed identity.
7. Thiết kế xử lý **stateless, idempotent**, có timeout, retries và quan sát hoạt động.
8. Chẩn đoán trigger không chạy, lỗi quyền Storage, HTTP timeout, xử lý message trùng và thiếu telemetry.

## 1. Serverless giải quyết bài toán gì?

Một ứng dụng bán hàng cần làm ba việc: trả lời API `GET /api/hello`, xử lý đơn hàng mới trong hàng đợi và tạo báo cáo định kỳ mỗi giờ.

Nếu tự quản lý web server để luôn polling hàng đợi và chạy scheduler, nhóm vận hành phải quản lý tiến trình, thời gian hoạt động và tự lập logic scaling. **Azure Functions** là dịch vụ chạy code theo **sự kiện/trigger**, với runtime, bindings và các tùy chọn hosting do Azure cung cấp.

~~~mermaid
flowchart LR
    C["HTTP client"]
    Q["Azure Queue Storage\norders"]
    T["Timer schedule"]
    H["Functions host\ntrigger listeners"]
    A["HTTP function\nhello"]
    B["Queue function\nprocess_order"]
    D["Timer function\nhourly_cleanup"]
    DB["Database / Storage"]
    M["Application Insights"]
    C --> H
    Q --> H
    T --> H
    H --> A
    H --> B
    H --> D
    B --> DB
    D --> DB
    A -.-> M
    B -.-> M
    D -.-> M
~~~

Đây là luồng logic, không có nghĩa mọi trigger đều nhận sự kiện qua một queue chung. Mỗi loại trigger có **cơ chế nhận, xác nhận, retry và scale riêng**.

| Nhu cầu | Có thể dùng Functions? | Lưu ý |
| --- | --- | --- |
| HTTP API hoặc webhook nhỏ | Có | Quan tâm authentication, cold start, timeout |
| Xử lý file/event | Có | Chọn trigger và cơ chế event phù hợp |
| Xử lý đơn hàng async | Có | Queue + idempotency |
| Tổng hợp định kỳ | Có | Timer trigger và lịch UTC |
| Workflow cần chờ lâu, nhiều bước | Cân nhắc Durable Functions | Có state/checkpoint thay vì giữ HTTP request |
| WebSocket server stateful dài hạn | Không phải mặc định | Cần kiến trúc kết nối và trạng thái khác |
| Batch dài/GPU/vận hành rất tùy biến | Đánh giá dịch vụ khác | Kiểm tra giới hạn host/plan |

Serverless **không đồng nghĩa không có server, không có chi phí hoặc không cần vận hành**. Bạn vẫn phải quản lý code, quyền truy cập, dữ liệu, SLO và ngân sách.

## 2. Function, Function App và tài nguyên liên quan

### 2.1. Function là đơn vị xử lý

Một **function** là một entrypoint thực thi logic khi trigger thỏa điều kiện. Ví dụ `hello` nhận HTTP, `process_order` nhận Queue Storage message, `hourly_cleanup` chạy theo lịch.

**Mỗi function có đúng một trigger**, nhưng có thể dùng thêm input/output bindings hoặc Azure SDK.

### 2.2. Function App là ranh giới ứng dụng

**Function App** là tài nguyên Azure chứa nhiều functions có chung một số cấu hình và vòng đời triển khai:

~~~text
Resource group: rg-func-lab
Function App:   fn-orders-lab
  - hello
  - process_order
  - hourly_cleanup

Related:
  Storage Account: stfunctionslab001
  Application Insights: appi-func-lab
  Hosting plan: chọn theo nhu cầu
~~~

Một Function App thường dùng chung:

- Ngôn ngữ/runtime configuration và phiên bản Functions host.
- App settings, identity và kết nối được cấu hình cấp app.
- Deployment package, logging/instrumentation.
- Hosting plan và đặc điểm scaling theo plan/triggers.

Nếu HTTP API cần latency chặt chẽ còn queue consumer rất tốn CPU, nên cân nhắc **Function Apps riêng** để cách ly vòng đời deploy, scaling, quyền và giám sát. Ngược lại, gom những functions có cùng đặc điểm giúp giảm số resource phải vận hành.

### 2.3. Các thuật ngữ dễ nhầm

| Khái niệm | Ý nghĩa |
| --- | --- |
| Function | Code/entrypoint được trigger gọi |
| Function App | Tài nguyên ứng dụng và đơn vị triển khai/cấu hình |
| Azure Functions host/runtime | Nạp function metadata, quản lý triggers và bindings, điều phối invocations |
| Language worker | Tiến trình chạy mã Python/Node.js/.NET isolated… theo programming model |
| Host instance | Một đơn vị đang chạy Functions host |
| Invocation | Một lần gọi function |
| Hosting plan | Cách cấp compute, scaling, networking và tính phí |
| App Service Plan | Một mô hình compute dành cho ứng dụng; không đồng nghĩa mọi Function App đều dùng Dedicated plan |
| Application Insights | Thu thập telemetry; không phải runtime chạy function |

### 2.4. Function App không tự động là một function độc lập

Publish một project Function App thường có thể tác động **nhiều functions** trong đó. Một dependency lỗi lúc startup có thể khiến toàn app không index được functions. Tách Function Apps khi khác mức criticality, tốc độ deploy, workload hoặc yêu cầu IAM/egress; tránh tách quá vụn nếu không có lợi ích.

## 3. Azure Functions host và language worker hoạt động ra sao?

~~~mermaid
flowchart TD
    E["HTTP / Queue / Timer\nnguồn sự kiện"]
    X["Trigger listener / extension"]
    H["Functions host\nmetadata, binding, dispatch"]
    W["Language worker\nPython, .NET, JavaScript..."]
    F["Function code"]
    S["Azure SDK / output binding"]
    O["Logs, metrics, traces"]
    E --> X --> H --> W --> F --> S
    H -.-> O
    F -.-> O
~~~

**Vòng đời khái quát:**

1. Hosting platform khởi tạo Functions host instance.
2. Host đọc `host.json`, app settings, metadata và binding extensions.
3. Trigger listener hoặc cơ chế event source cung cấp sự kiện đủ điều kiện.
4. Host tạo invocation và chuyển dữ liệu tới language worker hoặc execution model tương ứng.
5. Code thực thi, gọi dependency và tạo kết quả.
6. Runtime/extension hoàn tất hoặc xử lý lỗi theo trigger semantics.
7. Telemetry được ghi khi đã cấu hình observability.
8. Platform có thể thêm/bớt host instances theo plan và tải.

### 3.1. Language worker và programming model

Python code thường chạy trong **language worker** tách khỏi host. .NET có các mô hình worker/in-process khác nhau; phải chọn đúng model và runtime còn được hỗ trợ. Điều này ảnh hưởng khả năng index, dependency loading, concurrency và cách viết bindings.

Nếu upload package thành công nhưng portal không liệt kê function:

- Sai layout hoặc thiếu `host.json`.
- `FUNCTIONS_WORKER_RUNTIME` không khớp.
- Import Python/dependency lỗi.
- Thiếu hoặc sai trigger extension.
- Trộn Python programming model v1 và v2 không đúng.
- Runtime/phiên bản ngôn ngữ không tương thích.

**Deployment thành công không chứng minh trigger đã được runtime index và lắng nghe.** Kiểm tra host startup logs và danh sách functions.

### 3.2. Một instance có thể chạy nhiều invocation

~~~text
Function App fn-orders-lab
  Host instance A:
    Invocation #101, #102
  Host instance B:
    Invocation #103, #104
~~~

Mỗi invocation **không phải** một VM mới. Một instance có thể xử lý nhiều invocations đồng thời tùy trigger, language runtime, concurrency settings và tài nguyên. Nhiều instances có thể cùng phục vụ một Function App.

Vì host instances có thể bị thay thế, **biến global, bộ nhớ hoặc thư mục tạm không phải nguồn trạng thái giao dịch tin cậy**.

### 3.3. Thực thi theo loại trigger không giống nhau

HTTP có response cho client. Queue Storage có visibility timeout/poison message. Event Hubs có partition/checkpoint. Timer có schedule monitor. **Retry, completion, scaling và bảo đảm thứ tự phụ thuộc trigger**, không có chính sách duy nhất cho toàn Azure Functions.


## 4. Trigger và binding: khi nào chạy, nhận và ghi gì?

### 4.1. Một function chỉ có một trigger

| Trigger | Nguồn sự kiện | Tình huống |
| --- | --- | --- |
| HTTP | HTTP request | API/webhook |
| Timer | Lịch NCRONTAB | Cleanup/báo cáo |
| Azure Queue Storage | Message ở queue | Xử lý đơn hàng |
| Azure Service Bus | Queue/subscription message | Messaging doanh nghiệp |
| Blob Storage | Blob event/change theo khả năng | Thumbnail/OCR |
| Event Grid | Event publisher | Event-driven workflow |
| Event Hubs | Event stream theo partition | Telemetry ingestion |
| Cosmos DB | Change feed | Đồng bộ/projection |

Mỗi trigger có **semantics retry, completion, payload và scale riêng**. Không gắn HTTP và Queue trigger lên cùng một function. Có thể tạo hai functions riêng cùng gọi chung logic nghiệp vụ.

### 4.2. Input/output binding

**Input binding** giúp runtime cung cấp dữ liệu từ dịch vụ được hỗ trợ; **output binding** giúp ghi kết quả đến đích được extension hỗ trợ. Với logic phức tạp, gọi Azure SDK trực tiếp vẫn là lựa chọn phù hợp.

~~~mermaid
flowchart LR
    H["create_order\nHTTP trigger"]
    Q["Storage Queue\norders"]
    F["process_order\nQueue trigger"]
    D["SQL / Cosmos DB\nSDK"]
    O["Optional output binding\nStorage / queue"]
    H -->|enqueue| Q --> F --> D
    F --> O
~~~

Bindings không tự bảo đảm **distributed transaction nguyên tử** giữa queue và database. Nếu database ghi thành công nhưng function crash trước khi message hoàn tất, invocation có thể lặp; cần idempotency.

### 4.3. Binding extension và connection name

Trong Python code, giá trị `connection="OrdersStorage"` là **tên cấu hình**, không phải chuỗi bí mật. Runtime tìm application setting `OrdersStorage` hoặc các settings dùng tiền tố tương ứng khi dùng identity-based connection.

Có thể có:

- `AzureWebJobsStorage`: kết nối host storage phục vụ những chức năng vận hành runtime.
- `OrdersStorage`: connection riêng tới Queue Storage nghiệp vụ.

Không nhầm hai vai trò này, cũng không buộc dùng cùng một tài khoản cho mọi môi trường. Phải kiểm tra extension version, quyền dữ liệu và networking.

## 5. Vòng đời HTTP, Queue và Timer

### 5.1. HTTP

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant P as Functions Frontend
    participant H as Host
    participant W as Worker
    C->>P: GET /api/hello
    P->>H: Route + auth
    H->>W: Invocation
    W-->>H: HttpResponse
    H-->>P: status, headers, body
    P-->>C: HTTP 200
~~~

HTTP trigger cần input validation, HTTP status đúng, authentication/authorization, timeout, logging và xử lý dependency. HTTP request **không có cơ chế retry tự động như Queue trigger**; client/gateway có thể tự retry tùy cấu hình và phải bảo vệ tính idempotent.

Authorization levels thường gồm:

- `anonymous`: runtime không đòi function key; endpoint không tự được bảo mật.
- `function`: có thể yêu cầu function key hợp lệ, là shared secret.
- `admin`: quyền rộng hơn, không thích hợp làm public client key.

Function key không thay OAuth/JWT, Microsoft Entra ID, App Service Authentication hoặc API authorization nghiệp vụ. Không ghi function/admin keys vào URL public và source code client.

### 5.2. Queue trigger và redelivery

Với message `order-123`:

1. Queue trigger listener nhận message.
2. Runtime dispatch invocation.
3. Code xử lý và cập nhật state.
4. Khi thành công, extension hoàn tất message theo queue semantics.
5. Nếu thất bại, message có thể khả dụng lại sau visibility timeout/retry.
6. Sau nhiều lần lỗi, Storage Queue trigger có thể đưa message vào **poison queue** theo extension/host settings.

Thiết kế **at-least-once safe**: dùng `orderId`/message ID làm idempotency key, unique constraint hoặc state machine; có retry giới hạn và quy trình xử lý poison messages. Tránh thu tiền/gửi notification lặp khi cùng message được gọi lại.

### 5.3. Timer trigger

Azure Functions Timer dùng biểu thức **NCRONTAB sáu trường**:

~~~text
{second} {minute} {hour} {day} {month} {day-of-week}
~~~

| Schedule | Ý nghĩa |
| --- | --- |
| `0 */5 * * * *` | Mỗi 5 phút |
| `0 0 * * * *` | Đầu mỗi giờ |
| `0 0 2 * * *` | 02:00 hàng ngày theo timezone |
| `0 0 9 * * 1-5` | 09:00 thứ Hai–thứ Sáu |

Timezone thường mặc định UTC. Một số Linux/serverless plans **không hỗ trợ đổi timezone bằng `WEBSITE_TIME_ZONE`** như trên một số môi trường khác; nên giữ UTC, quy đổi lịch và kiểm thử. Timer không cam kết chạy đúng mili giây nếu host khởi động lại.

### 5.4. So sánh behavior

| Khía cạnh | HTTP | Queue | Timer |
| --- | --- | --- | --- |
| Client chờ? | Thường có | Không | Không |
| Kết quả | HTTP response | Message completion/retry | Không có HTTP response |
| Retry | Client/app tự quyết định | Extension, visibility/poison | Timer/host schedule monitor riêng |
| Dữ liệu đầu vào | Method, headers, body | Message/metadata | Timer info |
| Thiết kế quan trọng | Auth, status, latency | Idempotency, poison handling | Timezone, overlap, monitoring |

### 5.5. HTTP job chạy lâu

Nếu xử lý 10.000 ảnh mất 30 phút, không nên giữ HTTP request mở 30 phút. **Function timeout và HTTP frontend timeout là hai giới hạn khác nhau**; dù `functionTimeout` có thể cho execution lâu theo plan, frontend/client có thể hết thời gian trước.

Mẫu bất đồng bộ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP function
    participant Q as Queue
    participant W as Queue function
    participant DB as Job state store
    C->>H: POST /api/jobs
    H->>DB: Create jobId, status=pending
    H->>Q: Enqueue jobId
    H-->>C: 202 Accepted + status URL
    Q->>W: Dispatch jobId
    W->>DB: Update processing/done/failed
    C->>H: GET /api/jobs/{id}
    H->>DB: Read job status
    H-->>C: Status + result
~~~

Có thể dùng **Durable Functions async HTTP pattern** nếu cần điều phối/persistence/replay, nhưng đó là workflow riêng phải cấu hình.

## 6. Các hosting plans cho Function App

Azure Functions hỗ trợ nhiều mô hình cấp compute. **Region, runtime, OS, versions, quotas và chính sách giá thay đổi**, phải xác minh compatibility trước khi chọn.

| Hosting | Định hướng | Đánh đổi |
| --- | --- | --- |
| **Flex Consumption** | Serverless, scale linh hoạt và cấu hình memory/always-ready theo khả năng | Cold start, region/trigger support, tính phí execution/always-ready |
| **Consumption** truyền thống | Serverless có thể scale-to-zero trong điều kiện hỗ trợ | Giới hạn runtime/OS/network, cold start, định hướng kế hoạch mới |
| **Elastic Premium** | Compute prewarmed/always-ready, phù hợp latency và network requirements | Chi phí nền, instance/SKU quotas |
| **Dedicated (App Service Plan)** | Compute provisioned, workload luôn chạy hoặc plan có headroom | Chi phí khi idle, tier/Always On và scaling plan |
| **Azure Container Apps hosting** | Functions chạy trên hạ tầng/container app model được hỗ trợ | Cần đánh giá trigger, ingress, revision, scaling và billing |

Không mặc định tất cả plans hỗ trợ mọi ngôn ngữ và network configurations như nhau.

### 6.1. Flex Consumption

Là lựa chọn serverless cần xem xét cho project mới khi vùng/ngôn ngữ tương thích:

- Scale dựa trên tải của trigger; một số triggers có khả năng scale riêng hoặc theo nhóm.
- Chọn memory/instance capabilities trong giới hạn hỗ trợ.
- **Always-ready instances** khi cần giảm cold start và có chấp nhận chi phí nền.
- VNet integration theo yêu cầu và điều kiện của plan.
- Billing theo mô hình của Flex, có thể gồm execution và always-ready resources.

Không coi Flex là “mọi thời điểm đều 0 instance” nếu đã cấu hình always-ready. Phải kiểm tra mô hình tính phí riêng.

### 6.2. Consumption truyền thống

Có thể scale-to-zero, phù hợp nhiều workload event-driven đã triển khai. Nhưng phải xét giới hạn tính năng, cold start, timeout, OS/runtime và lộ trình hỗ trợ tại thời điểm chọn. Không bê nguyên tutorial cũ sang production mà không kiểm tra lựa chọn Flex.

### 6.3. Elastic Premium

Giữ/prewarm compute theo plan giúp giảm thời gian khởi tạo, hữu ích với API cần latency ổn định hoặc cấu hình VNet/network đặc thù. Tuy nhiên thường có mức **compute cost nền**, quota và giới hạn instances. Premium không thay thế tối ưu dependency.

### 6.4. Dedicated App Service Plan

Compute theo plan provisioned, có thể phù hợp khi workload tải cao liên tục hoặc plan đang còn headroom. Xem `Always On`, SKU/tier và việc nhiều apps chia sẻ compute. Manual/autoscale ở plan khác scale-to-zero kiểu serverless.

### 6.5. Lựa chọn theo SLO

- HTTP traffic ít và chấp nhận cold start → cân nhắc Flex/Consumption theo hỗ trợ.
- API latency nhạy, request không đều → so sánh Flex always-ready với Premium.
- Queue consumer peak cao → đánh giá event-driven scaling, max instances và backend quota.
- App chạy liên tục và đã có Dedicated plan → so sánh tổng chi phí với serverless.
- Dịch vụ containerized trong kiến trúc Container Apps → đánh giá Functions trên ACA khi hỗ trợ.

## 7. Scaling, concurrency và cold start

### 7.1. Scale-out không giống concurrency

**Scale-out** thêm host instances. **Concurrency** là số invocations đang chạy đồng thời trong một instance/worker theo trigger/plan.

~~~text
Load thấp:
  Host A → 2 invocations

Load cao:
  Host A → 5 invocations
  Host B → 5 invocations
  Host C → 5 invocations
~~~

Con số chỉ minh họa. Concurrency chịu ảnh hưởng CPU, memory, Python async/thread worker, queue batch size, prefetch, trigger/plan configuration. **Không có bảo đảm một invocation cần một host instance riêng**.

### 7.2. Ước lượng theo Little's Law

Nếu ứng dụng nhận 100 invocations/giây và mỗi invocation mất trung bình 0,2 giây:

\[
L=\lambda W=100\times0{,}2=20
\]

Có khoảng 20 invocations in-flight theo mô hình ổn định. Nếu một instance xử lý an toàn 5 invocations đồng thời, ước tính tối thiểu 4 instances trước headroom. Đây **không phải thuật toán scaling chính xác của Azure**, còn latency đuôi, burst, cold start và backend.

### 7.3. Cold start

**Scale-to-zero** cho phép giảm compute khi idle theo plan. **Cold start** là thời gian khởi tạo host, load runtime/dependencies, index functions và sẵn sàng nhận invocation.

Tác nhân:

- Package/dependencies quá lớn.
- Import SDK nặng và kết nối mạng ngay khi module import.
- Trigger extensions/host initialization.
- Khởi tạo resources, cấu hình secrets và private endpoints.
- Tải bất chợt phải tạo thêm instances.

Đánh giá p95/p99 latency bao gồm **request đầu**. Tối ưu import/startup; cân nhắc always-ready hoặc Premium khi SLO đòi hỏi. Không coi ping endpoint liên tục là giải pháp thay thế có kiểm soát chi phí.

### 7.4. Timeout

`functionTimeout` trong `host.json` kiểm soát thời gian invocation theo khả năng của plan. Các plans có defaults/max khác nhau và một số ngoại lệ; **không dùng một số phút cố định cho mọi môi trường**.

HTTP còn có giới hạn ở frontend/load balancer/client. Với job dài, dùng queue, Durable Functions hoặc giải pháp batch thay vì giữ request đồng bộ.

### 7.5. Downstream bottlenecks

Scale từ 2 lên 20 instances có thể tăng đồng thời SQL connections, Cosmos DB RU/s, Storage requests và API rate limit. Không tăng max instances trước khi xem:

- Throughput và latency backend.
- Connection pool/retry/backoff.
- Tính idempotent khi event bị retry.
- Chi phí compute, networking và logging.

**Scale-out Functions không làm backend tự tăng quota.**


## 8. Ví dụ tự chứa: một Function App với ba triggers (Python v2)

Ta xây ứng dụng `orders-functions` gồm:

- `hello`: HTTP GET `/api/hello`.
- `process_order`: xử lý message từ Storage Queue `orders`.
- `hourly_cleanup`: log kiểm tra định kỳ đầu mỗi giờ.

**Mục đích:** minh họa programming model, runtime discovery và cách ba triggers cùng tồn tại trong một Function App. Phần xử lý đơn hàng là mô phỏng: không thực hiện thanh toán hoặc ghi dữ liệu thật.

### 8.1. Cấu trúc project

~~~text
orders-functions/
  function_app.py
  host.json
  requirements.txt
  local.settings.json      # Không commit secrets/credentials
  .funcignore              # Tùy chọn loại file khi publish
~~~

Ở Python **v2 programming model**, decorators trong `function_app.py` mô tả functions và bindings; không nhất thiết cần một `function.json` viết tay cho từng function như model cũ.

### 8.2. `function_app.py`

~~~python
import json
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="hello", methods=["GET"])
def hello(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger: trả lời nhanh, không chạy job dài."""
    name = req.params.get("name", "bạn")
    return func.HttpResponse(
        f"Xin chào, {name}!",
        status_code=200,
        mimetype="text/plain; charset=utf-8",
    )


@app.queue_trigger(
    arg_name="msg",
    queue_name="orders",
    connection="OrdersStorage",
)
def process_order(msg: func.QueueMessage) -> None:
    """Queue trigger: minh họa việc đọc orderId và logging."""
    try:
        payload = json.loads(msg.get_body().decode("utf-8"))
        order_id = payload["orderId"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        logging.error("Message đơn hàng không hợp lệ")
        raise ValueError("Invalid order message") from exc

    logging.info("Processing order %s", order_id)

    # Ứng dụng thật:
    # 1) Kiểm tra orderId bằng database/unique constraint
    # 2) Chỉ tạo side effect khi đơn chưa được xử lý
    # 3) Ghi trạng thái và telemetry có kiểm soát
    # Không coi ví dụ log này đã có idempotency.


@app.timer_trigger(
    schedule="0 0 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def hourly_cleanup(timer: func.TimerRequest) -> None:
    """Timer trigger: chạy đầu mỗi giờ theo timezone của host."""
    if timer.past_due:
        logging.warning("Hourly task chạy trễ")
    logging.info("Hourly cleanup tick")
~~~

**Giải thích:**

- `FunctionApp` là đối tượng đăng ký functions trong Python v2.
- `@app.route` tạo HTTP trigger và route `hello`.
- `@app.queue_trigger` gắn Queue Storage trigger; `OrdersStorage` là **tên connection setting**.
- `@app.timer_trigger` chạy theo lịch, có thể nhận `past_due`.
- Không có request HTTP nào tự động tạo queue message trong ví dụ; chúng là **ba nguồn trigger độc lập**.
- Ứng dụng chỉ `logging.info` khi queue có message, chưa ghi database và chưa có cơ chế idempotency thật.

Với production, xử lý input validation, security, data contract, exception classification và idempotency trước khi dùng.

### 8.3. `requirements.txt`

~~~text
azure-functions
azure-storage-queue
~~~

`azure-functions` phục vụ runtime programming model; `azure-storage-queue` được dùng cho script gửi message thử ở mục 9. Trong dự án production, **pin versions** từ lock/dependency policy và kiểm thử runtime compatibility; không để mọi dependency tự trôi phiên bản.

### 8.4. `host.json`

~~~json
{
  "version": "2.0",
  "functionTimeout": "00:05:00",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  },
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  }
}
~~~

Các trường minh họa:

- `version: "2.0"` là **schema version của host.json**, không phải “Azure Functions runtime v2”; runtime phổ biến cho Python v2 model là Functions v4 theo hỗ trợ.
- `extensionBundle` giúp runtime có binding extensions tương thích như Queue Storage.
- `functionTimeout` phải nằm trong giới hạn **hosting plan**; 5 phút ở đây chỉ để thử.
- `samplingSettings` giảm một số telemetry theo cấu hình. Khi debug lỗi hiếm, xem tác động sampling để không kết luận thiếu request từ một tập log đã bị sampling.

### 8.5. `local.settings.json` cho Azurite

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "OrdersStorage": "UseDevelopmentStorage=true"
  }
}
~~~

**Đây chỉ là cấu hình local** dùng Azure Storage emulator **Azurite**. Trước khi chạy, phải bật Azurite với Blob/Queue/Table endpoints thích hợp theo nhu cầu host/extensions. Không đưa `UseDevelopmentStorage=true` lên Azure production; Azurite không phải Azure Storage thật.

`local.settings.json` có thể chứa credentials trong dự án khác và thường không được publish; **không commit file này vào repository chứa secret**. Ở Azure, dùng Function App application settings/Key Vault và managed identity phù hợp.

### 8.6. Những thay đổi an toàn để mở rộng ví dụ

Nếu muốn `hello` tạo công việc thật:

1. Tạo endpoint POST riêng, validate payload và identity.
2. Sinh `jobId` với khóa idempotency; lưu trạng thái.
3. Gửi message tới queue bằng SDK với quyền write phù hợp.
4. Trả HTTP `202 Accepted` cùng `jobId` và status URL.
5. Queue-triggered function xử lý, retry và cập nhật trạng thái.

Không biến `GET /api/hello` thành hành động thu tiền hay thay đổi dữ liệu; GET nên là thao tác đọc theo HTTP semantics.

## 9. Chạy local: Functions Core Tools và Azurite

### 9.1. Điều kiện cần

- Python version được Functions runtime và local Core Tools hỗ trợ.
- **Azure Functions Core Tools v4** tương thích.
- Một virtual environment và dependencies được cài.
- Azurite đang chạy để host storage và queue triggers có thể kết nối.
- Kết nối Internet khi lần đầu tải extension bundle/packages nếu cần.

Ví dụ lệnh trong **Bash/Linux/macOS** khi đã có các công cụ trên:

~~~bash
# Tại thư mục project orders-functions:
python -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt

# Bảo đảm Azurite đang chạy trong terminal/process khác.
func start
~~~

Trên Windows PowerShell, lệnh kích hoạt virtual environment khác Bash; dùng lệnh tương ứng hệ điều hành. Nếu Core Tools báo lỗi Storage emulator, kiểm tra endpoint Azurite, port, firewall và `AzureWebJobsStorage`.

### 9.2. Khởi tạo project mới thay vì chép cấu trúc thủ công

Nếu tạo từ đầu, Core Tools hỗ trợ init Python v2 project theo phiên bản:

~~~bash
func init orders-functions --worker-runtime python --model V2
~~~

Sau đó thêm `function_app.py` và các settings mẫu. **Không chạy init bên trong thư mục project chứa file cần giữ** mà chưa xác minh nó không overwrite. Dùng `func init --help` nếu phiên bản Core Tools yêu cầu cú pháp khác.

### 9.3. Kiểm thử HTTP

Thông thường route prefix là `/api` khi host chưa đổi:

~~~bash
curl -i "http://localhost:7071/api/hello?name=Mai"
~~~

Kỳ vọng HTTP 200 và nội dung:

~~~text
Xin chào, Mai!
~~~

**Local host có thể không thực thi authorization checks giống endpoint Azure**, tùy Core Tools và cấu hình. Không dùng kết quả test local để kết luận endpoint production đã được bảo vệ.

### 9.4. Gửi Queue message bằng Python SDK

Sau khi đã cài `azure-storage-queue` và bật Azurite, có thể chạy **đoạn mã minh họa trên máy lab**:

~~~python
import json
from azure.storage.queue import QueueClient

queue = QueueClient.from_connection_string(
    conn_str="UseDevelopmentStorage=true",
    queue_name="orders",
)

queue.create_queue()
queue.send_message(json.dumps({"orderId": "order-123"}))

print("Đã gửi message mẫu vào queue orders")
~~~

Nếu queue đã tồn tại, `create_queue()` có thể báo conflict; xử lý riêng trường hợp đó hoặc tạo queue một lần trước. **Đừng chạy script gửi message vào queue production** nếu không có quyền và quy trình phê duyệt.

Khi listener nhận được message, `process_order` ghi log `Processing order order-123`. Nếu message không phải JSON hoặc thiếu `orderId`, function ném lỗi và có thể được trigger gọi lại theo semantics queue.

### 9.5. Kiểm thử Timer

`hourly_cleanup` chạy đầu mỗi giờ theo schedule. Để thử nhanh trong **lab**, có thể đổi lịch thành `0 */1 * * * *` (mỗi phút), restart host và quan sát log. Trả lại schedule production trước khi deploy. Không đặt `run_on_startup=True` để “cưỡng ép” job production chạy ngay mỗi lần host recycle, vì có thể gây xử lý ngoài lịch.

### 9.6. Dấu hiệu local host khởi động đúng

Bạn nên thấy:

- Host startup không báo lỗi cấu hình Storage.
- Danh sách functions gồm `hello`, `process_order`, `hourly_cleanup`.
- HTTP route `/api/hello` có thể gọi.
- Queue message được xử lý khi Azurite có message.
- Timer được host nhận diện theo lịch.
- Logs rõ ràng nhưng không lộ secret.

Nếu host chỉ hiển thị một function, kiểm tra decorators, imports và binding extension, đừng vội kết luận queue không có message.

## 10. Ba lớp cấu hình: host.json, app settings và code

### 10.1. `host.json`

Áp dụng những cấu hình ở cấp Functions host như:

- Log levels/sampling/telemetry trong phạm vi hỗ trợ.
- `functionTimeout` theo giới hạn plan.
- Extension bundle và một số cấu hình triggers/concurrency.
- Một số cài đặt host-wide, không phải dữ liệu nghiệp vụ cụ thể của mỗi khách hàng.

Không lưu password hoặc connection string trực tiếp trong `host.json`.

### 10.2. `local.settings.json`

- Dùng cho **local development**.
- Có `Values` cho env/app settings.
- Có thể chứa secret và thường cần loại khỏi version control.
- Không được mặc định đồng bộ lên Azure khi deploy.

### 10.3. Azure Function App application settings

Khi chạy trên Azure, app settings được cung cấp cho runtime/ứng dụng như environment variables (cách expose tùy platform). Ví dụ:

~~~text
FUNCTIONS_WORKER_RUNTIME=python
AzureWebJobsStorage=<cấu hình host storage hợp lệ>
OrdersStorage__queueServiceUri=https://<account>.queue.core.windows.net
APPLICATIONINSIGHTS_CONNECTION_STRING=<chuỗi kết nối Application Insights>
~~~

Đây là mẫu **minh họa, không phải cấu hình đầy đủ có thể dán nguyên vào mọi plan**. Với identity-based connections, phải kiểm tra extension version và data-plane RBAC cho identity, có thể cần thêm các URI/service settings khác cho host storage tùy cấu hình.

**Không in giá trị bí mật** ra terminal logs và không chia sẻ production connection strings qua chat.

### 10.4. Configuration scope và deployment

Thay một app setting có thể khiến Function App/host restart và ảnh hưởng invocations đang chạy. Đổi `host.json` cần publish package mới. Thay code/requirements có thể gây cold start hoặc lỗi indexing.

Phân biệt:

| Thay đổi | Hệ quả có thể |
| --- | --- |
| Sửa function code | Build/deploy và host reload |
| Thêm dependency | Dependency install, image/package size tăng |
| Đổi `FUNCTIONS_WORKER_RUNTIME` | Có thể không index được code nếu không khớp |
| Đổi Storage connection | Trigger listeners có thể lỗi quyền/kết nối |
| Đổi `functionTimeout` | Phụ thuộc hosting plan, cần deploy host configuration |
| Đổi app setting | Có thể restart và ảnh hưởng concurrent invocations |
| Đổi identity/RBAC | Cần propagation, không tự cấp quyền qua code |

## 11. Quyền truy cập Storage, Identity và Secrets

### 11.1. Host storage và workload storage không nhất thiết giống nhau

**AzureWebJobsStorage** là cấu hình host storage dùng cho những nhu cầu vận hành của Functions runtime/extensions theo khả năng. Một số trigger/hosting behaviors sử dụng storage để lease, coordination hoặc tracking. **OrdersStorage** là kết nối tới queue nghiệp vụ.

Không để người học hiểu rằng “chỉ cần FUNCTIONS_WORKER_RUNTIME=python là đủ” để Queue/Timer triggers hoạt động ở mọi môi trường. Cần Storage connection/host configuration hợp lệ.

### 11.2. Managed identity và data-plane RBAC

Ở Azure, ưu tiên dùng system-assigned hoặc user-assigned managed identity để truy cập Storage/Key Vault theo khả năng hỗ trợ. Một số ví dụ quyền:

| Nhu cầu | Quyền/cơ chế cần đánh giá |
| --- | --- |
| Host storage | Các data actions/roles cần theo trigger và hosting |
| Đọc message từ Storage Queue | `Storage Queue Data Message Processor` hoặc quyền data-plane tương ứng |
| Gửi message vào queue | `Storage Queue Data Message Sender` hoặc role tương ứng |
| Đọc Blob | `Storage Blob Data Reader` khi phù hợp |
| Đọc Key Vault secret | Role `Key Vault Secrets User` hoặc cơ chế access policy phù hợp |
| Deploy Functions | Quyền control-plane phù hợp, khác quyền data-plane |

**Gắn identity không tự cấp Storage Queue permissions.** RBAC ở scope storage account/queue, networking và firewall đều phải cho phép luồng. Khi dùng Queue trigger, role phải đủ để xử lý và hoàn tất message theo yêu cầu extension.

### 11.3. Identity-based connection

Với Storage Queue extension hỗ trợ identity-based connections, các settings dạng:

~~~text
OrdersStorage__queueServiceUri=https://mystorage.queue.core.windows.net
~~~

giúp runtime lấy endpoint mà không cần chuỗi account key. Cần đảm bảo:

1. Function App đã bật managed identity.
2. Identity có data-plane role đúng.
3. Storage network/firewall/Private Endpoint cho phép traffic.
4. Trigger extension hỗ trợ connection bằng identity.
5. Host storage `AzureWebJobsStorage` cũng được cấu hình đúng (có thể khác).
6. Đã kiểm tra permissions propagation.

Nếu chỉ thấy HTTP function chạy nhưng Queue trigger không hoạt động, đừng tắt firewall hay dùng account key quyền rộng để chữa tạm. Đọc log để xác định thiếu connection setting, thiếu role, network hay queue.

### 11.4. Key Vault và bảo vệ bí mật

- Không commit `local.settings.json` chứa secrets.
- Dùng Key Vault references hoặc SDK với managed identity khi phù hợp.
- Không đưa function keys, access tokens, password vào response/log.
- Khi rotation secret, kiểm tra ứng dụng đã nhận bản mới chưa; có thể cần restart theo cách app/runtime cache config.
- Giới hạn quyền của CI/CD principal và function identity; không cấp Owner subscription chỉ để đọc Queue.

**Network security và RBAC là hai kiểm tra riêng:** có quyền trong Azure RBAC nhưng Private Endpoint/DNS không hoạt động thì trigger vẫn lỗi kết nối; ngược lại network thông nhưng thiếu data rights vẫn bị từ chối.


## 12. Triển khai Function App lên Azure có kiểm soát

### 12.1. Chọn kiến trúc trước khi tạo

Trước khi tạo Function App, xác định:

- Subscription, resource group và region.
- Runtime/language version và Functions host version được hỗ trợ.
- Hosting plan phù hợp SLO/cold start/networking.
- Storage Account và loại kết nối host storage.
- Application Insights/Log Analytics destination.
- Managed identity và quyền data-plane tới Storage/SQL/Key Vault.
- Inbound auth và outbound networking (VNet/Private Endpoint nếu cần).
- Environment variables, secrets và phương pháp CI/CD.
- Chính sách chi phí, quota, alert và rollback.

**Không copy lệnh tạo Function App của Consumption truyền thống cho Flex Consumption** khi CLI/hosting options khác. Với project mới, kiểm tra workflow tạo của hosting plan hiện hành trong portal/CLI, thay vì đoán tham số `az functionapp create`.

### 12.2. Tạo bằng Azure portal (khung quy trình)

1. Mở Azure portal, chọn **Function App → Create**.
2. Chọn subscription, resource group, tên ứng dụng duy nhất, region và runtime/language phù hợp.
3. Chọn hosting option/tier theo workload và vùng hỗ trợ.
4. Cấu hình storage, networking, logging và Application Insights.
5. Bật managed identity nếu cần; cấp RBAC **ở đúng resource scope**.
6. Khai báo application settings và Key Vault references cần thiết, không dùng credentials local.
7. Tạo app, chờ provisioning và kiểm tra endpoint/configuration.
8. Deploy code qua phương thức được hỗ trợ cho **đúng plan**; xác nhận functions đã được index.
9. Chạy smoke tests, kiểm tra logs và metrics.
10. Tạo alerts, budget và deployment/rollback procedure trước khi mở traffic production.

**Lưu ý:** Tạo Function App và Storage/Insights có thể phát sinh phí. Một Function App đã tạo nhưng chưa deploy functions vẫn có thể kéo theo tài nguyên tính phí ở một số plan.

### 12.3. Dùng Azure CLI để đọc, không làm lộ settings

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-func-lab"
APP="fn-orders-lab"

# Đọc thông tin tài nguyên.
az functionapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name, state:state, location:location, kind:kind, serverFarmId:serverFarmId}" \
  --output json

# Kiểm tra functions đã được runtime index.
az functionapp function list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table

# CHỈ liệt kê tên settings, tránh in giá trị connection strings.
az functionapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].name" \
  --output table
~~~

Đầu ra `az functionapp config appsettings list` **không giới hạn query** có thể chứa secrets. Đừng dán toàn bộ JSON settings lên ticket/chat. Ngay cả tài khoản có quyền đọc control plane cũng không chắc được phép xem mọi dữ liệu nghiệp vụ.

### 12.4. Publish dự án từ Core Tools

Với một Function App đã tạo, môi trường/plan được Core Tools đang sử dụng hỗ trợ và project đang ở đúng thư mục gốc:

~~~bash
func azure functionapp publish "$APP"
~~~

**Lệnh này thay đổi code đang chạy**, có thể restart workers và ảnh hưởng tất cả functions trong app. Cần kiểm tra phương thức deployment được hỗ trợ đối với **Flex Consumption và plan cụ thể**; nhiều quy trình production dùng CI/CD, deployment package, build container hoặc công nghệ deployment khác.

Trước khi publish:

- Chạy unit/integration tests và đánh giá dependency security.
- Xác nhận môi trường đúng subscription và resource name.
- Đảm bảo package bao gồm `host.json`, code và requirements cần thiết.
- Không đưa `local.settings.json` chứa credentials vào artifact.
- Chọn version/digest hoặc deployment artifact có thể rollback.
- Kiểm tra slot/revision support phù hợp plan thay vì mặc định mọi plan đều có deployment slots.

### 12.5. Kiểm tra sau deploy

- Function list gồm đủ `hello`, `process_order`, `hourly_cleanup`.
- HTTP endpoint chỉ accessible theo authentication rules đã thiết kế.
- Queue trigger có listener khỏe và đúng queue.
- Timer schedule đúng timezone.
- Không có import error hoặc host startup error.
- Application Insights có invocation telemetry/log.
- Identity/RBAC được áp dụng và firewall/Private Endpoint không chặn.
- SLO/latency và error rate đạt kỳ vọng.

Đừng đánh dấu deployment thành công chỉ vì lệnh publish trả exit code 0; **khả năng thực thi thực tế** phải được kiểm chứng.

## 13. Quan sát Functions: logs, metrics và tracing

### 13.1. Vì sao logging là bắt buộc?

Ở mô hình serverless, host instances có thể được tạo/xóa, và invocation lỗi có thể được retry trên instance khác. Không thể điều tra chỉ bằng cách SSH vào “server hiện tại”. Nên thu telemetry tập trung qua **Application Insights/Azure Monitor/Log Analytics** tùy cấu hình.

Các tín hiệu hữu ích:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Invocation count/success/failure | Tỷ lệ chạy lỗi là bao nhiêu? |
| Execution duration p50/p95/p99 | Có cold start hoặc dependency chậm? |
| HTTP status/latency | Client gặp 4xx/5xx nào? |
| Queue backlog và poison queue | Worker có bị chậm hoặc retry mãi? |
| Timer schedule/past due | Tác vụ định kỳ có chạy đúng giờ? |
| Host instance count/concurrency | Scaling có đủ không? |
| CPU/memory | Worker thiếu tài nguyên không? |
| Dependency failures/latency | SQL/Storage/API bên ngoài có nghẽn? |
| Logs/traces theo operation | Invocation nào gây lỗi, ở dependency nào? |
| Cost và ingestion volume | Logging có quá nhiều và tăng phí? |

### 13.2. Application Insights

Khi instrumentation được bật, có thể quan sát requests, dependencies, traces, exceptions và các nhóm telemetry khác theo SDK/integration. Tên bảng KQL phụ thuộc **classic Application Insights hoặc workspace-based Log Analytics schema**.

Ví dụ trong resource/query context có bảng `requests`:

~~~kusto
requests
| where timestamp >= ago(2h)
| summarize
    Count = count(),
    FailureCount = countif(success == false),
    P95Duration = percentile(duration, 95)
    by bin(timestamp, 5m)
| order by timestamp asc
~~~

Nếu workspace có resource-specific tables thay vì `requests`, kiểm tra schema thật và dùng bảng/field tương đương. Đừng sửa query bằng cách tự đoán tên cột không tồn tại.

### 13.3. Theo dõi exceptions

~~~kusto
exceptions
| where timestamp >= ago(24h)
| summarize Failures = count() by type, outerMessage
| order by Failures desc
~~~

Đây là ví dụ cho **Application Insights context có bảng `exceptions`**. Sampling/ingestion configuration có thể khiến số bản ghi không bằng tổng số invocation. Khi muốn đo tỷ lệ lỗi chính xác, kết hợp metrics và telemetry với điều kiện sampling tương ứng.

### 13.4. Correlation ID và structured logs

Một HTTP request gửi message vào queue; Queue trigger xử lý sau vài giây. Để nối hai invocations:

~~~text
HTTP function:
  traceId=abc, jobId=job-123, action=enqueue

Queue function:
  traceId=abc, jobId=job-123, action=process

Database operation:
  traceId=abc, jobId=job-123, duration=45ms
~~~

Không giả định trace context tự đi qua mọi queue hoặc SDK; nếu không có auto-instrumentation hỗ trợ, cần **truyền correlation context** trong message/headers theo chuẩn và chính sách. Không đưa bearer token, password, PII không cần thiết vào logs.

### 13.5. Alert vận hành

Ví dụ:

- HTTP 5xx vượt ngưỡng kèm p95 latency tăng.
- Queue backlog tăng liên tục dù messages đã được publish.
- Poison queue có message mới.
- Function invocations failures đột biến.
- Timer past-due hoặc không có lần chạy đúng chu kỳ.
- Throttling ở SQL/Storage/API, tăng dependency latency.
- Function App host restart/indexing error.
- Chi phí compute/telemetry vượt budget.

Mỗi alert cần **owner, SLO, severity và runbook**. Một lần Queue message fail có thể được retry thành công, nhưng vẫn cần theo dõi nếu tỷ lệ lỗi cao.

## 14. Độ tin cậy: idempotency, retries và eventual consistency

### 14.1. Bảo đảm at-least-once thay vì “exactly once”

Mẫu luồng:

~~~text
Receive order-123
    |
    v
Write database SUCCESS
    |
    v
Worker crashes BEFORE queue ACK
    |
    v
Message becomes visible again
    |
    v
Another invocation receives order-123
~~~

Nếu không kiểm tra `orderId`, ứng dụng có thể tạo duplicate order. Một giải pháp:

1. Dùng `orderId` làm khóa duy nhất trong DB.
2. Bắt đầu một transaction theo khả năng database.
3. Kiểm tra đã xử lý chưa; chỉ tạo side effects khi cần.
4. Ghi trạng thái `Processed` cùng kết quả.
5. Khi message được giao lại, trả về an toàn mà không tạo trùng.

**Chống lặp side effects** với email/payment có thể cần pattern outbox, deduplication và cơ chế nghiệp vụ bổ sung; không thể chỉ đặt flag trong RAM.

### 14.2. Retry có phân loại

| Lỗi | Có nên retry? | Gợi ý |
| --- | --- | --- |
| Storage/SQL timeout nhất thời | Có, giới hạn | Exponential backoff + jitter |
| HTTP 429 rate limit | Có, theo `Retry-After` khi áp dụng | Giới hạn concurrency và budget |
| Message thiếu trường bắt buộc | Không retry vô hạn | Poison/dead-letter/điều tra publisher |
| Unauthorized 403 do thiếu RBAC | Không tự sửa bằng retry mãi | Xử lý identity/permissions |
| Database unique conflict do message lặp | Trả trạng thái idempotent | Không tạo bản ghi thứ hai |
| Host OOM | Retry không giải quyết gốc | Tối ưu memory, cấu hình plan |

Trigger/extension có retry rules khác nhau; không coi HTTP retry policy giống Queue Service Bus và Event Hubs. Retry quá mức có thể tạo **retry storm** khi downstream đã nghẽn.

### 14.3. Thứ tự message

Với nhiều instances và concurrency cao, **không giả định Queue Storage messages được xử lý theo đúng thứ tự gửi trong mọi tình huống**. Nếu nghiệp vụ yêu cầu thứ tự theo `accountId` hoặc `orderId`, cần thiết kế partition/session/serialization phù hợp với messaging service hỗ trợ.

### 14.4. Durable Functions

**Durable Functions** cung cấp mô hình điều phối stateful functions như:

- **Orchestrator** điều phối các activity functions.
- **Activity** thực thi đơn vị công việc.
- **Entity** lưu một dạng state theo mô hình hỗ trợ.

Một flow có thể chờ event bên ngoài, retry activity, lưu trạng thái và tiếp tục sau host recycle. Tuy nhiên orchestrator có **replay semantics**: code điều phối phải tuân thủ nguyên tắc deterministic, không tự ý gọi API có side effects không được quản lý trong orchestrator.

Dùng Durable Functions khi workflow nhiều bước/chờ lâu; không phải mọi queue function nhỏ đều cần Durable.

## 15. Bảo mật và networking

### 15.1. Public HTTP không tự an toàn

HTTP trigger có route public cần:

- HTTPS và hostname/certificate phù hợp.
- Authentication và authorization (Entra ID, JWT, Easy Auth hoặc API Management khi phù hợp).
- Request validation, payload size limits và rate limiting.
- Kiểm tra CORS theo browser; **CORS không phải cơ chế phân quyền**.
- Không đưa function/admin key vào source hoặc URL dễ bị ghi log.
- Secrets/identity và data-plane permissions tối thiểu.

### 15.2. VNet, private endpoints và DNS

Khi Functions truy cập Azure SQL/Storage/Key Vault riêng tư:

1. Xác minh hosting plan có VNet integration phù hợp.
2. Chọn subnet/network route theo yêu cầu plan.
3. Cấu hình Private Endpoint cho dịch vụ đích nếu cần.
4. Liên kết Private DNS Zone/forwarding đúng VNet.
5. Kiểm tra Storage/SQL firewall và RBAC data-plane.
6. Đảm bảo host storage và trigger sources cũng truy cập được theo cấu hình.

**VNet integration không tự khiến mọi dịch vụ trở thành private.** Khi Functions bị lỗi trigger sau khi khóa Storage network, kiểm tra DNS/routing của host storage riêng với connection nghiệp vụ.

### 15.3. Quyền và trust boundary

Không cấp Owner subscription cho Function App chỉ để đọc queue. Phân tách:

- Deployment identity: cập nhật Function App/app settings theo quyền.
- Runtime managed identity: truy cập đúng Queue/Blob/SQL/Key Vault.
- Monitoring roles: đọc logs/metrics nhưng không tự xem secrets.
- Network team: quản lý private connectivity.
- Security team: policy, certificate/secret rotation.

RBAC cấp ở scope tối thiểu cần thiết. Đối với storage identity, **management-plane Contributor** không tự đồng nghĩa đủ mọi **data-plane** rights.

### 15.4. Rủi ro dependency package

Serverless vẫn chạy code do nhóm phát triển đóng gói. Pin dependencies, quét lỗ hổng, rà soát licensing và chạy security tests. Không import package từ nguồn không tin cậy hoặc nhúng secrets trong code. Các secrets local phải bị loại khỏi artifact/Git.

## 16. Chi phí và sizing

### 16.1. Những yếu tố tính phí

Các plan có cách tính phí khác nhau: compute provisioned, execution count, execution duration/memory hoặc always-ready resources, tùy plan. Ngoài Functions còn có thể có:

| Thành phần | Nguồn chi phí |
| --- | --- |
| Functions hosting | Plan/instances/vCPU-memory duration/execution theo pricing model |
| Storage Account | Transactions, dữ liệu, queues, egress |
| Application Insights/Log Analytics | Log ingestion, retention, alerts |
| Key Vault | Operations theo mô hình giá |
| Private Endpoint/NAT/network | Network resources và data processing |
| Database/Cosmos DB | RU/s, DTU/vCore, storage |
| Service Bus/Event Hubs | Messaging tier/throughput |
| API Management/Front Door | Gateway, requests, WAF, transfer |

Không dùng câu “Function không chạy thì chắc chắn không tốn tiền” cho mọi plan: Premium/Dedicated/always-ready và tài nguyên kèm theo có thể tiếp tục tính phí.

### 16.2. Ví dụ toán học ước lượng execution

Giả sử 1 triệu invocations/tháng, mỗi lần mất trung bình 0,2 giây và được cấp 512 MiB memory:

~~~text
1.000.000 invocations × 0,2 s = 200.000 execution-seconds

512 MiB = 0,5 GiB
200.000 × 0,5 GiB = 100.000 GiB-seconds
~~~

Đây là **phép tính khối lượng workload**, không phải hóa đơn Azure: billing có minimum execution duration, free grant, pricing model, always-ready hoặc rules riêng theo plan. Dùng **Pricing Calculator** và bảng giá đúng region/plan hiện hành để dự toán thực tế.

### 16.3. Giảm chi phí không phá SLO

- Giảm dependency latency và tối ưu memory CPU.
- Đặt concurrency/scale limits theo backend quota.
- Dùng queue để làm mượt spike và tránh request HTTP kéo dài.
- Chọn always-ready khi cold start thực sự ảnh hưởng SLO.
- Tắt log quá nhiều, cấu hình sampling/retention hợp lý, không mất tín hiệu critical.
- Đánh giá chi phí của plan theo chu kỳ tải thực, không chỉ peak một phút.
- Cân nhắc tách Function Apps nếu một workload làm thay đổi scaling/chi phí của app khác.

## 17. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
| --- | --- | --- |
| Không thấy functions sau deploy | Sai folder, missing host.json, import/index lỗi | Startup logs, deployment artifact, `az functionapp function list` |
| HTTP 404 | Sai route prefix, route không được index | `func start`, function list, route |
| HTTP 401/403 | Function key/auth, Easy Auth, RBAC/policy | Endpoint auth config, identity |
| HTTP 500 | Code exception hoặc dependency | Invocation logs và tracing |
| HTTP 502/504 | Frontend timeout hoặc upstream chậm | HTTP duration, dependency logs |
| Request đầu chậm | Cold start, import/dependency startup | p95/p99 sau idle, host cold start logs |
| Queue trigger không chạy | Wrong queue/connection, host storage, missing extension, RBAC/network | Settings names, Azurite/Storage logs, host startup |
| Queue chạy lặp | Redelivery/retry sau lỗi hoặc crash | Dequeue count, idempotency key |
| Poison queue có dữ liệu | Message xử lý nhiều lần lỗi | Inspect message an toàn, validate schema |
| Timer không đúng giờ | UTC/timezone, schedule format, host monitor | NCRONTAB, plan support, logs |
| Functions chậm dù scale nhiều | SQL/API quota hoặc concurrency | Dependency latency, pool limits |
| Không thấy telemetry | App Insights config, sampling, workspace sai | Connection string, schema, ingestion |
| Quyền Azure đúng nhưng Storage timeout | Private DNS/VNet/firewall | DNS, network path, endpoint |
| Cost tăng khi idle | Premium/always-ready/Dedicated, logs và Storage | Billing breakdown, instance min |

### 17.1. Quy trình từ triệu chứng tới nguyên nhân

1. Xác định **Function App, function, trigger, subscription, plan và mốc thời gian**.
2. Đọc host startup logs để chắc function được index.
3. Kiểm tra trigger source: HTTP path, queue name, Timer schedule hoặc event subscription.
4. Kiểm tra app settings, identity, storage connectivity và extension.
5. Đối chiếu invocation logs/traces với failure/latency của downstream.
6. Kiểm tra plan scale/concurrency/timeout và instance health.
7. Sửa đúng nguyên nhân, giữ bằng chứng trước khi restart/deploy.
8. Test lại với input đại diện, theo dõi cả failure rate và SLO.

## 18. Bài thực hành tổng hợp không cần tạo Azure resources

### 18.1. Dữ liệu giả lập

Một Function App `fn-orders-prod` có:

- HTTP function nhận đơn và đẩy message vào queue.
- Queue function xử lý order.
- Timer function làm báo cáo mỗi giờ.
- Host storage/queue đã được cấu hình.
- Một ngày có tải thường 10 msg/s, peak 150 msg/s.

Dữ liệu vận hành:

| UTC | Message backlog | Successful queue invocations | Failed invocations | HTTP p95 |
| --- | ---: | ---: | ---: | ---: |
| 08:00 | 20 | 600/phút | 0 | 180 ms |
| 09:00 | 2.000 | 700/phút | 15 | 240 ms |
| 09:05 | 8.000 | 800/phút | 90 | 270 ms |
| 09:15 | 12.000 | 820/phút | 120 | 290 ms |

**Câu A:** có thể chỉ cần tăng max instances là đủ?

*Đáp án:* Chưa. Backlog tăng, fail cũng tăng; phải tìm nguyên nhân: queue scaler/plan limit, DB throttling, lỗi message hay quyền. Nếu DB là bottleneck, tăng instances có thể làm fail rate tăng.

**Câu B:** một message `order-123` được gọi hai lần sau khi invocation đầu ghi DB thành công nhưng crash trước acknowledgment. Làm gì?

*Đáp án:* Thiết kế idempotency theo orderId, transaction/unique constraint, xử lý duplicate không tạo thêm side effects. Không giả định queue chạy exactly-once.

**Câu C:** Timer `0 0 9 * * *` chạy 09:00 UTC nhưng đội vận hành ở Việt Nam muốn 09:00 địa phương. Điều gì phải đổi?

*Đáp án:* Quy đổi đúng UTC và cân nhắc Daylight Saving Time nếu là khu vực có DST; Việt Nam UTC+7 không áp dụng DST thông thường. Nếu default UTC, 09:00 Việt Nam tương ứng 02:00 UTC, có thể dùng schedule `0 0 2 * * *`. Đừng tự dùng `WEBSITE_TIME_ZONE` khi plan/OS không hỗ trợ.

**Câu D:** HTTP function chạy workflow 12 phút, client nhận timeout trước dù `functionTimeout` dài hơn 12 phút. Vì sao?

*Đáp án:* Frontend HTTP/load balancer/client có giới hạn riêng; dùng queue + `202 Accepted` hoặc Durable Functions async pattern.

**Câu E:** Queue trigger không chạy, nhưng HTTP function vẫn trả 200. Cần xem gì?

*Đáp án:* `OrdersStorage` connection, queue name, extension bundle, storage firewall/private DNS, identity/data-plane RBAC và host startup logs. HTTP khỏe không chứng minh queue listener khỏe.

### 18.2. Checklist trước production

- Chọn hosting plan dựa trên SLO, region/runtime/network và chi phí.
- App được index đủ functions và logs/telemetry hoạt động.
- HTTP endpoint có xác thực/ủy quyền và input validation.
- Queue consumers idempotent, retry/poison handling rõ.
- Timer dùng timezone và lịch chính xác.
- Managed identity có RBAC cần thiết, không có secrets trong source.
- Host storage/trigger connections hoạt động trên network thật.
- Đo concurrency, cold start, timeout, CPU/memory và downstream capacity.
- Có CI/CD, version/rollback plan, monitoring alerts và budget.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một Function App có ba functions. Ba functions có nhất thiết chạy ở ba VMs khác nhau không?

**Đáp án:** Không. Số host instances và concurrency phụ thuộc hosting plan và tải; chúng cùng thuộc một đơn vị ứng dụng nhưng không cố định mỗi function một VM.

**Câu 2.** Một function có thể vừa là HTTP trigger vừa là Queue trigger không?

**Đáp án:** Mỗi function định nghĩa một trigger. Dùng hai functions tách biệt, có thể tái sử dụng logic nghiệp vụ.

**Câu 3.** Khác biệt `host.json` và `local.settings.json`?

**Đáp án:** `host.json` chứa cấu hình runtime/host; `local.settings.json` chứa settings dùng local, có thể có secrets, không mặc định publish lên Azure.

**Câu 4.** Đổi connection string ở Azure có thể làm trigger dừng dù code không thay đổi?

**Đáp án:** Có. Listener cần settings, quyền và connectivity đúng; thay cấu hình có thể restart host hoặc làm mất truy cập Storage.

**Câu 5.** Vì sao Storage Queue processing cần idempotency?

**Đáp án:** Message có thể được giao lại sau thất bại/crash, nên side effects có nguy cơ lặp.

**Câu 6.** Scale-out và concurrency khác nhau thế nào?

**Đáp án:** Scale-out tăng số host instances; concurrency tăng số invocations được xử lý đồng thời trên một instance theo limits.

**Câu 7.** Flex always-ready và Premium có thể phát sinh phí khi không có request?

**Đáp án:** Có thể, vì compute giữ sẵn/plan billing và các tài nguyên liên quan. Cần đọc bảng giá thực tế.

**Câu 8.** Khi HTTP request cần xử lý lâu, vì sao queue/202 hoặc Durable phù hợp hơn?

**Đáp án:** Tránh giữ connection vượt giới hạn frontend/client và giúp lưu trạng thái, retry, theo dõi tiến độ.

**Câu 9.** Function key có thay quyền xác thực người dùng OAuth không?

**Đáp án:** Không. Function key là shared secret và không tự biểu diễn user identity/authorization nghiệp vụ.

**Câu 10.** Tại sao không mặc định đổi `WEBSITE_TIME_ZONE` trong mọi hosting plan?

**Đáp án:** Tính năng có hạn chế theo OS/hosting plan; nên kiểm tra khả năng hỗ trợ và dùng UTC khi cần.

## Ghi nhớ

- **Function** là logic chạy theo một **trigger**; **Function App** là ranh giới cấu hình/triển khai chứa nhiều functions.
- **Functions host** nạp metadata/triggers/bindings; **language worker** thực thi code theo runtime/model được hỗ trợ.
- **HTTP, Queue, Timer** khác nhau về input, response, retry và scaling; một function chỉ có một trigger.
- **Flex Consumption, Consumption, Premium, Dedicated** có đặc điểm cấp compute, cold start, networking và billing khác nhau.
- **Scale-out không đồng nghĩa concurrency**; cần kiểm tra latency, downstream quota và khả năng xử lý lặp.
- **Stateless, idempotency, timeout/retries có giới hạn, managed identity và monitoring** là nền tảng của hệ thống Functions đáng tin cậy.
- Luôn xác minh **Function App runtime, host storage, trigger connection, RBAC, networking và observability** trước khi kết luận deployment hoàn tất.
