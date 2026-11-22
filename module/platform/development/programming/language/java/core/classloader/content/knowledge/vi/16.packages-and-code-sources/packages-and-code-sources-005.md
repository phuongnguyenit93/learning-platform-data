# ProtectionDomain trong các biến thể `defineClass`

> **Java Core → ClassLoader → Package và nguồn mã.** `ProtectionDomain` là metadata gắn với runtime class khi classloader định nghĩa class từ bytecode. Nó kết nối **`CodeSource` (nguồn mã/chứng chỉ)**, một **`ClassLoader`**, **`Principal`** và thông tin `PermissionCollection` của kiến trúc bảo mật Java. Bài này so sánh đúng các overload `defineClass`, chỉ ra cách truyền domain tường minh hoặc nhận domain mặc định, quy tắc certificate consistency trong cùng package, cách dùng `SecureClassLoader`, và đặc biệt phân biệt **metadata nguồn mã** với **sandbox thực sự** trên các phiên bản JDK hiện đại.

## 1. Câu trả lời ngắn: `ProtectionDomain` liên quan gì đến `defineClass`?

Một custom loader thường gọi `defineClass` từ `findClass` sau khi lấy bytes:

~~~java
Class<?> type = defineClass(name, classBytes, 0, classBytes.length);
~~~

Lời gọi này định nghĩa class với một **ProtectionDomain mặc định**. Nếu muốn gắn domain do chương trình cung cấp, sử dụng overload:

~~~java
Class<?> type = defineClass(
        name, classBytes, 0, classBytes.length, explicitDomain);
~~~

Đây đều là **snippet trong subclass của `ClassLoader`**, không phải code hợp lệ để gọi từ một class ứng dụng bất kỳ: `defineClass` là `protected final`. Một cách khác là dùng overload `ByteBuffer` hoặc lớp con `SecureClassLoader` nhận `CodeSource`.

**Điều quan trọng nhất:**

- `defineClass` tạo **runtime `Class<?>`** từ bytecode; `ProtectionDomain` là domain **được gắn với class được định nghĩa**.
- `CodeSource` trong domain giúp mô tả **vị trí và thông tin signer/certificate** được cung cấp qua quá trình nạp đã xác thực; nó **không bảo đảm** tự đi đọc class file từ URL ấy.
- Nếu truyền `null` cho `ProtectionDomain`, VM/JDK dùng **domain mặc định** theo hợp đồng `ClassLoader`.
- Với JDK 24 trở lên, **Security Manager đã bị vô hiệu hóa vĩnh viễn**. Gắn `ProtectionDomain` hay cấp `Permission` không biến plugin thành một sandbox có thể giới hạn truy cập tài nguyên. Tuy nhiên metadata CodeSource, một số kiểm tra về tên package/chứng chỉ và quy tắc định nghĩa class vẫn liên quan.

### Bảng overload cần nhớ

| API trong subclass | Domain được gắn | Ghi chú |
| --- | --- | --- |
| `defineClass(byte[] b, int off, int len)` | Không có đối số domain; cơ chế mặc định | **Deprecated** từ Java 1.1; không truyền binary name, không nên dùng |
| `defineClass(String name, byte[] b, int off, int len)` | **Domain mặc định** | Đề xuất cơ bản khi không có metadata nguồn riêng |
| `defineClass(String name, byte[] b, int off, int len, ProtectionDomain pd)` | `pd` nếu không-null; nếu null thì default | Kiểm tra package certificates, tên và class-file bytes |
| `defineClass(String name, ByteBuffer b, ProtectionDomain pd)` | `pd` hoặc default | Tương đương về ý nghĩa định nghĩa class từ bytes còn lại của buffer |
| `SecureClassLoader.defineClass(String name, byte[] b, int off, int len, CodeSource cs)` | Tạo `ProtectionDomain` từ `cs` khi `cs != null` | Convenience API của `SecureClassLoader` |
| `SecureClassLoader.defineClass(String name, ByteBuffer b, CodeSource cs)` | Tương tự overload bytes | Dùng `CodeSource` trực tiếp, không truyền một `ProtectionDomain` |

**Cẩn thận:** Java cũng có các API đặc biệt như `MethodHandles.Lookup.defineClass` và `Lookup.defineHiddenClass`. Chúng có semantics lookup/loader/package/hidden class riêng, **không phải các overload của `ClassLoader.defineClass`** được giải thích ở đây.

## 2. Cấu trúc dữ liệu: `ProtectionDomain` chứa những gì?

Các thành phần chính:

~~~text
Class<?> runtimeType
       |
       v
