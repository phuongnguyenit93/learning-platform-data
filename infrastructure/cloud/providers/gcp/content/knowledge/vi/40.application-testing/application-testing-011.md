# Thực hành pipeline kiểm thử có kiểm soát quota và chi phí

Một pipeline kiểm thử tự động giúp phát hiện lỗi sớm, nhưng nếu mỗi pull request đều tạo cơ sở dữ liệu, chạy hàng trăm tác vụ song song và giữ môi trường thử nghiệm hoạt động sau khi kết thúc, đội phát triển có thể gặp cả hai vấn đề: vượt quota Google Cloud và phát sinh chi phí không cần thiết. Ngược lại, đặt giới hạn quá thấp khiến kiểm thử bị treo, pipeline chậm và bản phát hành bị tắc.

Bài học này hướng dẫn xây dựng **pipeline kiểm thử Java/Spring trên Google Cloud theo ngân sách tài nguyên có chủ đích**. Phần lớn kiểm thử chạy cục bộ trong Cloud Build bằng mock hoặc emulator; chỉ một số bước tích hợp cần gọi dịch vụ thật ở project staging. Các bước tốn tiền có điều kiện kích hoạt, deadline, giới hạn song song, quyền IAM, dữ liệu thử nghiệm riêng và quy trình dọn dẹp.

Bài thuộc chương **Kiểm thử ứng dụng GCP** trong module **CLOUD_PROVIDERS_GCP**. Kiến thức về project, IAM, Cloud Run, lưu trữ, cơ sở dữ liệu, theo dõi độ tin cậy và chi phí giúp áp dụng cùng quy trình kiểm thử cho các workload thực tế.

## 1. Kết quả mong đợi

Sau bài học, bạn có thể:

- Chọn đúng tầng kiểm thử: unit, component, integration dùng emulator và smoke/end-to-end với dịch vụ thật.
- Cấu hình Cloud Build cho ứng dụng Maven/Spring với thời hạn tối đa cho từng bước và cả build.
- Giới hạn số lần kích hoạt, lượng tài nguyên đồng thời và quyền tạo tài nguyên có tính phí.
- Tách pipeline pull request giá rẻ khỏi pipeline staging cần quyền và phê duyệt.
- Thiết kế Cloud Run Job dùng để kiểm thử với task count, parallelism, retry và timeout rõ ràng.
- Theo dõi quota, tổng build-minutes, chi phí theo project/nhãn và đặt budget alert.
- Xử lý lỗi `RESOURCE_EXHAUSTED`, `429`, timeout, retry storm và môi trường thử nghiệm không được dọn.
- Đánh giá kết quả kiểm thử cùng chi phí thực tế trước khi tăng tần suất hoặc cấu hình máy.

## 2. Bài toán mẫu và ranh giới thực hành

Giả sử nhóm phát triển ứng dụng `checkout-api` bằng Java 21 và Spring Boot. Ứng dụng sử dụng Cloud Run, Pub/Sub, Cloud SQL và Cloud Storage. Nhóm cần phát hiện lỗi nhanh mỗi khi có pull request, đồng thời kiểm tra tương tác với Google Cloud trước khi phát hành.

Đề xuất ba loại pipeline:

| Loại chạy | Kích hoạt | Phạm vi kiểm thử | Tài nguyên GCP |
|---|---|---|---|
| PR nhanh | Mỗi pull request có thay đổi code | Unit, component, integration với fake/emulator | Chỉ máy Cloud Build, log và artifact tối thiểu |
| Staging có kiểm soát | Merge nhánh chính, theo lịch hoặc thao tác được phê duyệt | Smoke/API contract với dịch vụ thật | Project staging; số task và deadline nhỏ |
| Release | Sau khi staging đạt, có approval | Kiểm thử chọn lọc và xác minh bản triển khai | Project phát hành theo ranh giới quyền riêng |

**Mục tiêu của PR pipeline:** phát hiện phần lớn lỗi trong vài phút, không tạo tài nguyên có tính phí lâu dài. **Mục tiêu của staging pipeline:** kiểm tra những khác biệt mà emulator không tái hiện được, như IAM, networking, quota, TLS và hành vi managed service.

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Static check + unit test"]
    B --> C["Component/integration với fake và emulator"]
    C --> D{"Đạt?"}
    D -->|Không| E["Báo lỗi và dừng"]
    D -->|Có| F["Cho phép review / merge"]
    F --> G["Trigger staging có kiểm soát"]
    G --> H["Kiểm tra budget, quota, quyền và approval"]
    H --> I{"Đủ điều kiện?"}
    I -->|Không| J["Tạm dừng / hủy lượt chạy"]
    I -->|Có| K["Cloud Run Job smoke: task=1, parallelism=1"]
    K --> L["Thu thập kết quả và logs"]
    L --> M["Dọn dữ liệu/tài nguyên thử nghiệm"]
    M --> N{"Test + cleanup đạt?"}
    N -->|Có| O["Cho phép bước release"]
    N -->|Không| P["Tạo issue và giữ release"]
~~~

Không nên dùng một pipeline có đầy đủ quyền production cho mọi PR. Các thay đổi chưa được review có thể chạy mã tùy ý trên build worker; service account của PR pipeline phải có phạm vi quyền nhỏ nhất, đặc biệt với pull request từ nguồn bên ngoài.

## 3. Hiểu quota, giới hạn tài nguyên và chi phí

**Quota** là hạn mức tiêu thụ tài nguyên hoặc tốc độ gọi API do một dịch vụ áp dụng, thường theo project và region. **Limit** là giới hạn kỹ thuật của tài nguyên. **Cost** là số tiền phát sinh theo thời gian sử dụng, lượng request, dữ liệu hoặc hình thức lưu trữ.

