# 17.4 Truyền dữ liệu Java qua Bindings, ScriptContext và các phạm vi biến

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 17. Kịch bản nhúng  
**API trọng tâm:** `javax.script.Bindings`, `ScriptContext`, `SimpleBindings`, `SimpleScriptContext`, `ScriptEngine`, `ScriptEngineManager`.  
**Nền tảng:** Java 17 trở lên (JSR-223 / module `java.scripting`).

## Mục tiêu học tập

Khi nhúng một ngôn ngữ kịch bản vào ứng dụng Java, cần truyền dữ liệu từ host vào mã script, lấy kết quả trả về, và kiểm soát biến nào chỉ thuộc một lần chạy, biến nào được chia sẻ. **`Bindings`** chứa các cặp tên–giá trị; **`ScriptContext`** quản lý những `Bindings` theo phạm vi, cùng với input/output của script; **`ScriptEngine`** là bộ thực thi cụ thể dùng ngữ cảnh ấy để chạy một ngôn ngữ.

Sau bài này, bạn có thể:

1. Phân biệt `Bindings`, `ScriptContext`, `ScriptEngine` và `ScriptEngineManager`, hiểu luồng truyền object Java vào script và nhận lại giá trị.
2. Dự đoán kết quả tìm tên khi `ENGINE_SCOPE` và `GLOBAL_SCOPE` cùng định nghĩa một biến; hiểu giá trị `null` khác với biến không tồn tại.
3. Sử dụng `setAttribute`/`getAttribute`/`getAttributesScope`, `getBindings`/`setBindings` và `removeAttribute` đúng scope.
4. Phân biệt `engine.put/get`, `engine.setBindings`, `engine.eval(script, bindings)` và `engine.eval(script, context)`.
5. Thiết kế context riêng cho từng request, biết những gì thực sự được chia sẻ khi dùng chung `GLOBAL_SCOPE` hoặc cùng một object Java.
6. Dùng `ScriptEngineManager` phát hiện provider mà không mặc định Java 17 đã tích hợp JavaScript engine.
7. Biên dịch/chạy ví dụ Java 17 **không cần script engine bên ngoài**, sau đó chạy ví dụ tùy chọn khi có một JavaScript JSR-223 provider.
8. Nhận ra các rủi ro về vòng đời dữ liệu, concurrency, script injection, host object capabilities và bảo mật.

## 1. Bốn lớp của API kịch bản nhúng

JDK cung cấp API JSR-223 trong module `java.scripting`, nhưng **API không đồng nghĩa có sẵn một ngôn ngữ thực thi**.

| Thành phần | Vai trò | Dùng khi nào? |
| --- | --- | --- |
| `Bindings` | Bản đồ `Map<String,Object>` để gán tên script với giá trị Java | Chuẩn bị `user`, `config`, `requestId`, callable host objects |
| `ScriptContext` | Gom các `Bindings` theo scope, điều khiển tra cứu tên, `Reader`/`Writer`/error writer | Mỗi request/session cần context và output riêng |
| `ScriptEngine` | Chạy script của một ngôn ngữ cụ thể, nhận `ScriptContext` hoặc `Bindings` | `engine.eval(...)`, `engine.put/get(...)` |
| `ScriptEngineManager` | Khám phá/khởi tạo `ScriptEngineFactory` qua cơ chế provider, duy trì global bindings của manager | Chọn engine theo tên/extension/MIME type và cấu hình chia sẻ mặc định |

Mô hình dữ liệu:

~~~text
Java host
  |
  | new SimpleBindings(), put("user", javaObject)
  v
Bindings: { user -> Java object, locale -> "vi" }
  |
  | ScriptContext.setBindings(bindings, ENGINE_SCOPE)
  | ScriptContext.setBindings(global, GLOBAL_SCOPE)
  v
ScriptContext
  |-- ENGINE_SCOPE (100) : ưu tiên hơn
  |-- GLOBAL_SCOPE (200) : chỉ dùng nếu scope trước không khai báo tên
  |-- Reader / Writer / ErrorWriter
  |
  | engine.eval(scriptText, context)
  v
ScriptEngine provider cụ thể
  |
  | Script nhìn thấy biến theo convention của provider
  v
Kết quả Java Object hoặc ScriptException
~~~

**Điểm quan trọng:** `Bindings` không phải bản thân một script, `ScriptContext` không phải bộ thông dịch, và `ScriptEngineManager` cũng không chạy JavaScript. Chúng là lớp hợp đồng/integration cho những engine được cung cấp bởi nhà phát triển/runtime.

Từ Java 15, Nashorn đã bị loại khỏi JDK theo JEP 372. Trên Java 17 chuẩn, lệnh `new ScriptEngineManager().getEngineByName("JavaScript")` **có thể trả `null`** (và thường như vậy nếu chưa cài provider). Nếu có GraalJS JSR-223 hoặc engine bên thứ ba đã cấu hình, kết quả sẽ khác. Không nên suy ra một engine có hay không chỉ từ `java -version`; kiểm tra provider thực sự được discovery.

## 2. `Bindings` là một Map có key là tên thuộc tính

`javax.script.Bindings` kế thừa `Map<String,Object>`. Một object `SimpleBindings` là cách cơ bản để chứa các cặp tên–giá trị:

~~~java
Bindings values = new SimpleBindings();
values.put("user", "An");
values.put("attempts", 3);
values.put("active", true);
~~~

Đoạn này cần được đặt trong class có `import javax.script.*;` (hoặc imports tương đương).

