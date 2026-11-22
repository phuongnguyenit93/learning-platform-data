# MethodHandles.Lookup.defineClass và ngữ cảnh định nghĩa lớp trong Java

## 1. Tại sao định nghĩa lớp động cần một “ngữ cảnh” đáng tin cậy?

Java không chỉ nạp bytecode từ classpath hay JAR có sẵn. Framework, công cụ sinh mã, proxy engine và plugin runtime có thể **sinh class file bytes khi chương trình đang chạy**, sau đó yêu cầu JVM định nghĩa một kiểu mới. Nhưng một mảng `byte[]` không tự trả lời các câu hỏi quan trọng:

- Class mới sẽ thuộc **ClassLoader nào**?
- Nó có tên package và **runtime package** nào?
- Nó có quyền truy cập package-private vào các class xung quanh không?
- Nó thuộc module nào, có thể đọc và dùng những API nào?
- Nó nhận **protection domain** nào?
- Ai được quyền tạo class mới vào không gian tên đang tồn tại?
- Nó đã được **khởi tạo** chưa, và có trùng định nghĩa đã có không?

Từ Java 9, API `java.lang.invoke.MethodHandles.Lookup.defineClass(byte[])` giải quyết một trường hợp cụ thể: **định nghĩa một class bình thường, có tên, trong cùng ngữ cảnh runtime của lookup class**.

Chữ ký:

```java
public Class<?> defineClass(byte[] bytes)
        throws IllegalAccessException
```

Đây là chữ ký phương thức của `MethodHandles.Lookup`, không phải chương trình độc lập.

**Tóm tắt chính xác:** `Lookup.defineClass` tạo và liên kết class từ bytecode hợp lệ **với cùng defining ClassLoader, cùng runtime package và cùng protection domain với lookup class**. Nó **đòi hỏi mode `PACKAGE`** trên `Lookup` và **không chạy class initializer** ngay khi định nghĩa. Phương thức không nhận argument chọn ClassLoader tùy ý, cũng không tạo một class mới ở package khác do caller thích.

Điều này khác đáng kể với một custom `ClassLoader` tự đọc bytecode trong `findClass` rồi gọi `ClassLoader.defineClass`: bên dùng `Lookup` phải chứng minh mình có quyền ngữ cảnh package tương ứng, thay vì tùy chọn một loader/nguồn từ API đó.

## 2. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa trong bài | Ví dụ |
| --- | --- | --- |
| **Class file bytes** | Dãy byte tuân theo JVMS class file format, thường bắt đầu bằng magic `CA FE BA BE` | Nội dung `Generated.class` |
| **Binary name** | Tên nhị phân của kiểu trong class file | `demo.lookup.Generated` |
| **Lookup class** | Class xác định ngữ cảnh và quyền của đối tượng `Lookup` | `demo.lookup.LookupDefineDemo` |
| **Lookup modes** | Các cờ quyền như `PUBLIC`, `MODULE`, `PACKAGE`, `PRIVATE` | `lookup.lookupModes()` |
| **Defining ClassLoader** | Loader định nghĩa runtime class, góp phần tạo danh tính kiểu | Application loader của lookup class |
| **Runtime package** | Cặp (tên package, defining loader) | `("demo.lookup", appLoader)` |
| **Module** | JPMS module chứa lookup class và class được định nghĩa trong ngữ cảnh ấy | Unnamed module trong demo |
| **Protection domain** | Thông tin miền bảo vệ gắn với class, do runtime dùng cho các cơ chế bảo mật tương ứng | `lookupClass.getProtectionDomain()` |
| **Linking** | Xác minh/chuẩn bị/phân giải theo quy tắc JVMS | Sau khi tạo định nghĩa, có thể còn resolution về sau |
| **Initialization** | Thực thi `<clinit>` theo quy tắc active use | Khi gọi static method của class mới |

Một runtime class/interface thông thường được nhận diện bằng **(binary name, defining loader)**. Cùng tên, cùng bytecode nhưng được hai loader độc lập định nghĩa thì là hai kiểu runtime khác nhau. Ngược lại, `Lookup.defineClass` **không tạo loader riêng**: nó định nghĩa class trong loader của lookup class.

### Mối liên hệ với module

`Lookup.defineClass` không phải cơ chế tùy ý “chèn bytecode vào mọi module”. Với một lookup hợp lệ, class mới được định nghĩa trong ngữ cảnh của lookup class, bao gồm module tương ứng. Khi source chạy trên classpath thông thường, lookup class thuộc **unnamed module** của loader; khi chạy trong named module, cần kiểm tra các quy tắc JPMS, ranh giới package và quyền tạo lookup.

**Có cùng module không tự động cấp mọi quyền private:** các thành viên private thuộc ranh giới class/nest, không phải mọi class nằm trong module. Class mới có thể dùng package-private khi hợp lệ, nhưng không mặc nhiên là nestmate của lookup class chỉ vì được định nghĩa bằng `defineClass`.

## 3. Tại sao phải dùng MethodHandles.Lookup?

Đối tượng `Lookup` là ngữ cảnh được JVM dùng để kiểm tra quyền khi tạo method handle và thực hiện một số thao tác đặc quyền. Một `Lookup` mang thông tin về:

- `lookup.lookupClass()`: class được xem là chủ thể tra cứu.
- `lookup.lookupModes()`: quyền truy cập hiện có.
- Khi phù hợp, ngữ cảnh module và các hạn chế khi lookup đã được chuyển đổi hoặc giảm quyền.

Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> callerClass = lookup.lookupClass();
boolean canDefine = (lookup.lookupModes()
        & MethodHandles.Lookup.PACKAGE) != 0;
