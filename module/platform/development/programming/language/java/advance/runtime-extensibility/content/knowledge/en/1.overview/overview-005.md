# So sánh cấu hình, plugin Java, biên dịch động, kịch bản và JShell

Trong một ứng dụng Java, “mở rộng lúc chạy” có thể có nghĩa rất khác nhau: đổi một tham số, chọn một cách xử lý đã viết sẵn, bổ sung một thư viện mới, nhận mã Java để biên dịch, thực thi một ngôn ngữ kịch bản, hoặc thử nhanh vài dòng lệnh trong JShell. Năm cách này giải quyết những nhu cầu khác nhau và có ranh giới triển khai, kiểm thử, bảo mật khác nhau.

## 1. Bức tranh tổng thể: thứ gì thực sự được thay đổi?

| Cách tiếp cận | Đầu vào làm thay đổi hành vi | Cơ chế Java tiêu biểu | Có thêm logic mới mà không biên dịch lại ứng dụng chính? | Phù hợp nhất |
|---|---|---|---|---|
| **Cấu hình (configuration)** | Giá trị, cờ, tham số, tên chiến lược | Properties/YAML, biến môi trường, system properties, cấu hình do ứng dụng tự đọc | **Không**, nếu chỉ chọn trong những nhánh đã có | Đổi timeout, giới hạn, feature flag, chọn implementation có sẵn |
| **Plugin Java** | JAR chứa class đã biên dịch và hợp đồng mở rộng | Interface/SPI, §ServiceLoader§, class loader, JPMS | **Có**: thêm implementation đã build, miễn tương thích API | Tích hợp adapter, định dạng, provider, tính năng độc lập |
| **Biên dịch Java động** | Mã nguồn §.java§ nhận khi ứng dụng đang chạy | §javax.tools.JavaCompiler§, §java.compiler§, class loader | **Có**: tạo class từ nguồn Java mới | Code generation, công cụ học tập, rule đặc biệt cần Java |
| **Kịch bản (scripting)** | Nội dung script của một ngôn ngữ được engine hỗ trợ | §javax.script§ / JSR 223 hoặc API engine riêng | **Có**, trong phạm vi ngôn ngữ/engine được cài | Quy tắc thay đổi thường xuyên, automation, DSL, glue code |
| **JShell** | Snippet Java nhập tương tác | Công cụ §jshell§, module/API §jdk.jshell§ | **Có** trong phiên đánh giá snippet; không mặc nhiên là plugin sản phẩm | Khám phá API, chẩn đoán, dạy học, prototype |

**Cần phân biệt ba loại linh hoạt:**

- **Đổi dữ liệu điều khiển:** cấu hình chọn hành vi đã được lập trình và phát hành.
- **Bổ sung mã thực thi:** plugin, biên dịch động hoặc scripting đưa thêm logic chạy vào hệ thống; sự khác nhau nằm ở nguồn mã, cách đóng gói và thời điểm kiểm tra lỗi.
- **Thử nghiệm tương tác:** JShell giúp con người đánh giá Java ngay trong phiên làm việc; không tự cung cấp vòng đời, triển khai hay hợp đồng cho plugin production.

Không phương án nào tự động bảo đảm “hot reload”. Việc phát hiện thay đổi, tạo đối tượng mới, chuyển trạng thái, đóng tài nguyên và khôi phục khi lỗi phải được thiết kế riêng.

## 2. Cấu hình: thay đổi quyết định, không tự tạo thuật toán mới

Cấu hình là lựa chọn ít phức tạp nhất khi ứng dụng đã biết những cách xử lý có thể dùng. Giá trị cấu hình có thể được đọc khi khởi động, tại mỗi yêu cầu, theo lịch làm mới, hoặc được đẩy qua một cơ chế cập nhật. **Một file cấu hình thay đổi không đồng nghĩa chương trình đang chạy tự tải lại nó.**

Ví dụ Java 17: chọn cách chuẩn hóa chuỗi bằng system property; cả hai cách xử lý đều đã được biên dịch.

Tệp §ConfigDemo.java§:

```java
import java.util.Locale;

public class ConfigDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String input);
    }

    public static void main(String[] args) {
        String mode = System.getProperty("format.mode", "identity");

        Formatter formatter = switch (mode) {
            case "identity" -> text -> text;
            case "upper" -> text -> text.toUpperCase(Locale.ROOT);
            default -> throw new IllegalArgumentException(
                    "Unsupported format.mode: " + mode);
        };

        System.out.println(formatter.format("java"));
    }
}
```

