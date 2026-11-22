# Cập nhật cấu hình động và khả năng quay về phiên bản trước

**Phạm vi:** Cấu hình và bí mật trong kiến trúc hệ thống, ứng dụng phân tán và microservices.

Một dịch vụ có thể được triển khai thành công nhưng vẫn cần điều chỉnh giới hạn lưu lượng, timeout, số kết nối, tuyến gọi downstream hoặc trạng thái bật/tắt tính năng trong lúc đang chạy. Nếu mọi thay đổi nhỏ đều phải build và triển khai lại, thời gian phản ứng với sự cố sẽ dài. Tuy nhiên, khi một giá trị cấu hình sai được phát tán đến hàng chục instance, hậu quả có thể nhanh và rộng hơn một lỗi code thông thường.

**Cập nhật cấu hình động (dynamic configuration)** là cơ chế đưa các giá trị cấu hình mới vào tiến trình đang chạy theo một hợp đồng rõ ràng. **Quay về phiên bản trước (rollback)** là khả năng phục hồi bộ giá trị đã biết là tốt khi bản cấu hình mới gây lỗi, đồng thời vẫn bảo đảm lịch sử thay đổi, quyền quản trị và tính nhất quán.

Bài học này giải thích cách phân loại cấu hình, mô hình lưu và phân phối phiên bản, phương pháp áp dụng an toàn, kiểm soát lệch phiên bản giữa các instance, cơ chế canary và rollback, bảo mật bí mật, cùng một ví dụ Java minh họa việc đổi cấu hình nguyên tử trong bộ nhớ.

## 1. Vì sao cấu hình là một phần của hành vi hệ thống?

Giả sử Checkout Service đang chạy trên 12 instance. Mỗi instance gọi Payment Service với timeout 2 giây. Nhóm vận hành muốn giảm timeout còn 500 ms để tránh giữ kết nối quá lâu.

Nếu cập nhật đồng thời tất cả instance mà không đo tác động, những giao dịch hợp lệ mất 700 ms có thể bắt đầu thất bại hàng loạt. Nếu một nửa instance dùng 500 ms và nửa còn lại dùng 2 giây, cùng một thao tác có thể có hành vi khác nhau tùy instance nhận request. Nếu rollback chỉ đổi một file trên máy quản trị nhưng các instance tiếp tục giữ cache cũ, sự cố vẫn kéo dài.

Cấu hình vì vậy có ít nhất năm chiều cần thiết kế:

1. **Giá trị:** timeout, quota, feature flag, endpoint, bộ tham số xử lý.
2. **Phạm vi:** toàn hệ thống, môi trường, dịch vụ, tenant, vùng địa lý, instance hoặc nhóm người dùng.
3. **Phiên bản:** bản nào là nguồn được phê duyệt, bản nào đang có hiệu lực trên từng instance.
4. **Thời điểm hiệu lực:** lúc khởi động, lúc nhận cập nhật, lúc bắt đầu request hoặc sau khi tài nguyên liên quan được thay thế.
5. **Khả năng phục hồi:** điều kiện từ chối bản sai, cách quay về bản tốt và hành vi khi nơi cung cấp cấu hình không truy cập được.

Một thiết kế tốt không chỉ trả lời “đọc cấu hình ở đâu” mà còn trả lời **“ai đổi được, thay đổi được kiểm chứng ra sao, những tiến trình nào đã nhận, và làm thế nào phục hồi khi sai?”**.

## 2. Mô hình tổng thể: nguồn cấu hình, bộ điều khiển và các dịch vụ

~~~mermaid
flowchart LR
    O["Người vận hành / pipeline"] --> A["Phê duyệt + kiểm tra"]
    A --> R[("Kho cấu hình có phiên bản")]
    R --> D["Bộ phân phối / watch / poll"]
    D --> S1["Service instance A"]
    D --> S2["Service instance B"]
    D --> S3["Service instance C"]
    S1 --> M["Metrics + audit"]
    S2 --> M
    S3 --> M
    M --> G{"Đạt ngưỡng an toàn?"}
    G -->|Không| B["Tạo bản phục hồi từ bản tốt"]
    B --> R
~~~

Các trách nhiệm phải tách biệt:

- **Nguồn cấu hình có phiên bản:** lưu bản được phê duyệt, phạm vi và lịch sử; không mất dấu vì ai đó sửa trực tiếp trên một máy.
- **Đường điều khiển (control plane):** xác thực người thay đổi, kiểm tra schema, quản lý rollout, ghi audit, đặt bản mong muốn.
- **Đường xử lý (data plane):** các instance thực thi request và dùng bản cấu hình đã áp dụng.
- **Kênh phân phối:** thông báo sự thay đổi, cung cấp snapshot mới, xử lý lỗi mạng và đồng bộ lại.
- **Quan sát:** báo bản mong muốn và bản đã áp dụng, mức lệch, lỗi validation và ảnh hưởng đến SLO.

Một cấu hình vừa được lưu vào kho mới là **desired state**. Nó chưa chứng minh mọi instance đã chuyển sang **applied/effective state**. Cần theo dõi hai trạng thái riêng.

## 3. Phân loại: không phải giá trị nào cũng đổi an toàn lúc chạy

| Loại cấu hình | Ví dụ | Cách thay đổi thường phù hợp |
|---|---|---|
| **Bất biến theo bản build** | Định dạng dữ liệu đã biên dịch, phiên bản protocol không tương thích | Đổi code, kiểm thử và triển khai bản ứng dụng mới |
| **Cần khởi động lại** | Một số thuộc tính JVM, port bind, thiết lập framework khởi tạo một lần | Rolling restart/rolling deployment có kiểm soát |
| **Có thể nạp lại tại chỗ** | Timeout request, tỷ lệ sampling, quota hoặc hạn mức của bộ điều phối đã hỗ trợ | Reload, validate rồi đổi snapshot hoặc cập nhật đối tượng an toàn |
| **Feature flag** | Bật chế độ mới, chuyển thuật toán theo cohort | Đánh giá theo request/tenant; bật dần và có kill switch |
| **Cấu hình gắn tài nguyên có trạng thái** | DB pool size, TLS truststore, endpoint của client dài hạn | Khởi tạo tài nguyên mới, kiểm tra, chuyển lưu lượng rồi đóng tài nguyên cũ |
| **Bí mật (secret)** | Token API, password, certificate, private key | Cơ chế secret rotation có overlap và khả năng thu hồi |

Cần ghi rõ cho từng khóa:

- Kiểu dữ liệu, đơn vị, giá trị mặc định, min/max và quan hệ với khóa khác.
- Dịch vụ/nhóm chịu trách nhiệm và phạm vi môi trường.
- Có hỗ trợ hot reload không, nếu có thì điểm có hiệu lực cụ thể.
- Có thể rollback độc lập hay phải phối hợp với thay đổi schema, code hoặc tài nguyên bên ngoài.
- Độ nhạy: public, internal, confidential hay secret.
- Ngưỡng an toàn và chỉ số theo dõi sau khi áp dụng.

**Không gọi một giá trị là “dynamic” chỉ vì sửa được trong ConfigMap hoặc file YAML.** Nếu thư viện chỉ đọc một lần khi khởi động, sửa nguồn dữ liệu sẽ không thay đổi hành vi của tiến trình. Phải có cơ chế nạp lại và áp dụng vào đúng thành phần thực thi.

## 4. Thiết kế cấu hình có schema và ràng buộc

Cấu hình là đầu vào điều khiển chương trình, nên cần validate giống như một API quan trọng. Ví dụ:

~~~yaml
# Checkout Service - cấu hình nghiệp vụ, không chứa bí mật
service: checkout
environment: production
revision: 42
schemaVersion: 3
policy:
  paymentTimeoutMs: 1500
  maxInFlightPayments: 80
  retry:
    maxAttempts: 2
    backoffBaseMs: 100
  recommendationsEnabled: true
~~~

Kiểm tra cần thực hiện trước khi công bố hoặc áp dụng:

1. **Cú pháp và kiểu:** số nguyên đúng kiểu, boolean thực sự là boolean, tên khóa hợp lệ.
2. **Đơn vị:** phân biệt mili giây với giây; tránh trường hợp gửi 5 thay vì 5000.
3. **Giới hạn:** timeout phải dương, quota không vượt năng lực đã được đánh giá.
4. **Quan hệ giữa các khóa:** thời gian retry phải phù hợp deadline tổng thể; maxInFlight không được đặt quá khả năng DB.
5. **Tương thích schema:** phiên bản ứng dụng đang chạy có hiểu schema mới hay không.
6. **Phạm vi:** config production không thể vô tình đi vào staging hoặc tenant khác.
7. **An toàn nghiệp vụ:** bật tính năng mới phải có migration/schema/consumer hỗ trợ trước.
8. **Chính sách bảo mật:** không chứa password/token ở kho cấu hình phổ thông, không hạ xác minh TLS qua flag tùy ý.

Dùng kiểu dữ liệu rõ ràng thay vì chỉ lưu các chuỗi không có đơn vị. Ví dụ, đặt tên **paymentTimeoutMs** hoặc khai báo kiểu duration có quy ước định dạng. Một số giới hạn cần kiểm tra theo năng lực cụm thay vì chỉ kiểm tra giá trị min/max của một instance.

**Schema validation không thay thế canary:** giá trị 500 ms vẫn hợp lệ về kiểu nhưng có thể sai về vận hành nếu p99 của Payment Service là 800 ms.

## 5. Nguồn cấu hình và thứ tự ưu tiên

Một hệ thống thường kết hợp nhiều nguồn:

- Giá trị mặc định trong mã nguồn hoặc tài nguyên đi kèm bản build.
- File cấu hình theo môi trường.
- Biến môi trường hoặc tham số khởi động.
- Kho cấu hình tập trung với bản phát hành có phiên bản.
- Cơ chế override có thời hạn cho sự cố.
- Kho bí mật riêng cho thông tin xác thực.

Cần định nghĩa **thứ tự ưu tiên và quyền sở hữu khóa**. Nếu cùng một khóa có giá trị 2 giây trong file nhưng 500 ms trong kho tập trung, phải biết nguồn nào có hiệu lực và tại sao. Tránh nhiều bộ điều khiển cùng ghi một khóa rồi phụ thuộc thứ tự nhận sự kiện.

Ví dụ chính sách có thể là: default trong ứng dụng → cấu hình môi trường đã được duyệt → override tạm thời có TTL. Đây chỉ là một lựa chọn thiết kế; Spring Boot, Kubernetes hay từng hệ thống cấu hình có quy tắc ưu tiên riêng. Không tự áp dụng một thứ tự tổng quát cho mọi framework.

Nên hỗ trợ **config provenance**: với mỗi khóa, có thể truy vết bản nguồn, phiên bản, phạm vi áp dụng và tác nhân thay đổi, nhưng không lộ giá trị bí mật.

### 5.1. Kết hợp các lớp cấu hình

Nếu cấu hình có nhiều lớp như global, region, tenant, cần quy định merge ở mức nào:

~~~text
Global defaults
    |
    +-- Region: ap-southeast
          |
          +-- Service: checkout
                |
                +-- Tenant: enterprise-a
~~~

Đừng suy ra rằng “tenant override” luôn an toàn. Một tenant không được phép vượt global hard limit, thay đích gửi dữ liệu ra ngoài hoặc tắt cơ chế xác thực bằng một override tự phục vụ. Mỗi lớp cần giới hạn những khóa có thể ghi.

Cấu hình có thứ bậc và override dễ tạo trạng thái khó giải thích. Vì vậy, khi điều tra sự cố cần xem được **effective config** đã chuẩn hóa, có che bí mật, tại đúng instance và thời điểm.

## 6. Phiên bản bất biến: nền tảng cho rollback có thể tin cậy

Một bản cấu hình nên là snapshot bất biến, kèm metadata:

~~~json
{
  "service": "checkout",
  "environment": "production",
  "revision": 43,
  "schemaVersion": 3,
  "releaseId": "cfg-checkout-prod-43",
  "contentDigest": "sha256:example-digest",
  "basedOnRevision": 42,
  "changeReason": "Giảm thời gian chờ Payment",
  "createdAt": "2026-11-12T02:00:00Z",
  "payload": {
    "paymentTimeoutMs": 500,
    "maxInFlightPayments": 80,
    "recommendationsEnabled": true
  }
}
~~~

**Revision** là số thứ tự của lần phát hành cấu hình, **content digest** giúp kiểm tra tính toàn vẹn snapshot. Giá trị digest trong ví dụ chỉ minh họa, không phải hash thực. Bản phát hành nên được lưu bất biến và có dấu vết người duyệt/thay đổi.

Ví dụ chuỗi:

| Revision | Timeout | Trạng thái | Ý nghĩa |
|---|---:|---|---|
| 42 | 1500 ms | Đã biết tốt | Trước thay đổi |
| 43 | 500 ms | Gây tăng timeout | Bản thử nghiệm lỗi |
| 44 | 1500 ms | Bản phục hồi | **Payload của 42** với revision phát hành mới |

Một nguyên tắc quan trọng: **rollback không nhất thiết làm revision chạy lùi từ 43 về 42**. Trong hệ thống phân tán, client thường bỏ qua bản đến có revision nhỏ hơn để chống thông báo trễ. Vì vậy, nên **phát hành revision 44 chứa payload đã biết tốt của 42**, kèm metadata **rollbackOf=43** hoặc **restoredFrom=42**. Lịch sử vẫn tăng một chiều, trong khi hành vi quay về giá trị trước.

Không sửa nội dung của revision 42 hoặc 43 sau khi công bố. Nếu cùng ID nhưng payload thay đổi, cache, audit và kiểm tra checksum mất ý nghĩa.

### 6.1. Chống ghi đè từ hai người cùng lúc

Giả sử Alice và Bob đều chỉnh từ revision 42. Alice phát hành 43, Bob gửi thay đổi dựa trên 42; nếu kho chấp nhận ghi đè mù, thay đổi của Alice có thể biến mất.

Giải pháp là **optimistic concurrency / compare-and-swap**: mỗi thay đổi mang **expectedRevision=42**. Kho chỉ chấp nhận nếu currentRevision vẫn là 42; nếu đã là 43 thì yêu cầu tạo lại bản đề xuất dựa trên 43. Các API có thể dùng version, ETag, resourceVersion hoặc giao dịch cơ sở dữ liệu phù hợp.

Chống xung đột ở nơi công bố và chống áp dụng bản cũ trên instance là hai vấn đề riêng. Nên có cả hai.

## 7. Phân phối cập nhật: polling, watch và push

| Cách phân phối | Nguyên lý | Ưu điểm | Rủi ro cần xử lý |
|---|---|---|---|
| **Polling** | Instance hỏi kho theo chu kỳ | Đơn giản, dễ giám sát | Độ trễ nhận bản, nhiều request; cần jitter và conditional fetch |
| **Long polling / watch** | Giữ kết nối nhận tín hiệu thay đổi | Phản ứng nhanh | Đứt kết nối, reconnect storm, sự kiện bỏ lỡ |
| **Push / pub-sub** | Bộ điều khiển phát sự kiện có bản mới | Giảm thời gian phát hiện | Duplicate, out-of-order, mất thông báo; vẫn cần truy vấn snapshot |
| **File reload** | Watch file hoặc volume được cập nhật | Phù hợp một số môi trường | Atomic rename, sự kiện file, thư viện chỉ đọc khi startup |
| **Restart/rolling deployment** | Khởi động process mới với cấu hình mới | Rõ phạm vi vòng đời | Tốn thời gian, cần bảo đảm capacity và readiness |

