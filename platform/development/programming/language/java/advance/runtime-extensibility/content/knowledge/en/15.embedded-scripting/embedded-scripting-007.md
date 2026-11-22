# Truyền dữ liệu qua Bindings và chọn ENGINE_SCOPE hoặc GLOBAL_SCOPE

## 1. Bài toán truyền dữ liệu vào kịch bản nhúng

Trong ứng dụng Java có tích hợp ngôn ngữ kịch bản qua **JSR-223 Scripting API** (`javax.script`), mã chủ thường cần cung cấp thông tin cho script: cấu hình, mã người dùng, dữ liệu đầu vào, các tham số tính toán hoặc một dịch vụ Java được phép gọi. Ghép thẳng dữ liệu vào văn bản script vừa khó bảo trì vừa có nguy cơ sai cú pháp hoặc tạo lỗ hổng nếu dữ liệu không đáng tin. `Bindings` là cách truyền **tên → giá trị** cho engine qua API rõ ràng.

Ba đối tượng cần phân biệt:

- **`Bindings`:** giao diện kế thừa `Map<String, Object>`, chứa các cặp tên–đối tượng; `SimpleBindings` là một triển khai mặc định đơn giản.
- **`ScriptContext`:** giữ các Bindings được gắn ở những **scope** cụ thể cùng các luồng `Reader`, `Writer` và `errorWriter` cho lần thực thi.
- **`ScriptEngine`:** xử lý mã của một ngôn ngữ kịch bản; truy cập ngữ cảnh để thấy các giá trị và ghi kết quả.

Một ví dụ truyền dữ liệu vào một engine đã được cài đặt:

```java
// Đoạn minh họa; giả định engine đã có và scriptSource hợp lệ.
Bindings invocation = engine.createBindings();
invocation.put("userId", "u123");
invocation.put("attempt", 3);

Object result = engine.eval(scriptSource, invocation);
```

Trong trường hợp này, `invocation` là **ENGINE_SCOPE của lần eval**. Tên khóa Java có thể xuất hiện như biến của script, nhưng cách truy cập biến Java hoặc chuyển đổi object còn tùy ngôn ngữ/`ScriptEngine`.

**Chú ý JDK 17:** Java cung cấp gói `javax.script`, nhưng **không bảo đảm có sẵn một JavaScript engine**. Nashorn đã bị loại khỏi JDK từ Java 15. Nếu `new ScriptEngineManager().getEngineByName("javascript")` trả về `null` thì thiếu provider, không phải lỗi Bindings. Ví dụ chạy được tại mục 4 sử dụng `SimpleScriptContext` và `SimpleBindings`, không đòi hỏi cài thêm engine nào.

## 2. ENGINE_SCOPE và GLOBAL_SCOPE khác nhau thế nào?

`ScriptContext` có hai hằng chuẩn:

| Scope | Hằng số (giá trị) | Ý nghĩa | Dữ liệu thích hợp |
|---|---|---|---|
| **ENGINE_SCOPE** | `ScriptContext.ENGINE_SCOPE` (`100`) | Tập biến ở mức engine/context đang dùng | Input riêng một lần chạy, biến tạm, dữ liệu request |
| **GLOBAL_SCOPE** | `ScriptContext.GLOBAL_SCOPE` (`200`) | Tập biến dùng chung khi các context/engine được gắn **cùng Bindings** | Cấu hình chung, giá trị mặc định được phép chia sẻ |

Tên “GLOBAL_SCOPE” dễ gây hiểu nhầm. Nó **không** tạo một bảng giá trị toàn JVM. Một `ScriptContext` chỉ nhìn thấy global Bindings mà **chính context đó** được gắn. `ScriptEngineManager` có một global Bindings dùng chung cho các engine do manager tạo; hai manager độc lập không mặc nhiên chia sẻ map. Nếu hai context cùng nhận một đối tượng Bindings qua `setBindings(..., GLOBAL_SCOPE)`, chúng mới thực sự chia sẻ dữ liệu đó.

