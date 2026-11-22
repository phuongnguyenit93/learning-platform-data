# OAuth 2.0, access token và ID token khi gọi dịch vụ GCP

> **Chương:** IAM và xác thực  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi một ứng dụng Java cần đọc đối tượng trong Cloud Storage, gửi thông điệp đến Pub/Sub hoặc gọi một Cloud Run service nội bộ, nó phải chứng minh **ai đang gọi**, và dịch vụ nhận phải xác định **người gọi được làm gì**. Hai loại token rất dễ bị nhầm là **OAuth 2.0 access token** và **OpenID Connect (OIDC) ID token**. Cả hai có thể được gửi bằng HTTP header **Authorization: Bearer ...**, nhưng **mục đích, cách lấy và nơi sử dụng khác nhau**.

Bài này giải thích các khái niệm và hướng dẫn lựa chọn token cho các tình huống Google Cloud thực tế. Nguyên tắc xuyên suốt là: **lấy đúng loại token cho đúng dịch vụ đích, dùng danh tính có quyền tối thiểu, giữ token trong thời gian ngắn và không đưa bí mật vào mã nguồn hoặc log**.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **authentication** (xác thực danh tính), **authorization** (phân quyền), **OAuth 2.0**, **OIDC** và **IAM**.
2. Giải thích các thuộc tính quan trọng của access token và ID token, bao gồm **scope**, **audience (aud)**, **issuer (iss)** và **expiration (exp)**.
3. Chọn **access token** khi gọi Google Cloud APIs và **ID token** khi gọi những dịch vụ yêu cầu OIDC ID token, đặc biệt là Cloud Run có bật yêu cầu xác thực.
4. Hiểu vai trò của **Application Default Credentials (ADC)**, tài khoản người dùng, service account, metadata server, service account impersonation và Workload Identity Federation.
5. Thực hành xác thực từ **gcloud CLI**, **cURL** và **Java**, đồng thời tránh dùng khóa service account dài hạn khi có giải pháp an toàn hơn.
6. Chẩn đoán các lỗi HTTP 401/403 liên quan token, audience, scope, IAM và cấu hình dịch vụ đích.

## 1. Xác thực, phân quyền và mô hình gọi dịch vụ

Ba khái niệm sau có quan hệ nhưng không đồng nghĩa:

- **Authentication (xác thực):** xác định danh tính của người hoặc workload gửi yêu cầu, ví dụ một service account chạy trên Cloud Run.
- **Authorization (phân quyền):** kiểm tra danh tính vừa được xác thực có quyền thực hiện hành động cụ thể không, ví dụ đọc object hoặc gọi một endpoint riêng tư.
- **IAM (Identity and Access Management):** hệ thống quản trị chính sách vai trò/quyền đối với nhiều tài nguyên Google Cloud. Principal, role, resource và điều kiện chính sách quyết định việc truy cập được chấp nhận hay từ chối.

Ví dụ, một service account đã được Google xác thực không mặc nhiên được phép đọc mọi bucket. Dịch vụ còn đánh giá quyền như **storage.objects.get** ở tài nguyên đích theo IAM và các điều kiện liên quan.

~~~mermaid
sequenceDiagram
    participant C as Client / Workload
    participant I as Google identity/token service
    participant API as Google Cloud API
    C->>I: Xin token bằng danh tính được tin cậy
    I-->>C: Token ngắn hạn
    C->>API: Authorization: Bearer TOKEN
    API->>API: Xác thực token và principal
    API->>API: Kiểm tra quyền/scope/policy tương ứng
    API-->>C: Kết quả hoặc lỗi truy cập
~~~

**Có token hợp lệ chưa chắc có quyền.** Token có thể chứng minh danh tính, trong khi quyết định truy cập còn phụ thuộc IAM, policy, thiết lập API, phạm vi tài nguyên, mạng hoặc ứng dụng đích.

### 1.1. Các chủ thể thường gặp trong Google Cloud

| Principal / thành phần | Ví dụ | Vai trò trong truy cập |
|---|---|---|
| **User account** | Nhân viên đăng nhập Google Cloud CLI | Đại diện người dùng và các quyền người dùng đã được cấp |
| **Service account** | checkout-runtime@PROJECT_ID.iam.gserviceaccount.com | Danh tính của workload, pipeline hoặc tích hợp |
| **Workload identity / federated principal** | Workload từ GKE, GitHub Actions hoặc môi trường ngoài Google Cloud | Dùng danh tính liên kết để lấy quyền truy cập mà không phát khóa lâu hạn |
| **Resource server** | Cloud Storage API, Pub/Sub API, Cloud Run | Nhận request và đánh giá token cùng chính sách truy cập |
| **Token issuer / authorization server** | Dịch vụ Google phát hành access token hoặc ID token | Cấp token khi luồng xác thực đáp ứng điều kiện |

Trước khi viết code, hãy ghi rõ: **người gọi là ai, cần gọi endpoint nào, endpoint chấp nhận loại token nào, audience/scope nào, và quyền IAM nào phải được cấp?**

## 2. OAuth 2.0 và OpenID Connect giải quyết hai việc khác nhau

**OAuth 2.0** là một bộ cơ chế ủy quyền: client có thể nhận **access token** để truy cập tài nguyên/API theo những quyền được cho phép, có thể dưới danh nghĩa người dùng hoặc workload tùy luồng. OAuth 2.0 định nghĩa các vai trò như resource owner, client, authorization server và resource server, cùng nhiều luồng cấp quyền.

**OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính trên nền OAuth 2.0; một thành phần cốt lõi là **ID token**, thường là JWT đã ký, chứa các claim về chủ thể và ứng dụng/dịch vụ đích. ID token giúp bên nhận xác minh danh tính theo cách được thiết kế cho trường hợp đó.

| Câu hỏi | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Mục tiêu chính | Cấp quyền client truy cập tài nguyên/API | Xác thực danh tính và cung cấp thông tin về phiên đăng nhập/chủ thể |
| Token điển hình | Access token | ID token, thường cùng access token trong luồng OIDC |
| Bên nhận | Resource server / API chấp nhận token đó | Relying party / dịch vụ được chỉ định ở claim **aud** |
| Điều kiện quan trọng | Scope và kiểm tra quyền tại API; với Google Cloud còn có IAM | Chữ ký, issuer, audience, thời hạn, các claim/bước kiểm tra liên quan |
| Sai lầm phổ biến | Nghĩ có scope là vượt qua mọi IAM | Dùng ID token thay access token để gọi Google Cloud REST API |

**“OAuth token” là cách nói chưa đủ rõ.** Khi gọi API, hãy luôn xác định cụ thể cần **access token** hay **ID token**. Một luồng OIDC có thể cấp cả hai, nhưng chúng không thay thế nhau.

### 2.1. “Bearer token” chỉ là cách mang token

HTTP header thông dụng:

~~~http
GET /resource HTTP/1.1
Host: example.googleapis.com
Authorization: Bearer TOKEN_VALUE
~~~

Từ **Bearer** nghĩa là bên sở hữu token có thể trình token theo cơ chế bearer. Nó không cho biết token là access token, ID token hay loại token khác. Vì bearer token có thể bị sử dụng nếu lộ, cần bảo vệ như thông tin đăng nhập tạm thời:

- Luôn dùng HTTPS tới endpoint bên ngoài.
- Không ghi token vào log, ticket, ảnh chụp màn hình hoặc hệ thống theo dõi lỗi.
- Không đặt token trong URL/query string nếu có thể dùng header.
- Tránh lưu token ở nơi mọi người dùng hoặc quy trình khác có thể đọc.
- Để thư viện/nguồn credential phù hợp xử lý refresh và hết hạn.

## 3. Access token: thông thường để gọi Google Cloud APIs

**Access token** dùng để ủy quyền lời gọi đến Google APIs, chẳng hạn:

- **Cloud Resource Manager API:** đọc thông tin project.
- **Cloud Storage JSON API:** đọc metadata hoặc object, nếu caller có quyền.
- **Pub/Sub API:** publish hoặc pull message theo quyền được cấp.
- **Secret Manager API:** truy xuất phiên bản secret theo quyền.
- **Compute Engine API:** đọc/thay đổi máy ảo theo IAM, scope và các ràng buộc thích hợp.

Access token có thể đại diện cho **người dùng**, **service account** hoặc loại principal federated được hỗ trợ. Google phát hành nhiều loại access token; **không nên giả định tất cả đều là JWT có thể giải mã bằng dấu chấm**, hoặc tất cả đều có cùng độ dài và lifetime. Client nên xem token như chuỗi opaque, trừ khi tài liệu token cụ thể yêu cầu cách xử lý khác.

### 3.1. Scope và IAM có quan hệ thế nào?

**OAuth scope** giới hạn kiểu truy cập API mà token có thể yêu cầu; ví dụ scope phổ biến của Google Cloud:

~~~text
https://www.googleapis.com/auth/cloud-platform
~~~

Scope **cloud-platform** cho phép token được sử dụng với nhiều Google Cloud APIs về mặt scope, nhưng **không tự trao vai trò IAM**. Một service account có scope rộng nhưng không có **storage.objects.get** trên bucket sẽ không đọc được object đó. Ngược lại, service account có role phù hợp nhưng token bị giới hạn ở scope không chấp nhận cho API đích vẫn có thể bị từ chối.

Ở một số môi trường Compute Engine/GKE, cấu hình **access scopes** của workload cũng có thể ảnh hưởng access token. Trong các thiết kế hiện đại, nên kiểm soát quyền bằng **IAM tối thiểu** và dùng cấu hình scope phù hợp với API, thay vì coi scope là hàng rào bảo mật duy nhất.

~~~mermaid
flowchart LR
    T["Access token hợp lệ"] --> S{"Scope phù hợp?"}
    S -- "Không" --> E1["API từ chối"]
    S -- "Có" --> I{"Principal có IAM permission?"}
    I -- "Không" --> E2["API từ chối"]
    I -- "Có" --> P{"Các điều kiện, policy và API khác?"}
    P -- "Không đạt" --> E3["Từ chối"]
    P -- "Đạt" --> OK["Cho phép thao tác"]
~~~

Sơ đồ là mô hình khái niệm: thứ tự và mã lỗi cụ thể do từng API quyết định.

### 3.2. Ví dụ gọi Cloud Resource Manager REST API bằng access token

Trong máy phát triển đã cài Google Cloud CLI và đăng nhập bằng tài khoản được phép:

~~~bash
# Xác minh tài khoản CLI và project cấu hình, không tiết lộ token.
gcloud auth list
gcloud config list project

# PROJECT_ID là project được phép xem.
PROJECT_ID="my-learning-project"

# Access token thuộc danh tính đang đăng nhập gcloud CLI.
# Không bật shell tracing (-x) và không in token ra màn hình.
ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://cloudresourcemanager.googleapis.com/v3/projects/$PROJECT_ID"

# Xóa biến tạm trong phiên shell khi không còn dùng.
unset ACCESS_TOKEN
~~~

Điều kiện: Cloud Resource Manager API khả dụng, tài khoản có quyền **resourcemanager.projects.get** trên project và các điều kiện cần thiết của môi trường được đáp ứng. Nếu quyền thiếu, token vẫn có thể hợp lệ nhưng API từ chối request.

**Chú ý:** access token lấy từ lệnh trên dành cho **Google API**, không được coi là ID token hợp lệ để gọi Cloud Run service yêu cầu xác thực OIDC.

### 3.3. Hết hạn và refresh access token

Access token thường tồn tại ngắn (nhiều luồng khoảng một giờ; giới hạn cụ thể phụ thuộc loại token và cơ chế cấp). Ứng dụng chạy lâu phải:

1. Lấy token từ thư viện xác thực hoặc nguồn credential đáng tin cậy.
2. Theo dõi hoặc để thư viện xử lý thời điểm hết hạn.
3. Yêu cầu token mới khi cần, thay vì giữ giá trị cố định trong biến môi trường lâu ngày.
4. Không đăng xuất/sửa file credential của workload trong khi tác vụ đang chạy nếu chưa hiểu ảnh hưởng.

**Refresh token** là loại credential khác, có thể dùng trong một số luồng OAuth người dùng để xin access token mới. Nó có yêu cầu bảo vệ nghiêm ngặt; **không nên đồng nhất refresh token với access token**. Workload chạy bằng service account gắn vào môi trường Google Cloud thường lấy token ngắn hạn từ hạ tầng, không cần tự quản một refresh token người dùng.

## 4. ID token: chứng minh danh tính cho dịch vụ đích cụ thể

**ID token** trong các luồng OpenID Connect thường là **JWT** có chữ ký. Phần payload chứa claims. Ví dụ minh họa (đã lược bỏ các trường và không phải token thật):

~~~json
{
  "iss": "https://accounts.google.com",
  "sub": "109876543210987654321",
  "aud": "https://orders-api-abcdef-uc.a.run.app",
  "iat": 1790000000,
  "exp": 1790003600,
  "email": "caller@my-learning-project.iam.gserviceaccount.com"
}
~~~

Các claim đáng chú ý:

| Claim | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **iss** | Issuer phát hành token | So với các issuer hợp lệ mà dịch vụ hỗ trợ |
| **sub** | Định danh ổn định của principal trong ngữ cảnh issuer | Hữu ích để nhận biết chủ thể; không suy danh tính chỉ từ email |
| **aud** | Audience — dịch vụ/ứng dụng đích | Phải khớp audience dịch vụ mong đợi, hoặc cấu hình custom audience được hỗ trợ |
| **iat** | Thời điểm phát hành | Hỗ trợ kiểm tra tính hợp lệ theo thời gian |
| **exp** | Thời điểm hết hạn | Từ chối token đã hết hạn; xem xét sai lệch đồng hồ cho phép |
| **email / email_verified** | Thông tin tùy loại token và cách phát hành | Không phải mọi ID token đều có; không dựa duy nhất vào email để kiểm tra quyền |

Đây là **mẫu payload để đọc khái niệm**, không phải một mẫu JWT đầy đủ hay cam kết mọi loại ID token đều có cùng issuer/claims. ID token do hệ thống đăng nhập người dùng phát hành có audience là **OAuth client ID**, trong khi Google-signed ID token dùng gọi Cloud Run có thể dùng **URL dịch vụ** làm audience. Cần xác định rõ nguồn phát hành và bên nhận.

### 4.1. Mục đích của audience

Audience trả lời: **“Token này được cấp để gửi đến dịch vụ nào?”** Ví dụ cùng một service account gọi hai API nội bộ:

~~~text
Cloud Run service A: https://orders-api-abcdef-uc.a.run.app
Cloud Run service B: https://billing-api-abcdef-uc.a.run.app
~~~

