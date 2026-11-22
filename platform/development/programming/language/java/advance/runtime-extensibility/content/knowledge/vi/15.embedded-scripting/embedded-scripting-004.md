# Xử lý getEngineByName trả về null và engine không được cài đặt

## 1. Hiểu đúng kết quả null

Trong JSR 223, \`javax.script.ScriptEngineManager\` là bộ quản lý và khám phá **scripting engine**. Lệnh:

\`\`\`java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
\`\`\`

trả về một \`ScriptEngine\` nếu manager tìm được factory đã đăng ký hỗ trợ tên được yêu cầu; nếu không tìm được, API **trả về \`null\`**. Đây là một kết quả bình thường của quá trình tìm kiếm, không phải lúc nào cũng là exception hay bằng chứng script có lỗi.

Cần phân biệt ba tình huống:

1. **Không có engine phù hợp:** không tìm được factory công bố tên đó. \`getEngineByName\` trả về \`null\`.
2. **Có factory nhưng lỗi khởi tạo:** dependency, class loading hoặc mã factory lỗi. Có thể xuất hiện exception hoặc lỗi khác tùy implementation; không nên quy mọi lỗi về \`null\`.
3. **Có engine nhưng script không chạy được:** \`eval\` có thể phát sinh \`ScriptException\`, hoặc runtime có lỗi/capability không hỗ trợ. Đây là lỗi thực thi, không phải lỗi khám phá.

Nếu gọi \`engine.eval(...)\` ngay sau khi nhận \`null\`, Java sẽ ném \`NullPointerException\`. Thay vì để lỗi lan truyền khó hiểu, host phải kiểm tra engine trước và trả thông báo hành động rõ ràng.

## 2. Vì sao Java 17+ có thể không tìm thấy JavaScript engine?

Module \`java.scripting\` có các API JSR 223 như \`ScriptEngineManager\`, \`ScriptEngine\`, \`ScriptEngineFactory\`, \`Bindings\` và \`ScriptException\`; **module này không cung cấp bắt buộc một implementation cho JavaScript hoặc mọi ngôn ngữ khác**.

Lịch sử quan trọng:

- JDK 8 đến JDK 14 từng cung cấp Nashorn JavaScript engine trên các bản JDK tương ứng.
- Nashorn bị đánh dấu deprecated ở JDK 11.
- **Nashorn bị loại khỏi JDK từ JDK 15** (JEP 372). Vì vậy một JDK 17 hoặc JDK 21 thông thường không có JavaScript engine JSR 223 được cài sẵn chỉ vì có JDK.

Tên \`JavaScript\`, \`js\` hoặc \`ECMAScript\` là **alias do factory công bố**. Một engine bên thứ ba có thể công bố alias khác hoặc chỉ tích hợp qua API riêng, không qua JSR 223. Việc jar tồn tại trên ổ đĩa chưa đủ: engine phải được khai báo đúng và được class loader/module layer liên quan nhìn thấy.

## 3. Mẫu xử lý chuẩn: kiểm tra null trước khi eval

Một đoạn tích hợp đơn giản:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class SimpleScriptCall {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");

        if (engine == null) {
            System.err.println(
                "JavaScript engine unavailable. Install a compatible JSR 223 engine."
            );
            return;
        }

        Object result = engine.eval("1 + 2");
        System.out.println(result);
    }
}
\`\`\`

Lưu thành **\`SimpleScriptCall.java\`**, chạy:

\`\`\`bash
javac SimpleScriptCall.java
java SimpleScriptCall
\`\`\`

Trên JDK 17+ không có engine JavaScript, stderr là:

\`\`\`text
JavaScript engine unavailable. Install a compatible JSR 223 engine.
\`\`\`

Chương trình không cố thực thi script khi chưa có engine. Nếu có engine phù hợp thì cách diễn giải \`1 + 2\` và kiểu giá trị trả về do engine quyết định. Ví dụ này không dựa vào một engine cụ thể và không tuyên bố mọi môi trường đều in cùng một kết quả khi có engine.

Trong ứng dụng production, nên thay \`return\` bằng một **lỗi cấu hình có mã rõ ràng** (ví dụ \`SCRIPT_ENGINE_UNAVAILABLE\`) hoặc chuyển hệ thống sang trạng thái degraded nếu tính năng script chỉ là tùy chọn. Không tự ý chọn engine khác có semantics không tương đương.

## 4. Liệt kê factory có thật để chẩn đoán

Đừng đoán tên engine. Hãy liệt kê các factory mà manager nhìn thấy và các alias được hỗ trợ.

Ví dụ Java 17+ hoàn chỉnh, file **\`ScriptEngineDiagnostics.java\`**:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.Comparator;
import java.util.List;

public final class ScriptEngineDiagnostics {
    private static final String REQUESTED = "JavaScript";

    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        List<ScriptEngineFactory> factories =
                manager.getEngineFactories().stream()
                        .sorted(Comparator.comparing(
                                ScriptEngineFactory::getEngineName))
                        .toList();

        System.out.println("Factory count: " + factories.size());
        for (ScriptEngineFactory factory : factories) {
            System.out.println("Engine: " + factory.getEngineName());
            System.out.println("  Version: " + factory.getEngineVersion());
            System.out.println("  Language: " + factory.getLanguageName());
            System.out.println("  Aliases: " + factory.getNames());
        }

        ScriptEngine engine = manager.getEngineByName(REQUESTED);
        if (engine == null) {
            System.out.println("Lookup JavaScript: unavailable");
        } else {
            ScriptEngineFactory factory = engine.getFactory();
            System.out.println(
                    "Lookup JavaScript: " + factory.getEngineName());
        }
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac ScriptEngineDiagnostics.java
java ScriptEngineDiagnostics
\`\`\`

Trên JDK 17+ sạch, không có engine bên ngoài, stdout là:

\`\`\`text
Factory count: 0
Lookup JavaScript: unavailable
\`\`\`

Khi đã cài engine JSR 223, số lượng factory và các tên/phiên bản phụ thuộc vào thư viện và môi trường. Việc \`getEngineFactories()\` chứa một factory không bảo đảm mọi \`getEngineByName\` sẽ thành công: phải đối chiếu chính xác danh sách \`getNames()\` với tên yêu cầu và kiểm tra lỗi khi factory tạo engine.

### Bảng diễn giải kết quả

| Kết quả | Ý nghĩa có khả năng nhất | Việc cần làm |
|---|---|---|
| \`Factory count: 0\` | Manager không thấy factory nào | Kiểm tra runtime dependencies, class loader và service registration |
| Có factory, thiếu alias cần dùng | Tên tra cứu không được công bố | Dùng alias đã công bố, cấu hình lại tên, tránh đoán |
| Có alias nhưng tạo engine lỗi | Factory/engine có vấn đề runtime | Xem stack trace, dependency, khả năng tương thích |
| Có engine, eval lỗi | Lỗi cú pháp, dữ liệu hoặc engine | Chẩn đoán riêng \`ScriptException\` và nguyên nhân |
| Dev hoạt động, production không | Classpath/module path/packaging khác | So sánh artifact thực tế và launcher |

## 5. Engine được cài thế nào để manager tìm thấy?

Một implementation JSR 223 cần cung cấp \`ScriptEngineFactory\` và công bố nó qua cơ chế provider thích hợp.

**Trên classpath**, thư viện engine thường có:

\`\`\`text
META-INF/services/javax.script.ScriptEngineFactory
\`\`\`

Tệp service chứa tên đầy đủ của lớp factory. JAR engine cùng các dependency cần có mặt trong classpath được class loader sử dụng nhìn thấy.

**Trong explicit module**, provider có thể công bố bằng \`module-info.java\`:

\`\`\`java
module com.example.script.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.engine.MyEngineFactory;
}
\`\`\`

Đây là descriptor minh họa; các class thực tế cần được triển khai để biên dịch và chạy. Module tiêu thụ API cần \`requires java.scripting;\`.

Một số thư viện hoặc engine ngôn ngữ có thể **không hỗ trợ JSR 223**, dù có API nhúng riêng. Cài runtime ngôn ngữ nói chung không bảo đảm \`ScriptEngineManager\` nhìn thấy nó. Phải kiểm tra tài liệu đúng phiên bản của engine, artifact bridge JSR 223 (nếu có), các dependency đi kèm và version JDK hỗ trợ.

**Với Gradle/Maven**, thêm dependency vào build không đủ nếu packaging/runtime bỏ sót dependency đó. Cần kiểm tra classpath của process thực tế, fat JAR shading, việc merge tệp \`META-INF/services\`, module-path và \`jlink\` image. Nếu tạo bản runtime tùy chỉnh bằng \`jlink\`, phải bảo đảm module API và module provider được đưa vào/bound đúng cách.

## 6. Class loader, TCCL và ServiceLoader

\`ScriptEngineManager()\` mặc định sử dụng class loader gắn với ngữ cảnh thread để khám phá các engine theo cơ chế service provider. Nếu host chạy trong container/plugin framework, thread context class loader (TCCL) có thể khác class loader nạp application hoặc engine JAR.

Có constructor nhận loader tường minh:

\`\`\`java
ClassLoader engineLoader = /* class loader chứa engine đã xác thực */;
ScriptEngineManager manager = new ScriptEngineManager(engineLoader);
\`\`\`

Đây là đoạn minh họa; host phải tự xây dựng \`engineLoader\` đúng và giữ vòng đời hợp lệ. Việc dùng loader tường minh giúp tránh phụ thuộc vào TCCL của thread gọi, nhưng không tự tải JAR ở đường dẫn tùy ý. Nếu engine JAR được đặt trong thư mục plugin sau khi process đã khởi chạy, cần đưa nó vào lớp loader/layer mới theo thiết kế plugin manager; \`getEngineByName\` không tự quét thư mục file.

Khi khắc phục lỗi discovery, ghi lại:

- Class loader được truyền vào \`ScriptEngineManager\` và TCCL thực tế.
- Vị trí engine JAR, các dependency và tệp service provider.
- Module path và module graph nếu dùng JPMS.
- Phiên bản Java/JDK, phiên bản engine, alias factory và package relocation/shading.
- Log lỗi \`ServiceLoader\` hoặc factory khởi tạo không thành công.

Trong môi trường module layer, đừng mặc định \`ScriptEngineManager\` có overload nhận \`ModuleLayer\`; API của nó chỉ nhận \`ClassLoader\` hoặc dùng mặc định. Thiết kế discovery trong JPMS phải nhất quán với nơi module engine được resolve và loaded.

## 7. Đừng dùng tên engine làm cơ chế kiểm tra capability duy nhất

Engine tồn tại chưa đủ để đáp ứng nhu cầu của ứng dụng. Sau khi tìm được, host nên kiểm tra:

1. **Engine/language version:** phù hợp với script đang lưu trữ không?
2. **\`Compilable\`:** cần compile/cache script thì engine có hỗ trợ không?
3. **\`Invocable\`:** cần gọi hàm sau eval thì engine có hỗ trợ không?
4. **Threading:** có thể chia sẻ instance giữa request không, hay cần tạo engine/context riêng?
5. **Host interop và bảo mật:** script có thể truy cập đối tượng Java nào, có giới hạn quyền thích hợp không?
6. **Giới hạn tài nguyên:** có timeout, cancellation, memory/CPU bound khả dụng cho engine cụ thể không?

Ví dụ kiểm tra capability:

\`\`\`java
// Đoạn tích hợp, giả định engine != null.
if (!(engine instanceof javax.script.Compilable)) {
    throw new IllegalStateException("Engine does not support compilation");
}
if (!(engine instanceof javax.script.Invocable)) {
    throw new IllegalStateException("Engine does not support function invocation");
}
\`\`\`

Chỉ ép kiểu khi capability thực sự được triển khai. \`ScriptEngineFactory.getParameter("THREADING")\` có thể cho biết concurrency contract của engine theo JSR 223, nhưng vẫn cần đánh giá \`Bindings\`, \`ScriptContext\` và object Java chia sẻ.

## 8. Thiết kế fail-fast hoặc degrade có kiểm soát

Tùy vai trò của script đối với nghiệp vụ:

**Tính năng bắt buộc:** host nên kiểm tra engine khi khởi động và từ chối đánh dấu ứng dụng là sẵn sàng nếu engine bị thiếu. Tạo thông báo kèm tên yêu cầu, engine hiện có và cách cài/configure đúng.

**Tính năng tùy chọn:** có thể vô hiệu hóa feature liên quan và trả phản hồi rõ ràng như “Scripting unavailable”, trong khi các chức năng không phụ thuộc script vẫn phục vụ bình thường.

**Nhiều engine được hỗ trợ:** chỉ fallback khi có danh sách engine thay thế được phê duyệt và đã kiểm thử semantics tương đương. Không thử mọi factory một cách ngẫu nhiên vì ngôn ngữ, cách chuyển kiểu và quyền host access có thể khác nhau.

Mẫu phương thức khởi tạo có lỗi tường minh:

\`\`\`java
// Đoạn tích hợp; caller chịu trách nhiệm cung cấp manager.
static javax.script.ScriptEngine requireEngine(
        javax.script.ScriptEngineManager manager, String name) {
    javax.script.ScriptEngine engine = manager.getEngineByName(name);
    if (engine == null) {
        throw new IllegalStateException(
                "Required JSR 223 engine is unavailable: " + name);
    }
    return engine;
}
\`\`\`

Tách **lỗi cấu hình không có engine** khỏi **\`ScriptException\` khi eval** và lỗi dependency/runtime. Việc phân loại này giúp vận hành xử lý đúng gốc và tránh retry một thao tác không thể thành công cho đến khi cài engine.

## 9. Kiểm tra packaging và môi trường chạy

Một ứng dụng chạy được trong IDE nhưng không chạy khi đóng gói thường có khác biệt giữa các môi trường:

- Engine JAR chỉ nằm trong development/test dependency.
- File \`META-INF/services/javax.script.ScriptEngineFactory\` bị mất hoặc bị ghi đè khi tạo fat JAR.
- Dependency transitive của engine bị loại bỏ hoặc xung đột phiên bản.
- Named module không được resolve hoặc module path khác classpath.
- Custom runtime image thiếu module/provider.
- Class loader isolation hoặc TCCL khiến manager không nhìn thấy engine.
- Phiên bản JDK thay đổi: dự án dựa trên Nashorn có sẵn ở JDK cũ nhưng production dùng JDK mới.

Một chẩn đoán hữu ích là chạy \`ScriptEngineDiagnostics\` **bên trong đúng process/runtime image** của ứng dụng, hoặc tích hợp tương đương vào health diagnostics. Chỉ xem dependency tree lúc build không xác nhận được runtime discovery thực tế.

Với plugin host, nên bổ sung automated smoke test: sau khi deploy artifact cuối cùng, tìm engine bằng tên mong muốn, in metadata phiên bản, thực thi một script kiểm tra không có side effect rồi đóng/giải phóng tài nguyên đúng contract engine.

## 10. Bảo mật: có engine không có nghĩa an toàn để eval

Không nên tự động tải engine từ nguồn không được tin cậy chỉ để làm \`getEngineByName\` hết trả \`null\`. Engine và script đều là code thực thi. JSR 223 không cung cấp sandbox thống nhất cho mọi engine.

Một ứng dụng mở rộng lúc chạy cần:

- Xác minh nguồn gốc, phiên bản và tính toàn vẹn của engine artifact.
- Giới hạn người có quyền cài engine và nạp script.
- Không cung cấp database client, credential, filesystem hoặc đối tượng host có quyền cao vào \`Bindings\` của script không tin cậy.
- Quản lý execution timeout/resource theo khả năng engine; với script thiếu tin cậy, ưu tiên cô lập tiến trình/container.
- Ghi log engine identity, script ID, kết quả và lỗi mà không lộ nội dung nhạy cảm.
- Có cơ chế rollback và ngừng nhận request nếu engine mới không đáp ứng hợp đồng.

Class loader riêng và module layer riêng giúp tổ chức code, **không phải ranh giới bảo mật đủ mạnh** cho mã độc trong cùng JVM.

## 11. Những lỗi thường gặp

- Gọi \`engine.eval\` khi chưa kiểm tra \`engine != null\`.
- Tưởng \`java.scripting\` chứa JavaScript runtime mặc định trên JDK 17+.
- Đổi tên tra cứu ngẫu nhiên mà không đọc \`factory.getNames()\`.
- Chỉ cài engine JAR nhưng bỏ sót các dependency hoặc service registration.
- Kiểm tra trong IDE thay vì artifact/runtime deployment thật.
- Không nhận ra sự khác nhau giữa classpath, module path và class loader của manager.
- Bắt \`NullPointerException\` thay cho xử lý thiếu engine rõ ràng.
- Sử dụng một engine có ngôn ngữ/capability không tương thích như fallback âm thầm.
- Chia sẻ engine/context giữa luồng và tenant khi chưa xác minh thread safety.
- Coi việc tìm được engine là cho phép chạy script thiếu tin cậy.

## 12. Checklist xử lý khi getEngineByName trả null

1. In \`getEngineFactories()\` và danh sách \`getNames()\` của từng factory.
2. Kiểm tra tên yêu cầu và alias đã công bố.
3. Xác nhận engine bridge JSR 223 đúng phiên bản đã được cài trong runtime.
4. Kiểm tra JAR, transitive dependencies và service provider declaration.
5. Xác minh manager dùng class loader nhìn thấy engine; kiểm tra TCCL/JPMS.
6. Kiểm tra môi trường triển khai cuối cùng (IDE, container, custom runtime).
7. Khi có engine, kiểm tra \`Compilable\`, \`Invocable\`, threading và security policy cần thiết.
8. Chọn fail-fast hoặc degraded mode theo mức độ bắt buộc của tính năng.
9. Bổ sung smoke test và thông báo lỗi có hành động khắc phục rõ ràng.

**Ghi nhớ:** \`getEngineByName(...) == null\` nghĩa là **manager không tìm được engine thích hợp trong phạm vi discovery hiện có**. Cách xử lý đúng là kiểm tra factory, alias, class loader và packaging, rồi chủ động cài một implementation JSR 223 tương thích nếu tính năng yêu cầu—không mặc định engine có trong JDK.
