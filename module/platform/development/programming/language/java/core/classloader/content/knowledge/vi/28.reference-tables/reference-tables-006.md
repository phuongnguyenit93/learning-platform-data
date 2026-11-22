# Tra cứu JVMS, JLS, Javadoc và công cụ JDK theo chủ đề Java ClassLoader

## 1. Mục tiêu: tìm đúng nguồn trước khi giải thích lỗi

Khi nghiên cứu **ClassLoader**, nhiều câu hỏi nhìn giống nhau nhưng thuộc những tầng khác nhau của Java:

- `ClassLoader.loadClass` tìm lớp theo thứ tự nào?
- Vì sao hai class cùng tên không cast được cho nhau?
- Khi nào static initializer được chạy?
- Vì sao `NoSuchMethodError` xuất hiện dù mã nguồn biên dịch thành công?
- `getResourceAsStream` tìm file trong JAR theo tên nào?
- Vì sao module thấy được class nhưng reflection vào private member bị cấm?
- Dùng lệnh nào để kiểm tra classfile, dependency graph hoặc loaded classes thực tế?

Không nên giải tất cả bằng một bài blog hay một lệnh `javap` duy nhất. Để xác định đúng nguyên nhân, cần kết hợp **đặc tả (specification)**, **hợp đồng API**, **công cụ JDK** và **bằng chứng từ runtime**.

Bài này là một **bản đồ tra cứu** dành cho Java 17+ với trọng tâm class loading: cách chọn **JVMS**, **JLS**, **Javadoc**, **JDK tool manuals**, bảng tra theo chủ đề/triệu chứng, một ví dụ có thể tự chạy và một quy trình điều tra tái lập được.

> Nguyên tắc thực hành: **Xác định câu hỏi thuộc tầng nào → đọc nguồn chuẩn của tầng đó → dùng công cụ quan sát artifact/runtime → viết kết luận có điều kiện.** Đừng suy ngược toàn bộ ngữ nghĩa Java từ một dòng log trên một JVM cụ thể.

## 2. Phân biệt bốn nhóm nguồn

| Nguồn | Trả lời tốt nhất về | Ví dụ câu hỏi |
| --- | --- | --- |
| **JVMS — Java Virtual Machine Specification** | Classfile format, bytecode, loading/linking/resolution/initialization ở JVM, runtime class identity, access checks, VM errors | “Tại sao loader khác nhau tạo kiểu runtime khác nhau?”, “`VerifyError` xảy ra ở bước nào?” |
| **JLS — Java Language Specification** | Quy tắc của **ngôn ngữ Java**: tên, scope, access modifiers, initialization observable, source/binary compatibility | “Khi source dùng static field thì class được initialized thế nào?”, “Sửa `public` có ảnh hưởng binary compatibility không?” |
| **Javadoc — Java SE API Documentation** | Hợp đồng của các class/method chuẩn như `ClassLoader`, `Class`, `ModuleLayer`, `ServiceLoader`, `Proxy` | “`loadClass` có gọi `findLoadedClass` rồi parent không?”, “`getResourceAsStream` trả gì nếu resource thiếu?” |
| **JDK Tool Reference / man pages** | Cú pháp và khả năng của công cụ: `java`, `javap`, `jar`, `jdeps`, `jcmd`, `jfr`, `jlink` | “Lệnh nào hiển thị constant pool?”, “Làm sao bật log class loading?” |

Nguồn bổ sung thường gặp:

- **JEP (JDK Enhancement Proposal):** giải thích động lực, thiết kế và lộ trình của một tính năng; rất hữu ích để hiểu *vì sao* module system, CDS hoặc thay đổi JVM xuất hiện, nhưng **không thay** hợp đồng của Javadoc hoặc đặc tả phiên bản đang chạy.
- **Migration guides / troubleshooting guides:** hướng dẫn upgrade JDK, chuyển classpath sang module path, xử lý illegal reflective access; có ích cho tình huống cụ thể nhưng cần đối chiếu với API/spec.
- **Source code OpenJDK:** cung cấp cách *một bản implementation* triển khai, không mặc nhiên là hành vi bắt buộc trên mọi JVM tương thích Java.
- **Stack trace, `javap`, JFR, Unified Logging:** bằng chứng của *ứng dụng đang chạy*; chúng cần được diễn giải dưới các quy tắc của spec/API.

### 2.1. Không trộn “nguồn quy phạm” với “bằng chứng runtime”

Ví dụ một HotSpot build dùng application loader có tên hiển thị nội bộ cụ thể. Javadoc `ClassLoader` quy định cách lấy **defining loader** qua `Class.getClassLoader()`, còn tên class cụ thể của loader do HotSpot triển khai có thể khác theo JDK/distribution. Vì vậy:

~~~text
Thông tin có thể khẳng định:
  two Class<?> objects with same binary name + different defining loaders
  may represent different runtime types.

Không nên khẳng định cho mọi JVM:
  application loader luôn có cùng tên class implementation nội bộ
  hoặc class-loading log luôn có cùng thứ tự và wording.
~~~

Khi viết README/bug report, hãy ghi **Java SE version**, JVM vendor/build, classpath/module path và lệnh quan sát. Khi có xung đột apparent, xác định đang so **source-level language rule**, **bytecode runtime rule**, **API behavior** hay **implementation diagnostic output**.

## 3. Lộ trình đọc JVMS khi học ClassLoader

**Trang gốc Java SE 17:** https://docs.oracle.com/javase/specs/jvms/se17/html/index.html

