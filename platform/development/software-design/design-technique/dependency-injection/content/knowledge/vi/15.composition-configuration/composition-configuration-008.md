# Xác minh cấu hình trước khi sử dụng tài nguyên bên ngoài

Trong **Dependency Injection (DI)**, composition root quyết định tạo và kết nối các dependency của ứng dụng. Một sai lầm dễ mắc là **mở kết nối, tạo HTTP client, ghi file hoặc khởi động worker trước khi biết cấu hình có hợp lệ hay không**. Khi đó một giá trị cấu hình sai đơn giản có thể gây ra hàng loạt tác dụng phụ: khởi tạo dở dang, tài nguyên chưa được đóng, request bắt đầu xử lý với tham số sai và thông báo lỗi khó truy vết.

Bài học thuộc phần **Cấu hình lắp ghép** của module **Dependency Injection**. Mục tiêu là tách việc **đọc và xác minh cấu hình** khỏi việc **sử dụng tài nguyên bên ngoài**, thực hành Java 17 thuần với constructor injection và composition root, kiểm thử không cần mạng hoặc DI container, rồi xem xét cách áp dụng khi hệ thống mở rộng sang container có lifecycle riêng.

Nguyên tắc xuyên suốt là:

> **Kiểm tra được điều gì mà chưa cần I/O thì kiểm tra trước khi tạo tài nguyên; điều gì phải kiểm tra qua I/O thì thực hiện có kiểm soát, có timeout và cleanup.**

## 1. Vấn đề: kết nối trước, kiểm tra sau

Giả sử ứng dụng đồng bộ dữ liệu tới một dịch vụ HTTPS. Nó nhận ba giá trị cấu hình:

- `endpoint`: địa chỉ dịch vụ đích.
- `timeoutMs`: thời gian chờ cho một thao tác.
- `apiKey`: thông tin xác thực được cung cấp từ nơi cấu hình bảo mật.

Đoạn mã dưới đây minh họa cách lắp ghép dễ gây sự cố:

~~~java
// Mã minh họa chống mẫu; RemoteClient và Config là kiểu giả định.
RemoteClient client = new RemoteClient(rawEndpoint, rawApiKey);
int timeoutMs = Integer.parseInt(rawTimeoutMs);

if (timeoutMs <= 0) {
    throw new IllegalArgumentException("Invalid timeout");
}
client.setTimeout(timeoutMs);
~~~

Có ba vấn đề:

1. Constructor của client **có thể** mở tài nguyên hoặc chuẩn bị kết nối trước khi việc kiểm tra timeout được hoàn tất.
2. Nếu `Integer.parseInt(...)` thất bại, mã không có đường dọn dẹp client rõ ràng.
3. Logic lắp ghép đang trộn **cú pháp cấu hình**, **quy tắc nghiệp vụ** và **tác dụng phụ hạ tầng**, khiến test khó xác minh rằng cấu hình sai không gây I/O.

Ngay cả khi implementation hiện tại chỉ ghi nhớ tham số và chưa kết nối, **thiết kế vẫn không thể hiện ranh giới xác minh trước khi dùng tài nguyên**. Khi implementation thay đổi, thứ tự thực thi có thể trở nên nguy hiểm.

Mục tiêu là sắp xếp như sau:

~~~mermaid
flowchart TD
    Raw["Đầu vào cấu hình thô"] --> Parse["Parse, kiểm tra cấu trúc"]
    Parse --> Validate["Kiểm tra quy tắc và tương quan"]
    Validate --> Decision{"Cấu hình hợp lệ?"}
    Decision -->|"Không"| Error["Báo lỗi rõ trường, không đụng I/O"]
    Decision -->|"Có"| Config["ValidatedConfig bất biến"]
    Config --> Root["Composition root chọn adapter"]
    Root --> Open["Tạo hoặc mở tài nguyên bên ngoài"]
    Open --> Inject["Constructor injection vào service"]
    Inject --> Use["Thực hiện tác vụ"]
    Use --> Close["Đóng theo ownership/lifecycle"]
~~~

Trong luồng này, **cấu hình sai bị chặn trước ranh giới side effect**. Khi cấu hình đã hợp lệ, ứng dụng mới có quyền cân nhắc mở resource, kiểm tra kết nối và khởi chạy logic nghiệp vụ.

## 2. Phân loại những thứ có thể và không thể xác minh trước I/O

Nói “xác minh cấu hình trước khi dùng tài nguyên” không đồng nghĩa mọi điều kiện đều có thể được biết mà không kết nối ra ngoài. Nên phân biệt ít nhất ba tầng.

