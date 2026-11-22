# Thực hành gọi Vertex AI prediction từ Java

Một ứng dụng Java trên Cloud Run cần ước lượng **rủi ro giao dịch** trước khi quyết định có yêu cầu kiểm tra bổ sung hay không. Mô hình học máy đã được triển khai lên một **Vertex AI Endpoint**; ứng dụng chỉ gửi dữ liệu đặc trưng, nhận dự đoán rồi áp dụng quy tắc nghiệp vụ. Để làm đúng, Java phải biết **định dạng input/output của model**, dùng Application Default Credentials (ADC), gọi **đúng endpoint theo region**, xử lý lỗi và không ghi dữ liệu nhạy cảm vào log.

Bài thuộc chương **Vertex AI và học máy** trong học phần **CLOUD_PROVIDERS_GCP**: nối quy trình ML với project/IAM, VPC, Cloud Run/GKE, tự động hóa triển khai, giám sát độ tin cậy và chi phí. Nội dung thực hành **online prediction cho một custom-trained model đã deploy** qua Java client library; không mặc định API này tương đương với Gemini `generateContent`, batch prediction hoặc Vertex AI Vector Search.

Sau bài học, bạn có thể:

- Phân biệt **Model**, **Endpoint**, **DeployedModel**, `trafficSplit` và **PredictionService**.
- Kiểm tra deployment cùng input/output schema bằng Console/`gcloud` trước khi gửi dữ liệu.
- Tạo `PredictRequest` với `instances` kiểu Protobuf `Value` và gọi `PredictionServiceClient` từ Java 17+.
- Định cấu hình **regional API endpoint**, ADC và quyền `aiplatform.endpoints.predict` phù hợp.
- Phân tích `PredictResponse.predictions`, `deployedModelId`; bảo vệ Java service trước lỗi input, quota, timeout và output sai schema.
- Phân biệt online/batch prediction, public/private endpoints, autoscaling và chi phí máy triển khai.
- Kiểm thử với mô hình có contract xác định, đo P95 latency, xử lý model versioning/canary và giám sát drift.

> **Phạm vi:** các ID/project/model trong bài là ví dụ. Chỉ chạy dự đoán khi bạn có **Endpoint đã deploy model đúng định dạng**; lệnh predict không tự huấn luyện hay triển khai model. Tạo/deploy endpoint với tài nguyên CPU/GPU có thể phát sinh **chi phí liên tục**; không thao tác trên production nếu chưa được phép.

## 1. Từ model đến prediction response

~~~mermaid
flowchart LR
  A["Java API / Cloud Run"] --> B["ADC + IAM permission"]
  B --> C["Vertex AI regional PredictionService"]
  C --> E["Endpoint: traffic split"]
  E --> D1["Deployed model v1"]
  E --> D2["Deployed model v2"]
  D1 --> R["PredictResponse"]
  D2 --> R
  R --> F["Java validate score + business decision"]
~~~

| Đối tượng | Ví dụ | Ý nghĩa |
|---|---|---|
| **Model** | `projects/P/locations/L/models/M` | Artifact/metadata của một mô hình; chưa chắc đang phục vụ online |
| **Endpoint** | `projects/P/locations/L/endpoints/E` | Resource để ứng dụng gọi `predict` |
| **DeployedModel** | `deployedModelId` | Một phiên bản model đang phục vụ trên Endpoint với machine/replica config |
| **Traffic split** | 90% v1, 10% v2 | Chọn DeployedModel cho mỗi prediction request |
| **PredictionService** | `L-aiplatform.googleapis.com:443` | API service mà Java client kết nối qua gRPC/TLS |
| **PredictRequest.instances** | Mảng JSON/protobuf values | Dữ liệu từng record theo contract của serving model |
| **PredictResponse.predictions** | Mảng giá trị dự đoán | Cấu trúc **do model định nghĩa**, không phải luôn là số float |

**Endpoint ID khác Model ID.** Lệnh `gcloud ai models describe` kiểm tra artifact; lệnh `gcloud ai endpoints describe` mới cho biết Endpoint có model nào đang được deploy và traffic split. Một Endpoint có thể chứa nhiều DeployedModels có **interface tương thích**, nhưng model version mới có thể thay đổi schema nếu không quản lý hợp đồng đúng.

## 2. Contract mẫu: ba đặc trưng đầu vào

Để thống nhất các ví dụ, giả sử đội ML đã cung cấp mô hình phân loại rủi ro có **contract v1**:

| Vị trí | Feature | Kiểu/đơn vị | Ví dụ |
|---|---|---|---:|
| 0 | `amount_minor` | Số tiền theo minor unit, số nguyên không âm | 12500 |
| 1 | `account_age_days` | Số ngày tài khoản tồn tại | 365 |
| 2 | `failed_attempts_24h` | Số lần đăng nhập thất bại 24 giờ | 0 |

Đầu vào minh họa dạng **mảng số có thứ tự**; **chỉ dùng format này khi model đã được train/deploy để nhận một vector số theo chính thứ tự ấy**:

~~~json
{
  "instances": [
    [12500, 365, 0],
    [900000, 3, 7]
  ]
}
~~~

Một serving container khác có thể yêu cầu mỗi instance là **object** như `{"amount_minor":12500,"account_age_days":365,"failed_attempts_24h":0}`, hoặc tensor với tên trường riêng. Không có một “schema Java mặc định” cho mọi Vertex AI model. Xem **`predictSchemata.instanceSchemaUri`, `parametersSchemaUri` và `predictionSchemaUri`** nếu model khai báo chúng; với custom container, đối chiếu tài liệu và implementation của handler `/predict`.

Kết quả cũng là **hợp đồng**, chẳng hạn mô hình *có thể* trả:

~~~json
{
  "predictions": [
    {"risk_score": 0.08},
    {"risk_score": 0.91}
  ],
  "deployedModelId": "DEPLOYED_MODEL_ID"
}
~~~

