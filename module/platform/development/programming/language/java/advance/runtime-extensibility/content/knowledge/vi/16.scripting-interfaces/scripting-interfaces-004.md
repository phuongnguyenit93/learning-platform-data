# Kiểm tra Compilable và tái sử dụng CompiledScript với engine tương ứng

## 1. Vấn đề: có phải ScriptEngine nào cũng biên dịch trước được?

Trong JSR 223 (\`javax.script\`), mọi \`ScriptEngine\` cung cấp khả năng đánh giá script thông qua \`eval(...)\`, nhưng **không phải engine nào cũng hỗ trợ biên dịch trước**. Khả năng này được công bố bằng interface tùy chọn \`javax.script.Compilable\`.

Khi một script được thực thi nhiều lần, chẳng hạn quy tắc định giá, chuyển đổi dữ liệu hoặc xử lý sự kiện của plugin, việc phân tích cú pháp hay chuẩn bị chương trình lặp đi lặp lại có thể tốn tài nguyên. Một engine hỗ trợ \`Compilable\` cho phép tạo đối tượng \`CompiledScript\` để thực thi lại theo các \`Bindings\` hoặc \`ScriptContext\` phù hợp.

Tuy nhiên, **compile không đồng nghĩa với biên dịch Java thành class file**, và không phải engine nào cũng tạo machine code. Cụ thể, cách compile, cache, tối ưu hóa và thread safety đều do implementation quyết định.

Hai hợp đồng chính:

\`\`\`java
public interface Compilable {
    CompiledScript compile(String script) throws ScriptException;
    CompiledScript compile(java.io.Reader script) throws ScriptException;
}
\`\`\`

\`\`\`java
public abstract class CompiledScript {
    public abstract Object eval(ScriptContext context) throws ScriptException;
    public Object eval(Bindings bindings) throws ScriptException;
    public Object eval() throws ScriptException;
    public abstract ScriptEngine getEngine();
}
\`\`\`

\`getEngine()\` cho biết engine đã tạo ra đối tượng compiled script. Đây là mối liên hệ quan trọng: **CompiledScript thuộc về engine đã compile nó**, không phải một định dạng bytecode chung để tùy ý chuyển sang engine khác.

## 2. Kiểm tra capability trước khi ép kiểu

Cách kiểm tra đúng trên Java 17+:

\`\`\`java
ScriptEngine engine = manager.getEngineByName("some-language");

if (engine == null) {
    throw new IllegalStateException("No matching JSR 223 engine");
}

if (!(engine instanceof Compilable compilable)) {
    throw new IllegalStateException("Engine does not implement Compilable");
}

CompiledScript compiled = compilable.compile(scriptSource);
\`\`\`

Đoạn này là mã tích hợp; \`manager\`, \`scriptSource\` và engine tương thích phải có sẵn. Có hai nhánh lỗi khác nhau:

- **Không có engine**: \`getEngineByName(...)\` trả \`null\`; cần kiểm tra dependency, alias, service registration và class loader.
- **Có engine nhưng không hỗ trợ \`Compilable\`**: không được ép kiểu cưỡng bức; có thể dùng \`eval\` trực tiếp hoặc từ chối feature nếu compile là bắt buộc.

Một engine triển khai \`Compilable\` vẫn có thể ném \`ScriptException\` khi mã nguồn sai cú pháp hoặc không được engine chấp nhận. Ngoài ra, các lỗi từ implementation hoặc class loading phải được ghi nhận riêng theo nguồn gốc thực tế.

## 3. Biên dịch một lần và chạy nhiều lần

Chu trình cơ bản:

\`\`\`text
Script source + engine đã xác thực
              |
              v
       instanceof Compilable?
          /         \
       không         có
        |             |
  eval trực tiếp   compile(source)
  hoặc từ chối        |
                      v
                CompiledScript
                   /   |   \
                  v    v    v
               eval  eval  eval
             context A/B/C
\`\`\`

Cách này hữu ích khi một tập script tương đối ổn định được gọi nhiều lần. Tính khả thi phải được đo bằng benchmark trong engine thực tế: compile có thể nhanh hoặc chậm, object compiled có thể chứa trạng thái hoặc tài nguyên đáng kể, và một số engine đã có cache riêng khi gọi \`eval\`.

Sự tách biệt cần nhớ:

- **Compile** chuẩn bị biểu diễn có thể tái thực thi của script.
- **Eval** thực sự thực thi script và có thể tạo side effect.
- **Bindings/ScriptContext** cung cấp đầu vào, state và I/O của lần thực thi.
- **Engine** vẫn là môi trường/ngữ nghĩa cụ thể. Một compiled script không sống độc lập với engine chỉ vì host giữ reference tới nó.

## 4. Bindings và ScriptContext khi thực thi lại

JSR 223 cung cấp ba dạng thường dùng:

\`\`\`java
compiled.eval();
compiled.eval(bindings);
compiled.eval(context);
\`\`\`

Ý nghĩa:

1. **\`eval()\`**: thực thi theo context mặc định của engine, vì vậy có nguy cơ sử dụng state đã được đặt từ lần trước nếu engine/context được chia sẻ.
2. **\`eval(Bindings)\`**: cung cấp \`ENGINE_SCOPE\` bindings riêng cho một lần đánh giá theo hợp đồng \`CompiledScript\`. Phù hợp khi muốn truyền biến khác nhau qua các lần gọi.
3. **\`eval(ScriptContext)\`**: truyền context với bindings theo scope, \`Reader\`, \`Writer\` và \`ErrorWriter\` cụ thể, giúp kiểm soát môi trường thực thi.

Một mẫu tích hợp:

\`\`\`java
// Đoạn tích hợp; compiled được tạo bởi engine phù hợp.
Bindings first = compiled.getEngine().createBindings();
first.put("amount", 10);

Bindings second = compiled.getEngine().createBindings();
second.put("amount", 20);

Object a = compiled.eval(first);
Object b = compiled.eval(second);
\`\`\`

Đoạn script phải thực sự sử dụng biến \`amount\` theo cú pháp của ngôn ngữ engine. Không có cú pháp biến hoặc phép tính chung cho mọi ngôn ngữ được tích hợp qua JSR 223.

**Bindings không tạo sandbox.** Khi đưa object Java vào bindings, script có thể truy cập các khả năng của object theo quy tắc interop và security policy của engine. Không dùng chung mutable bindings giữa nhiều request hoặc tenant nếu chưa kiểm soát concurrency và quyền truy cập.

## 5. Ví dụ Java 17+ hoàn chỉnh, không phụ thuộc engine bên ngoài

JDK 17 trở lên không bắt buộc có JavaScript engine JSR 223. Để minh họa chính xác API compile và eval trên bất kỳ JDK 17+ thông thường nào có module \`java.scripting\`, chương trình dưới đây tạo một engine cực nhỏ **chỉ hỗ trợ phép cộng hai biến nguyên \`a + b\`**. Đây là engine học tập, không phải JavaScript engine hay parser tổng quát.

Lưu thành **\`CompiledScriptDemo.java\`**:

\`\`\`java
import java.io.Reader;
import java.io.IOException;
import java.util.regex.Pattern;
import javax.script.*;

public class CompiledScriptDemo {
    static final class AddEngine extends AbstractScriptEngine
            implements Compilable {
        private static final Pattern SOURCE =
                Pattern.compile("\\s*a\\s*\\+\\s*b\\s*");

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return compile(script).eval(context);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[1024];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
                return eval(source.toString(), context);
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return null; // Không đăng ký factory: chỉ là ví dụ nội bộ.
        }

        @Override
        public CompiledScript compile(String script)
                throws ScriptException {
            if (!SOURCE.matcher(script).matches()) {
                throw new ScriptException("Only a + b is supported");
            }
            return new AddCompiledScript(this);
        }

        @Override
        public CompiledScript compile(Reader script)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[1024];
                int count;
                while ((count = script.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
                return compile(source.toString());
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }
    }

    static final class AddCompiledScript extends CompiledScript {
        private final AddEngine engine;

        AddCompiledScript(AddEngine engine) {
            this.engine = engine;
        }

        @Override
        public Object eval(ScriptContext context) throws ScriptException {
            Object left = context.getAttribute("a");
            Object right = context.getAttribute("b");
            if (!(left instanceof Integer a) ||
                !(right instanceof Integer b)) {
                throw new ScriptException("a and b must be Integer");
            }
            return Math.addExact(a, b);
        }

        @Override
        public ScriptEngine getEngine() {
            return engine;
        }
    }

    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine = new AddEngine();

        if (!(engine instanceof Compilable compilable)) {
            throw new IllegalStateException("Compile not supported");
        }

        CompiledScript compiled = compilable.compile("a + b");
        System.out.println("same engine: " +
                (compiled.getEngine() == engine));

        Bindings first = engine.createBindings();
        first.put("a", 10);
        first.put("b", 5);
        System.out.println("first: " + compiled.eval(first));

        Bindings second = engine.createBindings();
        second.put("a", 7);
        second.put("b", 8);
        System.out.println("second: " + compiled.eval(second));
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac CompiledScriptDemo.java
java CompiledScriptDemo
\`\`\`

Stdout:

\`\`\`text
same engine: true
first: 15
second: 15
\`\`\`

Trong ví dụ này, \`compile("a + b")\` xác minh biểu thức một lần rồi trả object giữ reference tới đúng \`AddEngine\`. Hai lần \`eval(Bindings)\` sử dụng các bộ biến khác nhau nhưng cùng logic đã compile.

Ví dụ chỉ minh họa hợp đồng API. \`getFactory()\` trả \`null\` vì không công bố engine qua \`ScriptEngineManager\`; một engine production cần \`ScriptEngineFactory\` đúng quy tắc, quản lý script language đầy đủ, validation, resource lifecycle và security.

## 6. Có được dùng CompiledScript với engine khác không?

**Không được xem \`CompiledScript\` là artifact trung lập.** API \`CompiledScript.getEngine()\` trả về engine đã compile script, và \`eval(...)\` là method trên chính compiled artifact này.

Ví dụ tư duy:

\`\`\`text
Engine A --compile--> CompiledScript A --eval(context A)--> result
Engine B --compile--> CompiledScript B --eval(context B)--> result
\`\`\`

Không có API chuẩn \`engineB.eval(compiledFromA)\`. Hai engine có thể có cú pháp, kiểu dữ liệu, namespace, host interop và biểu diễn nội bộ khác nhau. Ngay cả hai instance của **cùng một implementation** cũng không mặc nhiên chia sẻ compiled object: chúng có thể chứa runtime context, cache hoặc bytecode độc lập.

Tái sử dụng hợp lệ thường là:

- Cùng \`CompiledScript\` và engine tương ứng.
- Các \`Bindings\`/\`ScriptContext\` mới được engine chấp nhận.
- Bối cảnh phiên bản engine và ngôn ngữ không đổi.
- Điều kiện thread safety được đảm bảo theo tài liệu engine.
- Thời gian sống của compiled object không vượt quá vòng đời engine/plugin.

Với hot reload, engine hoặc class loader mới cần **compile lại từ source** trong môi trường mới. Không cố ép reference của engine cũ sang runtime mới.

## 7. Caching compiled script an toàn

Một cache thường cần khóa gồm nhiều thành phần:

\`\`\`text
(engine identity/version,
 language version,
 script id + source digest,
 compile options,
 tenant/security scope nếu ảnh hưởng compilation)
\`\`\`

Nếu chỉ dùng \`scriptId\`, cache có thể trả artifact từ engine phiên bản cũ khi host cập nhật plugin. Nếu source thay đổi mà ID không đổi, kết quả cũng sai. Với multi-tenant, một số script chỉ thuộc tenant nhất định; phải bảo đảm key và quyền truy cập được áp dụng trước khi trả compiled artifact.

Các chính sách cần có:

1. **Compile on demand** hoặc warm-up cho script đã duyệt, tránh compile vô hạn khi người dùng gửi script tùy ý.
2. **Bounded cache** theo số lượng, memory footprint, TTL hoặc quota phù hợp. Không giữ mọi compiled script mãi mãi.
3. **Single-flight compile** nếu nhiều request cùng yêu cầu một script chưa cache, nhưng bảo đảm cơ chế này không gây deadlock.
4. **Invalidate** khi source, engine version, compile options, security policy hay plugin layer thay đổi.
5. **Cleanup** khi vô hiệu hóa engine; xóa reference tới \`CompiledScript\`, \`ScriptEngine\`, \`Bindings\` và loader để tránh giữ tài nguyên/hot-reload leak.
6. **Metrics**: compile latency, eval latency, cache hit/miss, lỗi parse/runtime và memory usage.

**Không đồng nhất cache thread-safe với eval thread-safe.** Một \`ConcurrentHashMap\` có thể bảo vệ cấu trúc cache, nhưng object \`CompiledScript\`/engine lấy ra có thể không được phép đánh giá đồng thời. Cần tuân thủ concurrency contract của engine: đồng bộ hóa, tạo engine/context theo request hoặc giữ pool instance phù hợp.

## 8. Trạng thái và vấn đề concurrency

Không có bảo đảm chung rằng mọi \`ScriptEngine\` hoặc \`CompiledScript\` của mọi nhà cung cấp đều thread-safe. Một số implementation lưu biến, function, compiled state hoặc global object trong engine.

JSR 223 cho phép engine công bố thông tin concurrency qua:

\`\`\`java
Object threading =
        engine.getFactory().getParameter("THREADING");
\`\`\`

Một số giá trị theo convention gồm \`MULTITHREADED\`, \`THREAD-ISOLATED\` và \`STATELESS\`. Nếu giá trị \`null\`, không thể mặc định engine hỗ trợ thực thi concurrent. Metadata này cần được đọc cùng tài liệu phiên bản thực tế; không thay thế kiểm thử race và state isolation.

Nếu cache một compiled script nhưng đồng thời chạy cho nhiều request:

- Tách \`Bindings\` giữa các request.
- Không truyền mutable Java objects dùng chung nếu không có đồng bộ hóa.
- Giới hạn số lần \`eval\` song song theo khả năng engine.
- Không chia sẻ context tenant A cho tenant B.
- Khôi phục thread-local/MDC/context class loader sau mỗi lời gọi plugin nếu có thay đổi.
- Không để timeout/cancellation khiến request kết thúc nhưng engine tiếp tục giữ resource không được quản lý.

## 9. Xử lý lỗi theo giai đoạn

Tách rõ các loại lỗi:

| Giai đoạn | Tình huống | Xử lý |
|---|---|---|
| Discovery | \`getEngineByName\` trả \`null\` | Kiểm tra engine đã cài, alias, class loader |
| Capability | Engine không \`instanceof Compilable\` | \`eval\` trực tiếp hoặc từ chối feature |
| Compilation | \`compile\` ném \`ScriptException\` | Báo lỗi source/line, không đưa vào cache |
| Evaluation | \`compiled.eval\` lỗi | Ghi nhận execution failure, kiểm tra side effect |
| Configuration | Bindings/context thiếu hoặc sai kiểu | Validate input trước khi eval |
| Runtime lifecycle | Engine bị thay hoặc dừng | Không dùng compiled object cũ; compile lại |

\`ScriptException\` có thể chứa thông tin file, line và column nếu engine cung cấp. Không nên log toàn bộ source có chứa dữ liệu nhạy cảm hoặc tiết lộ stack trace nội bộ cho người dùng cuối.

Với mã script đã có side effect, không tự retry eval chỉ vì gặp exception: một phần công việc có thể đã xảy ra. Cần chính sách idempotency và transaction/compensation nếu phù hợp.

## 10. Bảo mật và ranh giới plugin

\`Compilable\` là khả năng chuẩn bị và chạy code, **không phải công cụ sandbox**. Script thiếu tin cậy vẫn có thể truy cập host objects và tài nguyên tùy engine.

Các nguyên tắc quan trọng:

- Xác minh nguồn gốc, phiên bản và tính toàn vẹn của engine/plugin artifact.
- Giới hạn quyền truy cập của script tới Java objects và hệ thống file/network/process theo cơ chế engine hoặc ranh giới hệ điều hành.
- Không nhét credential, \`DataSource\`, database client hoặc internal service có quyền cao vào \`Bindings\` không tin cậy.
- Giới hạn thời gian, tài nguyên và độ dài source; lưu ý một engine không nhất thiết hỗ trợ cancellation có thể dừng mã đang chạy.
- Khi code không đáng tin, cân nhắc chạy trong process/container riêng với giao thức điều khiển/timeout rõ.
- Không dùng riêng class loader hoặc module layer làm ranh giới bảo mật.

Trong plugin host, một script có thể giữ reference đến object/class loader của engine; cache và callbacks phải được giải phóng khi plugin ngừng hoạt động.

## 11. Các lỗi phổ biến

- Ép \`(Compilable) engine\` khi chưa kiểm tra capability.
- Gọi method trên \`null\` vì không có engine JSR 223 tương ứng trong runtime.
- Tin rằng compile sẽ tăng hiệu năng trong mọi trường hợp mà không đo.
- Chia sẻ một \`CompiledScript\` giữa các engine hoặc phiên bản runtime khác nhau.
- Dùng \`eval()\` trên context mặc định rồi vô tình dùng lại biến của request trước.
- Tái dùng cùng \`Bindings\` mutable qua các luồng/tenant.
- Cache theo script ID mà bỏ qua source hash và version engine.
- Quên invalidation/cleanup khi hot reload plugin.
- Tưởng \`CompiledScript\` là bytecode có thể serialize và chạy trên JVM khác.
- Không tách lỗi compilation với lỗi execution và lỗi capability.
- Coi engine implementation hoặc compiled script tự bảo đảm thread safety.

## 12. Checklist áp dụng

Trước khi chọn compiled-script path:

1. Đã tìm được engine JSR 223 tương ứng và kiểm tra \`engine != null\`?
2. Engine thực sự triển khai \`Compilable\`?
3. Source/cú pháp và dependency của script được kiểm tra ở compile-time?
4. Biên dịch một lần có lợi về hiệu năng thực tế?
5. Compiled object được giữ cùng engine đã tạo ra nó?
6. \`Bindings\`/\`ScriptContext\` mỗi lần eval có đủ dữ liệu và không rò tenant?
7. Engine và compiled script có hỗ trợ concurrency theo cách sử dụng?
8. Cache có key, quota, invalidation và cleanup phù hợp?
9. Có chính sách lỗi, timeout, resource và security khi thực thi script?
10. Khi thay plugin/engine, có bỏ artifact cũ và compile lại source?

**Ghi nhớ:** kiểm tra \`engine instanceof Compilable\` trước khi compile; giữ \`CompiledScript\` gắn với **engine đã tạo ra nó**; tái sử dụng với bindings/context phù hợp và quản lý thread safety, cache, security cũng như vòng đời.
