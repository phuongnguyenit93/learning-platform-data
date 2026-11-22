# Revisions, traffic splitting và rollback trong Cloud Run

Một ứng dụng Java `orders-api` trên Cloud Run đang phục vụ hàng nghìn yêu cầu mỗi phút. Nhóm phát hành phiên bản mới để tối ưu xử lý đơn hàng, nhưng chỉ muốn **một phần nhỏ người dùng** chịu ảnh hưởng trước khi mở rộng. Nếu tỷ lệ lỗi tăng, nhóm cần **chuyển request về bản ổn định** mà không đợi build lại container. Đây là bài toán **revisions, traffic splitting và rollback**.

Cloud Run quản lý nhiều **revision bất biến** của cùng một service. Mỗi revision chứa một phiên bản image và cấu hình chạy, còn service có thể phân phối phần trăm request giữa các revisions. Cách này hỗ trợ **canary release**, **blue/green**, kiểm thử một revision với **traffic tag** và **rollback traffic** khi có sự cố.

Bài thuộc chương **Cloud Run** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối triển khai ứng dụng với IAM, VPC, Artifact Registry, GKE/Compute Engine, Cloud SQL, Cloud Storage, giám sát độ tin cậy và chi phí. Nội dung tập trung vào **Cloud Run services nhận HTTP requests**, không mặc định áp dụng các lệnh traffic split cho **Cloud Run jobs hoặc worker pools**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **service**, **revision**, **latest revision**, **serving revision**, **tag** và **image digest**.
2. Hiểu tại sao revision bất biến nhưng **phân phối traffic** vẫn thay đổi được.
3. Deploy revision mới ở **0% traffic**, gắn tag để smoke test trực tiếp.
4. Chia traffic có kiểm soát theo các mức 1% → 5% → 25% → 100%.
5. Rollback về revision ổn định bằng `gcloud` hoặc Console mà không build lại.
6. Phân biệt rollback **ứng dụng/traffic** với rollback database, schema, secrets và external side effects.
7. Đọc request count, tỷ lệ lỗi, độ trễ, logs theo revision và xác định tiêu chí dừng rollout.
8. Đánh giá tác động của tags, min instances, autoscaling và quyền IAM.
9. Viết runbook canary/rollback có bước kiểm tra và bài tập thực hành.

## 1. Mô hình service và revision

**Cloud Run service** là endpoint logic mà client gọi. Khi deploy image mới hoặc thay đổi **revision template configuration** (ví dụ environment variables, container image, CPU/memory hay runtime service account), Cloud Run tạo một **revision bất biến**.

~~~mermaid
flowchart TD
    CLIENT["Client / HTTP request"] --> URL["Cloud Run service URL<br/>orders-api"]
    URL --> T{"Traffic configuration"}
    T -->|"95%"| R1["Revision ổn định<br/>orders-api-00010-abc"]
    T -->|"5%"| R2["Revision canary<br/>orders-api-00011-def"]
    TAG["Tag URL: canary---..."] -->|"Truy cập trực tiếp"| R2
    R1 --> DB[("Cloud SQL / Storage / Pub/Sub")]
    R2 --> DB
~~~

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Service** | Tên và URL chung, cấu hình định tuyến request tới các revisions |
| **Revision** | Snapshot bất biến của image và revision-level settings lúc deploy |
| **Latest created revision** | Revision được tạo gần nhất, chưa chắc đã ready hoặc đang nhận traffic |
| **Latest ready revision** | Revision mới nhất đã sẵn sàng theo Cloud Run |
| **Serving revision** | Revision đang được service phân bổ traffic lớn hơn 0% |
| **Traffic split** | Cách định tuyến request tới nhiều revisions với tỷ lệ phần trăm |
| **Traffic tag** | Tên tạo URL riêng để gọi một revision cụ thể, kể cả khi 0% traffic |
| **Image digest** | Định danh image container theo nội dung; khác tag image có thể được gán lại |

Ví dụ service có hai revisions:

~~~text
orders-api-00010-abc   image .../orders-api@sha256:AAA...   traffic 100%
orders-api-00011-def   image .../orders-api@sha256:BBB...   traffic   0%
                                                     tag canary
~~~

Revision mới nhất có thể **không nhận request từ service URL**. Đây là trạng thái bình thường khi triển khai với `--no-traffic`.

### 1.1. Những thay đổi nào tạo revision?