Đây chỉ là **ví dụ output giả định**, không phải response được đảm bảo từ model thật. Một sklearn classifier có thể trả scalar/list các probabilities, AutoML tabular trả object chứa classes/scores, còn custom server có thể trả một cấu trúc khác. Java cần kiểm tra schema/output bounds trước khi diễn giải `0.91` là xác suất và ra quyết định.

## 3. Preflight: project, region, endpoint, IAM và network

Yêu cầu: project đã bật billing và Vertex AI API; **model đã upload và deploy vào Endpoint**; gcloud CLI; Java 17+; runtime principal có quyền prediction. Chọn một region hỗ trợ model/hạ tầng (ví dụ `us-central1` trong lab) và tuân thủ yêu cầu residency.

~~~bash
PROJECT_ID="my-vertex-risk-lab"
REGION="us-central1"
ENDPOINT_ID="1234567890123456789"   # thay bằng endpoint ID thật

gcloud config set project "$PROJECT_ID"
gcloud services enable aiplatform.googleapis.com --project="$PROJECT_ID"

# Xem endpoints, trạng thái deployment và traffic split.
gcloud ai endpoints list --project="$PROJECT_ID" --region="$REGION"
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,displayName,deployedModels,trafficSplit)"
~~~

**Chỉ tiếp tục nếu:** Endpoint tồn tại ở `$REGION`, `deployedModels` không rỗng, traffic split hợp lệ, deployment sẵn sàng và model/feature contract đã được xác nhận. Với shared public Endpoint, API host theo region và Endpoint resource name là hai thành phần **khác nhau**, đều phải đúng. Khi dùng **dedicated public/private Endpoint**, đường gọi URL/network có thể khác: không tự sử dụng shared `PredictionServiceClient` cho mọi loại Endpoint.

### Quyền IAM của các danh tính

| Principal | Chức năng | Quyền cần xem xét |
|---|---|---|
| **Java runtime SA** | Chỉ gọi prediction | `aiplatform.endpoints.predict` trên resource/project phù hợp (role ví dụ `roles/aiplatform.user` hoặc custom role hẹp) |
| **ML deployer** | Upload model, tạo Endpoint, deploy version | Endpoint/Model Admin permissions, `iam.serviceAccounts.actAs` nếu deploy dưới serving SA riêng |
| **Model serving container SA** | Đọc secrets/Cloud Storage trong handler khi cần | Quyền tài nguyên *mà container* truy cập, tách khỏi caller SA |
| **SRE** | Xem latency, errors, endpoint health | Monitoring/Logging/Vertex AI read roles phù hợp |

`roles/aiplatform.user` thường **rộng hơn một quyền predict**. Nếu mô hình/policy hỗ trợ IAM granular, cân nhắc custom role với `aiplatform.endpoints.predict` và chỉ quyền đọc metadata thực sự cần. **Không cấp `roles/aiplatform.admin` cho API Java** để sửa lỗi 403. Đừng gửi service account JSON key trong JAR, container image hay Git.

### Local ADC khác gcloud CLI credentials

~~~bash
# Chỉ trên máy phát triển đã được phép; ADC không phải gcloud user login.
gcloud auth application-default login

# Kiểm tra cấu hình project dùng để gọi, không in access token ra log.
gcloud config get-value project
~~~

Với Cloud Run/GKE, Java sẽ dùng ADC từ **runtime service account** (Cloud Run `--service-account`; GKE dùng Workload Identity Federation). Các quyền của người thao tác `gcloud ai endpoints describe` **không tự chuyển sang runtime service account**.

### Public vs private network

Shared public Endpoint thường được gọi qua `REGION-aiplatform.googleapis.com:443` với HTTPS/gRPC và IAM token; workload phải có outbound access/DNS/TLS tới Google APIs. **Private Endpoint** có thể yêu cầu VPC/PSC/peering/DNS/hostname và client/transport tương ứng, ngoài IAM. Có quyền predict không tự tạo route VPC; ngược lại, TCP/TLS kết nối được chưa chứng minh IAM/response hợp lệ.

## 4. Smoke test bằng gcloud trước khi viết Java

Để tách lỗi Java khỏi lỗi endpoint/model, trước hết kiểm tra một request bằng **đúng dữ liệu và endpoint** mà Java sẽ dùng. Trong một thư mục lab của người học, tạo file `predict-request.json`:

~~~json
{
  "instances": [
    [12500, 365, 0],
    [900000, 3, 7]
  ]
}
~~~

Từ terminal có danh tính được phép gọi prediction:

~~~bash
gcloud ai endpoints predict "$ENDPOINT_ID" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --json-request=predict-request.json
~~~

Đây là lệnh **Vertex AI** hiện hành, không dùng `gcloud ai-platform predict --model` của dịch vụ AI Platform Legacy. Yêu cầu có hai instances; kiểm tra response có `predictions` tương thích với **contract của model thực**. Mỗi deployed model/serving container có thể định nghĩa response khác; không tự kết luận “0.91 là rủi ro cao” nếu model trả **logits**, **class labels** hay **vector probabilities** theo thứ tự khác.

Nếu lệnh lỗi, phân loại trước:

| Biểu hiện | Nguyên nhân thường gặp |
|---|---|
| `NOT_FOUND` | Sai project, region, Endpoint ID, hoặc endpoint chưa tồn tại |
| `FAILED_PRECONDITION` | Endpoint/model chưa deploy hoặc trạng thái triển khai chưa sẵn sàng |
| `INVALID_ARGUMENT` | JSON thiếu `instances`, sai kiểu/shape, không đúng schema, request quá lớn |
| `PERMISSION_DENIED` | Principal hiện tại không có `aiplatform.endpoints.predict`, policy/perimeter |
| `RESOURCE_EXHAUSTED` | Quota, request concurrency, capacity endpoint |
| `UNAVAILABLE`/`DEADLINE_EXCEEDED` | Lỗi tạm thời, mạng/latency/model quá chậm |