Thông báo “revision 44 đã có” chỉ nên là **tín hiệu**. Instance cần tải **snapshot hoàn chỉnh**, kiểm tra schema/hash, rồi áp dụng theo thứ tự revision. Không dựa vào mọi sự kiện notification đều được giao đúng một lần.

Một vòng lặp đồng bộ ví dụ:

~~~text
onNotification(version):
    target = queryDesiredRevision()
    if target <= locallyAppliedRevision:
        return

    snapshot = fetchImmutableSnapshot(target)
    verifyIdentityScopeAndDigest(snapshot)
    candidate = parseAndValidate(snapshot)

    if candidate is not compatible with this app:
        reportRejected(target, "SCHEMA_INCOMPATIBLE")
        keepLastKnownGood()
        return

    if candidate contains lifecycle changes:
        prepareReplacementResources(candidate)
        switchAtSafeBoundary(candidate)
    else:
        atomicallyReplaceRuntimeSnapshot(candidate)

    reportAppliedRevision(target)
~~~

Cần xử lý thêm tình huống thông báo 43 đến sau khi instance đã áp dụng 44, reconnect từ trạng thái 40 lên 44, nhận cùng sự kiện hai lần hoặc kho tạm ngừng hoạt động. **Không giả định thứ tự sự kiện trên mọi kênh bằng thứ tự phiên bản đã công bố.**

### 7.1. Tính nhất quán giữa các instance

Trong vài giây hoặc phút của rollout, các instance có thể dùng revision khác nhau. Đây là **eventual convergence** nếu kiến trúc cho phép; không có một giao dịch nguyên tử trên toàn cụm chỉ nhờ dùng kho cấu hình chung.

Nếu tác vụ nghiệp vụ yêu cầu cùng chính sách từ đầu đến cuối, có thể:

- Gắn **policyVersion** vào request/job được xử lý để chọn đúng snapshot tương thích.
- Chốt snapshot tại đầu request và sử dụng nhất quán trong request.
- Triển khai theo nhóm tương thích, tránh mix những phiên bản làm thay đổi wire contract.
- Dùng cơ chế đồng bộ hoặc dừng nhận công việc có kiểm soát khi cần một cutover nghiêm ngặt.
- Tách những thay đổi không tương thích thành rollout code/data nhiều bước thay vì ép hot reload.

Không cố tạo sự nhất quán tuyệt đối trên toàn cụm cho mọi flag; chi phí và độ phức tạp có thể vượt lợi ích. Cần phân loại theo tác động.

## 8. Áp dụng nguyên tử trong một tiến trình

Một lỗi điển hình là cập nhật từng biến cấu hình riêng lẻ:

~~~text
maxRetries = 1       # đọc mới
requestTimeout = 200 # vẫn cũ trong một thời điểm
backoffMs = 500       # còn cũ
~~~

Nếu các biến có quan hệ, request có thể quan sát tổ hợp chưa từng được duyệt. Cách tốt hơn là **tạo và validate một snapshot bất biến**, sau đó đổi tham chiếu nguyên tử.

Ví dụ Java 21:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

record RetryPolicy(int maxAttempts, Duration backoff) {
    RetryPolicy {
        if (maxAttempts < 1 || maxAttempts > 5) {
            throw new IllegalArgumentException("maxAttempts out of range");
        }
        if (backoff.isNegative()) {
            throw new IllegalArgumentException("backoff must be non-negative");
        }
    }
}

record CheckoutPolicy(
        long revision,
        Duration paymentTimeout,
        int maxInFlight,
        RetryPolicy retryPolicy,
        boolean recommendationsEnabled) {

    CheckoutPolicy {
        if (revision < 1) {
            throw new IllegalArgumentException("revision must be positive");
        }
        if (paymentTimeout.compareTo(Duration.ofMillis(100)) < 0 ||
            paymentTimeout.compareTo(Duration.ofSeconds(10)) > 0) {
            throw new IllegalArgumentException("paymentTimeout out of range");
        }
        if (maxInFlight < 1 || maxInFlight > 500) {
            throw new IllegalArgumentException("maxInFlight out of range");
        }
        if (retryPolicy == null) {
            throw new IllegalArgumentException("retryPolicy required");
        }
        // Các ràng buộc liên trường được thêm theo hợp đồng nghiệp vụ.
    }
}

final class LiveConfig {
    private final AtomicReference<CheckoutPolicy> current;

    LiveConfig(CheckoutPolicy initial) {
        this.current = new AtomicReference<>(initial);
    }

    CheckoutPolicy snapshot() {
        return current.get();
    }

    boolean apply(CheckoutPolicy next) {
        while (true) {
            CheckoutPolicy previous = current.get();

            // Notification trễ/đến lặp không được ghi đè revision mới.
            if (next.revision() <= previous.revision()) {
                return false;
            }
            if (current.compareAndSet(previous, next)) {
                return true;
            }
        }
    }
}
~~~

Sử dụng snapshot trong một request:

~~~java
CheckoutPolicy policy = liveConfig.snapshot();

Duration timeout = policy.paymentTimeout();
RetryPolicy retry = policy.retryPolicy();

// Cùng một request dùng bộ giá trị của một revision.
paymentClient.call(orderId, timeout, retry);
~~~

Điều ví dụ này **thực sự bảo đảm** là một request lấy bộ giá trị nhất quán tại thời điểm đọc tham chiếu. Nó **không tự** thay đổi kích thước connection pool đã khởi tạo, số worker đang chạy, timeout được giữ trong một HTTP client khác hoặc chính sách ở instance bên cạnh. Những tài nguyên đó cần cơ chế cập nhật riêng.

Ngoài ra, quá trình tải, xác minh chữ ký/checksum, parse, validate và chuẩn bị tài nguyên nên hoàn tất **trước khi** gọi apply. Không sử dụng CAS như một cách thay thế validation hoặc quyền kiểm soát tại control plane.

### 8.1. Điểm hiệu lực: giữa request hay giữa giai đoạn?

Có ba cách áp dụng thường gặp:

- **Read-per-operation:** mỗi thao tác lấy snapshot mới; phản ứng nhanh nhưng một giao dịch nhiều bước có thể nhìn thấy hai revision.
- **Read-once-per-request:** snapshot tại đầu request; phù hợp khi cần nhất quán trong một request HTTP.
- **Pinned-per-job / policyVersion:** tác vụ dài lưu revision hoặc dùng snapshot đã chốt cho đến khi hoàn tất; phù hợp workflow, tính phí và xử lý có tính lặp.

Chọn điểm hiệu lực theo ngữ nghĩa nghiệp vụ. Với thay đổi bảo mật khẩn cấp như thu hồi quyền, có thể cần cơ chế kiểm tra hiện thời ở ranh giới nhạy cảm thay vì chỉ chốt quyền tại đầu một job kéo dài hàng giờ.

## 9. Cấu hình gắn với tài nguyên sống: thay tham chiếu không đủ

Một số khóa thay đổi hành vi của một đối tượng đã được tạo:

- Kích thước connection pool.
- HTTP client, DNS resolver, retry interceptor.
- TLS certificate/truststore.
- Thread pool, scheduler hoặc rate limiter lưu trạng thái.
- Endpoint đang duy trì kết nối lâu dài.
- Cache có TTL và dữ liệu chứa bởi phiên bản cũ.

