# Không gian tên, khả năng nhìn thấy và cô lập phụ thuộc trong Java ClassLoader

## 1. Vì sao cùng tên lớp chưa chắc là cùng kiểu?

Trong Java, `ClassLoader` vừa đưa định nghĩa lớp vào JVM, vừa tạo ranh giới **danh tính kiểu** (type identity). Điều này đặc biệt quan trọng khi chạy ứng dụng có plugin, container, hệ thống module hoặc nhiều phiên bản thư viện.

Một lớp ở thời điểm chạy được nhận diện về cơ bản bằng **cặp (tên nhị phân của lớp, class loader định nghĩa lớp đó)**. Ví dụ: `(com.example.dto.Order, LoaderA)` và `(com.example.dto.Order, LoaderB)` là **hai kiểu khác nhau**, dù bytecode hoặc mã nguồn giống hệt nhau. Vì vậy, một đối tượng thuộc kiểu thứ nhất không tự động ép kiểu được sang kiểu thứ hai.

Cần phân biệt ba thuật ngữ:

- **Binary name**: tên JVM dùng để tham chiếu, chẳng hạn `com.example.dto.Order`.
- **Defining loader**: loader thực sự định nghĩa lớp từ bytecode, thường qua `defineClass`. Đây là thành phần quyết định danh tính kiểu.
- **Initiating loader**: loader đã yêu cầu tải lớp và có thể nhận kết quả từ loader cha. Một lớp có thể có nhiều initiating loader nhưng chỉ một defining loader cho một định nghĩa cụ thể.

Do đó, gọi `child.loadClass("java.lang.String")` không có nghĩa `child` định nghĩa `String`; trong cơ chế ủy quyền thông thường, lớp này được trả về từ bootstrap loader.

### Hệ quả thực tế

| Tình huống | Ý nghĩa |
| --- | --- |
| Hai loader khác nhau tự định nghĩa `pkg.Foo` | Có hai kiểu `pkg.Foo` riêng biệt |
| Hai loader con cùng nhận `pkg.Api` từ loader cha | Dùng chung **một** kiểu `pkg.Api` |
| Cùng tên package nhưng lớp được định nghĩa bởi hai loader | Không tự động thuộc cùng **runtime package** |
| Hai plugin dùng hai phiên bản thư viện được tải riêng | Có thể cùng tồn tại nếu không rò kiểu riêng qua API chung |

**Ghi nhớ:** “Có thể tìm thấy file `.class`” và “có thể dùng lớp như cùng một kiểu” là hai câu hỏi khác nhau.

## 2. Không gian tên khi JVM giải quyết tham chiếu giữa các lớp

Khả năng **tìm thấy** một lớp, quyền **truy cập** lớp ấy, và khả năng **dùng chung định danh kiểu** là ba phép kiểm tra khác nhau. Một loader có thể yêu cầu lớp từ parent mà bản thân không định nghĩa lớp đó; `clazz.getClassLoader()` cho biết **defining loader**, còn `Thread.currentThread().getContextClassLoader()` là lựa chọn loader theo ngữ cảnh của một số API khám phá service.

Trong quá trình liên kết, JVM còn áp đặt **loading constraints** tại những ranh giới kiểu như chữ ký phương thức giữa lớp do các loader khác nhau định nghĩa. Vì vậy, hai plugin có thể nạp những thư viện riêng thành công nhưng gặp `LinkageError` khi phải thống nhất danh tính một kiểu dùng chung. Lỗi này cần được điều tra ở quan hệ loader và kiểu trong method descriptor; đổi tên biến hay ép kiểu không giải quyết nguyên nhân.

Nạp lớp riêng cũng không bỏ qua verification, quy tắc khởi tạo hay quyền truy cập của JPMS. Phần tiếp theo tập trung vào **ai có thể thấy lớp của ai** và những điều kiện để việc trao đổi kiểu qua ranh giới loader hợp lệ.

## 3. Mô hình ủy quyền cha–con và khả năng nhìn thấy

