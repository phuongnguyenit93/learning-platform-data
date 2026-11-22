# Version deployment, traffic migration và rollback

> **Chương:** App Engine  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một dịch vụ Java trên **Google App Engine** đang phục vụ khách hàng ổn định ở version `v1`. Nhóm phát triển chuẩn bị phát hành `v2` với tính năng mới nhưng chưa biết hiệu suất thực tế khi gặp traffic production. Nếu chạy `gcloud app deploy` với cấu hình mặc định, version mới thường được **promote nhận toàn bộ traffic ngay**, làm tăng nguy cơ phát hành lỗi trên diện rộng. Thay vào đó, ta sẽ deploy **không promote**, kiểm thử trực tiếp version mới, chia một phần traffic, theo dõi chỉ số rồi chuyển toàn bộ — hoặc **rollback** về version cũ nếu có vấn đề.

Bài học thuộc chương **App Engine** của mô-đun **CLOUD_PROVIDERS_GCP**, nơi người học làm quen Google Cloud từ project/IAM, VPC, Compute Engine, GKE và Cloud Run đến lưu trữ, cơ sở dữ liệu, triển khai, độ tin cậy và chi phí. Ví dụ chính dùng **App Engine Standard, Java 21**, nhưng cũng chỉ rõ điểm khác khi vận hành **App Engine Flexible**.

**Sau bài học, bạn có thể:**

1. Phân biệt **application, service, version, instance** và *traffic allocation*.
2. Deploy một version **chưa nhận traffic** bằng `--version` và `--no-promote`.
3. Kiểm thử bằng **version-specific URL** mà không thay đổi traffic của service.
4. Thiết lập **traffic splitting** theo IP, cookie hoặc random và hiểu hạn chế từng cách.
5. Phân biệt **traffic migration** sang một version với **canary rollout** qua nhiều tỷ lệ.
6. Rollback nhanh về version trước mà không giả định rollback sẽ khôi phục database hoặc secrets.
7. Đọc log/metric theo version, xử lý cold start, sticky sessions, cache và quản lý chi phí các version cũ.

## 1. Mô hình App Engine cần nhớ

Một ứng dụng App Engine gồm một hoặc nhiều **services**; mỗi service có nhiều **versions**; mỗi version chạy trên những **instances** do nền tảng quản lý theo loại môi trường và cấu hình scaling.

~~~mermaid
flowchart TB
  APP["App Engine application\nProject: demo-prod"] --> S1["Service: default\norders-api"]
  APP --> S2["Service: worker"]
  S1 --> V1["Version: v20261101a\n95% traffic"]
  S1 --> V2["Version: v20261119a\n5% traffic"]
  V1 --> I1["Instances v1"]
  V2 --> I2["Instances v2"]
  S2 --> VW["Version riêng của worker"]
~~~

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Application** | App Engine app của project | App-level location và các services; tạo ứng dụng là thao tác riêng |
| **Service** | `default`, `payments`, `worker` | Một đơn vị phục vụ có versions và traffic split riêng |
| **Version** | `v20261119a` | Bản code + runtime + deployment configuration tại thời điểm deploy |
| **Instance** | Tiến trình/VM thực thi version | Tạo/hủy theo automatic, basic hoặc manual scaling |
| **Traffic allocation** | `v1=0.95, v2=0.05` | Tỷ lệ routing ở **cấp service** đối với request không nhắm version cụ thể |
| **Version-specific URL** | `VERSION-dot-SERVICE-dot-PROJECT.REGION_ID.r.appspot.com` | Truy cập version cụ thể để smoke test |
| **Rollback** | Chuyển traffic về `v1` | Quay lại **routing/version**, không đảo ngược dữ liệu ngoài ứng dụng |

Một service có thể có nhiều version tồn tại cùng lúc. **Tạo version không phải cập nhật mọi instance của version cũ tại chỗ**: phiên bản mới là một deployment riêng. Điều này cho phép canary và rollback nhanh **miễn version tốt cũ còn sẵn sàng**.

### 1.1. Những gì thay đổi khi deploy

Khi chạy `gcloud app deploy`, App Engine tải source/artifact, xây dựng nếu cần, tạo hoặc thay version được chỉ định rồi điều chỉnh routing theo cờ `promote`.

- Không chỉ định `--version`: CLI thường tạo **version ID duy nhất**.
- Chỉ định `--version=v20261119a`: gắn tên version đó cho bản build.
- Không dùng `--no-promote`: lệnh deploy **mặc định promote** version mới nhận toàn bộ traffic.
- Dùng `--no-promote`: tạo version mới **nhưng giữ traffic split hiện tại**.

**Cảnh báo nghiêm trọng:** Nếu **deploy đè một version ID đang tồn tại**, App Engine có thể thay thế version cũ và **chuyển traffic ngay**, khiến bạn mất bản cũ để rollback. Vì vậy mỗi lần phát hành nên có **version ID chưa từng dùng**; không tái triển khai với cùng tên để “sửa nóng” một bản release.

### 1.2. Standard khác Flexible ở đâu?

| Chủ đề | App Engine Standard | App Engine Flexible |
| --- | --- | --- |
| Runtime | Managed runtimes, ví dụ Java 21 | Môi trường container/VM linh hoạt hơn |
| Cơ chế scaling/cost | Phụ thuộc automatic/basic/manual scaling và instance class | Dùng VM resources, version cũ có thể còn tốn phí khi không nhận traffic |
| Deployment | `gcloud app deploy`, `--no-promote` | Cùng nhóm lệnh deploy/traffic |
| Traffic splitting | Hỗ trợ chia traffic giữa versions | Hỗ trợ chia traffic giữa versions |
| **Gradual traffic migration với warmup** | Có thể dùng khi được hỗ trợ/cấu hình đúng | **Không hỗ trợ gradual migration giữa Flexible versions** theo tài liệu App Engine |
| Cold start/ready | Cần xem warmup và instance availability | Startup/VM provisioning có thể lâu hơn; phải theo dõi readiness |
| Rollback | Chuyển traffic về version cũ | Chuyển traffic về version cũ; đảm bảo version cũ có capacity |

**Không nhầm** gradual migration với manual canary. Trong Flexible, bạn vẫn có thể **tự chia traffic** theo các bước 5% → 25% → 50% → 100%; đó không phải cơ chế tự động gradual migration của Standard.