Trường hợp này cần một quy trình **prepare → validate → switch → drain → dispose**:

1. Chuẩn bị tài nguyên mới với cấu hình đề xuất, không ảnh hưởng luồng hiện tại.
2. Kiểm tra kết nối, handshake, quyền, giới hạn tài nguyên và readiness.
3. Chuyển các request mới sang tài nguyên mới bằng tham chiếu nguyên tử hoặc router có quản lý vòng đời.
4. Cho phép request đang dùng tài nguyên cũ kết thúc trong deadline phù hợp.
5. Đóng và giải phóng tài nguyên cũ; báo lỗi nếu quá trình drain thất bại.

Ví dụ đổi đích Payment API từ endpoint A sang B: thay string endpoint trong config không làm một HTTP client đang giữ pool tới A tự chuyển sang B. Nếu code tự tạo client mới cho mọi request, nó lại có nguy cơ rò connection hoặc tạo quá nhiều socket. Cần tầng quản lý tài nguyên rõ ràng.

Với giá trị có side effect ngay lập tức, ví dụ tăng maxInFlight, cần xác định limiter sử dụng snapshot mới thế nào khi đã có permit đang giữ. Không thay đổi một semaphore bằng cách tạo mới và quên permit cũ; có thể làm mất giới hạn tổng trong thời điểm chuyển đổi.

## 10. Feature flag và cấu hình hệ thống khác nhau ở đâu?

Feature flag thường quyết định bật một nhánh hành vi theo request, user, tenant, region hoặc cohort. Một số dạng:

- **Release flag:** bật dần một chức năng đã được triển khai.
- **Kill switch:** tắt nhanh phần tùy chọn gây sự cố.
- **Experiment flag:** phân nhóm A/B và giữ phân bổ ổn định.
- **Ops flag:** chuyển chế độ vận hành như dùng cache phụ hoặc chặn tác vụ batch.

Ví dụ chính sách:

~~~yaml
revision: 52
featureFlags:
  newCheckout:
    enabled: true
    rolloutPercent: 5
    stableKey: customerId
    allowlistedTenants:
      - test-tenant
  recommendations:
    enabled: false
~~~

Nếu rolloutPercent=5 được tính lại ngẫu nhiên cho mọi request, cùng một user có thể lúc thấy tính năng mới, lúc thấy tính năng cũ. Nên dùng **hash ổn định trên khóa phân nhóm và tên flag** để kết quả tương đối nhất quán trong một giai đoạn; bảo vệ độ riêng tư của khóa phân nhóm và không tiết lộ dữ liệu cá nhân trong log.

Một kill switch chỉ hữu ích khi code còn đường xử lý an toàn khi flag tắt và kênh phân phối thực sự đáp ứng độ trễ sự cố. Nếu bật tính năng mới đã ghi dữ liệu không tương thích hoặc thay schema không thể đảo ngược, tắt flag **không tự rollback được dữ liệu**.

Feature flag lâu đời không được dọn có thể tạo rất nhiều tổ hợp hành vi khó kiểm thử. Mỗi flag nên có owner, ngày/điều kiện bỏ và cam kết về hành vi khi nguồn flag mất kết nối.

## 11. Rollout cấu hình theo từng mức rủi ro

Để không làm hỏng toàn bộ cụm trong một thay đổi, có thể chia giai đoạn:

~~~text
Draft
  |
  v
Schema validation + review
  |
  v
Staging / thử tải / kiểm tra tương thích
  |
  v
Canary 1 instance hoặc cohort nhỏ
  |
  v
Quan sát guardrail + kiểm tra drift
  |
  +---- vi phạm ------> phát hành bản phục hồi
  |
  v
Tăng dần 5% -> 25% -> 50% -> 100%
  |
  v
Xác nhận hội tụ + lưu audit
~~~

Đối với từng bước, định nghĩa:

- **Tập đích:** instance, zone, region hoặc cohort nào nhận bản mới.
- **Thời gian quan sát:** đủ dài để thấy các request và tác vụ có độ trễ cao.
- **Guardrail:** error rate, timeout, latency p95/p99, saturation, queue age, conversion hoặc metric nghiệp vụ phù hợp.
- **Giới hạn dung sai:** ngưỡng nào phải dừng, rollback hoặc cần điều tra.
- **Điều kiện hoàn tất:** bao nhiêu instance xác nhận bản mới; instance chưa nhận có được phép nhận traffic không.
- **Người có quyền:** ai có quyền phê duyệt hoặc thực hiện emergency revert.

Tránh canary vô tình chỉ có một nhóm traffic dễ nhất. Nếu dịch vụ phục vụ đa tenant, vùng hoặc loại request, phải xác định liệu canary có đủ đại diện. Một số thay đổi ảnh hưởng tài nguyên dùng chung (ví dụ global DB pool hoặc schema), nên rollout một instance có thể **không cô lập hoàn toàn tác động**.

### 11.1. Nhận diện tác động bằng tiêu chí đo

Ví dụ giảm payment timeout từ 1500 ms xuống 500 ms. Guardrail có thể gồm:

| Metric | Tín hiệu cần nhìn | Rủi ro |
|---|---|---|
| payment timeout rate | Tăng so với baseline | Từ chối giao dịch hợp lệ |
| checkout success rate | Giảm theo cohort | Ảnh hưởng nghiệp vụ trực tiếp |
| p95/p99 checkout latency | Thay đổi bất thường | Trễ do retry/circuit breaker |
| retry attempts | Tăng sau 500 ms | Khuếch đại tải downstream |
| connection pool wait | Tăng hoặc giảm | Áp lực tài nguyên thay đổi |
| applied_revision | Instance nào chưa chuyển | Trạng thái hỗn hợp khó đánh giá |

Ngưỡng phải dựa trên SLO, sai số thống kê, lưu lượng thật và mục tiêu nghiệp vụ; không áp một con số “chuẩn” cho mọi hệ thống. Độ trễ giảm mà tỷ lệ thành công sụt mạnh không phải cải thiện.

## 12. Rollback có phiên bản: quy trình cụ thể

Giả sử revision 42 tốt, revision 43 đã phát cho 20% instance và gây tăng timeout.

### Bước 1 — Dừng lan truyền

Đóng băng rollout revision 43, ngừng việc đưa bản này sang những instance chưa nhận. Nếu pipeline có nhiều đợt song song, cần bảo đảm không còn job cũ đang tiếp tục phát hành 43.

### Bước 2 — Chọn bản thực sự có thể phục hồi

Xác định bản 42 là **last known good** nhờ bằng chứng vận hành. Kiểm tra nó còn tương thích với bản code, schema DB, API và bí mật hiện hành. Không mặc định “bản cũ” luôn an toàn sau một migration hoặc credential rotation.

### Bước 3 — Tạo revision phục hồi mới

Công bố revision 44, lấy payload của bản 42, ghi metadata **restoredFrom=42**, **rollbackOf=43** cùng người thực hiện và lý do. Revision 44 có trạng thái mới hơn 43 để các watcher áp dụng được. Dùng compare-and-swap để không xóa nhầm một bản tốt vừa được đội khác phát hành.

### Bước 4 — Phát hành và xác nhận

Đặt desiredRevision=44, thông báo đến các instance và cho watcher tải snapshot. Instance phải validate, chuyển hiệu lực, báo appliedRevision=44. Nếu có instance bị cô lập mạng, hệ thống cần biết chúng vẫn ở bản 43, không được khẳng định rollback toàn cụm đã xong.

### Bước 5 — Theo dõi hồi phục

