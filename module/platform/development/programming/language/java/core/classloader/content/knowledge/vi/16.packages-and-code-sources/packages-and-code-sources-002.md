# Package cùng tên trong nhiều ClassLoader: danh tính runtime và giới hạn truy cập

## 1. Vấn đề: cùng tên package chưa chắc cùng một package ở JVM

Trong mã nguồn Java, hai class đều khai báo:

```java
package demo.shared;
```

Ta thường gọi chúng là “cùng package”. Điều này đúng khi nói về **tên package ở mức cú pháp nguồn**. Tuy nhiên, ở runtime, Java còn xét **ClassLoader đã định nghĩa** từng class. Nếu `demo.shared.A` được loader L1 định nghĩa còn `demo.shared.B` được loader L2 định nghĩa, chúng **không nằm trong cùng một runtime package**, dù phần chuỗi `demo.shared` hoàn toàn giống nhau.

Đây là nền tảng để hiểu nhiều vấn đề thực tế:

- Vì sao mã **biên dịch được** với truy cập `package-private` nhưng khi chạy lại gặp `IllegalAccessError`?
- Vì sao hai thư viện ở hai plugin có cùng package vẫn không “chia sẻ nội bộ” như hai class do một loader định nghĩa?
- Vì sao hai class cùng **binary name** nhưng khác loader không ép kiểu qua nhau?
- Vì sao `Package.getName()` hoặc `Class.getPackageName()` không đủ để kết luận hai class có cùng quyền truy cập?
- Làm thế nào parent delegation, package sealing, signer và JPMS tác động đến việc phân chia package?

Quy tắc cốt lõi theo Java Virtual Machine Specification (JVMS):

> **Runtime package được xác định bởi cặp (tên package, defining class loader).**

Vì vậy, cùng tên package nhưng khác defining loader là **hai runtime packages khác nhau**. Ngược lại, hai class có tên package giống nhau và được **cùng một defining loader** định nghĩa thì thuộc cùng runtime package theo định nghĩa JVMS; vẫn phải xét thêm các ràng buộc module, bytecode verification và quyền truy cập liên quan.

## 2. Source package, binary name và runtime package

Xem hai class ví dụ (đây là **hai file riêng**, không phải một file chạy độc lập):

```java
// src/alpha/demo/shared/Alpha.java
package demo.shared;

public class Alpha {
    static String internal() {
        return "alpha";
    }
}
```

```java
// src/beta/demo/shared/Beta.java
package demo.shared;

public class Beta {
    public String message() {
        return "beta";
    }
}
```

Cả hai đều có phần khai báo `package demo.shared;`. Định danh tên nhị phân của chúng là:

- `demo.shared.Alpha`
- `demo.shared.Beta`

Nếu được định nghĩa bởi:

```text
L1 định nghĩa: demo.shared.Alpha
L2 định nghĩa: demo.shared.Beta
```

thì JVM xét:

```text
Runtime package của Alpha = ("demo.shared", L1)
Runtime package của Beta  = ("demo.shared", L2)
```

Nếu `L1 != L2` theo danh tính loader thì **hai cặp khác nhau**.

Lưu ý quan trọng: `Thread.currentThread().getContextClassLoader()`, loader ban đầu được gọi qua `loadClass` và **defining loader** không luôn trùng nhau. Khi tính runtime package, phải dùng **loader thực sự định nghĩa class**, lấy bằng `SomeClass.class.getClassLoader()`, không phải bất kỳ loader nào có mặt trong call stack.

### Ba cấp độ danh tính cần phân biệt

| Cấp độ | Dựa vào đâu? | Ví dụ |
| --- | --- | --- |
| Source package | Chuỗi trong khai báo `package` | `demo.shared` |
| Runtime package | **Package name + defining loader** | `("demo.shared", PluginLoaderA)` |
| Runtime class/interface | **Binary name + defining loader** | `("demo.shared.Service", PluginLoaderA)` |

Hai class có thể **khác runtime class** nhưng **cùng runtime package** nếu cùng loader và cùng package name. Hai class cũng có thể **cùng package name** nhưng **khác runtime package** nếu loader khác nhau.

## 3. Package-private và protected: hệ quả nhìn thấy ngay

Java có các mức truy cập: `public`, `protected`, package-private (không khai báo modifier), `private`.

Khi trình biên dịch thấy hai source class cùng khai báo `package demo.shared;`, nó có thể cho phép một class gọi member **package-private** của class kia, nếu các quy tắc compile-time khác được đáp ứng. Nhưng runtime phải bảo vệ quyền truy cập dựa trên **runtime package**.

Giả sử:

```java
// Được biên dịch cho package demo.shared
package demo.shared;

class Secret {
    static String reveal() {
        return "secret";
    }
}
```