ProtectionDomain
       +-- CodeSource
       |      +-- URL/location (có thể null)
       |      +-- Certificates / CodeSigners (có thể null)
       +-- PermissionCollection (metadata/legacy policy)
       +-- ClassLoader (có thể null)
       +-- Principal[] (thường có thể rỗng)
~~~

Các API thường dùng:

~~~java
ProtectionDomain domain = SomeClass.class.getProtectionDomain();
CodeSource source = domain.getCodeSource();
ClassLoader defining = SomeClass.class.getClassLoader();

if (source != null && source.getLocation() != null) {
    System.out.println(source.getLocation());
}
~~~

Đây là **snippet**, cần import `java.security.ProtectionDomain` và `java.security.CodeSource`. `getProtectionDomain()` trả domain liên kết với runtime class, nhưng mã chẩn đoán không nên mặc định mọi `Class` hay mọi runtime image đều có `CodeSource` khác null.

### 2.1. `CodeSource` không phải “nguồn bytes” do VM tự kiểm chứng

`new CodeSource(URL, Certificate[])` mô tả URL và certificates được truyền vào. Nếu bạn ghi `file:/example/plugins/a.jar` vào `CodeSource` nhưng lại định nghĩa bytes đọc từ nơi khác, chỉ riêng `defineClass` **không tự so khớp URL với nguồn thực tế** và không xác thực archive dựa trên tên URL.

Vì vậy:

- URL có thể chỉ là **metadata** do custom loader quyết định.
- Không dùng một `CodeSource` tự chế làm bằng chứng chữ ký số hợp lệ.
- Khi dùng JAR signed, code nạp phải thực sự **verify JAR/signature** bằng đường đọc/JAR verification thích hợp rồi mới tin certificates được trả.
- `CodeSource.getCertificates()` và `CodeSource.getCodeSigners()` phản ánh thông tin đã được cung cấp/được chuyển đổi theo API; `null`/rỗng không tự suy ra code được chứng thực.

**Khác biệt quan trọng:** `ProtectionDomain` là thuộc tính của một **runtime class**; `CodeSource` chỉ là một phần metadata của domain. Cùng một physical JAR có thể được định nghĩa bởi nhiều loader thành các runtime types khác nhau.

### 2.2. Hai kiểu constructor chính của `ProtectionDomain`

~~~java
ProtectionDomain staticDomain =
        new ProtectionDomain(codeSource, permissions);

ProtectionDomain domainWithContext =
        new ProtectionDomain(
                codeSource, permissions, definingLoader, principals);
~~~

Đây là **snippet cần biến phù hợp**. Bản hai tham số biểu diễn một domain với permissions được truyền; bản bốn tham số còn lưu loader và principals, phục vụ mô hình policy có ngữ cảnh của Security Manager trước đây. Trên JDK 24+ **không thể biến những permissions này thành ranh giới chặn file/network** chỉ bằng cách truyền domain cho `defineClass`.

Đừng suy diễn `domain.getPermissions() == null` là bằng chứng class “được phép tất cả”, cũng không suy diễn `getPermissions()` có một `FilePermission` là tiến trình sẽ bị chính sách Java mới chặn thao tác khác. Cần xét phiên bản JDK và hệ enforcement thực sự.

## 3. Domain mặc định: không truyền gì hoặc truyền `null`

Javadoc của `ClassLoader.defineClass(String, byte[], int, int)` xác nhận: khi không nêu domain, class nhận **ProtectionDomain mặc định**. JDK tạo default domain khi lần đầu cần và **tái sử dụng** cho những lần gọi tiếp theo của cơ chế mặc định.

Với overload năm tham số:

~~~java
defineClass(name, bytes, 0, bytes.length, null);
~~~

`null` ở vị trí `protectionDomain` có nghĩa dùng đúng **default domain**, không có nghĩa class không có domain.

**Đừng đoán cấu trúc bên trong default domain từ một JDK cụ thể.** Trên một số bản runtime, `getCodeSource()` có thể là đối tượng khác null nhưng URL của nó null; trên JDK 24+, `getPermissions()` của default domain theo tài liệu JDK là `null`. Do đó code chẩn đoán nên kiểm tra riêng:

~~~java
CodeSource cs = clazz.getProtectionDomain().getCodeSource();
boolean hasSourceLocation =
        cs != null && cs.getLocation() != null;
~~~

Snippet này cần biến `clazz` hợp lệ. `hasSourceLocation == false` không có nghĩa Java class file chưa từng được đọc; chỉ là domain không mang URL nguồn mã ở trường đang kiểm tra.

### 3.1. Tại sao không nên lạm dụng default domain?

