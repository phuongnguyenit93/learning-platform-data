# Nashorn và lựa chọn runtime JavaScript thay thế

Trong nhiều hệ thống Java lâu năm, JavaScript không chỉ xuất hiện ở giao diện web. Ứng dụng có thể nhúng JavaScript để đánh giá quy tắc nghiệp vụ, biến đổi dữ liệu, tạo mẫu báo cáo, mở rộng tính năng bằng plugin hoặc chạy các đoạn script do quản trị viên cấu hình. Một phần lớn những hệ thống này từng dựa vào **Nashorn**, JavaScript engine được tích hợp trong JDK 8 đến JDK 14.

Khi nâng JDK lên 15 hoặc cao hơn, Nashorn không còn được phân phối cùng JDK. Những đoạn Java dùng `ScriptEngineManager` để tìm engine tên `"nashorn"` có thể không còn tìm thấy engine; code import các lớp riêng của Nashorn có thể không biên dịch. Đây là vấn đề **tương thích API và môi trường thực thi**, không chỉ là thay đổi số phiên bản Java.

Bài học giải thích vòng đời Nashorn, cách nhận diện những phụ thuộc cũ, sự khác nhau giữa API chuẩn `javax.script` và engine cụ thể, đồng thời so sánh các hướng thay thế như GraalJS, Rhino, Nashorn độc lập và Node.js. Cuối bài là quy trình migration có ví dụ Java, các tình huống lỗi và cách kiểm chứng hành vi sau nâng cấp.

## 1. Nashorn là gì?

Nashorn là JavaScript engine từng được đóng gói trong JDK, cho phép chạy JavaScript bên trong một tiến trình Java. Ứng dụng có thể truy cập engine thông qua Java Scripting API (JSR-223), hoặc sử dụng các API riêng của Nashorn để tương tác sâu hơn với object JavaScript.

