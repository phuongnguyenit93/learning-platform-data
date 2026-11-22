# App Engine application, services và versions

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích quan hệ **Google Cloud project → App Engine application → services → versions → instances**, phân biệt App Engine service với Cloud Run service hoặc Kubernetes Service.
2. Tạo App Engine application trong một project, chọn region đúng ngay từ đầu và triển khai **default service** trước các service khác.
3. Cấu hình **app.yaml**, deploy một ứng dụng Java, xem service/version và dùng URL riêng để kiểm thử một version chưa nhận traffic.
4. Điều phối **traffic splitting, traffic migration, rollback**, hiểu điều kiện sử dụng **--no-promote**, **--split-by** và **--migrate**.
5. Chọn môi trường **standard/flexible**, scaling, danh tính workload, logging và cách tối ưu chi phí.
6. Xử lý các sự cố deployment, routing, cold start, IAM và phát hành; làm bài tập gắn với hệ thống thực tế.

## 1. Mô hình tài nguyên: application → service → version → instance

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tổ chức project, IAM, VPC, triển khai lên Compute Engine, GKE, Cloud Run, lưu trữ và database, bảo vệ tài nguyên và theo dõi chi phí. **App Engine** là lựa chọn **PaaS**: nhóm phát triển tập trung vào mã web service, khai báo cấu hình, còn nền tảng đảm nhiệm phần lớn công việc cấp phát hạ tầng, định tuyến và scaling.

~~~mermaid
flowchart TD
    P["Google Cloud project: shop-dev-001"] --> A["App Engine application<br/>region được chọn một lần"]
    A --> D["Service: default<br/>frontend / Java API"]
    A --> W["Service: worker<br/>backend xử lý"]
    D --> D1["Version: web-v1<br/>traffic 90%"]
    D --> D2["Version: web-v2<br/>traffic 10%"]
    W --> W1["Version: worker-v4<br/>traffic 100%"]
    D1 --> I1["1..N instances"]
    D2 --> I2["1..N instances"]
    W1 --> I3["1..N instances"]
~~~

| Cấp | Bản chất | Ví dụ | Phạm vi cấu hình |
|---|---|---|---|
| **Project** | Ranh giới Google Cloud về IAM, API, billing, quotas | shop-dev-001 | IAM, APIs, budgets, các tài nguyên khác |
| **Application** | Một App Engine application trong project, gắn một region | app của shop-dev-001 | Location, app-level routing |
| **Service** | Một thành phần logic độc lập, thường là frontend/API/worker | default, worker | Tập các versions và traffic riêng |
| **Version** | Một lần phát hành mã + cấu hình của service | web-v2 | Runtime, instance class, scaling, env, phiên bản mã |
| **Instance** | Tiến trình/đơn vị chạy phục vụ request của version | 3 instances của web-v2 | Được tạo/dừng theo scaling và tải |

**Mối quan hệ cốt lõi:** một **service có nhiều versions**, một **version có thể chạy trên nhiều instances**. Deploy thêm một version **không** tạo một application hoặc project mới. Tên *service* của App Engine **không phải** đối tượng Kubernetes Service của GKE.

### 1.1. Ví dụ tách trách nhiệm

Hệ thống bán hàng có hai services:

- **default**: nhận HTTP requests từ trình duyệt, chạy Java/Spring Boot, đọc Cloud SQL và Cloud Storage.
- **report-worker**: xử lý các yêu cầu tạo báo cáo theo luồng ứng dụng được hỗ trợ.

Hai services có thể dùng **runtime, instance class và scaling configuration khác nhau**. Mỗi service phát hành versions và chia traffic **độc lập**; chuyển traffic frontend không tự động chuyển traffic report-worker.

Không xem service boundary là ranh giới bảo mật tuyệt đối: cả hai vẫn thuộc một project, có thể chịu IAM kế thừa hoặc dùng chung App Engine default service account nếu không cấu hình riêng.

## 2. App Engine application: tạo một lần, chọn region cẩn thận

**Một Google Cloud project chỉ có một App Engine application.** Khi tạo app, chọn **region**; sau khi tạo, **không thể đổi region** của app. Một App Engine application nằm trong region và Google vận hành trên hạ tầng nhiều zones của region đó, nhưng điều này không thay cho thiết kế backup, data residency hay disaster recovery.

### 2.1. Chọn region như thế nào?

Đánh giá đồng thời:

- Người dùng ở đâu, mục tiêu độ trễ mạng và nơi đặt **Cloud SQL**, Cloud Storage, Memorystore.
- Region có hỗ trợ **App Engine** và runtime/feature dự định sử dụng hay không.
- Quy định residency, truyền dữ liệu liên region, giá mạng và yêu cầu sẵn sàng.
- Quy trình chuyển môi trường nếu sau này phải đổi region: **tạo project/app mới, di chuyển cấu hình và dữ liệu, đổi DNS/traffic** chứ không sửa region của app hiện có.

**Không chọn region chỉ vì gần người dùng nhất:** nếu database ở region khác, Java API gọi DB liên tục có thể chịu latency, chi phí egress và độ phức tạp HA cao hơn.

### 2.2. Kiểm tra trước khi tạo

~~~bash
gcloud config get-value project
gcloud auth list
gcloud app describe --project=shop-dev-001
gcloud app regions list
~~~

Nếu **gcloud app describe** trả về thông tin application, **không tạo app lần nữa**. Nếu app chưa tồn tại, lệnh tạo chỉ chạy sau khi xác minh region, billing, API và quyền quản trị.

~~~bash
# CHỈ chạy một lần trên project lab đã được phê duyệt.
gcloud app create \
  --project=shop-dev-001 \
  --region=asia-southeast1

gcloud app describe --project=shop-dev-001
~~~

Tên project và region là ví dụ; xác nhận **region xuất hiện trong danh sách App Engine hỗ trợ** trước khi chạy. Việc khởi tạo app là quyết định vị trí dài hạn. Không dùng project production để thử một region ngẫu nhiên.

### 2.3. Default service phải được triển khai trước

Mọi application có một **default service**. **Phải deploy version đầu tiên lên default trước khi tạo/deploy các services khác.**

Nếu tệp **app.yaml** không khai báo **service**, App Engine hiểu là **default**. Khi khai báo service khác (ví dụ **service: report-worker**), tên đó xác định thành phần riêng.

