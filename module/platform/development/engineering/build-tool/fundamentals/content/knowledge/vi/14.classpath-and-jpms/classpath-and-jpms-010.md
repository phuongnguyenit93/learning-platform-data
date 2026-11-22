# Nhận diện lỗi classpath trước khi thay đổi cấu hình một cách mò mẫm

Khi một ứng dụng Java báo không tìm thấy class, không nạp được method hoặc chạy được trên máy lập trình viên nhưng thất bại trên CI, nguyên nhân thường được quy ngay cho dependency. Người xử lý có thể vội thêm một thư viện, ép version, loại một dependency bắc cầu hoặc thay đổi classpath. Những thay đổi đó đôi khi làm lỗi biến mất tạm thời nhưng cũng có thể che giấu nguyên nhân thật và tạo ra lỗi mới.

Classpath là danh sách vị trí mà compiler hoặc JVM tìm class và resource. Lỗi classpath cần được chẩn đoán bằng cách xác định **tiến trình nào đang nạp class, nó đang dùng classpath nào, class được tìm ở đâu và phiên bản nào thực sự được nạp**. Với Java Platform Module System (JPMS), còn phải xác định class đang nằm trên classpath hay module path và module có đọc, export hoặc open package cần thiết hay không.

## 1. Classpath là gì và tại sao cùng một project có nhiều classpath?

Classpath là tập đường dẫn đến thư mục chứa class đã biên dịch, JAR hoặc các vị trí chứa resource mà công cụ Java dùng để tìm kiếm. Một chương trình có thể có classpath khác nhau ở từng giai đoạn.

| Classpath | Được dùng khi nào? | Ví dụ thành phần |
|---|---|---|
| Compile classpath | Compiler biên dịch mã nguồn chính. | API và thư viện mà mã trong `src/main/java` tham chiếu. |
| Runtime classpath | JVM chạy ứng dụng. | Class ứng dụng, thư viện runtime và resource cần khi chạy. |
| Test compile classpath | Compiler biên dịch mã kiểm thử. | Mã chính, JUnit API, thư viện test và helper. |
| Test runtime classpath | JVM chạy test. | Test classes, main classes, test engine, runtime libraries và test resources. |
| Build logic/plugin classpath | Gradle khởi tạo plugin hoặc build logic. | Gradle plugin và dependency mà plugin cần. |

Một dependency có thể có mặt trên compile classpath nhưng không có trên runtime classpath, hoặc ngược lại. Vì vậy, việc `compileJava` thành công không chứng minh ứng dụng có đủ class khi chạy. Tương tự, test compile thành công không bảo đảm test engine hoặc thư viện runtime đã có khi task `test` khởi chạy.

Trong Gradle Java Plugin, một số configuration thường gặp:

| Configuration | Vai trò |
|---|---|
| `implementation` | Dependency dùng nội bộ khi biên dịch và chạy module. |
| `api` | Dependency thuộc API công khai mà consumer của Java Library cần thấy trên compile classpath. |
| `compileOnly` | Dependency cần để biên dịch nhưng không được đưa vào runtime classpath theo cấu hình này. |
| `runtimeOnly` | Dependency chỉ cần khi chạy. |
| `testImplementation` | Dependency cần cho mã kiểm thử và compile classpath của test. |
| `testRuntimeOnly` | Dependency cần khi chạy test, ví dụ test engine hoặc runtime adapter. |

Ví dụ, nếu mã nguồn gọi trực tiếp một class trong thư viện nhưng thư viện chỉ được khai báo bằng `runtimeOnly`, compiler sẽ không tìm thấy class đó. Nếu dependency được khai báo bằng `compileOnly` nhưng ứng dụng thực sự cần class đó lúc chạy, JVM có thể báo lỗi khi nạp hoặc thực thi.

### 1.1. Classpath không phải danh sách dependency khai báo

Build file mô tả yêu cầu dependency. Công cụ build phân giải các yêu cầu đó thành dependency graph, chọn phiên bản, chọn variant và tạo file collection cho từng configuration. Classpath thực tế là kết quả sau resolution, không đơn giản là những dòng `implementation` nhìn thấy trong build script.

Một thư viện có thể được đưa vào classpath bắc cầu bởi dependency khác. Ngược lại, một dependency khai báo ở một configuration có thể không xuất hiện trong configuration đang được điều tra. Khi lỗi xảy ra, cần xem đúng configuration tương ứng với tiến trình gây lỗi.