| Đề tài | Mục JVMS nên mở | Điều cần tìm |
| --- | --- | --- |
| Định danh lớp runtime và defining/initiating loaders | **`5.3 Creation and Loading`** | Cặp (binary name, defining loader); delegation |
| Bootstrap loader, user-defined loader, arrays | **`5.3.1–5.3.3`** | Ai thực sự define Class, đặc thù array class |
| Loader constraints | **`5.3.4`** | Tính thống nhất kiểu khi loaders tương tác qua signatures |
| Tạo Class từ bytes / classfile | **`5.3.5`** và **Chapter 4** | Structural/classfile format constraints |
| Modules/layers khi tải classes | **`5.3.6`** | Tương tác giữa module, package và loaders |
| Linking tổng quát | **`5.4`** | Verification, preparation, resolution, access |
| Bytecode verification | **`5.4.1`**, **`4.9–4.10`** | `VerifyError` và type-state checks |
| Preparation và static field values | **`5.4.2`** | Chuẩn bị field trước `<clinit>` |
| Class, field, method resolution | **`5.4.3.1–5.4.3.4`** | Vì sao có `NoSuchMethodError`, `NoSuchFieldError` |
| Access control của JVM | **`5.4.4`** | `IllegalAccessError`, module/package access |
| Method selection / overriding | **`5.4.5–5.4.6`** | Dispatch và inheritance ở runtime |
| Initialization | **`5.5`** và **`2.9.2`** | `<clinit>`, thứ tự, locks, error state |
| Bytecode syntax và operands | **Chapter 6** | `getstatic`, `putstatic`, `invokestatic`, `new` |
| Runtime data areas | **`2.5`** | Method area, heap, stacks, constant pool |

Các URL trực tiếp có thể lưu trong bookmark:

- Loading: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Loading constraints: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- Linking: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- Resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3
- Access control: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- Initialization: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Class file format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Instructions: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

### 3.1. Cách đọc một mục JVMS cho đúng

Thực hiện theo trình tự:

1. Đọc **heading và mục ngay trước/sau** để nhận ra điều kiện ban đầu.
2. Ghi rõ đang xem **lớp chưa load**, **đã load**, **đã verified**, **đang resolution** hay **đã initialized**.
3. Phân biệt **defining loader** với **initiating loader**: một loader có thể yêu cầu nạp, rồi ủy quyền cho parent thực sự define.
4. Ghi nguyên tắc **runtime class identity**: binary name và defining loader; hai loader khác nhau không nhất thiết tạo hai Class khác nhau nếu chúng cùng delegate về một parent.
5. Khi gặp từ `may`, `must`, `may be deferred`, không biến quyền lựa chọn của VM implementation thành một thứ tự bắt buộc cho mọi JVM.
6. Tìm câu quy định **exception/error nào xuất hiện khi điều kiện bị vi phạm**.
7. Dùng Javadoc để xác định ý nghĩa cụ thể của lời gọi API mà ứng dụng sử dụng.

**Bẫy điển hình:** đọc `5.4 Resolution` rồi kết luận “mọi symbolic reference đều phải được resolve trước khi first method run”. JVMS cho phép nhiều hoạt động resolution được thực hiện sớm hoặc muộn, miễn error xuất hiện ở điểm sử dụng phù hợp. Cần phân biệt link-time guarantee với JVM implementation strategy.

## 4. Lộ trình đọc JLS khi học class loading

**Trang gốc Java SE 17:** https://docs.oracle.com/javase/specs/jls/se17/html/index.html

| Đề tài nguồn Java | Mục JLS | Câu hỏi gợi ý |
| --- | --- | --- |
| Class/interface loading | **`12.2`** | Khi nào JVM cần tạo class và các điều kiện đúng |
| Linking | **`12.3`** | Liên kết trong vòng đời Java program |
| Initialization | **`12.4`** | Điều gì làm static initialization xảy ra |
| Instance creation | **`12.5`** | Constructor và initialization instance |
| Class unloading | **`12.7`** | Khi nào class có thể unload |
| Scope/naming và qualified names | **Chapters 6–7** | Binary names, packages, access |
| Access control | **`6.6`** | `public`, `protected`, package-private, private |
| Module declarations | **`7.7`** | `requires`, `exports`, `opens`, `uses`, `provides` |
| Class members/methods | **Chapters 8–9** | `static`, `final`, overriding, interfaces |
| Binary compatibility | **Chapter 13** | Vì sao client đã compile vẫn lỗi khi đổi thư viện |
| Memory model | **`17.4`** | Happens-before; tránh gán nhầm concurrency bug cho verifier |

Liên kết trực tiếp:

- Loading: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- Unloading: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- Access: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6
- Modules: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7
- Binary compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html

### 4.1. Lúc nào đọc cả JLS và JVMS?

Ví dụ **class initialization**:

- JLS `12.4` giải thích Java-language semantics, triggers và những gì programmer có thể quan sát.
- JVMS `5.5` diễn tả quy trình JVM, locks và trạng thái khởi tạo, cùng những instruction chủ yếu gây yêu cầu initialization.
- Javadoc `Class.forName` giải thích một **API call cụ thể** với tham số `initialize`.
- `javap -c` cho thấy bytecode compiler tạo; JFR/logs cho biết một process thực sự đã trải qua điều gì.

Mỗi nguồn giải thích **một chiều của cùng hiện tượng**. Không nên đọc duy nhất `Class.forName` Javadoc rồi khẳng định mọi `.class` literal hoặc `loadClass` tự động chạy `<clinit>`.

## 5. Tra Javadoc theo API và triệu chứng

**Java SE 17 API index:** https://docs.oracle.com/en/java/javase/17/docs/api/index.html

| API / loại | Vấn đề gắn với ClassLoader | Trang Javadoc |
| --- | --- | --- |
| `java.lang.ClassLoader` | Parent delegation, `loadClass`, `findClass`, `defineClass`, resources, parallel-capable | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html |
| `java.lang.Class` | `forName`, `getClassLoader`, `getModule`, reflection và init | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html |
| `java.lang.Module` | Module identity, `isExported`, `isOpen`, `getResourceAsStream` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html |
| `java.lang.ModuleLayer` | Tạo layer mới và chọn loader mapping | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html |
| `java.lang.module.Configuration` | Module resolution và readability graph | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html |
| `java.lang.module.ModuleFinder` | Tìm module artifacts | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html |
| `java.util.ServiceLoader` | Provider discovery, `META-INF/services`, service type compatibility | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html |
| `java.util.ServiceConfigurationError` | Invalid provider và các lỗi SPI | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html |
| `java.lang.reflect.Proxy` | Dynamic proxy, interface visibility, JPMS restrictions | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html |
| `java.lang.reflect.InvocationHandler` | Method dispatch, default methods và exceptions | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html |
| `java.lang.reflect.AccessibleObject` | `setAccessible`, `trySetAccessible` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html |
| `java.lang.invoke.MethodHandles.Lookup` | `defineClass`, `defineHiddenClass`, lookup access | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html |
| `java.net.URLClassLoader` | Nạp classes/resources từ các URL roots | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html |
| `java.security.SecureClassLoader` | Code source / protection domains | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureClassLoader.html |
| `java.util.Properties` | Đọc config stream/reader khác encoding | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html |

