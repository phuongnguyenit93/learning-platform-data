# Thực hành bảo vệ và công bố API Java trên GCP

Một API Java cho đối tác truy vấn trạng thái đơn hàng đang chạy trên Cloud Run. Gửi trực tiếp URL của backend cho đối tác khiến đội phát triển khó quản lý khóa, giới hạn lưu lượng, theo dõi mức sử dụng và thay backend mà không ảnh hưởng client. **Google Cloud API Gateway** có thể làm cửa ngõ công bố các endpoint có khai báo OpenAPI; khi quy mô đối tác, API products và chính sách nâng cao lớn hơn, **Apigee** là lựa chọn API management chuyên sâu.

Bài thuộc chương **API Gateway và Apigee** của học phần **CLOUD_PROVIDERS_GCP**. Mục tiêu là thực hành một luồng an toàn: **client → API Gateway → Cloud Run Java backend → Google Cloud service**, kết hợp project, IAM, VPC, CI/CD, logging, độ tin cậy và chi phí. Ví dụ được giữ gọn để có thể triển khai trong project lab, rồi mở rộng các kiểm soát production một cách có cơ sở.

Sau bài này, bạn có thể:

- Phân biệt **caller authentication** (API key/JWT), **gateway-to-backend authentication** (IAM service account) và **authorization nghiệp vụ** trong Java.
- Viết một Java HTTP API tối thiểu, container hóa và triển khai thành **private Cloud Run service**.
- Tạo OpenAPI 2.0 với `x-google-backend`, định tuyến và yêu cầu API key.
- Tạo API config và gateway bằng `gcloud`, kích hoạt managed service, thử request hợp lệ/không hợp lệ.
- Bổ sung JWT validation, quota, logging, hạn chế CORS và xử lý secrets.
- Biết khi nào nên dùng **Apigee API proxy, API product, VerifyAPIKey, Quota, SpikeArrest** thay API Gateway.
- Thực hành runbook sự cố `401/403/404/429/5xx`, rollback và dọn tài nguyên đúng cách.

> **Phạm vi lab:** tất cả project ID, service account, URL, API key đều là placeholder. Các lệnh tạo Cloud Run/API Gateway/Artifact Registry phát sinh phí; chỉ chạy trong project được phép và không công bố dữ liệu khách hàng thật. Bài **không thực thi lệnh trên tài khoản Google Cloud**.

## 1. Kiến trúc và ranh giới trách nhiệm

~~~mermaid
flowchart LR
    C["Client đối tác"] -->|"HTTPS + API key / JWT"| G["API Gateway"]
    G -->|"OIDC ID token từ gateway SA"| R["Cloud Run private Java API"]
    R -->|"ADC + runtime SA"| D["Cloud SQL / Cloud Storage / Pub/Sub"]
    I["IAM: Invoker + data roles"] --> G
    I --> R
    M["Logging / Monitoring / Billing"] --> G
    M --> R
~~~

| Lớp | Danh tính/kiểm soát | Ai chịu trách nhiệm? |
|---|---|---|
| **Client → Gateway** | API key xác định client project; JWT xác thực người gọi khi cấu hình | API provider quản lý OpenAPI, issuer, key restrictions |
| **Gateway → Cloud Run** | API config sử dụng **backend-auth service account** lấy ID token; Cloud Run xác thực IAM Invoker | Platform/IAM team |
| **Java → dữ liệu** | **Cloud Run runtime service account** dùng ADC gọi API hoặc DB | Developer/data owner |
| **Java authorization** | Đúng user/tenant, scope, order ownership, input validation | Ứng dụng Java |
| **Quản trị API** | OpenAPI, quotas, analytics, developer onboarding | API platform team |

**Quan trọng:** API key **không phải** bằng chứng người dùng cuối là ai; một key bị lộ có thể bị sao chép. JWT được Gateway xác thực chỉ giải quyết tính hợp lệ của token theo issuer/audience; Java vẫn phải quyết định **người đó có quyền xem đơn hàng nào**. Backend IAM bảo vệ việc **ai được gọi Cloud Run**, không thay authorization của nghiệp vụ.

### Chọn API Gateway hay Apigee?

| Tiêu chí | **API Gateway** | **Apigee** |
|---|---|---|
| Mục đích | Công bố API đơn giản/nhẹ bằng OpenAPI/gRPC, routing, API keys/JWT, quotas | Vòng đời **API products**, consumer apps, policies, analytics và quản trị đối tác |
| Đơn vị định nghĩa | API → API config → Gateway | API proxy → environment → API product → developer app |
| Định tuyến | `x-google-backend` trên OpenAPI | ProxyEndpoint/TargetEndpoint và flows |
| Traffic control | Quotas trong API config/Service Control và backend limits | SpikeArrest, Quota, chính sách per app/product |
| Mở rộng chính sách | Các extension hỗ trợ trong OpenAPI | Policies xác thực, transform, traffic, threat protection, caching theo license |
| Độ phức tạp | Ít vận hành hơn cho API phổ thông | Nhiều cấu hình/quyền/chi phí hơn |

Một API Java đơn giản cho vài ứng dụng nội bộ/đối tác thường bắt đầu bằng **API Gateway**. Nếu tổ chức bán API theo gói Bronze/Silver/Gold, cần portal developer, điều khoản tiêu thụ và policy chain phức tạp, cân nhắc **Apigee**. Không nên mặc định “Apigee bảo mật hơn trong mọi trường hợp”: hiệu quả phụ thuộc policy, IAM, mạng và quy trình vận hành.

## 2. Lab: một Java HTTP API đơn giản

Lab dùng **JDK 21** để tránh phụ thuộc framework. API trả JSON không chứa dữ liệu nhạy cảm tại `GET /v1/hello` và có endpoint kiểm tra sức khỏe `GET /healthz`. Với ứng dụng Spring Boot thật, bạn có thể giữ nguyên mô hình gateway, thay container backend.

