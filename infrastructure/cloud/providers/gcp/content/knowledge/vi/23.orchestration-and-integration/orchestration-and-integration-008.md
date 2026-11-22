# Lựa chọn Pub/Sub, Cloud Tasks, Scheduler hoặc Workflows trên Google Cloud

Một hệ thống bán lẻ dùng **Cloud Run** cho API đơn hàng, **GKE** cho worker, **Cloud SQL** lưu giao dịch và **Cloud Storage** chứa báo cáo. Khi một đơn được tạo, hệ thống cần gửi sự kiện cho nhiều bộ phận; sau 15 phút phải nhắc khách chưa thanh toán; mỗi đêm phải tổng hợp doanh thu; một quy trình hoàn tiền lại phải lần lượt xác minh đơn, gọi hệ thống thanh toán và cập nhật trạng thái. Cả bốn yêu cầu đều có yếu tố bất đồng bộ, nhưng **không nên ép chúng vào cùng một dịch vụ**.

Google Cloud có bốn lựa chọn bổ trợ nhau: **Pub/Sub** phân phối sự kiện, **Cloud Tasks** xếp hàng những lời gọi tác vụ cụ thể, **Cloud Scheduler** kích hoạt theo lịch lặp lại và **Workflows** điều phối nhiều bước có trạng thái. Bài học thuộc chương **Điều phối và tích hợp ứng dụng** của mô-đun **CLOUD_PROVIDERS_GCP**, liên hệ lựa chọn dịch vụ với IAM, VPC, triển khai, độ tin cậy và chi phí. Nội dung tự chứa, tập trung vào cách **ra quyết định, cấu hình và vận hành**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn đúng dịch vụ theo **event fan-out, tác vụ HTTP, cron** hoặc **quy trình nhiều bước**.
2. Phân biệt publisher/subscriber, task producer/handler, scheduler/target và workflow/execution.
3. Hiểu semantics **at-least-once**, retry, deduplication, idempotency, rate limit và khả năng ordering của từng dịch vụ.
4. Viết ví dụ `gcloud` tạo topic/subscription, task queue, cron job và triển khai Workflows.
5. Tách danh tính **người khởi tạo, dịch vụ chuyển giao và service account chạy ứng dụng**.
6. Thiết kế kiến trúc kết hợp các dịch vụ, đặt SLO, đo backlog, lỗi, latency và chi phí.

## 2. Bốn dịch vụ giải quyết bốn câu hỏi khác nhau

| Dịch vụ | Câu hỏi chính | Đơn vị công việc | Mô hình |
| --- | --- | --- | --- |
| **Pub/Sub** | “Có sự kiện xảy ra, ai quan tâm thì xử lý?” | Message trên topic, được giao tới subscriptions. | **Phân phối sự kiện**, một-nhiều, bất đồng bộ. |
| **Cloud Tasks** | “Hãy gọi endpoint này, có kiểm soát thời điểm/tốc độ/retry.” | Task trong queue, với HTTP target hoặc target được hỗ trợ. | **Gọi tác vụ cụ thể**, producer biết đích. |
| **Cloud Scheduler** | “Đến giờ này/hằng ngày hãy kích hoạt công việc.” | Cron job và một lần gửi tới target. | **Kích hoạt định kỳ**, không tự chạy logic nghiệp vụ. |
| **Workflows** | “Gọi A, đọc kết quả, quyết định có gọi B, rồi chờ C.” | Workflow definition và execution gồm nhiều steps. | **Điều phối có trạng thái**, theo thứ tự/rẽ nhánh/song song. |

Hình dung:

~~~mermaid
flowchart LR
    E["Đơn hàng đã tạo"] --> PUB["Pub/Sub topic"]
    PUB --> BILL["Subscription: lập hóa đơn"]
    PUB --> ANALYTICS["Subscription: phân tích"]
    E --> TASKS["Cloud Tasks queue"]
    TASKS --> REMIND["Cloud Run: gửi nhắc thanh toán"]
    CRON["Cloud Scheduler: 02:00 mỗi ngày"] --> FLOW["Workflows: đối soát"]
    FLOW --> FETCH["Cloud Run: lấy dữ liệu"]
    FETCH --> REPORT["Cloud Run/BigQuery: lập báo cáo"]
~~~

Một sản phẩm có thể xuất hiện ở **nhiều nhánh** của cùng hệ thống. Không có quy tắc “hệ thống chỉ được chọn một trong bốn”.

## 3. Ma trận ra quyết định

### 3.1. Chọn theo yêu cầu nổi bật

| Yêu cầu | Ưu tiên khảo sát | Vì sao |
| --- | --- | --- |
| Một sự kiện cần đến 3–10 consumer độc lập. | **Pub/Sub** | Mỗi subscription có backlog, ack và khả năng scale riêng. |
| Gửi lệnh HTTP tới một worker, hạn chế 20 request/giây. | **Cloud Tasks** | Queue điều tiết dispatch rate và số task đồng thời. |
| Chạy backup/tổng hợp theo cron mỗi đêm. | **Cloud Scheduler** | Kích hoạt theo giờ và múi giờ được cấu hình. |
| Đến một thời điểm riêng cho từng đơn hàng mới gọi lại API. | **Cloud Tasks** với `scheduleTime`. | Lịch **một lần theo từng task** khác cron lặp lại. |
| Xác minh thanh toán → cấp hàng → thông báo; cần rẽ nhánh và xử lý lỗi. | **Workflows** | Lưu trạng thái execution và kết quả các bước. |
| Đồng bộ hàng triệu bản ghi, nhiều consumer xử lý song song. | **Pub/Sub** hoặc giải pháp batch phù hợp. | Workflows không phải engine xử lý từng record ở throughput cực lớn. |
| Mỗi ngày khởi động một quy trình nhiều bước. | **Scheduler → Workflows** | Scheduler giữ lịch; Workflows giữ trình tự thực thi. |
| Sự kiện cần kích hoạt quy trình nhiều bước. | **Pub/Sub/Eventarc → Workflows** | Lớp phát sự kiện tách khỏi lớp điều phối. |
| API đối tác chấp nhận tối đa 5 yêu cầu đồng thời. | **Cloud Tasks → HTTP handler** | Điều tiết trước điểm gọi, có retry có cấu hình. |

