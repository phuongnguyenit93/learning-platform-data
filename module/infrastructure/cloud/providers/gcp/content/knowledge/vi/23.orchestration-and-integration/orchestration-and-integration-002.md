# Workflow steps, expressions và quản lý dữ liệu thực thi

Trong hệ thống Java xử lý đơn hàng, một API cần kiểm tra tồn kho, tạo thanh toán, cập nhật trạng thái rồi gửi thông báo. Nếu mọi thao tác nằm trong một HTTP request, lỗi tạm thời hoặc timeout dễ khiến quy trình dang dở. **Google Cloud Workflows** giúp mô tả trình tự và điều kiện thực thi bằng YAML/JSON, gọi các dịch vụ như Cloud Run hoặc Google Cloud APIs, giữ dữ liệu trung gian và xử lý lỗi có kiểm soát.

Bài thuộc chương **Điều phối và tích hợp ứng dụng** trong học phần **CLOUD_PROVIDERS_GCP**: liên kết project, IAM, VPC, Java trên Cloud Run/GKE, Cloud Storage, cơ sở dữ liệu, CI/CD, độ tin cậy và chi phí. Trọng tâm là **cú pháp steps, expressions và quản lý dữ liệu của từng execution**; Workflows không thay ứng dụng nghiệp vụ hoặc database.

Sau bài này, bạn có thể:

- Đọc và viết các bước `assign`, `call`, `switch`, `for`, `parallel`, `try/except/retry`, `return`.
- Sử dụng biểu thức `${...}`, maps, lists, tham số đầu vào, kết quả và subworkflows.
- Hiểu **scope** của biến trong workflow, vòng lặp và nhánh song song; tránh ghi đè/race logic.
- Triển khai một workflow tính tổng đơn hàng chạy độc lập, truyền JSON input và xem output.
- Gọi Cloud Run qua **OIDC**, Google Cloud APIs qua **OAuth2/connector**, dùng IAM tối thiểu.
- Thiết kế retry/idempotency, log dữ liệu không nhạy cảm và đưa payload lớn ra Cloud Storage/DB.
- Giải thích giới hạn bộ nhớ execution, thời lượng, quota, logging và chi phí theo bước.

> **Lưu ý lab:** mọi project ID, service account và URL là ví dụ. Lệnh tạo workflow/IAM chỉ chạy trong project thử nghiệm đã được phép; không sử dụng dữ liệu hoặc khóa thật trong execution arguments hay logs.

## 1. Workflows điều phối, không xử lý thay ứng dụng

~~~mermaid
flowchart LR
  A["Java API / Scheduler / Eventarc"] --> W["Workflows execution"]
  W --> V["Validate: steps + expressions"]
  V --> S["Cloud Run: stock service"]
  S --> P["Cloud Run: payment service"]
  P --> N["Pub/Sub / notification"]
  W --> L["Cloud Logging + execution history"]
  S --> D["Cloud SQL / Firestore"]
  P --> D
~~~

Một **workflow definition** có thể có nhiều **executions** độc lập. Mỗi execution giữ biến và trạng thái điều phối của riêng mình; nó không có shared memory với execution khác. Code Java/Cloud Run xử lý business logic và lưu dữ liệu bền vững, còn Workflows quyết định **khi nào gọi dịch vụ nào, nhánh nào chạy và làm gì khi lỗi**.

| Dịch vụ | Chức năng ưu tiên | Không nên nhầm |
|---|---|---|
| **Workflows** | Điều phối có trạng thái, nhiều API calls, điều kiện, retries, đợi kết quả | Không phải message queue hay database |
| **Cloud Tasks** | Hàng đợi giao HTTP task, delay/rate limit/retry từng task | Không tự biểu diễn quy trình nhiều bước có nhánh |
| **Pub/Sub** | Phân phối thông điệp, fan-out nhiều subscribers | Không tự bảo đảm transaction xuyên nhiều service |
| **Eventarc** | Lọc và định tuyến event tới destination được hỗ trợ | Không tự giữ workflow business state |
| **Cloud Run job** | Xử lý batch đến khi hoàn thành; tasks/parallelism | Không thay trình tự nhiều API và phê duyệt |

Ví dụ: Eventarc khởi chạy workflow khi file mới được upload; workflow gọi Cloud Run để xác minh file, sau đó tạo job xử lý OCR. **Không nên truyền toàn bộ PDF qua biến Workflows**: chỉ truyền `bucket`, `objectName`, `generation` và job ID.

## 2. Cấu trúc YAML/JSON và các loại step

Workflows hỗ trợ **YAML hoặc JSON**; hai định dạng diễn tả cùng ngữ nghĩa. Ví dụ tối giản:

~~~yaml
main:
  params: [args]
  steps:
    - initialize:
        assign:
          - customer: ${default(map.get(args, "customer"), "guest")}
    - decide:
        switch:
          - condition: ${customer == "guest"}
            next: anonymous
    - knownCustomer:
        return: ${"Hello " + customer}
    - anonymous:
        return: "Please sign in"
~~~

Các step chạy **theo thứ tự được định nghĩa**, trừ khi `next`, `switch`, `return`, lỗi hoặc song song thay đổi luồng. Tên step phải **duy nhất trong cùng subworkflow**, nên đặt `validate_input`, `call_orders`, `return_result` để dễ tra execution history.

| Cú pháp | Dùng làm gì | Ghi nhớ |
|---|---|---|
| `main`, `params` | Điểm vào và tham số execution | Input thường là JSON map |
| `assign` | Tạo/cập nhật biến, map, list | Các phép gán trong cùng step xử lý theo thứ tự |
| `call`, `args`, `result` | Gọi stdlib/connector/subworkflow và lưu kết quả | `result` là tên biến, không dùng `${...}` |
| `switch`, `condition` | Chọn nhánh theo Boolean expression | Điều kiện đầu tiên đúng được chọn |
| `next` | Nhảy đến step cùng phạm vi hợp lệ | `next: end` kết thúc không trả dữ liệu |
| `for` | Lặp qua list/map hoặc dải số | Loop variable có scope riêng |
| `parallel` | Chạy các nhánh/vòng lặp đồng thời | Ghi biến parent phải khai báo `shared` |
| `try`, `retry`, `except`, `raise` | Thử lại, bắt, phát sinh lỗi | Chỉ retry tác vụ an toàn |
| `return` | Hoàn tất workflow và xuất giá trị | Không tự ghi kết quả vào DB |