## 2. Kế hoạch phát hành an toàn

Giả sử service `default` đang chạy `v20261101a` ở **100%**. Release mới là `v20261119a`. Mục tiêu:

~~~text
T0: v20261101a=100%   v20261119a=0%
    ↓ Deploy version mới với --no-promote
T1: Smoke test URL version mới, kiểm tra logs và dependencies
    ↓ Có xác nhận?
T2: v20261101a=95%    v20261119a=5%
    ↓ Quan sát lỗi/p95/DB và canary cohort
T3: v20261101a=75%    v20261119a=25%
    ↓ Quan sát
T4: v20261101a=0%     v20261119a=100%
    ↓ Tiếp tục theo dõi
T5: Giữ version cũ để rollback trong cửa sổ đã định
~~~

**Lưu ý:** Những mốc thời gian kiểm tra và tỷ lệ cụ thể chỉ minh họa. Với traffic thấp, canary 5% có thể không đủ số request để phát hiện bug hiếm; với dịch vụ quan trọng, cần thiết kế ngưỡng đủ ý nghĩa theo SLO và rủi ro.

### 2.1. Điều kiện trước rollout

- App Engine application/service đã tồn tại đúng project và location; lần đầu phải tạo **default service** trước các services khác.
- Người triển khai có IAM phù hợp cho App Engine/Cloud Build và quyền sử dụng runtime service account nếu cần.
- Build đã qua unit/integration/security tests; artifact và source revision được lưu.
- Version ID **mới**, không trùng version đang phục vụ.
- DB schema/API contracts **tương thích** giữa v1 và v2 trong lúc cùng chạy.
- Các kết nối Cloud SQL, Secret Manager, Pub/Sub hoặc tài nguyên khác được kiểm chứng.
- Dashboard có request count, HTTP 5xx, p95 latency, error logs, resource usage **theo version**.
- Version cũ còn tồn tại, rollback playbook có người phụ trách; ngân sách đủ chạy song song versions.
- Có quyền dừng rollout, thời gian quan sát và quyết định go/no-go cụ thể.

### 2.2. Sơ đồ quyết định

~~~mermaid
flowchart TD
  DEP["Deploy v2 --no-promote"] --> SMOKE{"Smoke test v2 pass?"}
  SMOKE -- "Không" --> FIX["Giữ v1 100%\nSửa build, deploy version mới"]
  SMOKE -- "Có" --> CAN["Canary v2 5%"]
  CAN --> SLO{"5xx, p95, DB, errors ổn?"}
  SLO -- "Không" --> BACK["Rollback: v1=100%"]
  SLO -- "Có" --> RAMP["25% → 50% → 100%"]
  RAMP --> CHECK{"SLO còn đạt?"}
  CHECK -- "Không" --> BACK
  CHECK -- "Có" --> HOLD["Theo dõi, giữ v1 trong rollback window"]
~~~

## 3. Ví dụ Java Standard: app.yaml và health/version endpoint

Bài học không triển khai ứng dụng hoàn chỉnh; giả sử bạn có một dự án **Spring Boot Java 21** đã cấu hình build **executable JAR** và chạy được trên App Engine Standard.

Tệp `app.yaml` tối thiểu cho service `default`:

~~~yaml
runtime: java21
service: default

automatic_scaling:
  min_instances: 0
  max_instances: 5

env_variables:
  APP_ENV: lab
~~~

App Engine Standard Java runtime cung cấp biến `PORT`, `GAE_SERVICE` và `GAE_VERSION`. Ứng dụng phải lắng nghe trên **port do môi trường cung cấp**, không hard-code một port cố định:

~~~yaml
# Ví dụ cấu hình Spring Boot application.yaml (khác app.yaml của App Engine)
server:
  port: ${PORT:8080}
~~~

Tạo endpoint minh họa cho release verification:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
public class ReleaseInfoController {
    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/release")
    public Map<String, String> release() {
        return Map.of(
            "service", System.getenv().getOrDefault("GAE_SERVICE", "local"),
            "version", System.getenv().getOrDefault("GAE_VERSION", "local")
        );
    }
}
~~~

**Giới hạn ví dụ:** `/healthz` trả OK nếu web request được xử lý; chưa kiểm tra database/dependency/logic nghiệp vụ. App production cần readiness metrics riêng, authentication cho endpoints nhạy cảm và không lộ secrets trong response.

Đối với Spring Boot Java 21, cách đóng gói và đường dẫn file cấu hình có thể khác theo Maven/Gradle/plugin. Tham khảo tài liệu App Engine Java để cấu hình entrypoint/JAR phù hợp. Ví dụ dưới đây **giả định app.yaml cùng source/artifact hợp lệ và test được tại local**.

## 4. Deploy version mới nhưng chưa nhận traffic

### 4.1. Kiểm tra ngữ cảnh trước khi thao tác

~~~bash
# Các lệnh chỉ đọc; đảm bảo đang nhắm ĐÚNG project
gcloud config get-value project
gcloud app describe --project=LAB_PROJECT_ID
gcloud app services list --project=LAB_PROJECT_ID

gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

Nếu không có App Engine application, **đừng chạy `gcloud app create` bừa bãi**: location chọn khi khởi tạo không thể chuyển dễ dàng và việc tạo application có hậu quả lâu dài cho project.

### 4.2. Lệnh deploy an toàn

~~~bash
# THAY ĐỔI CLOUD RESOURCES: chỉ chạy trên project lab được phê duyệt
gcloud app deploy app.yaml \
  --project=LAB_PROJECT_ID \
  --version=v20261119a \
  --no-promote
~~~

Kiểm tra version:

~~~bash
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

gcloud app versions describe v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

**Kỳ vọng:** Version `v20261119a` xuất hiện với **0% traffic**, còn `v20261101a` giữ **100%**. Nếu đây là version đầu tiên của service, tình huống routing có thể khác; bài giả định **service đã có version ổn định trước đó**.

### 4.3. Kiểm thử bằng URL version-specific

URL của App Engine sau tháng 2/2020 thường có cấu trúc:

~~~text
# Service default:
https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com

# Service đặt tên khác:
https://VERSION-dot-SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com

