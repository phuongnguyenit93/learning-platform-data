# Gọi Google Cloud REST API và khám phá API

Khi thao tác trên Google Cloud, người học thường bắt đầu với Google Cloud Console hoặc lệnh `gcloud`. Tuy nhiên, phía sau nhiều thao tác đó là các API có thể được gọi từ chương trình, pipeline CI/CD hoặc công cụ tự động hóa. Biết đọc tài liệu REST API và thực hiện một lời gọi có xác thực giúp bạn hiểu chính xác **đang tác động tới tài nguyên nào, bằng quyền gì, theo phương thức HTTP nào và kết quả có thể kiểm chứng ra sao**.

Bài học thuộc chương **Công cụ và môi trường GCP** của module `CLOUD_PROVIDERS_GCP`. Kỹ năng gọi API phục vụ toàn bộ hành trình học Google Cloud: khám phá project và IAM, kiểm tra VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu, sau đó tự động hóa phát hành, quan sát độ tin cậy và quản lý chi phí. Ví dụ thực hành chính là **liệt kê Cloud Run services qua REST API bằng một yêu cầu HTTP chỉ đọc**.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt Google Cloud management API với endpoint HTTP của chính ứng dụng đang chạy trên GCP.
2. Tìm đúng service, phiên bản API, phương thức REST, tài nguyên cha, các tham số, quyền và kiểu phản hồi.
3. Gọi một API an toàn bằng OAuth 2.0 access token với `curl` hoặc PowerShell; không đưa token vào mã nguồn.
4. Đọc JSON response, xử lý phân trang và nhận diện các lỗi `400`, `401`, `403`, `404`, `429`, `5xx`.
5. Biết khi nào nên dùng REST trực tiếp, `gcloud`, client library hay Infrastructure as Code; lập kế hoạch an toàn trước khi gọi API ghi tài nguyên.

## 2. REST API nằm ở đâu trong Google Cloud?

Hãy hình dung Google Cloud gồm hai lớp HTTP khác nhau:

| Lớp | Ví dụ | Mục đích và cách xác thực |
| --- | --- | --- |
| **Google Cloud API (control plane)** | `run.googleapis.com`, `compute.googleapis.com`, `cloudresourcemanager.googleapis.com` | Liệt kê, tạo, cấu hình hoặc xóa tài nguyên cloud; thường xác thực bằng OAuth 2.0 access token và kiểm soát bằng IAM. |
| **API của ứng dụng (data/application plane)** | `https://my-service-...run.app/orders` | Xử lý nghiệp vụ do bạn viết. Cách xác thực do ứng dụng và cấu hình truy cập quyết định; Cloud Run service riêng tư thường yêu cầu **OIDC ID token** phù hợp với audience. |

**Đừng nhầm access token với ID token.** Google Cloud management REST API thường nhận `Authorization: Bearer ACCESS_TOKEN`. Khi gọi endpoint của một Cloud Run service yêu cầu xác thực, cơ chế thường dùng là `Authorization: Bearer ID_TOKEN` với audience phù hợp. Hai loại token phục vụ hai mục đích khác nhau; không hoán đổi theo thói quen.

Google Cloud API có thể được cung cấp qua REST/JSON, gRPC hoặc cả hai. Tài liệu REST mô tả cách ánh xạ thao tác tài nguyên sang đường dẫn, HTTP method và JSON. Dù đang dùng SDK hay `gcloud`, khả năng đọc tài liệu REST vẫn hữu ích để hiểu các trường và lỗi ở mức thấp.

## 3. Giải phẫu một lời gọi REST

Xét yêu cầu lấy danh sách Cloud Run services trong một project và region:

```http
GET https://run.googleapis.com/v2/projects/PROJECT_ID/locations/REGION/services?pageSize=20
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
```