**Không thể xóa default service** theo cách xóa service thường. Có thể quản lý các versions và traffic của nó; nếu muốn ngừng toàn bộ application cần chọn phương án tắt ứng dụng hoặc quản trị project theo quy trình riêng.

## 3. App Engine standard và flexible: chọn môi trường nào?

Cả hai môi trường cùng thuộc mô hình **application/services/versions**, nhưng hạ tầng chạy và scaling khác nhau.

| Tiêu chí | **Standard environment** | **Flexible environment** |
|---|---|---|
| Runtime | Google-managed runtimes được hỗ trợ, ví dụ Java 21/25 | Container runtime tùy chỉnh/được hỗ trợ trên Compute Engine VMs |
| Scale | Automatic, basic, manual theo cấu hình | Automatic/manual theo khả năng môi trường |
| Scale xuống rất thấp | Phù hợp workload nhiều thời điểm ít traffic | Thường duy trì số instance tối thiểu, không giống standard scale-to-zero |
| Khởi động | Có thể gặp cold start | Instances thường tồn tại lâu hơn, có overhead hạ tầng |
| Cấu hình | Runtime + app.yaml, hạn chế môi trường thấp hơn | Quyền tùy chỉnh OS/container và dependencies nhiều hơn |
| Free tier | Một số tài nguyên standard có free quotas theo điều kiện | Không có cùng free tier như standard |
| Chi phí | Instance hours, requests, bandwidth và tài nguyên liên quan | VM/container resources, storage, network và dịch vụ liên quan |
| Migration traffic | Có cơ chế gradual khi bật warmup và đủ điều kiện | **Không hỗ trợ gradual migration**; chuyển ngay |

**Gợi ý:** bắt đầu với **standard** khi Java app dùng runtime được hỗ trợ và không cần can thiệp OS/container. Xem xét **flexible** khi cần binary/system dependencies hoặc tùy biến môi trường mà standard không đáp ứng. Với ứng dụng container HTTP thuần và không cần mô hình App Engine services/versions, **Cloud Run** cũng là phương án cần so sánh.

**Không có tuyên bố “standard luôn rẻ hơn”:** chi phí phụ thuộc workload, minimum instances, requests, CPU/memory, egress, build và database.

## 4. Service: ranh giới triển khai và định tuyến

Một service là thành phần logic của ứng dụng, sở hữu nhiều versions và tập cấu hình độc lập. Có thể:

- Chọn **runtime/instance class/scaling** riêng.
- Phân phối traffic giữa các versions **của chính service đó**.
- Truy cập bằng URL service hoặc điều hướng từ **dispatch.yaml**.
- Deploy và rollback riêng, không bắt buộc đồng bộ với các services khác.

### 4.1. Khi nào tách service?

| Nhu cầu | Quyết định |
|---|---|
| Một Java web app nhỏ, vòng đời triển khai chung | Chỉ **default** thường đủ |
| Frontend và reporting có tần suất tải, SLO, vòng đời khác nhau | Có thể tách **default** / **report-worker** |
| Cần cô lập IAM/trust boundary mạnh, budgets/quotas, dữ liệu nhạy cảm | Cân nhắc **tách projects**, không chỉ App Engine services |
| Đã dùng GKE hoặc Cloud Run cho worker | Không cần chuyển tất cả vào App Engine chỉ để tạo service đồng nhất tên |

### 4.2. Cấu trúc project Java gợi ý

~~~text
shop-web/
  pom.xml
  src/main/java/...                 # Java frontend
  src/main/appengine/app.yaml      # service: default

shop-report/
  pom.xml
  src/main/java/...                 # Java reporting
  src/main/appengine/app.yaml      # service: report-worker

app-routing/
  dispatch.yaml                    # điều hướng ở cấp application
~~~

Đây là **sơ đồ minh họa**, không phải các file được tạo trong repository của bài học. Các **app.yaml** khai báo service khác nhau. **dispatch.yaml** là cấu hình dùng chung cho cả app, không tự nhân bản theo mỗi version.

## 5. Version: đơn vị release, thử nghiệm và rollback

Deploy một bộ mã + cấu hình vào service tạo ra **version**. Khi không chỉ định ID, gcloud tạo version ID; khi chỉ định **--version**, bạn có thể gắn ID phát hành dễ truy vết, chẳng hạn **v20261119-01**.

### 5.1. Version khác instance

~~~text
Service default
├── Version v1: cấu hình runtime/java21, instance class F1
│   ├── Instance A
│   └── Instance B
└── Version v2: cấu hình runtime/java25, instance class F2
    ├── Instance C
    └── Instance D
~~~

Một version có thể mở rộng thêm instances mà **không tạo version mới**. Deploy source hoặc thay scaling setting trong **app.yaml** theo cách phát hành thông thường tạo version mới với cấu hình mới; thay đổi traffic allocation **không sửa nội dung binary của version**.

### 5.2. ID version và promotion

| Hành động | Ý nghĩa |
|---|---|
| Deploy không có **--version** | gcloud tự sinh version ID |
| Deploy với **--version=v2** | Tạo một version có ID chỉ định |
| Deploy mặc định | Theo cấu hình CLI, thường **promote version mới để nhận 100% traffic** trong service |
| Deploy với **--no-promote** | Deploy version nhưng **giữ traffic ở các versions hiện tại** |
| Deploy lại cùng một **version ID** | Có thể **ghi đè** version cũ, ảnh hưởng rollback; nên dùng ID mới |
| Chuyển traffic về version cũ | **Rollback routing**, không tự khôi phục database schema hoặc dữ liệu |

**Thực hành tốt:** dùng **version ID mới cho mỗi release**, thử bằng URL cụ thể của version, chỉ promote sau khi smoke test và readiness đạt. Nếu phát hành version v2 có migration database không backward-compatible, việc định tuyến trở lại v1 có thể không khôi phục ứng dụng; cần thiết kế **expand/contract database migration** và quy trình rollback tương ứng.

### 5.3. Version nhận 0% traffic vẫn có thể có chi phí

Không suy rằng **0% incoming traffic = không còn instance hoặc phí**. Basic/manual scaling, minimum instances, background processing hoặc tính chất flexible environment có thể làm versions còn chạy và tính phí. Phải kiểm tra **App Engine Versions/Instances, billing và cấu hình scaling** trước khi xóa hoặc stop.