Ba khái niệm liên quan nhưng không thay thế cho nhau:

- Cloud Build có quota về số build đồng thời, CPU đồng thời và giới hạn tốc độ gọi API. Giá trị phụ thuộc project, khu vực và pool; cần xem trang Quotas trước khi cấu hình.
- Cloud Run Jobs có số task, parallelism, task timeout, CPU/memory và retries. Quá nhiều task hoặc retry có thể gây áp lực lên Cloud SQL hoặc API khác.
- Cloud SQL, Pub/Sub, Cloud Storage và Networking có quota riêng; giảm quota Cloud Build không tự bảo vệ các dịch vụ này.
- Cloud Billing Budget ở chế độ **alerts-only** là cảnh báo, **không tự đặt trần chi tiêu cứng**. Một số khả năng spend cap có thể được hỗ trợ trong phạm vi nhất định; cần kiểm tra dịch vụ và dự án.

Ví dụ một pipeline test tạo 20 job task, mỗi task mở 10 kết nối database. Dù Cloud Build chỉ chạy một build, workload vẫn có thể tạo 200 kết nối gần đồng thời và vượt giới hạn Cloud SQL. Cần kiểm soát concurrency tại tầng job, test runner và connection pool.

### 3.1. Bảng ngân sách tài nguyên cho bài thực hành

| Hạng mục | Giới hạn đề xuất cho lab | Vì sao |
|---|---|---|
| Cloud Build tổng thể | 15 phút mỗi lượt | Tránh build hoặc test treo |
| Unit test | Tối đa 5 phút | Phát hiện test chậm bất thường |
| Integration dùng fake/emulator | Tối đa 8 phút | Chặn retry và deadlock kéo dài |
| Live smoke test | Một Cloud Run Job task | Không tạo tải lớn lên staging |
| Job parallelism | 1 | Dễ dự đoán số request đồng thời |
| Job task timeout | 300 giây | Giới hạn thời gian tính phí một task |
| Job retries trong lab | 0 | Tránh nhân số lượt chạy khi đang học |
| Dữ liệu test | Tên có run ID và thời hạn giữ | Tránh tích lũy lâu dài |
| Build triggers | PR scope hẹp; live test chỉ theo gate | Giảm chạy trùng và chạy không cần thiết |

Đây là **giới hạn minh họa**, không phải giá trị mặc định của Google Cloud hay khuyến nghị cố định cho mọi ứng dụng. Ở production, lựa chọn dựa trên độ phủ kiểm thử, tài nguyên thực tế, quota của project và SLO pipeline.

## 4. Chuẩn bị project, IAM và quan sát chi phí

Nên dùng ít nhất hai project:

- **BUILD_PROJECT_ID:** chạy Cloud Build, lưu test logs và kết quả.
- **STAGING_PROJECT_ID:** chứa dịch vụ Cloud Run, database hoặc tài nguyên dùng cho smoke test.

Project production tách biệt hoàn toàn; pipeline PR không có quyền tạo resource hoặc ghi dữ liệu ở staging/production.

Trước khi thử nghiệm:

1. Xác nhận billing account và quyền truy cập của hai project.
2. Bật Cloud Build API trong build project, Cloud Run API trong staging nếu dùng Job.
3. Tạo service account chạy build riêng; không cấp Editor hoặc Owner cho test pipeline.
4. Quy định service account của smoke test chỉ có quyền gọi những API cần thiết.
5. Đặt Cloud Billing Budget lọc theo project/nhãn liên quan, với ngưỡng cảnh báo sớm.
6. Kiểm tra trang **IAM & Admin → Quotas & System Limits** của Cloud Build và Cloud Run trong region dự định dùng.
7. Tạo dashboard hoặc truy vấn Billing để theo dõi chi phí sau mỗi tuần.

Ví dụ bật API bằng danh tính bootstrap có đủ quyền:

~~~bash
gcloud services enable cloudbuild.googleapis.com \
  --project=BUILD_PROJECT_ID

gcloud services enable run.googleapis.com \
  --project=STAGING_PROJECT_ID
~~~

Chỉ quản trị viên hoặc cơ chế IaC được giao mới nên bật API và cấp IAM. Không đưa quyền quản trị project vào service account chỉ cần thực thi unit test.

### 4.1. Quyền IAM tối thiểu

| Chủ thể | Vai trò/quyền cần xem xét | Không cần |
|---|---|---|
| Build identity cho PR | Cloud Build chạy build, ghi log; thường không cần quyền lên dịch vụ khác | Cloud Run Admin, Cloud SQL Admin, Project Editor |
| Build identity cho staging gate | Quyền thực thi **một** Cloud Run Job, ví dụ `roles/run.invoker` trên Job | Quyền sửa tất cả Job hoặc deploy production |
| Cloud Run Job service identity | Quyền đọc dữ liệu thử nghiệm cần thiết hoặc gọi endpoint staging | Quyền vào dữ liệu production |
| Người cấu hình trigger | Quyền quản trị trigger và quyền `iam.serviceAccounts.actAs` phù hợp | Service account key dài hạn |
| Người xem billing/quota | Quyền xem billing, Monitoring, Service Usage phù hợp | Quyền chỉnh resource không liên quan |

Khi dùng **user-managed service account** cho Cloud Build và lưu log vào Cloud Logging, đặt `options.logging: CLOUD_LOGGING_ONLY` và cấp quyền ghi log phù hợp, chẳng hạn `roles/logging.logWriter` trong build project. Nếu dùng Cloud Storage bucket lưu log, phải có bucket được kiểm soát và quyền ghi tương ứng.