### 5.1. Cách đọc Javadoc cho khỏi bỏ sót

Khi vào trang `ClassLoader`:

1. Tìm **Method Summary** rồi click đúng overload `loadClass(String)` hoặc `loadClass(String, boolean)`.
2. Đọc **Implementation Requirements** thay vì chỉ một câu mở đầu.
3. Đọc **Parameters**, **Returns**, **Throws** và **API Note**.
4. Kiểm tra `findClass`, `findLoadedClass`, `resolveClass`, `getClassLoadingLock` nếu làm custom loader.
5. Với resource, đọc riêng `ClassLoader.getResource` và `Class.getResource` vì slash đầu và module semantics **không giống nhau**.
6. Với `Class.forName`, phân biệt overload có `initialize=false` với overload mặc định có thể yêu cầu initialization.

**Quy tắc thực hành:** lời giải cho “`getResourceAsStream` trả null vì sao” nên bắt đầu từ Javadoc API đang gọi, sau đó kiểm tra JAR entries/classpath/module access. Đừng bắt đầu bằng JVMS bytecode verification vì đó không phải tầng trực tiếp xử lý lookup resource.

## 6. Tra cứu công cụ JDK: chọn lệnh theo bằng chứng cần thu

| Công cụ | Nên dùng khi | Ví dụ lệnh/mục |
| --- | --- | --- |
| **`java`** | Chạy cùng artifact, xem classpath/module path, bật class-loading logs | `java -cp out/classes lab.Probe`; `-Xlog:class+load=info` |
| **`javac`** | Kiểm tra source compile với target version/contract nào | `javac --release 17 -d out/classes ...` |
| **`javap`** | Xem classfile, descriptors, method opcodes, constant pool, frames | `javap -c -p -classpath out/classes lab.Probe`; `javap -v` |
| **`jar`** | Kiểm tra nội dung JAR, manifest, module descriptor | `jar --list --file app.jar`; `jar --describe-module --file app.jar` |
| **`jdeps`** | Phân tích dependency theo class/package/module, JDK internals | `jdeps --summary app.jar`; `jdeps --jdk-internals app.jar` |
| **`jcmd`** | Quan sát JVM process đang chạy, thống kê class loader, JFR | `jcmd -l`; `jcmd PID VM.classloader_stats` |
| **`jfr`** | Xem recording và events sau khi thu JFR | `jfr print recording.jfr` |
| **`jlink`** | Tạo runtime image gồm một tập modules | `jlink --help`; chọn modules từ graph |
| **`jmod`** | Quan sát/đóng gói JMOD | `jmod --help` |
| **`jshell`** | Thử nhanh Java API/JVM behavior quy mô nhỏ | `jshell` để thử `Class.forName`/reflection |

Các command manuals Java 17:

- java: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- javac: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- javap: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- jar: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- jdeps: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- jcmd: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- jfr: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- jlink: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html

**Một số `jcmd` commands là diagnostic commands phụ thuộc JVM implementation, build, process permissions và phiên bản JDK.** Trước khi dùng với production, xem `jcmd PID help` hoặc help riêng cho command; đừng coi tên internal class loader hay thứ tự bảng thống kê là API portable.

## 7. Sơ đồ nhanh: gặp vấn đề nào, mở trang nào?

~~~text
Triệu chứng / câu hỏi
    |
    +-- "Hai class cùng tên nhưng cast không được"
    |       JVMS 5.3 -> ClassLoader/Class Javadoc
    |       -> in Class.getClassLoader/getModule
    |
    +-- "Lỗi bytecode VerifyError"
    |       JVMS 4.9/4.10 + 5.4.1
    |       -> javap -v -p (Code/StackMapTable)
    |
    +-- "NoSuchMethodError/NoSuchFieldError"
    |       JVMS 5.4.3 + JLS Ch.13
    |       -> javap -c caller, javap -p runtime JAR
    |
    +-- "Static initializer chưa chạy / chạy sớm"
    |       JLS 12.4 + JVMS 5.5 + Class.forName Javadoc
    |       -> thử Class.forName(..., false/true, loader)
    |
    +-- "getResource không thấy file trong JAR"
    |       ClassLoader/Class/Module Javadoc
    |       -> jar --list, in resource URL/loader
    |
    +-- "ServiceLoader provider not a subtype"
    |       ServiceLoader Javadoc + JVMS 5.3
    |       -> so Class identity của service và provider
    |
    +-- "IllegalAccessError / reflection bị chặn"
    |       JVMS 5.4.4 + JLS 6.6 + AccessibleObject Javadoc
    |       -> check exports/opens/modules + javap
    |
    +-- "Split package / ModuleLayer không tạo được"
    |       ModuleLayer/Configuration Javadoc + JLS 7.7
    |       -> jar --describe-module; jdeps --check
    |
    +-- "Startup chậm do class loading?"
            JVMS 5.3/5.5 + ClassLoader Javadoc
            -> java -Xlog:class+load, JFR, startup profiling
~~~

Lưu ý: đây là **điểm bắt đầu** tra cứu, không phải bản xác định nguyên nhân tự động. Ví dụ `ClassCastException` cũng có thể xuất hiện chỉ vì cast logic sai, không có nhiều loaders; `NoSuchMethodError` có thể do binary incompatibility dù classpath chỉ có một loader.

## 8. Bảng tra chi tiết theo triệu chứng thực tế