```java
package demo.shared;

public class Caller {
    public static String read() {
        return Secret.reveal();
    }
}
```

Nếu `Caller` và `Secret` cùng được định nghĩa bởi một loader thích hợp, lời gọi tới method package-private có thể hợp lệ. Nhưng nếu:

- Loader **Parent** định nghĩa `demo.shared.Secret`;
- Loader **Child** định nghĩa `demo.shared.Caller`;
- Child delegate việc tìm `Secret` cho Parent;

thì tại runtime, caller và target **khác runtime package**, nên việc truy cập class `Secret` vốn package-private bị cấm. JVM có thể báo:

```text
java.lang.IllegalAccessError
```

Điểm mấu chốt: **đường dẫn trong source và việc compiler kiểm tra package name không quyết định cuối cùng quyền truy cập runtime** khi class loader split package thành những runtime packages khác nhau.

**Đối với `protected`:** ngoài những trường hợp truy cập hợp lệ qua quan hệ kế thừa và receiver theo Java/JVM, quyền truy cập “cùng package” cũng đòi hỏi cùng runtime package, không chỉ cùng chuỗi package. Không kết luận mọi lời gọi `protected` qua hai loader đều bị cấm: phải xét đầy đủ quan hệ subclass, điểm gọi và loại member.

**Đối với `public`:** accessibility của một public class/member có thể cho phép truy cập xuyên package và loader, nhưng vẫn còn module exports/readability, type identity, linkage, method signature và các quy tắc khác.

## 4. Parent delegation không “gộp” hai runtime packages

Một mô hình phổ biến:

```text
Host/Application ClassLoader
       ├── demo.shared.Secret
       └── demo.api.Plugin          (SPI dùng chung)
                 ▲
                 │ parent delegation
       Plugin ClassLoader
       ├── demo.shared.Caller
       └── plugin.impl.MyPlugin
```

Khi plugin loader nhận yêu cầu `loadClass("demo.shared.Secret")`, nó có thể hỏi parent; parent trả class đã định nghĩa. Nhưng khi plugin loader tự định nghĩa `demo.shared.Caller` bằng bytecode ở JAR riêng, hai class không trở thành cùng runtime package chỉ vì parent loader và child loader **có quan hệ cha–con**.

Không có quy tắc “hai loader liên quan họ hàng được xem như một package”. Điều kiện là **defining loader phải đúng cùng một đối tượng**.

Tương tự, nếu parent đã định nghĩa cả `Secret` và `Caller`, child chỉ delegate cả hai thì cả hai **vẫn cùng runtime package ở Parent**, vì child không tạo định nghĩa mới. Hãy kiểm tra `Class.getClassLoader()` của kết quả thực tế thay vì suy luận từ object được gọi.

| Tình huống | Defining loader của class A và B | Có cùng runtime package nếu package name giống? |
| --- | --- | --- |
| Hai class đều do parent định nghĩa, child chỉ delegate | Parent + Parent | Có |
| Một class ở parent, một class do child định nghĩa | Parent + Child | Không |
| Hai class đều do một plugin loader định nghĩa | Plugin + Plugin | Có |
| Hai plugin loader độc lập cùng định nghĩa package `com.foo` | Plugin A + Plugin B | Không |
| Hai loader cùng nạp lớp `java.lang.String` qua delegation | Bootstrap + Bootstrap | Có đối với lớp được bootstrap định nghĩa |
| Hai class trong những named modules | Phải xét defining loader và mô hình JPMS | Không suy chỉ từ tên package; named module có ràng buộc riêng |

## 5. Ví dụ Java 17 hoàn chỉnh: compile hợp lệ, runtime không được truy cập

Thí nghiệm bên dưới **tự sinh** bytecode ở hai thư mục riêng, tạo loader Parent và Child rồi thử truy cập một class package-private. Chương trình cũng dùng một loader thứ ba để chỉ ra **cùng binary name, cùng bytecode nhưng hai runtime classes độc lập**.

Thí nghiệm không cần Maven, Gradle, JAR ngoài hoặc truy cập mạng; chỉ cần **JDK 17+** có `javax.tools.JavaCompiler`.

### 5.1. Chương trình RuntimePackageDemo.java