Khi load một lượng lớn plugins/dependencies từ nhiều nơi, để tất cả nhận default domain khiến metadata không cho biết chúng đến từ artifact nào. Nếu bạn cần audit/provenance thực tế, có thể gắn một `CodeSource` được xác nhận, nhưng điều này phải đi kèm **xác thực nguồn bytes**, versioning, logging và quản lý loader.

Domain mặc định đủ cho nhiều loader nội bộ không dùng legacy permissions, miễn là bạn không dựa vào nó để thay cơ chế kiểm tra danh tính, đường dẫn hoặc nguồn tin cậy.

## 4. Overload nhận `ProtectionDomain` tường minh

Chữ ký chuẩn:

~~~java
protected final Class<?> defineClass(
    String name, byte[] b, int off, int len,
    ProtectionDomain protectionDomain);
~~~

Đặc điểm:

1. **`name`** là binary name, ví dụ `org.example.Plugin` — không phải path `org/example/Plugin.class`. Có thể truyền null theo API nhưng **nên truyền tên cụ thể**.
2. **`b, off, len`** giới hạn vùng byte chứa một class file hợp lệ. Offset/length sai có thể dẫn tới `IndexOutOfBoundsException`.
3. **`protectionDomain`** nếu khác null sẽ được gắn với class; nếu null dùng domain mặc định.
4. Khi bytes không phải class file hợp lệ, `ClassFormatError` (hoặc lỗi subtype/liên quan) có thể xảy ra.
5. Nếu `name` khác binary name khai báo trong bytes, JVM có thể ném **`NoClassDefFoundError`**.
6. Nếu tên bắt đầu `java.` và defining loader không thuộc loại được phép theo API, có **`SecurityException`**.
7. Trong cùng package của một loader, những classes được định nghĩa phải có **cùng bộ signing certificates**, nếu không sẽ gặp **`SecurityException`**.
8. Định nghĩa trùng binary name trong **cùng loader** là một vấn đề khác, có thể ném **`LinkageError`**; thêm domain khác không làm nó hợp lệ.

**Bảo mật thực sự không tự xuất hiện:** overload này gắn metadata domain; nó không tự cách ly code plugin khỏi Java API hay quyền truy cập của process.

### 4.1. `name == null` làm suy yếu kiểm tra nào?

Javadoc nêu rằng bước đối chiếu certificate set của package **không được thực hiện theo cùng cách khi `name` null**. Vì vậy overload cũ `defineClass(byte[],off,len)`, vốn không nhận tên, bị deprecated và không được khuyến khích dùng. Hãy cung cấp **binary name đáng tin** và xác nhận bytecode đúng tên ấy.

Không dùng `name=null` để “vượt lỗi ký JAR”: điều đó làm yếu kiểm tra consistency và tạo rủi ro thiết kế. Nếu package signer mismatch xảy ra, giải quyết bằng artifact/certificate đúng, tránh trộn signed và unsigned classes trong cùng package của loader.

## 5. Ví dụ Java 17+: gắn `ProtectionDomain`, đọc metadata, thử default và `ByteBuffer`

Thí nghiệm có **hai file Java**: một class plugin và host loader. Để không bị parent loader nạp class plugin trước, hãy **biên dịch plugin ra thư mục tách riêng**, còn khi chạy chỉ đặt host classes trên application classpath.

Cấu trúc:

~~~text
pd-lab/
├── plugin-src/
│   └── demo/plugin/Greeter.java
├── host-src/
│   └── ProtectionDomainDemo.java
└── build/
    ├── plugin/   (sinh ra)
    └── host/     (sinh ra)
~~~

Tệp **`plugin-src/demo/plugin/Greeter.java`**:

~~~java
package demo.plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public Greeter() { }
}
~~~

