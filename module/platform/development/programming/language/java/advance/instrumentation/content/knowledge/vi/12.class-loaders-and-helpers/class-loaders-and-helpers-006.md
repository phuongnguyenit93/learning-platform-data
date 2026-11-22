# Helper ở bootstrap chỉ liên kết với các lớp mà bootstrap có thể nạp

Trong Java Instrumentation, đôi khi agent cần một **helper class** để bytecode của các lớp hệ thống hoặc lớp do nhiều class loader khác nhau định nghĩa có thể gọi một hàm hỗ trợ thống nhất. Một lựa chọn là đưa helper vào **bootstrap class loader search** bằng `Instrumentation.appendToBootstrapClassLoaderSearch(...)` hoặc manifest `Boot-Class-Path`.

Nhưng sau khi helper được định nghĩa bởi **bootstrap loader**, các tham chiếu kiểu/class trong bytecode của helper phải được giải quyết theo khả năng **nạp lớp của bootstrap loader**, không phải dựa vào classpath của ứng dụng. Đặc tả package `java.lang.instrument` phát biểu trực tiếp: **supporting classes do agent bố trí để bootstrap định nghĩa chỉ được liên kết (*link*) tới những lớp do bootstrap định nghĩa**; cũng **không có bảo đảm mọi platform class đều do bootstrap định nghĩa**.

**Quy tắc cốt lõi:**

> **Một helper do bootstrap nạp không được phụ thuộc trực tiếp vào lớp chỉ có ở application/system/custom class loader.** Bootstrap đứng ở phía trên trong cơ chế delegation thông thường; nó không tự hỏi loader con xem có thể giải quyết lớp phụ thuộc hay không.

Bài này giải thích nguyên lý JVM, ý nghĩa thực tế của *link*, cách đưa helper vào bootstrap, ví dụ Java 17+ **chạy được** với lỗi `NoClassDefFoundError`, các mẫu giao tiếp an toàn, phân biệt loader visibility với Java module readability và checklist tránh lỗi khi viết agent.

## 1. Vì sao instrumentation cần bootstrap helper?

Một `ClassFileTransformer` có thể sửa bytes của class trước khi JVM định nghĩa chúng. Ví dụ muốn đo mỗi lần `java.util.SomeClass` thực thi method nào đó, công cụ biến đổi có thể chèn lệnh gọi:

~~~text
invokestatic lab/boot/BootHelper.record(Ljava/lang/String;)V
~~~

Đây là **mô tả symbolic bytecode**, không phải câu lệnh Java có thể chạy trực tiếp. JVM sẽ phải tìm và liên kết `lab.boot.BootHelper` khi đoạn code đã instrument được sử dụng.

Nếu helper chỉ có trong **agent JAR tải bởi system class loader**, lớp được định nghĩa bởi **bootstrap** có thể không giải quyết được tham chiếu đó. Việc agent tự gọi được helper không đồng nghĩa mã của `java.base` cũng gọi được, vì **loader khởi tạo việc giải quyết symbolic reference** có thể khác nhau.

Đưa một helper nhỏ vào bootstrap cho phép những class được định nghĩa bởi bootstrap tìm thấy helper ấy theo cơ chế nạp lớp của chính bootstrap. Nhưng helper bootstrap lại phải rất cẩn thận với **các phụ thuộc mà chính nó dùng**.

Sơ đồ điển hình (đơn giản hóa; JDK còn có platform loader):

~~~text
                  Bootstrap class loader
                   (Class.getClassLoader() = null)
                      ├─ java.lang.String
                      ├─ java.util.function.Supplier
                      └─ lab.boot.BootHelper  ← thêm bằng agent
                                │
                                │ tham chiếu tĩnh tới AppDependency?
                                ▼
                         KHÔNG tự tìm xuống dưới
                                ✕
                  Platform class loader
                                ▲
                                │ delegation thông thường
                                │
                   System/Application class loader
                      ├─ lab.agent.BootAgent
                      ├─ lab.app.Main
                      └─ lab.app.AppDependency

             Có thể còn custom/plugin loaders ở phía dưới.
~~~

Đường delegation thường đi **từ loader con lên parent** khi cần tìm class. Một loader cấp trên **không tự động dò ngược** classpath hoặc class định nghĩa ở các loader con. Một số loader tùy biến có thể dùng chiến lược khác, nhưng điều đó **không đổi giới hạn của helper đã được bootstrap định nghĩa**.

## 2. “Chỉ liên kết với các lớp bootstrap có thể nạp” nghĩa là gì?

Trong class file, phương thức có thể chứa **symbolic references** đến tên class, method, field và các type liên quan. JVM cần *resolution* các tham chiếu này trước hoặc khi thực thi những thao tác cần đến chúng.

Ví dụ, helper được bootstrap định nghĩa:

~~~java
package lab.boot;

public final class BootHelper {
    public static String unsafe() {
        return lab.app.AppDependency.value();
    }
}
~~~

Class `lab.app.AppDependency` có thể được biên dịch và hiện diện đầy đủ trong `app.jar`, thậm chí **đã được application class loader tải**. Điều đó vẫn **không khiến bootstrap loader có khả năng định nghĩa/tìm thấy `AppDependency` theo liên kết trực tiếp của helper**.

Khi JVM cần giải quyết tham chiếu từ `BootHelper` đến `lab.app.AppDependency`, lỗi thường thấy là:

~~~text
java.lang.NoClassDefFoundError: lab/app/AppDependency
~~~

Thời điểm lỗi phát sinh có thể tùy JVM và thời điểm resolution: trong ví dụ đơn giản bên dưới, nó xuất hiện khi gọi `unsafe()`; trong mã phức tạp hơn, verification, initialization, kiểu tham số, superclass/interface hoặc truy cập sâu bằng reflection cũng có thể làm lỗi lộ ra sớm hơn.

