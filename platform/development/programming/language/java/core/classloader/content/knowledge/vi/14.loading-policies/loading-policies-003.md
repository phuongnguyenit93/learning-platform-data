# Thiết kế chính sách chọn lọc theo package trong Java ClassLoader

## 1. Vấn đề cần giải quyết

Trong hệ thống host–plugin, không phải mọi lớp đều nên đi theo cùng một thứ tự tìm kiếm. **Parent-first** thích hợp với các kiểu JDK và hợp đồng API dùng chung. Ngược lại, một plugin đôi khi cần phiên bản class hoặc thư viện riêng để không bị bản trên application classpath của host lấn át.

**Chính sách chọn lọc theo package** (*selective package-based class loading*) nghĩa là phân loại **binary name** của lớp trước khi quyết định thứ tự lookup:

- `java.lang.String` và các class nền tảng: dùng cơ chế parent/Bootstrap/Platform phù hợp.
- `api.Service`: dùng API chung do parent định nghĩa để host và plugin thấy cùng một kiểu.
- `plugin.impl.Version` và `plugin.impl.ServiceImpl`: ưu tiên bytecode trong nguồn child.
- Những package không được chọn: giữ **parent-first delegation** bình thường.

Ví dụ:

~~~text
Application ClassLoader (parent)
├── api.Service                  [API chung]
├── plugin.impl.Version          [phiên bản host]
└── PolicyDemo
          ^
          | delegate với tên chia sẻ
          |
Selective URLClassLoader (child)
├── plugin.impl.Version          [phiên bản plugin]
└── plugin.impl.ServiceImpl      [implementation plugin]
~~~

Mục tiêu là **cô lập implementation**, không phá sự thống nhất của API contract. Một lớp có thể có cùng binary name nhưng do hai loader khác nhau định nghĩa, khiến nó là **hai kiểu runtime khác nhau**.

## 2. Phân biệt parent-first, child-first và child-only

**Parent-first mặc định** của `ClassLoader.loadClass(String, boolean)` hoạt động theo trình tự:

1. `findLoadedClass(name)`: đã được ghi nhận nạp tên này chưa?
2. Hỏi parent loader (hoặc cơ chế bootstrap khi parent là `null`).
3. Khi parent không tìm được, gọi `findClass(name)` của loader hiện tại.
4. Nếu `resolve=true`, gọi `resolveClass(result)` để link nếu cần.
5. Trả `Class<?>`, hoặc ném `ClassNotFoundException`.

Khi chỉ muốn đọc bytes từ nguồn mới mà vẫn parent-first, nên override **`findClass`**, không cần viết lại `loadClass`.

**Child-first với parent fallback** đảo thứ tự bước 2 và 3 **chỉ cho tên trong tập package được chọn**. Khi child không có lớp ấy, loader vẫn hỏi parent. Điều này linh hoạt, nhưng có thể vô tình nhận class phiên bản cũ từ host.

**Child-only/fail closed** với một namespace riêng sẽ ném `ClassNotFoundException` khi child không có tên đó, thay vì hỏi parent. Cách này cô lập chặt hơn nhưng yêu cầu plugin đóng gói đầy đủ mọi class thuộc namespace mà bạn sở hữu.

| Chính sách | Lần tìm đầu tiên | Khi không thấy | Phù hợp |
| --- | --- | --- | --- |
| Parent-first | Parent | Child `findClass` | JDK, API dùng chung, class mặc định |
| Child-first + fallback | Child `findClass` | Parent-first | Plugin implementation cần version riêng nhưng vẫn cho phép fallback |
| Child-only | Child `findClass` | Báo không tìm thấy | Namespace buộc phải riêng, không được lấy bản host |

Không có chính sách đúng cho mọi dự án. Việc chọn policy là quyết định ở **ranh giới hợp đồng và dependency**, không phải chỉ vì tên package trông quen thuộc.

## 3. Chọn package bằng prefix chính xác

Một bộ lọc đơn giản:

~~~java
private static boolean childFirst(String binaryName) {
    return binaryName.startsWith("plugin.impl.");
}
~~~