### 3.2. Cây quyết định nhanh

~~~mermaid
flowchart TD
    A["Công việc được kích hoạt bởi gì?"] --> B{"Giờ lặp lại cố định?"}
    B -- "Có" --> SCH["Cloud Scheduler"]
    B -- "Không" --> C{"Nhiều bước phụ thuộc,\n cần trạng thái/rẽ nhánh?"}
    C -- "Có" --> WF["Workflows"]
    C -- "Không" --> D{"Sự kiện có nhiều consumer\n độc lập?"}
    D -- "Có" --> PS["Pub/Sub"]
    D -- "Không" --> E{"Gọi một endpoint cụ thể,\n cần rate limit hoặc hẹn giờ?"}
    E -- "Có" --> CT["Cloud Tasks"]
    E -- "Không" --> F["Xét Pub/Sub hoặc lời gọi trực tiếp\n theo yêu cầu độ bền và coupling"]
    SCH -. "Có thể kích hoạt" .-> WF
    SCH -. "Có thể publish" .-> PS
    PS -. "Có thể khởi động" .-> WF
~~~

Đây là **heuristic**, không phải bảng tính năng tuyệt đối. Ví dụ Pub/Sub cũng có **push subscriptions** giao HTTP, còn Cloud Tasks cũng có retry. Sự khác biệt cốt lõi là **event distribution với consumer tự đăng ký** so với **explicit invocation tới endpoint mà producer lựa chọn**.

## 4. Pub/Sub: “Một sự kiện, nhiều bên quan tâm”

### 4.1. Publisher không cần biết subscriber

~~~text
Cloud Run orders-api → topic orders-events
   ├── invoices-sub   → GKE invoice worker
   ├── inventory-sub  → Cloud Run inventory handler
   └── analytics-sub  → analytics pipeline
~~~

Mỗi subscription nhận và xác nhận message **độc lập**. Nếu `analytics-sub` chậm, nó có backlog riêng; ack ở `invoices-sub` không làm analytics mất message đang chờ. Có thể dùng **pull/StreamingPull**, **push** hoặc các loại export subscription theo khả năng sản phẩm.

**Phù hợp khi:** tích hợp event-driven, fan-out, tách vòng đời triển khai consumer, nhu cầu throughput lớn. **Không phải lựa chọn đầu tiên khi:** publisher phải chỉ rõ từng HTTP endpoint, hẹn giờ từng lần gọi hoặc áp hạn mức dispatch chính xác cho một downstream.

### 4.2. Delivery semantics và lỗi

- Mặc định Pub/Sub là **at-least-once**; subscriber phải xử lý message trùng.
- Message không được ack trong **ack deadline** có thể được giao lại; client libraries hỗ trợ lease extension.
- **Ordering keys** có thể giữ thứ tự trong phạm vi key và điều kiện hỗ trợ, không tạo một thứ tự tổng quát cho mọi message.
- **Exactly-once delivery** có điều kiện hỗ trợ cho pull subscriptions và không đồng nghĩa *exactly-once database writes*.
- Subscription có **retention**, retry policy, dead-letter topic và metric về backlog/oldest unacked age.

Pub/Sub không thể biết transaction trong Cloud SQL đã commit hay chưa. Handler nên **ghi bền vững rồi mới ack**, kết hợp unique constraint/idempotency.

### 4.3. Ví dụ `gcloud`: fan-out

Lệnh dưới đây dùng Bash và **chỉ thực thi trong project lab được phép**. Các lệnh `create`/`publish` thay đổi tài nguyên hoặc dữ liệu, có thể phát sinh phí.

~~~bash
PROJECT_ID="retail-lab"
TOPIC="orders-events-lab"

# WRITE: tạo nguồn sự kiện.
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID"

# WRITE: mỗi consumer có subscription riêng.
gcloud pubsub subscriptions create invoices-sub-lab \
  --topic="$TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions create analytics-sub-lab \
  --topic="$TOPIC" --project="$PROJECT_ID"

# WRITE: publish event giả định.
gcloud pubsub topics publish "$TOPIC" \
  --message='{"eventId":"evt-101","orderId":"O-1001"}' \
  --attribute=type=order.created \
  --project="$PROJECT_ID"

# READ-ONLY: kiểm tra metadata từng subscription.
gcloud pubsub subscriptions describe invoices-sub-lab \
  --project="$PROJECT_ID"
~~~

Muốn đọc message có thể dùng `gcloud pubsub subscriptions pull`; **không dùng `--auto-ack` trên subscription production** nếu nghiệp vụ chưa được xử lý. Cần thiết kế IAM Publisher/Subscriber, retention và DLQ trước khi tạo dữ liệu thật.

## 5. Cloud Tasks: “Gọi endpoint này với nhịp độ được kiểm soát”

### 5.1. Task khác message sự kiện

Một Cloud Tasks **HTTP task** chỉ định **URL**, phương thức HTTP, body/headers, thời điểm thử gửi đầu tiên và tùy chọn authentication. Queue có giới hạn **dispatches/second**, **concurrent dispatches** và retry policy.

Ví dụ công việc “gửi email xác nhận cho đơn `O-1001`”:

~~~text
orders-api → Cloud Tasks queue: send-email
                      |
                 rate limit + retries
                      |
                      v
             Cloud Run /tasks/send-email
                      |
                Email provider API
~~~

