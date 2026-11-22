# Tổng hợp tiêu chí chọn cơ chế mở rộng theo nhu cầu, vận hành và mức độ tin cậy

## 1. Mục tiêu của bài thực hành tổng hợp

“Ứng dụng Java cần hỗ trợ plugin” chưa phải một yêu cầu đủ cụ thể để chọn công nghệ. Có hệ thống chỉ cần chọn một implementation đã biết khi khởi động; có hệ thống nhận JAR mới trong lúc chạy; có hệ thống biên dịch source Java do đối tác gửi; và cũng có hệ thống phải xử lý mã của người dùng **không tin cậy**. Các tình huống ấy yêu cầu kiến trúc khác nhau.

Bài thực hành này xây dựng một **khung ra quyết định** dựa trên ba nhóm tiêu chí:

1. **Nhu cầu nghiệp vụ:** ai phát triển extension, dạng đầu vào nào, thêm/thay lúc nào, có yêu cầu downtime bằng không hay không?
2. **Vận hành và khả năng bảo trì:** vòng đời start/stop, dependency, versioning, rollback, CI/CD, giám sát lỗi, độ trễ và rò rỉ tài nguyên.
3. **Mức độ tin cậy:** plugin có thể tiếp cận dữ liệu nào, hậu quả khi bị lỗi/tấn công là gì, có cần cách ly ở mức hệ điều hành/tiến trình hay không?

Kết quả cần đạt: lựa chọn được một cơ chế hoặc **tổ hợp cơ chế**, giải thích bằng điều kiện bắt buộc và trade-off, triển khai thử bằng Java 17, rồi lập kế hoạch test/rollout/rollback. Bài không mặc định “càng dynamic càng tốt” và không coi một classloader là sandbox bảo mật.

## 2. Bản đồ vai trò: không nhầm discovery, loading, compiling và isolation

Một hệ thống extensibility thường có nhiều tầng độc lập:

~~~text
Nguồn mã mở rộng
    |
    +-- Implementation đã compile ở build/deploy time
    +-- Provider JAR được đưa vào khi chạy
    +-- Source Java cần biên dịch
    +-- Snippet tương tác / script
    +-- Request gửi tới một dịch vụ mở rộng
    |
    v
Khám phá / lựa chọn implementation
    +-- Factory / strategy / DI container / registry
    +-- ServiceLoader / JPMS services
    |
    v
Tạo hoặc nạp code
    +-- Application classpath
    +-- URLClassLoader riêng cho mỗi generation
    +-- JPMS module path / ModuleLayer
    +-- JavaCompiler / JShell / engine ngoài
    |
    v
Thực thi
    +-- Cùng JVM: dùng chung quyền hạn và tài nguyên tiến trình
    +-- Worker JVM riêng: IPC + chính sách OS
    +-- Service riêng: HTTP/gRPC/message transport
    |
    v
Vòng đời và vận hành
    +-- Verify -> Start -> Activate -> Quiesce -> Stop -> Release
    +-- Metrics, tracing, version, health, rollback, cleanup
~~~

**ServiceLoader** giải quyết chủ yếu việc khám phá provider theo service contract. **URLClassLoader** giải quyết nạp lớp/tài nguyên qua URL và cho phép tạo không gian class riêng. **JPMS** quản lý quan hệ đọc module, exports, opens và service binding. **JavaCompiler** biên dịch source thành bytecode. **JShell** cho phép eval snippets Java trong một phiên tương tác. **Process/service boundary** mới có thể tổ chức chính sách quyền, CPU, RAM và khả năng kết thúc một extension hỏng một cách riêng biệt, khi OS được cấu hình đúng.

Vì vậy câu hỏi “nên chọn ServiceLoader hay URLClassLoader?” thường thiếu một tầng: hai công cụ có thể đi cùng nhau. Cụ thể, host có thể dùng `ServiceLoader.load(Plugin.class, loader)` trên một `URLClassLoader` riêng để vừa khám phá provider vừa nạp JAR được đặt vào runtime. Tuy nhiên, kết hợp đó **không tự cung cấp security isolation**.

## 3. Ma trận so sánh các cách mở rộng Java

| Phương án | Tình huống nên xét | Điểm mạnh | Hạn chế chính |
| --- | --- | --- | --- |
| **Strategy / Factory / DI** | Implementation được biết khi build; chỉ cần chọn hành vi theo config | Type-safe, ít moving parts, test và debug đơn giản | Thêm code mới thường phải build/deploy lại |
| **ServiceLoader tại startup** | SPI providers đóng JAR cùng release | Discovery chuẩn JDK, host phụ thuộc interface | Không tự download JAR mới hay xây hot-reload lifecycle |
| **ServiceLoader + URLClassLoader** | Provider JAR tin cậy cần nạp/thay khi đang chạy | Không cần host import implementation, loader theo generation | Dependency identity, thread, registry, shutdown, rollback khó hơn |
| **JPMS / ModuleLayer** | Muốn named modules và requires/exports/uses/provides tường minh | Module readability/encapsulation, service binding | Module graph, layer, exports/opens; không phải sandbox |
| **Reflection + registry** | Lựa chọn class/method có kiểm soát khi runtime | Linh hoạt, không cần biết implementation tại compile-time | Lỗi runtime/access/signature; không tự tìm provider hoặc bảo vệ host |
| **JavaCompiler API** | Nhận source Java đã được phép compile động | Compile Java, dùng diagnostics, classpath, module path, --release | Phải quản compiler, dependencies, output, annotation processors; không sandbox |
| **JShell API** | REPL, công cụ học tập, console Java snippet | Tốt cho một phiên tương tác, quản lý snippet state | Không phải deployment manager; eval có tác dụng phụ, không sandbox |
| **ScriptEngine JSR 223** | Scripting khi có engine đóng gói và governance | API chung cho engine được cài | JDK 17 không bảo đảm có JavaScript engine; Nashorn không còn đi kèm JDK |
| **Worker JVM/process riêng** | Cần hạn chế blast radius, quyền OS, tài nguyên hoặc kill độc lập | Có thể quota/restart/kill, version runtime riêng | IPC, latency, logging đa process, OS policy, deploy phức tạp hơn |
| **Service ngoài tiến trình** | Đối tác đa ngôn ngữ, triển khai/scale độc lập | Giao thức versioned, tách vòng đời, triển khai riêng | Network latency, auth, timeout, retry, consistency, version schema |