## 6. app.yaml: mô tả một service version

**app.yaml** là deployment descriptor của một service version: runtime, service, scaling, instance class và environment variables. Nội dung khác nhau theo **standard/flexible** và runtime; không dùng nguyên YAML của Cloud Run hoặc GKE.

### 6.1. Ví dụ standard Java

Trong Maven project, đặt **src/main/appengine/app.yaml**:

~~~yaml
runtime: java21
service: default
instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 10

env_variables:
  APP_ENV: "lab"
  REPORT_SERVICE_NAME: "report-worker"
~~~

**Giải thích:** **runtime: java21** chọn Java standard được hỗ trợ; tài liệu hiện hành cũng có **java25**. **service: default** chọn frontend. **F2** chọn instance class; **automatic_scaling** quản lý số instances; **min_instances: 0** không giữ instances tối thiểu theo cấu hình. **env_variables** dùng cho cấu hình không nhạy cảm, không chứa password/API key.

**Mặc định mới:** từ tháng 3/2025, **max_instances mặc định là 20** đối với App Engine standard applications mới; app cũ có thể khác. Hãy tự khai báo max_instances theo tải/giới hạn ngân sách và kiểm tra khi deploy, không dựa vào giá trị mặc định từ tài liệu cũ.

### 6.2. Cấu hình service thứ hai

~~~yaml
runtime: java21
service: report-worker
instance_class: F2
automatic_scaling:
  min_instances: 0
  max_instances: 4
env_variables:
  REPORT_MODE: "batch"
~~~

**service: report-worker** tạo service logic khác; nó **không** tự biến HTTP handler thành worker queue. Với công việc bất đồng bộ, tích hợp **Cloud Tasks, Pub/Sub** hoặc nền tảng xử lý batch phù hợp, không trông đợi instance auto-scaled sống mãi để chạy loop.

### 6.3. Automatic, basic và manual scaling

| Kiểu | Hành vi | Phù hợp | Rủi ro |
|---|---|---|---|
| **Automatic** | Tăng/giảm instances theo tải, latency, concurrency | HTTP API, website | Cold starts, burst, quota; cần max/min hợp lý |
| **Basic** | Khởi động khi có request, dừng khi idle | Tải gián đoạn | Startup delay, không lưu state trên local disk |
| **Manual** | Số instances xác định luôn chạy | Cần khả năng giữ tiến trình hoặc độ trễ ổn định | Phí khi không có requests; cần HA |

Ví dụ manual scaling **thay cho** automatic (không khai báo cả hai):

~~~yaml
runtime: java21
service: report-worker
instance_class: B2
manual_scaling:
  instances: 2
~~~

Với **flexible**, cơ chế scaling, loại VM và mô hình chi phí khác standard. Khi nhiều phiên bản có môi trường khác nhau, không mặc nhiên coi **gradual migration** được hỗ trợ giữa chúng.

## 7. Ví dụ Java/Spring Boot: nhận biết version phục vụ

App trả về **service** và **version** để quan sát canary. Biến hệ thống **GAE_SERVICE**, **GAE_VERSION** do App Engine cấp; không tự chỉnh trong app.yaml.

~~~java
package example.appengine;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }

    @RestController
    static class ReleaseController {
        @GetMapping("/health")
        Map<String, String> health() {
            return Map.of(
                "status", "ok",
                "service", System.getenv().getOrDefault("GAE_SERVICE", "local"),
                "version", System.getenv().getOrDefault("GAE_VERSION", "local")
            );
        }
    }
}
~~~

Mã này giả định Maven project dùng **Spring Boot Starter Web**. Ví dụ **pom.xml** tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>shop-app</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Đây là **version minh họa** để người học biết cấu trúc Maven; production phải khóa dependency theo phiên bản đã kiểm thử, theo dõi CVE và đối chiếu runtime support schedule. App Engine Java gen2 hỗ trợ deploy Maven source qua **gcloud app deploy pom.xml**, sử dụng build process của Google Cloud.

Đảm bảo HTTP server lắng nghe cổng **PORT** do App Engine cung cấp. Trong **src/main/resources/application.properties**:

~~~properties
server.port=${PORT:8080}
~~~

**PORT** không được khai báo trong **app.yaml env_variables** vì nền tảng tự đặt giá trị. Với custom entrypoint hoặc web server khác, bind đúng địa chỉ/cổng. Khi chạy trong local development, giá trị fallback 8080 được sử dụng.

**Vì sao trả version?** Khi chia traffic, response **/health** giúp xem request được phục vụ bởi bản nào. Tuy nhiên cookie split có thể giữ mỗi client trong một version; test này chỉ minh họa, không thay thế request/error metrics. Trong production không tiết lộ metadata nhạy cảm qua public endpoint.

## 8. Thực hành A — Deploy default rồi thêm một service

### 8.1. Tiền đề

Giả sử App Engine application **shop-dev-001** đã tồn tại đúng region, có hai dự án Maven. Các lệnh deploy **thay đổi tài nguyên và có thể phát sinh phí**; chỉ thực hiện trên project lab được phép và xác nhận IAM/billing/CI trước.

~~~bash
gcloud config get-value project
gcloud auth list
gcloud app describe --project=shop-dev-001
gcloud app services list --project=shop-dev-001
gcloud app versions list --project=shop-dev-001
~~~

### 8.2. Deploy version đầu tiên lên default

Tại thư mục **shop-web** chứa pom.xml, với **src/main/appengine/app.yaml** khai báo service default:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v1

gcloud app services list --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
~~~

Trong project mới, **default** phải có version trước khi thêm các services. Kiểm tra output lệnh và **dịch vụ đích**; mặc định deploy thường promote version mới (nếu không có cấu hình gcloud thay đổi).

### 8.3. Deploy report-worker

Sau khi default đã hoạt động, trong thư mục **shop-report**:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=report-v1

gcloud app services list --project=shop-dev-001
gcloud app versions list \
  --service=report-worker \
  --project=shop-dev-001
~~~

File app.yaml của thư mục **shop-report** **phải có** dòng **service: report-worker**. Quên khai báo này có thể vô tình deploy vào default. Nên dùng service-specific release checklist và IAM/deploy identity riêng cho môi trường thật.

