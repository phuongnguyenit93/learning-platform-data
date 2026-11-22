# Định nghĩa package và nguồn mã khi cần trong ClassLoader tùy chỉnh

> **Bối cảnh:** Java Core → ClassLoader → Loader tùy chỉnh. Khi tự đọc bytecode từ thư mục, JAR, kho plugin hoặc bộ sinh mã, bạn không chỉ quyết định **class nào được nạp** mà đôi khi còn cần gắn **thông tin package** (phiên bản, vendor, package sealing) và **nguồn mã — CodeSource** cho các class được định nghĩa. Bài học giải thích khi nào cần `definePackage`, cách phối hợp `SecureClassLoader`/`ProtectionDomain`, sự khác biệt giữa metadata và cơ chế bảo vệ thật, và các quy tắc không được phá vỡ. Ví dụ dùng Java 17+.

## 1. Vấn đề: defineClass thành công nhưng metadata ở đâu?

Một custom loader đơn giản thường trông như sau:

```java
// Snippet bên trong một subclass của ClassLoader:
byte[] bytes = readClassBytes(binaryName);
return defineClass(binaryName, bytes, 0, bytes.length);
```

Ở đây `readClassBytes` là helper do ứng dụng tự xây; snippet **không độc lập**. Nó có thể đủ nếu chỉ muốn nạp class thường. Nhưng sau khi định nghĩa `sample.plugin.Task`, những thông tin sau có thể quan trọng:

- `Task.class.getPackage().getSpecificationVersion()` báo phiên bản đặc tả package nào?
- `Task.class.getPackage().getImplementationVersion()` phản ánh bản release của plugin nào?
- Package có được **sealed** để tránh lẫn class từ nguồn khác không?
- `Task.class.getProtectionDomain().getCodeSource()` có thể cho biết class do nguồn nào cung cấp không?
- Nếu JAR có chữ ký, các class trong **cùng package của cùng loader** có tuân thủ quy tắc certificates nhất quán không?

**Câu trả lời:** `defineClass` tự tạo `Package` mặc định cho tên package nếu loader chưa có, nhưng metadata đặc thù **không tự phát sinh từ một tệp JAR manifest** chỉ nhờ bạn đọc bytes rồi gọi `defineClass`. Nếu ứng dụng muốn các thuộc tính cụ thể, hãy cấu hình chúng **trước lần định nghĩa class đầu tiên trong package**; nếu cần nguồn mã, hãy dùng overload `defineClass` nhận `ProtectionDomain` hoặc `SecureClassLoader.defineClass` nhận `CodeSource`.

Không phải custom loader nào cũng cần làm mọi việc này: chỉ thêm thông tin/cơ chế khi có use case rõ ràng và có thể duy trì tính nhất quán.

## 2. Phân biệt ba khái niệm không nên trộn lẫn

| Khái niệm | Được đại diện bằng | Trả lời câu hỏi |
| --- | --- | --- |
| **Java package metadata** | `java.lang.Package` | Tên package, specification/implementation title/version/vendor, tình trạng sealed, annotations nếu có. |
| **Code source** | `java.security.CodeSource` | Location URL và tập certificates/signers liên quan đến nguồn code (nếu được cung cấp/xác thực). |
| **Protection domain** | `java.security.ProtectionDomain` | Nhóm metadata security domain gồm code source, class loader, permission collection/principals theo cấu hình/constructor. |

Một `Class<?>` có thể biết package của nó trong khi `ProtectionDomain.getCodeSource() == null`. Ngược lại, một class có `CodeSource` nhưng package metadata phiên bản trống. Hai nhóm thông tin **không tự thay thế nhau**.

Thứ tự khuyến nghị của custom loader:

```text
1. Nhận yêu cầu loadClass(binaryName)
2. Kiểm tra đã load và thử parent theo policy
3. Trong findClass:
      - tìm đúng bytes của một class file
      - xác định package name, manifest metadata, source URL
      - kiểm tra/định nghĩa Package nếu cần
      - tạo CodeSource hoặc ProtectionDomain phù hợp
      - defineClass(binaryName, bytes, domain/source)
4. JVM liên kết/khởi tạo khi quy tắc tương ứng yêu cầu
```

`definePackage`, `defineClass` và `resolveClass` là những bước **khác nhau**; việc gọi `definePackage` không hề “load” tất cả lớp trong package.

## 3. Package là gì trong runtime đa ClassLoader?

Ở source, các lớp có thể khai báo:

```java
package sample.plugin;
```

Nhưng tại JVM, **runtime package** được phân biệt bằng **tên package + defining class loader**. Hai loader khác nhau đều có thể định nghĩa một package tên `sample.plugin` và mỗi loader quản lý `Package` của riêng mình.

