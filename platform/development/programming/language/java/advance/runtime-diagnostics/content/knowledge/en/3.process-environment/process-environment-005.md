# 3.5 Classpath, module path, thư viện native và cấu hình môi trường liên quan

Một ứng dụng Java có thể hoạt động ở máy phát triển nhưng thất bại khi khởi động hoặc chỉ hỏng một chức năng trên production dù cùng mã nguồn. Nguyên nhân có thể không nằm trong business logic: JVM được chạy bằng một JDK khác, class được lấy từ JAR khác, module không được resolve, class loader riêng nạp phiên bản thư viện khác, thư viện JNI thiếu dependency của hệ điều hành, hoặc cấu hình từ environment variable và working directory khác với điều người vận hành tưởng.

Bài này tập trung vào **chẩn đoán tiến trình JVM đang thực sự chạy**: dựng lại classpath và module graph có hiệu lực, xác định nguồn gốc một class/resource, kiểm tra native library và cấu hình môi trường, rồi liên hệ chúng với thông báo lỗi. Chỉ nhìn file cấu hình trong source repository hoặc chạy `java -version` ở terminal khác chưa đủ.

**Kết quả học tập:** phân biệt classpath, module path và native library path; biết đọc cấu hình launch và class loader; chọn bằng chứng theo triệu chứng; kiểm tra Java 17+ bằng công cụ chuẩn; nhận diện giới hạn của từng phép đo; và tái hiện chính xác sự khác nhau giữa hai môi trường.

## 1. Mô hình bốn tầng để dựng lại môi trường chạy

Một JVM tiến trình có ít nhất bốn tầng ảnh hưởng tới khả năng tìm mã:

1. **Runtime và lệnh khởi động:** đường dẫn executable thật, phiên bản vendor/JDK, JVM flags, `-D` system properties, launcher mode (`-cp`, `-jar`, `-m`), agent và option files.
2. **Class/module resolution:** classpath, module path, boot layer, module graph, các class loader (bootstrap, platform, application, custom), thứ tự và quy tắc delegate.
3. **Thư viện native và OS loader:** `java.library.path`, `System.loadLibrary`/`System.load`, phụ thuộc `.so`/`.dylib`/`.dll`, kiến trúc, ABI, libc, OS search paths.
4. **Môi trường triển khai:** process working directory, file mounts, environment variables, container image, Kubernetes Deployment/Pod, UID/quyền đọc/execute, shell script, cấu hình ứng dụng và secret injection.

Khi có sự cố, cần xác định **đường đi của class hoặc thư viện từ yêu cầu đến artifact thật**:

```text
Launcher / entrypoint / environment
                 |
                 v
  Java runtime + JVM options + cwd
                 |
       +---------+-----------+
       |                     |
       v                     v
  Classpath             Module path
  (unnamed module)      (named modules)
       |                     |
       +------> ClassLoader <-+
                    |
         Class / resource / ServiceLoader
                    |
          JNI / native bridge (nếu có)
                    |
      OS loader -> dependent native libraries
```

Sơ đồ chỉ mô tả hướng điều tra. **Một class không nhất thiết được nạp bởi application class loader**: framework, application server, plugin system, custom layers, agent và test runner có thể có loader riêng. Với mỗi class đang lỗi, ba thông tin cần biết là **tên class + defining class loader + nguồn code/resource**.

## 2. Classpath thực sự hoạt động thế nào?

### 2.1. Entry và thứ tự tìm kiếm

Classpath được truyền bằng `--class-path`, `-classpath` hoặc `-cp`; nó có thể gồm thư mục chứa `.class`, JAR và ZIP. Dấu phân cách path phụ thuộc hệ điều hành: **dấu hai chấm trên Linux/macOS**, **dấu chấm phẩy trên Windows**. Các entry tương đối được hiểu trong ngữ cảnh working directory và launcher.

Ví dụ trên Linux/macOS:

```bash
java -cp 'classes:lib/api.jar:lib/*' com.example.Main
```

Ví dụ tương ứng trên Windows (PowerShell/cmd):

```powershell
java -cp "classes;lib/api.jar;lib/*" com.example.Main
```

`lib/*` là wildcard đặc biệt của **Java launcher** để thêm JAR trong thư mục đó, không phải recursive search. Thứ tự các JAR được thêm bởi wildcard **không được bảo đảm**; không dùng nó như cơ chế chọn phiên bản ưu tiên. Trên shell Unix, đặt dấu nháy quanh classpath để shell không mở rộng `*` sai cách trước launcher.

Một class `com.example.Service` được tìm theo đường dẫn `com/example/Service.class` trong entry thích hợp. Với class loader truyền thống, thứ tự entry có ý nghĩa khi có **class trùng tên**, nhưng delegation, module resolution, multi-release JAR và custom loader cũng quyết định kết quả. “JAR xuất hiện trước trong danh sách” chỉ là một giả thuyết, chưa phải bằng chứng về class thực sự được nạp.

### 2.2. `CLASSPATH`, `-cp` và `java -jar` không tương đương

| Cách chạy | Classpath được chọn | Sai lầm dễ gặp |
| --- | --- | --- |
| `java com.example.Main` | Dùng `CLASSPATH` nếu launcher được cấu hình từ môi trường; nếu không, mặc định thường là `.` | Terminal hiện tại khác môi trường service |
| `java -cp 'classes:lib/*' com.example.Main` | `-cp` chỉ định classpath và ghi đè `CLASSPATH` của launcher | Nghĩ `CLASSPATH` vẫn được cộng thêm tự động |
| `java -jar app.jar` | `-jar` lấy main class từ manifest, không dùng user classpath từ `-cp` hoặc `CLASSPATH` theo cách chạy class trực tiếp | Cố thêm `-cp missing.jar` vào lệnh `-jar` rồi kỳ vọng library được nạp |
| `java -p mods -m app.module/com.example.Main` | Bắt đầu từ **named module** trên module path, theo module resolution | Cho rằng tất cả JAR trên `-p` đều tự động được resolve |
| Framework executable/fat JAR | Có thể dùng launcher và class loader riêng để nạp nested JAR | Chỉ nhìn `java.class.path` rồi kết luận toàn bộ dependency tree |

JAR manifest có thể chứa `Class-Path` để khai báo JAR phụ thuộc, theo quy tắc của Java JAR specification. Nhiều framework đóng gói thư viện trong cấu trúc đặc biệt (ví dụ nested JAR) và dùng loader riêng; cơ chế này **khác** classpath mặc định của Java launcher.

