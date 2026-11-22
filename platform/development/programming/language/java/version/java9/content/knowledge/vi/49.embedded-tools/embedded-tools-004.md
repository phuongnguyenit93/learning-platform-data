# Vị trí mô-đun qua getLocationForModule và listLocationsForModules

## 1. Vì sao công cụ Java nhúng cần hiểu vị trí mô-đun?

Khi viết một công cụ chạy **Java compiler ngay trong ứng dụng**, chẳng hạn một hệ thống biên dịch bài tập, bộ kiểm tra mã nguồn, plugin build hoặc công cụ tạo tài liệu, API `javax.tools.JavaCompiler` làm việc với các tệp nguồn và tệp class thông qua **`javax.tools.JavaFileManager`**. File manager quyết định công cụ sẽ tìm hoặc tạo những tệp đó ở đâu.

Từ Java 9, hệ thống Java Platform Module System (JPMS) cho phép chương trình chứa nhiều **named modules**. Khi đó, chỉ biết một đường tìm kiếm chung như `CLASS_PATH` là chưa đủ. Cùng một tên gói có thể cần được phân giải trong đúng mô-đun; compiler phải biết:

- Mô-đun `java.base` nằm ở đâu trong tập **system modules**?
- Mô-đun `demo.greetings` nằm ở đâu trong **module path**?
- Một `JavaFileObject` thuộc mô-đun nào?
- Có những mô-đun nào trong một vị trí tập hợp nhiều mô-đun?
- Sau khi chọn đúng mô-đun, làm sao mới đọc được `com.example.Service` hoặc `module-info.class`?

Hai phương thức cốt lõi vẫn có mặt trong Java SE hiện hành:

```java
JavaFileManager.Location getLocationForModule(
        JavaFileManager.Location location, String moduleName)
        throws IOException;

JavaFileManager.Location getLocationForModule(
        JavaFileManager.Location location, JavaFileObject file)
        throws IOException;

Iterable<Set<JavaFileManager.Location>> listLocationsForModules(
        JavaFileManager.Location location)
        throws IOException;
```

Các chữ ký trên là **trích đoạn API**, không phải một chương trình độc lập. Chúng là những **default methods** được bổ sung vào `JavaFileManager` từ Java 9; việc triển khai mặc định có thể ném `UnsupportedOperationException`. File manager của JDK có hỗ trợ nhận biết mô-đun, còn file manager tự viết phải cung cấp triển khai tương ứng nếu muốn công cụ biên dịch module hoạt động đúng.

**Mục tiêu bài học:** hiểu chính xác sự khác nhau giữa vị trí chứa **nhiều mô-đun** và vị trí chứa **một mô-đun**, sử dụng cả hai phương thức trong Java 17+, kết hợp với `inferModuleName` và các API đọc file, và xử lý đúng các giới hạn của nhà cung cấp file manager.

## 2. “Location” trong javax.tools là gì?

`JavaFileManager.Location` là một **đối tượng đại diện cho một vị trí logic** mà compiler/file manager nhận biết. Nó không đồng nghĩa trực tiếp với `java.nio.file.Path`, không nhất thiết là một thư mục vật lý, và không nên xử lý bằng cách tách chuỗi `getName()` rồi tự ghép đường dẫn.

Một location có các đặc tính:

- `getName()`: tên logic của location theo cách file manager định nghĩa.
- `isOutputLocation()`: location dành cho việc công cụ ghi kết quả hay không.
- `isModuleOrientedLocation()`: location có cấu trúc **module → package → class/file** hay chỉ **package → class/file**.

Hãy hình dung hai loại:

```text
Module-oriented location
    SYSTEM_MODULES / MODULE_PATH / MODULE_SOURCE_PATH
           |
           +-- module A
           |      +-- package x.y -> ClassA.class
           |
           +-- module B
                  +-- package z.t -> ClassB.class

Package-oriented location của một module
    getLocationForModule(MODULE_PATH, "module A")
           |
           +-- package x.y -> ClassA.class
           +-- package x.z -> ClassC.class
```

**Mối quan hệ quan trọng:** location cha kiểu *module-oriented* giúp tìm/chọn mô-đun. Kết quả `getLocationForModule(...)` là location dành riêng cho mô-đun đó, thường **package-oriented** để dùng với `list(...)`, `getJavaFileForInput(...)` và các API file manager khác.

Ví dụ, không thể xem `StandardLocation.MODULE_PATH` là một location gói thông thường rồi gọi `getJavaFileForInput(MODULE_PATH, "demo.api.Service", CLASS)` như thể mọi mô-đun chung một namespace. Trước hết phải xác định location của mô-đun chứa `Service`.

### Những StandardLocation liên quan

