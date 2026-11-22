# Phạm vi class loader và khả năng truy cập lớp hỗ trợ

## 1. Vì sao agent nhìn thấy lớp mà mã được chèn lại không thấy?

Giả sử agent chèn một lời gọi vào phương thức ứng dụng:

```java
demo.helper.Probe.signal();
```

Đây là lời gọi minh họa, chưa phải một chương trình độc lập. Việc agent biên dịch được hoặc tự gọi được `Probe` chưa chứng minh lời gọi sẽ chạy từ mọi lớp được biến đổi.

Sau khi chèn, lời gọi là một phần bytecode của **lớp đích**. JVM phân giải tham chiếu theo ngữ cảnh của lớp đó và bộ nạp định nghĩa nó, không tự chuyển sang dùng bộ nạp của agent.

Do đó, phải hỏi hai câu riêng:

1. Bộ nạp của agent có thể tìm thấy lớp hỗ trợ không?
2. Bộ nạp và ngữ cảnh truy cập của lớp đích có thể dùng đúng lớp hỗ trợ đó không?

“Đã có JAR trong JVM” không đủ. Phải biết JAR nằm ở đâu trong cơ chế tìm lớp, lớp nào đã được định nghĩa và ai đang tham chiếu tới nó.

## 2. Các phạm vi bộ nạp liên quan đến Java agent

Trong cách chạy agent bằng `-javaagent`, các lớp từ agent JAR được nạp bởi **system class loader** và thuộc module không tên của bộ nạp đó. Đây không có nghĩa mọi lớp ứng dụng đều dùng cùng bộ nạp: máy chủ ứng dụng, plugin hoặc công cụ có thể tạo bộ nạp riêng.

Java hiện đại có bootstrap, platform và system class loader. Bootstrap thường được biểu diễn bằng `null` khi gọi `Class.getClassLoader()`; `null` ở đây không phải lỗi thiếu bộ nạp.

Ví dụ một quan hệ cha có thể là:

```text
bootstrap
  |
platform
  |---------------------------|
system                        isolated plugin loader
(agent, app chính, helper)    (lớp đích Target)
```

Theo mô hình ủy quyền thông thường, bộ nạp con hỏi cha trước. Trong ví dụ này, bộ nạp plugin hỏi platform/bootstrap, rồi tìm trong nguồn riêng; nó không tự hỏi bộ nạp system là nhánh bên cạnh.

Nếu đặt helper ở system classpath, agent và ứng dụng chính có thể dùng được, nhưng plugin cách ly vẫn có thể không tìm thấy helper. Ngược lại, system class loader cũng không tự duyệt tất cả bộ nạp plugin để tìm lớp nghiệp vụ.

Sơ đồ là quan hệ cha của một cấu hình cụ thể, không phải quy tắc rằng mọi bộ nạp tùy biến đều dùng ủy quyền cha trước. Một số hệ thống có chính sách tìm lớp khác; phải kiểm tra môi trường thật. Xem [mô hình ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) và [quy tắc nạp lớp agent](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html).

## 3. Cùng tên chưa chắc cùng kiểu

Trong JVM, định danh lớp bao gồm tên nhị phân và bộ nạp **định nghĩa** lớp đó. Hai lớp cùng tên `demo.helper.Probe` nhưng do hai bộ nạp khác nhau định nghĩa là hai kiểu khác nhau.

Hệ quả thực tế:

- Ép kiểu giữa hai phiên bản cùng tên có thể gây `ClassCastException`.
- Trạng thái `static` của chúng là hai phần riêng.
- Chỉ trùng tên package chưa đủ để có quyền truy cập thành viên mức package; package ở thời gian chạy còn phụ thuộc bộ nạp.
- Chữ ký phương thức chứa kiểu chỉ có ở một phía có thể phát sinh lỗi liên kết hoặc ràng buộc bộ nạp.

Một lớp có thể được bộ nạp con **tìm thông qua cha**, nhưng vẫn do cha định nghĩa. Đừng kết luận mỗi lần bộ nạp con tìm lớp là một định nghĩa mới.