**Điểm cần nhớ:** `System.getProperty("java.class.path")` cho một phần thông tin cấu hình classpath mà system loader sử dụng. Nó **không nhất thiết liệt kê** tất cả JAR mà custom class loader đã nạp, module path, JAR nested hoặc thư viện native.

### 2.3. Classpath conflict và binary incompatibility

Giả sử lúc biên dịch, `checkout` dùng `payments-api-2.jar` có method `charge(String, long)`; khi deploy, một loader lại nạp `payments-api-1.jar` thiếu method đó. Ứng dụng có thể khởi động nhưng ném `NoSuchMethodError` khi đường code gọi method được chạy. Đây là lỗi **linkage/binary compatibility**: thay đổi cấu hình runtime hoặc artifact thực, không chỉ nhìn call stack.

Với duplicate class, cần phân biệt:

- **Tên class cùng FQCN nhưng khác loader**: tại JVM, type identity gồm cả binary name **và defining class loader**. Có thể gặp `ClassCastException` dù message in ra hai tên class giống nhau.
- **Một loader tìm thấy hai bản class**: cơ chế tìm kiếm, classpath order, JAR manifest và loader behavior quyết định bản nào được định nghĩa.
- **Compile-time khác runtime**: `NoSuchMethodError`, `NoSuchFieldError` hoặc `AbstractMethodError` thường chỉ ra bytecode kỳ vọng API khác với code đã được nạp.
- **Class tồn tại nhưng phụ thuộc của nó thiếu**: khi loader/linker cố resolve một loại khác có thể sinh `NoClassDefFoundError` hoặc lỗi liên quan. Một class cũng có thể ném `NoClassDefFoundError` sau lỗi khởi tạo trước đó, nên phải xem `Caused by` đầu tiên.

Công cụ `jdeps` phân tích dependency ở **bytecode tĩnh**, giúp tìm dependency thiếu, nhưng **không** tìm đầy đủ dependency được load bằng reflection, `ServiceLoader`, JNI hoặc các chuỗi tên class ghép động. Không xem kết quả `jdeps` là bản sao runtime class graph.

## 3. Module path và Java Platform Module System (JPMS)

### 3.1. Named và unnamed module

Từ Java 9, hệ thống module phân chia các gói vào module và có quan hệ **readability** (`requires`), **exports** cho Java access bình thường, **opens** cho deep reflection khi thích hợp. Bytecode trên classpath thuộc **unnamed module** của loader tương ứng; một modular JAR hoặc exploded module trên module path có thể tạo **named module** khi được resolve.

Ví dụ:

```java
module com.example.checkout {
    requires java.sql;
    requires com.example.contracts;
    exports com.example.checkout.api;
    opens com.example.checkout.internal to com.example.framework;
}
```

Đây là **đoạn minh họa của `module-info.java`**, không thể biên dịch độc lập khi thiếu các module/gói được nêu. `requires` thể hiện dependency module; `exports` cho phép nơi khác truy cập các public type trong package; `opens` cho phép truy cập reflection sâu tới package theo phạm vi khai báo. `exports` và `opens` không cùng ngữ nghĩa.

### 3.2. Module path là nơi có module, còn resolution chọn những module được sử dụng

`--module-path` (`-p`) trỏ tới các module khả dụng. Resolution bắt đầu từ root modules, đọc `requires` và các lựa chọn launcher. **Một JAR xuất hiện trên module path chưa có nghĩa module đó được đưa vào boot layer**. Module path có thể gồm:

- **Explicit module:** có `module-info.class`.
- **Automatic module:** JAR không có descriptor chính thức nhưng được đặt trên module path và được dùng như automatic module theo quy tắc đặt tên/metadata.
- **Exploded module:** thư mục output chứa `module-info.class` và class files.

Các lỗi điển hình:

- `Module ... not found`: tên module cần thiết không quan sát được hoặc thiếu dependency trong module path/runtime image.
- `FindException`/`ResolutionException`: các module không resolve được, có xung đột package, tên hay quan hệ.
- `IllegalAccessError` và `InaccessibleObjectException`: API hoặc reflection truy cập package không có quyền tương ứng.
- `ServiceConfigurationError`: module/provider khai báo hoặc được load không đúng, implementation không hợp lệ hay dependency hỏng.

**Đừng sửa bằng cách đẩy toàn bộ JAR lên classpath.** Làm thế có thể che lỗi module, phá service resolution hoặc dẫn tới cách nạp class khác.

### 3.3. `--add-exports`, `--add-opens` và `--add-reads`

| Option | Điều chỉnh | Thường dùng để điều tra |
| --- | --- | --- |
| `--add-exports source.module/pkg=target.module` | Xuất một package sang module đích để cho phép Java access thích hợp | Public/internal type không được export |
| `--add-opens source.module/pkg=target.module` | Mở package cho deep reflection của module đích | Framework phản chiếu field/constructor bị chặn |
| `--add-reads source.module=target.module` | Thêm readability edge giữa modules | Một named module không đọc được module khác |

`ALL-UNNAMED` có thể làm đích cho các option phù hợp khi code đích ở classpath. Những flag này **thay đổi chính sách đóng gói của runtime**, không giải quyết nguyên nhân thiếu JAR hay phiên bản bytecode sai. Ưu tiên chỉnh dependency/module descriptor hoặc nâng cấp framework tương thích; dùng workaround theo module/package cụ thể, có ghi lý do và kế hoạch loại bỏ. Không thêm `ALL-UNNAMED` trên diện rộng chỉ để tắt lỗi mà chưa hiểu.

### 3.4. Lệnh kiểm tra module

```bash
# Xem module có thể quan sát trên runtime đang gọi lệnh.
java --list-modules

# Xem descriptor module cụ thể (ví dụ module JDK).
java --describe-module java.sql

# Kiểm tra một JAR có explicit/automatic module metadata.
jar --describe-module --file lib/example.jar

# Đọc dependency tĩnh của artifact, nếu đã có JAR thật.
jdeps --missing-deps --class-path 'lib/*' app.jar

# Khi có ứng dụng module hóa và cấu hình đầy đủ:
java --module-path mods --validate-modules
```

Các lệnh trên là **mẫu thao tác trong môi trường chuẩn bị để kiểm tra**, không mặc định phản ánh module graph của tiến trình production nếu lệnh dùng một JDK, file tree hoặc working directory khác. `java --list-modules` liệt kê module *observable* đối với cách gọi đó; đừng nhầm với danh sách module **đã resolve** trong JVM mục tiêu. `--show-module-resolution` có thể được thêm vào **lệnh khởi động tương ứng** để xem quá trình resolution, nhưng tạo một tiến trình thử riêng là thao tác mới, cần dùng đúng artifact/cấu hình.