Tệp **`host-src/ProtectionDomainDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.Permissions;
import java.security.Principal;
import java.security.ProtectionDomain;
import java.security.cert.Certificate;

public class ProtectionDomainDemo {
    static final class ByteLoader extends ClassLoader {
        ByteLoader() {
            super(ProtectionDomainDemo.class.getClassLoader());
        }

        Class<?> withDomain(
                String name, byte[] bytes, ProtectionDomain pd) {
            return defineClass(name, bytes, 0, bytes.length, pd);
        }

        Class<?> withDefault(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }

        Class<?> withBuffer(
                String name, ByteBuffer bytes, ProtectionDomain pd) {
            return defineClass(name, bytes, pd);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/plugin/demo/plugin/Greeter.class"));
        String name = "demo.plugin.Greeter";

        ByteLoader specific = new ByteLoader();

        // URL dưới đây là metadata, KHÔNG cần file JAR tồn tại.
        CodeSource source = new CodeSource(
                Path.of("provenance/plugin-origin.jar").toUri().toURL(),
                (Certificate[]) null);

        Permissions permissions = new Permissions();
        permissions.add(new RuntimePermission("lesson.marker"));
        permissions.setReadOnly();

        ProtectionDomain domain = new ProtectionDomain(
                source, permissions, specific, new Principal[0]);

        Class<?> type = specific.withDomain(name, bytes, domain);
        ProtectionDomain actual = type.getProtectionDomain();

        System.out.println("custom loader="
                + (type.getClassLoader() == specific));
        System.out.println("source marker="
                + actual.getCodeSource().getLocation().getPath()
                    .endsWith("plugin-origin.jar"));
        System.out.println("domain loader="
                + (actual.getClassLoader() == specific));
        System.out.println("permission metadata="
                + actual.getPermissions().implies(
                    new RuntimePermission("lesson.marker")));

        System.out.println("defined, not initialized");
        type.getDeclaredConstructor().newInstance();
        System.out.println("instance created");

        ByteLoader defaultLoader = new ByteLoader();
        Class<?> defaultClass =
                defaultLoader.withDefault(name, bytes);
        CodeSource defaultSource =
                defaultClass.getProtectionDomain().getCodeSource();
        System.out.println("default source has location="
                + (defaultSource != null
                    && defaultSource.getLocation() != null));

        ByteLoader bufferLoader = new ByteLoader();
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        Class<?> fromBuffer =
                bufferLoader.withBuffer(name, buffer, null);
        System.out.println("buffer class=" + fromBuffer.getName());

        try {
            new ByteLoader().withDomain(
                    "demo.plugin.Other", bytes, domain);
            System.out.println("wrong name rejected=false");
        } catch (NoClassDefFoundError expected) {
            System.out.println("wrong name rejected=true");
        }
    }
}
~~~

Từ thư mục `pd-lab`, với JDK 17+ (POSIX shell):

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Greeter.java
javac --release 17 -d build/host \
    host-src/ProtectionDomainDemo.java
java -cp build/host ProtectionDomainDemo
~~~

**Stdout kỳ vọng trên OpenJDK 21 thông thường:**

~~~text
custom loader=true
source marker=true
domain loader=true
permission metadata=true
defined, not initialized
Greeter initialized
instance created
default source has location=false
buffer class=demo.plugin.Greeter
wrong name rejected=true
~~~

Giải thích:

1. `withDomain` gắn một domain được tạo tường minh vào class của loader `specific`. `getClassLoader()` của class là loader ấy.
2. `CodeSource` có URL được chương trình truyền vào; dòng “source marker” **chỉ kiểm tra metadata**, không chứng minh file `plugin-origin.jar` tồn tại hay đã được verify.
3. `permission metadata=true` phản ánh `PermissionCollection` có một marker do chúng ta **tự đặt**, không phải quyền truy cập mà hệ điều hành/JDK24+ đang cưỡng chế.
4. `defineClass` chưa kích hoạt initializer, nên `Greeter initialized` xuất hiện khi gọi constructor bằng reflection, **sau** dòng `defined, not initialized`.
5. Loader `defaultLoader` dùng overload không có domain nên không có URL source được khai báo tường minh; ví dụ kiểm tra **location** thay vì giả định cả đối tượng `CodeSource` bằng `null`.
6. `ByteBuffer` định nghĩa một bản class khác dưới **loader mới** với domain mặc định. Không dựa vào việc original buffer sẽ thay đổi `position()`/`limit()` sau lời gọi; nếu cần tái sử dụng, dùng `duplicate()`/`slice()` và quản lý state tường minh.
7. Tên `demo.plugin.Other` không khớp tên trong class bytes `demo.plugin.Greeter`, nên JVM từ chối bằng `NoClassDefFoundError`.

**Giới hạn ví dụ:** Mỗi lần định nghĩa cùng binary name sử dụng **ByteLoader instance mới**. Nếu cố định nghĩa lại `demo.plugin.Greeter` trong chính `specific`, bạn sẽ gặp duplicate-definition error. Không thêm thư mục `build/plugin` vào `java -cp` của host khi muốn giữ thí nghiệm tách loader.

## 6. `ByteBuffer` overload: cùng quy tắc domain, khác hình thức bytes

Overload:

~~~java
protected final Class<?> defineClass(
    String name, ByteBuffer data, ProtectionDomain pd);
~~~

Nó sử dụng class bytes từ buffer theo bounds/remaining đã cấu hình, áp dụng **cùng quy tắc binary name, package signer, `java.*` và domain** như overload mảng byte. Có thể dùng `ByteBuffer.wrap(bytes)` hoặc buffer lấy từ I/O/memory-mapped file theo nhu cầu.

Điều không đổi:

- `pd == null` vẫn chọn default ProtectionDomain.
- Buffer chứa class data sai có thể ném `ClassFormatError`.
- Tên không khớp class file bị từ chối.
- Cùng một loader không thể định nghĩa trùng runtime binary name bằng cách “đổi overload” từ byte array sang ByteBuffer.

**Lời khuyên thực hành:** Đừng phụ thuộc side effect vào vị trí/limit của chính buffer object sau `defineClass` trên mọi implementation. Nếu code cần đọc lại bytes, chuẩn bị `duplicate()`/`asReadOnlyBuffer()` hoặc giữ nguồn bytes riêng. Đánh giá cả lifetime và ownership khi buffer liên quan memory-mapped file/resource.

## 7. `SecureClassLoader`: nhận `CodeSource` thay vì tự tạo domain

`SecureClassLoader` là subclass của `ClassLoader` có các overload sau:

~~~java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len,
        CodeSource cs);

protected final Class<?> defineClass(
        String name, ByteBuffer b, CodeSource cs);
~~~

Khi cung cấp `cs != null`, `SecureClassLoader` tạo/tra `ProtectionDomain` phù hợp và liên kết domain này với class. Có một protected hook:

~~~java
protected PermissionCollection getPermissions(CodeSource cs);
~~~

Trước đây, subclass có thể override hook để gắn permission metadata theo CodeSource, phục vụ Java Security Manager. **JDK 25 Javadoc nói rõ:** permissions không thể dùng để kiểm soát truy cập tài nguyên nữa do Security Manager không còn được hỗ trợ.

### 7.1. So sánh hai phong cách

| Điều bạn có | Lựa chọn |
| --- | --- |
| Đã có `ProtectionDomain` cụ thể, cần truyền nguyên domain | `ClassLoader.defineClass(..., pd)` |
| Có CodeSource và muốn `SecureClassLoader` xây domain | `SecureClassLoader.defineClass(..., cs)` |
| Không có metadata nguồn mã riêng | `ClassLoader.defineClass(... )` không có pd, hoặc pd=null |
| Muốn plugin không đọc file/network trên JDK 24+ | **Không dùng** ProtectionDomain/Permission như sandbox; cần isolation ở process/OS/container |
| Muốn audit artifact và signer provenance | Xác minh nguồn bytes/chữ ký thực, rồi gắn CodeSource phù hợp để giữ metadata |

### 7.2. Ví dụ `SecureClassLoader` dùng CodeSource

Tệp **`SecureSourceDemo.java`**, sử dụng bytes của `Greeter.class` đã biên dịch ở mục 5:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class SecureSourceDemo {
    static final class OriginLoader extends SecureClassLoader {
        OriginLoader() {
            super(SecureSourceDemo.class.getClassLoader());
        }

        Class<?> fromSource(String name, byte[] bytes, CodeSource cs) {
            return defineClass(name, bytes, 0, bytes.length, cs);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/plugin/demo/plugin/Greeter.class"));

        CodeSource source = new CodeSource(
                Path.of("metadata/source.jar").toUri().toURL(),
                (Certificate[]) null);

        OriginLoader loader = new OriginLoader();
        Class<?> type = loader.fromSource(
                "demo.plugin.Greeter", bytes, source);

        CodeSource recorded =
                type.getProtectionDomain().getCodeSource();

        System.out.println("from origin loader="
                + (type.getClassLoader() == loader));
        System.out.println("source has marker="
                + (recorded != null
                    && recorded.getLocation() != null
                    && recorded.getLocation().getPath()
                        .endsWith("source.jar")));
    }
}
~~~

Biên dịch/chạy từ `pd-lab`:

~~~bash
javac --release 17 -d build/host host-src/SecureSourceDemo.java
java -cp build/host SecureSourceDemo
~~~

Stdout:

~~~text
from origin loader=true
source has marker=true
~~~

**Giải thích:** `SecureClassLoader` giúp chuyển CodeSource sang ProtectionDomain; `Source.jar` trên đường metadata **không được chương trình tải hoặc xác minh**. Thí nghiệm vẫn đọc bytes từ file `build/plugin/demo/plugin/Greeter.class`. Đặt URL tùy ý không chứng minh provenance.

`URLClassLoader` là subclass phổ biến của `SecureClassLoader`, có cơ chế lấy classes/resources từ URL search path và gắn metadata code source liên quan. Dùng đúng loader thư viện này thường đơn giản hơn tự viết `defineClass` nếu nhu cầu chỉ là nạp JAR động; vẫn phải quản lý `URLClassLoader.close()` và TCCL/resources.

## 8. Certificate/signers của package: bất biến phải giữ

Một điểm quan trọng trong Javadoc của `ClassLoader.defineClass`: **class đầu tiên được định nghĩa trong một package** xác định bộ certificates mà những class tiếp theo trong package ấy phải nhất quán. Certificate set được lấy từ `CodeSource` trong `ProtectionDomain`.

Ví dụ ý niệm:

~~~text
Loader L
  package example.lib
    A.class -- CodeSource certificates = {Signer-X}
    B.class -- CodeSource certificates = {Signer-X}  → cùng set: hợp lệ
    C.class -- CodeSource certificates = {Signer-Y}  → khác set: SecurityException
~~~

Điều này áp dụng ở phạm vi package của **cùng loader** theo hợp đồng định nghĩa class. Nó **không** có nghĩa hai class ở các package khác nhau buộc dùng chung signer, hoặc mọi JAR cùng tên package ở hai loader khác nhau đều chia sẻ một bộ certificates.

**Phân biệt hai yếu tố dễ lẫn:**

- `CodeSource.getLocation()` khác nhau **không tự động đồng nghĩa** signer mismatch. Java kiểm tra **bộ certificates**, không so bằng URL của JAR.
- Nếu một class unsigned và class khác signed trong cùng package của loader, sự khác biệt certificate set có thể bị từ chối. Lỗi cũng có thể xảy ra khi trộn signed JARs với signer sets khác.
- `Package sealing` là quy tắc khác: metadata manifest/`definePackage` có thể yêu cầu classes của package đến từ một seal base nhất quán. Đừng gọi mọi lỗi sealing là certificate mismatch.
- Đặt `name=null` có thể tránh bước so certificate package theo mô tả Javadoc, **không phải cách sửa đúng**. Hãy cung cấp binary name và tổ chức JARs/signer nhất quán.

### 8.1. Không “tự ký” bằng cách nhét certificates vào `CodeSource`

Tự tạo một `CodeSource(URL, Certificate[])` bằng certificates tự thu thập không biến bytes thành code signed đã xác thực. Muốn chứng minh JAR signed, phải có quy trình xác minh signature/entry bytes theo JAR verifier trước khi tin certificate metadata.

Một nguồn đáng kiểm tra:

~~~bash
jarsigner -verify -verbose -certs plugin.jar
~~~

Đây là mẫu lệnh kiểm tra **JAR thực**; thay `plugin.jar` bằng artifact của bạn. `jarsigner` thuộc JDK toolchain (kiểm tra availability trong JDK đang dùng). Với custom `JarFile` loader, lưu ý thông tin signer của entry có thể chỉ có ý nghĩa sau khi verifier đọc/xác thực đủ nội dung entry; đừng lấy signer metadata từ một entry chưa được xác minh rồi gán cho class.

## 9. Vì sao `ProtectionDomain` không còn là sandbox trên JDK hiện đại?

### 9.1. Lịch sử cần phân biệt theo phiên bản

| Phiên bản | Tình trạng |
| --- | --- |
| Java 8, nhiều JDK trước 17 | Security Manager/Policy từng là cơ chế có thể kiểm soát permissions cho code theo ProtectionDomain khi được kích hoạt và có security checks |
| Java 17–23 | Security Manager đã **deprecated for removal**; hành vi kích hoạt phụ thuộc release và cấu hình, không nên khởi tạo dự án sandbox mới dựa vào nó |
| Java 24 trở lên | **Security Manager permanently disabled** (JEP 486); không thể bật lại ở startup hoặc bằng `System.setSecurityManager` |
| JDK 25/26 | `ProtectionDomain`/`CodeSource` vẫn tồn tại cho API compatibility/metadata, nhưng không dùng `PermissionCollection` để chặn tài nguyên theo Security Manager |

JDK 24+ có các đặc điểm quan trọng theo hướng dẫn Oracle:

- `System.getSecurityManager()` trả `null`.
- `System.setSecurityManager(...)` ném `UnsupportedOperationException`.
- Cố bật bằng các cờ `-Djava.security.manager=...` được JDK từ chối khi khởi động.
- Java Policy API bị vô hiệu hóa/thu hẹp; domain không được cấp permissions từ policy hoạt động kiểu Security Manager cũ.
- Một số security-related methods đổi thành no-op, trả giá trị cố định, hoặc ném exception theo API migration.
- Các kiểm tra class definition **như tên `java.*`, class-file name mismatch và signer consistency** vẫn phải được xử lý theo Javadoc `defineClass`; đừng suy ra “bỏ Security Manager” đồng nghĩa “mọi bytecode được định nghĩa vô điều kiện”.

**Kết luận kỹ thuật:** `new ProtectionDomain(cs, permissions)` có thể vẫn mô tả `permissions` đã được truyền, nhưng **không có cơ chế Security Manager để cưỡng chế** rằng plugin không được mở socket/file/process. Muốn bảo vệ hệ thống khỏi plugin không tin cậy, dùng **OS process boundary**, containers, filesystem/network permissions, sandbox OS/VM phù hợp, signature verification, và hạn chế khả năng gọi APIs ở mức kiến trúc.

### 9.2. `ProtectionDomain.implies` và `PermissionCollection` không nên là quyết định phân quyền của hệ thống

Trong các JDK cũ, `ProtectionDomain.implies(permission)` có ý nghĩa trong mô hình policy/permission. Sau JDK 24, semantics policy bị giảm cấp; kết quả trên metadata không tương đương một bước OS/VM enforcement. Hệ thống hiện đại không nên dựa vào phép thử domain permissions để xác định caller có được đọc secrets hay truy cập tài nguyên không.

Nếu cần authorization trong ứng dụng, dùng cơ chế **principal/identity validation** và permission checks ở business/API boundary (ví dụ authenticated caller + role/capability check), không dùng classloader domain làm thay actor identity.

## 10. Những khác biệt không thuộc `ProtectionDomain`

Đừng nhầm các tầng:

1. **Runtime class identity:** binary name + defining loader. Domain khác không cho phép define trùng class name trong cùng loader; domain giống không khiến class ở hai loader trở thành một type.
2. **Package certificate consistency:** dựa CodeSource certificates trong quá trình `defineClass`; không phải `JPMS requires`.
3. **Package sealing:** quy tắc khai báo seal base/manifest, khác với signer certificates.
4. **JPMS module access:** `requires`/readability, `exports`, `opens`, module layer. Gắn domain không tự sửa `IllegalAccessError` hay `InaccessibleObjectException`.
5. **Resource loading:** `ClassLoader.getResource` tìm resource, không dùng `ProtectionDomain.getCodeSource()` làm resolver.
6. **Native-access controls:** cờ `--enable-native-access` trên JDK mới là cơ chế riêng; không dùng ProtectionDomain để bật JNI/FFM.
7. **Class linking và initialization:** `defineClass` tạo runtime class; `resolveClass` link; `<clinit>` chạy theo trigger initialization, không vì thêm domain.
8. **Jar URL và file handles:** domain chỉ metadata; việc mở/đóng JAR là nhiệm vụ của loader/resource owner như `URLClassLoader` và `JarFile`.

## 11. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoClassDefFoundError: wrong name` lúc `defineClass` | `name` khác binary name trong bytes | Đổi mapping class name ↔ class file; không đổi tên tùy ý |
| `SecurityException: Prohibited package name java...` | Loader không được phép define package `java.*` | Không dùng tên `java.*` cho plugin |
| `SecurityException` về signer mismatch | Trộn classes cùng package nhưng khác signing certificate set | Giữ signer/package nhất quán; xác minh JARs |
| `ClassFormatError` hoặc `VerifyError` | Bytes hỏng/incompatible | Kiểm tra classfile, Java version, bytecode toolchain |
| `IndexOutOfBoundsException` | Sai `off`/`len` | Tính bounds đúng; dùng đúng buffer |
| `LinkageError` khi define trùng tên | Loader định nghĩa class cùng name nhiều lần | `findLoadedClass` + `getClassLoadingLock`; không redefine |
| Plugin vẫn mở được file dù domain có empty Permissions | Không có Security Manager enforcing domain | Dùng OS/process isolation và authorization rõ ràng |
| `ClassCastException` với cùng tên class | Hai defining loaders khác nhau | Shared API qua parent, kiểm tra type identity |
| `IllegalAccessError`/`InaccessibleObjectException` | JPMS access/exports/opens | Sửa module graph/access; domain không cấp mở package |
| Audit source URL sai | CodeSource do loader tự tạo không khớp nguồn bytes | Theo dõi artifact thực và xác minh trước khi gắn metadata |
| `getProtectionDomain().getCodeSource()` null/URL null | Domain mặc định hoặc thiếu metadata nguồn | Null-check; không kết luận class chưa tồn tại |
| ByteBuffer reuse gặp lỗi ngẫu nhiên | State/contents của buffer bị tái sử dụng sai | Giữ bytes bất biến, duplicate/slice và quản lý I/O lifetime |