Trong mô hình **parent delegation** mặc định của `ClassLoader.loadClass`, loader kiểm tra lớp đã được tải, sau đó thường nhờ cha tìm trước; nếu cha không tìm thấy, loader con mới gọi `findClass` để tự định nghĩa.

```text
Bootstrap loader              (java.base, ví dụ java.lang.String)
       ↑
Platform loader               (một số module nền tảng JDK)
       ↑
Application/System loader     (classpath/module path ứng dụng)
       ↑
PluginLoader-A           PluginLoader-B
   (plugin A)              (plugin B)
```

Mũi tên chỉ hướng **yêu cầu lên cha**, không có nghĩa loader cha tự động truy cập được mọi lớp riêng của con.

- **Con thường nhìn thấy lớp của cha** do yêu cầu được ủy quyền lên trên.
- **Cha không tự nhìn thấy lớp chỉ do con định nghĩa**, vì cơ chế mặc định không tìm ngược xuống.
- **Hai loader anh em không tự nhìn thấy lớp riêng của nhau**. Chúng chỉ chia sẻ các lớp mà cả hai được cha chung trả về, hoặc thông qua cơ chế kết nối được thiết kế rõ.
- **Không phải mọi loader đều parent-first**. Container và plugin framework có thể thực hiện child-first hoặc quy tắc theo package. Phải xác minh loader thực tế thay vì mặc định mọi lớp đều tuân theo sơ đồ trên.

### Phân biệt ba loại “nhìn thấy”

1. **Visibility khi tải lớp**: loader đang dùng có thể tìm được định nghĩa không?
2. **Accessibility theo ngôn ngữ/JVM**: sau khi tìm được, `public`, `protected`, package-private, quan hệ kế thừa và quy tắc module cho phép truy cập không?
3. **Khả năng tương thích kiểu**: kiểu do loader nào định nghĩa? Hai `Class<?>` có thực sự là cùng một đối tượng `Class` không?

Ví dụ, một loader con có thể tải được một lớp `public` từ cha nhưng vẫn bị JPMS chặn truy cập do module chưa `exports` package, hoặc bị `opens` hạn chế truy cập phản chiếu sâu.

## 4. Runtime package, quyền truy cập và module

Trong JVM, hai lớp chỉ được coi là thuộc cùng một **runtime package** nếu tên package trùng **và defining loader tương ứng giống nhau**. Vì vậy, package-private không phải “lối tắt” để hai plugin truy cập internals của nhau chỉ vì chúng dùng cùng câu lệnh `package org.example;`.

Ví dụ, `pluginA.internal.Helper` và `pluginA.internal.Entry` có cùng package text nhưng do hai loader khác nhau định nghĩa: JVM không xem chúng là cùng runtime package cho mục đích truy cập package-private. Các lỗi có thể biểu hiện dưới dạng `IllegalAccessError` khi bytecode đã liên kết tới thành viên không hợp lệ.

Java Platform Module System (JPMS, Java 9+) bổ sung quy tắc **readability, exports và opens**:

- **Reads**: module nào có quan hệ đọc module nào.
- **Exports**: package nào công khai cho truy cập ở mức biên dịch và runtime.
- **Opens**: package nào cho phép truy cập phản chiếu sâu trong phạm vi cấu hình mở.
- **Class loader**: vẫn đảm trách nạp lớp và tham gia xác định danh tính kiểu; `ModuleLayer` không đồng nghĩa với class loader, vì cách ánh xạ module → loader có thể khác nhau.

Quyền truy cập được quyết định bởi **cả** ranh giới loader, modifiers và quy tắc module có liên quan. Đừng cố “sửa” lỗi module bằng cách chỉ thêm đường dẫn JAR vào classpath, hoặc sửa lỗi `ClassCastException` giữa hai loader bằng `--add-opens`.

## 5. Thí nghiệm Java 17+: hai loader, một tên lớp, hai kiểu

Chương trình dưới đây tự tạo mã nguồn `example.Payload`, dùng compiler của **JDK** biên dịch, sau đó tạo hai `URLClassLoader` độc lập có cùng thư mục lớp. Nó minh họa chính xác sự khác biệt giữa “cùng binary name” và “cùng type identity”.