Lưu chính xác mã sau vào file `RuntimePackageDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class RuntimePackageDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }
        Path root = Files.createTempDirectory("runtime-package-");
        try {
            Path parentSource = root.resolve("srcParent/demo/shared/Secret.java");
            Path callerSource = root.resolve("srcChild/demo/shared/Caller.java");
            Path tokenSource = root.resolve("srcChild/demo/shared/Token.java");
            Path parentClasses = root.resolve("parentClasses");
            Path childClasses = root.resolve("childClasses");
            Files.createDirectories(parentSource.getParent());
            Files.createDirectories(callerSource.getParent());
            Files.createDirectories(parentClasses);
            Files.createDirectories(childClasses);

            Files.writeString(parentSource, """
                    package demo.shared;
                    class Secret {
                        static String reveal() {
                            return "secret";
                        }
                    }
                    """);
            Files.writeString(callerSource, """
                    package demo.shared;
                    public class Caller {
                        public static String read() {
                            return Secret.reveal();
                        }
                    }
                    """);
            Files.writeString(tokenSource, """
                    package demo.shared;
                    public final class Token {}
                    """);

            int parentExit = compiler.run(null, null, null,
                    "--release", "17", "-d", parentClasses.toString(),
                    parentSource.toString());
            int childExit = compiler.run(null, null, null,
                    "--release", "17", "-classpath", parentClasses.toString(),
                    "-d", childClasses.toString(),
                    callerSource.toString(), tokenSource.toString());
            if (parentExit != 0 || childExit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL parentUrl = parentClasses.toUri().toURL();
            URL childUrl = childClasses.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader parent = new URLClassLoader(
                        new URL[]{parentUrl}, platform);
                 URLClassLoader child = new URLClassLoader(
                        new URL[]{childUrl}, parent);
                 URLClassLoader sibling = new URLClassLoader(
                        new URL[]{childUrl}, platform)) {

                Class<?> secret = parent.loadClass("demo.shared.Secret");
                Class<?> caller = child.loadClass("demo.shared.Caller");
                Class<?> token1 = child.loadClass("demo.shared.Token");
                Class<?> token2 = sibling.loadClass("demo.shared.Token");

                System.out.println("samePackageName="
                        + secret.getPackageName().equals(caller.getPackageName()));
                System.out.println("differentDefiningLoaders="
                        + (secret.getClassLoader() != caller.getClassLoader()));
                System.out.println("callerDefinedByChild="
                        + (caller.getClassLoader() == child));
                System.out.println("sameBinaryName="
                        + token1.getName().equals(token2.getName()));
                System.out.println("sameRuntimeClass=" + (token1 == token2));

                try {
                    caller.getMethod("read").invoke(null);
                    System.out.println("access=allowed");
                } catch (InvocationTargetException error) {
                    System.out.println("access="
                            + error.getCause().getClass().getSimpleName());
                }
                System.out.println("bootstrap="
                        + (child.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Lệnh biên dịch và thực thi:

```bash
javac RuntimePackageDemo.java
java RuntimePackageDemo
```

Stdout xác định với JDK 17+ có compiler đầy đủ, không có can thiệp bất thường từ môi trường:

```text
samePackageName=true
differentDefiningLoaders=true
callerDefinedByChild=true
sameBinaryName=true
sameRuntimeClass=false
access=IllegalAccessError
bootstrap=true
```

### 5.2. Từng dòng nói lên điều gì?

**`samePackageName=true`:** class `Secret` và `Caller` đều tự mô tả tên package là `demo.shared`. Đây là so sánh **chuỗi**, chưa phải so sánh runtime package.

**`differentDefiningLoaders=true`:** `Secret` do loader `parent` định nghĩa; `Caller` do loader `child` định nghĩa. Hai lớp khác runtime package mặc dù có cùng phần tên.

**`callerDefinedByChild=true`:** loader child hỏi parent theo chính sách parent-first; parent không có `Caller` nên child tìm `Caller.class` trong URL riêng và tự định nghĩa.

**`sameBinaryName=true` và `sameRuntimeClass=false`:** hai loader child/sibling đều tự định nghĩa `demo.shared.Token` từ cùng một thư mục chứa bytecode. Không phải cùng runtime class vì **defining loader khác nhau**.

**`access=IllegalAccessError`:** `Caller.read()` được compiler chấp nhận khi compile với `Secret.class` trong compile classpath. Nhưng ở runtime, method này cố truy cập `Secret` package-private do loader parent định nghĩa, trong khi `Caller` do child định nghĩa. JVM từ chối quyền truy cập. Reflection chỉ là cách chương trình chủ động gọi public method `Caller.read()` và quan sát exception gốc qua `InvocationTargetException.getCause()`; nguyên nhân vẫn là **quy tắc JVM về runtime package**, không phải vì dùng reflection khiến quyền truy cập thay đổi.

**`bootstrap=true`:** mặc dù yêu cầu qua child loader, `java.lang.String` do bootstrap loader định nghĩa, nên `getClassLoader() == null`.

### 5.3. Vì sao phải biên dịch Parent trước?

Khi biên dịch `Caller.java`, compiler được cấp:

```text
-classpath <parentClasses>
```

Nhờ đó `javac` nhìn thấy `Secret.class` trong cùng **source package name** và chấp nhận lời gọi package-private. Nhưng compiler chưa quyết định runtime sẽ đặt mỗi class ở defining loader nào. Tại runtime, mảng URL/quan hệ parent–child của thí nghiệm tạo ranh giới khác.

Đây là ví dụ điển hình của quy tắc: **source-level accessibility và runtime accessibility phải cùng nhất quán với cách phân bổ class cho loader**.

### 5.4. Nếu cả hai class do cùng loader định nghĩa thì sao?

Nếu đưa `Secret.class` và `Caller.class` vào **cùng một classpath root** của một loader và để chính loader đó định nghĩa cả hai, thì điều kiện “cùng runtime package” được đáp ứng. Khi không có các lỗi khác, lời gọi package-private có thể thành công.

Nếu parent đã cung cấp **cả** `Secret` và `Caller` thì child delegate cả hai và vẫn dùng chung runtime package của parent.

Không nên sửa lỗi bằng cách “thêm một bản Secret khác vào Child” mà không hiểu binary identity: parent-first có thể vẫn chọn bản ở Parent trước; child-first có thể làm hai bản `Secret` độc lập xuất hiện, gây lỗi khi truyền dữ liệu qua API chung.

## 6. Tên package giống nhau không có nghĩa có thể ép kiểu qua lại

Quy tắc **runtime class identity** còn mạnh hơn quy tắc runtime package: một runtime class được nhận diện bởi cặp **(binary name, defining loader)**.

```text
("demo.shared.Token", ChildLoader)   !=
("demo.shared.Token", SiblingLoader)
```

Ngay cả khi hai class được tạo từ **cùng mảng byte**:

- `token1.getName().equals(token2.getName())` là `true`;
- `token1 == token2` là `false`;
- Hai instance từ hai runtime classes này không thể coi là cùng class bằng phép cast tới class kia;
- `Class.isInstance` hoặc `isAssignableFrom` trên từng định nghĩa giúp kiểm tra quan hệ kiểu runtime thật;
- Những interface cha/API dùng chung có thể tạo cầu nối hợp lệ nếu **cả hai** implementation đều thực thi **chính cùng một định nghĩa interface của host**.

Một thông báo lỗi dạng “`demo.shared.Token cannot be cast to demo.shared.Token`” có thể là hệ quả của hai loader độc lập định nghĩa cùng binary name. Nhìn tên chuỗi trong stack trace không đủ; phải kiểm tra class loader.

### Runtime package khác với “vùng nhìn thấy” của class loader

- Một loader có thể nạp được class của parent nhờ delegation nhưng **không trở thành defining loader** của class đó.
- Một class có thể nhìn thấy API công khai từ parent dù khác runtime package.
- Quyền gọi package-private **không** được cấp chỉ vì child “nhìn thấy” class của parent.
- Hai loader cùng tải một file JAR nhưng định nghĩa class riêng thì vẫn có các runtime types và runtime packages riêng.

## 7. Kiểm tra package bằng Class API: dùng đúng thông tin

Một số API dễ tạo nhầm lẫn:

| API | Nó nói gì? | Nó không bảo đảm điều gì? |
| --- | --- | --- |
| `clazz.getPackageName()` | Tên package dạng chuỗi của class | Không xác nhận hai class ở cùng runtime package |
| `clazz.getPackage()` | Đối tượng `Package` mô tả package liên quan đến class | Không thay thế quy tắc runtime package trong JVMS |
| `clazz.getClassLoader()` | **Defining loader** của class; `null` với bootstrap | Không cho biết mọi initiating loader từng yêu cầu class |
| `loader.getDefinedPackage(name)` | `Package` được **loader đó** định nghĩa cho tên package khi có | Không định nghĩa lại lớp, không nói toàn bộ package của mọi loader |
| `loader.getDefinedPackages()` | Các `Package` do loader đó định nghĩa | Không tự quét tất cả parent/sibling loader |
| `clazz.getModule()` | Module runtime của class | Không thay thế defining-loader identity hay mọi access check |
| `clazz.getProtectionDomain()` | Protection domain nếu có thể truy vấn | Không quyết định hai class có cùng runtime package |
| `clazz.getSigners()` | Thông tin signer của class khi có | Không cho phép “chia sẻ” package-private across loaders |

Không viết:

```java
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName());
```

rồi xem kết quả `true` là bằng chứng đủ. Đây là **đoạn sai về mặt lập luận** nếu `a` và `b` có defining loader khác nhau.

Với hai class không thuộc các trường hợp đặc biệt như array/primitive, quy tắc nhận diện runtime package theo JVMS là xét **package name** và **defining loader**. Ví dụ snippet khi đã có hai đối tượng `Class<?> a,b`:

```java
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName())
        && a.getClassLoader() == b.getClassLoader();
