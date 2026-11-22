# Nhận diện bootstrap class loader qua `loader == null` trong `ClassFileTransformer`

## 1. Vấn đề cần giải quyết

Khi viết Java agent hoặc công cụ instrumentation, phương thức `ClassFileTransformer.transform(...)` nhận một tham số `ClassLoader loader`. Giá trị này cho biết **class loader định nghĩa class đang được xử lý** (*defining loader*). Trong hợp đồng Java Instrumentation:

> **Nếu `loader == null`, class đang được biến đổi do bootstrap class loader định nghĩa.**

Bootstrap loader là cơ chế tải lớp lõi của JVM, thường không được biểu diễn bằng một đối tượng `ClassLoader` Java có thể sử dụng trực tiếp. Vì vậy API dùng `null` như **giá trị quy ước**, chứ không có nghĩa “không biết class loader”, “thiếu dependency” hay “callback bị lỗi”.

Ví dụ, một transformer theo dõi cả mã ứng dụng và các lớp lõi có thể xử lý khác nhau:

```java
if (loader == null) {
    // Class được định nghĩa bởi bootstrap loader.
} else {
    // Class được định nghĩa bởi một ClassLoader Java cụ thể.
}
```

Đây là kiểm tra **danh tính nguồn định nghĩa class**. Nó không tự chứng minh class thuộc JDK hay ứng dụng, không phản ánh mức quyền, không bảo đảm class có thể sửa, và cũng không cho biết class đang chạy ở thread nào.

Bài học thuộc phần **hợp đồng transformer**: hiểu chính xác ý nghĩa callback, các trường hợp dễ nhầm và cách quan sát được `loader == null` mà không phụ thuộc vào việc một lớp JDK đã tình cờ được nạp trước lúc agent đăng ký.

## 2. Nhắc lại các loader thường gặp trên Java 17+

| Loại loader | Vai trò điển hình | Giá trị trong `transform` |
| --- | --- | --- |
| **Bootstrap** | Định nghĩa những lớp nền tảng, ví dụ `java.lang.Object`, `java.lang.String`; có thể mở rộng tìm kiếm bằng API instrumentation | **`null`** |
| **Platform** | Định nghĩa một số lớp module nền tảng/JDK theo cấu hình runtime | Đối tượng `ClassLoader` **không null** |
| **System/application** | Thường định nghĩa class trên application classpath | Đối tượng `ClassLoader` **không null** |
| **Custom loader** | Loader của plugin, framework, ứng dụng container, test runtime, v.v. | Đối tượng loader **không null** |

Ví dụ các API:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

Trong JVM Java 17 phổ biến, cả `platform` và `system` là đối tượng Java thực sự. **Không dùng `ClassLoader.getPlatformClassLoader() == null` để nhận diện bootstrap**: bootstrap là loader **khác** với platform. Cũng không mặc định hệ thống luôn chỉ có ba loader; framework có thể tạo nhiều loader riêng.

### “Defining” khác “initiating” như thế nào?

Java class loading thường có mô hình **ủy quyền (delegation)**. Ví dụ system class loader được yêu cầu tìm `java.lang.String` nhưng chuyển yêu cầu về bootstrap loader; class thực tế vẫn được **bootstrap định nghĩa**.

```text
App/System loader  --- yêu cầu java.lang.String ---+
                    (initiating loader)           |
                                                   v
                                        Bootstrap loader
                                        (defining loader)
                                                   |
                                                   v
                                         class java.lang.String
                                         getClassLoader() == null
```

Bởi vậy, trong transformer, `loader` biểu diễn **defining loader**, không phải “loader đầu tiên được gọi” hoặc loader cha được hỏi trong chuỗi delegation.

Đặc biệt, **Thread Context ClassLoader (TCCL)** lấy qua `Thread.currentThread().getContextClassLoader()` không được dùng thay `loader`. TCCL có thể do framework hoặc ứng dụng đặt thành system/custom loader trong khi class đang được transformer xử lý lại thuộc bootstrap.

## 3. Đọc đúng hợp đồng của hai overload `transform`

Java 17 có hai phương thức callback:

**Dạng truyền thống:**

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

