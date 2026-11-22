# Vì sao mã đã chèn có thể không nhìn thấy helper của agent

Một Java agent có thể chèn lệnh gọi `agent.ProbeHelper.hit()` vào phương thức của ứng dụng. Agent tự gọi `ProbeHelper.hit()` bình thường, bytecode được biến đổi cũng hợp lệ, nhưng khi phương thức ứng dụng thực thi, JVM lại báo `NoClassDefFoundError: agent/ProbeHelper`. Lý do phổ biến là **mã đã chèn được thực thi trong lớp mục tiêu, còn helper được định nghĩa trong một không gian class loader mà lớp mục tiêu không thể tra cứu**.

Bài này giải thích chính xác nơi JVM tìm helper, vì sao transformer có thể thấy helper nhưng phương thức đã instrument không thấy, cách tái hiện lỗi với Java 17+, cách chọn vị trí triển khai helper và cách chẩn đoán trong ứng dụng có nhiều class loader hoặc Java Platform Module System (JPMS).

## 1. Agent nhìn thấy một lớp không có nghĩa lớp mục tiêu cũng nhìn thấy

Trong một startup agent, Java Instrumentation thường có hai nhóm lớp:

- **Lớp agent**: triển khai `premain`, `ClassFileTransformer`, logic cấu hình và phụ thuộc như thư viện biến đổi bytecode. Theo đặc tả `java.lang.instrument`, các lớp từ agent JAR được nạp bởi **system class loader**, trong unnamed module tương ứng.
- **Lớp ứng dụng được instrument**: có thể được nạp bởi system class loader, bootstrap class loader, hoặc một class loader do container/framework/plugin tự tạo. Mỗi lớp mang danh tính gồm **tên nhị phân và defining class loader**.

Giả sử transformer đang chạy trong agent tạo ra lệnh JVM sau trong phương thức `demo.BusinessService.handle()`:

```text
invokestatic agent/ProbeHelper.hit:()V
```

Khi transformer tạo bytecode, nó đang thao tác trên mảng `byte[]`. Khi JVM nạp hoặc liên kết lớp `BusinessService`, lời gọi trên trở thành một **symbolic reference** trong constant pool của chính lớp `BusinessService`. Để giải tham chiếu tới `agent.ProbeHelper`, JVM dùng quy tắc liên kết lớp dựa trên **defining loader của `BusinessService`** (và cơ chế nạp/ủy quyền của loader đó), rồi kiểm tra truy cập. JVM không chuyển lời gọi này sang class loader của đối tượng transformer chỉ vì transformer là tác giả của các byte đã chèn.

Đây là khác biệt quan trọng:

| Hoạt động | Môi trường quyết định |
| --- | --- |
| Agent gọi `ProbeHelper.hit()` từ `premain` | Class loader của lớp agent đang gọi |
| Transformer dùng ASM chèn `INVOKESTATIC agent/ProbeHelper.hit` | Transformer chỉ sửa bytes và symbolic reference |
| `BusinessService.handle()` chạy lệnh đã chèn | Loader/module của **lớp `BusinessService`** quyết định quá trình resolve và kiểm tra truy cập |
| Agent gọi `Class.forName("agent.ProbeHelper")` thành công | Chỉ chứng minh loader dùng ở lệnh thử đó tìm được helper |

**Điểm mấu chốt:** sự hiện diện của helper trên classpath của agent không làm helper tự động xuất hiện trong mọi class loader của JVM.

## 2. Ví dụ class loader gây ra lỗi

Xét cây tra cứu sau:

```text
Bootstrap class loader
    |
    +-- java.lang.Object, java.lang.String, ...
    |
System / application class loader
    |
    +-- agent.Agent
    +-- agent.ProbeHelper
    |
Isolated URLClassLoader (parent = null)
    |
    +-- demo.BusinessService
        `-- invokestatic agent/ProbeHelper.hit:()V
