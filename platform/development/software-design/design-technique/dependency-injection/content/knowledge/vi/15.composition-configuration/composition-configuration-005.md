# Giá trị mặc định, độ ưu tiên nguồn cấu hình và khả năng truy vết

Một chương trình có thể áp dụng **Dependency Injection (DI)** đúng kỹ thuật — service nhận các interface qua constructor, composition root tạo và nối các adapter — nhưng vẫn vận hành sai nếu **cấu hình lắp ghép** thiếu quy tắc. Chẳng hạn, cùng một ứng dụng có giá trị timeout trong tệp cấu hình, biến môi trường và tham số dòng lệnh: giá trị nào được dùng để tạo HTTP client? Khi chạy production, làm sao biết cổng thanh toán đang dùng adapter nào, ai đã ghi đè cấu hình và vì sao?

**Cấu hình lắp ghép (composition configuration)** là tập hợp các quyết định và giá trị được sử dụng **tại ranh giới khởi động** để chọn implementation, tạo dependency, áp dụng scope/vòng đời và xây dựng object graph. Bài học này tập trung vào ba yếu tố thiết yếu:

1. **Giá trị mặc định (defaults)**: ứng dụng có thể hoạt động với những lựa chọn an toàn, có chủ đích khi chưa có cấu hình bên ngoài.
2. **Độ ưu tiên nguồn cấu hình (precedence)**: khi nhiều nguồn khai báo cùng một khóa, phải có quy tắc rõ ràng để quyết định giá trị hiệu lực.
3. **Khả năng truy vết (provenance/traceability)**: phải biết giá trị hiệu lực xuất phát từ nguồn nào, đã ghi đè những nguồn nào, trong khi **không để lộ thông tin bí mật**.

Trong module **Dependency Injection và Inversion of Control (IoC)**, các quyết định này thuộc về **composition root** hoặc thành phần cấu hình được bootstrap sử dụng. Service nghiệp vụ nên nhận **dependency đã được cấu hình** hoặc một **typed config** cần thiết qua constructor; không nên tự đi đọc `System.getenv()`, tệp cấu hình hay tham số CLI ở nhiều nơi khác nhau.

Sau bài này, bạn có thể:

- Xác lập thứ tự ưu tiên nguồn cấu hình một cách tường minh và có thể kiểm chứng.
- Phân biệt cấu hình **thiếu**, **rỗng**, **không hợp lệ** và **được ghi đè hợp lệ**.
- Thiết kế mặc định không vô tình làm ứng dụng chạy với adapter hoặc bí mật không phù hợp.
- Chuyển cấu hình dạng chuỗi thành kiểu Java bất biến, kiểm tra trước khi tạo object graph.
- Lưu **nguồn thắng**, lịch sử nguồn đóng góp và thông tin chẩn đoán an toàn.
- Thực hành resolution bằng Java 17 thuần, constructor injection và kiểm thử thứ tự ưu tiên.
- Hiểu giới hạn của DI container: nó có thể hỗ trợ binding và property resolution nhưng vẫn cần chính sách cấu hình do ứng dụng xác định.

## 1. Vì sao cấu hình là một phần của composition root?

Xem hai cách tạo một service thanh toán:

~~~java
// Cách 1: logic chọn adapter bị đưa vào nghiệp vụ.
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService() {
        String mode = System.getenv("PAYMENT_MODE");
        this.gateway = "sandbox".equals(mode)
                ? new SandboxPaymentGateway(/* config */)
                : new DemoPaymentGateway();
    }
}
~~~

Trong cách này, service biết tên biến môi trường, biết hai triển khai cụ thể và **tự chọn/cấp dependency**. Thay cấu hình khi test có thể đòi thay môi trường tiến trình; khi có nguồn cấu hình khác, logic có xu hướng bị phân tán.

~~~java
// Cách 2: phần nghiệp vụ chỉ nhận hợp đồng.
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }
}
~~~

Ở cách hai, composition root đưa ra quyết định:

~~~java
// Mã minh họa: config đã được resolve và validate trước đó.
PaymentGateway gateway = switch (config.mode()) {
    case DEMO -> new DemoPaymentGateway();
    case SANDBOX -> new SandboxPaymentGateway(config.timeoutMs());
};

CheckoutService checkout = new CheckoutService(gateway);
~~~

**Cấu hình không biến mất**; nó được chuyển vào đúng nơi chịu trách nhiệm tạo và nối dependency. Đây là ranh giới giữa:

- **Chính sách nghiệp vụ**: checkout phải làm gì với một PaymentGateway?
- **Chính sách lắp ghép**: PaymentGateway nào được sử dụng trong môi trường hiện tại, với timeout và tài nguyên gì?
- **Chính sách vận hành**: lấy cấu hình ở đâu, nguồn nào ưu tiên hơn, kiểm tra và truy vết ra sao?

DI đưa dependency vào service; **Dependency Inversion Principle (DIP)** giúp service phụ thuộc vào abstraction thay vì adapter cụ thể. Một DI container có thể tự động hóa bước cấp dependency, nhưng không thay ứng dụng quyết định thứ tự nguồn cấu hình hoặc ý nghĩa của từng khóa.

## 2. Nguồn cấu hình thường gặp và một chính sách ưu tiên rõ ràng

Một hệ thống Java có thể nhận cấu hình từ nhiều nguồn: giá trị mặc định trong mã, tệp `.properties` hoặc YAML, biến môi trường, system properties, tham số CLI, secret store hoặc dịch vụ cấu hình tập trung.

