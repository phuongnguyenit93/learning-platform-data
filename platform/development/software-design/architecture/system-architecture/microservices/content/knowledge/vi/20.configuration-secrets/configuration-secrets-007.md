# Cờ tính năng và thay đổi hành vi độc lập với triển khai

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Cấu hình và bí mật.  
> **Mục tiêu:** hiểu cách dùng **feature flags** để bật, tắt hoặc điều chỉnh hành vi của microservice mà không cần build và triển khai lại mã nguồn cho từng thay đổi; triển khai theo nhóm người dùng, theo dõi rủi ro và thu hồi có kiểm soát.

## 1. Vì sao cần tách triển khai khỏi phát hành tính năng?

Trong hệ thống microservices, một thay đổi thường đi qua nhiều bước: phát triển, kiểm thử, build image, triển khai, khởi động và kiểm tra sức khỏe. Nếu mỗi lần muốn bật một chức năng đều phải triển khai thêm một phiên bản, nhóm vận hành phải gắn quyết định **khi nào đưa code lên môi trường** với quyết định **ai được dùng chức năng và lúc nào**.

Ví dụ **Order Service** có thuật toán tính chiết khấu mới. Code đã vượt qua kiểm thử và được triển khai trên 20 pod, nhưng doanh nghiệp muốn mở cho nhân viên nội bộ, sau đó 5% khách hàng và cuối cùng toàn bộ hệ thống. Triển khai lại tất cả pod cho mỗi bước làm tăng rủi ro, thời gian và việc phối hợp.

**Feature flag** giải quyết bài toán bằng cách đặt một quyết định runtime tại điểm rẽ hành vi:

- Code của cả đường **cũ** và **mới** đã có trong bản triển khai.
- Một cơ chế cấu hình hoặc dịch vụ đánh giá flag cho biết request hiện tại được phép đi theo đường nào.
- Có thể tăng tỷ lệ người dùng, giới hạn theo tenant, dừng phát hành hoặc chuyển về đường cũ mà không cần thay binary.
- Mỗi thay đổi được đo đạc và có người chịu trách nhiệm.

Tách biệt hai sự kiện:

- **Deployment:** đưa phiên bản phần mềm lên môi trường.
- **Release/activation:** quyết định lúc nào và cho đối tượng nào tính năng có hiệu lực.

Một flag chỉ thay đổi hành vi **đã tồn tại trong code đang chạy**. Nó không thể tự thêm code chưa triển khai, tự khôi phục schema bị xóa, thu hồi giao dịch đã hoàn thành hoặc làm cho hai phiên bản không tương thích trở nên tương thích.

## 2. Feature flag là gì?

**Feature flag**, còn gọi là **feature toggle**, là một chính sách được đánh giá tại runtime để chọn một biến thể hành vi. Flag đơn giản nhất có hai giá trị:

- **OFF:** dùng đường hành vi hiện hành/ổn định.
- **ON:** dùng hành vi mới.

Thực tế một flag có thể có nhiều biến thể như **legacy**, **new-v1**, **new-v2**, hoặc giá trị tham số được kiểm soát như giới hạn page size. Điều quan trọng là **định nghĩa ý nghĩa nghiệp vụ** của từng biến thể trước khi bật.

~~~mermaid
flowchart LR
    C[Client] --> G[API Gateway]
    G --> O[Order Service]
    O --> F{Evaluate new-discount-engine}
    F -->|OFF| L[Legacy discount policy]
    F -->|ON| N[New discount policy]
    L --> R[Order response]
    N --> R
    CTRL[Flag control plane] -->|config snapshot / push| SDK[Flag SDK / cache]
    SDK --> F
~~~

Thành phần thường gặp:

1. **Flag definition:** tên, loại, biến thể, mô tả, default, owner và thời hạn dự kiến.
2. **Targeting rule:** môi trường, nhóm người dùng, tenant, region, điều kiện thuộc tính và percentage rollout.
3. **Evaluation context:** chủ thể và thông tin tối thiểu cần thiết để chọn biến thể.
4. **Control plane:** nơi người có quyền thay đổi chính sách và lưu lịch sử.
5. **Runtime client/SDK:** lấy cấu hình, giữ snapshot/cache và đánh giá flag trong ứng dụng.
6. **Telemetry/audit:** ghi việc thay đổi chính sách, sử dụng biến thể, số liệu nghiệp vụ và lỗi.

Không có nghĩa mọi hệ thống đều cần mua nền tảng flag riêng. Một ứng dụng nhỏ có thể đọc cấu hình từ một kho quản lý tập trung; hệ thống lớn cần targeting, cache, audit, phân quyền thay đổi và kiểm soát rollout tốt hơn.

## 3. Cờ tính năng khác gì so với cấu hình và bí mật?

| Khái niệm | Mục đích chính | Ví dụ | Cách quản lý |
| --- | --- | --- | --- |
| **Cấu hình thông thường** | Tham số vận hành hoặc thiết lập môi trường | Connection timeout, endpoint, pool size | Versioned config hoặc config service, kiểm tra hợp lệ |
| **Feature flag** | Chọn hành vi hoặc đối tượng được trải nghiệm | Bật thuật toán giảm giá mới cho 10% user | Targeting, rollout, audit, đo lường, có kế hoạch dọn dẹp |
| **Secret** | Dữ liệu xác thực hoặc mã hóa cần giữ kín | API key, DB password, signing key | Secret manager, encryption, least privilege, rotation |
| **Quyền truy cập** | Xác định người dùng/workload có được thao tác tài nguyên | User A được xem order của A | Authorization policy bắt buộc tại service/data layer |

Một flag có thể được lưu trong hệ thống cấu hình, nhưng **quy trình thay đổi flag** thường cần linh hoạt hơn vì nó trực tiếp ảnh hưởng luồng nghiệp vụ và cohort người dùng.

**Không lưu secret trong flag payload, targeting context, SDK phía client hoặc response trả về browser.** Một số nền tảng phát flag cho frontend; mọi cấu hình ở client phải được coi là có thể bị người dùng xem và thay đổi.

**Feature flag không thay thế authorization.** Ẩn nút “Admin” sau flag chỉ cải thiện trải nghiệm; API vẫn phải kiểm tra token, role, ownership, tenant và chính sách truy cập, kể cả khi người dùng tự gọi endpoint.

## 4. Các nhóm feature flag và vòng đời

### 4.1. Release flag

Dùng để triển khai code trước, sau đó cho phép nhóm người dùng được chọn trải nghiệm tính năng. Ví dụ **new-checkout-flow** bật cho nhân viên trước khi mở toàn bộ traffic.

Đặc trưng: thời gian tồn tại ngắn đến trung bình. Khi tính năng ổn định và được phát hành 100%, nên bỏ điều kiện và xóa đường cũ theo kế hoạch.

### 4.2. Experiment flag

Dùng để so sánh các biến thể của một giả thuyết, chẳng hạn giao diện A/B. Cần **phân nhóm ổn định, đo exposure đúng, chỉ số kết quả, guardrail và tiêu chí dừng**. Không thay đổi quy tắc phân nhóm tùy tiện giữa chừng vì làm sai kết quả.