Ý nghĩa:

- **Key** là String; giá trị là Java `Object` (có thể `String`, boxed primitive, `List`, `Map`, domain object, hoặc `null`).
- `Bindings` chỉ nắm **reference** đến giá trị Java, không tự deep-copy/serialize object. Thay đổi một object mutable có thể quan sát được ở nhiều context nếu chúng giữ cùng reference.
- `SimpleBindings` kiểm tra key theo hợp đồng: không truyền null/empty/không phải String trong những lệnh cần key. Không dùng map của dữ liệu nhập không tin cậy như một tập tên biến được cấp phát tùy ý mà không validate.
- `Bindings` không biểu diễn **một scope** khi đứng riêng. Nó trở thành ENGINE hoặc GLOBAL khi được gắn vào `ScriptContext` qua `setBindings`, hoặc được cung cấp cho một overload `eval`.
- Việc script có được truy cập object Java bằng cú pháp `user.name`, gọi getter, method hay field nào phụ thuộc **language engine** và chính sách host interoperability của provider. API chỉ chuyển reference, **không bảo đảm mọi engine sẽ giải mã mọi object Java theo cùng cách**.

### 2.1. `put` và `setAttribute`: hai cách thao tác cùng một map

Nếu một context đã gắn `Bindings`:

~~~java
Bindings engineValues = context.getBindings(ScriptContext.ENGINE_SCOPE);
engineValues.put("user", "An");
context.setAttribute("user", "Binh", ScriptContext.ENGINE_SCOPE);
~~~

Hai thao tác này cập nhật cùng bản đồ. `context.getAttribute("user")` sau đó sẽ trả `"Binh"` nếu không có logic engine khác can thiệp.

Đây là snippet minh họa với `context` đã khởi tạo. `setAttribute(name, value, scope)` khác với `getAttribute(name)`: lúc **ghi**, phải chỉ định scope; lúc đọc không chỉ định scope, context tìm theo thứ tự ưu tiên.

### 2.2. Map identity và vòng đời

Hai context có thể chứa:

- Hai `SimpleBindings` **riêng biệt** cho ENGINE_SCOPE: cập nhật một request không xuất hiện trong request kia.
- **Cùng một `Bindings` object** ở GLOBAL_SCOPE: cập nhật của context A có thể lộ ra ở context B.
- Hai map riêng nhưng mỗi map lại tham chiếu **cùng object mutable**: dù key/value maps tách nhau, object được dùng chung vẫn có thể bị thay đổi xuyên request.

Vì vậy không được kết luận “mỗi request có map mới, chắc chắn cách ly mọi trạng thái”. Isolation phải xem cả **scope map**, **object graph**, **engine internals** và concurrency.

## 3. `ScriptContext` và hai phạm vi thông dụng

`ScriptContext` định nghĩa hai scope chuẩn:

| Hằng số | Giá trị | Ý nghĩa điển hình |
| --- | ---: | --- |
| `ScriptContext.ENGINE_SCOPE` | **100** | Biến gắn với engine hoặc evaluation context; có **ưu tiên tra cứu cao hơn** |
| `ScriptContext.GLOBAL_SCOPE` | **200** | Biến chia sẻ mặc định theo context/manager khi được gắn; chỉ nhìn thấy khi không có tên cùng key ở ENGINE_SCOPE |

Thứ tự số **tăng dần** tương ứng **độ ưu tiên giảm dần**. Với `SimpleScriptContext`, `getScopes()` trả danh sách có thứ tự `[100, 200]`.

~~~text
getAttribute("theme")
   |
   +-- ENGINE_SCOPE có chứa key "theme"?
   |      |
   |      +-- Có -> trả giá trị trong ENGINE_SCOPE (kể cả null)
   |
   +-- Không -> GLOBAL_SCOPE có chứa key "theme"?
          |
          +-- Có -> trả giá trị trong GLOBAL_SCOPE
          +-- Không -> null
~~~

`GLOBAL_SCOPE` **không tự động** nghĩa là “global cho cả JVM” hay “global cho mọi engine trong process”. Nó là một namespace được **gắn** vào một `ScriptContext`. Khi dùng `ScriptEngineManager`, manager có bindings chung và thông thường gắn chúng vào những engine mà chính nó khởi tạo. Nếu tự tạo `SimpleScriptContext` hoặc tự gọi `engine.setContext(...)`, bạn phải tự quản lý phạm vi global.

### 3.1. `getAttribute(name)` và `getAttribute(name, scope)`

~~~java
Object resolved = context.getAttribute("theme");
Object local = context.getAttribute("theme", ScriptContext.ENGINE_SCOPE);
Object shared = context.getAttribute("theme", ScriptContext.GLOBAL_SCOPE);
~~~

- `getAttribute("theme")` trả giá trị ở **scope đầu tiên chứa tên**.
- `getAttribute("theme", ENGINE_SCOPE)` chỉ đọc map của scope ấy, không fallback global.
- `getAttribute("theme", GLOBAL_SCOPE)` chỉ đọc global, không bị local shadow.
- Không có key ở bất kỳ scope nào thì `getAttribute(name)` trả `null`.

### 3.2. Phân biệt **key có giá trị null** và **không có key**

Bẫy rất thực tế:

~~~java
context.setAttribute("theme", null, ScriptContext.ENGINE_SCOPE);
Object value = context.getAttribute("theme");
int scope = context.getAttributesScope("theme");
~~~

Nếu GLOBAL_SCOPE chứa `"theme"="global"`, kết quả vẫn:

~~~text
value == null
scope == 100
~~~

Vì `ENGINE_SCOPE` **đã khai báo tên** (dù giá trị null) nên global bị **che**. Khi muốn global hiện lại, phải **xóa key tại scope cao**, không chỉ set null:

~~~java
context.removeAttribute("theme", ScriptContext.ENGINE_SCOPE);
Object after = context.getAttribute("theme");  // "global"
~~~

`getAttributesScope(name)` trả số scope nhỏ nhất có tên đó, hoặc **`-1`** nếu không có ở scope nào. Đây là cách phân biệt chính thức giữa “giá trị null” và “chưa khai báo”.

### 3.3. `getBindings` và `setBindings`

~~~java
Bindings local = new SimpleBindings();
local.put("requestId", "req-1");
context.setBindings(local, ScriptContext.ENGINE_SCOPE);

Bindings global = new SimpleBindings();
global.put("region", "VN");
context.setBindings(global, ScriptContext.GLOBAL_SCOPE);
~~~

- `setBindings` **gắn/thay thế cả map** ở scope đó; không phải trộn từng key vào map cũ.
- Những code vẫn giữ reference đến map cũ sẽ không tự động thấy map mới sau khi `setBindings` thay thế.
- Với `SimpleScriptContext`, engine scope cần có Bindings phù hợp; global scope có thể chưa được gắn hoặc bị unset.
- Đặt cùng một `Bindings` vào hai context **cố ý chia sẻ cả map**; không có việc tạo bản sao bí mật.

**Quy tắc thiết kế:** một request mới nên bắt đầu từ một ENGINE_SCOPE map mới. Chỉ đặt giá trị thật sự có thể chia sẻ, phù hợp quyền truy cập, vào GLOBAL_SCOPE.

## 4. `ScriptEngine`: cách đưa dữ liệu vào nơi chạy script

`ScriptEngine` nhận dữ liệu qua default context hoặc context/bindings truyền trực tiếp cho mỗi lần eval.

### 4.1. `engine.put` và `engine.get`

~~~java
engine.put("user", "An");
Object user = engine.get("user");
~~~

- `put/get` của `ScriptEngine` làm việc với **ENGINE_SCOPE bindings của default context** của engine.
- `engine.put` tiện cho một phiên tương tác đơn giản, nhưng nếu nhiều request dùng chung engine, state có thể bị lưu lại giữa các lần eval.
- `engine.get("user")` không phải lệnh tìm mọi scope như `engine.getContext().getAttribute("user")`. Một name chỉ ở GLOBAL_SCOPE vẫn có thể thấy qua context lookup nhưng không nhất thiết có ở `engine.get`.
- `engine.setBindings(bindings, ENGINE_SCOPE)` thay **một scope của default context**; nó khác việc cung cấp bindings chỉ cho một lệnh eval.

Snippet này giả định có `ScriptEngine engine` hợp lệ; JDK 17 không bảo đảm provider tồn tại.

### 4.2. `eval(script)`: dùng default context

~~~java
Object result = engine.eval("user");
~~~

Đây chỉ là ví dụ với một engine **hiểu biểu thức `user`** và có biến đó. Ngôn ngữ/cú pháp script không do JSR-223 định nghĩa; một provider khác có thể yêu cầu cú pháp khác.

Lời gọi không có tham số context thường sử dụng default context của engine. Nếu bạn đã `engine.put("user","An")`, engine có thể thấy giá trị ấy thông qua binding của engine default context theo quy ước provider.

### 4.3. `eval(script, Bindings)`: ENGINE_SCOPE thay thế cho **evaluation đó**

~~~java
Bindings request = engine.createBindings();
request.put("user", "Binh");
Object result = engine.eval("user", request);
~~~

Hợp đồng `ScriptEngine.eval(String, Bindings)`: dùng `request` làm **ENGINE_SCOPE của phép eval này**. Với triển khai `AbstractScriptEngine`, một `ScriptContext` tạm được tạo để lấy ENGINE_SCOPE từ đối số, còn những scope khác, reader và writers được kế thừa từ default context.

**Không nhầm với `engine.setBindings(request, ENGINE_SCOPE)`:** overload `eval(script, request)` không phải lệnh thay vĩnh viễn ENGINE_SCOPE của engine default context. Tuy nhiên, nếu script sửa map `request` hoặc object bên trong map, chính map/object ấy vẫn bị thay đổi sau eval. “Temporary context” không có nghĩa các đối tượng được deep-copy hoặc các side effects tự rollback.

### 4.4. `eval(script, ScriptContext)`: truyền **đầy đủ phạm vi và I/O**

~~~java
ScriptContext requestContext = new SimpleScriptContext();
requestContext.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);
requestContext.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
requestContext.setAttribute("user", "An", ScriptContext.ENGINE_SCOPE);
Object result = engine.eval("user", requestContext);
~~~

Bằng cách này, caller quyết định:

- ENGINE_SCOPE map nào dùng cho request;
- GLOBAL_SCOPE map nào nhìn thấy (có thể chia sẻ hoặc cô lập);
- `Reader` / `Writer` / `ErrorWriter` của script;
- metadata context như `ScriptEngine.FILENAME` hoặc các key theo hợp đồng của provider.

`engine.eval(script, requestContext)` **không đòi** gọi `engine.setContext(requestContext)` trước đó. Nên hạn chế `setContext` toàn engine nếu muốn cô lập theo request và engine có thể được dùng lại.

