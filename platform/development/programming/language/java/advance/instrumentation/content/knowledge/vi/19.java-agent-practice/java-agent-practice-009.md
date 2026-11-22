# Tạo tình huống helper không thấy được rồi sửa bằng bố trí class loader phù hợp

## 1. Bài toán thực nghiệm và kết luận cốt lõi

Một Java agent có thể tạo ra **classfile hoàn toàn hợp lệ**, JVM đã định nghĩa được class và ứng dụng đã khởi tạo được object, nhưng ngay khi method đã instrument gọi một **helper class** thì xuất hiện `NoClassDefFoundError`. Nguyên nhân thường không nằm ở cú pháp bytecode, mà ở **class loader dùng để phân giải tham chiếu tới helper**.

Tình huống của bài:

- Agent chạy bằng `-javaagent`, có transformer thay bytes của `lab.target.Service` bằng phiên bản V2 chứa lệnh `lab.helper.Probe.mark()`.
- `Probe.class` **có tồn tại** và hiện diện trên **system classpath** của JVM.
- `Service` được định nghĩa bởi một **`URLClassLoader` độc lập có `parent=null`**, chỉ biết thư mục chứa `Service.class`.
- `Service` đã được định nghĩa, nhưng loader của nó **không thể tìm `Probe`**, nên khi `work()` chạy, JVM ném **`NoClassDefFoundError`**.
- Sửa theo **hai phương án thực tế**: (A) cho child loader **delegate** tới system class loader đang thấy `Probe`; hoặc (B) giữ child loader cô lập nhưng **thêm URL chứa `Probe.class` vào chính search path của child**.

**Điểm cần nhớ:** “Helper nằm trên `-cp`”, “agent JAR đã được nạp”, hoặc “thread context class loader là system” **không bảo đảm** lớp target do một loader khác định nghĩa nhìn thấy helper đó.

Bài thuộc nhóm **Thực nghiệm agent** nên cung cấp đầy đủ mã Java 17+, manifest, cấu trúc thư mục, các lệnh `javac`, `jar`, `java` và **stdout thật**. Chương trình được biên dịch bằng `javac 24.0.2 --release 17` và đã chạy với `-Xverify:all` trên JDK 24.0.2. Các điểm phụ thuộc JVM/vendor hoặc chính sách module được ghi rõ thay vì suy rộng từ một lần chạy.

### 1.1. Các kết quả cần chứng minh

| Kịch bản | Loader của `Service` | `Probe` nằm ở đâu? | Kết quả |
|---|---|---|---|
| Đối chứng: không agent | Child `URLClassLoader(parent=null)` | System classpath | V1 `work()` trả `original`, vì không gọi helper |
| Lỗi: agent cài V2 | Child `URLClassLoader(parent=null)` | System classpath, child không thấy | V2 được định nghĩa nhưng `work()` gây `NoClassDefFoundError` |
| Sửa A: delegation | Child có parent là **system loader** | System classpath, thấy qua parent | In `probe:hit`, trả `instrumented` |
| Sửa B: local search path | Child có parent null nhưng chứa **URL tới helper directory** | Child tự tìm được `Probe` | In `probe:hit`, trả `instrumented` |

Đây là bốn **lần chạy JVM riêng**. Không tái dùng cùng `Class<?>` giữa những lần chạy để tránh nhầm class đã định nghĩa với class sẽ được nạp trong test tiếp theo.

## 2. Vì sao helper có trên classpath vẫn có thể “vô hình”?

### 2.1. Class identity gắn với defining class loader

Trong JVM, danh tính runtime của một class được xác định bởi **binary name cộng với defining class loader**. Hai loader có thể cùng nạp một tên `lab.target.Service` mà tạo ra **hai class khác nhau**. Chính `Class.getClassLoader()` của target cho biết loader nào đã định nghĩa nó.

Mô hình cho tình huống lỗi:

~~~text
System / AppClassLoader
  Search path:
    out/app/                       -> lab.app.Main
    out/helper/                    -> lab.helper.Probe
  |
  +-- có thể tìm Probe: CÓ
  +-- Thread context loader: system (trong lab)

Child URLClassLoader(parent=null)
  Search URLs:
    out/base/                      -> lab.target.Service
  |
  +-- parent delegation tới system: KHÔNG
  +-- có thể tìm Probe: KHÔNG

Java Agent (startup -javaagent)
  |
  +-- transformer trả class bytes V2 cho lab/target/Service
  +-- V2 work() có symbolic ref lab/helper/Probe.mark:()V
  +-- target vẫn do Child URLClassLoader định nghĩa
~~~

Child loader không nhận khả năng nhìn thấy tất cả class trên system classpath chỉ vì các lớp cùng JVM. **Delegation graph của loader** quyết định những class nào có thể được tìm từ một class target cụ thể.

### 2.2. Quy tắc của symbolic reference trong bytecode

Khi JVM thực thi instruction kiểu:

~~~text
invokestatic lab/helper/Probe.mark:()V
~~~

nó phải phân giải symbolic reference trong constant pool của **`lab.target.Service`**. Việc phân giải class được tham chiếu tuân theo **defining loader của lớp chứa reference** và quy tắc JVM/loader delegation; trong lab, đó là child URLClassLoader.

Vì vậy:

- System loader tìm được `Probe` — **đúng**.
- Thread context loader của main là system — **đúng**.
- Child loader có parent null và không có URL helper — **đúng**.
- Child loader không thể phân giải `Probe` khi V2 gọi method — **cũng đúng**.
- Kết quả là `NoClassDefFoundError`, không phải classfile V2 sai định dạng.

**Không được suy rằng TCCL tự động được dùng cho mọi `invokestatic`.** Thread context class loader được một số framework, SPI/`ServiceLoader` hoặc code tùy chọn sử dụng khi họ **chủ động** đọc TCCL; nó không thay thế loader resolution của mỗi symbolic reference trong method bytecode.

### 2.3. `parent=null` nghĩa gì?

Với `new URLClassLoader(urls, null)`, đối số parent null chọn delegation lên **bootstrap class loader**, không phải “không có parent và vẫn tự động tìm mọi thứ từ system”. Các classes `java.lang.*` vẫn có thể được tìm nhờ bootstrap, nhưng `lab.helper.Probe` nằm ở system search path nên child không tự nhiên nhìn thấy nó.

Theo tài liệu `ClassLoader` của Java SE 17, khi parent là null **không có bảo đảm mọi platform classes đều visible**; đừng dùng parent-null custom loader như mặc định trong ứng dụng production mà không có thiết kế isolation rõ ràng.

## 3. Phân biệt ba loại lỗi: load helper, link helper, execute helper

Một lỗi helper vô hình có thể xuất hiện ở những giai đoạn khác nhau:

~~~text
Agent.premain trả về bình thường
        |
        v