| StandardLocation | Ý nghĩa hiện hành | Cách tiếp cận |
| --- | --- | --- |
| `SYSTEM_MODULES` | Các mô-đun hệ thống của JDK | Module-oriented; có thể tìm `java.base` |
| `MODULE_PATH` | Tìm các mô-đun người dùng đã biên dịch | Module-oriented; phải có module path phù hợp |
| `MODULE_SOURCE_PATH` | Tìm mã nguồn của các mô-đun | Module-oriented; dùng trong biên dịch nhiều mô-đun |
| `ANNOTATION_PROCESSOR_MODULE_PATH` | Tìm mô-đun chứa annotation processors | Module-oriented; phục vụ công cụ xử lý annotation |
| `UPGRADE_MODULE_PATH` | Tìm mô-đun nâng cấp được phép theo cơ chế module system | Module-oriented; chỉ dùng khi hệ thống thực sự có nhu cầu |
| `CLASS_PATH` | Tìm các lớp theo đường classpath | Package-oriented; không dùng như parent của `getLocationForModule` |
| `SOURCE_PATH` | Tìm mã nguồn thông thường | Package-oriented |
| `CLASS_OUTPUT` | Vị trí ghi class files | Output location; `getLocationForModule` có thể trả output location riêng cho mô-đun |
| `SOURCE_OUTPUT` | Vị trí ghi tệp nguồn phát sinh | Output location |

Bảng nhằm chỉ ra cách chọn location. Không nên lấy mọi hằng số `StandardLocation` rồi giả định đều có các module được cấu hình. Đặc biệt, `MODULE_PATH` của một file manager mới có thể **chưa được cấu hình**, còn `SYSTEM_MODULES` có thể được tìm thấy từ runtime JDK mà không cần người dùng cấp JAR hay thư mục.

## 3. getLocationForModule(location, moduleName): tìm đúng mô-đun theo tên

Chữ ký:

```java
JavaFileManager.Location getLocationForModule(
        JavaFileManager.Location parent, String moduleName)
        throws IOException;
```

Trong đó:

- `parent`: location đang quản lý **một tập mô-đun**, ví dụ `StandardLocation.SYSTEM_MODULES`, `MODULE_PATH`, `MODULE_SOURCE_PATH`, hoặc một **output location** phù hợp.
- `moduleName`: tên mô-đun (chẳng hạn `java.base` hoặc `demo.greetings`), không phải tên gói hay tên class.
- Kết quả: location logic thuộc **mô-đun cụ thể**, thường package-oriented nếu parent là module-oriented; nếu parent là output location thì kết quả là output location.

Ví dụ cách gọi:

```java
JavaFileManager.Location javaBase =
        fileManager.getLocationForModule(
                StandardLocation.SYSTEM_MODULES,
                "java.base");
```

Đây là **đoạn mã minh họa**, cần một biến `fileManager` hợp lệ. Kết quả `javaBase` không tự động là `Path` tới một file JAR. Trong một JDK hiện đại, class của các system modules có thể được quản lý qua runtime image; phải dùng API của file manager thay vì đoán đường dẫn vật lý.

**Không tráo tên:** `java.base` là *module name*, còn `java.lang` là *package name* và `java.lang.String` là *binary class name*. Sau khi có location của `java.base`, mới dùng tên `java.lang.String` với `getJavaFileForInput(...)`.

### Khi location không hợp lệ hoặc provider không hỗ trợ

Theo hợp đồng `JavaFileManager`:

- Có thể nhận `IOException` khi thao tác trên dữ liệu gặp lỗi I/O.
- Có thể nhận `UnsupportedOperationException` nếu file manager chưa triển khai thao tác tìm vị trí mô-đun.
- Có thể nhận `IllegalArgumentException` khi location đưa vào không phải module-oriented hay output location.
- Với file manager cụ thể, cần kiểm tra kết quả và xử lý trường hợp module không được tìm thấy; đừng mặc định module nào cũng có trong mọi JDK hoặc module path.

Điểm cuối rất quan trọng: các mô-đun bổ sung của vendor, mô-đun tự tạo hay JAR thư viện không thể được coi là luôn tồn tại trên mọi máy. Chỉ `java.base` là mô-đun nền tảng mà mọi JDK tuân theo module system đều cần.

## 4. getLocationForModule(location, JavaFileObject): tìm mô-đun sở hữu một tệp

Overload thứ hai:

```java
JavaFileManager.Location getLocationForModule(
        JavaFileManager.Location parent, JavaFileObject file)
        throws IOException;
```

Khác với overload nhận `String`, bạn đã có một `JavaFileObject` (tệp nguồn, class, v.v.) và muốn xác định **mô-đun sở hữu tệp ấy** trong một parent location đã biết.

Ví dụ trên các system modules:

```java
JavaFileManager.Location base =
        fileManager.getLocationForModule(
                StandardLocation.SYSTEM_MODULES, "java.base");

JavaFileObject stringClass =
        fileManager.getJavaFileForInput(
                base, "java.lang.String",
                JavaFileObject.Kind.CLASS);

JavaFileManager.Location owner =
        fileManager.getLocationForModule(
                StandardLocation.SYSTEM_MODULES, stringClass);

String name = fileManager.inferModuleName(owner);
```

