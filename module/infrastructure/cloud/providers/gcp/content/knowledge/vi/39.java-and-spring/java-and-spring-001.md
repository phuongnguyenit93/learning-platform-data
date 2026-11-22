# Lựa chọn JDK, runtime và nền tảng triển khai Java trên GCP

Một ứng dụng Java chạy tốt trên máy phát triển chưa chắc hoạt động ổn định khi đưa lên Google Cloud. JDK dùng để biên dịch có thể khác runtime trong container; thư viện Spring có thể chưa tương thích với Java mới; nền tảng triển khai có thể giới hạn hệ điều hành, quyền truy cập hoặc cách ứng dụng nhận request. Chọn đúng JDK, runtime và nền tảng giúp giảm lỗi tương thích, đơn giản hóa vận hành và duy trì khả năng cập nhật bảo mật.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, bài học đặt Java và Spring vào bức tranh triển khai Google Cloud từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Người học sẽ biết chọn runtime theo vòng đời ứng dụng, đóng gói artifact có thể tái lập, chọn mức kiểm soát hạ tầng phù hợp và vận hành ứng dụng theo yêu cầu về độ tin cậy, bảo mật và chi phí.

Sau bài học, người học có thể:

- Phân biệt JDK, JRE/runtime, JVM, Java distribution và container base image.
- Chọn phiên bản Java LTS và nhà cung cấp JDK theo yêu cầu hỗ trợ, giấy phép và chu kỳ vá lỗi.
- Kiểm tra tính tương thích giữa JDK, Spring Boot, Maven/Gradle, thư viện và nền tảng GCP.
- Phân biệt môi trường build với môi trường chạy và cố định phiên bản runtime.
- Chọn Cloud Run, Cloud Run Jobs/functions, GKE, Compute Engine hoặc App Engine theo đặc tính workload.
- Đóng gói ứng dụng Java/Spring Boot bằng Cloud Buildpacks hoặc Docker.
- Cấu hình JVM, cổng mạng, service account, secret, log, metric và trace phù hợp với môi trường triển khai.
- Lập kế hoạch nâng cấp JDK và chuyển nền tảng mà không làm gián đoạn dịch vụ.

## 1. Phân biệt JDK, runtime và JVM

Các thuật ngữ Java thường được dùng thay thế nhau trong hội thoại, nhưng chúng mô tả những thành phần khác nhau.

| Thành phần | Vai trò | Có trong giai đoạn nào? |
|---|---|---|
| JDK (Java Development Kit) | Bộ công cụ phát triển, gồm compiler **javac**, debugger, công cụ đóng gói và runtime | Build, test và có thể cả runtime |
| JRE/runtime | Thành phần cần thiết để chạy bytecode Java, gồm JVM và thư viện runtime | Runtime |
| JVM (Java Virtual Machine) | Thực thi bytecode, quản lý bộ nhớ, garbage collection, JIT và thread | Runtime |
| Java distribution | Bản phân phối JDK/runtime từ một nhà cung cấp cụ thể | Build/runtime tùy gói |
| Container base image | Hệ điều hành tối thiểu và runtime/library cần để chạy ứng dụng | Runtime container |

JDK thường được dùng trong giai đoạn build vì cần compiler và công cụ kiểm thử. Container production có thể chỉ cần JRE hoặc runtime image nhỏ hơn. Tách build image và runtime image giúp giảm kích thước, số package và bề mặt tấn công của container.

Java bytecode được tạo ra theo class-file version. Runtime phải hiểu được class-file version của ứng dụng và thư viện. Nếu biên dịch bằng JDK mới nhưng đặt target không phù hợp, ứng dụng có thể gặp lỗi **UnsupportedClassVersionError** khi chạy trên runtime cũ. Ngược lại, đặt target thấp không tự bảo đảm thư viện mới tương thích với runtime cũ.

### 1.1. Chọn Java LTS

Java phát hành feature release theo chu kỳ sáu tháng; một số phiên bản được nhà cung cấp đánh dấu Long-Term Support (LTS) với lịch cập nhật và hỗ trợ dài hơn. Tính đến tháng 11-2026, các bản LTS phổ biến gồm Java 17, 21 và 25. Java 25 là LTS mới hơn; Java 21 vẫn là lựa chọn ổn định cho nhiều hệ thống production; Java 17 còn được hỗ trợ trên nhiều nền tảng nhưng thời hạn hỗ trợ runtime của một số dịch vụ GCP sẽ đến sớm hơn.

| Phiên bản | Vị trí trong vòng đời | Gợi ý lựa chọn |
|---|---|---|
| Java 25 | LTS hiện hành, được nhiều runtime GCP hỗ trợ | Phù hợp dự án mới sau khi xác nhận framework, thư viện và agent |
| Java 21 | LTS đã được triển khai rộng | Phù hợp hệ thống production cần mức tương thích đã được kiểm chứng |
| Java 17 | LTS cũ hơn, vẫn được hỗ trợ trên nhiều runtime | Dùng cho hệ thống chưa thể nâng ngay; cần kế hoạch nâng cấp |
| Java 11 trở xuống | Nhiều runtime managed đã ngừng triển khai hoặc đang ở giai đoạn legacy | Lập kế hoạch chuyển sang phiên bản LTS còn hỗ trợ |

Không chọn JDK chỉ dựa vào số phiên bản cao nhất. Hãy cân nhắc phiên bản Java mà Spring Boot, framework, thư viện và agent hỗ trợ; lịch vá lỗi và thời hạn hỗ trợ của vendor; giấy phép production; kiến trúc CPU, hệ điều hành và native library; khả năng kiểm thử, quan sát và rollback; cùng runtime mà nền tảng đích hỗ trợ.

