# Workflows connectors, HTTP calls và xác thực

> **Chương:** Điều phối và tích hợp ứng dụng  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một dịch vụ bán hàng nhận yêu cầu xử lý đơn hàng: gọi API nội bộ chạy trên **Cloud Run** để kiểm tra trạng thái, phát sự kiện sang **Pub/Sub**, và khi cần liên lạc với đối tác qua HTTPS. Viết các lời gọi trực tiếp trong một HTTP request có thể tạo chuỗi phụ thuộc khó retry, khó theo dõi và khó xác định bước nào thất bại. **Google Cloud Workflows** giúp biểu diễn quá trình đó thành các **bước có trạng thái, rẽ nhánh, retry và kết quả thực thi**.

Bài thuộc chương **Điều phối và tích hợp ứng dụng** của mô-đun **CLOUD_PROVIDERS_GCP**, kết nối kiến thức về project/IAM, Cloud Run, Pub/Sub, Secret Manager và khả năng quan sát. Trọng tâm là ba lựa chọn cần phân biệt:

- **Workflows connector** (`googleapis.*`): gọi API của sản phẩm Google Cloud qua hàm tích hợp, tự xử lý xác thực IAM và một số cơ chế retry/long-running operation.
- **HTTP call** (`http.get`, `http.post`, `http.request`): gọi endpoint HTTP/HTTPS như Cloud Run, API Google không có connector, hoặc API đối tác.
- **Xác thực**: chọn đúng **OIDC ID token**, **OAuth 2.0 access token** hoặc credential riêng của bên thứ ba; không đánh đồng quyền gọi API với đường đi mạng.

**Sau bài học, bạn có thể:**

1. Viết Workflows YAML với `params`, `steps`, `assign`, `call`, `result`, `switch` và `return`.
2. Chọn connector thay vì HTTP trực tiếp cho API Google Cloud khi có phương thức được hỗ trợ.
3. Gọi Cloud Run có xác thực bằng `auth.type: OIDC` và API `*.googleapis.com` bằng `OAuth2`.
4. Gọi Pub/Sub bằng connector, mã hóa payload Base64 đúng định dạng và xử lý kết quả.
5. Quản lý runtime service account, quyền IAM, Secret Manager và credentials bên thứ ba.
6. Áp dụng timeout, retry, idempotency, `try/except` và theo dõi logs an toàn.
7. Triển khai/test một workflow và chẩn đoán lỗi 401/403/404/429/5xx.
8. Đánh giá khi nào cần Service Directory để gọi private endpoint trong VPC.

## 1. Workflows đứng ở đâu trong kiến trúc?

~~~mermaid
flowchart LR
    START["Caller / Cloud Scheduler / Eventarc"] -->|"Workflows execution"| WF["Google Cloud Workflows\nCác bước điều phối"]
    WF -->|"HTTPS + OIDC ID token"| RUN["Cloud Run\norders-read API"]
    WF -->|"Pub/Sub connector + IAM"| PS["Pub/Sub topic\norders-events"]
    WF -->|"Secret Manager connector"| SM["Secret Manager\ncredential đối tác"]
    WF -->|"HTTPS + external auth"| EXT["Partner API"]
    WF --> MON["Execution history\nCloud Logging / Monitoring"]
~~~

**Workflows là công cụ điều phối, không phải runtime cho logic tính toán nặng.** Nó phù hợp khi quá trình gồm nhiều lời gọi API, các nhánh quyết định, chờ kết quả hoặc cần nhìn lại một execution. Xử lý CPU-intensive, thao tác dữ liệu lớn hay xử lý hàng triệu bản ghi nên đặt trong **Cloud Run jobs, Cloud Functions, Dataflow, BigQuery** hoặc dịch vụ chuyên dụng rồi Workflows gọi chúng.

### 1.1. Ba khái niệm thường bị nhầm

| Khái niệm | Ví dụ | Ai chịu trách nhiệm? |
| --- | --- | --- |
| **Workflow definition** | `orders-orchestrator.yaml` | Mô tả các bước; được deploy thành một Workflows resource |
| **Execution** | Một lần chạy với `order_id=ord-123` | Workflows quản lý trạng thái, thời gian, lỗi và kết quả |
| **Workflow runtime identity** | `wf-orders@PROJECT_ID.iam.gserviceaccount.com` | Service account dùng khi Workflows gọi tài nguyên khác |

**Người khởi chạy execution** và **runtime service account** là **hai danh tính khác nhau**. Người gọi có thể chỉ có `roles/workflows.invoker`; runtime account phải có quyền của từng đích đến, ví dụ `roles/run.invoker` và `roles/pubsub.publisher`.

### 1.2. YAML và dữ liệu giữa các bước

Ví dụ không gọi mạng:

~~~yaml
main:
  params: [args]
  steps:
    - initialize:
        assign:
          - order_id: ${args.order_id}
          - current_status: "received"
    - check_order:
        switch:
          - condition: ${order_id == ""}
            next: invalid_order
        next: success
    - invalid_order:
        raise: "order_id must not be empty"
    - success:
        return:
          order_id: ${order_id}
          status: ${current_status}
~~~

Lệnh `assign` đặt biến cho execution; `switch` chọn nhánh; `raise` tạo lỗi; `return` kết thúc và trả kết quả. Workflows expressions nằm trong `${...}` và được tính khi **chạy**. Mọi giá trị trong ví dụ đều là giả định, không có Google Cloud resource nào được gọi.

**Lưu ý YAML:** Nếu một biểu thức Workflows chứa dấu hai chấm, ngoặc hoặc dấu nháy làm YAML parser hiểu sai, hãy đặt toàn biểu thức trong **nháy đơn YAML**. Không dùng tab để thụt lề.

## 2. Chọn connector hay HTTP call

| Tiêu chí | Workflows connector | HTTP call |
| --- | --- | --- |
| Cú pháp | `call: googleapis.<service>.<version>.<method>` | `call: http.get/post/put/delete/request` |
| Đích phổ biến | Các **Google Cloud APIs** có connector | Cloud Run service, REST Google API, SaaS/partner API, private HTTP endpoint |
| Xác thực | Tự sử dụng workflow service account | Phải khai báo `auth` cho OIDC/OAuth2 hoặc header riêng |
| Request/response | Theo schema API method; `args` thường gồm resource name, body | URL, query, headers, body, status code và response body |
| Retry | Có chính sách tích hợp theo method | Tự thêm `try/retry` nếu cần |
| Long-running operation | Một số connector tự poll đến khi xong | Tự tổ chức polling/callback nếu API không có helper |
| Quyền | Runtime service account cần IAM đối với resource | IAM/OIDC, OAuth scope hoặc credential của nhà cung cấp tùy đích |