Một chương trình truyền thống dùng Nashorn như sau:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class LegacyScriptDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine = new ScriptEngineManager()
                .getEngineByName("nashorn");

        Object value = engine.eval("10 + 20");
        System.out.println(value);
    }
}
```

Trên một bản JDK có sẵn Nashorn, ví dụ có thể in `30`. Trên một JDK mới không có JavaScript engine tương ứng, `getEngineByName("nashorn")` trả về `null` và lời gọi `engine.eval(...)` sẽ gây `NullPointerException`. Vấn đề xuất hiện vì engine vắng mặt, dù gói `javax.script` vẫn tồn tại.

Nashorn còn hỗ trợ những tiện ích tích hợp với JVM:

```javascript
var ArrayList = Java.type("java.util.ArrayList");
var values = new ArrayList();
values.add("alpha");
values.add("beta");
print(values.size());
```

`Java.type` và `print` trong ví dụ phản ánh môi trường Nashorn; chúng **không phải** các API được bảo đảm có mặt trong mọi runtime ECMAScript hoặc trong Node.js. Khi chuyển engine, mã JavaScript có thể cần chỉnh sửa ngay cả khi cú pháp ngôn ngữ vẫn hợp lệ.

## 2. Vòng đời Nashorn theo các mốc JDK

Các mốc cần nhớ:

| Phiên bản | Tình trạng Nashorn trong JDK | Tác động đối với migration |
|---|---|---|
| JDK 8 | Nashorn được giới thiệu và có sẵn trong JDK. | Những ứng dụng cũ có thể phụ thuộc ngầm vào JavaScript engine tích hợp. |
| JDK 9–10 | Nashorn tiếp tục được đóng gói. | Có thể truy cập qua `javax.script` và API Nashorn, tùy cấu hình module. |
| JDK 11 | JEP 335 đánh dấu Nashorn engine, các API liên quan và công cụ `jjs` là deprecated for removal. | Bắt đầu cần lập kế hoạch thay thế. |
| JDK 12–14 | Nashorn vẫn hiện diện nhưng đã nằm trong lộ trình loại bỏ. | Việc chạy được ở các bản này không chứng minh sẽ chạy được ở JDK 15+. |
| JDK 15 trở đi | JEP 372 loại bỏ Nashorn engine, các API riêng và `jjs` khỏi JDK. | Cần thêm engine bên ngoài, đổi giải pháp thực thi script hoặc chuyển logic khỏi JavaScript. |

Các module JDK bị loại bỏ theo JEP 372 bao gồm `jdk.scripting.nashorn` và `jdk.scripting.nashorn.shell`. Công cụ dòng lệnh `jjs` đi kèm Nashorn cũng không còn trong JDK mới.

**Điều không bị loại bỏ:** Java Scripting API `javax.script` và module `java.scripting` vẫn là một phần của nền tảng Java. Một thư viện bên thứ ba có thể cung cấp implementation `ScriptEngine` thông qua Service Provider Interface (SPI). Vì vậy, cần phân biệt **API để nhúng script** với **engine thực sự thi hành JavaScript**.

Không nên giải quyết sự cố bằng cách chỉ đổi `--release`, `-source` hay `-target` trong trình biên dịch. Những tùy chọn đó điều chỉnh biên dịch, không tự mang Nashorn trở lại runtime sau JDK 15.

## 3. Phân biệt JSR-223 và Nashorn API

JSR-223 là giao diện trừu tượng để ứng dụng Java làm việc với một scripting engine. Các kiểu phổ biến:

- `ScriptEngineManager`: khám phá các engine được đăng ký.
- `ScriptEngineFactory`: mô tả tên, phiên bản và ngôn ngữ mà engine hỗ trợ.
- `ScriptEngine`: đánh giá script, quản lý bindings và context.
- `Bindings` và `ScriptContext`: truyền biến và cấu hình vào phiên thực thi.
- `Invocable`: gọi hàm hoặc phương thức trong script nếu engine hỗ trợ.
- `Compilable` và `CompiledScript`: biên dịch/tái sử dụng script nếu implementation hỗ trợ.

Một phần mềm chỉ sử dụng các kiểu trên thường dễ thay engine hơn phần mềm import API riêng như:

```java
import jdk.nashorn.api.scripting.NashornScriptEngineFactory;
import jdk.nashorn.api.scripting.ScriptObjectMirror;
```

Hai class này là API riêng của Nashorn trong JDK cũ, không phải một phần của JSR-223. Khi thay engine, không có bảo đảm rằng implementation mới cung cấp các class tương đương hay cách chuyển kiểu dữ liệu giống hệt.

| Phụ thuộc trong mã cũ | Ý nghĩa | Mức độ cần điều chỉnh |
|---|---|---|
| `javax.script.ScriptEngine` | Giao diện chuẩn để thực thi script. | Có thể giữ khi engine mới có adapter JSR-223. |
| `getEngineByName("nashorn")` | Khám phá một engine theo tên riêng. | Cần đổi tên/khai báo engine và kiểm tra engine hiện diện. |
| `jdk.nashorn.api.scripting.*` | Phụ thuộc vào triển khai Nashorn trong JDK. | Cần thiết kế lại phần chuyển kiểu và tương tác. |
| `Java.type`, `Java.extend`, `Packages` | Java interop theo kiểu Nashorn. | Cần kiểm tra tính năng và quyền truy cập của engine thay thế. |
| `jjs script.js` | Gọi công cụ Nashorn bằng lệnh hệ điều hành. | Cần thay command hoặc triển khai runner riêng. |

Không nên coi việc compile được với `java.scripting` là bằng chứng hệ thống đã có JavaScript runtime. Tại thời điểm chạy, engine phải có mặt và được phát hiện theo đúng classpath hoặc module path.

## 4. Nhận diện phụ thuộc Nashorn trước khi nâng cấp

Kiểm kê những nơi chương trình thực thi hoặc lưu trữ script:

1. Java code tạo `ScriptEngineManager` hoặc `NashornScriptEngineFactory`.
2. Spring, workflow engine, rule engine hoặc các thư viện có cấu hình `language=javascript`.
3. JavaScript lưu ở thư mục resources, database, object storage hoặc bảng cấu hình.
4. Build script, công cụ vận hành và scheduler gọi `jjs`.
5. Plugin dùng `Java.type` hoặc script truy cập Java object do ứng dụng truyền vào.
6. Các API Nashorn riêng, chẳng hạn `ScriptObjectMirror` hoặc parser API.
7. Các nút tích hợp có yêu cầu chạy JavaScript nhưng không lộ rõ trong mã Java.

Có thể dùng tìm kiếm nguồn hoặc IDE với những từ khóa:

```text
nashorn
jdk.nashorn
ScriptEngineManager
ScriptEngine
Invocable
Compilable
getEngineByName
Java.type
Java.extend
Java.super
Packages
jjs
```

Đây là gợi ý kiểm kê, không phải danh sách đầy đủ. Script sinh động từ database, từ template hoặc tải khi runtime có thể không xuất hiện trong repository. Nếu cần xác định mức sử dụng thực tế, bổ sung log có kiểm soát: service nào chạy script, script ID nào, tần suất, thời gian chạy và loại lỗi.

Khi chạy kiểm tra trên JDK mới, trước tiên cần biết engine nào thực sự được đăng ký:

```java
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public class ListScriptEngines {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();

        for (ScriptEngineFactory factory : manager.getEngineFactories()) {
            System.out.println("Engine: " + factory.getEngineName());
            System.out.println("Language: " + factory.getLanguageName());
            System.out.println("Aliases: " + factory.getNames());
        }
    }
}
```

Nếu không có engine nào được liệt kê, kết quả thường là không in gì. Điều này không có nghĩa API `javax.script` đã bị xóa; nó chỉ cho thấy không có provider nào được tìm thấy trong môi trường chạy đó.

## 5. Vì sao không thể thay mọi engine bằng cách đổi một chuỗi tên?

Các JavaScript runtime có thể khác nhau ở ba lớp:

**Lớp ngôn ngữ:** phiên bản ECMAScript được hỗ trợ, cách phân tích cú pháp, built-in objects, module support và cơ chế Promise.

**Lớp tương tác Java:** cách truyền `Map`, `List` và POJO từ Java vào JS; cách gọi Java method; kiểu trả về; cách xử lý overload, array, exception và host class.

**Lớp môi trường:** quyền truy cập file/mạng, class loader, thread, tính tương thích với `javax.script`, sự hiện diện của Node.js APIs, quản lý context và đóng gói runtime.

Ví dụ, đoạn JavaScript:

```javascript
const Files = Java.type("java.nio.file.Files");
```

có thể có ý nghĩa trong một engine hỗ trợ Java interop và được cấp quyền truy cập Java classes, nhưng không phải cú pháp API có sẵn trong Node.js. Ngược lại:

```javascript
import { readFile } from "node:fs/promises";
```

là cách gọi built-in module của Node.js, không tự hoạt động trong một JavaScript context nhúng vào JVM. Vì vậy, việc chọn runtime phải bắt đầu bằng **yêu cầu thực tế của script** chứ không chỉ tên ngôn ngữ JavaScript.

## 6. Những lựa chọn thay thế phổ biến

| Lựa chọn | Cách chạy | Điểm mạnh | Lưu ý migration |
|---|---|---|---|
| **GraalJS với Polyglot API** | JavaScript chạy ngay trong JVM bằng `org.graalvm.polyglot.Context`. | ECMAScript hiện đại, tương tác Java có thể cấu hình chi tiết. | Cần thêm dependency và chuyển code nhúng từ JSR-223 nếu muốn dùng API mới. |
| **GraalJS qua JSR-223** | Adapter `ScriptEngine` bên ngoài JDK. | Giữ một phần kiến trúc Java dùng `javax.script`. | Module adapter riêng; khác biệt JS semantics và host access vẫn cần kiểm thử. |
| **Standalone Nashorn** | Engine Nashorn được đóng gói thành thư viện riêng. | Giữ nhiều script cũ trong giai đoạn chuyển tiếp. | Không phải engine được tích hợp lại vào JDK; vẫn cần dependency, bảo trì và kế hoạch dài hạn. |
| **Rhino** | JavaScript engine viết bằng Java, nhúng qua API riêng hoặc JSR-223 adapter. | Chạy trong JVM, có thể phù hợp với một số hệ thống Java lâu năm. | Kiểm tra mức hỗ trợ ECMAScript, Java interop, module và baseline JDK của từng phiên bản. |
| **Node.js** | Runtime JS chạy ở tiến trình riêng. | Phù hợp với ứng dụng JS dùng npm và Node built-ins. | Không phải engine trong JVM; cần giao tiếp liên tiến trình và quản lý deployment. |
| **Chuyển logic sang Java hoặc DSL** | Không cần JavaScript runtime. | Giảm phụ thuộc engine nếu script ít, ổn định, thuần nghiệp vụ. | Tốn công chuyển đổi, phải kiểm thử tương đương hành vi. |

Không có lựa chọn luôn tốt nhất cho mọi hệ thống. Nếu script chỉ gồm biểu thức đơn giản do ứng dụng kiểm soát, hướng chuyển thành Java/DSL có thể phù hợp. Nếu cần JavaScript hiện đại nhúng trong JVM và gọi một số API Java được cho phép, GraalJS là ứng viên đáng xem xét. Nếu script được viết cho Node.js và phụ thuộc nhiều npm package, thực thi bằng Node ở một tiến trình tách biệt thường tự nhiên hơn.

## 7. GraalJS: thay thế nhúng JavaScript bằng Polyglot API

GraalJS là JavaScript implementation trong hệ sinh thái GraalVM, có thể được thêm vào ứng dụng chạy trên JDK tương thích qua dependency. Không cần mặc định rằng cứ cài một JDK mới thì JavaScript engine đã có sẵn. Với GraalJS hiện đại, cách nhúng được khuyến nghị là dùng `org.graalvm.polyglot.Context`.

### 7.1. Cấu hình dependency trong Maven

Ví dụ Maven sau dùng nhóm artifact Community. Hãy chọn một phiên bản **đồng nhất và đã kiểm thử** cho tất cả dependency:

```xml
<properties>
    <graaljs.version>25.3.4.1</graaljs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.graalvm.polyglot</groupId>
        <artifactId>polyglot</artifactId>
        <version>25.3.4.1</version>
    </dependency>
    <dependency>
        <groupId>org.graalvm.polyglot</groupId>
        <artifactId>js-community</artifactId>
        <version>25.3.4.1</version>
        <type>pom</type>
    </dependency>