**Khác biệt cần phân biệt:**

| Câu hỏi | Câu trả lời |
|---|---|
| `AppDependency.class` có tồn tại trong app JAR không? | Có thể có |
| Application class loader có nạp được `AppDependency` không? | Có thể có |
| Bootstrap loader có nạp được `AppDependency` không? | **Không**, nếu class chỉ hiện diện ở application classpath và không nằm trong bootstrap search |
| Helper bootstrap có thể liên kết trực tiếp tới `AppDependency` chỉ vì app đã tải nó? | **Không** |
| Helper bootstrap có thể gọi code của ứng dụng bằng một callback qua interface mà bootstrap đã biết? | **Có thể**, nếu thiết kế đúng kiểu và loader như phần thực hành |

Với loader được JVM thể hiện qua `Class.getClassLoader()`:

~~~java
System.out.println(String.class.getClassLoader()); // null
System.out.println(BootHelper.class.getClassLoader()); // null nếu nạp bởi bootstrap
~~~

Đây là fragment bên trong method đã biết `BootHelper`. **`null` đại diện bootstrap loader** trong API `Class.getClassLoader()`, không phải “class không có loader” hoặc “JVM bỏ qua kiểm tra visibility”.

## 3. Bootstrap không đồng nghĩa “thấy mọi lớp của JDK”

JDK hiện đại thường có **bootstrap, platform và system/application class loaders**. Không nên rút ra kết luận “tên bắt đầu bằng `java.` hoặc `javax.` đều bootstrap định nghĩa”.

- Nhiều lớp quan trọng của **`java.base`** như `String`, `Object`, `Runnable`, `Supplier` có thể dùng làm kiểu giao tiếp ổn định cho bootstrap helper.
- Một số **platform classes/modules** được định nghĩa bởi **platform class loader** hoặc ở lớp module khác; đặc tả Instrumentation không bảo đảm bootstrap định nghĩa được tất cả platform classes.
- Một class của **agent** thường được định nghĩa bởi **system loader**, trừ khi agent bố trí một JAR phụ trợ để bootstrap nạp.
- Một class của **ứng dụng** thường ở system loader hoặc một **custom loader** (ví dụ plugin/container/framework).

**Điều cần hỏi là loader định nghĩa class nào**, không phải class có thuộc JDK hay là một phần của cùng file `.jar` mà bạn đang xem.

Ví dụ kiểm tra loader trong ứng dụng:

~~~java
static void showLoader(Class<?> type) {
    System.out.println(type.getName()
            + " -> " + type.getClassLoader());
}
~~~

Đây là một method minh họa để đặt bên trong class, không phải chương trình tự chạy. `getClassLoader() == null` là dấu hiệu bootstrap; với platform/application/custom loader, kết quả là object loader tương ứng. Khi log thực tế, nên ghi cả **class name, defining class loader và module** nếu đang điều tra Java 9+.

## 4. `appendToBootstrapClassLoaderSearch` làm gì, và không làm gì?

API chính thức:

~~~java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

Trong callback `premain`/`agentmain` của Java agent:

~~~java
java.util.jar.JarFile helperJar =
        new java.util.jar.JarFile("boot-helper.jar");
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
~~~

Đoạn này là **fragment**: biến `instrumentation` phải là `Instrumentation` do JVM cấp, đường dẫn là JAR có thật.

`appendToBootstrapClassLoaderSearch` chỉ định một **JAR để bootstrap tìm thêm khi việc tìm class theo cơ chế vốn có không thành công**. Có thể gọi nhiều lần, các JAR được bổ sung vào danh sách search theo thứ tự gọi. Nó không phải API “chuyển tất cả class đã tải qua bootstrap”.

**Không suy luận sai từ tên API:**

1. Không khiến bootstrap tự nhìn thấy **mọi class của application classpath**.
2. Không tự sao chép các class mà helper phụ thuộc từ agent JAR vào bootstrap.
3. Không chuyển **đối tượng `Class<?>` đã được định nghĩa bởi system loader** thành một class bootstrap.
4. Không thay đổi ngược lại các lần **symbolic reference resolution đã thất bại**: JVM có thể lưu kết quả giải quyết tham chiếu thất bại; chỉ thêm JAR sau đó chưa chắc chữa được liên kết đã lỗi.
5. Không tự bảo đảm mọi class trong JAR sẽ tải thành công: bản thân class ấy phải tuân thủ quy tắc linkage, accessibility và class-file version.
6. Không biến `-javaagent` thành `-Xbootclasspath`; đây là cơ chế Instrumentation được JDK định nghĩa.

**Hãy bổ sung helper JAR thật sớm** trong `premain`, trước khi biến đổi/tải những lớp sẽ gọi helper. Cần cẩn thận với việc tham chiếu đến helper từ code agent trước khi JAR được bổ sung vì điều đó có thể khiến helper bị loader không mong muốn định nghĩa trước.

Đặc tả còn cảnh báo **bootstrap helper JAR chỉ nên chứa các class/resource thực sự dành cho bootstrap instrumentation**. Không đặt toàn bộ agent, ứng dụng hoặc thư viện không liên quan vào đó.

## 5. Thực hành Java 17+: chứng minh lỗi trực tiếp và cách gọi an toàn

Bài thực hành dùng **ba JAR tách biệt**:

1. `boot-helper.jar`: chỉ có `lab.boot.BootHelper`, được bootstrap loader nạp.
2. `app.jar`: chứa `lab.app.Main` và `lab.app.AppDependency`, được application loader nạp.
3. `agent.jar`: chứa `lab.agent.BootAgent`; `premain` thêm `boot-helper.jar` vào bootstrap search.

