# Feature flag và bật tính năng theo nhóm người dùng

Trong chương **Cấu hình và môi trường**, feature flag (cờ tính năng) là cơ chế quyết định một nhánh hành vi của ứng dụng có được bật cho một nhóm đối tượng hoặc trong một môi trường nhất định hay không. Thay vì phải triển khai lại code mỗi khi muốn mở tính năng cho một nhóm người dùng, ứng dụng đọc quyết định từ cấu hình và chọn hành vi tương ứng.

Feature flag thường được dùng để phát hành dần một tính năng, thử nghiệm một trải nghiệm mới, tắt nhanh một chức năng đang gây sự cố hoặc giới hạn tính năng cho một nhóm nội bộ. Với ứng dụng serverless, cơ chế này cần tính đến cold start, nhiều execution environment chạy song song, cache cấu hình, retry và khả năng các instance nhìn thấy phiên bản flag khác nhau trong một khoảng thời gian.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Feature flag là một phần của cấu hình runtime: nó giúp thay đổi hành vi có kiểm soát mà không cần thay đổi code hoặc triển khai lại mỗi lần.

## 1. Feature flag là gì?

Feature flag là một quyết định cấu hình được ứng dụng kiểm tra tại runtime để chọn một hành vi. Ví dụ, cùng một phiên bản Java function có thể:

- Bật giao diện thanh toán mới cho nhân viên nội bộ.
- Cho phép 5% tài khoản khách hàng sử dụng quy trình mới.
- Bật xử lý batch lớn hơn ở môi trường staging.
- Tạm tắt một nhánh xử lý đang làm tăng lỗi database.
- Chạy một thử nghiệm A/B với hai biến thể của nội dung.

Một flag thường có key ổn định, giá trị mặc định, quy tắc targeting và metadata quản lý. Ví dụ:

~~~json
{
  "key": "new-checkout-flow",
  "enabled": true,
  "rolloutPercentage": 10,
  "environment": "production",
  "owner": "checkout-team",
  "expiresAt": "2027-03-31"
}
~~~

Đây là cấu trúc minh họa. Dịch vụ quản lý flag thực tế có thể lưu rule, segment, variant và điều kiện theo schema riêng. Ứng dụng không nên phụ thuộc trực tiếp vào JSON nội bộ của một nhà cung cấp; hãy chuyển nó thành mô hình đánh giá mà application code cần.

Flag thường là một phần của cấu hình động. Giá trị có thể được thay đổi độc lập với lần deploy code, nhưng ứng dụng chỉ nhìn thấy thay đổi khi cấu hình được tải hoặc refresh thành công.

## 2. Phân biệt feature flag, cấu hình và phân quyền

Ba khái niệm này có liên quan nhưng không thay thế nhau.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Feature flag | Có bật hành vi này cho đối tượng này không? | Dùng checkout mới cho nhóm beta |
| Runtime configuration | Hành vi được cấu hình bằng tham số nào? | Timeout API là 2 giây |
| Authorization / entitlement | Chủ thể này có quyền thực hiện hành động hoặc truy cập dữ liệu không? | Người dùng có quyền xem hóa đơn của tenant |

Feature flag quyết định code path hoặc trải nghiệm. Authorization kiểm tra quyền dựa trên danh tính, resource và policy. Không dùng một flag như cách duy nhất để bảo vệ dữ liệu hoặc cấp quyền truy cập.

Ví dụ, flag có thể bật nút xuất báo cáo mới trong giao diện, nhưng backend vẫn phải kiểm tra người gọi có quyền xuất báo cáo của tenant tương ứng hay không. Người dùng có thể sửa request hoặc gọi API trực tiếp; việc giao diện ẩn nút không bảo vệ được API.

Một số hệ thống có khái niệm entitlement hoặc gói dịch vụ. Nếu quyền sử dụng tính năng là một phần của hợp đồng khách hàng, nên kiểm tra entitlement ở policy service hoặc domain logic có nguồn dữ liệu đáng tin cậy. Flag có thể điều khiển rollout kỹ thuật, còn entitlement quyết định khách hàng có quyền sử dụng hay không.

## 3. Các loại feature flag

Có thể phân loại theo mục đích và thời gian tồn tại:

| Loại flag | Mục đích | Thời gian tồn tại thường gặp |
|---|---|---|
| Release toggle | Phát hành tính năng theo giai đoạn | Ngắn đến trung hạn |
| Operational toggle | Bật/tắt thành phần để bảo vệ hệ thống | Có thể dài hạn nếu là kill switch |
| Experiment toggle | Chia nhóm để so sánh biến thể | Trong thời gian thử nghiệm |
| Permission/entitlement toggle | Biểu diễn quyền sử dụng | Nên quản lý bằng hệ thống quyền riêng; không coi flag rollout là nguồn quyền |

Release toggle giúp triển khai code trước khi bật tính năng. Operational toggle giúp tắt một nhánh xử lý khi dependency gặp sự cố. Experiment toggle gán đối tượng vào các biến thể để đo tác động.

Một flag không nên tồn tại mãi chỉ vì việc xóa nó bị quên. Mỗi flag nên có owner, mục đích, ngày tạo, ngày dự kiến gỡ và người chịu trách nhiệm. Khi rollout hoàn tất, xóa nhánh code cũ và flag tương ứng để tránh tạo nhiều đường đi khó kiểm thử.

## 4. Targeting: chọn nhóm người dùng hoặc workload

Targeting là tập hợp quy tắc xác định đối tượng nào nhận giá trị flag nào. Quy tắc có thể dựa trên:

- Environment: dev, staging, production.
- Nhóm nội bộ hoặc beta cohort.
- Account ID hoặc tenant ID ổn định.
- Region hoặc loại thiết bị nếu có lý do nghiệp vụ.
- Phiên bản ứng dụng hoặc loại client.
- Phần trăm đối tượng được chọn.
- Danh sách allowlist hoặc denylist.

Ví dụ một thứ tự rule:

1. Tắt flag trong môi trường test đặc biệt.
2. Nếu tenant bị loại trừ, tắt tính năng.
3. Nếu subject nằm trong danh sách nhân viên nội bộ, bật tính năng.
4. Nếu subject nằm trong beta cohort, bật tính năng.
5. Nếu subject thuộc 10% rollout, bật tính năng.
6. Các đối tượng còn lại dùng giá trị mặc định false.

Thứ tự và độ ưu tiên phải được xác định rõ. Nếu một đối tượng vừa nằm trong allowlist vừa thuộc nhóm bị loại trừ, policy cần quy định rule nào thắng. Một cách thường dùng là deny/exclusion có ưu tiên cao nhất, sau đó đến explicit allowlist, segment và rollout percentage; tuy nhiên hệ thống cần ghi rõ quy tắc thực tế.

### 4.1. Chọn định danh ổn định

Để một người dùng không bị đổi nhóm ở mỗi request, dùng định danh ổn định như account ID hoặc tenant ID đã xác thực. Không dùng random number mới cho từng invocation.

Với B2B multi-tenant, cần quyết định đơn vị rollout là user hay tenant. Nếu tính năng ảnh hưởng đến dữ liệu dùng chung, bật cho một phần user trong cùng tenant có thể tạo trải nghiệm không nhất quán. Khi đó có thể rollout theo tenant để mọi thành viên của một tổ chức nhận cùng quyết định.

Không dùng email, số điện thoại hoặc dữ liệu cá nhân làm targeting key nếu một ID nội bộ ổn định là đủ. Tránh đưa thông tin nhạy cảm vào flag evaluation logs.

### 4.2. Context phải đáng tin cậy

Targeting context thường gồm subject ID và thuộc tính như tenant, role, region hoặc app version. Các thuộc tính dùng để ra quyết định phải được xác thực hoặc lấy từ nguồn đáng tin cậy.

Không tin một trường tenantId hoặc role do client tự gửi nếu backend chưa xác minh. Một người dùng có thể thay header hoặc payload để được đưa vào nhóm beta hay nhóm có tính năng cao cấp.

Adapter của HTTP trigger nên xác thực token, tạo principal nội bộ và chỉ sau đó mới xây dựng evaluation context. Với message trigger, context nên được lấy từ event đã xác thực nguồn phát hoặc metadata đã được producer tin cậy tạo ra.

## 5. Rollout theo phần trăm và cohort ổn định

Một rollout 10% thường có nghĩa là chọn ổn định 10% subject đủ điều kiện, không phải bật ngẫu nhiên cho 10% invocation.

Cách khái niệm:

\[
bucket = H(flagKey, subjectKey, salt) \bmod 100
\]

Nếu bucket nhỏ hơn rollout percentage thì bật flag. H là hàm băm ổn định; salt giúp phân nhóm khác nhau giữa các flag nếu muốn. Trong production, nên dùng cơ chế bucketing của flag provider hoặc một thuật toán ổn định đã được kiểm tra phân bố.

Ví dụ: subject có bucket 07 sẽ tiếp tục nằm trong nhóm 10% cho flag đó ở các request sau. Nếu rollout tăng lên 25%, các subject có bucket từ 10 đến 24 được thêm vào nhóm mới, trong khi nhóm đã bật vẫn giữ nguyên.

Không dùng hash không ổn định theo process hoặc giá trị random mới cho từng request. Cũng không dùng hàm hash của object phức tạp có thể thay đổi giữa phiên bản code. Nếu tự xây bucketing, cần định nghĩa encoding, normalization, salt, thuật toán và test để đảm bảo kết quả ổn định giữa runtime và ngôn ngữ.

### 5.1. Ví dụ bucketing Java mang tính minh họa

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class StableBucketing {
    private StableBucketing() {
    }

    public static int bucket(
            String flagKey,
            String subjectKey,
            String salt) {

        try {
            String input = flagKey + ":" + subjectKey + ":" + salt;
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));

            long value = Integer.toUnsignedLong(
                    ByteBuffer.wrap(digest).getInt());

            return (int) (value % 100);
        } catch (Exception failure) {
            throw new IllegalStateException(
                    "Unable to calculate rollout bucket", failure);
        }
    }

    public static boolean isEnabled(
            String flagKey,
            String subjectKey,
            String salt,
            int percentage) {

        if (percentage < 0 || percentage > 100) {
            throw new IllegalArgumentException(
                    "percentage must be between 0 and 100");
        }

        return bucket(flagKey, subjectKey, salt) < percentage;
    }
}
~~~

Ví dụ trên chỉ minh họa nguyên tắc ổn định. Hệ thống thực tế nên dùng một implementation bucketing đã được kiểm thử, chuẩn hóa input rõ ràng và không tự tạo một thuật toán khác với provider nếu cần cùng cohort ở nhiều service.

## 6. Kiến trúc đánh giá flag trong serverless

Một function có thể được gọi bởi HTTP, queue hoặc event bus. Mỗi trigger tạo evaluation context khác nhau nhưng application code nên dùng cùng một port.