Đây là **đoạn mã minh họa**, yêu cầu `fileManager` và `stringClass` hợp lệ. Với standard file manager của JDK, `name` là `java.base`.

**Tại sao cần overload theo file?** Một công cụ phân tích có thể nhận một file object mà chưa biết trước tên module. Nó có thể hỏi file manager “trong tập mô-đun này, file thuộc mô-đun nào?” rồi sử dụng location trả về để phân giải các tệp liên quan. Đừng tự đoán mô-đun từ tên thư mục hoặc cắt đường dẫn URI: layout vật lý của module path, JAR, runtime image hoặc file manager tùy biến có thể khác nhau.

Cả hai overload đều yêu cầu **parent location** phù hợp; không truyền location dành cho package rồi kỳ vọng tự tìm được mô-đun ở đâu đó bên ngoài nó.

## 5. listLocationsForModules: liệt kê tất cả module locations

Chữ ký:

```java
Iterable<Set<JavaFileManager.Location>> listLocationsForModules(
        JavaFileManager.Location parent)
        throws IOException;
```

Giá trị trả về là **một chuỗi các tập (sets) gồm các location**. Đây không phải `List<String>` tên module, cũng không phải một `Set<Location>` phẳng. Để liệt kê toàn bộ module locations, phải dùng **hai vòng lặp**:

```java
for (Set<JavaFileManager.Location> group
        : fileManager.listLocationsForModules(parent)) {

    for (JavaFileManager.Location moduleLocation : group) {
        String moduleName =
                fileManager.inferModuleName(moduleLocation);
        System.out.println(moduleName);
    }
}
```

Đoạn trên cần import `java.util.Set`, một `fileManager` hợp lệ và `parent` đã được cấu hình. Nó cho thấy cách xử lý đúng kiểu trả về; không phải ứng dụng độc lập.

Những điều cần nhớ:

1. Một nhóm `Set<Location>` chứa **các vị trí của mô-đun**, không phải các tên file tùy ý.
2. Số nhóm, số location mỗi nhóm, thứ tự nhóm và thứ tự module không có hợp đồng “cố định và có sắp xếp”; không viết thuật toán phụ thuộc thứ tự lặp.
3. Khi cần hiển thị danh sách ổn định cho UI hoặc bản báo cáo, **trích tên module bằng `inferModuleName(...)` rồi tự sắp xếp**.
4. Khi cần kết quả *một* mô-đun, dùng `getLocationForModule(parent, moduleName)` trực tiếp thay vì quét mọi thứ chỉ để chọn một tên.
5. File manager tùy biến có thể không triển khai thao tác này; default implementation của interface ném `UnsupportedOperationException`.

### Tại sao còn cần inferModuleName?

`JavaFileManager.inferModuleName(moduleLocation)` chuyển location dành riêng cho một mô-đun thành **tên mô-đun logic**. Nó hoạt động với location do `getLocationForModule` hoặc `listLocationsForModules` trả về.

```java
JavaFileManager.Location moduleLocation =
        fileManager.getLocationForModule(
                StandardLocation.SYSTEM_MODULES, "java.base");
String moduleName =
        fileManager.inferModuleName(moduleLocation);
```

Không sử dụng `moduleLocation.getName()` rồi cắt chuỗi để khôi phục `java.base`. Tên location có thể chứa metadata nội bộ tùy file manager; `inferModuleName` mới là API diễn đạt ý định “tên mô-đun”.

## 6. Ví dụ hoàn chỉnh 1: tìm java.base và liệt kê system modules

Chương trình sau chạy bằng **JDK 17+** và không cần tải thư viện hay tạo project module. Dùng `ToolProvider.getSystemJavaCompiler()` để lấy compiler của JDK, rồi dùng `StandardJavaFileManager` tương ứng.

Tạo tệp **`ModuleLocationsDemo.java`**:

```java
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;
import java.util.Locale;
import java.util.Set;

public class ModuleLocationsDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run on a JDK providing the system Java compiler");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             null, Locale.ROOT, null)) {

            JavaFileManager.Location root =
                    StandardLocation.SYSTEM_MODULES;

            JavaFileManager.Location base =
                    files.getLocationForModule(root, "java.base");
            if (base == null) {
                throw new IllegalStateException(
                        "Required module java.base not found");
            }

            System.out.println("rootModuleOriented="
                    + root.isModuleOrientedLocation());
            System.out.println("module="
                    + files.inferModuleName(base));
            System.out.println("childPackageOriented="
                    + !base.isModuleOrientedLocation());

            JavaFileObject stringClass =
                    files.getJavaFileForInput(
                            base,
                            "java.lang.String",
                            JavaFileObject.Kind.CLASS);

            System.out.println("StringClassFound="
                    + (stringClass != null));

            if (stringClass == null) {
                throw new IllegalStateException(
                        "java.lang.String class file not found");
            }

            JavaFileManager.Location owner =
                    files.getLocationForModule(root, stringClass);

            System.out.println("ownerFromFile="
                    + files.inferModuleName(owner));

            boolean listed = false;
            for (Set<JavaFileManager.Location> group
                    : files.listLocationsForModules(root)) {

                for (JavaFileManager.Location each : group) {
                    if ("java.base".equals(
                            files.inferModuleName(each))) {
                        listed = true;
                    }
                }
            }
            System.out.println("javaBaseListed=" + listed);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 ModuleLocationsDemo.java
java ModuleLocationsDemo
```

