# Quản lý trạng thái `ScriptEngine`, `Bindings` riêng và thông tin `THREADING` của factory

Trong Java, Java Scripting API (JSR 223, module `java.scripting`, package `javax.script`) cho phép ứng dụng thực thi mã kịch bản thông qua một giao diện chung là `ScriptEngine`. Khi tích hợp scripting vào ứng dụng có nhiều phiên làm việc, nhiều người dùng hoặc nhiều luồng, thách thức không chỉ là gọi `engine.eval(...)`: bạn còn phải **xác định trạng thái nằm ở đâu**, **lượt chạy nào được phép thấy biến của lượt khác**, và **provider của script engine có cam kết gì về concurrency**.

Ba công cụ cần hiểu là:

1. **`ScriptEngine` và `ScriptContext`:** đối tượng engine có context mặc định, các binding theo scope và có thể có trạng thái nội bộ riêng do implementation quản lý.
2. **`Bindings`:** ánh xạ tên biến → giá trị. Có thể tạo binding riêng cho mỗi phiên/yêu cầu và đưa vào `eval(script, bindings)` hoặc `eval(script, context)` thay vì dùng chung `ENGINE_SCOPE` mặc định.
3. **`ScriptEngineFactory.getParameter("THREADING")`:** khai báo của **provider** về khả năng thực thi script đồng thời và mức cô lập trạng thái. Không phải một công tắc giúp Java tự tạo thread-safety.

Bài này phân biệt các scope, giải thích chính xác bốn giá trị `THREADING`, đưa ra cách thiết kế an toàn và cung cấp một chương trình Java 17 chạy được **không cần cài một script engine bên thứ ba**.

## 1. Các tầng trạng thái thường bị nhầm với nhau

Một engine có thể xuất hiện trong hệ thống theo mô hình sau:

```text
ScriptEngineManager
  |-- Registry các ScriptEngineFactory
  |-- GLOBAL_SCOPE Bindings của manager
  |
  +-- tạo ScriptEngine #1
  |      |-- ScriptContext mặc định
  |      |      |-- ENGINE_SCOPE Bindings
  |      |      +-- GLOBAL_SCOPE Bindings (có thể chia sẻ từ manager)
  |      |
  |      +-- trạng thái nội bộ engine/provider (nếu có)
  |
  +-- tạo ScriptEngine #2
         |-- ScriptContext mặc định khác
         |      |-- ENGINE_SCOPE Bindings khác
         |      +-- GLOBAL_SCOPE có thể là cùng đối tượng của manager
         |
         +-- trạng thái nội bộ riêng hoặc dùng chung tùy implementation
```

**Trạng thái hiển thị trong `Bindings` không phải lúc nào cũng là toàn bộ trạng thái của scripting runtime.** Một implementation có thể duy trì môi trường thực thi, cache đã biên dịch, object/prototype, callback, tài nguyên native hoặc dữ liệu lưu trong biến riêng không được đặt trong `Bindings`. Việc thay một map `Bindings` có thể cô lập các tên biến được ánh xạ qua scope, nhưng **không tự bảo đảm reset toàn bộ runtime**.

Vì vậy phải quyết định rõ nhu cầu:

- Cần **mỗi lần gọi có tập biến riêng**? Dùng `Bindings` hoặc `ScriptContext` riêng.
- Cần **mỗi user/tenant có runtime độc lập**? Thường tạo engine riêng và tránh chia sẻ global context, đồng thời kiểm tra triển khai thực tế.
- Cần **nhiều thread dùng cùng một engine**? Kiểm tra `THREADING` và ranh giới state/concurrency; không suy đoán từ việc code mẫu chạy được một lần.
- Cần **thực thi code không tin cậy**? `ScriptEngine` không phải sandbox; phải xem xét cô lập bằng tiến trình/quyền/tài nguyên phù hợp.

## 2. Hai scope của `ScriptContext`: `ENGINE_SCOPE` và `GLOBAL_SCOPE`

`ScriptContext` xác định các scope mà engine có thể tra cứu thuộc tính và nơi gửi dữ liệu nhập/xuất. Với `SimpleScriptContext`, hai scope chuẩn là:

| Scope | Hằng số | Ý nghĩa |
|---|---|---|
| Engine | `ScriptContext.ENGINE_SCOPE` | Các biến gắn với context thực thi của engine hoặc từng lượt chạy được cung cấp một `Bindings` khác |
| Global | `ScriptContext.GLOBAL_SCOPE` | Các biến mặc định/phạm vi rộng hơn, thường được chia sẻ bởi các engine do cùng `ScriptEngineManager` tạo ra |

Khi truy cập theo thứ tự scope mặc định, **`ENGINE_SCOPE` được tìm trước `GLOBAL_SCOPE`**. Nếu cả hai có khóa `"region"`, giá trị ở `ENGINE_SCOPE` che (shadow) giá trị global trong phạm vi context đó.

