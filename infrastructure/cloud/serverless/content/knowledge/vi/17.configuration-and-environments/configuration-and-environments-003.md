# Biến môi trường, cấu hình động và bộ nhớ đệm cấu hình

Một Java function serverless có thể chạy ở nhiều môi trường như development, staging và production, đồng thời được mở rộng thành nhiều execution environment khi lưu lượng tăng. Mỗi instance cần biết endpoint dịch vụ, giới hạn xử lý, feature flag và các tham số vận hành. Nếu gắn các giá trị này trực tiếp vào mã nguồn, việc thay đổi cấu hình sẽ kéo theo build và deploy, đồng thời dễ tạo khác biệt giữa các môi trường.

Một thiết kế tốt tách **cấu hình gắn với lần triển khai**, **cấu hình có thể thay đổi khi ứng dụng đang chạy** và **secret**. Biến môi trường phù hợp với giá trị cấu hình theo deployment hoặc revision. Dynamic configuration phù hợp với feature flag, ngưỡng và chính sách cần thay đổi mà không triển khai lại. Secret cần được quản lý bằng hệ thống chuyên dụng và có quy trình cấp quyền, rotation. Vì function có thể scale-out thành nhiều instance, bộ nhớ đệm cấu hình phải có TTL, giới hạn độ cũ và hành vi khi nguồn cấu hình không khả dụng.

Bài học tập trung vào cách tổ chức cấu hình cho Java serverless, đọc và kiểm tra biến môi trường, tải cấu hình động, cache an toàn giữa các invocation và vận hành thay đổi cấu hình mà không làm hệ thống mất kiểm soát.

## 1. Ba loại dữ liệu cấu hình

Không phải giá trị nào ứng dụng đọc lúc khởi động cũng có cùng vòng đời. Hãy phân loại trước khi chọn nơi lưu.

| Loại | Ví dụ | Nơi quản lý phù hợp | Cách thay đổi |
|---|---|---|---|
| Cấu hình deployment | Region, tên queue, URL service, port, mức concurrency dự kiến | Biến môi trường hoặc cấu hình của revision/deployment | Thường thay đổi qua deploy/configuration update |
| Cấu hình động | Feature flag, ngưỡng nghiệp vụ, giới hạn theo tenant, tỷ lệ rollout | Dynamic configuration service hoặc database có quyền kiểm soát | Có thể cập nhật khi function đang chạy |
| Secret | API key, database password, signing key, token truy cập | Secret manager hoặc cơ chế secret tích hợp của nền tảng | Rotation theo quy trình bảo mật |

Ví dụ:

- `PAYMENT_API_BASE_URL` là cấu hình deployment vì endpoint thường khác giữa staging và production.
- `ENABLE_NEW_CHECKOUT` là feature flag có thể cần bật/tắt mà không deploy.
- `MAX_CART_ITEMS` có thể là cấu hình động nếu nhóm vận hành cần thay đổi giới hạn thường xuyên.
- `PAYMENT_API_SECRET` là secret và cần được bảo vệ, rotation.

Một giá trị có thể thuộc loại khác tùy yêu cầu. Ví dụ, giới hạn request cố định theo từng revision có thể là biến môi trường; giới hạn cần thay đổi tức thời theo tải có thể là dynamic config. Quyết định dựa trên tần suất thay đổi, mức độ quan trọng, yêu cầu nhất quán và khả năng chịu độ trễ khi cập nhật.

## 2. Biến môi trường trong serverless

Biến môi trường là cặp tên/giá trị được nền tảng đưa vào process khi khởi tạo runtime. Java đọc chúng qua `System.getenv()`.

Ví dụ:

```text
APP_ENV=production
PAYMENT_API_BASE_URL=https://payments.internal
HTTP_CONNECT_TIMEOUT_MS=1500
HTTP_REQUEST_TIMEOUT_MS=4000
MAX_BATCH_SIZE=100
ENABLE_VERBOSE_LOGGING=false
```

Trong Java:

```java
String environment = System.getenv("APP_ENV");
String paymentUrl = System.getenv("PAYMENT_API_BASE_URL");
```

Biến môi trường phù hợp với cấu hình không cần thay đổi liên tục. Với nhiều nền tảng, thay đổi environment variables tạo revision hoặc configuration version mới; các instance đang chạy có thể tiếp tục dùng cấu hình cũ cho đến khi được thay thế. Không nên giả định thay biến môi trường trong console sẽ cập nhật ngay lập tức vào process đang chạy.