### 3.5. Ví dụ module độc lập trên JDK 17+

Tạo ba thư mục/đường dẫn dưới đây trong một workspace học tập (lệnh shell minh họa Linux/macOS):

```text
src/
  demo.paths/
    module-info.java
    demo/paths/Main.java
mods/
```

Nội dung `src/demo.paths/module-info.java`:

```java
module demo.paths {
}
```

Nội dung `src/demo.paths/demo/paths/Main.java`:

```java
package demo.paths;

public class Main {
    public static void main(String[] args) {
        Module self = Main.class.getModule();
        System.out.println("module=" + self.getName());
        System.out.println("reads.java.base="
                + self.canRead(Object.class.getModule()));
    }
}
```

Biên dịch và chạy:

```bash
mkdir -p mods/demo.paths
javac -d mods/demo.paths src/demo.paths/module-info.java src/demo.paths/demo/paths/Main.java
java --module-path mods -m demo.paths/demo.paths.Main
```

Stdout trên JDK 17+:

```text
module=demo.paths
reads.java.base=true
```

`java.base` được tất cả module đọc theo quy tắc module system, dù ví dụ không khai báo `requires java.base`. Trong ứng dụng thực, `module-info.java` phải khai báo các quan hệ phù hợp; ví dụ nhỏ trên chỉ chứng minh cơ chế tên module và readability mặc định.

## 4. Class loader và nguồn gốc class/resource đang được nạp

### 4.1. Tên class chưa đủ để xác định phiên bản

Thứ tự quen thuộc của built-in loader là **bootstrap → platform → application**; loader tùy chỉnh có thể đi theo mô hình khác, như child-first trong một số plugin container. Khi một class được hỏi từ một loader, delegation thường ảnh hưởng class nào thực sự định nghĩa class đó. Vì vậy, log “có file `foo.jar`” chưa đủ để xác định `com.example.Foo` đang dùng từ đó.

Chọn theo triệu chứng:

| Cần biết | Cách lấy bằng chứng | Giới hạn |
| --- | --- | --- |
| Class có thuộc named module? | `SomeClass.class.getModule()` | Class trong unnamed module vẫn có module object |
| Class do loader nào định nghĩa? | `SomeClass.class.getClassLoader()` | `null` có thể biểu thị bootstrap, không phải thiếu loader |
| Class được nạp từ artifact nào? | `getProtectionDomain().getCodeSource()`; resource URL; class load log | `CodeSource` có thể `null` hoặc không đủ với generated/nested classes |
| Cùng resource có nhiều bản? | `ClassLoader.getResources("...")` | Tập và thứ tự kết quả phụ thuộc loader |
| Còn những loader nào trong JVM? | `jcmd <pid> VM.classloaders` hoặc `VM.classloader_stats` nếu hỗ trợ | Không chỉ ra tất cả mối quan hệ package/version bằng một lệnh |
| Class nào vừa load từ đâu theo thời gian? | `-Xlog:class+load=info` | Phải bật recording/log tương ứng; có overhead và lượng log |

Khi thấy `ClassCastException: com.example.Plugin cannot be cast to com.example.Plugin`, cần xem **hai class loader khác nhau**, chứ không vội đổi kiểu ép cast. Với `ServiceLoader`, thread context class loader và module layer cũng có thể quyết định provider nào được tìm.

### 4.2. Chương trình quan sát an toàn, có output xác định

Lưu file **`RuntimePathProbe.java`**:

```java
public class RuntimePathProbe {
    public static void main(String[] args) {
        Class<?> app = RuntimePathProbe.class;
        Class<?> core = java.util.ArrayList.class;

        System.out.println("app.named=" + app.getModule().isNamed());
        System.out.println("core.module=" + core.getModule().getName());
        System.out.println("core.bootstrap="
                + (core.getClassLoader() == null));
        System.out.println("app.resource.found="
                + (app.getResource("RuntimePathProbe.class") != null));
    }
}
```

Biên dịch và chạy **ở chế độ classpath** bằng JDK 17+:

```bash
javac RuntimePathProbe.java
java -cp . RuntimePathProbe
```

Stdout chính xác:

```text
app.named=false
core.module=java.base
core.bootstrap=true
app.resource.found=true
```

`RuntimePathProbe` chạy từ classpath nên thuộc unnamed module; `ArrayList` nằm trong `java.base` và do bootstrap loader định nghĩa. `getResource` trả về URL của file class trên classpath. Nếu thay đổi sang một deployment khác, những phép đo này phải chạy **trong cùng kiểu launcher/class loader của ứng dụng đó**; bản chạy thử đơn giản không chứng minh framework production nạp dependency theo cùng cách.

### 4.3. Đoạn mã truy vết nguồn gốc lớp

Trong code chẩn đoán có thể ghi một thông tin tối thiểu, đã lọc dữ liệu nhạy cảm:

```java
Class<?> type = com.example.api.Contract.class;
ClassLoader loader = type.getClassLoader();
java.security.CodeSource source =
        type.getProtectionDomain().getCodeSource();

String sourceUrl = source == null
        ? "<unknown>"
        : String.valueOf(source.getLocation());

System.out.println("module=" + type.getModule().getName());
System.out.println("loader=" + loader);
System.out.println("codeSource=" + sourceUrl);
```

Đây là **snippet minh họa**, chưa thể compile độc lập vì `com.example.api.Contract` phải được thay bằng class thật trong dự án. `CodeSource` có thể thiếu; một URL trỏ vào nested JAR hoặc jar đã bị relocate/shade cần được giải thích theo launcher cụ thể. Không tự đăng đường dẫn chứa tên tài khoản hoặc dữ liệu nhạy cảm lên log công khai.

Khi nghi duplicate resource, cân nhắc liệt kê bằng `getResources(...)` trong **đúng class loader** (không chỉ system loader). Ghi số lượng, loader identity, URL đã làm sạch. Nếu dùng reflection `Class.forName(name)`, mặc định nó có thể kích hoạt class initialization; khi chỉ muốn kiểm tra khả năng tìm class, dùng overload `Class.forName(name, false, loader)` và vẫn lưu ý class linkage có thể phát sinh.

### 4.4. Class loading logging và class loader thống kê

Một run thử trên Linux/macOS có thể bật:

```bash
java '-Xlog:class+load=info:file=classes.log:time,level,tags:filecount=3,filesize=20M' \
     -cp 'classes:lib/*' com.example.Main
```

`classes.log` ghi thông tin class loading theo cấu hình HotSpot/JDK; dung lượng tăng theo tải và lượng class nạp. Đây là **lệnh minh họa** cần thay bằng main class/args thật, và dùng trong staging/canary hoặc cửa sổ được cho phép; đừng mặc định bật mức log này lâu dài trên mọi instance. Với JVM đã chạy, `jcmd <pid> VM.classloaders` và `VM.classloader_stats` cho ảnh chụp cấu trúc/thống kê nếu command hỗ trợ. Chúng không cho bản đồ dependency chính xác bằng việc điều tra class quan tâm.

## 5. Native library: Java tìm tên, OS phải tải được file và dependency

### 5.1. Hai đường nạp khác nhau

`System.loadLibrary("codec")` truyền **tên logic**, không kèm prefix, extension hoặc path; nền tảng có thể ánh xạ điển hình thành `libcodec.so` trên Linux, `libcodec.dylib` trên macOS hoặc `codec.dll` trên Windows. `System.mapLibraryName("codec")` giúp xem ánh xạ trên JVM thực. Quá trình tìm thư viện phụ thuộc implementation, cấu hình `java.library.path` và hệ điều hành.

`System.load("/opt/app/native/libcodec.so")` dùng **đường dẫn tuyệt đối** tới file (minh họa Linux), bỏ khâu tìm theo tên logic của `loadLibrary`. Cả hai cuối cùng vẫn phụ thuộc OS dynamic loader và các thư viện thứ cấp.

Ví dụ chỉ minh họa, **không chạy được nếu máy không có native artifact**:

```java
// Chỉ chạy khi JNI library có thật và tương thích.
System.loadLibrary("codec"); // Tìm bằng tên logic.
System.load("/opt/app/native/libcodec.so"); // Đường dẫn tuyệt đối.
```

Không dùng cả hai câu trong một luồng startup chỉ để “thử may”. Chọn một cách nạp đúng theo sản phẩm; log lỗi đầu tiên, xác định thư viện ứng dụng và dependent libraries, kiểm tra phiên bản và kiến trúc.

### 5.2. `java.library.path` khác các biến đường dẫn của OS

| Thuộc tính hoặc biến | Ảnh hưởng điển hình | Cần kiểm chứng |
| --- | --- | --- |
| `-Djava.library.path=...` | Các thư mục JVM dùng để tìm native library theo tên | Giá trị runtime, đường dẫn có tồn tại/truy cập được; thay đổi property sau startup không là cách cấu hình nạp library được bảo đảm |
| `LD_LIBRARY_PATH` (Linux) | Đường tìm kiếm các shared objects của dynamic loader theo điều kiện hệ thống | Startup environment, `RPATH`/`RUNPATH`, quyền và cơ chế bảo mật |
| `DYLD_LIBRARY_PATH` (macOS) | Một nguồn thông tin cho dynamic loader macOS | System Integrity Protection / ký mã / policy có thể hạn chế ảnh hưởng |
| `PATH` (Windows) | Có thể góp phần vào Windows DLL search behavior | Search order thực còn phụ thuộc Windows loader flags, API và thư mục ứng dụng |
| `-agentpath` / `-agentlib` | Nạp native agent theo JVM option | Agent version/ABI, option, quyền; agent thay đổi hành vi JVM |
| `java.home` / `JAVA_HOME` | Runtime path thực trong JVM so với biến thường dùng bởi startup scripts | Hai giá trị không bắt buộc đồng nhất |

**Phân biệt hai câu hỏi:** “Java tìm thấy thư viện cấp một chưa?” và “OS loader có giải quyết được **mọi thư viện phụ thuộc** của nó không?”. Dù `/opt/app/native/libcodec.so` tồn tại, lời gọi nạp vẫn có thể thất bại vì nó cần `libssl.so`, `libstdc++.so` hoặc thư viện khác mà runtime image không có.

### 5.3. Các nhóm lỗi JNI/native thường gặp

| Biểu hiện | Nhánh kiểm tra | Bằng chứng cụ thể |
| --- | --- | --- |
| `no codec in java.library.path` | Thư viện cấp một không được tìm theo tên logic | `System.mapLibraryName`, `java.library.path`, file path, quyền |
| `cannot open shared object file` | File hoặc thư viện phụ thuộc thiếu / loader search path sai | Full error message, `readelf -d`, OS loader diagnostics |
| `wrong ELF class`, `bad CPU type`, DLL architecture mismatch | 32/64-bit, CPU architecture, ABI sai | `file`, `readelf -h`, `os.arch`, container image architecture |
| `undefined symbol` / incompatible version | Native ABI, symbol hoặc dependency version sai | Dynamic symbols, `SONAME`, `RPATH`/`RUNPATH`, exact artifact build |
| `Native Library ... already loaded in another classloader` | Một native library nạp qua loader khác nhau | Class loader owning JNI wrapper, plugin reload, lifecycle |
| `UnsatisfiedLinkError` khi gọi method native | Method JNI không có symbol/registration phù hợp | JNI method signature, package/class name, `RegisterNatives`, compiled library |
| JVM crash với `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION` | JNI/FFI/agent hoặc native runtime có thể gây lỗi memory | `hs_err_pid*.log`, native frames, core dump, dependency/ABI |

Một `UnsatisfiedLinkError` **không nhất thiết** là thiếu file `.so`: có thể do dependency của file thiếu, ABI không tương thích, method JNI chưa được liên kết, hoặc class loader ownership. Phải đọc **thông báo gốc cùng cause và native loader diagnostics**.

### 5.4. Công cụ đọc-only để kiểm tra native artifacts

Trên Linux, với **đúng file đã được triển khai**:

```bash
file /opt/app/native/libcodec.so
readelf -h /opt/app/native/libcodec.so
readelf -d /opt/app/native/libcodec.so
```

`readelf -h` cung cấp kiến trúc/định dạng ELF; `readelf -d` có thể cho `NEEDED`, `RPATH` và `RUNPATH`. `ldd` hữu ích với **binary đáng tin cậy**, nhưng đừng chạy nó trên thư viện không tin cậy vì trên một số hệ thống/cấu hình có rủi ro thực thi code. Trên macOS có `otool -L`; trên Windows có `dumpbin /DEPENDENTS` nếu công cụ phù hợp được cài. Những công cụ này không phải thành phần bắt buộc của JDK và có thể không hiện diện trong distroless container.