Các API thường gặp:

```java
engine.put("user", "Alice");
Object value = engine.get("user");

Bindings local = engine.getBindings(ScriptContext.ENGINE_SCOPE);
Bindings global = engine.getBindings(ScriptContext.GLOBAL_SCOPE);
```

Đây là **các biểu thức minh họa**, giả định đã có biến `engine`. `engine.put/get` làm việc với **ENGINE_SCOPE của context mặc định**. Đừng nhầm `engine.get("key")` với `engine.getContext().getAttribute("key")`: vế sau thực hiện tra cứu qua các scope theo quy tắc của `ScriptContext`.

Nếu cùng một engine xử lý hai user bằng:

```java
// Minh họa cách dùng chung ENGINE_SCOPE, không phải chính sách cô lập user.
engine.put("user", "Alice");
engine.eval("someScript");
engine.put("user", "Bob");
engine.eval("someScript");
```

thì trạng thái ENGINE_SCOPE bị thay đổi liên tiếp. Đến một lượt thực thi khác, tên `"user"` có thể đã mang giá trị của user khác. Trong môi trường bất đồng bộ, còn có thể xảy ra race condition. Dùng riêng `Bindings` sẽ giải quyết một phần quan trọng của vấn đề tên biến bị dùng chung.

### `GLOBAL_SCOPE` có thực sự riêng cho từng engine?

Không phải luôn như vậy. Khi dùng `ScriptEngineManager`, manager duy trì một tập `Bindings` global và **gắn đối tượng này làm `GLOBAL_SCOPE` cho các engine mà nó tạo**. Vì thế, dù mỗi engine có `ENGINE_SCOPE` riêng, chúng vẫn có thể nhìn thấy các key trong global bindings của manager.

Ví dụ ý tưởng:

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("region", "APAC"); // Thuộc GLOBAL_SCOPE của manager.
```

Nếu hai engine đều được manager tạo và nhận cùng `GLOBAL_SCOPE`, sửa một giá trị global có thể ảnh hưởng cả hai. Đây là lý do không nên đặt bí mật của từng user/tenant vào global bindings chung. Tên là “global” không có nghĩa dữ liệu bất biến hay thread-safe.

## 3. `eval(script)` khác gì `eval(script, bindings)`?

Đây là khác biệt cơ bản để tránh rò trạng thái.

**Gọi không có bindings riêng**:

```java
Object result = engine.eval(script);
```

Engine dùng **context mặc định** của nó. Những biến do script gán vào ENGINE_SCOPE có thể còn đó để lần gọi tiếp theo dùng lại (tùy ngôn ngữ và implementation). Việc lưu biến giữa hai lần `eval` là hành vi thường được ứng dụng sử dụng cho một phiên làm việc, nhưng không thích hợp khi mặc định gộp nhiều tenant vào cùng một phiên.

**Gọi có bindings riêng**:

```java
Bindings alice = engine.createBindings();
Bindings bob = engine.createBindings();