### Đặc điểm cần nhớ

- Giá trị thường được thiết lập ở cấp function, service, deployment hoặc revision.
- Mỗi môi trường có thể có bộ giá trị riêng.
- Biến môi trường có thể được đọc lúc init và giữ trong object cấu hình bất biến.
- Mỗi execution environment có bản sao riêng; biến môi trường không phải kho cấu hình dùng chung có khả năng đồng bộ.
- Không dùng biến môi trường để truyền lượng dữ liệu lớn hoặc danh sách thay đổi liên tục.
- Không log toàn bộ environment variables vì có thể chứa secret hoặc thông tin nội bộ.

### Quy ước đặt tên

Nên dùng tên rõ ràng, nhất quán và có đơn vị:

- `HTTP_CONNECT_TIMEOUT_MS` thay vì `TIMEOUT`.
- `MAX_RECORDS_PER_BATCH` thay vì `LIMIT`.
- `FEATURE_CHECKOUT_V2` thay vì `NEW_FEATURE`.
- `PAYMENT_API_BASE_URL` thay vì `URL`.

Nếu cùng một tham số được dùng ở nhiều module, thống nhất cách đặt tên và định nghĩa. Giá trị số cần có đơn vị trong tên hoặc tài liệu để tránh nhầm giây với mili giây.

## 3. Tạo cấu hình có kiểu dữ liệu trong Java

Không nên gọi `System.getenv()` rải rác trong nhiều class. Hãy đọc cấu hình ở một nơi, chuyển thành kiểu dữ liệu phù hợp và kiểm tra ngay khi khởi tạo.

Ví dụ dùng Java record:

```java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record AppConfig(
        String environment,
        URI paymentApiBaseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        int maxBatchSize,
        boolean verboseLogging) {

    public static AppConfig fromEnvironment(
            Map<String, String> env) {

        String environment = required(env, "APP_ENV");
        URI paymentUrl = URI.create(
                required(env, "PAYMENT_API_BASE_URL"));

        int connectMs = integer(
                env, "HTTP_CONNECT_TIMEOUT_MS", 1500);
        int requestMs = integer(
                env, "HTTP_REQUEST_TIMEOUT_MS", 4000);
        int batchSize = integer(
                env, "MAX_BATCH_SIZE", 100);
        boolean verbose = bool(
                env, "ENABLE_VERBOSE_LOGGING", false);

        if (connectMs <= 0 || requestMs <= 0) {
            throw new IllegalArgumentException(
                    "HTTP timeouts must be positive");
        }
        if (requestMs < connectMs) {
            throw new IllegalArgumentException(
                    "Request timeout must not be shorter than connect timeout");
        }
        if (batchSize < 1 || batchSize > 500) {
            throw new IllegalArgumentException(
                    "MAX_BATCH_SIZE must be between 1 and 500");
        }
        if (!"https".equalsIgnoreCase(paymentUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "Payment API must use HTTPS");
        }

        return new AppConfig(
                environment,
                paymentUrl,
                Duration.ofMillis(connectMs),
                Duration.ofMillis(requestMs),
                batchSize,
                verbose);
    }

    private static String required(
            Map<String, String> env,
            String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }
        return value.trim();
    }

    private static int integer(
            Map<String, String> env,
            String key,
            int defaultValue) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Invalid integer configuration: " + key, ex);
        }
    }

    private static boolean bool(
            Map<String, String> env,
            String key,
            boolean defaultValue) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return defaultValue;
        }
        if ("true".equalsIgnoreCase(value.trim())) {
            return true;
        }
        if ("false".equalsIgnoreCase(value.trim())) {
            return false;
        }
        throw new IllegalArgumentException(
                "Invalid boolean configuration: " + key);
    }
}
```

Khởi tạo một lần ở giai đoạn init:

```java
private static final AppConfig CONFIG =
        AppConfig.fromEnvironment(System.getenv());
```

Cách này giúp các class nhận cấu hình qua constructor thay vì tự đọc biến môi trường. Nếu cấu hình bắt buộc bị thiếu hoặc sai, ứng dụng thất bại sớm với thông báo rõ ràng, thay vì chạy một thời gian rồi lỗi ở một request ngẫu nhiên.

Không đưa giá trị secret vào exception message. Trong ví dụ, lỗi chỉ nêu tên key cấu hình chứ không in giá trị.

### Giá trị mặc định cần có chủ đích