Đừng coi việc chạy A/B test đồng nghĩa với có thể mở behavior thay đổi tiền, quyền hoặc dữ liệu mà chưa có kiểm soát nghiệp vụ.

### 4.3. Operational flag / kill switch

Cho phép giảm tải hoặc tắt phần xử lý phụ khi gặp sự cố. Ví dụ **enable-recommendations** hoặc **enable-bulk-imports** để bảo vệ checkout trước một dependency suy giảm.

Kill switch chỉ hiệu quả nếu hệ thống nhận được giá trị mới đủ nhanh, nhánh OFF thực sự an toàn và không có tác vụ đã khởi chạy nằm ngoài khả năng điều khiển.

### 4.4. Permissioning/entitlement flag

Bật chức năng dựa trên gói dịch vụ, tenant hoặc hợp đồng, chẳng hạn chỉ tenant doanh nghiệp được dùng API export. Có thể tồn tại lâu dài.

Cần phân biệt **entitlement** (người dùng có quyền theo hợp đồng) và **security authorization** (được phép trên tài nguyên cụ thể). Nếu entitlement là điều kiện bắt buộc, service phải thực thi bằng chính sách tin cậy phía server, không dựa vào frontend toggle.

### 4.5. Configuration/parameter flag

Chọn một tham số đã được giới hạn, ví dụ **max-page-size** có các biến thể 50, 100, 200. Phải có kiểu dữ liệu, miền giá trị, schema và validation. Không chấp nhận một số bất kỳ chỉ vì control plane trả về.

### 4.6. Phân loại theo tuổi thọ

- **Transient:** cờ phát hành tạm thời, có owner và ngày dự kiến xóa.
- **Long-lived:** cờ điều hành hoặc entitlement có lý do tồn tại lâu dài, vẫn cần review định kỳ.
- **Expired/stale:** cờ không còn biến thể thực sự hoặc không còn được đọc. Cần dọn để tránh tích lũy technical debt.

Mỗi flag nên được tạo cùng với **kế hoạch xóa hoặc lý do duy trì**. Một nhánh ON/OFF tồn tại mãi làm tăng không gian trạng thái, rủi ro test và độ khó đọc code.

## 5. Thiết kế một flag đủ rõ để vận hành

Ví dụ bản mô tả cho cờ chọn chính sách chiết khấu:

~~~yaml
key: checkout.discount-engine-v2
description: "Enable new discount calculation policy for eligible checkout requests"
type: release
owner: checkout-team
environments:
  production:
    defaultVariation: legacy
    rules:
      - match: internal-testers
        variation: v2
      - match: stable-percentage-cohort
        percentage: 5
        variation: v2
    fallbackVariation: legacy
rollout:
  guardrails:
    - checkout_error_rate
    - price_mismatch_count
    - p95_checkout_latency
  rollbackTarget: legacy
lifecycle:
  removeAfter: "post-rollout-cleanup"
~~~

Đây là **cấu trúc mô tả minh họa**, không phải schema mặc định của một sản phẩm flag cụ thể. Khi triển khai cần map sang SDK/nền tảng đã chọn.

Những thông tin nên có:

- **Key duy nhất, có namespace rõ:** ví dụ checkout.discount-engine-v2.
- **Mục đích và tiêu chí thành công:** thay đổi hành vi nào, đo bằng gì.
- **Default/fallback an toàn:** khi chưa nhận rule hoặc evaluation thất bại.
- **Owner và approver:** ai được sửa rollout, ai phản ứng khi xảy ra sự cố.
- **Environments:** development, staging, production; mặc định không tự đồng bộ ON giữa môi trường.
- **Targeting:** dùng thuộc tính có nguồn xác thực đáng tin và quy tắc phân nhóm ổn định.
- **Dependencies:** các phiên bản service/schema, endpoint hoặc dữ liệu nào phải sẵn sàng.
- **Cleanup trigger:** khi nào xóa cờ, code legacy và cấu hình thừa.

Tên cờ thể hiện **điều kiện có ý nghĩa**. Tránh tên mơ hồ như tempFix1, newFeature hoặc toggle123.

## 6. Luồng đánh giá flag trong một request

Một quy trình điển hình:

1. Service đã có **snapshot cấu hình** được kiểm soát và kiểm chứng kiểu.
2. Request đi qua authentication và lấy **subject/tenant context** từ identity đáng tin.
3. Tại một điểm rẽ được định nghĩa rõ, ứng dụng gọi **flag evaluator** cùng context tối thiểu.
4. Evaluator trả **variation**, **revision** và tùy chọn **reason** (target rule, default, fallback).
5. Service **đóng băng quyết định cho request hoặc transaction** khi cần nhất quán; không đánh giá lại giữa chừng chỉ vì snapshot được cập nhật.
6. Service chạy đường code tương ứng và phát telemetry; sau cùng trả response hoặc xử lý exception theo contract.
7. Khi flag bị thay đổi, các instance nhận snapshot mới theo cơ chế push/poll/cache đã cấu hình.

Một flag không nên được gọi như remote HTTP request cho **mỗi lần kiểm tra trong mỗi request** nếu điều đó biến service flag thành dependency đồng bộ nằm trên critical path. Phổ biến hơn là client dùng snapshot local được cập nhật nền hoặc cache có giới hạn.

### 6.1. Client-side versus server-side evaluation

| Vị trí đánh giá | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- |
| **Server-side SDK** | Giữ rule nhạy cảm bên server, gắn với identity, phù hợp nghiệp vụ | Cần quản lý snapshot, cache, đồng bộ đa instance |
| **Gateway-level evaluation** | Chính sách route chung và canary traffic | Không thay thế quyết định sâu trong domain service |
| **Browser/mobile SDK** | Cập nhật UI nhanh, giảm gọi server cho trình bày | Flag và context có thể bị quan sát/sửa; không dùng làm security boundary |
| **Batch/consumer evaluation** | Có thể kiểm soát workflow mới trên message | Phải giữ quyết định ổn định qua retry/replay |

Nếu rule dùng thông tin nhạy cảm, ưu tiên đánh giá phía server hoặc chỉ gửi kết quả tối thiểu tới client.

## 7. Targeting: bật tính năng cho đúng đối tượng

Cách phổ biến:

- **Allowlist nội bộ:** email hoặc user ID nhân viên đã được xác minh, dành cho thử nghiệm sớm.
- **Tenant/organization:** mở cho khách hàng thí điểm được chọn theo contract.
- **Region:** chọn vùng địa lý triển khai, chú ý pháp lý, độ trễ và hạ tầng riêng theo region.
- **Application version:** chỉ bật nếu mobile app hoặc client hỗ trợ protocol mới.
- **Percentage rollout:** bật cho phần trăm chủ thể ổn định.
- **Attribute rules:** ví dụ plan, loại account hoặc nhu cầu use case; thuộc tính phải có nguồn tin cậy.