```

Sơ đồ là cách biểu diễn **quan hệ tìm kiếm và khả năng nhìn thấy**, không phải mọi loader đều nhất thiết tạo thành một cây parent-first. Ở ví dụ, `URLClassLoader` cô lập không ủy quyền cho system loader; nó chỉ có đường tìm kiếm riêng và khả năng truy cập lớp bootstrap. Vì `agent.ProbeHelper` chỉ nằm ở system loader, lời gọi từ `BusinessService` không tìm được helper.

Một lớp thuộc bootstrap class loader cũng có vấn đề tương tự: ví dụ agent instrument phương thức của lớp JDK do bootstrap định nghĩa nhưng helper chỉ nằm trong agent JAR được system loader nạp. Hướng tìm kiếm từ bootstrap không tự động đi xuống system loader.

Trong thực tế, tình huống tương tự xuất hiện ở:
- Plugin runtime dùng class loader cô lập để từng plugin không chia sẻ thư viện.
- Application server triển khai nhiều ứng dụng với các module/webapp loader khác nhau.
- Framework dùng child-first loader hoặc loader có bộ lọc package.
- Instrumentation của lớp JDK/Java platform được nạp bởi bootstrap.
- Ứng dụng có nhiều phiên bản cùng tên lớp hoặc helper do các class loader khác nhau định nghĩa.

**Parent-first delegation chỉ là một chính sách thường gặp**; custom class loader có thể nạp cục bộ trước, lọc package hoặc từ chối ủy quyền. Không thể suy ra khả năng nhìn thấy helper chỉ từ tên class loader.

## 3. Vì sao lỗi có thể chỉ xuất hiện khi chạy phương thức?

Bytecode chứa `invokestatic` tham chiếu đến tên lớp/phương thức và descriptor. Theo quy tắc linking, JVM phải resolve tham chiếu đó trước khi có thể thực hiện lời gọi. Thời điểm resolve có thể sớm hoặc muộn tùy JVM và đường thực thi, nên không nên giả định rằng `ClassFileTransformer.transform(...)` thành công hoặc `Class.forName("demo.BusinessService")` thành công là proof helper đã được liên kết.

Luồng thường thấy:

```text
Agent nhận byte[] của BusinessService
    |
    v
Transformer thêm invokestatic agent/ProbeHelper.hit:()V
    |
    v
JVM nạp/định nghĩa BusinessService bằng isolated loader
    |
    v
Phương thức handle() được gọi
    |
    v
Resolve agent.ProbeHelper theo loader của BusinessService
    |
    +-- tìm thấy + truy cập hợp lệ --> gọi helper
    |
    +-- không tìm được -----------> NoClassDefFoundError
    |
    +-- tìm thấy nhưng không được phép truy cập
                                   --> IllegalAccessError hoặc lỗi liên kết phù hợp
```

Tùy chi tiết cụ thể, lỗi có thể xuất hiện ở giai đoạn nạp/liên kết trước lần gọi đầu tiên, không nhất thiết đúng ở lệnh `invokestatic` khi quan sát log. Nếu resolve symbolic reference đã thất bại, JVMS quy định các lần resolve tiếp theo đối với cùng tham chiếu thất bại với cùng lỗi. Vì vậy, **thêm helper vào search path sau khi đã phát sinh lỗi không bảo đảm “chữa” được tham chiếu đó trong lớp đang chạy**. Nên chuẩn bị đường nạp helper trước khi instrument hoặc trước khi lớp sử dụng tham chiếu.

Phân biệt hai lỗi thường bị nhầm:
- `ClassNotFoundException` là checked exception từ API nạp lớp tường minh như `ClassLoader.loadClass`/`Class.forName` khi không tìm thấy.
- `NoClassDefFoundError` là `LinkageError` thường gặp khi JVM không thể resolve lớp mà bytecode đã tham chiếu (hoặc một định nghĩa lớp không khởi tạo được). Một `ClassNotFoundException` có thể là cause của lỗi này.

## 4. Chạy ví dụ Java 17+ để tái hiện và sửa đường nhìn thấy helper

Ví dụ chỉ dùng JDK, không cần thư viện ngoài. `BusinessService.handle()` có sẵn lời gọi helper trong mã nguồn **để mô phỏng đúng instruction `invokestatic` mà một transformer thực tế sẽ chèn**. Mục đích là cô lập quy tắc liên kết và class loader; ví dụ này không tự thực hiện bytecode weaving.

Cấu trúc:

```text
helper-visibility/
|-- src/
|   |-- Launcher.java
|   |-- agent/
|   |   `-- ProbeHelper.java
|   `-- demo/
|       `-- BusinessService.java
`-- out/                # được tạo khi biên dịch
    |-- host/           # helper + Launcher; system loader thấy
    `-- target/         # chỉ BusinessService; isolated loader thấy
```