LTS là cam kết vòng đời của một nhà cung cấp hoặc bản phân phối theo chính sách của họ; không có nghĩa mọi vendor có lịch hỗ trợ giống nhau. Hãy đọc roadmap của chính nhà cung cấp JDK mà tổ chức chọn.

### 1.2. Chọn nhà cung cấp JDK

Các bản phân phối OpenJDK phổ biến gồm Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, Red Hat OpenJDK và Oracle JDK. Chúng cùng triển khai đặc tả Java nhưng có thể khác về gói cài đặt, lịch cập nhật, hỗ trợ thương mại, chứng nhận, giấy phép và cách đóng gói.

Khi đánh giá vendor, lập bảng kiểm:

1. **Support:** có hỗ trợ kỹ thuật, SLA và thời hạn vá lỗi phù hợp không?
2. **License:** điều kiện sử dụng và phân phối có phù hợp mô hình kinh doanh không?
3. **Patch cadence:** bản cập nhật bảo mật được phát hành và thông báo thế nào?
4. **Compatibility:** có build cho Linux distribution, kiến trúc CPU và native dependency đang dùng không?
5. **Supply chain:** image/package có chữ ký, checksum, SBOM và nguồn phát hành đáng tin cậy không?
6. **Operations:** đội vận hành có quy trình chuẩn để cập nhật, kiểm thử và rollback không?

Không giả định mọi gói mang tên OpenJDK đều có cùng cam kết hỗ trợ. Cần ghi rõ vendor, phiên bản và build number trong inventory, build metadata hoặc SBOM để truy vết khi có lỗ hổng.

### 1.3. Kiểm tra phiên bản thực tế

Trên máy phát triển hoặc trong container, dùng:

~~~bash
java -version
javac -version
./mvnw -version
./gradlew --version
~~~

Lệnh **java -version** cho biết runtime đang được gọi; **javac -version** cho biết compiler nếu JDK có mặt. Maven/Gradle có thể chạy bằng một JDK khác với JDK được cấu hình để compile source. Kiểm tra cả biến **JAVA_HOME**, toolchain và build log thay vì chỉ xem một lệnh.

## 2. Tương thích JDK với Spring Boot và công cụ build

Phiên bản Java phải được chọn cùng với Spring Boot, Spring Framework, Maven/Gradle, plugin, thư viện quan sát và các dependency có native component.

### 2.1. Spring Boot

Spring Boot đặt ra phiên bản Java tối thiểu và giới hạn tương thích cho mỗi dòng release. Tại thời điểm tháng 11-2026, tài liệu Spring Boot 4.0.x công bố yêu cầu tối thiểu Java 17 và hỗ trợ tới Java 27; Spring Boot 3.5.x yêu cầu tối thiểu Java 17 và hỗ trợ tới Java 25. Hãy kiểm tra đúng bản vá của nhánh Spring Boot đang sử dụng vì yêu cầu build tool, Spring Framework và container có thể thay đổi theo phiên bản.

Một số điểm cần rà soát khi nâng JDK:

- Spring Boot và Spring Framework có hỗ trợ phiên bản Java mục tiêu không?
- Plugin Maven/Gradle và annotation processor có tương thích không?
- Thư viện logging, JDBC driver, ORM, serialization và tracing có bản tương thích không?
- Có dependency dùng reflection sâu, API nội bộ hoặc native library bị ảnh hưởng bởi module system không?
- Bộ kiểm thử có phụ thuộc timezone, locale, charset, TLS hoặc hành vi GC không?
- Container image và runtime của GCP có hỗ trợ phiên bản Java cần dùng không?

Không nâng JDK và Spring Boot cùng lúc nếu chưa có kiểm thử phân biệt được nguyên nhân lỗi. Có thể nâng theo hai giai đoạn: giữ nguyên framework để xác minh JDK trước, sau đó nâng framework; hoặc dùng ma trận kiểm thử để đánh giá cả hai thay đổi trong cùng một đợt có kiểm soát.

### 2.2. Cấu hình Maven

Với Maven, ưu tiên Maven Wrapper để cố định phiên bản Maven cho nhóm phát triển và CI. Dùng thuộc tính **maven.compiler.release** để đặt API và bytecode target:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Nếu dự án dùng Spring Boot parent, kiểm tra property Java mà parent/plugin đang sử dụng để tránh cấu hình mâu thuẫn giữa **java.version**, **source**, **target** và **release**. Đừng chỉ thay JAVA_HOME rồi giả định compiler target cũng đổi theo.

Kiểm tra:

~~~bash
./mvnw -version
./mvnw -B clean verify
~~~

### 2.3. Cấu hình Gradle

Với Gradle, dùng Gradle Wrapper và Java toolchains để khai báo JDK dùng compile/test. Ví dụ:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
~~~

Toolchain giúp build chọn đúng JDK thay vì phụ thuộc JDK mặc định trên máy chạy CI. Cần xác minh Gradle version và plugin tương thích với Java version đã chọn.

### 2.4. Kiểm thử nâng cấp

Một bộ kiểm thử nâng JDK nên có:

- Compile và unit test.
- Integration test với database, cache, message broker và API bên ngoài.
- Kiểm thử TLS, certificate, DNS, proxy và JDBC.
- Kiểm thử startup, shutdown, graceful termination và health check.
- Load/soak test để quan sát GC, memory, thread và latency.
- Kiểm tra log, metric, trace và agent bảo mật.
- Kiểm tra native image hoặc JNI nếu ứng dụng sử dụng.