Với YAML, **thụt lề có ý nghĩa**. Phần `steps` phải là **danh sách** (mỗi item bắt đầu bằng `-`), trong khi `assign` là danh sách phép gán. Không viết như một file cấu hình Java/Spring thông thường rồi kỳ vọng engine tự suy thứ tự.

## 3. Expressions và cấu trúc dữ liệu trong execution

Workflows sử dụng ngôn ngữ expression riêng của runtime, viết trong `${...}`; đừng nhầm với Java expression, shell expansion hoặc giả định mọi hàm CEL/JavaScript đều dùng được. Các biểu thức được tính **khi step chạy**, có thể truy cập biến đã được gán.

~~~yaml
- init:
    assign:
      - qty: 3
      - unitPrice: 125
      - total: ${qty * unitPrice}
      - customer:
          id: "C-42"
          tier: "gold"
      - products: ["A", "B"]
- derive:
    assign:
      - customerId: ${customer.id}
      - firstSku: ${products[0]}
      - count: ${len(products)}
      - label: ${"total: " + string(total)}
- result:
    return: ${label}
~~~

Ví dụ trên là **đoạn steps** để gắn vào `main.steps`; kết quả `total` là 375. Dữ liệu hỗ trợ: `null`, boolean, integer/double, string, bytes, list và map.

| Nhu cầu | Cách viết | Ghi chú |
|---|---|---|
| Đọc key map | `${customer.id}` hoặc `${customer["id"]}` | Key có ký tự đặc biệt cần dùng dấu `["..."]` |
| Đọc map an toàn | `${map.get(args, "orderId")}` | Thiếu key trả `null` |
| Giá trị mặc định | `${default(map.get(args, "region"), "asia-southeast1")}` | Chỉ thay khi giá trị là `null` |
| Số phần tử | `${len(items)}` | Dùng cho list, map, string |
| Đổi số thành chuỗi | `${string(total)}` | Không nối trực tiếp string + number |
| Thêm một phần tử list | `${list.concat(items, "C")}` | Tạo **list mới**, không sửa list cũ tại chỗ |
| Built-in env | `${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}` | Không cần hardcode project |
| Chọn nhánh | `${total >= 1000}` | Expression phải thành Boolean |

**Bẫy YAML:** biểu thức chứa dấu hai chấm như `${"Status: " + state}` nên được bọc trong **nháy đơn ở tầng YAML**:

~~~yaml
- format:
    assign:
      - message: '${"Status: " + state}'
~~~

Đừng viết `prefix-${value}` như một chuỗi lai; tạo toàn bộ bằng `${"prefix-" + value}`. Hàm `if(condition, a, b)` **đánh giá cả hai tham số**; nếu cần tránh gọi phép tính gây lỗi ở nhánh không chọn, hãy dùng `switch`.

### Dữ liệu không tự tồn tại ngoài execution

Một map `order` trong Workflows là **biến của execution**, không phải record Cloud SQL. Để transaction bền vững, ghi vào Cloud SQL/Firestore/Cloud Storage thông qua connector hoặc service; Workflows có **execution history/result** nhưng **không phải kho lưu state nghiệp vụ dài hạn**.

## 4. Lab 1 — workflow tự chứa: tính tổng đơn hàng

Ví dụ sau không gọi API bên ngoài. Bạn có thể deploy để thử **input → validate → for loop → subworkflow → return**, không cần tạo Cloud Run hay database. Lưu tên file `orders-total.yaml`:

~~~yaml
main:
  params: [input]
  steps:
    - initialize:
        assign:
          - orderId: ${default(map.get(input, "orderId"), "")}
          - items: ${default(map.get(input, "items"), [])}
          - total: 0
          - skus: []
          - executionId: ${sys.get_env("GOOGLE_CLOUD_WORKFLOW_EXECUTION_ID")}

    - validate:
        switch:
          - condition: ${len(orderId) == 0}
            steps:
              - missingId:
                  raise: "orderId is required"
          - condition: ${len(items) == 0}
            steps:
              - emptyItems:
                  raise: "items must not be empty"

    - accumulate:
        for:
          value: item
          in: ${items}
          steps:
            - checkQuantity:
                switch:
                  - condition: ${item.qty <= 0}
                    steps:
                      - invalidQuantity:
                          raise: "item quantity must be positive"
            - addLine:
                assign:
                  - total: ${total + item.qty * item.unitPrice}
                  - skus: ${list.concat(skus, item.sku)}

    - makeLabel:
        call: formatLabel
        args:
          orderId: ${orderId}
          amount: ${total}
        result: label

    - packageResult:
        assign:
          - output:
              orderId: ${orderId}
              total: ${total}
              skus: ${skus}
              label: ${label}
              executionId: ${executionId}
    - done:
        return: ${output}

formatLabel:
  params: [orderId, amount]
  steps:
    - build:
        return: '${"READY: " + orderId + " / " + string(amount)}'
~~~

Đầu vào phải là **JSON object** có `orderId` là string, `items` là list của các maps chứa `sku`, `qty`, `unitPrice`, trong đó giá và số lượng là số hợp lệ. Ví dụ:

~~~json
{
  "orderId": "ORD-42",
  "items": [
    {"sku": "BOOK", "qty": 2, "unitPrice": 120},
    {"sku": "PEN", "qty": 3, "unitPrice": 15}
  ]
}
~~~