```

Đây là snippet, không phải chương trình độc lập. Nếu dùng để suy ra **quyền truy cập một member cụ thể**, cần tiếp tục xét modifier, access context, subclass rules và module access, không chỉ hai điều kiện này.

Đặc biệt, `getDefinedPackage` của loader con **không liệt kê tất cả** package của parent. Việc không thấy một package trong danh sách “defined here” không có nghĩa loader con không thể nạp class tương ứng nhờ delegation.

## 8. Package sealing và các JAR khác nhau

Một số JAR khai báo metadata package trong `META-INF/MANIFEST.MF`. Thuộc tính **Sealed** cho phép quy định package được seal theo một code source URL. Khi loader cố định nghĩa các class vào cùng package nhưng từ những nguồn không phù hợp với sealing policy, runtime/loader có thể từ chối.

Ví dụ manifest minh họa:

```text
Manifest-Version: 1.0
Name: demo/shared/
Sealed: true
```

Trong phạm vi loader xử lý manifest sealing, điều này có nghĩa các class của package được seal phải tuân theo nguồn code phù hợp. Nếu loader tìm `demo.shared.A` từ JAR1, rồi tìm `demo.shared.B` từ JAR2 khác, một **sealing violation** có thể xuất hiện.

Nhưng cần phân biệt:

1. **Runtime package identity:** do package name và defining loader quyết định.
2. **Sealing policy:** kiểm soát tập nguồn URL/code source được phép đóng góp các class vào một package trong cùng loader; phụ thuộc implementation của loader/JAR manifest.
3. **Module encapsulation:** kiểm soát đọc/export/open package trong JPMS; không phải một dạng của sealing.

Hai loader độc lập có thể **định nghĩa package cùng tên** mà không tự hợp thành một sealed package chung. Sealing không làm hai defining loaders tự nhận cùng quyền package-private.

### Dùng definePackage với custom ClassLoader

`ClassLoader.definePackage(...)` cho phép định nghĩa một đối tượng `Package` chứa metadata specification/implementation và URL sealing tùy API overload. Nó **không** tạo class mới, không cấp quyền package-private giữa loader, và không tự merge package của loader khác.

Nếu custom loader tải classes từ nhiều nguồn, cần thiết kế nhất quán package metadata, signer/certificate và protection domain. Trong một defining loader, các class cùng package phải tuân thủ ràng buộc signer/certificate khi áp dụng; vi phạm có thể gây `SecurityException` hoặc lỗi tương ứng.

**Không coi** việc gọi `definePackage("demo.shared", ...)` trên L2 là cách “nhập” runtime package của L1 vào L2. Hai loader vẫn độc lập.

## 9. Java Platform Module System (JPMS): split package và module

Từ Java 9, một lớp còn thuộc về một runtime module. Khi dùng **named modules**, JVM/module layer và loader còn áp dụng:

- **Readability:** module gọi có đọc module chứa kiểu đích hay không.
- **Exports:** package công khai có được module chứa nó export tới module dùng hay không.
- **Opens:** quyền reflective access tới package theo điều kiện module.
- **Package/module mapping:** hạn chế các package trùng nhau giữa named modules, đặc biệt nếu cùng một class loader cần định nghĩa chúng.
- **Unnamed module:** class được định nghĩa trên classpath thông thường thuộc unnamed module tương ứng với loader; nó không tương đương một named module được khai báo trong `module-info.java`.

Một class có access modifier `public` vẫn có thể không truy cập được từ module khác nếu package của named module chưa export phù hợp. Ngược lại, hai class có cùng chuỗi package name nhưng do hai loader khác nhau định nghĩa vẫn **không** được xem như một runtime package chỉ vì cấu hình module của chúng có quan hệ.

### Không lấy module path làm “cách sửa” ranh giới ClassLoader

Nếu dự án plugin bị `IllegalAccessError` do package-private giữa parent và child, di chuyển JAR lên module path không tự làm hai class thành cùng defining loader. Thậm chí named modules có thể tăng thêm các kiểm tra encapsulation và phát hiện split package.

Khi quyết định có nên dùng JPMS, cần xác định rõ ai sở hữu package, module nào định nghĩa API/SPI, module nào cần `requires` và package nào cần `exports`/`opens`.

### Runtime package và tổ chức module có cùng mục đích không?

Chúng khác vai trò:

| Cơ chế | Phạm vi |
| --- | --- |
| Source package | Sắp xếp source/binary names |
| Runtime package | Quyền truy cập/package identity dựa trên name + defining loader |
| Named module | Ranh giới module resolution, readability và encapsulation |
| ClassLoader | Nơi class được tìm/nạp/định nghĩa và danh tính kiểu runtime |

Thiết kế thành công thường **thống nhất** bốn cấp độ, thay vì coi một cấp độ tự động thay thế cấp độ còn lại.

## 10. Plugin, container và nhiều phiên bản thư viện

Một plugin architecture thường có:

```text
Host ClassLoader
   ├── com.company.spi.Plugin
   ├── com.company.spi.Request
   └── com.company.spi.Response
           ^
           |
     PluginLoader A
       ├── plugin.alpha.Handler
       └── thirdparty.lib.Utility (bản A)

     PluginLoader B
       ├── plugin.beta.Handler
       └── thirdparty.lib.Utility (bản B)
