# Bảo vệ thông tin bí mật trong đối tượng cấu hình và thông báo lỗi

## 1. Vì sao cấu hình lắp ghép là một ranh giới bảo mật?

Trong **Dependency Injection (DI)**, lớp nghiệp vụ nhận các cộng tác viên qua constructor, còn **composition root** lựa chọn, tạo và lắp ghép chúng. Đây là một cách thực hiện **Inversion of Control (IoC)**: mã nghiệp vụ không phải tự đọc biến môi trường, tải secret, khởi tạo client hay chọn adapter hạ tầng.

Nhưng chuyển việc cấu hình ra composition root **không tự động làm thông tin bí mật an toàn**. Trong lúc xây dựng object graph, ứng dụng có thể xử lý API key, access token, mật khẩu database, client secret hoặc khóa ký. Những giá trị đó dễ đi vào:

- Chuỗi `toString()` của một đối tượng cấu hình;
- Thông báo exception khi parse URI, kết nối hoặc xác thực thất bại;
- Log khởi động in toàn bộ biến môi trường, thuộc tính cấu hình hoặc HTTP headers;
- Dữ liệu tracing, metric labels, audit events và thông báo lỗi trả cho người dùng;
- Heap dump, crash report, bản ghi debug hoặc bản sao đối tượng sống quá lâu.

**Mục tiêu bài học:** lắp ghép dependency theo cách vẫn giữ thông tin cấu hình đủ rõ để kiểm tra, nhưng không để bí mật vô tình xuất hiện trong log, exception hoặc object graph không cần biết chúng.

Sau bài này, bạn có thể:

1. Phân biệt cấu hình thông thường với **secret** và xác định nơi nào được phép tiếp xúc với secret.
2. Thiết kế đối tượng cấu hình không tự lộ secret qua `toString()`, phép nối chuỗi hoặc exception.
3. Xử lý lỗi cấu hình theo **mã lỗi ổn định và thông điệp an toàn**, không phản chiếu giá trị đầu vào có thể chứa secret.
4. Viết composition root Java thuần để tạo secret, inject adapter và quản lý vòng đời của secret.
5. Kiểm thử các đường gây lộ phổ biến và nhận ra giới hạn của `char[]`, redaction, DI container và cơ chế cấp phát tài nguyên.

## 2. Mô hình rủi ro: secret đi qua đâu?

Giả sử ứng dụng thanh toán cần `PaymentGateway`. Cấu hình gồm endpoint HTTPS, thời gian chờ và một API token.

```text
Nguồn cấu hình                         Composition root
(configuration/secret manager)               |
          |                                  | kiểm tra, chọn adapter
          | giá trị thường + secret          v
          +--------------------------> GatewaySettings
                                              |
                                              v
                                       PaymentGateway
                                              |
                                              v
                                        CheckoutService
                                              |
                                        gọi nghiệp vụ
```

Không phải mọi thành phần trong sơ đồ cần thấy cả ba giá trị:

- `CheckoutService` chỉ cần hợp đồng `PaymentGateway`; nó **không cần biết** token hoặc cách đọc token.
- Adapter `PaymentGateway` cần thông tin xác thực để gọi hệ thống ngoài; quyền tiếp xúc với token phải được giới hạn ở adapter hoặc một credential provider đáng tin cậy.
- Composition root cần biết *cách cấp* credential cho adapter và *ai sở hữu* vòng đời của nó.
- Logging, controller và công cụ giám sát chỉ cần thông tin vận hành an toàn: tình trạng cấu hình, mã lỗi, correlation ID và kết quả xử lý, **không cần giá trị token**.

Một nguyên tắc hữu ích là **giảm số bản sao và số nơi biết secret**. Secret xuất hiện trong ít object, ít phương thức và ít output hơn thì bề mặt lộ lọt thường dễ kiểm soát hơn.

### 2.1. Những loại dữ liệu cần phân biệt

| Dữ liệu | Có phải secret? | Cách xử lý |
| --- | --- | --- |
| Timeout, số lần retry, tên feature flag | Thường không | Có thể ghi log khi hữu ích, nhưng vẫn xem xét metadata nhạy cảm của hệ thống. |
| Tên biến môi trường `PAYMENT_API_TOKEN` | Tên khóa, không phải giá trị bí mật | Có thể dùng trong lỗi `CONFIG_MISSING`; không in giá trị của khóa. |
| Giá trị API token, password, private key | Có | Không đưa vào log, `toString`, exception, URL hoặc response. |
| Endpoint nội bộ, tên host, tenant ID, request payload | Có thể nhạy cảm tùy hệ thống | Chỉ log những trường đã được xét duyệt; không mặc định tất cả metadata đều công khai. |
| Session cookie, Authorization header | Có | Tránh log nguyên header hoặc request dump; hạn chế nơi xử lý. |

**Không nên định nghĩa bảo mật chỉ bằng tên field.** Một chuỗi tên `url` có thể chứa `?token=...`, một message lỗi có thể nhúng mật khẩu, và một giá trị `headers` có thể chứa thông tin xác thực dù field không mang tên `secret`.