Lưu mã vào `LoaderNamespaceDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LoaderNamespaceDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("loader-namespace-");
        Path source = dir.resolve("example/Payload.java");
        Path bytecode = dir.resolve("example/Payload.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package example; public class Payload { }");

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Run with a JDK, not a JRE");
            }
            int exit = compiler.run(
                    null, null, null,
                    "-d", dir.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed: " + exit);
            }

            URL location = dir.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();

            try (URLClassLoader left =
                         new URLClassLoader(new URL[]{location}, platform);
                 URLClassLoader right =
                         new URLClassLoader(new URL[]{location}, platform)) {

                Class<?> leftType = Class.forName(
                        "example.Payload", true, left);
                Class<?> rightType = Class.forName(
                        "example.Payload", true, right);
                Object leftObject =
                        leftType.getDeclaredConstructor().newInstance();

                System.out.println(leftType.getName()
                        .equals(rightType.getName()));
                System.out.println(leftType == rightType);
                System.out.println(rightType.isInstance(leftObject));
                System.out.println(leftType.getClassLoader() == left);
                System.out.println(String.class.getClassLoader() == null);
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(dir.resolve("example"));
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy trong thư mục chứa file bằng JDK 17 trở lên:

```bash
javac LoaderNamespaceDemo.java
java LoaderNamespaceDemo
```

Stdout khi biên dịch/chạy thành công:

```text
true
false
false
true
true
```

Giải thích theo thứ tự:

1. `true`: hai lớp có cùng **tên nhị phân**.
2. `false`: hai biến `Class<?>` không tham chiếu cùng định nghĩa lớp.
3. `false`: đối tượng do `leftType` tạo **không phải** thể hiện của `rightType`, nên `rightType.cast(leftObject)` sẽ ném `ClassCastException`.
4. `true`: `left` chính là defining loader của bản `Payload` bên trái.
5. `true`: `String` thuộc lớp nền JDK, được định nghĩa bởi bootstrap loader, nên API trả về `null`.

Chương trình dùng `platform` làm cha để lớp `example.Payload` không bị application loader “nhận trước”. Nếu hai `URLClassLoader` có chung cha **và cha đã định nghĩa `Payload`**, cơ chế parent-first mặc định sẽ khiến chúng cùng nhận một `Class` từ cha; kết quả so sánh có thể khác. Đó chính là lý do thiết kế vị trí đặt JAR quan trọng.

## 6. Cô lập phụ thuộc trong kiến trúc plugin

Giả sử ứng dụng host cần chạy Plugin A phụ thuộc `json-lib 1.x` và Plugin B phụ thuộc `json-lib 2.x`. Nếu đưa cả hai JAR vào một classpath phẳng mà chúng có cùng binary name, thứ tự classpath và cơ chế nạp có thể khiến chỉ một phiên bản được chọn, tạo lỗi `NoSuchMethodError` hoặc hành vi sai.

Một kiến trúc có chủ đích:

```text
Host / parent loader
  ├─ com.acme.spi.Plugin          (giao diện dùng chung)
  ├─ com.acme.spi.Request         (kiểu dữ liệu giao tiếp chung)
  └─ thư viện ổn định dùng chung
         ↑                       ↑
  Plugin A loader            Plugin B loader
    ├─ impl.APlugin            ├─ impl.BPlugin
    └─ json-lib 1.x            └─ json-lib 2.x
