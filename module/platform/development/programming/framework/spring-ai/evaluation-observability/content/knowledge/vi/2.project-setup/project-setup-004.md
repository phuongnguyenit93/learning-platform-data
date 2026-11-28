# Tách thông tin xác thực và tài nguyên theo môi trường

> **Chương:** Thiết lập dự án
>
> **Phạm vi:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá relevance, fact checking, RAG/tool calling và quan sát metrics, traces, token usage, chi phí, độ trễ để tìm nguyên nhân suy giảm chất lượng qua các phiên bản prompt, model và pipeline.
> **Bộ nền minh họa:** Java 21, Spring Boot 4.2.0, Spring AI 2.1.0; cú pháp cấu hình tham chiếu tài liệu chính thức tại ngày 27/11/2026.

## 1. Mục tiêu và tình huống thực tế

Sau bài học, bạn có thể:

1. Phân biệt **secret**, cấu hình thông thường, dữ liệu thử nghiệm và tài nguyên hạ tầng của một ứng dụng Spring AI.
2. Thiết kế các môi trường **local/dev, test, staging, production** với quyền truy cập và tài nguyên tách biệt.
3. Dùng Spring Boot **profiles**, **environment variables**, **externalized configuration** và **configtree** để cấp cấu hình mà không nhúng khóa API vào repository.
4. Bố trí credential và hạn mức riêng cho **mô hình sinh câu trả lời**, **mô hình đánh giá**, embedding, vector database, tool và telemetry.
5. Kiểm chứng ứng dụng fail closed khi thiếu secret hoặc tham chiếu sai tài nguyên, đồng thời tạo baseline có thể đối chiếu khi chạy evaluation.

**Tình huống:** nhóm phát triển một trợ lý RAG dùng Spring AI, có pipeline sinh câu trả lời và một job LLM-as-a-Judge chấm relevance/fact checking hàng đêm. Nhà phát triển muốn thử prompt và retriever mới bằng dữ liệu nội bộ. Nếu laptop, CI và môi trường staging đều dùng **cùng khóa provider, cùng PGvector và cùng tài khoản quan sát production**, một lệnh nhập dữ liệu hoặc chạy benchmark có thể truy cập nhầm dữ liệu thật, thay đổi index, tiêu tốn ngân sách production và làm nhiễu traces.

**Nguyên tắc:** mỗi môi trường có **danh tính, quyền và tài nguyên được phép**. Dùng profile để chọn cấu hình; sử dụng **IAM/RBAC, tài khoản/secret riêng, kết nối mạng và phân quyền tài nguyên** để thực thi sự tách biệt. Chỉ dùng profile là chưa đủ để bảo vệ production.

## 2. Cần tách những gì?

| Nhóm | Ví dụ trong Spring AI | Mục đích tách |
|---|---|---|
| **Credential nhà cung cấp model** | API key, project ID, tổ chức, quyền gọi model | Không dùng chung hạn mức/billing và giảm phạm vi ảnh hưởng khi lộ khóa |
| **Credential dữ liệu** | JDBC user/password, token vector DB, object storage | Test/staging không được đọc/ghi corpus production |
| **Credential tool** | Token CRM, email, thanh toán, ticketing, search API | Bài test tool calling không được tạo hành động ngoài ý muốn |
| **Credential telemetry** | Token OTLP, API key của trace/metrics backend | Không trộn trace hoặc gửi dữ liệu nhạy cảm sang tenant không phù hợp |
| **Tài nguyên model** | Provider project, model deployment, endpoint, quota | Đo chi phí, độ trễ và lỗi đúng môi trường |
| **Kho dữ liệu RAG** | Postgres/PGvector, collection/index, embedding, bộ tài liệu | Tránh ghi đè index và nhiễm dữ liệu giữa các lần đánh giá |
| **Evaluation dataset** | Bộ QA, ground truth, rubric, phiên bản judge | So sánh chất lượng trên tập dữ liệu xác định, được cấp quyền |
| **Nơi lưu kết quả** | Database, object store, artifact/trace storage | Tách báo cáo thử nghiệm khỏi log và dữ liệu người dùng thật |

Cần xem cả **resource identifiers** (project/tenant/namespace/cluster/database/schema/index) lẫn credential. Hai API key khác nhau nhưng cùng có quyền truy cập một production database vẫn chưa đạt yêu cầu phân tách.

### Bốn loại thông tin thường bị nhầm

- **Secret:** API key, private key, password, client secret, token phiên. Không xuất hiện trong Git, Docker image, test fixture, log hoặc trace.
- **Cấu hình không bí mật:** tên model, region, timeout, endpoint hostname công khai, ngưỡng đánh giá, sampling rate. Có thể quản lý bằng YAML/ConfigMap nhưng vẫn cần kiểm soát thay đổi.
- **Dữ liệu nhạy cảm:** prompt thật, văn bản truy xuất, câu trả lời, metadata người dùng. Chúng không phải “secret cấu hình” nhưng vẫn phải áp dụng bảo vệ và retention.
- **Metadata thí nghiệm:** phiên bản prompt, model, dataset, commit, chi phí tổng hợp, metric định lượng. Có thể lưu lâu hơn nếu không chứa dữ liệu riêng tư hoặc ID có thể liên kết đến cá nhân.

Không nên ghi khóa API thành dạng “đã mã hóa Base64” trong Git và coi đó là cách quản lý secret. Base64 chỉ là mã hóa biểu diễn, có thể giải mã trực tiếp.

## 3. Ma trận môi trường và ranh giới tài nguyên

| Tiêu chí | Local / dev | CI / test | Staging / preprod | Production |
|---|---|---|---|---|
| Mục tiêu | Phát triển, debug | Kiểm thử lặp lại | Kiểm tra release gần điều kiện thật | Phục vụ người dùng |
| Model/provider | Model local hoặc project dev có quota thấp | Mock/fake; integration có tài khoản test | Project staging riêng | Project prod riêng |
| API key | Secret cá nhân/dev đã giới hạn | Secret tạm thời của CI hoặc không cần key | Secret staging từ secret manager | Secret prod với quyền tối thiểu |
| Vector DB | DB/container local | Ephemeral DB/test schema | Cluster/DB/index staging | Cluster/DB/index prod |
| Dữ liệu | Giả lập hoặc đã ẩn danh | Fixture có nhãn | Synthetic / dữ liệu đã được phép dùng | Dữ liệu thật theo quyền nghiệp vụ |
| Tools | Sandbox hoặc mock | Fake/stub | Sandbox endpoint, quyền ghi kiểm soát | Chỉ tools được phê duyệt |
| Observability | Local collector/backend | Không export hoặc isolated test tenant | Tenant staging | Tenant prod với retention riêng |
| Evaluation | Khám phá, phân tích lỗi | Deterministic assertions | Regression/canary có kiểm soát | Monitoring mẫu hợp lệ/được cho phép |
| Quota/chi phí | Thấp, cảnh báo nhanh | Giới hạn theo job | Ngân sách staging | Ngân sách riêng có alert/escalation |

