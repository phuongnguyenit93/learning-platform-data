# Kiểm thử tải, lỗi phụ thuộc và khả năng phục hồi

## 1. Bài thực hành tổng hợp: API đúng khi hệ thống không còn lý tưởng

Trong module **INTEGRATION_API_REST**, người học đã tiếp cận cách thiết kế resource, URI, phương thức, mã trạng thái HTTP, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền và xử lý lỗi. Bài thực hành tổng hợp này đặt những kiến thức đó vào một hệ thống đang nhận nhiều request, có dependency chậm hoặc tạm mất kết nối. Mục tiêu không phải làm cho mọi response đều là **200**, mà là giữ đúng hợp đồng và các bất biến nghiệp vụ trong giới hạn tài nguyên đã cam kết.

**Đề bài:** xây dựng và kiểm chứng một **Order API** giả lập bằng **Java 17+, Spring Boot 3, PostgreSQL**, gọi **Inventory API** qua HTTP, dùng **Redis** cho cache/rate limit và chạy sau gateway. Hãy thiết kế thử nghiệm tải, tiêm lỗi và phục hồi để chứng minh rằng:

- Các operation đọc bình thường đạt SLO khi tải trong mức được phép.
- Dependency Inventory chậm hoặc lỗi không làm mọi request GET độc lập bị treo.
- Không tạo **hai đơn hoặc hai lần giữ tồn kho** khi client retry một operation.
- Không tạo đơn thành công với giá/tồn kho phỏng đoán khi dependency bắt buộc không khả dụng.
- Không bỏ qua JWT, tenant/object-level authorization hoặc các precondition **If-Match**.
- Sau khi gỡ fault, latency, error rate, circuit state và backlog trở lại ngưỡng; dữ liệu vẫn nhất quán.

### Kết quả cần nộp

Một bài thực hành hoàn chỉnh có **mã test**, cấu hình/fixture, bảng số đo theo ba giai đoạn **baseline → fault → recovery**, ma trận kiểm thử HTTP/security, bằng chứng đối soát database và một báo cáo ngắn nêu **PASS / FAIL / INCONCLUSIVE** cùng quyết định phát hành.

**Giới hạn an toàn:** mọi workload và fault phải hướng tới **localhost, test namespace hoặc staging đã được chủ hệ thống phê duyệt**, dùng dữ liệu/credential giả lập và giới hạn RPS, duration, VUs, số bản ghi. Không chạy spike, phá kết nối, restart DB hay gửi đơn hàng lên hệ thống production/thanh toán thật chỉ để làm bài.

## 2. Hệ thống mẫu và ranh giới kiểm thử

~~~mermaid
flowchart LR
    C[Test client / k6 / REST Assured] --> G[Gateway / rate limiter]
    G --> S[Spring Boot Order API]
    S --> P[(PostgreSQL primary)]
    S --> R[(Redis: cache / quota)]
    S --> I[Inventory HTTP stub]
    S --> O[Outbox worker / audit]
    I --> S
~~~

Trong môi trường học, **Inventory** chạy qua WireMock hoặc MockWebServer để chủ động trả **200, 503, delay, connection reset**; nếu cần thử lỗi TCP có thể đặt Toxiproxy trước stub. Payment thật **không được gọi**: nếu mở rộng bài sang thanh toán, chỉ dùng payment sandbox có quyền.

### 2.1. Hợp đồng endpoint tối thiểu

| Endpoint | Hành vi bình thường | Hành vi khi lỗi |
| --- | --- | --- |
| **GET /api/v1/products/{id}** | 200 JSON product public/authorized, 404 khi không tìm thấy | 503 nếu nguồn dữ liệu bắt buộc không đáp ứng; có thể cache theo policy |
| **GET /api/v1/orders/{id}** | 200 JSON đúng tenant/owner, ETag và cache policy riêng tư | 401/403/404 theo security policy; 503 khi DB bắt buộc lỗi |
| **POST /api/v1/orders** | 201 Created + Location sau khi giữ tồn kho và tạo order hoàn chỉnh; yêu cầu Idempotency-Key | 400 input sai, 401/403, 409 conflict/fingerprint, 429 quota, 503 Inventory chắc chắn từ chối |
| **PATCH /api/v1/orders/{id}** | If-Match bắt buộc; 200 hoặc 204 theo contract; revision tăng nguyên tử | 412 stale ETag; 428 thiếu precondition nếu server bắt buộc |
| **GET /api/v1/order-operations/{id}** | Trả trạng thái operation đã tiếp nhận bền vững theo tenant | 404 khi không tồn tại/không được biết, 503 nếu nguồn authoritative down |

**Phân biệt ba outcome của POST:**

1. **Chưa thực hiện**: Inventory stub trả 503 **trước khi xác nhận bất kỳ reservation nào**. Server có thể trả 503 Problem Details và không tạo order hoàn tất.
2. **Đã commit**: hệ thống đã giữ hàng và commit order; trả **201 + Location** và lưu idempotency outcome.
3. **Không xác định từ góc nhìn client**: request đã gửi đi, response mất/timeout và upstream **có thể** đã giữ hàng. Không tự coi là thất bại rồi gửi lại với key mới. Dùng **cùng Idempotency-Key**, operation ID, reconciliation/status endpoint; nếu ứng dụng đã **durably accepted** việc xử lý bất đồng bộ, **202 Accepted** và status resource là hợp đồng phù hợp.

Đừng hứa rằng một transaction DB đơn lẻ tự bảo đảm nguyên tử cùng một Inventory HTTP service. Hệ thống cần **reservation key**, idempotency, trạng thái PENDING/COMPLETED/FAILED và quy trình hoàn tác/đối soát khi không có distributed transaction.

### 2.2. JSON và lỗi nhất quán

Ví dụ tạo đơn hợp lệ:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <test-access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: lab-20261118-tenant-a-op-001

{"sku":"LAB-KB-001","quantity":1}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json
Cache-Control: no-store

{"id":"11111111-1111-4111-8111-111111111111",
 "status":"CONFIRMED","sku":"LAB-KB-001",
 "amountMinor":2590000,"currency":"VND","revision":1}
~~~

Nếu Inventory chắc chắn chưa giữ hàng, response mẫu:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
Retry-After: 3

{"type":"https://api.example.test/problems/inventory-unavailable",
 "title":"Inventory temporarily unavailable",
 "status":503,"code":"INVENTORY_UNAVAILABLE"}
~~~