Hãy giữ **dấu chấm cuối** để phân biệt ranh giới package:

| Binary name | Khớp `plugin.impl.`? |
| --- | --- |
| `plugin.impl.Version` | Có |
| `plugin.impl.ServiceImpl` | Có |
| `plugin.impl.internal.Helper` | Có |
| `plugin.impl.Version$Nested` | Có |
| `plugin.implx.Version` | Không |
| `plugin.implementation.Service` | Không |
| `api.Service` | Không |

Nếu dùng `startsWith("plugin.impl")` (thiếu dấu chấm cuối), bạn có thể vô tình bắt cả `plugin.implx`. Nếu dùng `startsWith("plugin.")` quá rộng, các class contract như `plugin.api.Contract` cũng có thể bị chọn vào child-first và xuất hiện bản sao API.

Với nhiều prefix, nên biểu diễn chính sách thành **danh sách package được duyệt**, có test cho tên gần giống và tên nested. Phân biệt package được host sở hữu, package được plugin sở hữu, package chia sẻ và package nền tảng. Không coi toàn bộ `javax.*` hoặc `jakarta.*` là JDK class trong mọi môi trường: một số API có thể đến từ dependency ngoài JDK.

**Ưu tiên chắc chắn:** các kiểu dùng trong chữ ký phương thức hoặc interface giữa host và plugin cần được định nghĩa nhất quán bởi loader chung. Đừng cho plugin tùy tiện định nghĩa lại những API đó.

## 4. Khi nào cần override loadClass?

Chỉ override `findClass` thì vẫn **parent-first**. Để ưu tiên child cho một số package, ta phải kiểm soát thứ tự lookup, nên có thể override:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> found = findLoadedClass(name);

        if (found == null && childFirst(name)) {
            try {
                found = findClass(name);
            } catch (ClassNotFoundException missingLocally) {
                // Cho phép fallback sang thuật toán bình thường.
            }
        }

        if (found == null) {
            found = super.loadClass(name, false);
        }
        if (resolve) {
            resolveClass(found);
        }
        return found;
    }
}
~~~

Đây là **một phương thức bên trong subclass**, chưa phải chương trình độc lập. Phần 5 có code chạy hoàn chỉnh dùng `URLClassLoader`.

Giải thích những thành phần không được bỏ:

1. **`getClassLoadingLock(name)`:** giữ khóa thích hợp trong toàn bộ quá trình class loading. Tránh hai luồng cùng cố define một binary name.
2. **`findLoadedClass(name)`:** kiểm tra lớp đã được nạp/ghi nhận bởi loader, tránh define lại cùng tên.
3. **`childFirst(name)`:** áp dụng policy chỉ cho namespace chọn lọc.
4. **`findClass(name)`:** tìm bytecode ở nguồn child. Với subclass của `URLClassLoader`, phương thức này đã biết đọc những URL directory/JAR được cung cấp.
5. **Bắt riêng `ClassNotFoundException`:** cho phép fallback khi file class không có trong child. Không nuốt `ClassFormatError`, `LinkageError`, `SecurityException` như thể chúng chỉ là thiếu file.
6. **`super.loadClass(name, false)`:** thực hiện parent-first mặc định ở những trường hợp chưa có class. Gọi `false` vì chính override sẽ xử lý `resolveClass` ở cuối.
7. **`resolveClass(found)` nếu cờ `resolve=true`:** bảo toàn hợp đồng của overload hai tham số. Cờ này **không yêu cầu initialization**.

Đoạn code giữ khóa rồi gọi lại `super.loadClass`: khóa monitor Java là *reentrant* nên cùng luồng có thể vào lại khóa. Tuy nhiên, với các loader có đồ thị ủy quyền phức tạp (sibling hoặc circular delegation), vẫn phải kiểm tra deadlock và quy tắc *parallel capable*.