Biên dịch và chạy:

```bash
javac ConfigDemo.java
java ConfigDemo
java -Dformat.mode=upper ConfigDemo
```

Hai lần chạy lần lượt in ra:

```text
java
JAVA
```

Ở đây §-Dformat.mode=upper§ chỉ chọn nhánh §upper§. Thêm thuật toán dịch ngôn ngữ, kết nối hệ thống mới, hay xử lý một định dạng chưa biết vẫn cần mã đã được triển khai (trực tiếp hoặc qua một cơ chế mở rộng khác).

**Thiết kế tốt:** có schema/default rõ ràng; từ chối giá trị không hợp lệ; ghi nhận phiên bản cấu hình; làm mới một cách nguyên tử nếu cho phép reload; tránh dùng giá trị cấu hình làm tên class hoặc câu lệnh tùy ý mà không kiểm soát. Cấu hình là dữ liệu điều khiển, không phải vùng chạy mã tùy tiện.

## 3. Plugin Java: thêm implementation đã biên dịch qua hợp đồng ổn định

Một plugin thực hiện **extension point** mà ứng dụng chủ công bố: interface, dữ liệu đầu vào/đầu ra, quy tắc lỗi, phiên bản API và vòng đời. §ServiceLoader§ là cơ chế SPI có sẵn của Java để phát hiện provider. Thư viện như PF4J hoặc framework plugin riêng có thể bổ sung quản lý vòng đời, phiên bản và cô lập, nhưng hợp đồng với ứng dụng vẫn là vấn đề cốt lõi.

### Ví dụ chạy được: nạp plugin từ JAR qua §ServiceLoader§

Tạo các tệp theo cấu trúc:

```text
src/
  demo/
    api/TextPlugin.java
    app/Main.java
    plugins/UppercasePlugin.java
resources/
  META-INF/
    services/demo.api.TextPlugin
```

§src/demo/api/TextPlugin.java§:

```java
package demo.api;

public interface TextPlugin {
    String name();
    String apply(String input);
}
```

§src/demo/plugins/UppercasePlugin.java§:

```java
package demo.plugins;

import demo.api.TextPlugin;
import java.util.Locale;

public final class UppercasePlugin implements TextPlugin {
    @Override
    public String name() {
        return "uppercase";
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

§src/demo/app/Main.java§:

```java
package demo.app;

import demo.api.TextPlugin;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        boolean found = false;
        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            found = true;
            System.out.println(
                    plugin.name() + " = " + plugin.apply("java plugin"));
        }
        if (!found) {
            System.out.println("No plugin found");
        }
    }
}
```

Nội dung tệp **§resources/META-INF/services/demo.api.TextPlugin§** chính xác là tên class provider:

```text
demo.plugins.UppercasePlugin
```

Từ thư mục chứa §src§ và §resources§, dùng JDK 17+:

```bash
javac -d app-out src/demo/api/TextPlugin.java src/demo/app/Main.java
javac -cp app-out -d plugin-out src/demo/plugins/UppercasePlugin.java
jar --create --file plugin.jar -C plugin-out . -C resources META-INF/services
```

Chạy trên Windows (classpath dùng dấu chấm phẩy):

```powershell
java -cp "app-out;plugin.jar" demo.app.Main
```

Trên Linux/macOS (classpath dùng dấu hai chấm):

```bash
java -cp "app-out:plugin.jar" demo.app.Main
```

Cả hai cách chạy đều in:

```text
uppercase = JAVA PLUGIN
```

**Điểm mấu chốt:** ứng dụng §Main§ chỉ biết §TextPlugin§; JAR mang implementation và descriptor ở §META-INF/services§. Provider phải truy cập được từ class loader mà §ServiceLoader§ dùng. Với project theo Java Platform Module System, có thể khai báo §uses§ và §provides ... with ...§ trong §module-info.java§ thay cho file service của cơ chế classpath; việc resolve module và cấp quyền §exports§/§opens§ phải được xét riêng.

**Giới hạn thực tế:**

- §ServiceLoader.load(TextPlugin.class)§ phát hiện provider đang khả dụng qua class loader được chọn; nó **không tự theo dõi thư mục JAR**, tải JAR mới liên tục hoặc thay class đã load.
- Nạp JAR sau khi ứng dụng đã chạy thường đòi hỏi thiết kế class loader riêng và gọi §ServiceLoader.load(TextPlugin.class, pluginLoader)§. Muốn cập nhật implementation phải tạo loader/instance mới và chuyển người dùng sang phiên bản mới; class cùng tên do hai class loader khác nhau định nghĩa vẫn là **hai kiểu khác nhau**.
- Giữ API chung ở phía class loader cha, quản lý version/compatibility, dependency conflict, khởi tạo/hủy, thread, kết nối và tham chiếu tĩnh; loader không được thu gom nếu còn tham chiếu sống.
- Plugin bên thứ ba là **mã Java có toàn bộ quyền của tiến trình**, trừ khi có cô lập ngoài JVM. Kiểm tra nguồn cung, chữ ký/hash artifact và cân nhắc chạy tiến trình riêng cho plugin không đáng tin.

## 4. Biên dịch động: nhận Java source, tạo bytecode và nạp class mới

Biên dịch động phù hợp khi logic mới được biểu diễn bằng **mã nguồn Java**, không chỉ là tham số và chưa tồn tại dưới dạng class/JAR. Pipeline khái quát:

```text
Java source -> JavaCompiler -> .class (bytecode)
            -> class loader -> liên kết với API/hợp đồng -> thực thi