**`App.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class App {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(
            new InetSocketAddress("0.0.0.0", port), 0);
        ExecutorService executor = Executors.newFixedThreadPool(8);
        server.setExecutor(executor);

        server.createContext("/v1/hello", ex -> {
            if (!"GET".equals(ex.getRequestMethod())) {
                send(ex, 405, "{\"error\":\"method_not_allowed\"}");
                return;
            }
            send(ex, 200, "{\"message\":\"hello from Java API\"}");
        });
        server.createContext("/healthz", ex ->
            send(ex, 200, "{\"status\":\"ok\"}"));

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(1);
            executor.shutdown();
        }));
        server.start();
        System.out.println("Listening on port " + port);
    }

    private static void send(HttpExchange ex, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
            "Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (var output = ex.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

Đây là handler tối giản cho lab, chưa có persistence, auth theo tenant, request validation hoặc tracing. Java `HttpServer` có prefix matching: các route nhạy cảm trong ứng dụng thật phải được định tuyến và kiểm soát riêng. **Không xem OpenAPI là lớp authorization duy nhất**, nhất là khi backend còn những đường dẫn khác.

**`Dockerfile`**

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY App.java .
RUN javac --add-modules jdk.httpserver -d /app App.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app /app
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "-cp", "/app", "App"]
~~~

Kiểm thử trước deploy:

~~~bash
docker build --platform linux/amd64 -t java-api-gateway:lab .
docker run --rm -e PORT=9090 -p 9090:9090 java-api-gateway:lab

# Terminal khác:
curl -i http://localhost:9090/v1/hello
curl -i http://localhost:9090/healthz
~~~

Kỳ vọng `200` và JSON hợp lệ. Bài lab chỉ dùng `GET`, nên chưa cần database. Khi nâng cấp thành API đơn hàng, client Java có thể dùng ADC truy cập Cloud SQL/Firestore/Storage qua runtime service account riêng; **đừng đưa JSON private key vào Docker image**.

## 3. Triển khai Cloud Run backend ở chế độ yêu cầu IAM

Chuẩn bị một Google Cloud project có billing và quyền deploy; chọn region có API Gateway/Cloud Run hỗ trợ. Ví dụ Bash/Cloud Shell:

~~~bash
PROJECT_ID="my-api-lab-project"
REGION="asia-southeast1"
REPO="api-images"
SERVICE="java-orders-api"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/java-api:v1"
RUN_SA="java-api-runtime@$PROJECT_ID.iam.gserviceaccount.com"
GW_SA="api-gateway-backend@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com \
  apigateway.googleapis.com servicemanagement.googleapis.com \
  servicecontrol.googleapis.com

# Chỉ tạo repository và service accounts nếu chưa có.
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION"
gcloud iam service-accounts create java-api-runtime \
  --display-name="Cloud Run Java API runtime"
gcloud iam service-accounts create api-gateway-backend \
  --display-name="API Gateway backend invocation"

gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  --ingress=all \
  --no-allow-unauthenticated \
  --port=8080 \
  --timeout=30s \
  --max-instances=5

RUN_URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" --format='value(status.url)')"
echo "$RUN_URL"
~~~

**Vì sao `--ingress=all` nhưng vẫn gọi là private?** URL Cloud Run có thể tiếp cận qua Internet về mặt mạng, nhưng **IAM yêu cầu ID token hợp lệ và quyền Invoker**. `--ingress=internal` thường không phù hợp để API Gateway công khai gọi trực tiếp. Đây là bảo vệ bằng **authentication/IAM**, không phải tuyên bố backend chỉ có private IP. Với hệ thống có yêu cầu tuyệt đối về đường mạng, cần thiết kế riêng (load balancer/IAP/Apigee/network perimeter) theo sản phẩm hỗ trợ.

### Giao quyền gọi backend đúng service account

~~~bash
gcloud run services add-iam-policy-binding "$SERVICE" \
  --region="$REGION" \
  --member="serviceAccount:$GW_SA" \
  --role="roles/run.invoker"

# Kiểm tra Cloud Run chưa cấp Invoker cho allUsers.
gcloud run services get-iam-policy "$SERVICE" --region="$REGION"
~~~

**Không cấp `roles/run.admin` hoặc `roles/editor` cho Gateway**. Nó chỉ cần quyền `run.routes.invoke` trên service. Deployer tạo API config cần được `iam.serviceAccounts.actAs` đối với `GW_SA` (thường qua `roles/iam.serviceAccountUser` cấp trên SA) và quyền quản trị API Gateway phù hợp; **không trao quyền thay service account cho mọi developer**.

Test trước khi tạo Gateway:

~~~bash
# Không có ID token/Invoker phải bị từ chối.
curl -i "$RUN_URL/v1/hello"

# Nếu tài khoản kiểm thử có run.invoker:
curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$RUN_URL/v1/hello"
~~~

Nếu người kiểm thử chưa có Invoker, lệnh thứ hai cũng `403`; đó là **kết quả IAM đúng**, không phải code Java lỗi. Tránh “sửa” bằng `--allow-unauthenticated`.

## 4. Định nghĩa OpenAPI và chính sách API key

API Gateway cần một **API definition** khai báo đường dẫn được phép gọi, backend URL và kiểu bảo vệ client. Ví dụ dùng **OpenAPI 2.0** vì cú pháp ngắn, được API Gateway hỗ trợ và dễ liên hệ trực tiếp với `x-google-backend`. API Gateway cũng hỗ trợ OpenAPI 3.x, nhưng các extension và `securitySchemes` khác cú pháp.

Tạo file lab tên **`openapi.yaml`** và thay `CLOUD_RUN_URL` bằng giá trị thật `RUN_URL` sau khi deploy:

~~~yaml
swagger: "2.0"
info:
  title: java-orders-lab-api
  version: "1.0.0"
  description: Java Cloud Run API protected by API Gateway
schemes:
  - https
produces:
  - application/json

# Không chuyển tiếp các route không khai báo trong OpenAPI.
x-google-allow: configured
x-google-backend:
  address: https://YOUR-CLOUD-RUN-SERVICE-URL.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
  deadline: 20.0

securityDefinitions:
  api_key:
    type: apiKey
    name: x-api-key
    in: header

# Mọi operation trong mẫu cần API key.
security:
  - api_key: []

paths:
  /v1/hello:
    get:
      summary: Say hello from Java
      operationId: getHello
      responses:
        "200":
          description: Successful response
          schema:
            type: object
            properties:
              message:
                type: string
        "405":
          description: Method not allowed
~~~

**Giải thích những field quyết định:**

- `x-google-backend.address` là **HTTPS URL gốc** của Cloud Run service (không phải gateway URL). Nếu gắn sai URL, gateway có thể trả lỗi backend.
- `path_translation: APPEND_PATH_TO_ADDRESS` chuyển `/v1/hello` qua Cloud Run với **giữ path**, đúng với Java handler. Với backend đặt ở **operation level**, mặc định có thể là `CONSTANT_ADDRESS`, làm path thành query parameters; vì vậy nên khai báo rõ.
- `deadline: 20.0` giới hạn tối đa 20 giây để gateway chờ backend cho ví dụ; nên nhỏ hơn giới hạn Cloud Run `--timeout=30s`. Mặc định API Gateway deadline là 15 giây nếu không chỉ định. Các giới hạn tùy chế độ gateway/streaming; kiểm tra hiện hành trước khi đặt dài.
- `x-google-allow: configured` chỉ cho những methods/paths đã khai báo; tránh đặt `all` vì route chưa khai báo có thể đi qua **không áp cùng điều kiện auth**.
- `securityDefinitions.api_key` yêu cầu key ở header `x-api-key`. **API key xác định project/consumer để kiểm soát usage**, không chứng thực danh tính người dùng cuối.
- `security` global áp cho mọi operation; nếu thêm `security` riêng ở operation, cấu hình operation **thay thế** global security. Phải review để không vô tình mở endpoint có dữ liệu nhạy cảm.

Khi sửa `openapi.yaml` theo môi trường, **đừng nối thủ công thêm path** vào `address` nếu backend đã có route `/v1/hello`, vì `APPEND_PATH_TO_ADDRESS` sẽ tiếp tục gắn request path. Kiểm tra bằng hai lệnh `curl` cuối lab.

## 5. Tạo API config, kích hoạt managed service và gateway

Từ thư mục lab có file `openapi.yaml` đã được thay URL backend:

~~~bash
API_ID="java-orders-lab"
CONFIG_ID="java-orders-v1"
GATEWAY_ID="java-orders-gateway"

gcloud api-gateway apis create "$API_ID" --project="$PROJECT_ID"

gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec="openapi.yaml" \
  --backend-auth-service-account="$GW_SA" \
  --project="$PROJECT_ID"

gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"
~~~

Ở bước tạo API config, Google Cloud có thể cần thời gian để validate/deploy cấu hình; không chạy lại lệnh create với cùng ID trong lúc operation đang xử lý. API config được xem là **immutable về routing/auth**: khi sửa OpenAPI phải tạo **config ID mới** và update gateway, không overwrite config cũ.

### Bật managed service tương ứng cho API key

API Gateway sử dụng Service Management/Service Control để xác minh API keys và quotas. Sau khi tạo API, lấy **managed service name** từ API description rồi enable:

~~~bash
MANAGED_SERVICE="$(gcloud api-gateway apis describe "$API_ID" \
  --project="$PROJECT_ID" \
  --format="value(managedService)")"
echo "$MANAGED_SERVICE"

# Đây là managed service riêng của API, không phải apigateway.googleapis.com.
gcloud services enable "$MANAGED_SERVICE" \
  --project="$PROJECT_ID"
~~~

Không tự đoán managed service name từ API ID; dùng đúng giá trị `managedService` do Google Cloud trả về. Nếu chưa nhìn thấy service trong APIs & Services, có thể cần chờ propagation rồi kiểm tra lại.

### Tạo gateway ở một region

~~~bash
gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID"

GW_HOST="$(gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(defaultHostname)')"
echo "https://$GW_HOST"
~~~

Chờ Gateway chuyển sang trạng thái **ACTIVE** trước khi test. Default hostname là hostname do Google cấp; nếu muốn **custom domain**, cần quy trình DNS/TLS và mô hình load balancer phù hợp, không đơn thuần đặt một CNAME tùy ý rồi mặc định HTTPS sẽ đúng.

### Tạo API key và thử request

Trong Google Cloud Console, vào **APIs & Services → Credentials → Create credentials → API key** ở project client thử nghiệm. Áp **API restrictions** vào đúng managed API `java-orders-lab-api` và **application restrictions** (HTTP referrers, IPs hoặc loại client phù hợp) nếu có thể. Ghi key vào secret manager/biến môi trường tạm của client; **không commit key vào Git hoặc log**.

~~~bash
# Gán tạm trên máy lab. KHÔNG ghi giá trị thật trong Markdown.
API_KEY="REPLACE_WITH_RESTRICTED_LAB_API_KEY"

# Không gửi key: mong đợi bị gateway từ chối.
curl -i "https://$GW_HOST/v1/hello"

# Key sai: cũng phải bị gateway từ chối.
curl -i -H "x-api-key: INVALID" \
  "https://$GW_HOST/v1/hello"

# Key đúng được phép gọi API: mong đợi HTTP 200 và JSON.
curl -i -H "x-api-key: $API_KEY" \
  "https://$GW_HOST/v1/hello"

# Route không khai báo: không được tự chuyển tiếp tới backend.
curl -i -H "x-api-key: $API_KEY" \
  "https://$GW_HOST/healthz"
~~~

Kết quả lỗi khi thiếu/sai key có thể là `401` hoặc `403` với body tùy lý do Service Control; **đừng hardcode kỳ vọng duy nhất một mã**. `/healthz` không nằm trong OpenAPI nên thường không được route; production cũng nên kiểm thử method không hỗ trợ như `POST /v1/hello`.

**Kiểm tra hai đường gọi độc lập:** nếu `curl` tới Cloud Run URL không có ID token bị từ chối nhưng `curl` qua gateway với API key hợp lệ trả 200, ta đã chứng minh **backend IAM** và **gateway client-key** cùng hoạt động trong phạm vi lab. Đây **chưa chứng minh** JWT/end-user authorization vì lab hiện chỉ dùng API key.

## 6. Bảo vệ ứng dụng thực: JWT và quyền nghiệp vụ

Trong production, API key có thể gắn với project/consumer cho quota và attribution, nhưng **không đủ** cho dữ liệu cá nhân, tài chính hoặc đơn hàng. Cần xác thực caller bằng **JWT** (hoặc cơ chế tương đương), sau đó backend kiểm tra quyền nghiệp vụ.

Thêm security definition OpenAPI 2.0 với OIDC issuer/JWKS được tổ chức tin cậy. Ví dụ minh họa dùng Google ID tokens có issuer `https://accounts.google.com`; `CLIENT_ID` phải là audience OAuth client được chấp thuận:

~~~yaml
# Ghép vào securityDefinitions đã có, không thay bằng block riêng.
securityDefinitions:
  api_key:
    type: apiKey
    name: x-api-key
    in: header
  google_id_token:
    type: oauth2
    flow: implicit
    authorizationUrl: ""
    x-google-issuer: https://accounts.google.com
    x-google-jwks_uri: https://www.googleapis.com/oauth2/v3/certs
    x-google-audiences: YOUR_OAUTH_CLIENT_ID

# Cùng một item: yêu cầu BOTH API key AND JWT.
security:
  - api_key: []
    google_id_token: []
~~~

**Cách đọc OpenAPI security quan trọng:** trong một object cùng danh sách, các scheme kết hợp **AND**; nếu viết hai item `- api_key: []` và `- google_id_token: []` riêng, đó là **OR** — chỉ một trong hai cũng có thể qua. Không mở auth ngoài ý muốn vì hiểu sai YAML.

Client gửi:

~~~bash
# ID_TOKEN phải được cấp cho đúng issuer/audience và chưa hết hạn.
ID_TOKEN="REPLACE_WITH_VALID_USER_ID_TOKEN"
curl -i "https://$GW_HOST/v1/hello" \
  -H "x-api-key: $API_KEY" \
  -H "Authorization: Bearer $ID_TOKEN"
