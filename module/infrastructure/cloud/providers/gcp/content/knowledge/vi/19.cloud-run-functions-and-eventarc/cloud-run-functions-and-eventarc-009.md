# Cấu hình mạng, secrets và tài nguyên cho Cloud Run functions

Một hệ thống bán lẻ nhận sự kiện ảnh mới trên **Cloud Storage** qua **Eventarc**, chạy function tạo thumbnail rồi ghi kết quả trở lại bucket. Một function khác nhận HTTP request từ ứng dụng nội bộ để đồng bộ đơn hàng với dịch vụ đối tác. Cả hai đều cần chọn đúng đường mạng, danh tính và giới hạn tính toán: không công khai endpoint quản trị ngoài chủ đích; không nhúng API key vào mã nguồn; không tạo quá nhiều kết nối **Cloud SQL** khi sự kiện tăng đột biến.

**Cloud Run functions** (tên gọi hiện đại cho mô hình functions xây dựng trên nền Cloud Run; các quy trình cũ thường gọi là *Cloud Functions thế hệ 2*) cho phép triển khai code theo hàm xử lý HTTP hoặc sự kiện. Với chức năng mạng, secrets và tài nguyên, hãy tư duy theo ba câu hỏi: **ai được gọi hàm, hàm được đi tới đâu, và một instance được dùng bao nhiêu tài nguyên?**

Bài học thuộc chương **Cloud Run functions và Eventarc**, mô-đun **CLOUD_PROVIDERS_GCP**. Nó liên kết IAM/VPC, Cloud Run, Cloud Storage, Cloud SQL và quy trình phát hành, bảo vệ dữ liệu, kiểm soát độ tin cậy và chi phí. Ví dụ ưu tiên ngắn gọn, thực hành có điều kiện và không yêu cầu đọc các bài học khác.

## 1. Mục tiêu và mô hình tổng quan

Sau bài học, bạn có thể:

1. Phân biệt **ingress** vào function với **egress** từ function, và xác thực HTTP với phân quyền truy cập dữ liệu.
2. Chọn **Direct VPC egress**, **Serverless VPC Access connector** hoặc đường Internet/Google APIs phù hợp.
3. Sử dụng **Secret Manager** qua danh tính runtime, nắm khác biệt giữa secret gắn vào biến môi trường và mount thành volume.
4. Chọn **memory, CPU, timeout, concurrency, min/max instances** theo workload, SLO và chi phí.
5. Hiểu đường đi của **Eventarc trigger**, quyền gọi function và yêu cầu xử lý sự kiện trùng.
6. Triển khai, xác minh và xử lý lỗi cấu hình bằng `gcloud`, Cloud Logging và Cloud Monitoring.

~~~mermaid
flowchart LR
    C["HTTP client / Eventarc"] --> IN["Ingress + xác thực"]
    IN --> F["Cloud Run function"]
    SEC["Secret Manager"] -. "Runtime identity" .-> F
    F --> VPC["VPC: Cloud SQL / nội bộ"]
    F --> API["Google APIs / đối tác"]
    RES["CPU, RAM, timeout, concurrency, scaling"] -. "Giới hạn thực thi" .-> F
~~~

Trong sơ đồ, **Ingress/IAM**, **đường egress** và **quyền ứng dụng** là ba lớp riêng. Có đường tới Cloud SQL chưa có nghĩa function đã được phép đăng nhập database.

## 2. Phạm vi cấu hình và cách triển khai

### 2.1. Function nằm trên nền Cloud Run

Một function có **source code + entry point + runtime**, được build thành artifact có thể chạy trên hạ tầng Cloud Run. Các cấu hình áp dụng gồm:

| Nhóm | Ví dụ | Câu hỏi |
| --- | --- | --- |
| **Trigger** | HTTP, Eventarc/CloudEvents | Sự kiện hoặc request nào kích hoạt hàm? |
| **Ingress** | Internal, all, internal + Cloud Load Balancing (theo loại deploy) | Nguồn mạng nào có thể tới endpoint? |
| **Authentication** | IAM Invoker, danh tính Eventarc | Principal nào được phép gọi? |
| **Egress** | Direct VPC egress, connector, Internet/Google APIs | Hàm gọi backend nội bộ và dịch vụ ngoài bằng đường nào? |
| **Secrets** | Secret Manager env/volume | Ai có quyền đọc và bản secret nào được sử dụng? |
| **Capacity** | CPU, memory, timeout, concurrency, min/max instances | Khi tăng tải, hàm dùng tài nguyên và chi phí ra sao? |

**Lưu ý về giao diện quản lý:** có thể triển khai function qua giao diện **Cloud Run** hoặc quy trình **`gcloud functions` thế hệ 2**. Tên cờ có thể khác: chẳng hạn chế độ ingress của `gcloud functions deploy` dùng giá trị như `internal-only`, trong khi `gcloud run` dùng tên tương ứng theo giao diện Cloud Run. **Không trộn hai bộ cờ vào một lệnh**; kiểm tra `gcloud ... --help` của đường triển khai đang sử dụng.

