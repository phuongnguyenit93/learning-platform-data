# Dự án website tĩnh có Cloud Storage, HTTPS và CDN

Một website giới thiệu sản phẩm, tài liệu hướng dẫn, trang sự kiện hoặc giao diện frontend đã được build thành HTML, CSS và JavaScript thường không cần một máy chủ Java chạy liên tục để gửi các tệp đó đến trình duyệt. Google Cloud cho phép đặt tệp tĩnh trong **Cloud Storage**, dùng **Application Load Balancer** để phục vụ một tên miền qua **HTTPS**, và bật **Cloud CDN** để phân phối nội dung từ các điểm lưu đệm gần người dùng.

Dự án này sẽ dẫn bạn xây dựng một website tĩnh nhỏ, triển khai nó vào một Cloud Storage bucket riêng, kết nối với global external Application Load Balancer, cấu hình chứng chỉ TLS do Google quản lý, trỏ DNS và kiểm tra caching, bảo mật, chi phí cũng như quy trình cập nhật. Sau đó, chúng ta bổ sung pipeline Cloud Build để việc phát hành không còn phụ thuộc vào thao tác upload thủ công.

Bài học thuộc chương **Dự án thực hành GCP** của module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; thông qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong dự án này, những khái niệm về IAM, DNS, TLS, caching, CI/CD và FinOps được kết nối thành một hệ thống có thể kiểm thử từ trình duyệt.

> **Lưu ý chi phí và an toàn:** Các lệnh bên dưới là hướng dẫn để bạn chạy trong project lab của chính mình; bài học không tự tạo tài nguyên Google Cloud. Load balancer, IP công cộng, CDN, storage và lưu lượng mạng có thể phát sinh chi phí kể cả khi lượng truy cập rất thấp. Chỉ chạy sau khi chọn đúng project, bật Billing và đặt budget alert. Không lưu credential, dữ liệu nội bộ hay mã nguồn bí mật trong bucket công khai.

## Mục tiêu

Sau khi hoàn thành, bạn có thể:

- Mô tả đường đi từ người truy cập đến DNS, HTTPS load balancer, Cloud CDN và Cloud Storage.
- Tạo website HTML/CSS/JavaScript tĩnh có trang chính, trang phụ và trang lỗi.
- Tạo bucket, upload tệp, đặt content type, cấu hình index/error page và quyền truy cập phù hợp.
- Tạo backend bucket, bật Cloud CDN, cấu hình URL map, external IP và HTTPS frontend.
- Cấp phát chứng chỉ TLS được Google quản lý và trỏ DNS cho tên miền.
- Kiểm thử HTTPS, cache headers, mã trạng thái, bản phát hành và rollback.
- Thiết kế Cache-Control để cân bằng tốc độ tải với khả năng cập nhật.
- Tự động hóa upload bằng Cloud Build với quyền tối thiểu.
- Theo dõi chi phí, logs/metrics và dọn tài nguyên lab an toàn.

## 1. Phạm vi sản phẩm và tiêu chí hoàn thành

Giả sử nhóm cần website giới thiệu dịch vụ tên **GCP Demo Site** với tên miền minh họa **www.example.com**. Tên miền này chỉ là ví dụ, bạn phải sở hữu hoặc được quản lý một tên miền thật để hoàn tất phần DNS và chứng chỉ HTTPS.

**Chức năng tối thiểu:**

1. Trang chủ có tiêu đề, mô tả và liên kết đến trang giới thiệu.
2. Trang giới thiệu truy cập được bằng một đường dẫn tĩnh cụ thể.
3. Có CSS responsive và JavaScript tương tác nhỏ.
4. Trang lỗi tùy chỉnh cho đường dẫn không tồn tại.
5. Nội dung chỉ được phát hành qua miền đã chọn với HTTPS hợp lệ.
6. Cloud CDN được bật trên backend bucket.
7. Có cách phát hành phiên bản mới, kiểm tra cache và phục hồi phiên bản cũ.

**Tiêu chí kỹ thuật:**

| Hạng mục | Điều kiện chấp nhận |
|---|---|
| Storage | Tệp có trong bucket lab đúng project |
| Routing | URL gốc trả trang chính; file tĩnh tải được |
| HTTPS | Certificate ACTIVE/hợp lệ, hostname khớp |
| CDN | Backend bucket đã bật Cloud CDN; cache policy rõ ràng |
| Security | Chỉ chứa dữ liệu công khai; quyền deploy tách khỏi quyền đọc |
| Error handling | Đường dẫn không tồn tại có phản hồi lỗi đúng |
| Release | Thay đổi nội dung đến được người dùng theo chính sách cache |
| Operations | Có test, metrics, budget và quy trình cleanup |

### Ranh giới phạm vi

Cloud Storage **không chạy mã Java/Spring Boot, PHP hoặc xử lý request động ở phía server**. Website tĩnh có thể chạy JavaScript trong trình duyệt và gọi API động được host riêng trên Cloud Run/GKE/Compute Engine. Nếu ứng dụng cần authentication, session hoặc dữ liệu người dùng riêng tư, hãy thiết kế một backend và authorization riêng thay vì đưa dữ liệu đó vào các tệp tĩnh.

## 2. Kiến trúc mục tiêu

~~~mermaid
flowchart LR
    U["Trình duyệt"] --> DNS["DNS: www.example.com"]
    DNS --> IP["Global external IP"]
    IP --> LB["External Application Load Balancer<br/>HTTPS + Google-managed certificate"]
    LB --> MAP["URL map"]
    MAP --> CDN["Backend bucket<br/>Cloud CDN enabled"]
    CDN --> GCS["Cloud Storage<br/>index.html, CSS, JS, images"]
    CI["Cloud Build<br/>deploy identity"] --> GCS
    MON["Cloud Monitoring / Billing"] -.-> LB
    MON -.-> CDN
~~~

**Diễn giải từng lớp:**

| Thành phần | Trách nhiệm | Có gì cần quản lý? |
|---|---|---|
| DNS | Ánh xạ hostname sang IP của load balancer | A/AAAA/CNAME phù hợp, TTL và quyền quản trị zone |
| Global external IP | Địa chỉ cố định cho frontend | Reserve/release, billing |
| Application Load Balancer | Nhận HTTPS request và định tuyến | Frontend, forwarding rule, TLS proxy, URL map |
| Google-managed TLS certificate | Phục vụ chứng chỉ hợp lệ cho domain | Domain validation, provisioning, renewal và trạng thái |
| Backend bucket | Kết nối URL map với Cloud Storage | Tên backend bucket và policy |
| Cloud CDN | Cache nội dung ở edge theo HTTP semantics | Cache mode, TTL, invalidation và metrics |
| Cloud Storage | Origin lưu HTML/CSS/JS/assets | Object, IAM, metadata, storage location |
| Cloud Build | Tải artifact đã kiểm tra lên bucket | Trigger, build service account, approval |

Cloud Storage có cơ chế cache cho object, nhưng khi bật Cloud CDN ở backend bucket, bạn có thêm các chính sách cache và khả năng invalidation. CDN không làm thay đổi nội dung origin; nó giữ bản sao theo quy tắc caching.

### Vì sao HTTPS cần load balancer?

Cloud Storage có thể phát nội dung qua các Google Storage endpoints, nhưng **website dùng custom domain với HTTPS** cần một giải pháp frontend phù hợp. Trong bài này, Application Load Balancer nhận TLS trên miền của bạn, sau đó lấy tệp từ backend bucket. Chứng chỉ gắn với HTTPS frontend, **không cài vào object Cloud Storage**.

### Phiên bản load balancer

Bài thực hành chọn **global external Application Load Balancer** với load balancing scheme **EXTERNAL_MANAGED**. Google Cloud cũng hỗ trợ classic Application Load Balancer và một số mô hình regional có backend bucket, nhưng lệnh và tham số của các loại khác nhau. Khi thực hành, chọn **một loại** và dùng nhất quán mọi resource tương ứng; không ghép lệnh classic EXTERNAL với forwarding rule EXTERNAL_MANAGED.

## 3. Điều kiện tiên quyết

Bạn cần:

- Một Google Cloud project dùng cho lab, đã liên kết Billing.
- Một tên miền hoặc subdomain mà bạn có quyền sửa bản ghi DNS.
- Google Cloud CLI đã cài, xác thực và chọn project.
- Quyền tạo Cloud Storage bucket/object và cấu hình load balancing/certificate phù hợp.
- Quyền thay đổi DNS tại nhà đăng ký hoặc dịch vụ DNS của tên miền.
- Một thiết bị có trình duyệt, curl và môi trường shell hỗ trợ các lệnh minh họa.

### IAM cần cân nhắc

| Hoạt động | Quyền/role tham khảo | Phạm vi mong muốn |
|---|---|---|
| Tạo bucket và cấu hình website | Quyền quản trị Cloud Storage phù hợp | Chỉ project lab |
| Upload artifact | roles/storage.objectAdmin hoặc quyền tối thiểu tương ứng | Chỉ bucket chứa website |
| Đọc tệp công khai | allUsers với quyền đọc object trong phương án public origin | Chỉ bucket public được phê duyệt |
| Tạo IP/LB/URL map/certificate | Compute Network Admin và các quyền Compute liên quan | Chỉ project lab |
| Xem Monitoring/Billing | Viewer phù hợp của hệ thống quan sát/chi phí | Chỉ tài nguyên có liên quan |

