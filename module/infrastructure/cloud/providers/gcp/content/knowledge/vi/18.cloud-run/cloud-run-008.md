# Service identity và xác thực giữa các Cloud Run services

Một hệ thống đặt `orders-api` ở Cloud Run để nhận yêu cầu đặt hàng và gọi `inventory-api` để kiểm tra tồn kho. `inventory-api` không nên cho phép bất kỳ ai có URL đều gọi được. Đồng thời, `orders-api` phải chứng minh **danh tính của chính dịch vụ** khi gọi API nội bộ mà không lưu khóa service account JSON trong container.

Cloud Run giải quyết nhu cầu này bằng **service identity** (service account dùng khi chạy), **Cloud Run IAM Invoker** trên service đích và **Google-signed OpenID Connect (OIDC) ID token** có audience phù hợp. Trong chương **Cloud Run** của module **CLOUD_PROVIDERS_GCP**, bài này kết nối kiến thức IAM, HTTP, VPC, phát hành và giám sát để triển khai giao tiếp dịch vụ an toàn.

Sau bài học, bạn có thể:

1. Phân biệt runtime service identity, danh tính deploy, service agent và người dùng cuối.
2. Cấp quyền gọi theo **nguyên tắc tối thiểu** trên đúng Cloud Run service đích.
3. Lấy ID token trong Cloud Run, đặt `aud` và gửi request với header phù hợp.
4. Phân biệt xác thực danh tính với kiểm soát ingress, kết nối mạng và phân quyền nghiệp vụ.
5. Chẩn đoán lỗi 401/403, sai audience, thiếu quyền hoặc lỗi mạng; vận hành token an toàn.
6. Thực hành quy trình hai Cloud Run services và kiểm tra cả yêu cầu được phép lẫn bị từ chối.

## 1. Luồng xác thực giữa hai dịch vụ

~~~mermaid
sequenceDiagram
    participant C as Client được phép gọi A
    participant A as Cloud Run orders-api
    participant M as Metadata server
    participant B as Cloud Run inventory-api
    C->>A: HTTP request tới A
    A->>M: Yêu cầu ID token với audience URL(B)
    M-->>A: Google-signed ID token cho SA của A
    A->>B: HTTPS + Authorization Bearer ID_TOKEN
    B->>B: Kiểm tra token, aud, IAM Invoker và ingress
    B-->>A: Kết quả tồn kho
    A-->>C: Phản hồi ứng dụng
~~~

Trong sơ đồ, A có danh tính riêng, ví dụ `orders-caller@PROJECT_ID.iam.gserviceaccount.com`; B có runtime identity khác, ví dụ `inventory-runtime@PROJECT_ID.iam.gserviceaccount.com`. Quyền **gọi B** được cấp cho **service account của A trên B**. Quyền của B khi truy cập database hoặc Secret Manager lại được cấp cho service account của B trên tài nguyên tương ứng.

| Đối tượng | Vai trò trong quy trình | Quyền thường cần |
| --- | --- | --- |
| **Người/CI deploy A** | Triển khai revision, gắn runtime service account | Quyền deploy Cloud Run và `iam.serviceAccounts.actAs` trên service account gắn với A |
| **Runtime service account của A** | Đại diện danh tính của code chạy trong A | `roles/run.invoker` **trên B**, không phải vai trò Admin toàn project |
| **Cloud Run service B** | Nhận request và kiểm tra IAM ở lớp Cloud Run trước khi chuyển tới container | Cấu hình yêu cầu xác thực; IAM policy cho A |
| **Runtime service account của B** | Danh tính khi code B gọi Google Cloud APIs | Quyền tối thiểu trên database, bucket, secret… mà B thực sự dùng |
| **Cloud Run service agent** | Danh tính do Google quản lý để vận hành hạ tầng Cloud Run | Không phải service account mà application container nên dùng để tự xác thực gọi B |
| **Người dùng cuối** | Khách hàng sử dụng ứng dụng qua A | Quyền nghiệp vụ do ứng dụng/identity provider quản lý, không mặc nhiên có quyền gọi trực tiếp B |

### 1.1. Hai câu hỏi tách biệt

- **Authentication:** “Ai đang gọi?” — Cloud Run xác minh token Google ký và danh tính principal.
- **Authorization:** “Danh tính ấy được phép gọi B không?” — IAM của service đích yêu cầu quyền `run.routes.invoke`, thường qua `roles/run.invoker`.

Ngay cả khi A được phép gọi B, code của B vẫn cần kiểm tra **quyền nghiệp vụ**: ví dụ người dùng nào được xem đơn hàng nào. Không được suy ra rằng mọi yêu cầu đi qua A đều được phép đọc mọi bản ghi tại B.

### 1.2. Service identity và service agent không giống nhau

**Service identity** là service account gắn với một Cloud Run service/revision, được sử dụng làm danh tính để container gọi Google Cloud APIs và lấy token. Nếu không gắn service account riêng, Cloud Run có thể dùng Compute Engine default service account của project theo cấu hình mặc định; thực hành tốt là tạo **user-managed service account riêng cho từng workload**.

