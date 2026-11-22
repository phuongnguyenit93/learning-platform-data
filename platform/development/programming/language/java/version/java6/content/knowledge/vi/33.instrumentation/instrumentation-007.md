# appendToBootstrapClassLoaderSearch và appendToSystemClassLoaderSearch trong Java Instrumentation

Khi viết Java Agent để quan sát/biến đổi bytecode, đôi khi agent cần nạp một số **lớp hỗ trợ (helper classes)** từ một JAR riêng thông qua **bootstrap class loader** hoặc **system class loader**. `java.lang.instrument.Instrumentation` cung cấp chính xác hai phương thức:

```java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
void appendToSystemClassLoaderSearch(java.util.jar.JarFile jarfile);
```

Cả hai đều **bổ sung JAR vào đường tìm lớp của class loader đã chỉ định**, không phải “đăng ký transformer”, không biến mọi lớp đã tải thành lớp mới, không thêm JAR vào `module-path` và không tự sửa `java.class.path`. Phương thức thứ nhất dùng cho **bootstrap loader**, phương thức thứ hai dùng cho **system loader**. Chúng chỉ nên đưa **các lớp/resources hỗ trợ instrumentation cần thiết** vào đúng vùng tìm kiếm: đưa application classes tùy tiện vào bootstrap có thể gây class-loading conflicts và `IllegalAccessError` khó điều tra.

Bài thuộc chủ đề **Instrumentation** của Java 6 trong lộ trình, nhưng toàn bộ lời giải dùng **API và nguyên tắc vẫn phù hợp Java 17+ / Java SE 26**, không dựa vào `rt.jar`, `tools.jar`, `-Xbootclasspath/p` hoặc cơ chế đóng gói JDK đã lỗi thời. Một thí nghiệm Java Agent thực tế có **4 tệp Java, 3 JAR**, dùng `-javaagent` để nhận `Instrumentation` tại `premain`, gọi cả hai phương thức trên và kiểm chứng **loader identity, unnamed module, visibility, classpath property, NullPointerException**. Thí nghiệm đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy thành công trên **Zulu OpenJDK 24.0.2, 23/23 kiểm tra PASS**.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích chính xác ý nghĩa của `appendToBootstrapClassLoaderSearch(JarFile)` và `appendToSystemClassLoaderSearch(JarFile)`.
2. Phân biệt **bootstrap**, **platform** và **system/application class loader** trong Java hiện đại.
3. Lấy `Instrumentation` qua Java Agent `premain(String, Instrumentation)` mà không cần attach động.
4. Đóng gói JAR đúng mục đích: **bootstrap helper JAR**, **system helper JAR**, **agent JAR** và ứng dụng chính.
5. Dùng `java.util.jar.JarFile` với đường dẫn thực, xử lý input null và lỗi JAR.
6. Kiểm tra `Class.getClassLoader()==null` để nhận diện lớp thực sự được bootstrap loader định nghĩa.
7. Kiểm tra `ClassLoader.getSystemClassLoader()` để nhận diện lớp được system loader định nghĩa.
8. Hiểu `Class.getModule().isNamed()==false` cho helper classes được định nghĩa vào unnamed module tương ứng.
9. Chứng minh JAR được tìm thấy mặc dù **không có trong `java.class.path`**.
10. Hiểu khi nào `UnsupportedOperationException` có thể xảy ra do custom system class loader không hỗ trợ append.
11. Hiểu rằng bổ sung JAR **không hồi phục lỗi symbolic resolution đã ghi nhớ** và không ép class đã nạp được nạp lại.
12. Nắm cơ chế **parent delegation, class identity, package-private access và module boundaries**.
13. Nhận diện nguy cơ package collision, shadowing, class-loader constraints và nondeterministic linkage.
14. Biết sự khác nhau giữa thêm search path, đăng ký `ClassFileTransformer` và `retransformClasses`.
15. Triển khai Java Agent an toàn: minimal helper JAR, trust control, unique packages và quyền triển khai.
16. Chạy toàn bộ thí nghiệm 23 assertions với stdout được kiểm chứng.
17. Đọc tài liệu Javadoc hiện hành thay vì các mẹo “nạp vào rt.jar” từ JVM cũ.

## 2. Tổng quan Java Agent và Instrumentation

`java.lang.instrument` là module/package chuẩn cho các agent có thể quan sát hoặc biến đổi class bytecodes. Một Agent JAR được chỉ định lúc JVM khởi động:

```bash
java -javaagent:search-agent.jar=OPTIONS -cp out/app SampleApp
```

Giá trị `-javaagent` trong ví dụ này chỉ là **lệnh minh họa**. Cần xây đúng JAR và thay OPTIONS bằng đường dẫn thư mục chứa hai helper JAR; hướng dẫn chạy hoàn chỉnh nằm ở mục 10.

Manifest chính của Agent JAR phải có:

```text
Manifest-Version: 1.0
Premain-Class: SearchAgent
```

JVM gọi:

```java
public static void premain(String agentArgs, Instrumentation inst)
        throws Exception {
    // Cấu hình instrumentation trước main().
}
```

Trong Java 17+, `Instrumentation` là một **interface được JVM cung cấp cho agent**. Không tự `new Instrumentation()` hoặc tự implement interface để nhận quyền tương đương. `premain` nhận đối tượng instrumentation **trước** khi ứng dụng chạy `main`.

### 2.1. Bổ sung JAR hỗ trợ khác với biến đổi bytecode

| Hành động | API | Tác dụng |
| --- | --- | --- |
| Cho bootstrap loader tìm helper class mới | `appendToBootstrapClassLoaderSearch(JarFile)` | Mở rộng vùng tìm lớp của bootstrap. |
| Cho system loader tìm helper class mới | `appendToSystemClassLoaderSearch(JarFile)` | Mở rộng vùng tìm lớp của system loader. |
| Theo dõi/biến đổi bytes khi nạp class | `addTransformer(ClassFileTransformer)` | Gắn transformer theo cơ chế instrumentation. |
| Chạy lại transformer với class đã nạp | `retransformClasses(Class<?>...)` | Tùy JVM và agent capability; không phải append search path. |
| Đổi definition của class đã nạp | `redefineClasses(ClassDefinition...)` | Tùy JVM/capability và giới hạn redefine. |
| Mở rộng quan hệ JPMS module | `redefineModule(...)` | Bổ sung reads/exports/opens/services theo contract. |

**Đừng hiểu `appendToBootstrapClassLoaderSearch` là thao tác bắt buộc cho mọi Agent.** Với profiler/monitoring đơn giản, agent và transformer có thể chỉ cần những classes trong agent JAR, mà agent JAR vốn được nạp bởi system loader theo package specification. Chỉ dùng append khi helper thật sự cần được định nghĩa bởi loader tương ứng.

### 2.2. Agent class ở loader nào?

Theo package specification hiện hành, class của agent JAR **được system class loader nạp**, thuộc **unnamed module của system loader**. Không vì agent đã có `Instrumentation` mà class `SearchAgent` bỗng thuộc bootstrap loader.

Nếu bạn cần một helper phải được bootstrap định nghĩa (ví dụ để hỗ trợ instrument core classes), hãy đặt helper đó trong **JAR riêng** và append JAR vào bootstrap search, không đưa toàn bộ agent/app classes vào đó.

## 3. Ba tầng class loader trong Java 17+

Một mô hình đơn giản thường dùng với built-in loaders:

```text
System / application class loader
  - App classes từ class path
  - Agent class từ -javaagent
  - JAR thêm bằng appendToSystemClassLoaderSearch
              |
         parent delegation
              v
Platform class loader
  - Các platform modules theo runtime
              |
         parent delegation
              v
Bootstrap class loader
  - java.base và các classes do bootstrap định nghĩa
  - JAR thêm bằng appendToBootstrapClassLoaderSearch
```

Đây là **sơ đồ khái niệm**. Lớp cụ thể do loader nào định nghĩa phụ thuộc module graph và runtime; Java 9+ không còn mô hình đơn giản một tệp `rt.jar` chứa toàn bộ JDK như các bản cũ. Với lớp được bootstrap loader định nghĩa:

```java
ClassLoader loader = someClass.getClassLoader();
// null nghĩa là bootstrap class loader.
```

`null` là ký hiệu Java API cho bootstrap loader, không phải “class bị lỗi” hoặc “không có loader”. `ClassLoader.getSystemClassLoader()` trả system loader, không nhất thiết là chính class `jdk.internal.loader.ClassLoaders$AppClassLoader` trên mọi JVM/configuration.

### 3.1. Search path và nơi định nghĩa lớp

Hai khái niệm khác nhau:

- **Searching**: một loader được yêu cầu tìm bytes theo binary name.
- **Defining**: loader nào thực sự gọi/được JVM quy định tạo `Class` từ bytes.

Với `Class.forName("demo.instrument.bootstrap.BootHelper", true, null)`, loader request là bootstrap, và nếu tìm được class trong appended bootstrap JAR, `getClassLoader()` của class là `null`.

Với `Class.forName("demo.instrument.system.SystemHelper", true, ClassLoader.getSystemClassLoader())`, system loader tìm JAR đã append và định nghĩa class, `getClassLoader()` bằng system loader.

Điều đó quan trọng bởi **class identity không chỉ là tên**: cùng một binary name được hai defining loaders định nghĩa có thể là **hai kiểu không tương thích** (trừ khi loader delegation khiến chúng dùng chung một definition). Package-private access, linking và module readability cũng phụ thuộc defining loader/module.

### 3.2. Unnamed modules với Java Platform Module System

Một class không thuộc **named module** thường nằm trong **unnamed module của loader định nghĩa**. Trong lab:

- `BootHelper.getModule().isNamed() == false`.
- `SystemHelper.getModule().isNamed() == false`.
- Tuy đều là unnamed modules, **không suy ra hai class thuộc cùng một Module object**; mỗi loader có unnamed module riêng.
- Append không tự chuyển helper sang named module, không đưa JAR vào module-path.
- Nếu agent/helper muốn truy cập package không export/open từ một **named module**, class loading thành công chưa bảo đảm module access thành công. Kiểm tra `redefineModule` hoặc các quyền opens/exports theo policy và runtime.
- Instrumentation package spec có hỗ trợ mở rộng read edges khi biến đổi classes, nhưng **không nên diễn giải thành “mọi module tự mở cho agent”**.

## 4. appendToBootstrapClassLoaderSearch(JarFile)

Chữ ký đầy đủ:

```java
void appendToBootstrapClassLoaderSearch(JarFile jarfile)
```

Tác dụng theo Oracle Java SE 26 Javadoc: khi bootstrap class loader tìm một class không thành công ở các nguồn trước đó, các entries trong JAR được append cũng được tìm. Có thể gọi nhiều lần để bổ sung nhiều JAR; các JAR bổ sung được tìm theo **thứ tự gọi phương thức**.

Ví dụ lõi:

```java
try (JarFile jar = new JarFile(
        Path.of("/trusted/agent/bootstrap-support.jar").toFile())) {
    instrumentation.appendToBootstrapClassLoaderSearch(jar);
}
```

**Mảnh code**, cần `instrumentation` hợp lệ và path thật; không phải chương trình độc lập. Trong production, bảo đảm file JAR còn tồn tại/phù hợp trong suốt thời gian JVM cần tìm/nạp helper classes. Provider/JVM có thể giữ file handle; cân nhắc cơ chế cập nhật/xóa JAR khác nhau giữa Windows/Linux.

### 4.1. Khi nào cần bootstrap helper?

Thí dụ có một `ClassFileTransformer` xử lý các lớp thuộc `java.base`. Bytecode được chèn vào một bootstrap-defined class chỉ có thể liên kết trực tiếp đến các helper classes mà bootstrap loader có thể resolve, theo classloading/module rules. Một helper rất nhỏ trong bootstrap JAR có thể đáp ứng điều kiện đó.

**Không có bảo đảm mọi class của tất cả platform modules đều được bootstrap loader định nghĩa.** Theo Java package spec, helper được định nghĩa qua bootstrap append **chỉ được phép liên kết với classes được bootstrap định nghĩa**. Đừng để bootstrap helper phụ thuộc trực tiếp vào application code hoặc thư viện chỉ có ở system/application loader.

Một pattern thiết kế:

```text
bootstrap-support.jar
  demo/instrument/bootstrap/BootHelper.class  (bootstrap-safe)
                       |
                       | only boot-visible dependencies
                       v
                  java.base

search-agent.jar
  SearchAgent.class
  transformer classes...
                       |
                       +-- system loader, quản lý cấu hình/IO
                       |
                       +-- append bootstrap helper JAR khi cần
```

Dùng **unique package names** cho helpers như `demo.instrument.bootstrap`, tránh package của application, JDK hoặc thư viện khác. Nguy cơ shadowing/collision có thể gây lỗi liên kết không rõ nguyên nhân.

### 4.2. Kịch bản IllegalAccessError được Javadoc cảnh báo

Giả sử một class `C` do loader L định nghĩa có package-private accessor class `C$1`. Nếu bạn vô tình cho `C$1` xuất hiện trong bootstrap JAR, parent delegation có thể khiến nó được bootstrap định nghĩa. Khi `C` tại loader L muốn truy cập package-private member của `C$1`, hai classes khác **runtime package** (vì khác loader) dẫn đến `IllegalAccessError`.

Điều này có thể xảy ra dù package name trong text giống nhau. **Mỗi tên và loader identity đều có vai trò**. Cách phòng ngừa:

- Không append toàn bộ application/library JAR lên bootstrap.
- Bootstrap JAR chỉ chứa những helper classes tối thiểu phục vụ instrumentation.
- Dùng namespace dành riêng cho agent và helpers.
- Test agent trên đúng JDK/class loader topology của ứng dụng.
- Kiểm tra `getClassLoader()` và `getModule()` của helper khi điều tra.
- Không dựa vào internal JDK APIs để né classloader constraint.

### 4.3. Null và các ngoại lệ

`appendToBootstrapClassLoaderSearch(null)` ném `NullPointerException` theo API. Lab có assertion `nullBootstrapJarRejected=PASS`. Các lỗi mở JAR (`IOException`) xảy ra khi tạo `JarFile`, trước khi gọi append.

Ngoài ra, app có thể gặp `ClassNotFoundException` hoặc `LinkageError` khi cố dùng helper sai class name/package hoặc binary không tương thích. Những lỗi runtime đó không tự được “sửa” bằng việc append lại JAR mù quáng.

### 4.4. Cảnh báo về Class Data Sharing (CDS)

Khi append bootstrap path trên HotSpot có thể thấy một dòng stderr tương tự:

```text
OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
```

Dòng trên thực sự xuất hiện trong lần chạy thử trên **Zulu OpenJDK 24.0.2**. Nó là **cảnh báo về khả năng Class Data Sharing**, không phải lỗi “đã nạp bootstrap helper thất bại”: ngay sau đó assertions vẫn PASS. Nội dung và sự xuất hiện có thể khác giữa JDK distributions/flags, nên **không đưa stderr warning vào expected stdout ổn định**.

## 5. appendToSystemClassLoaderSearch(JarFile)

Chữ ký:

```java
void appendToSystemClassLoaderSearch(JarFile jarfile)
```

Nó bổ sung JAR cho **system class loader**. Khi system loader không tìm được class theo các nguồn sẵn có, nó sẽ thử các entries của JAR đã append. Giống bootstrap method, có thể gọi nhiều lần; **thứ tự append** xác định thứ tự tìm các JAR bổ sung.

Ví dụ:

```java
try (JarFile jar = new JarFile(
        Path.of("/trusted/agent/system-support.jar").toFile())) {
    instrumentation.appendToSystemClassLoaderSearch(jar);
}
```

Chỉ là mảnh code. Các lớp trong JAR này được dự kiến **system class loader định nghĩa** (khi chúng chưa được định nghĩa bởi parent loader trước đó). Đây không giống việc ghi vào `java.class.path` system property.

### 5.1. System helper phù hợp khi nào?

