# Vai trò của findClass, defineClass và ràng buộc khi tự viết ClassLoader trong Java

## 1. Bài toán: tại sao cần hiểu hai phương thức này?

Trong Java, một lớp không chỉ là tệp `.class` trên đĩa. JVM phải tìm được bytecode, chuyển bytecode thành một đối tượng `Class<?>`, liên kết các kiểu mà bytecode tham chiếu tới và quản lý danh tính lớp trong suốt thời gian chạy. `java.lang.ClassLoader` cung cấp giao diện để một runtime tự quyết định lấy bytecode từ đâu: thư mục riêng, JAR plugin, bộ nhớ, kho nội bộ hoặc nguồn khác.

Khi viết một class loader tùy biến, hai phương thức thường xuất hiện cạnh nhau nhưng **không làm cùng một việc**:

- **`findClass(String name)`:** điểm mở rộng để *tìm cách tạo* lớp khi cơ chế nạp mặc định chưa tìm thấy. Thường đọc bytecode từ nguồn do loader quản lý rồi gọi `defineClass`. Nó không tự cung cấp cơ chế parent delegation nếu bị gọi trực tiếp.
- **`defineClass(String name, byte[] bytes, int offset, int length)`:** phương thức `protected final` của `ClassLoader` yêu cầu JVM định nghĩa một lớp từ bytecode; nó không tìm file, không quyết định tải từ parent hay child và không được override.
- **`loadClass(String name)` / `loadClass(String name, boolean resolve)`:** cổng nạp lớp dùng cơ chế mặc định: kiểm tra lớp đã nạp, thử parent rồi mới gọi `findClass`. Đây là nơi thực hiện *delegation*, đồng bộ hóa quá trình nạp và tùy chọn resolve.

Với một kiến trúc extensibility, sai lầm thường gặp là nghĩ “chỉ cần override `findClass` để nạp tất cả lớp từ plugin”. Trên thực tế, parent có thể đã tải lớp trước, JVM còn áp đặt quy tắc về danh tính, định nghĩa trùng, package, chữ ký, linking và concurrency.

**Mục tiêu học tập:** hiểu chính xác luồng nạp, viết được loader nhỏ an toàn theo parent-first, dự đoán class identity, phân biệt lỗi tìm lớp với lỗi định nghĩa và biết những điểm phải xử lý thêm khi chuyển từ ví dụ học tập sang plugin runtime.

## 2. Luồng mặc định: loadClass → findClass → defineClass

Với một lớp tên nhị phân `demo.plugin.HelloGreeter`, hợp đồng `ClassLoader.loadClass(name, resolve)` mặc định có trình tự:

```text
caller: loader.loadClass("demo.plugin.HelloGreeter")
                  |
                  v
    lock = getClassLoadingLock(name)
                  |
                  v
       findLoadedClass(name)
          | đã nạp? -> trả Class đã có
          v chưa có
       thử parent.loadClass(name)
          | tìm được? -> trả Class do parent/ancestor định nghĩa
          v không tìm được
       this.findClass(name)           <--- điểm override thường dùng
          |
          v
       lấy byte[] từ nguồn riêng
          |
          v
       this.defineClass(name, bytes, 0, bytes.length)
          |
          v
       Class<?> do this loader định nghĩa
          |
          v
       nếu resolve == true: resolveClass(result)
          |
          v
       trả về Class<?>
```

Các nhánh thực tế của `loadClass` mặc định:

1. `findLoadedClass(name)` kiểm tra loader này đã được JVM ghi nhận là *initiating loader* của lớp có tên đó chưa. Kiểm tra này tránh tạo cùng một lớp lần nữa trong chu trình nạp thông thường; class đã trả từ parent cũng có thể được ghi nhận cho initiating loader.
2. Parent loader được thử trước. Nếu parent không tìm được, phương thức tiếp tục tới `findClass(name)` của child. Khi parent là `null`, JVM dùng cơ chế nạp bootstrap tương ứng, nhưng không nên giả định `null` cho thấy tất cả lớp của platform.
3. `findClass` là nơi tìm bytecode riêng và **thường** gọi `defineClass`; đây là cách triển khai của ta, không phải điều `findClass` tự thực hiện.
4. Nếu yêu cầu `resolve=true`, `resolveClass` thực hiện linking. **Resolve khác initialize**: class initializer tĩnh không nhất thiết chạy ngay khi chỉ gọi `loadClass`.
5. Không tìm được lớp thì báo `ClassNotFoundException`. Bytecode có mặt nhưng không hợp lệ hoặc không liên kết được có thể tạo các lỗi khác thuộc `LinkageError`, không được biến tất cả thành “not found”.