Chọn theo **vai trò cần giải quyết**, không nhất thiết ép một phương án làm mọi việc. Ví dụ: extension do người dùng cung cấp Java source có thể dùng `JavaCompiler` trong worker process; worker sau đó nạp bytecode đã compile. Nhưng nếu chỉ cần đổi từ formatter A sang B vốn đã có sẵn trong host, factory/DI là đủ.

## 4. Hỏi rõ yêu cầu trước khi so sánh công nghệ

Một workshop lựa chọn kiến trúc có thể dùng bộ câu hỏi sau:

| Nhóm | Câu hỏi cần trả lời bằng dữ liệu |
| --- | --- |
| Người cung cấp extension | Đội nội bộ, đối tác đã ký hợp đồng, admin hay người dùng không tin cậy? |
| Định dạng đầu vào | Class/JAR, named module, source Java, snippet, script hoặc API request? |
| Tần suất thay | Hàng quý, hàng tuần, vài lần/ngày, hay theo yêu cầu từng request? |
| Downtime | Có được restart JVM? Có yêu cầu zero-downtime/hot swap? |
| Compatibility | Plugin API version, JDK release, schema, ABI, dependency version được pin ra sao? |
| Quyền truy cập | Extension có được mở file, network, subprocess, truy cập secret hoặc DB không? |
| Failure containment | Một plugin treo/crash có được phép làm chậm hoặc dừng host không? |
| Hiệu năng | Latency p50/p95/p99, throughput, startup/reload time, RAM/metaspace budget? |
| Vận hành | Ai phát hành/review artifact, rollback, monitor, dừng tác vụ, cleanup tài nguyên? |
| Quan sát | Có log plugin ID/version, loader generation, CodeSource, module, trace ID? |
| Tính di động | Có cần plugin đa ngôn ngữ hoặc runtime khác nhau không? |
| Chất lượng | Test compatibility, negative tests, memory leak, concurrent hot swap? |

**Đừng trả lời “đáng tin” bằng cảm giác.** Tin cậy là thuộc tính của nguồn, quy trình xác minh artifact, quyền được cấp và khả năng giới hạn hậu quả. Plugin từ đối tác “có hợp đồng” nhưng được phép thực thi arbitrary bytecode vẫn có thể gây lỗi hoặc làm gián đoạn host; mức độ rủi ro thực tế phải được đánh giá.

## 5. Hard gates: loại trừ trước khi chấm điểm

### Gate 1 — Mã không tin cậy và blast radius

Nếu extension có thể thực thi code Java tùy ý do người dùng không tin cậy cung cấp, mà host chứa dữ liệu riêng tư hoặc không được phép bị crash/treo, thì `URLClassLoader`, JPMS, reflection, `JavaCompiler` và `JShell` **không phải sandbox**. Chúng chạy trong JVM hoặc điều phối code có tác dụng phụ, không tạo ranh giới quyền OS an toàn.

Kiến trúc cần cân nhắc worker process/container riêng, danh tính chạy có quyền tối thiểu, giới hạn CPU/RAM/PID/disk, filesystem isolation, network policy, hạn chế secret, timeout, hủy task và kill process tree. Một process riêng nhưng chạy với cùng quyền ghi file/network không hạn chế **chưa đủ** để coi là an toàn.

### Gate 2 — Bắt buộc có thể kết thúc công việc bị treo

Nếu host phải dừng một extension không hợp tác mà không ảnh hưởng tới các plugin khác, không thể chỉ trông chờ `Thread.interrupt()` hoặc `URLClassLoader.close()` trong cùng JVM. Interrupt có tính hợp tác; loader close không dừng thread và không hủy các class đã nạp. Với yêu cầu hard kill đáng tin, ưu tiên process boundary và chính sách OS.

### Gate 3 — Chính sách phát hành không cho tự nạp code khi chạy

Nhiều tổ chức chỉ cho phép artifact đã qua CI/CD, approval và release window. Nếu không có quy trình phê duyệt runtime load, việc thiết kế hot reload phức tạp có thể **trái chính sách**. Khi đó startup `ServiceLoader` hoặc factory/DI thường phù hợp hơn.

### Gate 4 — Toolchain và định dạng đầu vào