Khi chạy với **standard file manager của JDK** có hệ thống module chuẩn, kết quả:

```text
rootModuleOriented=true
module=java.base
childPackageOriented=true
StringClassFound=true
ownerFromFile=java.base
javaBaseListed=true
```

Ý nghĩa của từng dòng:

1. `SYSTEM_MODULES` là **module-oriented location**.
2. `getLocationForModule(SYSTEM_MODULES, "java.base")` trả vị trí của named module `java.base`.
3. Vị trí **của riêng `java.base`** là package-oriented.
4. Với location đã được thu hẹp vào mô-đun `java.base`, `getJavaFileForInput(...)` tìm thấy `java.lang.String` dạng `CLASS`.
5. Overload `getLocationForModule(root, stringClass)` tìm lại mô-đun sở hữu JavaFileObject.
6. `listLocationsForModules(SYSTEM_MODULES)` có chứa module `java.base`; chương trình kiểm tra thành viên mà không phụ thuộc thứ tự.

**Đã kiểm chứng hành vi trên OpenJDK 24:** các thuộc tính `rootModuleOriented`, `module`, `childPackageOriented`, `StringClassFound`, `ownerFromFile` và `javaBaseListed` tương ứng với kết quả trên. Ví dụ chỉ dựa vào API có từ Java 9 và là chương trình có thể biên dịch bằng `--release 17`.

### Vì sao dùng try-with-resources?

`StandardJavaFileManager` triển khai `Closeable/AutoCloseable`; sau khi hoàn thành thao tác, đóng file manager giúp giải phóng tài nguyên nội bộ mà compiler/file manager có thể sử dụng. Các file object và module locations nhận từ nó cũng thuộc phạm vi quản lý của file manager; **đừng cố sử dụng location/file object lâu dài sau khi file manager đóng** mà không có hợp đồng cho phép.

## 7. Ví dụ hoàn chỉnh 2: duyệt MODULE_PATH của một module tự tạo

Ví dụ đầu sử dụng system modules sẵn có. Ví dụ tiếp theo cho thấy cách **cấu hình `MODULE_PATH` rồi tìm một named module đã biên dịch**, phù hợp hơn với một công cụ build/biên dịch nhúng thực tế.

### 7.1. Tạo module mẫu

Tạo cấu trúc tệp:

```text
workspace/
  src/
    demo.greetings/
      module-info.java
      demo/
        greetings/
          api/
            Greeter.java
```

**`src/demo.greetings/module-info.java`:**

```java
module demo.greetings {
    exports demo.greetings.api;
}
```

**`src/demo.greetings/demo/greetings/api/Greeter.java`:**

```java
package demo.greetings.api;

public final class Greeter {
    private Greeter() { }

    public static String hello() {
        return "Hello from a named module";
    }
}
```

Tại thư mục `workspace`, tạo module đã biên dịch:

```bash
javac --release 17 --module-source-path src -d mods -m demo.greetings
```

Kết quả có thư mục chứa module `mods/demo.greetings/` và class files (bao gồm `module-info.class`). `mods` lúc này là một đầu vào có thể đặt trên module path. Lệnh `javac` không in stdout khi thành công; nếu sai cấu trúc tệp hoặc nội dung source, compiler sẽ báo lỗi.

### 7.2. Dùng StandardJavaFileManager để khám phá module path

Tạo tệp **`ModulePathScan.java`** ở thư mục `workspace`:

```java
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class ModulePathScan {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ModulePathScan <module-path-root>");
            return;
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run on a JDK providing the system Java compiler");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             null, Locale.ROOT, null)) {

            files.setLocationFromPaths(
                    StandardLocation.MODULE_PATH,
                    List.of(Path.of(args[0])));

            JavaFileManager.Location module =
                    files.getLocationForModule(
                            StandardLocation.MODULE_PATH,
                            "demo.greetings");

            System.out.println("found=" + (module != null));
            if (module == null) {
                return;
            }

            System.out.println("module="
                    + files.inferModuleName(module));
            System.out.println("moduleLocationPackageOriented="
                    + !module.isModuleOrientedLocation());

            boolean listed = false;
            for (Set<JavaFileManager.Location> group
                    : files.listLocationsForModules(
                            StandardLocation.MODULE_PATH)) {

                for (JavaFileManager.Location each : group) {
                    if ("demo.greetings".equals(
                            files.inferModuleName(each))) {
                        listed = true;
                    }
                }
            }
            System.out.println("listed=" + listed);
        }
    }
}
```