| Quan sát | Nguồn chuẩn mở trước | Công cụ/bằng chứng | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| `ClassNotFoundException` | ClassLoader Javadoc; JVMS 5.3 | Runtime `-cp`/module path, JAR entries | Đúng binary name, loader scope, resource có trong artifact? |
| `NoClassDefFoundError` | JVMS 5.4–5.5, JLS 12.4 | Full stack trace và cause, init logs | Dependency thiếu, initialization thất bại hay class definition không phù hợp? |
| `ClassCastException` cùng tên | JVMS 5.3, Class.getClassLoader | In cả hai `Class<?>`, loader và module | Cùng binary name nhưng khác defining loader? |
| `VerifyError` | JVMS 4.9–4.10 | `javap -v -p`, transformer output | Operand stack, locals, frames và version hợp lệ? |
| `ClassFormatError` | JVMS Chapter 4 | File bytes, `javap`, build steps | Header/constant pool/attributes sai? |
| `UnsupportedClassVersionError` | ClassLoader Javadoc, JVMS 4.1 | `javap -v` xem major version, `java -version` | Class được biên dịch cho JDK mới hơn runtime? |
| `NoSuchMethodError` | JVMS 5.4.3, JLS 13 | `javap -c` caller, `javap -p` runtime library | Method name, descriptor và version có giống compile-time? |
| `IllegalAccessError` | JVMS 5.4.4, JLS 13 | Caller/target classes, `Module.isExported` | Binary visibility/module access bị đổi? |
| `IllegalAccessException` | Method/Field Javadoc | Reflection callsite và modifiers | Caller có quyền invoke/get mà không suppress checks? |
| `InaccessibleObjectException` | AccessibleObject, Module Javadoc | `isOpen`, `module-info.java`, launcher args | Package có mở cho caller module? |
| `ServiceConfigurationError` | ServiceLoader Javadoc | `META-INF/services`, `jar --list`, loader identity | Provider class có subtype của đúng service Class? |
| `LayerInstantiationException` | ModuleLayer Javadoc | Module names/packages/loader mapping | Overlapping packages, mapping loader hoặc split delegation? |
| `ResolutionException` | Configuration, java.lang.module Javadoc | `jar --describe-module`, module graph | Exports/readability/dependency conflict? |
| Resource trả null | ClassLoader/Class/Module Javadoc | `getResource` URL và `jar --list` | Tên resource, dấu slash, module encapsulation? |
| Class unloading không xảy ra | JLS 12.7, ClassLoader/JFR docs | Loader stats/JFR/heap analysis | Còn reference tới loader/static cache/thread/TCCL? |
| Startup hoặc p99 đầu tiên chậm | JVMS 5.3–5.5, JFR docs | Startup traces, JFR, class logging | Loading hay initialization, I/O, JIT, DI/proxy? |

**Lưu ý khi gặp một Error:** luôn thu **đầy đủ message và cause chain**, binary class names, runtime JDK version, đúng artifact/classloader; việc chỉ đọc tên exception có thể dẫn đến chẩn đoán sai.

## 9. Demo Java 17+ runnable: nối tài liệu với bằng chứng

Demo nhỏ sau tạo một nested class, yêu cầu JVM tìm class nhưng **không yêu cầu initialization**, in loader identity, sau đó thực hiện **active use** khiến static initializer chạy. Chúng ta tiếp tục dùng `javap` và `jar` để đối chiếu bytecode và cách đóng gói.

### 9.1. Cây file

~~~text
lookup-lab/
└── src/
    └── lab/
        └── Probe.java
~~~

### 9.2. File src/lab/Probe.java

~~~java
package lab;

public final class Probe {
    static final class Deferred {
        static {
            System.out.println("Deferred initialized");
        }