### 2.1. Thứ tự tra cứu: engine ưu tiên global

Các phương thức `ScriptContext` hoạt động như sau:

- `getAttribute("key")` dò theo scope từ giá trị số thấp lên cao: **ENGINE_SCOPE (100) trước GLOBAL_SCOPE (200)**.
- `getAttribute("key", ScriptContext.GLOBAL_SCOPE)` chỉ đọc global, không bị engine che.
- `setAttribute("key", value, ScriptContext.ENGINE_SCOPE)` đặt tên vào engine. Tương tự với GLOBAL_SCOPE.
- `getAttributesScope("key")` trả về scope đang chứa tên được ưu tiên, hoặc `-1` nếu tên chưa được định nghĩa.
- `removeAttribute("key", ScriptContext.ENGINE_SCOPE)` chỉ xóa biến engine; nếu tên còn ở global, lần tra cứu mặc định sẽ thấy bản global.

Ví dụ có tên `tax` trùng trong cả hai scope:

```text
ENGINE_SCOPE: tax = 5
GLOBAL_SCOPE: tax = 10

getAttribute("tax")                           -> 5
getAttribute("tax", GLOBAL_SCOPE)             -> 10
getAttributesScope("tax")                     -> 100

Sau khi removeAttribute("tax", ENGINE_SCOPE):
getAttribute("tax")                           -> 10
getAttributesScope("tax")                     -> 200
```

**Shadowing không phải ghi đè global.** Biến `tax` trong ENGINE_SCOPE chỉ che giá trị global khi dùng lookup không chỉ scope. Xóa bản engine không làm mất `tax` của global.

Nếu một khóa được đặt với giá trị `null`, `getAttribute` vẫn có thể trả về `null` dù tên tồn tại. Để phân biệt “không tồn tại” và “tồn tại nhưng null”, dùng `getAttributesScope` hoặc `containsKey` trên đúng Bindings (nếu khác null); đừng chỉ kiểm tra `getAttribute(name) == null`.

### 2.2. Vòng đời không được quyết định bởi tên scope

- ENGINE_SCOPE trong ngữ cảnh mặc định của một `ScriptEngine` có thể tồn tại qua **nhiều lời gọi eval** nếu engine/context được tái sử dụng. Nó không tự được xóa sau từng yêu cầu.
- GLOBAL_SCOPE có thể dùng chung nếu hai context/engine cùng trỏ tới một map global. Thay đổi vào map có thể hiển thị ở tất cả bên dùng chung.
- Một Bindings còn được nơi khác giữ reference thì có thể sống tiếp dù một lần chạy script đã kết thúc.
- Không có đảm bảo thread-safety chỉ vì dữ liệu nằm trong GLOBAL_SCOPE; `SimpleBindings` thường dựa vào `HashMap`.

Vì vậy, cách chia scope phù hợp với **chủ sở hữu và thời gian sống thực tế của dữ liệu**, không chỉ với tên “engine/global”.

## 3. Tạo Bindings và gắn vào ScriptContext

### 3.1. Khởi tạo một Bindings

```java
Bindings local = new SimpleBindings();
local.put("userId", "u123");
local.put("retryCount", 3);
local.put("enabled", Boolean.TRUE);
```

Đoạn này cần import `javax.script.Bindings` và `javax.script.SimpleBindings`. Khóa của Bindings phải là chuỗi khác `null` và không rỗng; khóa không hợp lệ có thể ném `NullPointerException` hoặc `IllegalArgumentException`. Giá trị là Object, nhưng việc biến thành đối tượng của ngôn ngữ script phụ thuộc engine.

### 3.2. Gắn vào hai scope