**Cảnh báo giới hạn:** API `predict` có giới hạn request payload (tài liệu hiện hành khoảng **1,5 MB** với online predict), và số instances hợp lệ còn phụ thuộc model/container. `gcloud ai endpoints predict` đọc tối đa **100 instances từ file** theo CLI hiện hành. Đừng nhồi hàng triệu records vào một online request; dùng batch prediction hoặc chia nhỏ với giới hạn phù hợp.

### Nếu chưa có Endpoint

Team ML có thể tạo Endpoint và deploy **một model đã upload** bằng các lệnh sau, **chỉ trong project lab được phê duyệt ngân sách**:

~~~bash
MODEL_ID="MODEL_ID_DA_UPLOAD"

gcloud ai endpoints create \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --display-name="risk-score-lab"

# Copy ENDPOINT_ID mới từ kết quả create/list/describe.
# Chỉ deploy nếu model đủ điều kiện phục vụ trên machine type chọn.
gcloud ai endpoints deploy-model "$ENDPOINT_ID" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --model="$MODEL_ID" \
  --display-name="risk-v1" \
  --machine-type="n1-standard-2" \
  --min-replica-count=1 \
  --max-replica-count=2
~~~

Tạo một Endpoint **không tự tạo model**, và deploy model có thể mất thời gian. Machine type phải được Vertex AI/edition/model hỗ trợ; một số model đòi GPU hoặc serving container riêng. **Một replica tối thiểu có thể bị tính phí liên tục ngay cả khi không có request**. Scale-to-zero chỉ có ở cấu hình/tính năng đủ điều kiện, không nên mặc định mọi model deploy đều về 0 khi idle.

## 5. Tạo project Java với Maven

Ví dụ dùng **Java 17+** và thư viện `com.google.cloud:google-cloud-aiplatform`. Để có bản tái lập cho lab, `pom.xml` tối thiểu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>vertex-online-predict</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-aiplatform</artifactId>
      <version>3.100.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`3.100.0` là phiên bản thư viện tham khảo trong tài liệu API tại thời điểm soạn bài, **không phải yêu cầu cố định lâu dài**. Ở production dùng Google Cloud Libraries BOM hoặc dependency management được đội platform kiểm duyệt; cập nhật phiên bản và chạy kiểm thử trước deploy.

### Cấu trúc ví dụ

~~~text
vertex-online-predict/
├── pom.xml
└── src/main/java/example/
    └── PredictRisk.java
~~~

Không cần tự tìm token rồi gắn `Authorization` header: Java client sử dụng **ADC**, lấy token và tạo kênh gRPC/TLS. Với custom serving model trên shared public Endpoint, URI gRPC theo region là `REGION-aiplatform.googleapis.com:443`. Đừng đưa Project ID/region/endpoint ID của một môi trường vào code cố định khi cùng artifact chạy ở dev/staging/prod.

## 6. Java hoàn chỉnh: PredictRequest → PredictResponse

Ví dụ `PredictRisk.java` dưới đây **có thể biên dịch** với Maven project ở mục 5, và chỉ **gọi thành công** khi Endpoint tồn tại, IAM/network hợp lệ và serving model nhận **một instance là mảng ba con số**. Model cần trả **một prediction dạng object có trường `risk_score` trong khoảng [0,1]** để phương thức đọc điểm sử dụng được.

~~~java
package example;

import com.google.cloud.aiplatform.v1.EndpointName;
import com.google.cloud.aiplatform.v1.PredictRequest;
import com.google.cloud.aiplatform.v1.PredictResponse;
import com.google.cloud.aiplatform.v1.PredictionServiceClient;
import com.google.cloud.aiplatform.v1.PredictionServiceSettings;
import com.google.protobuf.ListValue;
import com.google.protobuf.Value;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class PredictRisk implements AutoCloseable {
    private final PredictionServiceClient client;
    private final String endpointResource;

    public PredictRisk(String project, String region, String endpointId)
            throws IOException {
        if (project.isBlank() || region.isBlank() || endpointId.isBlank()) {
            throw new IllegalArgumentException("Missing Vertex AI config");
        }
        PredictionServiceSettings settings = PredictionServiceSettings
            .newBuilder()
            .setEndpoint(region + "-aiplatform.googleapis.com:443")
            .build();
        this.client = PredictionServiceClient.create(settings);
        this.endpointResource = EndpointName
            .ofProjectLocationEndpointName(project, region, endpointId)
            .toString();
    }

    private static Value number(double n) {
        if (!Double.isFinite(n) || n < 0) {
            throw new IllegalArgumentException("Invalid feature number");
        }
        return Value.newBuilder().setNumberValue(n).build();
    }

    // Chính xác ba features theo CONTRACT V1 của model.
    private static Value instance(
            long amountMinor, long accountAgeDays, long failedAttempts) {
        ListValue vector = ListValue.newBuilder()
            .addValues(number(amountMinor))
            .addValues(number(accountAgeDays))
            .addValues(number(failedAttempts))
            .build();
        return Value.newBuilder().setListValue(vector).build();
    }

    private static double score(Value prediction) {
        // Không giả định tất cả models trả score object.
        if (prediction.getKindCase() != Value.KindCase.STRUCT_VALUE) {
            throw new IllegalStateException(
                "Unexpected prediction type: expected object");
        }
        Value field = prediction.getStructValue()
            .getFieldsOrDefault("risk_score", Value.getDefaultInstance());
        if (field.getKindCase() != Value.KindCase.NUMBER_VALUE) {
            throw new IllegalStateException(
                "Model output missing numeric risk_score");
        }
        double result = field.getNumberValue();
        if (!Double.isFinite(result) || result < 0 || result > 1) {
            throw new IllegalStateException("Risk score out of range");
        }
        return result;
    }

    public List<Double> predict(List<Value> instances) {
        if (instances.isEmpty() || instances.size() > 16) {
            throw new IllegalArgumentException("Expected 1..16 instances");
        }
        PredictRequest request = PredictRequest.newBuilder()
            .setEndpoint(endpointResource)
            .addAllInstances(instances)
            .build(); // Parameters chỉ gửi khi serving model yêu cầu.

        PredictResponse response = client.predict(request);
        if (response.getPredictionsCount() != instances.size()) {
            throw new IllegalStateException(
                "Prediction count did not match request");
        }

        // Logging chỉ model identity và count, KHÔNG log raw features.
        System.out.println("Deployed model: "
            + response.getDeployedModelId());
        List<Double> result = new ArrayList<>();
        for (Value item : response.getPredictionsList()) {
            result.add(score(item));
        }
        return List.copyOf(result);
    }

    @Override
    public void close() {
        client.close();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        String project = requiredEnv("VERTEX_PROJECT_ID");
        String region = requiredEnv("VERTEX_REGION");
        String endpointId = requiredEnv("VERTEX_ENDPOINT_ID");

        List<Value> inputs = List.of(
            instance(12500, 365, 0),
            instance(900000, 3, 7));

        try (PredictRisk predictor =
                 new PredictRisk(project, region, endpointId)) {
            List<Double> risks = predictor.predict(inputs);
            for (int i = 0; i < risks.size(); i++) {
                System.out.printf("item=%d risk=%.4f%n", i, risks.get(i));
            }
        }
    }
}
~~~