Agent hoặc application class được system loader định nghĩa cần gọi helper mà không muốn đưa bootstrap vào cuộc. Nếu helper phụ thuộc vào classes chỉ system loader nhìn thấy, **đừng** append helper vào bootstrap.

Ví dụ:

- Agent-side reporting/configuration utilities.
- Integration glue với application-level observability library (nếu policy cho phép).
- Code hỗ trợ transformer nằm trong app/system namespace, miễn không gây class identity conflict.
- Helper JAR được kiểm soát và versioned cùng agent.

Không append cả thư viện kinh doanh vào system loader nếu custom class loader/plugin isolation yêu cầu namespaces riêng. Append **không làm các custom child/isolated class loaders biến mất** hay bảo đảm mọi loader có thể nạp mọi lớp.

### 5.2. Custom system class loader có thể không hỗ trợ

Oracle Java SE 26 quy định system loader phải hỗ trợ một method:

```java
void appendToClassPathForInstrumentation(String jarFileName)
```

Đó là **tên chữ ký cơ chế hỗ trợ của custom system loader**, không phải một method public trên interface `Instrumentation` hoặc `ClassLoader` mà application nên gọi trực tiếp. Method có thể **không public** theo Javadoc; JVM/instrumentation tìm nó theo quy tắc implementation.

Nếu loader được cấu hình bằng `-Djava.system.class.loader=...` không hỗ trợ cơ chế đó, `appendToSystemClassLoaderSearch` có thể ném **`UnsupportedOperationException`**. Cách xử lý tốt là ghi rõ requirement/fail-fast của agent, kiểm tra classloader trên môi trường chạy và cập nhật custom loader đúng contract; **không cast** system loader sang `URLClassLoader` rồi chỉnh URL list như công thức cũ.

### 5.3. Không làm java.class.path đổi giá trị

Javadoc viết rõ **`appendToSystemClassLoaderSearch` không đổi `java.class.path` system property**. Do đó:

```java
String before = System.getProperty("java.class.path");
instrumentation.appendToSystemClassLoaderSearch(jarFile);
String after = System.getProperty("java.class.path");
assert before.equals(after);
```

Đây là mảnh code. Lab kiểm tra `classPathPropertyUnchanged=PASS` và từ `main` cũng xác minh `java.class.path` **không chứa tên hai support JAR**. Tuy vậy, classes trong support JAR vẫn load được.

Không dùng việc `java.class.path` không đổi như bằng chứng rằng append thất bại. Phải kiểm tra chính xác classloader identity và chạy helper method.

## 6. So sánh hai append APIs

| Thuộc tính | Bootstrap append | System append |
| --- | --- | --- |
| Phương thức | `appendToBootstrapClassLoaderSearch` | `appendToSystemClassLoaderSearch` |
| Tham số | `JarFile` | `JarFile` |
| Loader cần bổ sung | Bootstrap | System/application |
| Phương thức tạo Agent nhận Instrumentation | `premain`/`agentmain` | Giống nhau |
| Loader xác minh | `Class.getClassLoader()==null` | `Class.getClassLoader()==ClassLoader.getSystemClassLoader()` |
| Module thường gặp của helper JAR class | Unnamed module của bootstrap | Unnamed module của system |
| Mức độ rủi ro | Rất cao nếu lớp trùng application/JDK packages | Cao nếu trùng system/application packages |
| Phụ thuộc helper được phép | Chỉ các classes bootstrap có thể resolve | Các classes theo system loader delegation/JPMS rules |
| Ảnh hưởng `java.class.path` | Không phải cơ chế chỉnh property | Javadoc nêu không chỉnh property |
| Có thể gọi nhiều lần | Có, các JAR tìm theo thứ tự append | Có, các JAR tìm theo thứ tự append |
| Tham số null | `NullPointerException` | `NullPointerException` |
| Custom loader support | JVM bootstrap implementation | Có thể `UnsupportedOperationException` nếu custom system loader không hỗ trợ |
| Có tự load class ngay? | Không; chỉ bổ sung search path | Không; chỉ bổ sung search path |
| Có tự retransform classes đã loaded? | Không | Không |
| Có tự chuyển JAR vào named module? | Không | Không |

**Không dùng 2 methods như hai lựa chọn tùy hứng.** Chọn loader dựa trên **nơi instrumentation helper phải được resolve**, ràng buộc runtime package/module và nguồn classes hiện có.

## 7. Cấu trúc dự án thử nghiệm chạy thật

Để kiểm tra kỹ thuật này mà **không làm thay đổi repository chính**, tạo một thư mục lab riêng với cấu trúc:

```text
instrument-append-lab/
  src/
    boot/
      demo/instrument/bootstrap/BootHelper.java
    system/
      demo/instrument/system/SystemHelper.java
    agent/
      SearchAgent.java
    app/
      SampleApp.java
  agent.mf
  out/
    boot/              (javac output)
    system/            (javac output)
    agent/             (javac output)
    app/               (javac output)
  bootstrap-support.jar
  system-support.jar
  search-agent.jar
```

**Chú ý 3 loại JAR**:

1. **`bootstrap-support.jar`**: chứa duy nhất `demo.instrument.bootstrap.BootHelper`; class không tham chiếu application classes.
2. **`system-support.jar`**: chứa duy nhất `demo.instrument.system.SystemHelper`.
3. **`search-agent.jar`**: chứa duy nhất `SearchAgent` và manifest `Premain-Class: SearchAgent`; **không** chứa hai helpers.
4. `SampleApp` chỉ nằm trong **`out/app`**, được đưa vào `-cp` riêng. Không đưa support jars vào classpath lúc chạy.

Nếu bạn nhầm lẫn đưa helper JAR vào `-cp` ban đầu, phần kiểm tra “không có class trước append” sẽ mất ý nghĩa: classes đã sẵn trong đường tìm kiếm, không thể chứng minh append là nguyên nhân.

### 7.1. Minimal helper dễ kiểm chứng

Các helpers chỉ dùng `String` trong `java.base`, trả một nhãn nhận dạng. Không cần logging frameworks, JSON libraries, Guice/Spring, JMX, reflective private access hay code application. Kết quả này giúp tách vấn đề **class loader search** khỏi các lỗi module/library khác.

## 8. Source file 1 — BootHelper.java

**Đường dẫn:** `src/boot/demo/instrument/bootstrap/BootHelper.java`

```java
package demo.instrument.bootstrap;

public final class BootHelper {
    private BootHelper() { }

    public static String label() {
        return "BOOT_ONLY";
    }
}
```

`BootHelper` chỉ gọi các APIs do bootstrap loader định nghĩa; nếu nó được nạp bằng bootstrap, `BootHelper.class.getClassLoader() == null`. Không đặt lớp này trong agent JAR hay system-support JAR.

## 9. Source file 2 — SystemHelper.java

**Đường dẫn:** `src/system/demo/instrument/system/SystemHelper.java`

```java
package demo.instrument.system;

public final class SystemHelper {
    private SystemHelper() { }

    public static String label() {
        return "SYSTEM_ONLY";
    }
}
```

`SystemHelper` được đóng gói riêng. Theo lab, sau system append, `SystemHelper.class.getClassLoader()` là `ClassLoader.getSystemClassLoader()`. Đây là ví dụ riêng để kiểm chứng loader, không khuyến khích nhét mọi helper công cụ vào system class loader.

## 10. Source file 3 — SearchAgent.java

**Đường dẫn:** `src/agent/SearchAgent.java`

Agent chạy tại `premain` và nhận **`Instrumentation` do JVM cấp**. Trình tự:

1. Kiểm tra `SearchAgent` được system loader nạp.
2. Chứng minh `bootstrap-support.jar`/`system-support.jar` chưa nằm trong `java.class.path`.
3. Gọi `Class.forName(binaryName, false, requestedLoader)` trước append, kiểm tra helper **chưa tìm thấy**. Đây là **reflective discovery**, khác với cố tạo một **symbolic reference đã resolve thất bại**.
4. Mở hai `JarFile` với tên file có thật, append vào đúng class loader search.
5. Nạp bootstrap helper với `Class.forName(..., true, null)`; nạp system helper với system class loader.
6. Kiểm tra class-loader identity, unnamed modules, gọi method `label()` bằng reflection, parent delegation và classpath property unchanged.
7. Kiểm tra null `JarFile` bị cả hai methods từ chối.
8. In tổng kết **15/15**.