```

Đây là snippet, cần import `java.lang.invoke.MethodHandles` và chạy ở method thuộc class có quyền phù hợp.

`MethodHandles.lookup()` trả lookup gắn với **caller thật tại vị trí gọi**. Nếu method gọi `lookup()` nằm trong `demo.lookup.Host`, lookup class là `demo.lookup.Host`, không phải class nào mà ứng dụng đang muốn định nghĩa.

**Điều kiện quan trọng:** `defineClass` yêu cầu `Lookup.PACKAGE` access. `MethodHandles.publicLookup()` chỉ có quyền public/unconditional tương ứng, không thể được sử dụng để định nghĩa một class mới vào package cụ thể.

Nếu ứng dụng nhận một `Lookup` từ thư viện khác, **không nên đoán** nó còn quyền nguyên vẹn: các thao tác như `lookup.in(target)` hoặc `dropLookupMode(...)` có thể làm giảm mode. Kiểm tra `lookupClass()`, `lookupModes()` và nguồn cấp lookup khi thiết kế API.

## 4. defineClass(byte[]) làm gì và không làm gì?

Theo Java SE 17 API, `Lookup.defineClass(byte[])`:

1. Nhận bytecode của một class file hợp lệ.
2. Xác định ngữ cảnh từ lookup class hiện tại.
3. Bắt buộc có quyền `PACKAGE`.
4. Yêu cầu class được định nghĩa có **tên package giống lookup class**.
5. Tạo class với cùng **ClassLoader, runtime package và protection domain** của lookup class, tương đương về mặt định nghĩa với quy tắc `ClassLoader.defineClass` thích hợp.
6. **Tạo và liên kết** class, trả về đối tượng `Class<?>`.
7. **Không chạy static initializer** của class mới ngay tại lời gọi `defineClass`.

Thứ tự nội bộ, kiểm tra và thời điểm resolution của JVM có quy tắc riêng. Không suy luận rằng mọi phụ thuộc của class mới đều đã được khởi tạo hay rằng mọi lời gọi sau đó chắc chắn thành công.

### Không có các khả năng sau

- Không truyền tên binary name riêng như `defineClass("x.y.Z", bytes, ...)` của một số overload `ClassLoader`. Tên nằm trong bytes.
- Không cho caller chọn class loader bằng argument.
- Không cho định nghĩa class ở package khác lookup class.
- Không tự mở package của named module cho những module khác.
- Không đổi `exports`, `opens` hay `requires` của module descriptor.
- Không tự thêm class vào một nest để có quyền private; đó là chủ đề khác.
- Không tạo **hidden class**; API đó là `defineHiddenClass`.
- Không re-define một binary name đã tồn tại trong cùng defining loader như phiên bản mới.
- Không tạo sandbox an toàn cho bytecode từ nguồn không tin cậy.

### Vì sao `byte[]` phải đúng package?

Giả sử lookup class là `demo.lookup.Host`, còn mảng bytes định nghĩa `external.plugin.Generated`. Dù các bytes là một class file hợp lệ, lời gọi:

```java
lookup.defineClass(externalBytes);
```

sẽ vi phạm quy tắc **same package**, thường được API báo bằng `IllegalArgumentException` theo hợp đồng `Lookup.defineClass`. Đây không phải tình huống cần thử thêm dấu `/` vào tên: tên lớp thật nằm trong constant pool của class file.

## 5. Ví dụ Java 17 đã kiểm chứng: định nghĩa lớp từ bytecode đang ở ngoài classpath

Bài thực hành sau tạo bytecode động bằng `JavaCompiler` và nạp class không nằm trên application classpath. Tên class mới được chọn là `demo.lookup.Generated`, **cùng package** với chương trình chủ:

```text
Mã host lúc biên dịch:
    demo.lookup.LookupDefineDemo  -> out/demo/lookup/LookupDefineDemo.class

File Generated.java tạo lúc runtime trong thư mục tạm:
    demo.lookup.Generated         -> temp/classes/demo/lookup/Generated.class

Host đọc Generated.class thành byte[]
   -> MethodHandles.lookup().defineClass(bytes)
   -> Class<?> của demo.lookup.Generated