**Dạng có module (Java 9+):**

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Ở **cả hai dạng**, `loader == null` là dấu hiệu **bootstrap defining loader**. Tham số `module` giúp phân biệt lớp theo Java Platform Module System, **không thay thế** thông tin loader.

Các tham số khác có ý nghĩa **độc lập**:

- `className`: tên lớp theo **internal form** dùng dấu `/`, ví dụ `java/lang/String` và `demo/boot/BootProbe`, không phải binary name với dấu `.`. Luôn xử lý tình huống tên lớp không có sẵn nếu cần hỗ trợ các trường hợp đặc biệt.
- `classBeingRedefined`: `null` trong lần định nghĩa class thông thường; có thể khác `null` khi callback do redefine/retransform.
- `protectionDomain`: miền bảo vệ liên quan đến định nghĩa class; đừng dùng nó như dấu hiệu thay thế cho bootstrap.
- `classfileBuffer`: bytes của class ở giai đoạn biến đổi; **không sửa trực tiếp mảng đầu vào**. Trả `null` khi không muốn biến đổi; nếu sửa, trả một mảng `byte[]` mới chứa class file hợp lệ.

Đừng nhầm:

| Điều kiện | Ý nghĩa |
| --- | --- |
| `loader == null` | Class do **bootstrap loader** định nghĩa |
| `classBeingRedefined == null` | Callback là định nghĩa ban đầu, không phải redefine/retransform |
| `className == null` | Tên class không có/không áp dụng trong một trường hợp đặc biệt; không suy ra loader |
| `transform(...)` trả `null` | Transformer không thay thế bytecode trong lượt này |
| `Thread.currentThread().getContextClassLoader() == null` | Trạng thái TCCL của thread, **không** phải dấu hiệu trực tiếp về defining loader của class đang transform |

Một chi tiết quan trọng: trên Java 17, hai phương thức `transform` đều có implementation mặc định trong interface. **Không nên viết lambda rồi giả định `ClassFileTransformer` là functional interface**. Hãy dùng một class triển khai hoặc anonymous class và `@Override` phương thức mong muốn. Nếu override dạng 5 tham số, implementation mặc định của dạng có `Module` sẽ chuyển tiếp tới nó.

## 4. Cách viết transformer nhận diện bootstrap an toàn

Ví dụ **đoạn mã minh họa** đặt trong `premain(String, Instrumentation)` hoặc `agentmain(String, Instrumentation)`; riêng đoạn dưới không phải một chương trình có thể chạy độc lập:

```java
inst.addTransformer(new ClassFileTransformer() {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if ("java/lang/String".equals(className)
                || "demo/boot/BootProbe".equals(className)) {

            String kind = loader == null
                    ? "bootstrap"
                    : "non-bootstrap";

            System.out.println(className + " -> " + kind);
        }

        return null; // Không đổi bytecode.
    }
});
```