### 4.5. Các overload khác

`ScriptEngine` còn có `eval(Reader)`, `eval(Reader, Bindings)` và `eval(Reader, ScriptContext)`. Chúng chỉ khác **nguồn script** là `Reader` thay vì String; những quy tắc về scopes và metadata vẫn tương ứng. Khi dùng Reader, host phải quản lý lifecycle và đóng input đúng cách.

Một engine có thể cung cấp thêm `Invocable` để gọi function đã định nghĩa trong script, hoặc `Compilable` để cache một script đã compile; **không phải mọi engine đều implement hai interface tùy chọn này**. Đừng biến code host thành phụ thuộc bắt buộc vào chúng nếu chưa kiểm tra `instanceof`.

## 5. `ScriptEngineManager`: global state và provider discovery

Dùng manager để tìm engine:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    System.out.println("No JavaScript JSR-223 provider installed");
}
~~~

Đây là đoạn Java minh họa trong một class có import `javax.script.*`. Việc tên `"JavaScript"` có được một provider nhận hay không còn tùy provider/registration.

`ScriptEngineManager` dùng `ServiceLoader` để tìm `ScriptEngineFactory` trên classpath/module path phù hợp với class loader. Có thể kiểm tra:

~~~java
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
~~~

Không ép output cố định, vì danh sách provider tùy môi trường. Hãy xác nhận đã **cài đúng artifact JSR-223 provider** và các runtime dependencies của engine. Một thư viện thực thi ngôn ngữ chưa chắc đã tự đăng ký `ScriptEngineFactory` theo JSR-223.

### 5.1. Global của manager không phải global của mọi manager

~~~java
manager.put("region", "VN");
Bindings global = manager.getBindings();
~~~

Các engine được tạo bởi manager này có thể nhận/global-share các binding mặc định đó. Nhưng:

- `new ScriptEngineManager()` khác là một manager khác, không tự kế thừa map vừa tạo.
- Engine tạo trực tiếp ngoài manager hoặc context tạo thủ công không tự động thuộc cùng global map.
- `manager.put` thay đổi map global của manager, **không** tương đương `engine.put` (một default ENGINE_SCOPE).
- `manager.getBindings()` trả **map đang dùng**, không phải snapshot bất biến.
- Global có thể chứa object có quyền lớn; không đưa API nhạy cảm vào đó khi mọi script được tạo qua manager đều không đáng tin.

### 5.2. Tên scope “GLOBAL” không tạo transaction, sandbox hay thread safety

GLOBAL_SCOPE là một kênh chia sẻ dữ liệu, không bảo đảm atomic snapshot và không đồng nghĩa các script được chạy tuần tự. Nếu request A/B cùng dùng một map global mutable, việc thay `region` hoặc `user` ở một request có thể ảnh hưởng request còn lại.

Nên phân biệt:

- Giá trị cấu hình **read-only hoặc immutable**: có thể an toàn hơn khi chia sẻ, tùy nội dung.
- Đối tượng mutable có state chung: phải dùng synchronization/immutability/copy hoặc phân vùng.
- Thông tin người dùng, tenant, token, request-private data: chỉ cho scope của request và kiểm tra object không bị chia sẻ xuyên tenant.
- `SimpleBindings` dùng Map mutable thông thường; không được mặc định thread-safe.

## 6. Demo Java 17 độc lập: scope, shadowing, null và chia sẻ

Ví dụ này **không cần cài JavaScript/Groovy/GraalJS engine**. Nó thực hành đúng phần dữ liệu của JSR-223 trên `SimpleScriptContext` và `SimpleBindings`. Sau đó mới có demo `eval` nếu môi trường có provider.

**File:** `BindingsScopeDemo.java`

~~~java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineManager;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class BindingsScopeDemo {
    public static void main(String[] args) {
        Bindings sharedGlobal = new SimpleBindings();
        sharedGlobal.put("language", "vi");
        sharedGlobal.put("theme", "global");

        ScriptContext first = new SimpleScriptContext();
        ScriptContext second = new SimpleScriptContext();
        first.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
        second.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
        first.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);
        second.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);

        System.out.println("scopes=" + first.getScopes());
        System.out.println("first.theme.initial=" + first.getAttribute("theme"));
        first.setAttribute("theme", "engine", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.theme.override=" + first.getAttribute("theme"));
        System.out.println("first.theme.scope=" + first.getAttributesScope("theme"));
        System.out.println("second.theme=" + second.getAttribute("theme"));

        first.setAttribute("theme", null, ScriptContext.ENGINE_SCOPE);
        System.out.println("nullShadowsGlobal=" +
                (first.getAttribute("theme") == null
                && first.getAttributesScope("theme") == ScriptContext.ENGINE_SCOPE));
        first.removeAttribute("theme", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.theme.restored=" + first.getAttribute("theme"));

        Bindings firstEngine = first.getBindings(ScriptContext.ENGINE_SCOPE);
        firstEngine.put("user", "An");
        System.out.println("first.user=" + first.getAttribute("user"));
        System.out.println("second.user.scope=" + second.getAttributesScope("user"));
        first.setAttribute("user", "Binh", ScriptContext.ENGINE_SCOPE);
        System.out.println("bindingsAreLive=" + firstEngine.get("user"));
        sharedGlobal.put("language", "en");
        System.out.println("second.language=" + second.getAttribute("language"));
        System.out.println("globalShared=" +
                (first.getBindings(ScriptContext.GLOBAL_SCOPE)
                        == second.getBindings(ScriptContext.GLOBAL_SCOPE)));

        ScriptEngineManager manager = new ScriptEngineManager();
        manager.getBindings().put("app", "demo");
        System.out.println("manager.app=" + manager.getBindings().get("app"));
    }
}
~~~