Role cụ thể phụ thuộc tổ chức và quyền đã có. Không cấp Owner/Editor cho build service account chỉ để chạy bước upload. Người tạo load balancer có thể cần quyền khác với người viết nội dung.

### Bật API

Sử dụng một project lab đã được xác nhận:

~~~bash
export PROJECT_ID="your-lab-project-id"
export REGION="asia-southeast1"
export DOMAIN="www.your-owned-domain.example"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID"
~~~

DOMAIN là chỗ điền hostname thực tế có quyền DNS, không dùng nguyên chuỗi *.example để thử cấp chứng chỉ. Chọn location bucket theo vị trí người dùng, residency và chi phí; backend HTTPS ở global load balancer không bắt buộc bucket phải có cùng region với mọi người truy cập.

### Đặt giới hạn chi phí

Trước khi tạo các resource tính phí:

1. Tạo budget cho project lab và cấu hình cảnh báo ở các ngưỡng được chấp thuận.
2. Ghi danh sách IP, forwarding rule, backend bucket và bucket sẽ tạo.
3. Xác định ngày hết hạn lab và người có trách nhiệm cleanup.
4. Giới hạn số lần invalidation và kích thước tệp tải lên.
5. Không tự động load test quy mô lớn lên một site công khai khi chưa đặt giới hạn.

Budget alert **không mặc định dừng phát sinh chi phí**. Với lab, cần vừa theo dõi chi phí vừa thực hiện cleanup chủ động.

## 4. Chuẩn bị mã nguồn website tĩnh

Một cấu trúc đơn giản:

~~~text
static-site/
├── site/
│   ├── index.html
│   ├── about/
│   │   └── index.html
│   ├── 404.html
│   ├── assets/
│   │   ├── style.css
│   │   └── app.js
│   └── images/
│       └── logo.svg
└── cloudbuild.yaml        # Bổ sung ở phần CI/CD
~~~

Ví dụ dùng website HTML tĩnh thuần để tập trung vào GCP. Nếu có React/Vue/Angular, hãy build sản phẩm thành thư mục dist/ trước khi upload; tránh upload node_modules, source maps nhạy cảm, .env chứa secret hoặc tệp source không cần thiết.

### site/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Website tĩnh trên Google Cloud">
  <title>GCP Demo Site</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <header class="container">
    <nav aria-label="Điều hướng chính">
      <a href="/">Trang chủ</a>
      <a href="/about/">Giới thiệu</a>
    </nav>
  </header>
  <main class="container">
    <h1>Xin chào từ Google Cloud</h1>
    <p>Website tĩnh lưu trong Cloud Storage và phân phối qua HTTPS + CDN.</p>
    <button type="button" id="hello-button">Kiểm tra JavaScript</button>
    <p id="message" role="status"></p>
  </main>
  <footer class="container">GCP Demo Site — phiên bản thử nghiệm</footer>
  <script src="/assets/app.js" defer></script>
</body>
</html>
~~~

### site/assets/style.css

~~~css
:root {
  color-scheme: light;
  font-family: system-ui, sans-serif;
  background: #f7f9fc;
  color: #18324a;
}
body {
  margin: 0;
  line-height: 1.6;
}
.container {
  width: min(92%, 960px);
  margin: 0 auto;
  padding: 1.5rem 0;
}
nav {
  display: flex;
  gap: 1rem;
}
a {
  color: #1557b0;
}
button {
  padding: .65rem 1rem;
  border: 1px solid #1557b0;
  border-radius: .4rem;
  background: #fff;
  cursor: pointer;
}
~~~

### site/assets/app.js

~~~javascript
const button = document.querySelector("#hello-button");
const message = document.querySelector("#message");

if (button && message) {
  button.addEventListener("click", () => {
    message.textContent = "JavaScript đã tải thành công qua website tĩnh.";
  });
}
~~~

### site/about/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Giới thiệu — GCP Demo Site</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <main class="container">
    <nav><a href="/">Về trang chủ</a></nav>
    <h1>Giới thiệu</h1>
    <p>Dự án sử dụng Cloud Storage, HTTPS và Cloud CDN.</p>
  </main>
</body>
</html>
~~~

### site/404.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Không tìm thấy trang</title>
</head>
<body>
  <h1>404 — Không tìm thấy trang</h1>
  <p><a href="/">Quay về trang chủ</a></p>
</body>
</html>
~~~

Khi chạy local, dùng một HTTP server đơn giản để kiểm tra đường dẫn và CSS/JS. Ví dụ, nếu có Python trên máy phát triển, có thể chạy http.server phục vụ thư mục site; nhưng đây là lựa chọn cho người thực hành, không phải một bước cần thiết để tạo Cloud Storage hosting.

Với SPA dùng history routing, deep link như /orders/123 có thể không tồn tại dưới dạng object. Cần cấu hình URL rewrite/error fallback hoặc dùng hosting layer hỗ trợ SPA; tránh trả mọi lỗi 404 thành 200 để che các tài nguyên thực sự bị thiếu. Bài này chọn **multipage static HTML** để 404 hoạt động đúng ngữ nghĩa.

## 5. Tạo Cloud Storage bucket và cấu hình website

Cloud Storage bucket name phải duy nhất trên toàn bộ Google Cloud. Hãy chọn tên không chứa dữ liệu nhạy cảm và chỉ dùng cho website thử nghiệm. Trong các lệnh bên dưới, bạn cần thay chuỗi gợi ý bằng một tên còn khả dụng.

### 5.1 Chọn biến cấu hình

~~~bash
export PROJECT_ID="your-lab-project-id"
export REGION="asia-southeast1"
export SITE_BUCKET="your-unique-static-site-bucket"

gcloud config set project "$PROJECT_ID"
echo "Project: $PROJECT_ID"
echo "Bucket:  $SITE_BUCKET"
~~~

Không tiếp tục nếu project là production ngoài dự định. Một bucket có tên chứa từ lab vẫn có thể nằm trong project production; nên xác nhận project qua gcloud và Console.

### 5.2 Tạo bucket

~~~bash
gcloud storage buckets create "gs://$SITE_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

**Uniform bucket-level access (UBLA)** giúp quản lý quyền object thông qua IAM ở cấp bucket thay vì kết hợp nhiều object ACL. Đây là lựa chọn dễ quản lý cho bài thực hành. Nếu bucket đã tồn tại, không chạy lệnh tạo lại; kiểm tra bucket name, location, IAM và owner trước khi tiếp tục.

### 5.3 Upload nội dung

Đứng tại thư mục static-site chứa site/:

~~~bash
gcloud storage rsync --recursive ./site "gs://$SITE_BUCKET"

gcloud storage ls "gs://$SITE_BUCKET"
gcloud storage ls "gs://$SITE_BUCKET/assets/"
~~~

rsync cập nhật các object từ local sang bucket. **Không tự thêm tùy chọn xóa object ở đích** nếu chưa review chính xác danh sách file; có thể đang có bản phát hành hoặc resource khác trong bucket.

Cloud Storage giữ các tệp dưới key tương ứng:

~~~text
gs://BUCKET/index.html
gs://BUCKET/404.html
gs://BUCKET/about/index.html
gs://BUCKET/assets/style.css
gs://BUCKET/assets/app.js
~~~

### 5.4 Kiểm tra MIME types

Content-Type đúng giúp trình duyệt diễn giải dữ liệu chính xác:

| Đuôi | Content-Type thường dùng |
|---|---|
| .html | text/html; charset=utf-8 |
| .css | text/css |
| .js | text/javascript |
| .svg | image/svg+xml |
| .png | image/png |
| .webp | image/webp |

CLI có thể tự nhận loại tệp khi upload, nhưng bạn nên kiểm tra metadata của các object:

~~~bash
gcloud storage objects describe "gs://$SITE_BUCKET/index.html"
gcloud storage objects describe "gs://$SITE_BUCKET/assets/style.css"
gcloud storage objects describe "gs://$SITE_BUCKET/assets/app.js"
~~~

Nếu metadata sai, cập nhật object tương ứng:

~~~bash
gcloud storage objects update \
  "gs://$SITE_BUCKET/index.html" \
  --content-type="text/html; charset=utf-8"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/style.css" \
  --content-type="text/css"
~~~

Không mặc định gán mọi object thành text/html. Khi CSS/JS bị trả về với Content-Type sai và trình duyệt bật MIME sniffing protection, giao diện có thể không tải đúng.

### 5.5 Cấu hình trang chính và trang lỗi

~~~bash
gcloud storage buckets update "gs://$SITE_BUCKET" \
  --web-main-page-suffix=index.html \
  --web-error-page=404.html

gcloud storage buckets describe "gs://$SITE_BUCKET"
~~~

Với website tĩnh, MainPageSuffix giúp xử lý đường dẫn đến thư mục như /about/ bằng file about/index.html khi đường dẫn được website-serving endpoint xử lý đúng. NotFoundPage cho phép hiển thị 404.html khi tệp không tồn tại. Hãy kiểm tra thực tế qua HTTPS load balancer, không chỉ dựa vào metadata.

