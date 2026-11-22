# 17.8 Kiểm soát đối tượng Java được cung cấp và giới hạn dùng chung engine giữa các luồng

Trong một ứng dụng Java nhúng kịch bản qua `javax.script` (JSR-223), điều khó không chỉ là viết `engine.eval(source)` mà còn là **kiểm soát những quyền mà script nhận được khi chạm vào Java object** và **ngăn engine/state của request này ảnh hưởng request khác**. Chỉ cần cung cấp một repository, HTTP client hay service có quyền cao cho script, ứng dụng có thể mở ra nhiều hành động ngoài yêu cầu nghiệp vụ. Nếu engine được dùng chung cho nhiều thread hoặc tenant, variables và object references cũng có thể bị chia sẻ ngoài dự định.

Hai quyết định chính:

1. **Host access/capability:** đưa object gì vào `Bindings`, phương thức nào có thể được gọi, dữ liệu/identity nào được phép nhìn thấy, có chặn reflection/class loading, file/network/process/thread APIs và resource abuse chưa?
2. **Concurrency/state:** `ScriptEngineFactory.getParameter("THREADING")` cho biết engine có thể thực thi đồng thời không; còn `ScriptContext`/`Bindings`/Java object có bị dùng chung hay không là điều kiện độc lập.

**Mặc định an toàn để bắt đầu:** engine và context riêng cho mỗi request, chỉ cung cấp **capability facade** tối thiểu, bỏ manager-global secrets, kiểm tra provider-specific host policy; với script thật sự không tin cậy, cân nhắc **cách ly tiến trình và quota**. `Bindings` không phải security sandbox; `synchronized` chỉ hạn chế race, không xóa state hoặc giới hạn quyền.

## 1. Mô hình rủi ro và ranh giới tin cậy

| Tình huống | Rủi ro | Điều kiểm soát |
| --- | --- | --- |
| Script được cấp `DataSource`/`EntityManager` | Có thể truy cập dữ liệu ngoài phạm vi | Không cấp đối tượng hạ tầng; cung cấp facade chỉ trả dữ liệu đã được phân quyền |
| Cấp `HttpServletRequest`, session hoặc security context | Lộ token/headers/tenant identity | Tạo DTO nhỏ chỉ chứa các field được phép; host tự xác thực identity |
| Bật tra cứu Java class rộng | Reflection/`Runtime`/`ProcessBuilder`/file/network | Host class lookup/host member access policy của provider; quyền OS |
| Nhiều requests dùng `engine.put("token", ...)` | Dữ liệu tồn tại qua eval tiếp theo, rò cross-tenant | Bindings/request context riêng, engine lifecycle riêng |
| `THREADING=null` nhưng concurrent eval cùng engine | Race/interpreter state corruption | Một engine cho mỗi worker/request hoặc độc quyền lock |
| Engine báo `MULTITHREADED` | Vẫn có thể chia sẻ global script state | Kiểm soát scopes, globals và Java mutable objects |
| `Future.cancel(true)` khi script chạy mãi | Interrupt có thể không hủy runtime | Provider cancellation đáng tin cậy; OS process isolation |
| Engine pool trả instance chưa reset cho tenant mới | Closures, caches, imported modules hoặc callbacks giữ quyền cũ | Reset toàn diện theo provider; nếu không, discard engine |

**Phân hạng script:** trusted (được review/cùng quyền ứng dụng), semi-trusted (admin tenant hoặc config bên ngoài có thể lỗi), untrusted (input bất kỳ). Mỗi nhóm cần policy và mức isolation tương ứng. Một script được gọi là “trusted” vẫn cần kiểm thử race và resource limits. Một script untrusted **không** tự trở nên an toàn vì ta chỉ truyền vào một `Map` nhỏ.

## 2. ScriptEngineManager, ScriptEngine, ScriptContext và Bindings khác nhau

~~~text
ScriptEngineManager
   |
   +-- phát hiện ScriptEngineFactory (ServiceLoader)
   +-- manager GLOBAL_SCOPE Bindings
   |
   +-- getEngineByName(...) -> ScriptEngine instance
                                   |
                         default ScriptContext
                          ENGINE_SCOPE + GLOBAL_SCOPE
                                   |
                  eval(script, requestContext) --- ScriptContext riêng
                                              |
                                    ENGINE_SCOPE Bindings
                                    GLOBAL_SCOPE Bindings (tùy chọn)
                                              |
                                      host Java objects
~~~

| Thành phần | Hợp đồng | Điều dễ hiểu sai |
| --- | --- | --- |
| `ScriptEngineManager` | Tìm factories, tạo engine, có **global Bindings** | Không tự là engine pool hoặc isolation layer |
| `ScriptEngineFactory` | Metadata engine, tạo `ScriptEngine` | `"THREADING"` mô tả concurrency mức engine |
| `ScriptEngine` | Interpreter với default context và internal state | Không nhất thiết thread-safe; state có thể tồn tại qua eval |
| `ScriptContext` | Scoped attributes, Reader/Writer/ErrorWriter cho lần chạy | Context riêng không đảm bảo interpreter internals riêng |
| `Bindings` | Map `String` → `Object` | Chứa reference tới Java objects, không sao chép sâu |
| `CompiledScript` / `Invocable` | Tính năng tùy chọn để compile/invoke code | Có thể giữ reference tới engine và state, không mặc định cross-thread safe |
| Host facade | Đối tượng được expose qua engine interop | Ít methods không tự ngăn đường reflection/class loading nếu provider cho phép |