Default phù hợp với tham số có giá trị an toàn và được hiểu rõ, ví dụ bật/tắt log chi tiết hoặc batch size mặc định nhỏ. Không nên đặt default cho cấu hình thiết yếu như endpoint thanh toán, bucket lưu dữ liệu hoặc region nếu thiếu nó có thể khiến dữ liệu đi nhầm nơi.

Đối với tham số bảo mật, default phải fail-closed. Ví dụ, nếu không xác định được chế độ xác thực, không nên mặc định cho phép truy cập công khai.

## 4. Tách cấu hình theo môi trường

Development, staging và production thường khác nhau ở endpoint, quota, secret và chính sách vận hành. Cần quản lý các bộ cấu hình có thể so sánh và review.

Ví dụ bảng cấu hình:

| Key | Development | Staging | Production |
|---|---|---|---|
| APP_ENV | development | staging | production |
| PAYMENT_API_BASE_URL | sandbox endpoint | staging endpoint | production endpoint |
| HTTP_REQUEST_TIMEOUT_MS | 5000 | 4000 | 3000 |
| MAX_BATCH_SIZE | 20 | 50 | 100 |
| ENABLE_CHECKOUT_V2 | true | true | false |
| LOG_LEVEL | DEBUG | INFO | INFO |

Không sao chép nguyên bộ production secret vào staging hoặc development. Dùng secret riêng cho từng môi trường và giới hạn quyền đọc.

Cấu hình nên được quản lý dưới dạng code hoặc deployment manifest có review. Tuy nhiên, manifest chỉ nên chứa giá trị không nhạy cảm hoặc tham chiếu đến secret, không chứa plaintext secret. Hạn chế sửa cấu hình production thủ công ngoài quy trình vì sẽ tạo configuration drift giữa môi trường và source of truth.

## 5. Cấu hình động là gì?

Dynamic configuration là dữ liệu cấu hình được ứng dụng tải từ một nguồn bên ngoài trong khi process đang chạy. Nhờ vậy, nhóm vận hành có thể thay đổi một số hành vi mà không cần build và deploy lại function.

Ví dụ:

- Bật feature flag cho một nhóm người dùng.
- Thay đổi giới hạn số item trong request.
- Điều chỉnh tỷ lệ rollout một tính năng.
- Tắt một integration đang gặp sự cố.
- Thay đổi ngưỡng cảnh báo hoặc chính sách retry.
- Điều chỉnh mức độ xử lý theo tenant.

Nguồn dynamic config có thể là:

- Dịch vụ quản lý cấu hình của cloud provider.
- Feature flag service.
- Database hoặc key-value store có schema và quyền cập nhật rõ ràng.
- Một API nội bộ cung cấp snapshot cấu hình có version.

Dynamic configuration không nên được dùng như một nơi thay thế mọi biến môi trường. Những giá trị quyết định nơi function chạy, danh tính, quyền truy cập, network hoặc resource binding thường nên gắn với deployment để có thể review và rollout có kiểm soát.

### Phân biệt config động và secret

Dynamic config thường chứa tham số vận hành, không phải credential. Secret cần cơ chế quản lý vòng đời, mã hóa, audit, rotation và phân quyền riêng.

Không đưa password, private key hoặc access token vào một bảng feature flag chỉ vì ứng dụng đã có client đọc bảng đó. Dùng secret manager hoặc cơ chế secret tích hợp của nền tảng.

## 6. Thiết kế schema cho dynamic configuration

Dynamic config nên có schema và version rõ ràng. Tránh lưu một JSON tùy ý mà mỗi service tự diễn giải theo cách khác nhau.

Ví dụ snapshot cấu hình:

```json
{
  "version": 42,
  "updatedAt": "2026-11-17T10:15:00Z",
  "features": {
    "checkoutV2": true,
    "asyncReceipt": false
  },
  "limits": {
    "maxCartItems": 50,
    "maxRequestsPerMinute": 120
  }
}
```

Một schema tốt nên xác định:

- Tên và kiểu dữ liệu của từng trường.
- Trường bắt buộc và trường tùy chọn.
- Giá trị mặc định có an toàn không.
- Phạm vi hợp lệ của số và thời gian.
- Version schema và cách tương thích ngược.
- Ai được thay đổi từng nhóm cấu hình.
- Thời điểm hiệu lực và cách rollback.
- Cách xử lý trường không được phiên bản ứng dụng nhận biết.

Nên dùng immutable object sau khi parse và validate. Không để nhiều thread cùng sửa một Map cấu hình đang được dùng bởi các invocation. Mỗi lần refresh, tạo một snapshot mới rồi thay tham chiếu nguyên tử.