**Staging không mặc nhiên được sao chép toàn bộ production.** Nếu cần đánh giá phản ánh thực tế, chọn tập dữ liệu đã được phép chuyển môi trường, có thể mask/pseudonymize và kiểm tra yêu cầu bảo mật. Một bản sao database đã xóa vài trường hiển thị vẫn có thể chứa dữ liệu nhạy cảm trong metadata, embedding, backup hoặc logs.

### Kiến trúc tham chiếu

~~~mermaid
flowchart TB
  subgraph D["DEV / CI"]
    DK["Dev/test credentials"]
    DV["Vector DB / fixtures riêng"]
    DJ["Judge sandbox"]
    DT["Telemetry dev/test"]
  end
  subgraph S["STAGING"]
    SK["Staging credentials"]
    SV["Staging vector index"]
    SJ["Staging evaluation dataset"]
    ST["Staging telemetry"]
  end
  subgraph P["PRODUCTION"]
    PK["Prod credentials"]
    PV["Production corpus / vector DB"]
    PT["Production telemetry"]
    PJ["Prod inference endpoint"]
  end
  DK --> DV
  DK --> DJ
  DV --> DT
  SK --> SV
  SV --> SJ
  SJ --> ST
  PK --> PJ
  PJ --> PV
  PV --> PT
~~~

Sơ đồ thể hiện mục tiêu **không có đường truy cập ngang môi trường**. Ranh giới thực tế phải được kiểm soát bằng phân quyền identity, firewall/network policy, endpoint, namespace và quyền trên tài nguyên, không chỉ bằng cách đặt tên khác nhau.

## 4. Nguyên tắc thiết kế credential

### 4.1. Mỗi môi trường một identity và secret riêng

Ví dụ nhóm dùng một provider cho generator và judge:

| Workload | Credential dự kiến | Quyền |
|---|---|---|
| Dev generator | `ai-dev-generator` | Chỉ model/project dev, quota thấp |
| Staging generator | `ai-staging-generator` | Chỉ model/project staging |
| Staging evaluation worker | `ai-staging-judge` | Chỉ judge model/dataset staging, không có tool ghi prod |
| Production generator | `ai-prod-generator` | Chỉ model/project prod, các tool cần thiết |
| Production evaluation worker (nếu có) | `ai-prod-judge` | Chỉ dữ liệu mẫu được phép, quyền đọc; chi phí riêng |

Đây là **tên danh tính minh họa**, không phải tên secret thực của nhà cung cấp. Nếu provider không hỗ trợ key riêng theo từng vai trò, có thể dùng **tài khoản/project riêng, gateway tách quyền và quota**, hoặc đặt generator và judge ở hai workload có identity khác nhau.

**Cảnh báo Spring AI cụ thể:** Hai `ChatClient` cùng dùng một **auto-configured `OpenAiChatModel`** nhưng khác `defaultOptions.model` có thể chọn **hai model IDs**, song vẫn dùng **cùng connection và API key** của `ChatModel` mặc định. Muốn hai API key thực sự độc lập, cần:

1. Tách thành **API generator** và **evaluation worker** ở hai process/deployment, mỗi process nhận credential riêng; hoặc
2. Tạo **hai ChatModel/connection beans** bằng cấu hình tường minh, rồi gắn `ChatClient` đúng bean; kiểm tra version API và observability; hoặc
3. Sử dụng gateway/provider project có phân quyền và routing có kiểm soát.

Trong bài này, ví dụ hạ tầng ưu tiên **hai deployment cùng một artifact** vì dễ audit ranh giới, restart/rotate secret và quy chi phí. Hai service có thể dùng cùng codebase nhưng **không dùng chung secret**.

### 4.2. Credential không phải resource selector duy nhất

Nhà cung cấp có thể có:

- **project/organization ID** để định tuyến billing và quota;
- **base URL** để chọn region/gateway/endpoint;
- **model/deployment ID** để chọn loại model;
- **API key** hoặc workload identity để xác thực.

Với OpenAI starter của Spring AI 2.1, các property có sẵn gồm **spring.ai.openai.api-key**, **spring.ai.openai.base-url**, **spring.ai.openai.organization-id**, **spring.ai.openai.project-id**. Hai override chuyên biệt **spring.ai.openai.chat.api-key** và **spring.ai.openai.embedding.api-key** có thể ghi đè key chung cho chat/embedding. Chúng **không tự tạo ra hai tài khoản generator/judge** khi cả hai đều là chat model; trường hợp đó cần thiết kế hai workload/beans như trên.

**Không** đặt quyền truy cập tài nguyên dựa trên một chuỗi `APP_ENV=prod` do caller tùy ý truyền. Hệ thống đích phải xác minh quyền của identity và policy bên ngoài ứng dụng.

### 4.3. Phân biệt “bí mật” và “tham số phiên bản”

Không ghi credential vào artifact thí nghiệm, nhưng cần ghi **tham chiếu an toàn** và version của resource. Ví dụ kết quả benchmark có thể ghi:

~~~yaml
run_id: "staging-rag-20261127-01"
environment: "staging"
provider_project_alias: "ai-staging"
generator_model: "provider-generator-model"
judge_model: "provider-judge-model"
dataset_revision: "rag-fixtures-v4"
index_revision: "staging-index-v9"
prompt_revision: "prompt-v12"
pipeline_revision: "pipeline-v5"
credential_version_ref: "secret-version-42" # Chỉ ID/version, KHÔNG có giá trị secret
~~~

Không in log có toàn bộ `Environment`, request headers, datasource URL kèm credentials hoặc một `Map<String,String>` chứa tokens.

## 5. Spring Boot externalized configuration và profiles

Spring Boot giải quyết thuộc tính theo thứ tự ưu tiên từ nhiều **PropertySource** (file, environment, system properties, command-line, config import...). **Profile** chọn tập cấu hình, còn nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị. Đây là đặc tính tiện dụng nhưng cũng tạo rủi ro khi có override không được kiểm soát.

Ví dụ cấu trúc cấu hình khuyến nghị:

~~~text
src/main/resources/
  application.yml            # mặc định chung, không có secret
  application-dev.yml        # dev-only endpoints, quota thấp
  application-test.yml       # test offline / fixture
  application-staging.yml    # staging resources, secret volume
  application-prod.yml       # production resources, secret volume
~~~

Các file này là **ví dụ cấu trúc bài học**, không phải thao tác tạo thêm file trong repository hiện tại. Trong dự án thực tế có thể dùng nhiều document trong một YAML với `spring.config.activate.on-profile`, nhưng **không khai báo `spring.profiles.active` bên trong profile-specific document**.

### 5.1. application.yml — mặc định an toàn

~~~yaml
spring:
  application:
    name: spring-ai-quality-lab
  profiles:
    default: none
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
      observations:
        log-prompt: false
        log-completion: false

management:
  endpoints:
    web:
      exposure:
        include: "health,info"

app:
  evaluation:
    enabled: false            # PROPERTY TỰ ĐỊNH NGHĨA: code phải thực thi
~~~

Giải thích:

- **Không** lưu `spring.ai.openai.api-key` hoặc `spring.datasource.password` trong file chung.
- **spring.profiles.default: none** thay tên default profile khi không có active profile, nhưng **không tự từ chối khởi động**. Dự án cần kiểm tra profile hợp lệ trong startup/CI và bảo đảm app không truy cập resource nếu thiếu cấu hình.
- Hai cờ `log-prompt: false`, `log-completion: false` dành cho **ChatClient** và **ChatModel observations**. Mặc định Spring AI không xuất full prompt/completion; tiếp tục để tắt ngoài môi trường lab đã được kiểm soát.
- **app.evaluation.enabled** là property của ứng dụng, **không phải Spring AI builtin feature flag**. Nếu chưa viết mã điều kiện hóa evaluation job, giá trị này không tự làm gì.
- Actuator chỉ expose **health,info** trong cấu hình chung; endpoint metrics/prometheus nếu cần được mở riêng theo môi trường và phân quyền mạng.

### 5.2. application-dev.yml — tài nguyên phát triển