Chạy:

```bash
javac --release 17 ModulePathScan.java
java ModulePathScan mods
```

Với cấu trúc module do mục 7.1 biên dịch thành công:

```text
found=true
module=demo.greetings
moduleLocationPackageOriented=true
listed=true
```

Nếu `mods` không chứa `demo.greetings`, kết quả phụ thuộc cách file manager phản ánh đường tìm kiếm không có module. Vì vậy đoạn mã kiểm tra `module != null` và không sử dụng location chưa được xác nhận.

**Giải thích:**

- `setLocationFromPaths(MODULE_PATH, List.of(Path.of("mods")))` đặt search path của **file manager này**. Nó không đổi `java.class.path` hay module path của chính JVM đang chạy.
- `getLocationForModule(MODULE_PATH, "demo.greetings")` chỉ tìm trong **module path đã cấu hình**, không lẫn sang `SYSTEM_MODULES`.
- `inferModuleName(...)` lấy tên module từ location; không cần suy đoán module dựa trên folder name.
- `listLocationsForModules(MODULE_PATH)` liệt kê các module locations hiện được nhận biết từ module path; ứng dụng khác nhau có thể có số module và thứ tự khác nhau.
- Một JAR đặt trên **classpath** không tự trở thành module trên **module path** của compiler. Nếu cần kiểm thử một modular JAR hoặc automatic module, phải cấu hình đầu vào module path phù hợp.

Đây là ví dụ hoạt động với **module đã được biên dịch**; nếu bạn muốn biên dịch nhiều module nguồn từ đầu, sẽ thường dùng `MODULE_SOURCE_PATH` cho nguồn và `CLASS_OUTPUT` cho class được tạo.

## 8. MODULE_SOURCE_PATH và CLASS_OUTPUT khi nhúng compiler

Trong một công cụ build hoặc trình biên dịch nhúng, có thể cần biết cả ba vị trí:

```text
MODULE_SOURCE_PATH --> chọn module nguồn
          |
          v
JavaCompiler biên dịch các JavaFileObject
          |
          v
CLASS_OUTPUT --> class files riêng cho từng module
          |
          v
MODULE_PATH --> tìm các module đã biên dịch để dùng làm phụ thuộc
```

Thứ tự trong sơ đồ là quan hệ vai trò, không phải thứ tự các API phải được gọi. Với một compiler task, nguồn, output và phụ thuộc phải được cấu hình thống nhất để compiler phân giải `requires`, package imports và module descriptor.

### Cấu hình module source path

Ví dụ minh họa khi file manager đã được tạo và thư mục tồn tại:

```java
files.setLocationFromPaths(
        StandardLocation.MODULE_SOURCE_PATH,
        List.of(Path.of("src")));
```

Đây là **trích đoạn**, không tự biên dịch cả module. Sau khi cấu hình, `getLocationForModule(StandardLocation.MODULE_SOURCE_PATH, "demo.greetings")` có thể dùng để tìm vị trí nguồn của module trong cách bố trí mà compiler/file manager hỗ trợ.

Để thực sự biên dịch module trong một tool nhúng, ngoài việc cấu hình file manager còn phải gọi `JavaCompiler.getTask(...)` với nguồn và tùy chọn nhất quán. Bản thân `getLocationForModule(...)` **không đọc/biên dịch source, không kiểm tra phụ thuộc và không sinh class files**.

### Cấu hình đầu ra theo mô-đun

`StandardJavaFileManager.setLocationForModule(...)` cho phép gán đường tìm kiếm dành riêng cho một module tại một **module-oriented location** hoặc **output location**:

```java
files.setLocationForModule(
        StandardLocation.CLASS_OUTPUT,
        "demo.greetings",
        List.of(Path.of("mods/demo.greetings")));
```

Đoạn minh họa giả định có `files` là `StandardJavaFileManager` và thư mục `mods/demo.greetings` **đã tồn tại**. Với output location, API có thể ném `IOException` nếu đường dẫn output không phải thư mục hiện có. Việc đặt location không tạo ra source hoặc class files; compiler vẫn phải được gọi để biên dịch.

Có hai điểm dễ mắc lỗi:

1. `setLocationForModule(...)` thay thế association dành cho module tại location được chỉ định; dùng cẩn thận nếu compiler đang tự suy ra đường dẫn theo search path chung.
2. **Gọi lại** `setLocation(...)` hoặc `setLocationFromPaths(...)` trên parent module-oriented/output location sẽ **hủy các module-specific associations** trước đó theo hợp đồng `StandardJavaFileManager`. Vì thế phải xác định một thứ tự cấu hình rõ ràng, không gọi setLocation chung sau khi đã tinh chỉnh theo module.

Không sử dụng `setLocationForModule(CLASS_PATH, ...)` vì classpath không phải module-oriented location hoặc output location phù hợp.