| Thành phần | Ý nghĩa | Điều phải xác minh |
| --- | --- | --- |
| `GET` | Đọc danh sách, không yêu cầu thay đổi tài nguyên | Tài liệu method có đúng `list` và dùng `GET` không? |
| `https://run.googleapis.com` | Host API quản lý Cloud Run | Đúng API sản phẩm cần thao tác chưa? |
| `/v2` | Phiên bản REST API | Đúng phiên bản tài liệu và cấu trúc JSON chưa? |
| `projects/PROJECT_ID` | Phạm vi project | Đã dùng project ID thực sự của môi trường được cấp quyền chưa? |
| `locations/REGION` | Phạm vi region | Service tồn tại ở region nào? API có chấp nhận địa điểm đó không? |
| `services` | Bộ sưu tập tài nguyên | Cần `list` hay `get` một tên cụ thể? |
| `pageSize=20` | Tham số truy vấn | Phương thức có hỗ trợ `pageSize` và `pageToken` không? |
| `Authorization` | Danh tính của người/workload gọi | Token còn hạn và principal có quyền IAM cần thiết không? |

Trong API mô hình tài nguyên, tên resource thường có dạng phân cấp:

```text
projects/PROJECT_ID/locations/REGION/services/SERVICE_NAME
```

Điều đó khác với URL ứng dụng mà người dùng cuối truy cập. Tên resource dùng cho các API quản trị, còn URL ứng dụng dùng để gửi traffic nghiệp vụ.

Phương thức HTTP thường gặp:

| Method | Tác dụng phổ biến | Cẩn trọng |
| --- | --- | --- |
| `GET` | Đọc một tài nguyên hoặc danh sách | Có thể trả nhiều trang; yêu cầu IAM và quota vẫn áp dụng. |
| `POST` | Tạo tài nguyên hoặc gọi một thao tác | Không tự động giả định có thể retry an toàn. |
| `PATCH` | Chỉnh sửa một phần tài nguyên | Một số API yêu cầu `updateMask`, version/etag hoặc thao tác bất đồng bộ. |
| `PUT` | Thay thế/cập nhật tài nguyên ở API có hỗ trợ | Kiểm tra semantics cụ thể, tránh làm mất trường không gửi kèm. |
| `DELETE` | Xóa tài nguyên | Kiểm tra phụ thuộc, retention, điều kiện xóa và phương án khôi phục. |

Không phải API nào cũng cung cấp đủ mọi method, cùng tên tham số hoặc cùng cơ chế ghi. **Tài liệu của method cụ thể là nguồn quyết định**, không phải suy đoán từ các API khác.

## 4. Quy trình khám phá một Google Cloud API

Một cách khám phá hiệu quả là đi từ **nhu cầu → tên dịch vụ → loại tài nguyên → method → yêu cầu xác thực → phép thử**.

### Bước 1: Viết hành động cần thực hiện dưới dạng câu rõ ràng

Ví dụ: “Liệt kê các Cloud Run services trong project `demo-learning`, region `asia-southeast1` mà tài khoản này được phép nhìn thấy.” Câu này xác định rõ đối tượng, phạm vi và thao tác chỉ đọc. Cụm “xem các dịch vụ” chung chung chưa đủ để tìm endpoint chính xác.

### Bước 2: Tìm phương thức trong REST reference

Với ví dụ trên, xem tài liệu chính thức:

- [Cloud Run Admin API v2 — projects.locations.services.list](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/list)
- [Cloud Run Admin API v2 — projects.locations.services.get](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/get)
- [Tổng quan Google Cloud APIs](https://cloud.google.com/apis/docs/overview)

Đối với mỗi method, đọc tối thiểu sáu mục: **HTTP request**, path parameters, query parameters, request body, response body, OAuth scopes/IAM permissions. Nếu method tạo/cập nhật/xóa resource, đọc thêm các điều kiện về long-running operations, concurrency/etag và quota.

Một số dịch vụ có nhiều phiên bản như `v1`, `v2` hoặc nhiều giao diện quản lý. Không ghép đường dẫn lấy từ `v2` với schema JSON được mô tả trong tài liệu `v1`.

### Bước 3: Khám phá trực quan bằng APIs Explorer

Nhiều trang REST reference của Google hiển thị khu vực **Try this method / APIs Explorer**. Công cụ này giúp điền tham số, xem request và response, thử OAuth bằng tài khoản được phép. Khi thực hành:

1. Chọn method `GET/list` trước.
2. Điền đúng project và location của môi trường thử nghiệm.
3. Đọc scopes và quyền mà công cụ yêu cầu.
4. Kiểm tra HTTP status và JSON response; chỉ chuyển sang method ghi khi đã hiểu tác dụng.

Không dán access token, private key, dữ liệu khách hàng hoặc mật khẩu vào tài liệu, ảnh chụp màn hình hoặc phần chia sẻ công khai. APIs Explorer giúp học cú pháp; nó không thay thế quy trình kiểm soát thay đổi trong production.

### Bước 4: Khám phá theo máy bằng Discovery document (khi API hỗ trợ)

Google APIs Discovery Service cung cấp metadata mô tả các API được xuất bản, gồm tên, phiên bản và URL discovery document. Bạn có thể tra cứu danh mục công khai rồi tìm phần tử `run`:

```bash
curl --silent --show-error \
  "https://discovery.googleapis.com/discovery/v1/apis" \
  | jq '.items[] | select(.name == "run") | {name, version, discoveryRestUrl}'
```

Nếu một phiên bản có `discoveryRestUrl`, mở URL đó để khảo sát các resource/method, tham số và schema (cấu trúc thực tế phụ thuộc từng API). Với những API không có bản Discovery phù hợp, đọc REST reference hoặc tài liệu OpenAPI chính thức của dịch vụ. **Đừng mặc định Discovery liệt kê đầy đủ mọi giao diện gRPC hay mọi tính năng mới của mọi sản phẩm.**

### Bước 5: Đối chiếu với `gcloud` hoặc client libraries

Lệnh CLI giúp kiểm chứng kết quả người dùng nhìn thấy:

```bash
gcloud run services list \
  --project="demo-learning" \
  --region="asia-southeast1"
```

Kết quả qua CLI và REST có thể khác định dạng hiển thị, cách phân trang hoặc trường mặc định; so sánh theo **tên và trạng thái tài nguyên**, không kỳ vọng hai output luôn có cùng cấu trúc.

## 5. Chuẩn bị môi trường và quyền truy cập

Thực hành yêu cầu:

- Đã cài **Google Cloud CLI** (để lấy token) và một HTTP client như `curl` hoặc PowerShell `Invoke-RestMethod`. `jq` là tiện ích tùy chọn để đọc JSON.
- Có **project ID** và **region** được phép kiểm tra. Các ví dụ dùng `demo-learning` và `asia-southeast1` để minh họa; thay bằng giá trị của môi trường riêng.
- Dịch vụ **Cloud Run API** (`run.googleapis.com`) đã được bật cho project theo chính sách tổ chức.
- Principal gọi API được cấp quyền phù hợp; với thao tác liệt kê Cloud Run services, cần quyền IAM `run.services.list` trên phạm vi phù hợp. Một role thông dụng cần cân nhắc là `roles/run.viewer`; áp dụng nguyên tắc least privilege thay vì dùng Owner/Editor.

Kiểm tra project gcloud đang chọn và trạng thái bật API:

```bash
gcloud config get-value project

gcloud services list --enabled \
  --project="demo-learning" \
  --filter="name:run.googleapis.com"
```

`gcloud config get-value project` chỉ cho biết **cấu hình CLI hiện tại**; nó không tự quyết định project của một REST URL mà bạn tự viết. Nếu API chưa bật hoặc tài khoản thiếu quyền, đề nghị người quản trị xử lý theo môi trường được cấp phép. Lệnh bật API, cấp IAM và tạo tài nguyên đều là thao tác thay đổi cấu hình, không phải bước kiểm tra chỉ đọc.

## 6. Xác thực: OAuth 2.0, ADC, service account và IAM

### 6.1. Tài khoản dùng cho thao tác thủ công

Khi học trên máy cá nhân, đăng nhập CLI bằng tài khoản Google được phép:

```bash
gcloud auth login
gcloud auth list
```

Lấy một access token ngắn hạn phục vụ Google Cloud API:

```bash
gcloud auth print-access-token
```

Lệnh trên **in token ra stdout**, vì thế chỉ dùng trong terminal riêng và không sao chép token vào chat, issue, log CI hoặc commit. Trong ví dụ tiếp theo, token được lưu trong biến shell tạm thời để gửi qua HTTPS.

### 6.2. Phân biệt xác thực với phân quyền

Một token hợp lệ chỉ chứng minh danh tính và phạm vi xác thực (OAuth scope). **IAM** quyết định danh tính đó có được `run.services.list`, `compute.instances.list` hoặc thao tác khác trên resource cụ thể hay không. Có token chưa đồng nghĩa có quyền xem tất cả project.

Khi gọi Google Cloud API, scope phổ biến là `https://www.googleapis.com/auth/cloud-platform`. Scope là điều kiện ở lớp OAuth; không thay thế IAM. Một số API còn có điều kiện project, trạng thái bật dịch vụ, quota, VPC Service Controls hoặc Organization Policy.

### 6.3. Application Default Credentials (ADC) dùng cho mã ứng dụng

Khi ứng dụng dùng Google Cloud client library, thư viện thường tìm **Application Default Credentials**. Trên máy phát triển có thể cấu hình credentials riêng cho ADC:

```bash
gcloud auth application-default login
gcloud auth application-default print-access-token
```

**Hai kho credentials khác nhau:** `gcloud auth login` phục vụ danh tính CLI, còn `gcloud auth application-default login` tạo credentials cho ADC. Chúng có thể trỏ đến các principal khác nhau. Một số API với user credentials còn yêu cầu quota project; khi gặp lỗi tương ứng, kiểm tra cấu hình `gcloud auth application-default set-quota-project PROJECT_ID` và quyền `serviceusage.services.use`.

Trên Cloud Run, GKE hoặc Compute Engine, ứng dụng nên sử dụng **danh tính workload** được nền tảng cung cấp (ví dụ service account gắn với tài nguyên, Workload Identity Federation khi phù hợp), ưu tiên token ngắn hạn. Tránh phát hành file khóa service account dài hạn nếu không cần thiết; kiểm soát IAM của runtime và nơi lưu secret.

### 6.4. API key và ID token có thay được access token?

Không có quy tắc “một loại credential dùng cho tất cả API”:

| Cách xác thực | Khi thường dùng | Điều cần nhớ |
| --- | --- | --- |
| OAuth 2.0 **access token** | Google Cloud management APIs cần IAM | Token có hạn; quyền thật phụ thuộc principal, scopes và IAM. |
| **ADC** | Ứng dụng/client library cần lấy Google credentials theo môi trường | ADC là cơ chế **tìm credentials**, không phải một loại token mới. |
| OIDC **ID token** | Gọi ứng dụng Cloud Run riêng tư và một số endpoint xác thực theo audience | Chứng minh danh tính cho dịch vụ đích; không dùng thay access token khi gọi Cloud Run Admin API. |
| **API key** | Một số Google APIs hỗ trợ truy cập theo key và hạn mức | Không thay được IAM principal cho thao tác quản trị tài nguyên cần OAuth. |

## 7. Thực hành: gọi Cloud Run REST API bằng `curl`

### 7.1. Gửi yêu cầu liệt kê dịch vụ

Ví dụ sau sử dụng Bash, chỉ thực hiện HTTP `GET`:

```bash
PROJECT_ID="demo-learning"
REGION="asia-southeast1"
GCLOUD_ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --silent --show-error --fail-with-body \
  --get "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services" \
  --data-urlencode "pageSize=20" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  -H "Accept: application/json"
```

Thay `PROJECT_ID` và `REGION` bằng môi trường thử nghiệm có quyền. Trên một số phiên bản `curl` cũ chưa hỗ trợ `--fail-with-body`, có thể dùng `--fail` và thêm cách thu thập status/response body riêng. Nên tắt shell tracing (`set -x`) trước khi dùng token để tránh lộ giá trị trong log.

Điều gì đã xảy ra?

1. `gcloud` lấy OAuth access token ngắn hạn cho tài khoản CLI hiện tại.
2. `curl` gửi `GET` tới `run.googleapis.com` qua TLS, có header `Authorization: Bearer ...`.
3. Google kiểm tra token, API đã bật và IAM permission của principal.
4. Nếu hợp lệ, server trả JSON chứa danh sách service (có thể rỗng) và token trang tiếp theo nếu còn kết quả.

Bạn cũng có thể chỉ định quota/billing project bằng header `x-goog-user-project` **khi API và loại credentials yêu cầu**:

```http
x-goog-user-project: PROJECT_ID
```

Đây không phải một cách “mượn quyền”: principal vẫn cần quyền sử dụng quota project (thường là `serviceusage.services.use`), cùng các quyền IAM của resource đích. Không tự thêm header rồi coi lỗi `403` là lỗi xác thực duy nhất.

### 7.2. Phiên bản PowerShell

Nếu dùng PowerShell 5.1/7 trên Windows:

```powershell
$ProjectId = "demo-learning"
$Region = "asia-southeast1"
$AccessToken = gcloud auth print-access-token
$Url = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/services?pageSize=20"

$Headers = @{
    Authorization = "Bearer $AccessToken"
    Accept = "application/json"
}

$Result = Invoke-RestMethod -Method Get -Uri $Url -Headers $Headers
$Result.services | Select-Object name, uri, ingress
```

Biến `$Result` biểu diễn đối tượng JSON đã được PowerShell phân tích; nếu không có service nào, thuộc tính `services` có thể rỗng hoặc không xuất hiện. Lỗi HTTP trong PowerShell thường ném exception; cần bắt và xem status/response body khi chẩn đoán.

### 7.3. Đọc JSON response đúng cách

Một phản hồi minh họa có dạng:

```json
{
  "services": [
    {
      "name": "projects/demo-learning/locations/asia-southeast1/services/order-api",
      "uri": "https://order-api-example.a.run.app",
      "ingress": "INGRESS_TRAFFIC_ALL"
    }
  ],
  "nextPageToken": "TOKEN_IF_MORE_RESULTS"
}
```

Đây là **dữ liệu minh họa**, không phải resource thực. Chỉ dùng các thuộc tính và giá trị enum phù hợp với response schema của phiên bản API đang gọi. Trường `uri` là URL service; còn `name` là tên tài nguyên để dùng trong API quản trị. Nếu `nextPageToken` không có hoặc rỗng, thông thường đã tới trang cuối.

Với `jq`, trích xuất các trường quan trọng:

```bash
curl --silent --show-error --fail-with-body \
  "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services?pageSize=20" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  | jq '{items: [(.services // [])[] | {name, uri, ingress}], nextPageToken}'
```

`.services // []` xử lý cả trường hợp response không có danh sách. Không nên viết automation phụ thuộc vào các trường không được API cam kết.

### 7.4. Lấy một service cụ thể

Khi đã biết tên service:

```bash
SERVICE_NAME="order-api"

curl --silent --show-error --fail-with-body \
  "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/services/${SERVICE_NAME}" \
  -H "Authorization: Bearer ${GCLOUD_ACCESS_TOKEN}" \
  -H "Accept: application/json"
```

Đây là method `projects.locations.services.get`, cần quyền `run.services.get`. Không dùng `get` để xem toàn bộ các dịch vụ vì phương thức đó yêu cầu một resource name cụ thể.

## 8. Phân trang, bộ lọc, quota và kết quả nhất quán

Với tài nguyên lớn, nhiều Google Cloud `list` APIs trả một phần kết quả cùng `nextPageToken`. Không kết luận rằng project chỉ có 20 service vì lời gọi đầu dùng `pageSize=20`.

Quy trình phân trang an toàn:

```text
GET .../services?pageSize=20
  ├─ services: [trang 1]
  └─ nextPageToken: "abc"
GET .../services?pageSize=20&pageToken=abc
  ├─ services: [trang 2]
  └─ nextPageToken: ""
=> Hoàn tất khi nextPageToken rỗng/không tồn tại.
```

Khi xây script:

1. Dùng `pageToken` trả về từ **cùng một phương thức**; không tự cấu tạo hoặc giải mã token.
2. Giữ nhất quán các query parameters giữa các trang; URL-encode token đúng chuẩn.
3. Không giả định thứ tự trả về ổn định nếu API không cam kết sort; danh sách có thể đổi khi tài nguyên đang được thêm/xóa.
4. Không giả định mọi phương thức đều hỗ trợ `filter`, `orderBy`, `pageSize` giống nhau; kiểm tra reference.
5. Đặt giới hạn request, retry hợp lý và quan sát quota; một vòng lặp phân trang vô hạn cũng có thể gây chi phí hoặc giới hạn tốc độ.

Đối với hệ thống cần snapshot nhất quán, việc gọi `list` nhiều trang khi tài nguyên liên tục thay đổi chưa chắc đáp ứng yêu cầu; hãy kiểm tra guarantee của API hoặc thiết kế đối soát phù hợp.

## 9. Đọc lỗi HTTP và xử lý retry

Khi thử REST API, đừng chỉ nhìn HTTP status. Hãy đọc cả phần JSON error (thường có `error.code`, `error.message`, `error.status` và đôi khi `error.details`), đồng thời ghi nhận thời điểm, method, resource name và request ID nếu được cung cấp.

| HTTP status | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `400 Bad Request` | Path/query/body sai, field không hợp lệ, thiếu parent | Đọc reference và error details; so tên field, region, enum và URL encoding. |
| `401 Unauthorized` | Thiếu/không hợp lệ/hết hạn access token hoặc thiếu scope | Lấy token mới đúng loại; xác minh header `Authorization`, OAuth scopes. |
| `403 Forbidden` | IAM thiếu quyền, API chưa bật, quota project chưa được cấp phép hoặc ràng buộc tổ chức | Đọc reason/details; xác định principal, resource, API enablement, quota/billing, Organization Policy. |
| `404 Not Found` | Sai project/region/resource, API version/path sai hoặc tài nguyên chưa tồn tại | So full resource name và region; một số hệ thống có thể cố tình không tiết lộ sự tồn tại của tài nguyên. |
| `409 Conflict` | Resource trùng, xung đột thay đổi, trạng thái thao tác chưa phù hợp | Xác minh trạng thái hiện tại và semantics của method; tránh gửi lại vô điều kiện. |
| `429 Too Many Requests` | Vượt quota hoặc bị giới hạn tốc độ | Giảm tốc, xem quota, áp dụng backoff và `Retry-After` nếu có. |
| `500/502/503/504` | Lỗi server hoặc lỗi tạm thời trên đường truyền/phụ thuộc | Retry có kiểm soát với exponential backoff và jitter, dựa trên tính an toàn của thao tác. |

Ví dụ một JSON lỗi thường gặp (minh họa):

```json
{
  "error": {
    "code": 403,
    "message": "Permission denied on resource.",
    "status": "PERMISSION_DENIED"
  }
}
```

**Retry chỉ an toàn khi hiểu semantics của yêu cầu.** `GET` thường có thể gửi lại vì không tạo thay đổi. Với `POST` tạo resource hoặc kích hoạt nghiệp vụ, lỗi timeout không có nghĩa phía server chưa xử lý: có thể cần `requestId`/idempotency key nếu API hỗ trợ hoặc phải đọc trạng thái trước khi thực hiện lại. Với `PATCH`, kiểm tra `etag`/precondition và `updateMask` cụ thể của API. Giới hạn số lần retry, thêm độ trễ tăng dần và jitter để tránh khuếch đại sự cố.

Một checklist chẩn đoán có thứ tự: **URL/version → tên project/region/resource → token & scopes → IAM permission → API enabled → quota/policy → request JSON/schema**. Cách này hữu ích hơn việc thử ngẫu nhiên thêm quyền Administrator.

## 10. Từ thao tác đọc sang thao tác thay đổi tài nguyên

Với `POST`, `PATCH` và `DELETE`, cần xem nhiều hơn cú pháp HTTP. Ví dụ, một yêu cầu cập nhật cấu hình có thể trả về **long-running Operation** thay vì bản ghi tài nguyên hoàn chỉnh; script phải theo dõi Operation đến trạng thái kết thúc rồi đọc lại resource để xác minh.

Trước khi viết automation thay đổi GCP, trả lời:

- **Phạm vi:** project, region, tên resource và môi trường dev/staging/prod có được truyền tường minh không?
- **Quyền:** identity nào chạy lệnh, có được cấp permission tối thiểu không?
- **Tính lặp:** gọi lại có tạo bản sao hoặc ghi đè ngoài ý muốn không? API có `requestId`, `etag`, preconditions không?
- **Trạng thái bất đồng bộ:** API trả tài nguyên ngay hay cần đợi Operation hoàn tất?
- **Khôi phục:** đã backup cấu hình/dữ liệu, ghi nhận trước/sau và chuẩn bị rollback hợp lệ chưa?
- **Kiểm toán:** log có nhận diện người chạy, change ID, resource name mà không lộ access token/secret không?

Một lối phát triển an toàn là thử `list/get` ở sandbox → mô tả chính xác payload và quyền → kiểm chứng trên môi trường test → dùng công cụ như Terraform để quản lý cấu hình dài hạn và phát hiện drift khi phù hợp.

## 11. Chọn công cụ phù hợp với tình huống

| Công cụ | Phù hợp khi | Điểm cần nhớ |
| --- | --- | --- |
| **REST + curl/PowerShell** | Muốn học API, thử method mới, tích hợp hệ thống không có client library, debug request thô | Tự xử lý token, retry, pagination, encoding và response schema. |
| **APIs Explorer** | Khám phá tham số và response nhanh | Hữu ích cho thử nghiệm có kiểm soát; tránh thao tác ghi nhầm trong project thật. |
| **Google Cloud CLI (gcloud)** | Quản trị và khám phá thủ công, scripting đơn giản | CLI thường gom nhiều request hoặc biến đổi kết quả; tham khảo `--format=json` khi cần. |
| **Client library** | Ứng dụng production cần gọi Google Cloud API thường xuyên | Có tích hợp ADC, request model và hỗ trợ retry/pagination theo từng thư viện/API; vẫn phải hiểu IAM và quota. |
| **Terraform / IaC** | Khai báo và duy trì tài nguyên lâu dài, review thay đổi qua Git | Dùng plan/review, quản lý state an toàn; không thay thế mọi thao tác nghiệp vụ. |

Không cần gọi REST trực tiếp chỉ để chứng minh rằng API tồn tại. Một đội phát triển có thể dùng Terraform quản lý hạ tầng, client library xử lý thông điệp, `gcloud` kiểm tra thủ công, và `curl` khi cần debug chính xác một method.

### Những API nên biết tiếp theo

| Nhu cầu trong module | API REST gợi ý tra cứu | Phạm vi phương thức chỉ đọc để bắt đầu |
| --- | --- | --- |
| Tổ chức/project | Cloud Resource Manager API | `projects.get`, `projects.list` (kiểm tra parent/filter theo phiên bản) |
| Quyền truy cập | Cloud Resource Manager/IAM API | `getIamPolicy` theo đúng loại tài nguyên và yêu cầu quyền |
| Compute Engine | Compute Engine API | `instances.list` theo project/zone |
| GKE | Kubernetes Engine API | `projects.locations.clusters.list` |
| Cloud Run | Cloud Run Admin API | `projects.locations.services.list/get` |
| Lưu trữ object | Cloud Storage JSON API | `buckets.list`, `objects.list` |
| Dữ liệu quan hệ | Cloud SQL Admin API | `instances.list/get` |
| Theo dõi dịch vụ | Cloud Monitoring API | Liệt kê metric descriptors và đọc time series theo quyền |

Tên method và cấu trúc resource thay đổi theo phiên bản API; bảng trên là **điểm bắt đầu để tìm tài liệu**, không phải URL có thể sao chép nguyên xi. Ví dụ, Compute Engine API dùng vùng `zones/ZONE` khi liệt kê VM trong zone, còn Cloud Run dùng `locations/REGION`. Không thể thay “services” bằng “instances” trong cùng một base URL rồi cho rằng endpoint hợp lệ.

## 12. Thực hành có hướng dẫn

### Bài thực hành A — Khám phá mà chưa thay đổi tài nguyên

1. Chọn một project sandbox có quyền xem Cloud Run. Ghi lại project ID và region; kiểm tra Cloud Run API đã bật.
2. Mở REST reference `projects.locations.services.list`, xác định method, URL, path parameters, query parameters, OAuth scopes, permission và JSON response.
3. Lấy token của CLI bằng `gcloud auth print-access-token`; gọi `GET` bằng `curl` hoặc PowerShell.
4. Nếu response có services, lấy một `name` để thử `projects.locations.services.get`; nếu rỗng, ghi nhận đó vẫn có thể là kết quả hợp lệ.
5. So sánh tên tài nguyên với `gcloud run services list`; nếu khác, kiểm tra project, region và identity của hai lệnh.
6. Thử phân trang chỉ khi có đủ tài nguyên; ghi lại quy tắc `nextPageToken` ngay cả khi chưa xuất hiện trong môi trường nhỏ.

**Bằng chứng hoàn thành:** URL request đã ẩn token; HTTP status; 1–2 trường JSON liên quan; giải thích quyền IAM cần có; nhận xét về pagination.

### Bài thực hành B — Đọc và sửa một lỗi cấu hình trong sandbox

Giả định request `GET` trả `403 PERMISSION_DENIED`. Không đoán ngay cần role Editor: trước hết ghi lại principal đang dùng, phân biệt API chưa bật với thiếu `run.services.list`, đọc `error.details` nếu có và kiểm tra quyền sử dụng quota project khi được thông báo. Sau đó mô tả **thay đổi quyền tối thiểu** cần đề xuất cho người quản trị. Không yêu cầu thử cấp quyền quản trị rộng chỉ để vượt qua lỗi.

### Bài thực hành C — Chọn API đúng cho ba yêu cầu

| Yêu cầu | Hướng tìm API | Điều phải xác minh |
| --- | --- | --- |
| “Liệt kê VM tại một zone” | Compute Engine REST API, resource `instances` | Project, zone, `instances.list` và `compute.instances.list`. |
| “Biết Cloud SQL instances nào đang tồn tại” | Cloud SQL Admin REST API | `instances.list`, project, IAM, trạng thái API. |
| “Xem một Cloud Run service có public ingress không” | Cloud Run REST API v2, `services.get` | `ingress`, cơ chế xác thực invoker/IAM và chính sách mạng; ingress một mình không mô tả toàn bộ quyền truy cập. |

Hãy nộp một bản ghi ngắn cho mỗi trường hợp theo mẫu:

```text
Nhu cầu:
API / version / method:
HTTP method + URL resource (không chứa token):
Project / region / zone:
IAM permission + loại credential:
Trường JSON cần xem:
Lỗi/giới hạn có thể gặp:
Lựa chọn CLI hoặc client library tương đương:
```

## 13. Tự kiểm tra và ghi nhớ

1. Vì sao `gcloud auth print-access-token` không đồng nghĩa tài khoản có quyền `run.services.list`?
2. Cloud Run Admin API và URL ứng dụng Cloud Run khác nhau ở đối tượng quản lý và loại token như thế nào?
3. Khi REST `list` có `nextPageToken`, phải làm gì trước khi kết luận danh sách đã đầy đủ?
4. Vì sao cùng lỗi `403` có thể cần những cách sửa khác nhau?
5. Khi một request `POST` timeout, vì sao không nên tự động retry vô hạn?
6. Khi nào dùng `curl`, khi nào dùng `gcloud`, khi nào nên dùng client library hoặc Terraform?

**Ghi nhớ quy trình:** xác định nhu cầu → tìm đúng REST reference và phiên bản → kiểm tra project/location, API và IAM → lấy credential thích hợp → thử `GET` có kiểm soát → đọc JSON, status và pagination → tự động hóa chỉ sau khi hiểu retry, quota, idempotency và quyền.

### Tài liệu tra cứu chính thức

- [Google Cloud APIs overview](https://cloud.google.com/apis/docs/overview)
- [Cloud Run v2 REST reference](https://cloud.google.com/run/docs/reference/rest/v2)
- [Google Cloud authentication overview](https://cloud.google.com/docs/authentication)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Google APIs Discovery Service](https://developers.google.com/discovery/v1/getting_started)
- [Cloud IAM overview](https://cloud.google.com/iam/docs/overview)

Các phiên bản API, giới hạn quota và cách xác thực có thể thay đổi theo sản phẩm. Khi triển khai thực tế, hãy đối chiếu method cụ thể trên tài liệu chính thức và cấu hình project đang sử dụng.