```

Không cần chạy `java -cp ...:temp/classes`. Chính lookup định nghĩa kiểu mới ngay trong loader của host. Đây là đặc tính khác với tìm class qua path bằng `ClassLoader.loadClass`.

### 5.1. Lưu chương trình đầy đủ

Tạo file `src/demo/lookup/LookupDefineDemo.java`:

```java
package demo.lookup;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class LookupDefineDemo {
    private static final String INIT_KEY =
            "example.lookup.defineClass.initialized";

    public static void main(String[] args) throws Throwable {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        System.clearProperty(INIT_KEY);
        Path work = Files.createTempDirectory("lookup-define-");

        try {
            Path source = work.resolve(
                    "src/demo/lookup/Generated.java");
            Path foreign = work.resolve(
                    "src/demo/other/Foreign.java");
            Path output = work.resolve("classes");

            Files.createDirectories(source.getParent());
            Files.createDirectories(foreign.getParent());
            Files.createDirectories(output);

            Files.writeString(source, """
                    package demo.lookup;

                    public final class Generated {
                        static {
                            System.setProperty(
                                "example.lookup.defineClass.initialized", "yes");
                        }

                        static String say() {
                            return "Hello, dynamically defined";
                        }
                    }
                    """);

            Files.writeString(foreign, """
                    package demo.other;
                    public final class Foreign { }
                    """);

            int code = compiler.run(null, null, null,
                    "--release", "17", "-encoding", "UTF-8",
                    "-d", output.toString(),
                    source.toString(), foreign.toString());
            if (code != 0) {
                throw new IllegalStateException(
                        "Dynamic compilation failed");
            }

            byte[] localBytes = Files.readAllBytes(
                    output.resolve("demo/lookup/Generated.class"));
            byte[] foreignBytes = Files.readAllBytes(
                    output.resolve("demo/other/Foreign.class"));

            MethodHandles.Lookup lookup = MethodHandles.lookup();

            System.out.println("lookupClass="
                    + (lookup.lookupClass() == LookupDefineDemo.class));
            System.out.println("hasPackageMode="
                    + ((lookup.lookupModes()
                    & MethodHandles.Lookup.PACKAGE) != 0));

            Class<?> generated = lookup.defineClass(localBytes);

            System.out.println("samePackage="
                    + generated.getPackageName().equals(
                            LookupDefineDemo.class.getPackageName()));
            System.out.println("sameLoader="
                    + (generated.getClassLoader()
                            == LookupDefineDemo.class.getClassLoader()));
            System.out.println("sameModule="
                    + (generated.getModule()
                            == LookupDefineDemo.class.getModule()));
            System.out.println("sameProtectionDomain="
                    + (generated.getProtectionDomain()
                            == LookupDefineDemo.class.getProtectionDomain()));
            System.out.println("notInitializedAfterDefine="
                    + (System.getProperty(INIT_KEY) == null));

            MethodHandle handle = lookup.findStatic(
                    generated, "say", MethodType.methodType(String.class));

            System.out.println("call="
                    + (String) handle.invokeExact());
            System.out.println("initializedAfterCall="
                    + "yes".equals(System.getProperty(INIT_KEY)));

            try {
                MethodHandles.publicLookup().defineClass(localBytes);
                System.out.println("publicLookup=unexpected");
            } catch (IllegalAccessException expected) {
                System.out.println("publicLookup=IllegalAccessException");
            }

            try {
                lookup.defineClass(foreignBytes);
                System.out.println("otherPackage=unexpected");
            } catch (IllegalArgumentException expected) {
                System.out.println("otherPackage=IllegalArgumentException");
            }

            try {
                lookup.defineClass(localBytes);
                System.out.println("duplicate=unexpected");
            } catch (LinkageError expected) {
                System.out.println("duplicate=LinkageError");
            }
        } finally {
            System.clearProperty(INIT_KEY);
            try (Stream<Path> stream = Files.walk(work)) {
                for (Path p :
                        stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

**Lệnh chạy**, từ thư mục chứa `src`:

```bash
javac --release 17 -d out src/demo/lookup/LookupDefineDemo.java
java -cp out demo.lookup.LookupDefineDemo
```

Không cần biên dịch thủ công `Generated.java` hoặc `Foreign.java`: hai file này được chương trình tạo tạm và biên dịch ở runtime qua `JavaCompiler`. Cần **JDK đầy đủ** (có module `jdk.compiler`), không chỉ runtime image tối giản không chứa compiler.

### 5.2. Stdout chính xác

Chương trình trên được biên dịch bằng JDK 21 với mục tiêu `--release 17` và đã chạy thành công. Stdout thu được:

```text
lookupClass=true
hasPackageMode=true
samePackage=true
sameLoader=true
sameModule=true
sameProtectionDomain=true
notInitializedAfterDefine=true
call=Hello, dynamically defined
initializedAfterCall=true
publicLookup=IllegalAccessException
otherPackage=IllegalArgumentException
duplicate=LinkageError
```

Kết quả được xây dựng tránh phụ thuộc vào thứ tự liệt kê class/JAR hoặc vào GC. Nếu filesystem không cho tạo tệp tạm hay compiler không có, chương trình báo lỗi rõ thay vì giả vờ có cùng output.

### 5.3. Đọc kết quả theo ngữ cảnh

**`lookupClass=true`:** `MethodHandles.lookup()` được gọi bên trong `LookupDefineDemo.main`, nên class của lookup là `LookupDefineDemo`, không phải `Generated`.

**`hasPackageMode=true`:** lookup do chính class gọi tạo có quyền `PACKAGE`, là điều kiện cần của `defineClass`.

**`samePackage=true`:** bytes định nghĩa class trong `demo.lookup`, đúng package của lookup class. Nếu bytes mang tên `demo.other.Foreign`, không đạt điều kiện này.

**`sameLoader=true`:** class mới được định nghĩa bởi cùng loader với `LookupDefineDemo`. Không có custom ClassLoader thứ hai được tạo.

**`sameModule=true`:** cả host và class mới thuộc cùng ngữ cảnh module. Trong demo chạy qua classpath, cả hai thuộc unnamed module của application loader.

**`sameProtectionDomain=true`:** class mới có cùng protection domain với lookup class, không phải một domain do dữ liệu từ filesystem tự quyết định. Điều này cũng là lý do không được lấy lookup quyền cao để định nghĩa bytecode chưa xác minh.

**`notInitializedAfterDefine=true`:** khi `defineClass(localBytes)` trả về, static block của `Generated` chưa chạy nên system property chưa được đặt.

**`call=Hello, dynamically defined` và `initializedAfterCall=true`:** gọi static method `say()` qua method handle là active use; JVM khởi tạo class trước lời gọi, static block đặt system property.

**`publicLookup=IllegalAccessException`:** lookup public không có `PACKAGE` mode. Dù bytes đúng package, thiếu quyền lookup khiến định nghĩa bị từ chối.

**`otherPackage=IllegalArgumentException`:** bytes của `demo.other.Foreign` không cùng package với `LookupDefineDemo`. API từ chối class file này.

**`duplicate=LinkageError`:** đã có định nghĩa `demo.lookup.Generated` bởi loader đó. Gọi `defineClass` với cùng binary name lần nữa không tạo ra “version 2” của class trong cùng loader.

### 5.4. Vì sao dùng MethodHandle để gọi static method?

Phương thức `Generated.say()` có mức **package-private** (không khai báo `public`). Lookup chủ thuộc cùng runtime package có quyền thích hợp nên có thể lấy handle:

```java
MethodHandle handle = lookup.findStatic(
        generated, "say", MethodType.methodType(String.class));
```

Đây là snippet thuộc chương trình đầy đủ. Phần `invokeExact()` gọi method đúng chữ ký `()String` và gây initialization trước khi thực thi.

Nó đồng thời minh họa một lợi ích thực tế: class được định nghĩa **trong package/loader của host lookup**, cho phép tích hợp những API package-private có chủ đích, thay vì buộc công khai mọi API nội bộ. Nhưng vẫn phải kiểm soát ai được nhận Lookup có quyền `PACKAGE`.

## 6. Quy tắc “same package” nghiêm ngặt tới mức nào?

Ví dụ host nằm trong `demo.lookup`:

| Tên class thực trong bytes | Kết quả đối với lookup của `demo.lookup.LookupDefineDemo` |
| --- | --- |
| `demo.lookup.Generated` | Hợp lệ về **điều kiện package** nếu bytes chuẩn, chưa định nghĩa trùng, quyền lookup đủ |
| `demo.lookup.Helper$Nested` | Thuộc package `demo.lookup`; vẫn cần kiểm tra bytes/điều kiện khác |
| `demo.other.Foreign` | Khác package, `IllegalArgumentException` theo API |
| `java.lang.FakeString` | Khác package; không thể dùng lookup này để xâm nhập package Java nền tảng |
| Class file hỏng hoặc không phải class/interface | Không hợp lệ; có thể `ClassFormatError`/`IllegalArgumentException` tùy lỗi |
| Class cùng binary name đã được loader định nghĩa | Xung đột linkage; không phải tự ghi đè class cũ |

**Đừng tự kiểm tra package chỉ bằng đường dẫn file**. Package của một class được xác định từ tên nhị phân mã hóa trong bytecode, không phải do file được đặt ở thư mục nào. Đổi tên file `Foreign.class` thành `Generated.class` không làm đổi package chứa trong class file.

### Runtime package phụ thuộc defining loader

Hai class cùng package string nhưng khác loader là hai runtime packages khác nhau. Nếu ứng dụng thật cần định nghĩa class trong runtime package của một class ở plugin loader, hãy lấy **Lookup hợp lệ của chính class thuộc loader/plugin ấy** qua cơ chế được ủy quyền, không truyền bytecode vào lookup của host rồi kỳ vọng class tự “chuyển” sang plugin loader.

Ví dụ:

```text
HostLoader định nghĩa demo.lookup.Host
PluginLoader định nghĩa plugin.internal.Anchor

Host lookup -> định nghĩa class thuộc demo.lookup + HostLoader
Plugin anchor lookup -> định nghĩa class thuộc plugin.internal + PluginLoader
```

Đây là mô hình khái niệm; việc lấy plugin anchor lookup còn cần điều kiện quyền/module phù hợp. Có hai class loader không có nghĩa bạn tự động được quyền lấy lookup PACKAGE của cả hai.

## 7. Quyền Lookup và các cách tạo ngữ cảnh

### 7.1. MethodHandles.lookup()

`MethodHandles.lookup()` tạo Lookup từ caller class thực. Nếu gọi bên trong class `pkg.Anchor`, nó có thể có quyền đầy đủ trong ngữ cảnh phù hợp của Anchor. Đây là lựa chọn đơn giản nhất khi code **trong package đó** chủ động quyết định sinh class:

```java
final class Anchor {
    static Class<?> defineTrusted(byte[] bytes)
            throws IllegalAccessException {
        return MethodHandles.lookup().defineClass(bytes);
    }
}
```

Đây là **snippet minh họa**, cần import `MethodHandles`, được biên dịch trong package hiện tại. Một API như `defineTrusted` chỉ nên nhận bytes từ nguồn tin cậy và kiểm tra tính hợp lệ cần thiết.

### 7.2. MethodHandles.publicLookup()

`publicLookup()` được thiết kế cho các thành viên public thích hợp, **không có PACKAGE mode**, nên không thể gọi `defineClass` thành công. Nó không phải một “Lookup tự do nạp class” chỉ vì có tên public.

### 7.3. privateLookupIn(targetClass, callerLookup)

`MethodHandles.privateLookupIn(targetClass, callerLookup)` có thể tạo Lookup tới target class khi caller có **đủ quyền** và quan hệ truy cập/module cho phép. Với named modules, điều kiện module/package được mở phù hợp (*opens*) rất quan trọng. Không phải chỉ có target Class object là có thể lấy được mọi quyền của nó.

Một cách dùng kiến trúc:

1. Host định nghĩa API public để yêu cầu plugin tự sinh class.
2. Plugin có anchor class trong đúng package và loader mà class mới cần ở.
3. Code được cấp quyền sử dụng lookup PACKAGE một cách có kiểm soát.
4. Lookup mới chỉ định nghĩa **class cùng package** từ bytes được xác minh.
5. Host không cần cố mở `java.base` hay dùng reflective access trái chính sách JPMS.

**Nguyên tắc capability:** Lookup có `PACKAGE` mode là một dạng quyền có thể ủy nhiệm. Không phát tán Lookup đó cho mọi plugin hay cho dữ liệu từ mạng; người nhận có thể dùng nó để định nghĩa class mới trong không gian tên hợp lệ của lookup class.

### 7.4. Lookup.in và dropLookupMode

Các phương thức này có thể tạo một Lookup có quyền thấp hơn. Nếu quyền `PACKAGE` bị mất, `defineClass` sẽ không còn được phép:

```java
MethodHandles.Lookup restricted =
        MethodHandles.lookup().dropLookupMode(
                MethodHandles.Lookup.PACKAGE);
```

Đây là snippet; gọi `restricted.defineClass(bytes)` sẽ không có đủ quyền PACKAGE và có thể ném `IllegalAccessException`. Không được gắn nhãn lookup là “full privilege” chỉ vì object ban đầu đến từ code trusted.

## 8. So sánh Lookup.defineClass với ClassLoader.defineClass

Có hai nhóm cách định nghĩa class khác nhau về quyền và khả năng cấu hình.

| Tiêu chí | `Lookup.defineClass(bytes)` | `ClassLoader.defineClass(name, bytes, ...)` |
| --- | --- | --- |
| Chủ thể gọi | Code có một `Lookup` phù hợp | Subclass/logic của `ClassLoader` có quyền gọi protected API |
| Chọn loader | **Loader của lookup class** | Loader nhận lệnh `defineClass` |
| Chọn package | **Phải cùng package với lookup class** | Dựa vào bytes/name và policy/namespace của loader |
| Protection domain | **Cùng domain với lookup class** | Có overload cho phép chỉ định `ProtectionDomain` |
| Quyền bắt buộc | `Lookup.PACKAGE` | Quy tắc bảo mật/JVM của ClassLoader và protected method |
| Tích hợp package-private | Có thể trong cùng runtime package | Nếu class được định nghĩa bởi loader khác thì không thành cùng runtime package |
| Class file bytes | Yêu cầu bytes hợp lệ | Yêu cầu bytes hợp lệ |
| Khởi tạo static ngay khi định nghĩa? | **Không** | Không tự coi `defineClass` là một lệnh gọi `<clinit>` |
| Định nghĩa trùng binary name | Không cho tự ghi đè class | Không cho tự ghi đè class |
| Hidden class? | Không | Không; cần API riêng cho hidden class |

### Khi nào nên dùng Lookup.defineClass?

Phù hợp khi:

- Sinh một helper class mới để **cộng tác với code đã tồn tại trong chính package đó**.
- Muốn dùng package-private members trong một thư viện/runtime đã chủ động cấp lookup hợp lệ.
- Không cần tạo ClassLoader mới và không cần đưa class sang package khác.
- Bytecode do pipeline đáng tin cậy tạo ra, có quy tắc naming/version rõ ràng.
- Muốn định nghĩa một **named, ordinary class** có thể được xử lý bởi các API phản chiếu thông thường.

### Khi nào nên dùng custom ClassLoader?

Phù hợp hơn khi:

- Cần định nghĩa class ở **nhiều package** từ thư mục, JAR, database hoặc bytecode repository riêng.
- Cần **cô lập phiên bản thư viện**, unload một nhóm class theo vòng đời loader riêng.
- Cần chính sách parent/child delegation, package ownership và resource lookup riêng.
- Cần quản lý plugin loading một cách độc lập với loader/module của host.
- Cần kiểm soát protection domain/code source theo cơ chế được thiết kế trong custom loader.

**Không thay custom ClassLoader bằng một lookup của host rồi mong mọi plugin được cô lập.** Nếu tất cả class mới được định nghĩa chung ở host loader, chúng gắn với vòng đời host, không có isolation theo loader riêng cho từng phiên bản.

## 9. Định nghĩa lớp, linking và class initialization là ba việc khác nhau

Mối quan hệ:

```text
byte[] hợp lệ
    |
    v
Lookup.defineClass(bytes)
    |
    +-- tạo runtime class
    +-- linking theo hợp đồng API/JVMS
    +-- trả Class<?>
    |
    +-- chưa tự chạy static initializer
            |
            v
sau đó active use (ví dụ gọi static method)
    |
    +-- class initialization xảy ra theo quy tắc JLS
```

JVM có thể thực hiện một phần verification/resolution ở những thời điểm khác nhau, nhưng **lời gọi defineClass không tự chạy static initializer**. Đây là lý do ví dụ có:

```text
notInitializedAfterDefine=true
...
initializedAfterCall=true
```

Không phải mọi thao tác cầm `Class<?>` đều là active use: xem tên class, defining loader hoặc module thông thường không tương đương gọi constructor/static method. Nhưng một số thao tác reflective/API khác có thể yêu cầu initialization theo hợp đồng riêng; phải xét method cụ thể.

### Nếu static initializer ném lỗi?

Nếu `<clinit>` ném exception, các lời gọi sau có thể báo `ExceptionInInitializerError` hoặc `NoClassDefFoundError` liên quan class bị lỗi initialization, chứ không có nghĩa `Lookup.defineClass` đã “không tạo class”. Khi debug, tách lỗi **definition/linkage** khỏi lỗi **initialization**.

## 10. Những ngoại lệ cần biết

| Lỗi / exception | Khi nào cần xét? | Hướng xử lý |
| --- | --- | --- |
| `IllegalAccessException` | Lookup không có `PACKAGE` mode | Tạo/nhận Lookup đúng quyền tại anchor package; không dùng publicLookup |
| `IllegalArgumentException` | Bytes định nghĩa class khác package hoặc không phải class/interface theo quy tắc API | Kiểm tra binary name thật trong class file và loại class |
| `ClassFormatError` | Không phải class file cấu trúc hợp lệ | Kiểm tra nguồn bytes, format, transform, compiler |
| `VerifyError` | JVM không xác minh được bytecode | Kiểm tra generator/transformer, descriptors, stack map frames |
| `UnsupportedClassVersionError` | Class file yêu cầu JVM version mới hơn | Kiểm tra `javac --release`, version runtime |
| `LinkageError` | Trùng định nghĩa, ràng buộc linking hoặc dependency khác không hợp lệ | Kiểm tra naming/loader/dependency và nguyên nhân đầy đủ |
| `NullPointerException` | `bytes == null` | Không truyền dữ liệu thiếu |
| `SecurityException` | Có SecurityManager legacy và permission check phù hợp bị từ chối | Xem chính sách runtime, đừng nuốt exception |
| `ExceptionInInitializerError` | Class initializer ném lỗi khi active use | Tách khỏi thời điểm `defineClass` |
| `NoClassDefFoundError` | Dependency không khả dụng, class state lỗi trước đó hoặc wrong name trong tình huống liên quan | Đọc chuỗi cause và thời điểm lỗi |

**Không catch chung mọi `Throwable` rồi đổi sang `ClassNotFoundException`.** `LinkageError`, `VerifyError` hoặc `ClassFormatError` phản ánh vấn đề khác “không có class để tìm”. Che lỗi sẽ làm debugging và xử lý trạng thái JVM không an toàn.

### Duplicate definition trong cùng loader

Mỗi runtime class identity thông thường là (binary name, defining loader). Nếu `demo.lookup.Generated` đã được định nghĩa, gọi `lookup.defineClass(localBytes)` lần nữa cho cùng tên, cùng loader sẽ không tạo bản thứ hai. Ví dụ phát hiện `LinkageError` và in `duplicate=LinkageError`.

Cần cách khác cho nhu cầu **hot reload**: thiết kế ClassLoader mới hoặc cơ chế JVM instrumentation phù hợp, chứ không gọi lại `defineClass` vào cùng loader. Không đánh đồng các API redefine/retransform của instrumentation với `Lookup.defineClass`.

## 11. So sánh với defineHiddenClass

Từ Java 15, `Lookup.defineHiddenClass(bytes, initialize, options...)` phục vụ các class đặc biệt không thể được tìm theo binary name thông thường của named class. Đây là hướng khác với `defineClass`.

| Đặc tính | `defineClass` | `defineHiddenClass` |
| --- | --- | --- |
| Class kind | Named, ordinary class | Hidden class với quy tắc đặc biệt |
| Trả về | `Class<?>` | `MethodHandles.Lookup` trên hidden class |
| Yêu cầu lookup | `PACKAGE` mode | Full-privilege access theo API |
| Initialization parameter | Không; define không chạy initializer | Có tham số boolean `initialize` |
| Naming/lookup | Có binary name thông thường | Không tìm bằng cơ chế `ClassLoader.loadClass(name)` thông thường |
| Nestmate tùy chọn | Không có class option tương ứng | `NESTMATE` option có thể tạo quan hệ nest theo API |
| Strength/lifetime option | Theo class/loader thường | `STRONG` option cho hidden class theo quy tắc riêng |
| Mục đích | Named helper class trong runtime package | Runtime-generated implementation chi tiết, lambda-like internals |

**Đừng gọi `defineClass` với bytes của một class thông thường rồi gọi nó là hidden class.** Hai API có hợp đồng khác nhau về naming, initialization, privilege và lifecycle. Một số use case generated implementation không muốn chiếm binary name lâu dài có thể phù hợp hơn với hidden class, nhưng phải hiểu nest/module access và class data APIs.

### Hidden class có nghĩa “không thể rò rỉ bộ nhớ” không?

Không. Hidden class vẫn có thể bị giữ bởi object, method handle, `Class<?>`, registry hoặc reference khác. Điều kiện thu hồi phụ thuộc reachability/cơ chế JVM và tùy chọn liên quan; không có API “tự biến mất ngay”. Dù class loader có thể sống lâu, hidden class thường được thiết kế cho những tình huống vòng đời linh hoạt hơn named classes thông thường, nhưng không thay thế cleanup các tài nguyên bên ngoài.

## 12. Bảo mật và tính toàn vẹn của bytecode

Một lookup có quyền PACKAGE là một **capability** mạnh: nó cho phép định nghĩa class mới vào namespace runtime của lookup class với protection domain tương ứng. Vì vậy phải kiểm soát **nguồn bytes** và **người giữ lookup**.

### Quy trình kiểm tra bytecode đầu vào

1. **Ràng buộc nguồn tin cậy:** compiler nội bộ hoặc artifact ký/được build từ pipeline đã xác minh.
2. **Ràng buộc namespace:** class mới thuộc đúng package dự kiến. API có kiểm tra cuối nhưng ứng dụng nên có validation và naming policy rõ.
3. **Giới hạn kích thước:** không đọc byte array cực lớn hoặc số lượng class không giới hạn.
4. **Kiểm tra class file header:** magic `CA FE BA BE` và major version là điều kiện sơ bộ, **không chứng minh tính an toàn**.
5. **Xác thực integrity:** kiểm tra SHA-256 hoặc chữ ký so với metadata từ nguồn tin cậy. Digest lấy từ cùng nguồn không tin cậy không xác minh publisher.
6. **Bytecode verification:** dựa vào JVM verifier và công cụ sinh/biến đổi bytecode phù hợp, không tự tin chỉ vì class có magic header.
7. **Dependency graph:** class mới có thể tham chiếu superclass/interface hoặc library ngoài loader/graph của host; cần nạp/link đúng.
8. **Naming collision:** dùng naming scheme đảm bảo không trùng các class đã định nghĩa; không cố re-define cùng binary name trong một loader.
9. **Audit:** log binary name, fingerprint artifact, lookup class, loader identity và module; tránh log raw secrets/bytecode.
10. **Quyền thực thi:** class hợp lệ vẫn có thể gọi API mà tiến trình được phép; xác minh logic hoặc dùng process isolation khi chạy mã không tin cậy.

**Bytecode verifier không phải sandbox.** Việc class được định nghĩa cùng protection domain với host có thể làm các rủi ro nghiêm trọng hơn nếu host trao quyền `Lookup.defineClass` cho code hoặc bytes không đáng tin cậy.

### Điều không nên làm

```java
// Minh họa chống chỉ định: không dùng như API công khai
public Class<?> defineAnyUserBytes(byte[] userBytes)
        throws IllegalAccessException {
    return MethodHandles.lookup().defineClass(userBytes);
}
```

Đây là **đoạn chống chỉ định**, không phải code mẫu production. Dù phương thức chưa vượt ranh giới package, nó biến ngữ cảnh lookup của class có quyền thành cổng định nghĩa class từ input không tin cậy. Nếu cần mở rộng plugin, hãy tạo kiến trúc phân quyền riêng và kiểm tra artifact kỹ hơn.

## 13. Giải quyết vấn đề trong named module

Với JPMS, class của một named module không chỉ có class loader và runtime package mà còn thuộc module trong runtime graph. Khi muốn định nghĩa class mới cùng package của một named module, nên để **anchor class của chính module/package đó** cung cấp lookup theo cơ chế hợp lệ.

Ví dụ khái niệm:

```java
module app.codegen {
    exports app.codegen.api;
    // app.codegen.internal không tự động export hoặc opens.
}
```

Nếu `app.codegen.internal.Anchor` muốn sinh class trong `app.codegen.internal`, có thể dùng một lookup được tạo đúng trong Anchor. Module khác không tự có quyền PACKAGE vào package này chỉ nhờ `requires app.codegen;` hoặc bằng cách biết chuỗi tên package.

### privateLookupIn và opens

Để lấy private lookup sang một class thuộc module khác, `MethodHandles.privateLookupIn` phải tuân thủ khả năng đọc module và việc package đích **mở** phù hợp với module của caller. Một package chỉ `exports` public API chưa đồng nghĩa code ngoại module được tạo lookup đặc quyền vào mọi class trong package.

Thực hành nên ưu tiên module chủ sở hữu **chủ động cung cấp capability hẹp** cho công cụ sinh mã đáng tin, thay vì sửa nhiều `--add-opens` chỉ để “vượt” ngăn cách JPMS.

### Cùng module không thay thế PACKAGE access

Ngay cả khi lookup class và class bytecode có thể thuộc cùng module, `defineClass` vẫn yêu cầu:
- Lookup có `PACKAGE` mode;
- Binary name trong bytes có package giống lookup class;
- Class file hợp lệ;
- Không có xung đột definition/linkage.

Không suy luận rằng module được resolve tức lookup được phép định nghĩa lớp ở mọi package trong module.

## 14. Chẩn đoán khi defineClass thất bại

Quy trình thực hành:

1. **Xác định lookup class thực tế.** Log `lookup.lookupClass().getName()` và `lookup.lookupClass().getClassLoader()`.
2. **Đọc lookup modes.** Kiểm tra quyền `PACKAGE` bằng mask; không dựa vào tên biến `trustedLookup`.
3. **Xác minh bytes.** Class file version, binary name, magic, checksum, source artifact và biến đổi bytecode.
4. **So package** trong class bytes với `lookup.lookupClass().getPackageName()`.
5. **Kiểm tra class đã được định nghĩa chưa.** Một loader không thể tạo hai named classes cùng binary name bằng cách lặp defineClass.
6. **Phân biệt lỗi access, format, verify, linking và initialization.** Mỗi loại cần giải pháp khác nhau.
7. **Nếu JPMS:** xem module của lookup class, caller và quy tắc mở package khi lấy Lookup.
8. **Nếu plugin nhiều loader:** xác định loader thực sự định nghĩa lookup class, không nhầm initiating loader/TCCL.
9. **Nếu gặp memory pressure:** named class đã định nghĩa bởi loader sống lâu không được “xóa” chỉ nhờ bỏ Class<?> local. Đánh giá loader lifecycle và code generation volume.
10. **Không dùng catch Throwable** để che các lỗi nghiêm trọng rồi tạo một class fallback sai ABI.

### Công cụ JDK hữu ích

Với bytecode có trên đĩa:

```bash
javap -verbose -classpath generated/classes demo.lookup.Generated
```

Đây là **lệnh minh họa** cho artifact thật: thay classpath root và tên class theo thực tế. `javap -verbose` cho biết major version, constant pool, flags, phương thức và tên nhị phân được lưu trong class file. Nó không xác minh toàn bộ chính sách bảo mật của generator.

Với ứng dụng có log class loading phù hợp:

```bash
java -Xlog:class+load=info -cp out demo.lookup.LookupDefineDemo
```

Các event class-load có thể giúp thấy class nào được JVM định nghĩa/nạp, nhưng không luôn hiện nguồn file theo cách giống URLClassLoader khi bytes được cung cấp trực tiếp cho Lookup. Kết hợp log ứng dụng về fingerprint/lookup class để chẩn đoán.

### Snippet in ngữ cảnh sau khi define

```java
static void printType(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
    System.out.println("package=" + type.getPackageName());
    System.out.println("domain=" + type.getProtectionDomain());
}
```

Đây là **helper method**, không phải chương trình standalone. Khi in protection domain hay code source, hãy tránh để lộ thông tin nhạy cảm trong production logs.

## 15. Lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Có bất kỳ Lookup object nào đều gọi defineClass được.” | Phải có `PACKAGE` mode và đúng package của lookup class. |
| “publicLookup có thể sinh class public trong mọi package.” | Không; publicLookup không có PACKAGE access. |
| “defineClass(bytes) tự chọn tên class từ biến filename.” | Tên nằm trong class file bytes; file name không quyết định. |
| “Lookup.defineClass tạo một ClassLoader mới.” | Không; dùng loader của lookup class. |
| “Cùng package string ở hai loader là cùng runtime package.” | Không; runtime package còn xét defining loader. |
| “Class mới được định nghĩa sẽ chạy static block ngay.” | Không; defineClass không tự chạy initializer. |
| “Một class đã tồn tại có thể được cập nhật bằng defineClass lần hai.” | Không; duplicate binary name trong cùng loader gây linkage conflict. |
| “Được quyền PACKAGE nghĩa là truy cập mọi private member của mọi class cùng package.” | Không; private/nest access có ràng buộc riêng. |
| “Một lookup của host có thể định nghĩa tùy ý trong loader của plugin.” | Không; loader gắn với lookup class. |
| “Named module đã exports thì code ngoài module có toàn quyền privateLookupIn.” | Không; cần xem opens/readability và điều kiện API. |
| “ClassFormatError nghĩa bytes độc hại.” | Chỉ có nghĩa cấu trúc class không hợp lệ; không đánh giá ý định của code. |
| “Class hợp lệ qua verifier là an toàn để chạy.” | Không; phải kiểm soát quyền, trust và side effects. |
| “Lookup.defineClass là defineHiddenClass.” | Khác nhau về naming, privilege, initialization và lifecycle. |
| “JVM tự dọn mọi named class khi local Class<?> về null.” | Không; class unloading phụ thuộc defining loader reachability và GC. |

## 16. Bài tập tự kiểm tra

**Câu 1.** Lookup được tạo bên trong `demo.codegen.Anchor`, bytes chứa `demo.codegen.Generated`. Nếu Lookup có PACKAGE mode và bytecode hợp lệ, class mới dùng loader nào?

**Trả lời:** Defining loader của `demo.codegen.Anchor`; cùng runtime package và protection domain với lookup class.

**Câu 2.** Bytes chứa `other.pkg.Generated`, còn lookup class ở `demo.codegen`. Điều gì xảy ra?

**Trả lời:** Khác package nên `Lookup.defineClass` ném `IllegalArgumentException` theo hợp đồng API, thay vì âm thầm đổi package.

**Câu 3.** Vì sao `MethodHandles.publicLookup().defineClass(bytes)` thất bại?

**Trả lời:** Public lookup không có `PACKAGE` access; API ném `IllegalAccessException`.

**Câu 4.** `defineClass` trả Class<?> thành công. Static block trong class mới đã chạy chưa?

**Trả lời:** Chưa chỉ vì defineClass. Initialization diễn ra sau đó theo quy tắc active use, ví dụ lần đầu gọi một static method thích hợp.

**Câu 5.** Cùng bytes được dùng với hai Lookup mà lookup classes do hai defining loaders khác nhau định nghĩa. Hai Class<?> kết quả có là cùng runtime class không?

**Trả lời:** Không nếu mỗi loader định nghĩa độc lập. Runtime class identity là (binary name, defining loader).

**Câu 6.** Có thể dùng `Lookup.defineClass` thay cho custom URLClassLoader để cô lập hai phiên bản thư viện trùng binary name trong cùng host loader không?

**Trả lời:** Không. Lookup cùng host loader không tạo loader isolation; hai định nghĩa cùng tên trong một defining loader là xung đột.

**Câu 7.** Muốn tạo class ẩn không được tìm bằng tên thông thường, API nào thích hợp hơn?

**Trả lời:** `Lookup.defineHiddenClass(...)`, với điều kiện full privilege, cùng package và quy tắc hidden class tương ứng.

**Câu 8.** Trong named module, việc chỉ `exports` package đích có bảo đảm `privateLookupIn` từ mọi module khác được không?

**Trả lời:** Không. Cần xét `opens`, quyền caller và module readability theo MethodHandles API.

**Câu 9.** Nếu `Generated.say()` gây lỗi do dependency thiếu sau khi class đã được define, có nghĩa `defineClass` không hề tạo class không?

**Trả lời:** Không. Có thể định nghĩa class thành công nhưng resolution/initialization hoặc lời gọi sau đó gặp lỗi.

**Câu 10.** Tại sao không nên expose một Lookup có PACKAGE mode cho mọi plugin chưa xác thực?

**Trả lời:** Nó cho phép định nghĩa class mới trong runtime package/protection domain của lookup class. Đây là capability mạnh, không phải bộ lọc an toàn của bytecode.

## 17. Checklist khi triển khai sinh class động

- [ ] Xác định rõ lookup class và loader/module chủ sở hữu namespace.
- [ ] Chỉ tạo/ủy nhiệm Lookup có `PACKAGE` access cho thành phần đáng tin cậy.
- [ ] Kiểm tra binary name/package trong bytes; tránh xung đột tên đã định nghĩa.
- [ ] Xác minh nguồn artifact/generator, kích thước, class version và integrity phù hợp.
- [ ] Không coi magic header hoặc verifier là sandbox.
- [ ] Dùng classloader riêng nếu yêu cầu isolation, reload hoặc package khác.
- [ ] Phân biệt `defineClass`, `defineHiddenClass` và `ClassLoader.defineClass`.
- [ ] Trên JPMS, kiểm tra readability/exports/opens khi lấy Lookup vào package mục tiêu.
- [ ] Biết rằng defineClass không tự chạy static initializer; kiểm soát active use.
- [ ] Bắt/ghi nhận lỗi theo đúng nhóm: access, format, verification, linkage, initialization.
- [ ] Giới hạn số lượng class được sinh trong loader sống lâu, theo dõi Metaspace và cache.
- [ ] Có log lookup class, loader identity, module, binary name và lỗi phù hợp.
- [ ] Không cố redefine named class trùng tên bằng lookup cũ.
- [ ] Với bytecode không tin cậy, dùng mô hình phân quyền hoặc process isolation thích hợp.

## 18. Kết luận và tài liệu chính thức

`MethodHandles.Lookup.defineClass(byte[])` không đơn thuần là “đọc byte[] rồi tạo class”. Đây là API **định nghĩa class theo ngữ cảnh được ủy quyền**: lớp mới phải có tên trong **cùng package** với lookup class; dùng **cùng defining ClassLoader, runtime package và protection domain**; lookup phải có `PACKAGE` access; và **class initializer chưa chạy** sau lời gọi defineClass.

Nó phù hợp để sinh named helper class cộng tác với package hiện có. Khi cần một namespace riêng, nhiều package, isolation hoặc hot reload, hãy xem xét custom ClassLoader. Khi cần hidden class, hãy dùng API hidden-class tương ứng. Dù chọn cách nào, JVM vẫn cần class file hợp lệ và việc chạy code phải tuân theo trust model của ứng dụng.

### Tài liệu đối chiếu

- Java SE 17 `MethodHandles.Lookup` — `defineClass`, `defineHiddenClass`, lookup modes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17 `MethodHandles` — `lookup()` và `privateLookupIn(...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 `ClassLoader` — `defineClass` và delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JVMS 17 §4 — The class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS 17 §5 — Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JLS 17 §12.4 — Initialization of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- JLS 17 §12.7 — Unloading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
