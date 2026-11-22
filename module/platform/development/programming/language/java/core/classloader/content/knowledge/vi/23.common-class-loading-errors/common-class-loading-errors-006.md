# LinkageError do định nghĩa lớp trùng hoặc vi phạm loading constraint

## 1. Vấn đề: cùng tên class nhưng JVM không thể liên kết

Trong hệ thống Java dùng **custom ClassLoader**, plugin, application server hoặc hot reload, bạn có thể gặp thông báo:

~~~text
java.lang.LinkageError: loader ... attempted duplicate class definition
~~~

hoặc:

~~~text
java.lang.LinkageError: loader constraint violation ...
~~~

Cả hai có thể liên quan đến class loading, nhưng **khác nguyên nhân và khác cách xử lý**:

- **Định nghĩa lớp trùng (duplicate class definition):** JVM phát hiện một loader cố tạo lại class có cùng binary name mà nó đã được ghi nhận là initiating loader/đã định nghĩa. Một ClassLoader không thể tùy tiện gọi defineClass lần hai để ghi đè cùng class.
- **Vi phạm loading constraint:** Trong quá trình liên kết các kiểu liên quan qua nhiều loaders, JVM bắt buộc một tên type trong method/field descriptor phải chỉ về **cùng một runtime Class** dưới các loaders nhất định. Nếu thực tế hai loaders đã dùng **hai Class khác nhau** cho tên đó, JVM ném LinkageError để duy trì type safety.

**Quan trọng:** JVM hoàn toàn cho phép **hai ClassLoaders khác nhau định nghĩa hai class có cùng binary name** trong những trường hợp cách ly hợp lệ. Việc trùng tên giữa hai loaders **tự nó không phải LinkageError**. Lỗi chỉ xuất hiện khi phạm quy tắc định nghĩa/initiating loader hoặc một **ràng buộc type identity bắt buộc**.

Bài này có hai ví dụ Java 17+ đã kiểm chứng bằng OpenJDK 21, quy trình tái hiện lỗi, cách đọc stack trace và hướng khắc phục thực tế.

## 2. Phân biệt defining loader và initiating loader

### 2.1 Defining loader

**Defining loader** là loader đã thực sự định nghĩa runtime class từ một biểu diễn hợp lệ (ví dụ gọi defineClass). Với class thường, **(binary name, defining loader)** xác định danh tính runtime type:

~~~text
("plugin.Item", LoaderA) != ("plugin.Item", LoaderB)
~~~

Hai class có cùng mã nguồn và cùng tên vẫn khác loại nếu defining loaders khác nhau.

### 2.2 Initiating loader

**Initiating loader** là loader mà JVM ghi nhận đã bắt đầu yêu cầu load một class; nó có thể không phải defining loader.

Ví dụ:

~~~text
ChildLoader.loadClass("api.Service")
     |
     +-- hỏi ParentLoader
              |
              +-- parent định nghĩa api.Service
     |
     +-- child nhận lại Class của parent
~~~

Ở tình huống này:

- **ParentLoader** là defining loader của api.Service.
- **ChildLoader** có thể được JVM ghi nhận là initiating loader của cùng class do parent định nghĩa.
- **findLoadedClass("api.Service")** của child có thể thấy Class đã được initiate ở child, dù defining loader của Class đó là parent.

Đây là lý do một custom loader không nên tự gọi **defineClass** bừa bãi sau khi đã delegate tên đó sang parent.

### 2.3 Không thể định nghĩa lại tùy tiện trong cùng loader

Theo JVMS §5.3.5, nếu JVM đã ghi nhận loader L là initiating loader cho tên N thì việc yêu cầu tạo định nghĩa mới của tên ấy với L là không hợp lệ và gây **LinkageError**.

Trong thực tế dễ gặp hơn: một loader **gọi defineClass hai lần** với cùng binary name. Đây là hành vi sai ngay cả khi hai mảng bytes hoàn toàn giống nhau.

~~~text
Loader L
  defineClass("demo.Token", bytesV1) -> thành công
  defineClass("demo.Token", bytesV1) -> LinkageError
  defineClass("demo.Token", bytesV2) -> LinkageError

Loader L2 hoàn toàn mới
  defineClass("demo.Token", bytesV2) -> có thể thành công
~~~

Không có cơ chế “overwrite class” tự động trong **ClassLoader.defineClass**. Muốn cập nhật method body của cùng class đã nạp, có cơ chế **java.lang.instrument.Instrumentation.redefineClasses/retransformClasses** với giới hạn riêng. Muốn phiên bản runtime type mới, tạo loader mới rồi quản lý chuyển đổi/lifecycle.

## 3. LinkageError là một họ lỗi, không phải tất cả đều duplicate

**java.lang.LinkageError** là Error, không phải checked exception. Một số loại liên quan gồm:

| Loại lỗi | Dấu hiệu | Nhóm nguyên nhân |
| --- | --- | --- |
| **LinkageError** trực tiếp, thông báo attempted duplicate class definition | Cùng loader cố define lại tên đã biết | Duplicate definition |
| **LinkageError** trực tiếp, thông báo loader constraint violation | Hai loaders phải thống nhất runtime Class trong một type descriptor nhưng không thống nhất | Loading constraint |
| **NoClassDefFoundError** | JVM cần class nhưng định nghĩa không thể sử dụng/tìm được hoặc khởi tạo từng thất bại | Loading/linking/initialization |
| **ClassFormatError** | Bytes không phải class-file hợp lệ | Định dạng |
| **UnsupportedClassVersionError** | Class-file version không được JVM hỗ trợ | Version |
| **VerifyError** | Bytecode không thỏa verifier | Verification |
| **NoSuchMethodError / NoSuchFieldError** | Bytecode tham chiếu thành viên không tồn tại theo runtime definition | Binary incompatibility |
| **IncompatibleClassChangeError** và subclasses | Loại/thành viên được dùng không khớp quan hệ binary mong đợi | Binary incompatibility |