| Thao tác | Có tạo revision mới không? |
| --- | --- |
| Deploy image mới | **Có** |
| Đổi environment variable/secrets reference ở revision template | **Có** |
| Đổi CPU/memory/timeout/concurrency thuộc revision template | **Có** |
| Chuyển traffic 90/10 thành 50/50 | **Không** |
| Gắn/xóa tag ở traffic configuration | **Không** |
| Đổi traffic về revision cũ | **Không** |
| Một số service-level settings (ví dụ min instances ở cấp service) | **Không nhất thiết**; phụ thuộc cấp cấu hình |
| Dữ liệu Cloud SQL hay object Cloud Storage thay đổi | **Không** |

**Revision bất biến không có nghĩa hệ thống xung quanh bất biến**: Cloud SQL schema, secrets được tham chiếu, IAM, external APIs, VPC và queue vẫn có thể đổi sau khi revision được tạo.

### 1.2. Revision không phải backup hoàn chỉnh

Cloud Run có thể giữ những revisions cũ để định tuyến/rollback. Nhưng Cloud Run giới hạn tối đa **1.000 revisions trên mỗi service**; khi vượt giới hạn, revisions cũ có thể bị tự xóa. Revision không chứa backup của Cloud SQL, Cloud Storage hay external state. Để phát hành có thể tái hiện, giữ **image digest trong Artifact Registry**, release manifest và kế hoạch phục hồi dữ liệu.

## 2. Traffic splitting hoạt động như thế nào?

Traffic split xác định **tỷ lệ request gửi tới mỗi revision** trên service URL. Ví dụ:

| Revision | Tỷ lệ | Khoảng request dự kiến nếu có 10.000 request |
| --- | ---: | ---: |
| Ổn định (A) | 95% | Khoảng 9.500 |
| Canary (B) | 5% | Khoảng 500 |
| Tổng | 100% | 10.000 |

Các con số trên là **kỳ vọng thống kê**, không phải cam kết đúng số request, user hoặc session. Với traffic ít, tỷ lệ quan sát có thể lệch; một khách hàng cũng có thể gửi nhiều request tới những revisions khác nhau.

**Những giới hạn cần nhớ:**

- Chia theo **requests**, không mặc định chia theo từng người dùng/tài khoản/đơn hàng.
- Nếu bật **session affinity**, phân phối thực tế có thể bị ảnh hưởng; phải xem hướng dẫn liên quan.
- Cập nhật traffic **không tức thời trên mọi kết nối**; các requests đã bắt đầu vẫn được xử lý và trong thời gian chuyển tiếp requests có thể tới revision cũ hoặc mới.
- Các revisions có thể cùng truy cập database và queue, nên phải tương thích **dữ liệu và schema** trong suốt giai đoạn cả A và B hoạt động.
- Cloud Run traffic split không phải một feature flag theo user; nếu cần kiểm thử theo nhóm người dùng, thực hiện bằng gateway/feature flags/logic ứng dụng phù hợp.

### 2.1. Canary và blue/green

**Canary:** phát hành B ở 1–5%, đo sức khỏe, tăng dần lên 25%, 50% rồi 100% khi đạt điều kiện.

**Blue/green:** giữ A (blue) ở 100%, deploy B (green) ở 0%, thử bằng tag URL, sau đó chuyển phần lớn hoặc toàn bộ traffic sang B. Dùng tag để smoke test **không tự chuyển traffic** của service URL.

~~~mermaid
flowchart LR
    A["A ổn định 100%"] --> B["Deploy B 0% + tag"]
    B --> C["Smoke test B trực tiếp"]
    C --> D{"Đạt gate?"}
    D -->|Có| E["B 5% / A 95%"]
    E --> F{"SLO và nghiệp vụ đạt?"}
    F -->|Có| G["Tăng 25% → 50% → 100%"]
    F -->|Không| R["Rollback A 100%"]
    D -->|Không| R
~~~

## 3. Chuẩn bị trước khi thao tác trên service

**Giả định trong lab:** project `PROJECT_ID`, region `asia-southeast1`, service `orders-api` đã tồn tại, chỉ người được cấp phép mới được deploy; có hai image đã kiểm thử tại Artifact Registry.

~~~text
SERVICE = orders-api
REGION  = asia-southeast1
OLD_REV = orders-api-00010-abc      # ví dụ, thay tên thật
NEW_REV = orders-api-00011-def      # ví dụ, lấy sau deploy
IMAGE_B = asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST_B
~~~