**Các quyết định cố ý trong code:**

1. `PredictionServiceClient` được **tạo một lần và tái sử dụng**; tạo client/gRPC channel cho mỗi HTTP request sẽ làm tăng latency, sockets và áp lực tài nguyên.
2. `setEndpoint(region + "-aiplatform.googleapis.com:443")` là **API host**; `setEndpoint(EndpointName...toString())` trong request là **đường resource**, không được tráo đổi.
3. `instances` là `List<Value>`, mỗi `Value` biểu diễn một JSON instance. `ListValue` giữ thứ tự các features; protobuf numeric type dùng `double` nên cần xác định precision/scale và giới hạn ở input model.
4. Không gửi `parameters` nếu model không khai báo; với model có params hợp lệ, dùng `Value` theo `parametersSchemaUri`.
5. Giới hạn `1..16` là **giới hạn an toàn do ứng dụng lab đặt ra**, không phải quota cố định của Vertex AI. Production cần chọn batch size theo payload limit, latency, memory và server contract.
6. Không có fallback “prediction lỗi thì mặc định an toàn” trong demo: caller phải quyết định fail-open/fail-closed theo chính sách nghiệp vụ, không tự sinh điểm rủi ro giả.

### Chạy trong môi trường phát triển

~~~bash
export VERTEX_PROJECT_ID="my-vertex-risk-lab"
export VERTEX_REGION="us-central1"
export VERTEX_ENDPOINT_ID="1234567890123456789"

# Chỉ chạy trên workstation có ADC hợp lệ.
gcloud auth application-default login
mvn -q compile exec:java \
  -Dexec.mainClass=example.PredictRisk
~~~

Với Windows PowerShell, dùng `$env:VERTEX_PROJECT_ID="..."` thay `export`. Kết quả thật phụ thuộc mô hình đang deploy: **không có điểm rủi ro cố định phải xuất hiện**. Nếu gcloud smoke test thành công nhưng Java báo `Model output missing numeric risk_score`, nhiều khả năng code parsing **không khớp schema output**, không phải cần cấp thêm IAM.

## 7. Từ CLI sang một Java HTTP service trên Cloud Run

Trong hệ thống thực, `PredictRisk` thường nằm sau một **Java Spring Boot/Quarkus/Jakarta REST API**, chứ không chạy `main()` một lần mỗi request. API nhận mã giao dịch đã được xác thực, đọc features từ nguồn được ủy quyền (Cloud SQL/Spanner/Feature Store) và gọi Vertex AI:

~~~mermaid
sequenceDiagram
  participant U as Ứng dụng/client
  participant J as Java Cloud Run API
  participant D as Nguồn features đã xác thực
  participant V as Vertex AI Endpoint
  U->>J: POST /risk-decisions {transactionId}
  J->>D: Tra giao dịch + các features được phép
  D-->>J: amount_minor, age_days, attempts
  J->>V: Predict(instances)
  V-->>J: predictions + deployedModelId
  J->>J: Validate score + business rules
  J-->>U: Decision/needsReview + modelVersion
~~~

Để tái sử dụng class ở mục 6, bổ sung một phương thức public nhỏ ngay trong `PredictRisk`:

~~~java
// Thêm VÀO class PredictRisk (không phải class riêng).
public double predictOne(
        long amountMinor, long ageDays, long failedAttempts) {
    return predict(List.of(
        instance(amountMinor, ageDays, failedAttempts))).get(0);
}
~~~

Trong ứng dụng web, khởi tạo `PredictRisk` khi service startup, **đóng client khi shutdown**. Ví dụ controller Spring Boot dưới đây **chỉ là lớp tích hợp**, yêu cầu dependencies Spring Boot/Web và cấu hình dependency injection ngoài `pom.xml` đơn giản ở mục 5:

~~~java
// Minh họa REST layer: cần @Bean singleton PredictRisk và Spring Web.
@RestController
@RequestMapping("/api")
public class RiskController {
    private final PredictRisk predictor;

    public RiskController(PredictRisk predictor) {
        this.predictor = predictor;
    }

    @PostMapping("/risk")
    public Map<String, Object> risk(@RequestBody RiskFeatures features) {
        // Production: authenticate caller, authorize transaction/tenant,
        // rồi lấy features từ nguồn tin cậy, không tin raw client fields.
        double score = predictor.predictOne(
            features.amountMinor(),
            features.accountAgeDays(),
            features.failedAttempts24h());
        return Map.of("needsReview", score >= 0.8);
    }
}