Kiểm tra latency, timeout, error rate, business metrics, connection count và độ lệch revision. Nếu các instance giữ client/cache cấu hình cũ, có thể cần drain/restart có kiểm soát.

### Bước 6 — Điều tra và ngăn tái diễn

Ghi lại lý do thay đổi, phạm vi bị ảnh hưởng, thời gian khôi phục, guardrail đã hoạt động hay chưa. Giữ snapshot 43 để phân tích; không sửa lại lịch sử. Bổ sung validation hoặc quy trình phê duyệt nếu cần.

**Phân biệt ba khái niệm:**

- **Rollback cấu hình:** phục hồi giá trị điều khiển.
- **Rollback ứng dụng:** thay lại binary/container hoặc revision triển khai.
- **Rollback dữ liệu:** phục hồi/bù trừ trạng thái đã ghi, không phải lúc nào cũng đảo ngược an toàn.

Khi bản config mới đã khiến hệ thống gửi email, ghi DB, trừ tiền hoặc gọi API có tác dụng phụ, rollback config **không hủy được những tác dụng phụ đã xảy ra**. Cần xử lý nghiệp vụ riêng và idempotency/compensation khi phù hợp.

## 13. Sự cố khó: thông báo cũ đến sau bản rollback

Giả sử:

~~~text
09:00 Desired revision 42
09:05 Phát hành revision 43 (timeout 500 ms)
09:06 Instance A áp dụng 43
09:07 Phát hành rollback revision 44 (payload của 42)
09:07 Instance A áp dụng 44
09:08 Notification trễ của revision 43 tới A
~~~

Nếu watcher chỉ “đọc sự kiện mới nhất vừa nhận” mà không đối chiếu revision, A có thể rơi lại vào cấu hình lỗi. Phòng ngừa:

1. Giữ revision cục bộ tăng một chiều; không áp dụng version thấp hơn bản đang có.
2. Khi nhận notification, **hỏi desiredRevision hiện tại**, rồi tải snapshot của revision đó.
3. Dùng manifest/hash để tránh áp dụng payload sai ID.
4. Ghi accepted/rejected revision cùng lý do, không chỉ “refresh success”.
5. Khi reconnect, đồng bộ với trạng thái mong muốn thực tế thay vì replay mù từng notification cũ.

Nếu cần áp dụng lại **chính giá trị cũ**, hãy phát hành **revision mới có payload cũ**. Đây là lý do tách **version của bản phát hành** và **giá trị cấu hình**.

## 14. Kế hoạch khi hệ thống cấu hình không truy cập được

Control plane cũng có thể bị lỗi. Một dịch vụ quan trọng không nên mất khả năng phục vụ request chỉ vì mỗi request phải gọi kho cấu hình qua mạng.

Chính sách thường có các phần:

- **Last known good (LKG):** giữ snapshot cuối cùng đã validate và áp dụng thành công trong bộ nhớ; nếu cần, lưu cache cục bộ an toàn có kiểm soát.
- **Khởi động khi nguồn không truy cập được:** định nghĩa rõ có dùng LKG đã lưu, dùng default hạn chế, hay chặn khởi động vì thiếu cấu hình bắt buộc.
- **Staleness budget:** quy định cấu hình có thể cũ tối đa bao lâu. Feature flag ít quan trọng có thể chịu stale dài hơn chính sách khóa tài khoản.
- **Retry/backoff có jitter:** tránh hàng nghìn instance đồng loạt reconnect vào control plane đang phục hồi.
- **Watch + reconciliation:** dù đã nhận push, định kỳ xác nhận desired/applied để sửa trạng thái khi mất sự kiện.
- **Thời hạn override:** emergency override có TTL và người sở hữu; tránh để chế độ tạm thành mặc định vĩnh viễn.
- **Thu hồi khẩn cấp:** thiết kế đường thu hồi quyền/secret theo yêu cầu bảo mật, không giả định LKG là an toàn mãi mãi.

**Fail-open** và **fail-closed** phải được quyết định theo từng loại khóa:

| Cấu hình | Khi nguồn cấu hình lỗi | Cân nhắc |
|---|---|---|
| Tỷ lệ sampling telemetry | Giữ LKG hoặc mặc định cục bộ | Ưu tiên ứng dụng tiếp tục phục vụ |
| Recommendation feature flag | Tắt thành phần tùy chọn hoặc giữ LKG có thời hạn | Tránh làm hỏng chức năng chính |
| Rate limit phòng chống lạm dụng | Giữ giới hạn cục bộ an toàn và ghi cảnh báo | Không nên mở vô hạn vì mất control plane |
| Chặn một principal đã bị thu hồi | Cần cơ chế cập nhật/kiểm chứng đáng tin, hạn stale ngắn | LKG cũ có thể cho phép truy cập nguy hiểm |
| Khóa giải mã hoặc token hết hạn | Không thể tùy ý dùng khóa/token đã bị thu hồi | Phải có rotation, cache và chính sách hết hạn |
| Khóa thay đổi định tuyến dữ liệu | Chặn hoặc giới hạn theo mức an toàn khi thiếu thông tin | Tránh gửi dữ liệu tới sai vùng/tenant |

Không có một chính sách fail-open/closed đúng cho tất cả cấu hình. Mỗi nhóm khóa phải có owner, rủi ro, mức chấp nhận stale và hành vi khi lỗi được ghi lại.

## 15. Cấu hình và bí mật: hai vòng đời khác nhau

Cấu hình nghiệp vụ có thể lưu trong kho phiên bản phổ thông với cơ chế phê duyệt và audit. **Bí mật** như mật khẩu, token, private key cần kho bí mật, mã hóa, quyền truy cập giới hạn và hạn chế hiển thị giá trị.

Một cách tổ chức:

~~~text
Versioned Config Store
  paymentTimeoutMs: 1500
  maxInFlightPayments: 80
  paymentCredentialRef: payment-api-key/current

Secret Manager
  payment-api-key/version-7: [giá trị bí mật]
  payment-api-key/version-8: [giá trị bí mật]
~~~

Config chỉ chứa **tham chiếu** đến bí mật nếu cần; client được cấp quyền truy cập mới có thể lấy giá trị. Đừng ghi secret vào audit diff, thông báo notification, log reload, metric labels hay trạng thái health.

### 15.1. Đổi mật khẩu/token an toàn

Quy trình rotation khi hệ thống đích cho phép hai credential cùng hiệu lực:

1. Tạo credential mới với quyền tối thiểu; credential cũ vẫn hợp lệ tạm thời.
2. Cập nhật secret manager và phân phối tham chiếu/phiên bản mới theo nhóm.
3. Đảm bảo các client có thể nạp credential mới và mở kết nối; chuyển dần sang credential mới.
4. Theo dõi xác thực thành công, số kết nối dùng credential cũ và các lỗi tương ứng.
5. Thu hồi credential cũ sau khi xác nhận chuyển đổi và hết thời gian hợp lý.
6. Ghi dấu vết rotation; không giữ credential cũ còn hiệu lực vô hạn làm “rollback”.

Nếu hệ thống đích **chỉ cho một credential**, cần cách triển khai khác: phối hợp cutover, cửa sổ bảo trì hoặc cơ chế token trung gian; không giả định có thời gian overlap.

Nếu credential mới lỗi sau khi credential cũ đã bị thu hồi, **rollback config về tham chiếu cũ không khôi phục credential đã vô hiệu hóa**. Cần phát hành credential hợp lệ mới hoặc thực hiện quy trình phục hồi bí mật riêng. Tương tự, rollback CA/truststore phải cân nhắc chuỗi chứng chỉ và trạng thái thu hồi hiện hành.

### 15.2. Thay đổi chứng chỉ và trust anchor