Các file được **biên dịch cùng nhau** để Java compiler kiểm tra cú pháp và tham chiếu. Sau đó, chúng được **đóng gói tách biệt** để mô phỏng đúng ranh giới class loader khi chạy. Nếu bạn bỏ bước đóng gói tách biệt và để mọi class trong cùng application classpath, thí nghiệm không còn kiểm chứng đúng cơ chế bootstrap.

Cây thư mục:

~~~text
bootstrap-helper-lab/
├── src/
│   └── lab/
│       ├── boot/
│       │   └── BootHelper.java
│       ├── app/
│       │   ├── AppDependency.java
│       │   └── Main.java
│       └── agent/
│           └── BootAgent.java
├── MANIFEST.MF
└── out/                   sẽ tạo bằng javac
~~~

### 5.1. `src/lab/boot/BootHelper.java`

~~~java
package lab.boot;

import java.util.function.Supplier;

public final class BootHelper {
    private BootHelper() { }

    public static String safe() {
        return "boot-ok";
    }

    public static String unsafe() {
        return lab.app.AppDependency.value();
    }

    public static String viaCallback(Supplier<String> callback) {
        return callback.get();
    }
}
~~~

**Phân tích cả ba phương thức:**

- `safe()` chỉ sử dụng `String` từ `java.base` và literal; không có tham chiếu tới lớp ứng dụng.
- `unsafe()` có lời gọi **tĩnh** `AppDependency.value()`. Trong class file sẽ có symbolic reference tới `lab/app/AppDependency`, chỉ có trong **app JAR**. Khi `BootHelper` do bootstrap định nghĩa, nó không thể tự giải quyết tham chiếu này, dù ứng dụng có thể.
- `viaCallback(Supplier<String>)` có descriptor sử dụng **interface `Supplier` và `String` mà bootstrap biết**. Method không nhắc trực tiếp tên class ứng dụng; nó chỉ gọi `Supplier.get()`. Chính ứng dụng chịu trách nhiệm tạo implementation/lambda cho interface này.

Không nên coi `unsafe()` là thiết kế production. Nó được giữ trong bài chỉ để làm **thí nghiệm lỗi có chủ đích**.

### 5.2. `src/lab/app/AppDependency.java`

~~~java
package lab.app;

public final class AppDependency {
    private AppDependency() { }

    public static String value() {
        return "app-ok";
    }
}
~~~

Class này chỉ được đóng gói trong `app.jar`, **không có trong `boot-helper.jar`**. Đó là điều kiện cần của thí nghiệm về visibility.

### 5.3. `src/lab/app/Main.java`

~~~java
package lab.app;

import lab.boot.BootHelper;