**Đây là lệnh có thể thay traffic production và phát sinh chi phí.** Chỉ chạy trong project lab hoặc cửa sổ thay đổi đã duyệt; không sử dụng tên revision minh họa như một revision tồn tại thực.

### 3.1. IAM, Artifact Registry và danh tính

Người deploy/cập nhật traffic cần quyền Cloud Run phù hợp, thường là `roles/run.developer`; khi deploy với service account còn cần quyền `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs`). Với image từ Artifact Registry, các identity đọc image phải có quyền cần thiết, đặc biệt trong cấu hình cross-project.

**Đừng cấp Owner/Editor chỉ để chạy traffic update.** Kiểm tra đúng tài khoản, project, region và service trước khi thao tác:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud run services list \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

### 3.2. Ghi nhận trạng thái hiện hành

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(status.traffic,status.latestReadyRevisionName,status.latestCreatedRevisionName)"

gcloud run revisions list \
  --service=orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Xác minh **revision A đang phục vụ**, tên revision thật, image digest, traffic split, service URL, IAM/ingress, trạng thái health và rollback target. Lưu cấu hình ngoài production theo quy trình GitOps/change record; tránh đưa token/secrets vào log báo cáo.

### 3.3. Chọn revision quay về trước khi triển khai

Không mặc định **revision trước đó** luôn là bản tốt. Hãy chọn revision từng qua smoke tests, có image digest xác minh, schema còn tương thích, secret/permissions còn hoạt động. Ghi tên revision đó trong runbook.

## 4. Deploy revision B ở 0% và gắn traffic tag

Cloud Run hỗ trợ deploy revision mới **không nhận traffic từ service URL**; gắn tag `canary` để tester gọi trực tiếp B.

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST_B \
  --no-traffic \
  --tag=canary \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

**Lưu ý triển khai:**

- Service `orders-api` phải tồn tại và đang có revision A ổn định; `--no-traffic` giúp tránh đưa B ngay tới người dùng thông qua service URL.
- `FULL_DIGEST_B` phải thay bằng sha256 digest thật; `--image` chấp nhận tham chiếu theo digest.
- Tag phải hợp lệ; URL gắn tag được Cloud Run cấp. **Không tự đoán URL chỉ từ service name** vì có dạng URL khác nhau.
- Nếu thay cấu hình runtime identity, networking, secrets hoặc resource limits cùng lúc, phải đánh giá tác động tương ứng; đừng gộp quá nhiều thay đổi không liên quan trong một canary.
- Nếu deploy từ source thay vì image, `gcloud run deploy orders-api --source=. --no-traffic --tag=canary` sẽ kích hoạt **build mới**; không phải promotion của cùng image đã kiểm thử.

Sau deploy:

~~~bash
gcloud run revisions list \
  --service=orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(status.traffic)"
~~~

Lấy **NEW_REV chính xác** từ danh sách/traffic config. `latestReadyRevisionName` cho biết revision ready mới nhất, nhưng khi có nhiều pipeline deploy đồng thời, không nên dùng `LATEST` mù quáng.

## 5. Kiểm thử revision B qua tag URL

Tag `canary` tạo một URL riêng cho revision B, ngay cả khi B nhận **0% service traffic**. Ví dụ URL *minh họa*:

~~~text
https://canary---orders-api-123456789012.asia-southeast1.run.app
~~~

Lấy URL thật từ Cloud Run Console hoặc `status.traffic[].url` của service, không tự ghép bằng cách đoán hostname. URL tag không làm service tự trở thành **public**: IAM/ingress của Cloud Run service vẫn áp dụng.

### 5.1. Smoke tests nên bao gồm

- `GET /health` hoặc `/actuator/health` (nếu ứng dụng có endpoint tương ứng).
- HTTP request mẫu **không gây side effect**, kiểm tra JSON schema/content type.
- Kết nối Cloud SQL, Cloud Storage, Pub/Sub, Secret Manager theo quyền runtime thật.
- Một luồng tạo đơn **trong môi trường thử** hoặc với dữ liệu test đã cô lập.
- Logs cho thấy revision B nhận request, không nhầm request trả về từ A.

Với **private Cloud Run service**, caller cần `roles/run.invoker` hoặc permission tương đương. Khi client dùng ID token, **`aud` phải là URL của service gốc** (hoặc custom audience đã cấu hình), **kể cả khi request gửi tới URL gắn tag**.