**Cloud Run service agent** là tài khoản do Google quản lý để vận hành hạ tầng Cloud Run, có vai trò khác runtime identity. **Deployer** còn là danh tính thứ ba: người hoặc CI/CD cần quyền triển khai và quyền `roles/iam.serviceAccountUser` (bao gồm `iam.serviceAccounts.actAs`) trên runtime service account để gắn nó vào service.

Không dùng `roles/iam.serviceAccountTokenCreator` thay thế cho `roles/iam.serviceAccountUser` hoặc `roles/run.invoker`. Đối với lời gọi A → B trong cùng môi trường Cloud Run, A thường lấy ID token từ metadata server mà **không cần tải khóa JSON hoặc tự impersonate service account khác**.

## 2. IAM ở service đích và lựa chọn ingress

### 2.1. Đặt quyền ở đúng nơi

Giả sử chỉ `orders-api` được gọi `inventory-api`. Cấp `roles/run.invoker` cho service account của A **trên B**, không cấp cho `allUsers` hoặc trên toàn project nếu không cần:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export CALLER="orders-api"
export TARGET="inventory-api"
export CALLER_SA="orders-caller@$PROJECT_ID.iam.gserviceaccount.com"

# Thao tác ghi IAM; chạy khi đã có phê duyệt trên đúng service B
gcloud run services add-iam-policy-binding "$TARGET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"

# Chỉ đọc: xác minh policy của B
gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

`roles/run.invoker` là role có quyền `run.routes.invoke`. Tài khoản A **không cần** quyền `roles/run.admin` hoặc quyền sửa IAM trên B chỉ để gửi request. Nếu B dùng Cloud SQL, B cần quyền và cấu hình kết nối riêng; IAM Invoker trên B không tự cấp quyền database.

### 2.2. IAM check và network ingress là hai lớp

| Kiểm soát | Kiểm tra gì? | Lưu ý |
| --- | --- | --- |
| **Require authentication / Invoker IAM check** | Principal có token hợp lệ và quyền gọi service hay không | Endpoint có thể có đường Internet nhưng vẫn trả lỗi khi thiếu quyền. |
| **`ingress=all`** | Cho phép request từ các đường ingress hợp lệ, kể cả Internet | **Không** có nghĩa tự mở IAM; vẫn cần token nếu IAM check bật. |
| **`ingress=internal`** | Chỉ chấp nhận các nguồn/đường mạng được Cloud Run nhận diện là nội bộ | Cloud Run → Cloud Run thường cần cấu hình **VPC egress/routing** đúng để được nhận diện nội bộ. |
| **`ingress=internal-and-cloud-load-balancing`** | Nội bộ và các request qua external Application Load Balancer phù hợp | Thường dùng khi muốn áp Cloud Armor/IAP hoặc tập trung entrypoint ở load balancer. |

Không nên mặc định “hai Cloud Run services ở cùng project thì request đến `internal` luôn đi qua được”. Với Cloud Run làm caller, cần kiểm tra hướng dẫn **receive requests from other Cloud Run services**, Direct VPC egress hoặc Serverless VPC Access và routing phù hợp. Một token hợp lệ không thể vượt qua ingress policy đang chặn đường mạng.

Ngược lại, `ingress=internal` **không thay thế IAM**, bởi nhiều workload nội bộ có thể chung VPC. Với API riêng tư, nên dùng cả **đường vào được kiểm soát** lẫn **IAM Invoker có phạm vi hẹp**, nếu kiến trúc yêu cầu.

### 2.3. Bảo vệ khỏi confused deputy

Nếu A được cấp quyền gọi B nhưng A lại mở công khai endpoint `/proxy?url=...` và chuyển nguyên văn yêu cầu của bất kỳ ai vào B, người ngoài có thể lợi dụng danh tính của A để làm việc mà họ không được phép. Đây là rủi ro **confused deputy**.

Vì vậy A phải xác thực người dùng, kiểm tra quyền với từng thao tác, giới hạn endpoint/đường dẫn được gọi, không chuyển token hay dữ liệu tùy ý và ghi audit log phù hợp. Quyền service-to-service **không** có nghĩa cần chuyển tiếp ID token người dùng cuối để thay token dịch vụ.

## 3. ID token: lấy đúng danh tính và audience

Để gọi một Cloud Run service có bật Invoker IAM check, cách thông dụng là dùng **Google-signed OIDC ID token**. Token có các claims như `iss`, `sub`, `aud`, `iat` và `exp`; Cloud Run kiểm tra chữ ký, hạn dùng, audience và quyền IAM tương ứng. **Không sử dụng OAuth access token cho Google APIs như một sự thay thế tùy tiện cho ID token của Cloud Run**.

### 3.1. Quy tắc audience

Giả sử service B có URL chuẩn:

~~~text
https://inventory-api-abcdef-uc.a.run.app
~~~

| Endpoint gọi | Giá trị `aud` nên dùng |
| --- | --- |
| `https://inventory-api-abcdef-uc.a.run.app/health` | URL **gốc** của service B |
| `https://inventory-api-abcdef-uc.a.run.app/api/items?id=1` | URL **gốc** của service B; không thêm path/query |
| URL của một **traffic tag** thuộc B | Vẫn dùng URL **gốc** của B, không dùng URL tag làm audience |
| B được gọi qua custom domain | Không dùng custom domain làm audience mặc định; dùng URL chuẩn hoặc **custom audience** được cấu hình trên B |

