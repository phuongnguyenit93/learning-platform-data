# Ghi nhận phiên bản nguồn cùng lần làm mới gần nhất mà không lộ bí mật

Khi một ứng dụng Spring Boot nhận cấu hình từ Spring Cloud Config, người vận hành cần trả lời được ba câu hỏi: instance đang dùng bộ cấu hình nào, bộ cấu hình đó đến từ phiên bản nguồn nào và lần refresh gần nhất được xử lý lúc nào. Những thông tin này giúp đối chiếu hành vi giữa các replica, điều tra sự cố sau khi thay đổi cấu hình và xác định instance nào chưa cập nhật.

Việc quan sát phải có giới hạn. Config Server có thể trả về database password, token, endpoint nội bộ hoặc thông tin nhạy cảm khác. Không nên expose toàn bộ `Environment`, dump mọi property source hoặc ghi giá trị cấu hình vào log để tìm revision. Hãy tạo một tập metadata không nhạy cảm được cho phép rõ ràng, ghi nhận thời điểm refresh tại từng client và chỉ công bố các trường đã được kiểm duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt phiên bản nguồn cấu hình, label/branch và thời điểm client áp dụng cấu hình.
- Hiểu trường `version` trong response Environment của Config Server và giới hạn khi client cần sử dụng metadata đó.
- Thiết kế metadata không nhạy cảm cho Git, Vault, JDBC, Native và các backend khác.
- Ghi nhận thời điểm tải cấu hình ban đầu và thời điểm refresh gần nhất trên từng instance.
- Dùng `RefreshScopeRefreshedEvent` để cập nhật trạng thái sau khi refresh scope xử lý xong.
- Công bố metadata qua Actuator `InfoContributor` theo allowlist.
- Theo dõi refresh bằng log và Micrometer mà không tạo metric cardinality quá cao.
- Bảo vệ endpoint quan sát và tránh rò rỉ secret qua log, metric, trace hoặc health detail.
- Đối chiếu trạng thái giữa các replica và phát hiện instance bị tụt phiên bản cấu hình.

## 2. Ba mốc thời gian và phiên bản cần phân biệt

Trong hệ thống cấu hình tập trung, các khái niệm sau không đồng nghĩa:

| Thông tin | Ý nghĩa | Nguồn có thể lấy |
| --- | --- | --- |
| Source version | Phiên bản cụ thể của bộ cấu hình ở backend | Git commit SHA, immutable release ID, artifact version hoặc version manifest |
| Label | Tên tham chiếu đến nguồn cấu hình | Git branch, tag hoặc label mà client yêu cầu |
| Published time | Thời điểm bộ cấu hình được phát hành hoặc merge | CI/CD pipeline hoặc metadata release |
| Initial load time | Thời điểm instance nạp cấu hình khi khởi động | Đồng hồ của client sau khi ứng dụng khởi động thành công |
| Last refresh time | Thời điểm instance hoàn tất xử lý một lần refresh | Sự kiện refresh phía client và đồng hồ của instance |

Ví dụ, label `main` có thể trỏ đến nhiều commit khác nhau theo thời gian. Chỉ ghi `label=main` không đủ để xác định chính xác nội dung đã được nạp. Git commit SHA là định danh bất biến tốt hơn cho một revision cụ thể.

Tương tự, thời điểm webhook được nhận tại Config Server không phải thời điểm mọi client đã áp dụng cấu hình. Mỗi client có thể nhận event, tải cấu hình và hoàn tất refresh ở các thời điểm khác nhau. Vì vậy, `lastRefreshAt` nên được ghi tại từng instance.

## 3. Nguồn revision theo từng backend

Không phải backend nào cũng có một kiểu version chung.