~~~bash
# SERVICE_URL là URL chính thức của service, KHÔNG phải tag URL.
# TAG_URL lấy từ Cloud Run service traffic status.
gcloud auth print-identity-token --audiences=SERVICE_URL
# Client có quyền Invoker dùng token hợp lệ làm:
# Authorization: Bearer ID_TOKEN
# GET TAG_URL/health
~~~

Không in token thật vào tài liệu, log CI hoặc artifact của pipeline. Khi thử từ developer account, `gcloud auth print-identity-token --audiences` có điều kiện hỗ trợ theo loại credentials; dùng service account impersonation hoặc client library với ADC khi phù hợp. Không cố sửa IAM thành `allUsers` để “test cho tiện”.

### 5.2. Tag URL không đại diện tỷ lệ traffic

Test B qua tag vẫn chạy trên B nhưng **không làm tăng phần trăm traffic từ service URL**. Ngược lại, khi đã bắt đầu canary 5%, người dùng qua service URL có thể nhận B mà không sử dụng tag URL.

## 6. Chia traffic theo revision name

Sau khi smoke test B đạt, chuyển traffic từ A sang B từng bước. **Các lệnh dưới thay đổi routing thực tế.** Chỉ chạy khi revision A/B đã được kiểm tra đúng và change window được phê duyệt.

### 6.1. 95% A / 5% B

~~~bash
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=95,orders-api-00011-def=5 \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Ví dụ minh họa này giả định các revision names đúng như mục 3. Trong môi trường thật, **thay cả hai bằng tên revision thực tế**. Cặp phần trăm phải cộng thành **100%**.

### 6.2. Tăng 25%, 50% rồi 100%

~~~bash
# Khi 5% đạt tiêu chí SLO:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=75,orders-api-00011-def=25 \
  --region=asia-southeast1 --project=PROJECT_ID

# Sau khi 25% đạt tiêu chí:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=50,orders-api-00011-def=50 \
  --region=asia-southeast1 --project=PROJECT_ID

# Khi đã duyệt phát hành hoàn toàn:
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00011-def=100 \
  --region=asia-southeast1 --project=PROJECT_ID
~~~

**Sau mỗi lần điều chỉnh**, xác minh traffic assignment và theo dõi đủ thời gian/số request. Không tăng tự động chỉ vì lệnh CLI trả 0; câu hỏi quyết định là **B có đáp ứng health/SLO và logic nghiệp vụ không?**

### 6.3. Lệnh `--to-latest` không giống pin một revision

~~~bash
gcloud run services update-traffic orders-api \
  --to-latest \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

`--to-latest` chuyển 100% traffic về **latest revision** và duy trì kiểu định tuyến tới **latest/future revisions**. Vì vậy một deploy mới sau đó có thể tự nhận traffic. Khi CI/CD có nhiều pipeline, đây có thể là tác động **ngoài ý muốn**.

Đối với rollout kiểm soát nghiêm ngặt, nên chỉ định **revision name cụ thể** trong `--to-revisions` thay vì dựa vào `LATEST`. Traffic split về revisions cũ có thể được duy trì trên những deployment về sau; phải kiểm tra policy hiện tại trước mỗi đợt.

## 7. Rollback: chuyển 100% traffic về revision A

Nếu canary B tăng error rate hoặc vi phạm nghiệp vụ, dừng việc nâng tỷ lệ B và rollback:

~~~bash
gcloud run services update-traffic orders-api \
  --to-revisions=orders-api-00010-abc=100 \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Kiểm chứng:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID \
  --format="yaml(status.traffic)"

gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Trong Console: **Cloud Run → Services → orders-api → Revision history → Manage traffic → Send all traffic to one revision**, chọn A và lưu.

**Những điều rollback traffic làm và không làm:**

| Rollback về A | Kết quả |
| --- | --- |
| Định tuyến request mới qua service URL | Chuyển mục tiêu về A; cập nhật định tuyến cần thời gian lan truyền |
| Requests đã bắt đầu xử lý | Có thể tiếp tục trên B cho tới khi hoàn tất |
| Image/config revision B | B vẫn tồn tại, có thể còn tag |
| Revision mới | **Không tạo** chỉ từ thay đổi traffic |
| Database schema/data | **Không tự khôi phục** |
| Messages đã publish, emails, thanh toán | **Không hoàn tác** |
| External IAM/secrets/Cloud SQL state | **Không tự đổi** |
| Health check trước khi gửi traffic về A | Cloud Run **không chạy lại deployment health checks hoặc kiểm tra phụ thuộc** trước chuyển routing |