public final class Main {
    public static void main(String[] args) {
        System.out.println("helperBootstrap="
                + (BootHelper.class.getClassLoader() == null));
        System.out.println("safe=" + BootHelper.safe());
        System.out.println("viaCallback="
                + BootHelper.viaCallback(AppDependency::value));

        try {
            System.out.println("unsafe=" + BootHelper.unsafe());
        } catch (NoClassDefFoundError e) {
            System.out.println("unsafeError="
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

**Tại sao callback lại chạy được?** `AppDependency::value` được tạo trong class của ứng dụng dưới dạng `Supplier<String>`; bootstrap helper chỉ thực hiện **interface invocation tới `Supplier.get()`**, không trực tiếp giải quyết tên `lab.app.AppDependency` trong constant pool của helper. JVM có thể thực hiện dynamic dispatch tới implementation được ứng dụng tạo ra. Đó là **giao tiếp qua một kiểu chung bootstrap-visible**, khác với việc helper tự chứa symbolic reference trực tiếp tới app class.

Đây là ví dụ minh họa cơ chế, **không phải khuyến nghị truyền bất kỳ object ứng dụng nào vào helper**. Với agent thực tế, cần kiểm soát tham chiếu, vòng đời object và rủi ro rò rỉ class loader.

`catch (NoClassDefFoundError)` chỉ để demo tiếp tục in kết quả. Không nên che một `LinkageError` tương tự trong production mà không có chẩn đoán và chiến lược khôi phục.

### 5.4. `src/lab/agent/BootAgent.java`

~~~java
package lab.agent;

import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

public final class BootAgent {
    public static void premain(String jarPath, Instrumentation inst)
            throws Exception {
        if (jarPath == null || jarPath.isBlank()) {
            throw new IllegalArgumentException(
                    "bootstrap helper JAR required");
        }

        inst.appendToBootstrapClassLoaderSearch(
                new JarFile(jarPath));

        Class<?> helper =
                Class.forName("lab.boot.BootHelper", false, null);
        System.out.println("agentSawBootstrap="
                + (helper.getClassLoader() == null));
    }
}
~~~

Trong ví dụ:

1. JVM nạp **agent JAR** bằng `-javaagent`.
2. `premain` nhận đường dẫn tới **bootstrap helper JAR** trong agent option.
3. `new JarFile(jarPath)` đại diện đúng JAR chỉ có các helper dùng cho bootstrap.
4. `inst.appendToBootstrapClassLoaderSearch(...)` bổ sung JAR vào bootstrap search.
5. `Class.forName(name, false, null)` yêu cầu tìm class với **bootstrap loader** (`null` là bootstrap), đồng thời `false` không yêu cầu chạy static initializer ở bước này.
6. `helper.getClassLoader() == null` xác nhận class thực tế được bootstrap định nghĩa.

Tại thời điểm này, `BootAgent` **không** gọi `BootHelper.unsafe()`, vì mục tiêu là kiểm tra loader trước rồi để `Main` chứng minh lỗi khi cần giải quyết tham chiếu tới `AppDependency`.

### 5.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.BootAgent

~~~

Manifest cần có **dòng trống cuối**. `Premain-Class` trỏ tới agent entrypoint; `BootHelper` **không phải** `Premain-Class`. Ví dụ dùng `appendToBootstrapClassLoaderSearch` trực tiếp nên không bắt buộc có `Boot-Class-Path` trong manifest.

### 5.6. Biên dịch và tạo đúng ba JAR

Mở terminal tại `bootstrap-helper-lab`. Tạo thư mục biên dịch.

Bash/Git Bash:

~~~bash
mkdir -p out
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Biên dịch tất cả file bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac --release 17 -d out src/lab/boot/BootHelper.java src/lab/app/AppDependency.java src/lab/app/Main.java src/lab/agent/BootAgent.java
~~~

`--release 17` làm bytecode phù hợp với Java 17; ví dụ sử dụng những API có sẵn trong phiên bản đó. **Đây chỉ là bước biên dịch chung**. Phần quan trọng của bài là **tách các class thành ba JAR khác nhau** ở bước sau:

~~~bash
jar --create --file boot-helper.jar -C out lab/boot/BootHelper.class
jar --create --file app.jar -C out lab/app/Main.class -C out lab/app/AppDependency.class
jar --create --file agent.jar --manifest MANIFEST.MF -C out lab/agent/BootAgent.class
~~~

Kiểm tra nội dung nếu cần:

~~~bash
jar --list --file boot-helper.jar
jar --list --file app.jar
jar --list --file agent.jar
~~~

`boot-helper.jar` chỉ được có `lab/boot/BootHelper.class` (ngoài cấu trúc metadata JAR tự sinh). **Không thêm** `AppDependency.class` hoặc `Main.class` vào bootstrap JAR, vì điều đó có thể che khuất sai lầm đang muốn quan sát và thay đổi class identity.

Lệnh chạy:

~~~bash
java -javaagent:agent.jar=boot-helper.jar -cp app.jar lab.app.Main
~~~

Tại runtime, classpath chính **chỉ có `app.jar`**; `agent.jar` được JVM xử lý như agent, còn `boot-helper.jar` được thêm qua API. Vì vậy `BootHelper` không thể tình cờ được application class loader nạp từ main classpath.

**Stdout đã được kiểm chứng khi biên dịch `--release 17` và chạy trên JDK 24:**

~~~text
agentSawBootstrap=true
helperBootstrap=true
safe=boot-ok
viaCallback=app-ok
unsafeError=NoClassDefFoundError
~~~

Một số JVM (trong đó có OpenJDK/HotSpot) có thể in thêm cảnh báo về **Class Data Sharing** khi bootstrap search path được mở rộng, ví dụ `Sharing is only supported for boot loader classes because bootstrap classpath has been appended`. Đây thường là **stderr của JVM**, không phải dòng stdout của chương trình và không thay đổi kết quả minh họa. Nếu JVM khác có thay đổi hoặc không hỗ trợ cơ chế như mong đợi, cần kiểm tra cấu hình/bản phân phối cụ thể.

### 5.7. Diễn giải kết quả từng dòng

| Dòng | Bằng chứng |
|---|---|
| `agentSawBootstrap=true` | Agent đã tra được `BootHelper` bằng `Class.forName(..., null)` và class thực tế do bootstrap định nghĩa |
| `helperBootstrap=true` | Ứng dụng cũng nhìn thấy **chính class helper của bootstrap** qua mô hình delegation |
| `safe=boot-ok` | Helper chạy được khi chỉ dùng các lớp và kiểu bootstrap có thể liên kết |
| `viaCallback=app-ok` | Truyền implementation của interface bootstrap-visible giúp gọi code ứng dụng qua dynamic dispatch |
| `unsafeError=NoClassDefFoundError` | Helper bootstrap **không thể liên kết trực tiếp** đến class chỉ nằm ở application loader |

Tình huống này chứng minh **việc ứng dụng đã biết `AppDependency` không mở rộng class search cho bootstrap helper**.

## 6. Tại sao app gọi được helper bootstrap nhưng helper không tự gọi được app?

**Chiều gọi không đồng nghĩa chiều tìm lớp.**

Khi `Main` (application loader) tham chiếu `BootHelper`, loader/application runtime thường ủy quyền cho bootstrap tìm `BootHelper` trước. Do helper đã nằm trong bootstrap search, JVM có thể giải quyết tên ấy.

Ngược lại, khi code bên trong `BootHelper` chứa một symbolic reference tới `AppDependency`, JVM giải quyết tham chiếu trong ngữ cảnh class **được định nghĩa bởi bootstrap loader**. Bootstrap không mặc định hỏi ngược system loader để tìm class ứng dụng.

~~~text
App Main (system loader)
    │  static reference tới BootHelper
    └─────────────────────────────► bootstrap tìm thấy BootHelper   ✓

BootHelper (bootstrap loader)
    │  static reference tới AppDependency
    └─────────────────────────────► bootstrap không thấy app class  ✗
                                      NoClassDefFoundError
~~~

Điều này cũng giải thích vì sao lỗi có thể xuất hiện dù:

- `java -cp app.jar ...` chạy đúng;
- `ClassLoader.getSystemClassLoader().loadClass("lab.app.AppDependency")` hoạt động;
- `AppDependency` thậm chí đã được hệ thống dùng trước đó;
- agent Java (system loader) có thể gọi `AppDependency` từ chính mã của agent.

Các quan sát đó **không thay đổi loader giải quyết tham chiếu tĩnh của helper bootstrap**.

## 7. Thiết kế bootstrap helper an toàn hơn

### Cách A — Helper cực nhỏ, chỉ phụ thuộc kiểu bootstrap-visible

Nếu chức năng đơn giản như đếm sự kiện hoặc tạo dữ liệu nguyên thủy, hãy giữ helper độc lập:

~~~java
package lab.boot;

import java.util.concurrent.atomic.LongAdder;

public final class CounterHelper {
    private static final LongAdder CALLS = new LongAdder();

    private CounterHelper() { }

    public static void hit() {
        CALLS.increment();
    }

    public static long count() {
        return CALLS.sum();
    }
}
~~~

`LongAdder`, `String`, `Throwable`, `Runnable`, `Supplier` là những kiểu từ `java.base` hữu ích ở ví dụ bootstrap helper. Đây là class Java hoàn chỉnh nhưng chỉ chạy khi class được **biên dịch, đóng JAR và nạp đúng**; `hit()` không tự được gọi nếu chưa có code gọi nó.

Điểm mạnh: không có tham chiếu tĩnh tới agent hoặc app class; ít nguy cơ class-loader linkage. Điểm cần nhớ: một static field của helper được giữ ở bootstrap có thể tồn tại suốt vòng đời JVM, nên tránh lưu object, `Class<?>`, loader hoặc callback của ứng dụng **mãi mãi** nếu có hot-reload/plugin unload.

### Cách B — Giao tiếp qua interface do bootstrap biết

Trong thí nghiệm, `Supplier<String>` thuộc `java.base` đóng vai trò hợp đồng chung:

~~~java
public static String viaCallback(Supplier<String> callback) {
    return callback.get();
}
~~~

Đây là **fragment bên trong `BootHelper`**, không phải chương trình chạy độc lập. Helper chỉ phải giải quyết interface `Supplier`. Instance lambda của app là **một object runtime**, JVM dispatch lời gọi đến implementation tương ứng mà không cần helper phải tham chiếu tĩnh tới lớp tạo lambda.

Với dự án phức tạp, có thể định nghĩa một **interface nhỏ riêng nằm trong bootstrap helper JAR**, còn implementation nằm trong system/custom loader:

~~~java
package lab.boot;

public interface EventSink {
    void accept(String name, long elapsedNanos);
}
~~~

Class interface trên là file Java độc lập (`EventSink.java`) và phải được **đóng vào bootstrap JAR** cùng helper; không được để mỗi loader tự định nghĩa một bản trùng tên. Ứng dụng có thể cung cấp implementation, còn helper chỉ gọi qua interface được bootstrap định nghĩa.

**Những lưu ý quan trọng:**

- Tránh các chữ ký API bootstrap chứa type chỉ có ở app loader, kể cả return type/field type hoặc generic code làm phát sinh cast/reflective access.
- Chỉ truyền các type/helper interface mà bootstrap đã biết; object động có thể do app loader định nghĩa nhưng bootstrap helper không được bắt buộc liên kết tĩnh tới implementation class.
- Cân nhắc giới hạn vòng đời callback: một `static EventSink` mạnh ở bootstrap có thể giữ sống cả application class loader và gây **class loader leak** khi redeploy.
- Khi nhiều class loader có implementation cùng tên, phải kiểm tra **class identity**, không chỉ `getName()`.

### Cách C — Giữ logic phụ thuộc ứng dụng ở phía ứng dụng

Không nhất thiết đưa **toàn bộ agent** vào bootstrap. Một thiết kế rõ ràng:

~~~text
Bootstrap helper (ít code, ít phụ thuộc)
    │
    ├── API bootstrap-visible để ghi nhận/signal
    │
    ▼
System/app-side component (phụ thuộc ứng dụng ở đây)
    │
    ├── metrics SDK
    ├── logging/backend client
    └── application-specific classes
~~~

Helper chỉ cung cấp điểm gọi nhỏ và chuyển tín hiệu/dữ liệu theo hợp đồng chung. Đặt logging framework, HTTP client, serializer hoặc mã phụ thuộc framework phía ứng dụng/agent khi chúng **không bootstrap-visible**. Cơ chế kết nối có thể qua callback/interface, queue hoặc message abstraction, nhưng cần tránh deadlock và recursive class loading.

Không nên biến helper bootstrap thành *service locator* tùy ý cho mọi class của ứng dụng.

## 8. Có thể nạp app class bằng explicit loader không?

**Có thể tra cứu phản chiếu qua một loader được cung cấp rõ ràng**, nhưng điều đó **không thay đổi quy tắc linking tĩnh** của helper.

Ví dụ fragment minh họa:

~~~java
ClassLoader appLoader = ClassLoader.getSystemClassLoader();
Class<?> type = Class.forName(
        "lab.app.AppDependency", false, appLoader);
~~~

Đoạn này dùng **explicit loader** để tra tên class bằng API phản chiếu. Nó không có nghĩa một lệnh `invokestatic lab/app/AppDependency.value` **đã được biên dịch sẵn trong bytecode helper** sẽ tự đổi loader resolution của mình.

Cũng không có bảo đảm **system loader** chứa mọi class của ứng dụng: application server, plugin, OSGi hoặc các môi trường isolation có thể dùng custom loader. `Thread.currentThread().getContextClassLoader()` đôi khi giúp tìm class theo ngữ cảnh của ứng dụng, nhưng thread context loader cũng không bảo đảm trỏ tới loader chứa dependency cần tìm.

Khi dùng reflection hoặc `MethodHandle`, cần xét:

1. Cung cấp **đúng ClassLoader** và xác thực nguồn của class.
2. Quyền truy cập Java: public, package-private, module exports/opens.
3. Ràng buộc method signature và identity của type/loader.
4. Lỗi khi class bị unload/redeploy và các reference dài hạn có thể gây leak.
5. Chi phí reflection, khả năng exception và sự ổn định của API.

Với một helper cần được gọi từ bytecode của `java.base`, giao tiếp qua interface bootstrap-visible thường dễ kiểm soát hơn việc helper tự tìm app classes bằng tên.

## 9. `Boot-Class-Path` và `appendToSystemClassLoaderSearch` khác gì?

Có nhiều cơ chế để agent bố trí helper, nhưng **không đồng nghĩa về loader**:

| Cơ chế | Bổ sung vào tìm kiếm của loader nào? | Trường hợp thường gặp |
|---|---|---|
| `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` | **Bootstrap** | Helper cần được bootstrap-loaded class gọi |
| Manifest agent `Boot-Class-Path` | **Bootstrap** | Agent khai báo helper paths ngay trong manifest |
| `Instrumentation.appendToSystemClassLoaderSearch(JarFile)` | **System** | Helper dùng tại system/application loader và các loader con phù hợp |
| Classpath ứng dụng `-cp` | **System** (trong cấu hình JVM thông thường) | Lớp ứng dụng, thư viện |
| Một custom `ClassLoader#defineClass` | **Custom loader đó** | Plugin hoặc module isolations |

**Ví dụ manifest dùng `Boot-Class-Path`:**

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.BootAgent
Boot-Class-Path: boot-helper.jar

~~~

Đây là **ví dụ cấu hình thay thế**, không phải manifest đang dùng trong bài chạy ở phần 5. Đường dẫn tương đối của `Boot-Class-Path` được giải quyết theo quy tắc manifest agent đối với đường dẫn agent JAR; phải bảo đảm helper JAR có thực và ở đúng vị trí.

`appendToSystemClassLoaderSearch` không làm system loader thấy **mọi** class do custom child loader tải. Tương tự, không thể dùng system search để giải quyết một symbolic reference nằm trong class bootstrap theo cách tự động. **Đúng class loader cho helper** là một quyết định thiết kế quan trọng.

## 10. Java 9+ module readability không thay thế class-loader visibility

Từ Java 9, mỗi class còn thuộc về một **module**. Class được bố trí trong bootstrap helper JAR thông qua bootstrap search thường nằm trong **unnamed module của bootstrap loader**.

Đặc tả `java.lang.instrument` có một hỗ trợ quan trọng: để các class đã được transformer biến đổi có thể gọi supporting classes, JVM **bố trí module của class được transform đọc được unnamed module của bootstrap loader và unnamed module của loader nạp agent class**. Điều này giúp giải quyết một phần yêu cầu **module readability** khi chèn tham chiếu helper vào transformed code.

Nhưng **readability và class-loader visibility là hai chiều kiểm tra khác nhau**:

~~~text
Bài toán A: class đã transform → bootstrap helper
  - Tìm class: loader resolution
  - Đọc module: JPMS readability
  - Truy cập: public/package/exports và các quy tắc JVM liên quan

Bài toán B: bootstrap helper → class chỉ có ở application loader
  - Bootstrap vẫn không tự tìm xuống application loader.
  - Có thêm read edge cũng KHÔNG biến AppDependency thành bootstrap class.
~~~

Đừng dùng `--add-reads` hoặc `Instrumentation.redefineModule` như “cách sửa lỗi class not found” một cách máy móc. Chúng giải quyết **quan hệ đọc module**, không di chuyển class qua loader hay thay đổi hướng delegation. Nếu thật sự là lỗi quyền truy cập module, cần xác định rõ module nào đọc module nào, package nào được export/open và đối tượng caller thực tế.

Ngược lại, nếu lỗi là `NoClassDefFoundError` vì class chỉ nằm trong app loader, thêm read edge **không làm bootstrap tìm được class đó**.

## 11. `NoClassDefFoundError`, `ClassNotFoundException` và lỗi truy cập

Khi thiết kế bootstrap helper, cần đọc đúng **loại lỗi**:

| Lỗi/hiện tượng | Ý nghĩa phổ biến | Hướng chẩn đoán |
|---|---|---|
| `NoClassDefFoundError: lab/app/AppDependency` | Resolution một class tham chiếu từ bytecode không tìm thấy định nghĩa phù hợp | Kiểm tra **defining loader của helper**, bootstrap search, classpath và cách helper tham chiếu |
| `ClassNotFoundException` | API nạp theo tên như `Class.forName`/`loadClass` không tìm thấy class theo loader được yêu cầu | Kiểm tra tên nhị phân và loader truyền vào API |
| `IllegalAccessError` | Class có thể được tìm thấy nhưng liên kết/truy cập không được phép | Kiểm tra access flags, runtime package, module access, class identity |
| `NoSuchMethodError` / `NoSuchFieldError` | Đã tìm class nhưng descriptor của member không khớp hoặc thiếu | Kiểm tra phiên bản helper bị nạp, JAR trùng class, linkage |
| `ClassCastException` | Hai object/type không tương thích; có thể do cùng tên nhưng khác loader | Log `Class<?>`, loader và module của cả hai type |
| `UnsupportedClassVersionError` | Helper bytes được biên dịch cao hơn JVM hỗ trợ | Dùng `javac --release` phù hợp runtime |
| `ExceptionInInitializerError` | Lỗi khi chạy static initializer của một class | Xem cause; có thể bắt nguồn từ dependency/load |
| Helper nạp bởi system loader dù dự định bootstrap | JAR nằm ở app path hoặc bị load trước khi append | Kiểm tra `getClassLoader()`, thứ tự startup và đóng gói |

Điểm nguy hiểm: **một tên package giống nhau không bảo đảm cùng runtime package**. Package được xem xét cùng với **defining class loader**; class `p.C` do bootstrap định nghĩa và class `p.D` do application loader định nghĩa không mặc nhiên có quyền truy cập package-private lẫn nhau. Đặc tả `appendToBootstrapClassLoaderSearch` còn nêu trường hợp một accessor class như `C$1` bị bootstrap bắt nhầm từ JAR đã append, dẫn tới `IllegalAccessError`.

Đừng xem tất cả lỗi thành “thêm JAR vào classpath là xong”. Cần biết **ai đang cố resolve class nào**, và **loader của class chứa symbolic reference**.

## 12. Tại sao nên dùng package riêng cho bootstrap helper?

Khi append một JAR vào bootstrap search, JAR ấy có thể được tìm thấy từ **nhiều loader con** qua cơ chế delegation. Nếu dùng package hoặc class name trùng với class của ứng dụng, tên trùng có thể bị bootstrap nạp trước:

~~~text
Không nên:
  agent-helper.jar chứa com/example/internal/Util.class
  app.jar          cũng có com/example/internal/Util.class

Có chủ đích hơn:
  agent-helper.jar chứa io/example/instrumentation/boot/RecorderBridge.class
  app.jar          chứa com/example/service/Util.class
~~~

Hai đường dẫn trên là **ví dụ thiết kế**, không phải đường dẫn đến tài nguyên thật. Tên package riêng giúp giảm rủi ro:

- Bootstrap định nghĩa nhầm class vốn thuộc ứng dụng.
- Accessor class không public bị nạp dưới loader khác, gây lỗi package-private.
- Trùng các thư viện phụ thuộc/phiên bản làm phát sinh `NoSuchMethodError`.
- Class identity khác dự kiến gây `ClassCastException`.
- Custom loader khác nhau nạp nhiều bản cùng tên khiến trạng thái static không chia sẻ như mong muốn.

Không đặt toàn bộ dependency tree của agent vào bootstrap chỉ để “cho helper thấy hết”. Cách đó dễ gây ảnh hưởng toàn JVM và rất khó điều tra khi có nhiều agent.

## 13. Những hạn chế về class loading sớm và kiểm chứng runtime

### Append càng sớm càng tốt

Trong `premain`:

~~~text
JVM start
   ↓
nạp agent class
   ↓
premain → append bootstrap helper JAR
   ↓
đăng ký transformer / chuẩn bị instrumentation
   ↓
class đích được transform, định nghĩa và gọi helper
~~~

Lý do: nếu symbolic reference đã được JVM thử resolve **thất bại**, việc bổ sung JAR sau đó không nhất thiết khiến resolution được làm lại. Nếu class helper từng được application loader định nghĩa trước, thêm cùng tên vào bootstrap search **không biến class object hiện có thành class bootstrap**. Môi trường class loading song song còn khiến race khó tái hiện.

### Kiểm tra loader bằng mã, không chỉ vị trí JAR

Các phép kiểm tra minh họa:

~~~java
Class<?> helper =
        Class.forName("lab.boot.BootHelper", false, null);

System.out.println(helper.getClassLoader() == null);
System.out.println(helper.getModule());
~~~

`Class.forName(..., false, null)` yêu cầu bootstrap tìm tên được cho. `Class.getClassLoader() == null` xác nhận defining loader trong mô hình API. `getModule()` cho thông tin module (trong thực hành này helper không phải một named module).

### Dùng JVM class-loading diagnostics khi cần

Với JDK 17+:

~~~bash
java -Xlog:class+load=info -javaagent:agent.jar=boot-helper.jar -cp app.jar lab.app.Main
~~~

`-Xlog:class+load` ghi nhiều thông tin (thường rất dài). Tìm dòng liên quan `lab.boot.BootHelper`, `lab.app.AppDependency` và vị trí/nguồn nạp. Không cần bật verbose log ở toàn bộ workload production nếu không có mục tiêu chẩn đoán cụ thể.

Tránh nhầm **classpath trông có chứa class** với **loader thực tế đã định nghĩa class**. Trong môi trường plugin/application server, class còn có thể được define bởi custom loader qua các nguồn không thể suy ra từ `java.class.path` đơn thuần.

## 14. Khi helper muốn dùng logging, metrics hoặc SDK của ứng dụng

Một mẫu sai dễ gặp:

~~~java
package lab.boot;

public final class TracingHelper {
    public static void record(String operation) {
        com.acme.app.metrics.MetricsClient.send(operation);
    }
}
~~~

Đây là **fragment minh họa lớp có dependency không phù hợp**, không phải ví dụ để triển khai. Nếu `MetricsClient` chỉ được nạp bởi system/custom app loader, helper bootstrap sẽ không thể liên kết trực tiếp.

Các lựa chọn hợp lý:

1. **Đo/lưu sự kiện tối thiểu ở bootstrap** bằng kiểu JDK bootstrap-visible, rồi đẩy ra ngoài qua giao tiếp kiểm soát.
2. **Định nghĩa một interface giao tiếp nhỏ ở bootstrap** và cung cấp implementation từ app/agent loader. Không để bootstrap chứa type signatures của implementation.
3. **Đặt thư viện SDK ở phía agent/app loader**, không kéo toàn bộ SDK xuống bootstrap; tránh trùng dependency và class identity.
4. **Quản lý vòng đời**: bootstrap static field giữ callback/loader có thể cản redeploy và unload; cần cách deregister/cleanup.
5. **Kiểm soát lỗi**: một helper chèn vào bytecode hệ thống không nên để lỗi metrics che lỗi nghiệp vụ hoặc làm hỏng quá trình class loading.
6. **Cân nhắc tác động recursion**: class loading, logging, `Class.forName` hoặc instrumentation trong chính helper có thể kích hoạt thêm transformer; nên filter lớp helper khỏi transform nếu thiết kế yêu cầu.

Ví dụ bridge qua `Supplier` chỉ nhằm chứng minh **không có tham chiếu tĩnh ngược tới app class**. Không phải lời đảm bảo rằng callback bất kỳ luôn thread-safe, không deadlock hoặc thích hợp cho mọi phiên bản JVM.

## 15. Checklist thiết kế helper bootstrap

Trước khi đưa một class vào bootstrap helper JAR:

1. **Liệt kê dependencies tĩnh**: superclass, interfaces, field/method descriptors, method bodies, các library calls. Không phụ thuộc trực tiếp vào class chỉ có ở app/custom loader.
2. **Kiểm tra JDK types**: không suy luận mọi platform module đều bootstrap-defined; dùng kiểu thật sự bootstrap-visible.
3. **Đóng gói JAR nhỏ, package riêng**: không trộn app classes, toàn bộ agent hoặc thư viện bên thứ ba không cần thiết.
4. **Append đúng thời điểm**: gọi `appendToBootstrapClassLoaderSearch` trước khi class mục tiêu hoặc helper bị resolve theo đường không mong muốn.
5. **Kiểm chứng defining loader**: `getClassLoader() == null` cho helper, xác nhận app dependency thuộc loader khác.
6. **Thiết kế chiều giao tiếp**: nếu cần gọi code phía ứng dụng, dùng interface/callback bootstrap-visible hoặc cơ chế message có kiểm soát.
7. **Xét module/readability**: phân biệt loader visibility với JPMS read/export/open; đừng sửa module khi nguyên nhân là class search.
8. **Kiểm thử cả thành công và thất bại**: helper chỉ dùng JDK → chạy; helper tham chiếu app class → có thể `NoClassDefFoundError`; callback qua kiểu chung → chạy khi đúng điều kiện.
9. **Bảo toàn vòng đời và tính an toàn**: tránh giữ static references kéo dài tới application class loaders; kiểm tra concurrency, exception và overhead.
10. **Kiểm tra target runtime**: `javac --release` phải phù hợp JVM; class được instrument và helper phải vượt qua verifier/linker.

Một bootstrap helper “đơn giản” nhưng phụ thuộc ngầm vào thư viện hệ thống (logging, tracing, JSON) có thể làm toàn bộ instrumentation hỏng ngay khi class JDK đầu tiên cố gọi helper.

## 16. Câu hỏi tự kiểm tra

1. **Bootstrap helper có thể gọi trực tiếp một class chỉ nằm trong application classpath không?** Không theo liên kết bytecode tĩnh thông thường; bootstrap không tìm ngược xuống loader ứng dụng.
2. **Vì sao `BootHelper.safe()` chạy mà `BootHelper.unsafe()` lỗi?** `safe` chỉ dùng bootstrap-visible types; `unsafe` chứa symbolic reference tới `lab.app.AppDependency` do app loader nạp.
3. **`AppDependency` đã được application loader nạp trước đó có khắc phục được lỗi không?** Không. Bootstrap vẫn giải quyết reference theo khả năng của bootstrap.
4. **`Class.getClassLoader() == null` là dấu hiệu gì?** Class được bootstrap loader định nghĩa (theo API Java).
5. **`appendToBootstrapClassLoaderSearch` có tự kéo theo mọi dependency của agent vào bootstrap không?** Không; nó chỉ bổ sung các JAR cụ thể vào bootstrap search.
6. **Vì sao `BootHelper.viaCallback(AppDependency::value)` hoạt động?** Helper chỉ liên kết với `Supplier`/`String` đã bootstrap-visible; implementation do application loader tạo được gọi bằng interface dispatch.
7. **Có thể thay `Supplier` bằng interface riêng không?** Có, nếu interface chung nằm ở bootstrap và không chứa các type chỉ có ở application loader.
8. **Vì sao không đưa toàn bộ agent JAR vào bootstrap?** Dễ gây trùng class, lỗi accessibility, dependency và thay đổi class loading ngoài ý định.
9. **`Boot-Class-Path` khác `-cp` ở điểm nào?** Nó bổ sung search path của bootstrap theo manifest agent; `-cp` thông thường thuộc system/application loader.
10. **`--add-reads` có làm bootstrap tìm thấy `AppDependency` do app loader định nghĩa không?** Không. Readability module và class-loader visibility là hai vấn đề khác nhau.
11. **`ClassNotFoundException` và `NoClassDefFoundError` có luôn cùng ý nghĩa?** Không. Một lỗi thường xuất hiện từ API lookup có kiểm tra theo tên, lỗi còn lại thường từ class linkage/resolution.
12. **Một JAR append vào bootstrap có thể gây `IllegalAccessError` không?** Có, nếu class/accessor không public bị loader khác định nghĩa làm thay đổi runtime package/access.
13. **Helper bootstrap có dùng được mọi class thuộc platform module?** Không có bảo đảm như vậy theo đặc tả `java.lang.instrument`.
14. **Gỡ app plugin có thể bị ngăn nếu bootstrap giữ `static` reference đến implementation của plugin?** Có. Đây là nguồn class-loader leak cần quản lý.
15. **Muốn biết lỗi liên kết bắt nguồn từ class nào, nên làm gì?** Kiểm tra class chứa symbolic reference, defining loader, JAR search, module/access và kết quả loader diagnostics.

### Nguồn tham khảo chính thức

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): **supporting bootstrap classes chỉ link với bootstrap-defined classes**, class loader của agent, `Boot-Class-Path` và module readability hỗ trợ.
- [Java SE 21 — `Instrumentation.appendToBootstrapClassLoaderSearch`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): search path, cảnh báo không trộn class/resource, ví dụ `IllegalAccessError` và lỗi resolution đã thất bại.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/platform/system loaders và delegation.
- [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `forName` và defining loader.
- [Java Virtual Machine Specification SE 21, §5 — Loading, Linking, Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): symbolic references, runtime package và resolution.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): module readability và các quan hệ module.

**Ghi nhớ:** **bootstrap helper chỉ liên kết trực tiếp với lớp mà bootstrap có thể nạp/định nghĩa**. Đưa helper vào bootstrap giúp mã bootstrap gọi được helper nhưng **không cấp cho helper quyền nhìn ngược application class loader**. Khi cần gọi logic ứng dụng, giữ các phụ thuộc application-side và kết nối qua interface/callback bootstrap-visible có kiểm soát.