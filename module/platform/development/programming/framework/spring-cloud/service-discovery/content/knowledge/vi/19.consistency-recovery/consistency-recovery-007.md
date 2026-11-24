# Tránh đồng loạt đăng ký hoặc truy vấn lại sau sự cố

Khi registry vừa phục hồi sau một đợt mất kết nối, nhiều provider có thể đồng thời đăng ký lại và nhiều consumer đồng thời tải lại danh sách instance. Registry vừa thoát khỏi trạng thái quá tải lại nhận một đợt request lớn, tiếp tục chậm hoặc mất kết nối. Hiện tượng này thường được gọi là thundering herd.

Trong Spring Cloud Service Discovery, hai luồng cần kiểm soát là:

- **Registration storm:** nhiều instance provider cùng tạo hoặc cập nhật registration sau khi khởi động, reconnect hoặc session được khôi phục.
- **Discovery query storm:** nhiều consumer cùng gọi getServices, getInstances, refresh cache hoặc dựng lại danh sách endpoint sau khi registry phục hồi.

Giải pháp không chỉ là tăng timeout. Cần phân tán thời điểm retry, giới hạn tốc độ và số request đồng thời, dùng cache hợp lý, gộp các truy vấn trùng nhau, đồng thời giữ readiness và retry budget rõ ràng. Mục tiêu là để hệ thống phục hồi dần theo năng lực của registry thay vì dồn toàn bộ tải vào cùng một thời điểm.

## 1. Vì sao các client đồng loạt hoạt động?

Các client thường có cùng cấu hình và cùng sự kiện kích hoạt. Nếu không có độ trễ ngẫu nhiên, chúng có thể phát request gần như cùng lúc.

Những nguyên nhân thường gặp:

- Một cụm container được triển khai cùng lúc và tất cả provider khởi động trong cùng vài giây.
- Mạng đến Eureka, Consul hoặc ZooKeeper bị gián đoạn rồi khôi phục; mọi client reconnect cùng lúc.
- Nhiều ZooKeeper session hết hạn trong cùng một khoảng thời gian và các ứng dụng cùng tạo session mới.
- Cache discovery của nhiều consumer hết hạn cùng thời điểm.
- Nhiều ứng dụng có lịch refresh giống nhau, ví dụ mỗi 30 giây tính từ lúc khởi động.
- Một đợt deploy hoặc scale-out tạo hàng trăm instance mới cùng đăng ký.
- Một registry vừa phục hồi, tất cả consumer retry ngay các request đã thất bại.
- Health checker, load balancer và ứng dụng cùng truy vấn danh sách service theo chu kỳ giống nhau.

Ví dụ, 600 consumer cùng refresh registry sau khi mạng phục hồi. Nếu mỗi consumer tải danh sách nhiều service và retry ba lần khi lỗi, registry có thể nhận hàng nghìn request trong một đợt ngắn. Nếu provider cũng đồng thời đăng ký lại, tải đọc và ghi cùng tăng.

Đây là vòng lặp khuếch đại:

~~~mermaid
flowchart TD
    A["Registry hoặc network gặp sự cố"] --> B["Nhiều client mất kết nối"]
    B --> C["Registry phục hồi"]
    C --> D["Client đồng loạt reconnect / retry"]
    D --> E["Registration và query tăng đột biến"]
    E --> F{"Registry chịu được tải?"}
    F -->|"Không"| G["Timeout và lỗi mới"]
    G --> D
    F -->|"Có"| H["Client phục hồi dần"]
~~~

Nếu retry ngay sau mỗi lỗi, tải tăng đúng lúc hệ thống ít khả năng xử lý nhất. Cần làm cho các lần thử tiếp theo cách nhau và phân bố trên một khoảng thời gian.

## 2. Phân biệt retry, reconnect, refresh và registration

Các hành động này có mục đích khác nhau; không nên gộp tất cả thành một vòng lặp retry chung.