**Quan trọng:** code trên là **child-first với fallback**, không phải child-only. Nếu namespace `plugin.impl.*` phải tuyệt đối không dùng class host, đừng bỏ qua failure từ `findClass`: hãy chuyển tiếp `ClassNotFoundException` cho tên thuộc namespace ấy.

## 5. Ví dụ đầy đủ Java 17+: cùng binary name, hai phiên bản

Mục tiêu thử nghiệm: parent có `plugin.impl.Version` trả `"parent"`, child có `plugin.impl.Version` trả `"child"`. Plugin class `ServiceImpl` triển khai interface chung `api.Service` do parent định nghĩa.

### Cấu trúc nguồn

~~~text
example/
└── src/
    ├── parent/
    │   ├── api/
    │   │   └── Service.java
    │   ├── plugin/
    │   │   └── impl/
    │   │       └── Version.java
    │   └── PolicyDemo.java
    └── child/
        └── plugin/
            └── impl/
                ├── Version.java
                └── ServiceImpl.java
~~~

Hai tệp `Version.java` cùng tên và package nhưng thuộc hai vùng biên dịch/output khác nhau. **Không** biên dịch chúng vào cùng một thư mục.

### File `src/parent/api/Service.java`

~~~java
package api;

public interface Service {
    String execute();
}
~~~

### File `src/parent/plugin/impl/Version.java`

~~~java
package plugin.impl;

public class Version {
    public static String who() {
        return "parent";
    }
}
~~~

### File `src/child/plugin/impl/Version.java`

~~~java
package plugin.impl;

public class Version {
    public static String who() {
        return "child";
    }
}
~~~

### File `src/child/plugin/impl/ServiceImpl.java`

~~~java
package plugin.impl;

import api.Service;

public class ServiceImpl implements Service {
    @Override
    public String execute() {
        return Version.who();
    }
}
~~~

### File `src/parent/PolicyDemo.java`

~~~java
import api.Service;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import plugin.impl.Version;

public class PolicyDemo {
    static final class PackagePolicyLoader extends URLClassLoader {
        PackagePolicyLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        private static boolean childFirst(String name) {
            return name.startsWith("plugin.impl.");
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null && childFirst(name)) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException missingLocally) {
                        // Explicit fallback to normal parent-first lookup.
                    }
                }

                if (found == null) {
                    found = super.loadClass(name, false);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL plugin = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (PackagePolicyLoader loader = new PackagePolicyLoader(
                new URL[]{plugin}, PolicyDemo.class.getClassLoader())) {
            System.out.println("parent version: " + Version.who());

            Class<?> childVersion = loader.loadClass("plugin.impl.Version");
            System.out.println("child version: "
                    + childVersion.getMethod("who").invoke(null));
            System.out.println("same runtime class: "
                    + (Version.class == childVersion));
            System.out.println("child owns version: "
                    + (childVersion.getClassLoader() == loader));

            Class<?> implementation =
                    loader.loadClass("plugin.impl.ServiceImpl");
            Service service = (Service) implementation
                    .getDeclaredConstructor().newInstance();

            System.out.println("service: " + service.execute());
            System.out.println("api shared: "
                    + (loader.loadClass("api.Service") == Service.class));
            System.out.println("jdk shared: "
                    + (loader.loadClass("java.lang.String") == String.class));
        }
    }
}
~~~

Mã host dùng `URLClassLoader` để không phải tự cài đặt đọc bytecode/đọc JAR. Override `loadClass` chỉ thay chính sách chọn package và giữ phần còn lại của API chuẩn.

### Biên dịch và chạy Linux/macOS

Đứng trong `example`:

~~~bash
mkdir -p out/parent out/child

javac --release 17 -d out/parent \
  src/parent/api/Service.java \
  src/parent/plugin/impl/Version.java \
  src/parent/PolicyDemo.java

javac --release 17 -cp out/parent -d out/child \
  src/child/plugin/impl/Version.java \
  src/child/plugin/impl/ServiceImpl.java

java -cp out/parent PolicyDemo out/child
~~~