~~~

API Gateway xác minh chữ ký token qua JWKS, `iss`, `aud`, `exp` và các claims bắt buộc. Khi cấu hình JWT authentication, gateway gửi nội dung claim đã xác thực trong header **`X-Apigateway-Api-Userinfo`** (payload mã hóa base64url). Gateway có thể **thay** header `Authorization` bằng ID token phục vụ **backend invocation**; đừng coi header `Authorization` nhận tại Java là nguyên bản của user.

**Phòng chống header spoofing:** một số headers có thể được client gửi giả nếu backend có đường gọi khác hoặc proxy bị cấu hình sai. Vì thế:

1. Bảo đảm Cloud Run **chỉ những principal được phép** có quyền `run.invoker`, không mở `allUsers`.
2. Dùng API Gateway JWT validation đúng issuer/audience và loại bỏ route bypass.
3. Chỉ tin `X-Apigateway-Api-Userinfo` khi request thực sự được xác thực qua gateway và backend đã bảo vệ chặt đường truy cập; với hệ thống nhạy cảm, áp xác minh token/claims ở ứng dụng hoặc mô hình bảo mật sâu hơn khi yêu cầu.
4. Trong Java, thực hiện authorization theo `sub`/tenant/roles và **ownership của resource**, không chỉ kiểm tra JWT có chữ ký đúng.

**Deployment thay đổi:** tạo API config mới (ví dụ `java-orders-v2`) từ OpenAPI thêm JWT, chờ ACTIVE, kiểm thử các trường hợp có/không token, rồi chạy:

~~~bash
gcloud api-gateway gateways update "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="java-orders-v2" \
  --location="$REGION" \
  --project="$PROJECT_ID"
~~~

Chỉ chạy sau khi đã **tạo thành công `java-orders-v2` bằng `api-configs create`** và xác minh các route/auth; không dùng lệnh update như thể nó tự tạo config. Giữ config cũ để rollback nếu cần, sau đó dọn cấu hình không còn sử dụng theo quy trình.

## 7. Quota, rate limiting, CORS và request validation

API Gateway có thể dùng **API key gắn với consumer project** để tính quota. Phân biệt:

- **Quota:** giới hạn số lần dùng API trong khoảng thời gian (API Gateway hỗ trợ quota theo **phút/project** qua OpenAPI 2.0 extensions).
- **Rate limiting chống burst:** bảo vệ backend khỏi dồn request trong vài giây; quota theo phút không thay hoàn toàn burst control.
- **Authorization:** quyền gọi một route hoặc xem một đơn hàng; quota không phải authorization.
- **CORS:** chính sách trình duyệt về cross-origin request, **không phải** cơ chế ngăn người dùng gọi bằng `curl`.

### Ví dụ khai báo quota cho API Gateway

Ghép các phần sau vào OpenAPI **2.0**; phần `x-google-management` nằm **top-level**, còn `x-google-quota` nằm **trong operation GET /v1/hello**:

~~~yaml
# Top-level (cùng cấp info, securityDefinitions, paths)
x-google-management:
  metrics:
    - name: read-requests
      displayName: Read requests
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: read-requests-per-minute
        metric: read-requests
        unit: "1/min/{project}"
        values:
          STANDARD: 100