## 9. Khi nào dùng getLocationForModule, listLocationsForModules và inferModuleName?

| Bài toán thực tế | API chính | Kết quả mong muốn |
| --- | --- | --- |
| Biết tên module và cần tìm tệp trong đó | `getLocationForModule(parent, name)` | Location riêng cho module |
| Có sẵn JavaFileObject và cần xác định module sở hữu | `getLocationForModule(parent, file)` | Location module chứa file |
| Cần duyệt mọi module hiện diện ở parent | `listLocationsForModules(parent)` | `Iterable<Set<Location>>` |
| Đã có module location, cần tên module hiển thị | `inferModuleName(moduleLocation)` | Tên `java.base`, `demo.greetings`... |
| Cần đọc class đã biết trong module | `getJavaFileForInput(moduleLocation, binaryName, CLASS)` | JavaFileObject của class |
| Cần liệt kê JavaFileObject theo package | `list(moduleLocation, packageName, kinds, recurse)` | Các file trong package đã chọn |
| Cần cấu hình parent search path vật lý | `StandardJavaFileManager.setLocationFromPaths(...)` | Location gắn với danh sách Paths |
| Cần override đường dẫn của một module | `StandardJavaFileManager.setLocationForModule(...)` | Association riêng cho module |

**Phân biệt ba tên:**

- `java.base`: tên **module**.
- `java.lang`: tên **package**.
- `java.lang.String`: tên **class** dạng binary name.

Trong API đọc class, sau khi có `javaBaseLocation`, truyền `"java.lang.String"` và `JavaFileObject.Kind.CLASS`. Truyền module name vào tham số class name hoặc truyền package name vào tham số module name sẽ không cho kết quả đúng.

## 10. Vì sao listLocationsForModules trả Iterable<Set<Location>>?

Kiểu trả về được thiết kế để file manager có thể diễn đạt các **nhóm** module locations. Với các nguồn module khác nhau, file manager có thể tổ chức vị trí theo nhiều search entries. Vì vậy cách sử dụng portable là duyệt **mọi group, mọi location trong group**; không giả định:

- Chỉ có một set.
- Mỗi set luôn chỉ có một module.
- Thứ tự trả về tương ứng thứ tự alphabet hoặc thứ tự người dùng muốn biên dịch.
- Tên `getName()` chính là đường dẫn thư mục của module.
- Đếm tổng location sẽ tương đương số named modules có thể dùng trong mọi cấu hình, bất kể duplicates hoặc rules của provider.

Nếu muốn đưa ra UI với thứ tự ổn định, tạo danh sách tên qua `inferModuleName` rồi tự sắp xếp; nếu muốn tra cứu một module cụ thể, ưu tiên `getLocationForModule(parent, name)`.

Trong một **custom JavaFileManager**, giữ nguyên cấu trúc nhóm mà implementation quy định, trả location đại diện hợp lệ cho từng module và triển khai nhất quán `inferModuleName`; đừng gộp file class từ mọi module vào một namespace của classpath vì điều đó có thể làm sai module resolution.

## 11. Một số ranh giới cần giữ trong công cụ biên dịch nhúng

### 11.1. File manager location không phải Runtime Module

`JavaFileManager.Location` là đối tượng phục vụ **compiler/tools**. Nó **khác** `java.lang.Module` và `java.lang.ModuleLayer` của runtime JPMS. Tìm thấy `demo.greetings` trong `MODULE_PATH` không có nghĩa JVM hiện đang load mô-đun đó hoặc lớp của nó đã có thể gọi qua reflection.

Nếu mục tiêu là mô tả hoặc phân giải các module đã được load tại runtime, API phù hợp thuộc `java.lang.Module/ModuleLayer`. Nếu mục tiêu là quản lý nơi compiler đọc/ghi source/class files, dùng `javax.tools.JavaFileManager`.

### 11.2. Không coi một location là một physical Path

Các system modules trong JDK có thể nằm trong **runtime image**. Tên location có thể là một chuỗi có tính nội bộ của file manager và không map đơn giản sang `File` trên đĩa. Dùng `JavaFileManager.getJavaFileForInput(...)` hoặc `list(...)` để đọc file ở đúng package-oriented location.

`StandardJavaFileManager.getLocationAsPaths(...)` có thể cung cấp các `Path` khi implementation hỗ trợ, nhưng điều đó không bảo đảm mọi generic `JavaFileManager.Location` có một directory hoặc JAR path thông thường. Không ghép `moduleLocation.getName() + "/module-info.class"` để truy xuất dữ liệu.

### 11.3. Named modules khác classpath/unnamed module

Các phương thức nêu trên dành cho **module-aware** locations. Một thư viện trên `CLASS_PATH` thông thường không tự được liệt kê thành named module trên `MODULE_PATH`. Các JAR trên module path có thể là explicit named modules hoặc automatic modules theo quy tắc module system; vì vậy không nên suy đoán tên module từ artifact filename mà không xem descriptor và hiệu lực của file manager.

