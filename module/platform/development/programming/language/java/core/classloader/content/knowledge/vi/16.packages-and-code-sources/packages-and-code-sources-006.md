# SecureClassLoader và vai trò lịch sử của quyền truy cập

> **Java Core → ClassLoader → Package và nguồn mã.** `java.security.SecureClassLoader` mở rộng `ClassLoader` để gắn `CodeSource` và `ProtectionDomain` cho lớp được định nghĩa, đồng thời cung cấp hook `getPermissions(CodeSource)`. Nó ra đời trong mô hình bảo mật Java có `SecurityManager` và các file policy. **Từ JDK 24, Security Manager bị vô hiệu hóa vĩnh viễn:** giữ lại `SecureClassLoader` không làm plugin trở thành code bị sandbox. Bài học phân biệt API còn hữu ích, cơ chế cấp quyền mang tính lịch sử, kết quả thực tế và phương án bảo vệ phù hợp với JVM hiện đại.

## 1. Tóm tắt đúng trước khi viết code

Ba khẳng định cần tách riêng:

1. **SecureClassLoader là một ClassLoader thật.** Nó có thể đọc class-file bytes, định nghĩa class runtime, giao tiếp với parent, duy trì namespace của lớp và gắn `CodeSource`/`ProtectionDomain` như API quy định.
2. **PermissionCollection là metadata/cơ chế thuộc mô hình cũ.** Trước đây, khi một `SecurityManager` đang được bật, các permission checks có thể dựa trên `ProtectionDomain` trong access-control context. `getPermissions(CodeSource)` giúp một subclass góp phần tính permissions cho lớp mới.
3. **Trong JDK 24+, không có Security Manager để thực thi mô hình policy-based sandbox đó.** Tự trả về tập permissions rỗng từ `getPermissions` **không ngăn** class đọc file, môi trường hay mở kết nối mạng nhờ cơ chế `SecurityManager` nữa. Việc hệ điều hành/container và các API chuyên biệt kiểm soát tài nguyên là chuyện riêng.

Có thể nhớ:

```text
SecureClassLoader
  = ClassLoader + hỗ trợ CodeSource / ProtectionDomain / permissions metadata

SecureClassLoader != "untrusted-code sandbox" trên Java hiện đại

Class identity: (binary name, defining loader)
Source metadata: CodeSource(location, certificates/signers)
Legacy authorization: SecurityManager + AccessController + Policy + Permissions
Modern JDK 24+: legacy authorization cơ bản không còn hoạt động
```

`SecureClassLoader` **không bị xóa chỉ vì Security Manager không còn**. Nó vẫn là superclass công khai của `URLClassLoader` và vẫn có overload `defineClass` nhận `CodeSource`. Tuy vậy, không nên hiểu tên class chứa chữ “Secure” như một lời hứa an toàn.

## 2. SecureClassLoader đứng ở đâu trong cây ClassLoader?

Hệ kế thừa cơ bản:

```text
java.lang.Object
  └── java.lang.ClassLoader
        └── java.security.SecureClassLoader
              └── java.net.URLClassLoader
```

Một custom loader có thể extends trực tiếp `ClassLoader` hoặc `SecureClassLoader`:

- **Extends `ClassLoader`:** thường override `findClass` rồi gọi `defineClass(String, byte[], int, int, ProtectionDomain)` khi muốn gắn domain tự tạo.
- **Extends `SecureClassLoader`:** thêm các overload `defineClass(..., CodeSource)`; implementation của nó xây `ProtectionDomain` thích hợp từ `CodeSource` và permission hook.
- **Dùng `URLClassLoader`:** nếu nguồn chính là directory/JAR URLs, class loader chuẩn đã xử lý phần lớn công việc tìm JAR class/resources và code source. Không nhất thiết cần tự viết lại `findClass`.

Ví dụ tạo subclass:

```java
import java.security.SecureClassLoader;

public final class MyLoader extends SecureClassLoader {
    public MyLoader(ClassLoader parent) {
        super(parent);
    }

    // Override findClass khi cần đọc bytes từ nguồn riêng.
}
```

Đây là một class **biên dịch được**, không có `main`. Nó không nạp class từ nguồn mới cho đến khi bạn thực sự cài đặt `findClass` hoặc cấu hình một cơ chế tìm source.

Cũng như các loader khác, việc gọi `loadClass("demo.Task")` không luôn khiến `MyLoader` là defining loader: parent-first delegation có thể trả về class do parent định nghĩa. Phân biệt **loader được yêu cầu tìm** với **loader thực sự định nghĩa**.

## 3. API trọng tâm của SecureClassLoader

Các phương thức chuyên biệt:

```java
protected final Class<?> defineClass(
        String name,
        byte[] b, int off, int len,
        java.security.CodeSource cs);

protected final Class<?> defineClass(
        String name,
        java.nio.ByteBuffer b,
        java.security.CodeSource cs);

protected java.security.PermissionCollection getPermissions(
        java.security.CodeSource codesource);
```

Đây là **signatures minh họa**, không thể copy thành một file Java độc lập. Chúng là `protected` nên thường được gọi/override từ subclass phù hợp.

Ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `name` | Binary name kỳ vọng, ví dụ `demo.Task`, không phải `demo/Task.class`. |
| `b` | JVM class-file bytes hợp lệ của một lớp/interface. Không nhận Java source. |
| `off`, `len` | Đoạn dữ liệu hợp lệ trong `byte[]`; `len` là số byte, không phải end index. |
| `ByteBuffer` | Đầu vào bytes trong vùng được xác định bởi `position()/limit()` theo API. |
| `CodeSource cs` | Mô tả nguồn code của class, có thể `null`. |
| `getPermissions(cs)` | Hook tạo `PermissionCollection` gắn vào protection domain trong đường define có CodeSource. |

Nếu `cs` khác `null`, overload `SecureClassLoader#defineClass` tạo protection domain gắn với class. Các method `defineClass` là `final`: không override chúng; thay đổi policy tìm bytes ở `findClass`, permission metadata ở `getPermissions` hoặc cấu hình của loader.

Không nhầm `ClassLoader.defineClass(..., ProtectionDomain)` với `SecureClassLoader.defineClass(..., CodeSource)`: loại tham số cuối khác nhau. `SecureClassLoader` giúp từ code source đi tới domain, còn `ClassLoader` cho phép truyền domain đã được chuẩn bị.

## 4. CodeSource: mô tả nguồn code, không tự xác minh nguồn

`java.security.CodeSource` biểu diễn thông tin về **location URL** và certificates/signers liên quan.

Tạo nguồn mã cho bytes đọc từ một thư mục:

```java
// Trong method có import java.nio.file.Path, java.net.URL,
// java.security.CodeSource và java.security.cert.Certificate:
URL location = Path.of("plugin-classes")
        .toAbsolutePath().toUri().toURL();
CodeSource cs = new CodeSource(
        location, (java.security.cert.Certificate[]) null);
```

Trong JAR loader, location thường trỏ tới nguồn archive thực tế thay vì trỏ tùy tiện đến entry `.class`. Tuy nhiên:

- `new CodeSource(location, null)` chỉ gắn **metadata mà bạn cung cấp**. Nó không kiểm tra bytes thật được đọc từ URL ấy.
- Location không bắt buộc luôn khác `null` trong mọi domain; không viết `pd.getCodeSource().getLocation()` mà không kiểm tra nullable trong code sản phẩm.
- `null` certificates nghĩa là **không có certificate metadata được cung cấp**; không đồng nghĩa “JAR đã ký và xác minh”.
- Nếu nguồn là signed JAR, việc xác thực chữ ký cần đi qua API và quy trình JAR verification phù hợp, đọc/kiểm tra entries đúng cách; chỉ dựng thủ công một `CodeSource` không thay cho bước đó.
- Hai loader độc lập có thể định nghĩa class cùng binary name với cùng `CodeSource.location` mà vẫn tạo **hai runtime types khác nhau**. Type identity được quyết định bởi tên và defining loader, không phải nguồn URL.

Để chẩn đoán class thật:

```java
Class<?> clazz = /* lấy từ loader cần kiểm tra */;
ClassLoader definingLoader = clazz.getClassLoader();
java.security.ProtectionDomain pd = clazz.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();
java.net.URL url = source == null ? null : source.getLocation();
```

Đây là snippet có `clazz` đã được cung cấp; comment placeholder chỉ mô tả biến cần có, không là một chương trình chạy. `url` giúp xác định metadata nguồn, nhưng không phải chứng thực mật mã hay bằng chứng duy nhất về đường đi nạp class.

## 5. ProtectionDomain: từ CodeSource tới bối cảnh quyền hạn lịch sử

`ProtectionDomain` gắn metadata domain với một class. Trước đây, các domain trên call stack và access-control context đóng vai trò trong quyết định quyền truy cập khi `SecurityManager` kiểm tra permission.

Mô hình cổ điển:

```text
class bytes -> SecureClassLoader.defineClass(..., CodeSource)
                       |
                       v
           getPermissions(CodeSource)
                       |
                       v
           ProtectionDomain(CodeSource,
                            PermissionCollection,
                            ClassLoader, ...)
                       |
                       v
                    Class<?>
                       |
                       v
          Legacy SecurityManager permission checks
                       |
                       +--> grant/deny theo domain/context/policy
```