record RiskFeatures(long amountMinor,
                    long accountAgeDays,
                    long failedAttempts24h) {}
~~~

Ngưỡng `0.8` là **giá trị minh họa**, phải được đội ML/risk đánh giá bằng precision, recall, calibration, false-positive/false-negative cost và fairness. **Không tự từ chối giao dịch tài chính chỉ vì một model trả score cao**, và không công khai score nếu điều đó tạo điều kiện cho người xấu thăm dò hệ thống. Controller minh họa chưa triển khai xác thực, giới hạn tốc độ hay kiểm soát tenant — **không deploy trực tiếp lên production**.

### Cấp quyền cho Cloud Run runtime service account

~~~bash
MODEL_PROJECT="my-vertex-risk-lab"
APP_PROJECT="my-risk-api-lab"
REGION="us-central1"
RUN_SA="risk-api@$APP_PROJECT.iam.gserviceaccount.com"

# Chỉ gán khi SA đã tồn tại, owner cho phép và đã rà soát quyền.
gcloud projects add-iam-policy-binding "$MODEL_PROJECT" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/aiplatform.user"
~~~

Đây là role có sẵn giúp minh họa, **có thể rộng hơn nhu cầu prediction**. Đội IAM nên thay bằng custom role ít quyền hoặc binding theo resource nếu tổ chức hỗ trợ. Java Cloud Run trong `APP_PROJECT` vẫn cần mạng/egress phù hợp tới Vertex AI ở `MODEL_PROJECT`; khác project **không đồng nghĩa** đã tự có quyền.

Với image của **một web application hoàn chỉnh** đã build/push, ví dụ:

~~~bash
IMAGE="$REGION-docker.pkg.dev/$APP_PROJECT/apps/risk-api:v1"
ENDPOINT_ID="1234567890123456789"

gcloud run deploy risk-api \
  --project="$APP_PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUN_SA" \
  --set-env-vars="VERTEX_PROJECT_ID=$MODEL_PROJECT,VERTEX_REGION=$REGION,VERTEX_ENDPOINT_ID=$ENDPOINT_ID" \
  --no-allow-unauthenticated
~~~

**Lưu ý:** lệnh `gcloud run deploy` chỉ triển khai image đã có; nó **không biến** class Java CLI ở mục 6 thành một web server. Cần Spring Boot/Web (hoặc framework tương đương), server lắng nghe cổng `PORT` do Cloud Run cấp, health checks và các phép kiểm thử HTTP. Cloud Run endpoint không cho unauthenticated callers vẫn cần **authorization ở cấp giao dịch/tenant**; một caller có quyền `run.invoker` không tự được xem mọi giao dịch.

## 8. Xử lý lỗi có chủ đích: 4xx không giống 5xx

Java GAPIC gRPC thường phát sinh `com.google.api.gax.rpc.ApiException`. Dùng status code để quyết định **trả lỗi cho caller**, **retry giới hạn**, hay **chuyển manual review**; tránh quy về một HTTP 500 chung.

| gRPC/API status | Nhóm lỗi | Hướng xử lý |
|---|---|---|
| `INVALID_ARGUMENT` | Request thiếu/sai features, shape/schema/size | Trả 400 ở API; sửa payload/model contract, **không retry** |
| `NOT_FOUND` | Endpoint/model sai ID/region hoặc không tồn tại | Kiểm tra deploy/config, không retry vô hạn |
| `PERMISSION_DENIED`/`UNAUTHENTICATED` | ADC, role, org policy, VPC SC | Kiểm tra caller principal; không cấp Admin để chữa |
| `FAILED_PRECONDITION` | Endpoint chưa sẵn sàng, config không hợp lệ | Xem deployment/traffic split, readiness |
| `RESOURCE_EXHAUSTED` | Quota/rate limit/capacity | Throttle, backoff+jitter, quota/capacity |
| `UNAVAILABLE` | Lỗi mạng/server tạm thời | Retry giới hạn nếu còn deadline |
| `DEADLINE_EXCEEDED` | Client hoặc backend xử lý quá lâu | Đo end-to-end, xác minh kết quả/capacity; retry có giới hạn |
| `INTERNAL`/`UNKNOWN` | Lỗi nội bộ hoặc serving handler | Logs/metrics; chỉ retry nếu thật sự transient |

**Java phân loại lỗi** (bổ sung quanh lời gọi prediction trong tầng web/service):

~~~java
import com.google.api.gax.rpc.ApiException;
import com.google.api.gax.rpc.StatusCode;

try {
    double score = predictor.predictOne(12500, 365, 0);
    System.out.println(score);
} catch (ApiException ex) {
    StatusCode.Code code = ex.getStatusCode().getCode();
    boolean transientError = switch (code) {
        case RESOURCE_EXHAUSTED, UNAVAILABLE, DEADLINE_EXCEEDED -> true;
        default -> false;
    };
    // Hệ thống thật: chỉ retry khi có budget/deadline,
    // exponential backoff + jitter và maxAttempts, không log PII.
    System.err.println("Vertex prediction failed: " + code
        + ", mayRetry=" + transientError);
    throw ex;
}
~~~

Đây là **phân loại**, không phải retry loop. Production nên cấu hình deadline và retry budget ở **client settings/service layer**: ví dụ 2–3 attempts, backoff 200 ms → 1 s kèm jitter, tổng thời gian nhỏ hơn API/Cloud Run timeout. Kiểm tra retry policy mặc định của SDK theo phiên bản; **không cộng chồng retry của SDK, service mesh và Java HTTP client** khiến một request sinh nhiều lần inference ngoài dự kiến.

**Prediction thường là thao tác đọc**, nhưng **không có nghĩa tất cả serving handlers đều không có side effects**. Custom container có thể ghi DB hoặc gửi event; khi đó retry sau timeout có thể lặp tác dụng phụ. Lý tưởng tách **predict thuần** ra khỏi business commit: prediction cung cấp score, rồi ứng dụng giao dịch có idempotency key riêng và đảm bảo xử lý đúng một lần theo nghiệp vụ.