Nếu người dùng chưa cấu hình `MODULE_PATH`, việc không thấy module từ thư viện không nhất thiết là lỗi Java 9 API; có thể compiler hiện chỉ biết `SYSTEM_MODULES` và classpath.

### 11.4. Compiler API không bắt buộc có trong mọi runtime image

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu runtime không cung cấp system compiler. Mã chạy công cụ biên dịch nhúng nên dùng một JDK/runtime image có module `jdk.compiler`, hoặc cung cấp/compiler theo giải pháp được hỗ trợ; không assume ứng dụng chạy ở mọi runtime image đều có compiler.

Trong các cấu hình module chặt, `javax.tools` nằm trong module `java.compiler`; tùy cách build và module descriptor của công cụ, có thể phải khai báo `requires java.compiler;` để truy cập API.

## 12. Xử lý lỗi và kiểm chứng kết quả

| Dấu hiệu | Điều cần kiểm tra | Cách giải quyết |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime thiếu system compiler | Chạy tool trên JDK/runtime image có `jdk.compiler` |
| `UnsupportedOperationException` ở module methods | File manager tùy biến chưa triển khai chức năng từ Java 9 | Dùng standard file manager hoặc bổ sung các override tương thích |
| `IllegalArgumentException` khi tìm module | Parent không phải module-oriented/output location | Chọn `MODULE_PATH`, `MODULE_SOURCE_PATH`, `SYSTEM_MODULES` hoặc output đúng |
| Không tìm thấy module ứng dụng | `MODULE_PATH` trống/sai, module chưa compile, tên module sai | Kiểm tra input search path và cấu trúc artifact `module-info.class` |
| `IOException` | I/O, đường path không hợp lệ hoặc file manager gặp lỗi | Ghi nguyên nhân, kiểm tra quyền/trạng thái file và cấu hình |
| `inferModuleName` không hoạt động | Module location không do file manager quản lý hoặc provider không hỗ trợ | Dùng location được trả bởi đúng file manager |
| Chạy lại lookup sau `close()` báo lỗi/hành vi lạ | Vòng đời file manager đã kết thúc | Dùng file manager còn mở; đóng ở cuối phạm vi tool |
| `setLocationForModule` trước đó bị mất tác dụng | Sau đó lại gọi `setLocationFromPaths` trên parent | Thiết lập parent trước, override module-specific sau |
| Liệt kê được module nhưng import/`requires` vẫn lỗi | Compiler task chưa được cấu hình nhất quán; chính sách exports/reads sai | Xem module graph, source/output paths, descriptor và compiler diagnostics |

Nên kiểm thử trên một module đơn giản như `demo.greetings` trước khi tích hợp vào một build phức tạp. Trong công cụ chuyên dụng, giữ lại compiler diagnostics (qua `DiagnosticCollector` hoặc listener) và tên module/location logic để phân tích lỗi; **không phụ thuộc** vào giá trị `getName()` như một absolute physical path.

## 13. Lỗi thường gặp

**Lỗi 1 — Gọi getLocationForModule bằng CLASS_PATH.** Đây là package-oriented location, không phải module-oriented/output location hợp lệ. Chọn `MODULE_PATH` khi thực sự đọc các named modules đã biên dịch.

**Lỗi 2 — Dùng getLocationForModule(parent, "java.lang").** `java.lang` là package, không phải module. Để tìm `String.class`, lấy `java.base` rồi dùng `"java.lang.String"`.

**Lỗi 3 — Duyệt listLocationsForModules như Iterable<Location>.** Kiểu đúng là `Iterable<Set<Location>>`; phải có hai vòng lặp.

**Lỗi 4 — Tin moduleLocation.getName() là tên module.** Tên location là biểu diễn logic/provider-specific. Dùng `inferModuleName(...)` để lấy tên module.

**Lỗi 5 — Gọi getJavaFileForInput với MODULE_PATH trực tiếp.** Vị trí module-oriented không phải location để đọc class theo package. Thu hẹp về module location trước.

**Lỗi 6 — Kỳ vọng find module tự động tải hoặc compile module.** Các phương thức chỉ cung cấp location; việc biên dịch và quản lý module graph là trách nhiệm của compiler/tool.

**Lỗi 7 — Nhầm file-manager location với ModuleLayer/runtime modules.** Một module tìm được ở compiler input chưa chắc đã load trong JVM.

**Lỗi 8 — Không đóng StandardJavaFileManager.** Dễ để lại tài nguyên giữ bởi compiler/file manager; dùng try-with-resources khi phạm vi kết thúc.

**Lỗi 9 — Ghi đè setLocationFromPaths sau module-specific mapping.** Có thể hủy các mapping từ `setLocationForModule`; xác định rõ thứ tự cấu hình.