### 11.1. Checklist khi tự viết `findClass`

- [ ] Nhận đúng **binary name** và ánh xạ đến classfile entry hợp lệ.
- [ ] Đọc bytes từ nguồn tin cậy, đóng `InputStream`/`JarFile` khi phù hợp.
- [ ] Nếu cần CodeSource, lấy từ **artifact thực** và verify signatures trước khi tin certificate metadata.
- [ ] Chọn default PD, explicit PD hay `SecureClassLoader` overload theo nhu cầu metadata, không dùng để hứa sandbox.
- [ ] Duy trì certificate consistency trong cùng package/loader và package sealing khi có khai báo.
- [ ] Không định nghĩa classes trong `java.*` bằng plugin/application loader.
- [ ] Giữ `findLoadedClass`/locking do `loadClass` mặc định xử lý, tránh duplicate define.
- [ ] Kiểm tra cả byte[] overload và ByteBuffer overload nếu library của bạn hỗ trợ hai nguồn.
- [ ] Log binary name, defining loader, CodeSource location, module và phiên bản artifact **không tiết lộ thông tin nhạy cảm**.
- [ ] Khi reload plugin, dùng loader thế hệ mới và dọn loader/JAR handles cũ; đổi domain không reset runtime class.
- [ ] Với JDK 24+, dùng process/OS sandbox cho code không tin cậy thay vì Security Manager/PD.