`JavaCompiler` cần system compiler phù hợp; `ToolProvider.getSystemJavaCompiler()` có thể là `null` nếu runtime image không có compiler. `JShell` cần module `jdk.jshell` trong runtime và phù hợp cho snippet, không phải thay thế tổng quát cho compiler của nguyên project. `ScriptEngine` còn phụ thuộc engine thực tế đã cài; **không** giả định JDK 17 tự cung cấp Nashorn.

### Gate 5 — Ranh giới API và khả năng tương thích

Nếu host cast plugin sang một interface, host và implementation phải thống nhất **class identity** của API. Hai class cùng tên `demo.api.Plugin` do hai defining loaders khác nhau định nghĩa không tương đương. Với in-process plugin, thiết kế SPI/API chung nằm ở parent hoặc module phù hợp. Với IPC, schema/giao thức phải versioned và kiểm thử tương thích.

Nếu một phương án vi phạm hard gate, **loại nó trước**; không lấy throughput hoặc điểm phát triển cao để bù lỗ hổng bảo mật hay việc không thể đáp ứng SLA dừng job.

## 6. Cây quyết định nhanh

~~~text
Có chạy code không tin cậy hoặc cần blast-radius/kill isolation?
  |
  +-- CÓ --> Worker process/container hoặc service riêng
  |           + OS policy, quota, auth, IPC, health/restart
  |
  +-- KHÔNG --> Input là Java snippet tương tác?
                 |
                 +-- CÓ --> JShell (trong phạm vi được phép)
                 |
                 +-- KHÔNG --> Input là source Java cần compile ở runtime?
                                |
                                +-- CÓ --> JavaCompiler (trusted context)
                                |          + output + loader/module layer
                                |
                                +-- KHÔNG --> Đã có implementation ở build time?
                                               |
                                               +-- CÓ --> Strategy/DI/factory
                                               |          hoặc ServiceLoader startup
                                               |
                                               +-- KHÔNG --> Provider JAR được duyệt?
                                                              |
                                                              +-- KHÔNG --> Thiết kế/duyệt SPI
                                                              |
                                                              +-- CÓ --> Có yêu cầu nạp/thay
                                                                         khi JVM đang chạy?
                                                                       |
                                                                       +-- KHÔNG --> Startup SPI
                                                                       |
                                                                       +-- CÓ --> URLClassLoader
                                                                                  + ServiceLoader
                                                                                  + lifecycle
~~~

Nếu extension là named module và cần JPMS contracts, thay classpath loader bằng module path/layer có chủ đích. Với multi-language hoặc nhu cầu triển khai độc lập, service API có thể tốt hơn cả classloader. Cây quyết định không thay thế risk review; nó giúp nhanh chóng loại các phương án sai tầng.

## 7. Chấm điểm có trọng số sau khi qua hard gates

Để so sánh những phương án đủ điều kiện, chọn trọng số phù hợp và chấm 1–5 (5 tốt nhất). Một bộ trọng số **minh họa**:

| Tiêu chí | Trọng số |
| --- | ---: |
| Phù hợp nhu cầu reload/vòng đời | 25% |
| Chi phí vận hành, rollout, rollback | 20% |
| Compatibility và quản lý dependency | 20% |
| Latency, throughput và tài nguyên | 15% |
| Chẩn đoán, giám sát, kiểm thử | 10% |
| Độ phức tạp phát triển/bảo trì | 10% |
| **Tổng** | **100%** |

Công thức:

~~~text
weighted_score = SUM(weight_percent_i * rating_i) / 100

rating_i từ 1 tới 5.
Nếu fail hard gate thì loại phương án, không xét weighted_score.
~~~

Với tình huống **provider JAR đã duyệt, cần thay khi JVM đang chạy**, có thể chấm như sau. Điểm chỉ là giả định workshop, không phải benchmark:

| Phương án | Reload 25 | Ops 20 | Compatibility 20 | Performance 15 | Diagnosis 10 | Simplicity 10 | Điểm / 5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ServiceLoader startup/restart | 1 | 5 | 4 | 5 | 4 | 5 | **3,70** |
| ServiceLoader + URLClassLoader theo generation | 5 | 3 | 4 | 4 | 4 | 3 | **3,95** |
| Worker process riêng | 5 | 2 | 4 | 2 | 5 | 2 | **3,45** |

Kiểm tra công thức của phương án giữa:

~~~text
(25*5 + 20*3 + 20*4 + 15*4 + 10*4 + 10*3) / 100
= (125 + 60 + 80 + 60 + 40 + 30) / 100
= 395 / 100
= 3.95
~~~

Với startup SPI: `(25 + 100 + 80 + 75 + 40 + 50)/100 = 3,70`. Với worker process: `(125 + 40 + 80 + 30 + 50 + 20)/100 = 3,45`. Điểm số được tính nhất quán theo cùng trọng số.

**Ý nghĩa:** trong giả định này, dynamic SPI được đánh giá cao nhất về tổng điểm. Nhưng nếu restart là hành vi **không được phép**, startup SPI đã trượt hard gate về lifecycle; nếu mã không tin cậy và cần cách ly thì dynamic SPI trượt hard gate bảo mật, dù điểm số lớn hơn. Hãy kiểm chứng rating bằng benchmark và vận hành thử, không xem số 3,95 là chân lý.