## 2. Phân loại lỗi trước khi sửa build

Thông báo lỗi thường cho biết lỗi xuất hiện ở giai đoạn compile, class loading, liên kết bytecode, khởi tạo class hay module access. Phân loại đúng giúp thu hẹp nguyên nhân.

| Thông báo hoặc loại lỗi | Thường xảy ra ở đâu? | Điều cần kiểm tra đầu tiên |
|---|---|---|
| `package ... does not exist`, `cannot find symbol` | Biên dịch | Compile classpath, source set, dependency scope và import. |
| `ClassNotFoundException` | Runtime khi code chủ động tìm class bằng tên | Tên class, classloader và runtime classpath của tiến trình gọi. |
| `NoClassDefFoundError` | Runtime khi JVM cần class nhưng không thể định nghĩa/nạp class | Class hoặc dependency bắc cầu bị thiếu; cũng kiểm tra lỗi khởi tạo class trước đó. |
| `NoSuchMethodError` | Liên kết bytecode lúc chạy | Phiên bản JAR thực tế khác phiên bản lúc biên dịch hoặc API không tương thích nhị phân. |
| `NoSuchFieldError` | Liên kết bytecode lúc chạy | Phiên bản class được nạp không có field mà caller mong đợi. |
| `AbstractMethodError` | Runtime dispatch | Implementation không còn phù hợp với interface/abstract class mà caller được biên dịch theo. |
| `IncompatibleClassChangeError` | Runtime linkage | Thay đổi kiểu khai báo, static/instance hoặc cấu trúc class/interface giữa lúc compile và runtime. |
| `UnsupportedClassVersionError` | JVM đọc bytecode | Runtime JDK quá cũ so với class file version. |
| `ServiceConfigurationError` | Service loading | Provider không có trên classpath/module path, khai báo service sai hoặc không thể khởi tạo. |
| `FindException`, `ResolutionException` | JPMS module resolution | Module path, module name, dependency `requires` hoặc module descriptor. |
| `IllegalAccessError` | JPMS hoặc binary linkage | Package không được export hoặc access đã thay đổi. |
| `InaccessibleObjectException` | Reflection với module encapsulation | Package chưa được open cho module đang thực hiện reflection. |

Tên lỗi chỉ là dấu hiệu ban đầu. Một stack trace có thể chứa lỗi gốc khác ở phần `Caused by`. Hãy tìm exception đầu tiên có ý nghĩa trong chuỗi nguyên nhân, thay vì chỉ xử lý dòng cuối cùng.

## 3. Phân biệt các lỗi class thường gặp

### 3.1. `ClassNotFoundException`

`ClassNotFoundException` thường xuất hiện khi chương trình yêu cầu nạp class bằng tên, ví dụ qua `Class.forName`, `ClassLoader.loadClass` hoặc framework/plugin thực hiện class discovery.

Ví dụ:

```java
Class<?> driver = Class.forName("org.example.Driver");
```

Nếu `org.example.Driver` không có trên classpath mà classloader đang dùng, lời gọi sẽ ném `ClassNotFoundException`.

Các câu hỏi cần trả lời:

- Tên class có đúng package và chữ hoa/chữ thường không?
- JAR chứa class có nằm trong runtime classpath của tiến trình không?
- Framework đang dùng classloader nào: context classloader, plugin classloader hay classloader của thư viện?
- Class có được đóng gói vào artifact cuối cùng không?
- Nếu class được nạp qua ServiceLoader hoặc reflection, tên provider và cấu hình discovery có đúng không?

Lỗi này không tự động có nghĩa dependency chưa được khai báo ở build file. JAR có thể đã được khai báo nhưng chỉ nằm trên compile classpath, hoặc classloader cụ thể không nhìn thấy nó.

### 3.2. `NoClassDefFoundError`

`NoClassDefFoundError` xảy ra khi JVM cần một định nghĩa class nhưng không thể tìm/nạp hoặc không thể sử dụng định nghĩa đó. Một trường hợp phổ biến là class có lúc biên dịch nhưng thiếu trên runtime classpath.

Ví dụ, ứng dụng compile với thư viện `common-core`, nhưng dependency chỉ được khai báo bằng `compileOnly`. Khi chạy, JVM cần `org.example.CommonType` mà JAR không có trong runtime classpath.