**Retry-After: 3** là giá trị ví dụ khi server có cơ sở hướng dẫn retry; không bảo đảm sẽ phục hồi sau đúng ba giây. Nếu gateway hết thời gian chờ upstream, có thể thấy **504 Gateway Timeout**; client timeout không nhất thiết nhận bất kỳ status HTTP nào.

### 2.3. Phạm vi trách nhiệm và giả định

- JWT/role/tenant được xác minh bởi Spring Security; **tenantId từ body/query không được thay caller context**.
- Inventory stub và DB là thành phần test, dữ liệu order không có PII thật.
- Không cần triển khai hệ thống phân tán production hoàn chỉnh; có thể mô phỏng queue/outbox để kiểm các invariants nhưng phải ghi rõ những giới hạn chưa chứng minh.
- Test **REST Assured** đi qua HTTP embedded server để bao gồm filter chain và serialization; test **k6** từ bên ngoài qua endpoint test để tạo arrival rate đo được.
- Việc chạy trên staging thật chỉ được thực hiện khi có quyền và runbook rollback; một test local không chứng minh khả năng chịu lỗi của Kubernetes gateway/DB cluster production.

## 3. Tiêu chí thành công: SLO và bất biến dữ liệu phải cùng đúng

Trước khi chạy, lập một **thỏa thuận đo lường**. Các ngưỡng dưới đây là **giả định cho bài tập**, không phải mặc định khuyến nghị cho mọi REST API:

| Chỉ số | Mục tiêu ở tải đã định | Lưu ý |
| --- | --- | --- |
| GET products | **p95 dưới 250 ms; p99 dưới 600 ms** | Đúng item/tenant/cache profile |
| GET orders | **p95 dưới 300 ms** | Không bypass ACL, ETag đúng |
| POST orders | **p95 dưới 800 ms** khi Inventory khỏe | Không duplicate order/reservation |
| Unexpected HTTP errors | **dưới 0,5%** ở baseline | Tách 401/403/409/429 cố ý, 503 do fault |
| Steady-state recovery | **≤45 giây sau khi gỡ fault** | Hai cửa sổ 15 giây liên tục đạt SLO |
| Data integrity | **0 duplicate charge/order, 0 cross-tenant leak** | Kiểm authoritative DB/ledger |
| Fault boundary | GET không phụ thuộc Inventory vẫn phục vụ trong budget | Không lấy sự cố POST làm lý do 200 giả |

**Tính hợp lệ của một phép đo:** công cụ phát tải phải thực sự đạt arrival rate mục tiêu; **dropped iterations** và load-generator CPU không được cho thấy thiếu công suất. Nếu test không tạo fault như cấu hình, lỗi log/metrics thiếu hoặc số mẫu p99 quá ít, báo **INCONCLUSIVE**, không tự gắn PASS.

### 3.1. Phân biệt ba nhóm số đo

**Tải:** offered arrival rate, achieved RPS, concurrent in-flight requests, dropped iterations, số VUs, mix read/write, warm vs cold cache.

**Độ trễ và lỗi:** p50/p95/p99 theo **route và outcome**, connection/TTFB/body timings, 2xx/4xx/5xx, socket timeout, latency khi breaker mở, rate-limit rejects.

**Tính đúng đắn:** DB rows mới, reservation ledger, idempotency fingerprints, tenant scope, outbox backlog, optimistic-lock conflicts và độ đúng của ETag. HTTP 201 không chứng minh reservation thành công nếu logic backend có bug.

Không cộng các percentiles của từng pod để lấy "p99 hệ thống". Dùng histogram/distribution phù hợp cho toàn bộ requests trong window; đừng trộn GET nhanh và POST chậm rồi so một p95 chung với SLO từng endpoint.

### 3.2. Open load và closed load

- **Closed VUs:** một virtual user đợi response xong mới gửi request kế. Khi server chậm, tốc độ phát request giảm; dễ **giấu tail latency/coordinated omission**.
- **Open arrival rate:** tiếp tục lập lịch request ở tốc độ định trước, cho thấy queue/pool cần chịu số request mới khi upstream chậm. Phải cấp đủ VUs và theo dõi dropped iterations.
- **Stress/spike/soak:** chỉ chạy sau baseline, với trần tải, abort condition và quyền thực hiện; không tự thay profile giữa lúc đo rồi so trực tiếp p99.

## 4. Chuẩn bị lab và dữ liệu thử nghiệm

Một stack tối thiểu:

| Thành phần | Thiết lập |
| --- | --- |
| Java | JDK 17+ và Maven/Gradle phù hợp với Spring Boot dự án |
| Order API | Spring Boot 3, Spring MVC, Security Resource Server, Validation |
| Database | PostgreSQL test/Testcontainers; schema có order, idempotency operation, outbox |
| Cache/quota | Redis test hoặc in-memory adapter có giới hạn, không dùng chung production |
| Inventory | WireMock/MockWebServer trên localhost hoặc test namespace |
| Test HTTP | JUnit Jupiter + REST Assured + SpringBootTest RANDOM_PORT |
| Load | k6 hoặc công cụ tạo open-arrival-rate tương đương |
| Metrics | Spring Boot Actuator/Micrometer + logs/traces theo experiment ID |

**Fixture bắt buộc:** ít nhất hai tenants A/B, các principals reader/writer/admin có JWT ký hợp lệ cho test, một reader không được quyền POST, các product IDs khác nhau, Inventory stock cố định, order IDs khác tenant, nhiều revisions để thử If-Match và một clock/test config có thể điều khiển TTL.

**Dữ liệu tải:** tạo ít nhất vài trăm IDs tổng hợp để không để cache của một ID duy nhất che vấn đề DB. Tránh dùng token người dùng thật, số điện thoại/thẻ, email thực, dữ liệu xuất hiện trong customer reports hoặc analytics production. Các POST test dùng SKU/tenant riêng và có cleanup; nếu gửi 2 POST/s trong 120 s sẽ có ~240 test operations, vì vậy phải cấp quota DB và cleanup tương ứng.

### 4.1. Những ràng buộc trước khi bấm chạy

1. Kiểm tra **target hostname/namespace allowlist**, người sở hữu và thời gian chạy.
2. Giới hạn **RPS, VU, duration, số đơn và dung lượng**; đặt lệnh dừng/quy trình ngắt fault.
3. Không có external payment, SMS, email hoặc webhooks thật; tất cả upstream nguy hiểm dùng sandbox/stub.
4. Bật metrics, request/correlation ID và khả năng truy vấn authoritative DB; **redact Authorization/Cookie/PII**.
5. Đảm bảo test transactions/rows tách biệt; **@Transactional trên JUnit thread không tự rollback HTTP requests chạy trên server thread**.
6. Có tiêu chí **dừng ngay** nếu phát hiện cross-tenant data leak, duplicate charge, mất dữ liệu hoặc gây ảnh hưởng ngoài môi trường test.