~~~yaml
spring:
  ai:
    openai:
      api-key: ${DEV_AI_API_KEY}
      project-id: ${DEV_AI_PROJECT_ID}
      chat:
        model: ${DEV_GENERATOR_MODEL}
  datasource:
    url: ${DEV_PGVECTOR_JDBC_URL}
    username: ${DEV_PGVECTOR_USERNAME}
    password: ${DEV_PGVECTOR_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0       # Chỉ dùng với lưu lượng lab thấp
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${DEV_OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}

app:
  isolation:
    environment: dev
    vector-resource-id: ${DEV_VECTOR_RESOURCE_ID}
    dataset-id: ${DEV_DATASET_ID:synthetic-qa-v1}
  evaluation:
    enabled: true
    mode: local
~~~

Ở đây **DEV_* là tên environment variable** được process thực sự cung cấp, không phải tên biến chuẩn của Spring AI. Riêng `spring.ai.openai.api-key`, `spring.datasource.*` và đường dẫn OTLP là property được framework xử lý.

**Các trường `app.isolation.*`, `app.evaluation.*` là property tùy biến.** Phải có code dùng chúng để chọn đúng index, dataset và điều kiện chạy job. Chỉ thêm những dòng YAML không tự tạo isolation.

Không dùng fallback giống `${DEV_AI_API_KEY:prod-key}`. Nếu thiếu key, hệ thống phải báo cấu hình chưa đủ. Endpoint `localhost:4318` chỉ là giá trị dev; nếu collector chưa chạy, không có trace được xuất ra.

### 5.3. application-test.yml — chạy test không gọi provider thật

~~~yaml
spring:
  ai:
    model:
      chat: none
      embedding: none

app:
  isolation:
    environment: test
    vector-resource-id: isolated-fixture
    dataset-id: qa-offline-fixture-v1
  evaluation:
    enabled: false
    mode: fixture
~~~

Đây là profile **test offline**. Cấu hình `spring.ai.model.chat: none` và `spring.ai.model.embedding: none` chặn auto-configuration của các provider model tương ứng theo tài liệu Spring AI; **nếu production beans bắt buộc phải inject ChatModel/ChatClient**, test vẫn cần thay bằng fake/mock/test configuration. Việc disable model không tự thay thế dependency injection.

Integration tests **thực sự gọi provider** nên chạy thành một nhóm riêng, dùng **credential test**, có quota/thời gian/chi phí được duyệt và không gộp với unit test lặp lại mọi commit.

### 5.4. application-staging.yml — dùng secret volume

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/ai/"
  ai:
    openai:
      project-id: ${STAGING_AI_PROJECT_ID}
      chat:
        model: ${STAGING_GENERATOR_MODEL}
  datasource:
    url: ${STAGING_PGVECTOR_JDBC_URL}
    username: ${STAGING_PGVECTOR_USERNAME}
    # spring.datasource.password lấy từ configtree

management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${STAGING_OTLP_TRACES_ENDPOINT}
  tracing:
    sampling:
      probability: 0.25

app:
  isolation:
    environment: staging
    vector-resource-id: ${STAGING_VECTOR_RESOURCE_ID}
    dataset-id: ${STAGING_EVAL_DATASET_ID}
  evaluation:
    enabled: true
    mode: scheduled
~~~

`configtree:/run/secrets/ai/` là **đường dẫn bắt buộc**: khi chạy với profile staging mà thư mục import không tồn tại, Spring Boot báo lỗi thay vì bỏ qua. Cần provision volume trước khi chạy. Không thêm tiền tố `optional:` cho secret bắt buộc mà bạn muốn **fail early**.

Giả sử mount các file:

~~~text
/run/secrets/ai/
  spring.ai.openai.api-key       # nội dung là key staging
  spring.datasource.password    # nội dung là password staging
~~~

Spring Boot đọc các file của **config tree** như thuộc tính theo tên file; tên có dấu chấm được hỗ trợ. Hai file nằm trong secret volume **không thuộc Git hoặc container image**. Bản thân Secret trong Kubernetes cũng cần RBAC, mã hóa at rest nếu được cấu hình, kiểm soát truy cập và phân quyền vận hành.

### 5.5. application-prod.yml — production tách biệt

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/ai/"
  ai:
    openai:
      project-id: ${PROD_AI_PROJECT_ID}
      chat:
        model: ${PROD_GENERATOR_MODEL}
  datasource:
    url: ${PROD_PGVECTOR_JDBC_URL}
    username: ${PROD_PGVECTOR_USERNAME}

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  tracing:
    sampling:
      probability: 0.05
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${PROD_OTLP_TRACES_ENDPOINT}

app:
  isolation:
    environment: prod
    vector-resource-id: ${PROD_VECTOR_RESOURCE_ID}
    dataset-id: disabled-for-runtime
  evaluation:
    enabled: false
    mode: disabled
~~~

Trong production, metrics/prometheus có thể được thu thập qua cơ chế riêng với quyền truy cập dành cho monitoring; ví dụ giữ exposure tối thiểu để tránh mở rộng bề mặt truy cập. **Sampling 0.05** là giá trị minh họa, cần điều chỉnh theo lưu lượng, mục tiêu điều tra sự cố và ngân sách lưu trữ. Cũng phải có cơ chế sampling phù hợp cho lỗi/latency cao nếu muốn quan sát các tình huống hiếm.

**Không** dùng `spring.profiles.active: prod` ở trong `application-prod.yml`; bên triển khai chọn profile qua `SPRING_PROFILES_ACTIVE` hoặc tham số khởi động. Property `app.evaluation.enabled: false` chỉ ngăn job nếu code thực sự kiểm tra cờ.

## 6. Kích hoạt profile đúng cách và kiểm soát precedence

Ví dụ với Spring Boot:

~~~bash
# Lệnh minh họa, cần cài đặt biến DEV_* bằng cơ chế riêng
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run

# Hoặc dùng tham số rõ ràng
java -jar ai-quality-lab.jar --spring.profiles.active=staging
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
# Secret và endpoint DEV_* phải được cấp qua môi trường của process
.\mvnw.cmd spring-boot:run
~~~

Với **một profile môi trường**, ưu tiên `dev`, `test`, `staging` hoặc `prod` và kiểm tra chỉ có **một** profile nhóm này được kích hoạt. Nếu ứng dụng cần profile kỹ thuật khác (ví dụ `cloud`, `observability`), không xem đó là môi trường chính thứ hai.

Các nguồn có độ ưu tiên cao có thể **ghi đè** cùng key từ profile file, ví dụ:

~~~text
SPRING_AI_OPENAI_API_KEY
SPRING_DATASOURCE_URL
SPRING_PROFILES_ACTIVE
SPRING_CONFIG_IMPORT
~~~

Đừng sử dụng biến không kiểm soát trong CI runner hoặc chart dùng chung làm mặc định production. Chốt **configuration policy** ở môi trường triển khai: ai được sửa profile, secret refs, config imports và resource endpoints.

### “File .env” có tự được Spring Boot đọc không?

**Không có cơ chế mặc định của Spring Boot tự tìm và load file `.env` tùy ý** chỉ vì file nằm cạnh source. Docker Compose, IDE run configuration hoặc shell helper có thể nạp biến từ file trước khi chạy JVM. Nếu dùng `.env` ở local:

- đưa file chứa giá trị thật vào ignore và quản lý quyền trên máy;
- chỉ commit `.env.example` với **tên biến/giá trị giả**, không chứa credentials;
- hiểu `.env` đang được **công cụ nào** nạp, tránh nhầm giữa Compose interpolation và process environment.

Khi đã dùng Kubernetes Secret volume hoặc secret manager ở staging/prod, nên **tránh lưu bản sao secret** vào file YAML của image hay release artifact.

## 7. Cấp secret bằng Kubernetes mà không nhúng vào image

Ví dụ phần **container/pod spec** của một deployment môi trường staging (đoạn rút gọn, cần ghép vào manifest Deployment có selector và metadata hợp lệ):

~~~yaml
spec:
  serviceAccountName: ai-generator-staging
  containers:
    - name: ai-generator
      image: registry.example/ai-quality-lab:1.0.0
      env:
        - name: SPRING_PROFILES_ACTIVE
          value: "staging"
        - name: STAGING_AI_PROJECT_ID
          valueFrom:
            configMapKeyRef:
              name: ai-staging-settings
              key: provider-project-id
        - name: STAGING_PGVECTOR_JDBC_URL
          valueFrom:
            configMapKeyRef:
              name: ai-staging-settings
              key: pgvector-jdbc-url
        - name: STAGING_PGVECTOR_USERNAME
          valueFrom:
            configMapKeyRef:
              name: ai-staging-settings
              key: pgvector-username
        - name: STAGING_GENERATOR_MODEL
          valueFrom:
            configMapKeyRef:
              name: ai-staging-settings
              key: generator-model
        - name: STAGING_OTLP_TRACES_ENDPOINT
          valueFrom:
            configMapKeyRef:
              name: ai-staging-settings
              key: traces-endpoint
        - name: STAGING_VECTOR_RESOURCE_ID
          value: "staging-rag-index"
        - name: STAGING_EVAL_DATASET_ID
          value: "synthetic-qa-v4"
      volumeMounts:
        - name: ai-secrets
          mountPath: /run/secrets/ai
          readOnly: true
  volumes:
    - name: ai-secrets
      secret:
        secretName: ai-staging-generator-credentials
        items:
          - key: openai-api-key
            path: spring.ai.openai.api-key
          - key: pgvector-password
            path: spring.datasource.password
~~~

Điều kiện để ví dụ chạy:

1. ConfigMap `ai-staging-settings` và Secret `ai-staging-generator-credentials` đã tồn tại **trong namespace của staging**.
2. Secret có **hai keys** `openai-api-key` và `pgvector-password`, được cấp bằng secret manager/operator hoặc quy trình quản trị phù hợp.
3. Identity `ai-generator-staging` chỉ được phép truy cập dịch vụ và tài nguyên cần dùng ở staging; không có grant lên secrets hoặc dữ liệu production.
4. Container image và startup command hợp lệ, database, provider và OTLP backend thực sự kết nối được.

**Không minh họa secret value hoặc lệnh `kubectl create secret --from-literal=...` với giá trị thật** trong tài liệu chia sẻ: giá trị có thể lọt vào shell history/process list/log pipeline. Cấp từ hệ thống quản lý bí mật có phân quyền và kiểm toán.

### Service account và security boundary

Kubernetes **namespace** tiện để quản lý, nhưng một namespace khác tên **không tự ngăn** truy cập qua network. Cần phối hợp **RBAC**, **NetworkPolicy/egress controls**, định danh workload, IAM trên secret manager, quyền trên database, TLS và quyền ở provider/telemetry.

Kubernetes Secret được lưu ở dạng biểu diễn Base64 trong một số manifest/API; điều này **không phải bảo mật nội dung**. Bảo vệ cả lưu trữ của cluster, audit logs, quyền `get/list/watch` secrets, backup và snapshot.

## 8. Mô hình sinh, judge và embedding: tách identity theo vai trò

Với evaluation, có **hai chiều phân tách**:

1. **Theo môi trường:** dev/staging/prod không chia sẻ identity hoặc tài nguyên nhạy cảm.
2. **Theo vai trò:** generator, evaluator/judge, embedding và tools có thể cần quyền và ngân sách khác nhau **ngay trong cùng một môi trường**.

Ví dụ nhóm có hai workload ở staging:

~~~text
Deployment: ai-generator-staging
  SPRING_PROFILES_ACTIVE=staging
  SecretRef=ai-staging-generator-credentials
  Rights=read staging corpus; call generator model; invoke sandbox tools

CronJob: ai-evaluator-staging
  SPRING_PROFILES_ACTIVE=staging
  SecretRef=ai-staging-judge-credentials
  Rights=read approved staging evaluation dataset; call judge model
  Deny=production vector DB; mutating production tools
~~~

Sử dụng **cùng artifact** là có thể nếu code được thiết kế theo role và bật đúng job/bean thông qua cấu hình. Tuy nhiên hai process riêng dễ tách identity, quyền và accounting hơn trường hợp generator/judge cùng chạy trong một process với hai keys.

Nếu cùng provider OpenAI nhưng cần key chat và embedding riêng, Spring AI hỗ trợ:

~~~yaml
spring:
  ai:
    openai:
      chat:
        api-key: ${STAGING_CHAT_API_KEY}
      embedding:
        api-key: ${STAGING_EMBEDDING_API_KEY}
~~~

Đoạn này dùng cho **trường hợp cần tách chat với embedding**. Không được hiểu rằng nó tách **generator chat** khỏi **judge chat**: cả hai vẫn thuộc cùng loại chat nếu dùng chung auto-configured model.

Trong production, phải tránh cấp cho evaluator các token tool có quyền gửi email thật, sửa đơn hàng hoặc ghi dữ liệu; những ca kiểm thử tool calling có tác động nên dùng **stub/sandbox**. Nếu cần đánh giá hành vi tool trong production, phải có chính sách cho phép, giới hạn tài nguyên, cơ chế idempotency và quan sát sự kiện đầy đủ.

## 9. Tách vector database, corpus và evaluation dataset

Một pipeline RAG có ít nhất hai loại tài nguyên dữ liệu: **corpus/index dùng để trả lời** và **dataset/ground truth dùng để đánh giá**. Cần ghi version của cả hai.

| Tài nguyên | Dev / test | Staging | Production |
|---|---|---|---|
| PostgreSQL/PGvector | Docker container/ephemeral DB | Cluster hoặc DB staging | Cluster hoặc DB prod |
| DB principal | `rag_dev`, `rag_test` | `rag_staging` | `rag_prod` |
| Index/table/vector namespace | `rag_dev_*` | `rag_staging_*` | `rag_prod_*` |
| Corpus | Docs giả lập, đã ẩn danh | Snapshot được duyệt | Corpus thật có phân quyền |
| Embedding model | Có thể nhỏ hơn để thử nhanh | Giống prod khi cần so sánh | Model đã chốt cho index |
| Ground-truth dataset | Fixtures nhỏ | Bộ regression theo revision | Bộ monitoring được phép |

Khi dùng Spring Boot `spring.datasource.url`, `username`, `password` xác định **connection tới database**; tên index/table/collection và chính sách truy xuất còn phụ thuộc adapter VectorStore đang dùng. Trường `app.isolation.vector-resource-id` chỉ là metadata/custom setting và phải được map vào cấu hình vector store hoặc truy vấn thật. Dùng một property đặt tên riêng **không tạo hiệu lực an ninh**.

### Ba mức cách ly

- **Tốt nhất với workload rủi ro cao:** khác database/cluster/account và khác network/credentials.
- **Có thể đủ cho lab ít rủi ro:** cùng server nhưng khác database/schema, user permissions và index riêng, có test chống truy cập chéo.
- **Chỉ dùng tên khác trong cùng schema với cùng quyền admin:** không nên xem là tách biệt đáng tin cậy.

Test không được chạy **schema initialization, re-index hay cleanup** với quyền có thể tác động lên database production. Dùng migration tool và xác minh target DB trước khi thực hiện các thao tác có thể thay đổi dữ liệu.

### Lưu đúng context để chấm fact checking

Một lần evaluation phải giữ được:

~~~yaml
case_id: "faq-042"
environment: "staging"
question: "Hạn nộp báo cáo tháng là ngày nào?"
retrieved_document_ids:
  - "policy-monthly-v3-chunk-07"
corpus_revision: "policy-v3"
index_revision: "staging-pgvector-v9"
generator_model: "generator-model-revision"
judge_model: "judge-model-revision"
rubric_revision: "fact-check-v2"
~~~

Ví dụ metadata này không chứa toàn văn prompt hay tài liệu. Nếu muốn lưu **retrieved context** để tái lập, cần kho có access controls, encryption và retention phù hợp; không gửi context nhạy cảm sang hệ thống tracing công khai.

**Judge phải kiểm tra trên đúng bằng chứng mà generator đã được cấp.** Không để evaluator tự truy xuất một môi trường/vector index khác rồi tuyên bố câu trả lời không grounded hoặc grounded dựa trên nguồn không khớp.

## 10. Cách ly observability, chi phí và token

Các thông số cần tách theo môi trường:

- **OTLP collector/backend/tenant** để traces không chảy lẫn dev/staging/prod.
- **Service identity và các nhãn bounded-cardinality**: `environment`, `service`, `role`, `model` (khi tập model hữu hạn), `pipeline_version` (có giới hạn version).
- **Sampling, retention, quyền xem log/trace**; môi trường production thường có mức thu thập khác lab.
- **Provider project/billing/quota** và **cost attribution** cho generator, evaluator và embedding.

Với Spring Boot 4.2, có thể cấu hình endpoint OTLP HTTP riêng:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTLP_TRACES_ENDPOINT}
~~~