## 9. Online hay batch prediction? Không gọi từng record vô hạn

| Trường hợp | Cách phù hợp | Lý do |
|---|---|---|
| Java API cần score ngay trong request | **Online prediction** qua Endpoint | Tối ưu cho latency/traffic tương tác |
| Hàng triệu hàng trên BigQuery/GCS, báo cáo đêm | **Vertex AI batch prediction job** nếu model hỗ trợ | Tránh N request qua HTTP, xử lý theo batch files/tables |
| Luồng Pub/Sub liên tục và cần score | Dataflow/Cloud Run consumer → Online Endpoint hoặc kiến trúc streaming khác | Backpressure, bounded concurrency, dedup |
| Model generative như Gemini | API `generateContent`/SDK tương ứng | Không nhầm request schema `PredictRequest.instances` |
| Embedding/ranking/search | API/model chuyên biệt hoặc prediction schema của model đó | Vector, dimensions và limits khác classifier |

**Batch prediction** có tài nguyên/job lifecycle và input/output GCS/BigQuery riêng; **không cần giữ online Endpoint replicas** chỉ để tính 5 triệu records mỗi đêm nếu mô hình hỗ trợ batch trực tiếp. Cân nhắc batch predict nếu latency từng record không phải SLO. Nếu dùng serverless online cho workload thấp, kiểm tra chính xác quyền lợi scale-to-zero trước khi quyết định.

## 10. Model version, traffic split và contract test

Một Endpoint có thể deploy hai versions để **canary**. Nếu traffic split là 90% model v1 và 10% v2, một request tới Endpoint có thể được phục vụ bởi bất kỳ version nào theo cấu hình, nên response có `deployedModelId` để truy vết. Không gán một kết quả test cho model v2 chỉ vì request được gửi sau khi triển khai v2.

**Quy trình nâng cấp có kiểm soát:**

1. Đóng băng **feature contract v1**: thứ tự, kiểu, đơn vị, missing value, normalizer và output schema; phiên bản model mới phải tương thích khi dùng chung Endpoint.
2. Trước khi rollout, chạy **golden dataset** cả v1/v2 và so sánh output shape, latency, calibration, accuracy/fairness; nếu schema khác, dùng Endpoint/API version khác.
3. Deploy v2 với machine/quota/replicas đã được kiểm duyệt; cho một tỷ lệ traffic nhỏ. Không hardcode deployedModelId trong Java business logic.
4. Quan sát `deployedModelId`, P95/P99, error rate, feature distribution và business outcomes **theo từng version**.
5. Chỉ tăng traffic nếu dữ liệu kiểm chứng đạt SLO; khi sự cố, **chuyển traffic về v1** và có kế hoạch rollback schema/feature pipeline.

Kiểm tra Endpoint trước và sau canary:

~~~bash
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(deployedModels,trafficSplit)"
~~~

**Model v2 không nhất thiết trả kết quả giống v1.** Cái cần bất biến ở API boundary là **hợp đồng input/output, quyền, khả năng diễn giải và ngưỡng business policy**. Khi thay đổi model, có thể cần hiệu chỉnh threshold riêng theo version; dùng ngưỡng cố định mà không đánh giá calibration có thể tăng nhầm false positive.

## 11. Observability: latency, lỗi, chất lượng model và chi phí

| Lớp | Cần đo | Tại sao |
|---|---|---|
| Java API | End-to-end P50/P95/P99, timeout, 4xx/5xx | Kiểm tra SLO người dùng, không chỉ latency Vertex AI |
| Vertex AI Endpoint | Prediction request count, error count, inference latency, replica/CPU/GPU utilization | Tìm bottleneck serving/quota/autoscaling |
| Model/deployed version | `deployedModelId`, output shape, score distribution, drift/skew | Phát hiện version hỏng hoặc distribution shift |
| Dữ liệu đầu vào | Missing/invalid features, source freshness, schema version | Tránh inference trên thông tin thiếu hoặc sai đơn vị |
| Business outcomes | Precision/recall, tỷ lệ manual review, false positives sau khi có nhãn | Chất lượng model không bằng latency nhanh |
| Platform/FinOps | Deployed replica-hours, GPU/CPU, network egress, logs, monitoring | Tránh giữ endpoint đắt khi rất ít requests |
| Security | IAM policy changes, token/auth failures, suspicious traffic volume | Phát hiện gọi ngoài phạm vi |

**Cloud Monitoring và Cloud Logging:** có thể bật endpoint access/container logs theo mức được phép, tạo dashboards/alerts cho P95 latency và 5xx, đồng thời theo dõi số replicas cùng request rate. **Request/response logging** đôi khi ghi payload chứa đặc trưng nhạy cảm: đánh giá PII, consent, retention, access controls và ngân sách log trước khi bật.

**Model Monitoring:** các tính năng giám sát drift/skew và request logging phụ thuộc phiên bản Endpoint/model, vùng, loại model và cấu hình monitor. Nếu business có dữ liệu labeled chậm vài ngày, tạo pipeline đối soát prediction → outcome theo **pseudonymous transaction ID**, không ghi toàn bộ số tiền/người dùng vào log để lấy metric.

### Chi phí online prediction

~~~text
Tổng chi phí xấp xỉ
  = tài nguyên deployed model theo machine/replica-hours
  + accelerator/serving resources (nếu dùng)
  + prediction usage theo mô hình/kiểu dịch vụ được tính phí
  + network/egress, logging/monitoring, Cloud Run, feature reads
~~~