~~~mermaid
flowchart TB
    H["HTTP / Queue / Event"] --> AD["Trigger adapter"]
    AD --> CTX["Trusted evaluation context"]
    CTX --> APP["Application use case"]
    APP --> FLAG["Feature flag evaluator"]
    FLAG --> CACHE["Local snapshot / cache"]
    CACHE --> CFG["Flag configuration service"]
    APP --> PATH1["Old behavior"]
    APP --> PATH2["New behavior"]
~~~

Có thể tách thành các phần:

- **Configuration source:** nơi quản lý flag, rule, environment và rollout.
- **Provider adapter:** giao tiếp với dịch vụ hoặc SDK cụ thể.
- **Local cache:** giữ snapshot đã tải để tránh gọi mạng ở mỗi invocation.
- **Evaluator:** áp dụng rule với evaluation context.
- **Application code:** nhận kết quả đã đánh giá và chọn hành vi.

Application code không nên gọi trực tiếp AWS AppConfig, LaunchDarkly hoặc API nhà cung cấp ở mọi nhánh nghiệp vụ. Hãy bọc provider bằng một interface nội bộ hoặc chuẩn mở như OpenFeature để giảm phụ thuộc.

## 7. Định nghĩa port trong Java

Một interface nhỏ có thể thể hiện nhu cầu của ứng dụng:

~~~java
import java.util.Map;

public record FlagContext(
        String subjectKey,
        Map<String, String> attributes) {

    public FlagContext {
        attributes = Map.copyOf(attributes);
    }
}

public record FlagDecision(
        boolean enabled,
        String variant,
        String reason,
        String configurationVersion) {
}

public interface FeatureFlagEvaluator {
    FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue);
}
~~~

subjectKey là định danh ổn định đã được xác thực. attributes chỉ chứa các thuộc tính cần cho targeting, tránh đưa toàn bộ profile hoặc thông tin cá nhân vào evaluator.

Một use case có thể kiểm tra flag:

~~~java
public final class CheckoutService {
    private final FeatureFlagEvaluator flags;
    private final LegacyCheckout legacyCheckout;
    private final NewCheckout newCheckout;

    public CheckoutService(
            FeatureFlagEvaluator flags,
            LegacyCheckout legacyCheckout,
            NewCheckout newCheckout) {
        this.flags = flags;
        this.legacyCheckout = legacyCheckout;
        this.newCheckout = newCheckout;
    }

    public CheckoutResult checkout(
            CheckoutCommand command,
            FlagContext context) {

        FlagDecision decision = flags.evaluate(
                "new-checkout-flow",
                context,
                false);

        if (decision.enabled()) {
            return newCheckout.execute(command);
        }

        return legacyCheckout.execute(command);
    }
}
~~~

Giá trị mặc định false làm hệ thống quay về đường xử lý cũ khi flag không đọc được. Đây là lựa chọn phù hợp nếu đường cũ vẫn an toàn và được hỗ trợ. Nếu flag điều khiển một thao tác nguy hiểm, ví dụ bật luồng có khả năng ghi dữ liệu sai, default cần được chọn theo mức độ rủi ro và có thể phải fail closed.

## 8. Đánh giá flag an toàn khi provider lỗi

Flag provider có thể không truy cập được do network, throttling, timeout, credential hết hạn hoặc cấu hình sai. Ứng dụng phải xác định hành vi khi không thể đánh giá.

Có ba chiến lược thường gặp:

| Chiến lược | Hành vi | Khi phù hợp |
|---|---|---|
| Fail open | Cho phép nhánh mặc định tiếp tục | Tính năng không nhạy cảm, đường mặc định an toàn |
| Fail closed | Từ chối hoặc tắt nhánh có rủi ro | Tính năng có thể gây hỏng dữ liệu hoặc chi phí lớn |
| Last known good | Dùng snapshot hợp lệ gần nhất | Có thể chấp nhận cấu hình cũ trong một khoảng thời gian |

Không có default chung đúng cho mọi flag. Mỗi flag nên định nghĩa default và chính sách lỗi ngay khi tạo. Nếu provider không phản hồi, evaluator cần trả một quyết định có reason rõ ràng để log/metric, thay vì ném lỗi khiến toàn bộ request thất bại ngoài ý muốn.

Không dùng last known good vô hạn. Cần có max-stale age; khi snapshot quá cũ, ứng dụng chuyển sang default hoặc chính sách an toàn đã định nghĩa. Với kill switch bảo vệ hệ thống, stale config có thể khiến function tiếp tục hành vi cần tắt. Cần cân nhắc yêu cầu thời gian lan truyền và cơ chế cảnh báo riêng.

## 9. Cache flag trong Lambda và FaaS

Execution environment có thể được tái sử dụng giữa nhiều invocation, nhưng nền tảng có quyền kết thúc nó bất cứ lúc nào. Vì vậy:

- Static cache có thể giảm số lần tải cấu hình trong một environment.
- Cache không được coi là kho trạng thái bền vững.
- Các environment khác nhau có thể đang dùng version flag khác nhau.
- Cold start có thể tạo nhiều environment và cùng tải cấu hình.
- Invocation song song trong cùng environment cần đọc snapshot an toàn.

Không nên gọi flag service qua mạng ở mọi request nếu có thể tránh. Cách đó làm tăng latency, chi phí, áp lực lên control plane và tạo thêm dependency có thể làm function lỗi.

### 9.1. Cache snapshot có thời hạn

Một snapshot có thể chứa version, timestamp tải, flag definitions và metadata. Evaluator đọc snapshot bất biến; refresh tạo snapshot mới rồi thay thế tham chiếu nguyên tử.