</dependencies>
```

`25.3.4.1` ở đây là phiên bản ví dụ từ hướng dẫn GraalJS, **không phải yêu cầu cố định** cho mọi dự án. Khi triển khai, cập nhật theo release được tổ chức chọn và xác nhận license, yêu cầu JDK, khả năng tương thích, BOM/dependency resolution. Artifact `js` khác `js-community` về phân phối/licensing nên cần kiểm tra lựa chọn phù hợp với tổ chức.

### 7.2. Thực thi JavaScript đơn giản

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class GraalJsHello {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            Value result = context.eval("js", "21 * 2");
            System.out.println(result.asInt());
        }
    }
}
```

Kết quả:

```text
42
```

`Context` đại diện cho môi trường thực thi JS. `try-with-resources` giúp đóng context sau khi sử dụng. Đối tượng `Value` là lớp bao cho giá trị JS và cung cấp các phương thức chuyển đổi sang kiểu Java phù hợp. Đừng giữ `Value` và tiếp tục sử dụng sau khi context đã đóng.

### 7.3. Truyền dữ liệu từ Java sang JavaScript

Để áp dụng các quy tắc có dữ liệu đầu vào:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class DiscountRule {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            context.getBindings("js").putMember("subtotal", 150.0);
            context.getBindings("js").putMember("discountRate", 0.10);

            Value result = context.eval(
                    "js",
                    "subtotal * (1 - discountRate)");

            System.out.println(result.asDouble());
        }
    }
}
```

Kết quả dự kiến:

```text
135.0
```

Đây là ví dụ phù hợp với biểu thức số học đơn giản. Trong ứng dụng tài chính, cần kiểm soát cách tính và làm tròn; không nên sử dụng số `double` cho tiền nếu nghiệp vụ yêu cầu độ chính xác thập phân tuyệt đối.

### 7.4. Cho phép script gọi một số Java method đã chọn

Một khác biệt quan trọng so với nhiều ứng dụng Nashorn cũ là GraalJS hướng đến cách cấu hình an toàn: chỉ cho phép tương tác host khi được cấp quyền phù hợp. Ta có thể chỉ công bố một method theo chính sách `HostAccess.EXPLICIT`:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;

public class RestrictedInteropDemo {
    public static final class PricingFunctions {
        @HostAccess.Export
        public double applyDiscount(double subtotal, double rate) {
            if (subtotal < 0 || rate < 0 || rate > 1) {
                throw new IllegalArgumentException("Invalid input");
            }
            return subtotal * (1 - rate);
        }
    }

    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js")
                .allowHostAccess(HostAccess.EXPLICIT)
                .allowHostClassLookup(name -> false)
                .build()) {

            context.getBindings("js")
                    .putMember("pricing", new PricingFunctions());

            double result = context.eval(
                    "js",
                    "pricing.applyDiscount(200, 0.15)")
                    .asDouble();

            System.out.println(result);
        }
    }
}
```

Script chỉ gọi được những method mà chính sách host access cho phép. `@HostAccess.Export` đánh dấu public method muốn công bố. `allowHostClassLookup(name -> false)` tránh cho script tự tìm các lớp Java tùy ý bằng `Java.type`. Đây là ví dụ kiểm soát bề mặt API; khi chạy script không đáng tin cậy vẫn cần thêm giới hạn về tài nguyên, thời gian và cô lập.

Không nên đơn giản bật `HostAccess.ALL` cùng một predicate cho phép mọi Java class chỉ để script cũ tiếp tục chạy. Cấu hình đó có thể trao nhiều quyền hơn nghiệp vụ cần.

## 8. GraalJS với `ScriptEngine`: con đường chuyển tiếp

Nếu mã Java hiện tại dùng nhiều `ScriptEngine`, `Bindings` hoặc `Invocable`, có thể cân nhắc adapter JSR-223 của GraalJS. Điều này giúp giữ một phần giao diện gọi trong Java.