Tuy nhiên, `NoClassDefFoundError` cũng có thể xuất hiện sau khi khởi tạo class thất bại. Nếu static initializer của class ném exception, lần truy cập đầu tiên có thể báo `ExceptionInInitializerError`; những lần sau JVM có thể báo `NoClassDefFoundError: Could not initialize class ...`. Trong trường hợp này, thêm JAR vào classpath có thể hoàn toàn không liên quan. Cần tìm lỗi khởi tạo đầu tiên trong log.

### 3.3. `NoSuchMethodError` và các lỗi linkage

`NoSuchMethodError` cho biết bytecode của caller tham chiếu một method nhưng class được JVM nạp không có method với chữ ký đó. Điều này thường xảy ra khi:

- Mã được biên dịch với version mới nhưng runtime lại nạp version cũ.
- Hai thư viện bắc cầu yêu cầu các API không tương thích.
- Classpath có nhiều JAR chứa cùng class và JVM nạp nhầm bản.
- Một dependency bị force hoặc exclude khiến runtime graph khác với compile graph.

Ví dụ:

```text
Caller được biên dịch với common-core 2.x
                 |
                 v
Runtime nạp common-core 1.x
                 |
                 v
Method mới không tồn tại -> NoSuchMethodError
```

`NoSuchMethodError` không được sửa đúng cách bằng cách thêm ngẫu nhiên một JAR nữa. Cần xác định caller mong đợi API nào và runtime đã nạp class từ artifact nào.

Các lỗi liên quan như `NoSuchFieldError`, `AbstractMethodError` và `IncompatibleClassChangeError` cũng là dấu hiệu không tương thích nhị phân. Hãy so sánh bytecode caller với định nghĩa class thực tế, đặc biệt chữ ký method, field, modifier và quan hệ interface/class.

### 3.4. `UnsupportedClassVersionError`

Class file được biên dịch bằng JDK mới có thể không chạy trên runtime cũ hơn. Ví dụ class file Java 21 được đưa vào ứng dụng chạy bằng Java 17 sẽ gây lỗi phiên bản class không được hỗ trợ.

Kiểm tra cả JDK dùng để compile và JDK dùng để chạy ứng dụng. Trong Gradle, toolchain compiler và launcher có thể khác JVM khởi chạy Gradle. Chỉ nhìn `JAVA_HOME` hoặc kết quả `java -version` ở terminal chưa đủ nếu IDE, service hoặc CI job khởi chạy ứng dụng bằng một JDK khác.

## 4. Xác định lỗi thuộc compile, runtime hay test

Hãy xác định chính xác tiến trình/task gây lỗi trước khi chỉnh configuration.

### 4.1. Lỗi compile

Nếu `compileJava` hoặc `compileTestJava` thất bại với `package does not exist` hoặc `cannot find symbol`, hãy xem compile classpath tương ứng. Một dependency có thể:

- Chưa được khai báo.
- Được khai báo sai configuration.
- Không có variant phù hợp với consumer.
- Bị exclude khỏi dependency graph.
- Được resolve sang version không chứa class/API cần thiết.

Không nên thêm dependency vào `runtimeOnly` khi compiler đang thiếu class; runtime configuration không sửa compile classpath.

### 4.2. Lỗi runtime

Nếu compile thành công nhưng ứng dụng lỗi khi chạy, hãy xem runtime classpath của đúng task hoặc tiến trình. Một dependency có thể chỉ xuất hiện trong compile classpath hoặc được IDE thêm thủ công mà Gradle application task không có.

Kiểm tra:

- Runtime configuration có chứa JAR cần thiết không?
- Artifact được đóng gói có chứa dependency hay ứng dụng kỳ vọng dependency ngoài?
- Có dependency bắc cầu bị exclude không?
- Có version khác nhau giữa compile và runtime không?
- JVM thực tế có đúng classpath/launch configuration không?

### 4.3. Lỗi test

Nếu chỉ test thất bại, hãy xem `testRuntimeClasspath` và test engine. Một số trường hợp:

- Test compile được nhưng JUnit engine thiếu ở runtime.
- Test chạy được trong IDE vì IDE tự thêm thư viện, nhưng Gradle task không có dependency tương ứng.
- Một test framework hoặc plugin dùng classloader riêng.
- Test runtime nạp phiên bản khác với runtime ứng dụng.