Ví dụ đơn giản:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public record FlagSnapshot(
        String version,
        Instant loadedAt,
        Map<String, Boolean> values) {

    public FlagSnapshot {
        values = Map.copyOf(values);
    }
}

public final class SnapshotFlagEvaluator
        implements FeatureFlagEvaluator {

    private final AtomicReference<FlagSnapshot> current;

    public SnapshotFlagEvaluator(FlagSnapshot initial) {
        this.current = new AtomicReference<>(initial);
    }

    public void replaceSnapshot(FlagSnapshot next) {
        current.set(next);
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        FlagSnapshot snapshot = current.get();
        boolean enabled = snapshot.values().getOrDefault(
                flagKey, defaultValue);

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "local_snapshot",
                snapshot.version());
    }
}
~~~

Đây là ví dụ snapshot boolean đơn giản, chưa thể hiện targeting rule hoặc TTL. Implementation thực tế cần map rule theo key, kiểm tra tuổi snapshot, đồng thời bảo đảm map không thể bị sửa sau khi publish. AtomicReference giúp các invocation nhìn thấy snapshot cũ hoặc mới hoàn chỉnh, tránh đọc một cấu trúc đang được sửa dở.

### 9.2. Refresh và tránh thundering herd

Nếu mỗi execution environment đều refresh cùng lúc, một đợt scale-out có thể tạo nhiều request đồng thời đến configuration service. Có thể giảm tải bằng:

- TTL có jitter để các environment không refresh cùng thời điểm.
- Exponential backoff khi provider lỗi.
- Refresh nền nếu runtime và mô hình thực thi cho phép.
- Tải snapshot khi khởi tạo hoặc lần đầu cần, sau đó dùng cache.
- Dùng extension/agent cục bộ hoặc cache do provider SDK hỗ trợ.
- Giới hạn số lần retry và thời gian chờ.

Trong Lambda, background thread không được bảo đảm chạy liên tục khi function không có invocation. Nếu dùng refresh nền, phải hiểu rõ vòng đời runtime và không phụ thuộc thread đó để cập nhật chính xác. Một lần refresh đồng bộ khi cache hết hạn có thể đơn giản hơn, nhưng cần timeout ngắn và fallback rõ ràng.

### 9.3. Nhất quán giữa các environment

Khi thay đổi rollout từ 5% lên 20%, các environment có thể cập nhật snapshot ở những thời điểm khác nhau. Trong một khoảng ngắn, cùng một user có thể được đánh giá khác nhau nếu request đến các environment có config version khác nhau.

Để giảm vấn đề:

- Dùng bucketing ổn định theo flag key và subject key.
- Đưa rollout percentage và salt vào snapshot version.
- Theo dõi version đang được mỗi environment sử dụng.
- Chọn TTL phù hợp với mức độ nhanh cần lan truyền.
- Không dùng flag cục bộ để điều khiển quyết định cần nhất quán tuyệt đối hoặc có tác động bảo mật.

Nếu cần một thay đổi có hiệu lực tức thì, cache cục bộ có TTL có thể không đáp ứng. Cần một cơ chế control plane hoặc policy check có bảo đảm phù hợp, và chấp nhận chi phí/độ trễ của nó.

## 10. Quản lý flag bằng AWS AppConfig

AWS AppConfig là dịch vụ quản lý và triển khai cấu hình cho ứng dụng. Có thể dùng AppConfig để phân phối feature flag và cấu hình động theo application, environment và configuration profile.

Các khái niệm chính:

- **Application:** nhóm logic các cấu hình thuộc một ứng dụng.
- **Environment:** môi trường như dev, staging hoặc production.
- **Configuration profile:** loại cấu hình được phân phối, có thể là feature flags hoặc freeform configuration.
- **Hosted configuration version:** phiên bản cấu hình được lưu trong AppConfig hoặc nguồn cấu hình được hỗ trợ.
- **Deployment strategy:** cách phân phối phiên bản cấu hình theo thời gian và mức độ.
- **Validator:** kiểm tra cấu hình trước khi triển khai.

AppConfig có thể giúp triển khai thay đổi theo từng giai đoạn, theo dõi deployment và rollback khi có vấn đề. Dịch vụ quản lý phân phối cấu hình; ứng dụng vẫn cần đánh giá flag với context phù hợp và xử lý cache/fallback.

### 10.1. Lấy cấu hình từ Lambda

Có thể dùng AWS AppConfig Agent hoặc Lambda extension phù hợp để cung cấp cấu hình đã cache cho function qua endpoint cục bộ. Một lựa chọn khác là dùng AWS AppConfig Data APIs trực tiếp trong adapter.

Mô hình extension:

1. Lambda execution environment khởi chạy function và extension.
2. Extension lấy cấu hình từ AppConfig theo cấu hình deployment.
3. Function đọc snapshot từ endpoint local.
4. Extension refresh theo chu kỳ và cache response.
5. Function tiếp tục sử dụng snapshot khi xử lý invocation.

Cách này giảm số lần function phải gọi trực tiếp control plane. Cần cấu hình extension, IAM permission, application/environment/profile và thời gian polling phù hợp. Extension có thể ảnh hưởng init duration, memory và telemetry; hãy đo trước khi bật rộng.

### 10.2. Tách adapter AppConfig khỏi application core

Có thể triển khai FeatureFlagEvaluator bằng một adapter dùng AppConfig:

~~~java
public final class AppConfigFeatureFlagAdapter
        implements FeatureFlagEvaluator {

    private final AppConfigSnapshotProvider snapshots;

    public AppConfigFeatureFlagAdapter(
            AppConfigSnapshotProvider snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        FlagSnapshot snapshot = snapshots.current();
        // Tìm flag, áp dụng targeting rule với context.
        // Nếu không có flag hoặc snapshot không hợp lệ,
        // trả default theo chính sách đã cấu hình.
        boolean enabled = snapshot.values().getOrDefault(
                flagKey, defaultValue);

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "appconfig_snapshot",
                snapshot.version());
    }
}
~~~

AppConfigSnapshotProvider là interface minh họa. Adapter thực tế sẽ gọi endpoint local của extension hoặc AWS AppConfig Data API, parse schema và xây snapshot. Use case chỉ phụ thuộc FeatureFlagEvaluator, không phụ thuộc AppConfig SDK.

### 10.3. Validator và deployment strategy

Trước khi triển khai cấu hình, nên xác thực:

- Flag key không trùng.
- Kiểu dữ liệu đúng schema.
- Percentage nằm trong 0–100.
- Rule có priority rõ ràng.
- Default value được khai báo.
- Flag có owner và metadata cần thiết.
- Không có thuộc tính targeting nhạy cảm hoặc không hợp lệ.

Dùng deployment strategy có bake time và gradual rollout khi thay đổi cấu hình ảnh hưởng nhiều function. Theo dõi error rate, duration, throttles và metric nghiệp vụ trong lúc rollout. Nếu chỉ có thể biết sự cố sau khi người dùng báo, rollout chưa có đủ guardrail.

## 11. Tích hợp OpenFeature

OpenFeature là một chuẩn mở cung cấp API chung cho việc đánh giá feature flag. Ứng dụng dùng API của OpenFeature, còn provider cụ thể kết nối với hệ thống flag tương ứng.

Lợi ích:

- Giảm sự phụ thuộc trực tiếp vào SDK của một nhà cung cấp.
- Có thể thay provider mà ít thay đổi application code.
- Hỗ trợ evaluation context và nhiều kiểu flag.
- Dễ dùng test provider hoặc no-op provider trong kiểm thử.

OpenFeature không phải là dịch vụ lưu trữ flag. Vẫn cần một provider như AppConfig adapter hoặc dịch vụ feature management khác, cùng quy trình quản lý rule, rollout và quyền chỉnh sửa.

Một cách tổ chức là để adapter chuyển FlagContext nội bộ thành evaluation context của OpenFeature. Nếu đổi provider, chỉ provider adapter và cấu hình bootstrap thay đổi; use case tiếp tục gọi port nội bộ hoặc API chuẩn đã chọn.

## 12. Targeting theo nhóm và môi trường

Targeting rule cần có cấu trúc dễ đọc và có thể kiểm thử. Một rule có thể gồm:

- Priority hoặc thứ tự đánh giá.
- Điều kiện environment.
- Điều kiện segment hoặc thuộc tính subject.
- Phần trăm rollout.
- Giá trị hoặc variant trả về.
- Thời điểm bắt đầu/kết thúc.
- Owner và lý do thay đổi.

Ví dụ bảng rule:

| Ưu tiên | Điều kiện | Kết quả |
|---:|---|---|
| 1 | Environment là test và flag bị khóa | OFF |
| 2 | Tenant nằm trong exclusion list | OFF |
| 3 | Subject thuộc internal allowlist | ON |
| 4 | Tenant thuộc beta cohort | ON |
| 5 | Bucket nhỏ hơn 10 | ON |
| 6 | Không khớp rule | OFF |

Quy tắc cụ thể phải xác định precedence. Bảng này chỉ là một ví dụ: nếu exclusion cần thắng allowlist, phải đặt nó ở ưu tiên cao hơn. Không để hai rule mâu thuẫn mà evaluator tự quyết định theo thứ tự không được tài liệu hóa.

### 12.1. Nhóm theo tenant

Với SaaS nhiều tenant, rollout theo tenant thường giúp tránh trạng thái một số người trong cùng tổ chức thấy tính năng còn người khác thì không. Tuy nhiên, một số tính năng có thể rollout theo user nếu chúng không ảnh hưởng dữ liệu hoặc workflow dùng chung.

Context nên mang cả subject và tenant đã xác thực:

~~~java
FlagContext context = new FlagContext(
        authenticatedUser.internalId(),
        Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "environment", deploymentEnvironment,
                "clientVersion", clientVersion));
~~~

Không lấy tenantId trực tiếp từ body rồi dùng để targeting nếu backend chưa xác minh người dùng có thuộc tenant đó. Một tenant bị đưa nhầm vào beta có thể làm lộ tính năng hoặc thay đổi workflow của cả tổ chức.

### 12.2. Môi trường và production safety

Không nên dùng chung cấu hình flag giữa dev, staging và production nếu mục đích của các môi trường khác nhau. Mỗi environment cần profile hoặc namespace riêng, với quyền chỉnh sửa và quy trình phê duyệt phù hợp.

Một flag bật ở staging không có nghĩa nó tự động bật ở production. Promotion cấu hình cần có review, version và audit trail giống các thay đổi triển khai khác.

## 13. Variant và thử nghiệm A/B

Một boolean flag chỉ có hai trạng thái on/off. Experiment có thể cần nhiều variant, ví dụ A/B/C:

- Variant A: giao diện hiện tại.
- Variant B: checkout một trang.
- Variant C: checkout theo từng bước.

Evaluator trả variant cùng metadata assignment. Đối tượng cần được giữ ổn định ở cùng variant trong suốt thử nghiệm, dùng subject key và experiment key ổn định.

Khi thiết kế experiment, cần xác định:

- Đơn vị randomization là user, tenant hay session.
- Metric chính và guardrail metric.
- Thời gian thử nghiệm và cỡ mẫu.
- Cách xử lý user đổi thiết bị hoặc tenant.
- Cách loại trừ bot, nhân viên và traffic không hợp lệ.
- Quy tắc dừng khi error rate hoặc latency xấu đi.

Không đổi variant ngẫu nhiên ở mỗi invocation. Nếu một user nhìn thấy nhiều biến thể trong cùng hành trình, dữ liệu thử nghiệm bị nhiễu và trải nghiệm không nhất quán.

Feature flag cho phép phân phối variant; việc kết luận variant nào tốt hơn cần thiết kế phân tích thí nghiệm phù hợp. Không kết luận chỉ từ vài lượt chuyển đổi đầu tiên.

## 14. Kết hợp feature flag với deployment và canary

Deployment và feature rollout là hai hoạt động khác nhau:

- **Deployment:** đưa phiên bản code mới vào môi trường.
- **Feature rollout:** quyết định ai được chạy nhánh code mới.

Có thể deploy code trước nhưng giữ flag OFF. Sau khi smoke test và xác nhận an toàn, bật cho nhân viên nội bộ, rồi tăng dần phần trăm người dùng. Cách này tách rủi ro triển khai artifact khỏi rủi ro bật hành vi.

Canary deployment thường chuyển một phần traffic sang version mới của function hoặc alias. Feature flag rollout có thể bật nhánh code mới trong cùng version. Hai cơ chế có thể kết hợp, nhưng phải tránh nhân đôi phần trăm một cách không chủ đích.

Ví dụ: 10% traffic đến Lambda version mới, và trong version đó chỉ 20% subject bật feature flag. Tỷ lệ request vừa đi vào version mới vừa chạy nhánh mới không nhất thiết là 20% toàn hệ thống; nếu hai nhóm độc lập, nó có thể xấp xỉ 2%. Cần theo dõi dimension version và flag variant để hiểu chính xác.

## 15. Kill switch và kiểm soát sự cố

Operational flag có thể tắt một tính năng khi dependency gặp sự cố hoặc khi metric vượt ngưỡng. Ví dụ, tạm ngừng tạo thumbnail nếu dịch vụ xử lý ảnh quá tải, trong khi API chính vẫn hoạt động.

Một kill switch cần:

- Có default an toàn.
- Có owner và người được phép thay đổi.
- Có đường cập nhật nhanh đã được kiểm thử.
- Có metric xác nhận flag đã được áp dụng.
- Có hướng fallback rõ ràng.
- Có tài liệu cách bật lại và điều kiện gỡ bỏ.

Không phải kill switch nào cũng nên dùng cache dài. Nếu yêu cầu tắt trong vài giây, TTL cache phải phù hợp hoặc cần cơ chế phân phối nhanh hơn. Nếu function đang dùng snapshot cũ, thao tác tắt ở control plane chưa chắc có hiệu lực ngay trên mọi environment.

Không dùng feature flag để thay thế circuit breaker. Flag điều khiển một hành vi đã được định nghĩa; circuit breaker phản ứng với trạng thái lỗi của dependency theo ngưỡng và thời gian. Hai cơ chế có thể phối hợp nhưng khác mục đích.

## 16. Đánh giá flag trong HTTP, queue và scheduled function

### 16.1. HTTP-triggered function

HTTP adapter xác thực caller, tạo context rồi đánh giá flag. Nếu kết quả ảnh hưởng đến response, nên ghi variant và flag version vào log/trace mà không ghi PII.

Nếu client cần biết tính năng có khả dụng, backend có thể trả capability trong response. Tuy nhiên, client không được tự quyết định quyền truy cập; backend phải kiểm tra lại khi nhận thao tác.

### 16.2. Queue-triggered function

Message có thể được giao lại hoặc xử lý sau nhiều phút. Nếu evaluator dùng rollout percentage theo user/tenant, cần giữ subject key ổn định trong event. Nếu không có subject cụ thể, có thể đánh giá theo tenant, loại event hoặc một policy toàn cục.

Cần quyết định thời điểm đánh giá flag:

- **Tại lúc nhận event:** quyết định được ghi vào event hoặc metadata để các lần retry dùng cùng quyết định.
- **Tại lúc xử lý:** mỗi lần retry có thể thấy cấu hình mới.

Nếu một workflow cần tính nhất quán, lưu variant hoặc flag configuration version cùng trạng thái xử lý để retry không đổi hành vi giữa chừng. Với thao tác có rủi ro, không nên để retry sau nhiều giờ tự chuyển sang một nhánh nghiệp vụ khác chỉ vì flag vừa đổi.

### 16.3. Scheduled function

Scheduled function thường không có user context. Flag có thể dựa trên environment, loại job, tenant batch hoặc phần trăm partition. Với tác vụ có tác động lớn, cần log rõ config version và phạm vi dữ liệu được xử lý.

Nếu job chạy theo từng tenant, có thể rollout theo tenant. Nếu job xử lý partition, dùng partition key ổn định để tránh một partition thay đổi nhánh giữa các lần retry.

## 17. Tác động đến cold start, latency và chi phí

Flag evaluation có thể thêm chi phí nếu mỗi lần đánh giá gọi một API từ xa. Trong serverless, chi phí này nhân lên theo invocation và concurrency.

Các yếu tố cần cân nhắc:

- Thời gian khởi tạo SDK hoặc provider.
- Thời gian tải cấu hình lần đầu.
- Thời gian kiểm tra cache.
- Số lần refresh mỗi execution environment.
- Kích thước snapshot và chi phí deserialize.
- Memory dùng cho SDK, extension và cache.
- Số metric/log sinh ra từ quá trình đánh giá.