```

Cách tổ chức hợp lý:

1. **Đặt API/SPI và DTO dùng chung ở host/parent**, rồi plugin loader delegate để nhận chính cùng runtime types.
2. **Cô lập implementation và dependency không cần chia sẻ** theo plugin loader, nếu kiến trúc yêu cầu nhiều phiên bản thư viện cùng tồn tại.
3. **Không phụ thuộc quyền package-private xuyên loader**, kể cả package string giống nhau.
4. **Không truyền class nội bộ qua boundary** nếu host không có khả năng dùng đúng class identity; sử dụng public interface/SPI, adapter hoặc serialization contract.
5. **Tránh split package giữa JAR host và plugin** nếu các class bên trong gọi package-private trực tiếp với nhau.
6. **Kiểm soát delegation cho package API quan trọng**, tránh custom child-first tạo một bản `com.company.spi.Plugin` riêng rồi gây `ClassCastException` khi host cast.
7. **Phân biệt ClassLoader và classpath:** cùng đường dẫn JAR không có nghĩa cùng runtime type nếu được hai loader riêng biệt định nghĩa.

Khi cần “chia sẻ code nội bộ” giữa hai plugin, các lựa chọn bền vững hơn là đưa một API public thích hợp vào loader chung, trích thư viện chung có ranh giới công khai, hoặc để cùng một loader thật sự định nghĩa những class cần truy cập package-private (sau khi đánh giá ràng buộc namespace và bảo trì).

### Cùng package nhưng hai dependency versions

Ví dụ có hai bản `com.vendor.json.Parser` tại Plugin A và Plugin B. Nếu mỗi plugin tự định nghĩa phiên bản riêng thì chúng không phải cùng runtime class. Nếu parent đã nạp một bản Parser và plugin vẫn parent-first, cả hai có thể vô tình dùng **cùng** Parser của parent thay vì bản riêng.

Cần kiểm tra:

```java
System.out.println(parserType.getName());
System.out.println(parserType.getClassLoader());
```

Đây là snippet, giả định `parserType` là `Class<?>` đã được ứng dụng lấy. Nếu cần nguồn code, có thể kiểm tra `ProtectionDomain/CodeSource` khi giá trị tồn tại. Không chỉ so sánh version ghi trên tên JAR.

## 11. Những lỗi dễ nhầm khi hai loader có package trùng tên

| Triệu chứng | Lý do cần xét | Kiểm tra đầu tiên |
| --- | --- | --- |
| `IllegalAccessError` dù code biên dịch được | Package-private/protected qua hai runtime packages khác nhau | Loader thực sự định nghĩa caller và target |
| `ClassCastException` với hai tên lớp giống hệt | Cùng binary name nhưng defining loaders khác nhau | `Class<?> ==`, loader identity |
| `LinkageError` về loading constraints | JVM cần một tên kiểu nhất quán xuyên loader ở điểm liên kết | Class trong method descriptors, loader graph |
| `SecurityException` về signers/certificates | Classes trong cùng package và loader có signer policy không nhất quán | Source JAR, signatures và package metadata |
| `SecurityException: sealing violation` | Sealed package bị trộn các nguồn URL/JAR | Manifest sealing và code source |
| `ClassNotFoundException` khi load ở child | Child/parent không nhìn thấy định nghĩa cần thiết | Binary name, parent chain, nguồn bytecode |
| `NoClassDefFoundError` khi chạy | Phụ thuộc thiếu, wrong name hoặc trạng thái initialization lỗi | Thông báo nguyên nhân, classpath/dependency graph |
| `NoSuchMethodError` | Runtime nạp API phiên bản khác compile-time | Signatures và định nghĩa class đã được chọn |
| `InaccessibleObjectException` khi reflection | Quy tắc `opens` của JPMS hoặc access context | Module chứa class, caller module |
| `IllegalAccessException` từ reflection | Reflection API từ chối truy cập theo access checks | Member modifier, caller/module, access mode |

**Đặc biệt:** `IllegalAccessError` là một dạng `IncompatibleClassChangeError` (thuộc `LinkageError`), biểu thị access runtime không hợp lệ. Khác với `IllegalAccessException` là checked exception mà reflection có thể ném khi API phản chiếu từ chối truy cập. Thí nghiệm phần 5 bắt `InvocationTargetException` vì public method được invoke **đã bắt đầu chạy**, rồi JVM phát hiện vấn đề tại lời gọi tới class khác.

Một chương trình có thể gặp lỗi ngay trong quá trình liên kết tùy class verification/resolution; đừng khẳng định mọi lỗi package-private sẽ xuất hiện chính xác ở một dòng method call giống nhau trên mọi JVM. Mục tiêu là hiểu ranh giới loader, không dựa vào vị trí stack trace tuyệt đối.

## 12. Cách debug đúng: ghi name, defining loader, module và code source

Khi gặp sự cố package trùng tên, nên so sánh **hai đối tượng Class cụ thể**: caller và target.

Đặt hàm hỗ trợ sau trong một class Java:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("package=" + type.getPackageName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
    java.security.ProtectionDomain domain = type.getProtectionDomain();
    java.security.CodeSource source =
            domain == null ? null : domain.getCodeSource();
    System.out.println("codeSource="
            + (source == null ? "<unknown>" : source.getLocation()));
}
```