| Tầng | Cần kiểm tra | Có cần tài nguyên bên ngoài? | Ví dụ |
| --- | --- | --- | --- |
| **Cú pháp và kiểu dữ liệu** | Trường bắt buộc, số nguyên, URI, enum, định dạng thời lượng | Không | `timeoutMs` có phải số? URL có cú pháp hợp lệ? |
| **Ràng buộc và tính nhất quán** | Giá trị trong giới hạn cho phép, lựa chọn tương thích, xung đột tùy chọn | Thường không | Timeout từ 100–30.000 ms; HTTPS bắt buộc; hai chế độ không được đồng thời bật |
| **Khả dụng bên ngoài** | DNS, xác thực thật, quyền truy cập, kết nối, schema/database, quota | Có | Server có phản hồi? Credential có quyền? Bảng cần thiết có tồn tại? |

Hai tầng đầu nên chạy **trước** việc tạo hoặc sử dụng adapter hạ tầng. Tầng thứ ba cần I/O, nên được xem là **preflight kết nối**, **readiness check** hoặc **startup verification** riêng, có thời gian chờ và cleanup rõ ràng.

Điều quan trọng: một kết nối kiểm tra thành công lúc khởi động **không bảo đảm** server sẽ tiếp tục khả dụng khi request thực sự chạy. Ngược lại, một lỗi mạng tạm thời không có nghĩa cấu hình cú pháp đã sai. Hai loại lỗi có cách xử lý và giám sát khác nhau.

### Danh sách ràng buộc nên có với endpoint

Ví dụ, ứng dụng muốn chỉ kết nối đến HTTPS, không cho nhét username/password hoặc token vào URL. Một hợp đồng hợp lý có thể yêu cầu:

- URL là URI tuyệt đối, scheme `https`.
- Có hostname hợp lệ theo bộ phân tích URI.
- Không chứa `userinfo`, query hoặc fragment để giảm nguy cơ vô ý đưa bí mật vào URL và log.
- Không có giá trị timeout bằng 0, âm, vượt giới hạn hoặc sai kiểu.
- `apiKey` có mặt và không trống; không ghi giá trị thật vào thông báo lỗi.

Các quy tắc trên là **quy tắc thiết kế của ứng dụng ví dụ**, không phải điều kiện bắt buộc cho mọi API HTTPS. Một ứng dụng khác có thể cần query parameter hợp lệ và vẫn bảo đảm không đưa bí mật vào URL.

## 3. Tách cấu hình thô và cấu hình đã xác minh

Một mẫu thiết kế rõ ràng dùng hai kiểu dữ liệu:

1. **RawConfig** biểu diễn dữ liệu nhận từ môi trường, file hoặc command line. Giá trị có thể thiếu/sai và chưa nên dùng để khởi tạo adapter.
2. **ValidatedConfig** biểu diễn dữ liệu đã được phân tích và đáp ứng các điều kiện cần thiết. Đối tượng này bất biến và được truyền đến composition root.

~~~java
// Minh họa cấu trúc, các import được lược bỏ tại đây.
record RawConfig(String endpoint, String timeoutMs, String apiKey) {}

record ValidatedConfig(
        java.net.URI endpoint,
        java.time.Duration timeout,
        String apiKey) {
}
~~~

Lưu ý: **chỉ đặt tên kiểu `ValidatedConfig` không làm dữ liệu tự trở nên hợp lệ**. Phải có **một đường tạo được kiểm soát** và các bất biến được bảo vệ. Trong ví dụ hoàn chỉnh, parser thu thập lỗi theo trường, còn constructor của `ValidatedConfig` kiểm tra lại bất biến cốt lõi để ngăn mã khác vô tình tạo instance sai.

Các trách nhiệm nên được chia:

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| `RawConfig` | Giữ dữ liệu cấu hình chưa được tin cậy | Tự mở socket, kết nối database |
| `ConfigValidator` | Parse, kiểm tra và tạo cấu hình hợp lệ | Gọi API bên ngoài để “thử” khi mới kiểm tra kiểu |
| `ValidatedConfig` | Giữ giá trị chuẩn hóa/bất biến | Che giấu hoặc tự tạo HTTP client |
| Composition root | Chọn implementation, tạo resource, inject dependency | Để service nghiệp vụ tự đọc `System.getenv` |
| Adapter | Sử dụng cấu hình để giao tiếp hạ tầng | Tự suy đoán một cấu hình thiếu thành mặc định nguy hiểm |
| Lifecycle owner | Đóng resource theo scope | Đóng tài nguyên người khác đang dùng |

Điểm cốt lõi của DI/IoC vẫn giữ nguyên: service nghiệp vụ **sử dụng dependency đã được cung cấp**, không chọn và khởi tạo hạ tầng dựa trên biến môi trường.