| Backend | Metadata nguồn có thể dùng | Lưu ý |
| --- | --- | --- |
| Git | Commit SHA, tag bất biến, release ID và label | Branch là tham chiếu có thể di chuyển; commit SHA xác định nội dung cụ thể |
| Vault KV v2 | Secret version hoặc release ID của bộ cấu hình | Version của từng secret có thể khác nhau; không nhất thiết đại diện một snapshot toàn ứng dụng |
| JDBC | Release ID, batch ID hoặc version manifest | Cần thiết kế schema/transaction để các hàng cấu hình thuộc cùng một lần phát hành |
| Native/filesystem | Artifact version, package digest hoặc manifest revision | Không dùng timestamp file đơn lẻ làm bằng chứng snapshot nhất quán |
| ZooKeeper | Release ID hoặc version manifest của nhóm znode | Stat version/zxid có thể thay đổi riêng từng znode, không nhất thiết là version chung của cả cấu hình |

Với Git backend, Config Server trả metadata `version` trong response `Environment`; backend Git thường điền thông tin revision từ repository. Client có thể dùng response này ở tầng tích hợp hoặc quan sát phía server. Không nên mặc định rằng trường `version` tự trở thành một property bình thường trong Spring `Environment` của mọi Config Client.

Nếu ứng dụng client cần hiển thị revision một cách nhất quán, hãy cung cấp một metadata contract không nhạy cảm như `config.metadata.release-id`. Release pipeline có thể tạo ID bất biến cho lần phát hành cấu hình và đặt nó vào nguồn cấu hình tương ứng. Nếu yêu cầu phải hiển thị chính xác Git commit SHA, hãy triển khai một kênh metadata rõ ràng lấy từ response `Environment` hoặc manifest phát hành có liên kết đến commit SHA; không gắn nhãn một release ID tùy ý thành commit SHA.

## 4. Thiết kế metadata an toàn

Chỉ công bố các trường cần cho vận hành. Ví dụ:

```yaml
config:
  metadata:
    source: git
    release-id: cfg-2026.11.27.3
    label: production-2026.11
    published-at: "2026-11-27T10:30:00Z"
```

Ý nghĩa:

- `source`: loại backend ở mức khái quát, ví dụ `git`, `vault` hoặc `jdbc`.
- `release-id`: mã phát hành cấu hình không nhạy cảm, bất biến trong phạm vi hệ thống.
- `label`: nhãn release được phép hiển thị, không phải URL hoặc đường dẫn nội bộ.
- `published-at`: thời điểm pipeline phát hành snapshot, định dạng ISO-8601 UTC.

Không đưa các thông tin sau vào metadata công khai:

- Password, token, API key, private key hoặc secret value.
- Vault token, secret path nhạy cảm hoặc namespace có thể tiết lộ cấu trúc tenant.
- Git credential, URL repository chứa username/password hoặc thông tin xác thực.
- JDBC URL có username, password hoặc hostname nội bộ nếu không được phép công bố.
- Toàn bộ `Environment`, property source hoặc nội dung YAML đã render.
- Header xác thực, cookie, session ID hoặc dữ liệu người dùng.

Metadata cũng là dữ liệu cấu hình và có thể bị override bởi property source khác. Hãy chọn prefix riêng, kiểm tra nguồn hiệu lực và chỉ cho phép pipeline phát hành cập nhật các trường này.

## 5. Đưa revision vào bộ cấu hình

Một cách đơn giản là pipeline phát hành tạo `release-id` duy nhất và ghi vào context chung hoặc context riêng application.

Ví dụ Config repository:

```yaml
config:
  metadata:
    source: git
    release-id: cfg-2026.11.27.3
    label: production-2026.11
    published-at: "2026-11-27T10:30:00Z"
```

Pipeline nên:

1. Xác định commit hoặc bộ artifact sẽ phát hành.
2. Tạo release ID duy nhất, không tái sử dụng cho nội dung khác.
3. Ghi metadata cùng thay đổi cấu hình hoặc vào manifest phát hành có liên kết rõ ràng đến commit.
4. Kiểm tra metadata không chứa credential hoặc thông tin nội bộ bị cấm.
5. Phát hành bằng tag/label bất biến nếu quy trình hỗ trợ.
6. Ghi lại commit SHA thật trong release record của CI/CD.