**Chú ý:** khi chạy, chỉ đưa `out/parent` vào application `-cp`. `out/child` được truyền như tham số của chương trình, để `PolicyDemo` tạo URLClassLoader. Nếu thêm thư mục child vào classpath host, bản class host/child có thể xung đột theo thứ tự classpath và phá điều kiện thí nghiệm.

### Biên dịch và chạy Windows PowerShell

Trong thư mục `example`:

~~~powershell
New-Item -ItemType Directory -Force out\parent, out\child | Out-Null
javac --release 17 -d out\parent src\parent\api\Service.java src\parent\plugin\impl\Version.java src\parent\PolicyDemo.java
javac --release 17 -cp out\parent -d out\child src\child\plugin\impl\Version.java src\child\plugin\impl\ServiceImpl.java
java -cp out\parent PolicyDemo out\child
~~~

### Stdout đã kiểm chứng trên JDK

~~~text
parent version: parent
child version: child
same runtime class: false
child owns version: true
service: child
api shared: true
jdk shared: true
~~~

Giải thích theo từng dòng:

1. **parent version: parent:** `PolicyDemo` do application loader định nghĩa, nên truy cập `Version.who()` trực tiếp trong host lấy bản Version của parent.
2. **child version: child:** child loader ưu tiên `findClass` với package `plugin.impl.*` nên nhận class Version từ `out/child`.
3. **same runtime class: false:** cặp binary name + defining loader khác nhau tạo hai class runtime khác nhau.
4. **child owns version: true:** kiểm tra định nghĩa class bằng `getClassLoader() == loader`.
5. **service: child:** `ServiceImpl` do child định nghĩa resolve `Version` qua loader của mình, do đó dùng phiên bản child.
6. **api shared: true:** `api.Service` không nằm trong namespace child-first nên được parent cung cấp, cho phép cast triển khai child sang interface host.
7. **jdk shared: true:** `java.lang.String` được loader nền tảng/JVM cung cấp qua delegation, không bị child tái định nghĩa.

Mã được kiểm thử bằng `javac --release 17` và `java` với đúng hai classpath/output riêng; kết quả khớp hoàn toàn.

## 6. Tại sao package API chung cần parent-first?

Giả sử child cũng đóng gói riêng `api.Service` rồi chọn child-first cho `api.*`. Mặc dù class file mang tên giống nhau, Java có thể tạo:

~~~text
api.Service @ ParentLoader   !=   api.Service @ ChildLoader
~~~

Hai class đó không cùng danh tính JVM. Một object `plugin.impl.ServiceImpl` triển khai bản API child có thể **không ép kiểu** sang `api.Service` phía host, gây `ClassCastException`. Khi method signatures hoặc field types bắt buộc đồng nhất kiểu qua loader, JVM cũng có thể áp dụng *loading constraints* và phát sinh `LinkageError`.

Vì vậy, hãy đặt các interface và types xuất hiện ở **ranh giới giao tiếp** (tham số, return type, exception contract, DTO chia sẻ) vào namespace parent/shared loader. Chỉ cô lập implementation/private dependencies. Nếu một thư viện phiên bản riêng rò rỉ kiểu qua API công khai của plugin, policy theo package có thể không đủ; cân nhắc adapter/serialization hoặc một contract riêng.

## 7. Fallback có thể che giấu xung đột phiên bản

Giả sử child thiếu `plugin.impl.Helper` nhưng parent có bản cũ. Code child-first + fallback sẽ hỏi parent và nhận class cũ, có thể gây `NoSuchMethodError` khi plugin đã compile dựa trên bản mới.

Một số cách lựa chọn:

- **Cho fallback** khi tên đó thật sự có thể chia sẻ. Cần test tên có ở parent mà child không có.
- **Fail closed** đối với namespace riêng tuyệt đối: nếu child `findClass` không thấy thì ném `ClassNotFoundException`, không dùng parent.
- **Tách namespace** bằng package khác hoặc shading/relocation cho dependency tư nhân để giảm nguy cơ trùng.
- **Thiết kế API bridge** ở parent cho các lớp phải truyền qua ranh giới.