Ghi lại baseline trước nâng cấp: startup time, memory RSS, heap usage, GC pause, throughput, p95/p99 latency và error rate. So sánh sau nâng cấp trên cùng workload.

## 3. Chọn runtime Java trên Google Cloud

Runtime là môi trường thực thi ứng dụng. Trên GCP, có thể dùng runtime được Google quản lý hoặc tự đóng gói Java vào container/VM. Mức kiểm soát tăng dần từ nền tảng serverless đến Kubernetes và máy ảo, đồng thời trách nhiệm vận hành cũng thay đổi.

### 3.1. Các runtime Java managed hiện hành

Theo lịch runtime được Google Cloud công bố tại thời điểm tháng 11-2026, Java 25, 21 và 17 có mặt trên các runtime managed chính dưới đây. Lịch hỗ trợ có thể thay đổi; kiểm tra runtime support schedule trước khi tạo hệ thống mới hoặc lên lịch nâng cấp.

| Nền tảng | Java runtime đang được hỗ trợ | Mô hình |
|---|---|---|
| Cloud Run source deployments/buildpacks | Java 25, 21, 17 | Build source thành container rồi chạy service/job |
| Cloud Run functions | Java 25, 21, 17 | Runtime Functions Framework cho function |
| App Engine standard gen2 | Java 25, 21, 17 | Runtime managed, cấu hình bằng app.yaml |
| App Engine flexible | Java 25, 21, 17 | Container trên VM do App Engine quản lý |
| GKE | Do người dùng chọn trong container image | Tự quản lý image, pod và cluster mode |
| Compute Engine | Do người dùng cài trong VM hoặc container | Tự quản lý OS, JDK và tiến trình |

Các mốc hỗ trợ runtime Java 25 và Java 21 trên một số runtime GCP được công bố lần lượt tới tháng 10-2031 và tháng 9-2031; Java 17 trên Cloud Run/buildpacks và App Engine standard có mốc hỗ trợ tới tháng 10-2027. Mốc hỗ trợ không đồng nghĩa nền tảng sẽ tự nâng ứng dụng lên major version mới. Chủ sở hữu ứng dụng phải lập kế hoạch chuyển phiên bản trước khi runtime bị deprecated hoặc decommissioned.

### 3.2. Managed runtime hay tự quản lý container?

**Managed runtime** giảm công việc cài JDK, cập nhật OS và tích hợp nền tảng. Đổi lại, ứng dụng phải tuân theo runtime, buildpack, cấu hình và giới hạn mà dịch vụ hỗ trợ.

**Container tự quản lý** cho phép chọn JDK vendor, base image, native library và startup command. Đổi lại, nhóm chịu trách nhiệm rebuild image, cập nhật package, quét lỗ hổng, quản lý registry và kiểm thử runtime.

Hãy chọn theo yêu cầu thực tế:

- Nếu ứng dụng Spring Boot chuẩn HTTP, stateless và không cần tùy chỉnh OS, Cloud Run thường là điểm khởi đầu đơn giản.
- Nếu cần Kubernetes API, sidecar, service mesh, network policy hoặc nhiều workload container phối hợp, cân nhắc GKE.
- Nếu cần quyền quản trị OS, agent đặc biệt, filesystem hoặc tiến trình nền lâu dài, cân nhắc Compute Engine.
- Nếu muốn mô hình ứng dụng code-centric gắn với App Engine, kiểm tra giới hạn của standard hoặc flexible environment.

## 4. Chọn nền tảng triển khai

### 4.1. Cloud Run services

Cloud Run chạy container theo mô hình managed. Dịch vụ phù hợp với REST API, web service, backend Spring Boot, webhook và ứng dụng HTTP stateless.

Ưu điểm:

- Không cần tạo cluster hoặc quản lý VM.
- Có thể scale theo request và scale về 0 khi không có traffic nếu cấu hình cho phép.
- Tích hợp HTTPS endpoint, IAM, traffic splitting, revision và autoscaling.
- Có thể deploy source bằng buildpacks hoặc deploy container image tự build.
- Hỗ trợ cấu hình CPU, memory, concurrency, min/max instances, timeout và ingress.

Điểm cần thiết kế:

- Ứng dụng phải lắng nghe cổng được Cloud Run cung cấp qua biến môi trường PORT và bind trên 0.0.0.0.
- Spring Boot có thể cấu hình cổng mặc định 8080 và ánh xạ biến môi trường khi cần.
- Không lưu session hoặc file quan trọng chỉ trên filesystem tạm của instance.
- Không giả định một instance luôn tồn tại; request có thể được chuyển sang instance khác hoặc instance có thể bị dừng.
- Đặt concurrency theo khả năng thread pool, connection pool và memory của ứng dụng.
- Đặt maximum instances để bảo vệ database và dependency; minimum instances khi cần giảm cold start.
- Thiết kế graceful shutdown, readiness và xử lý SIGTERM.

Ví dụ application.yaml:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Nếu cấu hình port khác 8080, hãy lấy giá trị từ biến môi trường PORT. Không mở toàn bộ actuator endpoints ra Internet. Chỉ expose endpoint cần thiết và giới hạn quyền truy cập phù hợp. Các giá trị connection pool phải được tính trên tổng số instance có thể chạy đồng thời.

Deploy từ source:

~~~bash
gcloud run deploy orders-api --source . --region=asia-southeast1
~~~

