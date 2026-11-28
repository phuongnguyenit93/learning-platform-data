# Viết hướng dẫn tái lập cùng bằng chứng thực thi và quy trình vận hành

Một bài capstone về **Spring AI Tool Calling** chỉ thực sự có thể bàn giao khi người khác biết cách dựng lại môi trường, chạy cùng kịch bản, kiểm tra tool nào đã được gọi, xác nhận hệ thống có thực hiện side effect hay không, và xử lý được lỗi sau triển khai. Một đoạn ảnh chụp giao diện chatbot hoặc câu trả lời “đã gửi thông báo” **không đủ làm bằng chứng thực thi**: mô hình có thể nói vậy dù callback chưa chạy, callback bị chặn bởi policy, request timeout, hoặc job chỉ mới được đưa vào hàng đợi.

Bài thuộc chương **Thực hành tổng hợp** của mô-đun `SPRING_AI_TOOL_CALLING`. Mục tiêu là biến một ứng dụng tích hợp LLM với nghiệp vụ thông qua `@Tool`, `ToolCallback`, schema đầu vào, `ToolContext`, xác thực quyền và điều phối nhiều lượt gọi thành một **bộ bàn giao tái lập được**. Bộ bàn giao phải gồm hướng dẫn chạy, thông tin phiên bản, fixture, tiêu chí kiểm chứng, bằng chứng đã làm sạch thông tin nhạy cảm, runbook vận hành, khôi phục và giới hạn chi phí. Các ví dụ dưới đây là **mẫu tài liệu và code minh họa**, không phải kết quả đã chạy thực tế trong bài học này.

## 1. Ba câu hỏi mà bộ bàn giao phải trả lời

1. **Tái lập được không?** Một kỹ sư khác với môi trường được cấp quyền có thể lấy đúng commit, dependency, cấu hình, dữ liệu tổng hợp, model/provider và chạy lại kịch bản theo các bước rõ ràng hay không?
2. **Bằng chứng gì chứng minh đã chạy đúng?** Có thể đối chiếu tool call do mô hình đề xuất, callback thực thi, schema/authorization, trạng thái nghiệp vụ độc lập và response cuối bằng log/trace/audit đã redaction hay không?
3. **Ai vận hành sau khi bàn giao?** Có health check, dashboard, giới hạn chi phí, cách phát hiện sai tool, playbook sự cố, rollback, backup/restore và chủ sở hữu rõ ràng hay không?

Tách biệt ba tiêu chí này. Một ứng dụng có code đúng nhưng thiếu hướng dẫn/cấu hình thì không tái lập được. Một môi trường chạy được nhưng không có audit hoặc assertions thì không chứng minh được side effect. Một demo một lần thành công nhưng không có cảnh báo/quy trình khôi phục thì chưa đủ điều kiện vận hành.

| Đầu ra | Mức tối thiểu | Bằng chứng chấp nhận |
| --- | --- | --- |
| Reproduction guide | Phiên bản, lệnh chạy, profile, fixture, expected output | Người độc lập làm theo và ghi actual result |
| Tool contract | Tool names, descriptions, JSON schema, DTO, owner, risk | Snapshot/hash của catalog và contract tests |
| Security controls | Trusted caller, tenant, permission, confirmation | Negative tests và audit cho các quyết định từ chối |
| Execution proof | Tool proposals, executed calls, business state | Trace/callback spy + trạng thái service/sandbox |
| Operational runbook | Kiểm tra hoạt động, giám sát, khắc phục, rollback | Drill hoặc diễn tập được ghi nhận |
| Evaluation report | Tỷ lệ đúng tool, arguments, completion, latency/cost | Kết quả suite có sample size và model version |

## 2. Kịch bản xuyên suốt của capstone

Xây một trợ lý hỗ trợ đơn hàng với hai hành động nghiệp vụ:

- `getOrderStatus(orderNumber)`: đọc trạng thái đơn đang thuộc tenant mà người dùng được phép truy cập; **không side effect**.
- `sendOrderUpdate(orderNumber, channel)`: gửi một thông báo cập nhật đơn; **có side effect**, yêu cầu quyền `order:notify` và xác nhận của người có thẩm quyền.

Người dùng thử nghiệm:

> “Xem trạng thái đơn ORD-REPRO-001. Sau đó, nếu đơn đã được giao, hãy gửi thông báo qua email.”

Hành vi chấp nhận được:

1. Hệ thống xác thực principal `repro-user-a` thuộc `repro-tenant-a`.
2. Mô hình đề xuất `getOrderStatus`; service đọc kết quả `DELIVERED` từ dữ liệu thử nghiệm.
3. Mô hình có thể đề xuất `sendOrderUpdate` khi điều kiện đã thỏa; ứng dụng kiểm tra quyền và **tạm dừng xin xác nhận**.
4. Khi chưa xác nhận, notification gateway **không được gửi gì**.
5. Khi người có quyền duyệt, ứng dụng tiếp tục đúng paused call, thực thi callback, ghi `notificationId`/idempotency key và trạng thái gửi của **sandbox**.
6. Câu trả lời cuối phản ánh sự thật: `SENT` khi gateway xác nhận đã gửi, `QUEUED` khi mới tiếp nhận, `DENIED` khi không được phép.
7. Kịch bản với caller tenant B, quyền thiếu hoặc lệnh gửi lặp phải bị từ chối/deduplicate theo chính sách.

Nếu model không chọn gọi tool, bộ đánh giá báo sai tool selection thay vì tự gọi callback để “chữa” output. Nếu provider không có tính năng tool calling hoặc tool schema không tương thích, ghi `BLOCKED_CONFIGURATION` với nguyên nhân, không đánh dấu thành công.

## 3. Sơ đồ kiến trúc có thể tái lập

~~~mermaid
flowchart LR
  U["Caller / UI"] --> A["Spring API + Authn"]
  A --> O["ChatClient + ToolCallingAdvisor"]
  O --> M["LLM Provider / Stub"]
  M --> O
  O --> G["ToolCallingManager"]
  G --> T1["getOrderStatus ToolCallback"]
  G --> T2["sendOrderUpdate ToolCallback"]
  T1 --> P["OrderService: tenant ACL"]
  T2 --> C["Approval + authorization"]
  C --> N["Sandbox NotificationGateway"]
  P --> DB[("Fixture DB")]
  C --> S[("Approval / Idempotency Store")]
  N --> L[("Sandbox Ledger")]
  O --> E["Observation / Audit"]
  P --> E
  C --> E
  N --> E
~~~

Các ranh giới cần thể hiện trong diagram của dự án:

- **Model không gọi trực tiếp DB/HTTP gateway**; callback chạy trong ứng dụng.
- `ToolContext` chứa thông tin caller/tenant tin cậy do server cung cấp.
- Tool arguments đến từ model là dữ liệu chưa đáng tin cậy, phải parse/validate.
- Approval không tự cấp quyền; authorization tại service vẫn bắt buộc.
- Sandbox ledger là **nguồn bằng chứng độc lập** với văn bản mô hình.
- Tracing/logging chỉ ghi identifiers hoặc kết quả đã làm sạch, không ghi secret hay PII.

Với Spring AI 2.x, `ToolCallingAdvisor` tự động quản lý vòng tool calling qua `ChatClient` theo mặc định. Nếu gọi trực tiếp `ChatModel` hoặc tắt auto-registration, application phải tự thực thi tool calls và duy trì đúng tool-call/tool-response history. Ghi rõ con đường thực thi thực tế trong reproduction manifest.

## 4. Những thông tin phải “đóng băng” để tái lập

Một manifest chạy thử nên chứa:

| Hạng mục | Trường cần ghi | Vì sao |
| --- | --- | --- |
| Source | Git commit SHA, branch/tag, dirty state | Chạy đúng code, không “latest” mơ hồ |
| Runtime | OS/architecture, Java vendor/version, timezone | Tránh khác biệt classpath/time behavior |
| Build | Spring Boot version, Spring AI version/BOM, Gradle/Maven version | API tool calling khác giữa phiên bản |
| Provider | Provider, endpoint type/region, model ID/version, response mode | Tool choice/provider semantics có thể thay đổi |
| AI options | Temperature, max tokens, tool choice, streaming/parallel-tool option nếu có | So sánh cùng điều kiện |
| Tool catalog | Tool names, descriptions, schemas, enabled flags, risk tier, fingerprint | Model selection phụ thuộc descriptions/schemas |
| Context | Profile, non-secret feature flags, caller role/tenant, locale | Khác quyền có thể khác tool set |
| Fixtures | Fixture version/hash, seeded records, reset strategy | Expected state có thể kiểm chứng |
| Integrations | Sandbox endpoints, stub/real mode, HTTP timeout, retry limit | Chặn gọi nhầm production |
| Test | Test suite ID/version, case set, assertion version | Phân biệt thay đổi test với thay đổi code |
| Outcome | Run ID, start/end time UTC, status, evidence index | Liên kết artifacts và audit |

**Pin dependency bằng phiên bản thực tế dự án đã kiểm thử**, không lấy “Spring AI bản mới nhất” hoặc `latest.release`. Spring AI 2.1 có Tool Call Confirmation, `ToolCallDecisions` và tool-loop APIs; nếu dùng 1.x/2.0, ghi rõ các khác biệt và triển khai approval gate ở ứng dụng thay vì giả định `requiresConfirmation` đã tồn tại.

Với model hosted, pin model ID nếu provider cho phép nhưng vẫn phải chấp nhận backend có thể thay đổi. Do tính bất định, **“tái lập” ở tầng LLM nghĩa là tái lập quy trình, inputs, tiêu chí và phân phối kết quả**, không hứa câu chữ đầu ra giống hệt mọi lần.

## 5. Cấu trúc bộ hồ sơ bàn giao đề xuất

Đây là **cây thư mục gợi ý cho project capstone do người học tự xây**, không phải những file được tạo trong module bài học hiện tại:

~~~text
order-assistant-capstone/
├── README.md                       # Mục tiêu và quick start
├── docs/
│   ├── REPRODUCE.md                # Chạy lại từ môi trường sạch
│   ├── TOOL-CONTRACTS.md           # Tên, schema, DTO và policy
│   ├── EVIDENCE.md                 # Danh mục bằng chứng & verdict
│   ├── RUNBOOK.md                  # Giám sát, xử lý sự cố, rollback
│   └── ADR-001-tool-execution.md   # Lựa chọn advisor, memory, approval
├── fixtures/
│   ├── orders-synthetic.json
│   └── expected-outcomes.json
├── src/main/java/...               # @Tool, policy, services, app
├── src/test/java/...               # Unit/integration/contract tests
├── src/liveTest/java/...           # Live model/sandbox tests (opt-in)
├── evidence/<run-id>/              # Outputs đã redaction cho một run
├── gradlew / gradlew.bat
├── gradle/wrapper/...
├── settings.gradle
└── build.gradle
~~~

Không đưa `.env` chứa secret, database production dump, raw chat transcript nhạy cảm hoặc service account key vào Git. Với `evidence/<run-id>`, chỉ commit các bằng chứng đã được duyệt; bằng chứng thô phải nằm trong artifact store có quyền truy cập và retention phù hợp.

Một manifest mẫu có trạng thái **chưa chạy**, vì chưa có bằng chứng thật:

~~~json
{
  "schemaVersion": "1",
  "runId": "repro-example-001",
  "sourceCommit": "<git-sha-from-run>",
  "javaVersion": "<java-version-from-run>",
  "springBootVersion": "<pinned-build-version>",
  "springAiVersion": "2.1.x (replace with exact resolved version)",
  "model": {
    "mode": "stub",
    "provider": "none",
    "modelId": "scripted-fixture-v1"
  },
  "toolCatalogVersion": "<schema-hash>",
  "fixtureVersion": "orders-synthetic-v1",
  "environment": "isolated-test",
  "testSuite": "order-assistant-capstone-v1",
  "status": "NOT_RUN",
  "evidence": [],
  "notes": "Example template, not actual execution evidence"
}
~~~

Khi chạy thật, điền thông số từ build/runtime, không suy đoán. Không sao chép nguyên `status: NOT_RUN` thành `PASS` bằng thao tác thủ công nếu thiếu đối chứng.

## 6. Phân tầng kiểm thử trong reproduction guide

| Tầng | Model | Nghiệp vụ | Bằng chứng chính | Bắt buộc cho |
| --- | --- | --- | --- | --- |
| L0 — Unit | Không model hoặc fake | Mock service | Schema validation, policy, side-effect spy | Mọi commit |
| L1 — Component/integration | Scripted `ChatModel` | Fixture DB/Testcontainers | Tool loop, history, DI, idempotency | Mọi PR |
| L2 — Real model controlled | Provider thật | Tool fixtures/stub service | Tool selection, arguments, multi-round completion | Regression theo lịch/opt-in |
| L3 — Real model + sandbox | Provider thật | Sandbox API/ledger | Request/response với service thật trong sandbox | Release/integration gate |
| L4 — Staging rehearsal | Provider thật | Staging đầy đủ | Approval, recovery, observability và runbook | Trước production rollout |

**L0/L1 phải PASS trước khi cho phép L2/L3.** Chỉ live test trong môi trường được cấp phép với credential sandbox, ngân sách, giới hạn model/tool calls và network allowlist. Kết quả L2/L3 bị skip phải ghi `NOT_RUN`, không gộp vào PASS.

Với test safety quan trọng (cross-tenant, leak secret, side effect trước approval), cần **deterministic assertion** ở L0/L1. Một mô hình có thể “thường” tuân theo prompt nhưng tỷ lệ đó không bảo đảm an toàn.

## 7. Môi trường và cổng an toàn trước khi chạy

Ghi các biến và nguồn cấu hình trong tài liệu (không ghi secret values):

| Biến/setting | Giá trị/nguồn ví dụ | Ghi chú |
| --- | --- | --- |
| `SPRING_PROFILES_ACTIVE` | `repro-stub` hoặc `repro-sandbox` | Không dùng profile production |
| `RUN_LIVE_AI_TESTS` | `false` mặc định | Chỉ bật khi opt-in |
| `SPRING_AI_OPENAI_API_KEY` | Secret manager nếu dùng OpenAI | Không echo ra terminal/CI |
| `APP_ALLOWED_SANDBOX_HOSTS` | Allowlist hosts do ứng dụng kiểm tra | Fail closed nếu URL không khớp |
| `APP_REPRO_TENANT` | `repro-tenant-a` | Quyền chỉ trên fixture tenant |
| `APP_REPRO_MAX_MODEL_CALLS` | 4 mỗi case | Giới hạn do ứng dụng thực thi |
| `APP_REPRO_MAX_TOOL_CALLS` | 3 mỗi case | Giới hạn do ứng dụng thực thi |
| `APP_REPRO_MAX_COST_USD` | 2.00 mỗi suite | Hard stop do harness thực thi |
| `APP_REPRO_RUN_ID` | Unique per test run | Correlation, không làm metric tag |

Trường `APP_REPRO_*` là **cấu hình giả định của ứng dụng capstone**, không phải property Spring AI tự áp dụng. Muốn có hiệu lực, phải viết validator, quota guard và fallback khi vượt ngưỡng. Spring AI 2.1 hỗ trợ giới hạn tool calls trên `ToolCallingManager`; nó không tự giới hạn toàn bộ tiền API, HTTP retries hay số lần gọi model trong mọi đường chạy.

Cổng preflight cho môi trường:

~~~mermaid
flowchart TD
  A["Người chạy chọn mode"] --> B{"stub hay live?"}
  B -->|stub| C["Fixture + local service, không cần provider key"]
  B -->|live| D{"Opt-in + API key + sandbox allowlist?"}
  D -->|Không| X["STOP / NOT_RUN"]
  D -->|Có| E{"Quota, deadline, tenant hợp lệ?"}
  E -->|Không| X
  E -->|Có| F["Model thật + sandbox-only tools"]
  C --> G["Chạy deterministic suite"]
  F --> H["Chạy live-controlled suite"]
  G --> I["Collect/redact evidence"]
  H --> I
  I --> J["Independent verifier + report"]
~~~