ID token được tạo cho audience A **không nên được dịch vụ B chấp nhận** như token dành cho B. Kiểm tra audience hạn chế việc mang token từ hệ thống này sang hệ thống khác.

Khi gọi Cloud Run có yêu cầu xác thực, thông thường **aud** là URL gốc của receiving service (run.app URL) hoặc **custom audience** đã cấu hình trong Cloud Run. Không đưa path, query hoặc URL traffic tag vào audience mặc định. Nếu gọi qua custom domain, **không tự dùng custom domain làm audience**; cần cấu hình custom audience khi phù hợp.

### 4.2. Kiểm tra chữ ký ID token

Việc tách ba phần JWT và Base64URL-decode payload **không xác minh chữ ký**. Một dịch vụ tự kiểm tra ID token phải dùng thư viện OIDC/JWT uy tín để xác minh:

- Chữ ký với khóa công khai của issuer đáng tin.
- Issuer, audience, thời gian hết hạn và những claim bắt buộc.
- Thuật toán ký nằm trong tập được chấp nhận, không tin vào thuật toán do token tự đề xuất.
- Các ràng buộc nghiệp vụ khác: tenant/domain, quyền ứng dụng hoặc danh tính đã được cấp phép.

Với Cloud Run có bật IAM authentication, **nền tảng Cloud Run kiểm tra ID token và IAM của lời gọi vào service** trước khi request đến container. Nếu API trong container còn có phân quyền nghiệp vụ (ví dụ người dùng chỉ đọc được hóa đơn của chính họ), ứng dụng vẫn phải xác minh và áp dụng chính sách tương ứng. **IAM Invoker không tự thực hiện phân quyền nghiệp vụ bên trong ứng dụng.**

## 5. Bảng lựa chọn nhanh: gọi loại endpoint nào, cần token gì?

| Lời gọi | Token thường sử dụng | Điều kiện nhận request |
|---|---|---|
| Đọc project qua Cloud Resource Manager REST API | **Access token** | Scope/API phù hợp, principal có quyền đọc project |
| Đọc object qua Cloud Storage API | **Access token** | Quyền IAM/object cần thiết và ràng buộc bucket liên quan |
| Publish message tới Pub/Sub REST API | **Access token** | Quyền publish trên topic và cấu hình API liên quan |
| Truy xuất Secret Manager API | **Access token** | Quyền truy cập secret version, policy phù hợp |
| Gọi Cloud Run service riêng tư | **Google-signed OIDC ID token** | **aud** hợp lệ, caller có quyền Cloud Run Invoker và các điều kiện dịch vụ |
| Gọi HTTP endpoint do Cloud Tasks/Scheduler kích hoạt | **ID token** nếu đích là Cloud Run riêng tư và cấu hình OIDC | Tài khoản và audience/role của tác vụ phải đúng |
| Đăng nhập website bằng Google Sign-In/OIDC | **ID token** cho relying party (ứng dụng đăng nhập) | Audience là client ID ứng dụng, kiểm tra issuer/chữ ký/claims |
| Gọi Google APIs thay mặt người dùng sau OAuth consent | **User access token** | Người dùng cấp scope phù hợp và principal có các quyền liên quan |
| Gọi endpoint công khai không yêu cầu auth | Có thể không cần token | Vẫn có thể có bảo vệ ở lớp ứng dụng hoặc API gateway |

**Không thể thay access token bằng ID token chỉ vì cả hai được gửi trong header Authorization.** Quy tắc được quyết định bởi **tài liệu dịch vụ đích**, không phải hình thức chuỗi token.

## 6. Gọi Cloud Run riêng tư bằng ID token: ví dụ đầy đủ

Bối cảnh:

- **order-api** chạy trên Cloud Run, yêu cầu xác thực.
- **payment-worker** là ứng dụng gọi service đó, chạy bằng service account **worker-caller@PROJECT_ID.iam.gserviceaccount.com**.
- Đích cần cấp quyền **roles/run.invoker** cho service account người gọi trên đúng Cloud Run service.
- Khi phát request, worker phải gửi **ID token Google-signed** có **aud** là URL gốc của service nhận hoặc một custom audience hợp lệ.

~~~mermaid
sequenceDiagram
    participant W as payment-worker (service account)
    participant M as Metadata server / Identity service
    participant R as Cloud Run order-api
    W->>M: Xin ID token với aud=URL order-api
    M-->>W: Google-signed ID token
    W->>R: HTTPS Authorization: Bearer ID_TOKEN
    R->>R: Kiểm tra token: iss/aud/exp
    R->>R: Kiểm tra IAM Cloud Run Invoker
    alt Hợp lệ và có quyền
      R-->>W: 2xx hoặc kết quả từ ứng dụng
    else Token sai/thiếu hoặc không đủ quyền
      R-->>W: 401/403 tùy trường hợp
    end
~~~

### 6.1. Cấp quyền Invoker (thao tác của quản trị viên)

~~~bash
# Chỉ thực hiện bởi người có quyền sửa IAM của service.
PROJECT_ID="my-learning-project"
REGION="us-central1"
RECEIVER_SERVICE="order-api"
CALLER_SA="worker-caller@my-learning-project.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "$RECEIVER_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"
~~~

**Vai trò này được gắn cho caller ở service nhận**, không phải gắn trên Cloud Run service đang gọi. Quyền IAM của người **triển khai** workload cũng khác quyền của service account **runtime**.

Một service account có quyền Invoker trên service A **không mặc nhiên có quyền** trên service B.

### 6.2. Gọi thử từ máy phát triển bằng impersonation

Giả sử người dùng đã đăng nhập gcloud, được phép **impersonate** service account caller và chính caller có quyền Invoker:

~~~bash
# Trong môi trường bash, thay bằng URL Cloud Run thật.
TARGET_URL="https://order-api-abcdef-uc.a.run.app"
CALLER_SA="worker-caller@my-learning-project.iam.gserviceaccount.com"

# Phát hành ID token cho đúng audience của service nhận.
ID_TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account="$CALLER_SA" \
  --audiences="$TARGET_URL")"

# Chỉ gửi qua HTTPS; không echo token hoặc lưu vào log.
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ID_TOKEN" \
  "$TARGET_URL/health"

unset ID_TOKEN
~~~

Đây là một **lời gọi thật**; nếu endpoint health không tồn tại, có thể nhận 404 từ ứng dụng dù xác thực và IAM đã vượt qua. Cần thay URL/path bằng endpoint được cấp phép để kiểm thử.

**Lưu ý:** lệnh **gcloud auth print-identity-token** khi dùng trực tiếp với thông tin đăng nhập người dùng có thể tạo **generic ID token** dành cho thử nghiệm Cloud Run và Cloud Run functions. Không nên coi đó là ID token production để dùng với một ứng dụng bất kỳ. Ví dụ trên dùng **service account impersonation** để đặt rõ audience, và vẫn cần quyền tạo token thích hợp trên service account.

### 6.3. Gọi từ Cloud Run bằng metadata server

Trong Cloud Run, khi code chạy với service account runtime được cấu hình, nền tảng cung cấp metadata server để lấy token ngắn hạn. Nếu không dùng auth library, có thể yêu cầu ID token theo audience:

~~~bash
# Chạy bên trong một workload Google Cloud hỗ trợ metadata server.
# Đây không phải lệnh để chạy từ laptop thông thường.
TARGET_AUDIENCE="https://order-api-abcdef-uc.a.run.app"