# Trong paths./v1/hello.get:
x-google-quota:
  metricCosts:
    read-requests: 1
~~~

Quota trên có ý nghĩa **100 quota units mỗi phút cho mỗi consumer project** đối với operation được gắn cost 1. Không phải “100 request cho mỗi user” hay hạn chế IP. Những operation **không có `x-google-quota`** không tự bị áp quota này. Consumer project phải được nhận diện hợp lệ qua API key.

**Thay đổi quota khi có nhiều gateway:** `metrics` và `quota` được quản lý ở **cấp API**, không độc lập theo từng API config. Nếu config v1 và v2 đồng thời phục vụ nhưng bạn **đổi tên/xóa quota metric**, gateway đang dùng config cũ có thể trả **HTTP 500** khi kiểm tra quota. Giữ tên/cấu trúc metrics tương thích trong quá trình rollout; chỉ đổi limit khi đã kiểm soát phạm vi ảnh hưởng.

### CORS trong web API

Nếu frontend ở `https://portal.example.com` gọi gateway khác origin, browser gửi **preflight `OPTIONS`** khi request/header yêu cầu. Gateway không tự biến mọi endpoint thành CORS-enabled:

1. Định nghĩa route/method `OPTIONS` tương ứng trong OpenAPI, xem yêu cầu auth của preflight (trình duyệt không luôn gửi API key/JWT trong preflight).
2. Backend hoặc lớp proxy trả `Access-Control-Allow-Origin` với danh sách origin được chấp thuận; các headers như `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` chỉ vừa đủ.
3. Không dùng `Access-Control-Allow-Origin: *` cùng credentialed requests.
4. Không cho API key lộ vào client-side code không có khả năng giữ bí mật; website public có thể bị sao chép key, nên dùng JWT và bảo vệ backend/usage theo thiết kế.

**CORS không thay IAM, API key hoặc JWT.** Một caller dùng `curl` có thể gửi request không chịu chính sách CORS của browser.

### Những kiểm soát vẫn phải đặt trong Java

API Gateway không tự kiểm chứng đủ mọi schema/business constraint. Java API vẫn cần kiểm tra:

- Độ dài body, Content-Type, các trường bắt buộc, giới hạn file upload.
- Authentication/authorization của tenant và owner dữ liệu.
- SQL parameterization, chống injection, escaping output.
- Idempotency key cho `POST` có side effect, transaction/correlation ID.
- Timeout và connection pool tới Cloud SQL; không trả payload/stack trace nhạy cảm.
- Rate limit/circuit breaker bổ sung khi backend có phụ thuộc dễ quá tải.

## 8. Khi chuyển sang Apigee: quản trị API cho nhiều đối tác

**Apigee** tổ chức API ở mức sản phẩm và tổ chức người dùng API:

~~~mermaid
flowchart LR
    C["Developer app của đối tác"] --> P["Apigee API proxy"]
    P --> V["VerifyAPIKey / JWT / OAuth2"]
    V --> Q["Quota / SpikeArrest / threat policies"]
    Q --> T["TargetEndpoint: Java API"]
    PROD["API product"] --> V
    DEV["Developer + App registration"] --> PROD
    M["Apigee Analytics"] --> P
~~~

| Khái niệm | Ý nghĩa |
|---|---|
| **API proxy** | URL công khai, ProxyEndpoint, TargetEndpoint, flow/policy chain trước khi gọi backend |
| **API product** | Tập resource paths, HTTP methods và quota/quyền tiêu thụ dành cho nhóm ứng dụng |
| **Developer app** | Client đăng ký với API product; có credentials và trạng thái approved/revoked |
| **VerifyAPIKey** | Xác minh key thuộc ứng dụng hợp lệ và sản phẩm phù hợp |
| **OAuthV2 / VerifyJWT** | Xác thực bearer token và chính sách liên quan tùy mô hình identity |
| **Quota** | Hạn mức tiêu thụ theo app/product và khoảng thời gian |
| **SpikeArrest** | Làm mượt đột biến traffic để bảo vệ target |
| **API analytics** | Hiểu usage, latency và lỗi theo app/product/proxy |

**Điểm khác cốt lõi:** API Gateway keys thường xác định **consumer Google Cloud project**, trong khi Apigee developer apps/API products phục vụ hợp đồng truy cập của **đối tác** với khả năng quản lý lifecycle/analytics chi tiết. Đừng nghĩ chỉ tạo API product là đã cưỡng chế tất cả chính sách: cần gắn **VerifyAPIKey/OAuth/Quota policies** vào đúng proxy flow.

### Ví dụ chính sách VerifyAPIKey

Một file policy trong Apigee API proxy:

~~~xml
<VerifyAPIKey name="Verify-Partner-Key">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Gắn policy này vào **ProxyEndpoint request PreFlow** (hoặc flow thích hợp) để chặn request không có key hợp lệ **trước khi chuyển tới target**. Trong Apigee, key thường được cấp khi developer app đăng ký API product; vì vậy không mặc định lấy một **Google Cloud API key** từ APIs & Services Credentials làm Apigee developer-app key.

### Ví dụ giới hạn burst với SpikeArrest

~~~xml
<SpikeArrest name="Limit-Sudden-Traffic">
  <Rate>10ps</Rate>
</SpikeArrest>
~~~

`10ps` là ngưỡng định hướng **10 request/giây** theo cơ chế làm mượt của policy, không cam kết mọi giây đúng 10 request hoặc đảm bảo không còn overload. Để giới hạn theo **đối tác/app**, cấu hình `Identifier` dựa trên flow variable của `VerifyAPIKey` khi cần; còn **Quota** phù hợp với giới hạn tháng/ngày hoặc API product tiers.