Chạy test bằng Gradle Wrapper để tái hiện đúng môi trường build:

```bash
./gradlew test --info --stacktrace
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --info --stacktrace
```

## 5. Xem dependency graph của đúng configuration

Trong Gradle, task `dependencies` hiển thị graph cho configuration được chọn. Không nên chỉ xem `implementation` hoặc toàn bộ build file rồi suy luận runtime graph.

Ví dụ xem compile classpath:

```bash
./gradlew dependencies --configuration compileClasspath
```

Xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem test runtime classpath:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Nếu module được chọn không đúng version, dùng `dependencyInsight`:

```bash
./gradlew dependencyInsight --dependency common-core --configuration runtimeClasspath
```

Lệnh này giúp xác định:

- Dependency nào kéo module vào graph.
- Phiên bản nào được yêu cầu từ từng nhánh.
- Phiên bản nào được chọn và lý do chọn.
- Có constraint, platform, force hoặc rule nào ảnh hưởng không.

Có thể đổi configuration thành `compileClasspath` hoặc `testRuntimeClasspath` để so sánh kết quả. Nếu compile graph chọn `2.2` nhưng runtime graph chọn `1.8`, đây là manh mối quan trọng cho lỗi linkage.

### 5.1. Kiểm tra cấu hình dependency trong build script

Ví dụ:

```groovy
dependencies {
    implementation 'org.example:common-core:2.2.0'
    runtimeOnly 'org.example:database-driver:1.5.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Nếu mã chính gọi API của `common-core`, `implementation` là lựa chọn phù hợp. Nếu chỉ cần database driver khi chạy, `runtimeOnly` có thể phù hợp. Nếu test dùng JUnit, cần test API trên compile classpath và engine/launcher phù hợp trên runtime classpath theo cấu hình framework.

Không đổi `implementation` thành `api` chỉ để “thử cho chạy”. `api` dành cho dependency thuộc public API mà consumer của một Java Library cần có trên compile classpath. Nếu thư viện chỉ được ứng dụng nội bộ sử dụng, `implementation` thường phù hợp hơn.

## 6. Xác định JAR nào thực sự chứa class

Sau khi biết tên class cần tìm, hãy xác định artifact chứa class đó. Tên class đầy đủ (fully qualified class name) như `org.example.Driver` tương ứng với đường dẫn trong JAR:

```text
org/example/Driver.class
```

Dùng `jar tf` để liệt kê nội dung:

```bash
jar tf path/to/library.jar
```

Tìm class cụ thể trên Windows:

```powershell
jar tf path\to\library.jar | Select-String 'org/example/Driver.class'
```

Nếu class không nằm trong JAR, có thể dependency đã chọn không phải artifact mong đợi, class được chuyển sang module khác, hoặc class chỉ tồn tại trong variant khác.

### 6.1. Kiểm tra chữ ký class bằng `javap`

Khi gặp `NoSuchMethodError`, hãy kiểm tra class file của JAR runtime:

```bash
javap -classpath path/to/library.jar org.example.CommonType
```

Để xem chữ ký chi tiết:

```bash
javap -classpath path/to/library.jar -p -s org.example.CommonType
```

So sánh method descriptor với method mà caller cần. Có thể dùng `javap -verbose` để xem constant pool và thông tin bytecode nếu cần điều tra sâu hơn.

### 6.2. Kiểm tra JAR bị trùng class

Hai JAR có thể chứa class cùng fully qualified name. Điều này thường xảy ra khi:

- Một thư viện bị đóng gói lại trong một JAR khác.
- Dự án vừa dùng module mới vừa giữ bản shaded/uber JAR cũ.
- Một dependency cũ vẫn còn trong thư mục `lib` hoặc classpath IDE.
- Hai artifact khác tọa độ nhưng chứa cùng package/class.

Nếu có duplicate class, kết quả phụ thuộc classloader và thứ tự tìm kiếm. Không nên dựa vào thứ tự JAR để quyết định bản nào thắng. Hãy loại nguồn trùng, chọn một artifact sở hữu class hoặc dùng shading/relocation có chủ đích.

## 7. Xem classloader đã nạp class từ đâu

Classpath được khai báo chưa chắc là nguồn class mà JVM thực tế đã nạp, nhất là khi có nhiều classloader, plugin framework, application server hoặc IDE.

Trong mã Java, có thể in vị trí code source của một class:

```java
Class<?> type = org.example.CommonType.class;