### 6.1. Chạy với Java 17+

Từ thư mục chứa `BindingsScopeDemo.java`:

~~~bash
javac --release 17 -d out BindingsScopeDemo.java
java -cp out BindingsScopeDemo
~~~

Cài JDK 17+; không cần thêm JAR hay provider engine nào. `SimpleScriptContext` và `ScriptEngineManager` là thành phần có trong module `java.scripting` của JDK.

**Stdout chính xác đã được biên dịch/chạy kiểm chứng:**

~~~text
scopes=[100, 200]
first.theme.initial=global
first.theme.override=engine
first.theme.scope=100
second.theme=global
nullShadowsGlobal=true
first.theme.restored=global
first.user=An
second.user.scope=-1
bindingsAreLive=Binh
second.language=en
globalShared=true
manager.app=demo
~~~

### 6.2. Diễn giải các bước

- `scopes=[100, 200]` xác nhận hai scope chuẩn theo thứ tự ưu tiên.
- `first.theme.initial=global` vì ENGINE_SCOPE của `first` chưa khai báo `theme`; fallback tìm ở GLOBAL_SCOPE.
- `first.theme.override=engine`: khi `first` tự khai báo `theme` ở ENGINE_SCOPE, giá trị đó có ưu tiên hơn global. `first.theme.scope=100` chỉ ra scope có key đầu tiên.
- `second.theme=global`: ENGINE_SCOPE của `second` là map độc lập; cập nhật local của `first` không xuất hiện ở `second`.
- `nullShadowsGlobal=true`: một binding có giá trị null vẫn được coi là khai báo tên ở scope cao. Muốn fallback global phải `removeAttribute`.
- `first.theme.restored=global`: xóa key local làm giá trị global nhìn thấy trở lại.
- `first.user=An` và `bindingsAreLive=Binh`: `Bindings` là map sống, không phải snapshot của kết quả `getBindings`.
- `second.user.scope=-1` chứng minh key `user` chưa được khai báo ở bất kỳ scope nào của context thứ hai.
- `second.language=en` và `globalShared=true`: hai context đã được gắn **cùng** `Bindings` object, nên cập nhật global qua map ấy sẽ được context B nhìn thấy.
- `manager.app=demo`: `ScriptEngineManager` vẫn quản lý được global bindings ngay cả khi môi trường không cài một `ScriptEngine` cụ thể.

### 6.3. Đổi quy tắc chia sẻ để tự thử

Thay:

~~~java
second.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
~~~

bằng:

~~~java
Bindings isolated = new SimpleBindings();
isolated.put("language", "vi");
isolated.put("theme", "global");
second.setBindings(isolated, ScriptContext.GLOBAL_SCOPE);
~~~

Đây là **hai đoạn cần thay thế trong file demo**, không phải hai file riêng. Khi đó `globalShared=false`, và sau `sharedGlobal.put("language","en")`, `second.language` vẫn là `vi`. Qua đó thấy rõ “GLOBAL” là **map mà bạn chủ động chia sẻ**, không phải vùng global tự động trên toàn VM.

## 7. Demo chạy script khi có provider JSR-223

Java 17 không nhất thiết cài một `ScriptEngine` JavaScript. Vì vậy ví dụ này được viết để **không ném NullPointerException khi engine không có**. Phần thực thi biểu thức JavaScript cần một provider JSR-223 tương thích; nếu chưa cài provider, chương trình chỉ báo thiếu engine.

**File:** `OptionalJavaScriptEngineDemo.java`

~~~java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class OptionalJavaScriptEngineDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");
        if (engine == null) {
            System.out.println("no-jsr223-javascript-engine");
            return;
        }

        Bindings global = new SimpleBindings();
        global.put("region", "VN");

        Bindings request = engine.createBindings();
        request.put("user", "An");
        request.put("region", "HCM");

        ScriptContext context = new SimpleScriptContext();
        context.setBindings(global, ScriptContext.GLOBAL_SCOPE);
        context.setBindings(request, ScriptContext.ENGINE_SCOPE);

        Object result = engine.eval("user + ':' + region", context);
        System.out.println("result=" + result);

        Object temporary = engine.eval("user + ':' + region", request);
        System.out.println("temporary=" + temporary);
        System.out.println("persistentUser=" + engine.get("user"));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac --release 17 -d out OptionalJavaScriptEngineDemo.java
java -cp out OptionalJavaScriptEngineDemo
~~~

**Khi không có JavaScript provider**, stdout đã kiểm chứng:

~~~text
no-jsr223-javascript-engine
~~~

**Khi có provider phù hợp**, nhánh còn lại sẽ thực thi biểu thức JavaScript `user + ':' + region`. Với bindings đang gắn trong context, kết quả mong đợi của lần eval đầu là `An:HCM`, do `region="HCM"` ở ENGINE_SCOPE che `region="VN"` ở GLOBAL_SCOPE. Lệnh `eval(..., request)` dùng `request` làm ENGINE_SCOPE của chính lần chạy đó, không thay default scope của engine; `engine.get("user")` đọc default ENGINE_SCOPE, không phải `request`.