Không có một **thứ tự ưu tiên duy nhất đúng cho mọi framework và ứng dụng**. Bài này chủ động chọn chính sách minh họa sau, **từ ưu tiên thấp đến cao**:

| Mức ưu tiên | Nguồn | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| 1 — thấp nhất | **Defaults** được định nghĩa trong ứng dụng | Giá trị an toàn khi không có override | `payment.timeout-ms=1500` |
| 2 | **Tệp cấu hình** của môi trường | Cấu hình triển khai có thể quản lý bằng version | `payment.timeout-ms=2500` |
| 3 | **Biến môi trường** | Điều chỉnh theo deployment/process | `APP_PAYMENT_TIMEOUT_MS=3500` |
| 4 — cao nhất | **Tham số CLI** | Override có chủ đích cho lần chạy cụ thể | `--payment.timeout-ms=5000` |

Với chính sách **nguồn sau ghi đè nguồn trước**, nếu cả bốn nơi cung cấp timeout thì giá trị hiệu lực là `5000`.

~~~mermaid
flowchart LR
    D["Defaults: 1500"] --> F["File: 2500"]
    F --> E["Environment: 3500"]
    E --> C["CLI: 5000"]
    C --> R["Resolved timeout: 5000"]
~~~

Đây là **quy ước do ứng dụng lựa chọn**, không phải lời khẳng định mọi DI container đều áp dụng chính thứ tự này. Ví dụ, một framework có thể có nhiều loại profile, system properties hoặc property sources với thứ tự riêng. Khi dùng framework, cần kiểm tra cấu hình thực tế và tránh đặt thêm một bộ resolver với quy tắc mâu thuẫn.

### Ví dụ tổng hợp theo từng khóa

Giả sử có ba khóa cấu hình:

| Khóa chuẩn | Default | File | Environment | CLI | Hiệu lực |
| --- | --- | --- | --- | --- | --- |
| `payment.mode` | `demo` | — | `sandbox` | — | **sandbox** (environment) |
| `payment.timeout-ms` | `1500` | `2500` | `3500` | `5000` | **5000** (CLI) |
| `receipt.prefix` | `DEFAULT` | `FILE` | — | — | **FILE** (file) |

Dấu “—” nghĩa là **nguồn không cung cấp khóa**, không phải cố ý đặt khóa thành chuỗi rỗng. Mỗi khóa được giải quyết độc lập: CLI chỉ ghi đè timeout, không làm mất giá trị mode từ environment hay prefix từ file.

### Tên khóa thống nhất giữa các nguồn

Một ứng dụng nên xác định **tên khóa nội bộ chuẩn** (*canonical keys*) rồi chuyển đổi định dạng từ bên ngoài trước khi merge:

~~~text
Tệp:      payment.timeout-ms=2500
Env:      APP_PAYMENT_TIMEOUT_MS=3500
CLI:      --payment.timeout-ms=5000

             chuẩn hóa về

Khóa nội bộ: payment.timeout-ms
~~~

Java chuẩn không tự chuyển `APP_PAYMENT_TIMEOUT_MS` thành `payment.timeout-ms`. Phép chuẩn hóa đó do mã bootstrap hoặc thư viện cấu hình đảm nhiệm. Nếu quy tắc ánh xạ thiếu nhất quán, các giá trị có thể bị xem như các khóa khác nhau và **không ghi đè nhau**.

Đặc biệt, khi hai biến môi trường khác nhau cùng được chuẩn hóa thành một khóa, ứng dụng nên **phát hiện xung đột** thay vì phụ thuộc vào thứ tự duyệt không rõ ràng.

## 3. Defaults: tiện lợi nhưng phải có giới hạn an toàn

Default phù hợp với những giá trị có ý nghĩa rõ ràng và không gây bất ngờ: một timeout hợp lý, kích thước batch, tên prefix dùng cho demo, hoặc chính sách retry mặc định được phê duyệt.

Tuy nhiên, **không phải giá trị nào cũng nên có default**:

| Loại giá trị | Gợi ý thiết kế | Nguy cơ khi mặc định không đúng |
| --- | --- | --- |
| Timeout và giới hạn kích thước | Có thể có default được kiểm tra giới hạn | Timeout quá lớn khiến request treo; quá nhỏ gây lỗi giả |
| Cờ tính năng thử nghiệm | Có thể mặc định theo trạng thái an toàn | Tính năng không mong muốn được bật |
| Adapter demo/sandbox | Chỉ mặc định khi ngữ cảnh cho phép; production nên chọn rõ | Production vô tình chạy adapter giả hoặc bỏ qua thao tác thật |
| Endpoint bên ngoài | Có thể bắt buộc trong deployment thật | Gọi nhầm server hoặc môi trường khác |
| Token, password, private key | **Không** lưu secret thật như một default trong mã hoặc repo | Rò bí mật và khó rotation |
| Tenant ID, khóa vùng dữ liệu | Thường cần nhập tường minh nếu gắn với bảo mật/cách ly | Ghi nhầm dữ liệu giữa các tenant |

Ví dụ, chính sách trong bài cho phép `payment.mode=demo` vì đây là chương trình giáo dục; **không nên mặc định chế độ demo cho một hệ thống thanh toán production** nếu điều đó có thể khiến giao dịch không được thực hiện. Một ứng dụng thật có thể chọn **không có default cho mode**, bắt buộc deployment khai báo giá trị hợp lệ và từ chối khởi động khi thiếu.

Một nguyên tắc thực dụng:

> **Default chỉ nên tồn tại nếu giá trị ấy an toàn và có thể giải thích trong đúng ngữ cảnh triển khai.** Thiếu cấu hình bắt buộc nên gây lỗi rõ ràng, không âm thầm chọn một phương án tưởng như tiện.