### 4.1. Helper đặt trên classpath của system loader

Tệp `src/agent/ProbeHelper.java`:

```java
package agent;

public final class ProbeHelper {
    private ProbeHelper() {}

    public static void hit() {
        System.out.println("helper: hit");
    }
}
```

Trong hệ thống thật, đây có thể là class đóng gói trong agent JAR và được agent gọi từ `premain`. Nó được để public và có static method public nhằm tránh lẫn lỗi access level với lỗi class loading.

### 4.2. Lớp mục tiêu mang symbolic reference tới helper

Tệp `src/demo/BusinessService.java`:

```java
package demo;

public final class BusinessService {
    public void handle() {
        agent.ProbeHelper.hit();
    }
}
```

Java compiler tạo bytecode có tham chiếu tương tự mã chèn sau đây (minh họa khi sử dụng ASM; **đoạn này không phải chương trình ASM độc lập**):

```java
methodVisitor.visitMethodInsn(
    org.objectweb.asm.Opcodes.INVOKESTATIC,
    "agent/ProbeHelper",
    "hit",
    "()V",
    false
);
```

Cả mã Java được biên dịch trực tiếp và lời gọi do ASM chèn đều phải tuân thủ cùng quy tắc resolve symbolic reference khi JVM chạy phương thức.

### 4.3. Launcher thử ba đường nạp

Tệp `src/Launcher.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Launcher {
    private static void attempt(String label, URL[] locations, ClassLoader parent)
            throws Exception {
        try (URLClassLoader loader = new URLClassLoader(locations, parent)) {
            try {
                Class<?> target = Class.forName("demo.BusinessService", true, loader);
                Object instance = target.getConstructor().newInstance();
                target.getMethod("handle").invoke(instance);

                // So sánh Class identity: tên giống nhau chưa chắc là cùng class.
                Class<?> resolvedHelper =
                        Class.forName("agent.ProbeHelper", false, loader);
                boolean same = resolvedHelper == agent.ProbeHelper.class;
                System.out.println(label + ": OK, sameHelper=" + same);
            } catch (InvocationTargetException e) {
                Throwable cause = e.getCause();
                System.out.println(label + ": "
                        + cause.getClass().getSimpleName());
            } catch (LinkageError e) {
                // Một số JVM có thể resolve sớm ngay khi nạp/liên kết lớp.
                System.out.println(label + ": " + e.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL targetDir = Path.of("out", "target").toUri().toURL();
        URL hostDir = Path.of("out", "host").toUri().toURL();

        attempt("isolated", new URL[]{targetDir}, null);
        attempt("delegate-to-system", new URL[]{targetDir},
                ClassLoader.getSystemClassLoader());
        attempt("helper-in-isolated", new URL[]{targetDir, hostDir}, null);
    }
}
```

Ba trường hợp:

1. `isolated`: loader có `parent=null`, chỉ thấy thư mục chứa `BusinessService` và bootstrap. Helper ở `out/host` không có trong đường nạp.
2. `delegate-to-system`: loader nạp `BusinessService` từ `out/target`, còn `ProbeHelper` có thể được resolve qua system loader là parent.
3. `helper-in-isolated`: loader không có system parent nhưng thư mục `out/host` cũng là đường nạp riêng. Nó tự định nghĩa một `agent.ProbeHelper` **khác** class cùng tên đã được system loader định nghĩa.

### 4.4. Biên dịch và quan sát kết quả

Tạo thư mục `out/host` và `out/target`. Với bash trên Linux/macOS:

```bash
mkdir -p out/host out/target
```

Hoặc với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/host, out/target | Out-Null
```

Sau đó chạy các lệnh dưới đây từ thư mục `helper-visibility` bằng JDK 17+ (cùng cú pháp `javac`/`java` trên các hệ điều hành):

```bash
javac -encoding UTF-8 -d out/host src/agent/ProbeHelper.java src/Launcher.java
javac -encoding UTF-8 -cp out/host -d out/target src/demo/BusinessService.java
java -cp out/host Launcher
```

Kết quả dự kiến:

```text
isolated: NoClassDefFoundError
helper: hit
delegate-to-system: OK, sameHelper=true
helper: hit
helper-in-isolated: OK, sameHelper=false
```

Phân tích:
- Biên dịch thành công vì compiler thấy `ProbeHelper` qua `-cp out/host`. Nhưng **classpath lúc biên dịch không quyết định khả năng tìm lớp trong custom loader lúc chạy**.
- Với loader cô lập, `BusinessService.handle()` có thể không resolve được `agent.ProbeHelper`; reflection có thể bọc lỗi phát sinh trong phương thức bằng `InvocationTargetException`, nên launcher lấy `getCause()`.
- Ở trường hợp thứ hai, parent system cung cấp đúng class helper đang nằm trên classpath launcher, vì vậy `sameHelper=true`.
- Ở trường hợp thứ ba, loader cô lập nạp một bản `ProbeHelper` riêng từ `out/host`; gọi thành công nhưng `sameHelper=false`. Nếu helper có bộ đếm static, cache hoặc callback, bản của isolated loader **không chia sẻ trạng thái static** với bản của system loader.

Thư mục `out/host` ở trường hợp ba có cả lớp `Launcher`, chỉ để giảm số lệnh build của demo. Khi triển khai thực tế, nên đóng gói một JAR helper chuyên biệt thay vì mở toàn bộ classpath của agent cho plugin loader.

## 5. Chọn chiến lược giúp mã instrument nhìn thấy helper

Không có một chiến lược duy nhất phù hợp mọi loader. Trước khi chèn `invokestatic`, chọn nơi helper được định nghĩa, nơi chứa trạng thái đo và cách các lớp mục tiêu tiếp cận helper.

| Cách | Khi phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| **Dùng helper ở system loader và để target delegate được tới system** | Ứng dụng thông thường với application class loader hoặc hierarchy phù hợp | Custom loader có thể không delegate hoặc có quy tắc child-first; bootstrap không nhìn xuống system |
| **Đưa helper-only JAR vào bootstrap search** bằng `Instrumentation.appendToBootstrapClassLoaderSearch` | Điểm đo trong class JDK, nhiều loader cần cùng một bridge tối giản | Helper và mọi phụ thuộc phải được bootstrap giải quyết; tránh đưa cả agent/ASM/library vào bootstrap |
| **Đưa helper vào đúng loader của target** (loader-aware injection) | Plugin/container cô lập, mỗi loader cần helper riêng | Tách class identity/state theo loader, package/module access, trùng tên và vòng đời/unload |
| **Làm bridge tối giản ở bootstrap, phần xử lý phong phú ở agent** | Cần hook thấy được rộng rãi nhưng vẫn cô lập thư viện agent | Bridge chỉ dùng type bootstrap-visible; cơ chế chuyển tiếp cần tránh recursion, giữ tham chiếu loader và coupling |
| **Không chèn tham chiếu trực tiếp tới helper** hoặc dùng đường khác phù hợp | Muốn giảm phụ thuộc liên kết ở class mục tiêu | Kiểm tra chi phí, độ tin cậy và khả năng giải quyết phụ thuộc của cơ chế thay thế |

### 5.1. Bootstrap helper bằng Java Instrumentation

Để mọi lớp có thể tìm thấy một helper đơn giản qua bootstrap, agent có thể đặt một **JAR chỉ chứa lớp helper được thiết kế cho bootstrap** vào bootstrap search path:

```java
// Đoạn trích dùng bên trong premain(...), không phải file Java độc lập.
import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