**ClassNotFoundException** không phải LinkageError: đó là checked exception mà lookup APIs như loadClass có thể ném khi không tìm thấy class theo tên.

**ClassCastException** cũng không phải LinkageError: nó là RuntimeException khi cast sai. Hai loaders có thể định nghĩa hai type trùng tên **hợp lệ**, rồi ứng dụng ném ClassCastException khi cố cast instance giữa hai Class khác identity, mà không có loading constraint violation.

**Đừng sửa theo tên exception chung chung.** Đọc **lớp exception thực tế, thông báo đầy đủ, cause, thời điểm lỗi và đường loader ownership**.

## 4. Ví dụ Java 17+ số 1: định nghĩa trùng trong cùng loader

### 4.1 Cấu trúc thư mục

~~~text
project/
├── dup-src/
│   └── demo/
│       └── Token.java
└── src/
    └── DuplicateDemo.java
~~~

**dup-src/demo/Token.java**:

~~~java
package demo;

public class Token {
    public String value() {
        return "token";
    }
}
~~~

**src/DuplicateDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class DuplicateDemo {
    static class OnceLoader extends ClassLoader {
        OnceLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("dup-out/demo/Token.class"));

        OnceLoader loader = new OnceLoader(
                ClassLoader.getPlatformClassLoader());

        Class<?> first = loader.define("demo.Token", bytes);

        System.out.println("first = " + first.getName());
        System.out.println("defined by loader = "
                + (first.getClassLoader() == loader));

        try {
            loader.define("demo.Token", bytes);
            System.out.println("unexpected");
        } catch (LinkageError error) {
            System.out.println("second = "
                    + error.getClass().getSimpleName());
        }

        OnceLoader secondLoader = new OnceLoader(
                ClassLoader.getPlatformClassLoader());

        Class<?> second =
                secondLoader.define("demo.Token", bytes);

        System.out.println("other loader succeeds = "
                + (first != second));
    }
}
~~~

### 4.2 Biên dịch và chạy

Đứng tại thư mục **project**:

~~~bash
javac -d dup-out dup-src/demo/Token.java
javac -d demo-out src/DuplicateDemo.java
java -cp demo-out DuplicateDemo
~~~

Windows PowerShell dùng chính các lệnh trên vì mỗi classpath chỉ có một entry.

**Stdout đã chạy thực tế trên OpenJDK 21:**

~~~text
first = demo.Token
defined by loader = true
second = LinkageError
other loader succeeds = true
~~~

### 4.3 Tại sao lần thứ hai thất bại?

**loader.define("demo.Token", bytes)** lần đầu tạo runtime Class được định nghĩa bởi **loader**. Lần thứ hai cùng object loader yêu cầu defineClass với cùng name; JVM từ chối tạo định nghĩa trùng và ném LinkageError.

Trong ví dụ, catch chỉ in **tên loại lỗi**, không in toàn bộ thông báo vì **message cụ thể chứa tên loader và định dạng khác nhau giữa JVMs**.

**Quan sát then chốt:** Tạo **secondLoader** mới và define cùng bytes lại thành công. **first != second** là true. Việc **hai loaders định nghĩa cùng name là hợp lệ** nếu chưa có constraint bắt buộc chúng đồng nhất trong một quan hệ liên kết.

Đây là ví dụ về khác biệt giữa “trùng trong cùng loader” và “trùng giữa nhiều loaders”.

### 4.4 Ví dụ này có cố ý bỏ qua loadClass mặc định không?

Có. Phương thức **define** là wrapper trực tiếp tới protected defineClass để minh họa lỗi. Đây **không phải thiết kế loader production**.

Một loader bình thường nên để **ClassLoader.loadClass** thực hiện cache/delegation và override **findClass** để đọc bytes riêng. Khi cần custom policy, vẫn phải bảo toàn logic:

~~~text
getClassLoadingLock(name)
    |
    v
findLoadedClass(name)
    |
    v
parent delegation hoặc custom route phù hợp
    |
    v
findClass(name) khi thật sự cần định nghĩa mới
    |
    v
resolveClass nếu resolve=true
~~~

Nếu lặp lại defineClass trong cùng loader vì thấy file trên đĩa đã thay đổi, phương án đúng không phải “nuốt LinkageError và retry”, mà là xác định **Class đã tồn tại**, hoặc tạo loader mới cho deployment khác.

## 5. Loading constraint thực sự là gì?

### 5.1 Vấn đề type safety giữa nhiều loaders

Giả sử class A của loader L1 gọi method ở class B của loader L2, và chữ ký method có kiểu **api.Payload**:

~~~java
api.Payload echo(api.Payload value)
~~~

Một runtime name **api.Payload** có thể trỏ tới các Class khác nhau nếu loader L1 và loader L2 chọn bytecode từ những nguồn riêng.

Khi liên kết method/field tham chiếu qua boundary này, JVM phải bảo đảm **api.Payload trong descriptor chỉ tới cùng runtime type** ở những loader có liên quan. Nếu không, runtime method call có thể tưởng rằng tham số/giá trị trả về tương thích chỉ vì tên giống nhau trong constant pool, trong khi thực tế không phải cùng Class.

### 5.2 Ký hiệu của JVMS §5.3.4

JVMS mô tả loading constraints dưới dạng:

~~~text
N^L1 = N^L2
~~~

Đọc là: **tên type N do loader L1 và loader L2 initiate phải biểu thị cùng Class** khi ràng buộc ấy áp dụng.

Điều quan trọng:

- Đây là **ràng buộc type identity**, không phải lệnh JVM phải dùng một loader duy nhất cho toàn bộ chương trình.
- JVMS áp đặt constraints tại những thời điểm cụ thể của **preparation/resolution/lookup và method overriding**.
- Type names trong **method descriptors** (tham số và return) và **field descriptors** có thể tham gia.
- Với array reference types, JVM xét element type theo quy tắc thích hợp.
- Khi ràng buộc tồn tại mà hai loaders đã được ghi nhận initiate **hai Class khác nhau** cho cùng tên N, JVM ném **LinkageError**.
- Constraint có thể được áp đặt **trước** khi hai tên được resolve thực sự ở cả hai loader; vi phạm có thể lộ ra về sau khi một tên được initiate.
- JVM không bắt buộc ném lỗi ngay ở dòng **defineClass** của class đầu tiên; lỗi có thể xuất hiện khi preparation, linking hoặc resolution diễn ra.

### 5.3 Điều kiện vi phạm theo đặc tả

Theo JVMS §5.3.4, một loading constraint bị vi phạm khi đồng thời thỏa những điều kiện cần thiết:

1. Có initiating loader L đã được JVM ghi nhận cho Class C với tên N.
2. Có initiating loader L' đã được JVM ghi nhận cho Class C' cũng mang tên N.
3. Tập loading constraints (và quan hệ tương đương bắc cầu từ đó) đòi **N^L = N^L'**.
4. Nhưng **C != C'**.

**Không đủ** chỉ có điều kiện 1, 2 và 4. Phải có **điều kiện 3: ràng buộc bắt buộc đồng nhất type**.

### 5.4 Điều gì tạo ra loading constraint?

Các ví dụ trong JVMS:

- Một method override giữa subclass/superclass hoặc implements interface mà descriptor chứa reference types.
- Resolution của field reference đi qua class boundaries với field descriptor chứa reference type.
- Resolution của method/interface method references với tham số hoặc return reference types.
- Những bước liên kết tương ứng đòi các symbolic references biểu thị cùng runtime type.

Không nên hiểu rằng mọi method có signature chứa class riêng của plugin đều gây constraint violation. Nếu tất cả participants dùng **cùng Class shared API** qua delegation, constraints được thỏa mãn.

## 6. Ví dụ Java 17+ số 2: tái hiện loader constraint violation

### 6.1 Mô hình: interface chung ở host, Payload riêng của child

Ví dụ này cố tình tạo một tình huống **không an toàn**:

- Parent/application loader định nghĩa **api.Api** và **api.Payload**.
- Child loader tự định nghĩa **một api.Payload khác** có **cùng binary name**.
- Child còn định nghĩa **impl.Impl implements api.Api**. Method triển khai có descriptor chứa api.Payload.
- Khi JVM chuẩn bị liên kết interface method table cho Impl, nó phát hiện **api.Payload của child khác api.Payload của parent** trong một chữ ký buộc phải thống nhất.

~~~text
AppLoader:
    api.Api
       method api.Payload echo(api.Payload)
    api.Payload   <-- Class P1

BytesLoader child:
    api.Payload   <-- Class P2, P2 != P1
    impl.Impl implements AppLoader's api.Api

Method echo(Payload) qua interface boundary:
    Payload^AppLoader = Payload^BytesLoader
                  nhưng P1 != P2
         => loader constraint violation
~~~

### 6.2 Cấu trúc thư mục

~~~text
project/
├── host-src/
│   └── api/
│       ├── Api.java
│       └── Payload.java
├── child-src/
│   ├── api/
│   │   └── Payload.java
│   └── impl/
│       └── Impl.java
└── src/
    └── ConstraintDemo.java
~~~

**host-src/api/Payload.java**:

~~~java
package api;

public class Payload {
    public String source() {
        return "host";
    }
}
~~~

**host-src/api/Api.java**:

~~~java
package api;

public interface Api {
    Payload echo(Payload p);
}
~~~

**child-src/api/Payload.java**:

~~~java
package api;

public class Payload {
    public String source() {
        return "child";
    }
}
~~~

**child-src/impl/Impl.java**:

~~~java
package impl;

import api.Api;
import api.Payload;

public class Impl implements Api {
    @Override
    public Payload echo(Payload p) {
        return p;
    }
}
~~~

Hai file **api/Payload.java** có cùng binary name nhưng thuộc **hai source roots khác nhau**; không compile chúng cùng lúc vào một output folder.

### 6.3 Launcher ConstraintDemo.java

**src/ConstraintDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import api.Api;
import api.Payload;

