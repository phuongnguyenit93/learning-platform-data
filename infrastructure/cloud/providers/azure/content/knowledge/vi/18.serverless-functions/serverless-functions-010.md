# Mẫu fan-out, fan-in và quy trình chạy dài

Một Azure Function thông thường phù hợp xử lý một HTTP request, queue message hoặc event trong thời gian tương đối ngắn. Nhưng khi phải **xử lý hàng nghìn tài liệu độc lập**, **chờ người duyệt hai ngày** hoặc điều phối giao dịch gồm nhiều bước có thể thất bại, cách viết một Function gọi API tuần tự và giữ HTTP request mở trở nên khó vận hành: kết nối có thể timeout, worker có thể restart, tiến độ chỉ nằm trong RAM và retry có nguy cơ tạo side effect trùng.

**Azure Durable Functions** là phần mở rộng của Azure Functions dành cho **stateful workflows**. Lập trình viên mô tả quá trình điều phối bằng orchestrator, đưa thao tác có tác động bên ngoài vào activities, chờ durable timers hoặc external events và truy vấn trạng thái bằng instance ID. Runtime lưu lịch sử và có thể **replay** quyết định điều phối khi tiếp tục một phiên sau restart. Nó không miễn trừ lỗi logic, không bảo đảm exactly-once cho mọi side effect và không thay thế yêu cầu bảo mật hoặc quản lý chi phí.

Hai mẫu trọng tâm:

- **Fan-out/fan-in:** chia một tập input thành những activity độc lập có thể chạy song song, sau đó chờ và tổng hợp các kết quả.
- **Long-running orchestration:** mô hình hóa quy trình qua phút, giờ hoặc ngày bằng các điểm chờ bền vững, không giữ một HTTP connection hoặc thread liên tục.

Bài học thuộc chương **Serverless với Azure Functions** của mô-đun **CLOUD_PROVIDERS_AZURE**, kết nối việc phát triển Functions với subscription, resource group, Microsoft Entra ID, Storage, networking, Azure Monitor, bảo mật và quản lý chi phí ứng dụng trên Azure.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích hạn chế của HTTP Function thông thường đối với công việc chạy lâu.
2. Phân biệt starter/client, orchestrator, activity, orchestration instance, task hub, durable timer và external event.
3. Viết fan-out/fan-in với **Azure Durable Functions Python programming model v2**.
4. Xử lý retry, timeout, idempotency, partial failure và fan-in policy.
5. Thiết kế HTTP 202 Accepted, status endpoint và chống tạo job trùng khi caller retry.
6. Xây dựng quy trình chờ human approval với external event hoặc timeout.
7. Áp dụng monitor pattern, batching, sub-orchestrations và continue-as-new.
8. Hiểu deterministic replay, versioning, storage history và giới hạn payload.
9. Tính toán scale, concurrency, downstream quota, chi phí và bảo vệ task hub.
10. Chẩn đoán một instance Pending/Running/Failed, lập checklist production và kiểm thử sự cố.

Ví dụ dùng Python, Azure Functions Core Tools, Azure Storage/Azurite và Durable Functions extension. Tên tài nguyên, URL và payload là minh họa; **không tự tạo tài nguyên hoặc chạy code trên subscription thực**.

## 2. Khi nào một Function thông thường không đủ?

### 2.1. Bài toán xử lý 1.000 hóa đơn

Một HTTP endpoint nhận danh sách 1.000 hóa đơn. Mỗi hóa đơn cần gọi API phân tích, lưu kết quả vào Blob và tổng hợp báo cáo. Nếu dùng một HTTP Function:

~~~text
HTTP POST /analyze
    |
    v
Lặp 1.000 tệp → gọi API → lưu kết quả
    |
    v
Tổng hợp báo cáo → HTTP 200
~~~

Những rủi ro:

- Client, gateway và HTTP infrastructure có thể timeout trước khi vòng lặp xong.
- Function invocation chịu giới hạn của hosting plan.
- Worker restart/scale-in có thể làm mất tiến độ trong bộ nhớ.
- Nếu caller retry, có thể tính phí hoặc tạo dữ liệu trùng.
- Nếu tệp thứ 800 lỗi, khó xác định những tệp đã xử lý thành công.
- Tăng timeout không tự tạo checkpoint, retry policy hay truy vấn tiến độ.

**Durable Functions không làm một activity chạy quá giới hạn invocation trở nên hợp lệ.** Thay vì giữ một lời gọi đơn quá lâu, workflow chia thành các activities phù hợp với tài nguyên và timeout của hosting plan.

### 2.2. Trả kết quả bất đồng bộ

~~~mermaid
sequenceDiagram
    participant U as Client
    participant H as HTTP Starter
    participant O as Orchestrator
    participant A as Activity Workers
    participant S as State Storage
    U->>H: POST /jobs
    H->>O: Start instance
    H-->>U: 202 Accepted + instanceId
    O->>S: Lưu history/checkpoint
    O->>A: Schedule activities
    A-->>O: Results
    O->>S: Ghi trạng thái
    U->>H: GET /jobs/{id}
    H-->>U: Running/Completed/Failed
~~~

HTTP trả sớm để client không cần đợi toàn bộ công việc. Instance tiếp tục thông qua durable orchestration; hệ thống có thể theo dõi và phục hồi theo khả năng của runtime/backend.

### 2.3. Chọn công cụ phù hợp

| Nhu cầu | Hướng thiết kế | Lý do |
|---|---|---|
| HTTP API xử lý ngắn | HTTP-trigger Function | Đơn giản, không cần trạng thái |
| Queue message xử lý độc lập | Queue-trigger Function | Tận dụng queue/trigger retry |
| N hoạt động độc lập, cần kết quả chung | Durable fan-out/fan-in | Orchestrator theo dõi tập kết quả |
| API job chạy hàng chục phút | Async HTTP + Durable instance | Client lấy status qua ID |
| Chờ người phê duyệt | External event + durable timer | Có trạng thái trong thời gian chờ |
| Poll trạng thái job bên ngoài | Monitor pattern | Chờ timer thay cho sleep |
| Workflow nhiều SaaS/connector | Xem xét Logic Apps | Connector và workflow phù hợp |
| Batch/GPU tính toán nặng | Azure Batch/AKS Jobs/Container Apps Jobs | Orchestrator điều phối, không làm CPU-heavy |

Không dùng Durable Functions chỉ vì muốn "chạy nhiều việc cùng lúc"; nếu mỗi message hoàn toàn độc lập và không cần fan-in, queue consumers đơn giản có thể hiệu quả hơn.

## 3. Thành phần của Durable Functions

### 3.1. Client/starter

Client Function có thể:

- Tạo một orchestration instance.
- Lấy instance ID và trạng thái.
- Gửi external event.
- Gọi APIs quản lý terminate, suspend/resume hoặc purge theo khả năng phiên bản.
- Trả management/status URLs cho HTTP caller.

Starter không nên thực thi toàn bộ quy trình nặng; nó xác thực và kiểm tra request rồi khởi tạo instance.

### 3.2. Orchestrator

Orchestrator mô tả thứ tự công việc, dependency và điểm chờ:

~~~text
Activity A
   |
   +--> Activity B1 --+
   +--> Activity B2 --+--> Fan-in --> Activity C
   +--> Activity B3 --+
                         |
                         v
                    Chờ approval
                         |
                         v
                   Activity D
~~~

Orchestrator dùng các API như context.call_activity, task_all, task_any, create_timer, wait_for_external_event và call_sub_orchestrator. Nó **không nên trực tiếp đọc Blob, gọi HTTP hay tạo giao dịch**.

### 3.3. Activity

Activity chứa logic với side effects:

- Đọc Blob/DB.
- Gọi API AI hoặc đối tác.
- Xử lý và ghi kết quả.
- Gửi email, thông báo, tạo giao dịch.
- Kiểm tra trạng thái hệ thống ngoài.
- Tổng hợp kết quả lớn.