System.out.println("Class: " + type.getName());
System.out.println("Loader: " + type.getClassLoader());
System.out.println("Source: " + type.getProtectionDomain()
        .getCodeSource()
        .getLocation());
System.out.println("Module: " + type.getModule());
```

`CodeSource` có thể cho biết class được nạp từ thư mục hoặc JAR nào. Một số class do bootstrap/platform loader nạp hoặc do môi trường đặc biệt định nghĩa có thể không có `CodeSource`; khi đó giá trị có thể là `null`.

### 7.1. Bật log class loading

Với JDK 9 trở lên:

```bash
java -Xlog:class+load=info -jar app.jar
```

Với JDK 8:

```bash
java -verbose:class -jar app.jar
```

Log cho biết class được nạp và nguồn tương ứng. Có thể lọc log theo tên class:

```bash
java -Xlog:class+load=info -jar app.jar 2>&1 | grep 'org.example.CommonType'
```

Trên PowerShell:

```powershell
java -Xlog:class+load=info -jar app.jar 2>&1 | Select-String 'org.example.CommonType'
```

Đây là cách xác minh class nào thực sự được JVM nạp, hữu ích khi nghi ngờ classpath chứa nhiều version hoặc classloader khác nhau.

## 8. Kiểm tra classpath của tiến trình chạy

Nếu ứng dụng được chạy bằng `java -cp`, hãy kiểm tra chính chuỗi classpath mà lệnh khởi chạy cung cấp:

```bash
java -cp "build/classes/java/main:libs/*" com.example.Main
```

Trên Windows, dấu phân tách classpath là `;`; trên Unix-like systems thường là `:`.

```powershell
java -cp "build\classes\java\main;libs\*" com.example.Main
```

Nếu dùng `-jar`, JVM lấy classpath khởi chạy từ manifest của JAR (ví dụ thuộc tính `Class-Path` nếu có). Khi dùng `-jar`, không nên giả định tùy chọn `-cp` bên ngoài sẽ bổ sung classpath như lúc chạy main class trực tiếp.

Với ứng dụng được khởi chạy qua script, service manager, container hoặc IDE, hãy lấy lệnh thực tế mà môi trường đó thực hiện. `java -version` trong terminal chỉ cho biết Java được tìm thấy trong terminal hiện tại; nó không chứng minh service hoặc IDE đang dùng cùng JDK và classpath.

## 9. Phân biệt classpath với JPMS module path

Từ Java 9, JPMS bổ sung module system. Một ứng dụng có thể dùng classpath truyền thống, module path hoặc kết hợp hai cơ chế theo quy tắc của launcher và module.

| Cơ chế | Mục đích |
|---|---|
| Classpath (`-cp` hoặc `--class-path`) | Nạp class từ classpath; các class không nằm trong named module thường thuộc unnamed module của classloader tương ứng. |
| Module path (`--module-path`) | Tìm các module có module descriptor hoặc automatic module và xây dựng module graph. |
| `module-info.java` | Khai báo tên module, dependency `requires`, package `exports`, `opens` và các directive khác. |

Ví dụ module descriptor:

```java
module com.example.app {
    requires java.sql;
    requires com.example.common;