Đây là sơ đồ lịch sử, **không phải cơ chế sandbox đang hoạt động trên JDK 24+**.

Các getter thường hữu ích:

```java
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd.getCodeSource();
PermissionCollection permissions = pd.getPermissions();
```

Cần import đúng `java.security.*` hoặc tên đầy đủ; đây là snippet, `clazz` phải có trước. `getPermissions()` có thể trả `null` tùy đường định nghĩa class. Một `PermissionCollection` rỗng đơn giản là không liệt kê static permission tương ứng, **không chứng minh** một I/O operation sẽ bị từ chối trên JVM hiện đại.

### Những permission kiểu cũ

Các loại `Permission` lịch sử thường gặp:

| Permission | Mục đích cũ |
| --- | --- |
| `java.io.FilePermission` | Quyền đọc/ghi/xóa file theo đường dẫn. |
| `java.net.SocketPermission` | Quyền kết nối/nghe/resolve theo host/port. |
| `java.util.PropertyPermission` | Quyền đọc/ghi system property. |
| `java.lang.RuntimePermission` | Quyền cho các thao tác JVM nhất định. |
| `java.security.AllPermission` | Nhận mọi permission trong mô hình Security Manager; đặc biệt nguy hiểm nếu policy cấp nhầm. |

Khi Security Manager còn bật, các phép kiểm tra quyền phù hợp có thể dẫn đến `AccessControlException`. Khi nó không bật, nhiều operations không hỏi permission policy kiểu này. Từ JDK 24, **không thể bật lại** Security Manager để dựa vào chúng.

### getPermissions không phải quy tắc truy cập tùy ý cho mọi API

`SecureClassLoader#getPermissions(CodeSource)` là hook trả về permissions được gắn khi tạo protection domain. Nó **không** tự chặn `Files.readString`, `System.getProperty` hoặc `Socket.connect` bằng cách throw/return bộ permissions rỗng trong một JVM không có Security Manager. Nếu muốn áp dụng kiểm soát quyền ở tầng business, bạn phải đặt kiểm tra vào **chính API/service boundary do mình sở hữu** hoặc dùng isolation của OS/process. Kiểm tra nội bộ ấy không chặn code Java tùy ý gọi các thư viện JDK khác trong cùng process.

## 6. Lịch sử SecurityManager, Policy và AccessController

### Trước khi bị loại khỏi đường thực thi

Java từng có mô hình an ninh dựa trên khả năng kiểm tra permissions trong một process:

1. Class được loader định nghĩa cùng một `ProtectionDomain`.
2. `CodeSource` mô tả vị trí code và metadata certificates.
3. Chính sách `java.security.Policy` có thể cấp quyền theo nguồn/signers.
4. `SecurityManager` khi được bật, cùng các điểm kiểm tra do API nền tảng thực hiện, sẽ hỏi quyền.
5. `AccessController.checkPermission(...)`/`doPrivileged(...)` tham gia mô hình stack-based access control.

Ví dụ policy file **chỉ để nhận diện ứng dụng cũ**:

```text
grant codeBase "file:/opt/legacy/plugins/-" {
    permission java.util.PropertyPermission "app.config", "read";
    permission java.io.FilePermission "/opt/legacy/plugins/-", "read";
};
```

Đây không phải cấu hình nên dùng để bảo vệ plugin trên JDK hiện đại. `-Djava.security.policy` không còn có tác dụng bảo mật như trước ở JDK 24+.

`AccessController.doPrivileged` từng dùng để thực hiện thao tác trong scope xác định với semantics stack-inspection riêng. Nó **không** nên được hiểu đơn giản là “bật chế độ admin” hay “cho phép đoạn code vô hạn quyền” trong mọi trường hợp. Trước đây kết quả còn phụ thuộc policy, protection domains và ngữ cảnh gọi.

### Dòng thời gian cần nhớ

| Phiên bản Java | Tình trạng |
| --- | --- |
| Java 1.2 trở đi | Security architecture có `ProtectionDomain`, `CodeSource`, `SecureClassLoader`, `Policy` và `SecurityManager`. |
| Java 8 và các phiên bản cũ | Nhiều applet/Web Start/container có mô hình cấp quyền và kiểm tra security policy; không có nghĩa mọi app bật Security Manager. |
| Java 17 | **JEP 411** deprecate Security Manager **for removal**; vẫn có khả năng tương thích, nhưng nhà phát triển được khuyên chuyển đổi. |
| Java 17–23 | Các lựa chọn bật/dùng Security Manager cũ còn tồn tại với giới hạn/cảnh báo theo bản phát hành. |
| **JDK 24 trở lên** | **JEP 486** vô hiệu hóa Security Manager **vĩnh viễn**; không thể cài hoặc kích hoạt theo cách cũ. API liên quan vẫn còn một thời gian để hỗ trợ chuyển đổi nhưng có hành vi bị giới hạn/thay đổi. |