**Apigee không thay quyền backend.** Nếu Java target là Cloud Run private service, proxy cần cơ chế backend authentication phù hợp (được hỗ trợ bởi Apigee target/token policies, service account và IAM Invoker). Không hạ backend thành public chỉ để test Apigee. Trước khi mở rộng sang proxy production, xác minh cách cấp token/target SSL, VPC connectivity và region thật sự của Apigee runtime.

### Tình huống chọn Apigee thay API Gateway

Doanh nghiệp có 120 đối tác: gói **Bronze** 1000 requests/ngày, **Gold** 100.000 requests/ngày, cần self-service developer portal, analytics per app, revocation, threat policy và versioning theo hợp đồng. Lúc này việc tự xây quản trị gói/đối tác trên API Gateway có thể tốn nhiều code; Apigee có khái niệm **API product**, **developer app**, policy và analytics tương ứng. Tuy nhiên cần dự toán licensing, API traffic, environment/runtime và chi phí vận hành theo biểu phí Apigee hiện hành.

## 9. Hardening, vận hành và kiểm soát chi phí

### Quyền IAM tối thiểu

| Danh tính | Quyền điển hình | Không nên cấp |
|---|---|---|
| CI/CD deployer | Cloud Run deploy, Artifact Registry, API Gateway config/gateway permissions và `iam.serviceAccounts.actAs` đúng SA | Owner toàn organization |
| API Gateway backend SA | `roles/run.invoker` **trên đúng Cloud Run service** | Cloud Run Admin/Storage Admin |
| Cloud Run runtime SA | Quyền Cloud Storage/Cloud SQL/Pub/Sub cần cho Java | IAM Admin hoặc Editor mặc định |
| Client Google Cloud project | API enabled và restricted API key | Backend Invoker hoặc runtime SA credentials |
| Apigee proxy runtime | Chính sách và backend access cần thiết | IAM role rộng không phục vụ proxy |

### Bảo vệ đầu vào và quan sát

- Dùng **HTTPS**, kiểm tra JWT issuer/JWKS/audience và scopes; hỗ trợ key rotation, không ghi API keys/JWT vào log.
- Cloud Run service **không cấp `roles/run.invoker` cho allUsers**, riêng API Gateway SA có quyền gọi; kiểm tra policy của từng backend và luồng CI/CD thay đổi IAM.
- OpenAPI `x-google-allow: configured`, kiểm tra method/path case-sensitive, không để một route ngoài OpenAPI bypass auth.
- Dùng Secret Manager cho secrets của Java; không đưa DB credentials vào OpenAPI, image hoặc curl history.
- Có quota và load protection ở API/Cloud Run, giới hạn database connections theo số instance.
- Gắn trace/correlation ID từ gateway tới Java, log request outcome/latency mà không log toàn body nhạy cảm.
- Phân biệt **4xx do gateway auth/quota** với **4xx/5xx của Java backend** khi báo lỗi.
- Hạn chế IAM của API config creator và theo dõi audit changes của gateway/config/service account.

### Chỉ số nên đặt dashboard

| Chỉ số | Cách dùng |
|---|---|
| Gateway request count theo HTTP status | Phát hiện API key sai, JWT expired và tăng 401/403/429 |
| Gateway/backend latency P50/P95/P99 | Tách chậm ở proxy, Cloud Run, Cloud SQL |
| Cloud Run request count, 5xx, instances và CPU/memory | Scale và downstream bottlenecks |
| Quota exceeded/consumer usage | Kiểm tra gói tiêu thụ, key bị lạm dụng |
| API config/gateway state và rollout history | Sự cố khi đổi backend URL, timeout, quota metric |
| IAM audit và Cloud Logging | Truy vết thay đổi role Invoker và traffic không mong đợi |
| Billing theo API Gateway/Apigee, Cloud Run, LB, network và Logs | Dự toán tổng chi phí API |

**Không chỉ lấy HTTP `200` làm bằng chứng an toàn:** một JWT hợp lệ nhưng thuộc tenant khác có thể đang truy cập sai dữ liệu nếu Java bỏ qua authorization. Và nếu gateway trả `200` nhưng Java ghi database thất bại sau response, hệ thống thiếu transaction/error reporting đúng.

### Chi phí và độ tin cậy

Một API qua Gateway có thể phát sinh:

~~~text
API Gateway traffic / gateway-related charges
  + Cloud Run CPU/memory/request cost
  + Artifact Registry / Cloud Build
  + Cloud SQL / Cloud Storage / Pub/Sub
  + network egress, load balancer nếu có
  + Cloud Logging / Monitoring
~~~

Với Apigee, cần tính **gói/license**, API proxy traffic/transactions, environment/runtime, policy type và các dịch vụ phụ thuộc theo hợp đồng. Không kết luận API Gateway/Apigee “rẻ hơn” chỉ bằng giá mỗi triệu requests, vì khác nhu cầu product management và vận hành.

**API Gateway có thể được triển khai nhiều region** theo thiết kế; một gateway đơn ở một region không tự đạt disaster recovery đa vùng. Với hệ thống quan trọng, thiết kế gateways ở nhiều region với load balancing/custom domains theo tính năng hỗ trợ, Cloud Run backends sẵn sàng đa vùng, cơ chế bảo vệ dữ liệu và thử failover.

## 10. Runbook xử lý sự cố và rollout an toàn