Khi chẩn đoán, xem cả `clazz.getName()`, `clazz.getClassLoader()` và `clazz.getModule()`; không chỉ ghi tên lớp. Quy tắc định danh và liên kết được mô tả trong [JVMS, chương 5](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html).

## 4. Tổ chức lớp hỗ trợ theo phạm vi cần dùng

Một thiết kế thường tách:

```text
agent core
  - logic cấu hình, phân tích/biến đổi bytecode
  - thư viện riêng của công cụ
  - được system class loader nạp

helper/bridge tối thiểu
  - điểm vào mà bytecode lớp đích gọi
  - chữ ký công khai, ít phụ thuộc
  - được đặt ở phạm vi mà các lớp đích cần dùng đều nhìn thấy
```

Không cần đưa toàn bộ agent core lên bootstrap chỉ để một lời gọi đo đạc chạy được.

| Cách cung cấp helper | Phù hợp khi | Giới hạn cần kiểm tra |
| --- | --- | --- |
| Trên system classpath/phạm vi system loader | Lớp đích có thể tìm helper qua system loader | Không giải quyết bộ nạp bootstrap hoặc plugin cách ly |
| JAR riêng bổ sung qua `appendToSystemClassLoaderSearch` | Cần thêm lớp hỗ trợ cho system loader | Không biến system thành cha của mọi bộ nạp |
| JAR nhỏ bổ sung qua `appendToBootstrapClassLoaderSearch` | Cần helper ở phạm vi bootstrap để nhiều nhánh có thể tìm qua ủy quyền | Helper chỉ liên kết tới các lớp bootstrap nhìn thấy; tránh trùng lớp và phụ thuộc ngược |
| Helper được tích hợp riêng theo cơ chế của từng bộ nạp đích | Môi trường plugin có quy tắc cách ly riêng | Cần giải pháp được môi trường/công cụ hỗ trợ; không phải một API tiêm lớp phổ quát của Instrumentation |

`appendToBootstrapClassLoaderSearch(new JarFile(...))` bổ sung JAR vào quá trình tìm kiếm của bootstrap. Nó không thay thế lớp cùng tên đã được nạp và không sửa mọi lỗi liên kết đã xảy ra.

Agent cũng có thể khai báo thuộc tính manifest `Boot-Class-Path`; đường dẫn tương đối trong thuộc tính này được giải theo vị trí agent JAR. Điều đó khác đường dẫn tương đối tự truyền vào `new JarFile(...)`, vốn phụ thuộc thư mục làm việc của tiến trình.

Các API bổ sung JAR và điều kiện của chúng được mô tả trong [Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html). Với system class loader tùy biến, phải đáp ứng hợp đồng hỗ trợ thêm đường tìm kiếm; thao tác không được hỗ trợ có thể ném `UnsupportedOperationException`. Không giả định có thể ép system class loader thành `URLClassLoader` để sửa danh sách URL.

## 5. Hai ràng buộc quan trọng của helper dùng chung

### Không phụ thuộc ngược vào lớp nằm ở phạm vi hẹp hơn

Helper do bootstrap định nghĩa không thể tùy ý tham chiếu agent core nằm ở system loader hoặc kiểu nghiệp vụ chỉ có trong plugin. Nếu helper dùng một thư viện chỉ có trên system classpath, việc đưa chính helper lên bootstrap có thể làm lộ ra lỗi thiếu phụ thuộc mới.

Giữ helper nhỏ, ưu tiên các kiểu bootstrap nhìn thấy như `Object`, `String` và kiểu nguyên thủy ở biên giao tiếp. Đây là định hướng giảm phụ thuộc, không có nghĩa truyền `Object` là tự động an toàn: bên nhận vẫn phải hiểu đúng kiểu thực tế và chính sách chuyển đổi.