### 8.4. Lấy URL thật

~~~bash
gcloud app browse --project=shop-dev-001 \
  --service=default --no-launch-browser

gcloud app browse --project=shop-dev-001 \
  --service=report-worker --version=report-v1 \
  --no-launch-browser
~~~

Gọi HTTP **/health** ở frontend nếu phiên bản đã deploy endpoint đó. Nếu report-worker không có endpoint /health, 404 tại đường dẫn đó không tự chứng minh service lỗi.

## 9. Routing: default URL, service URL và version URL

App Engine định tuyến bằng **hostnames**, **dispatch.yaml** hoặc kết hợp **Cloud Load Balancing**.

### 9.1. Ba loại hostname

| Mục đích | Dạng URL minh họa | Hành vi |
|---|---|---|
| Application/default | **https://PROJECT_ID.REGION_ID.r.appspot.com** | Vào default service theo traffic allocation |
| Một service | **https://SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com** | Vào service theo traffic allocation riêng |
| Một version | **https://VERSION-dot-SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com** | Nhắm trực tiếp version, **không theo traffic split** |

**REGION_ID** là mã region rút gọn do Google cấp, **không nhất thiết giống** chuỗi **asia-southeast1** truyền cho gcloud app create. Dùng **gcloud app browse --no-launch-browser** để lấy URL thực tế, tránh tự ghép hostname.

Với **HTTPS appspot.com**, các nhãn dịch vụ/phiên bản sử dụng **-dot-** để phân tách khi nhắm cụ thể. Custom domain có quy tắc host riêng; không mặc định URL custom domain nhận cùng cách định tuyến.

### 9.2. URL của version không phải bí mật

Version **web-v2** deploy bằng **--no-promote** vẫn có URL riêng:

~~~bash
gcloud app browse \
  --project=shop-dev-001 \
  --service=default \
  --version=web-v2 \
  --no-launch-browser
~~~

Nếu application public và không có kiểm soát xác thực bổ sung, bất kỳ người nào biết URL version vẫn có thể gọi vào đó. **0% traffic từ service URL không đồng nghĩa private endpoint**. Không để debug/admin routes không được bảo vệ chỉ vì version chưa được promote.

### 9.3. dispatch.yaml: chọn service theo path

Ví dụ file **dispatch.yaml** áp dụng cho application:

~~~yaml
dispatch:
  - url: "*/reports/*"
    service: report-worker
  - url: "*/api/*"
    service: default
~~~

Sau khi cả hai services đã được deploy:

~~~bash
gcloud app deploy dispatch.yaml --project=shop-dev-001
~~~

**dispatch.yaml là cấu hình toàn app**, không gắn với một version cụ thể. Rules xét **theo thứ tự**, rule đầu tiên khớp thắng; các giới hạn pattern/host phải theo tài liệu. **Targeted routing URLs** nhắm trực tiếp service/version có thể bypass dispatch rules. Với external HTTPS Load Balancer, có thể còn lớp routing phía trước App Engine.

### 9.4. Soft routing

Nếu một **appspot.com hostname** nhắm service/version không tồn tại, một số requests có thể **soft route** về default service. Vì vậy HTTP 200 không chứng minh đã gọi đúng worker/version. Đối chiếu hostname thật, **GAE_SERVICE/GAE_VERSION**, Cloud Logging và phiên bản đang nhận traffic. Hostnames không hợp lệ trên custom domain thường có hành vi 404 khác.

## 10. Traffic splitting: canary và A/B testing

**Traffic splitting** phân request giữa **các versions của cùng một service** theo tỷ trọng. Nó áp dụng cho **service URL** hoặc route tới service không chỉ định version; **không** áp dụng cho URL nhắm trực tiếp một version.

### 10.1. Ví dụ 90/10

Giả sử service **default** có:

- **web-v1**: đã phát hành, đang nhận 100%.
- **web-v2**: mới deploy, đã kiểm thử trực tiếp.

Chạy:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v1=0.9,web-v2=0.1 \
  --split-by=cookie
~~~

Sau đó kiểm tra:

~~~bash
gcloud app services describe default --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
~~~

**Các tỷ trọng** được chuẩn hóa; 0.9/0.1 tương ứng mục tiêu **90% / 10%**. Kết quả quan sát trong thời gian ngắn có thể khác vì mẫu requests nhỏ, cookie stickiness, caches và IP distribution.

### 10.2. Split theo IP, cookie hoặc random

| Phương pháp | Đặc điểm | Cần lưu ý |
|---|---|---|
| **ip** (mặc định) | Hash địa chỉ IP người gửi, thường giữ người gửi cùng một version | NAT/proxy làm nhiều người chia IP; thiết bị di động đổi IP |
| **cookie** | Cookie **GOOGAPPUID** gắn người dùng vào nhóm version | Tốt cho A/B người dùng, cần lưu/forward cookie trong clients; cân nhắc caching |
| **random** | Phân request độc lập theo tỷ trọng | Không bảo đảm một người dùng luôn ở cùng version |

Ví dụ cookie:

~~~text
Người dùng A có cookie nhóm web-v1:
  request 1 → web-v1
  request 2 → web-v1

Người dùng B có cookie nhóm web-v2:
  request 1 → web-v2
  request 2 → web-v2
~~~

Trong hệ thống thương mại điện tử, cookie split có thể giúp người dùng có trải nghiệm A/B ổn định; tuy nhiên nếu APIs được gọi qua mobile/native clients hoặc giữa các services, cần quản lý/forward cookie đúng cách. Nếu tất cả traffic đi qua cùng proxy IP, **IP split** có thể lệch khá xa tỷ trọng mong muốn.

### 10.3. Điều kiện để canary an toàn

Trước khi chuyển 10% traffic:

1. **Version v2** đã được triển khai với **--no-promote**, smoke test qua version URL.
2. **Database schema, message formats, session state** tương thích giữa v1/v2; không để state duy nhất trong memory của một instance.
3. Có metrics/alerts cho **HTTP 5xx, p95/p99 latency, errors nghiệp vụ, billing**, với service/version labels.
4. Thiết kế rollback nhanh bằng lệnh **set-traffic**.
5. Có phương án xử lý ảnh hưởng nếu v2 bị lỗi dù chỉ 10% khách hàng.