## 4. Fail fast hay thu thập toàn bộ lỗi cấu hình?

Với một lỗi không thể khắc phục, **fail fast** nghĩa là dừng trước khi ứng dụng bắt đầu thực hiện công việc có side effect. Nhưng trong bước xác minh cấu hình, có thể hữu ích nếu **thu thập nhiều lỗi cùng lúc**, thay vì bắt người vận hành sửa từng trường theo nhiều vòng khởi động.

Ví dụ cấu hình đầu vào có ba lỗi:

~~~text
endpoint=http://service.example.test
timeoutMs=-100
apiKey=<empty>
~~~

Một kết quả hợp lý là:

~~~text
Invalid configuration:
- endpoint: expected HTTPS URL with host and no credentials/query/fragment
- timeoutMs: expected integer from 100 to 30000
- apiKey: required
~~~

Lợi ích:

- Người vận hành biết tất cả trường cần sửa trong một lượt.
- Không có network/file/database nào được khởi tạo khi dữ liệu sai.
- Thông báo chỉ cho biết **tên trường và quy tắc**, không tiết lộ nội dung secret.

**Ngoại lệ:** nếu một phép kiểm tra phụ thuộc vào giá trị chuẩn hóa của phép kiểm tra trước, cần tránh chạy mù quáng và gây `NullPointerException`. Ví dụ URI sai cú pháp thì bỏ qua các kiểm tra scheme/host ở URI đó, nhưng vẫn tiếp tục kiểm tra timeout và API key.

## 5. Ví dụ Java 17 hoàn chỉnh: cấu hình sai không mở kết nối

Ví dụ sau chỉ sử dụng thư viện chuẩn Java. Chúng ta tạo một `ConnectorFactory` giả có bộ đếm số lần `open()` và số lần `close()`. Test bảo đảm:

- Cấu hình sai tạo **nhiều lỗi theo trường**, không hề gọi factory.
- Cấu hình đúng mới gọi factory và inject connector vào `SyncService`.
- Khi thao tác gửi dữ liệu ném ngoại lệ, connector vẫn được đóng.
- Nếu factory không mở được tài nguyên, ngoại lệ được chuyển lên; factory phải tự dọn mọi resource đã cấp phát **trước khi trả object**.

Lưu toàn bộ mã vào `Main.java`:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record RawConfig(String endpoint, String timeoutMs, String apiKey) {}

record ValidatedConfig(URI endpoint, Duration timeout, String apiKey) {
    ValidatedConfig {
        Objects.requireNonNull(endpoint, "endpoint");
        Objects.requireNonNull(timeout, "timeout");
        Objects.requireNonNull(apiKey, "apiKey");

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null
                || endpoint.getRawUserInfo() != null
                || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException("Invalid endpoint");
        }
        long millis = timeout.toMillis();
        if (millis < 100 || millis > 30_000) {
            throw new IllegalArgumentException("Invalid timeout");
        }
        if (apiKey.isBlank()) {
            throw new IllegalArgumentException("Missing apiKey");
        }
    }
}

final class ConfigurationException extends IllegalArgumentException {
    private final List<String> issues;

    ConfigurationException(List<String> issues) {
        super("Invalid configuration: " + String.join("; ", issues));
        this.issues = List.copyOf(issues);
    }

    List<String> issues() {
        return issues;
    }
}

final class ConfigValidator {
    private ConfigValidator() {
    }

    static ValidatedConfig validate(RawConfig raw) {
        Objects.requireNonNull(raw, "raw");
        List<String> issues = new ArrayList<>();

        URI endpoint = null;
        String rawEndpoint = raw.endpoint();
        if (rawEndpoint == null || rawEndpoint.isBlank()) {
            issues.add("endpoint: required");
        } else {
            try {
                URI candidate = URI.create(rawEndpoint.trim());
                if (!"https".equalsIgnoreCase(candidate.getScheme())
                        || candidate.getHost() == null
                        || candidate.getRawUserInfo() != null
                        || candidate.getRawQuery() != null
                        || candidate.getRawFragment() != null) {
                    issues.add("endpoint: expected HTTPS URL with host "
                            + "and no credentials/query/fragment");
                } else {
                    endpoint = candidate;
                }
            } catch (IllegalArgumentException ignored) {
                // Không đưa nội dung URL thô vào lỗi vì có thể chứa bí mật.
                issues.add("endpoint: invalid URI syntax");
            }
        }

        Duration timeout = null;
        try {
            long millis = Long.parseLong(raw.timeoutMs());
            if (millis < 100 || millis > 30_000) {
                issues.add("timeoutMs: expected integer from 100 to 30000");
            } else {
                timeout = Duration.ofMillis(millis);
            }
        } catch (NumberFormatException ignored) {
            issues.add("timeoutMs: expected integer from 100 to 30000");
        }

        String apiKey = raw.apiKey();
        if (apiKey == null || apiKey.isBlank()) {
            issues.add("apiKey: required");
        }

        if (!issues.isEmpty()) {
            throw new ConfigurationException(issues);
        }
        return new ValidatedConfig(endpoint, timeout, apiKey);
    }
}