**Điểm khác Pub/Sub:** producer hướng tới **một handler cụ thể** thay vì phát thông báo cho một tập consumer tự đăng ký. Cloud Tasks **không bảo đảm strict ordering**; các task trong queue không trở thành FIFO business workflow chỉ nhờ được enqueue theo thứ tự.

### 5.2. Ba công cụ quản lý tải

| Thuộc tính | Tác dụng | Điều cần tránh |
| --- | --- | --- |
| `max-dispatches-per-second` | Điều tiết tốc độ gửi task tới handler. | Không hiểu là giới hạn tổng các request ngoài Cloud Tasks. |
| `max-concurrent-dispatches` | Chặn số task đang được dispatch đồng thời ở queue. | Không quên Cloud Run concurrency và DB/API capacity. |
| Retry/backoff | Thử lại HTTP response thất bại/timeout theo cấu hình. | Retry không thể làm nghiệp vụ không-idempotent trở nên an toàn. |

Task có thể được hẹn một **thời điểm chạy riêng** bằng `scheduleTime`. Đây **không phải recurring cron**: sau khi hoàn tất task đó, Cloud Tasks không tự tạo một task mới vào ngày hôm sau.

### 5.3. Ví dụ `gcloud`: queue → Cloud Run

Giả sử đã có Cloud Run service `send-email` **yêu cầu authentication**, service URL thật và một service account được cấp `roles/run.invoker`. Dùng hostname `run.app` mặc định của service khi làm HTTP target theo hướng dẫn Cloud Tasks; thay các placeholder trước khi chạy.

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
QUEUE="email-queue-lab"
RUN_URL="https://REPLACE_WITH_DEFAULT_RUN_APP_URL"
CALLER_SA="tasks-invoker@retail-lab.iam.gserviceaccount.com"

# WRITE: tạo queue có giới hạn dispatch nhỏ cho lab.
gcloud tasks queues create "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --max-dispatches-per-second=5 \
  --max-concurrent-dispatches=3 \
  --max-attempts=5

# WRITE: tạo một HTTP task gọi Cloud Run, dùng OIDC service identity.
gcloud tasks create-http-task email-O-1001-lab \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE" \
  --url="${RUN_URL}/tasks/send-email" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"orderId":"O-1001"}' \
  --oidc-service-account-email="$CALLER_SA" \
  --oidc-token-audience="$RUN_URL"

# READ-ONLY: xác minh queue config và task nếu còn chờ.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
gcloud tasks tasks list --queue="$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Tiền điều kiện:** Cloud Tasks API đã bật; người tạo task có các permissions cần thiết, bao gồm `iam.serviceAccounts.actAs` với service account dùng ký token theo phương án tương ứng; Cloud Run cho phép service account đó invoke. Queue có thể dispatch task rất nhanh, nên task vừa tạo **không nhất thiết còn xuất hiện** trong `tasks list`. `--oidc-token-audience` nên là **URL gốc của Cloud Run service** (không kèm path) nếu backend dùng audience mặc định.

### 5.4. Dedup không phải exactly-once

Nếu tự đặt **task ID** cố định, Cloud Tasks có thể từ chối tạo task trùng tên khi task đang tồn tại hoặc mới được hoàn thành/xóa trong **cửa sổ deduplication** được dịch vụ hỗ trợ. Nhưng:

- Task ID dedup là **dedup lúc tạo task**, không ngăn mọi HTTP delivery retry.
- Handler vẫn có thể nhận yêu cầu nhiều lần sau timeout hoặc lỗi mạng.
- Task ID cố định có lookup cost và ảnh hưởng latency tạo task; chọn quy tắc tên có chủ đích.
- Không nên dùng Cloud Tasks để đảm bảo một giao dịch tài chính “chỉ thanh toán một lần” nếu backend không có idempotency.

HTTP handler nên xác thực IAM/OIDC, kiểm tra payload, commit kết quả một cách idempotent, **chỉ trả HTTP 2xx khi đã hoàn tất xử lý bền vững**. Lỗi tạm thời trả status phù hợp để retry; lỗi cố định phải có quy trình lưu/quản lý, tránh lặp không cần thiết.

## 6. Cloud Scheduler: “Đúng chu kỳ, hãy kích hoạt công việc”

### 6.1. Cron không thực hiện công việc bên trong Scheduler

Cloud Scheduler nhận **lịch cron**, múi giờ và target:

- **HTTP(S) endpoint**, ví dụ Cloud Run hoặc Workflows Executions API.
- **Pub/Sub topic** để phát message kích hoạt.
- **App Engine HTTP target** trong các môi trường tương ứng.

Scheduler chỉ gửi một **request/message theo lịch**, còn target mới thực hiện nghiệp vụ. Scheduler cung cấp **at-least-once delivery**; cùng một kỳ cron có thể tạo nhiều attempts, nên target vẫn cần **idempotency**.

~~~text
02:00 UTC mỗi ngày
  → Scheduler job
      → Pub/Sub topic daily-reports
          → report workers
~~~

### 6.2. Cron, timezone và daylight saving

Cron `0 2 * * *` nghĩa là **02:00 mỗi ngày theo timezone cấu hình**, không mặc nhiên là giờ Việt Nam. Ví dụ `--time-zone="Asia/Ho_Chi_Minh"` chạy theo giờ Việt Nam; trong những vùng có DST, chuyển giờ có thể dẫn tới một số giờ bị lặp hoặc bỏ qua. Với lịch đòi tính nhất quán tuyệt đối theo thời gian, cân nhắc **UTC**.

Một số lịch quan trọng:

| Biểu thức | Ý nghĩa theo timezone của job |
| --- | --- |
| `0 2 * * *` | Hằng ngày lúc 02:00. |
| `0 9 * * 1` | Thứ Hai lúc 09:00. |
| `0 0 1 * *` | Đầu tháng lúc 00:00 ngày 1. |
| `0 0 * * 0` | Chủ nhật lúc 00:00. |