Với JVM đang chạy, `jcmd <pid> VM.dynlibs` (nếu HotSpot hỗ trợ) liệt kê các shared libraries **đã được nạp**. Thiếu tên thư viện trong danh sách có thể do library chưa được yêu cầu hoặc đã thất bại khi load; không đủ để kết luận đơn độc. Có thể đối chiếu với OS process mappings trong đúng PID namespace và quyền truy cập.

### 5.5. Container, libc và kiến trúc

Thư viện được biên dịch cho Linux/glibc không đương nhiên chạy trên image Linux/musl; file ARM64 không dùng được trên x86_64; Linux `.so` không thể được dùng như Windows `.dll`. Build pipeline có thể xuất đúng Java JAR nhưng mang theo native artifacts theo kiến trúc khác. Cần ghi **platform/CPU architecture của cả JVM và thư viện**, libc/native dependency closure, đường dẫn được mount, UID/GID, permission và container image digest. Không suy ra khả năng nạp native chỉ từ tên file.

## 6. Cấu hình môi trường nào thật sự ảnh hưởng tới JVM?

### 6.1. Lệnh launcher, option injection và system properties

Các yếu tố làm startup khác nhau có thể gồm:

- **Executable Java thực:** script gọi `$JAVA_HOME/bin/java` hoặc chọn qua `PATH`; trong container có thể là JRE custom image.
- **Tham số launcher:** `-cp`, `-jar`, `--module-path`, `-m`, `--add-modules`, `--add-opens`, `-Dkey=value`, `-javaagent`, `-agentpath`; thứ tự và đối tượng áp dụng có ý nghĩa.
- **`JDK_JAVA_OPTIONS`:** Java launcher có thể thêm option từ biến này vào trước option trên command line theo quy tắc JDK; phần khác vẫn phụ thuộc launcher/container script.
- **`JAVA_TOOL_OPTIONS`:** có thể tác động đến JVM options ở những cách khởi chạy thích hợp.
- **`_JAVA_OPTIONS`:** biến thường gặp ở một số HotSpot môi trường; không coi là API chuẩn có mặt trên mọi JVM.
- **Application config:** environment variables của framework, file cấu hình, arguments sau main class/JAR, profiles, secret mounts; có thể bị framework quy định precedence khác nhau.

Ví dụ cách gọi:

```bash
java -Dapp.mode=prod -cp 'classes:lib/*' com.example.Main --port=8080
```

Ở đây `-Dapp.mode=prod` là **JVM system property**; `--port=8080` xuất hiện **sau** tên main class nên là **application argument**, không phải Java launcher option. Nếu script tự xây dựng command line, đọc script *phiên bản triển khai* và kết quả launch thực; đừng mặc định thứ tự precedence của một framework mà chưa kiểm tra tài liệu của framework.

**Lưu ý bảo mật:** `VM.command_line`, `VM.system_properties`, process arguments, environment variables và app configs có thể chứa token/password hoặc đường dẫn nhạy cảm. Chỉ thu thập bằng quyền được phép, giới hạn trường cần xem và lọc trước khi chia sẻ; không dump toàn bộ `/proc/<pid>/environ` hay `printenv` lên chat/issue/log công khai.

### 6.2. Working directory và đường dẫn tương đối

Cùng lệnh `java -cp 'lib/*' Main` có thể chạy khác khi `cwd=/opt/app` và khi `cwd=/` vì `lib/*` trỏ tới hai vị trí khác. Tương tự, đường dẫn như `config/app.yml`, `./native` hay một file keystore tương đối phụ thuộc working directory hoặc cơ chế resolve riêng của framework.

Trong Java:

- `System.getProperty("user.dir")` phản ánh thuộc tính directory liên quan runtime; thường dùng để giải thích đường dẫn tương đối trong Java APIs.
- OS process current working directory là một sự thật ở mức tiến trình; trên Linux có thể xem `/proc/<pid>/cwd` nếu được phép.
- `System.getProperty("java.home")` mô tả Java runtime đang chạy; `JAVA_HOME` chỉ là biến môi trường có thể dùng để chọn executable trong startup script.

Không “chữa” bằng cách thêm một đường dẫn tuyệt đối hard-code cho mọi môi trường. Trước tiên xác định đường dẫn kỳ vọng, nơi file tồn tại thật, permission và cách ứng dụng xây đường dẫn; sau đó sửa packaging/deployment/config một cách có thể tái hiện.

### 6.3. Environment tại thời điểm process start khác shell của người điều tra

Một terminal mở sau sự cố có thể có `PATH`, `JAVA_HOME`, timezone hoặc proxy khác so với service systemd/Kubernetes. Các biến môi trường được **kế thừa khi process bắt đầu** (trừ cơ chế thay đổi đặc biệt trong tiến trình); sửa biến trong shell khác không cập nhật tự động JVM đang chạy. Có thể có các nguồn cấu hình chồng lên nhau:

```text
Image / OS defaults
   -> systemd unit / container environment / launch script
   -> JVM options and -D properties
   -> application arguments and framework config sources
   -> effective behavior inside the running process
```

Sơ đồ là luồng điều tra, **không phải một thứ tự override tổng quát** cho mọi framework. Trong Spring Boot hay ứng dụng có config framework khác, precedence từng property do hệ thống cấu hình đó quyết định, cần xác minh theo version.

### 6.4. File mount, quyền, case sensitivity và đường dẫn có khoảng trắng

- Linux thường phân biệt chữ hoa/chữ thường cho filename; Windows có hành vi khác. Một JAR/resource path đúng trên máy này có thể sai trên máy kia.
- `-cp 'my libs/*'` phải được quote đúng trên shell tương ứng; nếu path bị tách thành hai args, main class sẽ bị hiểu sai.
- JAR có thể ở đúng path nhưng user chạy Java không có quyền đọc; native library có thể cần quyền/trust policy phù hợp.
- Kubernetes ConfigMap/Secret mounts, symlink, init container và immutable image digest có thể khiến file thực không giống local build output.
- Fat JAR có thể chứa thư viện ở entry nội bộ khác với path người vận hành mong đợi; cần hiểu launcher.

Nếu config mất trên production, kiểm tra **path tuyệt đối sau resolve**, file existence, manifest/packaging và process identity. Đừng thử chmod 777 hoặc chỉnh file system rộng chỉ để xem lỗi có biến mất; điều này làm mất dấu nguyên nhân gốc và có rủi ro.