**Connector không phải HTTP proxy chung.** Không dùng `googleapis.run.v2...` chỉ để gọi một HTTP handler chạy trên Cloud Run: connector Cloud Run API phục vụ **quản trị tài nguyên Cloud Run**. Để gọi **endpoint của ứng dụng**, sử dụng `http.get`/`http.post` và OIDC.

### 2.1. Khi dùng connector

Một số nhóm phương thức:

- `googleapis.pubsub.v1.projects.topics.publish` — phát message vào Pub/Sub topic.
- `googleapis.secretmanager.v1.projects.secrets.versions.access` — đọc một secret version.
- `googleapis.bigquery.v2.jobs.query` — gửi SQL query tới BigQuery.
- `googleapis.storage.v1.objects.get` — lấy metadata của object Cloud Storage.
- Những hàm quản lý Cloud Run/GKE/Compute/Firestore khác tùy danh sách connector hiện hành.

Connector **không loại bỏ** yêu cầu bật API, IAM, quota, chi phí hoặc định dạng arguments. Cần đọc đúng schema trong **Workflows Connectors reference** thay vì suy tên method từ HTTP URL.

### 2.2. Khi dùng HTTP

- Gọi **Cloud Run app URL** có authentication.
- Gọi REST endpoint bên thứ ba, ví dụ payment/shipping provider.
- Gọi Google API qua `https://SERVICE.googleapis.com/...` khi không có connector phù hợp.
- Gọi private HTTP endpoint thông qua **Service Directory** (phần sau).

**Phân biệt cách xác thực:** Google Cloud APIs dùng **OAuth2 access token**; Cloud Run invocations thường dùng **OIDC ID token**; external API phụ thuộc hệ thống đó (API key, bearer token, OAuth2, mTLS...). Một token có chữ “Bearer” trong header không bảo đảm đúng loại token.

## 3. Runtime service account, IAM và ba nhóm xác thực

~~~mermaid
flowchart TD
    WF["Execution: Workflows runtime SA"] --> C{"Đích đến?"}
    C -->|"Google connector"| GOOGLE["IAM tự động\nGoogle API permissions"]
    C -->|"googleapis.com HTTP"| OAUTH["auth.type: OAuth2\nAccess token"]
    C -->|"Cloud Run HTTPS"| OIDC["auth.type: OIDC\nID token + audience"]
    C -->|"Partner HTTPS"| APIKEY["Header/API key/OAuth của partner\nCredential trong Secret Manager"]
    GOOGLE --> R["Kiểm tra quyền ở resource đích"]
    OAUTH --> R
    OIDC --> R
    APIKEY --> P["Kiểm tra quyền ở hệ thống đối tác"]
~~~

### 3.1. Quyền tối thiểu theo vai trò

| Ai thực hiện | Quyền thường cần | Phạm vi |
| --- | --- | --- |
| CI/deployer | Quyền tạo/update Workflows resource; quyền `iam.serviceAccounts.actAs` | Project và runtime SA |
| Người/ứng dụng gọi workflow | `roles/workflows.invoker` | Workflow/project phù hợp |
| **Workflow runtime SA → Cloud Run** | `roles/run.invoker` | **Callee Cloud Run service** |
| Runtime SA → Pub/Sub | `roles/pubsub.publisher` | **Đúng topic** |
| Runtime SA → Secret Manager | `roles/secretmanager.secretAccessor` | **Đúng secret** |
| Runtime SA → một Google API khác | Permissions riêng của API | Project/dataset/bucket/resource tương ứng |
| Workflows service agent | Vai trò hệ thống được Google quản lý; quyền bổ sung khi dùng Service Directory | Khác runtime SA |

**Không** gán `roles/editor`/Owner cho runtime SA vì một HTTP call trả 403. Xác định method, project chứa resource, principal thực tế, audience/scope và org policy trước khi sửa IAM.

### 3.2. OIDC: gọi Cloud Run

~~~yaml
- call_cloud_run:
    call: http.post
    args:
      url: https://orders-api-EXAMPLE-uc.a.run.app/process
      auth:
        type: OIDC
        audience: https://orders-api-EXAMPLE-uc.a.run.app
      headers:
        Content-Type: application/json
      body:
        order_id: "ord-123"
    result: run_response
~~~

- `type: OIDC` khiến Workflows cấp **ID token** dùng runtime SA.
- `audience` nên là **service root URL** của Cloud Run (không gồm `/process`), trừ khi callee có **custom audiences** được cấu hình.
- Callee phải cho phép runtime SA gọi qua **`roles/run.invoker`** và có **ingress policy** tương thích.
- Với `http.post`, request thành công thường nằm trong `run_response.body` và `run_response.code`.

**Không đặt access token OAuth2 thay ID token** cho endpoint Cloud Run có xác thực mặc định. Lệnh `auth` tự tạo header Authorization; không tự chèn bearer token giả vào cùng request.

### 3.3. OAuth2: gọi Google REST API không qua connector

~~~yaml
- get_project:
    call: http.get
    args:
      url: https://cloudresourcemanager.googleapis.com/v3/projects/LAB_PROJECT_ID
      auth:
        type: OAuth2
        # scopes: https://www.googleapis.com/auth/cloud-platform
    result: project_response
~~~

Cơ chế này dành cho HTTPS endpoint có hostname kết thúc bằng `.googleapis.com`; scope mặc định là `https://www.googleapis.com/auth/cloud-platform`. **Scopes không thay IAM permissions**: account vẫn phải có quyền API, ví dụ xem project metadata. Không sao chép mẫu OAuth2 rồi dùng cho bất kỳ hostname đối tác nào.

### 3.4. Bên thứ ba: credentials từ Secret Manager

Với partner API cần static API token, có thể đọc secret bằng helper Workflows:

~~~yaml
- load_partner_token:
    call: googleapis.secretmanager.v1.projects.secrets.versions.accessString
    args:
      secret_id: "partner-api-token"
      version: "7"
      project_id: ${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
    result: partner_token

- call_partner:
    call: http.get
    args:
      url: https://api.partner.example.com/v1/status
      headers:
        Authorization: ${"Bearer " + partner_token}
    result: partner_response
~~~

Đây là **đoạn steps mẫu**, không phải workflow hoàn chỉnh; `api.partner.example.com` là tên giả. Account phải có Secret Accessor trên đúng secret, nhà cung cấp phải chấp nhận kiểu Bearer này, request phải dùng HTTPS. **Không log `partner_token` hoặc `partner_response` nếu có dữ liệu nhạy cảm.**

**Cảnh báo quan trọng:** `--call-log-level=log-all-calls` có thể ghi tham số hoặc response call, gồm cả **giá trị secret trả về từ `accessString`**, vào Cloud Logging. Trong hệ thống xử lý credentials/PII, ưu tiên mức logging thấp, giảm nội dung execution history theo chính sách và dùng `sys.log` chỉ với thông tin đã loại bỏ bí mật.

## 4. HTTP calls: URL, headers, body, kết quả và lỗi

Các hàm chuẩn thường dùng là `http.get`, `http.post`, `http.put`, `http.patch`, `http.delete` và `http.request` khi cần method tùy chọn. Mỗi lời gọi có:

~~~yaml
- fetch_order:
    call: http.get
    args:
      url: https://example.com/orders/ord-123
      headers:
        Accept: application/json
      query:
        include_items: true
      timeout: 30
    result: response
~~~

Nếu API trả JSON với `Content-Type: application/json`, Workflows thường giải mã body thành map/list, dùng `response.body.status` hoặc `response.body["status"]`. Nếu đích trả text/binary, cần xử lý đúng loại dữ liệu, không giả định luôn có field `status`.

### 4.1. Ý nghĩa các trường

| Thuộc tính | Cách dùng |
| --- | --- |
| `url` | URL chính xác; hạn chế dùng hostname/path lấy từ input chưa được kiểm chứng |
| `headers` | Header dạng map; tránh log credentials |
| `query` | Map được URL-encode theo tham số |
| `body` | JSON map/list hoặc payload phù hợp; API cần hỗ trợ |
| `auth` | `OIDC` hoặc `OAuth2` khi Workflows hỗ trợ đích |
| `timeout` | Timeout **mỗi HTTP request**, không phải toàn workflow |
| `result` | Biến nhận response để bước sau dùng |
| `try/retry/except` | Retry những lỗi có thể phục hồi và bắt lỗi cuối |

Theo tài liệu, HTTP request mặc định timeout **300 giây**, tối đa **1.800 giây** cho một request; phải thiết kế theo timeout của callee. Nếu một job kéo dài nhiều giờ, không giữ một HTTP request chờ vô hạn; dùng connector LRO, polling có giới hạn hoặc callback/sự kiện.

### 4.2. HTTP response và exceptions

- Với 2xx, `result` thường có `code`, `headers`, `body`.
- Với HTTP 4xx/5xx, Workflows thường **raise `HttpError`** thay vì đi tiếp đến bước sử dụng `result`.
- Timeout/connection error có tag khác; không mặc định mọi error đều có `e.code`.
- Workflows errors có `tags` và `message`; xem `except` để phân loại.

Ví dụ xử lý 404 **không retry vô ích**:

~~~yaml
- lookup:
    try:
      call: http.get
      args:
        url: https://example.com/orders/ord-123
      result: order_response
    except:
      as: e
      steps:
        - handle_not_found:
            switch:
              - condition: ${"HttpError" in e.tags and e.code == 404}
                next: return_not_found
            next: rethrow_other_error
        - return_not_found:
            return:
              status: "not-found"
        - rethrow_other_error:
            raise: ${e}
~~~

Dùng `raise: ${e}` cho lỗi không xử lý được để execution thất bại có bằng chứng, thay vì luôn return thành công dù bước gọi backend lỗi.

## 5. Retry, idempotency và long-running operations

### 5.1. Retry HTTP đúng loại thao tác

Workflows có các policy mặc định:

| Policy | Đối tượng nên dùng | Lỗi được retry |
| --- | --- | --- |
| `http.default_retry` | Lời gọi **idempotent**, thường GET | 429, 502, 503, 504 và một số connection/timeout errors |
| `http.default_retry_non_idempotent` | POST/side effect không có bảo đảm idempotent | 429, 503 hoặc connection failure theo policy mặc định |

Ví dụ GET:

~~~yaml
- check_inventory:
    try:
      call: http.get
      args:
        url: https://inventory.example.com/items/sku-123
        timeout: 20
      result: inventory
    retry: ${http.default_retry}
~~~

Policy mặc định dùng tối đa **5 retries**, backoff tăng dần. Retry thêm **steps billed**, tăng độ trễ và có thể làm traffic tới backend tăng. Nếu cần giới hạn thấp hơn, khai báo `retry.predicate`, `max_retries` và `backoff`.

### 5.2. Vì sao POST cần idempotency key?

Một workflow gửi `POST /payments`, backend **đã ghi thanh toán** nhưng response bị mất; Workflows tưởng lỗi và thử lại. Nếu backend tạo giao dịch mới mỗi POST, khách hàng bị thu tiền hai lần.

**Thiết kế phòng tránh:**

- Truyền **idempotency key** duy nhất theo nghiệp vụ, ví dụ `payment_id`, để backend phát hiện request lặp.
- Ghi trạng thái theo key vào database với unique constraint/transaction.
- Chỉ retry những lỗi và phương thức đã có hợp đồng idempotency rõ.
- Nếu thao tác trước thành công nhưng thao tác sau thất bại, dùng **compensation/saga** khi nghiệp vụ cho phép.
- Pub/Sub có thể giao message lại; consumer cần **deduplication**, Workflows không biến mọi side effect thành exactly-once.

**Đừng cho `POST` dùng retry idempotent chỉ vì nó gọi một endpoint nội bộ.** Quyết định dựa tính chất nghiệp vụ, không dựa hostname.

### 5.3. Connector retries và polling LRO

Connector tích hợp retry cho Google API operations; với long-running operation (LRO) được hỗ trợ, connector có thể **chờ và poll** cho tới khi hoàn tất hoặc lỗi. Theo tài liệu, timeout mặc định các request là **30 phút**; timeout cho toàn LRO có thể cấu hình qua `connector_params`. Polling là các bước **có thể bị tính phí**, nên không đặt poll interval cực ngắn cho job chạy hàng giờ.

**Connector không ngụ ý “mọi API call sẽ tự chạy lại đến khi thành công”.** Nếu lỗi quyền hoặc dữ liệu không hợp lệ, cần sửa nguyên nhân; nếu operation đã thực hiện một phần, xử lý compensation/reconciliation trước khi chạy execution mới.

## 6. Ví dụ end-to-end: Cloud Run → Pub/Sub

### 6.1. Bối cảnh và hợp đồng API

- Cloud Run service **`orders-read`** cung cấp `GET /orders/{order_id}`, yêu cầu authenticated invoker và trả JSON kiểu `{"id":"ord-123","status":"READY"}`.
- Pub/Sub topic **`orders-events`** tồn tại và thuộc project lab.
- Workflow **`orders-orchestrator`** nhận input `{"order_id":"ord-123"}`, gọi Cloud Run bằng OIDC và publish event bằng connector.
- Runtime service account chỉ có `roles/run.invoker` trên `orders-read` và `roles/pubsub.publisher` trên `orders-events`.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant W as Workflows
    participant R as Cloud Run orders-read
    participant P as Pub/Sub orders-events
    C->>W: Execute(order_id)
    W->>R: GET /orders/{id} + OIDC ID token
    R-->>W: 200 {"status":"READY"}
    W->>P: Pub/Sub connector publish(Base64 JSON)
    P-->>W: messageIds
    W-->>C: Execution result
~~~

**Quan trọng:** Đây là ví dụ phát **sự kiện đã đọc/kiểm tra**, không thực hiện thanh toán hay thay đổi đơn hàng. Nếu dùng POST tạo giao dịch, phải thiết kế idempotency và error recovery riêng.

### 6.2. Toàn bộ Workflows YAML

Tạo file `orders-orchestrator.yaml` **trên máy lab** (không phải trong thư mục bài học này):

~~~yaml
main:
  params: [args]
  steps:
    - init:
        assign:
          - project_id: ${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}
          - run_url: ${sys.get_env("RUN_SERVICE_URL")}
          - topic_id: ${sys.get_env("TOPIC_ID")}
          - order_id: ${args.order_id}

    - get_order:
        try:
          call: http.get
          args:
            url: ${run_url + "/orders/" + order_id}
            auth:
              type: OIDC
              audience: ${run_url}
            timeout: 30
          result: order_response
        retry: ${http.default_retry}

    - build_event:
        assign:
          - event:
              event_type: "order.checked"
              order_id: ${order_id}
              status: ${order_response.body.status}
          - encoded_event: ${base64.encode(json.encode(event))}

    - publish_event:
        call: googleapis.pubsub.v1.projects.topics.publish
        args:
          topic: ${"projects/" + project_id + "/topics/" + topic_id}
          body:
            messages:
              - data: ${encoded_event}
                attributes:
                  origin: "orders-orchestrator"
        result: publish_result

    - done:
        return:
          order_id: ${order_id}
          checked_status: ${order_response.body.status}
          message_ids: ${publish_result.messageIds}
~~~

**Giải thích theo thứ tự:**

1. `sys.get_env` lấy project và hai **user-defined environment variables** của workflow. `RUN_SERVICE_URL` phải là URL gốc Cloud Run, **không có slash cuối**, ví dụ `https://orders-read-...run.app`.
2. `http.get` gọi đường dẫn `/orders/ord-123`; OIDC `audience` là root Cloud Run URL.
3. Backend giả định trả JSON có field `status`; nếu API trả text hoặc field khác, phải sửa mapping.
4. `json.encode(event)` tạo bytes; `base64.encode(...)` đáp ứng định dạng `PubsubMessage.data`.
5. Connector `googleapis.pubsub.v1.projects.topics.publish` dùng workflow service account, trả `messageIds`.
6. Workflow trả **metadata** thay vì trả secret hay toàn bộ response nhạy cảm.

**Giới hạn đầu vào:** Example xây URL từ `order_id`. Production phải validate cho phép chỉ các ký tự an toàn trong path (ví dụ chữ/số/dấu gạch nối) hoặc URL-encode đúng; không nối URL từ input không tin cậy. Xử lý input thiếu `order_id` và HTTP 404 theo hợp đồng nghiệp vụ, không publish nếu GET thất bại.

**Lưu ý duplicate:** HTTP GET retry an toàn khi nó không tạo side effect; riêng bước Pub/Sub publish có thể bị thực hiện lại nếu execution được chạy lại hoặc request thành công nhưng response mất. Consumer nên dùng `event_id/order_id` để loại duplicate khi yêu cầu nghiệp vụ cần điều đó.

## 7. Triển khai và kiểm thử workflow

**Bối cảnh lab:** Project `LAB_PROJECT_ID`; region `asia-southeast1`; Cloud Run service `orders-read` đã có endpoint trả JSON đúng hợp đồng; Pub/Sub topic `orders-events` đã tồn tại. Bạn có một service account riêng `wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com`.

**Không chạy các lệnh thay đổi IAM/deploy này trên production nếu chưa có phê duyệt.** Workflows, Cloud Run, Pub/Sub và Cloud Logging có thể phát sinh phí. Không chạy demo với dữ liệu đơn hàng thật.

### 7.1. Đọc preflight

~~~bash
# Chỉ đọc, tránh nhầm project và region
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud run services describe orders-read \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud pubsub topics describe orders-events \
  --project=LAB_PROJECT_ID

gcloud iam service-accounts describe \
  wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --project=LAB_PROJECT_ID
~~~

Nếu service account chưa có, người quản trị được cấp quyền tạo **trong project lab**:

~~~bash
# Thay đổi project; chỉ chạy khi được phép
gcloud iam service-accounts create wf-orders \
  --display-name="Workflows orders runtime" \
  --project=LAB_PROJECT_ID
~~~

Đảm bảo **Workflows API** và APIs đích được bật trong project phù hợp. Một workflow chỉ cần connector hoặc HTTP call **không** yêu cầu lưu Google Cloud service account key trên máy hoặc trong source YAML.

### 7.2. Cấp quyền cho runtime identity

~~~bash
# Cloud Run callee: cho phép runtime SA gọi đúng service
gcloud run services add-iam-policy-binding orders-read \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Pub/Sub topic: cho phép publish, không cấp Subscriber/Admin
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project=LAB_PROJECT_ID \
  --member="serviceAccount:wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

Người deploy phải có quyền quản lý workflow và **`iam.serviceAccounts.actAs`** trên `wf-orders`; người dùng gọi workflow cần quyền invoker **riêng**. Nếu Cloud Run và topic ở project khác, cấp IAM ở **project/resource đích**, không chỉ project chứa Workflows.

### 7.3. Deploy workflow cùng environment variables

~~~bash
# Thay đổi Workflows resource; RUN_SERVICE_URL là URL thật của Cloud Run
gcloud workflows deploy orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --source=orders-orchestrator.yaml \
  --service-account=wf-orders@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=RUN_SERVICE_URL=https://orders-read-EXAMPLE-as.a.run.app,TOPIC_ID=orders-events
~~~

`RUN_SERVICE_URL` là **URL gốc** của Cloud Run service, không phải URL giả trong bài. Không dùng `https://orders-read-EXAMPLE-as.a.run.app` nguyên văn. Với workflow chỉ gọi một Cloud Run service, tên env var không phải credential; **đừng để passwords/API keys trong Workflows environment variables** khi Secret Manager phù hợp hơn.

Kiểm tra definition:

~~~bash
gcloud workflows describe orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

### 7.4. Thực thi bằng dữ liệu giả

~~~bash
# Tạo một execution và đợi kết quả; CÓ GỌI Cloud Run và publish Pub/Sub
gcloud workflows run orders-orchestrator \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --data='{"order_id":"ord-123"}'
~~~

Kết quả mong đợi khi Cloud Run trả `{"id":"ord-123","status":"READY"}`:

~~~json
{
  "order_id": "ord-123",
  "checked_status": "READY",
  "message_ids": ["MESSAGE_ID_FROM_PUBSUB"]
}
~~~

`MESSAGE_ID_FROM_PUBSUB` là placeholder. Kết quả workflow ghi nhận publish được Pub/Sub chấp nhận, **không** chứng minh subscriber đã xử lý hoàn tất. Nếu cần xác nhận downstream, phải dùng phản hồi sự kiện/callback hoặc trạng thái riêng.

Có thể dùng `gcloud workflows execute` để **khởi chạy không đợi** và sau đó kiểm tra trạng thái execution. Trong Google Cloud Console: **Workflows → chọn workflow → Executions** để xem bước thành công/lỗi.

### 7.5. Các tình huống test an toàn

| Test | Hành vi mong đợi |
| --- | --- |
| `order_id=ord-123` tồn tại | Cloud Run trả 200; Pub/Sub nhận message |
| `order_id` không tồn tại | HTTP 404; workflow thất bại hoặc trả lỗi có cấu trúc nếu thêm `except` |
| Workflow SA thiếu `run.invoker` | HTTP auth/permission error, không tới publish |
| Workflow SA thiếu Pub/Sub Publisher | Cloud Run GET có thể thành công; connector publish bị từ chối |
| Cloud Run trả 503 tạm thời | `http.default_retry` có thể thử lại rồi fail nếu quá giới hạn |
| Topic không tồn tại | Publish connector báo lỗi resource, không tự tạo topic |

**Dọn lab:** Chỉ xóa workflow/topic/service account nếu chúng do chính bài lab tạo và không còn caller/subscriber phụ thuộc. Việc xóa topic có thể mất dữ liệu subscription và phá integration; cần xác minh ownership trước.

## 8. Connector nâng cao: Pub/Sub, Secret Manager và LRO

### 8.1. Pub/Sub publish thực hiện điều gì?

Workflow hoàn chỉnh ở mục 6 dùng `googleapis.pubsub.v1.projects.topics.publish`. Pub/Sub đòi `data` ở dạng **Base64 string**: `json.encode` tạo bytes, `base64.encode` tạo Base64 text. `attributes` là metadata chuỗi cho routing/filter subscriptions, không được chứa PII hoặc secrets.

**Không mặc định có exactly-once side effects:** nếu workflow retries hoặc replay execution, có thể publish nhiều messages tương đương. Consumer cần contract/idempotency phù hợp.

### 8.2. Secret Manager: hai cách đọc

| Connector | Kết quả | Khi dùng |
| --- | --- | --- |
| `googleapis.secretmanager.v1.projects.secrets.versions.access` | Response có `payload.data` Base64 | Cần xử lý bytes/metadata |
| `googleapis.secretmanager.v1.projects.secrets.versions.accessString` | String UTF-8 đã giải mã | Credential là text |

Ví dụ với `access`:

~~~yaml
- get_secret_version:
    call: googleapis.secretmanager.v1.projects.secrets.versions.access
    args:
      name: projects/LAB_PROJECT_ID/secrets/partner-token/versions/7
    result: secret_response

- decode_secret:
    assign:
      - partner_token: ${text.decode(base64.decode(secret_response.payload.data))}
~~~

**Không return hay ghi log `partner_token`.** Khi gọi `accessString`, tránh bật `log-all-calls` vì connector có thể đưa plaintext secret vào response logs. Việc lấy secret qua Workflows vẫn cần **Secret Accessor** trên đúng secret; đừng cấp quyền project-wide nếu chỉ cần một credential.

### 8.3. Long-running operation: kiểm soát chi phí poll

Một số Google APIs như tạo tài nguyên hoặc chạy batch job trả **long-running operation**. Connector có thể **poll** tới trạng thái cuối, tránh phải viết `while + sys.sleep + http.get` cho từng API.

- Kiểm tra connector method có hỗ trợ xử lý LRO không.
- Dùng `connector_params` theo reference để điều chỉnh **timeout tổng** và polling policy.
- Theo dõi quota, timeout và lỗi `OperationError`; bản thân operation có thể đã có side effect dù workflow không nhận kết quả mong muốn.
- Polling mỗi lần có thể được tính **một billable step**, nên không giảm interval vô tội vạ.

**Không coi tất cả connector call đều là LRO**: đọc metadata GCS và publish Pub/Sub là các operation thông thường.

## 9. Gọi private endpoint trong VPC

Nếu workflow cần gọi một **VM** hoặc internal HTTP backend chỉ có IP riêng, Workflows không tự được đặt vào subnet như một Compute Engine VM và không dùng trực tiếp Cloud Run **Direct VPC egress**. Google Cloud cung cấp tích hợp **Service Directory** để gửi HTTP request đến private VPC endpoint.

### 9.1. Điều kiện mạng

1. Tạo/đăng ký private endpoint trong **Service Directory namespace/service** tại region hợp lệ.
2. Đăng ký **một endpoint cho mỗi Service Directory service** khi dùng với Workflows; nếu có nhiều, Workflows có thể chọn bất kỳ endpoint nào.
3. Cấu hình VPC firewall, service listening port, đường trả lời và DNS.
4. Cấp cho **Workflows service agent** (khác runtime SA) quyền Service Directory Viewer và PSC Authorized Service theo hướng dẫn.
5. Nếu backend yêu cầu authentication, thiết kế **IAP/OIDC**, token hoặc mTLS theo capability được hỗ trợ.

### 9.2. Ví dụ HTTP private với Service Directory

~~~yaml
- check_private_inventory:
    call: http.get
    args:
      url: http://10.20.0.5:8080/health
      private_service_name: projects/LAB_PROJECT_ID/locations/asia-southeast1/namespaces/internal/services/inventory
      timeout: 15
    result: inventory_health
~~~

Đây là **địa chỉ IP ví dụ** và chỉ hoạt động sau khi thực sự tạo Service Directory service/endpoint, các IAM bindings và firewall tương ứng. Cơ chế này **không tự bảo đảm application authentication hoặc TLS cho endpoint HTTP**. Với dữ liệu nhạy cảm, yêu cầu HTTPS/mTLS hoặc IAP theo kiến trúc, không coi private IP là đủ bảo mật.

**Cloud Run ingress internal:** Theo tài liệu, Workflows có thể gọi Cloud Run có ingress hạn chế internal trong các điều kiện được hỗ trợ, nhưng vẫn cần `OIDC` và `run.invoker`. Không suy mọi URL private/internal hoặc custom domain đều được truy cập như một Cloud Run `run.app` URL.

## 10. Tính an toàn: đầu vào, lỗi, retries và trạng thái một phần

### 10.1. Kiểm tra đầu vào trước khi gọi

- Giới hạn format `order_id`; không xây URL/hostname từ chuỗi người dùng nhập nếu chưa validate.
- Không chèn secrets vào URL query hay workflow input.
- Với API có dữ liệu người dùng, kiểm tra authorize ở **backend**, không chỉ ở workflow.
- Tham số đầu vào có thể được lưu trong execution history, log hoặc audit theo cấu hình; không truyền tokens/passwords trong `--data`.
- Giới hạn kích thước payload; đối tượng dữ liệu lớn nên truyền **Cloud Storage object reference**, không trả toàn file qua các bước.

### 10.2. Ba trạng thái lỗi cần phân biệt

| Tình huống | Điều đã xảy ra | Chiến lược |
| --- | --- | --- |
| Cloud Run GET timeout trước khi nhận response | Không biết backend đã làm gì; GET lý tưởng idempotent | Retry bounded và điều tra timeout |
| Pub/Sub publish trả 403 | Cloud Run GET trước đó đã thành công, publish chưa được chấp nhận | Sửa IAM/topic, replay execution có kiểm soát |
| Publish thành công nhưng workflow mất response | Message có thể đã tồn tại | Không tự publish lại vô hạn; downstream dedupe |

**Không có distributed transaction tự động** xuyên Cloud Run, Pub/Sub và API đối tác. Nếu cần chuỗi cập nhật nhiều hệ thống, thiết kế **saga/compensation**, workflow state, durable idempotency keys và kiểm thử failure injection trong môi trường lab.

### 10.3. Retry policy có giới hạn

~~~yaml
- read_with_bounded_retry:
    try:
      call: http.get
      args:
        url: https://example.com/health
        timeout: 10
      result: resp
    retry:
      predicate: ${http.default_retry_predicate}
      max_retries: 3
      backoff:
        initial_delay: 2
        max_delay: 20
        multiplier: 2
~~~

Chọn `max_retries` theo SLO và sức chịu tải backend. Đối với 401/403 do quyền sai, retry không tự sửa IAM. Với 429/503, xem quota và capacity chứ không tăng số retries vô hạn.

### 10.4. Bắt lỗi và trả mã nghiệp vụ

Nếu muốn caller biết khác biệt giữa “đơn không có” và “hạ tầng lỗi”, định nghĩa error contract:

~~~yaml
- call_order:
    try:
      call: http.get
      args:
        url: https://example.com/orders/ord-123
      result: order_response
    except:
      as: e
      steps:
        - choose_error:
            switch:
              - condition: ${"HttpError" in e.tags and e.code == 404}
                next: not_found
            next: unexpected_error
        - not_found:
            return:
              ok: false
              reason: "order-not-found"
        - unexpected_error:
            raise: ${e}
~~~

Đừng return toàn bộ `e.body` cho người dùng nếu nó có stack trace, response payload, credentials hoặc PII. Trong production, cung cấp **correlation ID** và error category an toàn, lưu chi tiết lỗi ở logs được kiểm soát quyền.

## 11. Quan sát, vận hành, quota và chi phí

### 11.1. Theo dõi execution

Cloud Workflows lưu trạng thái execution như RUNNING/SUCCEEDED/FAILED và có **execution history** để biết bước nào đã chạy. Tại Console: Workflows → workflow → **Executions**; Cloud Logging có execution start/end logs theo cấu hình dịch vụ.

Các trường nên log **không chứa PII**:

- Correlation ID hoặc business key đã được cho phép.
- Workflow name, execution ID, version/revision đang chạy.
- Tên bước, thời gian bắt đầu/kết thúc, status.
- HTTP code/connector error tag và số lần retry.
- Pub/Sub message ID và downstream acknowledgment khi có.
- Thời gian xử lý tổng, số external calls và chi phí ước lượng.

### 11.2. Call logging và secrets

| Mức/thực hành | Rủi ro |
| --- | --- |
| `log-none` hoặc không log call details | Ít khả năng làm lộ payload/credentials; cần log nghiệp vụ tối thiểu khác |
| `log-errors-only` | Hữu ích khi debug, vẫn phải xem error body/headers có bí mật không |
| `log-all-calls` | **Rủi ro cao** khi gọi Secret Manager, API có bearer headers hoặc dữ liệu người dùng |
| `sys.log` tùy chọn | Cho phép kiểm soát nội dung, nhưng vẫn có phí và phải redact |
| Detailed execution history | Có thể lưu biến/trạng thái ở bước; đánh giá data classification/IAM |

**Không bật detailed history/call-all trong production chỉ vì khó tìm lỗi.** Trước khi tăng verbosity, kiểm tra retention, quyền xem logs, masking và chính sách dữ liệu. Cân nhắc ghi mã lỗi hoặc correlation ID thay vì lưu full HTTP body.

### 11.3. Chi phí cần tính

- Workflows tính phí theo **internal/external steps** tùy loại lời gọi; retries/polling làm tăng số bước.
- HTTP calls ra dịch vụ khác có thể gây **Cloud Run requests/compute, Pub/Sub messages, Secret Manager access, network egress**.
- Cloud Logging/Monitoring, Eventarc/Scheduler trigger, Service Directory, Cloud NAT hoặc backend private endpoint có thể có phí riêng.
- Có **quotas** về concurrency, execution history, request/response size, HTTP timeout; vượt quota có thể tạo 429/ResourceExhausted.
- Một workflow chạy hàng giờ vì chờ polling kém hiệu quả có thể rẻ hoặc đắt tùy số steps và dịch vụ được gọi; **đo trên Cloud Billing và Monitoring**, không đoán theo thời lượng đơn thuần.

**Tối ưu:** Kết hợp các `assign` hợp lý, chỉ retry lỗi tạm, dùng connector LRO/callback thay vì polling dày, giữ payload nhỏ và tránh log dư thừa.

## 12. Ma trận xử lý sự cố

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Deploy báo lỗi YAML | Sai thụt lề, expression chưa quote, sai field `steps/args` | Dùng cú pháp Workflows reference, kiểm tra dòng/step |
| Workflow chạy nhưng `args.order_id` lỗi | Input thiếu field hoặc sai map shape | Kiểm tra JSON `--data` và input validation |
| Cloud Run trả 401 | OIDC token/audience không hợp lệ | `auth.type=OIDC`, root service URL, custom audience |
| Cloud Run trả 403 | Runtime SA thiếu `run.invoker` hoặc ingress không cho nguồn | IAM của **callee**, ingress policy |
| Google API HTTP trả 401 | Sai `OAuth2`/scope hoặc endpoint | `*.googleapis.com`, auth block, API activation |
| Connector Pub/Sub trả 403 | Runtime SA không có Publisher trên topic | Topic IAM, project ID và topic name |
| Secret Manager access trả 403 | Thiếu Secret Accessor trên đúng secret/version | IAM, version existence |
| HTTP 404 | Sai URL/path; resource không tồn tại | Full path, Cloud Run handler, order ID |
| HTTP 429 | Quota, rate limit hoặc backend overload | Quota, Monitoring, backoff |
| HTTP 502/503/504 | Lỗi upstream/transient overload | Retry bounded, backend logs/SLO |
| Timeout | Quá `timeout`, network/connection hoặc backend chậm | HTTP timeout, Cloud Run request timeout, correlation ID |
| Pub/Sub message không thấy ở subscriber | Subscriber/subscription/filter chưa phù hợp | Message ID, topic, subscription, DLQ |
| Double processing | Execution replay/retry và thiếu idempotency | Dedupe keys, event IDs, consumer logs |
| Private endpoint không tới | Thiếu Service Directory/IAM/route/firewall | Service agent roles, endpoint registry, VPC |
| Credential xuất hiện trong logs | `log-all-calls` hoặc `sys.log` chứa response/token | Giảm logging, revoke/rotate secret, incident response |

**Quy tắc chẩn đoán:** Kiểm tra **workflow definition → runtime SA/IAM → token loại đúng → DNS/network → HTTP response/error → backend business logic → retries/side effects**. Không tăng IAM lên Editor hoặc bật anonymous Cloud Run invocation để “làm cho chạy”.

## 13. Bài lab tổng hợp và tiêu chí nộp bài

**Mục tiêu:** Hoàn thành một lần thực thi Cloud Run → Pub/Sub, chứng minh từng lớp xác thực và retry không làm mất khả năng truy vết.

| Bước | Thao tác | Bằng chứng |
| --- | --- | --- |
| 1 | Chọn project lab, Cloud Run service và Pub/Sub topic có sẵn | Tên resource, region, API enabled |
| 2 | Tạo runtime SA chuyên dụng | Email và IAM bindings tối thiểu |
| 3 | Deploy workflow YAML hoàn chỉnh | Workflow active, đúng URL/topic env |
| 4 | Chạy với `order_id=ord-123` | Execution SUCCEEDED |
| 5 | Xem Cloud Run logs và Pub/Sub publish result | Status JSON và message ID |
| 6 | Thử order ID không tồn tại | HTTP 404 và error handling phù hợp |
| 7 | Dùng một SA test thiếu Pub/Sub Publisher | Connector báo permission denied, không làm rò dữ liệu |
| 8 | Khôi phục IAM test/đánh giá idempotency | Không publish trùng ngoài ý muốn |
| 9 | Tùy chọn: mô hình Service Directory private endpoint | Sơ đồ IAM service agent + network |
| 10 | Dọn resources lab theo ownership | Không xóa resources dùng chung |

**Không đổi IAM của production SA để thử lỗi.** Tốt hơn là dùng bản workflow/service account test riêng, hoặc mô phỏng bằng case study khi không có sandbox.

### 13.1. Câu hỏi mở rộng

Giả sử Cloud Run trả 200, Pub/Sub publish cũng đã thành công, nhưng execution bị retry ở bước khác hoặc caller khởi chạy lại toàn workflow. Hãy thiết kế:

- `event_id` duy nhất cho cùng nghiệp vụ.
- Unique constraint/deduplication ở consumer.
- Trạng thái xử lý trong database theo key.
- Retry policy có thời hạn, DLQ cho lỗi kéo dài.
- Cách phát hiện “đã hoàn tất” mà không lặp tác vụ kinh doanh.

## 14. Bài tập tự kiểm tra

1. **Connector khác HTTP call ở đâu?** Connector dùng API method tích hợp và IAM, retry/LRO hỗ trợ; HTTP cần URL, headers/body và auth riêng.
2. **Cloud Run nên dùng token gì?** Google-signed **OIDC ID token** và caller cần `run.invoker`.
3. **Google REST API `*.googleapis.com` dùng token gì?** OAuth2 access token; scope không thay quyền IAM.
4. **External SaaS API có tự hỗ trợ `auth.type=OIDC` không?** Không mặc định; theo API contract, thường dùng credential riêng.
5. **Người gọi workflow có tự trở thành runtime SA không?** Không; invocation identity và workflow SA khác nhau.
6. **Có cần JSON service account key để Workflows gọi Pub/Sub không?** Không; connector dùng runtime identity.
7. **Pub/Sub connector yêu cầu payload `data` dạng gì?** Base64-encoded bytes, ví dụ `base64.encode(json.encode(event))`.
8. **Khi HTTP 404, Workflows có tự trả `response.code=404` như thành công không?** Thường raise HttpError, cần `except`.
9. **POST đã ghi dữ liệu nhưng mất response thì retry an toàn không?** Chỉ khi backend xử lý idempotency/compensation đúng.
10. **Retry GET 429/503 có tốn phí không?** Có thể tăng billed steps và latency.
11. **Service Directory private endpoint cần gì ngoài URL private IP?** Registration, service agent permissions, VPC route/firewall và app auth.
12. **LRO connector có thể chờ operation tới lúc xong không?** Có với những methods được hỗ trợ; polling tính phí theo bước.
13. **Có nên bật `log-all-calls` khi gọi `accessString`?** Không, vì secret plaintext có thể nằm trong logs.
14. **Workflow SUCCEEDED có bảo đảm Pub/Sub subscriber đã xử lý?** Không; publish acknowledgment khác downstream completion.
15. **Cloud Run 403 luôn là thiếu `run.invoker`?** Không; cũng cần kiểm tra ingress, principal, audience và org policy.
16. **Thời gian Workflows ở một region có bảo đảm mọi outbound call từ region đó?** Không; regionality của workflow và origin của HTTP request cần đánh giá riêng.

## 15. Checklist production và tài liệu chính thức

- [ ] Workflow có hợp đồng input/output, timeout, error contract và chủ sở hữu.
- [ ] Chọn connector khi phù hợp; HTTP khi gọi app endpoint hoặc API ngoài.
- [ ] Runtime SA chuyên dụng; `workflows.invoker` không bị nhầm với quyền của runtime SA.
- [ ] Cloud Run gọi bằng OIDC và đúng `audience`; Google APIs bằng OAuth2.
- [ ] Pub/Sub topic/Secret Manager IAM cấp trên đúng resource; không dùng Editor.
- [ ] Credential bên thứ ba trong Secret Manager, không trong source/YAML/logs.
- [ ] Có retry bounded theo idempotency; POST side effects và consumer có dedupe.
- [ ] 4xx/5xx, timeout và connector errors có handling/alert rõ ràng.
- [ ] Gọi private endpoint dùng Service Directory/IAP và routing hợp lệ khi cần.
- [ ] Không log request body/secret nhạy cảm; execution history và IAM đã review.
- [ ] Có Monitoring, correlation ID, alert cho execution FAILED và backend SLO.
- [ ] Đã tính Workflows steps/polling, API quotas, downstream costs và egress.
- [ ] Triển khai trên môi trường lab/canary; rollback workflow definition/version khi có lỗi.
- [ ] Có runbook reconciliation khi execution fail sau khi một số bước đã hoàn thành.

**Nguồn Google Cloud chính thức:**

- [Workflows overview](https://docs.cloud.google.com/workflows/docs/overview) — execution model, regionality và giới hạn.
- [Understand connectors](https://docs.cloud.google.com/workflows/docs/connectors) — IAM tự động, retries và LRO.
- [Connectors reference](https://docs.cloud.google.com/workflows/docs/reference/connectors) — danh sách `googleapis.*` và args schema.
- [Make an HTTP request](https://docs.cloud.google.com/workflows/docs/http-requests) — `http.get/post/request`, headers/body.
- [Authenticate from a workflow](https://docs.cloud.google.com/workflows/docs/authenticate-from-workflow) — OIDC, OAuth2 và external APIs.
- [Invoke Cloud Run from Workflows](https://docs.cloud.google.com/workflows/docs/calling-run-functions) — ID token và Invoker.
- [Publish Pub/Sub message](https://docs.cloud.google.com/workflows/docs/publish-pubsub-message) — Base64 payload và connector.
- [Secret Manager connector](https://docs.cloud.google.com/workflows/docs/use-secret-manager) — access/accessString, IAM.
- [Retry steps](https://docs.cloud.google.com/workflows/docs/reference/syntax/retrying) — predicates/backoff.
- [Catch errors](https://docs.cloud.google.com/workflows/docs/reference/syntax/catching-errors) — `try/except` và lỗi HTTP.
- [Invoke private endpoint using Service Directory](https://docs.cloud.google.com/workflows/docs/invoke-private-endpoint-vpc) — `private_service_name`, VPC và service agent.
- [Create/manage workflows](https://docs.cloud.google.com/workflows/docs/creating-updating-workflow) — deploy và runtime identity.
- [Send execution logs](https://docs.cloud.google.com/workflows/docs/log-workflow) — logging risk và history.
- [gcloud workflows run](https://docs.cloud.google.com/sdk/gcloud/reference/workflows/run) — thực thi có `--data`.
- [Workflows pricing](https://cloud.google.com/workflows/pricing) — internal/external steps.

**Ghi nhớ:** Dùng **connector** cho API Google Cloud khi có method phù hợp; dùng **HTTP + OIDC** để gọi Cloud Run, **HTTP + OAuth2** cho Google REST APIs và credentials riêng cho API đối tác. Đường mạng, IAM và xác thực ứng dụng là các lớp độc lập. Một workflow tin cậy phải có **retry có giới hạn, idempotency, quan sát được lỗi và không làm lộ secrets**.