JarFile helperJar = new JarFile("probe-bootstrap-helper.jar");
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
// Quản lý vòng đời JarFile theo vòng đời agent; không tùy tiện đóng
// khi JVM vẫn cần đọc các entry chưa nạp từ JAR.
```

Đăng ký JAR và đảm bảo class helper có thể được định nghĩa đúng bởi bootstrap **trước khi** mã mục tiêu thử resolve helper. Khi instrument lớp bootstrap, đừng thiết kế helper bootstrap phụ thuộc vào thư viện ASM/Jackson/SLF4J hay class ứng dụng do system/child loader nạp, trừ khi chứng minh toàn bộ đường liên kết thực sự khả dụng. Một helper public có thể chỉ đẩy sự kiện vào một hàng đợi an toàn và dùng API JDK tối giản; việc xử lý sự kiện nâng cao đặt ở nơi khác.

Lưu ý: thêm JAR vào bootstrap search không làm một `Class<?>` đã định nghĩa bởi system loader tự biến thành bootstrap class; có thể xuất hiện hai bản cùng tên do các loader khác nhau định nghĩa. Agent phải chủ động kiểm soát thứ tự load, namespace và nơi lưu trạng thái. Đặc tả cũng cảnh báo tránh đóng gói những lớp/tài nguyên không phục vụ bootstrap vào JAR này để không vô tình “cướp” tên class của ứng dụng.

### 5.2. System loader không phải nơi nhìn thấy toàn cục

`appendToSystemClassLoaderSearch(JarFile)` chỉ thêm JAR vào đường tìm kiếm của **system loader**. Nó không tự tạo quan hệ delegation từ bootstrap hoặc các loader cô lập vào system loader. Tương tự, `-javaagent:agent.jar` giúp JVM nạp agent nhưng không bảo đảm mọi target có thể resolve helper từ agent JAR.

Nếu framework cung cấp API chính thức để đăng ký hoặc định nghĩa helper trong plugin/webapp loader, cần đưa helper vào đúng class loader đó **trước** khi instrument class tham chiếu đến helper. Tránh dùng reflection để ép `ClassLoader#defineClass` vào loader bất kỳ, vì có ràng buộc truy cập/module, thứ tự nạp, package protection và khả năng xung đột với framework.

### 5.3. JPMS: nhìn thấy lớp và quyền truy cập là hai câu hỏi khác nhau

Kể cả khi tìm được helper, JVM còn phải kiểm tra module/package/class/method access. Ví dụ helper nằm trong một **named module** nhưng package không export phù hợp thì lời gọi `invokestatic` có thể gây `IllegalAccessError`; phương thức không `public` cũng có thể bị từ chối. Việc mở package (`opens`) thường liên quan đến deep reflection, không thay thế yêu cầu truy cập cho một lời gọi bytecode trực tiếp.

Với instrumentation qua `java.lang.instrument`, JVM có hỗ trợ đặc biệt: module của lớp đã biến đổi được thu xếp để đọc unnamed module của bootstrap loader và unnamed module của class loader nạp agent chính. Điều này **không thay thế class loading** và không làm cho helper nằm ở loader không thể tới được bỗng xuất hiện. Khi helper nằm trong named module khác, còn cần xét read edge và package export phù hợp; `Instrumentation.redefineModule` có thể hỗ trợ các điều chỉnh module graph được cho phép. Chỉ thêm `reads` khi đường nạp lớp vốn không tồn tại sẽ không giải quyết `NoClassDefFoundError`.

## 6. Quy trình chẩn đoán chính xác

Khi gặp lỗi, đừng vội thêm mọi JAR vào classpath. Xác nhận chính **định nghĩa của lớp mục tiêu** và helper mà JVM cần resolve:

1. **Đọc lỗi gốc:** lấy `cause` của `InvocationTargetException`, lỗi lồng trong stack trace, tên lớp từ `NoClassDefFoundError`, và vị trí phương thức có bytecode đã chèn.
2. **Xác định defining loader:** `targetClass.getClassLoader()`; giá trị `null` có nghĩa bootstrap. Ghi nhận target module bằng `targetClass.getModule()`.
3. **Xác định helper thật sự nằm đâu:** `helperClass.getClassLoader()`, `getModule()`, location JAR qua `getProtectionDomain().getCodeSource()` nếu có.
4. **Thử resolve bằng loader của target:** `Class.forName("agent.ProbeHelper", false, targetLoader)` ở môi trường kiểm thử thích hợp. Việc thử này kiểm tra đường nạp tên lớp, chưa bảo đảm descriptor, class identity và access đều hợp lệ.
5. **Kiểm tra bytecode:** xác nhận internal name `agent/ProbeHelper`, tên `hit`, descriptor `()V` và opcode `INVOKESTATIC` thực sự khớp class helper.
6. **Kiểm tra deployment/module:** helper JAR đã có đúng ở bootstrap/target loader chưa, helper dependencies có cùng đường nạp chưa, package có export hợp lệ không.
7. **Sửa và kiểm chứng bằng lần khởi động sạch:** thử lớp mục tiêu qua loader đúng, gọi phương thức trên đường instrument và xác nhận probe có tín hiệu. Không chỉ dựa vào việc transformer đã trả bytecode.

Đoạn kiểm tra ngắn có thể đặt trong test/diagnostic code đang giữ `Class<?> targetClass`:

```java
// Diagnostic snippet: targetClass là lớp thực sự bị biến đổi.
ClassLoader targetLoader = targetClass.getClassLoader();
System.out.println("target loader=" + targetLoader);
System.out.println("target module=" + targetClass.getModule());

try {
    Class<?> helper = Class.forName(
            "agent.ProbeHelper", false, targetLoader);
    System.out.println("resolved helper loader=" + helper.getClassLoader());
    System.out.println("resolved helper module=" + helper.getModule());
} catch (ClassNotFoundException e) {
    System.out.println("target loader cannot find helper: " + e);
}
```

Trong ví dụ mã, `Class.forName(..., false, null)` kiểm tra khả năng nạp từ bootstrap; Java cho phép `loader=null`. Đừng dựa vào tên loader dạng `toString()` để kết luận hai class là một; so sánh trực tiếp `Class<?>` khi có thể.

Nếu cần quan sát JVM, JDK 17+ hỗ trợ log nạp lớp bằng lệnh sau (có thể tạo nhiều log, nên bật trong môi trường kiểm thử hoặc với phạm vi phù hợp):

```bash
java -Xlog:class+load=info -cp out/host Launcher
```

Log cho biết nơi lớp được nạp, nhưng việc chứng minh loader và module cụ thể vẫn nên dựa trên object `Class<?>/ClassLoader` và thiết lập của ứng dụng.

## 7. Phân biệt triệu chứng khi helper không dùng được

| Triệu chứng | Hướng điều tra |
| --- | --- |
| `NoClassDefFoundError: agent/ProbeHelper` | Loader của class target không tìm được helper, hoặc việc load/link helper thất bại; đọc cause |
| `ClassNotFoundException` khi gọi `Class.forName` | Loader được truyền không có đường tìm class đó |
| `NoSuchMethodError` cho `ProbeHelper.hit:()V` | Thấy một class `ProbeHelper` nhưng method signature hoặc version không khớp bytecode |
| `IllegalAccessError` | Class/package/method không truy cập hợp lệ; xem access modifier và JPMS exports/reads |
| `IncompatibleClassChangeError` | Bytecode kỳ vọng method static nhưng định nghĩa runtime không tương thích, hoặc lỗi thay đổi hình dạng tương tự |
| `ExceptionInInitializerError` / `NoClassDefFoundError: Could not initialize class...` | Class được tìm thấy nhưng khởi tạo static thất bại; nguyên nhân khác với không tìm thấy file class |
| `ClassCastException` giữa hai lớp cùng tên | Nhiều loader đã định nghĩa các class có cùng tên nhưng khác danh tính |
| `LinkageError` liên quan loader constraint | Loader constraints hoặc version/type identity không tương thích |