### 2.2. Hai loại function phổ biến

- **HTTP function**: có endpoint HTTP; phải xác định ingress, authentication, timeout và HTTP response hợp lệ. Nếu public, thêm xác thực ở tầng ứng dụng/Cloud Run, HTTPS và bảo vệ tải theo nhu cầu.
- **Event-driven function**: Eventarc định tuyến sự kiện (chẳng hạn Cloud Storage object finalized) đến destination; phải cấu hình **trigger, service account, quyền nhận/gọi và event filters**. Không có nghĩa người dùng Internet cần quyền gọi function.

Eventarc có thể cung cấp **at-least-once delivery**, do đó handler phải chống xử lý trùng và ghi dữ liệu theo **idempotency key**. Các retry có thể tạo tải tăng vọt, ảnh hưởng trực tiếp tới `max instances`, Cloud SQL và chi phí.

## 3. Ingress: ai có thể kết nối tới endpoint?

### 3.1. Ingress không phải IAM

Chế độ ingress quyết định **đường kết nối được chấp nhận**; IAM quyết định **principal nào được invoke**. Một endpoint có chế độ ingress `all` vẫn có thể yêu cầu danh tính được cấp quyền gọi. Ngược lại, cho phép unauthenticated trên một endpoint được định tuyến ra ngoài có thể công khai chức năng nhạy cảm.

| Mục tiêu | Thiết kế ban đầu nên cân nhắc |
| --- | --- |
| Webhook công khai từ đối tác | Ingress phù hợp với Internet, xác thực chữ ký/webhook token, rate limiting, logging và bảo vệ tầng HTTP. |
| API nội bộ của tổ chức | Internal ingress hoặc load balancer nội bộ theo kiến trúc; IAM authentication. |
| Chỉ cho phép qua external Application Load Balancer | Chế độ kết hợp internal + Cloud Load Balancing nếu được hỗ trợ, dùng thêm Cloud Armor/IAP khi thích hợp. |
| Nhận Eventarc | Đảm bảo **đường giao sự kiện từ Eventarc được cho phép** và service account của trigger có quyền invoke. |

Không giả định “internal” nghĩa là mọi VM trong mọi VPC hoặc mọi dịch vụ ở cùng project đều được phép gọi. Cần kiểm tra quy tắc internal source, project/VPC boundaries và loại ingress của sản phẩm.

### 3.2. Xác thực HTTP qua IAM

Với dịch vụ yêu cầu authentication, caller cần token phù hợp và quyền invoke trên destination. Đối với function thế hệ 2 chạy trên Cloud Run, việc gọi HTTP thường liên quan tới **Cloud Run Invoker** (`roles/run.invoker`) và resource được quản lý tương ứng; quyền và cách gán có thể khác với các functions thế hệ trước.

Ví dụ gọi một endpoint **đã được cấp quyền** bằng identity token:

~~~bash
FUNCTION_URL="https://FUNCTION_URL_FROM_DEPLOY"

# READ/REQUEST: chỉ gọi nếu principal đã có quyền invoke.
TOKEN="$(gcloud auth print-identity-token)"
curl --fail-with-body -H "Authorization: Bearer $TOKEN" "$FUNCTION_URL"
~~~

`FUNCTION_URL` là placeholder. Đây là ví dụ thử nghiệm với danh tính `gcloud` đã đăng nhập; với **service-to-service production**, dùng identity token cấp cho đúng service account và `audience` là URL đích (hoặc custom audience đã cấu hình), theo tài liệu Cloud Run. Tham số `--audiences` của `gcloud auth print-identity-token` có giới hạn theo loại credential/impersonation, nên không áp máy móc cho user token. Không in token ra logs. `curl --fail-with-body` đòi curl hỗ trợ; nếu không, dùng `curl -i`. Có quyền xem function **chưa chắc** có quyền invoke.

### 3.3. Eventarc có danh tính gửi sự kiện riêng

Eventarc trigger thường dùng một **service account** để xác thực yêu cầu giao sự kiện tới Cloud Run destination. Ngoài quyền gọi destination, một số loại trigger cần quyền **Eventarc Event Receiver** và các vai trò liên quan đến Pub/Sub hoặc nguồn sự kiện, tùy loại sự kiện và project.

~~~text
Cloud Storage object finalized
      ↓
Eventarc trigger + event filters
      ↓   [trigger service account / IAM]
Cloud Run function
      ↓   [runtime service account / IAM]
Cloud Storage / Cloud SQL
~~~

**Trigger identity và runtime identity không phải một.** Cấp quyền đọc bucket cho trigger SA không mặc nhiên cho code function đọc object, và cấp quyền cho runtime SA không giúp Eventarc invoke destination nếu thiếu quyền riêng.

## 4. Egress: function kết nối tới đâu?

### 4.1. Ba nhóm đích