# REGION_ID là mã do App Engine cấp; đừng tự dùng tên region như asia-southeast1.
~~~

Có thể dùng gcloud để xem version URL mà không cần tự ghép tên:

~~~bash
gcloud app versions browse v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID \
  --no-launch-browser
~~~

Từ client được phép, kiểm tra `/healthz`, `/release`, endpoint đọc-only đến database/mock, log, startup và các dependency:

~~~bash
# Thay URL thật và chỉ dùng endpoint không nhạy cảm
curl -i "https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com/healthz"
curl -i "https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com/release"
~~~

**Cảnh báo bảo mật:** Version-specific URL **bỏ qua traffic split**; ngay cả version 0% vẫn có thể được gọi trực tiếp nếu ingress/auth cho phép. Nó **không phải một vùng thử nghiệm riêng tư**. Dùng IAM/IAP/ingress hoặc cơ chế bảo vệ phù hợp, không nhúng secrets và không bật debug endpoints công khai chỉ để smoke test.

### 4.4. Vì sao không deploy đè tên version cũ?

Ví dụ production đang chạy `v20261101a`, nhưng CI lại deploy code mới dưới **cùng ID**. Google Cloud cảnh báo việc dùng lại version ID có thể **thay version cũ**, chuyển traffic tức thời và khiến không thể chuyển về binary cũ. Chính sách CI nên:

- Cấp **ID unique** theo build/run, ví dụ `v20261119a`, `v20261119b`.
- Lưu **source commit + build ID + version ID + deployment timestamp + approval**.
- Chặn pipeline nếu version ID mục tiêu đã tồn tại.
- Rollback bằng **routing tới version được giữ**, không rebuild và deploy đè tên cũ.

## 5. Traffic splitting: chia tỷ lệ chứ không phải chia instances

Traffic splitting đặt **trọng số của các versions trong một service**. Ví dụ:

~~~bash
# Có tác động đến request routing của service, chỉ dùng lab
gcloud app services set-traffic default \
  --splits=v20261101a=0.95,v20261119a=0.05 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID
~~~

Cú pháp `--splits=VERSION=WEIGHT,...`; weights được chuẩn hóa theo tỷ lệ, ví dụ `v1=1,v2=1` tương đương 50/50. Lệnh thay đổi **toàn bộ traffic split của service** cho các version được nêu, không phải cộng thêm 5% vào cấu hình đang có.

### 5.1. Chọn thuật toán chia traffic

| Giá trị CLI | Cách quyết định version | Phù hợp | Hạn chế |
| --- | --- | --- | --- |
| `ip` | Hash địa chỉ IP nguồn | Đơn giản, không cần cookie | NAT/proxy làm nhiều users cùng IP; phân phối có thể lệch tỷ lệ |
| `cookie` | Cookie `GOOGAPPUID` phân vào 1.000 buckets | Sticky trải nghiệm người dùng, A/B | Client phải giữ cookie; cache và cookies nội bộ cần lưu ý |
| `random` | Lấy mẫu ngẫu nhiên theo trọng số mỗi request | Stateless requests, phân phối gần tỷ lệ khi lượng lớn | Cùng user có thể gặp nhiều versions, không sticky |

Theo tài liệu traffic splitting, **IP split** có thể thiếu chính xác ở canary tỷ lệ nhỏ hoặc với callers nằm sau cùng NAT. **Cookie split** sử dụng cookie tên `GOOGAPPUID` để ổn định routing; ứng dụng di động hoặc HTTP client cần giữ/forward cookie nếu muốn sticky. **Random** có trong `gcloud app services set-traffic`; cần cân nhắc rủi ro cho session/workflow nhiều request.

~~~mermaid
flowchart LR
  USER["1000 requests / users"] --> SPLIT{"Traffic split\nv1=95%, v2=5%"}
  SPLIT -->|"Theo IP / cookie / random"| A["v1: khoảng 950"]
  SPLIT -->|"Theo IP / cookie / random"| B["v2: khoảng 50"]
  B --> METRIC["So 5xx, p95, saturation\nvới v1 và baseline"]
~~~

**Tỷ lệ thực tế không luôn bằng tỷ lệ cấu hình** trong từng cửa sổ nhỏ; cookie/IP group người dùng, số requests và cache có thể làm lệch mẫu.

### 5.2. Chỉ requests không target version mới chịu traffic split

- URL **service** (không nêu version) được định tuyến theo traffic allocation.
- URL **version-specific** đi thẳng tới version đó, không tính tỷ lệ split của service.
- Các callers nhắm trực tiếp version (task/cron/internal client, tùy cấu hình) có thể tiếp tục gọi version cũ sau khi migration.
- Routing qua `dispatch.yaml`, custom domain hoặc external load balancer có các quy tắc riêng; phải kiểm tra **đường request thực**.

Do đó, **0% traffic không có nghĩa version không nhận request nào**. Trước khi xóa version cũ, kiểm tra version URLs, cron/tasks và phụ thuộc nội bộ.

### 5.3. Cookie splitting và cache/session

Nếu v1 trả HTML tham chiếu file CSS/JS tên không versioned, browser/CDN có thể cache asset từ v1 rồi dùng với v2, gây lỗi giao diện. Biện pháp:

1. Dùng **hashed filenames** cho static assets, đảm bảo tương thích hai versions.
2. Không lưu session quan trọng chỉ trong RAM của instance; dùng shared session storage khi cần.
3. Xử lý cookie `GOOGAPPUID` đúng; client phải lưu cookie giữa requests.
4. Với HTTP cache, xem `Vary: Cookie` và ảnh hưởng đến cache hit ratio; không bật vô điều kiện cho mọi response.
5. So các route quan trọng và workflows nhiều bước ở cả v1/v2.

## 6. Canary rollout nhiều giai đoạn

Sau smoke test, có thể tăng tỷ lệ theo từng bước **với phê duyệt/guardrails**:

~~~bash
# Bước 1: canary 5% cho version mới
gcloud app services set-traffic default \
  --splits=v20261101a=0.95,v20261119a=0.05 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID

# Bước 2: tăng lên 25% CHỈ nếu metric ổn
gcloud app services set-traffic default \
  --splits=v20261101a=0.75,v20261119a=0.25 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID

# Bước 3: tăng lên 50% CHỈ sau review
gcloud app services set-traffic default \
  --splits=v20261101a=0.50,v20261119a=0.50 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID
~~~

**Không chạy ba lệnh liên tiếp không có khoảng quan sát**: đây là **ba quyết định phát hành khác nhau**. Tại mỗi tỷ lệ, xác nhận số request canary đủ ý nghĩa, không có lỗi tài khoản/phiên và database chịu được sự thay đổi.

### 6.1. Checklist go/no-go cho từng bước

| Nhóm metric | Quy tắc so sánh | Khi nào dừng/rollback |
| --- | --- | --- |
| HTTP 5xx | So v2 với v1 trong cùng cửa sổ/loại request | V2 vượt error budget hoặc ngưỡng được duyệt |
| P95/P99 latency | So theo route/traffic volume, có baseline | Tail latency tăng đáng kể vượt SLO |
| Instance startup | Loading requests, cold start, scaling behavior | Tăng timeout/latency do v2 chưa đủ capacity |
| DB/cache | SQL errors, connection count, query latency | V2 gây saturation hoặc lỗi schema |
| Business KPI | Checkout success, thanh toán, đơn hàng | Giao dịch thất bại, double processing |
| Security/compatibility | Auth 401/403, secrets, payloads | Rò rỉ/quyền truy cập hoặc lỗi contract |
| Cost | Instance hours, logs, external dependencies | Chi phí tăng quá ngân sách hoặc không kiểm soát |

**Không chỉ quan sát HTTP status của trang chủ**. Canary có thể 200 ở `/healthz` nhưng lỗi ở chức năng ghi dữ liệu, migrate schema, async workers hoặc background tasks.

### 6.2. Xác minh routing sau mỗi bước

~~~bash
gcloud app services describe default \
  --project=LAB_PROJECT_ID

gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

gcloud app logs read \
  --service=default \
  --version=v20261119a \
  --limit=100 \
  --project=LAB_PROJECT_ID
~~~

Trên Console, vào **App Engine → Versions**, xem % traffic của mỗi version và đường liên kết **Traffic splitting**. Không chỉ dựa vào output của pipeline: routing configuration phải khớp traffic thực tế trong metrics.

## 7. Traffic migration: chuyển toàn bộ về một version

**Traffic migration** là thao tác đưa request routing của **một service** về **một version đích**. Nó khác với canary nhiều bước ở phần trước: kết quả cuối cùng của migration là **100% phiên bản đích**.

### 7.1. Chuyển ngay lập tức

~~~bash
# THAY ĐỔI toàn bộ routing ngay, có thể gây cold-start spike
gcloud app services set-traffic default \
  --splits=v20261119a=1 \
  --project=LAB_PROJECT_ID
~~~

Version cũ `v20261101a` nhận **0% traffic từ URL service thông thường**, nhưng chưa bị xóa. Nếu version mới chưa có instances sẵn sàng, request đầu tiên có thể phải chờ khởi động.

### 7.2. Migration dần bằng warmup trong Standard

~~~bash
# App Engine Standard: yêu cầu migration có kiểm soát tốc độ/capacity
gcloud app services set-traffic default \
  --splits=v20261119a=1 \
  --migrate \
  --project=LAB_PROJECT_ID
~~~

Theo tài liệu App Engine Standard, khi warmup requests được hỗ trợ và bật, nền tảng có thể **tăng dần lượng traffic** sang version đích, để autoscaler tạo và làm nóng instances mới. Với **Java Standard**, warmup được bật theo mặc định; các runtime khác có thể cần cấu hình `inbound_services: [warmup]` theo đời runtime. Warmup là **best effort**, không cam kết loại bỏ mọi loading requests; phải quan sát hiệu suất thực tế.

**Giới hạn đặc biệt:** **Gradual traffic migration không được hỗ trợ giữa những versions chạy App Engine Flexible** theo tài liệu hiện hành. Nếu dùng Flexible hoặc chuyển giữa hai environments, hãy lên kế hoạch **split traffic thủ công theo bước** hoặc migrate ngay, không coi `--migrate` là bảo đảm rollout dần.

### 7.3. Ba khái niệm dễ bị nhầm

| Tác vụ | Ví dụ | Ý định |
| --- | --- | --- |
| **Deploy** | `gcloud app deploy --no-promote` | Đưa code/config mới thành một version, chưa đổi routing |
| **Split traffic** | `--splits=v1=.9,v2=.1` | Cho nhiều versions cùng nhận tỷ lệ requests |
| **Migrate traffic** | `--splits=v2=1 --migrate` | Chuyển đích về v2, có thể làm dần để autoscaler bắt kịp trong Standard |

**Không coi `--migrate` là một canary test có quality gates.** Nếu cần dừng tự động ở 5% khi lỗi tăng, phải xây pipeline canary với quan sát và quyết định riêng.

### 7.4. Warmup và những giới hạn phải hiểu

- Khi version mới chưa có instances, việc bật đột ngột 100% dễ gây tăng response latency.
- App Engine Standard có thể gửi request `GET /_ah/warmup` để tải ứng dụng/caches khi cần; không phải lần nào cũng gửi trước user request.
- Warmup có thể tốn instance hours và cần xử lý nhẹ; đừng dùng warmup chạy migrations, ghi đơn hàng hay tác vụ không idempotent.
- Trong Flexible, việc cung cấp capacity của VM/version cũ và mới cần được chuẩn bị theo cơ chế scaling của Flexible.
- Với `--migrate`, kiểm tra trạng thái quá trình; **đừng tự hứa thời gian chính xác** hoàn tất migration.
- Sau khi đạt 100%, giữ version trước đủ lâu cho rollback, trừ khi quy định khác yêu cầu.

## 8. Rollback: đưa traffic về bản tốt đã biết

Rollback là **chuyển routing** về một version đã được kiểm chứng trước đó. Ví dụ canary v2 bị lỗi thanh toán, quay về v1:

~~~bash
# Có tác động production nếu chạy sai project: kiểm tra service trước
gcloud app services set-traffic default \
  --splits=v20261101a=1 \
  --project=LAB_PROJECT_ID
~~~

**Lệnh này không deploy lại code** và không xóa v2. Nó cập nhật traffic allocation của service để những request thông thường chọn v1.