ID_TOKEN="$(curl --fail-with-body --silent --show-error \
  -H "Metadata-Flavor: Google" \
  --get \
  --data-urlencode "audience=$TARGET_AUDIENCE" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity")"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ID_TOKEN" \
  "$TARGET_AUDIENCE/health"

unset ID_TOKEN
~~~

Metadata server được truy cập qua HTTP **trong môi trường nội bộ được hỗ trợ** và yêu cầu header **Metadata-Flavor: Google**. Không mở endpoint metadata ra Internet, không chuyển tiếp phản hồi cho client bên ngoài và cần bảo vệ ứng dụng khỏi các lỗ hổng như SSRF có thể dẫn tới truy cập metadata.

Trong code production, nên dùng **Google authentication libraries** để lấy và refresh token, thay vì tự lắp ghép curl hoặc tự quản cache.

### 6.4. Một header thay thế khi ứng dụng đã dùng Authorization

Cloud Run hỗ trợ một header khác cho ID token:

~~~http
X-Serverless-Authorization: Bearer ID_TOKEN
~~~

Header này hữu ích khi container cần dành **Authorization** cho cơ chế xác thực nghiệp vụ của ứng dụng. Nếu cả hai header đều có, Cloud Run ưu tiên **X-Serverless-Authorization** khi kiểm tra yêu cầu đầu vào. Không nên dùng header này như một quy tắc chung cho mọi Google API; nó là hành vi được Cloud Run hỗ trợ.

## 7. Application Default Credentials (ADC): cách ứng dụng tìm credential

**Application Default Credentials** là chiến lược để thư viện Google Cloud tự tìm nguồn credential phù hợp môi trường, giúp code giống nhau có thể chạy trên máy phát triển, Compute Engine, Cloud Run, GKE hoặc môi trường federated.

ADC tìm theo thứ tự ưu tiên:

1. Đường dẫn được chỉ định trong biến **GOOGLE_APPLICATION_CREDENTIALS**.
2. Tệp credential ADC tạo bởi **gcloud auth application-default login** trên máy phát triển.
3. Service account gắn với workload, được môi trường hỗ trợ cung cấp qua **metadata server**.

~~~mermaid
flowchart TD
    C["Google Cloud client/auth library"] --> E{"Có GOOGLE_APPLICATION_CREDENTIALS?"}
    E -- "Có" --> F["Đọc credential config ở đường dẫn đó"]
    E -- "Không" --> L{"Có local ADC file?"}
    L -- "Có" --> U["Dùng local ADC"]
    L -- "Không" --> M["Dùng attached identity / metadata server nếu hỗ trợ"]
    F --> T["Tạo/refresh token phù hợp"]
    U --> T
    M --> T
    T --> API["Gọi Google Cloud API / lấy ID token đúng audience"]
~~~

**Thứ tự tìm kiếm không phải xếp hạng độ an toàn.** Dùng một file key dài hạn ở bước 1 thường rủi ro hơn dùng attached service account ở bước 3, dù ADC kiểm tra biến môi trường trước.

### 7.1. gcloud credentials khác local ADC

Hai lệnh dễ bị nhầm:

~~~bash
# Xác thực cho các lệnh gcloud CLI.
gcloud auth login

# Thiết lập Application Default Credentials để thư viện
# Google Cloud trong code sử dụng trên máy phát triển.
gcloud auth application-default login
~~~

Hai cơ chế có thể dùng tài khoản khác nhau và lưu credential riêng. Vì vậy:

- **gcloud projects list** chạy thành công không chứng minh code Java dùng ADC đang có quyền tương tự.
- Thay đổi tài khoản đang hoạt động trong gcloud CLI không nhất thiết đổi tài khoản ADC.
- Token lấy bằng **gcloud auth print-access-token** có thể khác token do code dùng ADC sinh ra.
- Khi cần thử nghiệm cùng service account, cân nhắc **service account impersonation** cho CLI và ADC theo hướng dẫn Google Cloud, với quyền rõ ràng.

Để xác định nguyên nhân một lỗi quyền, cần xem **danh tính thực tế của credential đang dùng**, thay vì chỉ xem tên project trong cấu hình.

### 7.2. Danh tính runtime được khuyến nghị

| Môi trường | Nguồn credential nên cân nhắc | Lý do |
|---|---|---|
| Laptop của lập trình viên | Local ADC người dùng hoặc ADC impersonate service account | Tách môi trường cá nhân khỏi danh tính runtime |
| Cloud Run | Service account riêng gắn cho Cloud Run service | Tự lấy token ngắn hạn qua nền tảng |
| Compute Engine | Attached service account và quyền IAM phù hợp | Tránh chứa private key trên VM |
| GKE | **Workload Identity Federation for GKE** | Gắn quyền theo workload/Kubernetes ServiceAccount, hạn chế cấp quyền rộng cho node |
| CI/CD bên ngoài (GitHub Actions, v.v.) | **Workload Identity Federation** | Dùng danh tính của hệ thống ngoài, đổi lấy credential ngắn hạn |
| Tổ chức dùng IdP bên ngoài cho nhân viên | **Workforce Identity Federation** theo kiến trúc tổ chức | Liên kết danh tính người dùng từ IdP được hỗ trợ |

**Workload Identity Federation** và **Workforce Identity Federation** phục vụ nhóm principal khác nhau (workload và workforce). Khi thiết kế quyền IAM, phải xác định loại federation, trust configuration, principal mapping, service account impersonation nếu có và phạm vi audience.

### 7.3. Không dùng service account key nếu không cần

Tệp JSON private key của service account là credential dài hạn có thể bị sao chép. Nếu lộ, kẻ tấn công có thể dùng nó mà không cần truy cập môi trường gốc, cho đến khi khóa bị vô hiệu hóa hoặc bị giới hạn bởi kiểm soát khác.

Ưu tiên theo tình huống:

1. **Attached service account** với Cloud Run/Compute Engine.
2. **Workload Identity Federation for GKE** đối với pod.
3. **Workload Identity Federation** đối với runner ngoài Google Cloud.
4. **Service account impersonation** cho tác vụ được ủy quyền cần danh tính service account.
5. Chỉ dùng **service account key** nếu thực sự không có lựa chọn phù hợp, có phê duyệt, bảo vệ, giám sát, xoay vòng và thu hồi khóa.

Một tệp **external account credential configuration** dùng Workload Identity Federation không giống private key service account. Không suy đoán rằng mọi tệp JSON được đặt trong **GOOGLE_APPLICATION_CREDENTIALS** đều là “key”.

## 8. Service account impersonation và quyền tạo token

**Impersonation** cho phép một principal đã xác thực xin credential ngắn hạn để hành động với danh tính của service account khác. Có **hai danh tính**: người thực hiện impersonation và service account được impersonate.

Ví dụ: tài khoản dev chỉ được phép tạo token ngắn hạn cho **staging-caller@...**, còn service account staging-caller có quyền đọc một bucket test. Dev không cần trực tiếp có quyền đọc bucket trên user account của mình; thao tác được ủy quyền qua service account.

~~~mermaid
flowchart LR
    U["Developer / CI principal"] -->|"Được cấp quyền tạo token"| SA["Service account"]
    SA -->|"Được cấp IAM trên đích"| R["Bucket / API / Cloud Run service"]
    U -. "Xin token ngắn hạn" .-> T["IAM Credentials API"]
    T -. "Token cho service account" .-> U
    U -->|"Gọi với token"| R
~~~

**Quyền tạo token và quyền dùng token là hai bước khác nhau:**