Kết quả có `total = 285`, `skus = ["BOOK", "PEN"]` và `label = "READY: ORD-42 / 285"`. Trường `executionId` thay đổi ở mỗi lần chạy. Trường `unitPrice` chỉ minh họa số nguyên; với tiền thật, **không dùng phép tính double làm nguồn sự thật cho tài chính**. Lưu số nguyên theo đơn vị nhỏ nhất (ví dụ đồng/cents) và xác nhận bằng service/DB có transaction.

**Tại sao cần `formatLabel`?** Đây là **subworkflow**, nhận params và trả giá trị. `main` gọi nó qua `call`, truyền `args` và lưu kết quả vào biến `label`. Subworkflow không tự chia sẻ tất cả biến local của `main`.

## 5. Deploy, truyền JSON input và kiểm tra kết quả

Để deploy Workflows cần project đã bật billing/Workflows API, Google Cloud CLI, tài khoản deployer có quyền tương ứng (ví dụ `roles/workflows.admin`) và quyền `iam.serviceAccounts.actAs` trên workflow runtime service account. Người **chạy execution** dùng quyền tạo execution như `roles/workflows.invoker`; không cần role Admin nếu chỉ gọi workflow.

~~~bash
PROJECT_ID="my-workflows-lab"
REGION="asia-southeast1"
WORKFLOW="orders-total-lab"
WF_SA="orders-orchestrator@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable workflows.googleapis.com \
  workflowexecutions.googleapis.com

# Chỉ tạo service account nếu chưa tồn tại.
gcloud iam service-accounts create orders-orchestrator \
  --display-name="Runtime identity for orders workflow"

# File orders-total.yaml là nội dung đầy đủ ở mục 4.
gcloud workflows deploy "$WORKFLOW" \
  --location="$REGION" \
  --source="orders-total.yaml" \
  --service-account="$WF_SA"

gcloud workflows describe "$WORKFLOW" \
  --location="$REGION"
~~~

Trong lab này, workflow chỉ tính toán trong bộ nhớ và trả kết quả, chưa cần IAM để đọc bucket hay gọi Cloud Run. Khi có `sys.log` hoặc gọi Google Cloud APIs, cấp thêm **đúng permissions** cho `WF_SA` trên tài nguyên liên quan.

Chạy và **chờ execution hoàn thành**:

~~~bash
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"orderId":"ORD-42","items":[{"sku":"BOOK","qty":2,"unitPrice":120},{"sku":"PEN","qty":3,"unitPrice":15}]}'

# Chỉ đọc các executions và trạng thái.
gcloud workflows executions list "$WORKFLOW" \
  --location="$REGION"
~~~

Lệnh `gcloud workflows run` đợi kết quả, còn `gcloud workflows execute` khởi tạo **bất đồng bộ** và trả về execution để theo dõi. Đừng coi việc tạo execution thành công là giao dịch nghiệp vụ đã hoàn thành. Với lệnh trực tiếp, JSON truyền bằng `--data`; trong Bash dùng nháy đơn bao quanh JSON để tránh shell diễn giải dấu nháy kép bên trong.

**Thử lỗi có chủ đích:**

~~~bash
# Thiếu orderId: workflow sẽ FAILED với lỗi validate.
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"items":[{"sku":"BOOK","qty":1,"unitPrice":100}]}'

# Quantity âm: cũng phải FAILED.
gcloud workflows run "$WORKFLOW" \
  --location="$REGION" \
  --data='{"orderId":"BAD-1","items":[{"sku":"BOOK","qty":-1,"unitPrice":100}]}'
~~~

Không chạy lệnh cleanup với tên production. Nếu lab đã xong và workflow không còn được ai gọi:

~~~bash
gcloud workflows delete "$WORKFLOW" --location="$REGION"
~~~

Xóa workflow **không tự xóa** service account, Logs, Cloud Storage hay các dữ liệu đã được các execution trước đó ghi vào dịch vụ ngoài.

## 6. Control flow: `switch`, `next`, `for` và scope

### Nhánh điều kiện và bước tiếp theo

Một `switch` xét các điều kiện **theo thứ tự** và thực thi điều kiện đầu tiên đúng. Nếu không có điều kiện nào đúng, execution tiếp tục step sau đó (trừ khi có nhánh mặc định `condition: true`). Ví dụ:

~~~yaml
- choose:
    switch:
      - condition: ${total >= 1000}
        next: manualReview
      - condition: ${total >= 500}
        next: expressProcess
    next: normalProcess
- manualReview:
    return: "REVIEW_REQUIRED"
- expressProcess:
    return: "EXPRESS"
- normalProcess:
    return: "NORMAL"
~~~

Đoạn trên là **nhóm steps** và giả định `total` đã được gán ở step trước. `next` chỉ nhảy tới step hợp lệ trong cùng phạm vi; không được nhảy tùy ý vào/ra vòng lặp hay nhánh song song.

### Loop qua list và range

~~~yaml
- initialize:
    assign:
      - total: 0
- sum:
    for:
      value: n
      in: [1, 2, 3]
      steps:
        - add:
            assign:
              - total: ${total + n}
- finish:
    return: ${total}
~~~

Kết quả bằng 6. `total` được tạo **ngoài vòng lặp**, nên có thể cập nhật và đọc sau vòng lặp. Ngược lại, `n` và các biến **chỉ được tạo trong loop scope** không được tham chiếu bên ngoài.

Với `range: [1, 3]`, hai đầu **đều được tính**, nên có đúng ba vòng lặp (1, 2, 3). Dùng `next: continue` để bỏ qua iteration hiện tại và `next: break` để thoát vòng lặp, nhưng không nhảy ra một step tùy ý nằm bên ngoài loop.

### Scope của `except` và subworkflow