## 7. Chẩn đoán một JVM đang chạy bằng chứng cứ thu thập có kiểm soát

### 7.1. Xác định đúng process trước khi xem cấu hình

Một lộ trình read-only thường bắt đầu với thông tin workload/pod/service và PID, rồi dùng công cụ JDK tương ứng. Ví dụ trên hệ thống có JDK tools và quyền attach:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 help VM.classloaders
jcmd 12345 help VM.dynlibs
```

`12345` là PID ví dụ; trên container phải tính đúng PID namespace và user có quyền. `jcmd -l` có thể không liệt kê JVM trong container khác; lúc đó đối chiếu process/container runtime phù hợp. `VM.command_line` cho launch arguments của JVM đó; `VM.flags` cho các flag HotSpot được nêu; `VM.version` cho runtime thật. `jcmd <pid> help`/`help <command>` là nguồn chuẩn để xem command có tồn tại và tác động trên JVM cụ thể. Khi vấn đề là path, native lib hoặc class loader, chỉ gọi command cần thiết thay vì thu toàn bộ JVM data.

Có thể xem `VM.system_properties` nếu cần điều tra `java.class.path`, `java.library.path`, `java.home`, `user.dir`, nhưng kết quả có thể chứa secrets nên **đọc trong kênh được kiểm soát và chỉ xuất phần đã làm sạch**. Chỉ riêng `jcmd` command line cũng có thể chứa secret trong `-D...`. Với case nhạy cảm, ưu tiên phép đo nội bộ đã whitelist field.

### 7.2. Bộ bằng chứng tối thiểu theo câu hỏi

| Câu hỏi | Thu trước | Khi chưa đủ |
| --- | --- | --- |
| “Prod dùng JDK nào?” | `VM.version`, process executable, image digest | Đối chiếu build metadata, libc/OS architecture |
| “Vì sao thiếu class?” | exception chain, runtime launch mode, classpath/module path | Source của class qua loader/`CodeSource`, `jar tf`, `jdeps` |
| “Vì sao class có method khác?” | `NoSuchMethodError` signature, JAR versions và hashes | Xác minh class origin theo loader, `javap` API thật |
| “Vì sao module không resolve?” | Module name, `module-info`, `--module-path` và root set | `--show-module-resolution`, `--validate-modules` với launch cấu hình tương ứng |
| “Vì sao reflection bị chặn?” | Exception package/module/target, module descriptor | Kiểm tra exports/opens, framework version; workaround hẹp nếu cần |
| “Vì sao JNI không nạp được?” | Exact `UnsatisfiedLinkError` + system/native paths | OS dynamic dependencies, ABI/arch, `VM.dynlibs` |
| “Vì sao chỉ fail trong container?” | Image digest, command/args, cwd, mounts, UID, arch, env keys | So diff với instance lành và reproduce trong image tương đương |

**Mục tiêu là tìm sự khác biệt có thể chứng minh**, không phải tạo log/dump lớn. `jcmd` đa số lệnh ở đây là truy vấn ngắn nhưng vẫn có chi phí và yêu cầu quyền, nhất là với class loader có số lượng lớn; mỗi lần cần hạn chế tần suất.

### 7.3. Kiểm tra artifact offline mà không chạy application

Trên máy phân tích có đúng JAR artifacts:

```bash
jar tf app.jar
jar --describe-module --file app.jar
jdeps --missing-deps --class-path 'lib/*' app.jar