Child loader bắt đầu nạp lab.target.Service
        |
        v
Transformer thấy "lab/target/Service"
        |
        +--> trả bytes V2 hợp lệ, chứa ref tới Probe
        |
        v
JVM verify/define Service -> thành công
        |
        v
Service instance được tạo -> thành công
        |
        v
Service.work() được invoke qua reflection
        |
        v
invokestatic Probe.mark() cần resolve helper
        |
        +--> Loader của Service không tìm được Probe
                     |
                     v
               NoClassDefFoundError
~~~

Ba câu hỏi độc lập cần trả lời:

1. **Classfile của target có hợp lệ?** — Trong lab, có: JVM tạo được `Service` instance và `-Xverify:all` không báo `VerifyError`.
2. **Target class đã được định nghĩa?** — Có: chương trình in `app:service-defined-by-child=true` và đi tiếp tới `app:before-work`.
3. **Helper được load/resolved khi gọi method?** — Không trong mode isolated; có trong hai mode fix.

Việc class đã được define không bảo đảm **mọi dependency trong mọi method** sẽ resolve được. JVM có thể trì hoãn một số resolution tới lần đầu instruction liên quan được sử dụng, tùy hợp đồng JVMS và implementation.

### 3.1. `ClassNotFoundException` và `NoClassDefFoundError`

Trong mã lab, ta chủ động gọi:

~~~java
Class.forName("lab.helper.Probe", false, child);
~~~

Nếu child loader không tìm được helper, lời gọi tường minh này ném **`ClassNotFoundException`** (checked exception), được hàm `visible(...)` bắt để in `false`.

Nhưng khi `Service.work()` thực hiện symbolic reference `Probe.mark()`, lỗi có thể là **`NoClassDefFoundError`**, một `LinkageError`. Trong mã mẫu, method được gọi qua `java.lang.reflect.Method.invoke`, nên lỗi bên trong method nằm trong **`InvocationTargetException.getCause()`**; chương trình gỡ lớp wrapper để in đúng root cause.

**Không nhầm:** `ClassNotFoundException` đến từ yêu cầu tìm class rõ ràng qua API, còn `NoClassDefFoundError` khi JVM cố resolve reference của class đã biên dịch có thể phản ánh cùng một nguyên nhân loader không tìm thấy dependency.

### 3.2. Khi nào có lỗi khác?

- `NoSuchMethodError`: tìm thấy class helper nhưng method runtime không có **descriptor** cần gọi.
- `IllegalAccessError`: helper/class/member tìm thấy nhưng access check thất bại, ví dụ package/module access.
- `ClassCastException`: hai classes cùng binary name nhưng **do hai defining loaders khác nhau** tạo, không phải cùng runtime type.
- `ExceptionInInitializerError`: helper tồn tại nhưng static initializer throw; những lần dùng sau có thể dẫn tới `NoClassDefFoundError`.
- `ClassFormatError` hoặc `VerifyError`: bytes tạo ra sai trước khi cài, khác hoàn toàn lab này.
- `SecurityException`: class loader hoặc module/resource security policy từ chối thao tác.

Do đó, phải kết hợp **stack trace đầu tiên**, classloader identity, module context và thời điểm lỗi.

## 4. Thiết kế bốn phép thử độc lập

### 4.1. Source V1 và V2 của cùng một class

Tạo hai tệp `Service.java` có **cùng package và binary name `lab.target.Service`**, nhưng ở **hai source directories khác nhau**:

- **V1** `src/base/lab/target/Service.java`: method `work()` trả chuỗi `"original"`, không gọi helper.
- **V2** `src/v2/lab/target/Service.java`: method `work()` gọi `lab.helper.Probe.mark()` rồi trả `"instrumented"`.

Hai bản được compile thành **hai output folders riêng**. `out/base` chứa V1 để child loader tải class, trong khi agent đọc bytes V2 từ `out/v2/lab/target/Service.class` và thay bytes **trước khi JVM định nghĩa class**.

### 4.2. Helper độc lập

`lab.helper.Probe` nằm trong `out/helper`. Ta luôn đặt `out/helper` vào **system classpath**:

~~~text
out/app;out/helper          (Windows)
out/app:out/helper          (Linux/macOS)
~~~

Nhờ vậy, khi chương trình in `app:system-helper-visible=true`, ta biết helper **thực sự tồn tại và system loader tìm được**. Nếu child vẫn không thấy, lỗi rõ ràng thuộc **loader visibility**, không phải quên build helper.

### 4.3. Ba kiểu child loader

Code application chọn mode:

~~~text
isolated:
  URLClassLoader(urls = [out/base], parent = null)

delegated:
  URLClassLoader(urls = [out/base], parent = system)

local:
  URLClassLoader(urls = [out/base, out/helper], parent = null)
~~~

**Hai cách sửa khác bản chất:**

- `delegated`: helper vẫn do **system loader** định nghĩa; child nhờ parent delegation để dùng helper.
- `local`: child giữ parent null nhưng có chính URL chứa helper; **child có thể tự định nghĩa Probe**. Điều này phù hợp một plugin cần tự chứa dependency, nhưng có thể tạo **bản copy class độc lập** với class cùng tên do system loader định nghĩa. Nếu helper API chia sẻ object types với application, cần thiết kế identity/visibility cẩn thận.

## 5. Cấu trúc thư mục lab hoàn chỉnh

~~~text
helper-loader-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── lab/agent/HelperVisibilityAgent.java
│   ├── app/
│   │   └── lab/app/Main.java
│   ├── base/
│   │   └── lab/target/Service.java
│   ├── v2/
│   │   └── lab/target/Service.java
│   └── helper/
│       └── lab/helper/Probe.java
└── out/                        (tạo sau khi build)
    ├── agent/
    ├── app/
    ├── base/
    ├── v2/
    ├── helper/
    └── visibility-agent.jar
~~~

Không đổi tên package tùy tiện khi chép mã, vì transformer **so sánh chính xác** internal class name `lab/target/Service` và V2 tham chiếu tới `lab/helper/Probe`.

Mã sử dụng các API công khai của `java.instrument`, reflection và `java.net.URLClassLoader`. Không cần ASM hoặc Byte Buddy: **agent thay toàn bộ classfile lúc class đang được define bằng một classfile V2 đã được `javac` tạo hợp lệ**. Đây là cách thử có kiểm soát để tập trung vào classloader topology, không đánh lạc hướng sang thuật toán chỉnh bytecode.

## 6. Viết agent nhận classfile V2 từ một đường dẫn