1. **Google APIs:** Cloud Storage, Secret Manager, Pub/Sub... cần egress/DNS hợp lệ và quyền IAM; không nhất thiết đi vào VPC riêng.
2. **Private resource trong VPC:** Cloud SQL private IP, VM không có public IP, internal load balancer; cần phương án đưa traffic vào VPC.
3. **Internet hoặc dịch vụ đối tác:** cần chính sách egress, DNS, TLS và có thể yêu cầu địa chỉ IP nguồn cố định để đối tác allowlist.

**Cấu hình mạng không cấp IAM.** Mở đường TCP tới Cloud SQL không tự cấp quyền `cloudsql.instances.connect` hoặc quyền đăng nhập PostgreSQL.

### 4.2. Direct VPC egress và Serverless VPC Access connector

| Cách kết nối | Mô tả | Khi cần cân nhắc |
| --- | --- | --- |
| **Direct VPC egress** | Function trên nền Cloud Run gửi outbound tới VPC theo cấu hình network/subnet được sản phẩm hỗ trợ, **không cần connector**. | Ưu tiên khảo sát ở môi trường hỗ trợ, giảm tài nguyên connector cần quản lý. |
| **Serverless VPC Access connector** | Tạo connector được quản lý để function đi vào VPC; connector cần region, subnet/CIDR, capacity và IAM thích hợp. | Dùng khi workflow/tính năng hiện tại cần connector hoặc kiến trúc đã chuẩn hóa theo đó. |
| **Không kết nối VPC** | Gọi Google APIs và endpoint public theo mô hình egress của nền tảng. | Function không cần private resources. |

Direct VPC egress và connector **không nên được cấu hình chồng chéo** cho cùng luồng khi không có thiết kế được hỗ trợ. Tùy giao diện triển khai function và thế hệ dịch vụ, các cờ hỗ trợ Direct VPC egress có thể khác; xem chính xác `gcloud run deploy`/`gcloud functions deploy` và docs đang áp dụng.

### 4.3. Chọn phạm vi chuyển lưu lượng vào VPC

- **`private-ranges-only`**: định tuyến các đích thuộc những dải private/range được cơ chế sản phẩm nhận biết qua đường VPC; traffic khác theo đường egress mặc định.
- **`all`**: định tuyến toàn bộ outbound traffic qua VPC được cấu hình, kể cả traffic cần đi Internet, vì vậy **Cloud NAT/route/firewall** hoặc phương án egress khác có thể cần thiết.

Không coi `private-ranges-only` là một bộ lọc bảo mật chỉ cho phép kết nối đến private IP. Nó là **lựa chọn đường đi**, không phải firewall. Với Direct VPC egress, tên cờ CLI có thể là `--vpc-egress` thay vì `--egress-settings` của quy trình connector.

~~~mermaid
flowchart TB
    F["Cloud Run function"] --> E{"Egress mode?"}
    E -- "private ranges" --> PRIV["Private IP → VPC"]
    E -- "all traffic" --> VPC["Mọi outbound → VPC"]
    F --> API["Google APIs/public endpoint\nqua đường egress phù hợp"]
    VPC --> NAT["Cloud NAT/proxy/firewall\nnếu cần Internet"]
    PRIV --> SQL["Cloud SQL private IP / VM / internal LB"]
~~~

Sơ đồ đơn giản hóa routing: đường đi thực tế tới Google APIs phụ thuộc **DNS và phạm vi route của VPC**. Khi dùng restricted/private Google APIs endpoint hoặc Private Service Connect, phải cấu hình DNS, route và policy cụ thể, không chỉ bật một cờ.

### 4.4. Những điều kiện mạng thường bị quên

- Function, VPC subnet/connector và tài nguyên đích phải tương thích **region**, route và quyền Shared VPC nếu có.
- Với Cloud SQL private IP, kiểm tra **Private Service Access hoặc Private Service Connect**, cách chọn database endpoint và quyền database.
- Với `all` traffic, function vẫn cần **đường egress tới Google APIs**, Artifact Registry hoặc nguồn ngoài theo kiến trúc và chính sách.
- Nếu đối tác cần allowlist một IP nguồn cố định, thiết kế VPC egress + **Cloud NAT có địa chỉ IP tĩnh** hoặc egress proxy tương ứng, sau đó **kiểm tra IP thực**; Cloud Run không tự bảo đảm một public egress IP cố định.
- **VPC firewall, route, Cloud NAT, DNS và IAM** có vai trò khác nhau. Lỗi timeout không nên sửa bằng role Editor.

## 5. Secret Manager và danh tính runtime

### 5.1. Secrets không phải environment variables thuần túy

**Secret Manager** giữ các phiên bản secret (API tokens, database credentials...), còn function tham chiếu secret trong cấu hình. Cách phổ biến:

| Cơ chế | Khi secret được đọc | Ưu điểm | Rủi ro cần quản lý |
| --- | --- | --- | --- |
| **Secret → environment variable** | Được cung cấp cho instance theo phiên bản khi khởi tạo. | Ứng dụng đọc đơn giản qua `os.getenv`/`System.getenv`. | Instance đang chạy không tự nhận giá trị mới; cần chính sách rollout/restart và tránh log env. |
| **Secret → mounted volume** | Đọc file trong container theo hành vi mount/version được hỗ trợ. | Tách khỏi process env; có thể hỗ trợ đọc bản cập nhật theo cách cấu hình. | Quyền filesystem, thời điểm đọc, caching và khả năng ứng dụng reload. |
| **Gọi Secret Manager API trong code** | Theo yêu cầu của ứng dụng. | Linh hoạt kiểm soát thời điểm/version/cache. | Tăng API calls/latency, xử lý retries và IAM/network. |