Thông thường, local evaluation trên snapshot có độ trễ thấp hơn remote call. Cần khởi tạo provider một lần trong execution environment, tái sử dụng client thread-safe và refresh theo TTL. Không khởi tạo một SDK client mới trong mỗi handler invocation.

Tuy nhiên, không nên tăng TTL chỉ để giảm chi phí nếu flag là cơ chế vận hành cần phản ứng nhanh. Chọn TTL dựa trên yêu cầu propagation, stale tolerance và tác động khi config service lỗi.

## 18. Bảo mật và quyền quản trị flag

Người có quyền chỉnh sửa flag có thể thay đổi hành vi production mà không cần deploy code. Vì vậy, quyền quản trị flag là quyền vận hành nhạy cảm.

Nên áp dụng:

- Phân quyền ai được xem, sửa, approve và deploy cấu hình.
- Tách quyền dev, staging và production.
- Audit mọi thay đổi, bao gồm người sửa, thời điểm, giá trị cũ và mới.
- Yêu cầu review hoặc phê duyệt cho flag có tác động lớn.
- Bảo vệ API quản trị bằng IAM/SSO và MFA theo chính sách tổ chức.
- Không để ứng dụng public có quyền ghi cấu hình flag.
- Không đưa secret vào flag value nếu hệ thống flag không phải secret manager.
- Hạn chế context attributes để tránh gửi PII đến nhà cung cấp.

Flag không phải kho secret. Giá trị flag có thể được cache, log hoặc truyền qua nhiều thành phần. Password, private key và token cần được quản lý bởi secret manager.

## 19. Quan sát và đo lường hiệu quả rollout

Mỗi lần đánh giá flag không nhất thiết cần log đầy đủ. Nhưng cần có đủ dữ liệu để hiểu rollout đang tác động thế nào.

Có thể ghi các trường:

- flagKey.
- variant hoặc enabled state.
- configurationVersion.
- evaluationReason.
- environment.
- functionVersion.
- requestId hoặc eventId.
- subject cohort ở dạng không định danh trực tiếp nếu cần phân tích.

Không dùng subject ID hoặc user ID làm CloudWatch metric dimension vì cardinality cao. Nếu cần phân tích cohort, dùng metric theo variant, environment hoặc nhóm có số lượng hữu hạn; chi tiết từng subject nên ở hệ thống phân tích được kiểm soát quyền và retention.

Theo dõi cả metric kỹ thuật và nghiệp vụ:

- Error rate, duration p95/p99, throttles.
- Queue age, retry và DLQ.
- Tỷ lệ thành công theo variant.
- Conversion hoặc completion rate.
- Database load và external API error.
- Số environment đang dùng config version cũ nếu có thể quan sát.

Một rollout nên có guardrail. Nếu error rate hoặc latency vượt ngưỡng, dừng tăng phần trăm hoặc tắt flag. Không tăng rollout chỉ vì không có người dùng báo lỗi.

## 20. Kiểm thử feature flag

Một tính năng có flag tạo ra nhiều đường thực thi. Cần kiểm thử cả hai nhánh và các tình huống lỗi.

Ma trận tối thiểu:

| Trường hợp | Kỳ vọng |
|---|---|
| Flag OFF | Chạy đường cũ |
| Flag ON | Chạy đường mới |
| Flag không tồn tại | Dùng default |
| Provider timeout | Áp dụng fail-open/closed đã định nghĩa |
| Snapshot quá cũ | Áp dụng max-stale policy |
| Subject trong allowlist | Nhận quyết định đúng rule |
| Subject trong exclusion | Bị loại theo precedence |
| Rollout percentage thay đổi | Cohort ổn định theo thuật toán |
| Context thiếu thuộc tính | Dùng default hoặc rule fallback |
| Retry cùng event | Hành vi idempotent và variant theo policy |

Có thể dùng fake evaluator trong unit test:

~~~java
public final class FixedFlagEvaluator
        implements FeatureFlagEvaluator {

    private final boolean enabled;

    public FixedFlagEvaluator(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "test_provider",
                "test-version");
    }
}
~~~

Test có thể inject evaluator ON hoặc OFF để kiểm tra hai nhánh mà không cần gọi flag service thật. Integration test cần xác minh adapter đọc đúng schema, refresh snapshot, xử lý timeout và áp dụng rule precedence.

## 21. Vòng đời và dọn dẹp flag

Flag tạo thêm nhánh code và tổ hợp trạng thái cần kiểm thử. Một release flag đã rollout 100% nhưng vẫn tồn tại sẽ làm code phức tạp hơn và khiến người sau khó biết nhánh nào còn cần.

Một vòng đời điển hình:

1. Tạo flag với owner, mục đích, default và ngày hết hạn dự kiến.
2. Phát hành code có cả nhánh cũ và mới.
3. Kiểm thử ở dev/staging.
4. Bật cho allowlist nội bộ.
5. Rollout theo cohort hoặc phần trăm.
6. Theo dõi guardrail và metric nghiệp vụ.
7. Bật 100% khi đã đạt tiêu chí.
8. Xóa nhánh cũ và flag khỏi cấu hình.
9. Xóa rule, dashboard hoặc alert chỉ phục vụ rollout nếu không còn cần.

Operational kill switch có thể có vòng đời dài hơn, nhưng vẫn cần owner, tài liệu và kiểm tra định kỳ. Đừng để một flag không rõ người chịu trách nhiệm trở thành công tắc production mà không ai dám đụng.

## 22. Những lỗi thường gặp