## 3. Các lỗi thiết kế dễ làm lộ secret

### 3.1. Tự động tạo `toString()` cho mọi trường

Ví dụ dễ mắc:

```java
// Không nên dùng kiểu record này để lưu secret dạng String.
record UnsafeGatewayConfig(String endpoint, String apiToken) {}

// toString() sinh tự động sẽ chứa giá trị apiToken.
System.out.println(config);
```

Tương tự, một công cụ sinh `toString`, logger phản chiếu (reflection), thư viện serialize hoặc annotation tạo getter cho mọi field có thể vô tình đưa credential ra ngoài. Với object chứa secret, cần **chủ động thiết kế API và biểu diễn để log**. Việc đặt field là `private` không ngăn những phương thức của chính lớp hoặc công cụ được cấp quyền truy xuất làm lộ dữ liệu.

### 3.2. Dùng giá trị đầu vào trong thông báo lỗi

```java
// Sai: nếu rawUrl chứa token, thông báo lỗi cũng chứa token.
throw new IllegalArgumentException("Endpoint sai: " + rawUrl);
```

Nguy cơ không chỉ ở thông điệp tự viết. Một thư viện parse URI hoặc gọi HTTP cũng có thể đặt **input gốc** trong `getMessage()`, `toString()` hoặc nested cause. Gọi `logger.error("Startup failed", exception)` có thể đưa cả cause chain và request URL vào log.

**Giải pháp:** ở ranh giới cấu hình, ánh xạ những lỗi có thể chứa dữ liệu nhạy cảm sang **mã lỗi và mô tả an toàn**, ví dụ `INVALID_PAYMENT_ENDPOINT`. Không tự động nối raw input hoặc cause chưa được xem xét vào thông điệp gửi ra ngoài.

### 3.3. Để secret trong URL hoặc command line

```text
https://payments.example.invalid/charge?api_key=SECRET_VALUE
```

URL có thể xuất hiện trong access log, proxy log, hệ thống tracing, lịch sử trình duyệt hoặc exception. Với API hỗ trợ, hãy đặt credential vào cơ chế xác thực được thiết kế riêng, thường là header theo chuẩn của dịch vụ, qua kênh TLS và client đã được cấu hình an toàn. Không đưa secret vào query string hoặc đường dẫn nếu có lựa chọn an toàn hơn.

Tương tự, truyền secret qua tham số dòng lệnh có thể làm nó xuất hiện trong lịch sử shell hoặc danh sách tiến trình. Sử dụng secret manager, cơ chế cấp phát identity của môi trường chạy hoặc kênh cấu hình có kiểm soát quyền truy cập khi có thể.

### 3.4. Dùng mặc định bí mật bên trong constructor

```java
// Sai: dependency bị tạo ngầm với credential hard-code.
PaymentGateway() {
    this.client = new RemoteClient("hard-coded-secret");
}
```

Đoạn trên minh họa sai lầm, các lớp không phải API thực. Hard-code credential, kể cả “tạm thời”, dễ bị commit vào repository hoặc đóng gói trong artifact. Constructor của nghiệp vụ cũng không nên tự gọi `System.getenv` để tìm credential: dependency bị che giấu, test khó cô lập và lớp nghiệp vụ biết về môi trường triển khai.

## 4. Thiết kế đối tượng cấu hình an toàn hơn

Một cấu hình thanh toán có thể tách thành:

- **Cấu hình không bí mật**: endpoint, timeout, chế độ hoạt động. Các trường này vẫn cần xác thực, và không phải trường nào cũng nên xuất hiện trong log.
- **Đối tượng chứa secret**: chỉ cung cấp giá trị cho adapter thật sự cần nó, không đưa ra các phương thức in giá trị tùy tiện.
- **Service nghiệp vụ**: chỉ nhận `PaymentGateway`, không nhận `GatewaySettings` hoặc `SecretChars` nếu không cần.

Bài này dùng một wrapper `SecretChars` quanh `char[]`. Nó hỗ trợ sao chép phòng vệ, một biểu diễn `toString()` không lộ giá trị và xóa mảng đang giữ khi đóng. **Đây là giảm rủi ro chứ không phải bảo đảm xóa sạch bí mật khỏi mọi vùng nhớ Java.**

### 4.1. Vì sao `char[]` không phải giải pháp tuyệt đối?

`String` bất biến: sau khi tạo, code không có API đáng tin cậy để ghi đè bộ nhớ chứa nội dung của nó. `char[]` cho phép ứng dụng ghi đè các phần tử bằng `Arrays.fill`, nhưng:

- Nguồn cấu hình như `System.getenv` thường trả về `String` đã tồn tại trong bộ nhớ.
- Khi chuyển `char[]` sang `String`, encode thành byte, đưa vào thư viện HTTP hoặc tạo bản sao, dữ liệu có thể tồn tại ở những nơi khác.
- JVM/GC, runtime, thư viện và heap dump có thể giữ bản sao hoặc dấu vết; không thể hứa “xóa chắc chắn mọi dấu vết”.
- `char[]` mutable tạo thêm yêu cầu về ownership, thread safety và thời điểm đóng.