Không báo rollback “hoàn toàn thành công” chỉ vì service hiện ghi `100% A`. Phải quan sát request thực, latency, error rate, connections tới database và dữ liệu nghiệp vụ sau chuyển.

### 7.1. Khi A không còn tương thích database

Giả sử B đã migrate cột `status` từ enum cũ sang schema mới, A chỉ đọc schema cũ. Rollback traffic về A có thể làm lỗi tăng **thay vì giảm**.

Vì thế cần **expand–migrate–contract**:

1. Triển khai schema mới **tương thích A lẫn B** (expand).
2. Triển khai B và quan sát canary.
3. Migrate data theo job có kiểm soát, có backup/PITR khi áp dụng.
4. Chỉ xóa schema cũ (contract) **sau khi không còn cần rollback về A**.

Nếu thay đổi dữ liệu không thể đảo ngược, kế hoạch rollback phải bao gồm runbook cho database, queue và các side effects, không chỉ `update-traffic`.

## 8. Quan sát canary theo từng revision

Không đo riêng toàn service vì A chiếm 95% traffic có thể **che khuất lỗi của B**. Tách số liệu theo `revision_name`.

| Nhóm tín hiệu | Nên theo dõi |
| --- | --- |
| **Traffic** | Số request và tỉ lệ B thực nhận |
| **Availability** | 5xx rate, lỗi startup, timeout, số request không hoàn tất |
| **Latency** | p50, p95, p99 theo revision và endpoint |
| **Runtime** | CPU/memory, instance count, concurrency, cold starts khi thấy trong logs/metrics |
| **Dependencies** | Cloud SQL connections, Pub/Sub backlog, Cloud Storage errors |
| **Business** | Đơn hàng thành công, duplicate payment, invalid state transitions |
| **Costs** | CPU/memory billing, min instances, logs, egress |
| **Deploy safety** | Image digest, revision readiness, secret access, IAM và network changes |

Cloud Monitoring hỗ trợ **Cloud Run metrics** như request count, request latencies, instance count. Hãy chọn metric theo service và lọc/group bằng **revision**, status class, region khi có.

### 8.1. Logs Explorer filter

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
resource.labels.revision_name="orders-api-00011-def"
severity>=ERROR
~~~

Filter trên giúp tìm lỗi B. Có thể thêm `httpRequest.status>=500` hoặc trace/request ID theo dữ liệu logs thực tế. Đừng kết luận “B không có lỗi” khi chỉ có 3 requests.

### 8.2. Ví dụ quyết định canary

Giả sử trong 20 phút:

| Chỉ số | A ổn định | B canary 5% | Ngưỡng cho phép giả định |
| --- | ---: | ---: | --- |
| Request count | 19.000 | 1.000 | B đủ mẫu để xem xu hướng |
| HTTP 5xx rate | 0,2% | 2,0% | Không quá 0,5% |
| p95 latency | 180 ms | 420 ms | Không quá 300 ms |
| Tỷ lệ tạo đơn thành công | 99,8% | 98,7% | Không thấp hơn 99,5% |

**Quyết định:** rollback B vì vượt ngưỡng lỗi và độ trễ; không tăng traffic. Các số trên **hoàn toàn giả định**, chỉ minh họa cách đặt gate. Với B chỉ có 1–10 requests, cần chờ đủ dữ liệu hoặc dùng kiểm thử chủ động, không lấy tỷ lệ phần trăm làm kết luận chắc chắn.

### 8.3. Điều chỉnh không tức thời

Cloud Run nêu rõ cập nhật routing **không tức thời** và không hủy requests đang thực thi. Vì vậy sau lệnh rollback, B có thể còn xuất hiện trong logs hoặc metric thêm một khoảng thời gian. Đánh giá **thời gian của request**, trạng thái kết nối đang mở, traffic đã đi qua tag URL và độ trễ metrics trước khi kết luận rollback thất bại.

## 9. Tags, min instances và chi phí

Một revision không nhận requests thường **không tiêu tốn tài nguyên chạy và không bị tính phí compute** nếu không có cấu hình min instances hay request từ tag. Tuy nhiên:

- Với **service-level minimum instances**, Cloud Run phân bổ số instance tối thiểu cho **những revisions trong traffic split** theo tỷ lệ. Tagged revision 0% không tự nhận phần min instances cấp service.
- Với **revision-level minimum instances**, revision được tag có thể duy trì min instances **dù 0% traffic**, phát sinh chi phí.
- Request kiểm thử qua tag URL vẫn chạy container và có thể tạo chi phí request/compute/logs.
- Nếu bật **instance-based billing** hoặc cấu hình scaling đặc biệt, phí idle/runtime khác request-based billing.
- Tag tồn tại lâu sau test có thể tạo đường truy cập riêng tới revision cũ; phải quản trị IAM/ingress và xóa tag khi không cần.

Xóa tag `canary` khi hoàn tất kiểm thử:

~~~bash
gcloud run services update-traffic orders-api \
  --remove-tags=canary \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

Lệnh này **xóa tag**, không tự chuyển traffic. Trước khi xóa, kiểm tra không có hệ thống giám sát hay tester được phép nào còn cần URL đó.

**Tối ưu cost không phải giảm tỷ lệ canary bằng mọi giá.** Với revision B Java có cold start lớn, sample 1% có thể thiếu dữ liệu hoặc chịu ảnh hưởng cold start; có thể cần pre-warming/min instances theo nhu cầu đã duyệt và phép đo chi phí rõ ràng.

## 10. Quy trình phát hành an toàn với CI/CD

Một pipeline canary production nên được điều phối bởi **một nguồn thay đổi traffic** (GitOps/IaC/Cloud Deploy hoặc pipeline đã duyệt), tránh hai pipeline cạnh tranh thay đổi service.

~~~mermaid
flowchart TD
    SOURCE["Git commit + tests"] --> IMAGE["Build/push Artifact Registry<br/>ghi image digest"]
    IMAGE --> DEPLOY["Deploy B --no-traffic --tag=canary"]
    DEPLOY --> SMOKE["Smoke test tag URL, auth và dependencies"]
    SMOKE --> GATE{"Đạt test?"}
    GATE -->|Không| CLEAN["Dừng phát hành, giữ A 100%"]
    GATE -->|Có| STEP["Canary B 5%"]
    STEP --> OBS{"SLO + business gate đạt?"}
    OBS -->|Có| RAMP["Tăng 25% → 50% → 100%"]
    OBS -->|Không| ROLLBACK["Rollback A 100%"]
    RAMP --> FINAL["Xác minh, lưu release record"]
~~~

**Những kiểm soát bắt buộc:**

1. **Build once, deploy digest:** ghi Git SHA, image digest, config version và release ID.
2. **Thử trên staging trước:** integration/load/security tests trước khi deploy production ở 0%.
3. **Phân quyền rõ:** build identity push registry, deployer chỉnh service/traffic, runtime identity chỉ truy cập APIs cần thiết.
4. **Database backward compatibility:** A/B cùng dùng external resources; tránh schema đổi một chiều trong canary.
5. **Bounded progression:** mỗi traffic step cần số request đủ đánh giá và thời gian quan sát phù hợp.
6. **Automated stop/rollback có giới hạn:** alert/gate dựa trên SLO và nghiệp vụ, không để pipeline lặp rollback liên tục.
7. **Release audit:** lưu old/new revision names, traffic percentages, timestamps, người duyệt và bằng chứng smoke tests.
8. **Rollback drill:** diễn tập chuyển traffic về A trong môi trường thử, bao gồm xử lý side effects.

### 10.1. Nếu quản lý bằng Terraform hoặc YAML

Cloud Run `spec.traffic` có thể biểu diễn revisions và tỷ lệ:

~~~yaml
# Đoạn rút gọn từ Cloud Run Service (Knative API)
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  traffic:
    - revisionName: orders-api-00010-abc
      percent: 95
    - revisionName: orders-api-00011-def
      percent: 5
      tag: canary
~~~

Đây là **ví dụ tập trung vào traffic**, không phải manifest service đầy đủ để tạo mới độc lập. Nếu dùng `gcloud run services replace`, xuất và kiểm tra **toàn bộ service YAML** hiện hành trước khi thay; thay nhầm template hoặc IAM-related configuration có thể tạo revision ngoài ý muốn.

Với Terraform `google_cloud_run_v2_service`, traffic blocks có `type`/`revision` hoặc `tag` theo provider schema. **Đừng đồng thời thay traffic bằng CLI và Terraform** nếu pipeline sẽ tự `apply` cấu hình cũ trở lại; chọn một nguồn trạng thái được quản trị.