Một activity có thể thất bại hoặc được retry, nên phải có idempotency hoặc reconciliation khi có side effects.

### 3.4. Instance, history và task hub

| Thuật ngữ | Ý nghĩa |
|---|---|
| Instance ID | Định danh một lần chạy orchestration |
| Input | Dữ liệu đầu vào orchestration |
| History | Các sự kiện/decisions/results để runtime replay |
| Task hub | Nhóm dữ liệu và hoạt động điều phối của Durable backend |
| Task | Lời gọi activity, timer hoặc event được chờ |
| Custom status | Metadata tiến độ do ứng dụng cập nhật theo API hỗ trợ |
| Orchestration output | Giá trị trả về khi hoàn tất |
| Continue-as-new | Tiếp tục với input mới và rút gọn/đặt lại history theo runtime |

Durable Functions thường dùng Azure Storage provider hoặc backend khác được hỗ trợ, tùy extension, hosting và cấu hình. Task hub lưu trạng thái vận hành quan trọng; không xóa queues/tables/containers của task hub khi còn instance chạy.

## 4. Replay và nguyên tắc deterministic

### 4.1. Replay là gì?

Durable runtime có thể thực thi lại mã orchestrator từ đầu dựa trên history đã ghi, trả lại các kết quả activity/timer trước đó từ history, rồi tiếp tục từ chỗ chờ. **Mã orchestrator phải tái tạo cùng chuỗi quyết định** với cùng input/history.

~~~mermaid
flowchart TD
    A["Lên lịch Activity A"] --> H["History: Activity A completed"]
    H --> W["Đợi timer/event/Activity B"]
    W --> R["Worker restart"]
    R --> P["Replay code orchestrator"]
    P --> K["Khôi phục quyết định từ history"]
    K --> N["Tiếp tục bước còn chờ"]
~~~

Vì replay, log bên trong orchestrator có thể xuất hiện nhiều lần dù một activity không hề được thực thi lại. Replay **không** biến mọi side effect của activity thành exactly-once.

### 4.2. Những gì không nên làm trong orchestrator

- Gọi trực tiếp HTTP, Storage, SQL hoặc Key Vault.
- Gửi email, tạo hóa đơn, ghi file.
- Gọi random hoặc UUID không thuộc Durable context để quyết định nhánh.
- Dùng datetime.now/utcnow làm thời gian quyết định.
- Dùng time.sleep hoặc blocking wait.
- Phụ thuộc vào thứ tự không ổn định của một cấu trúc dữ liệu.
- Đọc app setting có thể thay đổi giữa các lần replay rồi đổi nhánh workflow.
- Bắt đầu threads, coroutines hay I/O không qua primitives Durable.

Ví dụ sai:

~~~python
from datetime import datetime
import requests

def wrong_orchestrator(context):
    if datetime.utcnow().hour < 12:
        requests.post("https://example.invalid/pay", json={"order": 1})
    return "done"
~~~

Khi replay, thời gian hoặc response mạng có thể khác và POST có thể lặp lại.

### 4.3. Cách đúng

- Lấy logical UTC từ **context.current_utc_datetime**.
- Tạo UUID bằng **context.new_uuid()** khi SDK hỗ trợ.
- Dùng **context.create_timer(deadline)** để chờ.
- Đưa HTTP/DB/Storage/Key Vault calls vào activity.
- Giữ input quyết định đã versioned; không đọc biến cấu hình mutable mỗi lần replay.
- Gửi ID/URI metadata nhỏ thay vì toàn bộ payload.

Có thể tránh log trùng trong orchestrator Python bằng cách kiểm tra trạng thái replay (khi SDK hỗ trợ):

~~~python
if not context.is_replaying:
    logging.info("Starting fan-out stage")
~~~

## 5. Mẫu fan-out/fan-in

### 5.1. Fan-out: lập lịch nhiều công việc

~~~mermaid
flowchart TD
    I["Input: 4 tài liệu"] --> O["Orchestrator"]
    O --> A1["Analyze 001"]
    O --> A2["Analyze 002"]
    O --> A3["Analyze 003"]
    O --> A4["Analyze 004"]
    A1 --> F["task_all: fan-in"]
    A2 --> F
    A3 --> F
    A4 --> F
    F --> S["Aggregate summary"]
    S --> R["Completed"]
~~~

Các activities có thể được phân phối trên nhiều workers. Tuy nhiên **N tasks không bảo đảm N executions đồng thời**: concurrency còn chịu giới hạn của worker, hosting plan, backend queues và downstream service.

### 5.2. Fan-in: chờ và tổng hợp

Một orchestrator thường:

~~~python
tasks = [
    context.call_activity("analyze_document", item)
    for item in items
]
results = yield context.task_all(tasks)
summary = yield context.call_activity("summarize_results", results)
return summary
~~~

task_all biểu thị dependency **chờ tất cả**, còn activity tổng hợp thực hiện công việc tính toán/ghi kết quả. Nếu một activity có exception, cần chính sách retry/partial success; không tự suy ra task_all luôn trả đủ kết quả thành công.

### 5.3. Những ứng dụng hợp lý

- Xử lý nhiều tệp/ảnh/tài liệu.
- Thu thập dữ liệu từ nhiều endpoints rồi tổng hợp.
- Chia một báo cáo thành nhiều phần tính toán.
- Xử lý từng partition/shard nhỏ.
- Chạy kiểm thử nhiều environment song song rồi tổng hợp.
- Gửi các yêu cầu độc lập tới nhiều service và chờ đủ kết quả.

Không fan-out những bước phải tuân theo transaction/order nghiêm ngặt hoặc gây xung đột trên cùng một bản ghi nếu chưa thiết kế khóa/idempotency.

### 5.4. Ví dụ thời gian

Nếu có 10 activities, mỗi activity 5 giây:

- Tuần tự: gần 50 giây tính riêng công việc, chưa có overhead.
- Đủ capacity: fan-out có thể gần hoạt động lâu nhất cộng overhead.
- Chỉ 2 slots đồng thời: có thể phải chạy khoảng 5 đợt.

Đây là mô hình lý tưởng, không phải cam kết latency của Azure. Nếu API đối tác hạn chế 2 requests/giây, gửi hàng nghìn activities đồng thời có thể khiến 429 và tăng thời gian xử lý.

## 6. Thực hành: Azure Durable Functions Python v2

### 6.1. Điều kiện và cấu trúc

Sử dụng Azure Functions runtime v4 và các gói tương thích:

~~~text
durable-documents/
  function_app.py
  requirements.txt
  host.json
  local.settings.json
~~~

requirements.txt minh họa:

~~~text
azure-functions
azure-functions-durable
~~~

Trong dự án thực, quản lý version/dependency có kiểm soát và kiểm tra khả năng tương thích trước phát hành.

### 6.2. Code đầy đủ

Ví dụ này xử lý **metadata tài liệu giả lập**, không thực hiện I/O thật hoặc trích nội dung PDF. Mục tiêu là minh họa fan-out, fan-in và API status.

~~~python
import logging

import azure.functions as func
import azure.durable_functions as df

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="jobs/start", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_batch(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("JSON không hợp lệ", status_code=400)

    if not isinstance(payload, dict):
        return func.HttpResponse("Body phải là object", status_code=400)

    items = payload.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 20):
        return func.HttpResponse(
            "items phải là mảng từ 1 đến 20 phần tử",
            status_code=400,
        )

    if any(
        not isinstance(item, str) or not item.strip() or len(item) > 100
        for item in items
    ):
        return func.HttpResponse("ID không hợp lệ", status_code=400)

    instance_id = await client.start_new(
        "fanout_orchestrator",
        None,
        {"items": items},
    )
    return client.create_check_status_response(req, instance_id)


@app.orchestration_trigger(context_name="context")
def fanout_orchestrator(context: df.DurableOrchestrationContext):
    payload = context.get_input()
    tasks = [
        context.call_activity("analyze_document", document_id)
        for document_id in payload["items"]
    ]
    results = yield context.task_all(tasks)
    summary = yield context.call_activity("summarize_results", results)
    return summary