Không lưu secret trực tiếp vào `--set-env-vars=API_TOKEN=gia-tri-bi-mat`, Git, Docker image, startup script hoặc logs. **Secret resource name/ID** thường không phải giá trị bí mật, nhưng cũng nên tuân thủ quy tắc đặt tên của tổ chức.

### 5.2. Quyền tối thiểu để đọc secret

Giả sử runtime service account `fn-orders-runtime@retail-lab.iam.gserviceaccount.com` cần đọc **duy nhất** secret `partner-api-token`. Cấp `roles/secretmanager.secretAccessor` ở phạm vi **secret cụ thể**:

~~~bash
# WRITE: minh họa gán IAM; SA và secret phải tồn tại.
gcloud secrets add-iam-policy-binding partner-api-token \
  --project=retail-lab \
  --member="serviceAccount:fn-orders-runtime@retail-lab.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# READ-ONLY: xem binding trực tiếp của secret.
gcloud secrets get-iam-policy partner-api-token \
  --project=retail-lab
~~~

Không cấp `roles/secretmanager.admin` cho function chỉ cần đọc. Quyền gán ở project hoặc tổ tiên có thể rộng hơn dự kiến; hãy kiểm tra **effective permissions** và điều kiện IAM/deny policy, không chỉ binding trên secret.

### 5.3. Gắn secret theo phiên bản

Ví dụ cấu hình Cloud Run functions qua `gcloud functions deploy` thế hệ 2:

~~~bash
# WRITE: chỉ định secret reference, không gửi secret value lên CLI.
# Dùng phiên bản số đã kiểm tra giúp triển khai có thể tái lập.
gcloud functions deploy orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --runtime=python312 \
  --source=. \
  --entry-point=orders_hook \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --set-secrets="PARTNER_API_TOKEN=partner-api-token:3"
~~~

Giá trị `3` chỉ là **ví dụ phiên bản secret**. Chỉ dùng sau khi tạo secret version thực tế; không coi `:latest` là lựa chọn mặc định tốt nhất khi cần release có thể rollback chính xác. Với volume mount, cú pháp flag khác và phải xác minh quyền đọc path/việc cập nhật phiên bản. **Không chạy lệnh nếu chưa có source code** và chưa kiểm tra region, runtime/flag support.

Đối với các function được tạo qua Cloud Run console/`gcloud run`, cấu hình secret có thể dùng flags khác (`--set-secrets`/volume mount theo workflow hỗ trợ). Không sao chép cờ của `gcloud functions` sang `gcloud run` mà không xem `--help`.

### 5.4. Rotation và khôi phục

Một kế hoạch rotation an toàn:

1. Tạo **secret version mới**; không ghi đè secret cũ.
2. Xác minh token mới hoạt động với đối tác/database và IAM runtime không đổi.
3. Cập nhật function sang version mới hoặc cơ chế mount đọc version mới theo kiến trúc; rollout có kiểm soát.
4. Theo dõi 401/403 từ đối tác, 5xx, retry và thời gian phản hồi.
5. Thu hồi token cũ **sau khi** xác minh mọi instance/revision dùng token mới.

Gán `latest` cho environment variable **không làm các instance đang chạy tự refresh biến môi trường**. Secret mount có thể có hành vi cập nhật khi đọc file, nhưng ứng dụng phải **đọc lại**, không cache vô hạn; kiểm tra điều kiện phiên bản và volume thực tế.

## 6. Cấu hình tài nguyên và hành vi scale

### 6.1. Những giới hạn quan trọng

| Cấu hình | Tác động | Nguy cơ khi đặt sai |
| --- | --- | --- |
| **Memory** | RAM cho runtime, thư viện, dữ liệu trung gian. | OOM khi giải mã ảnh/file lớn, function bị dừng. |
| **CPU** | Tốc độ xử lý và khởi tạo; phải tương thích memory/concurrency. | Chậm do thiếu CPU hoặc tốn phí vì cấp quá mức. |
| **Timeout** | Thời gian tối đa một request/instance execution được phép theo loại function. | Timeout khi tác vụ dài; retry có thể làm lại side effects. |
| **Concurrency** | Số request/sự kiện đồng thời trên một instance theo cấu hình hỗ trợ. | Race, memory contention, connection pool vượt giới hạn. |
| **Minimum instances** | Giữ capacity ấm để giảm xác suất cold start. | Tăng chi phí khi ít traffic. |
| **Maximum instances** | Giới hạn số instance scale-out theo chính sách. | Quá thấp làm backlog/latency tăng; quá cao làm downstream nghẽn. |