Các bước trên diễn tả **implementation mặc định** trong Java 17. Runtime hoặc loader khác có thể override `loadClass` và thay đổi chính sách, nhưng khi đó chủ sở hữu phải tự đảm bảo đồng bộ hóa, recursion, giao ước parent/child và tương thích kiểu.

## 3. API nào chịu trách nhiệm cho việc gì?

| Thành phần | Vai trò | Điểm cần nhớ |
|---|---|---|
| `loadClass(String)` | Điểm gọi công khai, nạp theo logic loader | Tương đương gọi overload `loadClass(name, false)` |
| `loadClass(String, boolean)` | Chu trình nạp mặc định, delegation, lock, resolve tùy chọn | Có thể override, nhưng dễ tạo deadlock/duplicate class nếu sai |
| `findLoadedClass(String)` | Hỏi JVM về lớp đã được ghi nhận cho loader | `protected final`; không phải “quét file trên đĩa” |
| `findClass(String)` | Hook để tìm bytecode/lớp ngoài parent | Default ném `ClassNotFoundException` |
| `defineClass(String, byte[], int, int)` | Chuyển bytecode thành định nghĩa lớp gắn với loader này | `protected final`, có kiểm tra tên/bytecode và ràng buộc JVM |
| `resolveClass(Class<?>)` | Liên kết lớp được chỉ định | Không phải chạy constructor hay static initializer |
| `getClassLoadingLock(String)` | Cấp lock cho lượt nạp tên lớp | Default dùng cả loader hoặc lock riêng theo tên nếu parallel-capable |
| `findResource`/`findResources` | Hook tìm resource của loader | Hoàn toàn khác `findClass`; cần cho cấu hình SPI/resource plugin |

Tên truyền vào các phương thức nạp là **binary name**, ví dụ `demo.plugin.HelloGreeter` hoặc `demo.plugin.Outer$Inner`. Đường dẫn file tương ứng có thể là `demo/plugin/HelloGreeter.class`, nhưng chuỗi đường dẫn này **không** được truyền làm tên lớp cho `defineClass`.

Khi viết loader, **thường chỉ override `findClass(String)`** và kế thừa cơ chế `loadClass`. Đây là hướng được Javadoc khuyến nghị cho loader tuân theo parent delegation.

## 4. Quy tắc class identity: cùng tên chưa chắc cùng lớp

JVM phân biệt class theo **tên nhị phân + loader định nghĩa lớp**. Vì vậy:

- Child loader A định nghĩa `demo.plugin.HelloGreeter` và child loader B cũng định nghĩa `demo.plugin.HelloGreeter` từ cùng bytecode: hai đối tượng `Class<?>` **khác nhau**.
- Một class do parent định nghĩa, khi child tải qua parent delegation, vẫn có `getClassLoader()` trỏ tới **defining loader của parent**, không phải child gọi yêu cầu.
- Một lớp interface dùng chung, chẳng hạn `demo.api.Greeter`, cần được cả host và plugin tham chiếu tới **cùng định nghĩa**. Nếu plugin định nghĩa bản sao riêng của interface với loader khác, phép ép về interface của host có thể thất bại dù tên package/class giống nhau.
- Hai lớp cùng tên package nhưng do hai loader khác nhau định nghĩa không tự nhiên thuộc cùng *runtime package*. Quyền truy cập package-private không dựa duy nhất vào chuỗi tên package.

**Initiating loader** là loader mà JVM ghi nhận khi nạp/tham chiếu một lớp; **defining loader** là loader thực sự gọi `defineClass` để định nghĩa lớp đó. Với parent-first, hai vai trò có thể khác nhau. `clazz.getClassLoader()` cho biết defining loader (`null` đối với lớp do bootstrap định nghĩa), không nhất thiết là loader mà ứng dụng gọi `loadClass`.

Khi các lớp ở những loader khác nhau tương tác qua chữ ký method/field, JVM còn có **loading constraints** để các tham chiếu kiểu chung không bất đồng. Vi phạm có thể phát sinh dưới dạng `LinkageError`, không phải một lỗi ép kiểu thông thường. Quy tắc thiết kế hữu ích là để API/SPI chung ở loader cha, plugin ở loader con và tránh đóng gói lại bản API không tương thích bên trong từng plugin.

## 5. Ví dụ Java 17+ chạy độc lập: DirectoryPluginLoader

Ví dụ sau tạo một SPI ở host, một provider ở thư mục plugin riêng, rồi viết một `ClassLoader` tự tìm bytecode trong thư mục. Kết quả cho thấy `findClass` chỉ định nghĩa implementation khi parent không thấy nó; interface được chia sẻ qua parent.