```

**Nguyên tắc thiết kế ranh giới:**

- **API/SPI dùng chung đặt ở loader cha**: host và các plugin phải tham chiếu **cùng một** `com.acme.spi.Plugin`. Nếu plugin tự đóng gói và định nghĩa lại interface đó, việc ép kiểu sang interface của host có thể thất bại dù tên giống nhau.
- **Thư viện cần cô lập đặt trong loader riêng**: chỉ phụ thuộc thật sự tách biệt mới định nghĩa ở loader riêng. Nếu cùng tên thư viện đã có trong cha và loader của plugin vẫn parent-first, plugin có thể vô tình dùng bản của cha.
- **Chiến lược child-first chỉ nên chọn lọc**: một số framework ưu tiên JAR của plugin cho package riêng, nhưng vẫn ủy quyền lớp JDK và API/SPI chung cho cha. Viết child-first tùy tiện có thể gây `LinkageError`, phá type identity hoặc làm sai giả định bảo mật.
- **Trao đổi qua hợp đồng ổn định**: interface chung, kiểu DTO chung, primitive, `String` hoặc dữ liệu JSON trung gian. Không truyền trực tiếp `json-lib.internal.Node` của plugin A sang plugin B nếu hai bên định nghĩa lớp đó độc lập.
- **Quản lý lifecycle**: đóng `URLClassLoader` giải phóng tài nguyên như JAR handle, nhưng không bảo đảm dỡ lớp ngay. Để GC thu hồi loader, phải loại bỏ tham chiếu còn giữ lớp, instance, thread, `ThreadLocal`, TCCL, cache và callback thuộc plugin.

### Parent-first và child-first khi phụ thuộc trùng tên

| Cách nạp | Lợi ích | Giới hạn |
| --- | --- | --- |
| Parent-first | Giữ nhất quán JDK và API dùng chung; dễ dự đoán | Không cô lập được một thư viện riêng nếu phiên bản cùng tên đã được cha nạp |
| Child-first chọn lọc | Cho plugin ưu tiên phiên bản thư viện nội bộ | Phải loại trừ các package API chia sẻ và bảo vệ những lớp thuộc JDK; khó chẩn đoán khi rò kiểu |
| Mỗi plugin có loader riêng, chỉ giao tiếp qua SPI cha | Tách thư viện triển khai và giữ hợp đồng chung | Phải quản lý tài nguyên, TCCL, serialization và chu kỳ sống plugin |

**Ví dụ qua ranh giới:** host gọi `Plugin.execute(Request)` thông qua một interface do cha định nghĩa. Bên trong plugin, nó có thể dùng một JSON parser riêng, nhưng trước khi trả kết quả cho host, dữ liệu phải được chuyển thành kiểu kết quả chung được cha định nghĩa. Khi thiết kế API, tránh để type riêng của plugin xuất hiện trong public method signature của hợp đồng chia sẻ.

## 7. Context ClassLoader và ServiceLoader

Một thư viện nằm ở loader cha có khi cần khám phá provider do loader con định nghĩa. Vì cha không tự tìm xuống con, Java có **Thread Context ClassLoader (TCCL)**:

```java
ClassLoader previous =
        Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Gọi thư viện cần tìm provider trong ngữ cảnh plugin.
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

Đây là **đoạn minh họa**, giả định biến `pluginLoader` đã được tạo bởi framework; nó không phải chương trình độc lập. Phải khôi phục TCCL trong `finally`, đặc biệt với thread pool, nếu không plugin cũ có thể bị giữ lại hoặc ảnh hưởng các tác vụ sau.

`ServiceLoader` có thể khám phá provider qua loader chỉ định, ví dụ `ServiceLoader.load(Plugin.class, pluginLoader)`. Để thành công, provider phải triển khai **chính xác** interface `Plugin` mà phía host đang dùng; metadata provider (như `META-INF/services/...` trên classpath truyền thống hoặc `provides ... with ...` trong module) cũng phải đúng. Một loader tìm được provider vẫn chưa chắc provider có thể ép kiểu sang SPI của host nếu SPI bị định nghĩa lại.

Đừng nhầm `Thread.currentThread().getContextClassLoader()` với loader đã định nghĩa chính lớp đang chạy: chúng có thể khác nhau. TCCL là cơ chế lựa chọn loader theo ngữ cảnh luồng, không thay đổi danh tính của lớp đã được định nghĩa.