## 11. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Deploy B xong service URL vẫn trả A | Deploy với `--no-traffic` | Đúng thiết kế; dùng tag URL hoặc update-traffic khi được duyệt |
| Tag URL trả `403` | Private service, caller thiếu Invoker/ID token hoặc token audience sai | Kiểm tra IAM và dùng **service URL làm audience**, không phải tag URL |
| Tag URL trả `404` | URL suy đoán sai, tag chưa gắn hoặc tag bị xóa | Lấy URL thực từ service traffic status |
| B nhận ít hơn kỳ vọng ở mức 1% | Ít requests, session affinity, thời gian propagation | Đo đủ mẫu và kiểm tra routing |
| Gọi `--to-latest` rồi deploy lần sau đi thẳng production | Routing trỏ `LATEST` | Dùng pin revision explicit và kiểm tra traffic policy |
| Chuyển traffic nhưng không thấy revision mới | Chỉ thay traffic, không deploy image/config | Kiểm tra revision list; đây là hành vi bình thường |
| B trả 5xx, A bình thường | App config, secret, dependency/schema, cold start | So sánh logs/metrics per revision |
| Rollback A xong vẫn có B trong logs | In-flight requests, tag URL hoặc propagation | Kiểm tra request timestamp, tag traffic và trạng thái update |
| Rollback A gây lỗi database | Migration của B không tương thích A | Thiết kế expand–contract và DB rollback runbook |
| Canary làm Cloud SQL vượt connection limit | A và B cùng scale độc lập | Giới hạn instances/concurrency, connection pool, quota DB |
| Tagged revision 0% vẫn tốn phí | Revision-level min instances hoặc request test | Kiểm tra scaling config/billing và gỡ tag khi xong |
| `update-traffic` bị `403`/`404` | Sai project/region/IAM/service hoặc revision name | Kiểm tra context, role, list revisions |
| Traffic bị pipeline khác sửa lại | IaC/Cloud Deploy/CI đua với thao tác tay | Xác định nguồn điều phối và khóa rollout |

## 12. Tình huống tổng hợp: canary Orders API

**Bối cảnh:** `orders-api` Java 21 trên Cloud Run dùng Cloud SQL PostgreSQL, Pub/Sub và Cloud Storage. Revision A đang xử lý 100% traffic. Revision B thêm một thuật toán khuyến mãi và ghi một trường metadata bổ sung.

**Yêu cầu:** không ngừng dịch vụ, giới hạn rủi ro lỗi của B và rollback nhanh.

| Giai đoạn | Traffic | Điều kiện đi tiếp |
| --- | --- | --- |
| Chuẩn bị | A 100%, B chưa tồn tại | Tests/scan, image digest, DB schema tương thích |
| Deploy | A 100%, B 0% + tag | Smoke test/tag URL được xác thực |
| Canary 1 | A 99%, B 1% | Không có lỗi nghiêm trọng, đủ mẫu request |
| Canary 2 | A 95%, B 5% | 5xx, p95, business conversion đạt |
| Canary 3 | A 75%, B 25% | Cloud SQL/pool/queue ổn định |
| Hoàn tất | B 100% | SLO đạt trong thời gian theo dõi |
| Nếu lỗi | A 100% | Xác nhận rollback và dữ liệu nghiệp vụ |

**Điểm thiết kế quan trọng:** hai revisions dùng **cùng Cloud SQL database**, nên việc tạo schema mới phải tương thích A; không để B ghi dữ liệu khiến A không thể đọc. Cùng lúc, traffic 5% không có nghĩa Cloud SQL dùng đúng 5% connection pool: số instances và connection behavior còn tùy cold start/concurrency.

Sau đợt phát hành, lưu lại: digest A/B, các traffic steps, logs/metrics, kết quả SLO, thời điểm bắt đầu/kết thúc và người duyệt. Gỡ tag canary khi không cần; không xóa ngay bản A nếu còn trong kế hoạch rollback.

## 13. Bài tập tự kiểm tra

**Câu 1.** Deploy revision B với `--no-traffic`, service URL vẫn trả A. Có phải deploy lỗi không?

*Đáp án gợi ý:* Không; B được tạo nhưng phân bổ 0%, có thể thử qua tag URL.

**Câu 2.** Đổi tỷ lệ A/B từ 90/10 thành 50/50 có tạo revision mới?

*Đáp án:* Không, đó là thay đổi traffic configuration của service.

**Câu 3.** Tỷ lệ canary 5% có bảo đảm chính xác 5% người dùng được B phục vụ không?

*Đáp án:* Không. Phân phối theo request và có biến động thống kê/session affinity.