**Chú ý:** Ở các bản GraalVM mới, adapter ScriptEngine không nhất thiết được đi kèm JDK theo mặc định. Cần khai báo dependency `org.graalvm.js:js-scriptengine` và đảm bảo JavaScript runtime được đóng gói cùng ứng dụng.

Ví dụ các dependency bổ sung cho Maven:

```xml
<dependency>
    <groupId>org.graalvm.js</groupId>
    <artifactId>js-scriptengine</artifactId>
    <version>25.3.4.1</version>
</dependency>
```

Dependency này dùng cùng phiên bản GraalJS như những dependency ở phần trước. Trong dự án JPMS, adapter cần xuất hiện trong module graph; tùy cấu hình có thể cần `--add-modules org.graalvm.js.scriptengine`.

Ví dụ kiểm tra engine trước khi gọi:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class GraalJsr223Demo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("graal.js");

        if (engine == null) {
            throw new IllegalStateException(
                    "GraalJS ScriptEngine not registered");
        }

        Object value = engine.eval("6 * 7");
        System.out.println(value);
    }
}
```

Engine có thể được đăng ký dưới nhiều alias. Luôn lấy tên engine từ `getEngineFactories()` trong runtime của ứng dụng thay vì tự suy luận tên hợp lệ. Nếu có nhiều engine cùng đăng ký alias `"JavaScript"`, nên chọn alias đủ rõ để tránh tình cờ đổi implementation.

**Ưu và giới hạn:** JSR-223 giúp giảm lượng code Java phải sửa ngay; tuy nhiên, thay engine vẫn có thể thay đổi JS syntax, Java interop, cách chuyển kết quả và security defaults. GraalJS khuyến nghị `Context` khi cần điều khiển cấu hình chi tiết. Với code mới, nên cân nhắc xây một adapter của ứng dụng bao quanh `Context` thay vì phát triển thêm sự phụ thuộc trực tiếp vào `ScriptEngine`.

## 9. Chuyển từ `Invocable` sang `Value.execute`

Nashorn cùng JSR-223 thường được dùng để gọi một hàm JS:

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class LegacyFunctions {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new ScriptEngineManager()
                .getEngineByName("nashorn");

        engine.eval("function multiply(a, b) { return a * b; }");
        Object answer = ((Invocable) engine)
                .invokeFunction("multiply", 6, 7);

        System.out.println(answer);
    }
}
```

Với Polyglot API, có thể lấy hàm JS như một `Value` và gọi trực tiếp:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class PolyglotFunctions {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            context.eval(
                    "js",
                    "function multiply(a, b) { return a * b; }");

            Value fn = context.getBindings("js")
                    .getMember("multiply");

            int answer = fn.execute(6, 7).asInt();
            System.out.println(answer);
        }
    }
}
```

Trong hệ thống thực tế, cần xử lý trường hợp hàm không tồn tại hoặc không thể thực thi, lỗi script, và kiểm tra kiểu kết quả. Cách gọi này thay thế phụ thuộc vào `Invocable` bằng API riêng của GraalVM; đây là một lựa chọn kiến trúc nên được bọc trong lớp adapter nếu ứng dụng cần khả năng đổi engine sau này.

## 10. Khác biệt JavaScript và Java interop khi chuyển từ Nashorn

Không phải mọi script Nashorn đều tương đương với script GraalJS, dù cùng thực thi JavaScript. Những điểm cần rà soát gồm:

| Chủ đề | Script Nashorn cũ thường dùng | Điều cần xem khi chuyển |
|---|---|---|
| Java class access | `Java.type("java.util.ArrayList")` | GraalJS có thể hỗ trợ, nhưng host class lookup phải được cho phép. |
| Package globals | `java.*`, `javax.*`, `Packages.*` | Có thể cần bật compatibility features hoặc sửa sang `Java.type`. |
| Helper functions | `Java.from`, `Java.to`, `Java.extend` | Kiểm tra phiên bản engine và cấu hình Java interop; có thể cần refactor. |
| Host objects | `ScriptObjectMirror` | Chuyển sang `Value`/bindings hoặc DTO rõ ràng. |
| Java overload | Gọi method overload trực tiếp | Kiểm tra quy tắc chuyển số, chuỗi, mảng và giải quyết overload. |
| Script outputs | `print()`, các chức năng `load()` | Không mặc định tồn tại giống nhau trong mọi engine hay mọi context. |
| Ngôn ngữ | ECMAScript phiên bản cũ và phần mở rộng Nashorn | Chạy test cho syntax, strict mode, `this`, scope và `undefined`. |
| Modules và npm | Script nhúng từ tài nguyên | Không tự có các built-in modules của Node.js như `fs` hoặc `http`. |

Khi migration, nên tách hai loại thay đổi:

1. **Chuẩn hóa script thành ECMAScript thuần:** giảm phụ thuộc vào `Java.type`, `Packages`, `ScriptObjectMirror` và các helper riêng.
2. **Chọn host integration mới:** Java cung cấp DTO/operations được phép qua bindings hoặc API tương đương, thay vì cho script tùy ý tìm và gọi mọi Java class.

Cách tách này giúp dễ kiểm thử logic JS và giảm chi phí đổi runtime ở những lần nâng cấp tiếp theo.

### 10.1. Nashorn compatibility mode của GraalJS

GraalJS cung cấp một chế độ tương thích Nashorn nhằm hỗ trợ một số extension của Nashorn:

```java
import org.graalvm.polyglot.Context;