**Traffic splitting không phải feature flag ở mức từng API route.** Nếu muốn chỉ cho nhóm nhân viên xem tính năng theo danh tính, cần logic ứng dụng hoặc công cụ feature flag tương ứng; cookie split chỉ giúp gán phiên bản theo request/client.

## 11. Migrate traffic, rollback và phát hành không gián đoạn

### 11.1. Deploy v2 mà chưa nhận traffic

~~~bash
# Trong project Java chứa pom.xml / app.yaml đúng service.
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v2 \
  --no-promote

# In URL version v2 để smoke test
gcloud app browse \
  --project=shop-dev-001 \
  --service=default \
  --version=web-v2 \
  --no-launch-browser
~~~

**--no-promote** giữ split hiện tại, **không** có nghĩa version mới đã được bảo mật hoặc không dùng tài nguyên. Mọi kiểm thử phải xác nhận chính xác version được nhắm và phiên bản ứng dụng thực sự phục vụ.

### 11.2. Chuyển 100% traffic ngay

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v2=1
~~~

Đây là thao tác routing, không tạo bản build mới. Khi v2 chưa có instances sẵn sàng, có thể có **latency spike** do cold start. Theo dõi readiness, load và warmup trước khi chuyển.

### 11.3. Gradual migration khác traffic splitting

Trong **App Engine standard**, **--migrate** có thể đưa traffic dần từ version cũ sang một version mới khi có **warmup requests** và các điều kiện thích hợp, giúp autoscaler tạo instances trước khi nhận toàn bộ tải:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v2=1 \
  --migrate
~~~

**Không mặc định --migrate luôn chuyển dần.** Nếu warmup requests không được bật, traffic có thể chuyển **ngay**. **Flexible environment không hỗ trợ gradual traffic migration**; chuyển ngay sang version đích. Nếu chuyển giữa versions ở standard/flexible khác môi trường, cũng có điều kiện buộc chuyển ngay.

Với Spring Boot/Java, xem tài liệu **warmup requests** của Java runtime để bật và kiểm thử phù hợp; đừng sao chép cấu hình warmup dành riêng cho runtime khác mà không xác nhận.

### 11.4. Rollback routing

Nếu metrics canary xấu, đưa toàn bộ traffic về v1:

~~~bash
gcloud app services set-traffic default \
  --project=shop-dev-001 \
  --splits=web-v1=1

gcloud app versions list \
  --service=default \
  --project=shop-dev-001
~~~

Đây là **rollback routing**, thường nhanh hơn deploy lại mã, nhưng chỉ an toàn nếu v1 còn tồn tại/hoạt động và **database, event schemas, secrets, external APIs** vẫn tương thích. Nếu v2 đã xóa dữ liệu hoặc thay schema không tương thích, rollback phiên bản mã có thể không khôi phục hệ thống.

### 11.5. Runbook triển khai theo giai đoạn

~~~mermaid
flowchart TD
    A["Build/test Java + kiểm tra config"] --> B["Deploy v2 --no-promote"]
    B --> C["Smoke test URL version v2"]
    C --> D{"Health, IAM, DB migrations OK?"}
    D -->|Không| X["Giữ traffic v1, sửa và deploy bản mới"]
    D -->|Có| E["Split 90% v1 / 10% v2"]
    E --> F{"Error rate và latency OK?"}
    F -->|Không| R["Rollback --splits=v1=1"]
    F -->|Có| G["Tăng 50% rồi 100%"]
    G --> H["Theo dõi SLO, dọn versions không dùng"]
~~~

**Lưu ý:** với một endpoint public và nhiều requests mỗi người dùng, **10% requests** không nhất thiết bằng **10% người dùng**. Chọn phương pháp splitting và tiêu chí quan sát phù hợp trước khi chạy một thí nghiệm A/B có kết luận kinh doanh.

## 12. Quản lý services, versions và instances sau khi deploy

### 12.1. Các lệnh chỉ đọc hữu ích

~~~bash
gcloud app services list --project=shop-dev-001
gcloud app versions list --service=default --project=shop-dev-001
gcloud app versions list --hide-no-traffic --project=shop-dev-001
gcloud app instances list --service=default --project=shop-dev-001
gcloud app services describe default --project=shop-dev-001

gcloud app logs read \
  --service=default \
  --version=web-v2 \
  --limit=50 \
  --project=shop-dev-001
~~~

**gcloud app versions list --hide-no-traffic** lọc versions không nhận traffic từ routing; không đủ để kết luận versions đó đã dừng và không có chi phí.

### 12.2. Stop và delete không giống nhau

~~~bash
# Cẩn thận: dừng một version (phụ thuộc loại scaling)
gcloud app versions stop \
  --service=default \
  web-v2 \
  --project=shop-dev-001

# Xóa một version chỉ sau khi đã loại khỏi traffic allocation.
gcloud app versions delete \
  --service=default \
  web-v2 \
  --project=shop-dev-001
~~~

**Delete là thao tác destructive**, không thể dùng lại source/config của version đó chỉ bằng chuyển traffic. Không thể xóa version **đang nhận traffic**. Nếu định xóa cả service không phải default, phải xét mọi versions của service và lưu lại policy/config theo change control. **Không thể xóa default service** theo lệnh xóa service thông thường.

Với auto-scaled standard versions, thao tác **stop** có hạn chế; xác nhận scaling type và cách dừng phù hợp trong tài liệu/runtime thực. Không dùng stop như “giải pháp giảm phí chắc chắn” mà chưa kiểm tra Instances/Billing sau đó.

### 12.3. Vì sao không nên giữ quá nhiều versions?

- **Manual/basic/flexible/min_instances** có thể làm instances tiếp tục dùng tài nguyên.
- Nhiều versions khiến thông tin routing, IAM, config drift và đối tượng chịu trách nhiệm khó theo dõi.
- Các artifacts staging/build, logs và storage liên quan có thể phát sinh chi phí.
- Xóa quá sớm mất phiên bản **rollback**.

**Quy trình tốt:** giữ số versions theo retention có chủ đích, đánh dấu bản release đáng tin cậy, chỉ dọn versions không còn traffic/rollback dependency và đối chiếu chi phí sau cleanup.