Với custom model ở Endpoint có `min-replica-count=1`, **máy tối thiểu vẫn chạy khi không có request** trừ khi cấu hình đủ điều kiện scale-to-zero. Tăng max replicas có thể cải thiện throughput lúc cao điểm nhưng tăng mức chi phí đỉnh, không chắc giảm P95 nếu model chậm do preprocessing. Xem biểu phí theo **region, model type, machine type, GPU, endpoint type** và lấy dữ liệu thực tế từ Cloud Billing.

**Ước lượng capacity minh họa:** 50 requests/s, 1 instance/request, 50 ms xử lý trung bình không hàm ý “chỉ cần một replica”; phải đo concurrency, queue, CPU/GPU memory, batching, model size, p95 tail và cold/warm performance. Không chọn replica count chỉ từ request average, không đặt retry vô hạn khi overload.

## 12. Kiểm thử theo từng lớp

| Ca test | Đầu vào / điều kiện | Kết quả cần xác nhận |
|---|---|---|
| **T1 — Golden request** | 2 valid numeric vectors | Hai predictions theo output schema, score nằm [0,1] |
| **T2 — Feature âm** | `amount_minor=-1`, age âm, attempts âm | Java validation từ chối **trước** RPC |
| **T3 — Sai số features** | 2 hoặc 4 phần tử thay vì 3 | Phát hiện bằng contract test/server validation, không làm ngơ |
| **T4 — Type mismatch** | string trong vector số | Serving model từ chối hoặc API phát hiện lỗi, không tự cast tùy tiện |
| **T5 — Sai output schema** | Model trả scalar hoặc list, không có `risk_score` | Ứng dụng thất bại rõ ràng, không lấy score mặc định 0 |
| **T6 — Sai region/endpoint** | Endpoint ID của project/vùng khác | `NOT_FOUND` hoặc lỗi cấu hình, không retry vô hạn |
| **T7 — IAM âm** | Caller SA không có quyền predict | `PERMISSION_DENIED`, không bật IAM rộng để bypass |
| **T8 — Quota và timeout** | Mock `RESOURCE_EXHAUSTED` hoặc `DEADLINE_EXCEEDED` | Retry giới hạn + circuit/bulkhead, latency budget |
| **T9 — Canary** | Endpoint có v1/v2 traffic split | Ghi nhận deployedModelId, tương thích schema |
| **T10 — Dữ liệu nhạy cảm** | Request có trường PII không thuộc contract | Chặn/loại PII, logs không chứa raw features/tokens |
| **T11 — Batch lớn** | 17 records | Bị chặn bởi giới hạn **do Java lab đặt**, không phát RPC |
| **T12 — Java/CLI parity** | Cùng endpoint, schema và features | Kết quả theo model contract; với deterministic model, sai khác trong tolerance phù hợp |

**Unit tests không cần Vertex AI thực:** bóc riêng phần chuyển features → `Value` và parsing `Value` → risk score để kiểm tra bằng protobuf giả:

~~~java
// Mock output cho parser; không cần endpoint hay ADC.
import com.google.protobuf.Struct;
import com.google.protobuf.Value;

Value fake = Value.newBuilder()
    .setStructValue(Struct.newBuilder()
        .putFields("risk_score",
            Value.newBuilder().setNumberValue(0.42).build())
        .build())
    .build();
// Assert: parser trả 0.42, và từ chối null/string/out-of-range.
~~~

Trong code mục 6, `score()` và `instance()` đang là `private`. Để unit-test trực tiếp, tách hai hàm thuần này sang một class `RiskContract` có visibility phù hợp. Không gọi endpoint thật trong toàn bộ unit tests; dành integration test cho staging.

### Những câu hỏi reliability cần trả lời

- Khi prediction lỗi, ứng dụng **chặn giao dịch, yêu cầu xét duyệt, hay dùng cơ chế rules-based có kiểm soát**? Chính sách phải được sản phẩm/risk xác nhận.
- Khi timeout, business workflow có đang thực hiện tác vụ ghi ngoài model không? Có **idempotency key** và trạng thái bền vững để tránh charge hai lần không?
- Khi v2 ra score khác v1, làm sao so đúng cohort/labels và quyết định rollback?
- Ai có quyền thay traffic split, read request logs, cập nhật model container và policy ngưỡng?
- Hệ thống giám sát drift/skew có phản ứng nếu feature distribution đổi đột ngột hay chỉ alert latency?

## 13. Runbook điều tra sự cố

~~~bash
PROJECT_ID="my-vertex-risk-lab"
REGION="us-central1"
ENDPOINT_ID="1234567890123456789"

# Chỉ đọc Endpoint/traffic/model deployment.
gcloud ai endpoints describe "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,deployedModels,trafficSplit)"

# Xác minh bằng CLI request contract đã lưu.
gcloud ai endpoints predict "$ENDPOINT_ID" \
  --project="$PROJECT_ID" --region="$REGION" \
  --json-request=predict-request.json
~~~

**Thứ tự chẩn đoán:** (1) Endpoint có deploy không → (2) region/API host và resource name đúng không → (3) Java runtime SA thật là ai → (4) IAM/perimeter/network → (5) instances contract → (6) handler/container/model health → (7) quota, machine/replica, timeout → (8) parse predictions và business policy.

| Nếu gặp | Không nên làm | Nên làm |
|---|---|---|
| `403` khi Cloud Run gọi Vertex AI | Gắn Owner/Admin toàn project | Kiểm tra runtime SA, `aiplatform.endpoints.predict` và policy |
| `INVALID_ARGUMENT` | Retry 10 lần | Đối chiếu JSON/Value shape/schema và type |
| Java lỗi parsing dù CLI predict OK | Thay machine type ngay | In schema metadata, test format output, không log PII |
| `429` vào giờ cao điểm | Tăng retries vô hạn | Throttle, autoscaling/quotas, backoff và queue |
| P95 cao ngay sau deploy model mới | Bỏ qua vì average thấp | Tách metrics theo deployedModelId, đo CPU/GPU/cold start |
| Chi phí tăng khi không có traffic | Xóa Endpoint đang phục vụ production | Xem min replicas/model deployments; dừng **lab** đúng owner |