**Không fallback sang production** nếu sandbox lỗi. Nếu provider vượt giới hạn quota hoặc token usage không có, dừng/ghi `INCONCLUSIVE` theo policy, không coi đó là kết quả nghiệp vụ đã PASS.

## 8. Dependency/build và thông tin phiên bản

Một skeleton Gradle cho **Spring Boot + Spring AI 2.1** phải dùng BOM và provider starter tương thích. Ví dụ ở mức cấu trúc (thay phiên bản bằng giá trị đã pin từ release notes chính thức và lockfile dự án):

~~~gradle
plugins {
    id 'java'
    id 'org.springframework.boot' version '<PINNED_BOOT_VERSION>'
    id 'io.spring.dependency-management' version '<PINNED_PLUGIN_VERSION>'
}

group = 'example.capstone'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories { mavenCentral() }

dependencyManagement {
    imports {
        mavenBom "org.springframework.ai:spring-ai-bom:<PINNED_SPRING_AI_VERSION>"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

**Cảnh báo:** các placeholder trong dấu `<...>` khiến Gradle chưa chạy được. Người thực hành phải thay bằng phiên bản tương thích đã kiểm tra, giữ lock/verification metadata và ghi resolved dependency list. Không để một bài “reproduction guide” dùng wildcard hoặc tự cập nhật phiên bản mỗi lần chạy.

Nếu không dùng provider OpenAI, thay starter và profile bằng provider tương ứng; **không nạp đồng thời nhiều credential provider không cần thiết**. Khi test stub, có thể dùng `@TestConfiguration`/test profile để tiêm một `ChatModel` giả và không khởi tạo kết nối provider thật. Không nên coi riêng việc đặt `RUN_LIVE_AI_TESTS=false` là đủ nếu application context vẫn có bean gọi network lúc startup.

## 9. Mẫu tool contract cho kịch bản capstone

Định nghĩa DTO rõ ràng và giữ status ở dạng enum hoặc code hữu hạn:

~~~java
public record OrderStatusDto(
        String orderNumber,
        String status,
        String shipmentReference) {}

public record NotificationReceipt(
        String operationId,
        String orderNumber,
        String status,           // SENT, QUEUED, FAILED
        String notificationId) {}

public record CallerContext(
        String subjectId,
        String tenantId,
        String requestId) {}
~~~

Ví dụ `@Tool` read-only và tool có side effect. Các service và `requireCaller(...)` là dependency do ứng dụng xây dựng:

~~~java
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public final class OrderAssistantTools {

    private final OrderService orderService;
    private final NotificationService notificationService;

    public OrderAssistantTools(
            OrderService orderService,
            NotificationService notificationService) {
        this.orderService = orderService;
        this.notificationService = notificationService;
    }

    @Tool(
        name = "getOrderStatus",
        description = """
            Xem trạng thái một đơn khi có mã đơn chính xác.
            Chỉ đọc; không hủy, sửa hoặc gửi thông báo.
            """)
    public OrderStatusDto getOrderStatus(
            @ToolParam(description = "Mã đơn chính xác") String orderNumber,
            ToolContext context) {

        CallerContext caller = requireCaller(context);
        return orderService.findVisibleOrder(caller, orderNumber);
    }

    @Tool(
        name = "sendOrderUpdate",
        description = """
            Gửi thông báo về trạng thái một đơn đã xác định.
            Có side effect; cần quyền, xác nhận và idempotency.
            """,
        requiresConfirmation = true)
    public NotificationReceipt sendOrderUpdate(
            @ToolParam(description = "Mã đơn chính xác") String orderNumber,
            @ToolParam(description = "Kênh gửi: EMAIL hoặc APP") String channel,
            ToolContext context) {

        CallerContext caller = requireCaller(context);
        return notificationService.sendAuthorizedOnce(
                caller, orderNumber, channel);
    }
}
~~~

`requiresConfirmation = true` chỉ dùng trực tiếp khi dependency có Tool Call Confirmation (Spring AI **2.1.0+**). Phiên bản cũ cần approval gate của ứng dụng. Dù có confirmation, callback/service vẫn phải kiểm tra caller, tenant, trạng thái đơn, recipient allowlist và idempotency key. Không đưa `tenantId`, `isAdmin` hoặc quyền do model tự khai báo vào arguments.

Để tái lập đúng behavior, kèm snapshot tool definitions và schema trong evidence. Đổi description/schema có thể làm model chọn tool khác dù Java method không thay đổi.

## 10. Fixture và expected outcomes phải độc lập với model

Dữ liệu tổng hợp mẫu:

~~~json
{
  "fixtureVersion": "orders-synthetic-v1",
  "tenant": "repro-tenant-a",
  "orders": [
    {
      "orderNumber": "ORD-REPRO-001",
      "status": "DELIVERED",
      "shipmentReference": "SHIP-REPRO-001"
    },
    {
      "orderNumber": "ORD-REPRO-002",
      "status": "NEW",
      "shipmentReference": null
    }
  ],
  "users": [
    {
      "subjectId": "repro-user-a",
      "capabilities": ["order:read", "order:notify"]
    },
    {
      "subjectId": "repro-readonly",
      "capabilities": ["order:read"]
    }
  ],
  "notificationGateway": {
    "mode": "sandbox",
    "recipient": "synthetic-recipient@example.test",
    "sendsBeforeApproval": 0
  }
}
~~~

**Không dùng địa chỉ/email/số điện thoại thật** trong fixture. Domain `example.test` dùng cho dữ liệu minh họa; khi dùng sandbox gateway thực, cần dùng recipient test được nhà cung cấp cấp phép. Điều kiện “đơn đã giao” phải được xác minh tại service ở thời điểm gửi, không chỉ dựa vào chuỗi trong prompt.

Expected outcomes:

| Case | Caller / yêu cầu | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- | --- |
| C01 | Xem `ORD-REPRO-001` | `getOrderStatus` trả `DELIVERED` | Spy + fixture DB |
| C02 | Xem đơn tenant khác | `RESOURCE_UNAVAILABLE`, không lộ dữ liệu | Query tenant filter + policy |
| C03 | Yêu cầu gửi nhưng chưa duyệt | `WAITING_APPROVAL`, 0 send | Paused reply + gateway ledger |
| C04 | User đủ quyền duyệt | Một notification được gửi/chấp nhận theo contract | Ledger + operation ID |
| C05 | User chỉ có quyền đọc cố gửi | `DENIED`, 0 send | Policy record + no outbound call |
| C06 | Approval gửi lại hai lần | Không có side effect thứ hai | Idempotency store/unique constraint |
| C07 | Provider trả 503 | Retry giới hạn, thông báo lỗi an toàn | Stub fault injection + attempts |
| C08 | Tool arguments sai schema | Validation error, không gọi service | Schema assertions + spy |
| C09 | Model không cần tool | Không gọi tool | Callback counter 0 |
| C10 | Hết model/tool budget | Dừng có reason code, không loop vô hạn | Metrics + bounded calls |

Bộ C01–C10 nên có cả happy path, negative path, retry và sự cố thật sự. Mỗi case phải chỉ rõ **expected tool actions** lẫn **expected business state**. Khi model trả lời bằng một câu hợp lý nhưng ledger không đổi, case C04 vẫn FAIL.

## 11. Kiểm thử deterministic: làm bằng chứng nền

Unit/contract tests nên chứng minh các bất biến mà mô hình không thể bảo đảm:

- `getOrderStatus` chỉ đọc order trong tenant hiện hành.
- `sendOrderUpdate` bị từ chối khi thiếu `order:notify` hoặc khác tenant.
- Tool input sai định dạng/enum không tới service.
- `ToolContext` không có caller → fail closed.
- Một idempotency key/operation ID không thể gửi trùng side effect.
- Đổi quyền giữa approval và execution phải được recheck.
- Timeout/exception đã sanitize không lộ secret/PII.
- Callback tên khác với tool đã công bố không bị thực thi.
- Một tool call ID phải ghép đúng `ToolResponseMessage`.

Ví dụ test với gateway spy:

~~~java
@Test
void notificationMustNotSendWithoutAuthorization() {
    CallerContext readonly = new CallerContext(
            "repro-readonly", "repro-tenant-a", "req-001");

    assertThatThrownBy(() -> notificationService.sendAuthorizedOnce(
            readonly, "ORD-REPRO-001", "EMAIL"))
            .isInstanceOf(AccessDeniedException.class);

    verifyNoInteractions(sandboxNotificationGateway);
}
~~~

Test này chỉ chứng minh service từ chối trước khi gọi gateway khi policy deny. Cần test repository/database riêng để chứng minh query tenant predicate và idempotency thực sự hoạt động. Tránh mock toàn bộ policy rồi kết luận đã kiểm thử authorization ở production topology.

Bằng chứng L0/L1 có thể là report JUnit XML, test name, assertion outcome, commit SHA và sanitized application logs. Đừng copy/đổi tên report của một bản build khác rồi dùng làm bằng chứng của run hiện tại.

## 12. Kiểm thử live model: bật có chủ ý và giới hạn rõ

Một test với provider thật nên tách riêng khỏi unit tests. JUnit 5 hỗ trợ điều kiện môi trường:

~~~java
@Tag("live-ai")
@EnabledIfEnvironmentVariable(
        named = "RUN_LIVE_AI_TESTS",
        matches = "true")
@SpringBootTest
@ActiveProfiles("repro-sandbox")
class LiveOrderToolSelectionIT {

    @Autowired ChatModel chatModel;
    @Autowired SandboxOrderTools tools;

    @Test
    void modelShouldLookUpExactOrderBeforeAnswering() {
        ChatClient client = ChatClient.builder(chatModel).build();

        String answer = client.prompt()
                .user("Trạng thái đơn ORD-REPRO-001 là gì?")
                .tools(tools)
                .toolContext(Map.of(
                        "caller", new CallerContext(
                                "repro-user-a",
                                "repro-tenant-a",
                                "live-case-001")))
                .call()
                .content();

        assertThat(tools.invokedOrderNumbers())
                .contains("ORD-REPRO-001");
        assertThat(answer).isNotBlank();
    }
}
~~~

`SandboxOrderTools` là bean/test fixture do người học viết với counter thread-safe; `answer.isNotBlank()` chỉ kiểm tra có output, **không chứng minh output đúng nghiệp vụ**. Cần thêm assertion dựa trên DTO/expected facts và đánh giá semantic nếu có yêu cầu về ngôn ngữ. Spring AI `Evaluator`/`EvaluationRequest` có thể hỗ trợ đánh giá, nhưng LLM-as-judge không nên dùng để quyết định kiểm thử quyền hoặc bằng chứng side effect.

Khi `RUN_LIVE_AI_TESTS` không bật, báo `NOT_RUN (skipped by gate)`. Nếu có key nhưng endpoint sai hoặc production URL lọt vào cấu hình, dừng trước network call. Với streaming, assert tool execution và terminal response chứ không đòi số chunks cố định.

## 13. Thu thập bằng chứng tại từng điểm kiểm soát

Một bộ evidence tối thiểu nên gắn với cùng `runId`/`operationId`, nhưng bảo vệ những ID nhạy cảm:

~~~mermaid
sequenceDiagram
    actor U as Caller
    participant C as ChatController
    participant AI as ChatClient / Model
    participant T as ToolCallback
    participant P as Policy / Approval
    participant S as Business Service
    participant G as Sandbox Gateway
    U->>C: User turn (case C04)
    C->>AI: Prompt + tools + trusted ToolContext
    AI-->>C: Tool call name + callId + arguments
    C->>P: Confirm required? Authz?
    P-->>C: APPROVED decision / audit ID
    C->>T: Resume allowed tool call
    T->>S: Validate tenant, operation key
    S->>G: Send sandbox notification
    G-->>S: notificationId + SENT/QUEUED
    S-->>T: NotificationReceipt
    T-->>AI: Tool result with original callId
    AI-->>C: Final response
    C-->>U: Câu trả lời đúng trạng thái
~~~

Cần thu được **sự kiện độc lập** ở ít nhất bốn vị trí:

1. **Model request/response metadata:** model ID, tool name, tool call ID, số model rounds (không log raw sensitive prompts).
2. **Tool callback:** được gọi/không được gọi, schema validation, duration, outcome, error code.
3. **Policy/approval:** người quyết định đã xác thực, tài nguyên/action, timestamp, policy version, approved/denied.
4. **Business/gateway:** mã giao dịch sandbox, idempotency key, trạng thái thực và thời điểm commit/ack.

Nếu dùng `returnDirect=true`, kết quả tool có thể trả trực tiếp cho caller mà không đi thêm một model round; tài liệu phải ghi rõ con đường đó. Nếu một reply có nhiều tool calls, đừng đánh đồng thứ tự callback hoàn tất với thứ tự tool-call ID gốc.

## 14. Đọc kết quả confirmation đúng API Spring AI 2.1

Khi tool có `requiresConfirmation=true`, `ToolCallingAdvisor` dừng vòng trước khi thực thi **bất kỳ tool call nào của cùng model reply**. Không dùng `.content()` để phát hiện pause vì văn bản có thể rỗng:

~~~java
ChatResponse reply = chatClient.prompt()
        .user("Gửi thông báo cho đơn ORD-REPRO-001")
        .call()
        .chatResponse();

List<String> awaiting =
        ToolCallDecisions.awaitingDecision(reply);

if (!awaiting.isEmpty()) {
    AssistantMessage message = reply.getResult().getOutput();

    // Application: lưu reply + prompt/tool definitions trong trusted store.
    // Hiển thị action/resource đã chuẩn hóa tới người có quyền duyệt.
    approvalStore.persistPending(
            operationId, reply,
            ToolCallDecisions.toolCallKeys(message));
}
~~~

Sau đó application nhận quyết định từ authenticated approver, không nhận lại raw tool call từ client. `ToolCallDecisions.of(...)` phải có **một decision cho mọi call trong reply**, kể cả call policy không yêu cầu xác nhận. `ToolCallingManager.executeToolCalls(prompt, reply, decisions)` chạy các call được cho phép; trước khi gọi, service kiểm tra quyền, resource state và idempotency lần nữa. Resume không tự chống replay; application phải ghi quyết định nguyên tử.

Bằng chứng case C03: saved paused response + confirmation record + **gateway send count = 0**. Bằng chứng case C04: allowed decision trong trusted store + callback/service audit + gateway ledger/operation ID. Không đánh dấu C04 PASS chỉ vì người dùng đã bấm “Cho phép”.
## 15. Viết REPRODUCE.md: trình tự chạy lại từ máy sạch

Một tài liệu tái lập phải có **lệnh, nơi chạy, điều kiện đầu vào, kết quả kỳ vọng và nơi lưu bằng chứng**. Chỉ viết “clone repo, cấu hình DB, chạy test” là chưa đủ.

Bước đề xuất:

| Bước | Người thực hiện | Điều kiện PASS | Evidence |
| --- | --- | --- | --- |
| R1 — Checkout | Developer/operator | Đúng commit, không có thay đổi ngoài ý muốn | Git SHA, dirty state |
| R2 — Xác minh runtime | Developer/operator | Java/Gradle/Boot/AI versions đúng manifest | Runtime/build version |
| R3 — Xác minh scope | Operator | Profile sandbox, tenant, allowlist đúng | Sanitized preflight report |
| R4 — Seed dữ liệu | Test runner | Fixture đúng version, hai tenant cách ly | Fixture hash, row counts |
| R5 — Unit/contract | CI/test runner | L0 PASS, không phụ thuộc provider thật | JUnit XML |
| R6 — Integration | CI/test runner | L1 PASS, callback/DB/queue đúng | Test report, trace stub |
| R7 — Live opt-in | Authorized runner | L2/L3 trong sandbox và budget | Live run report |
| R8 — Đối soát | Operator | Tool records khớp sandbox ledger | Audit/ledger comparison |
| R9 — Dọn dẹp | Operator | Không còn dữ liệu tạm ngoài phạm vi | Cleanup manifest |
| R10 — Ký/đóng gói | Release owner | Manifest và hashes khớp, không lộ secret | Evidence index |

Ví dụ trình tự cho hệ thống có Gradle Wrapper. **Chạy các lệnh này trong project capstone riêng ở môi trường được cấp phép**, không phải trong folder bài học của worker:

~~~bash
# 1. Lấy đúng source (thay placeholder theo project).
git clone <APP_REPOSITORY_URL>
cd order-assistant-capstone
git checkout <PINNED_COMMIT_SHA>
git rev-parse HEAD
git status --porcelain

# 2. Xác minh runtime và dependency đã pin.
java -version
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath

# 3. Chạy suite deterministic, không cần provider key.
./gradlew clean test

# 4. Chỉ sau khi L0/L1 PASS, chạy live suite theo profile opt-in
# trong CI job đã được cấp phép; không bật ở laptop mặc định.
RUN_LIVE_AI_TESTS=true SPRING_PROFILES_ACTIVE=repro-sandbox \
  ./gradlew liveTest
~~~

`liveTest` ở đây là task **do dự án tự cấu hình**; một project chỉ có Gradle plugin mặc định thường không có task này. Nếu chưa khai báo custom source set/test task, thay bằng task JUnit đã được cấu hình lọc tag `live-ai`. Không tuyên bố lệnh chạy được chỉ nhờ copy đoạn Markdown này.

Trên Windows, dùng `gradlew.bat` hoặc `.\gradlew.bat` theo shell, và cung cấp biến môi trường qua CI secret injection/PowerShell scope. Không hardcode API key vào command line vì có thể lưu trong shell history/CI log.

Khi `git status --porcelain` khác rỗng, ghi các thay đổi có chủ đích hoặc dừng; tuyệt đối không coi một source tree không xác định là bằng chứng tái lập của commit đã pin.

## 16. Chạy thử một lượt API và đối chiếu trạng thái thật

Nếu project cung cấp REST API riêng cho capstone, quy trình thử nghiệm có thể là:

~~~http
POST /api/assist
Authorization: Bearer <sandbox-user-token>
Content-Type: application/json

{
  "conversationId": "repro-conversation-001",
  "message": "Xem đơn ORD-REPRO-001 và đề xuất gửi cập nhật qua email"
}
~~~

Dự kiến response cho turn **đang chờ quyết định** do API ứng dụng định nghĩa:

~~~json
{
  "operationId": "op-example-001",
  "status": "WAITING_APPROVAL",
  "pendingAction": "sendOrderUpdate",
  "resourceReference": "ORD-REPRO-001",
  "requiresAuthorizedApprover": true
}
~~~

**Đây là payload minh họa contract**, không phải một response thực đã thu thập. Không sao chép mã JWT, email người dùng hoặc raw paused reply ra report công khai.

Bước xác nhận có thể thông qua endpoint ứng dụng:

~~~http
POST /api/approvals/<approval-id>/decisions
Authorization: Bearer <sandbox-approver-token>
Content-Type: application/json

{
  "decision": "APPROVE",
  "expectedVersion": 1
}
~~~

Backend phải tra bản paused reply **đã lưu trong trusted store**, kiểm tra approver/tenant, hạn, version và quyền hiện hành, rồi resume bằng quyết định cho từng call. Frontend chỉ gửi quyết định/approval ID; không gửi JSON tool arguments gốc để thực thi.

Sau bước này, query sandbox ledger bằng API riêng có quyền để kiểm tra `operationId`, `notificationId`, timestamp, status và số lần gửi. Với HTTP POST bị timeout, chỉ trả “trạng thái chưa xác định” nếu chưa có đối soát; **không** cho model tự khẳng định `SENT`.

Kịch bản cần lưu ba checkpoint: trước approval, ngay sau approved decision và sau khi gateway/worker báo terminal. Chúng giúp phân biệt “đã duyệt” với “đã gửi”.

## 17. Định nghĩa một “evidence artifact” đủ sức đối chứng

Mỗi artifact nên có metadata:

~~~json
{
  "artifactId": "E-C04-LEDGER",
  "runId": "repro-example-001",
  "caseId": "C04",
  "kind": "sandbox-ledger-verification",
  "source": "sandbox-notification-gateway",
  "captureMethod": "authorized-read-only-query",
  "capturedAtUtc": null,
  "status": "NOT_CAPTURED",
  "contentSha256": null,
  "storageRef": null,
  "redactionApplied": false
}
~~~

Trường `status: NOT_CAPTURED` và giá trị `null` có chủ đích: ví dụ này **không phải bằng chứng đã chạy**. Khi thực thi, một collector có kiểm soát mới điền timestamp, SHA-256, storage reference, verdict và chữ ký nếu quy trình yêu cầu.

Những dạng bằng chứng có giá trị:

- **Build/test:** JUnit XML và summary, dependency lock, commit SHA, container image digest.
- **Model/tool:** model operation metadata, tool name, tool-call ID, arguments-schema fingerprint, callback invocation count, stop reason.
- **Approval:** approval ID/version, người duyệt đã xác thực (trong audit hạn chế quyền), decision, timestamp và thời hạn.
- **Business:** sandbox ledger/repository state trước–sau, idempotency record và notification gateway acknowledgment.
- **Vận hành:** health/metrics snapshot, trace links, cảnh báo/thời gian xử lý incident, rollback drill.
- **Cleanup:** fixture resources đã xóa hoặc reset đúng scope, log không còn giữ credential.

Bằng chứng có thể **âm tính**: case “tool không được chạy trước duyệt” phải có callback/gateway invocation count = 0. Không nên chỉ dựa vào việc thiếu log; log có thể mất. Dùng spy/counter/ledger truy vấn độc lập kết hợp với audit state.

## 18. Bảng nối từng tiêu chí với nguồn bằng chứng

| Tiêu chí | Quan sát cần thu | Đối chứng độc lập | Verdict |
| --- | --- | --- | --- |
| Tool được chọn đúng | `getOrderStatus` trong model reply hoặc spy | Golden routing expectation | PASS/FAIL |
| Schema hợp lệ | DTO parse và validation không lỗi | Schema snapshot + validator | PASS/FAIL |
| Không thực thi trước approval | Callback send count = 0 | Sandbox ledger không có send | PASS/FAIL |
| Sau approval có một send hợp lệ | Operation ID và receipt | Gateway ledger count = 1 | PASS/FAIL |
| Replay không gửi trùng | Hai quyết định, một side effect | Unique idempotency record | PASS/FAIL |
| Cross-tenant không lộ dữ liệu | Resource unavailable / deny code | Repository tenant predicate test | PASS/FAIL |
| Error không chứa secrets | Sanitized code/message | Canary secret scan trên tool result/log | PASS/FAIL |
| Tái lập đúng môi trường | Commit/dependency/model manifest | CI runner report và checksum | PASS/FAIL |
| Runbook hoạt động | Operator làm drill đúng steps | Drill record + timer/audit | PASS/FAIL |

Chỉ ghi **PASS** khi điều kiện đã chạy và có ít nhất một nguồn bằng chứng đúng. Ghi **FAIL** khi assertion/đối soát sai, **NOT_RUN** khi chưa chạy, **BLOCKED** khi không thể thử vì thiếu môi trường/quyền, **INCONCLUSIVE** khi bằng chứng thiếu hoặc dữ liệu bất định. Đừng gộp bốn trạng thái này thành PASS.

Bộ chấp nhận capstone có thể cho phép live model bị `NOT_RUN` trong nhánh học tập offline, nhưng khi nộp bằng chứng “đã kiểm chứng trên provider thật”, các case tương ứng phải có actual run record. Chính sách release phải ghi rõ tầng L0–L4 nào là bắt buộc.

## 19. Chống sửa đổi và rò rỉ khi lưu bằng chứng

Bằng chứng cần đồng thời **toàn vẹn** và **an toàn dữ liệu**.

1. Ghi các sự kiện có thời gian UTC, run ID và trace ID.
2. Tách raw artifacts ở vùng truy cập hạn chế với sanitized derivatives dành cho nhóm xem báo cáo.
3. Loại/mã hóa access token, API key, cookie, Authorization header, email/số điện thoại và raw tool args nhạy cảm.
4. Không dùng request/tenant/user ID làm label metric có cardinality cao; dùng trace/audit được phân quyền.
5. Tính SHA-256 **sau khi redaction** trên đúng bản sanitized được bàn giao, và ghi rõ thuật toán.
6. Nếu cần lưu chứng cứ thô cho audit, quản lý retention, mã hóa, quyền truy cập và chính sách xóa riêng.
7. Giữ manifest danh sách file: path, content hash, size, timestamps, source, owner và verdict.
8. Không “sửa” file log sau khi đã ký hash; nếu có redaction bổ sung, tạo artifact phiên bản mới và cập nhật chain of custody.

Ví dụ lệnh kiểm tra hash trên Linux/macOS sau khi collector đã tạo artifacts trong project:

~~~bash
sha256sum evidence/<run-id>/manifest.json
sha256sum evidence/<run-id>/sanitized-tool-events.jsonl
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "evidence\<run-id>\manifest.json"
Get-FileHash -Algorithm SHA256 -LiteralPath "evidence\<run-id>\sanitized-tool-events.jsonl"
~~~

Không ký/hàm băm dữ liệu chưa được phân loại nhạy cảm rồi gửi artifact gốc cho người không được quyền. Hash giúp phát hiện sửa đổi, **không tự chứng minh nội dung là đúng**; điều đó cần kết quả chạy và đối chiếu độc lập.

## 20. Mẫu EVIDENCE.md và báo cáo cuối

Một kết quả chạy nên có bảng:

| Case | Mode | Model ID | Tool | Actual vs expected | Business proof | Status |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | stub | scripted-v1 | getOrderStatus | Chưa chạy | Chưa thu | NOT_RUN |
| C02 | stub | scripted-v1 | getOrderStatus | Chưa chạy | Chưa thu | NOT_RUN |
| C03 | stub | scripted-v1 | sendOrderUpdate | Chưa chạy | Chưa thu | NOT_RUN |
| C04 | sandbox | Chưa xác định | sendOrderUpdate | Chưa chạy | Chưa thu | NOT_RUN |

Bảng ở đây **chỉ minh họa định dạng**, không đại diện cho một run. Trong báo cáo thật, bắt buộc ghi đường dẫn evidence, timestamp, source commit và người xác minh.

Ví dụ cấu trúc báo cáo machine-readable:

~~~json
{
  "runId": "repro-example-001",
  "status": "NOT_RUN",
  "suite": "capstone-order-assistant-v1",
  "manifestRef": "manifest.json",
  "cases": [
    {
      "id": "C03",
      "expected": {
        "approvalState": "WAITING_APPROVAL",
        "sendsBeforeApproval": 0
      },
      "actual": null,
      "verdict": "NOT_RUN",
      "evidenceRefs": []
    },
    {
      "id": "C04",
      "expected": {
        "gatewaySendCount": 1
      },
      "actual": null,
      "verdict": "NOT_RUN",
      "evidenceRefs": []
    }
  ],
  "assertionsPassed": 0,
  "assertionsFailed": 0,
  "assertionsNotRun": 2,
  "notes": "Sample schema only; no execution performed"
}
~~~

Tính *completion rate* bằng số case đáp ứng **business acceptance assertions** chia cho case đã được đánh giá, kèm số case `NOT_RUN/BLOCKED/INCONCLUSIVE`. Không tính `NOT_RUN` là PASS; cũng không bỏ các case thất bại ra khỏi mẫu số chỉ vì provider trả kết quả không mong muốn.

## 21. Hiệu năng, chi phí và độ tin cậy trong bộ bằng chứng

Capstone không chỉ kiểm tra “đúng hay sai” mà còn phải đặt câu hỏi “đạt ở mức tài nguyên nào”:

| Chỉ số | Ý nghĩa | Nguồn |
| --- | --- | --- |
| User turn duration p50/p95 | Thời gian cảm nhận ở API | Application timer |
| Model calls per turn | Số model rounds do vòng tool tạo ra | `gen_ai.client.operation` + turn correlation |
| Tool invocations per turn | Callback thực thi | `spring.ai.tool` + app counter |
| Invalid argument rate | Lỗi schema/validation | Validation records |
| Tool technical error rate | Exceptions/timeouts | Spring AI observations |
| Business failure rate | `DENIED/FAILED/PARTIAL` | Service outcome |
| Completion rate | Case đạt business assertions | Evaluation report |
| Input/output token usage | Token do provider báo | Model response metadata |
| Estimated cost | Giá tham chiếu x tokens/tool usage | Budget service; ghi phương pháp ước tính |
| Approval wait/expiry | Thời gian chờ con người | Approval store |
| Job queue age | Backlog tác vụ dài | Job store |
| Downstream error/retry | Tính ổn định khi dependency lỗi | HTTP client metrics |

Các tên metric của Spring AI có thể thay đổi theo version/exporter. Kiểm tra endpoint thực tế và dùng tên metric tương ứng; không hardcode một bảng PromQL của phiên bản khác rồi coi không có metric là lỗi hệ thống.

**Chú ý:** `ChatClient` duration có thể bao gồm advisor/model/tool thời gian lồng nhau; không cộng tất cả timer rồi gọi là total user latency. Cũng không coi tool trả `QUEUED` là công việc nền đã `SUCCEEDED`.

Ngân sách tối thiểu cho live suite: max cases, max model calls/turn, max tool calls/turn, provider timeout, backend timeouts, retry cap, concurrency cap và chi phí tối đa. Khi vượt budget, dừng có mã lý do, ghi `BUDGET_EXCEEDED` và không tiếp tục chạy để “đạt đủ điểm”.

## 22. Runbook vận hành — startup và kiểm tra sẵn sàng

Một runbook cần có các bước **người trực vận hành** làm được, kể cả khi không phải tác giả code.

### 22.1 Trước khi bật traffic

1. Kiểm tra version của artifact/image và manifest; khác version đã kiểm thử → STOP.
2. Xác minh secret manager, endpoint provider, sandbox/production mode và outbound allowlist.
3. Kiểm tra DB migrations, kết nối queue/object storage và role/policy của service account.
4. Xác minh tool catalog không trùng tên, schema/description hash tương ứng bản release.
5. Xác minh `ToolCallingAdvisor` được đăng ký đúng một lần; không có hai tool advisors hoặc resolver fallback vô ý.
6. Kiểm tra confirmation policy và approver channel cho tool có side effect.
7. Kiểm tra quota/model call limits, retry/backoff/deadline, circuit breaker và kill switch.
8. Bật health/metrics/tracing đã redaction; xác minh collector/exporter có nhận tín hiệu.
9. Chạy smoke test đọc dữ liệu tổng hợp, không side effect.
10. Nếu có side-effect smoke test, dùng resource riêng của sandbox/staging, có cleanup và ledger đối chứng.

### 22.2 Health, readiness, liveness

| Kiểm tra | Liveness | Readiness | Không nên làm |
| --- | --- | --- | --- |
| JVM/web app còn chạy | Có | Có | Gọi model tốn tiền ở mỗi liveness probe |
| DB chính còn kết nối | Không nhất thiết | Thường có | Cho app healthy nếu không xử lý nổi yêu cầu |
| Queue/outbox dispatcher | Không nhất thiết | Theo khả năng degradation | Coi mất queue là “thành công” cho tool async |
| AI provider | Tránh gọi thường xuyên | Dùng synthetic probe tần suất thấp/circuit state | Dùng production customer prompt làm probe |
| Tool catalog/schema | Không cần probe mạng liên tục | Validate startup và version | Bật fallback resolver rộng để né lỗi |
| Notification gateway | Không nhất thiết | Theo feature flag/capability | Gửi email thật để kiểm tra readiness |

Thiết kế degradation: nếu AI provider lỗi, API có thể trả thông báo không khả dụng; nếu công cụ ghi lỗi, ứng dụng có thể cho phép các tool đọc tiếp tục **chỉ khi policy cho phép**. Không tuyên bố tính năng gửi thông báo đã sẵn sàng nếu gateway không hoạt động.

## 23. Runbook vận hành — giám sát và ca trực

Người trực nên có dashboard tối thiểu:

- Lưu lượng user turns, model rounds/turn, tool calls/turn.
- ChatClient/model/tool p50/p95 và dependency p95/timeout.
- Lỗi phân loại `MODEL_PROVIDER_ERROR`, `SCHEMA_INVALID`, `AUTH_DENIED`, `TOOL_NOT_FOUND`, `DOWNSTREAM_TIMEOUT`.
- Tỷ lệ hoàn tất mục tiêu người dùng, không chỉ HTTP 200.
- Pending approval count/age/expired, job queue depth/age.
- Idempotency deduplication events, replay attempts và abnormal side-effect attempts.
- Chi phí/usage theo model, budget còn lại và rate-limit saturation.
- Catalog/version distribution giữa replicas; tool-name collision counter.

Đặt ngưỡng SLO **từ dữ liệu thật và mức độ rủi ro**; ví dụ “p95 user turn dưới 5 giây cho tác vụ chỉ đọc” chỉ là mục tiêu gợi ý, không phải con số bắt buộc của Spring AI. Với tool side effect, *không thực thi trái phép* phải là invariant chặn tuyệt đối, không dựa trên ngưỡng tỷ lệ lỗi thấp.

Mẫu nhật ký điều hành:

~~~text
RUNBOOK CHECK
Time (UTC): <timestamp>
Release: <artifact-digest>
Catalog: <catalog-version>
Provider/model: <provider-id/model-id>
Turn p95: <observed> / SLO <target>
Tool error rate: <observed> / threshold <target>
Pending approvals: <observed>, oldest <duration>
Queue backlog: <observed>, oldest <duration>
Budget usage: <observed> / limit <limit>
Decision: CONTINUE | DEGRADE | PAUSE_WRITES | ROLLBACK
Operator: <authorized-operator>
Evidence refs: <trace/metrics/ticket>
~~~

Không lưu credentials hoặc raw tool arguments ở bản nhật ký phát cho nhóm rộng.

## 24. Runbook xử lý sự cố: phân loại, khoanh vùng, đối soát

| Triệu chứng | Khả năng cao | Bước đầu tiên |
| --- | --- | --- |
| Model không gọi tool cần thiết | Tool definition không được công bố, schema/prompt, provider behavior | Kiểm tra catalog + raw tool-call metadata có kiểm soát |
| Wrong tool/callback | Tên trùng, resolver fallback, index stale | Tắt tool rủi ro; đối chiếu requested vs resolved |
| Tool arguments sai | Model/schema mismatch, stale contract | Reject validation; không thực thi |
| Tool timeout/503 | Dependency/provider quá tải | Circuit breaker, rate limit, backoff, trace |
| Approval không thể tiếp tục | Paused reply thiếu/trùng decision, hết hạn, quyền đổi | Đối chiếu trusted store/decision keys |
| Mô hình trả “đã gửi” nhưng ledger không có | Hallucination, callback chưa chạy, job mới queued | Kiểm tra audit/gateway status; sửa response |
| Gửi thông báo trùng | Replay, retry hoặc lỗi idempotency | Tạm dừng write, đối soát ledger/operation ID |
| Rò rỉ dữ liệu tenant | Authorization/filter sai | Chặn khả năng truy cập, bảo toàn chứng cứ, xử lý incident |
| Trace mất tool span | Context propagation, observability disabled | Kiểm tra exporter, async propagation, sampling |
| Chi phí tăng đột biến | Tool loop chạy lặp, retry storm, model thay đổi | Giới hạn tool/model calls, dừng suite nếu cần |

Quy trình incident:

1. **Xác định ảnh hưởng**: feature nào, từ lúc nào, tenant/phạm vi nào và có side effect chưa.
2. **Chặn tác động tiếp diễn**: kill switch cho tool ghi, giảm concurrency, rút token có nguy cơ lộ hoặc chặn egress khi cần.
3. **Bảo toàn bằng chứng**: commit/digest, trace/audit events, catalog version, operation IDs; redaction trước chia sẻ.
4. **Đối soát nghiệp vụ**: hỏi gateway/ledger/DB độc lập; không suy diễn từ text mô hình.
5. **Phân loại lỗi**: provider, prompt/tool selection, schema, authorization, callback, external service, orchestration/history hay data.
6. **Khắc phục có test hồi quy**: sửa đúng lớp nguyên nhân, kiểm thử negative case trước khi bật lại.
7. **Khôi phục có kiểm soát**: canary, xác nhận metrics/safety invariants, rồi mới tăng traffic.
8. **Post-incident**: ghi thời gian, root cause, dữ liệu ảnh hưởng, hành động giảm thiểu và owner/công việc phòng tái diễn.

Khi có sai lệch dữ liệu, không xóa audit hoặc “sửa trực tiếp” trạng thái ledger để báo cáo trở thành PASS. Giữ chuỗi bằng chứng và xử lý bù trừ theo quy trình nghiệp vụ được phê duyệt.

## 25. Runbook rollback và khôi phục trạng thái

Rollback model/prompt/tool catalog khác rollback database/side effects:

| Thành phần | Có thể rollback đơn giản? | Lưu ý |
| --- | --- | --- |
| Prompt/template | Thường có | Giữ version để tái lập |
| Model ID/options | Tùy provider/model còn sẵn | Backend behavior vẫn có thể thay đổi |
| Tool descriptions/schema | Có nếu versioned | Cẩn thận paused calls theo schema cũ |
| Callback Java code | Có qua artifact rollback | Phải tương thích DB migrations |
| Catalog/tool-search cache | Cần invalidate/rebuild | Không dựa vào TTL để thu hồi quyền |
| Approval state | Không tự rollback tùy ý | Không resume nhầm quyết định đã xử lý |
| Sent notification | Thường **không thể unsend** | Đối soát hoặc compensation theo nghiệp vụ |
| DB migration | Tùy migration | Dùng backup/forward-fix nếu downgrade không an toàn |

Các bước:

1. Đóng tạm write-capability hoặc chuyển thành read-only mode.
2. Xác nhận ảnh hưởng và chụp snapshot state phục vụ điều tra.
3. Chọn artifact/model/catalog version đã được phê duyệt; kiểm tra compatibility với DB/schema.
4. Deploy rollback qua canary, invalidate caches và kiểm tra các replica cùng version.
5. Kiểm tra các approval/job đang dở: resume theo schema/tool definitions gốc được phép hoặc từ chối an toàn, không chạy callback đã bị thay đổi semantics.
6. Đối soát side effects đã commit; nếu notification đã gửi, chỉ gửi thông báo sửa sai khi policy cho phép, không giả là đã “hoàn tác”.
7. Chạy smoke tests read-only và negative authorization tests.
8. Tăng traffic khi metrics/SLO ổn định, ghi kết quả rollback drill/ticket.

**Không** dùng rollback như cách xóa bỏ dấu vết của tool call sai. Mọi quyết định vận hành cần audit và liên kết với run/incident ID.

## 26. Kiểm thử runbook bằng game day/rehearsal

Một runbook chỉ được viết mà chưa ai thử làm theo có rủi ro bỏ sót quyền, command hoặc đường dẫn. Tổ chức **diễn tập có kiểm soát** trên staging/sandbox:

| Drill | Cách gây lỗi an toàn | Kỳ vọng |
| --- | --- | --- |
| D01 — Provider outage | Stub model 503 hoặc chuyển test gateway sang unavailable | Circuit breaker/degrade, không loop vô hạn |
| D02 — Tool collision | Inject hai callbacks tên trùng vào test context | Fail startup/request, không thực thi tool |
| D03 — Approval expired | Dùng test clock đưa pending approval quá TTL | `EXPIRED`, 0 send |
| D04 — Duplicate decision | Submit cùng decision/idempotency key hai lần | Một transition, không double send |
| D05 — Tenant mismatch | Caller tenant A tra đơn tenant B | Deny và không rò rỉ thông tin |
| D06 — Gateway timeout after commit | Fake gateway commit rồi làm mất response | Trạng thái UNKNOWN/đối soát, không gửi lại bừa |
| D07 — Budget exceeded | Giảm max tool/model calls trong harness | Dừng có reason code, không tăng chi phí tiếp |
| D08 — Catalog rollback | Đổi tool description/schema trong test snapshot | Cache được làm mới, request an toàn |
| D09 — Worker crash | Dừng worker sandbox sau enqueue | Job được recover/đối soát theo idempotency |
| D10 — Evidence store outage | Chặn collector test | Không báo “verified PASS” khi thiếu proof bắt buộc |

Với D06, dùng **fake/sandbox gateway**; không cố tình tạo giao dịch thật để mô phỏng mất kết nối. Diễn tập phải ghi người thực hiện, môi trường, bước đã làm, timestamps, metric trước/sau, actual verdict và cải tiến runbook. Đừng coi “có checklist” là đã xác nhận recovery.

## 27. Trách nhiệm và quy trình phê duyệt bàn giao

Một bảng RACI ngắn làm rõ ai chịu trách nhiệm khi capstone chuyển sang vận hành:

| Công việc | Developer | Test/Eval owner | Security owner | SRE/Operator | Business owner |
| --- | --- | --- | --- | --- | --- |
| Pin code/dependencies và tool contracts | R | C | C | I | I |
| Thiết kế golden cases, fixture, assertions | C | R | C | I | C |
| Kiểm tra tenant, approval, PII, secrets | R | C | A | C | C |
| Quản lý sandbox credentials, rollout | C | C | C | R | I |
| SLO, alerts, incident/rollback | C | C | C | R | A/C |
| Ký xác nhận nghiệp vụ và hạn mức | C | C | C | C | A |
| Thu thập evidence và xác minh verdict | R | A/R | C | C | I |

`R`: thực hiện; `A`: chịu trách nhiệm phê duyệt; `C`: tham vấn; `I`: được thông báo. Vai trò cụ thể cần chỉnh theo tổ chức; bảng không cấp quyền thực thi ngoài chính sách authentication/authorization.

Trước khi bàn giao, ít nhất người vận hành và người duyệt nghiệp vụ phải biết:

- Cách tắt tool ghi, tạm dừng live tests và nhận diện provider outage.
- Cách xem chính xác trạng thái `WAITING_APPROVAL/QUEUED/SUCCEEDED/FAILED`.
- Cách phân biệt dữ liệu mô hình với nguồn nghiệp vụ.
- Cách lấy evidence mà không làm lộ secret/PII.
- Cách rollback và đối soát side effects không thể hoàn tác.
- Cách mở incident/escalation và liên hệ owner nếu vượt thời hạn xử lý.

## 28. Tiêu chí chấm bài capstone

Có thể dùng rubric với trọng số tham khảo:

| Tiêu chí | Trọng số gợi ý | Điều kiện bắt buộc |
| --- | ---: | --- |
| Tái lập source/build/env | 15% | Commit/dependency/profile/fixture rõ |
| Đúng tool contract/loop | 15% | Tool name/schema/context/historical messages chuẩn |
| Authorization/confirmation/idempotency | 20% | Không side effect trước quyền và approval |
| Bằng chứng execution độc lập | 20% | Test report + trace/audit + gateway/DB proof |
| Regression/evaluation có mẫu số | 10% | Positive/negative cases, kết quả không bị “làm đẹp” |
| Runbook/observability/rollback | 15% | Startup, metrics, incident, rollback, rehearsal |
| Bảo mật và lưu trữ evidence | 5% | Secret/PII redaction, integrity/retention |

Điều kiện **không thể bù điểm**: có truy cập chéo tenant, side effect trái phép, key thật bị lộ hoặc làm giả bằng chứng PASS. Những lỗi này phải BLOCK/FAIL bất kể điểm phần khác. Ngược lại, một live provider suite ghi `NOT_RUN` minh bạch có thể phù hợp bài tập offline nhưng **không** đủ bằng chứng cho yêu cầu release có L3 bắt buộc.

Rubric chỉ là mẫu; chủ sở hữu nghiệp vụ/security cần phê duyệt tiêu chí và SLO thật của dự án.

## 29. Bảng kiểm bàn giao cuối cùng

- [ ] Có mục tiêu, phạm vi và kiến trúc luồng `ChatClient → ToolCallingAdvisor → ToolCallback → service`.
- [ ] Có commit SHA, Java/Boot/AI versions, provider/model/options và dependency lock.
- [ ] Có tool catalog names/descriptions/schema/version và owner được xác thực.
- [ ] Có fixture tổng hợp, tenant A/B, expected outcomes và cơ chế reset sạch.
- [ ] Có test L0/L1 deterministic, cùng báo cáo PASS/FAIL thật.
- [ ] L2/L3 chỉ chạy khi opt-in với sandbox, network allowlist và budget.
- [ ] Có các case đọc, ghi sau duyệt, từ chối, replay, invalid schema, timeout, cross-tenant.
- [ ] Có bằng chứng model đề xuất tool và callback thực thi đúng tên/arguments.
- [ ] Có audit của approver và đối soát sandbox ledger độc lập với model text.
- [ ] Có phân biệt `SENT` với `QUEUED`, `APPROVED` với `SUCCEEDED`.
- [ ] Có run ID, timestamp UTC, case ID, artifact source, SHA-256 và manifest.
- [ ] Bằng chứng có redaction, phân quyền, retention và chain of custody phù hợp.
- [ ] Báo cáo phân biệt `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`.
- [ ] Có metrics/tracing, SLO, tool/model-call budgets và cảnh báo chi phí.
- [ ] Có health/readiness và runbook startup, triage, incident, rollback, đối soát.
- [ ] Có diễn tập ít nhất các lỗi provider, approval, double side effect, quyền và rollback.
- [ ] Có owner, đường escalation và người chấp thuận phạm vi production.
- [ ] Có giới hạn đã biết, test không chạy và backlog kỹ thuật ghi minh bạch.

## 30. Những lỗi bàn giao thường gặp và cách sửa

| Lỗi | Hậu quả | Sửa bằng |
| --- | --- | --- |
| “Dùng Spring AI mới nhất” | Không biết API nào đã test | Pin version + lockfile + commit |
| “Run project, xem UI” | Không có expected outcome | Fixture/golden cases |
| Screenshot chatbot nói “đã gửi” | Không chứng minh side effect | Gateway ledger/operation ID |
| Log thô có Authorization header | Rò rỉ bí mật | Redaction + restricted raw store |
| Live suite mặc định chạy mọi PR | Mất quota/chi phí, rủi ro side effect | Tag/opt-in/sandbox hard gate |
| Chỉ test happy path | Không phát hiện bypass quyền/replay | Negative/idempotency suite |
| Ghi `QUEUED` là completed | Sai tỷ lệ hoàn tất | Terminal job records |
| Lấy ID từ model để cấp quyền | Cross-tenant/data leak | Trusted `ToolContext` + service policy |
| Coi LLM-as-judge là chứng cứ security | Có thể chấm nhầm | Deterministic assertions |
| Không lưu manifest/evidence hash | Khó đối chiếu sau release | Immutable versioned evidence |
| Có dashboard mà không có runbook | Operator không biết làm gì khi báo động | SOP/incident drills |
| Rollback code rồi coi side effect biến mất | Giao dịch ngoài hệ thống vẫn tồn tại | Reconciliation/compensation |

## Tài liệu tham khảo

- [Spring AI — Tool Calling và ToolContext](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — ToolCallingAdvisor, vòng lặp và lịch sử tool responses](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI — Tool Call Confirmation (2.1.0+)](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI — Evaluation Testing và Evaluator](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html)
- [Spring Boot — Testing with Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Actuator Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [JUnit — Conditional Test Execution](https://junit.org/junit5/docs/current/user-guide/#extensions-conditions)
- [OpenTelemetry — Semantic Conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Kết luận:** một capstone Spring AI Tool Calling được bàn giao tốt không chỉ “chat có câu trả lời”. Người khác phải có thể kiểm tra đúng source và phiên bản, dựng môi trường an toàn, chạy cùng fixture, thấy **mô hình đề xuất gì và ứng dụng thực thi gì**, đối chiếu side effect từ service/sandbox, rồi làm theo runbook khi gặp sự cố. Bằng chứng chỉ được gọi là bằng chứng thực thi sau khi kiểm thử thật sự chạy và được ghi lại; tài liệu minh họa hoặc kết quả `NOT_RUN` không được giả thành PASS. Khi reproduction guide, evidence index và operating runbook gắn với cùng version/run ID, hệ thống có nền tảng để kiểm thử hồi quy, vận hành và cải tiến mà không hy sinh quyền truy cập, tính toàn vẹn dữ liệu hoặc khả năng truy cứu trách nhiệm.