## 13. IAM, service identity và kết nối tài nguyên GCP

Một App Engine version có thể gọi **Cloud Storage**, **Cloud SQL**, **Secret Manager** và các Google Cloud APIs. Cần tách **danh tính triển khai** khỏi **danh tính chạy ứng dụng**.

| Principal | Cần làm gì? | Quyền gợi ý |
|---|---|---|
| **Developer/CI deployer** | Tạo version, cấu hình service | App Engine Deployer và quyền dùng service account; có thể cần quyền Cloud Build/staging theo project |
| **Build service account** | Build mã Java và upload artifacts cần thiết | Quyền Cloud Build, Artifact Registry, staging tương ứng |
| **App Engine runtime service account** | Truy cập data APIs khi ứng dụng chạy | Bucket Object Viewer, Secret Accessor, Cloud SQL Client theo nhu cầu thực |
| **Release operator** | Chuyển traffic, rollback, dọn version | Quyền quản lý App Engine traffic/versions phù hợp |
| **Security/auditor** | Xem IAM, deployments, logs | Role read-only/audit theo phạm vi |

### 13.1. Default service account không nên có quyền rộng mặc định

App Engine có default service account truyền thống dạng **PROJECT_ID@appspot.gserviceaccount.com**, nhưng chính sách quyền mặc định ở các projects mới đã thay đổi. **Không mặc định account đó có Editor**, cũng không nên cố cấp Editor để “làm cho ứng dụng chạy”.

Khi triển khai có thể chỉ định service account dành riêng cho version:

~~~bash
gcloud app deploy pom.xml \
  --project=shop-dev-001 \
  --version=web-v3 \
  --no-promote \
  --service-account=shop-web-runtime@shop-dev-001.iam.gserviceaccount.com
~~~

Service account phải tồn tại; principal thực hiện deploy phải có quyền **sử dụng** nó. Runtime account chỉ nên có roles trên tài nguyên cần thiết:

- **roles/storage.objectViewer** trên bucket chứa ảnh đọc-only.
- **roles/secretmanager.secretAccessor** trên đúng secret, nếu Java SDK đọc secret.
- **roles/cloudsql.client** nếu kết nối Cloud SQL qua connector/proxy theo mô hình được hỗ trợ; database authentication là bước riêng.

**IAM không tự bảo đảm truy cập mạng** đến database private IP. Với VPC/private service connectivity, phải kiểm tra VPC egress, serverless connector, firewall và Cloud SQL architecture phù hợp cho standard/flexible.

### 13.2. Không nhúng khóa dài hạn vào app.yaml hoặc image

**env_variables** của app.yaml có thể hiện cho người có quyền đọc cấu hình. Tránh đặt access token, private key hoặc DB password ở đó. Dùng **Secret Manager** với **Application Default Credentials** và phân quyền secretAccessor phù hợp; giảm quyền truy cập source/CI logs. Cân nhắc phương án secret injection theo runtime/công cụ đã được tổ chức kiểm duyệt.

**Các services/versions dùng chung project không tự được cô lập IAM**: phải đặt service accounts riêng, review principal kế thừa và kiểm tra các API permissions thực. Những thay đổi IAM có thể khiến một version đã được deploy gặp lỗi runtime mà không cần redeploy.

## 14. Theo dõi hiệu năng, chi phí và tính sẵn sàng

### 14.1. Các chỉ số cần quan sát theo service/version

| Nhóm | Chỉ số | Khi nào cần hành động |
|---|---|---|
| **HTTP** | Request count, 4xx/5xx, p50/p95/p99 latency | Canary v2 làm tăng errors hoặc latency |
| **Scaling** | Instance count, instance class, cold-start/startup latency | Quá nhiều instances hoặc tải tăng mà không scale |
| **Runtime** | JVM heap, GC pauses, exceptions, health/readiness | App Java thiếu memory, startup chậm |
| **Database/storage** | Cloud SQL connection count, query latency, object errors | App chỉ lỗi khi backend bị nghẽn |
| **Release** | Traffic distribution, deployed versions, log labels | Version mới nhận traffic ngoài ý muốn |
| **Cost** | Instance hours, egress, requests, build/staging, database | Quota hoặc ngân sách tăng đột ngột |

Kiểm tra **App Engine dashboard**, **Cloud Monitoring**, **Cloud Logging**, **Error Reporting** và **Cloud Billing reports**. Với thí nghiệm A/B, phải phân biệt **version logs**; tổng latency của service có thể che khuất lỗi chỉ xảy ra trên v2.

### 14.2. Những chi phí dễ bỏ sót

- Một service có nhiều versions **manual/flexible/min_instances** có thể giữ resources đang tính phí dù một version nhận 0% traffic.
- **max_instances** cao có thể gây chi phí tăng khi peak/bot traffic, đồng thời tạo nhiều connections Cloud SQL làm quá tải DB.
- Thay đổi **instance_class** và scaling thresholds ảnh hưởng chi phí CPU/memory.
- Static files, Cloud Storage, Cloud SQL, network egress, Cloud Build, logging có bảng giá/quota riêng.
- Standard có **free usage quota theo điều kiện**, không phải miễn phí vô hạn; flexible không có cùng free tier.

Hãy đặt **Cloud Billing budget alerts**, theo dõi per-service cost và đặt alarms theo requests/instance spikes. **Budget alert không phải cơ chế tự động ngắt tài nguyên**. Trước khi tăng min instances để khử cold start, so sánh cải thiện SLO với phí phát sinh.

### 14.3. Stateless và an toàn trong rollout

App Engine instances có thể bị khởi tạo lại, thay thế hoặc dừng. Với Java:

1. **Không lưu session/giỏ hàng/đơn hàng chỉ trong memory hoặc local filesystem** của instance.
2. Dữ liệu giao dịch vào **Cloud SQL/Firestore/Spanner** theo use case; object vào **Cloud Storage**.
3. Dùng connection pooling có giới hạn để nhiều instances không vượt Cloud SQL maximum connections.
4. API nên **idempotent** cho retry/timeout khi phù hợp, tránh tạo đơn hàng trùng.
5. Cấu hình **graceful shutdown**, timeout, health checks và khả năng rollback.
6. Ưu tiên **database migrations backward-compatible** giữa các versions đang chia traffic.