Tệp **`src/agent/lab/agent/HelperVisibilityAgent.java`**:

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class HelperVisibilityAgent {
    public static void premain(String path, Instrumentation inst)
            throws Exception {

        byte[] replacement = Files.readAllBytes(Path.of(path));

        System.out.println("agent:ready");

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefined,
                    ProtectionDomain domain,
                    byte[] original) {

                if (!"lab/target/Service".equals(name)) {
                    return null;
                }

                System.out.println(
                        "agent:transform=lab/target/Service");

                return replacement.clone();
            }
        }, false);
    }
}
~~~

### 6.1. Vì sao chọn premain?

Với `-javaagent`, JVM gọi `premain` **trước `Main.main`**, nên transformer đã đăng ký trước lúc Main tạo custom `URLClassLoader` và nạp `Service`. Chúng ta muốn thay bytes **ngay trong lần class definition đầu tiên** chứ không phải đổi definition của một class đã load.

### 6.2. Ý nghĩa callback

- `name` là **internal name** `lab/target/Service`, không phải `lab.target.Service`.
- Lọc chặt `if (!"lab/target/Service".equals(name)) return null;` tránh sửa classes của JVM, agent và application khác.
- `replacement` là bytes của `Service` V2 đã được compile trước; `replacement.clone()` trả mảng mới để callback không chia sẻ mảng mutable với code khác.
- V2 vẫn có **cùng binary class name** với V1: `lab.target.Service`.
- Callback xảy ra trước khi class được define. `System.out.println("agent:transform...")` **không tự chứng minh** JVM đã verify và cài xong bytes; mốc `app:service-defined-by-child=true` và invocation mới cung cấp bằng chứng bổ sung.
- `addTransformer(..., false)` không xin retransformation capability; ta không gọi `retransformClasses`.
- Agent load replacement file **trước khi đăng ký transformer**, nên thiếu file sẽ làm startup fail rõ ràng thay vì callback bất ngờ lỗi giữa class loading path.

### 6.3. Vì sao không phải “tự thêm helper vào system search path”?

Agent chỉ **sinh/thay bytes cho Service**, không buộc target loader nhìn thấy class helper. Java Instrumentation **không tự động chuyển mọi dependency của agent** sang defining loader của target. Vì vậy V2 vẫn có thể gọi tới một class vô hình dù transformer hoạt động hoàn hảo.

Đây chính là nguyên nhân thực nghiệm cần tìm.

### 6.4. Hạn chế khi dùng replacement classfile

Phương pháp thay bytes của classfile V1 bằng V2 thích hợp **cho class chưa được define**. Nếu target đã loaded và cần `redefineClasses`/`retransformClasses`, còn có giới hạn schema, VM capabilities và active frames. Không lấy ví dụ load-time này để suy ra có thể thay superclass, fields hoặc methods tùy ý cho lớp đang chạy.

## 7. Viết ứng dụng tự tạo loader và kiểm tra visibility

Tệp **`src/app/lab/app/Main.java`**:

~~~java
package lab.app;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Main {
    private static boolean visible(
            ClassLoader loader, String name) {
        try {
            Class.forName(name, false, loader);
            return true;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "mode targetDir helperDir");
        }

        String mode = args[0];
        if (!mode.equals("isolated")
                && !mode.equals("delegated")
                && !mode.equals("local")) {
            throw new IllegalArgumentException("bad mode");
        }

        URL target = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();
        URL helper = Path.of(args[2])
                .toAbsolutePath().toUri().toURL();

        ClassLoader system = ClassLoader.getSystemClassLoader();

        ClassLoader parent =
                mode.equals("delegated") ? system : null;

        URL[] urls = mode.equals("local")
                ? new URL[] {target, helper}
                : new URL[] {target};

        System.out.println("app:mode=" + mode);

        System.out.println(
                "app:system-helper-visible="
                + visible(system, "lab.helper.Probe"));

        System.out.println(
                "app:context-is-system="
                + (Thread.currentThread().getContextClassLoader()
                   == system));

        try (URLClassLoader child =
                     new URLClassLoader(urls, parent)) {

            System.out.println(
                    "app:child-parent="
                    + (child.getParent() == null
                       ? "bootstrap" : "system"));

            System.out.println(
                    "app:child-helper-visible="
                    + visible(child, "lab.helper.Probe"));

            Class<?> service = Class.forName(
                    "lab.target.Service", true, child);

            System.out.println(
                    "app:service-defined-by-child="
                    + (service.getClassLoader() == child));

            Object instance = service
                    .getDeclaredConstructor().newInstance();

            Method work = service.getMethod("work");

            System.out.println("app:before-work");

            try {
                Object value = work.invoke(instance);
                System.out.println("app:result=" + value);
            } catch (InvocationTargetException e) {
                System.out.println(
                        "app:invoke-cause="
                        + e.getCause().getClass().getSimpleName());
            }
        }

        System.out.println("app:end");
    }
}
~~~

Đây là **file Java độc lập hoàn chỉnh**, không cần compile với agent classes; ứng dụng chỉ sử dụng reflection, `URLClassLoader` và JDK APIs.

### 7.1. Logic các biến

- `system`: system/application class loader trong JVM hiện tại.
- `target`: URL của directory chứa `Service.class` V1.
- `helper`: URL của directory chứa `Probe.class`.
- `mode=isolated`: child có parent null, URL chỉ có target.
- `mode=delegated`: child có parent system, URL chỉ có target.
- `mode=local`: child có parent null, URL có target và helper.

Nhánh trả lỗi trong `visible(...)` chỉ bắt `ClassNotFoundException` khi thử `Class.forName`. Mục đích là so sánh **khả năng tìm helper qua từng loader**; không dùng `Class.forName` trên mọi class của JVM hoặc coi hàm này là bộ kiểm chứng khả năng truy cập module/member toàn diện.

### 7.2. Tại sao có app:context-is-system?

Dòng:

~~~text
app:context-is-system=true
~~~

xuất hiện trong cả ba modes trên JVM kiểm thử. Nó minh họa rất rõ: **TCCL = system không tự làm `Service` do child loader định nghĩa thấy `Probe`**. Một số framework cố ý sử dụng TCCL để tải plugins; nhưng `invokestatic` được liên kết theo symbolic reference của class chứa instruction, không đơn giản “tra TCCL của thread”.

### 7.3. Tại sao in service-defined-by-child?

`Class.forName("lab.target.Service", true, child)` tải và khởi tạo `Service`. Code so sánh trực tiếp:

~~~java
service.getClassLoader() == child
~~~

Nếu true, ta biết **Service thực sự do child định nghĩa**, không bị parent loader “chiếm tên”. Trong lab, system classpath **không chứa `Service.class`**, nên ngay cả mode `delegated` cũng để child define Service. Chỉ helper được parent cung cấp.

Đây là điểm quan trọng trong cách sửa A: **không đổi ownership của target class**, chỉ mở khả năng nhìn thấy dependency qua delegation.

### 7.4. Reflection và root cause