Để biên dịch đoạn này trong một class agent, cần import:

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
```

Vì sao kiểm tra `"literal".equals(className)`? Nếu một callback có `className == null`, cách so sánh này không gây `NullPointerException`. Bộ lọc class cụ thể cũng giảm nguy cơ agent in log ồ ạt trong lúc JVM nạp nhiều lớp.

**Không nên viết:**

```java
loader.loadClass("example.Helper");
```

trước khi kiểm tra `loader != null`. Với lớp bootstrap, câu lệnh này ném `NullPointerException`. Ngay cả khi `loader` khác `null`, việc tải class từ ngay bên trong `transform` có thể gây recursion, deadlock hoặc thay đổi thứ tự load; việc thêm dependency cho biến đổi các lớp lõi cần thiết kế thận trọng.

## 5. Vì sao không thể chỉ lọc tên `java/` hoặc nhìn `getClassLoader()`?

### 5.1. Prefix không chứng minh defining loader

Đoạn sau **không chính xác**:

```java
boolean bootstrap = className.startsWith("java/");
```

Một số lớp nền tảng/JDK được định nghĩa bởi platform loader, và việc gán loader phụ thuộc module/runtime. Ngược lại, instrumentation có thể yêu cầu bootstrap loader tìm các lớp hỗ trợ trong một JAR bên ngoài, với package **không bắt đầu bằng `java/`**.

Kết luận dựa trên tên package sẽ sai khi JVM có loader khác hoặc agent mở rộng bootstrap search. **Nguồn sự thật là `loader` của callback.**

### 5.2. `Class.getClassLoader() == null` cần hiểu đúng phạm vi

Với Java 17 HotSpot thông thường:

```java
String.class.getClassLoader() == null
```

là `true` vì `String` được bootstrap định nghĩa. Nhưng:

```java
int.class.getClassLoader() == null
int[].class.getClassLoader() == null
```

cũng đều là `true`. Kiểu nguyên thủy (`int`, `void`) không được định nghĩa từ class file như class Java thông thường; array class được JVM tạo theo quy tắc đặc biệt. **Không suy ra rằng `int.class` hoặc `int[].class` từng gây callback `ClassFileTransformer.transform` chỉ vì loader là null.**

Theo hợp đồng `Class.getClassLoader()`, kiểu primitive và `void` trả `null`. Array class có loader của kiểu phần tử; array của primitive không có class loader. Khi kiểm tra **một class đã được định nghĩa bình thường**, `clazz.getClassLoader() == null` là dấu hiệu hữu ích để liên hệ với bootstrap; khi kiểm tra mọi đối tượng `Class<?>` phải loại primitive/array nếu đang muốn nói về các class file transformable.

### 5.3. Class đã được tải trước agent không tự đi qua transformer mới

`java.lang.String` thường đã có từ lúc JVM đang khởi động **trước khi `premain` đăng ký transformer**. Nếu thêm transformer rồi gọi `String.class.getClassLoader()`, bạn có thể thấy `null` nhưng **không hề nhận callback** cho `java/lang/String`.

Transformer đăng ký bình thường sẽ xử lý các lần định nghĩa class **sau** thời điểm đăng ký; không tự động phát lại lịch sử class loading. Muốn tác động tới lớp đã nạp phải xem xét `Instrumentation.retransformClasses` và capability/giới hạn tương ứng. Ví dụ thực hành tiếp theo sẽ chủ động tạo một lớp bootstrap chưa được tải để tránh phụ thuộc timing của JVM.

## 6. Thực hành A: quan sát Java class loader không cần agent

Tạo tệp **`LoaderFacts.java`**:

```java
public class LoaderFacts {
    public static void main(String[] args) throws Exception {
        Class<?> stringViaSystem = Class.forName(
                "java.lang.String",
                false,
                ClassLoader.getSystemClassLoader());

        System.out.println("String bootstrap=" +
                (String.class.getClassLoader() == null));
        System.out.println("String via system still bootstrap=" +
                (stringViaSystem.getClassLoader() == null));
        System.out.println("App bootstrap=" +
                (LoaderFacts.class.getClassLoader() == null));
        System.out.println("Primitive loader null=" +
                (int.class.getClassLoader() == null));
        System.out.println("Primitive array loader null=" +
                (int[].class.getClassLoader() == null));
    }
}
```

Dùng JDK 17+:

```bash
javac --release 17 LoaderFacts.java
java LoaderFacts
```

Trên runtime JDK 17+ thông thường có system/application loader, stdout dự kiến:

```text
String bootstrap=true
String via system still bootstrap=true
App bootstrap=false
Primitive loader null=true
Primitive array loader null=true
```

Điểm học tập:

- Khi được hỏi qua system loader, `String` **vẫn do bootstrap định nghĩa**; tham số loader truyền cho `Class.forName` là loader được yêu cầu tìm, không đổi defining loader của class.
- `LoaderFacts` được định nghĩa bởi application loader khi chạy bằng `java LoaderFacts` ở classpath thông thường.
- Hai dòng cuối chứng minh kiểm tra `getClassLoader() == null` **không đủ** để tuyên bố đã có callback class-file transformer.

Ví dụ này không khởi tạo Java agent; nó kiểm tra định danh loader trên các đối tượng `Class`.

## 7. Thực hành B: Java agent quan sát callback có `loader == null` một cách chủ động

### 7.1. Thiết kế thực nghiệm

Để chắc chắn nhận callback của bootstrap loader trong một môi trường có hỗ trợ instrumentation, ta tạo một class nhỏ trong JAR riêng, rồi gọi:

```java
instrumentation.appendToBootstrapClassLoaderSearch(
        new JarFile("bootstrap-probe.jar"));