**Không nhầm các kiểu endpoint:** đường dẫn gs:// dùng cho quản lý object; website endpoint và HTTPS load balancer xử lý request HTTP theo cấu hình tương ứng. Một URL Cloud Storage API trực tiếp không nhất thiết có cùng hành vi redirect/index/error như website hostname.

## 6. Chọn mô hình đọc nội dung: public bucket hay private bucket

Website trong bài này là nội dung công khai, nên một phương án đơn giản là cho phép đọc các object trong **bucket chỉ chứa tài nguyên public**. Google Cloud cũng hỗ trợ mô hình **private bucket access thông qua Cloud Load Balancing và Cloud CDN** với cấu hình riêng, phù hợp khi tổ chức muốn tránh cho người dùng truy cập trực tiếp vào origin.

### Phương án A — Bucket công khai cho nội dung public

Để trình duyệt và edge cache có thể đọc nội dung public theo hướng dẫn đơn giản, gán:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  "gs://$SITE_BUCKET" \
  --member=allUsers \
  --role=roles/storage.objectViewer
~~~

**Cảnh báo bảo mật:** role storage.objectViewer ở cấp bucket cho allUsers cho phép đọc các object và còn có thể cho phép liệt kê object metadata/tên đối tượng. Đây chỉ là phương án phù hợp với **bucket được dành riêng cho tệp hoàn toàn công khai**. Không đặt .env, token, backup, private source, sourcemap chứa dữ liệu nhạy cảm hoặc dữ liệu khách hàng trong bucket này.

Nếu public access prevention (PAP) được enforce trên bucket hoặc qua Organization Policy, việc thêm allUsers có thể bị từ chối. **Không tắt chính sách cấp tổ chức để vượt qua lỗi lab**; yêu cầu quản trị viên cấp một ngoại lệ đúng phạm vi nếu được phê duyệt, hoặc chuyển sang mô hình private bucket access.

### Phương án B — Private origin qua load balancer/CDN

Private bucket access là kiến trúc nâng cao có cơ chế quyền dành cho frontend và backend bucket. Nó cho phép phục vụ nội dung công khai qua load balancer/CDN trong khi ngăn truy cập origin bằng quyền allUsers thông thường. Mô hình này phải được cấu hình theo hướng dẫn riêng cho loại Application Load Balancer và Cloud CDN sử dụng.

Trong phương án này:

- Không cấp allUsers trực tiếp vào bucket.
- Thiết lập private bucket access theo tài liệu chính thức.
- Kiểm tra frontend HTTPS vẫn đọc được object, trong khi truy cập trực tiếp đến origin không được phép.
- Xem lại signed URLs hoặc signed cookies nếu có yêu cầu kiểm soát nội dung không công khai; không coi Cloud CDN caching là cơ chế authentication của ứng dụng.

Để tập trung vào việc học DNS, TLS và cache, các lệnh tiếp theo giả định **phương án A đã được chấp thuận**. Nếu project thuộc tổ chức áp dụng PAP nghiêm ngặt, chọn phương án B thay vì cố tái sử dụng nguyên lệnh allUsers.

## 7. Tạo global external IP và backend bucket

Đến đây, Cloud Storage mới là origin. Chúng ta cần một HTTPS frontend và URL map để website xuất hiện trên hostname đã chọn.

### 7.1 Đặt tên các resource

~~~bash
export IP_NAME="site-global-ip"
export BACKEND_BUCKET="site-backend"
export URL_MAP="site-url-map"
export TLS_CERT="site-managed-cert"
export HTTPS_PROXY="site-https-proxy"
export HTTPS_RULE="site-https-forwarding"

export DOMAIN="www.your-owned-domain.example"
~~~

Hãy đặt tên khác nếu project lab đã có resource cùng tên. Ghi các tên đã dùng vào báo cáo để cleanup đúng những gì bài lab tạo, tránh xóa resource của người khác.

### 7.2 Reserve global static IP

~~~bash
gcloud compute addresses create "$IP_NAME" \
  --network-tier=PREMIUM \
  --ip-version=IPV4 \
  --global \
  --project="$PROJECT_ID"

gcloud compute addresses describe "$IP_NAME" \
  --global \
  --project="$PROJECT_ID" \
  --format="get(address)"
~~~

Lưu kết quả IP vào tài liệu lab. Khi trỏ DNS, sử dụng IP này; không đặt A record đến địa chỉ ngẫu nhiên hoặc địa chỉ IP của Cloud Storage API.

### 7.3 Tạo backend bucket và bật Cloud CDN

~~~bash
gcloud compute backend-buckets create "$BACKEND_BUCKET" \
  --gcs-bucket-name="$SITE_BUCKET" \
  --enable-cdn \
  --project="$PROJECT_ID"

gcloud compute backend-buckets describe "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"
~~~

Backend bucket là tài nguyên của Cloud Load Balancing trỏ tới Cloud Storage bucket; **không** phải một Cloud Storage bucket thứ hai. Khi bật CDN, các response đủ điều kiện được lưu ở edge theo cache policy. Bạn cần xác minh backend bucket hiển thị trạng thái CDN enabled.

### 7.4 Tạo URL map

~~~bash
gcloud compute url-maps create "$URL_MAP" \
  --default-backend-bucket="$BACKEND_BUCKET" \
  --project="$PROJECT_ID"
~~~

URL map chọn backend dựa trên hostname và đường dẫn. Với một website duy nhất, default backend bucket là đủ. Khi cần thêm một API động chạy trên Cloud Run, có thể bổ sung backend service/serverless NEG và host/path rules phù hợp; bài này chưa cần cấu hình đó.

## 8. HTTPS frontend và chứng chỉ TLS

### 8.1 Cấp phát Google-managed certificate

~~~bash
gcloud compute ssl-certificates create "$TLS_CERT" \
  --domains="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"
~~~

Lệnh minh họa dùng **global Compute Engine Google-managed SSL certificate**. Certificate Manager cũng hỗ trợ chứng chỉ do Google quản lý và có các cách domain authorization riêng. Hai cách quản lý chứng chỉ có workflow gắn vào HTTPS proxy khác nhau; đừng tạo Certificate Manager certificate rồi gắn bằng tham số chỉ dành cho Compute SSL certificates.

Chứng chỉ được tạo chưa có nghĩa đã sẵn sàng. Google cần xác minh domain và provisioning có thể cần thời gian sau khi DNS được trỏ đúng đến frontend. Không triển khai production chính thức khi trạng thái chứng chỉ chưa hợp lệ.

### 8.2 Tạo target HTTPS proxy

~~~bash
gcloud compute target-https-proxies create "$HTTPS_PROXY" \
  --url-map="$URL_MAP" \
  --ssl-certificates="$TLS_CERT" \
  --project="$PROJECT_ID"
~~~

HTTPS proxy gắn URL map với TLS certificate. Chứng chỉ phải phù hợp hostname mà client dùng; nếu website phục vụ cả example.com và www.example.com, bạn cần chứng chỉ bao phủ các tên đó và DNS/frontend được cấu hình tương ứng.

### 8.3 Tạo global forwarding rule cho cổng 443

~~~bash
gcloud compute forwarding-rules create "$HTTPS_RULE" \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address="$IP_NAME" \
  --global \
  --target-https-proxy="$HTTPS_PROXY" \
  --ports=443 \
  --project="$PROJECT_ID"
~~~

Đường đi hiện tại:

~~~text
https://www.your-owned-domain.example
    → global static IP : 443
    → target HTTPS proxy + managed TLS certificate
    → URL map
    → Cloud CDN-enabled backend bucket
    → Cloud Storage origin
~~~

Trong bài này chỉ có frontend cổng 443. Nếu muốn người dùng gõ http:// mà được chuyển tự động sang https://, cấu hình thêm HTTP frontend cổng 80 **với URL redirect sang HTTPS**, không tạo một HTTP frontend trực tiếp phát nội dung không mã hóa. Cách thực hiện có thể qua Console hoặc một URL map redirect riêng theo tài liệu Application Load Balancer.

## 9. Trỏ DNS và kiểm tra chứng chỉ

Sau khi đã reserve IP và tạo HTTPS frontend, cập nhật DNS cho hostname bạn sở hữu:

| Trường DNS | Giá trị minh họa |
|---|---|
| Type | A |
| Name | www |
| Value | Global external IPv4 vừa reserve |
| TTL | Theo chính sách DNS, ví dụ 300 giây khi chuyển đổi |

Nếu dùng root/apex domain, hãy tạo A record cho đúng hostname tại DNS provider. CNAME dùng để trỏ sang **hostname**, không trỏ trực tiếp đến địa chỉ IP. Nếu muốn dùng IPv6, cần bổ sung địa chỉ/forwarding rule phù hợp và AAAA record tương ứng, không tự tạo AAAA trỏ đến một IPv4 address.

### Kiểm tra DNS

~~~bash
nslookup "$DOMAIN"
~~~

Kết quả cần giải về IP đã reserve. Việc thay DNS có thể cần thời gian do TTL và resolver cache; không dùng DNS cache của một máy để kết luận mọi nơi đã cập nhật.

### Kiểm tra trạng thái chứng chỉ