```

§javax.tools.JavaCompiler§ thuộc module §java.compiler§, cho phép gọi compiler từ chương trình Java. §ToolProvider.getSystemJavaCompiler()§ có thể trả §null§ nếu runtime image không có trình biên dịch; cần môi trường JDK phù hợp. Biên dịch thành công chưa bảo đảm class an toàn, tương thích API hoặc không gây lỗi runtime.

### Ví dụ Java 17 chạy được: biên dịch một class lúc chương trình đang chạy

Tệp §CompileDemo.java§:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class CompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("No Java compiler in this runtime");
        }

        Path dir = Files.createTempDirectory("java-dynamic-");
        Path file = dir.resolve("HelloDynamic.java");

        String source = """
                public class HelloDynamic {
                    public static String greet() {
                        return "Compiled at runtime";
                    }
                }
                """;
        Files.writeString(file, source);

        int status = compiler.run(
                null, null, null, "-d", dir.toString(), file.toString());
        if (status != 0) {
            throw new IllegalStateException("Compilation failed: " + status);
        }

        URL[] urls = {dir.toUri().toURL()};
        try (URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader())) {
            Class<?> generated = Class.forName(
                    "HelloDynamic", true, loader);
            Object result = generated.getMethod("greet").invoke(null);
            System.out.println(result);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac CompileDemo.java
java CompileDemo
```

Stdout khi biên dịch thành công:

```text
Compiled at runtime
```

Ví dụ tạo file nguồn và class trong thư mục tạm, rồi gọi phương thức public bằng reflection. Mẫu thật thường cần §JavaFileManager§, chẩn đoán lỗi qua §DiagnosticCollector§, classpath/module path xác định, API chung, cache theo phiên bản và cơ chế dọn artefact tạm. Có thể biên dịch hoàn toàn trong bộ nhớ bằng file manager tùy chỉnh, nhưng JavaCompiler không tự thực hiện bước nạp/chạy class.

**Không coi “biên dịch được” là “an toàn để chạy”:** mã do người dùng gửi có thể đọc file, gọi mạng, tạo thread hoặc gọi native code theo quyền tiến trình. Class loader, kiểm tra cú pháp, timeout của một method hay §SecurityManager§ không phải hàng rào đáng tin cho mã không tin cậy. Nếu thật sự phải chạy Java tùy ý, dùng tiến trình/container có giới hạn quyền, CPU, bộ nhớ, thời gian và mạng ở mức hệ điều hành; thiết kế đường dừng và thu hồi tài nguyên.

## 5. Scripting: diễn giải/chạy kịch bản thông qua một engine

Scripting thích hợp khi người biên soạn cần sửa quy tắc hay công thức thường xuyên mà không muốn build JAR cho mỗi thay đổi. Java cung cấp API chung §javax.script§ (JSR 223): tìm engine, truyền biến qua §Bindings§, gọi §eval§ và nhận kết quả. **API không đồng nghĩa có sẵn engine cho mọi ngôn ngữ.**