    exports com.example.api;
}
```

`requires` cho biết module cần đọc module khác. `exports` công bố package cho module khác truy cập theo quy tắc JPMS. `opens` cho phép reflective access theo phạm vi được khai báo.

Một JAR trên classpath thường được xử lý như thành phần của unnamed module. Điều này khác với một named module trên module path, nơi readability và package encapsulation được kiểm soát rõ ràng.

### 9.1. Lỗi module không phải lúc nào cũng là lỗi thiếu JAR

Ví dụ các lỗi:

- `Module ... not found`: module cần thiết không có trên module path hoặc tên module không đúng.
- `Module ... does not read ...`: module hiện tại không có quan hệ readability cần thiết.
- `Package ... is not visible`: package không được export đến module đang truy cập.
- `IllegalAccessError`: bytecode cố truy cập thành phần không được phép theo module hoặc thay đổi binary compatibility.
- `InaccessibleObjectException`: reflection cố truy cập thành phần trong package chưa được open.

Trong những trường hợp này, thêm JAR vào classpath có thể không giải quyết được. Cần kiểm tra module graph và directive trong `module-info.java`.

### 9.2. Kiểm tra module resolution

Khi chạy ứng dụng modular:

```bash
java --show-module-resolution --module-path mods:libs --module com.example.app/com.example.Main
```

Trên Windows, thay dấu phân tách path bằng `;`:

```powershell
java --show-module-resolution --module-path "mods;libs" --module com.example.app/com.example.Main
```

Log cho biết module nào được resolve và nguồn tìm thấy. Có thể dùng `jar --describe-module` để xem tên module và descriptor của JAR:

```bash
jar --describe-module --file path/to/library.jar
```

Nếu JAR không có `module-info.class`, nó có thể trở thành automatic module khi đặt trên module path, với tên module được suy ra từ metadata/tên JAR. Không nên đoán tên module từ tên file; hãy dùng công cụ để xem kết quả thực tế.

### 9.3. `jdeps` để phân tích quan hệ module/package

`jdeps` phân tích dependency ở mức class/package/module:

```bash
jdeps --summary path/to/app.jar
```

Để xem dependency theo module:

```bash
jdeps --print-module-deps path/to/app.jar
```

Với ứng dụng modular, có thể dùng `jdeps --check` cùng module path để kiểm tra module descriptor và dependency. `jdeps` là công cụ phân tích tĩnh; nó không thay thế việc chạy ứng dụng với classpath/module path thực tế.

## 10. Kiểm tra resource và ServiceLoader

Không phải mọi lỗi “không tìm thấy” đều liên quan đến `.class`. Framework thường tìm file cấu hình hoặc resource qua classpath.

Ví dụ:

```java
try (var stream = Main.class.getResourceAsStream("/config/app.yml")) {
    if (stream == null) {
        throw new IllegalStateException("Missing config/app.yml");
    }
}
```

Resource có thể thiếu vì:

- File nằm sai source set hoặc sai thư mục resources.
- Task process resources không đưa file vào output.
- JAR cuối cùng không chứa resource.
- Đường dẫn resource tuyệt đối/tương đối bị nhầm.
- Nhiều JAR chứa resource cùng tên và thứ tự classloader làm kết quả khác dự kiến.

Kiểm tra nội dung JAR bằng `jar tf` và xem output của task `processResources` hoặc `processTestResources`.

### 10.1. ServiceLoader

Java `ServiceLoader` tìm provider theo service type. Trên classpath truyền thống, provider thường được khai báo trong file:

```text
META-INF/services/<fully-qualified-service-interface>
```

Ví dụ:

```text
META-INF/services/com.example.spi.PaymentProvider
```

File này chứa tên class implementation. Nếu file không được đóng gói, provider không có trên runtime classpath hoặc implementation không thể khởi tạo, chương trình có thể không tìm thấy service hoặc ném `ServiceConfigurationError`.

Với named module, provider có thể được khai báo trong `module-info.java` bằng directive `provides ... with ...`. Khi điều tra, phải biết ứng dụng đang dùng classpath hay module path để kiểm tra đúng cơ chế khai báo service.

## 11. Một quy trình chẩn đoán có thứ tự

Thay vì thay dependency ngay khi thấy lỗi, hãy thu thập bằng chứng theo trình tự sau.

### Bước 1: Ghi nhận môi trường và lệnh tái hiện

Ghi lại:

- Lệnh Gradle/IDE/service/container đã chạy.
- Task hoặc main class gây lỗi.
- Phiên bản Gradle Wrapper và JVM chạy Gradle.
- JDK compiler và JDK runtime thực tế.
- Hệ điều hành và môi trường CI/local.
- Toàn bộ stack trace, đặc biệt phần `Caused by` đầu tiên.

Lệnh xem Gradle/JVM:

```bash
./gradlew --version
java -version
javac -version
```

Nếu ứng dụng được khởi chạy từ IDE hoặc service, hãy xác nhận JDK ở chính cấu hình đó.

### Bước 2: Xác định giai đoạn lỗi

Hỏi lỗi xuất hiện trong `compileJava`, `test`, `run`, lúc đóng gói hay sau khi triển khai. Giai đoạn quyết định configuration nào cần xem. Không dùng `runtimeClasspath` để giải thích một lỗi compile nếu compile task đang dùng `compileClasspath`.

### Bước 3: Phân loại exception

Phân biệt lỗi không tìm class, lỗi liên kết method, lỗi khởi tạo class, lỗi bytecode version, lỗi resource và lỗi JPMS. Tìm exception đầu tiên trong cause chain.

### Bước 4: Xem dependency graph đúng configuration

Chạy `dependencies` và `dependencyInsight` cho `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` hoặc configuration tương ứng. Xác định module và version được chọn.

### Bước 5: Xác minh artifact thực tế

Dùng `jar tf` để tìm class/resource. Dùng `javap` để xem chữ ký class. Nếu có thể, in `CodeSource` hoặc bật class loading log để biết JVM nạp class từ JAR nào.

### Bước 6: Kiểm tra classpath/module path của tiến trình

Đối chiếu lệnh khởi chạy thực tế, manifest, `-cp`, `--class-path`, `--module-path` và module descriptor. Không giả định classpath của Gradle task giống classpath trong IDE hoặc service.

### Bước 7: Chỉ thay đổi cấu hình khi nguyên nhân đã rõ

Chọn thay đổi nhỏ nhất phù hợp với bằng chứng: sửa dependency scope, cập nhật version, bỏ dependency trùng, thêm runtime library còn thiếu, sửa resource path hoặc điều chỉnh module descriptor. Sau đó chạy lại task tối thiểu để xác nhận và chạy phạm vi test/build cần thiết.

## 12. Ví dụ điều tra các tình huống phổ biến

### 12.1. Compile thành công nhưng runtime báo `ClassNotFoundException`

Giả sử project dùng reflection để nạp `org.example.Driver`. Compiler không cần class này vì tên class được truyền dưới dạng String, nên compile có thể thành công dù driver không có trên runtime classpath.

Kiểm tra:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency driver --configuration runtimeClasspath
```