```java
ScriptContext context = new SimpleScriptContext();

Bindings engineValues = new SimpleBindings();
engineValues.put("requestId", "req-17");

Bindings globalValues = new SimpleBindings();
globalValues.put("appName", "Portal");

context.setBindings(engineValues, ScriptContext.ENGINE_SCOPE);
context.setBindings(globalValues, ScriptContext.GLOBAL_SCOPE);

System.out.println(context.getAttribute("requestId")); // req-17
System.out.println(context.getAttribute("appName"));   // Portal
```

Đây là một đoạn mã minh họa có thể đặt bên trong phương thức Java và import `javax.script.*`. `SimpleScriptContext` có sẵn ENGINE_SCOPE bindings, nhưng GLOBAL_SCOPE mặc định có thể là `null` cho tới khi được đặt. `setBindings` **gắn tham chiếu tới map**, không tạo bản sao.

Không được đặt `null` vào `ENGINE_SCOPE` của `SimpleScriptContext`; scope này phải có Bindings hợp lệ. Nếu chưa cần global, có thể để GLOBAL_SCOPE chưa được thiết lập. Muốn nhiều context dùng chung giá trị, nên chủ động chia sẻ một object Bindings và xác định chính sách cập nhật của nó.

### 3.3. API setAttribute và getBindings không mâu thuẫn nhau

Hai thao tác sau đều tác động vào ENGINE_SCOPE của cùng context:

```java
context.setAttribute("requestId", "req-17", ScriptContext.ENGINE_SCOPE);
context.getBindings(ScriptContext.ENGINE_SCOPE)
       .put("requestId", "req-17");
```

Chúng khác cách viết, không phải hai bảng biến riêng biệt. Khi sử dụng `ScriptEngine` dựa trên `AbstractScriptEngine`, các thao tác tương ứng:

```java
engine.put("requestId", "req-17");
engine.getBindings(ScriptContext.ENGINE_SCOPE)
      .put("requestId", "req-17");
engine.getContext()
      .setAttribute("requestId", "req-17", ScriptContext.ENGINE_SCOPE);
```

đều hướng vào ENGINE_SCOPE trong ngữ cảnh mặc định. `AbstractScriptEngine.get(key)` đọc ENGINE_SCOPE; nếu muốn xét cả global và engine, dùng `engine.getContext().getAttribute(key)`. Không nên coi `engine.get(key)` là phép lookup tự động qua mọi scope mà không đọc hợp đồng của engine cụ thể.

## 4. Ví dụ Java 17 hoàn chỉnh, không cần script engine ngoài

Ví dụ chỉ sử dụng API chuẩn `javax.script`. Chúng ta tạo hai `SimpleScriptContext` có ENGINE_SCOPE riêng và chia sẻ **cùng một** Bindings ở GLOBAL_SCOPE. Chạy chương trình sẽ thấy chính xác thứ tự ưu tiên và việc chia sẻ giá trị.

**Tệp `ScopeDemo.java`:**

```java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScopeDemo {
    public static void main(String[] args) {
        Bindings shared = new SimpleBindings();
        shared.put("appName", "Portal");
        shared.put("tax", 10);

        ScriptContext first = new SimpleScriptContext();
        first.setBindings(shared, ScriptContext.GLOBAL_SCOPE);
        first.setAttribute("user", "Lan", ScriptContext.ENGINE_SCOPE);
        first.setAttribute("tax", 5, ScriptContext.ENGINE_SCOPE);

        ScriptContext second = new SimpleScriptContext();
        second.setBindings(shared, ScriptContext.GLOBAL_SCOPE);
        second.setAttribute("user", "Minh", ScriptContext.ENGINE_SCOPE);

        System.out.println("first.user=" + first.getAttribute("user"));
        System.out.println("second.user=" + second.getAttribute("user"));
        System.out.println("first.tax=" + first.getAttribute("tax"));
        System.out.println("second.tax=" + second.getAttribute("tax"));
        System.out.println("first.global.tax=" + first.getAttribute(
                "tax", ScriptContext.GLOBAL_SCOPE));
        System.out.println("tax.scope=" + first.getAttributesScope("tax"));

        first.removeAttribute("tax", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.tax.after=" + first.getAttribute("tax"));
        System.out.println("tax.scope.after=" + first.getAttributesScope("tax"));

        first.setAttribute("appName", "Local", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.appName=" + first.getAttribute("appName"));
        System.out.println("second.appName=" + second.getAttribute("appName"));

        System.out.println("same.global="
                + (first.getBindings(ScriptContext.GLOBAL_SCOPE)
                        == second.getBindings(ScriptContext.GLOBAL_SCOPE)));
        System.out.println("missing.scope="
                + first.getAttributesScope("missing"));
    }
}
```