**Cấu hình khả dụng phụ thuộc cách triển khai và nền tảng.** Cloud Run functions, Cloud Run services và functions thế hệ 1 không có cùng tập giới hạn/cờ CLI. Với event-triggered workloads, timeout request và cơ chế retry của Eventarc phải được xem cùng nhau; một sự kiện bị giao lại có thể chạy song song với lần xử lý trước nếu thiết kế không có khóa/idempotency.

### 6.2. Cân bằng concurrency và Cloud SQL

Giả sử function cấu hình:

~~~text
max instances = 20
concurrency = 10
DB connection pool tối đa mỗi instance = 5
~~~

Đây là **giới hạn lý thuyết**, không phải số kết nối luôn mở:

~~~text
Số request đồng thời có thể tiếp nhận tối đa ≈ 20 × 10 = 200
Số DB connections từ pools tối đa ≈ 20 × 5 = 100
~~~

Nếu Cloud SQL chỉ còn 60 kết nối khả dụng cho workload này, cấu hình pool/max instances ở trên có thể gây lỗi dù function còn CPU. Cần **load test, connection reuse, pool sizing, retry/backoff** và kiểm soát fan-out từ Eventarc.

### 6.3. Timeout và các tác vụ dài

Không chọn timeout rất lớn chỉ để “chắc chắn job hoàn thành”. Một handler đang xử lý sự kiện có thể bị dừng hoặc được retry, nên:

- Xử lý mỗi sự kiện thành những bước nhỏ; lưu checkpoint và idempotency key ở nơi bền vững.
- Trả thành công **chỉ khi** side effect đã commit an toàn.
- Nếu tác vụ dài vượt giới hạn runtime hoặc cần checkpoint phức tạp, cân nhắc **Cloud Run jobs**, **Cloud Batch**, Workflows hoặc queue workers.
- Nếu phải gọi downstream chậm, đặt timeout của **HTTP client** nhỏ hơn function timeout và xử lý lỗi rõ ràng.

### 6.4. Chi phí của minimum instances

Minimum instances có thể giảm độ trễ khởi động cho function có traffic thưa nhưng yêu cầu latency nghiêm ngặt. Tuy nhiên không loại bỏ mọi cold start khi scale vượt mức tối thiểu hoặc có revision mới. Đo:

- p95/p99 request hoặc thời gian hoàn thành event;
- số instances được khởi tạo, concurrency, CPU/memory;
- tỷ lệ lỗi/timeout/retry;
- **Cloud Run billing**, chi phí VPC connector/NAT và log volume.

## 7. Ví dụ thực hành: HTTP function có secret

### 7.1. Source code tự chứa

Ví dụ Python tối giản dùng `functions-framework`, lấy một secret **qua environment injection** và trả về trạng thái cấu hình (không lộ secret). Tạo hai file **trong thư mục source thực hành** khi triển khai; phần bài học không tạo những file này.

`main.py`:

~~~python
import os
import functions_framework

@functions_framework.http
def orders_hook(request):
    # Chỉ dùng IAM authenticated invocation ở môi trường này.
    # Không trả, không log hoặc ghi nguyên giá trị secret.
    token = os.getenv("PARTNER_API_TOKEN")
    if not token:
        return {"error": "server_not_configured"}, 503

    # Demo: ứng dụng thật dùng token để gọi đối tác qua HTTPS,
    # với client timeout, redaction trong logs và idempotency.
    return {"status": "configured"}, 200
~~~

`requirements.txt`:

~~~text
functions-framework>=3,<4
~~~

Ví dụ chỉ minh họa **đọc Secret Manager thông qua runtime injection**. Nó không chứng minh giao dịch với đối tác đã thành công. Khi phát triển thật, pin dependency versions để tái lập build, kiểm thử HTTPS/authentication và không dựa vào token này để thay thế IAM Invoker.

### 7.2. Tạo secret và service account

Những tài nguyên sau phải được tạo/phê duyệt trước khi deploy. Thay giá trị project/email mẫu:

~~~bash
# READ-ONLY: kiểm tra context trước mọi thao tác ghi.
gcloud auth list
gcloud config get-value project

gcloud secrets describe partner-api-token --project=retail-lab
gcloud iam service-accounts describe \
  fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --project=retail-lab
~~~

Nếu secret/SA chưa tồn tại, tạo qua quy trình IAM/Secret Manager của tổ chức rồi cấp `secretAccessor` như phần 5. **Không dùng `echo "SECRET"` hoặc lưu secret value trong file/command history** để minh họa tạo phiên bản.

### 7.3. Triển khai có giới hạn tài nguyên

Trong thư mục source chứa `main.py` và `requirements.txt`:

~~~bash
# WRITE: deploy function gen2; cần API/IAM/build permissions phù hợp.
gcloud functions deploy orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --runtime=python312 \
  --source=. \
  --entry-point=orders_hook \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=fn-orders-runtime@retail-lab.iam.gserviceaccount.com \
  --set-secrets="PARTNER_API_TOKEN=partner-api-token:3" \
  --memory=512MB \
  --timeout=60s \
  --max-instances=10 \
  --min-instances=0