```java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class SearchAgent {
    private static int checks;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        checks++;
        System.out.println(name + "=PASS");
    }

    private static boolean missing(String binaryName, ClassLoader loader) {
        try {
            Class.forName(binaryName, false, loader);
            return false;
        } catch (ClassNotFoundException expected) {
            return true;
        }
    }

    private static String label(Class<?> type) throws Exception {
        Method m = type.getMethod("label");
        return (String) m.invoke(null);
    }

    public static void premain(String options, Instrumentation inst)
            throws Exception {
        check("premainInstrumentation", inst != null);
        check("agentSystemLoader", SearchAgent.class.getClassLoader()
                == ClassLoader.getSystemClassLoader());
        Path dir = Path.of(options);
        String before = System.getProperty("java.class.path");

        check("supportJarsNotOnClasspath",
                !before.contains("bootstrap-support.jar")
                && !before.contains("system-support.jar"));
        check("bootstrapMissingBeforeAppend", missing(
                "demo.instrument.bootstrap.BootHelper", null));
        check("systemMissingBeforeAppend", missing(
                "demo.instrument.system.SystemHelper",
                ClassLoader.getSystemClassLoader()));

        try (JarFile boot = new JarFile(
                dir.resolve("bootstrap-support.jar").toFile())) {
            inst.appendToBootstrapClassLoaderSearch(boot);
        }
        try (JarFile system = new JarFile(
                dir.resolve("system-support.jar").toFile())) {
            inst.appendToSystemClassLoaderSearch(system);
        }

        Class<?> bootClass = Class.forName(
                "demo.instrument.bootstrap.BootHelper", true, null);
        Class<?> systemClass = Class.forName(
                "demo.instrument.system.SystemHelper", true,
                ClassLoader.getSystemClassLoader());

        check("bootLoadedByBootstrap", bootClass.getClassLoader() == null);
        check("bootInUnnamedModule", !bootClass.getModule().isNamed());
        check("bootMethodInvoked", "BOOT_ONLY".equals(label(bootClass)));
        check("systemLoadedBySystem",
                systemClass.getClassLoader()
                        == ClassLoader.getSystemClassLoader());
        check("systemInUnnamedModule",
                !systemClass.getModule().isNamed());
        check("systemMethodInvoked",
                "SYSTEM_ONLY".equals(label(systemClass)));
        check("bootstrapVisibleViaSystemDelegation", Class.forName(
                "demo.instrument.bootstrap.BootHelper", true,
                ClassLoader.getSystemClassLoader()) == bootClass);
        check("classPathPropertyUnchanged",
                before.equals(System.getProperty("java.class.path")));

        boolean nullBootRejected = false;
        try {
            inst.appendToBootstrapClassLoaderSearch(null);
        } catch (NullPointerException expected) {
            nullBootRejected = true;
        }
        check("nullBootstrapJarRejected", nullBootRejected);

        boolean nullSystemRejected = false;
        try {
            inst.appendToSystemClassLoaderSearch(null);
        } catch (NullPointerException expected) {
            nullSystemRejected = true;
        }
        check("nullSystemJarRejected", nullSystemRejected);

        if (checks != 15) {
            throw new AssertionError("agent check count=" + checks);
        }
        System.out.println("agentChecks=15/15");
    }
}
```

**Vì sao cần reflective `Class.forName` trước append?** Javadoc cảnh báo rằng khi JVM đã thử **resolve một symbolic reference** và thất bại, các lần resolve tiếp theo của cùng reference có thể luôn nhận lại lỗi cũ. Thí nghiệm cố ý kiểm tra discovery bằng reflection, **không tạo direct class references trong bytecode của agent** tới hai helpers, để tránh gắn vào tình huống symbolic resolution failure. Đừng dùng một thử nghiệm `NoClassDefFoundError` do constant-pool reference thất bại rồi nghĩ append sẽ chữa lỗi retroactively.

**Quan trọng:** đóng `JarFile` bằng try-with-resources sau khi đăng ký search location đã thành công trong runtime thử nghiệm; JVM vẫn tìm helper JAR theo đường dẫn. Không tự xóa/move support JAR ngay sau append trong production khi các classes khác còn có thể được nạp: search location cần còn hợp lệ và một số JVM/OS giữ file handles cho JAR.

## 11. Source file 4 — SampleApp.java

**Đường dẫn:** `src/app/SampleApp.java`

Ứng dụng không compile-link trực tiếp hai helper types; nó tìm bằng reflection sau khi `premain` đã append JARs. 8 assertions riêng chứng minh main application nhìn thấy hai helpers qua loader đúng và classpath property không bị bổ sung.

```java
import java.lang.reflect.Method;

public final class SampleApp {
    private static int checks;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        checks++;
        System.out.println(name + "=PASS");
    }

    private static String label(Class<?> type) throws Exception {
        Method method = type.getMethod("label");
        return (String) method.invoke(null);
    }

    public static void main(String[] args) throws Exception {
        check("appSystemLoader", SampleApp.class.getClassLoader()
                == ClassLoader.getSystemClassLoader());

        Class<?> boot = Class.forName(
                "demo.instrument.bootstrap.BootHelper", true, null);
        Class<?> system = Class.forName(
                "demo.instrument.system.SystemHelper", true,
                ClassLoader.getSystemClassLoader());

        check("appSeesBootstrapHelper", boot.getClassLoader() == null);
        check("appSeesSystemHelper",
                system.getClassLoader()
                        == ClassLoader.getSystemClassLoader());
        check("appInvokesBootstrapHelper",
                "BOOT_ONLY".equals(label(boot)));
        check("appInvokesSystemHelper",
                "SYSTEM_ONLY".equals(label(system)));
        check("appBootstrapInUnnamedModule", !boot.getModule().isNamed());
        check("appSystemInUnnamedModule", !system.getModule().isNamed());

        String cp = System.getProperty("java.class.path");
        check("appClasspathHasNoSupportJars",
                !cp.contains("bootstrap-support.jar")
                && !cp.contains("system-support.jar"));

        if (checks != 8) {
            throw new AssertionError("app check count=" + checks);
        }
        System.out.println("appChecks=8/8");
        System.out.println("totalChecks=23/23");
    }
}
```

Tại đây, `SampleApp` chỉ sử dụng **standard Java reflection**, nên không cần compile-time dependency đến support JARs. Đó là yếu tố then chốt để thử xem các classes có thể được nạp **chỉ nhờ append** không.

## 12. Manifest và biên dịch thành 3 JAR

### 12.1. Manifest agent.mf

**Tên file:** `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: SearchAgent

```

Trong manifest JAR, kết thúc bằng **một dòng trống**. Dùng `jar --manifest agent.mf` để công cụ JDK đóng gói và chuẩn hóa manifest. Trong lab này **không cần** `Can-Redefine-Classes` hoặc `Can-Retransform-Classes` bởi chúng ta không redefine/retransform classes. Không khai báo quyền/capability không dùng chỉ vì Agent có thể hỗ trợ.

### 12.2. Lệnh PowerShell trên Windows

Mở PowerShell **tại thư mục `instrument-append-lab`** có `src` và `agent.mf` đã tạo. Các lệnh sau tương thích JDK 17+; phần tương đương đã được chạy trên OpenJDK 24 trong lab.

```powershell
New-Item -ItemType Directory -Force out/boot,out/system,out/agent,out/app | Out-Null

javac --release 17 -encoding UTF-8 -d out/boot src/boot/demo/instrument/bootstrap/BootHelper.java
javac --release 17 -encoding UTF-8 -d out/system src/system/demo/instrument/system/SystemHelper.java
javac --release 17 -encoding UTF-8 -d out/agent src/agent/SearchAgent.java
javac --release 17 -encoding UTF-8 -d out/app src/app/SampleApp.java

jar --create --file bootstrap-support.jar -C out/boot .
jar --create --file system-support.jar -C out/system .
jar --create --file search-agent.jar --manifest agent.mf -C out/agent .

$root = (Get-Location).Path
java "-javaagent:$root\search-agent.jar=$root" -cp out/app SampleApp
```