Lưu ý: với trigger, service account chọn trên **trigger** có hiệu lực; cấu hình `serviceAccount` trong YAML không ghi đè được danh tính trigger. Kiểm tra cả hai nơi để tránh một workflow chạy bằng danh tính mạnh hơn dự kiến.

## 5. Chọn chiến lược kiểm thử ưu tiên hiệu quả

Chi phí thấp thường đến từ việc **đổi điểm thực thi** thay vì chỉ giảm tài nguyên máy.

| Tầng | Ví dụ Java/Spring | Mức độ dùng GCP | Khi chạy |
|---|---|---|---|
| Unit | JUnit 5, Mockito kiểm tra business rules | Không | Mỗi commit/PR |
| Component | `@WebMvcTest`, MockMvc, fake outbound adapter | Không | Mỗi PR |
| Integration cô lập | Emulator Pub/Sub/Firestore; WireMock; Testcontainers khi môi trường hỗ trợ | Không cần project cloud thật, nhưng dùng CPU/RAM build | PR/merge tùy thời gian |
| Integration live | Kiểm tra IAM, giao tiếp Cloud Storage/SQL/Pub/Sub thật | Phát sinh quota và chi phí | Merge, staging hoặc theo lịch |
| End-to-end | Smoke qua service/staging gateway | Có | Trước release và sau deploy |
| Load/soak | Kiểm tra throughput, autoscaling và giới hạn dịch vụ | Có thể tốn nhiều tiền | Theo lịch riêng, có approval/budget |

Các emulator không tái hiện đầy đủ IAM, quota, billing, vận hành phân tán hoặc mọi hành vi của dịch vụ. Vì vậy, vẫn cần một số ít smoke test trên GCP thật. Tránh cho mọi pull request tự tạo Cloud SQL instance hay dịch vụ mạng riêng nếu test chỉ cần một fake adapter.

Đối với dự án có nhiều test nặng, tách test category bằng Maven Surefire/Failsafe. Chỉ dùng live integration khi trigger được phê duyệt và các dữ liệu đầu vào đã được chuẩn bị.

## 6. Chuẩn bị dự án Maven và nhóm test

Giả sử cấu trúc ứng dụng:

~~~text
checkout-api/
├── pom.xml
├── src/
│   ├── main/java/com/example/checkout/
│   └── test/java/com/example/checkout/
│       ├── PriceCalculatorTest.java
│       ├── CheckoutControllerTest.java
│       └── CheckoutRepositoryIT.java
├── cloudbuild.yaml
└── README.md
~~~

Theo Maven conventions, Surefire thường chạy `*Test` trong phase `test` và Failsafe chạy `*IT` trong phase `integration-test` và `verify`. Nếu đang sử dụng Gradle, có thể áp dụng các nguyên tắc tương tự với tasks `test` và `integrationTest`.

Ví dụ một phần `pom.xml` với khả năng tách riêng unit/integration:

~~~xml
<properties>
  <skipUnitTests>false</skipUnitTests>
  <skipITs>false</skipITs>
</properties>
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <skipTests>${skipUnitTests}</skipTests>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <skipITs>${skipITs}</skipITs>
      </configuration>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Trong phần cấu hình plugin trên, hai biểu thức thuộc tính Maven `${skipUnitTests}` và `${skipITs}` được dùng để điều khiển việc chạy từng nhóm test. Có thể thay đổi các giá trị này qua tùy chọn `-D` trong các lệnh ở dưới.

Chạy ở máy phát triển:

~~~bash
# Unit tests: chạy nhanh, không gọi dịch vụ GCP thật.
mvn -B -ntp -DskipITs=true test

# Integration tests: bỏ qua unit đã chạy ở bước trước.
mvn -B -ntp -DskipUnitTests=true -DskipITs=false verify
~~~

Phải bảo đảm test tên `*IT` sử dụng emulator/fake hoặc database thử nghiệm đúng phạm vi. Không viết integration test mặc định kết nối thẳng vào production thông qua Application Default Credentials của người phát triển.

### 6.1. Một nguyên tắc quan trọng về retries

Tách biệt **retry hạ tầng** và **retry assertion**:

- Retry ngắn có backoff phù hợp khi emulator/service vừa khởi động hoặc có lỗi mạng tạm thời.
- Không tự động retry toàn bộ test suite nhiều lần chỉ để che flakiness.
- Ghi lại số lần retry, nguyên nhân và thời gian chờ.
- Khi phát hiện `429 RESOURCE_EXHAUSTED`, giảm concurrency hoặc tốc độ gọi trước khi tăng quota.

Nếu test có side effect, phải gắn run ID duy nhất và idempotency key để retry không tạo dữ liệu trùng hoặc chi phí ngoài dự kiến.

## 7. Thực hành Cloud Build cho pipeline giá rẻ

Dưới đây là ví dụ **`cloudbuild.yaml` mẫu** nằm trong repo ứng dụng. Không tạo file YAML mới trong bài học này; đoạn code dùng để học viên sao chép vào dự án của mình.

~~~yaml
steps:
  - id: unit
    name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -ntp -DskipITs=true test
    timeout: 300s
    volumes:
      - name: m2-cache
        path: /root/.m2

  - id: integration
    name: maven:3.9-eclipse-temurin-21
    waitFor: [unit]
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -ntp -DskipUnitTests=true -DskipITs=false verify
    timeout: 480s
    volumes:
      - name: m2-cache
        path: /root/.m2

  - id: staging-smoke
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    waitFor: [integration]
    entrypoint: bash
    args:
      - -euc
      - |
        if [ "$_RUN_LIVE_TESTS" != "true" ]; then
          echo "SKIP live smoke: flag is disabled"
          exit 0
        fi
        gcloud run jobs execute "$_SMOKE_JOB" \
          --project="$_STAGING_PROJECT" \
          --region="$_REGION" \
          --wait
    timeout: 420s