        static int number() {
            return 42;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = Probe.class.getClassLoader();

        Class<?> type = Class.forName(
                "lab.Probe$Deferred", false, loader);

        System.out.println("binary name: " + type.getName());
        System.out.println("same loader: "
                + (type.getClassLoader() == loader));
        System.out.println("module named: "
                + type.getModule().isNamed());

        System.out.println("value: " + Deferred.number());
    }
}
~~~

**Tại sao đúng Java 17:** `Class.forName(String, boolean, ClassLoader)` được Javadoc định nghĩa với flag initialization; `Class.getModule` có từ Java 9. Class `Deferred` là nested static class, có binary name `lab.Probe$Deferred` theo JLS/JVMS naming rules.

### 9.3. Biên dịch

Linux/macOS (bash/zsh), từ `lookup-lab`:

~~~bash
mkdir -p out/classes
javac --release 17 -d out/classes src/lab/Probe.java
java -cp out/classes lab.Probe
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/classes | Out-Null
javac --release 17 -d out/classes src/lab/Probe.java
java -cp out/classes lab.Probe
~~~

**Stdout chính xác trong demo classpath này:**

~~~text
binary name: lab.Probe$Deferred
same loader: true
module named: false
Deferred initialized
value: 42
~~~

Giải thích:

1. `Class.forName("lab.Probe$Deferred", false, loader)` yêu cầu tìm Class nhưng **không yêu cầu chạy `<clinit>`** của `Deferred`; vì vậy dòng initialization chưa xuất hiện.
2. `type.getName()` in **binary name** với ký tự `$` đối với nested class.
3. `Probe` và `Deferred` được định nghĩa bởi loader từ cùng application classpath root; `same loader: true`.
4. Chúng nằm trong **unnamed module** khi chạy bằng `-cp`, vì thế `module named: false`.
5. Lời gọi `Deferred.number()` là active use, buộc initialization trước khi chạy method body. Thứ tự hai dòng cuối phản ánh điều đó.

**Không nhầm:** kết quả trên chứng minh API không yêu cầu initialization ở bước lookup; không chứng minh JVM không làm bất cứ loại class loading/linking nào trước đó. Thứ tự class-loading events trong VM log có thể khác.

## 10. Dùng javap để xem JVM thực sự nhận instruction nào

Sau khi compile `Probe`, chạy:

~~~bash
javap -classpath out/classes -c -p lab.Probe
~~~

Mục cần tìm trong output:

- `public static void main(java.lang.String[])`.
- Một lời gọi `java/lang/Class.forName` với descriptor có hai tham số bổ sung: `boolean` và `ClassLoader`.
- Một lời gọi `lab/Probe$Deferred.number:()I`.
- Instructions liên quan `getstatic java/lang/System.out`, `invokevirtual java/io/PrintStream.println`.

Để xem metadata chi tiết:

~~~bash
javap -classpath out/classes -v -p lab.Probe
~~~

Đây là công cụ quan sát **classfile**, cung cấp constant pool, major version, method descriptors, `Code` attributes, line tables và (khi có) `StackMapTable`.

**Không nên sao chép nguyên output dài của `javap -v` thành “kết quả bất biến”:** offsets, constant pool indexes và bootstrap entries phụ thuộc compiler/build. Hãy dùng nó để so phương thức, opcode, descriptor thực của artifact cụ thể.

### 10.1. Xem nested class đúng cách

Với bash, zsh hoặc PowerShell, đặt binary name có `$` vào dấu nháy **đơn** để shell không diễn giải ký tự:

~~~bash
javap -classpath out/classes -c -p 'lab.Probe$Deferred'
~~~

Trong một số môi trường khác như Windows CMD, quoting rules khác; bạn có thể chỉ định đường dẫn file class đã được tạo hoặc escape tên theo shell thực tế. Khi thấy output static initializer `static {};` hoặc `<clinit>`, liên hệ với JLS `12.4` và JVMS `5.5` thay vì đoán từ Java source.

## 11. Dùng jar để xác nhận artifact có đúng classfile không

Từ thư mục `lookup-lab`:

~~~bash
jar --create --file out/probe.jar -C out/classes .
jar --list --file out/probe.jar
java -cp out/probe.jar lab.Probe
~~~

**Lưu ý:** JAR trên **không** thiết lập `Main-Class` trong manifest, nên lệnh đúng ở đây là `java -cp out/probe.jar lab.Probe`, **không phải** `java -jar out/probe.jar`.

Trong kết quả `jar --list` sẽ có ít nhất:

~~~text
lab/Probe.class
lab/Probe$Deferred.class
~~~

JAR có thể có thêm entries như `META-INF/` và thứ tự output có thể khác; không yêu cầu output chỉ gồm hai dòng trên.

`java -cp out/probe.jar lab.Probe` sẽ có **cùng stdout năm dòng của mục 9.3**, vì class và nested class đều nằm đúng JAR root. Lệnh `jar --list` chứng minh artifact có entries, **không tự chứng minh** application runtime đã nạp class từ chính JAR đó nếu classpath có nhiều root trùng tên. Muốn điều tra runtime origin, kết hợp class-loading log và inspection của loader/Class.

### 11.1. Nhìn module descriptor

Với một JAR có `module-info.class` hoặc automatic module, thử:

~~~bash
jar --describe-module --file some-library.jar
~~~

**Đây là lệnh mẫu**, yêu cầu JAR thực tế. Nếu artifact là automatic module, công cụ có thể cho biết derived module name; nếu không phải modular JAR, đọc output theo semantics của tool. Đừng giả định mọi JAR có explicit `module-info.java`.

## 12. Dùng jdeps để xem dependencies thay vì suy từ imports

Với `out/probe.jar` vừa build:

~~~bash
jdeps --summary out/probe.jar
~~~

Mục đích là xem dependency ở mức module/archive. Với demo chỉ dùng APIs chuẩn, kết quả cần xem dependency tới **java.base**; cách trình bày đường dẫn, tên archive và wording là do công cụ định dạng, không phải transcript cố định.

Các lệnh hữu ích khác khi có artifact thật:

~~~bash
jdeps --verbose:class app.jar
jdeps --jdk-internals app.jar
jdeps --list-deps app.jar
~~~

- `--verbose:class`: class-level dependency edges trong phạm vi analyzer quan sát.
- `--jdk-internals`: tìm tham chiếu tới **JDK internal APIs**, hữu ích khi nâng JDK.
- `--list-deps`: liệt kê module dependencies theo kết quả phân tích.

Với multi-release JAR, dùng `--multi-release 17` khi cần phân tích view phù hợp target JDK:

~~~bash
jdeps --multi-release 17 --summary multi-release-app.jar
~~~

Nếu đang kiểm tra named module có tên xác định trên module path:

~~~bash
jdeps --module-path mods --check module.name
~~~

Hai lệnh cuối là **mẫu**: chúng yêu cầu file `multi-release-app.jar`, thư mục `mods` hoặc `module.name` thực sự tồn tại. Không dùng trực tiếp với `out/probe.jar` ở trên để kiểm tra `module.name`, vì demo chạy trên classpath và không có explicit module descriptor.

**Giới hạn:** `jdeps` là **static dependency analysis**. Nó không tự biết tên class được ghép từ chuỗi rồi nạp bằng reflection hay plugin metadata, cũng không thay việc kiểm tra actual runtime `ClassLoader`, `ServiceLoader` và module resolution graph.

## 13. Quan sát class loading trong một JVM process

### 13.1. Unified Logging

OpenJDK/HotSpot Java 17+ hỗ trợ:

~~~bash
java -Xlog:class+load=info -cp out/classes lab.Probe
~~~

Các log lines có thể cho biết class nào được load và nguồn classfile. Do JVM cũng load rất nhiều Java core classes, output rất dài. **Không có stdout cố định** cho lệnh có logging này; chỉ năm dòng do `Probe` tự in mới có thứ tự dự kiến như mục 9.3, và logs có thể xen vào stdout/stderr.

Khi điều tra unloading:

~~~bash
java -Xlog:class+unload=info -cp out/classes lab.Probe
~~~

Không kỳ vọng sẽ **thấy unload event** trong demo ngắn: Class có thể không unload trước process exit hoặc không đủ điều kiện unload. Không có event không chứng minh class unloading bị tắt.

Một số bản HotSpot hỗ trợ các logging levels/tags bổ sung. Hãy kiểm tra `java -Xlog:help` trên chính runtime để biết tag combinations mà build của bạn cho phép; JDK tool manual là nguồn cú pháp, kết quả thực tế là bằng chứng configuration.

### 13.2. jcmd: quan sát JVM đang chạy

Đầu tiên:

~~~bash
jcmd -l
~~~

Lệnh thường hiển thị các Java processes có thể attach theo quyền OS. Chọn **PID của tiến trình thực cần kiểm tra**, sau đó:

~~~text
jcmd PID help
jcmd PID VM.classloader_stats
jcmd PID VM.class_hierarchy
~~~

Các dòng trên là **template**, chữ `PID` phải được thay bằng **số process ID thật**; không phải command có thể chạy đúng nguyên văn. `VM.classloader_stats` cho thống kê class loaders, `VM.class_hierarchy` cho class hierarchy theo chẩn đoán HotSpot. Một số command có impact và permission requirements; tham khảo `jcmd PID help COMMAND` trong cùng JDK version.

**Không nhầm giữa loader có thể “find/load” một class và loader đã “define” class đó.** Với parent delegation, một application/plugin loader có thể yêu cầu class nhưng parent mới là defining loader. Nếu cần chẩn đoán identity, in `clazz.getClassLoader()` trong code với hai `Class<?>` cụ thể.

### 13.3. JFR cho startup/performance

JFR có thể thu thông tin liên quan loading, allocations, CPU và nhiều events khác theo cấu hình, nhưng **không mặc định mọi event đều bật với cùng độ chi tiết**.

Ví dụ kích hoạt recording từ lúc chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording=filename=out/startup.jfr,settings=profile -cp out/classes lab.Probe
~~~

Sau đó xem recording:

~~~bash
jfr summary out/startup.jfr
jfr print out/startup.jfr
~~~

Với tiến trình quá ngắn, hãy xác minh file recording có thực và chứa events mong muốn; startup trigger, duration và JVM build có thể ảnh hưởng. Để phân tích class-loading events cụ thể, điều chỉnh event settings có kiểm soát thay vì kết luận “JFR không thấy nên class không load”.

## 14. Thực hành tra cứu theo từng ca lỗi

### 14.1. Ca A: ClassCastException “A cannot be cast to A”

**Triệu chứng:** cast một plugin object thành interface phía host thất bại mặc dù tên interface trong source giống nhau.

**Nguồn:** JVMS `5.3` (identity của runtime class là binary name + defining loader); Javadoc `Class.getClassLoader`, `Class.isAssignableFrom`.

**Thu thập bằng chứng:**

~~~java
Class<?> hostApi = HostApi.class;
Class<?> pluginApi = pluginLoader.loadClass(
        HostApi.class.getName());

System.out.println(hostApi == pluginApi);
System.out.println(hostApi.getClassLoader());
System.out.println(pluginApi.getClassLoader());
~~~

**Mã minh họa**, cần có `HostApi` và `pluginLoader`. Nếu `hostApi == pluginApi` false, plugin có thể đang define bản API riêng. Nếu true, cần điều tra cast target/object thực sự chứ không kết luận lỗi vì loader.

**Cách sửa:** chia sẻ interface/DTO/exception/annotation contract qua common parent loader/module, để private implementation classes ở plugin loader.

### 14.2. Ca B: NoSuchMethodError chỉ ở production

**Nguồn:** JVMS `5.4.3` resolution; JLS Chapter 13 binary compatibility; Javadoc method API nếu đó là Java library.

**Bằng chứng:**

~~~bash
javap -classpath compiled-client.jar -c -p client.Main
javap -classpath deployed-library.jar -p api.Library
jar --list --file deployed-library.jar
~~~

**Lệnh mẫu**, cần artifact thật. Xác định method name và descriptor mà client bytecode tham chiếu, đối chiếu với runtime library class. Có thể method bị đổi parameter, return type, static/instance form hoặc artifact deployment sai version.

**Cách sửa:** thống nhất compile/runtime dependency versions và test đúng packaged artifact. Không dùng `Class.forName` để “chữa” một symbolic method reference không còn hợp lệ.

### 14.3. Ca C: Resource tồn tại nhưng getResourceAsStream trả null

**Nguồn:** Javadoc `ClassLoader.getResourceAsStream`, `Class.getResource`, `Module.getResourceAsStream`.

**Bằng chứng:**

~~~bash
jar --list --file application.jar
~~~

và trong code:

~~~java
URL url = loader.getResource("config/app.properties");
System.out.println(url);
~~~

**Mã minh họa**, loader phải được khởi tạo. Kiểm tra tên entry `config/app.properties` đúng classpath root, slash đầu khác nhau giữa `Class` và `ClassLoader` APIs, loader lookup scope và JPMS resource encapsulation.

**Cách sửa:** đóng resources đúng root, chọn API/loader đúng, ưu tiên `getResourceAsStream` cho bytes trong JAR thay vì ép JAR URL thành `File`.

### 14.4. Ca D: VerifyError sau bytecode weaving

**Nguồn:** JVMS `4.9–4.10` và `5.4.1`.

**Bằng chứng:**

~~~bash
javap -classpath transformed.jar -v -p app.Transformed
~~~

Kiểm tra `Code` attributes, `max_stack`/`max_locals`, `StackMapTable` và classfile major version. Dùng **transformed artifact thực** làm đầu vào, không chỉ xem source trước weaving. `VerifyError` không phải chứng cứ rằng ứng dụng đã thử chạy mọi execution path và thấy logic sai.

### 14.5. Ca E: Split package/layer creation failure

**Nguồn:** Javadoc `Configuration`/`ModuleLayer` và JLS `7.7`.

**Bằng chứng:** list module descriptors/packages và phân biệt **module resolution** với **ModuleLayer definition**. `defineModulesWithOneLoader` không thể dùng một loader chứa các modules có package overlap; `defineModulesWithManyLoaders` cho mapping khác nhưng không sửa graph vi phạm exported package readability.

Lệnh hỗ trợ:

~~~bash
jar --describe-module --file library-a.jar
jar --describe-module --file library-b.jar
jdeps --module-path mods --check module.name
~~~

Các tên file/module là **placeholder dạng mẫu**, thay bằng artifacts thật; cần xem errors và graph cụ thể, không khẳng định hai JAR cùng có package trên disk luôn làm JVM fail ngay lập tức.

## 15. Tra cứu “phần nào của Java chịu trách nhiệm?” bằng ba bước

Một mẹo giúp tránh đọc sai nguồn:

### Bước 1 — Xác định đối tượng đang được hỏi

- Java source expression/declaration? → JLS.
- Bytecode opcode, constant pool, classfile verification, runtime identity? → JVMS.
- Method của `ClassLoader`/`Class`/`ServiceLoader`/`Proxy`? → Javadoc.
- Cú pháp `java`, `javap`, `jar`, `jdeps`, `jcmd`? → Tool manual.
- Một hành vi quan sát được trong HotSpot? → Run logs/JFR/source implementation, **sau đó** kiểm tra phần được spec cho phép.

### Bước 2 — Xác định version

Ví dụ: `ClassLoader` từ Java 8 và Java 17 khác nhau về named modules và API bổ sung. Tra cứu phải gắn version:

~~~text
Java SE 17:
  /javase/17/docs/api/
  /specs/jls/se17/
  /specs/jvms/se17/

Java phiên bản khác:
  tra đúng API/spec của phiên bản compiler/runtime dự kiến,
  không trộn một đoạn tutorial Java 8 với JPMS Java 17.
~~~

Với “Java hiện tại” hoặc một sự cố runtime thật, ghi **đúng phiên bản JDK trong dự án**. Ví dụ có thể chạy với JDK 17, không có nghĩa mọi tool output hoặc module access rule giống hệt ở mọi JDK sau đó.

### Bước 3 — Kiểm chứng bằng artifact/runtime thực

- Build lại sạch từ source/dependencies đã khóa.
- Kiểm tra `java -version`, `javac -version`, `java -cp` hoặc `--module-path`.
- `jar --list` để biết có bytes/resources không.
- `javap` để kiểm tra symbolic references/bytecode đã compile.
- `jdeps` cho static dependencies, nhưng đừng dùng nó làm chứng cứ toàn diện cho reflective loading.
- `jcmd`/JFR/logging để quan sát process khi lỗi chỉ xảy ra sau startup.
- In `Class.getName()`, `getClassLoader()`, `getModule()` đối với classes liên quan.

**Không phụ thuộc riêng vào một command:** `jar --list` có thể chứng minh file có trong JAR, nhưng class loader runtime có thể đã lấy một version khác từ parent. Ngược lại, thấy class được load không chứng minh static initializer đã chạy.

## 16. Đọc bản chuẩn bằng bookmark và từ khóa

Một bộ bookmark nhỏ có ích hơn việc ghi nhớ toàn bộ 600 trang spec:

| Bookmark | Từ khóa nên tìm trong trang |
| --- | --- |
| JVMS `5.3` | `defining loader`, `initiating loader`, `run-time package` |
| JVMS `5.4` | `verification`, `preparation`, `resolution`, `access control` |
| JVMS `5.5` | `initialization`, `initialization lock`, `erroneous state` |
| JVMS Chapter 4 | `ClassFile`, `Code`, `StackMapTable` |
| JLS `12.4` | `initialized`, `static`, `constant variable` |
| JLS Chapter 13 | `binary compatibility`, `accessibility` |
| ClassLoader Javadoc | `loadClass`, `findClass`, `getResource`, `parallel capable` |
| Class Javadoc | `forName`, `getClassLoader`, `getModule` |
| ModuleLayer Javadoc | `defineModulesWithOneLoader`, `defineModulesWithManyLoaders` |
| ServiceLoader Javadoc | `provider`, `META-INF/services`, `ServiceConfigurationError` |
| Proxy Javadoc | `newProxyInstance`, `visibility`, `non-public` |
| jcmd manual | `VM.classloader_stats`, `VM.class_hierarchy` |
| java manual | `-Xlog`, `--module-path`, `--add-exports`, `--add-opens` |

Khi đọc Javadoc, dùng tìm kiếm trong trang (`Ctrl+F` / `Cmd+F`) cho **tên method chính xác**. Chú ý các overload có tên giống nhau nhưng khác loader/context hoặc boolean flag. Với `ClassLoader.getResource` và `Class.getResource`, **dấu `/` ở đầu** mang ý nghĩa khác; đừng chép ví dụ API này vào API kia mà bỏ qua Javadoc.

## 17. Ngộ nhận phổ biến khi tra cứu ClassLoader

| Ngộ nhận | Cách kiểm chứng và hiểu đúng |
| --- | --- |
| “JLS và JVMS là hai bản copy của cùng luật” | JLS mô tả language semantics, JVMS mô tả classfile/runtime mechanics |
| “Đọc Javadoc là đủ kết luận mọi opcode JVM” | Method contract phải kết hợp JVMS khi nói về linking/bytecode |
| “Một HotSpot trace là quy tắc chuẩn trên mọi JVM” | Tool logs thường implementation-specific |
| “Hai class cùng binary name là cùng kiểu” | So `Class<?>` và defining loader, xem JVMS `5.3` |
| “loadClass luôn chạy static initializer” | Đối chiếu ClassLoader/Class Javadoc và JLS `12.4` |
| “Class.forName(false) không làm gì” | Có thể yêu cầu loading/linking, nhưng không yêu cầu initialization |
| “javap in đúng source” | Nó in **classfile** đã compile, không khôi phục đầy đủ ý định source |
| “jdeps thấy hết dynamic dependencies” | Reflection, ServiceLoader và computed names có thể không hiện trong static graph |
| “jar --list chứng minh app dùng đúng JAR” | Nó chỉ chứng minh artifact entries, không xác định runtime lookup order |
| “Cần một lệnh để chắc chắn mọi class đã loaded” | Runtime changes over time; tools có scope/permission/impact |
| “Thấy VerifyError nghĩa là logic Java sai” | Đó là bytecode verification issue |
| “NoSuchMethodError là compile error bình thường” | Thường là runtime binary linkage mismatch |
| “exports tương đương opens” | JPMS phân biệt public API access với deep reflection |
| “Tên class loader trong logs là Java SE API contract” | Implementation class names/log formats có thể khác |
| “Nếu không thấy ClassUnload log là JVM không unload” | Cần đủ điều kiện unloading, event/time window và logging |
| “Chỉ cần đổi classpath order sẽ sửa mọi duplicate API” | Cần biết loader graph, parent delegation và module ownership |

## 18. Checklist viết một báo cáo lỗi có thể tái lập

Trước khi nhờ đồng đội hoặc gửi issue cho thư viện/plugin framework, ghi:

1. **Triệu chứng:** exception/error đầy đủ, phần `Caused by` và thao tác gây lỗi.
2. **Runtime:** `java -version`, JDK vendor/build, OS và kiến trúc.
3. **Compile:** `javac --release` hoặc compiler target, dependency versions.
4. **Launch:** command-line arguments `-cp`/`--module-path`, module roots, relevant flags.
5. **Artifact:** chính file JAR/class mà runtime dùng; kết quả `jar --list`/`javap` cần thiết.
6. **Class identity:** cả hai `Class<?>` đang tương tác, `getName`/`getClassLoader`/`getModule`.
7. **Module access:** `requires`, `exports`, `opens`, caller/target modules nếu có.
8. **Resource path:** tên logic, directory/JAR entry và loader đã dùng.
9. **Tool evidence:** lệnh và vài dòng output liên quan, tránh dump hàng nghìn dòng class log không lọc.
10. **Nguồn chuẩn:** mục JVMS/JLS/Javadoc cụ thể, có version và fragment `#...`.
11. **Reproduction:** một project nhỏ đủ lệnh compile/run, nêu expected và actual; không thay code giữa các lần mà không ghi.
12. **Kết luận phân loại:** điều chắc chắn từ evidence, giả thuyết còn thiếu và thí nghiệm tiếp theo.

Khi viện dẫn spec nên ghi như sau:

~~~text
Claim: Hai Class cùng binary name nhưng khác defining ClassLoader
       không nhất thiết là cùng runtime type.
Source: JVMS SE 17 `5.3` — Creation and Loading.
Evidence: hostApi == pluginApi -> false; hai defining loader khác.
Scope: cùng process / classpath+plugin loader setup đã mô tả.
~~~

Ví dụ trên chỉ là **mẫu cách báo cáo**, không phải kết quả của demo `Probe` ở mục 9. Nó minh họa cách tách **quy tắc chuẩn** và **bằng chứng cụ thể**.

## 19. Bài tập tự kiểm tra và câu trả lời

**1. Muốn hiểu danh tính runtime của class, mở nguồn nào trước?**  
JVMS `5.3`; sau đó dùng `Class.getClassLoader()` và `==` trên hai Class runtime.

**2. Muốn biết `ClassLoader.getResourceAsStream` trả gì khi file thiếu?**  
Javadoc `ClassLoader`; thường trả null theo hợp đồng.

**3. Muốn hiểu static initializer chạy khi nào?**  
JLS `12.4` và JVMS `5.5`; đối chiếu `Class.forName` Javadoc khi dùng reflection.

**4. Gặp `NoSuchMethodError` sau khi deploy, nên xem gì?**  
JVMS resolution, JLS binary compatibility, `javap` caller và runtime library.

**5. Lệnh nào xem bytecode của một class?**  
`javap -c -p -classpath ROOT binary.Name`; `-v` xem thêm constant pool/attributes.

**6. Lệnh nào kiểm tra entry resource trong JAR?**  
`jar --list --file app.jar`.

**7. `jdeps` có luôn phát hiện class chỉ được nạp theo string từ reflection?**  
Không; đây là static dependency analyzer, không có quyền tiên tri dynamic behavior.

**8. Phân biệt `exports` và `opens` tìm ở đâu?**  
JLS `7.7` và Javadoc `Module`/`AccessibleObject`; kiểm tra caller/target module cụ thể.

**9. `jcmd PID VM.classloader_stats` là cú pháp hoàn chỉnh có thể copy ngay?**  
Không. Thay PID bằng số process ID thực và kiểm tra process attach permissions.

**10. Vì sao Class.forName(..., false, ...) không đồng nghĩa không load class?**  
Flag false liên quan việc **không yêu cầu initialization**, không phủ nhận loading/linking.

**11. Demo `Probe` chạy trên classpath thì `Class.getModule().isNamed()` là gì?**  
False, vì class thuộc unnamed module của loader.

**12. `java -Xlog:class+load=info` có output giống hệt trên mọi JVM/JDK?**  
Không. Đó là diagnostic logging của runtime hỗ trợ; logs, số lượng/thứ tự tùy môi trường.

**13. Khi nào Javadoc được ưu tiên hơn JVMS?**  
Khi câu hỏi trực tiếp là hợp đồng và edge case của một method thư viện cụ thể như `ClassLoader.getResources`.

**14. Tài liệu JEP có thay thế Java SE 17 API spec không?**  
Không. Dùng JEP để hiểu ý tưởng/động lực; dùng spec/Javadoc của target version cho behavior.

**15. Lý do phải ghi JDK version trong báo cáo?**  
Language/API, tool options, implementation diagnostics và module/security defaults có thể thay đổi theo phiên bản.

## 20. Tài nguyên tổng hợp và đường dẫn chính thức

### Đặc tả Java 17

- JVMS 17 — index: https://docs.oracle.com/javase/specs/jvms/se17/html/index.html
- JVMS 17 — Chapter 4 (class files): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS 17 — Chapter 5 (loading/linking/initialization): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JVMS 17 — Chapter 6 (instructions): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- JLS 17 — index: https://docs.oracle.com/javase/specs/jls/se17/html/index.html
- JLS 17 — Chapter 12 (execution): https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- JLS 17 — Chapter 13 (binary compatibility): https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- JLS 17 — Chapter 7 (packages/modules): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html

### Javadoc và công cụ

- Java SE 17 API index: https://docs.oracle.com/en/java/javase/17/docs/api/index.html
- Java SE 17 tools/man pages: https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html
- `java`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- `javap`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- `jar`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- `jdeps`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- `jfr`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html

**Ghi nhớ:** Spec trả lời *hệ thống phải bảo đảm điều gì*; Javadoc trả lời *API hứa hành vi gì*; các công cụ JDK cung cấp *bằng chứng về artifact/runtime cụ thể*. Kết luận kỹ thuật tốt cần nối được cả ba.