Do đó:

```text
Loader A defines sample.plugin.Task
    -> (binary name sample.plugin.Task, defining loader A)
    -> package sample.plugin của loader A

Loader B defines sample.plugin.Task
    -> (binary name sample.plugin.Task, defining loader B)
    -> package sample.plugin của loader B

A != B: hai runtime types khác nhau, hai runtime packages khác nhau
```

Hệ quả quan trọng:

- `package-private` không tự động truy cập được giữa hai lớp chỉ vì string `package` giống nhau.
- Cùng tên class do hai loader định nghĩa là **hai loại runtime** khác nhau; `ClassCastException` có thể xảy ra khi ép object giữa chúng.
- `getDefinedPackage("sample.plugin")` chỉ hỏi các package được **loader nhận câu hỏi trực tiếp định nghĩa**, không quét ngược parent.
- `getPackage(String)` của `ClassLoader` đã **deprecated từ Java 9**, bởi nó có thể tìm cả parent và cho metadata package không đúng lớp định nghĩa; ưu tiên `getDefinedPackage`.
- Để hỏi `Package` gắn với một class cụ thể, dùng `clazz.getPackage()` thay vì cố suy luận qua system loader.

### Package object không phải directory hay classpath root

`Package` là metadata runtime, **không phải** một thư mục `sample/plugin` được tạo trên disk. `definePackage` không thêm đường tìm JAR; và `getDefinedPackage` không cho biết JAR nào chứa mọi class package ấy.

## 4. Khi nào JVM tự tạo Package?

API `ClassLoader.defineClass(String, byte[], int, int, ProtectionDomain)` và các overload liên quan có cơ chế bảo đảm package phù hợp tên class được định nghĩa. Nếu loader chưa có `Package` cho tên đó, việc định nghĩa class có thể tạo **package mặc định** với các thuộc tính metadata theo quy tắc `Package`.

Vì vậy loader tối giản **không bắt buộc** gọi `definePackage` trước mọi `defineClass`.

Tuy nhiên, nếu bạn muốn specification title, version, implementation vendor hoặc `sealBase` được thiết lập theo một manifest, **phải định nghĩa tường minh package trước khi `defineClass` lần đầu ở package đó**. Đừng dựa vào việc “sau khi nạp vài class rồi mới cập nhật”.

Ví dụ:

```text
defineClass("sample.plugin.First", bytesFirst, ...)
       -> nếu package sample.plugin chưa tồn tại:
          package metadata mặc định được tạo

definePackage("sample.plugin", ... metadata cần có ...)
       -> quá muộn: không thể định nghĩa lại cùng package của loader
```

Một package name chỉ được định nghĩa **một lần trong một loader** và không thể thay đổi các thuộc tính bằng `definePackage` về sau. Vì thế quyết định metadata lúc load class đầu tiên là một phần thiết kế loader, không phải việc “vá nhãn” sau khi đã nạp.

## 5. definePackage: phiên bản, vendor và sealing

Overload được dùng phổ biến:

```java
protected Package definePackage(
        String name,
        String specTitle,
        String specVersion,
        String specVendor,
        String implTitle,
        String implVersion,
        String implVendor,
        java.net.URL sealBase);
```

`definePackage` là method `protected` trên `ClassLoader`: subclass có thể gọi từ logic nội bộ; mã ở ngoài không được tự do gọi nếu không có quyền `protected` thích hợp.

Các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `name` | Tên package kiểu dấu chấm, ví dụ `sample.plugin`. |
| `specTitle` | Tên specification. |
| `specVersion` | Phiên bản specification; `Package.isCompatibleWith` phân tích theo quy tắc số dot-separated. |
| `specVendor` | Nhà cung cấp specification. |
| `implTitle` | Tên implementation. |
| `implVersion` | Chuỗi phiên bản implementation, do bên đóng gói định nghĩa. |
| `implVendor` | Nhà cung cấp implementation. |
| `sealBase` | URL nguồn mà package được đóng dấu **sealed**; `null` nghĩa package không sealed. |

Một ví dụ trong custom loader:

```java
definePackage(
    "sample.plugin",
    "Demo API", "1.0", "Demo",
    "Plugin Impl", "2.0", "Demo",
    null);
```

Sau đó, với lớp `sample.plugin.Task` do loader ấy định nghĩa:

```java
Package p = taskClass.getPackage();
System.out.println(p.getSpecificationTitle()); // Demo API
System.out.println(p.getImplementationVersion()); // 2.0
System.out.println(p.isSealed()); // false
```