~~~bash
gcloud compute ssl-certificates describe "$TLS_CERT" \
  --global \
  --project="$PROJECT_ID" \
  --format="yaml(name,managed.status,managed.domainStatus,managed.domains)"
~~~

Chờ chứng chỉ được cấp thành công/ACTIVE cho domain thực tế trước khi xác nhận HTTPS sẵn sàng. Nếu provisioning kéo dài, kiểm tra DNS có trỏ đến đúng IP, hostname có bao phủ trong certificate, trạng thái frontend và khả năng domain được xác minh.

### Kiểm tra HTTPS và file tĩnh

~~~bash
curl -I "https://$DOMAIN/"
curl -I "https://$DOMAIN/index.html"
curl -I "https://$DOMAIN/about/"
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/not-found-test"
~~~

Kỳ vọng root/index/about/CSS trả response phù hợp và request thiếu resource trả 404. Với frontend đúng, trình duyệt phải báo chứng chỉ hợp lệ cho hostname và không có mixed-content warnings.

**Lưu ý:** HTTP status code và custom 404 page qua Cloud Storage/backend bucket có thể phụ thuộc endpoint và URL routing thực tế. Nếu gặp 403 cho một đường dẫn thiếu object, hãy kiểm tra quyền và cơ chế website/not-found response trước khi khẳng định đó là lỗi CDN. Thử cả đường dẫn /about/ và /about/index.html để kiểm chứng index suffix.

### Khi cần kiểm tra trước lúc DNS toàn hệ thống cập nhật

Với IP đã reserve và chứng chỉ đã ACTIVE, có thể dùng curl --resolve để định hướng một request HTTPS đến IP cụ thể trong khi vẫn giữ hostname cho TLS:

~~~bash
export FRONTEND_IP="REPLACE_WITH_RESERVED_IPV4"
curl --resolve "$DOMAIN:443:$FRONTEND_IP" \
  -I "https://$DOMAIN/"
~~~

Thay FRONTEND_IP bằng IP được cấp thật. Cách này **không bỏ qua xác thực TLS** và không giúp một certificate chưa provisioned trở thành hợp lệ; nó chỉ giúp kiểm tra đường đến frontend được chọn.

## 10. Thiết kế cache policy cho Cloud CDN

Cloud CDN có thể giảm thời gian tải và số lần đọc origin khi nội dung được cache. Tuy nhiên, với website được cập nhật thường xuyên, cache không được cấu hình tốt có thể khiến người dùng nhìn thấy phiên bản cũ dù object mới đã upload thành công.

### Cache-Control: phải hiểu trước khi đặt TTL

| Chỉ thị | Ý nghĩa thực tế | Trường hợp dùng |
|---|---|---|
| public | Cho phép shared cache lưu response phù hợp | Tệp static công khai |
| max-age=N | Cho phép giữ response fresh trong N giây | CSS, JS, ảnh hoặc HTML theo nhu cầu |
| no-cache | Cache có thể lưu response nhưng phải revalidate trước khi sử dụng lại | HTML cần nhận bản phát hành mới |
| no-store | Không lưu response ở cache tuân thủ chỉ thị | Nội dung nhạy cảm hoặc không được lưu |
| immutable | Gợi ý tài nguyên không đổi trong vòng đời URL | Assets có tên chứa content hash |
| s-maxage=N | TTL cho shared caches như CDN | Khi cần TTL edge khác browser |

Nếu không đặt Cache-Control metadata, Cloud Storage có thể cung cấp default response như public,max-age=3600 với object public; vì thế **không nên phó mặc TTL cho giá trị mặc định**. Cloud CDN xác định khả năng cache qua MIME type, status code, headers và cache mode của backend, không chỉ dựa trên phần mở rộng .js hay .html.

### Chính sách đề xuất cho bài lab

| Đối tượng | Chính sách gợi ý | Lý do |
|---|---|---|
| index.html | public, no-cache, max-age=0, must-revalidate | Ưu tiên cập nhật nội dung nhanh |
| 404.html | public, no-cache, max-age=0 | Không giữ lâu trang lỗi |
| about/index.html | public, no-cache, max-age=0 | Trang HTML có thể thay đổi |
| assets/style.css và app.js chưa hash | public, max-age=300 | Tránh kẹt quá lâu khi tên file không đổi |
| assets/app.a1b2c3.js được hash theo nội dung | public, max-age=31536000, immutable | URL mới khi nội dung đổi, cache lâu an toàn |
| Ảnh có tên cố định | public, max-age=3600 hoặc phù hợp | Giảm số lượt đọc origin; xem xét nhu cầu cập nhật |

Đây là các giá trị khởi đầu để học cách vận hành, không phải policy chung cho mọi tổ chức. Với asset hash dài hạn, workflow build phải tạo tên mới khi file thay đổi và cập nhật HTML để trỏ sang tên mới.

### Cập nhật object metadata

~~~bash
gcloud storage objects update \
  "gs://$SITE_BUCKET/index.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/404.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/about/index.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/style.css" \
  --cache-control="public,max-age=300"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/app.js" \
  --cache-control="public,max-age=300"
~~~

Kiểm tra thông tin sau cập nhật:

~~~bash
curl -I "https://$DOMAIN/index.html"
curl -I "https://$DOMAIN/assets/app.js"
~~~

Bạn nên thấy Cache-Control mong muốn, Content-Type đúng và các response status phù hợp. Với một số chính sách, bản response cũ có thể vẫn tồn tại ở browser/edge cho đến khi hết TTL hoặc được invalidated; lệnh metadata update không luôn làm cache cũ biến mất lập tức.

### Cache mode và nội dung công khai

Các cache modes phổ biến gồm USE_ORIGIN_HEADERS, CACHE_ALL_STATIC và FORCE_CACHE_ALL. Với website public, nên bắt đầu từ origin headers hoặc chính sách cache static phù hợp. **FORCE_CACHE_ALL** có thể bỏ qua các chỉ thị chống cache của origin và không an toàn cho dữ liệu cá nhân hóa; chỉ dùng khi đã bảo đảm tất cả nội dung thuộc backend được phép cache công khai.

Trong mô hình **private bucket access**, tài liệu Cloud CDN có các yêu cầu cache mode riêng. Khi chuyển kiến trúc, đọc lại hướng dẫn chính thức thay vì giả định policy của public bucket có thể sao chép nguyên vẹn.

## 11. Kiểm tra Cloud CDN cache thực sự hoạt động

Đã bật CDN không đồng nghĩa mọi request chắc chắn là cache hit. Request đầu tiên thường phải lấy nội dung từ origin; request sau có thể hit nếu object đủ điều kiện, còn mới và chưa bị evicted.

### Thử bằng lệnh

~~~bash
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/assets/style.css"
~~~

Xem các header như Cache-Control, Age nếu có, Content-Type và status. Header Age có thể gợi ý response lấy từ cache nhưng **không phải mọi response đều có Age, và chỉ một header không đủ để chứng minh chính xác hit ratio**.

### Thử bằng Cloud Monitoring

Trong Cloud Monitoring và trang Cloud CDN/Load Balancing:

1. Chọn đúng backend bucket và URL map.
2. Xem lưu lượng request và tỉ lệ cache hit/miss nếu metric khả dụng.
3. Quan sát bytes served từ cache so với origin.
4. So sánh nhiều lần truy cập sau khi nội dung đã được làm nóng cache.
5. Kiểm tra độ trễ và response codes; đừng tối ưu hit ratio khi người dùng đang nhận nội dung lỗi.

Nếu Cloud CDN logging được bật, chọn tỷ lệ lấy mẫu log phù hợp để hỗ trợ chẩn đoán. Không bật logging quá chi tiết cho mọi request khi lưu lượng lớn mà chưa đánh giá chi phí và dữ liệu có thể xuất hiện trong URL.

### Cache miss không nhất thiết là lỗi

Các nguyên nhân thường gặp:

- Request lần đầu ở một edge location.
- Object không cacheable do header, MIME type hoặc status.
- TTL hết, entry bị evicted hoặc nội dung đã invalidated.
- URL có query string khác và cache key policy coi đó là object khác.
- Có cookie/Authorization hoặc header làm thay đổi cacheability.
- CDN policy và origin metadata chưa phù hợp.

Đừng dùng tỷ lệ cache hit tối đa bằng mọi giá. Một response HTML cũ được cache rất tốt nhưng chứa link đến asset đã xóa sẽ gây lỗi thực tế cho người dùng.

## 12. Phát hành phiên bản mới và vô hiệu hóa cache

Giả sử đội thiết kế thay nội dung trang chủ:

~~~html
<h1>Xin chào từ Google Cloud — bản cập nhật</h1>
~~~

Một vòng phát hành thủ công:

1. Review thay đổi và chạy test local.
2. Upload assets mới vào bucket.
3. Upload trang HTML đã trỏ đến các assets cần thiết.
4. Đặt lại metadata Cache-Control nếu quy trình upload làm thay đổi metadata.
5. Kiểm tra HTTPS URL bằng curl và trình duyệt.
6. Nếu chính sách cache không cho phép cập nhật đủ nhanh, invalidation **đúng đường dẫn**.

### Targeted cache invalidation

Ví dụ invalidation hai URL cụ thể (không xóa toàn bộ cache):