Bài học này bàn về **vai trò lịch sử** đúng nghĩa: tìm hiểu vì sao API được thiết kế như vậy, nhưng không áp dụng một security model đã vô hiệu hóa cho một JVM đang chạy JDK 24+.

## 7. Điều gì thay đổi khi Security Manager bị vô hiệu hóa từ JDK 24?

Theo tài liệu chính thức của Oracle và **JEP 486**:

- Không thể bật Security Manager bằng `-Djava.security.manager=...` ở lúc khởi động: JVM báo lỗi.
- `System.setSecurityManager(...)` ném `UnsupportedOperationException`; `System.getSecurityManager()` luôn trả `null`.
- `AccessController.doPrivileged(...)` thực thi action trực tiếp theo semantics không có Security Manager; không còn là cách tạo ranh giới cấp quyền theo call stack.
- `AccessController.checkPermission(...)` **luôn ném `AccessControlException`** trong JDK 24+, nên đừng dùng nó làm phép “test có quyền hay không” cho app hiện đại.
- `Policy.getPolicy()` trả policy không cấp quyền; các phương thức thiết lập policy và API liên quan có hành vi bị ràng buộc. Chính sách từ `java.policy` không còn là cơ chế enforcement.
- `ProtectionDomain` có thể tiếp tục tồn tại như object và giữ metadata, nhưng **permission policy kiểu cũ không dùng để giới hạn quyền đọc file/network của class**.
- Các API nền tảng trước đây chỉ ném `SecurityException` khi Security Manager chặn thao tác thường không còn thực hiện kiểm tra ấy.

Cần phân biệt hai hiện tượng trái ngược:

1. **Tài nguyên được truy cập dù collection không liệt kê quyền:** trên JDK 24+ điều này không nghịch lý vì mô hình kiểm soát quyền đã ngưng.
2. **Một lời gọi trực tiếp vào API `AccessController.checkPermission` vẫn ném:** đó là hành vi tương thích được quy định cho API lỗi thời, không có nghĩa kiểm tra quyền đang bảo vệ file/network thật.

Không dựa vào câu “`checkPermission` ném lỗi nên file vẫn an toàn”: code có thể gọi thẳng filesystem/network APIs mà không đi qua check ấy.