**Dùng flag làm authorization:** Người dùng có thể gọi API trực tiếp. Backend vẫn phải kiểm tra quyền độc lập.

**Random rollout ở mỗi invocation:** Cùng user liên tục đổi nhánh. Dùng bucketing ổn định theo subject/tenant và flag key.

**Gọi provider ở mọi request:** Tăng latency, chi phí và phụ thuộc mạng. Dùng snapshot/cache có TTL và fallback.

**Cache vô thời hạn:** Một số environment không nhận được kill switch mới. Có max-stale, version và quy trình refresh.

**Dùng static cache như trạng thái bền vững:** Environment có thể bị thay thế. Lưu quyết định nghiệp vụ cần tồn tại lâu trong kho bền vững.

**Target theo dữ liệu client tự gửi:** Người dùng có thể tự thêm tenant hoặc role để vào nhóm. Dùng context đã xác thực.

**Rule precedence không rõ:** Allowlist và exclusion có thể xung đột. Tài liệu hóa thứ tự đánh giá và viết test.

**Không xác định behavior khi provider lỗi:** Một lỗi cấu hình làm toàn bộ function ngừng chạy hoặc bật nhầm tính năng. Đặt default và fail policy cho từng flag.

**Đổi flag giữa các lần retry:** Một event có thể xử lý bằng hai phiên bản nghiệp vụ. Lưu variant/config version nếu workflow cần nhất quán.

**Không đo guardrail:** Rollout tăng dù latency hoặc error rate xấu đi. Gắn rollout với alarm và tiêu chí dừng.

**Flag không được dọn dẹp:** Code path cũ và mới tồn tại lâu, tăng số tổ hợp kiểm thử. Đặt expiry và owner.

**Đưa secret vào flag:** Flag service không thay thế secret manager. Lưu secret ở dịch vụ quản lý bí mật và chỉ truyền tham chiếu.

## 23. Quy trình triển khai feature flag cho Java Lambda

Có thể áp dụng quy trình sau:

1. **Xác định mục đích:** Flag dùng cho release, operational toggle hay experiment?
2. **Chọn đơn vị targeting:** User, tenant, account, partition hay environment?
3. **Xác định default:** Khi flag không tồn tại hoặc provider lỗi, hành vi nào an toàn?
4. **Định nghĩa rule:** Allowlist, exclusion, segment, percentage và precedence.
5. **Thiết kế port:** Application core gọi interface trung lập với provider.
6. **Chọn provider:** AWS AppConfig, hệ thống feature management hoặc provider OpenFeature phù hợp.
7. **Thiết lập cache:** TTL, jitter, max-stale, refresh và last-known-good.
8. **Tạo context đáng tin:** Xác thực subject, tenant và các thuộc tính dùng trong rule.
9. **Triển khai code hai nhánh:** Bảo đảm cả nhánh cũ và mới được kiểm thử.
10. **Rollout nội bộ rồi tăng dần:** Theo dõi metric kỹ thuật và nghiệp vụ.
11. **Định nghĩa rollback:** Tắt flag hoặc quay lại version code/config đã biết.
12. **Dọn flag:** Xóa nhánh cũ sau khi rollout kết thúc và ghi nhận owner.

## 24. Checklist trước khi đưa feature flag vào production

- [ ] Mỗi flag có key ổn định, owner, mục đích và thời hạn dự kiến.
- [ ] Flag được phân biệt với runtime configuration và authorization.
- [ ] Default value và hành vi khi provider lỗi đã được xác định.
- [ ] Targeting dùng subject/tenant key ổn định và đáng tin cậy.
- [ ] Không dùng PII hoặc context do client tự khai báo để cấp rollout.
- [ ] Rule precedence và exclusion/allowlist được tài liệu hóa.
- [ ] Percentage rollout dùng bucketing ổn định.
- [ ] Lambda không gọi remote provider ở mỗi invocation nếu không cần.
- [ ] Cache có TTL, jitter, max-stale và fallback.
- [ ] Snapshot được thay thế an toàn khi có invocation đồng thời.
- [ ] Retry của message không vô tình đổi variant nếu nghiệp vụ cần nhất quán.
- [ ] Flag không thay thế kiểm tra quyền ở backend.
- [ ] Có metric và guardrail để dừng rollout khi có sự cố.
- [ ] Quyền chỉnh sửa production flag được giới hạn và audit.
- [ ] Không lưu secret trong flag configuration.
- [ ] Đã kiểm thử ON, OFF, missing, stale, timeout và rule conflict.
- [ ] Có kế hoạch rollback và dọn flag sau rollout.
- [ ] Đã đánh giá tác động latency, cold start, memory và chi phí.

## Kết luận

Feature flag cho phép tách việc triển khai code khỏi việc bật hành vi cho người dùng. Targeting theo allowlist, cohort hoặc phần trăm giúp phát hành có kiểm soát; operational toggle hỗ trợ giảm tác động khi xảy ra sự cố; experiment flag giúp so sánh các biến thể.

Trong serverless, cần dùng định danh ổn định, context đã xác thực và cache có thời hạn vì mỗi execution environment có thể giữ snapshot khác nhau trong một khoảng thời gian. Flag provider nên được bọc sau một port hoặc chuẩn như OpenFeature; AWS AppConfig có thể cung cấp cơ chế quản lý và phân phối cấu hình, còn Lambda extension/agent giúp cache gần function. Luôn xác định default, stale policy, retry behavior, guardrail, quyền quản trị và ngày dọn flag. Feature flag điều khiển hành vi rollout; authorization vẫn phải được thực hiện độc lập ở backend.