Lấy URL chuẩn bằng lệnh chỉ đọc:

~~~bash
TARGET_URL="$(gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'Cloud Run target: %s\n' "$TARGET_URL"
~~~

**Phân biệt:** `TARGET_URL` để tạo token là **service base URL**, còn endpoint HTTP có thể là `$TARGET_URL/health` hoặc một đường dẫn nghiệp vụ. Nếu dùng custom audience, phải khai báo audience đó trên B và truyền đúng chuỗi đã cấu hình.

### 3.2. Cách khuyến nghị: Google Auth library

Trong container A đang chạy trên Cloud Run, thư viện Google Auth có thể lấy ID token từ môi trường chạy. Ví dụ Python (phần code chạy ở **service A**, không phải trong Cloud Shell):

~~~python
import os

import google.auth.transport.requests
import google.oauth2.id_token
import requests

target_url = os.environ["TARGET_URL"].rstrip("/")

def request_inventory():
    # audience phải là URL gốc của service đích, KHÔNG phải /health
    auth_request = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(
        auth_request, target_url
    )
    response = requests.get(
        f"{target_url}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.text
~~~

`google-auth` tự sử dụng credential phù hợp với môi trường, bao gồm metadata server của Cloud Run. Không cần tạo service account key JSON. ID token thường có hạn khoảng **một giờ**; để thư viện quản lý hoặc tự refresh theo thời điểm `exp` nếu có cache. **Không ghi token vào log** và không gửi nó đến hostname không thuộc bên nhận đáng tin cậy.

### 3.3. Truy vấn metadata server trực tiếp

Khi cần kiểm tra hoặc tự viết client, code **bên trong Cloud Run A** có thể gọi metadata server:

~~~bash
# Chạy BÊN TRONG container của Cloud Run A; KHÔNG chạy từ laptop/Cloud Shell
TARGET_URL="https://SERVICE_B_DEFAULT_RUN_APP_URL"
TOKEN="$(curl --fail --silent --show-error --get \
  -H "Metadata-Flavor: Google" \
  --data-urlencode "audience=$TARGET_URL" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity")"

curl --fail --show-error --silent \
  --max-time 10 \
  -H "Authorization: Bearer $TOKEN" \
  "$TARGET_URL/"

unset TOKEN
~~~

`default` trong URL metadata là **alias của service account gắn với revision**, không có nghĩa Cloud Run nhất thiết đang dùng Compute Engine default service account của project. Metadata endpoint trả ID token mang danh tính runtime của A; request phải kèm `Metadata-Flavor: Google`.

Không in `$TOKEN` ra terminal, lưu trong Cloud Logging hoặc đưa token vào query parameter. Dùng HTTPS với B; hạn chế retry, đặt timeout và chỉ gửi token đến endpoint đích đã được cấu hình tin cậy.

### 3.4. Dùng header nào?

Cloud Run chấp nhận hai dạng header cho xác thực dịch vụ:

~~~http
Authorization: Bearer GOOGLE_SIGNED_ID_TOKEN
~~~

hoặc:

~~~http
X-Serverless-Authorization: Bearer GOOGLE_SIGNED_ID_TOKEN
~~~

Dùng `X-Serverless-Authorization` nếu `Authorization` đã được ứng dụng sử dụng để chuyển credential của người dùng. Nếu gửi cả hai, **Cloud Run ưu tiên kiểm tra `X-Serverless-Authorization`**; chữ ký trong token của header này bị loại bỏ trước khi dữ liệu header được chuyển tới user container theo cơ chế Cloud Run. Không coi đây là kênh chuyển token gốc tới B.

**Hai tầng danh tính:** Cloud Run có thể xác thực **dịch vụ A** bằng token ở `X-Serverless-Authorization`, trong khi container B xử lý một token người dùng riêng trong `Authorization`. B vẫn phải kiểm tra độc lập token người dùng và quyền truy cập tài nguyên nghiệp vụ. Không mặc định cả hai token thuộc cùng một principal.

### 3.5. Các lựa chọn không nên nhầm

| Cơ chế | Dùng cho | Không thay thế |
| --- | --- | --- |
| **OIDC ID token** có `aud` đúng B | Chứng minh danh tính khi A gọi private Cloud Run B | Quyền nghiệp vụ hoặc IAM Invoker trên B |
| **OAuth 2.0 access token** | Thường dùng để gọi Google Cloud APIs như Cloud Storage/Secret Manager | ID token có audience để gọi Cloud Run theo luồng chuẩn |
| **Service account key JSON** | Chỉ trong trường hợp đặc biệt có kiểm soát vòng đời khóa | Runtime identity tự cấp token từ metadata server |
| **Signed JWT tự tạo** | Một số giao thức liên kết/cơ chế exchange đã được hỗ trợ | Google-signed ID token mà Cloud Run xác thực |
| **Cloud Run IAM policy** | Quyết định danh tính nào được phép gọi B | Kiểm soát ingress/VPC hoặc authorization của nghiệp vụ |

Với workload **ngoài Google Cloud**, ưu tiên **Workload Identity Federation** để nhận credential ngắn hạn, không tải khóa JSON tồn tại lâu. Đối với người phát triển thử bằng gcloud, `gcloud auth print-identity-token` là công cụ kiểm tra thủ công; không sử dụng token người dùng thiếu audience rõ ràng như giải pháp production.