Nếu một lần chạy chậm hoặc retry kéo dài, lịch dự kiến tiếp theo có thể bị ảnh hưởng theo semantics của Scheduler; **không thiết kế giả định mọi cron đều xuất hiện đúng thời điểm với độ chính xác tuyệt đối**.

### 6.3. Ví dụ `gcloud`: cron → Pub/Sub

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
TOPIC="daily-reports-lab"

# WRITE: topic thử nghiệm phải tồn tại trước khi tạo Scheduler job.
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID"

# WRITE: mỗi ngày 02:00 theo giờ Việt Nam, publish một lệnh tổng hợp.
gcloud scheduler jobs create pubsub daily-report-lab \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --schedule="0 2 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --topic="$TOPIC" \
  --message-body='{"job":"daily-report","schemaVersion":1}'

# READ-ONLY: kiểm tra lịch và target.
gcloud scheduler jobs describe daily-report-lab \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Các API, IAM/service agents và region tương ứng phải được chuẩn bị. **Không tạo một job mới để gửi thẳng tới Cloud Tasks queue bằng cách giả định “Scheduler có target Cloud Tasks”**; pattern thường dùng là Scheduler → Pub/Sub/HTTP endpoint → producer tạo task, hoặc Scheduler → Workflows. Khi tạo HTTP job gọi Cloud Run, dùng **OIDC service account** và cấp `roles/run.invoker` ở destination phù hợp.

### 6.4. Chống chạy lại cùng kỳ cron

Với HTTP target dùng unix-cron, Cloud Scheduler gửi các header như `X-CloudScheduler-JobName` và `X-CloudScheduler-ScheduleTime`; có thể kết hợp chúng làm khóa nghiệp vụ để chống duplicate cho một kỳ lịch. Với target Pub/Sub, hãy thiết kế khóa chu kỳ từ **payload và thời gian nghiệp vụ** một cách tin cậy, không dùng một chuỗi tĩnh chung cho mọi ngày.

Ví dụ báo cáo ngày 2026-11-19 cần khóa `daily-report:2026-11-19`. Nếu có retry hay job được chạy thủ công, handler kiểm tra khóa trong kho bền vững để tránh gửi báo cáo/ghi sổ hai lần.

## 7. Workflows: “Một execution đi qua nhiều bước”

### 7.1. Điều phối có trạng thái

**Workflows** mô tả flow dưới dạng YAML/JSON: từng step có thể gọi HTTP endpoint/Google Cloud API, nhận kết quả, gán biến, rẽ nhánh, lặp, xử lý ngoại lệ hoặc chạy song song. Một **execution** có ID và trạng thái; Workflows có thể **chờ** mà không cần giữ một VM hoặc container chạy liên tục. Theo tài liệu Google Cloud, Workflows có thể chờ/poll/callback trong **tới một năm**, nhưng vẫn chịu quota và giới hạn riêng.

~~~mermaid
flowchart LR
    START["Bắt đầu hoàn tiền"] --> CHECK["Kiểm tra đơn"]
    CHECK --> VALID{"Hợp lệ?"}
    VALID -- "Không" --> STOP["Kết thúc / báo lỗi"]
    VALID -- "Có" --> PAY["Gọi cổng thanh toán"]
    PAY --> DB["Cập nhật trạng thái đơn"]
    DB --> NOTI["Gửi thông báo"]
~~~

**Workflows phù hợp khi:** thứ tự và kết quả từng bước có ý nghĩa, cần retry có chủ đích, chờ một hệ thống hoặc phối hợp nhiều API. **Không phù hợp khi:** chỉ muốn broadcast một event đơn giản hoặc xử lý hàng triệu bản ghi nhỏ như một loop khổng lồ trong một execution.

### 7.2. Ví dụ Workflows YAML gọi hai Cloud Run services

Ví dụ file `order-fulfillment.yaml` trong thư mục thực hành (không được tạo ở workspace bài học này). Thay URL giả bằng **Cloud Run HTTPS URL thật**, tạo trước các services và cấp `roles/run.invoker` cho **workflow runtime service account**.

~~~yaml
main:
  params: [args]
  steps:
    - reserveInventory:
        call: http.post
        args:
          url: https://REPLACE_WITH_INVENTORY_RUN_URL/reserve
          auth:
            type: OIDC
            audience: https://REPLACE_WITH_INVENTORY_RUN_URL
          body:
            orderId: ${args.orderId}
        result: reservation

    - confirmOrder:
        call: http.post
        args:
          url: https://REPLACE_WITH_ORDERS_RUN_URL/confirm
          auth:
            type: OIDC
            audience: https://REPLACE_WITH_ORDERS_RUN_URL
          body:
            orderId: ${args.orderId}
            reservationId: ${reservation.body.reservationId}
        result: confirmation

    - done:
        return:
          orderId: ${args.orderId}
          status: ${confirmation.body.status}
~~~

Đoạn YAML minh họa **đường thành công**, giả định Cloud Run `reserve` trả JSON có `reservationId`, còn `confirm` trả `status`. Nó **chưa** có validation lỗi, retry, timeout, compensation hoặc authorization nghiệp vụ; phải bổ sung các phần đó trước production. Với Workflows gọi Cloud Run, `auth: {type: OIDC}` dùng identity token dựa trên workflow SA; `audience` phải khớp backend Cloud Run service URL được chấp nhận, không tự gắn path.

### 7.3. Deploy và chạy thử

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
WORKFLOW="order-fulfillment-lab"
WORKFLOW_SA="workflow-orders@retail-lab.iam.gserviceaccount.com"

# WRITE: tạo/cập nhật workflow từ file trong thư mục lab.
gcloud workflows deploy "$WORKFLOW" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --source=order-fulfillment.yaml \
  --service-account="$WORKFLOW_SA"