## 4. Phân biệt thiếu, rỗng, không hợp lệ và ghi đè

Không nên viết resolver chỉ bằng phép `getOrDefault(key, defaultValue)` rồi coi mọi tình huống khác nhau như “thiếu”.

| Tình huống | Ví dụ | Cách xử lý nên xác định rõ |
| --- | --- | --- |
| **Không tồn tại khóa** | Env không có `APP_PAYMENT_TIMEOUT_MS` | Giữ giá trị từ nguồn ưu tiên thấp hơn |
| **Chuỗi rỗng** | `APP_PAYMENT_TIMEOUT_MS=` | Lỗi cấu hình hoặc cơ chế xóa có chủ đích nếu được đặc tả |
| **Toàn khoảng trắng** | `APP_PAYMENT_TIMEOUT_MS="   "` | Thông thường từ chối; không coi là vắng mặt |
| **Không đúng kiểu** | `payment.timeout-ms=fast` | Báo lỗi parse, không tự đổi sang default |
| **Ngoài miền hợp lệ** | `payment.timeout-ms=-1` | Báo lỗi validate, dù parse số thành công |
| **Override hợp lệ** | CLI `5000` ghi đè env `3500` | Dùng `5000`, lưu nguồn thắng và chuỗi nguồn |
| **Khóa không biết** | `payment.tiemout-ms` | Phát hiện typo theo chính sách chặt, thay vì lặng lẽ bỏ qua |

Đối với **giá trị không hợp lệ ở nguồn ưu tiên cao**, một chính sách thường an toàn là **fail fast** với thông báo có tên khóa và nguồn, thay vì âm thầm lùi về giá trị thấp hơn. Nếu không, người vận hành có thể tin rằng `payment.timeout-ms=5000` đã áp dụng, trong khi thực tế ứng dụng chạy với default `1500`.

Bài này chọn chính sách **strict**: mọi giá trị có mặt trong các nguồn đều phải không rỗng, mọi khóa đều phải được nhận diện, và **giá trị hiệu lực cuối cùng** phải vượt qua bước parse/validate kiểu. Với cách chọn này, chuỗi rỗng hoặc khóa sai **ở cả nguồn bị ghi đè** cũng gây lỗi để không che mất một cấu hình hỏng. Các ứng dụng khác có thể chọn mức kiểm tra khác, nhưng phải ghi lại rõ quy tắc; không nên thay đổi âm thầm giữa môi trường test và production.

### Trường hợp “muốn xóa một cấu hình cũ”

Nếu hệ thống cần hỗ trợ *unset* hay *remove* một khóa từ nguồn ưu tiên cao, đừng lấy chuỗi rỗng làm tín hiệu ngầm mà không có tài liệu. Có thể dùng biểu diễn riêng như thao tác `REMOVE` hoặc kiểu kết quả phân biệt **absent / present / removed**; sau đó quy định cách resolver áp dụng. Ví dụ của bài **không hỗ trợ xóa khóa**: có mặt mà rỗng là lỗi.

## 5. Truy vết cấu hình: biết “tại sao object graph được lắp như vậy”

Sau khi một deployment khởi động, chỉ biết giá trị cuối cùng chưa đủ. Cần trả lời được:

1. **Khóa nào** được dùng để chọn adapter hoặc đặt timeout?
2. **Nguồn nào thắng** khi nhiều nguồn cùng cung cấp một khóa?
3. **Những nguồn nào đã đóng góp** cho khóa ấy theo thứ tự ưu tiên?
4. **Phiên bản cấu hình / môi trường / lần khởi động nào** đã tạo ra object graph hiện tại?
5. Thông tin truy vết có làm lộ password, token, endpoint riêng tư hoặc dữ liệu cá nhân hay không?

Một bản ghi truy vết có thể có dạng:

~~~text
payment.mode       = sandbox | winner = env:APP_*         | sources = defaults -> env:APP_*
payment.timeout-ms = 5000    | winner = cli               | sources = defaults -> file -> env -> cli
receipt.prefix     = FILE    | winner = file:app.properties | sources = defaults -> file
~~~

Các giá trị trong ví dụ đều **không nhạy cảm**. Với secret, nên chỉ ghi tên khóa và nguồn hoặc ghi giá trị đã che như `<redacted>`; thậm chí **tên nguồn/đường dẫn** cũng cần được xem xét nếu chứa thông tin nhạy cảm.

### Provenance khác log toàn bộ cấu hình

**Provenance** là metadata mô tả *nguồn gốc và quá trình chọn* giá trị, không nhất thiết chứa toàn bộ nội dung thô. Ví dụ một bản ghi có thể giữ:

~~~text
key: payment.api-token
selectedSource: secret-store
overriddenSources: [defaults, env]
value: <redacted>
~~~

Nếu muốn truy nguyên chính xác một lần triển khai, còn có thể ghi **mã phiên bản cấu hình**, **thời điểm khởi động** và **dấu định danh triển khai** do hệ thống vận hành cấp. Không nên đưa bí mật thực vào thông báo lỗi, metric label hay exception stack trace chỉ để “debug cho dễ”.

Khi triển khai cơ chế log chung, cách an toàn là **mặc định không log giá trị**; chỉ bật hiển thị giá trị cho danh sách khóa không nhạy cảm đã được cho phép (*allowlist*). Tránh cơ chế dựa thuần vào việc tên khóa có chứa `password` hay `secret`, vì khóa nhạy cảm có thể mang tên khác.