**Không tin thuộc tính targeting do client tự khai** nếu nó ảnh hưởng chi phí, dữ liệu hoặc quyền. Ví dụ header X-Tenant-Plan: enterprise do client gửi không đủ để quyết định entitlement.

### 7.1. Percentage rollout cần phân nhóm ổn định

Bật “10% traffic” không có nghĩa mỗi request có 10% xác suất ON bằng cách gọi random. Nếu random mỗi request, cùng một user có thể thấy hai hành vi khác nhau trong cùng session, gây kết quả khó kiểm soát.

Một kỹ thuật là **deterministic bucketing**:

1. Chọn khóa chủ thể ổn định như subjectId đã xác thực hoặc tenantId.
2. Kết hợp với flag key và salt/version ổn định.
3. Hash thành bucket cố định, ví dụ 0 đến 9.999.
4. Với rollout 10%, ON cho bucket 0–999.
5. Tăng lên 20% sẽ bao gồm nhóm 10% cũ nếu các quy tắc không đổi.

**Lưu ý thiết kế:** 10% user không bảo đảm 10% request. Nếu một số user phát sinh traffic lớn hơn nhiều, cần đo tải thực tế theo request, tenant hoặc workload. Bật theo **tenant** cũng có thể tạo bước tăng tải rất lớn khi một tenant lớn chuyển sang ON.

~~~mermaid
flowchart TD
    X[subjectId + flagKey + salt] --> H[Hash ổn định]
    H --> B[Bucket 0 đến 9999]
    B --> C{Bucket nhỏ hơn ngưỡng?}
    C -->|Có| V2[variation v2]
    C -->|Không| OLD[variation legacy]
~~~

Cùng một key và context phải trả cùng biến thể trong khi chính sách chưa đổi. Khi thay đổi salt/hash algorithm, cohort có thể đảo; cần tránh nếu cần rollout tăng dần ổn định.

### 7.2. Ví dụ Java 21: bucketing ổn định