Đây là **phương thức minh họa**, không phải chương trình có `main` độc lập. Trong những môi trường bị giới hạn, một số thông tin security/protection có thể không sẵn có; `CodeSource == null` không chứng minh class đã bị nạp sai.

Quy trình:

1. Xác định **binary name** của caller và target liên quan trong lỗi.
2. Lấy **Class<?> của từng bên** nếu có thể; không dùng `Class.forName` với loader bất kỳ để rồi tưởng đó là class đã gây lỗi.
3. In `getPackageName()` và **`getClassLoader()` của cả hai**.
4. Nếu binary names hoặc package names giống nhưng loaders khác nhau, xét split runtime package/type identity.
5. Nếu cùng loader nhưng vẫn `IllegalAccessError`, kiểm tra modifier, static/instance, superclass, interface, module và binary incompatibility.
6. Nếu JAR khác nhau, kiểm tra manifest sealing, certificates/signers và hai bản class trùng binary name.
7. Nếu hệ dùng named modules, kiểm tra exports/opens/readability và nguồn module của class.
8. Nếu liên quan plugin, xác định parent-first/child-first policy và đường mà class đã thực sự đi qua.

### Công cụ JDK hỗ trợ

```bash
jar tf plugins/plugin-a.jar
jar tf plugins/plugin-b.jar
javap -classpath plugins/plugin-a.jar -p demo.shared.Secret
java -Xlog:class+load=info -cp "app/classes:lib/*" com.example.Main
```