**Lệnh chạy trên JDK 17+** từ thư mục chứa tệp:

```powershell
javac ScopeDemo.java
java ScopeDemo
```

**Stdout chính xác:**

```text
first.user=Lan
second.user=Minh
first.tax=5
second.tax=10
first.global.tax=10
tax.scope=100
first.tax.after=10
tax.scope.after=200
first.appName=Local
second.appName=Portal
same.global=true
missing.scope=-1
```

Giải thích lần lượt:

1. Hai context có hai bộ ENGINE_SCOPE khác nhau, nên `user` là `Lan` ở `first` và `Minh` ở `second`.
2. `shared.tax=10` tồn tại ở GLOBAL_SCOPE của cả hai. `first` có bản `tax=5` trong ENGINE_SCOPE nên bản đó được ưu tiên; `second` chỉ thấy `tax=10`.
3. Lấy rõ scope global vẫn trả `10` ngay cả khi `first` có bản engine.
4. `getAttributesScope("tax")` trả `100` trước khi xóa engine và `200` sau khi xóa engine.
5. `first` đặt `appName=Local` vào ENGINE_SCOPE, nhưng `second` vẫn đọc giá trị `Portal` ở global. Đó là che khuất, không phải thay đổi shared map.
6. So sánh `==` cho thấy hai context dùng chung **chính object global bindings**, không phải bản sao.
7. `getAttributesScope("missing")` trả `-1` vì không scope nào định nghĩa tên ấy.

Đây là chương trình hoàn chỉnh **về cơ chế scope**, nhưng chưa chạy script. Điểm mạnh của nó là có thể tự kiểm chứng trên Java 17 mà không phụ thuộc cấu hình engine.

## 5. Kết nối với ScriptEngine thật: bốn cách lựa chọn

Các đoạn trong phần này là **mẫu tích hợp** chứ không phải chương trình độc lập. Chúng giả định đã có một `ScriptEngine` phù hợp và một chuỗi `scriptSource` viết theo cú pháp của ngôn ngữ được chọn. Một engine không có trong môi trường không thể chạy eval chỉ nhờ import `javax.script`.

### 5.1. Truyền qua engine.put: trạng thái mặc định của engine

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("myLanguage");
if (engine == null) {
    throw new IllegalStateException("No script engine installed");
}

engine.put("userId", "u123");
engine.put("retryCount", 3);
Object result = engine.eval(scriptSource);
```

Import `ScriptEngine`, `ScriptEngineManager` và xử lý `ScriptException`. `put` thường ghi ENGINE_SCOPE mặc định, phù hợp khi mỗi engine có phiên chạy được quản lý rõ. **Nếu tái dùng cùng engine cho nhiều request, các khóa ENGINE_SCOPE có thể tồn tại qua nhiều lần eval**. Không xem ENGINE_SCOPE là “mỗi request” nếu bản thân engine được dùng chung.

### 5.2. Truyền một Bindings riêng cho từng lần eval

```java
Bindings invocation = engine.createBindings();
invocation.put("userId", "u123");
invocation.put("retryCount", 3);