## 8. Các tổ hợp kiến trúc hay dùng

### 8.1. Mã nội bộ ổn định: Factory, DI hoặc startup SPI

Nếu đội sản phẩm sở hữu toàn bộ implementations và release theo chu kỳ, một interface nhỏ với factory hoặc dependency injection thường đủ. Nếu muốn các thư viện tự công bố implementation mà host không import concrete classes, `ServiceLoader` ở startup là phù hợp. Không cần tự tạo loader generation, không phải có `JavaCompiler`.

Điểm mạnh: giảm rủi ro rò rỉ classloader, vận hành qua CI/CD chuẩn. Điểm yếu: thêm provider mới thường gắn với release/restart của host. Đây có thể là trade-off rất tốt nếu hot reload không phải yêu cầu thật.

### 8.2. JAR tin cậy, cần tải và cập nhật trong cùng JVM

Chọn **API/SPI dùng chung**, loader riêng theo generation và `ServiceLoader` để discovery. Định nghĩa contract `Plugin.id()/start()/stop()/close()` hoặc registration handle phù hợp; giữ mapping ID/version/generation → artifact/loader/instance.

Plugin manager phải đảm bảo: xác minh artifact trước load; chỉ chuyển routing khi candidate health tốt; không nhận call mới trên phiên cũ; đợi các call đang chạy; dừng executor/listener/scheduler; khôi phục TCCL và dọn ThreadLocal ở đúng thread; đóng loader, bỏ cache/registry references.

**`URLClassLoader.close()` không hủy class đã nạp.** Instance cũ vẫn có thể được gọi nếu host giữ reference. Phải chặn gọi theo trạng thái lifecycle, không trông chờ việc loader đóng sẽ tự vô hiệu hóa code.

### 8.3. Named modules và JPMS

Nếu module descriptor, `requires`, `exports`, `opens`, `uses/provides` có giá trị thật cho kiểm soát dependency và encapsulation, cân nhắc named modules/module layers. Không đặt mọi JAR lên module path chỉ để cảm thấy “mới hơn”. Named module không phải ranh giới bảo mật ở mức process; lifecycle của layer/class vẫn phụ thuộc tham chiếu và GC.

### 8.4. Source Java do người được phép cung cấp

`JavaCompiler` nhận các options như `--class-path`, `--module-path`, `-d`, `--release 17` để tạo bytecode. Biên dịch vào directory riêng, thu diagnostics, kiểm soát annotation processing và library versions, xác minh output trước khi nạp. Nếu source đến từ người dùng không tin cậy, chuyển cả quá trình compile và run sang worker được cô lập thích hợp.

### 8.5. Console/snippet hoặc script

`JShell` phù hợp cho Java snippets tương tác: dùng `SourceCodeAnalysis.analyzeCompletion` để tách snippet hoàn chỉnh trước `eval`; đóng session khi xong. Với scripting khác, JSR 223 chỉ là facade; cần engine thực tế và policy chạy code. Cả hai đều có thể thực thi mã có tác dụng phụ nếu chạy dưới quyền tiến trình, nên không dùng làm sandbox.

### 8.6. Process/service extension

Khi cần blast-radius, quyền hạn hoặc khả năng restart/scale riêng, chọn worker process hoặc dịch vụ ngoài JVM. Cần định nghĩa IPC schema, authentication, timeouts, retries, backpressure, idempotency, health checks, process limits và observability. Chi phí thêm là latency và hạ tầng; lợi ích là khả năng cách ly/triển khai độc lập được kiểm soát theo OS policy.

## 9. Bài thực hành Java 17: SPI discovery qua loader riêng

Ta sẽ triển khai **provider JAR đã được tin cậy** với `ServiceLoader` + `URLClassLoader`. Đây là bước tối thiểu để thấy sự kết hợp giữa API contract, discovery và loader generation. Ví dụ không pretend cung cấp sandbox hay đầy đủ hot reload, vì vòng đời thật cần nhiều thành phần hơn.

### 9.1. Cấu trúc dự án

Tạo các file sau trong thư mục `plugin-choice-demo`:

~~~text
plugin-choice-demo/
  src/
    api/demo/api/Formatter.java
    provider/demo/provider/UppercaseFormatter.java
    provider-resources/META-INF/services/demo.api.Formatter
    host/demo/host/HostApp.java
  build/                        (được tạo bởi lệnh biên dịch)
~~~

**File `src/api/demo/api/Formatter.java`:**

~~~java
package demo.api;

public interface Formatter {
    String id();
    String format(String input);
}
~~~

Đây là SPI mà host và provider cùng tham chiếu. Class của API sẽ được nạp từ **parent/application loader**; implementation plugin không được định nghĩa bản API riêng theo child loader.

**File `src/provider/demo/provider/UppercaseFormatter.java`:**

~~~java
package demo.provider;

import demo.api.Formatter;
import java.util.Locale;