## 4. Thực hành: Cloud Run A gọi Cloud Run B bằng ID token

Lab sau dùng **Cloud Run service B** là receiver và **Cloud Run service A** là caller. B yêu cầu xác thực; chỉ runtime service account của A có quyền Invoker trên B. Để thử dễ dàng, hai service dùng URL `run.app` và đường ingress cho phép request đến lớp kiểm tra IAM. Nếu dự án sử dụng `internal` ingress, cần thiết kế VPC egress trước như mục 2.2.

**Điều kiện:** project lab có billing và quyền tạo service account, quyền deploy Cloud Run, quyền cấp IAM trên **service A/B**, quyền `iam.serviceAccounts.actAs` trên những service account đã chọn, các API build cần thiết và ngân sách thử nghiệm. Các lệnh chỉ là hướng dẫn; **không thực thi trên production**.

### 4.1. Tạo danh tính tách biệt

Chạy trong Bash/Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export CALLER="orders-api-lab"
export TARGET="inventory-api-lab"
export CALLER_SA="orders-caller@$PROJECT_ID.iam.gserviceaccount.com"
export TARGET_SA="inventory-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com iam.googleapis.com

gcloud iam service-accounts create orders-caller \
  --display-name="Cloud Run caller lab"
gcloud iam service-accounts create inventory-runtime \
  --display-name="Cloud Run target lab"
~~~

Trước khi tiếp tục, người deploy cần `roles/iam.serviceAccountUser` trên **hai service account này** và quyền triển khai Cloud Run theo chính sách. Để tạo nguồn bằng `--source`, còn cần quyền Cloud Build/Artifact Registry của quy trình source deployment. Không gán Editor/Owner hoặc Token Creator toàn project chỉ để giải quyết một lỗi quyền khi deploy.

### 4.2. Triển khai service B yêu cầu xác thực

Sử dụng một container HTTP mẫu đã được tổ chức phê duyệt. Ví dụ public image của Cloud Run:

~~~bash
export TARGET_IMAGE="us-docker.pkg.dev/cloudrun/container/hello"

gcloud run deploy "$TARGET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$TARGET_IMAGE" \
  --service-account="$TARGET_SA" \
  --no-allow-unauthenticated

TARGET_URL="$(gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'B URL: %s\n' "$TARGET_URL"
~~~

Lệnh `--no-allow-unauthenticated` yêu cầu Cloud Run áp kiểm tra IAM Invoker. Nó **không tự biến endpoint thành private network**; ingress của B cũng phải được kiểm tra theo chính sách của project. Với lab dùng gọi trực tiếp tới URL `run.app` từ A, nếu B đặt `ingress=internal` thì cấu hình mạng phải bảo đảm traffic được nhận diện là nội bộ.

### 4.3. Chỉ cấp quyền A → B

~~~bash
gcloud run services add-iam-policy-binding "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"

gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Kiểm tra policy **không có `allUsers`** và không vô tình cấp Invoker cho service account B, người dùng hoặc toàn project nếu không cần. IAM binding trên B mới là thứ cho phép A gọi B, không phải tên biến môi trường `TARGET_URL`.

### 4.4. Mã nguồn của caller A

Trên máy lab, tạo thư mục `caller/` với ba file bên dưới. Mã chỉ gọi endpoint gốc của B, lấy ID token với audience B và **không trả token ra HTTP response**.

**`caller/main.py`**

~~~python
import os

from flask import Flask, jsonify
import google.auth.transport.requests
import google.oauth2.id_token
import requests

app = Flask(__name__)
TARGET_URL = os.environ["TARGET_URL"].rstrip("/")

@app.get("/call")
def call_target():
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(
        auth_req, TARGET_URL
    )
    upstream = requests.get(
        TARGET_URL + "/",
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=10,
    )
    # Không phản chiếu token hoặc nội dung riêng tư của B ra client A
    return jsonify(
        upstream_status=upstream.status_code,
        upstream_bytes=len(upstream.content),
    ), 200 if upstream.ok else 502
~~~

**`caller/requirements.txt`**

~~~text
Flask>=3,<4
gunicorn>=22,<24
google-auth>=2,<4
requests>=2,<3
~~~

**`caller/Procfile`**

~~~text
web: gunicorn --bind :$PORT main:app
~~~

Ví dụ giới hạn version theo major; khi triển khai thật nên khóa phiên bản đã qua kiểm thử và quét dependency. Đây là demo, chưa có đầy đủ tracing, circuit breaker và error handling cho production.

### 4.5. Triển khai A với service account riêng

Từ thư mục chứa `caller/`:

~~~bash
gcloud run deploy "$CALLER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=./caller \
  --service-account="$CALLER_SA" \
  --set-env-vars="TARGET_URL=$TARGET_URL" \
  --no-allow-unauthenticated

CALLER_URL="$(gcloud run services describe "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
printf 'A URL: %s\n' "$CALLER_URL"
~~~

`--source` cần quy trình build được bật và quyền của build/deploy identity. Đường vào A cũng yêu cầu xác thực; đây là chủ đích để không tạo một proxy công khai mang quyền của A. Không để `TARGET_URL` nhận giá trị tùy ý từ query parameter của người dùng.