Đây là lệnh **minh họa**, tên file/class cần thay bằng giá trị thật. Dòng `-cp` dùng dấu `:` của Linux/macOS; Windows dùng `;`. `jar tf` xác nhận entry có trong JAR; `javap -p` cho biết access modifiers/method signatures; unified class-load log giúp thấy bytecode đến từ đâu.

Với class do custom loader định nghĩa trực tiếp từ memory/database, nguồn `CodeSource` có thể không phải URL file/JAR; cần log loader identity và nguồn bytecode đáng tin cậy tại nơi `defineClass` xảy ra.

## 13. Những nhầm lẫn thường gặp

**“Hai file Java có `package demo.shared;` nên luôn truy cập package-private được.”** Sai. Runtime package phụ thuộc defining loader.

**“Parent và child là họ hàng nên được coi cùng package.”** Sai. Khác defining loader là khác runtime package, dù có delegation giữa chúng.

**“Package.getName() giống nhau thì quyền truy cập giống nhau.”** Sai. Nó chưa xét loader và các access rules khác.

**“Khi child gọi `parent.loadClass` thì lớp trả về thuộc package của child.”** Sai. Defining loader vẫn là parent.

**“Hai lớp cùng binary name ở hai loader là một type vì bytecode giống nhau.”** Sai. Runtime class identity còn chứa defining loader.

**“Chỉ cần dùng `public` cho class là mọi thành viên package-private đều được gọi.”** Sai. Class public và member access là hai kiểm tra khác nhau; named modules còn có ranh giới encapsulation.

**“Sealed package làm hai loader cùng tên chia sẻ quyền nội bộ.”** Sai. Sealing là ràng buộc source/package, không nhập defining loaders.

**“Gọi `definePackage` trên hai loader có cùng tên package sẽ merge class.”** Sai. API quản lý metadata package của loader tương ứng, không thay class identity.

**“JPMS có thể bỏ qua quy tắc runtime package.”** Sai. Module rules bổ sung quyền truy cập, không tự cấp package-private qua defining loaders.

**“Có `ClassCastException` thì chắc do package-private.”** Không đủ dữ kiện. Type identity lỗi là vấn đề class identity, không phải access modifier package-private trực tiếp.

## 14. Bài tập tự kiểm tra

**Câu 1.** `demo.shared.A` do L1 định nghĩa và `demo.shared.B` do L2 định nghĩa. Hai class có cùng runtime package không?