@app.activity_trigger(input_name="document_id")
def analyze_document(document_id: str) -> dict:
    logging.info("Analyzing document ID")
    return {
        "documentId": document_id,
        "processed": True,
        "score": len(document_id),
    }


@app.activity_trigger(input_name="results")
def summarize_results(results: list) -> dict:
    return {
        "total": len(results),
        "processed": sum(1 for r in results if r["processed"]),
        "scoreSum": sum(r["score"] for r in results),
        "documentIds": [r["documentId"] for r in results],
    }
~~~

Các thành phần:

1. HTTP starter kiểm tra input và giới hạn số lượng items.
2. Durable client gọi start_new và sinh instance ID.
3. create_check_status_response tạo phản hồi 202 với các URLs quản lý/trạng thái theo Durable Functions.
4. Orchestrator chỉ lập lịch activities và chờ task_all.
5. analyze_document thực thi công việc độc lập (giả lập).
6. summarize_results là activity riêng cho phép mở rộng logic tổng hợp.
7. Output cuối được lưu theo cơ chế trạng thái của runtime.

Nếu dùng Python programming model v1 hoặc phiên bản package khác, decorator/cấu trúc dự án thay đổi; không sao chép trực tiếp code v2 vào mô hình v1.

### 6.3. host.json minh họa

~~~json
{
  "version": "2.0",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  },
  "extensions": {
    "durableTask": {
      "hubName": "DocumentsHub",
      "maxConcurrentActivityFunctions": 10,
      "maxConcurrentOrchestratorFunctions": 5
    }
  }
}
~~~

Các giới hạn concurrency chỉ minh họa. Cấu hình tối ưu phụ thuộc worker/plan/provider và tải thật. **hubName** phải được quản lý theo môi trường; tránh vô tình cho hai ứng dụng độc lập dùng cùng task hub và storage state.

### 6.4. local.settings.json

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python"
  }
}
~~~

UseDevelopmentStorage=true dùng Azurite trong môi trường local có tính năng tương thích. Không đưa account key production vào local.settings.json trong Git và không sử dụng emulator làm storage production.

### 6.5. Gửi thử HTTP request

Với Core Tools và dependencies đã được cài, có thể chạy trong môi trường lab:

~~~bash
func start
~~~

Gửi request:

~~~bash
curl -X POST \
  http://localhost:7071/api/jobs/start \
  -H 'Content-Type: application/json' \
  -d '{"items":["invoice-001","invoice-002","invoice-003"]}'
~~~

Dự kiến trả 202 Accepted, instanceId và URLs để truy vấn hoặc quản lý instance. Những URLs có thể chứa key trong query string; **không copy nguyên response chứa URL quản lý vào log hoặc ticket công khai**.

Output cuối minh họa sau khi Completed:

~~~json
{
  "total": 3,
  "processed": 3,
  "scoreSum": 33,
  "documentIds": ["invoice-001", "invoice-002", "invoice-003"]
}
~~~

Ba document IDs đều dài 11 ký tự; score chỉ đo chiều dài ID để minh họa fan-in chứ không phải thuật toán phân tích tài liệu.

### 6.6. Những kiểm tra cần làm

- Trạng thái instance chuyển Pending/Running sang Completed.
- Kết quả gồm đúng 3 document IDs.
- Không có lỗi extension/host storage.
- Có thể đọc status mà không để lộ dữ liệu nhạy cảm.
- Thử 400 khi items rỗng/quá 20 hoặc phần tử không hợp lệ.
- Kiểm tra logs activity và correlation instance.
- Sau khi thay hoạt động giả bằng I/O thật, thử retry, permissions, throttling và error handling.

## 7. Fan-in với lỗi: all-or-nothing hay partial success?

### 7.1. Một activity thất bại

Giả sử 9/10 tệp xử lý thành công, tệp thứ 10 bị timeout:

~~~mermaid
flowchart TD
    O["Fan-out 10 activities"] --> S["9 thành công"]
    O --> F["1 lỗi"]
    S --> P{"Business policy"}
    F --> P
    P -->|Require all| X["Failed / cần xử lý"]
    P -->|Partial allowed| R["9 kết quả + 1 lỗi"]
    P -->|Transient| T["Retry giới hạn"]
    T --> P
~~~

Kết quả fan-in cần phản ánh nghiệp vụ. Với báo cáo tổng hợp có thể chấp nhận 1 tệp lỗi; với hệ thống đối soát tài chính có thể phải fail toàn bộ job để tránh công bố sai.

### 7.2. Các chiến lược

| Chính sách | Khi dùng | Cạm bẫy |
|---|---|---|
| Fail all | Cần đủ kết quả | Side effects trước đó có thể cần bù trừ |
| Retry transient | 429/503/network timeout | Retry nhân số request/chi phí |
| Partial success | Công việc độc lập, chấp nhận thiếu | Output phải ghi rõ thiếu kết quả |
| Dead-letter/quarantine | Item hỏng cần điều tra | Cần lưu metadata và cơ chế chạy lại chọn lọc |
| Batch/sub-orchestrator | Tập input lớn | Cần quản lý tiến độ và history |

Một wrapper activity có thể phân loại lỗi và trả object succeeded=false thay vì ném exception. Nhưng nếu business policy không cho partial result, không nên báo Completed một cách lạc quan.

### 7.3. Kết quả không nên chứa payload lớn

Ví dụ:

~~~json
{
  "documentId": "invoice-014",
  "succeeded": false,
  "attempts": 3,
  "errorCode": "PARTNER_TIMEOUT",
  "outputBlobPath": null
}
~~~

Với thành công, có thể lưu kết quả lớn vào Blob và chỉ trả result reference:

~~~json
{
  "documentId": "invoice-015",
  "succeeded": true,
  "attempts": 1,
  "errorCode": null,
  "outputBlobPath": "results/job-001/invoice-015.json"
}
~~~

Không đưa dữ liệu khách hàng, nội dung PDF, access token hoặc SAS URI dài hạn vào history nếu có thể tránh.

## 8. Retry và idempotency

### 8.1. Durable retry

Trong Python orchestrator, có thể gọi activity với retry options:

~~~python
retry_options = df.RetryOptions(
    first_retry_interval_in_milliseconds=5000,
    max_number_of_attempts=3,
)

result = yield context.call_activity_with_retry(
    "analyze_document",
    retry_options,
    "invoice-001",
)
~~~

Ví dụ minh họa API của Python Durable Functions. Cần kiểm tra SDK version, tham số và behavior khi triển khai. Retry nên có số lần, độ trễ và timeout hợp lý, không phải retry vô hạn.

### 8.2. Phân loại lỗi

- **Transient:** 429, 503, network timeout, service tạm không khả dụng.
- **Permanent:** payload sai, yêu cầu không hợp lệ, resource ID không tồn tại theo nghiệp vụ.
- **Authorization:** 401/403 do principal/RBAC/policy thường cần sửa cấu hình; retry nhiều lần không giúp.
- **Business conflict:** 409 hoặc duplicate đã xử lý cần reconciliation, không luôn là transient.
- **Operation timeout:** HTTP call timeout không chắc chứng minh operation phía đối tác chưa thực hiện.

### 8.3. Side effect trùng

Giả sử activity gửi POST tạo hóa đơn, đối tác đã lưu nhưng response bị mất. Runtime retry activity và phía đối tác có thể tạo hóa đơn thứ hai.

Để giảm rủi ro:

1. Tạo **operation ID ổn định** theo businessJobId + itemId + operationType.
2. Gửi Idempotency-Key nếu API hỗ trợ.
3. Dùng unique constraint hoặc conditional insert trong database.
4. Kiểm tra trạng thái operation đã có trước khi làm lại.
5. Ghi correlation ID trong logs/audit.
6. Có reconciliation nếu response bị mất sau side effect.