### 4.6. Kiểm thử cả quyền hợp lệ và quyền bị từ chối

**Kiểm thử âm tính:** gọi B **không có token**:

~~~bash
curl --silent --show-error --include "$TARGET_URL/"
~~~

Kết quả mong đợi: **401 hoặc 403** tùy cách Cloud Run xử lý yêu cầu và chính sách; quan trọng là **không được nhận phản hồi nghiệp vụ thành công**. Nếu nhận 200 từ B, kiểm tra Invoker IAM check và IAM bindings trước khi tiếp tục.

**Cho người thử nghiệm quyền gọi A, không cấp quyền gọi B:**

~~~bash
# Chỉ dùng user principal thật trong project lab, có phê duyệt
TEST_USER="YOUR_DEVELOPER_EMAIL"
gcloud run services add-iam-policy-binding "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="user:$TEST_USER" \
  --role="roles/run.invoker"
~~~

**Kiểm thử dương tính qua A** (chỉ dành cho người dùng `TEST_USER` đã xác thực trong gcloud):

~~~bash
# Token gcloud của người dùng chỉ dùng để KIỂM THỬ, không phải token runtime A→B
USER_TOKEN="$(gcloud auth print-identity-token)"
curl --silent --show-error --include \
  -H "Authorization: Bearer $USER_TOKEN" \
  "$CALLER_URL/call"
unset USER_TOKEN
~~~

Kết quả mong đợi: A phản hồi JSON chứa `upstream_status: 200` nếu service B mẫu khỏe, caller A có đúng runtime identity và đã cấp Invoker trên B. Token người dùng dùng để vào A **khác** ID token mà A tự lấy để gọi B.

Tiếp theo, dùng cùng tài khoản người thử để gọi B trực tiếp: nếu tài khoản **không có** quyền Invoker trên B, yêu cầu phải bị từ chối. Điều này giúp chứng minh quyền không vô tình cấp lan sang user.

**Đối chứng:** thu hồi tạm quyền A → B trong lab, lặp lại yêu cầu tới A; request nội bộ phải không còn thành công. Chỉ thực hiện đối chứng nếu được phê duyệt và có kế hoạch cấp lại quyền, tuyệt đối không dùng trên service production.

### 4.7. Dọn đúng tài nguyên bài tập

Sau khi xác nhận đây là **hai service lab**, không có ứng dụng khác phụ thuộc:

~~~bash
gcloud run services delete "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" --quiet
gcloud run services delete "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" --quiet

# Chỉ xóa hai service account do bài lab tạo và không còn ai dùng
gcloud iam service-accounts delete "$CALLER_SA" \
  --project="$PROJECT_ID" --quiet
gcloud iam service-accounts delete "$TARGET_SA" \
  --project="$PROJECT_ID" --quiet
~~~

Nếu đã cấp quyền deployer `roles/iam.serviceAccountUser` hoặc tạo Artifact Registry repository, build artifacts và log riêng cho bài tập, hãy kiểm tra và dọn **đúng những tài nguyên lab** được quản lý theo chính sách. Xóa service không tự dọn mọi image, log hoặc cấu hình IAM cấp ở scope lớn. Chi phí Cloud Build, Artifact Registry, Cloud Run và Cloud Logging có thể được ghi nhận trễ.

## 5. Gọi đồng bộ và bất đồng bộ

### 5.1. HTTP đồng bộ A → B

Mẫu ở mục 4 là **synchronous invocation**: A gửi HTTP request rồi chờ B trả lời. Nó phù hợp khi A cần kết quả ngay, nhưng phải xác định **timeout, retry, idempotency và giới hạn concurrency**:

- Đặt timeout nhỏ hơn deadline nghiệp vụ của A; không chờ vô hạn.
- Retry chỉ với lỗi phù hợp, backoff có jitter và giới hạn số lần; **POST tạo đơn hàng** cần idempotency key để tránh thực hiện hai lần.
- Dùng circuit breaker hoặc fallback nếu B không sẵn sàng; không để lỗi dây chuyền khiến mọi instance A bị nghẽn.
- Theo dõi p95/p99 latency và tỷ lệ lỗi từng hop, không chỉ HTTP status cuối.
- Nếu A dùng `X-Serverless-Authorization` để xác thực với B, B vẫn có thể nhận token người dùng khác trong `Authorization` theo thiết kế, nhưng phải kiểm tra token người dùng riêng.

### 5.2. Cloud Tasks gọi B bằng OIDC

Với tác vụ không cần kết quả tức thời, A có thể đưa công việc vào **Cloud Tasks**. Cloud Tasks gọi URL B và tự gắn OIDC token theo service account được cấu hình cho task. Ví dụ ý tưởng:

~~~mermaid
flowchart LR
    A["Cloud Run A"] -->|Tạo task| Q["Cloud Tasks queue"]
    Q -->|"POST + OIDC ID token"| B["Cloud Run B"]
    B -->|2xx khi xử lý thành công| Q
    Q -. "Retry theo chính sách khi lỗi" .-> B
~~~

Khi tạo HTTP task:

- `oidcToken.serviceAccountEmail` xác định danh tính Cloud Tasks sẽ sử dụng để gọi B; thường phải thuộc **cùng project với queue**.
- Service account đó cần `roles/run.invoker` **trên B**.
- Principal tạo task cần quyền enqueuer và quyền `iam.serviceAccounts.actAs` trên service account mà task dùng theo quy tắc Cloud Tasks.
- Đặt **`audience` bằng URL gốc của B**, đặc biệt khi URL task có path như `/process`. Không bỏ qua audience nếu hệ thống mặc định dùng nguyên URL có path.
- Handler B phải xử lý **at-least-once delivery**, retry, duplicate tasks, dead-letter và timeout theo yêu cầu.

Ví dụ lệnh CLI minh họa sau khi **queue, danh tính và quyền đã được chuẩn bị**:

~~~bash
gcloud tasks create-http-task \
  --queue="orders-queue" \
  --location="$REGION" \
  --url="$TARGET_URL/process" \
  --method=POST \
  --oidc-service-account-email="tasks-caller@$PROJECT_ID.iam.gserviceaccount.com" \
  --oidc-token-audience="$TARGET_URL"
~~~

Cú pháp/tùy chọn có thể thay đổi giữa các phiên bản gcloud; xác minh `gcloud tasks create-http-task --help` trong môi trường được phép. Lệnh là **tạo task có thể kích hoạt request thật**, không chạy trên queue production khi chưa phê duyệt. Cloud Run B cũng phải có endpoint `/process` và logic xử lý idempotent; container `hello` trong lab trước **không có** endpoint này.

### 5.3. Những lựa chọn khác

**Pub/Sub push** và **Cloud Scheduler** cũng có thể dùng OIDC identity để gọi Cloud Run khi được cấu hình theo tài liệu sản phẩm. Với giao tiếp bất đồng bộ, bên phát event thường không cần tự lấy ID token của B; dịch vụ trung gian gắn token theo danh tính được cấp quyền. Cloud Run còn có cơ chế kết nối nội bộ được quản lý theo từng phiên bản sản phẩm, ví dụ **express links (Preview)**; chỉ dùng nếu đã kiểm tra khả năng hỗ trợ, giới hạn và chính sách tổ chức.

Không mặc định lựa chọn async làm mất nhu cầu IAM: principal gọi B vẫn cần quyền thích hợp, và B vẫn phải xác minh dữ liệu nghiệp vụ.

## 6. Chẩn đoán lỗi xác thực và kết nối

### 6.1. Bảng lỗi theo lớp

| Biểu hiện | Nguồn gốc thường gặp | Kiểm tra |
| --- | --- | --- |
| HTTP **401** hoặc **403** khi gọi B không có token | B đang yêu cầu xác thực — có thể đúng thiết kế | Xác minh endpoint và chính sách; không mở public chỉ để hết lỗi. |
| **401/403** dù A có gửi token | Audience sai, token hết hạn/không hợp lệ, account A thiếu Invoker | So URL `aud`, runtime service account của A và IAM policy trên B. |
| **403** với token hợp lệ nhưng B có `ingress=internal` | Traffic không qua đường mạng được Cloud Run nhận diện là internal | Kiểm tra ingress của B và VPC egress/routing của A; token không vượt qua kiểm tra mạng. |
| **403** khi deploy A với service account mới | Deployer thiếu `iam.serviceAccounts.actAs` hoặc thiếu quyền deploy | Cấp `roles/iam.serviceAccountUser` trên đúng runtime SA, cộng quyền deploy phù hợp. |
| Token lấy từ metadata không được | Chạy từ laptop/Cloud Shell, thiếu header, runtime environment lỗi | Metadata endpoint ví dụ chỉ hoạt động **bên trong Cloud Run/Compute environment phù hợp**. |
| A dùng OAuth access token nhưng B kỳ vọng ID token | Nhầm luồng gọi Google APIs với private Cloud Run | Dùng Google-signed ID token có audience của B. |
| B trả **404/405** sau khi đã xác thực | Sai path hoặc method; container B không hỗ trợ endpoint | Kiểm tra route/path, HTTP method và app logs của B. |
| A trả **502/504** sau khi gọi B | Upstream timeout, DNS, TLS, quota, service B lỗi hoặc app A chuyển lỗi | Đọc cả log A/B; đối chiếu network, retry và backend health. |
| Request tới traffic tag bị từ chối | Token đặt `aud` thành URL tag thay vì URL service gốc | Lấy URL chuẩn của B để tạo token, giữ tag URL là endpoint request. |
| Gọi trực tiếp B thành công từ một tài khoản lạ | IAM policy cấp quá rộng, `allUsers` hoặc Invoker IAM check bị tắt | Kiểm tra IAM binding và service security settings ngay. |
| A thành công nhưng dữ liệu người dùng bị lộ | B dựa duy nhất vào danh tính A, không xác thực người dùng/tenant | Thêm authorization ở tầng nghiệp vụ; xem lại thiết kế confused deputy. |

Không thể phân biệt chắc chắn nguyên nhân chỉ từ một HTTP status. Phải đối chiếu **mã lỗi, đường request, policy IAM, ingress, audience, trạng thái service và logs**; lỗi bị chặn trước container có thể không xuất hiện trong log ứng dụng.

### 6.2. Kiểm tra danh tính và IAM theo thứ tự

