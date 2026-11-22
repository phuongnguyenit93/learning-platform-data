# Xác minh môi trường thiếu compiler, engine kịch bản hoặc module bắt buộc

## 1. Tại sao phải kiểm tra khả năng của runtime?

Một ứng dụng Java mở rộng lúc chạy có thể biên dịch source do người dùng cung cấp, thực thi script qua JSR 223, tìm provider bằng SPI hoặc nạp named modules qua JPMS. Những khả năng đó **không được bảo đảm chỉ vì chương trình đang chạy trên Java 17+**. Một runtime image tạo bằng `jlink` có thể cố ý loại `jdk.compiler`, `jdk.jshell`, `java.scripting` hoặc module khác; một JDK đầy đủ cũng không mặc nhiên cài sẵn JavaScript engine.

Vì vậy, trước khi kích hoạt plugin, host cần kiểm tra khả năng cần thiết trong **đúng process, module graph và class loader đang được sử dụng**, rồi phân biệt:

- **Thiếu module/API**: runtime không chứa hoặc không resolve module cần thiết.
- **Có API nhưng thiếu implementation/provider**: ví dụ có `java.scripting` nhưng `ScriptEngineManager` không tìm thấy JavaScript engine.
- **Có provider nhưng không sử dụng được**: lỗi version, dependency, class loader, module access, native library hoặc khi khởi tạo.
- **Có khả năng nhưng policy cấm**: tổ chức không cho chạy compiler/script không tin cậy trong process host.

Một preflight tốt phải tạo kết quả rõ ràng để deployment hoặc UI quyết định fail-fast hay degrade theo chức năng. Không đợi đến khi nhận request đầu tiên mới phát hiện compiler hoặc engine không có.

## 2. Ma trận thành phần cần kiểm tra

| Khả năng | Module/API liên quan | Kiểm tra nhanh | Diễn giải đúng |
|---|---|---|---|
| Compiler Java lúc chạy | `java.compiler` API, implementation thường là `jdk.compiler` | `ToolProvider.getSystemJavaCompiler()` | `null` nghĩa system compiler không khả dụng trong runtime hiện tại |
| Script engine JSR 223 | `java.scripting` | `new ScriptEngineManager(loader).getEngineFactories()` | Danh sách rỗng: không tìm thấy factory qua manager/loader đó |
| Engine ngôn ngữ cụ thể | Provider JSR 223 của ngôn ngữ | `getEngineByName("...")` | `null`: không có engine với alias đó trong phạm vi manager |
| JShell nhúng | `jdk.jshell` | `ModuleLayer.boot().findModule("jdk.jshell")` và thử tạo phiên khi áp dụng | Module có mặt không đồng nghĩa execution provider khởi động thành công |
| Named module/plugin | JPMS `ModuleFinder`, `ModuleLayer` | Xem `findModule`, resolve graph hoặc finder theo path | Module hiện diện trên disk chưa chắc đã được resolve |
| SPI service provider | `ServiceLoader` | Duyệt providers trong loader/layer phù hợp | Đúng module, `uses`/`provides`/service descriptor và class identity đều quan trọng |

**Phân biệt availability và readiness:** một API hiện diện chưa chắc provider hoạt động. Khi yêu cầu nghiệp vụ quan trọng, nên thực hiện phép thử nhỏ có kiểm soát (compile probe, tạo engine, resolve module) thay vì chỉ kiểm tra tên class tồn tại.

## 3. Compiler: API có thể có nhưng compiler vắng mặt