### 8.1. Runbook rollback trong sự cố

1. **Xác định** project, service, version mới/ổn định và phần traffic hiện tại.
2. **Quyết định** rollback dựa trên error budget, HTTP 5xx, p95, dữ liệu kinh doanh hoặc cảnh báo bảo mật.
3. **Chuyển routing** sang version tốt bằng lệnh trên hoặc Console → App Engine → Versions → Migrate traffic.
4. **Đọc lại traffic split**; kiểm tra requests và lỗi theo từng version, không dừng ở “lệnh exit 0”.
5. **Kiểm tra phiên đang hoạt động**, requests target version trực tiếp, cron/queues/background jobs và cache.
6. **Đối chiếu** database migrations, secrets, feature flags, Pub/Sub/Task queues: các hệ thống này **không rollback cùng code**.
7. **Giữ bằng chứng** incident, gỡ sự cố trong release pipeline; không xóa v2 ngay khi chưa phân tích nguyên nhân.

### 8.2. Đổi traffic là nhanh nhưng chưa bảo đảm không downtime

- Nếu v1 đã scale về 0, quay về có thể gặp **loading latency**; chuẩn bị capacity/warmup khi có thể.
- Nếu rollback diễn ra đúng peak traffic, version cũ có thể không đủ connection pool/CPU/quotas ngay lập tức.
- Requests đang xử lý trên v2 không tự chuyển sang v1 khi routing thay đổi.
- Một số clients gọi trực tiếp v2 URL sẽ **không chịu traffic split** và có thể tiếp tục sử dụng v2.
- Nếu v2 đã thay database schema theo hướng **không tương thích**, v1 có thể crash ngay sau khi nhận traffic.

**Rollback an toàn ≠ lệnh chạy thành công.** Cần xác nhận business metrics trở lại bình thường và dữ liệu vẫn nhất quán.

### 8.3. Rollback sau khi đã xóa version cũ?

Nếu `v20261101a` đã bị xóa, **không thể chuyển routing về version đó**; phải deploy lại artifact/source đã được lưu với version ID mới và xác minh lại. Vì vậy cần chính sách **retention** cho các releases đã được phê duyệt thay vì xóa phiên bản cũ ngay khi traffic bằng 0.

### 8.4. Tình huống schema migration: expand–migrate–contract

Giả sử v2 đổi tên cột `customer_name` thành `buyer_name`. Nếu migration lập tức xóa cột cũ, v1 sẽ lỗi sau rollback. Cách an toàn:

1. **Expand:** thêm `buyer_name` nhưng giữ `customer_name`; v1 vẫn chạy.
2. **Migrate:** v2 đọc/ghi tương thích, backfill dữ liệu, quan sát.
3. **Rollout:** canary v2 rồi full traffic khi dữ liệu nhất quán.
4. **Contract:** chỉ xóa cột cũ **sau khi** đã hết cửa sổ rollback và không client nào dùng.

Tương tự với message formats và APIs: **giữ tương thích ngược trong giai đoạn nhiều versions cùng chạy**.

## 9. Quan sát theo version và ngưỡng quyết định

### 9.1. Lệnh gcloud chỉ đọc

~~~bash
# Tra traffic routing hiện tại
gcloud app services describe default \
  --project=LAB_PROJECT_ID

# Liệt kê versions và traffic allocation
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

# Kiểm tra metadata/config của một version
gcloud app versions describe v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID

# Xem log của v2, giới hạn kết quả
gcloud app logs read \
  --service=default \
  --version=v20261119a \
  --limit=100 \
  --project=LAB_PROJECT_ID

# Theo dõi log liên tục (cần dừng khi kết thúc)
gcloud app logs tail \
  --service=default \
  --version=v20261119a \
  --project=LAB_PROJECT_ID
~~~

**Không in secrets hoặc tokens vào logs**. Với App Engine Standard, request logs và application logs có thể được lọc theo service/version; với Flexible, nguồn request logs có thể khác (ví dụ `nginx.request`).

### 9.2. Dashboard cần có

| Metric | So sánh | Mục đích |
| --- | --- | --- |
| Request count | v1 và v2 theo thời gian | Xác minh canary nhận lượng traffic mong muốn |
| 4xx/5xx rate | Theo version và endpoint | Phát hiện lỗi triển khai; phân biệt lỗi client/server |
| p50/p95/p99 latency | Theo version, route và loại request | Tìm regression không bị che bởi traffic trung bình |
| Instance count / startup latency | v1 và v2 | Đo cold start, warmup và autoscaling |
| Memory/CPU và error logs | Theo version | Phát hiện OOM, crash, resource exhaustion |
| DB connections/queries | Toàn app, version nếu instrumented | Không để hai versions cộng dồn quá DB capacity |
| Business KPIs | Checkout success, invoice creation, job failures | Bảo đảm người dùng vẫn hoàn thành tác vụ |
| Cost | Instance hours, Cloud Build, logs/network | Canh ngân sách khi chạy song song versions |

Trong Cloud Monitoring và Logs Explorer, lọc labels như **service, version** và project; xem cụ thể tên metric/resource types theo runtime/môi trường. **Không so tỷ lệ 5xx của v2 với v1 khi v2 chỉ nhận request từ một cohort khác mà không hiệu chỉnh phân phối**.

### 9.3. Một thang quyết định mẫu

| Điều kiện minh họa | Quyết định |
| --- | --- |
| Smoke test `/release` sai version hoặc kết nối DB lỗi | Dừng, không phân traffic |
| Canary 5% có 5xx cao rõ rệt hơn baseline | Rollback về v1 |
| Lỗi không rõ nhưng chưa đủ số requests để kết luận | Giữ tỷ lệ, thu thêm bằng chứng |
| v2 đạt SLO, business metrics ổn định, dependencies không bão hòa | Tăng tỷ lệ theo phê duyệt |
| Sau 100% có lỗi trong giờ cao điểm | Chuyển về v1 ngay, theo dõi capacity và dữ liệu |

Các ngưỡng định lượng thật phải dựa vào **SLO/error budget**, traffic volume, thống kê và đặc điểm nghiệp vụ; không dùng một công thức phần trăm cứng cho mọi dịch vụ.

## 10. Những vấn đề đặc biệt khi chạy nhiều versions