- Biến được tạo **bên ngoài** `for`/`except` và sửa trong block thường đọc được sau block.
- Biến mới chỉ tạo **trong `for` hoặc `except`** có scope cục bộ; không tham chiếu nó ở bước sau.
- `steps` lồng thông thường **không** tạo scope mới; `subworkflow` có params/local variables riêng.
- Trong `parallel`, biến parent **chỉ được đọc** trong branches trừ khi có khai báo `shared`.

Ví dụ nếu phải lưu lỗi để xử lý sau `except`, hãy khởi tạo biến `errorInfo: null` ở **parent scope** trước `try`, rồi mới gán trong `except`.

## 7. Kết nối Cloud Run và Google Cloud APIs

Workflows có thể dùng `call: http.get`/`http.post` hoặc các **Google Cloud connectors**. Mọi outbound call cần được xem xét **authentication** và IAM của workflow runtime SA.

### HTTP GET tới Cloud Run private service (OIDC)

Giả sử workflow đã có biến môi trường `ORDER_API_URL` là HTTPS root URL của Cloud Run service:

~~~yaml
main:
  params: [input]
  steps:
    - init:
        assign:
          - baseUrl: ${sys.get_env("ORDER_API_URL")}
          - orderId: ${input.orderId}
    - fetch:
        call: http.get
        args:
          url: ${baseUrl + "/orders/" + orderId}
          timeout: 30
          auth:
            type: OIDC
            audience: ${baseUrl}
        result: response
    - done:
        return: ${response.body}
~~~

Đặt user-defined environment variable khi deploy:

~~~bash
gcloud workflows deploy orders-api-flow \
  --location="$REGION" \
  --source=orders-api-flow.yaml \
  --service-account="$WF_SA" \
  --set-env-vars="ORDER_API_URL=https://YOUR-SERVICE-URL.run.app"
~~~

Điều kiện **bắt buộc**: `WF_SA` có `roles/run.invoker` trên **chính Cloud Run service** và backend có route `GET /orders/{id}`. `audience` thường là **service root URL** (không kèm path); token ID của Workflows không phải bearer token do end-user cung cấp. Cloud Run vẫn phải thực hiện business authorization dựa trên ngữ cảnh đã được xác thực.

~~~bash
gcloud run services add-iam-policy-binding orders-api \
  --region="$REGION" \
  --member="serviceAccount:$WF_SA" \
  --role="roles/run.invoker"
~~~

Trường `timeout` là timeout **cho HTTP call của workflow**, không phải cùng giá trị bắt buộc với Cloud Run request timeout; chọn hai mức tương thích và thiết kế retry/idempotency nếu client có thể timeout khi backend đã commit.

### Kết nối Google Cloud APIs: OAuth2 hoặc connector

Khi gọi `https://...googleapis.com` bằng HTTP request, dùng **OAuth2 access token**:

~~~yaml
- readProject:
    call: http.get
    args:
      url: ${"https://cloudresourcemanager.googleapis.com/v3/projects/" + projectId}
      auth:
        type: OAuth2
    result: projectResponse
~~~

Các connector `googleapis.*` tiện hơn vì tự dùng quyền của workflow runtime SA, và một số có hỗ trợ long-running operations. Ví dụ lấy **metadata** object Cloud Storage:

~~~yaml
- getObjectMetadata:
    call: googleapis.storage.v1.objects.get
    args:
      bucket: ${input.bucket}
      object: ${input.object}
    result: objectMetadata
~~~

Với direct Storage connector, workflow SA cần quyền đọc metadata/object như `storage.objects.get` ở đúng bucket (ví dụ vai trò Object Viewer phù hợp). `objectMetadata` là map metadata, **không phải toàn bộ bytes của file**. Không nên đưa object lớn vào `result` hoặc trả raw file content qua execution output.

| Endpoint đích | Cơ chế xác thực | Lỗi điển hình |
|---|---|---|
| Cloud Run private service | `auth: {type: OIDC}`, SA có Invoker | `401/403`, sai audience, service ingress |
| Google APIs trên `googleapis.com` | `auth: {type: OAuth2}` hoặc connector | IAM thiếu role/permission, API chưa bật |
| API ngoài Google Cloud | Auth header theo hệ thống ngoài; bảo vệ secret | Không đặt API key trong source hoặc logs |

**Không dùng `type: OIDC` thay cho OAuth2 đối với mọi Google API**, cũng không dùng OAuth2 access token thay cho Cloud Run ID token. Token được Workflows tạo bằng **workflow runtime SA**, không kế thừa tự động end-user JWT hoặc service account Java của caller.

## 8. Error handling: `try/except/retry` và idempotency

Một `http.get` có thể thất bại vì lỗi mạng, `429`, `502/503/504` hoặc timeout. Thử lại hợp lý giúp ứng dụng chịu lỗi tạm thời, nhưng retry không được làm phát sinh thêm thanh toán hoặc tạo đơn trùng.

Ví dụ **GET có thể retry** theo policy mặc định dành cho thao tác idempotent; `baseUrl` và `orderId` đã được khởi tạo:

~~~yaml
- fetchStatus:
    try:
      call: http.get
      args:
        url: ${baseUrl + "/orders/" + orderId}
        timeout: 20
        auth:
          type: OIDC
          audience: ${baseUrl}
      result: response
    retry:
      predicate: ${http.default_retry_predicate}
      max_retries: 3
      backoff:
        initial_delay: 1
        max_delay: 8
        multiplier: 2
    except:
      as: e
      steps:
        - failWithContext:
            raise:
              stage: "fetchStatus"
              message: "Could not load order status"
~~~

`max_retries: 3` là **ba lần thử lại sau lần đầu**, không phải tối đa ba lần gọi tổng cộng. `except` chạy khi lỗi không được xử lý hoặc retry hết; biến `e` chỉ có scope trong `except`. Nếu cần log lỗi chi tiết, phải lọc các trường có thể chứa token, endpoint nhạy cảm hoặc payload.