public final class UppercaseFormatter implements Formatter {
    public UppercaseFormatter() {
    }

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

Provider có public zero-argument constructor phù hợp với SPI trên classpath. Với JPMS named module, một provider còn có thể được khai báo bằng `provides ... with ...`; demo này chủ động dùng metadata classpath.

**File `src/provider-resources/META-INF/services/demo.api.Formatter`:**

~~~text
demo.provider.UppercaseFormatter
~~~

Tên **file descriptor** là fully qualified name của interface (`demo.api.Formatter`). Nội dung là fully qualified name của implementation, không thêm dấu `.class` hay JSON. Nếu descriptor không được đóng gói đúng đường dẫn, `ServiceLoader` không tự tìm thấy implementation này.

**File `src/host/demo/host/HostApp.java`:**

~~~java
package demo.host;

import demo.api.Formatter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/provider.jar");
        if (!Files.isRegularFile(jar)) {
            throw new IllegalStateException("Missing provider JAR");
        }

        ClassLoader parent = HostApp.class.getClassLoader();
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(
                "formatter-generation-1", urls, parent)) {

            ServiceLoader<Formatter> providers =
                    ServiceLoader.load(Formatter.class, loader);

            int count = 0;
            for (Formatter formatter : providers) {
                if (!"uppercase".equals(formatter.id())) {
                    continue;
                }

                count++;
                System.out.println("provider=" + formatter.id());
                System.out.println(
                        "result=" + formatter.format("hello plugin"));
                System.out.println("loader="
                        + formatter.getClass().getClassLoader().getName());
            }

            if (count != 1) {
                throw new IllegalStateException(
                        "Expected one uppercase provider; found " + count);
            }
        }
    }
}
~~~

**Giải thích:**

1. Host không import `demo.provider.UppercaseFormatter`. Nó chỉ biết SPI `Formatter`.
2. `URLClassLoader` có URL trỏ vào provider JAR và tên generation. Parent là loader của host, chứa API chung.
3. `ServiceLoader.load(Formatter.class, loader)` tìm SPI descriptor trong JAR rồi tạo provider. Không phải host tự dùng reflection để đoán tên implementation.
4. Khi provider được tạo từ child loader, `getClass().getClassLoader().getName()` trả tên loader đã được đặt trong demo.
5. Try-with-resources đóng loader khi host xong. Nếu provider có task nền/stream/listener, cần dừng chúng **trước** khi close loader trong một plugin manager thực tế.
6. Descriptor sai hoặc provider không có constructor phù hợp có thể dẫn đến `ServiceConfigurationError`; host cần log nguyên nhân, không nuốt lỗi và im lặng dùng implementation khác.

### 9.2. Compile và chạy

Tại thư mục `plugin-choice-demo`, với JDK 17+ và Bash:

~~~bash
mkdir -p build/api build/provider build/host

javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Formatter.java
jar --create --file build/api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/api.jar -d build/provider \
  src/provider/demo/provider/UppercaseFormatter.java

jar --create --file build/provider.jar \
  -C build/provider . \
  -C src/provider-resources META-INF/services/demo.api.Formatter

javac --release 17 -encoding UTF-8 \
  -cp build/api.jar -d build/host \
  src/host/demo/host/HostApp.java

# Provider JAR không được thêm vào application classpath.
java -cp "build/host:build/api.jar" demo.host.HostApp
~~~

**Stdout chính xác** nếu đóng gói đúng:

~~~text
provider=uppercase
result=HELLO PLUGIN
loader=formatter-generation-1
~~~

Trên Windows PowerShell, lệnh chạy dùng dấu chấm phẩy:

~~~powershell
java -cp "build/host;build/api.jar" demo.host.HostApp
~~~

Các lệnh Bash nhiều dòng dùng `` để nối dòng. Trên PowerShell, viết các lệnh `javac`/`jar` thành một dòng hoặc theo cú pháp nối dòng riêng.

Để kiểm tra kết quả đóng gói:

~~~bash
jar --list --file build/provider.jar
~~~

Trong JAR phải có `demo/provider/UppercaseFormatter.class` và `META-INF/services/demo.api.Formatter`. Không đặt `build/provider.jar` vào classpath của host vì parent có thể nạp implementation trước, làm hỏng thí nghiệm về loader generation.

### 9.3. Năm thử nghiệm có chủ đích

**Thử nghiệm A — Bỏ SPI descriptor:** Đóng gói JAR chỉ chứa class implementation. `ServiceLoader` sẽ không tìm provider theo descriptor đã thiếu; host báo rằng không tìm thấy đúng một provider. Điều này xác nhận discovery không đồng nhất với “có class trong JAR”.

**Thử nghiệm B — Sửa tên provider thành class không tồn tại:** Trỏ descriptor tới một class giả. Khi iterator tải provider, JShell không liên quan; `ServiceLoader` sẽ báo lỗi cấu hình (`ServiceConfigurationError`) thay vì “tự đoán” class.

**Thử nghiệm C — Tách parent/child:** Thêm provider JAR vào application classpath rồi quan sát `getClassLoader().getName()`. Parent delegation có thể khiến implementation được định nghĩa bởi parent; log sẽ không còn là generation của child như kỳ vọng. Điều này cho thấy deployment classpath ảnh hưởng identity.

**Thử nghiệm D — Tạo generation 2:** Dùng một provider JAR thứ hai có cùng binary class name nhưng mã khác, tạo một `URLClassLoader` mới với tên generation 2. Giữ API chung ở parent và chứng minh hai `Class<?>` có thể có defining loaders khác nhau. Không cố “unload” bằng cách chỉ gọi `close()` rồi giữ callback cũ.

