# Quy tắc đặc tả, chi tiết HotSpot và khác biệt theo phiên bản JDK

> **Ngữ cảnh:** Java Core → ClassLoader → Mô hình tổng quan. Bài này phân biệt những điều **JVM/Java SE bắt buộc**, hành vi của **API `ClassLoader`**, những gì thường quan sát ở **OpenJDK/HotSpot**, và những điểm phải kiểm tra lại khi đổi phiên bản JDK.

## 1. Ba lớp quy tắc cần phân biệt

Một hiện tượng như “lớp A do loader nào nạp?”, “tại sao không ép kiểu được?” hay “vì sao JDK mới không tìm thấy class cũ?” có thể thuộc ba lớp:

| Lớp | Nguồn quy tắc | Có thể dựa vào điều gì? |
| --- | --- | --- |
| **JVM Specification (JVMS)** | Định nghĩa class, runtime identity, loading, linking, initialization, verification, access control, loading constraints | Quy tắc tương thích của một JVM tuân thủ đặc tả; không buộc JVM dùng cấu trúc dữ liệu nội bộ hay đúng thứ tự log của HotSpot |
| **Java SE API/JLS** | `java.lang.ClassLoader`, `Class`, `Module`; JLS §12 | Hợp đồng phương thức, điều kiện khởi tạo lớp, mô hình delegation mặc định của API và ngoại lệ được công bố |
| **Triển khai JDK/VM** | OpenJDK/HotSpot, launcher, module runtime image, diagnostic tools | Tên lớp loader cụ thể, tổ chức file JDK, cờ JVM, log, Metaspace/CDS, tốc độ và cấu trúc bộ nhớ; có thể đổi theo bản JDK/VM |

**Nguyên tắc:** Nếu muốn khẳng định “mọi JVM đều thế”, phải tìm căn cứ ở JVMS/JLS hoặc API chuẩn. Nếu khẳng định “trên HotSpot JDK 17/21/25 có thể quan sát”, hãy chỉ rõ phạm vi phiên bản và cách kiểm chứng.

## 2. Bất biến do JVMS quy định

### 2.1. Định danh của lớp không chỉ là tên

Với lớp thông thường, danh tính runtime được xác định bởi cặp:

`(binary name, defining class loader)`

Hai loader khác nhau cùng `defineClass` từ bytecode mang tên `example.Plugin` tạo ra **hai kiểu runtime khác nhau**, dù bytes giống nhau. Vì thế:

- `Class<?>` của hai kiểu không bằng nhau; không thể mặc nhiên cast đối tượng từ loader thứ nhất sang kiểu do loader thứ hai định nghĩa.
- “Cùng tên package” không tự động mang lại quyền truy cập package-private. Một **runtime package** được xác định bởi *tên package + defining loader*; modular access còn chịu sự kiểm tra module.
- Hai bản cùng tên có thể cùng tồn tại khi do hai defining loader khác nhau định nghĩa; một loader không được định nghĩa hai lần cùng binary name theo cùng cách đó. Việc định nghĩa trùng gây lỗi liên kết, ví dụ `LinkageError`.

**Defining loader** trực tiếp định nghĩa lớp; **initiating loader** là loader mà JVM ghi nhận đã khởi xướng thành công việc nạp lớp, có thể qua delegation. Hai vai trò không nhất thiết giống nhau. Không suy ra defining loader chỉ từ loader ban đầu nhận lời gọi `loadClass`.

### 2.2. Delegation mặc định không đồng nghĩa một luật parent-first bất biến

API `ClassLoader.loadClass(String, boolean)` mặc định làm theo thứ tự: kiểm tra `findLoadedClass` → thử parent (hoặc bootstrap khi không có parent) → gọi `findClass` nếu chưa tìm được → resolve khi được yêu cầu. Vì vậy sơ đồ parent-first rất hữu ích cho các loader dùng triển khai mặc định.

Tuy nhiên, JVMS cho phép loader do ứng dụng định nghĩa thực hiện việc tìm/ủy quyền theo cách thích hợp miễn tuân thủ ràng buộc nạp và liên kết. Một loader có thể **child-first có chọn lọc** để cô lập plugin. Không nên kết luận “mọi Java ClassLoader luôn parent-first”. Những tên class dùng chung cho giao diện xuyên ranh giới (API host/plugin, thư viện chia sẻ, lớp nền tảng) cần được thống nhất loader để tránh identity và linkage conflict.