Đừng triển khai catch tổng quát kiểu `catch (Throwable ignored)` rồi fallback: nó che giấu lỗi bytecode hỏng, lỗi security, linkage và có thể khiến ứng dụng âm thầm chạy với phiên bản khác.

## 8. Đồng bộ, caching, linking và deadlock

Một override `loadClass` có trách nhiệm lớn hơn override `findClass` đơn thuần:

| Thành phần | Vì sao quan trọng? |
| --- | --- |
| `getClassLoadingLock(name)` | Khóa nạp theo tên đúng với loader; nhiều luồng không cùng define class một cách bất hợp lệ. |
| `findLoadedClass(name)` | Không lặp `defineClass` cho tên đã ghi nhận. |
| `super.loadClass(name, false)` | Cho parent-first hoạt động khi namespace không child-first hoặc khi fallback. |
| `resolveClass(found)` | Giữ hợp đồng khi `resolve=true`. |
| Phân biệt exception | `ClassNotFoundException` khác `LinkageError` và lỗi khởi tạo. |

`loadClass(name)` tương đương `loadClass(name,false)`; `resolveClass` thực hiện linking nếu cần, **không** gọi static initializer. Java có khái niệm *parallel capable class loader* và đăng ký thích hợp để hỗ trợ khóa khác nhau theo tên. Đừng mặc định mọi subclass có chính sách phức tạp đều parallel capable; phải kiểm tra đặc tả và cấu hình inheritance/registration.

Với đồ thị delegation không phân cấp hoặc có lời gọi giữa nhiều loader, deadlock có thể xuất hiện nếu các luồng giữ khóa theo thứ tự khác nhau. Đoạn ví dụ chỉ có một parent và một child, không tạo vòng delegation.

Việc đóng `URLClassLoader` bằng *try-with-resources* giải phóng tài nguyên I/O; **không** ngay lập tức unload class đã định nghĩa hay xóa mọi object đang dùng. Đừng dùng `close()` như phép thay class cùng tên trong một loader đang tồn tại.

## 9. Resource policy không tự đi theo class policy

Override `loadClass` chỉ thay đổi thứ tự **tìm class**. Tài nguyên được tìm qua API khác:

~~~java
URL url = loader.getResource("plugin/impl/config.properties");
InputStream stream =
        loader.getResourceAsStream("plugin/impl/config.properties");
~~~

Đây là mã minh họa, giả định loader có sẵn. `URLClassLoader.getResource` bình thường có chính sách parent-first riêng, nên có thể có tình huống class từ plugin child nhưng resource cùng tên lại từ parent. Nếu resource chứa cấu hình tương ứng chính xác với class phiên bản đó, việc chọn khác nguồn gây bug khó phát hiện.

Có thể phải định nghĩa chính sách riêng cho `getResource`/`getResources`/`findResource`, hoặc đổi tên/path resource để tránh trùng. `META-INF/services/...` và `ServiceLoader` cũng phải được kiểm tra: một số cách dùng `ServiceLoader` lấy loader từ thread context class loader, khác với cơ chế JVM resolve bytecode thông thường.

**Tương tự**, package policy không tự tạo JPMS ModuleLayer hoặc xử lý exports/opens của named modules. `URLClassLoader` là công cụ tìm lớp/resource trên URL classpath, không thay thế module resolver.