`OTLP_TRACES_ENDPOINT` trong ví dụ là **URL đầy đủ của traces ingestion**, thường kết thúc bằng `/v1/traces` cho OTLP/HTTP. Có thể dùng cấu hình chung `management.opentelemetry.otlp.endpoint` (gốc collector): Spring Boot 4.2 tự thêm đường dẫn `/v1/traces` khi dùng fallback chung với HTTP, nhưng **không thêm lại path** nếu đã đặt endpoint trace-specific. Không trộn hai kiểu URL rồi gửi vào path `/v1/traces/v1/traces`.

Nếu collector yêu cầu bearer/API key, cấp token OTLP qua secret manager hoặc volume, không commit URL có `user:password@host`, không log authorization headers. Việc có exporter và cấu hình endpoint **không bảo đảm backend đang nhận dữ liệu**: kiểm tra service health, quyền truy cập, TLS, sampling và span thực tế.

### Metrics và trace của Spring AI

Spring AI có observability cho `ChatClient`, `ChatModel`, embedding, tool và VectorStore. Các tín hiệu đại diện:

| Tín hiệu | Ý nghĩa | Lưu ý |
|---|---|---|
| `spring.ai.chat.client` | Thời gian đi qua ChatClient/advisors | Chỉ có khi thực sự gọi client |
| `gen_ai.client.operation` | Lời gọi provider/model | Có thể biến đổi tên khi xuất Prometheus |
| `gen_ai.client.token.usage` | Input/output tokens | Phụ thuộc usage mà model/provider trả về |
| `spring.ai.tool` | Thực thi tool | Không có nếu pipeline không gọi tool |
| `db.vector.client.operation` | Thao tác vector | Không có nếu request không truy xuất vector |