Vì vậy, hãy ưu tiên **giảm thời gian tồn tại và số bản sao**, tránh tạo `String` không cần thiết, không log, dùng giao thức bảo mật và quản lý quyền truy cập. Xóa `char[]` là một biện pháp bổ sung có giới hạn.

## 5. Ví dụ Java thuần: cấu hình redacted và injection tường minh

Ví dụ sau chạy mà không cần DI container hoặc network. Nó dùng **token giả tổng hợp, không phải credential thật** để minh họa việc truyền qua adapter, xóa mảng tạm và tránh đưa secret vào output.

Lưu tất cả vào `SafeConfigurationDemo.java`:

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Arrays;
import java.util.Objects;

// Wrapper tối giản cho secret do composition root sở hữu.
// Không dùng như một cơ chế bảo vệ bộ nhớ tuyệt đối.
final class SecretChars implements AutoCloseable {
    private char[] value;

    SecretChars(char[] source) {
        Objects.requireNonNull(source, "source");
        if (source.length == 0) {
            throw new IllegalArgumentException(
                    "Credential không được rỗng");
        }
        // Không giữ tham chiếu mảng mutable của caller.
        this.value = source.clone();
    }

    synchronized char[] copy() {
        if (value == null) {
            throw new IllegalStateException(
                    "Credential không còn hiệu lực");
        }
        return value.clone();
    }

    @Override
    public synchronized void close() {
        if (value != null) {
            Arrays.fill(value, '\0');
            value = null;
        }
    }

    @Override
    public String toString() {
        return "[REDACTED]";
    }
}

// Không dùng record tự sinh toString có thể lộ dữ liệu.
final class GatewaySettings {
    private final URI endpoint;
    private final int timeoutMillis;
    private final SecretChars credential;

    private GatewaySettings(URI endpoint, int timeoutMillis,
                            SecretChars credential) {
        this.endpoint = endpoint;
        this.timeoutMillis = timeoutMillis;
        this.credential = credential;
    }

    static GatewaySettings create(String rawEndpoint, int timeoutMillis,
                                  SecretChars credential) {
        Objects.requireNonNull(credential, "credential");

        if (rawEndpoint == null || rawEndpoint.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "INVALID_PAYMENT_ENDPOINT");
        }

        URI endpoint;
        try {
            endpoint = new URI(rawEndpoint);
        } catch (URISyntaxException invalid) {
            // Không kèm rawEndpoint hoặc invalid làm cause:
            // ngoại lệ của thư viện có thể chứa input gốc.
            throw new IllegalArgumentException(
                    "INVALID_PAYMENT_ENDPOINT");
        }

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null
                || endpoint.getRawUserInfo() != null
                || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "INVALID_PAYMENT_ENDPOINT");
        }
        if (timeoutMillis < 100 || timeoutMillis > 10_000) {
            throw new IllegalArgumentException(
                    "INVALID_PAYMENT_TIMEOUT");
        }

        return new GatewaySettings(
                endpoint, timeoutMillis, credential);
    }

    // Chỉ đưa các giá trị cần thiết tới adapter tin cậy.
    URI endpoint() {
        return endpoint;
    }

    int timeoutMillis() {
        return timeoutMillis;
    }

    SecretChars credential() {
        return credential;
    }

    @Override
    public String toString() {
        // Không in nguyên endpoint: đường dẫn đôi khi cũng nhạy cảm.
        return "GatewaySettings{endpoint=[CONFIGURED], timeoutMs="
                + timeoutMillis + ", credential=[REDACTED]}";
    }
}

// Hợp đồng nghiệp vụ: không cho phép service thấy credential.
interface PaymentGateway {
    void authorize(String orderRef, long amountVnd);
}

// Adapter DEMO: không kết nối mạng, không thực hiện thanh toán.
// Adapter thật phải dùng giao thức TLS và cơ chế xác thực phù hợp.
final class DemoPaymentGateway implements PaymentGateway {
    private final GatewaySettings settings;

    DemoPaymentGateway(GatewaySettings settings) {
        this.settings = Objects.requireNonNull(settings, "settings");
    }

    @Override
    public void authorize(String orderRef, long amountVnd) {
        if (orderRef == null || orderRef.trim().isEmpty()
                || amountVnd <= 0) {
            throw new IllegalArgumentException(
                    "INVALID_PAYMENT_REQUEST");
        }

        char[] temporaryCopy = settings.credential().copy();
        try {
            // Mô phỏng bước adapter nhận credential để xác thực.
            // KHÔNG log temporaryCopy, không lưu nó trong field.
            if (temporaryCopy.length == 0) {
                throw new IllegalStateException(
                        "PAYMENT_CREDENTIAL_UNAVAILABLE");
            }
            System.out.println("DEMO_AUTHORIZATION_OK");
        } finally {
            Arrays.fill(temporaryCopy, '\0');
        }
    }
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    void pay(String orderRef, long amountVnd) {
        gateway.authorize(orderRef, amountVnd);
    }
}