public class ConstraintDemo {
    static final class BytesLoader extends ClassLoader {
        BytesLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> defineLocal(String name, Path file)
                throws Exception {
            byte[] bytes = Files.readAllBytes(file);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("parent Payload = "
                + Payload.class.getName());
        System.out.println("shared API from parent = "
                + (Api.class.getClassLoader()
                   == ClassLoader.getSystemClassLoader()));

        BytesLoader child = new BytesLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> local = child.defineLocal(
                "api.Payload",
                Path.of("child-out/api/Payload.class"));

        System.out.println("same payload Class = "
                + (local == Payload.class));

        try {
            Class<?> impl = child.defineLocal(
                    "impl.Impl",
                    Path.of("child-out/impl/Impl.class"));

            System.out.println("impl defined = "
                    + impl.getName());

            Object obj = impl.getConstructor().newInstance();

            System.out.println("created = "
                    + obj.getClass().getName());
            System.out.println("invoked = "
                    + ((Api) obj).echo(new Payload()).source());

        } catch (LinkageError error) {
            System.out.println("error type = "
                    + error.getClass().getSimpleName());
            System.out.println("mentions constraint = "
                    + error.getMessage().contains("loader constraint"));
            System.out.println("error message = "
                    + error.getMessage());
        }

        // Cách sửa: loader mới KHÔNG định nghĩa api.Payload
        BytesLoader safe = new BytesLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> impl2 = safe.defineLocal(
                "impl.Impl",
                Path.of("child-out/impl/Impl.class"));

        Api ok = (Api) impl2.getConstructor().newInstance();

        System.out.println("shared payload works = "
                + ok.echo(new Payload()).source());
    }
}
~~~

**defineLocal** cố tình gọi defineClass trực tiếp để ép child định nghĩa thêm api.Payload và làm phát sinh xung đột. Đây là fixture chẩn đoán, không phải loader nên dùng trong sản phẩm.

### 6.4 Biên dịch theo đúng thứ tự

Đứng tại thư mục **project**, thực hiện từng lệnh:

~~~bash
javac -d host-out host-src/api/Payload.java host-src/api/Api.java

javac -cp host-out -d child-out child-src/impl/Impl.java

javac -d child-out child-src/api/Payload.java

javac -cp host-out -d demo-out src/ConstraintDemo.java

java -cp demo-out:host-out ConstraintDemo
~~~

**Tại sao compile Impl trước file Payload riêng của child?** Vì **impl.Impl** phải được compile chống lại **api.Api** và **api.Payload** của host để method descriptor đúng với interface chung. Chúng ta sau đó mới tạo một **api.Payload** khác trong child-out để cố tình làm hỏng identity tại runtime.

Trên Windows PowerShell, thay lệnh cuối bằng:

~~~powershell
java -cp "demo-out;host-out" ConstraintDemo
~~~

Các lệnh javac dùng **-cp host-out** chỉ có một entry nên giống nhau trên cả hai hệ điều hành.

### 6.5 Stdout đã kiểm chứng trên OpenJDK 21

Đầu ra được kiểm chứng; dòng **error message** phụ thuộc tên/hash loader cụ thể nên được lược khỏi mẫu cố định:

~~~text
parent Payload = api.Payload
shared API from parent = true
same payload Class = false
impl defined = impl.Impl
error type = LinkageError
mentions constraint = true
shared payload works = host
~~~

Trong chương trình thực, **giữa dòng mentions constraint và shared payload works còn có dòng**:

~~~text
error message = loader constraint violation in interface itable initialization ...
~~~

Đó là **dòng minh họa dạng thông báo**, không phải nguyên văn bất biến. JVM có thể bổ sung identity/address của ClassLoaders, module names và method descriptor. **Không test bằng toàn bộ chuỗi error message**; nếu cần kiểm tra loại lỗi, dùng exception class và đối chiếu nghĩa của message/stack trace.

Đặc biệt, dòng **created = ...** không được in trong lần chạy lỗi trên OpenJDK 21 vì việc liên kết cần thiết khi tạo instance ném LinkageError trước đó.

### 6.6 Tại sao lỗi xuất hiện sau dòng “impl defined”?

Khi **child.defineLocal("impl.Impl", ...)** trả về, class đã được tạo nhưng JVM có thể chưa hoàn tất các bước linking/resolution cụ thể dẫn tới kiểm tra constraint. Lệnh tạo instance qua reflection làm JVM tiến tới **interface itable initialization**, tại đó JVM phát hiện signature bất tương thích.

**Đây là đặc điểm quan trọng của LinkageError:** Không nên khẳng định lỗi phải xuất hiện ngay khi gọi defineClass, ngay khi loadClass hoặc ngay khi method được gọi. JVMS xác định các thời điểm kiểm tra constraints; exact stack frame và timing phụ thuộc kiểu resolution/JVM.

### 6.7 Vì sao phiên bản safe hoạt động?

Loader **safe** chỉ tự define **impl.Impl** và **không** tự define api.Payload. Khi cần api.Api và api.Payload, nó dùng parent delegation thông thường. Do đó method **Api.echo(Payload)** của parent và method triển khai từ child cùng nhắc đến **chính Class api.Payload của parent**.

Lệnh:

~~~java
Api ok = (Api) impl2.getConstructor().newInstance();
System.out.println(ok.echo(new Payload()).source());
~~~

chạy và trả **host**. Điều này chứng minh giải pháp **chia sẻ API types bằng một loader thống nhất**, không phải đổi tên method hay bắt rồi bỏ LinkageError.

## 7. Khác biệt tinh tế: JVM cho phép isolation nhưng bảo vệ boundary

Một hệ thống plugin hợp lệ:

~~~text
PluginLoaderA: plugin.internal.Cache
PluginLoaderB: plugin.internal.Cache
~~~

Hai class cùng binary name nhưng định nghĩa khác nhau **có thể cùng tồn tại** nếu không có ràng buộc buộc chúng phải là một type.

Vấn đề xuất hiện khi giao tiếp giữa hai loaders qua một type cần thống nhất:

~~~text
Host interface:
    SharedResult execute(SharedInput arg)

Plugin implements:
    SharedResult execute(SharedInput arg)

Nếu host và plugin dùng cùng SharedInput/SharedResult Class
    -> loading constraints được thỏa mãn

Nếu plugin tự define SharedInput/SharedResult trùng tên
    -> có thể vi phạm loading constraint ở linkage boundary
~~~

**Kinh nghiệm:** Đưa **service interfaces, DTOs, callback types và các dependency API dùng chung** vào parent/shared loader. Chỉ cô lập implementation packages. Plugin runtime vẫn có thể dùng child-first cho implementation riêng, nhưng tránh child-first trên **api.*** nếu đó là kiểu host truyền qua method signatures.

### 7.1 Cùng binary name không bao giờ đủ để ép kiểu

Với:

~~~java
Class<?> a = loaderA.loadClass("plugin.Item");
Class<?> b = loaderB.loadClass("plugin.Item");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                           // false
~~~

Đây là snippet giả định hai loaders thực sự tự define class và không delegate đến cùng parent Class.

Nếu bạn tạo instance của a rồi thử ép sang type b, có thể gặp **ClassCastException**. Đây là tình huống **identity mismatch ở runtime cast**, không nhất thiết là loader constraint violation. Phân biệt chúng bằng error type và code path.

### 7.2 Runtime package cũng khác theo defining loader

Ngay cả khi hai class khai báo cùng:

~~~java
package plugin.internal;
~~~

nếu được định nghĩa bởi hai loaders khác nhau, chúng không tự thuộc cùng **runtime package** cho package-private access. Khi code cần truy cập thành viên package-private, có thể xuất hiện **IllegalAccessError** nếu bytecode liên kết tới class khác runtime package, dù source text ghi cùng package.

Đừng sửa bằng cách đổi package name tràn lan; phải hiểu class identity, package/module access và loader mapping.

## 8. Nguyên nhân thực tế của duplicate definition

### 8.1 findClass bị gọi trực tiếp thay vì loadClass

~~~java
// Sai hướng nếu class cùng tên đã load:
Class<?> c = customLoader.findClass("plugin.Service");
~~~

Trong ứng dụng thông thường, **findClass là protected** và chỉ nên được gọi trong thuật toán loadClass thích hợp. Nếu subclass tự expose wrapper public để gọi findClass/defineClass nhiều lần, JVM có thể thấy cùng name được định nghĩa lại.

### 8.2 Override loadClass bỏ findLoadedClass

Ví dụ không an toàn:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    return findClass(name);
}
~~~