Những lệnh chỉ đọc:

~~~bash
gcloud config get-value project

# Xác nhận service A đang gắn service account nào
gcloud run services describe "$CALLER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(spec.template.spec.serviceAccountName,status.url)"

# Xem identity mà B cho phép invoke
gcloud run services get-iam-policy "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION"

# Xác nhận URL đúng cho audience
gcloud run services describe "$TARGET" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url)"
~~~

Một số phiên bản công cụ hiển thị đường YAML khác nhau; nếu trường rỗng, dùng `gcloud run services describe "$CALLER" --format=yaml` rồi tìm runtime service account theo output thực tế. Không chia sẻ toàn bộ cấu hình chứa environment variables/secrets ra kênh không được phân quyền.

### 6.3. Đọc request logs và tương quan hai service

Ví dụ Cloud Logging Query Language cho lỗi request của A:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api-lab"
httpRequest.status>=400
~~~

Tương tự, thay `orders-api-lab` thành tên của B để tìm log request đã tới service B và được Logging ghi nhận. Nếu không thấy log B, **không suy B chưa từng nhận request**: có thể request bị IAM/ingress chặn trước container, phạm vi log/retention không đúng hoặc truy vấn quá hẹp.

Trong ứng dụng, nên ghi **request ID / trace ID**, tên service, revision, status và latency, nhưng tuyệt đối không ghi `Authorization`, `X-Serverless-Authorization`, ID token hoặc bí mật trong payload. Cloud Audit Logs có thể giúp truy nguyên những thay đổi IAM/deployment, không thay thế request logs để đo độ trễ.

### 6.4. Cross-project và nhiều môi trường

Nếu A thuộc project X còn B thuộc project Y, **IAM binding trên B** vẫn phải chỉ định đúng service account của A và tuân thủ organization policies. Nếu runtime identity của A lại là service account **ở project khác với A**, cấu hình gắn service account cross-project có thêm điều kiện đối với Cloud Run service agent và chính sách tổ chức; không suy chỉ có `roles/iam.serviceAccountUser` là đủ.

Tách danh tính **dev/staging/prod**, không cấp một service account quyền Invoker lên tất cả production services. Khi sử dụng nhiều region hoặc VPC Service Controls, còn phải xét đường egress, chính sách ingress, quota, latency và data residency.

## 7. Thiết kế production: tối thiểu quyền và dễ vận hành

Một thiết kế A → B an toàn nên được kiểm tra từ **hạ tầng đến nghiệp vụ**:

| Lớp | Quyết định nên có |
| --- | --- |
| **Danh tính** | Mỗi workload có runtime service account riêng; không dùng chung khóa JSON hoặc default account được cấp quyền rộng. |
| **IAM** | Chỉ SA của A được Invoker **trên B**; service account B chỉ nhận quyền tới những tài nguyên nó cần. |
| **Triển khai** | CI/CD có quyền deploy và `actAs` trên đúng service account; không cấp Token Creator/Owner không cần thiết. |
| **Ingress** | Chọn `internal` khi đường VPC/routing được cấu hình, hoặc một ingress khác phù hợp; không nhầm ingress với IAM. |
| **Token** | OIDC ID token được cấp từ môi trường, audience URL B, có hạn dùng; không log, không lưu dài hạn. |
| **HTTP** | TLS, timeout, retry/backoff có giới hạn, idempotency cho tác vụ ghi và bảo vệ khỏi confused deputy. |
| **Quan sát** | Request/trace ID, 401/403/5xx, latency p99, IAM/deployment audit, cảnh báo theo SLO. |
| **Độ tin cậy** | Quota, concurrency, khả năng autoscale, tránh cascade failure, cân nhắc queue cho việc async. |
| **Chi phí** | Tính cả lượt request Cloud Run, CPU, network theo tuyến, Cloud Tasks (nếu dùng) và Logging. |

**Quy tắc phân quyền thực dụng:** một service cần gọi ba service đích chỉ nên có ba binding Invoker tại ba service đó, không tự động trở thành Cloud Run Admin trên project. Khi một service bị xóa hoặc đổi chức năng, rà soát và thu hồi những binding không còn cần.

## 8. Bài tập và câu hỏi kiểm tra

### Tình huống A — Sai audience dù có quyền

`orders-api` có service account `orders-caller` và đã được cấp Invoker trên `inventory-api`. Nhưng code A gọi `https://inventory.example.com/check` và tạo token với `aud=https://inventory.example.com/check`. B trả 401/403.

**Yêu cầu:** xác định lỗi, đề xuất thay đổi mà không mở public B.

**Đáp án định hướng:** lấy URL chuẩn `run.app` của **B**, đặt làm audience của ID token; endpoint request có thể chứa path hoặc custom domain nếu ingress/routing hỗ trợ. Nếu phải dùng audience tùy chỉnh, cấu hình **custom audience hợp lệ tại B**. Không cấp thêm Admin/Owner vì lỗi này không phải thiếu đặc quyền.

### Tình huống B — A được Invoker nhưng B đặt internal ingress

Hai Cloud Run services ở cùng project. A dùng đúng ID token và IAM nhưng request B vẫn bị chặn. B dùng `ingress=internal`; A chưa có cấu hình VPC egress/routing.