public class CompatibilityModeExample {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js")
                .allowExperimentalOptions(true)
                .option("js.nashorn-compat", "true")
                .build()) {
            context.eval("js", "print('legacy compatibility')");
        }
    }
}
```

Cấu hình `js.nashorn-compat` là tùy chọn tương thích, không chứng minh mọi script Nashorn chạy nguyên trạng. Nó có thể mở thêm tính năng làm suy yếu cách cấu hình an toàn mặc định; cần kiểm tra kỹ trước khi dùng với script không đáng tin cậy. Chế độ này có thể điều chỉnh ngôn ngữ về mức ECMAScript cũ; muốn dùng cú pháp mới cần kiểm tra và cấu hình `js.ecmascript-version` phù hợp nếu engine hỗ trợ.

Nên xem compatibility mode là **cầu nối migration**, kết hợp test và kế hoạch giảm dần Nashorn-specific extensions, thay vì xem là giải pháp cuối cùng cho mọi dự án.

## 11. Standalone Nashorn: giữ hệ thống cũ trong giai đoạn chuyển tiếp

Sau khi engine bị loại khỏi JDK, dự án Nashorn độc lập vẫn được cộng đồng OpenJDK duy trì dưới dạng thư viện riêng. Artifact thường được biết đến là `org.openjdk.nashorn:nashorn-core`; dự án công bố khả năng sử dụng với Java 11 trở lên.

Đây có thể là hướng phù hợp khi:

- Có nhiều script cũ phụ thuộc `Java.type` hoặc Nashorn-specific behavior.
- Cần nâng JDK sớm nhưng chưa đủ thời gian sửa tất cả script.
- Muốn giảm quy mô thay đổi trong một đợt triển khai và tách việc thay engine thành giai đoạn tiếp theo.

Tuy nhiên, standalone Nashorn **không phải Nashorn tích hợp vào JDK**. Ứng dụng cần khai báo thư viện và phụ thuộc bắc cầu, trong đó có các thành phần ASM theo dự án; class/module của implementation có tên khác với phiên bản trong JDK cũ.

Ví dụ khai báo dependency Maven (thay `NASHORN_VERSION` bằng bản đã xác nhận tương thích):

```xml
<dependency>
    <groupId>org.openjdk.nashorn</groupId>
    <artifactId>nashorn-core</artifactId>
    <version>NASHORN_VERSION</version>
</dependency>
```

Khi chạy trên module path, cần bảo đảm module `org.openjdk.nashorn` và những module phụ thuộc được resolve đúng. Nếu code Java vẫn import `jdk.nashorn.api.scripting.*`, việc chỉ thêm dependency không làm package cũ xuất hiện lại; cần sửa import và các sử dụng API cụ thể dựa trên tài liệu của standalone Nashorn.

Đừng xem đây là biện pháp lâu dài chỉ vì ứng dụng đã khởi động được. Cần tính cả lịch phát hành, bản sửa lỗi, bảo mật, license, mức hỗ trợ ECMAScript và kế hoạch thay thế những extension cũ.

## 12. Rhino: lựa chọn JavaScript engine viết bằng Java

Rhino là JavaScript engine được phát triển bằng Java và vẫn có các bản phát hành độc lập. Nó có thể nhúng vào một ứng dụng Java hoặc dùng adapter JSR-223 nếu dependency tương ứng được cung cấp.

Trong một số phiên bản Rhino, engine JSR-223 nằm trong artifact riêng `rhino-engine` bên cạnh `rhino`. Vì vậy, chỉ thêm core engine không bảo đảm `ScriptEngineManager` tìm thấy alias JavaScript. Kiểm tra release notes và dependency graph trước khi triển khai.

Rhino hiện đại hỗ trợ nhiều đặc điểm ECMAScript mới nhưng mức độ hoàn chỉnh của từng tính năng thay đổi theo release. Đừng giả định rằng Rhino luôn có cùng hành vi với Nashorn, GraalJS hoặc Node. Rhino cũng đặt baseline JDK theo phiên bản: chẳng hạn các bản Rhino 1.9 yêu cầu JDK 17 trở lên để chạy, trong khi một số bản cũ có yêu cầu thấp hơn.

Những điểm cần kiểm thử khi chọn Rhino:

- Bộ cú pháp JavaScript mà script hiện có sử dụng.
- Cách Java object, array, primitive và exception được chuyển qua ranh giới JS/Java.
- Khả năng tương thích với API `javax.script` nếu code host dựa trên JSR-223.
- Chiến lược context/thread trong ứng dụng server.
- Module/classpath, cấu hình sandbox và runtime JDK tối thiểu.

Rhino có thể phù hợp với các dự án yêu cầu engine triển khai bằng Java. Quyết định cần dựa trên benchmark và test của chính script trong hệ thống, không chỉ một bảng so sánh tính năng chung.

## 13. Node.js: chạy JavaScript ở tiến trình riêng

Node.js phù hợp khi hệ thống phải thực thi các script vốn được thiết kế cho Node, sử dụng nhiều npm package hoặc phụ thuộc các built-in modules như `node:fs`, `node:http` và event loop.

Kiến trúc lúc này thay đổi:

```text
Java application
      |
      | JSON / HTTP / gRPC / IPC
      v
JavaScript worker (Node.js process)
      |
      +-- npm packages
      +-- Node.js APIs
      +-- async tasks / event loop
```

Java không gọi `ScriptEngine.eval(...)` để chạy JS ngay trong JVM; thay vào đó, Java gửi dữ liệu và nhận kết quả qua một giao thức. Có thể dùng worker cố định, hàng đợi hoặc một service riêng, tùy tải và yêu cầu vận hành.

Ưu điểm:

- Chạy script theo đúng runtime Node.js và hệ sinh thái package tương ứng.
- Có ranh giới tiến trình rõ ràng để giới hạn CPU, memory và quyền truy cập bằng công cụ hệ điều hành/container.
- Có thể nâng phiên bản JS runtime độc lập với JDK nếu giao thức ổn định.

Chi phí:

- Phải triển khai, giám sát và cập nhật một runtime/service thứ hai.
- Có độ trễ giao tiếp và chi phí serialization.
- Cần quản lý timeout, retry, idempotency, thứ tự xử lý và tương quan request.
- Không thể truyền trực tiếp Java object tùy ý theo cơ chế Nashorn; phải thiết kế DTO/wire format.

Nếu chỉ cần đánh giá các biểu thức ngắn, chạy một tiến trình Node riêng cho mỗi request có thể tốn kém. Nếu sử dụng tiến trình kéo dài, cần quản lý concurrency, lỗi worker và tính riêng biệt giữa các request. Với input không đáng tin cậy, sử dụng container/process isolation và resource limit phù hợp; không mặc định một tiến trình Node là sandbox an toàn.

## 14. Cân nhắc thay JavaScript bằng Java hoặc DSL

Không phải ứng dụng nào có script cũng cần giữ một JavaScript engine mãi mãi. Nếu các script chỉ thực hiện một số phép tính hoặc luật được quy định trước, có thể chuyển logic vào Java hoặc một domain-specific language (DSL) giới hạn biểu thức.

Ví dụ, thay vì cho phép cấu hình tùy ý:

```javascript
if (cart.total > 1000 && cart.member) {
    cart.discount = 0.1;
}
```

có thể biểu diễn một luật như dữ liệu:

```json
{
  "minTotal": 1000,
  "memberRequired": true,
  "discountRate": 0.1
}
```

Java đọc dữ liệu và đánh giá theo logic được kiểm soát. Phương án này làm giảm khả năng người cấu hình thao tác với object/method ngoài hợp đồng. Đổi lại, nó ít linh hoạt hơn JavaScript tùy ý và cần chuyển đổi script đã tồn tại.

Hướng đi này đáng cân nhắc khi các luật ít thay đổi về cấu trúc, yêu cầu kiểm toán cao và bộ tính năng JavaScript lớn hơn rất nhiều so với nhu cầu thực tế.

## 15. Thiết kế một adapter để giảm phụ thuộc engine

Một lỗi kiến trúc là để code nghiệp vụ gọi trực tiếp `ScriptEngine` hoặc `Context` ở hàng chục vị trí. Khi thay engine, mọi nơi đó đều cần sửa.

Có thể đặt một hợp đồng nội bộ:

```java
import java.util.Map;