Đây là đoạn **phản ví dụ** bên trong subclass, không dùng trong production. Nó phá parent delegation, caching, resolve flag và locking. Mỗi lần load lại có nguy cơ gọi defineClass thêm lần nữa.

### 8.3 Cạnh tranh giữa nhiều threads

Nếu hai threads cùng yêu cầu class name, code:

~~~text
Thread A: class chưa có -> đọc bytes
Thread B: class chưa có -> đọc bytes
Thread A: defineClass thành công
Thread B: defineClass lại -> LinkageError
~~~

là race kinh điển. Cần khóa trong suốt chu kỳ **check → load → define** chứ không chỉ synchronized riêng lẻ từng bước.

### 8.4 Thay JAR trên đĩa rồi gọi defineClass lại

JVM không tự cập nhật class đã được định nghĩa khi file .class/.jar thay đổi. Một loader đang sống không phải container có thể “overwrite” class definitions.

Muốn nâng version implementation, tạo loader mới và quản lý old loader lifecycle, hoặc dùng instrumentation trong giới hạn cho phép.

### 8.5 Plugin bị đăng ký nhiều lần trong cùng loader

Một plugin engine có thể retry khởi tạo hoặc chạy hai callback đồng thời, cả hai đi vào cùng logic defineClass(name). Nếu ownership chưa rõ, một Class được define từ nhiều đường gọi.

**Giải pháp:** Cho một thành phần chịu trách nhiệm nạp mỗi binary name; dùng findLoadedClass đúng cách và đồng bộ hóa; tránh caching bytes như thể nó tương đương caching Class object.

## 9. Nguyên nhân thực tế của loading constraint violation

### 9.1 Child-first quá rộng

Nếu child-first áp dụng cả cho **host API package**, loader plugin có thể define lại **api.Event**, **api.Result**, **api.Context** và các types xuất hiện trong method signatures của host interfaces.

JVM có thể chấp nhận một số class trước, rồi phát hiện constraint khi linking interface implementations, method resolution hoặc field access.

**Giải pháp:** Parent-first cho shared packages; selective child-first cho implementation, chẳng hạn **plugin.internal.***.

### 9.2 Thư viện phụ thuộc bị đóng gói trùng

Host và plugin cùng có một bản thư viện **lib.model.Dto** trong classpath/JAR riêng. Nếu class này xuất hiện trong public API signature, việc tự define bản plugin có thể gây identity mismatch.

**Giải pháp:** Một bản shared dependency trong loader chung, hoặc thiết kế boundary không trực tiếp chuyển object thuộc class bị cô lập.

### 9.3 Thay class implementation mà quên shared interface

Host cast plugin implementation thành interface **api.Service** do host define, nhưng plugin lại có bản api.Service riêng. Lỗi có thể là **ClassCastException** hoặc linkage error liên quan, tùy lúc và quan hệ mà JVM phải resolve.

**Giải pháp:** Dùng một **Class api.Service chung** và để implementation của plugin ở loader riêng.

### 9.4 Tùy biến loader graph thành vòng/truy xuất không nhất quán

Một số framework có peer delegation, classloader-per-tenant hoặc module layer mappings. Nếu các đường dẫn lựa chọn Class khác nhau cho cùng API name tại những nơi phải thỏa type descriptor, JVM sẽ áp đặt constraints và có thể phát hiện xung đột.

**Giải pháp:** Xác định package ownership nhất quán, tránh nhiều nguồn tự định nghĩa cùng shared type. Không cố vô hiệu hóa JVM checks.

### 9.5 Reflection và service loading không sửa type identity

**Thread Context ClassLoader**, **Class.forName** và **ServiceLoader** có thể tìm provider classes qua loader khác. Nhưng chỉ đổi TCCL không làm những bản API Class từ host/plugin trở thành một.

Khi debugging, kiểm tra **serviceType.getClassLoader()**, **providerClass.getClassLoader()** và API dependency classes. Điều chỉnh rõ loader của shared contracts.

## 10. Viết ClassLoader đúng để tránh cả hai nhóm lỗi

### 10.1 Mẫu parent-first: chỉ override findClass

Với nguồn bytecode riêng, nên bắt đầu bằng:

~~~java
public final class PluginLoader extends ClassLoader {
    private final java.nio.file.Path root;

    public PluginLoader(ClassLoader parent,
                        java.nio.file.Path root) {
        super(parent);
        this.root = root;
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {

        if (!name.startsWith("plugin.internal.")) {
            throw new ClassNotFoundException(name);
        }

        java.nio.file.Path file = root.resolve(
                name.replace('.', '/') + ".class");

        try {
            byte[] bytes = java.nio.file.Files.readAllBytes(file);
            return defineClass(name, bytes, 0, bytes.length);
        } catch (java.io.IOException ex) {
            throw new ClassNotFoundException(name, ex);
        }
    }
}
~~~

Đây là **một class code hoàn chỉnh để minh họa hook**, chưa phải chương trình main. Đầu vào path/name trong loader production cần được kiểm soát chống path traversal, kích thước bytes, package restrictions và nguồn không tin cậy.

**Lợi ích:** Thuật toán ClassLoader.loadClass mặc định đã xử lý **getClassLoadingLock, findLoadedClass, parent-first, findClass, resolveClass**. Shared API packages thường được parent cung cấp, tránh child định nghĩa lại.

**Giới hạn:** Nếu parent cũng có implementation class mà plugin phải ưu tiên bản riêng, findClass đơn độc không sửa được thứ tự delegation. Lúc đó cần cân nhắc selective child-first theo package có chủ đích.

### 10.2 Selective child-first cần giữ cache và khóa

Mẫu ý tưởng:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {

    if (!name.startsWith("plugin.internal.")) {
        return super.loadClass(name, resolve);
    }

    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);