| Bước | Yêu cầu |
|---|---|
| Gọi **generateAccessToken** | Principal có quyền **iam.serviceAccounts.getAccessToken** trên service account; vai trò thường dùng là **roles/iam.serviceAccountTokenCreator** |
| Gọi **generateIdToken** | Principal có quyền **iam.serviceAccounts.getOpenIdToken**; có vai trò chuyên biệt **roles/iam.serviceAccountOpenIdTokenCreator** |
| Dùng access token gọi Google API | Service account được impersonate phải có quyền IAM/API cần thiết |
| Dùng ID token gọi Cloud Run | Service account được impersonate cần **roles/run.invoker** trên receiving service, audience phải hợp lệ |

Tài khoản có **Project Owner** chưa chắc có quyền tạo token của service account nếu IAM trên service account không cho phép. Ngược lại, cấp quyền **Token Creator** quá rộng có thể tạo đường leo thang đặc quyền. Cần giới hạn phạm vi và kiểm toán hoạt động impersonation.

Ví dụ CLI dùng quyền impersonation để nhận access token ngắn hạn:

~~~bash
# Không hiển thị token công khai; dùng trong phiên làm việc được kiểm soát.
TARGET_SA="staging-caller@my-learning-project.iam.gserviceaccount.com"

ACCESS_TOKEN="$(gcloud auth print-access-token \
  --impersonate-service-account="$TARGET_SA")"

# Dùng ACCESS_TOKEN với endpoint Google Cloud API được phép.
# Sau khi sử dụng, xóa biến.
unset ACCESS_TOKEN
~~~

## 9. Workload Identity Federation: xác thực bên ngoài Google Cloud

Một pipeline chạy trên GitHub Actions, AWS, Azure hoặc một nền tảng tự vận hành có thể có **OIDC token của hệ thống nguồn**. Không nên mặc định mang OIDC token đó gọi thẳng Google Cloud REST API.

Luồng tổng quát:

1. Workload chứng minh danh tính với **IdP bên ngoài** được Google Cloud trust.
2. Workload nhận assertion/token từ IdP.
3. **Security Token Service (STS)** của Google Cloud kiểm tra cấu hình federation và đổi assertion thành credential federated ngắn hạn.
4. Workload dùng federated credential trực tiếp ở dịch vụ có hỗ trợ hoặc impersonate service account theo cấu hình.
5. Credential Google Cloud thích hợp được dùng gọi Google APIs, hoặc xin Google-signed ID token cho service đích như Cloud Run.

~~~mermaid
sequenceDiagram
    participant CI as External CI workload
    participant IdP as External OIDC/SAML IdP
    participant STS as Google STS
    participant IAM as IAM Credentials (nếu impersonate)
    participant GCP as Google Cloud API / Cloud Run
    CI->>IdP: Lấy assertion về workload
    IdP-->>CI: Assertion
    CI->>STS: Đổi assertion theo federation config
    STS-->>CI: Federated credential
    opt Cần service account impersonation
      CI->>IAM: Xin token cho service account
      IAM-->>CI: Access token hoặc Google-signed ID token phù hợp
    end
    CI->>GCP: Gọi với token đúng loại
    GCP-->>CI: Kết quả theo IAM và policy
~~~

**Không phải mọi federated token đều được mọi dịch vụ chấp nhận theo cùng một cách.** Kiểm tra dịch vụ đích, kiểu principal được hỗ trợ và liệu cần thêm bước impersonation hay không.

Riêng **Workload Identity Federation for GKE**, các thành phần như GKE metadata server có thể thay mặt workload trao đổi Kubernetes ServiceAccount token để nhận credential Google Cloud. Ứng dụng nên dùng ADC/client libraries; không cần tự tạo khóa JSON cho từng pod.

## 10. OAuth 2.0 cho người dùng và OIDC đăng nhập ứng dụng

Không phải mọi tình huống gọi GCP đều là machine-to-machine. Một ứng dụng có thể cần:

- Người dùng đăng nhập với Google và nhận diện người dùng đó.
- Người dùng cho phép ứng dụng đọc một tài nguyên Google mà họ sở hữu.
- Backend dùng service account riêng để xử lý công việc nội bộ.

Đây là các luồng khác nhau.

### 10.1. Authorization code flow với PKCE

Trong ứng dụng web/mobile, luồng OAuth hiện đại thường dùng **authorization code** và **PKCE** khi phù hợp, để không để lộ thông tin bí mật của client và giảm nguy cơ đánh cắp authorization code.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant App as Ứng dụng
    participant Google as Google Authorization Server
    U->>App: Đăng nhập / cấp quyền
    App->>Google: Redirect kèm state, code_challenge, scope
    Google->>U: Xác thực và consent khi cần
    U-->>Google: Chấp nhận/từ chối
    Google-->>App: Authorization code về redirect URI
    App->>Google: Đổi code + code_verifier
    Google-->>App: Access token (+ ID token nếu OIDC; refresh token khi đủ điều kiện)
    App->>App: Xác minh ID token; quản lý session
~~~

Các thuộc tính quan trọng:

- **state** chống request giả mạo/liên kết sai phiên; cần xác minh khi nhận redirect.
- **PKCE** bảo vệ quá trình đổi authorization code.
- **redirect URI** phải hợp lệ và khớp cấu hình ứng dụng.
- **scope** phải nhỏ nhất phục vụ chức năng; không xin quyền rộng vô cớ.
- **ID token** dùng xác thực người dùng theo OIDC; **access token** dùng gọi API chấp nhận token đó.
- **refresh token** (nếu được phát hành) phải được bảo vệ cẩn thận, nhất là trên backend.

Một Google ID token từ đăng nhập website thường có **aud = OAuth client ID của website**. Không dùng nó làm token gọi Cloud Run riêng tư chỉ vì cả hai đều là JWT. Cloud Run IAM authentication có quy tắc issuer/audience/quyền riêng.

### 10.2. Service account không thay thế ủy quyền người dùng

Service account là danh tính của **ứng dụng/workload**. Nếu yêu cầu “người dùng A chỉ được xem đơn hàng A”, việc backend gọi Cloud SQL bằng một service account có quyền đọc cơ sở dữ liệu **không tự tạo phân quyền nghiệp vụ theo người dùng A**. Backend cần session/user identity và kiểm tra quyền tại lớp ứng dụng.

Tương tự, nếu ứng dụng cần hành động thay mặt người dùng trên một API yêu cầu OAuth consent của người dùng, không thể chỉ đổi sang service account mà bỏ qua mô hình ủy quyền dành cho người dùng. Một số cơ chế đặc thù như domain-wide delegation có điều kiện quản trị riêng và không phải lựa chọn mặc định.

## 11. Thực hành trong Java: tách hai loại token

Vì module học có nhiều tình huống ứng dụng Java chạy trên GCP, phần này minh họa hai mẫu code. Dùng **Google Auth Library for Java** (module chứa các lớp thuộc package **com.google.auth.oauth2**) và các thư viện HTTP phù hợp dự án. Cần lấy version ổn định được dự án quản lý và kiểm tra API của version đang dùng.

### 11.1. Access token qua ADC cho Google APIs

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import java.io.IOException;
import java.util.List;

public final class AccessTokenExample {
    public static String getTokenForGoogleApis() throws IOException {
        GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();

        if (credentials.createScopedRequired()) {
            credentials = credentials.createScoped(
                List.of("https://www.googleapis.com/auth/cloud-platform")
            );
        }

        credentials.refreshIfExpired();
        return credentials.getAccessToken().getTokenValue();
    }
}
~~~

