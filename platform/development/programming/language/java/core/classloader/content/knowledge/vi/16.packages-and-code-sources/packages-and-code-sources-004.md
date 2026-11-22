# CodeSource và vị trí nguồn bytecode trong Java ClassLoader

## 1. Vấn đề: class này “đến từ JAR nào”?

Khi gặp `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, xung đột nhiều phiên bản thư viện hoặc nghi ngờ plugin bị nạp sai, một câu hỏi chẩn đoán rất hữu ích là: **JVM đã nhận định nghĩa class đang chạy từ nguồn nào?**

Một cách thường thấy:

~~~java
Class<?> type = SomeLibraryClass.class;
java.security.CodeSource source =
        type.getProtectionDomain().getCodeSource();
java.net.URL location = source == null ? null : source.getLocation();
System.out.println(location);
~~~

Nhưng phép in này cần được hiểu đúng:

- **`CodeSource` là metadata về nguồn mã gắn với `ProtectionDomain` của class**; nó không phải một API bắt buộc trả **đường dẫn file `.class` cụ thể đã được đọc**.
- **`CodeSource.getLocation()` là một `URL`**, có thể trỏ đến **JAR**, **directory**, một địa chỉ nguồn khác, hoặc **`null`**.
- **`Class.getProtectionDomain()`** là bước lấy protection domain gắn với runtime class; CodeSource có thể `null`, và nếu có CodeSource thì `location` vẫn có thể `null`.
- **Custom ClassLoader có thể chủ động gán CodeSource** khi define class; URL được khai báo không tự trở thành bằng chứng rằng bytes thực sự được lấy từ URL đó.
- **Defining loader, code source, resource URL và nguồn class file trong build** là những khái niệm khác nhau.

Bài thuộc nhóm **Package và nguồn mã**, đi sâu vào **CodeSource và vị trí nguồn bytecode**: ý nghĩa, API liên quan, các trường hợp dễ hiểu sai và cách chẩn đoán đáng tin cậy. Ví dụ Java 17+ phía dưới kiểm chứng thực tế cả trường hợp nạp từ JAR, nạp bytes tự viết và gán URL nguồn mô tả.

## 2. Các đối tượng tham gia

### 2.1. `Class<?>`: class thực sự mà chương trình đang dùng

~~~java
Class<?> type = java.util.ArrayList.class;
~~~

`type` đại diện cho **runtime class** cụ thể. Hai class có cùng binary name nhưng được định nghĩa bởi hai ClassLoader khác nhau có thể là **hai `Class<?>` objects khác nhau**.

~~~java
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

Ba biểu thức là **snippet minh họa**, đặt trong một phương thức của bạn; chúng giúp xác định **tên**, **defining loader** và **module**. Chúng không tự cho biết toàn bộ lịch sử đọc từng byte từ disk/network.

### 2.2. `ProtectionDomain`: miền bảo vệ được gắn với class

~~~java
java.security.ProtectionDomain domain = type.getProtectionDomain();
~~~

`ProtectionDomain` mô tả context bảo vệ của một class, có liên hệ lịch sử với cơ chế cấp permissions và code source của Java security architecture.

Về cấu trúc, protection domain có thể liên hệ:

- `CodeSource` — thông tin về nguồn mã.
- `ClassLoader` — loader liên quan.
- `PermissionCollection` — dữ liệu permission theo mô hình security cũ hoặc API liên quan.
- `Principal[]` trong những dạng protection domain tương ứng.

**Không dùng `ProtectionDomain` như một hệ thống sandbox hiện đại chỉ bằng cách đặt metadata.** `SecurityManager` đã lỗi thời trong Java 17 và không còn là cơ chế được khuyến nghị cho phần mềm mới; hành vi còn phụ thuộc JDK đang chạy. Giá trị `ProtectionDomain` hữu ích cho **chẩn đoán provenance**, nhưng không phải “hộ chiếu bảo mật đã xác thực đường file”.

### 2.3. `CodeSource`: codebase URL và chứng cứ ký mã khi có

~~~java
java.security.CodeSource source = domain.getCodeSource();
~~~

`java.security.CodeSource` lưu:

- **`URL location`**: codebase/origin được gán cho code.
- Thông tin về **certificates** hoặc **CodeSigners**, nếu có và phù hợp.

Hợp đồng của [CodeSource Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html) cho phép URL location `null`; certificate/signers cũng có thể không có. **Không suy rằng class luôn được ký số, hoặc location URL luôn chỉ thẳng file `.class`**.

### 2.4. `ClassLoader`: cơ chế nạp lớp, không phải chính CodeSource

~~~java
ClassLoader definingLoader = type.getClassLoader();
~~~

Defining loader ảnh hưởng danh tính runtime class. Trong khi đó `CodeSource` là thông tin đi cùng `ProtectionDomain` của class; một loader có thể định nghĩa **nhiều class từ các code sources khác nhau**.

Một `URLClassLoader` dùng JAR URLs thường biết nguồn của class nó nạp từ JAR/directory và gắn thông tin nguồn phù hợp. Một custom subclass của `ClassLoader` dùng `defineClass(String, byte[], ...)` có thể được JVM gắn default protection domain, trong đó location không xác định.

## 3. Hợp đồng của `CodeSource.getLocation()`

~~~java
URL origin = codeSource.getLocation();
~~~

Ý nghĩa trả về là **URL của codebase/source được ghi nhận trong CodeSource**. Nó không đồng nghĩa với:

1. Đường dẫn **`.class` entry** ở trong JAR.
2. Đường dẫn file **`.java` source** đã biên dịch.
3. Đường dẫn JAR **mà Maven/Gradle tải ban đầu**.
4. Mỗi URL từng được `ClassLoader` kiểm tra trước khi tìm được class.
5. Một file đang còn tồn tại tại thời điểm bạn gọi method.
6. Bản ghi checksum/chứng cứ cryptographic rằng bytes đã được đọc từ URL đó.

Các tình huống điển hình:

| Class được nạp như thế nào? | `CodeSource.getLocation()` có thể cho thấy | Diễn giải |
|---|---|---|
| Application classes từ directory `build/classes` | URL directory `file:/.../build/classes/` | **Classpath root**, không phải từng file `.class` |
| Dependency từ `helper.jar` bằng `URLClassLoader` | URL `file:/.../helper.jar` | JAR chứa class, không kèm `!/pkg/Helper.class` |
| Custom loader đọc `byte[]` rồi `defineClass` không gắn nguồn | `null` location hoặc không có CodeSource | **Thiếu thông tin nguồn** không đồng nghĩa bytes không tồn tại |
| Custom `SecureClassLoader` truyền một `CodeSource` tường minh | URL do loader khai báo | **Metadata do loader cung cấp**, phải kiểm chứng nếu cần tính xác thực |
| Lớp nền tảng JDK | Có thể không có CodeSource phù hợp để in | Không nên coi `null` là lỗi; tra runtime module nếu cần |
| Framework sử dụng nested JAR hoặc memory/generated classes | URL theo loader/framework, hoặc `null` | Có thể không trùng đường file vật lý; xem loader/launcher riêng |

Không lập một luật cứng rằng mọi URL bắt đầu bằng `file:` đều là JAR, hoặc `null` luôn mang nghĩa bootstrap. Thực tế phụ thuộc loader và cách class được định nghĩa.

## 4. Cách lấy nguồn an toàn, có xử lý null

Một helper đơn giản:

~~~java
static java.net.URL codeSourceLocation(Class<?> type) {
    java.security.ProtectionDomain domain = type.getProtectionDomain();
    if (domain == null) {
        return null;
    }
    java.security.CodeSource source = domain.getCodeSource();
    return source == null ? null : source.getLocation();
}
~~~

**Đây là method minh họa**, cần đặt vào một class. Không có thao tác chuyển URL sang `Path` một cách mù quáng.

Sử dụng:

~~~java
URL location = codeSourceLocation(SomeType.class);
System.out.println(location == null ? "(unknown)" : location);
~~~

**Chú ý**: khi dùng `getProtectionDomain()` trong môi trường SecurityManager cũ, caller có thể bị kiểm tra permission; đây không phải một API guaranteed không lỗi trong mọi môi trường JDK lịch sử.

### 4.1. Vì sao phải kiểm tra hai cấp `null`?

Không nên làm thẳng:

~~~java
String p = type.getProtectionDomain()
               .getCodeSource()
               .getLocation()
               .getPath();
~~~

Dòng trên có thể ném `NullPointerException` khi CodeSource hoặc URL location vắng mặt. Ngay cả khi non-null, `URL.getPath()` **chưa phải một filesystem path đáng tin cậy** vì percent encoding, protocol khác `file:`, dạng `jar:`, nested JAR, remote URLs hoặc encoding trên Windows.

Với URL `file:` trỏ đến filesystem path, cách chuyển đúng khi cần `Path` là:

~~~java
Path path = Path.of(location.toURI());
~~~

Đoạn này là snippet minh họa, cần `import java.nio.file.Path;` và phải xử lý `URISyntaxException`. Trước khi chuyển hãy xác định `location != null` và protocol tương thích filesystem. Không dùng `Path.of` cho URL HTTP, `jrt:`, hay các schemes do framework quy định.

### 4.2. Không được hiểu mọi `CodeSource` là URLClassLoader

Những trường hợp class được nạp từ byte arrays, JDK image, instrumentation, proxy/generated classes, network/custom protocol và framework packaging có thể có nguồn khác hoặc không có URL location hữu ích.

Muốn biết loader nào định nghĩa:

~~~java
ClassLoader loader = type.getClassLoader();
System.out.println(loader == null ? "bootstrap" : loader.getClass().getName());
~~~

Khi biết loader, có thể tiếp tục đọc configuration/URLs của loader đó nếu API cho phép. Với `URLClassLoader`, `getURLs()` trả **danh sách URL search path của loader**, nhưng **đó không phải bằng chứng URL nào đã được dùng cho riêng class đang xét**.

## 5. CodeSource khác class resource URL như thế nào?

Nhiều lập trình viên dùng:

~~~java
URL resource =
        SomeType.class.getResource("SomeType.class");
~~~

Hoặc:

~~~java
String entry = SomeType.class.getName().replace('.', '/') + ".class";
ClassLoader loader = SomeType.class.getClassLoader();
URL resource = loader == null
        ? ClassLoader.getSystemResource(entry)
        : loader.getResource(entry);
~~~

Đây là **hai cách tra resource** (snippets; yêu cầu `SomeType` hợp lệ). Chúng có thể cho URL như:

~~~text
jar:file:/libs/helper.jar!/demo/lib/Helper.class
~~~

trong khi CodeSource có thể là:

~~~text
file:/libs/helper.jar
~~~

Lý do: resource URL đi đến **entry cụ thể** được tìm, còn CodeSource URL mô tả **codebase**.

Tuy nhiên:

- Resource lookup có delegation riêng, vì thế URL tìm được **không nhất thiết là bytes đã tạo `Class<?>`**, đặc biệt khi class đã được instrument/redefine hoặc loader tùy chỉnh có mapping khác.
- Một class được define từ `byte[]` có thể **không có `.class` resource** được công bố.
- Với modules, lớp nền tảng, hidden classes, nested JAR và custom class loaders, hình dạng resource URL có thể thay đổi.
- Nên xem **`CodeSource` + `ClassLoader` + `Module` + class/resource URL** như **các manh mối bổ trợ**, không đồng nhất chúng.

### 5.1. Không nhầm `getResource` với `getProtectionDomain`

| Phép gọi | Đối tượng trả về | Nội dung |
|---|---|---|
| `type.getProtectionDomain()` | `ProtectionDomain` | Metadata domain gắn với runtime class |
| `domain.getCodeSource()` | `CodeSource` hoặc `null` | Codebase/certificates/signers khi có |
| `source.getLocation()` | `URL` hoặc `null` | URL codebase nguồn mã được ghi nhận |
| `type.getClassLoader()` | `ClassLoader` hoặc `null` | Defining loader (null thường tương ứng bootstrap) |
| `type.getModule()` | `Module` | Runtime module, tên có thể null với unnamed module |
| `type.getResource("X.class")` | `URL` hoặc `null` | Tra resource liên quan tới class theo quy tắc API |
| `urlLoader.getURLs()` | `URL[]` | Search path của loader, không phải một URL cho từng class |

## 6. Thực hành Java 17+: CodeSource có URL của JAR, URL null và nguồn tổng hợp

Ví dụ sau chỉ cần JDK 17+, không cần Maven/Gradle. Chúng ta chuẩn bị **một class library**, đọc nó bằng ba con đường khác nhau:

1. `URLClassLoader` nhận URL của `helper.jar` → `CodeSource.location` ghi nhận URL JAR.
2. Custom `ClassLoader` đọc `Helper.class` từ một directory rồi dùng `defineClass` mặc định → **location không xác định**.
3. Custom `SecureClassLoader` vẫn đọc **chính file class đó** từ directory nhưng gắn một CodeSource URL **tổng hợp** không phải vị trí đọc bytes → minh họa lý do **không thể coi source URL là chứng cứ mạnh**.

### 6.1. Cấu trúc thư mục

~~~text
demo/
├── src/
│   ├── app/
│   │   └── OriginDemo.java
│   └── lib/
│       └── demo/
│           └── lib/
│               └── Helper.java
└── build/
    ├── app/
    ├── lib/
    │   └── demo/lib/Helper.class
    └── helper.jar
~~~

**Điều kiện tái hiện:** khi chạy, `-cp` chỉ chứa `build/app`, **không chứa `build/lib` hoặc `build/helper.jar`**. Nếu đưa chúng lên application classpath, parent-first delegation có thể định nghĩa `demo.lib.Helper` trước, làm sai ý nghĩa của so sánh loaders.

### 6.2. Tệp `src/lib/demo/lib/Helper.java`

~~~java
package demo.lib;

public final class Helper {
    public static String value() {
        return "HELPER_OK";
    }
}
~~~

Class này dùng một tên nhị phân duy nhất. Chương trình sẽ tạo các **runtime class khác nhau có cùng tên** dưới các defining loaders khác nhau; đây là hành vi hợp lệ trong mô hình class loading khi không có loading constraints xung đột.

### 6.3. Tệp `src/app/OriginDemo.java`

~~~java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class OriginDemo {
    static final String NAME = "demo.lib.Helper";

    static final class PlainBytesLoader extends ClassLoader {
        private final Path root;

        PlainBytesLoader(Path root) {
            super(OriginDemo.class.getClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    static final class LabelLoader extends SecureClassLoader {
        private final Path root;
        private final URL label;

        LabelLoader(Path root, URL label) {
            super(OriginDemo.class.getClassLoader());
            this.root = root;
            this.label = label;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                CodeSource declared =
                        new CodeSource(label, (Certificate[]) null);
                return defineClass(
                        name, bytes, 0, bytes.length, declared);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/helper.jar").toAbsolutePath();
        Path root = Path.of("build/lib");

        CodeSource appSource =
                OriginDemo.class.getProtectionDomain().getCodeSource();
        System.out.println("appSourceIsDirectory="
                + Files.isDirectory(
                        Path.of(appSource.getLocation().toURI())));

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { jar.toUri().toURL() },
                OriginDemo.class.getClassLoader())) {

            Class<?> cls = loader.loadClass(NAME);
            CodeSource source = cls.getProtectionDomain().getCodeSource();
            System.out.println("jarCodeSourceMatches="
                    + jar.toRealPath().equals(
                            Path.of(source.getLocation().toURI())
                                    .toRealPath()));
            System.out.println("jarDefiningLoaderMatches="
                    + (cls.getClassLoader() == loader));
            System.out.println("classResourceAvailable="
                    + (loader.getResource(
                            "demo/lib/Helper.class") != null));
        }

        Class<?> plain = new PlainBytesLoader(root).loadClass(NAME);
        CodeSource plainSource =
                plain.getProtectionDomain().getCodeSource();
        System.out.println("plainByteLocationNull="
                + (plainSource == null
                    || plainSource.getLocation() == null));

        URL label = new URL("file:/synthetic/location.jar");
        Class<?> tagged = new LabelLoader(root, label).loadClass(NAME);
        System.out.println("labeledCodeSourceSynthetic="
                + label.equals(tagged.getProtectionDomain()
                        .getCodeSource().getLocation()));
        System.out.println("sameNameDifferentClass="
                + plain.getName().equals(tagged.getName()) + ","
                + (plain != tagged));
    }
}
~~~

#### Ý đồ từng loader

- `PlainBytesLoader` đọc bytes trực tiếp bằng `Files.readAllBytes` và sử dụng `ClassLoader.defineClass(name, bytes, ...)`. Với default protection domain của JDK trong ví dụ, **không có URL location được gán**. **Không nhất thiết `CodeSource` object phải null; chính `getLocation()` có thể null**.
- `LabelLoader` extends `SecureClassLoader`, sử dụng protected overload `defineClass(name, bytes, offset, length, CodeSource)`. Nó **chủ động khai báo** một URL `file:/synthetic/location.jar` mặc dù bytes đã được đọc từ `build/lib`. Đường `/synthetic/location.jar` **không cần tồn tại** để metadata này được đặt.
- `URLClassLoader` dùng URL trỏ đến JAR thật. Nó kế thừa `SecureClassLoader` và cung cấp `CodeSource` từ nguồn được nạp khi áp dụng theo API.
- Ba loaders dùng parent application loader, nhưng `demo.lib.Helper` **không** nằm trên app runtime classpath. Vì vậy, mỗi loader có thể định nghĩa bản `Helper` riêng.

Cố ý dùng **`NAME`** và file nguồn rõ ràng để tách **định danh class** khỏi **location metadata**.

### 6.4. Biên dịch/chạy từ thư mục `demo`

Linux/macOS:

~~~sh
mkdir -p build/app build/lib
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
javac --release 17 -d build/app src/app/OriginDemo.java
java -cp build/app OriginDemo
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/app, build/lib | Out-Null
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
javac --release 17 -d build/app src/app/OriginDemo.java
java -cp build/app OriginDemo
~~~

**Stdout chính xác**, kiểm chứng bằng JDK 21 và `javac --release 17` sau khi dựng cây `demo`:

~~~text
appSourceIsDirectory=true
jarCodeSourceMatches=true
jarDefiningLoaderMatches=true
classResourceAvailable=true
plainByteLocationNull=true
labeledCodeSourceSynthetic=true
sameNameDifferentClass=true,true
~~~

Tất cả phép kiểm tra đều cố ý in **boolean** thay vì đường tuyệt đối phụ thuộc máy. Hai giá trị trên dòng cuối là:
1. `plain.getName().equals(tagged.getName()) == true`;
2. `plain != tagged == true`.

### 6.5. Đọc kết quả đúng

| Output | Điều chứng minh |
|---|---|
| `appSourceIsDirectory=true` | `OriginDemo` chạy từ directory `build/app` có CodeSource URL trỏ tới classpath root dạng directory |
| `jarCodeSourceMatches=true` | CodeSource location của `Helper` do `URLClassLoader` định nghĩa trùng JAR URL thực tế của demo |
| `jarDefiningLoaderMatches=true` | `Helper` trong nhánh đầu thực sự do loader được chỉ định định nghĩa |
| `classResourceAvailable=true` | Resource `demo/lib/Helper.class` tồn tại trong JAR theo đường tra của loader |
| `plainByteLocationNull=true` | Custom `defineClass` không buộc có location URL; **không đồng nghĩa bytecode chưa được đọc** |
| `labeledCodeSourceSynthetic=true` | Custom `SecureClassLoader` có thể gắn URL CodeSource do chính nó chọn |
| `sameNameDifferentClass=true,true` | Hai class cùng binary name nhưng khác defining loaders có thể là hai runtime types khác nhau |

**Giới hạn ngữ nghĩa:** ví dụ chứng minh `CodeSource` là dữ liệu được gắn khi define class, không phải phép xác minh supply chain. Nếu cần biết bytes đã được tải từ đâu thực sự, phải đối chiếu triển khai loader, artifact, cryptographic hashes và quá trình deploy.

### 6.6. Các biến thể tự thực hành

**Biến thể A — In URL thực tế:** thay các dòng boolean bằng `System.out.println(source.getLocation())`. Kết quả sẽ chứa đường dẫn theo máy hiện tại; vì vậy không đưa nó làm stdout cố định.

**Biến thể B — Thay file nguồn:** cho `PlainBytesLoader` đọc `build/lib` như cũ nhưng đổi URL `label`. Kết quả `labeledCodeSourceSynthetic` vẫn true nếu so với URL vừa gán, dù không có thay đổi về bytes. Điều đó chứng minh vai trò metadata.

**Biến thể C — Chạy với sai classpath:** thêm `build/helper.jar` vào `-cp` khi chạy. Application loader có thể định nghĩa `Helper` trước child loaders, khiến `jarDefiningLoaderMatches` không còn true. Đây là tác động của **parent-first delegation**, không phải `CodeSource` bị lỗi.

**Biến thể D — Resource lookup:** gọi `loader.getResource("demo/lib/Helper.class")` rồi in URL. Nó có thể có dạng `jar:file:...!/demo/lib/Helper.class`, khác URL CodeSource `file:.../helper.jar`.

## 7. Vì sao CodeSource không phải phép kiểm tra an toàn của artifact?

### 7.1. URL location không xác thực bytes

Hợp đồng `CodeSource(URL, certificates)` cho phép ứng dụng/loader đặt **CodeSource location** từ dữ liệu nó lựa chọn. Nhánh `LabelLoader` trong demo dùng URL không phải nơi đã đọc bytes. Bởi vậy:

~~~text
CodeSource.getLocation() != chứng cứ cryptographic về source bytes
~~~

Nếu bạn kiểm tra “plugin này có phải chính JAR đã được ký và phê duyệt không?”, **chỉ so sánh URL string là không đủ**. Hãy dùng quy trình xác minh integrity/signature hoặc hashes của artifact theo kênh tin cậy, cùng chính sách loader được kiểm soát.

### 7.2. Certificates và CodeSigners không đồng nghĩa class chắc chắn đáng tin

`CodeSource.getCertificates()` hoặc `getCodeSigners()` có thể trả null/không có dữ liệu nếu unsigned hoặc loader không cung cấp thông tin ký mã. Nếu có dữ liệu, cách tạo và xác thực dữ liệu còn phụ thuộc cơ chế xác minh JAR, trust stores, trust policy và loader đang dùng.

Việc **gắn** một `CodeSource` không tự làm ứng dụng trở thành một hệ thống xác thực chữ ký chuẩn. Với `URLClassLoader` đọc signed JARs, có cơ chế kiểm tra liên quan đến JAR verification và signer consistency; muốn xây chính sách tin cậy vẫn cần xác định đầu vào được xác minh bằng cách nào.

### 7.3. Một ProtectionDomain có thể được tái sử dụng

Khi dùng `ClassLoader.defineClass` với overload không cung cấp protection domain, JDK gắn **default protection domain** theo hợp đồng. Không nên mặc định mỗi `Class<?>` có một CodeSource URL riêng biệt hoặc một ProtectionDomain object riêng.

Mặt khác `SecureClassLoader` có thể tạo/cache protection domain dựa trên CodeSource; hai lớp từ một JAR có thể chia sẻ cùng codebase. CodeSource không phải bản ghi “file read event” cho từng class.

### 7.4. Runtime module và source location không tương đương

Với JPMS:

~~~java
Module module = SomeType.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

Đây là snippet minh họa. `module.getName()` cho biết module name (có thể null với unnamed module), không phải URL của JAR. Trong module layers tùy chỉnh, module có thể đến từ runtime image, directory hoặc modular JAR; `Module` và `CodeSource` trả lời những câu hỏi khác nhau.

## 8. Chẩn đoán vị trí class trong ứng dụng thực tế

Một quy trình đáng tin cậy khi nghi ngờ sai phiên bản JAR:

1. **Xác định đúng runtime `Class<?>`:** thông qua object/stack trace hoặc class cần kiểm tra.
2. **In binary name, defining ClassLoader và module:** phân biệt hai class cùng tên do hai loaders định nghĩa.
3. **Đọc `ProtectionDomain`/`CodeSource` có null guards:** lấy location URL nếu có; nếu null, báo “không có location”, không bịa origin.
4. **Kiểm tra resource URL và class loading log:** `SomeType.class.getResource("SomeType.class")`, cùng các phương tiện riêng của loader/framework nếu cần.
5. **So runtime JAR với build dependency graph:** trong Maven/Gradle, version resolve là một chuyện; file được copy vào container, JAR xuất hiện trên launcher classpath và loader thực tế là chuyện khác.
6. **Xem actual launcher:** `java -cp`, `java -jar`, module path, IDE, Spring Boot launcher, application server hoặc plugin container có thể dựng classpath khác nhau.
7. **Nếu URL trỏ tới JAR:** dùng `jar --list --file path/to/foo.jar` và công cụ checksum để đối chiếu artifact, không chỉ tin URL.
8. **Nếu URL null hoặc tổng hợp:** đọc implementation custom loader, nguồn bytes/caches, resource mapping, protection domain được gán ở đâu.
9. **Nếu class tồn tại nhưng vẫn lỗi:** xem lỗi linkage cụ thể, `NoSuchMethodError`, `IllegalAccessError`, `ClassCastException`, version và module access.
10. **Nếu cần bằng chứng bảo mật:** xác minh cryptographic hashes hoặc JAR signatures theo chính sách tin cậy riêng; CodeSource metadata chỉ là manh mối.

### 8.1. Log class loading ở HotSpot

Có thể chạy chương trình với:

~~~sh
java -Xlog:class+load=info -cp build/app OriginDemo
~~~

Log thường bao gồm thông tin tên class và nguồn mà VM/loader báo cáo, nhưng định dạng và độ đầy đủ phụ thuộc runtime/JDK. Không coi `-Xlog` là API thay thế một phép xác minh bytecode độc lập.

### 8.2. So source location với bytes thật

Nếu cần kết luận “class được định nghĩa bằng những byte nào”, thông tin CodeSource **chưa đủ**. Cần:

- Thu đúng artifact JAR/version trong môi trường runtime và hash nó.
- Hoặc với custom loader, instrument/log tại vị trí `readAllBytes`/`defineClass` và hash đúng mảng bytes trước khi define.
- Với agent redefinition/instrumentation, chú ý class bytes đã chạy có thể được biến đổi so với bytes trong file ban đầu.
- Giữ log có timestamp/version/loader identity và tránh ghi đường dẫn/bí mật nhạy cảm trong production logs.

**Giới hạn của tài liệu:** Java core không cung cấp một API phổ dụng `Class.getOriginalBytecodePath()` trả chính xác nguồn gốc của mọi class trong mọi ClassLoader. `CodeSource` là một mảnh thông tin, không phải lời giải xác thực toàn bộ.

## 9. Những nhầm lẫn cần tránh

1. **“`getCodeSource().getLocation()` luôn là file JAR.”** Sai: có thể là directory, URL khác hoặc null.
2. **“Nếu CodeSource null thì JVM không load được class.”** Sai: class đã tồn tại; chỉ thiếu metadata nguồn.
3. **“CodeSource object luôn null khi custom loader dùng `defineClass(byte[])`.”** Sai: nó có thể tồn tại nhưng location null như trường hợp đã kiểm chứng.
4. **“`getLocation()` trả đường dẫn file `.class`.”** Sai với JAR source: thường là URL của **archive/codebase**, không phải entry riêng.
5. **“Có class resource URL thì bytes đang chạy chắc chắn khớp resource hiện tại.”** Sai với custom loaders, instrumentation, modified archives và các cơ chế caching khác.
6. **“Tìm thấy một `.class` resource chứng minh loader đó đã định nghĩa runtime class.”** Sai: resource lookup và defining loader/class identity là các bước riêng.
7. **“CodeSource URL là bằng chứng chữ ký số đã được kiểm chứng.”** Sai: URL không xác minh cryptographic provenance.
8. **“Hai class cùng tên cùng CodeSource URL thì luôn cùng runtime type.”** Sai nếu defining loaders khác nhau.
9. **“Maven/Gradle cache path luôn chính là CodeSource location trong runtime.”** Sai với shaded JAR, repackaging, container và custom loader.
10. **“`URL.getPath()` là filesystem Path có thể dùng trực tiếp.”** Sai nếu URL encoded/protocol khác file hoặc đường platform-specific.
11. **“Module name cho biết JAR URL.”** Sai: module identity và code source origin khác nhau.
12. **“Classpath system liệt kê đủ mọi nguồn class.”** Sai với bootstrap/platform modules và plugin/framework loaders.
13. **“Nếu location trỏ đến file không tồn tại thì class chưa từng được load.”** Sai: URL có thể là metadata tổng hợp, file đã bị di chuyển hoặc loader đã đọc bytes vào memory.
14. **“Có thể đổi CodeSource để an toàn hoá plugin mà không cần thêm gì.”** Sai: an toàn cần trust policy và cơ chế xác minh riêng.

## 10. Câu hỏi tự kiểm tra

1. `CodeSource` lưu những loại thông tin nào ngoài URL?
2. `Class.getProtectionDomain()` giúp truy cập metadata nào?
3. Vì sao nên có null guards cho cả `CodeSource` lẫn `getLocation()`?
4. Class nạp từ directory và class nạp từ JAR thường khác hình dạng location URL thế nào?
5. Với `jar:file:/libs/x.jar!/p/X.class`, CodeSource location thường trỏ tới URL nào?
6. Vì sao `CodeSource.getLocation()` không chứng minh bytes thực sự được đọc từ URL đó?
7. Custom `ClassLoader.defineClass(name, bytes, ...)` có buộc location URL không null không?
8. `SecureClassLoader.defineClass(name, bytes, ..., CodeSource)` cho phép loader kiểm soát metadata nào?
9. Hai classes cùng binary name cùng source URL nhưng loader khác nhau có buộc cùng runtime identity không?
10. Đọc `SomeType.class.getResource("SomeType.class")` có luôn cung cấp exact loaded bytes không? Vì sao?
11. Tại sao dùng `Path.of(location.toURI())` chỉ phù hợp khi URL thể hiện filesystem resource?
12. Khi gặp `NoSuchMethodError`, bạn nên xác minh artifact/version nào đang chạy bằng cách nào?
13. `Module.getName()` và `CodeSource.getLocation()` trả lời những câu hỏi khác nhau ra sao?
14. Khi custom loader dùng bytes từ memory/network, CodeSource có thể có trạng thái nào?
15. Trong ví dụ, vì sao `labeledCodeSourceSynthetic=true` mà bytes vẫn được đọc từ `build/lib`?
16. Nếu một class bị agent instrument sau khi đã nạp, CodeSource có chứng minh bytes đang chạy không bị biến đổi không?
17. Khi CodeSource location có giá trị `null`, những nguồn chẩn đoán bổ sung nào có ích?
18. Vì sao nên dùng checksums/signature verification thay vì chỉ so URL nếu yêu cầu xác thực nguồn của plugin?

**Tiêu chí hoàn thành:** chạy được ví dụ Java 17+ và giải thích đủ bảy dòng stdout; phân biệt **CodeSource URL**, **class resource**, **defining loader**, **Module** và **bytes đã định nghĩa class**; biết xử lý null và lập một quy trình chẩn đoán không kết luận vượt quá những gì API cung cấp.

## 11. Tài liệu chính thức

- [Java SE 21 — `CodeSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): URL location, certificates, code signers, `getLocation()`.
- [Java SE 21 — `ProtectionDomain`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): miền bảo vệ của class và metadata CodeSource.
- [Java SE 21 — `Class.getProtectionDomain()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getProtectionDomain()): lấy protection domain gắn với runtime class.
- [Java SE 21 — `SecureClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass` overload có `CodeSource`.
- [Java SE 21 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): tìm class từ URL JAR/directory và thông tin source liên quan.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, default protection domain, delegation và defining loader.

Trong ví dụ, **CodeSource metadata được tạo bởi loader**, nên bài không đưa ra lời hứa rằng URL tự xác thực một artifact. Java 17+ đủ để biên dịch và chạy; stdout được kiểm chứng với JDK 21 và `javac --release 17`.