## 6. Thứ tự xử lý đúng: từ nguồn thô đến typed config và object graph

Thay vì để từng service tự đọc cấu hình tại thời điểm cần dùng, hãy áp dụng pipeline nhất quán:

~~~mermaid
flowchart TD
    Sources["Defaults / File / Environment / CLI"] --> Normalize["Chuẩn hóa tên khóa"]
    Normalize --> Merge["Merge theo thứ tự ưu tiên"]
    Merge --> Origin["Ghi nhận nguồn thắng và lịch sử nguồn"]
    Origin --> Parse["Parse kiểu, kiểm tra miền giá trị"]
    Parse --> Typed["Typed AppConfig bất biến"]
    Typed --> Root["Composition root chọn adapter và scope"]
    Root --> Graph["Object graph đã lắp ghép"]
    Root --> Safe["Trace an toàn, không lộ secret"]
~~~

Với mô hình này, **một snapshot cấu hình có hiệu lực** được xác nhận trước khi các dependency quan trọng được tạo. Việc lựa chọn `DemoPaymentGateway` hay `SandboxPaymentGateway` diễn ra ở composition root, không phải trong `CheckoutService`.

Khi `AppConfig` bất biến và được truyền qua constructor, những service đang chạy sử dụng cấu hình nhất quán với graph được tạo tại bootstrap. Nếu muốn **reload động** mà không restart, cần thiết kế riêng cách cập nhật cấu hình và tái tạo/switch adapter an toàn. Đổi một nguồn cấu hình sau khi graph được tạo **không tự làm constructor đã chạy cập nhật lại dependency**.

### Parse và validate nên tách trách nhiệm

- **Chuẩn hóa:** chuyển nguồn ngoài thành các canonical keys, phát hiện khóa trùng sau chuẩn hóa.
- **Merge:** giải quyết giá trị theo thứ tự ưu tiên, giữ nguồn thắng và lịch sử.
- **Parse:** chuyển `"5000"` thành `int`, `"sandbox"` thành enum.
- **Validate:** timeout phải nằm trong khoảng cho phép; prefix không được rỗng; mode phải thuộc tập đã định nghĩa.
- **Compose:** chọn implementation cụ thể và tạo các adapter theo typed config.

Tránh kết hợp tất cả vào một constructor của service nghiệp vụ: cách đó làm mã khó kiểm thử và khiến việc truy vết nguyên nhân cấu hình sai trở nên mơ hồ.

## 7. Thực hành Java 17: resolver có ưu tiên và nguồn gốc

Ví dụ dưới đây chạy bằng **Java 17 thuần**, không cần thư viện ngoài, không đọc biến môi trường thật để **kết quả có thể tái lập ở mọi máy**. Các `ConfigSource` mô phỏng defaults, tệp cấu hình, environment và CLI; chúng đã được chuẩn hóa về cùng bộ khóa. Trong ứng dụng thực, mã bootstrap sẽ đọc những nguồn tương ứng rồi tạo `ConfigSource`.

Ứng dụng có ba khóa không nhạy cảm:

- `payment.mode`: `demo` hoặc `sandbox`.
- `payment.timeout-ms`: số nguyên từ `100` đến `30000`.
- `receipt.prefix`: tiền tố biên nhận không rỗng.

Resolver chủ động áp dụng **nguồn sau ghi đè nguồn trước**, từ chối khóa lạ hoặc giá trị rỗng, rồi tạo một `CheckoutConfig` bất biến. Trace chỉ in **ba khóa đã xác định là không nhạy cảm**.