Đặc biệt, **Nashorn JavaScript engine đã bị loại khỏi JDK kể từ JDK 15**. Một JDK 17 chuẩn không tự có engine tên §JavaScript§ để §ScriptEngineManager§ tìm thấy. Muốn chạy JavaScript, Groovy hay ngôn ngữ khác, phải bổ sung engine tương thích và các dependency cần thiết, hoặc dùng API riêng của engine.

Tệp §ScriptDemo.java§:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class ScriptDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("No JavaScript engine installed");
            return;
        }

        engine.put("amount", 40);
        Object result = engine.eval("amount + 2");
        System.out.println(result);
    }
}
```

Biên dịch/chạy:

```bash
javac ScriptDemo.java
java ScriptDemo
```

Trên JDK 17 **không cài engine bổ sung**, stdout:

```text
No JavaScript engine installed
```

Nếu thêm engine JavaScript tương thích, nhánh §eval§ được chạy; kiểu trả về và cách hiển thị số tùy engine nên không giả định một stdout chung cho mọi engine. Với script thực tế nên quy định rõ API được phép gọi, kiểu dữ liệu vào/ra, phiên bản engine, chính sách lỗi, timeout, audit và cách cập nhật script. Nếu chỉ cần một ngôn ngữ luật hẹp, một DSL/biểu thức có cú pháp và phép toán giới hạn thường dễ kiểm soát hơn cho người dùng cuối.

**Cảnh báo vận hành:** script có quyền gọi Java/IO hay API host tùy engine và cấu hình thì có thể mạnh như mã plugin. Chỉ giới hạn biến đưa vào §Bindings§ không đủ làm sandbox. Không chạy script không đáng tin trong tiến trình nghiệp vụ có quyền nhạy cảm nếu chưa có cô lập phù hợp.

## 6. JShell: Java REPL để thử nghiệm, không phải engine kịch bản mặc định

§jshell§ là công cụ **Read–Eval–Print Loop** xuất hiện từ Java 9: nhập biểu thức, khai báo biến, method hoặc class, rồi nhận phản hồi mà không tạo trước một project Java. Khác JavaScript script engine, JShell đánh giá **snippet Java**. Nó hữu ích khi học API, kiểm tra giả thuyết và debug nhanh.

Ví dụ trong terminal có JDK 17+:

```text
$ jshell
jshell> int base = 40;
jshell> System.out.println(base + 2);
42
jshell> /exit
```

Dòng §42§ là stdout từ §System.out.println§; phần prompt/feedback của JShell có thể khác theo cấu hình và phiên. JShell còn có các lệnh §/help§, §/vars§, §/methods§, §/open§, §/save§. Khi cần nhúng vào ứng dụng, module §jdk.jshell§ cung cấp API §jdk.jshell.JShell§ để đánh giá snippet và theo dõi kết quả/sự kiện.

Điểm khác biệt với biên dịch Java động bằng §JavaCompiler§: JShell hỗ trợ vòng tương tác và trạng thái snippet qua nhiều lượt nhập, với quy tắc riêng cho khai báo/chỉnh sửa/thay thế snippet. Nó không thay cho một hệ thống build, kho version, hợp đồng plugin, dependency resolution hoặc cơ chế cập nhật an toàn. Dùng JShell làm “cho khách hàng nhập Java rồi chạy” vẫn đặt ra cùng vấn đề tin cậy mã như biên dịch và thực thi Java động.

## 7. Chọn cách nào theo nhu cầu?

| Tình huống | Ưu tiên | Lý do và điều kiện |
|---|---|---|
| Thay endpoint, timeout, mức log, bật một tính năng đã có | **Cấu hình** | Thay dữ liệu; có thể cần restart/reload theo cách ứng dụng thiết kế |
| Chọn một trong các thuật toán đã code sẵn theo tenant | **Cấu hình + Strategy** | Không cần plugin nếu tập thuật toán đóng và ít thay |
| Bên thứ ba cung cấp adapter xuất dữ liệu dưới dạng JAR | **Plugin Java** | Công bố interface/SPI, version API, quy trình đóng gói và kiểm thử |
| Nạp provider mới trong hệ thống đang phục vụ request | **Plugin + loader/vòng đời riêng** | §ServiceLoader§ đơn lẻ không giải quyết hot reload, chuyển phiên bản hoặc leak |
| Công cụ tạo class Java từ schema tại runtime | **Biên dịch động** | Có Java source, cần xử lý lỗi compiler và class loading |
| Người vận hành chỉnh quy tắc nghiệp vụ ngắn nhiều lần mỗi ngày | **Scripting hoặc DSL có kiểm soát** | Cần ngôn ngữ nhỏ, cập nhật/version/audit; không nhất thiết cần toàn bộ Java |
| Kỹ sư muốn thử API và quan sát kết quả vài dòng code | **JShell** | Phù hợp với phiên tương tác và học tập |
| Cho mã từ người dùng không đáng tin chạy trên server | **Đặt ranh giới an toàn trước khi chọn cơ chế** | Không cách nào trong năm cách tự cung cấp sandbox đáng tin |

Một sơ đồ quyết định ngắn:

```text
Có cần thêm thuật toán chưa được đóng gói?
├─ Không -> Cấu hình; có thể chọn Strategy đã biên dịch
└─ Có
   ├─ Đã có JAR theo extension API -> Plugin Java
   ├─ Có Java source cần biên dịch -> JavaCompiler + class loader
   ├─ Có script theo engine/DSL -> Scripting
   └─ Chỉ thử nghiệm Java tương tác -> JShell