**Không đưa ra “stdout chính xác” cho nhánh có provider**, vì sự hiện diện, object wrapping và chính sách JS host interop có thể khác. Provider có thể sử dụng tên alias khác `"JavaScript"` hoặc yêu cầu cấu hình module/classpath riêng. Phần **biên dịch** chương trình không cần provider; chỉ phần **thực thi script** mới cần.

### 7.1. Phân biệt ba lệnh đánh giá

~~~java
engine.eval(source);           // default ScriptContext của engine
engine.eval(source, bindings); // ENGINE_SCOPE tạm của evaluation
engine.eval(source, context);  // ScriptContext do caller cung cấp
~~~

Đây là ví dụ cú pháp với biến `source`/`bindings`/`context` đã được khai báo, không phải chương trình độc lập.

| Lời gọi | ENGINE_SCOPE được dùng | GLOBAL_SCOPE & I/O |
| --- | --- | --- |
| `eval(source)` | Map trong default context | Theo default context |
| `eval(source, bindings)` | Map `bindings` của lần eval | Với `AbstractScriptEngine`, lấy các scope/I/O còn lại từ default context |
| `eval(source, context)` | Map trong `context` do caller truyền | Theo chính `context` được truyền |

Đối với request isolation, `eval(source, context)` là lựa chọn rõ ràng nhất vì caller quyết định cả local/global và readers/writers. Với provider đã có default scope phù hợp, `eval(source, bindings)` là cách ngắn gọn.

## 8. ScriptContext còn quản lý đầu vào và đầu ra

`ScriptContext` không chỉ là tên biến. Nó có:

- `getReader()/setReader(Reader)`: nguồn input cho script khi provider hỗ trợ.
- `getWriter()/setWriter(Writer)`: nơi script có thể ghi stdout theo quy tắc provider.
- `getErrorWriter()/setErrorWriter(Writer)`: nơi gửi thông báo/lỗi do script chủ động in.
- `ScriptEngine.FILENAME`: một key metadata có thể hữu ích để engine báo tên nguồn trong diagnostic, tùy provider.

Ví dụ host muốn thu output vào memory:

~~~java
java.io.StringWriter output = new java.io.StringWriter();
ScriptContext context = new SimpleScriptContext();
context.setWriter(output);
// Nếu engine cụ thể dùng ScriptContext.getWriter():
// engine.eval(scriptText, context);
String collected = output.toString();
~~~

Đoạn này là **minh họa** với `engine`/`scriptText` chưa được khai báo, không phải một chương trình độc lập. Script syntax như `print(...)`/`console.log(...)` không được JSR-223 tiêu chuẩn hóa; một provider có thể viết ra console hệ thống thay vì `context.getWriter()` tùy API ngôn ngữ của nó. Không kết luận `StringWriter` tự động chặn tất cả stdout, stderr, network access hoặc logging của object Java do script gọi.

Nếu muốn Reader/Writer **riêng mỗi request**, nên tạo context mới và gắn writer riêng. Khi dùng chung writer giữa nhiều engine threads, phải có chính sách đồng bộ hoặc cách phân tách kết quả, tránh trộn output.

## 9. Truyền object Java vào script: phạm vi không phải quyền truy cập

### 9.1. Giá trị nào có thể đặt vào Bindings?

`Bindings` nhận `Object`, vì vậy host có thể đưa vào script những thứ như:

~~~java
Bindings bindings = new SimpleBindings();
bindings.put("username", "An");
bindings.put("retryLimit", 3);
bindings.put("tags", java.util.List.of("java", "runtime"));
bindings.put("options", java.util.Map.of("mode", "safe"));
~~~

Đây là một đoạn hợp lệ bên trong method với imports tương ứng. Java-side map hỗ trợ các object này, **nhưng cách gọi method, iteration, property access từ script phụ thuộc provider**. Ví dụ `tags.get(0)` là Java syntax; không phải mọi scripting language có đúng cú pháp ấy.

**Nên dùng kiểu dữ liệu nhỏ, immutable và tối thiểu quyền.** Đừng tự động đưa nguyên container `ApplicationContext`, database connection, class loader, `Runtime` hoặc một object service nhiều quyền vào script chỉ vì Bindings cho phép.

### 9.2. Objects chia sẻ theo reference

Nếu host gắn một `ArrayList` vào hai context, hai script có thể nhìn cùng list object qua bindings dù hai maps khác nhau. Khi script engine cho phép gọi các method Java trên object ấy, nó có thể mutate state, làm lộ dữ liệu giữa sessions.

Nếu cần isolation:

- Tạo bản sao dữ liệu theo request, nhất là các collections mutable.
- Chuyển object phức tạp sang DTO/interface chỉ có operations cần thiết.
- Không tái sử dụng một mutable `Bindings` cho nhiều request không cùng trust boundary.
- Đặt global chỉ những giá trị cho phép mọi script được chia sẻ.
- Cân nhắc isolate process cho script không tin cậy; JSR-223 scopes **không phải security boundary**.

### 9.3. Output và conversion

`engine.eval(script, context)` trả `Object`; provider có thể trả `String`, boxed number, boolean, một object wrapper, hoặc `null`. Không nên ép `(String) engine.eval(...)` khi chưa biết engine contract. Thay vào đó, kiểm tra `instanceof`, validate schema/giá trị, và chuyển đổi dữ liệu ở ranh giới.

Lỗi parser/runtime của script thường được engine báo bằng `ScriptException`. `ScriptException` có thể chứa vị trí lỗi (file/line/column) tùy provider và cách gắn metadata. Nhưng nếu object Java do script gọi ném runtime error, cách engine bọc/lan truyền ngoại lệ có thể khác; xem nguyên nhân thực, không giả định mọi lỗi luôn có một kiểu duy nhất.