| Triệu chứng | Nghi vấn chính | Cách kiểm tra |
|---|---|---|
| Gateway không tạo được API config | OpenAPI sai cấu trúc, backend URL sai, deployer thiếu `actAs` trên backend SA | `api-configs create` operation, `--backend-auth-service-account`, IAM |
| Gateway chưa hoạt động | API config/gateway đang tạo hoặc region chưa hỗ trợ | `gateways describe`, state ACTIVE, Cloud Operations |
| Thiếu API key bị 401/403 | Chưa gửi `x-api-key` hoặc key chưa enabled cho managed service | OpenAPI `securityDefinitions`, API key restrictions, managed API enabled |
| Key đúng nhưng 403 | API chưa enable trong consumer project, key bị restrict sai hoặc backend IAM từ chối | Phân biệt gateway 403 với Cloud Run 403 bằng logs |
| JWT không hợp lệ | `iss`/`aud`/`exp` sai, JWKS thay hoặc thiếu Bearer header | API Gateway auth logs, OIDC issuer, `x-google-audiences` |
| `/v1/hello` trả 404 | `x-google-backend` path translation sai hoặc route không khai báo | OpenAPI paths/methods, backend logs, case sensitivity |
| Cloud Run trả 403 sau gateway | Gateway backend SA thiếu `roles/run.invoker`; ID token audience sai | Cloud Run IAM, `x-google-backend.address`, API config service account |
| Backend timeout/503/504 | Java khởi động chậm, gateway `deadline`, Cloud Run timeout, downstream pool cạn | Gateway vs Cloud Run latency, startup, DB connection limits |
| Quota trả 429 | Consumer project vượt quota hoặc burst protection | Quota metric/limit, consumer key, client backoff |
| Gateway cũ lỗi 500 sau config mới | Đổi/xóa quota metric ở cấp API làm config cũ tham chiếu metric không tồn tại | So sánh `x-google-management` và `x-google-quota` giữa các configs |
| Browser báo CORS | Preflight `OPTIONS` chưa có route/auth hoặc headers sai | Browser network log, API config và backend response |
| Apigee key hợp lệ nhưng bị reject | API product không chứa route/method, developer app bị revoke hoặc policy chưa đúng | Developer app/product, VerifyAPIKey flow variables, trace |

### Lệnh chỉ đọc phục vụ điều tra

~~~bash
gcloud api-gateway apis describe "$API_ID" --project="$PROJECT_ID"
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" --project="$PROJECT_ID"
gcloud run services get-iam-policy "$SERVICE" --region="$REGION"
gcloud run services logs read "$SERVICE" \
  --region="$REGION" --limit=50
~~~

Nếu request bị Gateway chặn trước khi gọi backend, Java sẽ **không có log request đó**. Tìm theo timestamp, gateway hostname, route, HTTP status và trace; không chuyển sang sửa code Java khi chưa xác định lỗi ở lớp nào.

### Phát hành API config mới và rollback

1. Git review `openapi.yaml`: paths, security, backend address, JWT claims, quotas và deadline.
2. Tạo **API config ID mới** thay vì chỉnh routing/auth trực tiếp trên ID cũ.
3. Kiểm tra config ACTIVE; test API key/JWT, route 404, gateway-to-backend IAM bằng một gateway canary hoặc quy trình thử nghiệm tương thích.
4. Chuyển Gateway sang config mới bằng `gcloud api-gateway gateways update`, giám sát 4xx/5xx/P95.
5. Nếu lỗi, **update lại gateway về config cũ** còn hợp lệ; IAM/backend thay đổi cũng có thể phải rollback riêng.
6. Chỉ xóa config cũ khi không còn Gateway nào sử dụng; không xóa config đang active trên gateway.

## 11. Bài toán ứng dụng: Orders API cho ba đối tác

Doanh nghiệp có Java API cung cấp:

~~~text
GET  /v1/catalog/{itemId}     → dữ liệu công khai có kiểm soát usage
GET  /v1/orders/{orderId}     → dữ liệu nhạy cảm của một đối tác
POST /v1/orders               → tạo đơn hàng có tác dụng phụ
~~~

Phương án khuyến nghị:

| Endpoint | Client protection | Java/backend protection |
|---|---|---|
| `GET /v1/catalog/{itemId}` | API key restricted + quota | Input validation, cache, read-only database role |
| `GET /v1/orders/{orderId}` | API key **và** JWT của đối tác | Kiểm tra tenant/ownership của order, chỉ trả dữ liệu được phép |
| `POST /v1/orders` | API key + JWT, giới hạn tải | Validate body, idempotency key, transaction và audit |

Backend Cloud Run vẫn private bằng IAM Invoker của Gateway; API Java dùng runtime service account chỉ đọc/ghi đúng Cloud SQL/Storage/Pub/Sub resources. Khi đối tác tăng từ 3 lên 100 và có yêu cầu quản lý **API product tiers**, developer app approvals, self-service onboarding và policies nâng cao, nhóm cân nhắc Apigee.

**Tình huống có lỗi:** đối tác A gửi JWT hợp lệ nhưng đoán `orderId` của đối tác B. Gateway xác thực chữ ký và trả request vào Java, **Java phải trả `403`** do không có quyền xem đơn hàng. Nếu chỉ dựa vào API key/JWT hợp lệ mà không kiểm tra ownership, API vẫn mắc lỗi phân quyền nghiêm trọng.

## 12. Checklist trước khi công bố API

- [ ] Backend Java hoạt động local, image Linux/AMD64 và Cloud Run dùng đúng `PORT`.
- [ ] Cloud Run không cho `allUsers` invoke; gateway backend SA có **chỉ** `roles/run.invoker` trên service.
- [ ] API config creator có `iam.serviceAccounts.actAs` trên đúng backend SA; deployer/runtime là các danh tính tách biệt.
- [ ] OpenAPI định nghĩa đúng paths/methods, `x-google-allow: configured` và `APPEND_PATH_TO_ADDRESS`.
- [ ] Managed API service đã enable, API key bị restrict theo API/client phù hợp.
- [ ] Với dữ liệu nhạy cảm, áp JWT issuer/JWKS/audience và xác minh quyền nghiệp vụ tại Java.
- [ ] Không cấu hình security **OR** khi thật sự cần **AND** giữa API key và JWT.
- [ ] Không ghi khóa, token, PII vào source, logs hoặc URL query; secrets có cơ chế rotation/revocation.
- [ ] Có quota, bảo vệ burst, giới hạn Cloud Run instances/DB pools và client retry có backoff.
- [ ] Browser có CORS/preflight đúng route nếu API được gọi trực tiếp từ web.
- [ ] Theo dõi gateway 4xx/5xx, backend 5xx, latency, quotas, IAM changes và chi phí.
- [ ] Có quy trình phát hành API config mới, canary, rollback và cleanup gateway/config không dùng.
- [ ] Nếu dùng Apigee, **API products, apps và policies** đã liên kết vào flow; đã thử revoke một key và enforcement quota.