Ví dụ cho thấy access token có thể lấy từ ADC theo cấu hình môi trường. Trong ứng dụng thực tế, **ưu tiên Google Cloud client library** cho từng dịch vụ, vì thư viện thường tự gắn access token và refresh; không cần chuyển token thành chuỗi trong code nghiệp vụ. Nếu bắt buộc gọi REST thủ công, chỉ dùng chuỗi token trong request HTTPS, không log.

### 11.2. ID token cho Cloud Run private service từ ADC

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import java.io.IOException;

public final class IdTokenExample {
    public static String getIdTokenForCloudRun(String audience)
            throws IOException {
        GoogleCredentials base = GoogleCredentials.getApplicationDefault();

        if (!(base instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "ADC hiện tại không hỗ trợ cấp ID token trực tiếp; " +
                "hãy dùng attached service account hoặc cơ chế " +
                "impersonation/ID token provider được hỗ trợ."
            );
        }

        IdTokenCredentials idCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) base)
                .setTargetAudience(audience)
                .build();

        idCredentials.refreshIfExpired();
        return idCredentials.getIdToken().getTokenValue();
    }
}
~~~

Gọi như sau trong một môi trường **có nguồn credential hỗ trợ ID token**:

~~~java
String cloudRunUrl = "https://order-api-abcdef-uc.a.run.app";
String token = IdTokenExample.getIdTokenForCloudRun(cloudRunUrl);

// HTTP client thực hiện GET/POST tới endpoint hợp lệ, ví dụ /health:
// Header: Authorization: Bearer <token>
// Không log token. Nên để auth-aware HTTP client xử lý refresh/token.
~~~

**Giới hạn quan trọng:** local ADC tạo từ tài khoản người dùng thông thường không nhất thiết triển khai **IdTokenProvider**. Code trên cố ý báo lỗi rõ ràng trong trường hợp đó, thay vì giả định mọi ADC đều có khả năng cấp ID token Cloud Run. Service account runtime hoặc impersonated identity hỗ trợ là những hướng thường dùng; cần xác minh hỗ trợ theo loại credential và version library.

### 11.3. Không đưa token vào các đối tượng tồn tại lâu

Một service Java chạy nhiều giờ không nên lấy token ở lúc khởi động rồi lưu **static final String TOKEN** để sử dụng vô thời hạn. Token sẽ hết hạn. Thay vào đó:

- Giữ đối tượng credential/client được thư viện quản lý.
- Để thư viện tự refresh hoặc yêu cầu token mới khi cần.
- Dùng HTTP client có tính năng tạo authenticated request.
- Thiết lập timeout/retry có giới hạn và không retry vô hạn khi gặp 401/403.
- Không xuất token qua exception message, trace hoặc diagnostics.

## 12. Quản lý IAM khi kết hợp nhiều dịch vụ GCP

Một backend thương mại điện tử thường gọi nhiều loại đích:

~~~mermaid
flowchart TD
    P["Cloud Run: checkout-api\nService account: checkout-runtime"] -->|"ID token, aud=URL"| R["Cloud Run: fraud-service riêng tư"]
    P -->|"Access token / ADC"| S["Secret Manager API"]
    P -->|"Access token / ADC"| PUB["Pub/Sub API"]
    P -->|"Connector/database auth tương ứng"| DB["Cloud SQL"]
    IAM["IAM policy theo tài nguyên"] -. "run.invoker" .-> R
    IAM -. "secretmanager.versions.access" .-> S
    IAM -. "pubsub.topics.publish" .-> PUB
~~~

### 12.1. Ma trận quyền minh họa

| Caller | Đích | Token | Quyền cần xác định |
|---|---|---|---|
| checkout-runtime | fraud-service Cloud Run riêng tư | Google-signed ID token | **roles/run.invoker** trên fraud-service |
| checkout-runtime | Secret Manager secret | Access token (qua ADC) | Vai trò tối thiểu có **secretmanager.versions.access** trên secret |
| checkout-runtime | Pub/Sub topic | Access token (qua ADC) | Vai trò tối thiểu có **pubsub.topics.publish** trên topic |
| CI release | Cloud Run deployment API | Access token cho Google APIs | Quyền triển khai Cloud Run/Artifact Registry và quyền dùng runtime service account phù hợp |
| reporting-job | Cloud Storage bucket báo cáo | Access token (qua ADC) | Quyền đọc/ghi object theo đúng nhu cầu |
| người dùng website | checkout backend | Theo cơ chế phiên/JWT ứng dụng đã thiết kế | Xác thực và quyền nghiệp vụ tại backend |

Trong trường hợp Cloud SQL, phương thức kết nối có thể liên quan IP riêng, connector/Cloud SQL Auth Proxy, IAM database authentication hoặc thông tin đăng nhập database, tùy kiến trúc. Không suy rằng access token của Google API luôn là mật khẩu đăng nhập trực tiếp của mọi engine SQL.

### 12.2. Chọn runtime service account riêng

Nên tạo service account riêng cho những workload có phạm vi quyền khác nhau, ví dụ:

- **checkout-runtime**: publish một topic và đọc một secret.
- **fraud-runtime**: chỉ đọc dataset cần thiết.
- **reporting-job**: chỉ ghi bucket báo cáo.
- **ci-deployer**: triển khai vào môi trường đã chỉ định.

Nếu tất cả workload dùng cùng một service account có quyền rộng trên toàn project, một lỗ hổng ở một container có thể ảnh hưởng nhiều dịch vụ. Giảm quyền và tách danh tính giúp giới hạn phạm vi tác động và cải thiện audit log.

## 13. Khắc phục sự cố 401, 403 và lỗi xác thực

HTTP 401 thường liên quan **thiếu/không hợp lệ token**, còn 403 thường liên quan **thiếu quyền hoặc chính sách từ chối**. Tuy nhiên cách trả mã HTTP và nội dung lỗi phụ thuộc lớp gateway, sản phẩm và ứng dụng; cần đọc log đích và mã lỗi chi tiết.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra an toàn |
|---|---|---|
| Cloud Run 401 khi gọi service riêng tư | Không có ID token, sai audience, token hết hạn, issuer/signature không hợp lệ | Xác định loại token, URL gốc service và audience mong đợi |
| Cloud Run 403 | Caller không có Invoker, chính sách IAM/ingress chặn | Kiểm tra principal, binding và policy trên service đích |
| Google REST API báo thiếu scope | Access token bị giới hạn ở scope không phù hợp | Xác minh nguồn credential và scope của token bằng công cụ bảo mật phù hợp |
| Google REST API 403 dù có access token | Principal thiếu quyền IAM hoặc bị policy/API/quota ràng buộc | Kiểm tra tài nguyên, permission cụ thể, API enabled, quota |
| Code Java 403 nhưng gcloud CLI thành công | **gcloud auth login** và **ADC** dùng hai identity khác nhau | Kiểm tra nguồn ADC, quota project và IAM của principal runtime |
| Lỗi khi lấy ID token từ ADC trên laptop | User ADC không cung cấp IdTokenProvider phù hợp | Dùng service account impersonation hoặc môi trường runtime hỗ trợ |
| Metadata server không truy cập được | Đang chạy ngoài Google Cloud hoặc cấu hình khác | Xác định môi trường, header Metadata-Flavor và endpoint được hỗ trợ |
| Lỗi token sau khoảng một giờ | Cache token hết hạn, thiếu refresh | Để auth library quản lý hoặc xin token mới |
| Gọi Cloud Run qua custom domain bị 401 | **aud** không khớp URL mặc định/custom audience hợp lệ | Kiểm tra cấu hình audience của service, không đoán bằng URL của request |
| Access token bị leak trong pipeline | Lệnh echo, set -x, log headers hoặc lưu artifact | Thu hồi/giảm rủi ro credential, chỉnh log và chuyển sang token ngắn hạn |
| Lỗi quyền khi impersonate service account | Thiếu **getAccessToken/getOpenIdToken** trên service account đích | Kiểm tra policy của service account và vai trò token creator |
| Kết nối VPC riêng tư lỗi | DNS, route, firewall, ingress hoặc private endpoint | Tách lỗi mạng ra khỏi lỗi token/IAM |