Nếu viết loader tùy biến, cần:
1. Giữ tính nhất quán: mỗi tên đã nạp phải trả về đúng `Class` đó trong cùng loader.
2. Tuân thủ quy tắc khóa nạp đồng thời, `getClassLoadingLock` và `findLoadedClass`; chỉ đăng ký **parallel capable** nếu triển khai hỗ trợ.
3. Kiểm tra namespace được phép định nghĩa; JVM/API hạn chế định nghĩa lớp ở namespace như `java.*`.
4. Đừng đánh đồng “đọc được resource `.class`” với “có quyền định nghĩa hoặc truy cập kiểu” — module/export, chữ ký, package, bytecode verification và security/access rules vẫn được áp dụng.

### 2.3. Loading, linking và initialization là các giai đoạn khác nhau

| Giai đoạn | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **Loading** | Tìm biểu diễn nhị phân và tạo lớp (hoặc JVM tạo array class) | Chưa mặc nhiên chạy `static{}` hay static field initializer |
| **Verification** (linking) | Kiểm tra tính hợp lệ/type-safety của bytecode | Dữ liệu class file sai có thể gây `VerifyError` hoặc dạng `LinkageError` |
| **Preparation** (linking) | Tạo static fields và gán giá trị mặc định | Không chạy các initializer Java; có ngoại lệ hằng `ConstantValue` do đặc tả quy định |
| **Resolution** (linking) | Biến symbolic references thành tham chiếu runtime kèm kiểm tra access/loading constraints | Có thể thực hiện lười hoặc sớm, trong giới hạn thời điểm lỗi theo JVMS |
| **Initialization** | Thực thi `<clinit>`, static initializer và các phép gán static theo thứ tự đặc tả | Kích hoạt bởi các hành động active use được JLS/JVMS liệt kê; mỗi lớp khởi tạo nhiều nhất một lần cho mỗi identity |

Câu “class được load” **không chứng minh class đã initialize**. `ClassLoader.loadClass(name)` thông thường chỉ yêu cầu loading; `Class.forName(name, true, loader)` yêu cầu khởi tạo. Ngược lại, `Class.forName(name, false, loader)` không yêu cầu khởi tạo. Sự thật class đã được initialize hay chưa phải xét theo identity chính xác (tên + defining loader), không chỉ theo tên.

### 2.4. Type safety, loading constraints và các lỗi liên quan

JVM áp đặt **loading constraints** khi các kiểu ở những loader khác nhau giao tiếp qua superclass, method/field descriptor, v.v. Nếu cùng tên kiểu buộc phải biểu thị cùng một runtime type mà hai loader lại dẫn tới các lớp khác nhau, JVM có thể ném `LinkageError`. Mục tiêu là tránh một lời gọi phương thức truyền đối tượng với kiểu thực khác kiểu mà bên nhận giả định.

Những lỗi thường bị nhầm:

| Tình huống | Biểu hiện điển hình | Cách hiểu đúng |
| --- | --- | --- |
| Gọi `loadClass`/`Class.forName` bằng tên không tìm thấy | `ClassNotFoundException` (checked) | Không tìm thấy lớp theo loader/đường nạp được yêu cầu |
| Bytecode đang thực thi tham chiếu lớp có lúc build nhưng runtime không giải quyết được | `NoClassDefFoundError` | Lỗi liên kết kiểu runtime; cũng có thể xảy ra sau lần khởi tạo lớp thất bại |
| Class file mới hơn mức VM hỗ trợ | `UnsupportedClassVersionError` | Không phải thiếu class; là **định dạng/version bytecode** không hỗ trợ |
| Thiếu method/field lúc runtime do lệch binary dependency | `NoSuchMethodError` / `NoSuchFieldError` | Binary incompatibility; kiểm tra classpath/module path và bản JAR thực được nạp |
| Vi phạm access khi resolution | `IllegalAccessError` | Khác với lỗi reflective access như `InaccessibleObjectException` |
| Hai loader định nghĩa cùng tên nhưng đối tượng bị ép sang kiểu phía kia | `ClassCastException`, có thể chứa mô tả loader | Hai `Class` có identity khác; tên trùng không làm chúng tương thích |
| `static{}` ném exception khi khởi tạo | Thường là `ExceptionInInitializerError`; lần dùng sau có thể `NoClassDefFoundError` | Phải tìm nguyên nhân lỗi *đầu tiên* trong log, không chỉ lỗi theo sau |