**Đừng tự động dùng retry idempotent cho `POST /charge-card`**. Một request có thể đã đến service, database commit thành công, nhưng response bị mất. Thử lại sẽ tính tiền hai lần nếu API không hỗ trợ **idempotency key** và transaction/unique constraint. Có thể dùng `http.default_retry_non_idempotent` khi hiểu rõ retry predicate hạn chế hơn, song **predicate không thay được idempotency ở backend**.

| Lỗi | Hành động khuyến nghị |
|---|---|
| `429` hoặc `503` tạm thời | Retry có backoff/jitter, số lần giới hạn và deadline |
| `401/403` | Kiểm tra IAM/identity; không retry vô hạn khi thiếu quyền |
| `400` dữ liệu đầu vào sai | Trả lỗi nghiệp vụ, không retry |
| `404` order không tồn tại | Xử lý theo business flow; không luôn coi là lỗi hạ tầng |
| Timeout sau thao tác ghi | Tra cứu idempotency/business key trước khi phát lại |
| Lỗi không khôi phục được | `raise` có context, cảnh báo và cơ chế bù trừ |

Workflows không cung cấp distributed transaction xuyên Cloud Run/Cloud SQL/Pub/Sub. Với nghiệp vụ nhiều bước, dùng **saga**: mỗi bước có trạng thái bền vững và thao tác **compensation** được định nghĩa rõ (ví dụ hủy reservation nếu thanh toán thất bại), không mặc định rollback database ở mọi service.

## 9. `parallel` và dữ liệu chia sẻ giữa các nhánh

Hai cuộc gọi độc lập như lấy giá vận chuyển và số lượng tồn kho có thể chạy song song để giảm latency. Ví dụ sử dụng biến `results` tạo trước, đánh dấu `shared` cho phép các nhánh ghi vào map đó:

~~~yaml
main:
  steps:
    - init:
        assign:
          - results: {}
    - fetchInParallel:
        parallel:
          shared: [results]
          concurrency_limit: 2
          branches:
            - inventory:
                steps:
                  - getStock:
                      call: http.get
                      args:
                        url: https://example.com/api/stock
                      result: stockResponse
                  - saveStock:
                      assign:
                        - results["stock"]: ${stockResponse.body}
            - shipping:
                steps:
                  - getShipping:
                      call: http.get
                      args:
                        url: https://example.com/api/shipping
                      result: shippingResponse
                  - saveShipping:
                      assign:
                        - results["shipping"]: ${shippingResponse.body}
    - done:
        return: ${results}
~~~

Hai URL ở đây là **placeholder minh họa**, cần thay bằng endpoint thật và cấu hình `auth`/IAM trước khi deploy. Khi cả hai nhánh thành công, `results` chứa key `stock` và `shipping`, **không có bảo đảm nhánh nào hoàn thành trước**.

**Quy tắc scope trong `parallel`:**

- Biến tạo ở parent scope mặc định **đọc được nhưng không được gán** trong branch; muốn ghi thì khai báo `shared: [results]`.
- Những biến chỉ tạo bên trong một branch là **local của branch**, branch khác không tự đọc được.
- Các phép gán shared trong Workflows có tính **atomic**, nhưng **thứ tự chạy không xác định**. Tránh phụ thuộc vào thứ tự cập nhật nếu logic không giao hoán.
- `concurrency_limit` chỉ hạn chế mức đồng thời **của parallel step đó**; không phải quota toàn hệ thống hay giới hạn truyền tiếp cho mọi nested parallel.
- Khi một nhánh thất bại chưa xử lý, cả `parallel` có thể phát sinh `UnhandledBranchError`; policy `continueAll` khiến các nhánh còn lại cố chạy tiếp.

Một `parallel: for:` có thể xử lý nhiều object IDs đồng thời. Chọn `concurrency_limit` bằng capacity của downstream Cloud Run/Cloud SQL, **không đặt rất cao chỉ để rút thời gian**. Nếu cần hàng triệu events, dùng Pub/Sub/Dataflow/Cloud Run jobs thay vì đưa hàng triệu phần tử vào một list Workflows.

## 10. Quản lý dữ liệu thực thi và giới hạn kích thước

Vì Workflows giữ biến trong từng execution, điều phối phải dùng **metadata nhỏ** chứ không tích lũy dữ liệu lớn. Các giới hạn Workflows được công bố có thể thay đổi; tại thời điểm biên soạn, các con số quan trọng:

| Giới hạn | Giá trị tham khảo | Hệ quả |
|---|---:|---|
| Tổng dữ liệu biến, execution arguments và Eventarc payload | **512 KB** | Không truyền file/response lớn giữa các steps |
| Một string (UTF-8) | **256 KB** | JSON dài/base64 có thể vượt hạn |
| Độ dài một expression | **400 ký tự** | Tách biến/steps/subworkflows thay vì nhồi logic |
| Một execution tồn tại tối đa | **1 năm** | Có thể đợi tác vụ dài, nhưng phải có timeout nghiệp vụ riêng |
| Giữ execution history/results sau khi hoàn thành | **Tối đa 90 ngày** | Không dùng làm kho lưu kết quả dài hạn |

Đây là **giới hạn của engine**, không phải khuyến nghị nên dùng gần hết. Đặc biệt với `parallel`, bộ nhớ cho các biến parent và branch/iteration cũng chịu giới hạn. Lưu list lớn hoặc toàn bộ HTTP response body trong từng vòng lặp có thể khiến execution lỗi dù RAM Cloud Run backend vẫn còn.

### Mẫu quản lý dữ liệu tốt

~~~text
Java API nhận tài liệu
  → Cloud Storage: gs://docs/order-42.pdf (bytes)
  → Workflows arguments:
      {"orderId":"ORD-42","bucket":"docs","object":"order-42.pdf"}
  → Cloud Run/Job xử lý file qua Storage API
  → Cloud SQL/Firestore: processing status + result URI
  → Workflows result: {"orderId":"ORD-42","status":"DONE","resultUri":"gs://..."}
~~~

Thực hành:

- Truyền `id`, `generation`, URI, trạng thái và số liệu tóm tắt; không truyền toàn bộ bytes/PII.
- Dùng `result: response` **chỉ khi thực sự cần body**; nếu response rất lớn, thay backend trả URI hoặc object ID.
- Giải phóng tham chiếu không còn dùng: có thể gán `largePayload: null` sau khi tiêu thụ, nhưng tốt nhất **không tải payload lớn vào engine** ngay từ đầu.
- Với map optional fields, dùng `map.get`/`default` thay vì truy cập trực tiếp key chưa biết tồn tại.
- Chỉ dùng workflow arguments cho tham số được phép quan sát; secrets đi qua Secret Manager/runtime identity.

### Serialization và kiểu dữ liệu

`json.encode_to_string(map)` biến map/list thành JSON string để gửi qua API cần body chuỗi. `json.decode(text)` chuyển JSON string hợp lệ thành giá trị Workflows. HTTP response từ `http.get` có `code`, `headers` và `body`; tùy Content-Type, `body` có thể là map/list/string/bytes. Đừng mặc định `response.body.orderId` luôn tồn tại — xác minh hợp đồng API và null/error cases trước khi đọc.

**Dữ liệu đầu vào cần validation**: Workflows không tự áp Java Bean Validation hoặc schema từ API Gateway. Nếu application gửi `unitPrice` là string nhưng step thực hiện phép nhân, có thể xảy ra `TypeError`. Đặt schema validation ở Java API hoặc step kiểm tra `get_type`/required keys khi cần.

## 11. Gọi Workflows từ Java mà không chờ đồng bộ lâu

Một Java API thường **tạo execution rồi trả execution ID** cho client để tra cứu trạng thái; không giữ một HTTP request mở trong lúc nhiều service chạy. Dùng thư viện Java **`com.google.cloud:google-cloud-workflow-executions`** và **Application Default Credentials (ADC)** của Cloud Run/GKE/App Engine.

Ví dụ Java 21, đầu vào JSON cố định để minh họa; thư viện được quản lý phiên bản qua Google Cloud Libraries BOM tương thích:

~~~java
import com.google.cloud.workflows.executions.v1.ExecutionsClient;
import com.google.cloud.workflows.executions.v1.WorkflowName;
import com.google.cloud.workflows.executions.v1.types.Execution;

public final class StartOrderWorkflow {
    public static void main(String[] args) throws Exception {
        String projectId = "my-workflows-lab";
        String location = "asia-southeast1";
        String workflowId = "orders-total-lab";

        // JSON là STRING nằm trong trường Execution.argument.
        String payload = """
            {"orderId":"ORD-42","items":[
              {"sku":"BOOK","qty":2,"unitPrice":120},
              {"sku":"PEN","qty":3,"unitPrice":15}
            ]}
            """;

        try (ExecutionsClient client = ExecutionsClient.create()) {
            WorkflowName workflow =
                WorkflowName.of(projectId, location, workflowId);
            Execution request = Execution.newBuilder()
                .setArgument(payload)
                .build();
            Execution started = client.createExecution(workflow, request);

            // Execution có thể vẫn ACTIVE: đây là mã nhận dạng,
            // KHÔNG phải kết quả nghiệp vụ đã hoàn thành.
            System.out.println("Execution started: " + started.getName());
        }
    }
}
~~~

Đây là ví dụ **tạo execution**, không poll result. Trong REST API thật, trả `HTTP 202 Accepted` kèm execution ID (có kiểm soát quyền xem), và dùng `getExecution` với polling/backoff hoặc callback/notification khi yêu cầu nghiệp vụ. Với dữ liệu động, dùng JSON serializer như Jackson thay vì nối chuỗi JSON thủ công, tránh injection/sai escape.

Để code Java tạo execution, **runtime service account của Java API** cần quyền `workflows.executions.create` trên workflow (thường qua `roles/workflows.invoker`). Quyền này **khác** với quyền `WF_SA` dùng bên trong workflow để gọi Cloud Run/Storage. Không cấp `roles/workflows.admin` cho API Java chỉ để thực thi một workflow.

## 12. Logs, execution history, bảo mật và chi phí

Workflows tạo execution logs cho bắt đầu/kết thúc; khi cần có thể bật **call logging** hoặc gửi custom log bằng `sys.log`. Lưu ý call logging có thể chứa **arguments, responses và lỗi** tùy mức, nên không bật `log-all-calls` trên production chứa PII/secrets mà không đánh giá rủi ro.

~~~yaml
- logProgress:
    call: sys.log
    args:
      json:
        phase: "validated"
        executionId: ${sys.get_env("GOOGLE_CLOUD_WORKFLOW_EXECUTION_ID")}
        orderId: ${orderId}
      severity: INFO
~~~

Đây là một step để chèn vào workflow đã có `orderId`; nó yêu cầu runtime SA có permission `logging.logEntries.create` (ví dụ `roles/logging.logWriter` trong phạm vi đúng). **Không log JWT, token, password hoặc toàn bộ body API**. Trong hệ thống chứa PII, mã hóa/băm orderId hoặc loại nó khỏi log theo policy.

Theo dõi:

| Tín hiệu | Dùng để phát hiện |
|---|---|
| Execution state: `ACTIVE/SUCCEEDED/FAILED/CANCELLED` | Quy trình còn chạy, thất bại hay bị dừng |
| Số step executions và duration | Quy trình có nhiều vòng lặp, retry hoặc chờ lâu |
| HTTP 4xx/5xx và connector errors | IAM/network/backend có vấn đề |
| Retry count, backoff và timeout | Downstream đang thiếu capacity hoặc có lỗi dai dẳng |
| Workflows call logging / Cloud Logging | Sự cố từng step, rủi ro log dữ liệu nhạy cảm |
| Cloud Run/Cloud SQL/Pub/Sub business status | Chứng minh đã hoàn thành tác vụ, không chỉ kết thúc workflow |
| Billing theo Workflows steps và API downstream | Tối ưu chi phí vận hành |