~~~

Ví dụ dùng `gcloud functions` thế hệ 2 để minh họa các thông số phổ biến; tính năng/concurrency/CPU phụ thuộc CLI và runtime. Nếu đang sử dụng giao diện triển khai Cloud Run functions mới hơn, hãy dùng đúng flags tương ứng và xác minh cấu hình sau deploy. Nếu function cần quyền gọi Secret Manager, runtime SA phải có `secretAccessor` trên secret/version được tham chiếu. Nếu thiếu, container có thể **không khởi động được** hoặc không có secret khi chạy.

### 7.4. Thêm VPC egress khi thực sự cần

Nếu function cần truy cập **Cloud SQL private IP** hoặc một internal HTTP service, hãy chọn **một** phương án networking được hỗ trợ. Ví dụ với connector đã được quản trị và cấp quyền:

~~~bash
# WRITE: cập nhật bằng cách redeploy qua cùng workflow và source.
# Các flags dưới đây là PHẦN BỔ SUNG cho lệnh deploy ở trên,
# không phải lệnh độc lập để chạy riêng.
--vpc-connector=projects/retail-lab/locations/asia-southeast1/connectors/retail-egress
--egress-settings=private-ranges-only
~~~

Nếu chọn **Direct VPC egress** trong một workflow hỗ trợ Cloud Run configuration, hãy chỉ định network/subnet và vpc egress theo đúng CLI/API đó, **không đồng thời gắn connector**. Cần kiểm tra Shared VPC IAM, subnet capacity, firewall, DNS và đường tới Cloud SQL. Với `all` traffic, phải có egress path hợp lệ tới Internet/Google APIs.

### 7.5. Xem cấu hình thực tế và kiểm thử

~~~bash
# READ-ONLY: đối chiếu cấu hình function sau khi deploy.
gcloud functions describe orders-hook \
  --gen2 \
  --project=retail-lab \
  --region=asia-southeast1 \
  --format=yaml
~~~

Đọc các nhóm trường tương ứng với **serviceConfig**, ingress, egress, secret injection, service account, memory, timeout, concurrency và scaling. Không chỉ tin vào command đã gửi: policy tổ chức, API hoặc phiên bản CLI có thể ảnh hưởng cấu hình kết quả.

Thực hiện một HTTP request có identity token đúng audience và quyền invoke như phần 3; kỳ vọng response `{"status":"configured"}` nếu secret/version được gắn thành công. Nếu trả 503, kiểm tra Secret Manager reference và runtime permissions, **không bật unauthenticated để sửa lỗi**.

## 8. Eventarc: tách luồng giao sự kiện khỏi egress của function

### 8.1. Ví dụ Cloud Storage finalized event

Một object mới được ghi vào bucket và Eventarc chuyển CloudEvent tới function:

~~~mermaid
sequenceDiagram
    participant G as Cloud Storage
    participant E as Eventarc trigger
    participant F as Cloud Run function
    participant S as Cloud Storage output
    G->>E: Object finalized event
    E->>F: CloudEvent qua danh tính trigger
    F->>S: Đọc/ghi object bằng runtime SA
    F-->>E: Hoàn tất hoặc báo lỗi
~~~

Không nhầm ba quyền: **source phát sự kiện**, **trigger gọi destination**, **function truy cập bucket**. Khi triển khai Eventarc trigger, xác định nguồn event, location, filters, trigger SA và delivery retries phù hợp với dịch vụ đích. Nếu đặt ingress quá chặt mà đường giao của Eventarc không được hỗ trợ, function có thể không nhận sự kiện dù Eventarc trigger tồn tại.

### 8.2. CloudEvent handler minh họa

~~~python
import functions_framework

@functions_framework.cloud_event
def on_image_finalized(event):
    event_id = event["id"]
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")
    generation = data.get("generation")

    if not bucket or not name:
        raise ValueError("Missing Cloud Storage object metadata")

    # Dùng (bucket, name, generation) làm khóa idempotency.
    # Cần lưu trạng thái COMMITTED ở nơi bền vững trước khi
    # xác nhận thành công; không dùng bộ nhớ instance để chống trùng.
    print(f"event_id={event_id} object={bucket}/{name} generation={generation}")
~~~

Mẫu trên chỉ đọc metadata, **chưa thực hiện tạo thumbnail hay ghi kết quả**. Bài toán thực tế phải xử lý:

- Sự kiện có thể được giao **lặp lại** hoặc không theo thứ tự mong muốn.
- `event_id` và object `generation` dùng để nhận diện, nhưng không chỉ kiểm tra một biến trong RAM.
- Tránh **trigger loop** nếu function ghi output trở lại chính bucket/prefix có filter kích hoạt.
- Với lỗi tạm thời, dùng retry/backoff và dead-letter/quan sát phù hợp với nguồn/đường trigger; với lỗi dữ liệu cố định, tránh lặp vô hạn.
- Kiểm soát max instances để event burst không làm Cloud SQL hoặc dịch vụ đối tác quá tải.

## 9. Bảo mật, vận hành và chi phí