# WRITE: một execution thực sự gọi downstream services.
gcloud workflows execute "$WORKFLOW" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --data='{"orderId":"O-1001"}'

# READ-ONLY: xem workflow definition/metadata.
gcloud workflows describe "$WORKFLOW" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Lưu ý:** deployer cần quyền Workflows và quyền sử dụng workflow SA khi áp dụng; SA cần Invoker cho các Cloud Run services. `execute` **có side effects thật** ở downstream nếu URLs đã được cấu hình, do đó chỉ chạy trên data lab và endpoint idempotent. Workflows **không tạo distributed database transaction** giữa các services.

### 7.4. Retry và compensation không phải một

Nếu bước `reserveInventory` thành công nhưng `confirmOrder` thất bại:

- **Retry** có thể hợp lý nếu lỗi là 503/timeout tạm và endpoint `confirm` **idempotent**.
- **Compensation** (ví dụ `releaseReservation`) có thể cần khi nghiệp vụ không thể tiếp tục.
- **Không tự retry mọi HTTP POST**: payment/fulfillment có thể tạo side effect trùng.
- Workflows hỗ trợ `try`/`retry`/`except`, callbacks, branching và parallelism; thiết kế dựa trên lỗi thực tế.

Đối với quy trình dài, ghi `workflowExecutionId`, `orderId` và trạng thái nghiệp vụ trong kho bền vững theo nhu cầu. Nếu workflow bị cancel/fail, xem trạng thái external systems trước khi phát lại.

## 8. Kết hợp dịch vụ: bốn mẫu kiến trúc

### 8.1. Event fan-out rồi giới hạn tốc độ tới đối tác

~~~mermaid
flowchart LR
    API["Cloud Run: tạo đơn"] --> P["Pub/Sub: order.created"]
    P --> INV["Subscription: invoice"]
    P --> M["Subscription: marketing"]
    M --> PRODUCER["Enqueue task theo đối tác"]
    PRODUCER --> Q["Cloud Tasks: partner-queue"]
    Q --> HANDLER["Cloud Run: send partner request"]
~~~

Pub/Sub fan-out nhiều consumer; một consumer đưa tác vụ cần rate limit vào Cloud Tasks. **Không tạo một queue Cloud Tasks riêng để thay thế mọi Pub/Sub subscription** nếu mục tiêu chỉ là fan-out sự kiện.

### 8.2. Lịch chạy báo cáo → quy trình nhiều bước

~~~text
Scheduler: 02:00 mỗi ngày
  → Workflows execution
      → gọi Cloud Run lấy dữ liệu
      → khởi động BigQuery job / dữ liệu được duyệt
      → chờ kết quả
      → lưu báo cáo vào Cloud Storage
      → gửi thông báo kết quả
~~~

**Scheduler không theo dõi trạng thái từng bước**. Workflows mới là nơi quản lý step results và lỗi workflow; cần identity riêng cho Scheduler gọi **Workflows Executions API** (thường bằng OAuth access token và quyền `roles/workflows.invoker`), còn workflow SA có quyền tới từng downstream.

### 8.3. Hẹn một lần nhắc thanh toán

~~~text
Khách tạo đơn O-1001 lúc 14:00
    → tạo Cloud Task scheduleTime = 14:15
    → 14:15 gọi /check-and-remind
    → handler đọc trạng thái đơn:
         đã thanh toán → trả 2xx, không gửi gì
         chưa thanh toán → gửi nhắc idempotent
~~~

Đây là lịch **riêng của một đơn**, không phải cron một lần mỗi 15 phút. Không nên tạo một Cloud Scheduler job cho mỗi đơn hàng. Khi khách thanh toán sớm, task có thể vẫn dispatch; handler **phải kiểm tra lại trạng thái** và không dựa duy nhất vào việc cố xóa task.

### 8.4. Quy trình hoàn tiền có bước thất bại cần bù

~~~text
HTTP request / sự kiện refund.requested
    → Workflows:
         validate order
         reserve refund operation ID
         call payment provider (idempotency key)
         update Cloud SQL
         notify customer
         if needed: compensate / manual review
~~~

Chọn Workflows vì cần biết **bước nào thành công, bước nào thất bại**. Có thể dùng Pub/Sub phát sự kiện hoàn tiền sau khi trạng thái giao dịch được commit, hoặc Cloud Tasks để rate-limit một endpoint đối tác. **Không tuyên bố “Workflows làm mọi bước exactly-once”**; transaction và compensation thuộc thiết kế ứng dụng.

## 9. Những điều bốn dịch vụ không tự bảo đảm

### 9.1. At-least-once và idempotency

Pub/Sub, Cloud Tasks và Cloud Scheduler đều có thể tạo **nhiều lần delivery/attempt** cho cùng công việc. Workflows cũng có thể gọi lại step khi được cấu hình retry, hoặc cùng một business event kích hoạt nhiều executions. Vì vậy:

1. Sinh **business operation ID** trước khi publish/enqueue.
2. Trên consumer/handler, kiểm tra operation ID trong kho **bền vững**.
3. Commit side effect và trạng thái idempotency bằng transaction/unique constraint khi có thể.
4. Ack Pub/Sub hoặc trả HTTP 2xx **sau khi commit**.
5. Với external APIs, truyền idempotency key nếu đối tác hỗ trợ; nếu không, thiết kế reconciliation.

Ví dụ:

~~~sql
CREATE TABLE processed_operations (
  operation_id TEXT PRIMARY KEY,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trong transaction, thử ghi operation_id trước.
INSERT INTO processed_operations(operation_id)
VALUES ('send-receipt:O-1001')
ON CONFLICT DO NOTHING;
~~~

Ứng dụng chỉ thực thi side effect khi biết transaction **thực sự insert một dòng mới**, và các ghi nghiệp vụ cần commit **cùng transaction** khi thuộc cùng database. Nếu gọi API ngoài transaction, mẫu SQL trên **chưa đủ** bảo đảm đúng một side effect; cần **outbox/reconciliation** hoặc idempotency ở phía đối tác.

### 9.2. Ordering và rate limits

| Mong muốn | Thực tế cần làm |
| --- | --- |
| Sự kiện của cùng đơn xử lý đúng thứ tự | Pub/Sub ordering key khi được hỗ trợ + consumer tuần tự theo key; business version checks. |
| Task queue chạy theo thứ tự enqueue | Cloud Tasks không có bảo đảm strict FIFO; dùng khóa/phiên bản ở application. |
| Mỗi đối tác không quá 10 calls/s | Cloud Tasks queue dispatch limit + xem lại concurrency, retry và giới hạn đối tác. |
| Mỗi kỳ cron chỉ có một báo cáo | Scheduler at-least-once nên handler dùng khóa kỳ báo cáo trong DB. |
| Refund có một chuỗi nghiệp vụ duy nhất | Workflows + operation ID, transaction và kiểm soát concurrent executions. |

### 9.3. Hạn mức và dữ liệu tồn đọng

Pub/Sub giữ messages theo **retention của topic/subscription**; message unacked có thể hết hạn. Cloud Tasks giữ tasks theo giới hạn tuổi/lịch mà sản phẩm hỗ trợ; task tồn đọng không phải kho lưu trữ lịch sử nghiệp vụ vô hạn. Scheduler chỉ lưu **job schedule/attempt metadata**, không phải queue tích lũy vô hạn cho từng kỳ. Workflows lưu **execution state/history** theo tính năng/retention riêng, không thay thế database nghiệp vụ.

Với dữ liệu cần giữ dài hạn, dùng Cloud Storage/Cloud SQL/BigQuery hoặc hệ thống lưu trữ phù hợp. **Đừng chọn dịch vụ hàng đợi chỉ vì nghĩ nó thay backup được.**

## 10. IAM, mạng và bảo mật theo từng chặng

### 10.1. Danh tính không được gộp chung

| Chặng | Principal thường cần quyền | Ví dụ role/permission |
| --- | --- | --- |
| API phát sự kiện | Cloud Run runtime SA | `roles/pubsub.publisher` trên topic. |
| GKE đọc Pub/Sub | GKE workload identity/SA được cấu hình | `roles/pubsub.subscriber` trên subscription. |
| API tạo Cloud Tasks | Producer SA | Quyền tạo task ở queue, thường `roles/cloudtasks.enqueuer`. |
| Tasks gọi Cloud Run | OIDC task SA | `roles/run.invoker` trên service; creator có `iam.serviceAccounts.actAs` khi cần. |
| Scheduler gửi Pub/Sub | Scheduler service agent/identity theo workflow | Quyền cần thiết để publish target topic. |
| Scheduler gọi Workflows | SA dùng OAuth tới Executions API | `roles/workflows.invoker` ở phạm vi thích hợp. |
| Workflows gọi Cloud Run | Workflow runtime SA | `roles/run.invoker` trên từng Cloud Run service. |
| Cloud Run/GKE xử lý dữ liệu | Runtime SA riêng | Cloud SQL/Storage/Secret Manager permissions tối thiểu. |

**OIDC** phù hợp khi gọi một Cloud Run HTTPS endpoint yêu cầu ID token; với **Google APIs** như Workflows Executions API, thông thường dùng **OAuth 2.0 access token**. IAM role trên queue/topic **không tự cấp quyền gọi Cloud Run** hay quyền cập nhật Cloud SQL.

### 10.2. Network boundary vẫn tồn tại

- Cloud Run/GKE subscriber cần route, DNS và quyền tới Pub/Sub/Google APIs.
- Cloud Tasks HTTP target phải có URL reachable theo khả năng service; Cloud Run ingress có thể chặn đường không được hỗ trợ.
- Scheduler HTTP job cần target được phép nhận, OIDC/OAuth và timeout đúng loại.
- Workflows gọi Cloud Run qua HTTPS/OIDC theo kiến trúc hỗ trợ; khi gọi private endpoints, phải xem **IAP, Service Directory hoặc cách kết nối được sản phẩm hỗ trợ**, không suy rằng workflow luôn nằm trong VPC của GKE.
- Dùng VPC connector/Direct VPC egress, Cloud NAT, Private Google Access/PSC hoặc firewall theo từng luồng thật.

Không xử lý lỗi DNS/network timeout bằng cách cấp project Owner. Không sửa `401/403` bằng cách mở Cloud Run unauthenticated trong production.

## 11. Quan sát, SLO và phản ứng sự cố

| Dịch vụ | Chỉ số/vấn đề cần quan sát | Phản ứng phù hợp |
| --- | --- | --- |
| Pub/Sub | Unacked messages, oldest unacked age, ack rate, DLQ. | Scale subscriber theo năng lực downstream, xử lý poison message. |
| Cloud Tasks | Queue depth, oldest task age, dispatch rate, attempts/errors, throttling. | Điều chỉnh queue limits và handler; xem lỗi HTTP/timeout. |
| Scheduler | Last run, success/failure, retry, schedule lag. | Kiểm tra cron/timezone, quyền target và idempotency. |
| Workflows | Execution state, failed step, retries, execution duration, step usage. | Xem từng step, correlation ID, compensation/replay. |
| Downstream | Cloud Run 5xx/p95, Cloud SQL connections, API partner 429. | Bảo vệ capacity và giảm fan-out/retry storm. |

### 11.1. Một phép tính đơn giản để đặt giới hạn

Giả sử publisher tạo **120 đơn/phút**; mỗi đơn cần một email từ Cloud Tasks, thời gian xử lý trung bình **2 giây/task**. Để theo kịp tải lý tưởng:

~~~text
Arrival rate = 120 / 60 = 2 tasks/giây
Concurrency tối thiểu theo Little's Law ≈ 2 × 2 = 4 tasks
~~~

Chọn `max-concurrent-dispatches=4` là **ước lượng lý thuyết ở tải đều**, không phải khuyến nghị production. Với p95 xử lý lâu, retry hoặc burst, cần buffer, giới hạn API đối tác và load test. Nếu chọn `max-dispatches-per-second=1`, queue **sẽ tích backlog** khi hệ thống nhận 2 tasks/giây lâu dài.

### 11.2. Runbook lỗi tích hợp

1. **Xác định lớp**: job chưa kích hoạt, message chưa được giao, task còn trong queue, workflow step failed hay backend đã nhận nhưng lỗi?
2. **Đọc danh tính**: producer/trigger SA, OIDC/OAuth audience và IAM ở destination.
3. **Đọc mạng**: hostname, DNS, ingress/egress, timeout và connectivity.
4. **Đọc khả năng xử lý**: queue depth, rate, concurrency, Cloud Run scale, Cloud SQL limits.
5. **Đọc lỗi nghiệp vụ**: payload/schema, idempotency, transaction và trạng thái downstream.
6. **Phục hồi có kiểm soát**: replay, retry, re-enqueue hay compensation theo loại lỗi; tránh gửi trùng tác dụng phụ.
7. **Xác minh SLO**: backlog giảm, công việc hoàn thành, không có lỗi ẩn hoặc phí đột biến.

**Không sử dụng “xóa queue/topic/subscription” như bước xử lý đầu tiên** khi tồn đọng. Hành động này có thể xóa dữ liệu hoặc làm mất cơ hội retry/khôi phục.

## 12. Chi phí: chọn theo lượng công việc thực

| Thành phần | Xu hướng chi phí chính | Cần kiểm soát |
| --- | --- | --- |
| Pub/Sub | Data throughput, delivery/storage, retention và các tính năng bổ sung. | Số subscriptions/fan-out, kích thước payload, tuổi backlog. |
| Cloud Tasks | Số operations/tasks theo bảng giá, logs và chi phí handler. | Retry storm, task volume, queue rate. |
| Cloud Scheduler | Số cron jobs và phương án giá hiện hành, target usage. | Tránh tạo hàng triệu cron jobs cho từng bản ghi. |
| Workflows | Steps/internal/external steps, executions, logging/connector calls. | Workflow quá nhiều bước nhỏ, polling liên tục, retry không giới hạn. |
| Cloud Run/GKE/SQL | CPU/RAM/instances, database connections và data transfer. | Concurrency, max instances, downstream limits. |

Không có một lựa chọn luôn rẻ hơn. **Scheduler → Workflows** có thể hợp lý cho báo cáo theo ngày; dùng Workflows cho mỗi sự kiện nhỏ ở throughput rất lớn có thể làm tăng số steps và chi phí. **Pub/Sub** hợp cho một sự kiện với nhiều consumers, nhưng mỗi consumer tăng delivery/storage và nhu cầu vận hành.

Đánh giá theo **chi phí trên một kết quả nghiệp vụ hoàn thành**, không chỉ giá của một message hay một API call. Dùng Cloud Billing/Monitoring để đo, xét quota và vùng triển khai.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng Scheduler để hẹn từng email của hàng triệu đơn. | Quá nhiều jobs và khó quản lý lifecycle. | Cloud Tasks schedule time theo từng đơn. |
| Dùng Pub/Sub để gọi đúng một endpoint mà cần QPS cứng. | Thiếu queue-level rate control từ phía publisher. | Cloud Tasks hoặc subscriber chủ động flow control theo thiết kế. |
| Dùng Cloud Tasks như broadcast topic. | Producer phải tạo task cho từng handler, coupling tăng. | Pub/Sub với subscriptions độc lập. |
| Dùng Workflows để duyệt tuần tự từng event nhỏ ở throughput lớn. | Step count, latency và cost tăng. | Pub/Sub/batch workers; chỉ orchestration phần cần trạng thái. |
| Tin rằng retry đồng nghĩa exactly-once. | Gửi email/thu tiền trùng. | Idempotency key, transaction, outbox. |
| Tin Cloud Scheduler chạy “chính xác một lần/giờ”. | Bỏ sót retry hoặc thực hiện trùng. | Dùng scheduled-run ID và dedup. |
| Tin Cloud Tasks dispatch theo FIFO tuyệt đối. | Trạng thái đơn sai thứ tự. | Version checks/serial handling ở app. |
| Ack/trả 2xx trước khi commit. | Mất cơ hội retry khi ghi dữ liệu thất bại. | Commit bền vững rồi xác nhận. |
| Gộp mọi SA thành Editor. | Tăng tác động khi credential bị lộ. | IAM tối thiểu theo từng hop. |
| Chỉ nhìn queue depth mà không nhìn oldest age. | Công việc cũ/poison bị kẹt dù queue nhỏ. | Giám sát cả backlog size và tuổi. |

## 14. Bài tập

### Bài 1 — Chọn sản phẩm

Với mỗi yêu cầu, chọn dịch vụ chính và giải thích một câu: (a) phát `order.created` tới kế toán và analytics; (b) gọi webhook đối tác không quá 10 lần/giây; (c) tổng hợp báo cáo lúc 02:00 hằng ngày; (d) hoàn tiền qua ba bước có thể rẽ nhánh; (e) nhắc thanh toán đúng 15 phút sau khi tạo từng đơn.

**Gợi ý:** tương ứng Pub/Sub, Cloud Tasks, Scheduler, Workflows và Cloud Tasks.

### Bài 2 — Phân biệt HTTP push

Pub/Sub push subscription và Cloud Tasks HTTP target đều có thể gọi Cloud Run. Vậy khác biệt giữa **publisher không biết consumer** và **producer chỉ định endpoint**, giữa retention/backlog và queue dispatch control là gì?

### Bài 3 — Thiết kế fan-out

Website phát một `order.created` và ba teams cần xử lý độc lập. Vẽ topic/subscriptions, quyền IAM Publisher/Subscriber và metric backlog của mỗi nhóm. Điều gì xảy ra khi analytics dừng 30 phút?

### Bài 4 — Tác vụ chậm và rate limit

Một API đối tác cho phép tối đa 6 requests/giây và 3 requests đồng thời. Hãy chọn Cloud Tasks queue settings ban đầu, giải thích vì sao cần retry/backoff và idempotency, rồi nêu cách đo để chỉnh lại. Nếu producer tạo trung bình 9 tasks/giây trong 20 phút, backlog tăng khoảng bao nhiêu ở dispatch rate bền vững 6/giây, bỏ qua retries?

**Gợi ý:** tăng khoảng `(9 − 6) × 1.200 = 3.600` tasks.

### Bài 5 — Cron và timezone

Giải thích `0 9 * * 1` theo `Asia/Ho_Chi_Minh`. Nếu thay thành `Etc/UTC`, lịch theo giờ Việt Nam dịch thế nào? Vì sao cần chống duplicate cho cùng một kỳ báo cáo?

### Bài 6 — Workflows và compensation

Quy trình `reserve inventory → charge card → update order` thất bại ở bước thứ ba. Nêu những thông tin Workflows cần lưu, khi nào retry an toàn, khi nào phải reconcile/compensate và vì sao không được tự charge lại mà thiếu idempotency.

### Bài 7 — IAM hai chặng

Một Cloud Run API tạo Cloud Task; task gọi Cloud Run `send-email` có authentication. Phân biệt quyền SA của producer, OIDC SA trên task, quyền `iam.serviceAccounts.actAs`, `roles/run.invoker` và runtime SA của `send-email`.

### Bài 8 — Phát hiện và khắc phục

Cloud Scheduler job thành công nhưng không có báo cáo trong Cloud Storage. Hãy kiểm tra Scheduler target, Pub/Sub subscription hoặc Workflows execution, Cloud Run logs, Cloud Storage IAM và logic idempotency theo thứ tự. “Scheduler thành công” chứng minh được điều gì và **không** chứng minh được điều gì?

### Bài 9 — Đánh đổi chi phí

Hệ thống nhận 1 triệu sự kiện/ngày, mỗi sự kiện có 3 subscribers; báo cáo tổng hợp chạy mỗi đêm một lần. Đề xuất kiến trúc tiết kiệm phù hợp và nêu điều kiện nào khiến bạn chọn thêm Cloud Tasks hoặc Workflows thay vì cố dùng một dịch vụ duy nhất.

## 15. Checklist production và tài liệu chính thức

| Hạng mục | Câu hỏi kiểm chứng |
| --- | --- |
| **Pattern đúng** | Event fan-out, explicit task, cron hay multi-step orchestration? |
| **Trigger và target** | Đúng topic/subscription, URL, service, cron/timezone hay workflow execution? |
| **Delivery** | Có idempotency cho at-least-once, retry, timeout và re-execution không? |
| **Rate và backlog** | Dispatch/concurrency, publish/ack rate, oldest age, worker capacity phù hợp? |
| **State và recovery** | Workflows execution state, DB transaction, compensation, DLQ/replay khi cần? |
| **IAM** | Tách producer, delivery identity, workflow SA và runtime SA; least privilege? |
| **Network** | Ingress/egress, audience, OIDC/OAuth, DNS và private access được thử thật? |
| **CI/CD** | IaC/review, version, staging test, rollback và không làm mất queued data? |
| **Observability** | Có correlation ID, logs, lỗi, backlog/age, SLO và cost alerts? |
| **Economics** | Đã tính số lần publish/delivery/task/job/step và chi phí downstream? |

Tài liệu chính thức để đối chiếu giới hạn và cờ CLI theo phiên bản:

- [Google Cloud: Choosing Pub/Sub or Cloud Tasks](https://cloud.google.com/pubsub/docs/choosing-pubsub-or-cloud-tasks)
- [Pub/Sub subscriptions và delivery semantics](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Cloud Tasks: HTTP target quickstart](https://cloud.google.com/tasks/docs/add-task-queue)
- [Cloud Tasks: Configure queues and retries](https://cloud.google.com/tasks/docs/configuring-queues)
- [Cloud Scheduler overview](https://cloud.google.com/scheduler/docs/overview)
- [Cloud Scheduler cron format và timezone](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules)
- [Workflows overview](https://cloud.google.com/workflows/docs/overview)
- [Workflows: Authenticate requests](https://cloud.google.com/workflows/docs/authenticate-from-workflow)
- [Workflows: Schedule using Cloud Scheduler](https://cloud.google.com/workflows/docs/schedule-workflow)
- [gcloud tasks create-http-task](https://cloud.google.com/sdk/gcloud/reference/tasks/create-http-task)
- [gcloud scheduler jobs create pubsub](https://cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/pubsub)
- [gcloud workflows deploy](https://cloud.google.com/sdk/gcloud/reference/workflows/deploy)

**Ghi nhớ:** **Pub/Sub** là kênh thông báo sự kiện cho các consumer độc lập; **Cloud Tasks** là queue điều tiết việc gọi một handler cụ thể; **Cloud Scheduler** là đồng hồ kích hoạt theo lịch; **Workflows** là bộ điều phối nhiều bước có trạng thái. Chọn chúng theo **mục đích thực hiện công việc**, rồi thiết kế thêm authentication, retry, idempotency, rate limits, metrics và chi phí. Một kiến trúc tốt thường **kết hợp đúng các vai trò** thay vì cố dùng một sản phẩm cho mọi nhu cầu.