## 5. Thiết kế workload và chuỗi thời gian

Dùng ba vòng đo chạy với **cùng workload, seed, phiên bản ứng dụng và cấu hình**:

~~~text
0:00–0:30  Warm-up: tạo kết nối, nạp cache theo kế hoạch
0:30–2:30  Baseline: Inventory khỏe, đo p95/p99 và domain invariants
2:30–3:00  Fault window: Inventory trả 503/timeout có kiểm soát
3:00–4:00  Recovery window: gỡ fault, đo steady-state + backlog
4:00+      Reconcile orders/reservations và cleanup
~~~

Đây là ví dụ về **thứ tự**, không phải một script duy nhất bắt buộc tự động điều khiển fault. Gắn các mốc **T1 lúc bật fault**, **T2 lúc gỡ fault** vào metrics. Khi nhiều test chạy song song, phải phân biệt chính xác requests thuộc từng window; tránh dùng request chạy trước T1 nhưng kết thúc sau T1 như bằng chứng thuần baseline.

**Workload minh họa:**

- **20 GET products/giây**, nhiều IDs, dùng token reader; đây là luồng phải ít phụ thuộc Inventory.
- **2 POST orders/giây** vào tenant test với idempotency key duy nhất theo operation, tạo dữ liệu synthetic.
- Tùy chọn bổ sung GET orders, PATCH with If-Match, 429 quota tests ở **kịch bản riêng**, không trộn 401/429 chủ động với baseline error budget của đường đọc chính.
- Khi fault, giữ offered arrival rate cố định (trong trần phê duyệt) để đo **bulkhead + retry pressure**; không tự tăng tải giữa outage.

**Lưu ý:** k6 không phải công cụ đo transaction correctness trên DB; sau mỗi window cần đối soát authoritative state bằng test fixture/audit query và kết hợp JUnit/API tests.

## 6. k6: phép thử GET có open arrival rate

Script dưới đây minh họa read scenario **20 req/s trong 2 phút**, mỗi request chọn một product ID giả lập. Điều kiện chạy bắt buộc đặt biến môi trường và chỉ trỏ vào test environment.

~~~javascript
import http from "k6/http";
import { check } from "k6";
import { Rate } from "k6/metrics";

const contractFailure = new Rate("contract_failure");
const ids = (__ENV.PRODUCT_IDS || "")
    .split(",").map(x => x.trim()).filter(Boolean);
const base = __ENV.API_BASE_URL;
const token = __ENV.TEST_READ_TOKEN;

export const options = {
    scenarios: {
        catalog_read: {
            executor: "constant-arrival-rate",
            rate: 20,
            timeUnit: "1s",
            duration: "2m",
            preAllocatedVUs: 25,
            maxVUs: 60,
            exec: "readCatalog"
        }
    },
    thresholds: {
        "http_req_duration{scenario:catalog_read}": [
            "p(95)<250", "p(99)<600"
        ],
        "contract_failure": ["rate<0.005"],
        "dropped_iterations": ["count==0"]
    }
};

export function setup() {
    if (__ENV.LAB_AUTHORIZED !== "yes" ||
        !base || !token || ids.length === 0) {
        throw new Error("Lab authorization or fixtures missing");
    }
}

function matchesProduct(response, id) {
    if (response.status !== 200) return false;
    const type = response.headers["Content-Type"] || "";
    if (!type.includes("application/json")) return false;
    try {
        return response.json("id") === id;
    } catch (e) {
        return false;
    }
}

export function readCatalog() {
    const id = ids[Math.floor(Math.random() * ids.length)];
    const url = base + "/api/v1/products/" + encodeURIComponent(id);
    const res = http.get(url, {
        headers: {
            Authorization: "Bearer " + token,
            Accept: "application/json"
        },
        tags: { operation: "get_product" },
        timeout: "2s"
    });

    const correct = matchesProduct(res, id);
    check(res, { "product contract valid": () => correct });
    contractFailure.add(!correct, { operation: "get_product" });
}
~~~

**Đọc kết quả đúng cách:** kiểm achieved RPS, duration, percentiles, **dropped_iterations**, CPU của load generator và status breakdown. Metric **http_req_duration** của k6 có phạm vi đo riêng; DNS/TLS/connect/blocked có metrics khác. Không coi mỗi request trả 200 là "đúng" nếu JSON ID sai hoặc response từ tenant khác.

Nếu muốn thêm **POST scenario** trong cùng run, xem mục 7. Các biến **LAB_AUTHORIZED** là guardrail trong script, **không thay thế quyền phê duyệt vận hành**. Token lấy từ test issuer/secret manager, không commit vào repository hay in ra logs.

## 7. Mở rộng workload với POST nhưng không tạo giao dịch trùng

Đối với POST, **mỗi logical operation** cần Idempotency-Key riêng; retry của **cùng operation** phải tái dùng chính key đó. Không dùng một key cho mọi request, cũng không sinh key mới khi timeout làm trạng thái backend chưa chắc chắn.

Ví dụ k6 **scenario ghi độc lập** 2 req/s trên tenant test:

~~~javascript
import http from "k6/http";
import exec from "k6/execution";
import { check } from "k6";
import { Rate } from "k6/metrics";

const invalidWrites = new Rate("invalid_write_outcome");

export const options = {
    scenarios: {
        create_orders: {
            executor: "constant-arrival-rate",
            rate: 2,
            timeUnit: "1s",
            duration: "2m",
            preAllocatedVUs: 8,
            maxVUs: 30,
            exec: "createOrder"
        }
    },
    thresholds: {
        "http_req_duration{scenario:create_orders}": ["p(95)<800"],
        "invalid_write_outcome": ["rate<0.005"],
        "dropped_iterations": ["count==0"]
    }
};

export function setup() {
    const required = ["API_BASE_URL", "TEST_WRITE_TOKEN",
        "LAB_RUN_ID", "TEST_SKU"];
    if (__ENV.LAB_AUTHORIZED !== "yes" ||
        required.some(name => !__ENV[name])) {
        throw new Error("Use authorized synthetic test environment");
    }
}