Chỉ gửi Idempotency-Key khi backend thực sự hỗ trợ hoặc có lớp deduplication; tự đặt header mà không ai kiểm tra không bảo đảm exactly-once.

### 8.4. Exactly-once là một giả định nguy hiểm

Lịch sử Durable Functions giúp tái tạo **quyết định điều phối**, nhưng activity có thể bị chạy lại khi lỗi hoặc retry/delivery. Do đó side effect phải được thiết kế idempotent. Không áp dụng lời hứa "chạy đúng một lần" cho thanh toán, gửi email hay tạo đơn hàng chỉ vì workflow dùng Durable Functions.

### 8.5. Timeout ở nhiều lớp

Không đồng nhất:

- HTTP client timeout khi activity gọi API ngoài.
- Function invocation timeout theo hosting plan.
- Durable timer deadline của workflow.
- Retention/history timeout/capacity.
- Business SLA hoặc hợp đồng thời hạn phê duyệt.

Chờ bằng durable timer có thể kéo dài hơn thời gian sống một worker invocation, nhưng một activity thực thi CPU 4 giờ vẫn phải phù hợp plan và thiết kế.

## 9. Batching và giới hạn fan-out

### 9.1. Vì sao không lập lịch 500.000 activities cùng lúc?

- History events tăng mạnh.
- Input/output của task_all có thể rất lớn.
- Storage backend phải ghi nhiều messages/transactions.
- Replay tốn thời gian, memory.
- Downstream API có thể trả hàng loạt 429.
- Chi phí log/transactions tăng.
- Khó xác định nhóm item lỗi và phục hồi.

**Fan-out N hoạt động không có nghĩa N đồng thời chạy**; runtime và quota sẽ giới hạn. Nhưng lượng task đã lên lịch và lịch sử vẫn có thể gây áp lực lớn.

### 9.2. Batch pattern

~~~text
50.000 item IDs
  ├─ batch 1: 100 IDs → fan-out → fan-in → lưu summary
  ├─ batch 2: 100 IDs → fan-out → fan-in → lưu summary
  ├─ ...
  └─ batch 500: 100 IDs → fan-out → fan-in → lưu summary
                             |
                             v
                       Final aggregate
~~~

Pseudocode:

~~~python
# PSEUDOCODE trong orchestrator, không phải function hoàn chỉnh.
for batch in chunk(items, batch_size=100):
    tasks = [context.call_activity("process_item", x) for x in batch]
    results = yield context.task_all(tasks)
    yield context.call_activity("persist_batch_summary", results)
~~~

Nếu 500 batches vẫn khiến một orchestration giữ history dài, dùng sub-orchestrations hoặc continue-as-new, hoặc lưu tiến độ ngoài theo chiến lược phù hợp.

### 9.3. Concurrency per worker không phải global rate limit

maxConcurrentActivityFunctions là một setting có thể điều tiết số activities mỗi worker instance theo runtime/version. Khi Function App scale-out thành 10 instances, tổng số hoạt động có thể lớn hơn cấu hình per-worker.

Nếu đối tác giới hạn 30 calls/giây toàn hệ thống, cần:

- Distributed limiter/semaphore phù hợp, hoặc cấp phát batches theo quota.
- Backoff/retry cho 429 có giới hạn.
- Monitoring request rate, queue depth và latency.
- Kiểm tra công suất toàn App Service Plan/Functions plan.
- Cân nhắc di chuyển bước heavy/long CPU sang AKS/Batch/Container Apps Jobs.

### 9.4. Sub-orchestrations

~~~mermaid
flowchart TD
    P["Parent Orchestrator"] --> A["Child: nhóm A"]
    P --> B["Child: nhóm B"]
    P --> C["Child: nhóm C"]
    A --> A1["Activities A"]
    B --> B1["Activities B"]
    C --> C1["Activities C"]
    A1 --> F["Parent fan-in"]
    B1 --> F
    C1 --> F
    F --> O["Final result"]
~~~

Lợi ích: chia trách nhiệm, theo dõi từng nhóm, retry/timeout riêng và giảm độ phức tạp logic parent. Nhưng sub-orchestrations vẫn tạo state/history và không tự giới hạn toàn bộ concurrency.

## 10. HTTP 202 và quy trình chạy dài

### 10.1. Async Request-Reply

Một API nghiệp vụ có thể tạo job như sau:

~~~http
POST /api/jobs
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
Idempotency-Key: report-001

{"documentSetId":"batch-2026-001"}
~~~

Trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/jobs/report-001
Retry-After: 10

{"jobId":"report-001","state":"Accepted"}
~~~

Đây là **API contract do ứng dụng thiết kế**, không phải tự động được tạo từ Durable Functions. Client:

1. Gửi request với business ID/idempotency key.
2. Nhận 202 và job ID.
3. Poll status theo interval/backoff hợp lý.
4. Nhận Completed/Failed/TimedOut/Terminated theo contract.
5. Tải output riêng có authorization nếu output lớn/nhạy cảm.

### 10.2. Vì sao cần idempotency ngay tại starter?

Nếu server đã tạo instance nhưng response 202 bị mất, client sẽ retry POST. Nếu mỗi POST tự tạo instance mới, có thể sinh hai workflows.

Cần mapping business ID → orchestration ID, được bảo vệ bởi unique constraint hoặc conditional write; hoặc dùng instance ID theo nghiệp vụ có xử lý race/duplicate đúng semantics SDK. Không mặc định start_new cùng ID là đủ để chặn mọi race.

### 10.3. Status payload

~~~json
{
  "jobId": "report-001",
  "state": "Running",
  "progress": {
    "total": 1000,
    "completed": 780,
    "failed": 6
  },
  "resultReference": null
}
~~~

Schema trên là của ứng dụng. Durable runtime có các trạng thái/management APIs riêng; UI/API nên dịch chúng sang business states như AwaitingApproval, PartialCompleted hoặc TimedOut nếu cần.

### 10.4. Quản lý management URLs

create_check_status_response có thể trả statusQueryGetUri, sendEventPostUri, terminatePostUri, purgeHistoryDeleteUri hoặc URL khác tùy phiên bản. Một số chứa key trong query string. Không công khai những URL này cho mọi người dùng, nhất là khả năng terminate/purge/raise event. Nên dùng API wrapper xác thực Entra ID và kiểm tra job ownership theo tenant.

## 11. Durable timer: chờ mà không sleep

### 11.1. Ví dụ chờ 15 phút

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def delayed_check(context: df.DurableOrchestrationContext):
    task_id = context.get_input()["taskId"]
    deadline = context.current_utc_datetime + timedelta(minutes=15)

    yield context.create_timer(deadline)
    result = yield context.call_activity("check_partner_status", task_id)
    return result
~~~

check_partner_status cần được đăng ký riêng thành activity. Khi đang chờ timer, workflow được lưu trạng thái, không giữ một thread Python chạy vòng sleep liên tục.

### 11.2. Tránh time.sleep

Sai trong orchestrator:

~~~python
import time

def wrong_delay(context):
    time.sleep(900)
    return "done"
~~~

time.sleep giữ worker và không theo semantics durable timer. Nếu activity cần chờ giờ/ngày, cũng nên xem lại kiến trúc vì invocation timeout và tài nguyên worker.

### 11.3. Thời gian UTC và deadline

Dùng context.current_utc_datetime để tính deadline trong orchestrator, không dùng datetime.now/utcnow. Nếu business deadline theo giờ Việt Nam, chuyển đúng timezone ra UTC và lưu deadline theo schema rõ ràng.

Khi event và deadline xảy ra sát nhau, định nghĩa policy chấp nhận dựa trên timestamp nào. Không để race network tự quyết định một giao dịch quan trọng.

## 12. Human interaction: phê duyệt có hạn