**Chạy từ đúng thư mục lab** để các đường dẫn tương đối hợp lệ. `-javaagent:...=...` gồm:

- Phần trước `=`: absolute path tới `search-agent.jar`.
- Phần sau `=`: agent options, ở đây là absolute directory path chứa `bootstrap-support.jar` và `system-support.jar`.
- Quoted argument giữ các paths có khoảng trắng thành **một JVM argument**.
- `-cp out/app` chỉ có application output, không có helper JARs.

Bạn có thể dùng thư mục tạm để tránh để lại private application build artifacts trong repository. Không có credential/token nào được dùng trong ví dụ.

### 12.3. Lệnh Bash (Linux/macOS)

Các câu lệnh tương đương với JDK 17+:

```bash
mkdir -p out/boot out/system out/agent out/app

javac --release 17 -encoding UTF-8 -d out/boot \
  src/boot/demo/instrument/bootstrap/BootHelper.java
javac --release 17 -encoding UTF-8 -d out/system \
  src/system/demo/instrument/system/SystemHelper.java
javac --release 17 -encoding UTF-8 -d out/agent \
  src/agent/SearchAgent.java
javac --release 17 -encoding UTF-8 -d out/app \
  src/app/SampleApp.java

jar --create --file bootstrap-support.jar -C out/boot .
jar --create --file system-support.jar -C out/system .
jar --create --file search-agent.jar --manifest agent.mf -C out/agent .

root="$(pwd)"
java "-javaagent:$root/search-agent.jar=$root" \
  -cp out/app SampleApp
```

**Lệnh Bash được mô tả theo cú pháp shell phổ biến**, trong khi kết quả `23/23` ở mục sau đã được kiểm chứng trên OpenJDK 24.0.2 với PowerShell/Windows và đúng bốn Java source tương đương. Nếu dự án nằm trong path có dấu cách, giữ dấu quotes đúng như ví dụ.

### 12.4. Kiểm tra nội dung JAR

Tùy môi trường có thể dùng:

```bash
jar --list --file bootstrap-support.jar
jar --list --file system-support.jar
jar --list --file search-agent.jar
```

Kỳ vọng:

- Bootstrap JAR: chỉ helper ở `demo/instrument/bootstrap/BootHelper.class` và manifest mặc định.
- System JAR: chỉ helper ở `demo/instrument/system/SystemHelper.class` và manifest mặc định.
- Agent JAR: chỉ `SearchAgent.class` và manifest có `Premain-Class: SearchAgent`.
- Application `SampleApp.class` chỉ có trong `out/app`.

Đừng đóng gói cả `out`/`src` hoặc application classes vào bootstrap support JAR. Chất lượng **cấu trúc JAR** quan trọng ngang với code.

## 13. Stdout và kết quả đã kiểm chứng

**Java command** như phần cuối mục 12 đã chạy bằng Zulu OpenJDK 24.0.2, với các lớp được biên dịch bằng `javac --release 17`. Đây là **stdout Java chính xác**, không bao gồm cảnh báo HotSpot in ra stderr.

```text
premainInstrumentation=PASS
agentSystemLoader=PASS
supportJarsNotOnClasspath=PASS
bootstrapMissingBeforeAppend=PASS
systemMissingBeforeAppend=PASS
bootLoadedByBootstrap=PASS
bootInUnnamedModule=PASS
bootMethodInvoked=PASS
systemLoadedBySystem=PASS
systemInUnnamedModule=PASS
systemMethodInvoked=PASS
bootstrapVisibleViaSystemDelegation=PASS
classPathPropertyUnchanged=PASS
nullBootstrapJarRejected=PASS
nullSystemJarRejected=PASS
agentChecks=15/15
appSystemLoader=PASS
appSeesBootstrapHelper=PASS
appSeesSystemHelper=PASS
appInvokesBootstrapHelper=PASS
appInvokesSystemHelper=PASS
appBootstrapInUnnamedModule=PASS
appSystemInUnnamedModule=PASS
appClasspathHasNoSupportJars=PASS
appChecks=8/8
totalChecks=23/23
```

Đây là **15 kiểm tra Agent + 8 kiểm tra App = 23 kiểm tra PASS**; ba dòng `agentChecks/appChecks/totalChecks` là summary. Ở runtime đã thử, có một **stderr warning** từ HotSpot về Class Data Sharing khi bootstrap classpath được append, không phải một dòng stdout ở trên. Không tuyên bố rằng mọi JDK hoặc vendor sẽ in cùng warning.

### 13.1. Bảng giải thích kết quả Agent

| Assertion | Bằng chứng |
| --- | --- |
| `premainInstrumentation` | JVM đã truyền `Instrumentation` vào `premain`. |
| `agentSystemLoader` | `SearchAgent` do system loader nạp. |
| `supportJarsNotOnClasspath` | Hai support JAR không có trong `java.class.path` lúc đầu. |
| `bootstrapMissingBeforeAppend` | Bootstrap loader không tìm `BootHelper` trước append. |
| `systemMissingBeforeAppend` | System loader không tìm `SystemHelper` trước append. |
| `bootLoadedByBootstrap` | `BootHelper.getClassLoader()==null` sau bootstrap append. |
| `bootInUnnamedModule` | `BootHelper` không phải named module. |
| `bootMethodInvoked` | Bootstrap helper thật sự hoạt động, trả `BOOT_ONLY`. |
| `systemLoadedBySystem` | System helper được system loader định nghĩa. |
| `systemInUnnamedModule` | `SystemHelper` không phải named module. |
| `systemMethodInvoked` | System helper hoạt động, trả `SYSTEM_ONLY`. |
| `bootstrapVisibleViaSystemDelegation` | System loader cũng tìm thấy class đã bootstrap định nghĩa, không tạo type thứ hai. |
| `classPathPropertyUnchanged` | System property `java.class.path` không bị append API đổi. |
| `nullBootstrapJarRejected` | Null parameter ném `NullPointerException`. |
| `nullSystemJarRejected` | Null parameter ném `NullPointerException`. |

### 13.2. Bảng giải thích kết quả App

| Assertion | Bằng chứng |
| --- | --- |
| `appSystemLoader` | Application main class được system loader định nghĩa trong lab. |
| `appSeesBootstrapHelper` | App tìm được helper ở bootstrap. |
| `appSeesSystemHelper` | App tìm được helper ở system. |
| `appInvokesBootstrapHelper` | Reflective invocation của bootstrap helper thành công. |
| `appInvokesSystemHelper` | Reflective invocation của system helper thành công. |
| `appBootstrapInUnnamedModule` | Class của bootstrap helper ở unnamed module. |
| `appSystemInUnnamedModule` | Class của system helper ở unnamed module. |
| `appClasspathHasNoSupportJars` | Support JARs vẫn không nằm trong `java.class.path` dù đã load được. |

### 13.3. Rút ra từ kết quả

Nếu chỉ so `System.getProperty("java.class.path")` trước/sau append, bạn sẽ **không thấy thay đổi** và có thể kết luận sai rằng JAR chưa được dùng. Ngược lại, thực nghiệm kết hợp **class not found trước**, **class found sau**, **đúng defining loader** và **gọi method thành công** chứng minh API hoạt động.

Thành công của lab **không cho phép suy rộng** rằng thêm bất kỳ application JAR nào vào bootstrap đều an toàn; helper được cố tình thiết kế rất nhỏ, không gây trùng package hay phụ thuộc vào system-only classes.

## 14. Bẫy “failed symbolic reference” sau append

Javadoc `Instrumentation` cảnh báo một trường hợp rất dễ hiểu sai: khi JVM thử resolve một **symbolic reference trong constant pool** và thất bại, lần tiếp theo resolve **cùng reference** vẫn thất bại với lỗi đã gặp. Vì thế, nếu:

1. Class C đã được nạp với bytecode chứa direct reference tới class Helper.
2. C cố dùng Helper lúc chưa có JAR, gây lỗi resolution `NoClassDefFoundError`.
3. Agent append Helper JAR sau lỗi đó.
4. C tiếp tục cố dùng **symbolic reference cũ**.

…không có bảo đảm C sẽ hồi phục; theo JVMS, symbolic resolution failure có thể được ghi nhớ. **Append không tự xóa resolution error cache.**

### 14.1. Vì sao lab kiểm tra Class.forName bằng reflection?

Lab kiểm tra missing helper trước append bằng:

```java
Class.forName(binaryName, false, loader);
```

Với tên string lấy từ runtime, đây là đường **reflective discovery**, không phải một bytecode direct reference như `new BootHelper()` đã bị symbolic resolution failure. Điều đó cho phép minh họa “trước append không tìm thấy, sau append tìm thấy” mà không lẫn vào kịch bản cached symbolic failure.

**Không dùng ví dụ này như lời hứa rằng mọi cách thử thất bại trước append đều có thể hồi phục**. Khi đã có linkage error, phải phân tích classloader, resolution site và có thể cần restart JVM hoặc fix startup order.

### 14.2. Các class đã nạp không tự đổi defining loader

Nếu class `com.example.Foo` đã được một loader định nghĩa trước append, gọi append với JAR khác chứa `Foo.class` **không di chuyển** class đã nạp qua bootstrap/system loader. Cũng không tự “thay implementation” của Foo. Nếu cần instrument class đã loaded, hãy nghiên cứu `retransformClasses/redefineClasses` và JVM capability riêng; kể cả vậy, không thể chuyển defining loader của class bằng cách retransform.

### 14.3. Nhiều append JAR và thứ tự tìm kiếm

Cả hai methods có thể gọi nhiều lần. Nếu bạn append JAR A rồi B, Javadoc quy định chúng được **searched in invocation order** trong các JAR đã append. Nhưng quy tắc delegation/nguồn đã có của loader vẫn ảnh hưởng tới class resolution. Không dùng duplicate binary names ở nhiều JAR để làm cơ chế version switching:

- Một class đã defined không được tự định nghĩa lại.
- Nếu tồn tại class trong parent loader, child có thể nhận parent's version.
- Class identity phụ thuộc defining loader.
- Thứ tự append chỉ là một phần trong toàn bộ loading resolution.
- Dùng unique packages/version-safe naming và classpath/module graph ổn định.

## 15. Java modules và các giới hạn hiện hành

Java 9+ dùng Java Platform Module System (JPMS); không nên áp dụng sơ đồ Java 6 classpath/bootclasspath cũ theo nghĩa đen.

### 15.1. Bootstrap không có nghĩa “thấy mọi module”

Oracle package spec nói bootstrap helper chỉ được **link tới những classes do bootstrap loader định nghĩa**. Một số platform modules có thể được platform loader nạp hoặc không nằm trong boot layer đang resolved. Vì vậy helper:

- Nên phụ thuộc tối thiểu vào `java.base`.
- Tránh import code app/plugin.
- Tránh tham chiếu các package nội bộ JDK chưa export/open.
- Không cố assume mọi class của JDK đều có `getClassLoader()==null`.
- Có thể cần module options như `--add-modules` cho các modules không có trong boot layer nếu thực sự cần, theo hướng dẫn Oracle.
- Khi instrument classes trong named modules, cần phân biệt module read edges, opens và exports. `Instrumentation.redefineModule` cung cấp API có điều kiện để bổ sung một số quyền nhưng không đồng nghĩa “mở hết”.

### 15.2. System append không thêm vào module-path

Một JAR không có module descriptor, khi được system loader định nghĩa qua append, các classes thuộc **unnamed module của system loader**. Không vì JAR tên `metrics-helper.jar` hay nằm trong một thư mục modules mà nó tự trở thành named module. Với ứng dụng modular:

- Kiểm tra module graph thực tế.
- Kiểm tra package export/open restrictions nếu dùng reflection.
- Không đưa module-info.class tùy ý vào bootstrap JAR và hy vọng JVM tự giải module.
- Không xem `appendToSystemClassLoaderSearch` thay thế `ModuleLayer`/JPMS APIs.

### 15.3. Custom loaders và plugin isolation

Nhiều framework/servers có custom classloaders. `appendToSystemClassLoaderSearch` chỉ bổ sung **system loader search**, không tự sửa search path của mọi URLClassLoader, plugin loader hoặc custom isolated loader.

Các classes do plugin loader định nghĩa có thể nhìn hoặc không nhìn các helpers theo delegation/policy. Khi không tương thích:

- Xác định `targetClass.getClassLoader()`.
- Xác định parent chain, loader constraints và package access.
- Không tự chuyển helper sang bootstrap để “làm nó ai cũng thấy” nếu bootstrap dependency không an toàn.
- Thiết kế bridge/interface nằm ở loader có visibility phù hợp, giữ các lớp app-specific phía system/custom loader.
- Test trên framework/runtime thật, không chỉ ứng dụng command line mẫu.

## 16. Boot-Class-Path manifest và dynamic agents

Ngoài `appendToBootstrapClassLoaderSearch`, Java Agent specification còn mô tả **`Boot-Class-Path`** manifest attribute để khai báo paths được bootstrap search khi agent bắt đầu. Đây là một lựa chọn **vẫn được package spec hiện hành tài liệu hóa**, không đồng nghĩa legacy `-Xbootclasspath/p` hoặc sửa `rt.jar`.

So sánh:

| Cơ chế | Khi dùng | Lưu ý |
| --- | --- | --- |
| `Boot-Class-Path` trong agent JAR manifest | Khai báo paths trước/đúng lúc agent khởi động. | Path syntax/relative resolution và treatment khi attach động theo spec. |
| `appendToBootstrapClassLoaderSearch(JarFile)` | Agent có `Instrumentation` và cần append lúc runtime. | Đường search bổ sung bằng JarFile đã mở. |
| `appendToSystemClassLoaderSearch(JarFile)` | Muốn helper được system loader định nghĩa. | Không dùng Boot-Class-Path để thay. |
| `-javaagent:agent.jar` | Agent lúc JVM startup qua `premain`. | Dễ tái hiện; không phụ thuộc việc dynamic attach được phép. |
| Agent `agentmain` khi JVM đang chạy | Khi implementation hỗ trợ attach/agent loading. | Có security policy, warnings/opt-in trong HotSpot hiện hành. |

Java SE 26 package specification ghi cơ chế dynamic agent loading là **tùy implementation** và trên HotSpot `-XX:+EnableDynamicAgentLoading` được dùng để opt-in cho dynamic loading, có thể giảm warning theo tài liệu. Bài thực hành dùng **startup `-javaagent`** nên tránh phụ thuộc vào dynamic attach restrictions và không cần tự bật quyền attach.

Không xem `-javaagent` như một “tính năng chỉ debug” vô hại: agent có khả năng truy cập/biến đổi runtime, cần đánh giá trust của JAR và quyền của người khởi động.

## 17. Security, packaging và vận hành

### 17.1. Nguyên tắc chỉ thêm JAR được tin cậy

Các JAR append thay đổi phạm vi những classes JVM có thể resolve. Nếu JAR bị thay thế/giả mạo, rủi ro có thể là execution của bytecode không mong muốn và class identity conflict. Vì vậy:

- Chỉ dùng artifacts từ build/repository đáng tin.
- Có hash/signature/attestation và provenance khi hệ thống yêu cầu.
- Giới hạn quyền ghi vào thư mục support JAR trên production.
- Không nạp JAR do user request tự cung cấp trực tiếp.
- Không gọi append từ một API mạng không có authentication/authorization.
- Duy trì inventory và version policy rõ ràng cho agent/helpers.
- Không log source credentials, tokens hoặc sensitive class data từ transformer.
- Test rollback/disable agent và startup behavior khi JAR không có hoặc corrupted.
- Giảm helper jar size và dependency graph để tránh package conflicts.

### 17.2. Tránh split packages