Đặc tả quy định loại điều kiện lỗi và những thời điểm hợp lệ; **thứ tự log, tên class nội bộ, stack trace chính xác, thông báo lỗi** không phải giao diện ổn định để mã nghiệp vụ phụ thuộc.

### 2.5. Array class và primitive

JVM tạo array class trực tiếp; không đọc một file `[Lexample/Foo;.class`. Array có component là reference type thì defining loader tương ứng defining loader của component type; array của primitive được gắn với bootstrap loader. Vì thế `int[].class.getClassLoader()` trả về `null`; `Foo[].class.getClassLoader()` đi theo loader định nghĩa `Foo`. Đây là quy tắc JVMS, không phải một tối ưu riêng HotSpot.

## 3. Hệ phân cấp loader: hợp đồng API và cách JDK triển khai

Với JDK 9+, mô hình phổ biến có thể biểu diễn:

~~~text
Bootstrap (VM built-in; Java reflection thường hiển thị null)
    ↑
Platform loader (ClassLoader.getPlatformClassLoader())
    ↑
Application/System loader (ClassLoader.getSystemClassLoader())
    ↑
Custom loaders (nếu ứng dụng/framework tạo)
~~~

Sơ đồ là **mô hình giảng dạy**, không phải khẳng định mọi class luôn đi qua toàn bộ các nút. API tài liệu hóa rằng platform loader có thể phải ủy quyền tới loader khác khi xử lý một số module được upgrade; lớp trong module có thể được gắn với những loader khác nhau. Loader hierarchy và JPMS readability/export/access là **hai trục kiểm soát khác nhau**.

- **Bootstrap:** loader nội tại VM; trong API `Class.getClassLoader()` thường biểu diễn bằng `null`. `null` không phải lỗi và không có nghĩa class chưa được nạp.
- **Platform:** tải nhiều lớp nền tảng/JDK; JDK 9+ cung cấp `getPlatformClassLoader()`. Không đồng nhất mọi class `java.*` với platform loader: nhiều lớp lõi thuộc bootstrap.
- **Application/System:** thường tải mã trên class path và một số module; giá trị cụ thể có thể bị tùy chỉnh qua cơ chế system loader. Trên JDK 9+, **đừng cast system loader sang `URLClassLoader`**; API không hứa kiểu triển khai đó.
- **Custom:** loader plugin, container, app server, hot-reload, module layer. Có parent nhưng parent không đồng nghĩa owner của mọi lớp và không tự giải quyết xung đột class/resource.

Mã kiểm chứng trong một ứng dụng đơn giản chạy trên **class path** của JDK 17+:

~~~java
public class LoaderFacts {
    public static void main(String[] args) {
        System.out.println(String.class.getClassLoader() == null);
        System.out.println(
                LoaderFacts.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader());
        System.out.println(LoaderFacts.class.getModule().isNamed());
        System.out.println(Object.class.getModule().getName());
    }
}
~~~

~~~bash
javac LoaderFacts.java
java -cp . LoaderFacts
~~~

`stdout` trong điều kiện trên:

~~~text
true
true
false
java.base
~~~

Kết quả thứ hai/ba là của cách khởi động **class path cơ bản**, không phải một bất biến của mọi custom runtime hoặc module layer. `java.base` là tên module chuẩn chứa `java.lang.Object`.

## 4. Hai thí nghiệm phân biệt loading/initialization và class identity

### 4.1. Loading không tự chạy static initializer

Tệp **`InitBoundary.java`** (Java 17+):

~~~java
public class InitBoundary {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = InitBoundary.class.getClassLoader();
        System.out.println("1. before load");
        loader.loadClass(Target.class.getName());
        System.out.println("2. after load");
        Class.forName(Target.class.getName(), true, loader);
        System.out.println("3. after initialization");
    }
}
~~~

~~~bash
javac InitBoundary.java
java InitBoundary
~~~

`stdout`:

~~~text
1. before load
2. after load
Target initialized
3. after initialization
~~~