```

Sơ đồ lựa chọn theo bản chất đầu vào; mức độ tin cậy và yêu cầu cô lập có thể khiến phương án phải thay đổi dù cùng loại đầu vào.

## 8. Kết hợp trong một kiến trúc mở rộng

Trong sản phẩm lớn, các cách trên có thể **bổ sung cho nhau**:

1. Ứng dụng công bố §TextPlugin§ (API ổn định); một số implementation tích hợp sẵn, một số đến từ JAR ngoài.
2. §ServiceLoader§ hoặc plugin registry phát hiện các provider và quản lý phiên bản, trạng thái sẵn sàng.
3. Cấu hình §transform.provider=uppercase§ chọn provider đang có. Đổi cấu hình chỉ thay lựa chọn; thêm một provider mới vẫn đòi hỏi JAR và quy trình nạp.
4. Khi nghiệp vụ thật sự cần quy tắc mềm dẻo, một provider riêng có thể gọi DSL/script engine đã được quản trị. Điều đó không biến mọi plugin thành script.
5. JShell dành cho kỹ sư thử API hoặc điều tra lỗi trong môi trường được kiểm soát, không nằm trên đường chạy request của người dùng cuối.
6. Nếu nhận Java source, biên dịch động là pipeline riêng; kiểm thử và cách ly artifact trước khi cho bản biên dịch tham gia hệ thống thực.

Ví dụ luồng triển khai:

```text
Cấu hình chọn provider
        |
        v
Plugin registry --(SPI/API chung)--> Java plugin đã build
        |                               |
        |                               +--> xử lý nghiệp vụ
        +--> provider chạy DSL (nếu có engine)
        |
        +--> provider sinh từ Java source (nếu có pipeline compile riêng)