Trong Java 17, module `java.scripting` có JSR-223 API, **nhưng không nhất thiết có JavaScript engine**. Nashorn bị loại khỏi JDK từ **Java 15**; vì vậy `new ScriptEngineManager().getEngineByName("JavaScript")` có thể là `null` nếu chưa bổ sung engine provider.

## 3. Phân biệt ENGINE_SCOPE và GLOBAL_SCOPE

`ScriptContext.ENGINE_SCOPE` có mã số `100` và được tìm **trước** `ScriptContext.GLOBAL_SCOPE` có mã số `200`. Một `SimpleScriptContext` được tạo mới có ENGINE_SCOPE bindings mặc định và GLOBAL_SCOPE mặc định `null`.

~~~java
ScriptContext ctx = new SimpleScriptContext();

Bindings local = new SimpleBindings();
local.put("tenant", "A");
ctx.setBindings(local, ScriptContext.ENGINE_SCOPE);

Bindings global = new SimpleBindings();
global.put("tenant", "fallback");
global.put("shared", "common");
ctx.setBindings(global, ScriptContext.GLOBAL_SCOPE);

System.out.println(ctx.getAttribute("tenant")); // A
System.out.println(ctx.getAttribute("shared")); // common
~~~

Đây là **snippet minh họa trong method** với `import javax.script.*;`, không phải file Java chạy độc lập. Các giá trị được tìm theo scope order. Nhưng khái niệm “script nhìn thấy tên biến `tenant`” còn phụ thuộc cách provider expose attributes ra ngôn ngữ của nó.

Ba API gần giống:

- `engine.put("api", object)` sửa ENGINE_SCOPE bindings của **default context trên engine**. Dữ liệu này có thể còn qua nhiều lời gọi `eval(script)`.
- `engine.eval(script, bindings)` sử dụng `bindings` làm ENGINE_SCOPE cho **lần đánh giá** theo JSR-223; không chứng minh interpreter xóa state của script lần trước.
- `engine.eval(script, ctx)` dùng một `ScriptContext` caller cung cấp, gồm scopes và I/O. Nó vẫn có thể dùng **cùng engine internals** nếu caller giữ engine lâu dài.

**Không dùng `ScriptEngineManager.put` để lưu token/tenant ID:** manager-global bindings được gắn cho engines do manager tạo và có thể lộ tới mọi script của chúng.

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("sharedConfig", "non-secret"); // Chỉ public, thật sự dùng chung.
~~~

Đoạn này chỉ minh họa một giá trị an toàn để chia sẻ. Thay `"non-secret"` bằng credentials hay identity của một tenant là một thiết kế sai.

### Context riêng chưa đủ để “clear”

Engine có thể duy trì global variables, compiled procedures, module cache, closure hoặc object do previous eval giữ. Nếu provider không cam kết isolation theo context, thay `SimpleBindings` không đảm bảo request B không truy cập state còn lại từ A. Nếu cần đảm bảo mạnh, khởi tạo engine mới theo request hoặc dùng một provider-specific Context được tạo riêng.

## 4. Host object là capability, không chỉ là “giá trị”

Ví dụ sau là **mã minh họa điều không nên làm** cho script chưa đáng tin:

~~~java
bindings.put("db", dataSource);
bindings.put("request", servletRequest);
bindings.put("runtime", Runtime.getRuntime());
bindings.put("loader", classLoader);
bindings.put("service", applicationService);
~~~

Các biến `bindings`/`dataSource`/`servletRequest`/... được giả định sẵn để nêu rủi ro, không phải chương trình độc lập. Với provider có Java interoperability rộng, script có thể gọi methods của các objects ấy và giành capability vượt yêu cầu.

Thay bằng facade:

~~~java
public final class GreetingView {
    private final String prefix;
    public GreetingView(String prefix) { this.prefix = prefix; }
    public String hello(String name) { return prefix + name; }
}
~~~

Facade trên chỉ cho một phép ghép chuỗi, không cấp DB, network hay filesystem trực tiếp. Tuy nhiên **facade nhỏ không phải sandbox**: nếu provider bật reflection/class lookup quá rộng, object có thể mở đường tới `Object.getClass()` hoặc Java classes khác. Cần **chính sách host member access** và kiểm thử với engine thật. Với giá trị đơn giản, một `String`/`int`/immutable DTO đôi khi tốt hơn việc đưa bất kỳ object dịch vụ nào vào script.

### Checklist object trước khi bind

1. Script thật sự cần gọi **những method nào**? Giảm API bề mặt tới mức tối thiểu.
2. Method đã kiểm tra **authorization/tenant boundary** ở phía Java chưa, hay để script tự đặt tenant ID?
3. Object có giữ `ClassLoader`, file path, HTTP client, DB transaction, credentials, callback capture hay logger cho phép viết dữ liệu nhạy cảm không?
4. Mutable object có được dùng chung ở thread khác không? `final` trên field không biến object bên trong thành thread-safe.
5. Nếu đưa `Map`/`List`, có copy dữ liệu được phép và giới hạn kích thước/depth không?
6. Interop engine có cho phép gọi `getClass`, reflection, `Java.type`, constructor hoặc load host class không?
7. Có cơ chế chặn script gọi file/network/process/thread/native APIs không?
8. Kết quả script đi vào SQL/HTML/URL/command có tiếp tục được validate/escape đúng sink không?