Java Compiler API là `javax.tools`. Gọi:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // Không thể dùng system compiler trong runtime này.
}
```

Đoạn trên là minh họa, cần import `javax.tools.JavaCompiler` và `javax.tools.ToolProvider`. Trên JDK thông thường có `jdk.compiler`, nhưng runtime image tối giản hoặc môi trường cung cấp JRE/runtime khác có thể không hỗ trợ. Không nên chỉ kiểm tra `Class.forName("javax.tools.JavaCompiler")`: đó là interface API, không chứng minh implementation compiler sẵn có.

### 3.1. Compile probe và policy

Khi `compiler != null`, nếu việc biên dịch là chức năng bắt buộc, host có thể thử biên dịch một đơn vị Java nhỏ trong thư mục tạm có kiểm soát. Cần đặt `-proc:none` để tránh annotation processors không cần thiết, giới hạn output directory, thu thập diagnostics, đóng file manager và dọn temporary files sau phép thử.

Nên phân biệt `compiler unavailable`, `compile probe failed` và `compiler disabled by policy` thay vì báo chung 'Java lỗi'. Nếu compiler vắng mặt nhưng sản phẩm chỉ load plugin JAR đã biên dịch trước, có thể tắt tính năng dynamic compilation và tiếp tục vận hành bình thường.

## 4. Script engine: `java.scripting` không mang sẵn ngôn ngữ

JSR 223 cung cấp interface `ScriptEngine`, `ScriptEngineFactory` và `ScriptEngineManager`. Engine cụ thể do provider cài qua class path/module path hoặc một cách triển khai phù hợp.

```java
ScriptEngineManager manager =
        new ScriptEngineManager(Thread.currentThread().getContextClassLoader());
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    // Alias JavaScript không được provider hiện tại cung cấp.
}
```

Đây là đoạn minh họa cần import `javax.script.*`. Kể từ JDK 15, Nashorn đã bị loại khỏi JDK; do đó trên JDK 17 thông thường `getEngineByName("JavaScript")` trả `null` nếu chưa cài engine tương thích. Không nên khẳng định mọi máy Java 17 đều có JavaScript.

Các kiểm tra bổ sung:

1. Duyệt `manager.getEngineFactories()` để báo metadata ngôn ngữ và alias thực tế, tránh tự đoán tên.
2. Chọn đúng class loader để khám phá JSR 223 provider; một manager tạo với loader khác có thể không thấy engine trong plugin JAR.
3. Nếu provider nằm trong custom `ModuleLayer`, cân nhắc `ServiceLoader.load(layer, ScriptEngineFactory.class)` vì manager không tự quét mọi layer tùy ý.
4. Đánh giá nhanh `engine.eval(...)` bằng một biểu thức nhỏ theo ngôn ngữ thực tế **chỉ khi engine được tin cậy và preflight cho phép chạy mã**.

Đừng dùng script nhận từ khách hàng làm startup probe; kiểm thử engine cần source cố định, ít tác dụng phụ và có giới hạn tài nguyên.

## 5. Module bắt buộc: có trên đường dẫn chưa chắc được resolve

JPMS tách khả năng **tìm module** (`ModuleFinder`) khỏi **đồ thị module đã resolve** (`Configuration`) và **module runtime thực tế** (`ModuleLayer`).

```java
boolean inBoot = ModuleLayer.boot().findModule("jdk.jshell").isPresent();
boolean inImage = java.lang.module.ModuleFinder.ofSystem()
        .find("jdk.jshell").isPresent();
```

Đây là snippet minh họa: `inImage` cho biết module có trong tập system modules mà finder nhìn thấy; `inBoot` cho biết module nằm trong boot layer hoặc ancestors được tìm. Kết quả có thể khác nhau nếu module có sẵn trong image nhưng không thuộc tập đã resolve. Khi một plugin ở child layer, cần kiểm tra `pluginLayer.findModule(...)` thay vì chỉ nhìn boot layer.

### 5.1. Kiểm tra bắt buộc trước khi định nghĩa child layer

Giả sử thư mục `plugins/` chứa các modular JAR. Host có thể dùng:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
boolean found = finder.find("demo.plugin").isPresent();
```

Đoạn này cần import `java.lang.module.ModuleFinder`, `java.nio.file.Path`. Có file JAR không đủ: module descriptor có thể không hợp lệ, tên module có thể khác kỳ vọng, dependency bắt buộc có thể thiếu, hoặc split packages/module conflicts khiến resolve thất bại.

Để biết plugin thực sự chạy được, cần giải quyết configuration từ parent, kiểm tra dependencies rồi tạo layer theo policy. Lỗi nên được báo dưới nhóm như missing module, resolution conflict, layer instantiation failure thay vì tự động bỏ qua.

### 5.2. Lệnh chẩn đoán của JDK

```bash
java --list-modules
java --describe-module jdk.jshell
java --show-module-resolution --module-path mods \
  --module demo.host/demo.host.Main
```

Lệnh cuối là **mẫu cú pháp**, cần `mods` và module `demo.host` có thật. `--list-modules` cho biết các observable modules trong môi trường launcher, còn `--show-module-resolution` giúp quan sát graph khi chạy. Không suy ra rằng module được liệt kê đã được resolve vào mọi layer.

## 6. Ví dụ hoàn chỉnh Java 17+: báo cáo preflight runtime