**Chi phí Workflows phụ thuộc số bước nội bộ/bên ngoài được thực thi**, kể cả calls và retries theo cơ chế tính phí. Một `for` với 10.000 iterations không tương đương chỉ một bước trên hóa đơn; đồng thời vẫn có phí Cloud Run, Storage, Pub/Sub, logging và network. Cần đo số step thực, execution duration và chất lượng SLO, không chỉ số workflow definitions.

### Runbook ngắn

| Lỗi | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| Deploy fail vì YAML | Indentation, sai `steps` list, expression không quote khi có dấu `:` | Kiểm tra source ở step/line lỗi |
| `KeyError` hoặc `TypeError` | Key input thiếu, sai kiểu map/list/number | `map.get`, defaults và contract validation |
| `403` gọi Cloud Run | Workflow runtime SA thiếu Invoker hoặc OIDC audience sai | IAM policy Cloud Run, root URL audience |
| `403` gọi Google API | Thiếu role trên resource, API disabled, Org Policy | Workflow SA, OAuth2/connector, effective IAM |
| `429/503` | Quota hoặc downstream overload | Retry giới hạn, throttling, quan sát quotas |
| Timeout khi POST | Server có thể đã commit nhưng response mất | Check business idempotency trước retry |
| Memory limit exceeded | Lưu payload/list/HTTP response lớn | Thay bằng Cloud Storage/DB URI |
| Parallel unexpected result | Thiếu `shared` hoặc phụ thuộc thứ tự update | Review scopes, commutative operations |
| Java trả execution ID nhưng client tưởng DONE | `createExecution` bất đồng bộ | Poll state/get result hoặc callback |

**Phân tách quyền IAM:** deployer cần tạo/sửa workflow và `actAs` runtime SA; Java caller chỉ cần quyền tạo execution; workflow SA có quyền gọi từng downstream resource. Có thể thêm Workflows → Cloud Run Invoker và Storage Object Viewer theo tài nguyên, không cấp mặc định `Editor/Owner`.

## 13. Tình huống tích hợp: quy trình đặt hàng Java có bù trừ

Nhóm thương mại điện tử triển khai:

~~~text
Java Orders API (Cloud Run)
       │ tạo workflow execution, truyền orderId
       ▼
Workflows
  ├── validate orderId và lookup order
  ├── gọi Cloud Run Inventory: reserve(orderId) idempotently
  ├── gọi Cloud Run Payment: charge(orderId) idempotently
  │       └── nếu fail: release reservation (compensation)
  ├── cập nhật Cloud SQL trạng thái qua Orders service
  └── publish event / trả status + correlation ID
~~~

### Hợp đồng dữ liệu giữa các service

| Trường | Ví dụ | Quy tắc |
|---|---|---|
| `orderId` | `ORD-42` | Business key, không đoán từ execution ID |
| `requestId` | `req-123` | Dùng cho tracing; có thể thay đổi giữa các retries |
| `reservationId` | `RES-42` | Lưu bền vững tại Inventory service |
| `paymentId` | `PAY-42` | Lưu bền vững tại Payment service |
| `workflowExecutionId` | Do Workflows tạo | Theo dõi điều phối, không thay unique business key |
| `status` | `PENDING/PAID/FAILED` | Database/service là nguồn sự thật |

**Thứ tự bước không đủ để bảo đảm giao dịch:** nếu Inventory đã reserve nhưng Payment bị timeout, Workflows phải có chiến lược **truy vấn trạng thái thanh toán** trước khi quyết định retry hoặc release reservation. Một `except` trực tiếp gọi compensation chỉ phù hợp khi đã biết chắc business operation thất bại; nếu trạng thái không chắc chắn, chuyển sang `PENDING_RECONCILIATION` và kiểm tra. Không bù trừ “mù” khi request ghi có thể đã thành công.

### Các giả định cần kiểm thử

1. Cùng `orderId` tạo hai workflow executions: hệ thống vẫn không tạo hai charges nhờ idempotency/unique business constraints ở Payment.
2. Workflows bị cancel/retry giữa hai bước: backend lưu state; một reconciliation job tìm các orders còn PENDING.
3. Inventory tạm trả `503`: step retry có backoff mà không tạo hai reservations.
4. Payment trả `401/403`: sửa service account Invoker/IAM, không tăng retries vô hạn.
5. Payload order lớn: chỉ truyền IDs/URI, không giữ toàn bộ giỏ hàng/file dưới biến Workflows.
6. Nhiều executions cùng chạy: Workflows **không có global shared variable** để bảo vệ số tồn kho; Inventory/DB phải enforce concurrency/atomic update.

**Gợi ý kiến trúc:** dùng Cloud Scheduler/Workflows cho báo cáo tổng hợp theo lịch, Eventarc kích hoạt xử lý object, Pub/Sub làm luồng message fan-out; Workflows tập trung các bước cần **điều phối có thứ tự và nhánh theo kết quả**.

## 14. Checklist trước production

- [ ] Main/subworkflows có `params`, outputs và tên steps dễ tra cứu.
- [ ] Đã kiểm tra schema/type của JSON input và từng HTTP response trước khi truy cập nested fields.
- [ ] Expressions `${...}` dùng đúng hàm Workflows, nháy đơn bọc biểu thức có dấu hai chấm khi cần.
- [ ] Biến được tạo đúng scope; `for`/`except` không để lộ biến cục bộ ngoài block.
- [ ] `parallel` chỉ ghi parent variables qua `shared`; không phụ thuộc thứ tự thực thi.
- [ ] Không lưu file/response lớn trong execution variables; dùng Cloud Storage/DB và truyền IDs.
- [ ] OIDC cho Cloud Run, OAuth2/connector cho Google APIs, IAM theo tài nguyên.
- [ ] Retry chỉ áp dụng với thao tác an toàn hoặc có business idempotency key.
- [ ] Có timeout/circuit breaker và chiến lược compensation/reconciliation khi trạng thái không chắc.
- [ ] Java caller dùng ADC, chỉ có quyền tạo execution, không phải quyền sửa workflow.
- [ ] Có execution history, logs không chứa PII/secrets, dashboard error/latency/cost.
- [ ] CI/CD deploy theo revision/source review; có canary test và rollback cho workflow definition.
- [ ] Có quy trình dọn workflow thử nghiệm, service account/quyền dư và các tài nguyên downstream do lab tạo.