## 10. Rủi ro thực tế và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Child vẫn dùng phiên bản host | Policy không match tên, hoặc parent được hỏi trước khi `findClass`. | Kiểm tra `childFirst(name)` và `clazz.getClassLoader()`. |
| `ClassCastException` dù tên interface giống nhau | Host/child định nghĩa trùng API contract. | So sánh `Service.class` và class interface thực tế phía plugin. |
| `NoSuchMethodError` | Fallback sang dependency sai version. | Kiểm tra class nguồn và dependency graph. |
| `LinkageError: duplicate class definition` | Bỏ cache/khóa; định nghĩa lại cùng binary name. | Dùng `findLoadedClass` và khóa chuẩn. |
| `ClassFormatError` hoặc `VerifyError` | Bytecode nguồn hỏng hoặc không tương thích. | Đọc cause; đừng nuốt thành `ClassNotFoundException`. |
| Deadlock khi nạp nhiều loader | Có vòng ủy quyền hoặc khóa chồng chéo. | Rà lại delegation graph, locking và parallel capability. |
| Lỗi loader constraint violation | Hai loader có signature dùng cùng binary name nhưng class runtime khác. | Đưa types giao tiếp lên shared loader. |
| Config sai version | Class child-first, resource vẫn parent-first. | Kiểm tra policy resource tương ứng. |
| Package gần giống bị bắt nhầm | Prefix thiếu dấu `.` ở cuối. | Test `plugin.implx.*` và subpackage. |
| Plugin chạy được nhưng không cô lập bảo mật | Class loader không phải sandbox. | Xây chính sách bảo mật/cách ly tiến trình riêng. |

Với những plugin không tin cậy, đừng xem class loader là biện pháp bảo mật cho filesystem, network, CPU hay quyền hệ điều hành. Đây chủ yếu là cơ chế namespace, delegation và lifecycle class.

## 11. Checklist và bài tự kiểm tra

Trước khi đưa policy vào production:

1. Xác định rõ **API chung**, **implementation riêng**, **dependency tư nhân**, **lớp nền tảng**.
2. Dùng binary name và kiểm tra ranh giới prefix package: `"plugin.impl."`, không phải `"plugin.impl"`.
3. Chỉ override `loadClass` khi thật sự cần đổi **thứ tự delegation**; nếu giữ parent-first, ưu tiên override `findClass`.
4. Trong override, giữ khóa `getClassLoadingLock`, cache `findLoadedClass`, fallback đúng quyết định và `resolveClass`.
5. Xem xét rõ **child-first + fallback** hay **child-only** cho từng namespace; test tên thiếu trong child nhưng có ở parent.
6. Kiểm tra cùng binary name ở hai loader: object `Class<?>` phải khác khi mong cô lập.
7. Kiểm tra shared API: `loader.loadClass("api.Service") == Service.class` và ép kiểu qua contract thành công.
8. Kiểm tra các thư viện phiên bản khác nhau, các method signatures, exceptions, DTO và resource names.
9. Kiểm tra nạp lặp và nạp đa luồng, đặc biệt với custom graph hoặc nhiều loaders.
10. Kiểm tra resource/provider, vòng đời URLClassLoader, và giới hạn bảo mật của plugin.

**Câu hỏi 1.** Vì sao prefix `plugin.impl.` tốt hơn `plugin.impl`?

**Đáp:** Nó match đúng ranh giới package, tránh tên gần giống như `plugin.implx.Version`.

**Câu hỏi 2.** Child có bản `plugin.impl.Version` và parent cũng có bản cùng tên. Child-first sẽ lấy bản nào?

**Đáp:** Bản child nếu `findClass` của child thành công, dù parent cũng có. Nếu child không có, kết quả phụ thuộc policy fallback hay fail closed.

**Câu hỏi 3.** Vì sao `api.Service` ở parent và phải giữ cùng identity?

**Đáp:** Host và plugin phải chia sẻ một contract runtime; hai interface cùng binary name nhưng khác defining loader có thể không cast/linkage được.

**Câu hỏi 4.** Đã override `loadClass` child-first thì `getResource` cũng tự child-first phải không?

**Đáp:** Không. Resource lookup có API và chính sách độc lập; cần xử lý hoặc kiểm thử riêng.

**Câu hỏi 5.** Cờ `resolve=true` làm chạy `static { ... }`?

**Đáp:** Không. Nó yêu cầu linking khi cần; initialization được kích hoạt bởi active use hoặc API có hợp đồng initialize riêng.

## Tài liệu chính thức

- [Java SE 21 – ClassLoader.loadClass và getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html).
- [Java SE 21 – URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html).
- [JVMS Java SE 21 §5.3 – Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3).
- [JVMS Java SE 21 §5.4 – Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4).