**Yêu cầu:** giải thích hai kiểm tra độc lập và đề xuất hướng xử lý.

**Đáp án định hướng:** IAM xác minh danh tính/quyền, còn ingress xác minh đường mạng. Cấu hình **Direct VPC egress hoặc connector** và routing phù hợp (ví dụ all-traffic với Private Google Access hoặc đường nội bộ được hỗ trợ), rồi kiểm tra lại. Không biến B thành public chỉ để bỏ qua việc thiết kế mạng.

### Tình huống C — Một service account dùng chung

Đội vận hành gắn cùng một service account có role Editor toàn project cho `payments`, `inventory` và `email`, sau đó cấp Invoker trên tất cả các service. Một lỗ hổng ở `email` có thể được dùng để gọi API thanh toán.

**Yêu cầu:** thiết kế lại theo quyền tối thiểu.

**Đáp án định hướng:** tạo runtime service account riêng theo workload/môi trường, chỉ cấp Invoker trên service thật sự cần, tách quyền database/bucket/secret, rà soát quyền deployer `actAs` và bỏ quyền Editor không cần. Bổ sung xác thực/phân quyền nghiệp vụ ở payments để tránh confused deputy.

### Bài tập ứng dụng

Vẽ sơ đồ **Frontend → Orders → Inventory**, trong đó chỉ Frontend gọi Orders và chỉ Orders gọi Inventory. Hãy lập bảng gồm: **service**, **runtime SA**, **IAM Invoker trên đích**, **ingress**, **ID token audience** và **kiểm thử âm tính**. Trả lời thêm: nếu Orders dùng Cloud Tasks gọi Inventory không đồng bộ, **service account nào** phải được Invoker trên Inventory và ai cần quyền `actAs` khi tạo task?

### Câu hỏi tự kiểm tra

1. **Runtime identity của Cloud Run là gì?** — Service account được gắn với service/revision để code dùng khi truy cập Google Cloud hoặc lấy ID token.
2. **Cấp Invoker ở A hay B?** — Cấp trên **B** cho principal là runtime service account của A.
3. **Deployer cần quyền gì để gắn runtime SA?** — `iam.serviceAccounts.actAs`, thường từ `roles/iam.serviceAccountUser`, cộng quyền deploy Cloud Run.
4. **Có cần service account JSON key trong A không?** — Không; dùng metadata server/Google Auth library và identity gắn với service.
5. **`aud` khi gọi `B/path` là gì?** — URL gốc của B hoặc custom audience đã được cấu hình, không phải path.
6. **Hai header đều có token thì Cloud Run dùng header nào?** — `X-Serverless-Authorization` được ưu tiên.
7. **`ingress=internal` có thay IAM không?** — Không. Đây là hai lớp kiểm soát khác nhau.
8. **Bên nhận đã xác thực A thì có cần kiểm tra quyền người dùng không?** — Có, nếu nghiệp vụ phụ thuộc danh tính/quyền người dùng.
9. **Token gcloud của developer có nên dùng trong production không?** — Không; dùng ID token audience-bound của runtime service identity.
10. **Một request timeout sau POST có nên retry vô điều kiện không?** — Không; cần idempotency, giới hạn retry và đánh giá kết quả có thể đã hoàn tất.

## 9. Tài liệu chính thức

- [Cloud Run — Authenticating service-to-service](https://cloud.google.com/run/docs/authenticating/service-to-service): ID token, audience, headers và các phương pháp lấy token.
- [Cloud Run — Introduction to service identity](https://cloud.google.com/run/docs/securing/service-identity): service identity, metadata server và credential.
- [Cloud Run — Configure service identity](https://cloud.google.com/run/docs/configuring/services/service-identity): runtime service account và quyền `iam.serviceAccounts.actAs`.
- [Cloud Run — Access control with IAM](https://cloud.google.com/run/docs/securing/managing-access): Invoker role, yêu cầu xác thực và policy.
- [Cloud Run — Restrict ingress](https://cloud.google.com/run/docs/securing/ingress): `all`, `internal`, `internal-and-cloud-load-balancing`.
- [Cloud Run — Private networking](https://cloud.google.com/run/docs/securing/private-networking): yêu cầu VPC routing giữa các Cloud Run services dùng internal ingress.
- [Cloud Run — Troubleshooting](https://cloud.google.com/run/docs/troubleshooting): chẩn đoán 401/403, IAM, service configuration và request lỗi.
- [Cloud Tasks — Create HTTP tasks](https://cloud.google.com/tasks/docs/create-tasks): OIDC service account, audience và retry với HTTP target.
- [gcloud tasks create-http-task](https://cloud.google.com/sdk/gcloud/reference/tasks/create-http-task): cú pháp flag OIDC.

**Ghi nhớ:** luồng an toàn A → B có ba điều kiện độc lập: **A chạy dưới đúng service identity**, **A gửi Google-signed ID token có audience của B**, và **B cho phép principal của A qua IAM trong một đường ingress hợp lệ**. Ứng dụng vẫn phải tự bảo vệ dữ liệu nghiệp vụ. Khi các bước này được tách rõ, bạn có thể điều tra lỗi chính xác mà không phải mở rộng quyền hoặc công khai service ngoài ý muốn.