Ví dụ sau dùng các API có trong JDK 17 đầy đủ. Nó **không yêu cầu một script engine cụ thể** và không đánh giá script không tin cậy. Thay vì in danh sách biến thiên theo máy, nó in các boolean để có thể so sánh theo cấu hình.

Tạo file `RuntimePreflight.java`:

```java
import java.lang.module.ModuleFinder;
import java.util.List;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.tools.ToolProvider;

public final class RuntimePreflight {
    public static void main(String[] args) {
        boolean compiler = ToolProvider.getSystemJavaCompiler() != null;
        System.out.println("compiler available: " + compiler);

        boolean scriptingModule = ModuleFinder.ofSystem()
                .find("java.scripting").isPresent();
        System.out.println("java.scripting in image: " + scriptingModule);

        boolean jshellModule = ModuleFinder.ofSystem()
                .find("jdk.jshell").isPresent();
        System.out.println("jdk.jshell in image: " + jshellModule);

        ScriptEngineManager manager = new ScriptEngineManager();
        List<ScriptEngineFactory> factories = manager.getEngineFactories();
        boolean javascriptEngine = manager.getEngineByName("JavaScript") != null;
        System.out.println("javascript engine available: " + javascriptEngine);
        System.out.println("factory count nonnegative: " + (factories.size() >= 0));

        boolean javaBaseResolved = ModuleLayer.boot()
                .findModule("java.base").isPresent();
        System.out.println("java.base resolved: " + javaBaseResolved);
    }
}
```

Biên dịch và chạy bằng JDK 17+ với module API liên quan có sẵn:

```bash
javac RuntimePreflight.java
java RuntimePreflight
```

Trên JDK 17 **đầy đủ, thông thường, không cài thêm JavaScript engine**, một đầu ra điển hình:

```text
compiler available: true
java.scripting in image: true
jdk.jshell in image: true
javascript engine available: false
factory count nonnegative: true
java.base resolved: true
```

Đây là output **theo môi trường giả định cụ thể**; kết quả thật khác nếu runtime image tối giản, engine provider bổ sung, module bị loại bỏ hoặc class loader khác. Lệnh `javac` ở ví dụ cũng không thể chạy nếu môi trường hoàn toàn thiếu compiler. Trong môi trường không có `java.scripting`, chính chương trình có import `javax.script` có thể không link/run được; vì vậy phép thử này phù hợp cho **build đầy đủ**, không phải universal probe có thể chạy ở mọi image.

### 6.1. Thiết kế preflight thật sự an toàn với module thiếu

Nếu ứng dụng phải chạy trong image **không có `java.scripting`**, không nên đặt mọi phép kiểm tra engine trong entrypoint chính có static imports/đường dẫn thực thi bắt buộc. Hãy tách một bootstrap module nhỏ chỉ dùng Java SE tối thiểu, phát hiện module trước, rồi chỉ nạp class adapter JSR 223 khi API có sẵn. Có thể tổ chức các feature adapters trong JAR/module tùy chọn, hoặc sử dụng reflection có kiểm soát để tránh hard linkage ở đường code phải chạy khi API thiếu.

Tương tự, với `jdk.jshell` và `jdk.compiler`, việc import và khởi tạo class phụ thuộc trực tiếp có thể khiến host fail khi runtime image loại module; nên thiết kế loader/feature boundary rõ, có kiểm thử bằng từng runtime image thực.

## 7. Kiểm thử thiếu khả năng bằng ma trận môi trường

Đừng chỉ chạy test trên máy developer có full JDK. Tạo ma trận chạy với các image khác nhau và quyền thực thi khác nhau:

| Môi trường | Kỳ vọng |
|---|---|
| Full JDK 17+, không thêm engine script | Compiler thường có; JavaScript engine có thể không có |
| Custom image `jlink` không có `jdk.compiler` | Chức năng dynamic compilation phải báo unavailable hoặc fail-fast đúng policy |
| Custom image không có `java.scripting` | Feature script bị tắt, core host vẫn hoạt động nếu boundary tách đúng |
| Image có `java.scripting` nhưng không có provider | Không có engine thực thi; thông báo missing provider |
| Có engine JAR nhưng loader sai | Factory không được phát hiện; không báo nhầm là lỗi syntax script |
| Thiếu named module bắt buộc | Resolution/activation bị chặn; không load một phần rồi tiếp tục |
| Module có đủ nhưng provider constructor lỗi | Trạng thái provider failed; cleanup, ghi nguyên nhân |