Nếu application và bootstrap JAR cùng chứa một package, các classes mang cùng textual package name nhưng khác defining loaders có thể tạo các **runtime packages khác nhau**, dẫn đến `IllegalAccessError` hoặc `ClassCastException`. Trong JPMS, split packages còn có constraints riêng với named modules.

Hãy dùng **prefix package riêng** cho bootstrap and system support components và không copy application bytecode vào helper JAR. Một bridge nhỏ với public API có thể an toàn hơn đưa mọi library dependency vào bootstrap.

### 17.3. Quản lý JarFile và search path lifetime

Mẫu lab mở `JarFile` trong try-with-resources. Một số triển khai dùng path tên file để append; **không suy rằng bạn có thể xóa JAR ngay sau append** nếu còn lớp chưa được load. Hãy bảo vệ file availability đến khi agent/JVM không còn cần, có deployment procedure phù hợp với file locks trên Windows và symlink/version rollover trên Linux.

Khi `new JarFile(path)` ném `IOException`, đó là lỗi file I/O/format, không phải lỗi `Instrumentation`. Phân biệt lỗi tạo JAR với `UnsupportedOperationException` từ custom system loader.

### 17.4. Agent startup errors

Một exception chưa được catch trong `premain` có thể khiến JVM abort **trước khi `main` chạy**, theo Java Agent specification. Đây là hành vi đáng mong đợi nếu agent là yêu cầu bắt buộc, nhưng cần runbook rõ để không làm outage vì một support JAR bị thiếu.

Nếu agent chỉ là tính năng quan sát tùy chọn:

- Xác định policy fail-open/fail-closed theo doanh nghiệp.
- Có log nguyên nhân mà không lộ secrets.
- Có health check và startup canary.
- Có cách quay về phiên bản agent trước.
- Không dùng catch-all nuốt lỗi rồi giả vờ helper đã sẵn sàng.
- Không tự động nạp code từ nguồn không tin cậy để “fix” missing JAR.

## 18. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `ClassNotFoundException` trước append. | Helper chưa nằm trong search path. | Đây là negative baseline trong lab. |
| `ClassNotFoundException` sau append. | Sai package/binary name, JAR không chứa class, path không hợp lệ hoặc loader khác. | `jar --list`, kiểm tra tên class và loader. |
| `UnsupportedOperationException` ở system append. | Custom system loader không có append support. | Kiểm tra `appendToClassPathForInstrumentation(String)` contract. |
| `NullPointerException` từ append. | `JarFile` argument null. | Truyền `new JarFile(file)` hợp lệ. |
| `IOException` khi tạo JarFile. | File thiếu/hỏng/quyền truy cập/khóa file. | Kiểm tra deployment path/permissions. |
| `IllegalAccessError` sau bootstrap append. | Runtime package/classloader collision; non-public access giữa loaders. | Unique helper package, không append app classes. |
| `NoClassDefFoundError` không hết sau append. | Symbolic reference resolution trước đó đã fail. | Chỉnh startup order, không kỳ vọng retroactive fix. |
| `ClassCastException` với cùng tên class. | Hai class definitions bởi loaders khác nhau. | Kiểm tra `getClassLoader()`, tránh duplicate classes. |
| `NoSuchMethodError`/`LinkageError`. | Binary mismatch/version conflict trong lookup order. | Khóa versions, inspect actual defining loader. |
| `UnsupportedClassVersionError`. | Helper bytecode build cho JDK mới hơn runtime. | `javac --release 17` hoặc đúng target JDK. |
| Agent không chạy `premain`. | Thiếu `-javaagent` hoặc manifest `Premain-Class` sai. | `jar --describe-module` không thay manifest check; `jar --list` và inspect `META-INF/MANIFEST.MF`. |
| `Agent failed to load`. | JAR lỗi, method chữ ký sai, exception trong premain. | Kiểm tra manifest và stack/agent logs. |
| `java.class.path` không đổi. | Đây là behavior documented. | Kiểm tra class visibility và defining loader. |
| CDS warning khi append bootstrap. | HotSpot CDS hạn chế sharing khi bootstrap path thay đổi. | Đánh giá warning, không coi là Java Agent test fail. |
| Helper nằm ở system thay vì bootstrap. | JAR đóng gói sai hoặc load qua system từ trước. | Tách JARs, kiểm tra `getClassLoader()==null`. |
| Boot helper cần system-only library. | Bootstrap không thể resolve dependency. | Tách bridge/helper và chỉ để boot-safe dependencies. |
| Agent chạy local nhưng không trên server container. | Different class loader/module/JDK/deployment layout. | Kiểm tra runtime topology, policy và paths. |
| Dynamic attach bị từ chối. | Runtime policy/Java SE26 HotSpot opt-in. | Dùng startup `-javaagent` hoặc quy trình attach được phép. |

### 18.1. Checklist debug theo thứ tự

1. In Java runtime version và kiểm tra đúng JDK đang chạy.
2. Kiểm tra agent manifest `Premain-Class` và phương thức `premain` chính xác.
3. Kiểm tra đường dẫn tuyệt đối tới Agent JAR và hai support JARs.
4. Xác minh JAR entries bằng `jar --list --file ...`.
5. Kiểm tra không vô tình đặt support JARs vào initial `-cp`.
6. Log loader identity của agent và helper, không chỉ tên class.
7. Kiểm tra `Module.isNamed`/`Module.getName` nếu nghi JPMS.
8. Kiểm tra `java.system.class.loader` nếu system append unsupported.
9. Đọc các `ClassNotFoundException`, `NoClassDefFoundError` và `LinkageError` trong phase.
10. Không retry append vô hạn; sửa root cause của đường search/loader/dependencies.
11. Dừng deployment nếu helper JAR chưa được xác thực nguồn và hash.
12. Test agent startup với canary JVM trước khi áp vào workload thật.

## 19. Checklist QA cho bài thực hành

- [ ] Cấu trúc thư mục chứa đúng 4 Java files và manifest?
- [ ] `SearchAgent` có đúng `premain(String, Instrumentation)`?
- [ ] `search-agent.jar` có `Premain-Class: SearchAgent`?
- [ ] Hai support JARs không chứa agent/main classes?
- [ ] `bootstrap-support.jar` chỉ có bootstrap-safe helper?
- [ ] `system-support.jar` chỉ có system helper?
- [ ] Compile cả 4 với `javac --release 17` đã PASS?
- [ ] Chỉ `out/app` có mặt trong `-cp`?
- [ ] Negative `Class.forName` trước append đã cho CNFE?
- [ ] Bootstrap append làm `BootHelper.getClassLoader()==null`?
- [ ] System append làm `SystemHelper` do system loader định nghĩa?
- [ ] Cả hai helpers có unnamed modules?
- [ ] Reflective method invocation từ agent và app thành công?
- [ ] System delegation cùng nhìn thấy bootstrap helper?
- [ ] `java.class.path` không thay đổi sau append?
- [ ] Null JarFile triggers NPE trên cả hai API?
- [ ] Agent và app assertions đếm đủ 15 + 8?
- [ ] Có phân biệt stderr CDS warning với stdout PASS?
- [ ] Có test trên JDK/provider/OS của deployment thực tế?
- [ ] Có unique packages, không duplicate binary names?
- [ ] Có kiểm tra custom system loader nếu sử dụng?
- [ ] Có kiểm tra module access nếu ứng dụng dùng JPMS?
- [ ] Có lifecycle/rollback policy cho agent/helpers?
- [ ] Không dùng agent JAR không tin cậy?
- [ ] Không dùng cách quản lý `rt.jar`/`tools.jar` đã lỗi thời?

## 20. Bài tập mở rộng

**A — Xác nhận negative baseline.** Chạy `java -cp out/app SampleApp` **không có agent**. Chương trình không thể tìm bootstrap/system helpers; giải thích vì sao đây là expected failure, không coi là bug của classloader.

**B — Đảo hai append calls.** Gọi system append trước bootstrap append. Hai JAR chỉ có các class khác nhau nên kết quả có thể không đổi; giải thích vì sao điều đó **không** có nghĩa thứ tự append vô dụng trong trường hợp duplicate names.