export function createOrder() {
    const logicalId = __ENV.LAB_RUN_ID + "-"
        + exec.scenario.iterationInTest;
    const res = http.post(
        __ENV.API_BASE_URL + "/api/v1/orders",
        JSON.stringify({ sku: __ENV.TEST_SKU, quantity: 1 }),
        {
            headers: {
                Authorization: "Bearer " + __ENV.TEST_WRITE_TOKEN,
                "Idempotency-Key": logicalId,
                "Content-Type": "application/json",
                Accept: "application/json"
            },
            tags: { operation: "create_order" },
            timeout: "3s"
        }
    );

    let valid = res.status === 201
        && Boolean(res.headers.Location);
    if (valid) {
        try { valid = Boolean(res.json("id")); }
        catch (e) { valid = false; }
    }
    check(res, { "201 + Location + order id": () => valid });
    invalidWrites.add(!valid);
}
~~~

**Script này dành cho baseline khỏe**; trong fault window 503 có chủ đích, không dùng threshold 201 để tuyên bố HTTP 503 "sai" nếu đó là kết quả đúng hợp đồng. Fault cần scenario riêng, expected errors, kiểm latency và DB outcomes.

Đặt **LAB_RUN_ID mới cho mỗi lần chạy**, giữ idempotency key trong retry cùng operation. iterationInTest là chỉ số trong scenario, không dùng một mình qua nhiều runs. Nếu API có quota, cấp đủ stock và cách ly test tenants, tính trước số orders (~240 ở 2 POST/s trong 120 s) và cleanup.

### 7.1. Test race và replay cùng key

1. POST với key K và body A khi Inventory khỏe, nhận 201 + order ID.
2. POST lại **cùng K + body A + tenant**, theo contract demo nhận cùng order ID; không thêm DB row/giữ hàng.
3. POST **K + body B** → 409 idempotency fingerprint conflict.
4. POST K ở tenant B → không thể đọc outcome tenant A, dù string K trùng.
5. Gửi **hai POST đồng thời cùng K** → chỉ một operation được chấp nhận nguyên tử.
6. Khi client timeout và chưa biết upstream đã commit hay chưa, tra cứu operation/retry đúng **cùng key**; không tự sinh key mới.

## 8. Java/Spring: giới hạn timeout và phân loại lỗi

Ví dụ Spring Boot 3 dùng **RestClient** với transport đơn giản để minh họa **connect timeout và read timeout**:

~~~java
@Configuration
class InventoryHttpConfig {
    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder, Environment environment) {
        String url = Objects.requireNonNull(
            environment.getProperty("inventory.base-url"));

        var transport = new SimpleClientHttpRequestFactory();
        transport.setConnectTimeout(Duration.ofMillis(200));
        transport.setReadTimeout(Duration.ofMillis(350));

        return builder.baseUrl(url).requestFactory(transport).build();
    }
}
~~~

Cần imports phù hợp Spring Framework/Java. **SimpleClientHttpRequestFactory không cung cấp bounded connection pool**: ở production cần Apache HttpClient 5 hoặc transport tương đương có max connections, acquisition timeout, idle eviction và overall operation deadline. Read timeout không tự bao gồm mọi queue, backoff và retry.

### 8.1. Inventory gateway: phân biệt known failure với unknown outcome

~~~java
public record ReservationRequest(
        UUID tenantId, String sku, int quantity, String operationKey) {}

public record ReservationReceipt(String reservationId, String state) {}

@Service
public class InventoryGateway {
    private final RestClient client;