Có những trường hợp helper nạp được nhưng **helper phụ thuộc vào một class khác không nạp được**. Stack trace có thể nêu tên dependency thay vì class helper. Không bỏ qua cause và toàn bộ chuỗi tham chiếu.

## 8. Thiết kế helper để tránh lỗi vận hành về sau

Một helper được dùng bởi nhiều class loader cần có các tính chất:

- **Public API tối giản và ổn định:** giữ package, binary name, descriptor, kiểu tham số/trả về tương thích với bytecode đã chèn. Với bootstrap helper, ưu tiên những kiểu JDK có sẵn và không yêu cầu type ứng dụng.
- **Không phụ thuộc vòng ngược:** nếu helper gọi lại một phương thức cũng bị instrument, có thể lặp vô hạn hoặc gây stack overflow. Lọc lớp helper/agent khỏi transformer và có cơ chế reentrancy guard khi cần.
- **Chủ đích về trạng thái:** helper có nhiều bản theo loader sẽ có các biến static riêng. Nếu cần một bộ đếm/tập dữ liệu dùng chung, thiết kế bridge và quyền sở hữu dữ liệu rõ ràng.
- **Không giữ loader vô hạn:** map từ class loader sang context phải cân nhắc weak references, shutdown hook hoặc lifecycle của plugin/container; cache strong reference sai có thể ngăn unload.
- **Không load helper quá muộn:** chuẩn bị search path trước khi lớp được transform hay lời gọi probe được resolve; ghi nhận phiên bản triển khai helper và chương trình.
- **Không đưa toàn bộ thư viện agent vào bootstrap:** tránh trùng package, dependency không bootstrap-visible và nguy cơ thay đổi cách nạp lớp ngoài ý muốn.
- **Kiểm thử đúng loader thực tế:** thử với bootstrap, system, child-first, isolated loader và nhiều instance nếu hệ thống hỗ trợ; chạy cả đường gọi thật, không chỉ unit test transformer.
- **Có hành vi lỗi rõ ràng:** thu thập lỗi liên kết/khởi tạo và cung cấp khả năng ngừng instrument ở phạm vi an toàn, thay vì bắt `Throwable` rồi im lặng ở business path.

Một quy tắc thiết kế thực dụng: **xác định nơi helper sẽ được định nghĩa trước khi quyết định chèn instruction tham chiếu tới helper đó**. Việc chọn helper bootstrap, system hay per-loader là một phần của kiến trúc điểm đo, không chỉ là chi tiết đóng gói JAR.

## 9. Câu hỏi tự kiểm tra

1. Vì sao `Class.forName("agent.ProbeHelper")` thành công bên trong `premain` vẫn chưa chứng minh `demo.BusinessService` có thể gọi helper?
2. Điều gì khác nhau giữa `URLClassLoader(..., null)` và `URLClassLoader(..., ClassLoader.getSystemClassLoader())` trong ví dụ?
3. Vì sao kịch bản `helper-in-isolated` gọi thành công nhưng `sameHelper=false`? Bộ đếm static ở hai bản có chia sẻ không?
4. Khi instrument một lớp do bootstrap loader định nghĩa, vì sao chỉ thêm helper vào system classpath thường chưa đủ?
5. Nếu báo `IllegalAccessError` thay vì `NoClassDefFoundError`, bạn sẽ kiểm tra điều gì khác?
6. Có thể đặt `appendToBootstrapClassLoaderSearch` sau khi lỗi resolve đã xảy ra rồi giả định lời gọi cũ sẽ hoạt động ngay không? Vì sao?
7. Khi có nhiều plugin loader, bạn sẽ chọn singleton bootstrap bridge hay helper riêng từng loader? Hãy nêu ưu/nhược và cách tránh memory leak.

## 10. Tài liệu chuẩn để tra cứu thêm

- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách nạp agent class và lưu ý liên quan module.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, `redefineModule`.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, loader identity và API nạp class.
- [JVMS 21 — Loading, Linking, and Initializing, Chương 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining/initiating loader, resolution symbolic reference, loader constraints và lỗi truy cập.