substitutions:
  _RUN_LIVE_TESTS: "false"
  _SMOKE_JOB: "checkout-smoke"
  _STAGING_PROJECT: "example-staging"
  _REGION: "asia-southeast1"

timeout: 900s

options:
  logging: CLOUD_LOGGING_ONLY
~~~

**Cách hoạt động:**

1. Bước `unit` dùng tối đa 300 giây, và nếu thất bại thì các bước phụ thuộc không chạy.
2. Bước `integration` chạy sau unit; tối đa 480 giây; vẫn hoạt động trong worker Cloud Build. Bộ nhớ Maven repository nằm trên volume tạm để giảm tải lại dependency giữa các step.
3. Bước `staging-smoke` chỉ thực thi Cloud Run Job khi substitution `_RUN_LIVE_TESTS` là `true`. Mặc định không chạy live test.
4. `timeout: 900s` giới hạn tổng thời gian build; timeout mỗi bước chỉ là hạn mức của riêng bước đó.
5. `CLOUD_LOGGING_ONLY` lưu build log trong Cloud Logging; cần cấp quyền ghi log cho identity của build.
6. Các bước không gọi `gcloud run jobs update` hoặc tự tạo Cloud SQL, nên mặc định PR không sinh thêm dịch vụ có chi phí kéo dài.

Thời gian từng bước không cộng thành một cam kết tổng, vì còn thời gian chờ/pull image/khởi động. Tổng build timeout 900 giây là giới hạn riêng. Cloud Build mặc định có build timeout dài hơn; khai báo tường minh để chặn job mắc kẹt.

**Điều kiện bảo mật:** cờ `_RUN_LIVE_TESTS=true` chỉ là cơ chế lựa chọn hành vi. Nó **không phải ranh giới IAM**. Build identity chỉ được phép execute Job staging khi chính sách đã phê duyệt. Đối với PR không tin cậy, dùng trigger/service account không có quyền staging; tốt nhất tách hẳn cấu hình hoặc trigger live test khỏi PR pipeline.

### 7.1. Kiểm thử pipeline theo hai chế độ

Chạy mặc định trong project build đã cấu hình:

~~~bash
gcloud builds submit . \
  --project=BUILD_PROJECT_ID \
  --region=asia-southeast1 \
  --config=cloudbuild.yaml
~~~

Chạy live smoke khi đã có quyền, đủ quota và được phê duyệt:

~~~bash
gcloud builds submit . \
  --project=BUILD_PROJECT_ID \
  --region=asia-southeast1 \
  --config=cloudbuild.yaml \
  --substitutions=_RUN_LIVE_TESTS=true,_STAGING_PROJECT=STAGING_PROJECT_ID
~~~

Mỗi lệnh `gcloud builds submit` tải source lên Cloud Build và có thể phát sinh phí xử lý, lưu trữ/log và truyền dữ liệu. Chỉ chạy trong môi trường được giao; không mặc định project staging/region trong ví dụ đã tồn tại.

### 7.2. Cấu hình trigger

Trong Cloud Build Triggers, thiết lập:

- Trigger PR dùng `cloudbuild.yaml`, chỉ chạy khi thư mục Java/`pom.xml` hoặc tài liệu test liên quan thay đổi; có thể cấu hình included/ignored files.
- Trigger staging được gọi khi merge nhánh chính, theo lịch hoặc thao tác thủ công; dùng service account có quyền execute smoke Job.
- Trigger live yêu cầu **approval** trước khi khởi chạy nếu môi trường và quy trình yêu cầu.
- Thay đổi cấu hình pipeline, nâng cấp Maven/image hoặc sửa hạ tầng test phải được review.
- Không cho các fork hoặc PR chưa tin cậy tự sử dụng staging credentials.

Cloud Build cho phép cấu hình approval trên trigger. Approval chặn build cho đến khi người có quyền phê duyệt; nó không thay thế IAM, quota hay budget. Khi source code không thay đổi phần cần kiểm thử, trigger filtering giúp giảm tổng số lần chạy.

## 8. Tạo Cloud Run Job cho smoke test có giới hạn

Smoke Job nên sử dụng một container test image đã được xây dựng và kiểm tra riêng. Ví dụ, image có lệnh kiểm thử endpoint staging và kết thúc bằng exit code 0 nếu thành công, khác 0 nếu thất bại. Việc tạo và cấu hình Job thuộc bước bootstrap, không lặp lại trong mọi PR.

Lệnh minh họa của quản trị viên staging:

~~~bash
gcloud run jobs create checkout-smoke \
  --project=STAGING_PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/STAGING_PROJECT_ID/qa/checkout-smoke:approved \
  --tasks=1 \
  --parallelism=1 \
  --max-retries=0 \
  --task-timeout=300s \
  --cpu=1 \
  --memory=512Mi
~~~

Thay `:approved` bằng image digest được xác minh trong quy trình release nếu cần đảm bảo tính bất biến. Job này phải được cấu hình service identity riêng với quyền ít nhất để gọi dịch vụ staging cần kiểm thử.

**Giới hạn có ý nghĩa:**

