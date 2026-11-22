# JSR 223 và ranh giới giữa javax.script với engine ngôn ngữ

## 1. JSR 223 là gì?

**JSR 223 (Scripting for the Java Platform)** định nghĩa một API chuẩn để ứng dụng Java tìm, cấu hình và gọi các **scripting engine**. API công khai nằm trong package \`javax.script\`, thuộc module **\`java.scripting\`** từ Java 9.

JSR 223 giải quyết một bài toán tích hợp: mã Java muốn thực thi script mà không phải gắn chặt với API riêng của từng engine. Nó cung cấp hợp đồng để tìm engine, truyền biến, gọi \`eval\`, nhận kết quả và xử lý lỗi.

Điều quan trọng là phân biệt:

- **\`javax.script\`**: bộ interface/lớp phía Java, như \`ScriptEngineManager\`, \`ScriptEngine\`, \`ScriptEngineFactory\`, \`Bindings\`, \`ScriptContext\`, \`Compilable\`, \`Invocable\` và \`ScriptException\`.
- **Engine ngôn ngữ**: phần mềm thực sự phân tích cú pháp, biên dịch/diễn dịch và thực thi JavaScript, Groovy, Python hoặc ngôn ngữ khác.
- **Script source**: đoạn mã của ngôn ngữ mà engine hiểu, không phải mã Java và cũng không phải một phần tự động của JDK.

\`javax.script\` là một **SPI/API trung gian**, không phải bản thân một JavaScript runtime. Việc JDK có module \`java.scripting\` **không có nghĩa** JDK cài sẵn một engine cho mọi ngôn ngữ.

## 2. Kiến trúc và điểm mở rộng

\`\`\`text
Ứng dụng Java / plugin host
          |
          v
ScriptEngineManager  (javax.script)
          |
          +--> ScriptEngineFactory A --> Engine A --> Script
          |
          +--> ScriptEngineFactory B --> Engine B --> Script
          |
          +--> Không có factory phù hợp --> null / thông báo thiếu engine
\`\`\`

Host yêu cầu engine theo tên hoặc đặc điểm, ví dụ \`getEngineByName("groovy")\`. \`ScriptEngineManager\` sử dụng cơ chế service-provider để tìm các \`ScriptEngineFactory\` có thể truy cập qua class loader của nó. Nhà cung cấp engine triển khai contract đó rồi có thể cung cấp thêm API riêng để xử lý ngôn ngữ, classpath, sandbox và hiệu năng.

Phân chia trách nhiệm:

| Phần | Trách nhiệm | Không tự bảo đảm |
|---|---|---|
| \`ScriptEngineManager\` | Khám phá factory, ánh xạ tên/MIME/extension và cung cấp engine | Engine có tồn tại trên runtime |
| \`ScriptEngineFactory\` | Mô tả engine, các tên/extension/MIME được hỗ trợ và tạo engine | Mã script là đáng tin cậy |
| \`ScriptEngine\` | Đánh giá script bằng \`eval\`, quản lý bindings/context | API mọi engine hoàn toàn giống nhau |
| \`Bindings\` | Chứa các giá trị theo tên được đưa vào scope | Đối tượng trong bindings được cô lập |
| \`ScriptContext\` | Điều khiển scope, reader/writer/error writer và thuộc tính cho eval | Context thread-safe hay tự truyền qua executor |
| Engine runtime | Triển khai cú pháp/ngữ nghĩa của ngôn ngữ | Tương thích với Java/JDK và mọi thư viện |

Đây là điểm mở rộng cho hệ thống plugin: host có thể thay engine được cài đặt trong môi trường mà vẫn giữ phần lớn mã tích hợp dựa trên \`javax.script\`. Tuy nhiên, cấu hình, capability và giới hạn bảo mật vẫn phụ thuộc từng engine.

## 3. JSR 223 trên Java 17+: đừng mặc định có JavaScript engine

Trước đây, một số bản JDK cung cấp **Nashorn** làm JavaScript engine. Nashorn bị đánh dấu deprecated ở JDK 11 và **đã bị gỡ khỏi JDK kể từ JDK 15** (JEP 372). Vì vậy trong JDK 17 hoặc JDK 21 thông thường:

\`\`\`java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
\`\`\`

có thể trả về **\`null\`**, thay vì một engine sẵn dùng. API \`javax.script\` vẫn còn; chỉ có implementation cần được cung cấp riêng.

Các engine của bên thứ ba có thể tích hợp JSR 223 nếu họ cung cấp \`ScriptEngineFactory\` thích hợp. Không phải runtime ngôn ngữ nào cũng tự hỗ trợ JSR 223: có engine chỉ cung cấp API nhúng riêng (ví dụ một số API polyglot), và phiên bản hỗ trợ có thể thay đổi.

**Quy tắc vận hành:** kiểm tra danh sách factory thực sự có trên runtime mục tiêu; ghi lại engine name, version và language version; từ chối hoặc báo lỗi rõ khi không có engine yêu cầu.

## 4. Ví dụ Java 17+ chạy được: khám phá engine mà không cần thư viện ngoài

Tạo file **\`ScriptEngineDiscoveryDemo.java\`**:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.Comparator;

public class ScriptEngineDiscoveryDemo {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();

        manager.getEngineFactories().stream()
                .sorted(Comparator.comparing(ScriptEngineFactory::getEngineName))
                .forEach(factory -> System.out.println(
                        factory.getEngineName() + " / " +
                        factory.getEngineVersion() + " / " +
                        factory.getLanguageName()));

        ScriptEngine engine = manager.getEngineByName("JavaScript");
        System.out.println("JavaScript engine available: " + (engine != null));
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac ScriptEngineDiscoveryDemo.java
java ScriptEngineDiscoveryDemo
\`\`\`

Khi chạy trên JDK 17+ **không cài thêm scripting engine**, stdout là:

\`\`\`text
JavaScript engine available: false
\`\`\`

Nếu classpath/module path có engine tương thích được đăng ký, chương trình còn in các dòng factory trước đó và kết quả có thể chuyển thành \`true\`. Ví dụ không giả định rằng tên engine bên thứ ba luôn là \`JavaScript\`.

Trong named JPMS module sử dụng \`javax.script\`, phải khai báo:

\`\`\`java
module com.example.script.host {
    requires java.scripting;
}
\`\`\`

Đây là đoạn descriptor minh họa; tên module thực tế phụ thuộc dự án.

## 5. Truyền dữ liệu và gọi eval

Khi đã có một \`ScriptEngine\` hợp lệ, host có thể truyền dữ liệu bằng \`Bindings\`:

\`\`\`java
// Đoạn tích hợp; giả định manager tìm thấy engine phù hợp.
ScriptEngine engine = manager.getEngineByName("some-language");
if (engine == null) {
    throw new IllegalStateException("Scripting engine is unavailable");
}

Bindings values = engine.createBindings();
values.put("customerName", "Lan");
Object result = engine.eval("expression_using_customerName", values);
\`\`\`

Chuỗi script ở trên chỉ là **placeholder cú pháp** để chỉ ra điểm tích hợp; ngữ pháp thật phải phù hợp với ngôn ngữ của engine. \`eval(script, bindings)\` dùng bindings cho phạm vi ENGINE_SCOPE của lần thực thi; điều này khác với việc sửa mọi biến toàn cục của engine.

\`Bindings\` chứa **Java object references**, không tự serialize/sao chép hay giới hạn quyền. Nếu đưa vào một object như \`databaseClient\`, script có thể truy cập nhiều hơn dự kiến tùy khả năng interop của engine. Với mã script thiếu tin cậy, không coi bindings là biện pháp sandbox; cần chính sách host access và mô hình cô lập thực sự.

\`ScriptContext\` có scope:

- \`ENGINE_SCOPE\`: bindings gần với engine/eval, thường dành cho biến riêng.
- \`GLOBAL_SCOPE\`: bindings toàn cục nếu được cấu hình, có thể dùng chung qua nhiều engine/context.

Phân biệt scope là quan trọng khi chạy đa tenant. Không chia sẻ mutable \`Bindings\` giữa request trừ khi engine bảo đảm thread safety phù hợp và ứng dụng có đồng bộ hóa/cô lập rõ ràng.

## 6. Các capability tùy chọn của engine

Hợp đồng cơ bản không bảo đảm engine hỗ trợ mọi tính năng. Hai interface quan trọng:

**\`Compilable\`** cho phép biên dịch trước script để sử dụng nhiều lần:

\`\`\`java
// Đoạn tích hợp: engine đã có và script là cú pháp hợp lệ.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled =
            compilable.compile(script);
    Object result = compiled.eval();
}
\`\`\`

Hiệu năng và khả năng dùng lại \`CompiledScript\` tùy engine, đặc biệt khi có context/bindings mutable.

**\`Invocable\`** cung cấp cách gọi function hoặc method do script định nghĩa:

\`\`\`java
// Đoạn tích hợp: function "calculate" đã được eval và tồn tại.
if (engine instanceof javax.script.Invocable invocable) {
    Object value = invocable.invokeFunction("calculate", 5);
}
\`\`\`

Không có \`Compilable\` hoặc \`Invocable\` không phải engine lỗi; đó là capability tùy chọn. Host nên xác minh capability cần thiết khi khởi tạo, thay vì chờ đến lúc request thực tế mới thất bại.

\`ScriptEngineFactory.getParameter("THREADING")\` có thể cung cấp thông tin mô hình threading của engine theo contract JSR 223. Giá trị \`null\` không nên được hiểu là engine thread-safe. Ngay cả khi engine công bố khả năng concurrency, host vẫn cần hiểu trạng thái context và các Java object được truyền vào.

## 7. Service provider discovery và class loader

Một engine JSR 223 thường công bố implementation của interface:

\`\`\`java
javax.script.ScriptEngineFactory
\`\`\`

Trong JAR classpath, việc khám phá có thể dựa trên metadata service provider tại:

\`\`\`text
META-INF/services/javax.script.ScriptEngineFactory
\`\`\`

Với named JPMS module, provider có thể khai báo:

\`\`\`java
module com.example.language.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.language.EngineFactory;
}
\`\`\`

Đây là module descriptor minh họa, chỉ biên dịch khi có class factory thực. \`ScriptEngineManager\` cung cấp constructor nhận \`ClassLoader\` để điều khiển phạm vi khám phá, nhưng không tự tải các JAR mới chưa được đưa vào class loader/layer phù hợp.

Trong plugin host có nhiều class loader, cần tránh:

- Engine JAR không nằm trong phạm vi nhìn thấy của loader dùng để tạo manager.
- Host và plugin dùng API bridge/loại class không tương thích do duplicate dependency và class identity.
- Plugin loader được giữ lại bởi instance engine, script callback, thread hoặc cached compiled script sau khi thay phiên bản.
- Nhầm \`ServiceLoader.load(layer, service)\` với API \`ScriptEngineManager\`; manager không có overload trực tiếp nhận \`ModuleLayer\`. Nếu kiến trúc yêu cầu layer, phải thiết kế cách discovery/adapter phù hợp và tôn trọng quy tắc của JPMS.

Đối với thay engine động, nên kiểm tra artifact trước, tạo loader/layer có lifecycle, khám phá factory, kiểm tra capability rồi mới công bố engine cho request mới.

## 8. Ranh giới thực tế giữa javax.script và engine

Hãy coi \`javax.script\` là **cổng giao tiếp chung** và engine là **thành phần triển khai có thể thay thế**, nhưng hợp đồng chung chỉ mô tả một tập thao tác tương đối nhỏ. Những phần thường phụ thuộc engine bao gồm:

| Chủ đề | API chung hỗ trợ đến đâu? | Phụ thuộc engine |
|---|---|---|
| Phân tích script | \`eval\` và \`ScriptException\` | Cú pháp, thư viện, semantics |
| Biến | \`Bindings\`, \`ScriptContext\` | Cách map giá trị Java sang giá trị script |
| Biên dịch | \`Compilable\` nếu hỗ trợ | Cache, tối ưu hóa, lifecycle |
| Gọi hàm | \`Invocable\` nếu hỗ trợ | Mapping tham số và exception |
| Threading | Factory metadata về concurrency | Thread safety thực tế, khả năng chạy song song |
| Sandbox | Không có cơ chế sandbox chuẩn xuyên engine | Host access, filesystem/network/process permissions |
| Timeout | Không có contract timeout/cancel phổ quát cho mọi engine | Interruption, resource limits và quota |
| Module/classpath | Service discovery theo Java | Dependency, language modules, class loader |

Vì vậy hai engine cùng hỗ trợ JSR 223 không chắc cho kết quả giống nhau khi chạy một script bất kỳ. Khi chuyển engine, phải kiểm thử cú pháp, API language, conversion, exception behavior, security policy và performance.

## 9. Xử lý lỗi theo từng ranh giới

Một host nên phân loại lỗi theo giai đoạn:

1. **Discovery:** không có factory tên cần tìm, hoặc provider cấu hình sai. \`getEngineByName(...)\` có thể trả \`null\`.
2. **Initialization:** engine phụ thuộc thư viện thiếu, lỗi configuration, class loading hoặc service provider.
3. **Compilation/parsing:** \`ScriptException\` hoặc lỗi ngôn ngữ khi script sai cú pháp.
4. **Execution:** lỗi runtime script, dữ liệu không hợp lệ, interop Java hoặc tài nguyên hết.
5. **Lifecycle:** script callback, thread, resource hoặc class loader còn sống sau khi ngừng plugin.

Không bắt mọi lỗi rồi coi là “script syntax error”. Mã engine có thể có side effect trước khi exception xảy ra; retry không tự động an toàn. Log cần giữ engine identity/version, script ID hoặc hash, request ID và stage; tránh log script chứa bí mật hoặc dữ liệu nhạy cảm.

## 10. An toàn khi cho chạy script trong ứng dụng

JSR 223 là API thực thi code. Khi script do bên thứ ba hoặc người dùng cung cấp, rủi ro phụ thuộc mức truy cập của engine:

- **Không mặc định sandbox:** JSR 223 không có cấu hình chuẩn để hạn chế file, network, reflection, thread hoặc host object.
- **Không mở toàn bộ object graph của host:** chỉ cung cấp DTO/operation hẹp, tránh đưa thẳng database/credential/session vào bindings.
- **Giới hạn tài nguyên:** có timeout, memory/CPU quota và cancellation thực sự được engine hỗ trợ; với mã thiếu tin cậy, ưu tiên chạy process/container riêng.
- **Chặn mã chưa được kiểm tra:** xác minh nguồn, phiên bản, chữ ký/integrity của engine; giới hạn ai có quyền nạp script.
- **Quản lý tenant isolation:** mỗi execution context cần có ownership rõ. Engine instance có thể giữ global state, nên chọn mô hình pooling/context riêng phù hợp.
- **Quan sát và rollback:** ghi audit việc thực thi, version script, kết quả và lỗi, đồng thời tránh thực thi lại side effect không có idempotency.

Một class loader riêng hoặc module layer riêng **không thay thế được ranh giới bảo mật của hệ điều hành** với code không đáng tin.

## 11. Khi nào dùng JSR 223, khi nào dùng API riêng?

**Dùng JSR 223 khi:** host cần tích hợp đơn giản và muốn hỗ trợ nhiều engine có implementation tương thích; thao tác chủ yếu là \`eval\`, bindings, compile/invoke tùy chọn; khả năng thay thế backend có giá trị hơn tính năng nâng cao.

**Dùng API riêng của engine khi:** cần polyglot interop sâu, cấu hình host access chính xác, isolate/context nâng cao, giới hạn resource hay debug/profiling đặc thù. Khi đó có thể thiết kế adapter để giữ contract ứng dụng ổn định mà không ép mọi khả năng vào \`ScriptEngine\`.

Mô hình plugin thường hữu ích:

\`\`\`text
Host ScriptExecutor interface
    |
    +--> Jsr223ScriptExecutor
    |       |
    |       +--> ScriptEngine A
    |       +--> ScriptEngine B
    |
    +--> NativeEngineAdapter
            |
            +--> Engine-specific API
\`\`\`

Các adapter công bố capability thực tế để host chọn, thay vì giả định mọi engine giống nhau.

## 12. Lỗi phổ biến và checklist

Những nhầm lẫn thường gặp:

- Có \`javax.script\` nên nghĩ Java 17 luôn có JavaScript runtime.
- Gọi \`getEngineByName(...).eval(...)\` mà không kiểm tra kết quả \`null\`.
- Coi mọi engine là thread-safe hoặc mọi \`Bindings\` tự cô lập.
- Tin rằng \`ScriptException\` bao phủ mọi failure của provider/engine.
- Giả định một script chạy giống hệt giữa nhiều engine/language version.
- Đưa credential hoặc đối tượng quyền cao vào bindings khi chạy script không tin cậy.
- Không kiểm tra \`Compilable\`/\`Invocable\` trước khi ép kiểu.
- Không quản lý class loader hoặc context khi hot reload scripting plugin.
- Coi \`javax.script\` là sandbox hoặc có timeout chuẩn tích hợp.

Checklist áp dụng: xác định engine cần dùng; kiểm tra khả năng tìm thấy; chốt engine/language version; xác minh capability; định nghĩa rõ bindings/context và threading; đặt security boundary; giới hạn resource; quản lý lifecycle; kiểm thử output và lỗi với engine thực tế trong runtime mục tiêu.

**Ghi nhớ:** \`javax.script\` là **API tích hợp JSR 223** của Java, còn engine là **runtime ngôn ngữ do một implementation cung cấp**. Muốn chạy script phải có engine tương thích và chính sách thực thi rõ ràng; module \`java.scripting\` một mình không đủ.