`Method.invoke` bọc exception/error ném bên trong method bằng `InvocationTargetException`. Nếu chỉ log wrapper này, người học có thể thấy tên `InvocationTargetException` mà không nhìn thấy `NoClassDefFoundError` thật sự. Trong code, ta dùng:

~~~java
Throwable cause = e.getCause();
System.out.println(
        "app:invoke-cause=" + cause.getClass().getSimpleName());
~~~

Đây là **trích đoạn mô tả** cùng hành vi với code hoàn chỉnh (trong bản đầy đủ gọi `e.getCause()` trực tiếp). Để chẩn đoán production, lưu toàn bộ stack trace của root cause, loader/module context và nested exceptions; không chỉ in short name.

**Không bắt `InvocationTargetException` rồi nuốt lỗi trong ứng dụng thật.** Ở đây catch nhằm cho test hiển thị và tiếp tục chạy, không phải chiến lược production recovery.

## 8. Service V1, Service V2 và Probe helper

### 8.1. V1: method không phụ thuộc helper

Tệp **`src/base/lab/target/Service.java`**:

~~~java
package lab.target;

public final class Service {
    public String work() {
        return "original";
    }
}
~~~

Đây là classfile gốc mà child loader sẽ tìm tại `out/base/lab/target/Service.class`. Với **không agent**, dù child không thấy `Probe`, method vẫn chạy tốt vì V1 không có symbolic reference tới helper.

### 8.2. V2: bytecode hợp lệ nhưng có reference tới Probe

Tệp **`src/v2/lab/target/Service.java`**:

~~~java
package lab.target;

import lab.helper.Probe;

public final class Service {
    public String work() {
        Probe.mark();
        return "instrumented";
    }
}
~~~

V2 có cùng package, class name và public method signature với V1, nhưng thêm lời gọi `Probe.mark()`. Khi compile V2, trình biên dịch phải nhìn thấy `Probe` để sinh bytecode hợp lệ; vì vậy lệnh build V2 sử dụng `-cp out/helper`.

**Biên dịch được V2 không bảo đảm `Probe` có trong loader search path của Service khi chạy.** Đây là sự phân biệt giữa compile-time classpath và runtime classloader topology.

### 8.3. Helper: không cần ASM/Byte Buddy

Tệp **`src/helper/lab/helper/Probe.java`**:

~~~java
package lab.helper;

public final class Probe {
    public static void mark() {
        System.out.println("probe:hit");
    }
}
~~~

Helper chỉ dùng `System.out` nên đủ đơn giản để chạy qua system loader hoặc child loader parent-null trong hai mode fix. Khi helper phụ thuộc thêm JAR, native libraries, logging facade hoặc module khác, việc bố trí loader cần giải quyết **toàn bộ dependency closure**, không chỉ `Probe.class`.

## 9. Manifest và biên dịch: hai classfiles trùng tên nhưng tách output

Tệp **`agent.mf`** (giữ newline cuối):

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.HelperVisibilityAgent

~~~

`Premain-Class` là **binary Java name** với dấu chấm, còn callback transformer so sánh `lab/target/Service` với slash. Đừng nhầm hai định dạng.

### 9.1. Tạo thư mục output

Bash:

~~~bash
mkdir -p out/agent out/app out/base out/v2 out/helper
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/base, out/v2, out/helper
~~~

### 9.2. Build trên JDK 17+

Đứng trong thư mục gốc `helper-loader-lab` và chạy tuần tự:

~~~bash
javac --release 17 -d out/agent src/agent/lab/agent/HelperVisibilityAgent.java

javac --release 17 -d out/app src/app/lab/app/Main.java

javac --release 17 -d out/base src/base/lab/target/Service.java

javac --release 17 -d out/helper src/helper/lab/helper/Probe.java

javac --release 17 -cp out/helper -d out/v2 src/v2/lab/target/Service.java

jar --create --file out/visibility-agent.jar --manifest agent.mf -C out/agent .
~~~

Giải thích:

1. `out/agent`: bytecode agent.
2. `out/app`: bytecode application `Main`, không import `Service`.
3. `out/base`: `Service` V1 để child URLClassLoader nạp.
4. `out/helper`: `Probe` riêng, được system loader tìm nhờ runtime classpath.
5. `out/v2`: `Service` V2 đã được javac tạo với reference tới Probe; **không đặt V2 lên runtime classpath**.
6. `visibility-agent.jar`: chứa `HelperVisibilityAgent` và manifest `Premain-Class`.

`--release 17` hạn chế source/API và tạo classfile major **61**, phù hợp Java 17+. Trong lần thực nghiệm, toolchain là JDK 24.0.2 nhưng biên dịch với `--release 17`; kiểm thử chạy bằng JDK 24.0.2. Đối với sản phẩm phải chạy runtime 17/21, nên chạy thêm integration test trực tiếp trên các JVM đó.

### 9.3. Kiểm tra artifact trước khi chạy

~~~bash
jar --list --file out/visibility-agent.jar
javap -c -p -classpath out/v2 lab.target.Service
jdeps --jdk-internals out/visibility-agent.jar
~~~

Các điểm cần thấy:

- Agent JAR có `lab/agent/HelperVisibilityAgent.class` và nested transformer class.
- `META-INF/MANIFEST.MF` của **final JAR** chứa đúng `Premain-Class`.
- `javap -c` với V2 cho thấy instruction gọi `lab/helper/Probe.mark:()V` trong `work()`.
- `jdeps --jdk-internals` không báo dependency tới JDK internal API.
- `out/base` và `out/v2` có cùng binary name `lab.target.Service` nhưng **khác body method**.

Không dùng `--add-exports` hay `--add-opens` để chạy ví dụ: mọi class nằm trong unnamed modules, dùng public APIs và helper public.

## 10. Đối chứng không agent: Service V1 hoạt động

Đây là baseline để chắc chắn child loader đã có thể nạp Service. System classpath **có Probe**, nhưng child parent-null **không nhìn thấy Probe**. Vì V1 không gọi helper, không có lỗi.

**Windows PowerShell hoặc Command Prompt** (classpath separator `;`):

~~~powershell
java -Xverify:all -cp "out/app;out/helper" lab.app.Main isolated out/base out/helper
~~~

**Linux/macOS Bash** (classpath separator `:`):

~~~bash
java -Xverify:all -cp "out/app:out/helper" lab.app.Main isolated out/base out/helper
~~~

**Stdout chính xác từ JDK 24.0.2:**

~~~text
app:mode=isolated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=false
app:service-defined-by-child=true
app:before-work
app:result=original
app:end
~~~

Đọc kết quả:

- System loader tìm thấy `Probe`, chứng minh helper không thiếu ở toàn JVM.
- TCCL là system nhưng `child-helper-visible=false`.
- Service thực sự được định nghĩa bởi child.
- Method gốc trả `original` và process hoàn tất.
- Không có `agent:ready` hoặc `agent:transform` vì chưa chạy agent.