### 13.1. Quy trình điều tra theo thứ tự

1. **Xác định endpoint**: Google Cloud API, Cloud Run riêng tư, IAP hay ứng dụng tự quản xác thực?
2. **Xác định token được yêu cầu**: access token hay Google-signed ID token, có dùng audience cụ thể không?
3. **Xác định principal thực tế**: user ADC, attached service account, federated principal hay impersonated service account?
4. **Kiểm tra freshness**: token có hết hạn không? Có clock skew và cơ chế refresh thích hợp không?
5. **Kiểm tra scope/audience**: scope áp dụng cho Google APIs; aud áp dụng cho ID token ở dịch vụ đích.
6. **Kiểm tra IAM và policy**: principal có quyền ở **tài nguyên đúng** không? Có điều kiện hoặc deny policy không?
7. **Kiểm tra môi trường**: API enabled, quota, region, DNS, VPC, ingress, dịch vụ đang chạy?
8. **Đối chiếu log an toàn**: Cloud Audit Logs và log ứng dụng ở mức metadata/error code; tuyệt đối không yêu cầu người khác gửi giá trị token.

**Không dùng token decoder trên website không đáng tin** hoặc dán token production vào ticket công khai. Có thể đọc header/payload JWT trong một công cụ kiểm soát nội bộ để chẩn đoán, nhưng đọc payload **không thay việc xác minh chữ ký**, và bản thân token vẫn là bí mật.

### 13.2. Hai lỗi đặc biệt phổ biến

**Sai loại token:** một developer có access token từ gcloud rồi gửi tới Cloud Run có yêu cầu IAM authentication. Cloud Run mong Google-signed ID token với audience phù hợp. Giải pháp là lấy ID token đúng cách, không phải tăng quyền IAM một cách mù quáng.

**Sai danh tính:** CLI gọi API thành công dưới user có quyền Editor, còn ứng dụng Cloud Run chạy bằng service account ít quyền. Giải pháp là cấp **quyền vừa đủ cho runtime service account** trên tài nguyên cần truy cập, không phải sao chép credential của developer vào container.

## 14. Thiết kế bảo mật token và khả năng vận hành

### 14.1. Threat model ngắn

Giả định một container xử lý HTTP request có lỗ hổng **SSRF**. Nếu ứng dụng cho phép client bất kỳ truy cập metadata server, kẻ xấu có thể cố lấy token đại diện service account runtime và gọi những API mà service account đó có quyền.

Để giảm nguy cơ:

- Xử lý và giới hạn URL đích khi ứng dụng tải tài nguyên từ ngoài.
- Không cho untrusted input tùy ý điều khiển request tới địa chỉ nội bộ/metadata.
- Tách danh tính workload và chỉ cấp IAM đúng tài nguyên.
- Dùng token ngắn hạn do môi trường cấp, không thêm khóa dài hạn vào container.
- Theo dõi hành động bất thường và sử dụng audit log để điều tra.
- Cập nhật thư viện và triển khai kiểm tra bảo mật trong pipeline.

Token ngắn hạn **không loại bỏ** nguy cơ nếu service account bị cấp quyền quá rộng hoặc ứng dụng liên tục có khả năng xin token mới. Quyền tối thiểu và ranh giới mạng vẫn rất quan trọng.

### 14.2. Tự động hóa phát hành an toàn

Trong CI/CD, pipeline deploy Cloud Run hoặc GKE cần phân biệt:

- **Build identity:** quyền đọc mã nguồn, tải dependency và đẩy artifact.
- **Deploy identity:** quyền thay đổi tài nguyên triển khai, sử dụng service account runtime khi phù hợp.
- **Runtime identity:** quyền gọi APIs và các dịch vụ khác trong lúc ứng dụng chạy.

Không nên dùng một service account Owner cho cả ba giai đoạn. Pipeline bên ngoài GCP nên cân nhắc **Workload Identity Federation** với trust policy hạn chế theo repo, branch hoặc workflow, rồi cấp quyền triển khai có điều kiện phù hợp.

### 14.3. Quan sát và chi phí

Các lỗi 401/403 làm tăng request thất bại, thời gian xử lý retry và đôi khi tăng chi phí gọi dịch vụ. Khi vận hành, theo dõi:

- Tỷ lệ request lỗi theo endpoint và mã HTTP.
- Số lần thất bại xác thực / permission denied từ log có thể thu thập.
- Latency khi lấy credential nếu có nhiều lần refresh không cần thiết.
- Các lần impersonation bất thường trên service account nhạy cảm.
- Tác động tới SLO của người dùng, đặc biệt trong luồng Cloud Run → Cloud Run → database.

Không log token để tiện debug. Một log tốt chỉ cần timestamp, service, loại lỗi, request ID, principal nếu log hệ thống cung cấp an toàn và tài nguyên đích. Lưu giữ log cũng cần cân nhắc quyền truy cập và chi phí Cloud Logging.

## 15. Case study: Cloud Run xử lý đơn hàng và gọi dịch vụ kiểm tra gian lận

**Yêu cầu:** hệ thống thương mại điện tử có **checkout-api** nhận đơn hàng, cần gọi **fraud-checker** nội bộ để đánh giá rủi ro, sau đó ghi sự kiện vào Pub/Sub và truy xuất API Secret Manager khi cần. Hai service đều chạy trong project production nhưng có service account riêng.

### 15.1. Chọn token

| Hành động | Danh tính | Token | IAM cần có |
|---|---|---|---|
| checkout-api gọi fraud-checker | checkout-runtime | **ID token**, aud=URL fraud-checker | Invoker trên fraud-checker |
| checkout-api publish Pub/Sub | checkout-runtime | **Access token/ADC** | Pub/Sub Publisher trên topic đích |
| checkout-api đọc Secret Manager | checkout-runtime | **Access token/ADC** | Secret Manager Secret Accessor trên secret cần dùng |
| fraud-checker đọc dữ liệu riêng | fraud-runtime | Access token/ADC hoặc cơ chế truy cập dịch vụ tương ứng | Quyền tối thiểu trên dữ liệu |
| CI phát hành phiên bản checkout-api | ci-deployer | Access token cho Google APIs | Quyền deploy và dùng runtime service account trong phạm vi cần thiết |

### 15.2. Luồng triển khai