Object result = engine.eval(scriptSource, invocation);
```

`eval(String, Bindings)` dùng `invocation` làm **ENGINE_SCOPE cho lần thực thi**. Với `AbstractScriptEngine`, các scope khác như GLOBAL_SCOPE cũng như Reader/Writer đến từ context mặc định. Cách này thường giảm sự rò rỉ key giữa các lần chạy, nhưng **không hứa rằng toàn bộ nội trạng engine được cô lập**: một số triển khai giữ state ngoài Bindings.

### 5.3. Truyền ScriptContext riêng để kiểm soát cả hai scope

```java
ScriptContext execution = new SimpleScriptContext();

Bindings request = engine.createBindings();
request.put("userId", "u123");
execution.setBindings(request, ScriptContext.ENGINE_SCOPE);

Bindings defaults = new SimpleBindings();
defaults.put("appName", "Portal");
execution.setBindings(defaults, ScriptContext.GLOBAL_SCOPE);

java.io.StringWriter writer = new java.io.StringWriter();
execution.setWriter(writer);

Object result = engine.eval(scriptSource, execution);
String textOutput = writer.toString();
```

`eval(String, ScriptContext)` dùng **toàn bộ** ngữ cảnh do host truyền, cho phép đặt scope, input, output và error writer riêng cho một lần thực thi. Cách này phù hợp cho nhiều người dùng/tenant hoặc khi muốn thu giữ output. Một số engine có quy tắc riêng về việc ghi kết quả/biến; cần kiểm tra tài liệu provider.

### 5.4. Dùng ScriptEngineManager để chia sẻ GLOBAL_SCOPE

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("appName", "Portal");
manager.put("build", 17);

ScriptEngine first = manager.getEngineByName("myLanguage");
ScriptEngine second = manager.getEngineByName("myLanguage");
if (first == null || second == null) {
    throw new IllegalStateException("Script engine not installed");
}
first.put("requestId", "req-1");
second.put("requestId", "req-2");
```

`manager.put` thêm tên vào **global bindings của manager**; các engine do manager tạo dùng bộ global đó theo hợp đồng JSR-223. `first.put` và `second.put` đặt vào ENGINE_SCOPE riêng của **từng instance**. Do đó `requestId` không tự chia sẻ giữa hai engine.

Nếu gọi `engine.setBindings(anotherBindings, GLOBAL_SCOPE)`, engine có thể chuyển sang map global khác và không còn chia sẻ map của manager. Tương tự, tạo hai `ScriptEngineManager` không có nghĩa chúng chia sẻ một GLOBAL_SCOPE chung.

## 6. Chọn ENGINE_SCOPE hay GLOBAL_SCOPE theo dữ liệu

| Tình huống | Lựa chọn | Lý do |
|---|---|---|
| User ID, request ID, dữ liệu của một tác vụ | **ENGINE_SCOPE** trong Bindings/context mới | Giảm nguy cơ dữ liệu request trước lộ sang request sau |
| Tham số tính toán, feature flag riêng cho phiên chạy | **ENGINE_SCOPE** | Chỉ có ý nghĩa trong phạm vi đánh giá cụ thể |
| Giá trị mặc định chung như `appName` hoặc `defaultLocale` | **GLOBAL_SCOPE** khi thật sự cần chia sẻ | Tránh sao chép cấu hình được phép công khai |
| Giá trị mặc định có thể override theo request | Global mặc định + engine override | Quy tắc lookup cho phép che mà không làm đổi giá trị gốc |
| Object cung cấp thao tác Java cho script | Thường ENGINE_SCOPE/context riêng, giới hạn API | Tránh chia sẻ trạng thái và quyền quá rộng |
| Token, mật khẩu, đối tượng quản trị, dữ liệu tenant | Không nên để trong GLOBAL_SCOPE chung | Giảm diện tích lộ dữ liệu và khả năng truy cập chéo |

**Nguyên tắc:** dùng phạm vi nhỏ nhất đủ đáp ứng yêu cầu. Việc ghi vào GLOBAL_SCOPE chỉ hợp lý khi **mọi bên dùng chung map** đều được phép đọc và (nếu engine cho phép) sửa giá trị ấy.