Đây là **hai snippet cần nằm trong subclass và caller tương ứng**; `taskClass` phải được định nghĩa trước. Mục 7 có một chương trình độc lập có thể chạy thật.

### Giới hạn của phiên bản

`getImplementationVersion()` chỉ trả **chuỗi metadata** do loader đặt; JVM không đảm bảo đó là phiên bản Maven/SemVer hoặc trùng mã đang chạy. Với `getSpecificationVersion()`, `Package.isCompatibleWith(String)` so sánh các thành phần phiên bản dạng số và có thể ném `NumberFormatException` nếu format không phù hợp. Đừng dùng `Package` metadata như công cụ dependency resolver hay làm điều kiện an toàn để chấp nhận code không tin cậy.

### Không được redefine cùng package

Nếu gọi `definePackage` lần nữa cho cùng `name` trên cùng loader, method có thể ném `IllegalArgumentException` do package đã được định nghĩa. Với loader song song, hai thread cùng chuẩn bị metadata package cần đồng bộ thích hợp, tránh race giữa `getDefinedPackage` và `definePackage`.

## 6. Package sealing: nó bảo đảm gì, và custom loader cần làm gì?

Một `Package` được **sealed** khi `sealBase` khác `null`. Về ý nghĩa đóng gói JAR, các class trong package sealed phải thuộc đúng nguồn archive được đánh dấu. Kiểm tra metadata:

```java
Package p = someClass.getPackage();
boolean sealed = p.isSealed();
boolean fromExpectedBase = p.isSealed(expectedJarUrl);
```

`someClass` và `expectedJarUrl` là biến trong chương trình có thật; snippet minh họa API.

**Điểm thường bị hiểu sai:** gán `sealBase` vào `definePackage` chỉ tạo thuộc tính metadata sealed cho `Package`. Nếu **bạn tự viết loader** và tự gọi `defineClass` từ raw bytes, bạn phải tự quản lý việc xác định nguồn, kiểm tra package sealing và consistency theo thiết kế loader; không nên giả định mọi logic so khớp nguồn JAR/manifest của `URLClassLoader` sẽ tự được tái hiện cho loader của bạn.

Quy tắc kiểm tra một cách **minh họa** trước khi define thêm class từ `sourceUrl`:

```java
// Đặt trong loader, trước defineClass, với:
// packageName, sourceUrl và shouldBeSealed đã được xác định từ nguồn đáng tin.
Package pkg = getDefinedPackage(packageName);
if (pkg == null) {
    definePackage(packageName,
            null, null, null, null, null, null,
            shouldBeSealed ? sourceUrl : null);
} else if (pkg.isSealed()) {
    if (!pkg.isSealed(sourceUrl)) {
        throw new SecurityException("Package sealing violation");
    }
} else if (shouldBeSealed) {
    throw new SecurityException("Cannot seal already-unsealed package");
}
```

Đây là **snippet đặt trong subclass**, với ba biến `packageName`, `sourceUrl`, `shouldBeSealed` từ policy của ứng dụng. Trong sản phẩm, cần cùng khóa đồng bộ khi kiểm tra và khi nạp class, xác định package metadata một lần, và tránh lẫn certificate sets/source policy giữa các JAR.

Khi dùng `URLClassLoader`, nó có triển khai xử lý manifest/package metadata và package sealing khi nạp từ JAR; không nên xây lại nếu chỉ cần loader chuẩn. **Sealing không thay thế quyền truy cập module, chữ ký JAR hoặc isolation giữa các defining loaders.**

## 7. Nguồn mã: CodeSource và ProtectionDomain

### CodeSource gồm những gì?

`java.security.CodeSource` chứa:

- **Location URL** mô tả nguồn gắn với class, thường là JAR URL hoặc directory URL.
- **Certificates/signers** gắn với code, khi có và được xác thực phù hợp.

Ví dụ:

```java
java.net.URL origin = Path.of("build/plugin")
        .toAbsolutePath().toUri().toURL();

java.security.CodeSource source = new java.security.CodeSource(
        origin, (java.security.cert.Certificate[]) null);
```

Đây là snippet cần `import java.nio.file.Path;` (hoặc tên đầy đủ như trong ví dụ), không phải class có `main`. `origin` ở đây mô tả **nơi ứng dụng cho rằng bytes đến từ**. **Việc tự đặt CodeSource URL không chứng minh bytes thực sự được tải từ nguồn ấy**; bạn phải đọc/kiểm tra chúng đúng quy trình.

### Gắn nguồn qua SecureClassLoader

`java.security.SecureClassLoader` mở rộng `ClassLoader` và có overload:

```java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len, CodeSource cs);

protected final Class<?> defineClass(
        String name, java.nio.ByteBuffer b, CodeSource cs);
```