Không cố nhúng commit SHA của chính commit đang tạo vào nội dung của commit đó: nội dung file ảnh hưởng đến commit hash, nên việc tự tham chiếu tạo ra vòng phụ thuộc. Có thể dùng release ID được tạo trước commit, rồi để CI/CD lưu liên kết giữa release ID và commit SHA sau khi commit được tạo.

Nếu Config Server đã trả trường `Environment.version`, giữ trường đó như metadata nguồn có thẩm quyền ở phía server. `release-id` trong property source là marker tiện dụng để client và operator đối chiếu; hai giá trị nên được liên kết trong release record.

## 6. Ghi nhận thời điểm nạp ban đầu và refresh

Client nên giữ ít nhất hai mốc:

- `initialLoadedAt`: thời điểm ứng dụng hoàn tất khởi động với cấu hình ban đầu.
- `lastRefreshAt`: thời điểm client hoàn tất xử lý lần refresh gần nhất.

Không đặt `lastRefreshAt` thành thời điểm webhook được gửi hoặc thời điểm Config Server nhận request. Các mốc đó thuộc hệ thống khác và không phản ánh lúc client thực sự xử lý refresh.

Spring Cloud Context cung cấp `RefreshScopeRefreshedEvent` để thông báo refresh scope đã được làm mới. Ứng dụng có thể lắng nghe sự kiện này, đọc revision hiện tại từ `Environment` và cập nhật snapshot quan sát. Thời điểm ghi nhận cần được hiểu là lúc refresh scope đã xử lý việc loại bỏ target đã cache; target `@RefreshScope` mới thường được tạo lười ở lần truy cập tiếp theo.

Ví dụ trạng thái:

```java
import java.time.Instant;

public record ConfigSnapshot(
        String source,
        String releaseId,
        String label,
        Instant initialLoadedAt,
        Instant lastRefreshAt) {
}
```

Lưu snapshot như một đơn vị nguyên tử giúp tránh trường hợp dashboard đọc revision mới nhưng timestamp vẫn thuộc lần refresh trước.

## 7. Theo dõi refresh bằng sự kiện Spring Cloud

Ví dụ dưới đây minh họa một tracker ở phía client. Nó không lưu giá trị cấu hình nghiệp vụ; chỉ đọc allowlist metadata và ghi thời điểm.

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigRefreshState {

    private final Environment environment;
    private final AtomicReference<ConfigSnapshot> current = new AtomicReference<>();

    public ConfigRefreshState(Environment environment) {
        this.environment = environment;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        current.set(readSnapshot(Instant.now(), null));
    }

    @EventListener(RefreshScopeRefreshedEvent.class)
    public void onRefreshScopeRefreshed() {
        ConfigSnapshot previous = current.get();
        Instant initialLoadedAt = previous == null
                ? null : previous.initialLoadedAt();
        current.set(readSnapshot(initialLoadedAt, Instant.now()));
    }

    private ConfigSnapshot readSnapshot(
            Instant initialLoadedAt, Instant lastRefreshAt) {
        return new ConfigSnapshot(
                environment.getProperty("config.metadata.source", "unknown"),
                environment.getProperty("config.metadata.release-id", "unknown"),
                environment.getProperty("config.metadata.label", "unknown"),
                initialLoadedAt,
                lastRefreshAt);
    }

    public ConfigSnapshot current() {
        return current.get();
    }
}
```

Đây là mẫu triển khai cần được kiểm thử với phiên bản Spring Cloud đang dùng. Sự kiện `RefreshScopeRefreshedEvent` gắn với refresh scope; nếu ứng dụng có cơ chế cập nhật `Environment` tùy chỉnh mà không đi qua luồng refresh scope, cần tích hợp tracker vào lifecycle tương ứng. Khi khởi động, `initialLoadedAt` được ghi nhận riêng; `lastRefreshAt` vẫn rỗng cho đến lần refresh đầu tiên.

Không nên cập nhật `lastRefreshAt` khi mới nhận một message Bus hoặc khi request refresh bắt đầu. Chỉ cập nhật sau khi luồng refresh phía client đã đi đến sự kiện hoàn tất mà ứng dụng chọn làm mốc.

## 8. Công bố metadata qua Actuator InfoContributor

Spring Boot Actuator có endpoint `/actuator/info`. Có thể thêm một `InfoContributor` chỉ công bố các trường được cho phép.

```java
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