Nếu driver chỉ được khai báo trong `compileOnly` hoặc không được khai báo, thêm dependency vào configuration runtime phù hợp. Nếu driver do container cung cấp, xác nhận container có thực sự cung cấp class đó trước khi thêm vào ứng dụng.

### 12.2. Runtime báo `NoSuchMethodError`

Giả sử `library-a` được biên dịch với `common-core:2.2`, nhưng runtime graph chọn `common-core:1.8` do constraint hoặc force. Hãy xem:

```bash
./gradlew dependencyInsight --dependency common-core --configuration compileClasspath
./gradlew dependencyInsight --dependency common-core --configuration runtimeClasspath
```

Sau đó xác định JAR runtime bằng class loading log và kiểm tra method bằng `javap`. Nếu runtime graph thực sự chọn version cũ, điều tra nhánh kéo version đó vào, constraint, force hoặc dependency substitution. Chỉ nâng version sau khi xác nhận các consumer tương thích.

### 12.3. Test chạy trong IDE nhưng thất bại khi chạy Gradle

IDE có thể thêm test engine hoặc thư viện vào classpath theo cấu hình riêng. Hãy chạy `./gradlew test --info --stacktrace`, xem `testRuntimeClasspath` và kiểm tra dependency engine. Nếu chỉ thiếu test engine, khai báo đúng `testRuntimeOnly` theo framework đang dùng. Không thêm toàn bộ thư viện IDE vào `implementation` của ứng dụng.

### 12.4. Ứng dụng lỗi `UnsupportedClassVersionError` trên server

Kiểm tra phiên bản JDK chạy server, class file version của class lỗi và `options.release` của compiler. Nếu sản phẩm cần chạy trên Java 17, cấu hình compiler phù hợp và kiểm thử artifact trên runtime Java 17. Không chỉ đổi `JAVA_HOME` trên máy phát triển rồi cho rằng server đã được cập nhật.

### 12.5. `InaccessibleObjectException` sau khi nâng JDK

Lỗi có thể do framework dùng reflection vào package trong named module chưa được mở. Xác định module nguồn và module caller, xem tài liệu framework và module descriptor. `--add-opens` có thể là giải pháp chuyển tiếp khi thực sự cần, nhưng nên ưu tiên nâng framework hoặc sửa module openness đúng phạm vi. Không thêm hàng loạt `--add-opens` mà không biết package nào đang bị truy cập.

## 13. Những thay đổi dễ làm lỗi nặng hơn

Một số thao tác có vẻ nhanh nhưng có thể che giấu nguyên nhân:

- **Thêm mọi JAR vào classpath:** có thể tạo duplicate class, version conflict và che khuất lỗi dependency graph.
- **Dùng `force` ngay lập tức:** có thể sửa một nhánh nhưng làm hỏng consumer khác hoặc làm runtime graph khác compile graph.
- **Exclude dependency mà chưa xem ai dùng:** có thể loại bỏ class bắc cầu cần thiết ở runtime.
- **Đổi `implementation` thành `api` tùy tiện:** làm dependency rò rỉ ra public compile API của library và mở rộng classpath consumer.
- **Chuyển dependency thành `runtimeOnly` để hết lỗi compile:** không thể cung cấp API cho compiler.
- **Dùng `--add-opens` cho mọi package:** che giấu vấn đề tương thích module/reflection và làm giảm encapsulation.
- **Dựa vào thứ tự JAR:** classloader có thể nạp một class trùng tên từ artifact không mong muốn; kết quả có thể thay đổi giữa môi trường.
- **Xóa cache trước khi thu thập bằng chứng:** có thể làm mất manh mối về artifact đã resolve hoặc tái hiện khác với môi trường lỗi. Cache refresh chỉ nên thực hiện khi có lý do.

Thay đổi classpath cần có lý do dựa trên graph và artifact thực tế. Nếu không biết class nào bị thiếu hoặc JAR nào đang được nạp, việc thêm dependency là một phép thử mù, không phải chẩn đoán.

## 14. Công cụ hỗ trợ điều tra

| Công cụ/lệnh | Dùng để làm gì? |
|---|---|
| `./gradlew dependencies --configuration ...` | Xem dependency graph của configuration. |
| `./gradlew dependencyInsight --dependency ... --configuration ...` | Tìm nhánh yêu cầu và lý do version được chọn. |
| `./gradlew tasks --all` | Xem task có sẵn để xác định task compile/test/run tương ứng. |
| `./gradlew test --info --stacktrace` | Xem log chi tiết và stack trace của test task. |
| `jar tf file.jar` | Liệt kê class và resource trong JAR. |
| `javap -classpath ... ClassName` | Xem API/chữ ký class đã biên dịch. |
| `java -Xlog:class+load=info ...` | Theo dõi class được JVM nạp và nguồn nạp. |
| `jar --describe-module --file ...` | Xem module name và descriptor của JAR. |
| `jdeps --summary ...` | Phân tích dependency ở mức package/module. |
| `java --show-module-resolution ...` | Quan sát quá trình resolve module của JPMS. |

Mỗi công cụ trả lời một câu hỏi khác nhau. Dependency graph cho biết Gradle dự kiến đưa artifact nào vào configuration; `jar tf` cho biết artifact chứa gì; class loading log cho biết JVM đã nạp gì; `javap` cho biết class thực tế cung cấp API nào. Ghép các bằng chứng này sẽ giúp xác định chính xác vị trí sai lệch.

## 15. Checklist chẩn đoán trước khi sửa

- [ ] Đã xác định lệnh và tiến trình thực tế gây lỗi.
- [ ] Đã ghi lại JDK/Gradle version của đúng môi trường chạy.
- [ ] Đã đọc cause chain và phân loại exception.
- [ ] Đã xác định lỗi nằm ở compile, runtime, test hay JPMS resolution/access.
- [ ] Đã xem đúng configuration (`compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`...).
- [ ] Đã tìm nhánh dependency và version thực tế được chọn.
- [ ] Đã xác minh JAR có class/resource cần thiết.
- [ ] Đã xác định classloader và nguồn class được nạp nếu nghi ngờ duplicate/version mismatch.
- [ ] Đã kiểm tra classpath so với module path nếu dự án dùng JPMS.
- [ ] Đã chọn một thay đổi nhỏ, có giải thích và có cách kiểm chứng.

Nhận diện lỗi classpath hiệu quả bắt đầu từ exception và tiến trình thực tế, sau đó lần theo configuration, dependency graph, artifact và classloader. Khi dùng JPMS, cần kiểm tra thêm module graph cùng các directive `requires`, `exports` và `opens`. Chỉ sau khi biết class nào thiếu hoặc sai phiên bản, JAR nào đang được nạp và ở giai đoạn nào lỗi xảy ra, mới nên thay đổi dependency scope, version hay module configuration. Cách làm dựa trên bằng chứng giúp build ổn định hơn và tránh những thay đổi mò mẫm làm phát sinh lỗi mới.