# Ví dụ kiểm tra public methods đã biên dịch trong bản thư viện nhận diện được.
javap -classpath lib/payments-api.jar -public com.example.payment.Api
```

`jar tf` đọc mục trong archive, `jar --describe-module` phân tích module metadata, `jdeps` tìm dependency từ bytecode, `javap` xem chữ ký API. Những lệnh này **không tự chứng minh runtime đã nạp bản JAR đó**; cần đối chiếu hash/đường dẫn đúng instance. Một class được tạo bằng reflection hoặc sinh code tại runtime có thể không xuất hiện trong báo cáo tĩnh.

Ghi version artifact từ manifest hoặc build metadata, path đã resolve, checksum/hash nếu quy trình hỗ trợ. Không chỉ dựa vào tên `payments-api.jar` vì cùng tên có thể chứa bytecode khác.

### 7.4. Bật chẩn đoán class loading khi cần

Nếu bằng chứng hiện tại chưa xác định được class nạp từ đâu, một run được kiểm soát có thể dùng `-Xlog:class+load=info` như mục 4.4 để ghi thời điểm/source class loading. Chọn khoảng log ngắn, giới hạn rotation và dung lượng, tính overhead. Trên JVM đang chạy, HotSpot `VM.log` có thể cho phép điều chỉnh unified logging nếu có quyền/cú pháp phù hợp, nhưng đây là **thay đổi trạng thái runtime**; phải có phương án đảo lại và đo ảnh hưởng. Không kích hoạt log chi tiết trên toàn cluster một cách tùy tiện.

## 8. Phân biệt lỗi theo vị trí thất bại

| Triệu chứng/cụm lỗi | Vùng nghi ngờ đầu tiên | Việc chứng minh trước khi sửa |
| --- | --- | --- |
| `Could not find or load main class` | Main class, `-cp`, FQCN/package, cwd | Launcher mode, class file path trong JAR/dir |
| `ClassNotFoundException` | Dynamic `loadClass`/reflection, loader và path | Loader đang dùng, class origin, dependency |
| `NoClassDefFoundError` | Thiếu transitive class hoặc failed initialization | Root cause đầu tiên, static initializer, parent/linking |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary version mismatch | Signature bytecode, bản class thực tế nạp |
| `ClassCastException` với hai tên giống nhau | Duplicate classes từ loader khác nhau | Identity của hai `ClassLoader` và artifact |
| `Module ... not found` | Module path/root resolution | Module name thực, descriptor, module search roots |
| `InaccessibleObjectException` | Reflection bị chặn bởi JPMS | Module/package nào cần `opens`, vì sao framework chạm vào |
| `ServiceConfigurationError` | ServiceLoader provider module/JAR metadata | `uses`/`provides` hoặc `META-INF/services` và provider class |
| `UnsatisfiedLinkError` | JNI load/search/dependent libs/ABI/method binding | Full native loader error, symbol, library path, architecture |
| `UnsupportedClassVersionError` | Class được build cho JDK mới hơn runtime | Class file version và JDK của tiến trình |
| Chỉ fail trên prod/container | Config precedence, cwd, mounts, JDK, CPU/libc | Diff có chứng cứ giữa môi trường lành và lỗi |

**Quan hệ cause không phải lúc nào một-một.** Ví dụ `NoClassDefFoundError` có thể là hậu quả của `ExceptionInInitializerError` xảy ra trước đó; `UnsatisfiedLinkError` có thể là không thấy native method symbol dù file đã được nạp. Luôn đi ngược error chain tới lỗi đầu tiên và ghi thời điểm tương ứng.

## 9. Quy trình xử lý sự cố: từ triệu chứng đến fix tái hiện được

### Bước 1 — Đặt câu hỏi hẹp và chốt identity

Ghi service, pod/container ID, PID, JVM start/uptime nếu cần, image digest, JDK vendor/version, command line, cwd và thời điểm xảy ra lỗi. Ví dụ: “Trên pod B, vì sao `com.example.Parser` chạy bằng implementation từ JAR cũ dù pipeline vừa deploy bản mới?” tốt hơn “Sửa classpath”.

### Bước 2 — Xác minh runtime thật

Đối chiếu `VM.version`, `VM.command_line`, JVM flags, runtime properties **đã lọc**, process executable, start script/image/manifest. Đảm bảo terminal debug không vô tình dùng JDK khác. Phân biệt JVM launch arguments, app args và framework settings.

### Bước 3 — Phân loại đường nạp

- Class bình thường trên classpath → kiểm tra entry, ordering/duplicate JAR, resource URLs, loader.
- Named module → kiểm tra module descriptors, module path, resolution roots, exports/opens.
- Custom loader/nested JAR/plugin → dùng API/diagnostics của chính loader, framework packaging, code source.
- JNI/native → kiểm tra `java.library.path`, file chính, OS dependent libraries, kiến trúc/ABI.

Không thay đổi nhiều biến cùng lúc: nếu vừa sửa classpath, đổi JDK và thêm `--add-opens` thì không thể biết nguyên nhân thật.

### Bước 4 — Chứng minh file và loader đang được dùng

Tìm class origin bằng in-process probe hoặc class loading log, đối chiếu JAR hash và dependency graph. Với native, dùng OS loader diagnostics và `VM.dynlibs` nếu có. Với configuration, kiểm tra effective value trong process (đã redacted) cùng nơi nó được nạp.

### Bước 5 — Dựng bản so sánh “lành vs lỗi”

| Thuộc tính | Instance chạy được | Instance lỗi | Cần kết luận |
| --- | --- | --- | --- |
| JDK/Java executable | JDK 17, image A | JDK 17, image B | Cùng major nhưng khác vendor/build hoặc image? |
| Launcher mode/args | `-cp` và explicit JAR | `-jar` | Phụ thuộc có được nạp theo cùng cơ chế? |
| Artifact hash | Hash X | Hash Y | Bản nào có method/resource mong muốn? |
| Class loader/source | System loader/JAR A | Custom loader/JAR B | Runtime thực sự chọn bản nào? |
| Module graph | Required module resolved | Missing module | Module path/root set/descriptor khác gì? |
| Native dependencies | glibc build phù hợp | Image musl | ABI/libc mismatch có đúng là nguyên nhân? |
| cwd/mount/env keys | Có `config/app.yml` | Mount vào chỗ khác | File có tồn tại và được đọc đúng path? |

Giá trị trong bảng là **ví dụ giả định**, không phải ghi nhận từ môi trường cụ thể. So sánh càng chính xác về artifact digest, loader và cwd càng dễ phát hiện sai khác có thể sửa tại build/deploy.

### Bước 6 — Sửa nhỏ nhất và xác minh

- Thiếu JAR → sửa dependency packaging hoặc launcher classpath đúng chỗ.
- Duplicate/conflicting JAR → chuẩn hóa dependency graph, loại trùng bằng build tool và kiểm tra code origin.
- JPMS access → điều chỉnh module descriptor hoặc nâng version framework; workaround mở package có phạm vi hẹp nếu cần.
- Native dependency/ABI → build chọn artifact phù hợp OS/CPU/libc, đóng gói đủ thư viện và đặt đúng loader paths.
- Config/cwd/secret mount → sửa deployment contract, launch script hoặc cấu hình nguồn phù hợp.

Kiểm tra lại bằng **cùng startup mode và image** từng lỗi, rồi quan sát load source, logs và health endpoint. Với production, triển khai/canary theo quy trình và giữ khả năng rollback; không thay đổi runtime flag ngẫu nhiên trên tất cả instance.

### Bước 7 — Lưu “runtime evidence record”

Một bản ghi ngắn nên gồm: identity của tiến trình/container; cách chạy; JDK version; `java.class.path` hoặc module roots; classloader + code source cho class lỗi; native libs liên quan + ABI; cwd/config keys; artifact hashes; nguyên nhân có bằng chứng; fix và kết quả xác minh. Không lưu secret value, credential hoặc toàn bộ env dump trong tài liệu chia sẻ rộng.

## 10. Ba ca phân tích minh họa

### Ca A — `NoSuchMethodError` chỉ xuất hiện sau deploy

**Triệu chứng:** service startup thành công, endpoint thanh toán fail khi gọi `Api.charge(String,long)`. Local test chạy tốt.

**Giả thuyết:** bản `payments-api` trong runtime không giống bản compiler đã dùng.

**Điểm đo:** exact method descriptor trong stack/error; `javap -public` trên JAR của pod lỗi; class origin của `Api.class` từ đúng loader; kiểm tra hash/version tất cả JAR nghi vấn, classpath và custom loader.

**Diễn giải:** nếu `Api.class` được định nghĩa từ JAR thiếu method, lỗi nằm ở binary mismatch. Không sửa bằng cách cast, bắt `NoSuchMethodError` rồi retry; cần giải quyết dependency resolution/packaging. Nếu JAR có method đúng, kiểm tra class loader thứ hai, relocation và signature thực khác tên method giống nhau.

### Ca B — `InaccessibleObjectException` sau khi chuyển sang JPMS

**Triệu chứng:** framework dùng reflection vào `com.example.model.internal` và bị chặn.

**Giả thuyết:** named module không mở package cho module chứa framework.

**Điểm đo:** tên source module, package, target module trong exception; `module-info.java` thực của artifact; module resolution và phiên bản framework. Kiểm tra liệu framework dùng `setAccessible(true)`/deep reflection hay chỉ Java access.

**Diễn giải:** `exports` giải quyết public API access nhưng không mặc định cho deep reflection private members; `opens` thường phù hợp hơn cho reflection có kiểm soát. Dùng `--add-opens` theo package/target như biện pháp chẩn đoán tạm thời nếu được phép, rồi sửa descriptor/framework tương thích.

### Ca C — `UnsatisfiedLinkError` chỉ trên Linux container

**Triệu chứng:** `System.loadLibrary("codec")` hoạt động trên laptop nhưng thất bại trên pod Linux.

**Giả thuyết:** thiếu `libcodec.so`, thiếu dependent `.so`, ABI/musl-glibc mismatch hoặc container chạy khác CPU architecture.

**Điểm đo:** full error; `java.library.path` đã lọc; path thực và permission; `file`/`readelf -h`; `readelf -d` để thấy NEEDED/RUNPATH; OS loader diagnostics; image architecture; `VM.dynlibs` nếu library đã tải được.

**Diễn giải:** có file chính chưa đủ; dependent libs hoặc ABI có thể sai. Không thêm bừa `LD_LIBRARY_PATH` toàn cục vì có thể chọn bản native khác cho thư viện không liên quan. Sửa image/native package ở build và chạy lại trên môi trường tương đương.

## 11. Những lỗi tư duy cần tránh

1. **Dùng `java -version` từ shell để kết luận JVM production chạy bản đó.** Hỏi đúng PID hoặc executable/image.
2. **Nhìn `java.class.path` và coi đó là toàn bộ dependency runtime.** Custom loader, module path, nested JAR, dynamic loading nằm ngoài phạm vi một property.
3. **Dựa vào tên JAR, không kiểm tra nội dung/hash.** Hai file cùng tên có thể khác bytecode.
4. **Cho rằng mọi module trên `--module-path` đều đã resolved.** Phải xem roots và `requires`.
5. **Giả định `--add-opens` đồng nghĩa sửa classpath hoặc binary version.** Chúng giải quyết vấn đề quyền reflection, không tạo missing class/method.
6. **Lẫn `java.library.path` với `LD_LIBRARY_PATH`, hoặc nghĩ file JNI chính tồn tại là đủ.** OS loader còn phụ thuộc các thư viện khác.
7. **Chỉ tìm type theo tên, bỏ qua classloader identity.** Hai class cùng tên khác loader là hai type khác nhau.
8. **Bỏ qua cwd, permission và path quoting.** Relative path thay nghĩa giữa IDE, systemd và container.
9. **Thay đổi system property tại runtime rồi kỳ vọng JVM/OS library search nạp lại tự động.** Những cơ chế đã khởi tạo/cached không được bảo đảm cập nhật.
10. **Bỏ qua `Caused by` của lỗi đầu tiên.** Exception sau khi class initialization fail thường chỉ là hệ quả.
11. **Dump toàn bộ args, environment và properties để gửi lên issue.** Rất dễ tiết lộ credentials.
12. **Bật class loading debug dài hạn trên mọi instance.** Nó thêm overhead và dữ liệu lớn; cần kiểm soát thời gian/tần suất và dung lượng.
13. **Khắc phục bằng copy JAR hoặc `chmod 777` thủ công trên pod.** Fix không tái lập trong build/deploy và có thể tạo rủi ro bảo mật.
14. **Sửa đồng thời nhiều thành phần.** Không thể xác định gốc nếu vừa đổi JDK, module flags, dependency và native search path.

## 12. Checklist thu thập và xác nhận

- [ ] Đúng PID/container/JVM start, đúng thời điểm xảy ra lỗi?
- [ ] Đã xác minh Java executable, vendor, JDK version và image/artifact digest thực tế?
- [ ] Đã phân biệt cách chạy `-cp` / `-jar` / `-m` và application arguments?
- [ ] Đã kiểm tra `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, `-D` và config precedence ở mức nguồn?
- [ ] Class lỗi thuộc named hay unnamed module, defining loader nào, code source/resource URL nào?
- [ ] Classpath entries và module path có đúng, có duplicate/conflicting JAR, module resolution lỗi hay không?
- [ ] Có phân biệt `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` và lỗi access module?
- [ ] Với `ServiceLoader`/plugin, đã xem đúng context loader và provider metadata?
- [ ] Với JNI, đã kiểm tra logical library name, `java.library.path`, OS dependencies, ABI/CPU/libc và quyền?
- [ ] Đã kiểm tra cwd, đường dẫn tương đối, case sensitivity, mounts và user permissions của tiến trình?
- [ ] Đã so sánh instance lỗi và instance lành bằng đúng artifact hashes/loader/env **sau khi lọc secrets**?
- [ ] Fix đã được kiểm chứng trên cùng mode/image, có bằng chứng class/library được load đúng?