    public InventoryGateway(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    public ReservationReceipt reserve(ReservationRequest request) {
        try {
            return client.post()
                .uri("/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", request.operationKey())
                .body(request)
                .retrieve()
                .body(ReservationReceipt.class);
        } catch (HttpServerErrorException.ServiceUnavailable ex) {
            // Chỉ known-no-effect nếu Inventory contract bảo đảm.
            throw new InventoryUnavailableException(ex);
        } catch (ResourceAccessException ex) {
            // Request có thể đã được upstream nhận.
            throw new ReservationOutcomeUnknownException(ex);
        }
    }
}
~~~

**Skeleton cần bổ sung** imports, null/receipt-state validation, authentication service-to-service, tenant propagation được tin cậy và custom exceptions. Không gom HTTP 401/403, schema violation hoặc sai tenant thành timeout transient. **503 không mặc nhiên chứng minh upstream chưa có side effect**; giả định known-no-effect chỉ đúng khi có hợp đồng provider/stub rõ.

### 8.2. Resilience ở đúng dependency

| Cơ chế | Tiêu chí test |
| --- | --- |
| **Timeout/overall deadline** | Không chờ Inventory mãi, tính cả pool, connect, read, retry/backoff |
| **Bulkhead/queue bound** | Inventory hỏng không dùng hết threads/connections phục vụ GET độc lập |
| **Circuit breaker** | Khi lỗi liên tiếp, tạm ngừng calls; half-open probes có trần, phục hồi có cooldown |
| **Retry** | Không retry 400/401/403, chỉ transient safe/idempotent operations trong budget |
| **Admission control** | 429/503 khi quota/saturation theo contract, không bypass ACL |
| **Idempotency/outbox** | POST/replay không tạo duplicate, event đã commit không mất |

Cấu hình minh họa với Resilience4j hoặc phiên bản tương thích:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
  retry:
    instances:
      inventoryLookup:
        maxAttempts: 2
        waitDuration: 100ms
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 12
        maxWaitDuration: 0ms
~~~

Các tham số chỉ là **điểm bắt đầu cho phép đo**, không phải khuyến nghị cố định. instance **inventoryLookup** dùng cho GET tra cứu; **không tự gắn retry này vào POST reserve** nếu chưa chứng minh idempotency và xử lý outcome unknown. Kiểm Resilience4j decorators/annotation thật sự bao quanh calls, không chỉ YAML tồn tại.

### 8.3. Tính nhất quán của order dưới lỗi

Lưu **operation key + tenant + actor + fingerprint + outcome + trạng thái** với unique constraint phù hợp:

- **201** chỉ khi reservation và order được xác nhận hoàn tất theo contract.
- **202** chỉ nếu operation thực sự đã được **persist/queued bền vững** để xử lý sau, có status resource và worker/reconciliation.
- **503/timeout** khi không thể cam kết mức tối thiểu; không giả rằng upstream chưa commit nếu response mất.
- Khi worker retry hoặc outbox delivery **at least once**, phải giữ cùng business key và dedup ở Inventory/Payment.
- Một DB **@Transactional** không tự đảm bảo transaction nguyên tử với HTTP dependency.

## 9. Fault injection với WireMock/MockWebServer

Mỗi fault experiment phải ghi **giả thuyết, dependency, phạm vi, thời gian, điều kiện dừng và cách gỡ fault**. Ưu tiên Inventory HTTP stub trên local/test namespace; chỉ dùng Toxiproxy hoặc restart tài nguyên khi có quyền và giới hạn cụ thể.

| Fault | Cách tạo có kiểm soát | Expected result |
| --- | --- | --- |
| **HTTP 503 definite-no-effect** | Inventory stub trả 503 trước reserve | POST 503 Problem, không confirmed order |
| **Slow response headers** | Delay 800 ms, client deadline ngắn hơn | Bounded wait, không kéo hết servlet pool |
| **Connection reset** | Fault proxy/stub reset sau request bytes | Outcome UNKNOWN, reconcile theo operation key |
| **Intermittent 429** | Stub trả 429 + Retry-After | Không retry storm, attempts bounded |
| **Healthy recovery** | Gỡ fault, trả 200 | Circuit/queue/latency trở lại ngưỡng |
| **Redis unavailable** | Cô lập Redis trong lab | Cache/quotas đúng fail policy, không rò tenant |
| **DB pool saturation** | Pool test nhỏ, duration bounded | Fail fast, không deadlock, phục hồi pool |
| **Replica lag** | Làm chậm replica test | Fresh reads không vi phạm read-your-writes |
| **Pod restart** | Chỉ namespace staging được phép | Readiness/routing không mất committed writes |

Stub 503 bằng WireMock:

~~~java
WireMockServer inventory = new WireMockServer(
    WireMockConfiguration.options().dynamicPort());
inventory.start();

inventory.stubFor(
    post(urlEqualTo("/reservations"))
        .willReturn(aResponse()
            .withStatus(503)
            .withHeader("Content-Type", "application/problem+json")
            .withBody("{\"status\":503,\"code\":\"INVENTORY_DOWN\"}"))
);

// Cấu hình inventory.base-url trỏ tới inventory.baseUrl().
// Luôn reset và stop stub sau thí nghiệm.
~~~

Test phải chắc chắn Order API **đang gọi đúng stub**, không gọi Inventory ngoài môi trường test. Một HTTP 503 giả lập không kiểm được mọi loại connect/read timeout; dùng delayed headers, reset và Toxiproxy trong các test riêng. Lưu stub request counts và injected fault window để chứng minh lỗi đã xảy ra.

### 9.1. Mẫu giả thuyết test có thể kiểm chứng

~~~text
Experiment: INV-503-01
Baseline: 20 GET/s + 2 POST/s, 2 phút
Fault: Inventory /reservations trả 503 trong 30 giây
Safety: tenant synthetic; max 60 VUs; no real payment
Hypothesis: POST fail-fast, GET độc lập vẫn đạt p95
Expected HTTP: POST 503 + Problem Details, GET 200
Expected state: 0 CONFIRMED orders cho keys bị từ chối
Abort: cross-tenant leak, duplicate charge, overload ngoài scope
Recovery: gỡ fault, đo T2→T4 và reconcile theo key
~~~

Nếu fault không được áp dụng nhưng test vẫn xanh, kết quả **INCONCLUSIVE**. Đừng báo PASS chỉ vì server log một dòng "Inventory unavailable": phải có request count/status/delay thực và metric tương ứng.

## 10. Quan sát HTTP, JVM và domain state cùng lúc

| Tầng | Cần ghi |
| --- | --- |
| **k6** | offered/achieved requests/s, VUs, dropped iterations, p95/p99, status |
| **Gateway/Spring HTTP** | route template, status class, 429/502/503/504, latency |
| **JVM/pools** | CPU, GC pauses, memory, thread pool, HTTP/DB pool pending |
| **Resilience** | circuit OPEN/HALF_OPEN/CLOSED, bulkhead rejects, retry/timeout |
| **Inventory** | request count/key, reservations confirmed, fault profile thực |
| **PostgreSQL** | order/outbox/idempotency records, lock waits, DB pool usage |
| **Redis** | cache hits, errors, quota rejects, invalidation |
| **Security** | JWT validation, tenant ACL denies, không lộ cross-tenant data |

Gắn **experiment ID và correlation ID** trong traces. Tránh userId, orderId, tenantId thô, bearer token và PII trong metric labels hoặc CI logs. **HTTP 2xx/latency tốt chưa đủ**: phải đối soát DB và reservation ledger để chứng minh đúng kết quả nghiệp vụ.

## 11. Recovery: không đồng nhất health UP với phục hồi

Khai báo mốc:

~~~text
T0: baseline đạt SLO
T1: fault bật và được xác nhận có hiệu lực
T2: fault gỡ, Inventory đáp ứng khỏe
T3: API phục vụ được chức năng tối thiểu
T4: p95/error/queue đạt gate ở hai cửa sổ 15s liên tiếp
T5: đối soát DB, idempotency, reservations và outbox xong
~~~

- **Time to minimum service = T3 − T2.**
- **Time to steady-state recovery = T4 − T2.**
- **Time to data reconciliation = T5 − T2.**

**RTO** là mục tiêu thời gian phục hồi xác định trước; **RPO** là mức mất dữ liệu cho phép trong failure model. Với order đã commit, cần đối soát authoritative DB/ledger trước khi tuyên bố RPO=0. Client timeout không chứng minh chưa commit.

**Gate thực hành:**

1. Gỡ fault, xác nhận stub trả 200 và ghi T2.
2. Thử GET và **một số ít POST probes mới có key riêng**, không loop tạo orders vô hạn.
3. Quan sát breaker half-open/closed, pool pending giảm, không có retry burst.
4. Kiểm p95/error rate trong **hai cửa sổ liên tiếp mỗi cửa sổ 15 giây**; ghi T4.
5. Đối soát các operations trong fault window và backlog, ghi T5.
6. Nếu T4 quá budget hoặc dữ liệu sai thì **FAIL**; nếu thiếu samples/metrics thì **INCONCLUSIVE**.

## 12. Java + REST Assured: lỗi dependency không tạo order thành công giả

Test integration dùng Spring Boot RANDOM_PORT, REST Assured/JUnit 5 và Inventory WireMock stub. Ví dụ là **test skeleton**: cần import các class, setup token hợp lệ, @DynamicPropertySource cấu hình inventory.base-url tới stub, database/container riêng và cleanup.

~~~java
@Test
void definiteInventory503DoesNotConfirmOrder() {
    inventoryStub.stubFor(
        post(urlEqualTo("/reservations"))
            .willReturn(aResponse().withStatus(503)));

    String key = UUID.randomUUID().toString();
    String token = tokenFactory.forTenantWriter("tenant-a");

    given()
        .spec(apiSpec(port))
        .auth().oauth2(token)
        .contentType(ContentType.JSON)
        .header("Idempotency-Key", key)
        .body("{\"sku\":\"LAB-KB-001\",\"quantity\":1}")
    .when()
        .post("/orders")
    .then()
        .statusCode(503)
        .contentType("application/problem+json")
        .body("code", equalTo("INVENTORY_UNAVAILABLE"));

    assertEquals(0,
        orders.countConfirmedByOperationKey("tenant-a", key));
    assertEquals(0,
        inventoryLedger.countAcceptedReservations("tenant-a", key));
}
~~~

**Giới hạn quan trọng:** zero reservations chỉ được assert khi **stub/provider hợp đồng known-no-effect**. Với reset sau upstream accept, dùng UNKNOWN/reconciliation, không coi client exception là không có side effect. **@Transactional trên JUnit method không rollback commit do server HTTP thread tạo ra**. Dùng test DB riêng hoặc cleanup có chủ đích.

Thêm test delayed headers vượt timeout để assert request kết thúc trong budget **có headroom**, thay vì so một số milliseconds quá chặt gây flaky. Đo nhiều samples trong performance test và xác nhận GET không phụ thuộc Inventory vẫn chạy khi bulkhead bị chiếm.

## 13. OpenAPI 3.1: để test HTTP dựa trên hợp đồng công khai

Một bài thực hành tổng hợp phải công bố method, parameter, auth, request/response và lỗi trước khi viết assertions. Đoạn OpenAPI sau **rút gọn** cho operation tạo đơn:

~~~yaml
openapi: 3.1.0
info:
  title: Resilient Order API Lab
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      security: [{ bearerAuth: [] }]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: { type: string, minLength: 1, maxLength: 128 }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [sku, quantity]
              additionalProperties: false
              properties:
                sku: { type: string, minLength: 1 }
                quantity: { type: integer, minimum: 1, maximum: 50 }
      responses:
        '201':
          description: Order đã được tạo và xác nhận
          headers:
            Location:
              schema: { type: string }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '202':
          description: Operation đã được nhận bền vững để xử lý tiếp
          headers:
            Location:
              schema: { type: string }
        '400': { description: Input không hợp lệ }
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '409': { description: Idempotency fingerprint conflict }
        '429':
          description: Vượt quota
          headers:
            Retry-After:
              schema: { type: string }
        '503':
          description: Dependency bắt buộc không khả dụng
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/Problem' }
  /api/v1/orders/{id}:
    get:
      operationId: getOrder
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
        - in: header
          name: If-None-Match
          schema: { type: string }
      responses:
        '200':
          description: Đơn hàng được phép xem
          headers:
            ETag:
              schema: { type: string }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '304': { description: Representation chưa thay đổi, không có body }
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '404': { description: Không tìm thấy order được phép xem }
        '503': { description: Không lấy được core data bắt buộc }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer, bearerFormat: JWT }
  schemas:
    Order:
      type: object
      required: [id, status, sku, amountMinor, currency, revision]
      properties:
        id: { type: string, format: uuid }
        status: { type: string, enum: [PENDING, CONFIRMED, FAILED] }
        sku: { type: string }
        amountMinor: { type: integer, format: int64, minimum: 0 }
        currency: { type: string, minLength: 3, maxLength: 3 }
        revision: { type: integer, format: int64, minimum: 0 }
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
~~~