## 12. Câu hỏi tự kiểm tra

1. Không truyền `ProtectionDomain` vào `defineClass` thì class có domain không? **Có, domain mặc định.**
2. Truyền `null` cho PD overload có khác default overload không? **Về lựa chọn domain, không: đều dùng default.**
3. `CodeSource.getLocation()` có chứng minh bytecode thực sự đến từ URL ấy không? **Không nếu loader tự đặt metadata mà không xác minh nguồn.**
4. `ProtectionDomain` có quyết định một class ở loader A cast được sang class cùng tên loader B không? **Không; runtime type identity phụ thuộc defining loader.**
5. Overload nào của `SecureClassLoader` nhận `CodeSource`? **Byte array và ByteBuffer variants của chính `SecureClassLoader`.**
6. Vì sao `name=null` không nên dùng cho `defineClass`? **Làm mất kiểm tra expected binary name và suy yếu certificate/package consistency check.**
7. Khác URL CodeSource nhưng certificate sets giống có tự bị từ chối signer check không? **Không chỉ vì khác URL; signer check dựa certificate sets.**
8. `ProtectionDomain` có tự kiểm tra chữ ký số JAR từ một URL giả định không? **Không.**
9. JDK 25 còn bật Java Security Manager để sandbox plugin không? **Không; đã bị disable vĩnh viễn từ JDK 24.**
10. `defineClass` nhận ByteBuffer có cho phép định nghĩa trùng tên trong cùng loader không? **Không.**
11. Mẫu test nhận `wrong name` chứng minh điều gì? **Class file có một binary name thật; tham số name khác sẽ bị từ chối.**
12. `ProtectionDomain.getPermissions()` khác null có chắc VM sẽ cấm operation không thuộc permissions không? **Không trên JDK 24+; không có Security Manager enforcement.**
13. Có nên tin `Signer-X` chỉ do custom loader tự nhét vào `CodeSource`? **Không; phải xác minh JAR signature/entry bytes.**