Mã hóa TLS có thể cần giai đoạn chồng lấn tin cậy: client tin cả CA cũ và mới trong thời gian chuyển, server dùng chứng chỉ mới, sau đó mới xóa CA cũ khỏi truststore. Không tắt xác minh hostname hoặc certificate để “chữa” lỗi reload. Các kết nối đã mở có thể giữ session cũ; cần biết thời điểm reconnect và drain.

**Cấu hình động không được trở thành đường vượt kiểm soát an ninh.** Quyền thay feature flag thông thường không nên bao gồm quyền đọc secret, tắt TLS validation, nâng role quản trị hoặc đổi endpoint có thể đưa dữ liệu ra ngoài.

## 16. Bảo mật control plane cấu hình

Một máy chủ cấu hình có quyền tác động đến hàng loạt service; nếu bị chiếm quyền, hậu quả có thể tương đương phát hành code độc hại ở một số luồng nghiệp vụ. Vì vậy:

- **Authentication và RBAC:** tách người xem, người đề xuất, người duyệt và người phát hành; phân quyền theo service/environment/namespace.
- **Nguyên tắc ít quyền nhất:** team của Checkout không được tự sửa cấu hình production của Payment nếu không có vai trò tương ứng.
- **Bảo vệ đường truyền:** dùng TLS, xác thực máy chủ và danh tính workload khi instance tải config.
- **Quy trình phê duyệt:** thay đổi nhạy cảm cần review/dual control theo quy định; emergency change vẫn phải để lại audit.
- **Tính toàn vẹn:** checksum hoặc chữ ký snapshot khi threat model yêu cầu; client kiểm tra phạm vi và nguồn hợp lệ.
- **Không lộ secret:** metadata và diff có redaction; token không được nằm trong URL hay exception.
- **Chống replay/xung đột:** kiểm tra revision và expectedRevision.
- **Phân tách môi trường:** không cho một token staging thay policy production.
- **Giới hạn thao tác:** rate limit API quản trị, giữ audit trail, cảnh báo khi đổi nhiều khóa nguy hiểm.
- **Break-glass:** có quyền khẩn cấp giới hạn thời gian, lưu đầy đủ người thực hiện, lý do và kiểm tra lại sau sự cố.

Các thay đổi nguy hiểm như tắt xác thực, tăng quota vô hạn, đổi vùng lưu dữ liệu hoặc bỏ kiểm tra TLS nên bị chặn ở policy engine hoặc cần quy trình cao hơn thay vì chỉ hiện nút bật/tắt.

## 17. Spring Boot và Kubernetes: các hiểu lầm khi cập nhật cấu hình

### 17.1. Spring Boot

Spring Boot hỗ trợ nạp thuộc tính từ nhiều nguồn vào **Environment** và bind vào **@ConfigurationProperties**. Tuy nhiên, phần lớn bean và resource được khởi tạo theo vòng đời ứng dụng. Việc thay đổi giá trị ở một nguồn ngoài **không tự động** bảo đảm mọi bean đã dùng giá trị mới.

Có thể triển khai dynamic config bằng một tầng quản lý snapshot như ví dụ **AtomicReference**, hoặc dùng các thành phần refresh do giải pháp tương ứng cung cấp. Nếu sử dụng Spring Cloud và cơ chế **@RefreshScope** trong môi trường có hỗ trợ, phải kiểm tra chính xác bean nào được làm mới, bean nào vẫn giữ state cũ, tương tác với proxy, validation và vòng đời kết nối.

Các lưu ý:

- **@ConfigurationProperties** là cách bind cấu hình, không mặc nhiên là cơ chế hot reload.
- Refresh bean không đồng nghĩa resource ngoài JVM được cập nhật đúng.
- Các timeout được chép vào client tại lúc khởi tạo cần thiết kế reinitialize/reconfigure.
- Một controller đọc nhiều property rời rạc có thể quan sát tổ hợp giá trị không đồng nhất.
- Cấu hình nhạy cảm phải không xuất hiện trong actuator/config endpoints công khai.
- Không dựa vào một endpoint refresh không được bảo vệ làm đường cập nhật production.

### 17.2. Kubernetes

**ConfigMap** chứa cấu hình không bí mật, **Secret** là loại tài nguyên riêng cho dữ liệu bí mật nhưng vẫn cần RBAC, bảo vệ lưu trữ và quy định vận hành. Việc base64 encode giá trị Secret không phải mã hóa bảo mật.

Có khác biệt quan trọng:

| Cách đưa cấu hình vào Pod | Khi tài nguyên nguồn thay đổi | Hệ quả |
|---|---|---|
| Biến môi trường | Biến trong process đang chạy không tự đổi | Thường cần khởi động lại Pod hoặc cơ chế khác |
| Mount ConfigMap/Secret dưới dạng volume | Nội dung volume thường được cập nhật bất đồng bộ theo cơ chế và giới hạn của Kubernetes | Ứng dụng vẫn cần chủ động đọc lại và áp dụng |
| Mount dùng subPath | Không nhận cập nhật volume tự động theo cơ chế thông thường | Cần thiết kế rollout/restart khác |
| Sidecar/agent đồng bộ file | Agent có thể ghi file mới và gửi tín hiệu | Cần atomic file swap, validate và xử lý watcher |
| GitOps/Deployment rollout | Tạo Pod mới với cấu hình mới | Có thể quan sát rollout và rollback Deployment nhưng vẫn phải xử lý dữ liệu tương thích |

Không chỉ dựa vào file-watch event: việc cập nhật mount có thể dùng đổi liên kết/ghi thay file, và thư viện watch một inode/file cụ thể có thể bỏ lỡ bản mới. Cần cơ chế reconciliation định kỳ và đọc lại snapshot hoàn chỉnh.

Rolling restart do đổi ConfigMap checksum trong Pod template là một mô hình triển khai hợp lệ, **nhưng đó là reload bằng khởi động lại**, không phải cập nhật in-memory. Khi Pod mới dùng config sai, rollback Deployment phải bảo đảm nó thật sự trỏ đến nguồn cấu hình đúng; việc quay image về phiên bản cũ trong khi ConfigMap hiện tại vẫn lỗi có thể không khôi phục được dịch vụ.

## 18. Quan sát: biết bản nào đang có hiệu lực thật

Cần phân biệt ba chỉ số phiên bản:

- **Desired revision:** control plane muốn một instance/cohort chạy bản nào.
- **Downloaded/validated revision:** instance tải và kiểm tra thành công bản nào.
- **Applied revision:** snapshot nào đang thực sự điều khiển xử lý.

Một instance có thể tải revision 50 thành công nhưng vẫn dùng 49 vì resource mới không sẵn sàng. Chỉ số “config downloaded” không thể thay thế “config applied”.

Ví dụ metric và log:

~~~text
config_desired_revision{service="checkout",region="sg"} 44
config_applied_revision{service="checkout",instance="pod-7"} 44
config_reload_success_total{service="checkout"} 103
config_reload_rejected_total{service="checkout",reason="validation"} 2
config_reload_lag_seconds{service="checkout"} 4.1
config_rollback_total{service="checkout"} 1
~~~

Đây là tên metric minh họa, không phải tiêu chuẩn bắt buộc. Cần chú ý cardinality: nhãn instance/tenant quá chi tiết có thể gây tốn kém; tránh đưa secret, payload đầy đủ, ID nhạy cảm hoặc chuỗi lý do tùy ý vào label.

Mỗi lần cập nhật cần audit có cấu trúc:

~~~json
{
  "event": "CONFIG_APPLIED",
  "service": "checkout",
  "environment": "production",
  "instance": "checkout-7",
  "fromRevision": 43,
  "toRevision": 44,
  "releaseId": "cfg-checkout-prod-44",
  "result": "SUCCESS",
  "timestamp": "2026-11-12T02:07:00Z"
}
~~~