## 8. Những lỗi thường gặp và cách lần ra ranh giới

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách điều tra |
| --- | --- | --- |
| `ClassNotFoundException` | Loader được yêu cầu không tìm thấy tên lớp | In tên lớp, loader đầu vào, URL/JAR và sơ đồ cha |
| `NoClassDefFoundError` | Thiếu phụ thuộc ở lúc resolution hoặc lỗi trạng thái khởi tạo sau lần thất bại trước | Đọc toàn bộ `Caused by`, xác minh phụ thuộc và lỗi khởi tạo sớm hơn |
| `ClassCastException` có cùng tên lớp ở hai vế | Hai loader định nghĩa cùng binary name | So sánh `a.getClass() == expectedType` và in defining loader của từng phía |
| `NoSuchMethodError` / `NoSuchFieldError` | Version/API thực tế được nạp không khớp bytecode bên gọi | Xác định nguồn JAR và phiên bản **được nạp thực tế** |
| `LinkageError: loader constraint violation` | JVM thấy các định nghĩa không tương thích tại ranh giới liên kết kiểu | Xem kiểu trong method descriptor và loader của mỗi thành phần |
| `IllegalAccessError` | Quyền truy cập bytecode/runtime package/module không hợp lệ | Kiểm tra modifier, defining loader, `exports` và cấu hình module |
| `ServiceConfigurationError` | Provider không tìm được, không khởi tạo được hoặc không phải subtype của service dùng chung | Kiểm tra metadata provider, classpath/module path và danh tính SPI |
| `InaccessibleObjectException` | Truy cập phản chiếu sâu bị module encapsulation chặn | Kiểm tra `opens`, hướng truy cập và API thay thế hợp lệ |

**Ghi nhớ phân biệt:** `ClassNotFoundException` là ngoại lệ checked thường gặp khi gọi API nạp lớp bằng tên; `NoClassDefFoundError` là lỗi liên kết/khởi tạo khi JVM không thể dùng một định nghĩa được kỳ vọng, không nên tự động coi chúng là cùng một vấn đề.

### Quy trình chẩn đoán ngắn gọn

1. Ghi lại **binary name**, class nào đang gọi, và toàn bộ exception chain.
2. In `SomeType.class.getClassLoader()`; với object động, in `obj.getClass().getClassLoader()`. Kiểm tra hai phía biên API.
3. Xem vị trí bytecode được nạp; với lớp có code source khả dụng, có thể dùng `clazz.getProtectionDomain().getCodeSource()` (giá trị có thể `null`).
4. Với JDK 17+, chạy `java -Xlog:class+load=info ...` để theo dõi hoạt động nạp lớp. Tùy cách ghi log, có thể cần kết hợp với thông tin loader trong ứng dụng để xác nhận danh tính.
5. Nếu tiến trình cho phép attach, `jcmd <pid> VM.classloaders` cung cấp cái nhìn về hệ thống loader; danh sách lệnh có thể kiểm tra bằng `jcmd <pid> help`.
6. Đối chiếu classpath/module path, quan hệ cha, quy tắc delegation và tập JAR thực sự được gắn vào từng loader.
7. Với sự cố chỉ xảy ra sau redeploy/plugin reload, rà soát tham chiếu giữ loader cũ: thread sống lâu, scheduler, callback, static registry, cache, TCCL hoặc `ThreadLocal`.

Một phương pháp kiểm tra ngay trong Java:

```java
static void describe(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

Đoạn trên là **phương thức hỗ trợ**, đặt trong class của ứng dụng để gọi; `getModule().getName()` có thể trả `null` với unnamed module. `toString()` của loader hữu ích cho quan sát nhưng không nên coi là định danh bất biến hoặc duy nhất.

## 9. Những ngộ nhận dễ dẫn đến thiết kế sai

- **“Cùng FQN thì cast được.”** Sai khi defining loader khác nhau. FQN chỉ là một nửa danh tính kiểu.
- **“Loader con có thể tải mọi lớp của loader anh em.”** Không đúng với delegation mặc định; cần kênh tìm kiếm/layer/cầu nối riêng.
- **“Tạo URLClassLoader là cô lập mọi dependency.”** Không đúng nếu thư viện đã nằm ở cha và parent-first trả về bản của cha.
- **“Package name giống là có package-private access.”** Runtime package còn phụ thuộc defining loader.
- **“Đổi TCCL đổi class của object hiện tại.”** TCCL ảnh hưởng cách một số API tìm lớp/provider về sau; không định nghĩa lại lớp đã có.
- **“Dùng reflection là bỏ qua mọi ranh giới.”** Reflection vẫn chịu kiểm tra quyền truy cập và module encapsulation.
- **“Close loader nghĩa là unload toàn bộ class.”** JVM chỉ có thể thu hồi lớp/loader khi các điều kiện về reachability và lifecycle được thỏa mãn.
- **“JPMS thay thế ClassLoader.”** Module là cơ chế tổ chức/đóng gói, còn loader vẫn thực hiện loading và type identity.

## 10. Áp dụng: thiết kế hệ plugin không xung đột phiên bản

Trước khi triển khai, lần lượt trả lời:

1. **Thứ gì bắt buộc chia sẻ?** Xác định một bản duy nhất của các interface, DTO và exception trong API/SPI phía host.
2. **Thứ gì phải cô lập?** Xác định danh sách thư viện có thể khác phiên bản ở từng plugin; tránh cho thư viện đó lộ qua public API.
3. **Loader graph ra sao?** Vẽ rõ quan hệ cha–con, thư mục/JAR của mỗi loader, và package nào parent-first hay child-first.
4. **Ai chịu trách nhiệm khám phá provider?** Chỉ định loader cho `ServiceLoader` hoặc TCCL tại đúng điểm gọi và khôi phục TCCL.
5. **Khi plugin dừng thì điều gì được giải phóng?** Đóng tài nguyên, ngắt thread, unregister hook, xóa cache/ThreadLocal và tham chiếu đến object/class/loader.
6. **Kiểm thử những va chạm nào?** Hai plugin dùng cùng tên lớp với bytecode khác; hai phiên bản JSON lib; cast qua SPI; reload plugin; thiếu class ở thời điểm resolution.

### Tự kiểm tra kiến thức

**Câu 1.** Hai `URLClassLoader` khác nhau đều load cùng đường dẫn `example.Payload.class`. Có chắc hai `Class` giống nhau không?  
**Trả lời:** Không. Nếu mỗi loader tự định nghĩa, đó là hai kiểu; nếu cả hai ủy quyền cho cùng defining loader ở cha, có thể là một kiểu.

**Câu 2.** Plugin A báo `ClassCastException: com.acme.spi.Plugin cannot be cast to com.acme.spi.Plugin`. Nên kiểm tra gì đầu tiên?  
**Trả lời:** Danh tính `Plugin.class` ở host và phía plugin, đặc biệt việc plugin có đóng gói/định nghĩa lại SPI thay vì ủy quyền cho cha hay không.

**Câu 3.** Plugin B phải chạy phiên bản `json-lib` khác host, nhưng vẫn nạp bản host. Vì sao?  
**Trả lời:** Loader B dùng parent-first, nên cha đã tìm thấy lớp `json-lib` trước. Cần thiết kế tách phụ thuộc với delegation chọn lọc, tránh phá API/SPI dùng chung.

**Câu 4.** Một thư viện chung tìm không thấy provider đặt trong plugin, mặc dù plugin nhìn thấy thư viện đó. Vì sao?  
**Trả lời:** Quan hệ nhìn thấy một chiều: loader cha của thư viện không tự tìm xuống loader con của plugin. Kiểm tra loader được truyền cho `ServiceLoader` hoặc TCCL tại lúc discovery.

## Kết luận

Cách tư duy đúng là vẽ rõ **ai định nghĩa lớp nào**, **loader nào có thể yêu cầu lớp từ đâu**, và **kiểu nào phải chung một danh tính ở ranh giới giao tiếp**. Khi ba điều này nhất quán, Java ClassLoader có thể hỗ trợ plugin và nhiều phiên bản phụ thuộc an toàn hơn; khi chúng bị trộn lẫn, lỗi thường chỉ lộ ra ở runtime dưới dạng cast, linkage, access hoặc service discovery failures.