Không đặt mọi thư viện ứng dụng vào JAR bootstrap. Ngoài tăng phạm vi phụ thuộc, nó có thể gây trùng tên, khác định danh kiểu hoặc xung đột với các lớp mà ứng dụng muốn tự nạp.

### Bổ sung sớm và tránh hai định nghĩa helper

Nếu helper đã được system loader định nghĩa rồi mới bổ sung một bản cùng tên vào bootstrap, có thể tạo ra hai lớp khác nhau trong quá trình tìm kiếm tiếp theo. Chuẩn bị phạm vi helper trước khi đăng ký bộ biến đổi hoặc trước khi lớp đích cần phân giải tham chiếu.

Đặc tả cũng lưu ý rằng bổ sung JAR không sửa được mọi trường hợp một tham chiếu tượng trưng đã phân giải thất bại; lần thử lại có thể tiếp tục thất bại với cùng lỗi. Đừng lấy thao tác “thêm JAR rồi thử lại” làm cơ chế phục hồi mặc định cho một lớp đã gặp lỗi liên kết.

## 6. Tìm thấy lớp, quyền truy cập và module là ba lớp vấn đề

Ngay cả khi lớp hỗ trợ được tìm thấy, lời gọi còn phải thỏa mãn quyền truy cập Java và các quy tắc module:

1. **Khả năng tìm lớp**: bộ nạp liên quan có thể tìm đúng định nghĩa helper không?
2. **Quyền truy cập lớp/thành viên**: helper và phương thức có được phép gọi từ lớp đích không?
3. **Quan hệ module**: module đọc được nhau và package có được xuất/mở theo nhu cầu truy cập không?

Một helper nằm cùng tên package với lớp đích nhưng do bộ nạp khác định nghĩa không tự được hưởng quyền truy cập mức package. Với điểm vào dùng chung giữa nhiều phạm vi, thường cần lớp và phương thức `public`.

Đối với instrumentation, JVM bố trí quan hệ đọc từ module của lớp được biến đổi tới các module không tên liên quan của bootstrap và bộ nạp lớp agent theo hợp đồng. Đây là hỗ trợ cụ thể, không xóa các quy tắc bộ nạp hay cấp quyền truy cập mọi thành viên `private`.

Khi thực sự cần thay đổi quan hệ đọc, xuất/mở package hoặc dịch vụ của module, `Instrumentation.redefineModule` là API liên quan. Nó không tạo ra một lớp đang thiếu và không làm bộ nạp tùy ý nhìn thấy tất cả JAR. Mở package cho reflection cũng không thay thế việc thiết kế đúng nguồn cung cấp helper.

## 7. Thực nghiệm chạy được: system thấy helper, bộ nạp cách ly không thấy

Ví dụ dùng một lời gọi Java tĩnh thông thường trong `Target.run()` để tái hiện bài toán liên kết giống lời gọi helper nằm trong bytecode sau khi agent chèn. Không có thư viện biến đổi bytecode hoặc bước sửa class file trong thực nghiệm này.

Có bốn phần độc lập:

```text
src/helper/demo/helper/Probe.java
src/target/demo/target/Target.java
src/agent/demo/agent/VisibilityAgent.java
src/app/demo/app/Main.java
agent-manifest.mf
```

### Helper

Tệp `src/helper/demo/helper/Probe.java`:

```java
package demo.helper;

public final class Probe {
    public static void signal() {
        System.out.println("helper: target call");
    }
}
```

Helper chỉ dùng lớp thuộc `java.base`, không nhập lớp agent hoặc lớp đích.

### Lớp đích

Tệp `src/target/demo/target/Target.java`:

```java
package demo.target;

import demo.helper.Probe;

public final class Target {
    public static void run() {
        Probe.signal();
    }
}
```

`Target` được đóng vào JAR riêng và chỉ được nạp bởi bộ nạp cách ly.

### Agent

Tệp `src/agent/demo/agent/VisibilityAgent.java`:

```java
package demo.agent;

import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

public final class VisibilityAgent {
    private static JarFile bootstrapHelpers;

    public static void premain(String helperPath, Instrumentation inst)
            throws IOException {
        if (helperPath == null || helperPath.isBlank()) {
            System.out.println("agent: bootstrap helper=false");
            return;
        }
        bootstrapHelpers = new JarFile(helperPath);
        inst.appendToBootstrapClassLoaderSearch(bootstrapHelpers);
        System.out.println("agent: bootstrap helper=true");
    }
}
```

Không truyền tùy chọn: agent giữ nguyên phạm vi tìm helper. Có truyền đường dẫn JAR: agent bổ sung JAR đó vào bootstrap trước khi `main` chạy.

Agent không nhập hoặc nạp `Probe` trước thao tác bổ sung. Tham chiếu `JarFile` được giữ cho vòng đời tiến trình trong ví dụ; không dùng đoạn mã này như thiết kế thay nóng/gỡ thư viện bootstrap. Nếu đường dẫn sai và lỗi không được xử lý, khởi tạo agent có thể làm ứng dụng không vào `main`.

### Ứng dụng kiểm tra hai phạm vi

Tệp `src/app/demo/app/Main.java`:

```java
package demo.app;

import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) throws Exception {
        Class<?> helper = Class.forName("demo.helper.Probe");
        System.out.println(
                "system helper is bootstrap=" + (helper.getClassLoader() == null));

        URL targetJar = Path.of(args[0]).toUri().toURL();
        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] {targetJar}, ClassLoader.getPlatformClassLoader())) {
            Class<?> target = Class.forName("demo.target.Target", true, isolated);
            System.out.println(
                    "target loader is isolated=" + (target.getClassLoader() == isolated));
            try {
                target.getMethod("run").invoke(null);
            } catch (InvocationTargetException failure) {
                System.out.println(
                        "target failure=" + failure.getCause().getClass().getSimpleName());
            }
        }
    }
}
```

Ứng dụng chính gọi `Class.forName("demo.helper.Probe")` bằng ngữ cảnh bộ nạp của chính nó. Trong khi đó, `URLClassLoader` được tạo với **platform loader** làm cha, nên không nhìn sang system classpath để lấy helper.

`try-with-resources` đóng tài nguyên của `URLClassLoader` sau phép thử; đóng bộ nạp không có nghĩa lập tức dỡ mọi lớp khỏi JVM.

### Manifest và lệnh xây dựng

Tệp `agent-manifest.mf`, không có BOM và có xuống dòng ở cuối:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.VisibilityAgent