```

API này **thêm JAR vào danh sách mà bootstrap loader sẽ tìm kiếm**. Sau đó ứng dụng dùng `Class.forName(name, true, null)` để yêu cầu bootstrap loader định nghĩa class đó. Class được chọn chưa từng bị nạp trước khi agent bắt đầu, nên callback quan sát có ý nghĩa.

Cấu trúc thư mục:

```text
demo/
├── src/
│   └── demo/
│       ├── agent/
│       │   └── LoaderAgent.java
│       ├── boot/
│       │   └── BootProbe.java
│       └── app/
│           ├── AppProbe.java
│           └── DemoApp.java
└── agent.mf
```

Tạo đúng năm tệp nguồn/manifests bên dưới. Thư mục `classes/` và ba JAR sẽ do lệnh biên dịch/đóng gói tạo ra.

### 7.2. Tệp `src/demo/boot/BootProbe.java`

```java
package demo.boot;

public final class BootProbe {
    private BootProbe() {
    }

    public static String message() {
        return "from bootstrap";
    }
}
```

Class `BootProbe` cố ý chỉ phụ thuộc vào `java.lang`, không phụ thuộc class của ứng dụng. Bootstrap loader phải tự liên kết được các phụ thuộc mà lớp này sử dụng.

### 7.3. Tệp `src/demo/app/AppProbe.java`

```java
package demo.app;

public final class AppProbe {
    private AppProbe() {
    }

    public static String message() {
        return "from application";
    }
}
```

Class này sẽ được đóng gói trong **application JAR**, khác với `bootstrap-probe.jar`.

### 7.4. Tệp `src/demo/agent/LoaderAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class LoaderAgent {
    // Giữ JarFile tham chiếu trong vòng đời JVM của ví dụ.
    private static JarFile bootstrapJar;

    private LoaderAgent() {
    }

    public static void premain(String args, Instrumentation inst)
            throws Exception {

        bootstrapJar = new JarFile("bootstrap-probe.jar");
        inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/boot/BootProbe".equals(className)
                        || "demo/app/AppProbe".equals(className)) {

                    String owner = loader == null
                            ? "bootstrap"
                            : "non-bootstrap";

                    System.out.println("[transform] " +
                            className + ": " + owner);
                }

                // Không thay đổi bất kỳ bytecode nào.
                return null;
            }
        }, false);
    }
}
```

Agent làm hai việc **trước `main`**:

1. Mở `bootstrap-probe.jar` và bổ sung nó vào đường tìm kiếm của bootstrap loader.
2. Đăng ký transformer quan sát hai tên lớp, in loader tương ứng và luôn trả `null`.

Vì ví dụ chỉ quan sát class nạp mới nên `addTransformer(..., false)` là đủ; **không cần** `Can-Retransform-Classes` trong manifest.

Lưu ý `ClassFileTransformer` ở đây dùng **anonymous class** và override phương thức 5 tham số. Java 17 có implementation mặc định của callback 6 tham số sẽ chuyển tiếp sang dạng này, nên mẫu phù hợp với Java 17+.

### 7.5. Tệp `src/demo/app/DemoApp.java`

```java
package demo.app;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        Class<?> boot = Class.forName(
                "demo.boot.BootProbe", true, null);

        System.out.println("[main] bootLoaderNull=" +
                (boot.getClassLoader() == null));
        System.out.println("[main] bootValue=" +
                boot.getMethod("message").invoke(null));

        Class<?> app = Class.forName(
                "demo.app.AppProbe",
                true,
                ClassLoader.getSystemClassLoader());

        System.out.println("[main] appLoaderNull=" +
                (app.getClassLoader() == null));
        System.out.println("[main] appValue=" +
                app.getMethod("message").invoke(null));
    }
}
```

Phương thức `Class.forName(String, boolean, ClassLoader)` có ý nghĩa:

- Với `loader = null`, yêu cầu bootstrap loader tìm và khởi tạo `demo.boot.BootProbe`.
- Với `ClassLoader.getSystemClassLoader()`, yêu cầu system loader tìm `demo.app.AppProbe` trên application classpath.
- Mã dùng **reflection** để trì hoãn việc yêu cầu hai class cho đến vị trí rõ ràng trong `main`, tránh tham chiếu trực tiếp trong bytecode ứng dụng khiến JVM có thể resolve sớm.

### 7.6. Tệp `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.LoaderAgent