Tài liệu tương ứng: [Oracle — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html) và [JEP 486](https://openjdk.org/jeps/486).

## 8. Ví dụ thực hành: CodeSource + getPermissions nhưng không tạo sandbox

Bài thực hành dưới đây dùng **Java 17+**, biên dịch ứng dụng và plugin vào **hai thư mục khác nhau**, rồi nạp bytecode qua subclass của `SecureClassLoader`. Hook `getPermissions` trả collection rỗng, tức **không khai báo** `PropertyPermission("java.version","read")`; plugin vẫn gọi `System.getProperty("java.version")` thành công khi JVM không bật Security Manager.

**Quan trọng về điều kiện:** kết quả được xác minh trên **OpenJDK 21 với Security Manager không bật**. Trên JDK 24+ Security Manager luôn tắt, nên logic về không áp permission sandbox còn được xác nhận bằng đặc tả/JEP 486; không suy diễn kết quả này cho một JVM cũ đang bật Security Manager.

### Cấu trúc thư mục

```text
src/
  plugin/
    sandboxdemo/
      Worker.java
  app/
    SecureLoaderDemo.java
plugin-classes/     (javac tạo)
app-classes/        (javac tạo)
```

**File `src/plugin/sandboxdemo/Worker.java`:**

```java
package sandboxdemo;

public class Worker {
    public String message() {
        return "plugin-ok";
    }

    public boolean canReadVersion() {
        return System.getProperty("java.version") != null;
    }
}
```

**File `src/app/SecureLoaderDemo.java`:**

```java
import java.io.IOException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.PermissionCollection;
import java.security.Permissions;
import java.security.ProtectionDomain;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;
import java.util.PropertyPermission;
import java.util.concurrent.atomic.AtomicInteger;

public class SecureLoaderDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL sourceUrl;
        final AtomicInteger permissionCalls = new AtomicInteger();

        PluginLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath();
            this.sourceUrl = this.root.toUri().toURL();
        }

        @Override
        protected PermissionCollection getPermissions(CodeSource cs) {
            permissionCalls.incrementAndGet();
            return new Permissions();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path path = root.resolve(
                    binaryName.replace('.', '/') + ".class");
            try {
                byte[] data = Files.readAllBytes(path);
                CodeSource source = new CodeSource(
                        sourceUrl, (Certificate[]) null);
                return defineClass(
                        binaryName, data, 0, data.length, source);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginLoader loader = new PluginLoader(
                Path.of("plugin-classes"));
        Class<?> c = Class.forName(
                "sandboxdemo.Worker", false, loader);
        ProtectionDomain pd = c.getProtectionDomain();
        Object plugin = c.getDeclaredConstructor().newInstance();

        System.out.println("defined by plugin loader: "
                + (c.getClassLoader() == loader));
        System.out.println("source URL matches: "
                + (pd.getCodeSource().getLocation().equals(
                        Path.of("plugin-classes")
                            .toAbsolutePath().toUri().toURL())));
        System.out.println("permissions callback invoked: "
                + (loader.permissionCalls.get() == 1));
        System.out.println("explicit property permission: "
                + pd.getPermissions().implies(
                        new PropertyPermission("java.version", "read")));
        System.out.println("class code runs: "
                + c.getMethod("message").invoke(plugin));
        System.out.println("property read at runtime: "
                + c.getMethod("canReadVersion").invoke(plugin));
        System.out.println("same class on repeat: "
                + (Class.forName("sandboxdemo.Worker", false, loader) == c));
    }
}
```

### Biên dịch và chạy

Đứng từ thư mục gốc chứa `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/sandboxdemo/Worker.java
javac --release 17 -d app-classes src/app/SecureLoaderDemo.java
java -cp app-classes SecureLoaderDemo
```

Stdout **đã biên dịch, chạy và đối chiếu** trên OpenJDK 21 với Security Manager không bật:

```text
defined by plugin loader: true
source URL matches: true
permissions callback invoked: true
explicit property permission: false
class code runs: plugin-ok
property read at runtime: true
same class on repeat: true
```

### Giải thích từng kết quả

1. `plugin-classes` không nằm trong `-cp app-classes`; parent platform loader không nạp `sandboxdemo.Worker` từ thư mục ấy, nên `PluginLoader` trực tiếp định nghĩa class.
2. `CodeSource.location` được đặt từ đúng directory mà demo đọc bytecode và đi vào `ProtectionDomain` của class.
3. Hook `getPermissions(cs)` được gọi **một lần** khi domain được dựng để định nghĩa class đầu tiên từ `CodeSource` ấy. Con số là kết quả demo, không phải hợp đồng mọi loader/nhịp gọi trong mọi tình huống.
4. `getPermissions()` trả một `Permissions` collection rỗng. `PermissionCollection.implies(PropertyPermission(...))` trả `false`; tức collection ấy không liệt kê quyền.
5. **Plugin vẫn đọc được `java.version`** do JVM test không có Security Manager đang thực thi các kiểm tra kiểu cũ. Đây là minh họa mấu chốt: collection rỗng **không tự ngăn** các lời gọi `System.getProperty`.
6. Gọi `Class.forName` lần nữa với cùng name/loader trả đúng một `Class<?>`, không định nghĩa lại.
7. Reflection trong demo chỉ kích hoạt method của class được custom loader định nghĩa; nó **không** chứng minh class ấy bị cô lập hoặc được xác minh đáng tin cậy.

**Không dùng mẫu này để chạy untrusted plugin trên cùng JVM.** Trái lại, mục tiêu là minh họa rõ ràng sự khác biệt giữa metadata permissions và enforcement thực tế.

## 9. Vì sao CodeSource và permissions vẫn còn tồn tại trong API?

Có ba nhóm nhu cầu riêng:

**A. Tương thích mã cũ.** Rất nhiều loader/framework được xây khi security policy và `SecurityManager` còn là một phần của JVM. Xóa ngay các class/API sẽ phá binary compatibility. JDK có lộ trình vô hiệu hóa và sau đó mới có thể loại bỏ các phần API khác.

**B. Thông tin nguồn và kiểm tra consistency.** `CodeSource` vẫn có thể được đọc từ `ProtectionDomain` để chẩn đoán class hoặc phục vụ logic metadata; quy tắc nhất quán certificates trong một runtime package vẫn có ý nghĩa. Nhưng thông tin nguồn do loader cung cấp có thể bị đặt sai, nên phải hiểu provenance thực.

**C. Cấu trúc kế thừa.** `URLClassLoader` vốn extends `SecureClassLoader`, và một số custom loader dùng `defineClass(..., CodeSource)`. Việc tiếp tục cung cấp overload giúp các ứng dụng làm việc với class files và source metadata mà không bắt chúng tự dựng `ProtectionDomain` từ đầu.

Vì vậy không nên nói “`SecureClassLoader` vô dụng hoàn toàn”; đúng hơn là **vai trò sandbox bằng permissions lịch sử không còn hoạt động trên JDK 24+**, trong khi class-loading và source-domain metadata vẫn là những chức năng riêng.

### getPermissions không quyết định code nào được nạp

`getPermissions` được gọi trong đường dựng domain của `defineClass` nhận CodeSource; nó không tự kiểm tra tính hợp lệ của class-file bytes. Nếu muốn chặn plugin ở tầng quản lý, cần kiểm tra package allowlist, version, chữ ký được xác minh, nguồn thật, dependencies và chính sách trước khi gọi `defineClass` hoặc thực thi plugin.

Quá trình định nghĩa class vẫn chịu những quy tắc JVM riêng như `ClassFormatError`, `NoClassDefFoundError` (wrong name), `SecurityException` với namespace `java.` hoặc certificate set không nhất quán, và `LinkageError` khi định nghĩa trùng class. **Những checks còn tồn tại không đồng nghĩa với SecurityManager sandbox.**

## 10. Một số phân biệt bảo mật quan trọng

### Sandbox, class isolation và module encapsulation là ba chuyện khác nhau

| Cơ chế | Nó giải quyết điều gì? | Nó có chặn mọi quyền OS của plugin không? |
| --- | --- | --- |
| Custom `ClassLoader` | Tổ chức đường tìm class, delegation và runtime class identity. | Không. |
| `SecureClassLoader` + `CodeSource` | Gắn source/domain metadata; cơ chế permission checks từng có ý nghĩa với Security Manager. | Không trên JDK 24+. |
| JPMS (`module-info.java`, `exports`, `opens`) | Readability, strong encapsulation và reflective access trong module graph. | Không phải sandbox file/network/process. |
| JAR signing | Cung cấp khả năng kiểm tra tính toàn vẹn/xuất xứ theo chuỗi tin cậy phù hợp. | Không tự giới hạn hành vi code đã được chạy. |
| OS user permissions / container isolation | Giới hạn tài nguyên/process theo OS, với cấu hình phù hợp. | Có thể tạo ranh giới thực tế, phụ thuộc cấu hình và threat model. |
| Process/service boundary riêng | Tách plugin thành process khác, giao tiếp IPC và kiểm soát khả năng truy cập. | Có ranh giới rõ hơn nếu phối hợp OS controls. |

Một JAR **được ký hợp lệ** vẫn có thể chứa logic nguy hiểm hoặc lỗi; chữ ký không biến nó thành code có quyền hạn giới hạn. Một class được module system đóng gói kỹ vẫn chạy trong JVM process với các quyền OS của process nếu không có chính sách bên ngoài chặn.

### Có thể dùng Plugin API giới hạn không?

Có thể thiết kế `PluginContext` chỉ cung cấp method như `readPublicConfig()` hoặc `publishEvent()` và kiểm tra quyền của caller ở tầng business. Đây là biện pháp thiết kế tốt cho **extension đáng tin/được kiểm duyệt**, nhưng **không là sandbox đầy đủ** nếu code plugin tùy ý vẫn có thể gọi thẳng `Files`, `Socket`, reflection hoặc API khác trong cùng process. Muốn đối phó bytecode độc hại, cần ranh giới mạnh hơn.

## 11. Thiết kế plugin trên JVM hiện đại: nên chọn gì?

Nếu plugin đáng tin nhưng cần nạp động:

1. Tạo loader với parent phù hợp để chia sẻ API của host (ví dụ interface `Plugin` nằm ở parent).
2. Chọn `URLClassLoader` cho JAR/directory thông thường, hoặc `SecureClassLoader`/`ClassLoader` subclass khi thật sự cần nguồn bytecode tùy chỉnh hay source metadata.
3. Kiểm tra class-file bytes, binary name và dependencies; quản lý namespace, package sealing/certificates nếu framework chịu trách nhiệm.
4. Tách loader theo vòng đời plugin để có thể unload khi không còn reachable; đóng `URLClassLoader` để giải phóng tài nguyên nhưng không coi `close()` là lệnh unload ngay.
5. Ghi provenance thực khi cần chẩn đoán; đừng tự biến `CodeSource` thành phép xác minh đáng tin.

Nếu plugin **không đáng tin** hoặc bạn muốn kiểm soát filesystem/network:

1. Chạy code trong **process riêng** với user/quyền OS hạn chế; cân nhắc container, seccomp/App Sandbox, file-system mount, network policy theo môi trường.
2. Thiết kế IPC/API rõ ràng, phân quyền theo operation và validate dữ liệu từ plugin.
3. Phân biệt isolation tài nguyên với xác thực plugin. Hãy kiểm tra chữ ký/nguồn cung cấp qua cơ chế tin cậy phù hợp.
4. Chặn những khả năng không cần thiết ở cả tiến trình/hạ tầng, không chỉ đưa collection rỗng vào `ProtectionDomain`.
5. Lập threat model rõ ràng: “tránh plugin vô tình làm hỏng config” khác “chống mã độc chủ động tìm cách thoát sandbox”.

Không hứa rằng một container cấu hình mặc định tự chống mọi loại tấn công; khả năng cô lập thực tế phụ thuộc quyền OS, mount, network, syscall policy và cập nhật nền tảng.

## 12. Bẫy kỹ thuật thường gặp

| Quan niệm / lỗi | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| “Tên `SecureClassLoader` nghĩa là an toàn.” | Nó là subclass loader có hỗ trợ source/permissions, không phải security boundary hiện đại. | Xác định threat model và ranh giới process/OS. |
| “Tôi trả `new Permissions()` nên plugin không đọc được file.” | Không có Security Manager thực thi collection ấy trên JDK 24+. | Không dùng `getPermissions` làm sandbox. |
| “`CodeSource` trỏ URL hợp lệ nên bytes đã được xác minh.” | URL có thể do custom loader tự gán. | Kiểm tra nguồn đọc thực, chữ ký/hash/chain nếu cần. |
| “Security Manager còn dùng được với `-Djava.security.manager=allow`.” | JDK 24+ từ chối bật Security Manager. | Di chuyển khỏi mô hình policy cũ. |
| “`AccessController.checkPermission` ném nên file/network cũng bị chặn.” | Trong JDK 24+, method lỗi thời này luôn ném dù operations khác có thể vẫn chạy. | Đánh giá quyền qua OS/process API phù hợp. |
| “Policy cấp quyền từ `java.policy` trong JDK 24.” | Security Manager policy mechanism đã bị vô hiệu hóa. | Migrate cấu hình thành controls thật. |
| “`getProtectionDomain().getPermissions() == null` thì lỗi loader.” | Domain có thể không có static permissions theo đường định nghĩa class. | Kiểm tra `null`, không suy ra enforcement. |
| “Plugin interface cùng tên có thể cast giữa hai loaders.” | Binary name trùng chưa đủ; defining loaders khác nhau tạo hai runtime types. | Chia sẻ host API qua parent loader. |
| “Thêm `CodeSource` sau khi class đã define là thay được domain.” | Domain được gắn lúc class được định nghĩa; không phải property cập nhật tùy ý. | Quyết định metadata trước khi `defineClass`. |
| “Đóng class loader lập tức xóa mọi class.” | Class unloading phụ thuộc reachable references/GC, không phải `close()`. | Quản lý lifecycle/caches/threads. |
| “`SecureClassLoader` tự parse manifest và verify signed JAR.” | Các trách nhiệm khác nằm ở loader/JAR verification pipeline. | Dùng URLClassLoader/JarFile phù hợp, kiểm tra provenance. |
| “Module encapsulation tương đương chặn filesystem.” | JPMS quản lý visibility của Java packages, không cấp quyền OS theo domain. | Phân quyền ở API/process/OS. |

## 13. Cách đọc code cũ có getPermissions hoặc doPrivileged

Khi bảo trì ứng dụng legacy, nên tách câu hỏi:

- `getPermissions(CodeSource)` được override ở đâu? Nó trả một collection tĩnh, cấp quyền theo source, hay gọi `super.getPermissions`?
- Loader đang định nghĩa lớp nào, thuộc protection domain nào, và class nào chỉ được parent delegate?
- Ứng dụng từng bật Security Manager ở startup hay cài tại runtime?
- Có policy file/`java.security.policy` hoặc assumptions về `AllPermission`, `FilePermission` và `SocketPermission`?
- Có đoạn `AccessController.doPrivileged` để thu hẹp phạm vi đặc quyền hay để né kiểm tra trên call stack?
- Có `AccessController.checkPermission`/`Policy.setPolicy` cần được thay bằng kiểm soát thật trước khi nâng cấp JDK 24+?
- Các library có đang **bắt mọi `SecurityException` như thể chắc chắn tài nguyên bị cấm**? Một số exception đó vẫn có thể tới từ các cơ chế khác; phân loại theo API và nguyên nhân thực.
- Sự an toàn trước đây dựa vào việc applet/container chặn code độc hại, hay vào các quy tắc domain metadata không thực thi?

### Quy trình migration thực tế

1. Xác định phiên bản JDK đang chạy và có bật `SecurityManager` trên môi trường cũ hay không. Trong Java 17–23, chính sách/cảnh báo cụ thể tùy phiên bản.
2. Tìm các API `SecurityManager`, `AccessController`, `Policy`, `Permission` (đặc biệt khi dùng trực tiếp) và Java launcher options.
3. Viết test mô tả ranh giới bảo mật **thực sự cần**: không đọc thư mục nào, không gọi mạng nào, không được ghi đè config nào.
4. Chọn cơ chế thay thế có thể test được: process/OS sandbox, network namespace, container profiles, kiểm soát IPC, authz ở server.
5. Đánh giá source metadata có cần giữ để audit/debug hay không; có thể tiếp tục dùng CodeSource nhưng không coi là authorization gate.
6. Chạy test trên JDK 24+; không kỳ vọng khởi động với `-Djava.security.manager` hoặc kiểm tra `AccessController.checkPermission` theo semantics cũ.
7. Nếu thư viện third-party phụ thuộc Security Manager quá sâu, lên kế hoạch thay hoặc nâng phiên bản tương thích; không lén downgrade bảo mật bằng cách bỏ qua lỗi.

Trên môi trường Java 17–23 khi rà soát source legacy, `jdeprscan` có thể hỗ trợ tìm API deprecated của các class files, nhưng không thay phân tích cấu hình runtime/policy. Kết quả từ static scanning không tự xác nhận việc enforcement từng chạy đúng.

## 14. Tự kiểm tra kiến thức

1. **`SecureClassLoader` có khác `ClassLoader` chủ yếu ở đâu?**  
   Nó cung cấp overload `defineClass` nhận `CodeSource` và hook `getPermissions` để xây protection domain trong mô hình API của Java.
2. **Từ JDK 24, đặt `FilePermission` rỗng có tự ngăn plugin gọi `Files.readString` không?**  
   Không. Security Manager đã bị vô hiệu hóa, nên collection permission không còn là sandbox filesystem.
3. **Nếu một class có `CodeSource.location`, có chứng minh bytes đến từ URL đó không?**  
   Không; custom loader có thể đặt metadata sai. Cần xác minh nguồn thực.
4. **`ProtectionDomain.getPermissions()` có thể `null`?**  
   Có. Trạng thái này không nên được dùng để kết luận hệ thống đang thực thi hay từ chối operations.
5. **`getPermissions` trả `false` khi kiểm tra PropertyPermission, nhưng `System.getProperty` vẫn thành công trong demo. Vì sao?**  
   Demo không bật Security Manager. Metadata permission không được runtime dùng để từ chối lời gọi property.
6. **JDK 24 có thể bật Security Manager với `-Djava.security.manager=allow`?**  
   Không. JVM từ chối thao tác bật cơ chế đã bị vô hiệu hóa.
7. **`AccessController.checkPermission` trên JDK 24+ có đáng dùng để kiểm tra access thật không?**  
   Không; nó luôn ném exception theo API thay đổi.
8. **`URLClassLoader` có quan hệ gì với `SecureClassLoader`?**  
   `URLClassLoader` kế thừa từ `SecureClassLoader`, nhưng điều đó không biến URLClassLoader thành sandbox.
9. **Hai loaders cùng gắn URL source giống nhau và định nghĩa `demo.Task` có cùng runtime type không?**  
   Không; defining loader là thành phần của type identity.
10. **Muốn chạy bytecode thực sự không tin cậy nên dùng biện pháp nào?**  
    Ưu tiên process boundary và giới hạn OS/container phù hợp, IPC có kiểm soát, không chỉ dựa vào class-loader permissions.
11. **Có nên dùng `java.security.Policy` mới để quản lý quyền plugin trên Java hiện đại?**  
    Không như cách Security Manager từng dùng; policy mechanism bị vô hiệu hóa JDK 24+.
12. **SecureClassLoader vẫn có giá trị gì khi Security Manager không còn?**  
    Class loading và metadata `CodeSource`/`ProtectionDomain`, trong giới hạn API, vẫn có thể hữu ích cho tương thích và chẩn đoán.

## 15. Nguồn tham khảo chính thức

- [Java SE 25 — SecureClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): các overload `defineClass`, `getPermissions`; API Note xác nhận permissions không còn dùng kiểm soát quyền vì Security Manager không hỗ trợ.
- [Java SE 21 — SecureClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): bối cảnh phiên bản trước thay đổi JDK 24.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): source location/certificates.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): domain metadata và static/dynamic permissions.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): class loading, defining loader, protection domain, class-file name checks.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): bối cảnh Java 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): quyết định loại bỏ cơ chế kích hoạt từ JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): danh sách thay đổi `System`/`Policy`/`AccessController`/`ProtectionDomain` và hướng migration.
- [JVM Specification §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): lớp runtime được định danh bằng binary name và defining loader.