**Giới hạn cố ý của ví dụ:** chỉ nạp `.class` từ một thư mục đáng tin, theo package `demo.plugin`, không hỗ trợ JAR, manifest, chữ ký, resource, hot reload, module layer hay sandbox. Với plugin đóng gói thành JAR chuẩn, `URLClassLoader` thường thuận tiện và hoàn chỉnh hơn một loader tự viết.

### 5.1. Cấu trúc tệp

Tạo thư mục làm việc `loader-demo/` có nội dung:

```text
loader-demo/
  src/
    api/demo/api/Greeter.java
    plugin/demo/plugin/HelloGreeter.java
    host/demo/app/LoaderWalkthrough.java
  build/                            (tạo khi biên dịch)
    api/
    plugin/
    host/
```

**Tệp `src/api/demo/api/Greeter.java`:**

```java
package demo.api;

public interface Greeter {
    String greet(String name);
}
```

**Tệp `src/plugin/demo/plugin/HelloGreeter.java`:**

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp `src/host/demo/app/LoaderWalkthrough.java`:**

```java
package demo.app;

import demo.api.Greeter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderWalkthrough {
    private static final class DirectoryPluginLoader extends ClassLoader {
        private final Path root;

        DirectoryPluginLoader(Path directory, ClassLoader parent) {
            super(parent);
            this.root = directory.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            // Host/API và JDK tiếp tục đi qua parent-first loadClass.
            if (!name.startsWith("demo.plugin.")) {
                throw new ClassNotFoundException(name);
            }

            Path classFile = root.resolve(
                    name.replace('.', '/') + ".class").normalize();

            // Giữ phép đọc nằm trong root của demo.
            if (!classFile.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytecode = Files.readAllBytes(classFile);
                return defineClass(name, bytecode, 0, bytecode.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(
                        "Unable to read class: " + name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path pluginDirectory = Path.of("build/plugin");
        ClassLoader sharedApiLoader = Greeter.class.getClassLoader();

        DirectoryPluginLoader first =
                new DirectoryPluginLoader(pluginDirectory, sharedApiLoader);
        DirectoryPluginLoader second =
                new DirectoryPluginLoader(pluginDirectory, sharedApiLoader);

        Class<?> one = first.loadClass("demo.plugin.HelloGreeter");
        Class<?> oneAgain = first.loadClass("demo.plugin.HelloGreeter");
        Class<?> two = second.loadClass("demo.plugin.HelloGreeter");

        Greeter provider = one.asSubclass(Greeter.class)
                .getDeclaredConstructor()
                .newInstance();

        System.out.println("providerByFirst=" +
                (one.getClassLoader() == first));
        System.out.println("sameWithinFirst=" + (one == oneAgain));
        System.out.println("sameNameAcrossLoaders=" +
                one.getName().equals(two.getName()));
        System.out.println("sameClassAcrossLoaders=" + (one == two));
        System.out.println("sharedApi=" +
                (Greeter.class.isAssignableFrom(one)
                && Greeter.class.isAssignableFrom(two)));
        System.out.println("bootstrapString=" +
                (first.loadClass("java.lang.String").getClassLoader() == null));
        System.out.println("greeting=" + provider.greet("Java"));

        try {
            first.loadClass("demo.plugin.NotThere");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing=ClassNotFoundException");
        }
    }
}
```

**Giải thích implementation:**

1. `DirectoryPluginLoader` chỉ override `findClass`. Inherited `loadClass` đảm nhận lock, kiểm tra cached class và tìm ở parent trước.
2. `super(parent)` nhận loader đã nạp `Greeter.class`, nên cả host và implementation dùng chung SPI. Tránh dùng `super(null)` trong ví dụ này.
3. `name.startsWith("demo.plugin.")` khoanh phần lớp cho plugin. Nếu parent đã định nghĩa cùng tên, cơ chế parent-first vẫn ưu tiên parent: prefix trong `findClass` **không tự biến loader thành child-first**.
4. `root.resolve(name.replace('.', '/') + ".class")` ánh xạ binary name sang path. `normalize` và `startsWith(root)` là kiểm tra biên đơn giản; chúng **chưa** xử lý symlink, race thay file hay mọi rủi ro từ nội dung không tin cậy.
5. `Files.readAllBytes` lấy nội dung class file. Nếu không thể đọc, phương thức ném `ClassNotFoundException` với nguyên nhân `IOException` được giữ lại. Khi `defineClass` phát hiện bytecode hỏng, lỗi liên kết không bị giấu thành “không tìm thấy”.
6. `defineClass(name, bytecode, 0, bytecode.length)` là chỗ JVM định nghĩa lớp thuộc `first` hoặc `second`. Nó có thể định nghĩa cùng binary name **ở hai loader khác nhau**, nhưng không được định nghĩa lặp hai lần trong cùng loader.
7. `asSubclass(Greeter.class)` kiểm tra type compatibility khi lấy implementation. Constructor công khai không tham số của plugin được gọi bằng reflection.