Thông tin có ích khi điều tra:

- Bản nào đã được phát hành, bởi ai và với lý do gì?
- Cụm nào, bao nhiêu instance, zone hoặc cohort đã áp dụng?
- Instance nào từ chối bản mới và vì sao?
- Có phiên bản hỗn hợp quá lâu hoặc một cohort chưa đồng bộ không?
- Các SLO/metric nghiệp vụ thay đổi thế nào ngay sau mốc áp dụng?
- Bản nào cuối cùng được xác nhận là tốt và dựa vào bằng chứng gì?

**Health endpoint** không nên trả payload cấu hình và bí mật. Có thể công bố trạng thái tối giản: revision, trạng thái hợp lệ và độ trễ đồng bộ dưới quyền truy cập phù hợp.

## 19. Mô hình thực tế: giảm timeout thanh toán rồi rollback

### 19.1. Trạng thái ban đầu

Checkout Service có 12 instance, thanh toán được xem là thành công khi Payment Service phản hồi hợp lệ. Cấu hình bản 105:

~~~yaml
revision: 105
paymentTimeoutMs: 1500
maxInFlightPayments: 80
paymentRetryMaxAttempts: 2
paymentRetryBackoffMs: 100
~~~

Trong tải bình thường, p95 của Payment Service là 300 ms, p99 là 900 ms. Nhóm muốn giảm timeout xuống 600 ms nhằm giảm số request giữ kết nối quá lâu. Thay đổi này hợp lệ về kiểu, nhưng chưa chắc hợp lý với p99.

### 19.2. Phát hành bản 106

Kho tạo revision 106 với **paymentTimeoutMs=600**, giữ nguyên các khóa khác. Pipeline validate schema, chạy thử tải và canary trên hai instance được chọn. Mỗi instance nhận snapshot qua watcher, xác minh revision rồi áp dụng cho request mới. Request đang chạy tiếp tục dùng policy đã chốt tại thời điểm bắt đầu.

Dữ liệu giả định sau canary:

| Chỉ số | Bản 105 | Canary 106 | Nhận định |
|---|---:|---:|---|
| Payment timeout | 0,5% | 4,2% | Xấu đi rõ rệt |
| Checkout success | 99,2% | 95,4% | Vượt ngưỡng chấp nhận |
| p95 checkout latency | 700 ms | 550 ms | Có vẻ nhanh hơn nhưng nhiều request thất bại |
| Retry attempt/request | 0,06 | 0,18 | Downstream nhận thêm tải |
| Applied revision | 105 | 106 trên 2 instance | Canary chưa phát toàn cụm |

### 19.3. Hành động rollback

Bộ điều khiển dừng rollout 106 và tạo revision **107** với payload của **105**, metadata **restoredFrom=105** và lý do. Hai instance canary tải 107, validate và áp dụng; các instance còn lại có thể chuyển thẳng 105 → 107 nếu chưa từng dùng 106.

Hệ thống chỉ đánh dấu phục hồi hoàn tất khi các instance phục vụ traffic có appliedRevision=107 (hoặc được cô lập/đưa ra khỏi pool theo chính sách), tỷ lệ timeout trở về ngưỡng và retry không còn khuếch đại. Thông báo chậm của 106 không được ghi đè 107.

### 19.4. Kết luận từ tình huống

Giá trị 600 ms không sai cú pháp. Lỗi phát sinh ở sự phù hợp với latency thực tế và tác dụng phụ retry. Canary, guardrail và lịch sử revision giúp giới hạn ảnh hưởng và tìm đường phục hồi. Đổi một file ngược về 1500 ms mà không xác nhận từng instance đã áp dụng chưa đủ chứng minh đã rollback.

## 20. Trường hợp rollback config không đủ

### 20.1. Cấu hình gắn với database migration

Một flag mới cho phép ghi thêm trường dữ liệu có định dạng không tương thích. Sau khi flag bật và dữ liệu đã ghi, tắt flag có thể khiến bản code cũ không đọc được dữ liệu mới. Cần kế hoạch **expand → migrate → contract**, tương thích ngược và bước bù trừ/khôi phục dữ liệu nếu cần.

### 20.2. Thay đổi định tuyến/đích gửi dữ liệu

Config mới định tuyến sang region B, một phần dữ liệu đã được gửi tới đó. Quay về region A không tự di chuyển dữ liệu đã ghi hay bảo đảm các workflow đang chờ hoàn tất. Cần chính sách đồng bộ, đối soát và xử lý vùng dữ liệu.

### 20.3. Tăng số worker hoặc connection

Config cũ giới hạn 20 worker, bản mới tăng lên 200 và gây nghẽn DB. Rollback về 20 phải giảm tải đang chạy có kiểm soát; các job đã bắt đầu vẫn chiếm tài nguyên cho đến khi kết thúc hoặc bị hủy an toàn.

### 20.4. Secret rotation không thể đảo ngược

Credential cũ đã bị thu hồi. Đổi lại tham chiếu cũ chỉ tạo thêm lỗi xác thực. Cần phát hành credential mới hợp lệ và khôi phục phân phối bí mật.

### 20.5. Đổi contract giữa producer và consumer

Một feature flag bật sự kiện schema mới nhưng consumer cũ chưa hỗ trợ. Tắt flag chỉ ngăn phát tiếp; các sự kiện mới đã nằm trong queue vẫn cần handler tương thích, DLQ hoặc kế hoạch replay có kiểm soát.

Bởi vậy, trước khi cho phép một khóa là “rollbackable”, phải xác định **khôi phục giá trị có khôi phục được hành vi không** và liệu có side effect ngoài tiến trình hay không.

## 21. Kế hoạch xử lý xung đột và sai lệch cấu hình

Khi nhiều vùng hoặc nhóm dịch vụ vận hành độc lập, có thể gặp:

| Vấn đề | Ví dụ | Cách tiếp cận |
|---|---|---|
| **Version skew** | A đã nhận 51, B còn 50 | Xác định compatibility window; đo drift và chặn rollout khi vượt thời gian |
| **Stale event** | Notification 49 đến sau 51 | Từ chối revision cũ, reconcile desired |
| **Concurrent edit** | Hai thay đổi cùng dựa trên 50 | CAS/expectedRevision ở nơi công bố |
| **Partial apply** | Đổi timeout thành công, đổi client endpoint lỗi | Snapshot nguyên tử, prepare/switch resource hoặc rollback toàn nhóm |
| **Override bị quên** | Emergency override vẫn tồn tại sau sự cố | TTL, owner, cảnh báo sắp hết hạn và định kỳ đối soát |
| **Unknown key** | App cũ nhận schema chứa khóa mới | Từ chối hoặc bỏ qua theo hợp đồng schema và rủi ro, không im lặng mặc định |
| **Offline instance** | Pod mất kết nối control plane | LKG, staleness policy, reconnect có backoff |
| **Sai phạm vi** | Config staging phát cho production | Kiểm tra identity service/environment/region trước khi apply |
| **Thiếu quyền** | User chỉ có quyền xem cố publish | RBAC từ chối, audit và cảnh báo |
| **Checksum mismatch** | ID 55 nhưng nội dung không trùng digest | Không áp dụng, giữ LKG và báo lỗi integrity |

Không nên tự động “chữa drift” bằng cách đồng bộ một instance khác khi chưa xác minh đâu là bản có thẩm quyền. **Desired state từ control plane có phiên bản** là nơi quyết định; việc các instance đang có hai giá trị khác nhau chỉ là tín hiệu để điều tra và hội tụ.