**Thử nghiệm E — Stop đang có invocation:** Thêm provider task chạy chậm và gọi stop đồng thời. Host cần ngăn invocation mới, chờ in-flight work xong/cancel có timeout, rồi mới đóng loader. Test này quan trọng hơn chỉ chứng minh demo cơ bản in ra stdout.

## 10. Từ ví dụ thành plugin manager có lifecycle

Một plugin manager có thể dùng trạng thái:

~~~text
DISCOVERED -> VERIFIED -> PREPARED -> ACTIVE
                                   |
                                   v
                                QUIESCING -> STOPPED -> RELEASED
                    [failure được cleanup và báo rõ theo stage]
~~~

Đây là state machine **do ứng dụng thiết kế**, không phải tính năng tự có của `ServiceLoader` hoặc `URLClassLoader`.

- **DISCOVER:** phát hiện artifact, đọc plugin descriptor và capability, xác định API version.
- **VERIFY:** xác minh hash/signature, nguồn phát hành, dependency allowlist và policy trust. Nếu mã không tin cậy, định tuyến sang execution boundary phù hợp.
- **PREPARE:** tạo loader/module layer/worker, nạp class, instantiation, validate contract, start provider và health check. Nếu lỗi, dọn candidate.
- **ACTIVE:** publish routing, ghi plugin ID/version/generation, cấp context theo request, đo latency và error rate.
- **QUIESCING:** chặn request mới, theo dõi in-flight requests, đợi hoặc cancel theo policy; dừng scheduler/task nền.
- **STOPPED:** gọi lifecycle hooks, hủy listener/event bus registration, dừng executor/connection, cleanup ThreadLocal/TCCL trên đúng thread.
- **RELEASED:** đóng stream/JAR/loader (hoặc worker), loại cache/provider references và registry generation cũ. Không tuyên bố “classes unloaded” nếu chưa có bằng chứng JVM.

### Đổi version không đồng nghĩa thay file JAR tại chỗ

Nên dùng tên/path artifact bất biến: ID + version + digest hoặc build ID. Khi đưa v2 vào, không ghi đè JAR v1 đang được loader sử dụng. Kiểm tra v2 trong trạng thái chuẩn bị, chuyển routing có đồng bộ, giữ đường rollback đã kiểm tra và chỉ dọn v1 sau khi không còn in-flight calls.

Nếu v2 không khởi tạo/health check được, đóng candidate v2 và giữ v1 đang phục vụ (nếu chính sách cho phép). Nếu đã cutover mà v2 lỗi, có thể rollback routing sang một generation còn hợp lệ hoặc tạo instance mới của version đã duyệt; đừng cố tái sử dụng loader đã đóng.

### Observability cho plugin

Ít nhất các event `plugin.discovered`, `plugin.verified`, `plugin.loaded`, `plugin.activated`, `plugin.invocation.failed`, `plugin.deactivated` và `plugin.released` nên mang plugin ID/version, artifact digest, deployment generation, loader identity/CodeSource và module khi thích hợp. Nối invocation với request/trace ID.

Ghi metadata theo lifecycle để tránh đọc reflection lặp lại trong đường nóng. Snapshot chỉ nên chứa dữ liệu thuần và được bỏ khi stop; một singleton cache chứa `Class<?>` hoặc `ClassLoader` có thể vô tình giữ loader cũ sống.

## 11. Tình huống lựa chọn có đáp án và tiêu chí kiểm chứng

### 11.1. Formatter nội bộ, chỉ thay qua release window

Một ứng dụng có ba formatter cố định, do đội nội bộ viết, release hàng tháng; đổi formatter theo tenant qua config, không cần nạp code mới khi chạy.

**Chọn:** Strategy/DI hoặc startup SPI. Không cần JavaCompiler/JShell, không bắt buộc dynamic loader. **Điểm kiểm chứng:** unit test mỗi implementation, integration test API contract, đổi config không sửa source, rollback qua release đã phê duyệt.

### 11.2. JAR plugin của đối tác được duyệt, hot reload không restart

Đối tác cung cấp JAR được ký và xét dependency, host yêu cầu thay version trong cùng JVM mà request đang xử lý không bị mất.

**Chọn:** API chung + `ServiceLoader` + loader riêng theo generation, hoặc ModuleLayer nếu named modules có lợi ích rõ ràng. **Điểm kiểm chứng:** tải/validate v2, route request mới sang v2, cho v1 quiesce, stop task/listener, close loader, kiểm tra không giữ loader cũ qua nhiều chu kỳ; rollback không ghi đè JAR.

### 11.3. Trang web cho người dùng bất kỳ chạy Java source

Host chứa dữ liệu khách hàng; người dùng có thể gửi code vô hạn vòng lặp, file/network operations và gây exception.

**Chọn:** build/run trong worker process có hạn chế OS. JavaCompiler có thể được dùng bên trong worker, nhưng **không** đưa mã không tin cậy vào JVM host chỉ vì compiler và JShell có sẵn. **Điểm kiểm chứng:** timeout và kill process tree; giới hạn CPU/RAM/disk; thử truy cập file/network trái phép bị chặn; worker crash không làm host crash; audit/quota theo tenant.

### 11.4. Console Java nội bộ cho kỹ sư vận hành

Nhu cầu là chạy snippet Java ngắn theo phiên, với code đã được phê duyệt và chính sách truy cập phù hợp.