### 10.1. Session và sticky routing

Cookie split giúp một người dùng thường tiếp tục đến cùng version nếu client duy trì `GOOGAPPUID`; nó **không thay** cơ chế session store của ứng dụng.

- Với API nhiều bước, dùng schema/session format tương thích qua v1/v2.
- Không lưu trạng thái quan trọng chỉ trong RAM của một instance vì autoscaling và migration có thể thay instance.
- Đối với mobile/CLI clients, phải giữ cookies giữa requests nếu muốn sticky.
- Nếu dùng IP splitting với calls từ Google Cloud hoặc nhiều users sau NAT, tỷ lệ canary có thể bị lệch đáng kể.
- Đừng dựa vào stickiness để bảo đảm toàn bộ bước của một giao dịch luôn chạy trong đúng một process.

### 10.2. Cache và assets

Trong split rollout, v1 HTML có thể dẫn tới v2 CSS/JS cached nếu assets cùng tên. Nên dùng versioned filenames hoặc content hashes. Với CDN/Cloud Load Balancing, kiểm tra cache keys, headers và các đường request; đừng tự coi split ở App Engine là canary kiểm soát mọi request đi qua một cache/layer khác.

### 10.3. Background tasks và cron

Traffic split của request từ URL service **không đảm bảo** mọi tác vụ nền/cron hoặc direct-version requests cũng theo tỷ lệ đó. Các task queues, scheduled jobs và app-to-app requests có thể dùng đường routing riêng. Khi rollout:

- Rà soát các cron/task routes và target service/version.
- Đảm bảo xử lý idempotent; hai versions không tạo double processing.
- Không chạy database migrations/cleanup không tương thích trên cả v1 và v2.
- Khi rollback, xác minh producers và consumers cùng hiểu event schemas.

### 10.4. App Engine version URL và kiểm soát truy cập

Version-specific URLs thuận tiện để smoke test khi version nhận 0% traffic, nhưng nếu application chưa hạn chế ingress/authorization, người ngoài vẫn có thể nhắm trực tiếp URL đó. Tương tự, nếu dùng external Application Load Balancer/Cloud Armor làm lớp bảo vệ, hãy cấu hình **App Engine ingress controls** để tránh đường `appspot.com` bypass load balancer tùy kiến trúc.

**Không đưa URL bản canary vào giao diện khách hàng hoặc coi 0% traffic là biện pháp bảo mật.**

## 11. Quản trị vòng đời version và chi phí

### 11.1. Không xóa version đang nhận traffic

~~~bash
# Chỉ xem danh sách trước khi cân nhắc dọn
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

Theo CLI, `gcloud app versions delete` **không cho xóa version còn đang nhận traffic**. Chỉ sau khi chuyển routing đi, hoàn thành cửa sổ rollback, xác minh không còn direct-version callers và có approval mới cân nhắc:

~~~bash
# PHÁ HỦY VERSION: chỉ chạy trên lab/phiên bản đã hết retention
gcloud app versions delete v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

**Không xóa v2 ngay sau rollback** nếu cần thu thập logs/bằng chứng điều tra. Không xóa v1 chỉ vì đã đạt 100% v2 — việc giữ bản trước là yếu tố cốt lõi của rollback.

### 11.2. “Stop version” có giới hạn

Lệnh `gcloud app versions stop VERSION` theo tham chiếu CLI hiện hành chỉ dùng khi service có **manual scaling**. Đừng coi stop là lệnh chung để tắt mọi version **automatic scaling**:

~~~bash
# Chỉ áp dụng khi đủ điều kiện manual scaling; có tác động
gcloud app versions stop VERSION_ID \
  --service=SERVICE_NAME \
  --project=LAB_PROJECT_ID
~~~

Với automatic scaling, quản lý traffic allocation và deletion theo lifecycle/approval; kiểm tra các behavior Standard/Flexible và Console riêng nếu cần. **0% traffic không đảm bảo chi phí bằng 0**, nhất là Flexible hoặc cấu hình `min_instances`/manual scaling.

### 11.3. Dự toán chạy hai versions song song

Các thành phần có thể tăng:

- **Instance hours/VM resources** của v1 và v2 đồng thời, đặc biệt warm instances và Flexible VM.
- Cloud Build, Artifact Registry/source staging và storage artifacts.
- Log/trace/monitoring volume cho cả hai versions.
- Cloud SQL connections, cache, outbound network, Pub/Sub/Task queue tasks.
- Yêu cầu duy trì capacity cho rollback.

Nên đặt **Cloud Billing Budgets** và ngưỡng cảnh báo; sau cửa sổ rollback, quyết định giữ/xóa versions theo retention và yêu cầu kiểm toán. Không dọn theo “version đã 0% traffic” nếu nó còn được gọi trực tiếp.

## 12. Quy trình vận hành từ Console và CI/CD

### 12.1. Google Cloud Console

1. Vào **App Engine → Versions**, chọn project và đúng service.
2. Kiểm tra version cũ, traffic percentages và error rate.
3. Deploy version mới bằng pipeline hoặc CLI với `--no-promote`.
4. Sau smoke test version URL, chọn **Split traffic** để chia 5%/95%.
5. Chọn cơ chế split (IP hoặc cookie) và giám sát theo version.
6. Tăng tỷ lệ khi đáp ứng quality gates; cuối cùng **Migrate traffic** về một version.
7. Khi có lỗi, chọn version ổn định trước và **Migrate traffic** trở lại.
8. Sau cửa sổ rollback, dọn những versions không còn cần theo phê duyệt.

Giao diện các nút có thể thay đổi; không nhấn **Migrate traffic** khi chưa xác minh đang ở đúng project/service và version.

### 12.2. Pipeline release tham khảo

~~~text
Source commit + pull request review
  → Build/test Java artifact
  → Security/dependency scans
  → Tạo release version ID duy nhất
  → Deploy --no-promote
  → Smoke test version-specific URL
  → Chia traffic 5%
  → Metrics gate + approval
  → Chia traffic 25% → 50%
  → 100% và theo dõi sau phát hành
  → Giữ phiên bản tốt trước đó
  → Nếu vi phạm SLO: set-traffic old=1
~~~