- `--tasks=1`: một task mỗi execution trong lab; không phát sinh hàng chục worker cùng lúc.
- `--parallelism=1`: không chạy nhiều task song song.
- `--max-retries=0`: nếu test thất bại, dừng để điều tra thay vì tự lặp và phát sinh tiền. Production job có thể dùng retry có kiểm soát.
- `--task-timeout=300s`: task không chạy vô hạn.
- CPU và memory nhỏ, đủ cho smoke test ngắn; tăng khi có bằng chứng OOM hoặc thiếu CPU.
- Job chỉ chạy khi pipeline staging gate được phép gọi `jobs.execute`.

Chạy thủ công để kiểm tra:

~~~bash
gcloud run jobs execute checkout-smoke \
  --project=STAGING_PROJECT_ID \
  --region=asia-southeast1 \
  --wait
~~~

Dùng `--wait` để CLI chờ Job execution hoàn thành, giúp pipeline lấy kết quả thành công/thất bại và dừng release nếu cần. Đừng chỉ kiểm tra rằng yêu cầu tạo execution đã được chấp nhận.

### 8.1. Quản lý dữ liệu thử nghiệm

Nếu test ghi vào Firestore, Cloud SQL hoặc Cloud Storage, đặt namespace theo build ID:

~~~text
test-runs/
  run-<BUILD_ID>/
    orders/
    receipts/
    logs/
~~~

Một số nguyên tắc:

- Dữ liệu phải là dữ liệu giả, không có PII sản xuất.
- Dùng khóa định danh chạy test trong mọi bản ghi, object prefix hoặc schema.
- Hạn chế tài nguyên dùng chung: một Job task có thể đủ, không cần tạo database instance mới cho mỗi run.
- Có `finally`, cleanup step, scheduled cleanup hoặc lifecycle rule với TTL dự phòng.
- Nếu cleanup thất bại, pipeline phải ghi nhận resource còn sót và cảnh báo.
- Với Cloud Storage, cân nhắc lifecycle policy cho prefix/bucket thử nghiệm; với database, cleanup theo run ID và TTL khi loại dữ liệu hỗ trợ.

Không xóa cả bucket hoặc database dùng chung trong cleanup. Tài nguyên thử nghiệm cần có nhãn/chủ sở hữu để quy trình dọn dẹp xác định đúng phạm vi.

## 9. Quản lý quota theo từng tầng

### 9.1. Cloud Build

Cloud Build có quota cho concurrent builds, CPU đang dùng và tốc độ gọi API. Quota thay đổi theo region, loại pool, dự án và lịch sử sử dụng, do đó không ghi cứng một con số quota làm quy tắc cho mọi project. Khi queue tăng:

1. Kiểm tra trang Quotas và lịch sử build theo region.
2. Xác định số build đang running/queued và tần suất trigger.
3. Giảm số trigger không cần thiết, giảm retry, gộp build trùng commit.
4. Phân loại test nhanh/tốn chi phí để chỉ chạy live test ở gate.
5. Chỉ yêu cầu tăng quota khi pipeline đã được tối ưu và có nhu cầu thực tế.

Build **đang queued** không bị tính build-minutes như build đang xử lý, nhưng có thể kéo dài thời gian chờ phát hành. Tăng concurrency làm pipeline nhanh hơn trong một số trường hợp nhưng không nhất thiết giảm tổng chi phí.

### 9.2. Cloud Run và dịch vụ phụ thuộc

Hạn chế đồng thời không chỉ ở `parallelism`. Nếu Job dùng 1 task nhưng chạy 100 request song song bên trong Java, API/DB vẫn chịu 100 request.

Giới hạn thêm trong test runner, ví dụ:

~~~java
import java.util.concurrent.Semaphore;

public final class ApiRateGate {
    private final Semaphore slots = new Semaphore(3);

    public void run(Runnable request) throws InterruptedException {
        slots.acquire();
        try {
            request.run();
        } finally {
            slots.release();
        }
    }
}
~~~

Ví dụ chỉ cho tối đa ba đoạn xử lý đồng thời **trong một JVM**. Semaphore không điều phối nhiều Job instance và không giới hạn tốc độ request theo thời gian; nếu cần giới hạn RPS, dùng rate limiter có backoff/jitter và phối hợp toàn hệ thống.

Giữ connection pool staging có kích thước nhỏ, dùng page size thấp cho dữ liệu test và không tạo vòng lặp polling nhanh khi gặp lỗi. Với test Pub/Sub, cân nhắc số message và ack deadline phù hợp; với Cloud SQL, cân nhắc max connections và số instance; với Cloud Storage, tránh upload/download object lớn chỉ để kiểm tra một contract.

### 9.3. Rate limit và retry có giới hạn

Một chiến lược an toàn:

- Retry chỉ lỗi tạm thời được xác định, như 429, 503 hoặc timeout do mạng.
- Exponential backoff có jitter, tổng số lần thử hữu hạn.
- Đặt deadline tổng cho mỗi thao tác, không chỉ timeout cho từng attempt.
- Mỗi request ghi log số lần thử và lý do; dùng idempotency key khi có side effect.
- Nếu quota vẫn bị vượt, dừng hoặc giảm tải thay vì retry vô hạn.

Một test suite ổn định nên thất bại rõ ràng khi quota không đủ và báo nguyên nhân cho nhóm vận hành, thay vì âm thầm đợi hàng giờ.

## 10. Kiểm soát chi phí bằng nhiều lớp

Một ngân sách vận hành hợp lý kết hợp nhiều biện pháp:

| Lớp | Kiểm soát | Tác dụng |
|---|---|---|
| Trước khi chạy | Trigger filter, approval, phân loại test | Giảm số lần build tốn chi phí |
| Trong build | Build timeout, step timeout, machine size phù hợp | Giảm thời gian/CPU bị tiêu thụ |
| Trong test live | Task count, parallelism, retries, request rate | Giảm tải và chi phí downstream |
| Tài nguyên thử nghiệm | Project riêng, resource labels, TTL, cleanup | Tránh tài nguyên sống lâu sau test |
| Theo dõi | Billing budget, alerts, billing export, Monitoring | Phát hiện xu hướng bất thường |
| Chính sách | IAM, quota và quyền bật dịch vụ | Hạn chế hành động tốn tiền ngoài phạm vi |

**Không dùng budget alert như cầu dao tự động.** Dữ liệu chi phí có độ trễ; chi phí có thể vượt ngưỡng trước khi email hoặc Pub/Sub notification đến. Một số dịch vụ hỗ trợ spend cap hoặc các phương án giới hạn riêng, nhưng cần kiểm tra tính khả dụng, hành vi dừng và ảnh hưởng đến workload trước khi dựa vào đó.

### 10.1. Ước tính tiền Cloud Build

Cloud Build tính phí theo **build-minutes đang được xử lý** cùng loại máy và khu vực; thời gian queued không tạo build-minutes. Ngoài ra có thể phát sinh Cloud Logging, Cloud Storage, network egress, Artifact Registry và phí dịch vụ được test.

Công thức đơn giản:

~~~text
Chi phí Build ước tính ≈ build-minutes tính phí × đơn giá theo loại worker/region

Chi phí toàn pipeline ≈ Cloud Build + Cloud Run Job + API/DB/storage
                         + logging + egress + tài nguyên còn sót
~~~

Ví dụ để kiểm tra ngân sách: một nhóm có 60 build mỗi ngày, mỗi build 5 phút, chạy 20 ngày/tháng:

~~~text
60 build/ngày × 5 phút/build × 20 ngày = 6.000 build-minutes/tháng
~~~

Tài liệu giá Cloud Build tại thời điểm viết công bố một mức free tier theo billing account cho loại máy đủ điều kiện ở default pool; ưu đãi, đơn giá và giới hạn có thể thay đổi. Nếu **giả sử** được áp dụng đầy đủ 2.500 phút miễn phí/tháng và đơn giá ví dụ là 0,006 USD/phút, phần còn lại của tình huống này là:

~~~text
(6.000 − 2.500) × 0,006 USD ≈ 21 USD/tháng
~~~

Con số trên chỉ minh họa **riêng build-minutes**, chưa cộng tài nguyên khác và chỉ đúng với giả định ưu đãi/đơn giá cụ thể. Trong thực tế, đối chiếu trang Cloud Build Pricing theo region, loại máy, billing account, thuế và phí phụ trợ.

Cách giảm chi phí mạnh nhất thường là giảm lượt chạy lặp hoặc chuyển live test sang emulator, không phải luôn chọn máy nhỏ nhất. Máy quá chậm có thể làm thời gian thực thi tăng nhiều và khiến tổng build-minutes tốn hơn.

### 10.2. Chi phí live tests

Cloud Run Jobs có thể phát sinh phí vCPU-seconds, GiB-seconds và các thành phần khác tùy cấu hình; các dịch vụ được Job gọi cũng có thể tính phí. Nếu một Job bị retry nhiều lần, tổng thời gian tính phí tăng theo mỗi attempt.

Để ước tính, lấy số task × số attempt × thời gian chạy × tài nguyên phân bổ, rồi tra pricing của Cloud Run theo region. Bổ sung chi phí Cloud SQL, Pub/Sub, Storage, logs và egress. Gắn nhãn cho hạ tầng staging và lưu `BUILD_ID` trong logs để tìm nguồn chi phí tăng đột biến.

## 11. Giám sát quota, chất lượng và chi phí

Trên Cloud Build, theo dõi:

- Thời gian build p50/p95, tỷ lệ thất bại và timeout.
- Số build queued/running, số lượt theo trigger và branch.
- Thời gian unit/integration/live smoke riêng biệt.
- Tỷ lệ flaky test, số lần retry, lỗi `429`/`RESOURCE_EXHAUSTED`.
- CPU/memory hoặc loại máy đã chọn và tổng build-minutes.

Trên Cloud Run/Cloud Monitoring, theo dõi:

- Số executions, executions failed/succeeded và task retries.
- Task duration, memory/CPU allocation, lỗi khi gọi API downstream.
- Cloud SQL connection count và saturation.
- Pub/Sub backlog, số message test, retries và dead-letter.
- Cloud Logging volume và lưu trữ dữ liệu test.

Trên Cloud Billing:

- Chi phí theo **project**, dịch vụ, SKU và nhãn khi có.
- So sánh chi phí theo tuần/tháng trước và sau thay đổi trigger.
- Budget alert thresholds phù hợp với ngân sách thực tế.
- Với tổ chức cần phân tích sâu, bật Cloud Billing export sang BigQuery để tính cost per build hoặc cost per test suite từ các dữ liệu có thể liên kết; lưu ý chi phí không luôn được gắn trực tiếp với một build ID.

### Đặt ngưỡng cảnh báo nội bộ

Ví dụ nguyên tắc khi đưa vào vận hành:

| Dấu hiệu | Hành động |
|---|---|
| PR pipeline p95 vượt mục tiêu | Kiểm tra test chậm, caching và trigger trùng |
| Cloud Build queue tăng | Giảm parallel builds/trigger dư, xem quota theo region |
| Xuất hiện 429 liên tục | Giảm request concurrency, thêm backoff có giới hạn |
| Cloud Run Job kéo dài gần timeout | Điều tra deadlock/latency và test data |
| Budget chạm 50% hoặc 80% sớm | Kiểm tra chi phí theo SKU và tần suất pipeline |
| Phát hiện resource staging không có owner/TTL | Tạm dừng live trigger và dọn theo run ID |