### Version và rollback

Mỗi lần cập nhật nên có version tăng dần hoặc revision ID. Khi có sự cố, operator có thể quay về version trước và xác minh instance nào đã nhận version nào.

Không chỉ dựa vào timestamp để so sánh thứ tự cập nhật vì đồng hồ ở các hệ thống có thể lệch. Version tăng dần hoặc ID bất biến do config service cấp thường dễ kiểm soát hơn.

## 7. Cache cấu hình trong serverless

Nếu mỗi invocation đều gọi config service để lấy dynamic config, hệ thống sẽ tạo nhiều network request, tăng latency và phụ thuộc vào availability của dịch vụ cấu hình. Cache giúp giảm tải và tăng tốc.

Tuy nhiên, cache trong bộ nhớ function có phạm vi cục bộ:

- Mỗi execution environment có cache riêng.
- Khi scale-out, nhiều instance có thể giữ các version khác nhau trong một khoảng thời gian.
- Khi instance bị dừng, cache mất.
- Khi snapshot/restore được dùng, cache trong heap có thể được nhân bản hoặc đã quá hạn.
- Một lần refresh ở instance A không tự cập nhật cache ở instance B.

Vì vậy, cache không phải nguồn dữ liệu chuẩn. Nó là bản sao có thời hạn của config service.

### TTL và giới hạn độ cũ

TTL xác định thời gian một snapshot được xem là còn mới. Ví dụ, TTL 30 giây nghĩa là instance có thể tiếp tục dùng cấu hình đã tải trong tối đa 30 giây trước khi cần refresh.

Cần phân biệt:

- **Fresh TTL:** thời gian có thể dùng snapshot mà không cần refresh.
- **Maximum stale age:** khoảng thời gian tối đa được phép dùng snapshot cũ khi nguồn cấu hình gặp lỗi.
- **Refresh timeout:** giới hạn thời gian chờ config service.
- **Refresh interval:** khoảng cách giữa các lần refresh nếu dùng cơ chế chủ động.

Không nên để stale fallback vô thời hạn. Nếu cấu hình cũ có thể gây rủi ro bảo mật hoặc sai nghiệp vụ, cần fail-closed khi quá giới hạn stale.

## 8. Ví dụ cache dynamic config trong Java