## 15. Troubleshooting App Engine application, services và versions

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| **gcloud app create** báo đã tồn tại | Project chỉ có một application | **gcloud app describe**, region hiện tại |
| Muốn đổi region App Engine | Region cố định từ khi tạo | Cần project/app mới và migration plan |
| Deploy service mới không thành công | Chưa deploy **default** đầu tiên | App versions list, deploy default trước |
| Deploy report-worker nhưng chỉ thấy default | Thiếu **service: report-worker** trong app.yaml | app.yaml thật trong Maven build/staging |
| Java deploy thành công nhưng app trả 5xx | Sai port, startup error, thiếu env/IAM hoặc phụ thuộc | Cloud Build output, **gcloud app logs read**, JVM logs |
| /health trả về version không mong đợi | URL/dispatch/traffic split/cookie | app browse, service describe, GAE_VERSION |
| **--no-promote** nhưng URL version truy cập được | Hành vi đúng; version URL không bị traffic split chặn | Kiểm tra auth của endpoint, không dựa vào 0% traffic |
| Canary 90/10 nhưng chỉ thấy một version | Cookie/IP stickiness, mẫu requests nhỏ, cache | --split-by, client cookies, metrics version |
| **--migrate** chuyển ngay | Warmup chưa bật hoặc environment không hỗ trợ gradual | Warmup, standard/flexible, traffic migration docs |
| Request tới service không tồn tại vẫn trả 200 | Appspot **soft routing** về default | Check hostname, service/version in response |
| Version cũ 0% vẫn có phí | Manual/basic/flexible, min instances hoặc resource khác | Instances, version scaling, Billing |
| Không xóa được version | Version còn traffic | Set-traffic về version khác trước; xác minh |
| App gặp 403 khi đọc GCS/Secret Manager | Runtime service account thiếu quyền | Service identity, bucket/secret IAM; không cấp Owner |
| Image/deploy build lỗi | Build service account, staging bucket, dependency/runtime lỗi | Cloud Build logs, deployer IAM, Maven dependency |
| App bị quá tải dù Cloud Run/GKE khác vẫn khỏe | max_instances, DB pool, instance class, quota | Metrics từng service/version và backend |

**Quy trình khoanh vùng:**

1. **Xác nhận project và App Engine application**: không nhìn nhầm project hoặc region.
2. **Xác nhận service/version đích**: app.yaml, gcloud output và hostname.
3. **Phân biệt deployment lỗi với request lỗi**: Cloud Build/deployment logs khác runtime HTTP logs.
4. **Đọc traffic allocation** và phiên bản đang nhận requests; lưu ý cookies/IP.
5. **Kiểm tra identity/IAM** và kết nối tới database/storage nếu Java lỗi lúc runtime.
6. **Đo instance count/cold start**, quotas và billing nếu lỗi chỉ khi traffic tăng.
7. **Rollback traffic** khi canary thất bại, giữ logs/release artifacts để điều tra và thử lại bằng version ID mới.

## 16. Tình huống tổng hợp: phát hành Java API trên App Engine

Đội sản phẩm **Sao Mai** có một frontend Java truy cập Cloud SQL và Cloud Storage:

| Thành phần | Chọn | Lý do |
|---|---|---|
| Web/API | App Engine standard, **default** service | Mã Java phù hợp managed runtime |
| Báo cáo | **report-worker** service | Scale và phát hành độc lập |
| Dữ liệu đơn hàng | Cloud SQL PostgreSQL | Transaction và backup managed |
| Ảnh hóa đơn | Cloud Storage bucket private | Object storage và IAM |
| Phiên bản release | **web-v1**, **web-v2** | Triển khai canary và rollback |
| Runtime identity | Service account riêng theo workload | Least privilege; không dùng key JSON |

### 16.1. Đợt phát hành an toàn

~~~mermaid
flowchart TD
    B["Build + tests + security review"] --> D["Deploy web-v2 --no-promote"]
    D --> T["Test direct version URL"]
    T --> C{"Smoke/DB/IAM OK?"}
    C -->|Không| FIX["Sửa code rồi deploy version mới"]
    C -->|Có| S["Split web-v1:90 / web-v2:10"]
    S --> O["Quan sát 5xx, p99, DB connections"]
    O --> DEC{"SLO đạt?"}
    DEC -->|Không| R["Rollback traffic về web-v1"]
    DEC -->|Có| P["Promote 100% web-v2"]
    P --> K["Giữ v1 cho rollback, dọn theo retention"]
~~~

Giả sử tại 10% traffic, v2 tăng p95 latency từ 150 ms lên 900 ms do tạo DB connection mới theo mỗi request. Đội ngừng rollout, trả traffic về v1, khắc phục connection pooling rồi deploy **web-v3** thay vì sửa đè nội dung version v2.

### 16.2. Ma trận nghiệm thu

| Phép thử | Kỳ vọng |
|---|---|
| Deploy default đầu tiên | Application có default version |
| Deploy report-worker | Service thứ hai xuất hiện, không làm thay default |
| web-v2 --no-promote | Traffic default vẫn đến v1 |
| Gọi URL version web-v2 | Nhận v2 bất kể split service |
| Split 90/10 theo cookie | Duy trì affinity trong phạm vi cookie |
| web-v2 thiếu Storage IAM | Lỗi backend được phát hiện, không cấp quyền toàn project |
| Rollback traffic | Mọi request mới qua service URL chuyển về v1, trừ targeted URLs/caches |
| Database migration | v1 và v2 cùng hoạt động với schema trong thời gian canary |
| Dọn version | Không xóa bản còn traffic/được giữ để rollback |
| Billing | Đo tác động của instances và resources ngoài App Engine |

## 17. Bài tập có đáp án

### Bài tập A — Xác định cấu trúc

Một project có **một App Engine application**, hai services **default** và **analytics**, mỗi service ba versions; tại một thời điểm mỗi version chạy hai instances.

**Hỏi:** Có bao nhiêu App Engine applications, services, versions, instances?

**Đáp án:** **1 application, 2 services, 6 versions, 12 instances**. Instances là đơn vị chạy, không phải bản phát hành.

### Bài tập B — Lỗi khi tạo region

Project đã tạo application tại region A. Nhóm vận hành muốn dùng region B vì Cloud SQL ở B.