JShell: công cụ thăm dò/diagnostics ngoài luồng xử lý chính
```

Muốn “thay hành vi không restart”, cần thêm cơ chế quản trị phiên bản: xây phiên bản mới bên cạnh bản cũ, kiểm tra sức khỏe, chuyển request mới sang bản mới, để request cũ hoàn thành, đóng tài nguyên và có rollback. Không sửa trực tiếp class đã load hay kỳ vọng thay JAR trên đĩa lập tức thay bytecode đang chạy.

## 9. Các trục đánh đổi quan trọng

### Độ phức tạp và hiệu năng

- **Cấu hình:** rẻ nhất để triển khai và test; thay đổi thường chỉ ảnh hưởng đến chọn nhánh/giá trị, nhưng cơ chế reload cần đồng bộ và xử lý cấu hình lỗi.
- **Plugin:** chi phí nạp class/khởi tạo phụ thuộc số provider và dependency; khi đã nạp, lời gọi interface thông thường gần với code Java khác. Cần bảo đảm compatibility và vòng đời.
- **Biên dịch động:** tốn CPU/bộ nhớ cho biên dịch, có lỗi compile, quản lý file/class loader. Không nên compile lại cùng nguồn cho mỗi request; dùng hash/phiên bản để cache và công bố artifact đã kiểm thử.
- **Scripting:** phụ thuộc engine, phương thức eval/compile/cache và tương tác với JVM. Có thể tốn chi phí parse/interpret; không thể kết luận mọi script đều chậm hơn Java mà không benchmark workload thực.
- **JShell:** tối ưu cho phản hồi tương tác của người dùng, không nhằm làm đường thực thi giao dịch có throughput cao; duy trì state/snippet cũng cần kiểm soát tài nguyên.

### Bảo mật, kiểm thử và quản trị

| Cần kiểm tra | Cấu hình | Plugin | Biên dịch động | Scripting | JShell |
|---|---|---|---|---|---|
| Xác thực dữ liệu đầu vào | Schema, kiểu, giới hạn | Manifest, API, provenance | Source/policy/diagnostics | Script/policy/engine | Người dùng/phiên/snippet |
| Tương thích phiên bản | Schema config | API/ABI, dependency, JPMS | Compiler options, classpath | Engine + host API | Phiên bản JDK/module |
| Rollback | Cấu hình trước | JAR/registry trước | Artifact/class loader trước | Script version trước | Khởi tạo lại session |
| Cô lập mã không tin cậy | Thường không phát sinh mã mới | Cần process isolation | Cần process isolation | Cần process isolation nếu script mạnh | Cần process isolation |
| Quan sát lỗi | Validation/reload logs | Provider id, init, timeout | Diagnostic + runtime trace | Script id, engine, stack trace | Snippet status/event |

**Quy tắc thiết kế:** ghi log *phiên bản cụ thể đang thực thi* (config revision, plugin id/version, hash source/class, script id/version); giới hạn tài nguyên; có circuit breaker/timeout phù hợp; không để nhà cung cấp plugin giữ bí mật hoặc dependency nội bộ ngoài hợp đồng; phân biệt lỗi nạp, lỗi compile và lỗi khi thực thi.

## 10. Những nhầm lẫn thường gặp

1. **“Đổi YAML là có logic mới.”** Sai: YAML chỉ chứa dữ liệu; logic mới phải được build/nạp hoặc được một engine có khả năng thực thi xử lý.
2. **“ServiceLoader là hot swap.”** Sai: SPI giúp tìm provider, không tự cập nhật JAR, đổi implementation của object đang dùng hoặc thu hồi class loader.
3. **“Class loader là sandbox.”** Sai: nó cô lập namespace và hỗ trợ nạp class; không mặc nhiên chặn file, mạng, thread hay native access của mã được nạp.
4. **“JavaCompiler chạy code ngay.”** Sai: compiler tạo class/diagnostics; để thực thi cần bước nạp class và gọi method theo một hợp đồng.
5. **“Java 17 có sẵn JavaScript qua javax.script.”** Sai với JDK 17 tiêu chuẩn: API tồn tại nhưng Nashorn không còn; phải cài engine tương ứng.
6. **“JShell và JavaScript là một.”** Sai: JShell xử lý snippet **Java**, còn JavaScript là một ngôn ngữ khác cần runtime/engine riêng.
7. **“Chạy script hoặc snippet là vô hại hơn plugin.”** Sai: mức rủi ro phụ thuộc quyền thực tế và khả năng truy cập host; phần mở rộng có thể gây lỗi, rò dữ liệu hoặc làm cạn tài nguyên.
8. **“Thêm plugin là không cần deploy.”** Không nhất thiết: nếu app chỉ scan classpath lúc startup thì phải triển khai JAR và khởi động lại; live plugin loader là tính năng phải chủ động xây.
9. **“Chọn phương án linh hoạt nhất sẽ tốt nhất.”** Không: mỗi cơ chế thêm bề mặt lỗi, quản trị phiên bản và bảo mật. Chọn cơ chế đơn giản nhất vẫn đáp ứng loại thay đổi cần hỗ trợ.

**Ghi nhớ:** cấu hình **chọn** hành vi có sẵn; plugin **cắm thêm** Java bytecode đã build qua API; biên dịch động **tạo** bytecode từ Java source; scripting **đánh giá** chương trình bằng một engine; JShell **thử** Java tương tác. Xác định đầu vào thay đổi và ranh giới tin cậy trước khi chọn công cụ.