**Cần bổ sung** schema cho status resource của 202, PATCH/If-Match, security scopes, 412/428/504 và response examples khi triển khai thật. **Retry-After** là header tùy policy, không bắt buộc xuất hiện trong mọi 429/503. Không dùng **206 Partial Content** để biểu diễn order chưa hoàn tất; 206 thuộc HTTP Range. Không trả 207 hay 202 tùy tiện để che lỗi side effect.

**Bảo mật của 202:** status resource và operation receipt vẫn phải tenant/owner-scoped; client không được đoán operation ID của user khác để tra đơn. **201 replay** có thể dùng chính 201 hoặc một status khác nếu hợp đồng đã công bố; test phải khớp chính sách replay thật, không áp giả định HTTP chung.

## 14. Ma trận kiểm thử bắt buộc

Các ca phải được chạy theo **contract và điều kiện setup đã biết**, không gửi request ngẫu nhiên rồi suy status mong đợi.

| ID | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| B01 | GET products ở 20 req/s baseline | Đạt arrival rate, p95/p99/JSON body |
| B02 | POST orders ở 2 req/s baseline | 201 + Location, một order cho mỗi key |
| B03 | Payload/order count tăng | Không vượt quota/size, memory và DB ổn |
| B04 | VU generator thiếu | Có dropped iterations; test không được báo PASS |
| H01 | GET order sau PATCH có If-Match | ETag mới/200 hoặc 204 PATCH, GET đúng revision |
| H02 | PATCH với ETag cũ | 412, không ghi đè |
| H03 | GET If-None-Match khớp | 304 chỉ nếu đúng representation và đã authorize |
| H04 | GET list limit/cursor | Không bỏ ACL, không truy vấn vô hạn |
| F01 | Inventory 503 known-no-effect | POST 503 + Problem, 0 confirmed order |
| F02 | Inventory headers delay > client budget | Timeout bounded, GET độc lập vẫn phục vụ |
| F03 | Inventory connection reset | UNKNOWN, cùng key/reconcile; không double reserve |
| F04 | Inventory 429/503 xen kẽ | Retry budget không vượt deadline, không storm |
| F05 | Circuit OPEN | Calls fail-fast, không tiếp tục gọi upstream liên tục |
| F06 | Half-open và recovery | Probe bounded, quay lại CLOSED đúng điều kiện |
| F07 | Bulkhead full | Reject có kiểm soát, servlet/DB pool không bị giữ mãi |
| F08 | Redis unavailable | Cache/rate limit policy rõ; không fail-open security |
| F09 | PostgreSQL connection pool cạn | Bounded acquire timeout, không deadlock |
| F10 | Gateway trả 502/504 | Không lộ hostname/stack, response error đúng policy |
| I01 | POST cùng key và body | Outcome replay, không có duplicate order |
| I02 | Cùng key khác body | 409 fingerprint conflict, không sửa order cũ |
| I03 | Hai POST concurrent cùng key | Uniqueness/idempotency atomic |
| I04 | Client timeout sau reservation | Reconcile theo operation ID, không dùng key mới |
| S01 | Thiếu/sai JWT | 401 + Bearer challenge thích hợp, không side effect |
| S02 | Token thiếu quyền POST | 403, không reservation/order |
| S03 | Tenant B gọi GET/PATCH order tenant A | 403/404 theo policy, không rò dữ liệu |
| S04 | Client cố gửi price/tenantId không thuộc DTO | Không mass assignment/tin giá từ body |
| S05 | Cache từ admin/user A được truy cập bởi B | Không phát lại quyền/dữ liệu khác tenant |
| R01 | Gỡ fault nhưng circuit còn OPEN | Không kết luận recover chỉ từ health 200 |
| R02 | Hai cửa sổ 15 giây sau T2 đạt gate | T4−T2 ≤ 45s theo lab SLO |
| R03 | Backlog/outbox sau outage | Drain đúng budget, không mất/lặp nghiệp vụ |
| R04 | Sau recovery, reconcile tất cả operations | Không missing confirmed/duplicate charge |
| O01 | Log/metrics khi fault | Có trace/experiment ID, không chứa token/PII |