**Bài tập vận dụng:** một service đóng gói `app.jar` chạy bằng `java -jar app.jar`, người vận hành thêm `-cp lib/new-api.jar` nhưng endpoint vẫn ném `NoSuchMethodError`. Hãy trình bày thứ tự kiểm tra: vì sao `-cp` không hoạt động như dự đoán với `-jar`, dependency được đóng gói/manifest/custom loader thế nào, class `Api` thực sự được nạp bởi loader nào từ file nào, chữ ký method có trùng bytecode không, và cách sửa packaging để tất cả instance có cùng artifact. Đáp án tốt nêu **bằng chứng thu được trước khi thay đổi** cùng phép xác minh sau deploy.

## Tài liệu tham khảo

- Oracle Java SE 17, [`java` launcher reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-cp`, `-jar`, `-m`, `--module-path`, `JDK_JAVA_OPTIONS`, `-Xlog`.
- Oracle Java SE 17, [`jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.command_line`, `VM.flags`, `VM.system_properties`, `VM.classloaders`, `VM.dynlibs`.
- Oracle Java SE 17, [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): system loader, classpath, delegated loading và resources.
- Oracle Java SE 17, [Module system resolution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): observable/root modules, readability và resolution.
- Oracle Java SE 17, [`System` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `java.class.path`, `java.library.path`, `System.load` và `System.loadLibrary`.
- Oracle Java SE 17, [`jdeps` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html), [`jar` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html), [`javap` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra artifact, dependencies và bytecode.
- Oracle, [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): native method binding, JNI library và interface với mã native.

Để chẩn đoán môi trường chạy Java một cách tin cậy, luôn ghép **cấu hình launcher thực + module/classloader thực + artifact thực + native dependency thực + OS/container context**. Chỉ khi các lớp này được kiểm chứng cùng một instance và thời điểm, ta mới có thể phân biệt lỗi code với lỗi đóng gói hoặc môi trường.