Nếu truyền `CodeSource` khác `null`, `SecureClassLoader` tạo `ProtectionDomain` thích hợp cho class được định nghĩa. Bạn có thể kiểm tra:

```java
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd.getCodeSource();
URL url = cs == null ? null : cs.getLocation();
```

Đây là snippet, `clazz` là `Class<?>` được loader định nghĩa. Trường hợp không có nguồn mã rõ ràng, `cs` có thể `null`. Không bao giờ mặc định `clazz.getProtectionDomain().getCodeSource().getLocation()` luôn có giá trị — tránh `NullPointerException`.

### Gắn bằng ClassLoader với ProtectionDomain

Nếu extends `ClassLoader` thay vì `SecureClassLoader`, có thể dùng:

```java
defineClass(
        binaryName, bytes, 0, bytes.length, protectionDomain);
```

`protectionDomain` là `java.security.ProtectionDomain` do ứng dụng tạo hoặc quản lý, có thể chứa `CodeSource` và các thông tin liên quan. Nếu `null`, `defineClass` dùng default domain theo Javadoc. **Không phải mọi custom loader phải tự chế tạo ProtectionDomain**; chỉ làm khi metadata và quyền hạn thực sự cần kiểm soát.

### CodeSource không phải sandbox bảo mật tự động

Trong Java 17, `SecurityManager` đã bị deprecated for removal; từ JDK 24, Security Manager đã bị vô hiệu hóa vĩnh viễn theo JEP 486. Không dùng `ProtectionDomain` hay `CodeSource` như một lời hứa rằng bytecode plugin không tin cậy đã bị sandbox theo security policy cũ. Chúng vẫn là API metadata và các ràng buộc liên quan, nhưng isolation an toàn cho code không tin cậy có thể cần **process boundary**, container hoặc giải pháp có mô hình threat phù hợp.

## 8. Thực hành đầy đủ: metadata Package + CodeSource

Ví dụ sau tạo hai custom loader riêng, cùng đọc bytecode `sample.plugin.Task`:

- Loader thứ nhất **không sealed**, metadata specification/implementation được gắn trước khi định nghĩa class.
- Loader thứ hai **sealed** tại cùng URL nguồn.
- Mỗi loader tạo **runtime class và Package riêng**.
- Mỗi class lưu CodeSource URL đã khai báo thông qua `SecureClassLoader`.

Không dùng thư viện ngoài JDK và không cần file JAR vật lý; `origin` được gắn là URL của thư mục `build/plugin`, đúng với nơi ví dụ đọc class bytes.

### Cấu trúc source

```text
src/
  sample/
    plugin/
      Task.java
  app/
    PackageSourceDemo.java
build/
  plugin/        (javac tạo)
  app/           (javac tạo)
```

**File `src/sample/plugin/Task.java`:**

```java
package sample.plugin;

public class Task {
    public String message() {
        return "hello";
    }
}
```

**File `src/app/PackageSourceDemo.java`:**

```java
import java.io.IOException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class PackageSourceDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL origin;
        private final boolean sealed;

        PluginLoader(Path root, URL origin, boolean sealed) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
            this.origin = origin;
            this.sealed = sealed;
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path path = root.resolve(
                    binaryName.replace('.', '/') + ".class");

            final byte[] bytes;
            try {
                bytes = Files.readAllBytes(path);
            } catch (IOException ex) {
                throw new ClassNotFoundException(binaryName, ex);
            }

            int dot = binaryName.lastIndexOf('.');
            if (dot >= 0) {
                String pkgName = binaryName.substring(0, dot);
                if (getDefinedPackage(pkgName) == null) {
                    definePackage(
                            pkgName, "Demo API", "1.0", "Demo",
                            "Plugin Impl", "2.0", "Demo",
                            sealed ? origin : null);
                }
            }

            CodeSource codeSource = new CodeSource(
                    origin, (Certificate[]) null);

            return defineClass(
                    binaryName, bytes, 0, bytes.length, codeSource);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build/plugin").toAbsolutePath();
        URL origin = root.toUri().toURL();

        PluginLoader open = new PluginLoader(root, origin, false);
        Class<?> first = Class.forName(
                "sample.plugin.Task", false, open);
        Package pkg = first.getPackage();

        System.out.println("class defined by custom loader: "
                + (first.getClassLoader() == open));
        System.out.println("package title: "
                + pkg.getSpecificationTitle());
        System.out.println("package version: "
                + pkg.getImplementationVersion());
        System.out.println("unsealed: " + !pkg.isSealed());
        System.out.println("code source matches: "
                + origin.equals(first.getProtectionDomain()
                        .getCodeSource().getLocation()));
        System.out.println("repeated lookup same class: "
                + (Class.forName("sample.plugin.Task", false, open)
                        == first));

        PluginLoader sealed = new PluginLoader(root, origin, true);
        Class<?> second = Class.forName(
                "sample.plugin.Task", false, sealed);

        System.out.println("sealed: "
                + second.getPackage().isSealed());
        System.out.println("sealed at origin: "
                + second.getPackage().isSealed(origin));
        System.out.println("different runtime classes: "
                + (first != second));
        System.out.println("different Package objects: "
                + (first.getPackage() != second.getPackage()));
    }
}
```