Lệnh này sử dụng Cloud Build và Google Cloud buildpacks để tạo container image, lưu image trong Artifact Registry rồi deploy service. Đây là cách nhanh để bắt đầu. Nếu cần kiểm soát chính xác base image, build arguments, SBOM, signing hoặc build stage, hãy build image bằng Cloud Build riêng rồi deploy image đã tạo.

### 4.2. Cloud Run Jobs

Cloud Run Jobs phù hợp với công việc chạy đến khi hoàn thành thay vì phục vụ request liên tục:

- Batch import/export.
- Tác vụ đối soát dữ liệu.
- Job xử lý file hoặc báo cáo.
- Migration có kiểm soát.
- Công việc nền chạy theo lịch hoặc được gọi bởi workflow.

Job chạy container Java và kết thúc bằng exit code. Có thể cấu hình task count, parallelism, timeout, retry và task-specific environment. Ứng dụng không cần mở HTTP server nếu job không phục vụ request.

Không dùng Cloud Run service cho batch kéo dài nếu workload tự nhiên là một job có điểm bắt đầu/kết thúc rõ ràng. Ngược lại, không dùng Job cho API cần phản hồi đồng bộ mỗi request.

### 4.3. Cloud Run functions

Cloud Run functions phù hợp với một hàm được kích hoạt bởi HTTP hoặc sự kiện từ dịch vụ khác, ví dụ Pub/Sub, Cloud Storage hoặc Eventarc. Java function thường dùng Functions Framework và một entry point rõ ràng.

Chọn functions khi logic có phạm vi nhỏ, được gọi theo sự kiện và không cần toàn bộ ứng dụng web Spring Boot. Nếu cần nhiều endpoint, filter, security chain, dependency injection hoặc quy trình nghiệp vụ lớn, một Cloud Run service Spring Boot có thể dễ tổ chức và kiểm thử hơn.

### 4.4. Google Kubernetes Engine

GKE phù hợp khi tổ chức đã vận hành Kubernetes hoặc ứng dụng cần khả năng orchestration và tùy biến cao:

- Nhiều microservice và workload container có vòng đời khác nhau.
- Sidecar, service mesh, admission policy hoặc network policy.
- Stateful workload hoặc operator chuyên biệt.
- Kiểm soát node pool, accelerator, scheduling và topology.
- Hybrid hoặc multi-cluster theo yêu cầu kiến trúc.

GKE Autopilot giảm trách nhiệm quản lý node và một số cấu hình hạ tầng. GKE Standard cho phép kiểm soát node pool, machine type, OS và cấu hình cluster sâu hơn.

Ứng dụng Java cần được đóng gói thành container image. Deployment thường khai báo image, resource requests/limits, probes, environment variables, service account và autoscaling.

Ví dụ Deployment rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: app
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 500m
              memory: 768Mi
            limits:
              cpu: "2"
              memory: 1Gi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
~~~

Đây là mẫu để minh họa các trường quan trọng. Cần tạo Service, Gateway/Ingress hoặc load balancer phù hợp; cấu hình probes đúng với ứng dụng; dùng image tag bất biến hoặc digest; kiểm tra resource sizing qua load test. Không đặt liveness probe quá nhạy khiến ứng dụng bị restart khi chỉ đang xử lý tải cao.

Khi dùng GKE, cần tính cả CPU/memory request, node capacity, pod IP range, cluster autoscaler, HPA, rollout surge và quota Compute Engine. Pod tăng replica không có nghĩa cluster đã có node đủ chỗ để schedule.

### 4.5. Compute Engine

Compute Engine phù hợp với ứng dụng Java cần quyền kiểm soát VM:

- Ứng dụng legacy cần cài agent hoặc package ở cấp OS.
- Phần mềm yêu cầu filesystem, process hoặc network configuration đặc biệt.
- Ứng dụng monolith chưa sẵn sàng container hóa.
- Workload chạy nền lâu dài hoặc có yêu cầu cấp phép gắn với VM.

Nhóm vận hành chịu trách nhiệm cài JDK, cập nhật OS, cấu hình systemd, firewall, logging agent, monitoring, backup và mở rộng instance. Có thể dùng Managed Instance Group để triển khai nhiều VM và autoscaling.

Không nên cài JDK thủ công không có quy trình quản lý phiên bản. Dùng image family hoặc image custom có kiểm soát, cấu hình startup automation và ghi nhận JDK vendor/build number. Khi cập nhật, tạo image mới và triển khai theo rolling update để dễ rollback.

### 4.6. App Engine standard và flexible

App Engine có hai môi trường cho ứng dụng Java:

| Tiêu chí | Standard environment | Flexible environment |
|---|---|---|
| Runtime | Java runtime do Google quản lý | Container trên VM do App Engine quản lý |
| Kiểm soát OS | Giới hạn theo runtime/stack | Linh hoạt hơn qua Docker/buildpacks |
| Scale | Tối ưu cho scale nhanh, có thể về 0 theo cấu hình | Có minimum instance và scale theo cấu hình |
| Phù hợp | Web app Java theo runtime được hỗ trợ | Ứng dụng cần runtime/framework/library hoặc container tùy chỉnh |
| Trách nhiệm | Ít quản lý hạ tầng hơn | Nhiều cấu hình container và VM hơn |

Với App Engine standard gen2, khai báo runtime trong app.yaml:

~~~yaml
runtime: java25

instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 20
~~~