## 13. Bài tập thực hành

**Bài 1 — Phân tích ranh giới bảo mật.** Một khách gọi `GET /v1/orders/42` có API key hợp lệ nhưng không có JWT. Nếu API config chỉ bắt key, điều gì sẽ xảy ra? Khi backend Java trả dữ liệu mà không kiểm tra ownership, lỗ hổng nằm ở đâu? Vẽ ba tầng client auth, backend IAM và business auth.

**Bài 2 — Triển khai lab.** Viết `App.java` và `Dockerfile` theo mục 2, thử `PORT=9090`, deploy Cloud Run không cho gọi anonymous, cấp Gateway SA `roles/run.invoker`, rồi tạo OpenAPI/Gateway. Liệt kê kết quả mong đợi của bốn test `curl` ở mục 5.

**Bài 3 — Bảo vệ JWT.** Cho cấu hình hai cách:

~~~yaml
# A: OR, không đủ nếu bắt buộc cả hai
security:
  - api_key: []
  - google_id_token: []

# B: AND
security:
  - api_key: []
    google_id_token: []
~~~

Vì sao cấu hình B phù hợp với route đơn hàng nhạy cảm? Nêu các JWT claims được gateway kiểm tra và authorization Java vẫn phải làm.

**Bài 4 — Quota theo project.** Một API có quota 1000 units/phút/project, `GET` cost 1, `POST` cost 5. Trong một phút, đối tác gửi 200 GET và 100 POST. Tổng units là bao nhiêu? Còn bao nhiêu units để dùng? Nếu 3 user của cùng project chia sẻ một key, liệu mỗi người tự có 1000 units?

**Bài 5 — Debug lỗi.** Gateway gọi Cloud Run trả 403 dù `curl` trực tiếp kèm ID token từ admin trả 200. Hãy kiểm tra API config backend SA, role Invoker, `x-google-backend.address`, JWT audience backend và IAM propagation trước khi đổi source Java.

**Bài 6 — Phát hành config.** Gateway A chạy `config-v1` có quota metric `read-requests`. Nhóm tạo `config-v2` thay metric thành `read-v2` rồi cập nhật Gateway B. Vì sao Gateway A có thể lỗi 500? Thiết kế rollout và rollback không phá quota metric chung của API.

**Bài 7 — Chọn Apigee.** Một đơn vị có 50 đối tác, gói Bronze/Gold theo mức tiêu thụ, cần thu hồi khóa từng developer app, giám sát usage theo đối tác và bảo vệ burst. Hãy đề xuất API product, VerifyAPIKey, Quota, SpikeArrest, cách gắn policies vào flow và IAM của target Cloud Run.

**Bài 8 — Thiết kế production.** Đối tác gọi `POST /v1/orders` hai lần vì client timeout sau khi database đã commit. Đề xuất idempotency key, unique constraint/transaction, timeout và tracing ở Java; chỉ ra vì sao API Gateway không thể tự ngăn nghiệp vụ ghi trùng chỉ với API key.

## Tài liệu tham khảo chính thức

- [Getting started with API Gateway and Cloud Run](https://cloud.google.com/api-gateway/docs/get-started-cloud-run) — thứ tự tạo backend, API config và gateway.
- [Create an API config](https://cloud.google.com/api-gateway/docs/creating-api-config) — `gcloud api-configs create`, immutability, managed service và rollover.
- [Deploy an API to a gateway](https://cloud.google.com/api-gateway/docs/deploying-api) — `gcloud gateways create/update`, location và hostname.
- [Securing backend services](https://cloud.google.com/api-gateway/docs/securing-backend-services) — IAM Invoker cho Cloud Run backend.
- [Configure API Gateway development environment](https://cloud.google.com/api-gateway/docs/configure-dev-env) — quyền `actAs` và backend auth service account.
- [OpenAPI 2.0 extensions](https://cloud.google.com/api-gateway/docs/oasv2-extensions) — `x-google-backend`, path translation, `x-google-quota` và limits.
- [Use API keys](https://cloud.google.com/api-gateway/docs/authenticate-api-keys) — tạo/restrict key và managed service.
- [Using JWT to authenticate users](https://cloud.google.com/api-gateway/docs/authenticating-users-jwt) — issuer, JWKS, audience và `X-Apigateway-Api-Userinfo`.
- [API Gateway troubleshooting](https://cloud.google.com/api-gateway/docs/troubleshoot) — lỗi IAM, keys, config và quota metrics.
- [API Gateway quotas and limits](https://cloud.google.com/api-gateway/docs/quotas) — số API/config/gateways và request limits.
- [Apigee API products](https://cloud.google.com/apigee/docs/api-platform/publish/what-api-product) — developer app, API product, consumption policies.
- [Apigee VerifyAPIKey policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-api-key-policy) — kiểm chứng developer app key.
- [Apigee SpikeArrest policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/spike-arrest-policy) — kiểm soát đột biến traffic.
- [Apigee JSONThreatProtection policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/json-threat-protection-policy) — giới hạn payload JSON nguy hiểm.
- [API Gateway pricing](https://cloud.google.com/api-gateway/pricing), [Apigee pricing](https://cloud.google.com/apigee/pricing), [Cloud Run pricing](https://cloud.google.com/run/pricing) — dự toán chi phí toàn pipeline.