```

Manifest yêu cầu `Premain-Class` vì command line dùng `-javaagent`. Thực hành không dùng `Can-Retransform-Classes` vì không gọi `retransformClasses`. Kết thúc manifest bằng một **dòng trống**.

### 7.7. Biên dịch, tách ba JAR và chạy

Mở terminal tại **thư mục `demo/`** ở trên. Sử dụng JDK 17+ hỗ trợ target 17:

```bash
javac --release 17 -d classes src/demo/agent/LoaderAgent.java src/demo/boot/BootProbe.java src/demo/app/AppProbe.java src/demo/app/DemoApp.java

jar --create --file bootstrap-probe.jar -C classes demo/boot
jar --create --file loader-agent.jar --manifest agent.mf -C classes demo/agent
jar --create --file app.jar -C classes demo/app

java -javaagent:loader-agent.jar -cp app.jar demo.app.DemoApp
```

Giải thích cách đóng gói:

- `bootstrap-probe.jar` chỉ chứa các class của `demo.boot`.
- `loader-agent.jar` chứa `LoaderAgent.class` và **`LoaderAgent$1.class`** do anonymous transformer sinh ra; đóng gói cả thư mục `demo/agent` để không bỏ sót class phụ.
- `app.jar` chứa `DemoApp.class` và `AppProbe.class`, nhưng **không** chứa `BootProbe.class`.
- JVM chạy agent bằng `-javaagent`; khi `DemoApp` gọi `Class.forName`, bootstrap tìm được `BootProbe` trong JAR đã append.

**Stdout dự kiến** trên HotSpot/JDK 17+ có hỗ trợ bootstrap search:

```text
[transform] demo/boot/BootProbe: bootstrap
[main] bootLoaderNull=true
[main] bootValue=from bootstrap
[transform] demo/app/AppProbe: non-bootstrap
[main] appLoaderNull=false
[main] appValue=from application
```

Một số JDK có thể in thêm cảnh báo về Class Data Sharing hoặc cấu hình bootstrap classpath trên **stderr**; cảnh báo này không phải một phần stdout minh họa. Nếu ứng dụng có agent/JVM khác cùng tham gia, hãy đối chiếu đúng các dòng do ví dụ tạo ra.

Giải thích kết quả:

1. `BootProbe` được định nghĩa từ `bootstrap-probe.jar` bởi bootstrap loader nên callback nhận **`loader == null`**.
2. Reflection trên `boot.getClassLoader()` cũng trả `null`, xác nhận loader của **class thực**.
3. `AppProbe` được system loader định nghĩa từ `app.jar`, vì vậy callback nhận **`loader != null`**.
4. Không có bytecode nào bị sửa: transformer trả `null`; mục đích là quan sát định danh loader.
5. Hai class đều là code ta tự viết, nhưng một class có loader bootstrap và class kia có application loader. **Nguồn mã do ai viết không quyết định `loader`**; cơ chế class definition mới là yếu tố quyết định.

### 7.8. Kiểm tra artifact nếu kết quả khác

```bash
jar --list --file bootstrap-probe.jar
jar --list --file loader-agent.jar
jar --list --file app.jar
```

Quan sát đường dẫn class trong từng JAR và manifest thực tế. Nếu thiếu `LoaderAgent$1.class`, agent sẽ không tạo được transformer vì anonymous class không có. Nếu `BootProbe.class` bị đặt sai archive, `Class.forName("demo.boot.BootProbe", true, null)` có thể gây `ClassNotFoundException`. Nếu chạy lệnh từ thư mục khác, đường dẫn tương đối `bootstrap-probe.jar` trong `new JarFile(...)` có thể không tồn tại; khi đó chỉ định đường dẫn tuyệt đối đã kiểm tra hoặc chạy tại `demo/`.

**Đây là demo có chủ đích.** Trong production, không đưa tùy tiện toàn bộ ứng dụng vào bootstrap search chỉ để log loader.

## 8. Hợp đồng transformer và trường hợp retransform

Với **class load thông thường**, `classBeingRedefined == null`. Với **redefine/retransform**, tham số này có thể chứa `Class<?>` của lớp đang được xử lý. Tuy vậy ý nghĩa `loader == null` **không thay đổi**: nó luôn là defining loader của class được biến đổi.

Ví dụ khi cần phân nhánh cả loại loader và phase:

```java
boolean bootstrap = loader == null;
boolean revisiting = classBeingRedefined != null;