Ngưỡng 50% và 80% là ví dụ chính sách cảnh báo; chọn theo mức chi tiêu, chu kỳ và độ trễ billing của tổ chức. Hệ thống không nên tự xóa dữ liệu production khi chạm budget cảnh báo.

## 12. Quy trình chạy lab từ đầu đến cuối

### Bước 1 — Lập baseline

Ghi lại số build/ngày, thời gian build trung bình, quota concurrent builds, số lần chạy Job staging, chi phí tháng trước và hiện trạng test flaky. Nếu chưa có dữ liệu, thử nghiệm trên một branch và đo vài lượt trước khi bật trigger rộng.

### Bước 2 — Chạy test nội bộ

Chạy Maven unit test và integration dùng emulator/fake trên máy local. Xác minh test không sử dụng credentials GCP hoặc gọi endpoint production; test thực sự phù hợp với tên `*Test` và `*IT`.

### Bước 3 — Gửi Cloud Build ở chế độ mặc định

Dùng cấu hình phần 7 với `_RUN_LIVE_TESTS=false`. Kiểm tra step durations, tổng build time, log và kết quả test. Điều chỉnh timeout vừa đủ, có dự phòng; không tăng lên vài giờ chỉ để né lỗi.

### Bước 4 — Cấu hình live smoke Job một lần

Trong staging project, tạo Job `checkout-smoke` như phần 8, dùng image test đã được review. Kiểm tra số task, parallelism, retry, CPU, memory và task timeout. Tạo service identity chỉ có quyền đối với resource staging cần test.

### Bước 5 — Kích hoạt có phê duyệt

Dùng trigger staging riêng hoặc chạy `gcloud builds submit` có `_RUN_LIVE_TESTS=true` bằng danh tính đủ quyền. Không cho PR không tin cậy tự bật live test qua substitution.

### Bước 6 — Kiểm tra kết quả và dọn dữ liệu

Xác minh Job execution đạt, kiểm tra logs/metrics và xóa dữ liệu theo run ID. Chạy thêm cleanup scheduled job nếu cần để xử lý trường hợp build bị hủy trước khi cleanup.

### Bước 7 — Đo và tinh chỉnh

So sánh build-minutes, số lượt live Job, thời gian p95 và mức chi tiêu với baseline. Tăng parallelism hoặc machine size chỉ khi hiệu quả đo được lớn hơn chi phí và không làm vượt quota downstream.

### Bước 8 — Đóng cổng phát hành khi test thất bại

Đưa kết quả pipeline vào branch protection/release gate. Chỉ cho phép triển khai sau khi điều kiện chất lượng đạt và có phê duyệt phù hợp. Một pipeline test thành công nhưng không dọn tài nguyên hoặc không gửi kết quả về release gate chưa được xem là hoàn tất quy trình vận hành.

## 13. Tình huống sự cố và xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cloud Build báo quota exceeded hoặc queued lâu | Nhiều builds đồng thời, ít CPU quota | Kiểm tra quota theo region/pool, giảm trigger trùng và số build đồng thời |
| Integration test bị 429 | Gọi API quá nhanh hoặc quá nhiều client | Throttle, exponential backoff có jitter, hạn chế parallelism |
| Cloud Run Job lặp thất bại và tạo phí lớn | `max-retries` quá cao, lỗi không thể tự hồi phục | Giảm retries; sửa lỗi gốc; đặt deadline |
| Cloud SQL báo hết connection | Nhiều task, pool quá lớn hoặc connection leak | Giới hạn job tasks, pool và cleanup connections |
| CI mất quá nhiều thời gian tải dependency | Không có cache, mạng chậm | Sử dụng cache hợp lý trong build, pin dependency; đo kết quả |
| Test trôi qua nhưng live step bị skip | `_RUN_LIVE_TESTS=false` | Kiểm tra loại trigger và gate trước release; không coi PR pass là live-pass |
| Budget alert gửi sau khi phí đã tăng | Billing có độ trễ; alert không hard cap | Dùng quota/IAM/timeout/TTL làm guardrail trực tiếp |
| Resource staging bị giữ lâu | Cleanup không chạy khi build hủy | TTL/lifecycle và scheduled cleanup độc lập |
| Nhiều PR dùng chung dữ liệu test bị đụng nhau | Không gắn run ID hoặc namespace | Tách namespace và test isolation |
| Live smoke lỗi quyền | Build service account không có quyền chạy Job | Cấp quyền execute đúng Job; không cấp quyền sửa toàn project |

### Phân biệt lỗi quota với lỗi ứng dụng

Khi test thất bại, kiểm tra theo thứ tự:

1. Log cho thấy assertion thất bại hay lỗi hạ tầng (`429`, `503`, `RESOURCE_EXHAUSTED`)?
2. Có bao nhiêu request/job task được chạy đồng thời? Có retry storm không?
3. Quota nào áp dụng: Cloud Build, Cloud Run, Cloud SQL, Pub/Sub hay dịch vụ khác?
4. Project, region và service account có đúng môi trường?
5. Có resource/test data tồn tại từ lượt chạy trước gây tranh chấp không?
6. Mức chi phí tăng do build duration, live Job, logs, storage hay dữ liệu còn sót?
7. Sau khi giảm tải hoặc sửa test, cùng một test có tái hiện được lỗi không?

