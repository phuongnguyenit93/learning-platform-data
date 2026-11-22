# Agent JAR độc lập, executable JAR và class path hoặc module path của ứng dụng

Một Java agent không nhất thiết là một phần của file JAR chứa ứng dụng. Khi triển khai **Java Instrumentation**, bạn thường có **agent JAR độc lập** được JVM nạp bằng `-javaagent`, đồng thời ứng dụng chạy bằng một trong ba cách: **executable JAR** (`java -jar`), **class path** (`java -cp`) hoặc **module path** (`java --module-path ... --module ...`). Ba cách khởi chạy ứng dụng có cơ chế tìm lớp/phụ thuộc khác nhau, nhưng đều có thể dùng cùng một agent JAR độc lập.

Chủ đề của bài này là **Đóng gói và triển khai**: phân biệt các loại JAR, mục đích manifest, vị trí mà JVM tìm mã của agent và ứng dụng, khác biệt của Java Platform Module System (JPMS), cách đóng gói thư viện đi kèm, cách chạy thực tế và cách chẩn đoán các lỗi thường gặp. Ví dụ hoàn chỉnh bên dưới được biên dịch với **`javac --release 17`**, chạy trên **JDK 24** và đã xác minh ở **cả ba chế độ**.

> **Nguyên tắc đầu tiên:** `-javaagent:agent.jar` chỉ định JAR chứa **agent startup entrypoint**; `-jar app.jar` chỉ định JAR chứa **application main entrypoint**. Chúng là hai tùy chọn khác nhau của cùng một câu lệnh `java`. Agent JAR không tự trở thành executable application JAR chỉ vì có `Premain-Class`; ứng dụng không tự trở thành agent chỉ vì có `Main-Class`.

## 1. Bốn khái niệm cần phân biệt trước khi đóng gói

| Khái niệm | Chứa gì? | Cơ chế khởi chạy/resolve |
| --- | --- | --- |
| **Agent JAR độc lập** | Agent class có `premain`, `ClassFileTransformer` và helper cần thiết | `-javaagent:path/to/agent.jar[=options]`; manifest `Premain-Class` |
| **Executable application JAR** | Ứng dụng với một `public static void main(String[])` và manifest `Main-Class` | `java -jar app.jar` |
| **Class path** | Danh sách thư mục/JAR để application class loader tìm class và resource | `-cp`/`--class-path`; code chạy trong *unnamed module* nếu thuộc class path |
| **Module path** | Danh sách module artifacts/directory cho JPMS resolve module graph | `--module-path`/`-p` cùng `--module`/`-m`; explicit modules qua `module-info.class` |

Một file JAR là **định dạng lưu trữ**; việc trở thành agent, executable app, explicit module hay library phụ thuộc **metadata và cách launcher sử dụng nó**, không chỉ phần mở rộng `.jar`.

Ví dụ kiến trúc chuẩn:

~~~text
distribution/
├── packaging-agent.jar          -> JVM nạp bằng -javaagent
├── app.jar                      -> JVM khởi chạy bằng -jar, -cp hoặc -m
└── lib/
    └── greeting-lib.jar         -> thư viện ứng dụng
~~~

Sơ đồ dòng khởi động:

~~~text
java launcher
  |
  +-- -javaagent:packaging-agent.jar=lesson
  |         |
  |         +-- đọc Premain-Class
  |         +-- gọi premain("lesson", Instrumentation)
  |         +-- đăng ký ClassFileTransformer
  |
  +-- lựa chọn một kiểu chạy application:
            |
            +-- -jar app.jar
            +-- -cp ... demo.app.Main
            +-- --module-path ... --module demo.app/demo.app.Main
                         |
                         v
                   gọi application main
                         |
                         v
                  tải class/phụ thuộc
                  transformer nhận callbacks
~~~

Với startup agent, JVM gọi `premain` **trước** application `main`. Vì vậy load-time transformer đăng ký đủ sớm có thể quan sát các lớp ứng dụng được định nghĩa sau thời điểm đăng ký.

## 2. Agent JAR độc lập: Premain-Class là gì?

Một agent JAR nạp khi khởi động phải có manifest entry:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PackagingAgent
~~~

File manifest cần **dòng trống kết thúc main section**. Giá trị `Premain-Class` là **binary name**, có dấu chấm, của class agent nằm trong JAR. Agent class cung cấp một trong hai overload:

~~~java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation instrumentation)
~~~

hoặc:

~~~java
public static void premain(String agentArgs)
~~~

JVM ưu tiên overload nhận `Instrumentation` khi có. Nếu agent cần đăng ký `ClassFileTransformer`, overload có `Instrumentation` tiện nhất.

Khi khởi chạy:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

JVM sẽ truyền chuỗi `"lesson"` vào `agentArgs`. Chuỗi option sau dấu `=` là một **chuỗi do agent tự phân tích**; Java Instrumentation không bắt buộc định dạng JSON, CSV hay key-value nào.

### Agent JAR không cần Main-Class

Một JAR có:

~~~text
Premain-Class: demo.agent.PackagingAgent
~~~

nhưng **không có** `Main-Class` là hoàn toàn bình thường: người vận hành **không chạy**:

~~~bash
java -jar packaging-agent.jar
~~~

để bắt đầu instrument ứng dụng. Lệnh đó sẽ không chạy agent theo cơ chế `Premain-Class`; executable `-jar` cần một application `Main-Class` hợp lệ.

Ngược lại, `app.jar` chỉ có `Main-Class` thì dùng `java -jar app.jar` nhưng **không đủ để khởi động như agent** bằng `-javaagent:app.jar` nếu thiếu `Premain-Class` phù hợp.

### Một agent có thể cần dependency riêng

Nếu `PackagingAgent` dùng thư viện bytecode như ASM hoặc Byte Buddy, các class thư viện ấy phải **được tìm thấy trong ngữ cảnh loader của agent**. Việc ứng dụng có một thư viện trên module path hoặc dưới một nested JAR **không mặc nhiên** giúp agent resolve nó.

Phương án triển khai thường gặp:

- Tạo **agent JAR có dependency được đóng gói phù hợp** (*shaded/uber JAR*) và kiểm tra các resource/service metadata.
- Hoặc phát hành agent JAR cùng các JAR phụ thuộc với một manifest `Class-Path` tương thích, nếu launcher/system loader có thể resolve như thiết kế.
- Giữ các helper runtime cần gọi từ bytecode đã chèn **tách biệt** và bố trí khả năng truy cập theo class loader/module của target.

Trong ví dụ thực hành, agent chỉ dùng JDK API và không có third-party dependency để người học kiểm chứng packaging mà không cần Maven/Gradle.

## 3. Executable JAR: Main-Class và Class-Path

Executable JAR khai báo entrypoint ứng dụng:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/greeting-lib.jar
~~~

Hai thuộc tính có vai trò khác nhau:

- `Main-Class: demo.app.Main` cho JVM biết method `main(String[])` nào cần gọi khi chạy `-jar`.
- `Class-Path: lib/greeting-lib.jar` là **manifest class path**, khai báo một **đường dẫn tương đối từ vị trí của app.jar** tới JAR thư viện cần thêm để tìm class.

Ví dụ:

~~~text
dist/
├── app.jar
└── lib/
    └── greeting-lib.jar
~~~

Nếu `app.jar` nằm trong `dist/` thì `Class-Path: lib/greeting-lib.jar` sẽ trỏ về `dist/lib/greeting-lib.jar`. Nó **không phải** đường dẫn tính từ thư mục làm việc hiện tại trong mọi trường hợp. Việc chuyển mỗi `app.jar` mà không giữ đúng cấu trúc thư mục phụ thuộc có thể khiến ứng dụng không tìm thấy `Greeting`.

**Lưu ý:** manifest `Class-Path` là một chuỗi các **relative URLs** ngăn cách bằng khoảng trắng, không phải cùng cú pháp dấu `:`/`;` của tùy chọn `-cp`. Ví dụ:

~~~text
Class-Path: lib/greeting-lib.jar lib/metrics.jar config/
~~~

Đây là **ví dụ manifest có đường dẫn minh họa**, không phải cấu trúc thực tế của demo. Thư mục phải được khai báo bằng URL tương đối phù hợp; với thư viện production, cần kiểm tra quy tắc đóng gói resource và đường dẫn cho các môi trường triển khai.

### Khi dùng -jar, -cp không điều khiển classpath ứng dụng

Theo hướng dẫn Java launcher, nếu dùng:

~~~bash
java -cp "other.jar" -jar app.jar
~~~

thì **classpath do `-cp` cung cấp không phải nguồn tìm các user classes của ứng dụng khởi chạy bởi `-jar`**. Launcher dùng app JAR và các manifest class-path entries của nó. Vì vậy đừng dựa vào `-cp extra.jar -jar app.jar` để nạp thêm dependencies của executable JAR.

Cách đúng trong ví dụ là đưa dependency vào **manifest `Class-Path`** hoặc dùng một packaging launcher được thiết kế riêng, hay không dùng `-jar` mà chạy bằng `-cp ... MainClass`.

Sự khác biệt này không xóa bỏ `-javaagent`: đó là một **JVM option riêng**. Bạn hoàn toàn có thể chạy:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

và agent vẫn nhận `premain` trước ứng dụng như đã kiểm chứng.

## 4. Class path: ứng dụng khởi chạy bằng main class

Thay vì phụ thuộc vào `Main-Class` manifest của app JAR, người vận hành có thể đưa cả application và library JAR vào class path:

~~~text
Windows:
    java -javaagent:packaging-agent.jar=lesson -cp "app.jar;lib/greeting-lib.jar" demo.app.Main

Linux/macOS:
    java -javaagent:packaging-agent.jar=lesson -cp "app.jar:lib/greeting-lib.jar" demo.app.Main
~~~