**Câu 4.** Revision mới nhất luôn là revision đang phục vụ 100% traffic?

*Đáp án:* Không. Có thể là revision mới deploy 0% hoặc chưa ready.

**Câu 5.** Để test B khi B 0%, nên dùng service URL hay tag URL?

*Đáp án:* Tag URL trỏ trực tiếp B, không cần đổi service traffic.

**Câu 6.** Với Cloud Run private service, JWT audience khi gọi tag URL nên là URL nào?

*Đáp án:* URL của **service gốc** (hoặc custom audience được khai báo), không phải tag URL.

**Câu 7.** Lệnh rollback `--to-revisions=A=100` có hủy ngay các request đang xử lý trên B không?

*Đáp án:* Không. In-flight requests có thể tiếp tục; thay đổi routing cần thời gian lan truyền.

**Câu 8.** Cloud Run có chạy lại deployment health check của A trước khi chuyển traffic rollback không?

*Đáp án:* Không. Phải tự kiểm chứng external dependencies và hành vi ứng dụng.

**Câu 9.** Nếu B đã chạy migration xóa cột mà A cần, traffic rollback có chắc an toàn không?

*Đáp án:* Không. Cần schema backward compatibility, expand–contract và runbook dữ liệu.

**Câu 10.** Tagged revision 0% có luôn miễn phí compute không?

*Đáp án:* Không. Revision-level min instances hoặc requests qua tag có thể phát sinh phí.

**Câu 11.** Tại sao cần so 5xx rate của B thay vì chỉ tổng 5xx của service?

*Đáp án:* Phần traffic lớn ở A có thể che tỷ lệ lỗi cao của B.

**Câu 12.** Vì sao production rollout nên pin revision name hoặc image digest thay vì dùng `LATEST`/`:latest` tùy tiện?

*Đáp án:* `LATEST` có thể trỏ tới revision triển khai sau; image tag có thể thay đổi. Pin giúp tái hiện đúng artifact và routing đã kiểm duyệt.

## 14. Checklist trước production

- [ ] Xác minh project, region, service, người phụ trách và quyền deploy/traffic.
- [ ] Lưu old revision name, image digest, runtime config và target rollback.
- [ ] Có CI tests, image scan, smoke tests, database migration tương thích A/B.
- [ ] Deploy B ở **0% + tag**, không tự chuyển traffic ngay.
- [ ] Test tag URL với IAM/ingress hợp lệ; token audience dùng service URL.
- [ ] Mỗi bước traffic có tỷ lệ rõ ràng và tổng phân bổ bằng 100%.
- [ ] Có SLO thresholds, đủ request sample, đo theo **revision** và business metrics.
- [ ] Kiểm tra Cloud SQL connections, Pub/Sub, Cloud Storage, secrets và VPC egress.
- [ ] Có lệnh rollback A 100% và quy trình xác nhận rollback.
- [ ] Biết rollback traffic không hoàn tác database, messages hay side effects.
- [ ] Không dùng `--to-latest` nếu không muốn future deployments tự nhận traffic.
- [ ] Kiểm tra min instances ở cấp service/revision, tags tồn tại và chi phí.
- [ ] CI/CD, GitOps hoặc Terraform có một nguồn điều phối traffic duy nhất.
- [ ] Giữ digest/revision A đủ thời gian rollback; gỡ canary tag khi không cần.
- [ ] Lưu release record và kiểm thử rollback định kỳ.

## 15. Kết luận

**Cloud Run revision là bản phát hành bất biến; traffic configuration là công tắc điều phối.** Nhờ deploy `--no-traffic`, gắn tag, chia request theo tỷ lệ rồi rollback `--to-revisions=OLD_REV=100`, nhóm có thể phát hành Java service từng bước mà không cần build lại khi muốn quay về bản ổn định. Tuy nhiên rollback chỉ điều chỉnh **request routing**: dữ liệu, sự kiện và hệ thống phụ thuộc cần tương thích để rollback thực sự an toàn.

## Tài liệu tham khảo chính thức

- [Manage Cloud Run revisions](https://cloud.google.com/run/docs/managing/revisions)
- [Rollbacks, gradual rollouts and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [gcloud run services update-traffic](https://cloud.google.com/sdk/gcloud/reference/run/services/update-traffic)
- [gcloud run deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy)
- [Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Configure minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [Monitor Cloud Run services](https://cloud.google.com/run/docs/monitoring)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