**C — Thêm bootstrap helper thứ hai.** Tạo `bootstrap-extra.jar` với class khác, gọi bootstrap append hai lần. Thử nạp cả hai bằng `Class.forName(...,null)`.

**D — Thêm system helper thứ hai.** Tạo `system-extra.jar`, gọi system append nhiều lần. Xác minh loader identity của các classes.

**E — Cố ý đưa BootHelper vào system JAR nhưng không bootstrap JAR.** Dự đoán `Class.forName(binaryName, true, null)` thất bại, dù system loader có thể tìm thấy class.

**F — Cố ý đưa SystemHelper vào bootstrap JAR.** Xác minh nó có thể được parent bootstrap loader định nghĩa thay vì system loader; giải thích vì sao split packaging làm thay đổi identity.

**G — Kiểm tra named module.** Tạo ứng dụng dùng `module-info.java`, ghi nhận `getModule().isNamed()` của main class và helper classes. Không cho rằng module graph tự thay đổi khi append JAR.

**H — Duplicate names.** Đóng một binary name vào hai JARs (chỉ trong lab) và thử xác minh class được loader nào định nghĩa. Giải thích rủi ro của shadowing; **không áp dụng vào production**.

**I — Classpath property.** In `System.getProperty("java.class.path")` trước/sau system append và từ main; khác biệt thế nào với khả năng `Class.forName`?

**J — Package-private access.** Trong một test tách biệt, dựng hai classes cùng package name nhưng khác classloader và thử gọi package-private member. Phân tích `IllegalAccessError` mà Javadoc cảnh báo.

**K — Failed symbolic resolution.** Dựng một test JVM con riêng làm direct symbolic link tới helper trước append, ghi nhận `NoClassDefFoundError`, rồi thử append. Kết luận về failure caching theo JVMS, không sửa chính JVM test chính.

**L — Custom system class loader.** Đọc `ClassLoader.getSystemClassLoader` và Javadoc append contract; giải thích tại sao `URLClassLoader.addURL` reflection hacks không phải giải pháp chuẩn.

**M — Boot-Class-Path.** So sánh một agent manifest có `Boot-Class-Path` và một agent dùng `appendToBootstrapClassLoaderSearch`. Cả hai đều đang được Java specification mô tả, nhưng thứ tự setup/lifetime khác.

**N — Module boundary.** Instrument một class trong named module có API không export; phân biệt class visibility và Java module access, đề xuất cấu hình `redefineModule` tối thiểu (nếu được phép).

**O — Security review.** Tạo checklist supply chain cho agent/helper JARs: provenance, version lock, signature/hash, quyền ghi và rollback.

**P — Production canary.** Thiết kế một startup smoke test để kiểm chứng agent loader, helper loader, module access và business readiness trước rollout, không dùng `Class.forName` error làm “tự động chữa” version conflicts.

## 21. Câu hỏi tự kiểm tra và đáp án

**1. `appendToBootstrapClassLoaderSearch` làm gì?** — Bổ sung JAR vào vùng tìm lớp của bootstrap class loader.

**2. `appendToSystemClassLoaderSearch` làm gì?** — Bổ sung JAR vào vùng tìm lớp của system loader.

**3. Cả hai nhận tham số gì?** — `java.util.jar.JarFile`.

**4. Có cần Java Agent không?** — Cần một `Instrumentation` instance do JVM cung cấp cho agent qua `premain` hoặc `agentmain` (khi runtime hỗ trợ); không tự khởi tạo interface này.

**5. `-javaagent` gọi method nào?** — `premain` của class được manifest `Premain-Class` chỉ định.

**6. Agent class được nạp bởi bootstrap không?** — Theo package spec, agent JAR classes được system loader nạp.

**7. Bootstrap helper được xác minh bằng gì?** — `BootHelper.class.getClassLoader() == null`.

**8. System helper được xác minh bằng gì?** — `SystemHelper.class.getClassLoader() == ClassLoader.getSystemClassLoader()`.

**9. Một class đã load có đổi loader chỉ vì append không?** — Không.

**10. System append có làm `java.class.path` system property đổi không?** — Không, Javadoc nêu rõ.

**11. Append có thay `ClassFileTransformer` không?** — Không. Append tìm lớp, transformer sửa/quan sát bytecode.

**12. Append có tự biến JAR thành named module không?** — Không.

**13. Một bootstrap helper có thể import mọi application classes không?** — Không; chỉ link tới classes được bootstrap resolve theo package spec.

**14. Vì sao nên dùng unique package names?** — Tránh class shadowing và `IllegalAccessError` do runtime package/loader collisions.

**15. Cả hai methods có chấp nhận null JarFile không?** — Không, `NullPointerException`.

**16. System append có luôn hoạt động với custom system loader không?** — Không; có thể `UnsupportedOperationException` nếu loader không có cơ chế hỗ trợ.

**17. Vì sao `Class.forName` trước append và direct symbolic reference khác nhau?** — Symbolic resolution failure có caching rules; reflective discovery trong lab không kiểm chứng hồi phục của direct linkage đã fail.

**18. Có nên nạp app JAR đầy đủ vào bootstrap không?** — Không, rủi ro classes/packages conflicts và linkage errors cao.

**19. `Boot-Class-Path` manifest có còn được spec mô tả không?** — Có. Không nên nhầm với thao tác sửa `rt.jar`/JDK cũ.

**20. Vì sao lab không thử dynamic attach?** — Startup `-javaagent` đủ để minh họa hai append APIs, ít phụ thuộc runtime agent-loading policy của Java hiện đại.

**21. HotSpot CDS warning có nghĩa bootstrap append không chạy?** — Không; lab vẫn đạt 23/23 PASS.

**22. Hai unnamed modules có chắc là cùng một module không?** — Không; unnamed module gắn với defining classloader tương ứng.

**23. Java version nào dùng để biên dịch?** — `--release 17`, compatible Java17+.

**24. Java runtime nào đã thử?** — Zulu OpenJDK 24.0.2 trên Windows.

**25. Tổng số kiểm tra có thật là 23 không?** — Có: **15 Agent PASS + 8 App PASS = 23 PASS**, output ở mục 13.

## 22. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hai append methods, JAR search order, NPE/UnsupportedOperationException, symbolic resolution failure, `java.class.path`, redefine/retransform.
- [Oracle Java SE 26 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`/`premain`/`agentmain`, agent manifest, Boot-Class-Path, module visibility, bootstrap-helper dependencies, dynamic attach policy.
- [Oracle Java SE 26 — JarFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/jar/JarFile.html): tạo/đọc JAR entries, file lifecycle.
- [Oracle Java SE 26 — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/system/platform loaders, `getSystemClassLoader`, loader hierarchy.
- [Oracle Java SE 26 — Class](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): `Class.forName` và `getClassLoader/getModule`.
- [Oracle Java SE 26 — Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): named/unnamed modules và access rules.
- [Oracle Java SE 26 — Java Virtual Machine Specification, Resolution](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-5.html#jvms-5.4.3): symbolic reference resolution và cached failure semantics.
- [Oracle Java SE 26 — jar tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): tạo/kiểm tra JAR và manifest.
- [Oracle Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API tương thích Java 17.
- [Oracle Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup API/manifest trên Java17.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): chuẩn bị hạn chế dynamic agent loading, phân biệt với startup `-javaagent`.

**Ghi nhớ:** `appendToBootstrapClassLoaderSearch` và `appendToSystemClassLoaderSearch` **chỉ mở rộng các search locations của loader tương ứng**. Chúng không biến loader của classes đã nạp, không tự retransform, không sửa `java.class.path` hoặc module-path. Chỉ append **small, trusted, uniquely packaged instrumentation helper JARs** vào đúng loader, kiểm tra loader identity bằng `getClassLoader()`, quan tâm symbolic-resolution failures, JPMS visibility, classloader collisions và custom system-loader support. Thử nghiệm 4 Java sources/3 JARs của bài đã xác minh **23/23 PASS** bằng Java 17 source level trên OpenJDK 24.