### 12.1. Workflow

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Activity: chuẩn bị
    participant U as Approver
    participant E as Event API
    O->>A: Prepare report
    A-->>O: Report ID
    O->>U: Notify qua activity
    O->>O: Wait external event or timer
    U->>E: Approve/Reject
    E->>O: DecisionReceived
    O->>O: Validate decision/state
    O-->>U: Approved / Rejected / TimedOut
~~~

Gửi email hoặc notification phải chạy trong activity; orchestrator chỉ lên lịch activity đó.

### 12.2. Python orchestration

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def approval_orchestrator(context: df.DurableOrchestrationContext):
    request_id = context.get_input()["requestId"]

    review = yield context.call_activity("prepare_review", request_id)
    yield context.call_activity("notify_approver", review)

    deadline = context.current_utc_datetime + timedelta(hours=48)
    decision_task = context.wait_for_external_event("DecisionReceived")
    timer_task = context.create_timer(deadline)

    winner = yield context.task_any([decision_task, timer_task])

    if winner == timer_task:
        return {"requestId": request_id, "status": "TimedOut"}

    timer_task.cancel()
    decision = decision_task.result

    if decision.get("approved") is True:
        yield context.call_activity("finalize_approved", request_id)
        return {"requestId": request_id, "status": "Approved"}

    return {"requestId": request_id, "status": "Rejected"}
~~~

Các activities phải được định nghĩa riêng và idempotent. Đây là ví dụ orchestration, chưa bao gồm code ingress nhận quyết định. Cần xử lý event đến muộn, cancel pending tasks theo khả năng SDK và tránh duplicate decisions.

### 12.3. Gửi external event an toàn

Tại một API đã xác thực và kiểm tra người dùng được phép approve request/tenant:

~~~python
await client.raise_event(
    instance_id,
    "DecisionReceived",
    {"approved": True},
)
~~~

**Không coi instance ID là secret hoặc bằng chứng quyền.** API phải kiểm tra:

- Người gửi có role duyệt tương ứng không?
- Request ID thuộc tenant/dự án của người đó không?
- Workflow đã quá hạn hoặc đã được quyết định chưa?
- Event có bị gửi lặp không?
- Audit có actor, timestamp UTC và correlation ID không?
- Payload có chứa credential hay dữ liệu nhạy cảm không?

Nếu approval đến rất gần deadline, xác định rõ quy tắc ai thắng và cần reconciliation nếu hệ thống đã phát email hoặc thay trạng thái bên ngoài.

### 12.4. Quy trình phê duyệt không phải transaction nguyên tử

Ví dụ người duyệt bấm Approve, API nhận thành công nhưng event tới orchestrator bị delay. Nếu client retry, có thể gửi nhiều event. Cần idempotent decision store và business state transition có điều kiện. Durable event dùng để **đánh thức orchestration**, không nhất thiết là nguồn sự thật duy nhất cho các quyết định pháp lý/tài chính.

## 13. Monitor pattern: polling job bên ngoài

### 13.1. Khi không có webhook

Đối tác trả job ID và hỗ trợ API kiểm tra trạng thái:

~~~text
POST /exports → {"jobId":"export-4242"}
GET /exports/export-4242 → {"state":"pending"}
GET /exports/export-4242 → {"state":"completed"}
~~~

Monitor pattern:

1. Activity kiểm tra trạng thái.
2. Completed → trả kết quả.
3. Failed → đánh dấu lỗi.
4. Pending → durable timer.
5. Timer đến hạn → kiểm tra lại, tới deadline thì timeout.

### 13.2. Python minh họa

~~~python
from datetime import timedelta

@app.orchestration_trigger(context_name="context")
def monitor_export(context: df.DurableOrchestrationContext):
    job_id = context.get_input()["jobId"]
    deadline = context.current_utc_datetime + timedelta(hours=6)

    while context.current_utc_datetime < deadline:
        status = yield context.call_activity("read_export_status", job_id)

        if status == "completed":
            return {"jobId": job_id, "status": "Completed"}
        if status == "failed":
            return {"jobId": job_id, "status": "Failed"}

        next_check = context.current_utc_datetime + timedelta(minutes=10)
        yield context.create_timer(next_check)

    return {"jobId": job_id, "status": "TimedOut"}
~~~

read_export_status là activity gọi API ngoài; không gọi trực tiếp từ orchestrator. Với external webhook được bảo vệ, dùng external event có thể giảm số polling calls.

### 13.3. Bẫy monitor không có điểm dừng

Nếu poll mỗi phút trong nhiều tháng, history tăng liên tục. Cần deadline, maxAttempts, alert khi stuck và dùng continue-as-new hoặc chia lifecycle phù hợp. Một workflow định kỳ đơn giản có thể chỉ cần TimerTrigger Function, không nhất thiết một eternal orchestrator.

## 14. Continue-as-new và quy trình lặp dài

### 14.1. Vì sao history tăng?

Mỗi activity schedule/completion, timer/event và output có thể tạo event history. Khi một orchestration xử lý hàng trăm nghìn lượt, replay trở nên tốn thời gian và storage transactions.

**continue-as-new** giúp tiếp tục với input mới đồng thời rút gọn lịch sử theo runtime. Ví dụ xử lý từng trang dữ liệu:

~~~text
Round 1: cursor=0    → xử lý 100 tệp → continue_as_new(cursor=100)
Round 2: cursor=100  → xử lý 100 tệp → continue_as_new(cursor=200)
...
Round N: không còn tệp → Completed
~~~

### 14.2. Pseudocode

~~~python
# PSEUDOCODE: giả định load_batch/process_item đã được đăng ký.
@app.orchestration_trigger(context_name="context")
def incremental_workflow(context: df.DurableOrchestrationContext):
    state = context.get_input() or {"cursor": 0}
    batch = yield context.call_activity("load_batch", state["cursor"])

    if not batch["items"]:
        return {"status": "Completed", "cursor": state["cursor"]}

    tasks = [
        context.call_activity("process_item", item_id)
        for item_id in batch["items"]
    ]
    yield context.task_all(tasks)

    context.continue_as_new({"cursor": batch["nextCursor"]})
~~~

**Chú ý:** việc tăng cursor chỉ an toàn khi các item của batch được ghi nhận hoàn tất hoặc có idempotent retry. Continue-as-new không tự bảo đảm database giao dịch ngoài đã commit.

### 14.3. Những điều cần kiểm soát

- Số batch tối đa và deadline tổng thể.
- Metadata tiến độ bền vững, không chỉ output cuối.
- Trường hợp một item bị lỗi vĩnh viễn.
- External events đang chờ khi rollover lịch sử: semantics tùy provider/SDK, phải kiểm thử.
- Dừng/cancel/terminate theo chính sách.
- Migration version code khi instance sống qua nhiều release.
- Chi phí state storage và log.

### 14.4. Eternal orchestrations

Timer + continue-as-new có thể triển khai quy trình giám sát định kỳ trong thời gian dài. Nhưng không nên duy trì vô hạn nếu không có owner, stop condition, alert và retention plan. Nhiều tác vụ theo lịch thuần túy phù hợp TimerTrigger Function hơn.

## 15. Saga và compensation cho nhiều side effects

### 15.1. Bài toán đặt hàng

Một đơn hàng cần giữ tồn kho, thanh toán, tạo vận đơn. Nếu vận đơn thất bại sau khi đã trừ tiền, retry từ đầu có thể làm trừ tiền thêm lần nữa.

~~~mermaid
flowchart TD
    O["Order Created"] --> A["Reserve inventory"]
    A --> P["Charge payment"]
    P --> S["Create shipment"]
    S -->|OK| D["Order Completed"]
    S -->|Fail| R["Refund payment"]
    R --> U["Release inventory"]
    U --> X["Failed / Manual review"]
~~~

### 15.2. Compensation không phải rollback nguyên tử

Hoàn tiền có thể mất vài ngày, cần phí, có trạng thái trung gian hoặc chính nó có thể lỗi. Do vậy:

- Ghi operation IDs và audit.
- Tạo compensation activities idempotent.
- Retry có giới hạn rồi đưa vào manual review.
- Không báo hoàn tất nếu các bước bù trừ chưa đạt policy.
- Không xóa dấu vết giao dịch trước đó.

### 15.3. Pseudocode

~~~python
# PSEUDOCODE: các activity cần thiết kế side effect idempotent.
reserve = yield context.call_activity("reserve_inventory", order)

try:
    payment = yield context.call_activity("charge_payment", order)
    try:
        shipment = yield context.call_activity("create_shipment", order)
    except Exception:
        yield context.call_activity("refund_payment", payment)
        raise
except Exception:
    yield context.call_activity("release_inventory", reserve)
    raise
~~~

Trong thực tế, phải xử lý trường hợp compensation cũng lỗi và tránh vô tình chạy compensation hai lần. Các quy tắc transaction ở database, đối soát tài chính và external API cần được mô hình hóa riêng.

## 16. Versioning khi instance đang chạy

### 16.1. Đổi code orchestrator có thể phá replay

Instance bắt đầu bằng version v1 có thể replay bằng code mới v2 sau deployment. Nếu v2 thêm activity vào giữa lịch sử hoặc đổi logic không tương thích, runtime có thể gặp nondeterministic error.

~~~text
Version 1: A → B → C
Version 2: A → NEW → B → C
~~~

Khi một instance v1 đã hoàn tất A và chờ B, thay code theo v2 mà không có versioning có thể tạo sequence mới trái history.

### 16.2. Chiến lược

1. Đặt tên orchestrator mới như ProcessInvoicesV2 khi đổi flow lớn.
2. Giữ v1 code cho instances cũ tới khi kết thúc, theo chính sách deployment.
3. Version field trong input, giữ quyết định deterministic.
4. Kiểm tra schema versions của activity input/output.
5. Thử replay với instances thật/tình huống chờ lâu ở staging.
6. Ghi build SHA và deployment date.
7. Dùng versioning/deployment capability chính thức được Durable runtime hỗ trợ khi phù hợp.

Không lấy một app setting CURRENT_VERSION có thể đổi sau deploy làm điều kiện rẽ nhánh cho instance đang replay nếu lần chạy trước đã đi đường khác.

### 16.3. Backward compatible result

~~~json
{
  "schemaVersion": 2,
  "documentId": "invoice-001",
  "status": "processed",
  "resultRef": "results/invoice-001.json"
}
~~~

Định nghĩa default cho field mới và chỉ xóa field cũ khi không còn orchestrator chạy phiên bản trước cần nó.

## 17. Bảo vệ state storage và dữ liệu

### 17.1. Những gì có thể nằm trong history

Tùy provider/extension, history có thể chứa:

- Input và output orchestration.
- Activity inputs/results.
- Timer và external event payloads.
- Failure details/exception metadata.
- Custom status và runtime instance metadata.

Do đó **đừng truyền raw tài liệu khách hàng, PII/secret, access token hoặc SAS URI dài hạn** qua orchestration. Input nên là ID/Blob path; activity dùng managed identity để đọc dữ liệu thật.

### 17.2. Tham chiếu thay vì payload lớn

Không nên:

~~~json
{
  "documents": [
    {"id":"001","contentBase64":"<HÀNG_MB_DỮ_LI>"}
  ]
}
~~~

Nên:

~~~json
{
  "jobId":"job-001",
  "documentRefs":[
    {"id":"001","blobPath":"incoming/job-001/001.pdf"}
  ]
}
~~~

Activity phải kiểm tra input ID hợp lệ và tenant ownership trước khi đọc blob; không chỉ dựa vào việc path có trong request.

### 17.3. Quyền task hub

Nếu dùng Azure Storage provider:

- Cấu hình AzureWebJobsStorage/provider theo runtime và plan.
- Cấp quyền Blob/Queue/Table cần thiết cho Functions host/extension.
- Dùng managed identity khi provider và hosting hỗ trợ, tránh account key theo khả năng.
- Cấu hình VNet/Private Endpoint/DNS phù hợp.
- Tách task hubs và môi trường không được chia sẻ.
- Giới hạn quyền xem/xóa state và logs.
- Theo dõi usage, throttling và retention.

Không xóa queues/tables của Durable provider để "dọn log" khi còn instance chưa kết thúc.

### 17.4. Purge history

Durable APIs có thể cho phép purge history sau khi instance kết thúc theo quy tắc được hỗ trợ. Đây là thao tác phá trạng thái, phải theo retention/privacy/audit policy. Không coi purge là cách an toàn để sửa một workflow đang stuck; hãy điều tra và quyết định recovery trước.

## 18. Bảo mật HTTP, events và danh tính

| Bề mặt | Nguy cơ | Kiểm soát |
|---|---|---|
| HTTP starter | Caller tạo hàng nghìn jobs gây tốn phí | Entra authentication, authorization, quota/rate limit |
| Status/management URLs | Ai có URL/key có thể xem/điều khiển job | Wrapper API có auth, không lộ keys |
| External event API | Người lạ giả mạo approval | Identity verification, role, tenant ownership, audit |
| Activities | Secret leak, quyền quá rộng | Managed identity, Key Vault, RBAC tối thiểu |
| Task hub storage | Đọc hoặc xóa history | Storage encryption, RBAC, network và retention |
| CI/CD | Code chưa phê duyệt được deploy production | OIDC/WIF, approvals, branch protection |
| Logs | PII, access tokens, payload bị ghi lại | Data minimization và quyền truy cập |
| Retries | Giao dịch bị nhân đôi | Idempotency/deduplication |

**Function key không thay thế business authorization.** Một URL quản lý có key trong query string không được xem là đủ để chứng minh người dùng sở hữu job. Với ứng dụng đa tenant, phải kiểm tra caller identity và tenant mapping cho từng job.

Tách các identity:

- Caller tạo job.
- Function managed identity gọi Storage/Key Vault.
- Approver identity.
- CI/CD deploy identity.
- Đối tác API hoặc service account bên ngoài.

Không cấp chung quyền Owner cho tất cả các vai trò. Những activity của cùng một Function App có thể dùng cùng managed identity; nếu cần ranh giới quyền thật sự khác biệt, cân nhắc tách apps hoặc ranh giới chạy được hỗ trợ.

## 19. Monitoring và troubleshooting

### 19.1. Theo dõi cả kỹ thuật và nghiệp vụ

| Trường | Tác dụng |
|---|---|
| businessJobId | Tra cứu theo nghiệp vụ |
| durableInstanceId | Tra cứu state/history |
| orchestrationVersion | Kiểm soát replay/versioning |
| currentStage | Fan-out, fan-in, approval hoặc finalize |
| state | Running/Completed/Failed/Terminated... |
| total/completed/failed | Tiến độ xử lý |
| createdAtUtc/updatedAtUtc | SLA và job age |
| correlationId | Truy vết across services |
| outputRef | Vị trí kết quả an toàn |
| errorCode | Phân loại sự cố |
| taskHub/environment | Tách dev/staging/prod |

Có thể dùng customStatus theo SDK để báo tiến độ ở mức tổng hợp; không lưu toàn bộ payload lớn hoặc cập nhật quá dày chỉ để phục vụ UI.

### 19.2. Nguồn telemetry

- Azure Functions host logs.
- Application Insights: requests, exceptions, dependencies, traces.
- Durable instance management/status APIs.
- Storage/task hub provider metrics và queue diagnostics.
- Azure Monitor alerts.
- Key Vault/Storage/Entra logs.
- CI/CD release records.
- Business metrics: SLA, số job hoàn tất, side effects và reconciliation.

Không mặc định Azure Activity Log có mọi hoạt động của Durable runtime hoặc mọi lần đọc Blob; cần bật logging ở đúng data plane và kiểm soát retention.

### 19.3. KQL minh họa

Với workspace-based Application Insights có AppExceptions:

