# NoClassDefFoundError do thiếu lớp phụ thuộc hoặc sai tên

## 1. NoClassDefFoundError là gì?

`java.lang.NoClassDefFoundError` là một `LinkageError` xảy ra khi JVM hoặc ClassLoader cần định nghĩa, liên kết hay sử dụng một class nhưng **không thể tìm được định nghĩa cần thiết trong bối cảnh runtime**, mặc dù chương trình hoặc bytecode đã có sự phụ thuộc vào class đó. Thông điệp có thể chỉ tên class bị thiếu, tên không khớp hoặc cho biết class đã **khởi tạo thất bại trước đó**.

Trong thực hành Java ClassLoader, hai tình huống rất cần nhận diện là:

1. **Thiếu lớp phụ thuộc lúc chạy:** Class A có trên classpath, nhưng khi thực thi A, JVM cần class B và B không có trong đường tìm của loader thực sự dùng để resolve phụ thuộc.
2. **Sai tên nhị phân của class:** Loader được yêu cầu định nghĩa tên `demo.fake.Thing` từ một file `demo/fake/Thing.class`, nhưng nội dung bytecode lại khai báo `demo.real.Thing`; JVM từ chối định nghĩa với tên không khớp.

Thông điệp điển hình trên OpenJDK/HotSpot 17:

~~~text
java.lang.NoClassDefFoundError: demo/dep/Helper
~~~

hoặc:

~~~text
java.lang.NoClassDefFoundError: demo/fake/Thing (wrong name: demo/real/Thing)
~~~

Đây là **ví dụ định dạng thông điệp**, không phải hợp đồng bắt buộc mọi JDK/JVM phải dùng đúng dấu câu và nội dung. Muốn chẩn đoán chính xác, đọc **toàn bộ stack trace**, nguyên nhân lồng nhau (`Caused by`) và cấu hình ClassLoader thực tế.

### Hai thông tin không được đánh đồng

- “Có file `X.class` trong một JAR” **không chứng minh** loader đang resolve phụ thuộc có thể nhìn thấy file đó.
- “Tên file trên đĩa có vẻ đúng” **không chứng minh** binary name được biên dịch **bên trong bytecode** cũng đúng.

## 2. Phân biệt NoClassDefFoundError với ClassNotFoundException

| Khía cạnh | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Nhóm lỗi | Checked `Exception` | `Error`, subclass của `LinkageError` |
| Trường hợp thường gặp | Code gọi `Class.forName("pkg.Type")` hoặc `loader.loadClass("pkg.Type")` nhưng không tìm thấy | JVM cần class phụ thuộc đã được bytecode tham chiếu, nhưng không thể định nghĩa/liên kết class đó |
| Cách xử lý thông thường | Có thể bắt và xử lý như một lookup thất bại được dự kiến | Thường là lỗi triển khai/cấu hình nghiêm trọng; phải sửa runtime dependency hoặc binary mismatch |
| Có thể liên quan class loader? | Có | Có |
| Có thể xuất hiện cùng nhau trong causal chain? | Có | Có |

Một ví dụ minh họa:

~~~java
// Minh họa, không phải chương trình độc lập.
try {
    Class.forName("demo.dep.Helper");
} catch (ClassNotFoundException notFound) {
    System.out.println("Explicit lookup did not find Helper");
}
~~~

Đây là tra cứu **tường minh** theo tên; nếu không tìm thấy, API `Class.forName` thường báo `ClassNotFoundException`.

Còn đoạn sau được biên dịch khi `Helper` có sẵn:

~~~java
// Minh họa: Feature là class có bytecode gọi Helper.
System.out.println(Feature.message());
~~~

Nếu khi chạy `Helper.class` không còn được loader tìm thấy, JVM có thể ném `NoClassDefFoundError` khi thực thi lệnh cần resolve `Helper`. Không có mâu thuẫn: **đường code và giai đoạn lỗi khác nhau**.