        if (c == null) {
            try {
                c = findClass(name);
            } catch (ClassNotFoundException absent) {
                c = super.loadClass(name, false);
            }
        }

        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
~~~

Đoạn này là **method trong ClassLoader subclass có findClass phù hợp**, không phải chương trình độc lập.

Nó bảo đảm những yếu tố quan trọng:

- Shared APIs không bị child-first do prefix hạn chế.
- **findLoadedClass** tránh định nghĩa trùng đã initiate.
- **getClassLoadingLock(name)** quản lý concurrent requests.
- **findClass** được dùng cho class nội bộ.
- Chỉ fallback khi không tìm thấy bằng **ClassNotFoundException**; không bắt/nuốt **LinkageError**.
- **resolveClass** được gọi khi resolve=true.

Không mở rộng điều kiện child-first sang **java.*** hoặc mọi package của ứng dụng mà không có thiết kế type boundary, sealing và module rules. Đồng thời, đoạn code này không phải sandbox bảo mật.

### 10.3 Parallel-capable loaders

JDK cung cấp **registerAsParallelCapable()** và **getClassLoadingLock(name)** để hỗ trợ tải song song các tên class khác nhau.

Nếu subclass chưa đăng ký parallel capable theo quy tắc API, lock có thể là chính object loader, làm giảm concurrency nhưng vẫn giữ correctness khi thuật toán dùng lock đúng.

Nếu một runtime có loader graph phi cây hoặc nhiều loaders gọi chéo, cần phân tích **loading deadlock**; bỏ synchronized để “tránh nghẽn” có thể gây race/duplicate define nghiêm trọng hơn.

## 11. Chẩn đoán từ stack trace: xem những gì?

### 11.1 Tìm thông tin định danh loader

Một lỗi loader constraint có thể nhắc tới:

~~~text
loader constraint violation ...
class loader X for class/interface A ...
class loader Y for class/interface B ...
different Class objects for type api.Payload ...
~~~

Trong thông báo JVM thường kèm **module**, **unnamed module**, **parent loader**, tên class hoặc phương thức liên quan. Đừng bỏ phần này khi ghi issue/report.

Một loader custom nên có **tên/định danh** hữu ích khi debug. Ở Java 9+, một số constructor ClassLoader hỗ trợ tên; hoặc override toString có kiểm soát để phân biệt plugin versions.

### 11.2 In Class và defining loaders

Trong method có các biến clazzA, clazzB:

~~~java
System.out.println(clazzA.getName());
System.out.println(clazzA.getClassLoader());
System.out.println(clazzA.getModule());

System.out.println(clazzB.getName());
System.out.println(clazzB.getClassLoader());
System.out.println(clazzB.getModule());

System.out.println(clazzA == clazzB);
~~~

Đây là snippet minh họa, cần có hai Class objects. **Class.getClassLoader() có thể trả null** cho class do bootstrap loader định nghĩa; đừng gọi .toString() trực tiếp nếu chưa kiểm tra null.

**Không chỉ so tên string.** Hai Class có cùng getName() nhưng Class objects khác sẽ chỉ ra defining loaders hoặc identity khác.

### 11.3 Kiểm tra class files có thật sự từ nguồn mong đợi?

Với JDK toolchain:

~~~bash
javap -verbose -classpath host-out api.Payload
javap -verbose -classpath child-out api.Payload
~~~

Hai lệnh này hiển thị thông tin classfile ở **hai artifact roots**, không chứng minh JVM đã chọn nguồn nào trong runtime. Kết hợp với **getClassLoader()**, logs và code loader.

Kiểm tra archive:

~~~bash
jar --list --file plugin.jar
~~~

Nếu cùng API class xuất hiện trong host JAR và plugin JAR, đó là tín hiệu cần đánh giá package ownership, không phải bằng chứng tự động gây LinkageError.

### 11.4 JVM Unified Logging

Trên HotSpot/JVM hỗ trợ:

~~~bash
java -Xlog:class+load=info -cp demo-out:host-out ConstraintDemo
java -Xlog:help
~~~

Windows thay classpath separator bằng **;**. Logging class loading có thể giúp biết class nào được nạp, từ nguồn nào và ở giai đoạn nào, nhưng thông tin chi tiết phụ thuộc JVM/version. Không suy ra initiating loader hoàn toàn từ một dòng log chung; cần xét stack trace và Class objects.

### 11.5 Thread dump khi lỗi xảy ra khi chạy song song

Nếu duplicate do race, lỗi có thể chỉ xuất hiện dưới tải. Kiểm tra:

- Có thread nào vào cùng **findClass/defineClass** với cùng name không?
- Custom **loadClass** có khóa trên **getClassLoadingLock(name)** không?
- **findLoadedClass** có được gọi dưới lock không?
- Loader có phải parallel capable không?
- Một class có bị nạp đồng thời từ nhiều call paths khác nhau?
- Có cycle parent/child/peer delegation làm deadlock không?

Không dùng try/catch LinkageError để che race. Đó là triệu chứng thiết kế cần sửa.

## 12. Cách đọc thời điểm ném loader constraint violation

JVMS cho phép JVM trì hoãn một số bước resolution. Vì vậy:

~~~text
child.defineClass("impl.Impl", bytes)
          |
          v
Class object được tạo thành công
          |
          v
Reflection newInstance / method resolution
          |
          v
JVM liên kết method interface/superclass
          |
          v
Phát hiện api.Payload^AppLoader != api.Payload^ChildLoader
          |
          v
LinkageError: loader constraint violation
~~~

Ví dụ 2 quan sát đúng tình huống này trên OpenJDK 21.

Một số chương trình có thể ném sớm hơn, ví dụ trong preparation, hoặc muộn hơn khi symbolic reference liên quan được resolve. Khi lỗi xuất hiện ở dòng **newInstance()**, không có nghĩa constructor Java của Impl là nguyên nhân trực tiếp. JVM có thể đang làm bước liên kết cần thiết **trước khi constructor chạy**.

**Không dựa vào exact line number để kết luận.** Lấy stack trace, classloader ownership, class signature và JVMS loading constraint rules làm cơ sở.

## 13. Những giải pháp sai thường gặp

### 13.1 Catch LinkageError rồi dùng class khác

Không nên làm điều này như luồng bình thường:

~~~java
try {
    return customLoader.loadClass(name);
} catch (LinkageError ignored) {
    return parent.loadClass(name);
}
~~~

Đây là snippet **phản ví dụ** có biến customLoader/name/parent giả định. Nếu JVM đã thiết lập loading constraint hoặc có định nghĩa trùng, bỏ qua lỗi và tiếp tục trả một Class khác có thể làm application state/type consistency khó dự đoán.

**Đúng hơn:** thiết kế delegation trước khi định nghĩa class. Fallback chỉ nên xử lý **ClassNotFoundException** theo policy, không coi LinkageError là “không tìm thấy class”.

### 13.2 Đổi binary name nhưng vẫn giữ shared signature cũ

Đổi **api.Payload** của child thành một tên khác có thể né trùng tên, nhưng nếu plugin vẫn phải implements **Api.echo(api.Payload)** của host, signature phải dùng **chính host api.Payload**. Không thể sửa type mismatch chỉ bằng rename implementation hoặc ép cast không kiểm soát.

### 13.3 Đổi TCCL và mong sửa Class identity

**Thread Context ClassLoader** chỉ thay lookup context cho các API sử dụng nó. Nó không biến two runtime Class objects thành one Class. Cần kiểm tra **defining loader** thực tế và type boundary.

### 13.4 Xóa class file khỏi JAR khi Class đã nạp

Thay đổi artifact trên disk không hủy Class object đã tồn tại, không reset initiated-loader records. Khi cần nâng bản plugin, tạo loader mới và chuyển lifecycle, không trông chờ JVM tự quên định nghĩa cũ.

### 13.5 Bỏ khóa để “hết LinkageError do race”

Làm vậy dễ tăng xác suất duplicate definition. Cần atomicity trên **check/load/define** bằng khóa đúng và không thao tác defineClass cùng tên từ nhiều code paths.

### 13.6 Parent-first tuyệt đối cho mọi package mà không hiểu phiên bản

Parent-first là mặc định tốt cho **shared API**, nhưng nếu parent và child có implementation cùng tên và cần isolation, parent-first có thể trả bản sai. Dùng **selective child-first cho package nội bộ**, parent-first cho shared contracts.

## 14. Checklist khắc phục trong hệ plugin

Khi nhận lỗi LinkageError liên quan ClassLoader, kiểm tra theo trình tự:

1. **Đọc exact exception class và message.** Phân loại duplicate hay loading constraint; không trộn với ClassCastException.
2. **Ghi lại binary name và loaders được nhắc tới.** Bao gồm plugin version, module, parent chain.
3. **Nếu duplicate:** tìm nơi defineClass được gọi lặp; xem custom loadClass có findLoadedClass và loading lock chưa.
4. **Nếu constraint:** tìm method/field descriptor chứa type được JVM nêu (ví dụ api.Payload).
5. Xác nhận host và plugin đang dùng **cùng hay khác Class object** cho shared type đó.
6. Kiểm tra JAR/dependency graph có hai bản shared API/DTO bị đưa vào child không.
7. Chọn một loader làm **owner** của shared contracts; để child delegate chính xác tới owner.
8. Nếu cần isolation, giới hạn child-first vào internal implementation packages.
9. Kiểm tra kiểu package-private, module exports/opens và loader constraints ở boundary.
10. Rebuild artifact với cấu trúc classpath/module path đúng; không chỉ sửa code loader mà bỏ quên duplicate dependencies.
11. Test concurrency và hot redeploy nhiều vòng; xác nhận loader cũ được unregister và không bị thread/caches giữ.
12. Giữ bài test regression kiểm tra **a == b** cho types phải chia sẻ và **a != b** cho isolated implementations được kỳ vọng.

### 14.1 Dấu hiệu sửa đúng

Một hệ host/plugin đúng thường có:

~~~text
Host loader
   |
   +-- api.Service
   +-- api.Payload
   |
   +-- Plugin loader
           |
           +-- plugin.internal.PluginImpl
           |
           +-- khi cần api.Service/api.Payload:
               delegate tới Host loader
~~~

Method signature **Api.echo(Payload)** ở host và implementation plugin cùng nhìn thấy Class api.Payload do host define. Từ đó loading constraints được thỏa mãn.

Những packages implementation khác có thể vẫn được plugin loader định nghĩa riêng. Đây là thiết kế cho phép isolation có chủ đích **mà không phá type safety**.

## 15. Đối chiếu với các lỗi có vẻ giống

### 15.1 LinkageError duplicate vs ClassCircularityError

**ClassCircularityError** xuất hiện khi JVM phát hiện vòng trong quan hệ class hierarchy, chẳng hạn class cố kế thừa chính nó qua bytecode bất hợp lệ. Nó thuộc nhóm LinkageError nhưng **không phải duplicate definition**.

### 15.2 NoSuchMethodError sau khi thay JAR

Đây thường là binary compatibility issue: compile-time API và runtime API không khớp. Nó có thể liên quan classpath/classloader selection nhưng không đồng nghĩa JVM áp đặt loading constraint và thấy hai Class khác nhau.

### 15.3 NoClassDefFoundError và ClassNotFoundException

**ClassNotFoundException** là checked exception từ explicit lookup; **NoClassDefFoundError** có thể xuất hiện khi JVM cần một class trong linking/runtime execution mà định nghĩa không khả dụng hoặc trước đó initialization thất bại. Việc thiếu một class cũng có thể do loader policy, nhưng cần đọc cause thay vì mặc định “duplicate class”.

### 15.4 ClassCastException: cùng tên nhưng khác loader

~~~text
class plugin.Dto cannot be cast to class plugin.Dto
~~~

Có thể thấy hai tên giống hệt, nhưng message thường có loader/module details. Đây là type mismatch tại cast, không nhất thiết loader constraint violation. Dùng **getClassLoader** và Class identity kiểm tra.

### 15.5 IllegalAccessError với package giống nhau

Hai classes có cùng source package nhưng do loaders khác nhau define có thể không cùng runtime package. Package-private access có thể thất bại. Đây là vấn đề runtime package/module access, không phải attempted duplicate definition.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Loader L gọi defineClass("demo.Token", bytes) hai lần. Lần hai có được coi là cập nhật class cũ không?

**Đáp án:** Không. Đó là duplicate definition và có thể ném LinkageError. Muốn bản mới cần loader mới hoặc instrumentation theo giới hạn riêng.

**Câu 2.** Loader L1 và L2 đều define demo.Token. Chỉ riêng chuyện đó có bắt buộc lỗi không?

**Đáp án:** Không. Hai runtime Class khác nhau có thể cùng tồn tại nếu không có constraint buộc phải đồng nhất.

**Câu 3.** Defining loader và initiating loader có luôn là một không?

**Đáp án:** Không. Child có thể initiate class được parent define qua delegation.

**Câu 4.** Loading constraint ký hiệu N^L1=N^L2 có yêu cầu mọi classes của hai loaders giống nhau không?

**Đáp án:** Không. Nó ràng buộc một tên type N cụ thể trong những quan hệ linking được JVM áp đặt.

**Câu 5.** Vì sao interface Api.echo(api.Payload) có thể gây constraint khi Impl ở child loader?

**Đáp án:** JVM cần type api.Payload trong method descriptor có một identity nhất quán giữa interface và implementation. Nếu child dùng một Class api.Payload riêng, ràng buộc có thể bị vi phạm.

**Câu 6.** LinkageError có phải luôn ném ngay ở defineClass không?

**Đáp án:** Không. Có trường hợp lỗi xuất hiện khi preparation/resolution hoặc bước liên kết tương ứng sau đó. Ví dụ 2 thấy lỗi lúc tạo instance.

**Câu 7.** Vì sao bản safe của ví dụ 2 chạy được?

**Đáp án:** Loader safe không định nghĩa api.Payload riêng; nó dùng cùng shared Payload Class từ parent.

**Câu 8.** Có nên catch LinkageError rồi fallback parent như ClassNotFoundException không?

**Đáp án:** Không. LinkageError biểu thị lỗi linking/consistency, cần sửa classloader policy, duplicate definitions hoặc artifacts.

**Câu 9.** Nếu a.getName().equals(b.getName()) true nhưng a==b false, đây có phải trực tiếp là loading constraint violation?

**Đáp án:** Chưa. Đó chỉ cho thấy hai Class identities khác nhau. Loading constraint violation còn đòi một ràng buộc JVM bắt chúng đồng nhất.

**Câu 10.** API interface và DTO dùng giữa host/plugin nên do loader nào define?

**Đáp án:** Thường do một loader parent/shared được cả hai sử dụng; implementation nội bộ được plugin loader define riêng.

**Câu 11.** Race duplicate definition thường đến từ thiếu thao tác nào?

**Đáp án:** Thiếu phối hợp findLoadedClass và getClassLoadingLock(name) trong toàn bộ đường check/load/define.

**Câu 12.** Vì sao đổi classpath JAR mà không tạo loader mới có thể vẫn nhận bản cũ?

**Đáp án:** Class đã được JVM định nghĩa/initiate; loadClass có thể trả Class cũ. JVM không tự định nghĩa lại nó khi file trên đĩa đổi.

## 17. Tóm tắt

~~~text
Một tên class N được yêu cầu
       |
       v
Cùng loader cố define lại N đã biết?
       |
       +-- Có -> LinkageError (duplicate definition)
       |
       +-- Không
             |
             v
Hai loaders có hai Class khác cho N?
             |
             +-- Có nhưng không có constraint
             |        -> có thể hợp lệ (loader isolation)
             |
             +-- Có và JVM yêu cầu N^L1 = N^L2
                      -> LinkageError (constraint violation)
~~~

**Ba nguyên tắc quan trọng nhất:**

1. **Định nghĩa trùng trong cùng loader không phải reload**; bảo toàn cache/lock và tạo loader mới nếu cần runtime version mới.
2. **Hai loaders cùng tên class không tự sai**; sai khi JVM buộc các type trong một method/field boundary phải đồng nhất mà chúng khác Class identity.
3. **Dùng chung API/DTO từ một defining loader ổn định**, còn implementation có thể cô lập theo loader; kiểm tra bằng Class object và defining loader, không chỉ bằng tên chuỗi.

### Nguồn chuẩn để tra cứu sâu

- JVMS Java SE 21 **§5.3.4 Loading Constraints**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4
- JVMS Java SE 21 **§5.3.5 Deriving a Class from a class File Representation**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5
- JVMS Java SE 21 **§5.4.2 Preparation và §5.4.3 Resolution**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- JLS Java SE 21 **§12.2 Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- ClassLoader Java SE 21 API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- LinkageError Java SE 21 API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html