### 5.2. Biên dịch và chạy trên Windows PowerShell

Đứng trong thư mục `loader-demo/` và dùng JDK 17 trở lên:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/plugin,build/host | Out-Null
javac -d build/api src/api/demo/api/Greeter.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/HelloGreeter.java
javac -cp build/api -d build/host src/host/demo/app/LoaderWalkthrough.java
java -cp "build/api;build/host" demo.app.LoaderWalkthrough
```

### 5.3. Biên dịch và chạy trên Linux/macOS

```bash
mkdir -p build/api build/plugin build/host
javac -d build/api src/api/demo/api/Greeter.java
javac -cp build/api -d build/plugin src/plugin/demo/plugin/HelloGreeter.java
javac -cp build/api -d build/host src/host/demo/app/LoaderWalkthrough.java
java -cp "build/api:build/host" demo.app.LoaderWalkthrough
```

**Quan trọng:** lúc chạy, class path chứa **chỉ** `build/api` và `build/host`. Nếu thêm `build/plugin` vào lệnh `java -cp`, application parent loader có thể tìm `HelloGreeter` trước, khiến ví dụ không còn minh họa đúng ranh giới defining loader.

### 5.4. Stdout chính xác

```text
providerByFirst=true
sameWithinFirst=true
sameNameAcrossLoaders=true
sameClassAcrossLoaders=false
sharedApi=true
bootstrapString=true
greeting=Hello, Java
missing=ClassNotFoundException
```

**Cách đọc kết quả:**

- `providerByFirst=true`: class implementation thật sự được `first` định nghĩa vì parent không có `demo.plugin.HelloGreeter`.
- `sameWithinFirst=true`: gọi `loadClass` lần thứ hai trên `first` trả cùng `Class<?>`; inherited `loadClass` dùng thông tin lớp đã nạp thay vì định nghĩa lặp.
- `sameNameAcrossLoaders=true` nhưng `sameClassAcrossLoaders=false`: cùng tên và bytecode không đủ để tạo cùng runtime class nếu defining loader khác.
- `sharedApi=true`: hai class implementation đều implement bản `Greeter` do parent cung cấp. Vì vậy host có thể sử dụng interface chung.
- `bootstrapString=true`: `java.lang.String` được bootstrap loader định nghĩa (`getClassLoader() == null`); child đã delegate thay vì cố tự định nghĩa lớp nền tảng.
- `greeting=Hello, Java`: instantiate và gọi phương thức trên provider thành công.
- `missing=ClassNotFoundException`: không có file implementation nên `findClass` báo không tìm thấy; đây là case khác với bytecode tồn tại nhưng bị lỗi.

Ví dụ chạy tuần tự và không sửa tệp plugin khi đang nạp. Nó chưa chứng minh tương thích với môi trường host có SecurityManager, module system, cấu hình module layer hoặc class path bị thay đổi từ bên ngoài.

## 6. Các ràng buộc của defineClass: bytecode không phải cứ có là nạp được

`defineClass` là API có kiểm soát của JVM. Tên phương thức nghe giống “tạo class tùy ý”, nhưng Java bytecode và runtime vẫn phải tuân theo quy tắc ngôn ngữ và máy ảo.

### 6.1. Tên lớp, dữ liệu bytecode và phiên bản JDK

- Dùng overload có tên: `defineClass(name, bytes, offset, length)` hoặc overload có `ProtectionDomain`; overload chỉ nhận `byte[]` không kèm tên đã bị deprecated.
- `name` là binary name dự kiến, ví dụ `demo.plugin.HelloGreeter`, nên khớp tên trong class file. Nếu không khớp, lỗi thường là `NoClassDefFoundError` với thông tin *wrong name*.
- `offset` và `length` phải nằm trong giới hạn mảng; sai phạm vi sẽ dẫn đến `IndexOutOfBoundsException`.
- Bytecode phải là cấu trúc `.class` hợp lệ. Bytecode hỏng có thể tạo `ClassFormatError`, bytecode biên dịch cho phiên bản JVM mới hơn có thể tạo `UnsupportedClassVersionError` và bytecode vi phạm kiểm chứng có thể tạo `VerifyError`.
- Bytecode chứa tham chiếu tới dependency; `defineClass` thành công **không bảo đảm** mọi dependency sẽ link và mọi code có thể chạy. Lỗi liên kết/khởi tạo có thể xảy ra sau đó khi JVM cần đến kiểu hoặc thành viên.
- Phân biệt **load**, **link** (verify, prepare, resolve có thể diễn ra theo nhu cầu) và **initialize** (thực thi static initializer). `ClassLoader.loadClass` không tương đương `Class.forName(name, true, loader)` hoặc tạo instance.

Không nên lấy `bytes` từ nguồn không đáng tin rồi xem `defineClass` như một bộ sandbox: kiểm tra bytecode của JVM là kiểm tra cấu trúc/an toàn kiểu, không phải giới hạn hành vi nghiệp vụ của mã được chạy.

### 6.2. Không định nghĩa hai lần cùng lớp trong một loader

Một defining loader không thể định nghĩa cùng binary name hai lần. Trong đường nạp mặc định, `findLoadedClass` và lock giảm nguy cơ định nghĩa trùng. Nếu tự gọi `defineClass` lặp hoặc override `loadClass` sai, JVM có thể ném `LinkageError: attempted duplicate class definition`.

Để dùng phiên bản bytecode mới của cùng tên lớp, runtime thường phải tạo **class loader mới**, chuyển tham chiếu và vòng đời plugin sang phiên mới. `reload()` trên cơ chế khám phá dịch vụ hay đọc lại file không “ghi đè” định nghĩa lớp đã tồn tại trong cùng loader.

### 6.3. Package bị hạn chế, signer và sealing

- Loader ứng dụng thông thường không được tự định nghĩa lớp có tên thuộc namespace `java.*`; thao tác có thể dẫn đến `SecurityException`. Không dùng custom loader để giả lập hoặc thay thế các class nền tảng của JDK.
- Các lớp trong một package do **cùng loader** định nghĩa phải thỏa quy tắc nhất quán về bộ chứng chỉ/chữ ký của `CodeSource` khi `defineClass`. Không thể tùy tiện pha class có signer khác nhau trong cùng runtime package.
- Với loader dựa trên JAR có metadata package, `definePackage(...)` có thể được dùng **trước** `defineClass` để gắn specification/implementation metadata và `sealBase`. Khi `defineClass` tự tạo package ngầm, các thuộc tính đó không được suy ra đầy đủ từ JAR manifest của một loader tự viết.
- Nếu hỗ trợ sealed package, loader phải **tự thực thi chính sách sealing/nguồn JAR nhất quán** khi nhận class mới. Chỉ đọc file rồi gọi `defineClass` không thay thế toàn bộ quy tắc packaging của `URLClassLoader`.
- Dùng `getDefinedPackage(name)` để kiểm tra package được loader này định nghĩa; đừng nhầm với `getPackage(name)` cũ có thể trả package của ancestor.

Những ràng buộc này ảnh hưởng trực tiếp khi plugin đến từ nhiều JAR hoặc khi người viết loader định nạp class từ một nguồn tổng hợp mà không giữ thông tin package và code source.

### 6.4. ProtectionDomain không tự tạo cô lập bảo mật

Overload `defineClass(String, byte[], int, int, ProtectionDomain)` gắn một protection domain với class; overload không truyền domain sử dụng default `ProtectionDomain` theo JDK. `SecureClassLoader` còn cung cấp overload dựa trên `CodeSource`.

Tuy nhiên, không coi lựa chọn `ProtectionDomain`/class loader là giải pháp chạy plugin độc hại an toàn. Ở Java 17, cơ chế SecurityManager đã được deprecated for removal, và an toàn vận hành còn phụ thuộc môi trường/JDK/chính sách thực tế. Plugin cùng JVM vẫn có khả năng tiêu thụ CPU, bộ nhớ, tạo thread hoặc gây lỗi logic; sandbox đáng tin cậy thường cần ranh giới tiến trình/container/OS và quyền hạn riêng, không chỉ một custom class loader.

## 7. Delegation: khi nào nên override loadClass?

**Parent-first** là mặc định và thường là điểm khởi đầu tốt nhất cho SPI/plugin host:

1. API chia sẻ, JDK classes, logging contracts và kiểu dữ liệu chung được nạp từ parent.
2. Plugin implementation và dependency chuyên biệt được tìm ở child khi parent không thấy.
3. Host có thể cast provider về interface đã nạp từ parent.

**Child-first** có thể hữu ích nếu cần chọn phiên bản dependency khác giữa các plugin, nhưng việc override `loadClass` phải được thiết kế rõ. Nếu mặc định child-first cho mọi package, plugin có thể nạp lại API chung và làm mất tương thích. Một chính sách thực dụng khi cần child-first là **ưu tiên parent đối với JDK, SPI của host và package được xác định là shared**, còn package thực sự riêng của plugin mới được phép ưu tiên child.

Khi override `loadClass(String, boolean)`, mã phải chịu trách nhiệm:

- kiểm tra `findLoadedClass` và thực hiện đúng thứ tự truy vấn;
- khóa đồng bộ bằng `getClassLoadingLock(name)` hoặc cơ chế tương đương;
- không tạo vòng lặp ủy quyền parent ↔ child;
- không định nghĩa trùng nếu hai thread đòi cùng lớp;
- gọi `resolveClass(clazz)` đúng khi `resolve` được yêu cầu;
- giữ ranh giới API/SPI, package và loader constraints nhất quán.

Đừng override `loadClass` chỉ để log hoặc chỉ để đổi chỗ đọc file khi `findClass` đã đáp ứng yêu cầu. Nếu cần child-first, hãy lập bản đồ rõ package nào shared và package nào isolated, rồi viết test kiểm tra các tình huống class identity/method signature trước khi dùng trong runtime.

## 8. Đồng thời: getClassLoadingLock và parallel-capable loader

Loader có thể được gọi từ nhiều thread trong lúc khởi động ứng dụng hoặc nạp plugin. Nếu hai thread cùng yêu cầu `demo.plugin.HelloGreeter`, một implementation thiếu đồng bộ có thể khiến cả hai cùng thử `defineClass`, dẫn tới duplicate definition và trạng thái lỗi khó tái hiện.

Inherited `loadClass` của `ClassLoader` mặc định **synchronizes trên giá trị trả về từ `getClassLoadingLock(name)`** trong toàn bộ lượt nạp:

- Với loader **chưa đăng ký parallel capable**, lock mặc định là chính đối tượng loader. Lượt nạp các tên khác nhau sẽ bị tuần tự hóa trên cùng lock.
- Với loader đã đăng ký **parallel capable**, có thể dùng lock riêng theo binary name, cho phép các tên lớp khác nhau được nạp song song trong khi tên giống nhau vẫn được bảo vệ.
- `registerAsParallelCapable()` cần gọi trong khởi tạo tĩnh của lớp loader, trước khi tạo instance, và chỉ thành công nếu các lớp cha liên quan (trừ `Object`) cũng đã đăng ký. Trạng thái này không thể bật/tắt tùy ý trên instance sau đó.
- Đánh dấu parallel capable **không tự khiến mọi dữ liệu nội bộ thread-safe**: cache, map, jar handle, package definition, resource lookup và cấu trúc phụ phải tương thích concurrency.

Loader thư mục trong mục 5 chỉ dùng inherited `loadClass` và không khai báo parallel capable; đây là lựa chọn đơn giản, dễ hiểu. Nếu nâng cấp để tải đồng thời nhiều lớp, cần kiểm thử tải trùng tên và khác tên, xác minh lock granularity và hành vi parent delegation trước khi tối ưu throughput.

Tránh giữ những khóa tùy ý khi gọi lại code bên ngoài hay loader khác: dependency loading có thể lồng nhau, đặc biệt với plugin A và B phụ thuộc qua lại. Deadlock ở class loading thường khó chẩn đoán hơn lỗi đọc file.

## 9. Class loading không bao gồm resource loading

Một file plugin thường còn có `application.properties`, dữ liệu cấu hình, service descriptor và tài nguyên khác. Override `findClass` chỉ giúp nạp bytecode, **không tự khiến**:

```java
loader.getResource("META-INF/services/demo.api.Greeter");
```

trả ra tài nguyên thuộc thư mục plugin. Theo Javadoc Java 17, `findResource(String)` mặc định trả `null`, còn `findResources(String)` mặc định trả enumeration rỗng. Inherited `getResource` sẽ thử parent và sau đó các hook đó; vì vậy custom loader đọc được `.class` chưa chắc đọc được resource.

Hệ quả quan trọng với runtime extensibility:

- `ServiceLoader` trên class path tìm descriptor `META-INF/services/<SPI binary name>` qua cơ chế resource. Nếu loader không công bố resource, service discovery có thể rỗng dù `loader.loadClass("demo.plugin.HelloGreeter")` thành công.
- Code plugin gọi `Class.getResource*` hoặc `ClassLoader.getResourceAsStream` có thể không tìm được cấu hình đi kèm.
- Nếu plugin là JAR/URL, hãy cân nhắc `URLClassLoader` và kiểm tra chính sách resource; nếu custom source là bộ nhớ hoặc kho khác, triển khai `findResource`/`findResources` đúng ngữ nghĩa URL/stream thay vì chỉ thêm code `findClass`.
- Với **named modules**, class/resource visibility và encapsulation theo JPMS còn đặt điều kiện riêng. Không giả định resource trong package của named module luôn được đọc công khai.

Phần trình diễn mục 5 **không dùng `ServiceLoader`** và không cung cấp `META-INF/services`, nên không đòi hỏi override resource hooks.

## 10. Class path loader và named module loader khác nhau ở điểm nào?

Ví dụ trên biên dịch vào class path, nên các lớp do `DirectoryPluginLoader` định nghĩa thuộc **unnamed module** của loader đó. Nó không tự tạo một named module chỉ vì class nằm trong thư mục có package.

Java 9+ có thêm overload:

```java
protected Class<?> findClass(String moduleName, String name);
```

Khác với `findClass(String name)` thông thường:

- Hook hai tham số nhằm tìm class theo module cụ thể do loader định nghĩa; implementation mặc định gọi hook một tham số chỉ khi `moduleName == null`, còn module name khác `null` thì trả `null`.
- `ModuleLayer`, cách tạo layer, đóng gói module, exports/opens, package mapping và cách JVM liên kết module với loader cần được xử lý riêng.
- Override `findClass(String)` để đọc thư mục `.class` **không đủ** để coi runtime đã hỗ trợ đầy đủ các named modules.
- Loader có thể định nghĩa class từ unnamed module và tham gia môi trường JPMS, nhưng phải kiểm tra ranh giới package/module thực tế trước khi xây plugin isolation.

Chọn loader đơn giản hoặc `URLClassLoader` cho class-path plugin; dùng cơ chế module-layer phù hợp khi hệ thống yêu cầu named module isolation. Đừng coi `ClassLoader` và `ModuleLayer` là hai tên cho cùng một đối tượng.

## 11. Ràng buộc vận hành khi tự viết loader

### Đường dẫn, tài nguyên và nguồn bytecode

Loader mục 5 nhận directory tin cậy. Đưa đầu vào từ người dùng hoặc remote vào triển khai thật phải giải quyết thêm:

1. **Giới hạn namespace và root:** từ chối tên không đúng phạm vi, canonicalize đường dẫn, kiểm tra symlink/traversal và quyền truy cập file. `normalize()` chỉ xử lý các thành phần đường dẫn từ phía cú pháp, không bảo đảm file cuối cùng nằm dưới thư mục gốc nếu có symlink.
2. **Tránh đọc file quá lớn:** `Files.readAllBytes` cấp phát theo kích thước file. Với nguồn có thể bị tác động, xác minh giới hạn bytecode và kiểm soát TOCTOU/race đổi file nếu mức tin cậy đòi hỏi.
3. **Đóng tài nguyên và log nguồn:** mở `InputStream`, JAR, socket hoặc handle bằng vòng đời rõ ràng; log tên lớp, nguồn bytes và tên loader để điều tra lỗi. `defineClass` tự nó không đóng những tài nguyên đó.
4. **Giữ nguyên lỗi có nghĩa:** trả `ClassNotFoundException` nếu không tìm/đọc được lớp theo hợp đồng; để `LinkageError`/`SecurityException` có ngữ cảnh khi class đã được tìm nhưng JVM từ chối định nghĩa.
5. **Tính bất biến của bytecode:** không thay bytes giữa lúc kiểm tra/chọn nguồn và lúc định nghĩa mà không có chính sách snapshot; plugin hot swap nên dùng loader mới với state và ownership mới.
6. **Phân biệt class và resource:** không giả định nạp implementation thành công nghĩa là resource, native library hay SPI descriptor đã được hỗ trợ.

### Vòng đời và class unloading

Classloader không có phương thức “unload đúng lớp X”. Lớp đã được định nghĩa không được gỡ ra khỏi **cùng loader** để rồi nạp lại tên đó với bytecode khác. JVM có thể giải phóng lớp khi defining loader và các lớp/instance liên quan không còn được giữ sống, tùy điều kiện GC và runtime.

Các tham chiếu thường cản việc giải phóng gồm `static` cache ở host, listener/subscription chưa hủy, thread/TCCL, `ThreadLocal`, executor task, reflection metadata và `Class<?>` được giữ trong registry. Với loader giữ JAR/socket, cần đóng handle; khác với loader đọc file rồi thả stream ngay như ví dụ.

Với hot reload: dựng loader mới, nạp phiên bản plugin mới, chuyển giao lifecycle có kiểm soát, dừng callback cũ, xóa reference rồi đóng tài nguyên của phiên trước. Không kỳ vọng gọi `loadClass` hoặc `findClass` lần nữa trên loader cũ sẽ thay thế lớp đã định nghĩa.

## 12. Chẩn đoán lỗi đúng tầng

| Dấu hiệu | Tầng cần xem | Cách kiểm tra |
|---|---|---|
| `ClassNotFoundException` từ `loadClass` | Discovery/delegation | Đúng binary name chưa? Parent và thư mục plugin nào đang được dùng? File có tồn tại? |
| `NoClassDefFoundError: wrong name` | Define/link | Tên truyền vào `defineClass` có khớp tên trong class file? |
| `ClassFormatError` | Bytecode format | Tệp có phải `.class` hợp lệ, bytes có bị cắt/chỉnh sai không? |
| `UnsupportedClassVersionError` | Bytecode/JDK version | `javac --release` hoặc JDK runtime có phù hợp với class-file version? |
| `VerifyError` | Bytecode verification | Công cụ sinh/chỉnh bytecode có tạo stack map/instruction hợp lệ? |
| `LinkageError: duplicate class definition` | Identity/concurrency | Có định nghĩa cùng binary name hai lần trong một loader, bỏ qua cache/lock không? |
| `LinkageError: loader constraint violation` | Type identity | Có SPI/API trùng tên nhưng khác defining loader không? Quan hệ method signature có xung đột? |
| `ClassCastException` dù tên in giống nhau | Type identity | So sánh `clazz.getClassLoader()`, `interfaceClass.getClassLoader()` và `Class<?>` thực tế |
| `SecurityException` khi define | Tên package / signer / policy | Có cố định nghĩa `java.*`, trộn signer hoặc vi phạm policy? |
| `IllegalAccessError` hoặc `InaccessibleObjectException` | Access/module | Package-private qua loader khác, JPMS exports/opens hoặc reflection access |
| `ServiceLoader` rỗng dù `loadClass` thành công | Resource/discovery | Loader có tìm được `META-INF/services/...` hoặc cấu hình `uses/provides` đúng chưa? |
| OOM hoặc không unload sau redeploy | Lifecycle | Còn registry/cache/thread/TCCL giữ class, instance hay loader cũ? |

Trong log, nên ghi binary name, nguồn bytecode, initiating/defining loader, parent, exception cause và phiên plugin. Không đưa mọi `LinkageError` vào `catch (ClassNotFoundException)`; chúng có ngữ nghĩa khác nhau. Đặc biệt lỗi “file không tồn tại” khác lỗi “file tồn tại nhưng định nghĩa không hợp lệ”.

## 13. Bộ kiểm thử tối thiểu và quyết định thiết kế

Trước khi dùng một custom loader trong runtime, viết integration test riêng cho các điểm:

- **Delegation:** class thuộc host/JDK được parent nạp, class implementation riêng của plugin do child định nghĩa; không nạp duplicate SPI.
- **Cache:** gọi `loadClass` lặp trên một instance trả đúng `Class<?>` đã có, không gọi `defineClass` lần hai.
- **Identity:** hai loader độc lập nạp cùng tên tạo hai định nghĩa khác nhau; cả hai vẫn implement chung interface host nếu parent được cấu hình đúng.
- **Missing vs malformed:** thiếu file trả `ClassNotFoundException`; bytecode hỏng/không khớp tên cho lỗi bytecode/linking phù hợp.
- **Concurrency:** nhiều thread cùng tải một tên và nhiều tên khác; xác minh không duplicate definition, deadlock hoặc đọc dữ liệu nửa chừng.
- **Package và nguồn JAR:** metadata/chứng chỉ/sealing được xử lý theo chính sách; plugin khác signer không bị ghép sai.
- **Resource:** provider descriptor/configuration được tìm đúng nếu ứng dụng dựa vào `ServiceLoader`.
- **Lifecycle:** unload/redeploy loại được listener, cache, reference và handle; TCCL được khôi phục nếu runtime có thay đổi.
- **Giới hạn nguồn:** path traversal, symbolic link, class file quá lớn, lỗi I/O và JAR không tin cậy được xử lý theo mô hình threat thực tế.

Khi chỉ cần nạp class từ JAR/URL chuẩn, ưu tiên kiểm tra khả năng dùng `URLClassLoader` hoặc cơ chế module có sẵn trước khi tự viết loader. Chỉ viết `findClass` tùy biến khi thật sự có nguồn bytecode, chính sách resolution hay nhu cầu lifecycle khác biệt mà công cụ chuẩn không đáp ứng.

**Quy tắc nhớ:** `loadClass` chọn **đường nạp và delegation**, `findClass` quyết định **tìm lớp ở đâu khi parent chưa giải quyết được**, còn `defineClass` yêu cầu JVM **định nghĩa bytes thành class thuộc loader này**. Mọi quyết định đều chịu ràng buộc class identity, bytecode/linking, package, concurrency và vòng đời.

**Tài liệu chính thức:** [Java SE 17 ClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [Java SE 17 SecureClassLoader Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureClassLoader.html) và [JVM Specification — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).