Object one = engine.eval(script, alice);
Object two = engine.eval(script, bob);
```

`eval(String, Bindings)` dùng `alice` hoặc `bob` làm **ENGINE_SCOPE cho lần thực thi đó**. Theo hợp đồng Java Scripting API, nó **không thay thế vĩnh viễn ENGINE_SCOPE mặc định** của engine. Với `AbstractScriptEngine`, phiên eval được xây dựng bằng một `SimpleScriptContext` tạm có ENGINE_SCOPE là bindings được truyền và các phần khác được lấy từ context mặc định, trong đó có GLOBAL_SCOPE.

Điều cần nhớ:

- Những thay đổi tên biến mà script ghi vào `alice` không tự xuất hiện trong `bob`.
- Bản thân `alice` vẫn có thể giữ các thay đổi để **lần chạy sau của cùng phiên Alice** dùng tiếp, nếu bạn chủ động tái sử dụng object đó.
- Việc thay `Bindings` theo lượt gọi **không chứng minh cùng một engine có thể chạy đồng thời** trên nhiều thread.
- Nếu một object Java mutable được đặt vào cả `alice` và `bob`, hai binding map có thể khác nhau nhưng **object bên trong vẫn là cùng một tham chiếu**.
- Script vẫn có thể thấy `GLOBAL_SCOPE` và trạng thái nội bộ engine. Nếu cần isolation mạnh, thay `Bindings` thôi chưa đủ.

### `setBindings(...)` khác `eval(..., bindings)`

```java
engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
```

Đây là hành động **thay ENGINE_SCOPE mặc định của engine**. Những lần `engine.eval(script)` sau đó sẽ dùng `alice` cho tới khi bạn đổi lại. Nó **không tương đương** với việc truyền `alice` chỉ cho một lần eval.

Không nên liên tục gọi `setBindings(...)` trên một engine dùng chung giữa các request đồng thời: một request có thể thay context mặc định trong khi request khác đang thực thi, dẫn đến dữ liệu sai. Ưu tiên `eval(script, requestBindings)` hoặc `eval(script, requestContext)` với engine không được dùng đồng thời trái với cam kết factory.

## 4. `ScriptEngineFactory.getParameter("THREADING")`: đọc và hiểu đúng

`ScriptEngineFactory` mô tả loại engine, tên ngôn ngữ, phiên bản và khả năng liên quan. Java định nghĩa **khóa dành riêng là chuỗi `"THREADING"`**, đọc bằng:

```java
Object threading = factory.getParameter("THREADING");
```

Đừng viết `ScriptEngine.THREADING`: `THREADING` ở đây là **chuỗi khóa truyền vào factory**, không phải hằng số chuẩn mang tên đó trên interface `ScriptEngine`.

Theo Java SE 17 API, các giá trị được quy định:

| `THREADING` | Cam kết được mô tả | Hệ quả thiết kế |
|---|---|---|
| `null` | Engine implementation **không thread-safe**, không được thực thi script đồng thời trên cùng engine từ nhiều luồng | Không chia sẻ một engine để `eval` song song; chọn engine riêng theo luồng/yêu cầu hoặc quản lý quyền sở hữu/đồng bộ hợp lý |
| `"MULTITHREADED"` | Engine có thể thực thi script đồng thời; tác động thay đổi trạng thái từ luồng này **có thể thấy được** ở luồng khác | Concurrency được công bố nhưng **không có tự động cô lập biến** |
| `"THREAD-ISOLATED"` | Thỏa điều kiện `MULTITHREADED` và duy trì giá trị độc lập cho các symbol của script ở những thread khác nhau | Cô lập symbol theo luồng do implementation cam kết, nhưng vẫn cần quản lý shared objects, global bindings và các tác dụng phụ |
| `"STATELESS"` | Thỏa `THREAD-ISOLATED`; thực thi script **không thay đổi các mapping của ENGINE_SCOPE Bindings** trước/sau eval | Đây là cam kết mạnh hơn về mapping của ENGINE_SCOPE, **không có nghĩa code không thể thay đổi file, mạng hoặc đối tượng Java mutable** |

Cần chú ý các điểm thường bị diễn giải sai:

1. `"MULTITHREADED"` **không đồng nghĩa `"STATELESS"`**.
2. `"THREAD-ISOLATED"` nói về giá trị symbol theo thread; nó không phải giấy phép chia sẻ mọi `Map`, `List`, kết nối database hoặc object Java mutable giữa các luồng.
3. `"STATELESS"` nói rõ các key/value mapping của ENGINE_SCOPE `Bindings` giữ nguyên trước và sau script, **không bảo đảm mọi tác dụng phụ đều biến mất**.
4. `null` có nghĩa không có bảo đảm thread-safe cho engine. **Không được** suy ra rằng truyền hai `Bindings` riêng tự biến engine thành thread-safe.
5. Factory chỉ **công bố** đặc tính của implementation. Khi triển khai thật, cần đọc tài liệu provider, kiểm thử tương ứng với phiên bản đang dùng và kiểm soát concurrency ở lớp ứng dụng.

Phần lớn ứng dụng nên **bắt đầu từ giả định engine không dùng chung để chạy đồng thời** nếu chưa có bằng chứng ngược lại. Với công việc đa tenant có yêu cầu isolation mạnh, engine riêng theo tenant cũng chưa phải sandbox; dùng thêm ranh giới bảo mật phù hợp.

## 5. Khám phá engine và giới hạn JDK 17

`ScriptEngineManager` có thể tìm factory bằng cơ chế service provider và tạo engine theo tên:

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + " threading=" + factory.getParameter("THREADING"));
}

ScriptEngine engine = manager.getEngineByName("some-engine-name");
if (engine == null) {
    throw new IllegalStateException("Script engine is not installed");
}
```

Đây là trích đoạn để áp dụng khi ứng dụng đã cài provider thích hợp. `getEngineFactories()` **có thể trả danh sách rỗng**; không nên giả định luôn có JavaScript engine chỉ vì JDK có `javax.script`. Nashorn đã bị loại bỏ khỏi JDK từ Java 15, nên Java 17 không cung cấp sẵn Nashorn như những phiên bản cũ.

Có thể cài engine bên thứ ba tương thích JSR 223 rồi đăng ký theo cơ chế service provider mà nhà cung cấp chỉ dẫn. Cũng có thể **đăng ký factory bằng mã Java** qua:

```java
manager.registerEngineName("toy", factory);
```

Trong đoạn minh họa này, `factory` là một `ScriptEngineFactory` đã được tạo. Việc đăng ký tên ở manager **không biến factory thành thư viện JS**; manager chỉ biết nơi lấy engine khi có tên `toy`.