| Hành động | Mục đích | Rủi ro khi đồng loạt |
|---|---|---|
| Reconnect | Khôi phục kết nối client đến registry | Nhiều kết nối TCP/session mới cùng lúc |
| Register | Tạo hoặc cập nhật instance record | Nhiều thao tác ghi, có thể tạo ID trùng |
| Renew/heartbeat | Duy trì lease hoặc session | Tăng tải định kỳ nếu lịch bị đồng bộ |
| Refresh discovery | Tải lại danh sách instance/service | Nhiều request đọc và xử lý response lớn |
| Health check | Xác minh trạng thái registry hoặc service | Probe storm, nhất là khi kiểm tra fan-out |
| Retry request nghiệp vụ | Thử lại lời gọi downstream sau lỗi | Khuếch đại tải qua nhiều tầng service |

Một provider có thể đã reconnect nhưng chưa đăng ký thành công. Một consumer có thể đọc registry thành công nhưng cache vẫn chứa instance cũ. Vì vậy, theo dõi riêng connection state, registration state, discovery refresh và business readiness.

## 3. Dùng exponential backoff với jitter

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Jitter thêm độ ngẫu nhiên để các client không cùng retry ở một thời điểm.

Nếu không có jitter, 600 client cùng thất bại ở giây 0, chờ 1 giây rồi cùng retry; thất bại tiếp thì cùng chờ 2 giây, 4 giây và tiếp tục tạo các đợt tải đồng bộ.

Một công thức full jitter phổ biến:

\[
cap_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

\[
wait_n \sim Uniform(0,\ cap_n)
\]

Trong đó n là số lần retry đã thực hiện. Mỗi client tự chọn thời gian chờ ngẫu nhiên trong khoảng từ 0 đến cap. Khi cap đạt maxDelay, khoảng chờ không tiếp tục tăng.

Các biến thể khác:

| Chiến lược | Cách chọn thời gian | Đặc điểm |
|---|---|---|
| Exponential không jitter | Luôn chờ cap | Dễ tạo retry đồng bộ |
| Full jitter | Ngẫu nhiên từ 0 đến cap | Phân tán tốt các lần thử |
| Equal jitter | Chờ một nửa cap cộng phần ngẫu nhiên còn lại | Giảm khả năng retry quá sớm |
| Decorrelated jitter | Khoảng chờ mới dựa trên khoảng chờ trước và giới hạn | Tránh nhịp retry cố định |

Full jitter thường là lựa chọn dễ áp dụng. Cần có maxDelay để lần thử không bị trì hoãn vô hạn. Với thao tác có thời hạn nghiệp vụ, cũng cần deadline tổng thể để dừng retry khi đã hết thời gian hữu ích.

## 4. Ví dụ tạo thời gian chờ có full jitter trong Java

Đoạn helper dưới đây tính cap tăng dần và chọn thời gian chờ ngẫu nhiên. attempt bắt đầu từ 0 ở lần retry đầu tiên.

~~~java
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelay {

    private RetryDelay() {
    }

    public static long fullJitterMillis(
            int attempt,
            long baseDelayMillis,
            long maxDelayMillis) {

        if (attempt < 0) {
            throw new IllegalArgumentException("attempt phải >= 0");
        }
        if (baseDelayMillis <= 0 || maxDelayMillis < baseDelayMillis
                || maxDelayMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Khoảng delay không hợp lệ");
        }

        long cap = baseDelayMillis;

        for (int i = 0; i < attempt && cap < maxDelayMillis; i++) {
            cap = cap > maxDelayMillis / 2
                    ? maxDelayMillis
                    : Math.min(maxDelayMillis, cap * 2);
        }

        return ThreadLocalRandom.current().nextLong(cap + 1);
    }
}
~~~

Ví dụ cấu hình base delay 500 ms và max delay 30 giây:

| Lần retry | Cap tối đa | Khoảng chờ full jitter |
|---:|---:|---:|
| 0 | 500 ms | 0–500 ms |
| 1 | 1.000 ms | 0–1.000 ms |
| 2 | 2.000 ms | 0–2.000 ms |
| 3 | 4.000 ms | 0–4.000 ms |
| 4 | 8.000 ms | 0–8.000 ms |
| 5 | 16.000 ms | 0–16.000 ms |
| 6 trở đi | 30.000 ms | 0–30.000 ms |

Các giá trị chỉ là ví dụ cho một thao tác retry. Không dùng cùng một bộ thông số cho mọi request, heartbeat, session timeout và health check. Mỗi loại thao tác có deadline, chi phí và mức chịu lỗi riêng.

Khi nhận được Retry-After từ backend hoặc gateway, cân nhắc tôn trọng thời gian đó và thêm jitter nhỏ sau mốc được yêu cầu. Không retry sớm hơn giới hạn do backend đưa ra.

## 5. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể khắc phục bằng retry. Nếu lỗi do cấu hình sai, credential hết hạn hoặc serviceId không tồn tại, retry liên tục chỉ tạo thêm tải.

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Lỗi tạm thời | Connection reset, timeout, registry leader election | Backoff và retry có giới hạn |
| Quá tải | HTTP 429, 503, server overload | Giảm tốc độ, tôn trọng Retry-After, dùng retry budget |
| Lỗi xác thực/phân quyền | 401, 403, ACL denied | Không retry liên tục; sửa credential/quyền |
| Cấu hình sai | Sai hostname, port, scheme hoặc path | Báo lỗi cấu hình và dừng retry |
| Dữ liệu không hợp lệ | Metadata sai schema, instance ID trùng | Không retry mù; xử lý dữ liệu |
| Service chưa tồn tại | Chưa có provider đăng ký | Dùng deadline hoặc chính sách chờ có giới hạn |

Chỉ retry các thao tác có thể lặp lại an toàn. Registration nên có instance ID ổn định và semantics idempotent để retry không tạo nhiều record. Với thao tác ghi có thể tạo side effect, cần kiểm tra trạng thái trước khi thử lại hoặc dùng idempotency key.

## 6. Giới hạn retry budget và số lần thử

Backoff phân tán thời gian; retry budget giới hạn tổng lượng retry mà hệ thống cho phép.

Ví dụ, có thể đặt ngân sách retry tối đa bằng một tỷ lệ nhỏ so với số request gốc trong một cửa sổ thời gian. Nếu request gốc tăng, số retry được phép tăng theo giới hạn; nếu request gốc giảm, retry không tiếp tục tạo tải độc lập.

Các biện pháp:

- Giới hạn số lần thử cho mỗi thao tác.
- Đặt deadline tổng thể thay vì retry vô hạn.
- Giới hạn tỷ lệ retry trên tổng request.
- Khi budget cạn, trả lỗi có kiểm soát hoặc dùng dữ liệu cache còn phù hợp.
- Reset trạng thái backoff sau khi kết nối ổn định đủ lâu, không reset ngay sau một lần thành công chập chờn.
- Theo dõi retry rate riêng với request gốc.

Không nhân bản retry ở mọi tầng. Ví dụ, HTTP client retry 3 lần, LoadBalancer retry 3 lần và service gọi lại toàn bộ thao tác 3 lần có thể tạo đến 27 lần thử cho một request gốc. Chọn một tầng chịu trách nhiệm retry chính và truyền deadline xuống các tầng dưới.

## 7. Phân tán thời điểm khởi động và registration

Khi scale một deployment từ 0 lên nhiều replica, các instance thường khởi động gần nhau. Nếu tất cả cùng register ngay khi ApplicationContext sẵn sàng, registry nhận một đợt ghi lớn.

Có thể giảm đỉnh tải bằng:

- Random initial delay trước lần đăng ký hoặc lần thử đầu tiên.
- Rolling deployment với số replica tăng theo từng nhóm.
- Giới hạn maxSurge hoặc số instance được tạo mới đồng thời ở orchestrator.
- Giới hạn concurrency của thao tác registration.
- Retry registration với backoff và jitter khi registry chưa sẵn sàng.
- Chỉ chuyển readiness UP sau khi registration đã thành công nếu ứng dụng phụ thuộc vào discovery để nhận traffic.

Ví dụ, nếu có 300 provider mới và phân bố thời điểm đăng ký trong cửa sổ 30 giây, tải ghi trung bình lý thuyết khoảng 10 lần đăng ký mỗi giây thay vì 300 lần gần như cùng lúc. Thực tế còn phụ thuộc phân bố ngẫu nhiên, retry và tốc độ xử lý của registry; cần đo đỉnh tải chứ không chỉ nhìn trung bình.

Không thêm delay cố định giống nhau cho tất cả instance. Nếu mọi container đều sleep 10 giây, chúng vẫn có thể thức dậy cùng lúc. Phải dùng giá trị ngẫu nhiên theo instance hoặc cơ chế rollout có kiểm soát.

## 8. Registration phải idempotent và có định danh ổn định

Khi reconnect sau sự cố, provider cần biết registration cũ còn tồn tại hay đã mất. Nếu mỗi lần retry tạo một instance ID mới, registry có thể chứa nhiều record cho cùng một process.

Quy tắc nên áp dụng:

- Tạo instance ID ổn định trong vòng đời một instance.
- Không tạo UUID mới ở mỗi lần retry đăng ký.
- Nếu registry hỗ trợ upsert hoặc đăng ký theo ID, dùng đúng semantics đó.
- Sau session expiration, tạo registration mới gắn với session mới nhưng giữ định danh logic phù hợp.
- Khi process thay thế instance cũ, bảo đảm ID mới không xung đột và record cũ được dọn.
- Chỉ đánh dấu readiness UP sau khi trạng thái registration được xác minh theo yêu cầu của ứng dụng.

Với ZooKeeper ephemeral znode, session mới cần tạo lại node sau khi session cũ LOST. Tác vụ tạo node cần xử lý trường hợp node đã tồn tại do một lần retry trước đó hoặc do tiến trình khác đang sở hữu cùng path. Không xóa node của instance khác để “sửa” xung đột.

Với Eureka và Consul, kiểm tra trạng thái registration trước khi tạo một ID mới. Tránh lặp thao tác ghi toàn bộ metadata nếu chỉ cần cập nhật một trường và backend có API phù hợp.

## 9. Tránh query storm bằng cache và single-flight

Consumer không nên gọi registry cho mỗi request nghiệp vụ nếu danh sách instance có thể được cache an toàn. Spring Cloud DiscoveryClient implementation có thể đã sử dụng cache riêng, nhưng hành vi phụ thuộc registry client và cấu hình. Hãy kiểm tra implementation trước khi thêm một lớp cache khác.

Các nguyên tắc:

- Dùng cache instance list với TTL phù hợp.
- Thêm jitter vào thời điểm refresh để cache của các replica không hết hạn đồng thời.
- Khi cache hết hạn, chỉ cho một request thực hiện refresh; các request còn lại dùng kết quả đang có hoặc chờ cùng một future.
- Dùng stale-while-revalidate nếu dữ liệu cũ vẫn an toàn trong một khoảng thời gian.
- Không giữ instance đã biết là không khỏe quá lâu chỉ để tránh query.
- Tách cache theo serviceId nếu consumer chỉ cần một số dịch vụ.
- Không gọi getServices() toàn bộ registry nếu chỉ cần getInstances() cho một service cụ thể.

Single-flight là cơ chế gộp nhiều yêu cầu refresh cùng khóa thành một thao tác. Ví dụ, 100 request cùng yêu cầu danh sách inventory-service trong lúc cache hết hạn sẽ chia sẻ một lần refresh thay vì tạo 100 truy vấn.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A["Nhiều request cần instance list"] --> B["Kiểm tra cache theo serviceId"]
    B --> C{"Cache còn dùng được?"}
    C -->|"Có"| D["Trả cache"]
    C -->|"Không"| E["Kiểm tra refresh đang chạy"]
    E --> F{"Đã có refresh cùng khóa?"}
    F -->|"Có"| G["Chờ/chia sẻ kết quả"]
    F -->|"Chưa"| H["Tạo một refresh"]
    H --> I["Gọi DiscoveryClient"]
    I --> J["Cập nhật cache và giải phóng waiter"]
    J --> G
~~~

Không dùng stale data vô thời hạn. Đặt max stale age và chính sách fallback rõ ràng. Nếu endpoint đã bị gỡ vì lý do bảo mật hoặc địa chỉ đã thay đổi, dùng cache quá cũ có thể khiến consumer tiếp tục gửi traffic đến instance không còn được phép.

## 10. Jitter cho cache TTL và lịch refresh

Nếu mọi consumer dùng TTL 30 giây tính từ cùng một thời điểm deploy, chúng có thể cùng refresh ở giây thứ 30. Có thể thêm phần ngẫu nhiên vào TTL hoặc lịch refresh:

\[
TTL_{\text{effective}} = TTL_{\text{base}} + Uniform(-jitter,\ +jitter)
\]

Ví dụ TTL cơ sở 30 giây và jitter ±5 giây sẽ phân tán thời điểm hết hạn trong khoảng 25–35 giây. Không chọn jitter lớn đến mức dữ liệu stale vượt quá giới hạn chấp nhận.

Jitter phải nhỏ hơn TTL cơ sở để thời gian sống hiệu dụng luôn dương. Nếu TTL có ý nghĩa bảo mật hoặc giới hạn stale nghiêm ngặt, hãy tính cả biên thấp nhất và cao nhất thay vì chỉ dùng giá trị trung bình.

Một cách khác là refresh định kỳ với initial delay ngẫu nhiên cho mỗi process, sau đó dùng fixed delay từ thời điểm hoàn thành lần refresh trước. Fixed delay giúp tránh việc thao tác chậm kéo lịch chạy chồng lấn; vẫn cần giới hạn một refresh đang chạy tại một thời điểm.

Không thêm jitter vào deadline hoặc timeout của request nghiệp vụ theo cách làm vượt SLA. Jitter ở đây nhằm phân tán thời điểm thực hiện các tác vụ nền, không phải trì hoãn response tùy tiện.

## 11. Giới hạn concurrency và tốc độ truy cập registry

Ngay cả khi retry có jitter, nhiều client vẫn có thể cùng truy vấn registry trong một khoảng ngắn. Cần giới hạn số thao tác đồng thời và tốc độ phát request.

Có thể áp dụng:

- Semaphore hoặc bulkhead cho số truy vấn discovery đang chạy.
- Token bucket/rate limiter cho số request mỗi giây.
- Bounded queue cho công việc refresh hoặc re-register.
- Giới hạn số registration xử lý đồng thời trong một worker.
- Timeout cho từng thao tác và deadline cho toàn bộ quá trình.
- Circuit breaker để tạm ngừng gọi backend khi lỗi liên tục, sau đó half-open với số probe nhỏ.

Ví dụ semaphore giới hạn số thao tác đồng thời trong một process:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class DiscoveryConcurrencyLimiter {

    private final Semaphore permits = new Semaphore(4);

    public <T> T execute(
            java.util.concurrent.Callable<T> operation,
            long timeoutMillis) throws Exception {

        if (!permits.tryAcquire(timeoutMillis, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Discovery concurrency limit reached");
        }

        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Semaphore trên chỉ giới hạn trong một JVM. Nếu có 100 replica và mỗi replica cho phép 4 request đồng thời, registry vẫn có thể nhận tới 400 request cùng lúc. Muốn giới hạn toàn cụm, cần rate limit hoặc quota ở gateway, registry, service mesh hay tầng điều phối phù hợp.

Trong ví dụ, timeoutMillis chỉ là thời gian chờ lấy permit. Bản thân operation vẫn cần connect/read timeout riêng và deadline tổng thể; nếu operation treo vô hạn, permit sẽ bị giữ và làm cạn concurrency của process.

Không dùng queue không giới hạn. Khi registry chậm, queue sẽ phình lên, giữ nhiều tác vụ hết deadline và tạo thêm tải khi backend phục hồi. Hãy giới hạn kích thước queue, loại bỏ tác vụ đã quá hạn và áp dụng backpressure.

## 12. Circuit breaker và phục hồi có kiểm soát

Circuit breaker giúp ngăn client tiếp tục gửi request đến backend đang lỗi. Một mô hình thường dùng:

- **Closed:** request được phép đi qua; lỗi được ghi nhận.
- **Open:** tạm dừng gọi backend trong một khoảng thời gian.
- **Half-open:** chỉ cho một số ít probe thử lại.
- Nếu probe thành công, chuyển về closed; nếu thất bại, quay lại open.

Với discovery registry, circuit breaker nên có giới hạn probe nhỏ và jitter khi nhiều replica cùng chuyển half-open. Nếu 500 client cùng mở circuit trong 30 giây rồi cùng half-open, registry vẫn có thể nhận một đợt probe lớn.

Circuit breaker không thay thế cache và không tự khôi phục registration. Nó chỉ kiểm soát request đến dependency đang lỗi. Khi circuit open, ứng dụng cần quyết định có thể dùng cache cũ, tiếp tục xử lý request hiện tại hay trả lỗi phụ thuộc dịch vụ.

Đối với thao tác đăng ký, không được giả vờ registration thành công khi circuit open. Provider nên giữ readiness phù hợp và tiếp tục retry theo lịch có giới hạn.

## 13. Lưu ý theo từng registry

### Eureka

Eureka Client có các tác vụ heartbeat và registry fetch định kỳ. Khi nhiều client cùng khởi động hoặc reconnect, cần quan sát thời điểm renewal/fetch và tránh tạo thêm vòng polling riêng trùng chức năng với client tích hợp.

Các điểm cần chú ý:

- Dùng lease renewal và expiration phù hợp với mạng, không giảm quá thấp để ép phát hiện nhanh.
- Giữ registry fetch interval ở mức phù hợp với độ tươi của danh sách instance.
- Kiểm tra hành vi self-preservation trước khi diễn giải việc instance cũ còn trong registry.
- Dùng local cache của client/LoadBalancer có chủ đích và đo độ stale.
- Tránh để health check của mọi consumer gọi getServices() liên tục nếu không cần danh sách toàn bộ service.

### Consul

Consul agent thực hiện health check và đồng bộ trạng thái service. Khi nhiều service được tạo lại cùng lúc, agent và server có thể nhận nhiều registration/check update.

Các điểm cần chú ý:

- Phân tán thời điểm startup và đăng ký.
- Chọn check interval/timeout phù hợp; không đặt interval quá ngắn cho hàng nghìn service.
- Consumer chỉ truy vấn passing khi cần lọc instance khỏe.
- Dùng cache phía consumer và giới hạn tần suất refresh.
- Theo dõi trạng thái agent, node và service riêng; đừng để toàn bộ consumer cùng poll Catalog API sau một sự kiện leader election.

### ZooKeeper

ZooKeeper client dùng session và ephemeral znode. Sau khi ensemble phục hồi hoặc nhiều session hết hạn, nhiều client có thể cùng tạo session và đăng ký lại node.

Các điểm cần chú ý:

- Khi SUSPENDED, không vội tạo session mới nếu session cũ có thể còn hiệu lực.
- Khi LOST, đăng ký lại bằng session mới và ID ổn định.
- Phân tán reconnect và registration retry ở tầng ứng dụng nếu thư viện cho phép cấu hình phù hợp.
- Dùng watcher để nhận thay đổi thay vì polling liên tục, nhưng vẫn cần resync sau reconnect.
- Sau khi reconnect, phân tán các lần full resync; không để mọi consumer đồng loạt đọc toàn bộ cây service.

Các thư viện client có cơ chế reconnect riêng. Không bọc thêm một vòng retry bên ngoài mà không hiểu retry nội bộ, vì hai lớp có thể nhân số lần thử và làm tải tăng mạnh.

## 14. Spring Cloud: tránh chồng nhiều cơ chế retry

Một ứng dụng có thể đồng thời có retry ở nhiều tầng:

- Registry client tự reconnect.
- Discovery adapter retry request đến registry.
- Spring Cloud LoadBalancer retry khi chọn instance hoặc gọi lại.
- HTTP client retry kết nối.
- Resilience4j retry hoặc circuit breaker.
- Mã nghiệp vụ tự lặp khi nhận lỗi.

Nếu không xác định tầng chịu trách nhiệm, số lần thử có thể nhân lên. Ví dụ ba tầng đều retry tối đa 3 lần có thể tạo 27 lần thử cho một thao tác gốc.

Nên lập bảng rõ:

| Tầng | Trách nhiệm | Giới hạn |
|---|---|---|
| Registry client | Duy trì session/connection và refresh registry | Dùng cơ chế của thư viện, tránh thêm vòng trùng |
| Discovery cache | Giữ danh sách instance và refresh | TTL, jitter, single-flight |
| LoadBalancer/HTTP client | Chọn instance và xử lý lỗi kết nối | Retry nhỏ, có timeout |
| Business service | Quyết định fallback và idempotency | Deadline tổng thể và retry budget |

Kiểm tra phiên bản Spring Cloud và implementation cụ thể trước khi thay đổi thuộc tính. Không có một property chung để bật jitter cho mọi Eureka, Consul, ZooKeeper và LoadBalancer. Nếu thư viện không cung cấp điểm cấu hình, có thể cần adapter, scheduler hoặc orchestration ở tầng ứng dụng; không sửa trực tiếp internals của thư viện nếu không có lý do rõ ràng.

## 15. Quan sát để phát hiện thundering herd

Cần đo cả số lượng và thời điểm request. Tổng request trong một phút có thể bình thường nhưng vẫn che giấu một đỉnh tải rất lớn trong vài giây.

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| registration_attempt_total | Tổng số lần provider thử đăng ký |
| registration_success_total | Số lần đăng ký thành công |
| registration_retry_total | Số lần retry đăng ký |
| discovery_query_total | Tổng số truy vấn discovery |
| discovery_query_duration | Latency của getServices/getInstances/probe |
| discovery_refresh_inflight | Số lần refresh đang chạy |
| discovery_cache_hit_ratio | Tỷ lệ dùng được cache |
| registry_connection_state | Trạng thái kết nối client |
| retry_delay_seconds | Thời gian backoff được chọn |
| registry_error_rate | Tỷ lệ lỗi từ backend |

Theo dõi p50, p95, p99 và max latency; thêm histogram theo operation, không gắn serviceId hoặc instanceId không giới hạn vào label nếu gây high cardinality.

Log nên chứa operation, attempt, delay, serviceId ở mức cần thiết, registry endpoint đã được che thông tin nhạy cảm và connection state. Không log credential, token hoặc toàn bộ metadata tùy tiện.

Một dấu hiệu thundering herd là số request/connection tăng đột biến ngay sau reconnect hoặc deployment, sau đó timeout tăng và retry rate tiếp tục tăng. Đặt alert cho retry rate, queue depth, registration conflict và thời gian phục hồi.

## 16. Kiểm thử tình huống phục hồi

Có thể tạo một bài kiểm thử tải có kiểm soát:

1. Khởi động registry và một nhóm provider/consumer.
2. Ghi nhận baseline của registration, discovery query và latency.
3. Tạm chặn kết nối registry trong môi trường lab.
4. Khởi động lại registry hoặc khôi phục network.
5. Quan sát số reconnect, register và query theo từng giây.
6. So sánh khi không có jitter với khi có backoff, jitter, cache và giới hạn concurrency.
7. Kiểm tra registry có bị quá tải lại không.
8. Kiểm tra provider có đăng ký trùng hoặc consumer có dùng instance cũ quá lâu không.
9. Đo thời gian đến khi phần lớn client phục hồi.
10. Lặp lại với số lượng client lớn hơn và các khoảng lỗi khác nhau.

Không thử ngắt mạng hoặc làm mất quorum trên môi trường production. Bài test cần giới hạn số client, có khả năng rollback và không dùng dữ liệu nghiệp vụ thật.

Các tiêu chí so sánh:

- Đỉnh request mỗi giây đến registry.
- Số connection đồng thời.
- Tỷ lệ registration thành công.
- Thời gian đến khi 95% client phục hồi.
- Số lần retry trung bình và lớn nhất.
- Tỷ lệ request nghiệp vụ thất bại trong giai đoạn phục hồi.
- Độ cũ tối đa của cache discovery.

Một cấu hình tốt không nhất thiết làm client đầu tiên phục hồi nhanh nhất. Mục tiêu là phục hồi toàn hệ thống ổn định, không tạo đợt quá tải mới và vẫn đáp ứng giới hạn stale data đã chấp nhận.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Registry vừa phục hồi lại mất kết nối | Client reconnect đồng loạt | Backoff với full jitter và giới hạn concurrency |
| Nhiều registration trùng | Mỗi retry tạo instance ID mới | Dùng ID ổn định và registration idempotent |
| Consumer đồng loạt tải danh sách service | Cache hết hạn cùng lúc hoặc polling đồng bộ | TTL jitter, single-flight và targeted query |
| Retry tăng theo cấp số nhân | Retry chồng ở nhiều tầng | Chỉ định tầng retry chính, giới hạn tổng budget |
| Registry bị query liên tục dù không có traffic | Scheduled refresh hoặc health check quá dày | Điều chỉnh interval, cache và probe nhẹ |
| Sau reconnect consumer vẫn gọi instance cũ | Cache hoặc watcher chưa cập nhật | Resync có giới hạn, max stale age và loại endpoint lỗi |
| Queue refresh tăng không giới hạn | Backend chậm nhưng công việc vẫn được xếp hàng | Bounded queue, deadline và backpressure |
| Circuit breaker cùng half-open một lúc | Recovery window đồng bộ | Jitter thời gian mở lại và giới hạn probe |
| Provider readiness UP trước khi register | Startup lifecycle không chờ registration | Gắn readiness với trạng thái đăng ký nếu discovery là bắt buộc |
| Registry bị quá tải sau rolling deploy | Quá nhiều replica mới cùng tạo | Chia đợt rollout, giới hạn surge và random startup delay |

## 18. Checklist thiết kế

Trước khi đưa cơ chế phục hồi vào production, xác nhận:

1. Registration và query có phân loại lỗi tạm thời với lỗi cấu hình/permanent.
2. Retry dùng exponential backoff có jitter và max delay.
3. Mỗi thao tác có giới hạn số lần thử và deadline tổng thể.
4. Retry budget giới hạn tổng tải retry.
5. Instance ID ổn định và registration có thể retry an toàn.
6. Startup và rollout không tạo hàng loạt registration cùng thời điểm.
7. Cache discovery có TTL phù hợp và jitter.
8. Refresh cùng serviceId được gộp bằng single-flight hoặc cơ chế tương đương.
9. Có giới hạn concurrency, rate limit và bounded queue.
10. Circuit breaker có half-open probe giới hạn và không đồng bộ.
11. Không chồng retry ở registry client, LoadBalancer, HTTP client và business service.
12. Readiness không UP khi điều kiện registration bắt buộc chưa hoàn thành.
13. Watcher reconnect có resync nhưng resync được phân tán.
14. Có metric cho retry, registration, query, cache và recovery time.
15. Đã kiểm thử outage/recovery trong môi trường lab.

Điểm cốt lõi là: **sau sự cố, đừng để mọi client cùng thử lại ngay lập tức.** Phân tán thời điểm bằng jitter, giới hạn số lần và tốc độ thử, gộp truy vấn trùng, tận dụng cache còn an toàn và quan sát quá trình phục hồi. Registry cần nhận tải tăng dần theo khả năng xử lý của nó để hệ thống trở lại ổn định mà không tạo ra một sự cố thứ hai.