Một Bindings global là một map **có thể thay đổi**. Đừng suy ra rằng “config” bất biến chỉ vì đặt trong GLOBAL_SCOPE. Nếu cần cấu hình đọc chung, host có thể tạo snapshot bất biến, chỉ đưa vào các object immutable/DTO hạn chế quyền, hoặc sử dụng API engine ngăn cập nhật theo chính sách ứng dụng.

## 7. Những điểm dễ nhầm

### 7.1. GLOBAL_SCOPE không bảo đảm được nhìn thấy ở mọi nơi

GLOBAL_SCOPE thuộc `ScriptContext` hoặc Bindings mà host chia sẻ; không có registry toàn JVM. Nếu host tạo một `SimpleScriptContext` mới mà không gọi `setBindings(..., GLOBAL_SCOPE)`, nó không tự nhìn thấy global của các context khác.

### 7.2. Thay Bindings khác với xóa một khóa

- `context.removeAttribute("x", ENGINE_SCOPE)` xóa **một** tên trong engine; bản global còn nguyên.
- `context.setBindings(newBindings, ENGINE_SCOPE)` thay **toàn bộ** map engine, có thể làm mất nhiều khóa khác.
- `context.setAttribute("x", value, GLOBAL_SCOPE)` cập nhật global của **context hiện tại**, không tự cập nhật mọi manager độc lập.
- Nếu cả hai scope có `x` thì lookup không chỉ scope lấy bản engine; khi xóa bản engine có thể “lộ” bản global, làm giá trị nhìn thấy thay đổi.

### 7.3. Đối tượng Java đưa vào script không tự an toàn

`Bindings` không phải sandbox. Nếu host đưa trực tiếp một object có quyền file, network, database hoặc token store vào script không tin cậy, việc đặt nó ở ENGINE_SCOPE thay vì GLOBAL_SCOPE **không ngăn script** sử dụng các phương thức mà engine cho phép. Hạn chế bề mặt API, bảo vệ dữ liệu, xác định quyền và cân nhắc chạy script không tin cậy trong ranh giới cách ly phù hợp.

### 7.4. Đa luồng và trạng thái dùng chung

`SimpleBindings` sử dụng một map thông thường, không đảm bảo an toàn khi nhiều thread sửa đồng thời. `ScriptEngine` cũng có chính sách thread-safety riêng (có engine cung cấp metadata về concurrency, có engine không). Tạo **Bindings riêng theo request** là bước tốt, nhưng nếu cả hai context chứa cùng một object mutable thì các script vẫn chia sẻ state qua object đó.

### 7.5. Tên biến và quy tắc của engine

`Bindings` sử dụng tên chuỗi Java, nhưng một ngôn ngữ script có thể có từ khóa dành riêng hoặc quy tắc định danh khác. Các tên `ScriptEngine.ENGINE`, `ScriptEngine.FILENAME`, `ScriptEngine.NAME`... có thể có ý nghĩa đặc biệt với một số provider. Dùng tên biến rõ nghĩa, không trùng tên nội bộ trừ khi tài liệu engine quy định.

### 7.6. Giá trị null không phải lúc nào cũng nghĩa là thiếu

Một tên có thể có trong map với giá trị `null`. Khi cần kiểm tra sự tồn tại, dùng `getAttributesScope(name)` hoặc `getBindings(scope).containsKey(name)` khi Bindings có mặt. Với `getAttribute(name)` một mình, `null` không đủ để xác định.