Giá trị instance class và scaling phải được chọn theo workload và giới hạn hiện hành của App Engine. Runtime Java 25 là lựa chọn mới hơn trên standard gen2; không phải ứng dụng Java 8/11 cũ có thể chuyển lên chỉ bằng cách sửa runtime. Cần kiểm tra API, thư viện và namespace Jakarta/Java EE nếu ứng dụng dùng servlet hoặc bundled services legacy.

App Engine flexible hữu ích khi cần container và runtime tùy chỉnh nhưng vẫn muốn mô hình triển khai App Engine. Với dự án mới, hãy so sánh nó với Cloud Run và GKE vì container service có thể đáp ứng yêu cầu tương tự với mô hình vận hành khác.

## 5. Bảng quyết định nền tảng

| Yêu cầu chính | Nền tảng nên đánh giá đầu tiên | Lý do |
|---|---|---|
| Spring Boot REST API stateless | Cloud Run service | Container managed, HTTPS, revision và autoscaling |
| Batch job Java có điểm kết thúc | Cloud Run Jobs | Task, retry, timeout và parallelism |
| Function phản ứng theo event | Cloud Run functions | Function runtime và event integration |
| Microservices cần Kubernetes API, sidecar hoặc service mesh | GKE | Orchestration và kiểm soát Kubernetes |
| Legacy Java cần OS/agent riêng | Compute Engine | Toàn quyền VM và hệ điều hành |
| Web app Java muốn runtime code-centric managed | App Engine standard | Runtime quản lý và scale nhanh |
| Java cần container tùy chỉnh trong mô hình App Engine | App Engine flexible | Runtime linh hoạt trên VM/container |

Không có nền tảng tốt nhất cho mọi ứng dụng. Hãy chọn theo workload, SLO, yêu cầu network, mức kiểm soát, năng lực đội vận hành, chi phí nền tảng và thời gian cần để phát hành.

## 6. Đóng gói Java cho GCP

### 6.1. Google Cloud buildpacks

Buildpacks phát hiện cấu trúc dự án, chọn build process và tạo container image. Với Java, buildpacks hỗ trợ Maven và Gradle. Cloud Run source deployment có thể dùng buildpacks tự động mà không cần người phát triển cài Docker.

Nếu không chỉ định Java version, buildpacks có thể chọn phiên bản mới nhất được hỗ trợ. Để build có thể tái lập, hãy pin phiên bản JDK trong repository.

Tạo project.toml:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "25"
~~~

Có thể dùng cùng cấu hình này khi build bằng pack hoặc Cloud Buildpacks. Kiểm tra runtime support schedule và builder stack trước khi nâng version. Pin major version giúp tránh việc build mới tự chuyển sang major version khác khi buildpack cập nhật mặc định.

### 6.2. Docker multi-stage build

Khi cần kiểm soát JDK vendor, OS package và runtime image, dùng Dockerfile multi-stage. Ví dụ:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN ./mvnw -B dependency:go-offline

COPY src/ src/
RUN ./mvnw -B clean package -DskipTests

FROM eclipse-temurin:25-jre
WORKDIR /app