@Component
public class ConfigInfoContributor implements InfoContributor {

    private final ConfigRefreshState state;

    public ConfigInfoContributor(ConfigRefreshState state) {
        this.state = state;
    }

    @Override
    public void contribute(Info.Builder builder) {
        ConfigSnapshot snapshot = state.current();
        if (snapshot == null) {
            return;
        }

        Map<String, Object> details = new LinkedHashMap<>();
        details.put("source", snapshot.source());
        details.put("releaseId", snapshot.releaseId());
        details.put("label", snapshot.label());
        if (snapshot.initialLoadedAt() != null) {
            details.put("initialLoadedAt",
                    DateTimeFormatter.ISO_INSTANT.format(snapshot.initialLoadedAt()));
        }
        if (snapshot.lastRefreshAt() != null) {
            details.put("lastRefreshAt",
                    DateTimeFormatter.ISO_INSTANT.format(snapshot.lastRefreshAt()));
        }
        builder.withDetail("configuration", details);
    }
}
```

Cấu hình expose endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Response có thể có dạng:

```json
{
  "configuration": {
    "source": "git",
    "releaseId": "cfg-2026.11.27.3",
    "label": "production-2026.11",
    "initialLoadedAt": "2026-11-27T10:35:00Z",
    "lastRefreshAt": "2026-11-27T10:42:18Z"
  }
}
```

Đây là response minh họa. Endpoint Info phải được bảo vệ theo chính sách nội bộ. Nếu metadata revision/label được xem là thông tin nội bộ, chỉ cho phép operator hoặc hệ thống giám sát có xác thực đọc nó. Không expose `/actuator/env` để thay thế InfoContributor vì endpoint đó có thể tiết lộ giá trị cấu hình nhạy cảm.

## 9. Phân biệt refresh event, Environment và bean đã áp dụng

Một refresh có nhiều mốc khác nhau:

1. Config Server nhận thay đổi hoặc client nhận refresh event.
2. Client yêu cầu lại cấu hình và cập nhật `Environment`.
3. Spring Cloud Context phát các sự kiện liên quan đến thay đổi môi trường và refresh scope.
4. Refresh scope loại bỏ target bean đã cache.
5. Lần gọi tiếp theo qua scoped proxy tạo target mới với cấu hình hiện tại.
6. Hành vi nghiệp vụ thực tế được xác minh.

Vì vậy, timestamp từ `RefreshScopeRefreshedEvent` không chứng minh mọi bean trong JVM đã được tạo lại. Bean singleton thông thường có thể giữ giá trị đã đọc lúc khởi tạo; tài nguyên như connection pool có thể cần quy trình thay thế riêng. Nếu cần xác nhận ứng dụng thực sự dùng cấu hình mới, hãy thêm kiểm tra chức năng hoặc version marker ở tầng service.

Tương tự, Bus ACK xác nhận instance nhận event theo cơ chế Bus; nó không tự chứng minh Config Server trả đúng revision hoặc ứng dụng đã áp dụng mọi giá trị.

## 10. Ghi log refresh mà không ghi secret

Log nên giúp liên kết sự kiện giữa Config Server, Bus và client mà không chứa dữ liệu cấu hình.

Ví dụ log an toàn:

```text
INFO config-refresh completed application=orders instance=orders-7f9c
     source=git releaseId=cfg-2026.11.27.3 label=production-2026.11
     lastRefreshAt=2026-11-27T10:42:18Z