Để ví dụ trong bài **chạy chắc trên một JDK 17 bình thường**, phần tiếp theo cài một *script engine rất nhỏ* hỗ trợ ba lệnh `set`, `get`, `print`. Nó chỉ giúp quan sát scope và API, **không phải JavaScript, không phải production engine và không minh họa chạy nhiều thread an toàn**.

## 6. Chương trình Java 17 hoàn chỉnh, không cần thư viện ngoài

Tạo tệp `ScriptingStateDemo.java`. Ví dụ tự xây `ToyFactory` và `ToyEngine` từ các interface/class chuẩn `javax.script` để minh họa:

- `ScriptEngineManager` và việc đăng ký factory bằng tên.
- `ENGINE_SCOPE` mặc định khi gọi `eval(script)` hoặc `engine.put(...)`.
- Hai binding map riêng cho hai phiên làm việc qua `eval(script, bindings)`.
- `GLOBAL_SCOPE` từ manager và việc ghi đè giá trị ở ENGINE_SCOPE.
- Cảnh báo thực tế về `THREADING=null`.
- Tính khác nhau giữa `setBindings(...)` và truyền bindings cho một lượt eval.

Mã sau **là chương trình hoàn chỉnh**:

```java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class ScriptingStateDemo {
    private static final class ToyFactory implements ScriptEngineFactory {
        @Override
        public String getEngineName() {
            return "Toy Scripting Engine";
        }

        @Override
        public String getEngineVersion() {
            return "1.0";
        }

        @Override
        public List<String> getExtensions() {
            return List.of("toy");
        }

        @Override
        public List<String> getMimeTypes() {
            return List.of("text/x-toy");
        }

        @Override
        public List<String> getNames() {
            return List.of("toy");
        }

        @Override
        public String getLanguageName() {
            return "ToyScript";
        }

        @Override
        public String getLanguageVersion() {
            return "1.0";
        }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case "THREADING" -> null;
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> "toy";
                default -> null;
            };
        }

        @Override
        public String getMethodCallSyntax(
                String object, String method, String... args) {
            throw new UnsupportedOperationException(
                    "ToyScript does not support method calls");
        }

        @Override
        public String getOutputStatement(String toDisplay) {
            return "print " + toDisplay;
        }

        @Override
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }

        @Override
        public ScriptEngine getScriptEngine() {
            return new ToyEngine(this);
        }
    }

    private static final class ToyEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        ToyEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Object last = null;

            for (String raw : source.split("\\R")) {
                String command = raw.trim();
                if (command.isEmpty()) {
                    continue;
                }

                String[] parts = command.split(" ", 3);
                switch (parts[0]) {
                    case "set" -> {
                        if (parts.length != 3) {
                            throw new ScriptException("Usage: set name value");
                        }
                        context.setAttribute(
                                parts[1], parts[2], ScriptContext.ENGINE_SCOPE);
                        last = parts[2];
                    }
                    case "get" -> {
                        if (parts.length != 2) {
                            throw new ScriptException("Usage: get name");
                        }
                        last = context.getAttribute(parts[1]);
                    }
                    case "print" -> {
                        if (parts.length < 2) {
                            throw new ScriptException("Usage: print text");
                        }
                        try {
                            context.getWriter().write(
                                    command.substring("print ".length()));
                            context.getWriter().flush();
                        } catch (IOException ex) {
                            throw new ScriptException(ex);
                        }
                        last = null;
                    }
                    default -> throw new ScriptException(
                            "Unknown command: " + parts[0]);
                }
            }
            return last;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, count);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(text.toString(), context);
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return factory;
        }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngineFactory factory = new ToyFactory();
        manager.registerEngineName("toy", factory);
        manager.put("region", "APAC");

        ScriptEngine engine = manager.getEngineByName("toy");
        if (engine == null) {
            throw new IllegalStateException("Toy engine not available");
        }

        System.out.println(
                "THREADING: " + engine.getFactory().getParameter("THREADING"));

        engine.eval("set user Root");
        System.out.println("Default user: " + engine.get("user"));

        Bindings alice = engine.createBindings();
        Bindings bob = engine.createBindings();
        engine.eval("set user Alice", alice);
        engine.eval("set user Bob", bob);

        System.out.println("A user: " + engine.eval("get user", alice));
        System.out.println("B user: " + engine.eval("get user", bob));
        System.out.println("Default after private eval: "
                + engine.eval("get user"));

        alice.put("region", "EU");
        System.out.println("A region: " + engine.eval("get region", alice));
        System.out.println("B region: " + engine.eval("get region", bob));

        ScriptEngine another = manager.getEngineByName("toy");
        System.out.println("Another default user: "
                + another.eval("get user"));
        System.out.println("Shared manager GLOBAL_SCOPE: "
                + (engine.getBindings(ScriptContext.GLOBAL_SCOPE)
                == another.getBindings(ScriptContext.GLOBAL_SCOPE)));

        engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
        System.out.println("Switched default user: "
                + engine.eval("get user"));
    }
}
```