**Chọn:** JShell API, phân tích đầu vào bằng `SourceCodeAnalysis.analyzeCompletion` trước `eval`. Nếu console có tác động mạnh và phải hỗ trợ người dùng chưa tin cậy, vẫn cần execution isolation. **Điểm kiểm chứng:** snippet đa dòng, diagnostics, session cleanup, timeout/quyền truy cập và log audit.

### 11.5. Hai plugin có dependency xung đột

Hai plugin cần phiên bản khác nhau của thư viện, nhưng host API phải thống nhất class identity.

**Chọn:** loader graph có chủ đích hoặc module layers nếu packaging JPMS thực sự cần. Giữ API chung trong parent/layer thích hợp. **Điểm kiểm chứng:** không duplicate API class, không `ClassCastException`, version dependencies đúng, unload/stop không để lại task hoặc static cache ở host.

### 11.6. Extension đa ngôn ngữ và triển khai độc lập

Đối tác viết bằng Java, Go và Python, cần scale riêng và cập nhật theo lịch khác host.

**Chọn:** service extension qua API/gRPC/message, kèm schema versioning, authentication, retries/timeouts, idempotency và tracing. **Điểm kiểm chứng:** p95/p99 đạt SLA, partial outage không làm host treo, rolling deployment giữ backward compatibility, secrets/network segmentation đúng.

## 12. Bẫy kỹ thuật hay gặp

| Cách hiểu sai | Hệ quả | Hướng đúng |
| --- | --- | --- |
| “ServiceLoader tự nạp JAR mới từ bất kỳ đường dẫn nào” | Không tìm thấy provider | Cấu hình classpath/loader/module layer và SPI descriptor |
| “URLClassLoader.close() là unload plugin” | Instance/thread/listener cũ vẫn sống | Quiesce, stop, unregister, close, drop references |
| “JPMS là sandbox quyền truy cập hệ điều hành” | Plugin vẫn có quyền tiến trình | Dùng OS/process isolation theo threat model |
| “Đặt source vào JavaCompiler là an toàn” | Annotation processor/source/bytecode có thể gây tác dụng phụ | Quản toolchain và chạy trong worker nếu không tin cậy |
| “JShell.eval là trình biên dịch cả project” | Snippet/file boundary và trạng thái phiên bị xử lý sai | Dùng SourceCodeAnalysis/Compiler API theo mục đích |
| “JDK 17 chắc có JavaScript engine” | Không tìm thấy ScriptEngine | Kiểm tra/cài engine riêng, pin version và policy |
| “Tách process là đủ sandbox” | Cùng quyền file/network/secrets vẫn nguy hiểm | Least privilege, quota, filesystem/network isolation |
| “Score cao có thể bù security fail” | Vi phạm yêu cầu bắt buộc | Hard gates trước, weighted score sau |
| “Chỉ lưu class name là đủ chẩn đoán” | Không phân biệt v1/v2, parent delegation | Ghi ID/version/generation, CodeSource, defining loader |
| “Hot reload chỉ cần thay registry pointer” | Listener, ThreadLocal, executor v1 vẫn chạy | Quản in-flight calls, stop và cleanup |
| “System.gc() chứng minh unload” | Test flaky, kết luận rò rỉ sai | Theo dõi GC roots, JFR/thread/heap qua nhiều chu kỳ |
| “Đổi tên JAR khi loader đang dùng luôn ổn” | File handle và OS behavior khác nhau | Artifact bất biến, xử lý file theo lifecycle |

## 13. Kế hoạch đo và kiểm thử vận hành

Một phương án có điểm lý thuyết tốt chưa đủ để dùng production. Trước khi chốt, cần đánh giá trên workload gần thực tế:

1. **Latency/throughput:** đo p50/p95/p99, warm-up, throughput ở số plugin dự kiến, tail latency khi hot reload.
2. **Startup/reload:** discover, verify, build/load, health check, cutover, quiesce và stop mất bao lâu?
3. **Memory:** heap, metaspace, số live loaders, threads, file descriptors/JAR handles qua nhiều vòng reload.
4. **Failure containment:** plugin ném exception, deadlock, infinite loop, mất mạng, OOM/worker crash ảnh hưởng host thế nào?
5. **Compatibility:** đổi API method, module exports/opens, dependency version, schema của IPC; có phát hiện lỗi trước activation không?
6. **Rollback:** v2 lỗi trong prepare, lỗi sau cutover, lỗi cleanup v1; có đường trở về artifact đã duyệt và không mất request không?
7. **Trust boundary:** mã không tin cậy có truy cập file ngoài vùng cho phép, egress network, secret, process/host resource không?
8. **Khả năng hỗ trợ:** có đủ ID/version/generation, CodeSource/loader/module, correlation ID, diagnostics và metrics để truy nguyên không?
9. **Giới hạn vận hành:** quy mô job song song, tốc độ phát hành, ngân sách log/storage và khả năng phân phối artifact.
10. **Chất lượng developer workflow:** thêm provider mới có ít bước, test chạy độc lập và có template/validation rõ không?

Đừng đánh giá chỉ từ một vòng GC hoặc một lần đo p50. Tính ổn định và khả năng cleanup cần kiểm chứng bằng nhiều chu kỳ start/stop, có concurrency và đường lỗi.

## 14. Mẫu Architecture Decision Record (ADR) để nộp bài