if (bootstrap && revisiting) {
    // Một class bootstrap đang đi qua đường redefine/retransform.
}
```

Đoạn trên chỉ minh họa kiểm tra; không phải mã chạy độc lập. Muốn callback trên retransform, transformer phải được đăng ký theo chế độ `canRetransform = true` **và** JVM/agent có capability phù hợp. Việc phát hiện bootstrap không tự động cho phép sửa các class lõi.

Nếu một class đã được tải trước khi agent hoạt động, dùng `Instrumentation.getAllLoadedClasses()` và `Class.getClassLoader()` có thể giúp quan sát danh tính; thao tác đổi bytecode cho class đã nạp cần kiểm tra khả năng `isRetransformClassesSupported()`, `isModifiableClass()` và các giới hạn JVM cụ thể. Không gọi retransform đại trà để chỉ kiểm tra loader.

## 9. Tính đúng đắn và an toàn khi xử lý bootstrap classes

### 9.1. Tránh tham chiếu ngược từ lớp bootstrap vào ứng dụng

Class được bootstrap định nghĩa **không tự động thấy** các lớp chỉ tồn tại trong application/custom loader. Nếu transformer nhúng vào bytecode bootstrap lời gọi tới `com.myapp.AgentHelper` trong classpath ứng dụng, JVM có thể không giải quyết được phụ thuộc và ném `NoClassDefFoundError`/`LinkageError`.

Các helper cần dùng bởi class bootstrap phải được đặt ở nơi bootstrap có thể tìm thấy, và vẫn phải xử lý đúng quyền truy cập/module trên Java 9+. Việc đưa helper vào bootstrap search phải giới hạn ở những class thực sự phục vụ instrumentation và có package tên riêng để tránh xung đột.

### 9.2. `appendToBootstrapClassLoaderSearch` có phạm vi và rủi ro riêng

`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` chỉ bổ sung **JAR file** vào phần bootstrap tìm kiếm; nó không làm mọi class trong JAR tự được nạp và không biến thành cơ chế chung thay đổi loader của class đã định nghĩa.

Oracle lưu ý tránh đưa class không thuộc nhóm instrumentation vào JAR append, vì delegation có thể chọn nhầm lớp cùng tên/package, gây `IllegalAccessError` hoặc lỗi khó chẩn đoán. Nếu JVM đã resolve thất bại một symbolic reference, việc append JAR sau đó **không bảo đảm** lần resolve tiếp theo sẽ thành công: JVMS có quy tắc ghi nhớ lỗi resolution của tham chiếu đó.

### 9.3. Cẩn thận với module, quyền truy cập và thứ tự tải

Từ Java 9, class loading và module access là hai khía cạnh khác nhau. `loader == null` xác định bootstrap loader, nhưng không quyết định code đang thuộc **named module** hay **unnamed module**, cũng không tự cấp quyền đọc, export hoặc open package. Transformer có overload nhận `Module` để biết thêm ngữ cảnh module.

Trong callback, tránh:

- Gọi nhiều API phức tạp hoặc reflection tự tải thêm class;
- Ghi log không giới hạn cho toàn bộ `java/`;
- Khởi tạo class mới từ chính một package đang được transformer xử lý;
- Giữ tham chiếu mạnh tới mọi `ClassLoader` tùy tiện và làm class loader không được garbage-collect;
- Giả định callback luôn chạy trên một thread cố định hoặc luôn có TCCL giống ứng dụng.

Transformers có thể được gọi trong quá trình JVM đang định nghĩa class. Mọi thao tác load class mới, I/O hoặc đồng bộ hóa phức tạp trong callback đều có thể ảnh hưởng startup, hiệu năng và độ an toàn luồng. Khi quan sát một số ít lớp như demo, log ngắn giúp dễ kiểm tra hơn.

## 10. Các lỗi suy luận phổ biến

| Phát biểu hoặc biểu hiện | Kết luận đúng |
| --- | --- |
| “`loader == null` là lỗi do JVM không tìm thấy class loader” | Sai: với `transform`, đó là **bootstrap defining loader** |
| “`loader == null` nghĩa class chưa được nạp” | Sai: trạng thái mới nạp/redefine liên quan `classBeingRedefined` và đường callback, không phải riêng loader |
| “Tên bắt đầu `java/` thì chắc chắn bootstrap” | Không thể suy từ tên; phải xem loader thực tế |
| “`String.class.getClassLoader() == null` nên transformer mới đăng ký chắc chắn đã nhận `java/lang/String`” | Sai: `String` thường nạp trước khi transformer đăng ký |
| “`int.class.getClassLoader() == null` nên transformer đã xử lý class `int`” | Sai: primitive không phải class file Java thường được transform |
| “System loader tìm được `String` nên system loader định nghĩa `String`” | Sai: có thể ủy quyền cho bootstrap; callback cho biết defining loader |
| “`ClassLoader.getPlatformClassLoader()` là bootstrap” | Sai: platform là đối tượng loader khác với bootstrap |
| “TCCL là system loader nên `loader` trong callback luôn là system” | Sai: TCCL và defining loader là hai thông tin khác nhau |
| `NullPointerException` khi gọi `loader.loadClass(...)` trong transform | Phải bảo vệ trường hợp `loader == null`; không tự nạp class tùy tiện trong callback |
| Class bootstrap nạp được nhưng hook bytecode gọi helper không thấy | Kiểm tra class loader visibility, module access và phụ thuộc của helper |

## 11. Checklist khi dùng `loader == null` trong một agent thực

1. Dùng đúng tham số **`loader` của `transform`** để xác định bootstrap; kiểm tra `loader == null` **trước** khi gọi method trên loader.
2. Phân biệt defining loader với TCCL, initiating loader, loader cha và module.
3. So sánh `className` bằng tên **internal dạng dấu `/`**; viết bộ lọc null-safe và giới hạn logging.
4. Hiểu rõ class nào đã nạp **trước** khi đăng ký transformer; không coi thiếu callback là bằng chứng class không thuộc bootstrap.
5. Khi cần xử lý class lõi, kiểm tra khả năng retransform/modifiability và thiết kế helper có thể được bootstrap liên kết.
6. Nếu dùng `appendToBootstrapClassLoaderSearch`, tách JAR instrumentation nhỏ, package riêng; kiểm tra class/resource collision và quyền truy cập module.
7. Xác minh trên **JVM và artifact thực tế**, vì lớp do framework/plugin load có thể khác với cấu hình máy phát triển.

## 12. Tài liệu chuẩn

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): định nghĩa `loader` là defining loader; hai overload `transform`; yêu cầu không sửa input bytes và trả `null` khi không đổi.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, `retransformClasses` và khả năng của JVM.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): mô hình delegation, bootstrap/platform/system loader và xử lý array classes.
- [Java SE 17 — `Class.getClassLoader()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()): primitive/void trả `null`; loader được gắn với từng `Class<?>`.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): tham số loader `null` biểu diễn bootstrap loader khi tra cứu class.

**Ghi nhớ:** Trong `ClassFileTransformer.transform`, **`loader == null` là dấu hiệu bootstrap defining loader**. Dùng giá trị này trực tiếp để phân loại callback, đồng thời phân biệt với tên package, TCCL, class đã nạp trước agent và primitive/array không có class file thông thường.