## 13. Tài liệu chuẩn

1. [`ClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): mọi overload `defineClass`, domain mặc định, package signer constraints, `name` validation, `ByteBuffer`.
2. [`SecureClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass(..., CodeSource)` và `getPermissions` hook; API note về Security Manager.
3. [`ProtectionDomain` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/ProtectionDomain.html): constructors, `getCodeSource`, `getPermissions`, `getClassLoader`, `getPrincipals`.
4. [`CodeSource` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/CodeSource.html): location, certificate/signer metadata.
5. [Security Manager Permanently Disabled — JDK 25](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html): thay đổi API/policy từ JDK 24, lý do permissions không còn tạo sandbox.
6. [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): quyết định thiết kế chính thức.
7. [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loader.
8. [`JarFile` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarFile.html): JAR entries, verifier metadata và code signer information.

**Kết luận:** Các biến thể `defineClass` khác nhau ở **hình thức bytes** (`byte[]` hay `ByteBuffer`) và **cách chọn domain** (mặc định, truyền `ProtectionDomain` hoặc để `SecureClassLoader` tạo từ `CodeSource`). Domain gắn thông tin về nguồn mã/chứng chỉ và permission metadata vào runtime class, nhưng **không làm thay class identity** và **không thay sandbox** trên JDK 24+. Luôn bảo toàn expected binary name, package signer consistency và kiểm chứng artifact thực trước khi tin metadata.