## 8. Chẩn đoán lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
|---|---|---|
| `getEngineByName("javascript")` trả `null` | Chưa cài engine; JDK 17 không kèm Nashorn | Cài provider JSR-223 phù hợp, kiểm tra `getEngineFactories()` |
| Script nhận giá trị khác dự kiến | Biến ENGINE_SCOPE đang che GLOBAL_SCOPE | In `getAttributesScope` và hai `getAttribute(name, scope)` |
| Request sau thấy giá trị request trước | Engine/default context được dùng lại | Dùng Bindings/context riêng theo invocation hoặc quản lý dọn dẹp rõ ràng |
| Hai engine không thấy chung biến global | Không dùng cùng global map hoặc engine đã bị thay scope | Xem `manager.getBindings()` và `engine.getBindings(GLOBAL_SCOPE)` |
| `IllegalArgumentException`/`NullPointerException` khi đặt tên | Khóa không hợp lệ hoặc scope sai | Không dùng tên null/rỗng; dùng hằng scope chuẩn |
| `ScriptException` khi eval | Cú pháp/logic script hoặc lỗi do provider | Kiểm tra thông báo, nguồn script và `cause` |
| `ClassCastException` khi nhận kết quả | Kiểu object/định dạng trả về không như host giả định | Kiểm tra `result` và conversion theo engine |
| Kết quả không nhất quán khi chạy đồng thời | Bindings hoặc engine có state dùng chung không an toàn | Tách context/engine, đồng bộ hoặc dùng executor theo contract |
| Giá trị global bị sửa ngoài ý muốn | Chia sẻ map mutable cho nhiều script | Giảm quyền ghi và chia sẻ snapshot an toàn |
| Đặt ENGINE_SCOPE bindings thành null | Context không chấp nhận ENGINE_SCOPE null | Tạo Bindings hợp lệ trước khi gắn |

**Đừng sửa mọi lỗi bằng cách chuyển sang GLOBAL_SCOPE.** Việc mở rộng phạm vi chỉ che lỗi thiết kế state và có thể làm dữ liệu bị chia sẻ quá rộng.

## 9. Tự kiểm tra

1. **Bindings khác ScriptContext thế nào?** Bindings là map tên–giá trị; ScriptContext gắn các map vào scope và quản lý I/O.
2. **Nếu tên `tax` có trong engine và global thì `getAttribute("tax")` trả gì?** Trả bản ENGINE_SCOPE.
3. **`getAttribute("tax", GLOBAL_SCOPE)` có bị bản engine che không?** Không; đã chỉ rõ scope.
4. **GLOBAL_SCOPE có phải map toàn JVM không?** Không; nó được chia sẻ khi các context/engine chủ động dùng cùng Bindings.
5. **`engine.eval(script, bindings)` đặt `bindings` ở scope nào?** ENGINE_SCOPE của lần chạy đó.
6. **Vì sao nên có Bindings riêng cho mỗi request?** Để tránh biến tạm của request trước tồn tại và giảm chia sẻ state.
7. **ENGINE_SCOPE có làm script an toàn hơn về quyền I/O không?** Không; đó là phạm vi tra cứu tên, không phải cơ chế bảo mật.
8. **`getAttributesScope("unknown")` trả gì khi không có tên?** `-1`.

**Bài tập A:** thêm `shared.put("role", "viewer")` trong chương trình `ScopeDemo`. Đặt `first.setAttribute("role", "editor", ENGINE_SCOPE)` và dự đoán giá trị role của hai context trước/sau khi xóa bản engine.

**Bài tập B:** tạo một `SimpleScriptContext` thứ ba mà không gọi `setBindings(shared, GLOBAL_SCOPE)`, rồi thử đọc `appName`. Vì sao nó không thấy `Portal`?

**Bài tập C:** khi đã cài một JSR-223 engine cụ thể, thực hiện liên tiếp `eval(script, bindingsA)` và `eval(script, bindingsB)`, đồng thời kiểm tra xem engine có giữ state ngoài Bindings hay không trước khi triển khai chạy đồng thời.

## Tài liệu tham khảo

- Java SE 17, `ScriptContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- Java SE 17, `SimpleScriptContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html
- Java SE 17, `Bindings`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html
- Java SE 17, `SimpleBindings`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html
- Java SE 17, `ScriptEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Java SE 17, `AbstractScriptEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- Java SE 17, `ScriptEngineManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html