Metric nên là **số liệu tổng hợp**. Không gắn API key, câu hỏi, nội dung tài liệu, user ID, order ID hoặc full request ID vào **metric labels**. Các thuộc tính chi tiết được phép xuất trên trace cũng phải được kiểm soát truy cập và thời gian lưu.

### Đo chi phí theo generator và judge

Đừng xem chi phí của job đánh giá là chi phí phục vụ một request người dùng. Ví dụ:

| Workload | Số model calls/mẫu | Dữ liệu cần đo | Nơi quy ngân sách |
|---|---:|---|---|
| Generator | Thường 1, có thể tăng do tool/retry | tokens, latency, lỗi, model ID | Project generator của môi trường |
| Relevance judge | Thường 1 | verdict, usage, latency | Project judge |
| Fact-check judge | Thường 1 | verdict, usage, latency | Project judge |
| Embedding/retrieval | Phụ thuộc workflow | embedding tokens, vector query time | Project/index tương ứng |

Tính chi phí cần **đơn giá theo model và thời điểm**, cùng thông tin cache/retries/loại tokens nếu provider trả về. BOM Spring AI không chứa bảng giá model.

Áp dụng quota và cảnh báo theo **môi trường + vai trò**, ví dụ staging evaluation job có giới hạn số mẫu, số tokens và số lần retry. Khi job sai vòng lặp, việc tách quota giảm rủi ro ảnh hưởng production.

## 11. Kiểm tra cấu hình để fail closed

**Fail closed** nghĩa là khi thiếu secret, sai profile hoặc sai tài nguyên, hệ thống **từ chối chạy phần có rủi ro** thay vì âm thầm dùng credential/endpoint khác.

### Những điều nên kiểm tra lúc khởi động

1. Chính xác một profile môi trường chính được chọn và role của workload được chỉ định.
2. Không có giá trị secret bắt buộc là rỗng, unresolved placeholder hoặc token giả.
3. Resource IDs/endpoint được cấp cho environment tương ứng; **policy IAM/network** thực sự ngăn quyền chéo.
4. Nếu chạy evaluation, dataset và result store thuộc môi trường được cho phép.
5. Những tool có tác động bị tắt hoặc đổi sang sandbox ngoài production.
6. Không bật full prompt/response logging trong production.
7. Quota và mức sampling/retention nằm trong chính sách của môi trường.

Ví dụ **guard logic** với property do ứng dụng định nghĩa:

~~~java
package com.example.qualitylab;

import java.util.Arrays;
import java.util.List;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentIsolationGuard {

    public EnvironmentIsolationGuard(Environment environment) {
        List<String> activeProfiles = Arrays.asList(environment.getActiveProfiles());
        List<String> valid = List.of("dev", "test", "staging", "prod");

        long count = activeProfiles.stream().filter(valid::contains).count();
        if (count != 1) {
            throw new IllegalStateException(
                "Phải kích hoạt đúng một profile: dev/test/staging/prod");
        }

        String selected = activeProfiles.stream().filter(valid::contains)
                .findFirst().orElseThrow();
        String declared = environment.getRequiredProperty("app.isolation.environment");
        if (!selected.equals(declared)) {
            throw new IllegalStateException(
                "Profile và app.isolation.environment không khớp");
        }
    }
}
~~~

Đây là **kiểm tra tính nhất quán ở tầng ứng dụng**, không chứng minh hostname hay database là của môi trường tương ứng. Chống truy cập chéo còn phải **kiểm thử denial bằng tài khoản thực**, network policy và quyền trên dữ liệu; không dùng so khớp chuỗi env để thay thế bảo mật hạ tầng.

### Test âm tính bắt buộc

| Tình huống thử | Kết quả mong đợi |
|---|---|
 Không có `SPRING_PROFILES_ACTIVE` | Startup/guard không cho vào luồng chạy bình thường |
 Bật cùng lúc `dev,prod` | Guard báo cấu hình không hợp lệ |
 Thiếu secret volume staging/prod | App không khởi động với configtree bắt buộc |
 Secret volume tồn tại nhưng key rỗng/sai | Startup validation hoặc health/connection check phải phát hiện; không âm thầm fallback prod |
 Staging dùng credential truy cập PGvector prod | IAM/network/DB từ chối kết nối; kiểm thử xác nhận |
 Test chạy khi chat model disabled | Các test offline dùng fake/mock, không gọi mạng |
 Evaluation worker cố thực hiện production tool write | Bị từ chối do không được cấp quyền |
 OTLP staging trỏ tenant prod | Policy/credential tách biệt từ chối, có báo động cấu hình |

Lưu ý: `spring.config.import: configtree:` chỉ bảo đảm **đường dẫn mount có tồn tại**. Nó không tự bảo đảm tất cả **file key** đều hợp lệ; phải có thêm validation hoặc test kết nối. Thiếu `OPENAI_API_KEY` chưa chắc gây startup failure nếu không có bean nào truy cập property đó cho tới lúc chạy; cần kiểm chứng hành vi cụ thể.

## 12. Quản lý và xoay vòng secret

Một vòng đời secret đủ dùng cho môi trường production gồm:

1. **Cấp:** identity có quyền tối thiểu tạo/cấp phiên bản secret vào đúng môi trường.
2. **Phân phối:** workload được cấp quyền đọc riêng, qua secret manager/CSI volume/mounted secret; tránh ghi lên image hoặc Git.
3. **Sử dụng:** process chỉ đọc secrets cần thiết; không truyền lại cho tools/judge hoặc trace exporter không liên quan.
4. **Theo dõi:** audit việc cấp/đổi/đọc, 401/403, rate-limit, chi phí và bất thường.
5. **Rotation:** tạo key mới, cấp cho workload, rollout/reload theo khả năng ứng dụng, xác nhận kết nối, thu hồi key cũ.
6. **Thu hồi:** khi rời nhóm/lộ khóa, vô hiệu hóa ngay các credentials bị ảnh hưởng, kiểm tra log/billing và thay tài nguyên liên quan nếu cần.

### Quy trình rotation gợi ý

~~~mermaid
flowchart LR
    A["Tạo phiên bản secret mới"] --> B["Cập nhật secret manager"]
    B --> C["Rollout/reload workload"]
    C --> D["Smoke test + metrics 401/403"]
    D --> E{"Tất cả healthy?"}
    E -->|Có| F["Thu hồi secret cũ"]
    E -->|Không| G["Rollback sang phiên bản được phép"]
    G --> C
~~~

**Chi tiết vận hành:** ứng dụng Spring Boot có thể đọc secret lúc startup và **không tự refresh bean/provider client** khi nội dung file mount đổi. Nếu chưa có cơ chế refresh đã được kiểm chứng, dùng rolling restart. Không thu hồi key cũ trước khi tất cả instances dùng key mới đã sẵn sàng, trừ khi đang ứng phó sự cố lộ khóa cần revoke khẩn cấp.

Nếu nghi ngờ key bị lộ trong Git, **xóa khỏi commit mới không đủ**: cần revoke/rotate, xử lý lịch sử repository và kiểm tra việc sử dụng bất thường.

## 13. Đánh giá RAG/tool calling trong sandbox

Tách tài nguyên theo môi trường còn quyết định **độ tin cậy của kết quả evaluation**:

- Relevance hoặc fact-checking có thể bị sai nếu judge truy cập **khác corpus/index** với generator.
- Tool calling test có thể “pass” trên mock nhưng thất bại do contract/rate-limit của tool staging/prod khác nhau; cần các test integration được phép.
- Một bộ dữ liệu gắn nhãn lấy từ production có thể chứa PII. Cần quyền sử dụng, thời gian lưu và cơ chế mask trước khi đưa sang staging.
- Traces từ evaluation chứa câu hỏi, context hoặc câu trả lời có thể vi phạm tách môi trường dù model key đã tách.

**Kịch bản kiểm thử:** câu hỏi “Đơn hàng ABC đã giao chưa?” trong staging phải gọi **order-status sandbox** với ID giả; kết quả được kiểm bằng deterministic assertions (tool name và arguments) và judge chấm câu trả lời. Không cấp cho evaluation service quyền sửa đơn hàng thật hay gửi thông báo khách hàng.

Ví dụ báo cáo:

~~~json
{
  "experiment_id": "rag-staging-20261127",
  "environment": "staging",
  "generator_version": "model-gen-v1",
  "judge_version": "model-judge-v1",
  "dataset_revision": "synthetic-orders-v3",
  "retrieval_index_revision": "staging-index-v9",
  "tool_fixture_revision": "sandbox-tool-v2",
  "metrics": {
    "answer_relevance_pass_rate": 0.91,
    "fact_check_pass_rate": 0.88,
    "tool_argument_success_rate": 0.96
  }
}
~~~

Các số trong JSON là **ví dụ minh họa**, không phải kết quả benchmark thực nghiệm. Thí nghiệm thực phải lưu tổng số mẫu, các lỗi đánh giá, confidence/độ ổn định và phương pháp tính; tỷ lệ pass không có ý nghĩa nếu số mẫu quá ít hoặc judge chưa hiệu chuẩn.

## 14. Runbook xử lý cấu hình nhầm môi trường

### Sự cố A — Staging kết nối nhầm production vector database

**Dấu hiệu:** database audit ghi nhận staging service principal, index bị cập nhật, retrieval quality thay đổi đột ngột sau một job test.

**Xử lý:**

1. Ngừng job liên quan và khóa credential/đường truy cập không đúng quyền.
2. Xác nhận **connection identity và database target** ở tầng hạ tầng; tránh in password/token vào log.
3. So sánh phiên bản index, document count, migration và audit trail trước/sau.
4. Phục hồi dữ liệu nếu có ghi đè, rồi bổ sung IAM/network rule và negative integration test.
5. Đánh dấu các kết quả evaluation liên quan **không hợp lệ** nếu corpus đã thay đổi.

### Sự cố B — Prod trace xuất sang tenant staging

**Dấu hiệu:** request ID production hiện ở dashboard staging, dữ liệu đánh giá hoặc prompt metadata xuất sai vị trí.

**Xử lý:** cô lập exporter, điều chỉnh OTLP endpoint/credential, kiểm tra quyền truy cập và retention/việc xóa dữ liệu theo chính sách; sau đó xác minh route mới với một trace test **không chứa dữ liệu thật**.

### Sự cố C — Judge dùng cùng credential và quota với generator

**Dấu hiệu:** evaluation batch làm production generator tăng 429, chi phí cùng billing project, người dùng thấy latency cao.

**Xử lý:** tách judge sang workload/project/credential riêng, đặt concurrency và token budget, hẹn giờ batch hợp lý, thêm metric theo `role` và environment để phát hiện tái diễn.

### Sự cố D — Test có fallback sang key production

**Dấu hiệu:** CI vẫn gọi model thật dù profile test đã bật.

**Xử lý:** tìm cấu hình fallback, custom bean/provider client và secret injection cấp toàn cục ở CI; bỏ fallback, disable model và dùng fake test, thu hồi credential nếu đã bị sử dụng không đúng chính sách.

## 15. Bài thực hành và tiêu chí hoàn thành

### Bài 1 — Thiết kế ma trận quyền

Tạo bảng cho **dev, test, staging, prod** gồm: provider project, generator key ref, judge key ref, vector DB/schema, dataset, tool endpoint, OTLP tenant và quota. Đánh dấu ranh giới **cần network/IAM enforcement**, không chỉ dựa vào tên tài nguyên.

**Đầu ra mong đợi:** không có workload non-production nào có quyền ghi production, mỗi môi trường có telemetry và cost attribution riêng.

### Bài 2 — Chạy local không dùng production secrets