**Ý nghĩa:** class loader parent-null không tự động gây lỗi; nó gây lỗi **khi bytecode đòi một dependency mà loader không tìm được**.

## 11. Tái hiện lỗi: agent cài V2 nhưng child loader không thấy Probe

### 11.1. Command tái hiện

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main isolated out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main isolated out/base out/helper
~~~

Tham số sau dấu `=` của `-javaagent` là đường dẫn V2 class bytes. Đừng nhầm nó với application classpath. JVM đưa tham số đó vào `premain(String path, Instrumentation inst)`, agent đọc bytes trước khi đăng ký transformer.

### 11.2. Stdout đã được kiểm thử

~~~text
agent:ready
app:mode=isolated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=false
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
app:invoke-cause=NoClassDefFoundError
app:end
~~~

Đây là **đầu ra của đúng source trong bài**, không phải một tình huống giả định. Program kết thúc mã 0 vì `Main` chủ động bắt `InvocationTargetException` và in root cause để phục vụ lab. Nếu một production method không có catch này, lỗi có thể làm request/thread thất bại.

### 11.3. Chứng minh nguyên nhân bằng từng mốc

1. `agent:ready`: `premain` đọc file V2 và đăng ký transformer thành công.
2. `app:system-helper-visible=true`: helper có thể được tìm bằng system loader.
3. `app:context-is-system=true`: TCCL cũng là system, nhưng điều đó **không giúp** symbolic reference trong Service V2.
4. `app:child-parent=bootstrap`: child parent-null không delegate tới system.
5. `app:child-helper-visible=false`: lớp `Probe` không nằm trong search path của child.
6. `agent:transform=lab/target/Service`: transformer đã chọn đúng class và trả V2 bytes.
7. `app:service-defined-by-child=true`: JVM đã thực sự định nghĩa Service bằng child.
8. `app:before-work`: chỉ còn method invocation.
9. `app:invoke-cause=NoClassDefFoundError`: method V2 không resolve được `Probe`.

**Kết luận chính xác:** **bytecode V2 đã được cài/định nghĩa thành công**, nhưng helper không visible đối với **defining loader của Service**. Lỗi **không** nằm ở `Premain-Class`, không phải `ClassFormatError`, không phải helper bị thiếu trên toàn system classpath.

## 12. Cách sửa A: ủy quyền tới system class loader

Thay cách tạo child từ:

~~~java
new URLClassLoader(
        new URL[] {target},
        null);
~~~

thành:

~~~java
new URLClassLoader(
        new URL[] {target},
        ClassLoader.getSystemClassLoader());
~~~

Cách này **không tự đổi defining loader của Service sang system**: vì `Service.class` chỉ có trong `out/base`, không có trên system classpath, child vẫn tự define Service. Nhưng khi Service cần `Probe`, child delegation lên parent **system** và tìm được helper.

### 12.1. Command sửa A

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main delegated out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main delegated out/base out/helper
~~~

### 12.2. Stdout chính xác đã kiểm thử

~~~text
agent:ready
app:mode=delegated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=system
app:child-helper-visible=true
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
probe:hit
app:result=instrumented
app:end
~~~

**Điểm khác biệt quyết định:** `app:child-parent=system` và `app:child-helper-visible=true`. Dòng `probe:hit` chứng minh helper code thực sự đã được thực thi; `app:result=instrumented` chứng minh method V2 hoàn tất.

### 12.3. Khi nào nên chọn delegation?

Phù hợp nếu:

- Helper là **API dùng chung** cho nhiều plugins/target classes.
- Helper có thể được system hoặc một ancestor loader **định nghĩa một lần**.
- Target cần trao đổi những object types với phần còn lại của app.
- Có chính sách class identity và versions rõ ràng.

Cần kiểm tra:

- Nếu system loader **cũng chứa Service** cùng tên, parent-first delegation có thể làm child **không còn tự define Service**; dòng `service-defined-by-child` sẽ thành false, làm thí nghiệm khác đi.
- Nếu helper được system loader tải nhưng cần dependencies chỉ có ở child, helper lại có thể không tìm những dependencies đó (đảo ngược hướng visibility).
- Không tùy tiện mở parent delegation tới toàn bộ system classpath cho plugins không tin cậy; điều này mở rộng phạm vi các APIs mà plugin có thể gọi.

Cách sửa A điều chỉnh **loader hierarchy** cho phù hợp, không phải nâng cấp bytecode parser hay thêm launcher flags.

## 13. Cách sửa B: giữ isolation, đặt helper trong search path của child

Thay child URLs từ:

~~~java
new URLClassLoader(
        new URL[] {target},
        null);
~~~

thành:

~~~java
new URLClassLoader(
        new URL[] {target, helper},
        null);
~~~

Khi parent null, child không delegate tới system, **nhưng có cả folder chứa Service và folder chứa Probe**, nên nó tự tìm được helper.

### 13.1. Command sửa B

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main local out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main local out/base out/helper
~~~

### 13.2. Stdout chính xác đã kiểm thử

~~~text
agent:ready
app:mode=local
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=true
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
probe:hit
app:result=instrumented
app:end
~~~

**Điểm khác biệt:** `app:child-parent=bootstrap` giữ nguyên (không đổi delegation), nhưng `app:child-helper-visible=true` vì local URLs đã thêm helper. Method V2 chạy thành công.

### 13.3. Cái giá của isolation

Dù system loader cũng đã tải được `lab.helper.Probe`, child parent-null có thể **định nghĩa một bản Probe khác** từ `out/helper`. Hai classes cùng binary name nhưng khác defining loaders **không là cùng runtime type**.

Trong demo, `Probe.mark()` trả `void`, chỉ dùng public JDK `System.out` nên việc có bản helper riêng không gây vấn đề. Nhưng nếu helper:

- trả object của một interface do system loader định nghĩa;
- dùng singleton/static state chia sẻ giữa nhiều plugins;
- giữ caches/registries toàn cục;
- liên kết với type annotations hoặc framework service APIs;
- gọi các dependencies chỉ có ở system loader;

thì child-local helper có thể tạo class identity mismatch, duplicated state hoặc `ClassCastException`. Khi đó nên thiết kế **shared API classes ở một loader chung**, còn implementation có thể isolated, thay vì copy nguyên toàn bộ type graph.

## 14. So sánh hai cách sửa và chọn kiến trúc