## 10. Scope không giải quyết đồng thời và bảo mật

### 10.1. Data race và trạng thái engine

Một câu hỏi có hai phần độc lập:

1. **Map nào được dùng?** ENGINE_SCOPE/GLOBAL_SCOPE trong context, chia sẻ hay riêng.
2. **Ai có thể đồng thời sử dụng map/engine?** Nhiều thread có thể cùng thay global, hoặc engine có internal mutable state.

Không mặc định `SimpleBindings` thread-safe. Nếu provider có `ScriptEngineFactory.getParameter("THREADING")`, hãy đọc ý nghĩa theo chính provider; giá trị đó không biến mọi object trong bindings thành thread-safe. Một engine cho phép đa luồng chưa chắc cho phép chia sẻ một request context đang bị thay đổi không đồng bộ.

Một kiến trúc dễ kiểm soát:

~~~text
Shared script source / compiled artifact (nếu provider hỗ trợ an toàn)
                   |
           +-------+-------+
           |               |
        Request A        Request B
           |               |
   ENGINE_SCOPE A   ENGINE_SCOPE B
   private objects  private objects
           \               /
            \             /
       GLOBAL_SCOPE: immutable, approved config
~~~

Nếu cùng một engine instance cần chạy đồng thời, phải xác minh **threading contract của provider**. Nhiều ứng dụng chọn pool engine instances/context theo request để giảm chia sẻ không chủ ý.

### 10.2. Script injection khác với variable binding

Đưa dữ liệu vào `Bindings` là một cách **tránh nối trực tiếp chuỗi dữ liệu người dùng thành script source**. Đừng tạo script dạng:

~~~java
String source = "checkUser('" + untrustedUsername + "')";
~~~

Đây là **đoạn chống chỉ định**, giả định `untrustedUsername` đã có. Input chứa dấu nháy/ký tự script có thể thay đổi source được parse. Thay vào đó, truyền value qua bindings và giữ source code cố định:

~~~java
bindings.put("username", untrustedUsername);
Object result = engine.eval("checkUser(username)", bindings);
~~~

Đây là snippet minh họa với engine hỗ trợ cú pháp JavaScript-like, `bindings` và `untrustedUsername` đã khai báo. Binding tránh dạng source-string injection nêu trên, **không tự động làm script an toàn khi script được phép gọi object host đầy quyền**.

### 10.3. Mô hình đe dọa

JSR-223 là integration API, không phải sandbox. Một provider có thể cho script gọi host Java methods, nạp class, truy cập file/network hoặc reflection tùy cấu hình. Khi script **không tin cậy**:

- Không đưa object có quyền mạnh vào bindings, kể cả ở GLOBAL_SCOPE.
- Xác nhận giới hạn host interop/class access của provider; tính năng sandbox của mỗi engine khác nhau.
- Thiết lập giới hạn thời gian, bộ nhớ, CPU và I/O ở ranh giới thích hợp; timeout bằng `Future.cancel` không bảo đảm dừng mọi native/engine computation.
- Có audit logs, validate input/output, và nếu rủi ro cao thì thực thi script trong **process/container bị hạn chế quyền**.
- Không xem `ScriptContext` là cơ chế cách ly tenant tự động.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | Không có JSR-223 JavaScript provider được discovery | `manager.getEngineFactories()`; kiểm tra classpath/module path và đăng ký `ScriptEngineFactory` |
| `engine.get("region") == null` nhưng script đọc được `region` | `region` nằm ở GLOBAL_SCOPE, còn `engine.get` đọc ENGINE_SCOPE | Dùng `engine.getContext().getAttribute("region")` |
| Biến global bị “mất” khi gọi script | ENGINE_SCOPE có key trùng, kể cả value null | `getAttributesScope(name)` và `getBindings(ENGINE_SCOPE).containsKey(name)` |
| `removeAttribute` không làm biến biến mất hoàn toàn | Giá trị ở scope thấp lại hiện ra | Kiểm tra GLOBAL_SCOPE; xóa ở đúng scope nếu có quyền |
| Request B đọc được user của request A | Reuse một Bindings map hoặc object mutable; default engine context được share | Cấp ENGINE_SCOPE map/engine context riêng, giới hạn global và object references |
| `eval(script, bindings)` không thay giá trị thấy qua `engine.get` | Bindings chỉ được dùng làm ENGINE_SCOPE cho lần eval | Dùng `engine.setBindings` khi thực sự muốn thay default, hoặc giữ request tách biệt |
| `ScriptException` do cú pháp biến | Script language không hiểu syntax của snippet | Xác nhận engine name/provider và cú pháp của chính ngôn ngữ |
| `ClassCastException` khi đọc kết quả | Provider trả object wrapper/number khác loại | Kiểm tra runtime type và schema |
| `NullPointerException` khi dùng engine | `getEngineByName` trả null và code gọi `eval` ngay | Kiểm tra null, báo thiếu provider rõ ràng |
| `StringWriter` không thu được mọi output | Provider dùng API console khác hoặc code host tự ghi vào System.out | Xem tài liệu provider, không coi Writer là OS-level redirection |
| Chia sẻ GLOBAL_SCOPE gây race | Mutable SimpleBindings được dùng đồng thời | Thay immutable data, phân quyền request, dùng synchronization có chủ đích |
| Script chạy được nhưng có quyền quá rộng | Đã đưa service/reference nguy hiểm vào Bindings | Giới hạn capability/host access, isolate process khi cần |
| `Bindings.put` lỗi khi key lạ | Key null/empty hoặc không phải String | Validate variable names, dùng danh sách key rõ ràng |