`ClassNotFoundException` cũng có thể là **cause** bên trong một `NoClassDefFoundError`, tùy cơ chế loader/JVM, nhưng đừng mặc định luôn có hoặc luôn không có cause đó.

## 3. Vì sao compile thành công mà chạy lại lỗi?

Thực tế thường có ít nhất ba cấu hình khác nhau:

~~~text
Compile-time classpath
  ├── lib.jar
  └── dep.jar       ← javac nhìn thấy

Runtime classpath / loader graph
  └── lib.jar       ← dep.jar bị thiếu

Bytecode Feature.class
  └── symbolic reference tới demo/dep/Helper
                   |
             JVM resolve lúc cần
                   |
        loader không tìm được Helper
                   |
           NoClassDefFoundError
~~~

`javac` kiểm tra và ghi tham chiếu tới types/methods vào bytecode dựa trên các dependency lúc biên dịch. Nó **không đóng gói tự động** toàn bộ những JAR phụ thuộc vào output class/JAR ứng dụng.

Khi chạy, JVM dùng **runtime classpath/module path và delegation của ClassLoader tại thời điểm đó**. Một class có thể được load thành công trước, nhưng khi method hoặc field phụ thuộc được sử dụng lần đầu, quá trình resolution mới yêu cầu một class khác và thất bại.

Vì vậy:

- `Compilation successful` không có nghĩa `runtime dependencies complete`.
- Lỗi có thể xuất hiện **muộn**, chỉ khi chạm vào một code path.
- Đổi thứ tự JAR hoặc đưa đúng JAR vào nhầm loader không chắc sửa được.
- Nếu class đã được loader định nghĩa, thay file trên đĩa không làm JVM tự nạp lại version mới.

## 4. Ví dụ Java 17+ số 1: thiếu JAR phụ thuộc tại runtime

Ví dụ gồm ba tầng:

1. `demo.dep.Helper` nằm trong `dep.jar`.
2. `demo.lib.Feature` nằm trong `lib.jar` và gọi Helper.
3. `demo.host.App` là entry point trên application classpath.

Ta biên dịch đúng với dependency đầy đủ, sau đó cố ý bỏ `dep.jar` khỏi runtime `-cp` để tái hiện lỗi.

### 4.1. Cấu trúc thư mục

~~~text
missing-dependency-demo/
├── dep-src/
│   └── demo/dep/Helper.java
├── lib-src/
│   └── demo/lib/Feature.java
└── host-src/
    └── demo/host/App.java
~~~

### 4.2. File Helper.java

Tạo **`dep-src/demo/dep/Helper.java`**:

~~~java
package demo.dep;

public final class Helper {
    private Helper() {
    }

    public static String value() {
        return "DEP_OK";
    }
}
~~~

### 4.3. File Feature.java

Tạo **`lib-src/demo/lib/Feature.java`**:

~~~java
package demo.lib;

import demo.dep.Helper;

public final class Feature {
    private Feature() {
    }

    public static String message() {
        return Helper.value();
    }
}
~~~

Class `Feature` có dependency **trực tiếp trong method body** tới `demo.dep.Helper`. File `Feature.class` được biên dịch thành công nhưng khi `message()` chạy, JVM cần resolve class `Helper`.

### 4.4. File App.java

Tạo **`host-src/demo/host/App.java`**:

~~~java
package demo.host;

import demo.lib.Feature;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Start");

        try {
            System.out.println("Feature: " + Feature.message());
        } catch (NoClassDefFoundError failure) {
            System.out.println("Failure type: "
                    + failure.getClass().getSimpleName());
            System.out.println("Missing name: "
                    + failure.getMessage());
        }
    }
}
~~~

**Vì sao bắt `NoClassDefFoundError` ở đây?** Chỉ để thí nghiệm in output ngắn và xác định. Code production thường **không nên bắt rồi tiếp tục vận hành** sau lỗi linkage nghiêm trọng nếu runtime dependency chưa được sửa. Trong ứng dụng thật, ghi stack trace/cause và dừng hoặc cô lập plugin bị lỗi.