### 9.1. Tách danh tính

| Principal | Nhu cầu | Phạm vi quyền |
| --- | --- | --- |
| **CI/deployer** | Build/deploy function, chỉ định runtime SA/trigger. | Quyền triển khai phù hợp và `iam.serviceAccounts.actAs` khi cần. |
| **Eventarc trigger SA** | Giao sự kiện tới function. | Event receiver/invoker và quyền nguồn sự kiện theo workflow. |
| **Runtime SA** | Đọc secret, Cloud Storage/Cloud SQL. | Secret Accessor và quyền dữ liệu **theo tài nguyên tối thiểu**. |
| **Người gọi HTTP** | Invoke function đã bảo vệ. | Cloud Run Invoker trên destination khi áp dụng. |
| **SRE/auditor** | Xem logs, metrics và cấu hình. | Reader/Logging/Monitoring permissions phù hợp; không cần Admin mặc định. |

Secrets, event payload và thông tin request có thể chứa dữ liệu nhạy cảm. Không log token, headers bí mật, database password hoặc toàn bộ CloudEvent payload trước khi đánh giá dữ liệu cá nhân.

### 9.2. Định lượng chi phí

~~~text
Tổng chi phí vận hành ≈
  Cloud Run CPU/RAM/requests/instance time
  + minimum instances (nếu bật)
  + VPC connector hoặc Direct VPC egress-related networking
  + Cloud NAT / transfer / load balancing (nếu dùng)
  + Secret Manager access/version storage
  + Eventarc / Pub/Sub và downstream services
  + Cloud Logging / Monitoring
~~~

Đây là mô hình phân loại, không phải công thức Billing chính thức. Một function có RAM 2 GiB có thể không cần thiết cho webhook nhỏ, nhưng function resize ảnh lớn có thể OOM ở 256 MiB. Cần đo **p95 latency, memory peak, lỗi, retries, instances và chi phí mỗi sự kiện hoàn thành**; không chỉ đo thời gian một lần gọi.

### 9.3. Mốc rollout an toàn

1. Đọc cấu hình hiện tại và lưu lại source revision/runtime SA/trigger.
2. Áp thay đổi networking/secrets/capacity trong staging.
3. Thử request/sự kiện hợp lệ, lỗi IAM và một số tình huống retry/idempotency.
4. Quan sát Cloud Logging/Monitoring, Secret Manager audit và Cloud SQL connections.
5. Phát hành có review và phương án rollback cấu hình/phiên bản secret.

Không dùng thay đổi ingress, VPC egress, secret version và timeout **đồng thời** trong một lượt thử nghiệm khi chưa có baseline; nếu lỗi sẽ khó xác định nguyên nhân.

## 10. Troubleshooting theo triệu chứng

| Dấu hiệu | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| HTTP `403` trước khi vào handler | Caller thiếu quyền invoke hoặc token sai audience. | Function/Cloud Run IAM, identity token, ingress mode. |
| Client timeout, không có application log | Ingress/network route/DNS hoặc không đến được endpoint. | Ingress settings, LB, DNS/TCP/TLS và logs. |
| Eventarc trigger có nhưng function không chạy | Filter sai, trigger identity thiếu quyền, delivery/ingress không hợp lệ. | Eventarc trigger state, service agent/Invoker, logs. |
| Container không startup vì secret | Secret/version không tồn tại hoặc runtime SA thiếu `secretAccessor`. | Secret reference, IAM binding, revision logs. |
| Rotation xong vẫn dùng token cũ | Environment variable được nạp từ instance cũ hoặc app cache. | Revision/instance lifecycle, version reference, volume behavior. |
| Cloud SQL private IP timeout | Thiếu VPC egress, route/PSA/PSC, firewall hoặc DNS. | Egress mode, connector/Direct VPC, subnet/DB connectivity. |
| Google APIs lỗi khi bật `all` traffic | Thiếu Cloud NAT/route/DNS/private API path. | VPC route, NAT, DNS và Google APIs endpoint. |
| Event burst gây 5xx hoặc DB cạn connection | Max instances/concurrency/pool/retry quá lớn. | Instance count, DB connections, queue/retry metrics. |
| Function OOM hoặc timeout | Memory quá thấp, tác vụ quá dài hoặc remote dependency chậm. | Peak memory, request duration, timeout từng client call. |
| Chi phí tăng sau bật min instances/connector | Capacity ấm, connector/NAT và logging tồn tại cả khi ít traffic. | Billing theo SKU, số instance và network usage. |

**Thứ tự chẩn đoán:** (1) trigger/HTTP ingress → (2) IAM caller → (3) runtime SA/secret → (4) egress DNS/VPC/firewall → (5) CPU/RAM/timeout/concurrency → (6) downstream và logic idempotency. Một lỗi `PERMISSION_DENIED` từ Secret Manager không được sửa bằng tăng RAM.

## 11. Bài tập

### Bài 1 — Phân biệt ingress và egress