~~~text
Title: Chọn cơ chế mở rộng Java cho hệ thống ...

Context:
  - Người cung cấp code, định dạng extension
  - Nhu cầu thay lúc build/start/runtime
  - Trust classification và blast radius
  - JDK, dependency và API compatibility
  - SLA / availability / operational constraints

Hard gates:
  - Security and isolation
  - Stop/kill guarantees
  - Release governance
  - Toolchain/runtime availability
  - API/IPC contract compatibility

Options:
  - Strategy/ServiceLoader
  - Dynamic loader/ModuleLayer
  - Compiler/JShell
  - Worker/service boundary

Evaluation:
  - Trọng số + điểm + bằng chứng benchmark
  - Phương án bị loại bởi hard gate

Decision:
  - Tổ hợp được chọn
  - Vì sao phù hợp yêu cầu và trade-offs còn lại

Lifecycle:
  - Verify -> Prepare -> Activate -> Quiesce -> Stop -> Release
  - Rollback và cleanup failure handling

Evidence:
  - Source/demo/test, stdout, latency, memory, security tests
  - Observability, audit, artifact provenance

Review triggers:
  - Nguồn code thay đổi mức tin cậy
  - Tần suất reload, SLA hoặc ngôn ngữ plugin thay đổi
  - Incident/leak/compatibility breach
~~~

### Bài tập và yêu cầu nghiệm thu

**Bài tập A:** Với ba formatter nội bộ release theo CI/CD, chọn factory/DI hay startup SPI. Nêu lý do **không** dùng hot reload, test thay config và quy trình rollback.

**Bài tập B:** Với provider JAR tin cậy cần reload, mở rộng ví dụ mục 9: dùng v1/v2 JAR khác nhau, mỗi version một loader name/generation. Ghi CodeSource/defining loader của implementation; test hủy listener/task cũ và stop khi in-flight calls còn chạy.

**Bài tập C:** Với source Java không tin cậy từ người dùng web, nêu ít nhất sáu hard requirements cho worker: OS identity, CPU/memory/time, process kill, filesystem/network, secrets và audit/quotas. Trình bày threat model và kiểm thử negative paths.

**Bài tập D:** Chọn ba phương án đã vượt hard gates, đặt trọng số và điểm, tính bảng điểm đúng số học, đính kèm benchmark. Giải thích vì sao score không thay thế policy hoặc vận hành thực tế.

**Bài tập E:** Một request vẫn trả kết quả v1 sau khi routing sang v2. Nêu giả thuyết parent delegation, cached provider, listener cũ, ThreadLocal/TCCL hoặc in-flight request; thiết kế các trường log để loại trừ từng giả thuyết.

## 15. Rubric và checklist hoàn thành

| Hạng mục | Điểm gợi ý | Tiêu chí |
| --- | ---: | --- |
| Phân tích yêu cầu/trust và hard gates | 25 | Không dùng in-process như sandbox khi cần isolation |
| Phân biệt chính xác vai trò cơ chế | 20 | Hiểu discovery, loader, compiler, JPMS, IPC |
| Quyết định có ma trận và lý do | 20 | Điểm số đúng, trade-off và điều kiện loại trừ rõ |
| Java 17 demo, stdout, negative tests | 15 | SPI descriptor, provider JAR, loader riêng, kết quả tái lập |
| Lifecycle, rollout/rollback/observability | 15 | Generation, quiesce, stop, metrics và cleanup |
| Trình bày và tính tái lập | 5 | Cấu trúc, commands, giả định và giới hạn rõ |
| **Tổng** | **100** | |

Checklist cuối:

- [ ] Nhu cầu thật sự có cần thêm bytecode mới khi JVM đang chạy, hay chỉ đổi strategy có sẵn?
- [ ] Nguồn code đã được phân loại tin cậy và có artifact verification policy?
- [ ] Hard gates về security, stop/kill, release governance và API contract đã áp dụng?
- [ ] Không nhầm `ServiceLoader` với classloader, `JavaCompiler` với execution sandbox, JPMS với quyền OS?
- [ ] Có versioned API/IPC schema, dependency policy, artifact digest và rollback?
- [ ] Có loader/worker generation và đủ event logs để chẩn đoán class identity, CodeSource/module?
- [ ] Có quiesce/stop/cleanup cho executor, listener, ThreadLocal, TCCL và file resources?
- [ ] Có performance, soak, failure-injection, compatibility và security tests?
- [ ] Bảng điểm tính đúng và có bằng chứng benchmark thay vì số ước đoán?
- [ ] Quyết định ghi thành ADR và có điều kiện xem xét lại khi yêu cầu thay đổi?

**Kết luận:** Cơ chế mở rộng phù hợp là cơ chế giải quyết **đúng tầng nhu cầu**, đạt hard gates về tin cậy và vận hành, rồi mới tối ưu hiệu năng/độ phức tạp. Với plugin Java tin cậy cần reload, SPI + loader riêng thường là tổ hợp có ích; với source Java cần compile dùng JavaCompiler; với snippet tương tác dùng JShell; với mã không tin cậy hoặc cần cách ly lỗi mạnh, dùng ranh giới process/service cùng chính sách OS. Một kiến trúc chỉ thực sự hoàn chỉnh khi có versioning, lifecycle, rollback, observability và kiểm thử có thể tái lập.