public interface RuleRuntime {
    RuleResult evaluate(
            String ruleId,
            String script,
            Map<String, Object> inputs);
}
```

```java
public record RuleResult(boolean matched, String explanation) {
}
```

Một implementation có thể dùng GraalJS; implementation khác có thể gọi một worker Node. Bên ngoài chỉ biết hợp đồng `RuleRuntime` và giá trị trả về.

Khi thiết kế adapter, cần quy định:

- Ngôn ngữ và phiên bản cú pháp được chấp nhận.
- Kiểu đầu vào/đầu ra, quy tắc `null`, thiếu field, số thập phân và ngày giờ.
- Cách báo lỗi cú pháp, lỗi runtime, lỗi tài nguyên và lỗi timeout.
- Quyền truy cập host API, file, mạng và process.
- Giới hạn số lần gọi, thời gian, bộ nhớ và kích thước script.
- Chu kỳ khởi tạo context, cách cache mã đã biên dịch và quản lý thread.
- Quy tắc versioning script khi triển khai cuốn chiếu hoặc rollback.

Một adapter làm rõ phần hợp đồng thuộc về ứng dụng và phần hành vi thuộc về engine. Nó cũng cho phép chạy hai implementation trên cùng bộ fixture để so sánh kết quả migration.

## 16. Những điểm tương thích dữ liệu cần kiểm tra

Đổi JavaScript engine có thể làm thay đổi kết quả dù script không báo lỗi.

### 16.1. Số học và chuyển kiểu

JavaScript Number thường dùng số dấu phẩy động theo IEEE 754. Khi đưa `long`, `BigInteger` hoặc `BigDecimal` từ Java vào engine, mỗi implementation có thể có quy tắc chuyển đổi và host interop riêng.

Ví dụ, số nguyên Java lớn hơn giới hạn biểu diễn chính xác của JavaScript Number có thể mất độ chính xác nếu bị ép về Number. Hãy kiểm thử các giá trị biên, số âm, số rất lớn, `NaN`, `Infinity`, và quy tắc làm tròn. Với tiền tệ, ưu tiên biểu diễn có kiểm soát thay vì âm thầm chuyển `BigDecimal` thành `double`.

### 16.2. `null`, `undefined` và field thiếu

Một object từ Java có field `null` khác với một property JS không tồn tại và kết quả `undefined`. Cách bọc host objects và chuyển kết quả về Java có thể khác giữa Nashorn, GraalJS và Rhino. Test cần phân biệt:

```javascript
const a = { value: null };
const b = {};