| Tiêu chí | Sửa A: parent=system | Sửa B: thêm helper URL vào child |
|---|---|---|
| Target vẫn do child define? | Có trong lab, vì system không có Service | Có |
| Helper được tìm bởi | System parent qua delegation | Child search path |
| Child có còn isolation khỏi system app classes? | Không hoàn toàn; thấy system delegation | Có hơn, nhưng vẫn thấy bootstrap |
| Helper có thể bị define hai bản cùng tên? | Ít hơn nếu dùng chung ancestor | Có, nếu system và child đều có cùng helper |
| Chia sẻ interfaces/DTO với app | Thuận tiện hơn nếu loader graph nhất quán | Cần thiết kế loader boundary rõ |
| Phụ thuộc vào system loader classpath | Có | Không đối với helper đã thêm URL |
| Rủi ro package/version conflict | Parent-first có thể chọn version system không mong đợi | Plugin-local version có thể xung đột ở interface boundary |
| Khả năng phù hợp plugin cô lập | Cần cân nhắc trust/security | Phù hợp khi helper tự chứa dependencies và giao diện được kiểm soát |

**Nguyên tắc chọn:** đặt helper **ở một loader mà class chứa bytecode tham chiếu có thể sử dụng**, và bảo đảm helper lại nhìn thấy **các dependencies của chính nó**. Không chỉ hỏi “helper nằm trong JAR nào” mà phải vẽ được **loader graph** và xác định **class identity**.

### 14.1. Điều không nên làm

- Không thêm `out/helper` vào **system** classpath rồi mặc định target parent-null sẽ thấy helper; test cho thấy điều đó sai.
- Không đổi `Thread.currentThread().setContextClassLoader(system)` và kỳ vọng mọi `invokestatic` dùng system loader.
- Không gọi `Class.forName("lab.helper.Probe", true, system)` trước rồi kỳ vọng child parent-null tự dùng class đã load bởi system.
- Không đổi `Premain-Class` hay sửa manifest agent để “chữa” một symbolic reference khi target đã được cài.
- Không chỉ copy `Probe.class` vào agent JAR mà bỏ qua loader của target. Agent JAR thường nằm trong system search path, không phải bootstrap hoặc child-local search path.
- Không giấu lỗi `NoClassDefFoundError` bằng blanket catch trong business code; trong demo catch chỉ để in nguyên nhân.

## 15. Giải pháp nâng cao: bootstrap helper và hệ thống module

Hai cách đã test là cách trực tiếp nhất. Với một agent thực sự instrument các **bootstrap classes**, custom loader parent-null hoặc nhiều application loaders, đôi khi cần tổ chức helper vào một **bootstrap-visible helper JAR**.

### 15.1. appendToBootstrapClassLoaderSearch

Java SE cung cấp:

~~~java
Instrumentation.appendToBootstrapClassLoaderSearch(
        java.util.jar.JarFile jarfile);
~~~

Đây là **mã chữ ký minh họa**, không phải lệnh độc lập có thể chạy. Cần tạo một JAR riêng chứa classes helper phù hợp rồi truyền `JarFile` vào API trong agent.

Hợp đồng của API: khi bootstrap loader không tìm thấy class trong search path mặc định, JVM có thể tìm trong JAR được append. Như vậy một child loader có parent null **có thể delegate lên bootstrap** để tìm helper nếu helper đúng package/name đã được thêm.

**Nhưng đây là kỹ thuật có rủi ro:**

1. Helper JAR cho bootstrap nên chỉ chứa **những classes thực sự dành cho bootstrap** và phụ thuộc vào classes bootstrap có thể truy cập.
2. Không nhét cả agent, ASM/Byte Buddy, JSON, logging stack vào bootstrap nếu không cần; có thể gây class loading recursion hoặc namespace collision.
3. Một class được load bởi bootstrap có thể không thấy dependencies chỉ tồn tại ở system loader.
4. Package-private helpers, nested classes hoặc non-public accessors có thể bị `IllegalAccessError` nếu cùng tên/package nhưng khác **runtime package** (package + defining loader).
5. Bootstrap class path append không tự tạo JPMS module read/export relations mà các classes ở named modules có thể cần.
6. Test trên chính runtime/vendor; chỉ append JAR có nguồn và permission rõ ràng.

**Không có test bootstrap append trong bộ lab chính**; các kết quả stdout ở mục 11–13 chỉ chứng minh **delegation** và **local URL search path**. Chỉ triển khai bootstrap helper khi bài toán thật sự cần, với integration tests riêng.

### 15.2. appendToSystemClassLoaderSearch có giới hạn

Java SE còn có:

~~~java
Instrumentation.appendToSystemClassLoaderSearch(
        java.util.jar.JarFile jarfile);
~~~

Nó thêm JAR vào nơi **system class loader** tìm kiếm, không tự làm child parent-null nhìn thấy system loader. Nếu hệ thống đang mắc lỗi `isolated` giống demo, chỉ gọi `appendToSystemClassLoaderSearch` **không phải cách sửa** trừ khi thay luôn delegation graph hoặc loader search path.

### 15.3. Module access là một chiều khác

Từ Java 9, named modules có quy tắc reads/exports/opens:

- **Class không được tìm thấy**: thường là loader search path hoặc module resolution/visibility.
- **Class có thể tìm nhưng không được access**: có thể xuất hiện `IllegalAccessError` hoặc reflection `InaccessibleObjectException`.
- `Instrumentation.redefineModule` có thể thay một số module reads/exports/opens theo API, nhưng **không tự cung cấp classfile đang thiếu** cho child loader.
- `--add-opens` phục vụ deep reflection, không là thuốc chữa chung cho mọi `NoClassDefFoundError`.

Trong lab các classes nằm trên classpath và unnamed modules, nên kết quả tập trung vào **loader graph**, không phụ thuộc config `module-info.java`.

## 16. Chẩn đoán production theo từng bằng chứng

Khi agent in log transform thành công nhưng method gọi helper lỗi, nên thu thập thông tin theo trình tự:

### Bước 1 — Xác nhận bytecode đang thực thi đã được cài

- Agent/transformer có được gọi cho **đúng class internal name** chưa?
- Transformer trả `null` hay trả `byte[]` thay thế?
- Có transformer khác trong pipeline không?
- JVM có phát `VerifyError`/`ClassFormatError` trước khi define không?
- Mốc xác nhận definition/update thành công là gì?
- Với class đã load, `retransformClasses`/`redefineClasses` có return bình thường không?

**Không coi callback log là bằng chứng cài đặt hoàn tất.** Trong demo, mốc `service-defined-by-child=true` đi trước lỗi `work()` giúp khẳng định target đã được định nghĩa.

### Bước 2 — Tìm class chứa symbolic reference lỗi

Dùng `javap -c -p` hoặc một bytecode inspector phù hợp để thấy:

~~~text
invokestatic lab/helper/Probe.mark:()V
~~~

Kiểm tra binary name, method name, descriptor và source artifact của bytes đã cài. Một helper bị relocate thành package khác nhưng V2 vẫn gọi tên cũ cũng cho lỗi tương tự.

### Bước 3 — Định danh đúng defining loader