**Tiêu chí PASS của một test** phải bao gồm **HTTP observation + dữ liệu nguồn + giới hạn thời gian** nếu liên quan. Ví dụ F01 không thể PASS chỉ vì nhận 503 khi DB đã lặng lẽ tạo CONFIRMED order.

### 14.1. Race testing và data reconciliation

Trong DB test có thể kiểm một operation key tạo không quá một bản ghi authoritative:

~~~sql
SELECT tenant_id, idempotency_key, count(*)
FROM order_operations
GROUP BY tenant_id, idempotency_key
HAVING count(*) > 1;
~~~

**Kỳ vọng 0 rows** nếu unique constraint đã thiết kế đúng. Đây chưa kiểm duplicate **reservations ở upstream**: phải đối chiếu Inventory ledger theo cùng operation key. Đồng thời so số orders trạng thái CONFIRMED với các receipts đã xác minh; PENDING có thể hợp lệ tạm thời trong 202 workflow nhưng không được stuck vượt reconciliation SLA.

Cần kiểm **không có order tenant khác** trong response, kể cả status/resource không tồn tại theo caller. Với PATCH, CAS phải thực hiện ở DB, không chỉ if-check Java trước save.

## 15. Các bước thực hiện lab từ đầu tới cuối

### Bước 0 – Chốt hợp đồng và môi trường

Nộp bản mô tả endpoint/status, invariant, OpenAPI, test tenants, token scopes, Inventory stub base URL, DB cleanup và thời hạn chạy. Xác nhận API không thể tạo payment/thông báo thật. Thiết lập limits và abort guardrails trong k6/staging.

### Bước 1 – Kiểm đúng trước khi kiểm nhanh

Chạy REST Assured/JUnit cho **201/Location, 400, 401, 403, 404, 409, 412, 428, 429, 503 và Problem Details** theo endpoint hiện có. Tạo ít nhất hai tenants và một foreign-order test. Kiểm stock/price từ server, không tin client input. Khi contract chưa xanh, **không dùng load test để che bug correctness**.

### Bước 2 – Baseline không fault

Chạy read scenario rồi write scenario trong môi trường đã cho phép. Nếu chạy đồng thời, tổng profile phải được công bố rõ và không để test ghi phá dữ liệu. Ghi offered/achieved RPS, p95/p99, CPU, DB pool, quota rejects, số row sau POST. Kiểm **dropped iterations bằng 0** theo mục tiêu giả định; nếu không, điều chỉnh công suất generator hoặc tải mục tiêu trước khi diễn giải kết quả.

### Bước 3 – Fault dưới tải ổn định

Giữ cùng phiên bản ứng dụng và offered arrival rate. Tiêm từng fault **503, delay, reset** trên Inventory test stub theo cửa sổ riêng, ghi T1/T2, số requests thật bị fault và observability. Kiểm GET catalog vẫn chạy, POST fail đúng ngữ nghĩa, circuit/bulkhead/retry không tạo amplification. Không bật nhiều faults chồng lên nhau trước khi đã hiểu từng lỗi đơn lẻ.

### Bước 4 – Gỡ lỗi và đánh giá phục hồi

Gỡ stub lỗi, xác nhận Inventory khỏe, ghi T2. Theo dõi tới khi đạt gate hai cửa sổ liên tiếp, ghi T4 và đo thời gian. Không reset thủ công circuit/bỏ qua backlog chỉ để cho số đẹp. Nếu không đạt trong budget, ghi FAIL và bằng chứng: queue, breaker, pool, retry count, p95.

### Bước 5 – Đối soát và dọn dữ liệu

Kiểm DB orders, idempotency operations, Inventory reservations, outbox và status resources. Xử lý những operation UNKNOWN bằng cơ chế đã định, không tạo key mới để "thử lại". Xóa synthetic records theo namespace/test run ID, dừng stub/proxy, xác nhận trạng thái kết thúc trước khi đóng báo cáo.

### Bước 6 – Báo cáo và review

Nộp: **test code/config**, ma trận kết quả, đồ thị/tables baseline–fault–recovery, DB/ledger queries, T1–T5, quyết định và các rủi ro còn lại. Nếu thiếu load-generation evidence hoặc không có quyền/test scope, ghi **INCONCLUSIVE / chưa thực hiện thí nghiệm**, không điền số liệu giả như thật.

## 16. Đọc kết quả: ví dụ số minh họa, không phải lần chạy thực tế

Bảng sau là **dữ liệu giả định để luyện phân tích**, không phải kết quả đo từ hệ thống hay repository:

| Số đo | Baseline | Fault 503 Inventory | Sau recovery | Đánh giá |
| --- | ---: | ---: | ---: | --- |
| Offered GET/s | 20 | 20 | 20 | Giữ cùng tải |
| Achieved GET/s | 20 | 20 | 20 | Generator đủ khả năng |
| GET p95 (ms) | 140 | 175 | 148 | Dưới mục tiêu 250 |
| POST p95 (ms) | 490 | 110 | 515 | Khi fault, **503 nhanh** đúng mục tiêu fail-fast |
| POST 503 | 0% | 100% | 0% | Fault có hiệu lực, tách khỏi baseline SLO |
| Confirmed orders cho keys 503 known-no-effect | 0 | 0 | 0 | Bất biến đúng cho fault này |
| Circuit OPEN rồi CLOSED | CLOSED | OPEN | CLOSED | Cần log state transitions |
| Dropped iterations | 0 | 0 | 0 | Không có dấu hiệu generator thiếu VUs |