Để tạo runtime image thực tế, `jlink` yêu cầu closure module hợp lệ. Ví dụ (mang tính hướng dẫn; module set tùy ứng dụng):

```bash
jlink --add-modules java.base,java.logging \
  --output runtime-min
```

Image này không có compiler hay script API nếu không được thêm theo dependency closure. Một host cần `java.scripting` tĩnh sẽ không thể chạy trên image trên; phải tách feature và xây lại cấu hình image phù hợp. Không dùng `jlink` đơn giản để hứa rằng mọi API Java SE đã được loại bỏ có thể được phát hiện bằng code import trực tiếp.

## 8. Kiến trúc xử lý thiếu tính năng

Với từng capability, hãy xác định policy trước:

**Fail-fast:** Nếu sản phẩm bắt buộc compile Java lúc chạy hoặc cần một module contract thiết yếu để khởi động, trả lỗi startup có nguyên nhân và hướng xử lý, không tiếp tục một hệ thống ở trạng thái nửa hoạt động.

**Graceful degradation:** Nếu scripting chỉ là tính năng tùy chọn, tắt nút/chức năng đó, báo rõ nguyên nhân và giữ phần còn lại của host hoạt động. Đừng lặng lẽ thay engine bằng một ngôn ngữ khác hoặc fallback thực thi với semantics không tương thích.

**Retry sau cài bổ sung:** Thêm JAR vào filesystem khi JVM đã chạy không làm class loader/module graph tự thay đổi. Cần tạo manager mới với loader thích hợp hoặc resolve/tạo child layer tương ứng; trong vài trường hợp cần restart để có module/runtime image mới.

### Thông tin lỗi nên công bố

Một kết quả preflight có cấu trúc nên có: capability name, required/optional, status (`AVAILABLE`, `MISSING_API`, `MISSING_PROVIDER`, `BROKEN_PROVIDER`, `DISABLED_BY_POLICY`), nguyên nhân kỹ thuật, version và hướng khắc phục. Tránh log full environment variables, classpath chứa secret hoặc đường dẫn người dùng không cần thiết.

## 9. Lỗi dễ gặp và cách tránh

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Có `javax.tools.JavaCompiler` nên chắc compiler tồn tại | System compiler có thể là `null` | Kiểm tra `ToolProvider.getSystemJavaCompiler()` |
| Có `java.scripting` nên chắc chạy được JavaScript | JDK 17 không bao gồm Nashorn | Tìm engine provider theo alias/factory và kiểm tra thực tế |
| Thấy JAR trong `mods/` nên kết luận module đã nạp | Module chưa chắc đã được resolve | Kiểm tra `ModuleLayer`, `Configuration` và resolution |
| Gọi `Class.forName` với API optional ngay startup | App có thể fail trước khi kiểm tra khả năng | Tách feature adapter và lazy loading |
| Dùng `ScriptEngineManager` sai loader | Không tìm thấy engine dù JAR tồn tại | Truyền loader thích hợp hoặc dùng ServiceLoader theo layer |
| Tự động bỏ qua mọi lỗi provider | Che giấu deployment hỏng | Phân biệt missing và broken; giữ diagnostics |
| Test chỉ trên full JDK | Không phát hiện lỗi khi triển khai `jlink` image | Chạy thử trên image giống production |

## 10. Checklist triển khai

- [ ] Ghi rõ compiler, script engine, JShell và named modules nào bắt buộc/tùy chọn.
- [ ] Module APIs, provider implementations và runtime image được kiểm tra riêng.
- [ ] Class loader/module layer dùng cho preflight giống execution path thực tế.
- [ ] Có thông báo khác nhau cho missing API, missing provider, provider lỗi và policy deny.
- [ ] Có thử nghiệm trên image tối giản và image production.
- [ ] Mọi optional feature được cách ly khỏi đường bootstrap nếu module có thể thiếu.
- [ ] Không load/chạy mã plugin không tin cậy trong bước capability probe.
- [ ] Có fail-fast/graceful-degradation và rollout/rollback policy rõ ràng.

**Kết luận:** Trong hệ thống Java runtime extensibility, kiểm tra môi trường phải đi xa hơn việc tìm tên module hay class. Host cần xác minh compiler implementation, scripting provider, module graph và loader thực tế, đồng thời phân biệt chức năng bắt buộc với tùy chọn. Đưa các phép kiểm tra đó vào preflight deployment giúp tránh lỗi muộn và đưa ra trạng thái rõ ràng khi runtime image thiếu thành phần.