Không mặc định tăng quota ngay khi thấy `429`. Quota có thể đang ngăn pipeline vô tình làm quá tải một dịch vụ staging vốn phải chia sẻ với nhóm khác.

## 14. Những lỗi thiết kế cần tránh

- **Tất cả test đều dùng cloud thật:** pipeline chậm và chi phí tăng, dễ gặp giới hạn quota.
- **Không có deadline:** test treo nhiều giờ hoặc cứ chờ API vô hạn.
- **Retry vô hạn:** một lỗi tạm thời biến thành hàng nghìn request.
- **Đặt budget rồi coi đó là hard cap:** cảnh báo có độ trễ và không chặn tất cả tài nguyên.
- **Dùng một service account có quyền admin:** PR có thể thao tác resource ngoài phạm vi test.
- **Không kiểm tra trigger filtering:** sửa tài liệu cũng kích hoạt full integration suite.
- **Tăng máy build trước khi đo:** máy mạnh hơn có thể tăng chi phí mà không cải thiện đáng kể p95.
- **Live Job không có giới hạn task/parallelism:** làm quá tải Cloud SQL hoặc API staging.
- **Dọn resource chỉ trong bước cuối:** build bị hủy sẽ bỏ sót dữ liệu/test infrastructure.
- **Không phân tách test và release gate:** quy trình phát hành có thể bỏ qua smoke test dù CI màu xanh.

## 15. Checklist sẵn sàng áp dụng

- [ ] PR pipeline có unit test và integration cô lập.
- [ ] Live integration/smoke test tách khỏi PR không tin cậy.
- [ ] Cloud Build có step timeout và tổng build timeout.
- [ ] Tần suất trigger và đường dẫn file được giới hạn hợp lý.
- [ ] Cloud Build service account có IAM tối thiểu, cấu hình logs phù hợp.
- [ ] Quota Cloud Build và dịch vụ downstream đã được kiểm tra theo project/region.
- [ ] Cloud Run Job staging có task count, parallelism, timeout và retries rõ ràng.
- [ ] Test dùng dữ liệu giả, run ID riêng và không ghi production.
- [ ] Các API call có timeout, concurrency guard và retry hữu hạn.
- [ ] Staging có cleanup tự động và TTL/lifecycle dự phòng.
- [ ] Có Billing Budget alert; hiểu rõ cảnh báo không đồng nghĩa hard cap.
- [ ] Có dashboard logs, test failure, 429, build-minutes và chi phí.
- [ ] Live test kết quả được nối với release gate.
- [ ] Có người sở hữu và quy trình xử lý khi quota/cost tăng đột ngột.

## 16. Câu hỏi tự kiểm tra

1. Vì sao unit test và integration dùng emulator nên chạy trước smoke test trên Google Cloud thật?
2. Cloud Build step timeout và build timeout khác nhau thế nào?
3. Nếu đặt `_RUN_LIVE_TESTS=false`, pipeline có đủ bằng chứng rằng kết nối tới Cloud SQL staging đang hoạt động không?
4. Vì sao service account PR không nên được cấp quyền chạy Job staging?
5. Cloud Billing Budget dạng alerts-only có dừng chi tiêu khi chạm 100% không?
6. Một Cloud Run Job có 20 task nhưng parallelism bằng 1 nghĩa là gì?
7. Vì sao tăng retry không phải cách xử lý tốt khi API báo quota exhausted liên tục?
8. Nếu build bị hủy trước bước cleanup, phải có cơ chế nào để dọn dữ liệu test?
9. Những số liệu nào cần đo trước khi quyết định tăng CPU của Cloud Build worker?

**Gợi ý đáp án**

1. Vì chạy local/fake nhanh và ít tốn tiền, giảm số lần gọi API có quota; smoke trên cloud dành cho kiểm tra tích hợp thật.
2. Step timeout giới hạn một bước, build timeout giới hạn toàn bộ lượt build.
3. Không; pipeline mới xác minh test không cần live GCP, chưa kiểm tra IAM/network của staging.
4. Vì mã PR chưa tin cậy có thể chạy tùy ý; IAM staging phải thuộc trigger/phần công việc được kiểm soát.
5. Không. Alerts-only chỉ cảnh báo; không tự áp đặt hard cap.
6. Job thực hiện tối đa một task đồng thời; các task còn lại được lên lịch khi có chỗ trống.
7. Retry không kiểm soát làm tăng request, kéo dài thời gian và phí; cần giảm tải, backoff và xem quota.
8. Cleanup có TTL/lifecycle hoặc scheduled job độc lập với pipeline.
9. Thời gian build p50/p95, số lượt chạy, chi phí theo loại worker, tỷ lệ failure, queue và mức độ nghẽn CPU thực tế.

## Tài liệu tham khảo

- [Google Cloud: Cloud Build quotas and limits](https://docs.cloud.google.com/build/quotas)
- [Google Cloud: Build config file schema và timeout](https://docs.cloud.google.com/build/docs/build-config-file-schema)
- [Google Cloud: Cloud Build pricing](https://cloud.google.com/build/pricing)
- [Google Cloud: Create and manage build triggers](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Google Cloud: Substituting variable values in Cloud Build](https://docs.cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Google Cloud: User-managed service account for Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Google Cloud: Run Cloud Run jobs](https://docs.cloud.google.com/run/docs/execute/jobs)
- [Google Cloud: Cloud Run jobs parallelism](https://docs.cloud.google.com/run/docs/configuring/parallelism)
- [Google Cloud: Cloud Run jobs maximum retries](https://docs.cloud.google.com/run/docs/configuring/max-retries)
- [Google Cloud: Create and manage budgets and alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Apache Maven: Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven: Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)