### Cách chạy

Đứng trong thư mục gốc có `src`, chạy:

```bash
javac -d build/plugin src/sample/plugin/Task.java
javac -d build/app src/app/PackageSourceDemo.java
java -cp build/app PackageSourceDemo
```

**Stdout đã được biên dịch và đối chiếu trên OpenJDK 24; code chỉ dùng API hiện diện từ Java 17 trở về trước:**

```text
class defined by custom loader: true
package title: Demo API
package version: 2.0
unsealed: true
code source matches: true
repeated lookup same class: true
sealed: true
sealed at origin: true
different runtime classes: true
different Package objects: true
```

### Giải thích kết quả

1. `build/plugin` **không nằm trên `-cp build/app`**, vì vậy parent platform loader không định nghĩa `sample.plugin.Task` từ đó. `PluginLoader.findClass` nhận tên từ `Class.forName(name, false, loader)` và tự đọc bytes.
2. `getDefinedPackage(pkgName) == null` cho phép package metadata được khai báo trước khi `defineClass`. Hai giá trị `Demo API`, `2.0` xuất hiện đúng ở `clazz.getPackage()`.
3. `CodeSource(origin, null)` gắn một URL nguồn mà ví dụ cũng thật sự dùng để đọc bytes. `ProtectionDomain.getCodeSource().getLocation()` trả URL phù hợp. Ví dụ **không kiểm tra chữ ký** vì nguồn class test không có certificates.
4. `Class.forName(..., false, open)` lần tiếp theo trả **cùng `Class<?>`** trên cùng loader.
5. Loader thứ hai gắn `sealBase = origin`, nên `Package.isSealed()` và `isSealed(origin)` trả `true`. Thí nghiệm chứng minh metadata package; nó **không kiểm tra package sealing across multiple source JARs**.
6. Hai loader độc lập cho phép cùng binary name nhưng hai kiểu runtime khác nhau, cùng hai đối tượng `Package` riêng. **Không** suy ra chỉ vì chúng có CodeSource URL giống nhau thì type identity cũng giống nhau.

### Những giới hạn của ví dụ khi triển khai thực tế

`findClass` này chỉ là phiên bản đơn giản một lớp/package: nó chưa có cache/manifest parser, certificate verification, kiểm tra package sealing khi nạp nhiều nguồn, giới hạn kích thước file, chính sách nguồn cho phép hoặc đăng ký parallel-capable. Với nhiều class cùng package và concurrent loading, `getDefinedPackage` + `definePackage` phải được bảo vệ trong đúng cơ chế khóa và tránh `IllegalArgumentException` do race.

Không dùng nguyên loader này để chạy bytecode không tin cậy; `CodeSource` không biến nó thành sandbox.

## 9. Metadata từ JAR manifest: nên làm đúng thế nào?

Khi class đến từ JAR, những thuộc tính tương ứng có thể khai báo trong `META-INF/MANIFEST.MF`:

```text
Manifest-Version: 1.0
Specification-Title: Demo API
Specification-Version: 1.0
Specification-Vendor: Demo
Implementation-Title: Plugin Impl
Implementation-Version: 2.0
Implementation-Vendor: Demo
Sealed: false
```

Đây là **ví dụ nội dung manifest**, không phải output JVM. Manifest còn cho phép **package-specific sections**, thường có dạng:

```text
Name: sample/plugin/
Specification-Title: Plugin API
Implementation-Version: 2.1
Sealed: true
```

Khi loader tùy chỉnh phân tích manifest, cần xác định chính sách các attributes theo package section hoặc main section của manifest theo JAR Specification. Tên section dùng **dấu slash** như entry name, trong khi `definePackage` dùng **dấu chấm** trong tên package. `Sealed: true` yêu cầu seal base phù hợp URL **nguồn archive**, không phải tùy tiện dùng URL tới `.class` entry.

Một loader quản lý JAR nên:

1. Mở JAR một cách có kiểm soát, xác định chính xác nguồn class bytes.
2. Đọc manifest/metadata cho package liên quan, xét scope của main/section attributes.
3. Trước lần define đầu tiên, `definePackage` với metadata thích hợp.
4. Với package sealed, kiểm tra nguồn của các class tiếp theo trong **cùng loader/package** khớp seal base.
5. Đưa `CodeSource` gắn với **nguồn thật** của bytes; nếu có chữ ký, chỉ công nhận certificates đã được kiểm tra theo cơ chế JarFile/JarVerifier thích hợp.

Nếu chỉ cần nạp từ URL/JAR thông thường và muốn manifest metadata/sealing hoạt động theo cơ chế chuẩn, **ưu tiên `URLClassLoader`** — nó đã được xây cho đường tìm URL/JAR cùng metadata packaging. Tự xử lý `JarFile` và gọi `defineClass` trên bytes từ entry nghĩa là **bạn sở hữu phần trách nhiệm còn lại**, không phải đã nhận miễn phí toàn bộ behavior của `URLClassLoader`.

### Không nhầm CodeSource với manifest title/version

Manifest metadata như `Implementation-Version` là **thông tin package**. `CodeSource` chủ yếu liên quan **location và certificates**. Bạn có thể có package version `2.0` và `CodeSource` URL `file:/.../plugin.jar` cùng lúc; chúng không phải cùng một thuộc tính, và không tự suy được cái này từ cái kia qua API `defineClass`.

## 10. Certificates, signing và kiểm tra nhất quán package

Javadoc `ClassLoader#defineClass(..., ProtectionDomain)` quy định **class đầu tiên được định nghĩa trong một package** xác lập **tập certificates** mà những class tiếp theo **trong package do cùng loader định nghĩa** phải có. Tập certificates lấy từ `CodeSource` của `ProtectionDomain`; nếu khác sẽ gây `SecurityException`. Overload `SecureClassLoader.defineClass(..., CodeSource)` phục vụ việc tạo domain cho trường hợp này.

Đặc biệt:

- `CodeSource(origin, null)` biểu thị **không cung cấp certificates**, không có nghĩa JAR đã được ký hoặc xác minh.
- Tự tạo đối tượng `Certificate` và đưa vào `CodeSource` **không tương đương** với xác minh chữ ký archive và đảm bảo bytes là dữ liệu đã được ký.
- Nếu có nhiều JAR cung cấp class trong một package, loader phải giữ **certificate sets thống nhất**. Chỉ thay `URL` source không nhất thiết gây certificate mismatch nếu certificate sets tương thích; package sealing là kiểm tra nguồn riêng.
- Nếu cần xác minh signed JAR, hãy sử dụng cơ chế JAR verification và kiểm soát quá trình đọc toàn bộ entry trước khi tin tưởng certificate metadata phù hợp. Hãy phân biệt signing assurance, loader identity, package sealing và permissions.
- Không truyền `null` làm tên binary class chỉ để tránh một số kiểm tra namespace/certificates; Javadoc khuyến nghị **luôn cung cấp binary name** để xác nhận class vừa được định nghĩa đúng như dự kiến.

Các lỗi có thể xuất hiện:

| Lỗi | Nguyên nhân điển hình |
| --- | --- |
| `IllegalArgumentException` tại `definePackage` | Package đã được định nghĩa trong cùng loader. |
| `SecurityException` tại `defineClass` | Package certificate set không nhất quán, hoặc định nghĩa tên `java.*` từ loader không được phép. |
| `NoClassDefFoundError` dạng wrong name | `binaryName` truyền vào không khớp tên thật trong bytecode. |
| `ClassFormatError` | Dữ liệu class file không hợp lệ/cắt hỏng. |
| `LinkageError` | Cố định nghĩa trùng tên class trong cùng loader, hoặc một linkage constraint khác bị vi phạm. |
| `ClassNotFoundException` | `findClass` không tìm được/read được class bytes cần tìm. |
| `NullPointerException` khi đọc CodeSource | Giả định `getProtectionDomain().getCodeSource()` luôn khác `null`. |

Không coi mọi `SecurityException` là “JAR chưa ký”; phải đọc message, cause, ngữ cảnh class/package và chính sách được loader áp dụng.

## 11. Package metadata không thay thế module system hoặc các luật Java khác

Java 9+ có JPMS với named modules, `module-info.java`, readability, `exports` và `opens`. Các thuộc tính `Package` như `Specification-Version`, `Sealed` không phải quyền truy cập module. Một class được định nghĩa trong **unnamed module** của custom loader không tự trở thành class của một named module chỉ nhờ gọi `definePackage`.

Ngoài ra:

- **Package-private access** vẫn dựa trên runtime package gồm tên package và defining loader.
- **Exports/opens** của named module kiểm soát mức truy cập/reflective access theo module rules, không được cấp bởi manifest `Sealed`.
- **Class identity** vẫn là binary name + defining loader với class/interface thông thường; hai loader đọc cùng JAR không tạo cùng runtime type.
- **ProtectionDomain/CodeSource** không phải công cụ tự động giải quyết `IllegalAccessError` do module/package boundaries hoặc lỗi thiếu class.
- Nếu plugin muốn giao tiếp qua interface của host, đặt interface chung dưới loader cha phù hợp; nếu plugin tự define bản sao interface đó, cast sẽ có thể lỗi.

Khi package-info annotations quan trọng, cần đảm bảo `package-info.class` đến từ định nghĩa loader chính xác; `ClassLoader.getPackage(String)` deprecated có thể trả package metadata từ parent khiến bạn nhìn nhầm.

## 12. Thiết kế loader thực tế: trình tự và concurrency

Một quy trình an toàn hơn cho loader có nhiều plugin JARs:

```text
Yêu cầu loadClass("sample.plugin.Task")
    |
    v
findLoadedClass / parent delegation / class loading lock
    |
    v
Tìm JAR entry thật và xác minh bytes/nguồn
    |
    v
Xác định package từ binary name
    |
    +-- package chưa có:
    |      đọc manifest và definePackage trước class đầu tiên
    |
    '-- package đã có:
           kiểm tra metadata/sealBase/certificates policy
    |
    v
Xây CodeSource / ProtectionDomain nhất quán với source
    |
    v
defineClass(name, bytes, domain/source)
    |
    v
Trả Class<?>; JVM sẽ link/init theo semantics tương ứng
```

Các điểm cần cân nhắc:

**1. Tương tranh:** `getDefinedPackage` rồi `definePackage` không phải một transaction atomic cho toàn bộ việc đọc JAR và define class. Nếu custom loader đăng ký `registerAsParallelCapable` và nhiều thread nạp **hai class khác tên trong cùng package**, class-loading lock theo tên có thể **không ngăn race ở cấp package**. Cần đồng bộ trên package state riêng; đừng đơn giản `catch (IllegalArgumentException)` rồi nuốt mà không kiểm chứng metadata/seal base có nhất quán.

**2. Không define lại:** một loader không thể cập nhật `sample.plugin.Task` chỉ bằng `defineClass` lần hai hoặc thay `CodeSource` sau khi class đã được định nghĩa. Muốn hot reload thường tạo loader mới, quản lý object cũ và interface chung.

**3. Nguyên tắc nguồn dữ liệu:** URL của `CodeSource` phải tương ứng nguồn bytes loader đã đọc nếu bạn định dùng để chẩn đoán/chính sách. Không lấy URL từ tên người dùng rồi gắn mà không kiểm tra; metadata có thể sai hoặc bị giả mạo.

**4. Sealed packages:** một package sealed phải có một source base nhất quán; nếu loader tự thực hiện kiểm tra, cần làm **trước khi define thêm class**. Một URL khác nhưng dẫn tới cùng file theo hệ thống file cũng có thể cần chính sách canonicalization/thẩm định riêng.

**5. Loader ownership:** ai chịu trách nhiệm đóng JAR/URLClassLoader/stream? `definePackage` không quản lý archive handles. Dùng try-with-resources cho `JarFile` và entry streams khi bạn tự mở.

**6. Lỗi theo giai đoạn:** define thành công không bảo đảm resolution mọi dependency hay initialization thành công. Đừng đánh đồng lỗi metadata package với `NoClassDefFoundError` do dependency thiếu hoặc static initializer thất bại.