Giả sử **T2=180s** và đạt cửa sổ ổn định cuối tại **T4=210s**, thời gian phục hồi steady-state là **30s**, dưới ngân sách 45s. Tuy nhiên vẫn phải có **T5 đối soát**; nếu thấy hai confirmed orders dùng cùng key hoặc reservation orphan chưa xử lý theo policy, kết luận **FAIL dù HTTP metrics đạt**.

**Tại sao POST p95=110ms lúc outage không phải "hiệu năng cải thiện"?** Vì phần lớn operation trả lỗi sớm, không hoàn tất nghiệp vụ; phải phân loại latency theo **success/error/business outcome**. Một p95 thấp nhưng 100% 503 vẫn là mất chức năng tạo đơn.

### 16.1. Thang đánh giá mức độ kết luận

- **PASS:** đủ điều kiện tải, fault thật sự được áp, HTTP contracts và domain invariants giữ, recovery đạt gate.
- **FAIL:** ít nhất một invariant hoặc SLO bị vi phạm trong phạm vi đã xác định; có bằng chứng rõ.
- **INCONCLUSIVE:** k6 không phát đủ request, missing metrics, fixture không đúng, fault không áp hoặc sample quá ít.
- **NOT RUN:** chưa có quyền hoặc chưa chuẩn bị được môi trường; ghi rõ không phải PASS.

**Không làm đẹp báo cáo bằng cách bỏ 5xx hoặc loại bỏ các transactions không thành công khỏi mẫu mà không chú thích**. Báo cáo cần phân nhóm hợp lý, nhưng tỷ lệ user-visible failure vẫn phải được trình bày.

## 17. Lỗi thường gặp và thử thách nâng cao

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ nhìn average latency | Che p99 và queue wait | Theo dõi percentiles theo endpoint |
| Closed VUs nhưng gọi là tải cố định | Offered rate giảm khi server chậm | Open arrival + achieved-rate metrics |
| Dùng một product ID | Cache che database cost | Nhiều IDs, warm/cold cache tách |
| Gửi POST timeout lại với key mới | Duplicate order/reservation | Same key + reconciliation |
| Catch mọi Exception rồi trả 201 | Tạo thành công giả | Phân loại known/unknown failure |
| Circuit mở nhưng còn retry liên tục | Storm khi upstream đang down | Retry budget và decorator order |
| Test HTTP 503 mà không kiểm DB | Bỏ qua transaction đã commit | Order/Inventory ledger reconciliation |
| Quên JWT/tenant khi fault | Cross-tenant leak hoặc fail-open | Security-negative tests dưới fault |
| @Transactional trên JUnit method | Không rollback server HTTP transaction | Test DB isolation và cleanup |
| Có health 200 là coi recovered | Backlog/circuit còn bất thường | Stable windows + T5 reconciliation |
| Restart DB/proxy không có rollback | Phá môi trường chung | Scope được duyệt, safety/abort plan |
| Log request headers đầy đủ | Lộ token, cookie, PII | Redaction và metric labels bounded |

**Thử thách dành cho nhóm nâng cao:** thêm read-your-writes khi đọc replica chậm; đo 429 tại gateway và retry-after behavior; kiểm outbox consumer restart và at-least-once dedup; đặt idempotency TTL/scope; kiểm fallback cache của các trường optional nhưng không bỏ kiểm quyền.

## 18. Rubric chấm bài và checklist bàn giao

| Hạng mục | Điểm | Bằng chứng bắt buộc |
| --- | ---: | --- |
| **API contract & security** | 20 | OpenAPI, JWT/tenant ACL, đúng 201/202/409/429/503/412 |
| **Load design & đo** | 20 | Workload đại diện, bounded RPS/VUs, achieved-rate/p95/p99 |
| **Fault injection & resilience** | 25 | Stub/transport fault, bounded timeout/retry, circuit/bulkhead |
| **Correctness & reconciliation** | 20 | Order/Inventory ledger, idempotency, no duplicate/cross-tenant |
| **Recovery & report** | 15 | T2–T5, stable windows, PASS/FAIL/INCONCLUSIVE, cleanup |
| **Tổng** | **100** | Không có critical business/security violation |

**Điều kiện loại trực tiếp về an toàn:** tạo side effect trong production ngoài phạm vi được phép; tiết lộ token/PII; vượt ranh giới tenant; bỏ kiểm xác thực hoặc cố cho POST thành công bằng dữ liệu giả; không đối soát duplicate money/stock nhưng vẫn báo PASS.

**Checklist cuối bài:**

- [ ] Test scope, owner, môi trường, dữ liệu synthetic, trần RPS/VUs/duration rõ.
- [ ] OpenAPI, Idempotency-Key, ETag/If-Match và Problem Details thống nhất implementation.
- [ ] Baseline đạt tải mục tiêu, không có dropped iterations hoặc generator saturation.
- [ ] Fault 503/delay/reset đã thật sự tới Inventory test stub.
- [ ] Timeout, retry, circuit, bulkhead bảo vệ GET độc lập và không tạo storm.
- [ ] JWT, tenant/object ACL và input validation vẫn chạy trong mọi failure mode.
- [ ] Không có duplicate order/reservation, không có thành công giả.
- [ ] T2/T3/T4/T5, recovery gate và business ledger được đo/công bố.
- [ ] Logs/traces an toàn; cleanup/stop proxy và reset data sau thí nghiệm.
- [ ] Quyết định phát hành dựa trên bằng chứng, ghi rõ kết quả còn inconclusive.

**Ghi nhớ:** một hệ thống REST đáng tin cậy không phải hệ thống **không bao giờ trả lỗi**. Đó là hệ thống **đưa ra lỗi đúng, không phá bất biến, giới hạn tác động của dependency hỏng và phục hồi có thể đo lường**.

### Tài liệu để đối chiếu sau thực hành

- **RFC 9110 – HTTP Semantics**, **RFC 9457 – Problem Details for HTTP APIs**, **OpenAPI Specification 3.1**.
- **Spring Boot / Spring MVC / Spring Security / Spring Transactions**, **Micrometer/Actuator**.
- **k6 documentation**: constant-arrival-rate, custom metrics, checks, thresholds, dropped iterations.
- **WireMock, MockWebServer, Toxiproxy, Testcontainers, REST Assured, JUnit Jupiter**.
- **Resilience4j documentation**: timeout/time limiter, retry, circuit breaker, bulkhead.
- **OWASP API Security Top 10**: BOLA/BOPLA và resource consumption; **Google SRE Workbook**: SLO/error budget và incident recovery.