**Pipeline không tự suy “deploy success = release success”.** Mỗi giai đoạn cần lưu release record: project, service, version IDs, artifact/source commit, change approver, tỷ lệ traffic, dashboard links, timestamp, lý do rollback nếu có.

### 12.3. Quyền tối thiểu

- **Deployer identity:** quyền cần để deploy App Engine version và sử dụng service account của runtime; role cụ thể tùy App Engine/Cloud Build và tổ chức.
- **Release operator:** quyền quản lý **traffic splitting/migration** trên service, không nhất thiết quyền thay code.
- **Runtime identity:** quyền tới Cloud SQL, Secret Manager hoặc Google APIs đúng resource; không nên dùng service account quyền Editor.
- **Observer:** quyền xem metrics/logs, không cần quyền deploy/xóa version.
- **Admin:** quản lý application/configuration, quotas, IAM và emergency changes với audit.

Không cấp Project Owner/Editor rộng chỉ vì `gcloud app deploy` báo Permission denied. Đọc lỗi, xác định thiếu quyền App Engine, Cloud Build, Artifact Registry, Storage staging hoặc Service Account User rồi cấp ở phạm vi đúng.

## 13. Bảng xử lý sự cố

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Deploy mới làm 100% khách hàng nhận v2 ngay | Quên `--no-promote` | Rollback traffic về v1; sửa pipeline |
| Không thấy version mới | Deploy thất bại hoặc nhắm sai project/service | Xem deploy logs, `gcloud app versions list` |
| Không thể rollback về v1 | V1 bị xóa/ghi đè cùng version ID | Khôi phục artifact, deploy version ID mới; điều tra CI |
| Canary 5% nhận gần 0 hoặc quá nhiều requests | IP NAT, traffic thấp hoặc cookie cohort lệch | Xem split method, sample size, request metrics |
| User qua lại v1/v2 ngoài ý muốn | Random split, đổi IP, client không giữ cookie | Chọn cookie split và shared state |
| `/healthz` trên version URL trả OK nhưng production lỗi | Test không bao quát DB/authorization/business paths | Integration tests, business metrics |
| Chuyển 100% gây spike p95 | V2 chưa có capacity, cold start/warmup | Standard `--migrate` khi phù hợp, chuẩn bị instances |
| Flexible không gradual theo mong đợi | Feature không hỗ trợ như Standard | Chia traffic theo bước thủ công hoặc migrate ngay |
| v1 lỗi sau rollback | Database/schema/secrets đã thay không tương thích | Expand–migrate–contract, phục hồi dependency riêng |
| App Engine log vẫn có v2 sau rollback | Version URL/cron/tasks còn gọi trực tiếp hoặc inflight | Kiểm tra target paths, caller, request logs |
| Cookies/cache gây asset hỏng | CSS/JS files không versioned, session format đổi | Content hashing, compatibility, cache policy |
| 0% traffic nhưng vẫn tính phí | Flexible VMs, min instances/manual, background tasks | Xem scaling/instance hours và dọn có kiểm soát |
| Không delete được version | Version đang có traffic allocation | Đổi split trước; kiểm tra direct callers/retention |
| `versions stop` không hoạt động | Service không dùng manual scaling | Dùng lifecycle phù hợp, không ép stop |
| CI thiếu quyền | App Engine/Cloud Build/SA IAM chưa đúng | Sửa IAM tối thiểu theo error logs |

**Chuỗi điều tra:** đúng project/service → version ID → traffic split → version URL → application logs → backend dependencies → SLO/cost. Tránh thay đổi nhiều yếu tố cùng lúc làm mất dấu nguyên nhân.

## 14. Bài lab thực hành có hướng dẫn

**Điều kiện:** Chỉ chạy trong project lab có App Engine Standard Java 21 service `default` đang phục vụ `v20261101a`. Có artifact mới cho `v20261119a`, người học được quyền deploy/split traffic và có dashboard logs/monitoring. Nếu không có sandbox, hãy làm **phần mô phỏng bảng trạng thái** thay vì chạy lệnh thật.

### Phần A — Xác nhận baseline

1. Dùng `gcloud app services list` và `versions list` xác định service/version đang nhận 100%.
2. Ghi version cũ, source commit, HTTP 5xx/p95 baseline.
3. Kiểm tra database/API backward compatibility và ngân sách chạy hai versions.

### Phần B — Deploy và kiểm tra tách biệt

1. Chạy `gcloud app deploy app.yaml --version=v20261119a --no-promote` ở project lab.
2. Xem output version ID và `versions list`: v2 là 0%.
3. Dùng `gcloud app versions browse ... --no-launch-browser` để lấy version URL.
4. Test `/release` cho ra v2, `/healthz` và một chức năng read-only.
5. Đọc error logs/latency, xác nhận không ghi secrets.

### Phần C — Canary 5% rồi 25%

1. Chọn `--split-by=cookie` nếu muốn sticky users; giải thích vì sao không dùng `ip` khi traffic qua NAT.
2. Áp dụng 95/5, ghi giờ bắt đầu, lượng request thực và metrics.
3. Nếu đạt, cập nhật 75/25; nếu không, rollback.
4. Không chạy cả hai split lệnh liên tiếp khi chưa quan sát.

### Phần D — Migration và rollback thử nghiệm

1. Trong **App Engine Standard**, sau review, chuyển 100% sang v2 (cân nhắc `--migrate`).
2. Xác minh routing, request volume theo version, resource usage.
3. Giả định v2 có HTTP 5xx tăng đột biến; **rollback traffic về v1=1**.
4. Kiểm tra production-like service endpoint hiện trả `GAE_VERSION=v1` cho request được route theo service, trong khi version-specific URL v2 vẫn truy cập được nếu allowed.
5. Trình bày cách ngăn rollback gây lỗi DB khi schema đã đổi.

### Phần E — Báo cáo

| Bằng chứng | Giá trị cần ghi |
| --- | --- |
| Project/service | ID và đúng environment |
| Version cũ/mới | ID unique, source commit |
| Deploy no-promote | v2=0% sau deploy |
| Smoke test | Kết quả theo version URL |
| Canary 5% | Thời điểm, sample size, 5xx/p95 |
| Canary 25% | Thời điểm, sample size, metrics |
| 100% migration | Loại immediate/gradual, kết quả |
| Rollback | v1=100%, lỗi trở lại baseline |
| DB compatibility | Những thay đổi cần/không cần rollback |
| Chi phí | Instance hours, phụ thuộc/metrics bổ sung |
| Cleanup decision | Giữ version cũ bao lâu và vì sao |