## 22. Kiểm thử cho cơ chế dynamic config và rollback

Một bộ kiểm thử có giá trị nên đi qua cả đường thành công và thất bại:

### 22.1. Kiểm thử schema và áp dụng

- Snapshot hợp lệ được chấp nhận và xuất hiện ở appliedRevision.
- Sai kiểu, sai đơn vị, phạm vi hoặc vi phạm quan hệ khóa bị từ chối; bản đang chạy không thay đổi.
- Đổi nhiều khóa liên quan không tạo trạng thái nửa cũ nửa mới cho một request.
- Bean/client gắn tài nguyên thực sự nạp chính sách mới; tài nguyên cũ được giải phóng.
- Cấu hình không tương thích schema với version ứng dụng bị từ chối có lý do rõ.

### 22.2. Kiểm thử kênh phân phối

- Nhận notification trùng nhiều lần không có tác dụng phụ lặp.
- Nhận 42 sau 44 không làm revision giảm.
- Bỏ lỡ notification rồi reconnect vẫn hội tụ về desiredRevision hiện tại.
- Hai bản mới đến gần nhau không tạo trạng thái ngoài thứ tự.
- Kho cấu hình hoặc mạng mất kết nối thì ứng dụng tuân thủ LKG/staleness policy.
- Hàng trăm instance reconnect cùng lúc không làm sập control plane.

### 22.3. Kiểm thử rollout và rollback

- Canary chỉ đổi trên tập đích; những instance khác giữ bản trước.
- Khi guardrail vượt ngưỡng, rollout dừng, không có công việc phát hành cũ tiếp tục chạy.
- Rollback tạo **revision mới** với payload đã biết tốt.
- Mọi instance đang nhận traffic hoặc đã áp dụng revision phục hồi, hoặc bị xử lý theo quy trình cách ly.
- Connection pool/client cũ được drain hoặc được thay đúng khi config quay lại.
- Bản rollback không gây lại lỗi do bí mật đã thu hồi, schema đã thay đổi hay dữ liệu đã ghi.

### 22.4. Kiểm thử an ninh

- Người chỉ có quyền xem không thể phát hành, rollback hoặc đổi secret.
- Service A không đọc/sửa config của Service B hoặc môi trường khác.
- Secret không xuất hiện trong audit diff, log, metric và endpoint chẩn đoán.
- Snapshot giả, sai checksum, sai scope hoặc credential hết hạn bị từ chối.
- Emergency override có TTL và để lại audit; chỉ role thích hợp được kích hoạt.

Không chỉ kiểm thử endpoint “refresh trả 200”. Tiêu chí thành công là **hành vi thực thi đổi đúng, dữ liệu không hỏng, phạm vi quyền được giữ và có bằng chứng áp dụng/khôi phục**.

## 23. Quy trình vận hành đề xuất

Trước khi thay cấu hình production:

1. Xác định owner, mục đích, phạm vi, khóa thay đổi và các dịch vụ bị ảnh hưởng.
2. Kiểm tra schema, min/max, quan hệ khóa, compatibility và quyền thay đổi.
3. Ghi expectedRevision, tạo snapshot bất biến và diff đã che bí mật.
4. Xác định rollback target thực sự tương thích, cùng thao tác phục hồi nếu có side effect.
5. Chọn cohort, guardrail, thời gian quan sát và điều kiện dừng rollout.
6. Phát hành có kiểm soát, theo dõi desired/downloading/applied revision.
7. Dừng và rollback khi chạm điều kiện; xác nhận sự phục hồi ở cả data plane và chỉ số nghiệp vụ.
8. Lưu lịch sử, audit, nguyên nhân và thời điểm kết thúc; dọn override tạm khi an toàn.

Trong sự cố nghiêm trọng, nên có quy trình emergency được chuẩn bị trước thay vì tạo tài khoản toàn quyền hoặc chỉnh tay từng Pod. Lối phục hồi phải có đường thao tác rõ và giới hạn quyền thích hợp.

## 24. Bài tập ứng dụng

**Bài tập A — thiết kế chính sách:** Checkout Service có các khóa paymentTimeoutMs, retryMaxAttempts, dbPoolSize, enableRecommendations, paymentApiToken và serverPort. Hãy phân loại khóa nào hot reload được, khóa nào cần thay tài nguyên, khóa nào nên restart và khóa nào thuộc secret manager. Nêu rủi ro rollback cho từng loại.

**Bài tập B — dựng lịch sử revision:** Revision 17 đang tốt. Một người phát hành 18, một người khác cùng chỉnh từ 17. Hãy đề xuất compare-and-swap để tránh ghi đè; nếu 18 gây lỗi, hãy mô tả cách tạo 19 từ payload 17 sao cho watcher không bị kẹt ở 18.

**Bài tập C — quan sát version skew:** Có 10 Pod; 8 Pod dùng revision 55, 2 Pod vẫn ở 53 do mất kết nối. Thiết kế dashboard và cảnh báo. Khi nào được coi rollout hoàn tất? Bạn sẽ chọn tiếp tục phục vụ traffic, giảm traffic hay cô lập hai Pod theo tiêu chí gì?

**Bài tập D — thay HTTP client:** Cấu hình đổi URL downstream và TLS truststore. Hãy vẽ quy trình prepare, validate, switch, drain, dispose. Giải thích vì sao chỉ thay string trong AtomicReference không đủ, và cần xử lý request đang chạy thế nào.

**Bài tập E — kho cấu hình bị gián đoạn:** Feature flag, rate limit và danh sách chặn credential cùng không thể làm mới trong 20 phút. Chọn chính sách LKG/staleness cho từng nhóm và giải thích quyết định fail-open/fail-closed theo rủi ro.

**Bài tập F — sự cố rollback:** Một flag mới đã làm phát ra sự kiện schema v2, còn các consumer cũ chỉ hiểu v1. Dừng flag có đủ không? Hãy đưa ra thứ tự thay đổi producer/consumer, cách xử lý message đã tồn tại và tiêu chí phục hồi.

## 25. Ghi nhớ

- **Cấu hình động là một thay đổi trạng thái có kiểm soát**, không đơn thuần sửa file ngoài tiến trình.
- **Bản phát hành phải có revision, phạm vi, schema, dấu vết và snapshot bất biến.** Control plane lưu desired revision; mỗi instance báo applied revision thực tế.
- **Validate trước, áp dụng nguyên tử khi có thể;** với tài nguyên có trạng thái phải chuẩn bị mới, chuyển đổi an toàn và giải phóng tài nguyên cũ.
- **Canary, guardrail và đo tác động** quan trọng vì một giá trị đúng schema vẫn có thể sai về nghiệp vụ hoặc vận hành.
- **Rollback nên phát hành revision mới với payload đã biết tốt**, để tránh notification trễ ghi đè và giữ lịch sử tăng một chiều.
- **Quay lại cấu hình cũ không tự khôi phục dữ liệu, binary hay bí mật đã bị thu hồi.** Phải đánh giá tác dụng phụ và tương thích.
- **LKG, chính sách stale, phân quyền, audit và bí mật tách riêng** giúp hệ thống hoạt động an toàn khi control plane gặp sự cố.
- **Chỉ đánh dấu rollout hoặc rollback hoàn tất khi có bằng chứng áp dụng và hồi phục hành vi**, không chỉ khi API cập nhật trả về thành công.

Khả năng thay đổi và quay về cấu hình là một phần của năng lực vận hành hệ thống phân tán. Thiết kế tốt làm cho mọi thay đổi có thể truy vết, mọi instance có thể tự xác minh bản đang dùng, và con đường phục hồi vẫn hoạt động khi bản cấu hình mới nhất không an toàn.