### 4.5. Biên dịch và đóng JAR trên Bash

Mở terminal tại thư mục `missing-dependency-demo/`, dùng JDK 17+:

~~~bash
mkdir -p build/dep build/lib build/host dist

javac -encoding UTF-8 -d build/dep \
  dep-src/demo/dep/Helper.java

jar --create --file dist/dep.jar -C build/dep .

javac -encoding UTF-8 -cp dist/dep.jar \
  -d build/lib lib-src/demo/lib/Feature.java

jar --create --file dist/lib.jar -C build/lib .

javac -encoding UTF-8 \
  -cp "dist/lib.jar:dist/dep.jar" \
  -d build/host host-src/demo/host/App.java
~~~

### 4.6. Biên dịch và đóng JAR trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/dep,build/lib,build/host,dist | Out-Null

javac -encoding UTF-8 -d build/dep dep-src/demo/dep/Helper.java

jar --create --file dist/dep.jar -C build/dep .

javac -encoding UTF-8 -cp dist/dep.jar -d build/lib lib-src/demo/lib/Feature.java

jar --create --file dist/lib.jar -C build/lib .

javac -encoding UTF-8 -cp "dist/lib.jar;dist/dep.jar" -d build/host host-src/demo/host/App.java
~~~

### 4.7. Chạy với dependency đầy đủ

**Linux/macOS/Git Bash:**

~~~bash
java -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/lib.jar;dist/dep.jar" demo.host.App
~~~

Stdout:

~~~text
Start
Feature: DEP_OK
~~~

### 4.8. Bỏ dep.jar khỏi runtime

**Linux/macOS/Git Bash:**

~~~bash
java -cp "build/host:dist/lib.jar" demo.host.App
~~~

**Windows PowerShell:**

~~~powershell
java -cp "build/host;dist/lib.jar" demo.host.App
~~~

Stdout trên JDK 17 tiêu chuẩn:

~~~text
Start
Failure type: NoClassDefFoundError
Missing name: demo/dep/Helper
~~~

**Lý giải theo thứ tự:**

1. JVM tìm và tải `App` từ `build/host`.
2. `App` gọi `Feature.message()`; `Feature` có trong `dist/lib.jar` nên được tìm thấy.
3. Bytecode của `Feature.message()` gọi `Helper.value()`, cần class `demo.dep.Helper`.
4. Loader dùng để resolve dependency đó không tìm thấy `Helper` vì `dep.jar` đã bị bỏ khỏi runtime classpath.
5. `NoClassDefFoundError` xuất hiện **dù `Feature.class` có trên classpath và ứng dụng đã biên dịch thành công**.

### 4.9. Cách sửa

Giữ nguyên code và thêm **đúng** `dep.jar` vào đường tìm runtime của loader:

~~~bash
java -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

Trên Windows dùng `;` thay `:`. Trong ứng dụng đóng gói bằng Maven/Gradle, cần kiểm tra *runtime dependency graph*, transitive dependencies, scope/configuration và classpath của đúng tiến trình/test runner, không chỉ compile dependencies.

## 5. Ví dụ Java 17+ số 2: class nằm ở sai đường dẫn so với binary name

Không phải mọi `NoClassDefFoundError` đều là “thiếu file”. JVM kiểm tra rằng **tên class được yêu cầu** nhất quán với **binary name được ghi trong class file**.

Ví dụ class được biên dịch là:

~~~java
package demo.real;

public final class Thing {
}
~~~

Bytecode có internal name `demo/real/Thing`. Nếu chỉ **copy hoặc đổi tên file** tới:

~~~text
build/wrong/demo/fake/Thing.class
~~~

rồi ClassLoader thử định nghĩa tên `demo.fake.Thing` từ file đó, JVM nhận thấy:

~~~text
Tên được yêu cầu: demo/fake/Thing
Tên trong bytecode: demo/real/Thing
Kết quả: NoClassDefFoundError (wrong name: ...)
~~~