interface Connector extends AutoCloseable {
    void send(String message);

    @Override
    void close();
}

@FunctionalInterface
interface ConnectorFactory {
    Connector open(ValidatedConfig config);
}

final class SyncService {
    private final Connector connector;

    SyncService(Connector connector) {
        this.connector = Objects.requireNonNull(connector, "connector");
    }

    void sync(String payload) {
        connector.send(payload);
    }
}

final class Application {
    private Application() {
    }

    static void runOnce(RawConfig raw, ConnectorFactory factory) {
        Objects.requireNonNull(factory, "factory");

        // Bước 1: hoàn tất kiểm tra thuần dữ liệu, KHÔNG I/O.
        ValidatedConfig config = ConfigValidator.validate(raw);

        // Bước 2: chỉ bây giờ mới cho phép tạo resource ngoài.
        try (Connector connector = Objects.requireNonNull(
                factory.open(config), "opened connector")) {

            // Bước 3: composition root tiêm dependency đã chọn.
            SyncService service = new SyncService(connector);
            service.sync("SYNC");
        }
        // Bước 4: close() chạy kể cả khi sync() ném lỗi.
    }
}

// Test double: không kết nối mạng, chỉ ghi nhận các sự kiện.
final class CountingConnectorFactory implements ConnectorFactory {
    int openCalls;
    int closeCalls;
    final List<String> sent = new ArrayList<>();
    boolean failOnOpen;
    boolean failOnSend;

    @Override
    public Connector open(ValidatedConfig config) {
        openCalls++;
        if (failOnOpen) {
            throw new IllegalStateException("Connector unavailable");
        }
        return new Connector() {
            private boolean closed;

            @Override
            public void send(String message) {
                if (closed) {
                    throw new IllegalStateException("Connector closed");
                }
                if (failOnSend) {
                    throw new IllegalStateException("Send failed");
                }
                sent.add(message);
            }

            @Override
            public void close() {
                if (!closed) {
                    closed = true;
                    closeCalls++;
                }
            }
        };
    }
}