**Không cố tình gây lỗi trên production để chứng minh rollback.** Có thể mô phỏng trong code lab hoặc kích hoạt feature flag ở môi trường riêng.

## 15. Bài tập ôn tập và đáp án

1. **Không dùng `--no-promote` khi deploy thì rủi ro gì?** Version mới thường được route 100% traffic ngay.
2. **Deploy v2 ở 0% có thể truy cập không?** Có, qua version-specific URL nếu ingress/auth cho phép.
3. **Một service có hai versions có nghĩa mỗi version chạy đúng 50% số instances?** Không, split là tỷ lệ request, capacity/instances do scaling quyết định.
4. **`v1=2,v2=2` có khác `v1=.5,v2=.5` không?** Không; weights được chuẩn hóa.
5. **Vì sao 5% IP split có thể nhận hơn 5% traffic?** NAT, callers tập trung và phân phối nguồn IP.
6. **Cookie split cần gì ở mobile client?** Giữ/forward `GOOGAPPUID` theo requests.
7. **Random split có giữ cùng user trên một version không?** Không.
8. **Version URL có tham gia traffic split không?** Không; target trực tiếp version.
9. **`--migrate` khác canary?** Mục tiêu 100% một version, có cơ chế tăng dần trong Standard khi hỗ trợ; canary cần nhiều quyết định và metrics gates.
10. **Flexible có gradual migration như Standard không?** Không, theo tài liệu hiện hành; cần chia bước thủ công.
11. **Khi v2 lỗi, lệnh rollback cốt lõi là gì?** `gcloud app services set-traffic default --splits=v1=1`.
12. **Rollback routing có xóa migration DB không?** Không.
13. **Tại sao không tái dùng version ID cũ?** Có nguy cơ ghi đè và mất đường rollback.
14. **Có thể delete version đang nhận traffic?** Không; trước hết phải gỡ traffic allocation.
15. **0% traffic có đảm bảo phí bằng 0?** Không; còn cấu hình scaling, môi trường, version-targeted requests.
16. **`gcloud app versions stop` dùng cho mọi autoscaling version?** Không; CLI stop giới hạn theo manual scaling.
17. **HTTP 200 ở healthz là đủ để promote?** Không; cần business, DB, 5xx, p95 và security checks.
18. **Điểm khác v1/v2 khi nhiều versions cùng chạy là gì?** Có thể chia routing trong khi code/config riêng, nhưng cùng truy cập DB và external dependencies.

## 16. Checklist production và nguồn tham khảo

- [ ] Project/app/service/location đúng; version ID mới và artifact/source có traceability.
- [ ] Deploy **--no-promote**, kiểm thử version URL; không coi 0% là private.
- [ ] Chọn cookie/IP/random split theo loại client, sessions, NAT/cache.
- [ ] Canary có đủ request volume và quality gates theo SLO.
- [ ] Có warmup/capacity plan; phân biệt Standard và Flexible migration.
- [ ] Giữ version ổn định trong rollback window, không deploy ghi đè hoặc xóa sớm.
- [ ] DB/schema/message formats tương thích lúc v1/v2 chạy đồng thời.
- [ ] Giám sát theo service/version và business endpoints, không chỉ HTTP 200.
- [ ] Kiểm tra direct-version URLs, cron/tasks và ingress/security controls.
- [ ] IAM tối thiểu, release approvals, logs không chứa secrets.
- [ ] Budget cho nhiều versions, Cloud Build và phụ thuộc dữ liệu.
- [ ] Có runbook rollback, post-rollback verification và retention/cleanup.

**Tài liệu Google Cloud chính thức:**

- [App Engine overview](https://docs.cloud.google.com/appengine/docs/an-overview-of-app-engine) — application, services, versions.
- [Deploy/test App Engine Standard](https://docs.cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app) — `--no-promote`, version URLs.
- [Deploy/test App Engine Flexible](https://docs.cloud.google.com/appengine/docs/flexible/testing-and-deploying-your-app) — triển khai Flexible.
- [Traffic splitting — Standard](https://docs.cloud.google.com/appengine/docs/standard/splitting-traffic) — IP/cookie split, limitations.
- [Traffic splitting — Flexible](https://docs.cloud.google.com/appengine/docs/flexible/splitting-traffic) — canary cho Flexible.
- [Traffic migration — Standard](https://docs.cloud.google.com/appengine/docs/standard/migrating-traffic) — warmup, immediate/gradual, giới hạn.
- [Traffic migration — Flexible](https://docs.cloud.google.com/appengine/docs/flexible/migrating-traffic) — routing Flexible.
- [App Engine request routing](https://docs.cloud.google.com/appengine/docs/standard/how-requests-are-routed) — service/version URLs và dispatch.
- [Warmup requests](https://docs.cloud.google.com/appengine/docs/standard/configuring-warmup-requests) — tối ưu cold start.
- [Java Standard runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime) — Java 21, `PORT`, `GAE_VERSION`.
- [gcloud app deploy](https://docs.cloud.google.com/sdk/gcloud/reference/app/deploy) — `--version`, `--no-promote`.
- [gcloud app services set-traffic](https://docs.cloud.google.com/sdk/gcloud/reference/app/services/set-traffic) — `--splits`, `--split-by`, `--migrate`.
- [gcloud app versions delete](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/delete) — giới hạn xóa.
- [gcloud app versions stop](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/stop) — chỉ dùng khi manual scaling.
- [App Engine pricing](https://cloud.google.com/appengine/pricing) — instance hours và chi phí.

**Ghi nhớ:** Phát hành ít rủi ro trên App Engine bắt đầu bằng **deploy version mới mà chưa chuyển traffic**, sau đó smoke test, canary theo tỷ lệ có quality gates và migration sang version đích. Khi xảy ra sự cố, **đổi traffic về version tốt đã giữ lại** và xác minh cả ứng dụng lẫn dữ liệu. Rollback mã ứng dụng không thay thế backup, migration tương thích hay quan sát SLO.