### Biên dịch và chạy

Cài **JDK 17 trở lên** và đứng trong thư mục chứa `ScriptingStateDemo.java`. Hai lệnh sau dùng được trong PowerShell, Bash hoặc terminal thông thường:

```bash
javac --release 17 -encoding UTF-8 ScriptingStateDemo.java
java ScriptingStateDemo
```

`--release 17` hướng compiler tạo bytecode tương thích Java 17. Chương trình sử dụng module chuẩn `java.scripting` thuộc Java SE; trong cách chạy classpath này bạn không cần tạo `module-info.java` hay cài thêm một JavaScript implementation.

Stdout được kỳ vọng:

```text
THREADING: null
Default user: Root
A user: Alice
B user: Bob
Default after private eval: Root
A region: EU
B region: APAC
Another default user: null
Shared manager GLOBAL_SCOPE: true
Switched default user: Alice
```

Đây là **đầu ra của `ToyEngine` được viết trong chương trình**, không phải biểu hiện mặc định của tất cả engine JSR 223. `ToyFactory` trả `null` cho `"THREADING"` vì nó **không tuyên bố có thể `eval` song song** trên cùng instance.

## 7. Phân tích kết quả và trạng thái sau mỗi bước

### 7.1. Một engine có trạng thái mặc định

Lệnh:

```java
engine.eval("set user Root");
```

đặt `"user" = "Root"` trong `ENGINE_SCOPE` của `ScriptContext` mặc định. Vì vậy `engine.get("user")` trả `"Root"`.

Nếu chỉ dùng cách gọi `engine.eval(...)` mặc định cho các user khác nhau, họ có thể chia sẻ các biến đang tồn tại. Đây là một dạng *state leakage* rất dễ xảy ra nếu engine được cache như một singleton.

### 7.2. `Bindings` riêng cho Alice và Bob

```java
Bindings alice = engine.createBindings();
Bindings bob = engine.createBindings();

engine.eval("set user Alice", alice);
engine.eval("set user Bob", bob);
```

Mỗi `Bindings` có map riêng. Hai lệnh `get user` tương ứng trả `Alice` và `Bob`. Trong ví dụ, lời gọi `set` thay đổi map của request được truyền, còn ENGINE_SCOPE **mặc định vẫn là `"Root"`**. Do đó chương trình in:

```text
Default after private eval: Root
```

Nếu muốn mỗi phiên giữ biến qua nhiều lượt script, bạn có thể tái sử dụng `alice` cho phiên Alice; khi hết phiên phải giải phóng map và mọi đối tượng không còn cần thiết. **Không dùng chung một `Bindings` cho hai user** chỉ vì bạn đã gọi hai lần `createBindings()` ở nơi khác.

### 7.3. GLOBAL_SCOPE và thứ tự tra cứu

Manager đã gọi `manager.put("region", "APAC")`. Bởi các engine được tạo qua manager, `GLOBAL_SCOPE` của chúng cùng tham chiếu đến bindings global của manager.

- Khi `bob` chưa có `"region"`, `context.getAttribute("region")` tra GLOBAL_SCOPE và nhận `"APAC"`.
- Khi `alice.put("region", "EU")`, ENGINE_SCOPE của Alice có `"region"`, nên che giá trị global và trả `"EU"`.

Kết quả:

```text
A region: EU
B region: APAC
```

Không nên xem việc gán `alice.put("region","EU")` là thay region cho toàn bộ ứng dụng. Nó chỉ thay map Alice. Ngược lại, `manager.put("region",...)` là thay dữ liệu dùng chung trong manager và có thể làm thay đổi kết quả nhiều engine.

### 7.4. Engine mới và việc thay default bindings

`another` được tạo từ cùng manager nhưng là **instance mới** của `ToyEngine`; nó chưa gán key `"user"` vào ENGINE_SCOPE, do đó `get user` nhận `null`. Tuy vậy, nó vẫn thấy cùng global map từ manager; phép so sánh tham chiếu trong ví dụ là `true`.

Sau đó:

```java
engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
```

đặt map Alice làm default ENGINE_SCOPE của engine đầu. Vì thế `engine.eval("get user")` (không truyền bindings) trả `Alice`.

Trong chương trình, các bước chạy tuần tự và không có request đồng thời. **Đầu ra đúng không chứng minh `ToyEngine` thread-safe**; thông tin factory vẫn là `null`.

## 8. `ScriptContext` riêng khi cần thêm input/output riêng