~~~kusto
AppExceptions
| where TimeGenerated > ago(1h)
| summarize Failures = count()
  by bin(TimeGenerated, 5m), ProblemId
| order by TimeGenerated asc
~~~

Với AppRequests:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize Requests = count(),
            Failed = countif(Success == false),
            P95ms = percentile(DurationMs, 95)
  by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

Tên bảng/cột phụ thuộc cấu hình telemetry và schema thực tế. Query rỗng không chứng minh ứng dụng không có lỗi nếu logs chưa được ingest.

### 19.4. Alert hữu ích

- Job Running quá SLA hoặc không tiến bộ.
- Failed orchestrations hoặc activity failures tăng.
- 429/503/retry tăng bất thường.
- Task hub queue backlog hoặc storage throttling.
- Approval quá hạn và event đến trễ.
- Activity latency p95 tăng.
- Chi phí storage transactions/Functions/Log Analytics tăng.
- Deployment mới trùng thời gian nhiều instance gặp nondeterministic errors.
- Ngừng nhận telemetry hoặc external event bất thường.

Running khi đang đợi approval hợp lệ không phải stuck; alert phải hiểu **currentStage và deadline**.

## 20. Scale và chi phí

### 20.1. Nguồn giới hạn

- Số workers/instances theo hosting plan.
- maxConcurrentActivityFunctions và các runtime settings theo phiên bản.
- Task hub backend capacity, queues và partitions.
- CPU/memory của activities.
- Kích thước history/payload.
- Downstream API quotas/DB connections.
- Cold start và tốc độ scale.
- Network/Private Endpoint và token acquisition.

Một orchestrator chỉ nên điều phối. Nếu phải tổng hợp hàng GB dữ liệu, dùng activity hoặc dịch vụ xử lý dữ liệu chuyên dụng; không nhét toàn bộ vào orchestration history.

### 20.2. Ví dụ ước lượng

Có 2.000 tài liệu, mỗi request phân tích khoảng 3 giây; API giới hạn tối đa 40 requests đồng thời:

- Tuần tự lý tưởng gần 6.000 giây.
- 40 đồng thời lý tưởng gần 50 đợt × 3 giây = 150 giây.
- Thực tế cộng storage, queue, network, cold start, retry, aggregation.
- Gửi 2.000 requests cùng lúc dễ gặp 429, tăng lỗi và chi phí.

Đây là mô hình tính minh họa, **không phải benchmark hay cam kết Azure**.

### 20.3. Tính phí end-to-end

- Functions invocations, execution time và resources theo plan.
- Storage/task hub messages, transactions và retention.
- Key Vault operations, Blob/Queue/Service Bus.
- Application Insights/Log Analytics ingestion và retention.
- Network egress/Private Endpoint.
- API đối tác tính phí per request/token.
- Retry nhân số yêu cầu.
- Chi phí capacity always-ready/provisioned khi dùng.

Durable timer không giữ thread khi chờ nhưng **không có nghĩa mọi chi phí chờ đều bằng 0**. Storage/telemetry/plan vẫn có thể phát sinh phí.

## 21. Tình huống thực tế: 10.000 hóa đơn cần phê duyệt

### 21.1. Bối cảnh

Doanh nghiệp cần:

1. Liệt kê 10.000 hóa đơn mới từ Blob Storage.
2. Chia batches và phân tích từng tệp.
3. Lưu kết quả từng hóa đơn.
4. Tổng hợp báo cáo/những lỗi cần xử lý.
5. Gửi thông báo người quản lý.
6. Chờ approval tối đa 48 giờ.
7. Nếu Approved, phát hành báo cáo; nếu Rejected/TimedOut, giữ và đánh dấu trạng thái.

### 21.2. Kiến trúc

~~~mermaid
flowchart TD
    U["Portal/API"] --> H["HTTP Starter 202"]
    H --> P["Parent Durable Orchestrator"]
    P --> L["List document refs"]
    L --> B["Sub-orchestrations theo batch"]
    B --> A1["Analyze A"]
    B --> A2["Analyze B"]
    B --> A3["Analyze C"]
    A1 --> F["Batch fan-in"]
    A2 --> F
    A3 --> F
    F --> D["Ghi output Blob/DB"]
    D --> G["Global summary"]
    G --> N["Notify approver"]
    N --> W["External event or 48h timer"]
    W -->|Approved| R["Publish"]
    W -->|Rejected/Timeout| X["Hold + audit"]
~~~

### 21.3. Quyết định thiết kế

| Quyết định | Chọn | Vì sao |
|---|---|---|
| Orchestration input | Job ID và Blob IDs | Giảm history size |
| Fan-out | Batches giới hạn | Tránh bão activity/API |
| Activity output | Metadata và resultRef | Không chứa PDF lớn |
| Retry | 429/503 giới hạn | Bảo vệ quota |
| Dedup | (jobId, invoiceId, operation) | Tránh side effect trùng |
| Fan-in | Per-batch rồi global summary | Dễ quan sát |
| Human approval | External event + 48h timer | Chờ dài không giữ thread |
| Business result | Approved/Rejected/TimedOut | Trạng thái minh bạch |
| Version | Giữ v1/v2 tương thích | Replay an toàn |
| Security | Entra, managed identity, RBAC, private networking | Kiểm soát truy cập |
| Observability | App Insights + business progress | Theo dõi SLA |
| Retention | Theo policy data/history | Privacy và cost |

### 21.4. Acceptance tests

- Restart Function App khi đang chờ activity/timer, instance vẫn tiếp tục theo runtime state.
- Trường hợp một activity lỗi có retry/partial-failure policy rõ.
- Không có duplicate invoice nếu HTTP caller retry hoặc activity được chạy lại.
- Approval đến trước deadline hoạt động; đến sau deadline không tự publish.
- Reviewer không đúng role không gửi được event.
- Không có raw PDF/access token trong history/logs.
- Code v2 triển khai không phá phiên v1 còn chạy.
- Có cost metrics, SLA alert và cleanup/retention policy.
- Khi downstream hỏng, có reconciliation/manual intervention.

## 22. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Starter trả 500 | Durable binding/host storage/runtime lỗi | Host logs, storage connection, packages |
| 202 nhưng job không tiến | Task hub/queue, worker chưa xử lý | Instance status, provider diagnostics |
| Activity chạy trùng | Retry/delivery/duplicate starter | Operation ID, dedup, history |
| Orchestrator nondeterministic | Gọi time/random/I/O hoặc đổi code | Replay constraints, versioning |
| Log orchestrator trùng | Replay | context.is_replaying và log strategy |
| Fan-in mãi chưa xong | Activity stuck/fail, quota | Failed tasks, queue backlog, timeout |
| 429 nhiều | Downstream throttling | Batch size, retries và concurrency |
| State/history quá lớn | Truyền payload hoặc quá nhiều fan-out | Blob references, batching |
| Approval không được nhận | Sai instance/event, auth, instance đã kết thúc | Event API logs, status, correlation |
| Deadline sai | Dùng local clock/timezone | Logical UTC và timer |
| Upgrade code làm lỗi jobs cũ | Incompatible orchestrator changes | Versioning/deployment records |
| Storage 403 | Identity thiếu quyền hoặc firewall/DNS | RBAC data plane và networking |
| Management URL bị lộ | Key nằm trong query/log | Thu hồi key, wrapper API auth |
| Terminate nhưng activity vẫn tác động | Terminate không hủy side effects đã bắt đầu | Cooperative cancellation, reconciliation |
| Cleanup làm mất instance | Xóa task hub/history sai | Retention policy, backup/recovery |
| Chi phí tăng đột ngột | Retry/fan-out/log quá nhiều | Budget, usage, backpressure |

### 22.1. Quy trình điều tra