Ghi trong code chẩn đoán:

~~~java
ClassLoader loader = service.getClassLoader();
System.out.println(loader);
~~~

Đây là **trích đoạn**, cần biến `service` là `Class<?>` phù hợp. Với custom loader, log identity không chỉ tên class loader type. Tên `URLClassLoader` lặp lại ở nhiều instances không chứng minh chúng là cùng loader.

### Bước 4 — So sánh visibility qua các loaders

Trong môi trường có quyền chẩn đoán:

~~~java
Class.forName("lab.helper.Probe", false, system);
Class.forName("lab.helper.Probe", false, child);
~~~

Các dòng là **ví dụ để chạy riêng khi debug**, exception có thể được xử lý phù hợp. Nếu system thấy helper mà child không thấy, điều tra delegation parent và URL/JAR search path của child.

Chú ý: `Class.forName` tường minh có thể gây thêm class loading; không dùng nó như profiler quét tràn lan trên production. Và việc tìm được class không luôn chứng minh method access hợp lệ trong named modules.

### Bước 5 — Xem context loader nhưng không suy diễn

Ghi `Thread.currentThread().getContextClassLoader()` như dữ liệu bổ sung; không giả định nó là loader được JVM dùng để resolve mọi symbolic reference trong bytes của target.

### Bước 6 — Chọn cách sửa phù hợp

- Helper là public shared API: bố trí tại ancestor loader nhất quán, cho target loader delegate tới đó.
- Helper là plugin-local implementation: thêm helper cùng dependency closure vào loader của plugin.
- Target thuộc bootstrap: có thể cần helper JAR tối giản bootstrap-visible, với kiểm thử cẩn trọng.
- Named modules: giải quyết thêm module reads/exports phù hợp, không lẫn class lookup với access.
- Nhiều agents: tránh shading/package conflicts và duplicate helpers giữa loaders.

### Bước 7 — Test lại hành vi, không chỉ nhìn hết exception

Phải nhìn thấy **probe thực sự chạy**, method trả kết quả đúng, không có classloader leak, version conflict hoặc lỗi ở nhánh exception khác. Trong lab, hai dòng `probe:hit` và `app:result=instrumented` chứng minh cả helper invocation lẫn method return đều thành công.

## 17. Các lỗi phổ biến và nguyên nhân thực

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| `app:system-helper-visible=true` nhưng `child-helper-visible=false` | Loader của target có parent null hoặc không delegate tới system |
| `app:context-is-system=true` nhưng `NoClassDefFoundError` | TCCL không tự thay loader resolution của bytecode |
| `NoClassDefFoundError: lab/helper/Probe` khi invoke | Child không thấy helper, binary name mismatch hoặc helper initialization có lỗi |
| `ClassNotFoundException` trong probe `Class.forName` | Loader đang thử không tìm được class theo tên |
| `InvocationTargetException` khi gọi qua reflection | Đọc `getCause()` để thấy root cause thực |
| `ClassFormatError` khi Service được define | Replacement bytes sai format, không phải loader không thấy helper ở invocation |
| `VerifyError` | Stack maps/frames/instructions sai; kiểm tra output bytecode |
| `IllegalAccessError` | Runtime package, module exports hoặc visibility/member access |
| `NoSuchMethodError` | Helper class có nhưng version/descriptor khác |
| `ClassCastException` sau fix local | Duplicate class identity giữa loaders khi chia sẻ interface/DTO |
| `probe:hit` không xuất hiện dù không lỗi | V2 có thật được cài? Probe có nằm trong đường thực thi? |
| Fix delegated làm `service-defined-by-child=false` | System loader đang định nghĩa Service cùng tên trước child |
| Helper có thư viện phụ nhưng vẫn lỗi | Dependency closure của helper chưa visible |
| Copy helper vào agent JAR nhưng target vẫn lỗi | Agent JAR loader không nằm trong delegation graph của target |
| App chạy không agent nhưng lỗi khi có agent | Bytecode V2 đưa vào symbolic reference mới cần resolve |
| Gọi `appendToSystemClassLoaderSearch` mà child vẫn lỗi | Parent-null child không delegate lên system |
| Đổi TCCL nhưng không giải quyết | Symbolic reference dùng defining loader của Service, không TCCL |
| Re-run test cùng JVM, class không biến đổi lại | Class đã load; load-time transformer không tự redefine lại class |
| Class loader không unload sau thí nghiệm | Strong references tới Class/loader, threads, caches hoặc helper state |

### 17.1. Không được chỉnh class loader tùy tiện trong hệ thống thật

Đổi parent của một plugin loader có thể làm nhiều type từ application trở nên visible, thay đổi **class identity**, version resolution và security boundary. Phải thử tích hợp cả plugin APIs, DTO classes, serialization và service providers. Nếu không thể đổi loader hierarchy, phương án local helper hoặc một bridge/interface chung có thể phù hợp hơn.

### 17.2. Reflection chỉ là phương tiện demo

Ứng dụng dùng reflection để nạp `lab.target.Service` mà không đưa Service lên system classpath. Điều đó giữ được điều kiện cần cho experiment. Trong ứng dụng thật, target có thể được nạp qua plugin framework, servlet container, OSGi hoặc module layer; phải kiểm tra **actual defining loader** của target. Không copy test reflection vào production nếu hệ thống đã có cơ chế lifecycle/plugin loading rõ ràng.

## 18. Bài tập và câu hỏi tự đánh giá

### Bài A — dự đoán lỗi trước khi chạy

System classpath có `Probe`, child loader `parent=null` và chỉ biết `Service.class`. Bytecode V2 gọi `Probe.mark()`. Khi method chạy, điều gì xảy ra?

**Đáp án:** child không tìm được Probe theo graph của nó, method có thể ném `NoClassDefFoundError`. System/TCCL thấy helper không đủ.

### Bài B — phân biệt lỗi classfile và lỗi linkage

Ở mode isolated với agent, chương trình in `app:service-defined-by-child=true` rồi `app:invoke-cause=NoClassDefFoundError`. Điều đó nói gì về việc cài V2?

**Đáp án:** Service đã được định nghĩa thành công trên JVM thử nghiệm; lỗi phát sinh khi thực thi lời gọi helper. Đây không phải `ClassFormatError` trong class definition.

### Bài C — sửa bằng delegation

Đổi parent của child từ `null` thành `ClassLoader.getSystemClassLoader()`. Vì sao Service vẫn do child định nghĩa mà Probe lại do parent có thể cung cấp?

**Đáp án:** Service chỉ nằm trong URL của child; Probe nằm trong search path của parent. Parent-first lookup thất bại cho Service nên child define, nhưng thành công cho Probe.

### Bài D — sửa bằng local URL