Đây là thuật toán minh họa để hiểu nguyên lý. Trong sản phẩm thật nên ưu tiên SDK đã được kiểm chứng, đồng thời giữ ổn định thuật toán và encoding qua các ngôn ngữ service.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class PercentageRollout {
    private PercentageRollout() {}

    // Bật cho percentage phần trăm chủ thể.
    public static boolean enabled(
            String flagKey,
            String subjectId,
            String salt,
            int percentage
    ) {
        if (percentage < 0 || percentage > 100) {
            throw new IllegalArgumentException("percentage must be 0..100");
        }
        if (percentage == 0) {
            return false;
        }
        if (percentage == 100) {
            return true;
        }
        if (flagKey == null || flagKey.isBlank()
                || subjectId == null || subjectId.isBlank()) {
            return false; // Ví dụ mặc định an toàn khi thiếu identity.
        }

        String stableKey = flagKey + "|" + salt + "|" + subjectId;

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(stableKey.getBytes(StandardCharsets.UTF_8));
            long first64Bits = ByteBuffer.wrap(digest).getLong();
            long bucket = Long.remainderUnsigned(first64Bits, 10_000L);
            return bucket < percentage * 100L;
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Mọi instance dùng cùng flagKey/salt/subjectId sẽ ra quyết định giống nhau. Với percentage=10, các bucket 0–999 trả true. Phép modulo tạo sai lệch thống kê cực nhỏ nếu dùng nguồn hash 64 bit đều; với yêu cầu phân nhóm thử nghiệm nghiêm ngặt, dùng quy tắc bucketing của nền tảng thống nhất.

**Không đưa secret, password hay PII không cần thiết vào chuỗi hash.** Nếu subjectId là dữ liệu nhạy cảm, có thể dùng định danh nội bộ/pseudonymous ổn định và quản lý quyền đọc context. Salt ở đây phục vụ tách cohort; không được coi mặc nhiên là cơ chế bảo mật mật mã.

## 8. Cài đặt tại ranh giới nghiệp vụ trong Spring Boot

Ví dụ **Order Service** muốn chọn cách tính giá sau giảm giá. Quyết định phải nhất quán xuyên suốt một request để không báo tổng tiền theo v2 nhưng ghi cơ sở tính tiền theo legacy.

Xây dựng abstraction:

~~~java
public record FlagContext(
    String subjectId,
    String tenantId,
    String environment
) {}

public record FlagDecision(
    String variation,
    String revision,
    String reason
) {}

public interface FeatureFlagEvaluator {
    FlagDecision evaluate(String flagKey, FlagContext context);
}
~~~

Service đánh giá một lần rồi truyền quyết định xuống domain operation:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final String DISCOUNT_FLAG =
        "checkout.discount-engine-v2";

    private final FeatureFlagEvaluator flags;
    private final DiscountEngine legacyEngine;
    private final DiscountEngine newEngine;
    private final CheckoutRepository repository;

    public CheckoutService(
            FeatureFlagEvaluator flags,
            DiscountEngine legacyEngine,
            DiscountEngine newEngine,
            CheckoutRepository repository
    ) {
        this.flags = flags;
        this.legacyEngine = legacyEngine;
        this.newEngine = newEngine;
        this.repository = repository;
    }

    public CheckoutResult checkout(CheckoutCommand command, FlagContext context) {
        FlagDecision decision = flags.evaluate(DISCOUNT_FLAG, context);

        DiscountEngine engine = switch (decision.variation()) {
            case "v2" -> newEngine;
            case "legacy" -> legacyEngine;
            default -> legacyEngine;
        };

        PriceQuote quote = engine.quote(command);

        // Ghi version/decision cần thiết vào record giao dịch.
        // Không tính lại theo một lần evaluate khác trong cùng transaction.
        return repository.createCheckout(
            command,
            quote,
            decision.variation(),
            decision.revision()
        );
    }
}
~~~

Các interface **DiscountEngine**, **CheckoutRepository**, **CheckoutCommand**, **CheckoutResult** và **PriceQuote** là thành phần domain được minh họa; cần hiện thực và kiểm soát transaction theo hệ thống thực tế.

Điểm quan trọng:

- **Một quyết định cho một transaction:** nếu snapshot thay đổi giữa tính giá và thanh toán, không được âm thầm đổi engine.
- **Default legacy có chủ đích:** chỉ đúng khi hành vi legacy còn an toàn và tương thích. Không dùng mặc định đó cho mọi loại flag.
- **Giá cuối cùng do server tính:** flag chỉ chọn thuật toán đã được kiểm thử; không chấp nhận tổng tiền do client khai.
- **Persist decision metadata** khi cần đối soát, hỗ trợ khách hàng, xử lý idempotency và kiểm tra tranh chấp.
- **Không tự retry bằng engine khác** sau khi đã có side effect (đã giữ hàng, ghi order hoặc bắt đầu thanh toán). Việc chuyển nhánh ở giữa giao dịch có thể tạo sai lệch trạng thái.

Controller gọi service với **FlagContext** được xây dựng từ principal/tenant đã xác thực và cấu hình môi trường, không từ header tùy ý do client kiểm soát.

### 8.1. Feature flag provider và cache

Evaluator có thể được triển khai bằng SDK của một nền tảng quản lý flag, hoặc một provider nội bộ:

~~~java
public interface FlagSnapshotProvider {
    FlagSnapshot currentSnapshot();
}

public interface FlagSnapshot {
    FlagDecision resolve(String flagKey, FlagContext context);
}
~~~

Đây là pseudocode có hình thức Java. Provider cần thực thi **snapshot nhất quán**, không đọc nhiều phiên bản rule không đồng bộ. Các chi tiết về polling/streaming, storage, auth và metrics thuộc adapter hạ tầng, tách khỏi domain service.

## 9. Luồng phát hành an toàn: từ OFF đến 100%

Một quy trình rollout mẫu:

| Giai đoạn | Targeting | Mục tiêu |
| --- | --- | --- |
| 0. Deploy dark | OFF với khách hàng; có thể ON trong test | Đưa code mới lên mọi instance an toàn |
| 1. Internal | Nhân viên/tenant test | Kiểm tra hành vi thật với dữ liệu kiểm soát |
| 2. Canary | 1% hoặc vài tenant nhỏ | Quan sát lỗi và hiệu năng trên traffic thực |
| 3. Mở rộng | 5% → 10% → 25% → 50% | Xác nhận guardrail qua từng bước |
| 4. General availability | 100% đối tượng đủ điều kiện | Tính năng trở thành đường hành vi chuẩn |
| 5. Cleanup | Xóa flag và legacy khi đủ điều kiện | Giảm nhánh code và nợ kỹ thuật |

Tỷ lệ trên chỉ minh họa, không phải quy tắc bắt buộc. Với một tính năng nhạy cảm như tính tiền hoặc cấp quyền, nên dùng cohort có thể đối soát, giới hạn blast radius và tiêu chí chấp nhận nghiêm ngặt hơn.

**Mỗi bước tăng rollout là một thay đổi vận hành có rủi ro.** Tăng 5% lên 10% thường an toàn hơn nhảy thẳng 5% lên 100%, nhưng quyết định phải dựa trên metric, traffic và đặc tính failure mode.

### 9.1. Guardrails trước khi tăng tỷ lệ

Định nghĩa trước các ngưỡng như:

- Tỷ lệ request lỗi 5xx và tỷ lệ thất bại nghiệp vụ.
- p95/p99 latency, timeouts, saturation của thread/connection/CPU.
- Tỷ lệ tính giá bất thường, sai lệch giữa quote và charge.
- Số event lỗi, backlog consumer, DLQ và tỷ lệ giao dịch bị bỏ dở.
- Chỉ số sản phẩm như conversion, nhưng không đánh đổi tính đúng đắn hoặc bảo mật.

Cần **so sánh biến thể theo cohort** nếu có thể. Chỉ xem tổng số liệu có thể che giấu lỗi ở 5% người dùng bật v2.

### 9.2. Quy tắc dừng/rollback

Ví dụ:

- Nếu số lỗi tính giá > 0 đối với bất biến “tổng tiền đã cam kết phải khớp thanh toán”, dừng rollout và điều tra.
- Nếu checkout p95 tăng vượt ngân sách SLO ở cohort v2, giữ tỷ lệ hiện tại hoặc thu hồi theo runbook.
- Nếu dependency mới gây tăng timeout hàng loạt, chuyển cohort mới về legacy khi phương án fallback vẫn hợp lệ.

Ngưỡng cụ thể phải được phê duyệt theo nghiệp vụ, tải và SLO. **Rollback một flag không tự khôi phục các giao dịch hoặc dữ liệu đã thay đổi.**

## 10. Rollback, kill switch và giới hạn của việc tắt flag

Flag **OFF** có thể dừng các request tương lai đi vào đường mới nếu:

1. Tất cả instance nhận được thay đổi trong thời gian chấp nhận.
2. Các lời gọi hiện tại dùng quyết định nhất quán và có chính sách kết thúc.
3. Đường legacy vẫn tồn tại, chạy đúng với dữ liệu hiện tại.
4. Không có tác vụ nền hoặc consumer tiếp tục dùng phiên bản cũ của flag ngoài tầm kiểm soát.

Những việc **không thể hoàn tác chỉ bằng OFF**:

- Một email/SMS đã gửi.
- Một giao dịch thanh toán đã settle.
- Dữ liệu đã được ghi theo schema mới không thể đọc bởi code cũ.
- Sự kiện đã phát tới hệ thống bên ngoài hoặc consumer độc lập.
- Một quyền truy cập nhạy cảm đã được thực hiện.

Trong các trường hợp này cần compensation, reconciliation, data migration, trạng thái nghiệp vụ và vận hành thủ công phù hợp.

**Kill switch thật sự** phải được diễn tập: người trực vận hành có quyền đổi flag, cấu hình lan đến pod trong ngân sách thời gian, metrics xác nhận request mới đi nhánh OFF, và runbook giải quyết giao dịch đang xử lý.

Không thiết kế đường OFF mang nghĩa **bỏ qua kiểm tra bảo mật** hoặc **bỏ qua validation** để hệ thống “chạy được” trong sự cố.

## 11. Feature flags trong microservices: nhất quán xuyên service

Một người dùng đi qua Gateway → Order → Payment → Inventory. Nếu mỗi service tự đánh giá cùng một flag vào thời điểm khác nhau, sẽ có nguy cơ:

- Order chọn thuật toán v2 nhưng Payment xử lý theo contract legacy.
- Request đến hai replica khác nhau nhận snapshot chưa đồng bộ.
- Consumer xử lý message sau nhiều phút, khi cờ đã bị tắt.
- Retry của cùng giao dịch chạy sang biến thể khác.
- Một service đã triển khai v2 trong khi service khác chưa hỗ trợ.

Các cách xử lý:

### 11.1. Đặt flag tại đúng owner

Flag kiểm soát thuật toán tính giá nên do **checkout domain owner** chịu trách nhiệm. Đừng để các service tự diễn giải một flag toàn cục có tên chung nhưng ý nghĩa khác nhau.

### 11.2. Truyền decision hoặc contract version khi cần

Với thao tác xuyên service có tính nhất quán cao, service khởi tạo có thể xác định **contract version, calculation version hoặc workflow variant** rồi gửi thành field có kiểu rõ ràng trong request/event.

Phía nhận phải:

- Xác thực nguồn và quyền.
- Kiểm tra biến thể nằm trong tập version hỗ trợ.
- Áp dụng đúng contract và bảo vệ invariants.
- Không coi raw header hoặc variation do client tự cung cấp là nguồn tin cậy.

**Không truyền toàn bộ bộ rule hoặc secret flag context** qua message. Chỉ chia sẻ quyết định cần thiết cho xử lý.

### 11.3. Ghi version vào sự kiện và trạng thái bền vững

Ví dụ sự kiện phát ra:

~~~json
{
  "eventId": "ea90b153-0c65-4d67-a1a3-bf7197e46bd1",
  "eventType": "CheckoutConfirmed",
  "schemaVersion": 2,
  "orderId": "ORD-2026-0112",
  "pricingPolicyVersion": "discount-v2",
  "flagRevision": "discount-engine-r17",
  "occurredAt": "2026-11-12T02:00:00Z"
}
~~~

**Giá trị là minh họa.** Consumer dùng schemaVersion và pricingPolicyVersion theo contract nghiệp vụ; không bắt buộc consumer phải gọi lại feature flag service để “đoán” logic mà producer đã dùng.

### 11.4. Tránh cờ toàn cục cho một thay đổi liên service không tương thích

Nếu một flag bật protocol hoàn toàn mới cho toàn bộ cụm, nó có thể phá service chưa triển khai. Dùng **expand-contract migration** và khả năng tương thích giữa version trước khi bật flag:

1. Triển khai consumer đọc được cả dữ liệu/contract cũ và mới.
2. Triển khai producer có khả năng viết bản mới nhưng mặc định vẫn dùng bản cũ.
3. Bật producer mới cho cohort nhỏ, theo dõi.
4. Mở rộng và chuyển toàn bộ traffic khi tương thích được chứng minh.
5. Dọn field/code cũ sau khi xác nhận không còn consumer legacy.

Flag hỗ trợ **kiểm soát thứ tự đổi hành vi**, không thay thế versioning, schema migration hoặc contract testing.

## 12. Cấu hình, đồng bộ và failure mode của flag service

Một quyết định flag cần khả năng hoạt động kể cả khi control plane suy giảm. Một số mô hình:

| Mô hình | Ưu điểm | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Local config khi khởi động | Đơn giản, ít phụ thuộc runtime | Đổi flag thường cần restart/redeploy |
| Poll định kỳ | Có thể cache, hoạt động khi mất kết nối ngắn | Có độ trễ phản ánh config và tải lên control plane |
| Streaming/push | Thay đổi nhanh, hữu ích cho kill switch | Mất kết nối, duplicate/reordered updates |
| Sidecar/relay/cache | Giảm call trực tiếp từ nhiều service | Thành phần phụ và nguy cơ cache stale |
| Per-request remote evaluation | Chính sách đồng bộ tại một nơi | Latency và availability của flag service trên critical path |

### 12.1. Định nghĩa rõ stale/fallback policy

Nếu service flag không truy cập được:

- **Cờ release thông thường:** có thể dùng snapshot đã biết tốt gần nhất; khi khởi động mới thiếu snapshot, sử dụng default an toàn.
- **Cờ điều hành/kill switch:** độ trễ đồng bộ phải được đo; nếu outage khiến kill switch không thể cập nhật, cần đường điều khiển khẩn cấp đã được thiết kế trước.
- **Cờ liên quan quyền/entitlement:** không “fail open” để cấp thêm quyền. Authorization bắt buộc phải tiếp tục kiểm tra theo nguồn tin cậy.
- **Cờ chọn phương thức ghi dữ liệu:** lựa chọn fallback phải tương thích với trạng thái dữ liệu thực. Nếu đường legacy không đọc được dữ liệu mới, cần từ chối có kiểm soát thay vì tự chọn legacy.

Đặt một **maximum staleness** phù hợp từng loại flag. Không có một TTL chung đúng cho cả cờ giao diện và cờ giao dịch quan trọng.

### 12.2. Atomic snapshot và thứ tự cập nhật

Một bundle gồm nhiều rule hoặc các flag phụ thuộc nhau cần được phát hành dưới dạng snapshot có revision. Tránh đọc từng rule từ những thời điểm khác nhau rồi ghép thành cấu hình không tồn tại trong control plane.

Service cần:

- Chỉ thay snapshot sau khi đã parse, validate schema và kiểm tra version.
- Không áp dụng update cũ đè lên update mới.
- Giữ snapshot cũ hợp lệ khi bản cập nhật bị lỗi.
- Có log/metric thể hiện active revision và thời điểm cập nhật.
- Đánh giá flag trên một snapshot nhất quán trong phạm vi thao tác.

## 13. Phân quyền đổi flag và audit

Khả năng sửa flag trong production là **quyền thay đổi hành vi hệ thống**, gần với quyền triển khai. Người đổi cờ có thể khiến nhiều khách hàng dùng một đường code mới ngay lập tức.

Một hệ thống vận hành nên có:

- **Role-based access control:** phân quyền theo project, environment, loại flag và mức rủi ro.
- **Separation of duties:** với flag quan trọng, có thể yêu cầu review hoặc approval trước khi tăng rollout.
- **Audit trail:** ai tạo/sửa cờ, trước/sau là gì, thời điểm nào, lý do/change ticket và môi trường bị ảnh hưởng.
- **Emergency path:** có quyền tắt nhanh flag rủi ro và kiểm tra hiệu lực mà vẫn có log.
- **Least privilege:** application SDK có quyền **đọc/evaluate**, không được có quyền chỉnh rule production.
- **Secret separation:** SDK key hoặc token được lưu trong secret manager, rotation và giới hạn scope.
- **Environment isolation:** thao tác ở staging không được tự vô tình bật production.

Không ghi raw PII, access token, secret targeting hay nội dung nhạy cảm vào audit/event log. Lưu thông tin đủ để truy vết, có retention và access control phù hợp.

## 14. Đo lường hiệu quả theo biến thể

Chỉ biết flag ON hay OFF chưa đủ. Cần phân biệt:

1. **Assignment:** hệ thống quyết định user nằm trong cohort nào.
2. **Exposure:** user/request thực sự tiếp xúc và đi qua hành vi đó.
3. **Outcome:** kết quả nghiệp vụ và kỹ thuật sau exposure.

Ví dụ 10.000 user được assign vào v2 nhưng chỉ 1.000 người vào màn checkout; nếu đếm toàn bộ 10.000 là đã trải nghiệm, chỉ số A/B có thể bị méo.

Các tín hiệu nên theo dõi:

| Nhóm | Metric/event | Ý nghĩa |
| --- | --- | --- |
| Distribution | Tỷ lệ assignment theo variation | Targeting có đúng không |
| Actual exposure | Số request/user thực sự chạy v2 | Lưu lượng thay đổi thực |
| Technical health | 5xx, latency p95/p99, timeout, saturation | Phát hiện hồi quy kỹ thuật |
| Domain invariants | Sai lệch giá, duplicate charge, trạng thái đơn bất thường | Phát hiện sai nghiệp vụ |
| Product | Conversion, abandonment, engagement | Đánh giá mục tiêu phát hành/thí nghiệm |
| Operations | Config age, active revision, evaluation error/fallback | Quan sát hạ tầng flag |
| Control | Số lần thay rule, actor, thời gian propagation | Vận hành và tuân thủ thay đổi |

Dùng **flag key/variation/revision** có tập giá trị nhỏ trong metrics. Không đưa trực tiếp userId, email, orderId hoặc tenantId có cardinality lớn làm label Prometheus. Dữ liệu phân nhóm chi tiết có thể được ghi vào hệ thống event analytics đã có chính sách privacy và sampling.

### 14.1. Những sai lệch dễ gặp trong thử nghiệm A/B

- Người dùng bị chuyển biến thể giữa phiên làm nhiễu kết quả.
- Biến thể v2 có traffic địa lý khác A vì rule targeting; so sánh tổng thể không công bằng.
- Một user có nhiều thiết bị hoặc anonymous ID thay đổi, dẫn đến assignment không ổn định.
- Đổi tỷ lệ rollout trong khi đang đo mà không lưu mốc hoặc thiết kế phân tích.
- Chỉ xem conversion, bỏ qua p99 latency hoặc lỗi thanh toán hiếm nhưng nghiêm trọng.
- Không xác định **đơn vị ngẫu nhiên hóa** (user, tenant, device, request) phù hợp đơn vị tác động.

Feature flag cung cấp cơ chế phân nhóm; thiết kế thử nghiệm và diễn giải thống kê vẫn cần phương pháp riêng.

## 15. Vòng đời dọn cờ và kiểm soát nợ kỹ thuật

Nếu mỗi sprint thêm 5 flag mà không xóa, sau một năm service có nhiều nhánh phải hỗ trợ và nhiều tổ hợp khó kiểm thử. Với N flag độc lập có thể có tới **2^N tổ hợp trạng thái**, dù không phải mọi tổ hợp đều có thể xảy ra.

Đề xuất metadata và quy trình:

~~~yaml
flagKey: checkout.discount-engine-v2
owner: checkout-team
type: release
createdAt: "2026-10-01"
expectedReviewAt: "2026-12-01"
targetFinalVariation: v2
cleanupIssue: "CHK-482"
rollbackDependencies:
  - "legacy pricing must still read historical orders"
~~~

Đây là manifest minh họa. Khi v2 đã ổn định:

1. Xác nhận tất cả production instance và client/consumer liên quan hỗ trợ v2.
2. Xác nhận không còn cohort yêu cầu legacy và không có luồng lịch sử buộc giữ cách tính cũ.
3. Đưa quyết định v2 thành hành vi chuẩn trong code.
4. Xóa if/else cũ, rule và cấu hình flag không còn dùng.
5. Kiểm thử regression và triển khai cleanup.
6. Chỉ xóa cấu hình ở control plane sau khi chắc chắn không còn runtime/SDK cũ gọi flag; thứ tự tùy chính sách fallback.

Với operational flag dài hạn, có thể không xóa; nhưng phải định kỳ kiểm tra nhu cầu, owner, runbook, fallback và quyền thay đổi.

### 15.1. Dấu hiệu một flag đã “stale”

- Đã ON 100% nhiều tháng, không có kế hoạch cần OFF.
- Không còn đường code nào evaluate flag.
- Owner không còn rõ, release ticket đóng lâu nhưng chưa cleanup.
- Có thể xóa một biến thể mà không thay đổi behavior ở bất kỳ client nào đang chạy.
- Flag bị lưu trong dashboard nhưng không có usage/metrics.

Đừng tự động xóa cờ chỉ vì không thấy request trong 24 giờ; có workflow chạy hàng tháng hoặc thiết bị lâu không cập nhật.

## 16. Testing strategy cho feature flags

### 16.1. Unit test đường ON và OFF

Kiểm thử mỗi hành vi hợp lệ và bất biến nghiệp vụ:

- Legacy tạo đúng kết quả như trước.
- V2 tạo đúng kết quả với case thường và các boundary.
- Evaluation thất bại trả về fallback đúng contract.
- Không có nhánh nào bỏ qua authentication, authorization, validation.
- Request có cùng flag decision trong toàn transaction.

Ví dụ với stub evaluator:

~~~java
final class FixedFlagEvaluator implements FeatureFlagEvaluator {
    private final String variation;

    FixedFlagEvaluator(String variation) {
        this.variation = variation;
    }

    @Override
    public FlagDecision evaluate(String key, FlagContext context) {
        return new FlagDecision(variation, "test-revision", "test");
    }
}
~~~

Mỗi test ép variation rồi kiểm tra domain output. Không cần khởi chạy hệ thống flag production trong unit test để chứng minh routing đơn giản.

### 16.2. Contract/integration test

- Producer v2 với consumer cũ nếu cần duy trì backward compatibility.
- Event gửi khi ON, sau đó được xử lý khi OFF.
- Nhiều replica với snapshot revision không đồng bộ trong thời gian ngắn.
- Restart service khi control plane unreachable: fallback/snapshot đúng.
- DB migration đang ở trạng thái expand, write path cũ và mới cùng tồn tại.
- Retry và idempotency của giao dịch khi flag đổi giữa các lần gọi.
- Cache staleness, missing flag, biến thể không nhận diện và rule target sai kiểu.

### 16.3. Load/chaos test

- Bật v2 cho cohort tăng dần; quan sát CPU, connection pool, latency và downstream capacity.
- Mất control plane, mất mạng đến relay, nhận update lỗi hoặc update cũ.
- Kiểm tra kill switch có lan đến tất cả pod trong ngân sách thời gian.
- Thử request cao độ đồng thời khi phần trăm rollout thay đổi.
- Kiểm tra không có memory leak hoặc SDK evaluation tạo remote call trên hot path.

**Không cần test mọi 2^N tổ hợp** nếu N lớn. Ưu tiên các tổ hợp thực sự được phép theo dependency, cờ tương tác mạnh, ranh giới phiên bản, đường fallback và invariants quan trọng. Giảm số cờ đồng thời bằng cleanup và thiết kế ranh giới tốt.

## 17. Feature flags và CI/CD

Cấu trúc pipeline tham khảo:

~~~mermaid
flowchart LR
    CODE[Merge code mới] --> CI[Build + test]
    CI --> DEPLOY[Deploy code ON/OFF compatible]
    DEPLOY --> HEALTH[Health / contract checks]
    HEALTH --> ALLOW[Internal cohort]
    ALLOW --> CANARY[Canary rollout]
    CANARY --> FULL[Full rollout]
    FULL --> CLEAN[Remove temporary flag]
    OBS[Metrics + alert] --> CANARY
    OBS --> FULL
~~~

Đường phát hành an toàn thường cần:

- **Code đã triển khai trên toàn bộ target** trước khi cờ chọn v2, trừ khi gateway/routing có cơ chế bảo đảm request chỉ tới instance hỗ trợ v2.
- Build immutable image; thay đổi config/flag có audit riêng với code deployment.
- Có khả năng giữ deployment hiện tại và rollback riêng variation, khi backward compatibility cho phép.
- Đặt **release gate** dựa trên metric thực tế và phê duyệt thay đổi phù hợp mức rủi ro.
- Không coi flag ON là bằng chứng đủ để xóa ngay code cũ nếu vẫn còn consumer/client lâu chưa cập nhật.

**Dark launch** có thể chạy logic mới mà chưa ảnh hưởng user, nhưng phải cân nhắc chi phí và side effect. Chỉ được “shadow” tính toán thuần túy hoặc đường đi đã bảo đảm không ghi dữ liệu/gọi bên thứ ba; không gửi thanh toán thật hai lần để so sánh.

## 18. Thiết kế flag khi có thay đổi dữ liệu

Một nguy cơ lớn: cờ OFF không rollback được dữ liệu đã ghi theo định dạng mới.

### 18.1. Expand–migrate–contract

Giả sử muốn đổi order status từ một cột chuỗi sang một state machine mới:

1. **Expand:** bổ sung schema mới mà code cũ vẫn hoạt động; triển khai code đọc được cả hai representation.
2. **Migrate/backfill:** chuyển đổi dữ liệu, xử lý case lịch sử và kiểm tra tính nhất quán.
3. **Release flag:** bật đường ghi mới khi mọi consumer đã hỗ trợ.
4. **Observe:** đo độ lệch dữ liệu, consistency và lỗi theo variant.
5. **Contract:** khi mọi version cũ ngừng dùng, loại bỏ field hoặc đường ghi legacy theo migration có kế hoạch.

Không đặt flag ON ngay khi DB vừa có cột mới nếu các pod/consumer chưa hỗ trợ format đó.

### 18.2. State machine và dữ liệu lịch sử

Khi một order được tạo theo pricing policy v2, các lần hủy, hoàn tiền hoặc đối soát sau này phải dựa trên **giá trị đã cam kết và version phù hợp**, không được tính lại bằng variation hiện tại. Lưu thông tin cần thiết vào domain record hoặc event để tái dựng nghiệp vụ.

### 18.3. Side effect và “shadow traffic”

Nếu shadow path phát email, tạo hóa đơn hoặc ghi payment, đó không còn là thử nghiệm không ảnh hưởng. Thiết kế shadow bằng pure function, sandbox downstream hoặc ghi nhận kết quả so sánh không có side effect. Mọi thao tác ghi phải có idempotency và ownership rõ.

## 19. Cờ tính năng, canary deployment và blue-green deployment

| Cơ chế | Đơn vị điều khiển | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **Feature flag** | Người dùng, tenant, request hoặc biến thể nghiệp vụ | Bật/tắt đường code trong version đang chạy | Đòi hỏi hai nhánh tương thích, quản lý cờ |
| **Canary deployment** | Tỷ lệ request đến một tập instance/version | Kiểm tra binary mới với traffic nhỏ | Không nhất thiết giữ user ở cùng đường logic nếu route không sticky |
| **Blue-green deployment** | Chuyển traffic giữa hai môi trường/version | Đổi release và rollback infrastructure nhanh | Vẫn phải xử lý DB/schema compatibility |
| **Rolling deployment** | Thay từng instance dần | Triển khai không ngắt dịch vụ | Một thời gian có nhiều version đồng thời |

Các chiến lược kết hợp được. Ví dụ deploy rolling một build chứa v2 nhưng flag OFF; khi toàn bộ pod sẵn sàng, bật v2 cho cohort 1%, rồi tăng dần. Nếu muốn canary cả thay đổi runtime/JDK/dependency, chỉ flag logic có thể chưa đủ để thử rủi ro binary mới.

Cần kiểm tra tính tương thích khi có đồng thời **old instance + new instance**, **flag ON + OFF** và message trễ.

## 20. Các lỗi thiết kế phổ biến

### Lỗi 1: Dùng flag để bỏ qua bảo mật

Ví dụ: enable-auth=false hoặc skip-ownership-check=true được bật trong production để “giải quyết sự cố”.

**Hậu quả:** biến thao tác vận hành thành lỗ hổng truy cập. Authorization phải tồn tại độc lập với flag; các cờ dùng cho công cụ nội bộ vẫn phải được bảo vệ bằng identity và policy thật.

### Lỗi 2: Mỗi lần evaluate đều gọi remote

Request checkout phụ thuộc vào flag service ở mọi bước; khi flag service chậm, checkout cũng chậm.

**Hướng xử lý:** SDK local snapshot/cache, kiểm soát TTL, timeout, giới hạn tài nguyên và fallback có chủ đích.

### Lỗi 3: Random cho mỗi request

User thấy hành vi v2 khi xem giỏ nhưng legacy khi thanh toán, hoặc retry chạy sang thuật toán khác.

**Hướng xử lý:** deterministic subject bucketing, decision snapshot và persist version khi nghiệp vụ cần.

### Lỗi 4: Không giới hạn quyền chỉnh cờ

Bất kỳ developer nào cũng có thể bật v2 cho 100% traffic production, không có audit.

**Hướng xử lý:** RBAC, owner, approval cho thay đổi nhạy cảm, log actor/revision và emergency path.

### Lỗi 5: Tắt flag được coi như hoàn tác toàn bộ

Payment đã xử lý, event đã phát, database đã migrate; OFF không khôi phục được.

**Hướng xử lý:** ghi version vào state, idempotency, compensation, reconciliation và kế hoạch migration/rollback.

### Lỗi 6: Kết hợp quá nhiều flag không kiểm soát

Code có nhiều if lồng nhau, các biến thể mâu thuẫn và khó test.

**Hướng xử lý:** đặt một flag điều khiển một quyết định có ý nghĩa, định nghĩa dependencies rõ, có expiration và dọn release flag khi ổn định.

### Lỗi 7: Targeting dựa trên dữ liệu không đáng tin

Client tự gửi plan=enterprise để được bật nghiệp vụ đặc quyền.

**Hướng xử lý:** dùng identity/tenant attributes lấy từ nguồn server đã xác thực; enforcement vẫn ở authorization layer.

### Lỗi 8: Không quan sát được snapshot ở production

Một số pod chạy revision cũ nhưng dashboard chỉ hiển thị cờ “ON”.

**Hướng xử lý:** xuất active revision, config age, evaluation errors, propagation latency và metric theo variation.

### Lỗi 9: Flag drift giữa môi trường

Staging bật v2 nhưng production cùng tên flag lại có biến thể/config khác mà không biết.

**Hướng xử lý:** quản lý môi trường rõ ràng, review diff, quy trình promotion hoặc GitOps phù hợp, tránh đồng bộ tự động không kiểm soát.

### Lỗi 10: Cleanup quá sớm hoặc quá muộn

Xóa ngay OFF branch khi còn client cũ; hoặc để flag ON 100% nhiều năm.

**Hướng xử lý:** xác nhận deployment/consumer/contract compatibility rồi cleanup theo kế hoạch, owner và ngày review.

## 21. Kịch bản thực tế: phát hành thuật toán giảm giá mới

Giả sử hệ thương mại điện tử muốn áp dụng thuật toán **Discount Engine V2**. Một số promotion trước đây có quy tắc thứ tự áp dụng chưa nhất quán. Nhóm sản phẩm muốn phát hành dần, nhưng mọi checkout phải giữ nguyên tính đúng đắn của số tiền thanh toán.

### Giai đoạn chuẩn bị

- Xác định input/output contract cho cả V1 và V2.
- Tạo flag **checkout.discount-engine-v2** mặc định legacy.
- Viết test cho các tình huống giảm giá, thuế, làm tròn, currency, expired promotion và refund.
- Tách pure calculation khỏi thao tác ghi đơn/charge tiền.
- Lưu **pricingPolicyVersion** và quote đã chốt vào record để sử dụng sau này.
- Tạo dashboard so sánh invariant **order.totalAmount == chargedAmount** và rate checkout failure.
- Kiểm tra Payment hiểu số tiền đã chốt, không tự tính lại bằng policy hiện tại.

### Giai đoạn phát hành

1. Deploy build chứa cả V1 và V2, flag OFF.
2. Cho phép một nhóm nhân viên hoặc test tenant dùng v2.
3. Mở 1% người dùng theo bucket ổn định; không chọn random mỗi request.
4. Theo dõi sai lệch tiền, p95 latency, refund flow và trạng thái abandoned checkout.
5. Nếu guardrail ổn, tăng 5%, 25%, 50%, 100% theo kế hoạch.
6. Nếu phát sinh sai lệch tiền, ngừng phân bổ request mới vào v2, giữ record đã xử lý để đối soát và sửa dữ liệu theo quy trình nghiệp vụ.
7. Sau khi các đơn lịch sử và luồng hoàn tiền đã hỗ trợ version mới, lên kế hoạch dọn nhánh V1/flag.

### Khi flag service mất kết nối

Nếu Order Service đang có snapshot đã biết tốt, có thể dùng snapshot theo chính sách stale đã định. Nếu khởi động không có snapshot, chọn **default đã phê duyệt** hoặc từ chối thao tác nếu không thể bảo đảm tính đúng đắn; không đoán ngẫu nhiên biến thể.

Nếu rollout bị dừng giữa luồng thanh toán, thao tác đã bắt đầu phải hoàn tất hoặc chuyển sang trạng thái điều tra theo cùng quote/decision, không đổi engine giữa chừng.

## 22. Checklist thiết kế trước khi mở một flag production

1. **Ý nghĩa:** flag chọn chính xác hành vi nào? ON/OFF/variation có bất biến nào?
2. **Owner:** ai phụ trách code, rollout, hỗ trợ sự cố và cleanup?
3. **Người được bật:** rule dựa trên subject/tenant đáng tin? Cohort có ổn định không?
4. **Default:** khi thiếu config hoặc service flag lỗi, hệ thống làm gì?
5. **Tương thích:** phiên bản service, schema và event có thể hoạt động đồng thời không?
6. **Side effects:** có transaction, thanh toán, email, ghi data không thể hoàn tác không?
7. **Metrics:** đánh giá exposure, lỗi kỹ thuật, guardrail nghiệp vụ bằng gì?
8. **Sức chứa:** 10% user tương đương bao nhiêu traffic/cpu/calls downstream?
9. **Quyền thay đổi:** ai có thể nâng tỷ lệ, dừng hoặc bật 100%?
10. **Propagation:** update mất bao lâu tới tất cả instance; kill switch có được diễn tập?
11. **Kiểm thử:** ON, OFF, fallback, flag drift, retry, consumer cũ và DB migration?
12. **Dọn dẹp:** khi nào xóa cờ và đường legacy?

## 23. Câu hỏi tự kiểm tra

**1. Có feature flag thì mọi thay đổi đều không cần triển khai lại sao?**  
Không. Code của hành vi mới vẫn phải được build và deploy trước. Flag chỉ điều khiển hành vi mà binary đang chạy đã hỗ trợ.

**2. Khác nhau giữa rollout 10% user và 10% request là gì?**  
10% user chọn một nhóm người dùng ổn định, mỗi người có thể tạo số request khác nhau. 10% request là tỷ lệ traffic và có thể đưa cùng user qua hai biến thể nếu không sticky. Chọn đơn vị phù hợp mục tiêu.

**3. Tại sao không random ở mỗi lần gọi flag?**  
Vì request của cùng user/transaction có thể đổi biến thể, làm sai trải nghiệm và dữ liệu; deterministic bucketing giữ hành vi ổn định.

**4. Vì sao phải lưu pricingPolicyVersion vào đơn hàng?**  
Vì refund, dispute và đối soát diễn ra sau này, khi flag đã thay đổi. Các thao tác phải dựa trên policy và giá trị đã áp dụng tại thời điểm tạo giao dịch.

**5. Flag OFF có thể rollback migration xóa cột DB không?**  
Không. Cần migration tương thích, expand-contract, backfill và kế hoạch data rollback riêng.

**6. Feature flag có thể dùng để “ẩn” một API quản trị không?**  
Có thể ẩn UI hoặc tính năng khỏi nhóm user, nhưng không thay thế server-side authentication, authorization và kiểm tra resource.

**7. Một service nhận update flag mới còn service khác dùng snapshot cũ: cần làm gì?**  
Thiết kế contract tương thích, đo config age/revision, tránh để logic xuyên service phụ thuộc đồng thời vào hai decision khác nhau; truyền workflow/contract version khi cần.

**8. Khi control plane hỏng, mọi flag nên mặc định OFF?**  
Không có default chung đúng cho tất cả. Release flag có thể dùng legacy, entitlement cần tránh mở quyền sai, còn dữ liệu đã ghi theo format mới có thể không tương thích với legacy. Fallback phải được thiết kế theo từng flag.

**9. Khi nào nên xóa release flag?**  
Sau khi mục tiêu rollout đã đạt, không còn caller/consumer cần biến thể cũ và việc xóa code cũ không phá backward compatibility hoặc xử lý dữ liệu lịch sử.

**10. Vì sao cần audit việc đổi flag?**  
Vì thay đổi flag có thể ảnh hưởng production ngay lập tức. Audit cho phép biết người thay, môi trường, revision, lý do và thời điểm để ứng phó sự cố.

## Tài liệu tham khảo

- Martin Fowler — Feature Toggles (aka Feature Flags): https://martinfowler.com/articles/feature-toggles.html
- OpenFeature — Specification: https://openfeature.dev/specification/
- OpenFeature — Concepts: https://openfeature.dev/docs/reference/concepts/
- Google Cloud — Deployment strategies / progressive delivery concepts: https://cloud.google.com/architecture
- Microsoft Azure Architecture Center — Feature flags: https://learn.microsoft.com/en-us/azure/architecture/patterns/feature-flags
- AWS AppConfig — Feature flags and safe deployment: https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-creating-configuration-and-profile-feature-flags.html

**Ghi nhớ:** Feature flags là công cụ **kiểm soát thời điểm và phạm vi thay đổi hành vi**. Chúng mang lại phát hành có kiểm soát khi đi cùng code tương thích, cohort ổn định, default an toàn, telemetry theo variation, phân quyền thay đổi và kế hoạch dọn cờ. Sự an toàn của giao dịch, authorization và migration dữ liệu vẫn là trách nhiệm kiến trúc độc lập.