Ví dụ sau dùng một provider trừu tượng để tải cấu hình. Có thể triển khai provider bằng SDK của cloud config service, HTTP API nội bộ hoặc database.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class DynamicConfigCache {

    public interface Provider {
        DynamicSettings fetch(Duration timeout) throws Exception;
    }

    public record DynamicSettings(
            long version,
            boolean checkoutV2Enabled,
            int maxCartItems) {

        public DynamicSettings {
            if (version < 1) {
                throw new IllegalArgumentException("Invalid config version");
            }
            if (maxCartItems < 1 || maxCartItems > 500) {
                throw new IllegalArgumentException("Invalid maxCartItems");
            }
        }
    }

    private record Snapshot(
            DynamicSettings settings,
            Instant loadedAt,
            Instant expiresAt,
            Instant staleUntil) {
    }

    private final Provider provider;
    private final Clock clock;
    private final Duration ttl;
    private final Duration maxStale;
    private final Duration refreshTimeout;

    private volatile Snapshot current;

    public DynamicConfigCache(
            Provider provider,
            Clock clock,
            Duration ttl,
            Duration maxStale,
            Duration refreshTimeout) {
        this.provider = Objects.requireNonNull(provider);
        this.clock = Objects.requireNonNull(clock);
        this.ttl = Objects.requireNonNull(ttl);
        this.maxStale = Objects.requireNonNull(maxStale);
        this.refreshTimeout = Objects.requireNonNull(refreshTimeout);

        if (ttl.isNegative() || ttl.isZero()
                || maxStale.isNegative()
                || refreshTimeout.isNegative()
                || refreshTimeout.isZero()) {
            throw new IllegalArgumentException("Invalid cache durations");
        }
    }

    public DynamicSettings get() {
        Instant now = clock.instant();
        Snapshot snapshot = current;

        if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
            return snapshot.settings();
        }

        synchronized (this) {
            now = clock.instant();
            snapshot = current;

            if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
                return snapshot.settings();
            }

            try {
                // Provider phải tự áp dụng network timeout <= refreshTimeout.
                DynamicSettings fresh = provider.fetch(refreshTimeout);
                Instant loadedAt = clock.instant();

                Snapshot replacement = new Snapshot(
                        fresh,
                        loadedAt,
                        loadedAt.plus(ttl),
                        loadedAt.plus(ttl).plus(maxStale));

                current = replacement;
                return fresh;
            } catch (Exception refreshError) {
                if (snapshot != null
                        && clock.instant().isBefore(snapshot.staleUntil())) {
                    return snapshot.settings();
                }
                throw new IllegalStateException(
                        "Dynamic configuration is unavailable",
                        refreshError);
            }
        }
    }
}
```

Đây là ví dụ minh họa cache đồng bộ và single-flight trong phạm vi một process: các thread cùng instance không đồng thời tải nhiều bản cấu hình khi TTL hết hạn. Provider cần tự cấu hình connect/request timeout không vượt ngân sách `refreshTimeout`; trong ứng dụng hoàn chỉnh, nên truyền timeout này vào provider thay vì chỉ lưu nó trong cache.

Các điểm quan trọng:

- Snapshot là immutable record; refresh thay toàn bộ tham chiếu bằng một snapshot mới.
- `volatile` bảo đảm thread khác nhìn thấy snapshot đã thay thế.
- Double-check bên trong synchronized tránh nhiều thread cùng refresh.
- Stale fallback chỉ được phép đến `staleUntil`.
- Nếu chưa từng tải được cấu hình và provider lỗi, cache không có dữ liệu để fallback.
- Không log nội dung cấu hình hoặc secret khi refresh lỗi.

Đoạn code không tạo background thread. Trong serverless, thread nền có thể không được chạy liên tục giữa các invocation hoặc trước khi instance bị dừng. Refresh theo nhu cầu với timeout rõ ràng thường dễ dự đoán hơn; nếu dùng background refresh, phải kiểm tra lifecycle và bảo đảm request vẫn có đường xử lý khi refresh chưa hoàn tất.

## 9. Chống refresh stampede và quản lý độ trễ

Khi TTL hết hạn, nhiều request có thể đến cùng lúc. Nếu mọi thread đều gọi config service, một instance có thể tạo burst request. Khi nhiều execution environment cùng hết TTL gần nhau, tổng burst còn lớn hơn.

Một số biện pháp:

- Single-flight: chỉ một thread trong mỗi process thực hiện refresh, các thread khác dùng snapshot cũ hoặc chờ theo chính sách.
- TTL jitter: thêm độ lệch ngẫu nhiên nhỏ vào thời điểm hết hạn để các instance không refresh đồng loạt.
- Refresh timeout: giới hạn thời gian chờ nguồn cấu hình.
- Backoff: khi refresh thất bại, không thử lại trên mọi request.
- Stale-while-revalidate: tiếp tục dùng snapshot cũ trong giới hạn cho phép trong lúc một refresh đang chạy.
- Pre-warm có kiểm soát: tải cấu hình trong init nếu function cần config trước invocation đầu tiên.

Cache đồng bộ trong ví dụ trên khiến request đầu tiên sau khi hết TTL chờ refresh. Nếu độ trễ đó không chấp nhận được, có thể triển khai stale-while-revalidate với một tác vụ refresh có lifecycle được quản lý. Không dùng executor nền không được nền tảng hỗ trợ hoặc giả định instance sẽ sống đủ lâu để refresh hoàn tất.

Jitter chỉ giảm khả năng nhiều instance refresh cùng lúc; nó không tạo consistency toàn cục. Nếu cần thay đổi có hiệu lực gần như tức thời, hãy dùng cơ chế push/invalidation hoặc version check phù hợp, đồng thời tính đến việc một số instance có thể tạm thời chưa nhận update.

## 10. Chính sách khi config service không khả dụng

Config service cũng là một dependency. Nó có thể timeout, trả lỗi, bị giới hạn quota hoặc không truy cập được do network.

Cần xác định hành vi theo mức độ quan trọng của cấu hình:

| Loại cấu hình | Hành vi khi refresh lỗi |
|---|---|
| Feature flag không nhạy cảm | Có thể dùng snapshot cũ trong max stale age |
| Giới hạn tải hoặc quota | Dùng giá trị cũ trong thời gian ngắn nếu an toàn; sau đó áp dụng default bảo thủ hoặc từ chối |
| Chính sách bảo mật/authorization | Không dùng cấu hình cũ vô thời hạn; có thể fail-closed khi quá stale |
| Endpoint hoặc resource binding | Thường cần cấu hình deployment hợp lệ; không nên tự đoán endpoint thay thế |
| Secret hoặc credential | Refresh qua secret manager/provider; không dùng secret hết hạn hoặc bị thu hồi |

Không dùng một fallback chung cho mọi key. Với mỗi trường, xác định:

- Có thể dùng giá trị cũ tối đa bao lâu?
- Default có an toàn không?
- Khi không có giá trị hợp lệ, request nào cần từ chối?
- Có cần alert ngay khi refresh thất bại không?
- Ai có quyền rollback hoặc thay đổi config?

Nếu cache chưa từng có snapshot hợp lệ, không thể trả về dữ liệu giả định. Hãy fail rõ ràng hoặc dùng default đã được phê duyệt và kiểm tra.

## 11. Secret và rotation

Secret cần được quản lý tách biệt với cấu hình thông thường. Nền tảng cloud thường cung cấp secret manager hoặc khả năng tham chiếu secret khi deploy.

Nguyên tắc:

- Không commit secret vào Git hoặc đóng gói trong JAR/container image.
- Không đưa secret vào dynamic config store chỉ vì ứng dụng đã có cơ chế refresh.
- Cấp quyền đọc secret cho runtime service account ở phạm vi secret cụ thể.
- Không log giá trị secret, token, Authorization header hoặc chuỗi kết nối có password.
- Phân tách secret giữa development, staging và production.
- Theo dõi audit log và lịch sử rotation.
- Xử lý rotation có thời gian chuyển tiếp nếu provider cần đồng thời chấp nhận khóa cũ và mới.

### Inject secret lúc deploy hay đọc lúc chạy?

Hai cách có trade-off:

**Inject qua secret reference/environment hoặc volume:** đơn giản và giảm số lần gọi secret manager. Tuy nhiên, giá trị có thể gắn với revision hoặc được cập nhật theo semantics riêng của nền tảng. Cần biết khi nào instance nhận secret mới và có cần deploy lại không.

**Đọc từ Secret Manager lúc chạy:** cho phép refresh theo version hoặc rotation, nhưng thêm dependency mạng, IAM permission, latency và chi phí. Nên cache secret theo TTL phù hợp, có giới hạn stale nghiêm ngặt và xử lý rotation rõ ràng.

Không cache secret vô thời hạn. Khi credential bị thu hồi do sự cố bảo mật, cache quá lâu có thể kéo dài thời gian một instance tiếp tục dùng credential cũ.

## 12. Cấu hình động và feature flag an toàn

Feature flag cho phép bật/tắt hành vi mà không cần deploy, nhưng cũng có thể tạo trạng thái kết hợp khó kiểm thử. Ví dụ, checkout V2 bật trong khi payment integration mới chưa được cấu hình.

Hãy thiết kế flag với:

- Tên và mô tả mục đích.
- Owner chịu trách nhiệm.
- Ngày tạo và thời hạn dự kiến loại bỏ.
- Giá trị mặc định an toàn.
- Phạm vi áp dụng: toàn hệ thống, environment, tenant hoặc tỷ lệ người dùng.
- Điều kiện tương thích với phiên bản ứng dụng.
- Metric để đo tác động khi bật/tắt.

Không dùng feature flag để thay thế authorization. Một flag bật tính năng không đồng nghĩa người dùng có quyền thực hiện hành động. Backend vẫn phải kiểm tra role, owner và tenant.

Với rollout theo phần trăm, cần một phép phân nhóm ổn định để cùng một user không liên tục đổi giữa hai biến thể. Không dùng random mới cho mỗi request nếu muốn trải nghiệm ổn định; có thể hash một định danh phù hợp hoặc dùng feature flag provider. Không đưa PII vào log chỉ để theo dõi cohort.

### Kill switch

Một kill switch có thể tắt nhanh integration hoặc tính năng gặp sự cố. Nó cần được thiết kế sao cho đường đọc flag vẫn hoạt động khi dependency chính đang lỗi. Nếu kill switch nằm trong cùng một dịch vụ không truy cập được, nó không giúp khôi phục.

Với thao tác nguy hiểm, hãy ưu tiên default tắt và yêu cầu cấu hình rõ ràng để bật. Thử nghiệm quy trình bật/tắt trong staging và ghi nhận ai thay đổi.

## 13. Tương thích cấu hình giữa các phiên bản

Trong rollout serverless, revision cũ và revision mới có thể chạy đồng thời. Dynamic config mới phải tương thích với cả hai trong giai đoạn chuyển tiếp.

Ví dụ, revision mới hiểu trường `checkoutV2`, nhưng revision cũ không biết trường đó. Nếu config service thay đổi schema mà không có versioning, revision cũ có thể lỗi parse hoặc áp dụng default sai.

Một quy trình an toàn:

1. Deploy phiên bản ứng dụng có thể đọc cả schema cũ và mới.
2. Thêm trường cấu hình mới với default an toàn.
3. Cập nhật config service.
4. Theo dõi cả revision cũ và mới.
5. Chuyển traffic hoặc bật feature flag theo từng giai đoạn.
6. Sau khi không còn revision cũ, mới loại bỏ trường legacy.

Không đổi ý nghĩa của một key đang tồn tại mà không đổi version hoặc migration plan. Ví dụ, không đổi `timeout=5` từ giây sang mili giây trong khi tên key và schema vẫn giữ nguyên.

## 14. Cấu hình trong môi trường snapshot/restore

Một số runtime serverless có snapshot/restore để giảm cold start. Khi snapshot được khôi phục, biến static và cache trong heap có thể được nhân bản từ trạng thái tại thời điểm snapshot.

Với dynamic configuration, điều này có nghĩa:

- Snapshot có thể chứa config đã hết TTL khi restore.
- Nhiều execution environment có thể khởi đầu từ cùng version cache.
- Thời điểm refresh của các instance có thể lệch nhau.
- Secret hoặc token được tải trước snapshot có thể hết hạn.
- Deadline hoặc timestamp được lưu trước checkpoint không phản ánh thời điểm hiện tại.

Không xem cache trong heap là nguồn dữ liệu chuẩn. Khi restore, kiểm tra thời gian hết hạn và version; refresh nếu cần trước khi dùng cấu hình quan trọng. Nếu runtime cung cấp hook sau restore, có thể đánh dấu cache cần refresh hoặc làm mới tài nguyên phụ thuộc môi trường. Không thực hiện tác vụ nghiệp vụ trong hook.

Cũng cần tránh refresh đồng loạt ngay sau restore. Dùng jitter hoặc cơ chế single-flight theo instance và giới hạn tải lên config service.

## 15. Quan sát và kiểm toán thay đổi cấu hình

Khi một request xử lý khác thường, đội vận hành cần biết instance đã dùng version cấu hình nào. Không cần log toàn bộ cấu hình; chỉ cần version, source và các key không nhạy cảm có liên quan.

Metric và log hữu ích:

- Config version hiện tại theo service/revision.
- Thời điểm snapshot được tải và tuổi snapshot.
- Refresh success/failure count.
- Refresh latency và timeout count.
- Số lần dùng stale config.
- Số lần fallback về default.
- Lỗi validation hoặc schema mismatch.
- Secret refresh failure (không ghi secret value).
- Feature flag evaluation theo kết quả tổng hợp, tránh nhãn cardinality cao.

Mỗi lần cập nhật config nên có audit trail: ai thay đổi, thay đổi key nào, version trước/sau, lý do và thời điểm. Với thay đổi quan trọng, cần review hoặc approval theo quy trình tổ chức.

Không ghi toàn bộ dynamic config vào log nếu có thể chứa dữ liệu nhạy cảm hoặc tạo chi phí lớn. Ghi version và một số metadata đã được allow-list.

## 16. Kiểm thử cấu hình

Cấu hình là đầu vào của ứng dụng và cần được kiểm thử như code.

Các loại kiểm thử nên có:

| Kiểm thử | Điều cần xác minh |
|---|---|
| Missing required key | Ứng dụng fail fast với tên key, không in secret |
| Sai kiểu dữ liệu | Parser từ chối giá trị sai thay vì âm thầm dùng default |
| Ngoài phạm vi | Timeout âm, batch size quá lớn hoặc URL sai bị từ chối |
| Environment isolation | Staging không trỏ đến production endpoint hoặc secret |
| Dynamic schema | App đọc đúng version và xử lý field tùy chọn |
| Refresh đồng thời | Một instance không tạo nhiều request refresh không cần thiết |
| Config service timeout | Stale fallback hoặc fail-closed theo chính sách |
| TTL expiry | Snapshot hết hạn được refresh |
| Max stale exceeded | Không tiếp tục dùng config cũ vô thời hạn |
| Rollback | Có thể quay về version đã biết và xác minh kết quả |
| Snapshot restore | Cache cũ và secret hết hạn được phát hiện |
| Feature flag | Bật/tắt không bỏ qua authorization nghiệp vụ |

Dùng `Clock` có thể inject trong cache để kiểm thử TTL và stale age mà không phải chờ thời gian thật. Với provider, dùng fake implementation để mô phỏng timeout, lỗi 5xx và version mới.

## 17. Những lỗi triển khai thường gặp

- **Đọc biến môi trường ở khắp nơi:** cấu hình bị phân tán và khó kiểm tra; gom vào typed configuration object.
- **Không validate lúc khởi động:** function chạy với endpoint hoặc timeout sai rồi mới lỗi ở production; fail fast với key bắt buộc.
- **Đặt default cho cấu hình thiết yếu:** có thể làm dữ liệu đi sai nơi hoặc vô tình mở quyền; default chỉ cho trường thật sự an toàn.
- **Đưa secret vào log:** làm lộ credential; chỉ log tên key hoặc trạng thái refresh.
- **Dùng env var cho flag cần đổi tức thời:** thay đổi có thể yêu cầu revision mới; dùng dynamic config cho key có vòng đời phù hợp.
- **Gọi config service mỗi invocation:** tăng latency, request và chi phí; dùng cache có TTL.
- **Cache vô thời hạn:** instance có thể dùng chính sách cũ sau khi đã bị thu hồi; đặt max stale age.
- **Cho mọi instance refresh cùng lúc:** tạo thundering herd; dùng single-flight, jitter và backoff.
- **Dùng static cache làm nguồn chuẩn:** mỗi instance có bản riêng và có thể khác version; lưu source of truth ở dịch vụ ngoài.
- **Dùng một fallback cho mọi key:** cấu hình bảo mật có thể bị stale; phân loại theo mức độ quan trọng.
- **Đổi schema không tương thích:** revision cũ có thể lỗi trong rollout; version hóa và triển khai theo giai đoạn.
- **Tin feature flag thay cho authorization:** người dùng có thể truy cập tài nguyên trái phép; backend luôn kiểm tra quyền nghiệp vụ.

## 18. Quy trình triển khai thực tế

Khi xây dựng cấu hình cho Java serverless, có thể đi theo trình tự:

1. Liệt kê mọi key và phân loại deployment config, dynamic config hoặc secret.
2. Đặt tên có ý nghĩa, đơn vị rõ ràng và mô tả giá trị hợp lệ.
3. Quản lý biến môi trường theo revision/environment và tránh configuration drift.
4. Tạo typed configuration object, parse một lần và validate lúc init.
5. Chọn config service và schema version cho những key cần thay đổi khi runtime đang chạy.
6. Xác định TTL, max stale age, refresh timeout và fallback cho từng nhóm key.
7. Tạo immutable snapshot và thay tham chiếu nguyên tử khi refresh.
8. Chống refresh stampede bằng single-flight, jitter và backoff.
9. Đọc secret từ secret manager/provider với quyền tối thiểu và rotation rõ ràng.
10. Thiết kế feature flag không thay thế authorization và có owner/expiry.
11. Bảo đảm revision cũ và mới tương thích trong thời gian rollout.
12. Xử lý cache/credential hết hạn sau snapshot/restore nếu runtime hỗ trợ.
13. Theo dõi config version, refresh failure, stale use và audit trail.
14. Kiểm thử missing key, sai schema, timeout, rollback và nhiều instance cùng refresh.

## 19. Ghi nhớ

Biến môi trường phù hợp với cấu hình gắn với deployment hoặc revision; dynamic configuration phù hợp với những tham số cần thay đổi khi ứng dụng đang chạy; secret cần được quản lý riêng bằng cơ chế bảo mật chuyên dụng.

Trong Java serverless, hãy gom biến môi trường vào một cấu hình có kiểu dữ liệu và validate sớm. Dynamic config nên có schema/version, immutable snapshot và cache với TTL cùng giới hạn stale rõ ràng. Mỗi execution environment có cache riêng, vì vậy không giả định update ở một instance lập tức có hiệu lực trên toàn hệ thống.

Thiết kế refresh có timeout, single-flight, jitter và fallback theo mức độ quan trọng của từng key. Theo dõi version cấu hình, lỗi refresh và việc dùng stale data; kiểm thử rollout, rollback và snapshot/restore. Cách tổ chức này giúp thay đổi hành vi linh hoạt mà vẫn kiểm soát được tính nhất quán, bảo mật, độ trễ và chi phí.