`Target.class` chỉ lấy đối tượng `Class` mà không kích hoạt initialization; `loadClass` không yêu cầu initialization; lời gọi `Class.forName` với tham số `initialize=true` buộc khởi tạo nên dòng trong `static{}` xuất hiện giữa hai dấu mốc. Thử chạy lại trong *một JVM mới* để lặp lại trạng thái ban đầu; gọi lần nữa trong cùng JVM sẽ không chạy lại `static{}`.

### 4.2. Cùng binary name qua hai defining loader vẫn là hai kiểu

Tệp **`IdentityBoundary.java`** (Java 17+, chỉ minh họa việc override đúng một tên lớp; không dùng nguyên loader này trong production):

~~~java
import java.io.IOException;
import java.io.InputStream;

public class IdentityBoundary {
    static class Token {}

    private static final String TARGET = Token.class.getName();

    static final class Isolated extends ClassLoader {
        Isolated() {
            super(IdentityBoundary.class.getClassLoader());
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(TARGET)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = findClass(name);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(TARGET)) {
                throw new ClassNotFoundException(name);
            }
            String resource = name.replace('.', '/') + ".class";
            try (InputStream in = IdentityBoundary.class
                    .getClassLoader().getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> left = new Isolated().loadClass(TARGET);
        Class<?> right = new Isolated().loadClass(TARGET);

        System.out.println(left.getName().equals(right.getName()));
        System.out.println(left == right);
        System.out.println(
                left.getClassLoader() == right.getClassLoader());
        System.out.println(left == Token.class);
    }
}
~~~

~~~bash
javac IdentityBoundary.java
java IdentityBoundary
~~~

`stdout`:

~~~text
true
false
false
false
~~~

Giải thích: hai `Isolated` riêng biệt đọc cùng file class của `Token`, rồi mỗi loader gọi `defineClass`. Cùng tên trả về `true`; class identity và loader instance không giống nhau. `Token.class` từ loader ứng dụng là một kiểu thứ ba. Đoạn override chỉ xử lý lớp đích để giữ nguyên delegation cho JDK classes và các dependency khác; khi thiết kế plugin thực tế cần chính sách namespace, giải quyết dependency, bảo mật và vòng đời nghiêm ngặt.

**Không suy luận sai:** khác loader không tự động gây `ClassCastException`. Chỉ khi thực hiện một thao tác đòi hai đối tượng `Class` tương thích (cast, assign, reflection, method linkage...) mới có lỗi phù hợp. Và nếu custom loader **delegates** thì nhiều loader có thể trả về *cùng một* `Class` do parent định nghĩa.

## 5. ClassLoader gặp Java Platform Module System (JPMS)

Từ JDK 9, một module có thể đặt trong **module layer** và được gán loader; một loader có thể chứa nhiều module. Đây không phải ánh xạ module ↔ loader 1–1. Khả năng nạp được bytecode khác với khả năng **truy cập** type: JPMS còn xét readability, `exports` (truy cập API công khai) và `opens` (deep reflection theo quy tắc). Một class hiện diện trong runtime image nhưng không đọc/truy cập hợp lệ từ module gọi vẫn không thể được sử dụng như lớp công khai tùy ý.

Ví dụ tổng quát:

- `ClassLoader.loadClass("pkg.Hidden")` có thể trả về một `Class`, nhưng phép truy cập sau đó vẫn có thể thất bại vì module/package access.
- `--add-exports module/pkg=target` có thể mở quyền truy cập public type ở package không export; `--add-opens module/pkg=target` phục vụ deep reflection. Dùng có mục tiêu để tương thích/migrate, không xem là cách sửa dài hạn thay cho API công khai.
- `Thread.currentThread().getContextClassLoader()` (**TCCL**) cho thư viện/framework khả năng tra cứu provider trong ngữ cảnh caller, thường liên quan `ServiceLoader`, SPI, container và plugin. TCCL không phải “defining loader của thread”; cần đặt, khôi phục trong `finally` và tránh giữ reference đến plugin loader khi hot-reload.
- Resource lookup qua `getResource` / `getResources` có cơ chế delegation riêng và có thể chịu **encapsulation của module**; sự tồn tại của tài nguyên trên disk/JAR không bảo đảm mọi loader đều trả về URL của nó.
- Một multi-release JAR (`Multi-Release: true`) có thể có bytecode khác nhau dưới `META-INF/versions/N`. Runtime có thể chọn biến thể thích hợp cho phiên bản Java đang chạy. Vì vậy “cùng tên JAR” vẫn có thể cho class thực tế khác tùy JDK.

Không thay thế kiểm tra module graph bằng cây parent loader; đây là hai câu hỏi khác nhau: **ai định nghĩa kiểu?** và **ai được đọc/truy cập kiểu?**

## 6. HotSpot: những điều thường thấy nhưng không nên coi là luật JVMS

### 6.1. Nguồn class và cấu trúc runtime

- Trên **JDK 8**, các class JDK thường nằm trong `rt.jar` và extension mechanism; nhiều ứng dụng có thể gặp `ExtClassLoader` / `AppClassLoader` trong tên triển khai.
- Từ **JDK 9**, runtime image sử dụng module system và tài nguyên hệ thống có thể xuất hiện với scheme `jrt:/`. Extension loader trở thành **platform loader**, ứng dụng không được giả định system loader là `URLClassLoader` hoặc `java.home/lib/rt.jar` tồn tại.
- HotSpot lưu class metadata trong **Metaspace** (từ JDK 8; thay PermGen). Metaspace là chi tiết quản lý bộ nhớ của HotSpot; JVMS mô tả method area nhưng không bắt mọi JVM phải bố trí kiểu “Metaspace” giống HotSpot.
- HotSpot có thể sử dụng Class Data Sharing (CDS), archived classes, lazy resolution, tối ưu nạp/link tùy build và cấu hình; không suy ra từ log “source” rằng class luôn đọc từng byte trực tiếp từ đúng đường dẫn đó.
- Class unloading liên quan khả năng reclaim của loader/class và GC, không tự động xảy ra ngay khi gọi `URLClassLoader.close()`. `close()` giải phóng các handle/tài nguyên có thể đóng; class và loader còn bị tham chiếu thì chưa được giải phóng.

### 6.2. Chẩn đoán dựa trên công cụ, không dựa vào tên nội bộ

Các lệnh ví dụ dành cho **OpenJDK/HotSpot trên JDK 17+**; phiên bản khác có thể có tên option hoặc số lượng thông tin khác:

~~~bash
# In quá trình class loading (log có thể rất dài).
java -Xlog:class+load=info InitBoundary

# Thấy cả sự kiện class unloading (nếu GC thực sự unload).
java -Xlog:class+load=info,class+unload=info InitBoundary

# Cú pháp tương thích có từ JDK cũ, ít chi tiết/chỉnh lọc hơn.
java -verbose:class InitBoundary

# Chạy với PID của tiến trình Java còn sống, nếu jcmd attach được.
jcmd <pid> VM.classloaders
jcmd <pid> VM.classloader_stats
~~~

Các lệnh `jcmd` phụ thuộc JVM đích, quyền attach, môi trường container và danh sách diagnostic commands mà VM hỗ trợ; chạy `jcmd <pid> help` để xác nhận lệnh thực có. `VM.classloaders` hữu ích để thấy hierarchy, `VM.classloader_stats` để xem thống kê, nhưng **không** là hợp đồng đầu ra chuẩn của ngôn ngữ Java.

Khi điều tra sự cố, hãy ghi cùng lúc `java -version`, nhà phân phối JDK, cách chạy trên classpath/module path, tập JAR và dòng lệnh JVM. Đầu ra log thay đổi theo JDK, bật thêm log có thể ảnh hưởng performance; không nên parse bằng regex phụ thuộc tên `jdk.internal.loader.ClassLoaders$AppClassLoader`.

### 6.3. Vòng đời loader và lỗi memory leak ở container/plugin

Khả năng unload class phụ thuộc việc không còn các tham chiếu giữ loader/class có thể thu hồi; một GC cycle cũng không bảo đảm unload xảy ra đúng lúc. Nguồn giữ reference thường gặp: static registry của host, `ThreadLocal`, thread sống lâu, thread context class loader, executor/scheduler, listener, JMX, callback và cache giữ `Class`/`Method`. Khi reload plugin:

1. Dừng tác vụ và thread do plugin sở hữu; hủy listener/registration.
2. Khôi phục TCCL sau khi dùng và dọn `ThreadLocal`/cache chứa object hoặc class plugin.
3. Đóng `URLClassLoader`/resource nếu có; sau đó bỏ strong reference đến loader, instance và class.
4. Theo dõi loader/class count, GC và Metaspace sau nhiều chu kỳ reload; dùng công cụ phù hợp với phiên bản HotSpot.

Đừng dùng mỗi số MB Metaspace tăng trong một lần đo để kết luận leak: cần quan sát xu hướng qua nhiều lần GC/reload và phân biệt cơ chế cache/commit memory của VM.

## 7. Những khác biệt quan trọng theo JDK

| Phiên bản | Khác biệt cần nhớ khi học/triển khai ClassLoader | Class file major phổ biến |
| --- | --- | ---: |
| **JDK 8** | Trước JPMS; nhiều cấu hình classpath/`rt.jar`/extension dirs; PermGen đã thay bằng Metaspace trên HotSpot | **52** |
| **JDK 9** | JPMS (`module-info.java`, module path, layer); loader **platform** thay extension; runtime image modular, `jrt:/`; system loader không còn được giả định là `URLClassLoader`; unified logging `-Xlog` | **53** |
| **JDK 11** | Loại khỏi JDK các module Java EE/CORBA được liệt kê trong JEP 320; ứng dụng cũ có thể gặp class missing dù loader vẫn hoạt động đúng | **55** |
| **JDK 15** | **Hidden classes** (JEP 371), dùng cho runtime/framework động; tên `Class.getName()` của hidden class không nhất thiết là binary name thông thường; không suy ra có thể nạp lại bằng `Class.forName` | **59** |
| **JDK 17** | Strong encapsulation của JDK internals (JEP 403); `--illegal-access` không còn hiệu lực mở rộng như trước; reflection có thể gặp `InaccessibleObjectException` | **61** |
| **JDK 21** | Các quy tắc nòng cốt của JVMS về class identity/loading vẫn áp dụng; kiểm tra lại công cụ HotSpot, module configuration và version class file khi nâng cấp | **65** |
| **JDK 25** | Tiếp tục các ranh giới JVMS/JPMS; không dựa vào tên loader nội bộ, option VM hoặc log của JDK 8/11 làm hợp đồng lâu dài | **69** |
| **JDK 26** | Class file major tăng theo release; chương trình biên dịch bằng target mặc định của JDK mới có thể không chạy trên runtime cũ | **70** |

**Phân biệt version:** phiên bản **Java source**, class file target của `javac --release N` và **runtime JVM** là ba thông tin khác nhau. Ví dụ ứng dụng chạy bằng JDK 17 nhưng nạp file `major=65` được biên dịch cho Java 21 có thể nhận `UnsupportedClassVersionError`. Giảm `--release` chỉ giải quyết target bytecode và API được phép ở compile time; không sửa được những API bên thứ ba đòi JDK cao hơn hoặc semantic khác do JPMS, reflection, loader tùy biến.

Lệnh kiểm tra:

~~~bash
java -version
javac -version
javap -verbose LoaderFacts
~~~

Trong đầu ra `javap -verbose`, tìm dòng `major version`. Khi kiểm tra JAR chứa nhiều bản class, xác định entry thực được chọn (kể cả multi-release JAR) trước khi kết luận.

### 7.1. Ví dụ nâng cấp JDK 8 → 17/21/25: thay đổi thuộc lớp nào?

**Trường hợp A — mã cũ cast system loader:**

~~~java
// Dễ chạy trên một số môi trường JDK 8; không phải API contract.
java.net.URLClassLoader loader =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

Trên nhiều JDK 9+ HotSpot, cast này dẫn tới `ClassCastException`. Sửa đúng là dùng API `ClassLoader`/`getResource` khi chỉ cần tải resource, hoặc tự quản lý một `URLClassLoader` do ứng dụng tạo nếu thật sự cần chỉnh URL. Không kiểm tra bằng việc ép kiểu loader nội bộ.

**Trường hợp B — truy cập `sun.*`/`jdk.internal.*` bằng reflection:** JDK 17+ có thể chặn theo module encapsulation mặc định. Đây chủ yếu là giới hạn JPMS/runtime access, không phải parent loader “quên tải” class. Ưu tiên API được hỗ trợ; chỉ dùng `--add-opens`/`--add-exports` cho gói cụ thể khi đang chuyển đổi dependency.

**Trường hợp C — thiếu `javax.xml.bind` khi lên JDK 11+:** Java EE/CORBA modules đã bị loại khỏi JDK. Phải thêm dependency tương thích và cân nhắc namespace/phiên bản đúng; tạo child-first loader không tự đưa API đã bị loại trở lại.

**Trường hợp D — plugin có hai bản thư viện:** một plugin load cùng FQCN nhưng loader khác với API host. Cast hoặc linkage có thể thất bại. Đặt interface được chia sẻ dưới parent/loader thống nhất; chọn rõ package nào delegated, package nào isolated; kiểm tra dependency transitive và TCCL.

## 8. Quy trình điều tra khi thấy lỗi liên quan ClassLoader

1. **Nhận diện lỗi đầu tiên:** lấy đầy đủ exception/cause/stack trace, phân biệt checked `ClassNotFoundException` với `LinkageError`, `ClassCastException`, `InaccessibleObjectException`.
2. **Xác định context runtime:** `java -version`, VM vendor, flags, launch classpath/module path, module layer, class file major.
3. **Kiểm tra nơi class được định nghĩa:** `clazz.getName()`, `clazz.getClassLoader()`, `clazz.getModule()`, đường resource/code source khi hợp lệ; tránh in thông tin nhạy cảm từ môi trường production.
4. **Kiểm tra bản dependency thực sự được chọn:** JAR trùng lặp, version mediation, shaded package, multi-release entries, classpath/module path và classload order.
5. **Tách vấn đề “tìm” khỏi vấn đề “truy cập”:** class không tồn tại/không giải được, module không readable/exported/open, package bị sealed, bytecode quá mới hay loader có identity khác?
6. **Tái hiện tối thiểu:** một file Java hoặc một plugin nhỏ với cùng kiểu loader; so sánh cùng workload trên phiên bản JDK đang cần hỗ trợ.
7. **Dùng diagnostics có giới hạn:** `-Xlog:class+load` hoặc `jcmd` nếu có; xác nhận lại bằng API và đặc tả, vì log/tên class HotSpot không phải API ổn định.

### Checklist tự kiểm chứng kiến thức

- Nếu hai class cùng FQCN nhưng defining loader khác nhau, chúng có nhất thiết là một kiểu? **Không.**
- Nếu `ClassLoader.loadClass` chạy thành công, `static{}` chắc chắn đã chạy? **Không.**
- Nếu class ở runtime image, mọi module khác đều có thể reflective access? **Không.**
- Sơ đồ parent-first là thuật toán duy nhất mọi loader bắt buộc dùng? **Không.**
- `String.class.getClassLoader() == null` trên HotSpot có phải lỗi? **Không**, đó là cách API biểu diễn bootstrap loader.
- `java -Xlog:class+load` và tên `AppClassLoader` là quy định JVMS? **Không**, đó là triển khai/công cụ của JDK/VM.
- `URLClassLoader.close()` có bảo đảm unload tức thì? **Không.**
- Một `NoClassDefFoundError` luôn nghĩa là file JAR bị thiếu? **Không**; cần truy nguyên linkage hoặc khởi tạo thất bại.

## 9. Tài liệu chuẩn để đối chiếu

1. [JVMS `5 — Loading, Linking, and Initializing (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html) — defining/initiating loader, class identity, loading constraints, runtime package, linking và initialization.
2. [`ClassLoader` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — delegation mặc định, built-in loaders, parallel capable, resource lookup.
3. [JLS §12 — Execution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html) — khởi tạo lớp và các tình huống active use.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261) — module/loader changes từ JDK 9.
5. [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320) — lý do class cũ không còn nằm trong JDK 11.
6. [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) — cơ chế class động đặc biệt từ JDK 15.
7. [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) — truy cập JDK internals từ JDK 17.
8. [`jcmd` tool (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — command `VM.classloaders` và `VM.classloader_stats`.
9. [JAR File Specification — Multi-release JAR](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) và [`ClassFile` versions (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFile.html) — khác biệt bytecode theo phiên bản.

**Điều cần giữ sau bài:** mỗi khi nói về ClassLoader, trước tiên xác định phát biểu nằm ở *đặc tả JVMS/JLS*, *hợp đồng API Java SE* hay *quan sát HotSpot trên JDK cụ thể*. Nhờ đó ta giải thích đúng lỗi tương thích, chọn hướng sửa có thể duy trì khi nâng cấp JDK và tránh dựa vào chi tiết triển khai không được bảo đảm.