Đây là **hai câu lệnh minh họa để chạy khi đang đứng trong dist/**. Trên Windows class path separator là **dấu chấm phẩy `;`**; trên Linux/macOS là **dấu hai chấm `:`**. Dùng một chuỗi classpath cố định với separator sai có thể dẫn tới lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Điểm khác `-jar`:

1. Bạn nêu rõ tên main class `demo.app.Main` ở cuối phần JVM options.
2. `-cp` xác định nơi launcher tìm class và resource cho phần classpath.
3. Không cần manifest `Main-Class` để khởi chạy bằng main class.
4. Có thể đưa nhiều JAR/thư mục vào classpath một cách tường minh.
5. Những class được load từ class path thuộc **unnamed module** của loader tương ứng trong JPMS.

Với cùng demo, app và library JAR chứa `module-info.class` nhưng **khi đặt trên class path chúng vẫn xử lý như non-modular JARs**; JVM không dùng requires/exports của descriptor đó để tạo named module cho các class nằm trên class path. Điều này là một tính chất quan trọng của JAR File Specification.

### Class path wildcard và thứ tự tìm lớp

Một ví dụ launcher thông dụng:

~~~bash
java -cp "app.jar:lib/*" demo.app.Main
~~~

Với Java launcher, phần `lib/*` được mở rộng thành các file `.jar`/`.JAR` trực tiếp trong thư mục, nhưng **thứ tự các JAR do wildcard mở rộng không được bảo đảm**. Không dựa vào wildcard nếu ứng dụng có nhiều versions của cùng một class mà thứ tự load là một phần của logic.

Hơn nữa, class path wildcard không biến một directory thành một “fat JAR”; resource/class files trong cấu trúc không chuẩn vẫn cần packaging đúng.

## 5. Module path: chạy ứng dụng như một named module

JPMS được giới thiệu từ Java 9. Với modular application JAR, file `module-info.java` sẽ được biên dịch thành `module-info.class` trong root của JAR. Ví dụ application module:

~~~java
module demo.app {
    requires demo.greeting;
}
~~~

Và library module:

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

Nội dung descriptor mô tả **quan hệ giữa modules**:

- `requires demo.greeting`: module ứng dụng đọc module thư viện này.
- `exports demo.greeting`: public types trong package thư viện được module khác có quyền đọc truy cập ở mức Java API.
- `module-info.class` xác định tên explicit module, không chỉ binary name của class.

Khi chạy:

~~~text
Windows:
    java -javaagent:packaging-agent.jar=lesson --module-path "app.jar;lib/greeting-lib.jar" --module demo.app/demo.app.Main

Linux/macOS:
    java -javaagent:packaging-agent.jar=lesson --module-path "app.jar:lib/greeting-lib.jar" --module demo.app/demo.app.Main
~~~

Launcher resolve module `demo.app` và dependency `demo.greeting` qua **module path**. Phần `/demo.app.Main` sau tên module là tên main class cần thực thi; có thể bỏ phần đó nếu module artifact đã cung cấp main class thích hợp trong metadata và launcher có thể xác định.

Các điểm cần tách rõ:

| Nơi đặt JAR | JVM đối xử với JAR |
| --- | --- |
| `-cp app.jar` | Classpath entry, **unnamed module**, dù JAR có `module-info.class` |
| `--module-path app.jar --module demo.app` | Explicit named module `demo.app` nếu descriptor hợp lệ |
| `--module-path some-legacy.jar` | Có thể là **automatic module** nếu JAR không có descriptor; tên module theo `Automatic-Module-Name` hoặc quy tắc suy diễn |
| `-jar app.jar` | Chạy theo executable JAR, app được nạp từ class path cơ chế này; descriptor không tự biến nó thành named module |

**Không trông chờ manifest `Class-Path` tự thỏa quan hệ `requires demo.greeting` trong named module graph.** Với lệnh `--module`, module `demo.greeting` phải nằm trong những module mà resolver có thể quan sát/resolve (ví dụ qua `--module-path`). Manifest Class-Path là cơ chế của class-path JAR, không phải module descriptor.

### Agent JAR ở đâu trong modular application?

Dù ứng dụng chạy bằng `--module-path`, agent độc lập vẫn được JVM nạp thông qua **`-javaagent:packaging-agent.jar`**; không cần chuyển agent JAR vào module path chỉ vì app modular.

Theo Java Instrumentation package spec, agent classes của startup agent JAR được system class loader nạp vào **unnamed module của system loader**. Trong demo, transformer nhận tham số `Module module` của **class mục tiêu**, nên nó quan sát:

- `demo.app.Main` thuộc named module `demo.app` khi chạy modular.
- `demo.greeting.Greeting` thuộc named module `demo.greeting` khi chạy modular.

**Đừng đánh đồng module của agent với module của class đang được transform**. Một transformer sống trong system loader's unnamed module vẫn có thể được JVM gọi để quan sát các class của named module. Nhưng nếu bytecode mới được chèn gọi helper của agent, còn phải giải quyết **class loader visibility và module access** cho lệnh gọi đó.

## 6. Bài thực hành: cùng một agent và ứng dụng chạy được cả ba chế độ

Ví dụ dùng **ba artifacts**:

1. `packaging-agent.jar` — Java agent độc lập, chứa `Premain-Class`.
2. `app.jar` — executable application JAR có `Main-Class`, `Class-Path` và `module-info.class`.
3. `lib/greeting-lib.jar` — library modular JAR với module `demo.greeting`.

Agent chỉ **quan sát** callback của các class mục tiêu và in tên module tương ứng; nó luôn trả `null` nên **không sửa bytecode**. Chương trình ứng dụng in `mainModule`, trạng thái flag do agent đặt trước khi main chạy và kết quả gọi thư viện `Greeting.text()`.

Nhờ vậy, nếu một cách chạy bị thiếu dependency, bạn sẽ gặp lỗi; nếu module graph đúng, chương trình cho cùng kết quả nghiệp vụ nhưng **khác tên module**.

### 6.1. Cấu trúc source và distribution

Tạo các thư mục:

~~~text
packaging-demo/
├── agent-src/
│   └── demo/agent/PackagingAgent.java
├── greeting-src/
│   ├── module-info.java
│   └── demo/greeting/Greeting.java
├── app-src/
│   ├── module-info.java
│   └── demo/app/Main.java
├── agent.mf
└── app.mf
~~~

Sau khi build:

~~~text
packaging-demo/
├── agent-bin/
├── greeting-bin/
├── app-bin/
└── dist/
    ├── packaging-agent.jar
    ├── app.jar
    └── lib/
        └── greeting-lib.jar
~~~

Tất cả các nguồn trong demo dùng tính năng Java đã có ở JDK 17. Không có thư viện third-party và không cần `--enable-preview`.

### 6.2. File agent-src/demo/agent/PackagingAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class PackagingAgent {
    public static void premain(String options, Instrumentation inst) {
        System.setProperty("demo.agent.active", "true");
        System.out.println("agentPremain=" + options);

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> old,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if ("demo/app/Main".equals(className)
                        || "demo/greeting/Greeting".equals(className)) {

                    String moduleName = module != null && module.isNamed()
                            ? module.getName() : "unnamed";
                    System.out.println("agentSaw=" + className
                            + " module=" + moduleName);
                }

                return null;
            }
        });
    }
}
~~~

**Cách đọc code:**

- `premain(String, Instrumentation)` được JVM gọi trước `Main.main()`. Nó in chính xác option từ `-javaagent:...=lesson`.
- `System.setProperty("demo.agent.active", "true")` làm một dấu hiệu kiểm thử rằng agent đã thực sự khởi động; trong production không nên tạo side effect toàn JVM không cần thiết.
- `inst.addTransformer(...)` đăng ký transformer cho **load-time instrumentation**; dùng overload một tham số, mặc định **không retransformation-capable**.
- `className` là **JVM internal name** có dấu `/`; lọc `"demo/app/Main"` và `"demo/greeting/Greeting"` trước khi xử lý.
- `module.isNamed()` phân biệt named module với unnamed module của class đích. Tên `"unnamed"` chỉ là **nhãn hiển thị do demo đặt**, không phải giá trị trả về trực tiếp từ `module.getName()`.
- `return null` nghĩa là transformer **không cung cấp bytes thay thế**; JVM tiếp tục định nghĩa class bình thường.

**Lưu ý an toàn:** demo in `System.out.println` ngay trong callback để minh họa. Trong agent production, logging đồng bộ ở đường class loading có thể tăng latency và gây lock contention. Thay bằng filter nhanh, counter hoặc telemetry có giới hạn; không load lại chính target bằng `loader.loadClass(className)` trong callback.

### 6.3. File greeting-src/module-info.java

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

Descriptor khai báo một explicit module tên `demo.greeting`, xuất package `demo.greeting` để application module có thể gọi public method của thư viện.

### 6.4. File greeting-src/demo/greeting/Greeting.java

~~~java
package demo.greeting;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "hello-from-library";
    }
}
~~~

Class này chỉ dùng Java SE. Khi application gọi `Greeting.text()` lần đầu, transformer của agent có cơ hội quan sát tên `demo/greeting/Greeting` và module chứa class này.

### 6.5. File app-src/module-info.java

~~~java
module demo.app {
    requires demo.greeting;
}
~~~

Trong **module mode**, dòng `requires demo.greeting` bắt buộc resolver tìm được module thư viện. Khi JAR này nằm trên **class path**, descriptor không tạo named module cho app; do đó cùng JAR có thể thử cả classpath và modulepath modes.

### 6.6. File app-src/demo/app/Main.java

~~~java
package demo.app;

import demo.greeting.Greeting;

public final class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();

        System.out.println("mainModule="
                + (module.isNamed() ? module.getName() : "unnamed"));
        System.out.println("agentActive="
                + System.getProperty("demo.agent.active", "false"));
        System.out.println("greeting=" + Greeting.text());
    }
}
~~~

Code ứng dụng **không import hoặc gọi class của agent**. Nó chỉ đọc một system property được dùng làm dấu hiệu thử nghiệm. Thiết kế này cho phép thay agent JAR hoặc không bật agent mà không phải thay cách biên dịch Main và Greeting.

Nếu chạy mà không cung cấp `-javaagent`, thuộc tính sẽ nhận mặc định `false`; nếu bật agent, nhận `true`. Trong demo agent đặt property trước khi main chạy, nên kết quả thử nghiệm xác nhận startup order của hai entrypoints.

### 6.7. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PackagingAgent
~~~

Giữ một **dòng trống sau dòng Premain-Class**. Không cần `Main-Class` trong agent JAR. Nếu một triển khai thực sự cần retransform/redefine class đã load, mới bổ sung manifest capability như `Can-Retransform-Classes: true` hoặc `Can-Redefine-Classes: true` cùng kiểm tra `Instrumentation.is...Supported()`; demo hiện tại chỉ làm load-time observation.

### 6.8. File app.mf

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/greeting-lib.jar
~~~

**Giữ một dòng trống cuối main section.** File manifest này dùng để tạo executable `app.jar`; `Class-Path` chỉ tới thư viện nằm trong `dist/lib/` tương đối với vị trí `dist/app.jar`.

Lưu ý: `module-info.class` vẫn sẽ được đóng trong `app.jar` cùng với manifest. Trong `--module` mode, module descriptor quyết định quan hệ dependency; trong `-jar` mode, manifest `Main-Class`/`Class-Path` quyết định entrypoint và library class path.

### 6.9. Biên dịch từng artifact bằng JDK 17+

Các lệnh bên dưới chạy trong thư mục gốc `packaging-demo/`. Trước hết tạo output directories:

~~~bash
mkdir -p agent-bin greeting-bin app-bin dist/lib
~~~

**Bước A — Agent JAR:**

~~~bash
javac --release 17 -d agent-bin agent-src/demo/agent/PackagingAgent.java
jar --create --file dist/packaging-agent.jar \
    --manifest agent.mf -C agent-bin .
~~~

Dùng `-C agent-bin .` để đóng toàn bộ classes được biên dịch, bao gồm class ẩn danh của `ClassFileTransformer` (ví dụ `PackagingAgent$1.class`). Nếu chỉ đóng riêng `PackagingAgent.class` mà quên nested implementation class, agent có thể gặp lỗi class loading khi chạy `premain`.

**Bước B — Thư viện modular JAR:**

~~~bash
javac --release 17 -d greeting-bin \
    greeting-src/module-info.java \
    greeting-src/demo/greeting/Greeting.java

jar --create --file dist/lib/greeting-lib.jar \
    -C greeting-bin .
~~~

Thư viện có `module-info.class`, vì vậy là explicit modular JAR khi đặt trên module path.

**Bước C — Application modular/executable JAR:**

~~~bash
javac --release 17 \
    --module-path dist/lib/greeting-lib.jar \
    -d app-bin \
    app-src/module-info.java \
    app-src/demo/app/Main.java

jar --create --file dist/app.jar \
    --manifest app.mf -C app-bin .
~~~

`javac --module-path` ở bước biên dịch giúp compiler resolve `demo.greeting` từ library module và kiểm tra `requires`. Đây là **compiler option**; việc chạy ứng dụng sau đó với `-jar` hoặc `-cp` vẫn quyết định runtime loading mode độc lập.

Đoạn lệnh Bash dùng dấu `\` để nối dòng. Với **Windows PowerShell 5.1**, dùng lệnh một dòng sau để tránh lỗi shell parsing:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, greeting-bin, app-bin, dist/lib | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/PackagingAgent.java
jar --create --file dist/packaging-agent.jar --manifest agent.mf -C agent-bin .
javac --release 17 -d greeting-bin greeting-src/module-info.java greeting-src/demo/greeting/Greeting.java
jar --create --file dist/lib/greeting-lib.jar -C greeting-bin .
javac --release 17 --module-path dist/lib/greeting-lib.jar -d app-bin app-src/module-info.java app-src/demo/app/Main.java
jar --create --file dist/app.jar --manifest app.mf -C app-bin .
~~~

Khi làm trên CI, **chặn pipeline nếu `javac` hoặc `jar` trả exit code khác 0**; không tiếp tục đến bước chạy với một artifact cũ đã còn trên đĩa.

### 6.10. Chạy mode 1 — executable JAR

Đổi vào thư mục `dist/` sau khi build. Câu lệnh giống nhau trên Windows/Linux/macOS vì không có path-list separator:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=unnamed
mainModule=unnamed
agentActive=true
agentSaw=demo/greeting/Greeting module=unnamed
greeting=hello-from-library
~~~

Từ kết quả:

- `agentPremain=lesson` đứng **trước** output của app.
- `Main` được load với `module=unnamed` dù bên trong `app.jar` có `module-info.class`.
- `Greeting` được tìm thông qua `Class-Path: lib/greeting-lib.jar` từ manifest của executable JAR.
- `greeting=hello-from-library` xác nhận dependency có mặt và gọi thành công.

### 6.11. Chạy mode 2 — class path với main class

**Windows PowerShell:**

~~~powershell
java -javaagent:packaging-agent.jar=lesson -cp "app.jar;lib/greeting-lib.jar" demo.app.Main
~~~

**Linux/macOS Bash:**

~~~bash
java -javaagent:packaging-agent.jar=lesson -cp 'app.jar:lib/greeting-lib.jar' demo.app.Main
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=unnamed
mainModule=unnamed
agentActive=true
agentSaw=demo/greeting/Greeting module=unnamed
greeting=hello-from-library
~~~

Output giống mode `-jar` về module identity vì cả hai dùng classpath-mode loading cho app và library. Nhưng **cơ chế chọn entrypoint khác nhau**: `-cp ... demo.app.Main` nêu class ở command line, không cần đọc `Main-Class` để quyết định class nào được gọi.

Trong ví dụ này, `app.jar` có manifest `Class-Path`, nhưng câu lệnh `-cp` còn liệt kê tường minh cả library để dễ hiểu và kiểm soát. Ở một distribution thật, cần tránh đưa nhiều version trùng classes vào classpath vì thứ tự tìm class có thể tạo lỗi khó chẩn đoán.

### 6.12. Chạy mode 3 — module path với named modules

**Windows PowerShell:**

~~~powershell
java -javaagent:packaging-agent.jar=lesson --module-path "app.jar;lib/greeting-lib.jar" --module demo.app/demo.app.Main
~~~

**Linux/macOS Bash:**

~~~bash
java -javaagent:packaging-agent.jar=lesson --module-path 'app.jar:lib/greeting-lib.jar' --module demo.app/demo.app.Main
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=demo.app
mainModule=demo.app
agentActive=true
agentSaw=demo/greeting/Greeting module=demo.greeting
greeting=hello-from-library
~~~

So với mode 1/2, điểm khác biệt **không phải kết quả nghiệp vụ**, mà là **runtime module identity**:

- `Main.class.getModule().getName()` là `"demo.app"`.
- `Greeting.class.getModule().getName()` (được agent quan sát qua `Module module`) là `"demo.greeting"`.
- Runtime module graph thực sự resolve `requires demo.greeting` từ `module-info.class`.

**Đây chính là phép phân biệt class path và module path có thể quan sát được bằng chương trình**, thay vì chỉ đọc lý thuyết về JPMS.

## 7. So sánh trực tiếp ba cách chạy

| Đặc điểm | `-javaagent ... -jar app.jar` | `-javaagent ... -cp ... Main` | `-javaagent ... --module-path ... --module ...` |
| --- | --- | --- | --- |
| JVM khởi động agent riêng | Có | Có | Có |
| Agent entrypoint | `Premain-Class` / `premain` | Giống bên trái | Giống bên trái |
| App entrypoint | Manifest `Main-Class` | Tên main class trên CLI | Module name / main class |
| App module identity trong demo | `unnamed` | `unnamed` | `demo.app` |
| Library module identity trong demo | `unnamed` | `unnamed` | `demo.greeting` |
| Nguồn dependency chính | Manifest `Class-Path` | `-cp`/launcher classpath | `module-info` và module resolver |
| Có thể dùng cùng agent.jar | Có | Có | Có |
| Có cần đưa agent.jar vào module path | Không | Không | Không |
| Có thể cần module access cho injected helper | Tùy target | Tùy target | Đặc biệt quan trọng với named modules |

Về mặt phân phối, **đúng một bộ JARs có thể chạy theo nhiều mode**, như demo, nếu được biên dịch và khai báo module/manifest phù hợp. Nhưng không phải mọi ứng dụng hiện có có thể đổi cách chạy một cách tùy tiện. Nếu bạn dùng framework launcher, nested JAR layout, automatic modules, dynamic plugins hoặc module-specific service binding, cần kiểm tra runtime mode thực tế.

## 8. Agent classes nằm trong loader/module nào?

Một câu hỏi quan trọng khi triển khai instrumentation là **agent code có thấy các class của ứng dụng không, và class ứng dụng có thấy helper của agent không?**

Theo `java.lang.instrument` package specification, các class từ **agent JAR độc lập** nạp bằng Java instrumentation được **system class loader** nạp vào **unnamed module của system loader**.

Điều đó **không có nghĩa**:

1. Mọi class ứng dụng cũng do system loader định nghĩa. Plugin loader hoặc custom class loader có thể định nghĩa target độc lập.
2. Agent tự động đọc được mọi package private/internal của mọi named module.
3. Bất kỳ injected bytecode nào gọi một helper trong agent JAR cũng chắc chắn resolve và truy cập được helper.
4. Agent cần đứng trong module path của ứng dụng.
5. Agent có thể bỏ qua class loader constraints hoặc Java Module System access rules.

Một ứng dụng modular có thể có target thuộc `demo.app`, trong khi agent `demo.agent.PackagingAgent` vẫn sống trong unnamed module. Method `transform(Module module, ...)` nhận **Module của class mục tiêu**. Đây là thông tin cần giữ để lọc đúng named/unnamed modules.

### Ví dụ sử dụng Module trong transformer

~~~java
if (module != null && module.isNamed()) {
    String targetModule = module.getName();
    if (!"demo.app".equals(targetModule)) {
        return null;
    }
}
~~~

Đây là **mảnh code minh họa** bên trong callback; không phải một chương trình độc lập. Không dereference `module` mù quáng nếu có khả năng null. Cũng đừng chỉ lọc class bằng binary name khi một số class loaders có thể định nghĩa cùng tên ở nhiều ngữ cảnh.

### Khi bytecode instrumented gọi một agent helper

Giả sử transform chèn vào `demo.app.Main` một lời gọi:

~~~text
invokestatic demo/agent/TelemetryHelper.record()V
~~~

Đây là **mnemonic JVM bytecode** dạng minh họa, không phải source Java độc lập. Lúc method target chạy, JVM cần resolve `TelemetryHelper` và thực hiện access checks phù hợp với runtime class loader/module của caller.

Nếu target được bootstrap loader định nghĩa nhưng helper chỉ có trong system loader, bootstrap class **không mặc nhiên tìm thấy helper đó**. Nếu target thuộc named module, còn phải xét readability/exports/opens và cơ chế instrumentation có liên quan. Vì vậy:

- Khi cần helper chung cho bootstrap targets, cân nhắc bố trí một JAR **rất nhỏ, tách biệt** qua `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`, với giới hạn phụ thuộc phù hợp.
- Khi dùng helper trong application/custom loader, đảm bảo loader đó có đường resolve và tránh duplicate classes.
- Với module access phức tạp, cân nhắc API `Instrumentation.redefineModule(...)` hoặc các options launcher như `--add-reads`, `--add-exports`, `--add-opens` **chỉ khi thực sự cần và có kiểm thử**.
- Không dùng việc mở module làm cách sửa lỗi class file sai hoặc thiếu dependency.
- Không để một helper phụ thuộc ngược vào target đang được load rồi vô tình gây reentrant class loading.

**Demo không chèn lời gọi helper vào method target**, nên không yêu cầu bổ sung read edges hay mở packages. Điều đó giúp cô lập bài toán **packaging và resolution của ứng dụng** khỏi bài toán **runtime helper injection**.

## 9. Các loại manifest liên quan tới Java agent

Các attributes dễ bị lẫn:

| Manifest attribute | Nơi dùng | JVM gọi |
| --- | --- | --- |
| `Main-Class` | Executable application JAR | `public static void main(String[])` khi chạy `-jar` |
| `Premain-Class` | Agent JAR nạp bằng `-javaagent` lúc startup | `premain(String, Instrumentation)` hoặc overload một tham số |
| `Agent-Class` | Agent JAR được attach vào **JVM đang chạy** (nếu môi trường hỗ trợ) | `agentmain(...)` |
| `Launcher-Agent-Class` | Agent **đóng cùng executable application JAR** (cơ chế đặc biệt) | `agentmain(...)` **trước application main** |
| `Can-Retransform-Classes` | Agent capabilities | Cho agent yêu cầu retransformation nếu JVM hỗ trợ |
| `Can-Redefine-Classes` | Agent capabilities | Cho agent yêu cầu redefinition nếu JVM hỗ trợ |
| `Boot-Class-Path` | Agent JAR, bootstrap helper search | Bổ sung tìm helper theo quy tắc manifest |
| `Class-Path` | JAR manifest class path | Tìm các phụ thuộc dạng relative URLs |

### Launcher-Agent-Class có giống -javaagent không?

**Không hoàn toàn.** Trong Java SE 21, khi executable JAR có `Launcher-Agent-Class`, launcher có thể nạp agent class **từ chính executable JAR** và gọi **`agentmain` trước app main**. Còn với agent JAR **độc lập** được chỉ định bằng `-javaagent`, JVM gọi **`premain`** dựa trên `Premain-Class`.

Vì thế không được sao chép một class chỉ có method `premain` rồi cho rằng nó sẽ tự chạy khi bạn thêm `Launcher-Agent-Class`. Trường hợp đồng gói cần cấu trúc JAR/entrypoint phù hợp và phải thử riêng.

**Bài thực hành này dùng mô hình độc lập**, không dùng `Launcher-Agent-Class`. Đây là cách triển khai thuận tiện khi người quản trị muốn bật/tắt/thay phiên bản agent mà không build lại application JAR.

### Runtime attach không giống startup agent

Nếu một công cụ attach agent vào JVM **đã chạy**, JAR phải có `Agent-Class`, method `agentmain` và đáp ứng quy tắc/cơ chế attach của implementation. Không thể giả định một JAR chỉ có `Premain-Class` sẽ tự chạy `agentmain` khi attach. Các chính sách cho phép dynamic agent loading có thể thay đổi theo JDK/JVM, nên phải kiểm tra runtime mục tiêu.

Đối với load-time tracing cần bắt các class rất sớm, **khởi động bằng `-javaagent`** thường cho phạm vi quan sát rõ ràng hơn so với attach muộn rồi phải retransform những classes đã load.

## 10. Thư viện third-party của agent và của ứng dụng nên đặt ở đâu?

Đừng trộn lẫn hai hệ dependency chỉ vì chúng cùng nằm trên một máy.

| Phụ thuộc | Ai sử dụng? | Phương án đóng gói |
| --- | --- | --- |
| `java.lang.instrument` / API JDK | Agent startup | Có sẵn trong JDK/module platform; không copy class JDK vào JAR |
| ASM/Byte Buddy của agent | Transformer/helper agent | Agent distribution/shaded JAR hoặc thư viện agent được hệ loader của agent nhìn thấy |
| `demo.greeting.Greeting` | Application `demo.app.Main` | `lib/greeting-lib.jar` theo manifest `Class-Path` hoặc module path |
| Helper được bytecode target gọi tại runtime | Target đã instrument | Phụ thuộc loader/module **của target**, có thể cần bootstrap bridge |
| Build tool plugins (Maven/Gradle) | Máy build | Không nhất thiết đóng vào runtime JAR |
| ServiceLoader descriptors/resources | Library cần runtime discovery | Phải giữ trong JAR dưới `META-INF/services/...` hoặc module descriptors đúng |

Nếu bạn build **fat/uber JAR** bằng Maven Shade hoặc Gradle Shadow, cần xem xét:

- Trùng package/class giữa agent và ứng dụng.
- Shading/relocation giúp tránh xung đột nhiều phiên bản thư viện; nhưng không tự giải quyết mọi module access issue.
- Các file `META-INF/services` cần merge đúng nếu các thư viện phụ thuộc dùng `ServiceLoader`.
- Chữ ký JAR cũ có thể không còn hợp lệ sau khi nội dung bị thay đổi, cần xử lý an toàn và ký lại nếu có yêu cầu.
- `module-info.class` của nhiều dependencies không thể đơn giản ghép làm một module descriptor hợp lệ nếu không có thiết kế JPMS rõ ràng.
- Agent entrypoint class và nested transformer classes phải thực sự có mặt trong artifact sau build.
- Package relocation phải đồng bộ với code phản chiếu, tên resources và tham chiếu trong manifest nếu chúng bị ảnh hưởng.

### Nested JAR của framework không phải classpath chuẩn của java -jar

Một số framework như Spring Boot hỗ trợ executable “fat JAR” với cấu trúc **nested JARs** và custom launcher. Đó là cơ chế **do framework thực hiện**, không phải Java launcher mặc định tự coi mọi JAR con nhúng trong bất kỳ ZIP/JAR là classpath entries.

Nếu muốn agent dùng thư viện nằm trong framework application JAR, đừng suy luận rằng system class loader của agent sẽ tự duyệt được mọi nested JAR do custom launcher của ứng dụng quản lý. Nên phát hành và kiểm thử dependencies của agent **riêng**, rồi xem xét cách helper được target loader/module truy cập.

## 11. Kiểm tra artifact trước khi chạy

Sau khi tạo ba JARs, dùng các công cụ JDK:

~~~bash
jar --list --file dist/packaging-agent.jar
jar --list --file dist/app.jar
jar --list --file dist/lib/greeting-lib.jar
jar --describe-module --file dist/app.jar
jar --describe-module --file dist/lib/greeting-lib.jar
~~~

Các lệnh trên chỉ dùng để **liệt kê/quan sát artifacts**, không tự chạy instrumentation. Kiểm tra những điểm cốt lõi:

- `packaging-agent.jar` phải chứa `demo/agent/PackagingAgent.class` và class transformer lồng mà compiler tạo.
- Manifest của agent phải có `Premain-Class: demo.agent.PackagingAgent`.
- `app.jar` phải chứa `demo/app/Main.class`, `module-info.class` và `Main-Class` manifest.
- `greeting-lib.jar` phải chứa `demo/greeting/Greeting.class` và `module-info.class` của `demo.greeting`.
- Module descriptor của `demo.app` phải `requires demo.greeting`, còn descriptor thư viện `exports demo.greeting`.
- Distribution phải giữ thư viện ở `dist/lib/greeting-lib.jar` nếu muốn dùng executable mode với manifest path của demo.

**Phân biệt kiểm tra artifact và kiểm tra chạy thực:** việc file tồn tại hoặc `jar --list` thấy class không chứng minh runtime module graph đã resolve đúng hoặc transformer đã được gọi. Cần chạy từng lệnh ở mục 6.10–6.12 và kiểm tra stdout/exit code.

## 12. Chẩn đoán lỗi thường gặp khi đóng gói và chạy

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra / hướng sửa |
| --- | --- | --- |
| `no main manifest attribute` khi `java -jar app.jar` | Thiếu `Main-Class` | Kiểm tra app manifest và method main |
| `Failed to find Premain-Class manifest attribute` | Truyền nhầm app JAR vào `-javaagent` hoặc manifest agent thiếu | Kiểm tra manifest trong agent JAR |
| `ClassNotFoundException: demo.app.Main` | Class sai package/path hoặc sai classpath | `jar --list` và command line |
| `NoClassDefFoundError: demo/greeting/Greeting` | Thiếu dependency khi chạy `-jar`/`-cp` | Manifest `Class-Path` hoặc `-cp` đúng |
| `Module demo.greeting not found, required by demo.app` | Module library không nằm trên module path hoặc tên module sai | `--module-path`, `jar --describe-module` |
| `FindException` do nhiều module trùng | Duplicate modules hoặc tên module không nhất quán | Bỏ JAR trùng, kiểm tra module names |
| `IllegalAccessError` / `InaccessibleObjectException` | Module readability, exports/opens hoặc reflection | Kiểm tra JPMS access; không mở rộng vô tội vạ |
| `agentPremain=...` không xuất hiện | Thiếu `-javaagent` hoặc dùng cơ chế startup khác | In command line JVM và manifest |
| App `main` không chạy vì agent error | `premain` ném uncaught error hoặc thiếu agent dependency | Khắc phục agent startup failure trước |
| `app.jar` chạy bằng `-jar` nhưng không dùng `-cp extra.jar` | `-jar` bỏ qua classpath CLI dành cho app | Đưa dependency vào manifest hoặc đổi cách launch |
| Agent tìm thấy khi `-cp` nhưng không thấy helper khi target bootstrap load | Helper chỉ thấy ở system loader | Bố trí bootstrap helper nếu cần |
| App chạy unnamed thay vì named | Dùng `-jar`/`-cp` thay vì `--module` | Chạy đúng module mode |
| `ClassCastException` giữa hai class cùng tên | Khác class loaders tạo hai runtime identities | Kiểm tra defining loader/module và duplicate JAR |
| `UnsupportedClassVersionError` | Build JDK/release cao hơn runtime | Sử dụng `javac --release <target>` |
| Class được transform nhưng `ClassFormatError`/`VerifyError` | Transformer trả bytes không hợp lệ | Verify output và test ở JDK mục tiêu |
| Static helper ném lỗi lúc class loading | Agent helper initialization I/O hoặc phụ thuộc vòng | Pre-initialize dependency và giữ callback tối thiểu |

**Không** dùng cách “copy toàn bộ thư viện ứng dụng vào agent.jar” làm phản xạ đầu tiên khi gặp `ClassNotFoundException`. Việc trùng classes và class loaders có thể làm lỗi nghiêm trọng hơn; trước hết xác định **class nào cần được loader nào nạp** và thuộc module nào.

### Một phép thử tối thiểu để tách lỗi

1. Chạy `java -jar app.jar` **không có agent** (nếu app manifest Class-Path đủ).
2. Chạy `java -javaagent:packaging-agent.jar=lesson -jar app.jar`.
3. Chạy `java -javaagent:packaging-agent.jar=lesson -cp ... demo.app.Main`.
4. Chạy `java -javaagent:packaging-agent.jar=lesson --module-path ... --module demo.app/demo.app.Main`.

Nếu bước 1 lỗi, hãy xử lý packaging của ứng dụng trước. Nếu bước 1 đúng còn bước 2 lỗi, điều tra agent startup/transformer dependencies. Nếu chỉ bước 4 lỗi, kiểm tra module graph và JPMS access. Cách chia lớp lỗi này nhanh hơn việc sửa manifest nhiều lần một cách ngẫu nhiên.

## 13. Triển khai production và các rủi ro phụ

### 13.1. Quyền can thiệp của agent

Java agent có thể can thiệp sâu vào code được JVM chạy. Chỉ triển khai agent từ nguồn tin cậy, kiểm tra version, hash/signature và quyền phân phối JAR. Không nhận một JAR từ nguồn không xác minh rồi bật `-javaagent` trên ứng dụng production.

### 13.2. Giữ đường khởi động tái lập

Lưu đầy đủ:

- JDK runtime version và vendor/JVM implementation.
- Hash/build version của agent JAR, app JAR, library JARs.
- Chính xác lệnh `java` và JVM options.
- Classpath/modulepath cùng thứ tự entries khi có nhiều JAR.
- Agent options và policy instrumentation; không ghi secrets trong stdout.
- Tên class loader/module của target nếu có custom loaders.

Trên Windows, lưu separator `;`; trên Linux/macOS lưu separator `:`. Với container images, bảo đảm COPY toàn bộ cấu trúc `dist/lib/` nếu manifest Class-Path sử dụng đường dẫn đó. Nếu dùng Java executable trong image, kiểm tra nó có `java.instrument` module; các runtime images tối giản tạo bởi `jlink` có thể thiếu modules cần cho một agent.

### 13.3. Tính tương thích Java version

Cả agent và application trong demo được biên dịch bằng `--release 17`. Điều này giới hạn API/class-file version đầu ra của compiler theo Java 17, giúp tránh lỗi khi chạy trên JDK 17+. Nhưng nếu dùng thư viện bytecode của agent, phiên bản thư viện đó **phải hiểu class-file version của class mà nó instrument**, có thể mới hơn chính target release mà agent được compile.

Không đánh đồng `javac --release 17` với việc mọi Java agent sẽ hoạt động trên mọi JVM và mọi bytecode: cần test đúng JDK vendor, phiên bản và các class file mà ứng dụng thực sự load.

### 13.4. Multiple agents và transformer order

Cùng một tiến trình có thể có nhiều options:

~~~bash
java -javaagent:metrics-agent.jar -javaagent:security-agent.jar -jar app.jar
~~~

Các `premain` được gọi theo **thứ tự các `-javaagent` trên command line**. Tuy nhiên, thứ tự thực thi transformer không chỉ phụ thuộc vào thứ tự `premain`: theo `ClassFileTransformer`, JVM áp dụng các nhóm Java/native **retransformation-incapable/capable** theo thứ tự quy định, và thứ tự đăng ký bên trong từng nhóm.

Vì vậy, nếu hai agent cùng sửa một class, cần kiểm thử **pipeline bytes cuối** và tính tương thích thứ tự. Không kết luận “agent A khởi động trước nên mọi transform của A luôn chạy trước mọi transform của B” nếu chúng thuộc những nhóm capability khác nhau.

## 14. Kiểm thử nên có trong CI

Một bộ test packaging có độ tin cậy tốt nên bao gồm:

1. **Manifest test:** đọc `agent.jar` và `app.jar`, xác nhận `Premain-Class`/`Main-Class` đúng binary names.
2. **Jar content test:** mọi nested/anonymous helper classes cần thiết đã được đóng gói.
3. **Dependency test:** executable `-jar` tìm được `lib/greeting-lib.jar` qua đường dẫn tương đối.
4. **Classpath test:** chạy bằng `-cp` với đúng OS separator và xác nhận app main chạy.
5. **Modulepath test:** `jar --describe-module` cho đúng requires/exports và `java --module-path ... --module ...` thành công.
6. **Agent startup test:** `agentPremain` xuất hiện trước `mainModule`.
7. **Transformer callback test:** agent thấy đúng internal names và nhận đúng module của target.
8. **Isolation test:** chạy app **không có agent** vẫn hoạt động theo hợp đồng nghiệp vụ, trừ khi yêu cầu sản phẩm buộc phải có agent.
9. **Negative test — missing lib:** đổi vị trí library trong môi trường test để xác nhận lỗi được phát hiện rõ, không che dấu bởi classpath cũ.
10. **Negative test — wrong manifest:** thiếu `Premain-Class`/`Main-Class` phải làm test fail, không được coi là successful no-op.
11. **Custom loader test:** nếu production có plugins hoặc nested loaders, xác minh helper visibility theo loader thực tế.
12. **JPMS access test:** với named modules, thử các package đóng/mở và injected helper paths nếu agent có sửa bytecode.
13. **Version matrix:** chạy trên JDK mục tiêu, đặc biệt khi có bytecode transformation library.
14. **Artifact integrity:** kiểm tra JAR hash/signature, dependency SBOM và deployment layout.
15. **Performance sanity:** agent không làm tăng startup/class-loading latency vượt budget khi bật nhiều modules/classes.

**Một bản build “jar được tạo thành công” chưa đủ**. CI phải chứng minh entrypoints được gọi và các runtime dependencies thực sự được resolve trong chế độ triển khai dự kiến.

## 15. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Premain-Class` không tương đương `Main-Class` dù cả hai đều nằm trong `META-INF/MANIFEST.MF`?

**Câu 2.** Lệnh `java -cp extra.jar -jar app.jar` có đảm bảo ứng dụng tìm được class trong `extra.jar` không?

**Câu 3.** Manifest app có `Class-Path: lib/greeting-lib.jar`. Bạn chuyển `app.jar` sang thư mục khác nhưng không chuyển folder `lib` tương ứng. Có nguy cơ gì?

**Câu 4.** `app.jar` chứa `module-info.class`. Khi chạy `java -jar app.jar`, `Main.class.getModule().isNamed()` có chắc `true` không?

**Câu 5.** Hai JAR `app.jar` và `greeting-lib.jar` có modules `demo.app` và `demo.greeting`. Lệnh modular launch phải nêu ít nhất những thông tin nào?

**Câu 6.** Agent JAR dùng `-javaagent`, JVM gọi method nào? Nếu agent JAR dùng cơ chế attach sau startup thì khác gì?

**Câu 7.** Khi application chạy bằng module path, agent JAR riêng có bắt buộc được chuyển lên module path không?

**Câu 8.** Trong demo, `agentSaw=demo/app/Main module=demo.app` nhưng agent class có phải là thành viên module `demo.app` không?

**Câu 9.** Chèn `invokestatic demo/agent/TelemetryHelper.record()V` vào method của một bootstrap class. Helper chỉ nằm trên system loader. Việc bytecode được sinh đúng có bảo đảm lệnh chạy được không?

**Câu 10.** Vì sao không nên giả định một JAR chứa JAR khác bên trong sẽ tự chạy được theo Java launcher classpath tiêu chuẩn?

**Câu 11.** Khi tạo JAR agent, bạn đóng mỗi `PackagingAgent.class`, quên class ẩn danh transformer. Tình huống nào có thể xảy ra lúc startup?

**Câu 12.** Manifest có `Launcher-Agent-Class` thì launcher gọi `premain` hay `agentmain`, và nó khác `-javaagent` thế nào?

**Câu 13.** Với `-cp` trên Windows, dấu phân cách các entries là gì? Còn Linux/macOS?

**Câu 14.** Mỗi JAR có `module-info.class` nhưng bạn đặt tất cả trên class path. JPMS có áp dụng quan hệ `requires` của descriptor như explicit modules không?

**Câu 15.** Agent callback luôn `return null` như demo. Điều đó có nghĩa agent đã sửa bytecode của các class mục tiêu chưa?

### Đáp án

1. `Premain-Class` chọn **agent entrypoint** khi dùng `-javaagent`; `Main-Class` chọn **application entrypoint** khi dùng `-jar`.
2. **Không.** Với `-jar`, launcher bỏ qua classpath do `-cp` nêu cho user classes; cần manifest Class-Path hoặc đổi cách launch.
3. Library path tương đối từ app.jar bị hỏng, thường dẫn tới `NoClassDefFoundError`/class resolution failure.
4. **Không.** Trong demo `-jar` đưa app vào `unnamed module` dù JAR có module descriptor.
5. Cần `--module-path` chứa những module có thể resolve và `--module demo.app/demo.app.Main` hoặc main class đã khai báo phù hợp; module graph phải thỏa `requires demo.greeting`.
6. Startup agent gọi `premain` theo `Premain-Class`; attach agent gọi `agentmain` theo `Agent-Class` nếu môi trường hỗ trợ.
7. **Không.** Agent JAR vẫn được JVM nhận qua `-javaagent`.
8. **Không.** Agent nằm trong system loader's unnamed module; `Module` in log là **module của target class**.
9. **Không.** Bootstrap loader/module access có thể không resolve helper ở system loader; cần bố trí visibility phù hợp.
10. Java launcher tiêu chuẩn không tự mở mọi nested JAR làm classpath. Cơ chế nested JAR cần launcher/loader riêng.
11. Agent có thể thiếu class cần thiết cho implementation `ClassFileTransformer` và fail trước khi application main chạy.
12. `Launcher-Agent-Class` gọi **`agentmain` trước main** đối với co-packaged agent; `-javaagent` gọi `premain` từ JAR agent độc lập.
13. Windows: `;`. Linux/macOS: `:`.
14. **Không.** Modular JAR trên class path được xử lý như non-modular JAR.
15. **Chưa.** Nó chỉ quan sát callback; `null` nghĩa là không cung cấp bytecode thay thế ở bước này.

## 16. Checklist trước khi phát hành

- [ ] Agent JAR có `Premain-Class` hợp lệ và chứa mọi class/dependency runtime của agent.
- [ ] Application JAR có `Main-Class` nếu chạy executable `-jar`.
- [ ] Nếu dùng manifest `Class-Path`, đường dẫn tương đối từ app.jar tới dependencies vẫn chính xác sau deployment.
- [ ] Nếu dùng `-cp`, chọn đúng path separator theo OS; không trộn nhầm với manifest path syntax.
- [ ] Nếu dùng JPMS, module descriptors có `requires/exports` phù hợp và artifacts được đặt trên module path.
- [ ] Không mặc định đặt agent JAR vào module path chỉ vì app chạy modular.
- [ ] Helper do bytecode instrumented gọi có loader/module visibility hợp lệ.
- [ ] Không tự tải lại chính class đang được transform từ callback.
- [ ] Build bằng `--release` tương ứng runtime tối thiểu và test bytecode compatibility với JDK thực tế.
- [ ] CI chạy app ở **đúng mode production** và kiểm tra startup agent, main, library calls và exit code.
- [ ] Không lẫn `Agent-Class`/`Launcher-Agent-Class` với `Premain-Class`.
- [ ] Phát hành JARs có integrity/version metadata và kiểm thử đúng cấu trúc thư mục.

## 17. Tóm tắt

**Agent JAR độc lập** là nơi JVM tìm `Premain-Class` và gọi `premain` khi thấy `-javaagent`. **Executable application JAR** là nơi launcher tìm `Main-Class` và manifest library paths khi dùng `-jar`. **Class path** là cơ chế class/resource lookup cho unnamed-module application. **Module path** tạo explicit named modules khi kết hợp `module-info.class` và `--module`.

Trong ví dụ đã thử nghiệm, cùng ba JARs chạy thành công với `-jar`, `-cp` và `--module-path --module`. Hành vi nghiệp vụ giữ nguyên, nhưng thông tin module đích mà agent quan sát thay đổi đúng theo runtime mode. Đây là cơ sở thực hành để deploy agent độc lập mà không làm rối entrypoints, dependency search paths hoặc JPMS configuration của ứng dụng.

## 18. Tài liệu tham khảo chính thức

- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, `Premain-Class`/`Agent-Class`/`Launcher-Agent-Class`, system class loader, manifest capabilities và module visibility.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): cú pháp `-javaagent`, `-jar`, `-cp`, `--module-path`, `--module` và classpath separator.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, `Main-Class`, `Class-Path` relative URLs, modular/automatic JAR và `module-info.class`.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, module/loader/className, nghĩa của `return null` và truyền bytes giữa transformers.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, bootstrap/system loader search, redefineModule và kiểm tra capabilities.
- [Java SE 21 — jar tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): tạo JAR với manifest, `--list`, `--describe-module` và kiểm tra artifacts.