Việc đổi tên thư mục/file không sửa được `package`/`this_class` trong bytecode. Đây là một lỗi phổ biến khi tự viết `findClass`, tự giải nén JAR, sao chép bytecode hoặc nhầm package.

### 5.1. Cấu trúc

~~~text
wrong-name-demo/
├── thing-src/
│   └── demo/real/Thing.java
└── host-src/
    └── WrongNameProbe.java
~~~

Tạo **`thing-src/demo/real/Thing.java`**:

~~~java
package demo.real;

public final class Thing {
    public Thing() {
    }
}
~~~

Tạo **`host-src/WrongNameProbe.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class WrongNameProbe {
    private WrongNameProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: WrongNameProbe <wrong-class-root>");
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException("Missing class root");
        }

        URL[] urls = {root.toUri().toURL()};
        try (URLClassLoader child = new URLClassLoader(
                urls, WrongNameProbe.class.getClassLoader())) {
            try {
                Class.forName("demo.fake.Thing", false, child);
                System.out.println("Wrong name detected: false");
            } catch (NoClassDefFoundError failure) {
                System.out.println("Error type: "
                        + failure.getClass().getSimpleName());
                System.out.println("Wrong name detected: "
                        + String.valueOf(failure.getMessage())
                                .contains("wrong name"));
            }
        }
    }
}
~~~

Để tập trung vào sai tên, host **không đặt Thing.class lên application classpath** và chỉ để `URLClassLoader` đọc thư mục `build/wrong`.

### 5.2. Bash: biên dịch rồi cố ý copy sai vị trí

~~~bash
mkdir -p build/real build/wrong/demo/fake build/host

javac -encoding UTF-8 -d build/real \
  thing-src/demo/real/Thing.java

javac -encoding UTF-8 -d build/host \
  host-src/WrongNameProbe.java

cp build/real/demo/real/Thing.class \
  build/wrong/demo/fake/Thing.class

java -cp build/host WrongNameProbe build/wrong
~~~

### 5.3. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/real,build/wrong/demo/fake,build/host | Out-Null

javac -encoding UTF-8 -d build/real thing-src/demo/real/Thing.java

javac -encoding UTF-8 -d build/host host-src/WrongNameProbe.java

Copy-Item build/real/demo/real/Thing.class build/wrong/demo/fake/Thing.class

java -cp build/host WrongNameProbe build/wrong
~~~

Stdout trên OpenJDK/HotSpot 17:

~~~text
Error type: NoClassDefFoundError
Wrong name detected: true
~~~

`WrongNameProbe` in boolean thay vì toàn bộ `getMessage()`, vì format thông điệp lỗi có thể khác giữa các JVM. Trên HotSpot, phần thông điệp thường chứa `wrong name: demo/real/Thing`.

**Cách sửa đúng:** Giữ `Thing.class` tại `demo/real/Thing.class` và yêu cầu `demo.real.Thing`; hoặc thay `package demo.real;` thành `package demo.fake;` **trong source**, biên dịch lại và lưu output tại `demo/fake/Thing.class`. Không sửa chỉ bằng cách đổi tên file `.class`.

## 6. ClassNotFoundException khác với “wrong name”

Cùng `WrongNameProbe` ở trên, nếu child loader không tìm được file `demo/fake/Thing.class` ngay từ đầu, `Class.forName("demo.fake.Thing", false, child)` thường ném **`ClassNotFoundException`**.

Nhưng khi loader **tìm thấy file ở đường tìm hợp lệ**, rồi JVM phát hiện tên class trong bytecode không khớp tên yêu cầu, kết quả có thể là **`NoClassDefFoundError` với “wrong name”**.

~~~text
Không tìm thấy URL / bytes cho tên được yêu cầu
    → ClassNotFoundException (lookup failure)

Có bytes nhưng class file khai báo binary name khác
    → NoClassDefFoundError (wrong name)

Có bytes, đúng tên nhưng nội dung class file không hợp lệ
    → Có thể là ClassFormatError hoặc lỗi liên kết tương ứng
~~~

Một custom loader nên đọc bytes theo tên nhị phân chính xác rồi gọi `defineClass(name, bytes, 0, length)`. Nếu truyền bytes của class khác, JVM có thể phát hiện name mismatch.

Đối với module path, named module package ownership cũng ảnh hưởng class lookup; không suy từ việc thấy class file trong một modular JAR rằng bất kỳ loader/module nào cũng được phép dùng nó.

## 7. Các nguyên nhân khác thường gặp của NoClassDefFoundError

Mặc dù bài tập trung vào thiếu dependency và sai tên, cần nhận diện các biến thể để không chẩn đoán nhầm:

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `NoClassDefFoundError: pkg/Dependency` | Dependency thiếu trên runtime classpath/module path, hoặc không visible từ loader | Runtime dependency graph và loader topology |
| `NoClassDefFoundError: pkg/X (wrong name: pkg/Y)` | `.class` được đặt sai package path; custom loader định nghĩa sai tên | `package`, internal binary name, JAR entry |
| `NoClassDefFoundError: Could not initialize class ...` | Class đã từng khởi tạo thất bại, và lần dùng sau thấy class ở trạng thái erroneous | Tìm exception đầu tiên của static initialization |
| `NoClassDefFoundError` sau plugin reload | Old loader đã đóng hoặc dependency/version đã bị đổi; request vẫn dùng old generation | In-flight tasks, lifecycle/leases, `close()` |
| `NoClassDefFoundError` chỉ trên server/test | Compile/test classpath khác runtime thật; class có ở loader khác | Container-specific loaders, packaging, launcher |
| `NoClassDefFoundError` với tên class khác tên code đang gọi | Class trực tiếp có, nhưng dependency sâu hơn không có | Cause chain và class thực sự được resolve |

Đừng sửa bằng cách **bắt mọi `NoClassDefFoundError` rồi tiếp tục**. Nếu application thiếu runtime dependency, lỗi có thể tái xuất hiện trên code path khác. Nếu class khởi tạo hỏng, cơ chế JVM không “retry static initializer” chỉ vì code bắt lỗi.

## 8. Đừng nhầm thiếu class với class đã khởi tạo thất bại

Một class có `static` initializer ném exception có thể chuyển sang trạng thái **erroneous**. Lần active use đầu JVM thường ném `ExceptionInInitializerError` (nếu initializer ném non-`Error`); lần sau cần initialize **cùng runtime class** thường ném `NoClassDefFoundError: Could not initialize class ...`. Trong trường hợp này **bytecode và JAR vẫn có thể tồn tại nguyên vẹn**.

Dấu hiệu chẩn đoán quan trọng là thông điệp *Could not initialize class*, bản ghi `<clinit>`/first exception và quan hệ superclass initialization. Chỉ sửa file JAR hoặc `java.class.path` không reset class erroneous trong một loader đang sống.

Bài riêng **NoClassDefFoundError sau khi khởi tạo lớp thất bại** có lab Java 17+ tái hiện first failure → repeat failure, phân biệt `Class.forName(..., false, loader)` với initialization và thử loader mới sau khi sửa cấu hình. Bài hiện tại tập trung vào **dependency bị thiếu và file mang wrong binary name**, vốn có cách sửa khác.

## 9. Quy tắc binary name và đường dẫn class

Trong Java:

~~~java
package demo.real;

public class Thing {
}
~~~

Tên nhị phân là `demo.real.Thing`. Trong thư mục classpath/JAR thông thường, entry tương ứng:

~~~text
demo/real/Thing.class
~~~

Trong bytecode, constant pool và `this_class` dùng internal form với slash, ví dụ `demo/real/Thing`. Tên file đặt tại `demo/fake/Thing.class` không thay đổi metadata này.

Những kiểu sai tên hay gặp:

- Đổi thư mục hoặc file `.class` nhưng không biên dịch lại `package`.
- Loader dùng `name.replace('.', '/')` sai hoặc bỏ mất prefix.
- Class generator bytecode gắn `this_class` sai với tên yêu cầu.
- Đưa một class byte array tới `defineClass(otherName, bytes, ...)`.
- Nhầm tên nested class như `Outer$Inner` thành `Outer.Inner` trong một API yêu cầu binary name.
- Nhầm case-sensitive package/class name trên OS có cách xử lý filename khác nhau.

Một ví dụ nested class: source `demo.Outer.Inner` có thể có binary name `demo.Outer$Inner`, nên tên lookup bằng reflection thường là `demo.Outer$Inner`. Đây **không phải** lý do để sửa tên file bằng tay; dùng `javac`, đúng output root và `Class.getName()` để đối chiếu.

## 10. Chẩn đoán theo thứ tự: lỗi ở bước nào?

Khi gặp `NoClassDefFoundError`, làm theo trình tự:

1. **Lấy stack trace đầy đủ** của lần thất bại đầu tiên, bao gồm `Caused by` và suppressed exceptions nếu có.
2. **Đọc tên sau dấu hai chấm:** Là tên phụ thuộc như `demo/dep/Helper`, thông điệp `wrong name`, hay `Could not initialize class`?
3. **Xác định thời điểm:** Lỗi khi khởi chạy class chính, gọi một method, tạo plugin instance, mở ServiceLoader, hay sau reload?
4. **Kiểm tra runtime launcher:** `java -cp`, `--module-path`, script, container classpath, environment, dependency scopes.
5. **Kiểm tra nguồn thực tế:** JAR nào chứa entry chính xác, và loader nào được dùng để resolve class?
6. **Đối chiếu class identity:** `getClassLoader()` cho các class đã load; parent-first/child-first và module mapping.
7. **Nếu “wrong name”:** So tên yêu cầu, JAR entry/path và `this_class` bên trong bytecode.
8. **Nếu “Could not initialize class”:** Truy tìm static initialization failure đầu tiên.
9. **Khôi phục và kiểm chứng:** Chạy lại với runtime classpath hoặc package mapping đã sửa; không chỉ sửa compile classpath.

Không tự động lấy class hiện tại bằng `SomeClass.class.getClassLoader()` rồi kết luận mọi dependency của ứng dụng đều nằm trong loader đó: framework/plugin có thể tạo nhiều defining loaders, delegation khác nhau.

## 11. Các lệnh kiểm tra JAR và bytecode

Với ví dụ missing dependency:

~~~bash
jar --list --file dist/lib.jar
jar --list --file dist/dep.jar
~~~

`lib.jar` cần chứa `demo/lib/Feature.class`, còn `dep.jar` chứa `demo/dep/Helper.class`.

Dùng `javap` để đọc bytecode đã biên dịch:

~~~bash
javap -c -classpath dist/lib.jar demo.lib.Feature
~~~

Bạn có thể thấy lời gọi tham chiếu tới `demo/dep/Helper.value` trong disassembly. Lệnh `javap` này không chứng minh Helper có sẵn lúc chạy; nó chỉ cho thấy symbolic reference được ghi trong bytecode.

Đối với wrong name:

~~~bash
javap -verbose -classpath build/real demo.real.Thing
~~~

Trong output có metadata liên quan `this_class` và internal name `demo/real/Thing`. So sánh nó với entry bạn định nghĩa ở `build/wrong/demo/fake/Thing.class`.

Quan sát class loading trên Java 17:

~~~bash
java -Xlog:class+load=info \
  -cp "build/host:dist/lib.jar:dist/dep.jar" demo.host.App
~~~

Dòng log do JVM phát ra có thể nhiều, chứa đường dẫn tùy máy và không có output xác định như stdout của demo. Nó hữu ích khi cần biết một class **thực sự** được JVM nạp từ nguồn nào, nhưng cần kết hợp stack trace và classloader configuration.

Trên Windows, dấu phân cách `-cp` là `;`. Lệnh `javap -verbose` có output dài và phụ thuộc JDK nên không coi nó là một phần của stdout kỳ vọng.

## 12. NoClassDefFoundError trong hệ nhiều ClassLoader

Một plugin host có thể tạo child loader:

~~~java
// Mã minh họa, không phải chương trình độc lập.
URLClassLoader child =
        new URLClassLoader(pluginUrls, apiParentLoader);
Class<?> provider = child.loadClass("demo.plugin.PluginImpl");
~~~

`PluginImpl` được child định nghĩa nhưng phụ thuộc `demo.dep.Helper`. Classloader muốn resolve các tham chiếu đó phải có đường tìm phù hợp cho Helper; nếu Helper chỉ nằm trong **một sibling loader không được delegation tới**, nó có thể vẫn thất bại dù JVM đã nạp Helper ở loader khác.

### Những điều cần nhớ

- **Child nhìn parent** theo mô hình parent-first mặc định; **parent không tự duyệt class riêng của child**.
- **Sibling loaders** không tự động nhìn thấy nhau.
- Hai loaders định nghĩa cùng FQCN tạo runtime classes khác nhau; điều đó còn có thể gây `ClassCastException`/loader constraint `LinkageError`.
- Đưa JAR vào **classpath của một loader khác** không bảo đảm sửa lỗi ở loader đang resolve.
- Với `URLClassLoader.close()`, class đã load vẫn tồn tại nhưng nguồn tìm class mới của loader đã đóng không còn khả dụng.
- Với JPMS named modules, module readability, mapping loader và exports/opens là các ràng buộc bổ sung; không suy từ sự tồn tại class trong module JAR rằng mọi loader đều có thể tìm nó.

Một cách thiết kế ổn định: đặt shared API trong parent, đặt implementation và runtime dependencies của plugin vào đường tìm của plugin loader hoặc ở parent theo chính sách tương thích, quản lý generation lifecycle rõ ràng.

## 13. Lỗi thường gặp khi sửa

| Cách sửa sai | Vì sao chưa đủ/không đúng | Thay bằng |
|---|---|---|
| “File `Feature.class` có nên thiếu gì đâu?” | Feature phụ thuộc Helper ở bước runtime resolution | Kiểm tra toàn bộ dependency graph |
| Chỉ sửa compile classpath | `java` vẫn chạy với classpath khác | Sửa đúng runtime classpath/module path |
| Thêm dep.jar vào thư mục bất kỳ | Loader không tự quét mọi thư mục | Đưa dependency vào đúng loader URL/launcher |
| Đổi tên `Thing.class` hoặc directory bằng tay | Bytecode vẫn khai báo binary name cũ | Sửa `package` và biên dịch lại |
| Bắt `NoClassDefFoundError` rồi chạy tiếp | Lỗi linkage có thể tái diễn | Khắc phục packaging/configuration hoặc cô lập plugin |
| Chỉ xem exception cuối cùng | Initialization failure đầu tiên có thể bị che | Xem log từ lần lỗi đầu và `Caused by` |
| Đóng loader ngay sau plugin cutover | Request cũ có thể còn cần class/resource | Drain in-flight tasks rồi close |
| Đặt dependency ở sibling loader và trông chờ tự thấy | Không có delegation mặc định giữa siblings | Thiết kế parent/delegation đúng |
| Dựa vào thứ tự wildcard classpath | Thứ tự mở rộng `lib/*` không bảo đảm ổn định | Loại bỏ bản trùng và khóa dependencies |
| Dựa vào tên class đơn thuần | Runtime identity còn bao gồm defining loader | Kiểm tra `Class.getClassLoader()` |

## 14. Checklist phục hồi lỗi production

**Khi nhận lỗi:**

1. Chụp stack trace đầy đủ và version/runtime launch command.
2. Xác định tên class thất bại và từ khoá `wrong name` hoặc `Could not initialize class`.
3. Đối chiếu JAR packaging bằng `jar --list`, bytecode bằng `javap`.
4. Kiểm tra compile-time vs runtime dependency scopes.
5. Xác định defining loader của caller và loader graph thực tế.
6. Kiểm tra không có dependency bị exclude/shade sai hoặc transitive version xung đột.
7. Sửa đóng gói; build lại reproducibly, chạy thử đúng command production.
8. Nếu có plugin hot reload, kiểm tra old/new generation, request in-flight và thời điểm `close()`.
9. Nếu là initialization failure, sửa nguyên nhân static initializer thay vì chỉ thêm JAR.
10. Thêm integration test khởi chạy với **đúng runtime artifacts** để phát hiện lỗi trước phát hành.

Trong Maven/Gradle, nên sử dụng dependency-insight/dependency-tree và runtime classpath reporting để phát hiện dependency thiếu hoặc trùng version. Không ép mọi lỗi về “thiếu thư viện” nếu thông điệp đã chỉ ra name mismatch hoặc initialization failure.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `App` và `Feature` có trên runtime classpath, `Helper` chỉ có lúc biên dịch. Lỗi nào dễ xảy ra khi gọi `Feature.message()`?

**Đáp án:** `NoClassDefFoundError` cho `demo/dep/Helper` khi JVM cần resolve dependency và không tìm được lớp.

**Câu 2.** `Class.forName("demo.dep.Helper")` trực tiếp không tìm thấy class thường ném lỗi nào?

**Đáp án:** `ClassNotFoundException` (checked exception), khác đường xảy ra lỗi resolution của bytecode.

**Câu 3.** Đổi file `demo/real/Thing.class` thành `demo/fake/Thing.class` có làm binary name đổi theo không?

**Đáp án:** Không. Tên nằm trong bytecode vẫn là `demo/real/Thing`; nếu loader cố định nghĩa tên `demo.fake.Thing` có thể xuất hiện `NoClassDefFoundError (wrong name)`.

**Câu 4.** Vì sao phải kiểm tra runtime classpath chứ không chỉ `javac -cp`?

**Đáp án:** Compile-time dependencies không tự xuất hiện ở runtime; JVM tải class theo đường tìm của runtime loader.

**Câu 5.** Lần đầu sử dụng class lỗi ở static initializer, lần sau báo `NoClassDefFoundError`. Có chắc thiếu JAR không?

**Đáp án:** Không. Class có thể đã bị đánh dấu initialization failed; phải truy lần exception đầu tiên.

**Câu 6.** `Helper` nằm trong sibling loader của plugin nhưng plugin không ủy quyền tới nó. Tìm được Helper khi in danh sách JAR toàn JVM đã đủ chưa?

**Đáp án:** Chưa. Loader dùng để resolve phụ thuộc phải có đường tìm thực sự tới class phù hợp.

**Câu 7.** Có nên bắt `NoClassDefFoundError` rồi tiếp tục để “tự khôi phục” production không?

**Đáp án:** Thường không. Nên sửa dependency/name mismatch hoặc tách/disable plugin lỗi với policy rõ, thay vì bỏ qua lỗi linkage.

## 16. Nguồn tham khảo chính thức

- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): ý nghĩa của lỗi khi JVM/ClassLoader cần định nghĩa class nhưng không tìm được định nghĩa phù hợp.
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): lỗi tra cứu class tường minh.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation, `loadClass`, `findClass` và `defineClass`.
- [Java SE 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): lỗi static initialization.
- [Java Virtual Machine Specification 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization và loading constraints.
- [Java SE 17 — Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): runtime `--class-path`, module path và class loading logs.

**Ghi nhớ:** `NoClassDefFoundError` không chỉ có một nguyên nhân. Với lỗi **thiếu phụ thuộc**, so sánh runtime loader/classpath với bytecode đang cần class nào. Với **wrong name**, đối chiếu package, đường dẫn file và binary name bên trong `.class`, rồi biên dịch lại đúng. Luôn phân biệt với `ClassNotFoundException` của explicit lookup và `NoClassDefFoundError` phát sinh **sau một lỗi khởi tạo lớp**.