## 13. Những sai lầm và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Luôn gọi `definePackage` trước mỗi `defineClass` mà không kiểm tra trạng thái | `IllegalArgumentException` khi nạp class thứ hai trong package. | Quản lý trạng thái package; khai báo một lần. |
| Định nghĩa class đầu tiên rồi mới đọc manifest metadata | Package mặc định đã tồn tại; metadata không cập nhật bằng definePackage. | Đọc metadata trước khi defineClass đầu tiên. |
| Dùng `getPackage` trên loader để xác định đã define package chưa | Có thể lấy package từ parent, sai namespace loader. | Dùng `getDefinedPackage` của loader hoặc `clazz.getPackage()`. |
| Nghĩ `Package.isSealed()` tự bảo đảm custom loader đọc từ đúng JAR | Raw-bytes loader có thể không thực hiện đầy đủ policy kiểm tra nguồn. | Thiết kế sealing checks cho mọi class nguồn hoặc dùng URLClassLoader. |
| Gắn `CodeSource` URL tùy ý rồi coi đó là bằng chứng xuất xứ | Metadata sai/không được xác minh. | Lấy từ nguồn bytes đã kiểm chứng và quản lý trust. |
| Trộn signed/unsigned classes trong cùng runtime package | Certificate-set mismatch có thể ném `SecurityException`. | Giữ provenance/certificates nhất quán; tách package/loader nếu cần. |
| Dùng ProtectionDomain như sandbox đầy đủ trên Java hiện đại | Không bảo vệ trước code không tin cậy theo cách kỳ vọng. | Dùng isolation boundary phù hợp, không dựa vào SecurityManager cũ. |
| Đưa bản copy API host vào loader plugin khác | Cùng binary name nhưng khác defining loader, dẫn tới ClassCastException. | Chia sẻ API từ parent; kiểm soát parent delegation. |
| Mở JAR rồi quên đóng | Rò file descriptors/locks. | Đóng `JarFile`/streams theo lifecycle bằng try-with-resources. |
| Lẫn package version với module version | Nhầm chính sách dependency/resolution. | Phân biệt JAR manifest, `Package` metadata và module descriptors. |
| Tự đọc bytes nhưng quên kiểm tra binary name | `NoClassDefFoundError: wrong name` hoặc class loading sai mục tiêu. | Truyền expected binary name, xác nhận class-file đúng. |
| Hai thread đồng thời `definePackage` cùng name | Race/exception và nguy cơ chọn nhầm metadata. | Đồng bộ theo package, kiểm chứng policy trước khi cho class được define. |

## 14. Câu hỏi tự kiểm tra

1. **Custom loader chỉ gọi `defineClass` có bắt buộc phải gọi `definePackage` trước không?**  
   Không. `defineClass` có thể tạo package mặc định. Chỉ gọi `definePackage` trước khi cần metadata/sealing cụ thể.
2. **Tại sao gọi `definePackage("sample.plugin", ...)` sau khi class đầu tiên đã nạp thường thất bại?**  
   Vì package trong loader đã được định nghĩa, không thể định nghĩa lại để thay metadata.
3. **`getDefinedPackage` khác `getPackage` thế nào?**  
   `getDefinedPackage` trả package được loader đó định nghĩa; `getPackage` deprecated có thể tìm parent và dẫn tới metadata không đúng runtime package.
4. **Hai loader có cùng `Package.getName()` có chung một runtime package?**  
   Không. Runtime package khác nhau khi defining loader khác nhau.
5. **`sealBase == null` có nghĩa gì?**  
   Package không sealed; có URL nghĩa package metadata sealed tại base đó.
6. **`CodeSource` có trực tiếp lưu `Implementation-Version` không?**  
   Không. Nó chủ yếu gắn location và certificates; version/title thuộc `Package`.
7. **Nếu `CodeSource.location` trả URL mà ứng dụng đặt, điều đó có chứng minh class file được ký và hợp lệ?**  
   Không. Tự khai báo metadata không xác minh bytes/signature.
8. **Vì sao certificate set của class đầu tiên trong package quan trọng?**  
   Các class sau trong cùng package/loader cần bộ certificates tương thích, nếu không có thể gây `SecurityException`.
9. **Sealed package có tự làm bytecode an toàn như sandbox?**  
   Không. Nó liên quan nguồn package; không thay process isolation hay runtime permission system.
10. **Tại sao loader song song cần khóa theo package?**  
    Hai class có binary name khác nhau nhưng cùng package có thể đồng thời cố `definePackage` với thông tin khác nhau.
11. **Trong JDK 9+, muốn package metadata từ custom loader nào phải hỏi gì?**  
    `thatLoader.getDefinedPackage(name)` hoặc `clazz.getPackage()` của class do loader đó định nghĩa.
12. **Nên tự triển khai manifest/sealing cho mọi ứng dụng chỉ đọc JAR không?**  
    Không. Nếu `URLClassLoader` đáp ứng yêu cầu, ưu tiên dùng API chuẩn và tránh nhân đôi quy tắc dễ sai.

## 15. Tài liệu chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `definePackage`, `getDefinedPackage`, `defineClass`, metadata package và certificate rules.
- [Java SE 21 — Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html): specification/implementation metadata, `isSealed`, `isCompatibleWith`.
- [Java SE 21 — SecureClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass(String,byte[],int,int,CodeSource)` và `getPermissions`.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): location URL, certificate/signers metadata.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): security domain fields/constructors.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): JAR search, class definition và lifecycle chuẩn.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest attributes, package sections, sealing và signed JARs.
- [JVM Specification §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime type identity, defining loader và runtime package.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): tình trạng của security manager trong JDK 24+.