1. Xác minh caller, request ID và instance ID.
2. Kiểm tra host/runtime/extension versions.
3. Xem trạng thái task hub/provider, quyền Storage và network.
4. Xác định activity/timer/event đang chờ.
5. Kiểm tra error codes, retries và downstream quota.
6. Kiểm tra history/replay và deployment code version.
7. Đối chiếu business side effects, không tự retry toàn job.
8. Xác minh output và reconciliation.
9. Ghi incident, rollback/change ticket và cải tiến alert.

**Terminate không tự động đảo ngược một thanh toán, gửi email hoặc một activity đã bắt đầu.** Khi cần cancellation, thiết kế flag/operation state mà activities kiểm tra ở các checkpoint và compensation khi thích hợp.

## 23. Checklist production

### Workflow

- [ ] Cần stateful orchestration thật, không chỉ queue consumer độc lập.
- [ ] Có sơ đồ orchestrator, activities, sub-orchestrations, timers, events.
- [ ] Có fan-in policy all-or-nothing/partial.
- [ ] Fan-out size và concurrency phù hợp downstream quotas.
- [ ] Activities có retry giới hạn và idempotency.
- [ ] Có timeout/deadline, không dùng sleep lâu trong orchestrator.
- [ ] Có cách xử lý external event duplicate/late.
- [ ] Continue-as-new/batching cho history dài khi cần.
- [ ] Versioning không phá instance cũ.
- [ ] Có quy trình cancel/compensation.

### Bảo mật và dữ liệu

- [ ] Starter/status/event APIs có authentication/authorization.
- [ ] Không để quản lý URL/key lộ qua log/frontend.
- [ ] Orchestration input/output nhỏ, không chứa secrets/PII lớn.
- [ ] Task hub Storage có RBAC/network/retention đúng.
- [ ] Managed identity/Key Vault bảo vệ downstream.
- [ ] Có dedup cho operation IDs và event IDs.
- [ ] CI/CD roles và business approver roles tách biệt.
- [ ] Audit logs không chứa token/payload nhạy cảm.

### Kiểm thử

- [ ] Thử một, vài chục và hàng trăm activities trong lab.
- [ ] Thử partial failure, 429, timeout và retry.
- [ ] Thử restart/scale-in khi chờ timer/event.
- [ ] Thử approval trước/sau deadline, gửi lặp.
- [ ] Thử caller retry sau khi response 202 bị mất.
- [ ] Thử deploy v2 khi workflow v1 còn Running.
- [ ] Thử terminate lúc activity có side effect.
- [ ] Kiểm tra storage transactions, history size và latency.
- [ ] Có rollback code + reconciliation dữ liệu.

### Vận hành

- [ ] Dashboard Running/Completed/Failed/TimedOut và business stages.
- [ ] Alert job không tiến bộ, API throttling, backlog, approval quá hạn.
- [ ] Runbook identity/storage/provider/network.
- [ ] Owner cho workflow và manual intervention.
- [ ] Theo dõi chi phí Functions/Storage/Monitor/downstream.
- [ ] Purge history chỉ sau khi đáp ứng retention policy.
- [ ] Kế hoạch capacity và rate-limit đã được thử.

## 24. Tự kiểm tra kiến thức

1. **Tại sao HTTP Function thường không nên giữ kết nối hai ngày?** Timeout/worker lifecycle không cung cấp durable state.
2. **Durable Functions thêm điều gì?** Stateful orchestration, history/replay, durable timers và external events.
3. **Orchestrator và activity khác nhau?** Điều phối quyết định so với thao tác I/O/side effects.
4. **Fan-out là gì?** Chia danh sách thành nhiều activities độc lập.
5. **Fan-in là gì?** Chờ và tổng hợp kết quả theo policy.
6. **task_all có đảm bảo 500 activities chạy cùng lúc không?** Không.
7. **Nếu một activity lỗi thì fan-in có thể ra sao?** Failed, retry hoặc partial tùy thiết kế.
8. **Tại sao cần idempotency?** Activity có thể được retry/deliver lại sau khi side effect đã xảy ra.
9. **Exactly-once có tự được bảo đảm cho external API không?** Không.
10. **Vì sao datetime.now không phù hợp orchestrator?** Không deterministic khi replay.
11. **Thay time.sleep bằng gì?** context.create_timer với logical UTC.
12. **Dùng gì để chờ người duyệt?** wait_for_external_event kết hợp timer/task_any.
13. **External event có tự xác thực approver không?** Không; ingress API phải kiểm tra.
14. **202 trả về để làm gì?** Tách request khỏi công việc dài, cho client theo dõi status.
15. **Vì sao cần chống POST duplicate tại starter?** Response bị mất khiến caller retry và tạo hai instances.
16. **Continue-as-new có ích gì?** Tiếp tục vòng lặp với history được làm gọn.
17. **Monitor pattern hoạt động thế nào?** Activity kiểm tra trạng thái, durable timer chờ, lặp có deadline.
18. **Sub-orchestration giúp gì?** Chia workflow thành các nhóm có trạng thái riêng.
19. **Saga compensation là DB rollback nguyên tử?** Không, là bù trừ nghiệp vụ có thể lỗi.
20. **Tại sao deploy v2 có thể làm phiên v1 lỗi?** Replay yêu cầu code quyết định tương thích với history.
21. **Có nên lưu raw PDF vào orchestration input?** Không; dùng Blob reference.
22. **Task hub storage phải bảo vệ gì?** State/history/messages/credentials/retention.
23. **Function key có thay business authorization không?** Không.
24. **Terminate có hoàn tác giao dịch đã xảy ra không?** Không.
25. **Tại sao cần rate limit toàn cục?** Nhiều workers có thể cùng vượt downstream quota.
26. **Running lúc chờ approval có phải stuck?** Không, phụ thuộc stage/deadline.
27. **Chi phí chỉ gồm execution time?** Không; còn storage, logs, network, retry và downstream.
28. **Có thể thay fan-in lớn bằng queue độc lập?** Có nếu không cần hợp nhất kết quả.
29. **Cách điều tra duplicate?** Xem business/operation ID, history, retries và API logs.
30. **Workflow chạy dài đáng tin cậy cần gì?** Deterministic orchestration, idempotent activities, bounded retries, bảo mật event, monitoring, versioning và recovery.

## 25. Tài liệu tham khảo

- [Durable Functions overview](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview) — khái niệm và patterns.
- [Durable Functions application patterns](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview#application-patterns) — async HTTP, fan-out/fan-in, monitor, human interaction.
- [Fan-out/fan-in example](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-cloud-backup) — chia và tổng hợp công việc.
- [Python programming model v2](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-python-v2-programming-model) — decorators, client, orchestrator, activities.
- [Orchestrator code constraints](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-code-constraints) — deterministic/replay.
- [Durable HTTP APIs](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-http-api) — quản lý instance, event và status.
- [Durable timers](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-timers) — timer chờ bền vững.
- [External events](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-external-events) — human interaction và callbacks.
- [Error handling](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-error-handling) — retry/failure.
- [Performance and scale](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-perf-and-scale) — concurrency/partitioning.
- [Durable Functions versioning](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-versioning) — code changes và instances chạy dài.
- [Storage providers](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-storage-providers) — trạng thái và task hubs.
- [Durable Functions diagnostics](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-diagnostics) — logging và tracing.
- [Azure Functions hosting](https://learn.microsoft.com/azure/azure-functions/functions-scale) — hosting plans, scale và chi phí.
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — runtime identity.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — kiểm soát chi phí.

**Kết luận:** fan-out/fan-in chia công việc thành các activity độc lập rồi hợp nhất kết quả; Durable Functions duy trì trạng thái và lịch sử để điều phối quy trình kéo dài mà không giữ HTTP connection liên tục. Để sản xuất an toàn, cần **orchestrator deterministic, activity idempotent, bounded retries, payload nhỏ, external events có quyền, versioning cho instance cũ, monitoring và kế hoạch compensation/recovery**. Một workflow thành công không chỉ là trạng thái Completed mà còn phải chứng minh không tạo giao dịch trùng, chịu được restart và xử lý được khi hệ thống phụ thuộc thất bại.