`eval(script, bindings)` tiện khi khác nhau chỉ ở ENGINE_SCOPE; nó vẫn sử dụng Reader/Writer và các scope ngoài ENGINE_SCOPE từ context mặc định theo hợp đồng của `AbstractScriptEngine`. Khi mỗi lượt chạy cần **writer, error writer hoặc global map khác**, hãy tạo `ScriptContext` riêng.

Ví dụ minh họa độc lập về cách cấu hình một context:

```java
import java.io.StringWriter;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

static Object runWithContext(ScriptEngine engine, String script)
        throws javax.script.ScriptException {
    SimpleScriptContext context = new SimpleScriptContext();
    Bindings local = engine.createBindings();
    local.put("requestId", "request-001");
    context.setBindings(local, ScriptContext.ENGINE_SCOPE);

    Bindings safeGlobals = new SimpleBindings();
    safeGlobals.put("locale", "en");
    context.setBindings(safeGlobals, ScriptContext.GLOBAL_SCOPE);

    StringWriter output = new StringWriter();
    context.setWriter(output);

    Object result = engine.eval(script, context);
    return result;
}
```

Đây là **đoạn method minh họa** để đặt trong một class; nó không phải chương trình độc lập và không được gọi từ `main` ở phần 6. Nếu muốn đọc output script, có thể trả đồng thời `result` và `output.toString()` qua một kiểu kết quả riêng. Với engine thực, cần cấu hình thêm `setErrorWriter(...)` và `setReader(...)` nếu script dùng các kênh đó.

**Lưu ý:** `eval(script, context)` có thể cho phép cô lập scope và I/O theo lời gọi, nhưng với `THREADING=null` vẫn **không được chạy nhiều lời gọi đồng thời trên cùng engine**. `SimpleBindings` và `SimpleScriptContext` cũng không biến các object Java bên trong thành immutable hay thread-safe.

## 9. Thiết kế vòng đời engine trong ứng dụng server

Có thể lựa chọn một trong ba cách tổ chức:

| Chiến lược | Ưu điểm | Điều phải kiểm soát |
|---|---|---|
| Engine mới cho mỗi request | Hạn chế chia sẻ state giữa request, tương thích với provider không thread-safe khi không dùng chung instance | Chi phí khởi tạo, tài nguyên nội bộ; `GLOBAL_SCOPE` vẫn có thể được chia sẻ nếu dùng một manager |
| Engine riêng cho mỗi phiên/tenant | Hỗ trợ script cần giữ trạng thái qua nhiều lượt, giảm chi phí khởi tạo mỗi request | Chỉ một luồng sử dụng mỗi engine tại một thời điểm nếu THREADING không cho concurrency; quota, timeout, cleanup, kiểm soát tenant |
| Engine pool, cho mượn độc quyền | Tái sử dụng engine nhưng không chạy song song trên cùng instance | Reset toàn bộ state theo quy định provider, không trả engine bẩn vào pool, tránh dữ liệu user cũ còn lại |

Ví dụ pool có rủi ro: chỉ gọi `setBindings(new SimpleBindings(), ENGINE_SCOPE)` **không chứng minh engine đã sạch**, bởi implementation có thể chứa state khác trong engine, globals hoặc những object script đã lưu. Nếu không có API reset đủ tin cậy, engine mới thường an toàn về tính cô lập hơn.

Một phương án cố ý chỉ cho **một request sở hữu mỗi instance**:

```text
Request đến
    |
    v
Tạo/nhận engine có quyền sở hữu độc quyền
    |
    v
Tạo Bindings riêng (hoặc Context riêng)
    |
    v
eval(...) và xử lý result / ScriptException
    |
    v
Dọn state, trả lại pool nếu reset bảo đảm
hoặc bỏ engine và tạo mới cho lần sau
```

Với provider có `THREADING="MULTITHREADED"`, bạn **có thể** thiết kế chia sẻ engine và `eval` đồng thời theo cam kết của provider, nhưng vẫn phải bảo vệ các map/đối tượng mutable được chia sẻ và xác định logic tách user. *Thread-safe về khả năng chạy engine* không đồng nghĩa *tenant-safe về dữ liệu*.

## 10. Kiểm tra `THREADING` trước khi chọn chính sách

Trong chương trình dùng factory thật, bạn có thể đọc metadata:

```java
ScriptEngineFactory factory = engine.getFactory();
Object value = factory.getParameter("THREADING");

if (value == null) {
    // Chính sách bảo thủ: không sử dụng cùng engine để eval song song.
} else if ("MULTITHREADED".equals(value)) {
    // Provider công bố engine cho phép eval đồng thời; state có thể chia sẻ.
} else if ("THREAD-ISOLATED".equals(value)) {
    // Có thêm bảo đảm về symbol riêng theo thread.
} else if ("STATELESS".equals(value)) {
    // Có thêm bảo đảm mapping ENGINE_SCOPE không đổi bởi eval.
} else {
    // Tham số ngoài các giá trị chuẩn: tra tài liệu provider hoặc fail closed.
}
```