1. Dùng **application-dev.yml** và cấp các biến `DEV_*` qua local secret store/IDE environment.
2. Kiểm tra `SPRING_PROFILES_ACTIVE=dev`, database dev và provider project dev.
3. Dùng synthetic dataset và tạo một câu hỏi mẫu; xác minh request, token usage và trace tại collector dev nếu đã bật.
4. Tắt/đổi một secret để kiểm tra cơ chế báo lỗi; tuyệt đối không đặt fallback sang production.

**Đầu ra mong đợi:** các thao tác không chạm tài nguyên production; secret không lộ trong logs và giá trị config được kiểm tra bằng metadata an toàn.

### Bài 3 — Chạy test offline và một job judge có ngân sách

1. Chạy profile **test** với chat/embedding auto-configuration tắt và fake model cho phần code cần inject model.
2. Khai báo một integration job **riêng** dùng judge key của test/staging.
3. Thiết lập trần số mẫu, token budget, concurrency, timeout và retry cho job.
4. Kiểm tra evaluation request dùng **đúng retrieved context** từ cùng một run.
5. Lưu manifest gồm environment, model, judge, dataset/index/prompt revision và telemetry tenant.

**Đầu ra mong đợi:** unit tests không gọi provider thật; integration job chỉ dùng resource cho phép và báo chi phí riêng.

### Bài 4 — Negative tests bảo vệ môi trường

Thực hiện thử trên môi trường được phép bằng identity test không có quyền production:

| Kiểm tra | Kết quả đạt |
|---|---|
 Start với hai environment profiles | App báo lỗi |
 Start staging không có mandatory configtree mount | App báo lỗi |
 Dùng staging identity tới prod vector DB | Truy cập bị từ chối |
 Dùng staging judge vào prod tool endpoint | Truy cập bị từ chối |
 Gửi trace staging tới prod collector tenant | Truy cập bị từ chối |
 Thay judge key trong staging | Prod generator không bị ảnh hưởng |

### Câu hỏi tự kiểm tra

1. Vì sao **spring.profiles.active=staging** không phải một cơ chế an ninh?
2. Khác nhau giữa secret value, secret version reference và non-secret provider project ID?
3. Vì sao hai `ChatClient` với hai model IDs chưa chắc có hai API keys?
4. **configtree** giải quyết vấn đề nào? Bản thân nó có kiểm tra key secret đủ và đúng quyền không?
5. Nếu job đánh giá dùng chung PGvector prod, rủi ro ảnh hưởng đến factuality và tính tái lập ra sao?
6. Vì sao nên tách OTLP tenant, sampling và retention theo môi trường?
7. Khi key bị lộ hoặc cần rotation, vì sao rollout/reload workload là một bước riêng?
8. Điều kiện nào cho phép chạy đánh giá trên bản sao dữ liệu thật ở staging?

**Gợi ý đối chiếu:** (1) profile là chọn cấu hình, quyền do IAM/network/database/provider kiểm soát; (2) secret value phải được bảo vệ, version ref có thể lưu để audit, project ID là resource selector; (3) có thể dùng chung một auto-configured ChatModel; (4) import secrets từ file mount, cần validation và phân quyền riêng; (5) có thể chạm dữ liệu thật, thay index và làm bẩn benchmark; (6) tránh lộ/nhầm trace, chi phí và mức lưu giữ; (7) client thường đọc secret khi khởi tạo; (8) có phê duyệt, giới hạn truy cập, masking, retention và nghĩa vụ dữ liệu phù hợp.

## 16. Checklist bàn giao

- [ ] Đã phân loại **secret, non-secret config, dữ liệu nhạy cảm và metadata**.
- [ ] Mỗi môi trường có identity và quyền truy cập riêng; non-prod không có quyền prod.
- [ ] Key/provider project, vector DB/index, tool endpoints, evaluation dataset và OTLP tenant được tách.
- [ ] Generator/judge có ngân sách và quyền độc lập khi nhu cầu yêu cầu; không nhầm model ID với API key.
- [ ] Không có API key/password trong Git, image, build logs, trace hoặc dataset artifact.
- [ ] Spring profiles chỉ chọn cấu hình; có **IAM/RBAC/network policy/database grants** thực thi ranh giới.
- [ ] Staging/prod dùng secret injection có quản lý; thiếu secret bắt buộc không fallback sang prod.
- [ ] CI unit tests dùng fake/mocks; integration tests có quota và credential test riêng.
- [ ] Prompt/completion logging bị tắt theo policy; metric labels không chứa PII hoặc raw content.
- [ ] Có startup validation, smoke/negative tests và kiểm chứng quyền truy cập chéo bị từ chối.
- [ ] Có quy trình secret rotation/revocation, audit và xử lý sự cố.
- [ ] Mỗi evaluation run lưu đủ model/prompt/index/dataset/rubric và resource version an toàn để tái lập.

## Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, environment variables, config import và `configtree:` từ mounted volumes.
2. [Spring Boot 4.2 — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile-specific files, `spring.profiles.active`, các hạn chế với profile-specific documents.
3. [Spring AI 2.1 — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): `spring.ai.openai.api-key`, project ID, các override chat, auto-configuration và connection details.
4. [Spring AI 2.1 — OpenAI Embeddings](https://docs.spring.io/spring-ai/reference/api/embeddings/openai-embeddings.html): `spring.ai.openai.embedding.api-key` và resource/model options cho embedding.
5. [Spring AI 2.1 — Observability](https://docs.spring.io/spring-ai/reference/observability/): metrics/traces, token usage và chính sách prompt/completion logging.
6. [Spring Boot 4.2 — Observability/OTLP](https://docs.spring.io/spring-boot/reference/actuator/observability.html): OTLP common endpoint, signal-specific endpoint, exporter settings.
7. [Spring Boot 4.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access và nguyên tắc không mở các endpoint nhạy cảm.
8. [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) và [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/): quyền và phân phối bí mật cho workloads.
9. [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): giới hạn network traffic giữa namespaces/workloads khi network plugin hỗ trợ.
10. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): tạo, lưu trữ, rotation, auditing và thu hồi bí mật.

> **Ghi nhớ:** Với Spring AI Evaluation & Observability, tách cấu hình môi trường chỉ là bước đầu. Phải **tách quyền thực sự, dữ liệu RAG, judge/generator credentials, tools, telemetry và ngân sách**; sau đó kiểm tra không có đường truy cập chéo và lưu baseline đúng để các thay đổi relevance, fact checking, latency hay chi phí có thể được quy về nguyên nhân tin cậy.