public class Main {
    public static void main(String[] args) {
        // Không có credential thật; tất cả adapter đều là fake.
        RawConfig invalid = new RawConfig(
                "http://service.example.test", "-100", " ");
        CountingConnectorFactory factory = new CountingConnectorFactory();

        boolean rejected = false;
        try {
            Application.runOnce(invalid, factory);
        } catch (ConfigurationException expected) {
            rejected = true;
            check(expected.issues().size() == 3,
                    "Phải báo đủ 3 trường không hợp lệ");
            check(!expected.getMessage().contains("secret"),
                    "Thông báo lỗi không được lộ secret");
        }
        check(rejected, "Cấu hình sai phải bị chặn");
        check(factory.openCalls == 0 && factory.closeCalls == 0,
                "Cấu hình sai không được mở tài nguyên");

        RawConfig valid = new RawConfig(
                "https://service.example.test/v1",
                "1500", "example-key-not-real");
        Application.runOnce(valid, factory);
        check(factory.openCalls == 1 && factory.closeCalls == 1,
                "Cấu hình hợp lệ phải mở và đóng đúng một lần");
        check(factory.sent.equals(List.of("SYNC")),
                "Service phải dùng connector đã tiêm");

        CountingConnectorFactory sendFailure =
                new CountingConnectorFactory();
        sendFailure.failOnSend = true;
        boolean sendFailed = false;
        try {
            Application.runOnce(valid, sendFailure);
        } catch (IllegalStateException expected) {
            sendFailed = true;
        }
        check(sendFailed, "Phải quan sát được lỗi gửi");
        check(sendFailure.openCalls == 1
                        && sendFailure.closeCalls == 1,
                "Connector phải đóng cả khi send thất bại");

        CountingConnectorFactory openFailure =
                new CountingConnectorFactory();
        openFailure.failOnOpen = true;
        boolean openFailed = false;
        try {
            Application.runOnce(valid, openFailure);
        } catch (IllegalStateException expected) {
            openFailed = true;
        }
        check(openFailed && openFailure.openCalls == 1,
                "Phải phát hiện lỗi mở connector");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

Trong mô hình này, **`Application.runOnce` là composition root cho một thao tác đơn giản**. Cấu hình được kiểm tra trước khi gọi `ConnectorFactory.open`. `SyncService` chỉ biết hợp đồng `Connector` và không đọc cấu hình từ môi trường. Khi thực hành production, composition root của ứng dụng thường giữ client/pool dùng chung qua nhiều request thay vì mở và đóng mỗi lần; **ví dụ cố ý giới hạn vòng đời trong một thao tác** để quan sát ownership.

Đối với đường lỗi `factory.open(config)` ném ngoại lệ, `runOnce` chưa nhận được connector nào để đóng. **Factory** chịu trách nhiệm dọn tài nguyên được mở dở trước khi ném lỗi. Test ở trên xác minh lỗi được chuyển ra, **không** mô phỏng quá trình dọn tài nguyên dở dang trong implementation của factory.

## 6. Những kiểm tra nào nên nằm ở constructor và composition root?

Cần chọn đúng nơi kiểm tra thay vì đẩy mọi logic vào một class lớn.

**Ở kiểu dữ liệu cấu hình:** các bất biến nội tại, chẳng hạn timeout dương và endpoint có định dạng hợp lệ. Ví dụ `ValidatedConfig` tự kiểm tra để không dễ bị tạo sai ngoài đường validator. Lỗi cần chỉ rõ quy tắc mà không tiết lộ dữ liệu nhạy cảm.

**Ở bước chuẩn hóa/validator:** chuyển từ chuỗi thô sang kiểu có nghĩa (`Duration`, `URI`, `enum`); thu thập lỗi của nhiều trường; kiểm tra tính nhất quán giữa các lựa chọn. Đây là bước thuần tính toán và có thể unit test nhanh.

**Ở composition root:** chọn implementation, quyết định adapter dùng thật hay fake, policy retry, scope, ownership và thứ tự mở resource. Root chỉ tạo tài nguyên sau khi nhận config đã xác minh.

**Ở adapter:** kiểm tra những điều kiện có liên quan trực tiếp đến giao thức hoặc hạ tầng; báo lỗi nếu không kết nối/xác thực được; bảo đảm cleanup tài nguyên tạo dở. Adapter không nên tự sửa cấu hình sai bằng giá trị mặc định tùy tiện.

**Ở service nghiệp vụ:** kiểm tra các bất biến nghiệp vụ trên dữ liệu của lời gọi; nhận dependency bằng constructor. Service không nên gọi `System.getenv` rồi tự quyết định cổng kết nối nào cần tạo.

Một constructor service như `new SyncService(connector)` vẫn nên dùng `Objects.requireNonNull` cho dependency bắt buộc. Tuy nhiên, **kiểm tra null của dependency không thay thế bước xác minh endpoint, timeout và credential** đã được định nghĩa ở lớp cấu hình.

## 7. Xác minh kết nối thật: không được nhầm với xác minh cấu hình tĩnh

Sau khi cấu hình có cú pháp và quy tắc hợp lệ, ứng dụng có thể cần **kiểm tra khả dụng bên ngoài**.

Ví dụ:

- Kết nối database để xác minh credential và quyền truy cập cần thiết.
- Thử một request sức khỏe tới API đích.
- Xác minh topic/queue, schema hoặc bucket có tồn tại.
- Kiểm tra việc mở file theo đường dẫn và quyền ghi/đọc thực tế.

Những bước này **không còn thuần dữ liệu** và nên có các giới hạn:

1. **Timeout rõ ràng:** không để khởi động chờ vô thời hạn.
2. **Không gây tác dụng phụ không cần thiết:** không tạo đơn hàng thật, gửi email thật hoặc ghi một sự kiện nghiệp vụ chỉ để kiểm tra kết nối.
3. **Cleanup:** connection, response hoặc stream được mở phải đóng/trả về pool đúng hợp đồng.
4. **Lỗi phân loại được:** lỗi DNS, timeout, authentication, thiếu quyền và sai schema có hướng xử lý khác nhau.
5. **Chính sách startup rõ ràng:** service có bắt buộc từ chối khởi chạy khi dependency ngoài tạm thời không có, hay cho phép khởi chạy nhưng chưa sẵn sàng nhận request?

~~~mermaid
flowchart TD
    Parsed["ValidatedConfig"] --> Acquire["Tạo adapter với timeout"]
    Acquire --> Check{"Kiểm tra có I/O"}
    Check -->|"Đạt"| Ready["Báo sẵn sàng theo chính sách"]
    Check -->|"Không đạt"| Classify["Phân loại lỗi"]
    Classify --> Decision{"Dependency bắt buộc?"}
    Decision -->|"Có"| Stop["Đóng tài nguyên, từ chối sẵn sàng"]
    Decision -->|"Không"| Degraded["Chế độ suy giảm được thiết kế rõ"]
~~~

**Lưu ý về thời điểm:** một lần ping thành công không bảo đảm lệnh gửi tiếp theo sẽ thành công. Validation không thay thế timeout, retry có giới hạn, circuit breaker, xử lý lỗi hoặc giám sát lúc chạy. Ngược lại, nếu thiết kế cần **readiness** nhưng không yêu cầu **liveness** ngừng hoạt động khi dependency tạm thời lỗi, đừng gắn mọi thất bại mạng với việc tiến trình phải bị kill hoặc restart liên tục.

## 8. Eager, lazy và startup failure trong DI container

Khi sử dụng DI container, có thể đăng ký factory để tạo dependency theo kiểu **eager** hoặc **lazy**. Ranh giới xác minh cần được giữ rõ trong cả hai cách.

| Trường hợp | Điều cần bảo đảm |
| --- | --- |
| Singleton eager | Cấu hình được parse/validate trước khi container tạo các resource dùng chung; lỗi khởi tạo làm ứng dụng không sẵn sàng |
| Singleton lazy | Đã xác minh **cấu hình tĩnh** lúc bootstrap dù client chỉ được mở lúc cần; dự phòng lỗi kết nối ở lần gọi đầu |
| Request-scoped adapter | Cấu hình chung đã được xác minh; dữ liệu/scope riêng của từng request được kiểm tra trước khi mở resource của request |
| Provider/factory | Scope của provider và sản phẩm khác nhau; không mặc định container quản lý mọi instance do provider tự tạo |

Một rủi ro của lazy initialization là **lỗi cấu hình bị đẩy sang request đầu tiên**. Nếu cấu hình có thể được kiểm tra mà không I/O, không có lý do tốt để trì hoãn phần kiểm tra đó. Đối với các kết nối ngoài, lazy có thể hữu ích nhưng cần chính sách retry/readiness và lỗi ở runtime thích hợp.

### Nếu khởi tạo dở dang thất bại

Ví dụ composition root mở pool rồi mở message publisher; nếu bước sau thất bại, phải đóng pool đã tạo. Với Java thuần, có thể dùng `try-with-resources` hoặc `try/finally` cho các resource trong giai đoạn bootstrap, chỉ chuyển ownership cho đối tượng quản lý ứng dụng **khi việc lắp ghép đã thành công**.

Không giả định container sẽ dọn mọi resource được tạo dở **trước khi đăng ký hoàn tất**. Cần xem lifecycle contract của factory và framework. Khi shutdown, dừng tiếp nhận tác vụ, kết thúc các consumer đang chạy rồi mới đóng dependency nền như pool.

## 9. Bảo vệ bí mật và thông tin cấu hình nhạy cảm

Xác minh cấu hình không được biến thành đường rò rỉ secret.

Một số nguyên tắc:

- **Không in `RawConfig` hoặc `ValidatedConfig` nguyên object** nếu record chứa `apiKey`. `toString()` mặc định của record sẽ có thể đưa giá trị secret vào log.
- Không ghép trực tiếp endpoint thô, token, password hoặc chuỗi kết nối vào thông báo lỗi; chúng có thể chứa credential.
- Đưa ra tên trường và điều kiện hợp lệ: “`apiKey` required”, “`endpoint` must be HTTPS”; tránh “token sai: ...”.
- Nếu phải ghi dấu cấu hình để chẩn đoán, chỉ ghi thông tin đã được whitelist/redact; không cho phép bất cứ phần nào của URL có thể chứa credential lọt vào log.
- Coi giá trị từ biến môi trường, file và secret manager là **dữ liệu đầu vào cần kiểm tra**. Secret manager cung cấp dữ liệu không đồng nghĩa giá trị đó luôn phù hợp với ứng dụng.
- Sử dụng cơ chế bí mật của nền tảng, quyền truy cập tối thiểu và quy trình xoay vòng phù hợp với môi trường triển khai.

Trong mã Java ví dụ, `String` chứa API key nhằm giữ bài thực hành đơn giản; `String` là immutable và không thể chủ động xóa nội dung một cách đáng tin cậy. Với hệ thống có yêu cầu bảo vệ bí mật cao, cách nạp, lưu và dùng credential cần được thiết kế cùng security policy, không chỉ dựa vào việc đổi từ `String` sang `char[]`.

## 10. Không che lỗi cấu hình bằng mặc định thiếu chủ đích

Các giá trị mặc định có thể hợp lệ khi được thiết kế theo hợp đồng. Ví dụ, timeout mặc định có thể là một `Duration` đã được sản phẩm phê duyệt. Nhưng một lỗi cần tránh là **tự chọn adapter khác để ứng dụng khởi động bằng mọi giá**.

Ví dụ sai về ý tưởng:

~~~java
// Mã minh họa chống mẫu:
if (databaseUrl == null) {
    repository = new InMemoryRepository();
} else {
    repository = new JdbcRepository(databaseUrl);
}
~~~

Nếu ứng dụng production bắt buộc lưu dữ liệu bền vững, cách này có thể biến **thiếu cấu hình database** thành **mất dữ liệu âm thầm**. Với dependency quan trọng, **từ chối cấu hình thiếu** tốt hơn giả lập thành công.

Khi ứng dụng có chế độ offline hoặc test trong bộ nhớ chính thức, hãy biểu diễn nó bằng **chế độ cấu hình có tên rõ ràng** và kiểm tra các ràng buộc tương ứng. Chẳng hạn `STORAGE_MODE=IN_MEMORY` chỉ được phép trong môi trường hoặc profile đã chấp thuận. Không nên coi mọi lỗi cấu hình là tín hiệu tự động chuyển sang No-Op.

Một cấu hình có nhiều trường cần kiểm tra cả **quan hệ chéo**, ví dụ: nếu bật TLS thì phải cung cấp certificate/trust policy; nếu chọn broker thì phải có topic; nếu bật một tính năng thì phải có các dependency bắt buộc của tính năng đó. Việc chỉ kiểm tra từng trường không rỗng có thể chưa đủ.

## 11. Kiểm thử ranh giới “chưa được đụng I/O”

Ngoài test parser, một yêu cầu quan trọng là **chứng minh cấu hình sai không kích hoạt tài nguyên ngoài**. Có thể làm điều đó bằng:

- Fake factory ghi số lần `open()` như trong `Main.java`.
- Test double chủ động ném `AssertionError` nếu có ai gọi factory trong quá trình validation.
- Unit test kiểm tra validator **không phụ thuộc interface kết nối** và không đọc file/biến môi trường ẩn.
- Integration test thử adapter thật khi cấu hình hợp lệ để xác minh wiring và cleanup.

Nên bao phủ các nhóm lỗi:

| Nhóm kiểm thử | Ví dụ đầu vào/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Thiếu trường | `apiKey` trống | Báo lỗi trường, không mở resource |
| Sai cú pháp | URL/timeout không parse được | Báo lỗi thân thiện, không lộ giá trị thô |
| Sai giới hạn | Timeout bằng 0 hoặc quá lớn | Bị chặn trước I/O |
| Sai tương quan | Bật feature nhưng thiếu dependency cần thiết | Không lắp ghép object graph không hợp lệ |
| Cấu hình hợp lệ | Endpoint HTTPS, timeout trong giới hạn | Factory mới được gọi |
| Lỗi mở resource | Factory ném lỗi | Lỗi được chuyển lên; factory tự dọn phần tạo dở |
| Lỗi nghiệp vụ sau khi mở | Connector gửi thất bại | Resource đã nhận được đóng theo ownership |
| Shutdown khi có tác vụ | Pool vẫn được dùng | Dừng tác vụ/consumer rồi mới đóng pool |

Unit test dùng fake giúp kiểm tra **thứ tự và ranh giới tác dụng phụ**; integration test với database hoặc API mới kiểm tra được giả định về hạ tầng thực. Hai loại test bổ sung cho nhau, không thay thế nhau.

## 12. Những sai lầm thường gặp

### 12.1. Kết nối để xem cấu hình có đúng cú pháp không

Không cần mở socket để biết `timeoutMs=-1` không hợp lệ hoặc endpoint thiếu scheme. Parse và xác minh các trường đó bằng Java thuần trước.

### 12.2. Kiểm tra cấu hình rải rác trong từng service

Khi `OrderService`, `InvoiceService` và `EmailService` đều đọc `System.getenv` riêng, hệ thống khó biết đã kiểm tra đủ trước khi có side effect. Đưa việc chuẩn hóa/kiểm tra cấu hình và lựa chọn adapter về composition root.

### 12.3. “Validator” cũng gọi database, DNS hoặc HTTP mà không nói rõ

Một API `validate(config)` nghe như kiểm tra thuần dữ liệu nhưng có thể che giấu I/O. Nếu cần kiểm tra kết nối, nên gọi rõ `checkConnectivity` hoặc `verifyReadiness`, có timeout, cleanup và chính sách lỗi riêng.

### 12.4. In nguyên giá trị sai ra log

`throw new IllegalArgumentException("Invalid apiKey: " + apiKey)` là nguy cơ lộ secret. Thông báo nên chỉ ra trường và quy tắc, không lặp lại giá trị mật.

### 12.5. Kiểm tra quá muộn vì dùng lazy DI

Lazy tạo client không đồng nghĩa lazy phải kiểm tra cả phần cú pháp. Hãy xác minh cấu hình tĩnh trước khi ứng dụng nhận request, rồi xử lý lỗi I/O khi tạo resource theo thời điểm thiết kế.

### 12.6. Xác minh kết nối xong rồi giả định không bao giờ có lỗi

Kết nối có thể bị đóng, credential hết hạn hoặc dịch vụ ngoài ngừng hoạt động. Startup preflight **không thay thế** xử lý lỗi runtime.

### 12.7. Dọn sai resource khi bootstrap thất bại

Nếu một resource đã mở nhưng resource tiếp theo thất bại, các tài nguyên đã sở hữu cần được đóng. Nếu mở kết nối dùng chung cho nhiều service, từng service không được tùy tiện đóng kết nối đó sau mỗi lời gọi.

## 13. Bài tập thực hành

**Bài 1 — Thiết kế validator.** Ứng dụng nhận `storageMode`, `dbUrl`, `retryCount` và `timeoutMs`. Hãy phân biệt quy tắc kiểm tra cú pháp, giới hạn và quan hệ chéo. Chỉ cho phép thiếu `dbUrl` nếu mode được khai báo rõ là bộ nhớ và chế độ ấy hợp lệ.

**Bài 2 — Phát hiện side effect.** Refactor một composition root đang tạo HTTP client trước khi parse timeout. Dùng fake factory đếm lần `open()` để xác minh cấu hình sai không tạo client.

**Bài 3 — Bảo vệ secret.** Sửa thông báo lỗi validator để không in API key, password hoặc toàn URL thô. Kiểm tra cả `toString()` của record cấu hình có thể làm lộ dữ liệu ở đâu.

**Bài 4 — Xử lý lỗi khởi động.** Composition root đã mở một pool; bước mở message publisher thất bại. Thiết kế trình tự cleanup khi bootstrap lỗi và trình tự ownership khi bootstrap thành công.

**Bài 5 — Readiness.** Một API ngoài đôi khi timeout trong lúc khởi động nhưng ứng dụng vẫn có thể phục vụ các chức năng không liên quan. Đề xuất chính sách readiness/degraded mode có giới hạn, phân biệt lỗi mạng tạm thời với cấu hình sai.

## 14. Tự kiểm tra mức độ hiểu

**Câu 1.** Vì sao nên xác minh timeout trước khi tạo HTTP client? **Vì** timeout sai có thể được phát hiện hoàn toàn bằng dữ liệu, tránh mở resource rồi phải rollback/cleanup.

**Câu 2.** Một URI HTTPS hợp lệ có chứng minh dịch vụ ngoài khả dụng và token có quyền không? **Không.** Đó là kiểm tra cú pháp/quy tắc, không phải kết quả kiểm tra I/O.

**Câu 3.** DI container có tự bảo đảm mọi trường cấu hình đều đúng không? **Không.** Container giúp tạo/lắp ghép dependency; ứng dụng vẫn phải xác định các bất biến cấu hình và chiến lược xác minh.

**Câu 4.** Nếu `factory.open()` ném lỗi trước khi trả resource, ai chịu trách nhiệm dọn tài nguyên mở dở? **Factory**, vì consumer chưa nhận quyền sở hữu resource ấy.

**Câu 5.** Có nên đưa API key thật vào `ConfigurationException` để dễ debug không? **Không.** Báo tên trường và quy tắc, tránh ghi lại secret.

**Câu 6.** Vì sao phải có cả unit test và integration test? **Vì** unit test kiểm tra ranh giới validation và thứ tự side effect; integration test kiểm chứng adapter, credential và kết nối thật.

## Ghi nhớ

- **Xác minh cú pháp, giới hạn và tính nhất quán của cấu hình trước khi mở tài nguyên bên ngoài**; cấu hình sai phải bị chặn tại ranh giới side effect.
- **Tách `RawConfig` khỏi `ValidatedConfig`**, bảo vệ bất biến, thu thập lỗi theo trường và không đưa secret hoặc URL nhạy cảm vào log.
- **Composition root** chọn và lắp ghép adapter sau khi config hợp lệ; service nghiệp vụ tiếp tục nhận dependency bằng constructor thay vì đọc môi trường.
- **Kiểm tra khả dụng bên ngoài** là bước I/O riêng, cần timeout, cleanup và chính sách readiness; kiểm tra thành công không loại bỏ lỗi runtime.
- **Scope, ownership và lifecycle** vẫn phải rõ khi dùng DI container: cleanup resource tạo dở, đóng dependency được sở hữu đúng thời điểm, kiểm thử rằng cấu hình sai không làm phát sinh kết nối.