**Lỗi 10 — Giả định default methods được hỗ trợ trong mọi custom file manager.** Chữ ký tồn tại từ Java 9 nhưng implementation mặc định có thể ném `UnsupportedOperationException`.

## 14. Tự kiểm tra kiến thức

1. **getLocationForModule là API từ Java nào?** Java 9; vẫn dùng trong Java SE hiện nay.
2. **MODULE_PATH và CLASS_PATH khác nhau ở điểm nào?** `MODULE_PATH` là module-oriented, còn `CLASS_PATH` là package-oriented.
3. **Muốn lấy java.lang.String.class từ system modules, làm gì trước?** Lấy `getLocationForModule(SYSTEM_MODULES, "java.base")`.
4. **Đã có JavaFileObject nhưng chưa biết module, dùng gì?** Overload `getLocationForModule(parent, JavaFileObject)`.
5. **listLocationsForModules trả List<String> tên module?** Không; trả `Iterable<Set<Location>>`.
6. **Cần tên module từ module location, gọi gì?** `inferModuleName(moduleLocation)`.
7. **getLocationForModule có tự chạy javac không?** Không; nó chỉ tìm vị trí logic trong file manager.
8. **Module trên classpath có tự nằm trong MODULE_PATH không?** Không; phải cấu hình các module path entries tương ứng.
9. **Đóng file manager rồi dùng module location cũ có an toàn mặc nhiên không?** Không; tránh dùng khi vòng đời file manager đã kết thúc.
10. **Khi setLocationFromPaths(parent) sau setLocationForModule, điều gì xảy ra?** Các module-specific associations được thiết lập trước có thể bị hủy.
11. **ToolProvider.getSystemJavaCompiler có luôn khác null?** Không; runtime phải cung cấp system compiler.
12. **Tại sao không tách module name từ Location.getName()?** Vì tên location do implementation định nghĩa; `inferModuleName` mới là API tương ứng.
13. **Muốn liệt kê mô-đun trong một module path, cần gì?** Cấu hình `MODULE_PATH`, gọi `listLocationsForModules`, duyệt hai tầng và xác định tên qua `inferModuleName`.
14. **Một file manager khác có thể ném UnsupportedOperationException ở các module APIs?** Có; chúng là default methods với triển khai mặc định không bắt buộc hỗ trợ.
15. **Vị trí của một module lấy từ module-oriented parent có tiếp tục module-oriented không?** Thông thường không; kết quả dành riêng cho module là package-oriented.

## 15. Checklist ứng dụng trong embedded compiler

- [ ] Chạy trên JDK có system compiler; kiểm tra `ToolProvider.getSystemJavaCompiler()`.
- [ ] Dùng `StandardJavaFileManager` khi chưa cần custom file handling đặc biệt.
- [ ] Xác định parent đúng: `SYSTEM_MODULES`, `MODULE_PATH` hoặc `MODULE_SOURCE_PATH`.
- [ ] Phân biệt tên module/package/class và location logic/physical Path.
- [ ] Cấu hình `setLocationFromPaths` trước khi lookup module path riêng.
- [ ] Nếu dùng `setLocationForModule`, kiểm soát thứ tự và tác dụng ghi đè.
- [ ] Dùng `getLocationForModule` để thu hẹp về một module trước khi tìm class.
- [ ] Duyệt `Iterable<Set<Location>>` bằng hai vòng lặp, không dựa vào thứ tự.
- [ ] Lấy tên module qua `inferModuleName`, không tự phân tích `getName()`.
- [ ] Xử lý `IOException`, `IllegalArgumentException`, `UnsupportedOperationException` theo đúng nguyên nhân.
- [ ] Lưu compiler diagnostics nếu thực thi tác vụ biên dịch.
- [ ] Đóng file manager đúng vòng đời và kiểm thử lại khi thay JDK, provider hoặc module-path layout.

## Tài liệu chính thức đối chiếu

- Java SE 26 — `JavaFileManager` (cả hai overload `getLocationForModule`, `listLocationsForModules`, `inferModuleName`): https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html
- Java SE 26 — `JavaFileManager.Location` (module-oriented và package-oriented): https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.Location.html
- Java SE 26 — `StandardJavaFileManager` (`setLocationFromPaths`, `setLocationForModule`): https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- Java SE 26 — `StandardLocation` (`SYSTEM_MODULES`, `MODULE_PATH`, `MODULE_SOURCE_PATH`): https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardLocation.html
- Java SE 26 — `JavaCompiler`: https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261

**Ý chính:** `getLocationForModule(...)` thu hẹp vị trí tìm kiếm từ tập nhiều mô-đun thành vị trí của một mô-đun; `listLocationsForModules(...)` cho phép duyệt tất cả các vị trí mô-đun; `inferModuleName(...)` trả tên tương ứng. Dùng đúng parent location và vòng đời file manager sẽ giúp compiler/tool phân giải nguồn/class theo named module mà không phụ thuộc layout vật lý của JDK hoặc thư viện.