RUN useradd --system --uid 10001 appuser
COPY --from=build /workspace/target/*.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là mẫu minh họa; kiểm tra tag image cụ thể đang tồn tại và được hỗ trợ, cố định digest trong pipeline production, và điều chỉnh tên JAR nếu thư mục target chứa nhiều artifact. Trong môi trường cần kiểm soát sâu hơn, có thể dùng JRE/distroless base image nhỏ hơn và chạy bằng non-root user.

Nguyên tắc:

- Dùng JDK ở build stage, chỉ mang artifact cần thiết sang runtime stage.
- Không copy .git, credential, file cấu hình local hoặc secret vào image.
- Cập nhật base image và rebuild khi có security patch.
- Dùng .dockerignore để giảm build context.
- Gắn version hoặc commit SHA vào image tag; không dựa vào tag latest.
- Quét image, lưu SBOM và provenance, ký image nếu quy trình supply chain yêu cầu.
- Chạy non-root và chỉ cài package runtime thực sự cần.

### 6.3. Build một lần, triển khai nhiều môi trường

Nên build artifact một lần từ commit đã xác định, sau đó promote cùng một image digest qua staging và production. Không rebuild từ source riêng cho từng môi trường vì kết quả có thể khác do dependency, buildpack hoặc base image đã thay đổi.

Runtime configuration như project ID, endpoint, feature flag và resource name nên được truyền qua environment/configuration system. Secret lấy từ Secret Manager hoặc cơ chế secret được tổ chức phê duyệt; không nhúng vào image.

## 7. Cấu hình JVM trong container

JVM cần nhận biết giới hạn CPU và memory của container. Một container có memory limit 1 GiB không có nghĩa toàn bộ 1 GiB đều dành cho Java heap; process còn cần metaspace, thread stack, direct buffer, JIT code cache, native library và memory của hệ điều hành.

### 7.1. Heap và memory limit

Có thể cấu hình heap bằng -Xms/-Xmx hoặc tỷ lệ RAM như -XX:MaxRAMPercentage. Không đặt -Xmx bằng đúng memory limit của container vì JVM và native component cần thêm bộ nhớ ngoài heap.

Ví dụ:

~~~bash
java \
  -XX:MaxRAMPercentage=65 \
  -XX:InitialRAMPercentage=25 \
  -XX:+ExitOnOutOfMemoryError \
  -jar app.jar
~~~

Các giá trị chỉ là điểm bắt đầu. Đo RSS, heap, metaspace, direct memory, thread count và GC trong môi trường tương tự production trước khi chốt. Nếu container bị OOMKilled, xem cả memory limit và memory ngoài heap; chỉ tăng heap có thể làm lỗi nặng hơn.

### 7.2. CPU, GC và startup

- Dùng profiling để xác định CPU-bound hay I/O-bound trước khi thay garbage collector.
- Theo dõi GC pause, allocation rate, heap occupancy và thời gian startup.
- Với service scale-to-zero, đo cold start và warm-up; cân nhắc min instances hoặc startup CPU boost khi phù hợp.
- Với ứng dụng có JIT warm-up dài, so sánh thời gian phục vụ request đầu và request sau warm-up.
- Kiểm tra shutdown hook và thời gian drain request khi nền tảng dừng instance.
- Tránh tạo thread pool lớn hơn khả năng CPU và memory của container.

Virtual threads từ Java 21 có thể hữu ích cho workload I/O-bound có nhiều tác vụ blocking. Chúng không làm CPU-bound code chạy nhanh hơn và không thay thế giới hạn connection pool, backpressure hoặc timeout. Kiểm thử thư viện và native call trước khi chuyển một ứng dụng Spring sang virtual threads.

### 7.3. Concurrency và connection pool

Trên Cloud Run, concurrency là số request đồng thời một instance có thể nhận. Giá trị cao có thể cải thiện hiệu quả tài nguyên cho ứng dụng I/O-bound nhưng làm tăng memory, thread, connection và độ trễ khi request tranh chấp tài nguyên.

Với Spring Boot và HikariCP, tính tổng số kết nối tiềm năng:

\[
\text{Max DB connections} =
\text{Max instances} \times
\text{Pool size per instance}
\]

Ví dụ, 20 instance với pool tối đa 10 kết nối có thể tạo tới 200 kết nối. Cần cộng thêm kết nối từ job, migration, admin và ứng dụng khác dùng chung database. Đặt pool nhỏ vừa đủ và dùng timeout/backpressure thay vì để mỗi instance mở quá nhiều kết nối.

## 8. Bảo mật danh tính và cấu hình ứng dụng

### 8.1. Runtime service account

Ứng dụng Java gọi Google Cloud APIs nên dùng danh tính gắn với workload:

- Cloud Run: cấu hình service identity cho service.
- GKE: dùng Workload Identity Federation for GKE để ánh xạ Kubernetes ServiceAccount tới quyền Google Cloud.
- Compute Engine: dùng service account gắn với VM.
- App Engine: dùng service account của ứng dụng.

Không nhúng service account JSON key vào JAR, Docker image, source code hoặc biến môi trường được commit. Cấp role tối thiểu trên đúng project/resource, ví dụ chỉ đọc một bucket hoặc truy cập một secret cụ thể.

### 8.2. Secret và cấu hình

Spring Boot có nhiều nguồn cấu hình như environment variables, config files, command-line arguments và external configuration. Secret cần được quản lý riêng:

- Lưu password, API token và certificate private key trong Secret Manager.
- Chỉ cấp Secret Accessor trên secret mà service cần.
- Dùng version và rotation theo quy trình.
- Tránh ghi secret vào log, exception, trace attributes hoặc actuator environment endpoint.
- Không đưa secret vào Docker build argument hoặc image layer.

Với nhiều môi trường, tách cấu hình theo project và runtime identity. Không để cấu hình staging có thể vô tình trỏ tới database production.

### 8.3. Network và ingress

- Cloud Run: chọn ingress internal, internal-and-cloud-load-balancing hoặc all theo nhu cầu; bật IAM authentication nếu endpoint không public.
- GKE: dùng Service, Gateway/Ingress, NetworkPolicy và firewall phù hợp; giới hạn đường tới database.
- Compute Engine: đặt VM trong subnet riêng khi phù hợp, giới hạn firewall và dùng IAP cho quản trị.
- App Engine: kiểm tra ingress, firewall và đường kết nối tới dịch vụ phụ thuộc theo môi trường.

Private IP không tự động bảo vệ database nếu service account hoặc database credential có quyền quá rộng. Kết hợp network control với IAM, xác thực database và phân quyền dữ liệu.

## 9. Observability cho ứng dụng Java/Spring

Một ứng dụng production cần log, metric và trace để nhóm vận hành phát hiện và điều tra sự cố.

### 9.1. Logging

- Ghi log có cấu trúc JSON hoặc định dạng tương thích Cloud Logging.
- Dùng severity đúng mức; tránh ghi mọi exception thành INFO.
- Thêm request ID hoặc trace context để liên kết log với trace.
- Không ghi password, token, dữ liệu cá nhân hoặc payload nhạy cảm.
- Ghi stdout/stderr trong container nếu nền tảng thu thập theo cơ chế đó; với VM, cấu hình agent/collector phù hợp.

### 9.2. Metrics và health checks

Với Spring Boot Actuator và Micrometer, theo dõi:

- Request rate, error rate và latency percentile.
- JVM heap/non-heap, GC pause, thread count và process CPU.
- HikariCP active/idle/pending connections.
- Queue depth, cache hit ratio và dependency latency.
- Container memory/CPU, instance/pod count và restart.

Expose health endpoint theo mức cần thiết. Readiness trả lời ứng dụng có thể nhận traffic chưa; liveness trả lời process có cần restart không. Không dùng dependency bên ngoài không ổn định làm liveness check nếu điều đó có thể tạo restart storm.

### 9.3. Distributed tracing

Dùng OpenTelemetry hoặc instrumentation tương thích để tạo trace xuyên các service. Giữ W3C Trace Context qua HTTP/RPC/message queue và ghi trace ID vào log. Khi chạy Cloud Run hoặc GKE, đảm bảo exporter/collector có quyền ghi trace và có thể truy cập endpoint.

### 9.4. SLO và cảnh báo

Đặt SLI/SLO cho latency, availability và error rate. Cảnh báo theo burn rate/error budget thay vì chỉ cảnh báo một ngưỡng CPU. Kết hợp Cloud Monitoring dashboard với Logs Explorer và Cloud Trace để đi từ tín hiệu tổng hợp tới request cụ thể.

## 10. Chi phí và mô hình vận hành

Chi phí Java trên GCP phụ thuộc cách nền tảng cấp phát tài nguyên, thời gian chạy, network, storage, logging, database và số lượng bản sao.

| Nền tảng | Thành phần chi phí cần xem | Điểm cần cân nhắc |
|---|---|---|
| Cloud Run | CPU/memory theo mức sử dụng, request, minimum instances, network và artifact | Scale-to-zero có thể tiết kiệm cho tải không liên tục; min instances giúp giảm cold start nhưng tăng chi phí nền |
| Cloud Run Jobs | CPU/memory theo task và thời gian chạy | Tối ưu parallelism và retry để tránh chạy lặp tốn kém |
| GKE Autopilot | Tài nguyên pod được cấp phát, network, storage và dịch vụ phụ trợ | Dễ quản lý hơn nhưng phải tối ưu requests/limits và số workload |
| GKE Standard | Node VM, cluster, disk, network, logging và control plane theo mô hình giá hiện hành | Có thể tối ưu node utilization nhưng cần kỹ năng quản lý cluster |
| Compute Engine | VM uptime, disk, network, license và backup | Có thể hiệu quả cho tải ổn định; nhóm tự quản lý OS và patch |
| App Engine standard | Instance usage và tài nguyên theo scaling/configuration | Phù hợp ứng dụng code-centric; xem min instances và scale policy |
| App Engine flexible | VM/container capacity và minimum instances | Chi phí nền có thể cao hơn khi traffic thấp |

Không chọn nền tảng chỉ dựa vào giá compute trên một đơn vị. Tính cả thời gian kỹ sư vận hành, chi phí HA, scale headroom, database connection, log retention, egress và thời gian khắc phục sự cố.

## 11. Lộ trình quyết định và triển khai

Có thể dùng trình tự sau khi đưa một ứng dụng Java/Spring lên GCP:

1. **Mô tả workload:** HTTP service, event handler, batch job hay ứng dụng legacy; xác định latency, throughput, state và dependency.
2. **Chọn JDK:** ưu tiên LTS còn thời gian hỗ trợ phù hợp; xác nhận vendor, license, security update và kiến trúc.
3. **Kiểm tra framework:** đối chiếu Spring Boot, Spring Framework, Maven/Gradle, driver và agent với JDK.
4. **Chọn nền tảng:** Cloud Run cho HTTP stateless; Jobs cho batch; functions cho event handler; GKE cho orchestration; Compute Engine cho VM control; App Engine khi phù hợp mô hình managed runtime.
5. **Chọn build path:** buildpacks cho source deployment đơn giản; Docker multi-stage khi cần kiểm soát image.
6. **Cố định phiên bản:** pin JDK major, build tool, dependency và base image; ghi commit và image digest.
7. **Thiết lập identity/network:** service account riêng, IAM tối thiểu, secret manager và ingress/private networking.
8. **Thiết lập runtime:** CPU/memory, JVM flags, concurrency, connection pool, startup, shutdown và health checks.
9. **Kiểm thử:** integration, load, failover, security scan và rollback.
10. **Vận hành:** dashboard, SLO, log/trace, patch cadence và kế hoạch nâng JDK trước khi runtime hết hỗ trợ.

### 11.1. Ví dụ: Spring Boot API trên Cloud Run

Giả sử có ứng dụng orders-api dùng Spring Boot, Maven và Cloud SQL. Yêu cầu là phục vụ HTTPS API, scale theo request và không quản lý Kubernetes.

Lựa chọn:

- JDK 25 LTS sau khi xác nhận Spring Boot/dependency hỗ trợ.
- Maven Wrapper và maven.compiler.release cố định trong repository.
- Google Cloud buildpacks với GOOGLE_RUNTIME_VERSION=25 hoặc Docker multi-stage.
- Cloud Run service cho API stateless.
- Runtime service account riêng có quyền kết nối Cloud SQL và đọc đúng secret.
- Cloud SQL private IP/connector theo kiến trúc mạng đã chọn.
- HikariCP pool nhỏ, tính theo maximum instance count.
- Cloud Logging, Cloud Monitoring và OpenTelemetry tracing.

Deploy từ source để bắt đầu:

~~~bash
gcloud run deploy orders-api \
  --source . \
  --region=asia-southeast1 \
  --service-account=orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=40 \
  --max=20
~~~

Các giá trị CPU, memory, concurrency và max instances chỉ là ví dụ ban đầu. Hãy thay bằng kết quả load test, kiểm tra giới hạn dịch vụ và khả năng Cloud SQL. Nếu dùng container image tự build, thay --source . bằng --image IMAGE_URI và triển khai cùng image digest đã được kiểm tra.

### 11.2. Ví dụ: Spring worker trên GKE

Nếu ứng dụng có nhiều consumer, cần sidecar, network policy và lịch xử lý message, GKE có thể phù hợp hơn Cloud Run service. Khi đó:

- Đóng gói Java runtime vào image.
- Dùng Kubernetes ServiceAccount và Workload Identity Federation.
- Đặt CPU/memory requests/limits dựa trên profiling.
- Dùng HPA theo CPU hoặc custom metric như queue depth.
- Dùng PodDisruptionBudget và rolling update để bảo vệ availability.
- Cấu hình graceful shutdown để consumer ngừng nhận message mới và hoàn thành/ack message đang xử lý.
- Giám sát node, pod, queue lag, database connections và error rate.

## 12. Troubleshooting các vấn đề phổ biến

**UnsupportedClassVersionError.** Runtime đang cũ hơn class-file version của ứng dụng hoặc dependency. Kiểm tra JDK build, --release, java -version trong container và runtime image.

**Ứng dụng chạy local nhưng không khởi động trên Cloud Run.** Kiểm tra app có bind 0.0.0.0, lắng nghe biến PORT, hoàn thành startup trong giới hạn và không phụ thuộc filesystem local hay daemon riêng.

**Container bị OOMKilled.** Kiểm tra memory limit, heap, metaspace, direct buffer, thread stack và native memory. Không chỉ tăng -Xmx mà chưa đo RSS.

**Cloud Run trả lỗi 503 khi tải tăng.** Kiểm tra startup/cold start, max instances, concurrency, CPU allocation, readiness và dependency như database. Scale ứng dụng có thể làm connection pool downstream cạn.

**GKE pod Pending hoặc restart liên tục.** Kiểm tra resource requests/limits, node capacity, quota, IP range, image pull, liveness/readiness probe và log của container.

**Ứng dụng không truy cập được Google Cloud API.** Xác minh runtime service account, IAM role, ADC, Workload Identity và quyền resource. Không khắc phục bằng cách nhúng JSON key vào image.

**TLS hoặc JDBC lỗi sau nâng JDK.** Kiểm tra truststore, cipher/TLS policy, certificate chain, JDBC driver và thư viện native. Chạy integration test trên cùng runtime image.

**Build dùng JDK khác dự kiến.** Kiểm tra Maven/Gradle Wrapper, toolchain, JAVA_HOME, buildpack GOOGLE_RUNTIME_VERSION và log của build stage.

**Spring Boot Actuator health báo DOWN dù API hoạt động.** Kiểm tra health group, dependency check và readiness/liveness mapping. Không để dependency phụ làm liveness thất bại liên tục.

**Ứng dụng chạy tốt nhưng thiếu log/trace.** Kiểm tra stdout/stderr, logging format, OpenTelemetry exporter, IAM của collector và context propagation.

## 13. Checklist chọn JDK và nền tảng

### JDK và framework

- [ ] Đã chọn phiên bản Java LTS còn thời gian hỗ trợ phù hợp.
- [ ] Đã ghi rõ JDK vendor, version và build.
- [ ] License/support policy của vendor đã được chấp nhận.
- [ ] Spring Boot/Spring Framework và dependency tương thích với JDK.
- [ ] Maven/Gradle Wrapper và toolchain đã được cố định.
- [ ] Có test compile, integration, load và security sau nâng cấp.

### Runtime và nền tảng

- [ ] Runtime GCP đích còn được hỗ trợ trong thời gian dự án cần.
- [ ] Đã chọn Cloud Run, Jobs/functions, GKE, Compute Engine hoặc App Engine theo workload.
- [ ] Build runtime và production runtime tương thích.
- [ ] Phiên bản JDK/base image được pin, không phụ thuộc latest.
- [ ] Startup, port binding, health check và graceful shutdown đã được kiểm tra.
- [ ] CPU/memory, JVM heap và connection pool được sizing theo load test.

### Bảo mật và vận hành

- [ ] Runtime dùng service account riêng với IAM tối thiểu.
- [ ] Secret được lấy từ Secret Manager hoặc hệ thống được phê duyệt.
- [ ] Image chạy non-root và được quét lỗ hổng.
- [ ] Có log, metric, trace và SLO.
- [ ] Có quy trình patch JDK/base image và rebuild định kỳ.
- [ ] Có rollback và kế hoạch nâng cấp trước ngày runtime bị decommission.

## 14. Tài liệu tham khảo chính thức

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Google Cloud Buildpacks Java](https://cloud.google.com/docs/buildpacks/java)
- [Google Cloud Buildpacks runtime support](https://cloud.google.com/docs/buildpacks/runtime-support)
- [Cloud Run runtime lifecycle](https://cloud.google.com/run/docs/runtime-support)
- [Deploy Java Spring Boot to Cloud Run](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Deploy source code to Cloud Run](https://cloud.google.com/run/docs/deploying-source-code)
- [Choose an App Engine environment](https://cloud.google.com/appengine/docs/the-appengine-environments)
- [App Engine standard Java runtime](https://cloud.google.com/appengine/docs/standard/java-gen2/runtime)
- [App Engine standard runtime support schedule](https://cloud.google.com/appengine/docs/standard/lifecycle/support-schedule)
- [App Engine flexible Java runtime](https://cloud.google.com/appengine/docs/flexible/java/runtime)
- [Compare GKE and Cloud Run](https://cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run)
- [Google Cloud compute options](https://cloud.google.com/docs/compute-area/choose-compute-options)

Lựa chọn JDK và nền tảng triển khai là quyết định gắn với vòng đời ứng dụng. Khi phiên bản Java, framework, build tool, container image và runtime được cố định và kiểm thử cùng nhau, nhóm có thể phát hành ứng dụng Java/Spring trên GCP một cách nhất quán, cập nhật bảo mật đúng hạn và chọn mức kiểm soát hạ tầng phù hợp với nhu cầu thực tế.