**Hỏi:** Có thể chạy **gcloud app create --region=B** để đổi không?

**Đáp án:** Không. **Region đã chọn không đổi được**; phải tạo ứng dụng trong project khác và chuyển dịch source, cấu hình, dữ liệu và DNS/traffic theo kế hoạch.

### Bài tập C — Tìm lỗi app.yaml

~~~yaml
runtime: java21
instance_class: F2
automatic_scaling:
  max_instances: 5
~~~

File dùng cho report-worker, nhưng deploy xong chỉ thấy **default**.

**Đáp án:** Thiếu **service: report-worker** nên version được deploy vào default. Thêm trường service đúng rồi **deploy một version mới**; kiểm tra traffic do thao tác nhầm gây ra.

### Bài tập D — Canary và URL cụ thể

web-v1 nhận 90%, web-v2 nhận 10% theo cookie. Một tester luôn gọi URL **web-v2-dot-default-dot-...** và chỉ thấy v2.

**Hỏi:** Traffic split có hoạt động sai?

**Đáp án:** Không. **Version URL** nhắm trực tiếp v2, **bypass service-level traffic split**. Kiểm thử split qua URL không chỉ định version và thống kê trên nhiều clients/cookies.

### Bài tập E — Chọn phương pháp splitting

Ứng dụng mobile gọi HTTP API từ một gateway NAT; cần A/B theo người dùng, nhưng mỗi user có session riêng.

**Hỏi:** IP split hay cookie split phù hợp hơn?

**Đáp án:** **Cookie split** phù hợp hơn để duy trì affinity người dùng nếu mobile client quản lý/forward GOOGAPPUID. IP split qua gateway NAT có thể gom nhiều users thành một nhóm; random split có thể đổi version giữa requests của cùng user.

### Bài tập F — Deploy không đổi traffic

**Yêu cầu:** Viết lệnh deploy Maven version **web-v3** nhưng giữ toàn bộ traffic ở web-v1.

**Đáp án:**

~~~bash
gcloud app deploy pom.xml --project=shop-dev-001 \
  --version=web-v3 --no-promote
~~~

Sau đó dùng **gcloud app browse --service=default --version=web-v3 --no-launch-browser** để smoke test riêng.

### Bài tập G — Rollback và tương thích database

web-v2 đổi một cột bắt buộc trong Cloud SQL khiến web-v1 không còn ghi được. Khi v2 lỗi, nhóm định dùng **set-traffic default --splits=web-v1=1**.

**Hỏi:** Đây có phải rollback hoàn chỉnh không?

**Đáp án:** Không. Lệnh chỉ sửa routing; **schema database** vẫn bị thay đổi. Cần kế hoạch **expand/contract**, migration tương thích hai versions hoặc restore dữ liệu/schema theo quy trình DB. Thử rollback trong staging trước phát hành.

### Bài tập H — Chi phí và xóa version

Một App Engine flexible version cũ nhận 0% traffic nhưng vẫn chạy instances. Nhóm muốn xóa ngay để giảm phí.

**Hỏi:** Cần kiểm tra gì?

**Đáp án:** Xác nhận không có targeted URL, jobs, dependency, phiên bản dự phòng rollback hoặc traffic còn tới nó; kiểm tra instances/billing và chuẩn bị artifact/rollback thay thế. **0% traffic không đảm bảo hết chi phí**, và delete version là thao tác destructive.

## 18. Tổng kết và tài liệu tham khảo

**Sáu nguyên tắc cần nhớ:**

1. **Project → application → services → versions → instances** là phân cấp App Engine; một project chỉ có một application và region **không đổi** sau khi tạo.
2. **Default service** phải được deploy đầu tiên; thêm service bằng trường **service** trong app.yaml, mỗi service có phiên bản và traffic riêng.
3. **Version** là đơn vị phát hành; tạo version ID mới cho mỗi release, dùng **--no-promote** để kiểm thử an toàn trước khi chuyển traffic.
4. **Traffic splitting** phân phối requests ở service-level; **version URL** nhắm thẳng bản phát hành. Cookie/IP/random có đặc tính affinity khác nhau.
5. **Migration/rollback** là thay routing, không tự đảo ngược schema/data; gradual migration có giới hạn với warmup và flexible.
6. **Scaling, IAM, logs, budgets, release discipline** quyết định độ tin cậy và tổng chi phí; App Engine không thay thế bảo mật ứng dụng hay data backups.

**Tài liệu Google Cloud chính thức:**

1. [An overview of App Engine](https://docs.cloud.google.com/appengine/docs/an-overview-of-app-engine) — mô hình app/services/versions/instances.
2. [Set up a project and App Engine application](https://docs.cloud.google.com/appengine/docs/standard/managing-projects-apps-billing) — region và giới hạn một application/project.
3. [Structuring web services](https://docs.cloud.google.com/appengine/docs/standard/configuration-files) — default service, nhiều services và các file YAML.
4. [Java standard runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime) — Java runtimes, PORT, Maven/JAR startup.
5. [Java app.yaml configuration](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/configuring-your-app-with-app-yaml) — service, version và Java config.
6. [app.yaml reference](https://docs.cloud.google.com/appengine/docs/standard/reference/app-yaml) — scaling, env và handlers.
7. [Deploy an App Engine application](https://docs.cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app) — deploy, no-promote và version behavior.
8. [How requests are routed](https://docs.cloud.google.com/appengine/docs/standard/how-requests-are-routed) — service/version URLs và dispatch.
9. [Splitting traffic](https://docs.cloud.google.com/appengine/docs/standard/splitting-traffic) — IP/cookie và tỷ lệ canary.
10. [Migrating traffic](https://docs.cloud.google.com/appengine/docs/standard/migrating-traffic) — gradual/immediate và warmup.
11. [How instances are managed](https://docs.cloud.google.com/appengine/docs/standard/how-instances-are-managed) — scaling và quản lý versions.
12. [gcloud app deploy reference](https://docs.cloud.google.com/sdk/gcloud/reference/app/deploy) — flags --version/--no-promote.
13. [gcloud app services set-traffic](https://docs.cloud.google.com/sdk/gcloud/reference/app/services/set-traffic) — splits và --migrate.
14. [gcloud app versions delete](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/delete) — giới hạn xóa bản nhận traffic.