public class SafeConfigurationDemo {
    public static void main(String[] args) {
        // Mảng toàn ký tự X chỉ là dữ liệu giả để demo;
        // không ghi credential thật vào source code.
        char[] dummyInput = new char[12];
        Arrays.fill(dummyInput, 'X');

        try (SecretChars credential = new SecretChars(dummyInput)) {
            GatewaySettings settings = GatewaySettings.create(
                    "https://payments.example.invalid/v1",
                    1_500,
                    credential);

            // Composition root: tạo adapter và inject qua constructor.
            PaymentGateway gateway = new DemoPaymentGateway(settings);
            CheckoutService checkout = new CheckoutService(gateway);

            System.out.println(settings);
            checkout.pay("ORDER-DEMO", 120_000);
        } finally {
            // Caller cũng dọn bản sao đầu vào do mình sở hữu.
            Arrays.fill(dummyInput, '\0');
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SafeConfigurationDemo.java
java SafeConfigurationDemo
```

Đầu ra dự kiến:

```text
GatewaySettings{endpoint=[CONFIGURED], timeoutMs=1500, credential=[REDACTED]}
DEMO_AUTHORIZATION_OK
```

### 5.1. Composition root bảo vệ secret như thế nào?

`SafeConfigurationDemo.main` tạo token giả, tạo `SecretChars` rồi truyền vào `GatewaySettings` và `DemoPaymentGateway`. `CheckoutService` chỉ nhận `PaymentGateway`: lớp nghiệp vụ không thể vô tình gọi `System.getenv("PAYMENT_API_TOKEN")` hoặc ghi token ra log qua một field của chính nó.

`GatewaySettings.toString()` cố ý chỉ in dấu hiệu đã cấu hình, timeout và placeholder `[REDACTED]`. Nó **không in URL đầy đủ** và không gọi `credential.copy()`. Phương thức `GatewaySettings.create` kiểm tra endpoint, timeout, từ chối URI có userinfo/query/fragment và trả mã lỗi cố định khi URI không hợp lệ; lỗi parser không được giữ làm cause để tránh phản chiếu input.

`DemoPaymentGateway` lấy **bản sao tạm** của token khi cần và ghi đè bản sao ở `finally`. Composition root đóng `SecretChars` sau khi hết phiên xử lý demo. Một adapter thực tế sẽ cần gửi token đến dịch vụ được ủy quyền theo giao thức phù hợp; **không nên sao chép phần in console của adapter demo thành một triển khai thanh toán thật**.

**Ranh giới quyền sở hữu:** trong ví dụ, `GatewaySettings` và `DemoPaymentGateway` *mượn* `SecretChars`; composition root sở hữu và đóng nó. Chúng không tự đóng secret vì việc đóng quá sớm có thể ảnh hưởng các thành phần cùng dùng. Ở ứng dụng có request đồng thời, root phải **ngừng tiếp nhận việc và xử lý xong các yêu cầu còn lại trước khi đóng credential**. Các cờ và phương thức trong ví dụ không phải một cơ chế graceful shutdown đồng thời.

### 5.2. Giới hạn của ví dụ bảo mật

- `char[]` không chứng minh token không còn trong heap, vì runtime và thư viện có thể tạo bản sao.
- `SecretChars.toString()` an toàn không bảo đảm mọi serializer, debugger, logger hoặc memory dump đều an toàn.
- Việc từ chối query/fragment/userinfo giảm một nhóm nguy cơ, nhưng **không phát hiện được mọi secret bị chèn vào đường dẫn URL hoặc metadata khác**. Endpoint cần được lấy từ cấu hình đáng tin cậy và kiểm soát đích kết nối phù hợp.
- Adapter demo không gọi HTTP thực; production cần xác thực endpoint, TLS, timeout, giới hạn quyền truy cập, xử lý response và retry/idempotency theo contract.
- Không nên dùng `SecretChars` như một “kho secret” mà mọi thành phần đều có quyền `copy()`. Trong production, thu hẹp quyền truy cập vào lớp adapter được phép sử dụng credential.

## 6. Nạp bí mật từ môi trường mà không log giá trị

Ví dụ ở trên sử dụng token giả để luôn chạy được. Trong ứng dụng thật, composition root có thể sử dụng secret manager hoặc cơ chế cấp phát credential của nền tảng. Trường hợp đơn giản, có thể đọc biến môi trường:

```java
// Minh họa hàm bootstrap. SecretChars đã được định nghĩa ở mục 5.
static SecretChars loadCredentialFromEnvironment() {
    String raw = System.getenv("PAYMENT_API_TOKEN");
    if (raw == null || raw.isEmpty()) {
        // Chỉ thông báo TÊN khóa thiếu, không ghi giá trị.
        throw new IllegalStateException(
                "CONFIG_MISSING: PAYMENT_API_TOKEN");
    }

    char[] temporary = raw.toCharArray();
    try {
        return new SecretChars(temporary);
    } finally {
        Arrays.fill(temporary, '\0');
    }
}
```

Khi sử dụng hàm này, root chịu trách nhiệm đóng `SecretChars` vào đúng thời điểm. **Không** nên thêm `System.out.println(raw)`, `logger.debug("env={}", System.getenv())` hoặc nối `raw` vào exception.

**Lưu ý:** `System.getenv` trả `String`; xóa `temporary` **không xóa được** chuỗi `raw` hoặc giá trị trong môi trường tiến trình. Biến môi trường cũng có thể bị lộ qua cơ chế vận hành, crash dump hoặc cấu hình cấp quyền sai. Với hệ thống nhạy cảm, ưu tiên secret manager/identity-based access, phân quyền tối thiểu và kế hoạch rotation; môi trường vẫn là một đường cấp phát có đánh đổi, không phải biện pháp bảo mật tuyệt đối.

### 6.1. Không tạo secret mặc định khi cấu hình thiếu

Không nên sử dụng mẫu:

```java
// Anti-pattern: che thiếu cấu hình bằng một giá trị cố định.
String token = System.getenv("PAYMENT_API_TOKEN");
if (token == null) {
    token = "demo-token";
}
```

Nếu token là dependency bắt buộc ở môi trường production, thiếu token phải là **lỗi cấu hình rõ ràng trước khi nhận request**. Khi thực sự có chế độ demo, composition root nên chọn adapter demo **tường minh** theo cấu hình môi trường đã xác thực, thay vì ngầm chuyển từ thanh toán thật sang chế độ giả.

### 6.2. Chú ý cả thời điểm lỗi với factory/provider

Nếu composition root truyền `CredentialProvider` và chỉ nạp token ở lần request đầu, lỗi secret thiếu quyền hoặc không tồn tại sẽ được bộc lộ **khi sử dụng** thay vì lúc khởi động. Lazy initialization không làm cấu hình an toàn hơn: nó chỉ thay đổi thời điểm vấn đề xuất hiện.

Với dependency cốt lõi cần có để ứng dụng hoạt động đúng, nên kiểm chứng credential/quyền truy cập trước khi công bố READY nếu chính sách vận hành yêu cầu. Với credential có thể xoay vòng, một provider là abstraction phù hợp nếu nó kiểm soát hạn dùng, refresh và việc cấp phát bản sao an toàn; đừng để mọi service trực tiếp gọi secret manager.

## 7. Thiết kế thông báo lỗi theo nguyên tắc không phản chiếu secret

Phải phân biệt **lỗi dành cho người dùng/API consumer** và **chi tiết chẩn đoán dành cho vận hành nội bộ**. Cả hai vẫn cần tránh chứa secret, kể cả trong cause chain hoặc metadata không được kiểm soát.

### 7.1. Từ input chưa tin cậy sang mã lỗi an toàn

Một cách thực hiện ở ranh giới cấu hình:

```java
// Không in rawEndpoint; không giữ ngoại lệ parser chưa rà soát
// làm cause bởi message của nó có thể kèm input chứa secret.
try {
    URI endpoint = new URI(rawEndpoint);
    // Tiếp tục kiểm tra scheme, host, userinfo, query...
} catch (URISyntaxException badInput) {
    throw new IllegalArgumentException(
            "INVALID_PAYMENT_ENDPOINT");
}
```

Giữ lại mã lỗi tường minh giúp người vận hành biết **loại cấu hình nào sai**, mà không cần xem credential hoặc URL nguy hiểm. Có thể gắn thêm một correlation ID và bước hướng dẫn xử lý không chứa dữ liệu nhạy cảm.

Trong một hệ thống lớn, không nên mặc định loại bỏ toàn bộ cause của mọi exception. Thay vào đó, **phân loại tại ranh giới**: chỉ chuyển tiếp những exception và metadata đã biết an toàn; với lỗi từ thư viện có thể chứa input bí mật, ánh xạ sang lỗi mới an toàn và chỉ đưa thông tin đã kiểm duyệt vào telemetry. Tính chẩn đoán phải được cân bằng với ngăn lộ lọt.

### 7.2. Những ví dụ thông điệp nên và không nên xuất hiện

| Ngữ cảnh | Không an toàn | An toàn hơn |
| --- | --- | --- |
| Thiếu token | `PAYMENT_API_TOKEN=<giá trị>` hoặc dump toàn bộ env | `CONFIG_MISSING: PAYMENT_API_TOKEN` |
| URI không hợp lệ | `Bad URL: https://...?token=...` | `INVALID_PAYMENT_ENDPOINT` |
| Lỗi xác thực HTTP | Log toàn bộ Authorization header | `PAYMENT_AUTH_FAILED`, mã trạng thái được phép ghi, request correlation ID |
| Khởi động lỗi | `logger.error("Config: " + config)` khi `toString()` in secret | `CONFIG_STARTUP_FAILED` kèm trường an toàn được chọn lọc |
| Phản hồi API | Trả `exception.getMessage()` nguyên văn | Mã lỗi công khai, thông điệp chung và ID tra cứu nội bộ |
| Tracing | Lưu URL nguyên chuỗi và mọi HTTP header | Chỉ lưu scheme/tên hoạt động hoặc tag đã loại bí mật theo chính sách |

**Không đặt secret vào metric labels, span attributes, MDC, query parameters của tracing hoặc audit payload.** Chúng cũng là nơi dữ liệu được lưu trữ và truy cập, dù không được gọi là “log”.

### 7.3. Redaction theo allowlist tốt hơn sửa mọi chuỗi sau khi lộ

Một filter regex cuối đường log có thể bỏ sót token ở định dạng mới, token trong nested exception, URL encoding hoặc metadata được serialize khác cách. Thay vì chỉ dựa vào “thay mọi chuỗi có chữ password”, nên:

1. Chỉ log **các trường được phép** đã định nghĩa trước như `errorCode`, `operation`, `correlationId`, `durationMs`.
2. Không chuyển trực tiếp object chứa secret vào logger/serializer.
3. Tách message công khai khỏi thông tin chẩn đoán nội bộ đã được rà soát.
4. Bổ sung redaction ở hạ tầng log làm **lớp phòng vệ thứ hai**, không coi nó là biện pháp duy nhất.
5. Kiểm thử cả thành công và lỗi, bao gồm nested exceptions, invalid URLs và failure của client ngoài.

Nếu buộc phải log trạng thái cấu hình, hãy in `credentialConfigured=true` hoặc mã phiên bản cấu hình an toàn, không in credential hay bản băm tự tạo của nó. Hash của token có thể vẫn là dữ liệu nhạy cảm hoặc làm lộ khả năng liên kết, nên không nên ghi chỉ vì “không phải plaintext”.

## 8. Kiểm thử bằng Java thuần: không lộ secret trong output và exception

Ta kiểm tra các đường dễ lộ ngay cả khi **không gọi dịch vụ thanh toán thật**. Tạo file `SafeConfigurationTest.java` cạnh `SafeConfigurationDemo.java`:

```java
import java.util.Arrays;

public class SafeConfigurationTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // Chỉ là marker kiểm thử, tuyệt đối không dùng token thật.
        char[] marker = new char[12];
        Arrays.fill(marker, 'Z');
        String markerText = new String(marker);
        SecretChars secret = new SecretChars(marker);

        // Xóa input gốc không được làm hỏng bản sao đã inject.
        Arrays.fill(marker, '\0');
        char[] copied = secret.copy();
        check(markerText.equals(new String(copied)),
                "Không copy phòng vệ dữ liệu secret");
        Arrays.fill(copied, '\0');

        GatewaySettings settings = GatewaySettings.create(
                "https://payments.example.invalid/v1",
                2_000,
                secret);

        check(!secret.toString().contains(markerText),
                "SecretChars.toString lộ credential");
        check(!settings.toString().contains(markerText),
                "GatewaySettings.toString lộ credential");
        check(!settings.toString().contains(
                "payments.example.invalid/v1"),
                "GatewaySettings.toString in endpoint đầy đủ");

        // URL chứa secret trong query phải bị từ chối;
        // thông báo và cause không được phản chiếu input.
        boolean rejectedQuery = false;
        try {
            GatewaySettings.create(
                    "https://payments.example.invalid/"
                    + "?api_token=" + markerText,
                    2_000,
                    secret);
        } catch (IllegalArgumentException expected) {
            rejectedQuery = true;
            check(!expected.getMessage().contains(markerText),
                    "Lỗi validation phản chiếu token");
            check(expected.getCause() == null,
                    "Cause chưa rà soát được giữ lại");
        }
        check(rejectedQuery, "Không từ chối secret trong query");

        // Lỗi parser cũng phải được ánh xạ sang thông báo an toàn.
        boolean rejectedMalformed = false;
        try {
            GatewaySettings.create(
                    "https://bad host.invalid/?api_token=" + markerText,
                    2_000,
                    secret);
        } catch (IllegalArgumentException expected) {
            rejectedMalformed = true;
            check("INVALID_PAYMENT_ENDPOINT".equals(
                    expected.getMessage()),
                    "Lỗi parser không được chuẩn hóa");
            check(expected.getCause() == null,
                    "Lỗi parser còn đính kèm cause");
        }
        check(rejectedMalformed, "Không từ chối URI sai cú pháp");

        PaymentGateway gateway = new DemoPaymentGateway(settings);
        CheckoutService checkout = new CheckoutService(gateway);
        checkout.pay("TEST-ORDER", 10_000);

        secret.close();
        secret.close(); // Theo hợp đồng ví dụ, đóng lặp không gây lỗi.

        boolean rejectedAfterClose = false;
        try {
            secret.copy();
        } catch (IllegalStateException expected) {
            rejectedAfterClose = true;
            check(!expected.getMessage().contains(markerText),
                    "Lỗi dùng sau close chứa token");
        }
        check(rejectedAfterClose, "Đã đóng vẫn đọc được credential");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac SafeConfigurationDemo.java SafeConfigurationTest.java
java SafeConfigurationTest
```

Kết quả mong đợi:

```text
DEMO_AUTHORIZATION_OK
PASS
```

Bài test xác minh **copy phòng vệ**, biểu diễn `toString()` không lộ marker, URI có query không được chấp nhận, lỗi parse không kèm input/cause chưa kiểm duyệt và secret không còn được cấp bản sao sau `close()`.

**Giới hạn cần hiểu:** test không chứng minh token đã được xóa khỏi mọi vùng nhớ JVM; `markerText` được tạo thành `String` chỉ để kiểm thử. Bài test cũng chưa bắt toàn bộ log của các thư viện thật, serialized JSON, distributed tracing hay heap dump. Ứng dụng production cần kiểm thử tích hợp, kiểm thử quan sát dữ liệu log và cấu hình logging thực tế.

## 9. Scope, rotation và quyền sở hữu secret trong object graph

Secret cũng có **vòng đời**, không chỉ là một `String` trong file cấu hình.

### 9.1. Khi token sống theo ứng dụng

Nếu một API credential được cấp cho cả tiến trình, composition root có thể tạo credential và truyền vào adapter application-scoped. Root phải:

- Bảo đảm không cho nhận công việc trước khi credential bắt buộc đã có và hợp lệ theo chính sách.
- Không đóng credential trước khi các request đang dùng nó kết thúc.
- Tránh để controller, domain service hoặc serializer truy cập trực tiếp vào credential.
- Chỉ có một chủ sở hữu trách nhiệm đóng tài nguyên nếu cùng instance được chia sẻ.

Đừng để mỗi `CheckoutService` tự gọi `secret.close()`; làm vậy có thể vô hiệu hóa adapter dùng chung ở request khác.

### 9.2. Khi token phải xoay vòng

Nếu credential có thời hạn, việc inject một giá trị bất biến vào adapter và giữ mãi có thể khiến adapter dùng token hết hạn. Một lựa chọn là inject **`CredentialProvider`** vào adapter:

```java
// Hợp đồng minh họa, chưa có implementation cụ thể.
interface CredentialProvider {
    // Caller phải được quy định là chủ sở hữu bản sao trả về.
    char[] acquireCredentialCopy();
}
```

Provider có thể lấy giá trị hiện hành từ secret manager hoặc cache có TTL, nhưng phải định nghĩa rõ:

- Token hết hạn hoặc refresh thất bại thì báo lỗi theo chính sách nào?
- Các request đồng thời nhìn thấy phiên bản token nào?
- Ai xóa bản sao tạm và khi nào?
- Khi shutdown, có request nào còn mượn token không?
- Có được log token version hay metadata nào mà không làm lộ thông tin nhạy cảm?

**Không dùng một singleton giữ trực tiếp secret riêng của một user/request.** Token theo request hoặc phiên phải được cấp theo đúng danh tính và phạm vi, không được ghi nhầm vào registry dùng chung cho mọi người dùng.

### 9.3. Đóng tài nguyên không đồng nghĩa thu hồi credential ngoài hệ thống

Gọi `SecretChars.close()` chỉ cố gắng ghi đè mảng mà đối tượng này đang sở hữu. Nó **không thu hồi API key trên server**, không kết thúc session đã phát hành, không xóa secret manager entry và không bảo đảm xóa mọi bản sao trong process. Revocation/rotation là hành động riêng với dịch vụ cấp credential.

## 10. Khi dùng DI container, cần kiểm tra thêm gì?

DI container có thể đọc cấu hình, inject secrets vào constructor/field, khởi tạo client và gọi lifecycle hooks. Những tiện ích đó không loại bỏ nguy cơ lộ dữ liệu:

- Một container có thể hiển thị thuộc tính cấu hình, thông tin bean hoặc lỗi binding trong log khởi động; cần kiểm soát và kiểm thử cơ chế masking theo framework thực tế.
- `record`, serializer, `toString()` tự sinh và công cụ debug vẫn có thể làm lộ secret nếu kiểu cấu hình cung cấp mọi field.
- Proxy/provider và lazy initialization có thể làm lỗi secret thiếu hoặc expired chỉ xuất hiện ở request đầu, thay vì lúc bootstrap.
- Bean singleton giữ request-scoped credential hoặc user token có thể gây rò rỉ dữ liệu giữa người dùng.
- Secret do ứng dụng tự cấp phát có thể **không** thuộc ownership của container để được tự đóng; cần đọc đúng contract lifecycle.
- Annotation đánh dấu “sensitive” hoặc masking ở UI cấu hình không bảo đảm mọi thư viện HTTP, logging và tracing đều tôn trọng annotation đó.

Hãy giữ bất biến kiến trúc từ Java thuần: **business service nhận interface**, adapter được cấp credential theo scope, composition root chịu trách nhiệm cấu hình và lifecycle, còn logging chỉ xuất những trường đã cho phép.

## 11. Checklist rà soát trước khi triển khai

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Secret có bị commit, hard-code hoặc đưa qua CLI argument không? | Rà soát cách cấp phát và cơ chế quản lý secret; kiểm tra quy trình build/deploy. |
| `toString()`, record, Lombok hoặc serializer có lộ field nhạy cảm? | Test chuỗi biểu diễn và schema serialization với marker giả. |
| Lỗi parse URL/config có thể chứa raw input hoặc nested cause? | Truyền dữ liệu giả chứa marker vào đường lỗi; kiểm tra message và cause khi đi qua logger. |
| Logger có dump toàn bộ config, env, HTTP request/headers không? | Kiểm tra cấu hình log/trace và integration test. |
| API error trả `exception.getMessage()` chưa kiểm soát? | Kiểm tra exception mapping, HTTP response và correlation ID. |
| Các lớp nghiệp vụ có đọc secret trực tiếp? | Kiểm tra constructor dependency: nên nhận interface nghiệp vụ, không nhận token nếu không cần. |
| Secret thuộc scope nào, ai được phép copy và ai đóng? | Viết rõ ownership, thời hạn, chính sách concurrency và cleanup. |
| Secret hết hạn/rotation hoặc startup thiếu credential xử lý ra sao? | Test fail-fast/readiness, refresh, retry, dùng sau close và shutdown. |
| Có thể lộ trong telemetry, dump, cache, retry message hoặc proxy không? | Rà soát đường đi end-to-end và quyền truy cập vào dữ liệu vận hành. |
| Token có quyền tối thiểu và cơ chế thu hồi không? | Kiểm tra quyền cấp, TTL, audit và quy trình rotation/revocation. |

## 12. Bài tập thực hành

**Bối cảnh:** một ứng dụng gửi thông báo dùng `NotificationService`, `NotificationGateway` và `GatewayConfig`. Cấu hình gồm `endpoint`, `timeout`, `apiKey` và một optional feature flag. Ứng dụng chạy trên nhiều instance, có request đồng thời và key được xoay vòng định kỳ.

Hãy thực hiện:

1. **Phân loại dữ liệu:** trường nào là secret, trường nào là metadata có thể nhạy cảm, và vì sao không nên mặc định in cả `GatewayConfig`?
2. **Tách trách nhiệm:** viết constructor `NotificationService(NotificationGateway gateway)`. Chỉ rõ nơi đọc secret và nơi được phép biết adapter cụ thể.
3. **Xác thực cấu hình:** thiết kế hàm kiểm tra endpoint HTTPS, timeout hợp lệ và credential bắt buộc mà không bao giờ trả raw input trong exception.
4. **Thiết kế lỗi:** đề xuất các mã `CONFIG_MISSING`, `INVALID_ENDPOINT`, `GATEWAY_AUTH_FAILED` và nội dung phản hồi API an toàn; mô tả metadata nào được log.
5. **Viết test với marker giả:** kiểm tra `toString()`, nested cause, lỗi parser, serialization và response mapper không làm lộ marker.
6. **Quản lý vòng đời:** mô tả khi nào root tạo, inject và đóng credential; phải làm gì để request đang gửi không bị đóng token quá sớm?
7. **Rotation:** nếu gateway dùng token có hạn, hãy đề xuất interface provider và cách đồng bộ hóa việc cấp bản sao; nêu giới hạn của `char[]` trong JVM.
8. **Kiểm tra DI container:** khi chuyển wiring sang framework, bạn sẽ xác minh masking, binding, scope và destroy hook ra sao?

**Gợi ý đối chiếu:** `NotificationService` chỉ nên nhận `NotificationGateway`. Config và credential được tập trung tại bootstrap hoặc provider đáng tin cậy. Lỗi dành cho vận hành/người dùng nên có mã ổn định và dữ liệu đã cho phép, không phản chiếu token hoặc URL chưa kiểm duyệt. Kiểm thử bằng marker giả xác minh các đường biểu diễn, exception và output; còn secret manager, HTTP client và logging thực tế cần kiểm thử tích hợp và quản trị bảo mật riêng.

**Điểm cần nhớ:** DI làm rõ **ai tạo và ai sử dụng dependency**, nhưng không tự bảo vệ secret. Trong composition configuration, hãy hạn chế nơi biết credential, tránh để `toString()`, logger, URI hoặc exception làm lộ giá trị, kiểm tra cấu hình fail-fast bằng thông điệp an toàn và quản lý vòng đời/rotation rõ ràng. Bắt đầu bằng Java thuần và các bài test dùng marker giả, rồi xác minh thêm các cơ chế đặc thù khi chuyển sang DI container.