**Trả lời:** Không nếu L1 và L2 là hai loader object khác nhau, dù chuỗi package name giống.

**Câu 2.** Child gọi `loadClass("demo.shared.A")` và nhận class do Parent đã định nghĩa. Defining loader là ai?

**Trả lời:** Parent. Việc Child khởi xướng yêu cầu không đổi runtime package của class.

**Câu 3.** Tại sao compiler cho `Caller` gọi package-private `Secret.reveal()`, nhưng runtime báo `IllegalAccessError`?

**Trả lời:** Compiler thấy hai source types cùng tên package trong compile graph; runtime lại có `Caller` do Child định nghĩa, `Secret` do Parent định nghĩa. Chúng khác runtime package và JVM từ chối quyền package-private.

**Câu 4.** Hai `URLClassLoader` độc lập đọc cùng `demo.shared.Token.class`. So sánh `Class<?>` có bằng nhau không?

**Trả lời:** Không nếu mỗi loader tự định nghĩa class. Cùng binary name/bytecode nhưng khác defining loader nghĩa là hai runtime classes.

**Câu 5.** Khi module A `exports demo.shared`, một class cùng package name ở loader khác có đương nhiên gọi được `private` hoặc package-private member không?

**Trả lời:** Không. `exports` liên quan khả năng truy cập public types/members theo module rules; không cấp quyền private/package-private xuyên loader.

**Câu 6.** Tại sao một package sealed có thể gây lỗi khi JAR1 và JAR2 cung cấp hai class khác nhau trong cùng package?

**Trả lời:** Sealing đặt ràng buộc nguồn của các class trong package do loader quản lý. Nếu loader trộn các nguồn không thỏa seal base URL, có thể xảy ra sealing violation.

**Câu 7.** Cần log thông tin tối thiểu nào để biết hai class có cùng runtime package hay không?

**Trả lời:** Package name và defining loader của **từng** đối tượng `Class<?>` thực tế. Để chẩn đoán đầy đủ có thể thêm module, code source, method modifiers và dependency version.

**Câu 8.** Hệ plugin cần trao đổi thông điệp giữa A và B, nhưng mỗi plugin có loader riêng. Nên chọn thiết kế nào?

**Trả lời:** Đặt public SPI/DTO thích hợp tại loader host chia sẻ, để plugin delegate tới đó; tránh dựa vào truy cập package-private giữa hai loader.

## 15. Checklist triển khai an toàn về package identity

- [ ] Xác định defining loader thực tế của các class dùng trong cùng package name.
- [ ] Không trộn class cần truy cập package-private qua các loader khác nhau.
- [ ] API/SPI chung phải có **một định nghĩa runtime chia sẻ**, thường từ host/parent.
- [ ] Khi cô lập dependency, xem class cùng binary name có thể xuất hiện ở nhiều defining loaders.
- [ ] Ghi rõ namespace package nào thuộc host và package nào thuộc từng plugin.
- [ ] Kiểm tra parent-first/child-first policy trước khi kết luận JAR nào thắng.
- [ ] Cân nhắc sealing, signers, protection domains nếu nạp nhiều JAR vào một loader.
- [ ] Với named modules, kiểm tra module graph và `exports`/`opens`.
- [ ] Kiểm tra binary compatibility và quyền truy cập khi build bằng một bố cục loader nhưng chạy bằng bố cục khác.
- [ ] Test thực tế cùng artifact, loader tree và runtime JDK của môi trường triển khai.
- [ ] Khi có lỗi, in package name, loader, module và code source của **cả caller và target**.
- [ ] Không dùng `Class.getPackageName()` hoặc JAR path một mình để suy ra runtime package identity.

## 16. Kết luận và nguồn chuẩn

**Cùng tên package ở source code không bảo đảm cùng runtime package.** JVM xác định runtime package bằng **tên package cùng defining ClassLoader**. Quy tắc này giải thích vì sao package-private có thể bị chặn dù compiler đã chấp nhận, tại sao hai runtime classes cùng tên không cast được khi được định nghĩa bởi hai loader khác nhau, và vì sao plugin architecture cần một ranh giới API/SPI chung rõ ràng.

Khi điều tra lỗi, đừng hỏi riêng “hai class khai báo package gì?”; hãy hỏi **“mỗi class do loader nào thực sự định nghĩa?”**, rồi kiểm tra tiếp quyền member, quan hệ kiểu, module visibility, sealing và dependency compatibility.

Tài liệu tham khảo chính thức:

- JVMS 17 §5.3, *Creation of Classes and Interfaces* (defining loader và runtime class identity): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVMS 17 §5.4.4, *Access Control*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- JLS 17 §6.6, *Access Control*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6
- Java SE 17 `Class` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `ClassLoader` API, `definePackage` và `getDefinedPackage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Package` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