Một method `getBalance()` trên facade có thể **vẫn nguy hiểm** nếu nó đọc số dư của account bất kỳ mà không kiểm tra quyền. “Read-only” chỉ nói không ghi dữ liệu, **không** có nghĩa không thể rò dữ liệu.

## 5. JSR-223 không định nghĩa sandbox chung: cần policy của provider

JSR-223 quản lý evaluation/bindings/contexts, nhưng **không chuẩn hóa** host-access policy áp dụng cho mọi interpreter. Mỗi provider (GraalJS, standalone Nashorn, Groovy hoặc các engine khác) có quy tắc riêng. Không dựa vào việc xóa tên biến `"Runtime"` khỏi Bindings để khẳng định script không tìm lại class Java theo một đường khác.

Ví dụ **GraalJS Polyglot Context** (không thuộc JDK 17 thuần; đoạn minh họa cần dependency `org.graalvm.polyglot`):

~~~java
// Provider-specific, cần GraalJS và dependencies tương ứng.
try (org.graalvm.polyglot.Context ctx =
        org.graalvm.polyglot.Context.newBuilder("js")
            .allowHostAccess(org.graalvm.polyglot.HostAccess.EXPLICIT)
            .allowHostClassLookup(name -> false)
            .build()) {
    ctx.getBindings("js").putMember("api", exportedFacade);
    ctx.eval("js", "/* approved source */");
}
~~~

`HostAccess.EXPLICIT` chỉ expose members phù hợp policy như `@HostAccess.Export`; `allowHostClassLookup(name -> false)` hạn chế khả năng tra host class qua API đó. Nhưng **đây không phải sandbox hoàn chỉnh**: còn chính sách IO/native/threads/network/resource limits và tính năng tương thích với provider version. Với script untrusted, cân nhắc process isolation. Đừng bật `HostAccess.ALL`, `allowHostClassLookup(name -> true)` hay tương đương chỉ để một ví dụ chạy nhanh.

GraalJS có JSR-223 engine wrapper trong các cấu hình phù hợp. Một số host-access options có thể được đặt qua `Bindings` **trước khi context engine khởi tạo**; việc `eval` hoặc thao tác với bindings có thể khởi tạo context sớm, nên thứ tự cấu hình quan trọng. GraalVM hiện khuyến nghị trực tiếp dùng Polyglot `Context` để kiểm soát chi tiết hơn.

### Security Manager không phải lựa chọn nền tảng

`System.setSecurityManager`/Java Security Manager đã bị deprecated for removal từ Java 17 (JEP 411) và tiếp tục bị hạn chế trên các JDK sau này. Không thiết kế sandbox kịch bản mới dựa vào việc “bật SecurityManager” để cứu một engine có host interop rộng.

## 6. Kiểm tra `THREADING` bằng ScriptEngineFactory

Tham số dự trữ `"THREADING"` có ý nghĩa trong **`ScriptEngineFactory.getParameter(String)`**. Đừng viết `ScriptEngine.THREADING` vì JSR-223 không định nghĩa hằng đó.

~~~java
ScriptEngineFactory factory = engine.getFactory();
Object threading = factory.getParameter("THREADING");
System.out.println("THREADING = " + threading);
~~~

Snippet cần biến `engine` đã được tạo, và import `javax.script.*`. Theo Javadoc Java SE 17:

| Giá trị từ factory | Contract | Quyết định |
| --- | --- | --- |
| `null` | Engine **không thread-safe**, không thể execute scripts concurrently bằng cùng instance | Không gọi `eval` đồng thời trên engine đó |
| `"MULTITHREADED"` | Internal implementation thread-safe, concurrent scripts có thể chạy; **effects của một thread có thể nhìn thấy ở thread khác** | Có thể concurrency ở tầng interpreter nhưng vẫn cần quản lý globals/objects |
| `"THREAD-ISOLATED"` | Thỏa `MULTITHREADED` và mỗi thread có **giá trị symbols độc lập** trong script | Vẫn phải quản lý Java references và resources dùng chung |
| `"STATELESS"` | Thỏa `THREAD-ISOLATED` và script execution không thay **mappings của ENGINE_SCOPE Bindings** | Không bảo đảm object values là immutable hoặc script không có side effects |
| Giá trị không nhận diện | Provider-specific/metadata không mong đợi | Không tự suy ra concurrency an toàn; kiểm tra vendor docs |

**`STATELESS` không đồng nghĩa “không có side effects”.** Ví dụ nếu Bindings chứa reference tới `AtomicInteger`, việc script gọi `incrementAndGet` đổi state của object nhưng key/value mapping của Bindings vẫn giữ y nguyên. Tương tự, script có thể gọi HTTP client hoặc ghi file khi provider cho phép; THREADING metadata không chặn các hành động đó.

### MULTITHREADED không có nghĩa tenant isolation

~~~text
Thread A: context/sharedBindings["tenant"] = "A"; eval()
Thread B: context/sharedBindings["tenant"] = "B"; eval()
~~~