```

Nên ghi:

- Application name và instance ID đã được chuẩn hóa.
- Source type và release ID đã được cho phép công bố.
- Label không nhạy cảm.
- Timestamp UTC.
- Event ID hoặc correlation ID nếu có.
- Kết quả xử lý ở mức `success`, `failed` hoặc `unchanged`.

Không ghi:

- Toàn bộ `Environment` hoặc map property source.
- Giá trị của password, token, API key, certificate private key.
- Request/response body chứa cấu hình.
- Header Authorization, cookie hoặc credential của Vault/Git.
- Exception message nguyên văn nếu có khả năng chứa URL có credential hoặc secret.

Khi lỗi, ghi error category và correlation ID; chi tiết nhạy cảm cần được loại bỏ hoặc giữ trong hệ thống có quyền truy cập hạn chế.

## 11. Metric cho refresh và revision

Metric nên tập trung vào trạng thái vận hành và giữ cardinality thấp.

Các metric tùy chỉnh có thể gồm:

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| `config.refresh.success` | Counter | Số lần refresh scope hoàn tất |
| `config.refresh.failure` | Counter | Số lần refresh thất bại được instrumentation ghi nhận |
| `config.refresh.last.success.epoch` | Gauge | Thời điểm refresh thành công gần nhất dưới dạng epoch seconds/milliseconds |
| `config.refresh.duration` | Timer | Thời gian xử lý refresh nếu có điểm đo phù hợp |
| `config.revision.mismatch` | Counter/Gauge | Số lần phát hiện revision giữa instance không đồng nhất |

Đây là tên metric minh họa, không phải metric mặc định được Spring Cloud Config tự cung cấp. Ứng dụng cần đăng ký Micrometer instrumentation.

Không đưa Git commit SHA, release ID hoặc label có hàng nghìn giá trị vào metric tag nếu chúng làm tăng cardinality. Hãy để revision trong Info endpoint, log hoặc deployment inventory. Metric tag nên giới hạn ở `application`, `environment`, `result` và các giá trị có tập hữu hạn.

Ví dụ counter:

```java
Counter.builder("config.refresh.events")
        .tag("result", "success")
        .tag("application", "orders")
        .register(meterRegistry)
        .increment();