```

Dùng JDK 17 trở lên, đứng tại thư mục chứa `src`:

```shell
javac --release 17 -d out/helper src/helper/demo/helper/Probe.java
jar --create --file helper.jar -C out/helper .
javac --release 17 -cp helper.jar -d out/target src/target/demo/target/Target.java
jar --create --file target.jar -C out/target .
javac --release 17 -d out/agent src/agent/demo/agent/VisibilityAgent.java
jar --create --file visibility-agent.jar --manifest agent-manifest.mf -C out/agent .
javac --release 17 -d out/app src/app/demo/app/Main.java
```

`target.jar` chỉ có lớp đích; `helper.jar` chỉ có helper; agent JAR không gộp helper vào trong nó. Classpath biên dịch `Target` giúp trình biên dịch tìm helper, không tự biến helper thành nội dung của `target.jar`.

### Lần chạy 1: helper chỉ ở system classpath

Lệnh dưới đây dành cho Windows, nơi dấu phân cách các mục classpath là `;`:

```shell
java "-javaagent:visibility-agent.jar" -cp "out/app;helper.jar" demo.app.Main target.jar
```

Stdout:

```text
agent: bootstrap helper=false
system helper is bootstrap=false
target loader is isolated=true
target failure=NoClassDefFoundError
```

Helper được ứng dụng chính tìm thấy và do system loader định nghĩa. Nhưng khi `Target.run()` gọi `Probe.signal()`, bộ nạp cách ly không có đường tới helper.

Lỗi từ bên trong phương thức được gọi bằng reflection được bọc trong `InvocationTargetException`; ví dụ in lớp của nguyên nhân gốc để thấy `NoClassDefFoundError`.

### Lần chạy 2: agent bổ sung helper vào bootstrap

Chạy một JVM mới:

```shell
java "-javaagent:visibility-agent.jar=helper.jar" -cp "out/app;helper.jar" demo.app.Main target.jar
```

Stdout:

```text
agent: bootstrap helper=true
system helper is bootstrap=true
target loader is isolated=true
helper: target call
```

Ở lần chạy này, helper được bổ sung trước lần nạp đầu tiên. Cả system loader và bộ nạp cách ly đều tìm được cùng helper qua chuỗi ủy quyền tới bootstrap.

Ví dụ cố ý giữ cùng `helper.jar` trên system classpath ở hai lệnh để chỉ thay một yếu tố: thao tác của agent. Vì lần chạy thứ hai bổ sung bootstrap **trước** khi helper được nạp, không có định nghĩa system của helper được tạo trước đó.

Trên một số OpenJDK, bổ sung bootstrap classpath có thể in cảnh báo liên quan chia sẻ dữ liệu lớp ra **stderr**. Nó không nằm trong stdout nêu trên và không phải lỗi thiếu helper. Hai kết quả đã được kiểm tra trên Zulu OpenJDK 24.0.2.

Trên Linux/macOS, thay classpath `"out/app;helper.jar"` bằng `"out/app:helper.jar"`; các lệnh đóng gói không đổi.

## 8. Chẩn đoán theo đúng loại lỗi

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `ClassNotFoundException` khi gọi tìm lớp tường minh | Đang yêu cầu bộ nạp nào tìm lớp? Nguồn tìm của nó có JAR không? |
| `NoClassDefFoundError` khi mã đích gọi helper | Helper và toàn bộ phụ thuộc của nó có nhìn thấy từ bộ nạp/ngữ cảnh lớp đích không? Có nguyên nhân khởi tạo trước đó không? |
| `ClassCastException` dù tên lớp giống nhau | Có hai định nghĩa cùng tên ở hai bộ nạp không? |
| `IllegalAccessError` | Kiểm tra modifier, package thời gian chạy và quan hệ module; đừng chỉ kiểm tra tên package |
| `InaccessibleObjectException` khi dùng reflection sâu | Kiểm tra package đã được mở cho module thực hiện reflection chưa |
| Thêm JAR rồi vẫn lỗi | Lớp/tham chiếu đã được nạp hoặc phân giải thất bại trước đó chưa? Có bản helper khác không? |

Không thay context class loader của luồng rồi giả định mọi lời gọi bytecode tới helper sẽ dùng nó. Context class loader chỉ tác động những API/công cụ chủ động lựa chọn sử dụng nó; tham chiếu tĩnh trong `Target` vẫn có quy tắc phân giải riêng.

Cũng không dùng riêng `java.class.path` để kết luận toàn bộ khả năng tìm lớp. Việc bổ sung nơi tìm kiếm qua instrumentation và các bộ nạp riêng không được mô tả đầy đủ chỉ bằng chuỗi thuộc tính đó.

## 9. Tự thực hành

1. Trong ví dụ, đổi cha của bộ nạp cách ly thành `ClassLoader.getSystemClassLoader()`; dự đoán lần chạy không bổ sung bootstrap có tìm thấy helper không.
2. Bỏ `helper.jar` khỏi system classpath và chạy lại hai cấu hình; xác định phép tìm helper đầu tiên trong `Main` sẽ chịu tác động gì.
3. Thêm một phụ thuộc chỉ có trong ứng dụng vào helper; giải thích vì sao đưa helper lên bootstrap chưa đủ.
4. Nêu ba kiểm tra trước khi chèn lời gọi helper: nguồn cung cấp lớp, định danh kiểu và quyền truy cập/module.
5. Với một lỗi cùng tên lớp, ghi cả bộ nạp và module của hai phía trước khi sửa cách đóng gói.