Lưu toàn bộ mã sau vào `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

// Nguồn đã chuẩn hóa tên khóa. Không chứa logic đọc file/env.
record ConfigSource(String name, Map<String, String> values) {
    ConfigSource {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Missing source name");
        }
        values = Map.copyOf(Objects.requireNonNull(values, "values"));
    }
}

// Giá trị được chọn cùng nguồn đã cung cấp nó.
record SelectedValue(String raw, String source) {}

// Cấu hình có kiểu, đã được kiểm tra trước khi tạo dependency.
enum PaymentMode { DEMO, SANDBOX }

record CheckoutConfig(
        PaymentMode mode,
        int timeoutMs,
        String receiptPrefix) {
    CheckoutConfig {
        Objects.requireNonNull(mode, "mode");
        if (timeoutMs < 100 || timeoutMs > 30_000) {
            throw new IllegalArgumentException("Invalid timeout");
        }
        if (receiptPrefix == null || receiptPrefix.isBlank()) {
            throw new IllegalArgumentException("Invalid receipt prefix");
        }
        receiptPrefix = receiptPrefix.trim();
    }
}

record Resolution(
        CheckoutConfig config,
        Map<String, SelectedValue> selected,
        Map<String, List<String>> sourceHistory) {}

final class ConfigResolver {
    static final String MODE = "payment.mode";
    static final String TIMEOUT = "payment.timeout-ms";
    static final String PREFIX = "receipt.prefix";

    private static final Set<String> KNOWN =
            Set.of(MODE, TIMEOUT, PREFIX);

    static Resolution resolve(List<ConfigSource> lowToHigh) {
        Objects.requireNonNull(lowToHigh, "lowToHigh");

        Map<String, SelectedValue> selected = new HashMap<>();
        Map<String, List<String>> history = new HashMap<>();

        // Cấu hình ở phía sau có độ ưu tiên cao hơn.
        for (ConfigSource source : lowToHigh) {
            for (Map.Entry<String, String> e : source.values().entrySet()) {
                String key = e.getKey();
                String raw = e.getValue();

                if (!KNOWN.contains(key)) {
                    throw new IllegalArgumentException(
                            "Unknown key " + key + " from " + source.name());
                }
                if (raw.isBlank()) {
                    throw new IllegalArgumentException(
                            "Blank key " + key + " from " + source.name());
                }

                selected.put(key, new SelectedValue(raw, source.name()));
                history.computeIfAbsent(
                        key, ignored -> new ArrayList<>())
                        .add(source.name());
            }
        }

        String modeText = required(selected, MODE)
                .raw().trim().toLowerCase(Locale.ROOT);

        PaymentMode mode = switch (modeText) {
            case "demo" -> PaymentMode.DEMO;
            case "sandbox" -> PaymentMode.SANDBOX;
            default -> throw new IllegalArgumentException(
                    "Unknown mode from " + required(selected, MODE).source());
        };

        SelectedValue timeoutValue = required(selected, TIMEOUT);
        final int timeout;
        try {
            timeout = Integer.parseInt(timeoutValue.raw().trim());
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "Invalid integer for " + TIMEOUT
                            + " from " + timeoutValue.source(), error);
        }

        String prefix = required(selected, PREFIX).raw();
        CheckoutConfig config =
                new CheckoutConfig(mode, timeout, prefix);

        Map<String, List<String>> frozenHistory = new HashMap<>();
        history.forEach((key, contributors) ->
                frozenHistory.put(key, List.copyOf(contributors)));

        return new Resolution(
                config,
                Map.copyOf(selected),
                Map.copyOf(frozenHistory));
    }

    private static SelectedValue required(
            Map<String, SelectedValue> selected, String key) {
        SelectedValue result = selected.get(key);
        if (result == null) {
            throw new IllegalArgumentException("Missing key: " + key);
        }
        return result;
    }
}

record Order(String id, long amountCents) {
    Order {
        if (id == null || id.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record Receipt(String reference) {}

interface PaymentGateway {
    Receipt charge(Order order);
}

final class DemoPaymentGateway implements PaymentGateway {
    @Override
    public Receipt charge(Order order) {
        return new Receipt("DEMO-" + order.id());
    }
}

final class SandboxPaymentGateway implements PaymentGateway {
    private final int timeoutMs;

    SandboxPaymentGateway(int timeoutMs) {
        this.timeoutMs = timeoutMs;
    }

    @Override
    public Receipt charge(Order order) {
        // Mô phỏng adapter sandbox, không có HTTP/thanh toán thật.
        return new Receipt(
                "SANDBOX-" + order.id() + "-t" + timeoutMs);
    }
}

// Nghiệp vụ chỉ nhận gateway đã được chọn và cấu hình.
final class CheckoutService {
    private final PaymentGateway gateway;
    private final String receiptPrefix;

    CheckoutService(PaymentGateway gateway, String receiptPrefix) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.receiptPrefix =
                Objects.requireNonNull(receiptPrefix, "receiptPrefix");
    }

    String checkout(Order order) {
        Receipt receipt = gateway.charge(
                Objects.requireNonNull(order, "order"));
        return receiptPrefix + ":" + receipt.reference();
    }
}

public class Main {
    // Danh sách cố ý đặt theo độ ưu tiên tăng dần.
    static List<ConfigSource> sources() {
        return List.of(
                new ConfigSource("defaults", Map.of(
                        "payment.mode", "demo",
                        "payment.timeout-ms", "1500",
                        "receipt.prefix", "DEFAULT")),
                new ConfigSource("file:app.properties", Map.of(
                        "payment.timeout-ms", "2500",
                        "receipt.prefix", "FILE")),
                new ConfigSource("env:APP_*", Map.of(
                        "payment.mode", "sandbox",
                        "payment.timeout-ms", "3500")),
                new ConfigSource("cli", Map.of(
                        "payment.timeout-ms", "5000")));
    }

    static PaymentGateway createGateway(CheckoutConfig config) {
        return switch (config.mode()) {
            case DEMO -> new DemoPaymentGateway();
            case SANDBOX ->
                    new SandboxPaymentGateway(config.timeoutMs());
        };
    }

    // CHỈ in các khóa đã biết là không nhạy cảm.
    static void printSafeTrace(Resolution resolution) {
        for (String key : List.of(
                ConfigResolver.MODE,
                ConfigResolver.TIMEOUT,
                ConfigResolver.PREFIX)) {
            SelectedValue winner = resolution.selected().get(key);
            String contributors = String.join(
                    " -> ", resolution.sourceHistory().get(key));
            System.out.println(
                    key + "=" + winner.raw()
                    + " [from=" + winner.source()
                    + "; sources=" + contributors + "]");
        }
    }

    // Composition root: resolve cấu hình trước, sau đó lắp object graph.
    public static void main(String[] args) {
        Resolution resolution = ConfigResolver.resolve(sources());
        CheckoutConfig config = resolution.config();

        PaymentGateway gateway = createGateway(config);
        CheckoutService service =
                new CheckoutService(gateway, config.receiptPrefix());

        printSafeTrace(resolution);
        System.out.println(
                "Checkout=" + service.checkout(new Order("ORD-7", 125_000)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra dự kiến:

~~~text
payment.mode=sandbox [from=env:APP_*; sources=defaults -> env:APP_*]
payment.timeout-ms=5000 [from=cli; sources=defaults -> file:app.properties -> env:APP_* -> cli]
receipt.prefix=FILE [from=file:app.properties; sources=defaults -> file:app.properties]
Checkout=FILE:SANDBOX-ORD-7-t5000
~~~

Trong chương trình minh họa, `env:APP_*` và `cli` chỉ là **tên nguồn mô phỏng**, không phải chương trình đang truy vấn environment hay phân tích `args` thật. Điều này bảo đảm kết quả kiểm thử không phụ thuộc máy đang chạy.

### Đọc rõ cơ chế resolve

1. `ConfigSource` lưu một nguồn cấu hình và giữ bản sao các khóa/giá trị. Các nguồn đã dùng **canonical keys**.
2. `ConfigResolver.resolve` duyệt nguồn từ thấp đến cao; khi khóa đã tồn tại, `selected.put` cập nhật giá trị và nguồn thắng.
3. `history` ghi **tên nguồn đóng góp** theo đúng thứ tự, không giữ trong trace các giá trị bị ghi đè. Đây là cơ sở để giải thích tại sao CLI thắng trên timeout.
4. Sau merge, resolver kiểm tra đủ ba khóa, parse mode thành enum, timeout thành `int` và tạo `CheckoutConfig` có kiểm tra miền giá trị.
5. `Main.createGateway` chọn adapter dựa trên typed config. `CheckoutService` chỉ biết interface `PaymentGateway`; việc tạo adapter không nằm trong nghiệp vụ.
6. `printSafeTrace` dùng **allowlist ba khóa không nhạy cảm** và in nguồn thắng/lịch sử, thay vì duyệt một cách mù quáng toàn bộ cấu hình.

Đây là một **resolver giáo dục**, chưa xử lý mọi trường hợp như nested config, chuẩn hóa environment tự động, file parser, nguồn từ xa, mã hóa secret, reload động, qualifier hay transactional bootstrap. Những phần đó phụ thuộc công nghệ và yêu cầu triển khai.

## 8. Kiểm thử: độ ưu tiên, source trace và fail fast

Chỉ test rằng ứng dụng tạo được `CheckoutService` là chưa đủ. Để đảm bảo cấu hình đúng, ta cần xác minh **giá trị hiệu lực**, **nguồn thắng**, **lịch sử nguồn** và **hành vi khi cấu hình hỏng**.

Lưu đoạn sau vào `ConfigurationTest.java` cùng thư mục với `Main.java`:

~~~java
import java.util.List;
import java.util.Map;

public class ConfigurationTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(Runnable action, String scenario) {
        boolean rejected = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "Must reject: " + scenario);
    }

    public static void main(String[] args) {
        Resolution result = ConfigResolver.resolve(Main.sources());

        check(result.config().mode() == PaymentMode.SANDBOX,
                "Environment should override default mode");
        check(result.config().timeoutMs() == 5_000,
                "CLI should override file and environment timeout");
        check(result.config().receiptPrefix().equals("FILE"),
                "File should override default prefix");

        check(result.selected()
                        .get(ConfigResolver.TIMEOUT).source().equals("cli"),
                "Timeout origin must be CLI");

        check(result.sourceHistory()
                        .get(ConfigResolver.TIMEOUT).equals(List.of(
                            "defaults",
                            "file:app.properties",
                            "env:APP_*",
                            "cli")),
                "Source precedence chain must be preserved");

        // Override mới ở độ ưu tiên cao nhất phải thắng.
        Resolution overridden = ConfigResolver.resolve(List.of(
                new ConfigSource("defaults", Map.of(
                        "payment.mode", "demo",
                        "payment.timeout-ms", "1500",
                        "receipt.prefix", "DEFAULT")),
                new ConfigSource("cli", Map.of(
                        "payment.timeout-ms", "7000"))));
        check(overridden.config().timeoutMs() == 7_000,
                "Last provided value must win");

        // Giá trị sai ở nguồn ưu tiên cao KHÔNG được âm thầm
        // rơi về default.
        expectInvalid(() -> ConfigResolver.resolve(List.of(
                Main.sources().get(0),
                new ConfigSource("bad-cli", Map.of(
                        "payment.timeout-ms", "fast")))),
                "Non-numeric timeout");

        expectInvalid(() -> ConfigResolver.resolve(List.of(
                Main.sources().get(0),
                new ConfigSource("bad-env", Map.of(
                        "payment.timeout-ms", " ")))),
                "Blank override");

        expectInvalid(() -> ConfigResolver.resolve(List.of(
                Main.sources().get(0),
                new ConfigSource("bad-file", Map.of(
                        "payment.tiemout-ms", "5000")))),
                "Unknown key/typo");

        // Thiếu khóa bắt buộc, không có default: báo lỗi.
        expectInvalid(() -> ConfigResolver.resolve(List.of(
                new ConfigSource("partial", Map.of(
                        "payment.mode", "demo")))),
                "Missing required keys");

        // Object graph được lắp theo mode đã resolve.
        CheckoutService service = new CheckoutService(
                Main.createGateway(result.config()),
                result.config().receiptPrefix());

        check(service.checkout(new Order("T-1", 100))
                        .equals("FILE:SANDBOX-T-1-t5000"),
                "Selected adapter must match effective config");

        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java ConfigurationTest.java
java ConfigurationTest
~~~

Đầu ra dự kiến: `PASS`.

Bài kiểm thử không cần file thật, environment thật hay container. Ta kiểm tra chính sách cấu hình như một **hàm chuyển đổi dữ liệu đầu vào thành typed config**, rồi lắp graph riêng. Điều này giảm tính bất định và cho phép tái hiện lỗi cấu hình mà không phải thay đổi môi trường của cả tiến trình.

**Lưu ý:** Đây là kiểm thử bằng cách đọc/đối chiếu logic của ví dụ, không phải bảo đảm rằng Java đã được biên dịch trong quy trình viết tài liệu này. Khi dùng bài thực hành, hãy chạy các lệnh `javac` và `java` trong môi trường Java 17+.

## 9. Cấu hình có tính bảo mật: không đánh đổi khả năng truy vết lấy bí mật

Trong production, một khóa có thể mang token, mật khẩu database, API key hoặc thông tin nhạy cảm. Chính sách truy vết nên thiết kế **trước khi** bật log cấu hình:

- **Không in giá trị nhạy cảm**, kể cả giá trị bị ghi đè. Ghi khóa và tên nguồn là đủ cho nhiều trường hợp.
- **Mặc định redact**, chỉ xuất giá trị với allowlist khóa an toàn. Trong ví dụ, cả ba khóa đều được xác định trước là không nhạy cảm.
- **Không mã hóa secret vào default, mẫu log, stack trace hoặc URL query** chỉ để tiện gỡ lỗi.
- **Tránh log toàn bộ `System.getenv()` hoặc `Map<String,String>`**, vì có thể lộ secret không được dự đoán trước.
- **Giới hạn quyền đọc và vòng đời của secret**; nếu dùng secret store, phép lấy secret và cơ chế rotation phải có owner/lifecycle rõ.
- **Xem xét metadata nguồn**: tên tệp, tenant hoặc đường dẫn secret store đôi khi cũng cần được che.
- **Không nhầm “không log” với “không giữ trong bộ nhớ”**: resolver thực tế vẫn phải truyền giá trị bí mật tới adapter cần nó, nhưng nên giới hạn phạm vi và thời gian nắm giữ.

Nếu cần ghi dấu cấu hình phục vụ điều tra sự cố, có thể ghi ID revision hoặc hash của **bản cấu hình đã được chuẩn hóa và xử lý bí mật phù hợp**. Tránh dùng một hash đơn giản của secret có entropy thấp như bằng chứng công khai, vì nó có thể cho phép đoán secret qua đối chiếu. Cách tạo dấu vết cần được thiết kế theo yêu cầu an ninh cụ thể.

## 10. Cấu hình theo môi trường và profile: tránh “hai nguồn chân lý”

Ví dụ thường gặp là:

~~~text
defaults
   -> application.properties
   -> application-prod.properties
   -> environment
   -> CLI
~~~

Nếu ứng dụng hỗ trợ profile, hãy ghi rõ **khi nào profile được chọn** và **profile được đưa vào thứ tự merge ở vị trí nào**. Profile không nên được chọn muộn bên trong một service đã được tạo, vì khi đó hai service có thể vô tình sử dụng hai bộ cấu hình khác nhau.

Cũng cần tránh:

- Một module tự đọc `application.properties`, module khác tự đọc environment với precedence ngược.
- Một adapter đọc cấu hình động trong mỗi request, nhưng adapter khác giữ snapshot khi bootstrap, không có chính sách đồng bộ.
- Thay đổi tên khóa ở một nơi mà không sửa quy tắc chuẩn hóa ở nơi khác.
- Có nhiều `AppConfig` mutable toàn cục khiến các phần của object graph được tạo ở thời điểm khác nhau nhìn những phiên bản cấu hình khác nhau.

Giải pháp thường là **một pipeline resolution có tài liệu**, cung cấp typed config bất biến cho composition root và một cơ chế báo nguồn gốc được kiểm soát. Nếu cần nhiều cấu hình con, có thể tạo `PaymentConfig`, `StorageConfig`, `NotificationConfig` thay vì một object khổng lồ truyền vào mọi service.

### Reload động có cần thiết không?

Không phải mọi giá trị đều nên reload mà không restart. Có thể phân loại:

| Loại cấu hình | Cách quản lý thường đơn giản hơn |
| --- | --- |
| Chọn adapter hoặc scope | Resolve tại bootstrap; thay đổi cần dựng lại graph hoặc restart có kiểm soát |
| Timeout của client sống lâu | Có thể cần tạo client mới hoặc API cập nhật cấu hình an toàn |
| Cờ tính năng chỉ đọc | Có thể có nguồn cập nhật động, nhưng phải nêu rõ tính nhất quán phiên bản |
| Secret cần rotation | Cần cơ chế refresh/rotation và quyền sở hữu tài nguyên cụ thể |
| Giá trị gắn với request | Truyền như dữ liệu request, không biến thành mutable config toàn cục |

Một DI container không mặc định làm những đối tượng đã được constructor inject tự cấu hình lại khi nguồn bên ngoài thay đổi. Nếu sử dụng dynamic configuration, phải xác định **thời điểm phát hành snapshot**, khả năng rollback, và liệu những instance đang chạy có thể dùng phiên bản cũ an toàn hay không.

## 11. Các lỗi cấu hình lắp ghép thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách phòng tránh |
| --- | --- | --- |
| Timeout runtime không như giá trị trong file | Env/CLI đang ghi đè file | In provenance của khóa an toàn và tài liệu precedence |
| Sửa env nhưng service không đổi | Graph đã được tạo và giữ snapshot | Restart hoặc áp dụng cơ chế reload được thiết kế |
| CLI ghi giá trị sai, ứng dụng dùng default không báo | Resolver im lặng fallback khi parse lỗi | Fail fast cho cấu hình không hợp lệ |
| Một môi trường chạy adapter demo ngoài ý muốn | Default mode không phù hợp với deployment | Bắt buộc chọn mode/adapter trong production |
| Log khởi động lộ token | In toàn bộ cấu hình thô | Redact theo mặc định, dùng allowlist khóa an toàn |
| Hai nguồn có cách viết tên khác nhau không ghi đè | Không chuẩn hóa canonical keys | Chuẩn hóa và kiểm tra xung đột trước merge |
| Cấu hình “trống” bị coi như “vắng mặt” | Dùng `isEmpty` hoặc `getOrDefault` thiếu chính sách | Định nghĩa rõ absent, blank, invalid, removed |
| Lỗi chỉ xuất hiện khi request hiếm gọi tới adapter | Validation/khởi tạo bị trì hoãn | Kiểm tra typed config và wiring sớm; test entry service |
| Scope của dependency thay đổi ngoài ý muốn | Quyết định scope rải rác theo module | Quản lý binding/scope tại composition root |
| Lỗi cấu hình khó tái hiện | Không ghi version nguồn hoặc nguồn thắng | Giữ metadata provenance an toàn cho từng lần khởi động |

Các lỗi ở bảng trên không tự biến mất khi chuyển từ DI thủ công sang Spring, Guice hay một container khác. Công cụ có thể cung cấp cơ chế đọc property và validation, nhưng **chính sách ưu tiên, hợp đồng khóa và yêu cầu bảo mật** vẫn cần được xác định cho ứng dụng cụ thể.

## 12. Checklist áp dụng cấu hình có thể truy vết

1. **Liệt kê canonical keys** và đơn vị đo: ví dụ `timeout-ms` phải dùng mili-giây, tránh nhập nhằng giây và mili-giây.
2. **Phân loại bắt buộc/tùy chọn**: đâu là default an toàn, đâu là secret hoặc lựa chọn môi trường phải khai báo tường minh?
3. **Định nghĩa danh sách nguồn có thứ tự**: viết một sơ đồ hoặc bảng low-to-high, không lệ thuộc vào thứ tự map không rõ.
4. **Chuẩn hóa tên khóa** trước khi merge; phát hiện alias xung đột hoặc typo.
5. **Phân biệt absent và blank**; từ chối giá trị không hợp lệ theo chính sách rõ ràng.
6. **Merge theo từng khóa**, lưu giá trị hiệu lực, nguồn thắng và lịch sử nguồn đóng góp.
7. **Parse thành kiểu Java phù hợp**, kiểm tra miền giá trị, tương quan giữa các khóa và ràng buộc môi trường.
8. **Tạo typed config bất biến** rồi mới chọn adapter, factory, scope và lifecycle tại composition root.
9. **Ghi trace an toàn**: metadata nguồn và revision; redact secret, chỉ log giá trị thuộc allowlist.
10. **Kiểm thử độ ưu tiên và trường hợp lỗi**: các nguồn ghi đè nhau, thiếu khóa bắt buộc, blank, typo, parse sai, value ngoài miền.
11. **Tách unit test và wiring/integration test**: unit test resolver không cần môi trường thật; integration test xác minh adapter thật nhận config đúng.
12. **Ghi nhận chính sách thay đổi cấu hình**: restart, reload, rotation và trách nhiệm đóng/tạo lại tài nguyên.

### Tự kiểm tra

**Tình huống A:** Defaults đặt timeout `1500`, file đặt `2500`, env đặt `3500`, CLI đặt `5000`. Chính sách của bài này dùng timeout nào?

**`5000`**, vì CLI là nguồn cao nhất và cấu hình được merge từ thấp lên cao. Trace cần cho biết CLI là nguồn thắng và các nguồn thấp hơn đã đóng góp.

**Tình huống B:** Env có `APP_PAYMENT_TIMEOUT_MS=" "`, file đặt `2500`. Có nên âm thầm dùng `2500` không?

**Không theo chính sách strict của bài.** Khóa có mặt với giá trị trắng là cấu hình không hợp lệ; resolver từ chối để người vận hành sửa đúng nguồn, không coi nó như không tồn tại.

**Tình huống C:** Application chạy `demo` do default nhưng thực tế là môi trường production. Đã áp dụng DI đúng nên có thể chấp nhận chứ?

**Không.** DI chỉ đảm nhận việc cấp dependency. Mặc định có an toàn hay không thuộc chính sách deployment; production có thể cần bắt buộc cấu hình mode rõ ràng và từ chối khởi động khi thiếu.

**Tình huống D:** Một service tự gọi `System.getenv()` ở mỗi request, service khác dùng typed config inject khi bootstrap. Hệ thống có đang dùng một cấu hình nhất quán không?

**Không được bảo đảm.** Hai service có mô hình thời điểm đọc khác nhau; cần thống nhất snapshot hoặc thiết kế refresh có version và lifecycle rõ ràng.

**Tình huống E:** Muốn biết vì sao một secret nhận giá trị từ secret store thay vì env. Có nên in cả hai giá trị vào log không?

**Không.** Chỉ cần ghi tên khóa, nguồn thắng, chuỗi nguồn và revision được phép công bố; giá trị secret phải được che theo chính sách bảo mật.

## Ghi nhớ

**Giá trị mặc định** phải an toàn và được lựa chọn có chủ đích. **Độ ưu tiên nguồn cấu hình** phải tường minh, ổn định và kiểm thử được. **Khả năng truy vết** phải trả lời được “giá trị hiệu lực đến từ đâu và vì sao” mà không tiết lộ bí mật. Khi cấu hình được chuẩn hóa, resolve, parse và validate trước khi lắp object graph, **composition root** có thể chọn đúng adapter và scope; các service vẫn nhận dependency qua **constructor injection** và không phải biết nguồn cấu hình. DI container có thể tự động hóa nhiều thao tác, nhưng tính đúng và tính an toàn của chính sách cấu hình vẫn là trách nhiệm của thiết kế ứng dụng.