Giữ parent null, thêm URL của helper vào child. Vì sao chạy thành công? Có nguy cơ tạo hai class `lab.helper.Probe` cùng tên trong JVM không?

**Đáp án:** child tự tìm thấy helper trong URL search path; có thể có một bản do system và một bản do child định nghĩa, khác class identity.

### Bài E — TCCL không phải giải pháp mặc định

Đổi TCCL thành system khi mode isolated (trong lab vốn đã là system). Vì sao không chữa lỗi?

**Đáp án:** symbolic reference của Service V2 phân giải theo defining loader của Service, không tự động theo thread context loader.

### Bài F — kiểm tra helper bằng hai Class.forName

Vì sao `Class.forName("lab.helper.Probe", false, system)` trả về class nhưng cùng call với `child` lại ném `ClassNotFoundException`?

**Đáp án:** hai loaders có search paths/delegation graph khác nhau; global JVM không có một class namespace duy nhất.

### Bài G — thay package helper

Biên dịch V2 gọi `lab.helper.Probe`, nhưng deploy helper với binary name `lab.runtime.Probe`. Đưa JAR vào system có giải quyết được không?

**Đáp án:** không; phải khớp binary class name và method descriptor, hoặc rebuild/transform bytes V2 tương ứng.

### Bài H — helper gọi một API chỉ có ở system

Bạn dùng fix local, helper của child lại tham chiếu tới class của application system loader. Rủi ro gì?

**Đáp án:** helper do child định nghĩa cũng có thể không nhìn thấy dependency đó; phải thiết kế dependency closure và shared API boundary, không chỉ chép một file.

### Bài I — named module access

Một loader thấy helper, nhưng target vẫn báo `IllegalAccessError` do package không exported. Thêm helper vào URL có chắc chữa được không?

**Đáp án:** không; cần giải quyết module reads/exports/access đúng cách.

### Bài J — bootstrap helper

Khi instrument class bootstrap, vì sao copy helper vào system JAR không bảo đảm bootstrap class nhìn thấy helper? Khi nào cần cân nhắc `appendToBootstrapClassLoaderSearch`?

**Đáp án:** bootstrap không delegate xuống system; helper có thể phải nằm trong bootstrap-visible minimal JAR. Phải kiểm soát dependency/namespace và test riêng.

### Câu hỏi nhanh

1. **Defining class loader của một class lấy bằng gì?** — `clazz.getClassLoader()`.
2. **`parent=null` của URLClassLoader có tự tìm system classpath không?** — Không.
3. **Helper có trên system classpath nghĩa child chắc chắn tìm được không?** — Không.
4. **TCCL có tự giải quyết `invokestatic` của target không?** — Không.
5. **Lỗi gốc trong reflection wrapper đọc ở đâu?** — `InvocationTargetException.getCause()`.
6. **V2 đã define nhưng thiếu helper khi invoke có thể gây gì?** — `NoClassDefFoundError`.
7. **Fix A thay gì?** — Parent delegation tới loader có helper.
8. **Fix B thay gì?** — URLs/class search path của chính child loader.
9. **Fix local có thể tạo duplicate class identity không?** — Có.
10. **`appendToSystemClassLoaderSearch` tự chữa parent-null child không?** — Không.
11. **`appendToBootstrapClassLoaderSearch` có cần cho lab chính không?** — Không.
12. **Một callback transform đã log có đủ chứng minh class đã define không?** — Không.
13. **`-Xverify:all` đảm bảo mọi helper sẽ visible không?** — Không, linkage/runtime vẫn phải kiểm thử.
14. **Có thể tự do đổi schema của loaded class qua transformer không?** — Không; cần capabilities và tuân thủ VM restrictions.
15. **Tiêu chí xác nhận fix trong bài?** — Có `probe:hit`, `app:result=instrumented` và no linkage error.

## 19. Checklist release và tài liệu chính thức

### Trước khi thử lỗi trong sandbox

- [ ] Agent thật được khởi chạy bằng `-javaagent` và đúng `Premain-Class`.
- [ ] `Service` V1 và V2 có cùng binary name nhưng compile riêng.
- [ ] V2 chỉ thêm lời gọi helper public, cùng method signature.
- [ ] `Probe` được build tại `out/helper` và system loader thấy nó.
- [ ] `Service.class` không nằm trên system classpath để child thực sự define target.
- [ ] Code ghi mốc `service-defined-by-child` trước `work()`.
- [ ] Có catch `InvocationTargetException` trong lab để thấy root cause.
- [ ] Chạy baseline **không agent** và lưu output.
- [ ] Chạy lỗi isolated với agent để tái hiện `NoClassDefFoundError`.
- [ ] Chạy fix delegated và xác nhận `probe:hit`.
- [ ] Chạy fix local và xác nhận `probe:hit`.
- [ ] So sánh rõ **đường visibility helper**, không đổi Java business code giữa các fixes.

### Khi chọn giải pháp ở production

- [ ] Vẽ class loader graph thực tế, gồm target defining loader và loader sở hữu helper.
- [ ] Quyết định helper là shared API hay implementation local.
- [ ] Kiểm tra helper dependency closure, versions và shading/relocation.
- [ ] Cân nhắc class identity nếu cùng binary name được nhiều loaders định nghĩa.
- [ ] Nếu target ở named module, xác minh reads/exports/opens và access.
- [ ] Tránh helper bootstrap không cần thiết; nếu có, chỉ dùng JAR tối giản và test riêng.
- [ ] Kiểm tra rollback nếu class đang chạy đã được instrument.
- [ ] Thử các code paths, exception paths và async threads.
- [ ] Không nuốt lỗi linkage ở production mà không có chính sách fail-open/fail-fast.
- [ ] Đo chi phí startup/transform/lookup/GC, không giả định instrumentation miễn phí.
- [ ] Không mở rộng quyền class loader/module quá mức cần thiết.

**Kết luận:** khi Java agent chèn lời gọi tới helper, **helper phải visible từ góc nhìn class loader dùng để định nghĩa target**. Đưa helper lên system classpath chỉ là một nửa câu chuyện. Tình huống `URLClassLoader(parent=null)` minh họa được lỗi rất thật: JVM define Service V2 thành công nhưng không resolve được Probe khi method chạy. Hai cách sửa đã được kiểm thử: **delegate tới system** nếu helper là shared dependency, hoặc **thêm helper vào search path của child** nếu cần isolation. Hãy xác định loader graph, class identity và module access trước khi đổi bytecode hay thêm launcher flags.

### Nguồn chính thức

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation model, parent-null và system/platform/bootstrap loaders.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search path và parent constructor.
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()): defining loader identity.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, bootstrap/system loader JAR search append và retransform/redefine capability.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer callback và classfile output rules.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, helper bootstrap constraints.
- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): `InvocationTargetException` và cause.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity, loader constraints, resolution và linkage.