Một HTTP function chỉ được gọi từ dịch vụ nội bộ nhưng phải truy cập một public API đối tác. Chọn ingress và egress theo tiêu chí nào? Vì sao thiết lập `internal-only` không tự ngăn function gọi Internet?

### Bài 2 — Cloud SQL private IP

Function đọc secret thành công nhưng không thể kết nối PostgreSQL qua `10.x.x.x:5432`. Đề xuất kiểm tra **Direct VPC egress hoặc connector, subnet/region, PSA/PSC, DNS, route, firewall, database auth** theo thứ tự hợp lý. Tại sao cấp `secretAccessor` không giải quyết lỗi mạng?

### Bài 3 — IAM tối thiểu

Thiết kế quyền cho deployer, Eventarc trigger SA, runtime SA và người gọi HTTP. Principal nào cần Reader/Accessor trên Secret Manager? Principal nào cần invoke? Vì sao không cấp project Editor cho tất cả?

### Bài 4 — Rotation

Một function dùng `PARTNER_API_TOKEN=partner-api-token:3` qua environment variable. Sau khi tạo version `4`, function có tự chuyển sang dùng version mới không? Hãy lập checklist đổi version và rollback.

### Bài 5 — Chọn tài nguyên

Function resize ảnh có peak RAM 700 MiB, thời gian chạy p95 = 18 giây, có lúc nhận 2.000 sự kiện trong một phút. Hãy đề xuất memory, timeout, concurrency và max instances để thử nghiệm; cần đo những gì trước khi chốt thông số?

### Bài 6 — Phân tích connection pool

Function có `max instances=20`, `concurrency=10`, mỗi instance tối đa 5 DB connections. Tính concurrency request và số DB connections tối đa giả định, rồi đề xuất giảm tải khi Cloud SQL chỉ còn 60 kết nối.

**Gợi ý:** 200 requests và 100 connections là trần giả định; giới hạn hiệu quả còn tùy CPU, memory và ứng dụng.

### Bài 7 — Eventarc giao trùng

Một sự kiện Cloud Storage finalized được xử lý hai lần vì lần đầu đã tạo thumbnail nhưng handler timeout trước khi xác nhận. Thiết kế idempotency key, trạng thái commit bền vững và cách tránh ghi output kích hoạt một vòng sự kiện vô hạn.

### Bài 8 — Tính chi phí

So sánh hai phương án: function A min instances bằng 0, không VPC connector; function B min instances bằng 1, dùng connector và Cloud NAT. Với traffic chỉ 30 request/ngày, bạn sẽ đo yếu tố nào để kết luận B đáng chi phí hơn?

## 12. Checklist trước production

| Hạng mục | Tiêu chí |
| --- | --- |
| **Trigger/ingress** | HTTP/Eventarc rõ ràng, đường giao sự kiện hợp lệ, không công khai ngoài chủ đích. |
| **Authentication** | Invoker/trigger SA được giới hạn đúng destination, token/audience hợp lệ. |
| **Runtime identity** | SA riêng, có quyền Secret Manager và dữ liệu cần thiết, không dùng khóa JSON tĩnh. |
| **VPC egress** | Direct VPC hoặc connector được chọn có chủ đích, network/subnet/region đúng. |
| **Network path** | DNS, route, firewall, Cloud NAT/Google APIs/PSA/PSC được kiểm thử. |
| **Secrets** | Dùng secret references, version/rotation/rollback rõ ràng; không log secret. |
| **Resources** | CPU/memory/timeout/concurrency/min/max instances được load test theo SLO. |
| **Event semantics** | Có idempotency, retry/backoff, tránh trigger loop và kiểm soát burst. |
| **Observability** | Logs/traces/errors, event deliveries, memory, DB connections và chi phí. |
| **Release** | Source/revision/config được quản lý, có staging, phê duyệt và rollback. |

## 13. Tài liệu chính thức

Đối chiếu hạn mức, cờ CLI và quyền IAM theo loại Cloud Run functions hiện hành:

- [Cloud Run functions overview](https://cloud.google.com/run/docs/functions/overview)
- [Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions)
- [Cloud Run ingress](https://cloud.google.com/run/docs/securing/ingress)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Serverless VPC Access connectors](https://cloud.google.com/vpc/docs/serverless-vpc-access)
- [Configure secrets for Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control)
- [Cloud Run CPU and memory](https://cloud.google.com/run/docs/configuring/services/cpu)
- [Cloud Run concurrency](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run scaling and instance limits](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [Eventarc triggers and CloudEvents](https://cloud.google.com/eventarc/docs/overview)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [gcloud functions deploy](https://cloud.google.com/sdk/gcloud/reference/functions/deploy)

**Ghi nhớ:** cấu hình function an toàn cần **đúng nguồn gọi (ingress + IAM), đúng đường đi (egress + VPC/DNS/NAT), đúng danh tính đọc secrets (runtime SA + Secret Manager)** và **đúng hạn mức tài nguyên**. Với Eventarc, phải tách quyền giao sự kiện khỏi quyền runtime và thiết kế handler chịu được retry. Đo latency, lỗi, độ bền kết quả và chi phí theo workload thật trước khi đưa vào production.