## 15. Bài tập thực hành

**Bài 1 — Steps và expressions.** Cho `args = {"user":"Lan","items":[3,5,8]}`. Viết workflow có `params: [args]`, vòng `for` tính tổng 16, `switch` trả `"LARGE"` nếu tổng lớn hơn 15, ngược lại trả `"SMALL"`. Giải thích tại sao phải khai báo `sum` ngoài vòng lặp.

**Bài 2 — Xử lý dữ liệu thiếu.** Một execution chỉ truyền `{"orderId":"ORD-42"}`. Viết `map.get`/`default` để `items` nhận `[]` khi không có. Tại sao dùng `${args.items}` trực tiếp có thể gây lỗi?

**Bài 3 — Thực thi lab.** Deploy `orders-total.yaml` ở mục 4 vào project thử nghiệm với workflow SA riêng, chạy test input ORD-42 và test lỗi quantity âm. Ghi expected state/result; vì sao `gcloud workflows execute` không phải lời xác nhận giao dịch đã hoàn tất?

**Bài 4 — Scope và parallel.** Hai nhánh song song đọc Inventory và Shipping, cần ghi vào map `results`. Viết `parallel.shared` và hai biến local. Nêu điều gì xảy ra nếu gán `results` khi không đánh dấu shared, và vì sao thứ tự hoàn thành không được bảo đảm.

**Bài 5 — OIDC và OAuth2.** Một workflow gọi `https://orders-abc.run.app/orders/42` và `https://storage.googleapis.com/storage/v1/...`. Chọn `auth.type` đúng cho mỗi URL, IAM role/permissions cần có và giải thích vì sao workflow SA khác Java caller SA.

**Bài 6 — Retry và transaction.** Payment API trả timeout sau khi đã ghi charge. Thiết kế idempotency key, lookup trạng thái, quyết định retry/compensation và giới hạn attempts. Vì sao `http.default_retry_predicate` không bảo đảm “không có thanh toán trùng”?

**Bài 7 — Giới hạn dữ liệu.** Một service trả 800 KB JSON chứa danh sách 5.000 orders. Nếu Workflows giữ toàn bộ body trong `result`, điều gì xảy ra? Hãy đề xuất thiết kế thay thế dùng Cloud Storage URI và phân trang.

**Bài 8 — Java integration.** Dùng `ExecutionsClient` tạo execution cho `orders-total-lab` và trả HTTP 202 kèm execution ID. Nêu những permission IAM tối thiểu của Java runtime SA và workflow runtime SA; thiết kế một endpoint theo dõi trạng thái mà không lộ execution data của tenant khác.

**Bài 9 — Chi phí và vận hành.** Có 100.000 executions/ngày, mỗi execution lặp 25 items và gọi hai HTTP services với retry trung bình 1,2 lần. Liệt kê yếu tố tạo phí trong Workflows và downstream; đề xuất ba cách giảm số steps/calls mà vẫn bảo đảm SLO và audit.

## Tài liệu tham khảo chính thức

- [Workflows overview](https://cloud.google.com/workflows/docs/overview) — vai trò của service trong kiến trúc điều phối.
- [Workflows syntax overview](https://cloud.google.com/workflows/docs/reference/syntax) — cấu trúc steps và reserved words.
- [Steps](https://cloud.google.com/workflows/docs/reference/syntax/steps) — thứ tự thực thi và tên step.
- [Expressions](https://cloud.google.com/workflows/docs/reference/syntax/expressions) — cú pháp `${...}`, hàm và YAML escaping.
- [Variables and scope](https://cloud.google.com/workflows/docs/reference/syntax/variables) — scope của loop/except/subworkflow.
- [Maps and lists](https://cloud.google.com/workflows/docs/reference/syntax/maps) — map keys và `map.get`; [Lists](https://cloud.google.com/workflows/docs/reference/syntax/lists) — `list.concat`.
- [Iteration](https://cloud.google.com/workflows/docs/reference/syntax/iteration) — `for`, range, break/continue.
- [Subworkflows](https://cloud.google.com/workflows/docs/reference/syntax/subworkflows) — `params`/`call`/`result`.
- [Parallel steps](https://cloud.google.com/workflows/docs/reference/syntax/parallel-steps) — `shared`, atomic updates và concurrency.
- [Retry steps](https://cloud.google.com/workflows/docs/reference/syntax/retrying) — retry predicates và backoff.
- [Catch errors](https://cloud.google.com/workflows/docs/reference/syntax/catching-errors) — `try/except` và error maps.
- [Authenticated requests](https://cloud.google.com/workflows/docs/authenticate-from-workflow) — OIDC tới Cloud Run và OAuth2 tới APIs.
- [Create/deploy workflows](https://cloud.google.com/workflows/docs/creating-updating-workflow) — CLI và IAM.
- [Execute a workflow](https://cloud.google.com/workflows/docs/executing-workflow) — `run`/`execute` và kết quả.
- [Execute workflows from Java](https://cloud.google.com/workflows/docs/execute-workflow-client-libraries) — `ExecutionsClient` và ADC.
- [Execution logging](https://cloud.google.com/workflows/docs/log-workflow) — Cloud Logging, `sys.log` và call logging.
- [Workflows quotas and limits](https://cloud.google.com/workflows/quotas) — 512 KB data, expression length và retention.
- [Workflows pricing](https://cloud.google.com/workflows/pricing) — chi phí theo step và tích hợp services.