## 14. Checklist đưa Java prediction vào production

- [ ] Model được upload và **deploy lên Endpoint**, trafficSplit sẵn sàng; project/region/Endpoint ID tách cấu hình.
- [ ] Contract v1 nêu thứ tự/kiểu/đơn vị features, xử lý missing values và output semantics; có golden dataset.
- [ ] `PredictRequest.instances` là list các `Value` hợp lệ, không nhầm output scalar/object/list.
- [ ] `PredictionServiceSettings` dùng regional API host chính xác cho loại Endpoint.
- [ ] Java client singleton/reuse, đóng khi shutdown, HTTP/gRPC deadline và max concurrency phù hợp.
- [ ] Dùng ADC từ runtime SA, role ít quyền; không có access token/JSON key trong source/log.
- [ ] Phân biệt online Endpoint, batch prediction và API `generateContent` cho generative models.
- [ ] Mọi lỗi `INVALID_ARGUMENT/NOT_FOUND/403` không bị retry mù; `429/503/timeout` có retry budget.
- [ ] Không ghi raw customer features/PII vào logs; cấu hình request/response logging được privacy-review.
- [ ] Controller HTTP có authentication, authorization tenant, rate limit và validate dữ liệu nguồn.
- [ ] Có SLO P95/P99, error/quota metrics, model version trace, drift/skew/business outcome evaluation.
- [ ] Canary v2 có traffic split/rollback và kiểm tra input-output contract tương thích.
- [ ] Billing budgets và owner theo dõi deployed replica-hours, GPU và request volume.
- [ ] Cleanup lab khi không sử dụng; **undeploy model trước khi xóa Endpoint** sau khi xác nhận không còn traffic.

## 15. Bài tập vận dụng

**Bài 1 — Endpoint contract.** Phân biệt `Model`, `Endpoint`, `DeployedModel` và API host. Vì sao thay `Endpoint ID` bằng `Model ID` trong `PredictRequest.endpoint` sẽ lỗi?

**Bài 2 — Java Value.** Chuyển JSON instance `[12500,365,0]` thành `Value` chứa `ListValue` như mẫu. Viết phiên bản dùng `Struct` khi model yêu cầu object có ba tên trường.

**Bài 3 — IAM.** Java Cloud Run project A gọi Endpoint project B. Chỉ ra runtime SA, nơi cấp `aiplatform.endpoints.predict`, lý do không dùng Admin và khác biệt giữa deployer/model container SA.

**Bài 4 — Gcloud parity.** Với Endpoint thực ở lab, chạy `gcloud ai endpoints predict --json-request`, sau đó Java cùng input. So sánh `predictions`, `deployedModelId`, model version và nguyên nhân có thể khác kết quả.

**Bài 5 — Parsing.** Giả sử prediction thật là list `[0.08,0.92]` hoặc object `{"classes":["safe","risk"],"scores":[0.08,0.92]}`. Sửa parser có kiểm tra classes thứ tự và bounds; giải thích vì sao parser hiện tại phải báo lỗi.

**Bài 6 — Retry.** Một phút có 1000 requests, Vertex AI trả 429 với 20% requests. Đề xuất retry budget, max concurrency, rate limit và circuit breaker để tránh 1000 requests sinh thành bão requests mới.

**Bài 7 — Model canary.** Endpoint v1 có P95 120ms, v2 có P95 350ms và ít false negatives hơn. Đề xuất chỉ số và quy trình ra quyết định canary/rollback, không chỉ so average accuracy.

**Bài 8 — PII.** Model risk cần account age và failed attempts; developer muốn gửi thêm email/địa chỉ để “có thể giúp model”. Viết chính sách feature minimization, logging/retention, quyền và đánh giá fairness trước khi thay contract.

**Bài 9 — Chọn batch.** Có 8 triệu records cần tính điểm mỗi đêm, không cần real-time. So sánh chi phí, throughput và cách thiết kế Vertex batch prediction job với việc gọi 8 triệu online requests từ Java.

**Bài 10 — Runbook.** Cloud Run chạy tốt local nhưng báo `PERMISSION_DENIED`; một model v2 deploy xong báo `Model output missing numeric risk_score`. Nêu từng bước chẩn đoán riêng cho hai lỗi.

## Tài liệu tham khảo chính thức

- [Vertex AI: online predictions for custom-trained models](https://cloud.google.com/vertex-ai/docs/predictions/get-online-predictions) — instances, Endpoint và response contract.
- [Java Predict custom-trained model sample](https://cloud.google.com/vertex-ai/docs/samples/aiplatform-predict-custom-trained-model-sample) — `PredictionServiceClient`, `PredictRequest`.
- [PredictionServiceClient Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.PredictionServiceClient) — các phương thức predict.
- [PredictionServiceSettings Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.PredictionServiceSettings) — regional host, credentials và retry.
- [EndpointName Java reference](https://cloud.google.com/java/docs/reference/google-cloud-aiplatform/latest/com.google.cloud.aiplatform.v1.EndpointName) — resource name theo project/region.
- [gcloud ai endpoints predict](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/predict) — smoke test JSON.
- [gcloud ai endpoints deploy-model](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model) — model serving, replicas.
- [Endpoint types](https://cloud.google.com/vertex-ai/docs/predictions/choose-endpoint-type) — shared/dedicated public/private endpoints.
- [Vertex AI IAM permissions](https://cloud.google.com/iam/docs/roles-permissions/aiplatform) — `aiplatform.endpoints.predict`.
- [Vertex AI batch prediction](https://cloud.google.com/vertex-ai/docs/predictions/get-batch-predictions) — khi không cần online latency.
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity) — runtime SA và ADC.
- [Google Cloud ADC](https://cloud.google.com/docs/authentication/application-default-credentials) — local và workload authentication.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — serving resources, prediction và regional costs.