Đây là **đoạn logic minh họa**, không phải chương trình độc lập; biến `engine` cần lấy từ một factory đang cài.

Không cần ép `Object` thành `String` trước khi so sánh: dùng `"MULTITHREADED".equals(value)` vừa an toàn khi `null`, vừa rõ ngữ nghĩa. Nếu muốn log giá trị ngoài chuẩn, log theo cách không làm lộ những thuộc tính nội bộ nhạy cảm của engine.

### Những điều metadata không tự nói cho bạn

- Có bao nhiêu engine được tạo và ai sở hữu chúng.
- Provider có lưu state trong object phụ nào ngoài bindings không.
- Một object Java do script nhận được có thread-safe hoặc được tenant khác tham chiếu không.
- Khi engine dùng Java class loader riêng, script có quyền truy cập vào API nhạy cảm nào.
- Script chạy bao lâu, có bị timeout hoặc bị chặn vô hạn không.

Cần bổ sung tài liệu provider, kiểm thử tích hợp và ranh giới vận hành thực tế.

## 11. Không nhầm an toàn đồng thời với cách ly bảo mật

Một `ScriptEngine` được mô tả `"STATELESS"` không có nghĩa bạn có thể chạy script không tin cậy trong JVM của server mà không cần hạn chế quyền. Ngay cả một `Bindings` không bị thay đổi mapping vẫn có thể chứa đối tượng `List`, `Map`, `Connection`, `File` hoặc callback mutable; script có thể gọi method thay đổi **trạng thái của chính đối tượng**, của tệp, của mạng hoặc của hệ thống khác.

Các nguyên tắc thực hành:

1. **Không đặt secret hay dữ liệu user A trong global bindings của tất cả user.**
2. **Không chia sẻ object mutable không kiểm soát giữa các bindings riêng.** Tách map không phải deep copy.
3. **Phân loại nguồn script và dependency:** chỉ triển khai trong cùng JVM đối với script đủ tin cậy. Nếu script không tin cậy, dùng cô lập tiến trình phù hợp.
4. **Giới hạn tài nguyên:** CPU, thời gian, heap, kích thước input, số context/engine. Java Scripting API không tự áp đặt timeout hay quota.
5. **Quản lý context I/O:** writer có thể chứa dữ liệu nhạy cảm, cần cấu hình và thu gom theo phiên thay vì dùng writer toàn cục.
6. **Không tự động retry script có side effect:** nếu script đã ghi dữ liệu bên ngoài và lỗi muộn, chạy lại có thể ghi trùng.
7. **Giám sát:** log engine name, version, threading metadata, request ID đã làm sạch và thời gian thực thi; không log nguyên script hoặc tất cả bindings nếu có thông tin nhạy cảm.

## 12. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân phổ biến | Cách kiểm tra và sửa |
|---|---|---|
| Request B đọc được biến của request A | Dùng chung ENGINE_SCOPE mặc định hoặc tái sử dụng binding map sai phiên | Truyền `Bindings`/`ScriptContext` theo request và giới hạn vòng đời |
| `engine.eval(script, b)` xong, `engine.get("x")` không thấy giá trị trong `b` | `eval(..., b)` chỉ dùng `b` cho ENGINE_SCOPE của lần eval, **không thay default** | Đọc `b.get("x")` hoặc `eval("get x", b)` |
| Hai engine vẫn thấy chung biến | `GLOBAL_SCOPE` lấy từ cùng manager, hoặc object mutable được chia sẻ | Tách manager/context/global map theo ranh giới tenant |
| Có `Bindings` riêng nhưng dùng chung engine đa luồng vẫn lỗi | `THREADING=null` hoặc implementation có state nội bộ | Không `eval` song song trên engine; dùng instance riêng hoặc sở hữu độc quyền |
| Tưởng `"MULTITHREADED"` có nghĩa không rò trạng thái | Giá trị này cho phép effects của các luồng nhìn thấy nhau | Thêm policy cô lập data; cân nhắc engine/context riêng |
| Tưởng `"STATELESS"` cấm mọi side effect | Cam kết chỉ liên quan mappings của ENGINE_SCOPE | Kiểm soát các object/resource mà script có thể truy cập |
| `getEngineByName("JavaScript")` trả `null` trên Java 17 | Không có provider được cài hoặc được class loader nhìn thấy | Kiểm tra `getEngineFactories()` và cài engine tương thích |
| Script chạy được nhưng `ScriptException` khi gọi mã khác | Khác nhau giữa syntax/runtime của ngôn ngữ provider và policy engine | Ghi log diagnostic có kiểm soát, kiểm tra source và thư viện |
| `setBindings` thay mất biến mặc định | Thay trực tiếp default scope, không phải override tạm | Dùng `eval(script, bindings)` hoặc `eval(script, context)` |
| Pool engine trả dữ liệu user cũ cho user mới | Không reset hết state nội bộ và global | Loại bỏ instance hoặc thực hiện quy trình reset đã được provider xác nhận |
| Nội dung `Bindings` an toàn nhưng script sửa object bên trong | Map khác nhau nhưng tham chiếu object chung | Truyền dữ liệu bất biến, DTO đã kiểm soát hoặc bản sao thích hợp |