```

Counter thành công có thể tăng tại listener refresh hoàn tất. Counter thất bại cần được tăng ở điểm phát hiện lỗi thực tế trong luồng refresh hoặc integration layer; không suy luận thất bại chỉ vì không thấy event success.

## 12. Theo dõi nhiều instance và phát hiện cấu hình lệch phiên bản

Mỗi replica nên công bố snapshot riêng. Một dashboard hoặc hệ thống giám sát có thể thu thập:

| Instance | Release ID | Label | Last refresh (UTC) | Trạng thái |
| --- | --- | --- | --- | --- |
| `orders-a` | `cfg-2026.11.27.3` | `production-2026.11` | `10:42:18Z` | Đồng nhất |
| `orders-b` | `cfg-2026.11.27.3` | `production-2026.11` | `10:42:21Z` | Đồng nhất |
| `orders-c` | `cfg-2026.11.20.1` | `production-2026.11` | `09:15:02Z` | Cần kiểm tra |

Trong ví dụ, instance `orders-c` đang dùng release cũ. Có thể do:

- Instance không nhận được refresh event.
- Bus consumer hoặc HTTP notifier bị lỗi.
- Client không gọi được Config Server.
- Config Server replica trả cấu hình cũ do Git clone/cache hoặc backend lag.
- Refresh thất bại trước khi metadata được cập nhật.
- Instance chưa được restart sau một thay đổi không hỗ trợ refresh.

Nên có ngưỡng cảnh báo cho độ lệch thời gian refresh và revision. Không so sánh timestamp đơn lẻ để kết luận revision mới hơn; hãy so sánh release ID hoặc source revision theo quy tắc phát hành.

## 13. Timestamp và đồng bộ đồng hồ

`lastRefreshAt` được ghi bằng đồng hồ của client instance. Nếu các máy lệch giờ, dashboard có thể hiển thị thứ tự refresh sai.

Các nguyên tắc:

- Dùng UTC và định dạng ISO-8601, ví dụ `2026-11-27T10:42:18Z`.
- Đồng bộ đồng hồ bằng NTP hoặc cơ chế time synchronization của nền tảng.
- Không dùng local timezone để so sánh giữa region.
- Phân biệt `publishedAt` do pipeline ghi với `lastRefreshAt` do client ghi.
- Không lấy `publishedAt` làm bằng chứng client đã nạp cấu hình.
- Nếu cần đo duration, dùng monotonic clock cho khoảng thời gian; dùng wall-clock UTC để ghi timestamp.

Khi container được tạo lại, trạng thái in-memory của tracker bắt đầu lại. Nếu cần lịch sử refresh lâu dài, gửi event/metric/log đến hệ thống observability tập trung thay vì chỉ giữ snapshot trong JVM.

## 14. Bảo vệ endpoint metadata

`/actuator/info` thường ít nhạy cảm hơn `/actuator/env`, nhưng vẫn có thể tiết lộ tên service, release, label hoặc topology. Hãy phân loại metadata trước khi expose.

Biện pháp:

- Chỉ include endpoint `info` khi có nhu cầu.
- Dùng Spring Security hoặc gateway để yêu cầu xác thực và phân quyền.
- Tách management port/network nếu chính sách yêu cầu.
- Chỉ dùng `InfoContributor` allowlist; không tự động dump toàn bộ properties.
- Không cho phép client bên ngoài tùy ý chọn application hoặc revision để truy vấn metadata nội bộ.
- Không để error detail hoặc health detail chứa cấu hình bí mật.
- Kiểm tra log/trace của reverse proxy và monitoring agent để bảo đảm response không bị lưu trữ rộng hơn dự kiến.

Ví dụ bảo vệ endpoint bằng security là phần cấu hình riêng của ứng dụng; việc expose `info` trong Actuator không tự tạo authentication hoặc authorization.

## 15. Refresh thất bại và cách giữ trạng thái chính xác

Tracker nên phân biệt lần refresh gần nhất thành công với lần thử gần nhất.

Một snapshot mở rộng có thể gồm:

```java
public record ConfigRefreshStatus(
        String releaseId,
        Instant lastSuccessfulRefreshAt,
        Instant lastAttemptAt,
        String lastResult,
        String lastErrorCategory) {
}
```

Quy tắc:

- Chỉ cập nhật `lastSuccessfulRefreshAt` khi luồng refresh hoàn tất theo mốc được chọn.
- Ghi `lastAttemptAt` ở điểm bắt đầu refresh nếu ứng dụng có hook đáng tin cậy.
- Khi lỗi, giữ revision đang áp dụng và thời điểm thành công cũ.
- Ghi `lastResult=failed` cùng error category không nhạy cảm.
- Không thay revision đang áp dụng chỉ vì Config Server hoặc Git đã có phiên bản mới.
- Khi client fetch được cấu hình mới nhưng bean/tài nguyên áp dụng thất bại, cần có trạng thái riêng để phân biệt `environment-refreshed` với `application-verified`.

Nếu chỉ dùng `RefreshScopeRefreshedEvent`, tracker có thể ghi nhận refresh scope đã được xử lý. Để đo failure chính xác, cần instrument thêm điểm gọi refresh hoặc integration layer có thể quan sát exception; không suy luận mọi trường hợp thiếu event đều là failure vì có thể không có lần refresh nào được yêu cầu.

## 16. Chẩn đoán khi revision hoặc timestamp không đúng

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Revision trên client không đổi sau refresh | Metadata property chưa được cập nhật hoặc client chưa fetch cấu hình mới | Kiểm tra response Config Server, event và property source hiệu lực |
| Config Server revision mới nhưng client revision cũ | Client không nhận event hoặc refresh lỗi | Kiểm tra Bus ACK, HTTP notifier, client log và network |
| Revision giống nhau nhưng giá trị nghiệp vụ khác | Override từ biến môi trường/local property source hoặc metadata không đồng bộ | Kiểm tra nguồn ưu tiên và synthetic test |
| Last refresh timestamp mới nhưng bean vẫn dùng giá trị cũ | Bean singleton giữ state hoặc target refresh-scoped chưa được gọi lại | Kiểm tra bean lifecycle và hành vi qua proxy |
| Timestamp giữa replica sai thứ tự | Đồng hồ hệ thống lệch | Kiểm tra NTP và timezone |
| `/actuator/info` lộ thông tin nhạy cảm | Contributor hoặc InfoContributor khác đưa quá nhiều dữ liệu | Giới hạn allowlist và rà soát endpoint security |
| Metric tăng bất thường | Refresh loop, webhook duplicate hoặc Bus event lặp | Đối chiếu event ID, rate, broker và pipeline |
| Dashboard có revision cardinality quá lớn | Đưa commit SHA/release ID vào metric tag | Chuyển revision sang log/info và giữ metric tag có tập hữu hạn |
| Không có `lastRefreshAt` | Instance mới khởi động nhưng chưa refresh, hoặc event listener chưa được kích hoạt | Hiển thị `null`/`never` thay vì tự điền timestamp giả |

## 17. Quy trình triển khai quan sát revision và refresh

1. **Chọn source identifier:** xác định Git SHA, tag, Vault version, artifact ID hoặc release ID phù hợp backend.
2. **Thiết kế metadata contract:** chọn `source`, `release-id`, `label` và `published-at`; phân loại trường nào được công bố.
3. **Tích hợp pipeline:** tạo release ID và liên kết nó với source revision thật trong release record.
4. **Nạp metadata:** đưa marker không nhạy cảm vào property source hoặc kênh metadata riêng.
5. **Tạo refresh tracker:** ghi initial load và nghe sự kiện refresh phù hợp phiên bản.
6. **Lưu snapshot nguyên tử:** cập nhật revision và timestamp trong cùng một object.
7. **Công bố allowlist:** dùng InfoContributor hoặc endpoint nội bộ đã bảo vệ.
8. **Thêm telemetry:** log event có correlation ID, metric success/failure và last-success timestamp.
9. **Kiểm tra security:** thử truy cập bằng danh tính không có quyền và xác nhận không đọc được metadata nội bộ ngoài chính sách.
10. **Kiểm thử nhiều replica:** phát một thay đổi cấu hình, đối chiếu revision và timestamp trên từng instance.
11. **Kiểm thử lỗi:** ngắt Config Server/broker có kiểm soát và xác nhận last successful refresh không bị ghi đè sai.
12. **Thiết lập cảnh báo:** cảnh báo revision lệch, refresh quá lâu hoặc refresh failure tăng.

## 18. Checklist production

- [ ] Có định nghĩa rõ source version, label, published time và client refresh time.
- [ ] Git commit SHA không bị nhầm với branch/label hoặc release ID.
- [ ] Với backend không có commit SHA, có release ID/version manifest bất biến.
- [ ] Metadata được allowlist và không chứa secret, credential hoặc đường dẫn nhạy cảm.
- [ ] Pipeline liên kết release ID với source revision thực tế.
- [ ] Client ghi initial load và last successful refresh riêng biệt.
- [ ] Refresh timestamp được ghi sau mốc xử lý refresh đã chọn, không phải lúc nhận webhook/Bus message.
- [ ] Snapshot revision và timestamp được cập nhật nguyên tử.
- [ ] Endpoint Info chỉ công bố trường đã duyệt và được bảo vệ.
- [ ] Không expose `/actuator/env` hoặc dump toàn bộ property source để quan sát revision.
- [ ] Log không ghi giá trị cấu hình, token, password hoặc response body.
- [ ] Metric tag có cardinality thấp; revision không được dùng làm tag không giới hạn.
- [ ] Đồng hồ instance đồng bộ và timestamp dùng UTC.
- [ ] Có cách so sánh revision giữa tất cả replica.
- [ ] Có cảnh báo khi instance tụt revision hoặc quá lâu chưa refresh.
- [ ] Đã kiểm thử trường hợp refresh thất bại và giữ nguyên trạng thái thành công gần nhất.
- [ ] Đã xác minh hành vi bean sau refresh, không chỉ kiểm tra metadata.

## 19. Tài liệu tham khảo

- [Spring Cloud Config — Environment Repository and Environment Response](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Cloud Commons — Refresh Scope and Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Boot Actuator — Application Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Cloud Bus — Event Tracing](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/configuration.html)