### Quy trình debug ngắn

1. Xác nhận **provider** có tồn tại: danh sách `getEngineFactories()`, tên engine, classpath/module path.
2. Xác định **overload eval** thực tế: `eval(script)`, `eval(script, bindings)` hay `eval(script, context)`.
3. Kiểm tra map được gắn ở `ENGINE_SCOPE` và `GLOBAL_SCOPE` (reference identity, key presence).
4. Dùng `getAttributesScope(name)` để phân biệt shadowing và null với key không tồn tại.
5. Xem object Java trong binding có mutable/share không; validate tên biến và quyền truy cập.
6. Kiểm tra syntax/script exception theo provider; không giả định mọi engine đều dùng JavaScript.
7. Khi script chạy đồng thời hoặc không tin cậy, kiểm tra threading, host interop, I/O, timeout và isolation độc lập với scope.

## 12. Bài tập tự kiểm tra

**Bài 1 — Scope lookup.** Đặt `GLOBAL_SCOPE.theme="dark"`, `ENGINE_SCOPE.theme="light"`. `getAttribute("theme")` trả gì? `getAttribute("theme",GLOBAL_SCOPE)` trả gì?

**Bài 2 — Null shadow.** Thay ENGINE_SCOPE.theme bằng null. `getAttribute("theme")` trả null hay dark? `getAttributesScope("theme")` trả bao nhiêu? Phải làm gì để dark hiện lại?

**Bài 3 — Không có biến.** Tại sao `getAttribute("unknown")==null` chưa chứng minh key không tồn tại? Kết hợp `getAttributesScope` hoặc `containsKey` thế nào để phân biệt?

**Bài 4 — Context isolation.** Tạo hai `SimpleScriptContext` và hai local `SimpleBindings`. Nếu cả hai cùng trỏ đến một `ArrayList` mutable, liệu có còn cô lập hoàn toàn không? Đề xuất cách sửa.

**Bài 5 — eval overload.** Giả sử default engine scope có `user="A"`, global có `region="VN"`, còn request bindings có `user="B"`. So sánh hai lời gọi `eval("user + region")` và `eval("user + region", request)` trong engine có cú pháp tương ứng.

**Bài 6 — Manager global.** Tạo hai `ScriptEngineManager` riêng, mỗi manager có global bindings riêng. Vì sao không thể suy ra rằng global của manager A tự lan sang manager B?

**Bài 7 — Provider detection.** Chạy `OptionalJavaScriptEngineDemo` trên JDK17 không cài provider. Vì sao chương trình compile được nhưng không chạy biểu thức JavaScript? Khi cài provider, cách kiểm tra tên engine hợp lệ là gì?

**Bài 8 — Output capture.** Đặt `ScriptContext.setWriter(new StringWriter())`. Vì sao chỉ từ thao tác đó chưa thể bảo đảm mọi `System.out.println` do object Java gọi từ script đều bị thu lại?

**Bài 9 — Bảo mật.** Một ứng dụng đưa cả `DataSource` và `Runtime` vào GLOBAL_SCOPE dùng chung cho script khách hàng. Hãy xác định rủi ro, cách giảm quyền và ranh giới process cần dùng với script không tin cậy.

**Bài 10 — Request lifecycle.** Thiết kế một API `execute(script, requestData)` bằng `ScriptContext` mới cho mỗi request, ENGINE_SCOPE chứa input, GLOBAL_SCOPE chỉ chứa cấu hình immutable; giải thích cách xử lý output và exception.

## 13. Tóm lược

- **`Bindings`** là map tên–giá trị Java; **`ScriptContext`** gắn map ấy vào scopes và quản lý Reader/Writer; **`ScriptEngine`** là bộ thực thi script; **`ScriptEngineManager`** giúp discovery và cấu hình global mặc định.
- **`ENGINE_SCOPE=100` ưu tiên hơn `GLOBAL_SCOPE=200`.** Một key ở ENGINE_SCOPE có giá trị null vẫn shadow global; phải `removeAttribute` để fallback.
- **`getAttributesScope(name)`** cho biết nơi key thực sự được khai báo, trả `-1` nếu không tồn tại; `getAttribute(name)` có thể trả null trong cả hai trường hợp.
- **`engine.put/get`** thao tác trên default ENGINE_SCOPE, còn **`eval(script, bindings)`** dùng Bindings cho lần evaluation và **`eval(script, context)`** nhận toàn bộ context.
- **GLOBAL_SCOPE không phải global cho cả JVM**: mức chia sẻ phụ thuộc vào object `Bindings` bạn gắn và manager tạo engine.
- Java 17 có API `java.scripting` nhưng **không bảo đảm có sẵn JavaScript engine**; phải kiểm tra `getEngineByName`/`getEngineFactories` và cài provider JSR-223 nếu cần.
- Bindings chuyển **references**, không deep-copy hoặc sandbox; phải thiết kế per-request isolation, threading và host-access security riêng.

## Tài liệu tham khảo chính thức

- [Java SE 17 — `javax.script.Bindings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [Java SE 17 — `SimpleBindings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html)
- [Java SE 17 — `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html)
- [Java SE 17 — `SimpleScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html)
- [Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html)
- [Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372)