## 13. Checklist thiết kế khi tích hợp scripting

Trước khi dùng JSR 223 trong một ứng dụng đa phiên:

- **Discovery:** đã biết engine nào được cài, tên và version thực tế qua `ScriptEngineFactory` chưa?
- **THREADING:** đã đọc `factory.getParameter("THREADING")` và chọn chính sách concurrency tương ứng chưa?
- **Ownership:** engine thuộc request, session, pool hay singleton? Ai được phép gọi `eval` vào thời điểm nào?
- **Scopes:** `ENGINE_SCOPE` là map nào? Có `GLOBAL_SCOPE` từ manager bị nhiều request cùng thấy không?
- **Isolation:** mỗi user/tenant có Bindings hoặc context riêng, và các object trong map có bị chia sẻ ngoài ý muốn không?
- **Lifecycle:** có chính sách xóa state, dọn cache/writer/callback, tránh giữ instance đã dùng bởi user khác không?
- **Failure:** lỗi syntax/runtime được nhận dưới dạng `ScriptException` và trả về đúng chỗ, không rò dữ liệu?
- **Security:** script có đáng tin cậy không? Có cần process isolation thay vì chỉ tạo nhiều ScriptEngine?
- **Testing:** đã thử liên tiếp Alice → Bob → Alice, thử nhiều engine từ cùng manager, thử global shadowing và concurrency theo cam kết provider chưa?

## 14. Bài tập củng cố

1. **Duy trì phiên:** dùng cùng `Bindings alice` để chạy `set user Alice` rồi `get user` ở nhiều lượt; tạo `Bindings bob` mới và xác minh Bob không thấy `"Alice"`.
2. **Khảo sát shadowing:** đặt `"region" = "APAC"` trong manager, sau đó đặt `"region" = "EU"` trong `alice`. Xóa khóa `"region"` khỏi `alice` và giải thích vì sao lần đọc tiếp theo sẽ rơi về global.
3. **Thử context riêng:** thêm `SimpleScriptContext` với một `StringWriter` và một global map độc lập. Cho ToyScript chạy `print Hello`, kiểm tra writer có đúng `"Hello"` và context khác không bị đổi.
4. **Thử thay default:** sau `engine.setBindings(alice, ENGINE_SCOPE)`, chạy `engine.eval("get user")`; giải thích vì sao bây giờ thấy Alice dù không truyền bindings.
5. **Phân tích factory metadata:** giả sử ba nhà cung cấp lần lượt báo `null`, `"MULTITHREADED"` và `"STATELESS"`. Viết kế hoạch concurrency và state isolation phù hợp; chỉ ra phần nào vẫn cần bảo vệ dù nhà cung cấp báo `"STATELESS"`.
6. **Rủi ro map riêng nhưng object chung:** đặt cùng một `ArrayList` vào hai map bindings khác nhau. Giải thích vì sao sửa danh sách từ một bên vẫn tác động đến bên còn lại.
7. **Tích hợp engine thực:** khi dự án có JSR 223 engine đã cài, liệt kê `ScriptEngineManager.getEngineFactories()`, in `getEngineName()`, `getEngineVersion()` và `getParameter("THREADING")`. Chỉ chạy script khi thực sự có provider tương thích.

## 15. Tóm tắt cốt lõi

**`ScriptEngine` quản lý môi trường thực thi; `Bindings` quản lý ánh xạ tên–giá trị trong từng scope; `ScriptContext` xác định scope và I/O của lần thực thi; `ScriptEngineFactory` công bố khả năng của provider.**

Với `eval(script, bindings)`, bạn có thể tách `ENGINE_SCOPE` theo từng lượt mà không thay default bindings. Nhưng **cô lập biến không phải thread safety**, và **thread safety không tự tạo cô lập người dùng**. Luôn đọc `"THREADING"`, chủ động xác định engine ownership và quản lý `GLOBAL_SCOPE`/state nội bộ để tránh rò dữ liệu.

### Tài liệu chuẩn

- [Java SE 17 — ScriptEngineFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): ngữ nghĩa khóa `THREADING`.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `put/get`, `setBindings`.
- [Java SE 17 — AbstractScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): cách dùng context tạm cho `eval(script, bindings)`.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): discovery, factory và global bindings.