Nếu cùng Bindings mutable được dùng ở hai thread, A có thể đọc `"B"` khi thực thi dù interpreter báo `MULTITHREADED`. `THREAD-ISOLATED` bổ sung isolation về symbol values theo thread, nhưng vẫn không biến mọi Java object reference dùng chung thành an toàn.

### Metadata là một phần, tests là phần còn lại

Đọc `getParameter("THREADING")` từ **factory của chính engine đang sử dụng**. Không suy diễn từ tên ngôn ngữ `"JavaScript"`: có nhiều providers/version khác nhau. Nếu contract báo `null`, chọn engine-per-request hoặc exclusive borrow/lock. Nếu báo hỗ trợ concurrent, vẫn kiểm thử với representative workloads và host objects.

## 7. Các mô hình dùng engine khi có nhiều request/thread

| Mô hình | Ưu điểm | Điều kiện/hạn chế |
| --- | --- | --- |
| **Engine mới cho từng request** | Dễ hiểu nhất cho state ownership | Startup có thể tốn kém; manager-global và provider shared resources vẫn cần kiểm soát |
| **Engine riêng mỗi worker thread** | Reuse giảm chi phí tạo mới | Thread pools tái dùng thread qua tenants; state tồn tại lâu hơn request |
| **Exclusive engine pool** | Giảm số lần tạo engine | Checkout độc quyền, reset/discard theo provider, không để engine còn chạy quay lại pool |
| **Một shared engine + synchronized lock** | Ngăn eval đồng thời nếu mọi caller tôn trọng lock | Không xóa previous globals/closures, không đảm bảo tenant isolation |
| **Shared engine hỗ trợ MULTITHREADED** | Có thể tăng throughput | Shared state, Java mutable objects, readers/writers cần kiểm soát |
| **Isolated worker process/container** | Boundary phù hợp hơn với untrusted scripts và hard deadlines | IPC, OS quotas, process lifecycle và overhead cao hơn |

### 7.1. Engine per request

~~~java
ScriptEngine engine = approvedFactory.getScriptEngine();
Bindings vars = engine.createBindings();
vars.put("api", restrictedFacade);

ScriptContext context = new SimpleScriptContext();
context.setBindings(vars, ScriptContext.ENGINE_SCOPE);
Object result = engine.eval(approvedScriptSource, context);
~~~

Đoạn trên minh họa **trong method có xử lý `ScriptException`**. Không có `GLOBAL_SCOPE` chứa tokens. Tuy nhiên, tạo engine mới **không bảo đảm** chỉ còn các APIs được phép: vẫn phải cấu hình host-access riêng, và provider có thể dùng caches/process-wide state.

### 7.2. Shared engine với lock

~~~java
Object result;
synchronized (engine) {
    result = engine.eval(source, context);
}
~~~

Nếu tất cả callers dùng **cùng một lock** cho **tất cả thao tác ảnh hưởng engine state**, đây là cách ngăn concurrent `eval`. Nhưng nó **không** ngăn request B thấy data cũ của request A khi interpreter giữ state. Nếu callback reentrant hoặc long-running script, lock có thể làm queue dài hoặc deadlock. Không gọi “mô hình synchronized” là sandbox.

### 7.3. Pool có kiểm soát

~~~text
borrow engine #3 (exclusive)
  -> bind request A -> eval -> cleanup/discard -> release

borrow engine #3 (exclusive)
  -> bind request B -> eval -> cleanup/discard -> release
~~~

Không đưa engine về pool khi script bị timeout nhưng **vẫn đang chạy**. Với provider không hỗ trợ reset toàn bộ state (closures/module cache/global variables), xóa `Bindings` đơn thuần **không đủ** để reuse engine qua tenant boundary. Ưu tiên discard.

## 8. Ví dụ Java 17+ hoàn chỉnh, không cần cài JavaScript engine

Ví dụ sau dựng một **engine mô phỏng JSR-223 tối giản** bằng `AbstractScriptEngine`. Nó chỉ hiểu ba command `"greet"`, `"tenant"` và `"shared"`. Đây **không phải JavaScript, không phải sandbox** và không dùng để chứng minh một engine tổng quát an toàn; nó chỉ kiểm tra contract **ScriptEngine, ScriptContext, Bindings, ScriptEngineFactory, THREADING** và ownership khi chạy song song. Vì không cần external provider nên chạy được với **JDK 17+ thuần**.

Lưu file **`ScriptBoundaryDemo.java`**:

~~~java
import javax.script.*;
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ScriptBoundaryDemo {
    public static final class GreetingView {
        private final String prefix;
        public GreetingView(String prefix) { this.prefix = prefix; }
        public String hello(String name) { return prefix + name; }
    }

    // A tiny, intentionally limited ScriptEngine for deterministic JSR-223 tests.
    // It is not JavaScript and it is NOT a security sandbox for other engines.
    public static final class DemoEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;
        DemoEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext ctx) throws ScriptException {
            return switch (script) {
                case "greet" -> {
                    Object api = ctx.getAttribute("api", ScriptContext.ENGINE_SCOPE);
                    Object name = ctx.getAttribute("user", ScriptContext.ENGINE_SCOPE);
                    if (!(api instanceof GreetingView view) || !(name instanceof String user)) {
                        throw new ScriptException("Required binding missing");
                    }
                    yield view.hello(user);
                }
                case "tenant" -> ctx.getAttribute("tenant");
                case "shared" -> ctx.getAttribute("shared");
                default -> throw new ScriptException("Unsupported demo command");
            };
        }

        @Override
        public Object eval(Reader reader, ScriptContext ctx) throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buf = new char[256];
            try {
                int n;
                while ((n = reader.read(buf)) >= 0) source.append(buf, 0, n);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(source.toString(), ctx);
        }

        @Override public Bindings createBindings() { return new SimpleBindings(); }
        @Override public ScriptEngineFactory getFactory() { return factory; }
    }

    public static final class DemoFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "DemoEngine"; }
        @Override public String getEngineVersion() { return "1"; }
        @Override public List<String> getExtensions() { return List.of("demo"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-demo"); }
        @Override public List<String> getNames() { return List.of("demo"); }
        @Override public String getLanguageName() { return "FixedDemoCommands"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            if ("THREADING".equals(key)) return null;
            if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
            if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
            if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
            if (ScriptEngine.LANGUAGE_VERSION.equals(key)) return getLanguageVersion();
            if (ScriptEngine.NAME.equals(key)) return "demo";
            return null;
        }
        @Override public String getMethodCallSyntax(String obj, String method, String... args) {
            return obj + "." + method;
        }
        @Override public String getOutputStatement(String s) { return s; }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() { return new DemoEngine(this); }
    }

    private static ScriptContext newRequest(ScriptEngine engine, String tenant, String user) {
        Bindings vars = engine.createBindings();
        vars.put("api", new GreetingView(tenant + ":"));
        vars.put("tenant", tenant);
        vars.put("user", user);

        SimpleScriptContext ctx = new SimpleScriptContext();
        ctx.setBindings(vars, ScriptContext.ENGINE_SCOPE);
        // GLOBAL_SCOPE is left null. No large host objects are injected.
        return ctx;
    }

    private static String runIsolated(DemoFactory factory, String tenant, String user)
            throws ScriptException {
        ScriptEngine engine = factory.getScriptEngine();
        ScriptContext request = newRequest(engine, tenant, user);
        return (String) engine.eval("greet", request);
    }

    public static void main(String[] args) throws Exception {
        DemoFactory factory = new DemoFactory();
        System.out.println("THREADING = " + factory.getParameter("THREADING"));

        ScriptEngine engine = factory.getScriptEngine();
        ScriptContext a = newRequest(engine, "alpha", "An");
        ScriptContext b = newRequest(engine, "beta", "Binh");

        // Sequential only: THREADING=null does not permit parallel engine.eval.
        System.out.println("request A = " + engine.eval("greet", a));
        System.out.println("request B = " + engine.eval("greet", b));
        System.out.println("A binding keys = " +
                new TreeSet<>(a.getBindings(ScriptContext.ENGINE_SCOPE).keySet()));
        System.out.println("separate bindings = " +
                (a.getBindings(ScriptContext.ENGINE_SCOPE)
                        != b.getBindings(ScriptContext.ENGINE_SCOPE)));
        a.setAttribute("local", "A-only", ScriptContext.ENGINE_SCOPE);
        System.out.println("B local absent = " +
                (b.getAttribute("local") == null));

        Bindings global = new SimpleBindings();
        global.put("shared", "visible-to-A");
        global.put("tenant", "wrong-tenant");
        a.setBindings(global, ScriptContext.GLOBAL_SCOPE);
        System.out.println("engine scope takes precedence = " + engine.eval("tenant", a));
        System.out.println("A global visible = " + engine.eval("shared", a));
        System.out.println("B global absent = " +
                (b.getBindings(ScriptContext.GLOBAL_SCOPE) == null));

        try {
            engine.eval("dangerous-command", a);
        } catch (ScriptException expected) {
            System.out.println("unsupported demo command = " +
                    expected.getClass().getSimpleName());
        }

        // Parallel requests: each task obtains its OWN engine, context and facade.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> fa = pool.submit(() -> runIsolated(factory, "alpha", "Lan"));
            Future<String> fb = pool.submit(() -> runIsolated(factory, "beta", "Minh"));
            System.out.println("parallel request A = " + fa.get());
            System.out.println("parallel request B = " + fb.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch, chạy từ thư mục có file, dùng **JDK 17 trở lên**:

~~~bash
javac --release 17 ScriptBoundaryDemo.java
java ScriptBoundaryDemo
~~~

**`stdout` đã kiểm chứng khi compile `--release 17`, chạy trên JDK 24:**

~~~text
THREADING = null
request A = alpha:An
request B = beta:Binh
A binding keys = [api, tenant, user]
separate bindings = true
B local absent = true
engine scope takes precedence = alpha
A global visible = visible-to-A
B global absent = true
unsupported demo command = ScriptException
parallel request A = alpha:Lan
parallel request B = beta:Minh
~~~

Mã **thực sự biên dịch với `javac --release 17` và chạy trên JDK 24**, với 12 dòng output trên. Chạy với `--release 17` xác minh source/API phù hợp Java 17, **không đồng nghĩa** đã chạy trên một JVM 17. Demo factory không được đăng ký `ScriptEngineManager` và interpreter demo không hỗ trợ cú pháp JavaScript, nên không cần thêm engine.

### 8.1. Quan sát scopes và state

`newRequest` tạo `Bindings` mới cho mỗi request, chỉ gắn `api`, `tenant` và `user`. Output `A binding keys` cho thấy đúng ba keys; sau đó A thêm `local=A-only`, B không có key ấy. Khi A có `tenant=alpha` ở ENGINE_SCOPE và `tenant=wrong-tenant` ở GLOBAL_SCOPE, `getAttribute` trả `alpha` vì scope ưu tiên.

Demo cố ý gắn global map **chỉ cho context A**; B giữ GLOBAL_SCOPE null. Nếu ta thay bằng một **global map dùng chung** qua manager, reference có thể được lộ đến nhiều engines và đây là lý do tránh đặt tenant-specific values trong manager globals.

### 8.2. Vì sao parallel calls không vi phạm THREADING=null?

Hai lời gọi trên engine `engine` dùng contexts A/B được thực hiện **tuần tự**. Trong phần `ExecutorService`, mỗi task gọi `runIsolated` tạo một `DemoEngine` **riêng**, context và facade riêng. Không có hai threads đồng thời gọi cùng engine instance. `DemoFactory` của chương trình là immutable và đã được test với cách tạo instances này; **không suy ra** mọi ScriptEngineFactory bên ngoài đều thread-safe khi tạo engines concurrently.

### 8.3. Vì sao DemoEngine không phải security proof?

`DemoEngine.eval` chỉ hiểu các command `greet`, `tenant`, `shared`; nó tự từ chối input khác với `ScriptException`. Nhưng engine này **không** có parser JavaScript, reflection hay Java interoperability. Nó chứng minh cách sử dụng API JSR-223 và tách ownership; muốn xác minh một engine thực không cho script chạm file/DB/process, phải chạy các **adversarial tests trên chính provider đó** với policy tương ứng.

## 9. Tìm provider thực trong Java 17

Khi ứng dụng cài script engine provider phù hợp, có thể dùng pattern:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println(f.getEngineName() + ": " + f.getParameter("THREADING"));
}
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    throw new IllegalStateException("No approved JavaScript ScriptEngine installed");
}
Bindings bindings = engine.createBindings();
bindings.put("user", "An");
ScriptContext ctx = new SimpleScriptContext();
ctx.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
Object value = engine.eval("user", ctx);
~~~

Đoạn trên chỉ là **snippet bên trong method**, cần `javax.script.*` và xử lý `ScriptException`. Tên alias `"JavaScript"` không bảo đảm luôn tồn tại hoặc trỏ tới một provider cố định; muốn an toàn, kiểm tra factory name/version và policy trước khi thực thi. Biểu thức `"user"` là ví dụ syntax phía JavaScript, không phải syntax chuẩn của mọi scripting language.

`ScriptEngineManager.getEngineByName` trả `null` nếu không có engine matching. Nashorn built-in bị loại khỏi JDK 15 (JEP 372), vì thế nhiều tutorial Java 8 không chạy nguyên trạng trên JDK 17. Nếu dùng GraalJS trên JDK mới, cần chọn dependency/module và cách cấu hình host access theo documentation của phiên bản triển khai; tránh đoán version/cờ cấu hình.

### CompiledScript và Invocable

Nếu engine hỗ trợ `Compilable`, `CompiledScript` có thể giữ reference tới engine và state. Nếu hỗ trợ `Invocable`, script functions/closures có thể capture Java objects. **Không** mặc định chuyển CompiledScript hoặc function guest objects giữa threads/tenants. Cần đọc provider's thread/context ownership contract và thử nghiệm; đừng cho compiled code giữ secret từ request trước.

## 10. THREADING metadata không bảo đảm Java object thread-safe

Một engine `STATELESS` vẫn có thể được bind với mutable object:

~~~java
Bindings shared = new SimpleBindings();
shared.put("counter", new java.util.concurrent.atomic.AtomicInteger());
~~~

Giả sử provider cho script gọi `counter.incrementAndGet()`: internal state của `AtomicInteger` thay đổi, mặc dù `shared` giữ nguyên key `counter` và cùng value reference. Với `ArrayList`/`HashMap` thông thường, concurrent mutations có thể còn gây race. Vì vậy phải xem ba tầng riêng:

| Tầng | Hợp đồng |
| --- | --- |
| Engine execution | `THREADING` metadata và provider implementation |
| Request namespace | `Bindings`/`ScriptContext`/default context/manager globals |
| Java object behavior | Authorization, thread-safety, mutability, capabilities, side effects |

Ngay cả một DTO immutable nhưng chứa tham chiếu service có quyền cao cũng có thể mở đường tới hành động nguy hiểm. Và một facade read-only có thể làm lộ dữ liệu nếu không kiểm tra tenant.

## 11. Timeout và resource limits không thuộc JSR-223 chuẩn

`javax.script.ScriptEngine.eval` **không cung cấp API timeout/CPU quota/memory quota chuẩn**. Đừng mặc định đoạn:

~~~java
// Pseudo-code chỉ để cảnh báo:
Future<?> f = executor.submit(() -> runScript());
f.cancel(true);
~~~

sẽ giết một script chạy vô hạn. `cancel(true)` chỉ yêu cầu interrupt, không cưỡng bức interpreter dừng nếu nó không hợp tác. Đây là đoạn **pseudo-code**, giả sử `executor` và `runScript` đã tồn tại; không phải file standalone.

Biện pháp production:

1. Giới hạn kích thước source và input, recursion depth và CPU budget nếu provider hỗ trợ.
2. Dùng provider cancellation/close APIs được hỗ trợ; test với infinite loops thực tế.
3. Backpressure: bounded queue, max parallel engines, memory/CPU metrics, request deadlines.
4. Không trả engine còn đang chạy vào pool sau một timeout.
5. Với untrusted scripts, đặt engine trong **worker process/container** có quyền OS hạn chế, tài nguyên và vòng đời riêng. Đóng/kết thúc process khi quá hạn, áp dụng IPC validation.
6. Đóng contexts/resources theo provider; `ScriptEngine` chuẩn không phải `AutoCloseable`.
7. Giới hạn file/network/process/native access ở engine-specific policy và OS, không dựa vào `Thread.interrupt`.

### Vì sao pool có thể khuếch đại lỗi?

Một engine pool cố định 10 instances sẽ bị nghẽn nếu 10 scripts block mãi. Đặt timeout cho caller mà không ngăn scripts chạy thực sự còn tệ hơn: system có thể **reuse** instance vừa bị cancel cho request tiếp theo, trong khi thread cũ vẫn thao tác engine. Tính đúng đắn của pool đòi exclusive ownership và lifecycle khi abort, không chỉ timeout ở HTTP layer.

## 12. Validate output và exception trước khi trả về host

`ScriptEngine.eval` trả `Object`. Host cần xác minh type, kích thước và business constraints:

~~~java
Object raw = engine.eval(source, context);
if (!(raw instanceof String result) || result.length() > 256) {
    throw new IllegalArgumentException("Invalid script result");
}
// result vẫn cần escape/validate theo sink HTML, SQL, URL hay file path.
~~~

Đây là snippet trong method có các biến tương ứng và xử lý `ScriptException`. Dữ liệu do script trả **không tự trở thành trusted**. Không dùng nó trực tiếp làm SQL fragment, command, HTML hoặc path mà bỏ qua kiểm soát.

Nếu output là provider-specific guest object, không chuyển reference qua thread khác khi runtime không cho phép. Chuyển thành immutable Java DTO/primitive ngay khi còn context hợp lệ, kèm limit serialization depth/size. Với `null`, quyết định theo API contract và không mặc định thay bằng “success”.

Sau `ScriptException`, interpreter có thể đã cập nhật globals/caches hoặc gọi Java methods gây side effects. Không giả định “exception xảy ra thì state rollback”. Nếu dùng engine pool qua tenant, cân nhắc discard instance lỗi.

## 13. Kiểm thử isolation thực tế

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Không có JavaScript engine trên JDK 17 | `getEngineByName` trả null được xử lý, không NPE |
| `THREADING=null` và 20 concurrent requests | Không cùng sử dụng một instance đồng thời |
| `THREADING=MULTITHREADED` | Không dùng chung tenant data dù engine có thể execute concurrently |
| Bindings A/B | Không lộ token, user object, global var giữa requests |
| Manager GLOBAL_SCOPE | Không chứa secrets hoặc per-request identity |
| Host class interop | Không đến `Runtime`, `ProcessBuilder`, filesystem, reflection, class loader |
| Facade | Tự kiểm authorization, input/output constraints và side effects |
| Engine pool sau ScriptException | Không còn state/closure/module cache từ tenant trước |
| Script vòng lặp vô hạn | Resource deadline thực thi được provider/process bảo đảm |
| Java object mutable | Không race hoặc truyền reference sai owner thread |
| CompiledScript/Invocable | Không chuyển state engine-specific qua tenant/thread thiếu contract |
| Output | Type, length, nested data và sink validation |
| Provider shutdown | Không rò threads, class loaders, scripts hoặc contexts |

**Kiểm thử trên engine thật** là bắt buộc với host-access security. Demo tối giản ở mục 8 chỉ chứng minh cách dùng API chung; test malicious script trên nó không có ý nghĩa cho GraalJS/Groovy/engine khác.

## 14. Những nhầm lẫn phổ biến

**“Bindings riêng rồi thì share engine đồng thời được?”** Không. Concurrency của `ScriptEngine` do factory `THREADING` mô tả; bindings riêng chỉ là một phần về state.

**“`MULTITHREADED` là mỗi script có global riêng?”** Không. Contract nói state effects có thể nhìn thấy từ threads khác. `THREAD-ISOLATED` mạnh hơn về symbols, nhưng Java object references vẫn có thể chia sẻ.

**“`STATELESS` nghĩa là script không thể ghi file?”** Không. Nó chỉ có điều kiện về engine-scope bindings mappings; I/O host phụ thuộc provider/OS.

**“`engine.put("service", obj)` chỉ cho script lấy dữ liệu, không gọi methods?”** Không thể suy luận chung. Với host interop được bật, một object reference có thể cho phép script gọi các methods, truy tìm class và các capability khác.

**“Có thể tạo synchronized(engine) và tin rằng tenant đã cô lập?”** Không. Lock không xóa globals/closures/caches.

**“JSR-223 có timeout chắc chắn bằng cancel(true)?”** Không. Interrupt không phải cơ chế cưỡng bức hủy thực thi script.

**“Java 17 có Nashorn sẵn?”** Không. Nashorn đã bị loại từ JDK 15; cài provider tương thích nếu cần JavaScript.

**“Một thread-local engine trong worker pool an toàn cho mỗi tenant?”** Không. Worker thread được reuse; script state có thể tồn tại từ tenant trước.

**“Một facade ít methods chắc chắn là sandbox?”** Không. Bề mặt phương thức nhỏ là tốt, nhưng host interop chính sách rộng vẫn có thể cho phép reflection/class loading hoặc qua callback.

## 15. Quy trình áp dụng thực tế

1. Chọn một engine **và version cố định**, kiểm tra factory metadata, `THREADING` và host interop.
2. Phân loại script: trusted, semi-trusted, untrusted; định nghĩa boundary và quota.
3. Thiết kế một **allowlist capabilities**: object/method nào được expose, data nào có thể đọc và tác dụng phụ nào được phép.
4. Cấu hình host class lookup, member access, file/network/process/thread/native restrictions theo provider. Đừng bật “allow all” chỉ để pass demo.
5. Tạo `Bindings` và `ScriptContext` riêng mỗi request, không dùng manager-global secret. Đảm bảo context cũng có Reader/Writer độc lập nếu cần.
6. Chọn engine-per-request làm baseline khi state khó reset. Với pool/threads, giữ exclusive ownership khi metadata không cho concurrent calls.
7. Giữ request identity/tenant authorization ở Java host boundary, không cho script tự chỉ định quyền.
8. Validate kết quả, exceptions và output sinks; không coi `Object` từ script là trusted.
9. Giám sát concurrency, memory, timeouts, queue saturation và cleanup. Untrusted script cần resource/process isolation đáng tin.
10. Chạy adversarial tests và cross-tenant tests sau mỗi upgrade provider.

## 16. Câu hỏi tự kiểm tra

**1.** Factory `getParameter("THREADING")` trả null. Có gọi đồng thời `eval` trên một engine được không?  
**Đáp án:** Không theo contract. Dùng engine instances riêng hoặc exclusive locking.

**2.** Engine báo `"MULTITHREADED"`. Có được dùng một `SimpleBindings` chung chứa `tenant` rồi sửa ở hai threads không?  
**Đáp án:** Không nên. Interpreter được phép concurrent nhưng dữ liệu/state có thể chia sẻ; dùng context và bindings riêng.

**3.** `"THREAD-ISOLATED"` có bảo đảm Java `ArrayList` bind chung an toàn khi mutate không?  
**Đáp án:** Không. Symbol values theo thread và thread safety của Java object là hai việc độc lập.

**4.** `"STATELESS"` có ngăn script sửa object mà bindings trỏ tới?  
**Đáp án:** Không. Bất biến mapping không đồng nghĩa object value bất biến.

**5.** `engine.eval(source, context)` có tự cấm reflection hoặc network không?  
**Đáp án:** Không. `ScriptContext` là scopes/I/O; host interop phải cấu hình tại provider/OS.

**6.** Sao `new ScriptEngineManager().getEngineByName("JavaScript")` có thể trả null ở JDK17?  
**Đáp án:** JDK không bắt buộc ship JS provider; Nashorn đã bị loại từ Java 15.

**7.** `ScriptEngineManager.put("token", value)` có dùng tốt cho token từng request không?  
**Đáp án:** Không. Manager-global bindings có thể được shared cho engines khác.

**8.** `Future.cancel(true)` có đảm bảo đóng một script vòng lặp vô hạn không?  
**Đáp án:** Không. Nó gửi interrupt; runtime có thể không hợp tác. Cần provider cancellation hoặc kill isolated worker process.

**9.** Hai tasks của `ScriptBoundaryDemo` song song khi `THREADING=null` có vi phạm contract không?  
**Đáp án:** Không, vì mỗi task tạo **một instance engine riêng** và context riêng; shared engine ở phần trước chỉ dùng tuần tự.

**10.** Demo `DemoEngine` đã từ chối command lạ; có chứng minh GraalJS sandbox an toàn không?  
**Đáp án:** Không. Đây là interpreter toy không hỗ trợ JavaScript/interop; phải kiểm tra bảo mật với engine thật và cấu hình cụ thể.

**11.** Có thể dùng `ThreadLocal<ScriptEngine>` để luôn cô lập requests khác tenant không?  
**Đáp án:** Không. Thread pools tái sử dụng worker thread, engine state có thể tồn tại qua request boundary.

**12.** Khi provider cho phép Java object interop, một facade read-only có thể gây lộ dữ liệu không?  
**Đáp án:** Có. Method read-only vẫn có thể trả thông tin vượt quyền; cần tenant authorization, filter data và host-access policy.

## Tài liệu tham khảo

- [Java SE 17 — ScriptEngine: eval, Bindings, state](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [Java SE 17 — ScriptEngineFactory: THREADING contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [Java SE 17 — ScriptEngineManager: discovery, manager GLOBAL_SCOPE](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [Java SE 17 — ScriptContext và SimpleScriptContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html)
- [Java SE 17 — AbstractScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html)
- [Java SE 17 — java.scripting, JSR-223 interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html)
- [Oracle — Nashorn removal in Java 15](https://docs.oracle.com/en/java/javase/21/migrate/removed-tools-and-components.html)
- [GraalVM — JavaScript embedding, interop, multithreading](https://www.graalvm.org/javascript/docs/)
- [GraalVM — ScriptEngine wrapper and host access options](https://www.graalvm.org/javascript/docs/#scriptengine-implementation)