~~~bash
gcloud compute url-maps invalidate-cdn-cache "$URL_MAP" \
  --path="/index.html" \
  --host="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"

gcloud compute url-maps invalidate-cdn-cache "$URL_MAP" \
  --path="/" \
  --host="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"
~~~

Đường dẫn / và /index.html có thể là hai cache keys khác nhau. Nếu site phục vụ cả root và file index trực tiếp, cần xem chính sách URL rewriting/cache key để không bỏ sót đường dẫn người dùng truy cập.

**Không mặc định invalidation toàn bộ /* cho mỗi commit.** Invalidation có chi phí hoặc quota theo điều kiện sử dụng, và invalidation diện rộng có thể làm tăng đột biến requests đến origin. Với website production, ưu tiên content-hashed assets và HTML TTL ngắn hơn việc liên tục purge toàn bộ.

### Versioned assets và rollback

Khi dùng bundler (Vite/Webpack hoặc công cụ khác), có thể tạo:

~~~text
assets/app.8f2c3d.js
assets/style.4e5a7b.css
~~~

Một bản phát hành mới tạo tên hash mới; HTML mới trỏ đến file mới. Các asset cũ nên được giữ đủ lâu cho người dùng còn mở tab chứa HTML trước đó. Không xóa asset cũ ngay sau publish nếu nó còn được tham chiếu từ cache hoặc trang đã tải.

Để rollback, khôi phục **bộ artifact đã được kiểm thử** (HTML và assets tương ứng) và xác minh CDN đang phục vụ đúng. Đừng khôi phục riêng index.html nếu một số assets trước đó đã bị xóa. Có thể lưu release artifact trong CI/CD artifact store hoặc bucket nội bộ riêng có retention phù hợp.

### Tại sao nên coi website tĩnh là một release artifact?

Cloud Storage upload từng object không phải một giao dịch atomic cho cả directory. Nếu upload HTML trước rồi assets mới chưa sẵn sàng, người dùng có thể gặp 404 tạm thời. Một release workflow tốt nên:

- Build một bộ artifact bất biến.
- Kiểm tra link/reference và file tồn tại trước khi phát hành.
- Upload assets trước, HTML entrypoint sau.
- Chỉ chuyển metadata/cache hoặc traffic sau khi smoke test đạt.
- Giữ release cũ để rollback.

Với site nhỏ bài lab, thao tác rsync toàn bộ đủ để học luồng. Với production, cần quy trình publish thứ tự và rollback rõ hơn.

## 13. Tự động hóa bằng Cloud Build

Upload thủ công dễ sai project, sai bucket, thiếu file hoặc bỏ sót metadata. Có thể sử dụng Cloud Build để chạy các bước kiểm tra và upload artifact khi merge vào một nhánh được phê duyệt.

### Thiết kế CI/CD

~~~mermaid
flowchart LR
    A["Commit/merge"] --> B["Cloud Build trigger"]
    B --> C["Validate static files"]
    C --> D["Build frontend nếu cần"]
    D --> E["Upload assets → HTML"]
    E --> F["Check metadata/cache"]
    F --> G["Smoke test HTTPS"]
    G --> H["Release report"]
~~~

Build service account chỉ cần quyền upload/metadata trên bucket và quyền ghi logs cần thiết. **Nó không cần quyền tạo DNS, TLS certificate hoặc load balancer** cho mỗi lần release; các resource hạ tầng nên được quản lý qua IaC hoặc quy trình platform riêng.

### cloudbuild.yaml đơn giản

Tệp dưới đây dành cho repo có thư mục site/ đã chứa HTML/CSS/JS:

~~~yaml
substitutions:
  _SITE_BUCKET: your-unique-static-site-bucket

steps:
  - id: validate-site
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        test -f site/index.html
        test -f site/404.html
        test -f site/assets/style.css
        test -f site/assets/app.js
        echo "Static site input checks passed"

  - id: publish-assets
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        gcloud storage cp \
          site/assets/style.css \
          gs://$_SITE_BUCKET/assets/style.css
        gcloud storage cp \
          site/assets/app.js \
          gs://$_SITE_BUCKET/assets/app.js
        gcloud storage objects update \
          gs://$_SITE_BUCKET/assets/style.css \
          --cache-control="public,max-age=300"
        gcloud storage objects update \
          gs://$_SITE_BUCKET/assets/app.js \
          --cache-control="public,max-age=300"
    waitFor:
      - validate-site

  - id: publish-html
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        gcloud storage cp \
          site/about/index.html \
          gs://$_SITE_BUCKET/about/index.html
        gcloud storage cp \
          site/404.html \
          gs://$_SITE_BUCKET/404.html
        gcloud storage cp \
          site/index.html \
          gs://$_SITE_BUCKET/index.html
        gcloud storage objects update \
          gs://$_SITE_BUCKET/index.html \
          gs://$_SITE_BUCKET/404.html \
          gs://$_SITE_BUCKET/about/index.html \
          --cache-control="public,no-cache,max-age=0,must-revalidate"
    waitFor:
      - publish-assets

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 600s
~~~

Ví dụ dùng các file cụ thể để thấy rõ thứ tự upload assets trước rồi HTML. Với site lớn, hãy dùng một lệnh đồng bộ có kế hoạch kiểm soát các file bị xóa và metadata, hoặc publish release versioned. Không tự động xóa các file cũ trong một release đơn giản.

Trong cloudbuild.yaml, $_SITE_BUCKET là **custom substitution** của Cloud Build. Khi đưa một biến shell thực sự xuống container trong lệnh bash, có thể cần escape dollar bằng $$ theo quy tắc substitutions của Cloud Build. Không đưa password hay token vào substitutions.

### Cấu hình build identity

Quy trình thường gồm:

1. Tạo user-specified build service account.
2. Cấp quyền ghi object cho **bucket website**, không cấp toàn project nếu không cần.
3. Cấp quyền ghi Cloud Logging khi dùng CLOUD_LOGGING_ONLY.
4. Tạo trigger chỉ chạy từ branch được bảo vệ hoặc release tag.
5. Chỉ cho phép người/phần mềm được phê duyệt sửa build config và kích hoạt production release.
6. Xác minh build không thể sửa các bucket khác hoặc xóa resource networking.

Ví dụ chạy thủ công trong project lab:

~~~bash
gcloud builds submit . \
  --project="$PROJECT_ID" \
  --config=cloudbuild.yaml \
  --region="$REGION" \
  --substitutions="_SITE_BUCKET=$SITE_BUCKET"
~~~

CLI sử dụng danh tính build đã được cấu hình theo build/trigger; nếu môi trường yêu cầu chỉ định build service account, hãy cấu hình nó theo hướng dẫn hiện hành và bảo đảm principal có quyền phù hợp. Build sẽ thất bại khi không có quyền upload; **không** xử lý bằng cách cấp Editor/Owner.

### Tự động kiểm thử sau phát hành

Một pipeline có thể chạy smoke test khi cert/DNS đã hoạt động:

~~~bash
curl --fail --silent --show-error \
  "https://$DOMAIN/index.html" > /dev/null

curl --fail --silent --show-error \
  "https://$DOMAIN/assets/style.css" > /dev/null
~~~

Trong thực tế, có thể kiểm tra nội dung/version marker và mô tả lỗi rõ hơn là chỉ gọi curl. Nếu cache chưa cập nhật, test phải phân biệt “origin publish sai” và “CDN đang phục vụ phiên bản cũ đúng TTL”.

## 14. Bảo mật website tĩnh và ranh giới dữ liệu công khai

Cloud Storage + CDN phục vụ nội dung public rất hiệu quả, nhưng điều đó không loại bỏ trách nhiệm bảo mật ứng dụng.

### 14.1 Kiểm soát nội dung trong bucket

Không upload:

- API keys được phép thực hiện thao tác nhạy cảm, database password, private key hoặc service account JSON.
- File .env, .git, source code nội bộ, backup, logs hoặc dump chứa dữ liệu khách hàng.
- Source maps có mã nguồn/đường dẫn nội bộ chưa được phê duyệt công khai.
- File upload từ người dùng chưa qua kiểm tra và xử lý bảo mật.
- Cấu hình Spring Boot hoặc Java backend có thông tin xác thực.

Mọi file JS/HTML/JSON trên website public có thể được tải về và đọc bởi người dùng. **Minification, obfuscation hoặc tên file khó đoán không bảo vệ secret.**

Nếu frontend cần gọi API riêng trên Cloud Run:

1. Đặt API ở hostname riêng như api.example.com hoặc dùng path routing có chủ đích.
2. Xác thực và phân quyền ở backend, không dựa vào việc JavaScript ẩn nút.
3. Kiểm soát CORS nếu frontend/API khác origin; CORS không thay thế authorization.
4. Không lưu credential backend trong static files.
5. Kiểm soát rate limit, quotas và logs theo mức rủi ro.

### 14.2 Content Security Policy và HTTP security headers

Site có thể áp dụng các header như:

| Header | Vai trò |
|---|---|
| Content-Security-Policy | Hạn chế nguồn script, style, ảnh và các tài nguyên khác |
| X-Content-Type-Options: nosniff | Giảm nguy cơ xử lý sai MIME type |
| Referrer-Policy | Kiểm soát thông tin referrer được chia sẻ |
| Strict-Transport-Security | Yêu cầu browser tiếp tục dùng HTTPS sau khi được thiết lập |
| Permissions-Policy | Giới hạn một số browser capabilities |

Các header này cần được cấu hình tại tầng phục vụ HTTP có hỗ trợ, ví dụ response header policy ở load balancer hoặc dịch vụ frontend phù hợp. Không giả định Cloud Storage có thể thiết lập mọi response header tùy ý chỉ bằng một object metadata field.

HSTS cần được áp dụng cẩn thận sau khi HTTPS đã ổn định cho các hostname liên quan. Đừng bật includeSubDomains hoặc preload nếu các subdomain khác chưa sẵn sàng phục vụ HTTPS.

### 14.3 Bảo vệ quyền triển khai

Với public-origin bucket, đọc và ghi là hai quyền rất khác nhau:

- allUsers chỉ nên có quyền đọc trong bucket public được phê duyệt.
- Build identity có quyền upload và cập nhật metadata trên đúng bucket.
- Người quản trị hạ tầng có quyền sửa LB, chứng chỉ và DNS.
- Người xem logs/metrics không mặc nhiên có quyền sửa website.

Tách môi trường staging và production bằng bucket hoặc project phù hợp. Không để pull request từ nhánh chưa tin cậy chạy với service account có quyền phát hành trực tiếp lên website production.

### 14.4 Giới hạn của public-origin

Nếu bucket được công khai qua allUsers, người dùng có thể truy cập trực tiếp vào Cloud Storage endpoint khi biết bucket/object name, không nhất thiết phải đi qua HTTPS load balancer của bạn. Do đó:

- CDN, TLS policy hoặc WAF ở load balancer **không phải ranh giới truy cập duy nhất** của public origin.
- Không dùng public bucket để giữ tài liệu mà bạn muốn chỉ cho phép xem qua frontend đã xác thực.
- Khi cần buộc đường truy cập qua load balancer/CDN, chuyển sang private bucket access theo tài liệu của Google Cloud.

Đây là lý do bước lựa chọn public/private origin phải được quyết định theo threat model, không chỉ theo độ dễ của lệnh triển khai.

## 15. Monitoring, logging và theo dõi phiên bản

Một website tĩnh cũng có thể gặp sự cố: chứng chỉ hết hiệu lực, DNS trỏ sai, object bị xóa, HTML trỏ đến asset cũ, CDN cache sai hoặc chi phí tăng đột biến.

### Dashboard tối thiểu

| Nhóm | Tín hiệu cần xem | Mục đích |
|---|---|---|
| Load balancer | Request count, 4xx/5xx, latency | Phát hiện route hoặc origin lỗi |
| Cloud CDN | Cache hit/miss, cache egress/origin fetch | Đánh giá hiệu quả cache |
| Cloud Storage | Object count, bytes stored, operations | Phát hiện tăng storage hoặc đọc bất thường |
| TLS/DNS | Certificate status, DNS resolution, HTTPS synthetic check | Phát hiện mất khả dụng của miền |
| Cloud Build | Build status, release ID và người phát hành | Liên hệ thay đổi với sự cố |
| Billing | Cost theo project và dịch vụ | Phát hiện phí ngoài kế hoạch |

Không phải metric nào cũng có sẵn ngay khi chưa bật logging hoặc có quá ít traffic. Chọn các metrics phù hợp với resource đang dùng và cấu hình sample/logging cho vừa nhu cầu.

### Synthetic monitoring

Một kiểm tra từ bên ngoài có thể gửi GET đến:

~~~text
https://www.your-owned-domain.example/
https://www.your-owned-domain.example/about/
https://www.your-owned-domain.example/assets/style.css
~~~

Kiểm tra status, TLS validity, content marker và timeout. Chỉ kiểm tra load balancer health mà không tải trang thật sẽ không phát hiện mọi lỗi liên kết CSS/JS.

### Release metadata

Mỗi lần phát hành nên lưu:

- Source commit SHA.
- Cloud Build ID.
- Artifact checksum hoặc manifest.
- Thời điểm release UTC.
- Bucket và URL map.
- Người hoặc trigger thực hiện.
- Kết quả smoke test.
- Tham chiếu đến release trước dùng để rollback.

Một nhãn version hiển thị ở cuối trang hoặc comment HTML có thể giúp biết người dùng đang nhận phiên bản nào. Không đưa thông tin nội bộ nhạy cảm như private repository token hoặc secret path vào metadata public.

## 16. Ước lượng chi phí và tối ưu

Lợi ích của static hosting là không phải chạy một VM hoặc Java process 24/7. Tuy nhiên, kiến trúc HTTPS + load balancer + CDN có nhiều thành phần tính phí.

~~~text
Chi phí website tĩnh / tháng
  = Cloud Storage capacity và operations
  + Application Load Balancer và forwarding rules
  + Cloud CDN cache egress và cache fill (theo mô hình giá áp dụng)
  + network egress và transfer liên quan
  + Cloud DNS nếu dùng managed zone có phí
  + Cloud Logging / Monitoring theo mức sử dụng
  + các dịch vụ CI/CD và bảo mật nếu có
~~~

Không dùng công thức như hóa đơn chính xác vì giá phụ thuộc region, pricing tier, lượng traffic, cache hit ratio và các điều kiện hiện hành. Tra bảng giá chính thức và sử dụng Google Cloud Pricing Calculator trước khi triển khai lâu dài.

### Câu hỏi định lượng cho dự toán

1. Website có bao nhiêu GB object?
2. Có bao nhiêu lượt xem mỗi ngày?
3. Kích thước trung bình một page load gồm HTML/CSS/JS/ảnh là bao nhiêu?
4. Người dùng đến từ region nào và CDN có khả năng cache các object đó không?
5. Có bao nhiêu lần deploy hoặc cache invalidation mỗi tháng?
6. Log và metric được lưu trong bao lâu?
7. Load balancer chạy thường trực hay chỉ tồn tại trong thời gian lab?

### Ví dụ tính lưu lượng gần đúng

Giả sử **mỗi page load truyền trung bình 1 MiB** và có **100.000 page loads/tháng**:

~~~text
Data served to clients ≈ 100000 MiB
                       ≈ 97.7 GiB / tháng
~~~

Đây chỉ là phép ước lượng lưu lượng đến trình duyệt, **không phải** dung lượng origin egress hoặc hóa đơn CDN. Browser cache, edge cache, revalidation, tải lại tài nguyên và vị trí người dùng làm chi phí thực tế thay đổi. Nếu 70% dữ liệu được phục vụ từ cache tại edge, số byte origin được đọc có thể giảm, nhưng cần dùng metrics thực để ước lượng chính xác.

### Tối ưu không làm mất tính đúng đắn

- Tối ưu ảnh WebP/AVIF nếu phù hợp browser support.
- Nén hoặc minify CSS/JS và loại bỏ dependencies không cần.
- Đặt TTL cho asset bất biến; giữ HTML cập nhật được.
- Tránh invalidation diện rộng không cần thiết.
- Dùng content-hashed assets và release manifest.
- Đặt retention/lifecycle phù hợp với version cũ, không xóa asset vẫn còn được tham chiếu.
- Đặt budget và xem chi phí thực tế sau chu kỳ tải đại diện.

Đừng dùng cache policy cực dài cho index.html chỉ để đạt cache hit ratio cao, nếu người dùng cần nhận thông tin mới hoặc thay đổi quan trọng nhanh chóng.

## 17. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| DNS không về IP load balancer | Sai A record, TTL hoặc sửa nhầm DNS zone | nslookup/dig và tên zone có thẩm quyền |
| Chứng chỉ chưa ACTIVE | Domain chưa trỏ đúng frontend, validation/provisioning chưa xong | Certificate status/domainStatus |
| HTTPS lỗi hostname mismatch | Certificate không bao phủ hostname | SAN/domains và URL truy cập |
| Trang chủ 403 | Origin permission/PAP hoặc backend route sai | Bucket IAM, public/private access và URL map |
| Trang chủ 404 | Không có index.html ở root hoặc website config sai | Object list, MainPageSuffix, request path |
| /about/ không tải nhưng /about/index.html tải | Routing/index suffix chưa khớp | Website config và LB behavior |
| CSS/JS không tải | File không tồn tại, đường dẫn sai, Content-Type sai | DevTools Network và object metadata |
| Website vẫn hiện phiên bản cũ | Browser cache, CDN TTL hoặc object chưa upload | Cache-Control, Age, release ID và CDN metrics |
| Cache hit thấp | TTL ngắn, file không cacheable, URL/query biến đổi | Cache mode, headers và response type |
| CDN vô tình cache dữ liệu nhạy cảm | FORCE_CACHE_ALL hoặc public response có dữ liệu cá nhân | Dừng phát hành, xem policy, sửa origin, invalidate đúng phạm vi |
| Cloud Build permission denied | Build SA không có quyền bucket hoặc log | IAM tại bucket và service account thực tế |
| Lỗi sau deploy nhưng upload báo thành công | HTML/asset không đồng bộ hoặc file cũ bị xóa | Build manifest, smoke test, rollback artifact |
| Hóa đơn tăng dù ít người truy cập | LB/IP vẫn tồn tại, logging hoặc cache fills/egress | Billing breakdown và inventory resource |

### Trình tự điều tra

1. Kiểm tra DNS và trạng thái chứng chỉ.
2. Kiểm tra forwarding rule → HTTPS proxy → URL map → backend bucket.
3. Xác minh object tồn tại và có quyền truy cập phù hợp.
4. Xem status code và response headers ở đúng hostname.
5. So sánh object origin, cache policy và phiên bản release.
6. Kiểm tra Cloud CDN metrics/logs nếu có.
7. Nếu lỗi xuất hiện sau release, cân nhắc rollback trước khi đổi quyền toàn bộ project.

Tránh sửa đồng thời DNS, bucket IAM và cache policy khi chưa xác định nguyên nhân; thay đổi nhiều thứ cùng lúc làm mất khả năng truy vết.

## 18. Dọn tài nguyên lab an toàn

Kết thúc dự án học tập, hãy dọn các tài nguyên tính phí **chỉ khi chắc chắn đó là tài nguyên của riêng bài lab**. Một sai lầm thường gặp là xóa URL map hoặc bucket dùng chung với website khác.

### Inventory trước khi xóa

~~~bash
gcloud config get-value project

gcloud compute forwarding-rules describe "$HTTPS_RULE" \
  --global \
  --project="$PROJECT_ID"

gcloud compute backend-buckets describe "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"

gcloud storage buckets describe "gs://$SITE_BUCKET"
~~~

Đối chiếu mọi tên với resource inventory đã ghi ở đầu bài. Nếu các resource đang phục vụ traffic của tổ chức hoặc không thuộc lab, **không xóa**.

### Thứ tự phụ thuộc

Sau khi xác nhận và được phép dọn:

1. Chuyển DNS khỏi frontend theo kế hoạch hoặc xác nhận hostname lab không còn cần phục vụ.
2. Xóa forwarding rule HTTPS (và HTTP redirect rule nếu đã tạo).
3. Xóa target HTTPS proxy và các target proxy riêng của lab.
4. Xóa SSL certificate chỉ được dùng cho lab.
5. Xóa URL map chỉ thuộc lab.
6. Xóa backend bucket của load balancer.
7. Release global static IP khi không còn forwarding rule dùng đến.
8. Xóa object tạm rồi xóa Cloud Storage bucket sau khi xác nhận ownership, retention và backup.
9. Xóa build trigger/role binding test riêng nếu không còn dùng.
10. Kiểm tra Billing và resource inventory để xác nhận không còn tài nguyên tính phí ngoài dự kiến.

Ví dụ xóa phần frontend **chỉ khi đã đối chiếu các tên cụ thể**:

~~~bash
gcloud compute forwarding-rules delete "$HTTPS_RULE" \
  --global \
  --project="$PROJECT_ID"

gcloud compute target-https-proxies delete "$HTTPS_PROXY" \
  --global \
  --project="$PROJECT_ID"

gcloud compute ssl-certificates delete "$TLS_CERT" \
  --global \
  --project="$PROJECT_ID"

gcloud compute url-maps delete "$URL_MAP" \
  --global \
  --project="$PROJECT_ID"

gcloud compute backend-buckets delete "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"

gcloud compute addresses delete "$IP_NAME" \
  --global \
  --project="$PROJECT_ID"
~~~

**Cảnh báo:** Lệnh delete thực sự hủy resource; không chạy trong lúc website còn phục vụ người dùng hoặc khi resource được chia sẻ. Nếu có HTTP redirect frontend riêng, phải gỡ các dependency của frontend đó trước. Với bucket, ưu tiên review object inventory trong Console trước khi xóa; không dùng wildcard xóa toàn bộ project/bucket khi chưa kiểm tra retention và ownership.

Không dùng việc dừng truy cập website làm bằng chứng rằng chi phí bằng 0. Kiểm tra các resource còn tồn tại, vì static IP, load balancing components, object storage và log retention có thể tiếp tục phát sinh phí theo điều kiện sử dụng.

## 19. Bài tập thực hành theo từng mốc

Phần này tổng hợp dự án thành các mốc có thể đánh giá độc lập. Hãy thực hiện trong project lab và ghi lại ảnh/chỉ số bằng chứng, **không đưa credential hoặc dữ liệu nhạy cảm vào báo cáo**.

### Mốc A — Có website tĩnh dùng được

1. Tạo thư mục site với index.html, about/index.html, 404.html, CSS và JavaScript.
2. Mở website bằng local development server và kiểm tra các liên kết.
3. Dùng DevTools xác minh CSS/JS không báo lỗi MIME hoặc 404.
4. Kiểm tra layout trên màn hình nhỏ và khả năng dùng bàn phím.
5. Ghi lại phiên bản mã nguồn và danh sách file sẽ publish.

**Bằng chứng:** Trang chủ, trang phụ và nút JavaScript hoạt động; không có lỗi console quan trọng.

### Mốc B — Origin Cloud Storage được cấu hình đúng

1. Kiểm tra project ID, budget và bucket name.
2. Tạo bucket với location và uniform bucket-level access được chọn.
3. Upload chính xác nội dung site/.
4. Cấu hình index/error pages.
5. Kiểm tra Content-Type và Cache-Control.
6. Chỉ bật quyền đọc công khai cho bucket **đã được phê duyệt là public**, hoặc dùng private bucket access nếu tổ chức yêu cầu.

**Bằng chứng:** Bucket object list khớp source manifest; website configuration hợp lệ; không có secret trong object.

### Mốc C — HTTPS và CDN hoạt động

1. Reserve global external IPv4.
2. Tạo backend bucket trỏ Cloud Storage và bật Cloud CDN.
3. Tạo URL map với backend bucket mặc định.
4. Cấp phát Google-managed certificate cho hostname thật.
5. Tạo target HTTPS proxy và global forwarding rule cổng 443.
6. Trỏ DNS A record đến địa chỉ IP.
7. Chờ certificate active, kiểm tra HTTPS trong browser và curl.
8. Thực hiện vài request rồi quan sát CDN/cache metrics.

**Bằng chứng:** URL https://hostname/ tải thành công, certificate hợp lệ và backend bucket cho thấy CDN enabled.

### Mốc D — Phát hành phiên bản thứ hai

1. Đổi một tiêu đề hoặc đoạn nội dung trong index.html.
2. Cập nhật ít nhất một CSS/JS asset.
3. Upload assets trước rồi HTML.
4. Xác minh response content/headers sau publish.
5. Nếu cần, invalidate đúng đường dẫn / và /index.html.
6. Ghi release ID, thời điểm và cách kiểm tra cache.

**Bằng chứng:** Người dùng nhận nội dung mới trong khoảng thời gian chính sách cho phép; các link đến assets không lỗi.

### Mốc E — Tự động hóa và rollback

1. Tạo cloudbuild.yaml và service account được cấp quyền ghi bucket.
2. Chạy build từ một commit thử nghiệm.
3. Xác minh build log có các bước validate và publish.
4. Làm hỏng có kiểm soát một đường dẫn asset trong môi trường test, xác nhận smoke test phát hiện.
5. Khôi phục artifact của release trước và cập nhật cache theo chính sách.
6. Xác minh website trở lại trạng thái mong đợi.

**Bằng chứng:** Build ID, kết quả PASS/FAIL và báo cáo rollback. Không cố tình làm hỏng website production của người khác.

### Mốc F — Vận hành và cleanup

1. Xây dashboard tối thiểu cho request, lỗi, CDN và chi phí.
2. Tạo một synthetic check cho HTTPS homepage.
3. Xem Billing breakdown và so sánh với dự toán.
4. Ghi lại resource inventory.
5. Khi lab kết thúc, thực hiện cleanup theo thứ tự phụ thuộc.
6. Kiểm tra không còn tài nguyên phát sinh phí ngoài kế hoạch.

**Bằng chứng:** Checklist cuối dự án và resource inventory trước/sau cleanup.

### Tiêu chí đánh giá dự án

| Tiêu chí | Tỷ trọng tham khảo | Đạt khi |
|---|---:|---|
| Website và cấu trúc tệp | 15% | HTML/CSS/JS và 404 có thể kiểm tra |
| Cloud Storage và quyền | 20% | Bucket đúng project, metadata và IAM phù hợp |
| HTTPS/DNS | 20% | Hostname và chứng chỉ đúng, response được xác minh |
| CDN và cache policy | 15% | CDN enabled, TTL hợp lý, đo kiểm có bằng chứng |
| CI/CD và rollback | 15% | Có release tự động và cách quay lại bản cũ |
| Security, cost, observability | 15% | Không lộ secret, có metrics và budget/cleanup |

Tỷ trọng là ví dụ để tự học. Mỗi tổ chức có thể thay đổi theo mức quan trọng của bảo mật, khả năng tái lập và vận hành.

## 20. Nâng cấp dự án

Sau khi phần cơ bản hoạt động, thử một hoặc nhiều hướng mở rộng:

### Hướng 1 — Website công khai nhưng private origin

Chuyển sang private bucket access phù hợp với global external Application Load Balancer và Cloud CDN. Không dùng allUsers; kiểm tra rằng frontend vẫn phục vụ nội dung nhưng origin trực tiếp không mở cho người dùng tùy ý. Xem kỹ khả năng cache và yêu cầu cache mode của private bucket access.

### Hướng 2 — HTTP sang HTTPS redirect

Trong Load Balancing Console hoặc qua cấu hình URL map redirect:

1. Tạo thêm frontend HTTP cổng 80 cho IP đã dùng.
2. Định tuyến HTTP bằng URL redirect sang HTTPS, giữ host/path/query theo policy.
3. Kiểm tra mã phản hồi 301 hoặc 308 theo cấu hình.
4. Đảm bảo không tạo vòng redirect hoặc chuyển sang domain sai.
5. Chỉ bật HSTS khi mọi hostname liên quan đều có HTTPS hợp lệ.

**Không** dùng port 80 để phục vụ cùng nội dung dưới HTTP nếu mục tiêu là HTTPS-only.

### Hướng 3 — Frontend gọi API Java/Spring trên Cloud Run

Giữ website ở backend bucket, nhưng chạy API động trên Cloud Run với danh tính riêng và bảo vệ authentication/authorization. Có thể dùng api.example.com hoặc host/path rule trên load balancer. Kiểm tra CORS khi khác origin và tuyệt đối không đưa secret backend vào JavaScript.

### Hướng 4 — CI/CD dùng hashed assets

Thêm npm build step, tạo assets có content hash và đặt TTL dài cho assets. HTML có TTL ngắn hoặc revalidation. Sau đó thử deploy liên tiếp và rollback để chứng minh không gặp lỗi tham chiếu file đã bị xóa.

### Hướng 5 — IaC và kiểm soát thay đổi

Mô tả bucket, backend bucket, IP, URL map, certificate, proxy và forwarding rule bằng Terraform hoặc công cụ IaC tương thích. Bảo vệ state, review plan và dùng identity riêng cho provision. Không chạy destroy trên resource production chỉ vì test một thay đổi lab.

## 21. Checklist trước khi xem dự án hoàn thành

- [ ] Project lab và Billing đã được xác nhận.
- [ ] Có budget alert và owner chịu trách nhiệm chi phí.
- [ ] Domain thực tế thuộc quyền quản lý hoặc đã được cho phép sử dụng.
- [ ] Website tĩnh chạy local và không chứa secret.
- [ ] Bucket có tên duy nhất, đúng location và UBLA.
- [ ] Upload đúng index.html, trang phụ, 404.html và assets.
- [ ] Content-Type của HTML/CSS/JS/ảnh chính xác.
- [ ] Website main page và not-found page đã cấu hình.
- [ ] IAM chỉ cấp quyền public trên nội dung đã phê duyệt.
- [ ] Chính sách public access prevention được tôn trọng.
- [ ] Đã cân nhắc public origin hoặc private bucket access.
- [ ] Global IP, backend bucket và URL map được tạo đúng project.
- [ ] Cloud CDN đã bật và cache policy có chủ đích.
- [ ] TLS certificate ACTIVE và khớp hostname.
- [ ] DNS A record trỏ đến đúng frontend IP.
- [ ] HTTPS root, about và assets đáp ứng smoke test.
- [ ] Kiểm tra response 404 hoặc lỗi tương ứng cho file không có.
- [ ] HTML cache ngắn; hashed assets (nếu có) có TTL phù hợp.
- [ ] Có cách invalidation mục tiêu hoặc publish với versioned filenames.
- [ ] Cloud Build dùng danh tính chỉ có quyền upload cần thiết.
- [ ] Build/release được gắn commit ID và có phương án rollback.
- [ ] Đã kiểm tra hoạt động trên mobile và bằng bàn phím.
- [ ] Đã kiểm tra logs/metrics và thiết lập cảnh báo tối thiểu.
- [ ] Đã xem chi phí LB/CDN/Storage sau giai đoạn kiểm thử.
- [ ] Có tài liệu cleanup và inventory resource riêng của lab.

## Câu hỏi tự kiểm tra

**1. Vì sao Cloud Storage không đủ để tự phục vụ website custom domain qua HTTPS theo kiến trúc của bài?**

Vì website cần HTTPS frontend có chứng chỉ gắn với tên miền. Application Load Balancer nhận HTTPS, dùng URL map và backend bucket để lấy nội dung từ Cloud Storage.

**2. Backend bucket khác Cloud Storage bucket như thế nào?**

Cloud Storage bucket thực sự giữ object. Backend bucket là tài nguyên Load Balancing tham chiếu đến Cloud Storage bucket và có thể gắn Cloud CDN policy.

**3. Vì sao một bucket được cấp roles/storage.objectViewer cho allUsers phải chỉ chứa nội dung công khai?**

Vì người dùng Internet có thể đọc object và có thể liệt kê object metadata/tên tệp theo quyền được cấp. CDN không làm tệp trong public bucket trở nên bí mật.

**4. Uniform bucket-level access hỗ trợ điều gì?**

Nó dùng bucket-level IAM thay vì object ACL để kiểm soát quyền và giúp quản lý quyền nhất quán hơn.

**5. Trạng thái certificate đang provisioning có nghĩa website HTTPS đã sẵn sàng không?**

Chưa. Cần chờ quá trình xác minh và cấp phát, kiểm tra DNS và xác nhận chứng chỉ ACTIVE/hợp lệ trước khi công bố.

**6. Tại sao index.html không nên cache immutable một năm khi tên file không đổi?**

Vì trình duyệt và CDN có thể giữ bản HTML cũ dù đã publish bản mới; người dùng có thể không thấy thay đổi hoặc nhận link tới assets không còn phù hợp.

**7. Content-hashed asset giúp gì khi cache lâu?**

Khi nội dung thay đổi, filename/URL đổi theo. Cache của file cũ và file mới không xung đột, cho phép TTL dài mà vẫn phát hành phiên bản mới.

**8. Lệnh invalidation có cập nhật object trong Cloud Storage không?**

Không. Nó yêu cầu CDN dừng dùng cached response phù hợp. Object nguồn phải được upload/cập nhật riêng.

**9. Vì sao cần upload assets trước HTML?**

Vì HTML mới có thể tham chiếu đến assets mới. Nếu publish HTML trước khi assets có mặt, người dùng có thể gặp 404 hoặc giao diện bị lỗi.

**10. Khi nào cần private bucket access?**

Khi muốn nội dung được phục vụ qua load balancer/CDN nhưng không cho phép truy cập trực tiếp origin bằng quyền public bucket. Việc cấu hình quyền và cache phải theo mô hình được hỗ trợ.

**11. Vì sao Cloud Build chỉ nên có quyền ghi object thay vì Owner?**

Vì bước publish chỉ cần cập nhật tệp trong bucket. Quyền quản trị toàn project mở rộng blast radius nếu build config hoặc source bị chiếm quyền.

**12. Website không có traffic có chắc chắn không phát sinh chi phí không?**

Không. Load balancer, IP, lưu trữ và một số resource còn tồn tại có thể tiếp tục phát sinh chi phí. Phải kiểm tra inventory và Billing.

## Tài liệu tham khảo

- [Cloud Storage — Host a static website](https://docs.cloud.google.com/storage/docs/hosting-static-website)
- [Cloud Storage — Static website examples and tips](https://docs.cloud.google.com/storage/docs/static-website)
- [Cloud Load Balancing — Global external Application Load Balancer with Cloud Storage buckets](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-buckets)
- [Cloud Load Balancing — Backend buckets overview](https://docs.cloud.google.com/load-balancing/docs/backend-bucket)
- [Cloud CDN — Set up a backend bucket](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-bucket)
- [Cloud CDN — Caching overview](https://docs.cloud.google.com/cdn/docs/caching)
- [Cloud CDN — Invalidate cached content](https://docs.cloud.google.com/cdn/docs/invalidating-cached-content)
- [Cloud Storage — Uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Cloud Storage — Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud CDN — Configure private bucket access](https://docs.cloud.google.com/cdn/docs/configure-private-bucket-access)
- [Google Cloud SDK — gcloud storage objects update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [Google Cloud SDK — gcloud compute url-maps invalidate-cdn-cache](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/invalidate-cdn-cache)
- [Google Cloud — Cloud Build documentation](https://docs.cloud.google.com/build/docs/overview)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)

## Kết luận

Một website tĩnh hoàn chỉnh trên GCP không chỉ là các file HTML được upload vào bucket. **Cloud Storage** cung cấp origin lưu nội dung, **Application Load Balancer** cung cấp HTTPS frontend cho custom domain, **Google-managed certificate** bảo vệ kết nối TLS và **Cloud CDN** giúp phân phối nội dung theo chính sách cache. DNS đưa người dùng đến đúng frontend; IAM và public/private bucket access xác định cách bảo vệ origin; Cloud Build và release manifest giúp cập nhật có thể truy vết.

Đối với production, điều quan trọng nhất là thiết kế tách bạch: **nội dung thực sự công khai mới được public**, HTML và assets có TTL phù hợp, quyền publish được giới hạn, chứng chỉ/DNS được giám sát và luôn có cách rollback. Khi kết hợp thêm dự toán chi phí, synthetic checks và cleanup có kiểm soát, bạn có một dự án thực hành đầy đủ từ xây dựng website đến phát hành và vận hành trên Google Cloud.