console.log(a.value === null);      // true
console.log(b.value === undefined); // true
```

Nếu hệ thống dùng kết quả script để ghi cơ sở dữ liệu hoặc gửi message, cần định nghĩa rõ mapping giữa giá trị thiếu và giá trị rỗng.

### 16.3. Date, timezone và locale

Script có thể gọi `Date`, chuyển timestamp hoặc format theo locale. Khi nâng runtime, kiểm tra timezone mặc định, parse string không chuẩn, chuẩn ISO-8601 và daylight saving time. Nên truyền thời gian theo biểu diễn UTC/epoch rõ ràng thay vì để engine tự suy luận.

### 16.4. Collection, object và exception

Nashorn-specific `ScriptObjectMirror` không tương đương trực tiếp với `org.graalvm.polyglot.Value` hay wrapper của Rhino. Nếu API nghiệp vụ trả JS object, cần chuyển nó sang DTO hoặc cấu trúc JSON rõ ràng trước khi đi qua các tầng khác.

Exception từ Java code được script gọi cũng có thể bị bọc khác nhau. Đừng phụ thuộc vào tên class hoặc chuỗi exception cụ thể nếu mục tiêu chỉ là nhận diện lỗi nghiệp vụ. Hãy dùng error code/contract riêng ở ranh giới adapter.

## 17. Bảo mật khi chạy script

Một script có thể là:

- **Trusted:** nằm trong source repository và được review như mã chương trình.
- **Semi-trusted:** do quản trị viên cấu hình nhưng vẫn có thể sai hoặc bị lạm dụng.
- **Untrusted:** đến từ người dùng hoặc nguồn ngoài mà ứng dụng không kiểm soát.

Mức kiểm soát phải phù hợp với nguồn script. Không nên mặc định rằng thay Nashorn bằng một engine mới đồng nghĩa script đã được cô lập an toàn.

Các vấn đề cần xác định:

1. **Host access:** script có được gọi các Java method nào? Có được tìm class bằng `Java.type` không?
2. **File/network/process:** script có quyền đọc file, mở kết nối hoặc chạy lệnh hệ điều hành không?
3. **Tài nguyên:** vòng lặp vô hạn hoặc tạo object lớn có thể chiếm CPU/memory đến mức nào?
4. **Bí mật:** script có nhìn thấy credential, environment variable, service token hoặc object chứa dữ liệu nhạy cảm không?
5. **Tenant isolation:** script của hai khách hàng có chia sẻ context, global variables hoặc cache không?
6. **Audit:** có thể xác định script ID, phiên bản, người triển khai và lý do thất bại không?

Với GraalJS, sử dụng chính sách host access giới hạn, tránh công khai toàn bộ classpath, và không bật Nashorn compatibility mode nếu không có nhu cầu đã đánh giá. Với script thật sự không đáng tin cậy, nên cân nhắc cô lập ở cấp tiến trình/container và áp dụng time/memory limits, bởi script chạy trong cùng JVM vẫn chia sẻ tài nguyên với ứng dụng.

Không dựa vào `SecurityManager` của Java cũ như giải pháp sandbox duy nhất; chính sách Security Manager đã thay đổi theo các JDK mới. Các giới hạn phải được kiểm tra trên đúng JDK/runtime mục tiêu.

## 18. Hiệu năng và vòng đời của engine

Tùy lựa chọn, việc khởi động engine/context và biên dịch script có thể có chi phí khác nhau. Một số nguyên tắc chung:

**Không tạo context tùy tiện cho mọi phép toán nhỏ:** nếu tải cao, chi phí khởi tạo có thể đáng kể. Tuy nhiên, tái sử dụng context cũng cần kiểm soát state và thread.

**Tách script code khỏi request data:** có thể cache source hoặc compiled script theo key gồm script ID/version, nhưng không để dữ liệu request của người này rò sang request khác.

**Đặt giới hạn timeout và resource:** riêng `Future.cancel(true)` hoặc ngắt một Java thread không luôn bảo đảm dừng được mọi đường thực thi engine. Nếu yêu cầu cô lập mạnh, dùng process boundary và khả năng hủy worker.

**Đo trên đúng workload:** benchmark phép cộng đơn giản có thể không phản ánh script thực tế gọi Java method, parse JSON, tạo object hoặc truy cập dữ liệu. Cần đo thời gian khởi tạo, throughput ổn định, độ trễ P95/P99, memory và thời gian sau warm-up.

**Quản lý phiên bản dependency:** engine runtime và các phụ thuộc đi kèm phải được cập nhật bảo mật cùng chu kỳ ứng dụng. Khi nâng engine, chạy lại suite tương thích script giống như nâng JDK.

## 19. Quy trình migration Nashorn theo từng bước

### Bước 1: Xác định phạm vi sử dụng

Lấy danh sách call sites, script ID, nơi lưu script, các Java object được truyền vào, engine version và JDK runtime hiện tại. Đánh dấu script chứa Nashorn-specific features hoặc có quyền truy cập host rộng.

### Bước 2: Chốt hợp đồng hành vi

Với mỗi script quan trọng, ghi nhận input, output, lỗi kỳ vọng, side effects, timezone, độ chính xác số và thời gian chạy. Lưu script representative/golden fixtures đã loại thông tin nhạy cảm.

### Bước 3: Chọn runtime thay thế

Đối chiếu yêu cầu Java interop, ECMAScript, npm package, isolation, baseline JDK, license và vận hành. Làm proof-of-concept trên tập script đại diện.

### Bước 4: Tách adapter

Đưa code gọi engine vào một module/lớp chuyên trách. Định nghĩa dữ liệu vào/ra độc lập với `ScriptObjectMirror`, `Value` và các object riêng của engine.

### Bước 5: Chạy song song để so sánh

Trong test hoặc môi trường staging, đánh giá cùng một input bằng engine cũ và engine mới. So sánh kết quả theo **ngữ nghĩa** thay vì so sánh chuỗi thô nếu thứ tự property, kiểu số hoặc biểu diễn exception có thể khác.

### Bước 6: Kiểm tra bảo mật và tài nguyên

Thử script có vòng lặp vô hạn, truy cập class/file không được phép, input lớn, exception, `null`, `undefined`, hoạt động đồng thời và lỗi khởi tạo provider.

### Bước 7: Triển khai theo tỷ lệ

Nếu hệ thống hỗ trợ, chuyển từng nhóm script hoặc một tỷ lệ traffic sang runtime mới. Theo dõi tỷ lệ lỗi, thời gian chạy, bộ nhớ, sự khác biệt output và số lần fallback.

### Bước 8: Ngừng phụ thuộc Nashorn cũ

Sau khi đã xác nhận không còn script cần engine cũ, xóa dependency, flag compatibility, import riêng, lệnh `jjs` và cấu hình thừa. Cập nhật tài liệu về JavaScript runtime được hỗ trợ.

## 20. Ví dụ kiểm thử tương thích hành vi

Giả sử hệ thống có script tính mức giảm giá:

```javascript
function calculateDiscount(subtotal, isMember) {
    if (subtotal >= 1000 && isMember) {
        return 0.10;
    }
    return 0;
}
```

Một bộ fixture có thể dùng:

| Subtotal | Member | Kết quả kỳ vọng |
|---:|---|---:|
| 999.99 | true | 0 |
| 1000.00 | true | 0.10 |
| 1500.00 | false | 0 |
| 1500.00 | true | 0.10 |

Trong Java, adapter có thể chạy script và trả về một object `RuleResult` hoặc giá trị số theo hợp đồng. Test so sánh kết quả với fixture trên cả engine nguồn và engine đích. Ngoài ví dụ đơn giản, cần có fixture cho giới hạn số, `null`, exception, xử lý array/object và những helper Nashorn đang được sử dụng.

Một lỗi migration phổ biến là test chỉ xác nhận “script không ném exception”. Điều đó không phát hiện thay đổi ẩn về giá trị mặc định, làm tròn hoặc cách chọn overload của Java method.

## 21. Những lỗi thường gặp sau khi nâng JDK

### 21.1. `getEngineByName(...)` trả về `null`

**Dấu hiệu:** mã dùng `ScriptEngineManager` nhưng không có provider nào phù hợp, rồi phát sinh `NullPointerException`.

**Cách xử lý:** kiểm tra `getEngineFactories()`, thêm đúng engine/adapter dependency và đảm bảo classpath/module path phản ánh môi trường thực tế. Đổi tên engine theo alias mà provider công bố.

### 21.2. `ClassNotFoundException` hoặc `NoClassDefFoundError` cho `jdk.nashorn.*`

**Dấu hiệu:** mã Java import class riêng của Nashorn JDK cũ.

**Cách xử lý:** thay API engine-specific bằng adapter hiện đại. Nếu dùng standalone Nashorn, kiểm tra package/module mới và migration notes, không suy đoán package cũ đã được phục hồi.

### 21.3. `NoSuchFileException` / `command not found` khi gọi `jjs`

**Dấu hiệu:** script vận hành vẫn gọi shell Nashorn tích hợp của JDK.

**Cách xử lý:** thay command bằng runner mới, đóng gói runtime đi kèm và cập nhật CI/container image.

### 21.4. `Java is not defined` hoặc không truy cập được Java class

**Dấu hiệu:** script chứa `Java.type` hoặc package globals nhưng engine không có Java interop/không được cấp quyền.

**Cách xử lý:** xác định nhu cầu thực, dùng bindings/host API giới hạn hoặc cấu hình host class lookup ở phạm vi cho phép. Tránh bật quyền toàn bộ để chạy qua lỗi ban đầu.

### 21.5. Script chạy được trên máy phát triển nhưng lỗi khi đóng gói JPMS

**Dấu hiệu:** engine được phát hiện trên classpath nhưng không xuất hiện sau khi chuyển sang module path hoặc custom runtime image.

**Cách xử lý:** kiểm tra các module `java.scripting`, engine adapter module, service provider registration, resolved module graph và tham số của `jlink` nếu có.

### 21.6. Output lệch dù không có exception

**Dấu hiệu:** script trả về giá trị khác do ép kiểu số, semantics `null`/`undefined`, timezone hoặc xử lý object.

**Cách xử lý:** so sánh golden fixtures theo hợp đồng dữ liệu; sửa mapping ở adapter hoặc chuẩn hóa JS.

### 21.7. JavaScript chạy quá lâu hoặc làm tăng memory

**Dấu hiệu:** script có vòng lặp không kết thúc, giữ object lớn, cache context không đúng hoặc khởi tạo engine lặp lại.

**Cách xử lý:** đặt ngân sách tài nguyên, đo trên workload thực tế, quản lý vòng đời và cân nhắc chạy script ở tiến trình riêng nếu cần cô lập.

## 22. Checklist trước khi phát hành bản nâng cấp

- [ ] Đã tìm mọi chỗ gọi Nashorn, JSR-223 và `jjs`.
- [ ] Đã xác định script ở repository, tài nguyên, cấu hình và database.
- [ ] Đã lập danh sách Nashorn-specific extensions và Java interop.
- [ ] Đã biết tên, version, dependency và baseline JDK của runtime thay thế.
- [ ] Đã xác nhận runtime mới được đóng gói trong artifact/container.
- [ ] Đã tách contract đầu vào/đầu ra khỏi class của engine cũ.
- [ ] Đã kiểm thử kết quả JS trên các giá trị biên và golden fixtures.
- [ ] Đã kiểm tra việc chuyển đổi `null`, `undefined`, số, array/object và exception.
- [ ] Đã thiết kế chính sách host access và giới hạn tài nguyên phù hợp.
- [ ] Đã kiểm thử concurrency, cache và lifecycle của context/engine.
- [ ] Đã kiểm thử classpath, module path hoặc custom image đúng cấu hình triển khai.
- [ ] Đã có phương án rollback/fallback và chỉ số giám sát sau phát hành.
- [ ] Đã có kế hoạch bỏ engine/compatibility flag cũ khi kết thúc giai đoạn chuyển tiếp.

## Tài liệu tham khảo

- [JEP 335 — Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): mốc deprecated trong JDK 11.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): quyết định loại bỏ Nashorn ở JDK 15 và phạm vi ảnh hưởng.
- [Oracle JDK 15 Migration Guide](https://docs.oracle.com/en/java/javase/15/migrate/): thay đổi công cụ và thành phần của JDK 15.
- [Java API — ScriptEngineManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.scripting/javax/script/ScriptEngineManager.html): cơ chế khám phá engine theo JSR-223.
- [GraalJS — Run JavaScript on the JVM](https://www.graalvm.org/latest/reference-manual/js/RunOnJDK/): cách bổ sung dependency và nhúng GraalJS.
- [GraalJS — Nashorn Migration Guide](https://www.graalvm.org/latest/reference-manual/js/NashornMigrationGuide/): khác biệt Java interop và compatibility mode.
- [GraalJS — ScriptEngine](https://www.graalvm.org/latest/reference-manual/js/ScriptEngine/): adapter JSR-223 và cách cấu hình.
- [OpenJDK Standalone Nashorn](https://github.com/openjdk/nashorn): dự án engine Nashorn độc lập.
- [Mozilla Rhino](https://github.com/mozilla/rhino): engine JavaScript viết bằng Java và release notes.
- [GraalJS — JavaScript Modules and Packages](https://www.graalvm.org/reference-manual/js/NodeJSvsJavaScriptContext/): khác biệt giữa JavaScript nhúng và Node.js.

## Kết luận

Nashorn từng là engine JavaScript tích hợp trong JDK nhưng đã deprecated ở JDK 11 và bị loại bỏ từ JDK 15. Ứng dụng có thể tiếp tục dùng `javax.script` nếu bổ sung engine tương thích, nhưng việc giữ API `ScriptEngine` không tự bảo đảm script Nashorn sẽ chạy đúng. GraalJS với `Context` phù hợp khi cần nhúng JavaScript hiện đại trong JVM và kiểm soát Java interop; GraalJS JSR-223 hoặc standalone Nashorn có thể hỗ trợ giai đoạn chuyển tiếp; Rhino và Node.js phù hợp với những yêu cầu khác về runtime và hệ sinh thái. Quyết định nên dựa trên script thực tế, mức cần truy cập Java, baseline JDK, bảo mật và chi phí vận hành, sau đó được xác nhận bằng golden fixtures và kiểm thử trên môi trường triển khai thật.