1. Tạo service account **checkout-runtime** cho service gọi và **fraud-runtime** cho service nhận.
2. Chạy **checkout-api** với checkout-runtime.
3. Cấu hình **fraud-checker** yêu cầu xác thực và cấp **roles/run.invoker** cho checkout-runtime trên fraud-checker.
4. Trong checkout-api, lấy ID token có **aud** bằng URL gốc fraud-checker qua client library/metadata service phù hợp.
5. Gửi request HTTPS tới fraud-checker, kiểm tra mã phản hồi và timeout.
6. Dùng **ADC** để publish Pub/Sub hoặc gọi Secret Manager; cấp các IAM role riêng với phạm vi topic/secret cần thiết.
7. Theo dõi độ trễ, lỗi 401/403, retry và audit log; không log token.
8. Khi xoay vòng danh tính hoặc chuyển môi trường, cập nhật binding và cấu hình audience đúng dịch vụ đích.

**Biến thể gây lỗi:** sau khi đổi URL Cloud Run để phân luồng traffic, client thay **aud** bằng URL traffic tag. Dịch vụ có thể từ chối token. Cần giữ audience là service URL được Cloud Run chấp nhận hoặc custom audience đã cấu hình. Phần path/traffic tag của request và audience không nhất thiết giống nhau.

### 15.3. Bài học kiến trúc

Sử dụng hai loại token trong **cùng một ứng dụng** là bình thường: ID token cho một Cloud Run service riêng tư, access token cho Google APIs. Mỗi call có resource server, quyền và audience/scope riêng. Điều quan trọng là chọn **identity và token theo từng ranh giới truy cập**, không lưu một token chung cho toàn hệ thống.

## 16. Bài thực hành có kiểm soát

Các bài thực hành dưới đây chỉ cần một project/dev environment đã được cấp. Không yêu cầu mở quyền public, tải service account key hoặc thay đổi IAM production.

### 16.1. Phần A — Sơ đồ quyền cho ba lời gọi

Đề bài: ứng dụng Java chạy trên Cloud Run cần:

1. Đọc project metadata bằng Cloud Resource Manager API.
2. Gọi Cloud Run service **inventory-api** đang yêu cầu xác thực.
3. Ghi object vào Cloud Storage bucket báo cáo.

Hãy điền:

| Đích | Token nên dùng | Kiểm tra IAM tối thiểu | Audience / scope |
|---|---|---|---|
| Resource Manager | … | … | … |
| inventory-api | … | … | … |
| Cloud Storage | … | … | … |

**Gợi ý:** Resource Manager và Cloud Storage cần access token; inventory-api cần Google-signed ID token với **aud** đúng receiving service. Quyền IAM tương ứng phải tồn tại trên project, Cloud Run service và bucket.

### 16.2. Phần B — Kiểm tra môi trường local

~~~bash
# Chỉ hiển thị thông tin cấu hình, không in token.
gcloud auth list
gcloud config list
gcloud config get-value project

# Nếu chưa có ADC cho môi trường học và được phép đăng nhập:
# gcloud auth application-default login

# Có thể kiểm tra quyền ở project dev bằng thao tác đọc:
gcloud projects describe YOUR_PROJECT_ID
~~~

Giải thích vì sao **gcloud projects describe** thành công không bảo đảm một chương trình Java dùng ADC có quyền tương ứng.

### 16.3. Phần C — Đọc mã lỗi

Ba sự kiện giả định:

- **Sự kiện 1:** Cloud Run trả 401, log cho thấy client gửi access token thay vì ID token.
- **Sự kiện 2:** Caller gửi Google-signed ID token đúng audience, nhưng Cloud Run trả 403.
- **Sự kiện 3:** Java client gọi Secret Manager thất bại, trong khi cùng người dùng chạy gcloud CLI đọc project thành công.

Với mỗi sự kiện, hãy xác định **loại token, danh tính, quyền và nguồn credential** cần kiểm tra. Không chọn giải pháp mặc định là cấp Owner hoặc bật public access.

**Đáp án định hướng:**

- (1) Tạo ID token đúng audience; Cloud Run IAM authentication cần đúng loại token.
- (2) Kiểm tra principal và vai trò Invoker/điều kiện truy cập của service.
- (3) Kiểm tra ADC của Java khác CLI, principal runtime có quyền secret version cần thiết hay không; quyền đọc project không đồng nghĩa quyền đọc secret.

## 17. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “OAuth 2.0 là một loại token.” | OAuth 2.0 là cơ chế ủy quyền với nhiều luồng và loại credential/token liên quan. |
| “Access token và ID token đều là Bearer nên dùng thay nhau được.” | Header có thể giống, nhưng dịch vụ đích kỳ vọng loại token cụ thể. |
| “ID token JWT decode được là hợp lệ.” | Phải xác minh chữ ký và các claim bắt buộc; decode chỉ đọc dữ liệu. |
| “Có access token cloud-platform scope là đủ mọi quyền.” | IAM và các chính sách khác vẫn quyết định quyền. |
| “Có roles/run.invoker thì có thể gọi service mà không cần ID token.” | Cloud Run riêng tư cần lời gọi được xác thực hợp lệ, gồm token và điều kiện liên quan. |
| “Đăng nhập gcloud CLI thì ADC của Java cũng là tài khoản đó.” | Credential CLI và ADC được quản lý riêng. |
| “Dùng service account cần tải khóa JSON.” | Attached identity, federation và impersonation thường giảm rủi ro hơn. |
| “ID token user từ Google Sign-In dùng gọi mọi Cloud Run service.” | Token đăng nhập của website có audience/issuer và cơ chế kiểm tra khác. |
| “Đổi URL request thì phải đổi aud theo nguyên cả path.” | Audience Cloud Run mặc định là URL gốc của service hoặc custom audience hợp lệ. |
| “Token hết hạn chỉ cần retry HTTP mãi.” | Phải refresh token đúng cơ chế và giới hạn retry. |
| “Có quyền lấy token nghĩa là có quyền gọi mọi API.” | Service account được impersonate còn cần quyền thực tế tại API đích. |
| “Authentication xong là đã phân quyền nghiệp vụ.” | Ứng dụng vẫn phải áp dụng quyền người dùng lên dữ liệu/nghiệp vụ. |

## 18. Tài liệu tham khảo chính thức

Có thể kiểm tra tài liệu Google Cloud để theo dõi thay đổi API, cơ chế định danh và các khuyến nghị bảo mật:

- [Google Cloud Authentication — Token types](https://docs.cloud.google.com/docs/authentication/token-types)
- [Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [Cloud Run — Authenticate service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Application Default Credentials — How it works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Authenticate using REST](https://docs.cloud.google.com/docs/authentication/rest)
- [Service account impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [gcloud auth print-identity-token reference](https://docs.cloud.google.com/sdk/gcloud/reference/auth/print-identity-token)

Quyền, loại token, flow và khả năng của thư viện có thể thay đổi theo dịch vụ/phiên bản. Khi triển khai thực tế, hãy kiểm tra tài liệu đúng với phiên bản SDK và đặc điểm endpoint đang gọi.

---

**Ghi nhớ:** Với **Google Cloud REST APIs** như Storage, Pub/Sub, Secret Manager hoặc Resource Manager, thường cần **OAuth 2.0 access token** cùng quyền IAM phù hợp. Với **Cloud Run service riêng tư**, thường cần **Google-signed OIDC ID token** có **audience đúng receiving service**, đồng thời caller phải có **Cloud Run Invoker**. **ADC, attached service account và Workload Identity Federation** giúp ứng dụng lấy/đổi token ngắn hạn mà không phải quản lý private key lâu dài. Đây là nền tảng để xây dựng các hệ thống Compute Engine, GKE, Cloud Run và dữ liệu an toàn, tự động hóa được, dễ giám sát và kiểm soát chi phí.

